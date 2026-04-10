# app/core/config.py
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Ambiente
    APP_ENV: str = "development"
    APP_NAME: str = "OrbisClin Cold"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = APP_ENV == "development"
    PORT: int = 8000

    # Segurança
    SECRET_KEY: str  # Obrigatório, sem valor padrão
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    COOKIE_NAME: str = "cold_session"
    COOKIE_SECURE: bool = True

    # Banco de dados
    DATABASE_URL: str = "sqlite:///./orbisclin.db"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # Sensores / IoT
    SENSOR_POLL_INTERVAL_SECONDS: int = 60
    OFFLINE_THRESHOLD_MINUTES: int = 5

    # Email (SMTP)
    SMTP_HOST: str = "smtp.exemplo.com.br"
    SMTP_PORT: int = 587
    SMTP_USER: str = "cold@hospital.com.br"
    SMTP_PASSWORD: str = "senha_smtp"
    SMTP_FROM: str = "cold@hospital.com.br"
    SMTP_TLS: bool = True

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY não pode ser vazia. Defina no arquivo .env.")
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY deve ter pelo menos 32 caracteres.")

settings = Settings()