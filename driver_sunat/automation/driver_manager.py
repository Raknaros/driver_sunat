# -*- coding: utf-8 -*-
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from ..config import config

def get_webdriver(headless: bool = False):
    """
    Configura y devuelve una instancia de Chrome WebDriver.

    Args:
        headless (bool): Si es True, el navegador se ejecutará en modo sin cabeza (sin interfaz gráfica).

    Returns:
        Una instancia de selenium.webdriver.chrome.webdriver.WebDriver.
    """
    print("Configurando el WebDriver...")
    options = webdriver.ChromeOptions()

    # Asegurarse de que el directorio de descargas exista
    os.makedirs(config.DOWNLOAD_PATH, exist_ok=True)
    print(f"Directorio de descargas: {config.DOWNLOAD_PATH}")

    # Establecer preferencias de Chrome, como la ruta de descarga
    prefs = {
        "download.default_directory": config.DOWNLOAD_PATH,
        "download.prompt_for_download": False, # Desactiva el diálogo de "guardar como"
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    if headless:
        print("Ejecutando en modo headless.")
        options.add_argument("--headless")
        options.add_argument("--window-size=1920,1080") # Especificar tamaño de ventana es buena práctica en headless
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

    # Instala o actualiza el driver de Chrome automáticamente y lo configura
    service = ChromeService(ChromeDriverManager().install())
    
    driver = webdriver.Chrome(service=service, options=options)
    print("WebDriver configurado y listo.")
    return driver
