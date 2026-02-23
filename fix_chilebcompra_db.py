"""
fix_chilebcompra_db.py
Script de una sola vez para corregir source y company en registros de ChileCompra.
Corre con: python fix_chilebcompra_db.py
"""
import db

def run():
    with db.get_conn() as conn:
        with conn.cursor() as cur:

            # 1. Ver cuántos registros hay con source incorrecto
            cur.execute("SELECT source, COUNT(*) FROM opportunities WHERE source ILIKE '%chilebcompra%' OR source ILIKE '%chile compra%' GROUP BY source;")
            rows = cur.fetchall()
            print("Estado actual:")
            for r in rows:
                print(f"  source='{r['source']}' → {r['count']} registros")

            # 2. Ver si el raw tiene NombreOrganismo
            cur.execute("""
                SELECT id, company, raw->>'NombreOrganismo' as organismo
                FROM opportunities 
                WHERE source ILIKE '%chilebcompra%' OR source ILIKE '%chile compra%'
                LIMIT 3;
            """)
            samples = cur.fetchall()
            print("\nMuestra de datos raw:")
            for s in samples:
                print(f"  id={s['id']} company='{s['company']}' organismo='{s['organismo']}'")

            # 3. Fix: normalizar source + poblar company desde raw
            cur.execute("""
                UPDATE opportunities
                SET 
                    source = 'Chile Compra',
                    company = COALESCE(
                        NULLIF(raw->>'NombreOrganismo', ''),
                        NULLIF(raw->>'Organismo', ''),
                        company
                    )
                WHERE source ILIKE '%chilebcompra%' OR source ILIKE '%chile compra%';
            """)
            updated = cur.rowcount
            print(f"\nActualizados: {updated} registros")

        conn.commit()
    print("Listo ✓")

if __name__ == "__main__":
    run()
