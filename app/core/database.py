"""
Banco de dados — SQLite (dev) / PostgreSQL (prod).
Sem importação circular: não importa security.py.
"""
import logging
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

# ── Engine ─────────────────────────────────────────────────────────────────────

_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    # Echo SQL apenas em dev e fora de testes (evita poluir output do pytest)
    echo=(settings.APP_ENV == "development" and not settings.TESTING),
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ── Base declarativa (SQLAlchemy 2.x) ─────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Dependency FastAPI ─────────────────────────────────────────────────────────

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Inicialização ──────────────────────────────────────────────────────────────

def _senha_aleatoria(n: int = 16) -> str:
    alpha = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alpha) for _ in range(n))


def init_db() -> None:
    """
    Cria tabelas e admin inicial (apenas se não houver usuários).
    Em testes (TESTING=True) apenas cria as tabelas e retorna imediatamente.
    """
    from app.core import models  # noqa: F401 — registra todos os modelos na Base

    Base.metadata.create_all(bind=engine)

    # Em testes, não criar admin — o conftest controla o banco
    if settings.TESTING:
        return

    from app.core.pwd import hash_password

    with SessionLocal() as db:
        from app.core.models import Usuario
        if db.query(Usuario).count() == 0:
            senha = _senha_aleatoria(16)
            db.add(Usuario(
                username="admin",
                hashed_password=hash_password(senha),
                role="ADMIN",
                must_change_password=True,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ))
            db.commit()
            logger.warning("=" * 60)
            logger.warning("  PRIMEIRO BOOT — OrbisClin Cold")
            logger.warning("  Usuário : admin")
            logger.warning("  Senha   : %s", senha)
            logger.warning("  Troque a senha imediatamente após o login!")
            logger.warning("=" * 60)
