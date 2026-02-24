# connectors/chilebcompra.py
import re
import time
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
    "carretera", "vialidad", "embalse", "túnel",
    "planta industrial", "faena", "concentradora", "relave",
    "gas natural", "petróleo", "gasoducto",
]


# Patrones robustos con lookahead/lookbehind para manejar tildes y unicode
# (?<![a-záéíóúüñ]) = no precedido por letra
# (?![a-záéíóúüñ])  = no seguido por letra
def _w(word):
    """Envuelve una palabra con boundaries que funcionan con tildes."""
    return r"(?<![a-záéíóúüñA-ZÁÉÍÓÚÜÑ])" + word + r"(?![a-záéíóúüñA-ZÁÉÍÓÚÜÑ])"


INDUSTRY_PATTERNS = [
    # Minería — cuidado con falsos positivos (vitamina, albumina, protamina, etc.)
    (_w("minería"),         "Minería"),
    (_w("minero"),          "Minería"),
    (_w("minera"),          "Minería"),
    (_w("mina"),            "Minería"),
    (_w("cobre"),           "Minería"),
    (_w("litio"),           "Minería"),
    (_w("molibdeno"),       "Minería"),
    (_w("concentradora"),   "Minería"),
    (_w("relave"),          "Minería"),
    (r"faena minera",       "Minería"),
    (_w("yacimiento"),      "Minería"),
    (_w("perforación"),     "Minería"),
    (_w("tronadura"),       "Minería"),
    (_w("shovel"),          "Minería"),
    # Energía
    (r"panel(?:es)? solar", "Energía"),
    (r"energía solar",      "Energía"),
    (r"energía eólica",     "Energía"),
    (_w("fotovoltaico"),    "Energía"),
    (_w("subestación"),     "Energía"),
    (r"transmisión eléctrica", "Energía"),
    (r"línea de transmisión",  "Energía"),
    # Infraestructura — más específico para evitar "Puente Alto" (comuna)
    (_w("carretera"),       "Infraestructura"),
    (_w("autopista"),       "Infraestructura"),
    (r"dirección de vialidad.*construcc", "Infraestructura"),
    (_w("embalse"),         "Infraestructura"),
    (_w("túnel"),           "Infraestructura"),
    (r"puente (?:vial|caminero|nuevo|vehicular)", "Infraestructura"),
    (r"obra vial",          "Infraestructura"),
    # Oil & Gas
    (_w("petróleo"),        "Oil & Gas"),
    (r"gas natural",        "Oil & Gas"),
    (_w("gasoducto"),       "Oil & Gas"),
]

# Blacklist — títulos que nunca deben entrar aunque matcheen un keyword
TITLE_BLACKLIST = re.compile(
    r"(medicamento|fármaco|vitamina|albumina|protamina|metformina|rifaximina|"
    r"clomipramina|sitagliptin|linagliptin|piridostigmin|colestiramina|"
    r"amikacina|prealbumina|inmunoglobulina|arginina|glutamina|lactante|"
    r"show artístic|concierto|orquesta|sinfónic|evento verano|semana \w+ina|"
    r"luminaria|área verde|mejoramiento urban|aseo integral|vigilancia presencial|"
    r"servicio audiovisual|arriendo camión|arriendo rodillo|sub-base granular|"
    r"emulsión asfáltica|catastro de aguas)",
    re.IGNORECASE
)

# Compilar patrones
_COMPILED = [(re.compile(p, re.IGNORECASE), ind) for p, ind in INDUSTRY_PATTERNS]


def classify(title, desc=""):
    # Primero revisar blacklist
    if TITLE_BLACKLIST.search(title + " " + desc):
        return None
    blob = title + " " + desc
    for pattern, ind in _COMPILED:
        if pattern.search(blob):
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


def fetch_detail(code: str, ticket: str, session) -> dict:
    """Llama al endpoint de detalle para obtener organismo y unidad."""
    try:
        url = f"{SEARCH_URL}?codigo={code}&ticket={ticket}"
        r = session.get(url, timeout=15, headers={"User-Agent": "StratmapWorker/0.2"})
        r.raise_for_status()
        data = r.json()
        licitacion = data.get("Listado", [{}])[0] if data.get("Listado") else {}
        comprador = licitacion.get("Comprador") or {}
        return {
            "organismo": comprador.get("NombreOrganismo") or licitacion.get("NombreOrganismo") or "",
            "unidad":    comprador.get("NombreUnidad")    or licitacion.get("NombreUnidad")    or "",
            "region":    comprador.get("RegionUnidad")    or licitacion.get("RegionUnidad")    or "",
        }
    except Exception:
        return {}


def process_licitacion(item, detail: dict = None):
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
    code = item.get("CodigoExterno") or item.get("Codigo") or ""

    # Usar detalle si está disponible, sino intentar desde item
    d = detail or {}
    organismo = d.get("organismo") or item.get("NombreOrganismo") or item.get("Organismo") or None
    unidad    = d.get("unidad")    or item.get("NombreUnidad")    or item.get("Unidad")    or None
    region    = d.get("region")    or item.get("RegionUnidad")    or item.get("Region")    or None

    url = (
        f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={code}"
        if code else "https://www.mercadopublico.cl"
    )
    return {
        "source": "Chile Compra",
        "title": name[:500],
        "url": url,
        "company":    str(organismo)[:200] if organismo else None,
        "contractor": str(unidad)[:200]    if unidad    else None,
        "industry": industry,
        "region": str(region)[:100] if region else None,
        "phase": item.get("EstadoLicitacion") or item.get("CodigoEstado") or "Activa",
        "score": score_licitacion(monto, industry, name),
        "entry": code,
        "raw": {**item, **({"_detail": d} if d else {})},
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
                code = item.get("CodigoExterno") or item.get("Codigo") or ""
                detail = fetch_detail(code, ticket, session) if code else {}
                o = process_licitacion(item, detail)
                if o and o["entry"] not in seen:
                    seen.add(o["entry"])
                    results.append(o)
                time.sleep(0.3)  # evitar error de peticiones simultáneas
        if len(results) >= limit:
            break

    if not date_success:
        print("[chilebcompra] fechas fallaron, usando búsqueda por keywords...")
        for kw in KEYWORDS:
            items = fetch_by_keyword(kw, ticket, session)
            for item in items:
                code = item.get("CodigoExterno") or item.get("Codigo") or ""
                detail = fetch_detail(code, ticket, session) if code else {}
                o = process_licitacion(item, detail)
                if o:
                    key = o["entry"] or o["title"]
                    if key not in seen:
                        seen.add(key)
                        results.append(o)
                time.sleep(0.3)
            if len(results) >= limit:
                break

    print(f"[chilebcompra] encontradas {len(results)} licitaciones relevantes")
    return results[:limit]
