"""Shared FastAPI dependencies (auth gates + feature gates).

Routers import these to attach auth/plan checks to their endpoints.
"""
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException

import db
from auth import decode_token
from plans import features_for, plan_is_active


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


def require_feature(feature: str):
    """Factory: devuelve una dependency que exige que el plan del user incluya `feature`.

    Devuelve 402 (Payment Required) con detalle accionable si no.
    """
    def _dep(user=Depends(get_current_user)):
        plan_row = db.get_user_plan(user["user_id"])
        plan_name = plan_row.get("plan", "free")
        status = plan_row.get("status", "active")
        if not plan_is_active(status):
            raise HTTPException(
                status_code=402,
                detail=f"Tu suscripción está '{status}'. Actualizá tu método de pago en /billing/portal.",
            )
        if not features_for(plan_name).get(feature, False):
            raise HTTPException(
                status_code=402,
                detail=f"Tu plan ({plan_name}) no incluye '{feature}'. Mirá los planes en /pricing.html.",
            )
        return user
    return _dep
