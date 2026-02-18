import os
import psycopg
from psycopg.rows import dict_row

def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(db_url, row_factory=dict_row)

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS opportunities (
        id BIGSERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        company TEXT,
        contractor TEXT,
        sector TEXT,
        score INT DEFAULT 0,
        region TEXT,
        phase TEXT,
        entry_strategy TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
