# -*- coding: utf-8 -*-
import time
import os
from datetime import datetime
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from .base_task import BaseTask

class DownloadInvoicesTask(BaseTask):
    """
    Tarea para descargar facturas desde el portal de SUNAT.
    Implementa la lógica completa de navegación, búsqueda y descarga.
    """
    def __init__(self, driver: WebDriver):
        super().__init__(driver)

    def run(self, contribuyente: dict, start_date: str, end_date: str):
        """
        Ejecuta la lógica completa para descargar facturas de un contribuyente en un rango de fechas.

        Args:
            contribuyente (dict): Datos del contribuyente (ruc, user_sol, password_sol)
            start_date (str): Fecha de inicio (formato DD/MM/YYYY)
            end_date (str): Fecha de fin (formato DD/MM/YYYY)
        """
        self.logger.info(f"Iniciando descarga de facturas para RUC {contribuyente['ruc']} ({start_date} - {end_date})")

        try:
            # Login
            login_success = self.login(contribuyente)
            if not login_success:
                self.logger.error("Login falló, cancelando descarga")
                return

            # Navegar a sección de consultas de facturas
            self._navigate_to_invoice_section()

            # Buscar y descargar facturas
            self._search_and_download_invoices(start_date, end_date, contribuyente['ruc'])

            # Logout
            self.logout()

            self.logger.info("Descarga de facturas completada exitosamente")

        except Exception as e:
            self.logger.error(f"Error en descarga de facturas para RUC {contribuyente['ruc']}: {e}")
            raise

    def _navigate_to_invoice_section(self):
        """Navega a la sección de consultas de facturas electrónicas."""
        self.logger.debug("Navegando a sección de consultas de facturas")

        try:
            # Hacer clic en "Consultas" o similar
            wait = WebDriverWait(self.driver, 10)
            consultas_link = wait.until(EC.element_to_be_clickable((By.ID, "aOpcionConsultas")))
            consultas_link.click()

            # Cambiar al iframe de consultas
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "iframeApplication")))

            # Hacer clic en "Consulta de Facturas Electrónicas" (ajustar selector según necesidad)
            # Nota: Los selectores exactos pueden variar según cambios en SUNAT
            facturas_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Facturas')]")))
            facturas_link.click()

            self.logger.debug("Navegación a sección de facturas completada")

        except Exception as e:
            self.logger.error(f"Error navegando a sección de facturas: {e}")
            raise

    def _search_and_download_invoices(self, start_date: str, end_date: str, ruc: str):
        """Busca facturas en el rango de fechas y las descarga."""
        self.logger.debug(f"Buscando facturas entre {start_date} y {end_date}")

        try:
            wait = WebDriverWait(self.driver, 10)

            # Ingresar fechas
            fecha_desde = wait.until(EC.element_to_be_clickable((By.ID, "txtFechaEmisionDesde")))
            fecha_desde.clear()
            fecha_desde.send_keys(start_date)

            fecha_hasta = self.driver.find_element(By.ID, "txtFechaEmisionHasta")
            fecha_hasta.clear()
            fecha_hasta.send_keys(end_date)

            # Hacer clic en buscar
            buscar_btn = self.driver.find_element(By.ID, "btnBuscar")
            buscar_btn.click()

            # Esperar resultados
            time.sleep(3)

            # Verificar si hay resultados
            try:
                no_results = self.driver.find_element(By.XPATH, "//td[contains(text(),'No se encontraron')]")
                self.logger.info("No se encontraron facturas en el rango especificado")
                return
            except NoSuchElementException:
                pass  # Hay resultados

            # Seleccionar todas las facturas (checkbox general)
            try:
                select_all = self.driver.find_element(By.ID, "chkSeleccionarTodo")
                select_all.click()
                time.sleep(1)
            except NoSuchElementException:
                self.logger.warning("No se encontró checkbox para seleccionar todo")

            # Hacer clic en descargar
            download_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnDescargar")))
            download_btn.click()

            # Esperar a que se complete la descarga
            self._wait_for_download(ruc)

        except Exception as e:
            self.logger.error(f"Error en búsqueda y descarga: {e}")
            raise

    def _wait_for_download(self, ruc: str, timeout=300):
        """Espera a que se complete la descarga verificando el directorio de descargas."""
        self.logger.debug("Esperando completación de descarga")

        start_time = time.time()
        expected_files = 0

        while time.time() - start_time < timeout:
            # Verificar archivos .zip o .xml en el directorio de descargas
            files = os.listdir(self.config.DOWNLOAD_PATH)
            current_files = [f for f in files if f.endswith(('.zip', '.xml')) and ruc in f]

            if len(current_files) > expected_files:
                expected_files = len(current_files)
                self.logger.info(f"Descargados {expected_files} archivos hasta ahora")

            # Verificar si hay archivos .crdownload (Chrome downloading)
            downloading = [f for f in files if f.endswith('.crdownload')]
            if not downloading and expected_files > 0:
                self.logger.info(f"Descarga completada: {expected_files} archivos")
                return

            time.sleep(2)

        self.logger.warning("Timeout esperando descarga")
