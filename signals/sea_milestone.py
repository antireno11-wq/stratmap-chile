"""
signals/sea_milestone.py — Predictor de hitos y radar futuro para proyectos SEA
================================================================================
Analiza proyectos SEA según su estado actual y predice cuándo van a necesitar
proveedores, generando una señal de "demanda futura" con fecha estimada.

El proceso SEA en Chile tiene tiempos típicos bien conocidos:
  En Calificación   → RCA Favorable:    12–24 meses (promedio ~18 meses)
  RCA Aprobado       → Permisos:         3–9 meses
  Permisos listos    → Inicio construcción/licitación: 3–6 meses
  En Construcción    → Contratando AHORA

Almacena en raw.sea_milestone:
{
  "estado_actual": "En Calificación",
  "predicted_contracting_months": 24,
  "predicted_contracting_date": "2028-03",
  "confidence": "media",
  "milestone_reason": "Proyecto grande en calificación, Codelco típicamente tarda 18-24m",
  "computed_at": "2026-03-08T..."
}

También sube signal_score a proyectos cercanos a su fecha de contratación.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db
from datetime import datetime, timezone, timedelta
import json
import logging

logger = logging.getLogger(__name__)


# ── Tiempos típicos por estado SEA (en meses hasta inicio de contratación) ────
# (min, max, promedio) — se usa el promedio como estimación base
SEA_TIMELINE = {
    "en calificación":      (12, 36, 22),   # largo — proceso ambiental + RCA + permisos
    "en evaluación":        (12, 36, 22),
    "admision":             (18, 42, 28),   # más temprano, mayor incertidumbre
    "ingreso voluntario":   (24, 48, 34),
    "favorable":            (4,  12, 7),    # RCA favorable → permisos → licitación
    "aprobado":             (4,  12, 7),
    "en construcción":      (0,  3,  1),    # contratando AHORA
    "en operación":         (0,  6,  2),    # contratos de mantención/operación continuos
}

# Inversión alta → proceso más estructurado, tiempos más predecibles (reducir incertidumbre)
# Inversión baja → más riesgo de atraso o desistimiento
INVERSION_FACTOR = {
    "alta":   -3,   # >500M USD: atraer más financiamiento, proceso más rápido post-RCA
    "media":   0,   # 50-500M USD
    "baja":   +4,   # <50M USD: más probable que se aplace
}

# Mandantes grandes aceleran el proceso post-RCA
_MANDANTES_RAPIDOS = {
    "codelco", "bhp", "bhp chile", "escondida", "sqm", "collahuasi",
    "antofagasta minerals", "teck", "anglo american", "angloamerican",
    "barrick", "kinross", "lundin",
}


def _classify_estado(phase: str, raw: dict) -> str:
    """Normaliza el estado SEA a una clave del timeline."""
    estado = (phase or raw.get("ESTADO_EVALUACION") or raw.get("estado") or "").lower()
    if "calificaci" in estado:   return "en calificación"
    if "evaluaci" in estado:     return "en evaluación"
    if "favorable" in estado:    return "favorable"
    if "aprobado" in estado:     return "aprobado"
    if "construcci" in estado:   return "en construcción"
    if "operaci" in estado:      return "en operación"
    if "voluntario" in estado:   return "ingreso voluntario"
    if "admisi" in estado:       return "admision"
    return ""


def _classify_inversion(raw: dict) -> str:
    try:
        inv = float(raw.get("INVERSION_US") or 0)
        if inv >= 500_000_000:  return "alta"
        if inv >= 50_000_000:   return "media"
        return "baja"
    except Exception:
        return "media"


def _is_mandante_rapido(company: str) -> bool:
    c = (company or "").lower().strip()
    return any(m in c for m in _MANDANTES_RAPIDOS)


def _confidence(estado_key: str, inv_class: str, mandante_rapido: bool) -> str:
    if estado_key in ("en construcción", "en operación", "favorable", "aprobado"):
        return "alta"
    if inv_class == "alta" and mandante_rapido:
        return "alta"
    if inv_class == "alta" or mandante_rapido:
        return "media"
    return "baja"


def predict_milestone(project: dict) -> dict | None:
    """
    Predice hito de contratación para un proyecto SEA.
    Retorna dict con la predicción o None si no aplica.
    """
    raw = project.get("raw") or {}
    phase = project.get("phase") or ""
    company = project.get("company") or ""

    estado_key = _classify_estado(phase, raw)
    if not estado_key or estado_key not in SEA_TIMELINE:
        return None

    # Desistidos/rechazados: no predicción
    estado_lower = (phase or raw.get("ESTADO_EVALUACION") or "").lower()
    if any(x in estado_lower for x in ["desistido", "rechazado", "no admitido", "caducado"]):
        return None

    min_m, max_m, avg_m = SEA_TIMELINE[estado_key]
    inv_class = _classify_inversion(raw)
    rapido = _is_mandante_rapido(company)

    # Ajustes
    months = avg_m + INVERSION_FACTOR.get(inv_class, 0)
    if rapido and estado_key not in ("en construcción", "en operación"):
        months = max(months - 3, min_m)  # mandante grande acorta post-RCA
    months = max(min_m, min(max_m, months))

    now = datetime.now(timezone.utc)
    predicted_date = now + timedelta(days=int(months * 30.44))
    predicted_str = predicted_date.strftime("%Y-%m")

    conf = _confidence(estado_key, inv_class, rapido)

    # Signal score: mientras más cercano, más puntaje
    if months <= 3:    signal_boost = 25
    elif months <= 9:  signal_boost = 18
    elif months <= 18: signal_boost = 12
    elif months <= 30: signal_boost = 6
    else:              signal_boost = 2

    reason_parts = []
    if estado_key == "en construcción": reason_parts.append("en construcción — contratando ahora")
    elif estado_key in ("favorable", "aprobado"): reason_parts.append("RCA aprobado — en fase permisos/ingeniería")
    else: reason_parts.append(f"estado '{estado_key}' → ~{months} meses para contratar")
    if rapido: reason_parts.append("mandante grande acelera proceso")
    if inv_class == "alta": reason_parts.append("inversión alta (+certidumbre)")
    elif inv_class == "baja": reason_parts.append("inversión pequeña (+riesgo atraso)")

    return {
        "estado_actual": phase or estado_key,
        "predicted_contracting_months": months,
        "predicted_contracting_date": predicted_str,
        "confidence": conf,
        "milestone_reason": "; ".join(reason_parts),
        "signal_boost": signal_boost,
        "computed_at": now.isoformat(),
    }


def run(force_recompute: bool = False) -> dict:
    """
    Corre el predictor de hitos para todos los proyectos SEA activos.
    Actualiza raw.sea_milestone y aplica signal_boost al signal_score.

    Returns:
        dict con estadísticas del run
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            where = ""
            if not force_recompute:
                where = "AND (raw->>'sea_milestone') IS NULL"

            cur.execute(f"""
                SELECT id, title, phase, company, region, raw, score, signal_score
                FROM opportunities
                WHERE source = 'SEA'
                  {where}
                ORDER BY score DESC, updated_at DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        logger.info("[sea_milestone] No hay proyectos SEA pendientes")
        return {"processed": 0, "predicted": 0, "skipped": 0}

    predicted = 0
    skipped = 0
    updates = []

    for project in rows:
        milestone = predict_milestone(project)
        if not milestone:
            skipped += 1
            continue

        signal_boost = milestone.pop("signal_boost")
        new_signal = min(100, (project.get("signal_score") or 0) + signal_boost)

        updates.append({
            "id": project["id"],
            "milestone": json.dumps(milestone, ensure_ascii=False),
            "signal_score": new_signal,
        })
        predicted += 1

    if updates:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for u in updates:
                    cur.execute("""
                        UPDATE opportunities
                        SET raw = COALESCE(raw, '{}'::jsonb) || jsonb_build_object(
                                'sea_milestone', %(milestone)s::jsonb
                            ),
                            signal_score = %(signal_score)s,
                            last_signal_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %(id)s
                    """, u)
            conn.commit()
        logger.info(f"[sea_milestone] {predicted} predicciones guardadas")

    return {
        "processed": len(rows),
        "predicted": predicted,
        "skipped": skipped,
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = run(force_recompute=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
