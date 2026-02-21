# connectors/jobs_scraper.py
"""
Detecta señales de contratación en empresas mineras chilenas.
Fuentes: trabajando.cl, indeed.com/chile, portales directos de empresas.
Actualiza jobs_count y signal_score en la tabla opportunities.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

# ── Empresas mineras a monitorear ─────────────────────────────────────────────

MINING_COMPANIES = [
    {
        "name": "BHP",
        "keywords": ["bhp", "escondida", "spence"],
        "regions": ["Antofagasta", "Tarapacá"],
    },
    {
        "name": "Codelco",
        "keywords": ["codelco", "chuquicamata", "el teniente", "andina", "radomiro tomic"],
        "regions": ["Antofagasta", "O'Higgins", "Atacama"],
    },
    {
        "name": "Antofagasta Minerals",
        "keywords": ["antofagasta minerals", "los pelambres", "centinela", "zaldivar", "antucoya"],
        "regions": ["Antofagasta", "Coquimbo"],
    },
    {
        "name": "Anglo American",
        "keywords": ["anglo american", "los bronces", "el soldado"],
        "regions": ["Región Metropolitana", "Valparaíso"],
    },
    {
        "name": "Teck",
        "keywords": ["teck", "quebrada blanca", "carmen de andacollo"],
        "regions": ["Tarapacá", "Coquimbo"],
    },
    {
        "name": "Freeport-McMoRan",
        "keywords": ["freeport", "el abra"],
        "regions": ["Antofagasta"],
    },
    {
        "name": "Glencore",
        "keywords": ["glencore", "lomas bayas"],
        "regions": ["Antofagasta"],
    },
    {
        "name": "SQM",
        "keywords": ["sqm", "soquimich"],
        "regions": ["Antofagasta", "Tarapacá"],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ── Scrapers por fuente ────────────────────────────────────────────────────────

def fetch_trabajando(company_keyword: str) -> int:
    """Retorna cantidad de empleos en trabajando.cl"""
    try:
        url = f"https://www.trabajando.cl/trabajo/{requests.utils.quote(company_keyword)}"
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Busca contador de resultados
        for tag in soup.find_all(string=re.compile(r"\d+\s*(empleo|trabajo|cargo|resultado)", re.I)):
            nums = re.findall(r"\d+", tag)
            if nums:
                return int(nums[0])

        # Cuenta tarjetas de empleo
        cards = soup.find_all(["div", "article", "li"], class_=re.compile(r"job|empleo|oferta|aviso|card", re.I))
        return len(cards)

    except Exception as e:
        print(f"[jobs] trabajando.cl error para '{company_keyword}': {e}")
        return 0


def fetch_indeed(company_keyword: str) -> int:
    """Retorna cantidad de empleos en cl.indeed.com"""
    try:
        url = f"https://cl.indeed.com/jobs?q={requests.utils.quote(company_keyword)}&l=Chile"
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Busca el contador de resultados de Indeed
        count_el = soup.find("div", {"id": "searchCountPages"})
        if count_el:
            nums = re.findall(r"[\d,]+", count_el.get_text())
            if nums:
                return int(nums[0].replace(",", ""))

        # Cuenta tarjetas de empleo
        cards = soup.find_all("div", class_=re.compile(r"jobsearch-SerpJobCard|tapItem|job_seen_beacon", re.I))
        return len(cards)

    except Exception as e:
        print(f"[jobs] indeed error para '{company_keyword}': {e}")
        return 0


def fetch_getonbrd(company_keyword: str) -> int:
    """Retorna cantidad de empleos en getonbrd.com (muy usado en minería Chile)"""
    try:
        url = f"https://www.getonbrd.com/empleos?query={requests.utils.quote(company_keyword)}"
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.find_all(["div", "article"], class_=re.compile(r"job|empleo|position", re.I))
        return len(cards)
    except Exception as e:
        print(f"[jobs] getonbrd error para '{company_keyword}': {e}")
        return 0


def fetch_codelco_direct() -> int:
    """Scraping directo del portal de empleos de Codelco."""
    try:
        url = "https://www.codelco.com/trabaja-con-nosotros/prontus_codelco/2012-03-26/120000.html"
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Busca links a vacantes
        links = soup.find_all("a", href=re.compile(r"vacan|cargo|empleo|trabaj", re.I))
        return len(links)
    except Exception as e:
        print(f"[jobs] codelco directo error: {e}")
        return 0


# ── Scoring de señales ─────────────────────────────────────────────────────────

def jobs_to_signal_score(jobs_count: int) -> int:
    """
    Convierte cantidad de empleos en score adicional (0-30 puntos).
    """
    if jobs_count >= 50:
        return 30
    elif jobs_count >= 30:
        return 25
    elif jobs_count >= 20:
        return 20
    elif jobs_count >= 10:
        return 15
    elif jobs_count >= 5:
        return 10
    elif jobs_count >= 1:
        return 5
    return 0


# ── Función principal ──────────────────────────────────────────────────────────

def fetch_jobs_signals() -> List[Dict[str, Any]]:
    """
    Escanea todas las empresas mineras y retorna lista de señales detectadas.
    """
    results: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for company in MINING_COMPANIES:
        total_jobs = 0
        sources_checked = []

        for keyword in company["keywords"]:
            # trabajando.cl
            jobs_t = fetch_trabajando(keyword)
            total_jobs += jobs_t
            if jobs_t > 0:
                sources_checked.append(f"trabajando.cl/{keyword}: {jobs_t}")
            time.sleep(2)

            # indeed chile
            jobs_i = fetch_indeed(keyword)
            total_jobs += jobs_i
            if jobs_i > 0:
                sources_checked.append(f"indeed/{keyword}: {jobs_i}")
            time.sleep(2)

            # getonbrd
            jobs_g = fetch_getonbrd(keyword)
            total_jobs += jobs_g
            if jobs_g > 0:
                sources_checked.append(f"getonbrd/{keyword}: {jobs_g}")
            time.sleep(1)

        # Para Codelco, también revisamos directo
        if company["name"] == "Codelco":
            jobs_c = fetch_codelco_direct()
            total_jobs += jobs_c
            if jobs_c > 0:
                sources_checked.append(f"codelco.com: {jobs_c}")

        score_impact = jobs_to_signal_score(total_jobs)

        if total_jobs > 0:
            results.append({
                "company": company["name"],
                "signal_type": "jobs",
                "signal_source": "trabajando.cl + indeed + getonbrd",
                "signal_data": {
                    "jobs_count": total_jobs,
                    "sources": sources_checked,
                    "keywords_checked": company["keywords"],
                    "regions": company["regions"],
                },
                "score_impact": score_impact,
                "jobs_count": total_jobs,
                "detected_at": now,
            })
            print(f"[jobs] {company['name']}: {total_jobs} empleos detectados → +{score_impact} puntos")
        else:
            print(f"[jobs] {company['name']}: sin empleos detectados")

    return results


def get_companies_hiring_summary() -> List[Dict[str, Any]]:
    """
    Versión resumida para el dashboard.
    """
    signals = fetch_jobs_signals()
    return sorted(signals, key=lambda x: x["jobs_count"], reverse=True)


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Escaneando empleos en empresas mineras...")
    results = fetch_jobs_signals()
    print(f"\n✅ Total empresas con actividad: {len(results)}")
    for r in results:
        print(f"  → {r['company']}: {r['jobs_count']} empleos (+{r['score_impact']} pts)")
