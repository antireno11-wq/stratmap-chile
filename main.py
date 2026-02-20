import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities

app = FastAPI(title="Stratmap Chile API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa tabla sin botar si DB aún no está lista
init_db_safe()


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


@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile"}


@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "db_ok": ok, "db_msg": msg}


@app.post("/ingest")
def ingest(body: IngestBody):
    items = [i.model_dump() for i in body.items]
    inserted, updated = upsert_opportunities(items)
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(items)}


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows}
