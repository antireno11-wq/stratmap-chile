"""
signals/sea_signals.py
Convierte proyectos SEA en señales que suben el score de licitaciones/proyectos
activos del mismo titular (mandante).

Lógica:
- Un SEA en evaluación indica que el titular planea actividad futura
- Si el titular ya tiene licitaciones activas → les sube signal_score
- Todos los estados SEA son relevantes (En calificación, Aprobado, etc.)
- El SEA mismo NO aparece en la tabla de proyectos
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db

# Puntos según estado SEA
SEA_PHASE_POINTS = {
    "aprobado":        20,   # Ya tiene aprobación ambiental — alta probabilidad de licitar
    "en construcción": 18,   # En ejecución — definitivamente están contratando
    "en operación":    15,   # Operando — contratos de mantención y operación
    "en calificación": 12,   # En evaluación — señal temprana fuerte
    "favorable":       18,   # RCA favorable
    "desistido":        0,   # No aplica
    "rechazado":        0,   # No aplica
    "caducado":         0,   # No aplica
}

COMPANY_ALIASES = {
    "codelco": ["codelco", "corporación nacional del cobre", "corp. nac. del cobre"],
    "bhp":     ["bhp", "escondida", "minera escondida", "bhp billiton"],
    "sqm":     ["sqm", "soquimich", "sociedad química y minera"],
    "collahuasi": ["collahuasi", "doña inés de collahuasi"],
    "antofagasta minerals": ["antofagasta minerals", "antofagasta plc", "los pelambres",
                             "centinela", "zaldívar", "antucoya"],
    "teck": ["teck", "quebrada blanca", "carmen de andacollo"],
    "kinross": ["kinross", "la coipa", "maricunga"],
    "barrick": ["barrick", "pascua-lama", "veladero"],
    "glencore": ["glencore", "lomas bayas"],
    "enami": ["enami", "empresa nacional de minería"],
    "sqm": ["sqm", "soquimich"],
    "angloamerican": ["anglo american", "angloamerican", "los bronces", "el soldado"],
}


def normalize(text: str) -> str:
    return text.lower().strip() if text else ""


def match_company(sea_company: str, proj_company: str) -> bool:
    """True si el titular del SEA coincide con el mandante del proyecto."""
    sc = normalize(sea_company)
    pc = normalize(proj_company)
    if not sc or not pc:
        return False

    # Match directo
    if sc in pc or pc in sc:
        return True

    # Match por aliases
    for canonical, variants in COMPANY_ALIASES.items():
        sc_matches = any(v in sc for v in variants)
        pc_matches = any(v in pc for v in variants)
        if sc_matches and pc_matches:
            return True

    # Match por palabra significativa (>5 chars)
    sc_words = [w for w in sc.split() if len(w) > 5]
    return any(w in pc for w in sc_words)


def get_sea_signal_pts(phase: str) -> int:
    """Retorna puntos según fase SEA."""
    if not phase:
        return 8  # Default si no hay fase
    p = normalize(phase)
    for key, pts in SEA_PHASE_POINTS.items():
        if key in p:
            return pts
    return 8  # Default para fases no reconocidas


def run_sea_signals() -> dict:
    """
    Corre el matcher SEA → proyectos activos.
    Actualiza signal_score de proyectos del mismo titular.
    Retorna dict con estadísticas.
    """
    print("[sea_signals] Iniciando...")

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Obtener todos los SEA
            cur.execute("""
                SELECT id, title, company, region, phase, score
                FROM opportunities
                WHERE source = 'sea'
                AND company IS NOT NULL
                AND company != ''
            """)
            sea_rows = cur.fetchall()
            sea_cols = [d[0] for d in cur.description]
            sea_projects = [dict(zip(sea_cols, r)) for r in sea_rows]

            # Obtener proyectos activos NO-SEA (licitaciones, etc.)
            cur.execute("""
                SELECT id, title, company, region, source, phase
                FROM opportunities
                WHERE source != 'sea'
                AND phase NOT IN ('Noticia')
                AND company IS NOT NULL
                AND company != ''
            """)
            proj_rows = cur.fetchall()
            proj_cols = [d[0] for d in cur.description]
            active_projects = [dict(zip(proj_cols, r)) for r in proj_rows]

    print(f"[sea_signals] {len(sea_projects)} proyectos SEA, {len(active_projects)} proyectos activos")

    # Agrupar SEA por empresa para eficiencia
    sea_by_company: dict = {}
    for sea in sea_projects:
        company = sea.get("company") or ""
        if company not in sea_by_company:
            sea_by_company[company] = []
        sea_by_company[company].append(sea)

    # Para cada proyecto activo, buscar SEA del mismo titular
    updates = {}  # opp_id → {pts, details}

    for proj in active_projects:
        proj_company = proj.get("company") or ""
        proj_region  = proj.get("region") or ""

        matching_sea = []
        for sea_company, sea_list in sea_by_company.items():
            if match_company(sea_company, proj_company):
                matching_sea.extend(sea_list)

        if not matching_sea:
            continue

        # Calcular puntos totales del conjunto SEA
        total_pts = 0
        details = []
        for sea in matching_sea:
            phase_pts = get_sea_signal_pts(sea.get("phase") or "")
            if phase_pts == 0:
                continue  # Ignorar rechazados/desistidos

            # Bonus si misma región
            region_bonus = 3 if (proj_region and sea.get("region") == proj_region) else 0
            pts = phase_pts + region_bonus

            total_pts += pts
            phase_label = sea.get("phase") or "en evaluación"
            details.append(f"SEA: {sea['title'][:50]} ({phase_label})")

        if total_pts == 0:
            continue

        # Cap en 25 puntos por empresa
        total_pts = min(total_pts, 25)
        detail_str = " | ".join(details[:2])  # Máximo 2 SEA en el detalle

        proj_id = proj["id"]
        if proj_id not in updates or updates[proj_id]["pts"] < total_pts:
            updates[proj_id] = {"pts": total_pts, "detail": detail_str}

    # Aplicar updates a la BD
    applied = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for opp_id, upd in updates.items():
                # Solo sumar si no hay ya una señal SEA guardada
                cur.execute("""
                    UPDATE opportunities
                    SET signal_score = LEAST(
                            COALESCE(signal_score, 0) + %s,
                            30
                        ),
                        signal_detail = CASE
                            WHEN signal_detail IS NULL THEN %s
                            WHEN signal_detail NOT LIKE '%%SEA%%' THEN signal_detail || ' | ' || %s
                            ELSE signal_detail
                        END,
                        updated_at = NOW()
                    WHERE id = %s
                """, (upd["pts"], upd["detail"], upd["detail"], opp_id))
                if cur.rowcount:
                    applied += 1
        conn.commit()

    print(f"[sea_signals] {applied} proyectos actualizados con señales SEA")
    return {
        "sea_projects": len(sea_projects),
        "active_projects": len(active_projects),
        "projects_updated": applied,
    }


if __name__ == "__main__":
    result = run_sea_signals()
    print(f"\nResultado: {result}")
