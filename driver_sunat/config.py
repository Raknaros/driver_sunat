# -*- coding: utf-8 -*-
import os
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

    # --- Rutas de Archivos Locales ---
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATABASE_PATH = os.path.join(BASE_DIR, "data", "sunat_data.db")
    DOWNLOAD_PATH = os.path.join(BASE_DIR, "data", "downloads")
    
    # --- URLs del Portal ---
    # URL extraída de tu lógica de Selenium
    SUNAT_PORTAL_URL = "https://www.sunat.gob.pe/sol.html"

# Creamos una instancia de la configuración para importarla fácilmente en otros módulos
config = Config()