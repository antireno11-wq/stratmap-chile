# main.py
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field

from db import get_conn, init_db_safe


APP_NAME = os.getenv("APP_NAME", "stratmap-chile")
TZ = ZoneInfo("America/Santiago")

# Estado DB para healthcheck
DB_STATE: Dict[str, Any] = {"db_ok": False, "db_msg": "not initialized"}

app = FastAPI(title=APP_NAME)


# =========================
# Models
# =========================
class OpportunityIn(BaseModel):
    url: str = Field(..., min_length=8)
    title: str = Field(..., min_length=3)
    source: Optional[str] = None
    score: int = 0
    industry: Optional[str] = None  # Minería | Energía | Oil & Gas | Infraestructura | ...
    company: Optional[str] = None
    contractor: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    strategy: Optional[str] = None
    published_at: Optional[str] = None  # ISO string (opcional)


# =========================
# Helpers
# =========================
def now_clt_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


def _parse_ts(ts: Optional[str]):
    if not ts:
        return None
    try:
        # acepta "2026-02-17T12:34:56" o "2026-02-17 12:34:56"
        ts = ts.replace(" ", "T")
        dt = datetime.fromisoformat(ts)
        # si viene sin tz, lo asumimos Chile
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except Exception:
        return None


# =========================
# Startup
# =========================
@app.on_event("startup")
def startup():
    global DB_STATE
    DB_STATE = init_db_safe()


# =========================
# Routes
# =========================
@app.get("/")
def root():
    return {"ok": True, "service": APP_NAME, "time": now_clt_str()}


@app.get("/health")
def health():
    # Re-check rápido (sin reintentar mil veces)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1;")
                _ = cur.fetchone()
        db_ok = True
        db_msg = "ok"
    except Exception as e:
        db_ok = False
        db_msg = f"db error: {type(e).__name__}: {e}"

    return {"status": "ok", "time": now_clt_str(), "db_ok": db_ok, "db_msg": db_msg}


@app.post("/ingest")
def ingest(items: List[OpportunityIn]):
    """
    Inserta oportunidades (upsert por URL). Ideal para que un cron/job
    llame este endpoint con lo que juntó de RSS/SEA/etc.
    """
    if not items:
        return {"inserted": 0, "updated": 0}

    inserted = 0
    updated = 0

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for it in items:
                    pub_dt = _parse_ts(it.published_at)

                    # upsert por url
                    cur.execute(
                        """
                        insert into opportunities
                          (url, title, source, score, industry, company, contractor, region, phase, strategy, published_at)
                        values
                          (%s,  %s,    %s,     %s,    %s,       %s,      %s,        %s,    %s,    %s,       %s)
                        on conflict (url) do update set
                          title=excluded.title,
                          source=excluded.source,
                          score=excluded.score,
                          industry=excluded.industry,
                          company=excluded.company,
                          contractor=excluded.contractor,
                          region=excluded.region,
                          phase=excluded.phase,
                          strategy=excluded.strategy,
                          published_at=excluded.published_at
                        returning (xmax = 0) as inserted;
                        """,
                        (
                            it.url,
                            it.title,
                            it.source,
                            int(it.score or 0),
                            it.industry,
                            it.company,
                            it.contractor,
                            it.region,
                            it.phase,
                            it.strategy,
                            pub_dt,
                        ),
                    )
                    row = cur.fetchone()
                    # En Postgres: xmax=0 => insert, si no => update
                    if row and row[0] is True:
                        inserted += 1
                    else:
                        updated += 1

            conn.commit()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest DB error: {type(e).__name__}: {e}")

    return {"inserted": inserted, "updated": updated, "time": now_clt_str()}


@app.get("/opportunities")
def list_opportunities(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_score: int = Query(0, ge=0, le=100),
    industry: Optional[str] = None,
    company: Optional[str] = None,
    contractor: Optional[str] = None,
    q: Optional[str] = None,
):
    """
    Lista oportunidades desde Postgres con filtros.
    """
    where = ["score >= %s"]
    params: List[Any] = [min_score]

    if industry:
        where.append("lower(industry) = lower(%s)")
        params.append(industry)

    if company:
        where.append("lower(company) like lower(%s)")
        params.append(f"%{company}%")

    if contractor:
        where.append("lower(contractor) like lower(%s)")
        params.append(f"%{contractor}%")

    if q:
        where.append("(lower(title) like lower(%s) or lower(company) like lower(%s) or lower(contractor) like lower(%s))")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    sql = f"""
        select
          id, url, title, source, score, industry, company, contractor, region, phase, strategy,
          published_at, created_at
        from opportunities
        where {" and ".join(where)}
        order by score desc, coalesce(published_at, created_at) desc
        limit %s offset %s;
    """
    params.extend([limit, offset])

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

                cur.execute(f"select count(*) from opportunities where {' and '.join(where)};", params[:-2])
                total = cur.fetchone()[0]

        # rows viene como dict_row (en db.py), así que puede ser dict.
        return {"count": total, "items": rows, "time": now_clt_str()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List DB error: {type(e).__name__}: {e}")
