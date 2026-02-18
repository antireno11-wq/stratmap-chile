import os
import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json


def _db_url() -> str:
    """
    Railway suele exponer DATABASE_URL (o PGDATABASE/PGHOST/etc).
    Preferimos DATABASE_URL si existe.
    """
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    # fallback (por si Railway expone variables separadas)
    host = os.getenv("PGHOST")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")
    dbname = os.getenv("PGDATABASE")
    if host and user and password and dbname:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    raise RuntimeError("DATABASE_URL no está configurada (ni variables PG*).")


def get_conn():
    return psycopg.connect(_db_url(), row_factory=dict_row)


def init_db():
    """
    Crea tabla si no existe y asegura columnas necesarias.
    """
    ddl = """
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
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    # Por si tu tabla existía sin algunas columnas (migración suave)
    alter_cols = [
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS entry TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS raw JSONB;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS contractor TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS company TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS industry TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS region TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS phase TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS score INT DEFAULT 0;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS source TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS title TEXT;",
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS url TEXT;",
        # si por alguna razón no quedó UNIQUE
        "CREATE UNIQUE INDEX IF NOT EXISTS opportunities_url_uq ON opportunities(url);",
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            for q in alter_cols:
                cur.execute(q)
        conn.commit()


def upsert_opportunities(items: list[dict]) -> int:
    """
    Inserta o actualiza por url.
    Devuelve cantidad procesada (insert+update).
    """
    if not items:
        return 0

    sql = """
    INSERT INTO opportunities
      (source, title, url, company, contractor, industry, region, phase, score, entry, raw, updated_at)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
    ;
    """

    processed = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                raw_val = it.get("raw")
                # ✅ CLAVE: convertir dict → JSON
                if raw_val is not None:
                    raw_val = Json(raw_val)  # psycopg3 lo manda a jsonb
                cur.execute(
                    sql,
                    (
                        it.get("source"),
                        it.get("title"),
                        it.get("url"),
                        it.get("company"),
                        it.get("contractor"),
                        it.get("industry"),
                        it.get("region"),
                        it.get("phase"),
                        int(it.get("score") or 0),
                        it.get("entry"),
                        raw_val,
                    ),
                )
                processed += 1
        conn.commit()

    return processed


def list_opportunities(q: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))

    if q:
        sql = """
        SELECT id, source, title, url, company, contractor, industry, region, phase, score, entry, created_at, updated_at
        FROM opportunities
        WHERE
          title ILIKE %s
          OR company ILIKE %s
          OR contractor ILIKE %s
          OR industry ILIKE %s
          OR region ILIKE %s
        ORDER BY score DESC, updated_at DESC
        LIMIT %s;
        """
        like = f"%{q}%"
        params = (like, like, like, like, like, limit)
    else:
        sql = """
        SELECT id, source, title, url, company, contractor, industry, region, phase, score, entry, created_at, updated_at
        FROM opportunities
        ORDER BY score DESC, updated_at DESC
        LIMIT %s;
        """
        params = (limit,)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
