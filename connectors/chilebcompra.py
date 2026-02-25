"""
connectors/chilebcompra.py
Scraper de ChileCompra usando la API REST pública (sin ticket para búsqueda)
y scraping de detalle para extraer mandante y región real.
"""

import re
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.mercadopublico.cl"
DETAIL_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx"
SEARCH_URL = "https://buscador.mercadopublico.cl/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REGIONES = [
    "Tarapacá", "Antofagasta", "Atacama", "Coquimbo", "Valparaíso",
    "O'Higgins", "Maule", "Biobío", "Araucanía", "Los Lagos",
    "Aysén", "Magallanes", "Metropolitana", "Los Ríos", "Arica", "Ñuble"
]

KEYWORDS_MINERIA = [
    "minera", "mina", "cobre", "litio", "molibdeno", "relave",
    "concentradora", "chancado", "perforación", "extracción",
    "codelco", "bhp", "escondida", "collahuasi", "sqm", "albemarle",
]
KEYWORDS_ENERGIA = [
    "energía", "solar", "eólica", "fotovoltaica", "subestación",
    "transmisión eléctrica", "generación eléctrica",
]
KEYWORDS_INFRA = [
    "obras civiles", "construcción", "infraestructura", "vialidad",
    "puente", "camino", "pavimentación", "alcantarillado",
]


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


def fetch_detail(url: str, session: requests.Session) -> Dict[str, Optional[str]]:
    """Entra a la página de detalle y extrae mandante y región."""
    result = {"mandante": None, "region": None}
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar "Razón social:" → mandante
        for label in soup.find_all(string=re.compile(r"Razón social", re.I)):
            parent = label.parent
            # El valor está en el siguiente td o span
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

        # Fallback — buscar región en todo el texto
        if not result["region"]:
            full_text = soup.get_text()
            result["region"] = parse_region(full_text)

    except Exception as e:
        pass  # Silencioso — el detalle es opcional

    return result


def search_keyword(keyword: str, session: requests.Session) -> List[Dict]:
    """Busca en el buscador público de mercadopublico.cl."""
    items = []
    try:
        # Intentar con el buscador Solr de mercadopublico
        params = {
            "q": keyword,
            "rows": 50,
            "tipoBusqueda": "1",  # Licitaciones
        }
        r = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Extraer resultados del buscador
            for result in soup.select(".resultado, .search-result, article, .item-licitacion"):
                a = result.find("a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                if len(title) < 10:
                    continue
                href = a.get("href", "")
                url = BASE_URL + href if href.startswith("/") else href
                items.append({"title": title, "url": url})

        # Si el buscador no funciona, usar ListSearch directamente
        if not items:
            list_url = f"{BASE_URL}/Procurement/Modules/RFB/ListSearch.aspx"
            params2 = {"hddSearch": keyword, "ddlRegion": "0"}
            r2 = session.get(list_url, params=params2, headers=HEADERS, timeout=20)
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, "html.parser")
                for row in soup2.select("table tr"):
                    cells = row.find_all("td")
                    if not cells:
                        continue
                    a = row.find("a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    if len(title) < 10:
                        continue
                    href = a.get("href", "")
                    url = BASE_URL + href if href.startswith("/") else href
                    organismo = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    items.append({"title": title, "url": url, "organismo": organismo})

    except Exception as e:
        print(f"[chilebcompra] Error buscando '{keyword}': {e}")

    return items


def fetch_chilebcompra(limit: int = 150) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    seen_urls = set()

    search_terms = [
        "minera cobre", "litio", "codelco licitación",
        "obras civiles mina", "energía solar", "mantención industrial minería",
    ]

    for kw in search_terms:
        print(f"[chilebcompra] buscando: {kw}")
        rows = search_keyword(kw, session)
        print(f"[chilebcompra] '{kw}': {len(rows)} resultados")

        for row in rows:
            url = row.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = row.get("title", "")
            organismo_list = row.get("organismo", "")
            industry = classify_industry(title, organismo_list)

            # Entrar al detalle para mandante y región real
            detail = fetch_detail(url, session)
            mandante = detail["mandante"] or organismo_list or None
            region = detail["region"] or parse_region(organismo_list + " " + title)

            score = score_item(title, industry)

            all_items.append({
                "source": "Chile Compra",
                "title": title[:400],
                "url": url,
                "company": mandante,
                "contractor": None,
                "industry": industry,
                "region": region,
                "phase": "Licitación",
                "score": score,
                "entry": f"Mandante: {mandante} | Región: {region}" if mandante else None,
                "raw": {
                    "organismo": mandante,
                    "region": region,
                    "keyword": kw,
                    "tipo": "chilebcompra_web"
                }
            })
            time.sleep(0.5)  # Respetar el servidor

        time.sleep(1)
        if len(all_items) >= limit:
            break

    print(f"[chilebcompra] {len(all_items)} licitaciones encontradas")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_chilebcompra(limit=20)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:55]} | {i['company']} | {i['region']}")
