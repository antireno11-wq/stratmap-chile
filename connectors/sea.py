# connectors/sea.py
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

SEA_BASE = "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer"

# Layers que normalmente traen proyectos (los que ya viste que funcionan)
DEFAULT_LAYERS = os.getenv("SEA_LAYERS", "1,2").strip()  # ej: "1,2" o "0,1,2"
USER_AGENT = os.getenv("USER_AGENT", "stratmap-chile/0.1")

TIMEOUT = float(os.getenv("SEA_TIMEOUT", "20"))
RETRIES = int(os.getenv("SEA_RETRIES", "2"))


def _layer_url(layer_id: int) -> str:
    return f"{SEA_BASE}/{layer_id}"


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    last_err = None
    for i in range(RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if i < RETRIES:
                time.sleep(0.7 * (i + 1))
                continue
            raise last_err


def _get_layer_meta(layer_url: str) -> Dict[str, Any]:
    # ArcGIS layer metadata: fields, name, etc.
    return _get_json(layer_url, params={"f": "json"})


def _pick_date_field(meta: Dict[str, Any]) -> Optional[str]:
    """
    Intenta encontrar un campo de fecha usable.
    El SEA suele tener FECHA_PRESENTACION u otros.
    """
    fields = meta.get("fields") or []
    if not isinstance(fields, list):
        return None

    # candidatos típicos
    preferred = [
        "FECHA_PRESENTACION",
        "FECHA_INGRESO",
        "FECHA",
        "FECHA_CREACION",
        "created_date",
        "createdate",
        "creationdate",
    ]

    # 1) match exacto
    for p in preferred:
        for f in fields:
            if (f.get("name") or "").upper() == p.upper():
                return f.get("name")

    # 2) cualquier campo tipo date
    for f in fields:
        ftype = (f.get("type") or "").lower()
        if "date" in ftype:
            return f.get("name")

    # 3) cualquier campo que contenga 'fecha'
    for f in fields:
        name = (f.get("name") or "").lower()
        if "fecha" in name:
            return f.get("name")

    return None


def _region_from_attrs(attrs: Dict[str, Any]) -> Optional[str]:
    # SEA puede traer región con nombres distintos
    for k in ["REGION", "Region", "REGIÓN", "REGION_NOMBRE", "NOM_REGION", "REGION_PROYECTO"]:
        v = attrs.get(k)
        if v:
            return str(v).strip()
    return None


def _phase_from_attrs(attrs: Dict[str, Any]) -> Optional[str]:
    # Estados típicos en SEIA: aprobado, en calificación, etc.
    for k in ["ESTADO", "Estado", "ESTADO_PROYECTO", "FASE", "SITUACION", "SITUACIÓN"]:
        v = attrs.get(k)
        if v:
            return str(v).strip()
    return None


def _company_from_attrs(attrs: Dict[str, Any]) -> Optional[str]:
    # Titular
    for k in ["TITULAR", "Titular", "NOMBRE_TITULAR", "RAZON_SOCIAL", "RAZÓN_SOCIAL"]:
        v = attrs.get(k)
        if v:
            return str(v).strip()
    return None


def _title_from_attrs(attrs: Dict[str, Any]) -> str:
    for k in ["NOMBRE_PROYECTO", "NOMBRE", "PROYECTO", "TITULO", "TÍTULO", "NOM_PROYECTO"]:
        v = attrs.get(k)
        if v:
            return str(v).strip()
    # fallback: algo
    return str(attrs.get("OBJECTID") or attrs.get("objectid") or "Proyecto SEIA").strip()


def _code_from_attrs(attrs: Dict[str, Any]) -> Optional[str]:
    # El “código” que tú estabas sacando (tipo 9039, 9047)
    for k in ["CODIGO", "COD_PROY", "CODIGO_PROYECTO", "ID_PROYECTO", "COD_SEIA", "COD"]:
        v = attrs.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s.isdigit():
            return s
    # a veces viene como string con dígitos dentro
    for k in ["CODIGO", "COD_PROY", "CODIGO_PROYECTO", "COD_SEIA"]:
        v = attrs.get(k)
        if not v:
            continue
        s = "".join([c for c in str(v) if c.isdigit()])
        if s:
            return s
    return None


def _project_url(code: Optional[str], fallback_layer_url: str) -> str:
    if code and code.isdigit():
        return f"https://www.sea.gob.cl/buscador-de-proyectos?texto={code}"
    return fallback_layer_url


def _arcgis_query(layer_url: str, where: str, limit: int) -> List[Dict[str, Any]]:
    """
    Query ArcGIS layer returning features.
    """
    url = f"{layer_url}/query"
    params = {
        "f": "json",
        "where": where,
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": str(limit),
        "orderByFields": "OBJECTID DESC",
    }
    data = _get_json(url, params=params)
    feats = data.get("features") or []
    if not isinstance(feats, list):
        return []
    out = []
    for f in feats:
        attrs = f.get("attributes") or {}
        if isinstance(attrs, dict):
            out.append(attrs)
    return out


def fetch_sea(days_back: int = 90, limit: int = 800, debug: bool = False) -> List[Dict[str, Any]]:
    """
    Retorna items normalizados:
    {
      source: "sea",
      title, url,
      company, region, phase,
      raw: {...}
    }
    """
    layer_ids = []
    for part in DEFAULT_LAYERS.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit():
            layer_ids.append(int(part))

    # fallback si quedó vacío
    if not layer_ids:
        layer_ids = [1, 2]

    # Ventana de fechas (si existe campo fecha)
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(days=int(days_back))

    items: List[Dict[str, Any]] = []

    for lid in layer_ids:
        layer_url = _layer_url(lid)

        # meta para campo fecha
        date_field = None
        try:
            meta = _get_layer_meta(layer_url)
            date_field = _pick_date_field(meta or {})
        except Exception as e:
            if debug:
                print(f"[SEA] meta fail layer {lid}: {e}")
            date_field = None

        # where clause
        where = "1=1"
        if date_field:
            # ArcGIS date suele ser epoch ms o date type: usa timestamp ISO en string no siempre funciona.
            # Acá usamos ">= date 'YYYY-MM-DD'" que suele andar en muchos ArcGIS.
            yyyy_mm_dd = since_utc.strftime("%Y-%m-%d")
            where = f"{date_field} >= date '{yyyy_mm_dd}'"

        # Query
        try:
            attrs_list = _arcgis_query(layer_url, where=where, limit=int(limit))
            if debug:
                print(f"[SEA] layer {lid} date_field={date_field} got {len(attrs_list)}")
        except Exception as e:
            if debug:
                print(f"[SEA] query fail layer {lid}: {e}")
            continue

        for attrs in attrs_list:
            title = _title_from_attrs(attrs)
            company = _company_from_attrs(attrs)
            region = _region_from_attrs(attrs)
            phase = _phase_from_attrs(attrs)
            code = _code_from_attrs(attrs)
            url = _project_url(code, fallback_layer_url=layer_url)

            items.append(
                {
                    "source": "sea",
                    "title": title if code is None else f"{title} (SEIA {code})",
                    "url": url,
                    "company": company,
                    "contractor": None,
                    "industry": None,
                    "region": region,
                    "phase": phase,
                    "score": 0,
                    "entry": None,
                    "raw": attrs,
                }
            )

    # dedupe por url
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for it in items:
        u = it.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(it)

    return uniq
