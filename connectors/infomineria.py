"""
connectors/infomineria.py
Scraper de noticias de https://infomineria.cl/noticias/
Portal de noticias mineras chilenas.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")
BASE_URL = "https://infomineria.cl"
NEWS_URL = "https://infomineria.cl/noticias/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
}

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

MINING_KEYWORDS = [
    "mina", "minera", "minería", "cobre", "litio", "molibdeno", "oro", "plata",
    "codelco", "bhp", "escondida", "collahuasi", "sqm", "albemarle", "antofagasta",
    "relave", "concentradora", "faena", "extracción", "yacimiento", "exploración",
    "sernageomin", "cochilco", "teck", "kinross", "barrick",
]

SCORE_KEYWORDS = {
    "codelco": 15, "escondida": 12, "collahuasi": 12, "sqm": 10, "albemarle": 10,
    "litio": 10, "cobre": 8, "inversión": 8, "proyecto": 6, "licitación": 8,
    "contrato": 7, "construcción": 6, "ampliación": 7,
}


def parse_date(text: str) -> Optional[str]:
    """Parsea fechas en español: '15 de enero de 2026', 'enero 15, 2026', etc."""
    text = text.strip().lower()

    # Formato: "15 de enero de 2026"
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', text)
    if m:
        day, month_str, year = m.groups()
        month = MONTHS_ES.get(month_str)
        if month:
            try:
                dt = datetime(int(year), month, int(day), tzinfo=TZ)
                return dt.isoformat()
            except ValueError:
                pass

    # Formato: "enero 15, 2026" o "15 enero 2026"
    m = re.search(r'(\w+)\s+(\d{1,2})[,\s]+(\d{4})', text)
    if m:
        month_str, day, year = m.groups()
        month = MONTHS_ES.get(month_str)
        if month:
            try:
                dt = datetime(int(year), month, int(day), tzinfo=TZ)
                return dt.isoformat()
            except ValueError:
                pass

    # Formato ISO: "2026-01-15"
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=TZ)
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


def is_mining_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    return any(k in text for k in MINING_KEYWORDS)


def fetch_page(url: str, session: requests.Session, page: int = 1) -> List[Dict]:
    """Scrape una página de noticias."""
    items = []
    try:
        page_url = f"{url}page/{page}/" if page > 1 else url
        r = session.get(page_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # DEBUG en primera ejecución
        if page == 1:
            # Buscar artículos con múltiples selectores típicos de WordPress
            all_articles = soup.select("article, .post, .entry-item, .news-item, [class*='post-'], [class*='article-']")
            print(f"[infomineria] DEBUG: {len(all_articles)} artículos encontrados")
            if all_articles:
                print(f"[infomineria] DEBUG primer artículo: {str(all_articles[0])[:300]}")
            else:
                # Ver estructura general
                divs = soup.find_all("div", class_=True)[:5]
                for d in divs:
                    print(f"[infomineria] DEBUG div class={d.get('class')}: {d.get_text(strip=True)[:80]}")

        # Estrategia 1: artículos WordPress estándar
        articles = soup.select("article")
        if not articles:
            # Estrategia 2: divs con clases de post
            articles = soup.select(".post, .entry, .news-item, [class*='noticia']")
        if not articles:
            # Estrategia 3: buscar links con fechas cerca
            articles = soup.select("h2 a, h3 a, .entry-title a, .post-title a")

        for art in articles:
            try:
                # Si es un link directo (estrategia 3)
                if art.name == "a":
                    title = art.get_text(strip=True)
                    href = art.get("href", "")
                    url_item = href if href.startswith("http") else BASE_URL + href
                    date_iso = None
                    summary = ""
                else:
                    # Buscar título y link
                    title_el = (
                        art.select_one("h2 a, h3 a, h1 a, .entry-title a, .post-title a") or
                        art.select_one("h2, h3, h1, .entry-title, .post-title")
                    )
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    href = title_el.get("href") or (title_el.find("a") and title_el.find("a").get("href")) or ""
                    url_item = href if href.startswith("http") else BASE_URL + href

                    # Buscar fecha
                    date_el = art.select_one("time, .date, .entry-date, [class*='date'], [datetime]")
                    date_iso = None
                    if date_el:
                        date_str = date_el.get("datetime") or date_el.get_text(strip=True)
                        date_iso = parse_date(date_str)

                    # Resumen
                    summary_el = art.select_one(".entry-summary, .excerpt, p")
                    summary = summary_el.get_text(strip=True)[:200] if summary_el else ""

                if not title or len(title) < 10:
                    continue
                if not url_item or url_item == BASE_URL:
                    continue

                # Filtrar solo noticias mineras
                if not is_mining_relevant(title, summary):
                    continue

                score = score_noticia(title)
                items.append({
                    "source": "InfoMineria",
                    "title": title[:400],
                    "url": url_item,
                    "company": None,
                    "contractor": None,
                    "industry": "Minería",
                    "region": None,
                    "phase": "Noticia",
                    "score": score,
                    "entry": summary[:300] if summary else None,
                    "published_at": date_iso,
                    "raw": {
                        "tipo": "noticia_infomineria",
                        "summary": summary,
                    }
                })

            except Exception as e:
                continue

    except Exception as e:
        print(f"[infomineria] Error página {page}: {e}")

    return items


def fetch_infomineria(limit: int = 100) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    seen_urls = set()

    for page in range(1, 6):  # Hasta 5 páginas
        print(f"[infomineria] Scrapeando página {page}...")
        items = fetch_page(NEWS_URL, session, page)
        print(f"[infomineria] Página {page}: {len(items)} noticias mineras")

        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)

        if len(items) == 0:
            break  # No más páginas
        if len(all_items) >= limit:
            break

    print(f"[infomineria] Total: {len(all_items)} noticias")
    return all_items[:limit]


if __name__ == "__main__":
    items = fetch_infomineria(limit=20)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i.get('published_at', 'sin fecha')}")
