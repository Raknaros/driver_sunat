# -*- coding: utf-8 -*-
import time
from datetime import datetime
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from .base_task import BaseTask
from ...database import operations as db

class RequestReportTask(BaseTask):
    """
    Tarea para solicitar reportes T-Registro en SUNAT.
    Navega por el menú y solicita un tipo específico de reporte.
    """
    def __init__(self, driver: WebDriver):
        super().__init__(driver)

    def run(self, contribuyente: dict, tipo_reporte: str):
        """
        Ejecuta la solicitud de reporte para un contribuyente.

        Args:
            contribuyente (dict): Datos del contribuyente
            tipo_reporte (str): Tipo de reporte a solicitar (ej: "2", "3", "4")
        """
        self.logger.info(f"Solicitando reporte tipo {tipo_reporte} para RUC {contribuyente['ruc']}")

        try:
            # Login
            login_success = self.login(contribuyente)
            if not login_success:
                self.logger.error("Login falló, cancelando solicitud de reporte")
                return

            # Navegar al menú de reportes
            self._navigate_to_reports_section()

            # Solicitar el reporte
            self._request_report(tipo_reporte, contribuyente['ruc'])

            # Logout
            self.logout()

            self.logger.info(f"Solicitud de reporte tipo {tipo_reporte} completada para RUC {contribuyente['ruc']}")

        except Exception as e:
            self.logger.error(f"Error solicitando reporte para RUC {contribuyente['ruc']}: {e}")
            raise

    def _navigate_to_reports_section(self):
        """Navega al menú de Consultar y Reportes usando IDs específicos."""
        self.logger.debug("Navegando a sección de reportes")

        try:
            wait = WebDriverWait(self.driver, 15)

            # Click en SECCION EMPRESAS
            empresas_section = wait.until(EC.element_to_be_clickable((By.ID, "divOpcionServicio2")))
            empresas_section.click()
            time.sleep(1)

            # Click en SECCION MI RUC Y OTROS REGISTROS
            ruc_section = wait.until(EC.element_to_be_clickable((By.ID, "nivel1_10")))
            ruc_section.click()
            time.sleep(1)

            # Click en SECCION T-REGISTRO
            tregistro_section = wait.until(EC.element_to_be_clickable((By.ID, "nivel2_10_5")))
            tregistro_section.click()
            time.sleep(1)

            # Click en SECCION REGISTRO TRABAJADOR
            trabajador_section = wait.until(EC.element_to_be_clickable((By.ID, "nivel3_10_5_3")))
            trabajador_section.click()
            time.sleep(1)

            # Click en SECCION CONSULTAR Y REPORTES
            reportes_section = wait.until(EC.element_to_be_clickable((By.ID, "nivel4_10_5_3_1_3")))
            reportes_section.click()
            time.sleep(2)

            # Cambiar al iframe
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "iframeApplication")))

            # Verificar si hay mensaje de error (contribuyente no registrado como empleador)
            try:
                error_div = self.driver.find_element(By.CSS_SELECTOR, "div.msg")
                error_msg = self.driver.find_element(By.CSS_SELECTOR, "p.error").text
                if "El contribuyente no ha sido registrado como Empleador" in error_msg:
                    # Registrar observación
                    db.add_observation(ruc, f"Error al solicitar reporte: {error_msg}", "PENDIENTE")
                    self.logger.warning(f"Contribuyente {ruc} no registrado como empleador. Observación registrada.")
                    raise Exception(f"Contribuyente no registrado como empleador: {error_msg}")
            except NoSuchElementException:
                # No hay error, continuar
                pass

            # Click en DESCARGA DE INFORMACION DE PRESTADOR DE SERVICIOS
            descarga_link = wait.until(EC.element_to_be_clickable((By.ID, "adescarga")))
            descarga_link.click()
            time.sleep(2)

            self.logger.debug("Navegación a sección de reportes completada")

        except Exception as e:
            self.logger.error(f"Error en navegación a reportes: {e}")
            raise

    def _request_report(self, tipo_reporte: str, ruc: str):
        """Solicita un reporte específico con análisis inteligente de tabla."""
        self.logger.debug(f"Solicitando reporte tipo {tipo_reporte}")

        try:
            wait = WebDriverWait(self.driver, 10)

            # PRIMERO: Analizar tabla existente para ver si ya hay solicitudes en proceso
            tickets_antes = self._analyze_existing_reports()
            self.logger.info(f"Tickets existentes antes de solicitud: {len(tickets_antes)}")

            # Seleccionar tipo de reporte en el dropdown
            dropdown_element = wait.until(EC.element_to_be_clickable((By.ID, "selTipDes")))
            select = Select(dropdown_element)
            select.select_by_value(tipo_reporte)
            time.sleep(1)

            # Click en BOTON REGISTRAR PEDIDO
            registrar_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnRegistrar")))
            registrar_btn.click()
            time.sleep(1)

            # Confirmar en VENTANA MODAL DE CONFIRMACION
            aceptar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.btn-success.btn-ok")))
            aceptar_btn.click()
            time.sleep(3)

            # Re-switch al iframe por si se recargó
            self.driver.switch_to.default_content()
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "iframeApplication")))

            # SEGUNDO: Analizar tabla después de la solicitud para encontrar el nuevo ticket
            tickets_despues = self._analyze_existing_reports()
            nuevo_ticket = self._find_new_ticket(tickets_antes, tickets_despues)
            self.logger.info(f"Tickets antes: {tickets_antes}, después: {tickets_despues}, nuevo: {nuevo_ticket}")

            if nuevo_ticket:
                self.logger.info(f"Nuevo ticket generado: {nuevo_ticket}")

                # Registrar en BD local con el ticket
                report_data = {
                    'ruc': ruc,
                    'tipo_reporte': tipo_reporte,
                    'ticket': nuevo_ticket,
                    'estado': 'SOLICITADO',
                    'fecha_solicitud': datetime.now().isoformat()
                }

                report_id = db.add_report_request(report_data)
                self.logger.info(f"Reporte solicitado registrado en BD con ID {report_id}, Ticket {nuevo_ticket}")
                return report_id
            else:
                self.logger.warning("No se pudo identificar el ticket generado")
                # Registrar sin ticket por ahora
                report_data = {
                    'ruc': ruc,
                    'tipo_reporte': tipo_reporte,
                    'ticket': None,
                    'estado': 'SOLICITADO',
                    'fecha_solicitud': datetime.now().isoformat()
                }
                report_id = db.add_report_request(report_data)
                self.logger.info(f"Reporte solicitado registrado en BD con ID {report_id}, sin ticket")
                return report_id

        except Exception as e:
            self.logger.error(f"Error solicitando reporte: {e}")
            raise

    def _analyze_existing_reports(self):
        """Analiza la tabla de reportes existentes y retorna lista de tickets."""
        try:
            wait = WebDriverWait(self.driver, 5)  # Timeout corto

            # Buscar la tabla table-lista-masivo
            table = wait.until(EC.presence_of_element_located((By.ID, "table-lista-masivo")))
            time.sleep(1)

            # Obtener todas las filas del cuerpo de la tabla
            filas = table.find_elements(By.CSS_SELECTOR, "tbody tr")
            tickets = []

            for fila in filas:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 1:  # Al menos la columna de ticket
                    ticket = celdas[0].text.strip()
                    # Filtrar solo tickets válidos (numéricos, excluyendo mensajes como "El prestador no ha solicitado descargas.")
                    if ticket and ticket.isdigit():
                        tickets.append(ticket)

            self.logger.debug(f"Analizados {len(tickets)} tickets existentes")
            return tickets

        except (TimeoutException, NoSuchElementException):
            self.logger.debug("Tabla de reportes no encontrada o vacía")
            return []
        except Exception as e:
            self.logger.error(f"Error analizando tabla de reportes: {e}")
            return []

    def _find_new_ticket(self, tickets_antes, tickets_despues):
        """Encuentra el ticket nuevo comparando listas antes y después."""
        nuevos_tickets = set(tickets_despues) - set(tickets_antes)
        if nuevos_tickets:
            return list(nuevos_tickets)[0]  # Retorna el primer ticket nuevo
        return None