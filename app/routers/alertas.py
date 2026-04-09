"""Alertas: listagem, reconhecimento, API JSON."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role, TipoAlerta
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_AUTH     = Depends(require_role(Role.ADMIN, Role.OPERADOR, Role.VIEWER))
_WRITE    = Depends(require_role(Role.ADMIN, Role.OPERADOR))

TIPOS = [t.value for t in TipoAlerta]


def _q_alertas(db, user, ativo_only=False):
    from app.core.models import Alerta, Equipamento, Sensor
    q = (db.query(Alerta)
         .join(Sensor,      Alerta.sensor_id      == Sensor.id)
         .join(Equipamento, Alerta.equipamento_id == Equipamento.id))
    if ativo_only:
        q = q.filter(Alerta.fim_at.is_(None))
    if user.role != Role.ADMIN.value:
        q = q.filter(Equipamento.setor_id == user.setor_id) if user.setor_id else q.filter(False)
    return q


@router.get("/", response_class=HTMLResponse)
async def listar(request: Request, tipo: Optional[str] = Query(None),
                 historico: bool = Query(False), pagina: int = Query(1, ge=1),
                 db: Session = Depends(get_db), u=_AUTH):
    from app.core.models import Alerta
    POR_PAG = 30

    q_at = _q_alertas(db, u, ativo_only=True)
    if tipo:
        q_at = q_at.filter(Alerta.tipo == tipo)
    ativos = q_at.order_by(Alerta.inicio_at.desc()).all()

    hist, total_pag = [], 1
    if historico:
        q_h = _q_alertas(db, u).filter(Alerta.fim_at.isnot(None))
        if tipo:
            q_h = q_h.filter(Alerta.tipo == tipo)
        total    = q_h.count()
        total_pag = max(1, (total + POR_PAG - 1) // POR_PAG)
        pagina   = min(pagina, total_pag)
        hist     = q_h.order_by(Alerta.inicio_at.desc()).offset((pagina - 1) * POR_PAG).limit(POR_PAG).all()

    return templates.TemplateResponse(request, "alertas.html", {
        "current_user": u, "ativos": ativos, "historico_list": hist,
        "historico": historico, "tipo_filtro": tipo, "tipos_alerta": TIPOS,
        "pagina": pagina, "total_paginas": total_pag, "alertas_ativos": len(ativos),
    })


@router.post("/{aid}/reconhecer")
async def reconhecer(request: Request, aid: int,
                     db: Session = Depends(get_db), u=_WRITE):
    from app.core.models import Alerta, Equipamento
    a = db.query(Alerta).filter(Alerta.id == aid).first()
    if not a:
        return RedirectResponse("/alertas?erro=Alerta+nao+encontrado.", status_code=302)
    if u.role != Role.ADMIN.value:
        eq = db.query(Equipamento).filter(Equipamento.id == a.equipamento_id).first()
        if not eq or eq.setor_id != u.setor_id:
            return RedirectResponse("/alertas?erro=Permissao+negada.", status_code=302)
    if a.reconhecido_por:
        return RedirectResponse("/alertas?erro=Alerta+ja+reconhecido.", status_code=302)
    a.reconhecido_por = u.username
    a.reconhecido_at  = datetime.now(timezone.utc)
    log_audit(db, username=u.username, action=AcaoAudit.ALERTA_RECONHECIDO.value,
              target=f"alerta:{aid}", details={"tipo": a.tipo}, request=request)
    db.commit()
    return RedirectResponse("/alertas?ok=reconhecido", status_code=302)


@router.get("/api/ativos")
async def api_ativos(db: Session = Depends(get_db), u=Depends(get_current_user)):
    from app.core.models import Alerta, Equipamento, Sensor
    q = (db.query(Alerta)
         .join(Sensor,      Alerta.sensor_id      == Sensor.id)
         .join(Equipamento, Alerta.equipamento_id == Equipamento.id)
         .filter(Alerta.fim_at.is_(None)))
    if u.role != Role.ADMIN.value:
        q = q.filter(Equipamento.setor_id == u.setor_id) if u.setor_id else q.filter(False)
    total   = q.count()
    alertas = q.order_by(Alerta.inicio_at.desc()).limit(10).all()
    return JSONResponse({"total": total, "alertas": [
        {"id": a.id, "tipo": a.tipo,
         "equipamento": a.equipamento.nome if a.equipamento else None,
         "valor": a.valor_registrado, "limite": a.valor_limite,
         "inicio": a.inicio_at.isoformat(), "reconhecido": bool(a.reconhecido_por),
         "escalonamento": a.nivel_escalonamento}
        for a in alertas
    ]})
