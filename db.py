# db.py
import logging
import os, re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

logger = logging.getLogger("stratmap.db")


def _db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL no está seteada")
    return db_url


def get_conn():
    return psycopg.connect(_db_url(), row_factory=dict_row, connect_timeout=8)


# ── Normalización de nombres de empresas ──────────────────────────────────────
# Mismas variantes que aparecen en SEA/SIGEX/Codelco/MOP con razones sociales
# largas. Mapeamos a una forma canónica (la versión "marca") para no fragmentar
# el ranking de mandantes y los joins por empresa.
_COMPANY_ALIASES = {
    # BHP — Escondida, Spence
    "bhp":                                                "BHP Chile",
    "bhp chile":                                          "BHP Chile",
    "bhp chile inc":                                      "BHP Chile",
    "bhp chile inc.":                                     "BHP Chile",
    "bhp chile ltda":                                     "BHP Chile",
    "bhp billiton":                                       "BHP Chile",
    "minera escondida":                                   "Escondida",
    "minera escondida limitada":                          "Escondida",
    "escondida":                                          "Escondida",
    "minera spence":                                      "Spence",
    "minera spence s.a.":                                 "Spence",
    "spence":                                             "Spence",
    # AMSA — Pelambres, Centinela, Zaldívar
    "antofagasta minerals":                               "Antofagasta Minerals",
    "antofagasta minerals s.a.":                          "Antofagasta Minerals",
    "amsa":                                               "Antofagasta Minerals",
    "minera los pelambres":                               "Los Pelambres",
    "los pelambres":                                      "Los Pelambres",
    "pelambres":                                          "Los Pelambres",
    "minera centinela":                                   "Centinela",
    "centinela":                                          "Centinela",
    "minera zaldivar":                                    "Zaldívar",
    "minera zaldívar":                                    "Zaldívar",
    "compania minera zaldivar":                           "Zaldívar",
    "compañía minera zaldívar":                           "Zaldívar",
    # Codelco
    "codelco":                                            "Codelco",
    "corporacion nacional del cobre":                     "Codelco",
    "corporación nacional del cobre":                     "Codelco",
    "corporacion nacional del cobre de chile":            "Codelco",
    "corporación nacional del cobre de chile":            "Codelco",
    "codelco chile":                                      "Codelco",
    # Collahuasi
    "compania minera dona ines de collahuasi":            "Collahuasi",
    "compañía minera doña inés de collahuasi":            "Collahuasi",
    "doña inés de collahuasi scm":                        "Collahuasi",
    "minera collahuasi":                                  "Collahuasi",
    "collahuasi":                                         "Collahuasi",
    # Teck
    "compania minera teck quebrada blanca":               "Quebrada Blanca",
    "compañía minera teck quebrada blanca":               "Quebrada Blanca",
    "teck quebrada blanca":                               "Quebrada Blanca",
    "quebrada blanca":                                    "Quebrada Blanca",
    "teck resources":                                     "Teck",
    "teck resources chile":                               "Teck",
    "teck chile":                                         "Teck",
    "teck":                                               "Teck",
    "compania minera carmen de andacollo":                "Carmen de Andacollo",
    "compañía minera carmen de andacollo":                "Carmen de Andacollo",
    "carmen de andacollo":                                "Carmen de Andacollo",
    "teck andacollo":                                     "Carmen de Andacollo",
    "minera andacollo":                                   "Carmen de Andacollo",
    # Candelaria / Lundin
    "minera candelaria":                                  "Candelaria",
    "candelaria":                                         "Candelaria",
    "scm minera lumina copper chile":                     "Candelaria",
    "lumina copper":                                      "Candelaria",
    "lundin mining":                                      "Lundin Mining",
    # SQM
    "sqm":                                                "SQM",
    "sqm s.a.":                                           "SQM",
    "sociedad quimica y minera de chile":                 "SQM",
    "sociedad química y minera de chile":                 "SQM",
    # ENAMI
    "enami":                                              "ENAMI",
    "empresa nacional de mineria":                        "ENAMI",
    "empresa nacional de minería":                        "ENAMI",
    # MOP
    "ministerio de obras publicas":                       "MOP",
    "ministerio de obras públicas":                       "MOP",
    "direccion general de obras publicas":                "MOP",
    "dirección general de obras públicas":                "MOP",
    "mop":                                                "MOP",
    # Anglo American
    "anglo american":                                     "Anglo American",
    "anglo american sur":                                 "Anglo American",
    "anglo american norte":                               "Anglo American",
}


def normalize_company(name: Optional[str]) -> Optional[str]:
    """Devuelve la forma canónica de un nombre de empresa, o el input
    limpiado (trim + collapse spaces) si no hay match. None si vacío."""
    if not name or not name.strip():
        return None
    cleaned = " ".join(name.strip().split())  # collapse whitespace
    key = cleaned.lower()
    if key in _COMPANY_ALIASES:
        return _COMPANY_ALIASES[key]
    # Sin sufijos legales para reintentar
    stripped = key
    for suf in (" s.a.", " s.a", " spa", " ltda", " ltda.", " scm", " ltda ",
                " s.a. ", " sa ", " inc.", " inc ", " inc"):
        if stripped.endswith(suf):
            stripped = stripped[:-len(suf)].rstrip()
            break
    if stripped != key and stripped in _COMPANY_ALIASES:
        return _COMPANY_ALIASES[stripped]
    return cleaned


def init_db_safe() -> None:
    try:
        init_db()
        init_users_db()
        init_signals_db()
        init_contacts_db()
        init_pipeline_db()
    except Exception as e:
        logger.warning("init_db_safe: db not available yet",
                       extra={"err_type": type(e).__name__, "err": str(e)})


def init_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS opportunities (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        company TEXT NULL,
        contractor TEXT NULL,
        industry TEXT NULL,
        region TEXT NULL,
        phase TEXT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        entry TEXT NULL,
        raw JSONB NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities (score DESC);
    CREATE INDEX IF NOT EXISTS idx_opportunities_company ON opportunities (company);
    CREATE INDEX IF NOT EXISTS idx_opportunities_industry ON opportunities (industry);
    CREATE INDEX IF NOT EXISTS idx_opportunities_region ON opportunities (region);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS entry TEXT NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS raw JSONB NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS signals JSONB DEFAULT '[]';")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS signal_score INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS signal_detail TEXT;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS jobs_count INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS last_signal_at TIMESTAMPTZ NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS strategy TEXT NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;")
            # Deduplicación: dedup_key = hash de company+title (normalizado) +
            # source-category. Cuando dos fuentes reportan lo mismo (Portal Minero
            # + COCHILCO + DF cubriendo la misma noticia), dedup_key empareja.
            # is_duplicate=TRUE en las copias para que las queries de listado las
            # filtren.
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS dedup_key TEXT NULL;")
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_dedup_key ON opportunities(dedup_key) WHERE dedup_key IS NOT NULL;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_is_duplicate ON opportunities(is_duplicate) WHERE is_duplicate;")
            # Peso por evento (scoring_v2). Calculado tras cada ingesta por
            # score_events.run(). Reemplaza la lógica vieja de pesos fijos por
            # categoría en routers/mandantes.py.
            cur.execute("ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS event_weight INTEGER NULL;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_event_weight ON opportunities(event_weight) WHERE event_weight IS NOT NULL;")
        conn.commit()


def init_users_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        name TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_login TIMESTAMPTZ NULL
    );
    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ NULL;
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        preferred_industries TEXT[] DEFAULT '{}',
        preferred_regions TEXT[] DEFAULT '{}',
        preferred_phases TEXT[] DEFAULT '{}',
        preferred_companies TEXT[] DEFAULT '{}',
        keywords TEXT[] DEFAULT '{}',
        min_investment_usd INTEGER NULL,
        weight_region FLOAT DEFAULT 1.0,
        weight_industry FLOAT DEFAULT 1.0,
        weight_investment FLOAT DEFAULT 1.0,
        weight_phase FLOAT DEFAULT 1.0,
        weight_company FLOAT DEFAULT 1.0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ── Planes / billing ──────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS user_plans (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'active',  -- active, past_due, canceled, trialing
        current_period_end TIMESTAMPTZ NULL,
        mp_customer_id TEXT NULL,
        mp_preapproval_id TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_user_plans_plan ON user_plans(plan);
    CREATE INDEX IF NOT EXISTS idx_user_plans_mp_preapproval ON user_plans(mp_preapproval_id)
        WHERE mp_preapproval_id IS NOT NULL;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_signals_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS opportunity_signals (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
        signal_type VARCHAR(50),
        signal_source VARCHAR(100),
        signal_data JSONB DEFAULT '{}',
        score_impact INTEGER DEFAULT 0,
        detected_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_opportunity_signals_opportunity_id ON opportunity_signals(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_opportunities_signal_score ON opportunities(signal_score DESC);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_contacts_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS contacts (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        company TEXT NOT NULL,
        role TEXT NULL,
        email TEXT NULL,
        phone TEXT NULL,
        linkedin_url TEXT NULL,
        notes TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts (company);
    CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts (name);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_pipeline_db() -> None:
    # Esquema actual: pipeline y notes son per-user (multi-tenant).
    sql = """
    CREATE TABLE IF NOT EXISTS opportunity_pipeline (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'Detectada',
        outcome TEXT NULL,
        outcome_date TIMESTAMPTZ NULL,
        outcome_notes TEXT NULL,
        assignee TEXT NULL,
        notes TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(opportunity_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS pipeline_notes (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        note TEXT NOT NULL,
        author TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_pipeline_opportunity_id ON opportunity_pipeline(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_pipeline_user_id ON opportunity_pipeline(user_id);
    CREATE INDEX IF NOT EXISTS idx_pipeline_status ON opportunity_pipeline(status);
    CREATE INDEX IF NOT EXISTS idx_pipeline_notes_opportunity_id ON pipeline_notes(opportunity_id);
    CREATE INDEX IF NOT EXISTS idx_pipeline_notes_user_id ON pipeline_notes(user_id);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            # Migraciones idempotentes para BDs viejas
            cur.execute("ALTER TABLE opportunity_pipeline ADD COLUMN IF NOT EXISTS outcome TEXT NULL;")
            cur.execute("ALTER TABLE opportunity_pipeline ADD COLUMN IF NOT EXISTS outcome_date TIMESTAMPTZ NULL;")
            cur.execute("ALTER TABLE opportunity_pipeline ADD COLUMN IF NOT EXISTS outcome_notes TEXT NULL;")
        conn.commit()
    _migrate_pipeline_user_id()


def _migrate_pipeline_user_id() -> None:
    """One-shot migration: opportunity_pipeline y pipeline_notes pasan a per-user.

    Idempotente: si ya tienen user_id (NOT NULL) no hace nada. Si la columna
    no existe (BD vieja), la agrega, backfilea con MIN(users.id), recrea la
    constraint UNIQUE, y borra filas huérfanas si no había usuarios."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(id) AS uid FROM users")
            first_user = cur.fetchone()
            first_uid = first_user["uid"] if first_user else None

            for table, drop_constraint, new_constraint in [
                ("opportunity_pipeline",
                 "opportunity_pipeline_opportunity_id_key",
                 "opportunity_pipeline_opportunity_id_user_id_key"),
                ("pipeline_notes", None, None),
            ]:
                cur.execute("""
                    SELECT column_name, is_nullable FROM information_schema.columns
                    WHERE table_name = %s AND column_name = 'user_id'
                """, (table,))
                row = cur.fetchone()
                if row and row["is_nullable"] == "NO":
                    continue  # ya migrado

                logger.info("migrate to per-user (pipeline)", extra={"table": table})
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
                if first_uid is not None:
                    cur.execute(f"UPDATE {table} SET user_id = %s WHERE user_id IS NULL", (first_uid,))
                cur.execute(f"DELETE FROM {table} WHERE user_id IS NULL")
                cur.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")
                if drop_constraint:
                    cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {drop_constraint}")
                if new_constraint:
                    cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {new_constraint} UNIQUE (opportunity_id, user_id)")
        conn.commit()


def db_health() -> Tuple[bool, str]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 as ok;")
                _ = cur.fetchone()
        return True, "ok"
    except Exception as e:
        return False, f"db error: {type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE — Piedra angular de Stratmap
# Calcula la probabilidad de oportunidad comercial para proveedores mineros.
# Score 0–100 donde 100 = oportunidad directa activa con gran mandante.
# ══════════════════════════════════════════════════════════════════════════════

# Mandantes grandes conocidos → bonus de relevancia
_MANDANTES_GRANDES = {
    "bhp", "bhp chile", "bhp chile inc", "codelco", "enami",
    "anglo american", "angloamerican", "antofagasta minerals", "amsa",
    "freeport", "freeport-mcmoran", "mra freeport", "teck", "teck resources",
    "teck resources chile", "minera centinela", "minera escondida",
    "minera los pelambres", "pelambres", "escondida", "spence", "minera spence",
    "minera zaldívar", "minera zaldivar", "compania minera zaldivar",
    "sqm", "sqm s.a.", "albemarle", "sumitomo", "glencore",
    "rio tinto", "vale", "barrick", "kinross", "yamana",
    "gold fields", "agnico eagle", "newmont", "lundin", "capstone",
    "compania minera dona ines de collahuasi", "collahuasi",
    "minera candelaria", "first quantum", "lumina copper",
    "minera san cristobal", "quantum pacific",
}


def _mandante_size(company: str) -> int:
    """Retorna bonus de mandante: 15 si grande, 8 si mediano conocido, 0 si desconocido."""
    if not company:
        return 0
    c = company.lower().strip()
    if any(m in c for m in _MANDANTES_GRANDES):
        return 15
    if "minera" in c or "compania minera" in c or "compañía minera" in c:
        return 8
    return 3


def _mineral_score(recurso: str, title: str) -> int:
    """Bonus por mineral estratégico según relevancia de mercado actual."""
    txt = (recurso or title or "").lower()
    if any(x in txt for x in ["li ", "litio", "li-", "salar"]):          return 20
    if any(x in txt for x in ["cu", "cobre"]):                           return 15
    if any(x in txt for x in ["au", "ag", "oro", "plata", "gold"]):      return 12
    if any(x in txt for x in ["mo", "molibdeno", "re", "renio"]):        return 10
    if any(x in txt for x in ["fe", "hierro", "zn", "zinc", "ni", "niquel", "cobalto", "co "]):
        return 8
    if any(x in txt for x in ["potasio", "yodo", "boro", "nitrato"]):    return 10
    return 3


def _title_keywords_score(title: str) -> int:
    """Detecta señales positivas y negativas en el título del proyecto."""
    t = title.lower()
    score = 0
    POSITIVE = [
        ("llamado a licitación", 10), ("llamado a propuesta", 10),
        ("licitación pública", 8),    ("licitación privada", 7),
        ("proceso de contratación", 8), ("adjudicación", 6),
        ("concurso público", 7),       ("contrato de servicio", 6),
        ("convenio marco", 5),         ("en construcción", 5),
        ("inicio de obras", 6),        ("construcción y montaje", 7),
        ("ingeniería de detalle", 6),  ("ingeniería básica", 5),
        ("expansión", 5),              ("ampliación", 5),
        ("nuevo proyecto", 4),         ("fase ii", 5), ("fase iii", 5),
    ]
    NEGATIVE = [
        ("suspendido", -15),    ("paralizado", -15),   ("paralización", -15),
        ("desistido", -20),     ("desistimiento", -20), ("rechazado", -18),
        ("no admitido", -18),   ("archivado", -12),     ("abandonado", -15),
        ("término anticipado", -10), ("resolución de término", -10),
        ("cierre de faena", -8),
    ]
    for kw, pts in POSITIVE:
        if kw in t:
            score += pts
            break  # solo el mejor positivo
    for kw, pts in NEGATIVE:
        if kw in t:
            score += pts
    return score


def _region_score(region: str, raw: dict) -> int:
    """Bonus por región minera estratégica de Chile."""
    txt = (region or raw.get("REGION") or raw.get("region") or "").lower()
    if any(x in txt for x in ["antofagasta", "ii región", "ii region"]):  return 6
    if any(x in txt for x in ["atacama", "iii región", "iii region"]):    return 5
    if any(x in txt for x in ["tarapacá", "tarapaca", "i región"]):       return 5
    if any(x in txt for x in ["coquimbo", "iv región", "iv region"]):     return 4
    if any(x in txt for x in ["arica", "parinacota"]):                    return 3
    if any(x in txt for x in ["o'higgins", "ohiggins", "vi región"]):    return 3
    return 0


def _temporal_score(item: dict) -> int:
    """Boost/penalización según antigüedad. Recientes suben, viejos sin actividad bajan."""
    now = datetime.now(timezone.utc)
    best_date = None
    for field in ("updated_at", "last_signal_at", "published_at", "created_at", "entry"):
        v = item.get(field)
        if not v:
            continue
        if isinstance(v, str):
            try:
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                continue
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            if best_date is None or v > best_date:
                best_date = v
    if best_date is None:
        return 0
    days = (now - best_date).days
    if days <= 30:    return 8
    if days <= 90:    return 5
    if days <= 180:   return 2
    if days <= 365:   return 0
    if days <= 548:   return -5
    if days <= 730:   return -10
    return -15


def _monto_titulo(title: str) -> int:
    """Detecta montos en el título (UF, MM USD, MUSD) para scoring extra."""
    t = title.lower()
    for pat, pts in [
        (r"(?:us\$?|usd)\s*[\d,.]+\s*(?:mill|bn|billon)", 10),
        (r"[\d,.]+\s*(?:musd|mmusd|mm\s*usd)", 8),
        (r"[\d,.]+\s*(?:mill[oi]ones?\s*(?:de\s*)?(?:dólar|dollar|usd))", 8),
        (r"[\d,.]+\s*(?:uf|unidades?\s*de\s*fomento)", 4),
        (r"[\d,.]+\s*(?:millones?\s*(?:de\s*)?peso)", 3),
    ]:
        if re.search(pat, t):
            return pts
    return 0


def _mandante_heat_boost(heat_score: int) -> int:
    """Boost basado en temperatura del mandante (0–10 puntos).
    Un mandante muy activo (noticias + empleos + proyectos) indica
    mayor probabilidad de contratación a corto plazo."""
    if heat_score >= 80: return 10
    if heat_score >= 60: return 6
    if heat_score >= 40: return 3
    return 0


def calc_score(item: Dict[str, Any], mandante_heat: int = 0) -> int:
    """
    Calcula score 0–100 para un proyecto/licitación minera. v2.

    Componentes:
      BASE_TIPO    : fuente + estado (8–71)
      MINERAL      : mineral estratégico (3–20)
      MANDANTE     : tamaño del mandante (0–15)
      INVERSIÓN    : monto USD estructurado (0–15)
      SEÑAL_CRUZADA: signal_score existente (0–10)
      KEYWORDS     : palabras clave del título (-20 / +10)
      REGIÓN       : región minera estratégica (0–6)
      TEMPORAL     : antigüedad del registro (-15 / +8)
      MONTO_TÍTULO : montos detectados en texto (0–10)
      HEAT_MANDANTE: temperatura IA del mandante (0–10)
    """
    source  = (item.get("source") or "").strip()
    phase   = (item.get("phase")  or "").strip()
    company = (item.get("company") or "").strip()
    raw     = item.get("raw") or {}
    title   = item.get("title") or ""
    region  = item.get("region") or ""
    signal  = item.get("signal_score") or 0

    NEWS_SOURCES = {
        "Portal Minero", "BioBioChile", "Emol", "Cooperativa",
        "Minería Chilena", "COCHILCO Noticias", "Diario Financiero",
        "Revista EI", "Radio U. de Chile", "Radio Universidad de Chile",
        "RSS", "Lithium Chile", "InfoMineria", "Mundo Minería",
        "MLP Proveedores", "BHP Careers", "AMSA Careers",
        "Lundin Careers", "Collahuasi Careers", "Teck Careers",
    }
    if source in NEWS_SOURCES or phase == "Noticia":
        return 0

    if source in ("ENAMI", "Codelco"):
        tipo = (raw.get("tipo") or "").lower()
        op   = (raw.get("operacion") or "").lower()
        base = 65
        if "servicio" in tipo:   base = 68
        elif "bien" in tipo:     base = 62
        if any(x in op for x in ["chuquicamata", "andina", "teniente", "minis", "gabriela"]):
            base += 3

    elif source == "SEA":
        estado = (phase or raw.get("ESTADO_EVALUACION") or "").lower()
        if "calificacion" in estado or "calificación" in estado:            base = 58
        elif "admision" in estado or "admisión" in estado:                  base = 48
        elif "ingreso voluntario" in estado:                                base = 42
        elif any(x in estado for x in ["desistido", "rechazado", "no admitido"]): base = 8
        else:                                                               base = 35

    elif source == "SIGEX":
        phase_l = phase.lower() if phase else ""
        if "tramite" in phase_l or "trámite" in phase_l:        base = 40
        elif "aprobado" in phase_l:                              base = 32
        elif "evaluacion" in phase_l or "evaluación" in phase_l: base = 36
        elif "concesion" in phase_l or "concesión" in phase_l:   base = 28
        else:                                                    base = 25

    elif source == "manual":
        base = item.get("score") or 50

    else:
        base = 30

    recurso  = raw.get("recurso") or raw.get("RECURSO") or ""
    mineral  = _mineral_score(recurso, title)
    mandante = _mandante_size(company)
    keywords = _title_keywords_score(title)
    reg      = _region_score(region, raw)
    temporal = _temporal_score(item)
    monto_t  = _monto_titulo(title)

    inversion = 0
    if source == "SEA":
        inv = raw.get("INVERSION_US") or 0
        try:
            inv = float(inv)
            if inv >= 1_000_000_000:   inversion = 15
            elif inv >= 100_000_000:   inversion = 10
            elif inv >= 10_000_000:    inversion = 6
            elif inv >= 1_000_000:     inversion = 3
        except (TypeError, ValueError):
            pass

    senal = min(int(signal / 3), 10) if signal > 0 else 0
    heat  = _mandante_heat_boost(mandante_heat)

    total = base + mineral + mandante + keywords + reg + temporal + inversion + senal + monto_t + heat
    return max(0, min(total, 99))

def recalc_all_scores() -> Dict[str, Any]:
    """
    Recalcula scores para todos los proyectos en la BD.
    Incluye temperatura del mandante (mandante_heat) como componente del score.
    Retorna estadísticas del resultado.
    """
    with get_conn() as conn:
        # Pre-cargar heat scores de mandantes para evitar N+1 queries
        heat_map: Dict[str, int] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT company, heat_score FROM mandante_heat")
            for r in cur.fetchall():
                if r["company"]:
                    heat_map[r["company"].lower().strip()] = r["heat_score"] or 0

        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, source, phase, company, raw, title, signal_score, score,
                       updated_at, last_signal_at, published_at, created_at, entry
                FROM opportunities
            """)
            rows = cur.fetchall()

        updates = []
        for row in rows:
            item = dict(row)
            company_key = (item.get("company") or "").lower().strip()
            heat = heat_map.get(company_key, 0)
            new_score = calc_score(item, mandante_heat=heat)
            if new_score != (item.get("score") or 0):
                updates.append((new_score, item["id"]))

        if updates:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE opportunities SET score = %s, updated_at = NOW() WHERE id = %s",
                    updates
                )
            conn.commit()

    # Estadísticas
    dist = {"0": 0, "1-30": 0, "31-50": 0, "51-70": 0, "71-85": 0, "86-99": 0}
    by_source: Dict[str, Dict] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source, score FROM opportunities ORDER BY source")
            for row in cur.fetchall():
                s, sc = row["source"], row["score"] or 0
                if sc == 0:          dist["0"] += 1
                elif sc <= 30:       dist["1-30"] += 1
                elif sc <= 50:       dist["31-50"] += 1
                elif sc <= 70:       dist["51-70"] += 1
                elif sc <= 85:       dist["71-85"] += 1
                else:                dist["86-99"] += 1
                if s not in by_source:
                    by_source[s] = {"n": 0, "scores": []}
                by_source[s]["n"] += 1
                by_source[s]["scores"].append(sc)

    summary = {}
    for src, d in by_source.items():
        sc = d["scores"]
        summary[src] = {
            "n": d["n"],
            "avg": round(sum(sc) / len(sc)) if sc else 0,
            "min": min(sc),
            "max": max(sc),
        }

    return {
        "total_updated": len(updates),
        "total_rows": len(rows),
        "distribution": dist,
        "by_source": summary,
    }


def _compute_dedup_key(item: Dict[str, Any]) -> Optional[str]:
    """Calcula dedup_key = sha1 de title-normalizado + company-canónica.

    Cuando dos sources reportan la misma noticia/proyecto, los títulos suelen
    coincidir tras normalizar (lowercase, sin signos). Si no, esto no agrupa
    — es una dedup conservadora.
    """
    import hashlib
    import re
    title = (item.get("title") or "").lower().strip()
    if not title:
        return None
    # Quitar signos, números sueltos y collapsar espacios
    title_n = re.sub(r"[^a-záéíóúñü\s]", " ", title)
    title_n = " ".join(title_n.split())
    company = (item.get("company") or "").lower().strip()
    raw = f"{title_n}|{company}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def mark_duplicates() -> int:
    """Marca como is_duplicate=TRUE las filas con dedup_key compartido salvo
    una "ganadora" (mayor score, desempate por id menor). Idempotente.

    Devuelve cantidad de filas marcadas como duplicadas en esta corrida.
    """
    sql = """
    WITH ranked AS (
        SELECT id, dedup_key,
               ROW_NUMBER() OVER (
                   PARTITION BY dedup_key
                   ORDER BY score DESC, id ASC
               ) AS rn
        FROM opportunities
        WHERE dedup_key IS NOT NULL
    ),
    targets AS (
        SELECT id FROM ranked WHERE rn > 1
    )
    UPDATE opportunities o
    SET is_duplicate = TRUE
    FROM targets t
    WHERE o.id = t.id AND o.is_duplicate = FALSE;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            n = cur.rowcount
        conn.commit()
    return n


def upsert_opportunities(items: List[Dict[str, Any]]) -> Tuple[int, int]:
    inserted = 0
    updated = 0
    sql = """
    INSERT INTO opportunities
      (source, title, url, company, contractor, industry, region, phase, score,
       entry, raw, published_at, created_at, updated_at,
       jobs_count, signal_score, signal_detail, last_signal_at, dedup_key)
    VALUES
      (%(source)s, %(title)s, %(url)s, %(company)s, %(contractor)s, %(industry)s,
       %(region)s, %(phase)s, %(score)s, %(entry)s, %(raw)s, %(published_at)s, NOW(), NOW(),
       %(jobs_count)s, %(signal_score)s, %(signal_detail)s, %(last_signal_at)s, %(dedup_key)s)
    ON CONFLICT (url) DO UPDATE SET
      source = EXCLUDED.source, title = EXCLUDED.title, company = EXCLUDED.company,
      contractor = EXCLUDED.contractor, industry = EXCLUDED.industry, region = EXCLUDED.region,
      phase = EXCLUDED.phase, score = EXCLUDED.score, entry = EXCLUDED.entry,
      raw = EXCLUDED.raw,
      jobs_count = EXCLUDED.jobs_count,
      signal_score = EXCLUDED.signal_score,
      signal_detail = EXCLUDED.signal_detail,
      last_signal_at = COALESCE(EXCLUDED.last_signal_at, opportunities.last_signal_at),
      published_at = CASE WHEN EXCLUDED.published_at IS NOT NULL THEN EXCLUDED.published_at ELSE opportunities.published_at END,
      dedup_key = COALESCE(EXCLUDED.dedup_key, opportunities.dedup_key),
      is_active = TRUE,
      updated_at = NOW()
    RETURNING (xmax = 0) AS inserted;
    """
    for it in items:
        it.setdefault("company", None); it.setdefault("contractor", None)
        it.setdefault("industry", None); it.setdefault("region", None)
        it.setdefault("phase", None); it.setdefault("entry", None)
        it.setdefault("published_at", None)
        it.setdefault("jobs_count", 0); it.setdefault("signal_score", 0)
        it.setdefault("signal_detail", None); it.setdefault("last_signal_at", None)

        # Normalizar nombre de empresa (forma canónica para joins/rankings)
        it["company"] = normalize_company(it.get("company"))

        # Calcular dedup_key (lo usa mark_duplicates() post-ingest)
        it["dedup_key"] = _compute_dedup_key(it)

        # ── Calcular score automáticamente (salvo manual override > 0) ────────
        existing_score = it.get("score") or 0
        if it.get("source") == "manual" and existing_score > 0:
            it["score"] = existing_score  # respetar scores manuales
        else:
            it["score"] = calc_score(it)

        raw = it.get("raw")
        if isinstance(raw, (dict, list)): it["raw"] = Json(raw)
        elif raw is None: it["raw"] = None
        else: it["raw"] = Json({"value": str(raw)})

    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(sql, it)
                row = cur.fetchone()
                if row and row.get("inserted"): inserted += 1
                else: updated += 1
        conn.commit()
    return inserted, updated


# ── TTL por fuente (días). None = nunca expira. ───────────────────────────────
# Criterio: ciclo real de publicación en cada portal + margen de seguridad.
SOURCE_TTL_DAYS: Dict[str, int] = {
    # Portales de licitación / compras
    "Ariba Codelco":   45,   # procurement ciclo ~30 días
    "Ariba":           45,
    "Chile Compra":    45,   # mercado público típico 30-45 días
    "ChileCompra":     45,
    "MLP Proveedores": 60,   # ciclos algo más largos
    # Portales de mineras
    "Codelco":         60,
    "ENAMI":           60,
    # Infraestructura pública
    "MOP":             90,   # proyectos estado demoran más
    # Datos de mercado / reportes
    "COCHILCO":        120,  # estadísticas mensuales
    # Noticias / RSS (info caduca rápido)
    "RSS":             30,
    "Portal Minero":   30,
    "InfoMinería":     30,
    "Minería Chilena": 30,
    "Mundo Minería":   30,
    "rss_mineria":     30,
    "BioBioChile":     14,
    "Emol":            14,
    "Cooperativa":     14,
    # Empleos / careers (ya truncan al re-scrape, esto es red de seguridad)
    "BHP Careers":               14,
    "AMSA Careers":              14,
    "Teck Careers":              14,
    "Lundin Careers":            14,
    "Collahuasi Careers":        14,
    "Antofagasta Minerals Careers": 14,
    "Kinross Careers":           14,
    "Empleos Indeed":            14,
    # Fuentes que NUNCA expiran:
    #   "sea", "SEA"       → aprobaciones ambientales son permanentes
    #   "SIGEX"            → concesiones mineras duran décadas
    #   "Sernageomin"      → igual
    #   "manual"           → ingresadas a mano por el usuario
}


def expire_stale_opportunities() -> Dict[str, Any]:
    """Marca is_active=FALSE en oportunidades cuyo updated_at supera el TTL
    configurado por fuente. Retorna cuántos registros se inactivaron por fuente.

    Lógica: updated_at se actualiza en cada UPSERT cuando el ítem sigue
    apareciendo en el portal. Si updated_at no se ha renovado en N días,
    el ítem ya desapareció del portal → se marca inactivo.
    Items que reaparezcan en un fetch futuro son reactivados automáticamente
    (upsert_opportunities pone is_active=TRUE en el ON CONFLICT).
    """
    expired: Dict[str, int] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for source, ttl_days in SOURCE_TTL_DAYS.items():
                cur.execute("""
                    UPDATE opportunities
                    SET is_active = FALSE
                    WHERE source = %(source)s
                      AND is_active = TRUE
                      AND updated_at < NOW() - (%(ttl_days)s || ' days')::interval
                """, {"source": source, "ttl_days": ttl_days})
                count = cur.rowcount
                if count > 0:
                    expired[source] = count
        conn.commit()
    total = sum(expired.values())
    logger.info("expire_stale done", extra={"total": total, "by_source": expired})
    return {"total_expired": total, "by_source": expired}


def list_opportunities(
    q: Optional[str],
    limit: int,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 2000))
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    # Por defecto sólo mostramos oportunidades activas + canónicas (no duplicadas)
    if not include_inactive:
        conditions.append("o.is_active IS NOT FALSE")
        conditions.append("o.is_duplicate = FALSE")

    if q:
        conditions.append(
            "(o.title ILIKE %(q)s OR o.url ILIKE %(q)s OR o.company ILIKE %(q)s"
            " OR o.contractor ILIKE %(q)s OR o.industry ILIKE %(q)s OR o.region ILIKE %(q)s)"
        )
        params["q"] = f"%{q}%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
    SELECT o.id, o.source, o.title, o.url, o.company, o.contractor, o.industry, o.region, o.phase,
           o.score, o.signal_score, o.signal_detail, o.jobs_count, o.signals, o.last_signal_at,
           o.entry, o.raw, o.created_at, o.updated_at, o.is_active,
           (o.score + COALESCE(o.signal_score, 0)) AS radar_score,
           p.status AS pipeline_status, p.assignee AS pipeline_assignee
    FROM opportunities o
    LEFT JOIN opportunity_pipeline p ON p.opportunity_id = o.id
    {where}
    ORDER BY radar_score DESC, o.updated_at DESC LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_opportunity_by_url(url: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT id, source, title, url, company, contractor, industry, region, phase,
           score, signal_score, jobs_count, signals, last_signal_at, entry, raw, created_at, updated_at
    FROM opportunities WHERE url = %(url)s LIMIT 1;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"url": url})
            return cur.fetchone()


# ── Pipeline ──────────────────────────────────────────────────────────────────

PIPELINE_STATUSES = ["Detectada", "En análisis", "Postular", "No postular",
                     "Presentada", "Adjudicada", "Perdida"]

def get_pipeline(opportunity_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM opportunity_pipeline WHERE opportunity_id = %(id)s AND user_id = %(uid)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": opportunity_id, "uid": user_id})
            row = cur.fetchone()
    return dict(row) if row else None

def upsert_pipeline(opportunity_id: int, user_id: int, status: str, assignee: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO opportunity_pipeline (opportunity_id, user_id, status, assignee, updated_at)
    VALUES (%(opportunity_id)s, %(user_id)s, %(status)s, %(assignee)s, NOW())
    ON CONFLICT (opportunity_id, user_id) DO UPDATE SET
      status = EXCLUDED.status,
      assignee = COALESCE(EXCLUDED.assignee, opportunity_pipeline.assignee),
      updated_at = NOW()
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id, "user_id": user_id, "status": status, "assignee": assignee})
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def add_pipeline_note(opportunity_id: int, user_id: int, note: str, author: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO pipeline_notes (opportunity_id, user_id, note, author)
    VALUES (%(opportunity_id)s, %(user_id)s, %(note)s, %(author)s)
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id, "user_id": user_id, "note": note, "author": author})
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def get_pipeline_notes(opportunity_id: int, user_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT * FROM pipeline_notes
    WHERE opportunity_id = %(id)s AND user_id = %(uid)s
    ORDER BY created_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": opportunity_id, "uid": user_id})
            return [dict(r) for r in cur.fetchall()]

def list_pipeline(user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = """
    SELECT o.id, o.title, o.company, o.region, o.industry, o.url,
           (o.score + COALESCE(o.signal_score, 0)) AS radar_score,
           p.status, p.assignee, p.updated_at
    FROM opportunity_pipeline p
    JOIN opportunities o ON o.id = p.opportunity_id
    WHERE p.user_id = %(user_id)s
    """
    params: Dict[str, Any] = {"user_id": user_id}
    if status:
        sql += " AND p.status = %(status)s"
        params["status"] = status
    sql += " ORDER BY p.updated_at DESC;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ── Users & Preferences ───────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, name: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO users (email, password_hash, name)
    VALUES (%(email)s, %(password_hash)s, %(name)s)
    RETURNING id, email, name;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"email": email, "password_hash": password_hash, "name": name})
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    sql = "SELECT id, email, password_hash, name FROM users WHERE email = %(email)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"email": email})
            row = cur.fetchone()
    return dict(row) if row else None


def touch_user_last_login(user_id: int) -> None:
    """Marca last_login=NOW() para tracking de usuarios activos."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
        conn.commit()


# ── Billing / planes ──────────────────────────────────────────────────────────

def get_user_plan(user_id: int) -> Dict[str, Any]:
    """Devuelve el plan del usuario, o un default 'free' / 'active' si no hay fila."""
    sql = "SELECT * FROM user_plans WHERE user_id = %s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
    if row:
        return dict(row)
    return {"user_id": user_id, "plan": "free", "status": "active",
            "current_period_end": None, "mp_customer_id": None, "mp_preapproval_id": None}


def upsert_user_plan(user_id: int, plan: str, status: str,
                     current_period_end: Optional[datetime] = None,
                     mp_customer_id: Optional[str] = None,
                     mp_preapproval_id: Optional[str] = None) -> Dict[str, Any]:
    sql = """
    INSERT INTO user_plans (user_id, plan, status, current_period_end,
                            mp_customer_id, mp_preapproval_id, updated_at)
    VALUES (%(uid)s, %(plan)s, %(status)s, %(end)s, %(cust)s, %(pre)s, NOW())
    ON CONFLICT (user_id) DO UPDATE SET
      plan = EXCLUDED.plan,
      status = EXCLUDED.status,
      current_period_end = COALESCE(EXCLUDED.current_period_end, user_plans.current_period_end),
      mp_customer_id = COALESCE(EXCLUDED.mp_customer_id, user_plans.mp_customer_id),
      mp_preapproval_id = COALESCE(EXCLUDED.mp_preapproval_id, user_plans.mp_preapproval_id),
      updated_at = NOW()
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "uid": user_id, "plan": plan, "status": status,
                "end": current_period_end, "cust": mp_customer_id, "pre": mp_preapproval_id,
            })
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def get_user_by_mp_preapproval(preapproval_id: str) -> Optional[Dict[str, Any]]:
    """Encuentra el user_plans cuya preapproval coincide. Usado por el webhook MP."""
    sql = "SELECT * FROM user_plans WHERE mp_preapproval_id = %s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (preapproval_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def count_user_contacts(user_id: int) -> int:
    """No-op por ahora — contactos no están scopeados por user. Devuelve count global.

    TODO: cuando contacts tenga user_id, scopear este count.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM contacts")
            row = cur.fetchone()
    return int(row["n"]) if row else 0

def save_preferences(user_id: int, prefs: Dict[str, Any]) -> None:
    sql = """
    INSERT INTO user_preferences
      (user_id, preferred_industries, preferred_regions, preferred_phases,
       preferred_companies, keywords, min_investment_usd,
       weight_region, weight_industry, weight_investment, weight_phase, weight_company, updated_at)
    VALUES
      (%(user_id)s, %(preferred_industries)s, %(preferred_regions)s, %(preferred_phases)s,
       %(preferred_companies)s, %(keywords)s, %(min_investment_usd)s,
       %(weight_region)s, %(weight_industry)s, %(weight_investment)s, %(weight_phase)s, %(weight_company)s, NOW())
    ON CONFLICT (user_id) DO UPDATE SET
      preferred_industries = EXCLUDED.preferred_industries,
      preferred_regions = EXCLUDED.preferred_regions,
      preferred_phases = EXCLUDED.preferred_phases,
      preferred_companies = EXCLUDED.preferred_companies,
      keywords = EXCLUDED.keywords,
      min_investment_usd = EXCLUDED.min_investment_usd,
      weight_region = EXCLUDED.weight_region,
      weight_industry = EXCLUDED.weight_industry,
      weight_investment = EXCLUDED.weight_investment,
      weight_phase = EXCLUDED.weight_phase,
      weight_company = EXCLUDED.weight_company,
      updated_at = NOW();
    """
    prefs["user_id"] = user_id
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, prefs)
        conn.commit()

def get_preferences(user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM user_preferences WHERE user_id = %(user_id)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id})
            row = cur.fetchone()
    return dict(row) if row else None


# ── Signals ───────────────────────────────────────────────────────────────────

COMPANY_ALIASES: Dict[str, List[str]] = {
    "BHP":                  ["BHP"],
    "Codelco":              ["CODELCO", "Codelco", "Radomiro Tomic", "Chuquicamata",
                             "El Teniente", "División Andina", "División Salvador"],
    "SQM":                  ["SQM", "Sociedad Química"],
    "Anglo American":       ["Anglo American", "Anglo"],
    "Teck":                 ["Teck", "Caserones"],
    "Antofagasta Minerals": ["AMSA", "Antofagasta Minerals", "Antofagasta"],
    "Glencore":             ["Glencore", "Punta del Cobre"],
    "Freeport-McMoRan":     ["Freeport", "FCX", "Lumina", "LUMINA COPPER"],
}

def save_job_signal(opportunity_id: int, signal: Dict[str, Any]) -> None:
    # Dedup: solo sumar signal_score una vez por día por proyecto
    sql_check = """
    SELECT COUNT(*) as cnt FROM opportunity_signals
    WHERE opportunity_id = %(id)s
      AND signal_type = 'jobs'
      AND detected_at > NOW() - INTERVAL '24 hours';
    """
    sql_signal = """
    INSERT INTO opportunity_signals
      (opportunity_id, signal_type, signal_source, signal_data, score_impact, detected_at)
    VALUES (%(opportunity_id)s, %(signal_type)s, %(signal_source)s, %(signal_data)s, %(score_impact)s, %(detected_at)s);
    """
    # Solo suma score si es la primera detección del día
    sql_update_new = """
    UPDATE opportunities SET
      jobs_count = %(jobs_count)s,
      signal_score = LEAST(COALESCE(signal_score, 0) + %(score_impact)s, 50),
      last_signal_at = NOW(),
      signals = COALESCE(signals, '[]'::jsonb) || %(new_signal)s::jsonb
    WHERE id = %(opportunity_id)s;
    """
    # Si ya detectó hoy, solo actualiza jobs_count y last_signal_at
    sql_update_existing = """
    UPDATE opportunities SET
      jobs_count = %(jobs_count)s,
      last_signal_at = NOW()
    WHERE id = %(opportunity_id)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_check, {"id": opportunity_id})
            row = cur.fetchone()
            already_today = row and row.get("cnt", 0) > 0

            cur.execute(sql_signal, {
                "opportunity_id": opportunity_id,
                "signal_type": signal["signal_type"],
                "signal_source": signal["signal_source"],
                "signal_data": Json(signal["signal_data"]),
                "score_impact": signal["score_impact"],
                "detected_at": signal["detected_at"],
            })

            if already_today:
                cur.execute(sql_update_existing, {
                    "opportunity_id": opportunity_id,
                    "jobs_count": signal["jobs_count"],
                })
            else:
                cur.execute(sql_update_new, {
                    "opportunity_id": opportunity_id,
                    "jobs_count": signal["jobs_count"],
                    "score_impact": signal["score_impact"],
                    "new_signal": Json({
                        "type": "jobs",
                        "jobs_count": signal["jobs_count"],
                        "score_impact": signal["score_impact"],
                        "detected_at": signal["detected_at"].isoformat(),
                    }),
                })
        conn.commit()

def get_opportunities_by_company(company_name: str) -> List[Dict[str, Any]]:
    search_terms = COMPANY_ALIASES.get(company_name, [company_name])
    conditions = " OR ".join([f"company ILIKE %(term_{i})s" for i in range(len(search_terms))])
    params = {f"term_{i}": f"%{term}%" for i, term in enumerate(search_terms)}
    sql = f"""
    SELECT id, title, company, score, signal_score, jobs_count, last_signal_at
    FROM opportunities WHERE {conditions}
    ORDER BY signal_score DESC, score DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def get_radar_opportunities(limit: int = 20) -> List[Dict[str, Any]]:
    sql = """
    SELECT id, title, company, region, industry, phase, score, signal_score, jobs_count, signals,
           last_signal_at, updated_at, (score + COALESCE(signal_score, 0)) AS radar_score
    FROM opportunities
    ORDER BY radar_score DESC, last_signal_at DESC NULLS LAST
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"limit": limit})
            return cur.fetchall()

def get_signals_for_opportunity(opportunity_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT signal_type, signal_source, signal_data, score_impact, detected_at
    FROM opportunity_signals WHERE opportunity_id = %(opportunity_id)s
    ORDER BY detected_at DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opportunity_id": opportunity_id})
            return cur.fetchall()


# ── Contactos ─────────────────────────────────────────────────────────────────

def create_contact(contact: Dict[str, Any]) -> Dict[str, Any]:
    sql = """
    INSERT INTO contacts (name, company, role, email, phone, linkedin_url, notes)
    VALUES (%(name)s, %(company)s, %(role)s, %(email)s, %(phone)s, %(linkedin_url)s, %(notes)s)
    RETURNING *;
    """
    contact.setdefault("role", None); contact.setdefault("email", None)
    contact.setdefault("phone", None); contact.setdefault("linkedin_url", None)
    contact.setdefault("notes", None)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, contact)
            row = cur.fetchone()
        conn.commit()
    return dict(row)

def update_contact(contact_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fields = ["name","company","role","email","phone","linkedin_url","notes"]
    updates = ", ".join([f"{f} = %({f})s" for f in fields if f in data])
    if not updates: return None
    sql = f"UPDATE contacts SET {updates}, updated_at = NOW() WHERE id = %(id)s RETURNING *;"
    data["id"] = contact_id
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, data)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None

def delete_contact(contact_id: int) -> bool:
    sql = "DELETE FROM contacts WHERE id = %(id)s RETURNING id;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id": contact_id})
            row = cur.fetchone()
        conn.commit()
    return row is not None

def get_contacts_by_company(company: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT * FROM contacts
    WHERE company ILIKE %(like)s
       OR %(company)s ILIKE '%%' || company || '%%'
    ORDER BY name ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"company": company, "like": f"%{company}%"})
            return [dict(r) for r in cur.fetchall()]

def list_contacts(q: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    base = "SELECT * FROM contacts"
    params: Dict[str, Any] = {"limit": limit}
    if q:
        base += " WHERE name ILIKE %(q)s OR company ILIKE %(q)s OR role ILIKE %(q)s"
        params["q"] = f"%{q}%"
    base += " ORDER BY company ASC, name ASC LIMIT %(limit)s;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            return [dict(r) for r in cur.fetchall()]

def bulk_import_contacts(contacts: List[Dict[str, Any]]) -> Tuple[int, int]:
    inserted = errors = 0
    for c in contacts:
        try:
            create_contact(c)
            inserted += 1
        except Exception as e:
            logger.warning("contacts import row failed",
                           extra={"name": c.get("name"), "err": str(e)})
            errors += 1
    return inserted, errors


# ── AI Matching ───────────────────────────────────────────────────────────────

def init_ai_db() -> None:
    # Esquema actual (instalaciones nuevas): user_id INTEGER REFERENCES users(id).
    # Para instalaciones existentes que tienen user_id TEXT ('default'), corremos
    # la migración _migrate_ai_user_id_to_int() más abajo.
    create_sql = """
    CREATE TABLE IF NOT EXISTS service_profiles (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_key TEXT,
        company_name TEXT,
        services JSONB NOT NULL DEFAULT '[]',
        regions JSONB NOT NULL DEFAULT '[]',
        contract_sizes JSONB NOT NULL DEFAULT '[]',
        known_mandantes JSONB NOT NULL DEFAULT '[]',
        onboarding_done BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id)
    );

    CREATE TABLE IF NOT EXISTS mandante_heat (
        id              SERIAL PRIMARY KEY,
        company         TEXT NOT NULL UNIQUE,
        heat_score      INTEGER DEFAULT 0,
        heat_label      TEXT,
        heat_reason     TEXT,
        n_noticias      INTEGER DEFAULT 0,
        n_empleos       INTEGER DEFAULT 0,
        trending_topics TEXT[],
        scored_at       TIMESTAMPTZ DEFAULT NOW(),
        model_version   TEXT DEFAULT 'claude-sonnet-4-6'
    );
    CREATE INDEX IF NOT EXISTS idx_mandante_heat_company ON mandante_heat(company);
    CREATE INDEX IF NOT EXISTS idx_mandante_heat_score ON mandante_heat(heat_score DESC);

    CREATE TABLE IF NOT EXISTS ai_opportunity_fits (
        id SERIAL PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        fit_score INTEGER NOT NULL DEFAULT 0,
        fit_reason TEXT,
        service_applicable TEXT,
        contact_suggestion TEXT,
        model_version TEXT DEFAULT 'claude-sonnet-4-6',
        scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(opportunity_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ai_fits_user ON ai_opportunity_fits (user_id, fit_score DESC);
    CREATE INDEX IF NOT EXISTS idx_ai_fits_opp ON ai_opportunity_fits (opportunity_id);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
        conn.commit()
    _migrate_ai_user_id_to_int()


def _migrate_ai_user_id_to_int() -> None:
    """One-shot migration: convierte user_id TEXT ('default') a INTEGER REFERENCES users(id).

    Idempotente: se ejecuta solo si la columna user_id todavía es TEXT.
    Filas que no pueden ser asignadas a un usuario real se eliminan."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for table, unique_cols in [
                ("service_profiles",    ["user_id"]),
                ("ai_opportunity_fits", ["opportunity_id", "user_id"]),
            ]:
                cur.execute(
                    """
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = %s AND column_name = 'user_id'
                    """,
                    (table,),
                )
                row = cur.fetchone()
                if not row or row["data_type"] in ("integer", "bigint"):
                    continue  # ya migrado o tabla no existe

                logger.info("migrate user_id TEXT -> INTEGER", extra={"table": table})
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id_int INTEGER REFERENCES users(id) ON DELETE CASCADE")
                cur.execute("SELECT MIN(id) AS uid FROM users")
                first_user = cur.fetchone()
                first_uid = first_user["uid"] if first_user else None
                if first_uid is not None:
                    cur.execute(f"UPDATE {table} SET user_id_int = %s WHERE user_id_int IS NULL", (first_uid,))
                # Eliminar filas que no se pudieron asignar (no había user)
                cur.execute(f"DELETE FROM {table} WHERE user_id_int IS NULL")
                # Dropear constraint/index dependientes del user_id viejo
                if unique_cols == ["user_id"]:
                    cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_user_id_key")
                else:
                    cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_opportunity_id_user_id_key")
                cur.execute(f"DROP INDEX IF EXISTS idx_ai_fits_user")
                cur.execute(f"ALTER TABLE {table} DROP COLUMN user_id")
                cur.execute(f"ALTER TABLE {table} RENAME COLUMN user_id_int TO user_id")
                cur.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")
                if unique_cols == ["user_id"]:
                    cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_user_id_key UNIQUE (user_id)")
                else:
                    cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_opportunity_id_user_id_key UNIQUE (opportunity_id, user_id)")
                if table == "ai_opportunity_fits":
                    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_ai_fits_user ON ai_opportunity_fits (user_id, fit_score DESC)")
        conn.commit()


def upsert_service_profile(user_id: int, company_name: str, services: list,
                           regions: list = None, contract_sizes: list = None,
                           known_mandantes: list = None, company_key: str = None,
                           onboarding_done: bool = False) -> Dict[str, Any]:
    sql = """
    INSERT INTO service_profiles (user_id, company_key, company_name, services,
                                   regions, contract_sizes, known_mandantes,
                                   onboarding_done, updated_at)
    VALUES (%(user_id)s, %(company_key)s, %(company_name)s, %(services)s,
            %(regions)s, %(contract_sizes)s, %(known_mandantes)s,
            %(onboarding_done)s, NOW())
    ON CONFLICT (user_id) DO UPDATE SET
        company_key       = COALESCE(EXCLUDED.company_key, service_profiles.company_key),
        company_name      = EXCLUDED.company_name,
        services          = EXCLUDED.services,
        regions           = EXCLUDED.regions,
        contract_sizes    = EXCLUDED.contract_sizes,
        known_mandantes   = EXCLUDED.known_mandantes,
        onboarding_done   = EXCLUDED.onboarding_done,
        updated_at        = NOW()
    RETURNING *;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "user_id": user_id,
                "company_key": company_key,
                "company_name": company_name,
                "services": Json(services or []),
                "regions": Json(regions or []),
                "contract_sizes": Json(contract_sizes or []),
                "known_mandantes": Json(known_mandantes or []),
                "onboarding_done": onboarding_done,
            })
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def get_service_profile(user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM service_profiles WHERE user_id = %(user_id)s LIMIT 1;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id})
            row = cur.fetchone()
    return dict(row) if row else None


def upsert_ai_fit(opportunity_id: int, user_id: int, fit_score: int,
                  fit_reason: str, service_applicable: str,
                  contact_suggestion: str, model_version: str = "claude-sonnet-4-6") -> None:
    sql = """
    INSERT INTO ai_opportunity_fits
        (opportunity_id, user_id, fit_score, fit_reason, service_applicable, contact_suggestion, model_version, scored_at)
    VALUES
        (%(opp_id)s, %(user_id)s, %(score)s, %(reason)s, %(service)s, %(contact)s, %(model)s, NOW())
    ON CONFLICT (opportunity_id, user_id) DO UPDATE SET
        fit_score = EXCLUDED.fit_score,
        fit_reason = EXCLUDED.fit_reason,
        service_applicable = EXCLUDED.service_applicable,
        contact_suggestion = EXCLUDED.contact_suggestion,
        model_version = EXCLUDED.model_version,
        scored_at = NOW();
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "opp_id": opportunity_id, "user_id": user_id,
                "score": fit_score, "reason": fit_reason,
                "service": service_applicable, "contact": contact_suggestion,
                "model": model_version
            })
        conn.commit()


def get_ai_fit(opportunity_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT * FROM ai_opportunity_fits WHERE opportunity_id=%(opp_id)s AND user_id=%(user_id)s;"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"opp_id": opportunity_id, "user_id": user_id})
            row = cur.fetchone()
    return dict(row) if row else None


def list_opportunities_for_ai_scoring(user_id: int, limit: int = 500) -> List[Dict[str, Any]]:
    """Retorna oportunidades que aún no tienen AI fit score o fueron actualizadas después del último score."""
    sql = """
    SELECT o.id, o.title, o.source, o.company, o.industry, o.region, o.phase,
           o.score, o.url, o.entry, o.raw, o.updated_at,
           f.fit_score, f.scored_at
    FROM opportunities o
    LEFT JOIN ai_opportunity_fits f ON f.opportunity_id = o.id AND f.user_id = %(user_id)s
    WHERE o.source NOT IN ('Lithium Chile','Portal Minero','Revista EI',
                           'Minería Chilena','Diario Financiero','COCHILCO Noticias',
                           'InfoMineria','Mundo Minería')
      AND (f.id IS NULL OR o.updated_at > f.scored_at)
    ORDER BY o.score DESC
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "limit": limit})
            return [dict(r) for r in cur.fetchall()]



def get_ai_fits(user_id: int, min_score: int = 0, limit: int = 500) -> List[Dict[str, Any]]:
    """Retorna los scores IA calculados para la empresa, con datos del proyecto."""
    sql = """
    SELECT f.opportunity_id as id, f.fit_score, f.fit_reason,
           f.service_applicable, f.contact_suggestion, f.scored_at,
           o.title, o.source, o.company, o.region, o.phase, o.url, o.score
    FROM ai_opportunity_fits f
    JOIN opportunities o ON o.id = f.opportunity_id
    WHERE f.user_id = %(user_id)s AND f.fit_score >= %(min_score)s
    ORDER BY f.fit_score DESC, o.score DESC
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "min_score": min_score, "limit": limit})
            return [dict(r) for r in cur.fetchall()]


def list_top_ai_fits(user_id: int, min_score: int = 40, limit: int = 200) -> List[Dict[str, Any]]:
    sql = """
    SELECT o.*, f.fit_score, f.fit_reason, f.service_applicable, f.contact_suggestion, f.scored_at,
           COALESCE(s.signal_score, 0) as signal_score,
           (o.score + COALESCE(s.signal_score,0)) as radar_score
    FROM ai_opportunity_fits f
    JOIN opportunities o ON o.id = f.opportunity_id
    LEFT JOIN opportunity_signals s ON s.opportunity_id = o.id
    WHERE f.user_id = %(user_id)s AND f.fit_score >= %(min_score)s
    ORDER BY f.fit_score DESC, o.score DESC
    LIMIT %(limit)s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "min_score": min_score, "limit": limit})
            return [dict(r) for r in cur.fetchall()]

def upsert_mandante_heat(company: str, heat_score: int, heat_label: str,
                         heat_reason: str, n_noticias: int, n_empleos: int,
                         trending_topics: list, model_version: str = "claude-sonnet-4-6") -> None:
    sql = """
    INSERT INTO mandante_heat
        (company, heat_score, heat_label, heat_reason, n_noticias, n_empleos,
         trending_topics, scored_at, model_version)
    VALUES
        (%(company)s, %(heat_score)s, %(heat_label)s, %(heat_reason)s,
         %(n_noticias)s, %(n_empleos)s, %(topics)s, NOW(), %(model)s)
    ON CONFLICT (company) DO UPDATE SET
        heat_score     = EXCLUDED.heat_score,
        heat_label     = EXCLUDED.heat_label,
        heat_reason    = EXCLUDED.heat_reason,
        n_noticias     = EXCLUDED.n_noticias,
        n_empleos      = EXCLUDED.n_empleos,
        trending_topics= EXCLUDED.trending_topics,
        scored_at      = NOW(),
        model_version  = EXCLUDED.model_version;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "company":    company,
                "heat_score": heat_score,
                "heat_label": heat_label,
                "heat_reason": heat_reason[:500],
                "n_noticias": n_noticias,
                "n_empleos":  n_empleos,
                "topics":     trending_topics,
                "model":      model_version,
            })
        conn.commit()


def get_mandante_heat(company: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM mandante_heat WHERE company = %(c)s", {"c": company})
            r = cur.fetchone()
            return dict(r) if r else None


def get_all_mandante_heat() -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM mandante_heat ORDER BY heat_score DESC")
            return [dict(r) for r in cur.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# RADAR FUTURO — Vista de demanda anticipada por hitos SEA
# ══════════════════════════════════════════════════════════════════════════════

def get_radar_futuro(
    horizon_months: int = 36,
    min_score: int = 40,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Retorna proyectos SEA ordenados por fecha estimada de contratación.
    Solo incluye proyectos con sea_milestone calculado.

    Args:
        horizon_months: Máximo de meses hacia adelante (default 36)
        min_score: Score mínimo del proyecto (default 40)
        limit: Límite de resultados
    """
    sql = """
    SELECT
        o.id, o.title, o.company, o.region, o.phase, o.score,
        o.signal_score, o.url,
        (o.score + COALESCE(o.signal_score, 0)) AS radar_score,
        o.raw->'sea_milestone' AS milestone,
        (o.raw->'sea_milestone'->>'predicted_contracting_date') AS predicted_date,
        (o.raw->'sea_milestone'->>'predicted_contracting_months')::int AS months_out,
        (o.raw->'sea_milestone'->>'confidence') AS confidence,
        (o.raw->'sea_milestone'->>'milestone_reason') AS milestone_reason,
        o.raw->>'INVERSION_US' AS inversion_usd,
        mh.heat_score AS mandante_heat,
        mh.heat_label AS mandante_heat_label
    FROM opportunities o
    LEFT JOIN mandante_heat mh ON LOWER(TRIM(mh.company)) = LOWER(TRIM(o.company))
    WHERE o.source = 'SEA'
      AND o.raw ? 'sea_milestone'
      AND (o.raw->'sea_milestone'->>'predicted_contracting_months')::int <= %(horizon)s
      AND o.score >= %(min_score)s
      AND NOT (o.phase ILIKE '%%desistido%%' OR o.phase ILIKE '%%rechazado%%')
      AND (
          o.industry = 'Minería'
          OR LOWER(o.title) ~ '(miner|cobre|litio|oro|plata|salar|faena|concentrador|lixiviaci|nitr[oó]geno|molibdeno|hierro|codelco|escondida|collahuasi|sqm)'
      )
      AND LOWER(o.title) NOT SIMILAR TO '%%(hidrogeno|hidrógeno|eólico|eolico|solar|fotovoltaic|termosolar|wind|biomasa|geotermia|acuicultura|forestal|pesca|portuario|autopista|aeropuerto|hospital|vivienda|inmobiliaria)%%'
    ORDER BY
      (o.raw->'sea_milestone'->>'predicted_contracting_months')::int ASC,
      (o.score + COALESCE(o.signal_score, 0)) DESC
    LIMIT %(limit)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"horizon": horizon_months, "min_score": min_score, "limit": limit})
            rows = cur.fetchall()

    results = []
    for r in rows:
        row = dict(r)
        # Convertir JSONB a dict si viene como string
        for k in ("milestone",):
            if isinstance(row.get(k), str):
                try:
                    import json as _json
                    row[k] = _json.loads(row[k])
                except Exception:
                    pass
        results.append(row)
    return results


def get_radar_futuro_buckets(horizon_months: int = 36, min_score: int = 40) -> Dict[str, Any]:
    """Agrupa el radar futuro en buckets de tiempo para vista de dashboard."""
    all_projects = get_radar_futuro(horizon_months=horizon_months, min_score=min_score, limit=500)
    buckets: Dict[str, List] = {
        "0-6":   [],   # contratando ahora o muy pronto
        "6-18":  [],   # corto plazo
        "18-36": [],   # mediano plazo
    }
    for p in all_projects:
        m = p.get("months_out") or 999
        if m <= 6:    buckets["0-6"].append(p)
        elif m <= 18: buckets["6-18"].append(p)
        else:         buckets["18-36"].append(p)

    return {
        "total": len(all_projects),
        "buckets": {
            k: {"count": len(v), "projects": v}
            for k, v in buckets.items()
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE OUTCOME — Feedback loop desde CRM
# ══════════════════════════════════════════════════════════════════════════════

VALID_OUTCOMES = {"won", "lost", "stalled", "in_progress"}


def set_pipeline_outcome(
    opportunity_id: int,
    outcome: str,
    notes: str = "",
) -> bool:
    """
    Registra el resultado de un proyecto en el pipeline.
    Retorna True si actualizó, False si el pipeline no existe.

    outcome: 'won' | 'lost' | 'stalled' | 'in_progress'
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome debe ser uno de {VALID_OUTCOMES}")

    sql = """
    UPDATE opportunity_pipeline
    SET outcome = %(outcome)s,
        outcome_date = NOW(),
        outcome_notes = %(notes)s,
        updated_at = NOW()
    WHERE opportunity_id = %(opp_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "outcome": outcome,
                "notes": notes[:1000],
                "opp_id": opportunity_id,
            })
            updated = cur.rowcount
        conn.commit()
    return updated > 0


def get_outcome_stats() -> Dict[str, Any]:
    """
    Estadísticas de outcomes para calibración del scoring.
    Muestra qué distribución de scores tienen los proyectos que se ganaron vs perdieron.
    """
    sql = """
    SELECT
        p.outcome,
        COUNT(*) as n,
        ROUND(AVG(o.score)) as avg_score,
        ROUND(AVG(o.signal_score)) as avg_signal,
        MIN(o.score) as min_score,
        MAX(o.score) as max_score
    FROM opportunity_pipeline p
    JOIN opportunities o ON o.id = p.opportunity_id
    WHERE p.outcome IS NOT NULL
    GROUP BY p.outcome
    ORDER BY p.outcome
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
    return {"outcomes": rows}


def _compute_confidence(item: Dict[str, Any]) -> str:
    """
    Calcula nivel de confianza del score basado en calidad de datos.
    'high' = múltiples fuentes, inversión confirmada, empresa conocida.
    'medium' = datos parciales.
    'low' = datos mínimos.
    """
    score = 0
    raw = item.get("raw") or {}

    if raw.get("INVERSION_US"):                   score += 2
    if item.get("company"):                       score += 1
    if item.get("region"):                        score += 1
    if item.get("phase"):                         score += 1
    if raw.get("cross_source_confirmed"):         score += 3   # confirmado multi-fuente
    if raw.get("sea_milestone"):                  score += 1
    if (item.get("signal_score") or 0) > 10:     score += 1

    if score >= 7:  return "high"
    if score >= 4:  return "medium"
    return "low"
