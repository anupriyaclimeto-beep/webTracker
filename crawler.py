"""
crawler.py — CPCB EPR Plastic Portal Crawler

Steps:
  1. Home page → scroll & stitch → save
  2. "Plastic Waste Management" → click, snapshot open dropdown → save
  3. "About EPR" → click, snapshot open dropdown → save
  4. Each About EPR sub-page → scroll & stitch → save
     Sub-items: Categories Of Plastic Waste, EPR Target,
                Responsibility Of PIBOs, Plastic Waste Processing
  5. "Important Documents" → click to open dropdown, then scroll_and_stitch
     the WHOLE PAGE (the page itself scrolls to reveal all items — there is
     no internal scroller on the dropdown) → save
  6. "Bulk Upload" → click to open dropdown, single screenshot → save
     Items: Guidance Document - PIBO, Guidance Document - PWP(Cement)
  7. "Lodge Complaint" → click to open dropdown, single screenshot → save
     Items: Create Ticket, How To Create A Ticket
  8. "SOP" → click to open dropdown, single screenshot → save
     Items: PWP, PIBOs
"""

import asyncio
import os
os.environ.setdefault('PWDEBUG', '0')   # disable Playwright inspector
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

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

ARCHIVE_DIR = config["storage"]["archive_dir"]
HOME_URL    = "https://eprplastic.cpcb.gov.in/#/plastic/home"
BASE_URL    = "https://eprplastic.cpcb.gov.in/"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_archive_path(portal_name: str, key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", re.sub(r"https?://", "", key))
    safe = re.sub(r"_+", "_", safe).strip("_")[:180]
    path = Path(ARCHIVE_DIR) / portal_name / safe / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_snapshot(page, portal_name: str, key: str, screenshot_bytes: bytes) -> dict:
    """Persist HTML + screenshot to the archive folder and return paths."""
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(0.5)

    html            = await page.content()
    archive         = make_archive_path(portal_name, key)
    html_path       = archive / "snapshot.html"
    screenshot_path = archive / "screenshot.png"
    html_path.write_text(html, encoding="utf-8")
    screenshot_path.write_bytes(screenshot_bytes)
    logger.info("✓ Saved → %s", archive)
    return {
        "html":             html,
        "screenshot_bytes": screenshot_bytes,
        "html_path":        str(html_path),
        "screenshot_path":  str(screenshot_path),
    }


async def diff_and_store(portal_name, url, snap, har_path):
    """Run diff engine, update baseline, persist any detected changes."""
    baseline    = get_baseline(portal_name, url)
    diff_result = await run_all_diffs(
        portal_name=portal_name, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
    )
    update_baseline(
        portal=portal_name, url=url,
        html_path=snap["html_path"],
        screenshot_path=snap["screenshot_path"],
        har_path=har_path,
    )
    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            if diff_data.get("changed"):
                save_diff(portal=portal_name, url=url,
                          diff_type=diff_type, diff_detail=diff_data)
                logger.info("  ✅ Change detected: %s | %s", url, diff_type)


# ─────────────────────────────────────────────────────────────────────────────
# Full-page scroll + stitch
# ─────────────────────────────────────────────────────────────────────────────

async def scroll_and_stitch(page) -> bytes:
    """
    Scroll the full page top→bottom in viewport-height steps.
    Capture a viewport screenshot at each stop, stitch vertically into
    one tall PNG. Works for both normal pages AND open dropdown menus
    where the PAGE itself provides the scroll (no internal scroller).
    """
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]

    # Start from the very top
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

    total_h = await page.evaluate("document.body.scrollHeight")
    logger.info("  Page scrollHeight=%dpx  viewport=%dpx", total_h, vh)

    pieces  = []
    scroll_y = 0

    while scroll_y < total_h:
        await page.evaluate(f"window.scrollTo(0, {scroll_y})")
        await asyncio.sleep(0.4)   # let lazy content / Angular re-renders settle

        raw      = await page.screenshot(full_page=False, type="png")
        img      = Image.open(io.BytesIO(raw))
        actual_y = await page.evaluate("window.scrollY")
        pieces.append((actual_y, img))

        logger.info("  scrollY=%dpx  piece %d captured", actual_y, len(pieces))

        scroll_y += vh
        # Re-check: page may have grown due to lazy loading
        total_h = await page.evaluate("document.body.scrollHeight")

    # Stitch all pieces into one tall image
    stitched = Image.new("RGB", (vw, total_h))
    for y_pos, img in pieces:
        stitched.paste(img, (0, y_pos))

    # Scroll back to top and let Angular settle
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1.5)

    buf = io.BytesIO()
    stitched.save(buf, format="PNG")
    logger.info(
        "  Stitched: %dx%d px from %d pieces",
        vw, total_h, len(pieces),
    )
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Main crawl
# ─────────────────────────────────────────────────────────────────────────────

async def crawl_portal(portal_config: dict):
    portal_name = portal_config["name"]
    har_dir     = Path(ARCHIVE_DIR) / portal_name
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path    = str(har_dir / f"{portal_name}_network.har")

    crawl_id      = start_crawl_log(portal_name)
    pages_visited = 0

    async with async_playwright() as p:
        browser_cfg = config.get("browser", {})
        # Always headless — never open a browser window or Playwright inspector
        browser     = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={
                "width":  browser_cfg.get("viewport", {}).get("width",  1280),
                "height": browser_cfg.get("viewport", {}).get("height",  900),
            },
            record_har_path=har_path,
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── Auth ──────────────────────────────────────────────────────────────
        try:
            await handle_auth(page, portal_config)
        except Exception as e:
            logger.error("Auth failed: %s", e)
            await browser.close()
            finish_crawl_log(crawl_id, 0, status="error")
            return

        # ── STEP 1: Home page ─────────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page — scroll & stitch ═══")
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        snap = await save_snapshot(
            page, portal_name, HOME_URL,
            await scroll_and_stitch(page),
        )
        await diff_and_store(portal_name, HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home page done ✓")

        # ── STEP 2: "Plastic Waste Management" dropdown ───────────────────────
        logger.info("═══ STEP 2: Plastic Waste Management dropdown ═══")
        dropdown_key = HOME_URL + "__DROPDOWN_PlasticWasteManagement"

        clicked = False
        for sel in [
            "a:has-text('Plastic Waste Management')",
            "button:has-text('Plastic Waste Management')",
            "li:has-text('Plastic Waste Management') > a",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.0)
                    clicked = True
                    break
            except Exception:
                continue

        if clicked:
            snap2 = await save_snapshot(
                page, portal_name, dropdown_key,
                await page.screenshot(full_page=False, type="png"),
            )
            await diff_and_store(portal_name, dropdown_key, snap2, har_path)
            pages_visited += 1
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.info("  Plastic Waste Management dropdown done ✓")
        else:
            logger.warning("  Could not find 'Plastic Waste Management' link")

        # ── STEP 3: "About EPR" dropdown ──────────────────────────────────────
        logger.info("═══ STEP 3: About EPR dropdown ═══")
        about_epr_key = HOME_URL + "__DROPDOWN_AboutEPR"

        async def open_about_epr() -> bool:
            for sel in [
                "a:has-text('About EPR')",
                "button:has-text('About EPR')",
                "li:has-text('About EPR') > a",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.click()
                        await asyncio.sleep(1.0)
                        return True
                except Exception:
                    continue
            return False

        if await open_about_epr():
            snap3 = await save_snapshot(
                page, portal_name, about_epr_key,
                await page.screenshot(full_page=False, type="png"),
            )
            await diff_and_store(portal_name, about_epr_key, snap3, har_path)
            pages_visited += 1
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.info("  About EPR dropdown done ✓")
        else:
            logger.warning("  Could not find 'About EPR' link")

        # ── STEP 4: About EPR sub-pages ───────────────────────────────────────
        about_epr_subpages = [
            ("Categories Of Plastic Waste", "#/plastic/home/categoriesepr"),
            ("EPR Target",                  "#/plastic/home/eprtargets"),
            ("Responsibility Of PIBOs",     "#/plastic/home/pibopwp"),
            ("Plastic Waste Processing",    "#/plastic/home/plasticwaste"),
        ]

        for idx, (label, item_hash) in enumerate(about_epr_subpages, start=1):
            logger.info("═══ STEP 4.%d: %s ═══", idx, label)
            item_url = BASE_URL + item_hash

            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)
            await page.evaluate(f"window.location.hash = '{item_hash}'")
            await asyncio.sleep(1)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            await asyncio.sleep(2)

            logger.info("  Navigated to: %s", page.url)
            item_snap = await save_snapshot(
                page, portal_name, item_url,
                await scroll_and_stitch(page),
            )
            await diff_and_store(portal_name, item_url, item_snap, har_path)
            pages_visited += 1
            logger.info("  ✓ '%s' saved", label)

        # ── STEP 5: "Important Documents" dropdown — click then scroll page ───
        #
        # KEY INSIGHT: this dropdown has NO internal scroller.
        # When it opens, the dropdown items extend BELOW the viewport and the
        # PAGE ITSELF gets a scrollbar.  So the correct approach is:
        #   1. Navigate back to home so the navbar is present.
        #   2. Click "Important Documents" to open the dropdown.
        #   3. DO NOT close it — call scroll_and_stitch(page) which scrolls
        #      window.scrollY down the whole page, capturing every item.
        #   4. Save the stitched full-height screenshot.
        #
        logger.info("═══ STEP 5: Important Documents dropdown — click + scroll page ═══")
        imp_docs_key = HOME_URL + "__DROPDOWN_ImportantDocuments"

        # Go back to home so the navbar is visible
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # Click "Important Documents" to open the dropdown
        imp_opened = False
        for sel in [
            "a:has-text('Important Documents')",
            "button:has-text('Important Documents')",
            "li:has-text('Important Documents') > a",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)   # wait for the dropdown to fully expand
                    logger.info("  Dropdown opened — page should now be scrollable")
                    imp_opened = True
                    break
            except Exception:
                continue

        if imp_opened:
            # The dropdown is open and the page scrollbar is now active.
            # scroll_and_stitch scrolls window.scrollY from 0 → scrollHeight,
            # capturing every piece of the open dropdown as it comes into view.
            imp_screenshot = await scroll_and_stitch(page)

            snap5 = await save_snapshot(page, portal_name, imp_docs_key, imp_screenshot)
            await diff_and_store(portal_name, imp_docs_key, snap5, har_path)
            pages_visited += 1
            logger.info("  Important Documents full snapshot done ✓")
        else:
            logger.warning("  Could not find 'Important Documents' link")

        # ── STEP 6: "Bulk Upload" dropdown — click then scroll page ──────────
        #
        # Same pattern as Important Documents: no internal scroller.
        # Items: "Guidance Document - PIBO", "Guidance Document - PWP(Cement)"
        # Click to open the dropdown, then scroll_and_stitch the whole page
        # so both items are captured in one tall stitched screenshot.
        #
        logger.info("═══ STEP 6: Bulk Upload dropdown — click + scroll page ═══")
        bulk_upload_key = HOME_URL + "__DROPDOWN_BulkUpload"

        # Go back to home so the navbar is visible
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # Click "Bulk Upload" to open the dropdown
        bulk_opened = False
        for sel in [
            "a:has-text('Bulk Upload')",
            "button:has-text('Bulk Upload')",
            "li:has-text('Bulk Upload') > a",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)   # wait for dropdown to fully expand
                    logger.info("  Bulk Upload dropdown opened")
                    bulk_opened = True
                    break
            except Exception:
                continue

        if bulk_opened:
            # Dropdown is open — just take a single viewport screenshot.
            # Only 2 items so everything is visible at once.
            bulk_screenshot = await page.screenshot(full_page=False, type="png")

            snap6 = await save_snapshot(page, portal_name, bulk_upload_key, bulk_screenshot)
            await diff_and_store(portal_name, bulk_upload_key, snap6, har_path)
            pages_visited += 1
            logger.info("  Bulk Upload full snapshot done ✓")
        else:
            logger.warning("  Could not find 'Bulk Upload' link")


        # ── STEP 7: "Lodge Complaint" dropdown — click + single screenshot ─────
        # Items: Create Ticket, How To Create A Ticket
        logger.info("═══ STEP 7: Lodge Complaint dropdown — click + screenshot ═══")
        lodge_key = HOME_URL + "__DROPDOWN_LodgeComplaint"

        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        lodge_opened = False
        for sel in [
            "a:has-text('Lodge Complaint')",
            "button:has-text('Lodge Complaint')",
            "li:has-text('Lodge Complaint') > a",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    logger.info("  Lodge Complaint dropdown opened")
                    lodge_opened = True
                    break
            except Exception:
                continue

        if lodge_opened:
            lodge_screenshot = await page.screenshot(full_page=False, type="png")
            snap7 = await save_snapshot(page, portal_name, lodge_key, lodge_screenshot)
            await diff_and_store(portal_name, lodge_key, snap7, har_path)
            pages_visited += 1
            logger.info("  Lodge Complaint snapshot done ✓")
        else:
            logger.warning("  Could not find 'Lodge Complaint' link")

        # ── STEP 8: "SOP" dropdown — click + single screenshot ───────────────
        # Items: PWP, PIBOs
        logger.info("═══ STEP 8: SOP dropdown — click + screenshot ═══")
        sop_key = HOME_URL + "__DROPDOWN_SOP"

        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        sop_opened = False
        for sel in [
            "a:has-text('SOP')",
            "button:has-text('SOP')",
            "li:has-text('SOP') > a",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    logger.info("  SOP dropdown opened")
                    sop_opened = True
                    break
            except Exception:
                continue

        if sop_opened:
            sop_screenshot = await page.screenshot(full_page=False, type="png")
            snap8 = await save_snapshot(page, portal_name, sop_key, sop_screenshot)
            await diff_and_store(portal_name, sop_key, snap8, har_path)
            pages_visited += 1
            logger.info("  SOP snapshot done ✓")
        else:
            logger.warning("  Could not find 'SOP' link")

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ ALL DONE: %d pages crawled ═══", pages_visited)


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────

async def run_all_portals(portal_name_filter=None):
    for portal in config.get("portals", []):
        if portal_name_filter and portal["name"] != portal_name_filter:
            continue
        await crawl_portal(portal)


async def scheduler(portal_name_filter=None):
    while True:
        await run_all_portals(portal_name_filter)
        intervals = [
            p.get("crawl_interval_minutes", 60)
            for p in config.get("portals", [])
            if p.get("crawl_interval_minutes", 0) > 0
        ]
        wait_min = min(intervals) if intervals else 60
        logger.info("Next crawl in %d min", wait_min)
        await asyncio.sleep(wait_min * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    init_db()
    if args.once:
        asyncio.run(run_all_portals(args.portal))
    else:
        asyncio.run(scheduler(args.portal))


# ─────────────────────────────────────────────────────────────────────────────
# Multi-portal router — routes each portal to its dedicated crawler
# ─────────────────────────────────────────────────────────────────────────────

# Map portal name → crawler module function
PORTAL_CRAWLERS = {
    "EPR PLASTIC": "crawl_portal",    # this file
    "EPR EWASTE":  "crawl_ewaste",    # crawler_ewaste.py
}


async def run_all_portals(portal_name_filter=None):
    for portal in config.get("portals", []):
        name = portal["name"]
        if portal_name_filter and name != portal_name_filter:
            continue

        if name == "EPR EWASTE":
            from crawler_ewaste import crawl_ewaste_portal
            await crawl_ewaste_portal(portal)

        elif name == "EPR BATTERY":
            from crawler_battery import crawl_battery_portal
            await crawl_battery_portal(portal)

        elif name == "EPR ELV":
            from crawler_elv import crawl_elv_portal
            await crawl_elv_portal(portal)

        elif name == "EPR TYRES":
            from crawler_tyres import crawl_tyres_portal
            await crawl_tyres_portal(portal)

        elif name == "EPR USEDOIL":
            from crawler_usedoil import crawl_usedoil_portal
            await crawl_usedoil_portal(portal)

        elif name == "EPR PLASTIC":
            await crawl_portal(portal)

        else:
            logger.warning("Unknown portal '%s' — using default plastic crawler", name)
            await crawl_portal(portal)


async def scheduler(portal_name_filter=None):
    while True:
        await run_all_portals(portal_name_filter)
        intervals = [
            p.get("crawl_interval_minutes", 60)
            for p in config.get("portals", [])
            if p.get("crawl_interval_minutes", 0) > 0
        ]
        wait_min = min(intervals) if intervals else 60
        logger.info("Next crawl in %d min", wait_min)
        await asyncio.sleep(wait_min * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    init_db()
    if args.once:
        asyncio.run(run_all_portals(args.portal))
    else:
        asyncio.run(scheduler(args.portal))