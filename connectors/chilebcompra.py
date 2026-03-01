"""
connectors/chilebcompra.py
API oficial de ChileCompra con ticket.
Obtiene licitaciones por keyword y extrae mandante + región del detalle.
"""

import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

API_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
DETAIL_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx"
BASE_URL = "https://www.mercadopublico.cl"
DEFAULT_TICKET = "3510D840-A3C2-49B9-93A6-A4ADAEBE5956"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "es-CL,es;q=0.9",
}

REGIONES = [
    "Tarapacá", "Antofagasta", "Atacama", "Coquimbo", "Valparaíso",
    "O'Higgins", "Maule", "Biobío", "Araucanía", "Los Lagos",
    "Aysén", "Magallanes", "Metropolitana", "Los Ríos", "Arica", "Ñuble"
]

KEYWORDS = [
    "minera", "cobre", "litio", "codelco", "mina",
    "obras civiles", "energía solar", "mantención industrial",
]

KEYWORDS_MINERIA = ["minera", "mina", "cobre", "litio", "molibdeno", "relave",
                    "codelco", "bhp", "escondida", "collahuasi", "sqm", "albemarle"]
KEYWORDS_ENERGIA = ["energía", "solar", "eólica", "fotovoltaica", "subestación"]


def parse_region(text: str) -> Optional[str]:
    t = text.lower()
    for r in REGIONES:
        if r.lower() in t:
            return r
    return None


def classify_industry(title: str, organismo: str = "") -> str:
    text = f"{title} {organismo}".lower()
    if any(k in text for k in KEYWORDS_MINERIA):
        return "Minería"
    if any(k in text for k in KEYWORDS_ENERGIA):
        return "Energía"
    return "Infraestructura"


def score_item(title: str, industry: str) -> int:
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


def fetch_detail(code: str, session: requests.Session) -> Dict[str, Optional[str]]:
    """Scraping de página de detalle para extraer mandante y región."""
    result = {"mandante": None, "region": None}
    try:
        url = f"{DETAIL_URL}?idlicitacion={code}"
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar "Razón social:" → mandante
        for label in soup.find_all(string=re.compile(r"Razón social", re.I)):
            parent = label.parent
            next_el = parent.find_next_sibling() or parent.parent.find_next_sibling()
            if next_el:
                val = next_el.get_text(strip=True)
                if val and len(val) > 2:
                    result["mandante"] = val
                    break

        # Buscar "Región en que se genera la licitación:"
        for label in soup.find_all(string=re.compile(r"Región en que se genera", re.I)):
            parent = label.parent
            next_el = parent.find_next_sibling() or parent.parent.find_next_sibling()
            if next_el:
                val = next_el.get_text(strip=True)
                region = parse_region(val)
                if region:
                    result["region"] = region
                    break

        if not result["region"]:
            result["region"] = parse_region(soup.get_text())

    except Exception:
        pass

    return result


def fetch_by_date(date_str: str, ticket: str, session: requests.Session) -> List[Dict]:
    """fecha en formato DDMMYYYY"""
    try:
        url = f"{API_URL}?fecha={date_str}&ticket={ticket}"
        r = session.get(url, timeout=15, headers={"User-Agent": "StratmapWorker/1.0"})
        r.raise_for_status()
        data = r.json()
        return data.get("Listado", []) or []
    except Exception as e:
        print(f"[chilebcompra] error día {date_str}: {e}")
        return []


def fetch_chilebcompra(limit: int = 200) -> List[Dict[str, Any]]:
    ticket = os.getenv("CHILEBCOMPRA_TICKET", DEFAULT_TICKET)
    session = requests.Session()
    from datetime import datetime, timedelta
    seen_codes = set()
    all_items = []

    # Buscar últimos 7 días
    for i in range(7):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime("%d%m%Y")
        print(f"[chilebcompra] buscando día: {date_str}")
        licitaciones = fetch_by_date(date_str, ticket, session)
        print(f"[chilebcompra] {date_str}: {len(licitaciones)} resultados")
        if licitaciones and i == 0:
            # DEBUG — mostrar estructura del primer item
            first = licitaciones[0]
            print(f"[chilebcompra] DEBUG keys: {list(first.keys())}")
            for k, v in first.items():
                print(f"[chilebcompra] DEBUG {k}: {repr(str(v))[:80]}")

        consecutive_errors = 0
        for lic in licitaciones:
            code = lic.get("CodigoExterno", "") or lic.get("Codigo", "")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)

            title = lic.get("Nombre", "") or lic.get("NombreLicitacion", "")
            if not title or len(title) < 5:
                continue

            organismo = lic.get("NombreOrganismo", "") or lic.get("Organismo", {}).get("Nombre", "")
            region_api = lic.get("Region", "") or lic.get("NombreRegion", "")
            estado = lic.get("Estado", "") or lic.get("CodigoEstado", "")

            # Solo licitaciones activas
            if estado and any(x in str(estado).lower() for x in ["adjudicada", "desierta", "revocada", "suspendida"]):
                continue

            # Filtrar solo minería y sectores industriales relevantes
            industry = classify_industry(title, organismo)
            if industry not in ("Minería", "Energía"):
                # Incluir infraestructura solo si tiene keywords mineros
                if not any(k in title.lower() for k in KEYWORDS_MINERIA):
                    continue

            region = parse_region(region_api) or parse_region(organismo) or parse_region(title)

            # Entrar al detalle si falta mandante o región
            if not organismo or not region:
                detail = fetch_detail(code, session)
                organismo = organismo or detail["mandante"]
                region = region or detail["region"]
                time.sleep(0.3)

            detail_page_url = f"{DETAIL_URL}?idlicitacion={code}"
            score = score_item(title, industry)

            all_items.append({
                "source": "Chile Compra",
                "title": title[:400],
                "url": detail_page_url,
                "company": organismo or None,
                "contractor": None,
                "industry": industry,
                "region": region,
                "phase": "Licitación",
                "score": score,
                "entry": f"Mandante: {organismo} | Región: {region} | Código: {code}" if organismo else code,
                "raw": {
                    "codigo": code,
                    "organismo": organismo,
                    "region": region,
                    "estado": estado,
                    "keyword": date_str,
                    "tipo": "chilebcompra_api"
                }
            })

        time.sleep(0.5)
        if len(all_items) >= limit:
            break
        time.sleep(1)

    print(f"[chilebcompra] {len(all_items)} licitaciones encontradas")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_chilebcompra(limit=20)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:55]} | {i['company']} | {i['region']}")
