"""Shared FastAPI dependencies (auth gates).

Routers import these to attach auth checks to their endpoints.
"""
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException

from auth import decode_token


def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return {"user_id": int(payload["sub"]), "email": payload["email"]}


def require_admin(user=Depends(get_current_user)):
    admin_emails = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    if not admin_emails or user["email"].lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores")
    return user
