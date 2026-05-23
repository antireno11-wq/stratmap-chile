"""Endpoints /admin/* — scrapers, ops manuales y debug.

Todas las rutas requieren admin (gated por router-level dependency).
"""
import json as _json
import threading
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query

import db
from db import expire_stale_opportunities, recalc_all_scores
from deps import require_admin
from helpers import run_rss_ingest
from routers.mandantes import reset_faenas_cache

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/admin/stats")
def admin_stats():
    """Métricas operacionales para monitoreo: actividad por fuente, usuarios
    activos, llamadas IA persistidas en el último mes."""
    out = {}
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Oportunidades por fuente: total + activos + último scrape
            cur.execute("""
                SELECT source,
                       COUNT(*)                                AS total,
                       COUNT(*) FILTER (WHERE is_active)       AS active,
                       MAX(updated_at)                         AS last_scrape
                FROM opportunities
                WHERE source IS NOT NULL
                GROUP BY source
                ORDER BY total DESC
            """)
            sources = []
            for r in cur.fetchall():
                sources.append({
                    "source": r["source"],
                    "total": r["total"],
                    "active": r["active"],
                    "last_scrape": r["last_scrape"].isoformat() if r.get("last_scrape") else None,
                })
            out["sources"] = sources

            # Usuarios activos (login en los últimos 30 días)
            cur.execute("""
                SELECT
                    COUNT(*)                                                AS total,
                    COUNT(*) FILTER (WHERE last_login > NOW() - INTERVAL '30 days') AS active_30d,
                    COUNT(*) FILTER (WHERE last_login > NOW() - INTERVAL '7 days')  AS active_7d
                FROM users
            """)
            row = cur.fetchone() or {}
            out["users"] = {
                "total": row.get("total", 0),
                "active_30d": row.get("active_30d", 0),
                "active_7d": row.get("active_7d", 0),
            }

            # Llamadas IA persistidas (proxy de uso de Anthropic API).
            # Las llamadas a /mandantes/summary se cachean en memoria sin persistir,
            # así que esto subestima un poco — pero es lo medible sin instrumentar todo.
            ai_calls = {}
            try:
                cur.execute("""
                    SELECT COUNT(*) AS n FROM ai_opportunity_fits
                    WHERE scored_at > NOW() - INTERVAL '30 days'
                """)
                ai_calls["ai_fits_30d"] = (cur.fetchone() or {}).get("n", 0)
            except Exception as e:
                ai_calls["ai_fits_30d_error"] = str(e)
            try:
                cur.execute("""
                    SELECT COUNT(*) AS n FROM mandante_heat
                    WHERE scored_at > NOW() - INTERVAL '30 days'
                """)
                ai_calls["mandante_heat_30d"] = (cur.fetchone() or {}).get("n", 0)
            except Exception as e:
                ai_calls["mandante_heat_30d_error"] = str(e)
            out["ai_calls"] = ai_calls

    return out


@router.post("/admin/refresh-faenas")
def refresh_faenas():
    """Fuerza recarga del cache de faenas mineras."""
    reset_faenas_cache()
    return {"ok": True, "msg": "Cache de faenas limpiado, próxima llamada a /faenas recargará"}


@router.get("/admin/debug-noticias")
def debug_noticias(company: str = "Codelco"):
    """Debug: diagnostico completo de noticias en BD."""
    NEWS_LIST = [
        'Lithium Chile','Portal Minero','Revista EI','Mineria Chilena',
        'Diario Financiero','COCHILCO Noticias','InfoMineria','Mundo Mineria',
        'Radio U. de Chile','Radio Universidad de Chile','BioBioChile','RSS',
    ]
    STOPWORDS = {'spa','ltda','de','del','la','el','los','las','y','en','por','para','con'}
    words = [w.lower() for w in company.replace('.',' ').split()
             if len(w) > 3 and w.lower() not in STOPWORDS]
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT source, COUNT(*) as n FROM opportunities GROUP BY source ORDER BY n DESC LIMIT 40")
                all_sources = [{"source": r["source"], "n": r["n"]} for r in cur.fetchall()]

                cur.execute("SELECT COUNT(*) as n FROM opportunities WHERE source = ANY(%s)", (NEWS_LIST,))
                row = cur.fetchone()
                total_news = int(row["n"]) if row else 0

                cur.execute("""
                    SELECT title, source, COALESCE(company,'-') as company,
                           CAST(published_at AS TEXT) as published_at
                    FROM opportunities WHERE source = ANY(%s)
                    ORDER BY published_at DESC NULLS LAST LIMIT 5
                """, (NEWS_LIST,))
                latest_news = [dict(r) for r in cur.fetchall()]

                kw_hits = {}
                for kw in words[:6]:
                    cur.execute("SELECT COUNT(*) as n FROM opportunities WHERE source = ANY(%s) AND LOWER(title) LIKE %s",
                                (NEWS_LIST, f"%{kw}%"))
                    row2 = cur.fetchone()
                    kw_hits[kw] = int(row2["n"]) if row2 else 0

                cur.execute("""
                    SELECT title, source, CAST(published_at AS TEXT) as published_at
                    FROM opportunities
                    WHERE LOWER(TRIM(company)) = LOWER(TRIM(%s)) AND source = ANY(%s)
                    ORDER BY published_at DESC NULLS LAST LIMIT 5
                """, (company, NEWS_LIST))
                by_exact = [dict(r) for r in cur.fetchall()]

                query_result = []
                if words:
                    kw_parts = [f"LOWER(title) LIKE '%%{w}%%'" for w in words[:4]]
                    kw_cond = " OR ".join(kw_parts)
                    cur.execute(f"""
                        SELECT title, source, COALESCE(company,'-') as company,
                               CAST(published_at AS TEXT) as published_at
                        FROM opportunities
                        WHERE source = ANY(%s)
                          AND (LOWER(TRIM(company)) = LOWER(TRIM(%s)) OR ({kw_cond}))
                        ORDER BY published_at DESC NULLS LAST LIMIT 10
                    """, (NEWS_LIST, company))
                    query_result = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "company_buscada": company,
            "keywords_extraidas": words,
            "total_noticias_en_bd": total_news,
            "todos_los_sources": all_sources,
            "ultimas_5_noticias": latest_news,
            "noticias_exactas_por_company": by_exact,
            "hits_por_keyword": kw_hits,
            "resultado_query_final": query_result,
            "diagnostico": "OK" if query_result else ("Sin noticias en BD - correr worker" if total_news == 0 else "Noticias en BD pero no matchean"),
        }
    except Exception as e:
        import traceback as tb
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[:2000]}

@router.post("/admin/run-bhp-careers")
def run_bhp_careers():
    """Scraping de empleos BHP Chile — inline, sin módulo externo."""
    import traceback as tb, requests as _req, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    SEARCH_URL = (
        "https://careers.bhp.com/search/"
        "?createNewAlert=false&q=&optionsFacetsDD_location=Chile"
    )
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    }
    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","mecanico","instrumentista"],
        "Ingeniería":    ["engineer","ingeniero","specialist","especialista","lead","principal","tecnico"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning"],
        "TI / Datos":    ["digital","data","ai","autonomous","autonomia","ahs","software"],
        "RRHH":          ["training","capacit","rrhh","people","talento"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud"],
        "Proyectos":     ["project","proyecto","inversiones","transactions"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws):
                return area
        return "Otros"

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'BHP Careers'")
                deleted = cur.rowcount
            conn.commit()

        # Scrape
        resp = _req.get(SEARCH_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        jobs = []
        seen = set()
        for a in soup.select("table a[href*='/job/']"):
            raw_title = a.get_text(strip=True)
            if not raw_title or len(raw_title) < 5: continue
            href = a.get("href","")
            url = ("https://careers.bhp.com" + href) if href.startswith("/") else href
            if url in seen: continue
            seen.add(url)
            parts = raw_title.split("|")
            title   = parts[0].strip()
            empresa = parts[1].strip() if len(parts) > 1 else "BHP"
            jobs.append({"title": title, "empresa": empresa, "area": classify(title), "url": url})

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en BHP Chile", "deleted": deleted}

        # Normalizar nombres de empresa BHP → entidad canónica
        BHP_NORMALIZE = {
            "bhp":                    "BHP CHILE INC",
            "bhp chile":              "BHP CHILE INC",
            "bhp chile inc":          "BHP CHILE INC",
            "minera escondida":       "BHP CHILE INC",
            "escondida":              "BHP CHILE INC",
            "minera spence":          "BHP CHILE INC",
            "spence":                 "BHP CHILE INC",
            "cas plazo fijo":         "BHP CHILE INC",
            "bhp billiton":           "BHP CHILE INC",
        }
        for j in jobs:
            key = j["empresa"].lower().strip()
            j["empresa"] = BHP_NORMALIZE.get(key, j["empresa"])

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs: by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total = len(emp_jobs)
            areas = {}
            for j in emp_jobs: areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ","-")
            opps.append({
                "source": "BHP Careers",
                "title": f"Empleos BHP Chile — {empresa} ({total} cargos)",
                "company": empresa,
                "industry": "Minería",
                "phase": "Contratación activa",
                "region": "Chile",
                "score": 0,
                "url": f"https://careers.bhp.com/chile/{slug}",
                "published_at": now.isoformat(),
                "entry": f"{empresa}: {total} cargos disponibles en Chile.\n\n{cargo_list}",
                "jobs_count": total,
                "signal_score": min(total * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total, "fuente": "BHP Careers"}, ensure_ascii=False),
                "raw": {"by_area": areas, "empleos": [j["url"] for j in emp_jobs]},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": list(by_emp.keys()),
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}

@router.post("/admin/run-amsa-careers")
def run_amsa_careers():
    """Scraping de empleos Antofagasta Minerals (AMSA) — Pelambres, Centinela, Zaldívar, AMSA."""
    import traceback as tb, requests as _req, re as _re, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    BASE_URL = "https://career8.successfactors.com"
    LIST_URL = BASE_URL + "/career?company=AMSAP&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH"
    HEADERS  = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    }

    # Normalizar empresa AMSA a nombre canónico en Stratmap
    AMSA_COMPANIES = {
        "pelambres":   "MINERA LOS PELAMBRES",
        "centinela":   "MINERA CENTINELA",
        "zaldivar":    "COMPANIA MINERA ZALDIVAR",
        "zaldívar":    "COMPANIA MINERA ZALDIVAR",
        "amsa":        "ANTOFAGASTA MINERALS",
        "corporativo": "ANTOFAGASTA MINERALS",
    }

    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion","planta"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","eléctrico","mecanico","instrumentista"],
        "Ingeniería":    ["engineer","ingeniero","ingeniera","specialist","especialista","senior","tecnic"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning","gestor"],
        "TI / Datos":    ["digital","data","sistemas","software","ti ","tecnolog"],
        "RRHH":          ["training","capacit","rrhh","people","talento","personas"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador","superintendenta"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud","prevencion"],
        "Proyectos":     ["project","proyecto","inversiones","construccion","ejecucion"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws): return area
        return "Otros"

    def empresa_from_meta(meta):
        m = meta.lower()
        for key, name in AMSA_COMPANIES.items():
            if key in m: return name
        return "ANTOFAGASTA MINERALS"

    def get_page(page_no, session):
        params = {"company": "AMSAP", "career_ns": "job_listing_summary",
                  "navBarLevel": "JOB_SEARCH", "pageNo": page_no}
        r = session.get(BASE_URL + "/career", params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'AMSA Careers'")
                deleted = cur.rowcount
            conn.commit()

        session = _req.Session()
        jobs = []

        # Primera página — detectar total de páginas
        soup = get_page(1, session)
        pager = soup.get_text()
        # "Página 1 de 3" → extraer el último número
        m = _re.search(r'[Pp][áa]gina\s+\d+\s+de\s+(\d+)', pager)
        if not m:
            m = _re.search(r'Page\s+\d+\s+of\s+(\d+)', pager)
        total_pages = int(m.group(1)) if m else 1

        def parse_jobs(soup):
            # SuccessFactors muestra empleos como links dentro de tablas o divs
            # Estructura: <a href="/career?...jobId=XXXXX">Título del cargo</a>
            # Seguido de texto: "ID de solicitud de puesto: XXXXX - Publicado el DD/MM/YYYY - EMPRESA"
            seen_ids = set()
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if 'jobId' not in href and 'job_id' not in href and 'requisitionId' not in href:
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                job_url = (BASE_URL + href) if href.startswith('/') else href
                # Extraer ID del puesto para deduplicar
                id_m = _re.search(r'[jJ]ob[Ii]d=(\d+)|requisitionId=(\d+)', href)
                job_id = (id_m.group(1) or id_m.group(2)) if id_m else href[-8:]
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                # El texto del contenedor padre tiene la empresa y fecha
                container = a.parent
                for _ in range(4):  # subir hasta 4 niveles
                    if container and container.name in ('td', 'div', 'li', 'tr'):
                        break
                    container = container.parent if container else None
                meta = container.get_text(separator=' ', strip=True) if container else ''
                empresa = empresa_from_meta(meta)
                date_m = _re.search(r'(\d{2}/\d{2}/\d{4})', meta)
                fecha = date_m.group(1) if date_m else ''
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "job_id": job_id,
                    "fecha": fecha, "url": job_url,
                })

        parse_jobs(soup)
        for p in range(2, total_pages + 1):
            s = get_page(p, session)
            parse_jobs(s)

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en AMSA", "deleted": deleted}

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs: by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total = len(emp_jobs)
            areas = {}
            for j in emp_jobs: areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ", "-")
            opps.append({
                "source": "AMSA Careers",
                "title": f"Empleos AMSA — {empresa} ({total} cargos)",
                "company": empresa,
                "industry": "Minería",
                "phase": "Contratación activa",
                "region": "Chile",
                "score": 0,
                "url": f"https://career8.successfactors.com/amsa/{slug}",
                "published_at": now.isoformat(),
                "entry": f"{empresa}: {total} cargos disponibles.\n\n{cargo_list}",
                "jobs_count": total,
                "signal_score": min(total * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total, "fuente": "AMSA Careers"}, ensure_ascii=False),
                "raw": {"by_area": areas},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": {e: len(j) for e, j in by_emp.items()},
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}

@router.post("/admin/recalcular-scores")
def admin_recalcular_scores():
    """
    Recalcula scores de todos los proyectos usando el scoring engine de Stratmap.
    Aplica la función calc_score() a cada registro y actualiza la BD.
    """
    import traceback as tb
    try:
        result = recalc_all_scores()
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@router.post("/admin/run-lundin-careers")
def run_lundin_careers():
    """Scraping de empleos Lundin Mining Chile — Minera Candelaria (Tierra Amarilla)."""
    import traceback as tb, requests as _req, re as _re, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    BASE_URL  = "https://jobs.lundinmining.com"
    # Filtrar solo Chile — país CL
    SEARCH_URL = BASE_URL + "/search/?createNewAlert=false&q=&optionsFacetsDD_country=CL"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Mapeo de Business Unit → empresa canónica Stratmap
    LUNDIN_COMPANIES = {
        "candelaria":  "MINERA CANDELARIA",
        "lumina":      "SCM MINERA LUMINA COPPER CHILE",
        "lundin":      "MINERA CANDELARIA",
    }

    AREA_KW = {
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion","planta","minero"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","eléctrico","mecanico","instrumentista","mecánico"],
        "Ingeniería":    ["engineer","ingeniero","ingeniera","specialist","especialista","senior","tecnic","metalurgista"],
        "Geología":      ["geolog","geoscien","geotecnia","hidrogeol","exploracion","geologo"],
        "Finanzas":      ["finance","finanza","financiero","reporting","planning","gestor","contador"],
        "TI / Datos":    ["digital","data","sistemas","software","ti ","tecnolog","it "],
        "RRHH":          ["training","capacit","rrhh","people","talento","personas","recursos humanos"],
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador","superintendenta","lider","líder"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud","prevencion","prevención"],
        "Proyectos":     ["project","proyecto","inversiones","construccion","ejecucion","construcción"],
        "Supply Chain":  ["supply","cadena","logistic","logística","compras","abastecimiento","bodega"],
        "Procesamiento": ["procesamiento","processamento","metalurg","hidrometalurg","pirometalurg"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws): return area
        return "Otros"

    def empresa_from_bu(business_unit, location):
        bu = (business_unit or "").lower()
        loc = (location or "").lower()
        for key, name in LUNDIN_COMPANIES.items():
            if key in bu or key in loc: return name
        return "MINERA CANDELARIA"  # Default Chile = Candelaria

    try:
        # Borrar registros anteriores
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'Lundin Careers'")
                deleted = cur.rowcount
            conn.commit()

        session = _req.Session()
        jobs = []

        def parse_page(soup):
            # SuccessFactors: cada empleo es un <li> con un <a href="/job/...">
            for li in soup.select("ul.jobs-list li, #career-section li, li[class*='job']"):
                a = li.select_one("a[href*='/job/']")
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) < 4:
                    continue
                href = a.get("href", "")
                job_url = (BASE_URL + href) if href.startswith("/") else href

                # Extraer metadata del li
                text = li.get_text(separator=" ", strip=True)
                # Business Unit y location
                bu_m  = _re.search(r'Business Unit\s+(\S[^\n]+?)(?:\s{2,}|Department|Location|$)', text)
                loc_m = _re.search(r'Location\s+(\S[^\n]+?)(?:\s{2,}|Business|Department|$)', text)
                bu    = bu_m.group(1).strip() if bu_m else ""
                loc   = loc_m.group(1).strip() if loc_m else ""
                empresa = empresa_from_bu(bu, loc)
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "url": job_url,
                    "bu": bu, "loc": loc,
                })

        # Página 1
        r = session.get(SEARCH_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        parse_page(soup)

        # Detectar paginación
        pager_text = soup.get_text()
        m = _re.search(r'[Ss]howing\s+\d+\s+to\s+\d+\s+of\s+(\d+)', pager_text)
        total = int(m.group(1)) if m else len(jobs)
        per_page = 10  # SuccessFactors default
        total_pages = max(1, -(-total // per_page))  # ceil division

        for page in range(2, total_pages + 1):
            r2 = session.get(SEARCH_URL + f"&page={page}", headers=HEADERS, timeout=20)
            r2.raise_for_status()
            soup2 = BeautifulSoup(r2.text, "html.parser")
            parse_page(soup2)

        # Si parse falló (0 jobs), intentar selector alternativo
        if not jobs:
            # Fallback: buscar todos los links /job/ en la página
            for a in soup.find_all("a", href=_re.compile(r"/job/")):
                title = a.get_text(strip=True)
                if not title or len(title) < 4:
                    continue
                href = a.get("href", "")
                job_url = (BASE_URL + href) if href.startswith("/") else href
                # Extraer empresa de la URL o texto cercano
                container = a.parent
                for _ in range(5):
                    if container and container.name in ("li", "div", "tr", "article"):
                        break
                    container = container.parent if container else None
                meta = container.get_text(separator=" ", strip=True) if container else ""
                empresa = empresa_from_bu(meta, meta)
                jobs.append({
                    "title": title, "empresa": empresa,
                    "area": classify(title), "url": job_url,
                    "bu": "", "loc": "",
                })
            # Deduplicar por URL
            seen = set()
            unique = []
            for j in jobs:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    unique.append(j)
            jobs = unique

        if not jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en Lundin Mining Chile", "deleted": deleted}

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs:
            by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total_emp = len(emp_jobs)
            areas = {}
            for j in emp_jobs:
                areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in emp_jobs)
            slug = empresa.lower().replace(" ", "-").replace(".", "")
            opps.append({
                "source":      "Lundin Careers",
                "title":       f"Empleos Lundin Mining Chile — {empresa} ({total_emp} cargos)",
                "company":     empresa,
                "industry":    "Minería",
                "phase":       "Contratación activa",
                "region":      "Atacama",
                "score":       0,
                "url":         f"https://jobs.lundinmining.com/chile/{slug}",
                "published_at": now.isoformat(),
                "entry":       f"{empresa}: {total_emp} cargos disponibles.\n\n{cargo_list}",
                "jobs_count":  total_emp,
                "signal_score": min(total_emp * 3, 40),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total_emp, "fuente": "Lundin Careers"}, ensure_ascii=False),
                "raw":         {"by_area": areas, "empleos": [j["url"] for j in emp_jobs]},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok": True,
            "deleted_old": deleted,
            "jobs_encontrados": len(jobs),
            "empresas": {e: len(j) for e, j in by_emp.items()},
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@router.post("/admin/run-teck-careers")
def run_teck_careers():
    """Scraping de empleos Teck Chile — Carmen de Andacollo y Quebrada Blanca."""
    import traceback as tb, requests as _req, json as _json
    from datetime import datetime, timezone

    API_URL = "https://jobs.teck.com/services/recruiting/v1/jobs"
    BASE_URL = "https://jobs.teck.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://jobs.teck.com/search/?q=&locationsearch=Chile&searchResultView=LIST",
    }

    # Mapeo de ubicación → empresa canónica Stratmap
    # Pica, TA = Quebrada Blanca (Tarapacá); Andacollo, CO = Carmen de Andacollo (Coquimbo)
    LOCATION_MAP = {
        "pica":       "COMPANIA MINERA TECK QUEBRADA BLANCA",
        "tarapacá":   "COMPANIA MINERA TECK QUEBRADA BLANCA",
        "tarapaca":   "COMPANIA MINERA TECK QUEBRADA BLANCA",
        "andacollo":  "COMPANIA MINERA CARMEN DE ANDACOLLO",
        "coquimbo":   "COMPANIA MINERA CARMEN DE ANDACOLLO",
        "santiago":   "TECK CHILE",
    }

    # Mapeo categoría SuccessFactors → área Stratmap
    CAT_MAP = {
        "mantenimiento":          "Mantenimiento",
        "maintenance":            "Mantenimiento",
        "ingeniería":             "Ingeniería",
        "ingenieria":             "Ingeniería",
        "engineering":            "Ingeniería",
        "operaciones mina":       "Operaciones",
        "mine operations":        "Operaciones",
        "geociencia":             "Geología",
        "geoscience":             "Geología",
        "geología":               "Geología",
        "salud":                  "HSE",
        "health":                 "HSE",
        "safety":                 "HSE",
        "ambiente":               "HSE",
        "finanzas":               "Finanzas",
        "finance":                "Finanzas",
        "tecnología":             "TI / Datos",
        "technology":             "TI / Datos",
        "recursos humanos":       "RRHH",
        "human resources":        "RRHH",
        "supply chain":           "Supply Chain",
        "abastecimiento":         "Supply Chain",
        "proyectos":              "Proyectos",
        "projects":               "Proyectos",
        "administración":         "Administración",
        "business administration":"Administración",
    }

    def empresa_from_location(location_str):
        loc = (location_str or "").lower()
        for key, name in LOCATION_MAP.items():
            if key in loc: return name
        return "TECK CHILE"

    def area_from_cat(cat_str):
        c = (cat_str or "").lower()
        for key, area in CAT_MAP.items():
            if key in c: return area
        return "Otros"

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'Teck Careers'")
                deleted = cur.rowcount
            conn.commit()

        # POST a la API interna de SuccessFactors/Teck — filtro Chile, pageSize 200
        payload = {
            "keyword": "",
            "location": "Chile",
            "locale": "es_ES",
            "pageNo": 1,
            "pageSize": 200,
        }
        r = _req.post(API_URL, headers=HEADERS, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()

        raw_jobs = data.get("jobSearchResult", [])
        total_api = data.get("totalJobs", 0)

        if not raw_jobs:
            return {"ok": True, "msg": "Sin empleos encontrados en Teck Chile", "deleted": deleted, "total_api": total_api}

        # Parsear cada job
        jobs = []
        for item in raw_jobs:
            resp = item.get("response", {})
            title    = resp.get("unifiedStandardTitle", "")
            if not title: continue
            job_id   = resp.get("id", "")
            url_title = resp.get("unifiedUrlTitle", resp.get("urlTitle", ""))
            location  = (resp.get("jobLocationShort") or [""])[0].strip().rstrip(",").strip()
            cat       = (resp.get("filter6") or [""])[0]
            empresa   = empresa_from_location(location)
            area      = area_from_cat(cat)
            # Construir URL del empleo
            loc_slug = location.split(",")[0].strip().replace(" ", "-") if location else "Chile"
            job_url  = f"{BASE_URL}/job/{loc_slug}-{url_title}-/{job_id}/" if job_id else BASE_URL + "/search/?q=&locationsearch=Chile"
            jobs.append({
                "title":   title,
                "empresa": empresa,
                "area":    area,
                "location": location,
                "url":     job_url,
                "id":      job_id,
            })

        # Agrupar por empresa
        from collections import defaultdict
        by_emp = defaultdict(list)
        for j in jobs: by_emp[j["empresa"]].append(j)

        now = datetime.now(timezone.utc)
        opps = []
        for empresa, emp_jobs in by_emp.items():
            total_emp = len(emp_jobs)
            areas = {}
            for j in emp_jobs:
                areas[j["area"]] = areas.get(j["area"], 0) + 1
            cargo_list = "\n".join(f"• {j['title']} ({j['area']}) — {j['location']}" for j in emp_jobs)
            slug = empresa.lower().replace(" ", "-").replace(".", "")
            region = "Tarapacá" if "quebrada" in empresa.lower() else "Coquimbo" if "andacollo" in empresa.lower() else "Chile"
            opps.append({
                "source":       "Teck Careers",
                "title":        f"Empleos Teck Chile — {empresa} ({total_emp} cargos)",
                "company":      empresa,
                "industry":     "Minería",
                "phase":        "Contratación activa",
                "region":       region,
                "score":        0,
                "url":          f"https://jobs.teck.com/search/?q=&locationsearch=Chile&searchResultView=LIST",
                "published_at": now.isoformat(),
                "entry":        f"{empresa}: {total_emp} cargos disponibles en Chile.\n\n{cargo_list}",
                "jobs_count":   total_emp,
                "signal_score": min(total_emp * 3, 45),
                "last_signal_at": now.isoformat(),
                "signal_detail": _json.dumps({"by_area": areas, "total": total_emp, "fuente": "Teck Careers"}, ensure_ascii=False),
                "raw":          {"by_area": areas, "empleos": [{"title": j["title"], "url": j["url"]} for j in emp_jobs]},
            })

        inserted, updated = db.upsert_opportunities(opps)
        return {
            "ok":           True,
            "deleted_old":  deleted,
            "total_api":    total_api,
            "jobs_encontrados": len(jobs),
            "empresas":     {e: len(j) for e, j in by_emp.items()},
            "inserted":     inserted,
            "updated":      updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@router.post("/admin/run-collahuasi-careers")
def run_collahuasi_careers():
    """Scraping de empleos Minera Collahuasi — sitio web propio."""
    import traceback as tb, requests as _req, re as _re, json as _json
    from bs4 import BeautifulSoup
    from datetime import datetime, timezone

    BASE_URL   = "https://www.collahuasi.cl"
    OFERTAS_URL = BASE_URL + "/trabaja-con-nosotros/ofertas-laborales/"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    }

    AREA_KW = {
        "Supervisión":   ["supervisor","superintendente","gerente","jefe","coordinador","administrador","lider","líder"],
        "Operaciones":   ["operador","operadora","mina","produccion","extraccion","perforación","tronadura","carguío"],
        "Mantenimiento": ["mantenedor","mantenci","electrico","eléctrico","mecanico","instrumentista","mecánico"],
        "Ingeniería":    ["ingeniero","ingeniera","engineer","specialist","especialista","senior","técnico","tecnico","metalurgista","geólogo"],
        "Geología":      ["geolog","geotecnia","hidrogeol","exploracion","minería"],
        "RRHH":          ["rrhh","people","talento","personas","recursos humanos","aprendiz","profesional en entrenamiento"],
        "HSE":           ["seguridad","safety","ambiente","hse","salud","prevencion","prevención"],
        "Finanzas":      ["finanza","financiero","administrador","contab","gestor"],
        "Supply Chain":  ["abastecimiento","compras","logística","bodega","supply"],
    }

    def classify(title):
        t = title.lower()
        for area, kws in AREA_KW.items():
            if any(k in t for k in kws): return area
        return "Otros"

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM opportunities WHERE source = 'Collahuasi Careers'")
                deleted = cur.rowcount
            conn.commit()

        r = _req.get(OFERTAS_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        jobs = []
        seen = set()

        # Las ofertas están como <a href="/oferta/nombre-cargo/">
        for a in soup.find_all("a", href=_re.compile(r"/oferta/")):
            href = a.get("href", "")
            if not href: continue
            url = (BASE_URL + href) if href.startswith("/") else href
            if url in seen: continue
            seen.add(url)

            # El título está en el texto del link o en un h2/h3 cercano
            title = ""
            heading = a.find(["h2", "h3", "h4", "strong", "span"])
            if heading:
                title = heading.get_text(strip=True)
            if not title:
                title = a.get_text(strip=True).replace("VER MÁS", "").strip()
            if not title or len(title) < 4:
                continue

            jobs.append({
                "title": title,
                "url":   url,
                "area":  classify(title),
            })

        if not jobs:
            return {"ok": True, "msg": "Sin ofertas encontradas en Collahuasi", "deleted": deleted}

        now = datetime.now(timezone.utc)
        total = len(jobs)
        areas = {}
        for j in jobs:
            areas[j["area"]] = areas.get(j["area"], 0) + 1

        cargo_list = "\n".join(f"• {j['title']} ({j['area']})" for j in jobs)

        opp = {
            "source":       "Collahuasi Careers",
            "title":        f"Empleos Collahuasi — {total} cargos disponibles",
            "company":      "COMPANIA MINERA DONA INES DE COLLAHUASI",
            "industry":     "Minería",
            "phase":        "Contratación activa",
            "region":       "Tarapacá",
            "score":        0,
            "url":          OFERTAS_URL,
            "published_at": now.isoformat(),
            "entry":        f"Collahuasi: {total} cargos disponibles.\n\n{cargo_list}",
            "jobs_count":   total,
            "signal_score": min(total * 4, 45),
            "last_signal_at": now.isoformat(),
            "signal_detail": _json.dumps({"by_area": areas, "total": total, "fuente": "Collahuasi Careers",
                                          "ofertas": [j["title"] for j in jobs]}, ensure_ascii=False),
            "raw": {"by_area": areas, "empleos": [{"title": j["title"], "url": j["url"]} for j in jobs]},
        }

        inserted, updated = db.upsert_opportunities([opp])
        return {
            "ok":           True,
            "deleted_old":  deleted,
            "jobs_encontrados": total,
            "cargos":       [j["title"] for j in jobs],
            "areas":        areas,
            "inserted":     inserted,
            "updated":      updated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": tb.format_exc()[-2000:]}


@router.post("/admin/run-mandante-scorer")
def run_mandante_scorer():
    """Dispara scoring de temperatura de mandantes con IA."""
    import threading
    def _run():
        try:
            import mandante_scorer
            db.init_ai_db()
            result = mandante_scorer.run()
            print(f"[admin] Mandante scorer: {result}")
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring de temperatura iniciado en background"}

@router.post("/admin/run-ai-scoring")
def run_ai_scoring_all():
    """Corre scoring IA para todos los perfiles con onboarding completo."""
    import threading
    def _run():
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT user_id FROM service_profiles
                        WHERE onboarding_done = TRUE AND services IS NOT NULL AND services != '[]'
                    """)
                    user_ids = [r["user_id"] for r in cur.fetchall()]
            print(f"[admin-ai] user_ids a procesar: {user_ids}")
            import ai_matcher
            for uid in user_ids:
                print(f"[admin-ai] Procesando user_id={uid}...")
                ai_matcher.run(user_id=uid, limit=500)
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Scoring IA masivo iniciado"}


@router.post("/admin/run-demand-intel")
def run_demand_intel(
    batch_size: int = Query(default=30, ge=5, le=100),
    max_batches: int = Query(default=10, ge=1, le=50),
    force: bool = Query(default=False),
    source: Optional[str] = Query(default=None),
):
    """Analiza proyectos mineros y genera la lista de servicios necesarios con IA."""
    try:
        import demand_intel
        result = demand_intel.run(
            batch_size=batch_size,
            max_batches=max_batches,
            force_reanalyze=force,
            source_filter=source,
        )
        return {"ok": True, **result}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}


@router.post("/admin/run-ai-scorer")
def run_ai_scorer(
    score_min: int = Query(default=45, ge=0, le=99),
    score_max: int = Query(default=65, ge=0, le=99),
    batch_size: int = Query(default=20, ge=5, le=50),
    max_batches: int = Query(default=5, ge=1, le=20),
):
    """
    Corre AI scoring inteligente para proyectos en zona gris.
    Claude evalúa proyectos con score entre score_min y score_max
    y ajusta ±10 puntos según contexto que las reglas no capturan.
    """
    import threading
    result_container = {}

    def _run():
        try:
            import ai_scorer
            result = ai_scorer.run(
                score_min=score_min,
                score_max=score_max,
                batch_size=batch_size,
                max_batches=max_batches,
            )
            result_container.update(result)
            print(f"[ai-scorer] {result}")
        except Exception as e:
            import traceback
            result_container.update({"ok": False, "error": str(e)})
            traceback.print_exc()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)  # esperar hasta 2 min

    if result_container:
        return result_container
    return {"ok": True, "msg": "AI scorer corriendo en background"}


@router.post("/admin/mark-onboarding-done")
def mark_onboarding_done():
    """Marca todos los perfiles existentes con servicios como onboarding_done=true."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE service_profiles
                    SET onboarding_done = TRUE
                    WHERE services != '[]' AND services IS NOT NULL
                """)
                updated = cur.rowcount
            conn.commit()
        return {"updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/sources-count")
def sources_count():
    """Muestra cuántos registros hay por source — útil para diagnóstico."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) as n,
                       ROUND(AVG(score)) as avg_score,
                       MIN(published_at::date) as oldest,
                       MAX(published_at::date) as newest
                FROM opportunities
                GROUP BY source ORDER BY n DESC;
            """)
            rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        for k in ['oldest','newest']:
            if r.get(k): r[k] = str(r[k])
    return {"sources": rows}

@router.delete("/admin/delete-source/{source_name}")
def delete_source(source_name: str):
    """Elimina todos los registros de una fuente específica."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM opportunities WHERE source = %(s)s", {"s": source_name})
            deleted = cur.rowcount
        conn.commit()
    return {"deleted": deleted, "source": source_name}

@router.post("/admin/run-rss")
def run_rss_manual():
    """Ingesta manual de noticias RSS (Portal Minero, Revista EI, InfoMinería, etc.)."""
    result = run_rss_ingest()
    return result


@router.post("/admin/run-expire-stale")
def run_expire_stale():
    """Marca como inactivas las licitaciones cuyo updated_at supera el TTL por fuente.
    Ejecuta el mismo proceso que corre automáticamente cada 24h en el scheduler.
    """
    result = expire_stale_opportunities()
    return {"ok": True, **result}


@router.post("/admin/run-sigex")
def run_sigex():
    """Ingesta manual del SIGEX Sernageomin (proyectos de exploración)."""
    import threading
    def _run():
        try:
            from connectors.sigex_sernageomin import fetch_sigex
            items = fetch_sigex(limit=5000)
            if not items:
                print("[sigex] Sin items retornados")
                return
            inserted, updated = db.upsert_opportunities(items)
            print(f"[sigex] insertados={inserted}, actualizados={updated}, total={len(items)}")
        except Exception as e:
            import traceback; traceback.print_exc()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "msg": "Ingesta SIGEX iniciada en background"}
