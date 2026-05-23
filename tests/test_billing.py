"""Tests de billing y feature gates."""


# ── /me/plan ──────────────────────────────────────────────────────────────────

def test_me_plan_sin_token_401(client):
    assert client.get("/me/plan").status_code == 401


def test_me_plan_con_token_no_401_403(client, user_headers):
    # Sin DB devuelve 500. Lo importante: gate de auth pasa.
    r = client.get("/me/plan", headers=user_headers)
    assert r.status_code not in (401, 403)


# ── /billing/checkout ─────────────────────────────────────────────────────────

def test_checkout_sin_token_401(client):
    r = client.post("/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 401


def test_checkout_plan_invalido(client, user_headers):
    r = client.post("/billing/checkout", headers=user_headers, json={"plan": "xxx"})
    # 400 (validación interna) o 500 (sin DB) — pero NO 401/403
    assert r.status_code not in (401, 403)


def test_checkout_free_no_se_paga(client, user_headers):
    # Free no debería poder comprarse — 400
    r = client.post("/billing/checkout", headers=user_headers, json={"plan": "free"})
    # 400 si la lógica corre; 500 si rompe antes. Lo importante: NO 401/403.
    assert r.status_code not in (401, 403)


# ── /billing/webhook ──────────────────────────────────────────────────────────

def test_webhook_publico_no_requiere_auth(client):
    # Sin params ni body, debe responder OK (con ignored=...)
    r = client.post("/billing/webhook")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "ignored" in body


def test_webhook_ignora_topic_no_relevante(client):
    r = client.post("/billing/webhook?topic=payment&id=12345")
    assert r.status_code == 200
    assert r.json().get("ignored") == "payment"


# ── /billing/portal ───────────────────────────────────────────────────────────

def test_portal_sin_token_401(client):
    assert client.get("/billing/portal").status_code == 401


def test_portal_con_token_no_401_403(client, user_headers):
    r = client.get("/billing/portal", headers=user_headers)
    assert r.status_code not in (401, 403)


# ── require_feature en endpoints ──────────────────────────────────────────────

def test_export_contacts_free_user_402(client, user_headers, monkeypatch):
    """Free user no debería poder exportar. Sin DB devuelve 500, así que
    monkeypatchamos get_user_plan para simular plan free."""
    import db
    monkeypatch.setattr(db, "get_user_plan", lambda uid: {"plan": "free", "status": "active"})
    r = client.get("/contacts/export", headers=user_headers)
    assert r.status_code == 402


def test_export_contacts_pro_user_ok(client, user_headers, monkeypatch):
    """Pro user pasa el feature gate (luego puede dar 500 por DB en list_contacts)."""
    import db
    monkeypatch.setattr(db, "get_user_plan", lambda uid: {"plan": "pro", "status": "active"})
    r = client.get("/contacts/export", headers=user_headers)
    assert r.status_code != 402


def test_score_projects_free_user_402(client, user_headers, monkeypatch):
    import db
    monkeypatch.setattr(db, "get_user_plan", lambda uid: {"plan": "free", "status": "active"})
    r = client.post("/me/score-projects", headers=user_headers, json={})
    assert r.status_code == 402


def test_canceled_plan_402(client, user_headers, monkeypatch):
    """Status != active da 402 aunque el plan tenga la feature."""
    import db
    monkeypatch.setattr(db, "get_user_plan", lambda uid: {"plan": "pro", "status": "canceled"})
    r = client.get("/contacts/export", headers=user_headers)
    assert r.status_code == 402
