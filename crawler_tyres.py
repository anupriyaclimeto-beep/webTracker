"""
crawler_tyres.py — CPCB EPR Waste Tyre Portal Crawler
Targets:
  1. Home page          (scroll & stitch)
  2. Dashboard          (navbar click → scroll & stitch)
  3. Rules dropdown     (hover/click → viewport screenshot of open dropdown)
  4. Important Informations dropdown  (hover/click → viewport screenshot)
URL: https://eprtyres.cpcb.gov.in/
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

ARCHIVE_DIR   = config["storage"]["archive_dir"]
PORTAL_NAME   = "EPR TYRES"
HOME_URL      = "https://eprtyres.cpcb.gov.in/"
DASHBOARD_URL = "https://eprtyres.cpcb.gov.in/user/nationalDashboard"

# Archive keys for dropdown screenshots (not real URLs — used as storage keys)
KEY_RULES_DROPDOWN = HOME_URL + "__DROPDOWN_Rules"
KEY_IMPORTANT_DROPDOWN = HOME_URL + "__DROPDOWN_ImportantInformations"


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
    """Scroll the full page top→bottom and stitch into one PNG."""
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


async def open_dropdown_and_screenshot(page, nav_labels: list[str], step_name: str) -> bytes | None:
    """
    Hover then click the first matching navbar label to open its dropdown.
    Returns a viewport screenshot (PNG bytes) with the dropdown open,
    or None if the element could not be found.

    Strategy:
      1. Hover  → some menus open on hover
      2. Wait 600 ms
      3. Click  → ensure the dropdown is open
      4. Wait 800 ms for animation
      5. Take full-viewport screenshot
      6. Press Escape to close
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

            # Hover first (reveals hover-based dropdowns)
            await el.hover()
            await asyncio.sleep(0.6)

            # Click to also handle click-based dropdowns
            await el.click()
            await asyncio.sleep(0.8)

            logger.info("  [%s] Dropdown opened via: %s", step_name, sel)
            screenshot = await page.screenshot(full_page=False, type="png")

            # Close the dropdown
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            return screenshot

        except Exception:
            continue

    logger.warning("  [%s] Could not open dropdown — tried labels: %s", step_name, nav_labels)
    return None


async def click_dashboard_nav(page) -> bool:
    """
    Click the 'Dashboard' link in the navbar.
    Returns True on success, False on failure (caller will use direct URL).
    """
    selectors = [
        "nav a:has-text('Dashboard')",
        "a:has-text('Dashboard')",
        "button:has-text('Dashboard')",
        "[class*='nav'] a:has-text('Dashboard')",
        "[class*='menu'] a:has-text('Dashboard')",
        "li:has-text('Dashboard') > a",
        "li > a:has-text('Dashboard')",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                logger.info("  Clicked navbar 'Dashboard' via: %s", sel)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                return True
        except Exception:
            continue
    logger.warning("  Could not find 'Dashboard' navbar link — falling back to direct URL")
    return False


# ── Main crawl ────────────────────────────────────────────────────────────────

async def crawl_tyres_portal(portal_config: dict):
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

        # ── STEP 1: Home page — scroll & stitch ───────────────────────────────
        logger.info("═══ STEP 1: Home page ═══")
        await goto_home(page)
        snap = await save_snapshot(page, HOME_URL, await scroll_and_stitch(page))
        await diff_and_store(HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home done ✓  (URL: %s)", page.url)

        # ── STEP 2: Dashboard — click navbar link, scroll & stitch ────────────
        logger.info("═══ STEP 2: Dashboard (via navbar click) ═══")
        await goto_home(page)
        clicked = await click_dashboard_nav(page)
        if not clicked:
            logger.info("  Fallback → direct URL: %s", DASHBOARD_URL)
            await page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            await asyncio.sleep(3)
        logger.info("  Dashboard URL after navigation: %s", page.url)
        snap = await save_snapshot(page, DASHBOARD_URL, await scroll_and_stitch(page))
        await diff_and_store(DASHBOARD_URL, snap, har_path)
        pages_visited += 1
        logger.info("Dashboard done ✓")

        # ── STEP 3: Rules dropdown ─────────────────────────────────────────────
        # Navbar label: "Rules ▾"
        # Dropdown shows:  AMENDMENT RULES section
        #   • HOW (M & TM) Amendment Rules, 2022
        #   • HOW (M & TM) Amendment Rules, 2024
        logger.info("═══ STEP 3: Rules dropdown ═══")
        await goto_home(page)
        rules_ss = await open_dropdown_and_screenshot(
            page,
            nav_labels=["Rules"],
            step_name="Rules dropdown",
        )
        if rules_ss:
            snap = await save_snapshot(page, KEY_RULES_DROPDOWN, rules_ss)
            await diff_and_store(KEY_RULES_DROPDOWN, snap, har_path)
            pages_visited += 1
            logger.info("Rules dropdown done ✓")
        else:
            logger.warning("Rules dropdown screenshot skipped — element not found")

        # ── STEP 4: Important Informations dropdown ────────────────────────────
        # Navbar label: "Important Informations ▾"
        # Dropdown shows two sections:
        #   RULES & GUIDELINES
        #     • Notice and Environment Compensation (EC) Guidelines under
        #       Hazardous and Other Wastes (M&TM) Amendments Rules, 2022 and Amendments thereof
        #     • Notice issued to producers and recyclers regarding upload of
        #       E-GST Linked invoice on EPR Portal  [NEW] [SCN]
        #   GUIDANCE & SOP
        #     • Guidance Document for Generation and Transfer of EPR Certificate
        #     • Interim Arrangement (SOP)
        #     • Mechanism for Interim Arrangement
        logger.info("═══ STEP 4: Important Informations dropdown ═══")
        await goto_home(page)
        imp_ss = await open_dropdown_and_screenshot(
            page,
            nav_labels=["Important Informations", "Important Information",
                        "Important Communications", "Important Communication"],
            step_name="Important Informations dropdown",
        )
        if imp_ss:
            snap = await save_snapshot(page, KEY_IMPORTANT_DROPDOWN, imp_ss)
            await diff_and_store(KEY_IMPORTANT_DROPDOWN, snap, har_path)
            pages_visited += 1
            logger.info("Important Informations dropdown done ✓")
        else:
            logger.warning("Important Informations dropdown screenshot skipped — element not found")

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ EPR TYRES ALL DONE: %d pages ═══", pages_visited)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    portal_cfg = next(
        (p for p in config.get("portals", []) if p["name"] == PORTAL_NAME),
        {"name": PORTAL_NAME, "auth": "none"},
    )
    asyncio.run(crawl_tyres_portal(portal_cfg))