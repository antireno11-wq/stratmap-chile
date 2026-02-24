"""
sea_ingest.py — orquestador principal de ingesta
Corre todos los connectors y guarda en BD.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from db import upsert_opportunities, init_db_safe

TZ = ZoneInfo("America/Santiago")

def now_clt():
    return datetime.now(TZ).strftime("%H:%M:%S")

def ingest(items, label):
    if items:
        ins, upd = upsert_opportunities(items)
        print(f"[{label}] {ins} nuevos, {upd} actualizados")
    else:
        print(f"[{label}] sin items")

def run_sea():
    try:
        from connectors.sea import fetch_sea
        items = fetch_sea()
        ingest(items, "sea")
    except Exception as e:
        print(f"[sea] error: {e}")

def run_mop():
    try:
        from connectors.mop import fetch_all as mop_fetch
        items = mop_fetch(max_pages=15)
        ingest(items, "mop")
    except Exception as e:
        print(f"[mop] error: {e}")

def run_chilecompra():
    try:
        from connectors.chilebcompra import fetch_chilebcompra
        items = fetch_chilebcompra()
        ingest(items, "chilecompra")
    except Exception as e:
        print(f"[chilecompra] error: {e}")

def run_rss():
    try:
        from connectors.rss import fetch_rss
        items = fetch_rss()
        ingest(items, "rss")
    except Exception as e:
        print(f"[rss] error: {e}")

def run_sicep():
    try:
        from connectors.sicep import fetch_sicep
        items = fetch_sicep(limit=200)
        ingest(items, "sicep")
    except Exception as e:
        print(f"[sicep] error: {e}")

def run_mlp():
    try:
        from connectors.mlp_proveedores import fetch_mlp_proveedores
        items = fetch_mlp_proveedores(limit=100)
        ingest(items, "mlp")
    except Exception as e:
        print(f"[mlp] error: {e}")

def run_lithium_chile():
    try:
        from connectors.lithium_chile import fetch_lithium_chile
        items = fetch_lithium_chile(limit=100)
        ingest(items, "lithium_chile")
    except Exception as e:
        print(f"[lithium_chile] error: {e}")

def run_signals():
    try:
        from signals.jobs import run as jobs_run
        jobs_run()
    except Exception as e:
        print(f"[signals] error: {e}")

if __name__ == "__main__":
    print(f"[ingest] Iniciando...")
    init_db_safe()
    run_sea()
    run_mop()
    run_chilecompra()
    run_rss()
    run_sicep()
    run_mlp()
    run_lithium_chile()
    run_ariba()
    run_signals()
    print(f"[ingest] Listo")


def run_ariba():
    try:
        from connectors.ariba import fetch_ariba
        items = fetch_ariba(limit=200)
        ingest(items, "ariba")
    except Exception as e:
        print(f"[ariba] error: {e}")
