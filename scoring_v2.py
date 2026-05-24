"""scoring_v2 — peso por evento individual.

La fórmula anterior pesaba por CATEGORÍA (todas las licitaciones igual, todas
las noticias igual). Esto sobrevalora ruido (noticia de PR corporativo) y
subvalora señales reales (licitación de 50M USD).

`event_weight(opp)` devuelve un entero 0-100 con la importancia comercial del
evento, evaluando fuente, monto declarado y palabras clave estructurales.

Rangos:
    100  Licitación grande (>=5 MUSD declarados)
     80  Hecho esencial CMF (regulatorio, calidad institucional)
     75  Licitación mediana (0.5-5 MUSD)
     70  SEA — EIA / DIA presentado (proyecto futuro cierto)
     65  Licitación de fuente "alta señal" sin monto (ENAMI/Codelco/MOP)
     50  Licitación genérica sin monto (MercadoPublico, etc)
     40  Noticia ESTRUCTURAL (inversión/contrato/adjudica/MUSD)
     20  Empleo masivo (>10 vacantes)
     10  Noticia genérica
      5  Empleo individual

Las funciones son puras: aceptan dict, devuelven int. No tocan la DB.
"""
from __future__ import annotations

import re
from typing import Optional

from source_categories import (
    LICITACION_SOURCES, PROSPECTO_SOURCES, NOTICIA_SOURCES, EMPLEO_SOURCES,
)

# Fuentes con histórico de licitaciones "grandes" — si vienen sin monto declarado,
# asumimos que valen más que una compra menor de mercadopublico.
HIGH_SIGNAL_LICIT_SOURCES = {"ENAMI", "Codelco", "MOP", "Ariba Codelco", "SICEP", "MLP Proveedores"}

# Palabras que disparan "noticia estructural" — anuncio de inversión, contrato,
# adjudicación, hito de proyecto, capex declarado. Match case-insensitive sobre
# title + description.
STRUCTURAL_KEYWORDS = [
    r"\binversi[oó]n",
    r"\bcapex\b",
    r"\bcontrat[oa]\b",
    r"\badjudic\w+",                   # adjudica, adjudicada, adjudicación
    r"\blicitaci[oó]n\w*",
    r"\bmegaproyect",
    r"\bproyecto\s+nuev",
    r"\binaugur\w+",
    r"\bexpansi[oó]n\b",
    r"\bperfora\w+",
    r"\bsondaj\w+",
    r"\bplanta\s+(concentrador|desaliniz|procesad)",
    r"\bdesalini\w+",
    r"\beia\b|\bdia\b",                # evaluación ambiental
    r"\brca\b",                        # resolución ambiental
    r"\bcomodato\b",
    r"\bhito\b",
    r"\bcontrat\w+\s+(adjudic|firm)",
    r"\bcaperton",                     # contractor names que indican movimiento
    r"\b(mmusd|musd|mm\s*usd|mil\s*millones)\b",  # cifras en USD
    r"\bus\$\s*\d",
    r"\b\d+\s*millones\s+(de\s+)?d[oó]lar",
    r"\bcapex\s+anunci",
]
_STRUCTURAL_RE = re.compile("|".join(STRUCTURAL_KEYWORDS), re.IGNORECASE)

# Detección de montos en texto libre. Cubre:
#   "USD 50 millones", "US$ 100M", "MUSD 200", "$15.000 millones",
#   "5,5 MMUSD", "1.2 mil millones de dólares".
_AMOUNT_PATTERNS = [
    # X MUSD / MMUSD / M USD (millones USD)
    (re.compile(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*(?:MM?USD|M\s*USD|MMD)", re.IGNORECASE), 1.0),
    # MUSD X (notación invertida común en informes mineros)
    (re.compile(r"(?:MM?USD|M\s*USD)\s*(\d{1,4}(?:[.,]\d{1,3})?)", re.IGNORECASE), 1.0),
    # USD X millones / US$ X millones
    (re.compile(r"(?:USD|US\$)\s*(\d{1,4}(?:[.,]\d{1,3})?)\s*(?:millones?|MM)", re.IGNORECASE), 1.0),
    # X millones de dólares
    (re.compile(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*millones?\s+(?:de\s+)?d[oó]lar", re.IGNORECASE), 1.0),
    # X mil millones de dólares (X * 1000 MUSD)
    (re.compile(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*mil\s+millones?\s+(?:de\s+)?d[oó]lar", re.IGNORECASE), 1000.0),
]


def _to_float(s: str) -> Optional[float]:
    """Convierte '1,5' o '1.5' o '15.000' a float (formato español/inglés)."""
    s = s.replace(" ", "")
    # Si tiene ambos, asumimos formato es-CL: punto miles, coma decimal
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def extract_amount_musd(text: str) -> Optional[float]:
    """Extrae un monto en millones USD del texto, si lo detecta. None si no hay.

    Heurística simple — falla en monedas ambiguas (CLP/USD mezclado) y devuelve
    el PRIMER match. Suficiente para clasificación gruesa.
    """
    if not text:
        return None
    for pattern, mult in _AMOUNT_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        raw = m.group(1)
        value = _to_float(raw)
        if value is None or value <= 0:
            continue
        result = value * mult
        # Filtros sanos: rechazar montos absurdamente grandes (>500_000 MUSD = 500B)
        if 0.01 <= result <= 500_000:
            return round(result, 2)
    return None


def is_structural_news(text: str) -> bool:
    """True si la noticia contiene keywords de evento estructural (inversión,
    contrato, adjudica, MUSD, etc). False = noticia genérica/PR/operativa."""
    if not text:
        return False
    return bool(_STRUCTURAL_RE.search(text))


def event_weight(opp: dict) -> int:
    """Peso 0-100 del evento. Ver docstring del módulo para rangos."""
    if not isinstance(opp, dict):
        return 0
    source = (opp.get("source") or "").strip()
    title  = opp.get("title") or ""
    raw    = opp.get("raw") if isinstance(opp.get("raw"), dict) else {}
    desc   = (raw.get("description") or raw.get("summary") or "") if raw else ""
    text   = f"{title}\n{desc}"

    # CMF: hecho esencial regulatorio (calidad institucional).
    if source == "cmf":
        return 80

    # SEA: proyecto en evaluación ambiental — pipeline futuro cierto.
    if source in PROSPECTO_SOURCES:
        return 70

    # Licitaciones: peso por monto si se detecta.
    if source in LICITACION_SOURCES:
        amount = extract_amount_musd(text)
        if amount is not None:
            if amount >= 5:
                return 100
            if amount >= 0.5:
                return 75
        # Sin monto detectado: depende de la fuente.
        if source in HIGH_SIGNAL_LICIT_SOURCES:
            return 65
        return 50

    # Empleos: peso por volumen de vacantes (jobs_count). Una sola vacante es
    # poca señal; 50 vacantes nuevas son inicio de fase.
    if source in EMPLEO_SOURCES:
        n = int(opp.get("jobs_count") or 1)
        if n >= 10:
            return 20
        if n >= 3:
            return 10
        return 5

    # Noticias: estructural vs genérica.
    if source in NOTICIA_SOURCES:
        return 40 if is_structural_news(text) else 10

    # Fallback
    return 10
