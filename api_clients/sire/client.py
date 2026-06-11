"""
Cliente para la API SIRE de SUNAT.

Provee métodos para:
- Solicitar descarga de propuestas.
- Consultar estado de tickets.
- Descargar archivos ZIP en memoria.
- Aceptar, reemplazar, agregar comprobantes y generar registros (skeletons).
"""

import logging
from typing import Optional

from api_clients.base_client import (
    BaseSunatAPIClient,
    EmptyReportError,
    sunat_retry,
)
from api_clients.sire.schemas import DownloadResponse, TicketStatus

logger = logging.getLogger(__name__)


class SireClient(BaseSunatAPIClient):
    """
    Cliente para la API SIRE de SUNAT.

    Hereda de BaseSunatAPIClient, lo que le provee:
    - HTTPX asíncrono con timeout.
    - Reintentos automáticos ante 5xx.
    - Caché de tokens en Redis.
    - Refresco automático de token ante 401.

    Uso::

        async with SireClient(ruc="12345678901", username="user", password="pass") as client:
            ticket = await client.solicitar_descarga_propuesta("202501", "REMITENTE")
            estado = await client.consultar_estado_ticket(ticket)
            if estado.estado == "COMPLETADO":
                zip_bytes = await client.descargar_archivo(estado.parametros_descarga)
    """

    # ------------------------------------------------------------------
    # Configuración de la API
    # ------------------------------------------------------------------
    BASE_URL = "https://api.sunat.gob.pe/v1/sire"

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------
    async def _authenticate(self) -> str:
        """
        Autentica contra SUNAT usando las credenciales de la instancia.

        Returns:
            str: Access token para las siguientes peticiones.
        """
        logger.info("Autenticando RUC %s en SUNAT SIRE...", self.ruc)

        response = await self._client.post(
            "/auth",
            json={
                "ruc": self.ruc,
                "username": self.username,
                "password": self.password,
            },
        )
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]

        logger.info("Autenticación exitosa para RUC %s", self.ruc)
        return token

    # ------------------------------------------------------------------
    # Métodos completos (probados y funcionales)
    # ------------------------------------------------------------------

    @sunat_retry
    async def solicitar_descarga_propuesta(self, periodo: str, tipo: str) -> str:
        """
        Solicita una descarga de propuesta a SUNAT.

        Args:
            periodo: Período en formato AAAAMM (ej: "202501").
            tipo: Tipo de propuesta (ej: "REMITENTE", "TRANSPORTISTA").

        Returns:
            str: Ticket de seguimiento de la solicitud.

        Raises:
            httpx.HTTPStatusError: Si SUNAT responde con error.
        """
        logger.info(
            "Solicitando descarga propuesta: RUC=%s, periodo=%s, tipo=%s",
            self.ruc, periodo, tipo,
        )

        response = await self._make_request(
            "POST",
            "/descarga/solicitar",
            json={"periodo": periodo, "tipo": tipo},
        )
        data = response.json()
        ticket = data["ticket"]

        logger.info("Descarga solicitada exitosamente. Ticket: %s", ticket)
        return ticket

    @sunat_retry
    async def consultar_estado_ticket(self, ticket: str) -> TicketStatus:
        """
        Consulta el estado de un ticket de descarga.

        Detecta automáticamente si el reporte se generó vacío
        (sin registros/comprobantes), retornando estado 'SIN_DATOS'.

        Args:
            ticket: Ticket de seguimiento.

        Returns:
            TicketStatus con estado, mensaje y parámetros de descarga (si aplica).
        """
        logger.debug("Consultando estado del ticket %s", ticket)

        response = await self._make_request(
            "GET",
            f"/descarga/estado/{ticket}",
        )
        data = response.json()

        estado = data.get("estado", "ERROR")
        mensaje = data.get("mensaje", "")

        # Detectar reporte vacío: generado pero sin datos
        es_vacio = (
            estado == "COMPLETADO"
            and (
                data.get("cantidad_registros", 1) == 0
                or "sin datos" in mensaje.lower()
                or "vacio" in mensaje.lower()
                or "no contiene" in mensaje.lower()
            )
        )

        if es_vacio:
            logger.warning(
                "Ticket %s: reporte generado pero SIN DATOS. Mensaje: %s",
                ticket, mensaje,
            )
            return TicketStatus(
                ticket=ticket,
                estado="SIN_DATOS",
                mensaje="El reporte se generó correctamente pero no contiene registros.",
                parametros_descarga=None,
            )

        logger.debug("Ticket %s: estado=%s", ticket, estado)
        return TicketStatus(
            ticket=ticket,
            estado=estado,
            mensaje=mensaje,
            parametros_descarga=data.get("parametros_descarga"),
        )

    @sunat_retry
    async def descargar_archivo(self, download_params: dict) -> DownloadResponse:
        """
        Descarga el archivo ZIP de la propuesta.

        IMPORTANTE: Retorna los bytes en memoria. NADA DE DISCO.

        Args:
            download_params: Parámetros obtenidos de consultar_estado_ticket
                             cuando estado == 'COMPLETADO'.

        Returns:
            DownloadResponse con contenido en bytes o indicando reporte vacío.
        """
        logger.debug("Descargando archivo con params: %s", download_params)

        response = await self._make_request(
            "POST",
            "/descarga/obtener",
            json=download_params,
        )
        contenido = response.content

        # ZIP vacío típicamente pesa ~22 bytes (firma EoCd)
        # Un ZIP mínimo con archivos suele pesar > 100 bytes
        if not contenido or len(contenido) < 50:
            logger.warning(
                "Archivo descargado está vacío o es mínimo (%d bytes)",
                len(contenido) if contenido else 0,
            )
            return DownloadResponse(
                ticket=download_params.get("ticket", ""),
                contenido=None,
                es_vacio=True,
                mensaje="El archivo descargado no contiene datos.",
            )

        ticket = download_params.get("ticket", "desconocido")
        logger.info(
            "Archivo descargado exitosamente. Ticket: %s, tamaño: %d bytes",
            ticket, len(contenido),
        )
        return DownloadResponse(
            ticket=ticket,
            contenido=contenido,
            es_vacio=False,
        )

    # ------------------------------------------------------------------
    # Skeletons (cascarones para implementar después)
    # ------------------------------------------------------------------

    async def aceptar_propuesta(self, periodo: str, tipo: str) -> str:
        """
        Acepta la propuesta de SUNAT.

        Args:
            periodo: Período en formato AAAAMM.
            tipo: Tipo de propuesta.

        Returns:
            str: Ticket de seguimiento.

        Raises:
            NotImplementedError: Método no implementado aún.
        """
        raise NotImplementedError("aceptar_propuesta no implementado aún")

    async def reemplazar_propuesta(
        self, periodo: str, tipo: str, file_bytes: bytes
    ) -> str:
        """
        Reemplaza la propuesta subiendo un archivo.

        Args:
            periodo: Período en formato AAAAMM.
            tipo: Tipo de propuesta.
            file_bytes: Contenido del archivo ZIP/TXT a subir.

        Returns:
            str: Ticket de seguimiento.

        Raises:
            NotImplementedError: Método no implementado aún.
        """
        raise NotImplementedError("reemplazar_propuesta no implementado aún")

    async def agregar_comprobantes(self, periodo: str, file_bytes: bytes) -> str:
        """
        Agrega comprobantes a la propuesta.

        Args:
            periodo: Período en formato AAAAMM.
            file_bytes: Contenido del archivo con comprobantes.

        Returns:
            str: Ticket de seguimiento.

        Raises:
            NotImplementedError: Método no implementado aún.
        """
        raise NotImplementedError("agregar_comprobantes no implementado aún")

    async def generar_registro(self, periodo: str, tipo: str) -> str:
        """
        Consolida y genera el registro de la propuesta.

        Args:
            periodo: Período en formato AAAAMM.
            tipo: Tipo de propuesta.

        Returns:
            str: Ticket de seguimiento.

        Raises:
            NotImplementedError: Método no implementado aún.
        """
        raise NotImplementedError("generar_registro no implementado aún")