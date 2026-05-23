"""Tests de gates de autenticación y admin."""
import pytest


# ── Endpoints públicos ────────────────────────────────────────────────────────

def test_health_publico(client):
    assert client.get("/health").status_code == 200


def test_auth_login_publico(client):
    # No tira 401 ni 403 (puede dar 500 si la DB no está)
    r = client.post("/auth/login", json={"email": "x@y.cl", "password": "x"})
    assert r.status_code not in (401, 403)


def test_setup_first_user_requiere_allow_setup(client):
    # Sin ALLOW_SETUP=true en env, devuelve 403
    r = client.post("/setup/first-user", json={"email": "x@y.cl", "password": "x"})
    assert r.status_code == 403


# ── Endpoints protegidos: sin token → 401 ─────────────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("get",    "/contacts"),
    ("post",   "/contacts"),
    ("get",    "/opportunities"),
    ("get",    "/feed"),
    ("get",    "/pipeline"),
    ("get",    "/pipeline/statuses"),
    ("get",    "/me/preferences"),
    ("put",    "/me/preferences"),
    ("get",    "/me/service-profile"),
    ("get",    "/me/profile"),
    ("get",    "/ai/fits"),
    ("get",    "/mandantes"),
    ("get",    "/faenas"),
    ("get",    "/empleos/resumen"),
    ("get",    "/noticias"),
    ("delete", "/contacts/1"),
])
def test_endpoint_sin_token_401(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}, esperado 401"


# ── Endpoints admin: sin token → 401, con user no-admin → 403 ─────────────────

@pytest.mark.parametrize("method,path", [
    ("post",   "/admin/run-rss"),
    ("post",   "/admin/run-expire-stale"),
    ("post",   "/admin/run-sigex"),
    ("post",   "/admin/refresh-faenas"),
    ("get",    "/admin/sources-count"),
    ("post",   "/ingest"),  # admin-only también
    ("delete", "/admin/delete-source/foo"),
])
def test_admin_sin_token_401(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"


@pytest.mark.parametrize("method,path", [
    ("post", "/admin/run-rss"),
    ("post", "/admin/run-expire-stale"),
    ("post", "/admin/refresh-faenas"),
    ("get",  "/admin/sources-count"),
])
def test_admin_user_no_admin_403(client, user_headers, method, path):
    r = client.request(method, path, headers=user_headers, json={})
    assert r.status_code == 403, f"{method.upper()} {path} (user normal) -> {r.status_code}"


# ── Tokens malformados / firmados con otra clave ──────────────────────────────

def test_token_basura_401(client):
    r = client.get("/contacts", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


def test_authorization_sin_bearer_401(client):
    r = client.get("/contacts", headers={"Authorization": "Token foo"})
    assert r.status_code == 401


def test_authorization_sin_header_401(client):
    r = client.get("/contacts")
    assert r.status_code == 401


def test_token_firmado_con_otra_clave_401(client):
    from jose import jwt
    from datetime import datetime, timedelta
    # Token con un secret distinto al de la app
    bogus = jwt.encode(
        {"sub": "99", "email": "x@y.cl", "exp": datetime.utcnow() + timedelta(minutes=5)},
        "otra-clave-secreta-mas-de-32-caracteres-aaa",
        algorithm="HS256",
    )
    r = client.get("/contacts", headers={"Authorization": f"Bearer {bogus}"})
    assert r.status_code == 401


def test_token_expirado_401(client):
    from jose import jwt
    from datetime import datetime, timedelta
    from auth import SECRET_KEY
    expired = jwt.encode(
        {"sub": "99", "email": "x@y.cl", "exp": datetime.utcnow() - timedelta(minutes=5)},
        SECRET_KEY,
        algorithm="HS256",
    )
    r = client.get("/contacts", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


# ── Token válido NO debe ser bloqueado por auth (puede dar 500 por DB) ────────

def test_user_valido_no_401_403(client, user_headers):
    r = client.get("/contacts", headers=user_headers)
    assert r.status_code not in (401, 403)


def test_admin_valido_no_403(client, admin_headers):
    r = client.post("/admin/run-rss", headers=admin_headers)
    assert r.status_code not in (401, 403)
