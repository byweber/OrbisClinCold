"""Dashboard: KPIs, cards de setor, gráfico Chart.js."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.security import apply_setor_filter, get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_OFFLINE  = 5  # minutos


def _now(): return datetime.now(timezone.utc)


def _kpis(db, user) -> dict:
    from app.core.models import Alerta, Equipamento, Leitura, Sensor
    thr = _now() - timedelta(minutes=_OFFLINE)

    q_eq  = apply_setor_filter(db.query(Equipamento).filter(Equipamento.is_active == True), user, Equipamento)  # noqa: E712
    e_ids = [e.id for e in q_eq.all()]

    q_s   = db.query(Sensor).filter(Sensor.equipamento_id.in_(e_ids), Sensor.is_active == True)  # noqa: E712
    total = q_s.count()
    online  = q_s.filter(Sensor.ultimo_sinal >= thr).count()
    offline = total - online

    q_al  = db.query(Alerta).filter(Alerta.equipamento_id.in_(e_ids), Alerta.fim_at.is_(None))
    ativos   = q_al.count()
    criticos = q_al.filter(Alerta.nivel_escalonamento >= 2).count()
    nao_rec  = q_al.filter(Alerta.reconhecido_por.is_(None)).count()

    desde_24h  = _now() - timedelta(hours=24)
    s_ids      = [r[0] for r in q_s.with_entities(Sensor.id).all()]
    total_leit = db.query(func.count(Leitura.id)).filter(
        Leitura.sensor_id.in_(s_ids), Leitura.timestamp >= desde_24h).scalar() or 0
    al_24h = db.query(Alerta).filter(
        Alerta.equipamento_id.in_(e_ids), Alerta.inicio_at >= desde_24h,
        Alerta.tipo != "OFFLINE").count()
    conformidade = round(((total_leit - min(al_24h, total_leit)) / total_leit * 100), 1) if total_leit else 100.0

    return {"total_sensores": total, "online": online, "offline": offline,
            "alertas_ativos": ativos, "alertas_criticos": criticos,
            "nao_reconhecidos": nao_rec, "conformidade_24h": conformidade,
            "total_leituras_24h": total_leit, "equipamentos": len(e_ids),
            "timestamp": _now().isoformat()}


def _cards(db, user) -> list:
    from app.core.models import Alerta, Equipamento, Leitura, Setor, Sensor
    thr = _now() - timedelta(minutes=_OFFLINE)
    q_s = db.query(Setor).filter(Setor.is_active == True)  # noqa: E712
    if user.role != Role.ADMIN.value:
        q_s = q_s.filter(Setor.id == user.setor_id) if user.setor_id else q_s.filter(False)
    cards = []
    for setor in q_s.order_by(Setor.nome).all():
        e_ids  = [e.id for e in db.query(Equipamento).filter(
            Equipamento.setor_id == setor.id, Equipamento.is_active == True).all()]  # noqa: E712
        s_ids  = [s.id for s in db.query(Sensor).filter(
            Sensor.equipamento_id.in_(e_ids), Sensor.is_active == True).all()]  # noqa: E712
        alertas_n = db.query(Alerta).filter(
            Alerta.equipamento_id.in_(e_ids), Alerta.fim_at.is_(None)).count()
        offline_n = db.query(Sensor).filter(
            Sensor.id.in_(s_ids),
            (Sensor.ultimo_sinal < thr) | Sensor.ultimo_sinal.is_(None)).count()
        ultima = (db.query(Leitura)
                  .filter(Leitura.sensor_id.in_(s_ids), Leitura.temperatura.isnot(None))
                  .order_by(Leitura.timestamp.desc()).first())
        status = "alerta" if alertas_n else ("offline" if offline_n else "ok")
        cards.append({"setor": setor, "equipamentos": len(e_ids), "sensores": len(s_ids),
                      "alertas": alertas_n, "offline": offline_n, "status": status,
                      "ultima_temp": ultima.temperatura if ultima else None,
                      "ultima_ts":   ultima.timestamp   if ultima else None})
    return cards


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    from app.core.config import get_settings as _gs
    from app.core.security import decode_token
    from app.core.models import Usuario
    _settings = _gs()
    token = request.cookies.get(_settings.COOKIE_NAME)
    if not token:
        return RedirectResponse("/auth/login", status_code=302)
    try:
        payload = decode_token(token)
        u = db.query(Usuario).filter(
            Usuario.username == payload.get("sub",""),
            Usuario.is_active == True  # noqa: E712
        ).first()
        if not u:
            return RedirectResponse("/auth/login", status_code=302)
    except Exception:
        return RedirectResponse("/auth/login", status_code=302)
    if u.must_change_password:
        return RedirectResponse("/auth/trocar-senha", status_code=302)
    from app.core.models import Alerta, Equipamento
    kpis  = _kpis(db, u)
    cards = _cards(db, u)
    q_al  = (db.query(Alerta)
             .join(Equipamento, Alerta.equipamento_id == Equipamento.id)
             .filter(Alerta.fim_at.is_(None)))
    if u.role != Role.ADMIN.value:
        q_al = q_al.filter(Equipamento.setor_id == u.setor_id) if u.setor_id else q_al.filter(False)
    recentes = q_al.order_by(Alerta.inicio_at.desc()).limit(8).all()
    return templates.TemplateResponse(request, "home.html", {
        "current_user": u, "kpis": kpis, "cards": cards,
        "alertas_recentes": recentes,
        "alertas_ativos": kpis["alertas_ativos"],
        "sensores_ativos": kpis["online"],
    })


@router.get("/api/kpis")
async def api_kpis(db: Session = Depends(get_db), u=Depends(get_current_user)):
    return JSONResponse(_kpis(db, u))


@router.get("/api/grafico/{sensor_id}")
async def api_grafico(sensor_id: int, horas: int = Query(24, ge=1, le=168),
                      db: Session = Depends(get_db), u=Depends(get_current_user)):
    from app.core.models import Equipamento, Leitura, Sensor
    s = db.query(Sensor).filter(Sensor.id == sensor_id).first()
    if not s:
        return JSONResponse({"erro": "Sensor não encontrado"}, status_code=404)
    if u.role != Role.ADMIN.value:
        eq = db.query(Equipamento).filter(Equipamento.id == s.equipamento_id).first()
        if not eq or eq.setor_id != u.setor_id:
            return JSONResponse({"erro": "Acesso negado"}, status_code=403)
    desde    = _now() - timedelta(hours=horas)
    leituras = (db.query(Leitura)
                .filter(Leitura.sensor_id == sensor_id, Leitura.timestamp >= desde)
                .order_by(Leitura.timestamp.asc()).all())
    if len(leituras) > 500:
        step = len(leituras) // 300
        leituras = leituras[::step]
    eq = s.equipamento
    return JSONResponse({
        "sensor_id": sensor_id, "nome": s.nome or f"Sensor #{sensor_id}",
        "equipamento": eq.nome if eq else None,
        "temp_min": eq.temp_min if eq else None, "temp_max": eq.temp_max if eq else None,
        "umid_min": eq.umid_min if eq else None, "umid_max": eq.umid_max if eq else None,
        "labels":      [l.timestamp.strftime("%d/%m %H:%M") for l in leituras],
        "temperatura": [round(l.temperatura, 2) if l.temperatura is not None else None for l in leituras],
        "umidade":     [round(l.umidade,     2) if l.umidade     is not None else None for l in leituras],
    })
