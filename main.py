from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI(title="StratMap Chile API")

@app.get("/")
def home():
    return {
        "product": "StratMap",
        "country": "Chile",
        "status": "running",
        "time_cl": datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S"),
    }

@app.get("/health")
def health():
    return {"ok": True}
