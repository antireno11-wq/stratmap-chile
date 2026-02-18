import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunity, list_opportunities

APP_TZ = os.getenv("APP_TZ", "America/Santiago")
SERVICE_NAME = os.getenv("SERVICE_NAME", "stratmap-chile")

app = FastAPI(title="Stratmap Chile API", version="0.1.0")


def now_clt() -> str:
    return datetime.now(ZoneInfo(APP_TZ)).strftime("%Y-%m-%d %H:%M:%S %Z")


# =========================
# Models
# =========================
class OpportunityIn(BaseModel):
    source: str = Field(..., description="Origen: sea|rss|manual|otro")
    title: str
    url: str
    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None  # Minería | Energía | Oil & Gas | Infraestructura | etc.
    region: Optional[str] = None
    phase: Optional[str] = None
    score: Optional[int] = 0
    entry: Optional[str] = None  # antes 'Estrategia de Entrada' / 'Entrada'
    raw: Optional[Dict[str, Any]] = None  # payload completo por si quieres guardar más


class IngestBody(BaseModel):
    items: List[OpportunityIn]


# =========================
# Startup
# =========================
@app.on_event("startup")
def startup():
    # Importante: NO caer si DB está temporalmente abajo
    init_db_safe()


# =========================
# Routes
# =========================
@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_clt()}


@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "time": now_clt(), "db_ok": ok, "db_msg": msg}


@app.post("/ingest")
def ingest(body: IngestBody):
    # Inserta/actualiza por URL (idempotente)
    inserted = 0
    for it in body.items:
        try:
            upsert_opportunity(it.model_dump())
            inserted += 1
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"db error ingest: {e}")
    return {"ok": True, "inserted": inserted, "time": now_clt()}


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    # limit razonable
    limit = max(1, min(500, int(limit)))
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows, "time": now_clt()}
