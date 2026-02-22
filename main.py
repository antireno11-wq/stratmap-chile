@app.delete("/admin/cleanup-test")
def cleanup_test():
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM opportunities 
                WHERE title ILIKE '%test%'
                   OR title ILIKE '%ping%'
                   OR title ILIKE '%manual%'
                   OR company ILIKE '%testco%'
                RETURNING id
            """)
            deleted = cur.rowcount
        conn.commit()
    return {"ok": True, "deleted": deleted}

# ── Static UI (debe ir al final) ──────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
