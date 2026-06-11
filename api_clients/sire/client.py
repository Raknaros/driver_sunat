"""
Cliente para la API SIRE de SUNAT.

Implementa el flujo OAuth2 real de SUNAT:
1. Autenticación con 4 credenciales (client_id, client_secret, user_sol, clave_sol)
2. Endpoints reales de la API SIRE

Basado en el código legacy probado en driver_sunat/automation/sire/sire_client.py
"""

import logging
import re
from typing import Optional

import httpx

from api_clients.base_client import (
    BaseSunatAPIClient,
    sunat_retry,
)
from api_clients.sire.schemas import DownloadResponse, TicketStatus

logger = logging.getLogger(__name__)

TIPO_VENTAS = "ventas"
TIPO_COMPRAS = "compras"


class SireClient(BaseSunatAPIClient):
    """
    Cliente para la API SIRE de SUNAT.

    A diferencia de BaseSunatAPIClient, este cliente:
    - Recibe 4 credenciales (no 2): client_id, client_secret, user_sol, clave_sol
    - Usa OAuth2 real con grant_type=password y x-www-form-urlencoded
    - Usa URLs reales de SUNAT (api-seguridad, api-sire)

    Uso::

        async with SireClient(
            ruc="12345678901",
            client_id="oc_usuario",
            client_secret="oc_contrasena",
            user_sol="MIEMP1234",
            clave_sol="miclave123",
        ) as client:
            ticket = await client.solicitar_descarga_propuesta("202501", "ventas")
            estado = await client.consultar_estado_ticket(ticket, "202501")
    """

    # ------------------------------------------------------------------
    # URLs base de SUNAT
    # ------------------------------------------------------------------
    BASE_URL_SEGURIDAD = "https://api-seguridad.sunat.gob.pe"
    BASE_URL_SIRE = "https://api-sire.sunat.gob.pe"

    # ------------------------------------------------------------------
    # Mapeo de libros SIRE por tipo
    # ------------------------------------------------------------------
    LIBROS = {
        TIPO_VENTAS: "rvie",
        TIPO_COMPRAS: "rce",
    }

    def __init__(
        self,
        ruc: str,
        client_id: str,
        client_secret: str,
        user_sol: str,
        clave_sol: str,
    ):
        """
        Inicializa el cliente SIRE.

        Args:
            ruc: RUC del contribuyente.
            client_id: Corresponde a oc.usuario (de otras_credenciales).
            client_secret: Corresponde a oc.contrasena (de otras_credenciales).
            user_sol: Corresponde a e.usuario_sol (de entities).
            clave_sol: Corresponde a e.clave_sol (de entities).
        """
        super().__init__(
            ruc=ruc,
            username=client_id,
            password=client_secret,
        )
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_sol = user_sol
        self.clave_sol = clave_sol

    # ------------------------------------------------------------------
    # Autenticación OAuth2 real (NO el placeholder /auth)
    # ------------------------------------------------------------------
    async def _authenticate(self) -> str:
        """
        Obtiene un Bearer Token usando OAuth2 real de SUNAT.

        Endpoint: POST https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/
        Content-Type: application/x-www-form-urlencoded
        """
        logger.info(
            "Autenticando RUC %s en SUNAT SIRE (OAuth2)...", self.ruc
        )

        token_url = (
            f"{self.BASE_URL_SEGURIDAD}/v1/clientessol/"
            f"{self.client_id}/oauth2/token/"
        )

        # El username es la concatenación de RUC + user_sol
        username = f"{self.ruc}{self.user_sol}"

        payload = {
            "grant_type": "password",
            "scope": "https://api-cpe.sunat.gob.pe",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": username,
            "password": self.clave_sol,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = await self._client.post(
            token_url,
            data=payload,        # ← data (no json) para x-www-form-urlencoded
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]

        logger.info("Autenticación OAuth2 exitosa para RUC %s", self.ruc)
        return token

    # ------------------------------------------------------------------
    # Solicitar descarga de propuesta
    # ------------------------------------------------------------------
    @sunat_retry
    async def solicitar_descarga_propuesta(
        self, periodo: str, tipo: str
    ) -> str:
        """
        Solicita una propuesta de descarga a SUNAT.

        Args:
            periodo: Período en formato AAAAMM (ej: "202501").
            tipo: "ventas" o "compras".

        Returns:
            str: Ticket de seguimiento (numTicket).

        Raises:
            ValueError: Si el tipo no es válido.
        """
        libro = self._get_libro(tipo)

        logger.info(
            "Solicitando descarga propuesta: RUC=%s, periodo=%s, tipo=%s, libro=%s",
            self.ruc, periodo, tipo, libro,
        )

        if tipo == TIPO_VENTAS:
            url = (
                f"{self.BASE_URL_SIRE}/v1/contribuyente/migeigv/libros/"
                f"{libro}/propuesta/web/propuesta/{periodo}/exportapropuesta"
            )
            params = {"codTipoArchivo": "0"}
        else:
            url = (
                f"{self.BASE_URL_SIRE}/v1/contribuyente/migeigv/libros/"
                f"{libro}/propuesta/web/propuesta/{periodo}/exportacioncomprobantepropuesta"
            )
            params = {"codTipoArchivo": "0", "codOrigenEnvio": "2"}

        response = await self._make_request("GET", url, params=params)
        data = response.json()
        ticket = data.get("numTicket")

        if not ticket:
            raise ValueError(
                f"No se recibió numTicket en respuesta de SUNAT: {data}"
            )

        logger.info("Propuesta SIRE %s solicitada. Ticket: %s", tipo, ticket)
        return ticket

    # ------------------------------------------------------------------
    # Consultar estado de ticket
    # ------------------------------------------------------------------
    @sunat_retry
    async def consultar_estado_ticket(
        self, ticket: str, periodo: str
    ) -> TicketStatus:
        """
        Consulta el estado de un ticket de descarga.

        Endpoint real de SUNAT. Los códigos de estado reales son:
        - "01", "02", "03", "05": En proceso
        - "06": Terminado (listo para descargar)
        - "04": Error

        Args:
            ticket: Ticket de seguimiento.
            periodo: Período en formato AAAAMM.

        Returns:
            TicketStatus con estado normalizado.
        """
        logger.debug("Consultando estado del ticket %s", ticket)

        libro = "rvierce"  # Libro combinado para consulta de estado
        url = (
            f"{self.BASE_URL_SIRE}/v1/contribuyente/migeigv/libros/"
            f"{libro}/gestionprocesosmasivos/web/masivo/consultaestadotickets"
        )
        params = {
            "perIni": periodo,
            "perFin": periodo,
            "page": 1,
            "perPage": 20,
            "numTicket": ticket,
        }

        response = await self._make_request("GET", url, params=params)
        data = response.json()

        # Validar respuesta
        registros = data.get("registros")
        if not registros:
            logger.debug(
                "Ticket %s: respuesta sin registros, asumiendo PROCESANDO",
                ticket,
            )
            return TicketStatus(
                ticket=ticket,
                cod_estado="",
                des_estado="Sin registros en respuesta",
                status="PROCESANDO",
            )

        # Buscar el ticket específico en la lista
        ticket_info = None
        for registro in registros:
            if str(registro.get("numTicket")) == str(ticket):
                ticket_info = registro
                break

        if not ticket_info:
            logger.debug(
                "Ticket %s no encontrado en registros, asumiendo PROCESANDO",
                ticket,
            )
            return TicketStatus(
                ticket=ticket,
                cod_estado="",
                des_estado="Ticket no encontrado en respuesta",
                status="PROCESANDO",
            )

        detalle = ticket_info.get("detalleTicket", {})
        cod_estado = detalle.get("codEstadoEnvio", "")
        des_estado = detalle.get("desEstadoEnvio", "")

        logger.debug(
            "Ticket %s: cod_estado=%s, des_estado=%s",
            ticket, cod_estado, des_estado,
        )

        # Mapear estado SUNAT a status normalizado
        if cod_estado == "06":  # Terminado
            archivo_reporte_lista = ticket_info.get("archivoReporte")
            if not archivo_reporte_lista:
                logger.error(
                    "Ticket %s: listo pero sin archivoReporte", ticket
                )
                return TicketStatus(
                    ticket=ticket,
                    cod_estado=cod_estado,
                    des_estado=des_estado,
                    status="ERROR",
                    mensaje="Ticket listo pero sin sección archivoReporte",
                )

            archivo_info = archivo_reporte_lista[0]
            nom_archivo = archivo_info.get("nomArchivoReporte", "")

            # Detectar reporte vacío (por nombre o metadata)
            es_vacio = (
                "sin datos" in nom_archivo.lower()
                or "vacio" in nom_archivo.lower()
                or "no contiene" in nom_archivo.lower()
            )

            if es_vacio:
                return TicketStatus(
                    ticket=ticket,
                    cod_estado=cod_estado,
                    des_estado=des_estado,
                    status="SIN_DATOS",
                    mensaje="El reporte se generó correctamente pero no contiene registros.",
                )

            # Extraer parámetros de descarga (preservando el typo 'Achivo' de la API)
            download_params = {
                "nomArchivoReporte": nom_archivo,
                "codTipoArchivoReporte": archivo_info.get(
                    "codTipoAchivoReporte"  # ← Typo intencional de la API
                ),
                "codLibro": ticket_info.get(
                    "codLibro",
                    "140400" if "rvie" in nom_archivo.lower() else "080100",
                ),
                "perTributario": ticket_info.get("perTributario"),
                "codProceso": ticket_info.get("codProceso", "10"),
                "numTicket": ticket,
            }

            # Validar parámetros esenciales
            if not all(download_params.values()):
                logger.error(
                    "Ticket %s: parámetros de descarga incompletos: %s",
                    ticket, download_params,
                )
                return TicketStatus(
                    ticket=ticket,
                    cod_estado=cod_estado,
                    des_estado=des_estado,
                    status="ERROR",
                    mensaje="Parámetros de descarga incompletos",
                )

            return TicketStatus(
                ticket=ticket,
                cod_estado=cod_estado,
                des_estado=des_estado,
                status="LISTO",
                mensaje="Reporte listo para descargar",
                parametros_descarga=download_params,
            )

        elif cod_estado == "04":  # Error
            return TicketStatus(
                ticket=ticket,
                cod_estado=cod_estado,
                des_estado=des_estado,
                status="ERROR",
                mensaje=f"SUNAT reportó error: {des_estado}",
            )

        else:  # 01, 02, 03, 05 - En proceso
            return TicketStatus(
                ticket=ticket,
                cod_estado=cod_estado,
                des_estado=des_estado,
                status="PROCESANDO",
            )

    # ------------------------------------------------------------------
    # Descargar archivo
    # ------------------------------------------------------------------
    @sunat_retry
    async def descargar_archivo(self, download_params: dict) -> DownloadResponse:
        """
        Descarga el archivo ZIP del reporte SIRE.

        IMPORTANTE: Retorna los bytes en memoria. NADA DE DISCO.

        Args:
            download_params: Parámetros obtenidos de consultar_estado_ticket
                             cuando status == 'LISTO'.

        Returns:
            DownloadResponse con contenido en bytes o indicando reporte vacío.
        """
        logger.debug("Descargando archivo con params: %s", download_params)

        libro = "rvierce"
        url = (
            f"{self.BASE_URL_SIRE}/v1/contribuyente/migeigv/libros/"
            f"{libro}/gestionprocesosmasivos/web/masivo/archivoreporte"
        )

        response = await self._make_request("GET", url, params=download_params)

        # Validar que SUNAT no devolvió JSON de error con HTTP 200
        content_type = response.headers.get("Content-Type", "")
        contenido = response.content

        if "application/json" in content_type:
            error_body = response.text[:500]
            logger.error(
                "SUNAT devolvió JSON en lugar del archivo: %s", error_body
            )
            raise ValueError(
                f"Respuesta inesperada de SUNAT (Content-Type JSON): {error_body}"
            )

        nom_archivo = download_params.get("nomArchivoReporte", "desconocido")

        # ZIP vacío típicamente pesa ~22 bytes (firma EoCd)
        if not contenido or len(contenido) < 50:
            logger.warning(
                "Archivo descargado está vacío o es mínimo (%d bytes): %s",
                len(contenido) if contenido else 0,
                nom_archivo,
            )
            return DownloadResponse(
                ticket=download_params.get("numTicket", ""),
                contenido=None,
                es_vacio=True,
                mensaje="El archivo descargado no contiene datos.",
                nom_archivo=nom_archivo,
            )

        # Renombrar archivo para incluir el periodo real (evitar colisiones)
        periodo = download_params.get("perTributario", "")
        nom_archivo_final = self._renombrar_archivo(nom_archivo, periodo)
        if nom_archivo_final != nom_archivo:
            logger.info(
                "Nombre ajustado al periodo: '%s' -> '%s'",
                nom_archivo, nom_archivo_final,
            )

        logger.info(
            "Archivo descargado exitosamente: %s, tamaño: %d bytes",
            nom_archivo_final, len(contenido),
        )
        return DownloadResponse(
            ticket=download_params.get("numTicket", "desconocido"),
            contenido=contenido,
            es_vacio=False,
            nom_archivo=nom_archivo_final,
        )

    # ------------------------------------------------------------------
    # Métodos helpers
    # ------------------------------------------------------------------
    def _get_libro(self, tipo: str) -> str:
        """Obtiene el código de libro SIRE según el tipo."""
        libro = self.LIBROS.get(tipo)
        if not libro:
            raise ValueError(
                f"Tipo no válido: '{tipo}'. Debe ser '{TIPO_VENTAS}' o '{TIPO_COMPRAS}'"
            )
        return libro

    @staticmethod
    def _renombrar_archivo(nombre_original: str, periodo: str) -> str:
        """
        Ajusta el nombre del archivo descargado reemplazando timestamps
        de SUNAT por el período tributario real, preservando la estructura
        original del nombre.

        Patrones:
        1. Ventas: LE{RUC}{AAAAMMDD}{codigos}... → LE{RUC}{periodo}00{codigos}...
           Ej: LE1041883975420260100014040001EXP2 → LE1041883975420260400014040001EXP2
        2. Compras: {RUC}-{AAAAMMDD}-{codigo}-propuesta → {RUC}-{AAAAMMDD}-{periodo}-propuesta
           Ej: 20606283858-20260430-181929-propuesta → 20606283858-20260430-202604-propuesta

        Args:
            nombre_original: Nombre del archivo devuelto por SUNAT.
            periodo: Período en formato AAAAMM (ej: "202501").

        Returns:
            str: Nombre del archivo con el periodo real, o el original si no aplica.
        """
        if not periodo or not nombre_original:
            return nombre_original

        nombre = nombre_original

        # Patrón 1: Ventas - archivos que empiezan con LE seguidas de RUC (11 dígitos)
        # y luego una fecha de 8 dígitos AAAAMMDD
        # Busca: LE{RUC}{8dígitos}... y reemplaza los 8 dígitos por {periodo}00
        nombre = re.sub(
            r"^(LE\d{11})\d{8}",
            f"\\g<1>{periodo}00",
            nombre,
        )

        # Patrón 2: Compras - archivos en formato {RUC}-{AAAAMMDD}-{CODIGO6}-propuesta
        # Reemplaza los 6 dígitos (código) por el periodo AAAAMM
        nombre = re.sub(
            r"(\d{11}-\d{8}-)\d{6}(-propuesta)",
            f"\\g<1>{periodo}\\g<2>",
            nombre,
        )

        return nombre

    # ------------------------------------------------------------------
    # Skeletons (cascarones para implementar después)
    # ------------------------------------------------------------------

    async def aceptar_propuesta(self, periodo: str, tipo: str) -> str:
        """Acepta la propuesta de SUNAT."""
        raise NotImplementedError("aceptar_propuesta no implementado aún")

    async def reemplazar_propuesta(
        self, periodo: str, tipo: str, file_bytes: bytes
    ) -> str:
        """Reemplaza la propuesta subiendo un archivo."""
        raise NotImplementedError("reemplazar_propuesta no implementado aún")

    async def agregar_comprobantes(self, periodo: str, file_bytes: bytes) -> str:
        """Agrega comprobantes a la propuesta."""
        raise NotImplementedError("agregar_comprobantes no implementado aún")

    async def generar_registro(self, periodo: str, tipo: str) -> str:
        """Consolida y genera el registro."""
        raise NotImplementedError("generar_registro no implementado aún")