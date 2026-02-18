import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = os.getenv("BASE_URL")

SEA_TEST_URL = "https://www.sea.gob.cl/buscador-de-proyectos?texto=9030"


def now_clt():
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S CLT")


def fetch_sea():
    # Ejemplo simple
    return [{
        "source": "sea",
        "title": "Proyecto Modificación Faena Minera Caserones (SEIA 9030)",
        "url": SEA_TEST_URL,
        "company": "Caserones",
        "contractor": None,
        "industry": "Minería",
        "region": "Atacama",
        "phase": "Ambiental en curso",
        "score": 90,
        "entry": "continuidad / expansión",
        "raw": {}
    }]


def ingest(items):
    r = requests.post(f"{BASE_URL}/ingest", json={"items": items}, timeout=120)
    r.raise_for_status()
    return r.json()


def run_sea_ingest():
    print(f"[{now_clt()}] SEA ingest start")

    items = fetch_sea()
    print(f"[{now_clt()}] fetched {len(items)}")

    if not items:
        return {"ok": True, "fetched": 0}

    res = ingest(items)
    print(f"[{now_clt()}] ingest result: {res}")

    return {"ok": True, "fetched": len(items), "result": res}


if __name__ == "__main__":
    run_sea_ingest()
