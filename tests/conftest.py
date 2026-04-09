"""
Configuração de testes — SQLite em arquivo temporário.

Usa DATABASE_URL apontando para um arquivo .db temporário para que todas
as conexões SQLAlchemy (app + testes) compartilhem as mesmas tabelas.
SQLite em memória cria um banco isolado por conexão, o que causa "no such table".
"""
import os
import pathlib
import tempfile

# Banco temporário em arquivo (apagado ao fim de cada sessão de testes)
_db_file = pathlib.Path(tempfile.mktemp(suffix="_cold_test.db"))
os.environ.setdefault("TESTING",      "1")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_file}")
os.environ.setdefault("SECRET_KEY",   "test-secret-key-32-chars-minimum!!")

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import Base, engine, SessionLocal
from app.main import app

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Cria todas as tabelas uma vez por sessão de testes."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    _db_file.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _limpar_dados():
    """Limpa todos os dados entre testes, mantendo o schema."""
    yield
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
