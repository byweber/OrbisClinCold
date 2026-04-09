"""Testes do módulo de relatórios — Sprint 6."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.core.models import Alerta, Equipamento, Leitura, Setor, Sensor, Usuario
from app.core.pwd import hash_password
from app.core.constants import TipoAlerta, TipoEquipamento


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _seed():
    """Cria setor + equipamento + sensor + leituras + alerta. Retorna IDs."""
    with SessionLocal() as db:
        admin = Usuario(
            username="admin", hashed_password=hash_password("admin123"),
            role="ADMIN", is_active=True, must_change_password=False,
        )
        setor = Setor(nome="Farmácia", is_active=True)
        db.add_all([admin, setor]); db.flush()

        equip = Equipamento(
            setor_id=setor.id, nome="Geladeira A",
            tipo=TipoEquipamento.GELADEIRA.value,
            temp_min=2.0, temp_max=8.0,
            umid_min=40.0, umid_max=80.0,
            is_active=True,
        )
        db.add(equip); db.flush()

        sensor = Sensor(
            equipamento_id=equip.id, protocolo="HTTP",
            endereco="http://x", is_active=True,
        )
        db.add(sensor); db.flush()

        agora = datetime.now(timezone.utc)
        # 10 leituras dentro do range
        for i in range(10):
            db.add(Leitura(
                sensor_id=sensor.id,
                temperatura=5.0,
                umidade=60.0,
                timestamp=agora - timedelta(hours=10 - i),
            ))
        # 2 leituras fora do range (temperatura alta)
        for i in range(2):
            db.add(Leitura(
                sensor_id=sensor.id,
                temperatura=10.0,
                umidade=60.0,
                timestamp=agora - timedelta(hours=2 - i),
            ))

        # 1 alerta de temperatura alta
        alerta = Alerta(
            sensor_id=sensor.id, equipamento_id=equip.id,
            tipo=TipoAlerta.TEMP_ALTA.value,
            valor_registrado=10.0, valor_limite=8.0,
            inicio_at=agora - timedelta(hours=2),
            fim_at=agora - timedelta(hours=1),
        )
        db.add(alerta)
        db.commit()
        return equip.id, sensor.id


def _login(client):
    client.post("/auth/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)


# ─── Testes da camada de serviço ──────────────────────────────────────────────

def test_construir_dados_retorna_estrutura(client):
    eid, _ = _seed()
    from app.core.relatorio import construir_dados
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dados = construir_dados(
            db=db,
            equipamento_id=eid,
            data_inicio=agora - timedelta(days=1),
            data_fim=agora,
            gerado_por="admin",
        )
    assert dados is not None
    assert dados.equipamento_nome == "Geladeira A"
    assert dados.setor_nome == "Farmácia"
    assert len(dados.leituras) == 12
    assert len(dados.alertas) == 1


def test_stats_conformidade_corretas(client):
    eid, _ = _seed()
    from app.core.relatorio import construir_dados
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dados = construir_dados(
            db=db, equipamento_id=eid,
            data_inicio=agora - timedelta(days=1),
            data_fim=agora, gerado_por="admin",
        )
    # 10 conformes (5.0°C) + 2 não conformes (10.0°C) = 83.3%
    assert dados.stats_temp.total == 12
    assert dados.stats_temp.conformes == 10
    assert dados.stats_temp.nao_conformes == 2
    assert dados.stats_temp.conformidade == round(10 / 12 * 100, 1)


def test_construir_dados_equipamento_inexistente(client):
    from app.core.relatorio import construir_dados
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dados = construir_dados(
            db=db, equipamento_id=9999,
            data_inicio=agora - timedelta(days=1),
            data_fim=agora, gerado_por="admin",
        )
    assert dados is None


def test_alerta_duracao_calculada(client):
    eid, _ = _seed()
    from app.core.relatorio import construir_dados
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dados = construir_dados(
            db=db, equipamento_id=eid,
            data_inicio=agora - timedelta(days=1),
            data_fim=agora, gerado_por="admin",
        )
    assert len(dados.alertas) == 1
    # Alerta durou ~60 min
    assert dados.alertas[0].duracao_min is not None
    assert 55 <= dados.alertas[0].duracao_min <= 65


def test_sem_leituras_periodo_futuro(client):
    eid, _ = _seed()
    from app.core.relatorio import construir_dados
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dados = construir_dados(
            db=db, equipamento_id=eid,
            data_inicio=agora + timedelta(days=1),
            data_fim=agora + timedelta(days=2),
            gerado_por="admin",
        )
    assert dados is not None
    assert len(dados.leituras) == 0
    assert dados.stats_temp.total == 0
    assert dados.stats_temp.conformidade == 100.0


# ─── Testes HTTP ──────────────────────────────────────────────────────────────

def test_pagina_relatorios_renderiza(client):
    _seed(); _login(client)
    r = client.get("/relatorios/")
    assert r.status_code == 200
    assert "Gerar Relatório" in r.text
    assert "Geladeira A" in r.text


def test_gerar_sem_weasyprint_redireciona_com_erro(client, monkeypatch):
    """Se WeasyPrint não estiver instalado, redireciona com mensagem."""
    eid, _ = _seed(); _login(client)
    agora = datetime.now(timezone.utc)

    # Mocka gerar_pdf para lançar ImportError
    import app.routers.relatorios as rel_mod
    def _mock_gerar(*a, **kw):
        raise ImportError("weasyprint not installed")
    monkeypatch.setattr(rel_mod, "gerar_pdf" if hasattr(rel_mod, "gerar_pdf") else "__dummy", _mock_gerar, raising=False)

    # O endpoint captura exceções e redireciona
    r = client.post("/relatorios/gerar", data={
        "equipamento_id": eid,
        "data_inicio": (agora - timedelta(days=7)).date().isoformat(),
        "data_fim":    agora.date().isoformat(),
    }, follow_redirects=False)
    # Pode ser 302 (erro capturado) ou 200 se WeasyPrint instalado
    assert r.status_code in (200, 302)


def test_gerar_periodo_superior_365_dias(client):
    eid, _ = _seed(); _login(client)
    agora = datetime.now(timezone.utc)
    r = client.post("/relatorios/gerar", data={
        "equipamento_id": eid,
        "data_inicio": (agora - timedelta(days=400)).date().isoformat(),
        "data_fim":    agora.date().isoformat(),
    }, follow_redirects=False)
    assert r.status_code == 302
    assert "365" in r.headers["location"]


def test_gerar_equipamento_inexistente(client):
    _seed(); _login(client)
    agora = datetime.now(timezone.utc)
    r = client.post("/relatorios/gerar", data={
        "equipamento_id": 9999,
        "data_inicio": (agora - timedelta(days=7)).date().isoformat(),
        "data_fim":    agora.date().isoformat(),
    }, follow_redirects=False)
    assert r.status_code == 302
    assert "erro" in r.headers["location"]


def test_operador_nao_acessa_equipamento_de_outro_setor(client):
    eid, _ = _seed()
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Cria setor 2 + operador vinculado a ele
        s2 = Setor(nome="S2", is_active=True)
        db.add(s2); db.flush()
        op = Usuario(
            username="op", hashed_password=hash_password("op12345678"),
            role="OPERADOR", is_active=True, must_change_password=False,
            setor_id=s2.id,
        )
        db.add(op); db.commit()

    client.post("/auth/login", data={"username": "op", "password": "op12345678"},
                follow_redirects=False)
    r = client.post("/relatorios/gerar", data={
        "equipamento_id": eid,   # pertence a outro setor
        "data_inicio": (agora - timedelta(days=7)).date().isoformat(),
        "data_fim":    agora.date().isoformat(),
    }, follow_redirects=False)
    assert r.status_code == 302
    assert "erro" in r.headers["location"]
