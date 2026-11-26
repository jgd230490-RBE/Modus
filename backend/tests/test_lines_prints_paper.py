"""
26 Nov 2026 — the printed maps' route lines (branch claude/lines-prints-paper; mockup notes/map-lines-prints-mockup-1125,
cards 3, 3b and 4 to 6; John: "Yes, as recommended" to Q1 to Q9, then Q10 "Go with blue", against the recommendation).

WHAT IS ASSERTED
----------------
  Q4 + Q10  every exported map draws the laden leg dark blue #0051C4 and the empty leg light blue #72A7FF (two of the band
            blues): the route map export and the CLP plans (route_map_export.LEG_LADEN / LEG_EMPTY), the route sheet and its
            diversion page (export.RS_LOADED / RS_RETURN) and the Route analysis, whose _legs binds the colours as DEFAULT
            ARGUMENTS at def time (checked by drawing through it, not by reading the constant);
            the amber edge round a closure (DIVERSION_EDGE) stays the ONLY amber; no green leg is left.
  Q6        the printed busy-hours road is ink #3A3C41 (not the plan blue, not the sign blue).
  Q7        the collision evidence map draws the route in its OWN light greys #A9ABB0 / #C6C8CC under the ink marks, and its
            key follows; it reads no RS_* colour.
  Q8        the collision charts (_ce_time_of_day, _ce_cycle_by_hour) keep the route's green #059669 through their own
            constant CE_ROUTE_CHART, never RS_LOADED.
  Q9        the diversions pages keep the dashed usual road.
  Q5        only words that name a colour change: the route sheet's "the light blue route", the Route analysis's
            "(back in light blue)" twice, the user guide's export sentence "dark blue out and light blue back".

WHAT THIS DOES NOT PROVE
------------------------
How the files LOOK: every file was rebuilt from a local copy of live's organisation file and read page by page, in colour
and in greyscale (notes/session-1126-lines-prints-paper.md; pictures on the mockup page as "Real · built").

Run from the repo root:  python backend/tests/test_lines_prints_paper.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)
os.environ.setdefault("WAYSCOPE_WARM_CACHE", "0")
PASS, FAIL = 0, []


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def ok(label, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (f"  [{detail}]" if detail else ""))


import export  # noqa: E402
import route_map_export as rme  # noqa: E402
import route_analysis_render as rar  # noqa: E402

BLUE_OUT, BLUE_BACK, INK = "#0051C4", "#72A7FF", "#3A3C41"
OLD = {"#059669", "#F59E0B"}

# ---- Q4 + Q10: the legs -------------------------------------------------------------------------------------------
ok("⭐ Q10: the route map export (and the CLP plans) draws laden dark blue, empty light blue",
   rme.LEG_LADEN.upper() == BLUE_OUT and rme.LEG_EMPTY.upper() == BLUE_BACK, f"{rme.LEG_LADEN} {rme.LEG_EMPTY}")
ok("⭐ Q10: the route sheet (and its diversion page) draws loaded dark blue, return light blue",
   export.RS_LOADED.upper() == BLUE_OUT and export.RS_RETURN.upper() == BLUE_BACK, f"{export.RS_LOADED} {export.RS_RETURN}")
ok("Q10: the two blues are two of the band blues (one list with the public map's)",
   {BLUE_OUT, BLUE_BACK} <= {c.upper() for c in __import__("bulletin_doc").VOLUME_RAMP})
ok("Q10: the plan's leg colour by kind: laden and a diversion's laden dark blue, empty light blue, busy ink",
   export._plan_leg_colour("laden").upper() == BLUE_OUT and export._plan_leg_colour("diversion-laden").upper() == BLUE_OUT
   and export._plan_leg_colour("empty").upper() == BLUE_BACK and export._plan_leg_colour("diversion-empty").upper() == BLUE_BACK
   and export._plan_leg_colour("busy").upper() == INK)

# the Route analysis: _legs's default arguments were bound when the module was read; draw through it and see the colours
_seen = []
_real = export._rs_line
export._rs_line = lambda c, P, coords, colour, width, **k: _seen.append(colour.upper())
try:
    class _Doc:
        c = None
    rar._legs(_Doc(), lambda lon, lat: (lon, lat), {"loaded": [(0, 0), (1, 1)], "return": [(1, 1), (0, 0)]})
finally:
    export._rs_line = _real
ok("⭐ Q10: the Route analysis's legs, drawn with _legs's own defaults, are light blue back then dark blue out",
   _seen == [BLUE_BACK, BLUE_OUT], str(_seen))
ok("Q10: route_analysis_render reads the blues it imported", rar.RS_LOADED.upper() == BLUE_OUT and rar.RS_RETURN.upper() == BLUE_BACK)
ok("Q10: no leg constant is green or amber any more",
   not ({rme.LEG_LADEN.upper(), rme.LEG_EMPTY.upper(), export.RS_LOADED.upper(), export.RS_RETURN.upper()} & OLD))
ok("Q4: the amber edge round a closure stays, and is the only amber among the route map's line colours",
   rme.DIVERSION_EDGE.upper() == "#F59E0B"
   and [c for c in (rme.LEG_LADEN, rme.LEG_EMPTY, rme.BUSY_ROAD, rme.DIVERSION_EDGE) if c.upper() == "#F59E0B"] == [rme.DIVERSION_EDGE])
ok("Q4: the key's words stay (Laden (out), Empty (return), Busy-hours road, Way round a closure)",
   [l["label"] for l in rme.LEG_LEGEND] == ["Laden (out)", "Empty (return)", "Busy-hours road", "Way round a closure"])

# ---- Q6: the busy-hours road ----------------------------------------------------------------------------------------
ok("⭐ Q6: the printed busy-hours road is ink #3A3C41 (not the plan blue, not the sign blue)",
   rme.BUSY_ROAD.upper() == INK and rme.BUSY_ROAD.upper() not in {"#3B82F6", "#0B4EA2"}, rme.BUSY_ROAD)
ok("⭐ Q6: the Route analysis's busy-hours page draws the other road in ink too, never a stock blue beside the blue legs "
   "(found on R013's page in the build: #2563EB against #0051C4)",
   rar.BUSY_BLUE.upper() == INK and rar.BUSY_BLUE.upper() not in {"#2563EB", "#3B82F6", "#0B4EA2"}, rar.BUSY_BLUE)
_src = read("backend/route_analysis_render.py")
ok("Q6: the busy-hours page's map, and its key, read BUSY_BLUE",
   '_rs_line(c, P, use["loaded"], BUSY_BLUE' in _src and "_k_line(BUSY_BLUE)" in _src)

# ---- Q7 / Q8: the collision evidence ---------------------------------------------------------------------------------
ex = read("backend/export.py")
ok("⭐ Q7: the collision map has its own light greys for the route, out #A9ABB0 and back #C6C8CC",
   getattr(export, "CE_ROUTE_OUT", "").upper() == "#A9ABB0" and getattr(export, "CE_ROUTE_BACK", "").upper() == "#C6C8CC")
_ce = ex[ex.index("def build_collision_evidence_pdf("):]
_ce = _ce[:_ce.index("\ndef ", 10)]
ok("⭐ Q7: the collision evidence's map, its inset and its key read the route's own greys and never RS_LOADED / RS_RETURN",
   "RS_LOADED" not in _ce and "RS_RETURN" not in _ce and _ce.count("CE_ROUTE_OUT") >= 3 and _ce.count("CE_ROUTE_BACK") >= 3,
   f"RS in it: {'RS_LOADED' in _ce or 'RS_RETURN' in _ce}; {_ce.count('CE_ROUTE_OUT')} {_ce.count('CE_ROUTE_BACK')}")
ok("Q7: the collision ink is unchanged, and darker than either light grey", export.CE_INK == "#27272A")
ok("⭐ Q8: the two collision charts keep the route's green through their own constant",
   getattr(export, "CE_ROUTE_CHART", "").upper() == "#059669")
for fn in ("_ce_time_of_day", "_ce_cycle_by_hour"):
    body = ex[ex.index(f"def {fn}("):]
    body = body[:body.index("\ndef ", 10)]
    ok(f"⭐ Q8: {fn} reads CE_ROUTE_CHART and not RS_LOADED", "CE_ROUTE_CHART" in body and "RS_LOADED" not in body, fn)

# ---- Q9: the dashed usual road --------------------------------------------------------------------------------------
ra = read("backend/route_analysis_render.py")
ok("Q9: the diversions pages still draw the usual road dashed in its grey", ra.count("_legs(doc, P, R, dashed=True)") == 2
   and 'USUAL_GREY = "#71717A"' in ra)

# ---- Q5: the words that name a colour --------------------------------------------------------------------------------
ok("⭐ Q5: the route sheet says 'Then follow the light blue route back to A', never the amber one",
   '"Then follow the light blue route back to A"' in ex and "the amber route" not in ex)
ok("⭐ Q5: the Route analysis's two keys say '(back in light blue)', never '(back in amber)'",
   ra.count("(back in light blue)") == 2 and "back in amber" not in ra
   and '"The usual road out (back in light blue)"' in ra and '"The way taken out (back in light blue)"' in ra)
ug = read("frontend/help/index.html")
ok("⭐ Q5: the user guide's export sentence names the blues, not green and amber",
   "drawn dark blue out and light blue back, with the alternatives in use named in the key" in ug
   and "drawn green out and amber back" not in ug)
ok("Q5: the key words on paper stay (Loaded, A to B · Empty, back to A)",
   '"Loaded, A to B"' in ex and '"Empty, back to A"' in ex)
ok("the comments that describe the plan's legs name the blues", "the laden (dark blue) and empty (light blue) legs" in ex)

print(f"\ntest_lines_prints_paper: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
