# -*- coding: utf-8 -*-
import requests
from datetime import datetime, timedelta
from ...config import config
from ...database import operations as db

class SireClient:
    """
    Cliente para interactuar con la API SIRE de SUNAT.
    Maneja autenticación, tokens y requests con reintentos.
    """

    def __init__(self, logger, ruc):
        self.logger = logger
        self.ruc = ruc
        self.token = None
        self.token_expires_at = None
        # Obtener credenciales de BD
        creds = db.get_sire_credentials(ruc)
        if not creds:
            raise ValueError(f"No se encontraron credenciales SIRE válidas para RUC {ruc}")
        self.client_id = creds['client_id']
        self.client_secret = creds['client_secret']
        self.user_sol = creds['user_sol']

    def _get_token(self, ruc, sol_user, sol_pass):
        """
        Obtiene un Bearer Token usando OAuth2 password grant, con cache en BD.
        Registra errores de autenticación en observaciones locales.
        """
        # Primero intentar obtener de BD
        cached_token = db.get_valid_sire_token(ruc)
        if cached_token:
            self.token = cached_token
            self.token_expires_at = datetime.now() + timedelta(hours=1)  # Estimar
            self.logger.info("Token SIRE obtenido de cache")
            return self.token

        # Obtener nuevo token
        token_url = f"https://api-seguridad.sunat.gob.pe/v1/clientessol/{self.client_id}/oauth2/token/"
        username = f"{ruc}{sol_user}"

        payload = {
            'grant_type': 'password',
            'scope': 'https://api-cpe.sunat.gob.pe',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'username': username,
            'password': sol_pass
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            response = requests.post(token_url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            self.token = data.get('access_token')
            expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
            # Guardar en BD
            db.save_sire_token(ruc, self.token, expires_at)
            self.token_expires_at = datetime.now() + timedelta(hours=1)
            self.logger.info("Token de acceso SIRE obtenido y guardado")
            return self.token
        except requests.exceptions.HTTPError as e:
            error_msg = f"Error token SIRE HTTP {e.response.status_code}: {e.response.text}"
            self.logger.error(error_msg)
            # Registrar en observaciones locales
            from ...database.operations import add_observation
            add_observation(ruc, error_msg, "LOCAL")
            raise
        except requests.exceptions.RequestException as e:
            error_msg = f"Error obteniendo token SIRE: {e}"
            self.logger.error(error_msg)
            # Registrar en observaciones locales
            from ...database.operations import add_observation
            add_observation(ruc, error_msg, "LOCAL")
            raise

    def _make_request(self, method, url, params=None, retries=3):
        """
        Realiza una request HTTP con reintentos y manejo de token.
        """
        headers = {'Authorization': f'Bearer {self.token}'}
        for attempt in range(retries):
            try:
                response = requests.request(method, url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:  # Token expirado
                    self.logger.warning("Token expirado, intentando refrescar")
                    self.token = None  # Forzar refresh
                    continue
                self.logger.error(f"Error HTTP en request SIRE (intento {attempt+1}): {e}")
                if attempt == retries - 1:
                    raise
            except Exception as e:
                self.logger.error(f"Error en request SIRE (intento {attempt+1}): {e}")
                if attempt == retries - 1:
                    raise
        return None

    def request_proposal(self, ruc, sol_user, sol_pass, tipo, periodo):
        """
        Solicita una propuesta de descarga para Ventas o Compras.
        """
        token = self._get_token(ruc, sol_user, sol_pass)
        if tipo == 'ventas':
            libro = 'rvie'
            url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/propuesta/web/propuesta/{periodo}/exportapropuesta"
            params = {'codTipoArchivo': '0'}
        elif tipo == 'compras':
            libro = 'rce'
            url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/propuesta/web/propuesta/{periodo}/exportacioncomprobantepropuesta"
            params = {'codTipoArchivo': '0', 'codOrigenEnvio': '2'}
        else:
            raise ValueError(f"Tipo no válido: {tipo}")

        data = self._make_request('GET', url, params)
        if data and 'numTicket' in data:
            self.logger.info(f"Propuesta SIRE {tipo} solicitada, ticket: {data['numTicket']}")
            return data['numTicket']
        else:
            self.logger.error("No se recibió numTicket en respuesta de propuesta")
            return None

    def query_status(self, ruc, sol_user, sol_pass, tipo, periodo, ticket, page=1, per_page=20):
        """
        Consulta el estado de un ticket.
        """
        token = self._get_token(ruc, sol_user, sol_pass)
        libro = 'rvierce'  # Ambos usan rvierce para gestión
        url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/gestionprocesosmasivos/web/masivo/consultaestadotickets"
        params = {
            'perIni': periodo,
            'perFin': periodo,
            'page': page,
            'perPage': per_page,
            'numTicket': ticket
        }

        data = self._make_request('GET', url, params)
        if data:
            self.logger.info(f"Estado de ticket {ticket} consultado")
            return data
        return None

    def download_file(self, ruc, sol_user, sol_pass, tipo, periodo, ticket, nom_archivo, cod_tipo_archivo, cod_libro, cod_proceso='10'):
        """
        Descarga un archivo de reporte.
        """
        token = self._get_token(ruc, sol_user, sol_pass)
        libro = 'rvierce'  # Ambos usan rvierce para descarga
        url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/gestionprocesosmasivos/web/masivo/archivoreporte"
        params = {
            'nomArchivoReporte': nom_archivo,
            'codTipoArchivoReporte': cod_tipo_archivo,
            'codLibro': cod_libro,
            'perTributario': periodo,
            'codProceso': cod_proceso,
            'numTicket': ticket
        }

        headers = {'Authorization': f'Bearer {self.token}'}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
            response.raise_for_status()

            file_path = f"{config.DOWNLOAD_PATH}/{nom_archivo}"
            with open(file_path, 'wb') as f:
                f.write(response.content)
            self.logger.info(f"Archivo SIRE descargado: {file_path}")
            return file_path
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error descargando archivo SIRE: {e}")
            raise