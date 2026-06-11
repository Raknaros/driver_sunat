"""
Esquemas Pydantic para la API REST FastAPI.

Define los modelos de request/response para los endpoints del microservicio.
No confundir con api_clients/sire/schemas.py (esquemas del cliente SUNAT).
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DescargarRequest(BaseModel):
    """
    Request para POST /api/v1/sire/descargar.

    Attributes:
        ruc: RUC del contribuyente (11 dígitos numéricos).
        periodo: Período en formato AAAAMM (ej: "202501").
        tipo: Tipo de propuesta (ej: "REMITENTE", "TRANSPORTISTA").
        webhook_url: URL del orquestador para recibir la notificación.
    """
    ruc: str = Field(
        ...,
        description="RUC del contribuyente (11 dígitos)",
        examples=["12345678901"],
    )
    periodo: str = Field(
        ...,
        description="Período en formato AAAAMM",
        examples=["202501"],
    )
    tipo: str = Field(
        ...,
        description="Tipo de propuesta (ej: REMITENTE, TRANSPORTISTA)",
        examples=["REMITENTE"],
    )
    webhook_url: Optional[str] = Field(
        None,
        description="URL del orquestador para notificar el resultado",
        examples=["https://orquestador/api/webhooks/sire"],
    )

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: str) -> str:
        """Valida que el RUC tenga exactamente 11 dígitos numéricos."""
        if not re.match(r"^\d{11}$", v):
            raise ValueError("RUC debe tener exactamente 11 dígitos numéricos")
        return v

    @field_validator("periodo")
    @classmethod
    def validar_periodo(cls, v: str) -> str:
        """Valida que el período sea AAAAMM con año y mes válidos."""
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Período debe tener formato AAAAMM (6 dígitos)")

        año = int(v[:4])
        mes = int(v[4:6])

        if año < 2000 or año > 2100:
            raise ValueError("Año fuera de rango (debe estar entre 2000 y 2100)")
        if mes < 1 or mes > 12:
            raise ValueError("Mes debe estar entre 01 y 12")

        return v

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        """Valida que el tipo no esté vacío."""
        if not v or not v.strip():
            raise ValueError("Tipo no puede estar vacío")
        return v.strip().upper()


class DescargarResponse(BaseModel):
    """
    Respuesta exitosa con código HTTP 202 Accepted.

    Attributes:
        status: Siempre "accepted".
        job_id: ID de la operación creada en BD.
        message: Mensaje informativo.
    """
    status: str = "accepted"
    job_id: str = Field(..., description="ID de la operación en BD")
    message: str = "Tarea encolada correctamente"


class ErrorResponse(BaseModel):
    """Respuesta de error."""
    detail: str = Field(..., description="Descripción del error")


class HealthResponse(BaseModel):
    """
    Respuesta del endpoint /health.

    Attributes:
        status: "healthy" o "degraded".
        checks: Diccionario con el estado de cada dependencia.
    """
    status: str
    checks: dict