"""
ai_scorer.py — Scoring IA para proyectos mineros.

Claude evalúa proyectos y devuelve ajustes de score con justificación.
Se ejecuta como POST /admin/run-ai-scorer.

Flujo:
  1. Consulta BD: proyectos ordenados por prioridad (sin score IA, más recientes)
  2. Los envía en lotes a Claude con contexto enriquecido
  3. Claude devuelve JSON con {id, ajuste (-15 a +15), razon}
  4. Se persiste en raw.ai_score_reason y raw.ai_scored_at
"""

import json
import os
import time
from typing import Any, Dict, List, Tuple

import ai_client
import db

# ── Campos útiles para enviar a Claude ────────────────────────────────────────
FIELDS = ("id", "title", "company", "source", "phase", "region", "score", "raw")

SYSTEM_PROMPT = """Eres un experto senior en licitaciones y proyectos de minería chilena con 20 años de experiencia.
Tu tarea es evaluar oportunidades comerciales para proveedores de servicios y bienes mineros.

Para cada proyecto recibirás: título, empresa mandante, fuente, fase, región, score actual (0-100),
inversión estimada, estado de evaluación, temperatura del mandante (heat) y días sin actividad.

El score actual viene de un sistema de reglas. Tu trabajo es ajustarlo usando criterios que las reglas no capturan:
conocimiento del mercado minero chileno, señales de actividad real, probabilidad efectiva de contratación.

CRITERIOS DE AJUSTE (rango -15 a +15):
- +12 a +15: Proyecto claramente activo o próximo a licitar. Mandante grande (Codelco, BHP, SQM, etc.),
             fase de construcción o ingeniería de detalle, inversión >100M USD, mandante con heat >70.
- +6 a +11:  Señales moderadamente positivas. Proyecto viable, mandante conocido, región minera clave,
             actividad reciente, mandante caliente.
- 0:         Score correcto. Sin información adicional para ajustar.
- -6 a -11:  Señales débiles. Proyecto estancado, mandante desconocido, sin actividad en 6+ meses,
             fase muy temprana sin inversión confirmada.
- -12 a -15: Proyecto inactivo, rechazado, desistido, o claramente sin valor comercial.

CONTEXTO MINERO CHILE que las reglas no capturan:
- Proyectos SEA "En Calificación" con mandante grande y >500M USD son oportunidades reales aunque tardías
- Proyectos SIGEX en trámite son señales tempranas de exploración → potencial en 2-4 años
- Mandantes con heat >70 están activamente contratando RIGHT NOW
- Fases de modificación/ampliación de faenas existentes tienen contratación más rápida que proyectos nuevos

RESPONDE SOLO con un array JSON válido, sin texto adicional:
[
  {"id": 123, "ajuste": 12, "razon": "BHP en construcción, inversión 1.2B USD, heat=85, contratación activa"},
  {"id": 456, "ajuste": -12, "razon": "Estado desistido, sin actividad 2 años, mandante sin heat"},
  ...
]
"""


def _build_prompt(batch: List[Dict], heat_map: dict) -> str:
    lines = []
    for p in batch:
        raw = p.get("raw") or {}
        company = p.get("company") or "?"
        heat = heat_map.get((company or "").lower().strip(), 0)
        heat_str = f"{heat}/100" if heat else "sin datos"

        # Calcular días sin actividad
        dias_inactivo = "?"
        for field in ("updated_at", "last_signal_at"):
            v = p.get(field)
            if v:
                try:
                    from datetime import timezone
                    if isinstance(v, str):
                        from datetime import datetime as _dt
                        v = _dt.fromisoformat(v.replace("Z", "+00:00"))
                    if v.tzinfo is None:
                        from datetime import timezone
                        v = v.replace(tzinfo=timezone.utc)
                    from datetime import datetime as _dt2, timezone as _tz
                    dias_inactivo = (_dt2.now(_tz.utc) - v).days
                    break
                except Exception:
                    pass

        lines.append(
            f"ID:{p['id']} | {p.get('title','')[:90]} | "
            f"Mandante: {company} | Fuente: {p.get('source','?')} | "
            f"Fase: {p.get('phase','?')} | Región: {p.get('region','?')} | "
            f"Score: {p.get('score',0)} | "
            f"Inversión USD: {raw.get('INVERSION_US','?')} | "
            f"Estado SEA: {raw.get('ESTADO_EVALUACION','?')} | "
            f"Heat mandante: {heat_str} | "
            f"Días sin actividad: {dias_inactivo}"
        )
    return "Evalúa estos proyectos mineros chilenos:\n\n" + "\n".join(lines)


def _call_claude(prompt: str, retries: int = 2) -> List[Dict]:
    """Llama a la API de OpenRouter (con fallback a Anthropic) y parsea la respuesta JSON."""
    for attempt in range(retries + 1):
        try:
            text = ai_client.call_llm(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                max_tokens=1500,
                model="claude-haiku-4-5-20251001"
            )

            # Limpiar posibles markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            return json.loads(text)

        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                raise


NEWS_SOURCES = (
    'Portal Minero','BioBioChile','Emol','Cooperativa',
    'Minería Chilena','COCHILCO Noticias','Diario Financiero',
    'Revista EI','Radio U. de Chile','Radio Universidad de Chile',
    'RSS','Lithium Chile','InfoMineria','Mundo Minería',
    'MLP Proveedores','BHP Careers','AMSA Careers',
    'Lundin Careers','Collahuasi Careers','Teck Careers'
)


def run(score_min: int = 10, score_max: int = 85, batch_size: int = 20,
        max_batches: int = 10, only_unscored: bool = False) -> Dict[str, Any]:
    """
    Corre AI scoring para proyectos mineros.

    Args:
        score_min: Score mínimo a evaluar (default 10, excluye noticias en 0)
        score_max: Score máximo a evaluar (default 85, excluye scores perfectos)
        batch_size: Proyectos por llamada a Claude (default 20)
        max_batches: Máximo de llamadas API (default 10 = 200 proyectos)
        only_unscored: Si True, solo proyectos sin score IA previo (más eficiente)
    """
    # 1. Pre-cargar heat map de mandantes
    heat_map: Dict[str, int] = {}
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company, heat_score FROM mandante_heat")
            for r in cur.fetchall():
                if r["company"]:
                    heat_map[r["company"].lower().strip()] = r["heat_score"] or 0

    # 2. Buscar proyectos a evaluar — priorizando sin score IA y más recientes
    ai_filter = "AND (raw->>'ai_scored_at') IS NULL" if only_unscored else ""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, title, company, source, phase, region, score, raw,
                       updated_at, last_signal_at
                FROM opportunities
                WHERE score BETWEEN %s AND %s
                  AND source NOT IN %s
                  {ai_filter}
                ORDER BY
                  CASE WHEN (raw->>'ai_scored_at') IS NULL THEN 0 ELSE 1 END,
                  COALESCE(updated_at, created_at) DESC
                LIMIT %s
            """, (score_min, score_max, NEWS_SOURCES, batch_size * max_batches))
            proyectos = [dict(r) for r in cur.fetchall()]

    if not proyectos:
        return {"ok": True, "msg": "Sin proyectos en zona gris", "evaluados": 0, "actualizados": 0}

    # 3. Procesar en batches
    updates: List[Tuple[int, int, str]] = []  # (new_score, razon, id)
    errors = []
    batches_procesados = 0

    for i in range(0, len(proyectos), batch_size):
        batch = proyectos[i:i + batch_size]
        prompt = _build_prompt(batch, heat_map)
        id_to_score = {p["id"]: p["score"] for p in batch}

        try:
            resultados = _call_claude(prompt)
            for r in resultados:
                pid = r.get("id")
                ajuste = r.get("ajuste", 0)
                razon = r.get("razon", "")
                if pid not in id_to_score:
                    continue
                ajuste = max(-15, min(15, int(ajuste)))  # clamp extendido ±15
                new_score = max(0, min(99, id_to_score[pid] + ajuste))
                if new_score != id_to_score[pid]:
                    updates.append((new_score, razon, pid))

            batches_procesados += 1
        except Exception as e:
            errors.append(str(e))

        # Rate limit: pausa entre llamadas
        if i + batch_size < len(proyectos):
            time.sleep(1)

    # 3. Persistir ajustes — update score y guardar razón en raw.ai_boost
    actualizados = 0
    if updates:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for new_score, razon, pid in updates:
                    cur.execute("""
                        UPDATE opportunities
                        SET score = %s,
                            raw = COALESCE(raw, '{}'::jsonb) || jsonb_build_object(
                                'ai_score_reason', %s,
                                'ai_scored_at', NOW()::text
                            ),
                            updated_at = NOW()
                        WHERE id = %s
                    """, (new_score, razon, pid))
                    actualizados += 1
            conn.commit()

    return {
        "ok": True,
        "evaluados": len(proyectos),
        "batches": batches_procesados,
        "actualizados": actualizados,
        "errores": errors,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
