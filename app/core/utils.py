"""
Utilitários de domínio:
  - log_audit           → grava entrada no audit log
  - avaliar_alertas     → verifica leitura contra limites do equipamento
  - criar_ou_atualizar_alerta
  - fechar_alerta_se_existir
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.constants import ESCALONAMENTO_MINUTOS, NivelEscalonamento, TipoAlerta

logger = logging.getLogger(__name__)


# ── Audit Log ──────────────────────────────────────────────────────────────────

def log_audit(
    db: Session,
    *,
    username:   str,
    action:     str,
    target:     Optional[str] = None,
    details:    Optional[dict] = None,
    ip_address: Optional[str] = None,
    request:    Optional[Request] = None,
) -> None:
    from app.core.models import AuditLog
    ip = ip_address
    if ip is None and request is not None:
        fwd = request.headers.get("X-Forwarded-For")
        ip  = (
            fwd.split(",")[0].strip()
            if fwd
            else (request.client.host if request.client else None)
        )
    db.add(AuditLog(
        username=username, action=action, target=target,
        details=details, ip_address=ip,
        created_at=datetime.now(timezone.utc),
    ))
    db.flush()


# ── Avaliação de alertas ───────────────────────────────────────────────────────

def avaliar_alertas(db: Session, sensor_id: int, leitura) -> None:
    """Verifica temperatura e umidade contra os limites do equipamento."""
    from app.core.models import Sensor

    sensor = db.query(Sensor).filter(Sensor.id == sensor_id).first()
    if not sensor or not sensor.equipamento:
        return
    equip = sensor.equipamento
    temp, umid = leitura.temperatura, leitura.umidade

    # Temperatura
    if temp is not None:
        if equip.temp_max is not None and temp > equip.temp_max:
            criar_ou_atualizar_alerta(
                db, sensor_id=sensor_id, equipamento_id=equip.id,
                tipo=TipoAlerta.TEMP_ALTA.value,
                valor_registrado=temp, valor_limite=equip.temp_max,
            )
        else:
            fechar_alerta_se_existir(db, sensor_id=sensor_id, tipo=TipoAlerta.TEMP_ALTA.value)

        if equip.temp_min is not None and temp < equip.temp_min:
            criar_ou_atualizar_alerta(
                db, sensor_id=sensor_id, equipamento_id=equip.id,
                tipo=TipoAlerta.TEMP_BAIXA.value,
                valor_registrado=temp, valor_limite=equip.temp_min,
            )
        else:
            fechar_alerta_se_existir(db, sensor_id=sensor_id, tipo=TipoAlerta.TEMP_BAIXA.value)

    # Umidade
    if umid is not None:
        if equip.umid_max is not None and umid > equip.umid_max:
            criar_ou_atualizar_alerta(
                db, sensor_id=sensor_id, equipamento_id=equip.id,
                tipo=TipoAlerta.UMID_ALTA.value,
                valor_registrado=umid, valor_limite=equip.umid_max,
            )
        else:
            fechar_alerta_se_existir(db, sensor_id=sensor_id, tipo=TipoAlerta.UMID_ALTA.value)

        if equip.umid_min is not None and umid < equip.umid_min:
            criar_ou_atualizar_alerta(
                db, sensor_id=sensor_id, equipamento_id=equip.id,
                tipo=TipoAlerta.UMID_BAIXA.value,
                valor_registrado=umid, valor_limite=equip.umid_min,
            )
        else:
            fechar_alerta_se_existir(db, sensor_id=sensor_id, tipo=TipoAlerta.UMID_BAIXA.value)

    # Fecha alerta de offline se existir
    fechar_alerta_se_existir(db, sensor_id=sensor_id, tipo=TipoAlerta.OFFLINE.value)


def criar_ou_atualizar_alerta(
    db: Session,
    *,
    sensor_id:       int,
    equipamento_id:  int,
    tipo:            str,
    valor_registrado: Optional[float] = None,
    valor_limite:     Optional[float] = None,
) -> None:
    from app.core.models import Alerta
    existente = db.query(Alerta).filter(
        Alerta.sensor_id == sensor_id,
        Alerta.tipo == tipo,
        Alerta.fim_at.is_(None),
    ).first()

    if existente:
        existente.valor_registrado = valor_registrado
        db.flush()
        return

    agora = datetime.now(timezone.utc)
    db.add(Alerta(
        sensor_id=sensor_id,
        equipamento_id=equipamento_id,
        tipo=tipo,
        valor_registrado=valor_registrado,
        valor_limite=valor_limite,
        inicio_at=agora,
        fim_at=None,
        nivel_escalonamento=NivelEscalonamento.IMEDIATO.value,
        proxima_escalonamento_at=agora + timedelta(
            minutes=ESCALONAMENTO_MINUTOS[NivelEscalonamento.SEGUNDO]
        ),
    ))
    db.flush()


def fechar_alerta_se_existir(db: Session, *, sensor_id: int, tipo: str) -> None:
    from app.core.models import Alerta
    alerta = db.query(Alerta).filter(
        Alerta.sensor_id == sensor_id,
        Alerta.tipo == tipo,
        Alerta.fim_at.is_(None),
    ).first()
    if alerta:
        alerta.fim_at = datetime.now(timezone.utc)
        db.flush()
