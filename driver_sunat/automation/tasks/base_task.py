# -*- coding: utf-8 -*-
import time
import logging
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from ...config import config, PortalSunat, PORTAL_SELECTORS
from ...database.operations import update_central_db_observacion, add_observation

class BaseTask:
    """
    Clase base para todas las tareas de automatización.
    Contiene la lógica de login y logout común a todas las tareas.
    """
    portal: PortalSunat = PortalSunat.TRAMITES_Y_CONSULTAS

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        if not isinstance(self.portal, PortalSunat):
            raise TypeError("El atributo 'portal' de la clase debe ser un miembro de PortalSunat Enum.")

    def login(self, contribuyente: dict):
        """
        Ejecuta el proceso de login. Lanza una excepción si cualquier paso falla.
        Maneja únicamente el error de 'Falla de autenticación' como un caso de negocio.
        Devuelve True si el login es exitoso, False si falla la autenticación.
        """
        self.logger.info(f"Iniciando proceso de login para RUC: {contribuyente['ruc']} en portal {self.portal.name}")
        
        main_window = self.driver.current_window_handle

        # 1. Navegación y click en el portal dinámico
        self.driver.get(self.config.SUNAT_PORTAL_URL)
        self.driver.maximize_window()

        portal_selector = PORTAL_SELECTORS[self.portal]
        wait = WebDriverWait(self.driver, 15) # Aumentado a 15s para más tolerancia
        portal_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, portal_selector)))
        portal_button.click()

        time.sleep(2)

        # 2. Cambiar a la nueva ventana de login
        all_windows = self.driver.window_handles
        if len(all_windows) > 1:
            for window in all_windows:
                if window != main_window:
                    self.driver.switch_to.window(window)
                    break
        else:
            # Si no aparece la ventana emergente, es un error irrecuperable para este intento
            raise TimeoutException("No se pudo encontrar la ventana emergente de login.")
        
        self.driver.maximize_window()

        # 3. Ingreso de credenciales
        wait.until(EC.presence_of_element_located((By.ID, "txtRuc")))
        self.driver.find_element(By.ID, "txtRuc").send_keys(contribuyente['ruc'])
        self.driver.find_element(By.ID, "txtUsuario").send_keys(contribuyente['user_sol'])
        self.driver.find_element(By.ID, "txtContrasena").send_keys(contribuyente['password_sol'])
        self.driver.find_element(By.ID, "btnAceptar").click()

        # 4. Verificar si hay error de autenticación (única excepción manejada aquí)
        time.sleep(3)
        try:
            error_header = self.driver.find_element(By.ID, "lblHeader")
            if "Falla en la autenticación" in error_header.text:
                self.logger.warning(f"Detectada falla de autenticación para RUC {contribuyente['ruc']}. No se reintentará.")
                add_observation(contribuyente['ruc'], "Falla en la autenticación", "DETERMINANTE", "PENDIENTE")
                return False # Falla de negocio, no técnica.
        except NoSuchElementException:
            pass # No hay error de autenticación, el login parece exitoso.

        # 5. Manejo de diálogos post-login
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "ifrVCE")))

        try:
            wait.until(EC.element_to_be_clickable((By.ID, "btnFinalizarValidacionDatos"))).click()
            self.logger.info("Diálogo de validación de contacto cerrado.")
            time.sleep(0.5)
            # El botón cerrar puede o no estar, usar un try-except
            try:
                self.driver.find_element(By.ID, "btnCerrar").click()
            except NoSuchElementException:
                pass
        except (TimeoutException, NoSuchElementException):
            try:
                self.driver.find_element(By.ID, "btnCerrar").click()
                self.logger.info("Mensaje de buzón cerrado.")
            except (TimeoutException, NoSuchElementException):
                self.logger.debug("No se encontraron diálogos de validación o buzón.")

        self.driver.switch_to.default_content()
        self.logger.info(f"Login exitoso para RUC: {contribuyente['ruc']}")
        return True

    def logout(self):
        """Maneja el proceso de logout."""
        try:
            self.logger.info("Cerrando sesión...")
            self.driver.switch_to.default_content()
            self.driver.find_element(By.ID, "btnSalir").click()
            self.logger.info("Logout exitoso.")
        except Exception as e:
            self.logger.warning(f"No se pudo hacer logout. La sesión podría haber expirado: {e}")

    def run(self, *args, **kwargs):
        raise NotImplementedError("El método 'run' debe ser implementado por la subclase.")