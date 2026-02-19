import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from connectors.sea import fetch_sea

# =========================
# Config
# =========================
PRIVATE_BASE_URL = os.getenv("BASE_URL", "http://stratmap-chile.railway.internal:8080").rstrip("/")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")

SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "90"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "300"))

INGEST_BATCH = int(os.getenv("INGEST_BATCH", "80"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "45"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "5"))
INGEST_RETRY_SLEEP = int(os.getenv("INGEST_RETRY_SLEEP", "5"))

DEBUG = os.getenv("DEBUG", "0") == "1"


def now_clt() -> str:
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


def chunked(lst: list[dict], size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def pick_base_url() -> str:
    # Prueba privada
    try:
        r = requests.get(f"{PRIVATE_BASE_URL}/health", timeout=8)
        if r.status_code == 200:
            print(f"[{now_clt()}] using PRIVATE base url: {PRIVATE_BASE_URL}")
            return PRIVATE_BASE_URL
        else:
            print(f"[{now_clt()}] private /health not 200: {r.status_code}")
    except Exception as e:
        print(f"[{now_clt()}] private base url failed: {e}")

    # Fallback pública
    print(f"[{now_clt()}] using PUBLIC base url: {PUBLIC_BASE_URL}")
    return PUBLIC_BASE_URL


def post_ingest_batch(base_url: str, batch: list[dict]) -> dict:
    url = f"{base_url}/ingest"
    payload = {"items": batch}

    last_err: Exception | None = None

    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = requests.post(url, json=payload, timeout=INGEST_TIMEOUT)
            if r.status_code >= 400:
                if DEBUG:
                    print(f"[{now_clt()}] ingest HTTP {r.status_code}: {r.text[:800]}")
                r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            print(f"[{now_clt()}] ingest attempt {attempt}/{INGEST_RETRIES} failed: {e}")
            time.sleep(INGEST_RETRY_SLEEP)

    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries: {last_err}")


def run_sea_ingest():
    base_url = pick_base_url()
    print(f"[{now_clt()}] SEA ingest start -> {base_url}")

    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA fetched: {len(items)} items")

    if not items:
        print(f"[{now_clt()}] nothing to ingest")
        return

    total_inserted = 0
    total_updated = 0

    for n, batch in enumerate(chunked(items, INGEST_BATCH), start=1):
        print(f"[{now_clt()}] ingest batch {n} size={len(batch)}")
        res = post_ingest_batch(base_url, batch)
        total_inserted += int(res.get("inserted", 0))
        total_updated += int(res.get("updated", 0))

    print(f"[{now_clt()}] DONE sea_ingest inserted={total_inserted} updated={total_updated}")


if __name__ == "__main__":
    run_sea_ingest()
