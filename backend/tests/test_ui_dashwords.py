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
# REVERSED 25 Nov 2026 (the Dashboard rethink A1; John: "Yes, complete week"): both sides to the latest COMPLETE reported
# week, from the read (planned_to_cut_t / actual_to_cut_t); no longer every actual ÷ the plan up to this month
ok("2: the divisor is the tonnes planned to the last complete reported week, the actuals to the same week",
   "T.tCut += r.planned_to_cut_t || 0" in html and "deliveredPct: pctOf(T.actualCut, T.tCut)" in html
   and "plannedToDate: T.tCut" in html and "T.tNow" not in html and "nowIdx) T." not in html)
ok("2: the table's per-line figure follows", "a.actualCut * 100 / a.tCut" in html and "a.tCut += r.planned_to_cut_t || 0" in html and "a.tNow" not in html)
# NARROWED 24 Nov 2026 (the Dashboard rethink, A1; John's round 2): the strip's Delivered figure is the to-date share with
# "X t of Y t" under it and its status; the whole plan's share moves into its "i" (the drawing's "30 % of the whole plan").
# The big screen's two figures keep their words (2 of the old 3).
# REVERSED 25 Nov 2026 (the Dashboard rethink A1; John: "Yes, complete week"): the words name the cut week's Sunday
# ("to 22 Nov") wherever the share shows: the strip, "All the figures", the big screen, the chart's headline
ok("2: the card, the big-screen figures and the i box name the cut week",
   "t planned, both to Sunday ${K.cutWords}." in html and html.count("t planned to ${K.cutWords}`") == 3
   and html.count("`To ${K.cutWords}: ${grp(K.actualToCut)} t delivered ÷ ${grp(K.plannedToDate)} t planned.") == 2
   and "both to the last whole week reported" in html and "up to and including this month" not in html
   and "t planned up to this month" not in html and "planned to date" not in html)
ok("2 (John's change): the card shows BOTH, the cut share as the headline, the whole plan in its i box, the i box naming each",
   "deliveredWholePct: pctOf(T.actualT, T.t)" in html
   and "% of the whole plan in view (${grp(K.totT)} t)." in html and html.count("Whole plan: ${grp(K.actualT)} t ÷ ${grp(K.totT)} t planned in view.") == 2
   and "The second line gives the share of the whole plan in view" in html
   and '% <span className="text-[13px] font-normal">to date</span>' not in html and "t planned to date · " not in html)
ok("2: the strip's line under the figure is the delivered tonnes to the cut", "`${bigNum(K.actualToCut)} t of ${bigNum(K.plannedToDate)} t`" in html)
ok("3: a long series name is left off, never cut", 'if(String(ds.label || "").length > 20) return;' in html
   and 'm.label.slice(0, 19)' not in html)
ok("4: the council headline names the top bar by the bars' measure",
   "top = rows[0]" in clp and 'has the most {word}: {top[\'distance\']:g}' in clp and "takes the most" not in clp)
ok("4: the bars are ordered by that measure", 'rows.sort(key=lambda x: (-(x["distance"] or 0), x["council"]))' in clp)

print(f"\ntest_ui_dashwords: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
