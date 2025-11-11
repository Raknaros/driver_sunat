# -*- coding: utf-8 -*-
"""
Script de prueba para capturar información del buzón de SUNAT usando Selenium
e imprimir en consola en formato ordenado como previa subida a la base de datos.
"""

from datetime import datetime
from driver_sunat.automation.driver_manager import get_webdriver
from driver_sunat.automation.tasks.base_task import BaseTask
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def parse_leido(value) -> bool:
    """Convierte el valor de 'leido' de string a booleano."""
    if value is None:
        return False
    return str(value).lower() == 'true'

class TestMailboxTask(BaseTask):
    """
    Tarea de prueba para revisar el buzón electrónico de SUNAT e imprimir datos.
    Basada en CheckMailboxTask pero sin guardar en BD.
    """
    def __init__(self, driver: WebDriver):
        super().__init__(driver)

    def run(self, contribuyente: dict):
        """
        Ejecuta el flujo completo de revisión de buzón para un contribuyente e imprime los datos.
        """
        try:
            login_success = self.login(contribuyente)
            if not login_success:
                return  # El login falló, la razón ya fue logueada.

            print(f"Accediendo al buzón para {contribuyente['ruc']}...")
            self.driver.find_element(By.ID, "aOpcionBuzon").click()

            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "iframeApplication")))

            # Extraer y mostrar mensajes
            self._extract_and_print_messages(contribuyente['ruc'])

            self.logout()

        except Exception as e:
            print(f"No se pudo completar la tarea de revisión de buzón para {contribuyente['ruc']}. Error: {e}")

    def _extract_and_print_messages(self, ruc: str):
        """Extrae los mensajes de la web e imprime en formato de BD."""
        print("Extrayendo mensajes del buzón...")
        today_str = datetime.now().isoformat()

        # Obtener mensajes de la página web
        lista_mensajes_web = self.driver.find_element(By.ID, "listaMensajes")
        mensajes_web = lista_mensajes_web.find_elements(By.TAG_NAME, "li")
        print(f"Se encontraron {len(mensajes_web)} mensajes en la web.")

        messages_for_db = []
        for msg_element in mensajes_web:
            msg_id_attr = msg_element.get_attribute("id")
            msg_id = int(msg_id_attr) if msg_id_attr else 0

            leido_element = msg_element.find_element(By.ID, "idLeido")
            leido_value = leido_element.get_attribute("value") if leido_element else "false"
            web_leido = parse_leido(leido_value)

            # Formato como para subir a BD
            new_msg_data = {
                'id': msg_id,
                'ruc': ruc,
                'asunto': msg_element.find_element(By.CSS_SELECTOR, ".linkMensaje.text-muted").text,
                'fecha_publicacion': msg_element.find_element(By.CSS_SELECTOR, ".text-muted.fecPublica").text,
                'leido': web_leido,
                'fecha_revision': today_str
            }
            messages_for_db.append(new_msg_data)

        # Imprimir en consola
        print('\n=== MENSAJES DEL BUZÓN (FORMATO PARA BD) ===')
        for msg in messages_for_db:
            print(f"Mensaje: {msg}")
        print(f'\nTotal de mensajes: {len(messages_for_db)}')

if __name__ == '__main__':
    # Credenciales de ejemplo (reemplaza con las tuyas)
    CONTRIBUYENTE = {
        'ruc': '20606283858',
        'user_sol': 'TONERTAT',
        'password_sol': 'rcavinsio'
    }

    driver = get_webdriver(headless=False)  # Cambia a True para headless
    try:
        task = TestMailboxTask(driver)
        task.run(CONTRIBUYENTE)
    finally:
        driver.quit()