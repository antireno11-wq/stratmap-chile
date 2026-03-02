"""
connectors/empleos_indeed.py
Scraper de ofertas laborales mineras en Indeed Chile.
Busca cargos que indican actividad de proyecto/construcción.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

# Búsquedas que indican actividad de proyecto activo
SEARCHES = [
    ("ingeniero proyecto minería", "Antofagasta"),
    ("construcción montaje minera", "Antofagasta"),
    ("supervisor construcción mina", "Atacama"),
    ("jefe proyecto minería", "Chile"),
    ("ingeniero comisionamiento planta", "Chile"),
    ("puesta marcha concentradora", "Chile"),
]

# Empresas mineras clave para cruzar con proyectos
MINING_COMPANIES = [
    "codelco", "bhp", "escondida", "collahuasi", "sqm", "albemarle",
    "antofagasta minerals", "teck", "kinross", "barrick", "goldfields",
    "freeport", "lundin", "enami", "angloamerican", "anglo american",
    "glencore", "vale", "cía minera", "compañía minera", "minera"
]

# Tipos de cargo por señal
SIGNAL_HIGH = [  # Indican construcción/proyecto activo
    "proyecto", "construcción", "montaje", "comisionamiento", "puesta en marcha",
    "ramp-up", "epcm", "epc", "ingeniería", "obras", "ampliación", "expansión"
]
SIGNAL_MED = [  # Indican operaciones en curso
    "producción", "operaciones", "planta", "procesamiento", "mina", "faena",
    "supervisor", "jefe", "coordinador"
]

REGION_MAP = {
    "antofagasta": "Antofagasta", "calama": "Antofagasta", "chuquicamata": "Antofagasta",
    "atacama": "Atacama", "copiapó": "Atacama", "copiapo": "Atacama",
    "valparaíso": "Valparaíso", "valparaiso": "Valparaíso", "los andes": "Valparaíso",
    "o'higgins": "O'Higgins", "rancagua": "O'Higgins", "teniente": "O'Higgins",
    "metropolitana": "Metropolitana", "santiago": "Metropolitana",
    "coquimbo": "Coquimbo", "la serena": "Coquimbo",
    "tarapacá": "Tarapacá", "tarapaca": "Tarapacá", "iquique": "Tarapacá",
}


def classify_signal(title: str) -> tuple:
    """Retorna (tipo, puntos_señal)"""
    t = title.lower()
    if any(k in t for k in SIGNAL_HIGH):
        return ("construcción/proyecto", 15)
    if any(k in t for k in SIGNAL_MED):
        return ("operaciones", 8)
    return ("general", 3)


def extract_company(text: str) -> Optional[str]:
    t = text.lower()
    for co in MINING_COMPANIES:
        if co in t:
            # Capitalizar el nombre encontrado
            idx = t.find(co)
            return text[idx:idx+len(co)].title()
    return None


def parse_region(text: str) -> Optional[str]:
    t = text.lower()
    for k, v in REGION_MAP.items():
        if k in t:
            return v
    return None


def fetch_indeed_search(query: str, location: str, session: requests.Session) -> List[Dict]:
    items = []
    try:
        params = {
            "q": query,
            "l": location,
            "lang": "es",
        }
        url = "https://cl.indeed.com/jobs"
        r = session.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Indeed estructura los jobs en tarjetas
        job_cards = (
            soup.select("[data-jk], .job_seen_beacon, .tapItem, .result") or
            soup.select("li[class*='css']") or
            soup.select(".jobsearch-ResultsList > li")
        )

        print(f"[indeed] '{query}' en '{location}': {len(job_cards)} tarjetas")

        cutoff = (datetime.now(tz=TZ) - timedelta(days=60)).isoformat()

        for card in job_cards[:20]:
            try:
                # Título
                title_el = card.select_one("h2 a span, .jobTitle a, [data-testid='jobTitle']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Empresa
                company_el = card.select_one(".companyName, [data-testid='company-name'], .company")
                company_raw = company_el.get_text(strip=True) if company_el else ""

                # Ubicación
                loc_el = card.select_one(".companyLocation, [data-testid='job-location'], .location")
                location_raw = loc_el.get_text(strip=True) if loc_el else location

                # Link
                link_el = card.select_one("h2 a, .jobTitle a")
                href = link_el.get("href", "") if link_el else ""
                job_url = f"https://cl.indeed.com{href}" if href.startswith("/") else href

                region = parse_region(location_raw) or parse_region(location)
                company = extract_company(f"{company_raw} {title}") or company_raw or None
                signal_type, signal_pts = classify_signal(title)

                items.append({
                    "title": title,
                    "company": company,
                    "company_raw": company_raw,
                    "region": region,
                    "location_raw": location_raw,
                    "url": job_url,
                    "signal_type": signal_type,
                    "signal_pts": signal_pts,
                    "source_query": query,
                    "published_at": None,  # Indeed no siempre da fecha exacta
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[indeed] Error '{query}': {e}")

    return items


def fetch_indeed(limit: int = 200) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    seen = set()

    for query, location in SEARCHES:
        items = fetch_indeed_search(query, location, session)
        for item in items:
            key = f"{item['title']}_{item['company_raw']}"
            if key not in seen:
                seen.add(key)
                all_items.append(item)
        if len(all_items) >= limit:
            break

    print(f"[indeed] Total empleos: {len(all_items)}")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_indeed(limit=20)
    for i in items[:10]:
        print(f"  [{i['signal_pts']}pts] {i['title'][:50]} | {i['company']} | {i['region']}")
