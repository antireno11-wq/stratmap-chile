"""Tests del rate limiter (middleware en main.py)."""


def test_health_no_throttle(client):
    # /health está explícitamente exento; 50 hits seguidos sin 429
    for _ in range(50):
        assert client.get("/health").status_code == 200


def test_auth_login_limit_5_por_minuto(client):
    statuses = [
        client.post("/auth/login", json={"email": "x@y.cl", "password": "x"}).status_code
        for _ in range(7)
    ]
    # Las primeras 5 pasan (puede ser 401/500/etc según DB); la 6ª y 7ª son 429
    assert all(s != 429 for s in statuses[:5]), f"primeras 5 deberían pasar el limiter: {statuses}"
    assert statuses[5] == 429, f"6ª llamada debería ser 429: {statuses}"
    assert statuses[6] == 429


def test_admin_limit_2_por_minuto(client):
    statuses = [client.post("/admin/run-rss").status_code for _ in range(4)]
    # Primeras 2 pasan (401 por auth), 3ª y 4ª son 429
    assert statuses[0] != 429
    assert statuses[1] != 429
    assert statuses[2] == 429
    assert statuses[3] == 429


def test_retry_after_header_presente(client):
    # Forzar throttle
    for _ in range(3):
        client.post("/admin/run-rss")
    r = client.post("/admin/run-rss")
    assert r.status_code == 429
    assert r.headers.get("retry-after") == "60"


def test_x_forwarded_for_distingue_ips(client):
    # Mismo path pero distinta IP via X-Forwarded-For: no se mezclan los buckets
    for _ in range(2):
        client.post("/admin/run-rss", headers={"X-Forwarded-For": "1.1.1.1"})
    # Esta IP no agotó su bucket todavía
    r = client.post("/admin/run-rss", headers={"X-Forwarded-For": "2.2.2.2"})
    assert r.status_code != 429
