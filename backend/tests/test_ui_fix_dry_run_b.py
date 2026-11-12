"""
test_ui_fix_dry_run_b.py — 12 Nov 2026, cards B-X2 and B-X3 (the dry run on live, rule 13), branch
claude/clocs-b-dry-run-fixes.

  B-X2: the Route analysis' section C box "For the route risk assessment (CLOCS Standard v5, 5.1a)" drew its title as one
        8 pt line, 221 pt wide in a 201 pt room: "5.1a)" touched the box's right edge (R001, page 5). The box is the same
        width on every route (42 % of the page), so the title now breaks before its bracket when it does not fit, and the
        box grows by the line. Measured here with the real font.
  B-X3: the data pages' header (Locations, Routes, Zones) read "0 locations · 0 routes" for 6 to 8 s on live before the
        answer came; it now reads "Loading…" (C-F8's word) until the routes' answer, and takes the locations count from
        that answer until the map's own list is in. Source checks here; the real picture (a 5 s held answer) is on the card.

Its own file (BUILD.md rule 3). The rendered page 5 is measured in test_collisions.py (7c, B-X2).
"""
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (("  " + str(extra)[:300]) if extra else ""))


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


EXP = read("backend", "export.py")
HTML = read("frontend", "index.html")

# ---- B-X2: the box title ---------------------------------------------------------------------------------------- #
import export  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402

W, H = A4
CW = W - 2 * 12 * mm                       # build_collision_evidence_pdf's own page and margins
BW = CW - CW * 0.58 - 10                   # the box beside the table
ROOM = BW - 10                             # 5 pt inside each side
B = export._BF("bold")
fits = hasattr(export, "_box_title_lines") and hasattr(export, "CLOCS_BOX_TITLE")
ok("🔴 B-X2: a box-title helper and the title as one constant", fits)
if fits:
    T = export.CLOCS_BOX_TITLE
    ok("B-X2: the words do not change", T == "For the route risk assessment (CLOCS Standard v5, 5.1a)")
    ok("B-X2: (the fault) as one 8 pt line the title is wider than the box's room", stringWidth(T, B, 8) > ROOM,
       (stringWidth(T, B, 8), ROOM))
    L = export._box_title_lines(T, B, 8, ROOM)
    ok("🔴 B-X2: in the box's room it breaks before the bracket", L == ["For the route risk assessment", "(CLOCS Standard v5, 5.1a)"], L)
    ok("🔴 B-X2: every line inside the room, measured with the PDF's font", all(stringWidth(x, B, 8) <= ROOM for x in L),
       [round(stringWidth(x, B, 8), 1) for x in L])
    ok("B-X2: a room that takes it whole keeps one line", export._box_title_lines(T, B, 8, 400) == [T])
    L2 = export._box_title_lines(T, B, 8, 90)
    ok("B-X2: a narrower room wraps each part by words, every line inside, no word lost",
       all(stringWidth(x, B, 8) <= 90 for x in L2) and " ".join(L2) == T, L2)
    ok("B-X2: text with no bracket wraps by words", export._box_title_lines("one two three four five six", B, 8, 40)
       == export._wrap("one two three four five six", B, 8, 40))

i = EXP.find('title_lines = _box_title_lines(CLOCS_BOX_TITLE, B, 8, bw - 10)')
box = EXP[i:i + 1100] if i > 0 else ""
ok("🔴 B-X2: the box draws its title from the helper, in the box's own room", i > 0)
ok("🔴 B-X2: no single drawString of the whole title is left",
   'drawString(bx + 5, yy - 11, "For the route risk assessment (CLOCS Standard v5, 5.1a)")' not in EXP)
ok("B-X2: the box grows by the extra line, and the lines below move down with it",
   "extra = (len(title_lines) - 1) * 9.6" in box and "bh = 18 + extra +" in box and "yy -= 17 + extra" in box)
ok("B-X2: each title line drawn 9.6 pt under the last", "c.drawString(bx + 5, yy - 11 - i * 9.6, ln)" in box)
ok("B-X2: the lines are kept on the page's data for the tests", 'S["clocs_box_title"] = title_lines' in box)

# ---- B-X3: the data pages' counts --------------------------------------------------------------------------------- #
j = HTML.find('data-counts-loading="1"')
ok("🔴 B-X3: the counts line says Loading… until the routes' answer",
   '{status === null && <div className="text-xs text-slate-500 mt-1.5" data-counts-loading="1">Loading…</div>}' in HTML)
ok("🔴 B-X3: the counts themselves only once it is in",
   '{status !== null && <div className="text-xs text-slate-500 mt-1.5 flex flex-wrap gap-x-3 gap-y-1">' in HTML)
ok("🔴 B-X3: the locations count from the answer until the map's list is in",
   "<span>{locs.length || (summary && summary.locations) || 0} locations</span>" in HTML
   and "<span>{locs.length} locations</span>" not in HTML)
ok("B-X3: the routed line still closes the counts block", "routed for {vehLabel(showProfile)}</span>\n        </div>}\n      </PageHeader>" in HTML)
ok("B-X3: a failed status read still ends the wait (status becomes [], not null)",
   "fetchStatus().catch(() => setStatus([]))" in HTML)
ok("B-X3: the summary the count reads carries the locations", re.search(r'return \{"locations": db\.count_locations\(\), "routes": total',
                                                                         read("backend", "network.py")) is not None)
ok("B-X3: C-F8's word, nothing longer", HTML[j:j + 40].count("Loading…") == 1 if j > 0 else False)

print(f"\ntest_ui_fix_dry_run_b: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
