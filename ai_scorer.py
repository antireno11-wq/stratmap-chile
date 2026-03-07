"""
ai_scorer.py — Scoring IA para proyectos en zona gris (score 45–65).

Claude evalúa lotes de proyectos ambiguos y devuelve ajustes de score
con justificación. Se ejecuta como POST /admin/run-ai-scorer.

Flujo:
  1. Consulta BD: proyectos con score entre 45 y 65
  2. Los envía en lotes de 20 a Claude
  3. Claude devuelve JSON con {id, ajuste (-10 a +10), razon}
  4. Se persiste en campo `ai_score_boost` y `ai_score_reason` en raw
"""

import json
import os
import time
from typing import Any, Dict, List, Tuple

import httpx
import db

# ── Campos útiles para enviar a Claude ────────────────────────────────────────
FIELDS = ("id", "title", "company", "source", "phase", "region", "score", "raw")

SYSTEM_PROMPT = """Eres un experto en licitaciones y proyectos de minería chilena.
Tu tarea es evaluar oportunidades comerciales para proveedores de servicios y bienes mineros.

Para cada proyecto recibirás: título, empresa mandante, fuente, fase, región, score actual (0-100).
El score actual viene de un sistema de reglas. Tu trabajo es ajustarlo basándote en contexto que las reglas no capturan.

CRITERIOS DE AJUSTE:
- +8 a +10: Proyecto claramente activo, en fase de contratación, mandante relevante, región clave
- +4 a +7: Señales moderadamente positivas, proyecto viable pero con incertidumbre
- 0: Score correcto, no hay información adicional para ajustar
- -4 a -7: Proyecto estancado, información contradictoria, mandante menor
- -8 a -10: Proyecto claramente inactivo, rechazado, o de muy bajo valor comercial

RESPONDE SOLO con un array JSON válido, sin texto adicional:
[
  {"id": 123, "ajuste": 5, "razon": "Proyecto en fase de construcción con mandante Codelco"},
  {"id": 456, "ajuste": -8, "razon": "Estado desistido, sin actividad reciente"},
  ...
]
"""


def _build_prompt(batch: List[Dict]) -> str:
    lines = []
    for p in batch:
        raw = p.get("raw") or {}
        lines.append(
            f"ID:{p['id']} | {p.get('title','')[:80]} | "
            f"Empresa: {p.get('company','?')} | "
            f"Fuente: {p.get('source','?')} | "
            f"Fase: {p.get('phase','?')} | "
            f"Región: {p.get('region','?')} | "
            f"Score actual: {p.get('score',0)} | "
            f"Inversión USD: {raw.get('INVERSION_US','?')} | "
            f"Estado evaluación: {raw.get('ESTADO_EVALUACION','?')}"
        )
    return "Evalúa estos proyectos mineros chilenos:\n\n" + "\n".join(lines)


def _call_claude(prompt: str, retries: int = 2) -> List[Dict]:
    """Llama a la API de Claude y parsea la respuesta JSON."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY no configurada")

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",  # rápido y barato para batch scoring
                    "max_tokens": 1500,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"].strip()

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


def run(score_min: int = 45, score_max: int = 65, batch_size: int = 20,
        max_batches: int = 5) -> Dict[str, Any]:
    """
    Corre AI scoring para proyectos en zona gris.

    Args:
        score_min: Score mínimo a evaluar (default 45)
        score_max: Score máximo a evaluar (default 65)
        batch_size: Proyectos por llamada a Claude (default 20)
        max_batches: Máximo de llamadas API (default 5 = 100 proyectos)
    """
    # 1. Buscar proyectos en zona gris
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, company, source, phase, region, score, raw, updated_at
                FROM opportunities
                WHERE score BETWEEN %s AND %s
                  AND source NOT IN (
                    'Portal Minero','BioBioChile','Emol','Cooperativa',
                    'Minería Chilena','COCHILCO Noticias','Diario Financiero',
                    'Revista EI','Radio U. de Chile','Radio Universidad de Chile',
                    'RSS','Lithium Chile','InfoMineria','Mundo Minería',
                    'MLP Proveedores','BHP Careers','AMSA Careers',
                    'Lundin Careers','Collahuasi Careers','Teck Careers'
                  )
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT %s
            """, (score_min, score_max, batch_size * max_batches))
            proyectos = [dict(r) for r in cur.fetchall()]

    if not proyectos:
        return {"ok": True, "msg": "Sin proyectos en zona gris", "evaluados": 0, "actualizados": 0}

    # 2. Procesar en batches
    updates: List[Tuple[int, int, str]] = []  # (new_score, id, razon)
    errors = []
    batches_procesados = 0

    for i in range(0, len(proyectos), batch_size):
        batch = proyectos[i:i + batch_size]
        prompt = _build_prompt(batch)
        id_to_score = {p["id"]: p["score"] for p in batch}

        try:
            resultados = _call_claude(prompt)
            for r in resultados:
                pid = r.get("id")
                ajuste = r.get("ajuste", 0)
                razon = r.get("razon", "")
                if pid not in id_to_score:
                    continue
                ajuste = max(-10, min(10, int(ajuste)))  # clamp
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
