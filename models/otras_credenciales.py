from sqlalchemy import Column, Integer, String, BigInteger

from models.base import Base


class OtraCredencial(Base):
    """
    Mapeo a priv.otras_credenciales - SOLO LECTURA.

    Para obtener credenciales de API SIRE, filtrar por:
        tipo = 'APISUNAT'
        notas = 'SIRE'
    """
    __tablename__ = "otras_credenciales"
    __table_args__ = {"schema": "priv", "autoload_with": None}

    id = Column(Integer, primary_key=True)
    ruc = Column(BigInteger, nullable=True)
    tipo = Column(String, nullable=True)
    usuario = Column(String, nullable=True)
    contrasena = Column(String, nullable=True)
    credencial3 = Column(String, nullable=True)  # Legacy, no se usa para SIRE
    notas = Column(String, nullable=True)
    observaciones = Column(String, nullable=True)