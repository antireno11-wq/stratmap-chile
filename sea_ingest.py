import os
import sys
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from connectors.sea import fetch_sea
from connectors.chilebcompra import fetch_chilebcompra
from connectors.rss import fetch_rss

TZ = ZoneInfo("America/Santiago")
BASE_URL = os.getenv("BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")
SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "365"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "2000"))
CHILEBCOMPRA_DAYS_BACK = int(os.getenv("CHILEBCOMPRA_DAYS_BACK", "30"))
CHILEBCOMPRA_LIMIT = int(os.getenv("CHILEBCOMPRA_LIMIT", "500"))
RSS_DAYS_BACK = int(os.getenv("RSS_DAYS_BACK", "7"))
RSS_LIMIT = int(os.getenv("RSS_LIMIT", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "120"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "6"))
WAIT_HEALTH_SECONDS = int(os.getenv("WAIT_HEALTH_SECONDS", "180"))
HEALTH_POLL_SECONDS = float(os.getenv("HEALTH_POLL_SECONDS", "5"))

HEADERS = {
    "User-Agent": "StratmapWorker/0.2 (+railway; contact=ops)",
    "Accept": "application/json",
}


def now_clt() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


def wait_for_health(session: requests.Session) -> bool:
    url = f"{BASE_URL}/health"
    print(f"[{now_clt()}] waiting health: {url} (max {WAIT_HEALTH_SECONDS}s)")
    deadline = time.time() + WAIT_HEALTH_SECONDS
    while time.time() < deadline:
        try:
            r = session.get(url, timeout=15, headers=HEADERS)
            if r.status_code == 200 and r.json().get("db_ok"):
                print(f"[{now_clt()}] health OK")
                return True
        except Exception as e:
            print(f"[{now_clt()}] health check: {e}")
        time.sleep(HEALTH_POLL_SECONDS)
    print(f"[{now_clt()}] health NOT OK -> continue anyway")
    return False


def post_ingest_batch(session: requests.Session, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{BASE_URL}/ingest"
    last_err = None
    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = session.post(url, json={"items": batch}, timeout=INGEST_TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            wait = min(60, 2 ** attempt) + random.uniform(0, 0.6)
            print(f"[{now_clt()}] ingest attempt {attempt}/{INGEST_RETRIES} failed: {e} | sleep {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries: {last_err}")


def ingest_items(session: requests.Session, items: List[Dict[str, Any]], source: str) -> None:
    if not items:
        print(f"[{now_clt()}] {source}: nothing to ingest")
        return

    total_ins = total_upd = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        res = post_ingest_batch(session, batch)
        total_ins += int(res.get("inserted", 0))
        total_upd += int(res.get("updated", 0))
        print(f"[{now_clt()}] {source} batch ok: inserted={res.get('inserted')} updated={res.get('updated')}")
        time.sleep(0.25)

    print(f"[{now_clt()}] {source} DONE: inserted={total_ins} updated={total_upd}")


def run() -> None:
    print(f"[{now_clt()}] Worker start -> {BASE_URL}")
    session = requests.Session()
    wait_for_health(session)

    # ── SEA ──
    print(f"[{now_clt()}] Fetching SEA...")
    sea_items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA fetched: {len(sea_items)} items")
    ingest_items(session, sea_items, "SEA")

    # ── ChileCompra ──
    print(f"[{now_clt()}] Fetching ChileCompra...")
    cb_items = fetch_chilebcompra(days_back=CHILEBCOMPRA_DAYS_BACK, limit=CHILEBCOMPRA_LIMIT)
    print(f"[{now_clt()}] ChileCompra fetched: {len(cb_items)} items")
    ingest_items(session, cb_items, "ChileCompra")

    # ── RSS ──
    print(f"[{now_clt()}] Fetching RSS...")
    rss_items = fetch_rss(days_back=RSS_DAYS_BACK, limit=RSS_LIMIT)
    print(f"[{now_clt()}] RSS fetched: {len(rss_items)} items")
    ingest_items(session, rss_items, "RSS")

    print(f"[{now_clt()}] Worker finished")


if __name__ == "__main__":
    run()
