"""
Router de Relatórios — OrbisClin Cold.

Endpoints (prefixo /relatorios):
  GET  /              → tela de seleção de equipamento e período
  POST /gerar         → gera e devolve o PDF para download
  GET  /historico     → lista relatórios gerados (audit log)

Acesso: ADMIN (todos), OPERADOR (próprio setor).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role
from app.core.database import get_db
from app.core.security import apply_setor_filter, require_role

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_AUTH     = Depends(require_role(Role.ADMIN, Role.OPERADOR))

_TMPL_DIR = str(Path(__file__).resolve().parent.parent / "templates")


# ─── GET /relatorios ──────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def pagina_relatorios(
    request: Request,
    db: Session = Depends(get_db),
    u=_AUTH,
):
    from app.core.models import Equipamento

    q = apply_setor_filter(
        db.query(Equipamento).filter(Equipamento.is_active == True),  # noqa: E712
        u, Equipamento,
    )
    equipamentos = q.order_by(Equipamento.nome).all()

    # Período padrão: últimos 30 dias
    hoje   = datetime.now(timezone.utc).date()
    inicio = (hoje - timedelta(days=30)).isoformat()
    fim    = hoje.isoformat()

    return templates.TemplateResponse(request, "relatorios.html", {
        "current_user": u,
        "equipamentos": equipamentos,
        "data_inicio_default": inicio,
        "data_fim_default":    fim,
        "erro": None,
    })


# ─── POST /relatorios/gerar ───────────────────────────────────────────────────

@router.post("/gerar")
async def gerar_relatorio(
    request: Request,
    equipamento_id: int  = Form(...),
    data_inicio:    str  = Form(...),
    data_fim:       str  = Form(...),
    db: Session          = Depends(get_db),
    u                    = _AUTH,
):
    from app.core.models import Equipamento
    from app.core.relatorio import construir_dados, gerar_pdf
    from app.core.utils import log_audit

    # Valida acesso ao equipamento
    equip = db.query(Equipamento).filter(Equipamento.id == equipamento_id).first()
    if not equip:
        return RedirectResponse("/relatorios?erro=Equipamento+não+encontrado.", status_code=302)

    if u.role != Role.ADMIN.value and equip.setor_id != u.setor_id:
        return RedirectResponse("/relatorios?erro=Acesso+negado.", status_code=302)

    # Parse das datas
    try:
        tz   = timezone.utc
        ini  = datetime.fromisoformat(data_inicio).replace(tzinfo=tz)
        fim  = datetime.fromisoformat(data_fim).replace(hour=23, minute=59,
                                                         second=59, tzinfo=tz)
    except ValueError:
        return RedirectResponse("/relatorios?erro=Datas+inválidas.", status_code=302)

    if (fim - ini).days > 365:
        return RedirectResponse("/relatorios?erro=Período+máximo+de+365+dias.", status_code=302)

    # Gera os dados
    dados = construir_dados(
        db=db, equipamento_id=equipamento_id,
        data_inicio=ini, data_fim=fim,
        gerado_por=u.username,
    )
    if not dados:
        return RedirectResponse("/relatorios?erro=Sem+dados+para+o+período.", status_code=302)

    # Converte para PDF
    try:
        pdf = gerar_pdf(dados, _TMPL_DIR)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("WeasyPrint erro: %s", exc)
        return RedirectResponse(
            "/relatorios?erro=Erro+ao+gerar+PDF.+Verifique+se+WeasyPrint+está+instalado.",
            status_code=302,
        )

    # Audit log
    log_audit(
        db, username=u.username, action=AcaoAudit.REPORT_GENERATE.value,
        target=f"equipamento:{equipamento_id}",
        details={
            "periodo": f"{data_inicio} → {data_fim}",
            "leituras": len(dados.leituras),
            "alertas":  len(dados.alertas),
        },
        request=request,
    )
    db.commit()

    # Nome do arquivo
    nome_equip = equip.nome.replace(" ", "_")
    filename   = f"conformidade_{nome_equip}_{data_inicio}_{data_fim}.pdf"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
