"""
bhp_careers.py — Conector de empleos BHP Chile
================================================
Fuente: https://careers.bhp.com
Scraping simple con requests + BeautifulSoup (HTML server-side).
Categoriza los empleos por área usando keywords del título.

Integración:
  - Se llama desde sea_ingest.py al final del worker
  - Upsertea en la tabla opportunities con source='BHP Careers'
  - Actualiza signal_score y jobs_count del mandante "BHP"
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any

BASE_URL    = "https://careers.bhp.com"
SEARCH_URL  = (
    "https://careers.bhp.com/search/"
    "?createNewAlert=false&q=&optionsFacetsDD_location=Chile"
    "&optionsFacetsDD_customfield1=&optionsFacetsDD_title="
    "&optionsFacetsDD_customfield4="
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}

# Categorías por keywords del título
AREA_KEYWORDS = {
    "Operaciones":      ["operador","operadora","operaciones","produccion","extraccion","mina","minera"],
    "Mantenimiento":    ["mantenedor","mantenedora","mantenci","electrico","electricista","mecanico","instrumentista","planta"],
    "Ingeniería":       ["engineer","ingeniero","ingenieria","especialista","specialist","lead","principal","tecnico"],
    "Geología":         ["geolog","geoscien","geotecnia","hidrogeol","exploracion"],
    "Finanzas":         ["finance","finanza","financiero","reporting","planning","contab"],
    "TI / Datos":       ["digital","data","ai","autonomous","autonomia","ahs","software","systems","tecnolog"],
    "RRHH / Capacit.":  ["training","capacit","formacion","rrhh","people","talento"],
    "Supervisión":      ["supervisor","superintendente","gerente","jefe","coordinador"],
    "HSE":              ["seguridad","safety","medio ambiente","ambiente","hse","salud"],
    "Proyectos":        ["project","proyecto","inversiones","transactions","construction"],
}

def classify_area(title: str) -> str:
    t = title.lower()
    for area, kws in AREA_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return area
    return "Otros"


def parse_jobs(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Cada fila de resultado tiene un <a> con el título y URL del cargo
    for a in soup.select("table a[href*='/job/']"):
        title_raw = a.get_text(strip=True)
        if not title_raw or len(title_raw) < 5:
            continue

        # El título tiene formato "Cargo | Empresa" — separar
        parts = title_raw.split("|")
        title   = parts[0].strip()
        empresa = parts[1].strip() if len(parts) > 1 else "BHP"

        href = a.get("href", "")
        url  = BASE_URL + href if href.startswith("/") else href

        # Fecha de cierre (texto después del nombre de país)
        row = a.find_parent("tr") or a.find_parent("td")
        fecha_text = ""
        if row:
            text = row.get_text(" ", strip=True)
            # Buscar patrón DD Mon YYYY o YYYY-MM-DD
            m = re.search(r"\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}", text)
            if m:
                fecha_text = m.group(0)

        area = classify_area(title)

        jobs.append({
            "title":   title,
            "empresa": empresa,
            "area":    area,
            "url":     url,
            "fecha_cierre": fecha_text,
        })

    # Deduplicar por URL
    seen = set()
    unique = []
    for j in jobs:
        if j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)

    return unique


def fetch_all_pages() -> List[Dict[str, Any]]:
    all_jobs = []
    page = 1
    while True:
        url = SEARCH_URL + (f"&start={( page-1)*15}" if page > 1 else "")
        print(f"  [bhp] Página {page}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [bhp] Error página {page}: {e}")
            break

        jobs = parse_jobs(resp.text)
        if not jobs:
            break

        # Check for duplicates (llegamos al final)
        new_urls = {j["url"] for j in jobs} - {j["url"] for j in all_jobs}
        if not new_urls:
            break

        all_jobs.extend([j for j in jobs if j["url"] in new_urls])
        print(f"  [bhp] +{len(jobs)} empleos (total {len(all_jobs)})")

        # Si hay menos de 15, no hay más páginas
        if len(jobs) < 15:
            break
        page += 1

    return all_jobs


def build_opportunities(jobs: List[Dict]) -> List[Dict[str, Any]]:
    """Convierte empleos BHP a formato opportunity para upsert."""
    now = datetime.now(timezone.utc)
    opps = []

    # Agrupar por empresa para crear 1 opportunity por empresa con jobs_count
    from collections import defaultdict
    by_empresa: Dict[str, list] = defaultdict(list)
    for j in jobs:
        by_empresa[j["empresa"]].append(j)

    for empresa, emp_jobs in by_empresa.items():
        total = len(emp_jobs)
        areas = {}
        for j in emp_jobs:
            areas[j["area"]] = areas.get(j["area"], 0) + 1

        # Construir descripción con listado de cargos
        cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
        entry = (
            f"{empresa} tiene {total} cargo{'s' if total > 1 else ''} "
            f"disponibles en Chile actualmente:\n\n{cargo_list}"
        )

        # URL única por empresa para que el upsert no colisione
        empresa_slug = empresa.lower().replace(" ", "-").replace("/", "-")
        url = f"https://careers.bhp.com/chile/{empresa_slug}"

        signal_detail = {
            "by_area": areas,
            "total": total,
            "fuente": "BHP Careers",
            "cargos": [j["title"] for j in emp_jobs[:10]],
        }

        opps.append({
            "source":        "BHP Careers",
            "title":         f"Empleos BHP Chile — {empresa} ({total} cargos)",
            "company":       empresa,
            "industry":      "Minería",
            "phase":         "Contratación activa",
            "region":        "Chile",
            "score":         60 + min(total * 2, 30),   # más empleos → más relevante
            "url":           url,
            "published_at":  now.isoformat(),
            "entry":         entry,
            "jobs_count":    total,
            "signal_score":  min(total * 3, 40),
            "last_signal_at": now.isoformat(),
            "signal_detail": __import__('json').dumps(signal_detail, ensure_ascii=False),
            "raw":           {"by_area": areas, "empleos": [j["url"] for j in emp_jobs]},
        })

    return opps


def run() -> Dict[str, Any]:
    print("[bhp_careers] Scraping empleos BHP Chile...")
    jobs = fetch_all_pages()
    if not jobs:
        print("[bhp_careers] Sin empleos encontrados")
        return {"jobs": 0, "opportunities": 0}

    print(f"[bhp_careers] {len(jobs)} empleos encontrados")

    # Mostrar breakdown por área
    areas: Dict[str, int] = {}
    for j in jobs:
        areas[j["area"]] = areas.get(j["area"], 0) + 1
    for area, cnt in sorted(areas.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")

    opps = build_opportunities(jobs)
    print(f"[bhp_careers] {len(opps)} opportunities a upsertear")

    try:
        import db
        inserted, updated = db.upsert_opportunities(opps)
        print(f"[bhp_careers] inserted={inserted} updated={updated}")
        return {"jobs": len(jobs), "opportunities": len(opps), "inserted": inserted, "updated": updated}
    except Exception as e:
        print(f"[bhp_careers] Error upsert: {e}")
        import traceback; traceback.print_exc()
        return {"jobs": len(jobs), "error": str(e)}


if __name__ == "__main__":
    result = run()
    print(result)
