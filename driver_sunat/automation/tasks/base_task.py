# -*- coding: utf-8 -*-
import time
import logging
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from ...config import config
from ...database.operations import update_central_db_observacion

class BaseTask:
    """
    Clase base para todas las tareas de automatización.
    Contiene la lógica de login y logout común a todas las tareas.
    """
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def login(self, contribuyente: dict, max_retries=3):
        """
        Encapsula todo el proceso de login para un contribuyente, incluyendo el manejo de popups.
        Incluye reintentos automáticos y logging detallado.
        Lanza una excepción si el login falla después de todos los reintentos.
        """
        self.logger.info(f"Iniciando proceso de login para RUC: {contribuyente['ruc']}")

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"Intento {attempt + 1} de login para RUC {contribuyente['ruc']}")

                # 1. Navegación y manejo de Popups (lógica de tramites_consultas)
                main_window = self.driver.current_window_handle
                self.driver.get(self.config.SUNAT_PORTAL_URL)
                self.driver.maximize_window()
                self.driver.implicitly_wait(2)

                self.driver.find_element(By.CSS_SELECTOR, "a[href='javascript:tramiteConsulta()']").click()

                time.sleep(2)  # Espera para que aparezcan las ventanas emergentes

                all_windows = self.driver.window_handles
                if len(all_windows) > 1:
                    for window in all_windows:
                        if window != main_window:
                            self.driver.switch_to.window(window)
                            break
                self.driver.maximize_window()

                # 2. Ingreso de credenciales y manejo de diálogos (lógica de login_tramites_consultas)
                time.sleep(1)
                wait = WebDriverWait(self.driver, 10)
                wait.until(EC.presence_of_element_located((By.ID, "txtRuc")))
                self.driver.find_element(By.ID, "txtRuc").send_keys(contribuyente['ruc'])
                self.driver.find_element(By.ID, "txtUsuario").send_keys(contribuyente['user_sol'])
                self.driver.find_element(By.ID, "txtContrasena").send_keys(contribuyente['password_sol'])
                self.driver.find_element(By.ID, "btnAceptar").click()

                # 3. Manejo de diálogos post-login
                wait = WebDriverWait(self.driver, 10)
                wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "ifrVCE")))

                try:
                    # Busca el diálogo de validación de datos de contacto
                    wait.until(EC.element_to_be_clickable((By.ID, "btnFinalizarValidacionDatos")))
                    self.driver.find_element(By.ID, "btnFinalizarValidacionDatos").click()
                    self.logger.info("Diálogo de validación de contacto cerrado.")
                    time.sleep(0.5)
                    self.driver.find_element(By.ID, "btnCerrar").click()
                except (TimeoutException, NoSuchElementException):
                    try:
                        self.driver.find_element(By.ID, "btnCerrar").click()
                        self.logger.info("Mensaje de buzón cerrado.")
                    except (TimeoutException, NoSuchElementException):
                        self.logger.debug("No se encontraron diálogos de validación o buzón.")

                self.driver.switch_to.default_content()
                self.logger.info(f"Login exitoso para RUC: {contribuyente['ruc']}")
                return True

            except Exception as e:
                self.logger.warning(f"Intento {attempt + 1} falló para RUC {contribuyente['ruc']}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)  # Espera incremental
                    self.logger.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Login falló definitivamente para RUC {contribuyente['ruc']}")
                    try:
                        error_message = self.driver.find_element(By.CLASS_NAME, "col-md-12").text
                        if "falla" in error_message.lower():
                            update_central_db_observacion(contribuyente['ruc'], "FALLA AUTENTICACION")
                            self.driver.find_element(By.ID, "btnVolver").click()
                    except Exception:
                        pass
                    raise e

    def logout(self):
        """Maneja el proceso de logout."""
        try:
            self.logger.info("Cerrando sesión...")
            self.driver.switch_to.default_content()
            self.driver.find_element(By.ID, "btnSalir").click()
            # Reset to main page for next login
            self.driver.get(self.config.SUNAT_PORTAL_URL)
            self.logger.info("Logout exitoso.")
        except Exception as e:
            self.logger.warning(f"No se pudo hacer logout. La sesión podría haber expirado: {e}")

    def run(self, *args, **kwargs):
        raise NotImplementedError("El método 'run' debe ser implementado por la subclase.")