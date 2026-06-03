import os
import sys
import pathlib
import subprocess
from datetime import datetime

ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def start_crawl():
    """Entry‑point for the cron job – launches a crawl for all portals sequentially."""
    print(f"[{datetime.now()}] Scheduled crawl starting for all portals...")
    try:
        # Calls the crawler script with --once so it runs all portals sequentially and then exits.
        # Use the virtual environment Python if it exists, otherwise fallback to sys.executable
        venv_python = ROOT / "venv" / "Scripts" / "python.exe"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable
        
        # Ensure playwright browsers are installed (Crucial for Streamlit Cloud!)
        subprocess.run([python_exe, "-m", "playwright", "install", "chromium"], check=False)
        
        cmd = [python_exe, "crawler.py", "--once"]
        
        env = os.environ.copy()
        
        log_fh = open(ROOT / ".crawler.log", "w", encoding="utf-8", buffering=1)
        proc = subprocess.Popen(
            cmd, stdout=log_fh, stderr=log_fh, cwd=str(ROOT), env=env
        )
        with open(ROOT / "crawler.pid", "w") as f:
            f.write(str(proc.pid))
            
        print(f"[{datetime.now()}] Crawl process {proc.pid} launched successfully using {python_exe}.")
    except Exception as e:
        print(f"[{datetime.now()}] Crawl failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "start_crawl":
        start_crawl()
    else:
        print("Usage: python cron_tasks.py start_crawl")
