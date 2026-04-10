"""
Router de Exportação CSV — OrbisClin Cold.

Endpoints (prefixo /export):
  GET  /              → tela de seleção
  GET  /leituras      → download CSV de leituras
  GET  /alertas       → download CSV de alertas

Acesso: ADMIN (todos) · OPERADOR (próprio setor).
Limite: 365 dias por exportação.
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
from sqlalchemy.orm import Session

from app.core.constants import AcaoAudit, Role
from app.core.database import get_db
from app.core.security import apply_setor_filter, require_role
from app.core.utils import log_audit

router    = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)
_AUTH = Depends(require_role(Role.ADMIN, Role.OPERADOR))

_MAX_DIAS = 365


def _parse_periodo(data_inicio: Optional[str], data_fim: Optional[str]):
    """Converte strings de data para datetime UTC. Retorna (ini, fim) ou lança ValueError."""
    tz  = timezone.utc
    hoje = datetime.now(tz).date()

    ini_str = data_inicio or (hoje - timedelta(days=30)).isoformat()
    fim_str = data_fim    or hoje.isoformat()

    ini = datetime.fromisoformat(ini_str).replace(tzinfo=tz)
    fim = datetime.fromisoformat(fim_str).replace(
        hour=23, minute=59, second=59, tzinfo=tz
    )
    if (fim - ini).days > _MAX_DIAS:
        raise ValueError(f"Período máximo: {_MAX_DIAS} dias.")
    if ini > fim:
        raise ValueError("Data início deve ser anterior à data fim.")
    return ini, fim


# ── GET /export ────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def pagina_export(
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

    hoje  = datetime.now(timezone.utc).date()
    ini30 = (hoje - timedelta(days=30)).isoformat()

    return templates.TemplateResponse(request, "export.html", {
        "current_user":       u,
        "equipamentos":       equipamentos,
        "data_inicio_default": ini30,
        "data_fim_default":    hoje.isoformat(),
        "erro":               request.query_params.get("erro"),
    })


# ── GET /export/leituras ───────────────────────────────────────────────────────

@router.get("/leituras")
async def exportar_leituras(
    equipamento_id: int           = Query(...),
    sensor_id:      Optional[int] = Query(None),
    data_inicio:    Optional[str] = Query(None),
    data_fim:       Optional[str] = Query(None),
    db: Session                   = Depends(get_db),
    u                             = _AUTH,
):
    from app.core.models import Equipamento, Leitura, Sensor

    # Valida acesso
    equip = db.query(Equipamento).filter(Equipamento.id == equipamento_id).first()
    if not equip:
        return Response("Equipamento não encontrado.", status_code=404)
    if u.role != Role.ADMIN.value and equip.setor_id != u.setor_id:
        return Response("Acesso negado.", status_code=403)

    # Período
    try:
        ini, fim = _parse_periodo(data_inicio, data_fim)
    except ValueError as e:
        return Response(str(e), status_code=400)

    # Sensores do equipamento
    q_s = db.query(Sensor).filter(Sensor.equipamento_id == equipamento_id)
    if sensor_id:
        q_s = q_s.filter(Sensor.id == sensor_id)
    sensor_ids = [s.id for s in q_s.all()]

    # Leituras
    leituras = (
        db.query(Leitura)
        .filter(
            Leitura.sensor_id.in_(sensor_ids),
            Leitura.timestamp >= ini,
            Leitura.timestamp <= fim,
        )
        .order_by(Leitura.timestamp.asc())
        .all()
    )

    # Mapa sensor_id → nome
    sensores = {s.id: (s.nome or f"Sensor #{s.id}")
                for s in db.query(Sensor).filter(Sensor.id.in_(sensor_ids)).all()}

    # Gera CSV
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "id", "data_hora", "sensor_id", "sensor_nome",
        "equipamento", "setor",
        "temperatura_C", "umidade_pct",
        "temp_ok", "umid_ok",
    ])

    def _ok_temp(v):
        if v is None: return ""
        if equip.temp_min is not None and v < equip.temp_min: return "NAO"
        if equip.temp_max is not None and v > equip.temp_max: return "NAO"
        return "OK"

    def _ok_umid(v):
        if v is None: return ""
        if equip.umid_min is not None and v < equip.umid_min: return "NAO"
        if equip.umid_max is not None and v > equip.umid_max: return "NAO"
        return "OK"

    for l in leituras:
        w.writerow([
            l.id,
            l.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
            l.sensor_id,
            sensores.get(l.sensor_id, ""),
            equip.nome,
            equip.setor.nome if equip.setor else "",
            f"{l.temperatura:.2f}" if l.temperatura is not None else "",
            f"{l.umidade:.2f}"     if l.umidade     is not None else "",
            _ok_temp(l.temperatura),
            _ok_umid(l.umidade),
        ])

    # Audit log
    log_audit(
        db, username=u.username, action=AcaoAudit.EXPORT_CSV.value,
        target=f"equipamento:{equipamento_id}",
        details={
            "tipo": "leituras",
            "periodo": f"{data_inicio} → {data_fim}",
            "registros": len(leituras),
        },
    )
    db.commit()

    nome = (
        f"leituras_{equip.nome.replace(' ', '_')}"
        f"_{(ini.date())}_{(fim.date())}.csv"
    )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8-sig",  # utf-8-sig = BOM para Excel
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ── GET /export/alertas ────────────────────────────────────────────────────────

@router.get("/alertas")
async def exportar_alertas(
    equipamento_id: int           = Query(...),
    data_inicio:    Optional[str] = Query(None),
    data_fim:       Optional[str] = Query(None),
    tipo:           Optional[str] = Query(None),
    db: Session                   = Depends(get_db),
    u                             = _AUTH,
):
    from app.core.models import Alerta, Equipamento

    equip = db.query(Equipamento).filter(Equipamento.id == equipamento_id).first()
    if not equip:
        return Response("Equipamento não encontrado.", status_code=404)
    if u.role != Role.ADMIN.value and equip.setor_id != u.setor_id:
        return Response("Acesso negado.", status_code=403)

    try:
        ini, fim = _parse_periodo(data_inicio, data_fim)
    except ValueError as e:
        return Response(str(e), status_code=400)

    q = db.query(Alerta).filter(
        Alerta.equipamento_id == equipamento_id,
        Alerta.inicio_at >= ini,
        Alerta.inicio_at <= fim,
    )
    if tipo:
        q = q.filter(Alerta.tipo == tipo)
    alertas = q.order_by(Alerta.inicio_at.asc()).all()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "id", "tipo", "equipamento", "setor",
        "inicio", "fim", "duracao_min",
        "valor_registrado", "valor_limite",
        "nivel_escalonamento",
        "reconhecido_por", "reconhecido_em",
        "status",
    ])

    for a in alertas:
        dur = ""
        if a.fim_at:
            dur = f"{(a.fim_at - a.inicio_at).total_seconds() / 60:.1f}"
        status = "ATIVO" if a.fim_at is None else "ENCERRADO"

        w.writerow([
            a.id,
            a.tipo,
            equip.nome,
            equip.setor.nome if equip.setor else "",
            a.inicio_at.strftime("%d/%m/%Y %H:%M:%S"),
            a.fim_at.strftime("%d/%m/%Y %H:%M:%S") if a.fim_at else "",
            dur,
            f"{a.valor_registrado:.2f}" if a.valor_registrado is not None else "",
            f"{a.valor_limite:.2f}"     if a.valor_limite     is not None else "",
            a.nivel_escalonamento,
            a.reconhecido_por  or "",
            a.reconhecido_at.strftime("%d/%m/%Y %H:%M:%S") if a.reconhecido_at else "",
            status,
        ])

    log_audit(
        db, username=u.username, action=AcaoAudit.EXPORT_CSV.value,
        target=f"equipamento:{equipamento_id}",
        details={
            "tipo": "alertas",
            "periodo": f"{data_inicio} → {data_fim}",
            "registros": len(alertas),
        },
    )
    db.commit()

    nome = (
        f"alertas_{equip.nome.replace(' ', '_')}"
        f"_{ini.date()}_{fim.date()}.csv"
    )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
