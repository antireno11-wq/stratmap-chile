# connectors/jobs_scraper.py
"""
Detecta señales de contratación en empresas mineras chilenas.
Usa Playwright para renderizar páginas con JavaScript.
Actualiza jobs_count y signal_score en la tabla opportunities.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

# ── Configuración de empresas y sus portales directos ─────────────────────────

MINING_COMPANIES = [
    {
        "name": "BHP",
        "career_url": "https://careers.bhp.com/search-jobs/Chile/107/1",
        "wait_for": "ul.search-results",
        "count_selector": "span.search-results-count",
        "card_selector": "li.search-result",
    },
    {
        "name": "Codelco",
        "career_url": "https://empleos.codelco.cl/",
        "wait_for": "body",
        "count_selector": None,
        "card_selector": "div.vacante, article.job, li.empleo, div.oferta, a.job-link",
    },
    {
        "name": "SQM",
        "career_url": "https://www.sqm.com/es/sobre-sqm/trabaja-con-nosotros/",
        "wait_for": "body",
        "count_selector": None,
        "card_selector": "div.job, li.position, article.vacante, a.career-link",
    },
    {
        "name": "Anglo American",
        "career_url": "https://careers.angloamerican.com/search/?q=&locationsearch=Chile",
        "wait_for": "body",
        "count_selector": "span#totalJobCount",
        "card_selector": "li.job-result, div.job-item",
    },
    {
        "name": "Teck",
        "career_url": "https://jobs.teck.com/search/?q=&locationsearch=Chile",
        "wait_for": "body",
        "count_selector": "span.paginationLabel",
        "card_selector": "li.job-result, div.job-item",
    },
    {
        "name": "Antofagasta Minerals",
        "career_url": "https://www.aminerals.cl/trabaja-con-nosotros/",
        "wait_for": "body",
        "count_selector": None,
        "card_selector": "div.job, li.vacante, article.position, a.job-link",
    },
    {
        "name": "Glencore",
        "career_url": "https://www.glencore.com/careers/vacancies",
        "wait_for": "body",
        "count_selector": "span.count",
        "card_selector": "div.vacancy, li.job, article.position",
    },
    {
        "name": "Freeport-McMoRan",
        "career_url": "https://jobs.fcx.com/search/?q=&locationsearch=Chile",
        "wait_for": "body",
        "count_selector": "span.paginationLabel",
        "card_selector": "li.job-result, div.job-card",
    },
]


# ── Scoring de señales ─────────────────────────────────────────────────────────

def jobs_to_signal_score(jobs_count: int) -> int:
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


# ── Scraper con Playwright ─────────────────────────────────────────────────────

def scrape_with_playwright(company: Dict[str, Any]) -> int:
    """Usa Playwright para renderizar la página con JS y contar empleos."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process",
                ]
            )
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                )
            )

            page.goto(company["career_url"], timeout=30000)

            # Esperar a que cargue el contenido
            try:
                if company.get("wait_for"):
                    page.wait_for_selector(company["wait_for"], timeout=10000)
            except Exception:
                pass

            # Esperar un poco más para JS
            page.wait_for_timeout(3000)

            # Intento 1 — selector de contador explícito
            if company.get("count_selector"):
                try:
                    el = page.query_selector(company["count_selector"])
                    if el:
                        text = el.inner_text()
                        nums = re.findall(r"\d+", text)
                        if nums:
                            count = int(nums[0])
                            print(f"[jobs] {company['name']}: contador → {count}")
                            browser.close()
                            return count
                except Exception:
                    pass

            # Intento 2 — buscar número en texto de página
            try:
                text = page.inner_text("body")
                patterns = [
                    r"(\d+)\s*(empleos|vacantes|posiciones|cargos|oportunidades|jobs|positions|results)",
                    r"(showing|encontr\w+)\s+(\d+)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        nums = [g for g in match.groups() if g and g.isdigit()]
                        if nums:
                            count = int(nums[0])
                            print(f"[jobs] {company['name']}: texto → {count}")
                            browser.close()
                            return count
            except Exception:
                pass

            # Intento 3 — contar tarjetas de empleo
            if company.get("card_selector"):
                try:
                    max_cards = 0
                    for selector in company["card_selector"].split(","):
                        selector = selector.strip()
                        cards = page.query_selector_all(selector)
                        max_cards = max(max_cards, len(cards))
                    if max_cards > 0:
                        print(f"[jobs] {company['name']}: tarjetas → {max_cards}")
                        browser.close()
                        return max_cards
                except Exception:
                    pass

            browser.close()
            print(f"[jobs] {company['name']}: página cargó pero sin empleos detectados")
            return 0

    except Exception as e:
        print(f"[jobs] {company['name']} error Playwright: {e}")
        return 0


# ── Función principal ──────────────────────────────────────────────────────────

def fetch_jobs_signals() -> List[Dict[str, Any]]:
    """Escanea todos los portales de carreras y retorna señales detectadas."""
    results: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for company in MINING_COMPANIES:
        jobs_count = scrape_with_playwright(company)
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

        time.sleep(2)

    return results


def get_companies_hiring_summary() -> List[Dict[str, Any]]:
    """Versión resumida para el dashboard."""
    signals = fetch_jobs_signals()
    return sorted(signals, key=lambda x: x["jobs_count"], reverse=True)


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Escaneando portales de carreras mineras con Playwright...")
    results = fetch_jobs_signals()
    print(f"\n✅ Total empresas con actividad: {len(results)}")
    for r in results:
        print(f"  → {r['company']}: {r['jobs_count']} empleos (+{r['score_impact']} pts)")
