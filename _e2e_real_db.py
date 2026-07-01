"""E2E real contra un Postgres de verdad (docker). NO es parte de la app.
Se ejecuta a mano y se borra después. Verifica los caminos que los unit tests
no cubren: migración de contactos, aislamiento multi-tenant y webhook MP→plan.
"""
import os
import sys

# Fijar entorno ANTES de importar la app (load_dotenv override=False no los pisa).
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:55432/stratmap"
os.environ["SECRET_KEY"] = "x" * 48
os.environ["ADMIN_EMAILS"] = "admin@stratmap.cl"
os.environ["ALLOW_SETUP"] = "true"
os.environ.pop("RAILWAY_ENVIRONMENT_NAME", None)

from fastapi.testclient import TestClient

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK ' if cond else 'XX '}] {name}")

import db
from auth import create_access_token, hash_password
import main

print("\n== FASE A: boot + schema contra Postgres real ==")
with TestClient(main.app) as client:
    # init_db_safe corrió en el lifespan. Verificar tablas/colmnas clave.
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='contacts'")
            cols = {r["column_name"] for r in cur.fetchall()}
    check("tabla contacts existe", bool(cols))
    check("contacts tiene user_id", "user_id" in cols)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name='contacts' AND column_name='user_id'")
            row = cur.fetchone()
    check("contacts.user_id es NOT NULL", row and row["is_nullable"] == "NO")

    print("\n== FASE B: crear dos usuarios ==")
    r = client.post("/setup/first-user", json={"email": "admin@stratmap.cl", "password": "Secreto123", "name": "Admin"})
    check("setup/first-user 200", r.status_code == 200)
    uid_a = r.json().get("user_id")
    user_b = db.create_user("userb@stratmap.cl", hash_password("Secreto123"), "User B")
    uid_b = user_b["id"]
    check("dos user_id distintos", uid_a and uid_b and uid_a != uid_b)
    tok_a = create_access_token(uid_a, "admin@stratmap.cl")
    tok_b = create_access_token(uid_b, "userb@stratmap.cl")
    H = lambda t: {"Authorization": f"Bearer {t}"}

    print("\n== FASE C: aislamiento multi-tenant ==")
    r = client.post("/contacts", headers=H(tok_a), json={"name": "Contacto de A", "company": "Codelco"})
    check("A crea contacto 200", r.status_code == 200)
    cid_a = r.json().get("id")
    r = client.get("/contacts", headers=H(tok_b))
    check("B lista contactos: NO ve los de A", r.status_code == 200 and len(r.json().get("items", [])) == 0)
    r = client.delete(f"/contacts/{cid_a}", headers=H(tok_b))
    check("B NO puede borrar el contacto de A (404)", r.status_code == 404)
    r = client.get(f"/contacts?company=Codelco", headers=H(tok_b))
    check("B por-empresa: NO ve los de A", r.status_code == 200 and len(r.json().get("items", [])) == 0)
    r = client.post("/contacts", headers=H(tok_b), json={"name": "Contacto de B", "company": "BHP"})
    cid_b = r.json().get("id")
    r = client.get("/contacts", headers=H(tok_a))
    items_a = r.json().get("items", [])
    check("A solo ve su propio contacto", len(items_a) == 1 and items_a[0]["id"] == cid_a)
    r = client.delete(f"/contacts/{cid_a}", headers=H(tok_a))
    check("A SÍ puede borrar el suyo (200)", r.status_code == 200)

    print("\n== FASE D: migración desde esquema 'viejo' (contacts sin user_id) ==")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP INDEX IF EXISTS idx_contacts_user_id")
            cur.execute("ALTER TABLE contacts DROP COLUMN user_id")
            cur.execute("INSERT INTO contacts (name, company) VALUES ('Huérfano legacy', 'SQM')")
        conn.commit()
    db.init_contacts_db()  # dispara _migrate_contacts_user_id
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name='contacts' AND column_name='user_id'")
            nn = cur.fetchone()
            cur.execute("SELECT user_id FROM contacts WHERE name='Huérfano legacy'")
            orphan = cur.fetchone()
            cur.execute("SELECT MIN(id) AS m FROM users")
            first_uid = cur.fetchone()["m"]
    check("migración: user_id vuelve a NOT NULL", nn and nn["is_nullable"] == "NO")
    check("migración: contacto huérfano asignado al primer usuario",
          orphan and orphan["user_id"] == first_uid)

    print("\n== FASE E: webhook MP → activación de plan (fetch a MP mockeado) ==")
    import routers.billing as billing
    # Estado de checkout: plan pendiente con preapproval guardado.
    db.upsert_user_plan(user_id=uid_b, plan="pro", status="pending", mp_preapproval_id="pre_test_1")
    _orig = billing._fetch_preapproval
    billing._fetch_preapproval = lambda pid: {
        "status": "authorized", "external_reference": str(uid_b),
        "auto_recurring": {"transaction_amount": 29000},
        "next_payment_date": "2026-07-17T00:00:00Z",
    }
    try:
        r = client.post("/pagos?topic=preapproval&id=pre_test_1")
        check("webhook 200", r.status_code == 200)
        plan = db.get_user_plan(uid_b)
        check("webhook activó plan 'pro'", plan.get("plan") == "pro")
        check("webhook status pasó a 'active'", plan.get("status") == "active")

        # Anti-fraude: monto que NO matchea ningún plan → ignora, no cambia el plan.
        db.upsert_user_plan(user_id=uid_a, plan="free", status="active", mp_preapproval_id="pre_fraude")
        billing._fetch_preapproval = lambda pid: {
            "status": "authorized", "external_reference": str(uid_a),
            "auto_recurring": {"transaction_amount": 1},  # monto basura
        }
        r = client.post("/pagos?topic=preapproval&id=pre_fraude")
        check("webhook ignora monto inválido", r.json().get("ignored") == "amount_mismatch")
        check("plan NO se escaló por monto basura", db.get_user_plan(uid_a).get("plan") == "free")
    finally:
        billing._fetch_preapproval = _orig

print("\n" + "=" * 56)
print(f"RESULTADO: {len(PASS)} OK, {len(FAIL)} fallos")
if FAIL:
    print("FALLARON:", FAIL)
    sys.exit(1)
print("TODO VERDE ✓")
