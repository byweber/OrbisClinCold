"""
Router de Usuários — OrbisClin Cold.

Endpoints (prefixo /usuarios):
  GET    /              → lista usuários
  GET    /novo          → formulário
  POST   /novo          → cria usuário
  GET    /{id}/editar   → formulário preenchido
  POST   /{id}/editar   → atualiza role/setor/nome
  POST   /{id}/desativar → desativa conta
  POST   /{id}/ativar   → reativa conta
  POST   /{id}/reset-senha → gera nova senha aleatória e envia por e-mail

Acesso: ADMIN.
"""
from __future__ import annotations

import secrets
import string
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role
from app.core.database import get_db
from app.core.pwd import hash_password
from app.core.security import require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_ADMIN    = Depends(require_role(Role.ADMIN))

ROLES = [r.value for r in Role]


def _404(db, uid):
    from app.core.models import Usuario
    u = db.query(Usuario).filter(Usuario.id == uid).first()
    if not u:
        raise HTTPException(404, {"message": "Usuário não encontrado."})
    return u


def _ctx(user, **kw):
    return {"current_user": user, **kw}


def _senha_aleatoria(n: int = 12) -> str:
    alpha = string.ascii_letters + string.digits + "!@#$"
    return "".join(secrets.choice(alpha) for _ in range(n))


# ─── GET /usuarios ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def listar(request: Request, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Usuario
    usuarios = db.query(Usuario).order_by(Usuario.username).all()
    return templates.TemplateResponse(
        request, "admin/usuarios.html",
        _ctx(u, usuarios=usuarios),
    )


# ─── GET /usuarios/novo ───────────────────────────────────────────────────────

@router.get("/novo", response_class=HTMLResponse)
async def novo_page(request: Request, db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
    return templates.TemplateResponse(
        request, "admin/usuario_form.html",
        _ctx(u, usuario=None, setores=setores, roles=ROLES, erro=None),
    )


# ─── POST /usuarios/novo ──────────────────────────────────────────────────────

@router.post("/novo", response_class=HTMLResponse)
async def criar(
    request: Request,
    username:     str           = Form(...),
    nome_completo:str           = Form(""),
    email:        str           = Form(""),
    role:         str           = Form("VIEWER"),
    setor_id:     str           = Form(""),
    db: Session                 = Depends(get_db),
    u                           = _ADMIN,
):
    from app.core.models import Setor, Usuario

    username = username.strip().lower()
    if not username:
        setores = db.query(Setor).filter(Setor.is_active == True).all()  # noqa: E712
        return templates.TemplateResponse(
            request, "admin/usuario_form.html",
            _ctx(u, usuario=None, setores=setores, roles=ROLES,
                 erro="Username obrigatório."), status_code=400,
        )

    if db.query(Usuario).filter(Usuario.username == username).first():
        setores = db.query(Setor).filter(Setor.is_active == True).all()  # noqa: E712
        return templates.TemplateResponse(
            request, "admin/usuario_form.html",
            _ctx(u, usuario=None, setores=setores, roles=ROLES,
                 erro=f'Username "{username}" já existe.'), status_code=400,
        )

    senha = _senha_aleatoria()
    novo  = Usuario(
        username=username,
        hashed_password=hash_password(senha),
        nome_completo=nome_completo.strip() or None,
        email=email.strip() or None,
        role=role if role in ROLES else "VIEWER",
        setor_id=int(setor_id) if setor_id.strip() else None,
        must_change_password=True,
        is_active=True,
    )
    db.add(novo)
    db.flush()
    log_audit(db, username=u.username, action=AcaoAudit.CREATE.value,
              target=f"usuario:{novo.id}", details={"username": username, "role": role},
              request=request)
    db.commit()

    # Exibe senha temporária na tela (sem e-mail ainda — Fase 5 completa)
    return RedirectResponse(
        f"/usuarios?ok=criado&tmp_user={username}&tmp_pwd={senha}",
        status_code=302,
    )


# ─── GET /usuarios/{id}/editar ────────────────────────────────────────────────

@router.get("/{uid}/editar", response_class=HTMLResponse)
async def editar_page(request: Request, uid: int,
                      db: Session = Depends(get_db), u=_ADMIN):
    from app.core.models import Setor
    usuario = _404(db, uid)
    setores = db.query(Setor).filter(Setor.is_active == True).order_by(Setor.nome).all()  # noqa: E712
    return templates.TemplateResponse(
        request, "admin/usuario_form.html",
        _ctx(u, usuario=usuario, setores=setores, roles=ROLES, erro=None),
    )


# ─── POST /usuarios/{id}/editar ───────────────────────────────────────────────

@router.post("/{uid}/editar", response_class=HTMLResponse)
async def atualizar(
    request: Request,
    uid:          int,
    nome_completo:str = Form(""),
    email:        str = Form(""),
    role:         str = Form("VIEWER"),
    setor_id:     str = Form(""),
    db: Session       = Depends(get_db),
    u                 = _ADMIN,
):
    usuario = _404(db, uid)
    # Não permite rebaixar o próprio ADMIN
    if usuario.id == u.id and role != Role.ADMIN.value:
        return RedirectResponse("/usuarios?erro=Nao+pode+rebaixar+seu+proprio+usuario.", status_code=302)

    usuario.nome_completo = nome_completo.strip() or None
    usuario.email         = email.strip() or None
    usuario.role          = role if role in ROLES else "VIEWER"
    usuario.setor_id      = int(setor_id) if setor_id.strip() else None

    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"usuario:{uid}", details={"role": role}, request=request)
    db.commit()
    return RedirectResponse("/usuarios?ok=atualizado", status_code=302)


# ─── POST /usuarios/{id}/desativar ────────────────────────────────────────────

@router.post("/{uid}/desativar")
async def desativar(request: Request, uid: int,
                    db: Session = Depends(get_db), u=_ADMIN):
    usuario = _404(db, uid)
    if usuario.id == u.id:
        return RedirectResponse("/usuarios?erro=Nao+pode+desativar+seu+proprio+usuario.", status_code=302)
    usuario.is_active = False
    log_audit(db, username=u.username, action=AcaoAudit.DEACTIVATE.value,
              target=f"usuario:{uid}", details={"username": usuario.username}, request=request)
    db.commit()
    return RedirectResponse("/usuarios?ok=desativado", status_code=302)


# ─── POST /usuarios/{id}/ativar ───────────────────────────────────────────────

@router.post("/{uid}/ativar")
async def ativar(request: Request, uid: int,
                 db: Session = Depends(get_db), u=_ADMIN):
    usuario = _404(db, uid)
    usuario.is_active = True
    log_audit(db, username=u.username, action=AcaoAudit.UPDATE.value,
              target=f"usuario:{uid}", details={"acao": "reativado"}, request=request)
    db.commit()
    return RedirectResponse("/usuarios?ok=ativado", status_code=302)


# ─── POST /usuarios/{id}/reset-senha ─────────────────────────────────────────

@router.post("/{uid}/reset-senha")
async def reset_senha(request: Request, uid: int,
                      db: Session = Depends(get_db), u=_ADMIN):
    usuario = _404(db, uid)
    nova = _senha_aleatoria()
    usuario.hashed_password     = hash_password(nova)
    usuario.must_change_password = True
    log_audit(db, username=u.username, action=AcaoAudit.PASSWORD_CHANGE.value,
              target=f"usuario:{uid}", details={"acao": "reset por admin"}, request=request)
    db.commit()
    return RedirectResponse(
        f"/usuarios?ok=senha_resetada&tmp_user={usuario.username}&tmp_pwd={nova}",
        status_code=302,
    )
