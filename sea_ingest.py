"""
sea_ingest.py — orquestador principal de ingesta
"""
from db import upsert_opportunities, init_db_safe

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

def run_mop():
    try:
        from connectors.mop import fetch_all as mop_fetch
        ingest(mop_fetch(max_pages=15), "mop")
    except Exception as e:
        print(f"[mop] error: {e}")

def run_rss():
    try:
        from connectors.rss import fetch_rss
        ingest(fetch_rss(), "rss")
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
    run_mop()
    run_rss()
    run_mlp()
    run_lithium_chile()
    run_sicep()
    run_codelco()
    run_enami()
    run_infomineria()
    run_signals()
    print("[ingest] Listo")
