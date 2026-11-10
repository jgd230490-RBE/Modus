"""
The demo-path fixes (10 Nov 2026, branch claude/ui-fix-demo-path; mockup notes\\ui-fix-demo-path-mockup-1110\\, John:
"Yes, Q1–Q9"). Its own file (the wave rule): nothing appended to test_limits.py / test_lorry_plan.py beyond the two
pins those files carried, which are REVERSED there with the date.

WHAT IS ASSERTED
----------------
  * F10b (limits.runs_along, the one rule check_route and _matches share): a limit tagged on a short stub at a side
    road's MOUTH no longer counts for a route that only passes the junction (perpendicular 7–13 m stubs, a 41 m stub at
    29°, a 52 m stub at 38°); a limit the route runs along still counts (a parallel stretch, a 34 m one wholly on the
    route, a 32 m piece that bends 32° from the route while the route carries on past it), and so does a side road the
    route TURNS INTO and uses; the bridge trap still holds; the rule only ever drops a hit.
  * F7 (lorry_plan._lorry_rows): the break goes BEFORE the trip that would pass 4½ h of driving or 6 h of work
    (drivers_hours' own limits), on the mockup's two live lorries (Northfield Quarry, Batching Plant) and on every
    packing of a spread of made-up days: never over a limit before the break unless one trip alone passes it (Q1: then
    after that trip); the lorry count, trips, start, end, free time and room never move; the sheet says "before … pass".
  * C2: the Driver sheet's heading and the XLSX's Lorry type column print the lorry's NAME (conversions.vehicle_label,
    as the panel's vehLabel), never the stored key.
  * C1 (section_select.road_at): a click that names a route with nothing within reach takes that route's nearest
    stretch up to 1 km; a click naming no route, or a route over 1 km away, still finds nothing.
  * F8 (source): "Induction" is gone from the app and the map; the gate form reads "Check-in (min)" with the hover
    "Minutes each lorry spends at the gate on arrival."; the stored field safety_minutes is unchanged.

WHAT THIS DOES NOT PROVE
------------------------
Live's own limits after the re-check (checked on live after the merge), the PDF as printed (checked on a local copy),
and the map's Conditions rows (ui_fix_demo_path.js).

Run:  python3 backend/tests/test_ui_fix_demo_path.py
"""
import math
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

import drivers_hours as dh  # noqa: E402
import limits  # noqa: E402
import lorry_plan as lp  # noqa: E402
import section_select  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (f"  {extra}" if extra else ""))


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


# --------------------------------------------------------------------------- #
#  F10b: the side-road mouth                                                   #
# --------------------------------------------------------------------------- #
LAT0 = 52.62
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110540.0


def pt(x_m, y_m, lon0=-0.92):
    """[lon, lat] x metres east, y metres north of (lon0, LAT0)."""
    return [round(lon0 + x_m / KX, 7), round(LAT0 + y_m / KY, 7)]


def ray(x0, y0, deg, length, step=None):
    """A line from (x0, y0) metres at `deg` (0 = east, 90 = north), `length` metres long."""
    n = max(1, int(length // (step or length)))
    return [pt(x0 + math.cos(math.radians(deg)) * length * k / n, y0 + math.sin(math.radians(deg)) * length * k / n)
            for k in range(n + 1)]


MAIN = [pt(-2000 + 50 * i, 0) for i in range(81)]       # a route W -> E along the main road, 4 km, 50 m vertices


def counts(coords, line=MAIN, length_m=None):
    idx = limits._LineIndex(line, max(limits.MATCH_M, limits.POINT_M))
    return limits.runs_along(coords, idx, length_m) is not None


def limit_row(ext, coords, kind="weight"):
    a = limits.anchor_of("LineString", coords)
    return {"source": "osm", "ext_id": ext, "kind": kind, "value": 7.5, "unit": "t", "geom_type": "LineString",
            "geometry": coords, "length_m": limits._line_len_m(coords), "anchor_lon": a[0], "anchor_lat": a[1],
            "exceptions": "Except for access"}


ok("F10b: the constants are the measured pair (20°, 40 m) and live beside the old ones",
   limits.ALONG_ANGLE_DEG == 20.0 and limits.CARRY_ON_M == 40.0 and limits.MATCH_M == 20.0
   and limits.ALONG_MIN_M == 30.0 and limits.ALONG_SHARE == 0.6)
# the mouths: a short stub leaving the main road, all of it within 20 m of the route (the old rule counted every one)
MOUTHS = {"a 13 m stub at 81° (Sturdee Road)": ray(100, 0, 81, 13),
          "a 9 m stub at 90° (Sibson Road)": ray(300, 0, 90, 9),
          "a 7 m stub at 70° (Bowley Avenue)": ray(500, 0, 70, 7),
          "an 11 m stub at 89° (Melton Road)": ray(700, 0, 89, 11),
          "a 41 m stub at 29°, two vertices (the unnamed 41 m one)": ray(900, 0, 29, 41, 20.5),
          "a 52 m stub at 38° (Hunters Way)": ray(1100, 0, 38, 52, 26),
          "a 26 m stub at 86° that starts 2 m off the road (Marydene Drive)": ray(1300, 2, 86, 26)}
idx_main = limits._LineIndex(MAIN, 20.0)
for name, c in MOUTHS.items():
    old = limits._along(c, lambda q: idx_main.near(q, limits.MATCH_M))
    old_need = min(limits.ALONG_MIN_M, limits.ALONG_SHARE * limits._line_len_m(c))
    ok(f"F10b: ⭐ {name} at a junction the route only passes is NOT a hit", not counts(c),
       f"old along {old:.1f} need {old_need:.1f}")
ok("F10b: the old rule DID count the short mouths (the bug the fix answers)",
   all(limits._along(MOUTHS[k], lambda q: idx_main.near(q, limits.MATCH_M))
       >= min(limits.ALONG_MIN_M, limits.ALONG_SHARE * limits._line_len_m(MOUTHS[k])) - 1e-6
       for k in ("a 13 m stub at 81° (Sturdee Road)", "a 9 m stub at 90° (Sibson Road)", "an 11 m stub at 89° (Melton Road)")))
# the roads the route runs along
ok("F10b: ⭐ a 200 m stretch of the route's own road counts", counts([pt(-500, 1), pt(-400, 2), pt(-300, 1)]))
ok("F10b: a 34 m limit wholly on the route counts (60 % of a short one, as before)", counts([pt(-800, 0), pt(-766, 0)]))
ok("F10b: a 12 m piece of the route's road counts", counts([pt(-1000, 1), pt(-988, 1)]))
# a piece that bends away from the drawn line while the route carries on past it (Loughborough Road, 32 m at 32°):
# the route bends with the road, so the route's line runs on through the piece's far end
BEND = [pt(-2000 + 50 * i, 0) for i in range(41)] + [pt(27, 17), pt(27 + 50 * math.cos(math.radians(32)), 17 + 50 * math.sin(math.radians(32)))]
ok("F10b: ⭐ a 32 m piece at 32° the route carries on along (it bends with the road) still counts",
   counts([pt(0, 0), pt(27, 17)], line=BEND))
# a route that TURNS INTO the side road and uses it: the mouth counts (the route really is on it)
TURN = [pt(-2000 + 50 * i, 0) for i in range(42)] + [pt(50, 50 * k) for k in range(1, 8)]
ok("F10b: ⭐ a side road the route turns into and uses counts, mouth and all (it carries on 40 m past the far end)",
   counts([pt(50, 0), pt(50, 13)], line=TURN))
# the bridge trap still holds: a long road crossing under the route
ok("F10b: the bridge trap still holds (a road crossing the route is not a hit)", not counts(ray(-1500, -200, 90, 400, 20)))
# only ever drops a hit: anything the new rule counts, the old one counted too
cases = list(MOUTHS.values()) + [[pt(-500, 1), pt(-400, 2), pt(-300, 1)], [pt(-800, 0), pt(-766, 0)], ray(-1500, -200, 90, 400, 20)]
ok("F10b: the rule only ever drops a hit (no case the old rule refused is counted now)",
   all((limits._along(c, lambda q: idx_main.near(q, limits.MATCH_M)) >= min(limits.ALONG_MIN_M, limits.ALONG_SHARE * limits._line_len_m(c)))
       or not counts(c) for c in cases))
# _matches (abnormal loads) and check_route share the rule
lims = [limit_row("w1", MOUTHS["a 13 m stub at 81° (Sturdee Road)"]), limit_row("w2", [pt(-500, 1), pt(-400, 2), pt(-300, 1)])]
got = {L["ext_id"] for L, _p, _a in limits._matches(MAIN, lims)}
ok("F10b: ⭐ _matches (an abnormal load's line) uses the same rule: the stretch counts, the mouth does not", got == {"w2"}, str(got))
src = read("backend", "limits.py")
ok("F10b: check_route and _matches both call runs_along, and neither keeps its own copy of the old rule",
   src.count("runs_along(coords, idx, L.get(\"length_m\"))") == 2 and "need = min(ALONG_MIN_M, ALONG_SHARE" in src
   and src.count("need = min(ALONG_MIN_M, ALONG_SHARE") == 1)
ok("F10b: the module's notes say why (the side-road mouth, 16 of 30 on live)", "THE SIDE-ROAD MOUTH (10 Nov 2026)" in src
   and "16 of the 30 limits live flagged" in src)

# --------------------------------------------------------------------------- #
#  F7: the break before the trip that would pass                               #
# --------------------------------------------------------------------------- #
def T(route, cyc, drive, other, dest="Site"):
    return {"route_id": route, "line_key": route, "dest_id": dest, "dest_name": dest, "drive": drive,
            "other": other, "cyc": cyc, "qty": 20.0, "unit": "t", "material": "Aggregate"}


def lorry(trips):
    return {"trips": trips, "drive": sum(t["drive"] for t in trips), "work": sum(t["drive"] + t["other"] for t in trips)}


def before_break(row, trips_by_route):
    dr = wk = 0.0
    for b in row["blocks"]:
        if b["kind"] == "break":
            return dr, wk
        t = trips_by_route[b["route_id"]]
        dr += t["drive"]
        wk += t["drive"] + t["other"]
    return None


# the mockup's Northfield Quarry lorry: three R045 round trips of 161 min, 130 driving each (2 h 10)
NQ = [T("R045", 161, 130, 31, "Tilton Viaduct site")] * 3
r = lp._lorry_rows([lorry(NQ)], 600.0, 6 * 60)[0]
ok("F7: ⭐ Northfield Quarry (the mockup): trip, trip, BREAK, trip — the break before the trip that would pass 4½ h of driving",
   [b["kind"] for b in r["blocks"]] == ["trip", "trip", "break", "trip"] and r["blocks"][2]["start"] == "11:22"
   and r["blocks"][3]["start"] == "12:07", str([(b["kind"], b["start"]) for b in r["blocks"]]))
ok("F7: ...4 h 20 of driving before the break; back at the same time as before (start + work + break)",
   before_break(r, {"R045": NQ[0]})[0] == 260.0 and r["end"] == lp._hm(6 * 60 + 3 * 161 + 45))
# the mockup's Batching Plant lorry: R022 then four R049
BP = [T("R022", 42, 30, 12, "A Site")] + [T("R049", 124.5, 61, 63.5, "B Site")] * 4
by = {"R022": BP[0], "R049": BP[1]}
r = lp._lorry_rows([lorry(BP)], 600.0, 6 * 60)[0]
dr, wk = before_break(r, by)
ok("F7: ⭐ the Batching Plant lorry (the mockup): the break after the 4th trip, before the 5th (work would pass 6 h)",
   [b["kind"] for b in r["blocks"]] == ["trip"] * 3 + ["break"] + ["trip"] * 2
   and wk <= dh.WORK_SHORT_BREAK_AFTER_MIN and dr <= dh.DRIVING_BEFORE_BREAK_MIN, str([(b["kind"], b["start"]) for b in r["blocks"]]))
# Q1: one round trip alone passes 4½ h of driving: the break falls after it
LONG = [T("R900", 330, 290, 40)]
r = lp._lorry_rows([lorry(LONG)], 600.0, 6 * 60)[0]
ok("F7: ⭐ Q1: one round trip that alone passes 4½ h of driving: the break falls after it ('about here')",
   [b["kind"] for b in r["blocks"]] == ["trip", "break"], str([b["kind"] for b in r["blocks"]]))
LONG2 = [T("R900", 330, 290, 40), T("R901", 60, 40, 20)]
r = lp._lorry_rows([lorry(LONG2)], 600.0, 6 * 60)[0]
ok("F7: ...and with a second trip behind it, the break sits between them (never before the first trip)",
   [b["kind"] for b in r["blocks"]] == ["trip", "break", "trip"])
# every packing of a spread of made-up days: the rule holds and nothing but the order and times moves
bad, moved = [], []
SHIFT = 600.0
for cyc in (42, 60, 75, 91, 110, 124.5, 140, 161, 185, 210):
    for share in (0.5, 0.62, 0.7, 0.81):
        for n in (2, 3, 5, 8, 14):
            trips = [T(f"R{int(cyc)}", cyc, round(cyc * share, 1), round(cyc * (1 - share), 1))] * n + [T("R030", 30, 20, 10)] * 3
            L = lp.pack(trips, SHIFT)
            rows = lp._lorry_rows(L, SHIFT, 7 * 60)
            for Lx, row in zip(L, rows):
                byr = {t["route_id"]: t for t in Lx["trips"]}
                if row["break_minutes"]:
                    bb = before_break(row, byr)
                    first = row["blocks"][0]
                    alone = byr[first["route_id"]]
                    single_over = alone["drive"] > dh.DRIVING_BEFORE_BREAK_MIN or alone["drive"] + alone["other"] > dh.WORK_SHORT_BREAK_AFTER_MIN
                    if bb is None or ((bb[0] > dh.DRIVING_BEFORE_BREAK_MIN + 1e-6 or bb[1] > dh.WORK_SHORT_BREAK_AFTER_MIN + 1e-6)
                                      and not (single_over and row["blocks"][1]["kind"] == "break")):
                        bad.append((cyc, share, n, row["n"], bb))
                exp_end = 7 * 60 + Lx["work"] + row["break_minutes"]
                if (row["trips"] != len(Lx["trips"]) or abs(lp._minutes_of(row["end"]) - (exp_end % 1440)) > 1
                        or row["free_minutes"] != int(round(max(0.0, SHIFT - Lx["work"] - row["break_minutes"])))):
                    moved.append((cyc, share, n, row["n"]))
ok("F7: ⭐ 200 made-up days packed: before every break, driving ≤ 4½ h and work ≤ 6 h (unless one trip alone passes, Q1)",
   not bad, str(bad[:5]))
ok("F7: ...and the lorries, their trips, the end of the day and the free time are what they were (only the order moves)",
   not moved, str(moved[:5]))
lps = read("backend", "lorry_plan.py")
ok("F7: the sheet's line says 'before 4½ h of driving or 6 h of work pass' and keeps 'about here' and 15 + 30 (Q2)",
   "about here: the rules require it before " in lps and "4½ h of driving or 6 h of work pass; it may be taken as 15 + 30." in lps
   and "require it after" not in lps)
ok("F7: the limits come from drivers_hours (no number copied into the row builder)",
   "dh.DRIVING_BEFORE_BREAK_MIN" in lps and "dh.WORK_SHORT_BREAK_AFTER_MIN" in lps
   and not re.search(r"n_dr > 270|n_wk > 360", lps))
ok("F7: the not-modelled words are kept", "NOT_MODELLED_WORDS" in read("backend", "drivers_hours.py")
   and "not a check of anyone's hours" in read("backend", "drivers_hours.py"))

# --------------------------------------------------------------------------- #
#  C2: the lorry's name on the sheets                                          #
# --------------------------------------------------------------------------- #
import conversions  # noqa: E402
FACT = {"vehicles": {"Truck mixer 8 m³ (32t)": {"labels": {"en": "Concrete mixer 8 m³ (32t)"}},
                     "Artic Tipper (44t)": {"labels": {"en": "Tipper (44t)"}}}}
_real = conversions.load_factors
conversions.load_factors = lambda *a, **k: FACT
try:
    ok("C2: ⭐ the sheets name the lorry by its label: 'Truck mixer 8 m³ (32t)' prints 'Concrete mixer 8 m³ (32t)'",
       lp._veh("Truck mixer 8 m³ (32t)") == "Concrete mixer 8 m³ (32t)" and lp._veh("Artic Tipper (44t)") == "Tipper (44t)")
    ok("C2: a key with no label reads through the vehicle word rule ('Truck mixer' -> 'Concrete mixer'), never blank",
       lp._veh("Rigid 8-wheel (32t)") == "Rigid 8-wheel (32t)" and lp._veh("Truck mixer 6 m³ (26t)").startswith("Concrete mixer"),
       lp._veh("Truck mixer 6 m³ (26t)"))
finally:
    conversions.load_factors = _real
ok("C2: ⭐ the Driver sheet's heading and both XLSX rows print _veh(blk[...]), never the stored key",
   "· {_veh(blk['vehicle'])} · lorry {r['n']} of" in lps and lps.count('_veh(blk["vehicle"]), r["n"]') == 2
   and "{blk['vehicle']} · lorry" not in lps and 'short_name(blk["name"]), blk["vehicle"]' not in lps)

# --------------------------------------------------------------------------- #
#  C1: the road card at the scheme's zoom                                      #
# --------------------------------------------------------------------------- #
def box(rid, pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (rid, "loaded", 0, pts, (min(xs), min(ys), max(xs), max(ys)))


R1 = [pt(-1000 + 100 * i, 0) for i in range(21)]
R2 = [pt(-1000 + 100 * i, 3000) for i in range(21)]
_ctx, _ans = section_select._ctx, section_select._answer
section_select._ctx = lambda: {"boxes": [box("R001", R1), box("R002", R2)], "drawn": None, "legs": None}
section_select._answer = lambda kind, geom, month, c, enter_km=None: {"kind": kind, "month": month, "routes": ["hit"]}
try:
    near = pt(0, 300)                                          # 300 m off R001: past the 120 m reach
    a = section_select.road_at(near[0], near[1], 1, 120, route="R001")
    b = section_select.road_at(near[0], near[1], 1, 120)
    c = section_select.road_at(near[0], near[1] + 1200 / KY, 1, 120, route="R001")   # 1.5 km off
    d = section_select.road_at(pt(0, 50)[0], pt(0, 50)[1], 1, 120, route="R002")       # R001 within reach, R002 far
    ok("C1: ⭐ a click naming R001, 300 m from its stored line (past the 120 m reach): R001's nearest stretch is read",
       a.get("piece") and a.get("routes") == ["hit"], str(a)[:200])
    ok("C1: the same click naming no route still finds nothing (the fallback needs the clicked line)", b.get("piece") is None)
    ok("C1: a route over 1 km away is not stretched to (ROUTE_FALLBACK_M = 1 km)", c.get("piece") is None
       and section_select.ROUTE_FALLBACK_M == 1000.0)
    ok("C1: a road within reach still wins over the clicked route's far stretch (the fallback is for 'nothing at all')",
       d.get("piece") and abs(d["piece"][0][1] - LAT0) < 0.001, str(d.get("piece"))[:120])
finally:
    section_select._ctx, section_select._answer = _ctx, _ans
mp = read("map", "index.html")
ok("C1: ⭐ the card says 'No road found here. Zoom in and click the line.' only when nothing was found at all",
   "const none = res && res.kind !== 'area' && res.piece === null && !(res.routes || []).length;" in mp
   and "'No road found here. Zoom in and click the line.'" in mp and "'No route on this road.'" in mp)

# --------------------------------------------------------------------------- #
#  F8: Check-in, not Induction                                                 #
# --------------------------------------------------------------------------- #
app = read("frontend", "index.html")
ok("F8: ⭐ 'induction' is gone from the app and the public map (every place a person reads it)",
   not re.search(r"induction", app, re.I) and not re.search(r"induction", mp, re.I))
ok("F8: ⭐ the gate form reads 'Check-in (min)' with the hover 'Minutes each lorry spends at the gate on arrival.'",
   'title="Minutes each lorry spends at the gate on arrival.">Check-in (min)</span>' in app)
ok("F8: the gate row reads '15 min check-in' with the same hover; the line under the fields and the route's cycle say check-in",
   '{g.safety_minutes} min check-in</span>' in app and app.count('title="Minutes each lorry spends at the gate on arrival."') == 2
   and "<strong>Check-in</strong>: minutes at the gate, each lorry." in app and "min check-in at the gates`" in app)
ok("F8: the map's gate popup says 'Check-in:'", "<b>Check-in:</b> ${p.safety_minutes} min" in mp)
ok("F8: the stored field is unchanged (safety_minutes is still read and written)",
   "safety_minutes: e.target.value" in app and "p.safety_minutes" in mp)
ok("F8: the guide pictures' drawing script says check-in", "induction" not in read("backend", "tools", "make_guide_images.js").lower())

print(f"test_ui_fix_demo_path.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  ✗ " + f)
sys.exit(1 if FAIL else 0)
