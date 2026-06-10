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

IS_CLOUD = os.getenv("STREAMLIT_RUNTIME_ENV") == "cloud"
AUTH_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".auth_flag")


def _secret(key: str, fallback: str) -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError, AttributeError):
        return fallback


# ── LOGIN GATE ────────────────────────────────────────────────────────────────
def _check_credentials(username: str, password: str) -> bool:
    valid_user = _secret("LOGIN_USER", os.getenv("LOGIN_USER", "webtracker@test.com"))
    valid_pass = _secret("LOGIN_PASS",  os.getenv("LOGIN_PASS",  "12345"))
    return username.strip() == valid_user and password == valid_pass

if "authenticated" not in st.session_state:
    try:
        st.session_state["authenticated"] = os.path.exists(AUTH_FLAG)
    except Exception:
        st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #f8fafc !important;
    font-family: 'Outfit', sans-serif !important;
}
.login-outer {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 20px;
    background: #f8fafc;
}
.login-card-container {
    width: 100%;
    max-width: 420px;
    margin: auto;
}
.login-head {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 24px;
    text-align: center;
}
.logo-wrapper {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px rgba(37,99,235,0.25);
    margin-bottom: 16px;
}
.logo-icon {
    font-size: 24px;
    color: #ffffff;
}
.login-title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
    letter-spacing: -0.02em;
}
.login-sub {
    font-size: 14px;
    color: #64748b;
    margin-top: 6px;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 20px !important;
    padding: 36px !important;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.04), 0 4px 6px -4px rgba(0, 0, 0, 0.04) !important;
}
[data-testid="stTextInput"]>div>div {
    background-color: #f8fafc !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTextInput"]>div>div:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
    background-color: #ffffff !important;
}
[data-testid="stTextInput"] input {
    color: #0f172a !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
}
[data-testid="stButton"] button {
    background: #2563eb !important;
    border: 1px solid #2563eb !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    height: 42px !important;
    font-size: 14px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 6px -1px rgba(37,99,235,0.1) !important;
    margin-top: 8px !important;
}
[data-testid="stButton"] button:hover {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
    box-shadow: 0 6px 12px -1px rgba(37,99,235,0.2) !important;
    transform: translateY(-1px);
}
.helper {
    font-size: 12px;
    color: #64748b;
    margin-top: 16px;
    text-align: center;
    font-family: inherit;
}
</style>
""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        with st.container(border=True):
            st.markdown("""
            <div class="login-head">
              <div class="logo-wrapper">
                <div class="logo-icon">🔍</div>
              </div>
              <div class="login-title">Portal Change Monitor</div>
              <div class="login-sub">CPCB EPR · internal dashboard</div>
            </div>
            """, unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="admin", label_visibility="collapsed", key="login_user")
            password = st.text_input("Password", placeholder="••••••••", type="password", label_visibility="collapsed", key="login_pass")
            if st.button("Sign in", key="login_submit", use_container_width=True):
                if _check_credentials(username, password):
                    try:
                        with open(AUTH_FLAG, "w", encoding="utf-8") as _f:
                            _f.write(username or "user")
                    except Exception:
                        pass
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
            st.markdown('<div class="helper">You will remain logged in until you click Logout.</div>', unsafe_allow_html=True)
    st.stop()


def logout():
    st.session_state["authenticated"] = False
    # remove persisted auth flag so user stays logged out across refreshes
    try:
        if os.path.exists(AUTH_FLAG):
            os.remove(AUTH_FLAG)
    except Exception:
        pass
    st.rerun()


# ── PLAYWRIGHT CLOUD INIT ─────────────────────────────────────────────────────
if IS_CLOUD:
    @st.cache_resource
    def install_playwright_on_cloud():
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            return True
        except Exception as e:
            print(f"☁️ Playwright installation failed: {e}", flush=True)
            return False
    install_playwright_on_cloud()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
*,*::before,*::after{box-sizing:border-box;}
[data-testid="stToolbar"],[data-testid="stHeader"],#MainMenu,header,[data-testid="stDecoration"],
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],button[aria-label="Close sidebar"],
button[aria-label="Collapse sidebar"]{display:none!important;visibility:hidden!important;width:0!important;height:0!important}
html,body,[data-testid="stAppViewContainer"]{font-family:'Outfit',sans-serif!important;background:#f8fafc!important;color:#0f172a!important;}
.main .block-container{padding:0!important;max-width:100%!important;}

/* Buttons Styling */
[data-testid="stButton"] button{
    font-family:'Outfit',sans-serif!important;
    font-size:13px!important;
    font-weight:600!important;
    padding:6px 16px!important;
    height:36px!important;
    border-radius:8px!important;
    white-space:nowrap!important;
    line-height:1.2!important;
    letter-spacing:0.01em!important;
    min-width:0!important;
    transition: all 0.2s ease !important;
}
[data-testid="stButton"] button[kind="primary"]{
    background:#2563eb!important;
    border:1px solid #2563eb!important;
    color:#ffffff!important;
    box-shadow: 0 4px 6px -1px rgba(37,99,235,0.1) !important;
}
[data-testid="stButton"] button[kind="primary"]:hover{
    background:#1d4ed8!important;
    border-color:#1d4ed8!important;
    box-shadow: 0 6px 10px -1px rgba(37,99,235,0.2) !important;
    transform: translateY(-1px);
}
[data-testid="stButton"] button[kind="secondary"]{
    background:#ffffff!important;
    border:1px solid #cbd5e1!important;
    color:#334155!important;
    box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05) !important;
}
[data-testid="stButton"] button[kind="secondary"]:hover{
    background:#f8fafc!important;
    color:#0f172a!important;
    border-color:#94a3b8!important;
}

/* Stat Cards (Metrics) */
.stat-card-row {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
    width: 100%;
    flex-wrap: wrap;
}
.stat-card-custom {
    flex: 1 1 180px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -2px rgba(0,0,0,0.02);
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 140px;
}
.stat-card-custom::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--accent, #2563eb);
    opacity: 0.8;
}
.stat-card-custom .icon-container {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--bg-accent, rgba(37,99,235,0.06));
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
}
.stat-card-custom .icon-container svg, .stat-card-custom .icon-container span {
    color: var(--accent, #2563eb);
    font-size: 16px;
    font-weight: bold;
}
.stat-card-custom .s-value-large {
    font-size: 28px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1;
    margin-bottom: 4px;
}
.stat-card-custom .s-label-sub {
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
    margin-top: 2px;
}
.sparkline-svg {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 35px;
    pointer-events: none;
    opacity: 0.75;
}

/* Control Panel / Cards styling */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 16px !important;
    padding: 20px !important;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -2px rgba(0,0,0,0.02) !important;
}

/* Headers & Titles */
.section-hdr{
    font-family:'Outfit',sans-serif;
    font-size:13px;
    font-weight:700;
    letter-spacing:0.04em;
    text-transform:uppercase;
    color:#475569;
    border-bottom:1px solid #e2e8f0;
    padding-bottom:8px;
    margin:28px 0 16px 0;
}
.page-title{
    font-family:'Outfit',sans-serif;
    font-size:24px;
    font-weight:700;
    color:#0f172a;
    margin:0 0 6px 0;
    letter-spacing:-0.02em;
    display:flex;
    align-items:center;
    gap:10px;
}
.page-subtitle{
    font-size:14px;
    color:#64748b;
    margin-bottom:24px;
    font-weight:400;
}

/* Expanders as Clean List Rows */
[data-testid="stExpander"]{
    background:#ffffff!important;
    border:1px solid #e2e8f0!important;
    border-radius:12px!important;
    margin-bottom:8px!important;
    box-shadow:0 1px 2px 0 rgba(0,0,0,0.02)!important;
    transition: all 0.2s ease !important;
}
[data-testid="stExpander"]:hover{
    border-color:#cbd5e1!important;
    box-shadow:0 4px 12px -2px rgba(0,0,0,0.04)!important;
}
[data-testid="stExpander"] summary{
    background:#ffffff!important;
    color:#1e293b!important;
    font-size:14px!important;
    font-weight:500!important;
    font-family:'Outfit',sans-serif!important;
    padding: 12px 16px !important;
}
[data-testid="stExpander"] summary *{
    color:#1e293b!important;
}
[data-testid="stExpander"] svg{
    stroke:#64748b!important;
}
[data-testid="stExpander"] div,[data-testid="stExpander"] section,
[data-testid="stExpanderDetails"],[data-testid="stExpanderDetails"] div{
    background:#ffffff!important;
}
[data-testid="stExpander"] p{
    color:#475569!important;
}
[data-testid="stExpander"] strong,[data-testid="stExpander"] b{
    color:#0f172a!important;
}

.main h1,.main h2,.main h3,.main h4{color:#0f172a!important;font-family:'Outfit',sans-serif!important;}
.stMarkdown p,.stMarkdown span,.stMarkdown li{color:#475569!important;}
.stCaption,[data-testid="stCaptionContainer"]{color:#64748b!important;}
code{background:#f1f5f9!important;color:#2563eb!important;border-radius:4px!important;
    font-family:'IBM Plex Mono',monospace!important;font-size:11.5px!important;}
hr{border-color:#e2e8f0!important;}

/* Inputs & Form controls */
[data-testid="stSelectbox"]>div>div{
    background:#ffffff!important;
    border:1px solid #cbd5e1!important;
    color:#0f172a!important;
    border-radius:8px!important;
    font-size:13px!important;
    height:34px!important;
    min-height:34px!important;
    font-family:'Outfit',sans-serif!important;
    transition: all 0.2s ease !important;
}
[data-testid="stSelectbox"]>div>div:focus-within{
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
}
[data-testid="stSelectbox"] span{color:#0f172a!important;}
[data-testid="stSelectbox"] svg{fill:#64748b!important;}
[data-baseweb="popover"],[data-baseweb="menu"],[data-baseweb="select"] ul{
    background:#ffffff!important;
    border:1px solid #e2e8f0!important;
    border-radius:10px!important;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05)!important;
}
[data-baseweb="menu"] li,[data-baseweb="option"],[role="option"]{
    background:#ffffff!important;
    color:#334155!important;
    font-size:13px!important;
    font-family:'Outfit',sans-serif!important;
}
[data-baseweb="option"]:hover,[role="option"]:hover,[aria-selected="true"][role="option"]{
    background:#f1f5f9!important;
    color:#2563eb!important;
}
[data-testid="stTextInput"] input{
    background:#ffffff!important;
    border:1px solid #cbd5e1!important;
    color:#0f172a!important;
    border-radius:8px!important;
    font-size:13px!important;
    height:34px!important;
    font-family:'Outfit',sans-serif!important;
}
[data-testid="stTextInput"] input::placeholder{color:#94a3b8!important;}
[data-testid="stMetricValue"]{color:#0f172a!important;font-family:'IBM Plex Mono',monospace!important;font-size:24px!important;}
[data-testid="stMetricLabel"] p{color:#64748b!important;font-size:11px!important;}

/* Diff Area Light Theme */
.diff-area {
    background:#f8fafc!important;
    border:1px solid #e2e8f0!important;
    border-radius:12px!important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02) !important;
}
.diff-line{
    font-family:'IBM Plex Mono',monospace;
    font-size:12px;
    padding:4px 12px;
    margin:2px 0;
    border-radius:6px;
    white-space:pre-wrap;
    word-break:break-all;
    line-height:1.7;
    display:flex;
    gap:10px;
    align-items:baseline;
}
.diff-gutter{flex-shrink:0;width:12px;text-align:center;font-size:13px;font-weight:700;user-select:none;color:#94a3b8;}
.diff-added{background:#f0fdf4!important;border-left:4px solid #22c55e!important;color:#15803d!important;}
.diff-removed{background:#fef2f2!important;border-left:4px solid #ef4444!important;color:#b91c1c!important;}
.diff-context{background:transparent!important;color:#475569!important;border-left:4px solid #e2e8f0!important;}
ins.word{background:#dcfce7;color:#15803d;border-radius:3px;padding:1px 4px;font-weight:600;text-decoration:none;}
del.word{background:#fee2e2;color:#b91c1c;border-radius:3px;padding:1px 4px;font-weight:600;text-decoration:none;}
.diff-badge-added{background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:6px;
    padding:2px 10px;font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;}
.diff-badge-removed{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:6px;
    padding:2px 10px;font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;}

/* Banners (Crawler Running States) */
.running-banner{
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%) !important;
    border: 1px solid #bbf7d0 !important;
    border-radius: 12px;
    padding: 14px 20px;
    font-size: 14px;
    color: #166534;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 20px;
    box-shadow: 0 4px 12px rgba(22,101,52,0.04);
    justify-content: space-between;
    font-family: 'Outfit', sans-serif !important;
}
.running-banner .left {display:flex;align-items:center;gap:12px;}
.running-banner .title{font-size:15px;font-weight:700;color:#14532d;}
.running-banner .meta{font-size:12px;color:#166534;font-weight:500;}
.running-banner .progress{height:8px;border-radius:6px;background:rgba(0,0,0,0.04);overflow:hidden;width:220px}
.running-banner .progress > i{display:block;height:100%;background:linear-gradient(90deg,#22c55e,#3b82f6);width:0%;transition:width 600ms ease;}

.login-wait-banner{
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important;
    border: 1px solid #fde68a !important;
    border-radius: 12px;
    padding: 14px 20px;
    font-size: 14px;
    color: #92400e;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 20px;
    box-shadow: 0 4px 12px rgba(146,64,14,0.04);
    font-family: 'Outfit', sans-serif !important;
}
.spinner-ring {
    display: inline-block;
    width: 14px;
    height: 14px;
    background: #22c55e;
    border-radius: 50%;
    position: relative;
    flex-shrink: 0;
}
.spinner-ring::after {
    content: '';
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    background: #22c55e;
    animation: pulseGreen 1.6s infinite ease-in-out;
}
@keyframes pulseGreen {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.5); opacity: 0; }
}

.spinner-ring-amber {
    display: inline-block;
    width: 14px;
    height: 14px;
    background: #d97706;
    border-radius: 50%;
    position: relative;
    flex-shrink: 0;
}
.spinner-ring-amber::after {
    content: '';
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    background: #d97706;
    animation: pulseAmber 1.6s infinite ease-in-out;
}
@keyframes pulseAmber {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.5); opacity: 0; }
}

.banner-text{display:flex;flex-direction:column;gap:2px;}
.banner-title{font-size:14px;font-weight:700;}
.banner-sub{font-size:12px;font-weight:400;opacity:0.85;}
.idle-banner{
    background:#ffffff;
    border:1px solid #e2e8f0;
    border-radius:10px;
    padding:12px 16px;
    font-size:13px;
    color:#64748b;
    font-weight:500;
    display:flex;
    align-items:center;
    gap:8px;
    margin-bottom:16px;
    box-shadow: 0 1px 2px 0 rgba(0,0,0,0.02);
}

[data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;}
@media(max-width:768px){[data-testid="column"]{min-width:180px!important;flex:1 1 auto!important;}}
.logout-col [data-testid="stButton"]{display:flex;justify-content:flex-end;}
.logout-col [data-testid="stButton"] button{white-space:nowrap;padding:6px 20px!important;font-size:13px!important;}

/* Navigation pill tab styles (oval shape like the first image) */
[data-testid="stHorizontalBlock"] div:has(>button[key^="nav_"]) {
    display: flex;
    justify-content: center;
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
            return "↓ " + url.split("__DROPDOWN_")[-1].replace("_", " ").title()
        if "__PAGE_" in url:
            return url.split("__PAGE_")[-1].replace("_", " ").title()
        if "#/plastic/home/" in url.lower():
            name = url.lower().split("#/plastic/home/")[-1]
            return name.replace("/", " › ").replace("-", " ").replace("_", " ").title()
        if url.endswith("/plastic/home") or "/#/plastic/home" in url:
            return "Home Page"
        low = url.lower()
        if "cpcb.nic.in" in low:
            if "index.php" in low or low.rstrip("/").endswith("cpcb.nic.in"):
                return "Home Page"
            path = low.split("cpcb.nic.in/", 1)[-1].split("?")[0].strip("/")
            if path:
                return path.replace("/", " › ").replace("-", " ").replace("_", " ").title()
        slug = url.rstrip("/").split("/")[-1].split("#")[-1]
        return slug.replace("_", " ").replace("-", " ").title() or "Home Page"
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

# ── UPDATED: EPR USEDOIL added ─────────────────────────────────────────────
PORTAL_CRAWLER_MAP = {
    "EPR PLASTIC":  "crawler.py",
    "EPR EWASTE":   "crawler_ewaste.py",
    "EPR BATTERY":  "crawler_battery.py",
    "EPR TYRES":    "crawler_tyres.py",
    "EPR USEDOIL":  "crawler_usedoil.py",
    "EPR ELV":      "crawler_elv.py",
    "CPCB NIC":     "crawler_cpcb_nic.py",
}


def launch_crawl(portal=None):
    if portal and portal in PORTAL_CRAWLER_MAP:
        script = PORTAL_CRAWLER_MAP[portal]
        cmd    = [sys.executable, script, "--once"]
    elif portal:
        cmd = [sys.executable, "crawler.py", "--once", "--portal", portal]
    else:
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


CPCB_FILE_SUFFIXES = (".php", ".html", ".htm", ".asp", ".aspx", ".jsp")


def normalize_cpcb_url(url):
    """cpcb.nic.in needs trailing slash on directory paths (not on index.php)."""
    if not url or "cpcb.nic.in" not in url.lower():
        return url
    base = url.split("#")[0].split("?")[0]
    if base != "/" and not base.endswith("/"):
        if not any(base.lower().endswith(ext) for ext in CPCB_FILE_SUFFIXES):
            return base + "/"
    return base


def get_baselines_for_page(portal, url, limit=2):
    """Fetch baseline rows; for CPCB NIC also try slash-normalized URL."""
    rows = query_db(
        "SELECT * FROM baselines WHERE portal=? AND url=? ORDER BY updated_at DESC LIMIT ?",
        (portal, url, limit),
    )
    if rows or portal != "CPCB NIC":
        return rows
    alt = normalize_cpcb_url(url)
    if alt != url:
        rows = query_db(
            "SELECT * FROM baselines WHERE portal=? AND url=? ORDER BY updated_at DESC LIMIT ?",
            (portal, alt, limit),
        )
    if not rows and url.endswith("/"):
        rows = query_db(
            "SELECT * FROM baselines WHERE portal=? AND url=? ORDER BY updated_at DESC LIMIT ?",
            (portal, url.rstrip("/"), limit),
        )
    return rows


def get_portal_tracked_pages(portal):
    """Latest screenshot baseline per URL for a portal."""
    return query_db(
        """
        SELECT b.portal, b.url, b.screenshot_path, b.updated_at
        FROM baselines b
        INNER JOIN (
            SELECT url, MAX(id) AS max_id
            FROM baselines
            WHERE portal = ?
              AND screenshot_path IS NOT NULL
              AND screenshot_path != ''
            GROUP BY url
        ) t ON b.id = t.max_id
        WHERE b.portal = ?
        ORDER BY
            CASE WHEN b.url LIKE '%index.php%' THEN 0 ELSE 1 END,
            b.url
        """,
        (portal, portal),
    )


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

    # ── Stat cards ─────────────────────────────────────────────────────────────
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
        "<div class='page-title'>📸 Page Screenshots</div>"
        "<div class='page-subtitle'>Before / after screenshots — select any tracked page</div>",
        unsafe_allow_html=True
    )

    changed_url_set = {c["url"] for c in latest_changes}
    active_portal   = portal_filter or st.session_state.portal

    if active_portal and active_portal != "All Portals":
        tracked_pages = get_portal_tracked_pages(active_portal)
        if not tracked_pages:
            st.warning(
                f"No screenshots for **{active_portal}** yet. Click **▶ Run** to start a crawl."
            )
        else:
            f1, f2 = st.columns([2, 3])
            with f1:
                page_filter = st.radio(
                    "Show",
                    ["All tracked pages", "Changed only"],
                    horizontal=True,
                    key="ss_page_filter",
                )
            with f2:
                search_q = st.text_input(
                    "Search page",
                    placeholder="e.g. Introduction, Standards, Home…",
                    key="ss_search",
                )

            if page_filter == "Changed only":
                tracked_pages = [p for p in tracked_pages if p["url"] in changed_url_set]

            if search_q:
                q = search_q.lower()
                tracked_pages = [
                    p for p in tracked_pages
                    if q in friendly_page_name(p["url"]).lower() or q in p["url"].lower()
                ]

            if not tracked_pages:
                st.info("No pages match this filter. Try **All tracked pages** or clear search.")
            else:

                def page_label(row):
                    name = friendly_page_name(row["url"])
                    if row["url"] in changed_url_set:
                        return f"[{active_portal}] {name} 🔔"
                    return f"[{active_portal}] {name}"

                urls         = [p["url"] for p in tracked_pages]
                labels       = [page_label(p) for p in tracked_pages]
                sel_label    = st.selectbox(
                    f"Select page ({len(urls)} tracked)",
                    labels,
                    key="ss_page_select",
                )
                selected_url = urls[labels.index(sel_label)]
                display_url  = (
                    normalize_cpcb_url(selected_url)
                    if active_portal == "CPCB NIC"
                    else selected_url
                )

                st.markdown(
                    "<hr style='margin:8px 0 16px;border-color:#1a1f2e'>",
                    unsafe_allow_html=True,
                )

                baseline = get_baselines_for_page(active_portal, selected_url, limit=2)
                page_changes = query_db(
                    "SELECT * FROM changes WHERE portal=? AND url IN (?, ?) "
                    "ORDER BY timestamp DESC",
                    (active_portal, selected_url, display_url),
                )
                latest_b = baseline[0] if len(baseline) > 0 else None
                prev_b   = baseline[1] if len(baseline) > 1 else None

                st.markdown(
                    f"<div class='page-title' style='font-size:17px'>"
                    f"{friendly_page_name(selected_url)}"
                    f" <span style='font-size:12px;color:#a78bfa;font-weight:500'>"
                    f"[{active_portal}]</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption(display_url)

                sc1, sc2 = st.columns(2)
                with sc1:
                    st.markdown("**⬅️ Previous snapshot**")
                    if prev_b:
                        p = prev_b.get("screenshot_path")
                        if p and os.path.exists(p):
                            st.image(p, use_container_width=True)
                        else:
                            st.info("Not available")
                    else:
                        st.info("No previous snapshot (first crawl for this page)")
                with sc2:
                    st.markdown("**➡️ Latest snapshot**")
                    if latest_b:
                        p = latest_b.get("screenshot_path")
                        if p and os.path.exists(p):
                            st.image(p, use_container_width=True)
                        else:
                            st.info("Not available")
                    else:
                        st.info("No latest snapshot")

                if page_changes:
                    st.markdown("---")
                    for change in page_changes[:3]:
                        icon, label = DIFF_LABELS.get(change["diff_type"], ("❓", "?"))
                        with st.expander(f"{icon} {label} change", expanded=True):
                            try:
                                detail = json.loads(change["diff_detail"])
                                if change["diff_type"] == "html":
                                    render_html_change(detail)
                                elif change["diff_type"] == "visual":
                                    st.info(
                                        f"Appearance changed by "
                                        f"{detail.get('change_ratio', 0) * 100:.1f}%"
                                    )
                            except Exception:
                                st.info("Details unavailable.")

    elif not latest_changes:
        st.info(
            "Select a portal from the top dropdown (e.g. **CPCB NIC**) "
            "to browse all tracked page screenshots."
        )
    else:
        changed_urls = list({c["url"] for c in latest_changes})

        def url_label(url):
            chg = next((c for c in latest_changes if c["url"] == url), {})
            p   = chg.get("portal", "")
            return f"[{p}] {friendly_page_name(url)}" if p else friendly_page_name(url)

        labels       = [url_label(u) for u in changed_urls]
        sel_label    = st.selectbox(f"Select page ({len(changed_urls)} changed)", labels)
        selected_url = changed_urls[labels.index(sel_label)]
        chg_portal   = next(
            (c["portal"] for c in latest_changes if c["url"] == selected_url),
            None,
        )

        st.markdown("<hr style='margin:8px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)

        baseline = query_db(
            "SELECT * FROM baselines WHERE portal=? AND url=? ORDER BY updated_at DESC LIMIT 2",
            (chg_portal, selected_url),
        ) if chg_portal else query_db(
            "SELECT * FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2",
            (selected_url,),
        )
        page_changes = query_db(
            "SELECT * FROM changes WHERE url=? ORDER BY timestamp DESC",
            (selected_url,),
        )
        latest_b = baseline[0] if len(baseline) > 0 else None
        prev_b   = baseline[1] if len(baseline) > 1 else None
        chg_portal = chg_portal or (page_changes[0]["portal"] if page_changes else "—")

        st.markdown(
            f"<div class='page-title' style='font-size:17px'>{friendly_page_name(selected_url)}"
            f" <span style='font-size:12px;color:#a78bfa;font-weight:500'>[{chg_portal}]</span></div>",
            unsafe_allow_html=True,
        )

        sc1, sc2 = st.columns(2)
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
            icon, label = DIFF_LABELS.get(change["diff_type"], ("❓", "?"))
            with st.expander(f"{icon} {label} change", expanded=True):
                try:
                    detail = json.loads(change["diff_detail"])
                    if change["diff_type"] == "html":
                        render_html_change(detail)
                    elif change["diff_type"] == "visual":
                        st.info(f"Appearance changed by {detail.get('change_ratio', 0) * 100:.1f}%")
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
            color = "#8899b4"
        escaped = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f"<span style='color:{color}'>{escaped}</span>"

    colored_lines = [colorize(l) for l in log_lines]
    log_html = "<br>".join(colored_lines)

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