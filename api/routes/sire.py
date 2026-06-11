"""
Endpoints de la API para operaciones SIRE.

Define el endpoint POST /api/v1/sire/descargar que recibe las solicitudes
del orquestador, valida los datos, crea el registro de operación en BD
y encola la tarea en Celery.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas import DescargarRequest, DescargarResponse
from core.database import get_session_sync
from models.otras_credenciales import OtraCredencial
from models.operaciones import SireOperacion, EstadoOperacion
from workers.sire_tasks import task_solicitar_descarga_sire

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sire", tags=["SIRE"])


@router.post(
    "/descargar",
    status_code=202,
    response_model=DescargarResponse,
    summary="Encola una descarga de propuesta SIRE",
    description=(
        "Valida que existan credenciales SIRE para el RUC, crea un registro "
        "de operación en estado PENDING y encola la tarea en Celery. "
        "Retorna inmediatamente con HTTP 202 Accepted."
    ),
)
def descargar_propuesta(
    request: DescargarRequest,
    session: Session = Depends(get_session_sync),
):
    """
    Encola una tarea de descarga de propuesta SIRE.

    Args:
        request: Cuerpo de la solicitud con ruc, periodo, tipo y webhook_url.
        session: Sesión de BD (inyectada por FastAPI).

    Returns:
        DescargarResponse con job_id y estado "accepted".

    Raises:
        HTTPException 404: Si no existen credenciales SIRE para el RUC.
        HTTPException 422: Si los datos de entrada no pasan las validaciones.
    """
    # ---- Paso 1: Validar que existan credenciales SIRE para este RUC ----
    logger.info(
        "Validando credenciales SIRE para RUC %s, periodo %s, tipo %s",
        request.ruc, request.periodo, request.tipo,
    )

    cred = (
        session.query(OtraCredencial)
        .filter(
            OtraCredencial.ruc == int(request.ruc),
            OtraCredencial.tipo == "APISUNAT",
            OtraCredencial.notas == "SIRE",
        )
        .first()
    )

    if not cred:
        logger.warning(
            "Credenciales SIRE no encontradas para RUC %s", request.ruc
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No se encontraron credenciales SIRE para el RUC {request.ruc}. "
                "Verifique que exista un registro en priv.otras_credenciales "
                "con tipo='APISUNAT' y notas='SIRE'."
            ),
        )

    logger.debug(
        "Credenciales encontradas: RUC=%s, usuario=%s",
        cred.ruc, cred.usuario,
    )

    # ---- Paso 2: Crear registro de operación en estado PENDING ----
    operacion = SireOperacion(
        ruc=int(request.ruc),
        periodo=request.periodo,
        tipo_operacion=request.tipo,
        estado=EstadoOperacion.PENDING,
        log="Operación creada. Encolando tarea en Celery...",
    )
    session.add(operacion)
    session.commit()
    session.refresh(operacion)

    logger.info(
        "Operación %s creada para RUC %s, periodo %s, tipo %s",
        operacion.id, request.ruc, request.periodo, request.tipo,
    )

    # ---- Paso 3: Encolar tarea en Celery ----
    task_solicitar_descarga_sire.delay(
        ruc=int(request.ruc),
        periodo=request.periodo,
        tipo=request.tipo,
        webhook_url=request.webhook_url or "",
        operacion_id=operacion.id,
    )

    logger.info(
        "Tarea encolada para operación %s, RUC %s", operacion.id, request.ruc
    )

    # ---- Paso 4: Retornar 202 Accepted inmediatamente ----
    return DescargarResponse(
        status="accepted",
        job_id=str(operacion.id),
        message="Tarea de descarga encolada correctamente",
    )