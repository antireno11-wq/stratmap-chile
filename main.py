import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities

TZ = ZoneInfo("America/Santiago")

SERVICE_NAME = os.getenv("SERVICE_NAME", "stratmap-chile")


def now_clt() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


app = FastAPI(title="Stratmap Chile API", version="0.1.0")


@app.on_event("startup")
def _startup():
    # Importante: NO debe botar la app si DB está caída
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
    score: int = 0
    entry: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class IngestBody(BaseModel):
    items: List[OpportunityIn]


@app.get("/")
def root():
    return {"ok": True, "service": SERVICE_NAME, "time": now_clt()}


@app.get("/health")
def health():
    ok, msg = db_health()
    # /health siempre 200 para que Railway no te mate el servicio,
    # y te muestra db_ok true/false
    return {"status": "ok", "service": SERVICE_NAME, "time": now_clt(), "db_ok": ok, "db_msg": msg}


@app.post("/ingest")
def ingest(body: IngestBody):
    items = [it.model_dump() for it in body.items]
    try:
        inserted, updated = upsert_opportunities(items)
        return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated, "time": now_clt()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {"count": len(rows), "items": rows, "time": now_clt()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# Útil si Railway exige "app" y también para tu debug local
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
