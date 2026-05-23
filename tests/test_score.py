"""Tests del scoring engine (funciones puras en db.py)."""
from db import (
    _mandante_size,
    _mineral_score,
    _title_keywords_score,
    calc_score,
)


# ── _mandante_size ────────────────────────────────────────────────────────────

class TestMandanteSize:
    def test_mandante_grande_codelco(self):
        assert _mandante_size("Codelco") == 15

    def test_mandante_grande_bhp(self):
        assert _mandante_size("BHP Chile") == 15

    def test_mandante_grande_collahuasi(self):
        assert _mandante_size("Compania Minera Dona Ines de Collahuasi") == 15

    def test_mandante_minera_desconocida(self):
        assert _mandante_size("Minera Pyme Nueva") == 8

    def test_mandante_no_minero(self):
        assert _mandante_size("Empresa Random SpA") == 3

    def test_mandante_vacio(self):
        assert _mandante_size("") == 0
        assert _mandante_size(None) == 0


# ── _mineral_score ────────────────────────────────────────────────────────────

class TestMineralScore:
    def test_litio_top(self):
        assert _mineral_score("", "Proyecto de Litio en Atacama") == 20

    def test_cobre_segundo(self):
        assert _mineral_score("", "Mina de cobre Andes") == 15

    def test_oro_tercero(self):
        assert _mineral_score("", "Explotación de oro y plata") == 12

    def test_recurso_field(self):
        # La función requiere "li " (con espacio) o "li-" como delimitador para
        # no confundir con palabras como "limpieza". "Litio" en el título también funciona.
        assert _mineral_score("Litio en salar", "") == 20

    def test_sin_mineral(self):
        # Sin mineral detectado da el default
        assert _mineral_score("", "Camino rural") == 3


# ── _title_keywords_score ─────────────────────────────────────────────────────

class TestTitleKeywords:
    def test_licitacion_publica(self):
        # Tiene "licitación pública" (+8); también matchea "llamado a licitación"? No, este título no.
        assert _title_keywords_score("Licitación pública servicios mantención") > 0

    def test_proyecto_suspendido_castiga(self):
        # Suspendido (-15) > positivos
        assert _title_keywords_score("Proyecto suspendido por causa fuerza mayor") < 0

    def test_titulo_neutro(self):
        assert _title_keywords_score("Reporte trimestral 2025") == 0


# ── calc_score: end-to-end ────────────────────────────────────────────────────

class TestCalcScore:
    def test_noticia_siempre_cero(self):
        item = {
            "source": "Portal Minero",
            "title": "Codelco anuncia inversión",
            "company": "Codelco",
            "raw": {},
        }
        assert calc_score(item) == 0

    def test_phase_noticia_siempre_cero(self):
        item = {"source": "manual", "phase": "Noticia", "title": "x"}
        assert calc_score(item) == 0

    def test_enami_base_alto(self):
        item = {
            "source": "ENAMI",
            "title": "Licitación servicios sondaje",
            "company": "ENAMI",
            "phase": "",
            "raw": {"tipo": "servicio"},
        }
        # base 68 + mandante 15 + keywords>0 = score alto, capeado a 99
        assert calc_score(item) >= 70

    def test_sea_calificado_medio(self):
        item = {
            "source": "SEA",
            "phase": "En Calificación",
            "title": "Proyecto Mina Litio",
            "company": "Empresa SpA",
            "raw": {},
        }
        # base ≈58 + mineral 20 + ... > 60
        assert calc_score(item) >= 60

    def test_sea_rechazado_bajo(self):
        item = {
            "source": "SEA",
            "phase": "Desistido",
            "title": "Proyecto X",
            "company": "Y",
            "raw": {},
        }
        # base 8 → score bajo
        assert calc_score(item) <= 30

    def test_score_capeado_a_99(self):
        # Caso límite: todos los bonuses al máximo no deberían superar 99
        item = {
            "source": "ENAMI",
            "title": "llamado a licitación pública servicios sondaje litio",
            "company": "Codelco",
            "phase": "",
            "region": "Antofagasta",
            "raw": {"tipo": "servicio", "operacion": "chuquicamata", "recurso": "Li"},
            "signal_score": 30,
        }
        assert calc_score(item) <= 99

    def test_score_nunca_negativo(self):
        item = {
            "source": "SEA",
            "phase": "Desistido",
            "title": "suspendido paralizado desistido rechazado",
            "company": "",
            "raw": {},
        }
        assert calc_score(item) >= 0

    def test_mandante_heat_boost(self):
        base_item = {
            "source": "ENAMI",
            "title": "servicio",
            "company": "Codelco",
            "phase": "",
            "raw": {"tipo": "servicio"},
        }
        score_sin_heat = calc_score(base_item, mandante_heat=0)
        score_con_heat = calc_score(base_item, mandante_heat=80)
        # Heat aporta bonus, así que score con heat >= sin heat
        assert score_con_heat >= score_sin_heat
