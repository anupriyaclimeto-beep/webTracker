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


st.markdown("""
    <h1 style='font-size:28px;margin-bottom:0'>🔍 Portal Change Monitor</h1>
    <p style='color:gray;margin-top:4px'>
        Automatically monitors your portal and alerts you when anything changes
    </p>
    <hr>
""", unsafe_allow_html=True)

last_crawl = query_db(
    "SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 1"
)
latest_crawl_id = get_latest_crawl_id()
latest_changes = get_latest_crawl_changes(latest_crawl_id)

total_crawls = query_db("SELECT COUNT(*) as count FROM crawl_log")[0]["count"]
all_time_changes = query_db("SELECT COUNT(*) as count FROM changes")[0]["count"]

col1, col2, col3, col4 = st.columns(4)

with col1:
    change_count = len(latest_changes)
    bg = "#fff3cd" if change_count > 0 else "#d4edda"
    border = "#ffc107" if change_count > 0 else "#28a745"
    text = "#856404" if change_count > 0 else "#155724"
    icon = "⚠️" if change_count > 0 else "✅"
    label = "Changes in latest crawl"
    st.markdown(f"""
        <div style='background:{bg};padding:16px;border-radius:10px;
                    border-left:4px solid {border}'>
            <div style='font-size:13px;color:{text}'>{icon} {label}</div>
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
        status_color = "#d4edda" if lc["status"] == "done" else "#f8d7da"
        status_border = "#28a745" if lc["status"] == "done" else "#dc3545"
        status_text = "#155724" if lc["status"] == "done" else "#721c24"
        st.markdown(f"""
            <div style='background:{status_color};padding:16px;border-radius:10px;
                        border-left:4px solid {status_border}'>
                <div style='font-size:13px;color:{status_text}'>🕐 Last Crawl</div>
                <div style='font-size:14px;font-weight:bold;color:{status_text}'>
                    {time_ago(lc["started_at"])}
                </div>
                <div style='font-size:12px;color:{status_text}'>
                    {lc["pages_visited"]} pages scanned
                </div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

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
            except Exception:
                diff_lines = 0
                severity = "🟢 Low"

            with st.expander(
                f"{diff_label} — **{page_name}** — {when} ({date_str})"
            ):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Page:** {page_name}")
                with col_b:
                    st.markdown(f"**Severity:** {severity}")
                with col_c:
                    st.markdown(f"**Detected:** {date_str}")

                st.markdown("---")

                if change["diff_type"] == "html":
                    st.markdown("**What changed in the page content:**")
                    try:
                        detail = json.loads(change["diff_detail"])
                        diff_sample = detail.get("diff_sample", [])
                        if diff_sample:
                            added = [
                                l for l in diff_sample
                                if l.startswith("+") and not l.startswith("+++")
                            ]
                            removed = [
                                l for l in diff_sample
                                if l.startswith("-") and not l.startswith("---")
                            ]
                            if added:
                                st.markdown("🟢 **New content added:**")
                                for line in added[:5]:
                                    st.code(line[1:].strip(), language="html")
                            if removed:
                                st.markdown("🔴 **Content removed:**")
                                for line in removed[:5]:
                                    st.code(line[1:].strip(), language="html")
                        else:
                            st.info("Content changed but diff details not available.")
                    except Exception:
                        st.info("Change detected but details could not be parsed.")

                elif change["diff_type"] == "visual":
                    st.markdown("**What changed visually:**")
                    try:
                        detail = json.loads(change["diff_detail"])
                        ratio = detail.get("change_ratio", 0)
                        pixels = detail.get("changed_pixels", 0)
                        st.info(
                            f"🖼️ {pixels:,} pixels changed "
                            f"({ratio*100:.1f}% of the page)"
                        )
                    except Exception:
                        st.info("Visual change detected.")

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
                "SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 1",
                (url,)
            )
            page_changes = query_db(
                "SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC",
                (url,)
            )

            if not baseline:
                continue

            baseline = baseline[0]
            screenshot_path = baseline.get("screenshot_path")
            last_change = (
                page_changes[0]["timestamp"][:16] if page_changes else "—"
            )

            st.markdown(f"### 📄 {page_name}")
            st.caption(f"Change detected at: {last_change}")

            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**Latest screenshot:**")
                if screenshot_path and os.path.exists(screenshot_path):
                    st.image(screenshot_path, use_container_width=True)
                else:
                    st.info("Screenshot not available")

            with col_b:
                st.markdown("**What changed:**")
                for change in page_changes[:3]:
                    diff_label = friendly_diff_type(change["diff_type"])
                    st.markdown(f"**{diff_label}**")
                    try:
                        detail = json.loads(change["diff_detail"])
                        diff_sample = detail.get("diff_sample", [])
                        if diff_sample:
                            added = [
                                l for l in diff_sample
                                if l.startswith("+") and not l.startswith("+++")
                            ]
                            removed = [
                                l for l in diff_sample
                                if l.startswith("-") and not l.startswith("---")
                            ]
                            if added:
                                st.markdown("🟢 **Added:**")
                                for line in added[:3]:
                                    st.code(line[1:].strip(), language="html")
                            if removed:
                                st.markdown("🔴 **Removed:**")
                                for line in removed[:3]:
                                    st.code(line[1:].strip(), language="html")
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
                f"⚠️ {change_count} changes"
                if change_count > 0
                else "✅ No changes"
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