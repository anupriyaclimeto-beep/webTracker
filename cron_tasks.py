import os
import sys
import pathlib
import subprocess
from datetime import datetime

ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def tee_output(pipe, log_file, is_stderr=False):
    import sys
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
        
        # Check if we are running in Streamlit Cloud environment
        IS_CLOUD = os.getenv("STREAMLIT_SERVER_PORT") is not None
        if IS_CLOUD:
            pid_file = pathlib.Path("/tmp/.crawler.pid")
            log_file = pathlib.Path("/tmp/.crawler.log")
        else:
            pid_file = ROOT / ".crawler.pid"
            log_file = ROOT / ".crawler.log"

        # Clear/initialize log file
        try:
            if log_file.exists():
                log_file.unlink()
        except Exception:
            pass
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

        env = os.environ.copy()
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=env
        )
        
        import threading
        t1 = threading.Thread(target=tee_output, args=(proc.stdout, log_file, False), daemon=True)
        t2 = threading.Thread(target=tee_output, args=(proc.stderr, log_file, True), daemon=True)
        t1.start()
        t2.start()

        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
            
        print(f"[{datetime.now()}] Crawl process {proc.pid} launched successfully using {python_exe}.")
    except Exception as e:
        print(f"[{datetime.now()}] Crawl failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "start_crawl":
        start_crawl()
    else:
        print("Usage: python cron_tasks.py start_crawl")
