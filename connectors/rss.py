# connectors/rss.py
import xml.etree.ElementTree as ET
import hashlib
import requests
from typing import Any, Dict, List, Optional

RSS_FEEDS = [
    {
        "url": "https://www.biobiochile.cl/lista/categorias/economia/feed",
        "source": "BioBioChile - Economía",
        "industry": None,
    },
    {
        "url": "https://www.emol.com/rss/Noticias_del_Dia.xml",
        "source": "Emol",
        "industry": None,
    },
    {
        "url": "https://radio.uchile.cl/feed/",
        "source": "Radio Universidad de Chile",
        "industry": None,
    },
    {
        "url": "https://www.latercera.com/feed/",
        "source": "La Tercera",
        "industry": None,
    },
]

KEYWORDS_MINERIA = ["miner", "cobre", "litio", "molibdeno", "relave", "faena", "codelco", "bhp", "teck", "yacimiento", "salar", "antofagasta minerals"]
KEYWORDS_INFRA = ["infraestructura", "carretera", "puente", "ruta", "mop", "concesión vial", "obras públicas", "autopista"]
KEYWORDS_ENERGIA = ["energía", "fotovoltai", "eólica", "subestación", "transmisión", "solar", "renovable", "generación eléctrica"]
KEYWORDS_OIL = ["petróleo", "gas natural", "enap", "hidrocarburo", "gasoducto", "refinería"]


def classify_industry(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in KEYWORDS_MINERIA):
        return "Minería"
    if any(k in t for k in KEYWORDS_OIL):
        return "Oil & Gas"
    if any(k in t for k in KEYWORDS_ENERGIA):
        return "Energía"
    if any(k in t for k in KEYWORDS_INFRA):
        return "Infraestructura"
    return None


def score_rss(industry: Optional[str], title: str) -> int:
    base = 20
    if industry == "Minería":
        base = 50
    elif industry == "Oil & Gas":
        base = 48
    elif industry == "Energía":
        base = 45
    elif industry == "Infraestructura":
        base = 40

    t = title.lower()
    kw = 0
    if any(k in t for k in ["inversión", "proyecto", "planta", "ampliación", "construcción"]):
        kw += 10
    if any(k in t for k in ["millones", "mdd", "usd"]):
        kw += 8

    return max(0, min(100, base + kw))


def fetch_feed(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    try:
        r = requests.get(
            feed["url"], timeout=20,
            headers={"User-Agent": "StratmapWorker/0.2"},
            verify=False
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[rss] error {feed['source']}: {e}")
        return []

    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items:
        title = (
            item.findtext("title") or
            item.findtext("{http://www.w3.org/2005/Atom}title") or ""
        ).strip()

        if not title:
            continue

        description = (
            item.findtext("description") or
            item.findtext("{http://www.w3.org/2005/Atom}summary") or ""
        ).strip()

        blob = title + " " + description
        industry = feed.get("industry") or classify_industry(blob)

        if not industry:
            continue

        url = (
            item.findtext("link") or
            item.findtext("{http://www.w3.org/2005/Atom}id") or
            f"rss://{hashlib.md5((feed['url'] + title).encode()).hexdigest()}"
        ).strip()

        score = score_rss(industry, title)

        out.append({
            "source": feed["source"],
            "title": title[:500],
            "url": url,
            "company": None,
            "contractor": None,
            "industry": industry,
            "region": None,
            "phase": "Noticia",
            "score": score,
            "entry": None,
            "raw": {"title": title, "description": description[:500]},
        })

    return out


def fetch_rss(days_back: int = 7, limit: int = 200) -> List[Dict[str, Any]]:
    import urllib3
    urllib3.disable_warnings()
    out = []
    for feed in RSS_FEEDS:
        items = fetch_feed(feed)
        print(f"[rss] {feed['source']}: {len(items)} artículos relevantes")
        out.extend(items)
        if len(out) >= limit:
            break
    return out[:limit]
