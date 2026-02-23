"""
connectors/lithium_chile.py
Scraper de noticias de Lithium Chile Inc. (canadiense, en inglés).
https://lithiumchile.ca/all-news/
Traduce automáticamente los títulos al español.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL   = "https://lithiumchile.ca"
NEWS_URL   = "https://lithiumchile.ca/all-news/"
NEWS_2026  = "https://lithiumchile.ca/news-2026/"
NEWS_2025  = "https://lithiumchile.ca/news-2025/"
HEADERS    = {"User-Agent": "StratmapBot/1.0 (+https://stratmap.cl)"}

# Diccionario de traducción rápida de términos comunes en titulares mineros
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
    "agreement": "acuerdo",
    "definitive agreement": "acuerdo definitivo",
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
    "salar": "salar",
    "chile": "Chile",
    "argentina": "Argentina",
    "million": "millones",
    "billion": "miles de millones",
    "upsized": "ampliada",
    "life offering": "oferta de mercado",
    "special meeting": "junta especial",
    "shareholders": "accionistas",
    "exploration": "exploración",
    "drilling": "perforación",
    "results": "resultados",
    "completes": "completa",
    "files": "presenta",
    "reports": "reporta",
    "confirms": "confirma",
}


def translate_title(title: str) -> str:
    """Traducción rápida basada en diccionario + preserva nombres propios."""
    result = title
    for en, es in TRANSLATIONS.items():
        result = re.sub(re.escape(en), es, result, flags=re.IGNORECASE)
    # Capitalizar primera letra
    return result[0].upper() + result[1:] if result else title


def parse_date(date_str: str) -> Optional[str]:
    """Parsea fechas como 'February 18, 2026' → ISO."""
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return None


def score_item(title: str) -> int:
    text = title.lower()
    score = 50  # base — empresa de litio en Chile, alta relevancia

    if any(kw in text for kw in ["awarded", "adjudicó", "salar", "ceol", "concesión"]):
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

        # Lithium Chile news page: lista de "date + link" en el contenido principal
        content = soup.find("main") or soup.find("div", class_=re.compile(r"content|entry|post", re.I)) or soup

        # Buscar párrafos o divs que contengan fecha + link
        # Patrón: "Month DD, YYYY[link text](url)"
        date_pattern = re.compile(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}',
            re.IGNORECASE
        )

        # Buscar todos los links en la página de noticias
        for a_tag in content.find_all("a", href=True):
            title_en = a_tag.get_text(strip=True)
            if len(title_en) < 15:
                continue

            href = a_tag["href"]
            # Solo PDFs o páginas de noticias
            if not (href.endswith(".pdf") or "lithiumchile.ca" in href or href.startswith("/")):
                continue

            url_final = href if href.startswith("http") else BASE_URL + href

            # Buscar fecha cerca del link
            parent = a_tag.parent or a_tag
            parent_text = parent.get_text(" ", strip=True)
            date_match = date_pattern.search(parent_text)
            date_iso = parse_date(date_match.group(0)) if date_match else None

            title_es = translate_title(title_en)

            score = score_item(title_en)
            items.append({
                "source": "Lithium Chile",
                "title": f"{title_es} [EN: {title_en[:100]}]" if title_es != title_en else title_en,
                "url": url_final,
                "company": "Lithium Chile Inc.",
                "industry": "Minería",
                "region": "Antofagasta",
                "phase": "Noticia",
                "score": score,
                "entry": f"Fuente original en inglés: {title_en}",
                "raw": {
                    "source_url": url,
                    "title_original": title_en,
                    "title_es": title_es,
                    "published_at": date_iso,
                    "tipo": "noticia_lithium_chile"
                }
            })

        return items

    except Exception as e:
        print(f"[lithium_chile] Error fetching {url}: {e}")
        return []


def fetch_lithium_chile(limit: int = 100) -> List[Dict[str, Any]]:
    items = []

    # Scrapear página principal de noticias + 2026 + 2025
    for url in [NEWS_URL, NEWS_2026, NEWS_2025]:
        items.extend(fetch_page(url))

    # Deduplicar por URL
    seen = set()
    unique = []
    for item in items:
        if item["url"] not in seen and len(item["title"]) > 15:
            seen.add(item["url"])
            unique.append(item)

    # Ordenar por score
    unique.sort(key=lambda x: x["score"], reverse=True)
    print(f"[lithium_chile] {len(unique)} items")
    return unique[:limit]


if __name__ == "__main__":
    items = fetch_lithium_chile()
    for i in items[:8]:
        print(f"  [{i['score']}] {i['title'][:80]}")
