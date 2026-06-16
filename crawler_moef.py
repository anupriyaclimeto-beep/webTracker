"""
crawler_moef.py — MOEF Portal Crawler
URL: https://moef.gov.in/

This crawler simply visits the home page, takes a screenshot, and runs diffs.
It does not attempt to log in.
"""

import asyncio
import io
import json
import logging
import os
import sys

from playwright.async_api import async_playwright

from diff_engine import run_all_diffs
from storage import (
    init_db, update_baseline, get_baseline,
    save_diff, start_crawl_log, finish_crawl_log,
    upload_to_cloudinary, ARCHIVE_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

PORTAL_NAME = "MOEF"
HOME_URL    = "https://moef.gov.in/"

async def crawl_moef_portal(portal_config, mode="full"):
    init_db()
    if not portal_config:
        logger.error(f"Configuration for {PORTAL_NAME} not found.")
        return

    crawl_id = start_crawl_log(PORTAL_NAME)
    pages_visited = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.get("browser", {}).get("headless", True),
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        vp = config.get("browser", {}).get("viewport", {"width": 1280, "height": 800})
        context = await browser.new_context(viewport=vp, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        
        logger.info(f"Navigating to {HOME_URL}...")
        try:
            await page.goto(HOME_URL, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5)  # Wait for any dynamic rendering
        except Exception as e:
            logger.error(f"Failed to navigate to {HOME_URL}: {e}")
            finish_crawl_log(crawl_id, pages_visited, status="error")
            await browser.close()
            return

        # Hide noisy elements like captchas if present
        try:
            await page.evaluate("""() => {
                const captchas = document.querySelectorAll('img[src*="captcha"], img[id*="captcha"], img[alt*="captcha"]');
                captchas.forEach(el => el.style.visibility = 'hidden');
            }""")
            await asyncio.sleep(1)
        except Exception as e:
            pass

        logger.info("Taking full page screenshot...")
        screenshot_bytes = await page.screenshot(full_page=True, type="png")
        html_content = await page.content()

        # Save Baseline / Compute Diff
        page_key = "moef_home"
        
        old_data = get_baseline(PORTAL_NAME, page_key)
        
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_url = HOME_URL.replace("https://", "").replace("http://", "").replace("/", "_")
        snapshot_dir = os.path.join(ARCHIVE_DIR, PORTAL_NAME, f"{safe_url}_{page_key}")
        os.makedirs(snapshot_dir, exist_ok=True)
        
        shot_path = os.path.join(snapshot_dir, f"{ts}.png")
        html_path = os.path.join(snapshot_dir, f"{ts}.html")
        
        with open(shot_path, "wb") as f:
            f.write(screenshot_bytes)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # Upload to Cloudinary if configured
        remote_shot = upload_to_cloudinary(shot_path, resource_type="image")
        remote_html = upload_to_cloudinary(html_path, resource_type="raw")
        
        snap = {
            "screenshot_path": shot_path,
            "html_path": html_path,
            "url": HOME_URL,
            "screenshot_url": remote_shot,
            "html_url": remote_html
        }

        diff_image_save_path = os.path.join(snapshot_dir, f"{ts}_diff.png")
        diff_res = await run_all_diffs(
            PORTAL_NAME,
            HOME_URL,
            screenshot_bytes,
            html_content,
            old_data,
            diff_image_save_path=diff_image_save_path
        )
        
        if diff_res and diff_res.get("any_changed"):
            for diff_type, diff_data in diff_res.get("results", {}).items():
                if diff_type == "har": continue
                if diff_data.get("changed"):
                    save_diff(
                        portal=PORTAL_NAME,
                        url=HOME_URL,
                        diff_type=diff_type,
                        diff_detail=diff_data,
                        screenshot_url=snap.get("screenshot_url"),
                        html_url=snap.get("html_url")
                    )
        else:
            logger.info("No significant changes detected.")

        update_baseline(
            portal=PORTAL_NAME,
            url=page_key,
            html_path=snap.get("html_path"),
            screenshot_path=snap.get("screenshot_path"),
            har_path=None,
            screenshot_url=snap.get("screenshot_url"),
            html_url=snap.get("html_url")
        )
        pages_visited += 1

        logger.info("Crawl completed successfully.")
        finish_crawl_log(crawl_id, pages_visited, status="done")
        
        await browser.close()

if __name__ == "__main__":
    p_config = next((p for p in config["portals"] if p["name"] == PORTAL_NAME), None)
    asyncio.run(crawl_moef_portal(p_config))
