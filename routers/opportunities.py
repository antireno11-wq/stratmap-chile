"""Endpoints de opportunities, noticias, feed e ingest."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import db
from deps import get_current_user, require_admin, require_feature
from plans import features_for
from schemas import IngestPayload
from source_categories import NOTICIA_SOURCES, category_of

router = APIRouter(tags=["opportunities"])


@router.post("/ingest", dependencies=[Depends(require_admin)])
def ingest(payload: IngestPayload):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items provided")
    items = [item.model_dump() for item in payload.items]
    inserted, updated = db.upsert_opportunities(items)
    return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated}


@router.get("/opportunities")
def opportunities(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    all: bool = Query(default=False, description="Si true, ignora las preferencias del usuario y devuelve todo."),
    user=Depends(get_current_user),
):
    # Cap por plan: max_opps_per_day
    plan = db.get_user_plan(user["user_id"])
    cap = features_for(plan.get("plan", "free")).get("max_opps_per_day", 20)
    if limit > cap:
        limit = cap
    rows = db.list_opportunities(q=q, limit=limit)
    if not all:
        prefs = db.get_preferences(user["user_id"]) or {}
        industries = set(prefs.get("preferred_industries") or [])
        regions    = set(prefs.get("preferred_regions") or [])
        if industries:
            rows = [r for r in rows if not r.get("industry") or r["industry"] in industries]
        if regions:
            rows = [r for r in rows if not r.get("region") or r["region"] in regions]
    result = []
    for row in rows:
        r = dict(row)
        r["category"] = category_of(r.get("source", ""))
        for f in ["created_at", "updated_at", "last_signal_at"]:
            if r.get(f):
                r[f] = r[f].isoformat()
        result.append(r)
    return {"items": result, "count": len(result)}


@router.get("/noticias", dependencies=[Depends(get_current_user)])
def get_noticias(limit: int = Query(default=50, ge=1, le=200)):
    """Noticias recientes del sector minero."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, source, title, url, company, industry, region,
                           score, published_at, created_at
                    FROM opportunities
                    WHERE source = ANY(%s) AND is_duplicate = FALSE
                    ORDER BY COALESCE(published_at, created_at) DESC NULLS LAST
                    LIMIT %s
                """, (NOTICIA_SOURCES, limit))
                rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for f in ['published_at', 'created_at']:
                if r.get(f):
                    r[f] = r[f].isoformat()
        return {"items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feed")
def feed(user=Depends(get_current_user)):
    prefs = db.get_preferences(user["user_id"])
    # Cap por plan: max_opps_per_day también acota /feed
    plan = db.get_user_plan(user["user_id"])
    cap = features_for(plan.get("plan", "free")).get("max_opps_per_day", 20)
    rows = db.list_opportunities(q=None, limit=max(500, cap))
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
        r["category"] = category_of(r.get("source", ""))
        for f in ["created_at", "updated_at"]:
            if r.get(f):
                r[f] = r[f].isoformat()
        scored.append(r)
    scored.sort(key=lambda x: x["feed_score"], reverse=True)
    return scored[:cap]


@router.get("/opportunities/{opp_id}/services", dependencies=[Depends(get_current_user)])
def get_opportunity_services(opp_id: int):
    """Retorna los servicios necesarios analizados para un proyecto."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, company, region, phase, score, services_needed
                    FROM opportunities WHERE id = %s
                """, (opp_id,))
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        return {
            "id": row["id"],
            "title": row["title"],
            "company": row["company"],
            "region": row["region"],
            "phase": row["phase"],
            "score": row["score"],
            "services_needed": row["services_needed"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunities/{opp_id}/analyze-services",
             dependencies=[Depends(require_feature("ai_matching"))])
def analyze_opportunity_services(opp_id: int):
    """Analiza on-demand (IA) qué servicios requerirá un proyecto y guarda el resultado.

    Gated a planes con `ai_matching` (Pro/Team): el análisis consume IA, así que no se
    expone a usuarios free. Reemplaza la llamada rota a /admin/run-demand-intel (admin-only)
    que la UI hacía desde el drawer."""
    try:
        import demand_intel
        result = demand_intel.analyze_opportunity(opp_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo analizar el proyecto: {e}")
    if not result:
        raise HTTPException(status_code=422, detail="No se pudo generar el análisis para este proyecto")
    return {"ok": True, "services_needed": result}


@router.get("/opportunities/services/search", dependencies=[Depends(get_current_user)])
def search_by_service(
    q: str = Query(..., description="Rubro o servicio a buscar (ej: 'sondaje', 'campamento')"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Busca proyectos que van a necesitar un servicio específico."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, company, region, phase, score, services_needed
                    FROM opportunities
                    WHERE services_needed IS NOT NULL
                      AND services_needed::text ILIKE %s
                    ORDER BY score DESC
                    LIMIT %s
                """, (f"%{q}%", limit))
                rows = cur.fetchall()
        results = []
        for row in rows:
            services = row["services_needed"]
            matched_services = []
            if services and "services" in services:
                for svc in services["services"]:
                    if q.lower() in (svc.get("name", "") + svc.get("description", "") + svc.get("category", "")).lower():
                        matched_services.append(svc)
            results.append({
                "id": row["id"],
                "title": row["title"],
                "company": row["company"],
                "region": row["region"],
                "phase": row["phase"],
                "score": row["score"],
                "matched_services": matched_services,
                "horizon_months": services.get("horizon_months") if services else None,
                "phase_label": services.get("phase_label") if services else None,
            })
        return {"results": results, "count": len(results), "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
