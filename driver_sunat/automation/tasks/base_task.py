# -*- coding: utf-8 -*-
import time
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

    def login(self, contribuyente: dict):
        """
        Encapsula todo el proceso de login para un contribuyente, incluyendo el manejo de popups.
        Lanza una excepción si el login falla.
        """
        print(f"--- Iniciando proceso de login para RUC: {contribuyente['ruc']} ---")
        
        # 1. Navegación y manejo de Popups (lógica de tramites_consultas)
        main_window = self.driver.current_window_handle
        self.driver.get(self.config.SUNAT_PORTAL_URL)
        self.driver.maximize_window()
        self.driver.implicitly_wait(2)
        
        self.driver.find_element(By.XPATH, "/html/body/section[1]/div/div/section[2]/div[2]/div/a/span").click()
        
        time.sleep(2) # Espera para que aparezcan las ventanas emergentes
        
        all_windows = self.driver.window_handles
        if len(all_windows) > 1:
            for window in all_windows:
                if window != main_window:
                    self.driver.switch_to.window(window)
                    # Si hay más de un popup, este código podría necesitar ajustes,
                    # pero usualmente el último popup es el de login.
                    break
        self.driver.maximize_window()

        # 2. Ingreso de credenciales y manejo de diálogos (lógica de login_tramites_consultas)
        time.sleep(1)
        try:
            self.driver.find_element(By.ID, "txtRuc").send_keys(contribuyente['ruc'])
            self.driver.find_element(By.ID, "txtUsuario").send_keys(contribuyente['user_sol'])
            self.driver.find_element(By.ID, "txtContrasena").send_keys(contribuyente['password_sol'])
            self.driver.find_element(By.ID, "btnAceptar").click()

            # 3. Manejo de diálogos post-login
            wait = WebDriverWait(self.driver, 6)
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "ifrVCE")))

            try:
                # Busca el diálogo de validación de datos de contacto
                wait.until(EC.element_to_be_clickable((By.ID, "btnFinalizarValidacionDatos")))
                self.driver.find_element(By.ID, "btnFinalizarValidacionDatos").click()
                print("INFO: Diálogo de validación de contacto cerrado.")
                # A veces aparece otro botón de cerrar después
                time.sleep(0.5)
                self.driver.find_element(By.ID, "btnCerrar").click()
            except (TimeoutException, NoSuchElementException):
                # Si no está el diálogo de validación, busca el de mensaje de buzón
                try:
                    self.driver.find_element(By.ID, "btnCerrar").click()
                    print("INFO: Mensaje de buzón cerrado.")
                except (TimeoutException, NoSuchElementException):
                    print("INFO: No se encontraron diálogos de validación o buzón.")
            
            self.driver.switch_to.default_content()
            print(f"--- Login exitoso para RUC: {contribuyente['ruc']} ---")
            return True # Indica que el login fue exitoso

        except Exception as e:
            print(f"ERROR: Fallo durante el proceso de login para RUC {contribuyente['ruc']}.")
            try:
                error_message = self.driver.find_element(By.CLASS_NAME, "col-md-12").text
                if "falla" in error_message.lower():
                    update_central_db_observacion(contribuyente['ruc'], "FALLA AUTENTICACION")
                    self.driver.find_element(By.ID, "btnVolver").click()
            except Exception:
                pass # Si no se puede registrar la falla, simplemente continuamos
            raise e # Relanzamos la excepción para que el orquestador sepa que esta tarea falló

    def logout(self):
        """Maneja el proceso de logout."""
        try:
            print("Cerrando sesión...")
            self.driver.switch_to.default_content()
            self.driver.find_element(By.ID, "btnSalir").click()
            print("Logout exitoso.")
        except Exception:
            print("ADVERTENCIA: No se pudo hacer logout. La sesión podría haber expirado.")

    def run(self, *args, **kwargs):
        raise NotImplementedError("El método 'run' debe ser implementado por la subclase.")