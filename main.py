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


def now_clt() -> str:
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
    # NO mates el server si DB no está listo: deja “safe”
    init_db_safe()


# -------------------------
# Routes
# -------------------------
@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_clt()}


@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "time": now_clt(), "db_ok": ok, "db_msg": msg}


@app.post("/ingest")
def ingest(body: IngestBody):
    """
    Inserta/actualiza oportunidades (upsert por url).
    """
    try:
        # Convertimos a dict plano para que DB no se pelee con Pydantic
        items_dicts = [x.model_dump() for x in body.items]
        res = upsert_opportunities(items_dicts)
        res["time"] = now_clt()
        return res
    except Exception as e:
        # Esto te devuelve el error en JSON (como lo estás viendo)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {"count": len(rows), "items": rows, "time": now_clt()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
