"""
connectors/chilebcompra.py
Scraper de licitaciones de ChileCompra usando el buscador web público.
No requiere ticket API.
"""

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")

# Buscador público de ChileCompra — no requiere autenticación
SEARCH_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/ListSearch.aspx"
BASE_URL = "https://www.mercadopublico.cl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "es-CL,es;q=0.9",
}

KEYWORDS_MINERIA = [
    "minera", "mina", "minería", "cobre", "litio", "molibdeno",
    "relave", "concentradora", "chancado", "perforación",
    "codelco", "bhp", "escondida", "collahuasi", "antofagasta minerals",
    "teck", "sqm", "albemarle", "kinross", "goldfields",
]

KEYWORDS_INFRA = [
    "obras civiles", "construcción", "infraestructura", "vialidad",
    "puente", "camino", "pavimentación", "alcantarillado",
]

KEYWORDS_ENERGIA = [
    "energía", "solar", "eólica", "fotovoltaica", "subestación",
    "transmisión eléctrica", "generación",
]

ALL_KEYWORDS = KEYWORDS_MINERIA + KEYWORDS_INFRA + KEYWORDS_ENERGIA


def classify_industry(title: str, organismo: str) -> str:
    text = f"{title} {organismo}".lower()
    if any(k in text for k in KEYWORDS_MINERIA):
        return "Minería"
    if any(k in text for k in KEYWORDS_ENERGIA):
        return "Energía"
    if any(k in text for k in KEYWORDS_INFRA):
        return "Infraestructura"
    return "Infraestructura"


def score_licitacion(title: str, industry: str, monto: Optional[str]) -> int:
    base = 45
    if industry == "Minería":
        base = 65
    elif industry == "Energía":
        base = 58

    t = title.lower()
    if any(k in t for k in ["construcción", "montaje", "obras", "ampliación"]):
        base += 8
    if any(k in t for k in ["servicio", "mantención", "operación"]):
        base += 5

    return min(base, 85)


def parse_region(text: str) -> Optional[str]:
    regiones = [
        "Tarapacá", "Antofagasta", "Atacama", "Coquimbo", "Valparaíso",
        "O'Higgins", "Maule", "Biobío", "Araucanía", "Los Lagos",
        "Aysén", "Magallanes", "Metropolitana", "Los Ríos", "Arica", "Ñuble"
    ]
    t = text.lower()
    for r in regiones:
        if r.lower() in t:
            return r
    return None


def search_chilebcompra(keyword: str, session: requests.Session) -> List[Dict]:
    """Busca licitaciones en el portal web de ChileCompra."""
    try:
        params = {
            "hddSearch": keyword,
            "ddlRegion": "0",
            "ddlCategory": "0",
            "ddlOrganismType": "0",
        }
        r = session.get(SEARCH_URL, params=params, timeout=20, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        # Las licitaciones están en una tabla o lista de resultados
        rows = soup.select("table.table tr, .resultado-licitacion, li.licitacion")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Extraer datos de la fila
            title_el = row.find("a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if len(title) < 10:
                continue

            href = title_el.get("href", "")
            url = BASE_URL + href if href.startswith("/") else href

            # Organismo
            organismo = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            # Fecha
            fecha = cells[-1].get_text(strip=True) if cells else ""
            # Región del organismo
            region = parse_region(organismo + " " + title)
            industry = classify_industry(title, organismo)

            items.append({
                "title": title,
                "url": url or SEARCH_URL,
                "organismo": organismo,
                "fecha": fecha,
                "region": region,
                "industry": industry,
            })

        return items

    except Exception as e:
        print(f"[chilebcompra] Error buscando '{keyword}': {e}")
        return []


def fetch_chilebcompra(limit: int = 300) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    seen_urls = set()

    # Buscar por keywords relevantes (agrupados para no hacer demasiadas requests)
    search_terms = [
        "minera", "cobre", "litio", "codelco",
        "obras civiles minería", "energía solar",
        "construcción industrial", "mantención minera",
    ]

    for kw in search_terms:
        print(f"[chilebcompra] buscando: {kw}")
        rows = search_chilebcompra(kw, session)

        for row in rows:
            url = row["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            industry = row["industry"]
            score = score_licitacion(row["title"], industry, None)

            all_items.append({
                "source": "Chile Compra",
                "title": row["title"][:400],
                "url": url,
                "company": row["organismo"] or None,
                "contractor": None,
                "industry": industry,
                "region": row["region"],
                "phase": "Licitación",
                "score": score,
                "entry": None,
                "raw": {
                    "organismo": row["organismo"],
                    "fecha": row["fecha"],
                    "keyword": kw,
                    "tipo": "chilebcompra_web"
                }
            })

        time.sleep(1)
        if len(all_items) >= limit:
            break

    print(f"[chilebcompra] {len(all_items)} licitaciones encontradas")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_chilebcompra(limit=50)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i['company']} | {i['region']}")
