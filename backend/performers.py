"""Best performers (the winners podium), editable from the admin page.

Stored in the same SQLite database as everything else. Photos are uploaded to an `uploads/` folder next to
the database. If nothing has been saved yet, the website falls back to the list in frontend/config.js.
"""

import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from trader_store import DB_PATH

UPLOAD_DIR = Path(DB_PATH).with_name("uploads")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_PERFORMERS = 3

_PHOTO_UPLOAD = re.compile(r"^/uploads/[a-f0-9]{32}\.(jpg|png|webp)$")
_PHOTO_ASSET = re.compile(r"^assets/[A-Za-z0-9._/-]{1,120}$")
_NAME_FILE = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp)$")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute("CREATE TABLE IF NOT EXISTS site_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return con


# --------------------------------------------------------------------- validation
def clean_handle(raw: str) -> str:
    handle = (raw or "").strip().lstrip("@").strip()
    if not 1 <= len(handle) <= 30 or not re.fullmatch(r"[A-Za-z0-9_.\-]+", handle):
        raise ValueError("Handle must be 1-30 characters: letters, numbers, _ . -")
    return "@" + handle


def clean_photo(raw: Optional[str]) -> str:
    photo = (raw or "").strip()
    if not photo:
        return ""
    if _PHOTO_UPLOAD.match(photo) or _PHOTO_ASSET.match(photo):
        return photo
    if photo.startswith("https://") and len(photo) <= 300 and " " not in photo:
        return photo
    raise ValueError("Photo must be an uploaded image or an https link")


def clean_month(raw: str) -> str:
    month = (raw or "").strip()
    if not 1 <= len(month) <= 30 or not re.fullmatch(r"[A-Za-z0-9 ,.\-']+", month):
        raise ValueError("Period label must be 1-30 characters, e.g. 'Last Month'")
    return month


# --------------------------------------------------------------------- read / write
def get() -> Optional[Dict]:
    with _connect() as con:
        row = con.execute("SELECT value FROM site_settings WHERE key = 'performers'").fetchone()
    return json.loads(row[0]) if row else None


def save(month: str, items: List[Dict]) -> Dict:
    if not 1 <= len(items) <= MAX_PERFORMERS:
        raise ValueError(f"Add between 1 and {MAX_PERFORMERS} performers")
    performers = []
    for item in items:
        roi = float(item["roi"])
        if not 0 <= roi <= 100000:
            raise ValueError("ROI must be between 0 and 100000")
        performers.append({
            "handle": clean_handle(item["handle"]),
            "roi": round(roi, 1),
            "photo": clean_photo(item.get("photo")),
        })
    data = {
        "month": clean_month(month),
        "performers": sorted(performers, key=lambda p: p["roi"], reverse=True),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _connect() as con:
        con.execute(
            "INSERT INTO site_settings (key, value) VALUES ('performers', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(data),),
        )
    prune_uploads(data)
    return data


# --------------------------------------------------------------------- photo uploads
def sniff_image(data: bytes) -> Optional[str]:
    """Extension for a real JPEG/PNG/WebP file (checked by content, not by name), else None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_upload(data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Photo is too large (max 2 MB)")
    ext = sniff_image(data)
    if not ext:
        raise ValueError("Photo must be a JPG, PNG or WebP image")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"/uploads/{name}"


def upload_path(name: str) -> Optional[Path]:
    if not _NAME_FILE.match(name):
        return None
    path = UPLOAD_DIR / name
    return path if path.is_file() else None


def prune_uploads(current: Dict) -> None:
    """Delete uploaded photos that are no longer used and are over a day old."""
    if not UPLOAD_DIR.exists():
        return
    used = {Path(p["photo"]).name for p in current["performers"] if p["photo"].startswith("/uploads/")}
    cutoff = datetime.now().timestamp() - 86400
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.name not in used and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
