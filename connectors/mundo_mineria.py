"""
connectors/mundo_mineria.py
Scraper de noticias de https://mundomineria.cl/category/nacional/
Portal de noticias mineras chilenas — WordPress estándar.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")
BASE_URL = "https://mundomineria.cl"
PAGES = [
    "https://mundomineria.cl/category/nacional/",
    "https://mundomineria.cl/category/empresas/",
    "https://mundomineria.cl/category/instituciones/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
}

SCORE_KEYWORDS = {
    "codelco": 12, "escondida": 10, "collahuasi": 10, "sqm": 9, "albemarle": 9,
    "antofagasta minerals": 10, "teck": 8, "kinross": 8, "barrick": 8,
    "litio": 9, "cobre": 7, "inversión": 7, "proyecto": 5,
    "licitación": 8, "contrato": 6, "construcción": 5, "ampliación": 6,
    "nueva mina": 8, "faena": 7, "concentradora": 8, "relave": 7,
}


def parse_date_from_url(url: str) -> Optional[str]:
    """Extrae fecha de URLs tipo /2026/02/25/titulo/"""
    m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=TZ)
            return dt.isoformat()
        except ValueError:
            pass
    return None


def parse_date_text(text: str) -> Optional[str]:
    """Parsea fechas como '28 febrero, 2026'"""
    MONTHS = {
        "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
        "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
    }
    m = re.search(r'(\d{1,2})\s+(\w+)[,\s]+(\d{4})', text.lower())
    if m:
        month = MONTHS.get(m.group(2))
        if month:
            try:
                dt = datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=TZ)
                return dt.isoformat()
            except ValueError:
                pass
    return None


def score_noticia(title: str) -> int:
    base = 55
    t = title.lower()
    for kw, pts in SCORE_KEYWORDS.items():
        if kw in t:
            base += pts
    return min(base, 88)


def fetch_page(url: str, session: requests.Session, cutoff: str) -> List[Dict]:
    items = []
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = soup.select("article, .post, h2.entry-title, .jeg_post")
        if not articles:
            # Fallback — buscar todos los links de noticias
            articles = soup.select("h2 a, h3 a, .entry-title a")

        for art in articles:
            try:
                # Si es link directo
                if art.name == "a":
                    title = art.get_text(strip=True)
                    href = art.get("href", "")
                else:
                    link_el = art.select_one("h2 a, h3 a, .entry-title a, a[rel='bookmark']")
                    if not link_el:
                        continue
                    title = link_el.get_text(strip=True)
                    href = link_el.get("href", "")

                if not title or len(title) < 10:
                    continue
                if not href.startswith("http"):
                    href = BASE_URL + href

                # Fecha desde URL primero, luego del DOM
                date_iso = parse_date_from_url(href)
                if not date_iso and art.name != "a":
                    date_el = art.select_one("time, .date, .entry-date, [class*='date']")
                    if date_el:
                        date_iso = parse_date_text(date_el.get_text()) or \
                                   parse_date_from_url(date_el.get("datetime",""))

                # Filtrar antiguos
                if date_iso and date_iso < cutoff:
                    return items  # Artículos ordenados por fecha — parar

                score = score_noticia(title)

                items.append({
                    "source": "Mundo Minería",
                    "title": title[:400],
                    "url": href,
                    "company": None,
                    "contractor": None,
                    "industry": "Minería",
                    "region": None,
                    "phase": "Noticia",
                    "score": score,
                    "entry": None,
                    "published_at": date_iso,
                    "raw": {"tipo": "noticia_mundo_mineria"}
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[mundo_mineria] Error {url}: {e}")

    return items


def fetch_mundo_mineria(limit: int = 100) -> List[Dict[str, Any]]:
    session = requests.Session()
    cutoff = (datetime.now(tz=TZ) - timedelta(days=90)).isoformat()
    all_items = []
    seen_urls = set()

    for base_url in PAGES:
        for page_num in range(1, 4):  # Hasta 3 páginas por categoría
            url = f"{base_url}page/{page_num}/" if page_num > 1 else base_url
            items = fetch_page(url, session, cutoff)
            print(f"[mundo_mineria] {url}: {len(items)} noticias")

            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_items.append(item)

            if len(items) == 0:
                break
            if len(all_items) >= limit:
                break

        if len(all_items) >= limit:
            break

    print(f"[mundo_mineria] Total: {len(all_items)} noticias")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_mundo_mineria(limit=20)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:70]} | {i.get('published_at','sin fecha')[:10]}")
