"""Endpoints /mandantes/* y /faenas."""
import json as _json
import os
import time
from collections import Counter
import ai_client

from fastapi import APIRouter, Depends, HTTPException

import db
from deps import get_current_user
from source_categories import (
    LICITACION_SOURCES, CONCESION_SOURCES, PROSPECTO_SOURCES,
    NOTICIA_SOURCES, EMPLEO_SOURCES,
)

router = APIRouter(tags=["mandantes"], dependencies=[Depends(get_current_user)])

# Cache en memoria del summary IA por empresa
_company_summaries: dict = {}

# Cache en memoria de faenas mineras (24h)
_faenas_cache: dict = {"data": [], "ts": 0}


@router.get("/mandantes")
def get_mandantes():
    """
    Ranking de mandantes por MOVIMIENTO PONDERADO POR CALIDAD DE SEÑAL.

    El score se calcula sumando opportunities.event_weight (calculado por
    scoring_v2 / score_events) en la ventana correspondiente, normalizado
    contra el mejor mandante. Una licitación de 50 MUSD en ENAMI pesa 100;
    una noticia de PR pesa 10. Esto resuelve el problema viejo de que una
    empresa con muchas noticias chatas terminaba más alta que otra con una
    sola licitación grande.

    Devuelve por mandante:
      - score_30d / score_90d: actividad pesada (0-100, normalizada al top).
      - score_prev30:  ventana -60..-30 para tendencia.
      - trend, trend_pct: 'up' (≥+20%), 'down' (≤-20%), 'flat'.
      - breakdown_30d / breakdown_90d: conteos por categoría (licitaciones,
        SEA, noticias, empleos). SIGEX excluido.
      - heat_score / heat_label: capa IA (mandante_scorer) opcional.
    """
    sql = """
    WITH src AS (
        SELECT company, source, COALESCE(jobs_count, 0) AS jobs,
               COALESCE(event_weight, 0) AS w,
               COALESCE(published_at, created_at) AS act_date
        FROM opportunities
        WHERE company IS NOT NULL AND TRIM(company) != ''
          AND source != 'manual'
          AND is_duplicate = FALSE
          AND source != ALL(%(conce)s)
    ),
    base AS (
        SELECT
            company,
            -- Suma pesada por event_weight en cada ventana ───────────────────
            COALESCE(SUM(w) FILTER (WHERE act_date > NOW() - INTERVAL '30 days'), 0) AS weight_30d,
            COALESCE(SUM(w) FILTER (WHERE act_date > NOW() - INTERVAL '90 days'), 0) AS weight_90d,
            COALESCE(SUM(w) FILTER (WHERE act_date BETWEEN NOW() - INTERVAL '60 days' AND NOW() - INTERVAL '30 days'), 0) AS weight_p30,
            -- Breakdowns por categoría (solo conteos, para mostrar al usuario)
            COUNT(*) FILTER (WHERE source = ANY(%(licit)s)   AND act_date > NOW() - INTERVAL '30 days') AS licit_30d,
            COUNT(*) FILTER (WHERE source = ANY(%(prosp)s)   AND act_date > NOW() - INTERVAL '30 days') AS sea_30d,
            COUNT(*) FILTER (WHERE source = ANY(%(noticia)s) AND act_date > NOW() - INTERVAL '30 days') AS news_30d,
            COALESCE(SUM(jobs) FILTER (WHERE source = ANY(%(empleo)s) AND act_date > NOW() - INTERVAL '30 days'), 0) AS jobs_30d,
            COUNT(*) FILTER (WHERE source = ANY(%(licit)s)   AND act_date > NOW() - INTERVAL '90 days') AS licit_90d,
            COUNT(*) FILTER (WHERE source = ANY(%(prosp)s)   AND act_date > NOW() - INTERVAL '90 days') AS sea_90d,
            COUNT(*) FILTER (WHERE source = ANY(%(noticia)s) AND act_date > NOW() - INTERVAL '90 days') AS news_90d,
            COALESCE(SUM(jobs) FILTER (WHERE source = ANY(%(empleo)s) AND act_date > NOW() - INTERVAL '90 days'), 0) AS jobs_90d,
            MAX(act_date) AS last_activity
        FROM src
        GROUP BY company
    ),
    norm AS (
        -- Normalizamos contra el top mandante para que score_30d ∈ [0, 100].
        SELECT (SELECT NULLIF(MAX(weight_30d), 0) FROM base) AS max30,
               (SELECT NULLIF(MAX(weight_90d), 0) FROM base) AS max90,
               (SELECT NULLIF(MAX(weight_p30), 0) FROM base) AS maxp30
    )
    SELECT
        b.company,
        b.weight_30d, b.weight_90d, b.weight_p30,
        b.licit_30d, b.sea_30d, b.news_30d, b.jobs_30d,
        b.licit_90d, b.sea_90d, b.news_90d, b.jobs_90d,
        b.last_activity,
        COALESCE(h.heat_score, 0)                    AS heat_score,
        COALESCE(h.heat_label, '')                   AS heat_label,
        COALESCE(h.heat_reason, '')                  AS heat_reason,
        COALESCE(h.trending_topics, ARRAY[]::text[]) AS trending_topics,
        -- Normalización: weight_30d * 100 / max30, capeado en 100.
        ROUND(LEAST(b.weight_30d * 100.0 / COALESCE(n.max30, 1), 100))::int AS score_30d,
        ROUND(LEAST(b.weight_90d * 100.0 / COALESCE(n.max90, 1), 100))::int AS score_90d,
        ROUND(LEAST(b.weight_p30 * 100.0 / COALESCE(n.maxp30, 1), 100))::int AS score_prev30
    FROM base b
    CROSS JOIN norm n
    LEFT JOIN mandante_heat h ON LOWER(TRIM(h.company)) = LOWER(TRIM(b.company))
    WHERE b.weight_30d > 0 OR b.weight_90d > 0
    ORDER BY b.weight_30d DESC, b.weight_90d DESC
    LIMIT 100;
    """
    params = {
        "licit":   LICITACION_SOURCES,
        # SIGEX excluido (2026-05) tanto del scoring como del breakdown.
        "conce":   CONCESION_SOURCES,
        "prosp":   PROSPECTO_SOURCES,
        "noticia": NOTICIA_SOURCES,
        "empleo":  EMPLEO_SOURCES,
    }
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]

        # Computar tendencia 30d vs prev30d en Python (más legible que en SQL)
        for r in rows:
            s30 = r.get("score_30d") or 0
            sp30 = r.get("score_prev30") or 0
            # Si no había nada antes, cualquier actividad ahora es "up"
            if sp30 == 0:
                trend_pct = 100 if s30 > 0 else 0
            else:
                trend_pct = round((s30 - sp30) / sp30 * 100)
            r["trend_pct"] = trend_pct
            r["trend"] = "up" if trend_pct >= 20 else ("down" if trend_pct <= -20 else "flat")
            r["breakdown_30d"] = {
                "licitaciones": r.pop("licit_30d", 0),
                "sea":          r.pop("sea_30d", 0),
                "news":         r.pop("news_30d", 0),
                "jobs":         r.pop("jobs_30d", 0),
            }
            r["breakdown_90d"] = {
                "licitaciones": r.pop("licit_90d", 0),
                "sea":          r.pop("sea_90d", 0),
                "news":         r.pop("news_90d", 0),
                "jobs":         r.pop("jobs_90d", 0),
            }
            # Weight raw fields ya no se exponen (los usamos para normalizar).
            for k in ("weight_30d", "weight_90d", "weight_p30"):
                r.pop(k, None)
            if r.get("last_activity"):
                r["last_activity"] = r["last_activity"].isoformat()
            if r.get("trending_topics") is None:
                r["trending_topics"] = []

        return {"mandantes": rows, "total": len(rows)}
    except Exception as e:
        import logging
        logging.getLogger("stratmap.mandantes").warning("mandantes query failed", extra={"err": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mandantes/summary/{company_name}")
def get_company_summary(company_name: str):
    """Genera un resumen ejecutivo del mandante usando IA. Cacheado en memoria."""
    key = company_name.lower().strip()
    if key in _company_summaries:
        return _company_summaries[key]

    NEWS_SRC_LIST = NOTICIA_SOURCES
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

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        result = {"summary": None, "error": "no_api_key"}
        _company_summaries[key] = result
        return result

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
        raw = ai_client.call_llm(
            prompt=prompt,
            max_tokens=600,
            model="claude-sonnet-4-6"
        )
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        data = _json.loads(raw)
        result = {
            "company": company_name,
            "summary": data,
            "stats": {
                "n_sigex": stats.get("n_sigex", 0),
                "n_licitaciones": stats.get("n_licitaciones", 0),
                "n_sea": stats.get("n_sea", 0),
                "total_jobs": stats.get("total_jobs", 0),
                "regiones": regiones,
            }
        }
    except Exception as e:
        result = {"company": company_name, "summary": None, "error": str(e)}

    _company_summaries[key] = result
    return result


@router.get("/mandantes/detail")
def get_mandante_detail_q(company: str):
    """Detalle de mandante por query param — evita problemas de encoding en path."""
    return _mandante_detail(company)


@router.get("/mandantes/{company_name}")
def get_mandante_detail(company_name: str):
    """Detalle de un mandante: sus proyectos, SEA y noticias recientes."""
    return _mandante_detail(company_name)


def _mandante_detail(company_name: str):
    """Lógica compartida del detalle de mandante.

    "Proyectos" = todo source de categoría licitacion/concesion (excluye SEA, noticias,
    empleos y manual). SEA va aparte como "prospectos". Las noticias van aparte.
    """
    PROJECT_SOURCES = LICITACION_SOURCES + CONCESION_SOURCES  # SEA va aparte

    STOPWORDS = {'spa','ltda','s.a','s.a.','sa','de','del','la','el',
                 'los','las','y','en','por','para','con','una','uno','minera','minero'}

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, source, score,
                           COALESCE(signal_score,0) AS signal_score,
                           phase, region, url, published_at,
                           COALESCE(jobs_count,0) AS jobs_count
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND source = ANY(%(srcs)s)
                    ORDER BY (score + COALESCE(signal_score,0)) DESC
                    LIMIT 50;
                """, {"company": company_name, "srcs": PROJECT_SOURCES})
                projects = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT id, title, score, phase, region, url, published_at
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND source = 'SEA'
                    ORDER BY score DESC LIMIT 20;
                """, {"company": company_name})
                sea = [dict(r) for r in cur.fetchall()]

                words = [w.lower() for w in company_name.replace('.', ' ').replace(',', ' ').split()
                         if len(w) > 3 and w.lower() not in STOPWORDS]

                cur.execute("""
                    SELECT DISTINCT source FROM opportunities
                    WHERE source NOT IN ('SIGEX','ENAMI','Codelco','SEA','manual','MOP','Chile Compra')
                      AND source IS NOT NULL
                """)
                news_sources_in_db = [r["source"] for r in cur.fetchall()]

                if not news_sources_in_db:
                    news = []
                else:
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

                    if not news:
                        cur.execute("""
                            SELECT id, title, source, url, published_at
                            FROM opportunities
                            WHERE source = ANY(%(sources)s)
                            ORDER BY published_at DESC LIMIT 10;
                        """, {"sources": news_sources_in_db})
                        news = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT services_needed
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%(company)s))
                      AND services_needed IS NOT NULL
                    ORDER BY score DESC LIMIT 30
                """, {"company": company_name})
                services_rows = [r["services_needed"] for r in cur.fetchall()]

        cat_counter = Counter()
        for sn in services_rows:
            if isinstance(sn, dict) and "services" in sn:
                for svc in sn["services"]:
                    cat = svc.get("category") or svc.get("name") or ""
                    if cat:
                        cat_counter[cat] += 1
        top_services = [{"category": k, "count": v} for k, v in cat_counter.most_common(8)]

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
            "top_services": top_services,
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


@router.get("/faenas")
def get_faenas():
    """Lista de faenas mineras activas con coordenadas. Cacheado 24h."""
    global _faenas_cache
    now = time.time()
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


def reset_faenas_cache() -> None:
    """Limpia el cache de faenas. Usado por POST /admin/refresh-faenas."""
    global _faenas_cache
    _faenas_cache = {"data": [], "ts": 0}
