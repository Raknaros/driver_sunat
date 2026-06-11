from sqlalchemy import Column, Integer, String, BigInteger

from models.base import Base


class EntityCredencial(Base):
    """
    Mapeo a priv.entities - SOLO LECTURA.

    Contiene las credenciales tradicionales de SUNAT (usuario SOL y clave SOL).
    También incluye observaciones para trazabilidad.
    """
    __tablename__ = "entities"
    __table_args__ = {"schema": "priv", "autoload_with": None}

    id = Column(Integer, primary_key=True)
    ruc = Column(BigInteger, nullable=False)
    usuario_sol = Column("usuario_sol", String, nullable=True)
    clave_sol = Column("clave_sol", String, nullable=True)
    activo = Column("activo", String, nullable=True)
    observaciones = Column("observaciones", String, nullable=True)