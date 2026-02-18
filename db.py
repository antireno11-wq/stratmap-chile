import os
import time
from typing import Optional, List, Dict, Any, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL no está seteada en Railway")
    return url


def get_conn():
    return psycopg.connect(_db_url(), row_factory=dict_row)


DDL = """
CREATE TABLE IF NOT EXISTS opportunities (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    company TEXT,
    contractor TEXT,
    industry TEXT,
    region TEXT,
    phase TEXT,
    score INT DEFAULT 0,
    entry TEXT,
    raw JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_opps_score ON opportunities(score DESC);
CREATE INDEX IF NOT EXISTS idx_opps_company ON opportunities(company);
CREATE INDEX IF NOT EXISTS idx_opps_industry ON opportunities(industry);
"""


def init_db_safe(retries: int = 12, sleep_s: float = 2.0) -> None:
    """
    Intenta levantar DB; si no puede, no revienta el server.
    """
    last_err = None
    for _ in range(retries):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(DDL)
                conn.commit()
            return
        except Exception as e:
            last_err = e
            time.sleep(sleep_s)

    # no revienta, pero deja registro en logs
    print(f"[db] init_db_safe: no pude conectar/crear tablas: {type(last_err).__name__}: {last_err}")


def db_health() -> Tuple[bool, str]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok;")
                _ = cur.fetchone()
        return True, "ok"
    except Exception as e:
        return False, f"db error: {type(e).__name__}: {e}"


def upsert_opportunities(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert por url. Devuelve inserted/updated como enteros (sin listas/tuplas raras).
    """
    inserted = 0
    updated = 0

    sql = """
    INSERT INTO opportunities
        (source, title, url, company, contractor, industry, region, phase, score, entry, raw)
    VALUES
        (%(source)s, %(title)s, %(url)s, %(company)s, %(contractor)s, %(industry)s,
         %(region)s, %(phase)s, %(score)s, %(entry)s, %(raw)s)
    ON CONFLICT (url) DO UPDATE SET
        source = EXCLUDED.source,
        title = EXCLUDED.title,
        company = EXCLUDED.company,
        contractor = EXCLUDED.contractor,
        industry = EXCLUDED.industry,
        region = EXCLUDED.region,
        phase = EXCLUDED.phase,
        score = EXCLUDED.score,
        entry = EXCLUDED.entry,
        raw = EXCLUDED.raw,
        updated_at = now()
    RETURNING (xmax = 0) AS inserted;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                # defensivo: si viene cualquier cosa rara, normalizamos
                payload = {
                    "source": str(it.get("source") or "manual"),
                    "title": str(it.get("title") or "").strip(),
                    "url": str(it.get("url") or "").strip(),
                    "company": (it.get("company") or None),
                    "contractor": (it.get("contractor") or None),
                    "industry": (it.get("industry") or None),
                    "region": (it.get("region") or None),
                    "phase": (it.get("phase") or None),
                    "score": int(it.get("score") or 0),
                    "entry": (it.get("entry") or None),
                    # raw debe ser JSONB -> Json(dict)
                    "raw": Json(it.get("raw")) if isinstance(it.get("raw"), (dict, list)) else Json({}) if it.get("raw") is None else Json({"raw": str(it.get("raw"))}),
                }

                if not payload["title"] or not payload["url"]:
                    continue

                cur.execute(sql, payload)
                row = cur.fetchone()  # {"inserted": True/False}
                was_insert = bool(row["inserted"]) if row and "inserted" in row else False
                if was_insert:
                    inserted += 1
                else:
                    updated += 1

        conn.commit()

    return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated}


def list_opportunities(q: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))

    base = """
    SELECT
        id, source, title, url, company, contractor, industry, region, phase, score, entry,
        created_at, updated_at
    FROM opportunities
    """

    params: Dict[str, Any] = {"limit": limit}

    if q and q.strip():
        params["q"] = f"%{q.strip().lower()}%"
        sql = base + """
        WHERE lower(title) LIKE %(q)s
           OR lower(coalesce(company,'')) LIKE %(q)s
           OR lower(coalesce(contractor,'')) LIKE %(q)s
           OR lower(coalesce(industry,'')) LIKE %(q)s
           OR lower(coalesce(region,'')) LIKE %(q)s
        ORDER BY score DESC, updated_at DESC
        LIMIT %(limit)s
        """
    else:
        sql = base + """
        ORDER BY score DESC, updated_at DESC
        LIMIT %(limit)s
        """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
            return list(rows)
