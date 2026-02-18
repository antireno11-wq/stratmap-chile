import os
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id SERIAL PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
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
        conn.commit()


def upsert_opportunity(item: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO opportunities (
                    source, title, url, company, contractor,
                    industry, region, phase, score, entry, raw
                )
                VALUES (
                    %(source)s, %(title)s, %(url)s, %(company)s, %(contractor)s,
                    %(industry)s, %(region)s, %(phase)s, %(score)s, %(entry)s, %(raw)s
                )
                ON CONFLICT (url)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    company = EXCLUDED.company,
                    contractor = EXCLUDED.contractor,
                    industry = EXCLUDED.industry,
                    region = EXCLUDED.region,
                    phase = EXCLUDED.phase,
                    score = EXCLUDED.score,
                    entry = EXCLUDED.entry,
                    raw = EXCLUDED.raw,
                    updated_at = NOW();
            """, item)
        conn.commit()


def list_opportunities(q=None, limit=50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if q:
                cur.execute("""
                    SELECT *
                    FROM opportunities
                    WHERE title ILIKE %s OR company ILIKE %s
                    ORDER BY score DESC, created_at DESC
                    LIMIT %s
                """, (f"%{q}%", f"%{q}%", limit))
            else:
                cur.execute("""
                    SELECT *
                    FROM opportunities
                    ORDER BY score DESC, created_at DESC
                    LIMIT %s
                """, (limit,))
            return cur.fetchall()
