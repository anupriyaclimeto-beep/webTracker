from pathlib import Path
import difflib
base = Path(r'archive/my-portal/eprplastic.cpcb.gov.in_#_plastic_home/20260525_124632/snapshot.html')
cur = Path(r'archive/my-portal/eprplastic.cpcb.gov.in_#_plastic_home___Home/20260527_100924/snapshot.html')
print('baseline exists', base.exists())
print('current exists', cur.exists())
if not base.exists() or not cur.exists():
    raise SystemExit('One of the files is missing')
base_text = base.read_text(encoding='utf-8', errors='ignore')
cur_text = cur.read_text(encoding='utf-8', errors='ignore')
markers = ['BASELINE_TEST_BTN','BASELINE_TEST_TEXT','MANUAL_TEST_BTN','MANUAL_TEST_P','MANUAL_EDIT_MARKER','MANUAL_TEST_MARKER']
for marker in markers:
    print(marker, 'in baseline=', marker in base_text, 'in current=', marker in cur_text)

base_lines = base_text.splitlines()
cur_lines = cur_text.splitlines()
ud = list(difflib.unified_diff(base_lines, cur_lines, lineterm=''))
interesting = []
for i,line in enumerate(ud):
    if any(m in line for m in markers):
        for j in range(max(0,i-3), min(len(ud), i+4)):
            interesting.append(ud[j])
        interesting.append('---')
if not interesting:
    print('\\nNo marker-related diff lines found. Showing first 120 unified diff lines:')
    for l in ud[:120]:
        print(l)
else:
    print('\\nRelevant diff lines:')
    for l in interesting:
        print(l)

