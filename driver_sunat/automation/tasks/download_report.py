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
from ...database import operations as db

class DownloadReportTask(BaseTask):
    """
    Tarea para descargar reportes T-Registro listos en SUNAT.
    Revisa la tabla de pedidos y descarga los reportes disponibles.
    """
    def __init__(self, driver: WebDriver):
        super().__init__(driver)

    def run(self, contribuyente: dict, specific_ticket=None):
        """
        Ejecuta la descarga de reportes listos para un contribuyente.
        Si se especifica un ticket, busca solo ese reporte.
        """
        self.logger.info(f"Verificando reportes listos para descarga - RUC {contribuyente['ruc']}")

        try:
            # Obtener reportes pendientes de este RUC
            if specific_ticket:
                # Buscar reporte específico por ticket
                pending_reports = db.get_pending_reports(contribuyente['ruc'])
                pending_reports = [r for r in pending_reports if r['ticket'] == specific_ticket]
            else:
                pending_reports = db.get_pending_reports(contribuyente['ruc'])

            if not pending_reports:
                self.logger.info(f"No hay reportes pendientes para RUC {contribuyente['ruc']}")
                return

            self.logger.info(f"Encontrados {len(pending_reports)} reportes pendientes")

            # Login
            login_success = self.login(contribuyente)
            if not login_success:
                self.logger.error("Login falló, cancelando descarga de reportes")
                return

            # Navegar a la sección de reportes
            self._navigate_to_reports_section()

            # Procesar cada reporte pendiente
            for report in pending_reports:
                self._download_report_if_ready(report)

            # Logout
            self.logout()

            self.logger.info("Verificación de descargas completada")

        except Exception as e:
            self.logger.error(f"Error descargando reportes para RUC {contribuyente['ruc']}: {e}")
            raise

    def _navigate_to_reports_section(self):
        """Navega al menú de Consultar y Reportes (igual que RequestReportTask)."""
        self.logger.debug("Navegando a sección de reportes")

        try:
            wait = WebDriverWait(self.driver, 15)

            # Click en SECCION EMPRESAS
            empresas_section = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/div[2]/div[1]/div/div[2]")))
            empresas_section.click()
            time.sleep(1)

            # Click en SECCION MI RUC Y OTROS REGISTROS
            ruc_section = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/div[2]/div[2]/div/div[1]/div/div/ul/li[3]/span[2]")))
            ruc_section.click()
            time.sleep(1)

            # Click en SECCION T-REGISTRO
            tregistro_section = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/div[2]/div[2]/div/div[1]/div/div/ul/li[4]/li[7]")))
            tregistro_section.click()
            time.sleep(1)

            # Click en SECCION REGISTRO TRABAJADOR
            trabajador_section = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/div[2]/div[2]/div/div[1]/div/div/ul/li[4]/li[8]/li[5]/span[2]")))
            trabajador_section.click()
            time.sleep(1)

            # Click en SECCION CONSULTAR Y REPORTES
            reportes_section = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/div[2]/div[2]/div/div[1]/div/div/ul/li[4]/li[8]/li[6]/li[3]/span[1]")))
            reportes_section.click()
            time.sleep(2)

            self.logger.debug("Navegación a sección de reportes completada")

        except Exception as e:
            self.logger.error(f"Error en navegación a reportes: {e}")
            raise

    def _download_report_if_ready(self, report):
        """Verifica si un reporte está listo y lo descarga usando ticket específico."""
        try:
            ticket_buscado = report.get('ticket')
            if not ticket_buscado:
                self.logger.warning(f"Reporte ID {report['id']} no tiene ticket asignado")
                return False

            self.logger.debug(f"Verificando reporte ID {report['id']} con ticket {ticket_buscado}")

            wait = WebDriverWait(self.driver, 10)

            # Buscar la tabla de pedidos
            table = wait.until(EC.presence_of_element_located((By.ID, "table-lista-masivo")))
            time.sleep(2)

            # Obtener todas las filas del cuerpo de la tabla
            filas = table.find_elements(By.CSS_SELECTOR, "tbody tr")

            self.logger.debug(f"Se encontraron {len(filas)} filas en la tabla")

            for fila in filas:
                celdas = fila.find_elements(By.TAG_NAME, "td")

                if len(celdas) >= 4:  # Asegurarse de que la fila tenga datos
                    ticket = celdas[0].text.strip()
                    tipo_descarga = celdas[1].text.strip()
                    estado = celdas[2].text.strip()

                    # Buscar el enlace de descarga dentro de la 4ta celda
                    try:
                        enlace_elemento = celdas[3].find_element(By.TAG_NAME, "a")
                        nombre_archivo = enlace_elemento.text.strip()
                        url_descarga = enlace_elemento.get_attribute("href")
                    except:
                        nombre_archivo = "No disponible"
                        url_descarga = None
                        enlace_elemento = None

                    # Verificar si este es el ticket que buscamos
                    if ticket_buscado and ticket == str(ticket_buscado):
                        if estado == "Terminado" and enlace_elemento:
                            self.logger.info(f"✅ Ticket {ticket_buscado} encontrado y terminado. Iniciando descarga...")

                            # Click en el enlace de descarga
                            enlace_elemento.click()
                            time.sleep(2)

                            # Esperar a que se complete la descarga
                            self._wait_for_download()

                            # Actualizar estado en BD
                            db.update_report_status(
                                report['id'],
                                'DESCARGADO',
                                datetime.now().isoformat()
                            )

                            self.logger.info(f"Reporte ID {report['id']} (ticket {ticket_buscado}) descargado exitosamente")
                            return True
                        else:
                            self.logger.info(f"⚠️ El ticket {ticket_buscado} fue encontrado pero su estado es '{estado}'")
                            return False

            self.logger.debug(f"Ticket {ticket_buscado} no encontrado en la tabla")
            return False

        except Exception as e:
            self.logger.error(f"Error verificando reporte ID {report['id']}: {e}")
            return False

    def _wait_for_download(self, timeout=60):
        """Espera a que se complete la descarga."""
        self.logger.debug("Esperando completación de descarga")

        start_time = time.time()
        initial_files = len(os.listdir(self.config.DOWNLOAD_PATH))

        while time.time() - start_time < timeout:
            current_files = len(os.listdir(self.config.DOWNLOAD_PATH))
            if current_files > initial_files:
                self.logger.debug("Descarga completada")
                return
            time.sleep(1)

        self.logger.warning("Timeout esperando descarga de reporte")