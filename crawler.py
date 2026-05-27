"""
crawler_cpcb.py — CPCB EPR Plastic Portal Crawler

Does exactly 2 things:
  1. Home page → scroll step by step, stitch screenshots → save
  2. Click "Plastic Waste Management" → snapshot open dropdown → save → stop
"""

import asyncio
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
from storage import init_db, update_baseline, get_baseline, save_diff, start_crawl_log, finish_crawl_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

ARCHIVE_DIR = config["storage"]["archive_dir"]
HOME_URL = "https://eprplastic.cpcb.gov.in/#/plastic/home"


def make_archive_path(portal_name: str, key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", re.sub(r"https?://", "", key))
    safe = re.sub(r"_+", "_", safe).strip("_")[:180]
    path = Path(ARCHIVE_DIR) / portal_name / safe / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def scroll_and_stitch(page) -> bytes:
    """
    Scroll the page from top to bottom in viewport-height steps.
    At each step take a viewport screenshot, then stitch all pieces
    into one tall PNG. Returns the final PNG bytes.
    """
    viewport_w = page.viewport_size["width"]
    viewport_h = page.viewport_size["height"]

    # Scroll to top first
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

    total_height = await page.evaluate("document.body.scrollHeight")
    logger.info("Page height: %dpx, viewport: %dpx", total_height, viewport_h)

    pieces = []
    scroll_y = 0

    while scroll_y < total_height:
        await page.evaluate(f"window.scrollTo(0, {scroll_y})")
        await asyncio.sleep(0.4)   # let lazy content render at this position

        # Capture only the visible viewport (not full_page)
        shot = await page.screenshot(full_page=False, type="png")
        img = Image.open(io.BytesIO(shot))

        # How much of this screenshot is new (not already covered)?
        actual_scroll = await page.evaluate("window.scrollY")
        pieces.append((actual_scroll, img))

        scroll_y += viewport_h
        # Re-check height — page may have grown (lazy loading)
        total_height = await page.evaluate("document.body.scrollHeight")

    # Stitch pieces into one tall image
    stitched = Image.new("RGB", (viewport_w, total_height))
    for scroll_y_pos, img in pieces:
        stitched.paste(img, (0, scroll_y_pos))

    # Scroll back to top and wait for DOM to fully settle
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1.5)  # give Angular time to finish re-renders from scrolling

    out = io.BytesIO()
    stitched.save(out, format="PNG")
    logger.info("Stitched screenshot: %dx%d px from %d pieces", viewport_w, total_height, len(pieces))
    return out.getvalue()


async def save_snapshot(page, portal_name: str, key: str, screenshot_bytes: bytes) -> dict:
    """
    Save HTML + screenshot to archive.
    HTML is captured after scrolling is done and DOM has settled —
    so we get one clean stable snapshot with no duplicate/overlapping content.
    """
    # Wait for any pending Angular re-renders triggered by scrolling
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(0.5)

    html = await page.content()
    archive = make_archive_path(portal_name, key)
    html_path = archive / "snapshot.html"
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


async def diff_and_store(portal_name, url, snap, har_path):
    """Run diff, update baseline, save any changes."""
    baseline = get_baseline(portal_name, url)
    diff_result = await run_all_diffs(
        portal_name=portal_name, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
    )
    update_baseline(portal=portal_name, url=url,
                    html_path=snap["html_path"],
                    screenshot_path=snap["screenshot_path"],
                    har_path=har_path)
    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_data.get("changed"):
                save_diff(portal=portal_name, url=url,
                          diff_type=diff_type, diff_detail=diff_data)
                logger.info("  ✅ Change: %s | %s", url, diff_type)


async def crawl_portal(portal_config: dict):
    portal_name = portal_config["name"]
    har_dir = Path(ARCHIVE_DIR) / portal_name
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path = str(har_dir / f"{portal_name}_network.har")

    crawl_id = start_crawl_log(portal_name)
    pages_visited = 0

    async with async_playwright() as p:
        browser_cfg = config.get("browser", {})
        browser = await p.chromium.launch(
            headless=browser_cfg.get("headless", True),
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={
                "width": browser_cfg.get("viewport", {}).get("width", 1280),
                "height": browser_cfg.get("viewport", {}).get("height", 900),
            },
            record_har_path=har_path,
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            await handle_auth(page, portal_config)
        except Exception as e:
            logger.error("Auth failed: %s", e)
            await browser.close()
            finish_crawl_log(crawl_id, 0, status="error")
            return

        # ── STEP 1: Home page ────────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page — scroll & stitch ═══")
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(2)

        screenshot_bytes = await scroll_and_stitch(page)
        snap = await save_snapshot(page, portal_name, HOME_URL, screenshot_bytes)
        await diff_and_store(portal_name, HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home page done ✓")

        # ── STEP 2: Plastic Waste Management dropdown ────────────────────────
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
                    await asyncio.sleep(1.0)   # wait for dropdown to open
                    logger.info("  Dropdown opened")
                    clicked = True
                    break
            except Exception:
                continue

        if clicked:
            # Dropdown is open — just take a single viewport screenshot (no scroll)
            shot = await page.screenshot(full_page=False, type="png")
            snap2 = await save_snapshot(page, portal_name, dropdown_key, shot)
            await diff_and_store(portal_name, dropdown_key, snap2, har_path)
            pages_visited += 1

            await page.keyboard.press("Escape")
            logger.info("  Dropdown closed ✓")
        else:
            logger.warning("  Could not find 'Plastic Waste Management' link")

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ ALL DONE: %d pages crawled ═══", pages_visited)


async def run_all_portals(portal_name_filter=None):
    for portal in config.get("portals", []):
        if portal_name_filter and portal["name"] != portal_name_filter:
            continue
        await crawl_portal(portal)


async def scheduler(portal_name_filter=None):
    while True:
        await run_all_portals(portal_name_filter)
        intervals = [p.get("crawl_interval_minutes", 60) for p in config.get("portals", [])
                     if p.get("crawl_interval_minutes", 0) > 0]
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