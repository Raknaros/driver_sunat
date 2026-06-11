"""
Esquemas Pydantic para las operaciones del cliente SIRE.
"""

from pydantic import BaseModel
from typing import Optional


class TicketStatus(BaseModel):
    """
    Estado de un ticket de descarga consultado en SUNAT.

    - Si estado es 'SIN_DATOS', el reporte se generó pero está vacío.
    - parametros_descarga solo está presente cuando estado == 'COMPLETADO'.
    """
    ticket: str
    estado: str  # PENDIENTE, PROCESANDO, COMPLETADO, SIN_DATOS, ERROR
    mensaje: Optional[str] = None
    parametros_descarga: Optional[dict] = None


class DownloadResponse(BaseModel):
    """
    Respuesta de una descarga de archivo.

    - contenido: bytes del ZIP (None si es_vacio=True).
    - es_vacio: True si el reporte no contiene registros.
    """
    ticket: str
    contenido: Optional[bytes] = None
    es_vacio: bool = False
    mensaje: Optional[str] = None