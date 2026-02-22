from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import db_health, init_db_safe, list_opportunities, upsert_opportunities
from db import create_user, get_user_by_email, save_preferences, get_preferences
from auth import hash_password, verify_password, create_access_token, decode_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_safe()
    yield

app = FastAPI(title="Stratmap Chile", lifespan=lifespan)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return {"user_id": int(payload["sub"]), "email": payload["email"]}


# ── Schemas ───────────────────────────────────────────────────────────────────

class OpportunityIn(BaseModel):
    source: str
    title: str
    url: str
    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    score: int = 0
    entry: Optional[str] = None
    raw: Optional[Any] = None


class IngestPayload(BaseModel):
    items: List[OpportunityIn]


class LoginPayload(BaseModel):
    email: str
    password: str


class CreateUserPayload(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class PreferencesPayload(BaseModel):
    preferred_industries: List[str] = []
    preferred_regions: List[str] = []
    preferred_phases: List[str] = []
    preferred_companies: List[str] = []
    keywords: List[str] = []
    min_investment_usd: Optional[int] = None
    weight_region: float = 1.0
    weight_industry: float = 1.0
    weight_investment: float = 1.0
    weight_phase: float = 1.0
    weight_company: float = 1.0


# ── Setup ─────────────────────────────────────────────────────────────────────

@app.post("/setup/first-user")
def setup_first_user(payload: CreateUserPayload):
    existing = get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un usuario")
    password_hash = hash_password(payload.password)
    new_user = create_user(payload.email, password_hash, payload.name)
    return {"ok": True, "user_id": new_user["id"], "email": new_user["email"]}


# ── Endpoints públicos ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    db_ok, db_msg = db_health()
    return {"status": "ok", "db_ok": db_ok, "db_msg": db_msg}


@app.post("/auth/login")
def login(payload: LoginPayload):
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    token = create_access_token(user["id"], user["email"])
    return {"token": token, "email": user["email"], "name": user.get("name")}


@app.post("/ingest")
def ingest(payload: IngestPayload):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items provided")
    items = [item.model_dump() for item in payload.items]
    inserted, updated = upsert_opportunities(items)
    return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated}


# ── Opportunities — público por ahora ─────────────────────────────────────────

@app.get("/opportunities")
def opportunities(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    rows = list_opportunities(q=q, limit=limit)
    result = []
    for row in rows:
        r = dict(row)
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
        if r.get("last_signal_at"):
            r["last_signal_at"] = r["last_signal_at"].isoformat()
        result.append(r)
    return {"items": result, "count": len(result)}


# ── Endpoints privados ────────────────────────────────────────────────────────

@app.get("/feed")
def feed(user=Depends(get_current_user)):
    prefs = get_preferences(user["user_id"])
    rows = list_opportunities(q=None, limit=500)
    scored = []
    for row in rows:
        r = dict(row)
        boost = 0
        if prefs:
            if r.get("industry") and r["industry"] in prefs.get("preferred_industries", []):
                boost += 30 * prefs.get("weight_industry", 1.0)
            if r.get("region") and r["region"] in prefs.get("preferred_regions", []):
                boost += 25 * prefs.get("weight_region", 1.0)
            if r.get("phase") and r["phase"] in prefs.get("preferred_phases", []):
                boost += 20 * prefs.get("weight_phase", 1.0)
            if r.get("company") and r["company"] in prefs.get("preferred_companies", []):
                boost += 25 * prefs.get("weight_company", 1.0)
            for kw in prefs.get("keywords", []):
                if kw.lower() in (r.get("title") or "").lower():
                    boost += 15
        r["feed_score"] = (r.get("score") or 0) + boost
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
        scored.append(r)
    scored.sort(key=lambda x: x["feed_score"], reverse=True)
    return scored[:100]


@app.get("/me/preferences")
def get_my_preferences(user=Depends(get_current_user)):
    prefs = get_preferences(user["user_id"])
    return prefs or {}


@app.put("/me/preferences")
def update_preferences(payload: PreferencesPayload, user=Depends(get_current_user)):
    save_preferences(user["user_id"], payload.model_dump())
    return {"ok": True}


# ── Static UI (debe ir al final) ──────────────────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")
