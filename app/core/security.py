"""JWT, cookies, require_role, apply_setor_filter."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import Role
from app.core.database import get_db
from app.core.pwd import hash_password, verify_password  # noqa: F401 — re-exportado

logger   = logging.getLogger(__name__)
settings = get_settings()


def create_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Token inválido ou expirado."},
        )


def get_current_user(request: Request, db: Session = Depends(get_db)):
    from app.core.models import Usuario
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"message": "Não autenticado."})
    payload  = decode_token(token)
    username = payload.get("sub", "")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"message": "Token malformado."})
    user = db.query(Usuario).filter(
        Usuario.username == username, Usuario.is_active == True  # noqa: E712
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"message": "Usuário não encontrado ou inativo."})
    return user


def require_role(*roles: Role):
    def _check(user=Depends(get_current_user)):
        if user.role not in [r.value for r in roles]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail={"message": "Permissão insuficiente."})
        return user
    return _check


def apply_setor_filter(query, user, model):
    if user.role == Role.ADMIN.value:
        return query
    if user.setor_id is None:
        return query.filter(False)
    return query.filter(model.setor_id == user.setor_id)


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NAME, value=token,
        httponly=True, secure=settings.COOKIE_SECURE,
        samesite="lax", max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        httponly=True, secure=settings.COOKIE_SECURE, samesite="lax",
    )
