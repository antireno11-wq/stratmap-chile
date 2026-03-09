"""
signals/phase_tracker.py — Detector de cambios de fase en proyectos SEA
=========================================================================
Detecta cuando un proyecto cambia de fase (ej: "En Calificación" → "Aprobado")
y genera señales/alertas para los proyectos y usuarios interesados.

Lógica:
  1. Compara la fase actual en la BD con la fase anterior guardada en raw.previous_phase
  2. Si cambió → registra en phase_history + aplica signal_boost
  3. Ascensos de fase (más activo) suben score; descensos (desistido) bajan

Cambios críticos:
  En Calificación → Aprobado/Favorable: +20 pts  (¡RCA conseguido!)
  Aprobado → En Construcción: +25 pts             (¡comenzó la obra!)
  Cualquier → Desistido/Rechazado: -30 pts        (proyecto muerto)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Jerarquía de fases: valor más alto = más avanzado/activo
PHASE_RANK = {
    "ingreso voluntario":   1,
    "admisión":             2,
    "admision":             2,
    "en evaluación":        3,
    "en evaluacion":        3,
    "en calificación":      4,
    "en calificacion":      4,
    "favorable":            7,
    "aprobado":             7,
    "en construcción":      9,
    "en construccion":      9,
    "en operación":         8,
    "en operacion":         8,
    "modificación":         6,
    "modificacion":         6,
    "desistido":            0,
    "rechazado":            0,
    "no admitido":          0,
    "caducado":             0,
}

# Boost por tipo de transición
TRANSITION_BOOST = {
    # (desde_rank, hasta_rank) → boost
    # Ascenso a aprobado/favorable
    (4, 7): 20,   # calificación → aprobado
    (3, 7): 18,   # evaluación → aprobado
    (2, 7): 16,   # admisión → aprobado
    # Ascenso a construcción
    (7, 9): 25,   # aprobado → construcción
    (4, 9): 22,   # calificación → construcción (saltando etapas)
    # Descenso a muerto
    (4, 0): -30,  # calificación → desistido
    (7, 0): -25,  # aprobado → desistido (raro pero pasa)
    (3, 0): -25,
}

DEFAULT_ASCENSO_BOOST = 10   # ascenso genérico
DEFAULT_DESCENSO_BOOST = -15  # descenso genérico


def _phase_key(phase: str) -> str:
    return (phase or "").lower().strip()


def _phase_rank(phase: str) -> int:
    return PHASE_RANK.get(_phase_key(phase), 5)  # default 5 = estado desconocido


def _calc_boost(old_phase: str, new_phase: str) -> int:
    old_rank = _phase_rank(old_phase)
    new_rank = _phase_rank(new_phase)

    if old_rank == new_rank:
        return 0

    # Buscar boost específico
    key = (old_rank, new_rank)
    if key in TRANSITION_BOOST:
        return TRANSITION_BOOST[key]

    if new_rank > old_rank:
        # Ascenso genérico — proporcional al salto
        return min(DEFAULT_ASCENSO_BOOST + (new_rank - old_rank) * 2, 20)
    else:
        # Descenso genérico
        if new_rank == 0:
            return -30
        return DEFAULT_DESCENSO_BOOST


def _init_phase_history_table() -> None:
    """Crea la tabla phase_history si no existe."""
    sql = """
    CREATE TABLE IF NOT EXISTS phase_history (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        old_phase TEXT,
        new_phase TEXT,
        signal_boost INTEGER DEFAULT 0,
        detected_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_phase_history_opp ON phase_history(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_phase_history_date ON phase_history(detected_at DESC);
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def run(force_init: bool = True) -> dict:
    """
    Detecta cambios de fase para proyectos SEA.
    Registra en phase_history y aplica signal_boost.
    """
    if force_init:
        try:
            _init_phase_history_table()
        except Exception as e:
            logger.warning(f"[phase_tracker] init table warning: {e}")

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, phase, company, region, score, signal_score, raw
                FROM opportunities
                WHERE source = 'SEA'
                  AND phase IS NOT NULL
                ORDER BY updated_at DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {"checked": 0, "changes": 0}

    changes = []
    phase_updates = []

    for project in rows:
        raw = project.get("raw") or {}
        current_phase = (project.get("phase") or "").strip()
        prev_phase    = (raw.get("previous_phase") or "").strip()

        # Primera vez que procesamos este proyecto → guardar fase actual como baseline
        if not prev_phase:
            phase_updates.append({
                "id": project["id"],
                "prev": current_phase,
                "signal_score": project.get("signal_score") or 0,
                "log_change": False,
            })
            continue

        # Detectar cambio
        if _phase_key(current_phase) == _phase_key(prev_phase):
            continue  # sin cambio

        boost = _calc_boost(prev_phase, current_phase)
        new_signal = max(0, min(100, (project.get("signal_score") or 0) + boost))

        logger.info(
            f"[phase_tracker] CAMBIO: '{project['title'][:60]}' "
            f"{prev_phase!r} → {current_phase!r} (boost={boost:+d})"
        )

        changes.append({
            "opportunity_id": project["id"],
            "old_phase": prev_phase,
            "new_phase": current_phase,
            "signal_boost": boost,
        })
        phase_updates.append({
            "id": project["id"],
            "prev": current_phase,  # actualizar previous_phase
            "signal_score": new_signal,
            "log_change": True,
            "boost": boost,
        })

    if phase_updates:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Registrar cambios en phase_history
                for u in phase_updates:
                    if u["log_change"]:
                        cur.execute("""
                            INSERT INTO phase_history
                                (opportunity_id, old_phase, new_phase, signal_boost, detected_at)
                            VALUES (%s, %s, %s, %s, NOW())
                        """, (u["id"], u.get("old_phase"), u.get("new_phase"), u.get("boost", 0)))

                # Actualizar previous_phase y signal_score
                for u in phase_updates:
                    cur.execute("""
                        UPDATE opportunities
                        SET raw = COALESCE(raw, '{}'::jsonb) || jsonb_build_object(
                                'previous_phase', %(prev)s
                            ),
                            signal_score = %(signal_score)s,
                            last_signal_at = CASE WHEN %(log_change)s::boolean THEN NOW()
                                             ELSE last_signal_at END,
                            updated_at = NOW()
                        WHERE id = %(id)s
                    """, {
                        "prev": u["prev"],
                        "signal_score": u["signal_score"],
                        "log_change": u["log_change"],
                        "id": u["id"],
                    })
            conn.commit()

    return {
        "checked": len(rows),
        "changes": len(changes),
        "transitions": [
            {"title_id": c["opportunity_id"], "from": c["old_phase"],
             "to": c["new_phase"], "boost": c["signal_boost"]}
            for c in changes
        ],
    }


def get_recent_changes(limit: int = 50) -> list:
    """Retorna los cambios de fase más recientes para alertas/dashboard."""
    try:
        _init_phase_history_table()
    except Exception:
        pass
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ph.id, ph.opportunity_id, ph.old_phase, ph.new_phase,
                       ph.signal_boost, ph.detected_at,
                       o.title, o.company, o.region, o.score, o.url
                FROM phase_history ph
                JOIN opportunities o ON o.id = ph.opportunity_id
                ORDER BY ph.detected_at DESC
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
