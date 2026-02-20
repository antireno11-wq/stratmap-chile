# connectors/sea.py
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests

TZ = ZoneInfo("America/Santiago")

DEBUG = False

SEA_LAYERS = [
    # Ajusta si tienes más layers
    "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer/1",
    "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer/2",
]

REGION_MAP = {
    "I": "Tarapacá",
    "II": "Antofagasta",
    "III": "Atacama",
    "IV": "Coquimbo",
    "V": "Valparaíso",
    "VI": "O'Higgins",
    "VII": "Maule",
    "VIII": "Biobío",
    "IX": "La Araucanía",
    "X": "Los Lagos",
    "XI": "Aysén",
    "XII": "Magallanes",
    "RM": "Región Metropolitana",
    "XIV": "Los Ríos",
    "XV": "Arica y Parinacota",
    "XVI": "Ñuble",
}


def arcgis_query(layer_url: str, where: str = "1=1", limit: int = 500) -> List[Dict[str, Any]]:
    # ArcGIS REST query endpoint
    url = layer_url.rstrip("/") + "/query"
    params = {
        "where": where,
        "outFields": "*",
        "f": "json",
        "resultRecordCount": limit,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features", [])
    out = []
    for f in feats:
        attrs = f.get("attributes") or {}
        out.append(attrs)
    return out


def parse_arcgis_date(ms: Any) -> Optional[datetime]:
    try:
        if ms is None:
            return None
        ms = int(ms)
        # ArcGIS suele traer epoch ms
        return datetime.fromtimestamp(ms / 1000, tz=TZ)
    except Exception:
        return None


def region_label(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip().upper()
    return REGION_MAP.get(code, code)


def classify_industry(title: str, typology: Optional[str]) -> Optional[str]:
    t = (title or "").lower()
    ty = (typology or "").lower()

    blob = f"{t} {ty}"

    if any(k in blob for k in ["minera", "faena", "yacimiento", "mina", "relave", "concentradora", "chancado"]):
        return "Minería"
    if any(k in blob for k in ["agroindustria", "packing", "fruta", "congelamiento", "empacamiento", "planta"]):
        return "Agroindustria"
    if any(k in blob for k in ["energía", "fotovolta", "eólica", "subestación", "línea de transmisión"]):
        return "Energía"
    if any(k in blob for k in ["puerto", "terminal", "muelle"]):
        return "Portuario"
    if any(k in blob for k in ["carretera", "ruta", "camino", "puente"]):
        return "Infraestructura"
    return None


def score_v1(industry: Optional[str], title: str, inv_usd: Optional[float]) -> int:
    base = 30
    if industry == "Minería":
        base = 60
    elif industry == "Energía":
        base = 55
    elif industry == "Infraestructura":
        base = 45
    elif industry == "Agroindustria":
        base = 40

    t = (title or "").lower()

    kw = 0
    # keywords de oportunidad (muy simple)
    if any(k in t for k in ["ampliación", "expansión", "aumento"]):
        kw += 10
    if any(k in t for k in ["planta", "campamento", "oficinas", "instalación"]):
        kw += 8
    if any(k in t for k in ["construcción", "montaje", "habilitación"]):
        kw += 8

    inv = 0
    try:
        if inv_usd is not None:
            inv_usd = float(inv_usd)
            if inv_usd >= 50_000_000:
                inv = 20
            elif inv_usd >= 10_000_000:
                inv = 15
            elif inv_usd >= 1_000_000:
                inv = 10
            elif inv_usd >= 100_000:
                inv = 5
    except Exception:
        pass

    s = base + kw + inv
    return max(0, min(100, int(s)))


def fetch_sea(days_back: int = 90, limit: int = 800) -> List[Dict[str, Any]]:
    cutoff = datetime.now(TZ) - timedelta(days=days_back)
    out: List[Dict[str, Any]] = []

    for layer in SEA_LAYERS:
        rows = arcgis_query(layer, where="1=1", limit=limit)

        for a in rows:
            title = (a.get("NOMBRE_PROYECTO") or a.get("NOMBRE") or a.get("PROYECTO") or f"Proyecto SEA {a.get('OBJECTID')}").strip()

            # fecha: intenta FECHA_PRESENTACION si existe
            dt = parse_arcgis_date(a.get("FECHA_PRESENTACION")) or parse_arcgis_date(a.get("FECHA_CALIFICACION"))
            if dt and dt < cutoff:
                continue

            url = a.get("URL_EXPEDIENTE")
            if not url:
                # fallback al buscador por título
                q = requests.utils.quote(title[:80])
                url = f"https://www.sea.gob.cl/buscador-de-proyectos?texto={q}"

            company = a.get("TITULAR") or None
            reg_code = a.get("REGION")
            region = region_label(reg_code)

            typology = a.get("NOMBRE_TIPOLOGIA") or None
            industry = classify_industry(title, typology)

            inv_usd = a.get("INVERSION_US")
            score = score_v1(industry, title, inv_usd)

            out.append({
                "source": "sea",
                "title": title,
                "url": url,
                "company": company,
                "contractor": None,
                "industry": industry,
                "region": region,
                "phase": a.get("ESTADO_EVALUACION") or "Ambiental en curso",
                "score": score,
                "entry": None,
                "raw": a,
            })

    return out
