"""
Telegram verification service.
Sends trader IDs to PocketPartners affiliate bot and parses the response.
Requires TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING env vars.
"""

import asyncio
import os
import logging
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger(__name__)

API_ID             = int(os.environ.get("TELEGRAM_API_ID", "0") or "0")
API_HASH           = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING     = os.environ.get("TELEGRAM_SESSION_STRING", "")
PO_BOT_USERNAME    = "AffiliatePocketBot"

# When True, login is blocked instead of bypassed if Telegram is not configured.
_REQUIRE_VERIFICATION = os.environ.get("REQUIRE_VERIFICATION", "false").lower() == "true"

_client = None
_lock   = asyncio.Lock()


async def _get_client():
    global _client

    if not (API_ID and API_HASH and SESSION_STRING):
        return None

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if _client is None or not _client.is_connected():
            # connection_retries/timeout kept low (default is 5 retries x 10s
            # timeout, ~55s worst case) so a blocked/unreachable Telegram
            # fails within the reverse proxy's read timeout instead of the
            # request getting cut off with a 504 before this ever returns.
            _client = TelegramClient(
                StringSession(SESSION_STRING), API_ID, API_HASH,
                connection_retries=1, timeout=5,
            )
            await _client.connect()
            if not await _client.is_user_authorized():
                logger.error("Telegram session not authorized")
                _client = None
            else:
                logger.info("Telegram client connected")
    except Exception as e:
        logger.error(f"Telegram client init failed: {e}")
        _client = None

    return _client


def _parse_reply(text: str) -> Dict:
    """Parse PocketPartners bot response. Requires UID present and Sum of deposits > $50."""
    import re

    if not text:
        return {"found": False, "message": "NO RESPONSE FROM BOT"}

    if "user not found" in text.lower():
        return {"found": False, "message": "TRADER NOT FOUND"}

    if "uid:" not in text.lower():
        return {"found": False, "message": "UNRECOGNISED RESPONSE"}

    # Enforce minimum $45 in total deposits
    match = re.search(r'sum of deposits\s*:\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if match:
        total_deposits = float(match.group(1).replace(',', ''))
        if total_deposits < 45:
            return {
                "found":   False,
                "message": f"ACCESS DENIED — MINIMUM $45 DEPOSIT REQUIRED (yours: ${total_deposits:.2f})"
            }
    else:
        return {"found": False, "message": "COULD NOT VERIFY DEPOSIT HISTORY"}

    return {"found": True, "message": "TRADER VERIFIED"}


async def verify_trader(trader_id: str) -> Dict:
    """
    Send trader_id to PocketPartners bot and return verification result.
    Handles the bot's anti-robot captcha challenge automatically.
    Falls back to allowing login if Telegram is not configured.
    """
    if not _REQUIRE_VERIFICATION:
        logger.warning("REQUIRE_VERIFICATION=false — login bypass active")
        return {"found": True, "bypassed": True}

    client = await _get_client()

    if client is None:
        if _REQUIRE_VERIFICATION:
            logger.warning("Telegram not configured but REQUIRE_VERIFICATION=true — denying login")
            return {"found": False, "message": "VERIFICATION SERVICE NOT CONFIGURED — CONTACT ADMIN"}
        logger.warning("Telegram not configured — login bypass active")
        return {"found": True, "bypassed": True}

    async with _lock:
        try:
            async with client.conversation(PO_BOT_USERNAME, timeout=30) as conv:
                await conv.send_message(str(trader_id))
                reply = await conv.get_response(timeout=15)
                raw = reply.message or ""
                logger.info(f"Bot reply 1: {repr(raw[:200])}")

                # Handle anti-robot captcha challenge
                if "robot" in raw.lower() or "confirm" in raw.lower():
                    logger.info("Captcha challenge detected — clicking verify button")

                    # Click the first available inline button
                    try:
                        if reply.buttons:
                            await reply.click(0, 0)
                            logger.info("Captcha button clicked")
                        else:
                            logger.warning("No buttons on captcha message")
                    except Exception as click_err:
                        logger.warning(f"Button click failed: {click_err}")

                    # Wait for post-click response (may be confirmation or data)
                    try:
                        next_reply = await conv.get_response(timeout=10)
                        next_raw = next_reply.message or ""
                        logger.info(f"Post-captcha reply: {repr(next_raw[:200])}")

                        if "uid:" in next_raw.lower():
                            # Bot already sent the data after captcha click
                            raw = next_raw
                        else:
                            # Captcha passed but need to re-send the query
                            await asyncio.sleep(1)
                            await conv.send_message(str(trader_id))
                            final_reply = await conv.get_response(timeout=15)
                            raw = final_reply.message or ""
                            logger.info(f"Bot final reply: {repr(raw[:200])}")

                    except asyncio.TimeoutError:
                        # No response after click — re-send trader ID
                        logger.info("No post-click response, re-sending trader ID")
                        await conv.send_message(str(trader_id))
                        final_reply = await conv.get_response(timeout=15)
                        raw = final_reply.message or ""
                        logger.info(f"Bot final reply: {repr(raw[:200])}")

                result = _parse_reply(raw)
                logger.info(
                    f"Trader {trader_id} verification: "
                    f"{'FOUND' if result['found'] else 'NOT FOUND'}"
                )
                return result

        except asyncio.TimeoutError:
            logger.error("Telegram bot timed out")
            return {"found": False, "message": "VERIFICATION TIMEOUT — TRY AGAIN"}
        except Exception as e:
            logger.error(f"Telegram verification error: {e}")
            return {"found": False, "message": "VERIFICATION SERVICE UNAVAILABLE"}
