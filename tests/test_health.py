"""Tests del endpoint /health."""
import os


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for key in ("status", "db_ok", "version", "uptime_seconds", "worker", "last_scrape_by_source"):
        assert key in body, f"missing key: {key}"
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert isinstance(body["worker"], dict)


def test_health_version_from_env(monkeypatch, client):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "deadbeef0123456789abcdef")
    r = client.get("/health")
    # Toma los primeros 8 chars
    assert r.json()["version"] == "deadbeef"


def test_health_version_unknown_si_falta_env(monkeypatch, client):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    r = client.get("/health")
    assert r.json()["version"] == "unknown"
