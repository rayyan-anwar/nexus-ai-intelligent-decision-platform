from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base. Importing app.db.models registers every table on Base.metadata."""
