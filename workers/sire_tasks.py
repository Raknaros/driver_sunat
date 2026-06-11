"""
Tareas background de Celery para operaciones SIRE.

Define la tarea principal `task_procesar_descarga_sire` que ejecuta
el flujo completo de descarga de propuestas desde SUNAT:

1. Obtiene credenciales SIRE del RUC desde la BD (JOIN entre otras_cred + entities).
2. Solicita la descarga a SUNAT.
3. Hace polling cada 30s (máx 10 min) hasta que SUNAT completa el procesamiento.
4. Descarga el archivo ZIP en memoria.
5. Sube el archivo a AWS S3.
6. Notifica al orquestador vía webhook.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import update

from workers.celery_app import celery_app
from core.database import get_session_sync
from core.storage import S3StorageManager
from models.entities import EntityCredencial
from models.otras_credenciales import OtraCredencial
from models.operaciones import SireOperacion, EstadoOperacion
from api_clients.sire.client import SireClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de polling
# ---------------------------------------------------------------------------
POLL_INTERVAL = 30           # segundos entre cada consulta de estado
MAX_WAIT_SECONDS = 600       # 10 minutos máximo de espera
MAX_POLL_ATTEMPTS = MAX_WAIT_SECONDS // POLL_INTERVAL  # ~20 intentos


@celery_app.task(
    bind=True,
    max_retries=0,
    acks_late=True,
    task_track_started=True,
)
def task_procesar_descarga_sire(
    self,
    ruc: int,
    periodo: str,
    tipo: str,
    webhook_url: str = "",
    operacion_id: Optional[int] = None,
) -> dict:
    """
    Tarea principal de Celery para procesar una descarga SIRE.

    Args:
        ruc: Número RUC del contribuyente.
        periodo: Período en formato AAAAMM (ej: "202501").
        tipo: Tipo de propuesta ("ventas" o "compras").
        webhook_url: URL del orquestador para notificar el resultado.
        operacion_id: ID de la operación en BD para actualizar estado.

    Returns:
        dict: Resultado de la operación con estado, ticket y s3_url.
    """
    logger.info(
        "Iniciando task_procesar_descarga_sire: RUC=%s, periodo=%s, tipo=%s",
        ruc, periodo, tipo,
    )

    session = next(get_session_sync())

    try:
        storage = S3StorageManager()

        # ---- PASO 1: Obtener credenciales (JOIN entre ambas tablas) ----
        cred = _obtener_credenciales(session, ruc)

        if not cred:
            error_msg = (
                f"No se encontraron credenciales SIRE completas para RUC {ruc}. "
                "Verifique que existan registros en priv.otras_credenciales "
                "(tipo='APISUNAT', notas='SIRE') y priv.entities (activo=TRUE)."
            )
            logger.error(error_msg)
            _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, error_msg)
            return {"status": "error", "message": error_msg}

        # ---- PASO 2-7: Ejecutar flujo asíncrono ----
        result = asyncio.run(
            _ejecutar_flujo_descarga(
                ruc=str(ruc),
                client_id=cred["client_id"],
                client_secret=cred["client_secret"],
                user_sol=cred["user_sol"],
                clave_sol=cred["clave_sol"],
                periodo=periodo,
                tipo=tipo,
                operacion_id=operacion_id,
                session=session,
                storage=storage,
                webhook_url=webhook_url,
            )
        )
        return result

    except TimeoutError as e:
        logger.error("Timeout en descarga SIRE: %s", e)
        _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, str(e))
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.exception("Error fatal en task_procesar_descarga_sire")
        _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, str(e))
        return {"status": "error", "message": str(e)}

    finally:
        session.close()


def _obtener_credenciales(session, ruc: int) -> Optional[dict]:
    """
    Obtiene las 4 credenciales necesarias para SIRE.

    Hace un JOIN entre:
    - priv.otras_credenciales (oc) → client_id, client_secret
    - priv.entities (e) → user_sol, clave_sol
    """
    # Buscar credenciales de API (otras_credenciales)
    oc = (
        session.query(OtraCredencial)
        .filter(
            OtraCredencial.ruc == ruc,
            OtraCredencial.tipo == "APISUNAT",
            OtraCredencial.notas == "SIRE",
        )
        .first()
    )

    if not oc:
        return None

    # Buscar credenciales SOL (entities)
    ent = (
        session.query(EntityCredencial)
        .filter(
            EntityCredencial.ruc == ruc,
        )
        .first()
    )

    if not ent or not ent.usuario_sol or not ent.clave_sol:
        logger.warning(
            "RUC %s: credenciales SOL no encontradas en priv.entities "
            "(usuario_sol o clave_sol vacíos)", ruc
        )
        return None

    return {
        "client_id": oc.usuario,
        "client_secret": oc.contrasena,
        "user_sol": ent.usuario_sol,
        "clave_sol": ent.clave_sol,
    }


async def _ejecutar_flujo_descarga(
    ruc: str,
    client_id: str,
    client_secret: str,
    user_sol: str,
    clave_sol: str,
    periodo: str,
    tipo: str,
    operacion_id: Optional[int],
    session,
    storage: S3StorageManager,
    webhook_url: str,
) -> dict:
    """
    Ejecuta el flujo completo de descarga SIRE de forma asíncrona.
    """
    async with SireClient(
        ruc=ruc,
        client_id=client_id,
        client_secret=client_secret,
        user_sol=user_sol,
        clave_sol=clave_sol,
    ) as client:

        # ---- PASO 2 y 3: Solicitar descarga y actualizar BD ----
        ticket = await client.solicitar_descarga_propuesta(periodo, tipo)

        logger.info("Ticket obtenido: %s para RUC %s periodo %s", ticket, ruc, periodo)
        _actualizar_estado(
            operacion_id,
            session,
            EstadoOperacion.PROCESSING,
            log=f"Ticket generado: {ticket}",
            ticket=ticket,
        )

        # ---- PASO 4: Polling de estado ----
        estado_ticket = await _polling_estado_ticket(client, ticket, periodo)

        if estado_ticket.status == "SIN_DATOS":
            _actualizar_estado(
                operacion_id,
                session,
                EstadoOperacion.EMPTY,
                log="Reporte generado correctamente pero sin datos.",
            )
            _enviar_webhook(
                webhook_url,
                ruc=ruc,
                periodo=periodo,
                tipo=tipo,
                estado="EMPTY",
                s3_url=None,
            )
            return {"status": "empty", "ticket": ticket}

        # Si el estado no es LISTO, es un error
        if estado_ticket.status != "LISTO":
            error_msg = (
                f"Ticket {ticket} finalizó con estado inesperado: "
                f"{estado_ticket.status} - {estado_ticket.mensaje}"
            )
            raise Exception(error_msg)

        # ---- PASO 5: Descargar archivo ----
        download = await client.descargar_archivo(estado_ticket.parametros_descarga)

        if download.es_vacio:
            _actualizar_estado(
                operacion_id,
                session,
                EstadoOperacion.EMPTY,
                log="Archivo descargado vacío (sin registros).",
            )
            _enviar_webhook(
                webhook_url,
                ruc=ruc,
                periodo=periodo,
                tipo=tipo,
                estado="EMPTY",
                s3_url=None,
            )
            return {"status": "empty", "ticket": ticket}

        # ---- PASO 6: Subir a S3 ----
        nom_archivo = download.nom_archivo or f"{periodo}_{tipo}_{ticket}.zip"
        s3_key = f"unparsin/{nom_archivo}"
        s3_url = storage.upload_file_bytes(download.contenido, s3_key)

        logger.info(
            "Archivo subido a S3: %s (tamaño: %d bytes, nombre original: %s)",
            s3_url,
            len(download.contenido),
            nom_archivo,
        )
        _actualizar_estado(
            operacion_id,
            session,
            EstadoOperacion.S3_UPLOADED,
            log=f"Subido a S3: {s3_url} (archivo: {nom_archivo})",
            s3_url=s3_url,
        )

        # ---- PASO 7: Enviar webhook ----
        _enviar_webhook(
            webhook_url,
            ruc=ruc,
            periodo=periodo,
            tipo=tipo,
            estado="COMPLETED",
            s3_url=s3_url,
        )

        _actualizar_estado(
            operacion_id,
            session,
            EstadoOperacion.WEBHOOK_SENT,
            log="Webhook enviado correctamente al orquestador.",
        )

        return {
            "status": "success",
            "ticket": ticket,
            "s3_url": s3_url,
            "nom_archivo": nom_archivo,
        }


async def _polling_estado_ticket(
    client: SireClient, ticket: str, periodo: str
):
    """
    Realiza polling al estado del ticket cada POLL_INTERVAL segundos,
    hasta un máximo de MAX_POLL_ATTEMPTS intentos.
    """
    for intento in range(1, MAX_POLL_ATTEMPTS + 1):
        await asyncio.sleep(POLL_INTERVAL)

        estado = await client.consultar_estado_ticket(ticket, periodo)
        logger.info(
            "Polling ticket %s: intento %d/%d, status=%s (cod=%s)",
            ticket,
            intento,
            MAX_POLL_ATTEMPTS,
            estado.status,
            estado.cod_estado,
        )

        if estado.status in ("LISTO", "SIN_DATOS"):
            return estado

        if estado.status == "ERROR":
            raise Exception(
                f"SUNAT reportó error en ticket {ticket}: {estado.mensaje}"
            )

        # Estados intermedios: PROCESANDO → seguir esperando

    raise TimeoutError(
        f"Ticket {ticket} no se completó en {MAX_WAIT_SECONDS}s "
        f"({MAX_POLL_ATTEMPTS} intentos)"
    )


def _actualizar_estado(
    operacion_id: Optional[int],
    session,
    estado: EstadoOperacion,
    log: Optional[str] = None,
    ticket: Optional[str] = None,
    s3_url: Optional[str] = None,
):
    """Actualiza el estado de una operación en la BD."""
    if not operacion_id:
        return

    updates = {"estado": estado}
    if log is not None:
        updates["log"] = log
    if ticket is not None:
        updates["ticket"] = ticket
    if s3_url is not None:
        updates["s3_url"] = s3_url

    stmt = update(SireOperacion).where(SireOperacion.id == operacion_id).values(**updates)
    session.execute(stmt)
    session.commit()

    logger.info("Operación %s actualizada a %s", operacion_id, estado.value)


def _enviar_webhook(
    webhook_url: str,
    ruc: str,
    periodo: str,
    tipo: str,
    estado: str,
    s3_url: Optional[str],
):
    """Envía una notificación al orquestador vía webhook."""
    if not webhook_url:
        logger.warning("Webhook no enviado: URL vacía")
        return

    payload = {
        "ruc": ruc,
        "periodo": periodo,
        "tipo": tipo,
        "estado": estado,
        "s3_url": s3_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = httpx.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(
            "Webhook enviado a %s: estado=%s, ruc=%s",
            webhook_url,
            estado,
            ruc,
        )
    except Exception as e:
        logger.error("Error al enviar webhook a %s: %s", webhook_url, e)