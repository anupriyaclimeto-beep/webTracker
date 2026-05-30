import asyncio
import json
import logging
import os
import re
from difflib import unified_diff
from PIL import Image, ImageChops
import io
from deepdiff import DeepDiff
from bs4 import BeautifulSoup, Comment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

PIXEL_THRESHOLD = config["diff"].get("pixel_threshold", 0.05)


def clean_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        for tag in soup.find_all(True):
            attrs_to_remove = []
            attrs_to_clean = {}

            for attr, value in tag.attrs.items():
                attr_lower = attr.lower()

                if attr_lower.startswith("_nghost") or attr_lower.startswith("_ngcontent"):
                    attrs_to_remove.append(attr)
                    continue

                if attr_lower.startswith("_echarts_instance"):
                    attrs_to_remove.append(attr)
                    continue

                if attr_lower in ("data-uid", "data-reactid", "data-reactroot",
                                  "data-ember-action", "data-guid"):
                    attrs_to_remove.append(attr)
                    continue

                if attr_lower == "class":
                    if isinstance(value, list):
                        cleaned = [v for v in value if "ng-star-inserted" not in v]
                        attrs_to_clean[attr] = cleaned
                    elif isinstance(value, str):
                        attrs_to_clean[attr] = value.replace("ng-star-inserted", "").strip()
                    continue

                if attr_lower.startswith("ng-reflect"):
                    attrs_to_remove.append(attr)
                    continue

                if attr_lower == "autocomplete" and isinstance(value, str):
                    if re.fullmatch(r"[a-f0-9]{8,}", value):
                        attrs_to_remove.append(attr)
                        continue

                if attr_lower in ("nonce", "data-nonce", "data-token",
                                  "data-csrf", "data-requestverificationtoken"):
                    attrs_to_remove.append(attr)
                    continue

                if attr_lower == "style" and isinstance(value, str):
                    cleaned_style = re.sub(
                        r"max-height\s*:\s*calc\([^)]+\)\s*;?", "", value
                    ).strip().rstrip(";")
                    attrs_to_clean[attr] = cleaned_style
                    continue

            for attr in attrs_to_remove:
                del tag.attrs[attr]
            for attr, val in attrs_to_clean.items():
                tag.attrs[attr] = val

        text = soup.prettify()
        text = re.sub(r"End Session \(\d+\)", "End Session (N)", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    except Exception as e:
        logger.error("clean_html error — %s", str(e))
        return html


def build_selector(tag) -> str:
    """
    Build a concise CSS-like selector for a BeautifulSoup tag.
    e.g.  nav > ul > li > a.active  or  div#main > h2
    """
    parts = []
    node = tag
    for _ in range(5):   # walk up max 5 levels
        if node is None or node.name is None:
            break
        label = node.name
        if node.get("id"):
            label += f'#{node["id"]}'
        elif node.get("class"):
            cls = " ".join(c for c in node["class"] if c)
            if cls:
                label += f'.{cls.split()[0]}'   # first class only for brevity
        parts.append(label)
        node = node.parent
    parts.reverse()
    return " > ".join(parts) if parts else "unknown"


def extract_text_changes(diff_sample):
    """
    Convert raw HTML diff lines into human-readable descriptions
    including the selector context of each change.
    """
    added_texts = []
    removed_texts = []

    for line in diff_sample:
        if line.startswith("+") and not line.startswith("+++"):
            raw = line[1:].strip()
            result = extract_readable_text(raw)
            if result:
                added_texts.append(result)
        elif line.startswith("-") and not line.startswith("---"):
            raw = line[1:].strip()
            result = extract_readable_text(raw)
            if result:
                removed_texts.append(result)

    return added_texts, removed_texts


def extract_readable_text(html_fragment):
    """
    Pull meaningful human-readable content AND selector from an HTML fragment.
    Returns a dict {text, selector} or None if the fragment is noise.
    """
    try:
        noise_patterns = [
            r"^<[^>]+>$",
            r"echarts",
            r"_ngcontent|_nghost",
            r"ng-reflect",
            r"^\s*$",
        ]
        for pattern in noise_patterns:
            if re.search(pattern, html_fragment, re.IGNORECASE):
                return None

        soup = BeautifulSoup(html_fragment, "html.parser")

        for tag in soup.find_all(["button", "a", "label", "h1", "h2", "h3",
                                   "h4", "h5", "span", "td", "th", "li", "p"]):
            text = tag.get_text(strip=True)
            if text and len(text) > 1:
                tag_name = tag.name.upper()
                selector = build_selector(tag)
                if tag_name in ("BUTTON", "A"):
                    return {"text": f'{tag_name}: "{text}"', "selector": selector}
                return {"text": f'"{text}"', "selector": selector}

        plain = soup.get_text(strip=True)
        if plain and len(plain) > 1:
            return {"text": f'"{plain}"', "selector": "unknown"}

        return None

    except Exception:
        return None


def summarize_changes(added_texts, removed_texts):
    """
    Build a plain-English summary of what changed, including selector context.
    """
    def humanize_item(item):
        if not item:
            return None
        text = item.get("text", "").strip()
        selector = item.get("selector", "")

        m = re.match(r'^(?P<tag>[A-Z]+):\s*"(.*)"$', text)
        if m:
            tag = m.group('tag').lower()
            label = m.group(2)
            if tag == 'button':
                phrase = f'Button "{label}"'
            elif tag == 'a':
                phrase = f'Link "{label}"'
            else:
                phrase = f'{tag.capitalize()} "{label}"'
        else:
            q = re.match(r'^"(.*)"$', text)
            if q:
                label = q.group(1)
                low = label.lower()
                if any(word in low for word in ('button', 'add', 'submit', 'tracking')):
                    phrase = f'UI label "{label}"'
                else:
                    phrase = f'"{label}"'
            else:
                phrase = text if len(text) < 100 else text[:97] + "..."

        if selector and selector != "unknown":
            phrase += f' [{selector}]'

        return phrase

    added_phrases = []
    for a in added_texts:
        h = humanize_item(a)
        if h:
            added_phrases.append(h)

    removed_phrases = []
    for r in removed_texts:
        h = humanize_item(r)
        if h:
            removed_phrases.append(h)

    parts = []
    if added_phrases:
        uniq = list(dict.fromkeys(added_phrases))
        if len(uniq) == 1:
            parts.append(f"{uniq[0]} added")
        else:
            parts.append(f"Added: {', '.join(uniq[:5])}")

    if removed_phrases:
        uniq = list(dict.fromkeys(removed_phrases))
        if len(uniq) == 1:
            parts.append(f"{uniq[0]} removed")
        else:
            parts.append(f"Removed: {', '.join(uniq[:5])}")

    if not parts:
        return "Page structure changed (no visible text differences found)"

    return " | ".join(parts)


def visual_diff(baseline_path, current_bytes):
    try:
        if not baseline_path or not os.path.exists(baseline_path):
            logger.info("No baseline screenshot found — skipping visual diff")
            return {"changed": False, "reason": "no baseline"}

        baseline_img = Image.open(baseline_path).convert("RGB")
        current_img = Image.open(io.BytesIO(current_bytes)).convert("RGB")

        if baseline_img.size != current_img.size:
            current_img = current_img.resize(baseline_img.size)

        diff_img = ImageChops.difference(baseline_img, current_img)
        pixels = list(diff_img.getdata())
        changed_pixels = sum(1 for p in pixels if any(c > 10 for c in p))
        total_pixels = len(pixels)
        change_ratio = changed_pixels / total_pixels

        changed = change_ratio > PIXEL_THRESHOLD

        logger.info("Visual diff — changed_pixels=%s ratio=%.4f changed=%s",
                    changed_pixels, change_ratio, changed)

        return {
            "changed": changed,
            "changed_pixels": changed_pixels,
            "total_pixels": total_pixels,
            "change_ratio": round(change_ratio, 4)
        }

    except Exception as e:
        logger.error("Visual diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


def html_diff(baseline_path, current_html):
    try:
        if not baseline_path or not os.path.exists(baseline_path):
            return {"changed": False, "reason": "no baseline"}

        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_html = f.read()

        baseline_clean = clean_html(baseline_html)
        current_clean = clean_html(current_html)

        baseline_lines = baseline_clean.splitlines()
        current_lines = current_clean.splitlines()

        diff = list(unified_diff(
            baseline_lines,
            current_lines,
            lineterm="",
            n=2
        ))

        changed = len(diff) > 0

        added_texts, removed_texts = extract_text_changes(diff)
        summary = summarize_changes(added_texts, removed_texts) if changed else "No changes"

        # Build structured change list with selector info
        changes_with_selectors = []
        for item in added_texts:
            changes_with_selectors.append({
                "type": "added",
                "text": item.get("text", ""),
                "selector": item.get("selector", "unknown"),
            })
        for item in removed_texts:
            changes_with_selectors.append({
                "type": "removed",
                "text": item.get("text", ""),
                "selector": item.get("selector", "unknown"),
            })

        logger.info("HTML diff — changed=%s diff_lines=%s summary=%s",
                    changed, len(diff), summary)

        return {
            "changed": changed,
            "diff_lines": len(diff),
            "diff_sample": diff[:50],
            "summary": summary,
            "added_texts": [i.get("text") for i in added_texts[:10]],
            "removed_texts": [i.get("text") for i in removed_texts[:10]],
            "changes_with_selectors": changes_with_selectors[:20],
        }

    except Exception as e:
        logger.error("HTML diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


def json_diff(baseline_path, current_har_data):
    try:
        if not baseline_path or not os.path.exists(baseline_path):
            logger.info("No baseline HAR found — skipping json diff")
            return {"changed": False, "reason": "no baseline"}

        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)

        diff = DeepDiff(baseline_data, current_har_data, ignore_order=True)
        changed = len(diff) > 0

        logger.info("JSON diff — changed=%s keys=%s", changed, list(diff.keys()))

        return {
            "changed": changed,
            "diff_keys": list(diff.keys()),
            "diff_summary": str(diff)[:500]
        }

    except Exception as e:
        logger.error("JSON diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


def har_diff(baseline_har_path, current_har_path):
    try:
        if not baseline_har_path or not os.path.exists(baseline_har_path):
            logger.info("No baseline HAR found — skipping har diff")
            return {"changed": False, "reason": "no baseline"}

        if not current_har_path or not os.path.exists(current_har_path):
            logger.info("No current HAR found — skipping har diff")
            return {"changed": False, "reason": "no current har"}

        with open(baseline_har_path, "r", encoding="utf-8") as f:
            baseline_har = json.load(f)

        with open(current_har_path, "r", encoding="utf-8") as f:
            current_har = json.load(f)

        baseline_urls = set(
            e["request"]["url"]
            for e in baseline_har.get("log", {}).get("entries", [])
        )
        current_urls = set(
            e["request"]["url"]
            for e in current_har.get("log", {}).get("entries", [])
        )

        new_endpoints = current_urls - baseline_urls
        removed_endpoints = baseline_urls - current_urls
        changed = len(new_endpoints) > 0 or len(removed_endpoints) > 0

        logger.info("HAR diff — new=%s removed=%s changed=%s",
                    len(new_endpoints), len(removed_endpoints), changed)

        return {
            "changed": changed,
            "new_endpoints": list(new_endpoints),
            "removed_endpoints": list(removed_endpoints)
        }

    except Exception as e:
        logger.error("HAR diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


async def run_all_diffs(portal_name, url, current_screenshot, current_html, baseline):
    if not baseline:
        logger.info("No baseline found for %s — skipping all diffs", url)
        return None

    diff_config = config.get("diff", {})
    tasks = {}

    if diff_config.get("visual", True):
        tasks["visual"] = asyncio.to_thread(
            visual_diff,
            baseline.get("screenshot_path"),
            current_screenshot
        )

    if diff_config.get("html", True):
        tasks["html"] = asyncio.to_thread(
            html_diff,
            baseline.get("html_path"),
            current_html
        )

    if diff_config.get("har", True):
        tasks["har"] = asyncio.to_thread(
            har_diff,
            baseline.get("har_path"),
            f"archive/{portal_name}_network.har"
        )

    results = {}
    if tasks:
        completed = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), completed):
            if isinstance(result, Exception):
                logger.error("Diff task %s failed — %s", key, str(result))
                results[key] = {"changed": False, "error": str(result)}
            else:
                results[key] = result

    any_changed = any(r.get("changed", False) for r in results.values())
    logger.info("Diff complete for %s — any_changed=%s", url, any_changed)

    return {
        "any_changed": any_changed,
        "results": results
    }


if __name__ == "__main__":
    print("diff_engine.py loaded successfully")
    print("Diff types available: visual, html, json, har")