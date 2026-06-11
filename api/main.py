"""
Punto de entrada de la aplicación FastAPI.

Configura la aplicación, incluye los routers y define el endpoint
de health check para Docker/Kubernetes.
"""

import logging

import redis
from fastapi import FastAPI
from sqlalchemy import text

from api.routes.sire import router as sire_router
from api.schemas import HealthResponse
from core.config import settings
from core.database import SessionSync
from core.init_db import init_database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Creación de la aplicación FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Driver SUNAT - SIRE Microservice",
    description=(
        "Microservicio headless para descarga de propuestas SIRE. "
        "Provee endpoints REST para que el orquestador encargue tareas "
        "de descarga que se procesan de forma asíncrona con Celery."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Inicialización de la base de datos al arrancar
# ---------------------------------------------------------------------------
init_database()

# ---------------------------------------------------------------------------
# Inclusión de routers
# ---------------------------------------------------------------------------
app.include_router(sire_router)


# ---------------------------------------------------------------------------
# Endpoint de Health Check
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["Health"],
    response_model=HealthResponse,
    summary="Health check del microservicio",
    description=(
        "Verifica el estado de las dependencias externas: "
        "conexión a PostgreSQL y conexión a Redis. "
        "Retorna 'healthy' si todo funciona o 'degraded' si alguna "
        "dependencia falla."
    ),
)
def health_check():
    """
    Endpoint de health check para Docker/Kubernetes.

    Realiza chequeos básicos de conectividad con:
    - PostgreSQL (SELECT 1)
    - Redis (PING)

    Returns:
        dict: Estado general y chequeos individuales.
    """
    health_status = {"status": "healthy", "checks": {}}

    # ---- Check PostgreSQL ----
    try:
        session = SessionSync()
        session.execute(text("SELECT 1"))
        session.close()
        health_status["checks"]["database"] = "ok"
        logger.debug("Health check - Database: ok")
    except Exception as e:
        error_msg = f"error: {e}"
        health_status["checks"]["database"] = error_msg
        health_status["status"] = "degraded"
        logger.warning("Health check - Database: %s", error_msg)

    # ---- Check Redis ----
    try:
        r = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=3,
            decode_responses=True,
        )
        r.ping()
        r.close()
        health_status["checks"]["redis"] = "ok"
        logger.debug("Health check - Redis: ok")
    except Exception as e:
        error_msg = f"error: {e}"
        health_status["checks"]["redis"] = error_msg
        health_status["status"] = "degraded"
        logger.warning("Health check - Redis: %s", error_msg)

    return health_status