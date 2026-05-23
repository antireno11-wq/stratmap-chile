"""Endpoints `/me/*` y `/ai/fits` — todo scopeado al usuario logueado."""
import threading
import traceback

from fastapi import APIRouter, Depends, HTTPException

import db
from deps import get_current_user
from schemas import PreferencesPayload, ServiceProfilePayload

router = APIRouter(tags=["me"])


@router.get("/me/preferences")
def get_my_preferences(user=Depends(get_current_user)):
    prefs = db.get_preferences(user["user_id"])
    return prefs or {}


@router.put("/me/preferences")
def update_preferences(payload: PreferencesPayload, user=Depends(get_current_user)):
    db.save_preferences(user["user_id"], payload.model_dump())
    return {"ok": True}


@router.get("/me/service-profile")
def get_service_profile_endpoint(user=Depends(get_current_user)):
    profile = db.get_service_profile(user["user_id"])
    return profile or {"company_name": None, "services": []}


@router.put("/me/service-profile")
def update_service_profile(payload: ServiceProfilePayload, user=Depends(get_current_user)):
    db.init_ai_db()

    def normalize_service(s):
        if isinstance(s, str):
            return {"name": s, "description": ""}
        if hasattr(s, "model_dump"):
            return s.model_dump()
        if isinstance(s, dict):
            return s
        return {"name": str(s), "description": ""}

    profile = db.upsert_service_profile(
        user_id=user["user_id"],
        company_key=payload.company_key,
        company_name=payload.company_name or "",
        services=[normalize_service(s) for s in payload.services],
        regions=payload.regions or [],
        contract_sizes=payload.contract_sizes or [],
        known_mandantes=payload.known_mandantes or [],
        onboarding_done=payload.onboarding_done,
    )
    return {"ok": True, "profile": profile}


@router.get("/me/profile")
def get_profile(user=Depends(get_current_user)):
    """Retorna el perfil completo del usuario logueado, incluyendo onboarding_done."""
    profile = db.get_service_profile(user["user_id"])
    if not profile:
        return {"onboarding_done": False, "services": [], "company_name": None}
    return profile


@router.post("/me/score-projects")
def score_projects(payload: dict, user=Depends(get_current_user)):
    """Dispara scoring IA personalizado en background."""
    uid = user["user_id"]

    def _run():
        try:
            import ai_matcher
            result = ai_matcher.run(user_id=uid, limit=500)
            print(f"[score-projects] {result}")
        except Exception:
            traceback.print_exc()

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring IA iniciado en background"}


@router.get("/ai/fits")
def get_ai_fits(min_score: int = 0, limit: int = 500, user=Depends(get_current_user)):
    """Retorna los scores IA calculados para el usuario logueado."""
    try:
        fits = db.get_ai_fits(user_id=user["user_id"], min_score=min_score, limit=limit)
        return {"fits": fits, "total": len(fits)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
