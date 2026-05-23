"""Endpoints de empleos detectados en oportunidades."""
import json as _json

from fastapi import APIRouter, Depends, HTTPException

import db
from deps import get_current_user

router = APIRouter(tags=["empleos"], dependencies=[Depends(get_current_user)])


@router.get("/empleos/resumen")
def get_empleos_resumen():
    """Resumen de empleos disponibles por empresa (mandante).

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
                    'compania minera teck quebrada blanca','teck quebrada blanca',
                    'quebrada blanca','teck resources'
                ) THEN 'TECK QUEBRADA BLANCA'
                WHEN LOWER(TRIM(company)) IN (
                    'compania minera carmen de andacollo','carmen de andacollo',
                    'teck andacollo','minera andacollo'
                ) THEN 'CARMEN DE ANDACOLLO'
                WHEN LOWER(TRIM(company)) IN (
                    'teck chile','teck'
                ) THEN 'TECK CHILE'
                WHEN LOWER(TRIM(company)) IN (
                    'compania minera dona ines de collahuasi',
                    'compañía minera doña inés de collahuasi',
                    'collahuasi','minera collahuasi'
                ) THEN 'COLLAHUASI'
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
        for r in rows:
            if r.get("ultima_senal"):
                r["ultima_senal"] = r["ultima_senal"].isoformat()
            areas = {}
            for detail in (r.get("signal_details") or []):
                if not detail:
                    continue
                try:
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


@router.get("/empleos/empresa/{company_name}")
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
            try:
                d = _json.loads(r["signal_detail"]) if isinstance(r.get("signal_detail"), str) else (r.get("signal_detail") or {})
                r["areas"] = d.get("by_area") or d.get("areas") or {}
            except Exception:
                r["areas"] = {}
        return {"company": company_name, "proyectos": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
