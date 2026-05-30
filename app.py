import streamlit as st
import sqlite3
import json
import os
import subprocess
import sys
import time
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
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; }
[data-testid="stToolbar"], [data-testid="stHeader"], #MainMenu, header,
[data-testid="stDecoration"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"],
button[aria-label="Close sidebar"], button[aria-label="Collapse sidebar"]
{ display:none!important; visibility:hidden!important; width:0!important; height:0!important }

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'IBM Plex Sans', sans-serif !important;
    background: #080b10 !important;
}
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── NAVBAR ── */
.navbar {
    position: sticky;
    top: 0;
    z-index: 9999;
    background: #0c0f16;
    border-bottom: 1px solid #1a1f2e;
    padding: 0 28px;
    display: flex;
    align-items: center;
    height: 52px;
    gap: 0;
}
.navbar-brand {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 8px;
    padding-right: 24px;
    border-right: 1px solid #1a1f2e;
    letter-spacing: 0.02em;
}
.navbar-brand .dot { color: #3b82f6; }
.navbar-tabs {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 0 16px;
    flex: 1;
}
.nav-tab {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 12.5px;
    font-weight: 500;
    color: #64748b;
    padding: 5px 12px;
    border-radius: 6px;
    cursor: pointer;
    border: none;
    background: transparent;
    transition: all 0.15s ease;
    white-space: nowrap;
    letter-spacing: 0.01em;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    text-decoration: none;
}
.nav-tab:hover { background: #131929; color: #94a3b8; }
.nav-tab.active {
    background: #131929;
    color: #e2e8f0;
    border: 1px solid #1e2d47;
}
.nav-tab .tab-icon { font-size: 13px; }
.navbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
}

/* ── Streamlit button overrides ── */
[data-testid="stButton"] button {
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 5px 12px !important;
    height: 32px !important;
    border-radius: 6px !important;
    white-space: nowrap !important;
    line-height: 1 !important;
    letter-spacing: 0.02em !important;
    min-width: 0 !important;
}
/* Primary (active tab / run crawl) */
[data-testid="stButton"] button[kind="primary"] {
    background: #1d4ed8 !important;
    border: 1px solid #2563eb !important;
    color: #fff !important;
}
[data-testid="stButton"] button[kind="primary"]:hover {
    background: #2563eb !important;
}
/* Secondary */
[data-testid="stButton"] button[kind="secondary"] {
    background: #0f1623 !important;
    border: 1px solid #1e2d47 !important;
    color: #94a3b8 !important;
}
[data-testid="stButton"] button[kind="secondary"]:hover {
    background: #131929 !important;
    color: #e2e8f0 !important;
    border-color: #2a3a5c !important;
}

/* ── Page content wrapper ── */
.page-content {
    padding: 28px 32px 40px 32px;
    max-width: 1360px;
    margin: 0 auto;
}

/* ── Stat cards ── */
.stats-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 28px;
}
.stat-card {
    background: #0c0f16;
    border: 1px solid #1a1f2e;
    border-radius: 10px;
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
}
.stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--accent, #3b82f6);
    opacity: 0.6;
}
.stat-card .s-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #3d4f6b;
    margin-bottom: 8px;
}
.stat-card .s-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 32px;
    font-weight: 600;
    color: var(--accent, #e2e8f0);
    line-height: 1;
}

/* ── Section header ── */
.section-hdr {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #2d3a52;
    border-bottom: 1px solid #131929;
    padding-bottom: 8px;
    margin: 24px 0 16px 0;
}

/* ── Page title ── */
.page-title {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 22px;
    font-weight: 700;
    color: #e2e8f0;
    margin: 0 0 4px 0;
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 10px;
}
.page-subtitle {
    font-size: 13px;
    color: #3d4f6b;
    margin-bottom: 24px;
    font-weight: 400;
}

/* ── Expander dark ── */
[data-testid="stExpander"] {
    background: #0c0f16 !important;
    border: 1px solid #1a1f2e !important;
    border-radius: 8px !important;
    margin-bottom: 6px !important;
}
[data-testid="stExpander"] summary {
    background: #0c0f16 !important;
    color: #c8d6e8 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
[data-testid="stExpander"] summary * { color: #c8d6e8 !important; }
[data-testid="stExpander"] svg { stroke: #3d4f6b !important; }
[data-testid="stExpander"] div,
[data-testid="stExpander"] section,
[data-testid="stExpanderDetails"],
[data-testid="stExpanderDetails"] div { background: #0c0f16 !important; }
[data-testid="stExpander"] p { color: #8899b4 !important; }
[data-testid="stExpander"] strong,
[data-testid="stExpander"] b { color: #c8d6e8 !important; }

/* ── General text ── */
.main h1, .main h2, .main h3, .main h4 {
    color: #e2e8f0 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
.stMarkdown p, .stMarkdown span, .stMarkdown li { color: #8899b4 !important; }
.stCaption, [data-testid="stCaptionContainer"] { color: #3d4f6b !important; }
code {
    background: #0f1623 !important;
    color: #60a5fa !important;
    border-radius: 4px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11.5px !important;
}
hr { border-color: #1a1f2e !important; }

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    background: #0c0f16 !important;
    border: 1px solid #1a1f2e !important;
    color: #c8d6e8 !important;
    border-radius: 7px !important;
    font-size: 12.5px !important;
    height: 32px !important;
    min-height: 32px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
[data-testid="stSelectbox"] span { color: #c8d6e8 !important; }
[data-testid="stSelectbox"] svg { fill: #3d4f6b !important; }
[data-baseweb="popover"], [data-baseweb="menu"], [data-baseweb="select"] ul {
    background: #0c0f16 !important;
    border: 1px solid #1a1f2e !important;
    border-radius: 8px !important;
}
[data-baseweb="menu"] li, [data-baseweb="option"], [role="option"] {
    background: #0c0f16 !important;
    color: #8899b4 !important;
    font-size: 12.5px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
[data-baseweb="option"]:hover, [role="option"]:hover, [aria-selected="true"][role="option"] {
    background: #0f1623 !important;
    color: #60a5fa !important;
}

/* ── Text input ── */
[data-testid="stTextInput"] input {
    background: #0c0f16 !important;
    border: 1px solid #1a1f2e !important;
    color: #c8d6e8 !important;
    border-radius: 7px !important;
    font-size: 12.5px !important;
    height: 32px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
[data-testid="stTextInput"] input::placeholder { color: #2d3a52 !important; }

/* ── Metric ── */
[data-testid="stMetricValue"] {
    color: #e2e8f0 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 22px !important;
}
[data-testid="stMetricLabel"] p { color: #3d4f6b !important; font-size: 11px !important; }

/* ── Badges ── */
.badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10.5px;
    font-weight: 600;
    padding: 3px 9px;
    border-radius: 4px;
    white-space: nowrap;
    letter-spacing: 0.04em;
}
.badge-high   { background:#1f0f0f; color:#f87171; border:1px solid #3d1a1a; }
.badge-medium { background:#1a150a; color:#fbbf24; border:1px solid #3d2f0a; }
.badge-low    { background:#091a10; color:#34d399; border:1px solid #0f3320; }
.badge-type   { background:#0a1220; color:#60a5fa; border:1px solid #1e2d47; }
.badge-portal { background:#120f20; color:#a78bfa; border:1px solid #2d2252; }

/* ── Running crawl banner ── */
.running-banner {
    background: #091a10;
    border: 1px solid #0f3320;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 12.5px;
    color: #34d399;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    font-family: 'IBM Plex Mono', monospace;
}
.idle-banner {
    background: #0c0f16;
    border: 1px solid #1a1f2e;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 12.5px;
    color: #3d4f6b;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    font-family: 'IBM Plex Mono', monospace;
}
</style>
""", unsafe_allow_html=True)


# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS crawl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            pages_visited INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL,
            url TEXT NOT NULL,
            diff_type TEXT NOT NULL,
            diff_detail TEXT,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL,
            url TEXT NOT NULL,
            html_path TEXT,
            screenshot_path TEXT,
            har_path TEXT,
            updated_at TEXT NOT NULL,
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
        cur  = conn.cursor()
        cur.execute(query, args)
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        st.error(f"DB error: {e}")
        return []


# ── HELPERS ───────────────────────────────────────────────────────────────────

def time_ago(ts):
    try:
        diff = datetime.now() - datetime.fromisoformat(ts)
        s = int(diff.total_seconds())
        if s < 60:    return "just now"
        if s < 3600:  return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{diff.days}d ago"
    except Exception:
        return ts


def friendly_page_name(url):
    try:
        if "__DROPDOWN_" in url:
            return "↓ " + url.split("__DROPDOWN_")[-1].replace("_"," ").title()
        if "__PAGE_" in url:
            return url.split("__PAGE_")[-1].replace("_"," ").title()
        if "#/plastic/home/" in url.lower():
            name = url.lower().split("#/plastic/home/")[-1]
            return name.replace("/"," › ").replace("-"," ").replace("_"," ").title()
        if url.endswith("/plastic/home") or "/#/plastic/home" in url:
            return "Home Page"
        slug = url.rstrip("/").split("/")[-1].split("#")[-1]
        return slug.replace("_"," ").replace("-"," ").title() or "Home Page"
    except Exception:
        return url


DIFF_LABELS = {
    "html":   ("📄","Content"),
    "visual": ("🖼️","Visual"),
    "json":   ("📊","Data"),
    "har":    ("🔌","API"),
}


def severity_badge(diff_lines):
    if diff_lines > 50: return "🔴 High",   "High"
    if diff_lines > 10: return "🟡 Medium", "Medium"
    return "🟢 Low", "Low"


def is_crawl_running():
    rows = query_db(
        "SELECT id,portal,started_at,pages_visited FROM crawl_log "
        "WHERE status='running' "
        "AND started_at >= datetime('now','-15 minutes') "
        "AND pages_visited = 0 "
        "ORDER BY started_at DESC LIMIT 1"
    )
    return rows[0] if rows else None


def fix_stale_crawls():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """UPDATE crawl_log SET status='done'
               WHERE status='running'
               AND started_at < datetime('now','-15 minutes')"""
        ).rowcount
        conn.commit()
        conn.close()
    except Exception:
        pass


PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".", ".crawler.pid")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".", ".crawler.log")

PORTAL_CRAWLER_MAP = {
    "EPR PLASTIC":  "crawler.py",
    "EPR EWASTE":   "crawler_ewaste.py",
    "EPR BATTERY":  "crawler_battery.py",
    "EPR TYRES":    "crawler_tyres.py",
    "EPR USEDOIL":  "crawler_usedoil.py",
}


def launch_crawl(portal=None):
    if portal and portal in PORTAL_CRAWLER_MAP:
        script = PORTAL_CRAWLER_MAP[portal]
        if script == "crawler.py":
            # crawler.py is the multi-portal router — pass --portal to filter
            cmd = [sys.executable, script, "--once", "--portal", portal]
        else:
            # dedicated single-portal scripts — no --portal flag needed
            cmd = [sys.executable, script, "--once"]
    elif portal:
        cmd = [sys.executable, "crawler.py", "--once", "--portal", portal]
    else:
        # No portal selected → run all portals
        cmd = [sys.executable, "crawler.py", "--once"]

    log_fh = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd, stdout=log_fh, stderr=log_fh,
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
    )
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass


def read_log(tail=60):
    try:
        if not os.path.exists(LOG_FILE):
            return ["No log file yet — start a crawl first."]
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-tail:]] if lines else ["Log is empty."]
    except Exception as e:
        return [f"Could not read log: {e}"]


def stop_crawl():
    killed = False
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            import signal
            if sys.platform == "win32":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE)
            killed = True
    except Exception:
        pass
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE status='running'")
        conn.commit()
        conn.close()
    except Exception:
        pass
    return killed


# ── DATA ──────────────────────────────────────────────────────────────────────

def get_all_portals():
    return [r["portal"] for r in query_db("SELECT DISTINCT portal FROM crawl_log ORDER BY portal")]


def get_portal_stats(portal=None):
    and_clause = "AND cl.portal = ?" if portal else ""
    args       = (portal,) if portal else ()
    return query_db(f"""
        SELECT cl.portal,
               cl.started_at      AS last_crawl_at,
               cl.pages_visited,
               cl.status          AS last_status,
               COALESCE(td.today_changes,0) AS today_changes,
               COALESCE(at_.all_changes,0)  AS all_time_changes
        FROM   crawl_log cl
        LEFT JOIN (SELECT portal,COUNT(*) AS today_changes FROM changes
                   WHERE date(timestamp)=date('now') GROUP BY portal) td ON td.portal=cl.portal
        LEFT JOIN (SELECT portal,COUNT(*) AS all_changes  FROM changes
                   GROUP BY portal) at_ ON at_.portal=cl.portal
        WHERE cl.id IN (SELECT MAX(id) FROM crawl_log GROUP BY portal)
        {and_clause}
        ORDER BY cl.portal
    """, args)


def get_latest_crawl_changes(portal=None):
    if portal:
        row = query_db("SELECT started_at,finished_at FROM crawl_log "
                       "WHERE portal=? AND status='done' ORDER BY started_at DESC LIMIT 1", (portal,))
    else:
        row = query_db("SELECT started_at,finished_at FROM crawl_log "
                       "WHERE status='done' ORDER BY started_at DESC LIMIT 1")
    if not row: return []
    s = row[0]["started_at"]
    f = row[0]["finished_at"] or datetime.now().isoformat()
    if portal:
        return query_db("SELECT * FROM changes WHERE portal=? AND timestamp>=? AND timestamp<=? "
                        "ORDER BY timestamp DESC", (portal, s, f))
    return query_db("SELECT * FROM changes WHERE timestamp>=? AND timestamp<=? "
                    "ORDER BY timestamp DESC", (s, f))


def get_crawl_history(portal=None, limit=50):
    if portal:
        return query_db("SELECT * FROM crawl_log WHERE portal=? ORDER BY started_at DESC LIMIT ?",
                        (portal, limit))
    return query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT ?", (limit,))


# ── RENDER HELPERS ────────────────────────────────────────────────────────────

def render_html_change(detail):
    summary       = detail.get("summary","")
    added_texts   = detail.get("added_texts",[])
    removed_texts = detail.get("removed_texts",[])
    if added_texts or removed_texts:
        if summary: st.info(f"💬 {summary}")
        if added_texts:
            st.markdown("🟢 **Added:**")
            for i in added_texts[:5]: st.markdown(f"&nbsp;&nbsp;• {i}")
        if removed_texts:
            st.markdown("🔴 **Removed:**")
            for i in removed_texts[:5]: st.markdown(f"&nbsp;&nbsp;• {i}")
        return
    diff_sample = detail.get("diff_sample",[])
    if not diff_sample:
        st.info("Content changed but details not available.")
        return
    added_html   = [l[1:].strip() for l in diff_sample if l.startswith("+") and not l.startswith("+++")]
    removed_html = [l[1:].strip() for l in diff_sample if l.startswith("-") and not l.startswith("---")]
    from bs4 import BeautifulSoup
    import re
    def to_readable(lines):
        readable = []
        for raw in lines:
            if re.search(r"echarts|_ngcontent|_nghost|ng-reflect", raw, re.I): continue
            try:
                soup = BeautifulSoup(raw,"html.parser")
                for tag in soup.find_all(["button","a","label","span","h1","h2","h3","h4","p","td","li"]):
                    text = tag.get_text(strip=True)
                    if text and len(text)>1:
                        name = tag.name.upper()
                        readable.append(f'{name}: "{text}"' if name in ("BUTTON","A") else f'"{text}"')
                        break
                else:
                    plain = soup.get_text(strip=True)
                    if plain and len(plain)>1: readable.append(f'"{plain}"')
            except Exception: continue
        return list(dict.fromkeys(readable))
    ra = to_readable(added_html)
    rr = to_readable(removed_html)
    if ra:
        st.markdown("🟢 **Added:**")
        for i in ra[:5]: st.markdown(f"&nbsp;&nbsp;• {i}")
    if rr:
        st.markdown("🔴 **Removed:**")
        for i in rr[:5]: st.markdown(f"&nbsp;&nbsp;• {i}")
    if not ra and not rr:
        for line in added_html[:3]: st.code(line, language="html")


def render_change_expander(change):
    page_name = friendly_page_name(change["url"])
    when      = time_ago(change["timestamp"])
    try:
        detail     = json.loads(change["diff_detail"])
        diff_lines = detail.get("diff_lines",0)
        sev, sev_label = severity_badge(diff_lines)
        summary    = detail.get("summary","")
    except Exception:
        detail={};sev="🟢 Low";sev_label="Low";summary=""
    icon,_ = DIFF_LABELS.get(change["diff_type"],("❓",""))
    label_str = {"html":"Content","visual":"Visual","json":"Data","har":"API"}.get(change["diff_type"],"?")
    with st.expander(f"{icon} [{change['portal']}]  {page_name} — {label_str} — {when}", expanded=False):
        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f"**Portal:** `{change['portal']}`")
            st.markdown(f"**Page:** {page_name}")
        with c2:
            st.markdown(f"**Severity:** {sev_label}")
            st.markdown(f"**Type:** {label_str}")
        with c3:
            st.markdown(f"**Detected:** {change['timestamp'][:16]}")
        if summary: st.info(f"💬 {summary}")
        st.markdown("---")
        if change["diff_type"]=="html":
            render_html_change(detail)
        elif change["diff_type"]=="visual":
            ratio=detail.get("change_ratio",0);pixels=detail.get("changed_pixels",0)
            st.info(f"🖼️ {pixels:,} pixels changed ({ratio*100:.1f}%)")
        elif change["diff_type"]=="har":
            new_ep=detail.get("new_endpoints",[]);rem_ep=detail.get("removed_endpoints",[])
            if new_ep:
                st.markdown(f"🟢 **{len(new_ep)} new endpoint(s)**")
                for ep in new_ep[:3]: st.code(ep)
            if rem_ep:
                st.markdown(f"🔴 **{len(rem_ep)} removed endpoint(s)**")
                for ep in rem_ep[:3]: st.code(ep)


# ── STARTUP CLEANUP ─────────────────────────────────────────────────────────
fix_stale_crawls()

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "view"   not in st.session_state: st.session_state.view   = "overview"
if "portal" not in st.session_state: st.session_state.portal = "All Portals"

all_portals    = get_all_portals()
portal_options = ["All Portals"] + all_portals
running_crawl  = is_crawl_running()

total_crawls     = (query_db("SELECT COUNT(*) as c FROM crawl_log") or [{"c":0}])[0]["c"]
all_time_changes = (query_db("SELECT COUNT(*) as c FROM changes")   or [{"c":0}])[0]["c"]

portal_filter  = None if st.session_state.portal == "All Portals" else st.session_state.portal
latest_changes = get_latest_crawl_changes(portal_filter)


# ══════════════════════════════════════════════════════════════════
# NAVBAR — compact single row
# ══════════════════════════════════════════════════════════════════

nav_views = [
    ("overview",    "🏠", "Overview"),
    ("changes",     "🚨", "Changes"),
    ("screenshots", "📸", "Screenshots"),
    ("history",     "📅", "History"),
    ("console",     "🖥️", "Console"),
]

nb_brand, nb_tabs_cols, nb_right = st.columns([2, 6, 4])

with nb_brand:
    st.markdown(
        "<div style='padding:8px 0 6px;font-family:\"IBM Plex Mono\",monospace;"
        "font-size:13px;font-weight:600;color:#e2e8f0;letter-spacing:0.02em'>"
        "🔍 Change Monitor</div>",
        unsafe_allow_html=True
    )

# Nav tabs — one button per column
tab_cols = nb_tabs_cols.columns(len(nav_views))
for col, (view_id, icon, label) in zip(tab_cols, nav_views):
    with col:
        is_active = st.session_state.view == view_id
        if st.button(
            f"{icon} {label}",
            key=f"nav_{view_id}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.view = view_id
            st.rerun()

with nb_right:
    rc1, rc2, rc3 = st.columns([3, 2, 2])
    with rc1:
        sel = st.selectbox(
            "portal_sel", portal_options,
            index=portal_options.index(st.session_state.portal)
                  if st.session_state.portal in portal_options else 0,
            label_visibility="collapsed", key="top_portal_select"
        )
        if sel != st.session_state.portal:
            st.session_state.portal = sel
            st.rerun()
    with rc2:
        if running_crawl:
            if st.button("⏹ Stop", use_container_width=True, type="primary"):
                stop_crawl()
                time.sleep(1); st.rerun()
        else:
            if st.button("▶ Run", use_container_width=True, type="primary"):
                launch_crawl(portal_filter)
                time.sleep(2); st.rerun()
    with rc3:
        if st.button("↺ Refresh", use_container_width=True):
            st.rerun()

st.markdown("<hr style='margin:4px 0 20px;border-color:#1a1f2e'>", unsafe_allow_html=True)

# Wrap remaining content in page-content padding
st.markdown("<div style='padding:0 8px'>", unsafe_allow_html=True)

# Auto-refresh
if running_crawl:
    st.markdown("<script>setTimeout(()=>window.location.reload(),10000)</script>",
                unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
if st.session_state.view == "overview":

    portal_stats  = get_portal_stats(portal_filter)
    total_portals = len(portal_stats)
    portals_alert = sum(1 for p in portal_stats if p["today_changes"]>3)
    portals_warn  = sum(1 for p in portal_stats if 0<p["today_changes"]<=3)
    portals_ok    = sum(1 for p in portal_stats if p["today_changes"]==0)
    total_today   = sum(p["today_changes"] for p in portal_stats)

    st.markdown(
        "<div class='page-title'>🏠 Portal Overview</div>"
        "<div class='page-subtitle'>Health summary for every monitored portal</div>",
        unsafe_allow_html=True
    )

    cards = [
        ("PORTALS",        total_portals, "#3b82f6"),
        ("CHANGES TODAY",  total_today,   "#f87171" if total_today else "#34d399"),
        ("🔴 ALERT",       portals_alert, "#f87171"),
        ("🟡 WARNING",     portals_warn,  "#fbbf24"),
        ("🟢 CLEAN",       portals_ok,    "#34d399"),
    ]
    cols = st.columns(5)
    for col, (label, val, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"<div class='stat-card' style='--accent:{color}'>"
                f"<div class='s-label'>{label}</div>"
                f"<div class='s-value' style='color:{color}'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.markdown("<div class='section-hdr'>Per-portal status</div>", unsafe_allow_html=True)

    if not portal_stats:
        st.info("No portals crawled yet. Click **▶ Run** above to start.")
    else:
        for p in portal_stats:
            chg    = p["today_changes"]
            status = "alert" if chg>3 else ("warn" if chg>0 else "ok")
            dot    = "🔴" if status=="alert" else ("🟡" if status=="warn" else "🟢")
            lc_time = time_ago(p["last_crawl_at"]) if p["last_crawl_at"] else "never"
            last_status = p["last_status"] or "unknown"
            pages_val   = p["pages_visited"] if p["pages_visited"] else "—"

            stale = False
            if last_status=="running" and p["last_crawl_at"]:
                try:
                    from datetime import timedelta
                    stale = datetime.now()-datetime.fromisoformat(p["last_crawl_at"]) > timedelta(minutes=30)
                except Exception: pass

            display_status = (
                "❌ crashed"  if stale else
                "🔄 running…" if last_status=="running" else
                "✅ done"     if last_status=="done" else last_status
            )

            with st.expander(
                f"{dot}  {p['portal']}  —  "
                f"{'⚠️ '+str(chg)+' change(s) today' if chg else '✅ Clean today'}  —  "
                f"Last crawl: {lc_time}",
                expanded=(status!="ok")
            ):
                pc1,pc2,pc3,pc4 = st.columns(4)
                pc1.metric("Today",      chg)
                pc2.metric("All-time",   p["all_time_changes"])
                pc3.metric("Pages",      pages_val)
                pc4.metric("Status",     display_status)

                if last_status=="running" and not stale:
                    st.warning("🔄 Crawl in progress…")
                elif stale:
                    st.error("❌ Crawl seems crashed. Use **▶ Run** to restart.")

                st.caption(f"Last crawl: {p['last_crawl_at'][:16] if p['last_crawl_at'] else 'never'}")

                if chg>0:
                    st.markdown("---")
                    st.markdown("**Latest changes:**")
                    for ch in query_db(
                        "SELECT * FROM changes WHERE portal=? AND date(timestamp)=date('now') "
                        "ORDER BY timestamp DESC LIMIT 5", (p["portal"],)
                    ):
                        icon,lbl = DIFF_LABELS.get(ch["diff_type"],("❓","?"))
                        st.markdown(
                            f"&nbsp;&nbsp;{icon} `{friendly_page_name(ch['url'])}` — {lbl} — {time_ago(ch['timestamp'])}"
                        )


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: LATEST CHANGES
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "changes":
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.markdown(
        "<div class='page-title'>🚨 Latest Changes</div>"
        f"<div class='page-subtitle'>Scope: {scope} · Most recent crawl run</div>",
        unsafe_allow_html=True
    )

    f1,f2,f3,f4 = st.columns([2,2,2,3])
    with f1:
        filter_type = st.selectbox("Type",
            ["All Types","📄 Content","🖼️ Visual","📊 Data","🔌 API"], key="filter_type")
    with f2:
        filter_sev = st.selectbox("Severity",
            ["All Severities","🔴 High","🟡 Medium","🟢 Low"], key="filter_sev")
    with f3:
        if not portal_filter:
            fp_local = st.selectbox("Portal", ["All Portals"]+all_portals, key="fp_local")
        else:
            fp_local = st.session_state.portal
            st.caption(f"Portal: {st.session_state.portal}")
    with f4:
        search_q = st.text_input("🔍 Search page", placeholder="e.g. Home, SOP…", key="search_q")

    st.markdown("<hr style='margin:8px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)

    if not latest_changes:
        st.success("✅ No changes in the latest crawl.")
    else:
        type_map = {"📄 Content":"html","🖼️ Visual":"visual","📊 Data":"json","🔌 API":"har"}
        filtered = latest_changes[:]

        if filter_type != "All Types":
            filtered = [c for c in filtered if c["diff_type"]==type_map.get(filter_type)]
        if filter_sev != "All Severities":
            sl = filter_sev.split(" ",1)[1]
            def sev_of(c):
                try:
                    d=json.loads(c["diff_detail"]); _,s=severity_badge(d.get("diff_lines",0)); return s
                except: return "Low"
            filtered = [c for c in filtered if sev_of(c)==sl]
        if fp_local != "All Portals":
            filtered = [c for c in filtered if c["portal"]==fp_local]
        if search_q:
            filtered = [c for c in filtered if search_q.lower() in friendly_page_name(c["url"]).lower()]

        st.caption(f"Showing **{len(filtered)}** of {len(latest_changes)} change(s)")
        for change in filtered:
            render_change_expander(change)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: SCREENSHOTS
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "screenshots":
    st.markdown(
        "<div class='page-title'>📸 Changed Pages</div>"
        "<div class='page-subtitle'>Before / after screenshots of changed pages</div>",
        unsafe_allow_html=True
    )

    if not latest_changes:
        st.success("✅ No changed pages in the latest crawl.")
    else:
        changed_urls = list({c["url"] for c in latest_changes})
        def url_label(url):
            chg = next((c for c in latest_changes if c["url"]==url),{})
            p   = chg.get("portal","")
            return f"[{p}] {friendly_page_name(url)}" if p else friendly_page_name(url)

        labels       = [url_label(u) for u in changed_urls]
        sel_label    = st.selectbox(f"Select page ({len(changed_urls)} changed)", labels)
        selected_url = changed_urls[labels.index(sel_label)]

        st.markdown("<hr style='margin:8px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)

        baseline     = query_db("SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2", (selected_url,))
        page_changes = query_db("SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC", (selected_url,))
        latest_b     = baseline[0] if len(baseline)>0 else None
        prev_b       = baseline[1] if len(baseline)>1 else None
        chg_portal   = page_changes[0]["portal"] if page_changes else "—"

        st.markdown(
            f"<div class='page-title' style='font-size:17px'>{friendly_page_name(selected_url)}"
            f" <span style='font-size:12px;color:#a78bfa;font-weight:500'>[{chg_portal}]</span></div>",
            unsafe_allow_html=True
        )

        sc1,sc2 = st.columns(2)
        with sc1:
            st.markdown("**⬅️ Previous snapshot**")
            if prev_b:
                p = prev_b.get("screenshot_path")
                st.image(p, use_container_width=True) if p and os.path.exists(p) else st.info("Not available")
            else:
                st.info("No previous snapshot")
        with sc2:
            st.markdown("**➡️ Latest snapshot**")
            if latest_b:
                p = latest_b.get("screenshot_path")
                st.image(p, use_container_width=True) if p and os.path.exists(p) else st.info("Not available")
            else:
                st.info("No latest snapshot")

        st.markdown("---")
        for change in page_changes[:3]:
            icon,label = DIFF_LABELS.get(change["diff_type"],("❓","?"))
            with st.expander(f"{icon} {label} change", expanded=True):
                try:
                    detail = json.loads(change["diff_detail"])
                    if change["diff_type"]=="html": render_html_change(detail)
                    elif change["diff_type"]=="visual":
                        st.info(f"Appearance changed by {detail.get('change_ratio',0)*100:.1f}%")
                except Exception:
                    st.info("Details unavailable.")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: CRAWL HISTORY
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "history":
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.markdown(
        "<div class='page-title'>📅 Crawl History</div>"
        f"<div class='page-subtitle'>Scope: {scope}</div>",
        unsafe_allow_html=True
    )

    h1,_ = st.columns([2,5])
    with h1:
        hist_filter = st.selectbox("Filter",
            ["All Crawls","✅ With Changes","🟢 No Changes"], key="hist_filter")

    crawl_logs = get_crawl_history(portal_filter)

    if not crawl_logs:
        st.info("No crawls recorded yet.")
    else:
        st.markdown("<hr style='margin:8px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)
        for log in crawl_logs:
            count_row = query_db(
                "SELECT COUNT(*) as c FROM changes WHERE portal=? AND timestamp>=? AND timestamp<=?",
                (log["portal"], log["started_at"], log["finished_at"] or datetime.now().isoformat()))
            count = count_row[0]["c"] if count_row else 0

            if hist_filter=="✅ With Changes" and count==0: continue
            if hist_filter=="🟢 No Changes"  and count>0:  continue

            started  = log["started_at"][:16]
            finished = log["finished_at"][:16] if log["finished_at"] else "—"
            done     = log["status"]=="done"

            with st.expander(
                f"{'✅' if done else '🔄' if log['status']=='running' else '❌'} "
                f"[{log['portal']}]  {started}  |  "
                f"{'⚠️ '+str(count)+' change(s)' if count>0 else '✅ No changes'}  |  "
                f"{log['pages_visited']} pages",
                expanded=False
            ):
                dc1,dc2,dc3,dc4 = st.columns(4)
                dc1.metric("Pages", log["pages_visited"])
                dc2.metric("Changes", count)
                dc3.markdown(f"**Started:** {started}")
                dc4.markdown(f"**Finished:** {finished}")
                st.markdown(f"**Portal:** `{log['portal']}`  **Status:** `{log['status']}`")

                if count>0:
                    st.markdown("---")
                    st.markdown("**Pages that changed:**")
                    for p_row in query_db(
                        "SELECT DISTINCT url,diff_type FROM changes WHERE portal=? AND timestamp>=? AND timestamp<=?",
                        (log["portal"],log["started_at"],log["finished_at"] or datetime.now().isoformat())
                    )[:10]:
                        icon,lbl = DIFF_LABELS.get(p_row["diff_type"],("❓","?"))
                        st.markdown(f"&nbsp;&nbsp;{icon} `{friendly_page_name(p_row['url'])}` — {lbl}")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: CONSOLE
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "console":
    st.markdown(
        "<div class='page-title'>🖥️ Crawler Console</div>"
        "<div class='page-subtitle'>Live output from the crawler process</div>",
        unsafe_allow_html=True
    )

    cc1, cc2, _ = st.columns([1,1,5])
    with cc1:
        if st.button("↺ Refresh log", use_container_width=True): st.rerun()
    with cc2:
        tail_lines = st.selectbox("Lines", [30, 60, 100, 200], index=1,
                                  label_visibility="collapsed", key="tail_lines")

    log_lines = read_log(tail=tail_lines)

    if running_crawl:
        st.markdown(
            "<div class='running-banner'>🔄 Crawler is running — refreshing every 5s</div>",
            unsafe_allow_html=True
        )
        st.markdown("<script>setTimeout(()=>window.location.reload(),5000)</script>",
                    unsafe_allow_html=True)
    else:
        st.markdown(
            "<div class='idle-banner'>⏸ Crawler idle — click ▶ Run in the top bar to start</div>",
            unsafe_allow_html=True
        )

    # ── FIX: filter ScriptRunContext spam + full color logic ──────────────────
    def colorize(line):
        # Suppress noisy Streamlit bare-mode warnings from subprocess
        if "ScriptRunContext" in line:
            return ""
        if not line.strip():
            return ""
        if any(x in line for x in ["ERROR","error","Exception","Traceback"]):
            color = "#f87171"
        elif any(x in line for x in ["WARNING","warning","WARN"]):
            color = "#fbbf24"
        elif any(x in line for x in ["✓","Done","done","saved","Saved","ALL DONE"]):
            color = "#34d399"
        elif any(x in line for x in ["═══","STEP","Step"]):
            color = "#60a5fa"
        elif any(x in line for x in ["✅","Change","change"]):
            color = "#a78bfa"
        else:
            color = "#8899b4"
        escaped = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f"<span style='color:{color}'>{escaped}</span>"

    colored_lines = [colorize(l) for l in log_lines]
    # Filter out empty strings from suppressed lines before joining
    log_html = "<br>".join(c for c in colored_lines if c)

    st.markdown(f"""
        <div style='background:#050709;border:1px solid #1a1f2e;border-radius:10px;
                    padding:18px 20px;font-family:"IBM Plex Mono",monospace;font-size:11.5px;
                    line-height:1.75;max-height:520px;overflow-y:auto;
                    white-space:pre-wrap;word-break:break-all'>
            {log_html}
        </div>
    """, unsafe_allow_html=True)

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "rb") as f:
            st.download_button("⬇ Download full log", f, file_name="crawler.log",
                               mime="text/plain", use_container_width=False)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1a1f2e;margin-top:32px'>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-family:\"IBM Plex Mono\",monospace;font-size:11px;color:#2d3a52;"
    f"padding:0 8px 16px'>"
    f"Portal Change Monitor · {st.session_state.portal} · "
    f"{datetime.now().strftime('%d %b %Y, %I:%M %p')}</div>",
    unsafe_allow_html=True
)