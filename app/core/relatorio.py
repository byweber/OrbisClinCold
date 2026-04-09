"""
Geração de relatórios de conformidade em PDF — OrbisClin Cold.
RDC 430/2020 ANVISA.

Usa WeasyPrint para converter HTML → PDF.
A lógica de dados fica aqui; o template HTML fica em
app/templates/relatorio_conformidade.html.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─── Estruturas de dados do relatório ────────────────────────────────────────

@dataclass
class LeituraRow:
    timestamp:    datetime
    temperatura:  Optional[float]
    umidade:      Optional[float]
    temp_ok:      bool   # True = dentro do range
    umid_ok:      bool


@dataclass
class AlertaRow:
    tipo:             str
    inicio:           datetime
    fim:              Optional[datetime]
    valor_registrado: Optional[float]
    valor_limite:     Optional[float]
    duracao_min:      Optional[float]   # None = ainda ativo
    reconhecido_por:  Optional[str]


@dataclass
class EstatisticasTemp:
    total:        int   = 0
    conformes:    int   = 0
    nao_conformes:int   = 0
    media:        Optional[float] = None
    minima:       Optional[float] = None
    maxima:       Optional[float] = None
    conformidade: float = 100.0   # percentual


@dataclass
class DadosRelatorio:
    # Identificação
    equipamento_nome: str
    equipamento_tipo: str
    setor_nome:       str
    patrimonio:       Optional[str]
    fabricante:       Optional[str]
    modelo:           Optional[str]

    # Limites
    temp_min:   Optional[float]
    temp_max:   Optional[float]
    umid_min:   Optional[float]
    umid_max:   Optional[float]

    # Período
    data_inicio: datetime
    data_fim:    datetime
    gerado_em:   datetime
    gerado_por:  str

    # Dados
    leituras:   list[LeituraRow]  = field(default_factory=list)
    alertas:    list[AlertaRow]   = field(default_factory=list)
    stats_temp: EstatisticasTemp  = field(default_factory=EstatisticasTemp)
    stats_umid: EstatisticasTemp  = field(default_factory=EstatisticasTemp)

    # Resumo
    total_alertas:       int   = 0
    alertas_temperatura: int   = 0
    alertas_umidade:     int   = 0
    alertas_offline:     int   = 0


# ─── Construção dos dados ─────────────────────────────────────────────────────

def _calc_stats(valores: list[float], v_min: Optional[float],
                v_max: Optional[float]) -> EstatisticasTemp:
    stats = EstatisticasTemp()
    if not valores:
        return stats
    stats.total   = len(valores)
    stats.minima  = round(min(valores), 2)
    stats.maxima  = round(max(valores), 2)
    stats.media   = round(statistics.mean(valores), 2)

    def _ok(v: float) -> bool:
        if v_min is not None and v < v_min: return False
        if v_max is not None and v > v_max: return False
        return True

    stats.conformes     = sum(1 for v in valores if _ok(v))
    stats.nao_conformes = stats.total - stats.conformes
    stats.conformidade  = round(stats.conformes / stats.total * 100, 1)
    return stats


def construir_dados(
    db: Session,
    equipamento_id: int,
    data_inicio: datetime,
    data_fim:    datetime,
    gerado_por:  str,
    sensor_id:   Optional[int] = None,
    max_leituras: int = 2000,
) -> Optional[DadosRelatorio]:
    """
    Coleta leituras e alertas do período e retorna DadosRelatorio.
    Retorna None se o equipamento não for encontrado.

    max_leituras: limita o número de linhas na tabela do PDF
    (evitar PDFs de centenas de páginas para períodos longos).
    Se houver mais leituras, agrega por hora.
    """
    from app.core.models import Alerta, Equipamento, Leitura, Sensor

    equip = db.query(Equipamento).filter(Equipamento.id == equipamento_id).first()
    if not equip:
        return None

    setor_nome = equip.setor.nome if equip.setor else "—"

    # ── Sensores do equipamento ───────────────────────────────────────────────
    q_sensor = db.query(Sensor).filter(Sensor.equipamento_id == equipamento_id)
    if sensor_id:
        q_sensor = q_sensor.filter(Sensor.id == sensor_id)
    sensores = q_sensor.all()
    sensor_ids = [s.id for s in sensores]

    # ── Leituras ──────────────────────────────────────────────────────────────
    leituras_db = (
        db.query(Leitura)
        .filter(
            Leitura.sensor_id.in_(sensor_ids),
            Leitura.timestamp >= data_inicio,
            Leitura.timestamp <= data_fim,
        )
        .order_by(Leitura.timestamp.asc())
        .all()
    )

    # Agrega se muitas leituras (amostra de hora em hora)
    if len(leituras_db) > max_leituras:
        step = max(1, len(leituras_db) // max_leituras)
        leituras_db = leituras_db[::step]

    def _temp_ok(v: Optional[float]) -> bool:
        if v is None: return True
        if equip.temp_min is not None and v < equip.temp_min: return False
        if equip.temp_max is not None and v > equip.temp_max: return False
        return True

    def _umid_ok(v: Optional[float]) -> bool:
        if v is None: return True
        if equip.umid_min is not None and v < equip.umid_min: return False
        if equip.umid_max is not None and v > equip.umid_max: return False
        return True

    leituras_rows = [
        LeituraRow(
            timestamp   = l.timestamp,
            temperatura = l.temperatura,
            umidade     = l.umidade,
            temp_ok     = _temp_ok(l.temperatura),
            umid_ok     = _umid_ok(l.umidade),
        )
        for l in leituras_db
    ]

    # Estatísticas
    temps = [l.temperatura for l in leituras_db if l.temperatura is not None]
    umids = [l.umidade     for l in leituras_db if l.umidade     is not None]
    stats_t = _calc_stats(temps, equip.temp_min, equip.temp_max)
    stats_u = _calc_stats(umids, equip.umid_min, equip.umid_max)

    # ── Alertas ───────────────────────────────────────────────────────────────
    alertas_db = (
        db.query(Alerta)
        .filter(
            Alerta.equipamento_id == equipamento_id,
            Alerta.inicio_at >= data_inicio,
            Alerta.inicio_at <= data_fim,
        )
        .order_by(Alerta.inicio_at.asc())
        .all()
    )

    alertas_rows = []
    for a in alertas_db:
        dur = None
        if a.fim_at:
            dur = round((a.fim_at - a.inicio_at).total_seconds() / 60, 1)
        alertas_rows.append(AlertaRow(
            tipo=a.tipo, inicio=a.inicio_at, fim=a.fim_at,
            valor_registrado=a.valor_registrado, valor_limite=a.valor_limite,
            duracao_min=dur, reconhecido_por=a.reconhecido_por,
        ))

    total_al  = len(alertas_rows)
    al_temp   = sum(1 for a in alertas_rows if "TEMP" in a.tipo)
    al_umid   = sum(1 for a in alertas_rows if "UMID" in a.tipo)
    al_off    = sum(1 for a in alertas_rows if a.tipo == "OFFLINE")

    return DadosRelatorio(
        equipamento_nome=equip.nome,
        equipamento_tipo=equip.tipo,
        setor_nome=setor_nome,
        patrimonio=equip.patrimonio,
        fabricante=equip.fabricante,
        modelo=equip.modelo,
        temp_min=equip.temp_min, temp_max=equip.temp_max,
        umid_min=equip.umid_min, umid_max=equip.umid_max,
        data_inicio=data_inicio, data_fim=data_fim,
        gerado_em=datetime.now(timezone.utc),
        gerado_por=gerado_por,
        leituras=leituras_rows,
        alertas=alertas_rows,
        stats_temp=stats_t,
        stats_umid=stats_u,
        total_alertas=total_al,
        alertas_temperatura=al_temp,
        alertas_umidade=al_umid,
        alertas_offline=al_off,
    )


# ─── Renderização HTML → PDF ──────────────────────────────────────────────────

def gerar_pdf(dados: DadosRelatorio, template_dir: str) -> bytes:
    """
    Renderiza o template HTML com os dados e converte para PDF via WeasyPrint.
    Retorna os bytes do PDF gerado.
    """
    from jinja2 import Environment, FileSystemLoader
    from weasyprint import HTML

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )
    env.filters["fmt_temp"] = lambda v: f"{v:.1f}°C" if v is not None else "—"
    env.filters["fmt_umid"] = lambda v: f"{v:.1f}%" if v is not None else "—"
    env.filters["fmt_dt"]   = lambda v: v.strftime("%d/%m/%Y %H:%M") if v else "—"
    env.filters["fmt_date"] = lambda v: v.strftime("%d/%m/%Y") if v else "—"

    tmpl = env.get_template("relatorio_conformidade.html")
    html_str = tmpl.render(r=dados)

    pdf_bytes = HTML(string=html_str).write_pdf()
    logger.info(
        "PDF gerado: %s | período %s→%s | leituras=%d alertas=%d",
        dados.equipamento_nome,
        dados.data_inicio.strftime("%d/%m/%Y"),
        dados.data_fim.strftime("%d/%m/%Y"),
        len(dados.leituras), len(dados.alertas),
    )
    return pdf_bytes
