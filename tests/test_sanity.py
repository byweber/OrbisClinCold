"""Testes de sanidade — imports, constantes, factory."""

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_modelos_importam():
    from app.core.models import Setor, Equipamento, Sensor, Leitura, Alerta, Usuario, AuditLog  # noqa: F401

def test_constantes():
    from app.core.constants import TIPOS_EQUIPAMENTO, PROTOCOLOS, RANGES_PADRAO
    assert "GELADEIRA" in TIPOS_EQUIPAMENTO
    assert "MODBUS" in PROTOCOLOS
    assert RANGES_PADRAO["GELADEIRA"]["temp_min"] == 2.0

def test_pwd_hash_verify():
    from app.core.pwd import hash_password, verify_password
    h = hash_password("teste123")
    assert verify_password("teste123", h)
    assert not verify_password("errada", h)

def test_adapter_factory_invalido():
    from app.core.adapters.base import get_adapter
    try:
        get_adapter("INVALIDO", "x", {})
        assert False
    except ValueError:
        pass

def test_root_redirect_sem_auth(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "login" in r.headers["location"]
