"""Stratmap Chile — entrypoint FastAPI.

Concierge file: lifespan, rate limiting, /health y registro de routers.
La lógica de cada feature vive en routers/.
"""
from contextlib import asynccontextmanager
from typing import Dict
from collections import defaultdict, deque
import asyncio
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger("stratmap.web")

# Sentry — opt-in via SENTRY_DSN
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
from db import db_health, init_db_safe, recalc_all_scores


_app_started_ts: float = time.time()
from routers import (
    auth as auth_router,
    opportunities as opportunities_router,
    pipeline as pipeline_router,
    contacts as contacts_router,
    me as me_router,
    mandantes as mandantes_router,
    empleos as empleos_router,
    admin as admin_router,
    billing as billing_router,
    static_pages as static_pages_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan del proceso web. NO arranca scheduler — eso vive en worker.py."""
    init_db_safe()
    try:
        db.init_ai_db()
    except Exception as e:
        logger.warning("init_ai_db failed", extra={"err": str(e)})
    try:
        import demand_intel
        demand_intel.init_demand_intel_db()
        logger.info("demand_intel db initialized")
    except Exception as e:
        logger.warning("demand_intel init failed", extra={"err": str(e)})
    try:
        result = recalc_all_scores()
        logger.info("scores recalculados",
                    extra={"updated": result["total_updated"],
                           "total": result["total_rows"],
                           "distribution": result["distribution"]})
    except Exception as e:
        logger.warning("recalc_all_scores failed", extra={"err": str(e)})

    # Normalizar source 'sea' → 'SEA' (inconsistencia en datos)
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE opportunities SET source = 'SEA' WHERE source = 'sea'")
                n = cur.rowcount
            conn.commit()
        if n:
            logger.info("sea_source_normalized", extra={"rows": n})
    except Exception as e:
        logger.warning("sea normalize failed", extra={"err": str(e)})

    # Noticias no deben tener score — reset al arrancar
    try:
        NEWS_SRCS = [
            'Lithium Chile', 'Portal Minero', 'Revista EI', 'Minería Chilena',
            'Diario Financiero', 'COCHILCO Noticias', 'InfoMineria', 'Mundo Minería',
            'Radio U. de Chile', 'Radio Universidad de Chile', 'BioBioChile', 'RSS',
        ]
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE opportunities SET score = 0, signal_score = 0 WHERE source = ANY(%s) AND score > 0",
                    (NEWS_SRCS,),
                )
            conn.commit()
        logger.info("news scores reset to 0")
    except Exception as e:
        logger.warning("reset news scores failed", extra={"err": str(e)})

    logger.info("web ready", extra={"note": "scheduler runs in worker.py"})
    yield


app = FastAPI(title="Stratmap Chile", lifespan=lifespan)


# ── Rate limiting ─────────────────────────────────────────────────────────────
# In-memory sliding-window rate limiter, per IP, per rule. Single-instance only;
# si escalamos a múltiples réplicas hay que migrar a backend con Redis.

_RATE_RULES = [
    ("/admin/",     2,   60),
    ("/auth/login", 5,   60),
    ("",            200, 60),
]
_rl_hits: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
_rl_lock = asyncio.Lock()


def _match_rate_rule(path: str):
    for prefix, max_req, window in _RATE_RULES:
        if path.startswith(prefix):
            return prefix, max_req, window
    return _RATE_RULES[-1]


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    ip = _client_ip(request)
    rule_key, max_req, window = _match_rate_rule(request.url.path)
    now = time.monotonic()
    cutoff = now - window

    async with _rl_lock:
        bucket = _rl_hits[rule_key][ip]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_req:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Demasiadas solicitudes. Límite: {max_req}/{window}s."},
                headers={"Retry-After": str(window)},
            )
        bucket.append(now)

    return await call_next(request)


# ── Healthcheck ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Healthcheck: DB, último scrape por fuente, liveness del worker (derivada
    del MAX(updated_at) en opportunities, ya que el scheduler corre en worker.py
    y no comparte estado de proceso con la web)."""
    now = time.time()
    db_ok, db_msg = db_health()

    last_scrape: Dict[str, str] = {}
    most_recent_scrape_ts: float = 0.0
    if db_ok:
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT source, MAX(updated_at) AS last
                        FROM opportunities
                        WHERE source IS NOT NULL
                        GROUP BY source
                        ORDER BY source
                    """)
                    for r in cur.fetchall():
                        if r.get("last"):
                            last_scrape[r["source"]] = r["last"].isoformat()
                            most_recent_scrape_ts = max(most_recent_scrape_ts, r["last"].timestamp())
        except Exception as e:
            last_scrape = {"error": f"{type(e).__name__}: {e}"}

    # Liveness del worker: si el último scrape (cualquier fuente) fue hace >8h,
    # asumimos que el worker está caído. Antes de 8h consideramos sano.
    if most_recent_scrape_ts > 0:
        worker = {
            "last_scrape_ts": most_recent_scrape_ts,
            "seconds_ago": int(now - most_recent_scrape_ts),
            "stale": (now - most_recent_scrape_ts) > 8 * 3600,
        }
    else:
        worker = {"last_scrape_ts": None, "warming_up": True}

    return {
        "status": "ok",
        "db_ok": db_ok,
        "db_msg": db_msg,
        "version": os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")[:8],
        "uptime_seconds": int(now - _app_started_ts),
        "worker": worker,
        "last_scrape_by_source": last_scrape,
    }


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router.router)
app.include_router(opportunities_router.router)
app.include_router(pipeline_router.router)
app.include_router(contacts_router.router)
app.include_router(me_router.router)
app.include_router(mandantes_router.router)
app.include_router(empleos_router.router)
app.include_router(admin_router.router)
app.include_router(billing_router.router)
app.include_router(static_pages_router.router)


# ── Static files (catch-all, debe ir último) ──────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")
