from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Enum as SAEnum
from sqlalchemy.sql import func
import enum

from models.base import Base


class EstadoOperacion(str, enum.Enum):
    """Estados posibles de una operación SIRE."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    EMPTY = "EMPTY"  # Reporte generado correctamente pero sin datos
    S3_UPLOADED = "S3_UPLOADED"
    ERROR = "ERROR"
    WEBHOOK_SENT = "WEBHOOK_SENT"


class SireOperacion(Base):
    """
    Modelo para la tabla driver.sire_operaciones.

    Almacena el estado y trazabilidad de cada operación SIRE procesada.
    """
    __tablename__ = "sire_operaciones"
    __table_args__ = {"schema": "driver"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    ruc = Column(BigInteger, nullable=False, index=True)
    periodo = Column(String(6), nullable=False)
    tipo_operacion = Column(String(50), nullable=False)
    ticket = Column(String(100), nullable=True)
    s3_url = Column(String(500), nullable=True)
    estado = Column(SAEnum(EstadoOperacion), default=EstadoOperacion.PENDING)
    log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())