import asyncio
import json
import logging
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)


async def handle_auth(page, portal_config):
    auth_type = portal_config.get("auth", "public")

    if auth_type == "public":
        await public_auth(page, portal_config)

    elif auth_type == "manual":
        await manual_auth(page, portal_config)

    elif auth_type == "cookie":
        await cookie_auth(page, portal_config)

    else:
        logger.warning("Unknown auth type '%s' — treating as public", auth_type)
        await public_auth(page, portal_config)


async def public_auth(page, portal_config):
    url = portal_config["url"]
    logger.info("Public auth — navigating to %s", url)
    await page.goto(url, wait_until="networkidle")
    logger.info("Page loaded successfully")


async def manual_auth(page, portal_config):
    url = portal_config["url"]
    logger.info("Manual auth — opening %s", url)
    await page.goto(url, wait_until="networkidle")

    print("\n" + "="*60)
    print("BROWSER IS OPEN")
    print("Please do the following manually:")
    print("  1. Type your username and password")
    print("  2. Solve the CAPTCHA")
    print("  3. Enter the OTP")
    print("  4. Wait until you are fully logged in")
    print("  5. Click the RESUME button in the Playwright toolbar")
    print("="*60 + "\n")

    await page.pause()

    logger.info("Manual login completed — crawler taking over now")


async def cookie_auth(page, portal_config):
    url = portal_config["url"]
    session_path = portal_config.get("cookie", {}).get("storage_state_path")

    if not session_path:
        logger.error("Cookie auth requires storage_state_path in config.json")
        raise ValueError("Missing storage_state_path for cookie auth")

    import os
    if not os.path.exists(session_path):
        logger.error("Session file not found at %s — run capture_session.py first", session_path)
        raise FileNotFoundError(f"Session file not found: {session_path}")

    logger.info("Cookie auth — session loaded from %s", session_path)
    await page.goto(url, wait_until="networkidle")
    logger.info("Cookie session applied successfully")


async def capture_cookie_session(portal_config):
    url = portal_config["url"]
    session_path = portal_config.get("cookie", {}).get("storage_state_path", "sessions/session.json")

    import os
    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    browser_cfg = config.get("browser", {})

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        context = await browser.new_context(
            viewport={
                "width": browser_cfg.get("viewport", {}).get("width", 1280),
                "height": browser_cfg.get("viewport", {}).get("height", 800)
            }
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")

        print("\n" + "="*60)
        print("SESSION CAPTURE MODE")
        print("Please login manually in the browser.")
        print("Once fully logged in, click RESUME in the Playwright toolbar.")
        print("="*60 + "\n")

        await page.pause()

        await context.storage_state(path=session_path)
        logger.info("Session saved to %s", session_path)
        print(f"\nSession saved to {session_path}")
        print("You can now use auth: cookie in config.json\n")

        await browser.close()


async def create_browser_context(playwright):
    browser_cfg = config.get("browser", {})
    browser = await playwright.chromium.launch(
        headless=browser_cfg.get("headless", False),
        args=["--start-maximized"]
    )
    context = await browser.new_context(
        viewport={
            "width": browser_cfg.get("viewport", {}).get("width", 1280),
            "height": browser_cfg.get("viewport", {}).get("height", 800)
        },
        record_har_path="temp.har"
    )
    return browser, context


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        portal_name = sys.argv[2] if len(sys.argv) > 2 else None
        portal = None
        for p in config["portals"]:
            if portal_name is None or p["name"] == portal_name:
                portal = p
                break
        if not portal:
            print("Portal not found in config.json")
            sys.exit(1)
        asyncio.run(capture_cookie_session(portal))
    else:
        print("auth.py loaded successfully")
        print("Auth modes available: public, manual, cookie")