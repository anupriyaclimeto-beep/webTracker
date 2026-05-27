import streamlit as st
import sqlite3
import json
import os
from datetime import datetime

with open("config.json") as f:
    config = json.load(f)

DB_PATH = config["storage"]["db"]
ARCHIVE_DIR = config["storage"]["archive_dir"]

st.set_page_config(
    page_title="Portal Change Monitor",
    page_icon="🔍",
    layout="wide"
)


def query_db(query, args=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, args)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


def time_ago(timestamp_str):
    try:
        dt = datetime.fromisoformat(timestamp_str)
        diff = datetime.now() - dt
        total_seconds = int(diff.total_seconds())
        if total_seconds < 60:
            return "just now"
        elif total_seconds < 3600:
            return f"{total_seconds // 60} minutes ago"
        elif total_seconds < 86400:
            return f"{total_seconds // 3600} hours ago"
        else:
            return f"{diff.days} days ago"
    except Exception:
        return timestamp_str


def friendly_page_name(url):
    try:
        label = url.split("___")[-1].replace("_", " ")
        return label.title()
    except Exception:
        return url


def friendly_diff_type(diff_type):
    mapping = {
        "html": "📄 Content Changed",
        "visual": "🖼️ Visual Changed",
        "json": "📊 Data Changed",
        "har": "🔌 API Changed"
    }
    return mapping.get(diff_type, diff_type)


def severity_color(diff_lines):
    if diff_lines > 50:
        return "🔴 High"
    elif diff_lines > 10:
        return "🟡 Medium"
    else:
        return "🟢 Low"


def get_latest_crawl_id():
    rows = query_db(
        "SELECT id FROM crawl_log WHERE status='done' ORDER BY started_at DESC LIMIT 1"
    )
    return rows[0]["id"] if rows else None


def get_latest_crawl_changes(crawl_id):
    if not crawl_id:
        return []
    crawl_info = query_db(
        "SELECT started_at, finished_at FROM crawl_log WHERE id=?",
        (crawl_id,)
    )
    if not crawl_info:
        return []
    started = crawl_info[0]["started_at"]
    finished = crawl_info[0]["finished_at"] or datetime.now().isoformat()
    return query_db(
        "SELECT * FROM changes WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC",
        (started, finished)
    )


def render_html_change(detail):
    """Render human-readable HTML change summary."""

    # --- use pre-computed readable texts if available (new diff_engine) ---
    summary = detail.get("summary", "")
    added_texts = detail.get("added_texts", [])
    removed_texts = detail.get("removed_texts", [])

    if added_texts or removed_texts:
        if summary:
            st.info(f"💬 {summary}")
        if added_texts:
            st.markdown("🟢 **Added to the page:**")
            for item in added_texts[:5]:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {item}")
        if removed_texts:
            st.markdown("🔴 **Removed from the page:**")
            for item in removed_texts[:5]:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {item}")
        return

    # --- fallback: parse diff_sample for older records without readable texts ---
    diff_sample = detail.get("diff_sample", [])
    if not diff_sample:
        st.info("Content changed but diff details not available.")
        return

    added_html = [l[1:].strip() for l in diff_sample
                  if l.startswith("+") and not l.startswith("+++")]
    removed_html = [l[1:].strip() for l in diff_sample
                    if l.startswith("-") and not l.startswith("---")]

    # try to extract readable text from raw HTML lines
    from bs4 import BeautifulSoup
    import re

    def to_readable(lines):
        readable = []
        for raw in lines:
            # skip pure noise
            if re.search(r"echarts|_ngcontent|_nghost|ng-reflect", raw, re.I):
                continue
            try:
                soup = BeautifulSoup(raw, "html.parser")
                for tag in soup.find_all(["button", "a", "label", "span",
                                          "h1","h2","h3","h4","p","td","li"]):
                    text = tag.get_text(strip=True)
                    if text and len(text) > 1:
                        name = tag.name.upper()
                        readable.append(f'{name}: "{text}"' if name in ("BUTTON","A") else f'"{text}"')
                        break
                else:
                    plain = soup.get_text(strip=True)
                    if plain and len(plain) > 1:
                        readable.append(f'"{plain}"')
            except Exception:
                continue
        return list(dict.fromkeys(readable))  # deduplicate

    readable_added = to_readable(added_html)
    readable_removed = to_readable(removed_html)

    if readable_added or readable_removed:
        if readable_added:
            st.markdown("🟢 **Added to the page:**")
            for item in readable_added[:5]:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {item}")
        if readable_removed:
            st.markdown("🔴 **Removed from the page:**")
            for item in readable_removed[:5]:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {item}")
    else:
        # last resort: show raw HTML but collapsed
        st.markdown("🟢 **New content added:**" if added_html else "")
        for line in added_html[:3]:
            st.code(line, language="html")
        st.markdown("🔴 **Content removed:**" if removed_html else "")
        for line in removed_html[:3]:
            st.code(line, language="html")


# ── PAGE HEADER ──────────────────────────────────────────────────────────────

st.markdown("""
    <h1 style='font-size:28px;margin-bottom:0'>🔍 Portal Change Monitor</h1>
    <p style='color:gray;margin-top:4px'>
        Automatically monitors your portal and alerts you when anything changes
    </p>
    <hr>
""", unsafe_allow_html=True)

last_crawl = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 1")
latest_crawl_id = get_latest_crawl_id()
latest_changes = get_latest_crawl_changes(latest_crawl_id)

total_crawls = query_db("SELECT COUNT(*) as count FROM crawl_log")[0]["count"]
all_time_changes = query_db("SELECT COUNT(*) as count FROM changes")[0]["count"]

# ── STAT CARDS ───────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    change_count = len(latest_changes)
    bg = "#fff3cd" if change_count > 0 else "#d4edda"
    border = "#ffc107" if change_count > 0 else "#28a745"
    text = "#856404" if change_count > 0 else "#155724"
    icon = "⚠️" if change_count > 0 else "✅"
    st.markdown(f"""
        <div style='background:{bg};padding:16px;border-radius:10px;
                    border-left:4px solid {border}'>
            <div style='font-size:13px;color:{text}'>{icon} Changes in latest crawl</div>
            <div style='font-size:32px;font-weight:bold;color:{text}'>{change_count}</div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
        <div style='background:#d1ecf1;padding:16px;border-radius:10px;
                    border-left:4px solid #17a2b8'>
            <div style='font-size:13px;color:#0c5460'>📋 All Time Changes</div>
            <div style='font-size:32px;font-weight:bold;color:#0c5460'>{all_time_changes}</div>
        </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
        <div style='background:#d4edda;padding:16px;border-radius:10px;
                    border-left:4px solid #28a745'>
            <div style='font-size:13px;color:#155724'>✅ Total Crawls Done</div>
            <div style='font-size:32px;font-weight:bold;color:#155724'>{total_crawls}</div>
        </div>
    """, unsafe_allow_html=True)

with col4:
    if last_crawl:
        lc = last_crawl[0]
        sc = "#d4edda" if lc["status"] == "done" else "#f8d7da"
        sb = "#28a745" if lc["status"] == "done" else "#dc3545"
        st_color = "#155724" if lc["status"] == "done" else "#721c24"
        st.markdown(f"""
            <div style='background:{sc};padding:16px;border-radius:10px;
                        border-left:4px solid {sb}'>
                <div style='font-size:13px;color:{st_color}'>🕐 Last Crawl</div>
                <div style='font-size:14px;font-weight:bold;color:{st_color}'>
                    {time_ago(lc["started_at"])}
                </div>
                <div style='font-size:12px;color:{st_color}'>
                    {lc["pages_visited"]} pages scanned
                </div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── TABS ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "🚨 Latest Changes",
    "📸 Changed Pages",
    "📅 Crawl History"
])

with tab1:
    st.markdown("### Changes detected in the latest crawl")

    if last_crawl:
        lc = last_crawl[0]
        st.caption(
            f"Latest crawl: {lc['started_at'][:16]} — "
            f"{lc['pages_visited']} pages scanned — "
            f"Status: {lc['status']}"
        )

    if not latest_changes:
        st.success(
            "✅ No changes detected in the latest crawl — "
            "your portal looks the same as before."
        )
    else:
        st.warning(f"⚠️ {len(latest_changes)} change(s) detected in the latest crawl.")

        for change in latest_changes:
            page_name = friendly_page_name(change["url"])
            diff_label = friendly_diff_type(change["diff_type"])
            when = time_ago(change["timestamp"])
            date_str = change["timestamp"][:16]

            try:
                detail = json.loads(change["diff_detail"])
                diff_lines = detail.get("diff_lines", 0)
                severity = severity_color(diff_lines)
                # use summary for expander title if available
                summary = detail.get("summary", "")
            except Exception:
                diff_lines = 0
                severity = "🟢 Low"
                summary = ""
                detail = {}

            # expander title: show summary inline if short enough
            expander_title = f"{diff_label} — **{page_name}** — {when} ({date_str})"
            if summary and len(summary) < 80:
                expander_title += f" — _{summary}_"

            with st.expander(expander_title):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Page:** {page_name}")
                with col_b:
                    st.markdown(f"**Severity:** {severity}")
                with col_c:
                    st.markdown(f"**Detected:** {date_str}")

                st.markdown("---")
                st.markdown("**What changed on this page:**")

                if change["diff_type"] == "html":
                    render_html_change(detail)

                elif change["diff_type"] == "visual":
                    try:
                        ratio = detail.get("change_ratio", 0)
                        pixels = detail.get("changed_pixels", 0)
                        st.info(
                            f"🖼️ The page appearance changed — "
                            f"{pixels:,} pixels were different "
                            f"({ratio*100:.1f}% of the page)"
                        )
                    except Exception:
                        st.info("The page looks visually different from before.")

                elif change["diff_type"] == "har":
                    try:
                        new_ep = detail.get("new_endpoints", [])
                        removed_ep = detail.get("removed_endpoints", [])
                        if new_ep:
                            st.markdown(f"🟢 **{len(new_ep)} new API endpoint(s) appeared**")
                            for ep in new_ep[:3]:
                                st.code(ep)
                        if removed_ep:
                            st.markdown(f"🔴 **{len(removed_ep)} API endpoint(s) removed**")
                            for ep in removed_ep[:3]:
                                st.code(ep)
                    except Exception:
                        st.info("API/network change detected.")

                st.markdown("---")
                st.markdown(f"**Portal:** `{change['portal']}`")
                st.markdown(f"**Page URL:** `{change['url'].split('___')[0]}`")


with tab2:
    st.markdown("### Screenshots of pages that changed")
    st.caption("Only showing pages where changes were detected in the latest crawl.")

    if not latest_changes:
        st.success("✅ No changed pages in the latest crawl.")
    else:
        changed_urls = list({c["url"] for c in latest_changes})

        for url in changed_urls:
            page_name = friendly_page_name(url)
            baseline = query_db(
                "SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2",
                (url,)
            )
            page_changes = query_db(
                "SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC",
                (url,)
            )

            if not baseline:
                continue

            # baseline may contain up to 2 rows: [latest, previous]
            latest_baseline = baseline[0] if len(baseline) > 0 else None
            prev_baseline = baseline[1] if len(baseline) > 1 else None
            last_change = (
                page_changes[0]["timestamp"][:16] if page_changes else "—"
            )

            st.markdown(f"### 📄 {page_name}")
            st.caption(f"Change detected at: {last_change}")

            # show previous vs latest screenshots side-by-side for quick visual comparison
            col_prev, col_latest = st.columns(2)
            with col_prev:
                st.markdown("**Previous screenshot:**")
                if prev_baseline:
                    prev_screenshot = prev_baseline.get("screenshot_path")
                    if prev_screenshot and os.path.exists(prev_screenshot):
                        st.image(prev_screenshot, use_container_width=True)
                    else:
                        st.info("Previous screenshot not available")
                    # link to raw previous HTML
                    prev_html = prev_baseline.get("html_path")
                    if prev_html and os.path.exists(prev_html):
                        st.markdown(f"Previous snapshot: `{prev_html}`")
                else:
                    st.info("No previous snapshot available")

            with col_latest:
                st.markdown("**Latest screenshot:**")
                if latest_baseline:
                    latest_screenshot = latest_baseline.get("screenshot_path")
                    if latest_screenshot and os.path.exists(latest_screenshot):
                        st.image(latest_screenshot, use_container_width=True)
                    else:
                        st.info("Latest screenshot not available")
                    latest_html = latest_baseline.get("html_path")
                    if latest_html and os.path.exists(latest_html):
                        st.markdown(f"Latest snapshot: `{latest_html}`")
                else:
                    st.info("Latest snapshot not available")

            st.markdown("---")

            # details about what changed (textual / visual / har)
            st.markdown("**What changed:**")
            for change in page_changes[:3]:
                diff_label = friendly_diff_type(change["diff_type"])
                st.markdown(f"**{diff_label}**")
                try:
                    detail = json.loads(change["diff_detail"])
                    if change["diff_type"] == "html":
                        render_html_change(detail)
                    elif change["diff_type"] == "visual":
                        ratio = detail.get("change_ratio", 0)
                        st.info(f"Page appearance changed by {ratio*100:.1f}%")
                except Exception:
                    st.info("Change detected but details unavailable.")

            st.markdown("---")


with tab3:
    st.markdown("### Crawl history")
    st.caption("Every time the crawler ran and how many pages it scanned.")

    crawl_logs = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC")

    if not crawl_logs:
        st.info("No crawls recorded yet.")
    else:
        for log in crawl_logs:
            status_icon = "✅" if log["status"] == "done" else "❌"
            started = log["started_at"][:16]
            finished = log["finished_at"][:16] if log["finished_at"] else "—"
            pages = log["pages_visited"]

            crawl_changes = query_db(
                "SELECT COUNT(*) as count FROM changes "
                "WHERE timestamp >= ? AND timestamp <= ?",
                (
                    log["started_at"],
                    log["finished_at"] or datetime.now().isoformat()
                )
            )
            change_count = crawl_changes[0]["count"] if crawl_changes else 0
            change_badge = (
                f"⚠️ {change_count} changes" if change_count > 0 else "✅ No changes"
            )

            st.markdown(f"""
                <div style='background:#f8f9fa;padding:12px 16px;border-radius:8px;
                            margin-bottom:8px;border-left:4px solid
                            {"#28a745" if log["status"] == "done" else "#dc3545"}'>
                    <b>{status_icon} Crawl on {started}</b>
                    &nbsp;&nbsp;<span style='font-size:12px;
                    background:{"#fff3cd" if change_count > 0 else "#d4edda"};
                    padding:2px 8px;border-radius:4px;
                    color:{"#856404" if change_count > 0 else "#155724"}'>
                        {change_badge}
                    </span><br>
                    <span style='color:gray;font-size:13px'>
                        Finished: {finished} &nbsp;|&nbsp;
                        Pages scanned: {pages} &nbsp;|&nbsp;
                        Portal: {log["portal"]}
                    </span>
                </div>
            """, unsafe_allow_html=True)

st.markdown("---")
st.caption(
    f"Auto-monitoring active · "
    f"Last refreshed: {datetime.now().strftime('%d %b %Y, %I:%M %p')} · "
    f"Refresh page to update"
)