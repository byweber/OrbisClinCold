"""Testes de exportação CSV — leituras e alertas."""
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.models import (
    Alerta, Equipamento, Leitura, Setor, Sensor, Usuario,
)
from app.core.pwd import hash_password
from app.core.constants import TipoAlerta, TipoEquipamento


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed():
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        u = Usuario(username="admin", hashed_password=hash_password("admin123"),
                    role="ADMIN", is_active=True, must_change_password=False)
        s = Setor(nome="Farm", is_active=True)
        db.add_all([u, s]); db.flush()

        e = Equipamento(setor_id=s.id, nome="Gel A",
                        tipo=TipoEquipamento.GELADEIRA.value,
                        temp_min=2.0, temp_max=8.0,
                        umid_min=40.0, umid_max=80.0, is_active=True)
        db.add(e); db.flush()

        sen = Sensor(equipamento_id=e.id, protocolo="HTTP",
                     endereco="http://x", is_active=True)
        db.add(sen); db.flush()

        # 5 leituras OK, 2 fora do range
        for i in range(5):
            db.add(Leitura(sensor_id=sen.id, temperatura=5.0, umidade=60.0,
                            timestamp=agora - timedelta(hours=5 - i)))
        db.add(Leitura(sensor_id=sen.id, temperatura=10.0, umidade=60.0,
                        timestamp=agora - timedelta(minutes=30)))
        db.add(Leitura(sensor_id=sen.id, temperatura=1.0,  umidade=60.0,
                        timestamp=agora - timedelta(minutes=15)))

        # 2 alertas
        db.add(Alerta(sensor_id=sen.id, equipamento_id=e.id,
                      tipo=TipoAlerta.TEMP_ALTA.value,
                      valor_registrado=10.0, valor_limite=8.0,
                      inicio_at=agora - timedelta(hours=1),
                      fim_at=agora - timedelta(minutes=30),
                      reconhecido_por="admin"))
        db.add(Alerta(sensor_id=sen.id, equipamento_id=e.id,
                      tipo=TipoAlerta.TEMP_BAIXA.value,
                      valor_registrado=1.0, valor_limite=2.0,
                      inicio_at=agora - timedelta(minutes=20)))
        db.commit()
        return e.id, sen.id


def _login(client):
    client.post("/auth/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)


def _qs(eid, extra=""):
    agora = datetime.now(timezone.utc)
    ini   = (agora - timedelta(days=1)).date().isoformat()
    fim   = agora.date().isoformat()
    return f"equipamento_id={eid}&data_inicio={ini}&data_fim={fim}{extra}"


# ── Tela de seleção ───────────────────────────────────────────────────────────

def test_pagina_export_renderiza(client):
    _seed(); _login(client)
    r = client.get("/export/")
    assert r.status_code == 200
    assert "Exportar" in r.text
    assert "Gel A" in r.text


# ── Leituras ──────────────────────────────────────────────────────────────────

def test_export_leituras_retorna_csv(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(eid)}")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "leituras_Gel" in r.headers["content-disposition"]


def test_export_leituras_colunas_corretas(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(eid)}")
    linhas = r.text.strip().split("\n")
    cabecalho = linhas[0]
    assert "temperatura_C" in cabecalho
    assert "umidade_pct"   in cabecalho
    assert "temp_ok"       in cabecalho
    assert "sensor_nome"   in cabecalho


def test_export_leituras_quantidade(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(eid)}")
    linhas = [l for l in r.text.strip().split("\n") if l.strip()]
    # cabeçalho + 7 leituras
    assert len(linhas) == 8


def test_export_leituras_conformidade(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(eid)}")
    linhas = r.text.strip().split("\n")[1:]  # remove cabeçalho
    oks  = [l for l in linhas if ",OK,"  in l or l.endswith(",OK")]
    naos = [l for l in linhas if ",NAO," in l or l.endswith(",NAO")]
    assert len(oks)  >= 5
    assert len(naos) >= 2


def test_export_leituras_filtro_sensor(client):
    eid, sid = _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(eid, f'&sensor_id={sid}')}")
    assert r.status_code == 200
    linhas = r.text.strip().split("\n")
    assert len(linhas) == 8  # cabeçalho + 7


def test_export_leituras_equipamento_inexistente(client):
    _seed(); _login(client)
    r = client.get(f"/export/leituras?{_qs(9999)}")
    assert r.status_code == 404


def test_export_leituras_periodo_excede_365(client):
    eid, _ = _seed(); _login(client)
    r = client.get(
        f"/export/leituras?equipamento_id={eid}"
        f"&data_inicio=2020-01-01&data_fim=2025-01-01"
    )
    assert r.status_code == 400


def test_export_leituras_sem_auth(client):
    eid, _ = _seed()
    r = client.get(f"/export/leituras?{_qs(eid)}", follow_redirects=False)
    assert r.status_code in (302, 401)


# ── Alertas ───────────────────────────────────────────────────────────────────

def test_export_alertas_retorna_csv(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/alertas?{_qs(eid)}")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "alertas_Gel" in r.headers["content-disposition"]


def test_export_alertas_colunas_corretas(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/alertas?{_qs(eid)}")
    cab = r.text.strip().split("\n")[0]
    assert "duracao_min"          in cab
    assert "nivel_escalonamento"  in cab
    assert "reconhecido_por"      in cab
    assert "status"               in cab


def test_export_alertas_quantidade(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/alertas?{_qs(eid)}")
    linhas = [l for l in r.text.strip().split("\n") if l.strip()]
    assert len(linhas) == 3  # cabeçalho + 2 alertas


def test_export_alertas_filtro_tipo(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/alertas?{_qs(eid, '&tipo=TEMP_ALTA')}")
    linhas = [l for l in r.text.strip().split("\n") if l.strip()]
    assert len(linhas) == 2  # cabeçalho + 1 alerta TEMP_ALTA


def test_export_alertas_status_correto(client):
    eid, _ = _seed(); _login(client)
    r = client.get(f"/export/alertas?{_qs(eid)}")
    texto = r.text
    assert "ENCERRADO" in texto   # alerta com fim_at
    assert "ATIVO"     in texto   # alerta sem fim_at


def test_export_alertas_acesso_operador_outro_setor(client):
    eid, _ = _seed()
    with SessionLocal() as db:
        from app.core.models import Setor
        s2 = Setor(nome="S2", is_active=True)
        db.add(s2); db.flush()
        db.add(Usuario(username="op", hashed_password=hash_password("op12345678"),
                       role="OPERADOR", is_active=True, must_change_password=False,
                       setor_id=s2.id))
        db.commit()
    client.post("/auth/login", data={"username": "op", "password": "op12345678"},
                follow_redirects=False)
    r = client.get(f"/export/alertas?{_qs(eid)}")
    assert r.status_code == 403
