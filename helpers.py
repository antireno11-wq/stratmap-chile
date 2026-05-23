"""Helpers usados tanto por el scheduler (lifespan) como por endpoints admin."""
import logging
import traceback

import db

logger = logging.getLogger("stratmap.helpers")


def run_rss_ingest():
    """Corre ingesta RSS combinada (genéricos + minería) y retorna un resumen.

    Llamado por worker (cada 6h) y por POST /admin/run-rss (manual).
    """
    summary = {"ok": True, "feeds": {}}
    total_inserted = 0

    # 1. Feeds mineros (rss_mineria): Portal Minero, Mineria Chilena, COCHILCO,
    #    Diario Financiero, CChC, Revista EI, Electricidad, etc.
    try:
        from connectors.rss_mineria import fetch_rss_mineria
        items = fetch_rss_mineria(limit=300)
        if items:
            db.upsert_opportunities(items)
        summary["feeds"]["rss_mineria"] = len(items)
        total_inserted += len(items)
    except Exception as e:
        logger.warning("rss_mineria failed", extra={"err": str(e)})
        summary["feeds"]["rss_mineria_error"] = str(e)

    # 2. Feeds genéricos (rss): BioBioChile, Emol, Radio U.de Chile, La Tercera.
    #    Filtramos por keywords mineras para no llenar la BD de ruido.
    try:
        from connectors.rss import fetch_rss
        items = fetch_rss(limit=200)
        MINING_KW = [
            'mina', 'minera', 'minería', 'cobre', 'litio', 'oro', 'plata', 'molibdeno',
            'codelco', 'bhp', 'antofagasta', 'escondida', 'teck', 'collahuasi', 'enami',
            'atacama', 'tarapacá', 'exploración', 'yacimiento', 'faena',
        ]
        filtered = [
            i for i in items
            if any(kw in (i.get('title', '') + i.get('raw', {}).get('description', '')).lower()
                   for kw in MINING_KW)
        ]
        if filtered:
            db.upsert_opportunities(filtered)
        summary["feeds"]["rss_generico"] = {"total": len(items), "relevantes": len(filtered)}
        total_inserted += len(filtered)
    except Exception as e:
        logger.warning("rss generico failed", extra={"err": str(e)})
        summary["feeds"]["rss_generico_error"] = str(e)

    summary["total_inserted"] = total_inserted
    return summary
