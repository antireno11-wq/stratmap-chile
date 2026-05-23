"""Endpoints públicos de autenticación + bootstrap del primer usuario."""
import os

from fastapi import APIRouter, HTTPException

import db
from auth import hash_password, verify_password, create_access_token
from schemas import LoginPayload, CreateUserPayload

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginPayload):
    user = db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    try:
        db.touch_user_last_login(user["id"])
    except Exception:
        # No bloquear el login si la actualización falla
        pass
    token = create_access_token(user["id"], user["email"])
    return {"token": token, "email": user["email"], "name": user.get("name")}


@router.post("/setup/first-user")
def setup_first_user(payload: CreateUserPayload):
    if os.getenv("ALLOW_SETUP", "").lower() != "true":
        raise HTTPException(status_code=403, detail="Setup deshabilitado")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users")
            row = cur.fetchone()
            if row and int(row["n"]) > 0:
                raise HTTPException(status_code=403, detail="Setup ya completado: ya existen usuarios")
    password_hash = hash_password(payload.password)
    new_user = db.create_user(payload.email, password_hash, payload.name)
    return {"ok": True, "user_id": new_user["id"], "email": new_user["email"]}
