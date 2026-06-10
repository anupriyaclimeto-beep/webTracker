"""
crawler_usedoil.py — CPCB EPR Used Oil Portal Crawler
URL: https://eprusedoil.cpcb.gov.in/

Confirmed public pages (from search-result evidence):
  HOME            https://eprusedoil.cpcb.gov.in/
  LOGIN           https://eprusedoil.cpcb.gov.in/login          (ticker notices)
  DASHBOARD       https://eprusedoil.cpcb.gov.in/national-dashboard
  ABOUT US        https://eprusedoil.cpcb.gov.in/aboutus
  SIGNUP VIDEO    https://eprusedoil.cpcb.gov.in/signupVideo
  TERMS           https://eprusedoil.cpcb.gov.in/page/1
  PRIVACY POLICY  https://eprusedoil.cpcb.gov.in/page/3

Navbar dropdowns attempted (mirrors Battery / Tyres pattern):
  • Important Information  → viewport screenshot of open dropdown
  • Rules                  → viewport screenshot of open dropdown
  • SOP                    → viewport screenshot of open dropdown
  • Guidance Documents     → viewport screenshot of open dropdown
  • FAQ                    → scroll & stitch full page
"""

import asyncio
import io
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

os.environ.setdefault("PWDEBUG", "0")

from auth import handle_auth, ensure_logged_in, get_profile_dir, profile_exists, save_context_cookies
from diff_engine import run_all_diffs
from storage import (
    init_db, update_baseline, get_baseline,
    save_diff, start_crawl_log, finish_crawl_log,
    upload_to_cloudinary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
import shutil

with open("config.json") as f:
    config = json.load(f)

from storage import ARCHIVE_DIR
PORTAL_NAME  = "EPR USEDOIL"

HOME_URL      = "https://eprusedoil.cpcb.gov.in/"
LOGIN_URL     = "https://eprusedoil.cpcb.gov.in/login"
DASHBOARD_URL = "https://eprusedoil.cpcb.gov.in/national-dashboard"
ABOUTUS_URL   = "https://eprusedoil.cpcb.gov.in/aboutus"
SIGNUP_VID_URL = "https://eprusedoil.cpcb.gov.in/signupVideo"
TERMS_URL     = "https://eprusedoil.cpcb.gov.in/page/1"
PRIVACY_URL   = "https://eprusedoil.cpcb.gov.in/page/3"

# Storage keys for dropdown viewport screenshots (not real URLs)
KEY_DD_IMPORTANT  = HOME_URL + "__DROPDOWN_ImportantInformation"
KEY_DD_RULES      = HOME_URL + "__DROPDOWN_Rules"
KEY_DD_SOP        = HOME_URL + "__DROPDOWN_SOP"
KEY_DD_GUIDANCE   = HOME_URL + "__DROPDOWN_GuidanceDocuments"
KEY_PAGE_FAQ      = HOME_URL + "__PAGE_FAQ"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_archive_path(key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", re.sub(r"https?://", "", key))
    safe = re.sub(r"_+", "_", safe).strip("_")[:180]
    path = Path(ARCHIVE_DIR) / PORTAL_NAME / safe / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_snapshot(page, key: str, screenshot_bytes: bytes) -> dict:
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(0.5)
    html            = await page.content()
    archive         = make_archive_path(key)
    html_path       = archive / "snapshot.html"
    screenshot_path = archive / "screenshot.png"
    html_path.write_text(html, encoding="utf-8")
    screenshot_path.write_bytes(screenshot_bytes)
    logger.info("✓ Saved → %s", archive)
    return {
        "html": html,
        "screenshot_bytes": screenshot_bytes,
        "html_path": str(html_path),
        "screenshot_path": str(screenshot_path),
    }


async def diff_and_store(url: str, snap: dict, har_path: str):
    baseline    = get_baseline(PORTAL_NAME, url)
    diff_result = await run_all_diffs(
        portal_name=PORTAL_NAME, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
    )
    # Upload to Cloudinary
    screenshot_url = upload_to_cloudinary(snap["screenshot_path"], resource_type="image")
    html_url       = upload_to_cloudinary(snap["html_path"], resource_type="raw")
    if screenshot_url:
        logger.info("  Cloudinary screenshot: %s", screenshot_url)
    if html_url:
        logger.info("  Cloudinary HTML: %s", html_url)

    saved_any = False
    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            if diff_data.get("changed"):
                save_diff(portal=PORTAL_NAME, url=url,
                          diff_type=diff_type, diff_detail=diff_data,
                          screenshot_url=screenshot_url, html_url=html_url)
                saved_any = True
                logger.info("  Change: %s | %s", url, diff_type)

    # Update baseline only after saving changes
    if saved_any:
        try:
            update_baseline(
                portal=PORTAL_NAME, url=url,
                html_path=snap["html_path"],
                screenshot_path=snap["screenshot_path"],
                har_path=har_path,
                screenshot_url=screenshot_url,
                html_url=html_url,
            )
        except Exception as e:
            logger.warning("Failed to update baseline for %s: %s", url, e)
    # Cleanup local archive folder
    try:
        _snap_dir = Path(snap["screenshot_path"]).parent
        shutil.rmtree(_snap_dir)
        logger.info("✓ Cleaned up local archive %s", _snap_dir)
    except Exception as e:
        logger.warning("Cleanup failed for %s: %s", snap.get("screenshot_path", ""), e)


async def scroll_and_stitch(page) -> bytes:
    """Full-page scroll capture stitched into one tall PNG."""
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(0.5)
    total_h  = await page.evaluate("document.body.scrollHeight")
    logger.info("  scrollHeight=%dpx viewport=%dpx", total_h, vh)
    pieces, scroll_y = [], 0
    while scroll_y < total_h:
        await page.evaluate(f"window.scrollTo(0,{scroll_y})")
        await asyncio.sleep(0.4)
        raw      = await page.screenshot(full_page=False, type="png")
        img      = Image.open(io.BytesIO(raw))
        actual_y = await page.evaluate("window.scrollY")
        pieces.append((actual_y, img))
        scroll_y += vh
        total_h   = await page.evaluate("document.body.scrollHeight")
    stitched = Image.new("RGB", (vw, total_h))
    for y, img in pieces:
        stitched.paste(img, (0, y))
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(1.5)
    buf = io.BytesIO()
    stitched.save(buf, format="PNG")
    logger.info("  Stitched %dx%d from %d pieces", vw, total_h, len(pieces))
    return buf.getvalue()


async def goto_home(page):
    """Navigate to home and wait for full load."""
    await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    await asyncio.sleep(2)


async def do_direct_url(page, url: str, har_path: str, pages_visited: int,
                        label: str = "") -> int:
    """Navigate directly to a URL, scroll-and-stitch, save + diff."""
    logger.info("  Direct → %s", url)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    await asyncio.sleep(3)
    snap = await save_snapshot(page, url, await scroll_and_stitch(page))
    await diff_and_store(url, snap, har_path)
    pages_visited += 1
    logger.info("  ✓ %s", label or url)
    return pages_visited


async def open_dropdown_and_screenshot(page, nav_labels: list, step_name: str) -> bytes | None:
    """
    Hover + click the first visible navbar element matching any label.
    Returns a viewport PNG with the dropdown open, or None if not found.
    Presses Escape to close after capture.
    """
    selectors = []
    for label in nav_labels:
        selectors += [
            f"nav a:has-text('{label}')",
            f"nav button:has-text('{label}')",
            f"a:has-text('{label}')",
            f"button:has-text('{label}')",
            f"[class*='nav'] a:has-text('{label}')",
            f"[class*='nav'] button:has-text('{label}')",
            f"[class*='menu'] a:has-text('{label}')",
            f"li > a:has-text('{label}')",
        ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if not await el.is_visible(timeout=2000):
                continue
            await el.hover()
            await asyncio.sleep(0.6)
            await el.click()
            await asyncio.sleep(0.8)
            logger.info("  [%s] opened via: %s", step_name, sel)
            screenshot = await page.screenshot(full_page=False, type="png")
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            return screenshot
        except Exception:
            continue

    logger.warning("  [%s] dropdown not found — tried: %s", step_name, nav_labels)
    return None


async def do_dropdown(page, key: str, har_path: str, pages_visited: int,
                      step_name: str, nav_labels: list) -> int:
    """Open a dropdown, take viewport screenshot, save + diff."""
    await goto_home(page)
    ss = await open_dropdown_and_screenshot(page, nav_labels, step_name)
    if ss:
        snap = await save_snapshot(page, key, ss)
        await diff_and_store(key, snap, har_path)
        pages_visited += 1
        logger.info("  ✓ %s", step_name)
    else:
        logger.warning("  Skipped (not found): %s", step_name)
    return pages_visited


async def do_nav_scroll(page, har_path: str, pages_visited: int,
                        key: str, step_name: str, nav_labels: list) -> int:
    """Click a navbar item that navigates to a full page, then scroll-and-stitch."""
    await goto_home(page)
    for label in nav_labels:
        for sel in [
            f"nav a:has-text('{label}')",
            f"a:has-text('{label}')",
            f"li > a:has-text('{label}')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    try:
                        await page.wait_for_load_state("networkidle", timeout=12000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    logger.info("  [%s] navigated via: %s", step_name, sel)
                    snap = await save_snapshot(page, key, await scroll_and_stitch(page))
                    await diff_and_store(key, snap, har_path)
                    pages_visited += 1
                    logger.info("  ✓ %s", step_name)
                    return pages_visited
            except Exception:
                continue
    logger.warning("  Skipped (not found): %s", step_name)
    return pages_visited


# ── Main crawl ────────────────────────────────────────────────────────────────

async def crawl_usedoil_portal(portal_config: dict):
    har_dir  = Path(ARCHIVE_DIR) / PORTAL_NAME
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path = str(har_dir / f"{PORTAL_NAME}_network.har")

    crawl_id      = start_crawl_log(PORTAL_NAME)
    pages_visited = 0

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Headless: public pre-login pages
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PHASE 1 - Headless public crawl")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_har_path=har_path,
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── STEP 1: Home page ──────────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page ═══")
        await goto_home(page)
        snap = await save_snapshot(page, HOME_URL, await scroll_and_stitch(page))
        await diff_and_store(HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home done ✓")

        # ── STEP 2: Login page ─────────────────────────────────────────────────
        logger.info("═══ STEP 2: Login page (public ticker + notices) ═══")
        try:
            pages_visited = await do_direct_url(
                page, LOGIN_URL, har_path, pages_visited, "Login page"
            )
        except Exception as e:
            logger.warning("Failed to crawl login page: %s", e)

        # ── STEP 3: National Dashboard ─────────────────────────────────────────
        logger.info("═══ STEP 3: National Dashboard ═══")
        try:
            pages_visited = await do_direct_url(
                page, DASHBOARD_URL, har_path, pages_visited, "National Dashboard"
            )
        except Exception as e:
            logger.warning("Failed to crawl national dashboard: %s", e)

        # ── STEP 4: About Us ───────────────────────────────────────────────────
        logger.info("═══ STEP 4: About Us ═══")
        try:
            pages_visited = await do_direct_url(
                page, ABOUTUS_URL, har_path, pages_visited, "About Us"
            )
        except Exception as e:
            logger.warning("Failed to crawl about us: %s", e)

        # ── STEP 5: Signup Video page ──────────────────────────────────────────
        logger.info("═══ STEP 5: Signup Video page ═══")
        try:
            pages_visited = await do_direct_url(
                page, SIGNUP_VID_URL, har_path, pages_visited, "Signup Video"
            )
        except Exception as e:
            logger.warning("Failed to crawl signup video: %s", e)

        # ── STEP 6: Terms & Conditions ─────────────────────────────────────────
        logger.info("═══ STEP 6: Terms & Conditions (/page/1) ═══")
        try:
            pages_visited = await do_direct_url(
                page, TERMS_URL, har_path, pages_visited, "Terms & Conditions"
            )
        except Exception as e:
            logger.warning("Failed to crawl terms: %s", e)

        # ── STEP 7: Privacy Policy ─────────────────────────────────────────────
        logger.info("═══ STEP 7: Privacy Policy (/page/3) ═══")
        try:
            pages_visited = await do_direct_url(
                page, PRIVACY_URL, har_path, pages_visited, "Privacy Policy"
            )
        except Exception as e:
            logger.warning("Failed to crawl privacy: %s", e)

        # ── STEP 8: Important Information dropdown ─────────────────────────────
        logger.info("═══ STEP 8: Important Information dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_IMPORTANT, har_path, pages_visited,
            step_name="Important Information dropdown",
            nav_labels=[
                "Important Information",
                "Important Informations",
                "Important Communications",
                "Important Communication",
                "Notices",
            ],
        )

        # ── STEP 9: Rules dropdown ─────────────────────────────────────────────
        logger.info("═══ STEP 9: Rules dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_RULES, har_path, pages_visited,
            step_name="Rules dropdown",
            nav_labels=["Rules"],
        )

        # ── STEP 10: SOP dropdown ──────────────────────────────────────────────
        logger.info("═══ STEP 10: SOP dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_SOP, har_path, pages_visited,
            step_name="SOP dropdown",
            nav_labels=["SOP", "SOP for Registration", "Standard Operating Procedure"],
        )

        # ── STEP 11: Guidance Documents dropdown ──────────────────────────────
        logger.info("═══ STEP 11: Guidance Documents dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_GUIDANCE, har_path, pages_visited,
            step_name="Guidance Documents dropdown",
            nav_labels=[
                "Guidance Documents",
                "Guidance Document",
                "Guidance Manuals",
                "Guidance Manual",
            ],
        )

        # ── STEP 12: FAQ page ──────────────────────────────────────────────────
        logger.info("═══ STEP 12: FAQ page ═══")
        pages_visited = await do_nav_scroll(
            page, har_path, pages_visited,
            key=KEY_PAGE_FAQ,
            step_name="FAQ page",
            nav_labels=["FAQs", "FAQ", "Frequently Asked Questions"],
        )

        await context.close()
        await browser.close()

    logger.info("PHASE 1 complete | pages_visited=%d", pages_visited)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Persistent context: post-login pages
    # ══════════════════════════════════════════════════════════════════════════
    post_login_pages = portal_config.get("post_login_pages", [])
    if not post_login_pages:
        logger.info("No post_login_pages configured — skipping Phase 2")
        finish_crawl_log(crawl_id, pages_visited, status="done")
        logger.info("═══ EPR USEDOIL ALL DONE: %d pages ═══", pages_visited)
        return

    logger.info("=" * 60)
    logger.info("PHASE 2 - Persistent context post-login crawl")
    logger.info("=" * 60)

    profile_dir = get_profile_dir(portal_config)
    first_run   = not profile_exists(portal_config)

    if first_run:
        logger.info("First run - no browser profile found at %s", profile_dir)
        logger.info("Browser will open headful for manual login")
    else:
        logger.info("Browser profile found at %s - will attempt session restore", profile_dir)

    async with async_playwright() as p:
        persistent_ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # Restore saved cookies if available
        cookies_path = profile_dir / "cookies.json"
        if cookies_path.exists():
            try:
                cookies = json.loads(cookies_path.read_text())
                await persistent_ctx.add_cookies(cookies)
                logger.info("Session cookies restored from %s", cookies_path)
            except Exception as e:
                logger.warning("Failed to restore session cookies: %s", e)

        page = await persistent_ctx.new_page()

        # Ensure logged in
        try:
            await ensure_logged_in(page, portal_config)
        except TimeoutError as e:
            logger.error("Login timed out: %s", e)
            await persistent_ctx.close()
            finish_crawl_log(crawl_id, pages_visited, status="error")
            return
        except Exception as e:
            logger.error("Login failed: %s", e)
            await persistent_ctx.close()
            if "closed manually" in str(e) or "closed" in str(e).lower():
                finish_crawl_log(crawl_id, pages_visited, status="stopped")
                logger.info("Exiting crawler due to manual browser closure.")
                import sys
                sys.exit(0)
            finish_crawl_log(crawl_id, pages_visited, status="error")
            return

        # Crawl each post-login page
        for step_idx, page_cfg in enumerate(post_login_pages, start=13):
            label    = page_cfg.get("label", f"PostLogin_{step_idx}")
            url      = page_cfg.get("url", "")
            method   = page_cfg.get("method", "scroll")
            page_key = HOME_URL + f"__LOGGEDIN_{label}"

            if not url:
                logger.warning("Step %d: no URL for '%s' — skipping", step_idx, label)
                continue

            logger.info("=== STEP %d: %s (%s) ===", step_idx, label, method)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning("Navigation failed for '%s': %s", label, e)
                if "closed" in str(e).lower() or "detached" in str(e).lower():
                    logger.info("Exiting crawler due to manual browser closure.")
                    finish_crawl_log(crawl_id, pages_visited, status="stopped")
                    await persistent_ctx.close()
                    import sys
                    sys.exit(0)
                continue

            if method == "scroll":
                screenshot_bytes = await scroll_and_stitch(page)
            else:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")

            snap = await save_snapshot(page, page_key, screenshot_bytes)
            await diff_and_store(page_key, snap, har_path)
            pages_visited += 1
            logger.info("  '%s' done | pages_visited=%d", label, pages_visited)

        # Save cookies before closing
        try:
            await save_context_cookies(persistent_ctx, portal_config)
        except Exception as e:
            logger.warning("Failed to save session cookies: %s", e)

        await persistent_ctx.close()
        logger.info("Persistent browser profile saved to %s", profile_dir)

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ EPR USEDOIL ALL DONE: %d pages ═══", pages_visited)
    logger.info("CRAWL_FINISHED: %d pages", pages_visited)
    logger.info("ALL DONE - pages complete")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    portal_cfg = next(
        (p for p in config.get("portals", []) if p["name"] == PORTAL_NAME),
        {"name": PORTAL_NAME, "auth": "none"},
    )
    asyncio.run(crawl_usedoil_portal(portal_cfg))