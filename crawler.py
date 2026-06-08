"""
crawler.py — CPCB EPR Plastic Portal Crawler + Multi-Portal Router

Routes:
  EPR PLASTIC  → crawl_portal()       (this file)
  EPR EWASTE   → crawler_ewaste.py
  EPR BATTERY  → crawler_battery.py
  EPR TYRES    → crawler_tyres.py
  EPR ELV      → crawler_elv.py
  EPR USEDOIL  → crawler_usedoil.py

EPR Plastic crawl — two phases:

  PHASE 1 — Headless (public, pre-login):
    1.  Home page                        → scroll & stitch
    2.  Plastic Waste Management         → dropdown screenshot
    3.  About EPR                        → dropdown screenshot
    4.  About EPR sub-pages (4 pages)    → scroll & stitch each
    5.  Important Documents              → click dropdown + scroll page
    6.  Bulk Upload                      → click dropdown + viewport screenshot
    7.  Lodge Complaint                  → click dropdown + viewport screenshot
    8.  SOP                              → click dropdown + viewport screenshot

  PHASE 2 — Headful persistent context (post-login):
    9+. All pages in config post_login_pages list
        - First run   : browser opens, user logs in manually, profile saved to disk
        - After that  : session restored from disk automatically, no interaction needed
        - Session dead: browser re-opens for re-login, profile refreshed

Flag files written during run (same pattern as .crawler.pid):
  .login_needed  → app.py shows amber "waiting for login" banner
"""

import asyncio
import os
os.environ.setdefault("PWDEBUG", "0")
import io
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from auth import (
    handle_auth,
    ensure_logged_in,
    get_profile_dir,
    profile_exists,
)
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
HOME_URL = "https://eprplastic.cpcb.gov.in/#/plastic/home"
BASE_URL = "https://eprplastic.cpcb.gov.in/"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def safe_goto(page, url: str, *, label: str = ""):
    """Navigate with up to 3 retries — resilient against govt-portal timeouts."""
    tag = f" [{label}]" if label else ""
    for attempt in range(3):
        try:
            logger.info("  Navigating to%s (attempt %d/3) ...", tag, attempt + 1)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            break
        except Exception as e:
            if attempt == 2:
                logger.warning("  domcontentloaded timed out%s. Trying commit wait ...", tag)
                try:
                    await page.goto(url, wait_until="commit", timeout=25000)
                except Exception as final_err:
                    logger.error("  All navigation attempts failed%s: %s", tag, final_err)
            else:
                logger.warning("  Attempt %d failed%s: %s. Retrying in 3s ...", attempt + 1, tag, e)
                await asyncio.sleep(3)
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await asyncio.sleep(2)


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

    _snap_dir      = Path(snap["screenshot_path"]).parent
    _diff_img_path = str(_snap_dir / "diff_highlight.png")

    diff_result = await run_all_diffs(
        portal_name=portal_name, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
        diff_image_save_path=_diff_img_path,
    )

    screenshot_url = upload_to_cloudinary(snap["screenshot_path"], resource_type="image")
    html_url       = upload_to_cloudinary(snap["html_path"],        resource_type="raw")
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


# ── Browser config helper ─────────────────────────────────────────────────────

def _browser_args():
    return [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]

def _user_agent():
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )

def _viewport():
    browser_cfg = config.get("browser", {})
    return {
        "width":  browser_cfg.get("viewport", {}).get("width",  1280),
        "height": browser_cfg.get("viewport", {}).get("height",  900),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EPR Plastic crawl
# ══════════════════════════════════════════════════════════════════════════════

async def crawl_portal(portal_config: dict):
    portal_name = portal_config["name"]
    har_dir     = Path(ARCHIVE_DIR) / portal_name
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path    = str(har_dir / f"{portal_name}_network.har")

    crawl_id      = start_crawl_log(portal_name)
    pages_visited = 0
    logger.info("Starting crawl for portal: %s (crawl_id=%s)", portal_name, crawl_id)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Headless: public pre-login pages (steps 1–8)
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("━" * 60)
    logger.info("PHASE 1 — Headless pre-login crawl (steps 1–8)")
    logger.info("━" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_browser_args())
        context = await browser.new_context(
            viewport=_viewport(),
            record_har_path=har_path,
            ignore_https_errors=True,
            user_agent=_user_agent(),
        )
        page = await context.new_page()

        # Auth (public for pre-login phase — just navigate)
        try:
            await handle_auth(page, portal_config)
        except Exception as e:
            logger.error("Auth failed: %s", e)
            await browser.close()
            finish_crawl_log(crawl_id, 0, status="error")
            return

        # ── STEP 1: Home page ─────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page — scroll & stitch ═══")
        await safe_goto(page, HOME_URL, label="Home")
        snap = await save_snapshot(page, portal_name, HOME_URL,
                                   await scroll_and_stitch(page))
        await diff_and_store(portal_name, HOME_URL, snap, har_path)
        pages_visited += 1
        logger.info("Home page done ✓ | pages_visited=%d", pages_visited)

        # ── STEP 2: Plastic Waste Management dropdown ──────────────────────
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

        # ── STEP 3: About EPR dropdown ────────────────────────────────────
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

        # ── STEP 4: About EPR sub-pages ───────────────────────────────────
        about_epr_subpages = [
            ("Categories Of Plastic Waste", "#/plastic/home/categoriesepr"),
            ("EPR Target",                  "#/plastic/home/eprtargets"),
            ("Responsibility Of PIBOs",     "#/plastic/home/pibopwp"),
            ("Plastic Waste Processing",    "#/plastic/home/plasticwaste"),
        ]
        for idx, (label, item_hash) in enumerate(about_epr_subpages, start=1):
            logger.info("═══ STEP 4.%d: %s ═══", idx, label)
            item_url = BASE_URL + item_hash
            await safe_goto(page, BASE_URL, label=label)
            await page.evaluate(f"window.location.hash = '{item_hash}'")
            await asyncio.sleep(1)
            item_snap = await save_snapshot(page, portal_name, item_url,
                                            await scroll_and_stitch(page))
            await diff_and_store(portal_name, item_url, item_snap, har_path)
            pages_visited += 1
            logger.info("  ✓ '%s' saved | pages_visited=%d", label, pages_visited)

        # ── STEP 5: Important Documents ───────────────────────────────────
        logger.info("═══ STEP 5: Important Documents dropdown ═══")
        imp_docs_key = HOME_URL + "__DROPDOWN_ImportantDocuments"
        await safe_goto(page, HOME_URL, label="Important Documents")
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
                    imp_opened = True
                    break
            except Exception:
                continue
        if imp_opened:
            snap5 = await save_snapshot(page, portal_name, imp_docs_key,
                                        await scroll_and_stitch(page))
            await diff_and_store(portal_name, imp_docs_key, snap5, har_path)
            pages_visited += 1
            logger.info("  Important Documents done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Important Documents' link")

        # ── STEP 6: Bulk Upload ───────────────────────────────────────────
        logger.info("═══ STEP 6: Bulk Upload dropdown ═══")
        bulk_upload_key = HOME_URL + "__DROPDOWN_BulkUpload"
        await safe_goto(page, HOME_URL, label="Bulk Upload")
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
                    bulk_opened = True
                    break
            except Exception:
                continue
        if bulk_opened:
            snap6 = await save_snapshot(page, portal_name, bulk_upload_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, bulk_upload_key, snap6, har_path)
            pages_visited += 1
            logger.info("  Bulk Upload done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Bulk Upload' link")

        # ── STEP 7: Lodge Complaint ───────────────────────────────────────
        logger.info("═══ STEP 7: Lodge Complaint dropdown ═══")
        lodge_key = HOME_URL + "__DROPDOWN_LodgeComplaint"
        await safe_goto(page, HOME_URL, label="Lodge Complaint")
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
                    lodge_opened = True
                    break
            except Exception:
                continue
        if lodge_opened:
            snap7 = await save_snapshot(page, portal_name, lodge_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, lodge_key, snap7, har_path)
            pages_visited += 1
            logger.info("  Lodge Complaint done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'Lodge Complaint' link")

        # ── STEP 8: SOP ───────────────────────────────────────────────────
        logger.info("═══ STEP 8: SOP dropdown ═══")
        sop_key = HOME_URL + "__DROPDOWN_SOP"
        await safe_goto(page, HOME_URL, label="SOP")
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
                    sop_opened = True
                    break
            except Exception:
                continue
        if sop_opened:
            snap8 = await save_snapshot(page, portal_name, sop_key,
                                        await page.screenshot(full_page=False, type="png"))
            await diff_and_store(portal_name, sop_key, snap8, har_path)
            pages_visited += 1
            logger.info("  SOP done ✓ | pages_visited=%d", pages_visited)
        else:
            logger.warning("  Could not find 'SOP' link")

        await context.close()
        await browser.close()

    logger.info("PHASE 1 complete ✓ | pages_visited=%d", pages_visited)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Headful persistent context: post-login pages (steps 9+)
    # ══════════════════════════════════════════════════════════════════════════
    post_login_pages = portal_config.get("post_login_pages", [])
    if not post_login_pages:
        logger.info("No post_login_pages configured — skipping Phase 2")
        finish_crawl_log(crawl_id, pages_visited, status="done")
        logger.info("═══ EPR PLASTIC ALL DONE: %d pages crawled ═══", pages_visited)
        logger.info("CRAWL_FINISHED: %d pages", pages_visited)
        logger.info("ALL DONE — pages complete")
        return

    logger.info("━" * 60)
    logger.info("PHASE 2 — Persistent context post-login crawl (steps 9+)")
    logger.info("━" * 60)

    profile_dir = get_profile_dir(portal_config)
    first_run   = not profile_exists(portal_config)

    if first_run:
        logger.info("First run — no browser profile found at %s", profile_dir)
        logger.info("Browser will open headful for manual login")
    else:
        logger.info("Browser profile found at %s — will attempt session restore", profile_dir)

    async with async_playwright() as p:
        # launch_persistent_context returns a context directly (not browser + context)
        persistent_ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,          # always headful for post-login (shows login window if needed)
            args=_browser_args() + ["--start-maximized"],
            viewport=_viewport(),
            ignore_https_errors=True,
            user_agent=_user_agent(),
        )

        # Load and restore cookies if cookies.json exists
        cookies_path = profile_dir / "cookies.json"
        if cookies_path.exists():
            try:
                cookies = json.loads(cookies_path.read_text())
                await persistent_ctx.add_cookies(cookies)
                logger.info("Session cookies restored from %s", cookies_path)
            except Exception as e:
                logger.warning("Failed to restore session cookies: %s", e)

        page = await persistent_ctx.new_page()

        # ── Ensure logged in (restore session or prompt manual login) ──────
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
            finish_crawl_log(crawl_id, pages_visited, status="error")
            return

        # ── Steps 9+: crawl each post-login page ──────────────────────────
        for step_idx, page_cfg in enumerate(post_login_pages, start=9):
            label      = page_cfg.get("label", f"PostLogin_{step_idx}")
            url        = page_cfg.get("url", "")
            method     = page_cfg.get("method", "scroll")  # "scroll" or "viewport"
            page_key   = HOME_URL + f"__LOGGEDIN_{label}"

            if not url:
                logger.warning("Step %d: no URL configured for '%s' — skipping", step_idx, label)
                continue

            logger.info("═══ STEP %d: %s (%s) ═══", step_idx, label, method)

            # Re-check session before each page (defensive — long crawls can expire mid-run)
            try:
                if not await _quick_session_check(page, portal_config):
                    logger.warning("Session dropped mid-crawl — attempting re-login")
                    await ensure_logged_in(page, portal_config)
            except Exception as e:
                logger.error("Re-login failed at step %d: %s — skipping remaining post-login pages", step_idx, e)
                break

            await safe_goto(page, url, label=label)

            if method == "scroll":
                screenshot_bytes = await scroll_and_stitch(page)
            else:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")

            snap = await save_snapshot(page, portal_name, page_key, screenshot_bytes)
            await diff_and_store(portal_name, page_key, snap, har_path)
            pages_visited += 1
            logger.info("  ✓ '%s' done | pages_visited=%d", label, pages_visited)

        # Save cookies at the end of crawl
        try:
            from auth import save_context_cookies
            await save_context_cookies(persistent_ctx, portal_config)
        except Exception as e:
            logger.warning("Failed to save session cookies at end of crawl: %s", e)

        # Profile is auto-saved to disk on context.close()
        await persistent_ctx.close()
        logger.info("Persistent browser profile saved to %s", profile_dir)

    finish_crawl_log(crawl_id, pages_visited, status="done")
    logger.info("═══ EPR PLASTIC ALL DONE: %d pages crawled ═══", pages_visited)
    logger.info("CRAWL_FINISHED: %d pages", pages_visited)
    logger.info("ALL DONE — pages complete")


async def _quick_session_check(page, portal_config: dict) -> bool:
    """
    Lightweight session check — does NOT navigate away.
    Just checks if the current URL looks like an authenticated page.
    Falls back to full is_logged_in() if ambiguous.
    """
    current_url = page.url
    login_url   = portal_config.get("login_url", "")

    # If we're already on a login/sign page, session is dead
    if "login" in current_url.lower() or "sign-in" in current_url.lower():
        return False

    # If we're on the home/public page (redirected after session expire), check properly
    if current_url.rstrip("/") == HOME_URL.rstrip("/") or current_url == BASE_URL:
        from auth import is_logged_in
        return await is_logged_in(page, portal_config)

    # Looks like we're on an authenticated page
    return True


# ── Multi-portal router ───────────────────────────────────────────────────────

async def run_all_portals(portal_name_filter: str | None = None):
    for portal in config.get("portals", []):
        name = portal["name"]

        if portal_name_filter and name != portal_name_filter:
            logger.info("Skipping portal: %s (filter=%s)", name, portal_name_filter)
            continue

        logger.info("══════════════════════════════════════════")
        logger.info("Starting portal: %s", name)
        logger.info("══════════════════════════════════════════")

        try:
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
        except Exception as e:
            logger.error("Portal %s failed: %s", name, e, exc_info=True)
            try:
                from storage import exec_db
                exec_db(
                    "UPDATE crawl_log SET status='failed', finished_at=datetime('now') "
                    "WHERE portal=? AND status='running'",
                    (name,)
                )
            except Exception:
                pass
            continue


async def scheduler(portal_name_filter: str | None = None):
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
    parser.add_argument("--portal", help="Run only this portal, e.g. 'EPR PLASTIC'")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--clear-profile",
        action="store_true",
        help="Delete the saved browser profile for the selected portal (forces re-login next run)"
    )
    args = parser.parse_args()
    init_db()

    if args.clear_profile:
        from auth import clear_profile
        portal_name = args.portal or "EPR PLASTIC"
        portal_cfg  = next(
            (p for p in config.get("portals", []) if p["name"] == portal_name), None
        )
        if portal_cfg:
            cleared = clear_profile(portal_cfg)
            print(f"Profile {'cleared' if cleared else 'did not exist'} for {portal_name}")
        else:
            print(f"Portal '{portal_name}' not found in config.json")
    elif args.once:
        asyncio.run(run_all_portals(args.portal))
    else:
        asyncio.run(scheduler(args.portal))