"""
sea_ingest.py — orquestador principal de ingesta
"""
from db import upsert_opportunities, init_db_safe
from mining_filters import is_mining_relevant as _is_mining_relevant


def is_mining_relevant(item: dict) -> bool:
    """Wrapper compatible: extrae campos del dict y delega en mining_filters."""
    return _is_mining_relevant(
        item.get("title") or "",
        (item.get("raw") or {}).get("description", "") if isinstance(item.get("raw"), dict) else "",
        item.get("source") or "",
    )

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
    """DESACTIVADO 2026-05: las concesiones SIGEX son derechos sobre el suelo,
    no licitaciones — para un B2B de servicios a mandantes son ruido. El
    conector y los datos históricos siguen en la base; este wrapper queda
    vivo por si necesitamos re-activarlo."""
    return


def run_cmf():
    """Hechos esenciales CMF — señal regulatoria de alta calidad (inversiones,
    contratos, cambios de estrategia anunciados a la bolsa)."""
    try:
        from connectors.cmf import fetch_cmf
        ingest(fetch_cmf(limit=200), "cmf")
    except Exception as e:
        print(f"[cmf] error: {e}")
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

def main() -> None:
    """Pipeline completo de ingesta. Llamable desde worker.py o como CLI."""
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
    run_cmf()
    run_infomineria()
    run_mundo_mineria()
    run_empleos()
    run_signals()
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
