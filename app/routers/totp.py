"""
Router TOTP 2FA — OrbisClin Cold.

Endpoints (prefixo /auth/totp):
  GET  /setup          → exibe QR Code e código secreto para configurar app autenticador
  POST /setup/confirmar → valida o primeiro código e ativa 2FA
  POST /desativar       → desativa 2FA (exige senha atual)
  GET  /verificar       → tela de verificação TOTP durante o login (step 2)
  POST /verificar       → valida código TOTP e emite token completo
"""
from __future__ import annotations

import io
from pathlib import Path

import pyotp
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import AcaoAudit
from app.core.database import get_db
from app.core.security import get_current_user, set_auth_cookie, create_token, verify_password
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
settings  = get_settings()

_TOTP_ISSUER  = "OrbisClin Cold"
_PENDING_COOKIE = "totp_pending"


def _provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=_TOTP_ISSUER)


# ─── GET /auth/totp/setup ─────────────────────────────────────────────────────

@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, current_user=Depends(get_current_user)):
    if current_user.totp_enabled:
        return RedirectResponse("/auth/totp/status", status_code=302)

    secret = pyotp.random_base32()
    uri    = _provisioning_uri(secret, current_user.username)

    try:
        import qrcode  # type: ignore
        import qrcode.image.svg as qrsvg
        factory = qrsvg.SvgPathImage
        img     = qrcode.make(uri, image_factory=factory)
        buf     = io.BytesIO()
        img.save(buf)
        qr_svg  = buf.getvalue().decode("utf-8")
    except ImportError:
        qr_svg = None  # template mostra URI manual

    return templates.TemplateResponse(request, "totp_setup.html", {
        "current_user": current_user,
        "secret":       secret,
        "uri":          uri,
        "qr_svg":       qr_svg,
        "erro":         None,
    })


# ─── POST /auth/totp/setup/confirmar ─────────────────────────────────────────

@router.post("/setup/confirmar", response_class=HTMLResponse)
async def setup_confirmar(
    request: Request,
    secret:  str = Form(...),
    codigo:  str = Form(...),
    db: Session  = Depends(get_db),
    current_user = Depends(get_current_user),
):
    totp = pyotp.TOTP(secret)
    if not totp.verify(codigo.strip(), valid_window=1):
        uri = _provisioning_uri(secret, current_user.username)
        return templates.TemplateResponse(request, "totp_setup.html", {
            "current_user": current_user,
            "secret": secret, "uri": uri, "qr_svg": None,
            "erro": "Código inválido. Verifique o horário do dispositivo e tente novamente.",
        }, status_code=400)

    current_user.totp_secret  = secret
    current_user.totp_enabled = True
    log_audit(db, username=current_user.username, action=AcaoAudit.TOTP_ENABLE.value,
              request=request)
    db.commit()
    return RedirectResponse("/auth/totp/status?ok=ativado", status_code=302)


# ─── GET /auth/totp/status ────────────────────────────────────────────────────

@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request, current_user=Depends(get_current_user)):
    return templates.TemplateResponse(request, "totp_status.html", {
        "current_user": current_user,
    })


# ─── POST /auth/totp/desativar ────────────────────────────────────────────────

@router.post("/desativar", response_class=HTMLResponse)
async def desativar(
    request: Request,
    senha_atual: str = Form(...),
    db: Session      = Depends(get_db),
    current_user     = Depends(get_current_user),
):
    if not verify_password(senha_atual, current_user.hashed_password):
        return templates.TemplateResponse(request, "totp_status.html", {
            "current_user": current_user,
            "erro": "Senha incorreta.",
        }, status_code=400)

    current_user.totp_enabled = False
    current_user.totp_secret  = None
    log_audit(db, username=current_user.username, action=AcaoAudit.TOTP_DISABLE.value,
              request=request)
    db.commit()
    return RedirectResponse("/auth/totp/status?ok=desativado", status_code=302)


# ─── GET /auth/totp/verificar ─────────────────────────────────────────────────

@router.get("/verificar", response_class=HTMLResponse)
async def verificar_page(request: Request):
    """
    Tela de verificação de código TOTP após login com senha correta.

    BUG CORRIGIDO: a versão anterior usava request.session (Starlette) que
    lança AssertionError quando SessionMiddleware não está instalado.
    O fluxo correto usa o cookie httponly 'totp_pending' (JWT de curta duração)
    setado em POST /auth/login após senha válida com TOTP habilitado.
    """
    if not request.cookies.get(_PENDING_COOKIE):
        # Cookie ausente → usuário não passou pela etapa de senha; redireciona
        return RedirectResponse("/auth/login", status_code=302)

    return templates.TemplateResponse(request, "totp_verificar.html", {
        "erro": None,
    })


# ─── POST /auth/totp/verificar ────────────────────────────────────────────────

@router.post("/verificar", response_class=HTMLResponse)
async def verificar(
    request: Request,
    codigo:  str = Form(...),
    db: Session  = Depends(get_db),
):
    """
    Valida código TOTP do step 2 do login.
    O username pendente fica em cookie httponly assinado (totp_pending).
    """
    from app.core.models import Usuario
    from app.core.security import decode_token

    pending_token = request.cookies.get(_PENDING_COOKIE)
    if not pending_token:
        return RedirectResponse("/auth/login", status_code=302)

    try:
        payload  = decode_token(pending_token)
        username = payload.get("sub", "")
    except HTTPException:
        return RedirectResponse("/auth/login", status_code=302)

    user = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.is_active == True,  # noqa: E712
    ).first()
    if not user or not user.totp_enabled or not user.totp_secret:
        return RedirectResponse("/auth/login", status_code=302)

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(codigo.strip(), valid_window=1):
        return templates.TemplateResponse(request, "totp_verificar.html", {
            "erro": "Código inválido ou expirado. Tente novamente.",
        }, status_code=401)

    # TOTP OK → emite token completo e limpa cookie pendente
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    log_audit(db, username=user.username, action=AcaoAudit.LOGIN.value,
              details={"sucesso": True, "totp": True, "role": user.role}, request=request)
    db.commit()

    token    = create_token({"sub": user.username, "role": user.role})
    destino  = "/auth/trocar-senha" if user.must_change_password else "/"
    response = RedirectResponse(destino, status_code=302)
    set_auth_cookie(response, token)
    response.delete_cookie(_PENDING_COOKIE, httponly=True, samesite="lax")
    return response