"""
Inicialización de la base de datos.

Crea el schema y tablas necesarias si no existen.
Se ejecuta al arrancar la aplicación FastAPI.
"""

import logging

from sqlalchemy import text

from core.database import engine_sync

logger = logging.getLogger(__name__)


def init_database():
    """
    Crea el schema 'driver' y la tabla 'sire_operaciones' si no existen.
    Esta operación es idempotente (se puede ejecutar múltiples veces sin efectos
    secundarios).
    """
    logger.info("Inicializando base de datos...")

    with engine_sync.connect() as conn:
        # Crear schema driver si no existe
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS driver"))
        conn.commit()

        logger.info("Schema 'driver' verificado/creado.")

        # Crear tabla driver.sire_operaciones si no existe
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS driver.sire_operaciones (
                    id SERIAL PRIMARY KEY,
                    ruc BIGINT NOT NULL,
                    periodo VARCHAR(6) NOT NULL,
                    tipo_operacion VARCHAR(50) NOT NULL,
                    ticket VARCHAR(100),
                    s3_url VARCHAR(500),
                    estado VARCHAR(20) DEFAULT 'PENDING',
                    log TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                )
            """)
        )
        conn.commit()

        # Crear índice si no existe
        conn.execute(
            text("""
                CREATE INDEX IF NOT EXISTS idx_sire_operaciones_ruc
                ON driver.sire_operaciones(ruc)
            """)
        )
        conn.commit()

        logger.info("Tabla 'driver.sire_operaciones' verificada/creada.")