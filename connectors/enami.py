"""
connectors/enami.py
Scraper de licitaciones de ENAMI.
Fuente: https://www.enami.cl/Contratistas-y-Proveedores/Pages/default.aspx#/tabs3
Usa Playwright + intercepción de API SharePoint (AngularJS).
"""

import re
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
BASE_URL = "https://www.enami.cl"
URL = "https://www.enami.cl/Contratistas-y-Proveedores/Pages/default.aspx#/tabs3"

SCORE_KEYWORDS = {
    "construcción": 8, "montaje": 8, "obras": 6,
    "servicio": 5, "mantención": 7, "mantenimiento": 7,
    "suministro": 5, "reparación": 6, "ingeniería": 7,
    "planta": 6, "mina": 7, "eléctric": 6,
}

DIVISION_REGION = {
    "atacama": "Atacama", "coquimbo": "Coquimbo",
    "valparaíso": "Valparaíso", "valparaiso": "Valparaíso",
    "o'higgins": "O'Higgins", "ohiggins": "O'Higgins",
    "metropolitana": "Metropolitana", "antofagasta": "Antofagasta",
}


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=TZ)
            return dt.isoformat()
        except ValueError:
            pass
    # ISO format
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=TZ)
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
    base = 68
    t = title.lower()
    for kw, pts in SCORE_KEYWORDS.items():
        if kw in t:
            base += pts
    return min(base, 92)


def parse_sharepoint_items(data: dict) -> List[Dict]:
    """Parsea respuesta JSON de SharePoint REST API."""
    items = []
    rows = []

    # Formato OData v3/v4
    if "d" in data and "results" in data.get("d", {}):
        rows = data["d"]["results"]
    elif "value" in data:
        rows = data["value"]

    cutoff = (datetime.now(tz=TZ) - timedelta(days=90)).isoformat()

    for row in rows:
        title = (
            row.get("Title") or row.get("Titulo") or
            row.get("NombreLicitacion") or row.get("Nombre") or ""
        )
        if not title or len(title) < 5:
            continue

        # Fecha
        date_raw = (
            row.get("FechaPublicacion") or row.get("Created") or
            row.get("Modified") or row.get("Fecha") or ""
        )
        date_iso = parse_date(str(date_raw)) if date_raw else None

        # Filtrar antiguos
        if date_iso and date_iso < cutoff:
            continue

        url_doc = row.get("UrlDocumento") or row.get("Url") or row.get("FileRef") or URL
        if url_doc and url_doc.startswith("/"):
            url_doc = BASE_URL + url_doc

        region = parse_region(str(row))
        score = score_licitacion(title)

        items.append({
            "source": "ENAMI",
            "title": title[:400],
            "url": url_doc,
            "company": "ENAMI",
            "contractor": None,
            "industry": "Minería",
            "region": region,
            "phase": "Licitación",
            "score": score,
            "entry": str(row)[:300],
            "published_at": date_iso,
            "raw": {"tipo": "enami_licitacion", "raw_row": str(row)[:200]}
        })

    return items


def parse_xml_rows(rows_xml) -> List[Dict]:
    """Parsea filas XML de SharePoint Lists.asmx SOAP response."""
    items = []
    cutoff = (datetime.now(tz=TZ) - timedelta(days=90)).isoformat()

    for row in rows_xml:
        attrs = row.attrib
        # Buscar título en atributos comunes de SharePoint
        title = (
            attrs.get("ows_Title") or attrs.get("ows_Nombre") or
            attrs.get("ows_NombreLicitacion") or attrs.get("ows_LinkTitle") or
            attrs.get("ows_FileLeafRef") or ""
        )
        if not title or len(title) < 5:
            continue

        # Fecha
        date_raw = (
            attrs.get("ows_FechaPublicacion") or attrs.get("ows_Created") or
            attrs.get("ows_Modified") or attrs.get("ows_Fecha") or
            attrs.get("ows_FechaCierre") or ""
        )
        date_iso = parse_date(str(date_raw)) if date_raw else None
        if date_iso and date_iso < cutoff:
            continue

        # URL documento
        url_doc = attrs.get("ows_FileRef") or attrs.get("ows_Url") or URL
        if url_doc and url_doc.startswith("/"):
            url_doc = BASE_URL + url_doc.split(";#")[-1]  # SharePoint usa ;# como separador

        region = parse_region(str(attrs))
        score = score_licitacion(title)

        items.append({
            "source": "ENAMI",
            "title": title[:400],
            "url": url_doc,
            "company": "ENAMI",
            "contractor": None,
            "industry": "Minería",
            "region": region,
            "phase": "Licitación",
            "score": score,
            "entry": str(attrs)[:300],
            "published_at": date_iso,
            "raw": {"tipo": "enami_licitacion"}
        })

    return items


def fetch_enami(limit: int = 100) -> List[Dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[enami] Playwright no instalado")
        return []

    items = []
    api_data_found = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        # Interceptar respuestas de red
        def handle_response(response):
            url_r = response.url
            if any(x in url_r for x in ["_api/web/lists", "_vti_bin", "GetItems", "listdata.svc"]):
                try:
                    body = response.text()
                    if len(body) > 200 and ("{" in body or "<entry" in body):
                        api_data_found.append({"url": url_r, "body": body})
                        print(f"[enami] API capturada: {url_r[:100]}")
                except:
                    pass

        page.on("response", handle_response)

        try:
            print("[enami] Cargando página...")
            page.goto(URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(8000)  # Esperar Angular

            # Click en LICITACIONES
            try:
                lic_tab = page.query_selector("a:has-text('LICITACIONES')")
                if lic_tab:
                    lic_tab.click()
                    print("[enami] Click en LICITACIONES")
                    page.wait_for_timeout(8000)
            except Exception as ce:
                print(f"[enami] error click: {ce}")

            print(f"[enami] APIs capturadas: {len(api_data_found)}")

            # Procesar datos de API — SOAP/XML
            for api in api_data_found:
                try:
                    body = api["body"]
                    print(f"[enami] body snippet: {body[:300]}")
                    # Parsear XML SOAP
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(body)
                    # Buscar elementos z:row o row en cualquier namespace
                    ns = {'z': 'urn:schemas-microsoft-com:rowset', 's': 'uuid:BDC6E3F0-6DA3-11d1-A2A3-00AA00C14882'}
                    rows_xml = root.findall('.//{urn:schemas-microsoft-com:rowset}row') or                                root.findall('.//row') or                                root.findall('.//{#RowsetSchema}row')
                    print(f"[enami] XML rows encontrados: {len(rows_xml)}")
                    if rows_xml:
                        print(f"[enami] primer row attrs: {list(rows_xml[0].attrib.keys())[:10]}")
                    parsed = parse_xml_rows(rows_xml)
                    if parsed:
                        print(f"[enami] {len(parsed)} items parseados")
                        items.extend(parsed)
                except Exception as je:
                    print(f"[enami] error parse XML: {je}")
                    import traceback; traceback.print_exc()

            # Si no obtuvimos nada via API, intentar leer DOM
            if not items:
                print("[enami] Sin datos de API, intentando DOM...")
                # Esperar más para Angular
                page.wait_for_timeout(5000)

                # Extraer texto visible del área de licitaciones
                try:
                    # Buscar ng-repeat renderizado
                    ng_items = page.query_selector_all("[ng-repeat], [data-ng-repeat]")
                    print(f"[enami] ng-repeat: {len(ng_items)}")

                    # Buscar tabla renderizada por Angular
                    rows = page.query_selector_all("table tbody tr")
                    print(f"[enami] filas tabla: {len(rows)}")
                    if rows:
                        for row in rows[:limit]:
                            cells = row.query_selector_all("td")
                            if len(cells) < 2:
                                continue
                            full = row.inner_text().strip()
                            link_el = row.query_selector("a")
                            title = link_el.inner_text().strip() if link_el else cells[0].inner_text().strip()
                            href = link_el.get_attribute("href") if link_el else None
                            url_item = (BASE_URL + href if href and href.startswith("/") else href) or URL
                            date_iso = parse_date(full)
                            region = parse_region(full)
                            if not title or len(title) < 5:
                                continue
                            items.append({
                                "source": "ENAMI",
                                "title": title[:400],
                                "url": url_item,
                                "company": "ENAMI",
                                "contractor": None,
                                "industry": "Minería",
                                "region": region,
                                "phase": "Licitación",
                                "score": score_licitacion(title),
                                "entry": full[:300],
                                "published_at": date_iso,
                                "raw": {"tipo": "enami_licitacion"}
                            })

                    # Debug final
                    if not items:
                        section = page.evaluate(
                            "document.querySelector('[ng-controller],[ng-app],#tabs3,.tab-pane.active') ? "
                            "document.querySelector('[ng-controller],[ng-app],#tabs3,.tab-pane.active').innerText.substring(0,800) : "
                            "'NO SECTION'"
                        )
                        print(f"[enami] DEBUG section: {section}")

                except Exception as de:
                    print(f"[enami] DOM error: {de}")

        except Exception as e:
            print(f"[enami] Error general: {e}")
        finally:
            browser.close()

    print(f"[enami] {len(items)} licitaciones extraídas")
    return items[:limit]


if __name__ == "__main__":
    items = fetch_enami()
    for i in items[:10]:
        print(f"  [{i['score']}] {i['title'][:60]} | {i['region']} | {i.get('published_at','sin fecha')}")
