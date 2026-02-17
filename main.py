import requests

SEA_URL = "https://arcgisv11.sea.gob.cl/server/rest/services/WEBServices/ProyectosSEIA/MapServer/1/query"

def fetch_sea(limit: int = 10):
    params = {
        "f": "json",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": limit,
    }
    r = requests.get(SEA_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    items = []
    for feat in data.get("features", []):
        a = feat.get("attributes", {}) or {}
        title = a.get("NOMBRE_PROYECTO") or "Proyecto SEIA"
        code = a.get("ID_PROYECTO") or ""
        url = f"https://www.sea.gob.cl/buscador-de-proyectos?texto={code}" if code else "https://www.sea.gob.cl/buscador-de-proyectos"
        items.append((title, url))
    return items

def main():
    print("🔎 StratMap Chile – Test SEA\n")
    for i, (title, url) in enumerate(fetch_sea(10), 1):
        print(f"{i}. {title}\n   {url}\n")

if __name__ == "__main__":
    main()
