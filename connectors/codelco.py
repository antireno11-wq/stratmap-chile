"""
connectors/codelco.py
Scraper de licitaciones públicas de Codelco.
Fuente: https://www.codelco.com/licitaciones-en-proceso
No requiere autenticación.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")
BASE_URL = "https://www.codelco.com"
URL = "https://www.codelco.com/licitaciones-en-proceso"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
}

# Mapeo división → región
DIVISION_REGION = {
    "andina":                    "Valparaíso",
    "chuquicamata":              "Antofagasta",
    "el teniente":               "O'Higgins",
    "gabriela mistral":          "Antofagasta",
    "ministro hales":            "Antofagasta",
    "radomiro tomic":            "Antofagasta",
    "salvador":                  "Atacama",
    "ventanas":                  "Valparaíso",
    "casa matriz":               "Metropolitana",
    "hospital del cobre":        "Antofagasta",
    "multidivisional":           None,
    "vicepresidencia de proyectos": None,
}

SCORE_KEYWORDS = {
    "construcción": 8, "montaje": 8, "obras": 6,
    "servicio": 5, "mantención": 7, "mantenimiento": 7,
    "operación": 5, "suministro": 5, "reparación": 6,
    "ingeniería": 7, "epcm": 10, "epc": 9,
    "concentradora": 9, "planta": 6, "mina": 7,
    "eléctric": 6, "instrumentación": 6, "automatización": 7,
}


def parse_date(text: str) -> Optional[str]:
    """Parsea fechas DD/MM/YYYY."""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=TZ)
            return dt.isoformat()
        except ValueError:
            pass
    return None


def score_licitacion(title: str, tipo: str) -> int:
    base = 70  # Codelco es fuente premium
    t = title.lower()
    for kw, pts in SCORE_KEYWORDS.items():
        if kw in t:
            base += pts
    if tipo.lower() == "servicios":
        base += 5  # Servicios > bienes para proveedores
    return min(base, 95)


def fetch_codelco(limit: int = 200) -> List[Dict[str, Any]]:
    items = []
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar la tabla de licitaciones
        table = soup.find("table")
        if not table:
            print("[codelco] No se encontró tabla de licitaciones")
            return []

        rows = table.find_all("tr")[1:]  # Saltar header
        print(f"[codelco] {len(rows)} licitaciones encontradas")

        for row in rows[:limit]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            try:
                # Fecha publicación
                fecha_pub = cells[0].get_text(strip=True)
                published_at = parse_date(fecha_pub)

                # Tipo (Servicios/Bienes)
                tipo = cells[1].get_text(strip=True)

                # Título — viene con link al PDF de bases
                title_cell = cells[2]
                title_link = title_cell.find("a")
                title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
                pdf_href = title_link.get("href", "") if title_link else ""
                pdf_url = BASE_URL + pdf_href if pdf_href.startswith("/") else pdf_href

                if not title or len(title) < 5:
                    continue

                # Operación / División
                operacion = cells[3].get_text(strip=True)
                region = DIVISION_REGION.get(operacion.lower())

                # Fecha entrega (en texto libre)
                fecha_entrega_txt = cells[6].get_text(strip=True) if len(cells) > 6 else ""

                score = score_licitacion(title, tipo)

                # URL — preferir PDF de bases, sino la página principal
                url = pdf_url if pdf_url else URL

                entry_parts = []
                if operacion:
                    entry_parts.append(f"División: {operacion}")
                if tipo:
                    entry_parts.append(f"Tipo: {tipo}")
                if fecha_entrega_txt:
                    entry_parts.append(f"Entrega: {fecha_entrega_txt[:100]}")

                items.append({
                    "source": "Codelco",
                    "title": title[:400],
                    "url": url,
                    "company": "Codelco",
                    "contractor": None,
                    "industry": "Minería",
                    "region": region,
                    "phase": "Licitación",
                    "score": score,
                    "entry": " | ".join(entry_parts) if entry_parts else None,
                    "published_at": published_at,
                    "raw": {
                        "operacion": operacion,
                        "tipo": tipo,
                        "fecha_pub": fecha_pub,
                        "fecha_entrega": fecha_entrega_txt[:200],
                        "pdf_url": pdf_url,
                        "tipo_fuente": "codelco_licitaciones"
                    }
                })

            except Exception as e:
                continue

    except Exception as e:
        print(f"[codelco] Error: {e}")

    print(f"[codelco] {len(items)} licitaciones procesadas")
    return items


if __name__ == "__main__":
    items = fetch_codelco()
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i['company']} | {i['region']}")
