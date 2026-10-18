"""
UK drivers' hours for a lorry's day, 17 Oct 2026 — backend/drivers_hours.py and the places that must use it.

THE ASK (the user): "regards driving hours please use uk rules" → "a lorry's day is Shift hours a day less the breaks the
rules require, with driving capped at 9 h". Sources (gov.uk / legislation.gov.uk, checked 17 Oct 2026; notes not in git:
notes/drivers-hours-1017.md): the assimilated Reg 561/2006 Arts 6–8 (9 h driving; a 45-min break after 4.5 h driving;
11 h daily rest, so one driver's day of at most 13 h) and the Road Transport (Working Time) Regulations 2005 reg 7 (30 min
once work passes 6 h, 45 min once it passes 9 h; no more than 6 h of work without a break, so 15 min more past 12 h).

What is asserted: the break (one, never the 45 and the 30 added; the second break past 12 h), each threshold on both
sides, the 9 h cap, one driver's 13 h day (and Config NOT refusing a longer shift: a lorry can be double-shifted), the
limit named ('shift' / 'breaks' / 'driving' / 'driver_day' / 'none'), the old floor(typed shift ÷ cycle) kept beside it,
the electric day (charging is attended, so working time: on top of the break and counted when it is chosen), the split
of a cycle (gate-to-face is driving, check-in other work), the words; the public map's JavaScript twin gives the same
answers on the same cases (parse_map.js holds the same table); every place that worked trips a day out now calls the
rule (source level); 0 trips counts one lorry a trip everywhere; the gate figures keep the FULL shift.

WHAT THIS DOES NOT PROVE
------------------------
  * That the rules are the right ones for every vehicle (GB domestic rules for exempt vehicles are not modelled) or that
    a haulier keeps them: a planning figure, not a tachograph check. Weekly limits, night work, where the break falls
    and the day's other duties are not modelled.
  * route_analysis end to end is in test_phase5a.py (gates, check-in, gate-to-face) and test_phase4.py (a haul road);
    the Look-ahead's figures in test_lookahead.py; the electric day's numbers in test_carbon.py.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_drivers_hours.py
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

import drivers_hours as dh  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {detail}".strip())


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


# =========================================================================== #
#  1. The break: one, never the two added; each threshold on both sides        #
# =========================================================================== #
ok("⭐ no break for a short day: 4.5 h driving exactly and 6 h of work exactly need none (the rules say 'more than')",
   dh.break_minutes(270, 270) == 0 and dh.break_minutes(0, 360) == 0)
ok("30 min once work passes 6 h (2005 Regs reg 7), still 30 at 9 h of work exactly",
   dh.break_minutes(0, 361) == 30 and dh.break_minutes(200, 540) == 30)
ok("⭐ 45 min once driving passes 4.5 h (Art 7) or work passes 9 h",
   dh.break_minutes(271, 300) == 45 and dh.break_minutes(100, 541) == 45)
ok("🔴 the two are never added: 300 min driving and 500 min of work need ONE 45-min break, not 75",
   dh.break_minutes(300, 500) == 45 and dh.break_minutes(540, 600) == 45)
ok("⭐ the review: no more than 6 h of work without a break, so work past 12 h needs 15 min more (reg 7(1), 7(4)); "
   "12 h exactly does not", dh.break_minutes(300, 720) == 45 and dh.break_minutes(300, 721) == 60
   and dh.break_minutes(0, 721) == 60)

# =========================================================================== #
#  2. Trips a lorry a day                                                      #
# =========================================================================== #
CASES = [  # shift h, driving min a cycle, other work min a cycle -> trips, limited_by, break, the old floor
    (10, 60, 0, 9, "driving", 45, 10),     # the user's example: an all-driving hour, the 9 h cap
    (10, 69, 24, 5, "breaks", 45, 6),      # test_phase2's route: 6 cycles = 558 min of work + 45 > 600
    (10, 45, 24, 8, "shift", 45, 8),       # test_carbon's R3: 552 + 45 = 597 (3 minutes to spare)
    (10, 84, 20, 5, "shift", 45, 5),       # test_week1's 104-min cycle keeps its 5
    (10, 174, 24, 2, "breaks", 45, 3),     # test_phase4's haul road: 594 + 45 > 600
    (10, 600, 0, 0, "none", 0, 1),         # one cycle of 10 h driving: not one trip fits
    (5, 54, 0, 5, "shift", 0, 5),          # 270 min driving exactly: no break due, 5 fit 5 h
    (5, 54.01, 0, 4, "breaks", 0, 5),      # a hair over 4.5 h: the 45-min break takes one
    (13, 60, 30, 8, "shift", 45, 8),       # a 13 h day: 8 × 90 = 720 + 45 = 765 ≤ 780 (720 exactly: no second break)
    (8, 30, 30, 7, "breaks", 30, 8),       # 7 × 60 = 420 min of work: a 30-min break (driving 210)
    (13, 60, 0, 9, "driving", 45, 13),     # a 13 h day of driving: the 9 h cap, not the day
    (11, 20, 50, 8, "breaks", 45, 9),      # the 45 from WORK past 9 h (560 min), driving only 160
    (6, 30, 30, 6, "shift", 0, 6),         # 6 h of work exactly: no break due
    (9.5, 30, 30, 9, "shift", 30, 9),      # 9 h of work exactly, 4.5 h of driving exactly: still the 30
    (13, 60, 21, 8, "breaks", 45, 9),      # 9 would be 729 min of work: 45 + the second 15 = 789 > 780
    (10, 15, 5, 27, "breaks", 45, 30),     # short cycles: the 45 takes three
]
for sh, d, o, n, lim, brk, plain in CASES:
    r = dh.lorry_day(sh, d, o)
    ok(f"lorry_day({sh} h, {d} driving, {o} other) = {n} ({lim}, {brk} min break; the shift alone {plain})",
       r["trips"] == n and r["limited_by"] == lim and r["break_minutes"] == brk and r["trips_without_rules"] == plain,
       str(r))
r9 = dh.lorry_day(10, 60, 0)
ok("⭐ the result explains itself: driving and working minutes of the day, the shift, the cycle",
   r9["driving_minutes"] == 540 and r9["work_minutes"] == 540 and r9["shift_hours"] == 10 and r9["cycle_minutes"] == 60)
ok("🔴 every answer FITS: driving ≤ 9 h and work + the break ≤ the shift; one more never fits",
   all(dh.fits(dh.lorry_day(sh, d, o)["trips"], d, o, sh * 60) and not dh.fits(dh.lorry_day(sh, d, o)["trips"] + 1, d, o, sh * 60)
       for sh, d, o, *_ in CASES if dh.lorry_day(sh, d, o)["trips"] > 0))
ok("🔴 the search finds the LARGEST n that fits, checked against every n from 1 to 40 on every case",
   all(dh.lorry_day(sh, d, o)["trips"] == max([k for k in range(0, 41) if k == 0 or dh.fits(k, d, o, sh * 60)])
       for sh, d, o, *_ in CASES))
ok("a cycle of nothing makes no trips (no division by nothing)", dh.lorry_day(10, 0, 0)["trips"] == 0
   and dh.lorry_day(10, None, None)["trips"] == 0)

# =========================================================================== #
#  3. The shift: 10 h untyped; one driver's day at most 13 h; Config refuses nothing more
# =========================================================================== #
ok("⭐ the shift as typed, 10 h untyped or junk, read as at most 13 h for one driver (the 11 h daily rest) and says so",
   dh.shift_hours({"planning": {"shift_hours_per_day": 11}}) == (11.0, False)
   and dh.shift_hours({}) == (10.0, False) and dh.shift_hours({"planning": {"shift_hours_per_day": "abc"}}) == (10.0, False)
   and dh.shift_hours({"planning": {"shift_hours_per_day": 0}}) == (10.0, False)
   and dh.shift_hours({"planning": {"shift_hours_per_day": 15}}) == (13.0, True)
   and dh.typed_shift_hours({"planning": {"shift_hours_per_day": 15}}) == 15.0)
ok("the Routes page's words for a shift over 13 h; none at 13 or under",
   dh.shift_note({"planning": {"shift_hours_per_day": 13}}) is None and dh.shift_note({}) is None
   and dh.shift_note({"planning": {"shift_hours_per_day": 16}})
   == "The 16 h shift is read as 13 h for a lorry's trips: one driver's day (the 11-hour daily rest).")
_d15 = dh.lorry_day(13, 60, 30, typed_shift_h=15)
ok("⭐ a typed 15 h shift: 8 trips on one driver's 13 h, named 'driver_day' (not a break), the shift alone 10",
   _d15["trips"] == 8 and _d15["limited_by"] == "driver_day" and _d15["trips_without_rules"] == 10, str(_d15))
ok("...and its words say the 13 h day, not the break",
   dh.words(_d15) == "8 a day: as many as fit in one driver's 13 h day (the typed shift is longer) (45 min break)")

# Config: the review — a longer shift is NOT refused (a lorry can be double-shifted; the field is also a gate's
# stand-in open window). Narrowed from "Config refuses more than 13 h" (17 Oct, first build).
_tmp = tempfile.mkdtemp(prefix="dh_")
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(_tmp, "scratch.db")
import config  # noqa: E402
_doc = json.load(open(os.path.join(BACKEND, "factors.json"), encoding="utf-8"))
_doc.setdefault("planning", {})["shift_hours_per_day"] = 14
_probs = config.validate(_doc)
ok("🔴 the review: Config does NOT refuse a 14 h shift (nothing about the shift or 13 h in its problems)",
   not any("shift" in p.lower() or "13" in p for p in _probs), str(_probs))
ok("...and the refusal is gone from the source (no shift_problem anywhere)",
   "shift_problem" not in read("backend/config.py") and not hasattr(dh, "shift_problem"))

# =========================================================================== #
#  4. The split of a cycle, and the electric day                               #
# =========================================================================== #
_parts = {"unloading_minutes": 20.0, "safety_minutes": 5.0, "internal_travel_minutes": 6.0}
ok("⭐ the split: both legs + gate-to-face are DRIVING; loading, unloading and the gate check-in are OTHER WORK",
   dh.split_cycle(0.5, 0.4, _parts) == (60.0, 25.0) and dh.split_cycle(1.0, 0, None) == (60.0, 0.0))
ok("the electric day: charging comes ON TOP of the break (10 h, 60 + 0 a cycle, 20 min charging: 8 × 60 + 20 + 45 ≤ 600; "
   "9 × 60 + 20 is work past 9 h, + 45 > 600)",
   dh.ev_trips(10, 60, 0, lambda n: 20.0) == 8 and dh.ev_trips(10, 30, 30, lambda n: 0.0) == dh.lorry_day(10, 30, 30)["trips"]
   and dh.ev_trips(10, 30, 30, lambda n: 60.0) < dh.lorry_day(10, 30, 30)["trips"])
ok("⭐ the review: charging is WORKING TIME, counted when the break is chosen — 10 h, 30 + 30 a cycle, 30 min charging: "
   "9 trips would be 540 + 30 = 570 min of work (past 9 h → 45) = 615 > 600, so 8 (on top of a 30 break it would be 9)",
   dh.ev_trips(10, 30, 30, lambda n: 30.0) == 8 and dh.fits(9, 30, 30, 600) and not dh.fits(9, 30, 30, 600, extra_min=30.0))

# =========================================================================== #
#  5. The words                                                                #
# =========================================================================== #
ok("the words name the limit and the break", dh.words(dh.lorry_day(10, 60, 0)) == "9 a day: capped by the 9 h a day driving limit (45 min break)"
   and dh.words(dh.lorry_day(10, 600, 0)) == "One round trip does not fit in a driver's day: counted as one lorry a trip"
   and dh.words(dh.lorry_day(10, 69, 24)) == "5 a day: 1 fewer than the shift alone would hold: the required break takes the time (45 min break)")
ok("⭐ the review: the words count what the break took ('3 fewer'), not 'one fewer' for every case",
   dh.words(dh.lorry_day(10, 15, 5)) == "27 a day: 3 fewer than the shift alone would hold: the required break takes the time (45 min break)")
ok("🔴 the words a person reads say lorry-free plain English: no 'truck', no 'baked', no 'compliant' / 'legal' claim",
   not re.search(r"\b(trucks?|bak\w*|compliant|compliance|legal)\b",
                 dh.RULE_WORDS + " " + dh.NOT_MODELLED_WORDS + " " + " ".join(dh.LIMIT_WORDS.values()), re.I))
ok("the rule words say ONE break (the 45 covers the 30) and the caveat says what is not modelled",
   "the break the UK drivers' hours rules require" in dh.RULE_WORDS and "breaks" not in dh.RULE_WORDS
   and dh.NOT_MODELLED_WORDS.startswith("A planning figure, not a check of anyone's hours:")
   and "weekly limits" in dh.NOT_MODELLED_WORDS and "other duties" in dh.NOT_MODELLED_WORDS)

# =========================================================================== #
#  6. One rule everywhere (source level), and the gate keeps the full shift     #
# =========================================================================== #
_net = read("backend/network.py")
ok("⭐ network.py: route_analysis AND the public map's route figures call drivers_hours.lorry_day; no shift // cycle left",
   _net.count("drivers_hours.lorry_day(") == 2 and "shift_hr // cycle_hr" not in _net
   and "drivers_hours.split_cycle(l_hr, r_hr, parts)" in _net and "drivers_hours.split_cycle(out_hr, back_hr, _parts)" in _net)
ok("...each row carries the driving and other-work minutes and the lorry's day in parts and words; the trips on one "
   "driver's day against the TYPED shift; planning carries the rule, the 13 h note and the caveat",
   '"drive_min": round(drive_min, 2), "other_work_min": round(other_min, 2),' in _net
   and '"trips_without_rules": day["trips_without_rules"],' in _net and '"words": drivers_hours.words(day)}' in _net
   and "drivers_hours.lorry_day(shift_hr, drive_min, other_min, typed_shift_h=typed_shift_hr)" in _net
   and '"drivers_hours": drivers_hours.RULE_WORDS, "shift_capped": shift_capped,' in _net
   and '"shift_note": drivers_hours.shift_note(factors), "not_modelled": drivers_hours.NOT_MODELLED_WORDS},' in _net)
_carb = read("backend/carbon.py")
ok("carbon.py: the swapped route and the electric day use the rule (no shift ÷ cycle anywhere)",
   "// cycle_min" not in _carb and "shift_min // cyc" not in _carb and "drivers_hours.lorry_day(" in _carb
   and "drivers_hours.ev_trips(shift_h, drv, oth" in _carb)
ok("the review: carbon.py at the route's own distance READS the row's trips and split (no recomputing from rounded hours)",
   'if scale == 1.0 and row.get("drive_min") is not None:' in _carb and 'cycles = int(row.get("trips_per_day") or 0)' in _carb
   and "drive_min=line_drive, other_min=line_other)" in _carb)
_der = read("backend/derived.py")
ok("derived.py READS the row (never recomputes) and passes the driving and other-work minutes and the lorry's day on",
   '"drive_min": (row.get("drive_min") if baked else None),' in _der
   and '"other_work_min": (row.get("other_work_min") if baked else None),' in _der
   and '"lorry_day": (row.get("lorry_day") if baked else None),' in _der
   and "shift_min / cycle_min" not in _der.split('"""', 2)[2])
_gh, _ga = read("backend/gate_hours.py"), read("backend/gate_arrivals.py")
ok("🔴 the gate figures keep the FULL shift (a gate stays open while drivers take breaks): gate_hours and gate_arrivals "
   "never call the drivers' hours rule", "drivers_hours" not in _gh and "drivers_hours" not in _ga
   and "drivers_hours" not in read("backend/sim.py"))

# =========================================================================== #
#  7. 0 trips = one lorry a trip, in every reader (the review)                  #
# =========================================================================== #
import carbon  # noqa: E402
ok("⭐ carbon.lorries_for: 0 cycles a day (not one round trip fits) counts one lorry a trip; None only when not routed",
   carbon.lorries_for(44, 0, 22) == 2 and carbon.lorries_for(44, None, 22) is None and carbon.lorries_for(0, 0, 22) == 0
   and carbon.lorries_for(44, 2, 22) == 1)
_cl = read("backend/costlines.py")
ok("costlines: the vehicles on a routed line with 0 cycles are ceil(trips ÷ working days), never 0",
   'int(-(-f["trips"] // (max(1, cycles) * work_days))) if (baked and f["trips"] > 0)' in _cl)
ok("main.py: a routed line with 0 trips a day reads one trip a lorry-day (the same floor), never 'not routed'",
   'tpv = max(1, int(row.get("trips_per_day") or 0))' in read("backend/main.py"))
ok("carbon.ev_day: a battery that holds the trip but a day that holds none is NOT infeasible (day_fits False)",
   "return dict(out, cycles=0, day_fits=False)" in _carb and "return dict(out, cycles=0, feasible=False)" not in _carb)

# =========================================================================== #
#  8. The public map's JavaScript twin: the same cases, the same answers       #
# =========================================================================== #
_map = read("map/index.html")
ok("⭐ the map's drawer applies the same rule (lorryDayTrips) instead of shift ÷ cycle, and says so on the card",
   "function lorryDayTrips(shiftH, driveMin, otherMin)" in _map and "P.shift_hours_per_day/cycleH" not in _map
   and "' h shift less breaks, at most 9 h driving, '" in _map)
ok("the review: the drawer reads the SERVER's trips a day for the route when it has them (the routed cycle), and the "
   "rough estimate only without; 0 counts one lorry a trip",
   "const fromServer = typeof info.trips_per_day==='number';" in _map
   and "cur.trips_per_day=f.properties.trips_per_day; cur.cycle_hr=f.properties.cycle_hr;" in _map
   and "Math.ceil(peakLoads/(Math.max(1, tripsPerDay)*P.working_days_per_month))" in _map)
_js = read("backend/tests/parse_map.js")
ok("parse_map.js runs lorryDayTrips on THIS table (the two languages are held to one answer)",
   all(f"[{sh}, {d}, {o}, {n}]" in _js for sh, d, o, n, *_ in CASES), "")

try:
    import portable  # noqa: E402
    portable.remove_scratch_db(db, _tmp)
except Exception:
    pass

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
