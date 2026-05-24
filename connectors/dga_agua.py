"""
connectors/dga_agua.py — Catastro Público de Aguas (CPA) de la DGA.
=================================================================
La Dirección General de Aguas publica los DERECHOS DE APROVECHAMIENTO
otorgados. Para una empresa minera, pedir derechos de agua es señal
TEMPRANA (6-18 meses antes que aparezca en SEA) de que un proyecto está
armándose: sin agua no hay faena minera.

Estrategia de endpoints (probamos en orden, primero que responda gana):
  1. ArcGIS REST público de DGA (FeatureServer del CPA)
  2. datos.gob.cl CKAN datastore (mirror oficial)
  3. SNIA portal (último recurso, scrape simple)

Si ninguno responde, devuelve [] — @track_run lo marca como 'empty' en
/health.html (no 'error'), porque está esperado que algunos endpoints
caigan o cambien con el tiempo. Cuando confirmemos un endpoint estable
en producción, se borran los demás.

Filtramos a derechos asociados a sector minero/industrial buscando
keywords en el USO declarado: 'MINER', 'INDUSTR', 'BENEFICIO MINERAL'.
"""
from __future__ import annotations

import logging
import re
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Stratmap/1.0)",
    "Accept": "application/json",
}

# Endpoints candidatos en orden de preferencia. Si DGA publica uno nuevo
# en el futuro, agregar arriba.
ARCGIS_ENDPOINTS = [
    # Catastro Público de Aguas — capa de derechos
    "https://services2.arcgis.com/IF18jJa50O3lUlT5/arcgis/rest/services/CPA_Derechos_Otorgados/FeatureServer/0",
    "https://services1.arcgis.com/dpqVUyTaPcLuKn4z/arcgis/rest/services/CPA/FeatureServer/0",
    "https://geoportal.dga.cl/arcgis/rest/services/CPA/CPA_Derechos/MapServer/0",
]

# CKAN dataset id de datos.gob.cl — DGA publica el CPA acá también.
CKAN_RESOURCE_IDS = [
    # ids reales se confirman vía https://datos.gob.cl/dataset?organization=dga
    # estos son placeholders típicos del patrón CKAN — primer match real gana.
    "cpa-derechos-otorgados",
    "catastro-publico-aguas",
]

REGION_LOOKUP = {
    "1": "Tarapacá", "2": "Antofagasta", "3": "Atacama", "4": "Coquimbo",
    "5": "Valparaíso", "6": "O'Higgins", "7": "Maule", "8": "Biobío",
    "9": "La Araucanía", "10": "Los Lagos", "11": "Aysén",
    "12": "Magallanes", "13": "Metropolitana", "14": "Los Ríos",
    "15": "Arica y Parinacota", "16": "Ñuble",
}

MINING_USE_KEYWORDS = re.compile(
    r"\b(miner|industr|beneficio\s*mineral|lixiviaci|concentrad|fund(ici|ido)|chancad|"
    r"plant[ao]\s*(de\s*)?(concentr|desalin|procesad)|riego\s*industr|enfri)",
    re.IGNORECASE,
)


def _looks_mining(uso: str, titular: str = "") -> bool:
    """Marca el derecho como minero si el USO o el TITULAR sugiere minería."""
    txt = f"{uso or ''} {titular or ''}"
    if MINING_USE_KEYWORDS.search(txt):
        return True
    # Empresas mineras conocidas en titular (heurística amplia)
    minera_re = re.compile(r"\b(codelco|enami|antofagasta|escondida|collahuasi|"
                           r"sqm|albemarle|lithium|los\s+pelambres|los\s+bronces|"
                           r"caserones|spence|barrick|teck|lundin|kinross|gold\s*fields|"
                           r"minera\b|cmp\b)", re.IGNORECASE)
    return bool(minera_re.search(titular or ""))


def _fetch_arcgis() -> List[Dict[str, Any]]:
    """Intenta cada endpoint ArcGIS. Primero que responde wins."""
    for base in ARCGIS_ENDPOINTS:
        try:
            r = requests.get(
                f"{base}/query",
                params={
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "false",
                    "resultRecordCount": 2000,
                    "f": "json",
                },
                headers=HEADERS, timeout=25,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            features = data.get("features", []) or []
            if not features:
                continue
            out = []
            for f in features:
                a = f.get("attributes", {}) or {}
                # ArcGIS de DGA usa nombres variables; normalizamos buscando
                # por keywords típicos.
                titular = (
                    a.get("TITULAR") or a.get("Titular") or a.get("Nombre_Titular")
                    or a.get("nombre_titular") or ""
                ).strip()
                uso = (
                    a.get("USO") or a.get("Uso") or a.get("Uso_Agua")
                    or a.get("USO_AGUA") or ""
                ).strip()
                region = (
                    a.get("REGION") or a.get("Region") or a.get("Cod_Region") or ""
                )
                fecha = (
                    a.get("FECHA_RESOLUCION") or a.get("Fecha_Resolucion")
                    or a.get("FECHA") or None
                )
                caudal = a.get("CAUDAL_L_S") or a.get("Caudal") or a.get("CAUDAL")

                if not titular:
                    continue
                if not _looks_mining(uso, titular):
                    continue

                out.append(_format_item(titular, uso, region, fecha, caudal, a, base))
            logger.info(f"[dga_agua] ArcGIS {base} → {len(out)} derechos mineros")
            if out:
                return out
        except Exception as e:
            logger.warning(f"[dga_agua] ArcGIS {base} falló: {e}")
            continue
    return []


def _fetch_ckan() -> List[Dict[str, Any]]:
    """Fallback: datos.gob.cl CKAN datastore."""
    for rid in CKAN_RESOURCE_IDS:
        try:
            r = requests.get(
                "https://datos.gob.cl/api/3/action/datastore_search",
                params={"resource_id": rid, "limit": 2000},
                headers=HEADERS, timeout=25,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            records = (data.get("result") or {}).get("records") or []
            if not records:
                continue
            out = []
            for rec in records:
                titular = rec.get("titular") or rec.get("nombre_titular") or ""
                uso = rec.get("uso") or rec.get("uso_agua") or ""
                if not titular or not _looks_mining(uso, titular):
                    continue
                out.append(_format_item(
                    titular, uso,
                    rec.get("region") or rec.get("cod_region") or "",
                    rec.get("fecha_resolucion") or rec.get("fecha"),
                    rec.get("caudal") or rec.get("caudal_l_s"),
                    rec, f"ckan:{rid}",
                ))
            logger.info(f"[dga_agua] CKAN {rid} → {len(out)} derechos mineros")
            if out:
                return out
        except Exception as e:
            logger.warning(f"[dga_agua] CKAN {rid} falló: {e}")
            continue
    return []


def _format_item(titular: str, uso: str, region, fecha, caudal, raw: dict,
                 source_url: str) -> Dict[str, Any]:
    region_name = REGION_LOOKUP.get(str(region).strip(), str(region or "").strip())
    caudal_str = f" · {caudal} l/s" if caudal else ""
    title = f"Derecho de agua: {titular} ({uso}){caudal_str}"[:400]
    fecha_iso = None
    if fecha:
        # ArcGIS suele dar epoch ms; CKAN da string ISO. Manejamos ambos.
        if isinstance(fecha, (int, float)) and fecha > 0:
            from datetime import datetime, timezone
            fecha_iso = datetime.fromtimestamp(fecha / 1000, tz=timezone.utc).isoformat()
        else:
            fecha_iso = str(fecha)
    return {
        "source":       "DGA Agua",
        "title":        title,
        "url":          "https://snia.mop.gob.cl/dgawebsite/Recursos-Hidricos/Catastro-Publico-de-Aguas",
        "company":      titular,
        "industry":     "Minería" if _looks_mining(uso, titular) else "Industrial",
        "region":       region_name or None,
        "phase":        "Derecho otorgado",
        "score":        65,
        "published_at": fecha_iso,
        "entry":        f"{titular} | {uso}{caudal_str} | {region_name}",
        "raw": {
            "titular":   titular,
            "uso":       uso,
            "caudal":    caudal,
            "region":    region_name,
            "fecha":     fecha,
            "_endpoint": source_url,
            "_raw":      raw,
        },
    }


def fetch_dga_agua(limit: int = 500) -> List[Dict[str, Any]]:
    """Catastro de derechos de agua otorgados, filtrado a uso minero/industrial.

    Devuelve [] si ningún endpoint responde — el sistema lo marca como
    'empty' en /health.html, no 'error'. Esto es esperado mientras los
    endpoints reales de DGA estén sin confirmar.
    """
    items = _fetch_arcgis()
    if not items:
        items = _fetch_ckan()
    if not items:
        logger.info("[dga_agua] Ningún endpoint respondió con datos mineros — devolviendo vacío.")
        return []
    return items[:limit]


if __name__ == "__main__":
    items = fetch_dga_agua(limit=20)
    print(f"Total: {len(items)} derechos de agua mineros")
    for it in items[:5]:
        print(f"  {it['company'][:30]:<30} | {it['region']:<15} | {it['title'][:60]}")
