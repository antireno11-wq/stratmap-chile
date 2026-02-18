from fastapi import FastAPI, Query
from storage import init_db, insert_item, list_items

app = FastAPI(title="Stratmap Chile")

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/projects")
def projects(limit: int = Query(50, ge=1, le=500)):
    return {"items": list_items(limit=limit)}

@app.post("/ingest")
def ingest():
    # Por ahora: inserta 1 item demo para probar el flujo end-to-end
    insert_item(
        title="Demo: Proyecto ejemplo",
        url="https://www.sea.gob.cl/",
        source="demo",
    )
    return {"ok": True, "inserted": 1}
