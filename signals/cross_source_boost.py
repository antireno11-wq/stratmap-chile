"""
signals/cross_source_boost.py — Boost de confianza por confirmación multi-fuente
==================================================================================
Si el mismo proyecto aparece en 2+ fuentes (ej: SEA + noticia CMF + empleo),
es mucho más probable que sea real y esté activo.

Lógica:
  1. Agrupa proyectos por empresa + región
  2. Detecta clusters: misma empresa, misma región, fuentes distintas
  3. Aplica signal_boost proporcional al número de fuentes confirmando
  4. Registra en raw.cross_source_confirmed + signal_score

Boost:
  2 fuentes → +8 pts
  3 fuentes → +14 pts
  4+ fuentes → +20 pts
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db
import json
import logging
import re
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# Fuentes que son "confirmación real" (no noticias duplicadas)
CONFIRMING_SOURCES = {
    "SEA", "SIGEX", "Codelco", "ENAMI", "MOP", "COCHILCO",
    "CMF", "Ariba", "manual",
}
# Noticias/empleos son señales de actividad, no de existencia del proyecto
SIGNAL_SOURCES = {
    "BHP Careers", "AMSA Careers", "Lundin Careers", "Collahuasi Careers", "Teck Careers",
    "Portal Minero", "Minería Chilena", "Mundo Minería", "Lithium Chile",
    "InfoMineria", "Revista EI", "COCHILCO Noticias",
}

REGION_ALIASES: Dict[str, str] = {
    "antofagasta": "antofagasta", "ii región": "antofagasta", "ii region": "antofagasta",
    "atacama": "atacama", "iii región": "atacama",
    "tarapacá": "tarapaca", "tarapaca": "tarapaca", "i región": "tarapaca",
    "coquimbo": "coquimbo", "iv región": "coquimbo",
    "arica": "arica", "parinacota": "arica",
    "o'higgins": "ohiggins", "ohiggins": "ohiggins",
    "metropolitana": "rm", "rm": "rm",
}

COMPANY_CANONICAL: Dict[str, str] = {
    "codelco": "codelco", "corporación nacional del cobre": "codelco",
    "bhp": "bhp", "escondida": "bhp", "minera escondida": "bhp", "bhp billiton": "bhp",
    "sqm": "sqm", "soquimich": "sqm",
    "collahuasi": "collahuasi", "doña inés de collahuasi": "collahuasi",
    "antofagasta minerals": "antofagasta", "antofagasta plc": "antofagasta",
    "los pelambres": "antofagasta", "centinela": "antofagasta",
    "teck": "teck", "quebrada blanca": "teck", "carmen de andacollo": "teck",
    "enami": "enami", "empresa nacional de minería": "enami",
    "kinross": "kinross", "la coipa": "kinross",
    "barrick": "barrick", "lundin": "lundin", "candelaria": "lundin",
    "anglo american": "angloamerican", "los bronces": "angloamerican",
    "cap ": "cap", "cap minería": "cap",
    "capstone": "capstone",
}


def _normalize_company(company: str) -> str:
    c = (company or "").lower().strip()
    for kw, canon in COMPANY_CANONICAL.items():
        if kw in c:
            return canon
    return c[:30] if c else ""


def _normalize_region(region: str) -> str:
    r = (region or "").lower().strip()
    for kw, canon in REGION_ALIASES.items():
        if kw in r:
            return canon
    return r[:20] if r else ""


def run() -> dict:
    """
    Detecta proyectos confirmados por múltiples fuentes y aplica boost.
    """
    # 1. Traer todos los proyectos reales (no noticias)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, company, region, source, score, signal_score, raw
                FROM opportunities
                WHERE company IS NOT NULL
                  AND source != 'manual'
                  AND phase != 'Noticia'
                  AND phase != 'Hecho Esencial'
                ORDER BY company, region
            """)
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {"clusters": 0, "boosted": 0}

    # 2. Agrupar por (company_canonical, region_canonical)
    clusters: Dict[str, List[dict]] = {}
    for row in rows:
        company_key = _normalize_company(row.get("company") or "")
        region_key  = _normalize_region(row.get("region") or "")
        if not company_key:
            continue
        key = f"{company_key}|{region_key}"
        clusters.setdefault(key, []).append(row)

    # 3. Para cada cluster con 2+ fuentes distintas → aplicar boost
    updates = []
    n_clusters = 0

    for key, group in clusters.items():
        sources_present: Set[str] = set()
        project_ids = []
        for row in group:
            src = row.get("source") or ""
            sources_present.add(src)
            project_ids.append(row["id"])

        confirming = sources_present & CONFIRMING_SOURCES
        signals    = sources_present & SIGNAL_SOURCES
        n_confirming = len(confirming)

        if n_confirming < 2:
            continue  # solo 1 fuente confirmadora → no aplica boost

        n_clusters += 1

        if n_confirming >= 4:  boost = 20
        elif n_confirming >= 3: boost = 14
        else:                   boost = 8

        # Bonus extra si hay señales de empleo además
        if signals:
            boost = min(boost + 5, 25)

        confirmed_meta = {
            "confirming_sources": sorted(confirming),
            "signal_sources": sorted(signals),
            "n_confirming": n_confirming,
            "boost_applied": boost,
        }

        for row in group:
            # Solo boosteamos proyectos en fuentes confirmadoras, no noticias
            if (row.get("source") or "") not in CONFIRMING_SOURCES:
                continue
            new_signal = min(100, (row.get("signal_score") or 0) + boost)
            updates.append({
                "id": row["id"],
                "signal_score": new_signal,
                "meta": json.dumps(confirmed_meta, ensure_ascii=False),
            })

    if updates:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for u in updates:
                    cur.execute("""
                        UPDATE opportunities
                        SET signal_score = %(signal_score)s,
                            raw = COALESCE(raw, '{}'::jsonb) || jsonb_build_object(
                                'cross_source_confirmed', %(meta)s::jsonb
                            ),
                            last_signal_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %(id)s
                    """, u)
            conn.commit()

    logger.info(f"[cross_source] {n_clusters} clusters, {len(updates)} proyectos boosteados")
    return {"clusters": n_clusters, "boosted": len(updates)}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = run()
    print(result)
