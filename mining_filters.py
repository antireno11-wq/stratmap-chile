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
    # Energía residencial / regulación de consumo (no son oportunidades B2B)
    "tarifa eléctrica", "tarifas eléctricas", "cuentas de la luz",
    "cuenta de la luz", "subsidio eléctrico", "subsidio a la luz",
    "alza tarifa", "alzas tarifa", "cne", "ley eléctrica",
    "estabilización tarifaria", "consumidor residencial",
    # Política partidaria
    "diputado", "senador", "convención constitucional", "plebiscito",
    "candidato presidencial", "campaña presidencial",
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


# Países LATAM/globales NO-Chile. Bloomberg Línea y AméricaEconomía mezclan
# noticias de toda la región: descartamos las que mencionan otro país sin
# mencionar Chile o una empresa/lugar chileno.
NON_CHILE_COUNTRIES = [
    # Países (raíz)
    "ecuador", "perú", "peru", "brasil", "brazil", "argentina",
    "colombia", "bolivia", "méxico", "mexico", "venezuela",
    "uruguay", "paraguay", "panamá", "panama", "guatemala", "honduras",
    "costa rica", "cuba", "república dominicana", "puerto rico",
    "españa", "spain", "estados unidos", "ee.uu", "eeuu",
    "australia", "canadá", "canada", "china", "japón", "japon",
    # Gentilicios — los más comunes en titulares
    "peruano", "peruana", "brasileño", "brasileña", "ecuatoriano", "ecuatoriana",
    "argentino", "mexicano", "mexicana", "colombiano", "colombiana",
    "boliviano", "boliviana", "venezolano", "venezolana",
    # Capitales / ciudades grandes (cuando aparecen las identifican como NO Chile)
    "lima", "bogotá", "bogota", "buenos aires", "ciudad de méxico", "ciudad de mexico",
    "são paulo", "sao paulo", "rio de janeiro", "quito", "guayaquil",
    "la paz", "asunción", "asuncion", "montevideo", "caracas",
]

_CHILE_MARKERS = {"chile", "chileno", "chilena", "chilenos", "chilenas"}
# Solo operadores que tienen Chile como principal jurisdicción. Empresas
# globales (Vale, Rio Tinto, Glencore, BHP genérico, Freeport, Kinross,
# Newmont, Barrick) NO cuentan porque pueden estar en cualquier país.
_CHILE_OPERATORS = {
    "codelco", "enami", "cochilco", "sernageomin",
    "sqm",
    "bhp chile", "minera escondida", "escondida", "minera spence", "spence",
    "antofagasta minerals", "amsa",
    "minera los pelambres", "los pelambres", "pelambres",
    "minera centinela", "centinela",
    "minera zaldívar", "minera zaldivar",
    "collahuasi", "minera collahuasi", "doña inés de collahuasi",
    "teck quebrada blanca", "quebrada blanca",
    "carmen de andacollo", "teck andacollo", "minera andacollo",
    "minera candelaria", "candelaria",
    "minera el abra", "el abra",
    "minera valle central", "el teniente", "andina", "chuquicamata",
}
_CHILE_MARKERS |= _CHILE_OPERATORS
_CHILE_MARKERS |= {p.lower() for p in PLACES}      # hubs chilenos
_NON_CHILE_SET = {c.lower() for c in NON_CHILE_COUNTRIES}


def is_chile_relevant(title: str, description: str = "") -> bool:
    """¿Esta noticia es de Chile (o de operaciones chilenas)?

    - Si menciona Chile / empresa chilena / hub chileno: SÍ.
    - Si menciona otro país y NO Chile: NO.
    - Si no menciona ninguno: SÍ (asumimos relevante; ya pasó is_mining_relevant).
    """
    blob = ((title or "") + " " + (description or "")).lower()
    if any(m in blob for m in _CHILE_MARKERS):
        return True
    if any(c in blob for c in _NON_CHILE_SET):
        return False
    return True


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
    # Fuentes mineras 100% específicas. Pasan sin keyword obvio porque su sitio
    # entero es minería. Energy/infra excluidas: traen mucho ruido tarifario.
    mining_specific = {
        "portal minero", "minería chilena", "mineria chilena", "mch online",
        "cochilco noticias", "cochilco", "reporte minero",
        "nueva minería y energía", "piso exploración",
        "infomineria", "mundo minería", "mundo mineria", "lithium chile",
    }
    if src_l in mining_specific:
        return True
    # Solo lugar sin contexto minero → NO. Antes pasaba demasiado ruido.
    return False
