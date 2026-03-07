"""
sea_ingest.py — orquestador principal de ingesta
"""
from db import upsert_opportunities, init_db_safe

MINING_KEYWORDS = [
    "mina","minera","minero","cobre","litio","codelco","bhp","sqm","escondida",
    "collahuasi","relave","mineral","faena","concentradora","sernageomin",
    "cochilco","antofagasta","atacama","oro","plata","hierro","molibdeno",
    "exploración","yacimiento","planta","proyecto minero","licitación",
    "contrato","inversión","ampliación"
]
NON_MINING_KEYWORDS = [
    "fútbol","futbol","deporte","partido","gol","jugador","torneo","baleado",
    "disparado","pelea","riña","ketamina","droga","detenido","imputado",
    "alumbrado público","vertedero municipal","dólar cierra","bolsa de",
    "premundi","sub-20","sede deportiva","concesionado hospital"
]

def is_mining_relevant(item: dict) -> bool:
    """Filtra items claramente no relacionados con minería."""
    title = (item.get("title") or "").lower()
    # Rechazar si tiene keyword no minera
    if any(kw in title for kw in NON_MINING_KEYWORDS):
        return False
    # Para noticias RSS (fuentes genéricas), exigir al menos un keyword minero
    generic_sources = {"biobiochile","radio universidad de chile","radio u. de chile",
                       "cooperativa","emol","diario financiero"}
    src = (item.get("source") or "").lower()
    if src in generic_sources:
        return any(kw in title for kw in MINING_KEYWORDS)
    return True

def ingest(items, label):
    if items:
        ins, upd = upsert_opportunities(items)
        print(f"[{label}] {ins} nuevos, {upd} actualizados")
    else:
        print(f"[{label}] sin items")

def run_sea():
    try:
        from connectors.sea import fetch_sea
        ingest(fetch_sea(), "sea")
    except Exception as e:
        print(f"[sea] error: {e}")

def run_sea_signals():
    """Cruza proyectos SEA con licitaciones activas del mismo titular y sube signal_score."""
    try:
        from signals.sea_signals import run_sea_signals as _run
        result = _run()
        print(f"[sea_signals] {result}")
    except Exception as e:
        print(f"[sea_signals] error: {e}")
        import traceback; traceback.print_exc()

def run_rss():
    try:
        from connectors.rss import fetch_rss
        items = fetch_rss()
        filtered = [i for i in items if is_mining_relevant(i)]
        print(f"[rss] {len(items)} items → {len(filtered)} relevantes tras filtro minero")
        ingest(filtered, "rss")
    except Exception as e:
        print(f"[rss] error: {e}")

def run_mlp():
    try:
        from connectors.mlp_proveedores import fetch_mlp_proveedores
        ingest(fetch_mlp_proveedores(limit=100), "mlp")
    except Exception as e:
        print(f"[mlp] error: {e}")

def run_lithium_chile():
    try:
        from connectors.lithium_chile import fetch_lithium_chile
        ingest(fetch_lithium_chile(limit=100), "lithium_chile")
    except Exception as e:
        print(f"[lithium_chile] error: {e}")

def run_sicep():
    try:
        from connectors.sicep import fetch_sicep
        ingest(fetch_sicep(limit=200), "sicep")
    except Exception as e:
        print(f"[sicep] error: {e}")

def run_enami():
    try:
        from connectors.enami import fetch_enami
        ingest(fetch_enami(limit=100), "enami")
    except Exception as e:
        print(f"[enami] error: {e}")

def run_codelco():
    try:
        from connectors.codelco import fetch_codelco
        ingest(fetch_codelco(limit=200), "codelco")
    except Exception as e:
        print(f"[codelco] error: {e}")


def run_empleos():
    """Scrapea empleos mineros y cruza con proyectos para señales."""
    try:
        from connectors.empleos_indeed   import fetch_indeed
        from connectors.empleos_portales import fetch_portales
        from signals.empleos_signals     import run_empleos_signals

        print("[empleos] Iniciando scraping de empleos...")
        jobs = []

        try:
            jobs += fetch_indeed(limit=150)
        except Exception as e:
            print(f"[indeed] error: {e}")

        try:
            jobs += fetch_portales(limit=100)
        except Exception as e:
            print(f"[portales] error: {e}")

        print(f"[empleos] {len(jobs)} empleos totales recolectados")
        if jobs:
            run_empleos_signals(jobs)

    except Exception as e:
        print(f"[empleos] error general: {e}")
        import traceback; traceback.print_exc()


def run_sigex():
    try:
        from connectors.sigex_sernageomin import fetch_sigex
        ingest(fetch_sigex(limit=5000), "sigex")
    except Exception as e:
        print(f"[sigex] error: {e}")
        import traceback; traceback.print_exc()

def run_mundo_mineria():
    try:
        from connectors.mundo_mineria import fetch_mundo_mineria
        ingest(fetch_mundo_mineria(limit=100), "mundo_mineria")
    except Exception as e:
        print(f"[mundo_mineria] error: {e}")

def run_infomineria():
    try:
        from connectors.infomineria import fetch_infomineria
        ingest(fetch_infomineria(limit=100), "infomineria")
    except Exception as e:
        print(f"[infomineria] error: {e}")

def run_signals():
    try:
        from signals.jobs import run as jobs_run
        jobs_run()
    except Exception as e:
        print(f"[signals] error: {e}")

if __name__ == "__main__":
    print("[ingest] Iniciando...")
    init_db_safe()
    run_sea()
    run_sea_signals()
    run_rss()
    run_mlp()
    run_lithium_chile()
    run_sicep()
    run_codelco()
    run_enami()
    run_sigex()
    run_infomineria()
    run_mundo_mineria()
    run_empleos()
    run_signals()
    print("[ingest] Ingesta completa")

    # ── Scoring IA personalizado ───────────────────────────────────────────
    # Corre después de cada ingesta para mantener scores actualizados
    print("[ingest] Iniciando scoring IA...")
    try:
        import ai_matcher
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT company_key FROM service_profiles
                    WHERE onboarding_done = TRUE
                      AND services IS NOT NULL AND services != '[]'
                      AND company_key IS NOT NULL
                """)
                rows = cur.fetchall()
        keys = [r[0] for r in rows if r[0]]
        if keys:
            print(f"[ingest] Scoring IA para {len(keys)} empresa(s): {keys}")
            for key in keys:
                result = ai_matcher.run(company_key=key, limit=500)
                print(f"[ingest] {key}: {result}")
        else:
            print("[ingest] Sin perfiles con onboarding completo, skip scoring IA")
    except Exception as e:
        print(f"[ingest] Error en scoring IA: {e}")
        import traceback; traceback.print_exc()

    # ── BHP Careers ───────────────────────────────────────────────────────────
    print("[ingest] Scraping empleos BHP Chile...")
    try:
        import bhp_careers
        result = bhp_careers.run()
        print(f"[ingest] BHP Careers: {result}")
    except Exception as e:
        print(f"[ingest] Error BHP Careers: {e}")

    # ── AMSA Careers ──────────────────────────────────────────────────────────
    print("[ingest] Scraping empleos AMSA (Pelambres, Centinela, Zaldívar)...")
    try:
        import requests as _req
        r = _req.post("http://localhost:8000/admin/run-amsa-careers", timeout=60)
        result = r.json()
        print(f"[ingest] AMSA Careers: {result}")
    except Exception as e:
        print(f"[ingest] AMSA Careers error: {e}")

    # ── Teck Careers ──────────────────────────────────────────────────────────
    try:
        r = _req.post("http://localhost:8000/admin/run-teck-careers", timeout=60)
        result = r.json()
        print(f"[ingest] Teck Careers: {result}")
    except Exception as e:
        print(f"[ingest] Teck Careers error: {e}")

    # ── Collahuasi Careers ────────────────────────────────────────────────────
    try:
        r = _req.post("http://localhost:8000/admin/run-collahuasi-careers", timeout=60)
        result = r.json()
        print(f"[ingest] Collahuasi Careers: {result}")
    except Exception as e:
        print(f"[ingest] Collahuasi Careers error: {e}")

    # ── Lundin Mining Chile ────────────────────────────────────────────────────
    try:
        r = _req.post("http://localhost:8000/admin/run-lundin-careers", timeout=60)
        result = r.json()
        print(f"[ingest] Lundin Careers: {result}")
    except Exception as e:
        print(f"[ingest] Error AMSA Careers: {e}")
        import traceback; traceback.print_exc()

    # ── Scoring temperatura mandantes ─────────────────────────────────────────
    print("[ingest] Scoring temperatura de mandantes...")
    try:
        import mandante_scorer
        result = mandante_scorer.run()
        print(f"[ingest] Mandante scorer: {result}")
    except Exception as e:
        print(f"[ingest] Error en mandante scorer: {e}")
        import traceback; traceback.print_exc()

    print("[ingest] Listo")
