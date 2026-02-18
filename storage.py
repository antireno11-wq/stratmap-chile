import os
import sqlite3
from typing import Any, Dict, List

DB_PATH = os.getenv("DB_PATH", "./data/stratmap.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        con.commit()


def insert_item(title: str, url: str, source: str) -> None:
    init_db()
    with _conn() as con:
        con.execute(
            "INSERT INTO items(title, url, source, created_at) VALUES (?, ?, ?, datetime('now'))",
            (title, url, source),
        )
        con.commit()


def list_items(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as con:
        cur = con.execute(
            "SELECT title, url, source, created_at FROM items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for title, url, source, created_at in rows:
        out.append(
            {"title": title, "url": url, "source": source, "created_at": created_at}
        )
    return out
