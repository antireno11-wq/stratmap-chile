import os
import time
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

import requests

# ==============
# CONFIG
# ==============
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")
PRIVATE_BASE_URL = os.getenv("PRIVATE_BASE_URL", "http://stratmap-chile.railway.internal:8080").rstrip("/")

# Si defines BASE_URL, lo usa como primera opción
BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")

SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "90"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "400"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "120"))
HEALTH_TIMEOUT = int(os.getenv("HEALTH_TIMEOUT", "15"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "5"))

DEBUG = os.getenv("DEBUG", "1") == "1"

# ==============
# HELPERS
# ==============
def now_clt() -> str:
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


def log(msg: str):
    print(f"[{now_clt()}] {msg}", flush=True)


def chunked(lst: list[dict], n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def try_health(base: str) -> tuple[bool, str]:
    url = f"{base}/health"
    try:
        r = requests.get(url, timeout=HEALTH_TIMEOUT)
        return (r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    except Exception as e:
        return (False, f"error: {type(e).__name__}: {e}")


def pick_base_url() -> str:
    """
    Orden:
    1) BASE_URL (si existe)
    2) PRIVATE_BASE_URL
    3) PUBLIC_BASE_URL
    """
    candidates = []
    if BASE_URL:
        candidates.append(BASE_URL)
    candidates.append(PRIVATE_BASE_URL)
    candidates.append(PUBLIC_BASE_URL)

    for base in candidates:
        ok, info = try_health(base)
        log(f"Health check -> {base}/health => {info}")
        if ok:
            log(f"✅ Usando BASE_URL = {base}")
            return base

    # Si ninguna sirve, igual devolvemos PUBLIC (para que el error quede claro)
    log("❌ Ningún health respondió OK. Me quedo con PUBLIC_BASE_URL para mostrar error real.")
    return PUBLIC_BASE_URL


# ==============
# SEA FETCH (placeholder / adapta al tuyo)
# ==============
# Si tu fetch_sea real está en connectors/sea.py, puedes importarlo en vez de esto:
# from connectors.sea import fetch_sea

def fetch_sea(days_back: int, limit: int) -> list[dict]:
    """
    👉 Reemplaza esta función por tu fetch_sea real.
    Por ahora devuelve vacío para que el worker no reviente.
    """
    return []


# ==============
# INGEST
# ==============
def post_ingest(base_url: str, items: list[dict]) -> dict:
    url = f"{base_url}/ingest"
    payload = {"items": items}

    last_err = None
    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = requests.post(url, json=payload, timeout=INGEST_TIMEOUT)
            if r.status_code >= 400:
                # imprime body para entender 422/500/502
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:800]}")
            return r.json()
        except Exception as e:
            last_err = e
            wait = min(2 ** attempt, 20)
            log(f"⚠️ ingest attempt {attempt}/{INGEST_RETRIES} falló: {type(e).__name__}: {e}")
            log(f"   reintento en {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries: {last_err}")


def run_sea_ingest():
    base_url = pick_base_url()

    log(f"SEA ingest start -> {base_url}")
    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    log(f"SEA fetched: {len(items)} items")

    if not items:
        log("Nada que ingestar (items=0).")
        return

    total_inserted = 0
    total_updated = 0
    total = 0

    for idx, batch in enumerate(chunked(items, BATCH_SIZE), start=1):
        log(f"POST /ingest batch {idx} (size={len(batch)}) ...")
        res = post_ingest(base_url, batch)
        log(f"✅ ingest batch {idx} -> {res}")

        total_inserted += int(res.get("inserted", 0) or 0)
        total_updated += int(res.get("updated", 0) or 0)
        total += int(res.get("total", 0) or len(batch))

    log(f"✅ DONE. inserted={total_inserted} updated={total_updated} total={total}")


if __name__ == "__main__":
    run_sea_ingest()
