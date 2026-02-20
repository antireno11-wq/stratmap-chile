import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

import requests

from connectors.sea import fetch_sea  # debe existir y devolver list[dict]

TZ = ZoneInfo("America/Santiago")

BASE_URL = os.getenv("BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")

SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "90"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "800"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "120"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "6"))

# Espera máxima a que la API esté sana antes de arrancar (seg)
WAIT_HEALTH_SECONDS = int(os.getenv("WAIT_HEALTH_SECONDS", "180"))
HEALTH_POLL_SECONDS = float(os.getenv("HEALTH_POLL_SECONDS", "5"))

HEADERS = {
    "User-Agent": "StratmapWorker/0.1 (+railway; contact=ops)",
    "Accept": "application/json",
}


def now_clt() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


def wait_for_health(session: requests.Session) -> bool:
    url = f"{BASE_URL}/health"
    print(f"[{now_clt()}] waiting health: {url} (max {WAIT_HEALTH_SECONDS}s)")

    deadline = time.time() + WAIT_HEALTH_SECONDS
    last_msg = None

    while time.time() < deadline:
        try:
            r = session.get(url, timeout=15, headers=HEADERS)
            if r.status_code == 200:
                data = r.json()
                db_ok = bool(data.get("db_ok"))
                if db_ok:
                    print(f"[{now_clt()}] health OK: db_ok=true")
                    return True
                last_msg = f"health 200 but db_ok=false: {data.get('db_msg')}"
            else:
                last_msg = f"health status={r.status_code}"
        except Exception as e:
            last_msg = f"health exception: {type(e).__name__}: {e}"

        print(f"[{now_clt()}] {last_msg} | retry in {HEALTH_POLL_SECONDS}s")
        time.sleep(HEALTH_POLL_SECONDS)

    print(f"[{now_clt()}] health NOT OK after {WAIT_HEALTH_SECONDS}s -> continue anyway")
    return False


def post_ingest_batch(session: requests.Session, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{BASE_URL}/ingest"
    payload = {"items": batch}

    last_err: Exception | None = None

    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = session.post(url, json=payload, timeout=INGEST_TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            # backoff + jitter
            backoff = min(60, 2 ** attempt)
            jitter = random.uniform(0, 0.6)
            wait = backoff + jitter
            print(f"[{now_clt()}] ingest attempt {attempt}/{INGEST_RETRIES} failed: {e} | sleep {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries: {last_err}")


def run_sea_ingest() -> None:
    print(f"[{now_clt()}] SEA worker start -> {BASE_URL}")

    session = requests.Session()

    # 1) espera health
    wait_for_health(session)

    # 2) trae items
    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA fetched: {len(items)} items (days_back={SEA_DAYS_BACK}, limit={SEA_LIMIT})")

    if not items:
        print(f"[{now_clt()}] nothing to ingest")
        return

    total_ins = 0
    total_upd = 0

    # 3) ingesta por batches
    batch_num = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch_num += 1
        batch = items[i : i + BATCH_SIZE]

        res = post_ingest_batch(session, batch)

        total_ins += int(res.get("inserted", 0))
        total_upd += int(res.get("updated", 0))

        print(f"[{now_clt()}] batch {batch_num} ok: inserted={res.get('inserted')} updated={res.get('updated')} total={res.get('total')}")
        time.sleep(0.25)  # respiro

    print(f"[{now_clt()}] DONE sea_ingest inserted={total_ins} updated={total_upd}")


if __name__ == "__main__":
    run_sea_ingest()
