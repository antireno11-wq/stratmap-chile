import os
from fastapi import FastAPI
from db import init_db, list_opportunities

app = FastAPI(title="Stratmap Chile")

@app.on_event("startup")
def on_startup():
    # Crea tablas al iniciar
    init_db()

@app.get("/")
def root():
    return {"ok": True, "service": "stratmap-chile"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/opportunities")
def opportunities(limit: int = 50):
    rows = list_opportunities(limit=limit)
    return {"count": len(rows), "items": rows}
