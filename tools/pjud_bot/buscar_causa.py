#!/usr/bin/env python3
# tools/pjud_bot/buscar_causa.py
"""
Bot para revisar la Oficina Judicial Virtual (OJV) del Poder Judicial de Chile
y encontrar causas asociadas a un litigante / caratulado.

Pensado como herramienta de VERIFICACIÓN: si recibiste un correo (p. ej. de un
"estudio jurídico") avisando de una demanda, este bot te deja confirmar por tu
cuenta, en la fuente oficial, si la causa realmente existe — sin tener que
confiar en quien te escribió.

Fuente oficial: https://oficinajudicialvirtual.pjud.cl/  (Consulta Unificada de Causas)

Cómo funciona
-------------
La consulta pública de la OJV exige resolver un captcha, que una máquina no debe
saltarse. Por eso el bot funciona en dos modos:

  * assisted (por defecto): abre un navegador real, te lleva a la consulta y TÚ
    haces la búsqueda + resuelves el captcha. Cuando aparezca la tabla de
    resultados, vuelves a la terminal y presionas ENTER: el bot lee la tabla
    que quedó en pantalla, filtra las causas que calzan con lo que buscas y las
    exporta a JSON/CSV. Este modo SIEMPRE funciona aunque el sitio cambie.

  * auto (--auto): además intenta rellenar el formulario por ti (jurisdicción,
    tipo de búsqueda, nombre/RUT). Es "best-effort": si el sitio cambió sus
    campos, caerá de vuelta al modo asistido. El captcha igual lo resuelves tú.

Uso
---
  pip install -r requirements.txt
  playwright install chromium

  # Buscar por nombre del litigante (lo de la imagen):
  python buscar_causa.py --nombre "MENA ORTEGA WILFREDO"

  # Buscar por RUT (más preciso). Reemplaza por tu RUT real:
  python buscar_causa.py --rut 12.345.678-9

  # Afinar qué resultados marcar como "calce" (por defecto: el caratulado del correo):
  python buscar_causa.py --nombre "MENA ORTEGA WILFREDO" --match BANCO --match MENA

Nada de esto envía tus datos a terceros: todo ocurre entre tu navegador y el
sitio oficial del Poder Judicial.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

OJV_URL = "https://oficinajudicialvirtual.pjud.cl/indexN.php"

# Jurisdicciones de la consulta unificada. Una cobranza bancaria como
# "BANCO DEL ESTADO/MENA" suele ser un juicio ejecutivo en sede CIVIL.
JURISDICCIONES = ["suprema", "apelaciones", "civil", "laboral", "penal",
                  "cobranza", "familia", "disciplinario"]


@dataclass
class Causa:
    """Una fila de resultados de la OJV, normalizada."""
    rol: str = ""
    caratulado: str = ""
    tribunal: str = ""
    fecha: str = ""
    estado: str = ""
    competencia: str = ""
    raw: list[str] = field(default_factory=list)

    def matches(self, terms: list[str]) -> bool:
        if not terms:
            return True
        blob = " ".join([self.rol, self.caratulado, self.tribunal,
                         self.estado, self.competencia] + self.raw).upper()
        return all(t.upper() in blob for t in terms)


def log(msg: str) -> None:
    print(f"[pjud] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Lectura / parseo de la tabla de resultados que quedó renderizada en la página
# --------------------------------------------------------------------------- #

# Encabezados típicos de las tablas de resultados de la OJV, en orden flexible.
HEADER_HINTS = {
    "rol": ["rol", "rit", "ruc", "causa"],
    "caratulado": ["caratulado", "caratula", "carátula", "litigante", "partes"],
    "tribunal": ["tribunal", "juzgado", "corte"],
    "fecha": ["fecha", "ingreso"],
    "estado": ["estado", "etapa"],
    "competencia": ["competencia", "materia"],
}


def _classify_headers(headers: list[str]) -> dict[int, str]:
    """Mapea índice de columna -> nombre de campo, según el encabezado."""
    mapping: dict[int, str] = {}
    for i, h in enumerate(headers):
        hl = (h or "").strip().lower()
        for field_name, hints in HEADER_HINTS.items():
            if any(hint in hl for hint in hints):
                mapping[i] = field_name
                break
    return mapping


def parse_tables(tables: list[dict[str, Any]]) -> list[Causa]:
    """
    `tables` es una lista de {headers: [...], rows: [[...], ...]} extraída del DOM.
    Devuelve causas normalizadas. Las columnas que no reconozca igual quedan en .raw.
    """
    causas: list[Causa] = []
    for tbl in tables:
        headers = tbl.get("headers") or []
        mapping = _classify_headers(headers)
        for row in tbl.get("rows") or []:
            cells = [c.strip() for c in row]
            # Ignorar filas vacías o de "no hay resultados".
            joined = " ".join(cells).strip()
            if not joined or len(cells) < 2:
                continue
            if re.search(r"no\s+(se\s+)?(han\s+)?encontr|sin\s+resultados", joined, re.I):
                continue
            c = Causa(raw=cells)
            for idx, field_name in mapping.items():
                if idx < len(cells):
                    setattr(c, field_name, cells[idx])
            # Si no hubo encabezados reconocibles, heurística mínima.
            if not mapping:
                if len(cells) >= 2:
                    c.rol = cells[0]
                    c.caratulado = max(cells, key=len)  # la celda más larga suele ser la carátula
            causas.append(c)
    return causas


# JS que extrae TODAS las tablas visibles de la página (headers + filas).
EXTRACT_TABLES_JS = r"""
() => {
  const out = [];
  for (const table of document.querySelectorAll('table')) {
    const rect = table.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue; // tabla oculta
    let headers = [];
    const headEls = table.querySelectorAll('thead th, thead td');
    if (headEls.length) {
      headers = Array.from(headEls).map(e => e.innerText.trim());
    } else {
      const firstRow = table.querySelector('tr');
      if (firstRow && firstRow.querySelectorAll('th').length) {
        headers = Array.from(firstRow.querySelectorAll('th')).map(e => e.innerText.trim());
      }
    }
    const rows = [];
    const bodyRows = table.querySelectorAll('tbody tr');
    const rowEls = bodyRows.length ? bodyRows : table.querySelectorAll('tr');
    for (const tr of rowEls) {
      const cells = tr.querySelectorAll('td');
      if (!cells.length) continue;
      rows.push(Array.from(cells).map(td => td.innerText.replace(/\s+/g,' ').trim()));
    }
    if (rows.length) out.push({ headers, rows });
  }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Auto-fill best-effort del formulario de la OJV
# --------------------------------------------------------------------------- #

def try_autofill(page, jurisdiccion: str, nombre: str | None, rut: str | None) -> bool:
    """
    Intenta abrir la pestaña de jurisdicción y rellenar el formulario.
    Devuelve True si parece haber dejado algo listo; False si no pudo (caemos a asistido).
    Es deliberadamente tolerante: la OJV cambia su DOM seguido.
    """
    ok = False
    try:
        # Botones/pestañas de jurisdicción suelen tener el texto visible.
        label = {
            "suprema": "Corte Suprema", "apelaciones": "Corte de Apelaciones",
            "civil": "Civil", "laboral": "Laboral", "penal": "Penal",
            "cobranza": "Cobranza", "familia": "Familia",
            "disciplinario": "Disciplinario",
        }.get(jurisdiccion, jurisdiccion)
        for sel in [f"text=/^\\s*{re.escape(label)}\\s*$/", f"role=tab[name=/{re.escape(label)}/i]",
                    f"a:has-text('{label}')", f"button:has-text('{label}')"]:
            try:
                el = page.locator(sel).first
                if el.count():
                    el.click(timeout=3000)
                    ok = True
                    page.wait_for_timeout(800)
                    break
            except Exception:
                continue

        # Rellenar nombre o RUT en el primer input que calce.
        if nombre:
            for sel in ["input[name*='nombre' i]", "input[placeholder*='nombre' i]",
                        "input[id*='nombre' i]", "input[name*='litigante' i]"]:
                try:
                    el = page.locator(sel).first
                    if el.count():
                        el.fill(nombre, timeout=3000)
                        ok = True
                        break
                except Exception:
                    continue
        if rut:
            for sel in ["input[name*='rut' i]", "input[placeholder*='rut' i]",
                        "input[id*='rut' i]"]:
                try:
                    el = page.locator(sel).first
                    if el.count():
                        el.fill(rut, timeout=3000)
                        ok = True
                        break
                except Exception:
                    continue
    except Exception as e:
        log(f"auto-fill no pudo completar el formulario: {e}")
    return ok


# --------------------------------------------------------------------------- #
# Flujo principal
# --------------------------------------------------------------------------- #

def run(args: argparse.Namespace) -> int:
    if not args.nombre and not args.rut and not args.rol:
        log("Debes indicar al menos --nombre, --rut o --rol para buscar.")
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Falta Playwright. Instala con:")
        log("  pip install -r requirements.txt && playwright install chromium")
        return 2

    # Términos de calce: por defecto, lo del caratulado del correo.
    match_terms = list(args.match) if args.match else []
    if not match_terms:
        if args.nombre:
            # Usa el apellido más distintivo del nombre dado.
            match_terms = [args.nombre.split()[0]]
        elif args.rut:
            match_terms = [args.rut]

    log(f"Jurisdicción: {args.jurisdiccion}")
    log(f"Buscando por: " + ", ".join(
        f"{k}={v}" for k, v in [("nombre", args.nombre), ("rut", args.rut),
                                 ("rol", args.rol)] if v))
    log(f"Marcaré como CALCE las causas que contengan: {match_terms or '(todas)'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            locale="es-CL",
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        log(f"Abriendo {OJV_URL} ...")
        page.goto(OJV_URL, wait_until="domcontentloaded", timeout=60000)

        if args.auto:
            log("Modo auto: intentando rellenar el formulario...")
            try_autofill(page, args.jurisdiccion, args.nombre, args.rut)

        print()
        print("=" * 72)
        print("  ACCIÓN MANUAL REQUERIDA EN EL NAVEGADOR")
        print("=" * 72)
        print("  1. En la OJV abre 'Consulta Unificada de Causas'.")
        print(f"     Pestaña sugerida: {args.jurisdiccion.upper()}  (cobranza bancaria")
        print("     de un banco contra una persona suele ser sede CIVIL).")
        print("  2. Elige el tipo de búsqueda (Nombre / RUT / Rol) e ingresa el dato.")
        if args.nombre:
            print(f"        Nombre litigante : {args.nombre}")
        if args.rut:
            print(f"        RUT litigante    : {args.rut}")
        if args.rol:
            print(f"        Rol              : {args.rol}")
        print("  3. RESUELVE EL CAPTCHA y presiona 'Buscar'.")
        print("  4. Cuando veas la TABLA de resultados en pantalla, vuelve aquí.")
        print("=" * 72)
        if args.headless:
            log("OJO: estás en --headless, no verás el navegador ni podrás resolver el captcha.")
        try:
            input("\n>>> Presiona ENTER cuando la tabla de resultados esté visible... ")
        except (EOFError, KeyboardInterrupt):
            log("Cancelado por el usuario.")
            browser.close()
            return 1

        log("Leyendo la tabla de resultados de la página...")
        tables = page.evaluate(EXTRACT_TABLES_JS)
        browser.close()

    causas = parse_tables(tables)
    log(f"Filas de causa detectadas en pantalla: {len(causas)}")

    calces = [c for c in causas if c.matches(match_terms)]
    return report(causas, calces, match_terms, args)


def report(causas: list[Causa], calces: list[Causa],
           match_terms: list[str], args: argparse.Namespace) -> int:
    print()
    print("=" * 72)
    if calces:
        print(f"  ✅ {len(calces)} CAUSA(S) QUE CALZAN con {match_terms}")
    else:
        print(f"  ⚠️  NINGUNA causa en pantalla calza con {match_terms}")
        if causas:
            print(f"     (sí se leyeron {len(causas)} filas; revisa los términos --match)")
        else:
            print("     (no se leyó ninguna tabla; ¿estaban los resultados en pantalla?)")
    print("=" * 72)

    for i, c in enumerate(calces or causas, 1):
        print(f"\n  [{i}] Rol/RIT : {c.rol or '—'}")
        print(f"      Carátula: {c.caratulado or '—'}")
        if c.tribunal:    print(f"      Tribunal: {c.tribunal}")
        if c.fecha:       print(f"      Fecha   : {c.fecha}")
        if c.estado:      print(f"      Estado  : {c.estado}")
        if c.competencia: print(f"      Materia : {c.competencia}")
        if not any([c.rol, c.caratulado, c.tribunal]):
            print(f"      Datos   : {' | '.join(c.raw)}")

    # Exportar.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "consulta": {
            "nombre": args.nombre, "rut": args.rut, "rol": args.rol,
            "jurisdiccion": args.jurisdiccion, "match": match_terms,
            "fuente": OJV_URL, "fecha_consulta": datetime.now().isoformat(),
        },
        "total_filas": len(causas),
        "calces": [asdict(c) for c in calces],
        "todas": [asdict(c) for c in causas],
    }
    json_path = out_dir / f"causas_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / f"causas_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["calce", "rol", "caratulado", "tribunal", "fecha", "estado", "competencia"])
        calce_set = {id(c) for c in calces}
        for c in causas:
            w.writerow(["SI" if id(c) in calce_set else "", c.rol, c.caratulado,
                        c.tribunal, c.fecha, c.estado, c.competencia])

    print()
    log(f"Exportado: {json_path}")
    log(f"Exportado: {csv_path}")
    print()
    print("  Recordatorio: si la causa existe, los detalles y el 'cuaderno' con")
    print("  las actuaciones están en la misma OJV. NO necesitas pagarle a quien")
    print("  te avisó por correo para enterarte: la consulta es gratuita y pública.")
    return 0 if calces else (3 if causas else 4)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bot de verificación de causas en la Oficina Judicial Virtual del Poder Judicial de Chile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--nombre", help="Nombre del litigante a buscar (ej: 'MENA ORTEGA WILFREDO').")
    p.add_argument("--rut", help="RUT del litigante (más preciso), ej: 12.345.678-9.")
    p.add_argument("--rol", help="Rol/RIT exacto si ya lo conoces, ej: 'C-12345-2025'.")
    p.add_argument("--jurisdiccion", default="civil", choices=JURISDICCIONES,
                   help="Sede a consultar (default: civil; típica para cobranza bancaria).")
    p.add_argument("--match", action="append", default=[],
                   help="Término que debe contener una causa para marcarla como CALCE. "
                        "Repetible (todos deben aparecer). Default: apellido/rut buscado.")
    p.add_argument("--auto", action="store_true",
                   help="Intentar rellenar el formulario automáticamente (best-effort).")
    p.add_argument("--headless", action="store_true",
                   help="Correr sin ventana (NO recomendado: no podrás resolver el captcha).")
    p.add_argument("--out", default="./resultados",
                   help="Carpeta donde guardar JSON/CSV (default: ./resultados).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        log("Interrumpido.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
