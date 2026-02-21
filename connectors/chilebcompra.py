# connectors/chilebcompra.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import requests

TZ = ZoneInfo("America/Santiago")

# API pública de ChileCompra - no requiere autenticación
BASE_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"

# Códigos de rubros relevantes en ChileCompra
RUBROS_MINERIA = ["15", "23", "24"]        # Minerales, combustibles, equipos industriales
RUBROS_INFRA = ["30", "31", "32", "72"]    # Construcción, ingeniería
RUBROS_ENERGIA = ["26", "39", "40", "41"]  # Energía, utilities

KEYWORDS_MINERIA = ["miner", "cobre", "litio", "molibdeno", "relave", "faena", "concentradora", "yacimiento", "salar"]
KEYWORDS_INFRA = ["infraestructura", "carretera", "puente", "camino", "ruta", "vialidad", "construcción", "edificación"]
KEYWORDS_ENERGIA = ["energía", "eléctric", "fotovoltai", "eólica", "subestación", "transmisión", "generación"]
KEYWORDS_OIL = ["petróleo", "gas", "enap", "combustible", "hidrocarburo", "refinería", "gasoducto"]


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
        if monto >= 500_000_000:   # sobre 500M CLP
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


def fetch_licitaciones_page(fecha_ini: str, fecha_fin: str, page: int = 1) -> Dict[str, Any]:
    params = {
        "fechaInicio": fecha_ini,
        "fechaFin": fecha_fin,
        "pagina": page,
        "ticket": "guest",  # acceso público sin ticket
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[chilebcompra] error página {page}: {e}")
        return {}


def fetch_chilebcompra(days_back: int = 30, limit: int = 500) -> List[Dict[str, Any]]:
    now = datetime.now(TZ)
    fecha_ini = (now - timedelta(days=days_back)).strftime("%d%m%Y")
    fecha_fin = now.strftime("%d%m%Y")

    print(f"[chilebcompra] buscando licitaciones {fecha_ini} → {fecha_fin}")

    out: List[Dict[str, Any]] = []
    page = 1

    while len(out) < limit:
        data = fetch_licitaciones_page(fecha_ini, fecha_fin, page)

        licitaciones = data.get("Listado", [])
        if not licitaciones:
            break

        for lic in licitaciones:
            title = lic.get("Nombre") or lic.get("NombreLicitacion") or ""
            if not title:
                continue

            description = lic.get("Descripcion") or ""
            industry = classify_industry(title, description)

            # Solo incluir rubros relevantes
            if not industry:
                continue

            codigo = lic.get("CodigoExterno") or lic.get("Codigo") or ""
            url = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"

            company = lic.get("Comprador", {}).get("NombreOrganismo") or lic.get("NombreOrganismo") or None
            region = lic.get("Comprador", {}).get("Region") or None

            monto = None
            try:
                monto = float(lic.get("MontoEstimado") or 0)
            except Exception:
                pass

            estado = lic.get("Estado") or lic.get("CodigoEstado") or "Publicada"
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

        total = data.get("Cantidad", 0)
        fetched_so_far = page * len(licitaciones)
        if fetched_so_far >= total:
            break

        page += 1

    print(f"[chilebcompra] encontradas {len(out)} licitaciones relevantes")
    return out[:limit]
