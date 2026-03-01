"""
connectors/sicep.py
Scraper autenticado de SICEP usando Playwright.
Requiere variables de entorno: SICEP_USER, SICEP_PASS
"""

import os
import re
import time
from typing import Any, Dict, List, Optional

LOGIN_URL = "https://www.sistemasicep.cl/app/colaboradora/listaPublicacion"

CATEGORY_INDUSTRY = {
    "maquinaria": "Minería",
    "minería": "Minería",
    "minero": "Minería",
    "perforación": "Minería",
    "explosivos": "Minería",
    "chancado": "Minería",
    "concentradora": "Minería",
    "ingeniería eléctrica": "Energía",
    "eléctric": "Energía",
    "subestación": "Energía",
    "obras civiles": "Infraestructura",
    "construcción": "Infraestructura",
    "transporte": "Infraestructura",
    "logística": "Infraestructura",
}

MANDANTES_CONOCIDOS = {
    "sierra gorda": "Sierra Gorda SCM",
    "amsa": "Antofagasta Minerals",
    "antofagasta minerals": "Antofagasta Minerals",
    "centinela": "Minera Centinela",
    "escondida": "Minera Escondida",
    "bhp": "BHP",
    "collahuasi": "Compañía Minera Doña Inés de Collahuasi",
    "teck": "Teck Resources",
    "sqm": "SQM",
    "codelco": "Codelco",
    "pelambres": "Minera Los Pelambres",
    "zaldivar": "Minera Zaldívar",
    "kinross": "Kinross",
    "goldfields": "Gold Fields",
    "albemarle": "Albemarle",
    "engie": "Engie",
    "kghm": "KGHM",
}


def normalize_mandante(raw: str) -> str:
    if not raw:
        return raw
    lower = raw.lower().strip()
    for key, val in MANDANTES_CONOCIDOS.items():
        if key in lower:
            return val
    return raw.strip()


def classify_industry(category: str, title: str) -> str:
    text = f"{category} {title}".lower()
    for kw, ind in CATEGORY_INDUSTRY.items():
        if kw in text:
            return ind
    return "Minería"  # SICEP es 100% minería/industria


def score_sicep(title: str, category: str, phase: str, dias_restantes: Optional[int]) -> int:
    base = 60  # SICEP es fuente premium — licitaciones directas de mineras

    # Tipo
    if "licitación" in phase.lower():
        base += 15
    elif "oportunidad" in phase.lower():
        base += 10

    # Urgencia
    if dias_restantes is not None:
        if dias_restantes <= 3:
            base += 10
        elif dias_restantes <= 7:
            base += 5

    # Keywords de alto valor
    t = f"{title} {category}".lower()
    if any(k in t for k in ["adquisición", "compra", "suministro", "contrato"]):
        base += 8
    if any(k in t for k in ["nuevo", "ampliación", "nueva planta"]):
        base += 5

    return min(base, 95)


def parse_dias(texto: str) -> Optional[int]:
    """Extrae días restantes de texto como 'Finaliza en 3 días'."""
    m = re.search(r'finaliza en (\d+) día', texto, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if "finalizado" in texto.lower():
        return -1
    return None


def fetch_sicep(limit: int = 200) -> List[Dict[str, Any]]:
    user = os.getenv("SICEP_USER", "")
    password = os.getenv("SICEP_PASS", "")

    if not user or not password:
        print("[sicep] SICEP_USER o SICEP_PASS no configurados — saltando")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[sicep] Playwright no instalado — saltando")
        return []

    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            print("[sicep] Abriendo página de login...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # Login — buscar campos de usuario y contraseña
            # SICEP usa inputs con name="j_username" y "j_password" o similar
            user_input = (
                page.query_selector("input[name='j_username']") or
                page.query_selector("input[type='text']") or
                page.query_selector("input[placeholder*='suar' i]") or
                page.query_selector("input[placeholder*='user' i]")
            )
            pass_input = (
                page.query_selector("input[name='j_password']") or
                page.query_selector("input[type='password']")
            )

            if not user_input or not pass_input:
                print("[sicep] No se encontraron campos de login")
                browser.close()
                return []

            user_input.fill(user)
            pass_input.fill(password)

            # Buscar botón de login
            login_btn = (
                page.query_selector("button[type='submit']") or
                page.query_selector("input[type='submit']") or
                page.query_selector("a:has-text('Ingresar')") or
                page.query_selector("button:has-text('Ingresar')")
            )
            if login_btn:
                login_btn.click()
            else:
                page.keyboard.press("Enter")

            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle", timeout=20000)

            print(f"[sicep] Logueado, URL actual: {page.url}")

            # Navegar a la página de licitaciones via menú
            print(f"[sicep] Navegando a lista de publicaciones...")
            # Intentar ir directamente a la URL de lista
            list_urls = [
                "https://www.sistemasicep.cl/app/colaboradora/listaPublicacion",
                "https://www.sistemasicep.cl/app/colaboradora/licitaciones",
                "https://www.sistemasicep.cl/app/colaboradora/informacionLicitaciones",
            ]
            navigated = False
            for list_url in list_urls:
                try:
                    page.goto(list_url, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(2000)
                    print(f"[sicep] URL actual: {page.url}")
                    if "404" not in page.url and page.url != "about:blank":
                        navigated = True
                        break
                except:
                    continue
            
            if not navigated:
                # Click en el menú LICITACIONES → Información de Licitaciones
                try:
                    lic_menu = page.query_selector("a:has-text('LICITACIONES'), a:has-text('Información de Licitaciones')")
                    if lic_menu:
                        lic_menu.click()
                        page.wait_for_timeout(2000)
                        print(f"[sicep] URL tras click menú: {page.url}")
                except Exception as me:
                    print(f"[sicep] error menú: {me}")

            # SICEP es una SPA — la lista de licitaciones está en el sidebar izquierdo
            # Al hacer click en cada item, el detalle aparece en el panel derecho
            print("[sicep] Cargando lista de publicaciones...")
            page.wait_for_timeout(3000)

            page.wait_for_timeout(3000)
            
            # DEBUG — ver URL actual y estructura
            print(f"[sicep] URL de lista: {page.url}")
            try:
                # Ver todos los links en la página
                links = page.evaluate("Array.from(document.querySelectorAll('a[href]')).map(a => a.href + ' | ' + a.innerText.trim().substring(0,50)).filter(s => s.length > 5)")
                print(f"[sicep] Links encontrados: {links[:15]}")
                
                # Ver tablas
                tables = page.query_selector_all("table")
                print(f"[sicep] Tablas: {len(tables)}")
                if tables:
                    html = tables[0].evaluate("el => el.outerHTML")
                    print(f"[sicep] Primera tabla: {html[:500]}")
            except Exception as de:
                print(f"[sicep] debug error: {de}")

            # Buscar filas de tabla (estructura más común en portales gubernamentales)
            rows = page.query_selector_all("table tbody tr, table tr")
            clickable = [r for r in rows if len(r.inner_text().strip()) > 20]
            print(f"[sicep] {len(clickable)} licitaciones en lista")

            seen_titles = set()
            for item in clickable[:limit]:
                try:
                    # Click en el item para cargar su detalle
                    item.click()
                    page.wait_for_timeout(1500)

                    # Leer el panel de detalle (IDs fijos del HTML)
                    title = page.evaluate("document.getElementById('lblTituloOperacionDetallePublicacion')?.innerText || ''")
                    if not title:
                        # Fallback — leer texto del item mismo
                        title = item.inner_text().strip()[:200]
                    title = title.strip()
                    if not title or len(title) < 5 or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    categoria = page.evaluate("document.getElementById('lblCategoriaDetallePublicacion')?.innerText || ''")
                    ciudad = page.evaluate("document.getElementById('lblCiudadDetallePublicacion')?.innerText || ''")
                    fecha_cierre = page.evaluate("document.getElementById('lblFechaCierreDetallePublicacion')?.innerText || ''")
                    fecha_pub = page.evaluate("document.getElementById('lblFechaPublicacionDetallePublicacion')?.innerText || ''")
                    mandante_raw = page.evaluate("document.getElementById('lblOperacionDetallePublicacion')?.innerText || ''")

                    # URL del detalle
                    url = page.url or LOGIN_URL

                    mandante = normalize_mandante(mandante_raw)
                    category = categoria.strip() if categoria else ""
                    phase = "Licitación"

                    full_text = f"{title} {ciudad} {categoria} {mandante_raw}"
                    # Región
                    region = None
                    region_match = re.search(
                        r'(Antofagasta|Atacama|Coquimbo|Valparaíso|O\'Higgins|Maule|Biobío|'
                        r'Araucanía|Los Lagos|Aysén|Magallanes|Metropolitana|Tarapacá|'
                        r'Arica|Los Ríos|Ñuble)',
                        full_text, re.IGNORECASE
                    )
                    if region_match:
                        region = region_match.group(1)

                    # Días restantes
                    dias = parse_dias(full_text)

                    industry = classify_industry(category, title)
                    score = score_sicep(title, category, phase, dias)

                    items.append({
                        "source": "SICEP",
                        "title": title[:400],
                        "url": url,
                        "company": mandante or None,
                        "contractor": None,
                        "industry": industry,
                        "region": region,
                        "phase": phase,
                        "score": score,
                        "entry": description[:300] if description else None,
                        "raw": {
                            "category": category,
                            "dias_restantes": dias,
                            "is_new": is_new,
                            "mandante_raw": mandante_raw,
                            "tipo": "sicep"
                        }
                    })

                except Exception as e:
                    print(f"[sicep] Error parseando tarjeta: {e}")
                    continue

        except Exception as e:
            print(f"[sicep] Error general: {e}")
        finally:
            browser.close()

    # Deduplicar por título
    seen = set()
    unique = []
    for item in items:
        key = item["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    print(f"[sicep] {len(unique)} licitaciones extraídas")
    return unique[:limit]


if __name__ == "__main__":
    items = fetch_sicep(limit=50)
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:70]} | {i['company']} | {i['region']}")
