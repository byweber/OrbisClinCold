# app/core/database.py
import logging
import secrets
import string
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app.core.models import Usuario
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(Usuario).filter(Usuario.role == "ADMIN").first()
        if not admin:
            alphabet = string.ascii_letters + string.digits
            senha_temp = ''.join(secrets.choice(alphabet) for _ in range(12))
            admin = Usuario(
                username="admin",
                email="admin@orbisclin.local",
                nome_completo="Administrador do Sistema",
                hashed_password=get_password_hash(senha_temp),
                role="ADMIN",
                ativo=True
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            if settings.APP_ENV == "development":
                logger.warning("=" * 60)
                logger.warning("🔐 USUÁRIO ADMIN CRIADO")
                logger.warning(f"   Username: admin")
                logger.warning(f"   Senha....: {senha_temp}")
                logger.warning("=" * 60)
            else:
                logger.info("Usuário admin criado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()