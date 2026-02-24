"""
connectors/lithium_chile.py
Scraper de noticias de Lithium Chile Inc.
Estructura: tarjeta con fecha arriba y título/link abajo.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://lithiumchile.ca"
NEWS_URLS = [
    "https://lithiumchile.ca/all-news/",
    "https://lithiumchile.ca/news-2026/",
    "https://lithiumchile.ca/news-2025/",
]
HEADERS = {"User-Agent": "StratmapBot/1.0 (+https://stratmap.cl)"}

DATE_PATTERN = re.compile(
    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+\d{1,2},?\s+\d{4}',
    re.IGNORECASE
)

TRANSLATIONS = {
    "announces": "anuncia", "announce": "anuncia",
    "provides update": "entrega actualización",
    "provides clarification": "entrega aclaración",
    "update on": "actualización sobre",
    "closing of": "cierre de",
    "awarded": "adjudicó",
    "secures": "asegura", "securing": "asegurando",
    "exclusive rights": "derechos exclusivos",
    "lithium development": "desarrollo de litio",
    "sale of": "venta de",
    "acquisition": "adquisición",
    "transaction": "transacción",
    "definitive agreement": "acuerdo definitivo",
    "formal agreement": "acuerdo formal",
    "agreement": "acuerdo",
    "executes": "firma",
    "offering": "oferta pública",
    "deposit": "depósito",
    "receives": "recibe",
    "directors and officers": "directores y ejecutivos",
    "exercise options": "ejercen opciones",
    "pre-awarded": "pre-adjudicado",
    "concession": "concesión",
    "adjacent to": "adyacente a",
    "project": "proyecto",
    "chile": "Chile",
    "argentina": "Argentina",
    "million": "millones",
    "billion": "miles de millones",
    "special meeting": "junta especial",
    "shareholders": "accionistas",
    "exploration": "exploración",
    "drilling": "perforación",
    "results": "resultados",
    "completes": "completa",
    "files": "presenta",
    "reports": "reporta",
    "confirms": "confirma",
    "toward": "hacia",
    "timing of": "cronograma de",
    "approve": "aprobar",
    "its argentine": "su proyecto argentino",
    "life offering": "oferta pública",
}


def translate_title(title: str) -> str:
    result = title
    for en, es in TRANSLATIONS.items():
        result = re.sub(r'\b' + re.escape(en) + r'\b', es, result, flags=re.IGNORECASE)
    return result[0].upper() + result[1:] if result else title


def parse_date(date_str: str) -> Optional[str]:
    for fmt in ["%B %d, %Y", "%B %d %Y"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            continue
    return None


def score_item(title: str) -> int:
    text = title.lower()
    score = 50
    if any(kw in text for kw in ["awarded", "adjudicó", "salar", "concesión"]):
        score += 20
    if any(kw in text for kw in ["sale", "venta", "agreement", "acuerdo", "transaction"]):
        score += 15
    if any(kw in text for kw in ["million", "millones", "offering"]):
        score += 10
    if any(kw in text for kw in ["chile", "coipasa", "llamara", "turi", "atacama"]):
        score += 10
    return min(score, 88)


def fetch_page(url: str) -> List[Dict[str, Any]]:
    items = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        content = soup.find("main") or soup.find("div", class_=re.compile(r"content|entry|post", re.I)) or soup

        # Cada noticia es una tarjeta/div que contiene fecha + título+link
        # Buscamos todos los contenedores que tengan fecha Y link dentro
        # Estrategia: encontrar todos los links de noticias y buscar fecha en su tarjeta padre
        for a_tag in content.find_all("a", href=True):
            title_en = a_tag.get_text(strip=True)
            if len(title_en) < 15:
                continue

            href = a_tag["href"]
            if not ("lithiumchile.ca" in href or href.startswith("/") or href.endswith(".pdf")):
                continue
            if href in ["/", BASE_URL + "/"]:
                continue

            url_final = href if href.startswith("http") else BASE_URL + href

            # Buscar fecha: subir en el árbol hasta encontrar un contenedor
            # que tenga texto con fecha (la fecha está ANTES del link en la tarjeta)
            date_iso = None
            node = a_tag.parent
            for _ in range(5):  # subir hasta 5 niveles
                if node is None:
                    break
                # Buscar en todos los elementos hijo de este contenedor
                full_text = node.get_text(" ", strip=True)
                m = DATE_PATTERN.search(full_text)
                if m:
                    date_iso = parse_date(m.group(0))
                    if date_iso:
                        break
                node = node.parent

            # Si aún no hay fecha, buscar en elemento anterior sibling
            if not date_iso:
                prev = a_tag.find_previous(string=DATE_PATTERN)
                if prev:
                    m = DATE_PATTERN.search(str(prev))
                    if m:
                        date_iso = parse_date(m.group(0))

            title_es = translate_title(title_en)
            display_title = title_es if title_es.lower() != title_en.lower() else title_en

            items.append({
                "source": "Lithium Chile",
                "title": display_title[:400],
                "url": url_final,
                "company": "Lithium Chile Inc.",
                "industry": "Minería",
                "region": "Antofagasta",
                "phase": "Noticia",
                "score": score_item(title_en),
                "entry": title_en[:300],
                "published_at": date_iso,
                "raw": {
                    "title_original": title_en,
                    "title_es": title_es,
                    "published_at": date_iso,
                    "source_url": url,
                    "tipo": "noticia_lithium_chile"
                }
            })

    except Exception as e:
        print(f"[lithium_chile] Error fetching {url}: {e}")

    return items


def fetch_lithium_chile(limit: int = 100) -> List[Dict[str, Any]]:
    items = []
    for url in NEWS_URLS:
        items.extend(fetch_page(url))

    # Deduplicar por URL
    seen = set()
    unique = []
    for item in items:
        if item["url"] not in seen and len(item["title"]) > 15:
            seen.add(item["url"])
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    print(f"[lithium_chile] {len(unique)} items")
    return unique[:limit]


if __name__ == "__main__":
    items = fetch_lithium_chile()
    for i in items[:8]:
        d = (i.get("published_at") or "sin fecha")[:10]
        print(f"  [{i['score']}] {d} | {i['title'][:70]}")
