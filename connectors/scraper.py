# connectors/scraper.py
# Scraper directo para sitios sin RSS funcional
import requests
import hashlib
from typing import Any, Dict, List, Optional
try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
}

SITES = [
    {
        "name": "BioBioChile",
        "url": "https://www.biobiochile.cl/lista/categorias/economia",
        "article_selector": "article.news-item, .article-item, article",
        "title_selector": "h2, h3, .title",
        "link_selector": "a",
        "industry": None,
    },
    {
        "name": "Emol",
        "url": "https://www.emol.com/noticias/Economia/",
        "article_selector": "article, .EmolNews-Item, div.col-sm-6",
        "title_selector": "h3, h2, .EmolNews-title",
        "link_selector": "a",
        "industry": None,
    },
    {
        "name": "Cooperativa",
        "url": "https://www.cooperativa.cl/noticias/economia/",
        "article_selector": "article, .news-item, li.item",
        "title_selector": "h2, h3, .title",
        "link_selector": "a",
        "industry": None,
    },
    {
        "name": "CChC",
        "url": "https://www.cchc.cl/noticias/",
        "article_selector": "article, .news-card, .entry",
        "title_selector": "h2, h3, .entry-title",
        "link_selector": "a",
        "industry": "Infraestructura",
    },
]

INDUSTRIES = {
    "minería": "Minería", "mina ": "Minería", "cobre": "Minería",
    "litio": "Minería", "molibdeno": "Minería", "codelco": "Minería",
    "solar": "Energía", "eólica": "Energía", "subestación": "Energía",
    "transmisión": "Energía", "fotovoltai": "Energía", "renovable": "Energía",
    "carretera": "Infraestructura", "puente": "Infraestructura",
    "vialidad": "Infraestructura", "construcción": "Infraestructura",
    "petróleo": "Oil & Gas", "gas natural": "Oil & Gas", "gasoducto": "Oil & Gas",
    "inversión": "Infraestructura", "proyecto": "Infraestructura",
    "infraestructura": "Infraestructura",
}


def classify(text: str) -> Optional[str]:
    t = text.lower()
    for kw, ind in INDUSTRIES.items():
        if kw in t:
            return ind
    return None


def score_noticia(industry: Optional[str], title: str) -> int:
    base = {"Minería": 52, "Oil & Gas": 50, "Energía": 47, "Infraestructura": 42}.get(industry or "", 25)
    t = title.lower()
    kw = 0
    if any(k in t for k in ["inversión", "proyecto", "millones", "usd", "construcción", "planta"]): kw = 10
    return max(0, min(100, base + kw))


def scrape_site(site: Dict) -> List[Dict[str, Any]]:
    if not BS4_OK:
        print(f"[scraper] bs4 not installed, skipping {site['name']}")
        return []
    out = []
    try:
        r = requests.get(site["url"], timeout=20, headers=HEADERS, verify=False)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Try multiple article selectors
        articles = []
        for selector in site["article_selector"].split(", "):
            articles = soup.select(selector)
            if articles:
                break

        if not articles:
            # Fallback: get all links with substantial text
            articles = soup.find_all("a", href=True)

        seen_titles = set()
        for article in articles[:30]:
            # Get title
            title = ""
            for sel in site["title_selector"].split(", "):
                el = article.select_one(sel) if hasattr(article, 'select_one') else None
                if el and el.get_text(strip=True):
                    title = el.get_text(strip=True)
                    break
            if not title:
                title = article.get_text(strip=True)[:150]
            title = title.strip()
            if not title or len(title) < 15 or title in seen_titles:
                continue
            seen_titles.add(title)

            # Get link
            link = ""
            if hasattr(article, 'get') and article.get("href"):
                link = article["href"]
            else:
                a = article.find("a") if hasattr(article, 'find') else None
                if a:
                    link = a.get("href", "")
            if link and not link.startswith("http"):
                base_url = "/".join(site["url"].split("/")[:3])
                link = base_url + ("" if link.startswith("/") else "/") + link

            industry = site.get("industry") or classify(title)
            if not industry:
                continue

            url = link or f"scrape://{hashlib.md5((site['name']+title).encode()).hexdigest()}"
            out.append({
                "source": site["name"],
                "title": title[:500],
                "url": url,
                "company": None,
                "contractor": None,
                "industry": industry,
                "region": None,
                "phase": "Noticia",
                "score": score_noticia(industry, title),
                "entry": None,
                "raw": {"title": title, "source_url": site["url"]},
            })

        print(f"[scraper] {site['name']}: {len(out)} artículos")
    except Exception as e:
        print(f"[scraper] error {site['name']}: {e}")
    return out


def fetch_scraper(limit: int = 200) -> List[Dict[str, Any]]:
    import urllib3
    urllib3.disable_warnings()
    out = []
    for site in SITES:
        items = scrape_site(site)
        out.extend(items)
        if len(out) >= limit:
            break
    print(f"[scraper] total: {len(out)} items")
    return out[:limit]
