# connectors/mop.py
import requests
import xml.etree.ElementTree as ET
import hashlib
from typing import Any, Dict, List, Optional

MOP_RSS_FEEDS = [
    {"url": "https://www.mop.cl/Prensa/Lists/Noticias/rss.aspx", "source": "MOP Noticias"},
    {"url": "https://www.concesiones.cl/noticias/Paginas/RSS.aspx", "source": "MOP Concesiones"},
]

KEYWORDS_INFRA = ["carretera", "ruta", "puente", "camino", "autopista", "vialidad", "túnel", "embalse", "aeropuerto", "puerto", "concesión", "licitación", "construcción", "obra", "contrato", "adjudicación"]
KEYWORDS_MINERIA = ["miner", "cobre", "litio"]
KEYWORDS_ENERGIA = ["energía", "solar", "eólica", "transmisión"]


def classify(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in KEYWORDS_INFRA): return "Infraestructura"
    if any(k in t for k in KEYWORDS_MINERIA): return "Minería"
    if any(k in t for k in KEYWORDS_ENERGIA): return "Energía"
    return None


def score_mop(title: str, industry: str) -> int:
    base = 45 if industry == "Infraestructura" else 40
    t = title.lower()
    kw = 0
    if any(k in t for k in ["licitación", "adjudicación", "contrato", "llamado"]): kw += 15
    if any(k in t for k in ["millones", "usd", "uf", "mmus"]): kw += 10
    if any(k in t for k in ["inicio obras", "apertura", "nuevo proyecto"]): kw += 8
    return max(0, min(100, base + kw))


def fetch_mop_rss(feed: Dict) -> List[Dict[str, Any]]:
    out = []
    try:
        r = requests.get(feed["url"], timeout=15, headers={"User-Agent": "StratmapWorker/0.2"}, verify=False)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        for item in items:
            title = (item.findtext("title") or "").strip()
            if not title: continue
            description = (item.findtext("description") or "").strip()
            industry = classify(title + " " + description) or "Infraestructura"
            url = (item.findtext("link") or f"rss://{hashlib.md5((feed['url']+title).encode()).hexdigest()}").strip()
            out.append({
                "source": feed["source"],
                "title": title[:500],
                "url": url,
                "company": "MOP",
                "contractor": None,
                "industry": industry,
                "region": None,
                "phase": "Noticia",
                "score": score_mop(title, industry),
                "entry": None,
                "raw": {"title": title, "description": description[:500]},
            })
    except Exception as e:
        print(f"[mop] error {feed['source']}: {e}")
    return out


def fetch_mop(limit: int = 200) -> List[Dict[str, Any]]:
    import urllib3
    urllib3.disable_warnings()
    out = []
    for feed in MOP_RSS_FEEDS:
        items = fetch_mop_rss(feed)
        print(f"[mop] {feed['source']}: {len(items)} items")
        out.extend(items)
    print(f"[mop] total: {len(out)} items")
    return out[:limit]
