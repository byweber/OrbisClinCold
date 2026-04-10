"""Router de autenticação."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import AcaoAudit
from app.core.database import get_db
from app.core.security import (
    clear_auth_cookie, create_token, get_current_user,
    hash_password, set_auth_cookie, verify_password,
)
from app.core.utils import log_audit

settings  = get_settings()
router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get(settings.COOKIE_NAME):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.core.models import Usuario
    _ERRO = "Usuário ou senha incorretos."
    user = db.query(Usuario).filter(
        Usuario.username == username.strip().lower(),
        Usuario.is_active == True,  # noqa: E712
    ).first()
    if not user or not verify_password(password, user.hashed_password):
        log_audit(db, username=username, action=AcaoAudit.LOGIN.value,
                  details={"sucesso": False}, request=request)
        db.commit()
        return templates.TemplateResponse(request, "login.html", {"erro": _ERRO}, status_code=401)

    user.last_login = datetime.now(timezone.utc)
    log_audit(db, username=user.username, action=AcaoAudit.LOGIN.value,
              details={"sucesso": True, "role": user.role}, request=request)
    db.commit()

    # 2FA TOTP: se habilitado, emite token pendente e redireciona para verificação
    if user.totp_enabled:
        pending = create_token({"sub": user.username}, expires_minutes=5)
        resp    = RedirectResponse("/auth/totp/verificar", status_code=302)
        resp.set_cookie("totp_pending", pending, httponly=True,
                        secure=settings.COOKIE_SECURE, samesite="lax", max_age=300)
        return resp

    token   = create_token({"sub": user.username, "role": user.role})
    destino = "/auth/trocar-senha" if user.must_change_password else "/"
    resp    = RedirectResponse(destino, status_code=302)
    set_auth_cookie(resp, token)
    return resp


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    log_audit(db, username=current_user.username, action=AcaoAudit.LOGOUT.value, request=request)
    db.commit()
    resp = RedirectResponse("/auth/login", status_code=302)
    clear_auth_cookie(resp)
    return resp


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id, "username": current_user.username,
        "nome_completo": current_user.nome_completo, "role": current_user.role,
        "setor_id": current_user.setor_id, "must_change_password": current_user.must_change_password,
        "totp_enabled": current_user.totp_enabled, "last_login": current_user.last_login,
    }


@router.get("/trocar-senha", response_class=HTMLResponse)
async def trocar_senha_page(request: Request, current_user=Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "trocar_senha.html",
        {"current_user": current_user, "erro": None, "sucesso": False},
    )


@router.post("/trocar-senha", response_class=HTMLResponse)
async def trocar_senha(
    request: Request,
    senha_atual: str = Form(...),
    nova_senha:  str = Form(...),
    confirmar:   str = Form(...),
    db: Session      = Depends(get_db),
    current_user     = Depends(get_current_user),
):
    ctx = {"current_user": current_user, "sucesso": False}

    if not verify_password(senha_atual, current_user.hashed_password):
        return templates.TemplateResponse(request, "trocar_senha.html",
                                          {**ctx, "erro": "Senha atual incorreta."}, status_code=400)
    if nova_senha != confirmar:
        return templates.TemplateResponse(request, "trocar_senha.html",
                                          {**ctx, "erro": "As senhas não coincidem."}, status_code=400)
    if len(nova_senha) < 8:
        return templates.TemplateResponse(request, "trocar_senha.html",
                                          {**ctx, "erro": "A nova senha deve ter pelo menos 8 caracteres."}, status_code=400)
    if nova_senha == senha_atual:
        return templates.TemplateResponse(request, "trocar_senha.html",
                                          {**ctx, "erro": "A nova senha deve ser diferente da atual."}, status_code=400)

    current_user.hashed_password     = hash_password(nova_senha)
    current_user.must_change_password = False
    log_audit(db, username=current_user.username,
              action=AcaoAudit.PASSWORD_CHANGE.value, request=request)
    db.commit()
    return templates.TemplateResponse(request, "trocar_senha.html",
                                      {**ctx, "erro": None, "sucesso": True})
