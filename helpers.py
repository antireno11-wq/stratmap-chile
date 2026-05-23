"""Helpers usados tanto por el scheduler (lifespan) como por endpoints admin."""
import traceback

import db


def run_rss_ingest():
    """Corre el ingestor RSS y retorna un resumen.

    Llamado por _rss_scheduler (lifespan, cada 6h) y por /admin/run-rss (manual).
    """
    try:
        from connectors.rss import fetch_rss
        items = fetch_rss()
        MINING_KW = [
            'mina','minera','minería','cobre','litio','oro','plata','molibdeno',
            'codelco','bhp','antofagasta','escondida','teck','collahuasi','enami',
            'atacama','antofagasta','tarapacá','exploración','yacimiento','faena',
        ]
        filtered = [i for i in items if any(
            kw in (i.get('title','') + i.get('description','')).lower()
            for kw in MINING_KW
        )]
        db.upsert_opportunities(filtered)
        return {"ok": True, "total": len(items), "relevantes": len(filtered)}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()[-500:]}
