import os
import json
import tempfile
from diff_engine import clean_html, html_diff

def write_tmp_html(content):
    fd, path = tempfile.mkstemp(suffix=".html", prefix="baseline_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

BASE_HTML = """
<html><head><title>Test Page</title></head><body>
<h1>Important Notice</h1>
<div class="doc-list">
  <a href="/download/doc1.pdf">Download doc</a>
</div>
<div class="timestamp">Last updated: 2 minutes ago</div>
</body></html>
"""

def make_noisy(html):
    return html.replace("2 minutes ago", "3 minutes ago").replace("</body>", '<img src="data:image/png;base64,AAAA..."/> </body>')

def make_real_change(html):
    return html.replace("</div>\n</body>", '<div class="new-row"><a href="/download/doc2.pdf">New doc</a></div>\n</div>\n</body>')

def run_test():
    baseline_path = write_tmp_html(BASE_HTML)
    noisy = make_noisy(BASE_HTML)
    real = make_real_change(BASE_HTML)

    res_noisy = html_diff(baseline_path, noisy)
    res_real = html_diff(baseline_path, real)

    noisy_meaningful = res_noisy.get("meaningful_html_change", False) or res_noisy.get("changed", False)
    real_meaningful = res_real.get("meaningful_html_change", False) or res_real.get("changed", False)

    print("NOISY - changed:", res_noisy.get("changed"), "meaningful:", noisy_meaningful, "words_changed:", res_noisy.get("words_changed"))
    print("REAL  - changed:", res_real.get("changed"), "meaningful:", real_meaningful, "words_changed:", res_real.get("words_changed"))

    passed = True
    if noisy_meaningful:
        print("FAIL: Noisy change detected as meaningful")
        passed = False
    if not real_meaningful:
        print("FAIL: Real change NOT detected as meaningful")
        passed = False

    if passed:
        print("PASS: Noise filter working as expected")
        return 0
    else:
        return 2

if __name__ == "__main__":
    exit(run_test())

