"""
Esquemas Pydantic para las operaciones del cliente SIRE.
"""

from pydantic import BaseModel
from typing import Optional


class TicketStatus(BaseModel):
    """
    Estado de un ticket de descarga consultado en SUNAT.

    Los códigos de estado reales de SUNAT son:
    - "01", "02", "03", "05": En proceso
    - "06": Terminado (listo para descargar)
    - "04": Error
    """
    ticket: str
    cod_estado: str         # Código real de SUNAT: "01"-"06", "04"=error
    des_estado: str         # Descripción del estado
    status: str             # Normalizado: "PROCESANDO", "LISTO", "ERROR", "SIN_DATOS"
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
    nom_archivo: Optional[str] = None