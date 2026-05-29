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
/* ── Hide everything Streamlit default ── */
[data-testid="stToolbar"],[data-testid="stHeader"],#MainMenu,header,
[data-testid="stDecoration"],[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],[data-testid="stSidebarCollapseButton"],
button[aria-label="Close sidebar"],button[aria-label="Collapse sidebar"]
{display:none!important;visibility:hidden!important;width:0!important;height:0!important}

/* ── Page background ── */
[data-testid="stAppViewContainer"]{background:#0f1117}
.main .block-container{padding:0 2rem 2rem 2rem;max-width:1400px}

/* ── TOP NAVBAR ── */
.topnav{
  position:sticky;top:0;z-index:9999;
  background:#13161f;
  border-bottom:1px solid #2a2d3e;
  padding:0 24px;
  display:flex;align-items:center;gap:0;
  height:54px;
  margin:-1rem -2rem 1.5rem -2rem;
}
.topnav-brand{
  font-size:15px;font-weight:700;color:#e6edf3;
  display:flex;align-items:center;gap:8px;
  padding-right:24px;border-right:1px solid #2a2d3e;
  white-space:nowrap;
}
.topnav-tabs{display:flex;align-items:center;gap:2px;padding:0 16px;flex:1}
.topnav-tab{
  padding:6px 14px;border-radius:6px;
  font-size:13px;font-weight:500;color:#8b95a8;
  cursor:pointer;border:none;background:transparent;
  transition:background .12s,color .12s;white-space:nowrap;
}
.topnav-tab:hover{background:#1e2130;color:#c9d1d9}
.topnav-tab.active{background:#1e2130;color:#e6edf3}
.topnav-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.nav-portal-select{
  background:#1e2130;border:1px solid #2a2d3e;border-radius:6px;
  color:#e6edf3;font-size:12px;padding:4px 8px;cursor:pointer;
}
.crawl-status-pill{
  font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;
  background:#0d2b1a;color:#34d399;border:1px solid #155230;white-space:nowrap;
}
.crawl-status-pill.running{
  background:#1a2540;color:#60a5fa;border-color:#253a60;
}

/* ── Stat cards ── */
.stat-card{background:#1e2130;border:1px solid #2a2d3e;border-radius:12px;padding:16px 20px}
.stat-card .label{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#6e7891}
.stat-card .value{font-size:30px;font-weight:700;color:#e6edf3;line-height:1.1;margin:4px 0}

/* ── Expander dark ── */
details,details[open]{background:#1e2130!important;border-radius:10px}
details summary{font-size:14px!important;color:#e6edf3!important;font-weight:500!important;background:#1e2130!important}
details>div{background:#1e2130!important}
[data-testid="stExpander"]{background:#1e2130!important;border:1px solid #2a2d3e!important;border-radius:10px!important;margin-bottom:6px!important}
[data-testid="stExpander"] summary{background:#1e2130!important;color:#e6edf3!important}
[data-testid="stExpander"] summary *{color:#e6edf3!important;background:#1e2130!important}
[data-testid="stExpander"] svg{stroke:#e6edf3!important;fill:none!important}
[data-testid="stExpander"] div{background:#1e2130!important}
[data-testid="stExpander"] section{background:#1e2130!important}
[data-testid="stExpander"] p{color:#c9d1d9!important}
[data-testid="stExpander"] strong,[data-testid="stExpander"] b{color:#e6edf3!important}
[data-testid="stExpander"] [data-testid="stMetricValue"]{color:#e6edf3!important}
[data-testid="stExpander"] [data-testid="stMetricLabel"] p{color:#8b95a8!important}
[data-testid="stExpanderDetails"]{background:#1e2130!important}
[data-testid="stExpanderDetails"] div{background:#1e2130!important}

/* ── General text ── */
.main h1,.main h2,.main h3,.main h4{color:#e6edf3!important}
.stMarkdown p,.stMarkdown span,.stMarkdown li{color:#c9d1d9!important}
.stCaption,[data-testid="stCaptionContainer"]{color:#6e7891!important}
code{background:#252a3d!important;color:#60a5fa!important;border-radius:4px}
hr{border-color:#2a2d3e!important}

/* ── Selectbox ── */
[data-testid="stSelectbox"]>div>div{background:#1e2130!important;border:1px solid #2a2d3e!important;color:#e6edf3!important;border-radius:8px!important}
[data-testid="stSelectbox"] svg{fill:#6e7891!important}
[data-testid="stSelectbox"] span{color:#e6edf3!important}
[data-baseweb="popover"],[data-baseweb="menu"],[data-baseweb="select"] ul{background:#1e2130!important;border:1px solid #2a2d3e!important;border-radius:10px!important}
[data-baseweb="menu"] li,[data-baseweb="option"],[role="option"]{background:#1e2130!important;color:#c9d1d9!important;font-size:14px!important}
[data-baseweb="option"]:hover,[role="option"]:hover,[aria-selected="true"][role="option"]{background:#252a3d!important;color:#60a5fa!important}

/* ── Text input ── */
[data-testid="stTextInput"] input{background:#1e2130!important;border:1px solid #2a2d3e!important;color:#e6edf3!important;border-radius:8px!important}
[data-testid="stTextInput"] input::placeholder{color:#4a5568!important}

/* ── Radio ── */
[data-testid="stRadio"] label{color:#c9d1d9!important}

/* ── Badges ── */
.badge{font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;white-space:nowrap}
.badge-high{background:#3d1a1a;color:#f87171;border:1px solid #5c2626}
.badge-medium{background:#3d2f0a;color:#fbbf24;border:1px solid #5c470f}
.badge-low{background:#0d2b1a;color:#34d399;border:1px solid #155230}
.badge-type{background:#1a2540;color:#60a5fa;border:1px solid #253a60}
.badge-portal{background:#252a3d;color:#a78bfa;border:1px solid #3b3466;font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;white-space:nowrap}
.section-header{font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#4a5568;border-bottom:1px solid #2a2d3e;padding-bottom:8px;margin-bottom:14px}
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
            return "Dropdown: " + url.split("__DROPDOWN_")[-1].replace("_"," ").title()
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
    """Only treat as running if started within last 15 min and pages_visited is still 0."""
    rows = query_db(
        "SELECT id,portal,started_at,pages_visited FROM crawl_log "
        "WHERE status='running' "
        "AND started_at >= datetime('now','-15 minutes') "
        "AND pages_visited = 0 "
        "ORDER BY started_at DESC LIMIT 1"
    )
    return rows[0] if rows else None


def fix_stale_crawls():
    """Auto-fix any stuck 'running' rows older than 15 min on startup."""
    try:
        conn = sqlite3.connect(DB_PATH)
        fixed = conn.execute(
            """UPDATE crawl_log SET status='done'
               WHERE status='running'
               AND started_at < datetime('now','-15 minutes')"""
        ).rowcount
        conn.commit()
        conn.close()
        if fixed:
            import logging
            logging.getLogger(__name__).info("Auto-fixed %d stale running crawl(s)", fixed)
    except Exception:
        pass


PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".", ".crawler.pid")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".", ".crawler.log")


# Maps portal name → which crawler script to run
PORTAL_CRAWLER_MAP = {
    "EPR PLASTIC": "crawler.py",
    "EPR EWASTE":  "crawler_ewaste.py",
}


def launch_crawl(portal=None):
    """
    Launch the correct crawler script for the given portal.
    EPR PLASTIC → crawler.py
    EPR EWASTE  → crawler_ewaste.py
    All Portals → crawler.py --once (which routes internally)
    """
    # Pick the right script
    if portal and portal in PORTAL_CRAWLER_MAP:
        script = PORTAL_CRAWLER_MAP[portal]
        cmd    = [sys.executable, script, "--once"]
    elif portal:
        # Unknown portal — use main crawler with --portal flag
        cmd = [sys.executable, "crawler.py", "--once", "--portal", portal]
    else:
        # All Portals — main crawler handles routing
        cmd = [sys.executable, "crawler.py", "--once"]

    log_fh = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=log_fh,
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
    )
    # Save PID so Stop button can kill it
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    print(f"Launched {cmd[1]} for portal={portal or 'all'} PID={proc.pid}")


def read_log(tail=60):
    """Read last `tail` lines from the crawler log file."""
    try:
        if not os.path.exists(LOG_FILE):
            return ["No log file yet — start a crawl first."]
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-tail:]] if lines else ["Log is empty."]
    except Exception as e:
        return [f"Could not read log: {e}"]


def stop_crawl():
    """Kill the running crawler process and mark DB row as stopped."""
    killed = False
    # Kill by PID file
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
    # Mark DB row as stopped
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE status='running'"
        )
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
    with st.expander(f"{icon} **[{change['portal']}]** {page_name} — {label_str} — {when}", expanded=False):
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
fix_stale_crawls()  # fix any stuck 'running' rows before rendering

# ── SESSION STATE — active view & portal ──────────────────────────────────────

if "view" not in st.session_state:
    st.session_state.view = "overview"
if "portal" not in st.session_state:
    st.session_state.portal = "All Portals"

all_portals    = get_all_portals()
portal_options = ["All Portals"] + all_portals
running_crawl  = is_crawl_running()

lc_row = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 1")
lc     = lc_row[0] if lc_row else {}

total_crawls     = (query_db("SELECT COUNT(*) as c FROM crawl_log") or [{"c":0}])[0]["c"]
all_time_changes = (query_db("SELECT COUNT(*) as c FROM changes")   or [{"c":0}])[0]["c"]

portal_filter = None if st.session_state.portal == "All Portals" else st.session_state.portal
latest_changes = get_latest_crawl_changes(portal_filter)


# ── TOP NAVBAR ────────────────────────────────────────────────────────────────

# Tabs row
col_brand, col_tabs, col_right = st.columns([2, 5, 3])

with col_brand:
    st.markdown("<div style='padding:10px 0;font-size:16px;font-weight:700;color:#e6edf3'>🔍 Change Monitor</div>",
                unsafe_allow_html=True)

with col_tabs:
    t1,t2,t3,t4,col_tabs2 = st.columns(5)
    with t1:
        if st.button("🏠 Overview",   use_container_width=True,
                     type="primary" if st.session_state.view=="overview"   else "secondary"):
            st.session_state.view="overview";   st.rerun()
    with t2:
        if st.button("🚨 Changes",    use_container_width=True,
                     type="primary" if st.session_state.view=="changes"    else "secondary"):
            st.session_state.view="changes";    st.rerun()
    with t3:
        if st.button("📸 Screenshots",use_container_width=True,
                     type="primary" if st.session_state.view=="screenshots" else "secondary"):
            st.session_state.view="screenshots";st.rerun()
    with t4:
        if st.button("📅 History",    use_container_width=True,
                     type="primary" if st.session_state.view=="history"    else "secondary"):
            st.session_state.view="history";    st.rerun()

with col_tabs2:
    if st.button("🖥️ Console", use_container_width=True,
                 type="primary" if st.session_state.view=="console" else "secondary"):
        st.session_state.view="console"; st.rerun()

with col_right:
    r1,r2,r3 = st.columns([3,2,2])
    with r1:
        sel = st.selectbox("Portal", portal_options,
                           index=portal_options.index(st.session_state.portal)
                                 if st.session_state.portal in portal_options else 0,
                           label_visibility="collapsed", key="top_portal_select")
        if sel != st.session_state.portal:
            st.session_state.portal = sel
            st.rerun()
    with r2:
        if running_crawl:
            if st.button("⏹ Stop Crawl", use_container_width=True, type="primary",
                         help="Kill the running crawler process"):
                stopped = stop_crawl()
                if stopped:
                    st.warning("🛑 Crawl stopped.")
                else:
                    st.info("Marked as stopped in DB.")
                time.sleep(1)
                st.rerun()
        else:
            if st.button("▶ Run Crawl", use_container_width=True, type="primary"):
                launch_crawl(portal_filter)
                time.sleep(2)
                st.success("✅ Crawl started!")
                st.rerun()
    with r3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

st.markdown("<hr style='margin:0 0 1.5rem 0;border-color:#2a2d3e'>", unsafe_allow_html=True)

# Auto-refresh every 10s while crawl is running
if running_crawl:
    st.markdown("<script>setTimeout(()=>window.location.reload(),10000)</script>",
                unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
if st.session_state.view == "overview":
    st.markdown("<h2 style='color:#e6edf3;margin-bottom:4px'>🏠 Portal Overview</h2>", unsafe_allow_html=True)
    st.caption("Health summary for every monitored portal.")

    portal_stats  = get_portal_stats(portal_filter)
    total_portals = len(portal_stats)
    portals_alert = sum(1 for p in portal_stats if p["today_changes"]>3)
    portals_warn  = sum(1 for p in portal_stats if 0<p["today_changes"]<=3)
    portals_ok    = sum(1 for p in portal_stats if p["today_changes"]==0)
    total_today   = sum(p["today_changes"] for p in portal_stats)

    c1,c2,c3,c4,c5 = st.columns(5)
    for col,label,val,color in [
        (c1,"Portals",       total_portals,  "#60a5fa"),
        (c2,"Changes today", total_today,    "#f87171" if total_today else "#34d399"),
        (c3,"🔴 Alert",      portals_alert,  "#f87171"),
        (c4,"🟡 Warning",    portals_warn,   "#fbbf24"),
        (c5,"🟢 Clean",      portals_ok,     "#34d399"),
    ]:
        with col:
            st.markdown(f'<div class="stat-card"><div class="label">{label}</div>'
                        f'<div class="value" style="color:{color};font-size:28px">{val}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>Per-portal status</div>", unsafe_allow_html=True)

    if not portal_stats:
        st.info("No portals crawled yet. Click **▶ Run Crawl** above to start.")
    else:
        for p in portal_stats:
            chg = p["today_changes"]
            status = "alert" if chg>3 else ("warn" if chg>0 else "ok")
            dot    = "🔴" if status=="alert" else ("🟡" if status=="warn" else "🟢")
            lc_time= time_ago(p["last_crawl_at"]) if p["last_crawl_at"] else "never"
            last_status = p["last_status"] or "unknown"
            pages_val   = p["pages_visited"] if p["pages_visited"] else "—"

            stale = False
            if last_status=="running" and p["last_crawl_at"]:
                try:
                    from datetime import timedelta
                    stale = datetime.now()-datetime.fromisoformat(p["last_crawl_at"]) > timedelta(minutes=30)
                except Exception: pass

            display_status = ("❌ crashed" if stale else
                              "🔄 running…" if last_status=="running" else
                              "✅ done"     if last_status=="done"    else last_status)

            with st.expander(
                f"{dot} **{p['portal']}** — "
                f"{'⚠️ '+str(chg)+' change(s) today' if chg else '✅ Clean today'} — "
                f"Last crawl: {lc_time}", expanded=(status!="ok")):
                pc1,pc2,pc3,pc4 = st.columns(4)
                pc1.metric("Today's changes",  chg)
                pc2.metric("All-time changes", p["all_time_changes"])
                pc3.metric("Pages (last run)", pages_val)
                pc4.metric("Last status",      display_status)

                if last_status=="running" and not stale:
                    st.warning("🔄 Crawl in progress — auto-refreshing…")
                elif stale:
                    st.error("❌ Crawl seems crashed. Restart from **▶ Run Crawl**.")

                st.caption(f"Last crawl: {p['last_crawl_at'][:16] if p['last_crawl_at'] else 'never'}")

                if chg>0:
                    st.markdown("---")
                    st.markdown("**Latest changes:**")
                    for ch in query_db("SELECT * FROM changes WHERE portal=? AND date(timestamp)=date('now') "
                                       "ORDER BY timestamp DESC LIMIT 5", (p["portal"],)):
                        icon,lbl = DIFF_LABELS.get(ch["diff_type"],("❓","?"))
                        st.markdown(f"&nbsp;&nbsp;{icon} `{friendly_page_name(ch['url'])}` — {lbl} — {time_ago(ch['timestamp'])}")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: LATEST CHANGES
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "changes":
    st.markdown("<h2 style='color:#e6edf3;margin-bottom:4px'>🚨 Latest Changes</h2>", unsafe_allow_html=True)
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.caption(f"Scope: {scope}  ·  Most recent crawl run")

    # ── Filter bar ────────────────────────────────────────────────────────────
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

    st.markdown("<hr>", unsafe_allow_html=True)

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

        st.markdown(f"<div style='font-size:13px;color:#6e7891;margin-bottom:12px'>"
                    f"Showing <b style='color:#e6edf3'>{len(filtered)}</b> of {len(latest_changes)} change(s)</div>",
                    unsafe_allow_html=True)
        for change in filtered:
            render_change_expander(change)


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: SCREENSHOTS
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "screenshots":
    st.markdown("<h2 style='color:#e6edf3;margin-bottom:4px'>📸 Changed Pages</h2>", unsafe_allow_html=True)
    st.caption("Before / after screenshots of changed pages.")

    if not latest_changes:
        st.success("✅ No changed pages in the latest crawl.")
    else:
        changed_urls = list({c["url"] for c in latest_changes})
        def url_label(url):
            chg = next((c for c in latest_changes if c["url"]==url),{})
            p   = chg.get("portal","")
            return f"[{p}] {friendly_page_name(url)}" if p else friendly_page_name(url)

        labels        = [url_label(u) for u in changed_urls]
        sel_label     = st.selectbox(f"Select page ({len(changed_urls)} changed)", labels)
        selected_url  = changed_urls[labels.index(sel_label)]

        st.markdown("<hr>", unsafe_allow_html=True)
        baseline     = query_db("SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2", (selected_url,))
        page_changes = query_db("SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC", (selected_url,))
        latest_b     = baseline[0] if len(baseline)>0 else None
        prev_b       = baseline[1] if len(baseline)>1 else None
        chg_portal   = page_changes[0]["portal"] if page_changes else "—"

        st.markdown(f"<h3 style='color:#e6edf3'>📄 {friendly_page_name(selected_url)}"
                    f" <span style='font-size:13px;color:#a78bfa'>[{chg_portal}]</span></h3>",
                    unsafe_allow_html=True)

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
    st.markdown("<h2 style='color:#e6edf3;margin-bottom:4px'>📅 Crawl History</h2>", unsafe_allow_html=True)
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"
    st.caption(f"Scope: {scope}")

    h1,h2 = st.columns([2,5])
    with h1:
        hist_filter = st.selectbox("Filter",
            ["All Crawls","✅ With Changes","🟢 No Changes"], key="hist_filter")

    crawl_logs = get_crawl_history(portal_filter)

    if not crawl_logs:
        st.info("No crawls recorded yet.")
    else:
        st.markdown("<hr>", unsafe_allow_html=True)
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
                f"{'⚠️ '+str(count)+' change(s)' if count>0 else '🟢 No changes'}  |  "
                f"{log['pages_visited']} pages", expanded=False):

                dc1,dc2,dc3,dc4 = st.columns(4)
                dc1.metric("Pages scanned", log["pages_visited"])
                dc2.metric("Changes found", count)
                dc3.markdown(f"**Started:** {started}")
                dc4.markdown(f"**Finished:** {finished}")
                st.markdown(f"**Portal:** `{log['portal']}`  **Status:** `{log['status']}`")

                if count>0:
                    st.markdown("---")
                    st.markdown("**Pages that changed:**")
                    for p in query_db(
                        "SELECT DISTINCT url,diff_type FROM changes WHERE portal=? AND timestamp>=? AND timestamp<=?",
                        (log["portal"],log["started_at"],log["finished_at"] or datetime.now().isoformat()))[:10]:
                        icon,lbl = DIFF_LABELS.get(p["diff_type"],("❓","?"))
                        st.markdown(f"&nbsp;&nbsp;{icon} `{friendly_page_name(p['url'])}` — {lbl} change")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: CONSOLE
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "console":
    st.markdown("<h2 style=\'color:#e6edf3;margin-bottom:4px\'>🖥️ Crawler Console</h2>", unsafe_allow_html=True)
    st.caption("Live output from the crawler process.")

    # Controls row
    cc1, cc2, cc3 = st.columns([1,1,5])
    with cc1:
        if st.button("🔄 Refresh log", use_container_width=True):
            st.rerun()
    with cc2:
        tail_lines = st.selectbox("Lines", [30, 60, 100, 200], index=1,
                                  label_visibility="collapsed", key="tail_lines")

    log_lines = read_log(tail=tail_lines)

    # Status banner
    if running_crawl:
        st.markdown("""<div style='background:#0d2b1a;border:1px solid #155230;border-radius:8px;
            padding:10px 14px;margin-bottom:12px;font-size:13px;color:#34d399;font-weight:600'>
            🔄 Crawler is running — log is updating live. Page auto-refreshes every 5s.</div>""",
            unsafe_allow_html=True)
        # faster auto-refresh on console view
        st.markdown("<script>setTimeout(()=>window.location.reload(),5000)</script>",
                    unsafe_allow_html=True)
    else:
        st.markdown("""<div style='background:#1e2130;border:1px solid #2a2d3e;border-radius:8px;
            padding:10px 14px;margin-bottom:12px;font-size:13px;color:#6e7891'>
            ⏸ Crawler is idle. Click <b>▶ Run Crawl</b> in the top bar to start.</div>""",
            unsafe_allow_html=True)

    # Color-code log lines
    def colorize(line):
        if not line.strip(): return ""
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
            color = "#c9d1d9"
        escaped = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f"<span style='color:{color}'>{escaped}</span>"

    colored_lines = [colorize(l) for l in log_lines]
    log_html = "<br>".join(colored_lines)

    st.markdown(f"""
        <div style='background:#0d1117;border:1px solid #2a2d3e;border-radius:10px;
                    padding:16px 18px;font-family:monospace;font-size:12px;
                    line-height:1.7;max-height:520px;overflow-y:auto;
                    white-space:pre-wrap;word-break:break-all'>
            {log_html}
        </div>
    """, unsafe_allow_html=True)

    # Download log button
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "rb") as f:
            st.download_button("⬇ Download full log", f, file_name="crawler.log",
                               mime="text/plain", use_container_width=False)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Portal Change Monitor · Scope: {st.session_state.portal} · "
           f"Refreshed: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")