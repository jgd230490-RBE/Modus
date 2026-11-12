"""
9 Nov 2026 — UI fix "words 2" (wave 1 of the 9 Nov critique; branch claude/ui-fix-words-2). Source-level checks:
  1  Users' shared-codes banner has no date; says what is true and what to do.
  7  a "set by" line never prints a file path; the demo generator signs as "the demo planner" (package too).
 15  the Dashboard's five biggest materials keep their colours, the rest fold into "Other (N)" named under the chart;
     a repeated route label says what differs; axis ticks never repeat.
 #45 the technical guide's inline code wraps (no sideways scroll at 390 px).
 D1  the demo's header shows the tenant's name (no "Your organisation's name appears here").
 D6  no "(fictional)" on a place or organisation name in the package.
Run from the repo root:  python backend/tests/test_ui_words2.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PASS = 0
FAIL = []


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
gen = read("backend/tools/make_demo_tenant.py")
tech = read("frontend/help/technical/index.html")
pkg_raw = read("demo/uk-corridor.package.json")

# ---- 1 the banner
# NARROWED 10 Nov 2026 (U5, claude/ui-fix-long-sentences): the banner is "Shared codes are still on." and a link to the guide
i = html.index("Shared codes are still on.")
banner = html[i:i + 400]
ok("1: the banner names no date", not re.search(r"\d{1,2} (Oct|Nov) 20\d\d|Sat 31", banner))
ok("1: the banner says what to do (a link to how)", "How to switch them off" in banner and 'GUIDE_URL("ug-shared-codes")' in banner)
ok("1: the old sentence is gone", "They end on" not in html)

# ---- 7 set-by lines
ok("7: byWords hides a path / script name", 'function byWords(v)' in html and '"the demo planner"' in html)
ok("7: both 'Set by' lines go through byWords",
   "Set by ${byWords(t.updated_by)}" in html and "Set by {byWords(T.updated_by)" in html)
ok("7: the generator signs as the demo planner", 'by="tools/make_demo_tenant.py"' not in gen and gen.count('by="the demo planner"') >= 8)
ok("7: the shipped package carries no script name as a signature", "make_demo_tenant.py" not in pkg_raw)
ok("7: the package is signed by the demo planner", '"updated_by": "the demo planner"' in pkg_raw)

# ---- 15 charts
ok("15: the fold: five keep colours, one grey Other (N)",
   "const matHead = D.mats.length > 6 ? D.mats.slice(0, 5) : D.mats" in html and "`Other (${matRest.length})`" in html
   and 'tok("--chart-none", "#A8A29E")' in html)
ok("15: both material charts use the folded sets", "datasets: matSets.map((x) =>" in html and "labels: matSets.map(x => x.m)" in html)
ok("15: the names of the folded materials sit under both desk charts", html.count('data-other-mats="1"') == 2)
ok("15: a repeated route label gets the material", "topDup[topBase(r)] > 1 && r.material ? `${r.route_id} · ${r.material}`" in html
   and "material: r.material_type, baked: !!r.baked" in html)
ok("15: a tick keeps its first decimal (1.5 k)", "(Math.round(+v / 100) / 10) + \" k\"" in html
   and "Math.round(+v / 1e3) + \" k\"" not in html)

# ---- #45
ok("#45: technical guide inline code wraps", "li>code,p>code{overflow-wrap:anywhere}" in tech)

# ---- D1 / D6
ok("D1: the header shows the tenant's name on the demo too", "HEADER_DEMO_NAME" not in html
   and re.search(r'hdr-muted truncate max-w-\[36vw\]">\{TENANT\.name\}</span>', html) is not None)
pkg = json.loads(pkg_raw)
locs = pkg["tables"].get("locations") or []
ok("D6: the package has locations", len(locs) >= 20)
names = [r.get("name", "") if isinstance(r, dict) else "" for r in locs]
ok("D6: no '(fictional)' on a place name", not any("(fictional)" in n for n in names))
vendors = [str(r.get("vendor") or "") for r in locs if isinstance(r, dict)]
ok("D6: nor on a vendor", not any("(fictional)" in v for v in vendors))
groups = json.dumps(pkg["tables"].get("clp_review_groups") or [])
ok("D6: nor on the client group's name", "Highways client (fictional)" not in groups and "Highways client" in groups)

print(f"\ntest_ui_words2: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
