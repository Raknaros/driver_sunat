from sqlalchemy import Column, String, BigInteger, Boolean, Integer
from models.base import Base

class CredencialEntity(Base):
    """
    Modelo de SOLO LECTURA mapeado a la tabla de credenciales SOL.
    """
    __tablename__ = "entities"
    __table_args__ = {'schema': 'priv'}

    ruc = Column(BigInteger, primary_key=True)
    usuario_sol = Column(String(255))
    clave_sol = Column(String(255))
    activo = Column(Boolean)

class OtraCredencial(Base):
    """
    Modelo de SOLO LECTURA mapeado a las credenciales adicionales (Ej: API SUNAT).
    """
    __tablename__ = "otras_credenciales"
    __table_args__ = {'schema': 'priv'}

    id = Column(Integer, primary_key=True)
    ruc = Column(BigInteger)
    tipo = Column(String)
    usuario = Column(String)
    contrasena = Column(String)
    credencial3 = Column(String)
