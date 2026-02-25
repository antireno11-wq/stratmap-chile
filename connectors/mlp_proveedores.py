"""
connectors/mlp_proveedores.py
Scraper del Portal de Proveedores Locales de Minera Los Pelambres.
https://web.proveedoreslocalesmlp.cl/
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://web.proveedoreslocalesmlp.cl"
HEADERS = {"User-Agent": "StratmapBot/1.0 (+https://stratmap.cl)"}


def score_item(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    score = 45  # base — portal especializado minería local

    high_kw = ["licitación", "licitacion", "cotización", "cotizacion",
                "contrato", "concurso", "adjudicación", "llamado", "oferta"]
    med_kw  = ["obras", "servicio", "suministro", "transporte", "mantención",
                "proveedor", "empresa colaboradora", "requerimiento"]

    for kw in high_kw:
        if kw in text:
            score += 15
            break
    for kw in med_kw:
        if kw in text:
            score += 8
            break
    return min(score, 75)


def fetch_mlp_proveedores(limit: int = 100) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # Sección noticias — buscar tarjetas/artículos
        news_section = soup.find(id="noticias") or soup.find("section", string=re.compile("Noticias", re.I))
        containers = []

        if news_section:
            containers = news_section.find_all(["article", "div"], class_=re.compile(r"card|news|noticia|item", re.I))

        # Fallback — buscar "Leer más" links con títulos
        if not containers:
            links = soup.find_all("a", string=re.compile("Leer más|Leer Mas|ver más", re.I))
            for link in links:
                parent = link.find_parent(["article", "div", "section"])
                if parent and parent not in containers:
                    containers.append(parent)

        # Si tampoco hay — parsear texto directo buscando bloques con título + descripción
        if not containers:
            # Buscar h2/h3 seguidos de párrafo en el área de noticias
            for heading in soup.find_all(["h2", "h3", "h4"]):
                text = heading.get_text(strip=True)
                if len(text) > 20:
                    p = heading.find_next_sibling("p")
                    description = p.get_text(strip=True) if p else ""
                    link_tag = heading.find("a") or heading.find_next("a")
                    url = BASE_URL
                    if link_tag and link_tag.get("href"):
                        href = link_tag["href"]
                        url = href if href.startswith("http") else BASE_URL + href

                    if text and len(text) > 15:
                        score = score_item(text, description)
                        items.append({
                            "source": "MLP Proveedores",
                            "title": text[:400],
                            "url": url,
                            "company": "Minera Los Pelambres",
                            "industry": "Minería",
                            "region": "Coquimbo",
                            "phase": "Noticia",
                            "score": score,
                            "entry": description[:500] if description else None,
                            "raw": {"source_url": BASE_URL, "tipo": "noticia_mlp"}
                        })

        for container in containers[:limit]:
            title_tag = container.find(["h1","h2","h3","h4","strong"])
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or len(title) < 10:
                continue

            p_tags = container.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in p_tags[:2])

            link_tag = container.find("a")
            url = BASE_URL
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                url = href if href.startswith("http") else BASE_URL + href

            score = score_item(title, description)
            items.append({
                "source": "MLP Proveedores",
                "title": title[:400],
                "url": url,
                "company": "Minera Los Pelambres",
                "industry": "Minería",
                "region": "Coquimbo",
                "phase": "Noticia",
                "score": score,
                "entry": description[:500] if description else None,
                "raw": {"source_url": BASE_URL, "tipo": "noticia_mlp"}
            })

        # Deduplicar por URL
        seen = set()
        unique = []
        for item in items:
            if item["url"] not in seen:
                seen.add(item["url"])
                unique.append(item)

        print(f"[mlp_proveedores] {len(unique)} items")
        return unique[:limit]

    except Exception as e:
        print(f"[mlp_proveedores] Error: {e}")
        return []


if __name__ == "__main__":
    items = fetch_mlp_proveedores()
    for i in items[:5]:
        print(f"  [{i['score']}] {i['title'][:70]}")
