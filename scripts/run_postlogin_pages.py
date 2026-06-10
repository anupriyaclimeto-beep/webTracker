import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path so local modules (auth, storage) import correctly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from playwright.async_api import async_playwright

from auth import launch_persistent_context, ensure_logged_in, get_profile_dir
from storage import archive_artefacts, update_baseline, ARCHIVE_DIR


async def run():
    with open("config.json") as f:
        cfg = json.load(f)
    portal = next((p for p in cfg.get("portals", []) if p.get("name") == "EPR PLASTIC"), None)
    if not portal:
        print("Portal 'EPR PLASTIC' not found in config.json")
        return

    targets = [
        "https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/material",
        "https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/sales",
    ]

    async with async_playwright() as p:
        ctx = await launch_persistent_context(p, portal)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Ensure logged in (will open manual login if needed)
        print("Ensuring logged in (complete manual login in the opened browser if prompted)...")
        try:
            await ensure_logged_in(page, portal, force_manual=False)
        except Exception as e:
            print("Login failed or aborted:", e)
            try:
                await ctx.close()
            except Exception:
                pass
            return

        for url in targets:
            print("Visiting:", url)
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(1.2)
                html = await page.content()
                screenshot = await page.screenshot(full_page=True)
            except Exception as e:
                print("Failed to capture:", url, e)
                continue

            # Archive artefacts (runs in thread)
            print("Archiving artefacts...")
            try:
                screenshot_path, html_path, har_path, screenshot_url, html_url = await asyncio.to_thread(
                    archive_artefacts, portal["name"], url, screenshot, html, None
                )
                print("Archived ->", screenshot_url, html_url)
            except Exception as e:
                print("Archive failed:", e)
                continue

            # Update baseline (runs in thread)
            try:
                await asyncio.to_thread(
                    update_baseline,
                    portal["name"],
                    url,
                    html_path,
                    screenshot_path,
                    har_path,
                    screenshot_url,
                    html_url,
                )
                print("Baseline updated for:", url)
            except Exception as e:
                print("Failed to update baseline:", e)

        try:
            await ctx.close()
        except Exception:
            pass

    print("Done.")


if __name__ == "__main__":
    asyncio.run(run())

