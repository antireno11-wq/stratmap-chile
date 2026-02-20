import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities

APP_NAME = os.getenv("APP_NAME", "stratmap-chile")
TZ = ZoneInfo("America/Santiago")

app = FastAPI(title="Stratmap Chile API", version="0.1.0")

# CORS abierto para MVP (después lo cerramos por dominios)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_clt_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


@app.on_event("startup")
def startup():
    # No bota la app si Postgres se demora en levantar
    init_db_safe()


@app.get("/")
def root():
    return {"ok": True, "service": APP_NAME, "time": now_clt_str()}


@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "time": now_clt_str(), "db_ok": ok, "db_msg": msg}


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


@app.post("/ingest")
def ingest(body: IngestBody):
    items = [it.model_dump() for it in body.items]
    inserted, updated = upsert_opportunities(items)
    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
        "time": now_clt_str(),
    }


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows, "time": now_clt_str()}
