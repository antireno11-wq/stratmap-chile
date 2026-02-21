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
from connectors.rss_mineria import fetch_rss_mineria
from connectors.cochilco import fetch_cochilco
from connectors.mop import fetch_mop

TZ = ZoneInfo("America/Santiago")
BASE_URL = os.getenv("BASE_URL", "https://stratmap-chile-production.up.railway.app").rstrip("/")
SEA_DAYS_BACK = int(os.getenv("SEA_DAYS_BACK", "365"))
SEA_LIMIT = int(os.getenv("SEA_LIMIT", "2000"))
CHILEBCOMPRA_DAYS_BACK = int(os.getenv("CHILEBCOMPRA_DAYS_BACK", "30"))
CHILEBCOMPRA_LIMIT = int(os.getenv("CHILEBCOMPRA_LIMIT", "500"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "120"))
INGEST_RETRIES = int(os.getenv("INGEST_RETRIES", "6"))
WAIT_HEALTH_SECONDS = int(os.getenv("WAIT_HEALTH_SECONDS", "180"))
HEALTH_POLL_SECONDS = float(os.getenv("HEALTH_POLL_SECONDS", "5"))

HEADERS = {"User-Agent": "StratmapWorker/0.2", "Accept": "application/json"}


def now_clt() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CLT")


def wait_for_health(session: requests.Session) -> bool:
    url = f"{BASE_URL}/health"
    print(f"[{now_clt()}] waiting health: {url}")
    deadline = time.time() + WAIT_HEALTH_SECONDS
    while time.time() < deadline:
        try:
            r = session.get(url, timeout=15, headers=HEADERS)
            if r.status_code == 200 and r.json().get("db_ok"):
                print(f"[{now_clt()}] health OK")
                return True
        except Exception as e:
            print(f"[{now_clt()}] health: {e}")
        time.sleep(HEALTH_POLL_SECONDS)
    print(f"[{now_clt()}] health timeout -> continue anyway")
    return False


def post_batch(session: requests.Session, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{BASE_URL}/ingest"
    for attempt in range(1, INGEST_RETRIES + 1):
        try:
            r = session.post(url, json={"items": batch}, timeout=INGEST_TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = min(60, 2 ** attempt) + random.uniform(0, 0.6)
            print(f"[{now_clt()}] attempt {attempt} failed: {e} | sleep {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"Ingest failed after {INGEST_RETRIES} retries")


def ingest(session: requests.Session, items: List[Dict[str, Any]], source: str) -> None:
    if not items:
        print(f"[{now_clt()}] {source}: nothing to ingest")
        return
    total_ins = total_upd = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        res = post_batch(session, batch)
        total_ins += int(res.get("inserted", 0))
        total_upd += int(res.get("updated", 0))
        print(f"[{now_clt()}] {source} batch: inserted={res.get('inserted')} updated={res.get('updated')}")
        time.sleep(0.25)
    print(f"[{now_clt()}] {source} DONE: inserted={total_ins} updated={total_upd}")


def run() -> None:
    print(f"[{now_clt()}] Worker start -> {BASE_URL}")
    session = requests.Session()
    wait_for_health(session)

    # SEA
    print(f"[{now_clt()}] Fetching SEA...")
    items = fetch_sea(days_back=SEA_DAYS_BACK, limit=SEA_LIMIT)
    print(f"[{now_clt()}] SEA: {len(items)} items")
    ingest(session, items, "SEA")

    # ChileCompra
    print(f"[{now_clt()}] Fetching ChileCompra...")
    items = fetch_chilebcompra(days_back=CHILEBCOMPRA_DAYS_BACK, limit=CHILEBCOMPRA_LIMIT)
    print(f"[{now_clt()}] ChileCompra: {len(items)} items")
    ingest(session, items, "ChileCompra")

    # COCHILCO
    print(f"[{now_clt()}] Fetching COCHILCO...")
    items = fetch_cochilco(limit=300)
    print(f"[{now_clt()}] COCHILCO: {len(items)} items")
    ingest(session, items, "COCHILCO")

    # MOP
    print(f"[{now_clt()}] Fetching MOP...")
    items = fetch_mop(limit=200)
    print(f"[{now_clt()}] MOP: {len(items)} items")
    ingest(session, items, "MOP")

    # RSS Minería
    print(f"[{now_clt()}] Fetching RSS Minería...")
    items = fetch_rss_mineria(limit=300)
    print(f"[{now_clt()}] RSS: {len(items)} items")
    ingest(session, items, "RSS")

    print(f"[{now_clt()}] Worker finished")


if __name__ == "__main__":
    run()
