# connectors/chilebcompra.py
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import requests

TZ = ZoneInfo("America/Santiago")
TICKET = os.getenv("CHILEBCOMPRA_TICKET", "F8537A18-6766-4DEF-9E59-426B4FEE2844")
BASE_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"

KEYWORDS_MINERIA = ["miner", "cobre", "litio", "molibdeno", "relave", "faena", "concentradora", "yacimiento", "salar", "extracción"]
KEYWORDS_INFRA = ["infraestructura", "carretera", "puente", "camino", "ruta", "vialidad", "construcción", "edificación", "obras civiles"]
KEYWORDS_ENERGIA = ["energía", "eléctric", "fotovoltai", "eólica", "subestación", "transmisión", "generación", "solar"]
KEYWORDS_OIL = ["petróleo", "gas natural", "enap", "combustible", "hidrocarburo", "refinería", "gasoducto"]


def classify_industry(title: str, description: str = "") -> Optional[str]:
    blob = (title + " " + description).lower()
    if any(k in blob for k in KEYWORDS_MINERIA):
        return "Minería"
    if any(k in blob for k in KEYWORDS_OIL):
        return "Oil & Gas"
    if any(k in blob for k in KEYWORDS_ENERGIA):
        return "Energía"
    if any(k in blob for k in KEYWORDS_INFRA):
        return "Infraestructura"
    return None


def score_licitacion(industry: Optional[str], monto: Optional[float], title: str) -> int:
    base = 25
    if industry == "Minería":
        base = 65
    elif industry == "Oil & Gas":
        base = 60
    elif industry == "Energía":
        base = 55
    elif industry == "Infraestructura":
        base = 45

    inv = 0
    if monto:
        if monto >= 500_000_000:
            inv = 20
        elif monto >= 100_000_000:
            inv = 15
        elif monto >= 50_000_000:
            inv = 10
        elif monto >= 10_000_000:
            inv = 5

    t = title.lower()
    kw = 0
    if any(k in t for k in ["ampliación", "expansión", "construcción", "montaje", "instalación"]):
        kw += 8
    if any(k in t for k in ["servicio", "mantención", "operación"]):
        kw += 5

    return max(0, min(100, base + inv + kw))


def fetch_day(fecha: str) -> List[Dict[str, Any]]:
    """Trae licitaciones de un día específico. Formato fecha: DDMMAAAA"""
    params = {"fecha": fecha, "ticket": TICKET}
    try:
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("Listado", [])
    except Exception as e:
        print(f"[chilebcompra] error día {fecha}: {e}")
        return []


def fetch_chilebcompra(days_back: int = 30, limit: int = 500) -> List[Dict[str, Any]]:
    now = datetime.now(TZ)
    print(f"[chilebcompra] buscando últimos {days_back} días")

    out: List[Dict[str, Any]] = []

    for i in range(days_back):
        if len(out) >= limit:
            break

        day = now - timedelta(days=i)
        fecha = day.strftime("%d%m%Y")
        licitaciones = fetch_day(fecha)

        for lic in licitaciones:
            title = lic.get("Nombre") or ""
            if not title:
                continue

            description = lic.get("Descripcion") or ""
            industry = classify_industry(title, description)

            if not industry:
                continue

            codigo = lic.get("CodigoExterno") or lic.get("Codigo") or ""
            url = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"

            company = None
            region = None
            if isinstance(lic.get("Comprador"), dict):
                company = lic["Comprador"].get("NombreOrganismo")
                region = lic["Comprador"].get("Region")

            monto = None
            try:
                monto = float(lic.get("MontoEstimado") or 0)
            except Exception:
                pass

            estado = lic.get("Estado") or "Publicada"
            score = score_licitacion(industry, monto, title)

            out.append({
                "source": "chilebcompra",
                "title": title,
                "url": url,
                "company": company,
                "contractor": None,
                "industry": industry,
                "region": region,
                "phase": str(estado),
                "score": score,
                "entry": codigo,
                "raw": lic,
            })

    print(f"[chilebcompra] encontradas {len(out)} licitaciones relevantes")
    return out[:limit]
