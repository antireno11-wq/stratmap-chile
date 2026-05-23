"""Tests del endpoint GET /admin/stats — gates de auth, no shape (necesita DB)."""


def test_admin_stats_sin_token_401(client):
    assert client.get("/admin/stats").status_code == 401


def test_admin_stats_user_no_admin_403(client, user_headers):
    assert client.get("/admin/stats", headers=user_headers).status_code == 403


def test_admin_stats_admin_no_401_403(client, admin_headers):
    # Sin DB devuelve 500 (queries fallan), pero la gate de admin sí pasó
    r = client.get("/admin/stats", headers=admin_headers)
    assert r.status_code not in (401, 403)
