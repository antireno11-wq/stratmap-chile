"""Endpoints de billing — integración con Mercado Pago via preapprovals (suscripciones).

Flujo:
  1. Frontend hace POST /billing/checkout {plan: "pro"|"team"} → devolvemos init_point URL.
  2. Frontend redirige al user a init_point. MP cobra y maneja recurrencia.
  3. MP envía POST /billing/webhook con topic=preapproval & id=<preapproval_id>.
  4. Validamos firma HMAC, fetcheamos el preapproval, actualizamos user_plans.
  5. /me/plan refleja el nuevo plan.

Env vars:
  MP_ACCESS_TOKEN     — Access token de Mercado Pago (test o prod).
  MP_WEBHOOK_SECRET   — Secret para validar firma del webhook (panel MP > Webhooks).
  PUBLIC_URL          — base URL pública (https://...railway.app), para back_url y notification_url.

Sandbox: crear una app de prueba en https://www.mercadopago.cl/developers,
copiar TEST-... access token y configurar webhook a https://<tu>.up.railway.app/billing/webhook.
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

import db
from deps import get_current_user
from plans import PLANS

logger = logging.getLogger("stratmap.billing")
router = APIRouter(tags=["billing"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckoutPayload(BaseModel):
    plan: str  # "pro" | "team"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mp_token() -> str:
    tok = os.getenv("MP_ACCESS_TOKEN", "").strip()
    if not tok:
        raise HTTPException(status_code=503, detail="MP_ACCESS_TOKEN no configurado")
    return tok


def _public_base_url() -> str:
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        # Fallback razonable: tu URL de Railway
        base = "https://stratmap-chile.up.railway.app"
    return base


def _verify_signature(request_id: str, data_id: str, ts: str, signature_header: str) -> bool:
    """Valida x-signature de Mercado Pago.

    Formato del header: 'ts=<unix>,v1=<hex>'.
    Manifest a firmar: 'id:<data_id>;request-id:<request_id>;ts:<ts>;'.
    """
    secret = os.getenv("MP_WEBHOOK_SECRET", "").strip()
    if not secret:
        # Sin secret no podemos validar — devolvemos True pero loggeamos.
        # En prod hay que setearlo.
        logger.warning("mp webhook: MP_WEBHOOK_SECRET no configurado, NO se valida firma")
        return True
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _fetch_preapproval(preapproval_id: str) -> dict:
    """Trae el preapproval desde MP API. Lazy import del SDK."""
    import mercadopago  # noqa
    sdk = mercadopago.SDK(_mp_token())
    resp = sdk.preapproval().get(preapproval_id)
    if resp.get("status") and resp["status"] >= 400:
        raise HTTPException(status_code=502, detail=f"MP fetch failed: {resp}")
    return resp.get("response", {})


def _status_to_internal(mp_status: str) -> str:
    """Mapea status de MP a status interno."""
    if mp_status in ("authorized", "active"):
        return "active"
    if mp_status in ("pending",):
        return "trialing"
    if mp_status in ("cancelled", "finished"):
        return "canceled"
    if mp_status in ("paused",):
        return "past_due"
    return "canceled"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/billing/checkout")
def create_checkout(payload: CheckoutPayload, user=Depends(get_current_user)):
    """Crea un preapproval (suscripción recurrente) en Mercado Pago."""
    if payload.plan not in PLANS or payload.plan == "free":
        raise HTTPException(status_code=400, detail=f"Plan inválido: {payload.plan}")

    plan_def = PLANS[payload.plan]
    if plan_def["price_clp"] <= 0:
        raise HTTPException(status_code=400, detail="No se puede pagar un plan gratuito")

    import mercadopago  # noqa
    sdk = mercadopago.SDK(_mp_token())

    base = _public_base_url()
    body = {
        "reason": f"Stratmap {plan_def['label']} — suscripción mensual",
        "external_reference": str(user["user_id"]),
        "payer_email": user["email"],
        "back_url": f"{base}/billing/portal",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(plan_def["price_clp"]),
            "currency_id": "CLP",
        },
        "status": "pending",
    }
    resp = sdk.preapproval().create(body)
    if resp.get("status") and resp["status"] >= 400:
        logger.error("mp preapproval create failed", extra={"resp": resp})
        raise HTTPException(status_code=502, detail=f"No se pudo crear el checkout: {resp.get('response')}")

    pre = resp["response"]
    init_point = pre.get("init_point")
    preapproval_id = pre.get("id")

    # Guardamos preapproval_id en user_plans para poder linkar el webhook
    db.upsert_user_plan(
        user_id=user["user_id"],
        plan=payload.plan,
        status="pending",  # Hasta que MP confirme via webhook, sigue 'pending'
        mp_preapproval_id=preapproval_id,
    )
    logger.info("mp checkout created", extra={
        "user_id": user["user_id"], "plan": payload.plan, "preapproval_id": preapproval_id,
    })
    return {"init_point": init_point, "preapproval_id": preapproval_id, "plan": payload.plan}


@router.post("/billing/webhook")
async def mp_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="x-signature"),
    x_request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    """Webhook público de Mercado Pago. Idempotente, valida firma HMAC."""
    body = await request.body()
    qp = dict(request.query_params)
    topic = qp.get("topic") or qp.get("type") or ""
    resource_id = qp.get("id") or qp.get("data.id") or ""

    logger.info("mp webhook received", extra={"topic": topic, "id": resource_id})

    # Validar firma si MP la mandó (en producción siempre debería estar)
    if x_signature and "ts=" in x_signature and "v1=" in x_signature:
        try:
            parts = dict(p.split("=", 1) for p in x_signature.split(","))
            ts_val = parts.get("ts", "")
            v1_val = parts.get("v1", "")
            ok = _verify_signature(x_request_id or "", resource_id, ts_val, v1_val)
            if not ok:
                logger.warning("mp webhook: firma inválida", extra={"id": resource_id})
                raise HTTPException(status_code=401, detail="Firma MP inválida")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("mp webhook: error parseando firma", extra={"err": str(e)})

    # Solo procesamos topic=preapproval (suscripciones). Ignoramos otros.
    if topic not in ("preapproval", "subscription_preapproval"):
        return {"ok": True, "ignored": topic}

    if not resource_id:
        return {"ok": True, "ignored": "no_id"}

    try:
        pre = _fetch_preapproval(resource_id)
    except HTTPException as e:
        logger.error("mp webhook: fetch failed", extra={"id": resource_id, "err": e.detail})
        return {"ok": False, "error": "fetch_failed"}

    # external_reference es el user_id que guardamos al crear el checkout
    external_ref = pre.get("external_reference")
    if not external_ref:
        logger.warning("mp webhook: preapproval sin external_reference", extra={"id": resource_id})
        return {"ok": True, "ignored": "no_external_ref"}
    try:
        user_id = int(external_ref)
    except ValueError:
        return {"ok": True, "ignored": "bad_external_ref"}

    mp_status = pre.get("status", "")
    plan_row = db.get_user_plan(user_id) or {}
    # El plan ya está guardado del checkout; el webhook solo actualiza status
    plan_name = plan_row.get("plan", "pro")

    next_payment_iso = pre.get("next_payment_date")
    current_period_end = None
    if next_payment_iso:
        try:
            current_period_end = datetime.fromisoformat(next_payment_iso.replace("Z", "+00:00"))
        except Exception:
            pass

    db.upsert_user_plan(
        user_id=user_id,
        plan=plan_name,
        status=_status_to_internal(mp_status),
        current_period_end=current_period_end,
        mp_preapproval_id=resource_id,
    )
    logger.info("mp webhook applied", extra={
        "user_id": user_id, "plan": plan_name, "mp_status": mp_status,
    })
    return {"ok": True}


@router.get("/billing/portal")
def billing_portal(user=Depends(get_current_user)):
    """Información del plan actual + URL para gestionar/cancelar en MP."""
    plan_row = db.get_user_plan(user["user_id"])
    preapproval_id = plan_row.get("mp_preapproval_id")
    mp_management_url = None
    if preapproval_id:
        # Mercado Pago expone la gestión via init_point del preapproval, no hay portal genérico.
        # El user puede cancelar desde su cuenta MP > Mis suscripciones.
        mp_management_url = "https://www.mercadopago.cl/subscriptions"
    return {
        "plan": plan_row.get("plan", "free"),
        "status": plan_row.get("status", "active"),
        "current_period_end": (
            plan_row["current_period_end"].isoformat()
            if plan_row.get("current_period_end") else None
        ),
        "mp_preapproval_id": preapproval_id,
        "manage_url": mp_management_url,
    }
