"""
Pocket Option headless browser authentication.
Logs into pocketoption.com via Playwright Chromium and returns the lo_uid
session cookie that the WebSocket client needs.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

PO_EMAIL    = os.environ.get("PO_EMAIL", "")
PO_PASSWORD = os.environ.get("PO_PASSWORD", "")


async def _login_async() -> Optional[str]:
    """Open a headless browser, log in to PO, and return the lo_uid cookie."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = await ctx.new_page()

            logger.info("PO headless login: navigating to login page...")
            await page.goto(
                "https://pocketoption.com/en/login/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            # Dismiss cookie/GDPR banner if present
            try:
                accept_btn = page.locator("button:has-text('Accept'), button:has-text('OK')")
                if await accept_btn.count() > 0:
                    await accept_btn.first.click(timeout=3_000)
            except Exception:
                pass

            # Fill credentials
            await page.wait_for_selector('input[type="email"]', timeout=15_000)
            await page.fill('input[type="email"]', PO_EMAIL)
            await page.fill('input[type="password"]', PO_PASSWORD)

            logger.info("PO headless login: submitting credentials...")
            await page.click('button[type="submit"]')

            # Wait up to 45s for the URL to leave the login page
            try:
                await page.wait_for_url(
                    lambda url: "login" not in url,
                    timeout=45_000,
                )
            except Exception:
                pass

            current_url = page.url
            logger.info(f"PO headless login: landed on {current_url}")

            # Save screenshot for debugging
            try:
                await page.screenshot(path="/tmp/po_login_debug.png", full_page=True)
                logger.info("Debug screenshot saved to /tmp/po_login_debug.png")
            except Exception:
                pass

            if "login" in current_url:
                logger.error("Still on login page — likely CAPTCHA or wrong credentials")

            # Extract lo_uid from all PO cookies
            cookies = await ctx.cookies("https://pocketoption.com")
            lo_uid = next(
                (c["value"] for c in cookies if c["name"] == "lo_uid"), None
            )

            await browser.close()

            if lo_uid:
                logger.info(f"PO session token obtained (…{lo_uid[-10:]})")
            else:
                logger.error("lo_uid cookie not found — login may have failed or CAPTCHA blocked")

            return lo_uid

    except Exception as exc:
        logger.error(f"PO headless login error: {exc}")
        return None


def get_po_session_token() -> Optional[str]:
    """
    Synchronous entry point.
    Runs the async login in a dedicated event loop so it can be called
    from synchronous startup code.
    """
    if not PO_EMAIL or not PO_PASSWORD:
        logger.warning("PO_EMAIL / PO_PASSWORD not set — skipping headless PO login")
        return None

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_login_async())
    finally:
        loop.close()
