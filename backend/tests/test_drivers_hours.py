"""
UK drivers' hours for a lorry's day, 17 Oct 2026 — backend/drivers_hours.py and the places that must use it.

THE ASK (the user): "regards driving hours please use uk rules" → "a lorry's day is Shift hours a day less the breaks the
rules require, with driving capped at 9 h". Sources (gov.uk / legislation.gov.uk, checked 17 Oct 2026; notes not in git:
notes/drivers-hours-1017.md): the assimilated Reg 561/2006 Arts 6–8 (9 h driving; a 45-min break after 4.5 h driving;
11 h daily rest, so a day of at most 13 h) and the Road Transport (Working Time) Regulations 2005 reg 5 (30 min after 6 h
of work, 45 min after 9 h).

What is asserted: the break (one, never two added), each threshold on both sides, the 9 h cap, the 13 h shift cap, the
limit named ('shift' / 'breaks' / 'driving' / 'none'), the old floor(shift ÷ cycle) kept beside it, the electric day
(charging on top of the break), the split of a cycle (gate-to-face is driving, check-in other work), Config's refusal over
13 h, the words; the public map's JavaScript twin gives the same answers on the same cases (parse_map.js holds the same
table); every place that worked trips a day out now calls the rule (source level); the gate figures keep the FULL shift.

WHAT THIS DOES NOT PROVE
------------------------
  * That the rules are the right ones for every vehicle (GB domestic rules for exempt vehicles are not modelled) or that
    a haulier keeps them: a planning figure, not a tachograph check. Weekly limits and night work are not modelled.
  * route_analysis end to end is in test_phase5a.py (gates, check-in, gate-to-face) and test_phase4.py (a haul road);
    the Look-ahead's figures in test_lookahead.py; the electric day's numbers in test_carbon.py.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_drivers_hours.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

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
#  1. The break: one, never two added; each threshold on both sides            #
# =========================================================================== #
ok("⭐ no break for a short day: 4.5 h driving exactly and 6 h of work exactly need none (the rules say 'more than')",
   dh.break_minutes(270, 270) == 0 and dh.break_minutes(0, 360) == 0)
ok("30 min once work passes 6 h (2005 Regs reg 5), still 30 at 9 h of work exactly",
   dh.break_minutes(0, 361) == 30 and dh.break_minutes(200, 540) == 30)
ok("⭐ 45 min once driving passes 4.5 h (Art 7) or work passes 9 h",
   dh.break_minutes(271, 300) == 45 and dh.break_minutes(100, 541) == 45)
ok("🔴 the two are never added: 300 min driving and 500 min of work need ONE 45-min break, not 75",
   dh.break_minutes(300, 500) == 45 and dh.break_minutes(540, 600) == 45)

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
    (13, 60, 30, 8, "shift", 45, 8),       # a 13 h day: 8 × 90 = 720 + 45 = 765 ≤ 780
    (8, 30, 30, 7, "breaks", 30, 8),       # 7 × 60 = 420 min of work: a 30-min break (driving 210)
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
ok("a cycle of nothing makes no trips (no division by nothing)", dh.lorry_day(10, 0, 0)["trips"] == 0
   and dh.lorry_day(10, None, None)["trips"] == 0)

# =========================================================================== #
#  3. The shift: 10 h untyped, at most 13 h; Config refuses more                #
# =========================================================================== #
ok("⭐ the shift as typed, 10 h untyped or junk, CAPPED at 13 h (the 11 h daily rest) and says so",
   dh.shift_hours({"planning": {"shift_hours_per_day": 11}}) == (11.0, False)
   and dh.shift_hours({}) == (10.0, False) and dh.shift_hours({"planning": {"shift_hours_per_day": "abc"}}) == (10.0, False)
   and dh.shift_hours({"planning": {"shift_hours_per_day": 0}}) == (10.0, False)
   and dh.shift_hours({"planning": {"shift_hours_per_day": 15}}) == (13.0, True))
ok("Config's words for a shift over 13 h name the rule; 13 itself is allowed",
   dh.shift_problem(13) is None and dh.shift_problem(10) is None and dh.shift_problem("x") is None
   and dh.shift_problem(13.5) == "Shift hours a day: at most 13 — a driver's daily rest is 11 hours in every 24 under the UK drivers' hours rules")
ok("🔴 config.validate runs it (a Save over 13 h is refused in those words)",
   "drivers_hours.shift_problem(plan.get(\"shift_hours_per_day\"))" in read("backend/config.py"))

# =========================================================================== #
#  4. The split of a cycle, and the electric day                               #
# =========================================================================== #
_parts = {"unloading_minutes": 20.0, "safety_minutes": 5.0, "internal_travel_minutes": 6.0}
ok("⭐ the split: both legs + gate-to-face are DRIVING; loading, unloading and the gate check-in are OTHER WORK",
   dh.split_cycle(0.5, 0.4, _parts) == (60.0, 25.0) and dh.split_cycle(1.0, 0, None) == (60.0, 0.0))
ok("the electric day: charging comes ON TOP of the break (10 h, 60 + 0 a cycle, 20 min charging: 8 × 60 + 20 + 45 ≤ 600; 9 × 60 > 540 driving)",
   dh.ev_trips(10, 60, 0, lambda n: 20.0) == 8 and dh.ev_trips(10, 30, 30, lambda n: 0.0) == dh.lorry_day(10, 30, 30)["trips"]
   and dh.ev_trips(10, 30, 30, lambda n: 60.0) < dh.lorry_day(10, 30, 30)["trips"])

# =========================================================================== #
#  5. The words                                                                #
# =========================================================================== #
ok("the words name the limit and the break", dh.words(dh.lorry_day(10, 60, 0)) == "9 a day: capped by the 9 h a day driving limit (45 min break)"
   and dh.words(dh.lorry_day(10, 600, 0)) == "One round trip does not fit in a driver's day"
   and dh.words(dh.lorry_day(10, 69, 24)).startswith("5 a day: one fewer than the shift alone would hold"))
ok("🔴 the words a person reads say lorry-free plain English: no 'truck', no 'baked', no 'compliant' / 'legal' claim",
   not re.search(r"\b(trucks?|bak\w*|compliant|compliance|legal)\b", dh.RULE_WORDS + " ".join(dh.LIMIT_WORDS.values()), re.I))

# =========================================================================== #
#  6. One rule everywhere (source level), and the gate keeps the full shift     #
# =========================================================================== #
_net = read("backend/network.py")
ok("⭐ network.py: route_analysis AND the public map's route figures call drivers_hours.lorry_day; no shift // cycle left",
   _net.count("drivers_hours.lorry_day(") == 2 and "shift_hr // cycle_hr" not in _net
   and "drivers_hours.split_cycle(l_hr, r_hr, parts)" in _net and "drivers_hours.split_cycle(out_hr, back_hr, _parts)" in _net)
ok("...each row carries the driving and other-work minutes and the lorry's day in parts and words",
   '"drive_min": round(drive_min, 2), "other_work_min": round(other_min, 2),' in _net
   and '"trips_without_rules": day["trips_without_rules"],' in _net and '"words": drivers_hours.words(day)}' in _net
   and '"drivers_hours": drivers_hours.RULE_WORDS, "shift_capped": shift_capped}' in _net)
_carb = read("backend/carbon.py")
ok("carbon.py: the swapped route and the electric day use the rule (no shift ÷ cycle anywhere)",
   "// cycle_min" not in _carb and "shift_min // cyc" not in _carb and "drivers_hours.lorry_day(" in _carb
   and "drivers_hours.ev_trips(shift_h, drv, oth" in _carb)
ok("derived.py READS the row (never recomputes) and passes the driving minutes and the lorry's day on",
   '"drive_min": (row.get("drive_min") if baked else None),' in read("backend/derived.py")
   and '"lorry_day": (row.get("lorry_day") if baked else None),' in read("backend/derived.py")
   and "shift_min / cycle_min" not in read("backend/derived.py").split('"""', 2)[2])
_gh, _ga = read("backend/gate_hours.py"), read("backend/gate_arrivals.py")
ok("🔴 the gate figures keep the FULL shift (a gate stays open while drivers take breaks): gate_hours and gate_arrivals "
   "never call the drivers' hours rule", "drivers_hours" not in _gh and "drivers_hours" not in _ga
   and "drivers_hours" not in read("backend/sim.py"))

# =========================================================================== #
#  7. The public map's JavaScript twin: the same cases, the same answers       #
# =========================================================================== #
_map = read("map/index.html")
ok("⭐ the map's drawer applies the same rule (lorryDayTrips) instead of shift ÷ cycle, and says so on the card",
   "function lorryDayTrips(shiftH, driveMin, otherMin)" in _map and "P.shift_hours_per_day/cycleH" not in _map
   and "' h shift less breaks, at most 9 h driving, '" in _map)
_js = read("backend/tests/parse_map.js")
ok("parse_map.js runs lorryDayTrips on THIS table (the two languages are held to one answer)",
   all(f"[{sh}, {d}, {o}, {n}]" in _js for sh, d, o, n, *_ in CASES), "")

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
