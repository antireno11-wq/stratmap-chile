"""
Scraper MOP — proyectos.mop.gob.cl
Scores recalibrados para no competir con proyectos mineros SEA.
"""
import time
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://proyectos.mop.gob.cl"
SEARCH_URL = f"{BASE_URL}/Default.asp"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Stratmap/1.0)",
    "Accept-Language": "es-CL,es;q=0.9",
}

REGION_MAP = {
    "I":   "Tarapacá", "II":  "Antofagasta", "III": "Atacama",
    "IV":  "Coquimbo", "V":   "Valparaíso",  "VI":  "O'Higgins",
    "VII": "Maule",    "VIII":"Biobío",        "IX":  "Araucanía",
    "X":   "Los Lagos","XI":  "Aysén",         "XII": "Magallanes",
    "XIII":"Metropolitana","XIV":"Los Ríos",    "XV": "Arica y Parinacota",
    "XVI": "Ñuble",    "RM":  "Metropolitana",
    "INTERREGIONAL": "Interregional",
}

SERVICE_MAP = {
    "Vialidad":     "Vialidad",
    "Portuarias":   "Obras Portuarias",
    "Aeropuertos":  "Aeropuertos",
    "Hidráulicas":  "Obras Hidráulicas",
    "Arquitectura": "Arquitectura",
    "Sanitarios":   "Agua Potable Rural",
}


def normalize_region(raw: str) -> str:
    raw = raw.strip().upper()
    for k, v in REGION_MAP.items():
        if raw == k or raw.startswith(k + " ") or raw.startswith(k + "-"):
            return v
    return raw.title()


def classify_service(service_raw: str) -> str:
    for k, v in SERVICE_MAP.items():
        if k.lower() in service_raw.lower():
            return v
    return service_raw.strip()


def score_project(name: str, service: str) -> int:
    """
    Score MOP recalibrado: máximo 55 para no competir con SEA/minería (que llega a 90-100).
    Proyectos de infraestructura son relevantes pero de distinta naturaleza.
    """
    name_lower = name.lower()
    score = 50  # base MOP — infraestructura relevante

    # Tipo de obra — bonus por relevancia comercial
    if any(w in name_lower for w in ["construccion", "construcción", "nuevo", "ampliacion", "ampliación"]):
        score += 8
    elif any(w in name_lower for w in ["mejoramiento", "mejoras"]):
        score += 5
    elif any(w in name_lower for w in ["conservacion", "conservación", "mantenimiento"]):
        score += 2

    # Tipo de infraestructura — mayor oportunidad comercial
    if any(w in name_lower for w in ["aeropuerto", "puerto", "terminal"]):
        score += 10
    elif any(w in name_lower for w in ["embalse", "presa", "canal"]):
        score += 8
    elif any(w in name_lower for w in ["puente", "túnel", "tunel", "viaducto"]):
        score += 6
    elif any(w in name_lower for w in ["ruta", "autopista", "carretera", "acceso"]):
        score += 4

    # Servicio premium
    if "aeropuerto" in service.lower() or "portuaria" in service.lower():
        score += 5
    elif "hidráulica" in service.lower() or "hidraulica" in service.lower():
        score += 4

    return min(score, 82)  # cap MOP


def fetch_page(page: int, session: requests.Session) -> list:
    params = {
        "buscar": "true",
        "whichpage": str(page),
        "pagesize": "20",
    }
    try:
        resp = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[mop] error página {page}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")
    projects = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        try:
            region_raw = cols[0].get_text(strip=True)
            service_raw = cols[1].get_text(strip=True)
            name_cell = cols[2]
            bip_raw = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            program_raw = cols[4].get_text(strip=True) if len(cols) > 4 else ""

            link = name_cell.find("a")
            if not link:
                continue

            name = link.get_text(strip=True)
            href = link.get("href", "")
            if not name or not href:
                continue

            region = normalize_region(region_raw)
            service = classify_service(service_raw)
            score = score_project(name, service)

            projects.append({
                "source": "MOP",
                "title": name[:500],
                "url": f"{BASE_URL}/{href}",
                "company": "MOP",
                "industry": "Minería",
                "region": region,
                "phase": "En ejecución",
                "score": score,
                "entry": bip_raw or None,
                "raw": {
                    "bip": bip_raw,
                    "region": region_raw,
                    "program": program_raw,
                    "service": service_raw,
                },
            })
        except Exception:
            continue

    return projects


def fetch_all(max_pages: int = 40, delay: float = 0.3) -> list:
    session = requests.Session()
    all_projects = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        projects = fetch_page(page, session)
        if not projects:
            print(f"[mop] página {page} vacía — deteniendo")
            break

        new = [p for p in projects if p["url"] not in seen_urls]
        if not new:
            break

        seen_urls.update(p["url"] for p in new)
        all_projects.extend(new)
        print(f"[mop] página {page}: {len(new)} proyectos nuevos (total: {len(all_projects)})")
        time.sleep(delay)

    return all_projects


# Alias para compatibilidad con sea_ingest.py
def fetch_mop(limit: int = 500, max_pages: int = 40) -> list:
    items = fetch_all(max_pages=max_pages)
    return items[:limit]


if __name__ == "__main__":
    projects = fetch_all()
    print(f"\n[mop] Total: {len(projects)} proyectos")
    if projects:
        scores = [p["score"] for p in projects]
        print(f"[mop] Score min: {min(scores)}, max: {max(scores)}, avg: {sum(scores)//len(scores)}")
