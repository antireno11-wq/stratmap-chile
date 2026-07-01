"""Fixtures compartidas. Setean env vars antes de cargar la app."""
import os
import secrets

# Env vars que auth.py exige al import. Se setean ANTES de importar la app.
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
os.environ.setdefault("ADMIN_EMAILS", "admin@test.cl")
# main.py NO carga el .env bajo pytest (detecta "pytest" en sys.modules), así que
# el entorno de test queda aislado del .env local.

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Cliente con server-side exceptions desactivadas para poder testear
    endpoints aunque la DB no esté disponible (las gates de auth corren antes)."""
    from main import app
    # Limpiar rate limit state entre tests para evitar interferencia
    from main import _rl_hits
    _rl_hits.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def user_token():
    """JWT válido para un usuario sin permisos de admin."""
    from auth import create_access_token
    return create_access_token(99, "user@test.cl")


@pytest.fixture
def admin_token():
    """JWT válido para un admin (email en ADMIN_EMAILS)."""
    from auth import create_access_token
    return create_access_token(1, "admin@test.cl")


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
