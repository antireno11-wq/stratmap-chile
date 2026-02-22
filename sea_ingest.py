import os
import sys
import time
import random
import subprocess
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
from connectors.scraper import fetch_scraper
from connectors.jobs_scraper import fetch_jobs_signals

import db

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


def install_playwright_browsers() -> None:
    """Instala Chromium si no está disponible."""
    chromium_path = os.path.expanduser(
        "~/.cache/ms-playwright/chromium_headless_shell-1208/"
        "chrome-headless-shell-linux64/chrome-headless-shell"
    )
    if not os.path.exists(chromium_path):
        print(f"[{now_clt()}] Instalando Chromium para Playwright...")
        try:
            result = subprocess.run(
                ["playwright", "install", "chromium", "--with-deps"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print(f"[{now_clt()}] Chromium instalado correctamente")
            else:
                print(f"[{now_clt()}] Error instalando Chromium: {result.stderr[:200]}")
        except Exception as e:
            print(f"[{now_clt()}] Error instalando Chromium: {e}")
    else:
        print(f"[{now_clt()}] Chromium ya disponible")


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


def run_jobs_signals() -> None:
    """Corre el scraper de empleos y actualiza signal_score en opportunities."""
    print(f"[{now_clt()}] Fetching Jobs Signals...")
    signals = fetch_jobs_signals()
    print(f"[{now_clt()}] Jobs: {len(signals)} empresas con actividad detectada")

    total_updated = 0
    for signal in signals:
        company_name = signal["company"]
        opportunities = db.get_opportunities_by_company(company_name)

        if not opportunities:
            print(f"[{now_clt()}] Jobs: '{company_name}' sin oportunidades en BD — skipping")
            continue

        for opp in opportunities:
            try:
                db.save_job_signal(opp["id"], signal)
                total_updated += 1
                print(f"[{now_clt()}] Jobs: '{company_name}' → opp_id={opp['id']} +{signal['score_impact']}pts ({signal['jobs_count']} empleos)")
            except Exception as e:
                print(f"[{now_clt()}] Jobs: error guardando señal para opp_id={opp['id']}: {e}")

    print(f"[{now_clt()}] Jobs DONE: {total_updated} oportunidades actualizadas")


def run() -> None:
    print(f"[{now_clt()}] Worker start -> {BASE_URL}")

    session = requests.Session()
    wait_for_health(session)

    # Instalar Chromium después del health check para no bloquear el startup
    install_playwright_browsers()

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

    # Scraper
    print(f"[{now_clt()}] Fetching Scraper...")
    items = fetch_scraper(limit=200)
    print(f"[{now_clt()}] Scraper: {len(items)} items")
    ingest(session, items, "Scraper")

    # RSS Minería
    print(f"[{now_clt()}] Fetching RSS Minería...")
    items = fetch_rss_mineria(limit=300)
    print(f"[{now_clt()}] RSS: {len(items)} items")
    ingest(session, items, "RSS")

    # Jobs Signals
    run_jobs_signals()

    print(f"[{now_clt()}] Worker finished")


if __name__ == "__main__":
    run()
