# app/main.py
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from app.core.config import settings
from app.routers import auth, dashboard, admin, equipamentos, sensores, alertas, audit
from app.core.database import engine, Base, init_db
import logging

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Inicializa banco (cria tabelas e admin se não existir)
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

# SessionMiddleware necessário para CSRF
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    max_age=86400,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração CSRF
@CsrfProtect.load_config
def get_csrf_config():
    return [
        ("secret_key", settings.SECRET_KEY),
        ("cookie_secure", settings.COOKIE_SECURE),
        ("cookie_samesite", "lax"),
        ("token_location", "body"),
    ]

@app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
    logger.warning(f"CSRF validation failed: {exc.message}")
    return JSONResponse(status_code=403, content={"detail": "CSRF token inválido ou ausente."})

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Inclusão das rotas
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(equipamentos.router)
app.include_router(sensores.router)
app.include_router(alertas.router)
app.include_router(audit.router)

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/csrf-token")
async def get_csrf_token(csrf_protect: CsrfProtect = Depends()):
    csrf_token = csrf_protect.generate_csrf_token()
    return {"csrf_token": csrf_token}