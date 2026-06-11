from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos SQLAlchemy."""
    metadata = MetaData()