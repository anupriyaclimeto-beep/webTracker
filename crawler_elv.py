"""
crawler_elv.py — CPCB EPR ELV Portal Crawler
URL: https://eprelv.cpcb.gov.in/

Same pattern as all other CPCB EPR crawlers.
Steps auto-detect what's available on the navbar.
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
    upload_to_cloudinary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
import shutil

with open("config.json") as f:
    config = json.load(f)

from storage import ARCHIVE_DIR
PORTAL_NAME = "EPR ELV"
HOME_URL    = "https://eprelv.cpcb.gov.in/"


# ── Helpers (identical pattern to crawler_battery.py / crawler_ewaste.py) ─────

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


async def diff_and_store(url, snap, har_path):
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

    update_baseline(
        portal=PORTAL_NAME, url=url,
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
                save_diff(portal=PORTAL_NAME, url=url,
                          diff_type=diff_type, diff_detail=diff_data,
                          screenshot_url=screenshot_url, html_url=html_url)
                logger.info("  Change: %s | %s", url, diff_type)
    # Cleanup local archive folder
    try:
        _snap_dir = Path(snap["screenshot_path"]).parent
        shutil.rmtree(_snap_dir)
        logger.info("✓ Cleaned up local archive %s", _snap_dir)
    except Exception as e:
        logger.warning("Cleanup failed for %s: %s", snap.get("screenshot_path", ""), e)


async def scroll_and_stitch(page) -> bytes:
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
        logger.info("  scrollY=%dpx piece=%d", actual_y, len(pieces))
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
    # Retry loop for government portal stability
    for attempt in range(3):
        try:
            logger.info("  Navigating to home page (attempt %d/3)...", attempt + 1)
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            break
        except Exception as e:
            if attempt == 2:
                logger.warning("  Timeout on domcontentloaded. Trying fallback to commit wait state...")
                try:
                    await page.goto(HOME_URL, wait_until="commit", timeout=25000)
                except Exception as final_err:
                    logger.error("  Failed all navigation attempts, continuing anyway: %s", final_err)
            else:
                logger.warning("  Navigation attempt %d failed: %s. Retrying in 3 seconds...", attempt + 1, e)
                await asyncio.sleep(3)
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await asyncio.sleep(2)


async def click_item(page, *labels) -> bool:
    for label in labels:
        for sel in [
            f"a:has-text('{label}')",
            f"button:has-text('{label}')",
            f"li:has-text('{label}') > a",
            f"nav a:has-text('{label}')",
            f"[class*='nav'] a:has-text('{label}')",
            f"[class*='menu'] a:has-text('{label}')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    logger.info("  Clicked: '%s'", label)
                    return True
            except Exception:
                continue
    logger.warning("  Not found: %s", labels)
    return False


async def do_dropdown(page, key, har_path, pv, *labels):
    """Click → single screenshot → escape. Returns updated pages_visited."""
    await goto_home(page)
    if await click_item(page, *labels):
        snap = await save_snapshot(page, key,
                                   await page.screenshot(full_page=False, type="png"))
        await diff_and_store(key, snap, har_path)
        pv += 1
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        logger.info("  %s done ✓", labels[0])
    return pv


async def do_scroll(page, key, har_path, pv, *labels):
    """Click → scroll & stitch whole page. Returns updated pages_visited."""
    await goto_home(page)
    if await click_item(page, *labels):
        snap = await save_snapshot(page, key, await scroll_and_stitch(page))
        await diff_and_store(key, snap, har_path)
        pv += 1
        logger.info("  %s done ✓", labels[0])
    return pv


# ── Main crawl ────────────────────────────────────────────────────────────────

async def crawl_elv_portal(portal_config: dict):
    har_dir  = Path(ARCHIVE_DIR) / PORTAL_NAME
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path = str(har_dir / f"{PORTAL_NAME}_network.har")

    crawl_id = start_crawl_log(PORTAL_NAME)
    pv       = 0

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

        # ── STEP 1: Home ──────────────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page ═══")
        await goto_home(page)
        snap = await save_snapshot(page, HOME_URL, await scroll_and_stitch(page))
        await diff_and_store(HOME_URL, snap, har_path)
        pv += 1
        logger.info("Home done ✓")

        # ── STEP 2: Important Communication — scroll (many items) ─────────────
        logger.info("═══ STEP 2: Important Communication ═══")
        pv = await do_scroll(
            page, HOME_URL + "__DROPDOWN_ImportantCommunication", har_path, pv,
            "Important Communication", "Notifications", "Circular"
        )

        # ── STEP 3: Rules — scroll (multiple rules) ───────────────────────────
        logger.info("═══ STEP 3: Rules ═══")
        pv = await do_scroll(
            page, HOME_URL + "__DROPDOWN_Rules", har_path, pv,
            "Rules", "ELV Rules", "EP Rules"
        )

        # ── STEP 4: National Dashboard ────────────────────────────────────────
        logger.info("═══ STEP 4: National Dashboard ═══")
        await goto_home(page)
        if await click_item(page, "National Dashboard", "Dashboard"):
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            await asyncio.sleep(3)
            snap = await save_snapshot(page, HOME_URL + "__PAGE_NationalDashboard",
                                       await scroll_and_stitch(page))
            await diff_and_store(HOME_URL + "__PAGE_NationalDashboard", snap, har_path)
            pv += 1
            logger.info("  National Dashboard done ✓")

        # ── STEP 5: SOP — single screenshot ──────────────────────────────────
        logger.info("═══ STEP 5: SOP ═══")
        pv = await do_dropdown(
            page, HOME_URL + "__DROPDOWN_SOP", har_path, pv,
            "SOP", "SOP for Registration"
        )

        # ── STEP 6: Guidance Manuals — single screenshot ──────────────────────
        logger.info("═══ STEP 6: Guidance Manuals ═══")
        pv = await do_dropdown(
            page, HOME_URL + "__DROPDOWN_GuidanceManuals", har_path, pv,
            "Guidance Manuals", "Guidance Manual"
        )

        # ── STEP 7: FAQs ─────────────────────────────────────────────────────
        logger.info("═══ STEP 7: FAQs ═══")
        await goto_home(page)
        if await click_item(page, "FAQs", "FAQ"):
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(2)
            snap = await save_snapshot(page, HOME_URL + "__PAGE_FAQs",
                                       await scroll_and_stitch(page))
            await diff_and_store(HOME_URL + "__PAGE_FAQs", snap, har_path)
            pv += 1
            logger.info("  FAQs done ✓")

        # ── STEP 8: Lodge Complaint — single screenshot ───────────────────────
        logger.info("═══ STEP 8: Lodge Complaint ═══")
        pv = await do_dropdown(
            page, HOME_URL + "__DROPDOWN_LodgeComplaint", har_path, pv,
            "Lodge Complaint"
        )

        # ── STEP 9: Important Documents — scroll (if present) ─────────────────
        logger.info("═══ STEP 9: Important Documents ═══")
        pv = await do_scroll(
            page, HOME_URL + "__DROPDOWN_ImportantDocuments", har_path, pv,
            "Important Documents", "Important Links"
        )

        await context.close()
        await browser.close()

    finish_crawl_log(crawl_id, pv, status="done")
    logger.info("═══ EPR ELV ALL DONE: %d pages ═══", pv)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    portal_cfg = next(
        (p for p in config.get("portals", []) if p["name"] == PORTAL_NAME),
        {"name": PORTAL_NAME, "auth": "none"},
    )
    asyncio.run(crawl_elv_portal(portal_cfg))