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

from __future__ import annotations

import asyncio

import asyncio

async def monitor_browser(context: BrowserContext, closed_event: asyncio.Event) -> None:
    """Continuously monitor the persistent context. If all pages close, set the event.
    This runs in a background task while the crawler proceeds.
    """
    while True:
        open_pages = [p for p in context.pages if not p.is_closed()]
        if not open_pages:
            closed_event.set()
            break
        await asyncio.sleep(1)

import os
os.environ.setdefault("PWDEBUG", "0")
import io
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
import sys
from playwright.async_api import async_playwright, BrowserContext
# CI mode detection - force headless / skip login pages in CI
CI_MODE = os.getenv("CI", "false").lower() == "true"

from PIL import Image
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import signal

from auth import (
    handle_auth,
    ensure_logged_in,
    get_profile_dir,
    profile_exists,
    launch_persistent_context,
    monitor_browser,
)
from diff_engine import run_all_diffs
from storage import (
    init_db, update_baseline, get_baseline,
    save_diff, start_crawl_log, finish_crawl_log,
    upload_to_cloudinary,
)
from storage import update_crawl_progress

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

from storage import ARCHIVE_DIR
HOME_URL = "https://eprplastic.cpcb.gov.in/#/plastic/home"
BASE_URL = "https://eprplastic.cpcb.gov.in/"

# Globals for signal handling / progress updates
CURRENT_CRAWL_ID = None
CURRENT_PAGES_VISITED = 0

def _handle_stop_signal(signum, frame):
    try:
        logger.info("Received stop signal (%s). Flushing crawl progress.", signum)
        if CURRENT_CRAWL_ID is not None:
            try:
                update_crawl_progress(CURRENT_CRAWL_ID, CURRENT_PAGES_VISITED)
            except Exception as e:
                logger.warning("Failed to update progress on signal: %s", e)
            try:
                finish_crawl_log(CURRENT_CRAWL_ID, CURRENT_PAGES_VISITED, status="stopped")
            except Exception as e:
                logger.warning("Failed to finish crawl log on signal: %s", e)
    finally:
        try:
            import sys
            sys.exit(0)
        except Exception:
            pass

# Register handlers
signal.signal(signal.SIGINT, _handle_stop_signal)
try:
    signal.signal(signal.SIGTERM, _handle_stop_signal)
except Exception:
    # SIGTERM may not be available on Windows
    pass

# ── Helpers ────────────────------------------------------------------------───

def normalize_url(url: str) -> str:
    return url.lower().replace("https://", "").replace("http://", "").rstrip("/")


async def discover_sidebar_pages(page, portal_config) -> list:
    """
    Dynamically finds and expands all dropdowns in the sidebar/navigation panel,
    extracts all valid links, and returns a list of dictionaries with label, url, and method.
    """
    logger.info("Starting dynamic sidebar page discovery...")
    # 1. Wait for page/sidebar to be loaded
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(2)
    
    # 2. Try to locate the sidebar element
    sidebar_selectors = [
        "aside", "nav", ".sidebar", ".left-sidebar", "app-sidebar", 
        "app-left-menu", ".main-sidebar", "[class*='sidebar']", "[class*='menu']"
    ]
    sidebar = None
    for sel in sidebar_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                sidebar = el
                logger.info("Found sidebar container matching selector: %s", sel)
                break
        except Exception:
            continue
    
    if sidebar is None:
        logger.warning("Could not find sidebar container — falling back to page body")
        sidebar = page.locator("body")

    # 3. Find and click dropdown toggles to expand all sub-menus
    dropdown_labels = [
        "Producer", "Road Making Declaration", "PIBO Operations", "Annual Filings",
        "Operations", "Filings", "Registration", "Declaration"
    ]
    
    caret_selectors = [
        "i[class*='arrow']", "i[class*='chevron']", "i[class*='caret']", "i[class*='angle']",
        "mat-icon:has-text('keyboard_arrow_down')", "mat-icon:has-text('expand_more')",
        ".caret", ".arrow", "[class*='arrow']", "[class*='chevron']"
    ]
    
    toggles = []
    # Check by labels
    for label in dropdown_labels:
        loc = sidebar.locator(f"a:has-text('{label}'), li:has-text('{label}'), div:has-text('{label}')").first
        try:
            if await loc.is_visible(timeout=1000):
                toggles.append(loc)
        except Exception:
            pass
            
    # Check by caret selectors
    for sel in caret_selectors:
        try:
            locs = sidebar.locator(sel)
            count = await locs.count()
            for i in range(count):
                loc = locs.nth(i)
                # Walk up to the clickable parent
                parent = loc.locator("xpath=./ancestor::*[self::a or self::li or self::button or self::div][1]")
                if await parent.is_visible(timeout=500):
                    toggles.append(parent)
        except Exception:
            pass

    # De-duplicate toggles by element handles
    unique_toggles = []
    seen_handles = set()
    for t in toggles:
        try:
            h = await t.element_handle()
            if h and h not in seen_handles:
                seen_handles.add(h)
                unique_toggles.append(t)
        except Exception:
            pass

    logger.info("Found %d potential dropdown toggles to expand", len(unique_toggles))
    for idx, t in enumerate(unique_toggles):
        try:
            text = (await t.inner_text()).split("\n")[0].strip()
            if any(w in text.lower() for w in ["logout", "signout", "exit", "home", "dashboard"]):
                continue
                
            # Check if it is already expanded
            is_expanded = False
            for attr in ["aria-expanded", "aria-selected"]:
                val = await t.get_attribute(attr)
                if val == "true":
                    is_expanded = True
                    break
            if not is_expanded:
                cls = await t.get_attribute("class") or ""
                if any(w in cls.lower() for w in ["active", "expanded", "open", "show"]):
                    is_expanded = True
            
            if is_expanded:
                logger.info("  Toggle [%d]: '%s' is already expanded, skipping click", idx, text)
                continue

            logger.info("  Clicking toggle [%d]: '%s' to expand", idx, text)
            await t.click()
            await asyncio.sleep(0.8) # wait for animation
        except Exception as e:
            logger.debug("Failed to click toggle %d: %s", idx, e)

    # 4. Collect all links (a tags) in the sidebar
    links_loc = sidebar.locator("a")
    count = await links_loc.count()
    logger.info("Scanning %d 'a' elements in sidebar...", count)
    
    discovered_pages = []
    seen_urls = set()
    
    for i in range(count):
        try:
            link = links_loc.nth(i)
            if not await link.is_visible():
                continue
            
            text = (await link.inner_text()).strip().replace("\n", " ")
            href = await link.get_attribute("href")
            router_link = await link.get_attribute("routerlink")
            
            # Resolve URL
            url = href or router_link or ""
            if not url or url.startswith("javascript:") or url == "#" or url == "/":
                continue
                
            # Clean up / construct absolute URL
            if url.startswith("#/"):
                base = portal_config["url"].split("#")[0].rstrip("/")
                url = f"{base}/{url}"
            elif url.startswith("/"):
                base = portal_config["url"].split("#")[0].rstrip("/")
                from urllib.parse import urlparse
                parsed = urlparse(base)
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
            elif not url.startswith("http"):
                base = portal_config["url"].split("#")[0].rstrip("/")
                url = f"{base}/{url}"
                
            # Skip logouts, external links
            text_lower = text.lower()
            if any(w in text_lower for w in ["logout", "sign out", "signout", "exit", "log out"]):
                continue
            # Skip duplicate urls
            if url in seen_urls:
                continue
                
            seen_urls.add(url)
            
            # Generate safe label
            label = re.sub(r"[^a-zA-Z0-9_]", "_", text).strip("_")
            if not label:
                label = f"Page_{len(discovered_pages) + 1}"
                
            discovered_pages.append({
                "label": label,
                "url": url,
                "method": "scroll"
            })
            logger.info("  Discovered page: label='%s', url='%s'", label, url)
        except Exception as e:
            logger.warning("Error processing link %d: %s", i, e)
            
    return discovered_pages


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
    # If HTML diff errored, do not upload or update baseline — log and skip
    try:
        html_res = diff_result.get("results", {}).get("html", {}) if diff_result and diff_result.get("results") else {}
        if html_res.get("error"):
            logger.error("HTML diff failed — baseline NOT updated for %s: %s", url, html_res.get("error"))
            # Cleanup local archive folder and skip uploads/updates
            try:
                shutil.rmtree(_snap_dir)
                logger.info("✓ Cleaned up local archive %s", _snap_dir)
            except Exception as e:
                logger.warning("Cleanup failed for %s: %s", snap.get("screenshot_path", ""), e)
            return
    except Exception:
        # defensive: if diff_result is None or unexpected structure, avoid uploading/updating
        logger.error("HTML diff result missing or malformed — baseline NOT updated for %s", url)
        try:
            shutil.rmtree(_snap_dir)
        except Exception:
            pass
        return

    # Upload to Cloudinary (only if html diff succeeded)
    screenshot_url = upload_to_cloudinary(snap["screenshot_path"], resource_type="image")
    html_url       = upload_to_cloudinary(snap["html_path"],        resource_type="raw")
    if screenshot_url:
        logger.info("  Cloudinary screenshot: %s", screenshot_url)
    if html_url:
        logger.info("  Cloudinary HTML:       %s", html_url)

    # If there was no previous baseline, create the initial baseline now
    # (we do not create a 'change' record for first snapshot).
    if not baseline:
        try:
            update_baseline(
                portal=portal_name, url=url,
                html_path=snap["html_path"],
                screenshot_path=snap["screenshot_path"],
                har_path=har_path,
                screenshot_url=screenshot_url,
                html_url=html_url,
            )
            logger.info("  Initial baseline created for %s", url)
        except Exception as e:
            logger.warning("  Failed to create initial baseline for %s: %s", url, e)
        try:
            shutil.rmtree(_snap_dir)
            logger.info("✓ Cleaned up local archive %s", _snap_dir)
        except Exception:
            pass
        return

    # --- Decide whether to persist each diff based on stricter rules ---
    saved_any = False
    if diff_result and diff_result.get("results"):
        from storage import get_conn, USE_SUPABASE
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            try:
                should_save = False
                if diff_type == "visual":
                    ratio = float(diff_data.get("change_ratio") or 0.0)
                    pixels = int(diff_data.get("changed_pixels") or 0)
                    # RULE 1: Only save if ratio > 0.05 and pixels > 0
                    if ratio > config.get("diff", {}).get("visual_change_min_ratio", 0.05) and pixels > 0:
                        should_save = True
                    else:
                        # delete any previously inserted trivial visual rows for this url
                        try:
                            if USE_SUPABASE:
                                conn = get_conn()
                                with conn.cursor() as cur:
                                    cur.execute(
                                        "DELETE FROM public.changes WHERE portal=%s AND url=%s AND diff_type='visual' AND (COALESCE((diff_detail->>'change_ratio')::float, 0) < %s OR COALESCE((diff_detail->>'changed_pixels')::int,0) = 0)",
                                        (portal_name, url, config.get("diff", {}).get("visual_change_min_ratio", 0.05))
                                    )
                                    conn.commit()
                                conn.close()
                        except Exception:
                            pass
                elif diff_type == "html":
                    # RULE 2: Only save if >=10 real words changed OR diff_lines >=3
                    words_changed = int(diff_data.get("words_changed") or 0) if diff_data.get("words_changed") is not None else 0
                    diff_lines = int(diff_data.get("diff_lines") or 0)
                    meaningful = diff_data.get("meaningful_html_change", False)
                    if words_changed >= 10 or diff_lines >= 3 or meaningful:
                        should_save = True
                    else:
                        # delete trivial html changes if present (only for Supabase)
                        try:
                            if USE_SUPABASE:
                                conn = get_conn()
                                with conn.cursor() as cur:
                                    cur.execute(
                                        "DELETE FROM public.changes WHERE portal=%s AND url=%s AND diff_type='html' AND (COALESCE((diff_detail->>'diff_lines')::int,0) < %s AND COALESCE((diff_detail->>'words_changed')::int,0) < %s)",
                                        (portal_name, url, 3, 10)
                                    )
                                    conn.commit()
                                conn.close()
                        except Exception:
                            pass
                # persist if decided
                if should_save:
                    try:
                        # If visual diff produced a local diff image, upload it and record URL in diff_detail
                        try:
                            if diff_type == "visual":
                                local_diff_path = diff_data.get("diff_image_path") or diff_data.get("diff_image_save_path")
                                if local_diff_path and os.path.exists(local_diff_path):
                                    uploaded = upload_to_cloudinary(local_diff_path, resource_type="image")
                                    if uploaded:
                                        diff_data["diff_image_url"] = uploaded
                        except Exception:
                            # non-fatal: continue saving diff even if upload fails
                            logger.debug("Failed to upload diff image for %s: %s", url, exc_info=True)

                        save_diff(portal=portal_name, url=url,
                                  diff_type=diff_type, diff_detail=diff_data,
                                  screenshot_url=screenshot_url, html_url=html_url)
                        saved_any = True
                        logger.info("  Change detected and saved: %s | %s", url, diff_type)
                    except Exception as e:
                        logger.error("Failed to save diff for %s %s: %s", url, diff_type, e)
                else:
                    logger.info("  Trivial/noise change ignored for %s | %s", url, diff_type)
            except Exception as e:
                logger.error("Error deciding save for diff_type=%s url=%s: %s", diff_type, url, e)

    # If we saved any diffs, update the baseline now (last)
    try:
        if saved_any:
            update_baseline(
                portal=portal_name, url=url,
                html_path=snap["html_path"],
                screenshot_path=snap["screenshot_path"],
                har_path=har_path,
                screenshot_url=screenshot_url,
                html_url=html_url,
            )
            logger.info("  Baseline updated after saving changes: %s", url)
    except Exception as e:
        logger.warning("Failed to update baseline after saving diffs for %s: %s", url, e)
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
    # register for signal-safe updates
    global CURRENT_CRAWL_ID, CURRENT_PAGES_VISITED
    CURRENT_CRAWL_ID = crawl_id
    pages_visited = 0
    CURRENT_PAGES_VISITED = pages_visited
    logger.info("Starting crawl for portal: %s (crawl_id=%s)", portal_name, crawl_id)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Headless: public pre-login pages (steps 1–8)
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("━" * 60)
    logger.info("PHASE 1 — Headless pre-login crawl (steps 1–8)")
    logger.info("━" * 60)

    async with async_playwright() as p:
        # Force headless in CI, otherwise use configured headless flag
        browser_headless = True if CI_MODE else config.get("browser", {}).get("headless", True)
        browser = await p.chromium.launch(headless=browser_headless, args=_browser_args())
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
            try:
                await browser.close()
            except Exception:
                pass
            finish_crawl_log(crawl_id, 0, status="error")
            return

        # ── STEP 1: Home page ─────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page — scroll & stitch ═══")
        await safe_goto(page, HOME_URL, label="Home")
        snap = await save_snapshot(page, portal_name, HOME_URL,
                                   await scroll_and_stitch(page))
        await diff_and_store(portal_name, HOME_URL, snap, har_path)
        pages_visited += 1
        CURRENT_PAGES_VISITED = pages_visited
        try:
            update_crawl_progress(crawl_id, pages_visited)
        except Exception as e:
            logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
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
        # In CI we skip post-login pages when no profile exists (cannot perform manual login)
        if CI_MODE and not profile_exists(portal_config):
            logger.warning("CI mode — no profile found for %s; skipping post-login pages.", portal_name)
            finish_crawl_log(crawl_id, pages_visited, status="done")
            logger.info("═══ EPR PLASTIC ALL DONE: %d pages crawled (CI skip) ═══", pages_visited)
            return
        persistent_ctx = await launch_persistent_context(p, portal_config)
        browser_closed_event = asyncio.Event()
        monitor_task = asyncio.create_task(monitor_browser(persistent_ctx, browser_closed_event))
        page = persistent_ctx.pages[0] if persistent_ctx.pages else await persistent_ctx.new_page()

        if browser_closed_event.is_set():
            logger.info("User closed the browser before any navigation – aborting crawl")
            finish_crawl_log(crawl_id, pages_visited, status="aborted")
            await persistent_ctx.close()
            return

        # ── Ensure logged in (restore session or prompt manual login) ──────
        try:
            await ensure_logged_in(page, portal_config, force_manual=first_run)
        except TimeoutError as e:
            logger.error("Login timed out: %s", e)
            await persistent_ctx.close()
            finish_crawl_log(crawl_id, pages_visited, status="error")
            return
        except Exception as e:
            logger.error("Login failed: %s", e)
            try:
                await persistent_ctx.close()
            except Exception:
                pass
            if "closed manually" in str(e) or browser_closed_event.is_set():
                finish_crawl_log(crawl_id, pages_visited, status="stopped")
                logger.info("Exiting crawler due to manual browser closure.")
                import sys
                sys.exit(0)
            finish_crawl_log(crawl_id, pages_visited, status="error")
            return

        if browser_closed_event.is_set():
            logger.info("User closed the browser after login – aborting crawl")
            finish_crawl_log(crawl_id, pages_visited, status="stopped")
            await persistent_ctx.close()
            import sys
            sys.exit(0)

        # ── Dynamic Sidebar Discovery ─────────────────────────────────────
        try:
            discovered = await discover_sidebar_pages(page, portal_config)
            logger.info("Discovered %d pages from sidebar", len(discovered))
        except Exception as e:
            logger.error("Failed to dynamically discover sidebar pages: %s", e)
            discovered = []

        # Merge configured pages and dynamically discovered pages
        final_pages = []
        seen_normalized = set()

        # 1. Add configured pages first (preserves labels and custom methods like pibo_unregistered)
        for page_cfg in post_login_pages:
            url_cfg = page_cfg.get("url", "")
            if url_cfg:
                final_pages.append(page_cfg)
                seen_normalized.add(normalize_url(url_cfg))

        # 2. Add discovered pages that aren't already configured
        for page_cfg in discovered:
            norm = normalize_url(page_cfg["url"])
            if norm not in seen_normalized:
                final_pages.append(page_cfg)
                seen_normalized.add(norm)

        logger.info("Total post-login pages to crawl: %d (configured: %d, newly discovered: %d)",
                    len(final_pages), len(post_login_pages), len(final_pages) - len(post_login_pages))

        # ── Steps 9+: crawl each post-login page ──────────────────────────
        # target post-login pages that should trigger special interactions and then stop
        target_pages = {
            "https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/material",
            "https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/sales",
        }
        visited_targets = set()

        async def try_select_unregistered(page) -> bool:
            """Try to open a registration-type select and choose 'Unregistered'."""
            # common selectors for mat-select or native select near label text
            select_selectors = [
                "mat-select[placeholder*='Registration Type']:not([disabled])",
                "mat-select:near(:text('Registration Type'), 100)",
                "select:near(:text('Registration Type'), 100)",
                "[class*='select']:near(:text('Registration Type'), 100)",
            ]
            option_selectors = [
                "mat-option:has-text('Unregistered')",
                ".mat-option:has-text('Unregistered')",
                "[role='option']:has-text('Unregistered')",
                ".dropdown-item:has-text('Unregistered')",
            ]
            try:
                for s in select_selectors:
                    try:
                        el = page.locator(s).first
                        if await el.is_visible(timeout=2000):
                            await el.click()
                            await asyncio.sleep(0.8)
                            # select option
                            for opt in option_selectors:
                                try:
                                    oel = page.locator(opt).first
                                    if await oel.is_visible(timeout=2000):
                                        await oel.click()
                                        await asyncio.sleep(0.8)
                                        return True
                                except Exception:
                                    continue
                    except Exception:
                        continue
            except Exception:
                pass
            return False

        for step_idx, page_cfg in enumerate(final_pages, start=9):
            label    = page_cfg.get("label", f"PostLogin_{step_idx}")
            url      = page_cfg.get("url", "")
            method   = page_cfg.get("method", "scroll")  # "scroll", "viewport", or "pibo_unregistered"
            page_key = HOME_URL + f"__LOGGEDIN_{label}"

            if not url:
                logger.warning("Step %d: no URL configured for '%s' — skipping", step_idx, label)
                continue

            logger.info("═══ STEP %d: %s (%s) ═══", step_idx, label, method)

            # Re-check session before each page
            try:
                if not await _quick_session_check(page, portal_config):
                    logger.warning("Session dropped mid-crawl — attempting re-login")
                    await ensure_logged_in(page, portal_config)
            except Exception as e:
                logger.error("Re-login failed at step %d: %s — skipping remaining pages", step_idx, e)
                if "closed manually" in str(e) or browser_closed_event.is_set():
                    browser_closed_event.set()
                break

            if browser_closed_event.is_set():
                logger.info("User closed the browser during crawl – aborting")
                break

            # Special deep-crawl mode for PIBO Unregistered Procurement
            if method == "pibo_unregistered":
                from pibo_crawler import crawl_pibo_unregistered_procurement
                sub_count = await crawl_pibo_unregistered_procurement(
                    page, portal_name, har_path,
                    save_snapshot, diff_and_store, scroll_and_stitch, safe_goto, HOME_URL
                )
                pages_visited += sub_count
                CURRENT_PAGES_VISITED = pages_visited
                try:
                    update_crawl_progress(crawl_id, pages_visited)
                except Exception as e:
                    logger.warning("Failed to update crawl progress: %s", e)
                logger.info("  PIBO Unregistered done | pages_visited=%d", pages_visited)
                continue

            await safe_goto(page, url, label=label)

            if method == "scroll":
                screenshot_bytes = await scroll_and_stitch(page)
            else:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")
            # If this is one of the target PIBO pages, try to select 'Unregistered'
            try:
                if url in target_pages:
                    ok = await try_select_unregistered(page)
                    if ok:
                        logger.info("Selected 'Unregistered' on %s", url)
                    visited_targets.add(url)
            except Exception as e:
                logger.warning("Failed special interaction on %s: %s", url, e)

            snap = await save_snapshot(page, portal_name, page_key, screenshot_bytes)
            await diff_and_store(portal_name, page_key, snap, har_path)
            pages_visited += 1
            CURRENT_PAGES_VISITED = pages_visited
            try:
                update_crawl_progress(crawl_id, pages_visited)
            except Exception as e:
                logger.warning("Failed to update crawl progress: %s", e)
            logger.info("  '%s' done | pages_visited=%d", label, pages_visited)

            # If we've visited all configured targets, finish crawl and exit
            if visited_targets >= target_pages:
                logger.info("All target post-login pages visited — finishing crawl.")
                finish_crawl_log(crawl_id, pages_visited, status="done")
                logger.info("═══ EPR PLASTIC ALL DONE: %d pages crawled (targets complete) ═══", pages_visited)
                return

        # Save cookies at the end of crawl
        try:
            from auth import save_context_cookies
            await save_context_cookies(persistent_ctx, portal_config)
        except Exception as e:
            logger.warning("Failed to save session cookies at end of crawl: %s", e)

        if not browser_closed_event.is_set():
            from auth import wait_for_user_to_close
            await wait_for_user_to_close(persistent_ctx)
            logger.info("Persistent browser profile saved to %s", profile_dir)
        else:
            await persistent_ctx.close()
        monitor_task.cancel()

    if browser_closed_event.is_set():
        finish_crawl_log(crawl_id, pages_visited, status="stopped")
        logger.info("Crawl aborted due to manual browser closure.")
        import sys
        sys.exit(0)

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


async def crawl_pibo_unregistered_procurement(page, portal_name: str, har_path: str) -> int:
    """
    Deep crawl of PIBO Operations → Unregistered Procurement.
    Steps:
      1. Navigate to Unregistered Procurement page
      2. Scroll full page to footer → screenshot
      3. Click "Add New" button → form modal opens
      4. Screenshot form (initial state)
      5. Click Registration Type dropdown → "Unregistered" option → screenshot
      6. Close & reopen form → click Entity Type dropdown → screenshot each option
      7. Close & reopen form → click Plastic Material Type dropdown → scroll options → screenshot
    Returns count of pages/states captured.
    """
    PIBO_URL   = "https://eprplastic.cpcb.gov.in/#/plastic/pibo-unregistered-procurement"
    BASE_KEY   = HOME_URL + "__LOGGEDIN_PIBO_Unregistered_Procurement"
    pv         = 0

    logger.info("═══ PIBO Unregistered Procurement — full deep crawl ═══")

    # ── 1. Navigate and scroll full page to footer ────────────────────────────
    logger.info("  Step 1: Navigate and scroll to footer")
    await safe_goto(page, PIBO_URL, label="PIBO Unregistered Procurement")
    screenshot_bytes = await scroll_and_stitch(page)
    snap = await save_snapshot(page, portal_name, BASE_KEY + "__fullpage", screenshot_bytes)
    await diff_and_store(portal_name, BASE_KEY + "__fullpage", snap, har_path)
    pv += 1
    logger.info("  Full page scrolled & stitched ✓")

    # ── Helper: open the "Add New" modal ──────────────────────────────────────
    async def open_add_new_modal() -> bool:
        """Click the Add New button and wait for modal to appear."""
        for sel in [
            "button:has-text('Add New')",
            "button:has-text('Add new')",
            "button:has-text('+ Add New')",
            "a:has-text('Add New')",
            ".btn:has-text('Add')",
            "[class*='add']:has-text('New')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    # Wait for modal
                    try:
                        await page.wait_for_selector(
                            ".modal, mat-dialog-container, [role='dialog'], .dialog-container",
                            timeout=5000
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                    logger.info("  Add New modal opened via: %s", sel)
                    return True
            except Exception:
                continue
        logger.warning("  Could not find 'Add New' button")
        return False

    # ── Helper: close modal ───────────────────────────────────────────────────
    async def close_modal():
        for sel in [
            "button:has-text('×')", "button:has-text('Close')",
            ".modal-header .close", ".btn-close",
            "[aria-label='Close']", "mat-dialog-container button:first-child",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)

    # ── Helper: click a dropdown in the form and screenshot ───────────────────
    async def click_form_dropdown_and_screenshot(dropdown_label: str, key_suffix: str) -> bool:
        """
        Find a dropdown by its label text, click it to open, scroll through options,
        and take a full screenshot of the expanded dropdown.
        """
        for sel in [
            f"mat-select[placeholder*='{dropdown_label}']:not([disabled])",
            f"mat-select:near(:text('{dropdown_label}'), 100)",
            f"select:near(:text('{dropdown_label}'), 100)",
            f"[class*='select']:near(:text('{dropdown_label}'), 100)",
            f".ng-select:near(:text('{dropdown_label}'), 100)",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(1.2)
                    # Scroll dropdown options if present
                    try:
                        panel = page.locator(
                            "mat-option, .mat-option, .dropdown-item, .ng-option, [role='option']"
                        ).first
                        await panel.wait_for(timeout=3000)
                        # Scroll to bottom of options list
                        await page.evaluate("""
                            const panel = document.querySelector(
                                '.mat-select-panel, .cdk-overlay-pane, .dropdown-menu, .ng-dropdown-panel'
                            );
                            if (panel) panel.scrollTop = panel.scrollHeight;
                        """)
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass
                    snap = await save_snapshot(
                        page, portal_name,
                        BASE_KEY + f"__form__{key_suffix}",
                        await page.screenshot(full_page=False, type="png")
                    )
                    await diff_and_store(portal_name, BASE_KEY + f"__form__{key_suffix}", snap, har_path)
                    logger.info("  Dropdown '%s' captured ✓", dropdown_label)
                    # Close dropdown
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
        logger.warning("  Dropdown '%s' not found", dropdown_label)
        return False

    # ── 2. Open modal — initial screenshot ───────────────────────────────────
    logger.info("  Step 2: Open Add New modal (initial state)")
    if await open_add_new_modal():
        snap = await save_snapshot(
            page, portal_name,
            BASE_KEY + "__form__initial",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__initial", snap, har_path)
        pv += 1
        logger.info("  Form initial state captured ✓")

        # ── 3. Registration Type dropdown (Registered / Unregistered) ─────────
        logger.info("  Step 3: Registration Type dropdown")
        if await click_form_dropdown_and_screenshot("Registration Type", "RegistrationType_dropdown"):
            pv += 1

        # Select "Unregistered" option to reveal more fields ──────────────────
        logger.info("  Step 3b: Select 'Unregistered' option")
        for sel in [
            "mat-option:has-text('Unregistered')",
            ".mat-option:has-text('Unregistered')",
            "[role='option']:has-text('Unregistered')",
            ".dropdown-item:has-text('Unregistered')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    snap = await save_snapshot(
                        page, portal_name,
                        BASE_KEY + "__form__after_unregistered_selected",
                        await page.screenshot(full_page=False, type="png")
                    )
                    await diff_and_store(portal_name, BASE_KEY + "__form__after_unregistered_selected", snap, har_path)
                    pv += 1
                    logger.info("  'Unregistered' selected, new fields captured ✓")
                    break
            except Exception:
                continue

        # ── 4. Entity Type dropdown ──────────────────────────────────────────
        logger.info("  Step 4: Entity Type dropdown")
        if await click_form_dropdown_and_screenshot("Entity Type", "EntityType_dropdown"):
            pv += 1

        # ── 5. Plastic Material Type dropdown ────────────────────────────────
        logger.info("  Step 5: Plastic Material Type dropdown")
        if await click_form_dropdown_and_screenshot("Plastic Material Type", "PlasticMaterialType_dropdown"):
            pv += 1

        # ── 6. Final form screenshot (all visible fields filled/empty) ────────
        logger.info("  Step 6: Final form state screenshot")
        snap = await save_snapshot(
            page, portal_name,
            BASE_KEY + "__form__final_state",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__final_state", snap, har_path)
        pv += 1

        # Close modal
        await close_modal()
        logger.info("  Modal closed ✓")
    else:
        logger.warning("  Skipping form screenshots — Add New button not found")

    logger.info("  PIBO Unregistered Procurement complete | sub-pages captured: %d", pv)
    return pv


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