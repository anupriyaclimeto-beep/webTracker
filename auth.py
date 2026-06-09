"""
auth.py — Authentication helpers for CPCB EPR Portal Crawler

Auth modes:
  public     → just navigate, no login needed
  none       → alias for public
  manual     → open browser headful, pause for user (legacy Playwright toolbar)
  cookie     → restore from saved storage_state JSON
  persistent → NEW: Playwright persistent context with auto-saved browser profile
               - First run: headful browser opens, user logs in manually
               - Subsequent runs: session restored from disk, no interaction needed
               - Session expired: headful browser re-opens automatically

Flag files (same pattern as .crawler.pid / .crawler.log):
  .login_needed  → written when waiting for manual login, deleted on success
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

# ── Flag file path (same dir as .crawler.pid) ─────────────────────────────────
IS_CLOUD   = os.getenv("STREAMLIT_SHARING_MODE") is not None or os.path.exists("/mount/src")
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__)) or "."
LOGIN_FLAG = "/tmp/.login_needed" if IS_CLOUD else os.path.join(_BASE_DIR, ".login_needed")


# ══════════════════════════════════════════════════════════════════════════════
# Public helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_profile_dir(portal_config: dict) -> Path:
    """Return the persistent profile directory for this portal."""
    profile_dir = portal_config.get(
        "browser_profile_dir",
        f"browser_profiles/{portal_config['name'].replace(' ', '_')}"
    )
    if not os.path.isabs(profile_dir):
        profile_dir = os.path.abspath(os.path.join(_BASE_DIR, profile_dir))
    path = Path(profile_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path



async def save_context_cookies(context: BrowserContext, portal_config: dict) -> None:
    """Save session cookies to cookies.json in the portal profile directory."""
    try:
        cookies = await context.cookies()
        profile_dir = get_profile_dir(portal_config)
        cookies_path = profile_dir / "cookies.json"
        cookies_path.write_text(json.dumps(cookies, indent=2))
        logger.info("Session cookies saved to %s", cookies_path)
    except Exception as e:
        logger.warning("Failed to save cookies: %s", e)



async def monitor_browser(context: BrowserContext, closed_event: asyncio.Event) -> None:
    """Monitor the persistent browser context. If the user closes all pages (or the context), set the closed_event.
    This is used early in crawl_portal to abort if the browser is closed before navigation.
    """
    while not closed_event.is_set():
        try:
            # If there are no open pages, assume the user closed the browser.
            open_pages = [p for p in context.pages if not p.is_closed()]
            if not open_pages:
                closed_event.set()
                logger.info("User closed the persistent browser before navigation.")
                break
        except Exception as e:
            logger.warning("Error while monitoring browser context: %s", e)
        await asyncio.sleep(1)


async def wait_for_user_to_close(context: BrowserContext) -> None:
    """Wait until the user manually closes all browser pages, then close the context.
    Called after all post-login pages have been crawled, so the user can review
    the browser before it shuts down. Session cookies are saved BEFORE this call.
    """
    logger.info("=" * 60)
    logger.info("CRAWL COMPLETE — Browser will stay open until you close it.")
    logger.info("You can review the browser, then close it manually.")
    logger.info("Session is already saved. Safe to close anytime.")
    logger.info("=" * 60)
    while True:
        try:
            open_pages = [p for p in context.pages if not p.is_closed()]
            if not open_pages:
                break
        except Exception:
            break
        await asyncio.sleep(2)
    try:
        await context.close()
    except Exception:
        pass
    logger.info("User closed the browser; context closed.")


def profile_exists(portal_config: dict) -> bool:
    """True if a browser profile folder exists and has content (not first run)."""
    path = get_profile_dir(portal_config)
    # Chromium writes a 'Default' folder inside the profile dir on first run
    return (path / "Default").exists() or any(path.iterdir())


def _write_login_flag():
    try:
        Path(LOGIN_FLAG).write_text("1")
    except Exception:
        pass


def _delete_login_flag():
    try:
        if os.path.exists(LOGIN_FLAG):
            os.remove(LOGIN_FLAG)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Session validation
# ══════════════════════════════════════════════════════════════════════════════

async def is_logged_in(page: Page, portal_config: dict) -> bool:
    """
    Navigate to a post-login page and check for a post-login DOM element.
    Returns True if the session is still valid.
    """
    selector = portal_config.get("login_success_selector", "")
    portal_home_url = portal_config.get("url", "")
    login_url       = portal_config.get("login_url", "")

    # Use explicit session_check_url if given, else use first post-login page,
    # else fall back to portal home. Avoids using public pages as session check.
    session_check_url = portal_config.get("session_check_url", "")
    post_login_pages  = portal_config.get("post_login_pages", [])
    if session_check_url:
        dashboard_url = session_check_url
    elif post_login_pages:
        dashboard_url = post_login_pages[0]["url"]
    else:
        dashboard_url = portal_home_url

    if not selector:
        logger.warning("No login_success_selector configured — assuming logged in")
        return True

    try:
        await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Try every comma-separated selector
        for sel in [s.strip() for s in selector.split(",")]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=4000):
                    logger.info("SESSION VALID — selector matched: %s", sel)
                    return True
            except Exception:
                continue

        # Secondary check: URL is NOT on login page AND NOT on public home page
        current_url = page.url

        def clean(u: str) -> str:
            return u.lower().replace("https://", "").replace("http://", "").rstrip("/")

        current_clean = clean(current_url)
        home_clean    = clean(portal_home_url)
        login_clean   = clean(login_url)

        is_login_page  = (
            "login" in current_url.lower()
            or "sign" in current_url.lower()
            or (login_clean and current_clean == login_clean)
        )
        # Portal redirected back to its own public home when session expired
        is_public_home = (
            current_clean == home_clean
            or (home_clean and current_clean == home_clean.split("#")[0].rstrip("/"))
        )

        if not is_login_page and not is_public_home:
            logger.info("SESSION VALID — not on login/public home page (%s)", current_url)
            return True

        logger.info(
            "SESSION EXPIRED — on login/home page for %s (URL: %s)",
            portal_config.get("name", ""), current_url
        )
        return False

    except Exception as e:
        logger.warning("is_logged_in check failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Manual login wait
# ══════════════════════════════════════════════════════════════════════════════

async def wait_for_manual_login(page: Page, portal_config: dict) -> bool:
    """
    Open the login URL in the already-open headful browser and poll until
    the user completes login (detected via login_success_selector or URL change).

    Writes .login_needed flag so app.py can show the amber banner.
    Deletes the flag and returns True on success.
    Raises TimeoutError if login_timeout_seconds exceeded (if timeout is > 0).
    """
    login_url    = portal_config.get("login_url", portal_config.get("url", ""))
    selector     = portal_config.get("login_success_selector", "")
    timeout_secs = portal_config.get("login_timeout_seconds", 300)

    _write_login_flag()

    logger.info("=" * 60)
    logger.info("WAITING FOR LOGIN — browser window is open")
    logger.info("  Portal : %s", portal_config.get("name", ""))
    logger.info("  URL    : %s", login_url)
    if timeout_secs > 0:
        logger.info("  Timeout: %d seconds", timeout_secs)
    else:
        logger.info("  Timeout: None (waiting indefinitely)")
    logger.info("  Complete login in the browser to continue crawling.")
    logger.info("  Session will be saved and reused on future runs.")
    logger.info("=" * 60)

    try:
        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)
        # Detect Angular 404 page — fall back to home
        current_after_goto = page.url
        page_title = await page.title()
        is_404 = (
            "404" in current_after_goto
            or "404" in (page_title or "").lower()
            or "not found" in (page_title or "").lower()
        )
        if is_404:
            portal_home = portal_config.get("url", "")
            logger.warning(
                "Login URL returned 404 — falling back to home page: %s", portal_home
            )
            login_url = portal_home  # update login_url to home
            try:
                await page.goto(portal_home, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Could not navigate to login URL: %s", e)


    portal_home_url = portal_config.get("url", "")
    start    = time.time()
    interval = 2  # poll every 2 seconds

    def _clean(u: str) -> str:
        return u.lower().replace("https://", "").replace("http://", "").rstrip("/")

    home_clean  = _clean(portal_home_url)
    login_clean = _clean(login_url) if login_url else ""

    while timeout_secs <= 0 or (time.time() - start < timeout_secs):
        # Only treat as closed if ALL pages in the context are gone (a single
        # page may briefly report closed during Angular route changes).
        open_pages = [p for p in page.context.pages if not p.is_closed()]
        if not open_pages and (time.time() - start) > 3:
            logger.warning("Browser window was manually closed by the user. Aborting login.")
            _delete_login_flag()
            raise RuntimeError("Browser window closed manually by the user.")
        if page.is_closed() and open_pages:
            # Route change opened a new tab/page — switch to the latest one.
            page = open_pages[-1]

        elapsed = int(time.time() - start)

        # Check selector
        if selector:
            for sel in [s.strip() for s in selector.split(",")]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        logger.info(
                            "LOGIN DETECTED after %ds — selector matched: %s",
                            elapsed, sel
                        )
                        _delete_login_flag()
                        await save_context_cookies(page.context, portal_config)
                        return True
                except Exception:
                    continue

        # Check URL no longer on login or public-home page
        current_url   = page.url
        current_clean = _clean(current_url)

        on_login = (
            "login" in current_url.lower()
            or "sign" in current_url.lower()
            or "404" in current_url.lower()
            or (login_clean and current_clean == login_clean)
        )
        on_home = (
            current_clean == home_clean
            or (home_clean and current_clean == home_clean.split("#")[0].rstrip("/"))
        )

        # Also check if URL moved to a known post-login page (dashboard etc.)
        post_login_urls = [
            _clean(pg.get("url", ""))
            for pg in portal_config.get("post_login_pages", [])
            if pg.get("url")
        ]
        on_post_login_page = any(
            current_clean == pl or current_clean.startswith(pl)
            for pl in post_login_urls if pl
        )

        if on_post_login_page:
            logger.info(
                "LOGIN DETECTED after %ds — arrived at post-login page: %s",
                elapsed, current_url
            )
            _delete_login_flag()
            await save_context_cookies(page.context, portal_config)
            return True

        if login_url and not on_login and not on_home and current_url != login_url:
            logger.info(
                "LOGIN DETECTED after %ds — URL changed to: %s",
                elapsed, current_url
            )
            _delete_login_flag()
            await save_context_cookies(page.context, portal_config)
            return True

        if elapsed % 30 == 0 and elapsed > 0:
            if timeout_secs > 0:
                logger.info(
                    "WAITING FOR LOGIN — %ds elapsed, %ds remaining ...",
                    elapsed, timeout_secs - elapsed
                )
            else:
                logger.info(
                    "WAITING FOR LOGIN — %ds elapsed (waiting indefinitely) ...",
                    elapsed
                )

        await asyncio.sleep(interval)

    _delete_login_flag()
    logger.error("LOGIN TIMEOUT — %d seconds exceeded. Crawl aborted.", timeout_secs)
    raise TimeoutError(
        f"Manual login not completed within {timeout_secs} seconds"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main orchestrator called by crawler.py
# ══════════════════════════════════════════════════════════════════════════════

async def ensure_logged_in(page: Page, portal_config: dict, *, force_manual: bool = False) -> bool:
    """
    Check if the current persistent-context session is valid.
    If yes  → log SESSION VALID and return immediately.
    If no   → open login page (browser is already headful), wait for manual login.

    Returns True on success, raises on timeout.
    """
    if force_manual:
        logger.info(
            "First run for %s — opening browser for manual login (skipping session check)",
            portal_config.get("name", ""),
        )
        return await wait_for_manual_login(page, portal_config)

    logger.info("Checking session validity for %s ...", portal_config.get("name", ""))

    if await is_logged_in(page, portal_config):
        logger.info("SESSION VALID — skipping manual login, proceeding to post-login crawl")
        return True

    logger.info(
        "SESSION EXPIRED or first run — switching to manual login for %s",
        portal_config.get("name", "")
    )
    return await wait_for_manual_login(page, portal_config)


# ══════════════════════════════════════════════════════════════════════════════
# Legacy auth modes (unchanged — used by other portals)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_auth(page: Page, portal_config: dict):
    """Route to the correct auth handler based on portal config."""
    auth_type = portal_config.get("auth", "public")

    if auth_type in ("public", "none"):
        await public_auth(page, portal_config)
    elif auth_type == "manual":
        await manual_auth(page, portal_config)
    elif auth_type == "cookie":
        await cookie_auth(page, portal_config)
    elif auth_type == "persistent":
        # persistent auth is handled directly in crawl_portal() via
        # launch_persistent_context + ensure_logged_in — nothing to do here
        logger.info("Persistent auth mode — handled by crawl_portal()")
    else:
        logger.warning("Unknown auth type '%s' — treating as public", auth_type)
        await public_auth(page, portal_config)


async def public_auth(page: Page, portal_config: dict):
    url = portal_config["url"]
    logger.info("Public auth — navigating to %s", url)
    await page.goto(url, wait_until="networkidle", timeout=30000)
    logger.info("Page loaded successfully")


async def manual_auth(page: Page, portal_config: dict):
    """Legacy manual auth using Playwright toolbar pause."""
    url = portal_config["url"]
    logger.info("Manual auth — opening %s", url)
    await page.goto(url, wait_until="networkidle", timeout=30000)

    print("\n" + "=" * 60)
    print("BROWSER IS OPEN")
    print("Please do the following manually:")
    print("  1. Type your username and password")
    print("  2. Solve the CAPTCHA")
    print("  3. Enter the OTP")
    print("  4. Wait until you are fully logged in")
    print("  5. Click the RESUME button in the Playwright toolbar")
    print("=" * 60 + "\n")

    await page.pause()
    logger.info("Manual login completed — crawler taking over now")


async def cookie_auth(page: Page, portal_config: dict):
    url          = portal_config["url"]
    session_path = portal_config.get("cookie", {}).get("storage_state_path")

    if not session_path:
        logger.error("Cookie auth requires storage_state_path in config.json")
        raise ValueError("Missing storage_state_path for cookie auth")

    if not os.path.exists(session_path):
        logger.error(
            "Session file not found at %s — run capture_session.py first",
            session_path
        )
        raise FileNotFoundError(f"Session file not found: {session_path}")

    logger.info("Cookie auth — session loaded from %s", session_path)
    await page.goto(url, wait_until="networkidle", timeout=30000)
    logger.info("Cookie session applied successfully")


async def launch_persistent_context(playwright, portal_config: dict) -> BrowserContext:
    """Launch a persistent Chromium context using the portal's profile directory.
    The context is headful (visible) to allow manual login when needed.
    """
    """Launch a persistent Chromium context using the portal's profile directory.
    The context is headful (visible) to allow manual login when needed.
    """
    profile_dir = get_profile_dir(portal_config)
    # Browser launch arguments – align with crawler's _browser_args()
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
    # Viewport from config (fallback to defaults)
    viewport_cfg = config.get("browser", {}).get("viewport", {})
    viewport = {"width": viewport_cfg.get("width", 1280), "height": viewport_cfg.get("height", 900)}
    # User agent fallback
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=args,
        viewport=viewport,
        user_agent=user_agent,
        ignore_https_errors=True,
    )
    return context


# ══════════════════════════════════════════════════════════════════════════════
# Utility: clear saved profile (force re-login next run)
# ══════════════════════════════════════════════════════════════════════════════

def clear_profile(portal_config: dict) -> bool:
    """
    Delete the persistent browser profile so the next crawl run will
    open a fresh login window. Called from app.py "↺ Force re-login" button.
    Returns True if profile was deleted, False if it didn't exist.
    """
    path = get_profile_dir(portal_config)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        logger.info("Browser profile cleared for %s — next run will require login", portal_config.get("name", ""))
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Legacy: capture cookie session helper
# ══════════════════════════════════════════════════════════════════════════════

async def capture_cookie_session(portal_config: dict):
    url          = portal_config["url"]
    session_path = portal_config.get("cookie", {}).get("storage_state_path", "sessions/session.json")

    os.makedirs(os.path.dirname(session_path), exist_ok=True)
    browser_cfg = config.get("browser", {})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(
            viewport={
                "width":  browser_cfg.get("viewport", {}).get("width",  1280),
                "height": browser_cfg.get("viewport", {}).get("height", 800),
            }
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")

        print("\n" + "=" * 60)
        print("SESSION CAPTURE MODE")
        print("Please login manually in the browser.")
        print("Once fully logged in, click RESUME in the Playwright toolbar.")
        print("=" * 60 + "\n")

        await page.pause()
        await context.storage_state(path=session_path)
        logger.info("Session saved to %s", session_path)
        print(f"\nSession saved to {session_path}\n")
        await browser.close()


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        portal_name = sys.argv[2] if len(sys.argv) > 2 else None
        portal      = None
        for p in config["portals"]:
            if portal_name is None or p["name"] == portal_name:
                portal = p
                break
        if not portal:
            print("Portal not found in config.json")
            sys.exit(1)
        asyncio.run(capture_cookie_session(portal))

    elif len(sys.argv) > 1 and sys.argv[1] == "clear-profile":
        portal_name = sys.argv[2] if len(sys.argv) > 2 else None
        portal      = None
        for p in config["portals"]:
            if portal_name is None or p["name"] == portal_name:
                portal = p
                break
        if not portal:
            print("Portal not found in config.json")
            sys.exit(1)
        cleared = clear_profile(portal)
        print(f"Profile {'cleared' if cleared else 'did not exist'} for {portal['name']}")

    else:
        print("auth.py — available commands:")
        print("  python auth.py capture [portal_name]       — capture cookie session")
        print("  python auth.py clear-profile [portal_name] — delete persistent profile")
        print("Auth modes: public, none, manual, cookie, persistent")