# db.py
import os
from typing import Any, Dict, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json


def _db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL no está seteada")
    return db_url


def get_conn():
    return psycopg.connect(_db_url(), row_factory=dict_row, connect_timeout=8)


def init_db_safe() -> None:
    try:
        init_db()
        init_users_db()
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
    CREATE INDEX IF NOT EXISTS idx_opportunities_region ON opportunities (region);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS entry TEXT NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS raw JSONB NULL;")
        conn.commit()


def init_users_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        name TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        preferred_industries TEXT[] DEFAULT '{}',
        preferred_regions TEXT[] DEFAULT '{}',
        preferred_phases TEXT[] DEFAULT '{}',
        preferred_companies TEXT[] DEFAULT '{}',
        keywords TEXT[] DEFAULT '{}',
        min_investment_usd INTEGER NULL,
        weight_region FLOAT DEFAULT 1.0,
        weight_industry FLOAT DEFAULT 1.0,
        weight_investment FLOAT DEFAULT 1.0,
        weight_phase FLOAT DEFAULT 1.0,
        weight_company FLOAT DEFAULT 1.0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
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

    for it in items:
        it.setdefault("company", None)
        it.setdefault("contractor", None)
        it.setdefault("industry", None)
        it.setdefault("region", None)
        it.setdefault("phase", None)
        it.setdefault("score", 0)
        it.setdefault("entry", None)

        raw = it.get("raw")
        if isinstance(raw, (dict, list)):
            it["raw"] = Json(raw)
        elif raw is None:
            it["raw"] = None
        else:
            it["raw"] = Json({"value": str(raw)})

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
          url ILIKE %(q)s OR
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


def get_opportunity_by_url(url: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT id, source, title, url, company, contractor, industry, region, phase, score, entry, raw, created_at, updated_at
    FROM opportunities
    WHERE url = %(url)s
    LIMIT 1;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"url": url})
            row = cur.fetchone()
            return row if row else None


# ── Users & Preferences ───────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, name: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO users (email, password_hash, name)
    VALUES (%(email)s, %(password_hash)s, %(name)s)
    RETURNING id, email, name;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"email": email, "password_hash": password_hash, "name": name})
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    sql = "SELECT id, email, password_hash, name FROM users WHERE email = %(email)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"email": email})
            row = cur.fetchone()
    return dict(row) if row else None


def save_preferences(user_id: int, prefs: Dict[str, Any]) -> None:
    sql = """
    INSERT INTO user_preferences
      (user_id, preferred_industries, preferred_regions, preferred_phases,
       preferred_companies, keywords, min_investment_usd,
       weight_region, weight_industry, weight_investment, weight_phase, weight_company, updated_at)
    VALUES
      (%(user_id)s, %(preferred_industries)s, %(preferred_regions)s, %(preferred_phases)s,
       %(preferred_companies)s, %(keywords)s, %(min_investment_usd)s,
       %(weight_region)s, %(weight_industry)s, %(weight_investment)s, %(weight_phase)s, %(weight_company)s, NOW())
    ON CONFLICT (user_id) DO UPDATE SET
      preferred_industries = EXCLUDED.preferred_industries,
      preferred_regions = EXCLUDED.preferred_regions,
      preferred_phases = EXCLUDED.preferred_phases,
      preferred_companies = EXCLUDED.preferred_companies,
      keywords = EXCLUDED.keywords,
      min_investment_usd = EXCLUDED.min_investment_usd,
      weight_region = EXCLUDED.weight_region,
      weight_industry = EXCLUDED.weight_industry,
      weight_investment = EXCLUDED.weight_investment,
      weight_phase = EXCLUDED.weight_phase,
      weight_company = EXCLUDED.weight_company,
      updated_at = NOW();
    """
    prefs["user_id"] = user_id
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, prefs)
        conn.commit()


def get_preferences(user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM user_preferences WHERE user_id = %(user_id)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id})
            row = cur.fetchone()
    return dict(row) if row else None
