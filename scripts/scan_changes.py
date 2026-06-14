#!/usr/bin/env python3
"""
Scan the changes table and classify each row as:
 - real: visible / meaningful change
 - trivial: structural / no visible text / zero pixels
 - noisy: low-confidence, placeholder summaries, or explicitly marked noise

Writes a small report to stdout (counts and samples).
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

from storage import get_conn, USE_SUPABASE

CFG = {}
try:
    with open(ROOT / "config.json", "r", encoding="utf-8") as f:
        CFG = json.load(f)
except Exception:
    CFG = {}

diff_cfg = CFG.get("diff", {})
CONF_THRESH = float(diff_cfg.get("noise_confidence_threshold", 0.6))
VISUAL_MIN = float(diff_cfg.get("visual_change_min_ratio", diff_cfg.get("pixel_threshold", 0.05)))
TEXT_MIN_WORDS = int(diff_cfg.get("text_change_min_words", 5))
TEXT_MIN_LINES = int(diff_cfg.get("text_line_min_changes", 3))


def fetch_rows(limit=None):
    sql = "SELECT id, portal, url, diff_type, diff_detail, ai_summary, timestamp FROM public.changes ORDER BY timestamp DESC" if USE_SUPABASE else "SELECT id, portal, url, diff_type, diff_detail, ai_summary, timestamp FROM changes ORDER BY timestamp DESC"
    if limit:
        sql = sql + f" LIMIT {int(limit)}"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    # Normalize rows to dicts
    norm = []
    for r in rows:
        if isinstance(r, dict):
            norm.append(r)
        else:
            # sequence -> map to column names
            cols = [c[0] for c in cur.description]
            norm.append(dict(zip(cols, r)))
    try:
        conn.close()
    except Exception:
        pass
    return norm


def parse_detail(d):
    if not d:
        return {}
    if isinstance(d, dict):
        return d
    try:
        return json.loads(d)
    except Exception:
        return {}


def classify_row(r):
    """Return category: 'real', 'trivial', 'noisy'"""
    ai = (r.get("ai_summary") or "") or ""
    if isinstance(ai, str) and ai.strip():
        low = ai.lower()
        if "no description" in low or "no visible" in low or "no changes" in low:
            return "noisy"
    detail = parse_detail(r.get("diff_detail"))
    if detail.get("is_noise"):
        return "noisy"
    try:
        conf = detail.get("confidence")
        conf = float(conf) if conf is not None else None
    except Exception:
        conf = None
    if conf is not None and conf < CONF_THRESH:
        return "noisy"

    dtype = (r.get("diff_type") or "").lower()
    if dtype == "visual":
        try:
            pixels = int(detail.get("changed_pixels") or 0)
        except Exception:
            pixels = 0
        try:
            ratio = float(detail.get("change_ratio") or 0.0)
        except Exception:
            ratio = 0.0
        if pixels == 0 or ratio <= VISUAL_MIN:
            return "trivial"
        return "real"
    if dtype == "html":
        try:
            words = int(detail.get("words_changed") or detail.get("wordsChanged") or 0)
        except Exception:
            words = 0
        try:
            lines = int(detail.get("diff_lines") or detail.get("lines_changed") or 0)
        except Exception:
            lines = 0
        highlighted = detail.get("highlighted_lines") or []
        if words >= TEXT_MIN_WORDS or lines >= TEXT_MIN_LINES or (highlighted and len(highlighted) > 0):
            return "real"
        return "trivial"
    if dtype in ("har", "json"):
        if not detail:
            return "trivial"
        if dtype == "har":
            new_ep = detail.get("new_endpoints") or []
            rem_ep = detail.get("removed_endpoints") or []
            if new_ep or rem_ep:
                return "real"
            return "trivial"
        return "real"
    # default
    return "real"


def run(limit=None):
    rows = fetch_rows(limit=limit)
    counts = {"real": 0, "trivial": 0, "noisy": 0}
    samples = {"real": [], "trivial": [], "noisy": []}
    for r in rows:
        cat = classify_row(r)
        counts[cat] += 1
        if len(samples[cat]) < 10:
            samples[cat].append({"id": r.get("id"), "portal": r.get("portal"), "url": r.get("url"), "type": r.get("diff_type")})

    print("Scan complete")
    print("Total rows scanned:", len(rows))
    print("Counts:", counts)
    for cat in ("real", "trivial", "noisy"):
        print("\nSample", cat.upper(), "rows:")
        for s in samples[cat]:
            print(" ", s)

    # Optionally write to file
    out = {"counts": counts, "samples": samples}
    with open(ROOT / "scan_changes_report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("\nWrote report to scan_changes_report.json")


if __name__ == "__main__":
    run(limit=1000)

