# connectors/jobs_scraper.py
"""
Detecta señales de contratación en empresas mineras chilenas.
Fuentes: Trabajando.com, Laborum.cl y portales directos de empresas.
Actualiza jobs_count y signal_score en la tabla opportunities.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        "keywords": ["codelco", "chuquicamata", "el teniente", "andina", "salvador", "gabriela mistral", "radomiro tomic"],
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
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
}

# ── Scrapers por fuente ────────────────────────────────────────────────────────

def fetch_trabajando(company_keyword: str) -> int:
    """Retorna cantidad de empleos encontrados en trabajando.com para una empresa."""
    try:
        url = f"https://www.trabajando.com/empleos?q={requests.utils.quote(company_keyword)}&l=Chile"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Busca el contador de resultados
        counter = soup.find("span", class_=re.compile(r"result|count|total", re.I))
        if counter:
            nums = re.findall(r"\d+", counter.get_text())
            if nums:
                return int(nums[0])

        # Si no hay contador, cuenta las tarjetas de empleo
        cards = soup.find_all("div", class_=re.compile(r"job-card|oferta|aviso", re.I))
        return len(cards)

    except Exception as e:
        print(f"[jobs] trabajando.com error para '{company_keyword}': {e}")
        return 0


def fetch_laborum(company_keyword: str) -> int:
    """Retorna cantidad de empleos encontrados en laborum.cl para una empresa."""
    try:
        url = f"https://www.laborum.cl/empleos?q={requests.utils.quote(company_keyword)}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Busca contador de resultados
        counter = soup.find(string=re.compile(r"\d+\s*(empleos|resultados|trabajos)", re.I))
        if counter:
            nums = re.findall(r"\d+", counter)
            if nums:
                return int(nums[0])

        # Cuenta tarjetas
        cards = soup.find_all("article", class_=re.compile(r"job|aviso|oferta", re.I))
        return len(cards)

    except Exception as e:
        print(f"[jobs] laborum.cl error para '{company_keyword}': {e}")
        return 0


def fetch_codelco_direct() -> int:
    """Scraping directo del portal de empleos de Codelco."""
    try:
        url = "https://www.codelco.com/prontus_codelco/site/edic/base/port/trabaja_con_nosotros.html"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        vacantes = soup.find_all(string=re.compile(r"vacan|cargo|posici", re.I))
        return len(vacantes)
    except Exception as e:
        print(f"[jobs] codelco directo error: {e}")
        return 0


# ── Scoring de señales ─────────────────────────────────────────────────────────

def jobs_to_signal_score(jobs_count: int) -> int:
    """
    Convierte cantidad de empleos en un score de señal (0-30 puntos adicionales).
    Estos puntos se suman al score base de la oportunidad.
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
    Formato compatible con opportunity_signals.
    """
    results: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for company in MINING_COMPANIES:
        total_jobs = 0
        sources_checked = []

        for keyword in company["keywords"]:
            # Trabajando.com
            jobs_t = fetch_trabajando(keyword)
            total_jobs += jobs_t
            if jobs_t > 0:
                sources_checked.append(f"trabajando.com: {jobs_t}")
            time.sleep(1)  # Respetar rate limiting

            # Laborum.cl
            jobs_l = fetch_laborum(keyword)
            total_jobs += jobs_l
            if jobs_l > 0:
                sources_checked.append(f"laborum.cl: {jobs_l}")
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
                "signal_source": "trabajando.com + laborum.cl",
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
    Versión resumida para el dashboard — muestra qué empresas
    están contratando más esta semana.
    """
    signals = fetch_jobs_signals()
    summary = sorted(signals, key=lambda x: x["jobs_count"], reverse=True)
    return summary


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Escaneando empleos en empresas mineras...")
    results = fetch_jobs_signals()
    print(f"\n✅ Total empresas con actividad: {len(results)}")
    for r in results:
        print(f"  → {r['company']}: {r['jobs_count']} empleos (+{r['score_impact']} pts)")
