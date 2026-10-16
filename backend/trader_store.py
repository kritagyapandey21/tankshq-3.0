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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS replaced_sessions (
            token_hash TEXT PRIMARY KEY,
            replaced_at REAL NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trader_flags (
            trader_id TEXT PRIMARY KEY,
            telegram_joined INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def claim_session(trader_id: str, token: str) -> bool:
    """Make `token` the sole active session for a Trader ID.

    The newest login wins: any older session for the same Trader ID is ended, and remembered as
    "replaced" so that browser can be told why it was signed out. Returns True if an older, still
    active session was replaced.
    """
    now = time.time()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM trader_sessions WHERE last_seen < ?", (now - SESSION_TTL_SECONDS,))
        connection.execute("DELETE FROM replaced_sessions WHERE replaced_at < ?", (now - 86400,))
        old = connection.execute(
            "SELECT token_hash FROM trader_sessions WHERE trader_id = ?", (trader_id.casefold(),)
        ).fetchone()
        if old:
            connection.execute("INSERT OR REPLACE INTO replaced_sessions (token_hash, replaced_at) VALUES (?, ?)", (old[0], now))
            connection.execute("DELETE FROM trader_sessions WHERE trader_id = ?", (trader_id.casefold(),))
        connection.execute(
            "INSERT INTO trader_sessions (trader_id, token_hash, last_seen) VALUES (?, ?, ?)",
            (trader_id.casefold(), _token_hash(token), now),
        )
        return bool(old)


def was_replaced(token: str) -> bool:
    """True if this token's session was ended because the same Trader ID logged in elsewhere."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM replaced_sessions WHERE token_hash = ?", (_token_hash(token),)
        ).fetchone()
    return bool(row)


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


def trader_for_token(token: str) -> str | None:
    """Trader ID that owns an active session token (lower-cased), or None."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT trader_id FROM trader_sessions WHERE token_hash = ?", (_token_hash(token),)
        ).fetchone()
    return row[0] if row else None


def get_telegram_joined(trader_id: str) -> bool:
    with _connect() as connection:
        row = connection.execute(
            "SELECT telegram_joined FROM trader_flags WHERE trader_id = ?", (trader_id.casefold(),)
        ).fetchone()
    return bool(row and row[0])


def set_telegram_joined(trader_id: str) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO trader_flags (trader_id, telegram_joined, updated_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(trader_id) DO UPDATE SET
                telegram_joined = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (trader_id.casefold(),),
        )
