"""
signals/empleos_signals.py
Cruza ofertas de empleo mineras con proyectos en la BD
y actualiza signal_score + signal_detail.

Lógica:
- Busca proyectos con misma empresa Y/O región
- Agrupa empleos por empresa+región
- Suma puntos según tipo de cargo y cantidad
- Actualiza signal_score en la BD
"""

from typing import Any, Dict, List, Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db

# Cuántos puntos adicionales por volumen de empleos
def volume_bonus(count: int) -> int:
    if count >= 10: return 10
    if count >= 5:  return 6
    if count >= 3:  return 4
    if count >= 2:  return 2
    return 0

def normalize(text: str) -> str:
    return text.lower().strip() if text else ""

def companies_match(job_company: str, proj_company: str) -> bool:
    """True si el empleo y el proyecto son de la misma empresa."""
    jc = normalize(job_company)
    pc = normalize(proj_company)
    if not jc or not pc: return False

    # Alias conocidos
    ALIASES = {
        "codelco": ["codelco", "corporación nacional del cobre"],
        "bhp": ["bhp", "escondida", "minera escondida", "bhp billiton"],
        "sqm": ["sqm", "soquimich", "sociedad química"],
        "collahuasi": ["collahuasi", "compañía minera doña inés de collahuasi"],
        "antofagasta minerals": ["antofagasta minerals", "antofagasta plc", "minera los pelambres",
                                  "centinela", "zaldívar"],
        "teck": ["teck", "quebrada blanca", "carmen de andacollo"],
        "kinross": ["kinross", "la coipa", "maricunga"],
    }
    for canonical, variants in ALIASES.items():
        if any(v in jc for v in variants) and any(v in pc for v in variants):
            return True

    # Match directo parcial
    return jc in pc or pc in jc or any(w in pc for w in jc.split() if len(w) > 4)


def run_empleos_signals(job_items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Recibe lista de empleos (output de fetch_indeed + fetch_portales),
    cruza con proyectos en BD y actualiza signal_score.
    Retorna dict {opp_id: puntos_sumados}
    """
    if not job_items:
        print("[empleos_signals] Sin empleos para procesar")
        return {}

    # Agrupar empleos por (empresa, región)
    groups: Dict[str, Dict] = {}
    for job in job_items:
        company = normalize(job.get("company") or job.get("company_raw") or "")
        region  = job.get("region") or ""
        key = f"{company}|{region}"
        if key not in groups:
            groups[key] = {
                "company": job.get("company") or job.get("company_raw"),
                "region": region,
                "jobs": [],
                "max_pts": 0,
            }
        groups[key]["jobs"].append(job)
        groups[key]["max_pts"] = max(groups[key]["max_pts"], job.get("signal_pts", 3))

    print(f"[empleos_signals] {len(job_items)} empleos → {len(groups)} grupos empresa+región")

    # Obtener todos los proyectos activos de la BD
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, company, region, source, phase
                FROM opportunities
                WHERE phase != 'Noticia'
                AND (published_at > NOW() - INTERVAL '18 months' OR published_at IS NULL)
            """)
            projects = cur.fetchall()
            cols = [d[0] for d in cur.description]
            projects = [dict(zip(cols, row)) for row in projects]

    print(f"[empleos_signals] {len(projects)} proyectos activos para cruzar")

    updates: Dict[int, Dict] = {}  # opp_id → {pts, detail}

    for group_key, group in groups.items():
        g_company = group["company"] or ""
        g_region  = group["region"]
        g_count   = len(group["jobs"])
        g_max_pts = group["max_pts"]
        g_vol     = volume_bonus(g_count)

        # Puntos base del grupo = max señal individual + bonus por volumen
        group_pts = g_max_pts + g_vol

        # Tipo de señal predominante
        types = [j.get("signal_type","general") for j in group["jobs"]]
        dominant_type = max(set(types), key=types.count)

        detail = f"{g_count} empleo{'s' if g_count>1 else ''} {dominant_type}"
        if g_company: detail += f" en {g_company}"
        if g_region:  detail += f" ({g_region})"

        for proj in projects:
            proj_company = proj.get("company") or ""
            proj_region  = proj.get("region") or ""

            match_company = companies_match(g_company, proj_company)
            match_region  = g_region and g_region == proj_region

            if not match_company and not match_region:
                continue

            # Calcular puntos según tipo de match
            pts = 0
            if match_company and match_region:
                pts = group_pts          # Match perfecto
            elif match_company:
                pts = int(group_pts * 0.8)   # Solo empresa
            elif match_region:
                pts = int(group_pts * 0.4)   # Solo región

            if pts == 0:
                continue

            pid = proj["id"]
            if pid not in updates:
                updates[pid] = {"pts": 0, "details": []}
            updates[pid]["pts"] = min(updates[pid]["pts"] + pts, 30)  # cap 30pts por proyecto
            updates[pid]["details"].append(detail)

    # Aplicar updates a la BD
    applied = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for opp_id, update in updates.items():
                pts = update["pts"]
                detail_str = " | ".join(update["details"][:3])
                cur.execute("""
                    UPDATE opportunities
                    SET signal_score = LEAST(COALESCE(signal_score, 0) + %s, 30),
                        signal_detail = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (pts, detail_str, opp_id))
                if cur.rowcount:
                    applied += 1
        conn.commit()

    print(f"[empleos_signals] {applied} proyectos actualizados con señales de empleo")
    return {oid: u["pts"] for oid, u in updates.items()}


if __name__ == "__main__":
    # Test con datos dummy
    test_jobs = [
        {"company": "Codelco", "company_raw": "Codelco", "region": "Antofagasta",
         "title": "Ingeniero de Proyecto Chuquicamata", "signal_type": "construcción/proyecto",
         "signal_pts": 15},
        {"company": "Codelco", "company_raw": "Codelco", "region": "Antofagasta",
         "title": "Supervisor de Construcción", "signal_type": "construcción/proyecto",
         "signal_pts": 15},
        {"company": "BHP/Escondida", "company_raw": "BHP", "region": "Antofagasta",
         "title": "Jefe de Operaciones", "signal_type": "operaciones", "signal_pts": 8},
    ]
    result = run_empleos_signals(test_jobs)
    print(f"Proyectos actualizados: {result}")
