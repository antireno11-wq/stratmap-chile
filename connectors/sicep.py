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

            # Navegar a lista si no estamos ya ahí
            if "listaPublicacion" not in page.url:
                page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)

            # Scroll para cargar más items (lista infinita)
            print("[sicep] Cargando lista de publicaciones...")
            last_count = 0
            scroll_attempts = 0
            max_scrolls = 15

            while scroll_attempts < max_scrolls:
                cards = page.query_selector_all(".publicacion-item, .list-group-item, [class*='publicacion'], [class*='licitacion']")
                if not cards:
                    # Fallback — buscar divs con el patrón visual
                    cards = page.query_selector_all("div.panel, div.card, li.list-item")

                current_count = len(cards)
                if current_count >= limit or current_count == last_count:
                    break

                last_count = current_count
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                scroll_attempts += 1

            print(f"[sicep] {len(cards)} tarjetas encontradas")

            # DEBUG — imprimir HTML de primera tarjeta para entender estructura
            if cards:
                try:
                    html = cards[0].evaluate("el => el.outerHTML")
                    print(f"[sicep] DEBUG primera tarjeta HTML: {html[:800]}")
                    txt = cards[0].inner_text()
                    print(f"[sicep] DEBUG texto: {repr(txt[:300])}")
                except Exception as de:
                    print(f"[sicep] DEBUG error: {de}")

            # Parsear cada tarjeta
            for card in cards[:limit]:
                try:
                    # DEBUG — ver todo el texto de la tarjeta
                    try:
                        full_debug = card.inner_text()
                        html_debug = card.evaluate("el => el.outerHTML")
                        print(f"[sicep] CARD texto: {repr(full_debug[:200])}")
                        print(f"[sicep] CARD html: {html_debug[:400]}")
                    except:
                        pass

                    # Título — intentar todos los elementos posibles
                    title_el = (
                        card.query_selector("a[href*='detalle'], a[href*='publicacion']") or
                        card.query_selector("h3, h4, h5, .titulo, [class*='title']") or
                        card.query_selector(".card-title, .panel-title, strong") or
                        card.query_selector("a") or
                        card.query_selector("span")
                    )
                    title = title_el.inner_text().strip() if title_el else card.inner_text().strip()[:200]
                    title = re.sub(r'\(Clic para ver detalles\)', '', title, flags=re.IGNORECASE).strip()
                    if not title or len(title) < 5:
                        continue

                    # URL del detalle
                    href = title_el.get_attribute("href") if title_el else None
                    url = f"https://www.sistemasicep.cl{href}" if href and href.startswith("/") else (href or LOGIN_URL)

                    # Texto completo de la tarjeta
                    full_text = card.inner_text()

                    # Descripción
                    desc_el = card.query_selector("p, .descripcion, [class*='desc']")
                    description = desc_el.inner_text().strip()[:300] if desc_el else ""

                    # Mandante — buscar "Publicado por X"
                    mandante_raw = ""
                    m = re.search(r'por\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ\s]+?)(?:\s+\d|\s*-|\s*·|$)', full_text)
                    if m:
                        mandante_raw = m.group(1).strip()
                    mandante = normalize_mandante(mandante_raw)

                    # Categoría (badge de color)
                    cat_el = card.query_selector("[class*='badge'], [class*='label'], [class*='categoria'], [class*='rubro']")
                    category = cat_el.inner_text().strip() if cat_el else ""

                    # Tipo: Licitación / Oportunidad de negocio
                    phase = "Licitación"
                    if "oportunidad de negocio" in full_text.lower():
                        phase = "Oportunidad de negocio"
                    elif "licitación" in full_text.lower():
                        phase = "Licitación"

                    # Estado: NUEVO / FINALIZADO
                    is_new = "+ nuevo" in full_text.lower()
                    is_done = "finalizado" in full_text.lower()
                    if is_done:
                        phase = f"{phase} (Finalizada)"

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
