"""
mandante_scorer.py — Scoring de temperatura de mandantes con IA
===============================================================
Analiza noticias recientes + señales de empleo por mandante y usa Claude
para asignar un heat_score (0-100) que indica qué tan activo/caliente está
cada mandante en el mercado minero chileno.

Se integra al worker (sea_ingest.py) y corre después del ai_matcher.
También se puede ejecutar manualmente: python mandante_scorer.py
"""

import os, sys, json, time
from typing import Any, Dict, List
import anthropic
import db

MODEL      = "claude-sonnet-4-6"
MAX_TOKENS = 3000
BATCH_SIZE = 15  # mandantes por llamada

NEWS_SOURCES_PY = {
    'Lithium Chile','Portal Minero','Revista EI','Minería Chilena',
    'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Minería',
    'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
    'Mundo Minería',
}

STOPWORDS = {'spa','ltda','s.a','s.a.','sa','de','del','la','el','los','las',
             'y','en','por','para','con','una','uno','corp','inc','chile'}


def get_keywords(company: str) -> List[str]:
    """Extrae keywords significativas del nombre de la empresa."""
    return [w.lower() for w in company.replace('.','').replace(',','').split()
            if len(w) > 3 and w.lower() not in STOPWORDS]


def fetch_context(company: str) -> Dict[str, Any]:
    """Obtiene noticias y señales de empleo para un mandante."""
    keywords = get_keywords(company)
    if not keywords:
        keywords = [company.lower()[:10]]

    kw_conditions = " OR ".join(f"LOWER(title) LIKE '%{kw}%'" for kw in keywords[:4])

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Noticias recientes (sin límite de fecha)
            cur.execute(f"""
                SELECT title, source, published_at::date as fecha
                FROM opportunities
                WHERE source = ANY(%(sources)s)
                  AND (LOWER(TRIM(company)) = LOWER(%(company)s) OR ({kw_conditions}))
                ORDER BY published_at DESC LIMIT 20
            """, {"sources": list(NEWS_SOURCES_PY), "company": company})
            noticias = [dict(r) for r in cur.fetchall()]

            # Señales de empleo
            cur.execute("""
                SELECT SUM(jobs_count) as total_jobs,
                       MAX(signal_score) as top_signal,
                       COUNT(*) as n_proyectos
                FROM opportunities
                WHERE LOWER(TRIM(company)) = LOWER(%(company)s)
                  AND jobs_count > 0
            """, {"company": company})
            empleo = dict(cur.fetchone() or {})

            # Proyectos activos (conteo)
            cur.execute("""
                SELECT COUNT(*) as n
                FROM opportunities
                WHERE LOWER(TRIM(company)) = LOWER(%(company)s)
                  AND source NOT IN ('manual','SEA')
                  AND source != ANY(%(news)s)
            """, {"company": company, "news": list(NEWS_SOURCES_PY)})
            n_proyectos = (cur.fetchone() or {}).get("n", 0)

    return {
        "noticias": noticias,
        "total_jobs": int(empleo.get("total_jobs") or 0),
        "top_signal": int(empleo.get("top_signal") or 0),
        "n_proyectos_con_empleo": int(empleo.get("n_proyectos") or 0),
        "n_proyectos_activos": int(n_proyectos or 0),
    }


def build_batch_prompt(batch: List[Dict]) -> str:
    mandantes_block = []
    for i, item in enumerate(batch):
        ctx = item["context"]
        news_titles = "\n".join(
            f"  [{n.get('fecha','')}] {n['title']} ({n['source']})"
            for n in ctx["noticias"][:10]
        ) or "  (sin noticias recientes)"

        mandantes_block.append(f"""
[{i+1}] EMPRESA: {item['company']}
Proyectos activos en BD: {ctx['n_proyectos_activos']}
Empleos activos detectados: {ctx['total_jobs']} (en {ctx['n_proyectos_con_empleo']} proyectos)
Señal de empleo score: {ctx['top_signal']}
Noticias recientes ({len(ctx['noticias'])}):
{news_titles}""")

    return f"""Eres un analista experto en el sector minero chileno.
Evalúa el nivel de actividad actual de cada empresa minera basándote en su presencia en noticias y señales de empleo.

{chr(10).join(mandantes_block)}

Para cada empresa asigna:
- heat_score (0-100): qué tan activa/caliente está en este momento
  * 80-100: Muy activa — muchas noticias recientes, empleos, proyectos en marcha
  * 60-79:  Activa — actividad notable, presencia mediática
  * 40-59:  Moderada — algo de actividad pero no destaca
  * 20-39:  Baja — poca actividad detectable
  * 0-19:   Sin señal — sin noticias ni empleos recientes
- heat_label: exactamente uno de "🔥 Muy activa" | "⚡ Activa" | "📊 Moderada" | "💤 Baja actividad"
- heat_reason: 1 oración explicando POR QUÉ ese score (menciona proyectos o noticias específicas si las hay)
- trending_topics: lista de 2-4 temas recurrentes en las noticias (ej: ["expansión Escondida","litio","conflicto agua"])

Responde SOLO JSON sin markdown:
{{
  "results": [
    {{
      "company": "<nombre exacto>",
      "heat_score": <0-100>,
      "heat_label": "<label>",
      "heat_reason": "<razón>",
      "trending_topics": ["tema1", "tema2"]
    }}
  ]
}}"""


def score_batch(client: anthropic.Anthropic, batch: List[Dict]) -> List[Dict]:
    prompt = build_batch_prompt(batch)
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw).get("results", [])
    except Exception as e:
        print(f"  [scorer] Error batch: {e}")
        return []


def run(min_proyectos: int = 1) -> Dict:
    print("[mandante_scorer] Iniciando scoring de temperatura...")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[mandante_scorer] ERROR: ANTHROPIC_API_KEY no configurada")
        return {"error": "no_api_key"}

    # Obtener todos los mandantes con proyectos
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT company
                FROM opportunities
                WHERE company IS NOT NULL AND TRIM(company) != ''
                  AND source NOT IN ('manual','SEA')
                ORDER BY company
            """)
            companies = [r[0] for r in cur.fetchall() if r[0]]

    print(f"[mandante_scorer] {len(companies)} empresas a evaluar")

    # Obtener contexto para cada una
    items = []
    for company in companies:
        ctx = fetch_context(company)
        # Solo procesar si tiene algo que analizar
        if ctx["n_proyectos_activos"] > 0 or ctx["total_jobs"] > 0 or ctx["noticias"]:
            items.append({"company": company, "context": ctx})

    print(f"[mandante_scorer] {len(items)} con contexto relevante")

    if not items:
        return {"scored": 0}

    client  = anthropic.Anthropic(api_key=api_key)
    scored  = 0
    batches = [items[i:i+BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    for bi, batch in enumerate(batches, 1):
        print(f"  [batch {bi}/{len(batches)}] {len(batch)} mandantes...")
        results = score_batch(client, batch)

        # Lookup original context by company
        ctx_map = {item["company"]: item["context"] for item in batch}

        for r in results:
            company = r.get("company","")
            ctx = ctx_map.get(company, {})
            try:
                db.upsert_mandante_heat(
                    company        = company,
                    heat_score     = max(0, min(100, int(r.get("heat_score", 0)))),
                    heat_label     = str(r.get("heat_label",""))[:50],
                    heat_reason    = str(r.get("heat_reason",""))[:500],
                    n_noticias     = len(ctx.get("noticias", [])),
                    n_empleos      = ctx.get("total_jobs", 0),
                    trending_topics= [str(t)[:100] for t in r.get("trending_topics",[])[:5]],
                )
                scored += 1
                print(f"    → {company[:40]:40s} heat={r['heat_score']:3d} {r.get('heat_label','')}")
            except Exception as e:
                print(f"    [err] {company}: {e}")

        if bi < len(batches):
            time.sleep(1.0)

    print(f"[mandante_scorer] DONE — scored={scored}")
    return {"scored": scored, "total": len(items)}


if __name__ == "__main__":
    db.init_ai_db()
    run()
