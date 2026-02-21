# connectors/chilebcompra.py
import requests
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
SEARCH_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
DEFAULT_TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"

KEYWORDS = [
    "minería", "mina", "cobre", "litio", "molibdeno",
    "energía solar", "energía eólica", "subestación", "transmisión eléctrica",
    "carretera", "puente", "túnel", "vialidad", "embalse",
    "planta industrial", "faena", "concentradora", "relave",
    "gas natural", "petróleo", "gasoducto",
]

INDUSTRIES = {
    "minería": "Minería", "mina ": "Minería", "cobre": "Minería",
    "litio": "Minería", "molibdeno": "Minería", "concentradora": "Minería",
    "relave": "Minería", "faena": "Minería", "yacimiento": "Minería",
    "solar": "Energía", "eólica": "Energía", "subestación": "Energía",
    "transmisión": "Energía", "fotovoltai": "Energía",
    "carretera": "Infraestructura", "puente": "Infraestructura",
    "vialidad": "Infraestructura", "embalse": "Infraestructura", "túnel": "Infraestructura",
    "petróleo": "Oil & Gas", "gas natural": "Oil & Gas", "gasoducto": "Oil & Gas",
}


def classify(title, desc=""):
    blob = (title + " " + desc).lower()
    for kw, ind in INDUSTRIES.items():
        if kw in blob:
            return ind
    return None


def score_licitacion(monto, industry, title):
    base = {"Minería": 65, "Oil & Gas": 60, "Energía": 55, "Infraestructura": 45}.get(industry or "", 40)
    inv = 0
    if monto:
        if monto >= 500_000_000: inv = 20
        elif monto >= 100_000_000: inv = 15
        elif monto >= 50_000_000: inv = 10
    kw = 0
    t = title.lower()
    if any(k in t for k in ["ampliación", "construcción", "nueva planta"]): kw = 8
    elif any(k in t for k in ["servicio", "mantención", "operación"]): kw = 5
    return max(0, min(100, base + inv + kw))


def process_licitacion(item):
    name = item.get("Nombre") or item.get("NombreLicitacion") or ""
    desc = item.get("Descripcion") or item.get("DescripcionLicitacion") or ""
    industry = classify(name, desc)
    if not industry:
        return None
    monto = None
    for k in ["MontoEstimado", "Monto", "MontoTotal"]:
        try:
            v = float(item.get(k) or 0)
            if v > 0:
                monto = v
                break
        except Exception:
            pass
    org = item.get("NombreOrganismo") or item.get("Organismo") or None
    region = item.get("RegionUnidad") or item.get("Region") or None
    code = item.get("CodigoExterno") or item.get("Codigo") or ""
    url = (
        f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={code}"
        if code else "https://www.mercadopublico.cl"
    )
    return {
        "source": "ChileCompra",
        "title": name[:500],
        "url": url,
        "company": str(org)[:200] if org else None,
        "contractor": None,
        "industry": industry,
        "region": str(region)[:100] if region else None,
        "phase": item.get("EstadoLicitacion") or "Activa",
        "score": score_licitacion(monto, industry, name),
        "entry": code,
        "raw": item,
    }


def fetch_by_date(date_str, ticket, session):
    url = f"{SEARCH_URL}?fecha={date_str}&ticket={ticket}"
    try:
        r = session.get(url, timeout=30, headers={"User-Agent": "StratmapWorker/0.2"})
        r.raise_for_status()
        return r.json().get("Listado") or []
    except Exception as e:
        print(f"[chilebcompra] error día {date_str}: {e}")
        return []


def fetch_by_keyword(keyword, ticket, session):
    url = f"{SEARCH_URL}?buscar={requests.utils.quote(keyword)}&ticket={ticket}&cantidad=100"
    try:
        r = session.get(url, timeout=30, headers={"User-Agent": "StratmapWorker/0.2"})
        r.raise_for_status()
        return r.json().get("Listado") or []
    except Exception as e:
        print(f"[chilebcompra] keyword '{keyword}' error: {e}")
        return []


def fetch_chilebcompra(days_back=30, limit=500):
    ticket = os.getenv("CHILEBCOMPRA_TICKET", DEFAULT_TICKET)
    session = requests.Session()
    seen = set()
    results = []
    today = datetime.now(TZ)
    date_success = False

    print(f"[chilebcompra] buscando últimos {days_back} días")
    for i in range(days_back):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        date_str = d.strftime("%d%m%Y")
        items = fetch_by_date(date_str, ticket, session)
        if items:
            date_success = True
            for item in items:
                o = process_licitacion(item)
                if o and o["entry"] not in seen:
                    seen.add(o["entry"])
                    results.append(o)
        if len(results) >= limit:
            break

    if not date_success:
        print("[chilebcompra] fechas fallaron, usando búsqueda por keywords...")
        for kw in KEYWORDS:
            items = fetch_by_keyword(kw, ticket, session)
            for item in items:
                o = process_licitacion(item)
                if o:
                    key = o["entry"] or o["title"]
                    if key not in seen:
                        seen.add(key)
                        results.append(o)
            if len(results) >= limit:
                break

    print(f"[chilebcompra] encontradas {len(results)} licitaciones relevantes")
    return results[:limit]
