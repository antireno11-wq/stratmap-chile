import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities


SERVICE_NAME = os.getenv("SERVICE_NAME", "stratmap-chile")
TZ = ZoneInfo("America/Santiago")

app = FastAPI(title="Stratmap Chile API", version="0.1.0")


def now_clt_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


# -------------------------
# Models
# -------------------------
class OpportunityIn(BaseModel):
    source: str = Field(..., description="Origen: sea|rss|manual|otro")
    title: str
    url: str

    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    score: Optional[int] = 0
    entry: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class IngestBody(BaseModel):
    items: List[OpportunityIn]


# -------------------------
# Startup
# -------------------------
@app.on_event("startup")
def startup() -> None:
    # IMPORTANT: no debe botar el server si DB está down
    init_db_safe()


# -------------------------
# Routes
# -------------------------
@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_clt_str()}


@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "time": now_clt_str(), "db_ok": ok, "db_msg": msg}


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {"count": len(rows), "items": rows, "time": now_clt_str()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {type(e).__name__}: {e}")


@app.post("/ingest")
def ingest(body: IngestBody):
    try:
        inserted, updated = upsert_opportunities([x.model_dump() for x in body.items])
        return {
            "ok": True,
            "inserted": inserted,
            "updated": updated,
            "total": inserted + updated,
            "time": now_clt_str(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {type(e).__name__}: {e}")
