import streamlit as st
import sqlite3
import json
import os
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)

DB_PATH     = config["storage"]["db"]
ARCHIVE_DIR = config["storage"]["archive_dir"]

st.set_page_config(
    page_title="Portal Change Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",   # we don't use Streamlit sidebar at all
)

# ── GLOBAL CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── reset Streamlit chrome ── */
[data-testid="stToolbar"],
[data-testid="stHeader"],
[data-testid="stDecoration"],
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
#MainMenu,
footer { display: none !important; visibility: hidden !important; }

/* ── base ── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #0b0d14 !important;
    font-family: 'Inter', sans-serif;
}
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── top navbar ── */
.navbar {
    position: sticky; top: 0; z-index: 1000;
    background: #111320;
    border-bottom: 1px solid #1f2235;
    padding: 0 28px;
    display: flex; align-items: center; gap: 0;
    height: 56px;
}
.navbar-brand {
    font-size: 15px; font-weight: 700; color: #e2e8f0;
    letter-spacing: -.01em;
    display: flex; align-items: center; gap: 8px;
    margin-right: 36px; white-space: nowrap;
}
.navbar-brand .dot { width:8px;height:8px;border-radius:50%;background:#22d3ee;
    box-shadow:0 0 8px #22d3ee88; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.nav-link {
    font-size: 13px; font-weight: 500; color: #64748b;
    padding: 18px 14px; border-bottom: 2px solid transparent;
    cursor: pointer; white-space: nowrap; text-decoration: none;
    transition: color .15s, border-color .15s;
}
.nav-link:hover { color: #94a3b8; }
.nav-link.active { color: #e2e8f0; border-bottom-color: #22d3ee; }
.nav-spacer { flex: 1; }
.nav-portal-badge {
    background: #1a1f35; border: 1px solid #2a3050;
    color: #a78bfa; font-size: 12px; font-weight: 600;
    padding: 4px 12px; border-radius: 20px;
}
.nav-time {
    font-size: 11px; color: #374151; margin-left: 16px;
}

/* ── page wrapper ── */
.page { padding: 24px 32px 40px 32px; }

/* ── stat cards ── */
.stat-grid { display: grid; grid-template-columns: repeat(5,1fr); gap: 14px; margin-bottom: 28px; }
.stat-card {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 14px; padding: 20px 22px;
    position: relative; overflow: hidden;
    transition: transform .15s, border-color .2s;
}
.stat-card:hover { transform: translateY(-3px); border-color: #2a3050; }
.stat-card::before {
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background: var(--accent, #22d3ee);
    opacity: .7;
}
.stat-card .s-label {
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #374151; margin-bottom: 8px;
}
.stat-card .s-value {
    font-size: 32px; font-weight: 700;
    color: var(--accent, #e2e8f0); line-height: 1;
}

/* ── section title ── */
.sec-title {
    font-size: 11px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #374151;
    border-bottom: 1px solid #1a1f2e;
    padding-bottom: 10px; margin: 24px 0 16px;
}

/* ── portal row card ── */
.portal-row {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 12px; padding: 16px 20px;
    margin-bottom: 10px; display: flex; align-items: center; gap: 16px;
    transition: border-color .15s;
}
.portal-row:hover { border-color: #2a3050; }
.portal-row.alert { border-left: 3px solid #f87171; }
.portal-row.warn  { border-left: 3px solid #fbbf24; }
.portal-row.ok    { border-left: 3px solid #34d399; }
.pr-name { font-size: 14px; font-weight: 700; color: #e2e8f0; flex:1; }
.pr-meta { font-size: 12px; color: #4b5563; }
.pr-stat { text-align: right; }
.pr-stat .n { font-size: 22px; font-weight: 700; }
.pr-stat .l { font-size: 10px; color: #4b5563; text-transform: uppercase; letter-spacing:.05em; }

/* ── change row ── */
.chg-row {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 10px; padding: 14px 18px; margin-bottom: 8px;
    transition: border-color .15s;
}
.chg-row:hover { border-color: #2a3050; }
.chg-top { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.chg-name { font-size:14px; font-weight:600; color:#e2e8f0; flex:1; }
.chg-when { font-size:11px; color:#374151; }

/* ── badges ── */
.badge {
    font-size: 11px; font-weight: 600; padding: 3px 10px;
    border-radius: 20px; white-space: nowrap; display: inline-block;
}
.b-high   { background:#3d1a1a; color:#f87171; border:1px solid #5c2626; }
.b-medium { background:#3d2f0a; color:#fbbf24; border:1px solid #5c470f; }
.b-low    { background:#0d2b1a; color:#34d399; border:1px solid #155230; }
.b-type   { background:#0f1e3d; color:#60a5fa; border:1px solid #1e3a6e; }
.b-portal { background:#1a1a35; color:#a78bfa; border:1px solid #302865; }

/* ── crawl history row ── */
.crawl-row {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 10px; padding: 14px 20px; margin-bottom: 8px;
    display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
}
.cr-status { font-size:18px; }
.cr-portal { font-size:13px; font-weight:700; color:#e2e8f0; }
.cr-time   { font-size:12px; color:#4b5563; }
.cr-stat   { font-size:12px; }
.cr-stat b  { color:#e2e8f0; }
.cr-spacer { flex:1; }

/* ── filter bar ── */
.filter-bar {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 10px; padding: 14px 20px;
    margin-bottom: 20px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
}

/* ── diff detail box ── */
.diff-box {
    background: #0d0f1c; border: 1px solid #1a1f2e;
    border-radius: 8px; padding: 14px 16px; margin-top: 12px;
}
.diff-added   { color: #34d399; font-size:13px; margin: 3px 0; }
.diff-removed { color: #f87171; font-size:13px; margin: 3px 0; }
.diff-info    { color: #64748b; font-size:13px; font-style:italic; }

/* ── screenshot panel ── */
.ss-panel {
    background: #111320; border: 1px solid #1f2235;
    border-radius: 12px; padding: 16px; height: 100%;
}
.ss-label { font-size:12px; font-weight:600; color:#64748b; margin-bottom:10px; }

/* ── empty state ── */
.empty-state {
    text-align:center; padding:48px 24px;
    color: #374151; font-size:14px;
}
.empty-state .icon { font-size:36px; margin-bottom:12px; }

/* ── Streamlit widget overrides ── */
[data-testid="stExpander"] {
    background: #111320 !important;
    border: 1px solid #1f2235 !important;
    border-radius: 10px !important; margin-bottom:6px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * { color:#e2e8f0 !important; background:#111320 !important; }
[data-testid="stExpander"] svg { stroke:#e2e8f0 !important; fill:none !important; }
[data-testid="stExpander"] div,
[data-testid="stExpanderDetails"],
[data-testid="stExpanderDetails"] div { background:#111320 !important; }
[data-testid="stExpander"] p { color:#94a3b8 !important; }
[data-testid="stExpander"] span:not([data-testid="stMetricDelta"]) { color:#94a3b8 !important; }
[data-testid="stExpander"] strong, [data-testid="stExpander"] b { color:#e2e8f0 !important; }
[data-testid="stMetricValue"] { color:#e2e8f0 !important; }
[data-testid="stMetricLabel"] p { color:#64748b !important; }

hr { border-color:#1a1f2e !important; }
.stMarkdown p,.stMarkdown span,.stMarkdown li { color:#94a3b8 !important; }
.stCaption,[data-testid="stCaptionContainer"] { color:#4b5563 !important; }
code { background:#0f1929 !important; color:#60a5fa !important; border-radius:4px; }

[data-testid="stSelectbox"]>div>div {
    background:#111320 !important; border:1px solid #1f2235 !important;
    color:#e2e8f0 !important; border-radius:8px !important;
}
[data-testid="stSelectbox"] svg { fill:#4b5563 !important; }
[data-testid="stSelectbox"] span { color:#e2e8f0 !important; }
[data-baseweb="popover"],[data-baseweb="menu"],
ul[data-testid="stSelectboxVirtualDropdown"],
div[data-baseweb="popover"]>div {
    background:#111320 !important; border:1px solid #1f2235 !important; border-radius:10px !important;
}
[data-baseweb="menu"] li,[data-baseweb="option"],[role="option"] {
    background:#111320 !important; color:#94a3b8 !important; font-size:13px !important;
}
[data-baseweb="option"]:hover,[role="option"]:hover,
[aria-selected="true"][role="option"] { background:#1a1f35 !important; color:#60a5fa !important; }

[data-testid="stTextInput"] input {
    background:#111320 !important; border:1px solid #1f2235 !important;
    color:#e2e8f0 !important; border-radius:8px !important;
}
[data-testid="stTextInput"] input::placeholder { color:#374151 !important; }
[data-testid="stRadio"] label { color:#94a3b8 !important; }

button[data-testid^="baseButton"] {
    background:#1a1f35 !important; border:1px solid #2a3050 !important;
    color:#e2e8f0 !important; border-radius:8px !important;
    transition: background .15s !important;
}
button[data-testid^="baseButton"]:hover { background:#252b45 !important; }

/* remove top padding Streamlit adds */
.stApp > div:first-child { padding-top: 0 !important; }
div[data-testid="stVerticalBlock"] > div:first-child { padding-top: 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS crawl_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            portal         TEXT    NOT NULL,
            started_at     TEXT    NOT NULL,
            finished_at    TEXT,
            pages_visited  INTEGER DEFAULT 0,
            status         TEXT    DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS changes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            portal      TEXT NOT NULL,
            url         TEXT NOT NULL,
            diff_type   TEXT NOT NULL,
            diff_detail TEXT,
            timestamp   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS baselines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            portal          TEXT NOT NULL,
            url             TEXT NOT NULL,
            html_path       TEXT,
            screenshot_path TEXT,
            har_path        TEXT,
            updated_at      TEXT NOT NULL,
            UNIQUE(portal, url)
        );
    """)
    conn.commit()
    conn.close()

init_db()


def query_db(query, args=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, args)
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        st.error(f"Database error: {e}")
        return []


def time_ago(ts):
    try:
        diff = datetime.now() - datetime.fromisoformat(ts)
        s = int(diff.total_seconds())
        if s < 60:    return "just now"
        if s < 3600:  return f"{s // 60}m ago"
        if s < 86400: return f"{s // 3600}h ago"
        return f"{diff.days}d ago"
    except Exception:
        return ts


def friendly_page_name(url):
    try:
        return url.split("___")[-1].replace("_", " ").title()
    except Exception:
        return url


DIFF_LABELS = {
    "html":   ("📄", "Content"),
    "visual": ("🖼️", "Visual"),
    "json":   ("📊", "Data"),
    "har":    ("🔌", "API"),
}

def severity_badge(diff_lines):
    if diff_lines > 50: return "High",   "b-high"
    if diff_lines > 10: return "Medium", "b-medium"
    return "Low", "b-low"


# ── DB QUERIES ────────────────────────────────────────────────────────────────

def get_all_portals():
    rows = query_db("SELECT DISTINCT portal FROM crawl_log ORDER BY portal")
    return [r["portal"] for r in rows]


def get_portal_stats(portal=None):
    and_clause = "AND cl.portal = ?" if portal else ""
    args = (portal,) if portal else ()
    return query_db(f"""
        SELECT
            cl.portal,
            cl.started_at      AS last_crawl_at,
            cl.pages_visited,
            cl.status          AS last_status,
            COALESCE(td.today_changes, 0)   AS today_changes,
            COALESCE(at_.all_changes, 0)    AS all_time_changes
        FROM crawl_log cl
        LEFT JOIN (
            SELECT portal, COUNT(*) AS today_changes
            FROM   changes
            WHERE  date(timestamp) = date('now')
            GROUP BY portal
        ) td ON td.portal = cl.portal
        LEFT JOIN (
            SELECT portal, COUNT(*) AS all_changes
            FROM   changes
            GROUP BY portal
        ) at_ ON at_.portal = cl.portal
        WHERE cl.id IN (
            SELECT MAX(id) FROM crawl_log GROUP BY portal
        )
        {and_clause}
        ORDER BY cl.portal
    """, args)


def get_latest_crawl_changes(portal=None):
    if portal and portal != "All Portals":
        row = query_db(
            "SELECT id, started_at, finished_at FROM crawl_log "
            "WHERE portal=? AND status='done' ORDER BY started_at DESC LIMIT 1",
            (portal,),
        )
    else:
        row = query_db(
            "SELECT id, started_at, finished_at FROM crawl_log "
            "WHERE status='done' ORDER BY started_at DESC LIMIT 1",
        )
    if not row:
        return []
    s = row[0]["started_at"]
    f = row[0]["finished_at"] or datetime.now().isoformat()
    if portal and portal != "All Portals":
        return query_db(
            "SELECT * FROM changes WHERE portal=? AND timestamp>=? AND timestamp<=? "
            "ORDER BY timestamp DESC",
            (portal, s, f),
        )
    return query_db(
        "SELECT * FROM changes WHERE timestamp>=? AND timestamp<=? ORDER BY timestamp DESC",
        (s, f),
    )


def get_crawl_history(portal=None, limit=50):
    if portal and portal != "All Portals":
        return query_db(
            "SELECT * FROM crawl_log WHERE portal=? ORDER BY started_at DESC LIMIT ?",
            (portal, limit),
        )
    return query_db(
        "SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )


# ── RENDER HELPERS ────────────────────────────────────────────────────────────

def render_html_change(detail):
    summary       = detail.get("summary", "")
    added_texts   = detail.get("added_texts", [])
    removed_texts = detail.get("removed_texts", [])

    if added_texts or removed_texts:
        if summary:
            st.info(f"💬 {summary}")
        if added_texts:
            st.markdown("🟢 **Added:**")
            for item in added_texts[:5]:
                st.markdown(f"&nbsp;&nbsp;• {item}")
        if removed_texts:
            st.markdown("🔴 **Removed:**")
            for item in removed_texts[:5]:
                st.markdown(f"&nbsp;&nbsp;• {item}")
        return

    diff_sample = detail.get("diff_sample", [])
    if not diff_sample:
        st.info("Content changed but diff details not available.")
        return

    added_html   = [l[1:].strip() for l in diff_sample if l.startswith("+") and not l.startswith("+++")]
    removed_html = [l[1:].strip() for l in diff_sample if l.startswith("-") and not l.startswith("---")]

    from bs4 import BeautifulSoup
    import re

    def to_readable(lines):
        readable = []
        for raw in lines:
            if re.search(r"echarts|_ngcontent|_nghost|ng-reflect", raw, re.I):
                continue
            try:
                soup = BeautifulSoup(raw, "html.parser")
                for tag in soup.find_all(["button","a","label","span","h1","h2","h3","h4","p","td","li"]):
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
        return list(dict.fromkeys(readable))

    readable_added   = to_readable(added_html)
    readable_removed = to_readable(removed_html)

    lines_html = ""
    if readable_added:
        lines_html += "<div style='font-size:13px;font-weight:600;color:#34d399;margin-bottom:4px'>🟢 Added</div>"
        for item in readable_added[:5]:
            lines_html += f"<div class='diff-added'>+ {item}</div>"
    if readable_removed:
        lines_html += "<div style='font-size:13px;font-weight:600;color:#f87171;margin:10px 0 4px'>🔴 Removed</div>"
        for item in readable_removed[:5]:
            lines_html += f"<div class='diff-removed'>- {item}</div>"
    if lines_html:
        st.markdown(f"<div class='diff-box'>{lines_html}</div>", unsafe_allow_html=True)
    elif not readable_added and not readable_removed:
        for line in added_html[:3]:
            st.code(line, language="html")


def render_change_expander(change):
    page_name = friendly_page_name(change["url"])
    when      = time_ago(change["timestamp"])
    date_str  = change["timestamp"][:16]

    try:
        detail     = json.loads(change["diff_detail"])
        diff_lines = detail.get("diff_lines", 0)
        sev_label, sev_cls = severity_badge(diff_lines)
        summary    = detail.get("summary", "")
    except Exception:
        detail = {}; sev_label = "Low"; sev_cls = "b-low"; summary = ""

    icon, type_label = DIFF_LABELS.get(change["diff_type"], ("❓", "?"))

    with st.expander(
        f"{icon} **[{change['portal']}]** {page_name} — {type_label} — {when}",
        expanded=False,
    ):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"**Portal:** `{change['portal']}`")
            st.markdown(f"**Page:** {page_name}")
        with mc2:
            st.markdown(f"**Severity:** {sev_label}")
            st.markdown(f"**Type:** {type_label}")
        with mc3:
            st.markdown(f"**Detected:** {date_str}")
            st.markdown(f"**URL:** `{change['url'].split('___')[0]}`")

        if summary:
            st.info(f"💬 {summary}")
        st.markdown("---")
        st.markdown("**What changed:**")

        if change["diff_type"] == "html":
            render_html_change(detail)
        elif change["diff_type"] == "visual":
            ratio  = detail.get("change_ratio", 0)
            pixels = detail.get("changed_pixels", 0)
            st.info(f"🖼️ {pixels:,} pixels changed ({ratio*100:.1f}% of the page)")
        elif change["diff_type"] == "har":
            new_ep     = detail.get("new_endpoints", [])
            removed_ep = detail.get("removed_endpoints", [])
            if new_ep:
                st.markdown(f"🟢 **{len(new_ep)} new endpoint(s)**")
                for ep in new_ep[:3]: st.code(ep)
            if removed_ep:
                st.markdown(f"🔴 **{len(removed_ep)} removed endpoint(s)**")
                for ep in removed_ep[:3]: st.code(ep)


# ── DATA FETCH ────────────────────────────────────────────────────────────────

all_portals      = get_all_portals()
portal_options   = ["All Portals"] + all_portals
total_crawls     = (query_db("SELECT COUNT(*) as count FROM crawl_log") or [{"count":0}])[0]["count"]
all_time_changes = (query_db("SELECT COUNT(*) as count FROM changes")   or [{"count":0}])[0]["count"]
last_crawl_row   = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 1")
lc               = last_crawl_row[0] if last_crawl_row else {}


# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "view" not in st.session_state:
    st.session_state.view = "overview"
if "portal" not in st.session_state:
    st.session_state.portal = "All Portals"


# ── NAV DATA ──────────────────────────────────────────────────────────────────
portal_filter      = None if st.session_state.portal == "All Portals" else st.session_state.portal
latest_changes_nav = get_latest_crawl_changes(portal_filter)
nav_chg_count      = len(latest_changes_nav)
last_crawl_str     = time_ago(lc.get("started_at","")) if lc else "never"
active             = st.session_state.view

# ── TOP NAVBAR (brand only — no clickable links) ───────────────────────────────
st.markdown(f"""
<div class="navbar">
  <div class="navbar-brand">
    <div class="dot"></div>
    🔍 Change Monitor
  </div>
  <div class="nav-spacer"></div>
  <span style="font-size:11px;color:#374151;margin-right:16px">
    Last crawl: <b style="color:#64748b">{last_crawl_str}</b>
  </span>
  <span class="nav-portal-badge">{st.session_state.portal}</span>
</div>
""", unsafe_allow_html=True)

# ── NAV TAB BUTTONS ────────────────────────────────────────────────────────────
# Pure st.button — no href, no page reload, same tab always
st.markdown("""
<style>
/* Tab button row */
div[data-testid="stHorizontalBlock"]:has(button[key="nav_overview"]) {
    background: #0e1019;
    border-bottom: 1px solid #1a1f2e;
    padding: 0 24px !important;
    gap: 0 !important;
    margin-bottom: 0 !important;
}
/* All nav buttons default */
button[key^="nav_"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    color: #4b5563 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 12px 4px !important;
    transition: color .15s !important;
    box-shadow: none !important;
}
button[key^="nav_"]:hover {
    color: #94a3b8 !important;
    background: transparent !important;
    border-bottom: 2px solid #374151 !important;
}
/* Active nav button */
button[key="nav_ACTIVE_KEY"] {
    color: #e2e8f0 !important;
    border-bottom: 2px solid #22d3ee !important;
}
</style>
""".replace("ACTIVE_KEY", active), unsafe_allow_html=True)

_nav_items = [
    ("overview", "🏠 Overview"),
    ("changes",  f"🚨 Changes{' (' + str(nav_chg_count) + ')' if nav_chg_count > 0 else ''}"),
    ("pages",    "📸 Pages"),
    ("history",  "📅 History"),
]

_nb1, _nb2, _nb3, _nb4, _nb_space, _nb_portal, _nb_refresh = st.columns([1.3, 1.5, 1, 1.2, 2.5, 2, 0.7])
for _col, (_vkey, _vlabel) in zip([_nb1, _nb2, _nb3, _nb4], _nav_items):
    with _col:
        if st.button(_vlabel, key=f"nav_{_vkey}", use_container_width=True):
            st.session_state.view = _vkey
            st.rerun()

with _nb_portal:
    _sel_portal = st.selectbox(
        "Portal", portal_options,
        index=portal_options.index(st.session_state.portal)
              if st.session_state.portal in portal_options else 0,
        key="portal_select",
        label_visibility="collapsed",
    )
    if _sel_portal != st.session_state.portal:
        st.session_state.portal = _sel_portal
        st.rerun()

with _nb_refresh:
    if st.button("🔄", key="refresh_btn", use_container_width=True, help="Refresh"):
        st.rerun()

# re-derive portal_filter after possible change
portal_filter = None if st.session_state.portal == "All Portals" else st.session_state.portal



# ── quick stat strip ──────────────────────────────────────────────────────────
latest_changes_nav = get_latest_crawl_changes(portal_filter)
nav_chg_count      = len(latest_changes_nav)

if st.session_state.portal != "All Portals":
    scoped_all    = query_db("SELECT COUNT(*) as count FROM changes WHERE portal=?", (st.session_state.portal,))[0]["count"]
    scoped_crawls = query_db("SELECT COUNT(*) as count FROM crawl_log WHERE portal=?", (st.session_state.portal,))[0]["count"]
else:
    scoped_all    = all_time_changes
    scoped_crawls = total_crawls

chg_color = "#f87171" if nav_chg_count > 0 else "#34d399"
strip_html = f"""
<div style="display:flex;gap:12px;margin:14px 0 4px;flex-wrap:wrap">
  <div style="background:#111320;border:1px solid #1f2235;border-radius:10px;padding:10px 20px;display:flex;align-items:center;gap:12px">
    <span style="font-size:10px;color:#374151;text-transform:uppercase;letter-spacing:.08em">Scope</span>
    <span style="font-size:13px;font-weight:700;color:#a78bfa">{st.session_state.portal}</span>
  </div>
  <div style="background:#111320;border:1px solid #1f2235;border-radius:10px;padding:10px 20px;display:flex;align-items:center;gap:12px">
    <span style="font-size:10px;color:#374151;text-transform:uppercase;letter-spacing:.08em">Latest crawl changes</span>
    <span style="font-size:20px;font-weight:700;color:{chg_color}">{nav_chg_count}</span>
  </div>
  <div style="background:#111320;border:1px solid #1f2235;border-radius:10px;padding:10px 20px;display:flex;align-items:center;gap:12px">
    <span style="font-size:10px;color:#374151;text-transform:uppercase;letter-spacing:.08em">All-time changes</span>
    <span style="font-size:20px;font-weight:700;color:#60a5fa">{scoped_all}</span>
  </div>
  <div style="background:#111320;border:1px solid #1f2235;border-radius:10px;padding:10px 20px;display:flex;align-items:center;gap:12px">
    <span style="font-size:10px;color:#374151;text-transform:uppercase;letter-spacing:.08em">Total crawls</span>
    <span style="font-size:20px;font-weight:700;color:#a78bfa">{scoped_crawls}</span>
  </div>
  {"" if not lc else f'''
  <div style="background:#111320;border:1px solid #1f2235;border-radius:10px;padding:10px 20px;display:flex;align-items:center;gap:12px">
    <span style="font-size:10px;color:#374151;text-transform:uppercase;letter-spacing:.08em">Last crawl</span>
    <span style="font-size:13px;font-weight:600;color:{'#34d399' if lc.get('status')=='done' else '#f87171'}">
      {'✅ Done' if lc.get('status')=='done' else '❌ Failed'} &nbsp;·&nbsp; {last_crawl_str}
    </span>
  </div>
  '''}
</div>
"""
st.markdown(strip_html, unsafe_allow_html=True)
st.markdown("<hr style='margin:16px 0'>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW 1 — Portal Overview
# ════════════════════════════════════════════════════════════════════════════════
if st.session_state.view == "overview":

    st.markdown("<h2 style='color:#e2e8f0;margin:0 0 4px'>🏠 Portal Overview</h2>", unsafe_allow_html=True)
    st.caption("Health summary for every monitored portal.")

    portal_stats = get_portal_stats(portal_filter)

    total_portals   = len(portal_stats)
    portals_alert   = sum(1 for p in portal_stats if p["today_changes"] > 3)
    portals_warn    = sum(1 for p in portal_stats if 0 < p["today_changes"] <= 3)
    portals_ok      = sum(1 for p in portal_stats if p["today_changes"] == 0)
    total_today_chg = sum(p["today_changes"] for p in portal_stats)

    cards_html = f"""
    <div class="stat-grid" style="margin-top:20px">
      <div class="stat-card" style="--accent:#60a5fa">
        <div class="s-label">Portals</div>
        <div class="s-value">{total_portals}</div>
      </div>
      <div class="stat-card" style="--accent:{'#f87171' if total_today_chg else '#34d399'}">
        <div class="s-label">Changes Today</div>
        <div class="s-value">{total_today_chg}</div>
      </div>
      <div class="stat-card" style="--accent:#f87171">
        <div class="s-label">🔴 Alert</div>
        <div class="s-value">{portals_alert}</div>
      </div>
      <div class="stat-card" style="--accent:#fbbf24">
        <div class="s-label">🟡 Warning</div>
        <div class="s-value">{portals_warn}</div>
      </div>
      <div class="stat-card" style="--accent:#34d399">
        <div class="s-label">🟢 Clean</div>
        <div class="s-value">{portals_ok}</div>
      </div>
    </div>
    """
    st.markdown(cards_html, unsafe_allow_html=True)

    st.markdown("<div class='sec-title'>Per-portal status</div>", unsafe_allow_html=True)

    if not portal_stats:
        st.markdown("<div class='empty-state'><div class='icon'>🕳️</div>No portals have been crawled yet.</div>",
                    unsafe_allow_html=True)
    else:
        for p in portal_stats:
            chg    = p["today_changes"]
            status = "alert" if chg > 3 else ("warn" if chg > 0 else "ok")
            dot    = "🔴" if status == "alert" else ("🟡" if status == "warn" else "🟢")
            lc_time = time_ago(p["last_crawl_at"]) if p["last_crawl_at"] else "never"
            last_status = p["last_status"] or "unknown"
            pages_val   = str(p["pages_visited"]) if p["pages_visited"] else "—"

            stale = False
            if last_status == "running" and p["last_crawl_at"]:
                try:
                    from datetime import timedelta
                    elapsed = datetime.now() - datetime.fromisoformat(p["last_crawl_at"])
                    stale = elapsed > timedelta(minutes=30)
                except Exception:
                    pass

            display_status = (
                "❌ crashed" if stale else
                "🔄 running" if last_status == "running" else
                "✅ done"    if last_status == "done" else last_status
            )

            with st.expander(
                f"{dot} **{p['portal']}** — "
                f"{'⚠️ ' + str(chg) + ' change(s) today' if chg else '✅ Clean today'} — "
                f"Last crawl: {lc_time}",
                expanded=(status != "ok"),
            ):
                pc1, pc2, pc3, pc4 = st.columns(4)
                pc1.metric("Today's changes",  p["today_changes"])
                pc2.metric("All-time changes", p["all_time_changes"])
                pc3.metric("Pages (last run)", pages_val)
                pc4.metric("Last status",      display_status)

                if last_status == "running" and not stale:
                    st.warning("🔄 Crawl is currently in progress — refresh in a moment.")
                elif stale:
                    st.error("❌ Last crawl appears to have crashed. Check crawler logs and restart.")

                st.caption(f"Last crawl: {p['last_crawl_at'][:16] if p['last_crawl_at'] else 'never'}")

                if chg > 0:
                    st.markdown("---")
                    st.markdown("**Latest changes for this portal:**")
                    portal_changes = query_db(
                        "SELECT * FROM changes WHERE portal=? "
                        "AND date(timestamp)=date('now') ORDER BY timestamp DESC LIMIT 5",
                        (p["portal"],),
                    )
                    for ch in portal_changes:
                        icon, label = DIFF_LABELS.get(ch["diff_type"], ("❓", "?"))
                        st.markdown(
                            f"&nbsp;&nbsp;{icon} `{friendly_page_name(ch['url'])}` "
                            f"— {label} — {time_ago(ch['timestamp'])}"
                        )


# ════════════════════════════════════════════════════════════════════════════════
# VIEW 2 — Latest Changes
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "changes":

    st.markdown("<h2 style='color:#e2e8f0;margin:0 0 4px'>🚨 Latest Changes</h2>", unsafe_allow_html=True)
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.caption(f"Scope: {scope}  ·  Changes from the most recent crawl run")

    latest_changes = get_latest_crawl_changes(portal_filter)

    fcol1, fcol2, fcol3, fcol4 = st.columns([2, 2, 2, 3])
    with fcol1:
        filter_type = st.selectbox("Type",
            ["All Types","📄 Content","🖼️ Visual","📊 Data","🔌 API"], key="filter_type")
    with fcol2:
        filter_severity = st.selectbox("Severity",
            ["All Severities","🔴 High","🟡 Medium","🟢 Low"], key="filter_sev")
    with fcol3:
        if not portal_filter:
            filter_portal_local = st.selectbox("Portal",
                ["All Portals"] + all_portals, key="filter_portal_local")
        else:
            filter_portal_local = st.session_state.portal
            st.caption(f"Portal: {st.session_state.portal}")
    with fcol4:
        search_q = st.text_input("🔍 Search page name", placeholder="e.g. Dashboard…", key="search_q")

    st.markdown("<hr style='margin:12px 0'>", unsafe_allow_html=True)

    if not latest_changes:
        st.markdown("<div class='empty-state'><div class='icon'>✅</div>No changes detected in the latest crawl.</div>",
                    unsafe_allow_html=True)
    else:
        type_map = {"📄 Content":"html","🖼️ Visual":"visual","📊 Data":"json","🔌 API":"har"}
        filtered = latest_changes

        if filter_type != "All Types":
            dt = type_map.get(filter_type)
            filtered = [c for c in filtered if c["diff_type"] == dt]

        if filter_severity != "All Severities":
            sev_label = filter_severity.split(" ", 1)[1]
            def sev_of(c):
                try:
                    d = json.loads(c["diff_detail"])
                    s, _ = severity_badge(d.get("diff_lines", 0))
                    return s
                except Exception:
                    return "Low"
            filtered = [c for c in filtered if sev_of(c) == sev_label]

        if filter_portal_local != "All Portals":
            filtered = [c for c in filtered if c["portal"] == filter_portal_local]

        if search_q:
            filtered = [c for c in filtered
                        if search_q.lower() in friendly_page_name(c["url"]).lower()]

        st.markdown(
            f"<div style='font-size:13px;color:#374151;margin-bottom:12px'>"
            f"Showing <b style='color:#e2e8f0'>{len(filtered)}</b> of {len(latest_changes)} change(s)</div>",
            unsafe_allow_html=True,
        )

        for change in filtered:
            render_change_expander(change)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW 3 — Changed Pages
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "pages":

    st.markdown("<h2 style='color:#e2e8f0;margin:0 0 4px'>📸 Changed Pages</h2>", unsafe_allow_html=True)
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.caption(f"Scope: {scope}  ·  Side-by-side screenshots of pages where changes were detected.")

    latest_changes = get_latest_crawl_changes(portal_filter)

    if not latest_changes:
        st.markdown("<div class='empty-state'><div class='icon'>📷</div>No changed pages in the latest crawl.</div>",
                    unsafe_allow_html=True)
    else:
        changed_urls = list({c["url"] for c in latest_changes})

        def url_label(url):
            chg = next((c for c in latest_changes if c["url"] == url), {})
            p   = chg.get("portal", "")
            return f"[{p}] {friendly_page_name(url)}" if p else friendly_page_name(url)

        page_labels    = [url_label(u) for u in changed_urls]
        selected_label = st.selectbox(
            f"Select page to inspect ({len(changed_urls)} changed)", page_labels)
        selected_url = changed_urls[page_labels.index(selected_label)]

        st.markdown("<hr style='margin:12px 0'>", unsafe_allow_html=True)

        baseline = query_db(
            "SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2",
            (selected_url,),
        )
        page_changes = query_db(
            "SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC",
            (selected_url,),
        )

        latest_b   = baseline[0] if len(baseline) > 0 else None
        prev_b     = baseline[1] if len(baseline) > 1 else None
        last_chg   = page_changes[0]["timestamp"][:16] if page_changes else "—"
        chg_portal = page_changes[0]["portal"] if page_changes else "—"

        st.markdown(
            f"<h3 style='color:#e2e8f0'>📄 {friendly_page_name(selected_url)}"
            f"&nbsp;<span style='font-size:13px;color:#a78bfa'>[{chg_portal}]</span></h3>",
            unsafe_allow_html=True,
        )
        st.caption(f"Change detected at: {last_chg}")

        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("<div class='ss-panel'>", unsafe_allow_html=True)
            st.markdown("**⬅️ Previous snapshot**")
            if prev_b:
                prev_ss = prev_b.get("screenshot_path")
                if prev_ss and os.path.exists(prev_ss):
                    st.image(prev_ss, use_container_width=True)
                else:
                    st.info("Previous screenshot not available")
            else:
                st.info("No previous snapshot")
            st.markdown("</div>", unsafe_allow_html=True)

        with sc2:
            st.markdown("<div class='ss-panel'>", unsafe_allow_html=True)
            st.markdown("**➡️ Latest snapshot**")
            if latest_b:
                latest_ss = latest_b.get("screenshot_path")
                if latest_ss and os.path.exists(latest_ss):
                    st.image(latest_ss, use_container_width=True)
                else:
                    st.info("Latest screenshot not available")
            else:
                st.info("No latest snapshot")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**What changed:**")
        for change in page_changes[:3]:
            icon, label = DIFF_LABELS.get(change["diff_type"], ("❓", "?"))
            with st.expander(f"{icon} {label} change", expanded=True):
                try:
                    detail = json.loads(change["diff_detail"])
                    if change["diff_type"] == "html":
                        render_html_change(detail)
                    elif change["diff_type"] == "visual":
                        ratio = detail.get("change_ratio", 0)
                        st.info(f"Page appearance changed by {ratio*100:.1f}%")
                except Exception:
                    st.info("Change detected but details unavailable.")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW 4 — Crawl History
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "history":

    st.markdown("<h2 style='color:#e2e8f0;margin:0 0 4px'>📅 Crawl History</h2>", unsafe_allow_html=True)
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.caption(f"Scope: {scope}  ·  Every crawl run — pages visited and changes found.")

    hcol1, _ = st.columns([2, 4])
    with hcol1:
        history_filter = st.selectbox(
            "Filter", ["All Crawls","✅ With Changes","🟢 No Changes"], key="hist_filter")

    crawl_logs = get_crawl_history(portal_filter)

    if not crawl_logs:
        st.markdown("<div class='empty-state'><div class='icon'>📋</div>No crawls recorded yet.</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown("<hr style='margin:12px 0'>", unsafe_allow_html=True)

        for log in crawl_logs:
            crawl_changes = query_db(
                "SELECT COUNT(*) as count FROM changes "
                "WHERE portal=? AND timestamp>=? AND timestamp<=?",
                (log["portal"], log["started_at"],
                 log["finished_at"] or datetime.now().isoformat()),
            )
            count = crawl_changes[0]["count"] if crawl_changes else 0

            if history_filter == "✅ With Changes" and count == 0: continue
            if history_filter == "🟢 No Changes"  and count > 0:  continue

            started  = log["started_at"][:16]
            finished = log["finished_at"][:16] if log["finished_at"] else "—"
            done     = log["status"] == "done"

            with st.expander(
                f"{'✅' if done else '❌'} [{log['portal']}]  {started}  |  "
                f"{'⚠️ ' + str(count) + ' change(s)' if count > 0 else '🟢 No changes'}  |  "
                f"{log['pages_visited']} pages",
                expanded=False,
            ):
                dc1, dc2, dc3, dc4 = st.columns(4)
                dc1.metric("Pages scanned", log["pages_visited"])
                dc2.metric("Changes found", count)
                dc3.markdown(f"**Started:** {started}")
                dc4.markdown(f"**Finished:** {finished}")
                st.markdown(f"**Portal:** `{log['portal']}`")

                if count > 0:
                    st.markdown("---")
                    st.markdown("**Pages that changed:**")
                    crawl_changed_pages = query_db(
                        "SELECT DISTINCT url, diff_type FROM changes "
                        "WHERE portal=? AND timestamp>=? AND timestamp<=?",
                        (log["portal"], log["started_at"],
                         log["finished_at"] or datetime.now().isoformat()),
                    )
                    for p in crawl_changed_pages[:10]:
                        icon, label = DIFF_LABELS.get(p["diff_type"], ("❓", "?"))
                        st.markdown(
                            f"&nbsp;&nbsp;{icon} `{friendly_page_name(p['url'])}` — {label} change"
                        )

# ── close page div + footer ───────────────────────────────────────────────────
st.markdown("</div>", unsafe_allow_html=True)
st.markdown("---")
st.caption(
    f"Auto-monitoring active · "
    f"Scope: {st.session_state.portal} · "
    f"Last refreshed: {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
)