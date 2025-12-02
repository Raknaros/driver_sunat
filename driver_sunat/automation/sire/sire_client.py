# -*- coding: utf-8 -*-
import requests
from datetime import datetime, timedelta
from ...config import config
from ...database import operations as db

class SireNoComprobantesError(Exception):
    """Lanzada cuando la API SIRE devuelve un error 1070 (sin comprobantes)."""
    pass

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
        Obtiene un Bearer Token con un sistema de cache de tres niveles:
        1. Cache en memoria (dentro de la instancia)
        2. Cache en BD local
        3. Solicitud a la API de SUNAT
        """
        # 1. Verificar cache en memoria
        if self.token and self.token_expires_at and self.token_expires_at > datetime.now():
            self.logger.info("Token SIRE obtenido de cache en memoria.")
            return self.token

        # 2. Verificar cache en BD
        cached_token = db.get_valid_sire_token(ruc)
        if cached_token:
            self.token = cached_token
            self.token_expires_at = datetime.now() + timedelta(hours=1)  # Asumir 1h de validez
            self.logger.info("Token SIRE obtenido de cache en BD.")
            return self.token

        # 3. Obtener nuevo token de SUNAT
        self.logger.info("Solicitando nuevo token de acceso SIRE a SUNAT...")
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
            # Guardar en BD con fecha de expiración real
            expires_in_seconds = data.get('expires_in', 3600) # Default 1 hora
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)
            db.save_sire_token(ruc, self.token, self.token_expires_at.isoformat())
            
            self.logger.info("Token de acceso SIRE obtenido y guardado.")
            return self.token
        except requests.exceptions.HTTPError as e:
            error_msg = f"Error token SIRE HTTP {e.response.status_code}: {e.response.text}"
            self.logger.error(error_msg)
            db.add_observation(ruc, error_msg, "LOCAL")
            raise
        except requests.exceptions.RequestException as e:
            error_msg = f"Error obteniendo token SIRE: {e}"
            self.logger.error(error_msg)
            db.add_observation(ruc, error_msg, "LOCAL")
            raise

    def _make_request(self, method, url, params=None, retries=3, sol_user=None, sol_pass=None):
        """
        Realiza una request HTTP con reintentos y manejo de token.
        """
        # Asegurarse de tener un token antes de la primera request
        if not self.token:
            self._get_token(self.ruc, sol_user, sol_pass)

        for attempt in range(retries):
            try:
                headers = {'Authorization': f'Bearer {self.token}'}
                response = requests.request(method, url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                # Manejo de error 422 / 1070
                if e.response.status_code == 422:
                    try:
                        error_data = e.response.json()
                        if any(err.get('cod') == '1070' for err in error_data.get('errors', [])):
                            raise SireNoComprobantesError(error_data)
                    except (ValueError, KeyError):
                        pass # Si el JSON no es válido o no tiene la estructura, se trata como error normal

                if e.response.status_code == 401:  # Token expirado
                    self.logger.warning("Token expirado o inválido, intentando refrescar...")
                    self.token = None # Forzar refresh
                    self._get_token(self.ruc, sol_user, sol_pass) # Obtener nuevo token
                    continue # Reintentar la request original
                self.logger.error(f"Error HTTP en request SIRE (intento {attempt+1}): {e.response.text}")
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

        data = self._make_request('GET', url, params, sol_user=sol_user, sol_pass=sol_pass)
        if data and 'numTicket' in data:
            self.logger.info(f"Propuesta SIRE {tipo} solicitada, ticket: {data['numTicket']}")
            return data['numTicket']
        else:
            self.logger.error(f"No se recibió numTicket en respuesta de propuesta: {data}")
            return None

    def query_status(self, ruc, sol_user, sol_pass, ticket, periodo):
        """
        Consulta el estado de un ticket.
        """
        libro = 'rvierce'
        url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/gestionprocesosmasivos/web/masivo/consultaestadotickets"
        params = {
            'perIni': periodo,
            'perFin': periodo,
            'page': 1,
            'perPage': 20,
            'numTicket': ticket
        }

        data = self._make_request('GET', url, params, sol_user=sol_user, sol_pass=sol_pass)
        if data:
            self.logger.info(f"Estado de ticket {ticket} consultado")
            return data
        return None

    def download_file(self, ruc, sol_user, sol_pass, download_params: dict):
        """
        Descarga un archivo de reporte usando los parámetros obtenidos de la consulta de estado.
        """
        libro = 'rvierce'
        url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/{libro}/gestionprocesosmasivos/web/masivo/archivoreporte"
        
        # Asegurarse de tener un token
        if not self.token:
            self._get_token(ruc, sol_user, sol_pass)

        headers = {'Authorization': f'Bearer {self.token}'}
        try:
            response = requests.get(url, headers=headers, params=download_params, timeout=60)
            response.raise_for_status()

            nom_archivo = download_params.get('nomArchivoReporte')
            file_path = f"{config.DOWNLOAD_PATH}/{nom_archivo}"
            with open(file_path, 'wb') as f:
                f.write(response.content)
            self.logger.info(f"Archivo SIRE descargado: {file_path}")
            return file_path
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error descargando archivo SIRE: {e}")
            raise