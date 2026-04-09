"""CRUD Equipamentos + defaults de range por tipo."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, RANGES_PADRAO, TIPOS_EQUIPAMENTO, Role
from app.core.database import get_db
from app.core.security import require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_ADMIN    = Depends(require_role(Role.ADMIN))


def _404(db, eid):
    from app.core.models import Equipamento
    e = db.query(Equipamento).filter(Equipamento.id == eid).first()
    if not e:
        raise HTTPException(404, {"message": "Equipamento não encontrado."})
    return e

def _ctx(user, **kw): return {"current_user": user, **kw}

def _f(v: str) -> Optional[float]:
    try:
        return float(v) if v.strip() else None
    except (ValueError, AttributeError):
        return None


@router.get("/api/defaults/{tipo}")
async def defaults(tipo: str):
    d = RANGES_PADRAO.get(tipo.upper())
    return JSONResponse(d if d else {"temp_min": None, "temp_max": None, "umid_min": None, "umid_max": None})


@router.get("/", response_class=HTMLResponse)
async def listar(request: Request, setor_id: Optional[int] = None,
                 db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Equipamento, Setor, Sensor
    q = db.query(Equipamento)
    if setor_id:
        q = q.filter(Equipamento.setor_id == setor_id)
    equips = q.order_by(Equipamento.setor_id, Equipamento.nome).all()
    s_map  = {r.equipamento_id: r.total for r in
              db.query(Sensor.equipamento_id, func.count(Sensor.id).label("total"))
              .filter(Sensor.is_active == True).group_by(Sensor.equipamento_id).all()}  # noqa: E712
    for e in equips:
        e._sensor_count = s_map.get(e.id, 0)
    setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
    return templates.TemplateResponse(request, "admin/equipamentos.html",
                                      _ctx(u, equipamentos=equips, setores=setores, setor_id_filtro=setor_id))


@router.get("/novo", response_class=HTMLResponse)
async def novo_page(request: Request, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
    return templates.TemplateResponse(request, "admin/equipamento_form.html",
                                      _ctx(u, equipamento=None, setores=setores,
                                           tipos=TIPOS_EQUIPAMENTO, ranges_padrao=RANGES_PADRAO, erro=None))


@router.post("/novo", response_class=HTMLResponse)
async def criar(request: Request, setor_id: int = Form(...), nome: str = Form(...),
                tipo: str = Form(...), patrimonio: str = Form(""), fabricante: str = Form(""),
                modelo: str = Form(""), temp_min: str = Form(""), temp_max: str = Form(""),
                umid_min: str = Form(""), umid_max: str = Form(""),
                db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Equipamento, Setor
    nome = nome.strip()
    if not nome or tipo not in TIPOS_EQUIPAMENTO:
        setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
        return templates.TemplateResponse(request, "admin/equipamento_form.html",
                                          _ctx(u, equipamento=None, setores=setores, tipos=TIPOS_EQUIPAMENTO,
                                               ranges_padrao=RANGES_PADRAO, erro="Preencha nome e tipo."), status_code=400)
    e = Equipamento(setor_id=setor_id, nome=nome, tipo=tipo,
                    patrimonio=patrimonio.strip() or None, fabricante=fabricante.strip() or None,
                    modelo=modelo.strip() or None, temp_min=_f(temp_min), temp_max=_f(temp_max),
                    umid_min=_f(umid_min), umid_max=_f(umid_max), is_active=True)
    db.add(e); db.flush()
    log_audit(db, username=u.username, action=AcaoAudit.CREATE.value,
              target=f"equipamento:{e.id}", details={"nome": nome, "tipo": tipo}, request=request)
    db.commit()
    return RedirectResponse("/equipamentos?ok=criado", status_code=302)


@router.get("/{eid}/editar", response_class=HTMLResponse)
async def editar_page(request: Request, eid: int, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    equip   = _404(db, eid)
    setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
    return templates.TemplateResponse(request, "admin/equipamento_form.html",
                                      _ctx(u, equipamento=equip, setores=setores,
                                           tipos=TIPOS_EQUIPAMENTO, ranges_padrao=RANGES_PADRAO, erro=None))


@router.post("/{eid}/editar", response_class=HTMLResponse)
async def atualizar(request: Request, eid: int, setor_id: int = Form(...),
                    nome: str = Form(...), tipo: str = Form(...), patrimonio: str = Form(""),
                    fabricante: str = Form(""), modelo: str = Form(""),
                    temp_min: str = Form(""), temp_max: str = Form(""),
                    umid_min: str = Form(""), umid_max: str = Form(""),
                    db: Session = Depends(get_db), u=_ADMIN):
    e = _404(db, eid)
    e.setor_id = setor_id; e.nome = nome.strip(); e.tipo = tipo
    e.patrimonio = patrimonio.strip() or None; e.fabricante = fabricante.strip() or None
    e.modelo     = modelo.strip() or None
    e.temp_min   = _f(temp_min); e.temp_max = _f(temp_max)
    e.umid_min   = _f(umid_min); e.umid_max = _f(umid_max)
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"equipamento:{eid}", details={"nome": e.nome}, request=request)
    db.commit()
    return RedirectResponse("/equipamentos?ok=atualizado", status_code=302)


@router.post("/{eid}/desativar", response_class=HTMLResponse)
async def desativar(request: Request, eid: int, motivo: str = Form(...),
                    db: Session = Depends(get_db), u=_ADMIN):
    e = _404(db, eid)
    if not motivo.strip():
        return RedirectResponse("/equipamentos?erro=Informe+o+motivo+de+inativacao.", status_code=302)
    e.is_active = False; e.motivo_inativacao = motivo.strip()
    log_audit(db, username=u.username, action=AcaoAudit.DEACTIVATE.value,
              target=f"equipamento:{eid}", details={"motivo": motivo}, request=request)
    db.commit()
    return RedirectResponse("/equipamentos?ok=desativado", status_code=302)


@router.post("/{eid}/ativar")
async def ativar(request: Request, eid: int, db: Session = Depends(get_db), u=_ADMIN):
    e = _404(db, eid); e.is_active = True; e.motivo_inativacao = None
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"equipamento:{eid}", details={"acao": "reativado"}, request=request)
    db.commit()
    return RedirectResponse("/equipamentos?ok=ativado", status_code=302)
