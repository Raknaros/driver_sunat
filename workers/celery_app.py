"""
Configuración de Celery para el microservicio driver_sunat.

Define la instancia de Celery que se conecta a Redis (broker y backend)
e incluye automáticamente las tareas definidas en workers.sire_tasks.
"""

from celery import Celery
from core.config import settings

celery_app = Celery(
    "driver_sunat",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.sire_tasks"],
)

# Configuración general
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Lima",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)