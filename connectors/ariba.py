"""
connectors/ariba.py
Scraper autenticado de SAP Ariba (portal Codelco).
Requiere: ARIBA_USER, ARIBA_PASS, ARIBA_URL
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LOGIN_URL_DEFAULT = "https://service.ariba.com/Sourcing.aw/109582012/aw?awh=r&awssk=imz7nWe8&dard=1"


def parse_fecha(texto: str) -> Optional[str]:
    if not texto:
        return None
    # Formato visto en screenshot: "08/04/2026 16:00"
    for fmt in ["%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"]:
        try:
            dt = datetime.strptime(texto.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return None


def dias_restantes(fecha_iso: Optional[str]) -> Optional[int]:
    if not fecha_iso:
        return None
    try:
        dt = datetime.fromisoformat(fecha_iso)
        return (dt - datetime.now(timezone.utc)).days
    except Exception:
        return None


def classify_industry(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["eléctric", "electricidad", "subestación", "media tensión", "alta tensión", "instrumentación", "control"]):
        return "Energía"
    if any(k in t for k in ["carretera", "vialidad", "camino", "puente", "obras civiles", "infraestructura"]):
        return "Infraestructura"
    return "Minería"


def score_ariba(title: str, event_type: str, dias: Optional[int]) -> int:
    base = 72  # Ariba Codelco = fuente premium directa
    t = title.lower()
    if any(k in t for k in ["construcción", "montaje", "nueva", "ampliación", "planta"]):
        base += 10
    if any(k in t for k in ["servicio", "mantención", "operación", "reparación"]):
        base += 5
    if event_type and "rfp" in event_type.lower():
        base += 5
    if dias is not None:
        if 0 < dias <= 7:
            base += 8
        elif 7 < dias <= 30:
            base += 4
    return min(base, 98)


def fetch_ariba(limit: int = 200) -> List[Dict[str, Any]]:
    user     = os.getenv("ARIBA_USER", "")
    password = os.getenv("ARIBA_PASS", "")
    url      = os.getenv("ARIBA_URL", LOGIN_URL_DEFAULT)

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
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1440, "height": 900}
        ).new_page()

        try:
            print(f"[ariba] Abriendo login...")
            page.goto(url, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(2000)

            # Llenar credenciales
            user_sel = (
                page.query_selector("input[type='email']") or
                page.query_selector("input[name='UserName']") or
                page.query_selector("input[type='text']")
            )
            pass_sel = page.query_selector("input[type='password']")

            if not user_sel or not pass_sel:
                print("[ariba] Campos de login no encontrados")
                browser.close()
                return []

            user_sel.fill(user)
            page.wait_for_timeout(300)
            pass_sel.fill(password)
            page.wait_for_timeout(300)

            btn = (
                page.query_selector("button[type='submit']") or
                page.query_selector("button:has-text('Inicio de sesión')") or
                page.query_selector("button:has-text('Log in')")
            )
            if btn:
                btn.click()
            else:
                page.keyboard.press("Enter")

            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            print(f"[ariba] Logueado — URL: {page.url}")

            # Esperar tabla de licitaciones
            page.wait_for_selector("table tr, [role='row']", timeout=20000)
            page.wait_for_timeout(1500)

            # Parsear filas
            # Columnas vistas: Título | ID | Hora de finalización | Estado | Tipo de evento
            rows = page.query_selector_all("table tr")
            if not rows:
                rows = page.query_selector_all("[role='row']")

            print(f"[ariba] {len(rows)} filas encontradas")

            for row in rows[1:limit+1]:  # skip header
                try:
                    cells = row.query_selector_all("td")
                    if not cells:
                        cells = row.query_selector_all("[role='cell'], [role='gridcell']")
                    if len(cells) < 2:
                        continue

                    # Título
                    a_tag   = cells[0].query_selector("a")
                    title   = (a_tag or cells[0]).inner_text().strip()
                    if not title or len(title) < 5:
                        continue

                    # URL
                    href = a_tag.get_attribute("href") if a_tag else None
                    if href and href.startswith("/"):
                        detail_url = f"https://service.ariba.com{href}"
                    elif href and href.startswith("http"):
                        detail_url = href
                    else:
                        detail_url = url

                    doc_id     = cells[1].inner_text().strip() if len(cells) > 1 else ""
                    fecha_txt  = cells[2].inner_text().strip() if len(cells) > 2 else ""
                    estado     = cells[3].inner_text().strip() if len(cells) > 3 else "Abierto"
                    event_type = cells[4].inner_text().strip() if len(cells) > 4 else "RFP"

                    # Solo abiertas
                    if estado.lower() not in ["abierto", "open", "active", "activo", ""]:
                        continue

                    fecha_iso = parse_fecha(fecha_txt)
                    dias      = dias_restantes(fecha_iso)
                    industry  = classify_industry(title)
                    score     = score_ariba(title, event_type, dias)

                    items.append({
                        "source":     "Ariba Codelco",
                        "title":      title[:400],
                        "url":        detail_url,
                        "company":    "Codelco",
                        "contractor": None,
                        "industry":   industry,
                        "region":     None,
                        "phase":      f"{event_type}",
                        "score":      score,
                        "entry":      doc_id or title[:60],
                        "raw": {
                            "doc_id":          doc_id,
                            "fecha_cierre":    fecha_iso,
                            "dias_restantes":  dias,
                            "estado":          estado,
                            "event_type":      event_type,
                            "tipo":            "ariba_codelco"
                        }
                    })

                except Exception as e:
                    print(f"[ariba] Error fila: {e}")
                    continue

        except Exception as e:
            print(f"[ariba] Error general: {type(e).__name__}: {e}")
        finally:
            browser.close()

    # Deduplicar
    seen, unique = set(), []
    for item in items:
        key = item.get("entry", item["title"][:60])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    print(f"[ariba] {len(unique)} licitaciones extraídas")
    return unique[:limit]


if __name__ == "__main__":
    for i in fetch_ariba(50)[:10]:
        print(f"  [{i['score']}] {i['title'][:70]} | {i.get('entry','')} | dias: {i['raw'].get('dias_restantes')}")
