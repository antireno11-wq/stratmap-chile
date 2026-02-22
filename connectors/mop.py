# connectors/mop.py
import requests
from bs4 import BeautifulSoup
from typing import Any, Dict, List

BASE_URL = "https://proyectos.mop.gob.cl"
SEARCH_URL = f"{BASE_URL}/Default.asp"
HEADERS = {"User-Agent": "StratmapWorker/0.3"}

REGION_MAP = {
    "Arica y Parinacota": "Arica y Parinacota",
    "Tarapacá": "Tarapacá",
    "Antofagasta": "Antofagasta",
    "Atacama": "Atacama",
    "Coquimbo": "Coquimbo",
    "Valparaíso": "Valparaíso",
    "Metropolitana": "Región Metropolitana",
    "O'Higgins": "O'Higgins",
    "Maule": "Maule",
    "Ñuble": "Ñuble",
    "Biobío": "Biobío",
    "Araucanía": "La Araucanía",
    "Los Ríos": "Los Ríos",
    "Los Lagos": "Los Lagos",
    "Aysén": "Aysén",
    "Magallanes": "Magallanes",
    "Interregional": "Interregional",
}

SERVICE_INDUSTRY = {
    "Vialidad":             "Infraestructura",
    "Portuarias":           "Infraestructura",
    "Aeropuertos":          "Infraestructura",
    "Hidráulicas":          "Infraestructura",
    "Arquitectura":         "Infraestructura",
    "Sanitarios Rurales":   "Infraestructura",
}

def normalize_region(raw: str) -> str:
    for key, val in REGION_MAP.items():
        if key.lower() in raw.lower():
            return val
    return raw.strip()

def normalize_service(raw: str) -> str:
    for key in SERVICE_INDUSTRY:
        if key.lower() in raw.lower():
            return key
    return raw.strip()

def score_project(name: str, service: str, program: str) -> int:
    base = 50
    name_l = name.lower()
    prog_l = (program or "").lower()
    # Proyectos grandes
    if any(k in name_l for k in ["construccion", "ampliacion", "nuevo"]):
        base += 10
    if any(k in name_l for k in ["ruta", "autopista", "carretera"]):
        base += 8
    if any(k in name_l for k in ["puente", "túnel", "embalse"]):
        base += 8
    if any(k in name_l for k in ["aeropuerto", "puerto", "portuario"]):
        base += 10
    if "mejoramiento" in name_l:
        base += 5
    if "conservacion" in name_l:
        base += 3
    return min(base, 90)

def fetch_page(page: int, session: requests.Session) -> List[Dict[str, Any]]:
    params = {
        "whichpage": page,
        "buscar": "true",
        "vigente": "",
        "region": "null",
        "planes": "",
        "servicios": "null",
        "clasificadores": "",
        "palabras": "",
        "pagesize": 20,
    }
    try:
        r = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = "latin-1"
    except Exception as e:
        print(f"[mop] error página {page}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    # La tabla de proyectos tiene columnas: Región, Servicio, Nombre, BIP, Programa
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            texts = [c.get_text(strip=True) for c in cols]
            # Detectar fila de datos: primera col es una región conocida
            region_raw = texts[0]
            if not any(k.lower() in region_raw.lower() for k in REGION_MAP):
                continue

            service_raw = texts[1] if len(texts) > 1 else ""
            # Nombre y link del proyecto
            link_tag = cols[2].find("a") if len(cols) > 2 else None
            name = link_tag.get_text(strip=True) if link_tag else texts[2]
            href = link_tag.get("href", "") if link_tag else ""
            url = f"{BASE_URL}/{href}" if href and not href.startswith("http") else href
            if not url:
                continue

            bip = texts[3] if len(texts) > 3 else ""
            program = texts[4] if len(texts) > 4 else ""

            region = normalize_region(region_raw)
            service = normalize_service(service_raw)

            results.append({
                "source": "MOP",
                "title": name[:500],
                "url": url,
                "company": "MOP",
                "contractor": None,
                "industry": "Infraestructura",
                "region": region,
                "phase": "En ejecución",
                "score": score_project(name, service, program),
                "entry": bip or None,
                "raw": {
                    "bip": bip,
                    "service": service_raw,
                    "program": program,
                    "region": region_raw,
                },
            })

    return results


def fetch_mop(max_pages: int = 40, limit: int = 500) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        items = fetch_page(page, session)
        if not items:
            print(f"[mop] página {page} vacía — deteniendo")
            break
        new = 0
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)
                new += 1
        print(f"[mop] página {page}: {new} proyectos nuevos (total: {len(all_items)})")
        if len(all_items) >= limit:
            break

    print(f"[mop] total: {len(all_items)} proyectos")
    return all_items[:limit]
