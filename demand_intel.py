"""
demand_intel.py — Motor de Inteligencia de Demanda para Stratmap
Analiza proyectos mineros (SEA, SIGEX, Codelco, etc.) y genera con IA
la lista de servicios/proveedores que se van a necesitar, con prioridad
y horizonte temporal estimado.

Almacena en opportunities.services_needed (JSONB):
{
  "phase_label": "Construcción",
  "horizon_months": 18,
  "services": [
    {
      "category": "Ingeniería y Construcción",
      "name": "Empresa EPCM",
      "priority": "alta",
      "description": "Gestión integral del proyecto de construcción"
    },
    ...
  ],
  "summary": "Proyecto de expansión de planta SAL...",
  "analyzed_at": "2026-03-07T..."
}
"""
import os
import json
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

# ── Taxonomía de fases y sus servicios típicos (como base/hint para IA) ────────
PHASE_HINTS = {
    "exploración": {
        "label": "Exploración",
        "horizon": "6-18 meses",
        "services_hint": ["sondaje diamantino", "campamento base", "transporte en terreno",
                          "laboratorio de análisis de muestras", "topografía", "seguridad industrial",
                          "servicio de agua potable", "geología de superficie", "drones y geofísica"]
    },
    "pre-factibilidad": {
        "label": "Pre-Factibilidad",
        "horizon": "12-24 meses",
        "services_hint": ["ingeniería básica", "estudios de impacto ambiental", "consultoría geológica",
                          "laboratorios metalúrgicos", "topografía detallada", "estudios hidrogeológicos",
                          "consultoras ambientales", "servicios de perforación"]
    },
    "construcción": {
        "label": "Construcción",
        "horizon": "6-36 meses",
        "services_hint": ["empresa EPCM", "movimiento de tierras", "obras civiles y hormigón",
                          "instalaciones eléctricas", "tuberías y piping", "montaje industrial",
                          "estructuras de acero", "transporte de carga sobredimensionada",
                          "grúas y equipos pesados", "campamentos obreros", "alimentación industrial",
                          "seguridad y vigilancia", "laboratorio de control de calidad",
                          "equipos de ventilación", "explosivos y tronadura"]
    },
    "operación": {
        "label": "Operación",
        "horizon": "Continuo",
        "services_hint": ["mantenimiento de equipos", "repuestos e insumos", "reactivos químicos",
                          "servicios de alimentación (casino)", "transporte de personal",
                          "ropa de trabajo y EPP", "lubricantes y combustibles", "servicios médicos",
                          "capacitación y entrenamiento", "instrumentación y control",
                          "servicios de limpieza industrial", "gestión de residuos",
                          "energía eléctrica y agua industrial"]
    },
    "modificación": {
        "label": "Modificación / Ampliación",
        "horizon": "6-24 meses",
        "services_hint": ["ingeniería de detalle", "obras civiles adicionales", "montaje eléctrico",
                          "equipos de proceso", "automatización y control", "piping especializado",
                          "pruebas y puesta en marcha", "capacitación técnica"]
    },
    "cierre": {
        "label": "Cierre / Abandono",
        "horizon": "12-36 meses",
        "services_hint": ["remediación ambiental", "revegetación", "retiro de equipos",
                          "tratamiento de aguas ácidas", "geotecnia de cierre",
                          "monitoreo ambiental post-cierre", "demolición controlada"]
    }
}


def _detect_phase_key(phase: str, title: str) -> str:
    """Detecta la fase clave basándose en el texto."""
    text = (phase or "" + " " + title or "").lower()
    if any(w in text for w in ["construcción", "construc", "epc", "obras civiles", "erección"]):
        return "construcción"
    if any(w in text for w in ["explorac", "sondaje", "perforac", "drill"]):
        return "exploración"
    if any(w in text for w in ["operac", "producción", "planta en operación", "funcionamiento"]):
        return "operación"
    if any(w in text for w in ["modificac", "ampliación", "ampliacion", "optimización", "mejoramiento", "continuidad"]):
        return "modificación"
    if any(w in text for w in ["cierre", "abandono", "desmantelamiento"]):
        return "cierre"
    if any(w in text for w in ["factibilidad", "prefactibilidad", "ingeniería básica"]):
        return "pre-factibilidad"
    # SEA: "En Calificación" generalmente es construcción o modificación grande
    if any(w in text for w in ["en calificación", "calificacion", "sea"]):
        return "construcción"
    return "operación"


def _analyze_project(project: dict) -> dict | None:
    """
    Llama a Claude Haiku para analizar un proyecto y generar la lista de servicios.
    Retorna dict con services_needed o None si falla.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("[demand_intel] ANTHROPIC_API_KEY no configurada")
        return None

    title = project.get("title", "")
    phase = project.get("phase", "")
    company = project.get("company", "")
    region = project.get("region", "")
    raw = project.get("raw") or {}
    tipologia = raw.get("NOMBRE_TIPOLOGIA", "")
    inversion = raw.get("INVERSION_US")
    inversion_str = f"USD {inversion:,.0f}" if inversion else "No especificada"

    phase_key = _detect_phase_key(phase, title)
    phase_info = PHASE_HINTS.get(phase_key, PHASE_HINTS["operación"])

    prompt = f"""Eres un experto en la industria minera chilena. Analiza este proyecto minero y genera la lista detallada de servicios y proveedores que serán necesarios.

PROYECTO:
- Nombre: {title}
- Empresa: {company}
- Región: {region}
- Fase actual: {phase}
- Tipología SEA: {tipologia}
- Inversión estimada: {inversion_str}

INSTRUCCIONES:
1. Identifica entre 8 y 15 servicios/rubros específicos que este proyecto va a necesitar contratar
2. Agrúpalos por categoría
3. Indica prioridad: "alta" (necesario para el proyecto), "media" (probable), "baja" (posible)
4. Piensa en el contexto chileno: qué tipo de empresa local podría proveer esto
5. Sé específico — no digas "servicios generales", di "empresa de sondaje diamantino" o "proveedor de explosivos ANFO"

Responde SOLO con JSON válido, sin texto adicional, sin markdown, exactamente así:
{{
  "phase_label": "nombre de la fase en español",
  "horizon_months": número estimado de meses hasta que se contraten (número entero),
  "summary": "Una oración resumiendo qué tipo de demanda genera este proyecto",
  "services": [
    {{
      "category": "Nombre de categoría",
      "name": "Nombre específico del servicio o proveedor",
      "priority": "alta|media|baja",
      "description": "Breve descripción de qué se necesita exactamente"
    }}
  ]
}}"""

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": MODEL,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"].strip()

        # Limpiar posibles backticks
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        return result

    except Exception as e:
        logger.warning(f"[demand_intel] Error analizando proyecto '{title[:50]}': {e}")
        return None


def _get_db_conn():
    import db as _db
    return _db.get_conn()


def init_demand_intel_db():
    """Agrega columna services_needed a opportunities si no existe."""
    conn = _get_db_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE opportunities
                ADD COLUMN IF NOT EXISTS services_needed JSONB NULL;
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_opportunities_services
                ON opportunities USING gin(services_needed)
                WHERE services_needed IS NOT NULL;
            """)
    conn.close()
    logger.info("[demand_intel] DB inicializada")


def run(
    batch_size: int = 30,
    max_batches: int = 10,
    force_reanalyze: bool = False,
    source_filter: str | None = None
) -> dict:
    """
    Analiza proyectos mineros y guarda los servicios necesarios.

    Args:
        batch_size: proyectos por lote
        max_batches: máximo de lotes a procesar
        force_reanalyze: si True, re-analiza proyectos ya procesados
        source_filter: filtrar por fuente ('SEA', 'Codelco', etc.)

    Returns:
        dict con estadísticas del run
    """
    conn = _get_db_conn()

    # Obtener proyectos a analizar
    try:
        with conn.cursor() as cur:
            # Excluir noticias y empleos — solo proyectos e inversiones reales
            exclude_sources = [
                'Lithium Chile', 'Portal Minero', 'Revista EI', 'Minería Chilena',
                'Diario Financiero', 'COCHILCO Noticias', 'InfoMineria',
                'Mundo Minería', 'RSS', 'BHP Careers', 'AMSA Careers',
                'Lundin Careers', 'Teck Careers', 'Collahuasi Careers'
            ]

            where_clauses = ["source != ALL(%s)", "score >= 50"]
            params: list = [exclude_sources]

            if not force_reanalyze:
                where_clauses.append("services_needed IS NULL")

            if source_filter:
                where_clauses.append("source = %s")
                params.append(source_filter)

            where_sql = " AND ".join(where_clauses)
            limit = batch_size * max_batches

            cur.execute(f"""
                SELECT id, title, phase, company, region, raw, source, score
                FROM opportunities
                WHERE {where_sql}
                ORDER BY score DESC, updated_at DESC
                LIMIT %s
            """, params + [limit])

            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        logger.info("[demand_intel] No hay proyectos pendientes de análisis")
        return {"analyzed": 0, "errors": 0, "skipped": 0}

    logger.info(f"[demand_intel] Analizando {len(rows)} proyectos...")

    analyzed = 0
    errors = 0
    skipped = 0

    for i, row in enumerate(rows):
        opp_id  = row["id"]
        title   = row["title"]
        phase   = row["phase"]
        company = row["company"]
        region  = row["region"]
        raw     = row["raw"]
        source  = row["source"]
        score   = row["score"]

        project = {
            "id": opp_id,
            "title": title or "",
            "phase": phase or "",
            "company": company or "",
            "region": region or "",
            "raw": raw or {},
            "source": source or "",
            "score": score or 0
        }

        # Skip si el título es muy corto o sin contexto
        if len(project["title"]) < 20:
            skipped += 1
            continue

        result = _analyze_project(project)

        if result:
            try:
                conn2 = _get_db_conn()
                with conn2:
                    with conn2.cursor() as cur:
                        cur.execute("""
                            UPDATE opportunities
                            SET services_needed = %s
                            WHERE id = %s
                        """, (json.dumps(result), opp_id))
                conn2.close()
                analyzed += 1
                logger.info(f"[demand_intel] [{i+1}/{len(rows)}] OK: {title[:60]}")
            except Exception as e:
                logger.error(f"[demand_intel] Error guardando proyecto {opp_id}: {e}")
                errors += 1
        else:
            errors += 1

        # Rate limiting suave entre llamadas
        if (i + 1) % 10 == 0:
            import time
            time.sleep(1)

    logger.info(f"[demand_intel] Completado: {analyzed} analizados, {errors} errores, {skipped} omitidos")
    return {"analyzed": analyzed, "errors": errors, "skipped": skipped, "total": len(rows)}
