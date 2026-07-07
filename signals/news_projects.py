"""
signals/news_projects.py — Predictor e integrador de hitos y proyectos desde noticias.
================================================================================
Analiza las noticias ingresadas y determina si describen hitos de proyectos
o nuevos proyectos mineros, enriqueciendo la base de datos de manera automatizada.
"""

import sys
import os
import json
import logging
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db
import ai_client
from source_categories import NOTICIA_SOURCES

logger = logging.getLogger("stratmap.news_projects")

SYSTEM_PROMPT = """Eres un extractor de datos estructurados para minería en Chile.
Tu tarea es analizar el título y contenido de una noticia e identificar si describe:
1. Un proyecto minero específico (ej: Quebrada Blanca Fase II, Chuquicamata Subterránea) o faena.
2. Una obra de infraestructura minera relevante.
3. Una licitación o adjudicación de un contrato minero importante.
4. Un hito o evento clave de un proyecto (ej: aprobación ambiental/RCA, inicio de construcción, inauguración, paralización, etc.).

Debes responder estrictamente en formato JSON válido, sin bloques de código ```json o texto adicional.
Formato exacto de respuesta:
{
  "is_project_related": true o false,
  "project_name": "Nombre limpio del proyecto o faena" (o null),
  "company": "Compañía mandante/titular de la mina" (o null),
  "region": "Región de Chile donde se ubica, ej: Antofagasta, Atacama, Coquimbo, etc." (o null),
  "phase": "Fase descrita: 'Calificación', 'Aprobado', 'Construcción', 'Licitación', 'Operación' u otra" (o null),
  "milestone_text": "Breve resumen en una frase del hito o noticia" (o null)
}
"""

def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def get_words(text: str) -> set:
    if not text:
        return set()
    # Extraer palabras de 4 o más letras, en minúsculas y sin acentos
    text = text.lower()
    text = re.sub(r"[áäâ]", "a", text)
    text = re.sub(r"[éëê]", "e", text)
    text = re.sub(r"[íïî]", "i", text)
    text = re.sub(r"[óöô]", "o", text)
    text = re.sub(r"[úüû]", "u", text)
    words = re.findall(r"[a-z0-9]{4,}", text)
    # Stemming básico para español (plurales y vocales finales de género)
    stemmed = []
    for w in words:
        if len(w) >= 5:
            if w.endswith("s"):
                w = w[:-1]
            if w.endswith("a") or w.endswith("o") or w.endswith("e"):
                w = w[:-1]
        stemmed.append(w)
    return set(stemmed)

def is_title_similar(title1: str, title2: str) -> bool:
    w1 = get_words(title1)
    w2 = get_words(title2)
    if not w1 or not w2:
        return False
    intersection = w1.intersection(w2)
    if not intersection:
        return False
    # Al menos 55% de coincidencia en el título más corto para evitar falsos positivos
    min_len = min(len(w1), len(w2))
    overlap = len(intersection) / min_len
    return overlap >= 0.55

def run(force_recompute: bool = False, limit: int = 15) -> dict:
    """
    Analiza noticias no procesadas, detecta si corresponden a proyectos/hitos,
    y nutre proyectos existentes o crea nuevos según corresponda.
    """
    logger.info("Iniciando análisis de noticias para proyectos...")
    
    where = "AND (raw->>'news_project_processed') IS NULL"
    if force_recompute:
        where = ""

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, source, title, url, company, region, published_at, created_at, entry, raw
                FROM opportunities
                WHERE (source = ANY(%s) OR phase = 'Noticia')
                  AND is_duplicate = FALSE
                  {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (list(NOTICIA_SOURCES), limit))
            news_items = [dict(r) for r in cur.fetchall()]

    if not news_items:
        logger.info("No hay noticias pendientes de procesar.")
        return {"processed": 0, "enriched": 0, "created": 0}

    processed = 0
    enriched = 0
    created = 0

    for news in news_items:
        news_id = news["id"]
        title = news["title"]
        entry = news["entry"] or ""
        news_url = news["url"]
        news_source = news["source"]
        published_at = news["published_at"] or news["created_at"]
        raw = news["raw"] or {}

        # 1. Llamar al LLM para analizar relevancia de proyecto
        prompt = f"Título de noticia: {title}\nDetalle de noticia: {entry}"
        try:
            llm_response = ai_client.call_llm(prompt=prompt, system=SYSTEM_PROMPT)
            cleaned = clean_json_text(llm_response)
            data = json.loads(cleaned)
        except Exception as e:
            logger.error(f"Error procesando LLM o parseando JSON para noticia id={news_id}: {e}")
            # Marcar como procesado con error para no ciclar infinitamente
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    raw["news_project_processed"] = True
                    raw["news_project_error"] = str(e)
                    cur.execute("""
                        UPDATE opportunities
                        SET raw = %(raw)s::jsonb, updated_at = NOW()
                        WHERE id = %(id)s
                    """, {"raw": json.dumps(raw, ensure_ascii=False), "id": news_id})
                conn.commit()
            processed += 1
            continue

        is_proj = data.get("is_project_related", False)
        project_name = data.get("project_name")
        company = data.get("company")
        region = data.get("region")
        phase = data.get("phase")
        milestone_text = data.get("milestone_text")

        if not is_proj or not company:
            # Marcar como no relacionado y seguir
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    raw["news_project_processed"] = True
                    raw["is_project_related"] = False
                    cur.execute("""
                        UPDATE opportunities
                        SET raw = %(raw)s::jsonb, updated_at = NOW()
                        WHERE id = %(id)s
                    """, {"raw": json.dumps(raw, ensure_ascii=False), "id": news_id})
                conn.commit()
            processed += 1
            continue

        # Normalizar compañía y buscar si ya existe el proyecto
        norm_company = db.normalize_company(company) or company
        
        # Intentar buscar proyecto existente
        matched_project = None
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Buscar en proyectos reales de la misma compañía
                cur.execute("""
                    SELECT id, title, company, region, raw, score, signal_score
                    FROM opportunities
                    WHERE company = %(company)s
                      AND is_duplicate = FALSE
                      AND (source = 'SEA' OR source = 'Noticias Proyectos' OR phase != 'Noticia')
                """, {"company": norm_company})
                candidate_projects = [dict(r) for r in cur.fetchall()]

        # Buscar coincidencia de título / nombre de proyecto
        search_name = project_name or title
        for proj in candidate_projects:
            if is_title_similar(proj["title"], search_name):
                matched_project = proj
                break

        if matched_project:
            # ENRIQUECER PROYECTO EXISTENTE (Nutrir con la noticia)
            proj_id = matched_project["id"]
            proj_raw = matched_project["raw"] or {}
            if not isinstance(proj_raw, dict):
                proj_raw = {}
            
            signals = proj_raw.get("signals") or []
            if not isinstance(signals, list):
                signals = []

            # Verificar si ya tiene este link de noticia registrado
            if not any(s.get("url") == news_url for s in signals):
                signals.append({
                    "source": news_source,
                    "title": title,
                    "url": news_url,
                    "published_at": published_at.isoformat() if isinstance(published_at, datetime) else str(published_at),
                    "detail": milestone_text or title
                })
                proj_raw["signals"] = signals
                
                # Incrementar signal_score por nueva confirmación de noticia
                cur_sig = matched_project.get("signal_score") or 0
                new_sig = min(100, cur_sig + 12)  # Boost de +12 pts
                
                with db.get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE opportunities
                            SET raw = %(raw)s::jsonb,
                                signal_score = %(signal_score)s,
                                last_signal_at = NOW(),
                                updated_at = NOW()
                            WHERE id = %(id)s
                        """, {
                            "raw": json.dumps(proj_raw, ensure_ascii=False),
                            "signal_score": new_sig,
                            "id": proj_id
                        })
                        conn.commit()
            
            # Marcar noticia original como procesada y vincularla al proyecto
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    raw["news_project_processed"] = True
                    raw["is_project_related"] = True
                    raw["linked_project_id"] = proj_id
                    cur.execute("""
                        UPDATE opportunities
                        SET raw = %(raw)s::jsonb, updated_at = NOW()
                        WHERE id = %(id)s
                    """, {"raw": json.dumps(raw, ensure_ascii=False), "id": news_id})
                    conn.commit()
            
            logger.info(f"Noticia id={news_id} vinculada al proyecto existente id={proj_id} ({matched_project['title']})")
            enriched += 1

        else:
            # CREAR NUEVO PROYECTO
            new_proj_title = project_name or title
            new_url = f"project-news://{news_id}"
            
            new_raw = {
                "is_custom_news_project": True,
                "original_news_url": news_url,
                "signals": [
                    {
                        "source": news_source,
                        "title": title,
                        "url": news_url,
                        "published_at": published_at.isoformat() if isinstance(published_at, datetime) else str(published_at),
                        "detail": milestone_text or title
                    }
                ]
            }

            new_opp = {
                "source": "Noticias Proyectos",
                "title": new_proj_title,
                "url": new_url,
                "company": norm_company,
                "contractor": None,
                "industry": "Minería",
                "region": region or "Nacional",
                "phase": phase or "Detectada",
                "score": 45,  # Score base
                "signal_score": 15,  # initial boost
                "entry": f"Proyecto detectado en prensa: {milestone_text or title}",
                "raw": new_raw,
                "published_at": published_at,
                "last_signal_at": datetime.now(timezone.utc)
            }

            try:
                db.upsert_opportunities([new_opp])
                
                # Buscar id del nuevo proyecto insertado para vincularlo a la noticia
                with db.get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM opportunities WHERE url = %s", (new_url,))
                        new_proj_id = cur.fetchone()["id"]
                
                # Marcar noticia original como procesada y vincularla al nuevo proyecto
                with db.get_conn() as conn:
                    with conn.cursor() as cur:
                        raw["news_project_processed"] = True
                        raw["is_project_related"] = True
                        raw["linked_project_id"] = new_proj_id
                        cur.execute("""
                            UPDATE opportunities
                            SET raw = %(raw)s::jsonb, updated_at = NOW()
                            WHERE id = %(id)s
                        """, {"raw": json.dumps(raw, ensure_ascii=False), "id": news_id})
                        conn.commit()
                
                logger.info(f"Creado nuevo proyecto '{new_proj_title}' (id={new_proj_id}) desde noticia id={news_id}")
                created += 1
            except Exception as e:
                logger.error(f"Error insertando nuevo proyecto desde noticia id={news_id}: {e}")

        processed += 1

    return {"processed": processed, "enriched": enriched, "created": created}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run(force_recompute=True, limit=5)
    print(res)
