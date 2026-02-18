from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo
import threading
import os

from db import init_db_safe
from sea_ingest import run_sea_ingest

app = FastAPI(title="Stratmap Chile API", version="0.1.0")


def _run_ingest_async():
    try:
        print("🌊 [SEA] Ingest starting...")
        out = run_sea_ingest()
        print("✅ [SEA] Ingest done:", out)
    except Exception as e:
        print("❌ [SEA] Ingest error:", repr(e))


@app.on_event("startup")
def startup():
    print("🚀 Stratmap starting...")
    init_db_safe()

    # Flag para poder apagar/encender el ingest desde Variables en Railway
    run_on_start = os.getenv("RUN_INGEST_ON_START", "1") == "1"

    if run_on_start:
        t = threading.Thread(target=_run_ingest_async, daemon=True)
        t.start()
        print("🧵 Ingest thread launched")
    else:
        print("⏭️ RUN_INGEST_ON_START=0, no se ejecuta ingest al arrancar")


@app.get("/")
def root():
    now = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")
    return {"ok": True, "service": "stratmap-chile", "time": now}


@app.get("/health")
def health():
    now = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")
    return {"status": "ok", "time": now}
