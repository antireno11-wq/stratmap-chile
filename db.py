import os
import psycopg
from psycopg.rows import dict_row


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL no está configurada en Railway > Variables")
    return db_url


def get_conn():
    return psycopg.connect(get_db_url(), row_factory=dict_row)


def init_db():
    sql = """
    create table if not exists opportunities (
        id bigserial primary key,
        source text not null,
        title text not null,
        url text not null unique,
        summary text,
        company text,
        contractor text,
        sector text,
        region text,
        phase text,
        score int default 0,
        created_at timestamptz default now()
    );

    create index if not exists idx_opportunities_score on opportunities(score desc);
    create index if not exists idx_opportunities_created on opportunities(created_at desc);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
