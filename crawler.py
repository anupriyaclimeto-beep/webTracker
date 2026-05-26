import asyncio
import json
import logging
import os
from playwright.async_api import async_playwright
from storage import (
    init_db,
    archive_artefacts,
    update_baseline,
    get_baseline,
    save_diff,
    start_crawl_log,
    finish_crawl_log,
    clear_baselines_for_portal
)
from diff_engine import html_diff, visual_diff

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

LOGGED_IN_URLS = [
    "pibo-dashboard",
    "epr/pibo",
    "epr/producer",
    "epr/filing",
    "epr/compensation",
    "epr/annual",
    "plastic/home"
]

NOT_LOGGED_IN_URLS = [
    "login",
    "signin",
    "sign-in"
]

SIDEBAR_MENU = [
    {
        "name": "Home",
        "click": "Home",
        "submenu": []
    },
    {
        "name": "Producer",
        "click": "Producer",
        "submenu": [
            "Applications"
        ]
    },
    {
        "name": "Wallet",
        "click": "Wallet",
        "submenu": []
    },
    {
        "name": "Credit Exchange",
        "click": "Credit Exchange",
        "submenu": []
    },
    {
        "name": "Consolidated Available Certificates",
        "click": "Consolidated Available Certificates",
        "submenu": []
    },
    {
        "name": "Road Making Declaration",
        "click": "Road Making Declaration",
        "submenu": [
            "PW Procurement",
            "Self Declaration"
        ]
    },
    {
        "name": "PIBO Operations",
        "click": "PIBO Operations",
        "submenu": [
            "Material Procurement Details",
            "Sales Details"
        ]
    },
    {
        "name": "Annual Filings",
        "click": "Annual Filings",
        "submenu": [
            "Annual Consumption",
            "State wise PW Generation",
            "Annual Report",
            "Filled Annual Report"
        ]
    },
    {
        "name": "Compensation",
        "click": "Compensation",
        "submenu": []
    }
]


async def is_logged_in(page, portal_config):
    try:
        await page.goto(
            portal_config["url"],
            wait_until="domcontentloaded",
            timeout=config["browser"]["timeout_ms"]
        )
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        current_url = page.url
        logger.info("Current URL after load: %s", current_url)

        for keyword in LOGGED_IN_URLS:
            if keyword.lower() in current_url.lower():
                logger.info("Already logged in — detected URL: %s", current_url)
                return True

        for keyword in NOT_LOGGED_IN_URLS:
            if keyword.lower() in current_url.lower():
                logger.info("Not logged in — URL contains: %s", keyword)
                return False

        is_login_page = await page.query_selector("input[type='password']")
        if is_login_page:
            logger.info("Login form detected — not logged in")
            return False

        sidebar = await page.query_selector(".side-menu-item, .sidebar, nav")
        if sidebar:
            logger.info("Sidebar detected — assuming logged in")
            return True

        logger.info("Cannot determine login state — assuming not logged in")
        return False

    except Exception as e:
        logger.error("Error checking login status — %s", str(e))
        return False


async def wait_for_login(page, portal_config):
    url = portal_config["url"]
    logger.info("Waiting for manual login...")

    print("\n" + "="*60)
    print("BROWSER IS OPEN")
    print("Please login manually in the browser.")
    print("Crawler will start AUTOMATICALLY once you are logged in.")
    print("DO NOT click anything in the terminal.")
    print("="*60 + "\n")

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=config["browser"]["timeout_ms"]
    )
    await page.wait_for_timeout(2000)

    for i in range(60):
        try:
            current_url = page.url
            logger.info("Waiting for login... (%s/60) URL: %s", i + 1, current_url)

            for keyword in LOGGED_IN_URLS:
                if keyword.lower() in current_url.lower():
                    logger.info("Login detected — URL: %s", current_url)
                    print("\n✅ Login detected! Crawl starting automatically...\n")
                    return True

            sidebar = await page.query_selector(".side-menu-item, .sidebar, nav")
            has_password = await page.query_selector("input[type='password']")
            if sidebar and not has_password:
                logger.info("Sidebar detected — login confirmed")
                print("\n✅ Login detected! Crawl starting automatically...\n")
                return True

            await page.wait_for_timeout(5000)

        except Exception as e:
            logger.error("Error waiting for login — %s", str(e))
            await page.wait_for_timeout(5000)

    logger.error("Login timeout — user did not login within 5 minutes")
    return False


async def click_and_capture(page, label, portal_name):
    try:
        logger.info("Clicking menu item: %s", label)

        clicked = False
        selectors = [
            f"text={label}",
            f"span:has-text('{label}')",
            f"a:has-text('{label}')",
            f"li:has-text('{label}')",
            f"div:has-text('{label}')"
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible():
                    await element.click()
                    clicked = True
                    logger.info("Clicked using selector: %s", selector)
                    break
            except Exception:
                continue

        if not clicked:
            logger.warning("Could not click menu item: %s", label)
            return

        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        current_url = page.url
        screenshot_bytes = await page.screenshot(full_page=True)
        html_content = await page.content()

        logger.info("Captured: %s — URL: %s", label, current_url)

        url_key = current_url + f"___{label.replace(' ', '_')}"

        screenshot_path, saved_html_path, saved_har_path = archive_artefacts(
            portal=portal_name,
            url=url_key,
            screenshot_bytes=screenshot_bytes,
            html_content=html_content,
            har_data=None
        )

        existing_baseline = get_baseline(portal_name, url_key)

        if existing_baseline is None:
            update_baseline(
                portal=portal_name,
                url=url_key,
                html_path=saved_html_path,
                screenshot_path=screenshot_path,
                har_path=saved_har_path
            )
            logger.info("Baseline saved for: %s", label)
        else:
            logger.info("Baseline exists — running diffs for: %s", label)

            html_result = html_diff(existing_baseline["html_path"], html_content)
            if html_result.get("changed"):
                save_diff(portal_name, url_key, "html", html_result)
                logger.info("HTML change detected and saved for: %s", label)
            else:
                logger.info("No HTML change for: %s", label)

            visual_result = visual_diff(
                existing_baseline["screenshot_path"], screenshot_bytes
            )
            if visual_result.get("changed"):
                save_diff(portal_name, url_key, "visual", visual_result)
                logger.info("Visual change detected and saved for: %s", label)
            else:
                logger.info("No visual change for: %s", label)

            update_baseline(
                portal=portal_name,
                url=url_key,
                html_path=saved_html_path,
                screenshot_path=screenshot_path,
                har_path=saved_har_path
            )

    except Exception as e:
        logger.error("Error capturing %s — %s", label, str(e))


async def capture_form_fields(page, portal_name, form_name):
    try:
        logger.info("Capturing form fields for: %s", form_name)

        all_field_data = {}

        selects = await page.query_selector_all("select, ng-select, .ng-select")
        for i, select in enumerate(selects):
            try:
                label_el = await page.query_selector("label:near(select)")
                label = await label_el.inner_text() if label_el else f"dropdown_{i}"
                options = await select.query_selector_all("option, .ng-option")
                option_texts = []
                for opt in options:
                    text = await opt.inner_text()
                    if text.strip():
                        option_texts.append(text.strip())
                all_field_data[label.strip()] = option_texts
            except Exception:
                continue

        inputs = await page.query_selector_all("input, textarea")
        input_labels = []
        for inp in inputs:
            try:
                placeholder = await inp.get_attribute("placeholder")
                if placeholder:
                    input_labels.append(placeholder.strip())
            except Exception:
                continue
        all_field_data["input_fields"] = input_labels

        screenshot_bytes = await page.screenshot(full_page=True)
        html_content = await page.content()

        url_key = page.url + f"___form_{form_name.replace(' ', '_')}"

        screenshot_path, saved_html_path, saved_har_path = archive_artefacts(
            portal=portal_name,
            url=url_key,
            screenshot_bytes=screenshot_bytes,
            html_content=html_content,
            har_data=all_field_data
        )

        existing_baseline = get_baseline(portal_name, url_key)
        if existing_baseline is None:
            update_baseline(
                portal=portal_name,
                url=url_key,
                html_path=saved_html_path,
                screenshot_path=screenshot_path,
                har_path=saved_har_path
            )
            logger.info("Form baseline saved for: %s", form_name)
        else:
            logger.info("Form baseline exists — running diffs for: %s", form_name)

            html_result = html_diff(existing_baseline["html_path"], html_content)
            if html_result.get("changed"):
                save_diff(portal_name, url_key, "html", html_result)
                logger.info("HTML change detected in form: %s", form_name)

            visual_result = visual_diff(
                existing_baseline["screenshot_path"], screenshot_bytes
            )
            if visual_result.get("changed"):
                save_diff(portal_name, url_key, "visual", visual_result)
                logger.info("Visual change detected in form: %s", form_name)

            update_baseline(
                portal=portal_name,
                url=url_key,
                html_path=saved_html_path,
                screenshot_path=screenshot_path,
                har_path=saved_har_path
            )

        return all_field_data

    except Exception as e:
        logger.error("Error capturing form fields for %s — %s", form_name, str(e))
        return {}


async def close_modal(page):
    try:
        close_selectors = [
            "button.close",
            ".modal .close",
            "button:has-text('×')",
            ".btn-close",
            "[aria-label='Close']",
            "mat-dialog-container button",
            ".modal-header .close"
        ]
        for selector in close_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(1000)
                    logger.info("Modal closed using: %s", selector)
                    return True
            except Exception:
                continue

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)
        logger.info("Modal closed using Escape key")
        return True

    except Exception as e:
        logger.error("Could not close modal — %s", str(e))
        return False


async def click_and_capture_with_form(
    page, label, portal_name, open_form_button=None, form_name=None
):
    try:
        await click_and_capture(page, label, portal_name)
        await page.wait_for_timeout(1500)

        if open_form_button and form_name:
            try:
                btn = page.locator(f"text={open_form_button}").first
                if await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    logger.info("Opened form: %s", form_name)
                    await capture_form_fields(page, portal_name, form_name)
                    await close_modal(page)
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logger.warning("Could not open form %s — %s", form_name, str(e))

    except Exception as e:
        logger.error(
            "Error in click_and_capture_with_form for %s — %s", label, str(e)
        )


async def crawl_portal(portal_config):
    portal_name = portal_config["name"]
    browser_cfg = config.get("browser", {})
    user_data_dir = browser_cfg.get("user_data_dir", "browser_session")

    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs("archive", exist_ok=True)

    crawl_id = start_crawl_log(portal_name)
    pages_visited = 0

    logger.info("Starting crawl for portal: %s", portal_name)

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=browser_cfg.get("headless", False),
                args=["--start-maximized"],
                viewport={
                    "width": browser_cfg.get("viewport", {}).get("width", 1280),
                    "height": browser_cfg.get("viewport", {}).get("height", 800)
                },
                record_har_path=f"archive/{portal_name}_network.har"
            )

            page = await context.new_page()

            logged_in = await is_logged_in(page, portal_config)

            if not logged_in:
                success = await wait_for_login(page, portal_config)
                if not success:
                    logger.error("Login failed or timed out")
                    await context.close()
                    finish_crawl_log(crawl_id, 0, status="failed")
                    return
            else:
                logger.info("Already logged in — starting crawl immediately")

            await page.wait_for_timeout(2000)
            clear_baselines_for_portal(portal_name)
            logger.info("Old baselines cleared — starting fresh crawl")
            for menu_item in SIDEBAR_MENU:
                main_label = menu_item["name"]
                submenus = menu_item["submenu"]

                await click_and_capture(page, main_label, portal_name)
                pages_visited += 1
                await page.wait_for_timeout(1000)

                for sub_label in submenus:
                    if sub_label == "Material Procurement Details":
                        await click_and_capture_with_form(
                            page=page,
                            label=sub_label,
                            portal_name=portal_name,
                            open_form_button="Add New",
                            form_name="Add Material Procurement Details"
                        )
                    elif sub_label == "Sales Details":
                        await click_and_capture_with_form(
                            page=page,
                            label=sub_label,
                            portal_name=portal_name,
                            open_form_button="Add New",
                            form_name="Add Sales Details"
                        )
                    else:
                        await click_and_capture(page, sub_label, portal_name)

                    pages_visited += 1
                    await page.wait_for_timeout(1000)

            await context.close()
            logger.info("HAR file saved to archive/%s_network.har", portal_name)

        finish_crawl_log(crawl_id, pages_visited, status="done")
        logger.info(
            "Crawl complete — %s pages visited for %s",
            pages_visited, portal_name
        )

    except Exception as e:
        finish_crawl_log(crawl_id, pages_visited, status="failed")
        logger.error("Crawl failed for %s — %s", portal_name, str(e))
        raise


async def run_all_portals():
    init_db()
    for portal in config["portals"]:
        logger.info("="*50)
        logger.info("Portal: %s", portal["name"])
        logger.info("="*50)
        await crawl_portal(portal)


if __name__ == "__main__":
    asyncio.run(run_all_portals())