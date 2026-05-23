"""Background worker — scheduler de scrapers e ingest tasks.

Corre como servicio separado del web (ver Procfile).
Sustituye al scheduler que vivía en main.py lifespan.

Ciclo:
  - cada 6h: RSS ingest (rápido, alto refresco de noticias).
  - cada 24h (cada 4 ciclos): full ingest pipeline + AI scorer (zona gris)
    + expiración de licitaciones obsoletas.

Para que las tareas diarias corran al primer arranque, fijamos `cycle = 4`
en el inicio (no esperamos 24h para el primer full ingest).
"""
import asyncio
import os
import traceback

import db
from helpers import run_rss_ingest


SHORT_CYCLE_SECONDS = 6 * 3600   # RSS cada 6h
DAILY_EVERY_N_CYCLES = 4         # 4 * 6h = 24h


def _full_ingest():
    """Pipeline completo: SEA, RSS, ENAMI, SIGEX, careers scrapers, mandante scorer, ai_matcher."""
    import sea_ingest
    sea_ingest.main()


def _ai_scorer_zona_gris():
    import ai_scorer
    return ai_scorer.run(score_min=45, score_max=65, batch_size=20, max_batches=3)


def _init():
    db.init_db_safe()
    try:
        db.init_ai_db()
    except Exception as e:
        print(f"[worker] init_ai_db warning: {e}")


async def _loop():
    print(f"[worker] starting (pid={os.getpid()})")
    _init()
    loop = asyncio.get_event_loop()

    # Empezar en cycle 4 para que el primer arranque corra las tareas diarias.
    cycle = DAILY_EVERY_N_CYCLES
    while True:
        # ── RSS (cada ciclo de 6h) ────────────────────────────────────────────
        try:
            print(f"[worker] cycle {cycle}: RSS ingest")
            result = await loop.run_in_executor(None, run_rss_ingest)
            print(f"[worker] RSS: {result}")
        except Exception:
            traceback.print_exc()

        # ── Tareas diarias (cada 4 ciclos = 24h) ─────────────────────────────
        if cycle % DAILY_EVERY_N_CYCLES == 0:
            try:
                print("[worker] full ingest pipeline...")
                await loop.run_in_executor(None, _full_ingest)
            except Exception:
                traceback.print_exc()

            try:
                print("[worker] AI scorer zona gris...")
                ai_result = await loop.run_in_executor(None, _ai_scorer_zona_gris)
                print(f"[worker] AI scorer: {ai_result}")
            except Exception:
                traceback.print_exc()

            try:
                print("[worker] expirando licitaciones obsoletas...")
                expire = await loop.run_in_executor(None, db.expire_stale_opportunities)
                print(f"[worker] expire: {expire}")
            except Exception:
                traceback.print_exc()

        cycle += 1
        await asyncio.sleep(SHORT_CYCLE_SECONDS)


if __name__ == "__main__":
    asyncio.run(_loop())
