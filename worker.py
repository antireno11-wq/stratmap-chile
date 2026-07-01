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
import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger("stratmap.worker")

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.getenv("RAILWAY_ENVIRONMENT_NAME", "dev"),
        release=os.getenv("RAILWAY_GIT_COMMIT_SHA"),
        traces_sample_rate=0.05,
        send_default_pii=False,
    )
    logger.info("sentry initialized")

import db
from helpers import run_rss_ingest


SHORT_CYCLE_SECONDS = 6 * 3600   # RSS cada 6h
DAILY_EVERY_N_CYCLES = 4         # 4 * 6h = 24h


def _full_ingest():
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
        logger.warning("init_ai_db failed", extra={"err": str(e)})
    # El worker corre demand_intel (UPDATE opportunities.services_needed). La columna
    # + índice GIN los crea init_demand_intel_db(): sin esto el worker dependía de que
    # la web hubiera booteado antes (orden de deploy, no garantía).
    try:
        import demand_intel
        demand_intel.init_demand_intel_db()
    except Exception as e:
        logger.warning("init_demand_intel_db failed", extra={"err": str(e)})
    try:
        import ingest_log
        ingest_log.ensure_schema()  # tabla ingest_runs (observabilidad de scrapers)
    except Exception as e:
        logger.warning("ingest_log ensure_schema failed", extra={"err": str(e)})


async def _loop():
    logger.info("worker starting", extra={"pid": os.getpid()})
    _init()
    loop = asyncio.get_event_loop()

    # Empezar en cycle 1: el primer arranque solo corre RSS (rápido). El primer
    # daily ocurre cuando cycle=4 (24h después). Antes arrancaba con cycle=4 →
    # full ingest + Playwright bloqueaban todos los ciclos siguientes hasta
    # terminar (a veces horas), durante los cuales el RSS no refrescaba.
    cycle = 1
    while True:
        # ── RSS (cada ciclo de 6h) ────────────────────────────────────────────
        try:
            logger.info("rss ingest", extra={"cycle": cycle})
            result = await loop.run_in_executor(None, run_rss_ingest)
            logger.info("rss done", extra={"result": result})
        except Exception:
            logger.exception("rss failed")

        # ── Tareas diarias (cada 4 ciclos = 24h) ─────────────────────────────
        if cycle % DAILY_EVERY_N_CYCLES == 0:
            try:
                logger.info("full ingest pipeline")
                await loop.run_in_executor(None, _full_ingest)
            except Exception:
                logger.exception("full ingest failed")

            try:
                logger.info("ai scorer zona gris")
                ai_result = await loop.run_in_executor(None, _ai_scorer_zona_gris)
                logger.info("ai scorer done", extra={"result": ai_result})
            except Exception:
                logger.exception("ai scorer failed")

            try:
                logger.info("expire stale opportunities")
                expire = await loop.run_in_executor(None, db.expire_stale_opportunities)
                logger.info("expire done", extra={"result": expire})
            except Exception:
                logger.exception("expire failed")

        cycle += 1
        await asyncio.sleep(SHORT_CYCLE_SECONDS)


if __name__ == "__main__":
    asyncio.run(_loop())
