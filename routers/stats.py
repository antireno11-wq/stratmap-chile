"""Stats endpoints para los charts del dashboard."""
from fastapi import APIRouter, Depends, HTTPException, Query

import db
from deps import get_current_user
from source_categories import (
    LICITACION_SOURCES, CONCESION_SOURCES, PROSPECTO_SOURCES,
    NOTICIA_SOURCES, EMPLEO_SOURCES,
)

router = APIRouter(tags=["stats"], dependencies=[Depends(get_current_user)])


@router.get("/stats/timeseries")
def timeseries(days: int = Query(default=30, ge=7, le=180)):
    """Cantidad de oportunidades (no duplicadas) ingestadas por día, por categoría.

    Devuelve `{ dates: [...], series: { licitacion: [...], prospecto: [...],
    noticia: [...], concesion: [...] } }` con `days` puntos.
    """
    sql = """
    WITH days AS (
        SELECT generate_series(
            (NOW() - (%(d)s || ' days')::interval)::date,
            NOW()::date,
            INTERVAL '1 day'
        )::date AS day
    ),
    activity AS (
        SELECT COALESCE(published_at, created_at)::date AS day,
               CASE
                 WHEN source = ANY(%(licit)s)   THEN 'licitacion'
                 WHEN source = ANY(%(prosp)s)   THEN 'prospecto'
                 WHEN source = ANY(%(noticia)s) THEN 'noticia'
                 ELSE 'otros'
               END AS category
        FROM opportunities
        WHERE COALESCE(published_at, created_at) > NOW() - (%(d)s || ' days')::interval
          AND source != 'manual'
          AND source != ALL(%(conce)s)
          AND is_duplicate = FALSE
    )
    SELECT d.day,
           SUM((a.category = 'licitacion')::int) AS licitacion,
           SUM((a.category = 'prospecto')::int)  AS prospecto,
           SUM((a.category = 'noticia')::int)    AS noticia
    FROM days d
    LEFT JOIN activity a ON a.day = d.day
    GROUP BY d.day
    ORDER BY d.day;
    """
    params = {
        "d": days,
        "licit":   LICITACION_SOURCES,
        # SIGEX excluido del display 2026-05 — los registros viejos siguen en la
        # base pero no aparecen en los charts.
        "conce":   CONCESION_SOURCES,
        "prosp":   PROSPECTO_SOURCES,
        "noticia": NOTICIA_SOURCES,
    }
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return {
            "dates":  [r["day"].isoformat() for r in rows],
            "series": {
                "licitacion": [int(r["licitacion"] or 0) for r in rows],
                "prospecto":  [int(r["prospecto"] or 0)  for r in rows],
                "noticia":    [int(r["noticia"] or 0)    for r in rows],
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/by-category")
def by_category(days: int = Query(default=30, ge=7, le=365)):
    """Conteo agregado por categoría en los últimos `days` días. Para donut chart."""
    sql = """
    SELECT
        SUM((source = ANY(%(licit)s))::int)   AS licitacion,
        SUM((source = ANY(%(prosp)s))::int)   AS prospecto,
        SUM((source = ANY(%(noticia)s))::int) AS noticia,
        SUM((source = ANY(%(empleo)s))::int)  AS empleo
    FROM opportunities
    WHERE COALESCE(published_at, created_at) > NOW() - (%(d)s || ' days')::interval
      AND source != 'manual'
      AND source != ALL(%(conce)s)
      AND is_duplicate = FALSE;
    """
    params = {
        "d": days,
        "licit":   LICITACION_SOURCES,
        "conce":   CONCESION_SOURCES,
        "prosp":   PROSPECTO_SOURCES,
        "noticia": NOTICIA_SOURCES,
        "empleo":  EMPLEO_SOURCES,
    }
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone() or {}
        return {
            "licitacion": int(row.get("licitacion") or 0),
            "prospecto":  int(row.get("prospecto")  or 0),
            "noticia":    int(row.get("noticia")    or 0),
            "empleo":     int(row.get("empleo")     or 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
