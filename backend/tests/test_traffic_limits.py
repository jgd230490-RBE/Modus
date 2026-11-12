"""
Traffic limits (9 Nov 2026, v2.1 task 2.1-1): a limit on the lorries a road or an area may carry, drawn on Zones as
kind "Traffic limit", checked against the approved plan. John's Q1-Q12 as recommended.

WHAT IS ASSERTED
----------------
  * the fields: a number > 0, movements / visits, average / busiest day, the public tick; a limit never routes;
    another kind carries no limit; a zone that stops being a limit loses its fields;
  * which legs pass: a line within 25 m for half its length, an area entered 200 m (less for a small one), a road
    beside a line or an area does not; every stored option is tested;
  * the count (Q2): the loaded leg "in" and the empty way back "out", each only on the roads it runs; visits count a
    route once; this scheme's drawn routes only; over / near (90 %) / ok;
  * dated limits use the in-force working days (Q7); a dated diversion moves the share of a route on the road;
  * the busiest-day check on planned days (day_counts); the flag words (TRAFFIC LIMIT / TRAFFIC NEAR, not ROAD LIMIT);
  * summary(): public only, the Sites filter; through() for 2.1-4.

WHAT THIS DOES NOT PROVE
------------------------
HERE and Mapbox are never called; Postgres is not run; the screens are checked by the source pins in parse_frontend /
parse_map and in Chrome.

Run:  python3 backend/tests/test_traffic_limits.py
"""
import json
import os
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

TMP = tempfile.mkdtemp(prefix="rbe_tlim_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import route_choice  # noqa: E402
import counting  # noqa: E402
import traffic_limits as TL  # noqa: E402
import datetime as dt  # noqa: E402

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


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture: R1 loaded west->east along lat 52.5 (MAIN), back along the        #
#  northern road (lat 52.51). R2 both ways on MAIN. R1's loaded option 1 is   #
#  the northern road; a dated closure (1-17 Dec 2027) on MAIN diverts it.     #
# =========================================================================== #
ART = network.DEFAULT_PROFILE
LAT = 52.5
for lid, lon in (("L1", -1.0), ("L2", -0.9), ("L3", -1.0)):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, 'Quarry')", (lid, lid, LAT, lon))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R2', 'L3', 'L2', 'Small aggregate', 'IPT1')")


def pts(lats, lon0=-1.0, lon1=-0.9, n=11):
    return [[round(lon0 + (lon1 - lon0) * i / (n - 1), 6), lats(i)] for i in range(n)]


MAIN = pts(lambda i: LAT)
NORTH = [[-1.0, LAT]] + pts(lambda i: LAT + 0.01, -0.99, -0.91, 9) + [[-0.9, LAT]]


def put(rid, leg, alt, line, km):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, ART, json.dumps(line), km, km / 40.0, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="")


put("R1", "loaded", 0, MAIN, 7.0)
put("R1", "loaded", 1, NORTH, 8.0)
put("R1", "return", 0, NORTH, 8.0)
put("R2", "loaded", 0, MAIN, 7.0)
put("R2", "return", 0, MAIN, 7.0)
DRAWN = {"R1": ART, "R2": ART}
DEC27, NOV27 = 24, 23
LINES = {m: [{"route_id": "R1", "vehicle_loads": 230.0, "co2_t": 1.0, "ipt": "IPT1"},
             {"route_id": "R2", "vehicle_loads": 100.0, "co2_t": 1.0, "ipt": "IPT1"}] for m in (NOV27, DEC27)}


def ctx(lines=None, wd=20.0):
    return {"drawn": DRAWN, "legs": TL._legs(DRAWN), "rows": route_choice._rows_by_route(), "share_cache": {},
            "wd": wd, "lines_by_month": (lambda: (lines if lines is not None else LINES, None)), "months": 30}


ROAD = {"type": "LineString", "coordinates": [[-0.97, LAT], [-0.95, LAT], [-0.93, LAT]]}
ROAD_11M = {"type": "LineString", "coordinates": [[-0.97, LAT + 0.0001], [-0.93, LAT + 0.0001]]}
ROAD_33M = {"type": "LineString", "coordinates": [[-0.97, LAT + 0.0003], [-0.93, LAT + 0.0003]]}
# 0.68 km on MAIN, then 1.33 km away north: about a third of the line within 25 m
ROAD_BEND = {"type": "LineString", "coordinates": [[-0.96, LAT], [-0.95, LAT], [-0.95, LAT + 0.012]]}
AREA = {"type": "Polygon", "coordinates": [[[-0.96, LAT - 0.002], [-0.94, LAT - 0.002], [-0.94, LAT + 0.002],
                                            [-0.96, LAT + 0.002], [-0.96, LAT - 0.002]]]}
SMALL = {"type": "Polygon", "coordinates": [[[-0.9507, LAT - 0.00045], [-0.9493, LAT - 0.00045],
                                             [-0.9493, LAT + 0.00045], [-0.9507, LAT + 0.00045],
                                             [-0.9507, LAT - 0.00045]]]}
BESIDE = {"type": "Polygon", "coordinates": [[[-0.96, LAT + 0.0005], [-0.94, LAT + 0.0005], [-0.94, LAT + 0.003],
                                              [-0.96, LAT + 0.003], [-0.96, LAT + 0.0005]]]}

# =========================================================================== #
#  1. The fields                                                               #
# =========================================================================== #
z = zones.create_zone("Main Street limit", ROAD, kind="traffic_limit", limit_value=21, affects_routing=True)
ok("⭐ a traffic limit is a zone kind", "traffic_limit" in zones.KINDS and z.get("kind") == "traffic_limit", str(z))
ok("🔴 Q11: a traffic limit never routes, even when sent affects_routing", z.get("affects_routing") is False,
   str(z.get("affects_routing")))
ok("defaults: movements, daily average, on the public map (Q6)",
   z.get("limit") == {"value": 21.0, "counts": "movements", "basis": "average", "public": True}, str(z.get("limit")))
ok("the Zones chip reads 'Limit 21 / day'", TL.chip(z["limit"]) == "Limit 21 / day")
ok("🔴 no number: refused in words",
   zones.create_zone("x", ROAD, kind="traffic_limit").get("error") == "a traffic limit needs a number (lorries a day)")
ok("🔴 0 refused", "more than 0" in (zones.create_zone("x", ROAD, kind="traffic_limit", limit_value=0).get("error") or ""))
ok("🔴 an unknown unit refused", "movements or visits" in (zones.create_zone(
   "x", ROAD, kind="traffic_limit", limit_value=5, limit_counts="lorries").get("error") or ""))
ok("🔴 an unknown basis refused", "busiest day" in (zones.create_zone(
   "x", ROAD, kind="traffic_limit", limit_value=5, limit_basis="peak").get("error") or ""))
c = zones.create_zone("Closure", AREA, kind="closure", limit_value=99, affects_routing=False)
ok("another kind carries no limit, whatever is sent", c.get("limit") is None and db.query(
   "SELECT limit_value FROM zones WHERE tenant_id = ? AND id = ?", (db.current_tenant(), c["id"]))[0]["limit_value"] is None)
ok("🔴 an existing zone made a limit needs a number",
   (zones.update_zone(c["id"], kind="traffic_limit").get("error") or "").startswith("a traffic limit needs"))
u = zones.update_zone(c["id"], kind="traffic_limit", limit_value=50, limit_counts="visits", affects_routing=True)
ok("...with one it becomes a limit, visits, and stops routing",
   (u.get("limit") or {}).get("counts") == "visits" and u.get("affects_routing") is False, str(u))
u2 = zones.update_zone(c["id"], limit_basis="busiest_day", limit_public=False)
ok("a partial edit keeps the value and unit",
   u2.get("limit") == {"value": 50.0, "counts": "visits", "basis": "busiest_day", "public": False}, str(u2.get("limit")))
u3 = zones.update_zone(c["id"], kind="closure")
ok("a limit that becomes another kind loses its fields", u3.get("limit") is None and db.query(
   "SELECT limit_counts FROM zones WHERE tenant_id = ? AND id = ?", (db.current_tenant(), c["id"]))[0]["limit_counts"] is None)
zones.update_zone(c["id"], active=False)
ok("limit_zones: active traffic limits with a number only", [x["id"] for x in TL.limit_zones()] == [z["id"]])

# =========================================================================== #
#  2. Which legs pass (Q5)                                                     #
# =========================================================================== #
C = ctx()


def P(g):
    return TL.passing(g, drawn=C["drawn"], legs=C["legs"])


p = P(ROAD)
ok("⭐ a line on MAIN: R1's loaded leg (option 0) and both of R2's legs pass; R1's way back (north) does not",
   p == {"R1": {"loaded": {0}, "return": set()}, "R2": {"loaded": {0}, "return": {0}}}, str(p))
ok("a line drawn 11 m off the road still counts (within 25 m)", set(P(ROAD_11M)) == {"R1", "R2"})
ok("🔴 a line 33 m off the road does not", P(ROAD_33M) == {}, str(P(ROAD_33M)))
ok("🔴 a line that leaves the road (under half its length within 25 m) does not", P(ROAD_BEND) == {}, str(P(ROAD_BEND)))
NROAD = {"type": "LineString", "coordinates": [[-0.97, LAT + 0.01], [-0.93, LAT + 0.01]]}
pn = P(NROAD)
ok("a line on the northern road: R1's way back and its loaded option 1", pn == {"R1": {"loaded": {1}, "return": {0}}}, str(pn))
ok("⭐ an area MAIN crosses: R1 in, R2 both",
   P(AREA) == {"R1": {"loaded": {0}, "return": set()}, "R2": {"loaded": {0}, "return": {0}}}, str(P(AREA)))
ok("an area 100 m across: a route right through it counts (entry shrinks to a quarter of its diagonal)",
   set(P(SMALL)) == {"R1", "R2"}, str(P(SMALL)))
ok("🔴 an area beside the road (its edge 55 m off) does not", P(BESIDE) == {}, str(P(BESIDE)))

# =========================================================================== #
#  3. The count (Q2, Q3, Q8)                                                   #
# =========================================================================== #
f = TL.through(ROAD, NOV27, ctx=C)
# R1 230 / 20 = 11.5 in, 0 out; R2 100 / 20 = 5 in, 5 out
ok("⭐ in = the loaded legs on the road (11.5 + 5), out = the ways back on it (5: R1 comes back north)",
   f["in_per_day"] == 16.5 and f["out_per_day"] == 5.0 and f["movements_per_day"] == 21.5, str(f))
ok("⭐ visits count a route once: 11.5 + 5", f["visits_per_day"] == 16.5, str(f))
ok("the routes listed with their own split",
   {r["route_id"]: (r["in_per_day"], r["out_per_day"]) for r in f["routes"]} == {"R1": (11.5, 0.0), "R2": (5.0, 5.0)})
ok("a route both ways on the road: 5 visits = 10 movements, counting's rule",
   counting.convert(5.0, counting.VISITS, counting.MOVEMENTS) == 10.0)
cz = dict(C)
cz["lines_by_month"] = lambda: ({NOV27: LINES[NOV27] + [{"route_id": "RX", "vehicle_loads": 999.0}]}, None)
ok("🔴 a line on a route the map does not draw adds nothing",
   TL.through(ROAD, NOV27, ctx=cz)["movements_per_day"] == 21.5)
ok("states: 21.5 vs 21 over, vs 23 near (90 %), vs 30 ok, none without a limit",
   (TL.state_of(21.5, 21), TL.state_of(21.5, 23), TL.state_of(21.5, 30), TL.state_of(None, 30))
   == ("over", "near", "ok", "none"))
ok("near starts at exactly 90 % (Q8)", TL.state_of(18.0, 20) == "near" and TL.state_of(17.99, 20) == "ok")
zl = TL.limit_zones()[0]
chk = TL.check(zl, [NOV27], ctx=C)
ok("⭐ check: Nov 2027 21.5 movements against 21 = over", chk[NOV27]["value"] == 21.5 and chk[NOV27]["state"] == "over", str(chk))
zv = dict(zl)
zv["limit"] = dict(zl["limit"], counts="visits")
ok("...the same road in visits: 16.5 against 21 = ok", TL.check(zv, [NOV27], ctx=C)[NOV27]["state"] == "ok")
ok("a month with no lines reads 0, ok", TL.check(zl, [5], ctx=C)[5]["value"] == 0 and TL.check(zl, [5], ctx=C)[5]["state"] == "ok")

# =========================================================================== #
#  4. Dated limits (Q7) and a dated diversion                                  #
# =========================================================================== #
zd = dict(zl, starts_on="2027-11-15", ends_on="2027-12-31")
cd = TL.check(zd, [NOV27 - 1, NOV27, DEC27], ctx=C)
nov_days = TL.in_force_days(zd, NOV27)
ok("⭐ a limit from 15 Nov: not in force in Oct 2027, Nov counts its in-force working days only",
   (NOV27 - 1) not in cd and cd[NOV27]["days"] == len(nov_days) and 0 < len(nov_days) < len(route_choice.month_days(NOV27)),
   str({k: v["days"] for k, v in cd.items()}))
ok("...an even spread: the in-force days' average equals the month's", cd[NOV27]["value"] == 21.5)
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.002], [-0.948, LAT - 0.002], [-0.948, LAT + 0.002],
                                           [-0.952, LAT + 0.002], [-0.952, LAT - 0.002]]]}
cl = zones.create_zone("Christmas works", BOX, kind="closure", affects_routing=True,
                       starts_on="2027-12-01", ends_on="2027-12-17")
route_choice.refresh_zones()
C2 = ctx()
ok("fixture: R1's loaded leg goes north 1-17 Dec 2027", route_choice.alt_on("R1", ART, "loaded", "2027-12-06") == 1)
fd = TL.through(ROAD, DEC27, ctx=C2)
r1 = next((r for r in fd["routes"] if r["route_id"] == "R1"), {})
dec_days = len(route_choice.month_days(DEC27))
main_days = sum(1 for d in route_choice.month_days(DEC27) if route_choice.alt_on("R1", ART, "loaded", d.isoformat()) == 0)
ok("⭐ Dec 2027: R1 counts on MAIN only on the days it uses MAIN (11.5 x those days / the month's)",
   abs(r1.get("in_per_day", -1) - round(11.5 * main_days / dec_days, 2)) < 0.011 and 0 < main_days < dec_days
   and r1.get("out_per_day") == 0, str((r1, main_days, dec_days)))
zdec = dict(zl, starts_on="2027-12-01", ends_on="2027-12-17")
cdec = TL.check(zdec, [DEC27], ctx=C2)
ok("🔴 a limit in force only 1-17 Dec: R1 is never on MAIN then, so only R2 counts (10 movements)",
   cdec[DEC27]["value"] == 10.0, str(cdec))
fn = TL.through(NROAD, DEC27, ctx=C2)
ok("...and the northern road gains R1's diverted share (in) beside its usual way back (out)",
   abs(fn["in_per_day"] - round(11.5 * (dec_days - main_days) / dec_days, 2)) < 0.011 and fn["out_per_day"] == 11.5, str(fn))
zones.update_zone(cl["id"], active=False)
route_choice.refresh_zones()

# =========================================================================== #
#  5. The planned days (Q4)                                                    #
# =========================================================================== #
C3 = ctx()
zb = dict(zl, limit=dict(zl["limit"], basis="busiest_day", value=20))
dc = TL.day_counts(zb, {"2027-11-08": {"R1": 9, "R2": 6}, "2027-11-09": {"R1": 12, "R2": 6}}, ctx=C3)
ok("⭐ busiest day: 9 in + 6 in + 6 out = 21 over 20; 12 + 12 = 24 over",
   dc["2027-11-08"]["value"] == 21 and dc["2027-11-09"]["value"] == 24 and dc["2027-11-08"]["state"] == "over", str(dc))
ok("...the day's split kept", (dc["2027-11-08"]["in"], dc["2027-11-08"]["out"], dc["2027-11-08"]["visits"]) == (15, 6, 15))
dc2 = TL.day_counts(dict(zb, starts_on="2027-11-09"), {"2027-11-08": {"R1": 9}, "2027-11-09": {"R1": 9}}, ctx=C3)
ok("a day before the limit starts is not checked", list(dc2) == ["2027-11-09"])
ok("🔴 Q1: the flags are TRAFFIC LIMIT / TRAFFIC NEAR, never ROAD LIMIT (the signed weight / height flag)",
   TL.FLAG_WORDS == {"over": "TRAFFIC LIMIT", "near": "TRAFFIC NEAR"} and "ROAD LIMIT" not in TL.FLAG_WORDS.values())
ok("the flag text names the limit, the figure and the unit",
   TL.flag_text(zl, "over", 21.5, "Mon 8 Nov") == "Main Street limit Mon 8 Nov: 22 lorry movements against a limit of 21",
   TL.flag_text(zl, "over", 21.5, "Mon 8 Nov"))

# =========================================================================== #
#  6. summary(): public, Sites                                                 #
# =========================================================================== #
zp = zones.create_zone("Private limit", AREA, kind="traffic_limit", limit_value=500, limit_public=False)
s = TL.summary([NOV27], ctx=ctx())
names = [x["name"] for x in s["limits"]]
ok("⭐ the staff summary has both limits", names == ["Main Street limit", "Private limit"], str(names))
sp = TL.summary([NOV27], public_only=True, ctx=ctx())
ok("🔴 Q6: the public summary leaves the unticked one out", [x["name"] for x in sp["limits"]] == ["Main Street limit"])
m = s["limits"][0]["months"][str(NOV27)]
ok("summary: months over listed, the figure and the split", s["limits"][0]["months_over"] == [NOV27]
   and m["value"] == 21.5 and m["in_per_day"] == 16.5 and m["out_per_day"] == 5.0, str(m))
ok("the unit in words",
   s["limits"][0]["unit_words"] == "lorry movements a day, in and out counted separately (daily average)")
sf = TL.summary([NOV27], route_filter={"R2"}, ctx=ctx())
ok("⭐ the Sites filter keeps R2's lorries only (10 movements), the limit unchanged",
   sf["limits"][0]["months"][str(NOV27)]["value"] == 10.0 and sf["limits"][0]["limit"]["value"] == 21.0)
ok("with_routes=False drops the route list",
   "routes" not in TL.summary([NOV27], with_routes=False, ctx=ctx())["limits"][0]["months"][str(NOV27)])
ok("summary's note: this scheme's lorries only (Q3)", "This scheme's lorries only" in s["note"])

# =========================================================================== #
#  6b. The Look-ahead's flags (clashes.traffic_limit)                          #
# =========================================================================== #
import clashes  # noqa: E402
import days as _days  # noqa: E402
_ctx0 = TL.context
TL.context = lambda: ctx()
try:
    WK = [d.isoformat() for d in _days.bucket_dates(NOV27, 2)]
    D1, D2 = WK[0], WK[1]

    def la_line(rid, trips):
        return {"route_id": rid, "month_index": NOV27, "discipline": "D", "section_id": "", "ipt": "IPT1",
                "days": [{"day_date": d, "derived": {"trips": t}} for d, t in trips.items()]}
    LL = [la_line("R1", {D1: 9, D2: 4}), la_line("R2", {D1: 6, D2: 2})]
    fl = clashes.traffic_limit(LL, NOV27, 2)
    over = [f for f in fl if f["code"] == "TRAFFIC_LIMIT"]
    ok("⭐ the average limit (21.5 vs 21 in Nov 2027) flags both lines on a route that passes, no day, TRAFFIC LIMIT",
       sorted(f["route_id"] for f in over) == ["R1", "R2"] and all("day_date" not in f and f["label"] == "TRAFFIC LIMIT"
                                                                   for f in over), str(fl))
    ok("...the sentence says a day on average", all("(a day on average)" in f["text"] and "Main Street limit" in f["text"] for f in over),
       str([f["text"] for f in over]))
    zones.update_zone(z["id"], limit_basis="busiest_day", limit_value=20)
    fb = clashes.traffic_limit(LL, NOV27, 2)
    ok("⭐ a busiest-day limit of 20: the first day (9 + 6 in, 6 out = 21) flags on that day only; the second (4+2+2) none",
       sorted((f["route_id"], f["day_date"]) for f in fb) == [("R1", D1), ("R2", D1)]
       and all(f["code"] == "TRAFFIC_LIMIT" for f in fb), str(fb))
    zones.update_zone(z["id"], limit_value=23)
    fn_ = clashes.traffic_limit(LL, NOV27, 2)
    ok("...a limit of 23: 21 is near (90 %), amber TRAFFIC NEAR", fn_ and all(f["code"] == "TRAFFIC_NEAR" and f["label"] == "TRAFFIC NEAR"
                                                                              for f in fn_), str(fn_))
    zones.update_zone(z["id"], starts_on="2030-01-01")
    ok("a limit not in force in the week raises nothing", clashes.traffic_limit(LL, NOV27, 2) == [])
    zones.update_zone(z["id"], starts_on=None, limit_basis="average", limit_value=21)
    ok("the codes sit after the pours on the rail", list(clashes.CODES[-2:]) == ["TRAFFIC_LIMIT", "TRAFFIC_NEAR"])
    ok("compute() calls it, guarded", "flags += traffic_limit(all_lines, month_index, week_index)" in read("backend/clashes.py"))
finally:
    TL.context = _ctx0

# =========================================================================== #
#  6c. The Simulation (card 7), the bulletin (Q10), the CLP (card 6)           #
# =========================================================================== #
import bulletin_doc  # noqa: E402
import clp_doc_layers  # noqa: E402
_ctx0 = TL.context
TL.context = lambda: ctx()
try:
    d8 = dt.date(2027, 11, 8)
    sd = TL.sim_day({"R1": 9, "R2": 6}, [d8])
    ok("⭐ the Simulation's day: 9 + 6 in, 6 out = 21 movements against 21 = near (90 % or more); the private area 21 against 500",
       [(r["name"], r["value"], r["state"]) for r in sd] == [("Main Street limit", 21.0, "near"), ("Private limit", 21.0, "ok")],
       str(sd))
    sd2 = TL.sim_day({"R1": 12, "R2": 6}, [d8])
    ok("...12 + 6 in, 6 out = 24: over, listed first (worst first)", sd2[0]["state"] == "over" and sd2[0]["value"] == 24.0
       and sd2[0]["in"] == 18.0 and sd2[0]["out"] == 6.0, str(sd2))
    ok("a limit not in force on the day is left out", all(r["name"] != "Main Street limit" for r in
                                                          (zones.update_zone(z["id"], starts_on="2030-01-01") and TL.sim_day({"R1": 9}, [d8]))))
    zones.update_zone(z["id"], starts_on=None)
    ok("source: sim.day sends traffic_limits from the day's whole loads per route, guarded",
       '"traffic_limits": traffic,' in read("backend/sim.py") and "traffic_limits.sim_day(by_route," in read("backend/sim.py"))

    T = bulletin_doc.traffic_month(NOV27)
    ok("⭐ the bulletin: only the public limit, its figure with the in / out split, Over in words",
       T and [r["name"] for r in T["rows"]] == ["Main Street limit"] and T["rows"][0]["figure"] == "22 (17 in, 5 out)"
       and T["rows"][0]["limit"] == "21 movements a day" and T["rows"][0]["state"] == "Over" and T["glance"] == "1 over, 0 near",
       str(T))
    ok("a month with no public limit in force: no table at all", bulletin_doc.traffic_month(NOV27 + 40) is None
       or all(r["state_key"] == "ok" for r in bulletin_doc.traffic_month(NOV27 + 40)["rows"]))
    zones.update_zone(z["id"], limit_basis="busiest_day", limit_value=40)
    Tb = bulletin_doc.traffic_month(NOV27)
    ok("a busiest-day limit the average is under reads 'Average only' (the bulletin has no day plan, Q4)",
       Tb["rows"][0]["state"] == "Average only" and Tb["rows"][0]["limit"] == "40 movements a day (busiest day)", str(Tb))
    zones.update_zone(z["id"], limit_basis="average", limit_value=21)
    many = [zones.create_zone(f"Limit {i}", ROAD, kind="traffic_limit", limit_value=100 + i) for i in range(7)]
    Tm = bulletin_doc.traffic_month(NOV27)
    ok("⭐ at most six rows, the over one first, the counts of every one", len(Tm["rows"]) == 6 and Tm["total"] == 8
       and Tm["rows"][0]["state"] == "Over" and Tm["glance"] == "1 over, 0 near", str(Tm["rows"][0]))
    h = bulletin_doc._traffic_html(Tm)
    ok("the web table: after the panel, the over word red, '2 more within their limits', the note",
       'data-bulletin="traffic-limits"' in h and '<td class="flag">Over</td>' in h and "2 more within their limits." in h
       and "a planning check, not a count on the road" in h)
    # 12 Nov 2026 (A-F8 (a), John's yes): the printed newsletter prints EVERY public limit once, in its works table
    ok("⭐ by_zone holds every public limit's row by its zone (eight), not only the six the web table shows",
       len(Tm["by_zone"]) == 8 and set(Tm["by_zone"]) == {m_["id"] for m_ in many} | {z["id"]}
       and all(r["zone_id"] == k for k, r in Tm["by_zone"].items()), str(sorted(Tm["by_zone"]))[:200])
    import export
    _ll = export._limit_line(lambda s: str(s), T["rows"][0])
    ok("⭐ the works row's limit line: this month's figure, the limit and the plan word in the web table's words; Over red",
       "This month, a day:" in _ll and T["rows"][0]["figure"] in _ll and "Limit:</font> 21 movements a day" in _ll
       and "Plan:" in _ll and "<font color='#B91C1C'><b>Over</b></font>" in _ll, _ll)
    ok("...a limit within reads Within, not coloured", "<b>" not in export._limit_line(
       lambda s: str(s), dict(T["rows"][0], state="Within", state_key="ok")))
    for m_ in many:
        zones.update_zone(m_["id"], active=False)
    gl = bulletin_doc._glance({}, {}, [], [], [], None, [], None, "Nov 2027", None, T)
    ok("the glance row: 'Traffic limits on local roads' with '1 over, 0 near', only when a limit is in force",
       any(g["item"] == "Traffic limits on local roads" and g["figure"] == "1 over, 0 near" for g in gl)
       and not any(g["item"] == "Traffic limits on local roads" for g in
                   bulletin_doc._glance({}, {}, [], [], [], None, [], None, "Nov 2027", None, None)))
    br = bulletin_doc._brief("Nov 2027", None, {}, None, [], [], [], False, None, None, T)
    ok("the key points (the leaflet's): the works line carries 'Traffic limits on local roads: 1 over, 0 near.', still five at most",
       br[-1].endswith("Traffic limits on local roads: 1 over, 0 near.") and len(br) <= 5, str(br))
    BD = read("backend/bulletin_doc.py")
    ok("source: the web page prints {traffic} after {lot}", "{lot}\n{traffic}\n" in BD)
    EX = read("backend/export.py")
    # REVERSED 12 Nov 2026 (A-F8 (a), John's yes): the table after the panel is gone from the newsletter; the works row
    # carries the figure, and the note goes under the works table
    ok("source: the newsletter prints no table after the panel; the works row carries the limit, the note under it",
       EX.count('story += _traffic_flow(K, S.get("traffic"))') == 0 and "_limit_line(E, lim) if lim" in EX
       and 'story.append(P(E(S["traffic"]["note"]), st_grey))' in EX)
    ok("the works word for a traffic limit is 'traffic limit' (it read 'local control')",
       bulletin_doc.ZONE_WORDS.get("traffic_limit") == "traffic limit")

    data = {"lines": [{"route_id": "R2", "month": NOV27, "trips": 100.0}, {"route_id": "R2", "month": DEC27, "trips": 60.0}]}
    tr = clp_doc_layers.traffic_rows(data, ["R2"])
    ok("⭐ the CLP (a plan with R2's lorries): the busiest month Nov 2027, this plan 10 movements, all lorries 21.5 — over",
       [(r["name"], r["month"], r["plan"], r["all"], r["state"]) for r in tr] == [("Main Street limit", NOV27, 10.0, 21.5, "over"),
                                                                              ("Private limit", NOV27, 10.0, 21.5, "ok")], str(tr))
    ok("...a plan whose routes pass no limit: no rows", clp_doc_layers.traffic_rows(data, ["R9"]) == [])
    CD = read("backend/clp_doc.py")
    ok("source: §2.3.1 prints the table in HGV words before the TRO line",
       CD.index("Traffic limits on roads this plan's lorries use") < CD.index('D.todo("Traffic Regulation Orders needed')
       and "HGV {'movements'" in CD)
finally:
    TL.context = _ctx0

# =========================================================================== #
#  7. Source pins                                                              #
# =========================================================================== #
M = read("backend/main.py")
ok("the staff read is planners / admins and kept until the next write",
   '@app.get("/api/traffic-limits")' in M and '_staff_json("traffic-limits"' in M)
ok("the public read is kept in memory, public limits only",
   '@app.get("/api/public/traffic-limits")' in M and "summary(public_only=True" in M)
ok("db: the four zone columns", all(c_ in read("backend/db.py") for c_ in ("limit_value", "limit_counts", "limit_basis", "limit_public")))

# seen in Chrome 9 Nov 2026: a figure that rounds to its limit keeps one decimal, so an Over row never reads "5 / 5"
import bulletin_doc as _BDt
ok("6d. bulletin: 5.33 against 5 reads 5.3; 4.6 against 5 reads 4.6; 22.4 against 21 reads 22; 5 against 5 reads 5",
   _BDt._tl_value(5.33, 5) == "5.3" and _BDt._tl_value(4.6, 5) == "4.6" and _BDt._tl_value(22.4, 21) == "22" and _BDt._tl_value(5, 5) == "5")

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
