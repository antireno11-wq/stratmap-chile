"""Tests de las correcciones de seguridad (auditoría):
   - C1: aislamiento de contactos por user_id (firmas exigen user_id).
   - C2: derivación de plan por monto en el webhook MP (sin fallback 'pro').
   - C3: rutas del webhook MP y gates de los endpoints nuevos.
"""
import pytest


# ── C2: _plan_from_amount (puro, sin DB) ──────────────────────────────────────

def test_plan_from_amount_pro():
    from routers.billing import _plan_from_amount
    assert _plan_from_amount(29000) == "pro"


def test_plan_from_amount_team():
    from routers.billing import _plan_from_amount
    assert _plan_from_amount(89000) == "team"


def test_plan_from_amount_string_ok():
    from routers.billing import _plan_from_amount
    assert _plan_from_amount("29000") == "pro"


def test_plan_from_amount_monto_desconocido_none():
    from routers.billing import _plan_from_amount
    assert _plan_from_amount(12345) is None


def test_plan_from_amount_cero_none():
    # El precio de 'free' es 0, pero free se excluye → ningún plan de pago matchea 0.
    from routers.billing import _plan_from_amount
    assert _plan_from_amount(0) is None


def test_plan_from_amount_none():
    from routers.billing import _plan_from_amount
    assert _plan_from_amount(None) is None


# ── C1: las funciones de contactos EXIGEN user_id (lock de firma) ─────────────

def test_list_contacts_requiere_user_id():
    import db
    with pytest.raises(TypeError):
        db.list_contacts()  # type: ignore[call-arg]


def test_create_contact_requiere_user_id():
    import db
    with pytest.raises(TypeError):
        db.create_contact({"name": "x", "company": "y"})  # type: ignore[call-arg]


def test_count_user_contacts_existe():
    import db
    assert callable(db.count_user_contacts)


# ── C3: webhook MP responde en /pagos y /pago (no 404) ────────────────────────

def test_webhook_pagos_route_existe(client):
    # Sin secret configurado y fuera de producción: procesa y ignora topic vacío.
    r = client.post("/pagos")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_webhook_pago_route_existe(client):
    r = client.post("/pago")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_webhook_ignora_topic_no_preapproval(client):
    r = client.post("/pagos?topic=payment&id=123")
    assert r.status_code == 200
    assert r.json().get("ignored") == "payment"


# ── Gates de los endpoints nuevos ─────────────────────────────────────────────

def test_analyze_services_sin_token_401(client):
    assert client.post("/opportunities/123/analyze-services").status_code == 401


def test_analyze_services_free_user_402(client, user_headers, monkeypatch):
    import db
    monkeypatch.setattr(db, "get_user_plan", lambda uid: {"plan": "free", "status": "active"})
    r = client.post("/opportunities/123/analyze-services", headers=user_headers)
    assert r.status_code == 402


def test_generate_email_sin_token_401(client):
    assert client.post("/contacts/5/generate-email").status_code == 401
