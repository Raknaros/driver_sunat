# -*- coding: utf-8 -*-
import os
import logging
from dotenv import load_dotenv

# Carga las variables de entorno desde un archivo .env
load_dotenv()

class Config:
    """
    Clase de configuración para almacenar todos los ajustes de la aplicación.
    """
    # --- Clave de Cifrado ---
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    if not ENCRYPTION_KEY:
        raise ValueError("No se ha definido ENCRYPTION_KEY en el archivo .env. Es necesaria para la seguridad de las credenciales.")

    # --- Configuración de la Base de Datos Central (PostgreSQL) ---
    PG_HOST = os.getenv("PG_HOST")
    PG_PORT = os.getenv("PG_PORT", "5432")
    PG_DBNAME = os.getenv("PG_DBNAME")
    PG_USER = os.getenv("PG_USER")
    PG_PASSWORD = os.getenv("PG_PASSWORD")

    # --- Configuración de API SIRE ---
    # Credenciales obtenidas de BD local (otras_credenciales)

    # --- Rutas de Archivos Locales ---
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATABASE_PATH = os.path.join(BASE_DIR, "data", "sunat_data.db")
    DOWNLOAD_PATH = os.path.join(BASE_DIR, "data", "downloads")
    LOG_PATH = os.path.join(BASE_DIR, "logs", "driver_sunat.log")

    # --- URLs del Portal ---
    # URL extraída de tu lógica de Selenium
    SUNAT_PORTAL_URL = "https://www.sunat.gob.pe/sol.html"

    # --- Configuración de Horarios Programados ---
    SCHEDULE_CONFIG = {
        'sync_clients': {'hour': 1, 'minute': 0},  # Diario 1:00 AM
        'check_mailbox': {'hour': 8, 'minute': 0},  # Diario 8:00 AM
        'download_invoices': {'day': 1, 'hour': 2, 'minute': 0},  # Mensual día 1, 2:00 AM
        'request_reports': {'day': 1, 'hour': 3, 'minute': 0},  # Mensual día 1, 3:00 AM
        'download_reports': {'hour': 9, 'minute': 0},  # Diario 9:00 AM
        'sire_reports': {'day': 9, 'hour': 9, 'minute': 0},  # Mensual día 9, 9:00 AM
    }

    # --- Configuración de Logging ---
    LOG_CONFIG = {
        'level': logging.INFO,
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file': LOG_PATH,
        'max_bytes': 10 * 1024 * 1024,  # 10MB
        'backup_count': 5
    }

# Creamos una instancia de la configuración para importarla fácilmente en otros módulos
config = Config()

# Configuración global de logging
def setup_logging():
    """Configura el sistema de logging global."""
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)

    logging.basicConfig(
        level=config.LOG_CONFIG['level'],
        format=config.LOG_CONFIG['format'],
        handlers=[
            logging.FileHandler(config.LOG_PATH),
            logging.StreamHandler()  # También mostrar en consola
        ]
    )

    # Configurar rotating file handler si es necesario
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        config.LOG_PATH,
        maxBytes=config.LOG_CONFIG['max_bytes'],
        backupCount=config.LOG_CONFIG['backup_count']
    )
    file_handler.setFormatter(logging.Formatter(config.LOG_CONFIG['format']))

    # Reemplazar el handler básico con el rotativo
    root_logger = logging.getLogger()
    root_logger.handlers[0] = file_handler