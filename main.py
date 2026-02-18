import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import init_db, upsert_opportunities, list_opportunities


SERVICE_NAME = os.getenv("SERVICE_NAME", "stratmap-chile")
TZ = os.getenv("TZ", "America/Santiago")


def now_cl() -> str:
    return datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M:%S %Z")


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


app = FastAPI(title="Stratmap Chile API", version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_cl()}


@app.get("/health")
def health():
    # Simplemente confirma que la app está arriba (DB la valida init_db)
    return {"status": "ok", "time": now_cl()}


@app.post("/ingest")
def ingest(body: IngestBody):
    if not body.items:
        raise HTTPException(status_code=400, detail="items viene vacío")

    try:
        items = [it.model_dump() for it in body.items]
        ids = upsert_opportunities(items)
        return {"ok": True, "ingested": len(items), "ids": ids[:50], "time": now_cl()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {"count": len(rows), "items": rows, "time": now_cl()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/routes")
def routes():
    base = os.getenv("PUBLIC_BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")
    return {
        "base": base,
        "docs": f"{base}/docs",
        "openapi": f"{base}/openapi.json",
        "health": f"{base}/health",
        "ingest_post": f"{base}/ingest",
        "opportunities": f"{base}/opportunities?limit=50",
        "time": now_cl(),
    }
