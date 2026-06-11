"""
Tareas background de Celery para operaciones SIRE.

Define dos tareas que se encadenan automáticamente:

1. task_solicitar_descarga_sire (RÁPIDA, ~1-2s):
   - Obtiene credenciales
   - Solicita descarga a SUNAT → ticket
   - Actualiza BD: PROCESSING + ticket
   - Encola la tarea 2

2. task_consultar_descarga_sire (LA QUE TARDA):
   - Polling cada 30s (máx 10 min)
   - Descarga archivo en memoria
   - Sube a S3
   - Webhook

Esto permite que el orquestador encole muchas solicitudes y TODAS se ejecuten
rápidamente, dejando las consultas para después (priorización FIFO natural).
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


# ============================================================================
# TAREA 1: SOLICITAR DESCARGA (RÁPIDA, ~1-2s)
# ============================================================================

@celery_app.task(
    bind=True,
    max_retries=0,
    acks_late=True,
    task_track_started=True,
)
def task_solicitar_descarga_sire(
    self,
    ruc: int,
    periodo: str,
    tipo: str,
    webhook_url: str = "",
    operacion_id: Optional[int] = None,
) -> dict:
    """
    Tarea RÁPIDA que solo solicita la descarga a SUNAT.

    Flujo:
    1. Obtiene credenciales SIRE del RUC.
    2. Solicita descarga a SUNAT → ticket.
    3. Actualiza BD a PROCESSING con el ticket.
    4. Encola la tarea de consulta+descarga para este ticket.

    Al ser rápida, los workers pueden procesar muchas solicitudes
    en poco tiempo, dejando las consultas para después.
    """
    logger.info(
        "Solicitando descarga SIRE: RUC=%s, periodo=%s, tipo=%s",
        ruc, periodo, tipo,
    )

    session = next(get_session_sync())

    try:
        # ---- Obtener credenciales ----
        cred = _obtener_credenciales(session, ruc)

        if not cred:
            error_msg = (
                f"No se encontraron credenciales SIRE completas para RUC {ruc}."
            )
            logger.error(error_msg)
            _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, error_msg)
            return {"status": "error", "message": error_msg}

        # ---- Solicitar descarga (asíncrono, pero rápido) ----
        ticket = asyncio.run(
            _solicitar_ticket(
                ruc=str(ruc),
                client_id=cred["client_id"],
                client_secret=cred["client_secret"],
                user_sol=cred["user_sol"],
                clave_sol=cred["clave_sol"],
                periodo=periodo,
                tipo=tipo,
            )
        )

        # ---- Actualizar BD ----
        _actualizar_estado(
            operacion_id,
            session,
            EstadoOperacion.PROCESSING,
            log=f"Ticket generado: {ticket}",
            ticket=ticket,
        )

        logger.info(
            "Ticket obtenido: %s para RUC %s. Encolando consulta...",
            ticket, ruc,
        )

        # ---- Encolar tarea de consulta+descarga ----
        # La tarea de consulta recibe las credenciales directamente
        # para no tener que consultar BD nuevamente
        task_consultar_descarga_sire.delay(
            ruc=ruc,
            periodo=periodo,
            tipo=tipo,
            ticket=ticket,
            webhook_url=webhook_url,
            operacion_id=operacion_id,
            client_id=cred["client_id"],
            client_secret=cred["client_secret"],
            user_sol=cred["user_sol"],
            clave_sol=cred["clave_sol"],
        )

        return {"status": "solicitado", "ticket": ticket}

    except Exception as e:
        logger.exception("Error solicitando descarga SIRE para RUC %s", ruc)
        _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, str(e))
        return {"status": "error", "message": str(e)}

    finally:
        session.close()


async def _solicitar_ticket(
    ruc: str,
    client_id: str,
    client_secret: str,
    user_sol: str,
    clave_sol: str,
    periodo: str,
    tipo: str,
) -> str:
    """
    Función asíncrona para solicitar un ticket de descarga.
    Separada para poder ejecutarla con asyncio.run() desde la tarea síncrona.
    """
    async with SireClient(
        ruc=ruc,
        client_id=client_id,
        client_secret=client_secret,
        user_sol=user_sol,
        clave_sol=clave_sol,
    ) as client:
        ticket = await client.solicitar_descarga_propuesta(periodo, tipo)
        return ticket


# ============================================================================
# TAREA 2: CONSULTAR ESTADO + DESCARGAR + SUBIR (LA QUE TARDA)
# ============================================================================

@celery_app.task(
    bind=True,
    max_retries=0,
    acks_late=True,
    task_track_started=True,
)
def task_consultar_descarga_sire(
    self,
    ruc: int,
    periodo: str,
    tipo: str,
    ticket: str,
    webhook_url: str = "",
    operacion_id: Optional[int] = None,
    client_id: str = "",
    client_secret: str = "",
    user_sol: str = "",
    clave_sol: str = "",
) -> dict:
    """
    Tarea que consulta el estado del ticket, descarga y sube a S3.

    Flujo:
    1. Polling cada 30s (máx 10 min) a consultar_estado_ticket.
       • SIN_DATOS → BD: EMPTY, webhook, return.
       • COMPLETADO → continúa.
       • ERROR → raise.
    2. Descarga archivo en memoria.
       • es_vacio → BD: EMPTY, webhook, return.
    3. Sube a S3 → BD: S3_UPLOADED.
    4. Envía webhook → BD: WEBHOOK_SENT.
    """
    logger.info(
        "Consultando descarga SIRE: RUC=%s, periodo=%s, tipo=%s, ticket=%s",
        ruc, periodo, tipo, ticket,
    )

    session = next(get_session_sync())

    try:
        storage = S3StorageManager()

        result = asyncio.run(
            _ejecutar_consulta_descarga(
                ruc=str(ruc),
                client_id=client_id,
                client_secret=client_secret,
                user_sol=user_sol,
                clave_sol=clave_sol,
                periodo=periodo,
                tipo=tipo,
                ticket=ticket,
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
        logger.exception("Error fatal en task_consultar_descarga_sire")
        _actualizar_estado(operacion_id, session, EstadoOperacion.ERROR, str(e))
        return {"status": "error", "message": str(e)}

    finally:
        session.close()


async def _ejecutar_consulta_descarga(
    ruc: str,
    client_id: str,
    client_secret: str,
    user_sol: str,
    clave_sol: str,
    periodo: str,
    tipo: str,
    ticket: str,
    operacion_id: Optional[int],
    session,
    storage: S3StorageManager,
    webhook_url: str,
) -> dict:
    """
    Ejecuta el polling, descarga y subida a S3 de forma asíncrona.
    """
    async with SireClient(
        ruc=ruc,
        client_id=client_id,
        client_secret=client_secret,
        user_sol=user_sol,
        clave_sol=clave_sol,
    ) as client:

        # ---- Polling de estado ----
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

        if estado_ticket.status != "LISTO":
            error_msg = (
                f"Ticket {ticket} finalizó con estado inesperado: "
                f"{estado_ticket.status} - {estado_ticket.mensaje}"
            )
            raise Exception(error_msg)

        # ---- Descargar archivo ----
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

        # ---- Subir a S3 ----
        nom_archivo = download.nom_archivo or f"{periodo}_{tipo}_{ticket}.zip"
        s3_key = f"unparsin/{nom_archivo}"
        s3_url = storage.upload_file_bytes(download.contenido, s3_key)

        logger.info(
            "Archivo subido a S3: %s (tamaño: %d bytes, nombre: %s)",
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

        # ---- Enviar webhook ----
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
    """Realiza polling al estado del ticket cada POLL_INTERVAL segundos."""
    for intento in range(1, MAX_POLL_ATTEMPTS + 1):
        await asyncio.sleep(POLL_INTERVAL)

        estado = await client.consultar_estado_ticket(ticket, periodo)
        logger.info(
            "Polling ticket %s: intento %d/%d, status=%s (cod=%s)",
            ticket, intento, MAX_POLL_ATTEMPTS,
            estado.status, estado.cod_estado,
        )

        if estado.status in ("LISTO", "SIN_DATOS"):
            return estado

        if estado.status == "ERROR":
            raise Exception(
                f"SUNAT reportó error en ticket {ticket}: {estado.mensaje}"
            )

    raise TimeoutError(
        f"Ticket {ticket} no se completó en {MAX_WAIT_SECONDS}s "
        f"({MAX_POLL_ATTEMPTS} intentos)"
    )


# ============================================================================
# FUNCIONES COMPARTIDAS
# ============================================================================

def _obtener_credenciales(session, ruc: int) -> Optional[dict]:
    """
    Obtiene las 4 credenciales necesarias para SIRE.
    JOIN entre priv.otras_credenciales y priv.entities.
    """
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

    ent = (
        session.query(EntityCredencial)
        .filter(EntityCredencial.ruc == ruc)
        .first()
    )

    if not ent or not ent.usuario_sol or not ent.clave_sol:
        logger.warning(
            "RUC %s: credenciales SOL no encontradas en priv.entities", ruc
        )
        return None

    return {
        "client_id": oc.usuario,
        "client_secret": oc.contrasena,
        "user_sol": ent.usuario_sol,
        "clave_sol": ent.clave_sol,
    }


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
            webhook_url, estado, ruc,
        )
    except Exception as e:
        logger.error("Error al enviar webhook a %s: %s", webhook_url, e)