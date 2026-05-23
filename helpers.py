"""Helpers usados tanto por el scheduler (lifespan) como por endpoints admin."""
import logging
import traceback

import db
from mining_filters import is_mining_relevant, is_chile_relevant

logger = logging.getLogger("stratmap.helpers")


def _chile_filter(items: list) -> list:
    """Filtra items aplicando DOS condiciones:
    1. Debe ser relevante minería (empresa/sustancia/operación/regulatorio).
    2. Debe ser de Chile (o no mencionar otro país).

    Bloomberg Línea, AméricaEconomía y Diario Financiero a veces sueltan
    noticias regionales de toda LATAM o cosas no-mineras (aerolíneas, retail,
    etc.) — esto las recorta antes de tocar la DB."""
    out = []
    for it in items:
        title = it.get("title", "") or ""
        source = it.get("source", "") or ""
        desc = ""
        raw = it.get("raw")
        if isinstance(raw, dict):
            desc = raw.get("description", "") or ""
        if not is_mining_relevant(title, desc, source):
            continue
        if not is_chile_relevant(title, desc):
            continue
        out.append(it)
    return out


def run_rss_ingest():
    """Corre ingesta RSS combinada (genéricos + minería) y retorna un resumen.

    Llamado por worker (cada 6h) y por POST /admin/run-rss (manual).
    """
    summary = {"ok": True, "feeds": {}}
    total_inserted = 0

    # 1. Feeds mineros (rss_mineria): Portal Minero, Mineria Chilena, COCHILCO,
    #    Diario Financiero, CChC, Revista EI, Electricidad, etc. Filtramos por
    #    relevancia chilena (saca noticias regionales de Brasil/Perú/Ecuador
    #    que entran via Bloomberg Línea + AméricaEconomía).
    try:
        from connectors.rss_mineria import fetch_rss_mineria
        raw = fetch_rss_mineria(limit=300)
        items = _chile_filter(raw)
        if items:
            db.upsert_opportunities(items)
        summary["feeds"]["rss_mineria"] = {"total": len(raw), "chile_only": len(items)}
        total_inserted += len(items)
    except Exception as e:
        logger.warning("rss_mineria failed", extra={"err": str(e)})
        summary["feeds"]["rss_mineria_error"] = str(e)

    # 2. Feeds genéricos (rss): BioBioChile, Emol, Radio U.de Chile, La Tercera.
    #    Filtramos via mining_filters.is_mining_relevant() — mejor cobertura que
    #    keyword-list inline (80+ términos, lista negativa para ruido).
    try:
        from connectors.rss import fetch_rss
        items = fetch_rss(limit=200)
        filtered = [
            i for i in items
            if is_mining_relevant(
                i.get("title", ""),
                (i.get("raw") or {}).get("description", ""),
                i.get("source", ""),
            )
        ]
        if filtered:
            db.upsert_opportunities(filtered)
        summary["feeds"]["rss_generico"] = {"total": len(items), "relevantes": len(filtered)}
        total_inserted += len(filtered)
    except Exception as e:
        logger.warning("rss generico failed", extra={"err": str(e)})
        summary["feeds"]["rss_generico_error"] = str(e)

    # 3. Scrapers minería-específicos que antes solo corrían en sea_ingest.main()
    #    (cada 24h). Ahora corren también cada 6h para mejor refresh de noticias.
    specific_scrapers = [
        ("infomineria",   "connectors.infomineria",   "fetch_infomineria",   100),
        ("mundo_mineria", "connectors.mundo_mineria", "fetch_mundo_mineria", 100),
        ("lithium_chile", "connectors.lithium_chile", "fetch_lithium_chile",  30),
    ]
    for name, mod_path, fn_name, lim in specific_scrapers:
        try:
            mod = __import__(mod_path, fromlist=[fn_name])
            raw_items = getattr(mod, fn_name)(limit=lim)
            items = _chile_filter(raw_items)
            if items:
                db.upsert_opportunities(items)
            summary["feeds"][name] = {"total": len(raw_items), "chile_only": len(items)}
            total_inserted += len(items)
        except Exception as e:
            logger.warning(f"{name} failed", extra={"err": str(e)})
            summary["feeds"][f"{name}_error"] = str(e)

    # Pasada de deduplicación post-ingest. Idempotente, marca extras como
    # is_duplicate=TRUE para que las queries de listado los oculten.
    try:
        dup_count = db.mark_duplicates()
        summary["duplicates_marked"] = dup_count
    except Exception as e:
        logger.warning("mark_duplicates failed", extra={"err": str(e)})

    summary["total_inserted"] = total_inserted
    return summary
