"""
Ponto de entrada — OrbisClin Cold.
Sem CSRF, sem SessionMiddleware, sem imports circulares.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.core.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger   = logging.getLogger(__name__)
settings = get_settings()

# Caminhos absolutos — funcionam independente do cwd (PyCharm, terminal, testes)
_BASE_DIR   = Path(__file__).resolve().parent
_TMPL_DIR   = str(_BASE_DIR / "templates")
_STATIC_DIR = str(_BASE_DIR / "static")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Iniciando %s na porta %s", settings.APP_NAME, settings.PORT)
    init_db()
    logger.info("Banco inicializado")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

templates = Jinja2Templates(directory=_TMPL_DIR)
templates.env.globals["now"] = datetime.now(timezone.utc)

# ── Routers ────────────────────────────────────────────────────────────────────
from app.routers import (  # noqa: E402
    auth, totp, setores, equipamentos, sensores,
    alertas, dashboard, usuarios, relatorios, audit, export_csv,
)

app.include_router(auth.router,         prefix="/auth",         tags=["auth"])
app.include_router(totp.router,         prefix="/auth/totp",    tags=["totp"])
app.include_router(setores.router,      prefix="/setores",      tags=["setores"])
app.include_router(equipamentos.router, prefix="/equipamentos", tags=["equipamentos"])
app.include_router(sensores.router,     prefix="/sensores",     tags=["sensores"])
app.include_router(alertas.router,      prefix="/alertas",      tags=["alertas"])
app.include_router(usuarios.router,     prefix="/usuarios",     tags=["usuarios"])
app.include_router(relatorios.router,   prefix="/relatorios",   tags=["relatorios"])
app.include_router(audit.router,        prefix="/audit",        tags=["audit"])
app.include_router(export_csv.router,   prefix="/export",       tags=["export"])
app.include_router(dashboard.router,    prefix="",              tags=["dashboard"])


# ── Tratamento global de erros de autenticação ────────────────────────────────
from fastapi import Request as _Request                             # noqa: E402
from fastapi.responses import RedirectResponse as _RR              # noqa: E402
from fastapi.exceptions import HTTPException as _HTTPEx            # noqa: E402


@app.exception_handler(_HTTPEx)
async def _auth_redirect(request: _Request, exc: _HTTPEx):
    """
    401 em rotas HTML → redireciona para login.
    401/403 em rotas /api/* ou /health → devolve JSON.
    """
    path = request.url.path
    # Rotas que devem retornar JSON mesmo sem autenticação
    JSON_PREFIXES = ("/api/", "/alertas/api", "/sensores/api",
                     "/equipamentos/api", "/sensores/api",
                     "/audit/export", "/health",
                     "/auth/me", "/auth/logout", "/auth/trocar-senha")
    is_api = any(path.startswith(p) for p in JSON_PREFIXES)
    if exc.status_code == 401 and not is_api:
        return _RR(f"/auth/login?next={path}", status_code=302)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
