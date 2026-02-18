import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple

import psycopg
from psycopg.rows import dict_row

APP_TZ = os.getenv("APP_TZ", "America/Santiago")


def _now() -> str:
    return datetime.now(ZoneInfo(APP_TZ)).isoformat()


def get_conn() -> psycopg.Connection:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL no está seteada")
    return psycopg.connect(db_url, row_factory=dict_row)


def init_db_safe() -> None:
    """Crea tabla si no existe, pero no revienta el server si DB está abajo."""
    try:
        init_db()
    except Exception as e:
        print(f"[db] init_db_safe: {e}")


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT,
                    company TEXT,
                    contractor TEXT,
                    industry TEXT,
                    region TEXT,
                    phase TEXT,
                    score INTEGER DEFAULT 0,
                    entry TEXT,
                    raw JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opps_score ON opportunities(score DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opps_company ON opportunities(company);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opps_industry ON opportunities(industry);")
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


def upsert_opportunity(item: Dict[str, Any]) -> None:
    # Normaliza
    url = (item.get("url") or "").strip()
    title = (item.get("title") or "").strip()
    if not url or not title:
        raise ValueError("url/title son obligatorios")

    data = {
        "url": url,
        "title": title,
        "source": item.get("source"),
        "company": item.get("company"),
        "contractor": item.get("contractor"),
        "industry": item.get("industry"),
        "region": item.get("region"),
        "phase": item.get("phase"),
        "score": int(item.get("score") or 0),
        "entry": item.get("entry"),
        "raw": item.get("raw"),
        "updated_at": _now(),
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO opportunities
                    (url, title, source, company, contractor, industry, region, phase, score, entry, raw, updated_at)
                VALUES
                    (%(url)s, %(title)s, %(source)s, %(company)s, %(contractor)s, %(industry)s, %(region)s, %(phase)s, %(score)s, %(entry)s, %(raw)s, %(updated_at)s)
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    source = EXCLUDED.source,
                    company = EXCLUDED.company,
                    contractor = EXCLUDED.contractor,
                    industry = EXCLUDED.industry,
                    region = EXCLUDED.region,
                    phase = EXCLUDED.phase,
                    score = EXCLUDED.score,
                    entry = EXCLUDED.entry,
                    raw = EXCLUDED.raw,
                    updated_at = EXCLUDED.updated_at
                ;
            """, data)
        conn.commit()


def list_opportunities(q: Optional[str], limit: int) -> List[Dict[str, Any]]:
    where = ""
    params = {"limit": limit}
    if q and q.strip():
        q = q.strip()
        where = "WHERE (title ILIKE %(q)s OR company ILIKE %(q)s OR contractor ILIKE %(q)s OR industry ILIKE %(q)s)"
        params["q"] = f"%{q}%"

    sql = f"""
        SELECT
            url, title, source, company, contractor, industry, region, phase, score, entry,
            created_at, updated_at
        FROM opportunities
        {where}
        ORDER BY score DESC, updated_at DESC
        LIMIT %(limit)s;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
