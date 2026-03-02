"""
connectors/empleos_portales.py
Scraper de portales de empleo propios de mineras:
- Codelco: https://www.codelco.com/trabaja-con-nosotros
- BHP/Escondida: https://careers.bhp.com
- SQM: https://www.sqm.com/es/trabaja-con-nosotros/
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("America/Santiago")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "es-CL,es;q=0.9",
}

SIGNAL_HIGH = ["proyecto","construcción","montaje","comisionamiento","puesta en marcha",
               "ramp-up","epcm","epc","ingeniería","obras","ampliación","expansión"]
SIGNAL_MED  = ["producción","operaciones","planta","procesamiento","mina","faena",
               "supervisor","jefe","coordinador"]

REGION_KEYWORDS = {
    "antofagasta":"Antofagasta","calama":"Antofagasta","chuquicamata":"Antofagasta",
    "atacama":"Atacama","copiap":"Atacama","salvador":"Atacama",
    "valparaíso":"Valparaíso","valparaiso":"Valparaíso","andina":"Valparaíso",
    "o'higgins":"O'Higgins","rancagua":"O'Higgins","teniente":"O'Higgins",
    "tarapacá":"Tarapacá","tarapaca":"Tarapacá","iquique":"Tarapacá",
    "coquimbo":"Coquimbo","la serena":"Coquimbo",
}

def classify_signal(title: str):
    t = title.lower()
    if any(k in t for k in SIGNAL_HIGH): return ("construcción/proyecto", 15)
    if any(k in t for k in SIGNAL_MED):  return ("operaciones", 8)
    return ("general", 3)

def parse_region(text: str) -> Optional[str]:
    t = text.lower()
    for k, v in REGION_KEYWORDS.items():
        if k in t: return v
    return None

def make_item(title, company, region, url, signal_type, signal_pts):
    return {
        "title": title[:300],
        "company": company,
        "company_raw": company,
        "region": region,
        "location_raw": region or "",
        "url": url,
        "signal_type": signal_type,
        "signal_pts": signal_pts,
        "source_query": company,
        "published_at": None,
    }

# ── CODELCO ───────────────────────────────────────────────────────────────────
def fetch_codelco_jobs(session: requests.Session) -> List[Dict]:
    items = []
    try:
        # Codelco usa un portal público con tabla de cargos
        url = "https://www.codelco.com/trabaja-con-nosotros/prontus_codelco/2011-01-18/120411.html"
        r = session.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tr, .cargo-item, .job-item, li")
        print(f"[codelco_jobs] {len(rows)} elementos encontrados")
        for row in rows:
            text = row.get_text(" ", strip=True)
            if len(text) < 10: continue
            link = row.select_one("a")
            href = link.get("href","") if link else url
            if href.startswith("/"): href = "https://www.codelco.com" + href
            region = parse_region(text)
            stype, spts = classify_signal(text)
            if spts >= 8:  # Solo señales relevantes
                items.append(make_item(text[:200], "Codelco", region, href, stype, spts))
    except Exception as e:
        print(f"[codelco_jobs] error: {e}")

    # Alternativa: buscar en portal de licitaciones/noticias de empleo
    if not items:
        try:
            url2 = "https://www.codelco.com/trabaja-con-nosotros"
            r2 = session.get(url2, headers=HEADERS, timeout=20)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            links = soup2.select("a[href*='cargo'], a[href*='empleo'], a[href*='trabajo']")
            for a in links[:10]:
                title = a.get_text(strip=True)
                if len(title) < 5: continue
                href = a.get("href","")
                if href.startswith("/"): href = "https://www.codelco.com" + href
                stype, spts = classify_signal(title)
                items.append(make_item(title, "Codelco", None, href, stype, spts))
        except Exception as e:
            print(f"[codelco_jobs] alt error: {e}")

    print(f"[codelco_jobs] {len(items)} cargos")
    return items

# ── BHP / ESCONDIDA ───────────────────────────────────────────────────────────
def fetch_bhp_jobs(session: requests.Session) -> List[Dict]:
    items = []
    try:
        # BHP usa API pública para buscar empleos en Chile
        url = "https://careers.bhp.com/api/jobs?countryCode=CL&pageSize=50"
        r = session.get(url, headers=HEADERS, timeout=20)
        data = r.json()
        jobs = data.get("data", data.get("jobs", data.get("items", [])))
        print(f"[bhp_jobs] {len(jobs)} empleos via API")
        for job in jobs[:50]:
            title = job.get("title") or job.get("name") or ""
            location = job.get("location") or job.get("city") or ""
            job_url = job.get("url") or job.get("applyUrl") or "https://careers.bhp.com"
            if not title: continue
            region = parse_region(f"{title} {location}")
            stype, spts = classify_signal(title)
            items.append(make_item(title, "BHP/Escondida", region, job_url, stype, spts))
    except Exception as e:
        print(f"[bhp_jobs] API error: {e}")
        # Fallback HTML
        try:
            url2 = "https://careers.bhp.com/search-jobs/Chile/1777/3/3893952/45/-90/50/2"
            r2 = session.get(url2, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r2.text, "html.parser")
            for el in soup.select(".job-title, h2 a, .position-title")[:30]:
                title = el.get_text(strip=True)
                if len(title) < 5: continue
                stype, spts = classify_signal(title)
                items.append(make_item(title, "BHP/Escondida", "Antofagasta",
                                       "https://careers.bhp.com", stype, spts))
        except Exception as e2:
            print(f"[bhp_jobs] fallback error: {e2}")

    print(f"[bhp_jobs] {len(items)} cargos")
    return items

# ── SQM ───────────────────────────────────────────────────────────────────────
def fetch_sqm_jobs(session: requests.Session) -> List[Dict]:
    items = []
    try:
        url = "https://www.sqm.com/es/trabaja-con-nosotros/"
        r = session.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = soup.select(".job-listing, .cargo, .position, article, li")
        print(f"[sqm_jobs] {len(jobs)} elementos")
        for job in jobs[:30]:
            link = job.select_one("a")
            if not link: continue
            title = link.get_text(strip=True)
            if len(title) < 5: continue
            href = link.get("href","")
            if href.startswith("/"): href = "https://www.sqm.com" + href
            text = job.get_text(" ", strip=True)
            region = parse_region(text) or "Antofagasta"  # SQM opera en Atacama/Antofagasta
            stype, spts = classify_signal(title)
            items.append(make_item(title, "SQM", region, href, stype, spts))
    except Exception as e:
        print(f"[sqm_jobs] error: {e}")
    print(f"[sqm_jobs] {len(items)} cargos")
    return items

# ── MAIN ──────────────────────────────────────────────────────────────────────
def fetch_portales(limit: int = 200) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items = []
    for fn in [fetch_codelco_jobs, fetch_bhp_jobs, fetch_sqm_jobs]:
        try:
            all_items.extend(fn(session))
        except Exception as e:
            print(f"[portales] error en {fn.__name__}: {e}")
    print(f"[portales] Total: {len(all_items)} empleos")
    return all_items[:limit]

if __name__ == "__main__":
    items = fetch_portales(limit=30)
    for i in items[:15]:
        print(f"  [{i['signal_pts']}pts/{i['signal_type']}] {i['title'][:55]} | {i['company']} | {i['region']}")
