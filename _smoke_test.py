"""Smoke test funcional completo contra Postgres real (docker). Manual, se borra después.
Recorre todos los routers buscando 500s / flujos rotos. Mockea Mercado Pago (externo).
"""
import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:55432/stratmap"
os.environ["SECRET_KEY"] = "x" * 48
os.environ["ADMIN_EMAILS"] = "admin@stratmap.cl"
os.environ["ALLOW_SETUP"] = "true"
os.environ["PUBLIC_URL"] = "https://web-production-e8e0d.up.railway.app"
os.environ.pop("RAILWAY_ENVIRONMENT_NAME", None)
os.environ.pop("MP_WEBHOOK_SECRET", None)  # webhook sin firma en el smoke

# Mock del SDK de Mercado Pago ANTES de importar la app (checkout no llama afuera).
import mercadopago
class _FakePre:
    def create(self, body): return {"status": 201, "response": {"id": "pre_smoke", "init_point": "https://mp.test/redirect"}}
    def get(self, pid): return {"status": 200, "response": {"status": "authorized", "external_reference": "1",
            "auto_recurring": {"transaction_amount": 29000}, "next_payment_date": "2026-08-01T00:00:00Z"}}
class _FakeSDK:
    def __init__(self, *a, **k): pass
    def preapproval(self): return _FakePre()
mercadopago.SDK = _FakeSDK

from fastapi.testclient import TestClient
import db
from auth import create_access_token, hash_password
import main

OK, BAD = [], []
def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(f"  [{'OK ' if cond else 'XX '}] {name}{('  → ' + detail) if (detail and not cond) else ''}")

with TestClient(main.app) as c:
    print("\n== setup ==")
    r = c.post("/setup/first-user", json={"email": "admin@stratmap.cl", "password": "Secreto123", "name": "Admin"})
    uid_admin = r.json().get("user_id")
    A = {"Authorization": f"Bearer {create_access_token(uid_admin, 'admin@stratmap.cl')}"}
    ub = db.create_user("user@stratmap.cl", hash_password("Secreto123"), "User")
    uid = ub["id"]
    U = {"Authorization": f"Bearer {create_access_token(uid, 'user@stratmap.cl')}"}
    check("setup admin + user", bool(uid_admin and uid))

    # Sembrar una oportunidad vía /ingest (admin)
    r = c.post("/ingest", headers=A, json={"items": [{
        "source": "SEA", "title": "Proyecto Minero de Prueba Cobre Norte 2026", "url": "https://sea.test/1",
        "company": "Codelco", "industry": "Minería", "region": "Antofagasta", "phase": "Construcción", "score": 75}]})
    check("POST /ingest siembra oportunidad", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    r = c.get("/opportunities?all=true&limit=50", headers=U)
    items = r.json().get("items", [])
    opp_id = items[0]["id"] if items else None
    check("GET /opportunities devuelve la oportunidad", bool(opp_id), f"{r.status_code}")

    print("\n== /me/* ==")
    check("GET /me/plan", c.get("/me/plan", headers=U).status_code == 200)
    check("GET /me/preferences", c.get("/me/preferences", headers=U).status_code == 200)
    r = c.put("/me/preferences", headers=U, json={"industries": ["Minería"], "keywords": ["cobre"],
              "preferred_regions": ["Antofagasta"], "companies": [], "phases": [], "sources": []})
    check("PUT /me/preferences", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    check("GET /me/profile", c.get("/me/profile", headers=U).status_code == 200)
    check("GET /me/service-profile", c.get("/me/service-profile", headers=U).status_code == 200)
    r = c.put("/me/service-profile", headers=U, json={"company_key": "acme", "company_name": "ACME",
              "services": [{"name": "Sondajes", "description": ""}], "regions": ["Antofagasta"],
              "contract_sizes": [], "known_mandantes": [], "onboarding_done": True})
    check("PUT /me/service-profile", r.status_code == 200, f"{r.status_code} {r.text[:140]}")

    print("\n== oportunidades / pipeline / notas ==")
    if opp_id:
        check("GET /opportunities/{id}/services", c.get(f"/opportunities/{opp_id}/services", headers=U).status_code == 200)
        check("GET /opportunities/{id}/pipeline", c.get(f"/opportunities/{opp_id}/pipeline", headers=U).status_code == 200)
        r = c.put(f"/opportunities/{opp_id}/pipeline", headers=U, json={"status": "En análisis", "assignee": "Yo"})
        check("PUT pipeline", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        r = c.post(f"/opportunities/{opp_id}/notes", headers=U, json={"note": "Nota de prueba", "author": "Yo"})
        check("POST nota", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        check("GET notas", c.get(f"/opportunities/{opp_id}/notes", headers=U).status_code == 200)
        r = c.post(f"/opportunities/{opp_id}/analyze-services", headers=U)
        check("analyze-services free → 402", r.status_code == 402, f"{r.status_code}")

    print("\n== contactos (CRUD + gates) ==")
    r = c.post("/contacts", headers=U, json={"name": "Juan Pérez", "company": "Codelco", "role": "Gerente"})
    check("POST contacto", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    cid = r.json().get("id")
    check("GET contactos", c.get("/contacts", headers=U).status_code == 200)
    check("PUT contacto", c.put(f"/contacts/{cid}", headers=U, json={"role": "CEO"}).status_code == 200)
    check("POST /contacts/import", c.post("/contacts/import", headers=U,
          json=[{"name": "Ana", "company": "BHP"}]).status_code == 200)
    check("export free → 402", c.get("/contacts/export", headers=U).status_code == 402)
    check("generate-email contacto inexistente → 404", c.post("/contacts/99999/generate-email", headers=U).status_code == 404)

    print("\n== feature gates con plan Pro ==")
    db.upsert_user_plan(user_id=uid, plan="pro", status="active")
    check("export Pro → 200", c.get("/contacts/export", headers=U).status_code == 200)
    check("DELETE contacto", c.delete(f"/contacts/{cid}", headers=U).status_code == 200)

    print("\n== billing (MP mockeado) ==")
    check("checkout plan inválido → 400", c.post("/billing/checkout", headers=U, json={"plan": "xxx"}).status_code == 400)
    check("checkout free → 400", c.post("/billing/checkout", headers=U, json={"plan": "free"}).status_code == 400)
    r = c.post("/billing/checkout", headers=U, json={"plan": "pro"})
    check("checkout pro → init_point", r.status_code == 200 and r.json().get("init_point"), f"{r.status_code} {r.text[:140]}")
    check("GET /billing/portal", c.get("/billing/portal", headers=U).status_code == 200)
    check("webhook /pagos topic no-preapproval → ok", c.post("/pagos?topic=payment&id=1").status_code == 200)

    print("\n== páginas estáticas ==")
    for pg in ["/", "/login.html", "/pricing.html", "/kanban.html", "/mandantes.html",
               "/preferences.html", "/onboarding.html", "/mapa.html", "/health.html", "/theme.css", "/app.js"]:
        check(f"GET {pg}", c.get(pg).status_code == 200)

    print("\n== auto-GET de todas las rutas sin parámetros (busca 500s) ==")
    seen = set()
    SKIP = ("/admin/run", "/admin/ingest", "/ingest", "/setup")  # endpoints pesados/destructivos
    for route in main.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods or "{" in path or path in seen:
            continue
        if any(path.startswith(s) for s in SKIP):
            continue
        seen.add(path)
        try:
            st = c.get(path, headers=A).status_code
        except Exception as e:
            st = f"EXC:{type(e).__name__}"
        # Un smoke sano: nunca 5xx. (401/402/404/200 son aceptables.)
        ok = isinstance(st, int) and st < 500
        check(f"GET {path} [{st}]", ok, str(st))

print("\n" + "=" * 60)
print(f"RESULTADO SMOKE: {len(OK)} OK, {len(BAD)} fallos")
if BAD:
    print("FALLARON:", BAD)
    sys.exit(1)
print("SMOKE TODO VERDE ✓")
