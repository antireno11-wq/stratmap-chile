"""Clasificación canónica de fuentes — qué tipo de oportunidad representa cada source.

Antes esto vivía esparcido en SQL crudo (routers/mandantes.py, routers/opportunities.py).
Centralizarlo acá significa que cambiar la categorización es una sola edición.

Categorías:
  - licitacion : compra pública / privada con plazo de postulación (ENAMI, Codelco,
                 MOP, ChileCompra, SICEP, Ariba). Suele ser la oportunidad más
                 directa para un proveedor.
  - concesion  : derecho minero o concesión administrativa (SIGEX, lo que entrega
                 SERNAGEOMIN). Señal temprana — no hay compra pública aún.
  - prospecto  : proyecto en evaluación ambiental (SEA). Pipeline futuro,
                 horizonte 6-24 meses.
  - noticia    : medios y portales sectoriales. No es oportunidad directa pero
                 da contexto y señales tempranas.
  - empleo     : scrapers de careers pages (BHP/AMSA/Teck/Collahuasi/Lundin).
                 Señal de actividad/expansión del mandante.
  - manual     : entrada manual del usuario.
"""

CATEGORIES: dict[str, str] = {
    # Licitaciones (compra pública o privada formal)
    "ENAMI":              "licitacion",
    "Codelco":            "licitacion",
    "MOP":                "licitacion",
    "ChileCompra":        "licitacion",
    "SICEP":              "licitacion",
    "Ariba Codelco":      "licitacion",
    "MLP Proveedores":    "licitacion",

    # Concesiones mineras
    # SIGEX desactivado 2026-05 — derechos sobre el suelo, no señal de oportunidad
    # comercial. Los datos históricos quedan pero no entran al pipeline ni al score.
    "SIGEX":              "concesion",

    # Regulatorio (hechos esenciales CMF) — info de calidad institucional. Por
    # ahora la categorizamos como noticia (encaja en el flujo de display); el
    # scoring v2 le dará un peso explícito mayor.
    "cmf":                "noticia",

    # Prospectos (evaluación ambiental / catastros oficiales de inversión)
    "SEA":                "prospecto",
    "COCHILCO":           "prospecto",   # catastro de inversiones — proyectos con MUSD declarados

    # Noticias y medios sectoriales
    "Portal Minero":              "noticia",
    "Minería Chilena":            "noticia",
    "MCh Online":                 "noticia",
    "COCHILCO Noticias":          "noticia",
    "Reporte Minero":             "noticia",
    "Nueva Minería y Energía":    "noticia",
    "Piso Exploración":           "noticia",
    "Construcción Minera":        "noticia",
    "Diario Financiero":          "noticia",
    "Pulso":                      "noticia",
    "El Mostrador Mercados":      "noticia",
    "AméricaEconomía":            "noticia",
    "Bloomberg Línea":            "noticia",
    "CChC":                       "noticia",
    "Revista EI":                 "noticia",
    "Revista Electricidad":       "noticia",
    "Energía Estratégica":        "noticia",
    "InfoMineria":                "noticia",
    "Mundo Minería":              "noticia",
    "Lithium Chile":              "noticia",
    "BioBioChile":                "noticia",
    "Emol":                       "noticia",
    "La Tercera":                 "noticia",
    "Cooperativa Economía":       "noticia",
    "24Horas Economía":           "noticia",
    "Radio Universidad de Chile": "noticia",
    "Radio U. de Chile":          "noticia",
    "RSS":                        "noticia",

    # Empleos / señales de contratación
    "BHP Careers":         "empleo",
    "AMSA Careers":        "empleo",
    "Lundin Careers":      "empleo",
    "Teck Careers":        "empleo",
    "Collahuasi Careers":  "empleo",

    # Manual
    "manual":              "manual",
}


def category_of(source: str) -> str:
    """Devuelve la categoría canónica del source. Sources desconocidos quedan en 'otros'."""
    if not source:
        return "otros"
    return CATEGORIES.get(source.strip(), "otros")


# Helpers para SQL: listas planas por categoría, listas para usar en `source = ANY(%s)`.
def sources_in(category: str) -> list[str]:
    return [s for s, c in CATEGORIES.items() if c == category]


LICITACION_SOURCES = sources_in("licitacion")
CONCESION_SOURCES  = sources_in("concesion")
PROSPECTO_SOURCES  = sources_in("prospecto")
NOTICIA_SOURCES    = sources_in("noticia")
EMPLEO_SOURCES     = sources_in("empleo")
