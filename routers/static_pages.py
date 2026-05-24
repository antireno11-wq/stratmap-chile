"""Rutas explícitas para páginas HTML.

Necesarias porque app.mount("/", StaticFiles(html=True)) sirve archivos
con extensión, pero algunas referencias internas usan rutas explícitas.
"""
import os as _os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(include_in_schema=False)


def _serve(filename: str):
    path = _os.path.join("static", filename)
    if _os.path.exists(path):
        return FileResponse(path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@router.get("/mandantes.html")
def serve_mandantes():
    return _serve("mandantes.html")


@router.get("/mandante.html")
def serve_mandante():
    return _serve("mandante.html")


@router.get("/mapa.html")
def serve_mapa():
    return _serve("mapa.html")


@router.get("/kanban.html")
def serve_kanban():
    return _serve("kanban.html")


@router.get("/preferences.html")
def serve_preferences():
    return _serve("preferences.html")


@router.get("/health.html")
def serve_health():
    return _serve("health.html")
