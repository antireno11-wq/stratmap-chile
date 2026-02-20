import os
from pathlib import Path
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa DB sin botar si Postgres no está listo todavía
init_db_safe()

# Monta /static SOLO si existe la carpeta (si no, NO revienta)
STATIC_DIR = Path("static")
if STATIC_DIR.exists() and STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
# API
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
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(items)}


@app.get("/opportunities")
def opportunities(
    q: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
):
    rows = list_opportunities(q=q, limit=limit)
    return {"count": len(rows), "items": rows}


# ---------------------------------------------------
# UI mínima (sin archivos)
# ---------------------------------------------------
UI_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Stratmap - UI</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; }
    .row { display:flex; gap: 12px; align-items:center; flex-wrap: wrap; }
    input { padding: 10px; min-width: 260px; }
    button { padding: 10px 14px; cursor: pointer; }
    table { border-collapse: collapse; width: 100%; margin-top: 18px; }
    th, td { border-bottom: 1px solid #eee; padding: 10px; text-align: left; vertical-align: top; }
    th { position: sticky; top: 0; background: #fff; }
    .pill { display:inline-block; padding: 2px 8px; border: 1px solid #ddd; border-radius: 999px; font-size: 12px; }
    .muted { color:#666; font-size: 12px; }
  </style>
</head>
<body>
  <h1>Stratmap</h1>
  <div class="row">
    <input id="q" placeholder="Buscar (title / company / industry / region)"/>
    <button onclick="load()">Buscar</button>
    <button onclick="document.getElementById('q').value=''; load()">Limpiar</button>
    <span class="muted" id="meta"></span>
  </div>

  <table>
    <thead>
      <tr>
        <th>Score</th>
        <th>Título</th>
        <th>Company</th>
        <th>Industria</th>
        <th>Región</th>
        <th>Fuente</th>
        <th>Link</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

<script>
async function load() {
  const q = document.getElementById('q').value.trim();
  const url = new URL('/opportunities', window.location.origin);
  url.searchParams.set('limit', '200');
  if (q) url.searchParams.set('q', q);

  const res = await fetch(url.toString());
  const data = await res.json();

  document.getElementById('meta').textContent = `Mostrando ${data.count} oportunidades`;

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  for (const it of data.items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="pill">${it.score ?? 0}</span></td>
      <td>${escapeHtml(it.title ?? '')}<div class="muted">${escapeHtml(it.phase ?? '')}</div></td>
      <td>${escapeHtml(it.company ?? '')}</td>
      <td>${escapeHtml(it.industry ?? '')}</td>
      <td>${escapeHtml(it.region ?? '')}</td>
      <td>${escapeHtml(it.source ?? '')}</td>
      <td><a href="${it.url}" target="_blank" rel="noopener">abrir</a></td>
    `;
    tbody.appendChild(tr);
  }
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[m]));
}
load();
</script>
</body>
</html>
"""

@app.get("/ui", response_class=HTMLResponse)
def ui():
    # Si existe templates/index.html lo usa, si no, usa UI embebida
    tpl = Path("templates/index.html")
    if tpl.exists():
        return HTMLResponse(tpl.read_text(encoding="utf-8"))
    return HTMLResponse(UI_HTML)
