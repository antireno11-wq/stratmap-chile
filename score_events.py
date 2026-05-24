"""score_events — recalcula opportunities.event_weight tras cada ingesta.

Función única: `run(batch_size=2000, only_unscored=True) -> dict`.

Si only_unscored=True (default), solo procesa filas con event_weight IS NULL —
ideal para correrlo después de cada ingesta sin pisar todo.

Si only_unscored=False, recalcula TODO. Útil cuando cambia la lógica de
scoring_v2 y querés refrescar el universo. Se invoca via /admin/run-score-events.
"""
from __future__ import annotations

import time
from typing import Optional

import db
from scoring_v2 import event_weight


def run(batch_size: int = 2000, only_unscored: bool = True) -> dict:
    """Recalcula event_weight para todas las filas (o solo las que tienen NULL).

    Estrategia: cursor por id ascendente. En modo only_unscored, el filtro
    "event_weight IS NULL" hace que el set se vacíe naturalmente. En modo full
    usamos `id > last_id` para no procesar dos veces.
    """
    t0 = time.time()
    processed = 0
    last_id = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            while True:
                if only_unscored:
                    cur.execute(
                        """SELECT id, source, title, raw, jobs_count
                             FROM opportunities
                            WHERE event_weight IS NULL
                            ORDER BY id
                            LIMIT %s""",
                        (batch_size,),
                    )
                else:
                    cur.execute(
                        """SELECT id, source, title, raw, jobs_count
                             FROM opportunities
                            WHERE id > %s
                            ORDER BY id
                            LIMIT %s""",
                        (last_id, batch_size),
                    )
                rows = cur.fetchall()
                if not rows:
                    break
                for r in rows:
                    w = event_weight({
                        "source": r.get("source"),
                        "title": r.get("title"),
                        "raw": r.get("raw"),
                        "jobs_count": r.get("jobs_count"),
                    })
                    cur.execute("UPDATE opportunities SET event_weight = %s WHERE id = %s", (w, r["id"]))
                    last_id = max(last_id, r["id"])
                conn.commit()
                processed += len(rows)
                if len(rows) < batch_size:
                    break
    return {
        "processed": processed,
        "duration_ms": int((time.time() - t0) * 1000),
    }
