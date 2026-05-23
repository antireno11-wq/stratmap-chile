"""Tests de filtros mineros, normalización de empresas y dedup."""
import pytest

from mining_filters import is_mining_relevant
from db import normalize_company, _compute_dedup_key


# ── mining_filters.is_mining_relevant ─────────────────────────────────────────

class TestMiningFilter:
    @pytest.mark.parametrize("title", [
        "Codelco aumenta producción de cobre en Chuquicamata",
        "Nuevo proyecto de litio en el Salar de Atacama",
        "BHP inicia construcción en Spence",
        "Antofagasta Minerals reporta resultados",
        "Sondaje minero en Atacama",
    ])
    def test_acepta_minero_obvio(self, title):
        assert is_mining_relevant(title) is True

    @pytest.mark.parametrize("title", [
        "Colo Colo gana el partido",
        "Detenido por droga en Santiago",
        "Hospital concesionado abre en Antofagasta",
        "Dólar cierra estable",
        "Premundi sub-20 en Calama",
    ])
    def test_rechaza_no_minero(self, title):
        assert is_mining_relevant(title) is False

    def test_fuente_minera_especifica_pasa(self):
        # Aunque no haya keyword obvio, viene de fuente minera
        assert is_mining_relevant("Resultados trimestrales", "", "Portal Minero") is True
        assert is_mining_relevant("Reporte mensual", "", "COCHILCO Noticias") is True

    def test_negativo_con_positivo_pasa(self):
        # Si menciona droga + minera, lo dejamos pasar (es noticia real)
        assert is_mining_relevant("Decomiso de droga en faena minera de Codelco") is True

    def test_descripcion_ayuda(self):
        # Title corto, description tiene la keyword
        assert is_mining_relevant("Empresa anuncia", "inversión en proyecto de cobre por USD 500M") is True


# ── normalize_company ─────────────────────────────────────────────────────────

class TestNormalizeCompany:
    @pytest.mark.parametrize("raw,expected", [
        ("Codelco",                                       "Codelco"),
        ("CODELCO",                                       "Codelco"),
        ("Corporacion Nacional del Cobre",                "Codelco"),
        ("Corporación Nacional del Cobre de Chile",       "Codelco"),
        ("BHP",                                           "BHP Chile"),
        ("BHP CHILE INC",                                 "BHP Chile"),
        ("Minera Escondida",                              "Escondida"),
        ("Compañía Minera Doña Inés de Collahuasi",       "Collahuasi"),
        ("Minera Los Pelambres",                          "Los Pelambres"),
        ("Antofagasta Minerals S.A.",                     "Antofagasta Minerals"),
        ("Minera Centinela",                              "Centinela"),
    ])
    def test_canonical_known(self, raw, expected):
        assert normalize_company(raw) == expected

    def test_empty_returns_none(self):
        assert normalize_company("") is None
        assert normalize_company(None) is None
        assert normalize_company("   ") is None

    def test_unknown_passes_through_cleaned(self):
        # Empresa no mapeada: limpia espacios pero mantiene casing
        assert normalize_company("  Empresa Random  SpA  ") == "Empresa Random SpA"

    def test_idempotent(self):
        # Aplicar dos veces da lo mismo
        n1 = normalize_company("Compañía Minera Doña Inés de Collahuasi")
        n2 = normalize_company(n1)
        assert n1 == n2 == "Collahuasi"


# ── dedup_key ──────────────────────────────────────────────────────────────────

class TestDedupKey:
    def test_misma_noticia_distintas_fuentes(self):
        a = {"title": "Codelco anuncia inversión", "company": "Codelco"}
        b = {"title": "Codelco Anuncia Inversión", "company": "Codelco"}
        c = {"title": "Codelco anuncia inversión.", "company": "Codelco"}
        ka = _compute_dedup_key(a)
        kb = _compute_dedup_key(b)
        kc = _compute_dedup_key(c)
        assert ka == kb == kc
        assert ka  # not None

    def test_distinto_titulo_distinta_key(self):
        a = {"title": "Codelco anuncia inversión", "company": "Codelco"}
        b = {"title": "Codelco para producción", "company": "Codelco"}
        assert _compute_dedup_key(a) != _compute_dedup_key(b)

    def test_titulo_vacio_devuelve_none(self):
        assert _compute_dedup_key({"title": "", "company": "x"}) is None
        assert _compute_dedup_key({"title": None}) is None

    def test_company_diferente_distinta_key(self):
        a = {"title": "anuncia inversión", "company": "Codelco"}
        b = {"title": "anuncia inversión", "company": "BHP"}
        assert _compute_dedup_key(a) != _compute_dedup_key(b)
