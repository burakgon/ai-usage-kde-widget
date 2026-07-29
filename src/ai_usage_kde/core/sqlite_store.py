from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteStateStore:
    """Read and compare-and-swap VS Code-compatible state databases."""

    def read(self, path: Path, key: str) -> Optional[str]:
        if not path.is_file():
            return None
        try:
            uri = f"{path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2) as connection:
                row = connection.execute(
                    "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
                    (key,),
                ).fetchone()
        except (OSError, sqlite3.Error):
            return None
        if not row or not isinstance(row[0], str):
            return None
        value = row[0].strip()
        return value or None

    def compare_and_swap(
        self,
        path: Path,
        key: str,
        *,
        expected: Optional[str],
        value: str,
    ) -> bool:
        if not path.is_file():
            return False
        try:
            with sqlite3.connect(path, timeout=5) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
                    (key,),
                ).fetchone()
                current = row[0] if row and isinstance(row[0], str) else None
                if current != expected:
                    connection.rollback()
                    return False
                connection.execute(
                    "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                    (key, value),
                )
                connection.commit()
            return True
        except (OSError, sqlite3.Error):
            return False
