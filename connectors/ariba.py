"""
connectors/ariba.py
Scraper autenticado de SAP Ariba (portal Codelco).
Requiere: ARIBA_USER, ARIBA_PASS
"""

import os
import re
from typing import Any, Dict, List, Optional

ARIBA_URL = "https://service.ariba.com/Sourcing.aw/109582012/aw?awh=r&awssk=imz7nWe8&dard=1"

# Mapa de divisiones Codelco a regiones
DIVISION_REGION = {
    "rt01": "Antofagasta", "radomiro": "Antofagasta",
    "gobm": "Antofagasta", "gabriela mistral": "Antofagasta",
    "chuqui": "Antofagasta", "chuquicamata": "Antofagasta",
    "norte": "Antofagasta",
    "el teniente": "O'Higgins", "det": "O'Higgins",
    "ventanas": "Valparaíso", "barquito": "Atacama",
    "andina": "Valparaíso",
    "salvador": "Atacama",
    "vpzn": "Antofagasta",
}

def parse_region(text: str) -> Optional[str]:
    t = text.lower()
    for kw, region in DIVISION_REGION.items():
        if kw in t:
            return region
    # Regiones directas
    for r in ["Antofagasta","Atacama","Coquimbo","Valparaíso","O'Higgins","Maule","Biobío","Metropolitana"]:
        if r.lower() in t:
            return r
    return None

def score_ariba(title: str, mercancia: str, dias: Optional[int]) -> int:
    base = 70
    t = f"{title} {mercancia}".lower()
    if any(k in t for k in ["construcción", "montaje", "obras", "planta", "ampliación", "infraestructura"]):
        base += 10
    if any(k in t for k in ["servicio", "mantención", "operación", "reparación"]):
        base += 5
    if dias is not None and dias <= 14:
        base += 8  # urgente
    return min(base, 95)

def parse_dias(texto: str) -> Optional[int]:
    m = re.search(r'(\d+)\s*días?', texto, re.IGNORECASE)
    return int(m.group(1)) if m else None

def fetch_ariba(limit: int = 200) -> List[Dict[str, Any]]:
    user = os.getenv("ARIBA_USER", "")
    password = os.getenv("ARIBA_PASS", "")
    url = os.getenv("ARIBA_URL", ARIBA_URL)

    if not user or not password:
        print("[ariba] ARIBA_USER o ARIBA_PASS no configurados — saltando")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ariba] Playwright no instalado — saltando")
        return []

    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        try:
            print("[ariba] Abriendo login...")
            page.goto(url, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(2000)

            # Login
            user_input = (
                page.query_selector("input[type='text']") or
                page.query_selector("input[type='email']")
            )
            pass_input = page.query_selector("input[type='password']")

            if not user_input or not pass_input:
                print("[ariba] No se encontraron campos de login")
                browser.close()
                return []

            user_input.fill(user)
            pass_input.fill(password)

            login_btn = (
                page.query_selector("button[type='submit']") or
                page.query_selector("input[type='submit']") or
                page.query_selector("button:has-text('Inicio de sesión')")
            )
            if login_btn:
                login_btn.click()
            else:
                page.keyboard.press("Enter")

            page.wait_for_timeout(5000)
            page.wait_for_load_state("networkidle", timeout=30000)
            print(f"[ariba] URL post-login: {page.url}")
            page.wait_for_timeout(3000)

            # ── Extraer lista principal ────────────────────────────────────────
            rows = (
                page.query_selector_all("tbody tr") or
                page.query_selector_all("tr[class*='Row']")
            )
            print(f"[ariba] {len(rows)} filas en lista")

            # Recolectar links y datos básicos de la lista
            list_items = []
            for row in rows[:limit]:
                try:
                    cells = row.query_selector_all("td")
                    if len(cells) < 2:
                        continue
                    title_cell = cells[0]
                    title_link = title_cell.query_selector("a")
                    title = (title_link or title_cell).inner_text().strip()
                    if not title or len(title) < 5:
                        continue
                    href = title_link.get_attribute("href") if title_link else None
                    if href and not href.startswith("http"):
                        href = f"https://service.ariba.com{href}"
                    doc_id       = cells[1].inner_text().strip() if len(cells) > 1 else ""
                    fecha_cierre = cells[2].inner_text().strip() if len(cells) > 2 else ""
                    status       = cells[3].inner_text().strip() if len(cells) > 3 else "Abierto"
                    event_type   = cells[4].inner_text().strip() if len(cells) > 4 else "RFP"

                    if status.lower() in ["cerrado", "cancelado", "closed", "awarded"]:
                        continue

                    list_items.append({
                        "title": title, "href": href, "doc_id": doc_id,
                        "fecha_cierre": fecha_cierre, "status": status,
                        "event_type": event_type
                    })
                except Exception:
                    continue

            print(f"[ariba] {len(list_items)} licitaciones abiertas, entrando a detalles...")

            # ── Entrar al detalle de cada licitación ───────────────────────────
            for li in list_items[:limit]:
                try:
                    if not li["href"]:
                        # Sin link, usar datos básicos
                        items.append(_build_item(li, {}, url))
                        continue

                    detail_page = browser.new_page(
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                    )
                    detail_page.goto(li["href"], wait_until="networkidle", timeout=30000)
                    detail_page.wait_for_timeout(2000)

                    detail_text = detail_page.inner_text("body") or ""

                    # Extraer campos del detalle
                    detail = {}

                    # Propietario / contacto
                    m = re.search(r'Propietario[:\s]+([^\n]+)', detail_text)
                    if m: detail["propietario"] = m.group(1).strip()

                    # Mercancía / categoría
                    m = re.search(r'Mercancía[:\s]+([^\n]+)', detail_text)
                    if m: detail["mercancia"] = m.group(1).strip()

                    # Región desde detalle
                    m = re.search(r'Regiones?[:\s]+([^\n]+)', detail_text)
                    if m: detail["region_raw"] = m.group(1).strip()

                    # Tiempo restante
                    m = re.search(r'Tiempo restante[:\s]*([\d]+)\s*días?', detail_text, re.IGNORECASE)
                    if m: detail["dias_restantes"] = int(m.group(1))

                    # Fecha vencimiento
                    m = re.search(r'Fecha de vencimiento[:\s]+([^\n]+)', detail_text)
                    if m: detail["fecha_vencimiento"] = m.group(1).strip()

                    detail_page.close()
                    items.append(_build_item(li, detail, li["href"]))

                except Exception as e:
                    print(f"[ariba] Error detalle '{li['title'][:40]}': {e}")
                    items.append(_build_item(li, {}, li.get("href") or url))
                    continue

        except Exception as e:
            print(f"[ariba] Error general: {e}")
        finally:
            browser.close()

    # Deduplicar
    seen = set()
    unique = []
    for item in items:
        key = item["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    print(f"[ariba] {len(unique)} licitaciones extraídas")
    return unique[:limit]


def _build_item(li: dict, detail: dict, url: str) -> dict:
    title = li["title"]
    mercancia = detail.get("mercancia", "")
    region_raw = detail.get("region_raw", "") or li["title"]
    region = parse_region(region_raw) or parse_region(title)
    dias = detail.get("dias_restantes")
    propietario = detail.get("propietario", "")
    fecha_venc = detail.get("fecha_vencimiento", li.get("fecha_cierre", ""))

    entry_parts = []
    if propietario: entry_parts.append(f"Contacto: {propietario}")
    if mercancia:   entry_parts.append(f"Categoría: {mercancia}")
    if fecha_venc:  entry_parts.append(f"Cierre: {fecha_venc}")
    if dias:        entry_parts.append(f"{dias} días restantes")

    return {
        "source": "Ariba Codelco",
        "title": title[:400],
        "url": url,
        "company": "Codelco",
        "contractor": propietario[:200] if propietario else None,
        "industry": "Minería",
        "region": region,
        "phase": f"{li['event_type']} - {li['status']}",
        "score": score_ariba(title, mercancia, dias),
        "entry": " | ".join(entry_parts)[:500] if entry_parts else None,
        "raw": {
            "doc_id": li.get("doc_id", ""),
            "fecha_cierre": li.get("fecha_cierre", ""),
            "fecha_vencimiento": fecha_venc,
            "dias_restantes": dias,
            "mercancia": mercancia,
            "region_raw": region_raw,
            "propietario": propietario,
            "status": li.get("status", ""),
            "event_type": li.get("event_type", ""),
            "tipo": "ariba_codelco"
        }
    }


if __name__ == "__main__":
    items = fetch_ariba(limit=20)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i['region']} | {i['contractor']}")
