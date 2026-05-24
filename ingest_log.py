"""ingest_log — observabilidad de los conectores de ingesta.

Registra start/end/status/items de cada corrida de scraper en la tabla
`ingest_runs`. Resuelve el "scraper se murió hace 2 semanas y nadie se enteró".

Uso típico (en sea_ingest.py):

    from ingest_log import track_run

    @track_run("enami")
    def run_enami():
        from connectors.enami import fetch_enami
        return ingest(fetch_enami(limit=100), "ENAMI")
        # `ingest()` debe devolver dict {"inserted": n, "updated": m} para que el
        # tracker capture los conteos. Si devuelve None o algo más, queda en NULL.

El decorador captura excepciones y las loguea como 'error', preservando el
raise para que el comportamiento upstream no cambie.

Consultar la salud:

    GET /admin/health
"""
from __future__ import annotations

import functools
import time
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Optional

import db


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingest_runs (
    id           SERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'running',
    items_in     INT,
    items_upd    INT,
    error_msg    TEXT,
    duration_ms  INT
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_source_started
    ON ingest_runs (source, started_at DESC);
"""


def ensure_schema() -> None:
    """Idempotente. Llamar una vez al boot del worker / web."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
    except Exception as e:
        print(f"[ingest_log] no se pudo crear tabla ingest_runs: {e}")


def _insert_start(source: str) -> Optional[int]:
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ingest_runs (source, started_at) VALUES (%s, NOW()) RETURNING id",
                    (source,),
                )
                return cur.fetchone()["id"]
    except Exception as e:
        print(f"[ingest_log] insert_start failed: {e}")
        return None


def _finish(run_id: Optional[int], status: str, items_in: Optional[int],
            items_upd: Optional[int], error: Optional[str], elapsed_ms: int) -> None:
    if run_id is None:
        return
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE ingest_runs
                          SET finished_at = NOW(),
                              status      = %s,
                              items_in    = %s,
                              items_upd   = %s,
                              error_msg   = %s,
                              duration_ms = %s
                        WHERE id = %s""",
                    (status, items_in, items_upd, (error or "")[:1500], elapsed_ms, run_id),
                )
    except Exception as e:
        print(f"[ingest_log] finish failed: {e}")


def track_run(source: str) -> Callable:
    """Decorador. La función decorada puede devolver:
        - dict con keys 'inserted' y 'updated'  → se guardan en items_in/items_upd
        - cualquier otra cosa o None             → quedan en NULL pero status='ok'
       Si lanza excepción, status='error' y se re-raisea.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            run_id = _insert_start(source)
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                items_in = items_upd = None
                if isinstance(result, dict):
                    items_in  = result.get("inserted")
                    items_upd = result.get("updated")
                # 'empty' si corrió sin problemas pero no trajo nada nuevo
                status = "empty" if (items_in is not None and items_in == 0 and items_upd in (0, None)) else "ok"
                _finish(run_id, status, items_in, items_upd, None, int((time.time() - t0) * 1000))
                return result
            except Exception as e:
                err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}"
                _finish(run_id, "error", None, None, err, int((time.time() - t0) * 1000))
                raise
        return wrapper
    return decorator


@contextmanager
def manual_run(source: str):
    """Variante context manager para flujos no decorables.
       Devuelve un dict mutable; el caller setea 'inserted'/'updated'.

           with manual_run('cmf') as r:
               items = fetch_cmf()
               r['inserted'] = len(items)
    """
    run_id = _insert_start(source)
    t0 = time.time()
    r: dict = {}
    try:
        yield r
        status = "empty" if (r.get("inserted") in (0, None) and r.get("updated") in (0, None)) else "ok"
        _finish(run_id, status, r.get("inserted"), r.get("updated"), None, int((time.time() - t0) * 1000))
    except Exception as e:
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}"
        _finish(run_id, "error", None, None, err, int((time.time() - t0) * 1000))
        raise


def health_summary() -> list[dict]:
    """Última corrida por fuente + semáforo de antigüedad.
       Devuelve lista ordenada por riesgo (rojo primero)."""
    sql = """
    WITH latest AS (
        SELECT DISTINCT ON (source)
            source, started_at, finished_at, status, items_in, items_upd,
            error_msg, duration_ms,
            EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600 AS age_hours
        FROM ingest_runs
        ORDER BY source, started_at DESC
    )
    SELECT * FROM latest
    ORDER BY
        CASE status WHEN 'error' THEN 0 ELSE 1 END,
        age_hours DESC;
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[ingest_log] health_summary failed: {e}")
        return []

    for r in rows:
        age = float(r.get("age_hours") or 0)
        st  = r.get("status") or ""
        if st == "error":
            light = "red"
        elif age >= 48:
            light = "red"
        elif age >= 30:
            light = "yellow"
        elif st == "empty" and age >= 24:
            light = "yellow"
        else:
            light = "green"
        r["traffic_light"] = light
        r["age_hours"] = round(age, 1)
        for k in ("started_at", "finished_at"):
            if r.get(k) is not None:
                r[k] = r[k].isoformat()
    return rows
