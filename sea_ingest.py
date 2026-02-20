import os
import time
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests

from connectors.sea import fetch_sea  # tu fetch_sea actual que devuelve list[dict]


TZ = ZoneInfo("America/Santiago")

BASE_URL = os.getenv("BASE_URL", "https://stratmap-chile-production.up.railway.app")
SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "90"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "800"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "120"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "5"))


def now_clt() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


def health_ok() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def post_ingest_batch(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{BASE_URL}/ingest"
    payload = {"items": batch}

    last_err = None
    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = requests.post(url, json=payload, timeout=INGEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            wait = min(60, 2 ** attempt)
            print(f"[{now_clt()}] ingest attempt {attempt}/{INGEST_RETRIES} failed: {e} | sleep {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries: {last_err}")


def run_sea_ingest() -> None:
    print(f"[{now_clt()}] SEA worker start -> {BASE_URL}")

    # check health
    if not health_ok():
        print(f"[{now_clt()}] API health NO OK: {BASE_URL}/health")
        # igual intenta (a veces health está ok pero lento), pero avisamos
    else:
        print(f"[{now_clt()}] API health OK")

    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA fetched: {len(items)} items")

    if not items:
        print(f"[{now_clt()}] nothing to ingest")
        return

    total_ins = 0
    total_upd = 0

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        res = post_ingest_batch(batch)
        total_ins += int(res.get("inserted", 0))
        total_upd += int(res.get("updated", 0))
        print(f"[{now_clt()}] batch {i//BATCH_SIZE+1} ok: {res}")

        # pequeño respiro para no saturar
        time.sleep(0.2)

    print(f"[{now_clt()}] DONE sea_ingest inserted={total_ins} updated={total_upd}")


if __name__ == "__main__":
    run_sea_ingest()
