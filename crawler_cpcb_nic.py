"""
crawler_cpcb_nic.py — CPCB main website (cpcb.nic.in)

Tracks:
  1. Home page (full stitch)
  2. All internal links from main nav (.sf-menu) — every dropdown / sub-menu page
"""

import asyncio
import io
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from PIL import Image
from playwright.async_api import async_playwright

os.environ.setdefault("PWDEBUG", "0")

from auth import handle_auth
from diff_engine import run_all_diffs
from storage import (
    init_db,
    update_baseline,
    get_baseline,
    save_diff,
    start_crawl_log,
    finish_crawl_log,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

ARCHIVE_DIR = config["storage"]["archive_dir"]
PORTAL_NAME = "CPCB NIC"
HOME_URL = "https://cpcb.nic.in/index.php"
BASE_HOST = "cpcb.nic.in"
MENU_SELECTOR = ".sf-menu"
SKIP_IN_HREF = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", "mailto:", "javascript:", "#")
# cpcb.nic.in returns 404 without trailing slash on directory-style paths
_FILE_PATH_SUFFIXES = (".php", ".html", ".htm", ".asp", ".aspx", ".jsp")


def normalize_url(url: str) -> str:
    """CPCB paths need a trailing slash (except index.php and other files)."""
    url = urldefrag(url.strip())[0]
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    path = parsed.path or "/"
    lower = path.lower()
    if path != "/" and not path.endswith("/"):
        if not any(lower.endswith(ext) for ext in _FILE_PATH_SUFFIXES):
            path = path + "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def make_archive_path(key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", re.sub(r"https?://", "", key))
    safe = re.sub(r"_+", "_", safe).strip("_")[:180]
    path = (
        Path(ARCHIVE_DIR)
        / PORTAL_NAME
        / safe
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_snapshot(page, key: str, screenshot_bytes: bytes) -> dict:
    try:
        await page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    await asyncio.sleep(0.8)
    html = await page.content()
    archive = make_archive_path(key)
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


async def diff_and_store(url, snap, har_path):
    baseline = get_baseline(PORTAL_NAME, url)
    diff_result = await run_all_diffs(
        portal_name=PORTAL_NAME,
        url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
    )
    update_baseline(
        portal=PORTAL_NAME,
        url=url,
        html_path=snap["html_path"],
        screenshot_path=snap["screenshot_path"],
        har_path=har_path,
    )
    if diff_result and diff_result.get("any_changed"):
        for diff_type, diff_data in diff_result["results"].items():
            if diff_type == "har":
                continue
            if diff_data.get("changed"):
                save_diff(
                    portal=PORTAL_NAME,
                    url=url,
                    diff_type=diff_type,
                    diff_detail=diff_data,
                )
                logger.info("  ✅ Change: %s | %s", url, diff_type)


async def scroll_and_stitch(page) -> bytes:
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(0.4)

    total_h = await page.evaluate(
        "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
    )
    logger.info("  scrollHeight=%dpx viewport=%dpx", total_h, vh)

    if total_h <= vh + 20:
        return await page.screenshot(full_page=True, type="png")

    pieces, scroll_y = [], 0
    while scroll_y < total_h:
        await page.evaluate(f"window.scrollTo(0,{scroll_y})")
        await asyncio.sleep(0.4)
        raw = await page.screenshot(full_page=False, type="png")
        img = Image.open(io.BytesIO(raw))
        actual_y = await page.evaluate("window.scrollY")
        pieces.append((actual_y, img))
        scroll_y += vh
        total_h = await page.evaluate(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )

    stitched = Image.new("RGB", (vw, total_h))
    for y, img in pieces:
        stitched.paste(img, (0, min(y, total_h - img.height)))

    await page.evaluate("window.scrollTo(0,0)")
    buf = io.BytesIO()
    stitched.save(buf, format="PNG")
    logger.info("  Stitched %dx%d from %d pieces", vw, total_h, len(pieces))
    return buf.getvalue()


async def goto_home(page):
    timeout = config.get("browser", {}).get("timeout_ms", 90000)
    await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=timeout)
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(2)


async def discover_menu_urls(page) -> list[dict]:
    """Collect unique cpcb.nic.in pages linked from the main nav dropdown tree."""
    raw = await page.evaluate(
        """(sel) => {
            const skip = ['.pdf','.jpg','.jpeg','.png','.gif','.zip','mailto:','javascript:','#'];
            const out = new Map();
            const root = document.querySelector(sel);
            if (!root) return [];
            root.querySelectorAll('a[href]').forEach(a => {
                let href = a.href || '';
                const text = (a.innerText || '').trim().replace(/\\s+/g, ' ');
                if (!href || !text) return;
                if (!href.includes('cpcb.nic.in')) return;
                const low = href.toLowerCase();
                for (const s of skip) { if (low.includes(s)) return; }
                href = href.split('#')[0];
                if (!out.has(href)) out.set(href, text);
            });
            return Array.from(out.entries()).map(([href, label]) => ({href, label}));
        }""",
        MENU_SELECTOR,
    )
    seen = set()
    items = []
    for item in raw:
        url = normalize_url(item["href"])
        if BASE_HOST not in urlparse(url).netloc:
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "label": item["label"]})
    items.sort(key=lambda x: x["url"])
    return items


async def goto_page(page, url: str) -> bool:
    timeout = config.get("browser", {}).get("timeout_ms", 90000)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as e:
        logger.warning("  goto failed (%s): %s", url, e)
        try:
            await page.goto(url, wait_until="load", timeout=timeout)
        except Exception as e2:
            logger.error("  skip — could not load: %s", e2)
            return False
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(1.5)
    return True


async def track_page(page, url: str, label: str, har_path: str) -> bool:
    logger.info("── %s", label[:70])
    logger.info("   %s", url)
    if not await goto_page(page, url):
        return False
    screenshot = await scroll_and_stitch(page)
    snap = await save_snapshot(page, url, screenshot)
    await diff_and_store(url, snap, har_path)
    return True


async def crawl_cpcb_nic_portal(portal_config: dict, limit: int | None = None):
    har_dir = Path(ARCHIVE_DIR) / PORTAL_NAME
    har_dir.mkdir(parents=True, exist_ok=True)
    har_path = str(har_dir / f"{PORTAL_NAME}_network.har")

    crawl_id = start_crawl_log(PORTAL_NAME)
    pages_visited = 0
    pages_failed = 0

    browser_cfg = config.get("browser", {})
    viewport = browser_cfg.get("viewport", {"width": 1280, "height": 800})

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=browser_cfg.get("headless", True),
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
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

        # ── Step 1: Home ──────────────────────────────────────────────────────
        logger.info("═══ STEP 1: Home page ═══")
        await goto_home(page)
        home_key = normalize_url(HOME_URL)
        if await track_page(page, home_key, "Home", har_path):
            pages_visited += 1

        # ── Step 2: Discover all main-nav dropdown URLs ───────────────────────
        logger.info("═══ STEP 2: Discover menu links ═══")
        await goto_home(page)
        menu_items = await discover_menu_urls(page)
        logger.info("Found %d unique menu URLs in %s", len(menu_items), MENU_SELECTOR)

        # Skip home duplicates already captured
        home_aliases = {
            normalize_url(HOME_URL),
            normalize_url("https://cpcb.nic.in/home/"),
            normalize_url("https://cpcb.nic.in/"),
        }
        to_crawl = [
            m for m in menu_items
            if normalize_url(m["url"]) not in home_aliases
        ]
        if limit is not None and limit > 0:
            to_crawl = to_crawl[:limit]
            logger.info("Limit applied — crawling first %d menu pages only", limit)
        logger.info("Crawling %d dropdown / sub-menu pages", len(to_crawl))

        # ── Step 3: Each menu page ────────────────────────────────────────────
        for i, item in enumerate(to_crawl, 1):
            url = normalize_url(item["url"])
            logger.info("═══ [%d/%d] ═══", i, len(to_crawl))
            ok = await track_page(page, url, item["label"], har_path)
            if ok:
                pages_visited += 1
            else:
                pages_failed += 1
            await asyncio.sleep(0.5)

        await context.close()
        await browser.close()

    status = "done" if pages_failed == 0 else "done_with_errors"
    finish_crawl_log(crawl_id, pages_visited, status=status)
    logger.info(
        "═══ CPCB NIC DONE: %d pages OK, %d failed ═══",
        pages_visited,
        pages_failed,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CPCB NIC portal crawler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single crawl run (passed by dashboard; default behaviour)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max menu pages to crawl (for testing); default = all",
    )
    args = parser.parse_args()

    init_db()
    portal_cfg = next(
        (p for p in config.get("portals", []) if p["name"] == PORTAL_NAME),
        {"name": PORTAL_NAME, "url": HOME_URL, "auth": "none"},
    )
    asyncio.run(crawl_cpcb_nic_portal(portal_cfg, limit=args.limit))
