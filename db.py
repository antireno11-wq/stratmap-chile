import os
import psycopg
from psycopg.rows import dict_row


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL no está seteada.")
    return db_url


def get_conn():
    return psycopg.connect(get_db_url(), row_factory=dict_row, connect_timeout=10)


def init_db() -> None:
    # 1) Crea tabla base si no existe
    ddl_base = """
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

        raw JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    # 2) Migraciones seguras: agrega columnas que tu código espera
    # (Si ya existen, no hace nada)
    ddl_migrations = """
    ALTER TABLE opportunities
      ADD COLUMN IF NOT EXISTS entry TEXT;

    ALTER TABLE opportunities
      ADD COLUMN IF NOT EXISTS raw JSONB;

    ALTER TABLE opportunities
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    """

    ddl_indexes = """
    CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(score DESC);
    CREATE INDEX IF NOT EXISTS idx_opportunities_company ON opportunities(company);
    CREATE INDEX IF NOT EXISTS idx_opportunities_industry ON opportunities(industry);
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl_base)
            cur.execute(ddl_migrations)
            cur.execute(ddl_indexes)
        conn.commit()


def upsert_opportunities(items: list[dict]) -> list[int]:
    sql = """
    INSERT INTO opportunities
      (source, title, url, company, contractor, industry, region, phase, score, entry, raw, updated_at)
    VALUES
      (%(source)s, %(title)s, %(url)s, %(company)s, %(contractor)s, %(industry)s, %(region)s, %(phase)s,
       %(score)s, %(entry)s, %(raw)s::jsonb, NOW())
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
    RETURNING id;
    """

    ids: list[int] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(sql, it)
                row = cur.fetchone()
                if row and "id" in row:
                    ids.append(int(row["id"]))
        conn.commit()
    return ids


def list_opportunities(q: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 200))

    base = """
    SELECT
      id, source, title, url, company, contractor, industry, region, phase, score, entry,
      created_at, updated_at
    FROM opportunities
    """
    params = {}
    where = ""
    if q:
        where = "WHERE (title ILIKE %(q)s OR company ILIKE %(q)s OR contractor ILIKE %(q)s OR industry ILIKE %(q)s)"
        params["q"] = f"%{q}%"

    order = "ORDER BY score DESC, updated_at DESC"
    sql = f"{base} {where} {order} LIMIT {limit};"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return rows
