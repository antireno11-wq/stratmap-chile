import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db import init_db_safe, db_health, upsert_opportunities, list_opportunities

# =========================
# App
# =========================
app = FastAPI(title="Stratmap Chile API", version="0.1.0")

# (opcional) CORS por si después haces frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Startup: NO inicializar DB en import
# =========================
@app.on_event("startup")
def startup_event():
    # Esto ayuda a ver logs en Railway
    print("### STARTING STRATMAP ###", flush=True)
    # Crea tabla si no existe, pero NO bota la app si DB está caída
    init_db_safe()
    print("### STARTUP DONE ###", flush=True)


# =========================
# Models
# =========================
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


# =========================
# Minimal UI (home)
# =========================
@app.get("/", response_class=HTMLResponse)
def home():
    # Dominio público (Railway) para que puedas copiar/pegar
    # Si no existe, igual mostramos lo básico.
    public_url = os.getenv("PUBLIC_URL", "").strip()
    if not public_url:
        # fallback: lo que tú ya tienes desplegado (puedes cambiarlo)
        public_url = "https://stratmap-chile-production.up.railway.app"

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Stratmap</title>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
          code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 6px; }}
          a {{ color: #0b5fff; text-decoration: none; }}
          a:hover {{ text-decoration: underline; }}
          .box {{ border: 1px solid #eee; border-radius: 12px; padding: 16px; margin-top: 16px; }}
          .title {{ font-size: 22px; font-weight: 700; }}
          .sub {{ color: #555; margin-top: 4px; }}
          ul {{ margin: 10px 0 0 18px; }}
        </style>
      </head>
      <body>
        <div class="title">Stratmap Chile</div>
        <div class="sub">API + Ingest (SEA/RSS) - UI mínima</div>

        <div class="box">
          <div><b>Links rápidos</b></div>
          <ul>
            <li><a href="{public_url}/health" target="_blank">{public_url}/health</a></li>
            <li><a href="{public_url}/docs" target="_blank">{public_url}/docs</a></li>
            <li><a href="{public_url}/opportunities" target="_blank">{public_url}/opportunities</a></li>
          </ul>
        </div>

        <div class="box">
          <div><b>Probar ingest (ejemplo)</b></div>
          <p>En <code>POST {public_url}/ingest</code> con JSON:</p>
          <pre style="background:#f8f8f8;padding:12px;border-radius:10px;overflow:auto;">
{{
  "items": [
    {{
      "source": "manual",
      "title": "Test UI Stratmap",
      "url": "https://example.com/ui-test",
      "company": "BHP",
      "industry": "Minería",
      "region": "Antofagasta",
      "phase": "Ambiental en curso",
      "score": 80,
      "entry": "expansión",
      "raw": {{"hello":"world"}}
    }}
  ]
}}
          </pre>
        </div>
      </body>
    </html>
    """
    return html


# =========================
# Health
# =========================
@app.get("/health")
def health():
    ok, msg = db_health()
    return {"status": "ok", "db_ok": ok, "db_msg": msg}


# =========================
# Ingest + List
# =========================
@app.post("/ingest")
def ingest(body: IngestBody):
    items = [i.model_dump() for i in body.items]
    inserted, updated = upsert_opportunities(items)
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(items)}


@app.get("/opportunities")
def opportunities(q: Optional[str] = None, limit: int = 50):
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows}
