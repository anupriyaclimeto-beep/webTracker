"""
ai_summarizer.py — Generate plain-English change summaries using Gemini API.

Called once per detected change (at crawl time) and cached in the DB so the
dashboard never makes a live API call.
"""

import json
import logging
import re
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Optional: still loads config.json for future use
try:
    with open("config.json") as f:
        _cfg = json.load(f)
except Exception:
    _cfg = {}

# Gemini API Configuration
GEMINI_API_KEY = "AIzaSyB1xXn-Wk7hrRW58u4V1V8H52yTTyXfgrw"
MODEL = "gemini-2.0-flash"
MAX_TOKENS = 100

# Friendly display names for URL keys
_PAGE_NAME_HINTS = {
    "__DROPDOWN_SOP": "SOP dropdown menu",
    "__DROPDOWN_ImportantDocuments": "Important Documents dropdown menu",
    "__DROPDOWN_BulkUpload": "Bulk Upload dropdown menu",
    "__DROPDOWN_LodgeComplaint": "Lodge Complaint dropdown menu",
    "__DROPDOWN_AboutEPR": "About EPR dropdown menu",
    "__DROPDOWN_PlasticWasteManagement": "Plastic Waste Management dropdown menu",
    "categoriesepr": "Categories of Plastic Waste page",
    "eprtargets": "EPR Target page",
    "pibopwp": "Responsibility of PIBOs page",
    "plasticwaste": "Plastic Waste Processing page",
    "home": "Home page",
}


def _page_hint(url: str) -> str:
    """Return a human-friendly page description from the URL."""
    for key, label in _PAGE_NAME_HINTS.items():
        if key.lower() in url.lower():
            return label

    # fallback: last path segment
    clean = url.split("?")[0].rstrip("/")
    segment = clean.split("/")[-1].replace("_", " ").replace("-", " ")

    return segment or "the page"


def _build_prompt(url: str, diff_type: str, diff_detail: dict) -> str:
    """
    Construct a concise prompt that gives Gemini everything it needs
    to write a plain-English summary.
    """

    page = _page_hint(url)

    # ── HTML / content diff ────────────────────────────────────────────────
    if diff_type == "html":

        added = diff_detail.get("added_texts", [])
        removed = diff_detail.get("removed_texts", [])
        with_sel = diff_detail.get("changes_with_selectors", [])
        summary = diff_detail.get("summary", "")

        change_lines = []

        for item in with_sel[:12]:

            direction = "Added" if item.get("type") == "added" else "Removed"
            text = item.get("text", "")
            selector = item.get("selector", "")

            if text:
                change_lines.append(
                    f"- {direction}: {text} (CSS path: {selector})"
                )

        if not change_lines:

            for t in added[:6]:
                change_lines.append(f"- Added: {t}")

            for t in removed[:6]:
                change_lines.append(f"- Removed: {t}")

        changes_block = (
            "\n".join(change_lines)
            if change_lines
            else summary or "Structure changed."
        )

        return f"""
You are summarizing a website change for a non-technical government official.

Page monitored: {page}
Change type: Content / HTML

Raw detected changes:
{changes_block}

Write ONE plain-English sentence (max 30 words) explaining:
1. What changed
2. Roughly where on the page it happened

Examples:
- "New instructions were added near the top of the page."
- "Important document links were removed from the dropdown menu."

Rules:
- Use simple language
- Do NOT mention HTML, CSS, selectors, DOM, or technical terms
- Do NOT start with "The page"
- Reply with only the sentence
"""

    # ── Visual diff ────────────────────────────────────────────────────────
    elif diff_type == "visual":

        ratio = diff_detail.get("change_ratio", 0)
        pixels = diff_detail.get("changed_pixels", 0)

        pct = round(ratio * 100, 1)

        area = (
            "small"
            if pct < 5
            else ("moderate" if pct < 20 else "large")
        )

        return f"""
You are summarizing a website change for a non-technical government official.

Page monitored: {page}
Change type: Visual appearance

Changed pixels: {pixels:,}
Change percentage: {pct}%
Affected area: {area}

Write ONE simple sentence (max 25 words).

Examples:
- "The appearance of the home page changed slightly."
- "A large section of the Important Documents page now looks different."

Reply with only the sentence.
"""

    # ── HAR / API diff ─────────────────────────────────────────────────────
    elif diff_type == "har":

        new_ep = diff_detail.get("new_endpoints", [])
        removed_ep = diff_detail.get("removed_endpoints", [])

        parts = []

        if new_ep:
            parts.append(
                f"New API calls detected: {', '.join(new_ep[:3])}"
            )

        if removed_ep:
            parts.append(
                f"API calls removed: {', '.join(removed_ep[:3])}"
            )

        block = "\n".join(parts) or "API endpoints changed."

        return f"""
You are summarizing a website change for a non-technical government official.

Page monitored: {page}
Change type: Network / API

{block}

Write ONE plain-English sentence (max 25 words).

Do NOT use technical jargon.

Example:
"The page is now loading information from a new source behind the scenes."

Reply with only the sentence.
"""

    # ── JSON diff ──────────────────────────────────────────────────────────
    else:

        summary = diff_detail.get(
            "diff_summary",
            "Data structure changed."
        )

        return f"""
You are summarizing a website change for a non-technical government official.

Page monitored: {page}
Change type: Data / JSON

Raw diff summary:
{summary[:300]}

Write ONE plain-English sentence (max 25 words)
explaining what changed in simple terms.

Reply with only the sentence.
"""


def generate_ai_summary(url: str, diff_type: str, diff_detail: dict) -> str:
    """
    Call Gemini API and return a plain-English summary.
    Falls back gracefully on any failure.
    """

    fallback = diff_detail.get("summary", "Change detected.")

    if not GEMINI_API_KEY:
        logger.warning("No Gemini API key configured")
        return fallback

    prompt = _build_prompt(url, diff_type, diff_detail)

    payload = json.dumps({
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": MAX_TOKENS
        }
    }).encode("utf-8")

    api_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(req, timeout=15) as resp:

            body = json.loads(resp.read().decode("utf-8"))

            text = (
                body["candidates"][0]
                ["content"]["parts"][0]["text"]
                .strip()
            )

            # Remove accidental prefixes
            text = re.sub(
                r"^(summary|answer|result)\s*:\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )

            logger.info(
                "Gemini summary generated for %s [%s]: %s",
                url,
                diff_type,
                text,
            )

            return text

    except urllib.error.HTTPError as e:

        body = e.read().decode("utf-8", errors="ignore")

        logger.error(
            "Gemini API HTTP %s — %s",
            e.code,
            body[:300]
        )

        return fallback

    except Exception as e:

        logger.error("Gemini API error — %s", e)

        return fallback