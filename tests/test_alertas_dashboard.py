"""Testes Alertas e Dashboard — Sprint 4."""
import pytest
from datetime import datetime, timedelta, timezone
from app.core.models import Alerta, Equipamento, Leitura, Setor, Sensor, Usuario
from app.core.pwd import hash_password
from app.core.database import SessionLocal
from app.core.constants import TipoAlerta, TipoEquipamento


def _setup(role="ADMIN", setor_id=None):
    """Cria usuário, setor, equipamento e sensor. Retorna (uid, sid, eid, senid)."""
    with SessionLocal() as db:
        u = Usuario(username="admin", hashed_password=hash_password("admin123"),
                    role=role, is_active=True, must_change_password=False,
                    setor_id=setor_id)
        s = Setor(nome="Farm", is_active=True)
        db.add_all([u, s]); db.flush()
        e = Equipamento(setor_id=s.id, nome="Gel A",
                        tipo=TipoEquipamento.GELADEIRA.value,
                        temp_min=2.0, temp_max=8.0, is_active=True)
        db.add(e); db.flush()
        sen = Sensor(equipamento_id=e.id, protocolo="HTTP",
                     endereco="http://x", is_active=True)
        db.add(sen); db.commit()
        return u.id, s.id, e.id, sen.id


def _login(client):
    client.post("/auth/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)


def _alerta(sensor_id, equip_id, tipo=TipoAlerta.TEMP_ALTA.value,
            ativo=True, reconhecido_por=None):
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        a = Alerta(sensor_id=sensor_id, equipamento_id=equip_id, tipo=tipo,
                   valor_registrado=10.5, valor_limite=8.0, inicio_at=agora,
                   fim_at=None if ativo else agora + timedelta(minutes=30),
                   reconhecido_por=reconhecido_por)
        db.add(a); db.commit(); db.refresh(a)
        return a.id


# ── Alertas ───────────────────────────────────────────────────────────────────

def test_listar_alertas_ativos(client):
    _, _, eid, senid = _setup(); _login(client)
    _alerta(senid, eid)
    r = client.get("/alertas/")
    assert r.status_code == 200
    assert "TEMP ALTA" in r.text


def test_listar_historico(client):
    _, _, eid, senid = _setup(); _login(client)
    _alerta(senid, eid, ativo=False)
    assert client.get("/alertas/?historico=true").status_code == 200


def test_filtrar_por_tipo(client):
    _, _, eid, senid = _setup(); _login(client)
    _alerta(senid, eid, tipo=TipoAlerta.TEMP_ALTA.value)
    r = client.get("/alertas/?tipo=TEMP_ALTA")
    assert r.status_code == 200


def test_reconhecer_alerta(client):
    _, _, eid, senid = _setup(); _login(client)
    aid = _alerta(senid, eid)
    r = client.post(f"/alertas/{aid}/reconhecer", follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        a = db.query(Alerta).filter_by(id=aid).first()
        assert a.reconhecido_por == "admin"
        assert a.reconhecido_at is not None


def test_reconhecer_ja_reconhecido(client):
    _, _, eid, senid = _setup(); _login(client)
    aid = _alerta(senid, eid, reconhecido_por="outro")
    r = client.post(f"/alertas/{aid}/reconhecer", follow_redirects=False)
    assert r.status_code == 302
    assert "erro" in r.headers["location"]


def test_operador_nao_reconhece_outro_setor(client):
    _, s1id, _, _ = _setup()
    # setor 2 com equipamento separado
    with SessionLocal() as db:
        s2 = Setor(nome="S2", is_active=True)
        u2 = Usuario(username="op", hashed_password=hash_password("op123"),
                     role="OPERADOR", is_active=True, must_change_password=False,
                     setor_id=s1id)
        db.add_all([s2, u2]); db.flush()
        e2 = Equipamento(setor_id=s2.id, nome="G2",
                         tipo=TipoEquipamento.GELADEIRA.value, is_active=True)
        db.add(e2); db.flush()
        sen2 = Sensor(equipamento_id=e2.id, protocolo="HTTP",
                      endereco="http://x2", is_active=True)
        db.add(sen2); db.commit()
        eid2, senid2 = e2.id, sen2.id
    aid = _alerta(senid2, eid2)
    client.post("/auth/login", data={"username": "op", "password": "op123"},
                follow_redirects=False)
    r = client.post(f"/alertas/{aid}/reconhecer", follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        assert db.query(Alerta).filter_by(id=aid).first().reconhecido_por is None


def test_api_alertas_ativos(client):
    _, _, eid, senid = _setup(); _login(client)
    _alerta(senid, eid)
    d = client.get("/alertas/api/ativos").json()
    assert d["total"] == 1
    assert d["alertas"][0]["tipo"] == "TEMP_ALTA"


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_sem_auth_redireciona(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "login" in r.headers["location"]


def test_dashboard_carrega(client):
    _setup(); _login(client)
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_dashboard_must_change_redireciona(client):
    with SessionLocal() as db:
        db.add(Usuario(username="m", hashed_password=hash_password("m12345678"),
                       role="ADMIN", is_active=True, must_change_password=True))
        db.commit()
    client.post("/auth/login", data={"username": "m", "password": "m12345678"},
                follow_redirects=False)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "trocar-senha" in r.headers["location"]


def test_api_kpis(client):
    _setup(); _login(client)
    d = client.get("/api/kpis").json()
    assert "online" in d
    assert "alertas_ativos" in d
    assert "conformidade_24h" in d


def test_kpis_contam_alertas(client):
    _, _, eid, senid = _setup(); _login(client)
    _alerta(senid, eid)
    _alerta(senid, eid, tipo=TipoAlerta.OFFLINE.value)
    assert client.get("/api/kpis").json()["alertas_ativos"] == 2


def test_api_grafico(client):
    _, _, eid, senid = _setup(); _login(client)
    with SessionLocal() as db:
        db.add(Leitura(sensor_id=senid, temperatura=5.0,
                       timestamp=datetime.now(timezone.utc)))
        db.commit()
    d = client.get(f"/api/grafico/{senid}").json()
    assert "labels" in d and len(d["temperatura"]) == 1


def test_api_grafico_404(client):
    _setup(); _login(client)
    assert client.get("/api/grafico/9999").status_code == 404


def test_operador_nao_ve_outro_setor_nos_kpis(client):
    _, s1id, _, _ = _setup()
    # Cria setor 2 com alerta
    with SessionLocal() as db:
        s2 = Setor(nome="S2", is_active=True)
        op = Usuario(username="op", hashed_password=hash_password("op123"),
                     role="OPERADOR", is_active=True, must_change_password=False,
                     setor_id=s1id)
        db.add_all([s2, op]); db.flush()
        e2  = Equipamento(setor_id=s2.id, nome="G2",
                          tipo=TipoEquipamento.GELADEIRA.value, is_active=True)
        db.add(e2); db.flush()
        sen2 = Sensor(equipamento_id=e2.id, protocolo="HTTP",
                      endereco="http://x2", is_active=True)
        db.add(sen2); db.flush()
        a2 = Alerta(sensor_id=sen2.id, equipamento_id=e2.id,
                    tipo=TipoAlerta.TEMP_ALTA.value, valor_registrado=10.0,
                    valor_limite=8.0, inicio_at=datetime.now(timezone.utc))
        db.add(a2); db.commit()

    client.post("/auth/login", data={"username": "op", "password": "op123"},
                follow_redirects=False)
    d = client.get("/api/kpis").json()
    assert d["alertas_ativos"] == 0  # operador não vê alertas do setor 2
