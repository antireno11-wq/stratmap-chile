from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo

from db import init_db, get_conn

app = FastAPI(title="Stratmap Chile")

def ch_time():
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")

@app.on_event("startup")
def startup():
    # esto es rápido; solo crea tabla si no existe
    init_db()

@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile", "time": ch_time()}

@app.get("/health")
def health():
    return {"status": "ok", "time": ch_time()}

@app.get("/opportunities")
def opportunities(limit: int = 50):
    limit = max(1, min(limit, 200))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source, title, url, company, contractor, sector, score, region, phase, entry_strategy, created_at
                FROM opportunities
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return {"count": len(rows), "items": rows, "time": ch_time()}
