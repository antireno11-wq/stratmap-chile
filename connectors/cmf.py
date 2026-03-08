"""
connectors/cmf.py — Hechos Esenciales CMF (Comisión para el Mercado Financiero)
=================================================================================
Extrae hechos esenciales de empresas mineras que cotizan en bolsa.
Son anuncios materiales que las empresas están obligadas a publicar:
inversiones, proyectos, contratos, CAPEX, cambios de estrategia.

Estos son señales tempranas SEMANAS antes que aparezcan en SEA o noticias.

Fuentes:
  - API pública CMF: https://api.cmfchile.cl/api-sbifv3/recursos/v1/
  - Portal web CMF: https://www.cmfchile.cl/

Empresas mineras monitoreadas (las que cotizan en bolsa):
  SQM, Antofagasta Minerals (ANTO), CAP, Compañía Minera Atacocha,
  Lundin, Kinross, Teck, Barrick (ADR), Gold Fields, Capstone.
"""

import requests
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Empresas mineras con presencia en Chile que reportan a CMF o bolsas públicas
MINING_RUTS_CMF = {
    # RUT → nombre canónico
    "90.430.000-0": "SQM",
    "93.775.000-3": "CAP",
    "77.144.000-5": "Antofagasta Minerals",
    "79.758.000-2": "Minera Escondida (BHP)",
    "96.625.000-7": "Codelco",
    "76.362.771-5": "Collahuasi",
}

# Keywords mineros para filtrar hechos esenciales relevantes
MINING_KEYWORDS = [
    "mina", "minera", "minería", "cobre", "litio", "oro", "plata",
    "proyecto", "inversión", "capex", "construcción", "ampliación",
    "expansión", "contrato", "licitación", "epc", "epcm",
    "exploración", "yacimiento", "faena", "planta",
    "codelco", "bhp", "sqm", "collahuasi", "antofagasta",
    "escondida", "teck", "kinross", "barrick", "lundin",
]

CMF_API_BASE = "https://api.cmfchile.cl/api-sbifv3/recursos/v1"
CMF_HE_URL   = "https://www.cmfchile.cl/sitio/apii/hechos_esenciales.php"
HEADERS = {
    "User-Agent": "StratmapWorker/0.3 (inteligencia-comercial-mineria)",
    "Accept": "application/json",
}


def _is_mining_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in MINING_KEYWORDS)


def _parse_inversion(text: str) -> float | None:
    """Intenta extraer monto de inversión del texto del hecho esencial."""
    patterns = [
        r"([\d,.]+)\s*(?:millon|millón|millones?)\s*(?:de\s*)?(?:dólar|dollar|usd|us\$)",
        r"usd?\s*\$?\s*([\d,.]+)\s*(?:mm|m|mill)",
        r"([\d,.]+)\s*(?:musd|mmusd|mm\s*usd)",
    ]
    for pat in patterns:
        m = re.search(pat, text.lower())
        if m:
            try:
                raw_num = m.group(1).replace(",", "").replace(".", "")
                return float(raw_num) * 1_000_000  # asumir millones → USD
            except Exception:
                pass
    return None


def fetch_cmf_hechos_esenciales() -> List[Dict[str, Any]]:
    """
    Obtiene hechos esenciales de empresas mineras desde la API pública CMF.
    Prueba múltiples endpoints conocidos con fallback.
    """
    out = []

    # Endpoint 1: API pública moderna CMF
    try:
        resp = requests.get(
            CMF_HE_URL,
            params={"formato": "json", "cantidad": 200},
            headers=HEADERS,
            timeout=20,
            verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data if isinstance(data, list) else data.get("hechos_esenciales", data.get("items", []))
            for item in items:
                titulo  = str(item.get("titulo") or item.get("title") or item.get("nombre") or "")
                cuerpo  = str(item.get("cuerpo") or item.get("body") or item.get("descripcion") or "")
                empresa = str(item.get("empresa") or item.get("emisor") or item.get("company") or "")
                fecha   = item.get("fecha") or item.get("date") or item.get("fecha_envio")
                url     = str(item.get("url") or item.get("link") or "https://www.cmfchile.cl/hechos-esenciales")
                text    = titulo + " " + cuerpo + " " + empresa

                if not titulo or not _is_mining_relevant(text):
                    continue

                inversion = _parse_inversion(text)
                out.append({
                    "source": "CMF",
                    "title": titulo[:500],
                    "url": url,
                    "company": empresa or None,
                    "contractor": None,
                    "industry": "Minería",
                    "region": None,
                    "phase": "Hecho Esencial",
                    "score": 0,  # recalc_all_scores lo va a calcular
                    "entry": str(item.get("id") or item.get("codigo") or ""),
                    "raw": {
                        "body": cuerpo[:1000],
                        "fecha": str(fecha) if fecha else None,
                        "INVERSION_US": inversion,
                        "tipo": "hecho_esencial",
                    },
                    "published_at": _parse_date(fecha),
                })
            if out:
                logger.info(f"[cmf] {len(out)} hechos esenciales mineros desde endpoint principal")
                return out
    except Exception as e:
        logger.warning(f"[cmf] Endpoint principal falló: {e}")

    # Endpoint 2: RSS CMF (fallback más robusto)
    rss_urls = [
        "https://www.cmfchile.cl/web/feed/",
        "https://www.cmfchile.cl/sitio/rss/hechos_esenciales.xml",
    ]
    for rss_url in rss_urls:
        try:
            import xml.etree.ElementTree as ET
            resp = requests.get(rss_url, headers=HEADERS, timeout=15, verify=False)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                titulo = (item.findtext("title") or "").strip()
                desc   = (item.findtext("description") or "").strip()
                link   = (item.findtext("link") or "").strip()
                date_s = item.findtext("pubDate") or item.findtext("dc:date") or ""
                text   = titulo + " " + desc

                if not titulo or not _is_mining_relevant(text):
                    continue

                inversion = _parse_inversion(text)
                out.append({
                    "source": "CMF",
                    "title": titulo[:500],
                    "url": link or "https://www.cmfchile.cl",
                    "company": _extract_company(titulo),
                    "contractor": None,
                    "industry": "Minería",
                    "region": None,
                    "phase": "Hecho Esencial",
                    "score": 0,
                    "entry": link,
                    "raw": {
                        "body": desc[:1000],
                        "fecha": date_s,
                        "INVERSION_US": inversion,
                        "tipo": "hecho_esencial",
                    },
                    "published_at": _parse_date(date_s),
                })
            if out:
                logger.info(f"[cmf] {len(out)} hechos desde RSS {rss_url}")
                return out
        except Exception as e:
            logger.warning(f"[cmf] RSS {rss_url} falló: {e}")

    logger.warning("[cmf] Todos los endpoints fallaron — sin datos")
    return out


_COMPANY_PATTERNS = [
    ("sqm", "SQM"), ("codelco", "Codelco"), ("bhp", "BHP"),
    ("escondida", "Minera Escondida"), ("collahuasi", "Collahuasi"),
    ("antofagasta", "Antofagasta Minerals"), ("teck", "Teck"),
    ("kinross", "Kinross"), ("barrick", "Barrick"), ("cap ", "CAP"),
    ("lundin", "Lundin Mining"), ("capstone", "Capstone Copper"),
    ("angloamerican", "Anglo American"), ("anglo american", "Anglo American"),
]


def _extract_company(text: str) -> str | None:
    t = text.lower()
    for kw, name in _COMPANY_PATTERNS:
        if kw in t:
            return name
    return None


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y",
                        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def fetch_cmf(limit: int = 200) -> List[Dict[str, Any]]:
    items = fetch_cmf_hechos_esenciales()
    logger.info(f"[cmf] total: {len(items)} hechos esenciales mineros")
    return items[:limit]
