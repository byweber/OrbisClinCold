"""Ponto de entrada — OrbisClin Cold."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
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

_TMPL_DIR    = str(Path(__file__).resolve().parent / "templates")
_STATIC_DIR  = str(Path(__file__).resolve().parent / "static")


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

# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers import auth, setores, equipamentos, sensores, alertas, dashboard  # noqa: E402

app.include_router(auth.router,         prefix="/auth",         tags=["auth"])
app.include_router(setores.router,      prefix="/setores",      tags=["setores"])
app.include_router(equipamentos.router, prefix="/equipamentos", tags=["equipamentos"])
app.include_router(sensores.router,     prefix="/sensores",     tags=["sensores"])
app.include_router(alertas.router,      prefix="/alertas",      tags=["alertas"])
app.include_router(dashboard.router,    prefix="",              tags=["dashboard"])


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
