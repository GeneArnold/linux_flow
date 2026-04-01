"""SQLite history store for transcriptions.

Stores every completed recording with its raw Whisper output, the
AI-enhanced final text, the enhancement mode, recording duration, and
whether the text was injected or just copied to clipboard.

DB file lives next to main.py as history.db — excluded from git via .gitignore
since it contains the user's personal dictation history.

Schema notes:
- raw_text: what Whisper returned verbatim
- final_text: what was actually injected/copied (may equal raw_text if mode=raw)
- mode: "raw" | "clean" | "rewrite"
- injected: 1 if xdotool successfully typed the text, 0 if clipboard fallback

All functions open and close a connection per call. SQLite handles this
fine for our low write frequency and avoids connection lifecycle issues.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "history.db"


# Ensure the table exists the moment this module is imported.
# This means the UI can query history before the engine has started.
def _ensure_init():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                raw_text   TEXT NOT NULL,
                final_text TEXT NOT NULL,
                mode       TEXT NOT NULL,
                duration_s REAL,
                injected   INTEGER NOT NULL DEFAULT 0
            )
        """)


_ensure_init()


def _conn() -> sqlite3.Connection:
    """Open a connection with row_factory=sqlite3.Row so rows act like dicts."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    """Create the history table if it doesn't exist.
    Safe to call multiple times — CREATE TABLE IF NOT EXISTS is idempotent.
    Called explicitly by the engine at startup and implicitly by all public
    functions below so the UI can query history before the engine starts.
    """
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                raw_text   TEXT NOT NULL,
                final_text TEXT NOT NULL,
                mode       TEXT NOT NULL,
                duration_s REAL,
                injected   INTEGER NOT NULL DEFAULT 0
            )
        """)


def save(
    raw_text: str,
    final_text: str,
    mode: str,
    duration_s: float | None = None,
    injected: bool = False,
) -> int:
    """Insert a new history entry and return its row ID."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO history (created_at, raw_text, final_text, mode, duration_s, injected) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                raw_text,
                final_text,
                mode,
                duration_s,
                1 if injected else 0,
            ),
        )
        return cur.lastrowid


def get_recent(limit: int = 50) -> list[dict]:
    """Return the most recent entries, newest first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(entry_id: int) -> dict | None:
    """Return a single entry by ID, or None if not found."""
    with _conn() as con:
        row = con.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
    return dict(row) if row else None


def delete(entry_id: int) -> None:
    """Delete a single history entry by ID."""
    with _conn() as con:
        con.execute("DELETE FROM history WHERE id = ?", (entry_id,))


def clear_all() -> None:
    """Delete all history entries. Used by the 'Clear All' button in the UI."""
    with _conn() as con:
        con.execute("DELETE FROM history")
