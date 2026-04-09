"""
Banco de dados — SQLite (dev) / PostgreSQL+TimescaleDB (prod).
init_db() cria admin com senha aleatória no primeiro boot.
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

# ── Engine ────────────────────────────────────────────────────────────────────

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
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


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _gerar_senha(n: int = 16) -> str:
    alpha = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alpha) for _ in range(n))


def init_db() -> None:
    """Cria tabelas e admin inicial (apenas se não houver usuários)."""
    from app.core import models  # noqa: F401
    from app.core.pwd import hash_password

    Base.metadata.create_all(bind=engine)

    # Em testes, não criar admin — o conftest controla o DB
    if settings.TESTING:
        return

    with SessionLocal() as db:
        from app.core.models import Usuario
        if db.query(Usuario).count() == 0:
            senha = _gerar_senha(16)
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
