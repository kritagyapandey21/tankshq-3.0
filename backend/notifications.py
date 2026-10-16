"""Daily "time to trade" notifications.

* Web Push (browser notifications) for traders who opt in on the member hub.
* The same daily message is served to the website (GET /notifications/today) for the in-app banner.

Settings (all optional, via .env):
    NOTIFY_TIME          local time to send, HH:MM          (default 10:00)
    NOTIFY_TZ            time zone for NOTIFY_TIME          (default Asia/Kolkata)
    VAPID_PRIVATE_KEY    PEM text; if unset a key pair is generated once and saved next to the database
    VAPID_PUBLIC_KEY     base64url public key matching the private key
    VAPID_SUBJECT        mailto: or https: contact for push services (default mailto:admin@example.com)
"""

import asyncio
import base64
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from trader_store import DB_PATH
from timezone_utils import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

NOTIFY_TIME = os.environ.get("NOTIFY_TIME", "10:00").strip()
NOTIFY_TZ = os.environ.get("NOTIFY_TZ", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com").strip()
SEND_WINDOW_HOURS = 3        # if the server was down at NOTIFY_TIME, still send for up to this long afterwards
SITE_URL_PATH = "/hub"  # where a tap on the notification lands

# Short, encouraging, and honest: discipline and risk control, never promises of profit.
MESSAGES: List[str] = [
    "A new trading day is open. Show up, follow your plan, and let the setup come to you.",
    "Consistency beats intensity. One disciplined session today is worth more than a lucky streak.",
    "Check TANIX AI 3.0 today. Take only the signals you can enter on time, and skip the rest.",
    "Protect your capital first. Profits are the reward for staying in the game.",
    "Small stakes, clear rules, calm mind. That is how traders last.",
    "Today's goal is not to win big. It is to follow your rules from the first trade to the last.",
    "Great traders are patient. Wait for the signal, take it, and walk away from the screen.",
    "Set your stake and your daily loss limit before the first trade. Then honour them.",
    "Every expert was once a beginner who kept showing up. Open the terminal and do today's work.",
    "Losses are tuition, not failure, as long as you keep the same stake and learn from each one.",
    "Your edge is discipline. Let the system do the thinking and you do the executing.",
    "Don't chase. If you miss an entry, the next signal is only minutes away.",
    "A calm trader is a profitable trader. Breathe, check the signal, and enter at the exact time.",
    "Progress is built daily. Review yesterday, plan today, execute with focus.",
    "Stick to your daily trade count. Quality setups beat quantity every time.",
    "Hit your target or your limit? Close the platform. Ending a good session on time is a skill.",
    "The market will be here tomorrow. Your capital must be too. Trade smart today.",
    "Wins build confidence, discipline builds a career. Stay on your plan today.",
    "Start the day with the Telegram channel, then the terminal, then your rules. In that order.",
    "Fear and greed are the real opponents. Rules and risk limits are how you beat them.",
    "Focus on the process: right stake, right time, right signal. Results follow the process.",
    "A tracked trade is a lesson. Log your results today and see your own pattern.",
    "You do not need to catch every move. You need to protect your balance and catch the right ones.",
    "Treat trading like a business: a plan, a budget, a routine. Today is another day to run it well.",
    "Don't trade to win back a loss. Trade the next signal on its own merits.",
    "Be patient with the plan and strict with the risk. That combination compounds.",
    "Your future self will thank you for the discipline you show today.",
    "Review your money management rules before the first trade. Two minutes now saves a bad hour later.",
    "Show up ready, stay in control, and finish the day with your rules intact.",
    "Trading carries real risk. Only trade money you can afford to lose, and keep your stake small.",
    "Today is a fresh page. Open the terminal, wait for a clean signal, and trade with a clear head.",
]


# --------------------------------------------------------------------- storage
def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute(
        """CREATE TABLE IF NOT EXISTS push_subscriptions (
               endpoint TEXT PRIMARY KEY,
               trader_id TEXT NOT NULL,
               p256dh TEXT NOT NULL,
               auth TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    con.execute("CREATE TABLE IF NOT EXISTS notify_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return con


def save_subscription(trader_id: str, endpoint: str, p256dh: str, auth: str) -> None:
    with _connect() as con:
        con.execute(
            """INSERT INTO push_subscriptions (endpoint, trader_id, p256dh, auth)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(endpoint) DO UPDATE SET
                   trader_id = excluded.trader_id, p256dh = excluded.p256dh, auth = excluded.auth""",
            (endpoint, trader_id.casefold(), p256dh, auth),
        )


def remove_subscription(endpoint: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


def list_subscriptions() -> List[Dict[str, str]]:
    with _connect() as con:
        rows = con.execute("SELECT endpoint, trader_id, p256dh, auth FROM push_subscriptions").fetchall()
    return [{"endpoint": r[0], "trader_id": r[1], "p256dh": r[2], "auth": r[3]} for r in rows]


def _get_state(key: str) -> Optional[str]:
    with _connect() as con:
        row = con.execute("SELECT value FROM notify_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_state(key: str, value: str) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO notify_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# --------------------------------------------------------------------- VAPID keys
_vapid = None
_public_key_b64: Optional[str] = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _load_vapid():
    """Return (Vapid instance, public key base64url). Generated once and persisted if not configured."""
    global _vapid, _public_key_b64
    if _vapid is not None:
        return _vapid, _public_key_b64

    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization

    pem = os.environ.get("VAPID_PRIVATE_KEY", "").strip().replace("\\n", "\n")
    key_file = Path(DB_PATH).with_name("vapid_keys.json")
    if not pem and key_file.exists():
        pem = json.loads(key_file.read_text(encoding="utf-8")).get("private_pem", "")
    if pem:
        vapid = Vapid.from_pem(pem.encode())
    else:
        vapid = Vapid()
        vapid.generate_keys()
        pem = vapid.private_pem().decode()
        key_file.write_text(json.dumps({"private_pem": pem}), encoding="utf-8")
        logger.info("Generated new VAPID key pair at %s", key_file)

    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    _vapid, _public_key_b64 = vapid, _b64url(public)
    return _vapid, _public_key_b64


def public_key() -> str:
    return _load_vapid()[1]


# --------------------------------------------------------------------- messages
def message_for(day) -> Dict[str, str]:
    """Deterministic message for a calendar date, so every trader sees the same one that day."""
    body = MESSAGES[day.toordinal() % len(MESSAGES)]
    return {"title": "Time to trade, Trader", "body": body, "url": SITE_URL_PATH}


def today_local() -> datetime:
    return datetime.now(ZoneInfo(NOTIFY_TZ))


def todays_message() -> Dict[str, str]:
    return message_for(today_local().date())


# --------------------------------------------------------------------- sending
def _send_one(sub: Dict[str, str], payload: str) -> str:
    """Blocking. Returns 'ok', 'gone' (subscription is dead) or 'error'."""
    from pywebpush import webpush, WebPushException

    vapid, _ = _load_vapid()
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=payload,
            vapid_private_key=vapid,
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=6 * 3600,
        )
        return "ok"
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return "gone"
        logger.warning("Push failed (%s): %s", status, str(exc)[:160])
        return "error"
    except Exception as exc:  # network problems etc.
        logger.warning("Push failed: %s", str(exc)[:160])
        return "error"


async def send_to_all(message: Optional[Dict[str, str]] = None) -> Dict[str, int]:
    message = message or todays_message()
    payload = json.dumps(message)
    result = {"sent": 0, "removed": 0, "failed": 0}
    for sub in list_subscriptions():
        outcome = await asyncio.to_thread(_send_one, sub, payload)
        if outcome == "ok":
            result["sent"] += 1
        elif outcome == "gone":
            remove_subscription(sub["endpoint"])
            result["removed"] += 1
        else:
            result["failed"] += 1
    logger.info("Daily notification: %s", result)
    return result


def _due(now: datetime) -> bool:
    """True when it is past NOTIFY_TIME today (but not by more than SEND_WINDOW_HOURS)."""
    try:
        hh, mm = (int(x) for x in NOTIFY_TIME.split(":"))
    except ValueError:
        hh, mm = 10, 0
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return target <= now <= target + timedelta(hours=SEND_WINDOW_HOURS)


async def daily_loop() -> None:
    """Background task: send the day's notification once, shortly after NOTIFY_TIME."""
    logger.info("Daily notifications scheduled for %s (%s)", NOTIFY_TIME, NOTIFY_TZ)
    while True:
        try:
            now = today_local()
            today = now.date().isoformat()
            if _due(now) and _get_state("last_sent_date") != today:
                _set_state("last_sent_date", today)   # mark first so a slow send can't repeat
                await send_to_all(message_for(now.date()))
        except Exception as exc:
            logger.error("Daily notification loop error: %s", exc)
        await asyncio.sleep(30)
