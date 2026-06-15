import glob, re

repl = '''async def diff_and_store(url, snap, har_path):
    baseline    = get_baseline(PORTAL_NAME, url)
    diff_image_path = f"archive/{PORTAL_NAME.replace(' ','_')}_diff_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    diff_result = await run_all_diffs(
        portal_name=PORTAL_NAME, url=url,
        current_screenshot=snap["screenshot_bytes"],
        current_html=snap["html"],
        baseline=baseline,
        diff_image_save_path=diff_image_path
    )
    # Upload to Cloudinary
    screenshot_url = upload_to_cloudinary(snap["screenshot_path"], resource_type="image")
    html_url       = upload_to_cloudinary(snap["html_path"], resource_type="raw")
    if screenshot_url:
        logger.info("  Cloudinary screenshot: %s", screenshot_url)
    if html_url:
        logger.info("  Cloudinary HTML: %s", html_url)

    diff_image_url = None
    if diff_result and diff_result.get("results", {}).get("visual", {}).get("diff_image_path"):
        diff_image_url = upload_to_cloudinary(diff_result["results"]["visual"]["diff_image_path"], resource_type="image")
        if diff_image_url:
            diff_result["results"]["visual"]["diff_image_url"] = diff_image_url
            if "html" in diff_result["results"]:
                diff_result["results"]["html"]["diff_image_url"] = diff_image_url

    saved_any = False
    if diff_result and diff_result.get("any_changed"):'''

for f in ['crawler_battery.py', 'crawler_tyres.py', 'crawler_elv.py', 'crawler_usedoil.py']:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    old = '''async def diff_and_store(url, snap, har_path):
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

    saved_any = False
    if diff_result and diff_result.get("any_changed"):'''
    
    if old in content:
        content = content.replace(old, repl)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f'Updated {f}')
    else:
        print(f'Could not find pattern in {f}')
