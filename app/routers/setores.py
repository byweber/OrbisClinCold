"""CRUD Setores — ADMIN apenas."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role
from app.core.database import get_db
from app.core.security import require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_ADMIN    = Depends(require_role(Role.ADMIN))


def _404(db, sid):
    from app.core.models import Setor
    s = db.query(Setor).filter(Setor.id == sid).first()
    if not s:
        raise HTTPException(404, {"message": "Setor não encontrado."})
    return s

def _ctx(user, **kw): return {"current_user": user, **kw}


@router.get("/", response_class=HTMLResponse)
async def listar(request: Request, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor, Equipamento
    counts = {r.setor_id: r.total for r in
              db.query(Equipamento.setor_id, func.count(Equipamento.id).label("total"))
              .filter(Equipamento.is_active == True).group_by(Equipamento.setor_id).all()}  # noqa: E712
    setores = db.query(Setor).order_by(Setor.nome).all()
    for s in setores:
        s._eq_count = counts.get(s.id, 0)
    return templates.TemplateResponse(request, "admin/setores.html", _ctx(u, setores=setores))


@router.get("/novo", response_class=HTMLResponse)
async def novo_page(request: Request, u=_ADMIN):
    return templates.TemplateResponse(request, "admin/setor_form.html", _ctx(u, setor=None, erro=None))


@router.post("/novo", response_class=HTMLResponse)
async def criar(request: Request, nome: str = Form(...), descricao: str = Form(""),
                db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    nome = nome.strip()
    if not nome:
        return templates.TemplateResponse(request, "admin/setor_form.html",
                                          _ctx(u, setor=None, erro="Nome obrigatório."), status_code=400)
    if db.query(Setor).filter(Setor.nome == nome).first():
        return templates.TemplateResponse(request, "admin/setor_form.html",
                                          _ctx(u, setor=None, erro=f'Já existe um setor "{nome}".'), status_code=400)
    s = Setor(nome=nome, descricao=descricao.strip() or None, is_active=True)
    db.add(s); db.flush()
    log_audit(db, username=u.username, action=AcaoAudit.CREATE.value,
              target=f"setor:{s.id}", details={"nome": nome}, request=request)
    db.commit()
    return RedirectResponse("/setores?ok=criado", status_code=302)


@router.get("/{sid}/editar", response_class=HTMLResponse)
async def editar_page(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    return templates.TemplateResponse(request, "admin/setor_form.html", _ctx(u, setor=_404(db, sid), erro=None))


@router.post("/{sid}/editar", response_class=HTMLResponse)
async def atualizar(request: Request, sid: int, nome: str = Form(...), descricao: str = Form(""),
                    db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    s = _404(db, sid); nome = nome.strip()
    if not nome:
        return templates.TemplateResponse(request, "admin/setor_form.html",
                                          _ctx(u, setor=s, erro="Nome obrigatório."), status_code=400)
    if db.query(Setor).filter(Setor.nome == nome, Setor.id != sid).first():
        return templates.TemplateResponse(request, "admin/setor_form.html",
                                          _ctx(u, setor=s, erro=f'Já existe outro setor "{nome}".'), status_code=400)
    old = s.nome; s.nome = nome; s.descricao = descricao.strip() or None
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"setor:{sid}", details={"antes": old, "depois": nome}, request=request)
    db.commit()
    return RedirectResponse("/setores?ok=atualizado", status_code=302)


@router.post("/{sid}/desativar")
async def desativar(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Equipamento
    s = _404(db, sid)
    ativos = db.query(Equipamento).filter(Equipamento.setor_id == sid,
                                          Equipamento.is_active == True).count()  # noqa: E712
    if ativos:
        return RedirectResponse(f"/setores?erro=Desative+os+{ativos}+equipamento(s)+ativos+antes.", status_code=302)
    s.is_active = False
    log_audit(db, username=u.username, action=AcaoAudit.DEACTIVATE.value,
              target=f"setor:{sid}", details={"nome": s.nome}, request=request)
    db.commit()
    return RedirectResponse("/setores?ok=desativado", status_code=302)


@router.post("/{sid}/ativar")
async def ativar(request: Request, sid: int, db: Session = Depends(get_db), u=_ADMIN):
    s = _404(db, sid); s.is_active = True
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"setor:{sid}", details={"acao": "reativado"}, request=request)
    db.commit()
    return RedirectResponse("/setores?ok=ativado", status_code=302)
