"""Testes CRUD — Setores, Equipamentos, Sensores."""
import pytest
from app.core.models import Equipamento, Setor, Sensor, Usuario
from app.core.pwd import hash_password
from app.core.database import SessionLocal
from app.core.constants import TipoEquipamento, Protocolo


def _admin():
    with SessionLocal() as db:
        u = Usuario(username="admin", hashed_password=hash_password("admin123"),
                    role="ADMIN", is_active=True, must_change_password=False)
        db.add(u); db.commit()


def _login(client):
    client.post("/auth/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)


def _setor(nome="Farm") -> int:
    with SessionLocal() as db:
        s = Setor(nome=nome, is_active=True)
        db.add(s); db.commit(); db.refresh(s)
        return s.id


def _equip(setor_id, nome="Gel A") -> int:
    with SessionLocal() as db:
        e = Equipamento(setor_id=setor_id, nome=nome,
                        tipo=TipoEquipamento.GELADEIRA.value,
                        temp_min=2.0, temp_max=8.0, is_active=True)
        db.add(e); db.commit(); db.refresh(e)
        return e.id


# ── Setores ───────────────────────────────────────────────────────────────────

def test_listar_setores(client):
    _admin(); _login(client); _setor("UTI")
    assert "UTI" in client.get("/setores/").text


def test_criar_setor(client):
    _admin(); _login(client)
    r = client.post("/setores/novo", data={"nome": "Hemo", "descricao": ""},
                    follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        assert db.query(Setor).filter_by(nome="Hemo").first() is not None


def test_criar_setor_duplicado(client):
    _admin(); _login(client); _setor("Farm")
    r = client.post("/setores/novo", data={"nome": "Farm", "descricao": ""},
                    follow_redirects=False)
    assert r.status_code == 400


def test_editar_setor(client):
    _admin(); _login(client)
    sid = _setor("Old")
    r = client.post(f"/setores/{sid}/editar", data={"nome": "New", "descricao": ""},
                    follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        assert db.query(Setor).filter_by(id=sid).first().nome == "New"


def test_desativar_setor_sem_equipamentos(client):
    _admin(); _login(client)
    sid = _setor()
    client.post(f"/setores/{sid}/desativar", follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Setor).filter_by(id=sid).first().is_active is False


def test_desativar_setor_com_equipamentos_bloqueado(client):
    _admin(); _login(client)
    sid = _setor(); _equip(sid)
    client.post(f"/setores/{sid}/desativar", follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Setor).filter_by(id=sid).first().is_active is True


def test_reativar_setor(client):
    _admin(); _login(client)
    sid = _setor()
    with SessionLocal() as db:
        s = db.query(Setor).filter_by(id=sid).first()
        s.is_active = False; db.commit()
    client.post(f"/setores/{sid}/ativar", follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Setor).filter_by(id=sid).first().is_active is True


def test_acesso_operador_bloqueado(client):
    with SessionLocal() as db:
        db.add(Usuario(username="op", hashed_password=hash_password("op123"),
                       role="OPERADOR", is_active=True, must_change_password=False))
        db.commit()
    client.post("/auth/login", data={"username": "op", "password": "op123"},
                follow_redirects=False)
    assert client.get("/setores/").status_code == 403


# ── Equipamentos ──────────────────────────────────────────────────────────────

def test_criar_equipamento(client):
    _admin(); _login(client)
    sid = _setor()
    r = client.post("/equipamentos/novo", data={
        "setor_id": sid, "nome": "Gel B", "tipo": "GELADEIRA",
        "temp_min": "2.0", "temp_max": "8.0", "umid_min": "", "umid_max": "",
        "patrimonio": "", "fabricante": "", "modelo": "",
    }, follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        assert db.query(Equipamento).filter_by(nome="Gel B").first() is not None


def test_defaults_por_tipo(client):
    _admin(); _login(client)
    d = client.get("/equipamentos/api/defaults/GELADEIRA").json()
    assert d["temp_min"] == 2.0 and d["temp_max"] == 8.0


def test_defaults_tipo_invalido(client):
    _admin(); _login(client)
    assert client.get("/equipamentos/api/defaults/INVALIDO").json()["temp_min"] is None


def test_desativar_equipamento_requer_motivo(client):
    _admin(); _login(client)
    eid = _equip(_setor())
    client.post(f"/equipamentos/{eid}/desativar", data={"motivo": ""},
                follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Equipamento).filter_by(id=eid).first().is_active is True


def test_desativar_equipamento_com_motivo(client):
    _admin(); _login(client)
    eid = _equip(_setor())
    client.post(f"/equipamentos/{eid}/desativar", data={"motivo": "Manut."},
                follow_redirects=False)
    with SessionLocal() as db:
        e = db.query(Equipamento).filter_by(id=eid).first()
        assert e.is_active is False
        assert e.motivo_inativacao == "Manut."


# ── Sensores ──────────────────────────────────────────────────────────────────

def test_criar_sensor(client):
    _admin(); _login(client)
    eid = _equip(_setor())
    r = client.post("/sensores/novo", data={
        "equipamento_id": eid, "nome": "S1", "protocolo": "HTTP",
        "endereco": "http://sensor.local", "config_json_raw": "{}",
    }, follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        assert db.query(Sensor).filter_by(nome="S1").first() is not None


def test_config_default_modbus(client):
    _admin(); _login(client)
    d = client.get("/sensores/api/config-default/MODBUS").json()
    assert "slave_id" in d and "reg_temp" in d


def test_testar_sensor_sem_conexao(client):
    _admin(); _login(client)
    eid = _equip(_setor())
    with SessionLocal() as db:
        s = Sensor(equipamento_id=eid, protocolo="HTTP",
                   endereco="http://127.0.0.1:19999/x",
                   config_json={"field_temp": "temp"}, is_active=True)
        db.add(s); db.commit(); db.refresh(s); sid = s.id
    d = client.post(f"/sensores/{sid}/testar").json()
    assert d["sucesso"] is False


def test_desativar_sensor(client):
    _admin(); _login(client)
    eid = _equip(_setor())
    with SessionLocal() as db:
        s = Sensor(equipamento_id=eid, protocolo="MODBUS",
                   endereco="192.168.1.1:502", is_active=True)
        db.add(s); db.commit(); db.refresh(s); sid = s.id
    client.post(f"/sensores/{sid}/desativar", follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Sensor).filter_by(id=sid).first().is_active is False
