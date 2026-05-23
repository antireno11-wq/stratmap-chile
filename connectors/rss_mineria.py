# connectors/rss_mineria.py
import xml.etree.ElementTree as ET
import hashlib
import requests
from typing import Any, Dict, List, Optional

RSS_FEEDS = [
    # ── Minería ──────────────────────────────────────────────────────────────
    {"url": "https://www.portalminero.com/wp/feed/", "source": "Portal Minero", "industry": "Minería"},
    {"url": "https://www.mch.cl/feed/", "source": "Minería Chilena", "industry": "Minería"},
    {"url": "https://www.cochilco.cl/web/feed/", "source": "COCHILCO Noticias", "industry": "Minería"},
    {"url": "https://www.reporteminero.cl/feed/", "source": "Reporte Minero", "industry": "Minería"},
    {"url": "https://www.nuevamineria.com/revista/feed/", "source": "Nueva Minería y Energía", "industry": "Minería"},
    {"url": "https://www.mineriachilena.com/feed/", "source": "MCh Online", "industry": "Minería"},
    {"url": "https://www.mining.com/feed/", "source": "Mining.com", "industry": "Minería"},
    {"url": "https://www.mining-technology.com/feed/", "source": "Mining Technology", "industry": "Minería"},
    # ── Negocios / finanzas (filtro por keywords mineros downstream) ─────────
    {"url": "https://www.df.cl/noticias/site/list/port/rss.xml", "source": "Diario Financiero", "industry": None},
    {"url": "https://www.americaeconomia.com/rss.xml", "source": "AméricaEconomía", "industry": None},
    {"url": "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml", "source": "Bloomberg Línea", "industry": None},
    # ── Infraestructura / construcción ──────────────────────────────────────
    {"url": "https://www.cchc.cl/feed/", "source": "CChC", "industry": "Infraestructura"},
    # ── Energía ──────────────────────────────────────────────────────────────
    {"url": "https://www.revistaei.cl/feed/", "source": "Revista EI", "industry": "Energía"},
    {"url": "https://www.electricidad.cl/feed/", "source": "Revista Electricidad", "industry": "Energía"},
    {"url": "https://energiaestrategica.com/feed/", "source": "Energía Estratégica", "industry": "Energía"},
    # ── Generales Chile (filtro estricto por keywords mineros) ───────────────
    {"url": "https://radio.uchile.cl/feed/", "source": "Radio U. de Chile", "industry": None},
]
# Removidos (verificados muertos 2026-05-23): pisoexploracion.cl (DNS),
# construccionminera.cl (DNS), pulso.cl/feed/ (devuelve HTML), elmostrador
# mercados/feed/ (404), biobiochile.cl/feed/ (404), emol.com/rss (timeout),
# cooperativa.cl/economia.xml (404), 24horas.cl/economia.xml (404).

KEYWORDS_MINERIA = ["miner", "cobre", "litio", "molibdeno", "relave", "faena", "codelco", "bhp", "teck", "yacimiento", "salar", "antofagasta minerals", "collahuasi", "escondida", "spence", "chuquicamata"]
KEYWORDS_INFRA = ["infraestructura", "carretera", "puente", "ruta", "mop", "concesión vial", "obras públicas", "autopista", "aeropuerto", "hospital", "embalse"]
KEYWORDS_ENERGIA = ["energía", "fotovoltai", "eólica", "subestación", "transmisión", "solar", "renovable", "generación eléctrica", "hidrógeno verde", "geotérmica"]
KEYWORDS_OIL = ["petróleo", "gas natural", "enap", "hidrocarburo", "gasoducto", "refinería", "gnl"]


def classify_industry(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in KEYWORDS_MINERIA): return "Minería"
    if any(k in t for k in KEYWORDS_OIL): return "Oil & Gas"
    if any(k in t for k in KEYWORDS_ENERGIA): return "Energía"
    if any(k in t for k in KEYWORDS_INFRA): return "Infraestructura"
    return None


def score_rss(industry: Optional[str], title: str) -> int:
    base = 20
    if industry == "Minería": base = 52
    elif industry == "Oil & Gas": base = 50
    elif industry == "Energía": base = 47
    elif industry == "Infraestructura": base = 42
    t = title.lower()
    kw = 0
    if any(k in t for k in ["inversión", "proyecto", "planta", "ampliación", "construcción", "millones", "usd"]): kw += 10
    return max(0, min(100, base + kw))


def fetch_feed(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    try:
        r = requests.get(feed["url"], timeout=15, headers={"User-Agent": "StratmapWorker/0.2"}, verify=False)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[rss_mineria] error {feed['source']}: {e}")
        return []

    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items:
        title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        if not title: continue
        description = (item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
        blob = title + " " + description
        industry = feed.get("industry") or classify_industry(blob)
        if not industry: continue
        url = (item.findtext("link") or item.findtext("{http://www.w3.org/2005/Atom}id") or
               f"rss://{hashlib.md5((feed['url']+title).encode()).hexdigest()}").strip()
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


def fetch_rss_mineria(limit: int = 300) -> List[Dict[str, Any]]:
    import urllib3
    urllib3.disable_warnings()
    out = []
    for feed in RSS_FEEDS:
        items = fetch_feed(feed)
        print(f"[rss_mineria] {feed['source']}: {len(items)} artículos")
        out.extend(items)
        if len(out) >= limit: break
    return out[:limit]
