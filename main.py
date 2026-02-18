from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI(title="Stratmap Chile")

def ch_time():
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")

@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile", "time": ch_time()}

@app.get("/health")
def health():
    return {"status": "ok", "time": ch_time()}

@app.get("/opportunities")
def opportunities():
    # por ahora dummy, después lo conectamos a Postgres
    return {"count": 0, "items": [], "time": ch_time()}
