"""
tests/test_news_projects.py — Tests del extractor de hitos y proyectos desde noticias.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from signals.news_projects import is_title_similar, clean_json_text, run


def test_is_title_similar():
    # Coincidencia alta por Chuquicamata y Subterránea
    assert is_title_similar("Chuquicamata Subterránea", "Chuquicamata desarrollo subterráneo") is True
    # Sin suficiente solapamiento de palabras significativas
    assert is_title_similar("Planta Desaladora Escondida", "Desaladora Spence") is False
    # Solapamiento parcial aceptable
    assert is_title_similar("Cobre en Quebrada Blanca", "Mina Quebrada Blanca de Teck") is True


def test_clean_json_text():
    assert clean_json_text("```json\n{\"test\": true}\n```") == '{"test": true}'
    assert clean_json_text("{\"test\": true}") == '{"test": true}'


@patch("db.get_conn")
@patch("ai_client.call_llm")
def test_news_projects_run_enrichment(mock_call_llm, mock_get_conn):
    # Mock de noticia no procesada
    mock_news = [
        {
            "id": 101,
            "source": "Portal Minero",
            "title": "Codelco iniciará construcción de Chuquicamata Subterránea",
            "url": "https://portalminero.com/news1",
            "company": "Codelco",
            "region": "Antofagasta",
            "published_at": datetime(2026, 7, 7, tzinfo=timezone.utc),
            "created_at": datetime(2026, 7, 7, tzinfo=timezone.utc),
            "entry": "Proyecto de expansión minera subterránea",
            "raw": {}
        }
    ]
    # Proyecto existente candidato a match
    mock_candidates = [
        {
            "id": 201,
            "title": "Chuquicamata Subterránea",
            "company": "Codelco",
            "region": "Antofagasta",
            "raw": {"signals": []},
            "score": 80,
            "signal_score": 10
        }
    ]

    mock_cursor = MagicMock()
    # fetchall retorna:
    # 1. Lista de noticias
    # 2. Lista de proyectos candidatos
    mock_cursor.fetchall.side_effect = [mock_news, mock_candidates]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    # Mock respuesta del LLM
    mock_call_llm.return_value = """
    {
      "is_project_related": true,
      "project_name": "Chuquicamata Subterránea",
      "company": "Codelco",
      "region": "Antofagasta",
      "phase": "Construcción",
      "milestone_text": "Iniciaron obras civiles del nuevo nivel de ventilación."
    }
    """

    # Ejecutar
    result = run(force_recompute=True, limit=1)

    assert result["processed"] == 1
    assert result["enriched"] == 1
    assert result["created"] == 0

    # Se debió llamar a execute para actualizar el proyecto y la noticia
    assert mock_cursor.execute.call_count >= 2


@patch("db.get_conn")
@patch("ai_client.call_llm")
def test_news_projects_run_creation(mock_call_llm, mock_get_conn):
    # Mock de noticia no procesada
    mock_news = [
        {
            "id": 102,
            "source": "Minería Chilena",
            "title": "Nuevo rajo minero en Atacama por Compañía Random",
            "url": "https://mch.cl/news2",
            "company": "Compañía Random",
            "region": "Atacama",
            "published_at": datetime(2026, 7, 7, tzinfo=timezone.utc),
            "created_at": datetime(2026, 7, 7, tzinfo=timezone.utc),
            "entry": "Una nueva iniciativa de explotación minera.",
            "raw": {}
        }
    ]
    # No hay proyectos candidatos (retorna lista vacía)
    mock_candidates = []

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": 999}
    mock_cursor.fetchall.side_effect = [mock_news, mock_candidates]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    # Mock respuesta del LLM
    mock_call_llm.return_value = """
    {
      "is_project_related": true,
      "project_name": "Rajo Minero Atacama",
      "company": "Compañía Random",
      "region": "Atacama",
      "phase": "Construcción",
      "milestone_text": "Iniciaron obras civiles del nuevo rajo."
    }
    """

    # Ejecutar
    result = run(force_recompute=True, limit=1)

    assert result["processed"] == 1
    assert result["enriched"] == 0
    assert result["created"] == 1

    assert mock_cursor.execute.call_count >= 2
