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
        init_signals_db()
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
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS signals JSONB DEFAULT '[]';")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS signal_score INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS jobs_count INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS last_signal_at TIMESTAMPTZ NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS strategy TEXT NULL;")
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


def init_signals_db() -> None:
    """Crea la tabla de señales para el Radar de Proyectos."""
    sql = """
    CREATE TABLE IF NOT EXISTS opportunity_signals (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
        signal_type VARCHAR(50),
        signal_source VARCHAR(100),
        signal_data JSONB DEFAULT '{}',
        score_impact INTEGER DEFAULT 0,
        detected_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_opportunity_signals_opportunity_id
        ON opportunity_signals(opportunity_id);

    CREATE INDEX IF NOT EXISTS idx_opportunities_signal_score
        ON opportunities(signal_score DESC);
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
    SELECT id, source, title, url, company, contractor, industry, region, phase,
           score, signal_score, jobs_count, signals, last_signal_at,
           entry, raw, created_at, updated_at,
           (score + COALESCE(signal_score, 0)) AS radar_score
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

    base += " ORDER BY radar_score DESC, updated_at DESC LIMIT %(limit)s;"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            return cur.fetchall()


def get_opportunity_by_url(url: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT id, source, title, url, company, contractor, industry, region, phase,
           score, signal_score, jobs_count, signals, last_signal_at,
           entry, raw, created_at, updated_at
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


# ── Signals & Radar de Proyectos ──────────────────────────────────────────────

def save_job_signal(opportunity_id: int, signal: Dict[str, Any]) -> None:
    """Guarda una señal de empleo en opportunity_signals y actualiza opportunities."""

    sql_signal = """
    INSERT INTO opportunity_signals
      (opportunity_id, signal_type, signal_source, signal_data, score_impact, detected_at)
    VALUES
      (%(opportunity_id)s, %(signal_type)s, %(signal_source)s, %(signal_data)s, %(score_impact)s, %(detected_at)s);
    """

    sql_update = """
    UPDATE opportunities SET
      jobs_count     = %(jobs_count)s,
      signal_score   = LEAST(COALESCE(signal_score, 0) + %(score_impact)s, 100),
      last_signal_at = NOW(),
      signals        = COALESCE(signals, '[]'::jsonb) || %(new_signal)s::jsonb
    WHERE id = %(opportunity_id)s;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_signal, {
                "opportunity_id": opportunity_id,
                "signal_type": signal["signal_type"],
                "signal_source": signal["signal_source"],
                "signal_data": Json(signal["signal_data"]),
                "score_impact": signal["score_impact"],
                "detected_at": signal["detected_at"],
            })
            cur.execute(sql_update, {
                "opportunity_id": opportunity_id,
                "jobs_count": signal["jobs_count"],
                "score_impact": signal["score_impact"],
                "new_signal": Json({
                    "type": "jobs",
                    "jobs_count": signal["jobs_count"],
                    "score_impact": signal["score_impact"],
                    "detected_at": signal["detected_at"].isoformat(),
                }),
            })
        conn.commit()


def get_opportunities_by_company(company_name: str) -> List[Dict[str, Any]]:
    """Retorna oportunidades que coincidan con una empresa."""
    sql = """
    SELECT id, title, company, score, signal_score, jobs_count, last_signal_at
    FROM opportunities
    WHERE company ILIKE %(company)s
    ORDER BY signal_score DESC, score DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"company": f"%{company_name}%"})
            return cur.fetchall()


def get_radar_opportunities(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retorna las oportunidades con más movimiento para el Radar de Proyectos.
    Combina score base + signal_score para el ranking final.
    """
    sql = """
    SELECT
        id, title, company, region, industry, phase,
        score, signal_score, jobs_count, signals,
        last_signal_at, updated_at,
        (score + COALESCE(signal_score, 0)) AS radar_score
    FROM opportunities
    ORDER BY radar_score DESC, last_signal_at DESC NULLS LAST
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()


def get_signals_for_opportunity(opportunity_id: int) -> List[Dict[str, Any]]:
    """Retorna el historial de señales de una oportunidad específica."""
    sql = """
    SELECT signal_type, signal_source, signal_data, score_impact, detected_at
    FROM opportunity_signals
    WHERE opportunity_id = %(opportunity_id)s
    ORDER BY detected_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id})
            return cur.fetchall()
