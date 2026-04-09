"""
Worker Celery do OrbisClin Cold.

Iniciar (dois terminais):
  .venv/Scripts/celery -A app.core.worker worker -l info -c 4
  .venv/Scripts/celery -A app.core.worker beat   -l info
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

# ─── App Celery ───────────────────────────────────────────────────────────────

celery_app = Celery(
    "orbisclin_cold",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "poll-sensores":  {"task": "app.core.worker.poll_all_sensors",    "schedule": settings.SENSOR_POLL_INTERVAL_SECONDS},
    "check-offline":  {"task": "app.core.worker.check_offline_sensors","schedule": 300},
    "escalate-alerts":{"task": "app.core.worker.escalate_alerts",     "schedule": 60},
    "monthly-report": {"task": "app.core.worker.generate_monthly_report",
                       "schedule": crontab(day_of_month="1", hour="8", minute="0")},
}


def _get_db():
    from app.core.database import SessionLocal
    return SessionLocal()


# ─── poll_all_sensors ─────────────────────────────────────────────────────────

@celery_app.task(name="app.core.worker.poll_all_sensors", bind=True, max_retries=2)
def poll_all_sensors(self):
    from app.core.models import Sensor, Leitura
    from app.core.adapters.base import get_adapter
    from app.core.utils import avaliar_alertas, log_audit

    db = _get_db()
    try:
        sensores = db.query(Sensor).filter(Sensor.is_active == True).all()  # noqa: E712
        logger.info("poll_all_sensors: %d sensores ativos", len(sensores))

        for sensor in sensores:
            try:
                adapter  = get_adapter(sensor.protocolo, sensor.endereco, sensor.config_json or {})
                resultado = adapter.read()

                if resultado.sucesso:
                    agora   = datetime.now(timezone.utc)
                    leitura = Leitura(sensor_id=sensor.id,
                                      temperatura=resultado.temperatura,
                                      umidade=resultado.umidade,
                                      timestamp=agora)
                    db.add(leitura)
                    sensor.ultimo_sinal = agora
                    db.flush()
                    avaliar_alertas(db, sensor.id, leitura)
                    db.commit()
                else:
                    logger.warning("Sensor %d falhou: %s", sensor.id, resultado.erro)
                    log_audit(db, username="system", action="SENSOR_POLL_FALHA",
                              target=f"sensor:{sensor.id}", details={"erro": resultado.erro})
                    db.commit()

            except Exception as exc:
                db.rollback()
                logger.error("Erro sensor %d: %s", sensor.id, exc)
    finally:
        db.close()


# ─── check_offline_sensors ────────────────────────────────────────────────────

@celery_app.task(name="app.core.worker.check_offline_sensors")
def check_offline_sensors():
    from app.core.models import Sensor
    from app.core.utils import criar_ou_atualizar_alerta
    from app.core.constants import TipoAlerta

    db        = _get_db()
    threshold = datetime.now(timezone.utc) - timedelta(minutes=settings.OFFLINE_THRESHOLD_MINUTES)
    try:
        for sensor in db.query(Sensor).filter(Sensor.is_active == True).all():  # noqa: E712
            if sensor.ultimo_sinal is None or sensor.ultimo_sinal < threshold:
                criar_ou_atualizar_alerta(db, sensor_id=sensor.id,
                                          equipamento_id=sensor.equipamento_id,
                                          tipo=TipoAlerta.OFFLINE.value)
                db.commit()
    finally:
        db.close()


# ─── escalate_alerts ──────────────────────────────────────────────────────────

@celery_app.task(name="app.core.worker.escalate_alerts")
def escalate_alerts():
    from app.core.models import Alerta
    from app.core.constants import NivelEscalonamento, ESCALONAMENTO_MINUTOS

    db   = _get_db()
    agora = datetime.now(timezone.utc)
    try:
        alertas = db.query(Alerta).filter(
            Alerta.fim_at.is_(None),
            Alerta.proxima_escalonamento_at <= agora,
            Alerta.nivel_escalonamento < NivelEscalonamento.ADMIN.value,
        ).all()

        proximos = {1: NivelEscalonamento.GERENCIA, 2: NivelEscalonamento.ADMIN}
        for alerta in alertas:
            novo = alerta.nivel_escalonamento + 1
            alerta.nivel_escalonamento = novo
            if novo in proximos:
                alerta.proxima_escalonamento_at = agora + timedelta(
                    minutes=ESCALONAMENTO_MINUTOS[proximos[novo]]
                )
            else:
                alerta.proxima_escalonamento_at = None
            logger.warning("ESCALADA alerta id=%d → nível %d", alerta.id, novo)
            # TODO Fase 4: e-mail HTML para o grupo correspondente

        db.commit()
    finally:
        db.close()


# ─── generate_monthly_report ──────────────────────────────────────────────────

@celery_app.task(name="app.core.worker.generate_monthly_report")
def generate_monthly_report():
    logger.info("generate_monthly_report: placeholder — implementar na Fase 3 (WeasyPrint)")
    # TODO Fase 3: gerar PDF de conformidade mensal
