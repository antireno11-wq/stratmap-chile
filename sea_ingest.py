import os
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= CONFIG =========
BASE_URL = os.getenv("BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")
SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "90"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "300"))
DEBUG = os.getenv("DEBUG", "0") == "1"

SEA_LAYERS = [
    "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer/1",
    "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer/2",
]

DATE_FIELDS = ["FECHA_PRESENTACION", "fecha_presentacion", "FECHA_INGRESO", "fecha_ingreso"]


def now_clt() -> str:
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


def safe_str(x) -> str:
    return ("" if x is None else str(x)).strip()


def pick_date_field(field_names: list[str]) -> str | None:
    lower = {f.lower(): f for f in field_names}
    for cand in DATE_FIELDS:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def get_layer_fields(layer_url: str) -> list[str]:
    r = requests.get(f"{layer_url}?f=json", timeout=40)
    r.raise_for_status()
    meta = r.json()
    fields = meta.get("fields") or []
    return [f.get("name") for f in fields if f.get("name")]


def arcgis_query(layer_url: str, where: str, limit: int) -> list[dict]:
    q = f"{layer_url}/query"
    params = {
        "f": "json",
        "where": where,
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": str(limit),
    }
    r = requests.get(q, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") or []
    return [f.get("attributes") or {} for f in feats]


def parse_arcgis_date(value) -> datetime | None:
    # ArcGIS típicamente entrega epoch ms (int)
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            # epoch ms
            return datetime.fromtimestamp(value / 1000, tz=ZoneInfo("America/Santiago"))
        s = str(value)
        # si viene como string raro, lo ignoramos
        return None
    except Exception:
        return None


def classify_industry(title: str) -> str:
    t = title.lower()

    mining = ["mina", "minero", "minera", "lixivi", "relave", "tranque", "concentradora", "cobre", "oro", "plata", "litio"]
    energy = ["solar", "fotovolta", "eólico", "eolica", "bess", "bater", "subestación", "transmis", "línea", "energia", "central"]
    oilgas = ["gas", "gnl", "glp", "oleod", "gasod", "refiner", "terminal", "combustible"]
    infra = ["puerto", "carretera", "ruta", "concesión", "aeropuerto", "hospital", "mall", "centro de distribución", "edificio", "bodega"]

    if any(k in t for k in mining):
        return "Minería"
    if any(k in t for k in oilgas):
        return "Oil & Gas"
    if any(k in t for k in energy):
        return "Energía"
    if any(k in t for k in infra):
        return "Infraestructura"
    return "Otros"


def extract_company(title: str) -> str | None:
    # Heurística simple: si menciona empresas conocidas, las devolvemos
    known = [
        "codelco", "bhp", "amssa", "amsa", "antofagasta minerals", "teck", "anglo american",
        "sqm", "enami", "cap", "colbún", "engie", "enel", "aes", "acciona"
    ]
    tl = title.lower()
    for k in known:
        if k in tl:
            return k.upper() if len(k) <= 5 else k.title()
    return None


def extract_region(attrs: dict) -> str | None:
    # depende de la capa; probamos varios nombres
    for key in ["REGION", "Region", "REGION_PROY", "REGION_NOMBRE", "NOMBRE_REGION"]:
        if key in attrs and attrs.get(key):
            return safe_str(attrs.get(key))
    return None


def extract_title(attrs: dict) -> str:
    for key in ["NOMBRE", "NOMBRE_PROY", "NOMBRE_PROYECTO", "PROYECTO", "NOM_PROYECTO", "NOMBRE_INICIATIVA"]:
        if key in attrs and attrs.get(key):
            return safe_str(attrs.get(key))
    # fallback
    return safe_str(attrs.get("OBJECTID") or "Proyecto SEA")


def extract_code(attrs: dict) -> str | None:
    # tu “código” SEIA lo estás armando como “texto=XXXX”; lo sacamos si existe
    for key in ["CODIGO", "CODIGO_PROY", "COD_SEIA", "ID_PROY", "CODIGO_SEIA"]:
        if key in attrs and attrs.get(key):
            return safe_str(attrs.get(key))
    return None


def build_url(title: str, attrs: dict) -> str:
    code = extract_code(attrs)
    if code and re.match(r"^\d+$", code):
        return f"https://www.sea.gob.cl/buscador-de-proyectos?texto={code}"
    # si no hay código, igual dejamos buscador por título
    q = requests.utils.quote(title[:80])
    return f"https://www.sea.gob.cl/buscador-de-proyectos?texto={q}"


def fetch_sea(days_back: int, limit: int) -> list[dict]:
    cutoff = datetime.now(ZoneInfo("America/Santiago")) - timedelta(days=days_back)
    out: list[dict] = []

    for layer in SEA_LAYERS:
        try:
            fields = get_layer_fields(layer)
            date_field = pick_date_field(fields)

            if DEBUG:
                print(f"[SEA] layer={layer} date_field={date_field}")

            rows = arcgis_query(layer, where="1=1", limit=limit)

            for a in rows:
                title = extract_title(a)
                # filtro por fecha si existe campo
                if date_field and a.get(date_field) is not None:
                    dt = parse_arcgis_date(a.get(date_field))
                    if dt and dt < cutoff:
                        continue

                company = extract_company(title)
                industry = classify_industry(title)
                region = extract_region(a)

                out.append({
                    "source": "sea",
                    "title": title,
                    "url": build_url(title, a),
                    "company": company,
                    "contractor": None,
                    "industry": industry,
                    "region": region,
                    "phase": "Ambiental en curso",
                    "score": 0,
                    "entry": None,
                    "raw": a,
                })

        except Exception as e:
            if DEBUG:
                print(f"[SEA] error layer {layer}: {e}")

    return out


def ingest(items: list[dict]) -> dict:
    url = f"{BASE_URL}/ingest"
    payload = {"items": items}

    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


def main():
    print(f"[{now_clt()}] SEA ingest start -> {BASE_URL}")
    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA fetched: {len(items)} items")

    if not items:
        print(f"[{now_clt()}] nothing to ingest")
        return

    res = ingest(items)
    print(f"[{now_clt()}] ingest result: {res}")


if __name__ == "__main__":
    main()
