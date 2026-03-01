from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import csv, io

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
from db import (db_health, init_db_safe, list_opportunities, upsert_opportunities,
                create_user, get_user_by_email, save_preferences, get_preferences,
                create_contact, update_contact, delete_contact,
                get_contacts_by_company, list_contacts, bulk_import_contacts,
                get_pipeline, upsert_pipeline, add_pipeline_note,
                get_pipeline_notes, list_pipeline, PIPELINE_STATUSES)
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

class ContactIn(BaseModel):
    name: str
    company: str
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None

class PipelineUpdate(BaseModel):
    status: str
    assignee: Optional[str] = None

class NoteIn(BaseModel):
    note: str
    author: Optional[str] = None


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

@app.get("/opportunities")
def opportunities(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    rows = list_opportunities(q=q, limit=limit)
    result = []
    for row in rows:
        r = dict(row)
        for f in ["created_at","updated_at","last_signal_at"]:
            if r.get(f): r[f] = r[f].isoformat()
        result.append(r)
    return {"items": result, "count": len(result)}


# ── Pipeline ──────────────────────────────────────────────────────────────────

@app.get("/pipeline")
def get_pipeline_list(status: Optional[str] = Query(default=None)):
    rows = list_pipeline(status=status)
    result = []
    for row in rows:
        r = dict(row)
        if r.get("updated_at"): r["updated_at"] = r["updated_at"].isoformat()
        result.append(r)
    return {"items": result, "count": len(result), "statuses": PIPELINE_STATUSES}

@app.get("/pipeline/statuses")
def get_statuses():
    return {"statuses": PIPELINE_STATUSES}

@app.put("/opportunities/{opportunity_id}/pipeline")
def update_pipeline(opportunity_id: int, payload: PipelineUpdate):
    if payload.status not in PIPELINE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Opciones: {PIPELINE_STATUSES}")
    row = upsert_pipeline(opportunity_id, payload.status, payload.assignee)
    if row.get("updated_at"): row["updated_at"] = row["updated_at"].isoformat()
    if row.get("created_at"): row["created_at"] = row["created_at"].isoformat()
    return row

@app.get("/opportunities/{opportunity_id}/pipeline")
def get_opp_pipeline(opportunity_id: int):
    row = get_pipeline(opportunity_id)
    if not row:
        return {"opportunity_id": opportunity_id, "status": None, "assignee": None}
    if row.get("updated_at"): row["updated_at"] = row["updated_at"].isoformat()
    if row.get("created_at"): row["created_at"] = row["created_at"].isoformat()
    return row

@app.post("/opportunities/{opportunity_id}/notes")
def add_note(opportunity_id: int, payload: NoteIn):
    row = add_pipeline_note(opportunity_id, payload.note, payload.author)
    if row.get("created_at"): row["created_at"] = row["created_at"].isoformat()
    return row

@app.get("/opportunities/{opportunity_id}/notes")
def get_notes(opportunity_id: int):
    rows = get_pipeline_notes(opportunity_id)
    result = []
    for row in rows:
        r = dict(row)
        if r.get("created_at"): r["created_at"] = r["created_at"].isoformat()
        result.append(r)
    return {"items": result}


# ── Contactos ─────────────────────────────────────────────────────────────────

@app.get("/contacts")
def get_contacts(
    q: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    if company:
        rows = get_contacts_by_company(company)
    else:
        rows = list_contacts(q=q, limit=limit)
    result = []
    for row in rows:
        r = dict(row)
        for f in ["created_at","updated_at"]:
            if r.get(f): r[f] = r[f].isoformat()
        result.append(r)
    return {"items": result, "count": len(result)}

@app.post("/contacts")
def add_contact(payload: ContactIn):
    row = create_contact(payload.model_dump())
    for f in ["created_at","updated_at"]:
        if row.get(f): row[f] = row[f].isoformat()
    return row

@app.put("/contacts/{contact_id}")
def edit_contact(contact_id: int, payload: ContactUpdate):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    row = update_contact(contact_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    for f in ["created_at","updated_at"]:
        if row.get(f): row[f] = row[f].isoformat()
    return row

@app.delete("/contacts/{contact_id}")
def remove_contact(contact_id: int):
    ok = delete_contact(contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return {"ok": True}

@app.post("/contacts/import")
def import_contacts(payload: List[ContactIn]):
    contacts = [c.model_dump() for c in payload]
    inserted, errors = bulk_import_contacts(contacts)
    return {"ok": True, "inserted": inserted, "errors": errors}

@app.get("/contacts/export")
def export_contacts():
    rows = list_contacts(limit=10000)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","name","company","role","email","phone","linkedin_url","notes","created_at"])
    writer.writeheader()
    for row in rows:
        r = dict(row)
        if r.get("created_at"): r["created_at"] = r["created_at"].isoformat()
        writer.writerow({k: r.get(k,"") for k in writer.fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contactos_stratmap.csv"}
    )


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
        for f in ["created_at","updated_at"]:
            if r.get(f): r[f] = r[f].isoformat()
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


# ── AI Matching ───────────────────────────────────────────────────────────────

class ServiceItem(BaseModel):
    name: str
    description: Optional[str] = None

class ServiceProfilePayload(BaseModel):
    company_name: Optional[str] = None
    services: List[ServiceItem] = []

@app.get("/me/service-profile")
def get_service_profile_endpoint():
    profile = db.get_service_profile("default")
    return profile or {"company_name": None, "services": []}

@app.put("/me/service-profile")
def update_service_profile(payload: ServiceProfilePayload):
    db.init_ai_db()
    profile = db.upsert_service_profile(
        user_id="default",
        company_name=payload.company_name or "",
        services=[s.model_dump() for s in payload.services]
    )
    return {"ok": True, "profile": profile}

@app.get("/ai/fits")
def get_ai_fits(min_score: int = 40, limit: int = 200):
    try:
        items = db.list_top_ai_fits(user_id="default", min_score=min_score, limit=limit)
        for r in items:
            for f in ["created_at","updated_at","scored_at"]:
                if r.get(f): r[f] = r[f].isoformat()
        return {"items": items, "total": len(items)}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}

@app.get("/opportunities/{opp_id}/ai-fit")
def get_opportunity_ai_fit(opp_id: int):
    try:
        fit = db.get_ai_fit(opp_id, "default")
        if fit and fit.get("scored_at"):
            fit["scored_at"] = fit["scored_at"].isoformat()
        return fit or {}
    except Exception:
        return {}

@app.post("/admin/run-ai-matcher")
def trigger_ai_matcher():
    import subprocess, sys
    try:
        result = subprocess.Popen(
            [sys.executable, "ai_matcher.py", "default"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return {"ok": True, "pid": result.pid, "message": "AI matcher iniciado en background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/admin/fix-chilebcompra")
def fix_chilebcompra():
    """Normaliza source ChileCompra → Chile Compra y sube scores de MOP."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Fix source name
                cur.execute("""
                    UPDATE opportunities
                    SET source = 'Chile Compra'
                    WHERE source = 'ChileCompra';
                """)
                fixed_source = cur.rowcount
                # Fix MOP scores — subir base de 30 a 50
                cur.execute("""
                    UPDATE opportunities
                    SET score = LEAST(score + 20, 82)
                    WHERE source = 'MOP' AND score < 60;
                """)
                fixed_mop = cur.rowcount
            conn.commit()
        return {"ok": True, "fixed_source": fixed_source, "fixed_mop_scores": fixed_mop}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/chilebcompra-debug")
def chilebcompra_debug():
    """Llama directamente a la API de ChileCompra y muestra los campos reales."""
    try:
        import requests as req
        ticket = "F8537A18-6766-4DEF-9E59-426B4FEE2844"
        url = f"https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?buscar=mineria&ticket={ticket}&cantidad=1"
        r = req.get(url, timeout=20)
        data = r.json()
        # Intentar por fecha de hoy si keyword no funciona
        items = data.get("Listado") or []
        if not items:
            from datetime import datetime
            today = datetime.now().strftime("%d%m%Y")
            url2 = f"https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?fecha={today}&ticket={ticket}"
            r2 = req.get(url2, timeout=20)
            data2 = r2.json()
            items = data2.get("Listado") or []
            if not items:
                return {"error": "sin resultados en ningún endpoint", "data_kw": data, "data_fecha": data2}
        item = items[0]
        return {"keys": list(item.keys()), "sample": item}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/sources-summary")
def sources_summary():
    """Muestra cuántos registros hay por source y su score promedio."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT source, COUNT(*) as total, 
                           ROUND(AVG(score)) as avg_score,
                           MAX(score) as max_score,
                           MIN(score) as min_score
                    FROM opportunities
                    GROUP BY source
                    ORDER BY total DESC;
                """)
                rows = cur.fetchall()
        return {"sources": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Static UI (debe ir al final) ──────────────────────────────────────────────


@app.post("/admin/delete-non-mining")
def delete_non_mining():
    """Elimina todos los proyectos que no son de industria Minería o Energía minera."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Contar antes
                cur.execute("SELECT COUNT(*) as n FROM opportunities")
                total_before = cur.fetchone()["n"]

                # Eliminar no-minería (conservar Minería, Energía, y NULL para revisar)
                cur.execute("""
                    DELETE FROM opportunities 
                    WHERE industry NOT IN ('Minería', 'Energía')
                    AND industry IS NOT NULL
                """)
                deleted = cur.rowcount

                # También eliminar MOP (infraestructura vial pura)
                cur.execute("""
                    DELETE FROM opportunities
                    WHERE source = 'MOP'
                    AND NOT (
                        title ILIKE '%mina%' OR title ILIKE '%minera%' OR
                        title ILIKE '%cobre%' OR title ILIKE '%litio%' OR
                        title ILIKE '%codelco%' OR title ILIKE '%faena%'
                    )
                """)
                deleted_mop = cur.rowcount

                cur.execute("SELECT COUNT(*) as n FROM opportunities")
                total_after = cur.fetchone()["n"]

            conn.commit()
        return {
            "before": total_before,
            "after": total_after,
            "deleted_non_mining": deleted,
            "deleted_mop_non_mining": deleted_mop
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/delete-chilebcompra")
def delete_chilebcompra():
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'Chile Compra'")
                deleted = cur.rowcount
            conn.commit()
        return {"deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/", StaticFiles(directory="static", html=True), name="static")
