"""
Disruption zones by date, PR B (29 Oct 2026, task 0c): the readers that follow the month — the shared-road index and
its month read (the busiest-roads heat map), the council clip and its month read, the bulletin / export / CLP plan
maps, the Look-ahead week map, the Simulation's legs, and the collision and community strips.

WHAT IS ASSERTED
----------------
  * route_choice's helpers (leg_key, in_use, in_use_keys, month_weights, majority_alt);
  * the index reads a diversion's line as "R1@1"; a route's own main line and diversion are ONE route (no shared
    road between them); road_load gives each key its share of the month's working days and lists routes, not keys;
  * the council clip holds the diversion; a month's loads and carbon split by the days, adding up to the route's;
  * the month maps, the week map and the Simulation draw / run the diversion in its period only;
  * a collision near a diversion in use is along a route; the community strip covers the diversion.

WHAT THIS DOES NOT PROVE
------------------------
HERE and Mapbox are never called; Postgres is not run; the heat map and the PDFs are not looked at here (the Chrome
check is). The month payload road_load reads is a stand-in (month_lines patched), not the bar's own read.

Run:  python3 backend/tests/test_zone_diversions_b.py
"""
import json
import math
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_route_sheet.py ---------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_zdb_")
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
import gates  # noqa: E402
import haul  # noqa: E402
import zones  # noqa: E402
import here_routing  # noqa: E402
import route_choice  # noqa: E402
import road_sections  # noqa: E402
import areas  # noqa: E402
import bulletin_doc  # noqa: E402
import lookahead  # noqa: E402
import sim  # noqa: E402
import collisions  # noqa: E402
import community  # noqa: E402

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
#  Fixture: R1 west->east along lat 52.5 through a box; its stored option 1    #
#  goes north along R3's road (lat 52.51). R3 runs that northern road only.    #
#  A dated zone (1-17 Dec 2027) on the box diverts R1 onto option 1.           #
# =========================================================================== #
ART = network.DEFAULT_PROFILE
LAT = 52.5
for lid, lon in (("L1", -1.0), ("L2", -0.9)):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, 'Quarry')", (lid, lid, LAT, lon))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R3', 'L1', 'L2', 'Small aggregate', 'IPT1')")


def pts(lats, lon0=-1.0, lon1=-0.9, n=11):
    return [[round(lon0 + (lon1 - lon0) * i / (n - 1), 6), lats(i)] for i in range(n)]


MAIN = pts(lambda i: LAT)
NORTH = [[-1.0, LAT]] + pts(lambda i: LAT + 0.01, -0.99, -0.91, 9) + [[-0.9, LAT]]
R3LINE = pts(lambda i: LAT + 0.01, -0.99, -0.91, 9)
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.002], [-0.948, LAT - 0.002], [-0.948, LAT + 0.002],
                                           [-0.952, LAT + 0.002], [-0.952, LAT - 0.002]]]}


def put(rid, leg, alt, line, km):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, ART, json.dumps(line), km, km / 40.0, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="")


for leg in ("loaded", "return"):
    put("R1", leg, 0, MAIN, 7.0)
    put("R1", leg, 1, NORTH, 8.0)
    put("R3", leg, 0, R3LINE, 6.0)
ZD = zones.create_zone("Christmas trading", BOX, kind="closure", affects_routing=True,
                       starts_on="2027-12-01", ends_on="2027-12-17")["id"]
route_choice.refresh_zones()
DEC27, NOV27 = 24, 23
ok("fixture: R1 is diverted onto option 1 in 1-17 Dec 2027 (PR A's rules)",
   route_choice.alt_on("R1", ART, "loaded", "2027-12-06") == 1 and route_choice.alt_on("R1", ART, "loaded", "2027-12-20") == 0)

# =========================================================================== #
#  1. The helpers                                                              #
# =========================================================================== #
ok("leg_key / base_of: the main line is the route's id, an option 'R1@1'",
   route_choice.leg_key("R1", 0) == "R1" and route_choice.leg_key("R1", 1) == "R1@1" and route_choice.base_of("R1@1") == "R1")
ok("⭐ in_use: R1's option 1 on both legs, for the profile", route_choice.in_use(ART).get(("R1", ART, "loaded")) == {1}
   and route_choice.in_use(ART).get(("R1", ART, "return")) == {1})
ok("in_use_keys: {'R1@1'}", route_choice.in_use_keys() == {"R1@1"})
w = route_choice.month_weights("R1", ART, DEC27)
ok("⭐ month_weights: Dec 2027 is 13 of 23 working days on option 1, the rest on the main line",
   abs(w["loaded"][1] - 13 / 23) < 1e-9 and abs(w["loaded"][0] - 10 / 23) < 1e-9 and abs(w["return"][1] - 13 / 23) < 1e-9, str(w))
ok("...and Nov 2027 the main line only", route_choice.month_weights("R1", ART, NOV27)["loaded"] == {0: 1.0})
ok("majority_alt: the week of 6 Dec is option 1; a week in Jan 2028 the main line",
   route_choice.majority_alt("R1", ART, "loaded", route_choice.week_days(DEC27, 2)) in (0, 1)
   and route_choice.majority_alt("R1", ART, "loaded", [__import__("datetime").date(2027, 12, d) for d in (6, 7, 8, 9, 10)]) == 1
   and route_choice.majority_alt("R1", ART, "loaded", [__import__("datetime").date(2028, 1, d) for d in (10, 11, 12)]) == 0)

# =========================================================================== #
#  2. Shared roads (the busiest-roads heat map)                                #
# =========================================================================== #
pl = road_sections.polylines_for("loaded", ART)
ok("⭐ the index reads R1's diversion line beside the main lines, as 'R1@1'", set(pl) == {"R1", "R1@1", "R3"}, str(sorted(pl)))
ok("...and not with diversions=False (the old read)", set(road_sections.polylines_for("loaded", ART, diversions=False)) == {"R1", "R3"})
road_sections.rebuild(ART)
runs = road_sections.stored_runs("loaded")
own = [r["routes"] for r in runs]
ok("⭐ the diversion and R3 share the northern road: one run owned by R1@1 and R3", ["R1@1", "R3"] in own, str(own))
ok("🔴 R1's main line and its own diversion are ONE route: the stretch only they share is no shared road",
   all(len({road_sections._base(k) for k in o}) >= 2 for o in own), str(own))
kw = road_sections.key_weights(["R1", "R1@1", "R3"], DEC27, "loaded", ART)
ok("key_weights: Dec 2027 R1 10/23, R1@1 13/23, R3 (no diversion) 1.0",
   abs(kw["R1"] - 10 / 23) < 1e-9 and abs(kw["R1@1"] - 13 / 23) < 1e-9 and kw["R3"] == 1.0, str(kw))
ok("...Nov 2027: R1@1 has no share", road_sections.key_weights(["R1@1"], NOV27, "loaded", ART)["R1@1"] == 0.0)
lens = road_sections.route_lengths(ART)
ok("route_lengths: the diversion's key has that option's own legs (both stored here)",
   "R1@1" in lens and abs(lens["R1@1"]["loaded"] - road_sections.length_km(NORTH)) < 1e-6
   and abs(lens["R1@1"]["return"] - road_sections.length_km(list(reversed(NORTH)))) < 1e-6)

_ml = road_sections.month_lines


def fake_month(month):
    return {"working_days": 20, "lines": [
        {"route_id": "R1", "vehicle_loads": 230.0, "trips_per_vehicle_day": 4, "co2_t": 10.0, "ipt": "IPT1"},
        {"route_id": "R3", "vehicle_loads": 100.0, "trips_per_vehicle_day": 4, "co2_t": 5.0, "ipt": "IPT1"}]}


road_sections.month_lines = fake_month
try:
    dec = road_sections.road_load(DEC27, drawn={"R1", "R3"}, profile=ART)
    nov = road_sections.road_load(NOV27, drawn={"R1", "R3"}, profile=ART)
finally:
    road_sections.month_lines = _ml
run_d = next((r for r in dec["runs"] if r["routes"] == ["R1", "R3"]), None)
ok("⭐ Dec 2027: the northern run carries R3's whole month and R1's 13/23 of it (230 x 13/23 = 130 loads)",
   run_d is not None and abs(run_d["loads"] - (100 + 130)) < 1e-6 and run_d["diverted"] == ["R1"],
   str([(r["routes"], r["loads"]) for r in dec["runs"]]))
ok("...R1's entry says its share: 130 loads, 6.5 movements a day",
   run_d and next(x for x in run_d["route_shares"] if x["route_id"] == "R1")["loads"] == 130.0
   and next(x for x in run_d["route_shares"] if x["route_id"] == "R1")["movements_per_day"] == 6.5)
ok("⭐ Nov 2027: no diversion, so the northern road carries R3 only", all("R1" not in r["routes"] for r in nov["runs"]),
   str([(r["routes"], r["loads"]) for r in nov["runs"]]))
ok("🔴 no run lists an index key: the feed names routes", all("@" not in k for r in dec["runs"] for k in r["routes"]))
co2_r1 = next(x for x in run_d["route_shares"] if x["route_id"] == "R1")["co2_t"]
ok("the carbon on the run is R1's month carbon x its share x the run's length / the diversion's two-way length",
   abs(co2_r1 - round(10.0 * 13 / 23 * run_d["length_km"] / lens["R1@1"]["two_way"], 3)) < 1e-3, str(co2_r1))

# =========================================================================== #
#  3. Councils                                                                 #
# =========================================================================== #
NORTH_AREA = {"type": "Polygon", "coordinates": [[[-1.01, LAT + 0.003], [-0.89, LAT + 0.003], [-0.89, LAT + 0.02],
                                                  [-1.01, LAT + 0.02], [-1.01, LAT + 0.003]]]}
SOUTH_AREA = {"type": "Polygon", "coordinates": [[[-1.01, LAT - 0.01], [-0.89, LAT - 0.01], [-0.89, LAT + 0.003],
                                                  [-1.01, LAT + 0.003], [-1.01, LAT - 0.01]]]}
areas.import_collection({"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"LAD24CD": "E01", "LAD24NM": "North Council"}, "geometry": NORTH_AREA},
    {"type": "Feature", "properties": {"LAD24CD": "E02", "LAD24NM": "South Council"}, "geometry": SOUTH_AREA}],
    "attribution": ["Test boundaries (fictional)."]}, replace=True)
areas.rebuild()
clips = areas.clip_table()
ok("⭐ the council clip holds R1's diversion as 'R1@1' (its km in the northern council)",
   "R1@1" in clips and any(v > 0 for k, v in clips["R1@1"][ART]["loaded"].items() if k != areas.WHOLE_LEG), str(sorted(clips)))
ok("...the main line is clipped as before", "R1" in clips and areas.WHOLE_LEG in clips["R1"][ART]["loaded"])
ids = {a["name"]: a["area_id"] for a in areas.stored_areas()}
ctx = areas._month_context(drawn={"R1": ART, "R3": ART})
ok("the month context knows which routes a diversion touches", ctx["diverted"] == {"R1"})
lines = [{"route_id": "R1", "vehicle_loads": 230.0, "co2_t": 10.0}]
dmon = areas._area_month(DEC27, lines, None, 20.0, ctx, geometry=False)
nmon = areas._area_month(NOV27, lines, None, 20.0, ctx, geometry=False)
A = lambda m, n: next(a for a in m["areas"] if a["area_id"] == ids[n])
# the diversion leaves and rejoins the main road inside the southern council, so it enters BOTH: a route counts in
# every district its laden leg enters (areas' rule), whichever of its lines it is on that day
ok("⭐ Dec 2027: the northern council has R1's 13/23 of the month (130 loads); the southern all 230 (both lines enter it)",
   abs(A(dmon, "North Council")["loads"] - 130.0) < 1e-6 and abs(A(dmon, "South Council")["loads"] - 230.0) < 1e-6,
   str((A(dmon, "North Council")["loads"], A(dmon, "South Council")["loads"])))
ok("...Nov 2027: the whole month in the southern council, none in the northern",
   A(nmon, "North Council")["loads"] == 0 and abs(A(nmon, "South Council")["loads"] - 230.0) < 1e-6)
ok("🔴 over the councils the month's carbon still adds up to R1's figure (10 t), split by the days",
   abs(sum(a["co2_t"] or 0 for a in dmon["areas"]) - 10.0) < 0.05, str([a["co2_t"] for a in dmon["areas"]]))

# =========================================================================== #
#  4. The month's maps (bulletin, export, CLP plans) and the week's map        #
# =========================================================================== #
g_dec = bulletin_doc._geometries(["R1", "R3"], month_index=DEC27)
g_nov = bulletin_doc._geometries(["R1", "R3"], month_index=NOV27)
g_none = bulletin_doc._geometries(["R1", "R3"])
ok("⭐ the bulletin / export / CLP plan line for Dec 2027 is R1's diversion; Nov 2027 and no month the main line",
   [list(p) for p in g_dec["R1"][0]] == NORTH and [list(p) for p in g_nov["R1"][0]] == MAIN and [list(p) for p in g_none["R1"][0]] == MAIN)
ok("source: the bulletin and the export pass their month", "_geometries([r[\"route_id\"] for r in rows], month_index=mi)" in read("backend/bulletin_doc.py")
   and "bulletin_doc._geometries(ids, month_index=mi)" in read("backend/route_map_export.py"))
import datetime as _dt  # noqa: E402
wk = [_dt.date(2027, 12, 6) + _dt.timedelta(days=i) for i in range(7)]
wg = {g["route_id"]: g for g in lookahead.week_geometry(["R1", "R3"], days=wk)}
wg0 = {g["route_id"]: g for g in lookahead.week_geometry(["R1", "R3"])}
ok("⭐ the Look-ahead week map: the week of 6 Dec 2027 draws R1's diversion and its distance; no week, the main line",
   wg["R1"]["geometry"] == NORTH and wg["R1"]["distance_km"] == 8.0 and wg0["R1"]["geometry"] == MAIN, str(wg["R1"]["distance_km"]))
ok("source: the week map's read and the PDF pass the week", "lookahead.week_geometry(id_list, veh, days=wk)" in read("backend/main.py")
   and "days=_page_week_days(page)" in read("backend/export.py") and "&bucket=${bucket === \"next\" ? \"next\" : \"commit\"}" in read("frontend/index.html"))

# =========================================================================== #
#  5. The Simulation                                                           #
# =========================================================================== #
per, _z = sim._legs_for(["R1"], True, days=route_choice.month_days(DEC27))
per0, _z = sim._legs_for(["R1"], True, days=route_choice.month_days(NOV27))
per_none, _z = sim._legs_for(["R1"], True)
ok("⭐ the Simulation's Dec 2027 day runs R1 on its diversion (13 of 23 days); Nov 2027 and no period the main line",
   int(per["R1"][ART]["loaded"]["alt_index"]) == 1 and int(per0["R1"][ART]["loaded"]["alt_index"]) == 0
   and int(per_none["R1"][ART]["loaded"]["alt_index"]) == 0)
ok("source: the day passes its period (month / week / the date)", "_legs_for(sorted({l[\"route_id\"] for l in lines}), with_lines, days=span_days)" in read("backend/sim.py"))

# =========================================================================== #
#  6. The collision and community strips                                       #
# =========================================================================== #
ok("⭐ a collision near R1's diversion only is ALONG a route (lorries drive it in those months)",
   collisions.along({"routes": {"R1@1": 10}}) == "route")
ok("...near an option no diversion uses it is still an alternative", collisions.along({"routes": {"R3@2": 10}}) == "alternative")
ok("...and near a main line, a route, as before", collisions.along({"routes": {"R3": 10}}) == "route")
ok("along takes the set once for a whole read", collisions.along({"routes": {"R1@1": 1}}, in_use=set()) == "alternative")
lines_s = community.strip_from_db().lines
ok("⭐ the community strip covers R1's diversion line (a fetch then finds the schools along it)",
   any(abs(c[1] - (LAT + 0.01)) < 1e-6 for ln in lines_s for c in ln) and len(lines_s) >= 3, str(len(lines_s)))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
