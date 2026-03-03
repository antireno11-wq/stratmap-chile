"""
faenas_mineras.py — Conector de Faenas Mineras activas de Chile
===============================================================
Fuente: Ministerio de Medio Ambiente / Sernageomin
API:    https://arcgis.mma.gob.cl/server/rest/services/ide/Cartografia_Base/FeatureServer/2

Contiene ubicación de todas las explotaciones mineras activas de Chile
con nombre, empresa titular, tipo de mineral y coordenadas exactas.
Estos datos se sirven directamente al mapa como capa estática (no se
upsertean en opportunities — son datos de referencia, no oportunidades).
"""

import requests
from typing import List, Dict, Any

BASE_URL = "https://arcgis.mma.gob.cl/server/rest/services/ide/Cartografia_Base/FeatureServer/2/query"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Stratmap/1.0)",
    "Accept": "application/json",
}

# Tipos de faena conocidos
TIPO_LABELS = {
    "1": "Gran Minería",
    "2": "Mediana Minería",
    "3": "Pequeña Minería",
    "4": "Pirquinería",
    "5": "Planta de Tratamiento",
    "G": "Gran Minería",
    "M": "Mediana Minería",
    "P": "Pequeña Minería",
}

def fetch_faenas(limit: int = 2000) -> List[Dict[str, Any]]:
    """
    Descarga todas las faenas mineras activas con coordenadas.
    Retorna lista de dicts listos para servir al frontend.
    """
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "geometryPrecision": "5",
        "outSR": "4326",   # WGS84
        "f": "json",
        "resultOffset": 0,
        "resultRecordCount": limit,
    }

    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[faenas] Error fetching: {e}")
        return []

    features = data.get("features", [])
    print(f"[faenas] {len(features)} faenas descargadas")

    results = []
    for f in features:
        attrs = f.get("attributes", {})
        geom  = f.get("geometry", {})

        # Coordenadas — vienen en WGS84 por outSR=4326
        lng = geom.get("x") or attrs.get("LONGITUD") or attrs.get("ESTE")
        lat = geom.get("y") or attrs.get("LATITUD")  or attrs.get("NORTE")

        if not lat or not lng:
            continue
        # Validar rango Chile
        if not (-56 < float(lat) < -17 and -76 < float(lng) < -60):
            continue

        nombre  = (attrs.get("NOMBRE") or attrs.get("NOM_FAENA") or
                   attrs.get("NOMBRE_FAENA") or "Sin nombre").strip()
        empresa = (attrs.get("EMPRESA") or attrs.get("TITULAR") or
                   attrs.get("PROPIETARIO") or "").strip()
        mineral = (attrs.get("MINERAL") or attrs.get("RECURSO") or
                   attrs.get("TIPO_MINERAL") or "").strip()
        tipo    = str(attrs.get("TIPO") or attrs.get("CATEGORIA") or "")
        region  = (attrs.get("REGION") or attrs.get("NOM_REGION") or "").strip()
        comuna  = (attrs.get("COMUNA") or "").strip()

        tipo_label = TIPO_LABELS.get(tipo.strip(), tipo or "Faena Minera")

        results.append({
            "nombre":   nombre,
            "empresa":  empresa,
            "mineral":  mineral,
            "tipo":     tipo_label,
            "region":   region,
            "comuna":   comuna,
            "lat":      round(float(lat), 5),
            "lng":      round(float(lng), 5),
        })

    print(f"[faenas] {len(results)} faenas con coordenadas válidas")
    return results


if __name__ == "__main__":
    faenas = fetch_faenas()
    for f in faenas[:5]:
        print(f)
    print(f"Total: {len(faenas)}")
