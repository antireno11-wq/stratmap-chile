import os
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "")

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está definido en variables de entorno.")
    # row_factory dict para que los SELECT vengan como dicts
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    """
    Crea tablas básicas para Stratmap.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Tabla oportunidades (proyectos/noticias)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id BIGSERIAL PRIMARY KEY,
                    source TEXT NOT NULL,            -- rss | sea | etc
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    summary TEXT,
                    region TEXT,
                    industry TEXT,                   -- Minería | Energía | Oil & Gas | Infraestructura
                    company TEXT,                    -- Mandante
                    contractor TEXT,
                    score INT DEFAULT 0,
                    entry_strategy TEXT,
                    phase TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Tabla "seen" para no repetir
            cur.execute("""
                CREATE TABLE IF NOT EXISTS seen_urls (
                    url TEXT PRIMARY KEY,
                    first_seen_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            conn.commit()

def mark_seen(url: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO seen_urls(url) VALUES (%s) ON CONFLICT (url) DO NOTHING;",
                (url,)
            )
            conn.commit()

def is_seen(url: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM seen_urls WHERE url = %s LIMIT 1;", (url,))
            return cur.fetchone() is not None

def upsert_opportunity(item: dict):
    """
    Inserta o actualiza una oportunidad por URL.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO opportunities (
                    source, title, url, summary, region, industry, company, contractor,
                    score, entry_strategy, phase
                )
                VALUES (
                    %(source)s, %(title)s, %(url)s, %(summary)s, %(region)s, %(industry)s,
                    %(company)s, %(contractor)s, %(score)s, %(entry_strategy)s, %(phase)s
                )
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    region = EXCLUDED.region,
                    industry = EXCLUDED.industry,
                    company = EXCLUDED.company,
                    contractor = EXCLUDED.contractor,
                    score = EXCLUDED.score,
                    entry_strategy = EXCLUDED.entry_strategy,
                    phase = EXCLUDED.phase;
            """, {
                "source": item.get("source", "unknown"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary"),
                "region": item.get("region"),
                "industry": item.get("industry"),
                "company": item.get("company"),
                "contractor": item.get("contractor"),
                "score": int(item.get("score", 0) or 0),
                "entry_strategy": item.get("entry_strategy"),
                "phase": item.get("phase"),
            })
            conn.commit()

def list_opportunities(limit: int = 50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM opportunities
                ORDER BY score DESC, created_at DESC
                LIMIT %s;
            """, (limit,))
            return cur.fetchall()
