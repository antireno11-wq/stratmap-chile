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
        init_contacts_db()
        init_pipeline_db()
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
    CREATE INDEX IF NOT EXISTS idx_opportunity_signals_opportunity_id ON opportunity_signals(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_opportunities_signal_score ON opportunities(signal_score DESC);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_contacts_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS contacts (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        company TEXT NOT NULL,
        role TEXT NULL,
        email TEXT NULL,
        phone TEXT NULL,
        linkedin_url TEXT NULL,
        notes TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts (company);
    CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts (name);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_pipeline_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS opportunity_pipeline (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'Detectada',
        assignee TEXT NULL,
        notes TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(opportunity_id)
    );

    CREATE TABLE IF NOT EXISTS pipeline_notes (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        note TEXT NOT NULL,
        author TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_pipeline_opportunity_id ON opportunity_pipeline(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_pipeline_status ON opportunity_pipeline(status);
    CREATE INDEX IF NOT EXISTS idx_pipeline_notes_opportunity_id ON pipeline_notes(opportunity_id);
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
      source = EXCLUDED.source, title = EXCLUDED.title, company = EXCLUDED.company,
      contractor = EXCLUDED.contractor, industry = EXCLUDED.industry, region = EXCLUDED.region,
      phase = EXCLUDED.phase, score = EXCLUDED.score, entry = EXCLUDED.entry,
      raw = EXCLUDED.raw, updated_at = NOW()
    RETURNING (xmax = 0) AS inserted;
    """
    for it in items:
        it.setdefault("company", None); it.setdefault("contractor", None)
        it.setdefault("industry", None); it.setdefault("region", None)
        it.setdefault("phase", None); it.setdefault("score", 0); it.setdefault("entry", None)
        raw = it.get("raw")
        if isinstance(raw, (dict, list)): it["raw"] = Json(raw)
        elif raw is None: it["raw"] = None
        else: it["raw"] = Json({"value": str(raw)})

    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(sql, it)
                row = cur.fetchone()
                if row and row.get("inserted"): inserted += 1
                else: updated += 1
        conn.commit()
    return inserted, updated


def list_opportunities(q: Optional[str], limit: int) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    base = """
    SELECT o.id, o.source, o.title, o.url, o.company, o.contractor, o.industry, o.region, o.phase,
           o.score, o.signal_score, o.jobs_count, o.signals, o.last_signal_at,
           o.entry, o.raw, o.created_at, o.updated_at,
           (o.score + COALESCE(o.signal_score, 0)) AS radar_score,
           p.status AS pipeline_status, p.assignee AS pipeline_assignee
    FROM opportunities o
    LEFT JOIN opportunity_pipeline p ON p.opportunity_id = o.id
    """
    params: Dict[str, Any] = {"limit": limit}
    if q:
        base += """
        WHERE o.title ILIKE %(q)s OR o.url ILIKE %(q)s OR o.company ILIKE %(q)s
           OR o.contractor ILIKE %(q)s OR o.industry ILIKE %(q)s OR o.region ILIKE %(q)s
        """
        params["q"] = f"%{q}%"
    base += " ORDER BY radar_score DESC, o.updated_at DESC LIMIT %(limit)s;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            return cur.fetchall()


def get_opportunity_by_url(url: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT id, source, title, url, company, contractor, industry, region, phase,
           score, signal_score, jobs_count, signals, last_signal_at, entry, raw, created_at, updated_at
    FROM opportunities WHERE url = %(url)s LIMIT 1;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"url": url})
            return cur.fetchone()


# ── Pipeline ──────────────────────────────────────────────────────────────────

PIPELINE_STATUSES = ["Detectada", "En análisis", "Postular", "No postular",
                     "Presentada", "Adjudicada", "Perdida"]

def get_pipeline(opportunity_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM opportunity_pipeline WHERE opportunity_id = %(id)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": opportunity_id})
            row = cur.fetchone()
    return dict(row) if row else None

def upsert_pipeline(opportunity_id: int, status: str, assignee: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO opportunity_pipeline (opportunity_id, status, assignee, updated_at)
    VALUES (%(opportunity_id)s, %(status)s, %(assignee)s, NOW())
    ON CONFLICT (opportunity_id) DO UPDATE SET
      status = EXCLUDED.status,
      assignee = COALESCE(EXCLUDED.assignee, opportunity_pipeline.assignee),
      updated_at = NOW()
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id, "status": status, "assignee": assignee})
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def add_pipeline_note(opportunity_id: int, note: str, author: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO pipeline_notes (opportunity_id, note, author)
    VALUES (%(opportunity_id)s, %(note)s, %(author)s)
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id, "note": note, "author": author})
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def get_pipeline_notes(opportunity_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT * FROM pipeline_notes
    WHERE opportunity_id = %(id)s
    ORDER BY created_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": opportunity_id})
            return [dict(r) for r in cur.fetchall()]

def list_pipeline(status: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = """
    SELECT o.id, o.title, o.company, o.region, o.industry, o.url,
           (o.score + COALESCE(o.signal_score, 0)) AS radar_score,
           p.status, p.assignee, p.updated_at
    FROM opportunity_pipeline p
    JOIN opportunities o ON o.id = p.opportunity_id
    """
    params: Dict[str, Any] = {}
    if status:
        sql += " WHERE p.status = %(status)s"
        params["status"] = status
    sql += " ORDER BY p.updated_at DESC;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


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


# ── Signals ───────────────────────────────────────────────────────────────────

COMPANY_ALIASES: Dict[str, List[str]] = {
    "BHP":                  ["BHP"],
    "Codelco":              ["CODELCO", "Codelco", "Radomiro Tomic", "Chuquicamata",
                             "El Teniente", "División Andina", "División Salvador"],
    "SQM":                  ["SQM", "Sociedad Química"],
    "Anglo American":       ["Anglo American", "Anglo"],
    "Teck":                 ["Teck", "Caserones"],
    "Antofagasta Minerals": ["AMSA", "Antofagasta Minerals", "Antofagasta"],
    "Glencore":             ["Glencore", "Punta del Cobre"],
    "Freeport-McMoRan":     ["Freeport", "FCX", "Lumina", "LUMINA COPPER"],
}

def save_job_signal(opportunity_id: int, signal: Dict[str, Any]) -> None:
    # Dedup: solo sumar signal_score una vez por día por proyecto
    sql_check = """
    SELECT COUNT(*) as cnt FROM opportunity_signals
    WHERE opportunity_id = %(id)s
      AND signal_type = 'jobs'
      AND detected_at > NOW() - INTERVAL '24 hours';
    """
    sql_signal = """
    INSERT INTO opportunity_signals
      (opportunity_id, signal_type, signal_source, signal_data, score_impact, detected_at)
    VALUES (%(opportunity_id)s, %(signal_type)s, %(signal_source)s, %(signal_data)s, %(score_impact)s, %(detected_at)s);
    """
    # Solo suma score si es la primera detección del día
    sql_update_new = """
    UPDATE opportunities SET
      jobs_count = %(jobs_count)s,
      signal_score = LEAST(COALESCE(signal_score, 0) + %(score_impact)s, 50),
      last_signal_at = NOW(),
      signals = COALESCE(signals, '[]'::jsonb) || %(new_signal)s::jsonb
    WHERE id = %(opportunity_id)s;
    """
    # Si ya detectó hoy, solo actualiza jobs_count y last_signal_at
    sql_update_existing = """
    UPDATE opportunities SET
      jobs_count = %(jobs_count)s,
      last_signal_at = NOW()
    WHERE id = %(opportunity_id)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_check, {"id": opportunity_id})
            row = cur.fetchone()
            already_today = row and row.get("cnt", 0) > 0

            cur.execute(sql_signal, {
                "opportunity_id": opportunity_id,
                "signal_type": signal["signal_type"],
                "signal_source": signal["signal_source"],
                "signal_data": Json(signal["signal_data"]),
                "score_impact": signal["score_impact"],
                "detected_at": signal["detected_at"],
            })

            if already_today:
                cur.execute(sql_update_existing, {
                    "opportunity_id": opportunity_id,
                    "jobs_count": signal["jobs_count"],
                })
            else:
                cur.execute(sql_update_new, {
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
    search_terms = COMPANY_ALIASES.get(company_name, [company_name])
    conditions = " OR ".join([f"company ILIKE %(term_{i})s" for i in range(len(search_terms))])
    params = {f"term_{i}": f"%{term}%" for i, term in enumerate(search_terms)}
    sql = f"""
    SELECT id, title, company, score, signal_score, jobs_count, last_signal_at
    FROM opportunities WHERE {conditions}
    ORDER BY signal_score DESC, score DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def get_radar_opportunities(limit: int = 20) -> List[Dict[str, Any]]:
    sql = """
    SELECT id, title, company, region, industry, phase, score, signal_score, jobs_count, signals,
           last_signal_at, updated_at, (score + COALESCE(signal_score, 0)) AS radar_score
    FROM opportunities
    ORDER BY radar_score DESC, last_signal_at DESC NULLS LAST
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()

def get_signals_for_opportunity(opportunity_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT signal_type, signal_source, signal_data, score_impact, detected_at
    FROM opportunity_signals WHERE opportunity_id = %(opportunity_id)s
    ORDER BY detected_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id})
            return cur.fetchall()


# ── Contactos ─────────────────────────────────────────────────────────────────

def create_contact(contact: Dict[str, Any]) -> Dict[str, Any]:
    sql = """
    INSERT INTO contacts (name, company, role, email, phone, linkedin_url, notes)
    VALUES (%(name)s, %(company)s, %(role)s, %(email)s, %(phone)s, %(linkedin_url)s, %(notes)s)
    RETURNING *;
    """
    contact.setdefault("role", None); contact.setdefault("email", None)
    contact.setdefault("phone", None); contact.setdefault("linkedin_url", None)
    contact.setdefault("notes", None)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, contact)
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def update_contact(contact_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = ["name","company","role","email","phone","linkedin_url","notes"]
    updates = ", ".join([f"{f} = %({f})s" for f in fields if f in data])
    if not updates: return None
    sql = f"UPDATE contacts SET {updates}, updated_at = NOW() WHERE id = %(id)s RETURNING *;"
    data["id"] = contact_id
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, data)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None

def delete_contact(contact_id: int) -> bool:
    sql = "DELETE FROM contacts WHERE id = %(id)s RETURNING id;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": contact_id})
            row = cur.fetchone()
        conn.commit()
    return row is not None

def get_contacts_by_company(company: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT * FROM contacts
    WHERE company ILIKE %(like)s
       OR %(company)s ILIKE '%%' || company || '%%'
    ORDER BY name ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"company": company, "like": f"%{company}%"})
            return [dict(r) for r in cur.fetchall()]

def list_contacts(q: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    base = "SELECT * FROM contacts"
    params: Dict[str, Any] = {"limit": limit}
    if q:
        base += " WHERE name ILIKE %(q)s OR company ILIKE %(q)s OR role ILIKE %(q)s"
        params["q"] = f"%{q}%"
    base += " ORDER BY company ASC, name ASC LIMIT %(limit)s;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            return [dict(r) for r in cur.fetchall()]

def bulk_import_contacts(contacts: List[Dict[str, Any]]) -> Tuple[int, int]:
    inserted = errors = 0
    for c in contacts:
        try:
            create_contact(c)
            inserted += 1
        except Exception as e:
            print(f"[contacts] error importando {c.get('name')}: {e}")
            errors += 1
    return inserted, errors
