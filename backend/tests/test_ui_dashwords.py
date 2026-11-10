"""
10 Nov 2026 — finding 19 (desk Dashboard text; John: "Yes to all four"; branch claude/ui-fix-dashboard-words). Source checks:
  1  "forecast months" is gone from the Dashboard: plan lines.
  2  "Delivered against plan" divides by the tonnes planned up to and including this month (K.plannedToDate).
  3  a series name that would not fit is left off the chart, never cut (the key carries it).
  4  the council chart's headline names the top bar, by the measure the bars are drawn in.
Run from the repo root:  python backend/tests/test_ui_dashwords.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASS, FAIL = 0, []


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def ok(label, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)


html = read("frontend/index.html")
clp = read("backend/clp.py")

ok("1: no 'forecast month' left on a screen (one code comment may)", html.count("forecast month") <= 1 and "forecast month" not in read("frontend/help/index.html"))
ok("1: plan lines, in the coverage line and the two reported lines",
   "plan lines have a route" in html and html.count("reported on ${K.reportedN} of ${D.lines} plan lines") == 2
   and html.count("plan line${K.reportedN === 1") >= 2)
ok("2: the divisor is the tonnes planned up to this month",
   "if(r.month_index <= nowIdx) T.tNow += r.tonnes" in html and "deliveredPct: pctOf(T.actualT, T.tNow)" in html
   and "plannedToDate: T.tNow" in html)
ok("2: the table's per-line figure follows", "a.actualT * 100 / a.tNow" in html and "if(r.month_index <= nowIdx) a.tNow += r.tonnes" in html)
ok("2: the card, the big-screen figures and the i box say 'planned to date'",
   "t planned to date`}" in html and html.count("t planned up to this month`") == 3 and "up to and including this month" in html)
ok("2: nothing prints the whole-range total as the divisor", "t of ${bigNum(K.totT)} t`}" not in html)
ok("3: a long series name is left off, never cut", 'if(String(ds.label || "").length > 20) return;' in html
   and 'm.label.slice(0, 19)' not in html)
ok("4: the council headline names the top bar by the bars' measure",
   "top = rows[0]" in clp and 'has the most {word}: {top[\'distance\']:g}' in clp and "takes the most" not in clp)
ok("4: the bars are ordered by that measure", 'rows.sort(key=lambda x: (-(x["distance"] or 0), x["council"]))' in clp)

print(f"\ntest_ui_dashwords: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
