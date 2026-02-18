import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query
from db import init_db, get_conn


SERVICE_NAME = os.getenv("SERVICE_NAME", "stratmap-chile")

app = FastAPI(title="Stratmap Chile")


def now_clt() -> str:
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


@app.on_event("startup")
def startup():
    # crea tabla si no existe
    init_db()


@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_clt()}


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1 as ok;")
                _ = cur.fetchone()
        return {"status": "ok", "time": now_clt(), "db_ok": True, "db_msg": "ok"}
    except Exception as e:
        return {"status": "ok", "time": now_clt(), "db_ok": False, "db_msg": f"db error: {e}"}


@app.get("/opportunities")
def list_opportunities(
    limit: int = Query(50, ge=1, le=200),
    q: str = Query("", description="filtro simple por texto en título/empresa"),
):
    q = (q or "").strip()

    if q:
        sql = """
        select id, source, title, url, summary, company, contractor, sector, region, phase, score, created_at
        from opportunities
        where (title ilike %s) or (company ilike %s) or (contractor ilike %s)
        order by created_at desc
        limit %s;
        """
        like = f"%{q}%"
        params = (like, like, like, limit)
    else:
        sql = """
        select id, source, title, url, summary, company, contractor, sector, region, phase, score, created_at
        from opportunities
        order by created_at desc
        limit %s;
        """
        params = (limit,)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return {"count": len(rows), "items": rows, "time": now_clt()}
