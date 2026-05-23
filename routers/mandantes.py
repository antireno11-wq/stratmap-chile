"""Endpoints /mandantes/* y /faenas."""
import json as _json
import os
import time
from collections import Counter

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
    Ranking de mandantes por actividad consolidada.
    Categoriza cada fuente via source_categories.CATEGORIES.
    """
    from source_categories import LICITACION_SOURCES, CONCESION_SOURCES, PROSPECTO_SOURCES, NOTICIA_SOURCES, EMPLEO_SOURCES

    # Buckets: usamos arrays parametrizados (más seguro que f-string en SQL)
    sql = """
    WITH base AS (
        SELECT
            company,
            COUNT(*) FILTER (WHERE source = ANY(%(licit)s))     AS n_licitaciones,
            COUNT(*) FILTER (WHERE source = ANY(%(conce)s))     AS n_sigex,
            COUNT(*) FILTER (WHERE source = ANY(%(prosp)s))     AS n_sea,
            COUNT(*) FILTER (WHERE source = ANY(%(empleo)s))    AS n_empleos,
            -- "n_proyectos" = licitaciones + concesiones + prospectos (todo lo que es oportunidad real)
            COUNT(*) FILTER (WHERE source = ANY(%(real)s))      AS n_proyectos,
            COALESCE(AVG(score) FILTER (WHERE source = ANY(%(real)s)), 0) AS avg_score,
            MAX(COALESCE(signal_score, 0))                                AS top_signal,
            SUM(COALESCE(jobs_count, 0))                                  AS total_jobs,
            0                                                              AS n_news_recent,
            MAX(COALESCE(published_at, created_at))                       AS last_activity
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
        b.n_empleos,
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
            LEAST(b.avg_score * 0.6, 60) +
            LEAST(b.n_licitaciones * 4, 20) +
            LEAST(b.n_sigex * 0.3, 15) +
            LEAST(b.n_sea * 5, 15) +
            LEAST(b.top_signal, 7) + LEAST(b.total_jobs * 2, 3) +
            LEAST(COALESCE(h.heat_score, 0) * 0.15, 15)
        ) AS score_consolidado
    FROM base b
    LEFT JOIN mandante_heat h ON LOWER(TRIM(h.company)) = LOWER(TRIM(b.company))
    WHERE b.n_proyectos > 0 OR b.n_sea > 0 OR b.n_news_recent > 0
    ORDER BY score_consolidado DESC
    LIMIT 100;
    """
    params = {
        "licit":  LICITACION_SOURCES,
        "conce":  CONCESION_SOURCES,
        "prosp":  PROSPECTO_SOURCES,
        "empleo": EMPLEO_SOURCES,
        "real":   LICITACION_SOURCES + CONCESION_SOURCES + PROSPECTO_SOURCES,
    }
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]

                # Enriquecer con conteo de noticias por keyword
                try:
                    cur.execute("""
                        SELECT title, company
                        FROM opportunities
                        WHERE published_at > NOW() - INTERVAL '90 days'
                          AND source = ANY(%s)
                          AND title IS NOT NULL
                    """, (NOTICIA_SOURCES,))
                    recent_news = cur.fetchall()
                    news_titles = [(r["title"] or "").lower() for r in recent_news]

                    STOPWORDS_N = {'spa','ltda','s.a','s.a.','sa','de','del','la','el',
                                   'los','las','y','en','por','para','con','una','uno',
                                   'minera','minero','compania','compañia','inversiones',
                                   'chile','norte','sur','este','oeste'}
                    for row in rows:
                        name = row.get("company") or ""
                        kws = [w.lower() for w in name.replace("."," ").replace(","," ").split()
                               if len(w) > 3 and w.lower() not in STOPWORDS_N]
                        if not kws:
                            continue
                        count = sum(1 for t in news_titles if any(k in t for k in kws))
                        row["n_news_recent"] = count
                except Exception as ne:
                    print(f"[mandantes] news count error: {ne}")

        for r in rows:
            if r.get("last_activity"):
                r["last_activity"] = r["last_activity"].isoformat()
            if r.get("heat_scored_at"):
                r["heat_scored_at"] = r["heat_scored_at"].isoformat()
            if r.get("trending_topics") is None:
                r["trending_topics"] = []
        return {"mandantes": rows, "total": len(rows)}
    except Exception as e:
        import logging
        logging.getLogger("stratmap.mandantes").warning("mandantes query failed, fallback", extra={"err": str(e)})
        # Fallback sin mandante_heat join (por si mandante_heat no existe en BDs viejas)
        try:
            simple_sql = """
            WITH base AS (
                SELECT company,
                    COUNT(*) FILTER (WHERE source = ANY(%(licit)s))   AS n_licitaciones,
                    COUNT(*) FILTER (WHERE source = ANY(%(conce)s))   AS n_sigex,
                    COUNT(*) FILTER (WHERE source = ANY(%(prosp)s))   AS n_sea,
                    COUNT(*) FILTER (WHERE source = ANY(%(real)s))    AS n_proyectos,
                    COALESCE(AVG(score) FILTER (WHERE source = ANY(%(real)s)), 0) AS avg_score,
                    MAX(COALESCE(signal_score,0))                                  AS top_signal,
                    SUM(COALESCE(jobs_count,0))                                    AS total_jobs,
                    MAX(COALESCE(published_at,created_at))                        AS last_activity
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
                    cur.execute(simple_sql, params)
                    rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                if r.get("last_activity"):
                    r["last_activity"] = r["last_activity"].isoformat()
                r["trending_topics"] = []
            return {"mandantes": rows, "total": len(rows)}
        except Exception as e2:
            raise HTTPException(status_code=500, detail=str(e2))


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
        raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
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
