"""Small persistent store for Trader ID display preferences."""

import sqlite3
import os
import hashlib
import time
from pathlib import Path

from timezone_utils import DEFAULT_TIMEZONE, normalize_timezone

DB_PATH = Path(os.environ.get(
    "TRADER_DB_PATH",
    str(Path(__file__).with_name("trader_preferences.sqlite3")),
))
SESSION_TTL_SECONDS = 120


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trader_preferences (
            trader_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trader_sessions (
            trader_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            last_seen REAL NOT NULL
        )
        """
    )
    return connection


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def claim_session(trader_id: str, token: str) -> bool:
    """Atomically claim the sole active session for a Trader ID."""
    now = time.time()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM trader_sessions WHERE last_seen < ?", (now - SESSION_TTL_SECONDS,))
        existing = connection.execute(
            "SELECT 1 FROM trader_sessions WHERE trader_id = ?", (trader_id.casefold(),)
        ).fetchone()
        if existing:
            return False
        connection.execute(
            "INSERT INTO trader_sessions (trader_id, token_hash, last_seen) VALUES (?, ?, ?)",
            (trader_id.casefold(), _token_hash(token), now),
        )
        return True


def touch_session(token: str) -> bool:
    now = time.time()
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE trader_sessions SET last_seen = ? WHERE token_hash = ? AND last_seen >= ?",
            (now, _token_hash(token), now - SESSION_TTL_SECONDS),
        )
        return cursor.rowcount == 1


def release_session(token: str) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM trader_sessions WHERE token_hash = ?", (_token_hash(token),))


def get_timezone(trader_id: str) -> str:
    with _connect() as connection:
        row = connection.execute(
            "SELECT timezone FROM trader_preferences WHERE trader_id = ?",
            (trader_id,),
        ).fetchone()
    return normalize_timezone(row[0] if row else DEFAULT_TIMEZONE)


def set_timezone(trader_id: str, timezone_name: str) -> str:
    timezone_name = normalize_timezone(timezone_name)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO trader_preferences (trader_id, timezone, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(trader_id) DO UPDATE SET
                timezone = excluded.timezone,
                updated_at = CURRENT_TIMESTAMP
            """,
            (trader_id, timezone_name),
        )
    return timezone_name
