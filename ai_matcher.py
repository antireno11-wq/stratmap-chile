"""
ai_matcher.py — Batch nocturno que usa Claude para scorear oportunidades
contra el perfil de servicios de cada usuario.

Corre como cron job en Railway:
  python ai_matcher.py

Variables de entorno requeridas:
  DATABASE_URL      — PostgreSQL connection string
  ANTHROPIC_API_KEY — Claude API key
"""

import os
import sys
import json
import time
from typing import Any, Dict, List, Optional

import anthropic
import db

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400
BATCH_DELAY = 0.5   # segundos entre llamadas para no saturar la API
MAX_PER_RUN = 100   # máximo por corrida (subir a 500 cuando esté probado)


def build_prompt(opp: Dict[str, Any], services: List[Dict[str, Any]], company_name: str) -> str:
    services_text = "\n".join([
        f"- {s['name']}: {s.get('description', '')}" for s in services
    ])
    return f"""Eres un analista de negocios B2B en Chile. Evalúa si la siguiente licitación/proyecto 
es una oportunidad para que la empresa "{company_name}" ofrezca sus servicios.

SERVICIOS QUE OFRECE LA EMPRESA:
{services_text}

LICITACIÓN/PROYECTO A EVALUAR:
Título: {opp.get('title', '')}
Fuente: {opp.get('source', '')}
Industria: {opp.get('industry', '')}
Región: {opp.get('region', '')}
Fase: {opp.get('phase', '')}
Mandante: {opp.get('company', '')}
Score base: {opp.get('score', 0)}

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown:
{{
  "fit_score": <número 0-100>,
  "fit_reason": "<explicación concisa en español de 1-2 oraciones de por qué hay o no hay fit>",
  "service_applicable": "<nombre del servicio más aplicable, o 'Ninguno' si no hay fit>",
  "contact_suggestion": "<rol o cargo de la persona a contactar dentro del proyecto, ej: 'Gerente de Operaciones', 'Jefe de Abastecimiento'>"
}}

Criterios de scoring:
- 80-100: Fit muy alto, el proyecto claramente necesita este servicio
- 60-79: Fit alto, probable necesidad del servicio
- 40-59: Fit medio, posible necesidad indirecta
- 20-39: Fit bajo, relación lejana
- 0-19: Sin fit relevante"""


def score_opportunity(
    client: anthropic.Anthropic,
    opp: Dict[str, Any],
    services: List[Dict[str, Any]],
    company_name: str
) -> Optional[Dict[str, Any]]:
    prompt = build_prompt(opp, services, company_name)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        # Limpiar posibles backticks de markdown
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        # Validar campos requeridos
        return {
            "fit_score": max(0, min(100, int(result.get("fit_score", 0)))),
            "fit_reason": str(result.get("fit_reason", ""))[:500],
            "service_applicable": str(result.get("service_applicable", ""))[:200],
            "contact_suggestion": str(result.get("contact_suggestion", ""))[:200],
        }
    except json.JSONDecodeError as e:
        print(f"  [ai] JSON parse error para opp {opp['id']}: {e} | raw: {raw[:100]}")
        return None
    except Exception as e:
        print(f"  [ai] Error para opp {opp['id']}: {type(e).__name__}: {e}")
        return None


def run(user_id: int, limit: int = MAX_PER_RUN) -> dict:
    print(f"[ai_matcher] Iniciando batch para user_id={user_id} (limit={limit})")

    # 1. Verificar API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ai_matcher] ERROR: ANTHROPIC_API_KEY no está configurada")
        return {"ok": False, "error": "no_api_key"}

    # 2. Cargar perfil de servicios
    profile = db.get_service_profile(user_id)
    if not profile:
        print(f"[ai_matcher] No hay perfil de servicios para user_id={user_id} — abortando")
        return {"ok": False, "error": "no_profile"}

    services = profile.get("services") or []
    if not services:
        print("[ai_matcher] El perfil no tiene servicios configurados — abortando")
        return {"ok": False, "error": "no_services"}

    company_name = profile.get("company_name", "Mi empresa")
    print(f"[ai_matcher] Empresa: {company_name} | Servicios: {len(services)}")
    for s in services:
        print(f"  · {s['name']}: {s.get('description','')[:60]}")

    # 3. Cargar oportunidades pendientes
    opps = db.list_opportunities_for_ai_scoring(user_id=user_id, limit=limit)
    print(f"[ai_matcher] {len(opps)} oportunidades pendientes de scoring")

    if not opps:
        print("[ai_matcher] Todo al día, nada que procesar")
        return {"ok": True, "scored": 0, "errors": 0}

    # 4. Procesar con Claude
    client = anthropic.Anthropic(api_key=api_key)
    scored = 0
    errors = 0

    for i, opp in enumerate(opps, 1):
        print(f"  [{i}/{len(opps)}] opp_id={opp['id']} — {opp['title'][:60]}...")
        result = score_opportunity(client, opp, services, company_name)

        if result:
            db.upsert_ai_fit(
                opportunity_id=opp["id"],
                user_id=user_id,
                fit_score=result["fit_score"],
                fit_reason=result["fit_reason"],
                service_applicable=result["service_applicable"],
                contact_suggestion=result["contact_suggestion"],
                model_version=MODEL
            )
            scored += 1
            print(f"    → fit_score={result['fit_score']} | {result['fit_reason'][:80]}")
        else:
            errors += 1

        time.sleep(BATCH_DELAY)

    print(f"[ai_matcher] DONE — scored={scored} errors={errors}")
    return {"ok": True, "scored": scored, "errors": errors}


if __name__ == "__main__":
    # CLI: python ai_matcher.py <user_id>
    if len(sys.argv) < 2:
        print("Usage: python ai_matcher.py <user_id>")
        sys.exit(1)
    db.init_ai_db()
    run(user_id=int(sys.argv[1]))
