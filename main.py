"""Stratmap Chile — entrypoint FastAPI.

Concierge file: lifespan, scheduler, rate limiting, /health y registro
de routers. La lógica de cada feature vive en routers/.
"""
from contextlib import asynccontextmanager
from typing import Dict
from collections import defaultdict, deque
import asyncio
import time

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import db
from db import db_health, init_db_safe, recalc_all_scores, expire_stale_opportunities
from helpers import run_rss_ingest
from routers import (
    auth as auth_router,
    opportunities as opportunities_router,
    pipeline as pipeline_router,
    contacts as contacts_router,
    me as me_router,
    mandantes as mandantes_router,
    empleos as empleos_router,
    admin as admin_router,
    static_pages as static_pages_router,
)


# ── Background scheduler ──────────────────────────────────────────────────────

async def _rss_scheduler():
    """Corre RSS cada 6h y tareas diarias (ai scorer + expire stale) cada 24h."""
    await asyncio.sleep(10)
    cycle = 0
    while True:
        print("[scheduler] Corriendo RSS ingest...")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_rss_ingest)
        print(f"[scheduler] RSS done: {result}")

        cycle += 1
        if cycle % 4 == 0:
            print("[scheduler] Corriendo AI scorer zona gris...")
            try:
                import ai_scorer
                ai_result = await loop.run_in_executor(
                    None, lambda: ai_scorer.run(score_min=45, score_max=65, batch_size=20, max_batches=3)
                )
                print(f"[scheduler] AI scorer done: {ai_result}")
            except Exception as e:
                print(f"[scheduler] AI scorer error: {e}")

            print("[scheduler] Expirando licitaciones obsoletas...")
            try:
                expire_result = await loop.run_in_executor(None, expire_stale_opportunities)
                print(f"[scheduler] Expire done: {expire_result}")
            except Exception as e:
                print(f"[scheduler] Expire error: {e}")

        await asyncio.sleep(6 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_safe()
    try:
        db.init_ai_db()
    except Exception as e:
        print(f"[startup] init_ai_db warning: {e}")
    try:
        import demand_intel
        demand_intel.init_demand_intel_db()
        print("[startup] demand_intel DB inicializada")
    except Exception as e:
        print(f"[startup] demand_intel init warning: {e}")
    try:
        result = recalc_all_scores()
        print(f"[startup] Scores recalculados: {result['total_updated']} actualizados de {result['total_rows']} total")
        print(f"[startup] Distribución: {result['distribution']}")
    except Exception as e:
        print(f"[startup] Warning recalc scores: {e}")

    # Normalizar source 'sea' → 'SEA' (inconsistencia en datos)
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE opportunities SET source = 'SEA' WHERE source = 'sea'")
                n = cur.rowcount
            conn.commit()
        if n:
            print(f"[startup] Normalizado {n} registros 'sea' → 'SEA'")
    except Exception as e:
        print(f"[startup] Warning SEA normalize: {e}")

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
        print("[startup] Scores de noticias reseteados a 0")
    except Exception as e:
        print(f"[startup] Warning reset news scores: {e}")

    asyncio.create_task(_rss_scheduler())
    print("[startup] RSS scheduler iniciado (cada 6h)")
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
    db_ok, db_msg = db_health()
    return {"status": "ok", "db_ok": db_ok, "db_msg": db_msg}


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router.router)
app.include_router(opportunities_router.router)
app.include_router(pipeline_router.router)
app.include_router(contacts_router.router)
app.include_router(me_router.router)
app.include_router(mandantes_router.router)
app.include_router(empleos_router.router)
app.include_router(admin_router.router)
app.include_router(static_pages_router.router)


# ── Static files (catch-all, debe ir último) ──────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")
