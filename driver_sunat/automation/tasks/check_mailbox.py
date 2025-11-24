# -*- coding: utf-8 -*-
import time
from datetime import datetime
from .base_task import BaseTask
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ...database import operations as db

def parse_leido(value) -> bool:
    """Convierte el valor de 'leido' de string a booleano."""
    if value is None:
        return False
    return str(value) == '1'

class CheckMailboxTask(BaseTask):
    """
    Tarea específica para revisar el buzón electrónico de SUNAT.
    """
    def __init__(self, driver: WebDriver):
        super().__init__(driver)

    def run(self, contribuyente: dict):
        """
        Ejecuta el flujo completo de revisión de buzón para un contribuyente.
        """
        try:
            login_success = self.login(contribuyente)
            if not login_success:
                return  # El login falló, la razón ya fue logueada.

            self.logger.info(f"Accediendo al buzón para {contribuyente['ruc']}")
            self.driver.find_element(By.ID, "aOpcionBuzon").click()

            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "iframeApplication")))

            # Lógica de sincronización de mensajes
            self._sync_messages(contribuyente['ruc'])

            # Agregar observación local de éxito
            db.add_observation(contribuyente['ruc'], "Buzon Revisado", "LOCAL", "PENDIENTE")

            # Sync buzon to central
            db.sync_buzon_to_central(contribuyente['ruc'])

            self.logout()

        except Exception as e:
            self.logger.error(f"No se pudo completar la tarea de revisión de buzón para {contribuyente['ruc']}: {e}")

    def _sync_messages(self, ruc: str):
        """Compara los mensajes de la web con la BD local y los sincroniza."""
        self.logger.debug("Sincronizando mensajes del buzón")
        today_str = datetime.now().isoformat()

        # 1. Obtener estado actual de la BD local
        local_messages = db.get_messages_by_ruc_as_dict(ruc)

        # 2. Obtener mensajes de la página web
        lista_mensajes_web = self.driver.find_element(By.ID, "listaMensajes")
        mensajes_web = lista_mensajes_web.find_elements(By.TAG_NAME, "li")
        self.logger.info(f"Se encontraron {len(mensajes_web)} mensajes en la web para RUC {ruc}")

        # 3. Comparar y sincronizar
        for msg_element in mensajes_web:
            msg_id_attr = msg_element.get_attribute("id")
            msg_id = int(msg_id_attr) if msg_id_attr else 0
            leido_element = msg_element.find_element(By.ID, "idLeido")
            leido_value = leido_element.get_attribute("value") if leido_element else "false"
            web_leido = parse_leido(leido_value)

            if msg_id not in local_messages:
                # Mensaje nuevo, lo guardamos
                new_msg_data = {
                    'id': msg_id,
                    'ruc': ruc,
                    'asunto': msg_element.find_element(By.CSS_SELECTOR, ".linkMensaje.text-muted").text,
                    'fecha_publicacion': msg_element.find_element(By.CSS_SELECTOR, ".text-muted.fecPublica").text,
                    'leido': web_leido,
                    'fecha_revision': today_str
                }
                db.add_message(new_msg_data)
                self.logger.info(f"Nuevo mensaje guardado (ID: {msg_id}) para RUC {ruc}")
            else:
                # Mensaje ya existe, chequear si cambió el estado de leído
                local_leido = local_messages[msg_id]['leido']
                if web_leido and not local_leido:
                    # El mensaje fue leído en la web, actualizamos nuestra BD
                    db.update_message_status(msg_id, True, today_str)
                    self.logger.info(f"Estado del mensaje actualizado a LEIDO (ID: {msg_id}) para RUC {ruc}")
