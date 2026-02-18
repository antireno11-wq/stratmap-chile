from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo

from db import init_db_safe, get_conn

app = FastAPI(title="Stratmap Chile")

DB_STATUS_OK = False
DB_STATUS_MSG = "not checked"

def ch_time():
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")

@app.on_event("startup")
def startup():
    global DB_STATUS_OK, DB_STATUS_MSG
    ok, msg = init_db_safe()
    DB_STATUS_OK, DB_STATUS_MSG = ok, msg
    # NO levantamos excepción: el servicio debe quedar online igual

@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile", "time": ch_time()}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": ch_time(),
        "db_ok": DB_STATUS_OK,
        "db_msg": DB_STATUS_MSG,
    }

@app.get("/opportunities")
def opportunities(limit: int = 50):
    limit = max(1, min(limit, 200))

    try:
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

    except Exception as e:
        # Devuelve error “amigable” en vez de romper la app
        return {
            "count": 0,
            "items": [],
            "time": ch_time(),
            "error": f"{type(e).__name__}: {e}",
        }
