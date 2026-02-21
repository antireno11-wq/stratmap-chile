# connectors/cochilco.py
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")

# COCHILCO catastro de inversión minera - API pública
CATASTRO_URL = "https://www.cochilco.cl/Mercado%20de%20Metales/Catastro%20de%20Inversiones.aspx"
RSS_COCHILCO = "https://www.cochilco.cl/web/feed/"

# Regiones mineras principales para scoring
REGIONES_MINERAS = ["Antofagasta", "Atacama", "Tarapacá", "Coquimbo", "Arica y Parinacota"]

def score_cochilco(monto_mmusd: Optional[float], region: Optional[str], stage: Optional[str]) -> int:
    base = 55  # COCHILCO ya es minería por definición
    
    inv = 0
    if monto_mmusd:
        if monto_mmusd >= 1000: inv = 25
        elif monto_mmusd >= 500: inv = 20
        elif monto_mmusd >= 100: inv = 15
        elif monto_mmusd >= 50: inv = 10
        elif monto_mmusd >= 10: inv = 5

    reg = 0
    if region and any(r in (region or '') for r in REGIONES_MINERAS):
        reg = 8

    stage_boost = 0
    s = (stage or '').lower()
    if any(k in s for k in ['construcción', 'ejecución', 'operación']):
        stage_boost = 12
    elif any(k in s for k in ['factibilidad', 'ingeniería', 'diseño']):
        stage_boost = 8
    elif any(k in s for k in ['exploración', 'prospección']):
        stage_boost = 4

    return max(0, min(100, base + inv + reg + stage_boost))


def fetch_cochilco_rss() -> List[Dict[str, Any]]:
    """Trae noticias de COCHILCO vía RSS"""
    import xml.etree.ElementTree as ET
    out = []
    try:
        r = requests.get(RSS_COCHILCO, timeout=20, headers={"User-Agent": "StratmapWorker/0.2"}, verify=False)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        for item in items:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            url = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            out.append({
                "source": "COCHILCO",
                "title": title[:500],
                "url": url,
                "company": "COCHILCO",
                "contractor": None,
                "industry": "Minería",
                "region": None,
                "phase": "Noticia",
                "score": 55,
                "entry": None,
                "raw": {"title": title, "description": description[:500]},
            })
    except Exception as e:
        print(f"[cochilco] RSS error: {e}")
    return out


def fetch_cochilco_catastro() -> List[Dict[str, Any]]:
    """
    Intenta obtener el catastro de inversiones de COCHILCO.
    COCHILCO publica un Excel con el catastro — intentamos el endpoint directo.
    """
    out = []
    # COCHILCO publica datos en JSON a través de su portal de datos
    endpoints = [
        "https://www.cochilco.cl/_api/web/lists/getbytitle('Catastro')/items?$top=500&$format=json",
        "https://datosabiertos.cochilco.cl/api/action/datastore_search?resource_id=catastro-inversiones&limit=500",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=20, headers={
                "User-Agent": "StratmapWorker/0.2",
                "Accept": "application/json"
            }, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data.get("value") or data.get("result", {}).get("records", [])
                for item in items:
                    title = item.get("Title") or item.get("proyecto") or item.get("PROYECTO") or ""
                    if not title:
                        continue
                    company = item.get("empresa") or item.get("EMPRESA") or item.get("Empresa") or None
                    region = item.get("region") or item.get("REGION") or item.get("Region") or None
                    stage = item.get("etapa") or item.get("ETAPA") or item.get("Estado") or None
                    monto = None
                    for k in ["monto_mmus", "MONTO", "inversion", "INVERSION", "monto"]:
                        try:
                            monto = float(item.get(k) or 0)
                            break
                        except:
                            pass
                    score = score_cochilco(monto, region, stage)
                    out.append({
                        "source": "COCHILCO",
                        "title": str(title)[:500],
                        "url": "https://www.cochilco.cl/Mercado%20de%20Metales/Catastro%20de%20Inversiones.aspx",
                        "company": str(company) if company else None,
                        "contractor": None,
                        "industry": "Minería",
                        "region": str(region) if region else None,
                        "phase": str(stage) if stage else "En evaluación",
                        "score": score,
                        "entry": str(item.get("id") or item.get("ID") or ""),
                        "raw": item,
                    })
                if out:
                    print(f"[cochilco] catastro: {len(out)} proyectos desde {url}")
                    break
        except Exception as e:
            print(f"[cochilco] catastro error {url}: {e}")

    return out


def fetch_cochilco(limit: int = 300) -> List[Dict[str, Any]]:
    out = []
    catastro = fetch_cochilco_catastro()
    out.extend(catastro)
    rss = fetch_cochilco_rss()
    out.extend(rss)
    print(f"[cochilco] total: {len(out)} items (catastro={len(catastro)}, rss={len(rss)})")
    return out[:limit]
