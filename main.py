from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo
import os

from db import init_db_safe
from sea_ingest import run_sea_ingest

app = FastAPI(title="Stratmap Chile API", version="0.1.0")


@app.on_event("startup")
def startup():
    print("🚀 Stratmap starting...")
    init_db_safe()

    # Ejecuta SEA ingest automáticamente al iniciar
    try:
        print("🌊 Running SEA ingest...")
        result = run_sea_ingest()
        print("SEA ingest result:", result)
    except Exception as e:
        print("SEA ingest error:", e)


@app.get("/")
def root():
    now = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")
    return {"ok": True, "service": "stratmap-chile", "time": now}


@app.get("/health")
def health():
    return {"status": "ok"}
