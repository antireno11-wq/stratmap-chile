"""
connectors/enami.py
Scraper de licitaciones de ENAMI.
Fuente: https://www.enami.cl/Contratistas-y-Proveedores/Pages/default.aspx#/tabs3
Usa Playwright porque es una SPA.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
BASE_URL = "https://www.enami.cl"
URL = "https://www.enami.cl/Contratistas-y-Proveedores/Pages/default.aspx#/tabs3"

SCORE_KEYWORDS = {
    "construcción": 8, "montaje": 8, "obras": 6,
    "servicio": 5, "mantención": 7, "mantenimiento": 7,
    "operación": 5, "suministro": 5, "reparación": 6,
    "ingeniería": 7, "planta": 6, "mina": 7,
    "eléctric": 6, "instrumentación": 6,
}

DIVISION_REGION = {
    "atacama":       "Atacama",
    "coquimbo":      "Coquimbo",
    "valparaíso":    "Valparaíso",
    "o'higgins":     "O'Higgins",
    "metropolitana": "Metropolitana",
    "antofagasta":   "Antofagasta",
}


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    # DD/MM/YYYY
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=TZ)
            return dt.isoformat()
        except ValueError:
            pass
    return None


def parse_region(text: str) -> Optional[str]:
    t = text.lower()
    for k, v in DIVISION_REGION.items():
        if k in t:
            return v
    return None


def score_licitacion(title: str) -> int:
    base = 68  # ENAMI fuente premium
    t = title.lower()
    for kw, pts in SCORE_KEYWORDS.items():
        if kw in t:
            base += pts
    return min(base, 92)


def fetch_enami(limit: int = 100) -> List[Dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[enami] Playwright no instalado — saltando")
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
            print("[enami] Cargando página...")
            # Ir primero a la página base
            page.goto("https://www.enami.cl/Contratistas-y-Proveedores/Pages/default.aspx", 
                      wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(3000)

            # Click en el tab LICITACIONES
            try:
                lic_tab = (
                    page.query_selector("a:has-text('LICITACIONES')") or
                    page.query_selector("[href*='tabs3']") or
                    page.query_selector("a[href*='licitacion' i]")
                )
                if lic_tab:
                    lic_tab.click()
                    print("[enami] Click en tab LICITACIONES")
                    page.wait_for_timeout(5000)
                else:
                    print("[enami] Tab no encontrado, intentando URL directa con hash")
                    page.evaluate("window.location.hash = '#/tabs3'")
                    page.wait_for_timeout(5000)
            except Exception as ce:
                print(f"[enami] error click tab: {ce}")

            print(f"[enami] URL actual: {page.url}")

            # Esperar que aparezca contenido de licitaciones
            try:
                page.wait_for_selector("table, [class*='licit'], iframe", timeout=15000)
            except:
                pass
            page.wait_for_timeout(3000)

            # Verificar si hay iframe con el contenido
            iframes = page.query_selector_all("iframe")
            print(f"[enami] iframes: {len(iframes)}")

            # DEBUG
            try:
                html_snippet = page.evaluate("document.body.innerHTML.substring(0, 2000)")
                print(f"[enami] DEBUG body: {html_snippet}")
            except Exception as de:
                print(f"[enami] debug error: {de}")

            # Intentar extraer tabla de licitaciones
            rows = page.query_selector_all("table tr")
            if not rows:
                rows = page.query_selector_all("[class*='licit'], [class*='item-licit']")

            print(f"[enami] {len(rows)} filas encontradas")

            seen_titles = set()
            for row in rows[1:limit+1]:  # Skip header
                try:
                    cells = row.query_selector_all("td")
                    if not cells or len(cells) < 2:
                        continue

                    # Extraer campos típicos de tabla de licitaciones
                    full_text = row.inner_text().strip()
                    if not full_text or len(full_text) < 10:
                        continue

                    # Buscar link
                    link_el = row.query_selector("a")
                    title = link_el.inner_text().strip() if link_el else cells[0].inner_text().strip()
                    href = link_el.get_attribute("href") if link_el else None
                    url = (BASE_URL + href if href and href.startswith("/") else href) or URL

                    if not title or len(title) < 5 or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    # Fecha (buscar en celdas)
                    date_iso = None
                    for cell in cells:
                        txt = cell.inner_text().strip()
                        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', txt):
                            date_iso = parse_date(txt)
                            break

                    region = parse_region(full_text)
                    score = score_licitacion(title)

                    # Solo últimos 3 meses
                    if date_iso:
                        cutoff = (datetime.now(tz=TZ) - timedelta(days=90)).isoformat()
                        if date_iso < cutoff:
                            print(f"[enami] Fecha {date_iso} muy antigua — deteniendo")
                            items = items  # Keep what we have
                            break

                    items.append({
                        "source": "ENAMI",
                        "title": title[:400],
                        "url": url,
                        "company": "ENAMI",
                        "contractor": None,
                        "industry": "Minería",
                        "region": region,
                        "phase": "Licitación",
                        "score": score,
                        "entry": full_text[:300],
                        "published_at": date_iso,
                        "raw": {"tipo": "enami_licitacion"}
                    })

                except Exception:
                    continue

        except Exception as e:
            print(f"[enami] Error: {e}")
        finally:
            browser.close()

    print(f"[enami] {len(items)} licitaciones extraídas")
    return items


if __name__ == "__main__":
    items = fetch_enami()
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i['region']} | {i.get('published_at','sin fecha')}")
