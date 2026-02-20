import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities

# ---------------------------------------------------
# App
# ---------------------------------------------------

app = FastAPI(title="Stratmap Chile API", version="0.1.0")

# CORS (por si después haces frontend separado)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Inicializa tabla (no bota la app si DB no está lista aún)
init_db_safe()

# ---------------------------------------------------
# Models
# ---------------------------------------------------

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

# ---------------------------------------------------
# API Endpoints
# ---------------------------------------------------

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
    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "total": len(items),
    }


@app.get("/opportunities")
def opportunities(
    q: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
):
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows}

# ---------------------------------------------------
# UI Endpoint
# ---------------------------------------------------

@app.get("/ui", response_class=HTMLResponse)
def ui():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse(
            "<h1>Error</h1><p>No se encontró templates/index.html</p>",
            status_code=500,
        )
