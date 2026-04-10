# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.models import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.JWTError:
        return None

def set_auth_cookie(response, token: str):
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Usuario:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user

def get_current_active_user(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if not current_user.ativo:
        raise HTTPException(status_code=403, detail="Usuário inativo")
    return current_user

def role_required(required_role: str):
    def dependency(current_user: Usuario = Depends(get_current_active_user)):
        if current_user.role != required_role and current_user.role != "ADMIN":
            raise HTTPException(status_code=403, detail="Permissão insuficiente")
        return current_user
    return dependency