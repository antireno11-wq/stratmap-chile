from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import csv, io

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
from db import (db_health, init_db_safe, list_opportunities, upsert_opportunities,
                recalc_all_scores,
                create_user, get_user_by_email, save_preferences, get_preferences,
                create_contact, update_contact, delete_contact,
                get_contacts_by_company, list_contacts, bulk_import_contacts,
                get_pipeline, upsert_pipeline, add_pipeline_note,
                get_pipeline_notes, list_pipeline, PIPELINE_STATUSES)
from auth import hash_password, verify_password, create_access_token, decode_token

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_safe()
    try:
        db.init_ai_db()
    except Exception as e:
        print(f"[startup] init_ai_db warning: {e}")
    # Recalcular scores con el scoring engine al arrancar
    try:
        result = recalc_all_scores()
        print(f"[startup] Scores recalculados: {result['total_updated']} actualizados de {result['total_rows']} total")
        print(f"[startup] Distribución: {result['distribution']}")
    except Exception as e:
        print(f"[startup] Warning recalc scores: {e}")

    # Normalizar source 'sea' → 'SEA' (inconsistencia en datos)
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE opportunities SET source = 'SEA' WHERE source = 'sea'")
                n = cur.rowcount
            conn.commit()
        if n: print(f"[startup] Normalizado {n} registros 'sea' → 'SEA'")
    except Exception as e:
        print(f"[startup] Warning SEA normalize: {e}")

    # Noticias no deben tener score — reset al arrancar
    try:
        NEWS_SRCS = [
            'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',
            'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',
            'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
        ]
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE opportunities SET score = 0, signal_score = 0 WHERE source = ANY(%s) AND score > 0",
                    (NEWS_SRCS,)
                )
            conn.commit()
        print("[startup] Scores de noticias reseteados a 0")
    except Exception as e:
        print(f"[startup] Warning reset news scores: {e}")
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

@app.get("/noticias")
def get_noticias(limit: int = Query(default=50, ge=1, le=200)):
    """Noticias recientes del sector minero."""
    NEWS_SOURCES = [
        'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',
        'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',
        'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
    ]
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, source, title, url, company, industry, region,
                           score, published_at, created_at
                    FROM opportunities
                    WHERE source = ANY(%s)
                    ORDER BY COALESCE(published_at, created_at) DESC NULLS LAST
                    LIMIT %s
                """, (NEWS_SOURCES, limit))
                rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for f in ['published_at','created_at']:
                if r.get(f): r[f] = r[f].isoformat()
        return {"items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
                AND source IN ({NEWS_SOURCES})
            ) AS n_news_recent,
            MAX(COALESCE(published_at, created_at))     AS last_activity
        FROM opportunities
        WHERE company IS NOT NULL AND TRIM(company) != ''
          AND source != 'manual'
        GROUP BY company
    )
    SELECT
        b.company,
        b.n_proyectos,
        b.n_licitaciones,
        b.n_sigex,
        b.n_sea,
        b.top_signal                            AS signal_score,
        b.total_jobs,
        b.n_news_recent,
        b.last_activity,
        COALESCE(h.heat_score, 0)               AS heat_score,
        COALESCE(h.heat_label, '')              AS heat_label,
        COALESCE(h.heat_reason, '')             AS heat_reason,
        COALESCE(h.trending_topics, ARRAY[]::text[]) AS trending_topics,
        h.scored_at                             AS heat_scored_at,
        ROUND(
            -- Score promedio de proyectos (base, max 60)
            LEAST(b.avg_score * 0.6, 60) +
            -- Licitaciones directas tienen más peso (max 20)
            LEAST(b.n_licitaciones * 4, 20) +
            -- SIGEX: exploración activa (max 15)
            LEAST(b.n_sigex * 0.3, 15) +
            -- SEA: proyecto grande en evaluación (max 15)
            LEAST(b.n_sea * 5, 15) +
            -- Señal de empleo (max 10)
            LEAST(b.top_signal, 7) + LEAST(b.total_jobs * 2, 3) +
            -- Heat IA: boost por actividad reciente (max 15)
            LEAST(COALESCE(h.heat_score, 0) * 0.15, 15)
        ) AS score_consolidado
    FROM base b
    LEFT JOIN (
        SELECT * FROM mandante_heat
        WHERE 1=1
    ) h ON LOWER(TRIM(h.company)) = LOWER(TRIM(b.company))
    WHERE b.n_proyectos > 0 OR b.n_sea > 0 OR b.n_news_recent > 0
    ORDER BY score_consolidado DESC
    LIMIT 100;
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
        # Serialize dates + convert arrays
        for r in rows:
            if r.get("last_activity"):
                r["last_activity"] = r["last_activity"].isoformat()
            if r.get("heat_scored_at"):
                r["heat_scored_at"] = r["heat_scored_at"].isoformat()
            # trending_topics may come as None
            if r.get("trending_topics") is None:
                r["trending_topics"] = []
        return {"mandantes": rows, "total": len(rows)}
    except Exception as e:
        print(f"[mandantes] Error: {e}")
        # Si falla por mandante_heat inexistente, reintentar sin heat join
        try:
            simple_sql = f"""
            WITH base AS (
                SELECT company,
                    COUNT(*) FILTER (WHERE source NOT IN ({NEWS_SOURCES}, 'SEA', 'manual')) AS n_proyectos,
                    COUNT(*) FILTER (WHERE source IN ('ENAMI','Codelco')) AS n_licitaciones,
                    COUNT(*) FILTER (WHERE source = 'SIGEX') AS n_sigex,
                    COUNT(*) FILTER (WHERE source = 'SEA') AS n_sea,
                    COALESCE(AVG(score) FILTER (WHERE source NOT IN ({NEWS_SOURCES},'SEA','manual')),0) AS avg_score,
                    MAX(COALESCE(signal_score,0)) AS top_signal,
                    SUM(COALESCE(jobs_count,0)) AS total_jobs,
                    MAX(COALESCE(published_at,created_at)) AS last_activity
                FROM opportunities
                WHERE company IS NOT NULL AND TRIM(company) != '' AND source != 'manual'
                GROUP BY company
            )
            SELECT company, n_proyectos, n_licitaciones, n_sigex, n_sea,
                   top_signal AS signal_score, total_jobs, last_activity,
                   0 AS heat_score, '' AS heat_label, '' AS heat_reason,
                   ARRAY[]::text[] AS trending_topics, NULL AS heat_scored_at,
                   ROUND(LEAST(avg_score*0.6,60)+LEAST(n_licitaciones*4,20)+LEAST(n_sigex*0.3,15)+LEAST(n_sea*5,15)+LEAST(top_signal,7)+LEAST(total_jobs*2,3)) AS score_consolidado
            FROM base WHERE n_proyectos > 0 OR n_sea > 0
            ORDER BY score_consolidado DESC LIMIT 100;
            """
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(simple_sql)
                    rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                if r.get("last_activity"):
                    r["last_activity"] = r["last_activity"].isoformat()
                r["trending_topics"] = []
            return {"mandantes": rows, "total": len(rows)}
        except Exception as e2:
            raise HTTPException(status_code=500, detail=str(e2))

# Cache en memoria para no regenerar en cada visita
_company_summaries: dict = {}

@app.get("/mandantes/summary/{company_name}")
def get_company_summary(company_name: str):
    """
    Genera un resumen ejecutivo del mandante usando IA.
    Se cachea en memoria durante la sesión.
    """
    import os, json as _json

    key = company_name.lower().strip()
    if key in _company_summaries:
        return _company_summaries[key]

    # Recolectar contexto de la BD
    NEWS_SRC_LIST = [
        'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',
        'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',
        'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
    ]
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE source = 'SIGEX') as n_sigex,
                       COUNT(*) FILTER (WHERE source IN ('ENAMI','Codelco')) as n_licitaciones,
                       COUNT(*) FILTER (WHERE source = 'SEA') as n_sea,
                       SUM(COALESCE(jobs_count,0)) as total_jobs,
                       array_agg(DISTINCT region) FILTER (WHERE region IS NOT NULL) as regiones,
                       array_agg(DISTINCT phase) FILTER (WHERE phase IS NOT NULL) as fases,
                       MAX(published_at) as ultima_actividad
                FROM opportunities
                WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(c)s))
                  AND source != 'manual'
            """, {"c": company_name})
            stats = dict(cur.fetchone() or {})

            cur.execute("""
                SELECT title FROM opportunities
                WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(c)s))
                  AND source = ANY(%(news)s)
                ORDER BY published_at DESC LIMIT 5
            """, {"c": company_name, "news": NEWS_SRC_LIST})
            recent_news = [r["title"] for r in cur.fetchall()]

            cur.execute("""
                SELECT title, source FROM opportunities
                WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(c)s))
                  AND source NOT IN ('SEA','manual')
                  AND source != ANY(%(news)s)
                ORDER BY (score + COALESCE(signal_score,0)) DESC LIMIT 5
            """, {"c": company_name, "news": NEWS_SRC_LIST})
            top_projects = [f"{r['title']} ({r['source']})" for r in cur.fetchall()]

    # Construir prompt para Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        result = {"summary": None, "error": "no_api_key"}
        _company_summaries[key] = result
        return result

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    regiones = [r for r in (stats.get("regiones") or []) if r][:5]
    prompt = f"""Eres un analista del sector minero chileno. Genera un resumen ejecutivo conciso de esta empresa para profesionales del sector.

EMPRESA: {company_name}

DATOS EN BD STRATMAP:
- Concesiones SIGEX: {stats.get("n_sigex",0)}
- Licitaciones (ENAMI/Codelco): {stats.get("n_licitaciones",0)}
- Prospectos SEA: {stats.get("n_sea",0)}
- Empleos detectados: {stats.get("total_jobs",0)}
- Regiones activas: {", ".join(regiones) if regiones else "—"}
- Proyectos destacados: {"; ".join(top_projects[:3]) if top_projects else "—"}
- Noticias recientes: {"; ".join(recent_news[:3]) if recent_news else "—"}

Responde SOLO JSON sin markdown:
{{
  "descripcion": "<2-3 oraciones sobre qué hace esta empresa en minería chilena, sus operaciones principales y relevancia en el sector>",
  "presencia_chile": "<1 oración sobre su presencia geográfica y escala de operaciones en Chile>",
  "actividad_reciente": "<1 oración sobre su actividad más reciente según los datos>",
  "tipo": "<uno de: Gran Minería | Mediana Minería | Junior Explorer | Proveedor Minero | Empresa Estatal | Consultora>",
  "minerales_principales": ["mineral1", "mineral2"],
  "regiones_clave": ["region1", "region2"]
}}"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = _json.loads(raw)
        result = {
            "company": company_name,
            "summary": data,
            "stats": {
                "n_sigex": stats.get("n_sigex",0),
                "n_licitaciones": stats.get("n_licitaciones",0),
                "n_sea": stats.get("n_sea",0),
                "total_jobs": stats.get("total_jobs",0),
                "regiones": regiones,
            }
        }
    except Exception as e:
        result = {"company": company_name, "summary": None, "error": str(e)}

    _company_summaries[key] = result
    return result

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

    # Lista exhaustiva de sources de noticias — todo lo que no sea proyecto real
    NON_PROJECT_SOURCES = (
        "'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',"
        "'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',"
        "'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',"
        "'BHP Careers','manual'"
    )

    STOPWORDS = {'spa','ltda','s.a','s.a.','sa','de','del','la','el',
                 'los','las','y','en','por','para','con','una','uno','minera','minero'}

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:

                # Proyectos activos
                cur.execute(f"""
                    SELECT id, title, source, score,
                           COALESCE(signal_score,0) AS signal_score,
                           phase, region, url, published_at,
                           COALESCE(jobs_count,0) AS jobs_count
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND source NOT IN ({NON_PROJECT_SOURCES}, 'SEA')
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

                # ── Noticias ──────────────────────────────────────────────────
                # Estrategia en capas:
                # 1. Noticias con company exacto
                # 2. Noticias con keywords del nombre en el título
                # 3. Si aún no hay, mostrar noticias recientes del sector (fallback)

                # Extraer keywords del nombre
                words = [w.lower() for w in company_name.replace('.',' ').replace(',',' ').split()
                         if len(w) > 3 and w.lower() not in STOPWORDS]

                # Obtener todos los sources que existen en la BD (para no hardcodear)
                cur.execute("""
                    SELECT DISTINCT source FROM opportunities
                    WHERE source NOT IN ('SIGEX','ENAMI','Codelco','SEA','manual','MOP','Chile Compra')
                      AND source IS NOT NULL
                """)
                news_sources_in_db = [r["source"] for r in cur.fetchall()]

                if not news_sources_in_db:
                    news = []
                else:
                    # Query 1: por company exacto o keywords
                    kw_conds = ""
                    kw_params = {}
                    if words:
                        kw_conds = " OR " + " OR ".join(
                            f"LOWER(title) LIKE %(kw{i})s" for i in range(len(words))
                        )
                        kw_params = {f"kw{i}": f"%{w}%" for i, w in enumerate(words)}

                    cur.execute("""
                        SELECT id, title, source, url, published_at
                        FROM opportunities
                        WHERE source = ANY(%(sources)s)
                          AND (
                              LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                              {kw_conds}
                          )
                        ORDER BY published_at DESC LIMIT 15;
                    """.format(kw_conds=kw_conds),
                    {**{"sources": news_sources_in_db, "company": company_name}, **kw_params})
                    news = [dict(r) for r in cur.fetchall()]

                    # Fallback: si no encontró nada, traer las últimas noticias del sector
                    if not news:
                        cur.execute("""
                            SELECT id, title, source, url, published_at
                            FROM opportunities
                            WHERE source = ANY(%(sources)s)
                            ORDER BY published_at DESC LIMIT 10;
                        """, {"sources": news_sources_in_db})
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

# ── Faenas Mineras ─────────────────────────────────────────────────────────────

_faenas_cache: dict = {"data": [], "ts": 0}

@app.get("/faenas")
def get_faenas():
    """
    Lista de faenas mineras activas con coordenadas.
    Se cachea en memoria 24h para no golpear la API en cada carga de mapa.
    """
    import time
    global _faenas_cache
    now = time.time()
    # Cache de 24 horas
    if _faenas_cache["data"] and (now - _faenas_cache["ts"]) < 86400:
        return {"faenas": _faenas_cache["data"], "total": len(_faenas_cache["data"]), "cached": True}
    try:
        from faenas_mineras import fetch_faenas
        data = fetch_faenas(limit=2000)
        _faenas_cache = {"data": data, "ts": now}
        return {"faenas": data, "total": len(data), "cached": False}
    except Exception as e:
        if _faenas_cache["data"]:
            return {"faenas": _faenas_cache["data"], "total": len(_faenas_cache["data"]), "cached": True}
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/refresh-faenas")
def refresh_faenas():
    """Fuerza recarga del cache de faenas mineras."""
    global _faenas_cache
    _faenas_cache = {"data": [], "ts": 0}
    return {"ok": True, "msg": "Cache de faenas limpiado, próxima llamada a /faenas recargará"}

# ── Empleos por empresa ────────────────────────────────────────────────────────

@app.get("/empleos/resumen")
def get_empleos_resumen():
    """
    Resumen de empleos disponibles por empresa (mandante).
    Muestra movimiento de contratación activa en el sector minero.
    Normaliza nombres de empresa para consolidar duplicados (BHP, Escondida, etc.)
    """
    NEWS_SRC = (
        "'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',"
        "'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',"
        "'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS','manual'"
    )
    sql = f"""
    WITH normalized AS (
        SELECT
            CASE
                WHEN LOWER(TRIM(company)) IN (
                    'bhp','bhp chile','bhp chile inc','minera escondida',
                    'escondida','minera spence','spence','cas plazo fijo',
                    'bhp billiton','bhp chile ltda'
                ) THEN 'BHP CHILE INC'
                WHEN LOWER(TRIM(company)) IN (
                    'antofagasta minerals','amsa','amsa - corporativo',
                    'antofagasta minerals s.a.'
                ) THEN 'ANTOFAGASTA MINERALS'
                WHEN LOWER(TRIM(company)) IN (
                    'minera centinela','centinela'
                ) THEN 'MINERA CENTINELA'
                WHEN LOWER(TRIM(company)) IN (
                    'minera los pelambres','los pelambres','pelambres'
                ) THEN 'MINERA LOS PELAMBRES'
                WHEN LOWER(TRIM(company)) IN (
                    'minera zaldivar','minera zaldívar','compania minera zaldivar',
                    'compañía minera zaldívar'
                ) THEN 'MINERA ZALDIVAR'
                WHEN LOWER(TRIM(company)) IN (
                    'minera candelaria','candelaria','scm minera lumina copper chile',
                    'lumina copper','lundin mining'
                ) THEN 'MINERA CANDELARIA'
                WHEN LOWER(TRIM(company)) IN (
                    'codelco','corporacion nacional del cobre','corporación nacional del cobre'
                ) THEN 'CODELCO'
                ELSE UPPER(TRIM(company))
            END AS company_norm,
            jobs_count, signal_score, last_signal_at, signal_detail
        FROM opportunities
        WHERE company IS NOT NULL AND TRIM(company) != ''
          AND source NOT IN ({NEWS_SRC})
          AND (jobs_count > 0 OR signal_score > 0)
    )
    SELECT
        company_norm                                    AS company,
        SUM(COALESCE(jobs_count, 0))                    AS total_jobs,
        MAX(COALESCE(signal_score, 0))                  AS top_signal,
        COUNT(*) FILTER (WHERE jobs_count > 0)          AS proyectos_con_empleos,
        COUNT(*) FILTER (WHERE signal_score > 0)        AS proyectos_con_senal,
        MAX(last_signal_at)                             AS ultima_senal,
        array_agg(DISTINCT signal_detail) FILTER (
            WHERE signal_detail IS NOT NULL AND (jobs_count > 0 OR signal_score > 0)
        ) AS signal_details
    FROM normalized
    GROUP BY company_norm
    HAVING SUM(COALESCE(jobs_count,0)) + MAX(COALESCE(signal_score,0)) > 0
    ORDER BY total_jobs DESC, top_signal DESC
    LIMIT 30;
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
        # Parsear signal_details para extraer áreas
        for r in rows:
            if r.get("ultima_senal"):
                r["ultima_senal"] = r["ultima_senal"].isoformat()
            # Parsear desglose de áreas desde signal_details
            areas = {}
            for detail in (r.get("signal_details") or []):
                if not detail:
                    continue
                try:
                    import json as _json
                    d = _json.loads(detail) if isinstance(detail, str) else detail
                    for area, cnt in (d.get("by_area") or d.get("areas") or {}).items():
                        areas[area] = areas.get(area, 0) + int(cnt)
                except Exception:
                    pass
            r["areas"] = areas
            del r["signal_details"]
        return {"empresas": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/empleos/empresa/{company_name}")
def get_empleos_empresa(company_name: str):
    """Detalle de empleos por proyecto para una empresa específica."""
    sql = """
    SELECT id, title, region, phase, jobs_count, signal_score,
           signal_detail, last_signal_at, url
    FROM opportunities
    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
      AND jobs_count > 0
    ORDER BY jobs_count DESC, signal_score DESC
    LIMIT 50;
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"company": company_name})
                rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("last_signal_at"):
                r["last_signal_at"] = r["last_signal_at"].isoformat()
            # Parsear áreas del signal_detail
            try:
                import json as _json
                d = _json.loads(r["signal_detail"]) if isinstance(r.get("signal_detail"), str) else (r.get("signal_detail") or {})
                r["areas"] = d.get("by_area") or d.get("areas") or {}
            except Exception:
                r["areas"] = {}
        return {"company": company_name, "proyectos": rows, "total": len(rows)}
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

@app.get("/admin/debug-noticias")
def debug_noticias(company: str = "Codelco"):
    """Debug: diagnostico completo de noticias en BD."""
    NEWS_LIST = [
        'Lithium Chile','Portal Minero','Revista EI','Mineria Chilena',
        'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Mineria',
        'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
    ]
    STOPWORDS = {'spa','ltda','de','del','la','el','los','las','y','en','por','para','con'}
    words = [w.lower() for w in company.replace('.',' ').split()
             if len(w) > 3 and w.lower() not in STOPWORDS]
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT source, COUNT(*) as n FROM opportunities GROUP BY source ORDER BY n DESC LIMIT 40")
                all_sources = [{"source": r["source"], "n": r["n"]} for r in cur.fetchall()]

                cur.execute("SELECT COUNT(*) as n FROM opportunities WHERE source = ANY(%s)", (NEWS_LIST,))
                row = cur.fetchone()
                total_news = int(row["n"]) if row else 0

                cur.execute("""
                    SELECT title, source, COALESCE(company,'-') as company,
                           CAST(published_at AS TEXT) as published_at
                    FROM opportunities WHERE source = ANY(%s)
                    ORDER BY published_at DESC NULLS LAST LIMIT 5
                """, (NEWS_LIST,))
                latest_news = [dict(r) for r in cur.fetchall()]

                kw_hits = {}
                for kw in words[:6]:
                    cur.execute("SELECT COUNT(*) as n FROM opportunities WHERE source = ANY(%s) AND LOWER(title) LIKE %s",
                                (NEWS_LIST, f"%{kw}%"))
                    row2 = cur.fetchone()
                    kw_hits[kw] = int(row2["n"]) if row2 else 0

                cur.execute("""
                    SELECT title, source, CAST(published_at AS TEXT) as published_at
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%s)) AND source = ANY(%s)
                    ORDER BY published_at DESC NULLS LAST LIMIT 5
                """, (company, NEWS_LIST))
                by_exact = [dict(r) for r in cur.fetchall()]

                query_result = []
                if words:
                    kw_parts = [f"LOWER(title) LIKE '%%{w}%%'" for w in words[:4]]
                    kw_cond = " OR ".join(kw_parts)
                    cur.execute(f"""
                        SELECT title, source, COALESCE(company,'-') as company,
                               CAST(published_at AS TEXT) as published_at
                        FROM opportunities
                        WHERE source = ANY(%s)
                          AND (LOWER(TRIM(company)) = LOWER(TRIM(%s)) OR ({kw_cond}))
                        ORDER BY published_at DESC NULLS LAST LIMIT 10
                    """, (NEWS_LIST, company))
                    query_result = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "company_buscada": company,
            "keywords_extraidas": words,
            "total_noticias_en_bd": total_news,
            "todos_los_sources": all_sources,
            "ultimas_5_noticias": latest_news,
            "noticias_exactas_por_company": by_exact,
            "hits_por_keyword": kw_hits,
            "resultado_query_final": query_result,
            "diagnostico": "OK" if query_result else ("Sin noticias en BD - correr worker" if total_news == 0 else "Noticias en BD pero no matchean"),
        }
    except Exception as e:
        import traceback as tb
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[:2000]}

@app.post("/admin/run-bhp-careers")
def run_bhp_careers():
    """Scraping de empleos BHP Chile — inline, sin módulo externo."""
    import traceback as tb, requests as _req, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    SEARCH_URL = (
        "https://careers.bhp.com/search/"
        "?createNewAlert=false&q=&optionsFacetsDD_location=Chile"
    )
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    }
    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","mecanico","instrumentista"],
        "Ingeniería":    ["engineer","ingeniero","specialist","especialista","lead","principal","tecnico"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning"],
        "TI / Datos":    ["digital","data","ai","autonomous","autonomia","ahs","software"],
        "RRHH":          ["training","capacit","rrhh","people","talento"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud"],
        "Proyectos":     ["project","proyecto","inversiones","transactions"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws):
                return area
        return "Otros"

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'BHP Careers'")
                deleted = cur.rowcount
            conn.commit()

        # Scrape
        resp = _req.get(SEARCH_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        jobs = []
        seen = set()
        for a in soup.select("table a[href*='/job/']"):
            raw_title = a.get_text(strip=True)
            if not raw_title or len(raw_title) < 5: continue
            href = a.get("href","")
            url = ("https://careers.bhp.com" + href) if href.startswith("/") else href
            if url in seen: continue
            seen.add(url)
            parts = raw_title.split("|")
            title   = parts[0].strip()
            empresa = parts[1].strip() if len(parts) > 1 else "BHP"
            jobs.append({"title": title, "empresa": empresa, "area": classify(title), "url": url})

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en BHP Chile", "deleted": deleted}

        # Normalizar nombres de empresa BHP → entidad canónica
        BHP_NORMALIZE = {
            "bhp":                    "BHP CHILE INC",
            "bhp chile":              "BHP CHILE INC",
            "bhp chile inc":          "BHP CHILE INC",
            "minera escondida":       "BHP CHILE INC",
            "escondida":              "BHP CHILE INC",
            "minera spence":          "BHP CHILE INC",
            "spence":                 "BHP CHILE INC",
            "cas plazo fijo":         "BHP CHILE INC",
            "bhp billiton":           "BHP CHILE INC",
        }
        for j in jobs:
            key = j["empresa"].lower().strip()
            j["empresa"] = BHP_NORMALIZE.get(key, j["empresa"])

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs: by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total = len(emp_jobs)
            areas = {}
            for j in emp_jobs: areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ","-")
            opps.append({
                "source": "BHP Careers",
                "title": f"Empleos BHP Chile — {empresa} ({total} cargos)",
                "company": empresa,
                "industry": "Minería",
                "phase": "Contratación activa",
                "region": "Chile",
                "score": 0,
                "url": f"https://careers.bhp.com/chile/{slug}",
                "published_at": now.isoformat(),
                "entry": f"{empresa}: {total} cargos disponibles en Chile.\n\n{cargo_list}",
                "jobs_count": total,
                "signal_score": min(total * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total, "fuente": "BHP Careers"}, ensure_ascii=False),
                "raw": {"by_area": areas, "empleos": [j["url"] for j in emp_jobs]},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": list(by_emp.keys()),
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}

@app.post("/admin/run-amsa-careers")
def run_amsa_careers():
    """Scraping de empleos Antofagasta Minerals (AMSA) — Pelambres, Centinela, Zaldívar, AMSA."""
    import traceback as tb, requests as _req, re as _re, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    BASE_URL = "https://career8.successfactors.com"
    LIST_URL = BASE_URL + "/career?company=AMSAP&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH"
    HEADERS  = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    }

    # Normalizar empresa AMSA a nombre canónico en Stratmap
    AMSA_COMPANIES = {
        "pelambres":   "MINERA LOS PELAMBRES",
        "centinela":   "MINERA CENTINELA",
        "zaldivar":    "COMPANIA MINERA ZALDIVAR",
        "zaldívar":    "COMPANIA MINERA ZALDIVAR",
        "amsa":        "ANTOFAGASTA MINERALS",
        "corporativo": "ANTOFAGASTA MINERALS",
    }

    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion","planta"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","eléctrico","mecanico","instrumentista"],
        "Ingeniería":    ["engineer","ingeniero","ingeniera","specialist","especialista","senior","tecnic"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning","gestor"],
        "TI / Datos":    ["digital","data","sistemas","software","ti ","tecnolog"],
        "RRHH":          ["training","capacit","rrhh","people","talento","personas"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador","superintendenta"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud","prevencion"],
        "Proyectos":     ["project","proyecto","inversiones","construccion","ejecucion"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws): return area
        return "Otros"

    def empresa_from_meta(meta):
        m = meta.lower()
        for key, name in AMSA_COMPANIES.items():
            if key in m: return name
        return "ANTOFAGASTA MINERALS"

    def get_page(page_no, session):
        params = {"company": "AMSAP", "career_ns": "job_listing_summary",
                  "navBarLevel": "JOB_SEARCH", "pageNo": page_no}
        r = session.get(BASE_URL + "/career", params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'AMSA Careers'")
                deleted = cur.rowcount
            conn.commit()

        session = _req.Session()
        jobs = []

        # Primera página — detectar total de páginas
        soup = get_page(1, session)
        pager = soup.get_text()
        # "Página 1 de 3" → extraer el último número
        m = _re.search(r'[Pp][áa]gina\s+\d+\s+de\s+(\d+)', pager)
        if not m:
            m = _re.search(r'Page\s+\d+\s+of\s+(\d+)', pager)
        total_pages = int(m.group(1)) if m else 1

        def parse_jobs(soup):
            # SuccessFactors muestra empleos como links dentro de tablas o divs
            # Estructura: <a href="/career?...jobId=XXXXX">Título del cargo</a>
            # Seguido de texto: "ID de solicitud de puesto: XXXXX - Publicado el DD/MM/YYYY - EMPRESA"
            seen_ids = set()
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if 'jobId' not in href and 'job_id' not in href and 'requisitionId' not in href:
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                job_url = (BASE_URL + href) if href.startswith('/') else href
                # Extraer ID del puesto para deduplicar
                id_m = _re.search(r'[jJ]ob[Ii]d=(\d+)|requisitionId=(\d+)', href)
                job_id = (id_m.group(1) or id_m.group(2)) if id_m else href[-8:]
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                # El texto del contenedor padre tiene la empresa y fecha
                container = a.parent
                for _ in range(4):  # subir hasta 4 niveles
                    if container and container.name in ('td', 'div', 'li', 'tr'):
                        break
                    container = container.parent if container else None
                meta = container.get_text(separator=' ', strip=True) if container else ''
                empresa = empresa_from_meta(meta)
                date_m = _re.search(r'(\d{2}/\d{2}/\d{4})', meta)
                fecha = date_m.group(1) if date_m else ''
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "job_id": job_id,
                    "fecha": fecha, "url": job_url,
                })

        parse_jobs(soup)
        for p in range(2, total_pages + 1):
            s = get_page(p, session)
            parse_jobs(s)

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en AMSA", "deleted": deleted}

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs: by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total = len(emp_jobs)
            areas = {}
            for j in emp_jobs: areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ", "-")
            opps.append({
                "source": "AMSA Careers",
                "title": f"Empleos AMSA — {empresa} ({total} cargos)",
                "company": empresa,
                "industry": "Minería",
                "phase": "Contratación activa",
                "region": "Chile",
                "score": 0,
                "url": f"https://career8.successfactors.com/amsa/{slug}",
                "published_at": now.isoformat(),
                "entry": f"{empresa}: {total} cargos disponibles.\n\n{cargo_list}",
                "jobs_count": total,
                "signal_score": min(total * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total, "fuente": "AMSA Careers"}, ensure_ascii=False),
                "raw": {"by_area": areas},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": {e: len(j) for e, j in by_emp.items()},
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}

@app.post("/admin/recalcular-scores")
def admin_recalcular_scores():
    """
    Recalcula scores de todos los proyectos usando el scoring engine de Stratmap.
    Aplica la función calc_score() a cada registro y actualiza la BD.
    """
    import traceback as tb
    try:
        result = recalc_all_scores()
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@app.post("/admin/run-lundin-careers")
def run_lundin_careers():
    """Scraping de empleos Lundin Mining Chile — Minera Candelaria (Tierra Amarilla)."""
    import traceback as tb, requests as _req, re as _re, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    BASE_URL  = "https://jobs.lundinmining.com"
    # Filtrar solo Chile — país CL
    SEARCH_URL = BASE_URL + "/search/?createNewAlert=false&q=&optionsFacetsDD_country=CL"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Mapeo de Business Unit → empresa canónica Stratmap
    LUNDIN_COMPANIES = {
        "candelaria":  "MINERA CANDELARIA",
        "lumina":      "SCM MINERA LUMINA COPPER CHILE",
        "lundin":      "MINERA CANDELARIA",
    }

    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion","planta","minero"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","eléctrico","mecanico","instrumentista","mecánico"],
        "Ingeniería":    ["engineer","ingeniero","ingeniera","specialist","especialista","senior","tecnic","metalurgista"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion","geologo"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning","gestor","contador"],
        "TI / Datos":    ["digital","data","sistemas","software","ti ","tecnolog","it "],
        "RRHH":          ["training","capacit","rrhh","people","talento","personas","recursos humanos"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador","superintendenta","lider","líder"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud","prevencion","prevención"],
        "Proyectos":     ["project","proyecto","inversiones","construccion","ejecucion","construcción"],
        "Supply Chain":  ["supply","cadena","logistic","logística","compras","abastecimiento","bodega"],
        "Procesamiento": ["procesamiento","processamento","metalurg","hidrometalurg","pirometalurg"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws): return area
        return "Otros"

    def empresa_from_bu(business_unit, location):
        bu = (business_unit or "").lower()
        loc = (location or "").lower()
        for key, name in LUNDIN_COMPANIES.items():
            if key in bu or key in loc: return name
        return "MINERA CANDELARIA"  # Default Chile = Candelaria

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'Lundin Careers'")
                deleted = cur.rowcount
            conn.commit()

        session = _req.Session()
        jobs = []

        def parse_page(soup):
            # SuccessFactors: cada empleo es un <li> con un <a href="/job/...">
            for li in soup.select("ul.jobs-list li, #career-section li, li[class*='job']"):
                a = li.select_one("a[href*='/job/']")
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) < 4:
                    continue
                href = a.get("href", "")
                job_url = (BASE_URL + href) if href.startswith("/") else href

                # Extraer metadata del li
                text = li.get_text(separator=" ", strip=True)
                # Business Unit y location
                bu_m  = _re.search(r'Business Unit\s+(\S[^\n]+?)(?:\s{2,}|Department|Location|$)', text)
                loc_m = _re.search(r'Location\s+(\S[^\n]+?)(?:\s{2,}|Business|Department|$)', text)
                bu    = bu_m.group(1).strip() if bu_m else ""
                loc   = loc_m.group(1).strip() if loc_m else ""
                empresa = empresa_from_bu(bu, loc)
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "url": job_url,
                    "bu": bu, "loc": loc,
                })

        # Página 1
        r = session.get(SEARCH_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        parse_page(soup)

        # Detectar paginación
        pager_text = soup.get_text()
        m = _re.search(r'[Ss]howing\s+\d+\s+to\s+\d+\s+of\s+(\d+)', pager_text)
        total = int(m.group(1)) if m else len(jobs)
        per_page = 10  # SuccessFactors default
        total_pages = max(1, -(-total // per_page))  # ceil division

        for page in range(2, total_pages + 1):
            r2 = session.get(SEARCH_URL + f"&page={page}", headers=HEADERS, timeout=20)
            r2.raise_for_status()
            soup2 = BeautifulSoup(r2.text, "html.parser")
            parse_page(soup2)

        # Si parse falló (0 jobs), intentar selector alternativo
        if not jobs:
            # Fallback: buscar todos los links /job/ en la página
            for a in soup.find_all("a", href=_re.compile(r"/job/")):
                title = a.get_text(strip=True)
                if not title or len(title) < 4:
                    continue
                href = a.get("href", "")
                job_url = (BASE_URL + href) if href.startswith("/") else href
                # Extraer empresa de la URL o texto cercano
                container = a.parent
                for _ in range(5):
                    if container and container.name in ("li", "div", "tr", "article"):
                        break
                    container = container.parent if container else None
                meta = container.get_text(separator=" ", strip=True) if container else ""
                empresa = empresa_from_bu(meta, meta)
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "url": job_url,
                    "bu": "", "loc": "",
                })
            # Deduplicar por URL
            seen = set()
            unique = []
            for j in jobs:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    unique.append(j)
            jobs = unique

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en Lundin Mining Chile", "deleted": deleted}

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs:
            by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total_emp = len(emp_jobs)
            areas = {}
            for j in emp_jobs:
                areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ", "-").replace(".", "")
            opps.append({
                "source":      "Lundin Careers",
                "title":       f"Empleos Lundin Mining Chile — {empresa} ({total_emp} cargos)",
                "company":     empresa,
                "industry":    "Minería",
                "phase":       "Contratación activa",
                "region":      "Atacama",
                "score":       0,
                "url":         f"https://jobs.lundinmining.com/chile/{slug}",
                "published_at": now.isoformat(),
                "entry":       f"{empresa}: {total_emp} cargos disponibles.\n\n{cargo_list}",
                "jobs_count":  total_emp,
                "signal_score": min(total_emp * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total_emp, "fuente": "Lundin Careers"}, ensure_ascii=False),
                "raw":         {"by_area": areas, "empleos": [j["url"] for j in emp_jobs]},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": {e: len(j) for e, j in by_emp.items()},
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@app.post("/admin/run-mandante-scorer")
def run_mandante_scorer():
    """Dispara scoring de temperatura de mandantes con IA."""
    import threading
    def _run():
        try:
            import mandante_scorer
            db.init_ai_db()
            result = mandante_scorer.run()
            print(f"[admin] Mandante scorer: {result}")
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring de temperatura iniciado en background"}

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

# Rutas explícitas para páginas HTML (fallback si static/ no las encuentra)
from fastapi.responses import FileResponse
import os as _os

def _static(filename):
    """Sirve un archivo desde static/ con fallback."""
    path = _os.path.join("static", filename)
    if _os.path.exists(path):
        return FileResponse(path)
    return {"detail": "Not Found"}, 404

@app.get("/mandantes.html", include_in_schema=False)
def serve_mandantes(): return _static("mandantes.html")

@app.get("/mandante.html", include_in_schema=False)
def serve_mandante(): return _static("mandante.html")

@app.get("/mapa.html", include_in_schema=False)
def serve_mapa(): return _static("mapa.html")

@app.get("/kanban.html", include_in_schema=False)
def serve_kanban(): return _static("kanban.html")

@app.get("/preferences.html", include_in_schema=False)
def serve_preferences(): return _static("preferences.html")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
