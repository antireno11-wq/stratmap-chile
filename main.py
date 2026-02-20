from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from db import init_db_safe, ingest_opportunities, list_opportunities

APP_NAME = os.getenv("APP_NAME", "stratmap-chile")
TZ = ZoneInfo("America/Santiago")

app = FastAPI(title="Stratmap Chile API", version="0.1.0")


def now_clt_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


# -----------------------
# Models
# -----------------------
class OpportunityIn(BaseModel):
    source: str = Field(..., description="Origen: sea|rss|manual|otro")
    title: str
    url: str
    company: str | None = None
    contractor: str | None = None
    industry: str | None = None
    region: str | None = None
    phase: str | None = None
    score: int | None = 0
    entry: str | None = None
    raw: dict[str, Any] | None = None


class IngestBody(BaseModel):
    items: list[OpportunityIn]


# -----------------------
# Startup
# -----------------------
@app.on_event("startup")
def startup() -> None:
    # NO debe botar la app si la DB no está lista
    init_db_safe()


# -----------------------
# Routes
# -----------------------
@app.get("/")
def root() -> dict:
    return {"ok": True, "service": APP_NAME, "time": now_clt_str()}


@app.get("/health")
def health() -> dict:
    # health simple; init_db_safe ya evitó crash
    return {"status": "ok", "time": now_clt_str()}


@app.post("/ingest")
def ingest(body: IngestBody) -> dict:
    try:
        # Convertimos Pydantic models a dict normales
        items = [x.model_dump() for x in body.items]
        res = ingest_opportunities(items)
        res["time"] = now_clt_str()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/opportunities")
def opportunities(q: str | None = None, limit: int = 50) -> dict:
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {"count": len(rows), "items": rows, "time": now_clt_str()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
