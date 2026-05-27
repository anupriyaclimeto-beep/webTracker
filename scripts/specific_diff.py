import sys, os, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from diff_engine import html_diff

base = r'archive\\my-portal\\eprplastic.cpcb.gov.in_#_plastic_home\\20260525_124632\\snapshot.html'
cur = r'archive\\my-portal\\eprplastic.cpcb.gov.in_#_plastic_home___Home\\20260527_100924\\snapshot.html'

with open(cur, 'r', encoding='utf-8', errors='ignore') as f:
    cur_html = f.read()

res = html_diff(base, cur_html)
print(json.dumps(res, indent=2))

