import os
import psycopg
from psycopg.rows import dict_row

def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url

def get_conn():
    return psycopg.connect(get_db_url(), row_factory=dict_row)

def init_db_safe() -> tuple[bool, str]:
    """
    Intenta crear tabla. Si falla, NO rompe el servicio.
    Retorna (ok, message).
    """
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
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        return True, "db ok"
    except Exception as e:
        return False, f"db error: {type(e).__name__}: {e}"
