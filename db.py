# db.py
import os
import time
import psycopg
from psycopg.rows import dict_row

def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return ""
    # Railway suele usar postgres://, psycopg prefiere postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # asegura sslmode si no viene (seguro para Railway)
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = url + f"{sep}sslmode=require"
    return url

def get_conn():
    url = _db_url()
    if not url:
        raise RuntimeError("DATABASE_URL no está seteada en el servicio.")
    # timeout corto para no colgar el startup
    return psycopg.connect(
        url,
        row_factory=dict_row,
        connect_timeout=5,
    )

def init_db_safe(max_retries: int = 6, sleep_seconds: float = 2.0) -> dict:
    """
    Crea tabla y deja la app arriba aunque la DB esté caída.
    Retorna estado para healthcheck.
    """
    url = _db_url()
    if not url:
        return {"db_ok": False, "db_msg": "DATABASE_URL missing"}

    last_err = None
    for i in range(max_retries):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    create table if not exists opportunities (
                        id bigserial primary key,
                        url text unique not null,
                        title text not null,
                        source text,
                        score int default 0,
                        industry text,
                        company text,
                        contractor text,
                        region text,
                        phase text,
                        strategy text,
                        published_at timestamptz,
                        created_at timestamptz default now()
                    );
                    """)
                    conn.commit()
            return {"db_ok": True, "db_msg": "ok"}
        except Exception as e:
            last_err = e
            time.sleep(sleep_seconds)

    return {"db_ok": False, "db_msg": f"db error: {type(last_err).__name__}: {last_err}"}
