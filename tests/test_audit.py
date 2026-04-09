"""Testes do Audit Log UI e exportação CSV."""
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.core.models import AuditLog, Usuario
from app.core.pwd import hash_password


def _admin():
    with SessionLocal() as db:
        db.add(Usuario(username="admin", hashed_password=hash_password("admin123"),
                       role="ADMIN", is_active=True, must_change_password=False))
        db.commit()


def _login(client):
    client.post("/auth/login", data={"username": "admin", "password": "admin123"},
                follow_redirects=False)


def _seed_logs(n=5, username="admin", action="LOGIN", target=None):
    with SessionLocal() as db:
        for i in range(n):
            db.add(AuditLog(
                username=username, action=action,
                target=target or f"setor:{i+1}",
                details={"idx": i},
                ip_address="127.0.0.1",
                created_at=datetime.now(timezone.utc),
            ))
        db.commit()


# ── Acesso ────────────────────────────────────────────────────────────────────

def test_audit_requer_admin(client):
    _admin()
    with SessionLocal() as db:
        db.add(Usuario(username="op", hashed_password=hash_password("op123456"),
                       role="OPERADOR", is_active=True, must_change_password=False))
        db.commit()
    client.post("/auth/login", data={"username": "op", "password": "op123456"},
                follow_redirects=False)
    assert client.get("/audit/").status_code == 403


def test_audit_carrega_para_admin(client):
    _admin(); _login(client)
    r = client.get("/audit/")
    assert r.status_code == 200
    assert "Audit Log" in r.text


def test_audit_lista_registros(client):
    _admin(); _login(client)
    _seed_logs(3, action="CREATE")
    r = client.get("/audit/")
    assert r.status_code == 200
    # Deve conter pelo menos os logs gerados pelo login
    assert "admin" in r.text


# ── Filtros ───────────────────────────────────────────────────────────────────

def test_filtro_por_usuario(client):
    _admin(); _login(client)
    _seed_logs(3, username="enfermeiro", action="UPDATE")
    r = client.get("/audit/?username=enfermeiro")
    assert r.status_code == 200
    assert "enfermeiro" in r.text


def test_filtro_por_acao(client):
    _admin(); _login(client)
    _seed_logs(2, action="CREATE")
    _seed_logs(2, action="DELETE")
    r = client.get("/audit/?action=CREATE")
    assert r.status_code == 200
    assert "CREATE" in r.text


def test_filtro_por_alvo(client):
    _admin(); _login(client)
    _seed_logs(2, target="equipamento:99")
    r = client.get("/audit/?target=equipamento%3A99")
    assert r.status_code == 200
    assert "equipamento:99" in r.text


def test_filtro_sem_resultados(client):
    _admin(); _login(client)
    r = client.get("/audit/?username=fantasma_xyz")
    assert r.status_code == 200
    assert "Nenhum registro" in r.text


# ── Paginação ─────────────────────────────────────────────────────────────────

def test_paginacao_total_correto(client):
    _admin(); _login(client)
    _seed_logs(60, action="SENSOR_TEST")  # > POR_PAGINA (50)
    r = client.get("/audit/?action=SENSOR_TEST")
    assert r.status_code == 200
    # Deve mostrar contagem correta
    assert "60" in r.text


def test_pagina_2_acessivel(client):
    _admin(); _login(client)
    _seed_logs(60, action="SENSOR_TEST")
    r = client.get("/audit/?action=SENSOR_TEST&pagina=2")
    assert r.status_code == 200


# ── Exportação CSV ────────────────────────────────────────────────────────────

def test_export_csv_retorna_csv(client):
    _admin(); _login(client)
    _seed_logs(5, action="LOGIN")
    r = client.get("/audit/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "Content-Disposition" in r.headers
    assert ".csv" in r.headers["content-disposition"]


def test_export_csv_conteudo_correto(client):
    _admin(); _login(client)
    _seed_logs(3, username="enfermeiro", action="CREATE", target="setor:1")
    r = client.get("/audit/export?username=enfermeiro&action=CREATE")
    assert r.status_code == 200
    linhas = r.text.strip().split("\n")
    # Cabeçalho + 3 registros
    assert linhas[0].startswith("id,data_hora")
    assert len(linhas) >= 4


def test_export_csv_filtros_respeitados(client):
    _admin(); _login(client)
    _seed_logs(5, action="CREATE")
    _seed_logs(5, action="DELETE")
    r = client.get("/audit/export?action=DELETE")
    assert r.status_code == 200
    # Apenas registros DELETE no CSV
    linhas = [l for l in r.text.strip().split("\n") if "DELETE" in l]
    assert len(linhas) == 5


def test_export_csv_sem_auth_retorna_401(client):
    r = client.get("/audit/export")
    assert r.status_code == 401
