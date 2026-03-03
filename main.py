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
    company_key: Optional[str] = None
    services: List[Any] = []        # acepta strings o {name, description}
    regions: List[str] = []
    contract_sizes: List[str] = []
    known_mandantes: List[str] = []
    onboarding_done: bool = False

@app.get("/me/service-profile")
def get_service_profile_endpoint():
    profile = db.get_service_profile("default")
    return profile or {"company_name": None, "services": []}

@app.put("/me/service-profile")
def update_service_profile(payload: ServiceProfilePayload):
    db.init_ai_db()
    company_key = payload.company_key or "default"
    # Normalizar services: strings → {"name": str}, objetos → mantener
    def normalize_service(s):
        if isinstance(s, str): return {"name": s, "description": ""}
        if hasattr(s, "model_dump"): return s.model_dump()
        if isinstance(s, dict): return s
        return {"name": str(s), "description": ""}

    profile = db.upsert_service_profile(
        user_id=company_key,
        company_key=company_key,
        company_name=payload.company_name or "",
        services=[normalize_service(s) for s in payload.services],
        regions=payload.regions or [],
        contract_sizes=payload.contract_sizes or [],
        known_mandantes=payload.known_mandantes or [],
        onboarding_done=payload.onboarding_done,
    )
    return {"ok": True, "profile": profile}



@app.get("/mandantes")
def get_mandantes():
    """
    Ranking de mandantes por actividad consolidada.
    Incluye cualquier mandante con proyectos reales (ENAMI, Codelco, SIGEX, SEA).
    """
    NEWS_SOURCES = (
        "'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',"
        "'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',"
        "'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS'"
    )
    sql = f"""
    WITH base AS (
        SELECT
            company,
            COUNT(*) FILTER (WHERE source NOT IN ({NEWS_SOURCES}, 'SEA', 'manual'))
                AS n_proyectos,
            COUNT(*) FILTER (WHERE source IN ('ENAMI','Codelco'))
                AS n_licitaciones,
            COUNT(*) FILTER (WHERE source = 'SIGEX')
                AS n_sigex,
            COUNT(*) FILTER (WHERE source = 'SEA')
                AS n_sea,
            COALESCE(AVG(score) FILTER (
                WHERE source NOT IN ({NEWS_SOURCES}, 'SEA', 'manual')
            ), 0)                                       AS avg_score,
            MAX(COALESCE(signal_score, 0))              AS top_signal,
            SUM(COALESCE(jobs_count, 0))                AS total_jobs,
            COUNT(*) FILTER (
                WHERE published_at > NOW() - INTERVAL '90 days'
                AND source NOT IN ({NEWS_SOURCES}, 'manual')
                AND source IN ({NEWS_SOURCES})
            ) AS n_news_recent,
            MAX(COALESCE(published_at, created_at))     AS last_activity
        FROM opportunities
        WHERE company IS NOT NULL AND TRIM(company) != ''
          AND source != 'manual'
        GROUP BY company
    )
    SELECT
        company,
        n_proyectos,
        n_licitaciones,
        n_sigex,
        n_sea,
        top_signal      AS signal_score,
        total_jobs,
        n_news_recent,
        last_activity,
        ROUND(
            -- Score promedio de proyectos (base, max 60)
            LEAST(avg_score * 0.6, 60) +
            -- Licitaciones directas tienen más peso (max 20)
            LEAST(n_licitaciones * 4, 20) +
            -- SIGEX: exploración activa (max 15)
            LEAST(n_sigex * 0.3, 15) +
            -- SEA: proyecto grande en evaluación (max 15)
            LEAST(n_sea * 5, 15) +
            -- Señal de empleo (max 10)
            LEAST(top_signal, 7) + LEAST(total_jobs * 2, 3)
        ) AS score_consolidado
    FROM base
    WHERE n_proyectos > 0 OR n_sea > 0
    ORDER BY score_consolidado DESC
    LIMIT 100;
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
        # Serialize dates
        for r in rows:
            if r.get("last_activity"):
                r["last_activity"] = r["last_activity"].isoformat()
        return {"mandantes": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/mandantes/detail")
def get_mandante_detail_q(company: str):
    """Detalle de mandante por query param — evita problemas de encoding en path."""
    return _mandante_detail(company)

@app.get("/mandantes/{company_name}")
def get_mandante_detail(company_name: str):
    """Detalle de un mandante: sus proyectos, SEA y noticias recientes."""
    return _mandante_detail(company_name)

def _mandante_detail(company_name: str):
    """Lógica compartida del detalle de mandante."""
    NEWS_SOURCES = (
        "'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',"
        "'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',"
        "'Radio U. de Chile','Radio Universidad de Chile','BioBioChile'"
    )
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Proyectos activos — todo lo que NO es noticia ni SEA
                # Búsqueda case-insensitive para tolerar variaciones de nombre
                cur.execute(f"""
                    SELECT id, title, source, score,
                           COALESCE(signal_score,0) AS signal_score,
                           phase, region, url, published_at,
                           COALESCE(jobs_count,0) AS jobs_count
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND source NOT IN ({NEWS_SOURCES}, 'SEA', 'manual')
                    ORDER BY (score + COALESCE(signal_score,0)) DESC
                    LIMIT 50;
                """, {"company": company_name})
                projects = [dict(r) for r in cur.fetchall()]

                # Prospectos SEA
                cur.execute("""
                    SELECT id, title, score, phase, region, url, published_at
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND source = 'SEA'
                    ORDER BY score DESC LIMIT 20;
                """, {"company": company_name})
                sea = [dict(r) for r in cur.fetchall()]

                # Noticias recientes (90 días)
                # Las noticias no tienen company asignado, buscar por nombre en título
                # Usar las primeras 2 palabras del nombre para el match
                words = [w for w in company_name.split() if len(w) > 3]
                kw = words[0] if words else company_name
                cur.execute(f"""
                    SELECT id, title, source, url, published_at
                    FROM opportunities
                    WHERE source IN ({NEWS_SOURCES})
                      AND published_at > NOW() - INTERVAL '180 days'
                      AND (
                          LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                          OR LOWER(title) LIKE %(kw)s
                      )
                    ORDER BY published_at DESC LIMIT 15;
                """, {"company": company_name, "kw": f"%{kw.lower()}%"})
                news = [dict(r) for r in cur.fetchall()]

        # Serialize dates
        for lst in [projects, sea, news]:
            for r in lst:
                if r.get("published_at"):
                    r["published_at"] = r["published_at"].isoformat()

        return {
            "company": company_name,
            "projects": projects,
            "proyectos": projects,
            "sea": sea,
            "sea_prospectos": sea,
            "news": news,
            "noticias": news,
            "summary": {
                "n_proyectos": len(projects),
                "n_sea": len(sea),
                "n_news": len(news),
                "total_signal": sum(r.get("signal_score") or 0 for r in projects),
                "total_jobs": sum(r.get("jobs_count") or 0 for r in projects),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/me/score-projects")
def score_projects(payload: dict):
    """
    Dispara scoring IA personalizado para todos los proyectos contra el perfil de la empresa.
    Corre en background — el frontend puede polling /ai/fits para ver cuando hay resultados.
    """
    import threading
    company_key = payload.get("company_key", "default")

    def _run():
        try:
            import ai_matcher
            result = ai_matcher.run(company_key=company_key, limit=500)
            print(f"[score-projects] {result}")
        except Exception as e:
            import traceback; traceback.print_exc()

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring IA iniciado en background", "company_key": company_key}


@app.get("/me/profile")
def get_profile(company_key: str = "default"):
    """Retorna el perfil completo incluyendo onboarding_done."""
    profile = db.get_service_profile(company_key)
    if not profile:
        return {"onboarding_done": False, "services": [], "company_name": None}
    return profile


@app.get("/ai/fits")
def get_ai_fits(company_key: str = "default", min_score: int = 0, limit: int = 500):
    """Retorna los scores IA calculados para la empresa."""
    try:
        fits = db.get_ai_fits(user_id=company_key, min_score=min_score, limit=limit)
        return {"fits": fits, "total": len(fits)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/run-ai-scoring")
def run_ai_scoring_all():
    """Corre scoring IA para todos los perfiles con onboarding completo."""
    import threading
    def _run():
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT company_key FROM service_profiles
                        WHERE onboarding_done = TRUE AND services IS NOT NULL AND services != '[]'
                    """)
                    rows = cur.fetchall()
            keys = [r[0] for r in rows if r[0]]
            print(f"[admin-ai] Perfiles a procesar: {keys}")
            import ai_matcher
            for key in keys:
                print(f"[admin-ai] Procesando {key}...")
                ai_matcher.run(company_key=key, limit=500)
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring IA masivo iniciado"}

@app.post("/admin/mark-onboarding-done")
def mark_onboarding_done():
    """Marca todos los perfiles existentes con servicios como onboarding_done=true."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE service_profiles
                    SET onboarding_done = TRUE
                    WHERE services != '[]' AND services IS NOT NULL
                """)
                updated = cur.rowcount
            conn.commit()
        return {"updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/sources-count")
def sources_count():
    """Muestra cuántos registros hay por source — útil para diagnóstico."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) as n,
                       ROUND(AVG(score)) as avg_score,
                       MIN(published_at::date) as oldest,
                       MAX(published_at::date) as newest
                FROM opportunities
                GROUP BY source ORDER BY n DESC;
            """)
            rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        for k in ['oldest','newest']:
            if r.get(k): r[k] = str(r[k])
    return {"sources": rows}


@app.delete("/admin/delete-source/{source_name}")
def delete_source(source_name: str):
    """Elimina todos los registros de una fuente específica."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM opportunities WHERE source = %(s)s", {"s": source_name})
            deleted = cur.rowcount
        conn.commit()
    return {"deleted": deleted, "source": source_name}


@app.post("/admin/run-sigex")
def run_sigex():
    """Ingesta manual del SIGEX Sernageomin (proyectos de exploración)."""
    import threading
    def _run():
        try:
            from connectors.sigex_sernageomin import fetch_sigex
            items = fetch_sigex(limit=5000)
            if not items:
                print("[sigex] Sin items retornados")
                return
            inserted, updated = db.upsert_opportunities(items)
            print(f"[sigex] insertados={inserted}, actualizados={updated}, total={len(items)}")
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Ingesta SIGEX iniciada en background"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
