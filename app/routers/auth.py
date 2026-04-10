# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, set_auth_cookie, get_current_active_user
from app.core.models import Usuario
from fastapi_csrf_protect import CsrfProtect

router = APIRouter(prefix="/auth", tags=["autenticação"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, csrf_protect: CsrfProtect = Depends()):
    csrf_token = csrf_protect.generate_csrf_token()
    return templates.TemplateResponse("auth/login.html", {"request": request, "csrf_token": csrf_token})

@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_protect: CsrfProtect = Depends(),
    db: Session = Depends(get_db)
):
    await csrf_protect.validate_csrf(request)
    user = db.query(Usuario).filter(func.lower(Usuario.username) == username.strip().lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        csrf_token = csrf_protect.generate_csrf_token()
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Credenciais inválidas", "csrf_token": csrf_token},
            status_code=401
        )
    if not user.ativo:
        csrf_token = csrf_protect.generate_csrf_token()
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Usuário inativo", "csrf_token": csrf_token},
            status_code=403
        )
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    response = RedirectResponse(url="/dashboard", status_code=302)
    set_auth_cookie(response, access_token)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("cold_session")
    return response

@router.get("/me")
async def read_users_me(current_user: Usuario = Depends(get_current_active_user)):
    return current_user