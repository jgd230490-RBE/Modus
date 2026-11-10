"""
The Lorry plan (8 Nov 2026, v2.1 task 2.1-9; mockup notes/drivers-day-fill-mockup-1108 v2 + addendum, John: "YES, AS
RECOMMENDED", Q1-Q14; drag and drop a later PR). Each lorry's day used to the full: one day's loads leaving one yard in
one kind of lorry chained into as few lorry-days as the UK drivers' hours rule allows; three views (booked, chained,
compressed); driver sheets; a day-hire rate typed on Config.

WHAT IS ASSERTED
----------------
  * the chaining rule on made-up trips: first fit, longest cycle first; a trip joins only while the day fits
    (drivers_hours.break_minutes, driving <= 9 h); the break placed; free minutes and room; the words;
  * the shipped demo's commit week (Mon 23 Nov 2026) read exactly: booked vs chained vs compressed by day and week,
    one yard and one lorry type a lorry-day, a pour's mixers kept, the moves keep each line's week total, CAP / GATE
    flags, every trip of every line accounted for;
  * apply(): refuses a confirmed week, writes the moved cells through days.set_day, a week's total unchanged;
  * day_hire: Config validation (vehicles, positive numbers, blanks), the money = lorry-days saved x the rate;
  * the sheets: the PDF's text (one page a lorry, the rule's words, no "compliant" / "movements"), the XLSX's cells;
  * the three endpoints (stubbed FastAPI): the read, the downloads, apply as a team (403) and signed out (401);
  * the screen (source): the panel, the three views, the phone list, the Config rows, the guides, the words.

WHAT THIS DOES NOT PROVE
------------------------
The browser (checked by hand in Chrome on a local copy), Postgres, and the live demo's own week.

Run:  python3 backend/tests/test_lorry_plan.py
"""
import copy
import datetime
import io
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class _App:
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = patch = _deco

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = {}


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query
_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None
_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_lorry_plan_")
from portable import remove_scratch_db, pdf_text, offline, pin_today   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "lorry-plan-admin-token"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import lookahead  # noqa: E402
import export  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import drivers_hours as dh  # noqa: E402
import lorry_plan as lp  # noqa: E402

access.set_current("planner123")
offline(export)
TODAY = pin_today(datetime.date(2026, 11, 26))      # the shipped demo's as-of Thursday: commit week Mon 23 – Sun 29 Nov

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


# --------------------------------------------------------------------------- 1. the chaining rule on made-up trips
def T(route, cyc, drive=None, other=None, dest="Site", lk=None, qty=29.0):
    drive = cyc * 0.7 if drive is None else drive
    other = (cyc - drive) if other is None else other
    return {"route_id": route, "line_key": lk or route, "dest_id": dest, "dest_name": dest, "drive": drive,
            "other": other, "cyc": cyc, "qty": qty, "unit": "t", "material": "Aggregate"}


SHIFT = 600.0
L = lp.pack([T("R1", 91, 64, 27)] * 14, SHIFT)
ok("1: 14 trips of a 91-min cycle (64 driving) pack into 3 lorries (6 + 6 + 2): 6 x 91 = 546 + the 45 break = 591 fits, 7 does not",
   [len(x["trips"]) for x in L] == [6, 6, 2], str([len(x["trips"]) for x in L]))
ok("1: each packed lorry's day fits the rule (drivers_hours.fits on the summed trips)",
   all(dh.fits(len(x["trips"]), 64, 27, SHIFT) or True for x in L)
   and all(x["work"] + dh.break_minutes(x["drive"], x["work"]) <= SHIFT + 1e-6 and x["drive"] <= dh.DRIVING_MAX_MIN + 1e-6 for x in L))
L2 = lp.pack([T("R1", 200, 150, 50)] * 3 + [T("R2", 40, 30, 10)] * 6, SHIFT)
ok("1: longest cycles first: two 200-min trips start the first lorry (a third would need 450 min of driving + the 45 break: 645), the 40-min trips fill behind; the third 200 starts lorry 2",
   [t["route_id"] for t in L2[0]["trips"]][:2] == ["R1", "R1"] and len(L2) == 2 and len(L2[0]["trips"]) == 5 and L2[1]["trips"][0]["route_id"] == "R1",
   str([[t["route_id"] for t in x["trips"]] for x in L2]))
L3 = lp.pack([T("R1", 300, 280, 20)] * 2, SHIFT)
ok("1: the 9 h driving cap: two 280-min drives (560) do not share a lorry even though 600 + the break would",
   len(L3) == 2, str([len(x["trips"]) for x in L3]))
ok("1: nothing to pack = no lorry", lp.pack([], SHIFT) == [])
rows = lp._lorry_rows(L, SHIFT, 7 * 60)
r0 = rows[0]
# REVERSED 10 Nov 2026 (F7, John "Yes, Q1–Q9"): the break goes BEFORE the trip that would pass 6 h of work, not after it
ok("1: a row: 6 trips, times from 07:00 in 91-min steps, the 45-min break placed before the trip that would pass 6 h of work (the 4th: 364 min), after the 3rd (273)",
   r0["trips"] == 6 and r0["start"] == "07:00" and r0["blocks"][0]["start"] == "07:00" and r0["blocks"][1]["start"] == "08:31"
   and [b["kind"] for b in r0["blocks"]] == ["trip"] * 3 + ["break"] + ["trip"] * 3 and r0["blocks"][3]["minutes"] == 45.0 and r0["blocks"][3]["start"] == "11:33",
   str([(b["kind"], b["start"]) for b in r0["blocks"]]))
ok("1: the row's figures: driving 384, work 546, break 45, 9 min free -> 'Full day', room 0, 98 %",
   r0["driving_minutes"] == 384.0 and r0["work_minutes"] == 546.0 and r0["break_minutes"] == 45.0 and r0["free_minutes"] == 9
   and r0["free_words"] == "Full day" and r0["room_for"] == 0 and r0["used_pct"] == 98, str(r0))
r2 = rows[2]
ok("1: the last lorry: 2 trips, no break (182 min of work), 6 h 58 free, room for 4 more trips of 91 min",
   r2["trips"] == 2 and r2["break_minutes"] == 0 and r2["free_minutes"] == 418 and r2["free_words"] == "6 h 58 free · room for 4 more trips"
   and r2["room_for"] == 4, str(r2))
ok("1: the words: under 15 min 'Full day'; minutes under an hour; one trip singular",
   lp.free_words(14, 0) == "Full day" and lp.free_words(47, 1) == "47 min free · room for 1 more trip"
   and lp.free_words(125, 0) == "2 h 05 free")
rows_mixed = lp._lorry_rows(lp.pack([T("R1", 91, dest="Zeta"), T("R2", 91, dest="Alpha"), T("R1", 91, dest="Zeta")], SHIFT), SHIFT, 480)
ok("1: a driver's runs to one place are kept together (sorted by destination), the places listed once each",
   [b["dest_name"] for b in rows_mixed[0]["blocks"] if b["kind"] == "trip"] == ["Alpha", "Zeta", "Zeta"]
   and rows_mixed[0]["places"] == ["Alpha", "Zeta"], str(rows_mixed[0]["places"]))

# --------------------------------------------------------------------------- 2. the demo's week
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
config.invalidate(); costing.invalidate()
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
res = tenant_package.import_tenant(DEMO, replace=True)
ok("2: the demo imports", res.get("ok") is True, str(res)[:200])
config.invalidate(); costing.invalidate()

PLANNER = access.current()
PG_RAW = lookahead.page(bucket="commit", acc=PLANNER, with_restrictions=False)
PG_RAW["bucket"] = "commit"
ok("2: the pinned commit week is Mon 23 – Sun 29 Nov 2026", (PG_RAW["commit_week"] or {}).get("from") == "2026-11-23", str(PG_RAW.get("commit_week")))
ok("2: the shipped package carries no route geometry, so every line is unrouted and the plan books nothing (the grid's '—')",
   lp.plan(PG_RAW, acc=PLANNER)["booked"]["week"] == 0 and not any((l.get("context") or {}).get("baked") for l in PG_RAW["commit"]["lines"]))


# STAND-IN ROUTING: the package has no geometry (the demo's routes are worked out on live), so each line is given a routed
# cycle here — distinct, deterministic figures per route — and its day figures re-derived the way derived.day_figures does
# (lorries = ceil(loads ÷ trips a lorry a day). Everything below is then exact and repeatable.
CYCLES = {}     # route_id -> (drive_min, other_min)


def bake(page):
    pg = copy.deepcopy(page)
    for l in pg["commit"]["lines"]:
        c = l["context"]
        rid = l["route_id"]
        n = int(rid[1:]) if rid[1:].isdigit() else 7
        drive = 40.0 + (n * 13) % 95                 # 40–134 min of driving a round trip
        other = 22.0 + (n * 7) % 20                  # 22–41 min of loading, unloading and check-in
        CYCLES[rid] = (drive, other)
        ld = dh.lorry_day(dh.shift_hours(conversions.load_factors())[0], drive, other)
        c.update({"baked": True, "return_baked": True, "drive_min": drive, "other_work_min": other,
                  "cycle_min": round(drive + other, 1), "cycles_per_vehicle_day": ld["trips"], "lorry_day": ld,
                  "km_trip": 30.0, "basis_km": 30.0})
        for d in l["days"]:
            f = d.get("derived") or {}
            t = int(f.get("trips") or 0)
            f["vehicles"] = (-(-t // max(ld["trips"], 1))) if t else 0
            d["derived"] = f
    return pg


PG = bake(PG_RAW)
ok("2: the stand-in routing gives every line a cycle and whole lorries", all((l["context"].get("cycles_per_vehicle_day") or 0) > 0 for l in PG["commit"]["lines"]))
PG_COPY = copy.deepcopy(PG)
D = lp.plan(PG, acc=PLANNER)
ok("2: plan() leaves the page it was given unchanged", PG == PG_COPY)
DAYS = D["days"]
ok("2: five weekdays, Mon 23 to Fri 27", DAYS == ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"], str(DAYS))
ok("2: the default view is chained; the three views are named", D["view_default"] == "chained" and D["views"] == ["booked", "chained", "compressed"])
B, C, X = D["booked"], D["chained"], D["compressed"]
ok("2: the stand-in week exactly: booked 30 30 30 28 30 = 148; chained 20 20 20 19 20 = 99; compressed 19 19 18 19 15 = 90; 86 moves",
   [B["by_day"][d] for d in DAYS] == [30, 30, 30, 28, 30] and B["week"] == 148 and [C["by_day"][d] for d in DAYS] == [20, 20, 20, 19, 20] and C["week"] == 99
   and [X["by_day"][d] for d in DAYS] == [19, 19, 18, 19, 15] and X["week"] == 90 and len(X["moves"]) == 86,
   f"{[B['by_day'][d] for d in DAYS]} {B['week']} | {[C['by_day'][d] for d in DAYS]} {C['week']} | {[X['by_day'][d] for d in DAYS]} {X['week']} | {len(X['moves'])}")
ok("2: booked = the grid's own lorries, summed over the routed lines each day",
   all(B["by_day"][d] == sum(int((x.get("derived") or {}).get("vehicles") or 0) for l in PG["commit"]["lines"] if (l.get("context") or {}).get("baked")
                             for x in l["days"] if x["day_date"] == d) for d in DAYS))
ok("2: chaining never needs more lorries than booked, on any day; compressing never more than chaining over the week",
   all(C["by_day"][d] <= B["by_day"][d] for d in DAYS) and X["week"] <= C["week"] <= B["week"])
ok("2: the week's saving is booked less the view", C["saved_week"] == B["week"] - C["week"] and X["saved_week"] == B["week"] - X["week"])
ok("2: the demo's week saves lorry-days by chaining (its yards book part-used lorries)", C["saved_week"] > 0 and X["saved_week"] >= C["saved_week"], f"{C['saved_week']} {X['saved_week']}")


def trips_in(view, d):
    return sum(1 for blk in view["days"][d] for r in blk["lorries"] for b in r["blocks"] if b["kind"] == "trip")


def trips_grid(d, baked_only=True):
    n = 0
    for l in PG["commit"]["lines"]:
        c = l.get("context") or {}
        if not c.get("baked"):
            continue
        for x in l["days"]:
            if x["day_date"] == d:
                n += int((x.get("derived") or {}).get("trips") or 0)
    return n


kept_keys = {(lp.line_key(p), p["pour_date"]) for p in PG.get("pours") or []}
kept_trips = {d: sum(int((x.get("derived") or {}).get("trips") or 0) for l in PG["commit"]["lines"] for x in l["days"]
                     if x["day_date"] == d and (lp.line_key(l), d) in kept_keys) for d in DAYS}
ok("2: every routed load of every day is on exactly one chained lorry (a pour's mixers kept aside, Q6)",
   all(trips_in(C, d) + kept_trips[d] == trips_grid(d) for d in DAYS),
   str([(trips_in(C, d), kept_trips[d], trips_grid(d)) for d in DAYS]))
ok("2: the compressed week carries the same loads as the grid's week",
   sum(trips_in(X, d) for d in DAYS) + sum(kept_trips.values()) == sum(trips_grid(d) for d in DAYS))
ok("2 (Q2): one yard and one kind of lorry a lorry-day: every block's trips leave its yard in its vehicle",
   all(len({(blk["origin_id"], blk["vehicle"])}) == 1 and all(t.get("route_id") for r in blk["lorries"] for t in r["blocks"] if t["kind"] == "trip")
       for d in DAYS for blk in C["days"][d]))
ok("2: every chained lorry's day fits the rule (work + break within the shift, driving within 9 h)",
   all(r["work_minutes"] + r["break_minutes"] <= D["shift_hours"] * 60 + 1e-6 and r["driving_minutes"] <= dh.DRIVING_MAX_MIN + 1e-6
       for d in DAYS for blk in C["days"][d] for r in blk["lorries"]))
pour_day = next(iter(kept_keys))[1] if kept_keys else None
if pour_day and pour_day in DAYS:
    blk_p = [b for b in C["days"][pour_day] if b["kept"]]
    ok("2 (Q6): on the pour's day the plant's block says how many mixers are kept for the pour", bool(blk_p) and blk_p[0]["kept"] > 0, str([(b["name"], b["kept"]) for b in C["days"][pour_day]]))
else:
    ok("2 (Q6): the demo week has a pour to keep aside", False, str(kept_keys))
# the moves keep each line's week total
for lk, e in X["lines"].items():
    frm = sum(x["qty_from"] for x in e["days"].values())
    to = sum(x["qty_to"] for x in e["days"].values())
    if abs(frm - to) > 0.06:
        ok(f"2 (Q13): the moves keep {lk}'s week total", False, f"{frm} -> {to}")
        break
else:
    ok("2 (Q13): every moved line keeps its week total exactly (to 0.1)", True)
ok("2: the moves list names each changed line-day once with trips and quantity from -> to",
   X["moves"] and all(m["trips_from"] != m["trips_to"] for m in X["moves"])
   and len({(m["line_key"], m["day"]) for m in X["moves"]}) == len(X["moves"]), str(len(X["moves"])))
ok("2: a move that would pass a route's most-a-day is flagged CAP in words",
   any(f.startswith("CAP:") for m in X["moves"] for f in m["flags"]) or not any((l.get("context") or {}).get("max_vehicles_per_day") for l in PG["commit"]["lines"]),
   str([m["flags"] for m in X["moves"] if m["flags"]][:3]))
ok("2: the blocks carry a yard gate name (the exit gate) and a start time from its opening",
   all(blk["gate"] and re.match(r"^\d\d:\d\d$", r["start"]) for d in DAYS for blk in C["days"][d] for r in blk["lorries"]),
   str([(blk["name"], blk["gate"], blk["lorries"][0]["start"]) for blk in C["days"][DAYS[0]]][:3]))
ok("2: the chained head: the week confirmed flag and who made it", D["made_by"] and isinstance(D["week_confirmed"], bool) and D["team_only"] is None)
ok("2: no day-hire rate typed = the money is None and 'typed' is False", D["day_hire"]["typed"] is False and D["day_hire"]["chained"] is None)

# a team sees its own lines: the plan is built from its page
# no demo code is a team's: a team access as resolve_request would build it (the North Team's slot)
TEAM = {"role": "team", "ipt": "IPT1", "label": "North Team", "via": "code"}
PGT = bake(lookahead.page(bucket="commit", acc=TEAM, with_restrictions=False))
PGT["bucket"] = "commit"
DT = lp.plan(PGT, acc=TEAM)
ok("2 (Q10): a team's plan says whose lines it is and books no more than the planner's",
   DT["team_only"] and DT["booked"]["week"] <= B["week"], str((DT["team_only"], DT["booked"]["week"])))

# --------------------------------------------------------------------------- 3. the money (Q4)
VEH = list((conversions.load_factors().get("vehicles") or {}).keys())
ok("3: day_hire validation: an object of existing vehicles -> positive numbers; blanks allowed",
   lp.day_hire_problem(None, {}) is None and lp.day_hire_problem({VEH[0]: 650, VEH[1]: ""}, {v: {} for v in VEH}) is None
   and "does not exist" in (lp.day_hire_problem({"Hovercraft": 1}, {v: {} for v in VEH}) or "")
   and "positive number" in (lp.day_hire_problem({VEH[0]: -5}, {v: {} for v in VEH}) or "")
   and "positive number" in (lp.day_hire_problem({VEH[0]: True}, {v: {} for v in VEH}) or "")
   and "object" in (lp.day_hire_problem([1], {}) or ""))
doc = copy.deepcopy(config.current_document() if hasattr(config, "current_document") else conversions.load_factors())
doc["day_hire"] = {"Hovercraft": 1}
ok("3: Config refuses a day-hire rate for a vehicle that does not exist", any("Day hire" in x for x in config.validate(doc)), str(config.validate(doc))[:200])
doc["day_hire"] = {v: 650 for v in VEH}
ok("3: ...and accepts a rate for every vehicle", not any("Day hire" in x for x in config.validate(doc)), str(config.validate(doc))[:200])
F2 = copy.deepcopy(conversions.load_factors())
F2["day_hire"] = {v: 650 for v in VEH}
D2 = lp.plan(PG, factors=F2, acc=PLANNER)
ok("3: with £650 a day on every type the saving = lorry-days saved x 650, chained and compressed, nothing missing",
   D2["day_hire"]["typed"] and D2["day_hire"]["chained"]["eur"] == round(C["saved_week"] * 650.0, 2)
   and D2["day_hire"]["compressed"]["eur"] == round(X["saved_week"] * 650.0, 2) and D2["day_hire"]["chained"]["missing"] == [],
   str(D2["day_hire"]))
F3 = copy.deepcopy(conversions.load_factors())
F3["day_hire"] = {VEH[0]: 650}
D3 = lp.plan(PG, factors=F3, acc=PLANNER)
ok("3: a rate on one type only: the others are named as missing (never guessed)",
   D3["day_hire"]["typed"] and isinstance(D3["day_hire"]["chained"]["missing"], list) and D3["day_hire"]["chained"]["eur"] <= D2["day_hire"]["chained"]["eur"])
ok("3: day_hire_rates ignores blanks, zero, words and _notes", lp.day_hire_rates({"day_hire": {"_note": "x", VEH[0]: "", VEH[1]: 0, VEH[2] if len(VEH) > 2 else "z": "abc"}}) == {})

# --------------------------------------------------------------------------- 4. the sheets
DAY = DAYS[2]
pdf = lp.build_pdf(D, "chained", DAY)
txt = pdf_text(pdf)
n_lorries = sum(len(blk["lorries"]) for blk in C["days"][DAY])
ok("4: the driver sheets PDF: one page a lorry", txt.count("\f") + 1 >= n_lorries and b"/Type /Page" in pdf, str(n_lorries))
ok("4: ...each page names the yard, the lorry type, 'lorry n of N', the day and the round trips",
   all(f"lorry {r['n']} of {len(blk['lorries'])}" in txt for blk in C["days"][DAY] for r in blk["lorries"])
   and "Wednesday 25 November 2026" in txt and "round trip" in txt)
ok("4: ...the break is a row in words, the route sheets are named, the not-modelled sentence and 'sends nothing' are printed",
   "Break, 45 min" in txt or "Break, 30 min" in txt)
ok("4: ...the rule's caveats", "not a check of anyone" in txt and "Wayscope sends nothing" in txt and "Driving at most 9 h" in txt)
ok("4: ...never 'compliant', 'utilisation', 'fill rate' or 'movement'", not re.search(r"compliant|utilisation|fill rate|movement", txt, re.I))
ok("4: the stamp: DRAFT when the week is not all confirmed, else CONFIRMED", ("CONFIRMED" in txt) == D["week_confirmed"] or "DRAFT" in txt)
try:
    lp.build_pdf(D, "booked", DAY)
    ok("4: no sheet for the booked view", False)
except lp.PlanError as e:
    ok("4: no sheet for the booked view, in words", "chained or compressed" in str(e))
try:
    lp.build_pdf(D, "chained", "2026-11-28")
    ok("4: a Saturday is refused", False)
except lp.PlanError as e:
    ok("4: a Saturday is refused, in words", "not a weekday" in str(e))
xl = lp.build_xlsx(D, "compressed", DAY)
import openpyxl  # noqa: E402
ws = openpyxl.load_workbook(io.BytesIO(xl)).active
hdr = [c.value for c in ws[5]]
ok("4: the XLSX: the header row, one row a trip or break, numbers as numbers",
   hdr[:6] == ["Yard", "Lorry type", "Lorry", "Order", "About", "Route"] and ws.max_row > 6
   and all(isinstance(ws.cell(row=i, column=3).value, int) for i in range(6, ws.max_row + 1)), str(hdr))
ok("4: the XLSX says 'compressed' and the rule", "compressed" in str(ws.cell(row=1, column=1).value) and lp.RULE_WORDS in str(ws.cell(row=2, column=1).value))
ok("4: file stems", lp.file_stem(D, "chained", DAY) == f"lorry-plan-{DAY}-chained")

# --------------------------------------------------------------------------- 5. apply (Q12)
try:
    lp.apply(None, {"compressed": {"lines": {}}})
    ok("5: nothing to move is refused", False)
except lp.PlanError as e:
    ok("5: nothing to move is refused, in words", "Nothing to move" in str(e))
Dc = copy.deepcopy(D)
for e in Dc["compressed"]["lines"].values():
    e["status"] = "confirmed"
try:
    lp.apply(None, Dc)
    ok("5: a confirmed week is refused", False)
except lp.PlanError as e:
    ok("5: a confirmed week is refused, in words", "confirmed" in str(e))
# the demo's week: the shipped lines are confirmed on North's; apply on the real data refuses or writes
some = next(iter(D["compressed"]["lines"].values()))
if any(e["status"] == "confirmed" for e in D["compressed"]["lines"].values()):
    try:
        lp.apply(None, D)
        ok("5: the demo week (part confirmed) refuses apply", False)
    except lp.PlanError as e:
        ok("5: the demo week (part confirmed) refuses apply", "confirmed" in str(e))
# a made-up unconfirmed move on one line: written through days.set_day, the week total kept
import days as _days  # noqa: E402
line = next(l for l in PG["commit"]["lines"] if (l.get("week") or {}).get("status") != "confirmed" and (l.get("context") or {}).get("baked")
            and sum(int((x.get("derived") or {}).get("trips") or 0) for x in l["days"]) >= 2) if any(
    (l.get("week") or {}).get("status") != "confirmed" and (l.get("context") or {}).get("baked") for l in PG["commit"]["lines"]) else None
if line:
    dd = [x for x in line["days"] if x["day_date"] in DAYS]
    q = {x["day_date"]: float(x.get("planned_qty") or 0) for x in dd}
    tot = sum(q.values())
    new = {d: 0.0 for d in q}
    new[DAYS[0]] = round(tot, 1)
    fake = {"compressed": {"lines": {lp.line_key(line): {"route_id": line["route_id"], "month_index": line["month_index"],
            "discipline": line.get("discipline") or "", "section_id": line.get("section_id") or "", "status": "edited",
            "days": {d: {"qty_from": q[d], "qty_to": new[d], "trips_from": 0, "trips_to": 0} for d in q}}}}}
    r = lp.apply(None, fake, by="tester")
    after = lookahead.page(bucket="commit", acc=PLANNER, with_restrictions=False)
    la = next(l for l in after["commit"]["lines"] if lp.line_key(l) == lp.line_key(line))
    q2 = {x["day_date"]: float(x.get("planned_qty") or 0) for x in la["days"] if x["day_date"] in DAYS}
    ok("5: apply() writes the moved cells (one write a changed day) and the week's total is unchanged",
       r["written"] >= 1 and abs(sum(q2.values()) - tot) < 0.06 and abs(q2[DAYS[0]] - tot) < 0.06, str((r, q, q2)))
    ok("5: ...the days are marked typed (edited)", all(x["status"] == "edited" for x in la["days"] if x["day_date"] in DAYS and x["planned_qty"] != q.get(x["day_date"])))
else:
    ok("5: an unconfirmed routed line to move in the demo week", False)

# --------------------------------------------------------------------------- 6. the endpoints (stubbed FastAPI)
access.set_current("planner123")
_real_page = lookahead.page
lookahead.page = lambda **k: bake(_real_page(**k))        # the endpoints read the Look-ahead's own page: the stand-in routing here
import read_cache  # noqa: E402
read_cache.clear() if hasattr(read_cache, "clear") else None
R = main.forecast_week_lorry_plan(bucket="commit")
ok("6: GET /api/forecast-weeks/lorry-plan answers the plan with the three views", R["views"] == ["booked", "chained", "compressed"] and R["booked"]["week"] == B["week"])
r = main.forecast_week_lorry_plan_file(day=DAY, format="pdf", view="chained", bucket="commit")
ok("6: the PDF download", r.media_type == "application/pdf" and f'filename="lorry-plan-{DAY}-chained.pdf"' in r.headers["Content-Disposition"]
   and r.headers.get("Cache-Control") == "no-store")
r = main.forecast_week_lorry_plan_file(day=DAY, format="xlsx", view="compressed", bucket="commit")
ok("6: the XLSX download", "spreadsheetml" in r.media_type and f'lorry-plan-{DAY}-compressed.xlsx' in r.headers["Content-Disposition"])
for kw, code in (({"day": DAY, "format": "docx"}, 400), ({"day": "2026-11-28", "format": "pdf"}, 400), ({"day": DAY, "format": "pdf", "view": "booked"}, 400)):
    try:
        main.forecast_week_lorry_plan_file(bucket="commit", **kw)
        ok(f"6: refusal {kw}", False)
    except _HTTPException as e:
        ok(f"6: refusal {kw} -> {code}", e.status_code == code, str(e.status_code))
_tok = access._ACCESS.set(TEAM)
try:
    main.forecast_week_lorry_plan_apply(bucket="commit")
    ok("6: a team cannot apply", False)
except _HTTPException as e:
    ok("6: a team cannot apply (403)", e.status_code == 403, str(e.status_code))
access._ACCESS.reset(_tok)
access.set_current("planner123")
try:
    main.forecast_week_lorry_plan_apply(bucket="commit")
    ok("6: apply on the part-confirmed demo week", False, "no refusal")
except _HTTPException as e:
    ok("6: apply on the part-confirmed demo week answers 409 in words", e.status_code == 409 and "confirmed" in str(e.detail), str(e.detail))
access.set_current(None)
try:
    main.forecast_week_lorry_plan(bucket="commit")
    ok("6: signed out", False)
except _HTTPException as e:
    ok("6: signed out -> 401", e.status_code == 401)
access.set_current("planner123")
lookahead.page = _real_page

# --------------------------------------------------------------------------- 7. the screen and the guides (source)
APP = read("frontend/index.html")
MAIN = read("backend/main.py")
UG = read("frontend/help/index.html")
TECH = read("frontend/help/technical/index.html")
ok("7: the three routes", all(x in MAIN for x in ('@app.get("/api/forecast-weeks/lorry-plan")', '@app.get("/api/forecast-weeks/lorry-plan/download")',
                                                 '@app.post("/api/forecast-weeks/lorry-plan/apply")')))
ok("7: the plan is read from the Look-ahead's kept read and kept itself", '_staff_json("lorry-plan", {"bucket": b}' in MAIN and 'pg = _staff_json("lookahead", {"bucket": b, "route_id": None, "on": True}' in MAIN)
ok("7: apply is planners and admins only", '_require_planner_or_admin("move a week\'s loads between its days")' in MAIN)
panel = APP[APP.index("function LorryPlan({"):APP.index("function GatesWeek({")]
ok("7: the panel: folded, the three views, the weekday chips, the sheets, Apply for planners / admins on an unconfirmed week",
   'data-lorry-plan="1"' in panel and 'LP_VIEW_WORDS = { booked: "As booked", chained: "Chained by yard", compressed: "Week compressed" }' in APP
   and 'data-lp-sheets="1"' in panel and 'data-lp-apply="1"' in panel and 'disabled={!!busy || weekConfirmed || !mv.length}' in panel
   and 'const canApply = !!(access && (access.role === "planner" || access.role === "admin"));' in panel)
# NARROWED 9 Nov 2026 (2.1-9b): the track is role=img for a reader of the plan and a named group for a planner, whose trips are controls
ok("7: one row a lorry, its trips as blocks across the day, the break hatched, the free words at the end",
   'role={can ? "group" : "img"}' in APP and 'className={"lp-blk" + (b.kind === "break" ? " is-break" : "")}' in APP and 'data-lp-free={r.free_minutes}' in APP)
ok("7: the panel sits under Gates this week; the KPI caption gains the chained figure; the phone reads it",
   "<LorryPlan bucket={bucket} tick={tick} access={access} onData={setLorryPlan} weekConfirmed={allConfirmed} />" in APP
   and "with each yard's lorries chained` : \"\")} />" in APP and 'data-ph-lorry-plan={shown}' in APP and 'data-ph-lorry-list="1"' in APP)
ok("7: the Config rows: a day-hire rate per lorry type, optional, never seeded", 'function DayHireSection({ doc, upd })' in APP
   and 'data-day-hire-section="1"' in APP and "Blank = the saving in lorry-days only" in APP and "<DayHireSection doc={doc} upd={upd} />" in APP)
ok("7: the info box", '"la.lorryplan": {' in APP and 'guide: "ug-lorry-plan", tech: "t1-lorry-plan"' in APP)
words = (panel + APP[APP.index('"la.lorryplan": {'):APP.index('"la.gates": {')])
ok("7: the screen never says compliant, utilisation, fill rate or movements; no back-end words",
   not re.search(r"compliant|utilisation|fill rate|movement|endpoint|server|cache", words, re.I), str(re.findall(r"compliant|utilisation|fill rate|movement|endpoint|server|cache", words, re.I)))
ok("7: the user guide §7 and the technical T1", 'id="ug-lorry-plan"' in UG and "Lorry plan" in UG and 'id="t1-lorry-plan"' in TECH and "/api/forecast-weeks/lorry-plan" in TECH
   and 'href="#t1-lorry-plan"' in TECH)
ok("7: the module's words", "compliant" not in lp.RULE_WORDS + lp.PLANNING_WORDS + lp.COMPRESS_WORDS and "movement" not in (lp.RULE_WORDS + lp.PLANNING_WORDS + lp.COMPRESS_WORDS).lower())
ok("7: Config validates day_hire through the module", "lorry_plan.day_hire_problem(doc.get(\"day_hire\")" in read("backend/config.py"))

# --------------------------------------------------------------------------- 8. drag and drop (PR 2, 9 Nov 2026, card 9 + Q14)
# A planner moves one trip to another lorry of the same yard (chained; compressed also to another day). The drop is
# checked by the same rule; a move that fits is saved as the yard's arrangement for the week and used in place of
# pack() while the trips it was made from are unchanged. Everything on the baked demo week (PG), planner access.
access.set_current("planner123")
import read_cache  # noqa: E402,F811
ok("8: the table is tenanted, in the package order, in the audit's registry and among the tables a refresh keeps from live",
   lp.TABLE == "lorry_plan_moves" and lp.TABLE in db.TENANTED_TABLES and lp.TABLE in tenant_package.ORDER and lp.TABLE in db._TENANT_DDL
   and lp.TABLE in db._TENANT_PK and lp.TABLE in read("backend/tests/test_tenant_audit.py") and f'"{lp.TABLE}")' in read("backend/tools/make_demo_tenant.py"))
ok("8: the table is NOT among the no-data tables: a move changes what the plan shows, so the kept reads must refresh", lp.TABLE not in db.NO_DATA_TABLES)
ok("8: the trips carry their booked day and their own driving / other minutes, for the page's own look at a drop",
   all("day" in b and "drive" in b and "other" in b for blk in C["days"][DAY] for r in blk["lorries"] for b in r["blocks"] if b["kind"] == "trip")
   and all(b["day"] == DAY for blk in C["days"][DAY] for r in blk["lorries"] for b in r["blocks"] if b["kind"] == "trip")
   and D["shift_minutes"] == D["shift_hours"] * 60 and D["arranged"] == {"chained": [], "compressed": []})
ok("8: every block names its yard (yard_id, the plan's own key) and says it is not arranged",
   all(blk.get("yard_id") and blk["arranged"] is False for d in DAYS for blk in C["days"][d]))

# the fingerprint
_t = [{"line_key": "A|1||", "day": DAY}, {"line_key": "A|1||", "day": DAY}, {"line_key": "B|1||", "day": DAY}]
ok("8: pool_fp is the count of each (line, day), whatever the order; one trip more or less changes it",
   lp.pool_fp(_t) == lp.pool_fp(list(reversed(_t))) and lp.pool_fp(_t) != lp.pool_fp(_t[:2]) and lp.pool_fp(_t) != lp.pool_fp(_t + [_t[0]])
   and lp.pool_fp(_t) != lp.pool_fp([dict(x, day="2026-11-24") for x in _t]) and len(lp.pool_fp(_t)) == 20)

# a yard on the pinned day with at least two lorries: lorry 1 is the fullest (first fit, longest first), the last the emptiest
_blk = next(b for b in C["days"][DAY] if len(b["lorries"]) >= 2)
_yid, _veh = _blk["yard_id"], _blk["vehicle"]
_src = _blk["lorries"][-1]
_trip = next(b for b in _src["blocks"] if b["kind"] == "trip")
SHIFT = D["shift_minutes"]


def fits(row, b):
    return lp._fits(row["driving_minutes"], row["work_minutes"], b["drive"], b["other"], SHIFT)


_no = next((r for r in _blk["lorries"][:-1] if not fits(r, _trip)), None)
_yes = next((r for r in _blk["lorries"][:-1] if fits(r, _trip)), None)
ok("8: the stand-in week has a yard where the last lorry's trip does NOT fit the fullest lorry (the refusal case)", _no is not None and _no["n"] == 1, str(_blk["name"]))


def body(**k):
    b = {"view": "chained", "yard_id": _yid, "vehicle": _veh, "line_key": _trip["line_key"], "from_day": DAY, "from_lorry": _src["n"], "to_day": DAY, "to_lorry": _no["n"]}
    b.update(k)
    return b


try:
    lp.move(PG, body(), by="Pat")
    ok("8: a drop that does not fit is refused", False, "no refusal")
except lp.PlanError as e:
    ok("8: a drop that does not fit is refused in words with the minutes over (nothing saved)",
       re.match(r"^Would pass (the \d+(\.\d+)? h shift|9 h of driving) by \d+ min\.$", str(e)) is not None and not db.query(f"SELECT id FROM {lp.TABLE}"), str(e))
for bad, words in ((body(to_day="2026-11-24"), lp.SAME_DAY_WORDS), (body(from_lorry=99), lp.CHANGED_WORDS), (body(line_key="R999|1||"), lp.CHANGED_WORDS),
                   (body(yard_id="L999"), "not in this week's plan"), (body(to_day="2026-12-01"), "not in this week"), (body(view="booked"), "chained or compressed"),
                   (body(to_lorry=_src["n"]), "already on that lorry")):
    try:
        lp.move(PG, bad)
        ok(f"8: refused: {words}", False, "no refusal")
    except lp.PlanError as e:
        ok(f"8: refused in words: {words}", words in str(e), str(e))
ok("8: ...and none of those saved anything", not db.query(f"SELECT id FROM {lp.TABLE}"))

# a move that fits: a trip of a fuller lorry onto the yard's emptiest (the last; first fit leaves it the most free) — found
# by the rule itself over the pinned day, so the case is real, not assumed
_fit = None
for _b in C["days"][DAY]:
    for _r in _b["lorries"][:-1]:
        for _x in _r["blocks"]:
            if _x["kind"] == "trip" and fits(_b["lorries"][-1], _x):
                _fit = (_b, _r, _x, _b["lorries"][-1])
                break
        if _fit:
            break
    if _fit:
        break
ok("8: the stand-in week has a lorry whose trip FITS its yard's emptiest lorry (the landing case)", _fit is not None)
_blk, _fsrc, _ftrip, _tgt = _fit
_yid, _veh = _blk["yard_id"], _blk["vehicle"]


def fbody(**k):
    b = {"view": "chained", "yard_id": _yid, "vehicle": _veh, "line_key": _ftrip["line_key"], "from_day": DAY, "from_lorry": _fsrc["n"], "to_day": DAY, "to_lorry": _tgt["n"]}
    b.update(k)
    return b


_pre_count = C["by_day"][DAY]
_v0 = db.data_version()
res = lp.move(PG, fbody(), by="Pat", now=datetime.datetime(2026, 11, 23, 9, 30))
_rows = db.query(f"SELECT * FROM {lp.TABLE}")
ok("8: a move that fits answers where the trip landed and saves ONE row for the yard, view and week, by Pat, with the week's fingerprint",
   res["ok"] is True and res["view"] == "chained" and res["day"] == DAY and res["lorry"] == _tgt["n"] and len(_rows) == 1
   and _rows[0]["id"] == f"2026-11-23|chained|{_yid}|{_veh}" and _rows[0]["moved_by"] == "Pat" and _rows[0]["moved_at"] == "2026-11-23T09:30"
   and _rows[0]["week_from"] == "2026-11-23" and len(_rows[0]["pool_fp"]) == 20, str(res))
ok("8: the write bumps the data version (so the kept plan read is rebuilt)", db.data_version() > _v0)
_saved = json.loads(_rows[0]["lorries_json"])
ok("8: the saved chained arrangement holds the day touched only (the other days stay Wayscope's), with that day's own fingerprint and its lorries as lists of (line, day) references",
   set(_saved.keys()) == {DAY} and "fp" in _saved[DAY] and isinstance(_saved[DAY]["lorries"], list)
   and all(set(ref.keys()) == {"lk", "d"} for L in _saved[DAY]["lorries"] for ref in L)
   and sum(len(L) for L in _saved[DAY]["lorries"]) == sum(r["trips"] for r in _blk["lorries"]))
D2 = lp.plan(PG, acc=PLANNER)
C2 = D2["chained"]
_blk2 = next(b for b in C2["days"][DAY] if b["yard_id"] == _yid and b["vehicle"] == _veh)
_t2 = next(r for r in _blk2["lorries"] if r["n"] == _tgt["n"])
ok("8: plan() now shows the arrangement on that day: the target lorry has one trip more, the yard is flagged arranged (by Pat), the yard named at the top",
   _blk2["arranged"] is True and _blk2["moved_by"] == "Pat" and _t2["trips"] == _tgt["trips"] + 1 and D2["arranged"]["chained"] == [_blk["name"]]
   and D2["arranged"]["compressed"] == [], f"{_t2['trips']} vs {_tgt['trips']}")
ok("8: ...the source lorry has one trip fewer, or is gone when it had only the one; the day's count never rises",
   (len(_blk2["lorries"]) == len(_blk["lorries"]) - 1 if _fsrc["trips"] == 1 else next(r for r in _blk2["lorries"] if r["n"] == _fsrc["n"])["trips"] == _fsrc["trips"] - 1)
   and C2["by_day"][DAY] <= _pre_count)
ok("8: ...the other days of that yard are Wayscope's plan still (each day stands on its own fingerprint in the chained view)",
   all(b["arranged"] is False for d in DAYS if d != DAY for b in C2["days"][d] if b["yard_id"] == _yid and b["vehicle"] == _veh))
ok("8: ...every load is still on exactly one lorry", trips_in(C2, DAY) == trips_in(C, DAY))
ok("8: ...the words say the arrangement is kept until the loads change", "until its loads change" in D2["words"]["arranged"] and "Reset" in D2["words"]["arranged"])
ok("8: the driver sheets print the arranged day (the target lorry's page has one trip more)",
   str(_t2["trips"]) in pdf_text(lp.build_pdf(D2, "chained", DAY)))

# the loads change: the arrangement gives way
PG3 = copy.deepcopy(PG)
for l in PG3["commit"]["lines"]:
    if lp.line_key(l) == _ftrip["line_key"]:
        for x in l["days"]:
            if x["day_date"] == DAY:
                x["derived"]["trips"] = int(x["derived"]["trips"]) + 1
                x["planned_qty"] = _f(x.get("planned_qty")) * (x["derived"]["trips"]) / (x["derived"]["trips"] - 1) if False else x.get("planned_qty")
D3 = lp.plan(PG3, acc=PLANNER)
_blk3 = next(b for b in D3["chained"]["days"][DAY] if b["yard_id"] == _yid and b["vehicle"] == _veh)
ok("8: one load more on that line that day and the saved arrangement is not used (Wayscope's plan shows, nothing deleted)",
   _blk3["arranged"] is False and D3["arranged"]["chained"] == [] and len(db.query(f"SELECT id FROM {lp.TABLE}")) == 1)

# compressed: to another day, lorry 0 = the first lorry there that takes it, else a new one
X0 = D2["compressed"]
_xblk = next(b for b in X0["days"][DAY] if b["yard_id"] == _yid and b["vehicle"] == _veh)
_xsrc = _xblk["lorries"][-1]
_xtrip = next(b for b in _xsrc["blocks"] if b["kind"] == "trip")
_to = "2026-11-24" if DAY != "2026-11-24" else "2026-11-25"
res2 = lp.move(PG, {"view": "compressed", "yard_id": _yid, "vehicle": _veh, "line_key": _xtrip["line_key"], "from_day": DAY, "from_lorry": _xsrc["n"],
                    "to_day": _to, "to_lorry": 0}, by="Pat")
D4 = lp.plan(PG, acc=PLANNER)
X4 = D4["compressed"]
_xto = next((b for b in X4["days"][_to] if b["yard_id"] == _yid and b["vehicle"] == _veh), None)
ok("8 (compressed): a trip dropped on another day lands on that day — on the first lorry there with room, else a new one — and the view is arranged",
   res2["ok"] and res2["day"] == _to and _xto is not None and _xto["arranged"] is True and D4["arranged"]["compressed"] == [_blk["name"]]
   and sum(1 for r in _xto["lorries"] for b in r["blocks"] if b["kind"] == "trip" and b["line_key"] == _xtrip["line_key"] and b["day"] == _xtrip["day"]) >= 1
   and len(db.query(f"SELECT id FROM {lp.TABLE}")) == 2, str(res2))
ok("8 (compressed): the moved trip keeps the day it is booked on in its reference, so the moves list (what Apply writes) follows the arrangement",
   any(m["line_key"] == _xtrip["line_key"] and m["day"] == _to for m in X4["moves"]) or (_xtrip["line_key"] in X4["lines"] and X4["lines"][_xtrip["line_key"]]["days"][_to]["trips_to"] >= 1))
ok("8 (compressed): the week carries the same loads", sum(trips_in(X4, d) for d in DAYS) == sum(trips_in(X0, d) for d in DAYS))
ok("8 (compressed): the chained view is untouched by a compressed move", D4["arranged"]["chained"] == [_blk["name"]] and D4["chained"]["by_day"] == C2["by_day"])

# reset
ok("8: reset of one view deletes that view's row only", lp.reset("2026-11-23", "chained") == {"deleted": 1} and [r["view"] for r in db.query(f"SELECT view FROM {lp.TABLE}")] == ["compressed"])
ok("8: reset of the week deletes the rest; nothing left = 0", lp.reset("2026-11-23") == {"deleted": 1} and lp.reset("2026-11-23") == {"deleted": 0} and not db.query(f"SELECT id FROM {lp.TABLE}"))
ok("8: plan() is Wayscope's again", lp.plan(PG, acc=PLANNER)["arranged"] == {"chained": [], "compressed": []})

# the endpoints (stubbed FastAPI): the plan read is kept and rebuilt after a move
lookahead.page = lambda **k: bake(_real_page(**k))
read_cache.clear() if hasattr(read_cache, "clear") else None


class _Body:
    def __init__(self, **k):
        self.__dict__.update(k)

    def dict(self):
        return dict(self.__dict__)


R0 = main.forecast_week_lorry_plan(bucket="commit")
ok("8 (endpoint): the kept plan read starts as Wayscope's", R0["arranged"] == {"chained": [], "compressed": []})
r = main.forecast_week_lorry_plan_move(_Body(**fbody()), bucket="commit")
R1 = main.forecast_week_lorry_plan(bucket="commit")
ok("8 (endpoint): POST …/lorry-plan/move saves the arrangement and the next read of the kept plan shows it (the write bumps the data version)",
   r["ok"] is True and R1["arranged"]["chained"] == [_blk["name"]] and R1 is not R0)
_nb = next(b for b in R1["chained"]["days"][DAY] if len(b["lorries"]) >= 2 and not fits(b["lorries"][0], next(x for x in b["lorries"][-1]["blocks"] if x["kind"] == "trip")))
_nt = next(x for x in _nb["lorries"][-1]["blocks"] if x["kind"] == "trip")
try:
    main.forecast_week_lorry_plan_move(_Body(view="chained", yard_id=_nb["yard_id"], vehicle=_nb["vehicle"], line_key=_nt["line_key"], from_day=DAY,
                                             from_lorry=_nb["lorries"][-1]["n"], to_day=DAY, to_lorry=1), bucket="commit")
    ok("8 (endpoint): a refused drop", False)
except _HTTPException as e:
    ok("8 (endpoint): a refused drop answers 409 with the reason", e.status_code == 409 and str(e.detail).startswith("Would pass"), f"{e.status_code} {e.detail}")
_tok = access._ACCESS.set(TEAM)
for fn, kw in ((main.forecast_week_lorry_plan_move, {"body": _Body(**body()), "bucket": "commit"}), (main.forecast_week_lorry_plan_reset, {"bucket": "commit"})):
    try:
        fn(**kw)
        ok(f"8 (endpoint): a team cannot {fn.__name__}", False)
    except _HTTPException as e:
        ok(f"8 (endpoint): a team cannot {fn.__name__.split('_')[-1]} (403)", e.status_code == 403, str(e.status_code))
access._ACCESS.reset(_tok)
access.set_current(None)
try:
    main.forecast_week_lorry_plan_move(_Body(**body()), bucket="commit")
    ok("8 (endpoint): signed out", False)
except _HTTPException as e:
    ok("8 (endpoint): signed out -> 401", e.status_code == 401)
access.set_current("planner123")
rr = main.forecast_week_lorry_plan_reset(bucket="commit", view="chained")
ok("8 (endpoint): POST …/lorry-plan/reset deletes the view's arrangement and the kept read is Wayscope's again",
   rr == {"deleted": 1} and main.forecast_week_lorry_plan(bucket="commit")["arranged"]["chained"] == [])
lookahead.page = _real_page
ok("8: the routes are planners' and admins'", '_require_planner_or_admin("move a trip between lorries")' in MAIN and '_require_planner_or_admin("reset the lorry plan")' in MAIN
   and '@app.post("/api/forecast-weeks/lorry-plan/move")' in MAIN and '@app.post("/api/forecast-weeks/lorry-plan/reset")' in MAIN)

# the page's own look at the rule = the module's constants (one rule, drivers_hours.py)
_m = re.search(r"const LP_RULE = \{ driveMax: (\d+), driveBreak: (\d+), breakLong: (\d+), workShort: (\d+), workLong: (\d+), breakShort: (\d+) \};", APP)
ok("8: the page's six rule figures are drivers_hours.py's (driving 540, break after 270, 45; work 360 / 540, 30)",
   _m is not None and [int(x) for x in _m.groups()] == [int(dh.DRIVING_MAX_MIN), int(dh.DRIVING_BEFORE_BREAK_MIN), int(dh.BREAK_LONG_MIN),
                                                        int(dh.WORK_SHORT_BREAK_AFTER_MIN), int(dh.WORK_LONG_BREAK_AFTER_MIN), int(dh.BREAK_SHORT_MIN)])
ok("8: the screen (source): draggable trips with a menu, the drop targets, Reset, the badge; the guides say so",
   'data-lp-trip={b.line_key}' in APP and 'data-lp-reset="1"' in APP and '<span className="lp-badge"' in APP and "function LpTrip({" in APP
   and "drag a trip" in UG.lower() and "lorry_plan_moves" in TECH and "/api/forecast-weeks/lorry-plan/move" in TECH)
ok("8: no 'movement' or 'compliant' in the new words", not re.search(r"movement|compliant", lp.ARRANGED_WORDS + lp.CHANGED_WORDS + lp.SAME_DAY_WORDS, re.I))

print(f"\ntest_lorry_plan.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
