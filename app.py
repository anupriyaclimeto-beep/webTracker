import streamlit as st
import re
import sqlite3
import json
import os
import requests
from difflib import unified_diff
import html as _html
import subprocess
import sys
import time
from contextlib import contextmanager
import threading
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ── BUILT-IN SCHEDULER ─────────────────────────────────────────────────────────
@st.cache_resource
def start_background_scheduler():
    def run_schedule():
        last_run = {}
        target_times = ["07:00", "15:00", "15:10", "15:20", "15:30", "22:00"]
        import datetime as dt
        ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
        while True:
            now          = dt.datetime.now(ist)
            current_time = now.strftime("%H:%M")
            if current_time in target_times and last_run.get(current_time) != now.date():
                last_run[current_time] = now.date()
                print(f"[{now}] In-app scheduler triggered for {current_time}!")
                try:
                    root = Path(__file__).parent
                    cmd  = [sys.executable, str(root / "cron_tasks.py"), "start_crawl"]
                    subprocess.Popen(cmd, cwd=str(root))
                except Exception as e:
                    print(f"[{now}] In-app scheduler failed: {e}")
            time.sleep(30)

    t = threading.Thread(target=run_schedule, daemon=True)
    t.start()
    return t

start_background_scheduler()

# ── CONFIG ────────────────────────────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)

DB_PATH     = config["storage"]["db"]
ARCHIVE_DIR = config["storage"]["archive_dir"]

# ── ENVIRONMENT / CLOUD DETECTION ─────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
IS_CLOUD = os.getenv("STREAMLIT_SHARING_MODE") is not None or os.path.exists("/mount/src")
AUTH_FLAG = os.path.join(Path(__file__).parent, ".user_logged_in")

def _secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

SUPABASE_HOST         = _secret("SUPABASE_HOST")
SUPABASE_PORT         = _secret("SUPABASE_PORT")
SUPABASE_DB           = _secret("SUPABASE_DB")
SUPABASE_USER         = _secret("SUPABASE_USER")
SUPABASE_PWD          = _secret("SUPABASE_PASSWORD")
SUPABASE_SERVICE_ROLE = _secret("SUPABASE_SERVICE_ROLE_KEY")

USE_SUPABASE = all([
    SUPABASE_HOST, SUPABASE_PORT, SUPABASE_DB, SUPABASE_USER,
    SUPABASE_PWD or SUPABASE_SERVICE_ROLE,
])

if USE_SUPABASE:
    import psycopg2
    import psycopg2.pool
    from psycopg2.extras import RealDictCursor
    _DSN = (
        f"host={SUPABASE_HOST} port={SUPABASE_PORT} dbname={SUPABASE_DB} "
        f"user={SUPABASE_USER} password={SUPABASE_SERVICE_ROLE or SUPABASE_PWD} sslmode=require"
    )

    @st.cache_resource
    def get_connection_pool():
        return psycopg2.pool.ThreadedConnectionPool(1, 15, _DSN)


def get_portal_config(portal_name):
    try:
        for p in config.get("portals", []):
            if p.get("name") == portal_name:
                return p
    except Exception:
        pass
    return None

st.set_page_config(
    page_title="Portal Change Monitor — CPCB EPR Web Tracker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
.hdr-title {
    padding:8px 0 6px;
    font-family:"IBM Plex Mono",monospace;
    font-size:15px;
    font-weight:600;
    letter-spacing:0.02em;
    color:#000000 !important;
    display:flex;
    align-items:center;
    gap:4px;
}

/* Navigation pill tab styles (oval shape like the first image) */
[data-testid="stHorizontalBlock"] div:has(>button[key^="nav_"]) {
    display: flex;
    justify-content: center;
}
</style>
""", unsafe_allow_html=True)


# ── DB ────────────────────────────────────────────────────────────────────────
def init_db():
    if USE_SUPABASE:
        return
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS crawl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
            pages_visited INTEGER DEFAULT 0, status TEXT DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL, url TEXT NOT NULL, diff_type TEXT NOT NULL,
            diff_detail TEXT, timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal TEXT NOT NULL, url TEXT NOT NULL,
            html_path TEXT, screenshot_path TEXT, har_path TEXT, updated_at TEXT NOT NULL
        );
    """)
    for col in ["screenshot_url", "html_url"]:
        for table in ["changes", "baselines"]:
            cur.execute(f"PRAGMA table_info({table})")
            if col not in {row[1] for row in cur.fetchall()}:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    # UI-only hidden changes table (stores IDs of changes hidden from UI)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hidden_changes (
            change_id INTEGER PRIMARY KEY,
            hidden_at TEXT NOT NULL
        );
    """)
    conn.commit(); conn.close()

init_db()

def _pg_query_to_sqlite(query):
    q = query.replace("?", "%s")
    q = q.replace("started_at >= datetime('now','-15 minutes')", "CAST(started_at AS timestamp) >= NOW() - INTERVAL '15 minutes'")
    q = q.replace("started_at >= datetime('now', '-15 minutes')", "CAST(started_at AS timestamp) >= NOW() - INTERVAL '15 minutes'")
    q = q.replace("started_at < datetime('now','-15 minutes')",  "CAST(started_at AS timestamp) < NOW() - INTERVAL '15 minutes'")
    q = q.replace("started_at < datetime('now', '-15 minutes')", "CAST(started_at AS timestamp) < NOW() - INTERVAL '15 minutes'")
    q = q.replace("datetime('now')", "NOW()")
    return q

def query_db(query, args=()):
    try:
        if USE_SUPABASE:
            pool = get_connection_pool()
            conn = pool.getconn()
            returned = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(_pg_query_to_sqlite(query), args)
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                returned = True
                conn = pool.getconn(); returned = False
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(_pg_query_to_sqlite(query), args)
                    return [dict(r) for r in cur.fetchall()]
            finally:
                if not returned:
                    try:
                        pool.putconn(conn)
                    except Exception:
                        pass
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, args)
            rows = cur.fetchall()
            conn.close()
            return [dict(r) for r in rows]
    except Exception as e:
        st.error(f"DB error: {e}")
        return []

def exec_db(query, args=()):
    try:
        if USE_SUPABASE:
            pool = get_connection_pool()
            conn = pool.getconn(); returned = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(_pg_query_to_sqlite(query), args)
                    conn.commit()
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                try: pool.putconn(conn, close=True)
                except Exception: pass
                returned = True
                conn = pool.getconn(); returned = False
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(_pg_query_to_sqlite(query), args)
                    conn.commit()
            finally:
                if not returned:
                    try: pool.putconn(conn)
                    except Exception: pass
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(query, args)
            conn.commit(); conn.close()
    except Exception:
        pass


# ── HELPERS ───────────────────────────────────────────────────────────────────
def time_ago(ts):
    try:
        diff = datetime.now() - (ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)))
        s = int(diff.total_seconds())
        if s < 60:    return "just now"
        if s < 3600:  return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{diff.days}d ago"
    except Exception: return str(ts)


def friendly_page_name(url):
    """Convert internal URL keys to human-readable page names."""
    try:
        # Post-login pages — show lock icon
        if "__LOGGEDIN_" in url:
            return "🔐 " + url.split("__LOGGEDIN_")[-1].replace("_", " ").title()
        if "__DROPDOWN_" in url:
            return "↓ " + url.split("__DROPDOWN_")[-1].replace("_", " ").title()
        if "__PAGE_" in url:
            return url.split("__PAGE_")[-1].replace("_", " ").title()
        if "#/plastic/home/" in url.lower():
            name = url.lower().split("#/plastic/home/")[-1]
            return name.replace("/", " › ").replace("-", " ").replace("_", " ").title()
        if url.endswith("/plastic/home") or "/#/plastic/home" in url:
            return "Home Page"
        slug = url.rstrip("/").split("/")[-1].split("#")[-1]
        return slug.replace("_", " ").replace("-", " ").title() or "Home Page"
    except Exception:
        return url


DIFF_LABELS = {
    "html":   ("📄", "Content"),
    "visual": ("🖼️", "Visual"),
    "json":   ("📊", "Data"),
    "har":    ("🔌", "API"),
}

def severity_badge(diff_lines):
    if diff_lines > 50: return "🔴 High",   "High"
    if diff_lines > 10: return "🟡 Medium", "Medium"
    return "🟢 Low", "Low"


# ── Crawler state helpers ──────────────────────────────────────────────────────
IS_CLOUD_APP  = os.getenv("STREAMLIT_SHARING_MODE") is not None or os.path.exists("/mount/src")
_BASE_APP_DIR = os.path.dirname(os.path.abspath(__file__)) or "."

if IS_CLOUD_APP:
    PID_FILE   = "/tmp/.crawler.pid"
    LOG_FILE   = "/tmp/.crawler.log"
    LOGIN_FLAG = "/tmp/.login_needed"
else:
    PID_FILE   = os.path.join(_BASE_APP_DIR, ".crawler.pid")
    LOG_FILE   = os.path.join(_BASE_APP_DIR, ".crawler.log")
    LOGIN_FLAG = os.path.join(_BASE_APP_DIR, ".login_needed")


def is_waiting_for_login() -> bool:
    """True when crawler has opened a headful browser and is waiting for manual login."""
    return os.path.exists(LOGIN_FLAG)


def is_crawl_running():
    rows = query_db(
        "SELECT id,portal,started_at,pages_visited FROM crawl_log "
        "WHERE status='running' AND started_at >= datetime('now','-15 minutes') "
        "ORDER BY started_at DESC LIMIT 1"
    )
    if not rows:
        return None
    row = rows[0]
    try:
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
            except Exception:
                pid = None

            def process_running(pid_val):
                try:
                    if sys.platform == "win32":
                        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid_val}"],
                                                      stderr=subprocess.DEVNULL, text=True)
                        return str(pid_val) in out
                    else:
                        proc = subprocess.run(["ps", "-p", str(pid_val)],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return proc.returncode == 0
                except Exception:
                    return False

            if pid and process_running(pid):
                return row
            try: os.remove(PID_FILE)
            except Exception: pass
            try:
                exec_db("UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE id=?",
                        (row["id"],))
            except Exception: pass
            return None
        else:
            try:
                exec_db("UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE id=?",
                        (row["id"],))
            except Exception: pass
            return None
    except Exception:
        return row


def fix_stale_crawls():
    try:
        exec_db("UPDATE crawl_log SET status='done' WHERE status='running' AND started_at < datetime('now','-15 minutes')")
    except Exception: pass


def tee_output(pipe, log_file, is_stderr=False):
    try:
        with open(log_file, "a", encoding="utf-8", errors="replace") as f:
            for line in iter(pipe.readline, ""):
                f.write(line)
                f.flush()
                if is_stderr:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()
    except Exception as e:
        print(f"Error in logging tee: {e}")


def launch_crawl(portal=None):
    cmd = [sys.executable, "crawler.py", "--once"]
    if portal:
        cmd.extend(["--portal", portal])
    env = os.environ.copy()
    if IS_CLOUD_APP:
        for k in st.secrets.keys():
            try: env[k] = str(st.secrets[k])
            except Exception: pass
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
    
    # Reset log file
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_BASE_APP_DIR,
            env=env
        )
        
        t1 = threading.Thread(target=tee_output, args=(proc.stdout, LOG_FILE, False), daemon=True)
        t2 = threading.Thread(target=tee_output, args=(proc.stderr, LOG_FILE, True), daemon=True)
        t1.start()
        t2.start()
        
        with open(PID_FILE, "w") as f: f.write(str(proc.pid))
    except Exception as e:
        print(f"Failed to launch crawl: {e}")


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
            with open(PID_FILE) as f: pid = int(f.read().strip())
            import signal
            if sys.platform == "win32":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE); killed = True
    except Exception: pass
    # Clean up login flag if crawler was stopped mid-login
    try:
        if os.path.exists(LOGIN_FLAG):
            os.remove(LOGIN_FLAG)
    except Exception: pass
    try:
        exec_db("UPDATE crawl_log SET status='stopped', finished_at=datetime('now') WHERE status='running'")
    except Exception: pass
    return killed


def clear_portal_profile(portal_name: str) -> bool:
    """Delete the persistent browser profile — forces re-login on next run."""
    portal_cfg = get_portal_config(portal_name)
    if not portal_cfg:
        return False
    try:
        from auth import clear_profile
        return clear_profile(portal_cfg)
    except Exception as e:
        st.error(f"Could not clear profile: {e}")
        return False


# ── DATA ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_all_portals():
    configured = [p["name"] for p in config.get("portals", [])]
    db_portals = [r["portal"] for r in query_db("SELECT DISTINCT portal FROM crawl_log")]
    all_p = list(configured)
    for p in db_portals:
        if p not in all_p:
            all_p.append(p)
    return all_p

@st.cache_data(ttl=30)
def get_portal_stats(portal=None):
    and_clause = "AND cl.portal = ?" if portal else ""
    args       = (portal,) if portal else ()
    db_stats   = query_db(f"""
        SELECT cl.portal, cl.started_at AS last_crawl_at, cl.pages_visited,
               cl.status AS last_status,
               COALESCE(td.today_changes,0) AS today_changes,
               COALESCE(at_.all_changes,0)  AS all_time_changes
        FROM crawl_log cl
        LEFT JOIN (SELECT portal,COUNT(*) AS today_changes FROM changes
                   WHERE date(timestamp)=date('now') GROUP BY portal) td ON td.portal=cl.portal
        LEFT JOIN (SELECT portal,COUNT(*) AS all_changes FROM changes GROUP BY portal) at_ ON at_.portal=cl.portal
        WHERE cl.id IN (SELECT MAX(id) FROM crawl_log GROUP BY portal)
        {and_clause} ORDER BY cl.portal
    """, args)
    stats_map         = {s["portal"]: s for s in db_stats}
    configured_portals = config.get("portals", [])
    if portal:
        configured_portals = [p for p in configured_portals if p["name"] == portal]
    merged = []
    for p in configured_portals:
        name = p["name"]
        merged.append(stats_map[name] if name in stats_map else {
            "portal": name, "last_crawl_at": None, "pages_visited": 0,
            "last_status": "never", "today_changes": 0, "all_time_changes": 0,
        })
    for name, s in stats_map.items():
        if name not in [p["name"] for p in configured_portals]:
            merged.append(s)
    return merged

@st.cache_data(ttl=300)
def get_latest_crawl_changes(portal=None):
    """Return recent changes for the portal (last N minutes) to avoid timezone/run-window issues."""
    recent_minutes = 180  # last 3 hours; adjust if you need longer window
    # Fetch rows (same logic for portal and global)
    if portal:
        if USE_SUPABASE:
            rows = query_db(
                "SELECT * FROM public.changes WHERE portal=%s AND timestamp >= NOW() - INTERVAL '%s minutes' ORDER BY timestamp DESC LIMIT 500",
                (portal, recent_minutes)
            )
        else:
            rows = query_db(
                "SELECT * FROM changes WHERE portal=? AND timestamp>=datetime('now','-%d minutes') ORDER BY timestamp DESC LIMIT 500" % recent_minutes,
                (portal,)
            )
    else:
        if USE_SUPABASE:
            rows = query_db(
                "SELECT * FROM public.changes WHERE timestamp >= NOW() - INTERVAL '%s minutes' ORDER BY timestamp DESC LIMIT 500",
                (recent_minutes,)
            )
        else:
            rows = query_db(
                "SELECT * FROM changes WHERE timestamp>=datetime('now','-%d minutes') ORDER BY timestamp DESC LIMIT 500" % recent_minutes,
                ()
            )

    # Filter out noisy/low-confidence changes and trivial visual diffs
    try:
        threshold = float(config.get("diff", {}).get("noise_confidence_threshold", 0.6))
    except Exception:
        threshold = 0.6
    visual_min = float(config.get("diff", {}).get("visual_change_min_ratio", config.get("diff", {}).get("pixel_threshold", 0.05)))
    filtered = []
    for r in rows:
        try:
            detail = r.get("diff_detail") or {}
            if isinstance(detail, str):
                detail = json.loads(detail or "{}")
        except Exception:
            detail = {}
        is_noise = bool(detail.get("is_noise"))
        conf = detail.get("confidence")
        try:
            conf = float(conf) if conf is not None else None
        except Exception:
            conf = None
        # Skip if explicitly marked noise or low confidence
        if is_noise:
            continue
        if conf is not None and conf < threshold:
            continue
        # For visual diffs, skip trivial/zero-pixel changes or below visual_min
        if r.get("diff_type") == "visual":
            try:
                ratio = float(detail.get("change_ratio") or 0.0)
            except Exception:
                ratio = 0.0
            changed_pixels = int(detail.get("changed_pixels") or 0)
            if changed_pixels == 0 or ratio <= visual_min:
                continue
        filtered.append(r)
    # Further restrict to only pages with a visible/meaningful change.
    visible = []
    text_min_words = int(config.get("diff", {}).get("text_change_min_words", 5) or 5)
    text_min_lines = int(config.get("diff", {}).get("text_line_min_changes", 3) or 3)
    for r in filtered:
        try:
            dtype = r.get("diff_type")
            detail = r.get("diff_detail") or {}
            if isinstance(detail, str):
                detail = json.loads(detail or "{}")
        except Exception:
            detail = {}
            dtype = r.get("diff_type")
        visible_flag = False
        if dtype == "visual":
            try:
                pixels = int(detail.get("changed_pixels") or 0)
                ratio = float(detail.get("change_ratio") or 0.0)
            except Exception:
                pixels = 0; ratio = 0.0
            if pixels > 0 and ratio > visual_min:
                visible_flag = True
        elif dtype == "html":
            try:
                words = int(detail.get("words_changed") or 0)
                lines = int(detail.get("diff_lines") or 0)
            except Exception:
                words = 0; lines = 0
            highlighted = detail.get("highlighted_lines") or []
            # Only consider HTML changes visible if there are actual visible text differences:
            # - word count changed above threshold, OR
            # - line changes above threshold, OR
            # - explicit highlighted lines (word-level highlights)
            # Do NOT treat structural-only changes (e.g., added empty <tr> or attribute changes) as visible.
            if words >= text_min_words or lines >= text_min_lines or (highlighted and len(highlighted) > 0):
                visible_flag = True
        elif dtype in ("json", "har"):
            # treat API/data/har changes as visible if there are added/removed entries
            if detail:
                if dtype == "har":
                    new_ep = detail.get("new_endpoints") or []
                    rem_ep = detail.get("removed_endpoints") or []
                    if new_ep or rem_ep:
                        visible_flag = True
                else:
                    # json/data diffs: consider non-empty diff_detail as visible
                    visible_flag = True
        if visible_flag:
            visible.append(r)
    return visible

@st.cache_data(ttl=30)
def get_crawl_history(portal=None, limit=50):
    if portal:
        return query_db("SELECT * FROM crawl_log WHERE portal=? ORDER BY started_at DESC LIMIT ?", (portal, limit))
    return query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT ?", (limit,))


# ── DIFF RENDERERS ────────────────────────────────────────────────────────────
def render_highlighted_html_diff(detail):
    highlighted_lines = detail.get("highlighted_lines", [])
    summary           = detail.get("summary", "")
    if not highlighted_lines:
        if summary: st.info(f"💬 {summary}")
        return

    def is_noise_line(line):
        html = (line.get("html") or "").lower()
        text = (line.get("text") or "").strip()
        if "data:image" in html or "base64" in html: return True
        if re.search(r"[A-Za-z0-9+/]{80,}", html) or re.search(r"[A-Za-z0-9+/]{80,}", text): return True
        if len(text) > 80 and " " not in text: return True
        return len(re.sub(r"<[^>]+>", "", html).strip()) == 0 and len(text) == 0

    filtered = [l for l in highlighted_lines if not is_noise_line(l)]
    if not filtered:
        st.info(f"💬 {summary}  — (Rendering/noise-only changes filtered)" if summary else "No readable text changes detected.")
        return

    added_count   = sum(1 for l in highlighted_lines if l["type"] == "added")
    removed_count = sum(1 for l in highlighted_lines if l["type"] == "removed")
    badges = ""
    if added_count:   badges += f"<span class='diff-badge-added'>+{added_count} added</span>&nbsp;"
    if removed_count: badges += f"<span class='diff-badge-removed'>-{removed_count} removed</span>"

    header_html = (
        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap'>"
        f"<span style='font-family:\"IBM Plex Mono\",monospace;font-size:11.5px;color:#6a8aaa'>💬 {summary}</span>"
        f"&nbsp;{badges}</div>" if summary else f"<div style='margin-bottom:8px'>{badges}</div>"
    )
    lines_html = [header_html]
    for line in [l for l in filtered if l.get("type") in ("added", "removed")][:200]:
        typ     = line["type"]
        content = line.get("html") or line.get("text", "")
        cls     = "diff-added" if typ == "added" else "diff-removed"
        gutter  = "+" if typ == "added" else "-"
        lines_html.append(f"<div class='diff-line {cls}'><span class='diff-gutter'>{gutter}</span>{content}</div>")

    st.markdown(
        "<div class='diff-area' style='background:#05070a;border:1px solid #1a1f2e;border-radius:10px;"
        "padding:14px 16px;max-height:520px;overflow-y:auto;font-family:\"IBM Plex Mono\",monospace;"
        "font-size:12px;line-height:1.6;'>"
        + "".join(lines_html) + "</div>",
        unsafe_allow_html=True,
    )


def render_visual_diff(detail, change, baseline_path=None, current_path=None):
    ratio        = detail.get("change_ratio", 0)
    pixels       = detail.get("changed_pixels", 0)
    diff_img_path = detail.get("diff_image_path")
    st.info(f"🖼️ **{pixels:,} pixels changed ({ratio*100:.1f}%)**")
    if diff_img_path and os.path.exists(diff_img_path):
        st.markdown("**🔴 Highlighted diff — red areas show what changed:**")
        st.image(diff_img_path, use_container_width=True)
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**⬅️ Before**")
            if baseline_path and (baseline_path.startswith("http") or os.path.exists(baseline_path)):
                st.image(baseline_path, use_container_width=True)
            else:
                st.info("No baseline image")
        with c2:
            st.markdown("**➡️ After**")
            p = change.get("screenshot_url") or current_path
            if p and (p.startswith("http") or os.path.exists(p)):
                st.image(p, use_container_width=True)
            else:
                st.info("No current image")


def render_change_expander(change):
    page_name = friendly_page_name(change["url"])
    when = time_ago(change.get("timestamp"))

    try:
        detail = json.loads(change.get("diff_detail") or "{}")
        diff_lines = int(detail.get("diff_lines", 0) or 0)
        sev, sev_label = severity_badge(diff_lines)
        summary = detail.get("summary", "")
    except Exception:
        detail = {}
        diff_lines = 0
        sev, sev_label = "🟢 Low", "Low"
        summary = ""

    icon, _ = DIFF_LABELS.get(change.get("diff_type"), ("❓", ""))
    label_str = {"html": "Content", "visual": "Visual", "json": "Data", "har": "API"}.get(change.get("diff_type"), "?")
    sev_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(sev_label, "🟢")

    # Confidence badge (if available)
    try:
        confidence = float(detail.get("confidence")) if detail.get("confidence") is not None else None
    except Exception:
        confidence = None
    if confidence is not None:
        if confidence >= 0.75:
            conf_icon = "🔴 High"
        elif confidence >= 0.45:
            conf_icon = "🟡 Medium"
        else:
            conf_icon = "🟢 Low"
    else:
        conf_icon = None

    # expand by default if this is the most recent change
    try:
        most_recent = query_db("SELECT id FROM changes ORDER BY timestamp DESC LIMIT 1")
        most_recent_id = most_recent[0]["id"] if most_recent else None
    except Exception:
        most_recent_id = None
    expanded_by_default = True if most_recent_id and change.get("id") == most_recent_id else False

    title_label = (summary[:80] + "...") if summary else label_str
    with st.expander(f"{icon} [{change.get('portal')}]  {page_name} — {title_label} — {sev_icon} {sev_label} — {when}", expanded=expanded_by_default):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**Portal:** `{change.get('portal')}`")
            st.markdown(f"**Page:** {page_name}")
        with c2:
            st.markdown(f"**Severity:** {sev_label}")
            st.markdown(f"**Type:** {label_str}")
        with c3:
            ts = change.get("timestamp")
            st.markdown(f"**Detected:** {str(ts)[:16] if ts else 'N/A'}")
            if conf_icon:
                st.markdown(f"**Confidence:** {conf_icon}")

        st.markdown("---")

        dtype = change.get("diff_type")
        if dtype == "html":
            added_texts = detail.get("added_texts") or []
            removed_texts = detail.get("removed_texts") or []
            words_changed = int(detail.get("words_changed") or 0)
            lines_changed = int(detail.get("lines_changed") or 0)
            changes_sel = detail.get("changes_with_selectors") or []
            summary_text = detail.get("summary") or ""

            # Plain-English "What changed" header
            if added_texts and removed_texts:
                what_changed = f"Text changed from {removed_texts[0]} to {added_texts[0]}"
            elif added_texts:
                what_changed = f"New text appeared: {', '.join(added_texts[:5])}"
            elif removed_texts:
                what_changed = f"Text removed: {', '.join(removed_texts[:5])}"
            elif words_changed > 0:
                what_changed = f"~{words_changed} words changed (structural/attribute update)"
            else:
                what_changed = "Page structure changed — no visible text difference found"

            st.markdown(f"**What changed:** {what_changed}")
            st.markdown("---")

            highlighted = detail.get("highlighted_lines") or []
            if highlighted:
                render_highlighted_html_diff(detail)
            else:
                card_lines = []
                if summary_text:
                    card_lines.append(f"<div style='font-weight:700;margin-bottom:6px'>📄 {_html.escape(summary_text)}</div>")
                card_lines.append(f"<div style='color:#94a3b8;margin-bottom:6px'>{words_changed} words changed · {lines_changed} lines changed</div>")
                if added_texts:
                    card_lines.append("<div style='margin-top:6px'><strong>Added:</strong><ul style='margin-top:6px;margin-bottom:6px'>")
                    for a in added_texts[:10]:
                        card_lines.append(f"<li style='color:#86efac'>{_html.escape(a)}</li>")
                    card_lines.append("</ul></div>")
                if removed_texts:
                    card_lines.append("<div style='margin-top:6px'><strong>Removed:</strong><ul style='margin-top:6px;margin-bottom:6px'>")
                    for r in removed_texts[:10]:
                        card_lines.append(f"<li style='color:#fca5a5'>{_html.escape(r)}</li>")
                    card_lines.append("</ul></div>")
                if changes_sel:
                    table_html = [
                        "<div style='margin-top:8px'><strong>Locations:</strong>",
                        "<table style='width:100%;border-collapse:collapse;margin-top:8px'>",
                        "<thead><tr><th style='text-align:left;padding:6px;border-bottom:1px solid #1a1f2e'>Type</th>"
                        "<th style='text-align:left;padding:6px;border-bottom:1px solid #1a1f2e'>Text</th>"
                        "<th style='text-align:left;padding:6px;border-bottom:1px solid #1a1f2e'>Location (selector)</th></tr></thead><tbody>"
                    ]
                    for item in changes_sel[:50]:
                        t = _html.escape(str(item.get("type") or ""))
                        txt = _html.escape(str(item.get("text") or "")) or "(no text)"
                        sel = _html.escape(str(item.get("selector") or "unknown"))
                        table_html.append(f"<tr><td style='padding:6px;border-bottom:1px solid #0f1724'>{t}</td>"
                                          f"<td style='padding:6px;border-bottom:1px solid #0f1724'>{txt}</td>"
                                          f"<td style='padding:6px;border-bottom:1px solid #0f1724;font-family:monospace'>{sel}</td></tr>")
                    table_html.append("</tbody></table></div>")
                    card_lines.extend(table_html)
                st.markdown("<div style='background:#05070a;border:1px solid #1a1f2e;border-radius:8px;padding:12px;margin-bottom:8px'>"
                            + "".join(card_lines) + "</div>", unsafe_allow_html=True)

        elif dtype == "visual":
            baseline_rows = query_db("SELECT screenshot_path, screenshot_url FROM baselines WHERE url=? ORDER BY updated_at DESC LIMIT 2", (change.get("url"),))
            baseline_path = (baseline_rows[1].get("screenshot_url") or baseline_rows[1].get("screenshot_path")) if len(baseline_rows) > 1 else None
            current_path = (baseline_rows[0].get("screenshot_url") or baseline_rows[0].get("screenshot_path")) if len(baseline_rows) > 0 else None
            render_visual_diff(detail, change, baseline_path, current_path)

        elif dtype == "har":
            new_ep = detail.get("new_endpoints", []) or []
            rem_ep = detail.get("removed_endpoints", []) or []
            if new_ep:
                st.markdown(f"🟢 **{len(new_ep)} new endpoint(s)**")
                for ep in new_ep[:5]:
                    st.code(ep)
            if rem_ep:
                st.markdown(f"🔴 **{len(rem_ep)} removed endpoint(s)**")
                for ep in rem_ep[:5]:
                    st.code(ep)


# ── STARTUP CLEANUP ───────────────────────────────────────────────────────────
if not st.session_state.get("_stale_cleaned"):
    fix_stale_crawls()
    st.session_state["_stale_cleaned"] = True

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "view"   not in st.session_state: st.session_state.view   = "overview"
if "portal" not in st.session_state: st.session_state.portal = "All Portals"

all_portals    = get_all_portals()
portal_options = ["All Portals"] + all_portals
running_crawl  = is_crawl_running()
waiting_login  = is_waiting_for_login()

# If no crawl is running, but we think a manual crawl is running, check if it has actually exited
if not running_crawl and st.session_state.get("crawler_manual_running"):
    started_at_str = st.session_state.get("crawler_manual_started_at")
    if started_at_str:
        try:
            started_at = datetime.fromisoformat(started_at_str)
            elapsed = (datetime.now() - started_at).total_seconds()
            if elapsed > 10:  # If more than 10 seconds elapsed and no crawl is running in DB/process, it must have finished or crashed
                st.session_state.pop("crawler_manual_running", None)
                st.session_state.pop("crawler_manual_started_at", None)
                st.rerun()
        except Exception:
            st.session_state.pop("crawler_manual_running", None)


@st.cache_data(ttl=60)
def _get_global_counts():
    tc = (query_db("SELECT COUNT(*) as c FROM crawl_log") or [{"c": 0}])[0]["c"]
    ac = (query_db("SELECT COUNT(*) as c FROM changes")   or [{"c": 0}])[0]["c"]
    return tc, ac
total_crawls, all_time_changes = _get_global_counts()

portal_filter  = None if st.session_state.portal == "All Portals" else st.session_state.portal
latest_changes = get_latest_crawl_changes(portal_filter)

# Detect crawl finish from logs
try:
    recent_log = read_log(tail=80)
    finish_patterns = [r"all done", r"finished crawling", r"pages complete", r"crawl finished", r"crawl complete", r"ALL DONE"]
    found = any(re.search(p, ln, re.IGNORECASE) for ln in recent_log for p in finish_patterns)
    if found:
        if st.session_state.get("crawler_prev_running", False) or running_crawl:
            st.session_state.pop("crawler_manual_running", None)
            st.session_state.pop("crawler_manual_started_at", None)
            st.session_state["crawler_prev_running"] = False
            st.session_state.view = "changes"
            try:
                row = query_db("SELECT id FROM crawl_log WHERE status='running' ORDER BY started_at DESC LIMIT 1")
                if row:
                    exec_db("UPDATE crawl_log SET status='done', finished_at=datetime('now') WHERE id=?", (row[0]["id"],))
            except Exception:
                pass
            try:
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
            except Exception:
                pass
            try:
                get_latest_crawl_changes.clear()
            except Exception:
                pass
            st.success("Crawl finished (detected in logs). Showing changes.")
            st.markdown("<script>setTimeout(()=>window.location.reload(),900)</script>", unsafe_allow_html=True)
except Exception:
    pass


# ── NAVBAR ────────────────────────────────────────────────────────────────────
nav_views = [
    ("overview",    "🏠", "Overview"),
    ("changes",     "🚨", "Changes"),
    ("console",     "🖥️", "Console"),
]

def on_portal_change():
    if "top_portal_select" in st.session_state:
        st.session_state.portal = st.session_state.top_portal_select

hdr_left, hdr_nav = st.columns([1.3, 4])

with hdr_left:
    st.markdown("<div class='hdr-title'>🔍 Change Monitor</div>", unsafe_allow_html=True)

with hdr_nav:
    nav_weights = [1] * len(nav_views) + [0.6]
    nav_cols = st.columns(nav_weights)
    for col, (view_id, icon, label) in zip(nav_cols[:-1], nav_views):
        with col:
            is_active = st.session_state.view == view_id
            if st.button(f"{icon} {label}", key=f"nav_{view_id}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.view = view_id
                st.rerun()

    with nav_cols[-1]:
        if st.button("⎋ Logout", key="logout_btn", use_container_width=True):
            logout()
        st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<hr style='margin:4px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)

# ── Control panel ─────────────────────────────────────────────────────────────
if "run_warning" not in st.session_state:
    st.session_state["run_warning"] = False

with st.container(border=True):
    if st.session_state["run_warning"]:
        st.warning("⚠️ Please select a specific portal first (do not leave 'All Portals').")
        st.session_state["run_warning"] = False

    cc1, cc2, cc3 = st.columns([4, 2, 2])

    with cc1:
        st.markdown("<div style='font-size:10.5px;font-family:\"IBM Plex Mono\",monospace;color:#526d95;"
                    "text-transform:uppercase;margin-bottom:6px;letter-spacing:0.04em'>🎯 Target Portal</div>",
                    unsafe_allow_html=True)
        curr_portal = st.session_state.portal if st.session_state.portal in portal_options else "All Portals"
        st.selectbox("portal_sel", portal_options, index=portal_options.index(curr_portal),
                     label_visibility="collapsed", key="top_portal_select", on_change=on_portal_change)

    with cc2:
        st.markdown("<div style='font-size:10.5px;font-family:\"IBM Plex Mono\",monospace;color:#526d95;"
                    "text-transform:uppercase;margin-bottom:6px;letter-spacing:0.04em'>🤖 Crawler</div>",
                    unsafe_allow_html=True)
        manual_running = st.session_state.get("crawler_manual_running", False)
    if running_crawl or manual_running:
        if st.button("⏹ Stop", use_container_width=False, type="primary", key="stop_btn"):
            stop_crawl()
            st.session_state.pop("crawler_manual_running", None)
            st.session_state.pop("crawler_manual_started_at", None)
            try:
                get_latest_crawl_changes.clear()
            except Exception:
                pass
            time.sleep(1); st.rerun()
    else:
        # smaller centered run button
        st.markdown("<div style='text-align:center'>", unsafe_allow_html=True)
        if st.button("▶ Run", use_container_width=False, type="primary", key="run_btn"):
            if portal_filter is None:
                st.session_state["run_warning"] = True
                time.sleep(0.1); st.rerun()
            # Mark manual run started and launch crawler in background.
            st.session_state["crawler_manual_running"]   = True
            st.session_state["crawler_manual_started_at"] = datetime.now().isoformat()
            launch_crawl(portal_filter)
            # Do not clear global caches or force a rerun here to avoid layout shifts / loaders.
        st.markdown("</div>", unsafe_allow_html=True)

    with cc3:
        # ── Session status — for all persistent-auth portals ──────────────
        st.markdown("<div style='font-size:10.5px;font-family:\"IBM Plex Mono\",monospace;color:#526d95;"
                    "text-transform:uppercase;margin-bottom:6px;letter-spacing:0.04em'>🔐 Session</div>",
                    unsafe_allow_html=True)
        selected_portal = st.session_state.portal
        pcfg = get_portal_config(selected_portal) if selected_portal != "All Portals" else None
        if pcfg and pcfg.get("auth") == "persistent":
            profile_dir  = Path(pcfg.get("browser_profile_dir",
                               f"browser_profiles/{selected_portal.replace(' ', '_')}"))
            cookies_path = profile_dir / "cookies.json"
            profile_ok   = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False
            cookies_ok   = cookies_path.exists() and cookies_path.stat().st_size > 10 if cookies_path.exists() else False
            btn_disabled = running_crawl is not None or manual_running
            if cookies_ok:
                st.markdown("<div style='font-size:11px;color:#22c55e;margin-bottom:4px'>✅ Session saved</div>",
                            unsafe_allow_html=True)
            elif profile_ok:
                st.markdown("<div style='font-size:11px;color:#f59e0b;margin-bottom:4px'>⚠ Login needed</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size:11px;color:#94a3b8;margin-bottom:4px'>○ No session yet</div>",
                            unsafe_allow_html=True)
            btn_label = "↺ Re-login" if profile_ok else "⚙ First login"
            if st.button(btn_label, use_container_width=True, key="relogin_btn",
                         disabled=bool(btn_disabled),
                         help="Clear saved session — next crawl will open login window"):
                if clear_portal_profile(selected_portal):
                    st.success(f"Session cleared for {selected_portal}. Next crawl will open login window.")
                else:
                    st.info("No profile to clear.")
                time.sleep(1); st.rerun()
        else:
            st.markdown("<div style='font-size:11px;color:#2d3a52;padding-top:6px'>— select a portal</div>",
                        unsafe_allow_html=True)

st.markdown("<hr style='margin:4px 0 20px;border-color:#1a1f2e'>", unsafe_allow_html=True)
st.markdown("<div style='padding:0 8px'>", unsafe_allow_html=True)

# ── Running state management ──────────────────────────────────────────────────
manual_running = st.session_state.get("crawler_manual_running", False)
manual_started = st.session_state.get("crawler_manual_started_at")
if manual_running and not running_crawl:
    try:
        if manual_started and datetime.now() - datetime.fromisoformat(manual_started) > timedelta(seconds=120):
            st.session_state.pop("crawler_manual_running", None)
            st.session_state.pop("crawler_manual_started_at", None)
            manual_running = False
    except Exception: pass

current_running = bool(running_crawl or manual_running)
prev_running    = st.session_state.get("crawler_prev_running", False)

# Notify when crawl finishes
if prev_running and not current_running:
    try:
        last = query_db("SELECT * FROM crawl_log ORDER BY started_at DESC LIMIT 1")
        if last:
            lr      = last[0]
            pages   = lr.get("pages_visited", 0)
            started = lr.get("started_at")
            finished= lr.get("finished_at") or datetime.now().isoformat()
            changes_row = query_db("SELECT COUNT(*) as c FROM changes WHERE timestamp>=? AND timestamp<=?",
                                   (started, finished))
            changes = changes_row[0]["c"] if changes_row else 0
            msg     = f"Crawl finished — {pages} pages visited · {changes} change(s)."
            st.success(msg)
    except Exception: pass
    try:
        st.session_state.pop("crawler_manual_running", None)
        st.session_state.pop("crawler_manual_started_at", None)
    except Exception: pass

# ── Banners ───────────────────────────────────────────────────────────────────
if waiting_login:
    # Amber banner — waiting for manual login
    st.markdown(
        "<div class='login-wait-banner'>"
        "  <div class='spinner-ring-amber'></div>"
        "  <div class='banner-text'>"
        "    <span class='banner-title' style='color:#fbbf24'>Waiting for manual login</span>"
        "    <span class='banner-sub' style='color:#92681a'>"
        "      Browser window is open on the server — complete login to continue crawling. "
        "      Session will be saved and reused on future runs automatically."
        "    </span>"
        "  </div>"
        "</div>",
        unsafe_allow_html=True
    )
    st.markdown("<script>setTimeout(()=>window.location.reload(),5000)</script>", unsafe_allow_html=True)

elif current_running:
    # Green banner — crawling
    st.markdown(
        "<div class='running-banner'>"
        "  <div class='spinner-ring'></div>"
        "  <div class='banner-text'>"
        "    <span class='banner-title'>Crawler is running</span>"
        "    <span class='banner-sub' style='color:#1f6b47'>Refreshing every second — do not close this tab</span>"
        "  </div>"
        "</div>",
        unsafe_allow_html=True
    )
    try:
        pages      = running_crawl.get("pages_visited") if running_crawl else None
        portal_name= (running_crawl.get("portal") if running_crawl else None) or st.session_state.get("portal")
        portal_cfg = get_portal_config(portal_name) if portal_name else None
        max_pages  = portal_cfg.get("max_pages") if portal_cfg else None
        if pages is not None and max_pages:
            pct = min(100, int(pages / max_pages * 100))
            st.markdown(
                f"<div style='margin-top:8px'>"
                f"<div style='background:rgba(255,255,255,0.04);height:8px;border-radius:6px;overflow:hidden'>"
                f"<div style='width:{pct}%;height:100%;background:linear-gradient(90deg,#34d399,#60a5fa)'></div></div>"
                f"<div style='font-size:12px;color:#cfe8ff;margin-top:6px'>{pages} / {max_pages} pages</div></div>",
                unsafe_allow_html=True,
            )
        elif pages is not None:
            st.markdown(f"<div style='margin-top:6px;font-size:13px;color:#cfe8ff'>Pages visited: {pages}</div>",
                        unsafe_allow_html=True)
    except Exception: pass
    st.markdown("<script>setTimeout(()=>window.location.reload(),1000)</script>", unsafe_allow_html=True)

st.session_state["crawler_prev_running"] = current_running


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
if st.session_state.view == "overview":
    portal_stats  = get_portal_stats(portal_filter)
    total_portals = len(portal_stats)
    portals_alert = sum(1 for p in portal_stats if p["today_changes"] > 3)
    portals_warn  = sum(1 for p in portal_stats if 0 < p["today_changes"] <= 3)
    portals_ok    = sum(1 for p in portal_stats if p["today_changes"] == 0)
    total_today   = sum(p["today_changes"] for p in portal_stats)

    st.markdown("<div class='page-title'>🏠 Portal Overview</div>"
                "<div class='page-subtitle'>Health summary for every monitored portal</div>",
                unsafe_allow_html=True)

    cards = [
        ("PORTALS",       total_portals, "#3b82f6"),
        ("CHANGES TODAY", total_today,   "#f87171" if total_today else "#34d399"),
        ("🔴 ALERT",      portals_alert, "#f87171"),
        ("🟡 WARNING",    portals_warn,  "#fbbf24"),
        ("🟢 CLEAN",      portals_ok,    "#34d399"),
    ]
    cols = st.columns(5)
    for col, (label, val, color) in zip(cols, cards):
        with col:
            st.markdown(f"<div class='stat-card' style='--accent:{color}'>"
                        f"<div class='s-label'>{label}</div>"
                        f"<div class='s-value' style='color:{color}'>{val}</div></div>",
                        unsafe_allow_html=True)

    st.markdown("<div class='section-hdr'>Per-portal status</div>", unsafe_allow_html=True)

    if not portal_stats:
        st.info("No portals crawled yet. Click **▶ Run** above to start.")
    else:
        for p in portal_stats:
            chg         = p["today_changes"]
            status      = "alert" if chg > 3 else ("warn" if chg > 0 else "ok")
            dot         = "🔴" if status == "alert" else ("🟡" if status == "warn" else "🟢")
            lc_time     = time_ago(p["last_crawl_at"]) if p["last_crawl_at"] else "never"
            last_status = p["last_status"] or "unknown"
            pages_val   = p["pages_visited"] if p["pages_visited"] else "—"
            stale       = False
            if last_status == "running" and p["last_crawl_at"]:
                try:
                    lca   = p["last_crawl_at"]
                    stale = datetime.now() - (lca if isinstance(lca, datetime) else datetime.fromisoformat(str(lca))) > timedelta(minutes=30)
                except Exception: pass
            display_status = (
                "❌ crashed"  if stale else
                "🔄 running…" if last_status == "running" else
                "✅ done"     if last_status == "done" else last_status
            )
            with st.expander(
                f"{dot}  {p['portal']}  —  "
                f"{'⚠️ ' + str(chg) + ' change(s) today' if chg else '✅ Clean today'}  —  "
                f"Last crawl: {lc_time}", expanded=(status != "ok")
            ):
                pc1, pc2, pc3, pc4 = st.columns(4)
                pc1.metric("Today",    chg); pc2.metric("All-time", p["all_time_changes"])
                pc3.metric("Pages",    pages_val); pc4.metric("Status", display_status)
                if last_status == "running" and not stale: st.warning("🔄 Crawl in progress…")
                elif stale: st.error("❌ Crawl seems crashed. Use **▶ Run** to restart.")
                st.caption(f"Last crawl: {p['last_crawl_at'][:16] if p['last_crawl_at'] else 'never'}")
                if chg > 0:
                    st.markdown("---"); st.markdown("**Latest changes:**")
                    for ch in query_db(
                        "SELECT * FROM changes WHERE portal=? AND date(timestamp)=date('now') ORDER BY timestamp DESC LIMIT 5",
                        (p["portal"],)
                    ):
                        icon, lbl = DIFF_LABELS.get(ch["diff_type"], ("❓", "?"))
                        st.markdown(f"&nbsp;&nbsp;{icon} `{friendly_page_name(ch['url'])}` — {lbl} — {time_ago(ch['timestamp'])}")


# ════════════════════════════════════════════════════════════════════════════════
# VIEW: CHANGES
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "changes":
    scope = f"Portal: **{st.session_state.portal}**" if portal_filter else "All portals"

    # --- resolve the crawl run timestamp to show in subtitle ---
    _cl_row = query_db(
        "SELECT started_at FROM crawl_log WHERE portal=? AND status NOT IN ('running') ORDER BY started_at DESC LIMIT 1",
        (portal_filter,)
    ) if portal_filter else query_db(
        "SELECT started_at FROM crawl_log WHERE status NOT IN ('running') ORDER BY started_at DESC LIMIT 1"
    )
    _run_label = f"Crawl run: {_cl_row[0]['started_at'][:16]}" if _cl_row else "Most recent crawl run"

    _title_col, _ = st.columns([8, 1])
    with _title_col:
        st.markdown(f"<div class='page-title'>🚨 Latest Changes</div>"
                    f"<div class='page-subtitle'>Scope: {scope} · {_run_label}</div>",
                    unsafe_allow_html=True)

    f1, _, f3 = st.columns([2, 0.25, 3])
    with f1:
        fp_local = st.session_state.portal if portal_filter else st.selectbox("Portal", ["All Portals"] + all_portals, key="fp_local")
    # We always hide low-confidence/noisy changes in the UI and do not show DB-hidden rows.
    hide_noisy = True
    show_hidden = False
    # Compact single-date filter (shows changes on selected date)
    date_col, _ = st.columns([2, 6])
    with date_col:
        filter_date = st.date_input("Date", value=datetime.now().date(), key="filter_date")

    st.markdown("<hr style='margin:8px 0 16px;border-color:#1a1f2e'>", unsafe_allow_html=True)

    # Re-fetch with cleared cache if just refreshed
    latest_changes = get_latest_crawl_changes(portal_filter)

    if not latest_changes:
        st.success("✅ No changes in the latest crawl.")
    else:
        filtered = latest_changes[:]
        # severity filter removed — only show meaningful changes (severity derived in expander)
        if fp_local != "All Portals":
            filtered = [c for c in filtered if c["portal"] == fp_local]
        # Apply single-date filter if set
        try:
            sel_date = st.session_state.get("filter_date", None)
            if sel_date:
                def match_date(c):
                    try:
                        ts = c.get("timestamp")
                        if not ts:
                            return False
                        t = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
                        return t.date() == sel_date
                    except Exception:
                        return False
                filtered = [c for c in filtered if match_date(c)]
        except Exception:
            pass
        # Apply noisy-change hiding (always enabled). Do NOT consult or persist hidden_changes table here.
        hidden_count = 0
        visible = []
        for c in filtered:
            try:
                detail = json.loads(c.get("diff_detail") or "{}")
                is_noise = bool(detail.get("is_noise"))
                # If change is noise and hide_noisy enabled, skip it.
                if is_noise and hide_noisy:
                    hidden_count += 1
                    continue
                visible.append(c)
            except Exception:
                visible.append(c)
        filtered = visible

        # Additional strict visible-change filter: only show cards when there is an actual visible change.
        def has_visible_change(change):
            try:
                detail = json.loads(change.get("diff_detail") or "{}")
                if change.get("diff_type") == "html":
                    words = int(detail.get("words_changed") or 0)
                    lines = int(detail.get("diff_lines") or 0)
                    summary = (detail.get("summary") or "")
                    if words == 0 and lines == 0:
                        return False
                    if "no visible text" in summary.lower():
                        return False
                elif change.get("diff_type") == "visual":
                    ratio = float(detail.get("change_ratio") or 0)
                    pixels = int(detail.get("changed_pixels") or 0)
                    if pixels == 0 or ratio < 0.05:
                        return False
            except Exception:
                return False
            return True

        filtered = [c for c in filtered if has_visible_change(c)]

        if not filtered:
            st.success("✅ No visible changes found — structural or noise-only changes were filtered out.")
        else:
            st.caption(f"Showing **{len(filtered)}** of {len(latest_changes)} change(s) — {hidden_count} hidden (noise filtered)")
            for change in filtered:
                render_change_expander(change)




# VIEW: SCREENSHOTS removed per user request — functionality has been deleted from the UI.


# History view removed per user request.

# ════════════════════════════════════════════════════════════════════════════════
# VIEW: CONSOLE
# ════════════════════════════════════════════════════════════════════════════════
elif st.session_state.view == "console":
    st.markdown("<div class='page-title'>🖥️ Crawler Console</div>"
                "<div class='page-subtitle'>Live output from the crawler process</div>",
                unsafe_allow_html=True)
    cc1, cc2, _ = st.columns([2, 2, 5])
    with cc1:
        if st.button("⏹ Stop crawler", use_container_width=True, key="console_stop"):
            stopped = stop_crawl()
            st.success("Stop signal sent.") if stopped else st.warning("Could not send stop (no PID file?).")
            try:
                get_latest_crawl_changes.clear()
            except Exception:
                pass
            time.sleep(0.8); st.rerun()
    with cc2:
        if st.button("↺ Refresh", use_container_width=True, key="console_refresh_btn"):
            try:
                get_latest_crawl_changes.clear()
            except Exception:
                pass
            st.rerun()

    log_lines = read_log(tail=60)

    # Console view will not render a separate running/waiting banner to avoid duplication.
    if not (running_crawl or waiting_login):
        st.markdown("<div class='idle-banner'>⏸ Crawler idle — click ▶ Run to start</div>", unsafe_allow_html=True)

    def colorize(line):
        if "ScriptRunContext" in line or not line.strip(): return ""
        if any(x in line for x in ["ERROR", "error", "Exception", "Traceback"]):  color = "#f87171"
        elif any(x in line for x in ["WARNING", "warning", "WARN"]):              color = "#fbbf24"
        elif any(x in line for x in ["WAITING FOR LOGIN"]):                        color = "#fbbf24"  # amber
        elif any(x in line for x in ["LOGIN DETECTED", "SESSION VALID"]):          color = "#34d399"  # green
        elif any(x in line for x in ["SESSION EXPIRED", "LOGIN TIMEOUT"]):         color = "#f87171"  # red
        elif any(x in line for x in ["✓", "Done", "done", "saved", "Saved", "ALL DONE"]): color = "#34d399"
        elif any(x in line for x in ["═══", "━", "STEP", "Step", "PHASE"]):       color = "#60a5fa"
        elif any(x in line for x in ["🔐", "LOGGEDIN"]):                           color = "#a78bfa"  # purple for post-login pages
        elif any(x in line for x in ["✅", "Change", "change"]):                   color = "#a78bfa"
        else:                                                                        color = "#8899b4"
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<span style='color:{color}'>{escaped}</span>"

    colored_lines = [colorize(l) for l in log_lines]
    log_html      = "<br>".join(c for c in colored_lines if c)
    st.markdown(
        f"<div style='background:#050709;border:1px solid #1a1f2e;border-radius:10px;"
        f"padding:18px 20px;font-family:\"IBM Plex Mono\",monospace;font-size:11.5px;"
        f"line-height:1.75;max-height:520px;overflow-y:auto;white-space:pre-wrap;word-break:break-all'>"
        f"{log_html}</div>",
        unsafe_allow_html=True
    )

    # Console will not auto-refresh the whole page; user can use Refresh button to update logs.

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "rb") as f:
            st.download_button("⬇ Download full log", f, file_name="crawler.log", mime="text/plain")

    # ---------------- Change Audit Tool ----------------
    st.markdown("---")
    st.markdown("### Change Audit (last 20)")
    audit_rows = query_db("SELECT id, portal, url, diff_type, diff_detail, timestamp FROM changes ORDER BY timestamp DESC LIMIT 20")
    if not audit_rows:
        st.info("No recent changes to audit.")
    else:
        for row in audit_rows:
            cid = row.get("id")
            portal = row.get("portal")
            url = row.get("url")
            ctype = row.get("diff_type")
            ts = row.get("timestamp")
            try:
                detail = json.loads(row.get("diff_detail") or "{}")
            except Exception:
                detail = {}
            conf = detail.get("confidence")
            is_noise = detail.get("is_noise", False)
            col1, col2, col3 = st.columns([6, 2, 2])
            with col1:
                st.markdown(f"**[{portal}]** `{friendly_page_name(url)}` — {ctype} — {str(ts)[:16]}")
                if conf is not None:
                    st.caption(f"Confidence: {conf} — {'Noise' if is_noise else 'Likely real'}")
            with col2:
                st.markdown("<div style='color:#94a3b8'>Mark Noise / Unhide removed</div>", unsafe_allow_html=True)
            with col3:
                st.markdown("<div style='color:#94a3b8'>Use admin tools to manage hidden changes</div>", unsafe_allow_html=True)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1a1f2e;margin-top:32px'>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-family:\"IBM Plex Mono\",monospace;font-size:11px;color:#2d3a52;padding:0 8px 16px'>"
    f"Portal Change Monitor · {st.session_state.portal} · {datetime.now().strftime('%d %b %Y, %I:%M %p')}</div>",
    unsafe_allow_html=True
)