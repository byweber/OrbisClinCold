# app/core/utils.py
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.models import Sensor, Alerta, Leitura

logger = logging.getLogger(__name__)

def avaliar_alertas(db: Session, sensor: Sensor, leitura: Leitura):
    if not sensor.alerta_min and not sensor.alerta_max:
        return
    alertas_gerados = []
    if sensor.alerta_min is not None and leitura.valor < sensor.alerta_min:
        tipo = "TEMPERATURA_BAIXA" if sensor.tipo == "temperatura" else "UMIDADE_BAIXA"
        alerta = _criar_alerta_se_nao_existente(db, sensor, tipo, leitura.valor, sensor.alerta_min)
        if alerta:
            alertas_gerados.append(alerta)
    if sensor.alerta_max is not None and leitura.valor > sensor.alerta_max:
        tipo = "TEMPERATURA_ALTA" if sensor.tipo == "temperatura" else "UMIDADE_ALTA"
        alerta = _criar_alerta_se_nao_existente(db, sensor, tipo, leitura.valor, sensor.alerta_max)
        if alerta:
            alertas_gerados.append(alerta)
    if alertas_gerados:
        logger.info(f"Alertas gerados para sensor {sensor.id}: {[a.tipo for a in alertas_gerados]}")

def _criar_alerta_se_nao_existente(db: Session, sensor: Sensor, tipo: str, valor_atual: float, limite: float):
    existente = db.query(Alerta).filter(
        Alerta.sensor_id == sensor.id,
        Alerta.tipo == tipo,
        Alerta.resolvido == False
    ).first()
    if existente:
        return None
    novo_alerta = Alerta(
        sensor_id=sensor.id,
        tipo=tipo,
        valor=valor_atual,
        limite=limite,
        mensagem=f"{sensor.tipo.capitalize()} {valor_atual} (limite: {limite})",
        timestamp=datetime.utcnow(),
        resolvido=False
    )
    db.add(novo_alerta)
    try:
        db.commit()
        db.refresh(novo_alerta)
        return novo_alerta
    except IntegrityError:
        db.rollback()
        logger.debug(f"Alerta duplicado evitado para sensor {sensor.id}, tipo {tipo}")
        return None