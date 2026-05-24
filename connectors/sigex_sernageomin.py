"""
Conector SIGEX – Sernageomin
============================
API: https://services1.arcgis.com/OyjvVdFTl5hfSdX3/arcgis/rest/services/Visor_SIGEX/FeatureServer/0

Campos confirmados:
  NOMBRE_PROYECTO  → título del proyecto de exploración
  TITULAR          → empresa titular de la concesión
  RUT_TITULAR      → RUT del titular
  REGION           → código REG_01..REG_16
  ESTADO           → EST_01 (En Evaluación) | EST_02 (Aprobado)
  TIPO_TRAMITE     → TT_01 (Prórroga) | TT_02 (Vencimiento) | TT_03 (Bienalidad)
  TIPO_RECURSO     → TR_01 (Metálicos) | TR_02 (Industriales) | TR_03 (Energéticos)
  RECURSO_CONCAT   → texto legible de minerales, ej: "Cu, Au, Ag"
  LATITUD/LONGITUD → coordenadas WGS84
  FECHA / Fecha_2  → fecha de ingreso al SIGEX
  ENLACE           → URL directa al expediente en Sernageomin

Nota: exceededTransferLimit=true, hay >2000 registros — se pagina de a 2000.
"""

import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

BASE_URL = "https://services1.arcgis.com/OyjvVdFTl5hfSdX3/arcgis/rest/services/Visor_SIGEX/FeatureServer/0"
DASHBOARD_URL = "https://www.arcgis.com/apps/dashboards/f47a3c43bb974de486313d2f15e70fda"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Stratmap/1.0)",
    "Accept": "application/json",
    "Referer": "https://www.arcgis.com/",
}

# ── Lookups de dominio ─────────────────────────────────────────────────────────
REGION_LOOKUP = {
    "REG_01": "Arica y Parinacota",
    "REG_02": "Tarapacá",
    "REG_03": "Antofagasta",
    "REG_04": "Atacama",
    "REG_05": "Coquimbo",
    "REG_06": "Valparaíso",
    "REG_07": "Metropolitana",
    "REG_08": "O'Higgins",
    "REG_09": "Maule",
    "REG_10": "Ñuble",
    "REG_11": "Biobío",
    "REG_12": "La Araucanía",
    "REG_13": "Los Ríos",
    "REG_14": "Los Lagos",
    "REG_15": "Aysén",
    "REG_16": "Magallanes",
}

ESTADO_LOOKUP = {
    "EST_01": "En Evaluación",
    "EST_02": "Aprobado",
}

TRAMITE_LOOKUP = {
    "TT_01": "Exploración (Prórroga)",
    "TT_02": "Exploración (Vencimiento)",
    "TT_03": "Bienalidad Explotación",
}

TIPO_RECURSO_LOOKUP = {
    "TR_01": "Metálicos",
    "TR_02": "Industriales",
    "TR_03": "Energéticos",
}

HIGH_VALUE_MINERALS = {"cu", "cobre", "li", "litio", "au", "oro", "mo", "molibdeno",
                       "ag", "plata", "co", "cobalto", "ni", "níquel", "niquel"}
MED_VALUE_MINERALS  = {"fe", "hierro", "zn", "zinc", "mn", "manganeso", "pb", "plomo"}


def score_item(recurso: str, tipo_recurso: str, estado: str, region: str) -> int:
    score = 55
    r = (recurso or "").lower()
    tr = (tipo_recurso or "").lower()
    estado_lower = (estado or "").lower()
    region_lower = (region or "").lower()

    if "aprobado" in estado_lower:
        score += 15
    elif "evaluación" in estado_lower or "evaluacion" in estado_lower:
        score += 8

    if any(m in r for m in HIGH_VALUE_MINERALS):
        score += 15
    elif any(m in r for m in MED_VALUE_MINERALS):
        score += 8

    if "energétic" in tr or "energetic" in tr:
        score -= 10

    if any(reg in region_lower for reg in ["antofagasta", "atacama", "tarapacá", "tarapaca", "coquimbo"]):
        score += 8

    return max(0, min(100, score))


def parse_fecha(fecha_str: str) -> Optional[str]:
    if not fecha_str:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(str(fecha_str).strip(), fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def fetch_page(offset: int, count: int = 2000, where: str = "1=1") -> Dict:
    params = {
        "where": where,
        "outFields": "OBJECTID,ID,NOMBRE_PROYECTO,TITULAR,RUT_TITULAR,REGION,ESTADO,"
                     "TIPO_TRAMITE,TIPO_RECURSO,RECURSO_CONCAT,LATITUD,LONGITUD,"
                     "FECHA,Fecha_2,ENLACE",
        "returnGeometry": "false",
        "resultOffset": offset,
        "resultRecordCount": count,
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }
    try:
        r = requests.get(f"{BASE_URL}/query", params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[sigex] Error en offset {offset}: {e}")
        return {}


def fetch_sigex(limit: int = 5000) -> List[Dict[str, Any]]:
    """Ingesta completa del SIGEX con paginación automática."""
    items = []
    offset = 0
    page_size = 2000

    while len(items) < limit:
        data = fetch_page(offset, min(page_size, limit - len(items)))
        features = data.get("features", [])

        if not features:
            print(f"[sigex] Sin más features en offset {offset}")
            break

        for feat in features:
            a = feat.get("attributes", {})

            nombre  = (a.get("NOMBRE_PROYECTO") or "").strip()
            titular = (a.get("TITULAR") or "").strip()
            if not nombre and not titular:
                continue

            region_code  = a.get("REGION") or ""
            estado_code  = a.get("ESTADO") or ""
            tramite_code = a.get("TIPO_TRAMITE") or ""
            tipo_rec     = a.get("TIPO_RECURSO") or ""
            recurso      = (a.get("RECURSO_CONCAT") or "").strip()

            region       = REGION_LOOKUP.get(region_code, region_code)
            estado       = ESTADO_LOOKUP.get(estado_code, estado_code)
            tramite      = TRAMITE_LOOKUP.get(tramite_code, tramite_code)
            tipo_rec_str = TIPO_RECURSO_LOOKUP.get(tipo_rec, tipo_rec)

            # Fecha — Fecha_2 es DateOnly "YYYY-MM-DD", más fiable
            fecha_iso = None
            fecha_2 = a.get("Fecha_2")
            if fecha_2:
                fecha_iso = parse_fecha(str(fecha_2))
            if not fecha_iso:
                fecha_iso = parse_fecha(a.get("FECHA") or "")

            enlace   = a.get("ENLACE") or DASHBOARD_URL
            sigex_id = a.get("ID") or ""

            minerales = f" [{recurso}]" if recurso else ""
            title = f"{nombre}{minerales}" if nombre else f"Exploración {titular}{minerales}"

            score = score_item(recurso, tipo_rec, estado, region)

            items.append({
                "source":       "SIGEX",
                "title":        title[:400],
                "url":          enlace,
                "company":      titular,
                "industry":     "Minería",
                "region":       region,
                "phase":        estado or "Concesión activa",
                "score":        score,
                "published_at": fecha_iso,
                "entry":        f"{nombre} | {titular} | {recurso} | {region} | {estado}",
                "raw": {
                    "sigex_id":     sigex_id,
                    "rut_titular":  a.get("RUT_TITULAR"),
                    "tipo_tramite": tramite,
                    "tipo_recurso": tipo_rec_str,
                    "recurso":      recurso,
                    "lat":          a.get("LATITUD"),
                    "lng":          a.get("LONGITUD"),
                    "estado_code":  estado_code,
                    "source_type":  "sigex_sernageomin",
                }
            })

        print(f"[sigex] offset={offset}: {len(features)} features, total acumulado={len(items)}")
        offset += len(features)

        if not data.get("exceededTransferLimit", False):
            break

    print(f"[sigex] Ingesta completa: {len(items)} proyectos SIGEX")
    return items[:limit]


def fetch_sigex_explotacion(limit: int = 2000) -> List[Dict[str, Any]]:
    """SIGEX filtrado a TIPO_TRAMITE='TT_03' (Bienalidad Explotación).

    Diferencia con fetch_sigex():
    - source = 'SIGEX Explotación' (no 'SIGEX'). Permite categorizarlo aparte
      del SIGEX general que fue retirado del pipeline.
    - Solo trae filas con trámite TT_03, que indica que la empresa está
      manteniendo activa una concesión de explotación (paga la bienalidad).
      Esto es señal de continuidad operacional — no de proyecto nuevo, pero
      sí confirma que el mandante tiene faena viva en esa región.

    Para concesiones NUEVAS de explotación (constituciones) la fuente real es
    el Boletín Oficial Minero (PDF mensual), no implementado.
    """
    items: List[Dict[str, Any]] = []
    offset = 0
    page_size = 2000
    where = "TIPO_TRAMITE='TT_03'"

    while len(items) < limit:
        data = fetch_page(offset, min(page_size, limit - len(items)), where=where)
        features = data.get("features", [])
        if not features:
            break

        for feat in features:
            a = feat.get("attributes", {})
            titular = (a.get("TITULAR") or "").strip()
            nombre  = (a.get("NOMBRE_PROYECTO") or "").strip()
            if not titular:
                continue

            region_code = a.get("REGION") or ""
            estado_code = a.get("ESTADO") or ""
            recurso     = (a.get("RECURSO_CONCAT") or "").strip()
            region      = REGION_LOOKUP.get(region_code, region_code)
            estado      = ESTADO_LOOKUP.get(estado_code, estado_code)

            fecha_iso = None
            fecha_2 = a.get("Fecha_2")
            if fecha_2:
                fecha_iso = parse_fecha(str(fecha_2))
            if not fecha_iso:
                fecha_iso = parse_fecha(a.get("FECHA") or "")

            enlace = a.get("ENLACE") or DASHBOARD_URL
            mineral_str = f" [{recurso}]" if recurso else ""
            title = f"Bienalidad explotación: {nombre or titular}{mineral_str}"

            items.append({
                "source":       "SIGEX Explotación",
                "title":        title[:400],
                "url":          enlace,
                "company":      titular,
                "industry":     "Minería",
                "region":       region,
                "phase":        "Explotación activa",
                "score":        50,
                "published_at": fecha_iso,
                "entry":        f"{titular} | bienalidad | {region} | {recurso}",
                "raw": {
                    "sigex_id":     a.get("ID"),
                    "rut_titular":  a.get("RUT_TITULAR"),
                    "tipo_tramite": "Bienalidad Explotación",
                    "recurso":      recurso,
                    "lat":          a.get("LATITUD"),
                    "lng":          a.get("LONGITUD"),
                    "source_type":  "sigex_explotacion",
                }
            })

        offset += len(features)
        if not data.get("exceededTransferLimit", False):
            break

    print(f"[sigex_explotacion] {len(items)} concesiones de explotación activas")
    return items[:limit]


if __name__ == "__main__":
    items = fetch_sigex(limit=10)
    for i in items:
        print(f"  {i['company'][:30]:<30} | {i['region']:<15} | {i['phase']:<15} | score={i['score']} | {i['title'][:50]}")
