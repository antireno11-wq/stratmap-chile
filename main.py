from fastapi import Query

@app.get("/opportunities")
def opportunities(user_id: int = Query(None), limit: int = 50):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT * FROM opportunities ORDER BY score DESC LIMIT %s", (limit,))
            rows = cur.fetchall()

    if not user_id:
        return {"count": len(rows), "items": rows}

    # Traer preferencias del usuario
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT industries, regions, companies
                FROM user_preferences
                WHERE user_id = %s
            """, (user_id,))
            prefs = cur.fetchone()

    if not prefs:
        return {"count": len(rows), "items": rows}

    industries = prefs["industries"] or []
    regions = prefs["regions"] or []
    companies = prefs["companies"] or []

    scored = []

    for r in rows:
        personal_score = r["score"]

        if r["industry"] in industries:
            personal_score += 20

        if r["region"] in regions:
            personal_score += 10

        if r["company"] in companies:
            personal_score += 25

        r["personal_score"] = personal_score
        scored.append(r)

    scored.sort(key=lambda x: x["personal_score"], reverse=True)

    return {
        "count": len(scored),
        "items": scored[:limit]
    }
