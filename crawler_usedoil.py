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

from auth import handle_auth
from diff_engine import run_all_diffs
from storage import (
    init_db, update_baseline, get_baseline,
    save_diff, start_crawl_log, finish_crawl_log,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

ARCHIVE_DIR  = config["storage"]["archive_dir"]
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
    update_baseline(
        portal=PORTAL_NAME, url=url,
        html_path=snap["html_path"],
        screenshot_path=snap["screenshot_path"],
        har_path=har_path,
    )
    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            if diff_data.get("changed"):
                save_diff(portal=PORTAL_NAME, url=url,
                          diff_type=diff_type, diff_detail=diff_data)
                logger.info("  ✅ Change: %s | %s", url, diff_type)


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

        try:
            await handle_auth(page, portal_config)
        except Exception as e:
            logger.warning("Auth skipped: %s", e)

        # ── STEP 1: Home page ──────────────────────────────────────────────────
        # Captures: scrolling ticker (deadline notices), intro paragraph,
        # entity-type cards (Producers/Recyclers/Collection Agents/Used Oil Importer),
        # footer links.
        logger.info("═══ STEP 1: Home page ═══")
        await goto_home(page)
        snap = await save_snapshot(page, HOME_URL, await scroll_and_stitch(page))
        await diff_and_store(HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home done ✓")

        # ── STEP 2: Login page ─────────────────────────────────────────────────
        # Even without credentials, the login page shows the public ticker
        # (e.g. "Annual Return deadline extended to 30 Sep 2025",
        #        "Used Oil Importer Registration now available",
        #        "Signup for all entities now available").
        # Monitoring this page catches notice changes without needing auth.
        logger.info("═══ STEP 2: Login page (public ticker + notices) ═══")
        pages_visited = await do_direct_url(
            page, LOGIN_URL, har_path, pages_visited, "Login page"
        )

        # ── STEP 3: National Dashboard ─────────────────────────────────────────
        # Public stats page: registrations, EPR certificate counts, etc.
        # URL confirmed: /national-dashboard
        logger.info("═══ STEP 3: National Dashboard ═══")
        pages_visited = await do_direct_url(
            page, DASHBOARD_URL, har_path, pages_visited, "National Dashboard"
        )

        # ── STEP 4: About Us ───────────────────────────────────────────────────
        # Explains the HOW (M&TM) Second Amendment Rules, 2023 and EPR obligations.
        # Useful to catch if the statutory text or obligation wording changes.
        logger.info("═══ STEP 4: About Us ═══")
        pages_visited = await do_direct_url(
            page, ABOUTUS_URL, har_path, pages_visited, "About Us"
        )

        # ── STEP 5: Signup Video page ──────────────────────────────────────────
        # Public tutorial page at /signupVideo — captures any new video links
        # or tutorial updates added for Producers / Recyclers / Collection Agents.
        logger.info("═══ STEP 5: Signup Video page ═══")
        pages_visited = await do_direct_url(
            page, SIGNUP_VID_URL, har_path, pages_visited, "Signup Video"
        )

        # ── STEP 6: Terms & Conditions ─────────────────────────────────────────
        # Static legal text at /page/1 — changes here are policy-significant.
        logger.info("═══ STEP 6: Terms & Conditions (/page/1) ═══")
        pages_visited = await do_direct_url(
            page, TERMS_URL, har_path, pages_visited, "Terms & Conditions"
        )

        # ── STEP 7: Privacy Policy ─────────────────────────────────────────────
        # Static policy page at /page/3.
        logger.info("═══ STEP 7: Privacy Policy (/page/3) ═══")
        pages_visited = await do_direct_url(
            page, PRIVACY_URL, har_path, pages_visited, "Privacy Policy"
        )

        # ── STEP 8: Important Information dropdown ─────────────────────────────
        # Expected content (mirroring Battery/Tyres pattern):
        #   • Deadline extension notices
        #   • Annual Return filing notices
        #   • New module availability announcements
        # Tries multiple label variants to handle label drift.
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
        # Expected content:
        #   • HOW (M&TM) Rules, 2016
        #   • HOW (M&TM) Second Amendment Rules, 2023  (the key used-oil rule)
        logger.info("═══ STEP 9: Rules dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_RULES, har_path, pages_visited,
            step_name="Rules dropdown",
            nav_labels=["Rules"],
        )

        # ── STEP 10: SOP dropdown ──────────────────────────────────────────────
        # Expected content:
        #   • SOP for Producer registration
        #   • SOP for Recycler registration
        #   • SOP for Collection Agent registration
        #   • SOP for Used Oil Importer registration
        logger.info("═══ STEP 10: SOP dropdown ═══")
        pages_visited = await do_dropdown(
            page, KEY_DD_SOP, har_path, pages_visited,
            step_name="SOP dropdown",
            nav_labels=["SOP", "SOP for Registration", "Standard Operating Procedure"],
        )

        # ── STEP 11: Guidance Documents dropdown ──────────────────────────────
        # Expected content:
        #   • Guidance Document for EPR Certificate generation & transfer
        #   • Interim Arrangement guidance
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
        # FAQ confirmed on Battery / Tyres portals; try nav-click first.
        # Scroll-and-stitch the full page to capture all Q&A pairs.
        logger.info("═══ STEP 12: FAQ page ═══")
        pages_visited = await do_nav_scroll(
            page, har_path, pages_visited,
            key=KEY_PAGE_FAQ,
            step_name="FAQ page",
            nav_labels=["FAQs", "FAQ", "Frequently Asked Questions"],
        )

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ EPR USEDOIL ALL DONE: %d pages ═══", pages_visited)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    portal_cfg = next(
        (p for p in config.get("portals", []) if p["name"] == PORTAL_NAME),
        {"name": PORTAL_NAME, "auth": "none"},
    )
    asyncio.run(crawl_usedoil_portal(portal_cfg))