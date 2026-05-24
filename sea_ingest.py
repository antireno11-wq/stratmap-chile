"""
sea_ingest.py — orquestador principal de ingesta.

Cada run_*() lleva @track_run("source") (ver ingest_log.py) que registra cada
corrida en la tabla ingest_runs. Las excepciones se loguean ahí y se RE-RAISEAN
para que main() pueda decidir continuar o no — el pipeline NO debe morirse por
una sola fuente caída, así que main() envuelve cada call individualmente.
"""
from db import upsert_opportunities, init_db_safe
from mining_filters import is_mining_relevant as _is_mining_relevant
from ingest_log import track_run, ensure_schema as _ensure_ingest_log


def is_mining_relevant(item: dict) -> bool:
    """Wrapper compatible: extrae campos del dict y delega en mining_filters."""
    return _is_mining_relevant(
        item.get("title") or "",
        (item.get("raw") or {}).get("description", "") if isinstance(item.get("raw"), dict) else "",
        item.get("source") or "",
    )

def ingest(items, label) -> dict:
    """Inserta items y devuelve conteos para que @track_run los capture."""
    if not items:
        print(f"[{label}] sin items")
        return {"inserted": 0, "updated": 0}
    ins, upd = upsert_opportunities(items)
    print(f"[{label}] {ins} nuevos, {upd} actualizados")
    return {"inserted": int(ins or 0), "updated": int(upd or 0)}


@track_run("sea")
def run_sea():
    from connectors.sea import fetch_sea
    return ingest(fetch_sea(), "sea")

@track_run("sea_signals")
def run_sea_signals():
    """Cruza proyectos SEA con licitaciones activas del mismo titular y sube signal_score."""
    from signals.sea_signals import run_sea_signals as _run
    result = _run()
    print(f"[sea_signals] {result}")
    return {"inserted": int((result or {}).get("matched") or 0), "updated": 0} if isinstance(result, dict) else None

@track_run("rss")
def run_rss():
    from connectors.rss import fetch_rss
    items = fetch_rss()
    filtered = [i for i in items if is_mining_relevant(i)]
    print(f"[rss] {len(items)} items → {len(filtered)} relevantes tras filtro minero")
    return ingest(filtered, "rss")

@track_run("mlp")
def run_mlp():
    from connectors.mlp_proveedores import fetch_mlp_proveedores
    return ingest(fetch_mlp_proveedores(limit=100), "mlp")

@track_run("lithium_chile")
def run_lithium_chile():
    from connectors.lithium_chile import fetch_lithium_chile
    return ingest(fetch_lithium_chile(limit=100), "lithium_chile")

@track_run("sicep")
def run_sicep():
    from connectors.sicep import fetch_sicep
    return ingest(fetch_sicep(limit=200), "sicep")

@track_run("enami")
def run_enami():
    from connectors.enami import fetch_enami
    return ingest(fetch_enami(limit=100), "enami")

@track_run("codelco")
def run_codelco():
    from connectors.codelco import fetch_codelco
    return ingest(fetch_codelco(limit=200), "codelco")


@track_run("empleos")
def run_empleos():
    """Scrapea empleos mineros (Indeed + portales corporativos) y cruza con proyectos."""
    from connectors.empleos_indeed   import fetch_indeed
    from connectors.empleos_portales import fetch_portales
    from signals.empleos_signals     import run_empleos_signals

    print("[empleos] Iniciando scraping de empleos...")
    jobs = []
    try:
        jobs += fetch_indeed(limit=150)
    except Exception as e:
        print(f"[indeed] sub-error: {e}")
    try:
        jobs += fetch_portales(limit=100)
    except Exception as e:
        print(f"[portales] sub-error: {e}")

    print(f"[empleos] {len(jobs)} empleos totales recolectados")
    if jobs:
        run_empleos_signals(jobs)
    return {"inserted": len(jobs), "updated": 0}


def run_sigex():
    """DESACTIVADO 2026-05: las concesiones SIGEX son derechos sobre el suelo,
    no licitaciones — para un B2B de servicios a mandantes son ruido. El
    conector y los datos históricos siguen en la base; este wrapper queda
    vivo por si necesitamos re-activarlo."""
    return


@track_run("cmf")
def run_cmf():
    """Hechos esenciales CMF — señal regulatoria de alta calidad (inversiones,
    contratos, cambios de estrategia anunciados a la bolsa)."""
    from connectors.cmf import fetch_cmf
    return ingest(fetch_cmf(limit=200), "cmf")

@track_run("cochilco")
def run_cochilco():
    """COCHILCO: catastro oficial de inversiones mineras (proyectos con MUSD
    declarados, etapa, empresa, región) + RSS de noticias COCHILCO.
    Activado 2026-05 — estaba dormido como CMF."""
    from connectors.cochilco import fetch_cochilco
    return ingest(fetch_cochilco(limit=300), "cochilco")

@track_run("sigex_explotacion")
def run_sigex_explotacion():
    """SIGEX filtrado a TT_03 (Bienalidad Explotación) — confirma que un
    mandante mantiene activa una concesión productiva. Diferente del SIGEX
    general (retirado) que cubría exploración."""
    from connectors.sigex_sernageomin import fetch_sigex_explotacion
    return ingest(fetch_sigex_explotacion(limit=2000), "sigex_explotacion")

@track_run("dga_agua")
def run_dga_agua():
    """DGA: derechos de aprovechamiento de agua otorgados con uso minero o
    industrial. Señal TEMPRANA (6-18 meses antes que aparezca el EIA en SEA).
    Best-effort: si los endpoints DGA no responden, queda 'empty' en
    /health.html y se confirma el endpoint correcto a futuro."""
    from connectors.dga_agua import fetch_dga_agua
    return ingest(fetch_dga_agua(limit=500), "dga_agua")

@track_run("mundo_mineria")
def run_mundo_mineria():
    from connectors.mundo_mineria import fetch_mundo_mineria
    return ingest(fetch_mundo_mineria(limit=100), "mundo_mineria")

@track_run("infomineria")
def run_infomineria():
    from connectors.infomineria import fetch_infomineria
    return ingest(fetch_infomineria(limit=100), "infomineria")

@track_run("signals_jobs")
def run_signals():
    from signals.jobs import run as jobs_run
    jobs_run()
    return None


@track_run("score_events")
def run_score_events():
    """Recalcula opportunities.event_weight para las filas nuevas (NULL).
    Corre al final del pipeline para que el endpoint /mandantes y futuros
    consumidores tengan pesos frescos."""
    import score_events
    result = score_events.run(only_unscored=True)
    return {"inserted": int(result.get("processed") or 0), "updated": 0}


# Lista de (nombre, función) que main() itera. Centralizar acá hace que agregar
# una fuente sea una línea, y que el wrapper try/except sea uniforme.
PIPELINE: list[tuple[str, callable]] = [
    ("sea",            lambda: run_sea()),
    ("sea_signals",    lambda: run_sea_signals()),
    ("rss",            lambda: run_rss()),
    ("mlp",            lambda: run_mlp()),
    ("lithium_chile",  lambda: run_lithium_chile()),
    ("sicep",          lambda: run_sicep()),
    ("codelco",        lambda: run_codelco()),
    ("enami",          lambda: run_enami()),
    ("cmf",                lambda: run_cmf()),
    ("cochilco",           lambda: run_cochilco()),
    ("sigex_explotacion",  lambda: run_sigex_explotacion()),
    ("dga_agua",           lambda: run_dga_agua()),
    ("infomineria",        lambda: run_infomineria()),
    ("mundo_mineria",  lambda: run_mundo_mineria()),
    ("empleos",        lambda: run_empleos()),
    ("signals_jobs",   lambda: run_signals()),
    ("score_events",   lambda: run_score_events()),
]


def main() -> None:
    """Pipeline completo de ingesta. Llamable desde worker.py o como CLI."""
    print("[ingest] Iniciando...")
    init_db_safe()
    _ensure_ingest_log()

    for name, fn in PIPELINE:
        try:
            fn()
        except Exception as e:
            # @track_run ya registró 'error' en ingest_runs; acá solo evitamos
            # que se rompa el resto del pipeline.
            print(f"[{name}] excepción capturada en main(): {e}")

    print("[ingest] Ingesta completa")

    # ── Scoring IA personalizado por usuario ──────────────────────────────────
    # Corre después de cada ingesta para mantener scores actualizados.
    print("[ingest] Iniciando scoring IA por usuario...")
    try:
        import db as _db
        import ai_matcher
        with _db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id FROM service_profiles
                    WHERE onboarding_done = TRUE
                      AND services IS NOT NULL AND services != '[]'
                """)
                user_ids = [r["user_id"] for r in cur.fetchall()]
        if user_ids:
            print(f"[ingest] Scoring IA para {len(user_ids)} usuario(s): {user_ids}")
            for uid in user_ids:
                result = ai_matcher.run(user_id=uid, limit=500)
                print(f"[ingest] user_id={uid}: {result}")
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


if __name__ == "__main__":
    main()
