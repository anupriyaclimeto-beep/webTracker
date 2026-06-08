"""
force_logout.py — Force logout from CPCB EPR Plastic portal
Opens the browser with the saved profile and hits the logout URL to
clear the server-side session so a fresh login can be done.
"""
import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROFILE_DIR  = Path("browser_profiles/EPR_PLASTIC").resolve()
LOGOUT_URL   = "https://eprplastic.cpcb.gov.in/#/plastic/logout"
LOGIN_URL    = "https://eprplastic.cpcb.gov.in/#/plastic/login"
HOME_URL     = "https://eprplastic.cpcb.gov.in/#/plastic/home"

async def force_logout():
    logger.info("Opening browser with saved profile: %s", PROFILE_DIR)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            ignore_https_errors=True,
        )

        page = await ctx.new_page()

        # Step 1: Try direct logout URL
        logger.info("Navigating to logout URL: %s", LOGOUT_URL)
        try:
            await page.goto(LOGOUT_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning("Logout URL navigation error: %s", e)

        current_url = page.url
        logger.info("After logout URL, current page: %s", current_url)

        # Step 2: Look for a Logout button on the page and click it
        logout_selectors = [
            "button:has-text('Logout')",
            "a:has-text('Logout')",
            "button:has-text('Log Out')",
            "a:has-text('Log Out')",
            "button:has-text('Sign Out')",
            "a:has-text('Sign Out')",
            "[class*='logout']",
        ]

        logged_out = False
        for sel in logout_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    logger.info("Clicking logout button: %s", sel)
                    await el.click()
                    await asyncio.sleep(3)
                    logged_out = True
                    break
            except Exception:
                continue

        if not logged_out:
            logger.info("No logout button found — navigating to home then checking session")
            try:
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
            except Exception:
                pass

        final_url = page.url
        logger.info("Final URL: %s", final_url)

        if "login" in final_url.lower():
            logger.info("SUCCESS — Logged out! Browser is now on login page.")
            logger.info("You can now run the crawler to log in fresh.")
        else:
            logger.info("Session may still be active. Current URL: %s", final_url)
            logger.info("You can manually click Logout in the browser window that just opened.")
            logger.info("Keeping browser open for 60 seconds so you can do it manually...")
            await asyncio.sleep(60)

        await ctx.close()
        logger.info("Browser closed.")

if __name__ == "__main__":
    asyncio.run(force_logout())
