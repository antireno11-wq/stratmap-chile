# connectors/jobs_scraper.py
"""
Detecta señales de contratación en empresas mineras chilenas.
Fuentes: portales de carreras directos de cada empresa.
Actualiza jobs_count y signal_score en la tabla opportunities.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}

# ── Configuración de empresas y sus portales directos ─────────────────────────

MINING_COMPANIES = [
    {
        "name": "BHP",
        "career_url": "https://careers.bhp.com/search-jobs/Chile/107/1",
        "count_selectors": ["span.search-results-count", "div.result-count", "h1.results-count"],
        "card_selectors": ["li.search-result", "div.job-card", "article.job"],
    },
    {
        "name": "Codelco",
        "career_url": "https://empleos.codelco.cl/",
        "count_selectors": ["span.total", "div.count", "h2.results"],
        "card_selectors": ["div.vacante", "article.job", "li.empleo", "div.oferta"],
    },
    {
        "name": "SQM",
        "career_url": "https://www.sqm.com/es/sobre-sqm/trabaja-con-nosotros/",
        "count_selectors": ["span.count", "div.jobs-count"],
        "card_selectors": ["div.job", "li.position", "article.vacante", "a.job-link"],
    },
    {
        "name": "Anglo American",
        "career_url": "https://careers.angloamerican.com/search/?q=&locationsearch=Chile",
        "count_selectors": ["span.paginationLabel", "div.results-count", "span#totalJobCount"],
        "card_selectors": ["li.job-result", "div.job-item", "article.job-listing"],
    },
    {
        "name": "Teck",
        "career_url": "https://jobs.teck.com/search/?q=&locationsearch=Chile",
        "count_selectors": ["span.paginationLabel", "div.results-count"],
        "card_selectors": ["li.job-result", "div.job-item"],
    },
    {
        "name": "Antofagasta Minerals",
        "career_url": "https://www.aminerals.cl/es/personas/trabaja-con-nosotros/",
        "count_selectors": ["span.count", "div.total-jobs"],
        "card_selectors": ["div.job", "li.vacante", "article.position", "a.job-link"],
    },
    {
        "name": "Freeport-McMoRan",
        "career_url": "https://jobs.freeportinmycommunity.com/search/?q=&locationsearch=Chile",
        "count_selectors": ["span.paginationLabel", "div.results-count"],
        "card_selectors": ["li.job-result", "div.job-card"],
    },
    {
        "name": "Glencore",
        "career_url": "https://www.glencore.com/careers/vacancies?country=Chile",
        "count_selectors": ["span.count", "div.results-number"],
        "card_selectors": ["div.vacancy", "li.job", "article.position"],
    },
]

# ── Scraper genérico por portal directo ───────────────────────────────────────

def scrape_career_page(company: Dict[str, Any]) -> int:
    """
    Scraping directo del portal de carreras de una empresa.
    Intenta múltiples selectores para encontrar el conteo de empleos.
    """
    try:
        r = requests.get(company["career_url"], headers=HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Intento 1 — buscar contador numérico explícito
        for selector in company.get("count_selectors", []):
            tag_name, *class_parts = selector.split(".")
            class_name = class_parts[0] if class_parts else None
            el = soup.find(tag_name, class_=class_name)
            if el:
                nums = re.findall(r"\d+", el.get_text())
                if nums:
                    count = int(nums[0])
                    print(f"[jobs] {company['name']}: contador encontrado → {count}")
                    return count

        # Intento 2 — buscar número en texto tipo "X empleos" o "X vacantes"
        text = soup.get_text()
        patterns = [
            r"(\d+)\s*(empleos|vacantes|posiciones|cargos|oportunidades|jobs|positions)",
            r"(empleos|vacantes|posiciones|jobs|positions)[:\s]+(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                nums = [g for g in match.groups() if g and g.isdigit()]
                if nums:
                    count = int(nums[0])
                    print(f"[jobs] {company['name']}: texto encontrado → {count}")
                    return count

        # Intento 3 — contar tarjetas de empleo
        total_cards = 0
        for selector in company.get("card_selectors", []):
            parts = selector.split(".")
            tag = parts[0]
            cls = parts[1] if len(parts) > 1 else None
            cards = soup.find_all(tag, class_=cls) if cls else soup.find_all(tag)
            total_cards = max(total_cards, len(cards))

        if total_cards > 0:
            print(f"[jobs] {company['name']}: tarjetas encontradas → {total_cards}")
            return total_cards

        print(f"[jobs] {company['name']}: página cargó pero sin empleos detectados")
        return 0

    except requests.exceptions.HTTPError as e:
        print(f"[jobs] {company['name']} HTTP error: {e}")
        return 0
    except requests.exceptions.ConnectionError as e:
        print(f"[jobs] {company['name']} conexión fallida: {e}")
        return 0
    except Exception as e:
        print(f"[jobs] {company['name']} error inesperado: {e}")
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
    Escanea todos los portales de carreras y retorna señales detectadas.
    """
    results: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for company in MINING_COMPANIES:
        jobs_count = scrape_career_page(company)
        score_impact = jobs_to_signal_score(jobs_count)

        if jobs_count > 0:
            results.append({
                "company": company["name"],
                "signal_type": "jobs",
                "signal_source": company["career_url"],
                "signal_data": {
                    "jobs_count": jobs_count,
                    "career_url": company["career_url"],
                },
                "score_impact": score_impact,
                "jobs_count": jobs_count,
                "detected_at": now,
            })
            print(f"[jobs] ✅ {company['name']}: {jobs_count} empleos → +{score_impact} pts")
        else:
            print(f"[jobs] {company['name']}: sin empleos detectados")

        time.sleep(2)  # Respetar rate limiting entre empresas

    return results


def get_companies_hiring_summary() -> List[Dict[str, Any]]:
    """Versión resumida para el dashboard."""
    signals = fetch_jobs_signals()
    return sorted(signals, key=lambda x: x["jobs_count"], reverse=True)


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Escaneando portales de carreras mineras...")
    results = fetch_jobs_signals()
    print(f"\n✅ Total empresas con actividad: {len(results)}")
    for r in results:
        print(f"  → {r['company']}: {r['jobs_count']} empleos (+{r['score_impact']} pts)")
