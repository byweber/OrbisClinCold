"""
Router de Audit Log — OrbisClin Cold.

Endpoints (prefixo /audit):
  GET  /          → listagem paginada com filtros
  GET  /export    → download CSV de todos os registros filtrados

Acesso: ADMIN apenas (logs contêm dados sensíveis de operação).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role
from app.core.database import get_db
from app.core.security import require_role

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_ADMIN    = Depends(require_role(Role.ADMIN))

POR_PAGINA  = 50
ACOES_LISTA = [a.value for a in AcaoAudit]


def _aplicar_filtros(q, username, action, target, data_inicio, data_fim):
    from app.core.models import AuditLog
    if username:
        q = q.filter(AuditLog.username.ilike(f"%{username}%"))
    if action:
        q = q.filter(AuditLog.action == action)
    if target:
        q = q.filter(AuditLog.target.ilike(f"%{target}%"))
    if data_inicio:
        try:
            ini = datetime.fromisoformat(data_inicio).replace(tzinfo=timezone.utc)
            q   = q.filter(AuditLog.created_at >= ini)
        except ValueError:
            pass
    if data_fim:
        try:
            fim = datetime.fromisoformat(data_fim).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            q = q.filter(AuditLog.created_at <= fim)
        except ValueError:
            pass
    return q


# ─── GET /audit ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def listar(
    request:     Request,
    username:    Optional[str] = Query(None),
    action:      Optional[str] = Query(None),
    target:      Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim:    Optional[str] = Query(None),
    pagina:      int           = Query(1, ge=1),
    db: Session                = Depends(get_db),
    u                          = _ADMIN,
):
    from app.core.models import AuditLog

    q = db.query(AuditLog)
    q = _aplicar_filtros(q, username, action, target, data_inicio, data_fim)
    q = q.order_by(AuditLog.created_at.desc())

    total     = q.count()
    total_pag = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina    = min(pagina, total_pag)
    registros = q.offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()

    # Período padrão para os campos de filtro
    hoje  = datetime.now(timezone.utc).date().isoformat()
    ini30 = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    return templates.TemplateResponse(request, "audit.html", {
        "current_user":   u,
        "registros":      registros,
        "total":          total,
        "pagina":         pagina,
        "total_paginas":  total_pag,
        "por_pagina":     POR_PAGINA,
        # Filtros ativos
        "f_username":     username    or "",
        "f_action":       action      or "",
        "f_target":       target      or "",
        "f_data_inicio":  data_inicio or ini30,
        "f_data_fim":     data_fim    or hoje,
        "acoes_lista":    ACOES_LISTA,
    })


# ─── GET /audit/export ────────────────────────────────────────────────────────

@router.get("/export")
async def exportar_csv(
    username:    Optional[str] = Query(None),
    action:      Optional[str] = Query(None),
    target:      Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim:    Optional[str] = Query(None),
    db: Session                = Depends(get_db),
    u                          = _ADMIN,
):
    from app.core.models import AuditLog

    q = db.query(AuditLog)
    q = _aplicar_filtros(q, username, action, target, data_inicio, data_fim)
    q = q.order_by(AuditLog.created_at.desc())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "data_hora", "usuario", "acao", "alvo",
                     "ip_address", "detalhes"])
    for r in q.all():
        writer.writerow([
            r.id,
            r.created_at.strftime("%d/%m/%Y %H:%M:%S"),
            r.username,
            r.action,
            r.target or "",
            r.ip_address or "",
            str(r.details or ""),
        ])

    nome = f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
