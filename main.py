import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from db import init_db, upsert_opportunity, list_opportunities
from sea_ingest import run_sea_ingest

app = FastAPI(title="Stratmap Chile API")

RUN_INGEST_ON_START = os.getenv("RUN_INGEST_ON_START", "0") == "1"


class OpportunityIn(BaseModel):
    source: str
    title: str
    url: str
    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    score: Optional[int] = 0
    entry: Optional[str] = None
    raw: Optional[dict] = None


class IngestBody(BaseModel):
    items: List[OpportunityIn]


def now_clt():
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


@app.on_event("startup")
def startup():
    init_db()

    if RUN_INGEST_ON_START:
        threading.Thread(target=run_sea_ingest).start()


@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile", "time": now_clt()}


@app.get("/health")
def health():
    return {"status": "ok", "time": now_clt()}


@app.post("/ingest")
def ingest(body: IngestBody):
    inserted = 0
    updated = 0

    for item in body.items:
        upsert_opportunity(item.dict())
        inserted += 1

    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "total": len(body.items),
        "time": now_clt()
    }


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    try:
        rows = list_opportunities(q=q, limit=limit)
        return {
            "count": len(rows),
            "items": rows,
            "time": now_clt()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
