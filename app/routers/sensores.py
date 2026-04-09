"""CRUD Sensores + teste de conexão."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, CONFIG_JSON_DEFAULTS, PROTOCOLOS, Role
from app.core.database import get_db
from app.core.security import require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_ADMIN    = Depends(require_role(Role.ADMIN))
_OFFLINE  = 5  # minutos


def _404(db, sid):
    from app.core.models import Sensor
    s = db.query(Sensor).filter(Sensor.id == sid).first()
    if not s:
        raise HTTPException(404, {"message": "Sensor não encontrado."})
    return s

def _ctx(user, **kw): return {"current_user": user, **kw}

def _status(sensor) -> str:
    if sensor.ultimo_sinal is None:
        return "nunca"
    delta = (datetime.now(timezone.utc) - sensor.ultimo_sinal).total_seconds() / 60
    return "online" if delta <= _OFFLINE else "offline"


@router.get("/api/config-default/{protocolo}")
async def config_default(protocolo: str):
    return JSONResponse(CONFIG_JSON_DEFAULTS.get(protocolo.upper(), {}))


@router.get("/", response_class=HTMLResponse)
async def listar(request: Request, equipamento_id: Optional[int] = None,
                 db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Sensor, Equipamento
    q = db.query(Sensor)
    if equipamento_id:
        q = q.filter(Sensor.equipamento_id == equipamento_id)
    sensores = q.order_by(Sensor.equipamento_id, Sensor.id).all()
    for s in sensores:
        s._status = _status(s)
    equips = (db.query(Equipamento).filter(Equipamento.is_active == True)  # noqa: E712
              .order_by(Equipamento.nome).all())
    return templates.TemplateResponse(request, "admin/sensores.html",
                                      _ctx(u, sensores=sensores, equipamentos=equips,
                                           equipamento_id_filtro=equipamento_id))


@router.get("/novo", response_class=HTMLResponse)
async def novo_page(request: Request, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Equipamento
    equips = (db.query(Equipamento).filter(Equipamento.is_active == True)  # noqa: E712
              .order_by(Equipamento.nome).all())
    return templates.TemplateResponse(request, "admin/sensor_form.html",
                                      _ctx(u, sensor=None, equipamentos=equips,
                                           protocolos=PROTOCOLOS,
                                           config_defaults=CONFIG_JSON_DEFAULTS, erro=None))


@router.post("/novo", response_class=HTMLResponse)
async def criar(request: Request, equipamento_id: int = Form(...), nome: str = Form(""),
                protocolo: str = Form(...), endereco: str = Form(...),
                config_json_raw: str = Form("{}"),
                db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Sensor, Equipamento
    protocolo = protocolo.upper(); endereco = endereco.strip()
    if protocolo not in PROTOCOLOS or not endereco:
        equips = db.query(Equipamento).filter(Equipamento.is_active == True).all()  # noqa: E712
        return templates.TemplateResponse(request, "admin/sensor_form.html",
                                          _ctx(u, sensor=None, equipamentos=equips,
                                               protocolos=PROTOCOLOS, config_defaults=CONFIG_JSON_DEFAULTS,
                                               erro="Protocolo e endereço são obrigatórios."), status_code=400)
    try:
        config = json.loads(config_json_raw) if config_json_raw.strip() else {}
    except json.JSONDecodeError:
        config = {}
    s = Sensor(equipamento_id=equipamento_id, nome=nome.strip() or None,
               protocolo=protocolo, endereco=endereco, config_json=config, is_active=True)
    db.add(s); db.flush()
    log_audit(db, username=u.username, action=AcaoAudit.CREATE.value,
              target=f"sensor:{s.id}", details={"protocolo": protocolo, "endereco": endereco}, request=request)
    db.commit()
    return RedirectResponse("/sensores?ok=criado", status_code=302)


@router.get("/{sid}/editar", response_class=HTMLResponse)
async def editar_page(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Equipamento
    sensor = _404(db, sid)
    equips = (db.query(Equipamento).filter(Equipamento.is_active == True)  # noqa: E712
              .order_by(Equipamento.nome).all())
    return templates.TemplateResponse(request, "admin/sensor_form.html",
                                      _ctx(u, sensor=sensor, equipamentos=equips,
                                           protocolos=PROTOCOLOS,
                                           config_defaults=CONFIG_JSON_DEFAULTS, erro=None))


@router.post("/{sid}/editar", response_class=HTMLResponse)
async def atualizar(request: Request, sid: int, equipamento_id: int = Form(...),
                    nome: str = Form(""), protocolo: str = Form(...), endereco: str = Form(...),
                    config_json_raw: str = Form("{}"),
                    db: Session = Depends(get_db), u=_ADMIN):
    s = _404(db, sid)
    try:
        config = json.loads(config_json_raw) if config_json_raw.strip() else {}
    except json.JSONDecodeError:
        config = s.config_json or {}
    s.equipamento_id = equipamento_id; s.nome = nome.strip() or None
    s.protocolo = protocolo.upper(); s.endereco = endereco.strip(); s.config_json = config
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"sensor:{sid}", details={"protocolo": s.protocolo}, request=request)
    db.commit()
    return RedirectResponse("/sensores?ok=atualizado", status_code=302)


@router.post("/{sid}/testar")
async def testar(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.adapters.base import get_adapter
    s = _404(db, sid)
    try:
        ok, msg = get_adapter(s.protocolo, s.endereco, s.config_json or {}).test_connection()
    except Exception as exc:
        ok, msg = False, str(exc)
    log_audit(db, username=u.username, action=AcaoAudit.SENSOR_TEST.value,
              target=f"sensor:{sid}", details={"sucesso": ok, "mensagem": msg}, request=request)
    db.commit()
    return JSONResponse({"sucesso": ok, "mensagem": msg})


@router.post("/{sid}/desativar")
async def desativar(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    s = _404(db, sid); s.is_active = False
    log_audit(db, username=u.username, action=AcaoAudit.DEACTIVATE.value,
              target=f"sensor:{sid}", details={"endereco": s.endereco}, request=request)
    db.commit()
    return RedirectResponse("/sensores?ok=desativado", status_code=302)


@router.post("/{sid}/ativar")
async def ativar(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    s = _404(db, sid); s.is_active = True
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"sensor:{sid}", details={"acao": "reativado"}, request=request)
    db.commit()
    return RedirectResponse("/sensores?ok=ativado", status_code=302)
