"""Filtro de relevancia minera para noticias genéricas.

Antes vivía duplicado en sea_ingest.py y helpers.py con listas cortas. Lo
centralizamos acá con una lista más amplia que cubre:

- empresas (mineras chilenas + globales que operan en Chile)
- sustancias / minerales
- operaciones e infraestructura (relaves, lixiviación, sondaje, ...)
- regulatorio (RCA, SEA, SERNAGEOMIN, concesión minera)
- regiones / hubs mineros chilenos (Calama, Chuquicamata, Salar de Atacama, ...)

También una lista negativa para descartar ruido evidente (deportes, policial, etc.).
"""

# Empresas y operadores mineros (chilenos + globales presentes en Chile)
COMPANIES = [
    "codelco", "bhp", "sqm", "anglo american", "antofagasta minerals", "amsa",
    "los pelambres", "pelambres", "minera escondida", "escondida", "minera spence", "spence",
    "collahuasi", "minera collahuasi", "doña inés de collahuasi",
    "teck", "teck resources", "quebrada blanca", "carmen de andacollo",
    "minera candelaria", "candelaria", "lundin", "lundin mining", "lumina copper",
    "freeport", "freeport-mcmoran", "kinross", "yamana", "gold fields",
    "agnico eagle", "newmont", "sumitomo", "glencore", "rio tinto",
    "vale", "barrick", "capstone", "first quantum",
    "minera zaldívar", "minera zaldivar", "minera centinela", "centinela",
    "minera valle central", "minera el abra", "el abra",
    "enami", "sernageomin", "cochilco", "enap",
]

# Sustancias / minerales / commodities
SUBSTANCES = [
    "cobre", "copper", "litio", "lithium", "oro", "gold", "plata", "silver",
    "molibdeno", "moly", "hierro", "iron ore", "zinc", "níquel", "niquel", "nickel",
    "cobalto", "cobalt", "manganeso", "potasio", "yodo", "iodine",
    "boro", "boron", "nitrato", "salmuera", "uranio", "salar",
    "concentrado de cobre", "cátodo", "catodo",
]

# Operaciones, procesos e infraestructura minera
OPERATIONS = [
    "mina", "minera", "minero", "minería", "mining", "yacimiento", "faena",
    "tranque", "relave", "relaves", "lixiviación", "lixiviacion",
    "flotación", "flotacion", "concentradora", "planta concentradora",
    "fundición", "fundicion", "smelter", "refinería", "refineria",
    "sx-ew", "electroobtención", "electroobtencion",
    "sondaje", "perforación", "perforacion", "drilling", "exploración minera",
    "epcm", "estudios geológicos", "estudios geologicos",
    "explotación minera", "explotacion minera", "transporte minero",
    "rajo abierto", "subterránea", "subterranea", "tajo abierto",
    "geotecnia", "hidrogeología", "hidrogeologia",
]

# Regulatorio / institucional
REGULATORY = [
    "sea ", "sea.gob", "rca", "declaración de impacto", "declaracion de impacto",
    "estudio de impacto ambiental", "eia ", "dia ", "concesión minera", "concesion minera",
    "denuncio minero", "royalty minero", "ley minera", "código de minería",
    "codigo de mineria", "amsa - corporativo", "comité de inversiones",
]

# Hubs mineros chilenos (regiones, ciudades, salares)
PLACES = [
    "antofagasta", "atacama", "calama", "chuquicamata", "mejillones", "taltal",
    "tocopilla", "copiapó", "copiapo", "vallenar", "ovalle", "iquique",
    "sierra gorda", "andacollo", "tarapacá", "tarapaca",
    "salar de atacama", "salar de maricunga", "salar de pedernales",
    "los andes mining", "el teniente", "andina",
]

# Términos negativos: noise evidente que aparece en feeds genéricos.
NEGATIVE_KEYWORDS = [
    "fútbol", "futbol", "deporte", "partido", "gol", "jugador", "torneo",
    "premundi", "sub-20", "sub20", "sub 20", "sede deportiva",
    "baleado", "disparado", "pelea", "riña", "homicidio", "asesinato",
    "ketamina", "droga", "narco", "detenido", "imputado",
    "alumbrado público", "vertedero municipal",
    "hospital concesionado", "concesionado hospital",
    "dólar cierra", "bolsa de", "ipsa cae", "ipsa sube",
    "concesión vial",  # MOP infra, va por otra fuente, no por noticias
]


# Lugares como Antofagasta o Calama son débiles por sí solos: son ciudades
# enteras y aparecen en cualquier noticia local. Por eso los separamos: un
# match solo en PLACES no alcanza para sobreescribir un negativo.
_PLACES: set[str] = {kw.lower() for kw in PLACES}
_STRONG_POSITIVE: set[str] = {
    kw.lower() for bucket in (COMPANIES, SUBSTANCES, OPERATIONS, REGULATORY)
    for kw in bucket
}
_ALL_POSITIVE: set[str] = _STRONG_POSITIVE | _PLACES
_ALL_NEGATIVE: set[str] = {kw.lower() for kw in NEGATIVE_KEYWORDS}


def is_mining_relevant(title: str, description: str = "", source: str = "") -> bool:
    """¿Esta noticia/proyecto es relevante para Stratmap minería?

    Lógica:
    - Si hay un keyword negativo Y no hay positivo "fuerte" (empresa, mineral,
      operación, regulatorio): NO. Un mero match de ciudad no rescata.
    - Si hay positivo fuerte: SÍ (aunque haya negativo: "decomiso droga en
      faena de Codelco" es legítimo).
    - Si la fuente es minera-específica: SÍ.
    - Si hay solo positivo de lugar y nada negativo: SÍ.
    - Caso default: NO.

    El description ayuda cuando el title es muy corto.
    """
    title_l = (title or "").lower()
    desc_l = (description or "").lower()
    src_l = (source or "").lower()
    blob = title_l + " " + desc_l

    has_strong_pos = any(kw in blob for kw in _STRONG_POSITIVE)
    has_place_pos  = any(kw in blob for kw in _PLACES)
    has_neg        = any(kw in blob for kw in _ALL_NEGATIVE)

    # Negativo + solo lugar → noise (ej: "Premundi sub-20 en Calama")
    if has_neg and not has_strong_pos:
        return False
    # Positivo fuerte sobrevive
    if has_strong_pos:
        return True
    # Fuentes mineras/industriales específicas: pasan sin keyword obvio porque
    # su sitio entero es minería/energía/infraestructura.
    mining_specific = {
        "portal minero", "minería chilena", "mineria chilena", "mch online",
        "cochilco noticias", "cochilco", "reporte minero",
        "nueva minería y energía", "piso exploración", "construcción minera",
        "infomineria", "mundo minería", "mundo mineria", "lithium chile",
        "revista ei", "revista electricidad", "energía estratégica", "cchc",
    }
    if src_l in mining_specific:
        return True
    # Solo lugar sin contexto minero → NO. Antes pasaba demasiado ruido.
    return False
