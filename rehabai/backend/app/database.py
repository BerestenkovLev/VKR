"""Подключение к базе данных.

Для демонстратора используется SQLite (один файл, без установки СУБД).
В целевой архитектуре, описанной в работе, на этом месте PostgreSQL,
развёрнутый в сертифицированном защищённом контуре (152-ФЗ, СКЗИ).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Файл базы создаётся рядом с приложением при первом запуске.
SQLITE_URL = "sqlite:///./rehabai.db"

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},  # требуется SQLite в многопоточном FastAPI
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей."""
    pass


def get_db():
    """Зависимость FastAPI: открывает сессию на время запроса и закрывает после."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
