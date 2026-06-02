import asyncio
import json
import logging
import os
import re
from difflib import unified_diff, SequenceMatcher
from PIL import Image, ImageChops, ImageDraw, ImageFilter
import io
from deepdiff import DeepDiff
from bs4 import BeautifulSoup, Comment
import html as _html
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

PIXEL_THRESHOLD = config["diff"].get("pixel_threshold", 0.05)


def fetch_url_or_read_file(path_or_url: str, as_bytes: bool = False):
    """Fetch content from an HTTP URL or read from local disk."""
    if not path_or_url:
        return None
    try:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            resp = requests.get(path_or_url, timeout=15)
            resp.raise_for_status()
            return resp.content if as_bytes else resp.text
        else:
            if not os.path.exists(path_or_url):
                return None
            mode = "rb" if as_bytes else "r"
            encoding = None if as_bytes else "utf-8"
            with open(path_or_url, mode, encoding=encoding) as f:
                return f.read()
    except Exception as e:
        logger.error(f"Failed to load {path_or_url}: {e}")
        return None


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
                    attrs_to_remove.append(attr); continue
                if attr_lower.startswith("_echarts_instance"):
                    attrs_to_remove.append(attr); continue
                if attr_lower in ("data-uid","data-reactid","data-reactroot","data-ember-action","data-guid"):
                    attrs_to_remove.append(attr); continue
                if attr_lower == "class":
                    if isinstance(value, list):
                        attrs_to_clean[attr] = [v for v in value if "ng-star-inserted" not in v]
                    elif isinstance(value, str):
                        attrs_to_clean[attr] = value.replace("ng-star-inserted","").strip()
                    continue
                if attr_lower.startswith("ng-reflect"):
                    attrs_to_remove.append(attr); continue
                if attr_lower == "autocomplete" and isinstance(value, str):
                    if re.fullmatch(r"[a-f0-9]{8,}", value):
                        attrs_to_remove.append(attr); continue
                if attr_lower in ("nonce","data-nonce","data-token","data-csrf","data-requestverificationtoken"):
                    attrs_to_remove.append(attr); continue
                if attr_lower == "style" and isinstance(value, str):
                    cleaned_style = re.sub(r"max-height\s*:\s*calc\([^)]+\)\s*;?","",value).strip().rstrip(";")
                    attrs_to_clean[attr] = cleaned_style; continue
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
    parts = []
    node = tag
    for _ in range(5):
        if node is None or node.name is None:
            break
        label = node.name
        if node.get("id"):
            label += f'#{node["id"]}'
        elif node.get("class"):
            cls = " ".join(c for c in node["class"] if c)
            if cls:
                label += f'.{cls.split()[0]}'
        parts.append(label)
        node = node.parent
    parts.reverse()
    return " > ".join(parts) if parts else "unknown"


def extract_text_changes(diff_sample):
    added_texts = []
    removed_texts = []
    for line in diff_sample:
        if line.startswith("+") and not line.startswith("+++"):
            result = extract_readable_text(line[1:].strip())
            if result:
                added_texts.append(result)
        elif line.startswith("-") and not line.startswith("---"):
            result = extract_readable_text(line[1:].strip())
            if result:
                removed_texts.append(result)
    return added_texts, removed_texts


def extract_readable_text(html_fragment):
    try:
        noise_patterns = [r"^<[^>]+>$", r"echarts", r"_ngcontent|_nghost", r"ng-reflect", r"^\s*$"]
        for pattern in noise_patterns:
            if re.search(pattern, html_fragment, re.IGNORECASE):
                return None
        soup = BeautifulSoup(html_fragment, "html.parser")
        for tag in soup.find_all(["button","a","label","h1","h2","h3","h4","h5","span","td","th","li","p"]):
            text = tag.get_text(strip=True)
            if text and len(text) > 1:
                tag_name = tag.name.upper()
                selector = build_selector(tag)
                if tag_name in ("BUTTON","A"):
                    return {"text": f'{tag_name}: "{text}"', "selector": selector}
                return {"text": f'"{text}"', "selector": selector}
        plain = soup.get_text(strip=True)
        if plain and len(plain) > 1:
            return {"text": f'"{plain}"', "selector": "unknown"}
        return None
    except Exception:
        return None


def summarize_changes(added_texts, removed_texts):
    def humanize_item(item):
        if not item:
            return None
        text = item.get("text","").strip()
        selector = item.get("selector","")
        m = re.match(r'^(?P<tag>[A-Z]+):\s*"(.*)"$', text)
        if m:
            tag = m.group("tag").lower()
            label = m.group(2)
            phrase = f'Button "{label}"' if tag=="button" else (f'Link "{label}"' if tag=="a" else f'{tag.capitalize()} "{label}"')
        else:
            q = re.match(r'^"(.*)"$', text)
            phrase = f'"{q.group(1)}"' if q else (text if len(text)<100 else text[:97]+"...")
        if selector and selector != "unknown":
            phrase += f" [{selector}]"
        return phrase

    added_phrases   = list(dict.fromkeys(filter(None, [humanize_item(a) for a in added_texts])))
    removed_phrases = list(dict.fromkeys(filter(None, [humanize_item(r) for r in removed_texts])))

    parts = []
    if added_phrases:
        parts.append(f"Added: {', '.join(added_phrases[:5])}" if len(added_phrases)>1 else f"{added_phrases[0]} added")
    if removed_phrases:
        parts.append(f"Removed: {', '.join(removed_phrases[:5])}" if len(removed_phrases)>1 else f"{removed_phrases[0]} removed")
    return " | ".join(parts) if parts else "Page structure changed (no visible text differences found)"


# ── WORD-LEVEL DIFF ───────────────────────────────────────────────────────────

def word_level_diff(old_line: str, new_line: str) -> tuple:
    """
    Return (old_html, new_html) with <del class='word'>/<ins class='word'> tags
    wrapping only the words that actually changed.
    """
    old_words = old_line.split()
    new_words = new_line.split()
    sm = SequenceMatcher(None, old_words, new_words, autojunk=False)
    old_parts, new_parts = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        old_chunk = " ".join(old_words[i1:i2])
        new_chunk = " ".join(new_words[j1:j2])
        if tag == "equal":
            if old_chunk:
                old_parts.append(old_chunk)
            if new_chunk:
                new_parts.append(new_chunk)
        else:
            if old_chunk:
                old_parts.append(f'<del class="word">{old_chunk}</del>')
            if new_chunk:
                new_parts.append(f'<ins class="word">{new_chunk}</ins>')
    return " ".join(old_parts), " ".join(new_parts)


# ── HIGHLIGHT DIFF IMAGE ──────────────────────────────────────────────────────

def generate_diff_image(baseline_path: str, current_bytes: bytes):
    try:
        baseline_bytes = fetch_url_or_read_file(baseline_path, as_bytes=True)
        if not baseline_bytes:
            return None
        baseline_img = Image.open(io.BytesIO(baseline_bytes)).convert("RGB")
        current_img  = Image.open(io.BytesIO(current_bytes)).convert("RGB")

        if baseline_img.size != current_img.size:
            current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

        w, h = baseline_img.size

        diff_img    = ImageChops.difference(baseline_img, current_img)
        diff_arr    = diff_img.load()
        mask        = Image.new("L", (w, h), 0)

        changed_pixels = 0
        for y in range(h):
            for x in range(w):
                r, g, b = diff_arr[x, y]
                if r > 15 or g > 15 or b > 15:
                    changed_pixels += 1
                    mask.putpixel((x, y), 255)

        mask = mask.filter(ImageFilter.MaxFilter(11))

        pad     = 6
        label_h = 32
        comp_w  = w * 2 + pad * 3
        comp_h  = h + label_h + pad * 2

        comp = Image.new("RGB", (comp_w, comp_h), (18, 22, 30))

        def dim(img, factor=0.75):
            r, g, b = img.split()
            return Image.merge("RGB", [
                r.point(lambda x: int(x * factor)),
                g.point(lambda x: int(x * factor)),
                b.point(lambda x: int(x * factor)),
            ])

        base_dim    = dim(baseline_img)
        current_dim = dim(current_img)

        left_x  = pad
        right_x = pad + w + pad
        top_y   = label_h + pad

        comp.paste(base_dim,    (left_x,  top_y))
        comp.paste(current_dim, (right_x, top_y))

        red_overlay = Image.new("RGB", (w, h), (255, 50, 50))
        comp.paste(red_overlay, (left_x,  top_y), mask)
        comp.paste(red_overlay, (right_x, top_y), mask)

        draw = ImageDraw.Draw(comp)
        draw.rectangle([0, 0, comp_w, label_h], fill=(12, 15, 22))
        draw.text((left_x  + w//2 - 40, 8), "< BEFORE",  fill=(200, 210, 230))
        draw.text((right_x + w//2 - 40, 8), "AFTER >",   fill=(200, 210, 230))

        total_pixels = w * h
        pct = changed_pixels / total_pixels * 100
        badge_text = f"  {changed_pixels:,} px changed ({pct:.1f}%)  "
        badge_x = comp_w // 2 - 80
        draw.rectangle([badge_x - 2, 4, badge_x + 160, label_h - 4], fill=(30, 40, 60), outline=(60, 100, 160))
        draw.text((badge_x + 4, 9), badge_text, fill=(96, 165, 250))

        buf = io.BytesIO()
        comp.save(buf, format="PNG", optimize=True)
        logger.info("Diff image generated — changed_pixels=%s (%.1f%%)", changed_pixels, pct)
        return buf.getvalue()

    except Exception as e:
        logger.error("generate_diff_image error — %s", e)
        return None


# ── VISUAL DIFF ───────────────────────────────────────────────────────────────

def visual_diff(baseline_path, current_bytes, diff_image_save_path=None):
    try:
        if not baseline_path:
            logger.info("No baseline screenshot found — skipping visual diff")
            return {"changed": False, "reason": "no baseline"}
            
        baseline_bytes = fetch_url_or_read_file(baseline_path, as_bytes=True)
        if not baseline_bytes:
            logger.info("Failed to load baseline screenshot — skipping visual diff")
            return {"changed": False, "reason": "failed to load baseline"}

        baseline_img = Image.open(io.BytesIO(baseline_bytes)).convert("RGB")
        current_img  = Image.open(io.BytesIO(current_bytes)).convert("RGB")

        if baseline_img.size != current_img.size:
            current_img = current_img.resize(baseline_img.size, Image.LANCZOS)

        diff_img       = ImageChops.difference(baseline_img, current_img)
        pixels         = list(diff_img.getdata())
        changed_pixels = sum(1 for p in pixels if any(c > 10 for c in p))
        total_pixels   = len(pixels)
        change_ratio   = changed_pixels / total_pixels
        changed        = change_ratio > PIXEL_THRESHOLD

        diff_image_path = None
        if changed:
            diff_bytes = generate_diff_image(baseline_path, current_bytes)
            if diff_bytes and diff_image_save_path:
                os.makedirs(os.path.dirname(diff_image_save_path), exist_ok=True)
                with open(diff_image_save_path, "wb") as f:
                    f.write(diff_bytes)
                diff_image_path = diff_image_save_path
                logger.info("Diff image saved → %s", diff_image_save_path)

        logger.info("Visual diff — changed_pixels=%s ratio=%.4f changed=%s",
                    changed_pixels, change_ratio, changed)

        return {
            "changed":        changed,
            "changed_pixels": changed_pixels,
            "total_pixels":   total_pixels,
            "change_ratio":   round(change_ratio, 4),
            "diff_image_path": diff_image_path,
        }

    except Exception as e:
        logger.error("Visual diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


# ── HTML DIFF ─────────────────────────────────────────────────────────────────

def html_diff(baseline_path, current_html):
    try:
        if not baseline_path:
            return {"changed": False, "reason": "no baseline"}

        baseline_html = fetch_url_or_read_file(baseline_path, as_bytes=False)
        if not baseline_html:
            return {"changed": False, "reason": "failed to load baseline html"}

        baseline_clean = clean_html(baseline_html)
        current_clean  = clean_html(current_html)

        baseline_lines = baseline_clean.splitlines()
        current_lines  = current_clean.splitlines()

        diff = list(unified_diff(baseline_lines, current_lines, lineterm="", n=2))
        changed = len(diff) > 0

        added_texts, removed_texts = extract_text_changes(diff)
        summary = summarize_changes(added_texts, removed_texts) if changed else "No changes"

        changes_with_selectors = []
        for item in added_texts:
            changes_with_selectors.append({"type":"added",   "text": item.get("text",""), "selector": item.get("selector","unknown")})
        for item in removed_texts:
            changes_with_selectors.append({"type":"removed", "text": item.get("text",""), "selector": item.get("selector","unknown")})

        # ── build highlighted diff with word-level inline markup ──────────────
        highlighted_lines = []
        pending_removed = []

        for line in diff[:200]:
            if line.startswith("+++") or line.startswith("---"):
                continue

            if line.startswith("-") and not line.startswith("---"):
                # Buffer removed lines — they may be paired with a following add
                pending_removed.append(line[1:])

            elif line.startswith("+") and not line.startswith("+++"):
                new_text = line[1:]
                if pending_removed:
                    # Pair with the earliest buffered removed line → word-level diff
                    old_text = pending_removed.pop(0)
                    old_html, new_html = word_level_diff(old_text.strip(), new_text.strip())
                    highlighted_lines.append({"type": "removed", "text": old_text, "html": old_html})
                    highlighted_lines.append({"type": "added",   "text": new_text, "html": new_html})
                else:
                    # Pure addition — wrap entire line in <ins>
                    safe = new_text.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    highlighted_lines.append({
                        "type": "added",
                        "text": new_text,
                        "html": f'<ins class="word">{safe}</ins>',
                    })

            else:
                # Context line — flush any leftover unpaired removes first
                for rem in pending_removed:
                    safe = rem.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    highlighted_lines.append({
                        "type": "removed",
                        "text": rem,
                        "html": f'<del class="word">{safe}</del>',
                    })
                pending_removed = []

                if line.startswith("@@"):
                    highlighted_lines.append({"type": "context_header", "text": line, "html": line})
                else:
                    t = line[1:] if line.startswith(" ") else line
                    safe = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    highlighted_lines.append({"type": "context", "text": t, "html": safe})

        # Flush any trailing unpaired removes
        for rem in pending_removed:
            safe = rem.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            highlighted_lines.append({
                "type": "removed",
                "text": rem,
                "html": f'<del class="word">{safe}</del>',
            })

        # Build an HTML-friendly highlighted snippet from the unified diff.
        # Escape HTML and wrap added/removed/context lines with classes for UI rendering.
        try:
            snippet_lines = []
            for line in diff[:400]:  # limit size to avoid huge payloads
                if line.startswith("+++ ") or line.startswith("--- "):
                    snippet_lines.append(f'<div class="udiff-meta">{_html.escape(line)}</div>')
                elif line.startswith("@@"):
                    snippet_lines.append(f'<div class="udiff-hunk">{_html.escape(line)}</div>')
                elif line.startswith("+") and not line.startswith("+++"):
                    snippet_lines.append(f'<div class="udiff-line added">+ {_html.escape(line[1:])}</div>')
                elif line.startswith("-") and not line.startswith("---"):
                    snippet_lines.append(f'<div class="udiff-line removed">- {_html.escape(line[1:])}</div>')
                elif line.startswith(" "):
                    snippet_lines.append(f'<div class="udiff-line context"> {_html.escape(line[1:])}</div>')
                else:
                    snippet_lines.append(f'<div class="udiff-line">{_html.escape(line)}</div>')
            html_snippet = "<div class='html-diff'>" + "\n".join(snippet_lines) + "</div>"
        except Exception:
            html_snippet = None

        logger.info("HTML diff — changed=%s diff_lines=%s summary=%s", changed, len(diff), summary)

        return {
            "changed":               changed,
            "diff_lines":            len(diff),
            "diff_sample":           diff[:50],
            "summary":               summary,
            "added_texts":           [i.get("text") for i in added_texts[:10]],
            "removed_texts":         [i.get("text") for i in removed_texts[:10]],
            "changes_with_selectors": changes_with_selectors[:20],
            "highlighted_lines":     highlighted_lines,
            "html_snippet":          html_snippet,
        }

    except Exception as e:
        logger.error("HTML diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


# ── JSON DIFF ─────────────────────────────────────────────────────────────────

def json_diff(baseline_path, current_har_data):
    try:
        if not baseline_path or not os.path.exists(baseline_path):
            return {"changed": False, "reason": "no baseline"}
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)
        diff = DeepDiff(baseline_data, current_har_data, ignore_order=True)
        changed = len(diff) > 0
        logger.info("JSON diff — changed=%s keys=%s", changed, list(diff.keys()))
        return {"changed": changed, "diff_keys": list(diff.keys()), "diff_summary": str(diff)[:500]}
    except Exception as e:
        logger.error("JSON diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


# ── HAR DIFF ──────────────────────────────────────────────────────────────────

def har_diff(baseline_har_path, current_har_path):
    try:
        if not baseline_har_path or not os.path.exists(baseline_har_path):
            return {"changed": False, "reason": "no baseline"}
        if not current_har_path or not os.path.exists(current_har_path):
            return {"changed": False, "reason": "no current har"}
        with open(baseline_har_path, "r", encoding="utf-8") as f:
            baseline_har = json.load(f)
        with open(current_har_path, "r", encoding="utf-8") as f:
            current_har = json.load(f)
        baseline_urls = set(e["request"]["url"] for e in baseline_har.get("log",{}).get("entries",[]))
        current_urls  = set(e["request"]["url"] for e in current_har.get("log",{}).get("entries",[]))
        new_endpoints     = current_urls - baseline_urls
        removed_endpoints = baseline_urls - current_urls
        changed = len(new_endpoints) > 0 or len(removed_endpoints) > 0
        logger.info("HAR diff — new=%s removed=%s changed=%s", len(new_endpoints), len(removed_endpoints), changed)
        return {"changed": changed, "new_endpoints": list(new_endpoints), "removed_endpoints": list(removed_endpoints)}
    except Exception as e:
        logger.error("HAR diff error — %s", str(e))
        return {"changed": False, "error": str(e)}


# ── RUN ALL DIFFS ─────────────────────────────────────────────────────────────

async def run_all_diffs(portal_name, url, current_screenshot, current_html, baseline,
                        diff_image_save_path=None):
    if not baseline:
        logger.info("No baseline found for %s — skipping all diffs", url)
        return None

    diff_config = config.get("diff", {})
    tasks = {}

    if diff_config.get("visual", True):
        tasks["visual"] = asyncio.to_thread(
            visual_diff,
            baseline.get("screenshot_url") or baseline.get("screenshot_path"),
            current_screenshot,
            diff_image_save_path,
        )

    if diff_config.get("html", True):
        tasks["html"] = asyncio.to_thread(
            html_diff,
            baseline.get("html_url") or baseline.get("html_path"),
            current_html,
        )

    if diff_config.get("har", True):
        tasks["har"] = asyncio.to_thread(
            har_diff,
            baseline.get("har_path"),
            f"archive/{portal_name}_network.har",
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

    return {"any_changed": any_changed, "results": results}


if __name__ == "__main__":
    print("diff_engine.py loaded successfully")
    print("Diff types available: visual (with highlight), html (with word-level highlight), json, har")