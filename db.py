import os
import json
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Tuple

import psycopg
from psycopg.rows import dict_row


def _db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL no está seteada")
    return db_url


def get_conn():
    return psycopg.connect(_db_url(), row_factory=dict_row, connect_timeout=8)


def init_db_safe() -> None:
    """
    Crea tabla si no existe. NO bota la app si DB está caída.
    """
    try:
        init_db()
    except Exception as e:
        print(f"[db] init_db_safe: DB no disponible todavía: {type(e).__name__}: {e}")


def init_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS opportunities (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,

        company TEXT NULL,
        contractor TEXT NULL,
        industry TEXT NULL,
        region TEXT NULL,
        phase TEXT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        entry TEXT NULL,

        raw JSONB NULL,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities (score DESC);
    CREATE INDEX IF NOT EXISTS idx_opportunities_company ON opportunities (company);
    CREATE INDEX IF NOT EXISTS idx_opportunities_industry ON opportunities (industry);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    # Por si tenías una tabla antigua sin 'entry'
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS entry TEXT NULL;")
        conn.commit()


def db_health() -> Tuple[bool, str]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 as ok;")
                _ = cur.fetchone()
        return True, "ok"
    except Exception as e:
        return False, f"db error: {type(e).__name__}: {e}"


def upsert_opportunities(items: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Inserta o actualiza por url (UNIQUE).
    Retorna (inserted, updated)
    """
    inserted = 0
    updated = 0

    sql = """
    INSERT INTO opportunities
      (source, title, url, company, contractor, industry, region, phase, score, entry, raw, created_at, updated_at)
    VALUES
      (%(source)s, %(title)s, %(url)s, %(company)s, %(contractor)s, %(industry)s, %(region)s, %(phase)s, %(score)s, %(entry)s, %(raw)s, NOW(), NOW())
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
      updated_at = NOW()
    RETURNING (xmax = 0) AS inserted;
    """

    # NORMALIZA RAW: dict -> JSON string -> JSONB via psycopg
    for it in items:
        raw = it.get("raw")
        if isinstance(raw, (dict, list)):
            it["raw"] = psycopg.types.json.Json(raw)
        elif raw is None:
            it["raw"] = None
        else:
            # si viene como string u otro, lo guardamos como string
            it["raw"] = psycopg.types.json.Json({"value": str(raw)})

        it.setdefault("company", None)
        it.setdefault("contractor", None)
        it.setdefault("industry", None)
        it.setdefault("region", None)
        it.setdefault("phase", None)
        it.setdefault("score", 0)
        it.setdefault("entry", None)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(sql, it)
                row = cur.fetchone()
                if row and row.get("inserted"):
                    inserted += 1
                else:
                    updated += 1
        conn.commit()

    return inserted, updated


def list_opportunities(q: Optional[str], limit: int) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))

    base = """
    SELECT id, source, title, url, company, contractor, industry, region, phase, score, entry, raw, created_at, updated_at
    FROM opportunities
    """

    params: Dict[str, Any] = {"limit": limit}

    if q:
        base += """
        WHERE
          title ILIKE %(q)s OR
          company ILIKE %(q)s OR
          contractor ILIKE %(q)s OR
          industry ILIKE %(q)s OR
          region ILIKE %(q)s
        """
        params["q"] = f"%{q}%"

    base += " ORDER BY score DESC, updated_at DESC LIMIT %(limit)s;"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            return cur.fetchall()
