"""
Configuração centralizada — pydantic-settings v2.
Lê do arquivo .env na raiz do projeto.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Aplicação ──────────────────────────────────────────────────────────────
    APP_NAME: str = "OrbisClin Cold"
    APP_ENV:  str = "development"
    PORT:     int = 8001
    TESTING:  bool = False

    # ── Segurança ──────────────────────────────────────────────────────────────
    SECRET_KEY: str  = "TROQUE-ANTES-DE-PRODUCAO-minimo-32-chars!!"
    ALGORITHM:  str  = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int  = 480
    COOKIE_NAME:   str  = "cold_session"
    COOKIE_SECURE: bool = False

    # ── Banco ──────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./orbisclin_cold.db"

    # ── Redis / Celery ─────────────────────────────────────────────────────────
    REDIS_URL:             str = "redis://localhost:6379/1"
    CELERY_BROKER_URL:     str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Sensores ───────────────────────────────────────────────────────────────
    SENSOR_POLL_INTERVAL_SECONDS: int = 60
    OFFLINE_THRESHOLD_MINUTES:    int = 5

    # ── E-mail ─────────────────────────────────────────────────────────────────
    SMTP_HOST:     str  = "localhost"
    SMTP_PORT:     int  = 587
    SMTP_USER:     str  = ""
    SMTP_PASSWORD: str  = ""
    SMTP_FROM:     str  = "cold@hospital.com.br"
    SMTP_TLS:      bool = True

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
