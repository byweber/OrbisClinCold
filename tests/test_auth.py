"""Testes de autenticação — Sprint 2."""
import pytest
from app.core.models import Usuario
from app.core.pwd import hash_password
from app.core.database import SessionLocal


def _criar_usuario(username="operador", password="senha123", role="OPERADOR",
                   must_change=False, setor_id=None):
    with SessionLocal() as db:
        u = Usuario(username=username, hashed_password=hash_password(password),
                    role=role, is_active=True, must_change_password=must_change,
                    setor_id=setor_id)
        db.add(u); db.commit()


def _login(client, username="operador", password="senha123"):
    return client.post("/auth/login", data={"username": username, "password": password},
                       follow_redirects=False)


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_page_exibida(client):
    r = client.get("/auth/login")
    assert r.status_code == 200
    assert "OrbisClin" in r.text


def test_login_sucesso_seta_cookie(client):
    _criar_usuario()
    r = _login(client)
    assert r.status_code == 302
    from app.core.config import get_settings
    assert get_settings().COOKIE_NAME in r.cookies


def test_login_redireciona_para_home(client):
    _criar_usuario()
    r = _login(client)
    assert r.headers["location"] == "/"


def test_login_senha_errada_retorna_401(client):
    _criar_usuario()
    r = client.post("/auth/login", data={"username": "operador", "password": "errada"},
                    follow_redirects=False)
    assert r.status_code == 401


def test_login_usuario_inexistente_retorna_401(client):
    r = client.post("/auth/login", data={"username": "fantasma", "password": "x"},
                    follow_redirects=False)
    assert r.status_code == 401


def test_login_usuario_inativo_bloqueado(client):
    _criar_usuario()
    with SessionLocal() as db:
        u = db.query(Usuario).filter_by(username="operador").first()
        u.is_active = False; db.commit()
    r = _login(client)
    assert r.status_code == 401


def test_login_must_change_redireciona(client):
    _criar_usuario(must_change=True)
    r = _login(client)
    assert r.status_code == 302
    assert "trocar-senha" in r.headers["location"]


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_sem_autenticacao_retorna_401(client):
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 401


def test_logout_limpa_cookie(client):
    _criar_usuario()
    _login(client)
    from app.core.config import get_settings
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    assert r.cookies.get(get_settings().COOKIE_NAME, "") == ""


# ── /me ───────────────────────────────────────────────────────────────────────

def test_me_sem_autenticacao_retorna_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_retorna_dados_usuario(client):
    _criar_usuario(username="admin", role="ADMIN")
    _login(client, username="admin")
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert "hashed_password" not in r.json()


# ── Trocar senha ──────────────────────────────────────────────────────────────

def test_trocar_senha_sem_autenticacao(client):
    r = client.post("/auth/trocar-senha", data={"senha_atual": "x", "nova_senha": "y", "confirmar": "y"},
                    follow_redirects=False)
    assert r.status_code == 401


def test_trocar_senha_sucesso(client):
    _criar_usuario()
    _login(client)
    r = client.post("/auth/trocar-senha",
                    data={"senha_atual": "senha123", "nova_senha": "NovaSenha@25",
                          "confirmar": "NovaSenha@25"})
    assert r.status_code == 200
    assert "Senha alterada" in r.text


def test_trocar_senha_atual_errada(client):
    _criar_usuario()
    _login(client)
    r = client.post("/auth/trocar-senha",
                    data={"senha_atual": "errada", "nova_senha": "NovaSenha@25",
                          "confirmar": "NovaSenha@25"})
    assert r.status_code == 400
    assert "incorreta" in r.text.lower()


def test_trocar_senha_confirmacao_diferente(client):
    _criar_usuario()
    _login(client)
    r = client.post("/auth/trocar-senha",
                    data={"senha_atual": "senha123", "nova_senha": "NovaSenha@25",
                          "confirmar": "Diferente@25"})
    assert r.status_code == 400
    assert "coincidem" in r.text.lower()


def test_trocar_senha_muito_curta(client):
    _criar_usuario()
    _login(client)
    r = client.post("/auth/trocar-senha",
                    data={"senha_atual": "senha123", "nova_senha": "abc", "confirmar": "abc"})
    assert r.status_code == 400
    assert "8 caracteres" in r.text


def test_trocar_senha_igual_a_atual(client):
    _criar_usuario()
    _login(client)
    r = client.post("/auth/trocar-senha",
                    data={"senha_atual": "senha123", "nova_senha": "senha123",
                          "confirmar": "senha123"})
    assert r.status_code == 400
    assert "diferente" in r.text.lower()


def test_trocar_senha_desativa_must_change(client):
    _criar_usuario(must_change=True)
    _login(client)
    client.post("/auth/trocar-senha",
                data={"senha_atual": "senha123", "nova_senha": "NovaSenha@25",
                      "confirmar": "NovaSenha@25"})
    with SessionLocal() as db:
        u = db.query(Usuario).filter_by(username="operador").first()
        assert u.must_change_password is False
