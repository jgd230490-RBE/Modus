"""
Concrete pours (29 Oct 2026, task 3a, B1 / V5): pours.py, the day split, the Look-ahead's pour flags, the API.

WHAT IS ASSERTED
----------------
  * figures(): the mockup's worked example exactly (R049's measured 47 / 40 min, 120 m³ at 30 m³ an hour from 07:30:
    16 loads, a mixer every 15 min, a 2 h 05 round trip, 9 mixers, 06:30 first loads, 11:30 the end); 6 mixers booked
    = MIXERS SHORT, the end 12:58; 2 = COLD JOINT, the face waits 47.5 min; the 30-minute edge; the transit limit; a
    part load; mixers in a no-delivery band; the deck example (60 m³ an hour: 16 mixers, a cold joint at 3);
  * the two limits (defaults, Config's validation);
  * the split (Q5): a pour's week and day carry it, the rest is shared, the month total holds;
  * storage: the problems in words (no line, not m³, not a mixer, no date), the Thursday rule, the id;
  * the reads: drive times from the stored route (the planned road) and from the busy-hour times (the worst hour), the
    gate's check-in, OVER PLAN across a line's month, a cancelled pour raises nothing;
  * the weeks and days materialise with the pour, edited rows hold;
  * the Look-ahead: the rail's pour flags carry the pour's day, the page lists the week's pours;
  * the API: a team writes its own lines only (404 for another's), the list filters by team, 400 in words;
  * the package carries the table; the generator's pours.

WHAT THIS DOES NOT PROVE
------------------------
HERE is never called (the stored routes are typed here); Postgres is not run; no screen is looked at.

Run:  python3 backend/tests/test_pours.py
"""
import datetime
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

# ---- stubs, verbatim from test_zone_diversions_b.py ---------------------------
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


def _passthrough_decorator(*a, **k):
    def wrap(fn):
        return fn
    return wrap


class _App:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return _passthrough_decorator()

    post = put = delete = patch = get

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


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
_resp.Response = object
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_pours_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import here_routing  # noqa: E402
import weeks  # noqa: E402
import days  # noqa: E402
import lookahead  # noqa: E402
import clashes  # noqa: E402
import tenant_package  # noqa: E402
import read_cache  # noqa: E402
import pours  # noqa: E402

for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def flag_codes(fig):
    return [f["code"] for f in fig["flags"]]


# =========================================================================== #
#  1. figures(): the worked example and its variants                           #
# =========================================================================== #
EX = dict(m3=120, rate=30, start=7 * 60 + 30, m3_per_load=7.5, load_min=10, laden_min=47, check_in=3, washout=10,
          back_min=40)
f = pours.figures(**EX)
ok("⭐ the worked example: 16 loads, a mixer every 15 min, a 125 min round trip, 9 mixers (8.33)",
   f["loads"] == 16 and f["gap"] == 15.0 and f["cycle"] == 125.0 and f["needed"] == 9 and f["needed_exact"] == 8.33, str(f))
ok("...loading to the end of discharge 75 min; the first mixer loads 06:30, the last arrives 11:15, the end 11:30",
   f["transit"] == 75.0 and f["first_loads"] == "06:30" and f["last_arrives"] == "11:15" and f["ends"] == "11:30", str(f))
ok("...enough mixers, no flag", f["flags"] == [] and f["booked"] is None and f["face_wait"] == 0.0)
ok("...the parts of the round trip add up to it", abs(sum(f["parts"].values()) - f["cycle"]) < 1e-6, str(f["parts"]))
f6 = pours.figures(**EX, booked=6)
ok("⭐ 6 mixers booked: MIXERS SHORT, a mixer every 20.8 min, the face waits 5.8, the end 12:58 (1 h 28 later)",
   flag_codes(f6) == ["POUR_SHORT"] and f6["real_gap"] == 20.8 and f6["face_wait"] == 5.8 and f6["ends"] == "12:58"
   and f6["late_by"] == 87.5 and "6 of 9 mixers" in f6["flags"][0]["text"] and "1 h 28" in f6["flags"][0]["text"], str(f6))
f2 = pours.figures(**EX, booked=2)
ok("⭐ 2 mixers booked: COLD JOINT, the face waits 47.5 min (over 30), no MIXERS SHORT besides",
   flag_codes(f2) == ["POUR_COLD_JOINT"] and f2["face_wait"] == 47.5 and "48 min" in f2["flags"][0]["text"], str(f2))
ok("9 or 20 mixers booked: no flag", pours.figures(**EX, booked=9)["flags"] == [] and pours.figures(**EX, booked=20)["flags"] == [])
# the 30-minute edge: cycle 125, discharge 15 -> booked b gives a wait of 125/b - 15; set the limit at exactly that
w3 = 125 / 3 - 15
ok("🔴 the cold-joint edge: a wait equal to the limit is no cold joint, a hair over is",
   "POUR_COLD_JOINT" not in flag_codes(pours.figures(**EX, booked=3, cold_joint=w3))
   and "POUR_COLD_JOINT" in flag_codes(pours.figures(**EX, booked=3, cold_joint=w3 - 0.1)))
ok("TRANSIT: 75 min over a 60 min limit is red; at 75 it is not",
   "POUR_TRANSIT" in flag_codes(pours.figures(**EX, transit_limit=60))
   and "POUR_TRANSIT" not in flag_codes(pours.figures(**EX, transit_limit=75)))
fp = pours.figures(**dict(EX, m3=100))
ok("a part load: 100 m³ is 14 loads, the last 2.5 m³; the pour ends after its own (shorter) discharge",
   fp["loads"] == 14 and fp["last_load_m3"] == 2.5 and fp["ends"] == pours.clock(450 + 13 * 15 + 5), str(fp))
fb = pours.figures(**EX, bands=[(8 * 60, 9 * 60)])
ok("⭐ a no-delivery band 08:00-09:00: the mixers at the gate 07:57-08:57 are counted (4) and flagged IN A BAND",
   fb["in_band"] == 4 and flag_codes(fb) == ["POUR_BAND"] and "4 mixers" in fb["flags"][0]["text"], str(fb["in_band"]))
deck = dict(EX, m3=400, rate=60)
fd = pours.figures(**deck)
ok("the deck example: 60 m³ an hour on the same road needs 16 mixers, a cold joint at 3 and none at 4",
   fd["needed"] == 16 and "POUR_COLD_JOINT" in flag_codes(pours.figures(**deck, booked=3))
   and flag_codes(pours.figures(**deck, booked=4)) == ["POUR_SHORT"], str(fd["needed"]))
ok("worst_flag: red before amber", pours.worst_flag([{"code": "POUR_BAND"}, {"code": "POUR_TRANSIT"}]) == "POUR_TRANSIT")
ok("clock and hm", pours.clock(450) == "07:30" and pours.clock(1470) == "00:30 next day" and pours.hm(125) == "2 h 05"
   and pours.hm(45) == "45 min")

# =========================================================================== #
#  2. The limits                                                               #
# =========================================================================== #
ok("the defaults: 120 and 30 minutes", pours.limits({}) == {"transit_min": 120.0, "cold_joint_min": 30.0})
ok("typed limits are read", pours.limits({"planning": {"pours": {"transit_limit_min": 90, "cold_joint_min": 45}}})
   == {"transit_min": 90.0, "cold_joint_min": 45.0})
ok("an out-of-range limit falls back to the default",
   pours.limits({"planning": {"pours": {"transit_limit_min": 5}}})["transit_min"] == 120.0)
ok("limits_problem: none for absent or good, words for bad",
   pours.limits_problem(None) is None and pours.limits_problem({"cold_joint_min": 30}) is None
   and "between 5 and 240" in (pours.limits_problem({"cold_joint_min": 300}) or "")
   and "number of minutes" in (pours.limits_problem({"transit_limit_min": "x"}) or ""))

# =========================================================================== #
#  3. The split (Q5)                                                           #
# =========================================================================== #
sm = pours.split_month(1000, 4, {2: 400})
ok("⭐ split_month: the pour's week carries it plus an even share of the rest; the month adds up",
   sm == {1: 150.0, 2: 550.0, 3: 150.0, 4: 150.0} and abs(sum(sm.values()) - 1000) < 1e-9, str(sm))
ok("...no pours = quantity ÷ weeks (the old rule)", pours.split_month(1000, 5, {}) == {w: 200.0 for w in range(1, 6)})
ok("...pours over the month leave nothing to share", pours.split_month(300, 4, {1: 400}) == {1: 400.0, 2: 0.0, 3: 0.0, 4: 0.0})
mon = datetime.date(2027, 3, 8)
wk = [mon + datetime.timedelta(days=i) for i in range(7)]
sd = pours.split_days(200, wk, {wk[3]: 120})
ok("⭐ split_days: the pour day (Thu) carries 120, the other four weekdays share 80, the weekend 0",
   sd[wk[3]] == 120.0 and all(sd[wk[i]] == 20.0 for i in (0, 1, 2, 4)) and sd[wk[5]] == 0.0 and sd[wk[6]] == 0.0, str(sd))
ok("...without pours it is days.split_week", pours.split_days(200, wk, {}) == days.split_week(200, wk))
ok("...a weekend pour carries its m³", pours.split_days(100, wk, {wk[5]: 60})[wk[5]] == 60.0)

# =========================================================================== #
#  Fixture: a batching plant P, a site S with one gate (3 min check-in), route  #
#  R1 P->S stored for the 8 m³ mixer at 47 / 40 min; an Approved m³ line in     #
#  Mar 2027 (month 15) for IPT1, a tonnes line on R2, a tipper m³ line on R3.   #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()
access.set_current("planner123")
PLANNER = access.current()
TEAM1 = {"role": "ipt", "ipt": "IPT1", "label": "North Team"}
TEAM2 = {"role": "ipt", "ipt": "IPT2", "label": "Central Team"}
MIX = "Truck mixer 8 m³ (32t)"
TIP = network.DEFAULT_PROFILE
FAC = conversions.load_factors()
ok("fixture: the seed's 8 m³ mixer carries 7.5 m³ and loads in 10 min",
   FAC["vehicles"][MIX]["payload_m3"] == 7.5 and network._turnaround_minutes(MIX, FAC)[0] == 10.0)
for lid, name, typ, lon in (("P", "Plant", "Batching plant", -1.0), ("S", "Site", "Site", -0.9)):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, 52.5, ?, ?)", (lid, name, lon, typ))
G = gates.create_gate("S", "Gate A", 52.5, -0.9, direction="both", safety_minutes=3, is_default=True)
ok("fixture: the site's gate with a 3 min check-in", (G or {}).get("safety_minutes") == 3, str(G))
for rid in ("R1", "R2", "R3"):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, 'P', 'S', "
               "'Ready-mixed concrete', 'IPT1')", (rid,))
LINE = [[-1.0, 52.5], [-0.95, 52.5], [-0.9, 52.5]]
network._upsert_geom("R1", MIX, json.dumps(LINE), 43.0, 47 / 60.0, None, leg="loaded", alt_index=0)
network._upsert_geom("R1", MIX, json.dumps(list(reversed(LINE))), 42.7, 40 / 60.0, None, leg="return", alt_index=0)
MAR27 = 15


def line(fid, rid, q, unit, veh, ipt="IPT1", mi=MAR27, sec="WS4", status="Approved"):
    db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, unit, material_type, "
               "material_description, vehicle_type, status, ipt) VALUES (?, ?, ?, 'structures', ?, ?, ?, "
               "'Ready-mixed concrete', 'C32/40 concrete', ?, ?, ?)", (fid, rid, mi, sec, q, unit, veh, status, ipt))


line("F1", "R1", 1000.0, "m3", MIX)
line("F2", "R2", 500.0, "t", MIX)
line("F3", "R3", 500.0, "m3", TIP)
line("F4", "R1", 300.0, "m3", MIX, ipt="IPT2", sec="WS2")
ok("month_of: the Thursday rule — Mon 1 Mar 2027 is in Feb 2027's last week? no: its Thursday is 4 Mar",
   pours.month_of(datetime.date(2027, 3, 1)) == MAR27 and pours.month_of(datetime.date(2027, 3, 11)) == MAR27)
ok("...and Mon 29 Mar 2027's week belongs to April (Thu 1 Apr)", pours.month_of(datetime.date(2027, 3, 29)) == 16)

BASE = {"route_id": "R1", "discipline": "structures", "section_id": "WS4", "pour_date": "2027-03-11", "start": "07:30",
        "m3": 120, "rate_m3h": 30, "washout_min": 10, "place": "Pier 3 base"}
P1 = pours.create_pour(dict(BASE), FAC, by="test")
ok("⭐ create: P001 on the line, month 15, start kept as HH:MM", P1.get("id") == "P001" and P1["month_index"] == MAR27
   and P1["start"] == "07:30" and P1["status"] == "planned" and P1["ipt"] == "IPT1", str(P1))
for label, patch, words in (
        ("no line in that month", {"pour_date": "2027-06-10"}, "no line on that route"),
        ("a line in tonnes", {"route_id": "R2"}, "planned in m³"),
        ("a line whose vehicle carries no m³", {"route_id": "R3"}, "concrete mixer"),
        ("no date", {"pour_date": ""}, "needs a date"),
        ("no start", {"start": "7.30"}, "start time"),
        ("rate 0", {"rate_m3h": 0}, "pour rate must be above 0"),
        ("1.5 mixers", {"mixers_booked": 1.5}, "whole number"),
        ("a status nobody knows", {"status": "maybe"}, "planned, confirmed")):
    r = pours.create_pour(dict(BASE, **patch), FAC)
    ok(f"create refuses {label}, in words", words.lower() in (r.get("error") or "").lower(), str(r))
ok("source: no BOOLEAN compared with a number in pours.py (the 28 Oct rule)", not re.search(r"\bactive\s*=\s*1\b", read("backend/pours.py")))

# =========================================================================== #
#  4. The reads: drive times, the gate, OVER PLAN                              #
# =========================================================================== #
d1 = pours.decorate([pours.get_pour("P001")], FAC)[0]
fg = d1["figures"]
ok("⭐ decorate: the stored road's 47 / 40 min, the gate's 3 min, the line's mixer -> the worked example's figures",
   d1["basis"] == "planned" and fg["parts"] == {"loading": 10.0, "there": 47.0, "check_in": 3.0, "discharge": 15.0,
                                               "washout": 10.0, "back": 40.0} and fg["needed"] == 9, str(d1))
ok("...names: plant, site, gate, the mixer's name (never the key's 'Truck')",
   d1["origin_name"] == "Plant" and d1["dest_name"] == "Site" and d1["gate_name"] == "Gate A"
   and d1["vehicle_name"].startswith("Concrete mixer"))
ok("...the limits on the reply are the tenant's", fg["limits"] == {"transit_min": 120.0, "cold_joint_min": 30.0})
# the busy-hour times: worst hour of the departures. Store tipper-free rows for the mixer itself.
gc = {r["leg"]: r["computed_at"] for r in db.query("SELECT leg, computed_at FROM route_geometry WHERE route_id = 'R1' "
                                                    "AND vehicle_profile = ?", (MIX,))}
for hour, lo, rt in (("06:00", 50, 41), ("08:00", 60, 45), ("09:00", 55, 44), ("12:00", 48, 40)):
    for leg, mins in (("loaded", lo), ("return", rt)):
        db.execute("INSERT INTO route_hour_times (route_id, vehicle_profile, leg, hour, rank, alt_index, geom_computed_at, "
                   "duration_hr) VALUES ('R1', ?, ?, ?, 0, 0, ?, ?)", (MIX, leg, hour, gc[leg], mins / 60.0))
read_cache.clear() if hasattr(read_cache, "clear") else None
d1h = pours.decorate([pours.get_pour("P001")], FAC)[0]
ok("⭐ busy-hour times: the mixers set off 06:30-10:15, so 06:00 / 08:00 / 09:00 (nearest); the worst is 08:00 (60 + 45)",
   d1h["basis"] == "hours" and d1h["figures"]["parts"]["there"] == 60.0 and d1h["figures"]["parts"]["back"] == 45.0
   and set(d1h["basis_hours"]) == {"06:00", "08:00", "09:00"}, str((d1h["basis"], d1h.get("basis_hours"), d1h["figures"]["parts"])))
there, back, basis, hrs = pours.drive_times("R1", MIX, MAR27, [12 * 60])
ok("...a noon departure reads the 12:00 times", (there, back, basis, hrs) == (48.0, 40.0, "hours", ["12:00"]))
db.execute("DELETE FROM route_hour_times")
ok("...without them, the planned road", pours.drive_times("R1", MIX, MAR27, [450])[2] == "planned")
ok("a route not routed for the mixer: no figures, said",
   pours.drive_times("R2", MIX, MAR27, [450]) == (None, None, None, []))
P2 = pours.create_pour(dict(BASE, pour_date="2027-03-16", m3=950, place="Deck"), FAC)
dd = {p["id"]: p for p in pours.decorate(pours.list_pours(), FAC)}
ok("⭐ OVER PLAN: 120 + 950 m³ of pours against the line's 1000 m³ flags both pours",
   all("POUR_OVER_PLAN" in [x["code"] for x in dd[i]["flags"]] for i in ("P001", "P002")), str({i: dd[i]["flags"] for i in dd}))
pours.update_pour("P002", {"m3": 400}, FAC)
dd = {p["id"]: p for p in pours.decorate(pours.list_pours(), FAC)}
ok("...400 m³ instead: no OVER PLAN", all("POUR_OVER_PLAN" not in [x["code"] for x in dd[i]["flags"]] for i in dd))
pours.update_pour("P002", {"status": "cancelled", "mixers_booked": 1}, FAC)
dd = {p["id"]: p for p in pours.decorate(pours.list_pours(), FAC)}
ok("a cancelled pour raises no flag (1 mixer booked would be a cold joint)", dd["P002"]["flags"] == [])
ok("update refuses a bad field and changes nothing", "error" in pours.update_pour("P001", {"rate_m3h": -1}, FAC)
   and pours.get_pour("P001")["rate_m3h"] == 30.0)
ok("update of a pour that does not exist", pours.update_pour("P999", {"m3": 1}, FAC).get("error") == "pour not found")

# =========================================================================== #
#  5. The weeks and days carry the pour (Q5)                                   #
# =========================================================================== #
weeks.materialise_window(MAR27, MAR27)
ws = {int(w["week_index"]): float(w["planned_qty"]) for w in weeks.list_weeks(MAR27, MAR27)
      if w["route_id"] == "R1" and w["section_id"] == "WS4"}
n_w = weeks.weeks_in_month(MAR27)
mi_p, wi_p = weeks.week_of_date(datetime.date(2027, 3, 11))
ok(f"⭐ the month's {n_w} weeks: the pour's week (wk {wi_p}) = 120 + (1000-120)/{n_w}, the others (1000-120)/{n_w}",
   abs(ws[wi_p] - (120 + 880 / n_w)) < 1e-6 and all(abs(ws[w] - 880 / n_w) < 1e-6 for w in ws if w != wi_p)
   and abs(sum(ws.values()) - 1000) < 1e-6, str(ws))
today = datetime.date(2027, 3, 9)                 # Tuesday of the pour's week: the commit bucket
res = days.list_days(today=today)
r1 = next(l for l in res["lines"] if l["route_id"] == "R1" and l["section_id"] == "WS4")
by_day = {d["day_date"]: float(d["planned_qty"]) for d in r1["days"]}
rest = (ws[wi_p] - 120) / 4
ok("⭐ the pour's day: Thu 11 Mar carries 120 m³; Mon-Wed and Fri share the rest of the week",
   abs(by_day["2027-03-11"] - 120) < 1e-6 and all(abs(by_day[d] - rest) < 1e-6 for d in
                                                   ("2027-03-08", "2027-03-09", "2027-03-10", "2027-03-12")), str(by_day))
ok("...the days add up to the week (no DAYS ≠ WEEK)", not r1["days_ne_week"])
sd_res = days.set_day("R1", MAR27, "structures", "WS4", "2027-03-11", 90.0, by="test", today=today)
ok("fixture: a planner types 90 on the pour's day", "error" not in sd_res, str(sd_res))
pours.update_pour("P001", {"m3": 150}, FAC)
res = days.list_days(today=today)
r1 = next(l for l in res["lines"] if l["route_id"] == "R1" and l["section_id"] == "WS4")
by_day2 = {d["day_date"]: (float(d["planned_qty"]), d["status"]) for d in r1["days"]}
ok("🔴 an edited day holds what was typed when the pour moves (the derived days follow)",
   by_day2["2027-03-11"] == (90.0, "edited"), str(by_day2))

# =========================================================================== #
#  6. The Look-ahead: the rail and the page                                    #
# =========================================================================== #
pours.update_pour("P001", {"m3": 120, "mixers_booked": 2}, FAC)
page = lookahead.page(today=today)
pf = [x for x in page["clashes"]["flags"] if x["code"].startswith("POUR_")]
ok("⭐ the rail: P001's COLD JOINT on its day, its line's key, the pour's id, the place in the sentence",
   any(x["code"] == "POUR_COLD_JOINT" and x["day_date"] == "2027-03-11" and x["route_id"] == "R1"
       and x["pour_id"] == "P001" and x["text"].startswith("Pier 3 base, 2027-03-11:") for x in pf), str(pf))
ok("the rail's codes list the five pour codes", all(c in page["clashes"]["codes"] for c in pours.CODES))
ok("⭐ the page lists the week's pours for the grid (P001; not the cancelled P002)",
   [p["id"] for p in page["pours"]] == ["P001"] and page["pours"][0]["m3"] == 120.0, str(page.get("pours")))
tok = access._ACCESS.set(TEAM2)
try:
    page2 = lookahead.page(today=today)
finally:
    access._ACCESS.reset(tok)
ok("🔴 another team's Look-ahead sees neither the pour nor its flag",
   page2["pours"] == [] and not any(x["code"].startswith("POUR_") for x in page2["clashes"]["flags"]))

# =========================================================================== #
#  7. The API                                                                  #
# =========================================================================== #


def as_(acc, fn, *a, **k):
    t = access._ACCESS.set(acc)
    try:
        return fn(*a, **k)
    finally:
        access._ACCESS.reset(t)


lst = as_(PLANNER, main.list_pours_ep)
ok("GET /api/pours (planner): every pour, decorated, the limits and the words",
   {p["id"] for p in lst["pours"]} == {"P001", "P002"} and lst["limits"]["cold_joint_min"] == 30.0
   and lst["words"]["POUR_SHORT"] == "MIXERS SHORT")
t2 = as_(TEAM2, main.list_pours_ep)
ok("...a team sees only its own lines' pours (team 2: none)", t2["pours"] == [])
try:
    as_(TEAM2, main.create_pour_ep, main.PourIn(**dict(BASE, pour_date="2027-03-12")))
    ok("🔴 a team cannot add a pour on another team's line", False)
except _HTTPException as e:
    ok("🔴 a team cannot add a pour on another team's line (404, as for a line it cannot see)", e.status_code == 404)
c = as_(TEAM1, main.create_pour_ep, main.PourIn(**dict(BASE, pour_date="2027-03-12", m3=60, place="Pier 4")))
ok("⭐ the line's own team adds one: decorated, with its figures", c.get("id") == "P003" and c["figures"]["loads"] == 8)
try:
    as_(TEAM1, main.create_pour_ep, main.PourIn(**dict(BASE, pour_date="2027-03-12", rate_m3h=0)))
    ok("a bad pour is a 400 in words", False)
except _HTTPException as e:
    ok("a bad pour is a 400 in words", e.status_code == 400 and "pour rate" in e.detail.lower(), e.detail)
u = as_(TEAM1, main.update_pour_ep, "P003", main.PourPatch(mixers_booked=3))
ok("PATCH: the team edits its pour", u["mixers_booked"] == 3)
try:
    as_(TEAM2, main.update_pour_ep, "P003", main.PourPatch(m3=1))
    ok("🔴 another team cannot edit it", False)
except _HTTPException as e:
    ok("🔴 another team cannot edit it (404)", e.status_code == 404)
try:
    as_(TEAM2, main.delete_pour_ep, "P003")
    ok("🔴 ...nor delete it", False)
except _HTTPException as e:
    ok("🔴 ...nor delete it (404)", e.status_code == 404 and pours.get_pour("P003") is not None)
ok("DELETE by its team", as_(TEAM1, main.delete_pour_ep, "P003") == {"deleted": "P003"} and pours.get_pour("P003") is None)
lc = as_(PLANNER, main.pour_lines)["lines"]
ok("GET /api/pours/lines: only m³ lines whose vehicle carries m³ (R1's two sections; not R2 tonnes, not R3 tipper)",
   sorted((x["route_id"], x["section_id"]) for x in lc) == [("R1", "WS2"), ("R1", "WS4")]
   and lc[0]["months"] == [MAR27] and lc[0]["vehicle_name"].startswith("Concrete mixer"), str(lc))
ok("...a team's choices are its own lines", [x["section_id"] for x in as_(TEAM2, main.pour_lines)["lines"]] == ["WS2"])

# =========================================================================== #
#  8. Config, the package, the generator, the registrations                    #
# =========================================================================== #
doc = json.loads(json.dumps(FAC))
doc.setdefault("planning", {})["pours"] = {"cold_joint_min": 500}
ok("config.validate refuses a cold-joint time out of range, in words",
   any("between 5 and 240" in p for p in config.validate(doc)), str(config.validate(doc)))
doc["planning"]["pours"] = {"transit_limit_min": 90, "cold_joint_min": 20}
ok("...and takes good ones", not any("pours" in p.lower() or "cold-joint" in p.lower() for p in config.validate(doc)))
pkg = tenant_package.export_tenant()
ok("⭐ the package carries the pours", len((pkg.get("tables") or {}).get("pours") or []) == 2, str(list((pkg.get("tables") or {}).keys())[:5]))
ok("registered: TENANTED_TABLES, ORDER (after forecasts), EMPTY_CHECK, the tenant audit",
   "pours" in db.TENANTED_TABLES and tenant_package.ORDER.index("pours") > tenant_package.ORDER.index("forecasts")
   and "pours" in tenant_package.EMPTY_CHECK and '"pours"' in read("backend/tests/test_tenant_audit.py"))
gen = read("backend/tools/make_demo_tenant.py")
sys.path.insert(0, os.path.join(BACKEND, "tools"))
ok("the generator plans three pours (fictional), one this week, one next week, the deck in Apr 2028",
   gen.count("(fictional)\", \"Pump") + gen.count("(fictional)\", \"Two pumps") == 3 and "as-of thursday" in gen
   and "next tuesday" in gen and "2028-04-19" in gen)
import make_demo_tenant as _mdt  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")      # the generator points the database at its own file on import
ok("demo_pour_date: the as-of week's Thursday, next week's Tuesday, a fixed date",
   _mdt.demo_pour_date("as-of thursday", datetime.date(2026, 10, 29)) == datetime.date(2026, 10, 29)
   and _mdt.demo_pour_date("next tuesday", datetime.date(2026, 10, 29)) == datetime.date(2026, 11, 3)
   and _mdt.demo_pour_date("2028-04-19", datetime.date(2026, 10, 29)) == datetime.date(2028, 4, 19))
ok("the module says the limits are not a standard and names the sources",
   all(s in read("backend/pours.py") for s in ("NOT A STANDARD", "BS 8500:2023", "Concrete Society", "1710.3")))

# =========================================================================== #
#  9. PR B: the preview, the Day sheet, the screens (source level)              #
# =========================================================================== #
pv = as_(PLANNER, main.preview_pour_ep, "R1", "2027-03-11", "07:30", 120, 30, discipline="structures", section_id="WS4",
         washout_min=10)
ok("⭐ the preview (nothing saved): the worked example's figures for a pour as typed",
   pv["id"] is None and pv["figures"]["needed"] == 9 and pv["figures"]["ends"] == "11:30"
   and len(pours.list_pours()) == 2, str(pv.get("figures")))
pv2 = as_(PLANNER, main.preview_pour_ep, "R1", "2027-03-16", "07:30", 900, 30, discipline="structures", section_id="WS4")
ok("the preview counts its own m³ in OVER PLAN: 120 + 900 over the line's 1000",
   "POUR_OVER_PLAN" in [x["code"] for x in pv2["flags"]], str(pv2["flags"]))
pv3 = as_(PLANNER, main.preview_pour_ep, "R1", "2027-03-11", "07:30", 900, 30, discipline="structures", section_id="WS4",
          exclude_id="P001")
ok("...and leaves out the stored pour it stands for (P001's 120 replaced by 900: no OVER PLAN)",
   "POUR_OVER_PLAN" not in [x["code"] for x in pv3["flags"]], str(pv3["flags"]))
try:
    as_(PLANNER, main.preview_pour_ep, "R1", "2027-03-11", "07:30", 120, 0, discipline="structures", section_id="WS4")
    ok("a preview with no rate is a 400 in words", False)
except _HTTPException as e:
    ok("a preview with no rate is a 400 in words", e.status_code == 400 and "pour rate" in e.detail.lower(), e.detail)
try:
    as_(TEAM2, main.preview_pour_ep, "R1", "2027-03-11", "07:30", 120, 30, discipline="structures", section_id="WS4")
    ok("🔴 a team cannot preview on another team's line", False)
except _HTTPException as e:
    ok("🔴 a team cannot preview on another team's line (404)", e.status_code == 404)

import export  # noqa: E402
from portable import pdf_text, offline  # noqa: E402
offline(export)
pg = lookahead.page(today=today)
ok("the Day sheet's pours: Thursday's is P001, Monday has none",
   [p["id"] for p in export.day_sheet_pours(pg, "2027-03-11")] == ["P001"] and export.day_sheet_pours(pg, "2027-03-08") == [])
try:
    ds = " ".join(pdf_text(export.build_day_sheet_pdf(pg, "2027-03-11"), "", raw=True).split())
except Exception as e:      # noqa: BLE001
    ds = "ERROR " + str(e)
ok("⭐ the Day sheet PDF: 'Pours today' with the place, the start, the mixers and the flag, above the lines",
   "Pours today" in ds and "Pier 3 base" in ds and "07:30" in ds and "COLD JOINT" in ds
   and ds.index("Pours today") < ds.index("FROM / TO"), ds[:400])
ds_mon = " ".join(pdf_text(export.build_day_sheet_pdf(pg, "2027-03-08"), "", raw=True).split())
ok("...Monday's sheet has no pour block", "Pours today" not in ds_mon and "FROM / TO" in ds_mon)

fe = read("frontend/index.html")
pp = fe[fe.index("const POUR_WORD = {"):fe.index("// ================================================================= Plan → Stockpiles")]
# what a person can read: the slice without its comments (// lines and {/* */} blocks)
pp_words = re.sub(r"\{/\*.*?\*/\}", "", re.sub(r"(?m)^\s*//.*$", "", pp), flags=re.S).replace("${API}", "")
ok("⭐ Plan → Pours: in the Plan group after Stockpiles, its icon, a desk page",
   '{ id: "pours", label: "Pours", glyph: "◒" }' in fe and "\n  pours: \"M" in fe
   and '{page === "pours" && !narrow && <PoursPage meta={meta} access={role} who={who} />}' in fe)
ok("the page reads /pours and /pours/lines once each; the form asks /pours/preview; writes POST / PATCH / DELETE",
   pp.count("fetch(`${API}/pours`)") == 1 and pp.count("fetch(`${API}/pours/lines`)") == 1
   and "fetch(`${API}/pours/preview?${q}`)" in pp and 'send("POST", "/pours"' in pp and 'send("PATCH", `/pours/${edit}`' in pp
   and 'send("DELETE", `/pours/${p.id}`' in pp)
ok("the row: the name opens it (row-open), one status, the ⋯ with Edit, Cancel the pour / Plan again, a red Delete… that asks",
   'className="row-open" aria-label={`Edit ${p.place || p.id}`}' in pp and "<RowStatus word={st.word}" in pp
   and ">Cancel the pour</button>" in pp and ">Plan again</button>" in pp and "window.confirm(`Delete the pour" in pp)
ok("the four figures and the round trip as one bar, named for a screen reader",
   all(w in pp for w in ("mixers needed", "between mixers", "a mixer's round trip", "first loads · pour ends"))
   and 'role="img" aria-label={"A mixer\'s round trip: "' in pp)
ok("🔴 the Pours page names no standard, no supplier and no back end (sources are in the technical guide only)",
   not re.search(r"BS 8500|EN 206|Concrete Society|Holcim|Series 1700|\bAPI\b|endpoint|server|\bHERE\b", pp_words),
   str(re.findall(r"BS 8500|EN 206|Concrete Society|Holcim|Series 1700|\bAPI\b|endpoint|server|\bHERE\b", pp_words)))
ok("⭐ the Look-ahead grid's POUR mark on the pour's day; the phone card's on the day shown",
   "const poursAt = useMemo(" in fe and 'className="pour-mark" data-pour-mark={d.day_date}' in fe
   and "const pourLines = new Set(((page && page.pours) || []).filter(p => p.pour_date === shown)" in fe)
ok("Config → Planning: the two limits, blank = 120 and 30, the hint says the specification wins",
   'data-cfg={"pours-" + k}' in fe and '"transit_limit_min", "Concrete: loading to the end of discharge, at most (minutes)", "120"' in fe
   and '"cold_joint_min", "Concrete: cold joint when the face waits more than (minutes)", "30"' in fe
   and "Your specification or the supplier's ticket wins." in fe)
ug = read("frontend/help/index.html")
tg = read("frontend/help/technical/index.html")
ok("⭐ the user guide's chapter 16 (three sections, in the contents): the figures, the flags, where pours show",
   '<h1 id="16-concrete-pours">16. Concrete pours</h1>' in ug and ug.count('<h2 id="16-') == 3
   and '<a href="#16-concrete-pours">16. Concrete pours</a>' in ug and "settings, not a standard" in ug)
ok("...the technical guide's T1 entry holds the sources and the arithmetic",
   '<h2 id="t1-pours">Concrete pours</h2>' in tg
   and all(w in tg for w in ("BS 8500:2023", "Concrete Society", "1710.3", "split_month", "was not read")))

_aud = read("backend/tests/ui_audit.js")
ok("the UI audit walks Plan > Pours (portal and team pages, its header named, a deep stop on the first pour opened)",
   # NARROWED 29 Oct 2026 (the Simulation's own page): the Simulation follows Pours in the portal pages
   '"stockpiles", "pours", "simulation", "lookahead"' in _aud and 'pours: "Pours"' in _aud and 'meta("pours+open", w)' in _aud
   and re.search(r'const TEAM_PAGES = \[[^\n]*"pours"', _aud) is not None)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
