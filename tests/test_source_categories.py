"""Tests del módulo source_categories — clasificación canónica de fuentes."""
import pytest

from source_categories import (
    CATEGORIES, category_of, sources_in,
    LICITACION_SOURCES, CONCESION_SOURCES, PROSPECTO_SOURCES,
    NOTICIA_SOURCES, EMPLEO_SOURCES,
)


class TestCategoryOf:
    @pytest.mark.parametrize("source,expected", [
        ("ENAMI", "licitacion"),
        ("Codelco", "licitacion"),
        ("MOP", "licitacion"),
        ("ChileCompra", "licitacion"),
        ("SICEP", "licitacion"),
        ("SIGEX", "concesion"),
        ("SEA", "prospecto"),
        ("Portal Minero", "noticia"),
        ("BHP Careers", "empleo"),
        ("manual", "manual"),
    ])
    def test_known_source(self, source, expected):
        assert category_of(source) == expected

    def test_unknown_source(self):
        assert category_of("foo") == "otros"

    def test_empty_source(self):
        assert category_of("") == "otros"
        assert category_of(None) == "otros"

    def test_whitespace_stripped(self):
        assert category_of("  ENAMI  ") == "licitacion"


class TestBuckets:
    def test_licitacion_includes_mop_chilecompra(self):
        # Bug histórico: solo ENAMI y Codelco contaban como licitaciones
        assert "MOP" in LICITACION_SOURCES
        assert "ChileCompra" in LICITACION_SOURCES
        assert "SICEP" in LICITACION_SOURCES

    def test_sigex_is_concesion_not_licitacion(self):
        assert "SIGEX" in CONCESION_SOURCES
        assert "SIGEX" not in LICITACION_SOURCES

    def test_sea_is_prospecto(self):
        assert "SEA" in PROSPECTO_SOURCES
        assert "SEA" not in LICITACION_SOURCES

    def test_news_sources_not_in_licitacion(self):
        for src in NOTICIA_SOURCES:
            assert src not in LICITACION_SOURCES, f"{src} appears in both noticia and licitacion"
            assert src not in CONCESION_SOURCES
            assert src not in PROSPECTO_SOURCES

    def test_empleo_separate_from_news(self):
        for src in EMPLEO_SOURCES:
            assert src not in NOTICIA_SOURCES, f"{src} in empleo + noticia"

    def test_sources_in_consistent_with_dict(self):
        # sources_in("licitacion") debe ser la misma lista que extraer de CATEGORIES
        expected = [s for s, c in CATEGORIES.items() if c == "licitacion"]
        assert sorted(sources_in("licitacion")) == sorted(expected)
