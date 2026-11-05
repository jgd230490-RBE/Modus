"""
Busy hours: use another road at those times (5 Nov 2026, task 0d-2). The user: "Yes, as recommended" to Q1-Q20 of
notes/busy-hours-apply-mockup-1105 (a planner can take a collision busy-hours offer and "use Alt N on weekdays in
these hours", stop it again, and see what it saves or adds).

WHAT IS ASSERTED
----------------
  * route_choice.line_fp (in the DDL and ALTERed on an old database);
  * use_busy: one 'peak' row per (lorry type, leg) that has its own Alt N (Q1), weekdays, the offered hours, the line's
    fingerprint; a type without Alt N stays on the main line; a second Use of the band replaces the first;
  * busy_share by the route's open window; mix(): the trips setting off in the hours take Alt N (Q2, Q4), a zone row
    still decides its days (Q10); month_weights / in_use(kinds=zone) / periods stay on the zones (Q9);
  * derived.cycle_for follows (distance by share of trips) and carries busy_hours; the Look-ahead context has it;
  * busy_alt_at (the Simulation's per-trip road): by the minute a leg sets off, weekdays only, a zone first;
  * a Route all that changes Alt N pauses the use (Q11); Use again; Stop (Q13 roles: planner yes, submitter no);
  * busy_savings: planned trips in the hours x the difference a trip makes, a dearer road ADDS (Q19), recorded loads
    from the Use date as "so far" (Q18); better_all_day (Q3);
  * the endpoint answers: uses, offered (Q12), can_use; source guards for the readers that must not follow.

WHAT THIS DOES NOT PROVE
------------------------
HERE and the collision records are not used: the offer itself is test_collisions' business, and the endpoint's
"offered now" check is exercised with collisions.busy_hours stubbed. Postgres is not run. The screens are parse_frontend /
parse_map / dom_frontend and the Chrome check.

Run:  python3 backend/tests/test_busy_hours.py
"""
import datetime
import json
import os
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
        self.cookies = {}


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

TMP = tempfile.mkdtemp(prefix="rbe_bh_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import route_choice  # noqa: E402
import derived  # noqa: E402
import access  # noqa: E402
import collisions  # noqa: E402
import fairprice  # noqa: E402
import busy_savings  # noqa: E402
import weeks  # noqa: E402

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


def raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()
access.set_current("planner123")

# =========================================================================== #
#  Fixture: R1 L1 -> L2, the main line 7 km, Alt 2 8 km (longer, the safer    #
#  road of the R001 kind); R3 whose Alt 1 is shorter AND quicker (R013's kind) #
#  A Flatbed on R1 has a main line only.                                       #
# =========================================================================== #
ART = "Artic Tipper (44t)"
FLAT = "Artic Flatbed (44t)"
LAT = 52.5
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
for rid in ("R1", "R3"):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, 'L1', 'L2', 'Small aggregate', 'IPT1')", (rid,))
MAIN = [[-1.0, LAT], [-0.95, LAT], [-0.9, LAT]]
NORTH = [[-1.0, LAT], [-0.95, LAT + 0.01], [-0.9, LAT]]
FAR = [[-1.0, LAT], [-0.95, LAT + 0.02], [-0.9, LAT]]
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.002], [-0.948, LAT - 0.002], [-0.948, LAT + 0.002],
                                           [-0.952, LAT + 0.002], [-0.952, LAT - 0.002]]]}


def put(rid, leg, alt, line, km, hr, prof=ART):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, prof, json.dumps(line), km, hr, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="", avoids=None)


for leg in ("loaded", "return"):
    put("R1", leg, 0, MAIN, 7.0, 0.20)
    put("R1", leg, 1, FAR, 9.0, 0.24)
    put("R1", leg, 2, NORTH, 8.0, 0.22)
    put("R1", leg, 0, MAIN, 7.0, 0.21, prof=FLAT)
    put("R3", leg, 0, FAR, 9.0, 0.24)
    put("R3", leg, 1, MAIN, 7.0, 0.20)

# =========================================================================== #
#  1. The column                                                               #
# =========================================================================== #
cols = {r["name"] if isinstance(r, dict) and "name" in r else r[1] for r in db.query("PRAGMA table_info(route_choice)")}
ok("⭐ route_choice.line_fp exists (the busy-hours road's line when put in use)", "line_fp" in cols, str(cols))
ok("🔴 ...in the DDL AND ALTERed on an old database", "line_fp         TEXT" in db._TENANT_DDL["route_choice"]
   and "ALTER TABLE route_choice ADD COLUMN line_fp TEXT" in read("backend/db.py"))

# =========================================================================== #
#  2. Use                                                                      #
# =========================================================================== #
ok("busy_share: 16:00–19:00 in a 06:00–18:00 window is 2 h of 12", abs(route_choice.busy_share("16:00", "19:00", (360, 1080)) - 2 / 12) < 1e-9)
ok("...hours outside the window are 0", route_choice.busy_share("19:00", "21:00", (360, 1080)) == 0.0)
SPAN = route_choice.busy_span("R1")
ok("⭐ the route's open window: no gate at either end -> the default gate hours (08:00–17:00)", SPAN == (480, 1020), str(SPAN))
e = raises(lambda: route_choice.use_busy("R1", 0, "16:00", "19:00"))
ok("Use of the main line is refused in words", isinstance(e, route_choice.BusyError) and "other roads" in str(e))
e = raises(lambda: route_choice.use_busy("R1", 5, "16:00", "19:00"))
ok("Use of a road not stored is refused in words", isinstance(e, route_choice.BusyError) and "Route it again" in str(e))
n = route_choice.use_busy("R1", 1, "16:00", "19:00", who="Pat")
n = route_choice.use_busy("R1", 2, "16:00", "19:00", who="Pat")          # the planner changes their mind: Alt 2
rows = db.query("SELECT * FROM route_choice WHERE tenant_id = ? AND reason_kind = 'peak'", (db.current_tenant(),))
ok("⭐ Q1: one row per lorry type and leg that has its own Alt N (the tipper's two legs; the flatbed has none)",
   n == 2 and len(rows) == 2 and {r["vehicle_profile"] for r in rows} == {ART} and {r["leg"] for r in rows} == {"loaded", "return"},
   str([(r["vehicle_profile"], r["leg"]) for r in rows]))
ok("⭐ a second Use of the same hours REPLACES the first (Alt 2, not Alt 1 and Alt 2)", all(int(r["alt_index"]) == 2 for r in rows))
ok("...weekdays, the offered hours, in use, by the planner, with its line's fingerprint and the change in length",
   all(r["days"] == "1111100" and r["hours_from"] == "16:00" and r["hours_to"] == "19:00" and r["status"] == "in_use"
       and r["source"] == "planner" and r["decided_by"] == "Pat" and r["line_fp"] and abs(float(r["km_delta"]) - 1.0) < 1e-9
       for r in rows), str(rows))

# =========================================================================== #
#  3. The figures follow by share of trips                                     #
# =========================================================================== #
NOV27 = (2027 - 2026) * 12 + 11
SH = 1 / 9                         # 16:00–17:00 of 08:00–17:00
m = route_choice.mix("R1", ART, route_choice.month_days(NOV27))
ok("⭐ Q4: a month with no zone: 1/9 of the trips on (2, 2), the rest on the main line",
   abs(dict(m["pairs"]).get((2, 2), 0) - SH) < 1e-5 and abs(dict(m["pairs"]).get((0, 0), 0) - (1 - SH)) < 1e-5, str(m))
ok("...the busy share is said, the zones' diverted share stays 0", abs(m["busy"]["share"] - SH) < 1e-4 and m["diverted"] == 0.0
   and m["busy"]["options"][0]["alt"] == 2 and m["busy"]["options"][0]["from"] == "16:00", str(m))
ok("⭐ Q1: the flatbed (no Alt 2 stored) stays on the main line", route_choice.mix("R1", FLAT, route_choice.month_days(NOV27))["pairs"] == [((0, 0), 1.0)])
ok("⭐ Q9: month_weights (shared roads, councils) stays on the main line",
   route_choice.month_weights("R1", ART, NOV27)["pairs"] == [((0, 0), 1.0)])
ok("⭐ Q9: in_use() for the strips takes the busy road; kinds=('zone',) does not",
   ("R1", ART, "loaded") in route_choice.in_use() and not route_choice.in_use(kinds=("zone",)))
ok("...in_use_keys names it like a diversion's (R1@2)", "R1@2" in route_choice.in_use_keys())
ok("Q9: periods (the Diversions list) leaves busy-hours rows out", route_choice.periods("R1") == [])
c = derived.cycle_for("R1", ART, {}, month_index=NOV27)
ok("⭐ cycle_for: the distance by share of trips (7 x 8/9 + 8 x 1/9)", abs(c["loaded_km"] - round(7 * (1 - SH) + 8 * SH, 3)) < 2e-3,
   str(c.get("loaded_km")))
ok("...and the row carries busy_hours, not a diversion share", c["busy_hours"]["share"] > 0 and c["diversion"]["share"] == 0.0)
ctx = derived.line_context({"route_id": "R1", "vehicle_type": ART, "unit": "t", "month_index": NOV27,
                            "week": {"planned_qty": 100}}, conversions.load_factors())
ok("⭐ a line's context (Look-ahead, cost lines, carbon) carries busy_hours", (ctx.get("busy_hours") or {}).get("share", 0) > 0)

# a dated zone on R1 in Dec 2027: Q10, the zone decides its days
ZD = zones.create_zone("Christmas trading", BOX, kind="closure", affects_routing=True,
                       starts_on="2027-12-01", ends_on="2027-12-17")["id"]
route_choice.refresh_zones()
DEC27 = NOV27 + 1
md = route_choice.mix("R1", ART, route_choice.month_days(DEC27))
ok("⭐ Q10: a dated closure wins its 13 days; the busy road takes 1/9 of the other 10 only",
   abs(md["busy"]["share"] - SH * 10 / 23) < 1e-4 and abs(md["diverted"] - 13 / 23) < 1e-3, str(md))
ok("...the status of the busy-hours rows is kept by a zone refresh (it rewrites zone rows only)",
   {r["status"] for r in db.query("SELECT status FROM route_choice WHERE tenant_id = ? AND reason_kind = 'peak'",
                                  (db.current_tenant(),))} == {"in_use"})

# =========================================================================== #
#  4. The Simulation's per-trip road                                           #
# =========================================================================== #
MON = datetime.date(2027, 11, 8)
ok("⭐ Q2: a leg setting off at 16:30 on a weekday takes Alt 2", route_choice.busy_alt_at("R1", ART, "loaded", MON, 16 * 60 + 30) == 2)
ok("...at 15:59 the main line; at 19:00 the main line", route_choice.busy_alt_at("R1", ART, "loaded", MON, 959) == 0
   and route_choice.busy_alt_at("R1", ART, "loaded", MON, 19 * 60) == 0)
ok("...on a Saturday the main line", route_choice.busy_alt_at("R1", ART, "loaded", MON + datetime.timedelta(days=5), 990) == 0)
ok("...a zone day: the zone's option, whatever the hour (Q10)",
   route_choice.busy_alt_at("R1", ART, "loaded", datetime.date(2027, 12, 6), 990) == route_choice.alt_on("R1", ART, "loaded", "2027-12-06"))

# =========================================================================== #
#  5. Savings                                                                  #
# =========================================================================== #
FAC = conversions.load_factors()
COST = {"index_eur_per_l": 1.5, "fair_params": fairprice.params(FAC)}
db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, unit, material_type, "
           "vehicle_type, status, ipt) VALUES ('F1', 'R1', ?, 'earthworks', 'WS1', 2900, 't', 'Small aggregate', ?, "
           "'Approved', 'IPT1')", (NOV27, ART))
db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, unit, material_type, "
           "vehicle_type, status, ipt) VALUES ('F2', 'R1', ?, 'earthworks', 'WS1', 2900, 't', 'Small aggregate', ?, "
           "'Pending', 'IPT1')", (NOV27 + 2, ART))
use = route_choice.busy_uses("R1")[0]
ok("busy_uses: one use for the band, in use, Alt 2, with its legs", len(route_choice.busy_uses("R1")) == 1
   and use["status"] == "in_use" and use["alt"] == 2 and len(use["legs"]) == 2, str(use))
pt = busy_savings.per_trip("R1", ART, (2, 2), NOV27, COST, FAC)
ok("⭐ per trip: Alt 2 both ways is 2 km longer and slower, with more CO2e and a dearer fair price (Q19: it ADDS)",
   abs(pt["km"] - 2.0) < 1e-6 and pt["min"] > 0 and pt["kg"] > 0 and pt["eur"] > 0, str(pt))
sv = busy_savings.for_use(use, factors=FAC, cost=COST)
trips = sv["planned"]["of"]
ok("⭐ planned: the Approved lines only (the Pending month left out), trips in the hours = trips x the month's share",
   trips == 100 and abs(sv["planned"]["trips"] - round(100 * SH, 1)) < 0.06, str(sv["planned"]))
ok("...km = trips in the hours x the 2 km a trip adds", abs(sv["planned"]["km"] - round(100 * SH * 2.0, 1)) < 0.06, str(sv["planned"]))
ok("...nothing recorded yet: so far is 0 of 0", sv["so_far"]["of"] == 0 and sv["so_far"]["kg"] == 0)
weeks.materialise_line("R1", "earthworks", "WS1", NOV27)
wk = db.query("SELECT week_index FROM forecast_weeks WHERE tenant_id = ? AND route_id = 'R1' AND month_index = ? "
              "ORDER BY week_index", (db.current_tenant(), NOV27))
weeks.set_actual("R1", NOV27, "earthworks", "WS1", int(wk[0]["week_index"]), actual_qty=580, by="Sam")
sv2 = busy_savings.for_use(use, factors=FAC, cost=COST)
ok("⭐ Q18: so far from the recorded loads (580 t = 20 trips), estimated by the week's share",
   sv2["so_far"]["of"] == 20 and sv2["so_far"]["trips"] > 0 and sv2["so_far"]["kg"] > 0, str(sv2["so_far"]))
old = dict(use, decided_at="2028-01-01T00:00:00+00:00")
sv3 = busy_savings.for_use(old, factors=FAC, cost=COST)
ok("...a Use pressed after the month counts none of it", sv3["planned"]["of"] == 0 and sv3["so_far"]["of"] == 0, str(sv3))
ok("⭐ Q3: R1's Alt 2 is longer — not 'better all day'", busy_savings.better_all_day("R1", 2) is False)
ok("⭐ Q3: R3's Alt 1 is shorter and quicker — 'better all day'", busy_savings.better_all_day("R3", 1) is True)

# =========================================================================== #
#  6. The endpoint, the roles, Stop, pause                                     #
# =========================================================================== #
_real_busy = collisions.busy_hours
collisions.busy_hours = lambda rid, acc=None: {"shown": True, "period": "2021–2025", "offers": [
    {"label": "Alt 2", "alt": 2, "bands": [{"from": "16:00", "to": "19:00", "route": 14, "alt": 5}], "midday": None}]}
out = main._with_busy_uses("R1", collisions.busy_hours("R1"))
ok("⭐ the answer: the route's uses with their figures, the offer marked in use, can_use for a planner",
   out["uses"][0]["savings"]["planned"]["of"] == 100 and out["offers"][0]["in_use"] == ["16:00"]
   and out["uses"][0]["offered"] is True and out["can_use"] is True, str(out)[:400])
ok("...the offer says whether Alt 2 is better all day (Q3)", out["offers"][0]["better_all_day"] is False)
collisions.busy_hours = lambda rid, acc=None: {"shown": True, "period": "2021–2025", "offers": []}
out = main._with_busy_uses("R1", collisions.busy_hours("R1"))
ok("⭐ Q12: no longer offered after a fetch, it stays in use and says so", out["uses"][0]["status"] == "in_use"
   and out["uses"][0]["offered"] is False)
tok = access.set_current("submitter123")
e = raises(lambda: main.busy_hours_use("R1", {"stop": True, "from": "16:00"}))
ok("⭐ Q13: a submitter cannot Use or Stop", getattr(e, "status_code", None) == 403, str(e))
access.reset_current(tok)
tok = access.set_current(None)
e = raises(lambda: main.busy_hours_use("R1", {"stop": True, "from": "16:00"}))
ok("...nor anyone signed out (401)", getattr(e, "status_code", None) == 401, str(e))
access.reset_current(tok)
e = raises(lambda: main.busy_hours_use("R1", {"alt": 1, "from": "07:00", "to": "10:00"}))
ok("⭐ Use of hours that are not offered now is refused (409, in words)", getattr(e, "status_code", None) == 409
   and "not offered" in str(e), str(e))
e = raises(lambda: main.busy_hours_use("R9", {"alt": 1, "from": "07:00", "to": "10:00"}))
ok("...a route not here is a 404", getattr(e, "status_code", None) == 404, str(e))
out = main.busy_hours_use("R1", {"stop": True, "from": "16:00"})
ok("⭐ Stop: the use is stopped and the month back on the main line", out["uses"][0]["status"] == "stopped"
   and route_choice.mix("R1", ART, route_choice.month_days(NOV27))["pairs"] == [((0, 0), 1.0)])
e = raises(lambda: main.busy_hours_use("R1", {"alt": 2, "from": "16:00", "to": "19:00"}))
ok("⭐ Use again on a STOPPED band that is no longer offered: refused (Use needs an offer, or a use in use / paused)",
   getattr(e, "status_code", None) == 409, str(e))
collisions.busy_hours = lambda rid, acc=None: {"shown": True, "period": "2021–2025", "offers": [
    {"label": "Alt 2", "alt": 2, "bands": [{"from": "16:00", "to": "19:00", "route": 14, "alt": 5}], "midday": None}]}
out = main.busy_hours_use("R1", {"alt": 2, "from": "16:00", "to": "19:00"})
ok("...offered again: Use puts it back in use", out["uses"][0]["status"] == "in_use", str(out["uses"]))
collisions.busy_hours = _real_busy
# Q11: a Route all that changes Alt 2's line pauses the use
put("R1", "loaded", 2, FAR, 9.0, 0.24)
route_choice.refresh_zones()
st = {r["leg"]: r["status"] for r in db.query("SELECT leg, status FROM route_choice WHERE tenant_id = ? AND reason_kind = 'peak'",
                                              (db.current_tenant(),))}
ok("⭐ Q11: the changed leg's use is paused; the unchanged leg stays in use", st == {"loaded": "paused", "return": "in_use"}, str(st))
ok("...the use reads paused, and the busy hours on the loaded leg go back to the main line",
   route_choice.busy_uses("R1")[0]["status"] == "paused"
   and route_choice.busy_alt_at("R1", ART, "loaded", MON, 990) == 0 and route_choice.busy_alt_at("R1", ART, "return", MON, 990) == 2)
route_choice.use_busy("R1", 2, "16:00", "19:00", who="Pat")
ok("...Use again takes the new line and is in use", route_choice.busy_uses("R1")[0]["status"] == "in_use")

# =========================================================================== #
#  7. Source guards                                                            #
# =========================================================================== #
ok("🔴 councils and the shared roads stay on the zones (Q9)", 'route_choice.in_use(kinds=("zone",))' in read("backend/areas.py")
   and 'route_choice.in_use(profile, kinds=("zone",))' in read("backend/road_sections.py"))
ok("🔴 month_weights asks mix without the busy hours", "rows=rows, peaks=False)" in read("backend/route_choice.py"))
ok("🔴 a bake's refresh checks the busy-hours roads (Q11)", "check_busy()" in read("backend/route_choice.py"))
ok("🔴 the collision-hours answer carries the uses", "return _with_busy_uses(route_id, out)" in read("backend/main.py"))
ok("🔴 the Use endpoint guards planner / admin", '_require_planner_or_admin("use another road in the busy hours")' in read("backend/main.py"))

remove_scratch_db(db, TMP)
print(f"test_busy_hours: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  ✗", f)
sys.exit(1 if FAIL else 0)
