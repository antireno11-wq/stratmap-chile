"""
sea_ingest.py — orquestador principal de ingesta
Corre todos los connectors y guarda en BD.
"""
import time
from db import upsert_opportunities, init_db_safe

def run_sea():
    try:
        from connectors.sea import fetch_all as sea_fetch
        items = sea_fetch()
        if items:
            ins, upd = upsert_opportunities(items)
            print(f"[sea] {ins} nuevos, {upd} actualizados")
    except Exception as e:
        print(f"[sea] error: {e}")

def run_mop():
    try:
        from connectors.mop import fetch_all as mop_fetch
        items = mop_fetch(max_pages=40)
        if items:
            ins, upd = upsert_opportunities(items)
            print(f"[mop] {ins} nuevos, {upd} actualizados")
    except Exception as e:
        print(f"[mop] error: {e}")

def run_chilecompra():
    try:
        from connectors.chilecompra import fetch_all as cc_fetch
        items = cc_fetch()
        if items:
            ins, upd = upsert_opportunities(items)
            print(f"[chilecompra] {ins} nuevos, {upd} actualizados")
    except Exception as e:
        print(f"[chilecompra] error: {e}")

def run_rss():
    try:
        from connectors.rss import fetch_all as rss_fetch
        items = rss_fetch()
        if items:
            ins, upd = upsert_opportunities(items)
            print(f"[rss] {ins} nuevos, {upd} actualizados")
    except Exception as e:
        print(f"[rss] error: {e}")

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
    run_chilecompra()
    run_rss()
    print("[ingest] Listo")
