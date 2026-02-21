# connectors/rss.py
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import requests
import hashlib

TZ = ZoneInfo("America/Santiago")

RSS_FEEDS = [
    {
        "url": "https://www.cochilco.cl/rss/noticias.xml",
        "source": "COCHILCO",
        "industry": "Minería",
    },
    {
        "url": "https://minmineria.gob.cl/feed/",
        "source": "Ministerio de Minería",
        "industry": "Minería",
    },
    {
        "url": "https://www.mop.cl/Prensa/Paginas/RSS.aspx",
        "source": "MOP",
        "industry": "Infraestructura",
    },
    {
        "url": "https://www.df.cl/rss/noticias.xml",
        "source": "Diario Financiero",
        "industry": None,  # se clasifica automáticamente
    },
    {
        "url": "https://www.elmercurio.com/rss/xml_portadas.aspx?idp=18",
        "source": "El Mercurio - Negocios",
        "industry": None,
    },
]

KEYWORDS_MINERIA = ["miner", "cobre", "litio", "molibdeno", "relave", "faena", "codelco", "bhp", "antofagasta minerals", "teck", "yacimiento", "salar"]
KEYWORDS_INFRA = ["infraestructura", "carretera", "puente", "camino", "ruta", "mop", "concesión vial", "obras públicas"]
KEYWORDS_ENERGIA = ["energía", "fotovoltai", "eólica", "subestación", "transmisión", "solar", "renovable"]
KEYWORDS_OIL = ["petróleo", "gas natural", "enap", "combustible", "hidrocarburo", "gasoducto"]


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
    if any(k in t for k in ["millones", "mdd", "usd", "millardos"]):
        kw += 8

    return max(0, min(100, base + kw))


def make_url_hash(url: str, title: str) -> str:
    """Genera URL única para artículos RSS sin URL propia"""
    return f"rss://{hashlib.md5((url + title).encode()).hexdigest()}"


def fetch_feed(feed: Dict[str, Any], days_back: int = 7) -> List[Dict[str, Any]]:
    cutoff = datetime.now(TZ) - timedelta(days=days_back)
    out = []

    try:
        r = requests.get(feed["url"], timeout=20, headers={"User-Agent": "StratmapWorker/0.2"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[rss] error {feed['source']}: {e}")
        return []

    # Soporte para RSS y Atom
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
            make_url_hash(feed["url"], title)
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
            "raw": {"title": title, "description": description[:1000], "feed": feed["url"]},
        })

    return out


def fetch_rss(days_back: int = 7, limit: int = 200) -> List[Dict[str, Any]]:
    out = []
    for feed in RSS_FEEDS:
        items = fetch_feed(feed, days_back=days_back)
        print(f"[rss] {feed['source']}: {len(items)} artículos relevantes")
        out.extend(items)
        if len(out) >= limit:
            break
    return out[:limit]
