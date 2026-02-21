from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import db_health, init_db_safe, list_opportunities, upsert_opportunities


# ── Startup ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_safe()
    yield

app = FastAPI(title="Stratmap Chile", lifespan=lifespan)


# ── Schemas ───────────────────────────────────────────────────────────────────

class OpportunityIn(BaseModel):
    source: str
    title: str
    url: str
    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    score: int = 0
    entry: Optional[str] = None
    raw: Optional[Any] = None


class IngestPayload(BaseModel):
    items: List[OpportunityIn]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    db_ok, db_msg = db_health()
    return {"status": "ok", "db_ok": db_ok, "db_msg": db_msg}


@app.post("/ingest")
def ingest(payload: IngestPayload):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items provided")

    items = [item.model_dump() for item in payload.items]
    inserted, updated = upsert_opportunities(items)

    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
    }


@app.get("/opportunities")
def opportunities(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
):
    rows = list_opportunities(q=q, limit=limit)
    # Convertir a dict serializable
    result = []
    for row in rows:
        r = dict(row)
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
        if r.get("raw") and hasattr(r["raw"], "__iter__"):
            pass  # ya es dict
        result.append(r)
    return result


# ── Static UI (debe ir al final) ──────────────────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")
