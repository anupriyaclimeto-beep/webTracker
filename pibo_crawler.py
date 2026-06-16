"""
pibo_crawler.py — Deep crawl handlers for specified CPCB EPR Plastic Pages.

Contains handlers for:
  1. Material Procurement: https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/material
  2. Sales Details: https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/sales
  3. Declaration Procurement: https://eprplastic.cpcb.gov.in/#/epr/pibo-declaration-procurement
  4. PIBO Wallet: https://eprplastic.cpcb.gov.in/#/epr/pibo-wallet
"""

import asyncio
import logging
import re
import os
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── Shared Modal Helpers ──────────────────────────────────────────────────────

async def open_add_new_modal(page) -> bool:
    """Click the Add New button and wait for modal."""
    selectors = [
        "button:has-text('Add New')",
        "button:has-text('Add new')",
        "button:has-text('+ Add New')",
        "a:has-text('Add New')",
        ".btn:has-text('New')",
        "[class*='add-new']",
        "button:has-text('Add')",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                await asyncio.sleep(1.5)
                # Wait for modal/dialog to appear
                try:
                    await page.wait_for_selector(
                        ".modal, mat-dialog-container, [role='dialog'], .cdk-overlay-container, .modal-content",
                        timeout=6000
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                logger.info("  'Add New' modal opened via: %s", sel)
                return True
        except Exception:
            continue
    logger.warning("  'Add New' button not found — skipping modal steps")
    return False


async def close_modal(page):
    """Close modal via close button or Escape."""
    for sel in [
        "button:has-text('x')",
        "button:has-text('X')",
        ".modal .close",
        ".btn-close",
        "[aria-label='Close']",
        "mat-dialog-container .mat-icon-button",
        ".modal-header button",
        ".modal-content button:has-text('Close')",
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.click()
                await asyncio.sleep(1)
                logger.info("  Modal closed via button")
                return
        except Exception:
            continue
    await page.keyboard.press("Escape")
    await asyncio.sleep(1)
    logger.info("  Modal close attempted via Escape")

    # Violent fallback: if modal still exists, nuke it via JS
    try:
        if await page.locator("ngb-modal-window, .modal, .cdk-overlay-container").count() > 0:
            await page.evaluate("""
                document.querySelectorAll('ngb-modal-window, .modal, .modal-backdrop, .cdk-overlay-backdrop').forEach(e => e.remove());
                document.body.classList.remove('modal-open');
            """)
            await asyncio.sleep(0.5)
            logger.info("  Modal force-removed via JS")
    except Exception:
        pass


async def open_dropdown_and_capture(
    page,
    label_text: str,
    key_suffix: str,
    base_key: str,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
) -> bool:
    """
    Find a mat-select / ng-select near the given label text,
    click to open it, scroll options to bottom, screenshot.
    """
    selectors = [
        f"mat-select:near(:text('{label_text}'), 120)",
        f".mat-select:near(:text('{label_text}'), 120)",
        f"ng-select:near(:text('{label_text}'), 120)",
        f"select:near(:text('{label_text}'), 120)",
        f"[placeholder*='{label_text}']",
        f"[aria-label*='{label_text}']",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await asyncio.sleep(1.2)
                # Scroll options panel to bottom to reveal all items
                try:
                    await page.evaluate("""
                        const panels = [
                            document.querySelector('.mat-select-panel'),
                            document.querySelector('.cdk-overlay-pane .mat-select-panel'),
                            document.querySelector('.dropdown-menu.show'),
                            document.querySelector('.ng-dropdown-panel'),
                            document.querySelector('.mat-autocomplete-panel'),
                        ];
                        for (const p of panels) {
                            if (p) { p.scrollTop = p.scrollHeight; break; }
                        }
                    """)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                # Screenshot with dropdown open
                snap = await save_snapshot(
                    page, portal_name,
                    base_key + f"__form__{key_suffix}",
                    await page.screenshot(full_page=False, type="png")
                )
                await diff_and_store(
                    portal_name, base_key + f"__form__{key_suffix}", snap, har_path
                )
                logger.info("  Dropdown '%s' captured ✓", label_text)
                # Close dropdown without closing modal
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.6)
                return True
        except Exception:
            continue
    logger.warning("  Dropdown '%s' not found", label_text)
    return False


# ── Specific Page Crawlers ────────────────────────────────────────────────────

async def crawl_material_procurement(
    page,
    url: str,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
    scroll_and_stitch,
    safe_goto,
    home_url: str,
) -> int:
    """Deep crawl of Material Procurement (Registered / Unregistered modal forms)."""
    BASE_KEY = home_url + "__LOGGEDIN_PIBO_Material_Procurement"
    pv = 0

    logger.info("═══ Material Procurement deep crawl starting: %s ═══", url)
    await safe_goto(page, url, label="Material Procurement")
    screenshot_bytes = await scroll_and_stitch(page)
    snap = await save_snapshot(page, portal_name, BASE_KEY + "__fullpage", screenshot_bytes)
    await diff_and_store(portal_name, BASE_KEY + "__fullpage", snap, har_path)
    pv += 1

    if await open_add_new_modal(page):
        # 1. Initial form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__initial",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__initial", snap, har_path)
        pv += 1

        # 2. Registration Type dropdown
        if await open_dropdown_and_capture(page, "Registration Type", "RegistrationType_open", BASE_KEY, portal_name, har_path, save_snapshot, diff_and_store):
            pv += 1

        # Open dropdown using exact XPath
        try:
            await page.locator("xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form/div/form/div/div/div/ng-select/div/div/div[2]").click(timeout=3000)
            await asyncio.sleep(1)
        except:
            pass

        # Select "Unregistered" to reveal fields
        unregistered_selected = False
        for sel in [
            "xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form/div/form/div/div/div/ng-select/ng-dropdown-panel/div/div[2]/div[2]",
            "mat-option:has-text('Unregistered')",
            ".mat-option:has-text('Unregistered')",
            "[role='option']:has-text('Unregistered')",
            ".dropdown-item:has-text('Unregistered')",
            "li:has-text('Unregistered')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(1.5)
                    snap = await save_snapshot(
                        page, portal_name, BASE_KEY + "__form__unregistered_selected",
                        await page.screenshot(full_page=False, type="png")
                    )
                    await diff_and_store(portal_name, BASE_KEY + "__form__unregistered_selected", snap, har_path)
                    pv += 1
                    unregistered_selected = True
                    break
            except Exception:
                continue

        # 3. Entity Type dropdown
        if await open_dropdown_and_capture(page, "Entity Type", "EntityType_open", BASE_KEY, portal_name, har_path, save_snapshot, diff_and_store):
            pv += 1

        # 4. Plastic Material Type dropdown
        if await open_dropdown_and_capture(page, "Plastic Material Type", "PlasticMaterialType_open", BASE_KEY, portal_name, har_path, save_snapshot, diff_and_store):
            pv += 1

        # 5. Final form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__final_state",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__final_state", snap, har_path)
        pv += 1

        await close_modal(page)

    return pv


async def crawl_sales_details(
    page,
    url: str,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
    scroll_and_stitch,
    safe_goto,
    home_url: str,
) -> int:
    """Deep crawl of Sales Details modal form."""
    BASE_KEY = home_url + "__LOGGEDIN_PIBO_Sales_Details"
    pv = 0

    logger.info("═══ Sales Details deep crawl starting: %s ═══", url)
    await safe_goto(page, url, label="Sales Details")
    screenshot_bytes = await scroll_and_stitch(page)
    snap = await save_snapshot(page, portal_name, BASE_KEY + "__fullpage", screenshot_bytes)
    await diff_and_store(portal_name, BASE_KEY + "__fullpage", snap, har_path)
    pv += 1

    if await open_add_new_modal(page):
        # 1. Initial form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__initial",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__initial", snap, har_path)
        pv += 1

        # Give the modal extra time to fully load and render its fields
        await asyncio.sleep(2)

        # 2. Registration Type dropdown: Select Unregistered
        try:
            # Click Dropdown robustly
            try:
                await page.locator("xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[1]/div/ng-select").click(timeout=5000)
            except:
                await page.locator("ng-select:near(:text('Registration Type'), 100)").first.click(timeout=5000, force=True)
            
            await asyncio.sleep(1)
            
            # Click Unregistered
            try:
                await page.locator(".ng-option >> text=\"Unregistered\"").first.click(timeout=5000, force=True)
            except:
                try:
                    await page.locator("//div[contains(@class, 'ng-option')]//span[contains(text(), 'Unregistered')]").first.click(timeout=5000, force=True)
                except:
                    # Fallback to the exact div[2] xpath
                    await page.locator("xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[1]/div/ng-select/ng-dropdown-panel/div/div[2]/div[2]/span").click(timeout=5000, force=True)
            
            await asyncio.sleep(2) # Wait for the form fields to appear
        except Exception as e:
            logger.error("Failed to select Unregistered in Sales: %s", e)

        # Helper function to select Entity Type and intercept JSON from Entity Name dropdown
        async def intercept_and_select_entity(entity_name, entity_xpath, json_filename):
            try:
                # 1. Click Entity Type dropdown robustly
                try:
                    # Click the dropdown container itself, not the hidden input
                    await page.locator("xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[3]/div/ng-select").click(timeout=5000)
                except:
                    await page.locator("ng-select:near(:text('Entity Type'), 100), ng-select[placeholder*='Entity Type']").first.click(timeout=5000, force=True)
                
                await asyncio.sleep(1)
                
                # 2. Click the specific entity (Producer, Brand Owner, Importer)
                try:
                    # Try text matching first - using exact role or class with text
                    await page.locator(f".ng-option >> text=\"{entity_name}\"").first.click(timeout=5000, force=True)
                except:
                    try:
                        await page.locator(f"//div[contains(@class, 'ng-option')]//span[contains(text(), '{entity_name}')]").first.click(timeout=5000, force=True)
                    except:
                        # Fallback to absolute XPath
                        await page.locator(f"xpath={entity_xpath}").click(timeout=5000, force=True)
                
                await asyncio.sleep(2)

                # Set up response interceptor
                api_response_data = None
                
                async def handle_response(response):
                    nonlocal api_response_data
                    if "list_entity_name" in response.url and response.status == 200:
                        try:
                            api_response_data = await response.json()
                        except:
                            pass
                
                page.on("response", handle_response)
                
                # 3. Click Entity Name dropdown to trigger the API call
                try:
                    await page.locator("ng-select:near(:text('Name of the Entity'), 100), ng-select[placeholder*='Entity Name']").first.click(timeout=5000, force=True)
                except:
                    await page.locator("xpath=/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[5]/div/ng-select").click(timeout=5000, force=True)
                
                # Wait for API to fire
                await asyncio.sleep(4)
                
                page.remove_listener("response", handle_response)
                
                if api_response_data:
                    os.makedirs("archive", exist_ok=True)
                    with open(f"archive/{json_filename}", "w") as f:
                        json.dump(api_response_data, f, indent=4)
                    logger.info("Saved %s successfully!", json_filename)
            except Exception as e:
                logger.error("Failed intercepting %s: %s", entity_name, e)

        # Execute the extraction for all 3 entities
        await intercept_and_select_entity(
            "Producer", 
            "/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[3]/div/ng-select/ng-dropdown-panel/div/div[2]/div[1]/span", 
            "EPR_PLASTIC_Unregistered_Producer.json"
        )
        await intercept_and_select_entity(
            "Brand Owner", 
            "/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[3]/div/ng-select/ng-dropdown-panel/div/div[2]/div[2]/span", 
            "EPR_PLASTIC_Unregistered_Brand_Owner.json"
        )
        await intercept_and_select_entity(
            "Importer", 
            "/html/body/ngb-modal-window/div/div/div[2]/app-pibo-material-procurement-form-sales/form/div[1]/div[3]/div/ng-select/ng-dropdown-panel/div/div[2]/div[3]/span", 
            "EPR_PLASTIC_Unregistered_Importer.json"
        )

        # Final form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__final_state",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__final_state", snap, har_path)
        pv += 1

        await close_modal(page)

    return pv


async def crawl_declaration_procurement(
    page,
    url: str,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
    scroll_and_stitch,
    safe_goto,
    home_url: str,
) -> int:
    """Deep crawl of Self Declaration Procurement modal form."""
    BASE_KEY = home_url + "__LOGGEDIN_PIBO_Declaration_Procurement"
    pv = 0

    logger.info("═══ Declaration Procurement deep crawl starting: %s ═══", url)
    await safe_goto(page, url, label="Declaration Procurement")
    screenshot_bytes = await scroll_and_stitch(page)
    snap = await save_snapshot(page, portal_name, BASE_KEY + "__fullpage", screenshot_bytes)
    await diff_and_store(portal_name, BASE_KEY + "__fullpage", snap, har_path)
    pv += 1

    if await open_add_new_modal(page):
        # 1. Initial form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__initial",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__initial", snap, har_path)
        pv += 1

        # 2. Categories of Plastic dropdown
        if await open_dropdown_and_capture(page, "Categories of Plastic", "CategoriesOfPlastic_open", BASE_KEY, portal_name, har_path, save_snapshot, diff_and_store):
            pv += 1

        # 3. State dropdown
        if await open_dropdown_and_capture(page, "State", "State_open", BASE_KEY, portal_name, har_path, save_snapshot, diff_and_store):
            pv += 1

        # 4. Final form state
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__final_state",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__final_state", snap, har_path)
        pv += 1

        await close_modal(page)

    return pv


async def crawl_pibo_wallet(
    page,
    url: str,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
    scroll_and_stitch,
    safe_goto,
    home_url: str,
) -> int:
    """Deep crawl of PIBO Wallet (Credit/Debit Operations modal form)."""
    BASE_KEY = home_url + "__LOGGEDIN_PIBO_Wallet"
    pv = 0

    logger.info("═══ PIBO Wallet deep crawl starting: %s ═══", url)
    await safe_goto(page, url, label="PIBO Wallet")
    screenshot_bytes = await scroll_and_stitch(page)
    snap = await save_snapshot(page, portal_name, BASE_KEY + "__fullpage", screenshot_bytes)
    await diff_and_store(portal_name, BASE_KEY + "__fullpage", snap, har_path)
    pv += 1

    ops_button_clicked = False
    selectors = [
        "button:has-text('Credit/Debit Operations')",
        "button:has-text('Debit/Credit Operations')",
        "button:has-text('Operations')",
        "button:has-text('Credit/Debit')",
        "button:has-text('Debit/Credit')",
        "button:has-text('Add')",
        ".btn:has-text('Operations')",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                await asyncio.sleep(1.5)
                try:
                    await page.wait_for_selector(
                        ".modal, mat-dialog-container, [role='dialog'], .cdk-overlay-container, .modal-content",
                        timeout=5000
                    )
                except Exception:
                    pass
                logger.info("  Credit/Debit Operations modal opened via: %s", sel)
                ops_button_clicked = True
                break
        except Exception:
            continue

    if ops_button_clicked:
        snap = await save_snapshot(
            page, portal_name, BASE_KEY + "__form__initial",
            await page.screenshot(full_page=False, type="png")
        )
        await diff_and_store(portal_name, BASE_KEY + "__form__initial", snap, har_path)
        pv += 1

        await close_modal(page)
    else:
        logger.warning("  Could not find button to open Credit/Debit Operations modal")

    return pv


# ── Backward Compatibility Delegate ──────────────────────────────────────────

async def crawl_pibo_unregistered_procurement(
    page,
    portal_name: str,
    har_path: str,
    save_snapshot,
    diff_and_store,
    scroll_and_stitch,
    safe_goto,
    home_url: str,
) -> int:
    """Legacy entry point, delegates to crawl_material_procurement."""
    url = "https://eprplastic.cpcb.gov.in/#/epr/pibo-operations/material"
    return await crawl_material_procurement(
        page, url, portal_name, har_path, save_snapshot, diff_and_store, scroll_and_stitch, safe_goto, home_url
    )
