"""
crawler.py — CPCB EPR Plastic Portal Crawler + Multi-Portal Router

Routes:
  EPR PLASTIC  → crawl_portal()       (this file)
  EPR EWASTE   → crawler_ewaste.py
  EPR BATTERY  → crawler_battery.py
  EPR TYRES    → crawler_tyres.py
  EPR ELV      → crawler_elv.py
  EPR USEDOIL  → crawler_usedoil.py

Plastic portal steps:
  1. Home page                        → scroll & stitch
  2. Plastic Waste Management         → dropdown screenshot
  3. About EPR                        → dropdown screenshot
  4. About EPR sub-pages (4 pages)    → scroll & stitch each
  5. Important Documents              → click dropdown + scroll page
  6. Bulk Upload                      → click dropdown + viewport screenshot
  7. Lodge Complaint                  → click dropdown + viewport screenshot
  8. SOP                              → click dropdown + viewport screenshot
"""

import asyncio
import os
os.environ.setdefault("PWDEBUG", "0")
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
    upload_to_cloudinary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

from storage import ARCHIVE_DIR
HOME_URL    = "https://eprplastic.cpcb.gov.in/#/plastic/home"
BASE_URL    = "https://eprplastic.cpcb.gov.in/"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_archive_path(portal_name: str, key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", re.sub(r"https?://", "", key))
    safe = re.sub(r"_+", "_", safe).strip("_")[:180]
    path = Path(ARCHIVE_DIR) / portal_name / safe / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_snapshot(page, portal_name: str, key: str, screenshot_bytes: bytes) -> dict:
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

async def diff_and_store(portal_name: str, url: str, snap: dict, har_path: str):
    baseline = get_baseline(portal_name, url)

    # Save highlighted diff image alongside the snapshot
    from pathlib import Path as _Path
    _snap_dir      = _Path(snap["screenshot_path"]).parent
    _diff_img_path = str(_snap_dir / "diff_highlight.png")

    diff_result = await run_all_diffs(
        portal_name=portal_name, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
        diff_image_save_path=_diff_img_path,   # ← NEW
    )
    # Upload screenshot and HTML snapshot to Cloudinary
    screenshot_url = upload_to_cloudinary(snap["screenshot_path"], resource_type="image")
    html_url       = upload_to_cloudinary(snap["html_path"], resource_type="raw")
    if screenshot_url:
        logger.info("  Cloudinary screenshot: %s", screenshot_url)
    if html_url:
        logger.info("  Cloudinary HTML:       %s", html_url)

    update_baseline(
        portal=portal_name, url=url,
        html_path=snap["html_path"],
        screenshot_path=snap["screenshot_path"],
        har_path=har_path,
        screenshot_url=screenshot_url,
        html_url=html_url,
    )

    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            if diff_data.get("changed"):
                save_diff(portal=portal_name, url=url,
                          diff_type=diff_type, diff_detail=diff_data,
                          screenshot_url=screenshot_url, html_url=html_url)
                logger.info("  Change detected: %s | %s", url, diff_type)
    # Cleanup local archive folder
    try:
        shutil.rmtree(_snap_dir)
        logger.info("✓ Cleaned up local archive %s", _snap_dir)
    except Exception as e:
        logger.warning("Cleanup failed for %s: %s", snap.get("screenshot_path", ""), e)


async def scroll_and_stitch(page) -> bytes:
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)
    total_h  = await page.evaluate("document.body.scrollHeight")
    logger.info("  Page scrollHeight=%dpx  viewport=%dpx", total_h, vh)
    pieces   = []
    scroll_y = 0
    while scroll_y < total_h:
        await page.evaluate(f"window.scrollTo(0, {scroll_y})")
        await asyncio.sleep(0.4)
        raw      = await page.screenshot(full_page=False, type="png")
        img      = Image.open(io.BytesIO(raw))
        actual_y = await page.evaluate("window.scrollY")
        pieces.append((actual_y, img))
        logger.info("  scrollY=%dpx  piece %d captured", actual_y, len(pieces))
        scroll_y += vh
        total_h   = await page.evaluate("document.body.scrollHeight")
    stitched = Image.new("RGB", (vw, total_h))
    for y_pos, img in pieces:
        stitched.paste(img, (0, y_pos))
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1.5)
    buf = io.BytesIO()
    stitched.save(buf, format="PNG")
    logger.info("  Stitched: %dx%d px from %d pieces", vw, total_h, len(pieces))
    return buf.getvalue()


# ── EPR Plastic crawl ─────────────────────────────────────────────────────────

async def crawl_portal(portal_config: dict):
    portal_name = portal_config["name"]
    har_dir     = Path(ARCHIVE_DIR) / portal_name
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path    = str(har_dir / f"{portal_name}_network.har")

    crawl_id      = start_crawl_log(portal_name)
    pages_visited = 0
    logger.info("Starting crawl for portal: %s (crawl_id=%s)", portal_name, crawl_id)

    async with async_playwright() as p:
        browser_cfg = config.get("browser", {})
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
        snap = await save_snapshot(page, portal_name, HOME_URL,
                                   await scroll_and_stitch(page))
        await diff_and_store(portal_name, HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home page done ✓ | pages_visited=%d", pages_visited)

        # ── STEP 2: Plastic Waste Management dropdown ─────────────────────────
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
            snap2 = await save_snapshot(page, portal_name, dropdown_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, dropdown_key, snap2, har_path)
            pages_visited += 1
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.info("  Plastic Waste Management dropdown done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Plastic Waste Management' link")

        # ── STEP 3: About EPR dropdown ────────────────────────────────────────
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
            snap3 = await save_snapshot(page, portal_name, about_epr_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, about_epr_key, snap3, har_path)
            pages_visited += 1
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.info("  About EPR dropdown done ✓ | pages_visited=%d", pages_visited)
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
            item_snap = await save_snapshot(page, portal_name, item_url,
                                            await scroll_and_stitch(page))
            await diff_and_store(portal_name, item_url, item_snap, har_path)
            pages_visited += 1
            logger.info("  ✓ '%s' saved | pages_visited=%d", label, pages_visited)

        # ── STEP 5: Important Documents — click + scroll page ─────────────────
        logger.info("═══ STEP 5: Important Documents dropdown — click + scroll page ═══")
        imp_docs_key = HOME_URL + "__DROPDOWN_ImportantDocuments"
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)
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
                    await asyncio.sleep(1.5)
                    logger.info("  Dropdown opened — page is now scrollable")
                    imp_opened = True
                    break
            except Exception:
                continue
        if imp_opened:
            snap5 = await save_snapshot(page, portal_name, imp_docs_key,
                                        await scroll_and_stitch(page))
            await diff_and_store(portal_name, imp_docs_key, snap5, har_path)
            pages_visited += 1
            logger.info("  Important Documents full snapshot done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Important Documents' link")

        # ── STEP 6: Bulk Upload — click + viewport screenshot ─────────────────
        logger.info("═══ STEP 6: Bulk Upload dropdown — click + screenshot ═══")
        bulk_upload_key = HOME_URL + "__DROPDOWN_BulkUpload"
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)
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
                    await asyncio.sleep(1.5)
                    logger.info("  Bulk Upload dropdown opened")
                    bulk_opened = True
                    break
            except Exception:
                continue
        if bulk_opened:
            snap6 = await save_snapshot(page, portal_name, bulk_upload_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, bulk_upload_key, snap6, har_path)
            pages_visited += 1
            logger.info("  Bulk Upload snapshot done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Bulk Upload' link")

        # ── STEP 7: Lodge Complaint — click + viewport screenshot ─────────────
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
            snap7 = await save_snapshot(page, portal_name, lodge_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, lodge_key, snap7, har_path)
            pages_visited += 1
            logger.info("  Lodge Complaint snapshot done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Lodge Complaint' link")

        # ── STEP 8: SOP — click + viewport screenshot ─────────────────────────
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
            snap8 = await save_snapshot(page, portal_name, sop_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, sop_key, snap8, har_path)
            pages_visited += 1
            logger.info("  SOP snapshot done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'SOP' link")

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ EPR PLASTIC ALL DONE: %d pages crawled ═══", pages_visited)
    # explicit finish markers for UI to detect in logs
    logger.info("CRAWL_FINISHED: %d pages", pages_visited)
    logger.info("ALL DONE — pages complete")


# ── Multi-portal router ───────────────────────────────────────────────────────
# ONE definition only — routes by portal name, respects --portal filter.

async def run_all_portals(portal_name_filter: str | None = None):
    """
    Iterate over portals in config.json.
    If portal_name_filter is set, only run that one portal.
    """
    for portal in config.get("portals", []):
        name = portal["name"]

        # ── honour --portal filter ────────────────────────────────────────────
        if portal_name_filter and name != portal_name_filter:
            logger.info("Skipping portal: %s (filter=%s)", name, portal_name_filter)
            continue

        logger.info("══════════════════════════════════════════")
        logger.info("Starting portal: %s", name)
        logger.info("══════════════════════════════════════════")

        if name == "EPR PLASTIC":
            await crawl_portal(portal)

        elif name == "EPR EWASTE":
            from crawler_ewaste import crawl_ewaste_portal
            await crawl_ewaste_portal(portal)

        elif name == "EPR BATTERY":
            from crawler_battery import crawl_battery_portal
            await crawl_battery_portal(portal)

        elif name == "EPR TYRES":
            from crawler_tyres import crawl_tyres_portal
            await crawl_tyres_portal(portal)

        elif name == "EPR ELV":
            from crawler_elv import crawl_elv_portal
            await crawl_elv_portal(portal)

        elif name == "EPR USEDOIL":
            from crawler_usedoil import crawl_usedoil_portal
            await crawl_usedoil_portal(portal)

        else:
            logger.warning("Unknown portal '%s' — skipping", name)
            continue

        logger.info("Portal %s finished ✓", name)


async def scheduler(portal_name_filter: str | None = None):
    """Run all portals on a loop, sleeping between runs."""
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CPCB EPR Portal Crawler")
    parser.add_argument(
        "--portal",
        help="Run only this portal, e.g. 'EPR PLASTIC' or 'EPR TYRES'",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no scheduler loop)",
    )
    args = parser.parse_args()
    init_db()
    if args.once:
        asyncio.run(run_all_portals(args.portal))
    else:
        asyncio.run(scheduler(args.portal))