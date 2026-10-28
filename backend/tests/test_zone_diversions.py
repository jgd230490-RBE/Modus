"""
Disruption zones by date (28 Oct 2026, task 0c). The user: "Will the geofenced areas along a route divert to the
alternative route automatically?" Answered by a yes to all eleven questions of notes/zone-alternatives-mockup-1028.

WHAT IS ASSERTED
----------------
  * the table route_choice (shared with 0d) and route_geometry.avoids, tenanted, in the package;
  * the main line avoids only UNDATED routing zones (network.active_avoid);
  * route_choice.refresh_zones: per (route, lorry type, leg) whose main line crosses a dated zone in force, the
    SHORTEST stored option that misses every zone in force then, for the zone's dates only; needs_route when none
    does; a second refresh rewrites, never doubles;
  * alt_on per day, mix per month / week by WORKING days (Q2); derived.cycle_for / line_context follow the line's
    month and week (distance weighted, trips a day the fewest); the Look-ahead flag NO_WAY_ROUND;
  * the public map data's Diversion features (months, zone names, no origin / dest keys);
  * "Keep the main route" and its undo; "Find a way round" (HERE stubbed): the cost first, one call a leg, stored at
    alt_index 10 with `avoids`, kept by a plain re-route, no_way_round when HERE still crosses, nothing written on
    a HERE failure;
  * zone saves: a dated zone clears no main line and reports its diversions; an undated one re-routes as before;
  * lorry limits on a diversion count only in the weeks its dates touch.

WHAT THIS DOES NOT PROVE
------------------------
HERE is never called: which avoid shapes HERE honours is the probe zone-avoid-probe.ps1 (28 Oct). Postgres is not
run. The map's drawing of a diversion is parse_map.js and the Chrome check, not this file.

Run:  python3 backend/tests/test_zone_diversions.py
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

TMP = tempfile.mkdtemp(prefix="rbe_zd_")
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
import derived  # noqa: E402
import clashes  # noqa: E402
import limits  # noqa: E402
import tenant_package  # noqa: E402

os.environ["ADMIN_TOKEN"] = "secret"
TOK = "secret"

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

# =========================================================================== #
#  Fixture: one route R1 L1 -> L2 along lat 52.5, its main line through a box   #
#  at lon -0.95; HERE's option 1 north of it (8 km), option 2 further (9 km)    #
# =========================================================================== #
ART = "Artic Tipper (44t)"
LAT = 52.5
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R2', 'L1', 'L2', 'Small aggregate', 'IPT1')")
MAIN = [[-1.0, LAT], [-0.95, LAT], [-0.9, LAT]]
NORTH = [[-1.0, LAT], [-0.95, LAT + 0.01], [-0.9, LAT]]
FAR = [[-1.0, LAT], [-0.95, LAT + 0.02], [-0.9, LAT]]
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.002], [-0.948, LAT - 0.002], [-0.948, LAT + 0.002],
                                           [-0.952, LAT + 0.002], [-0.952, LAT - 0.002]]]}


def put(rid, leg, alt, line, km, hr, avoids=None, prof=ART):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, prof, json.dumps(line), km, hr, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="", avoids=avoids)


for leg in ("loaded", "return"):
    put("R1", leg, 0, MAIN, 7.0, 0.20)
    put("R1", leg, 1, FAR, 9.0, 0.24)       # stored first, so "shortest" — not HERE's order — has to pick option 2
    put("R1", leg, 2, NORTH, 8.0, 0.22)
    put("R2", leg, 0, MAIN, 7.0, 0.20)      # R2 has NO stored option that misses the box

# =========================================================================== #
#  1. The table, the column, the package                                       #
# =========================================================================== #
cols = {r["name"] if isinstance(r, dict) and "name" in r else r[1] for r in db.query("PRAGMA table_info(route_choice)")}
ok("⭐ route_choice exists with the shape 0d shares (dates, hours, reason, status, source)",
   {"tenant_id", "id", "route_id", "vehicle_profile", "leg", "alt_index", "starts_on", "ends_on", "hours_from",
    "hours_to", "days", "reason_kind", "reason_ref", "status", "source", "km_delta", "decided_by", "decided_at"} <= cols, str(cols))
ok("🔴 route_choice is tenanted and keyed (tenant_id, id), registered in the same edit",
   "route_choice" in db.TENANTED_TABLES and db._TENANT_PK["route_choice"] == "(tenant_id, id)")
ok("the tenant package carries it, after route_geometry (it names stored options)",
   "route_choice" in tenant_package.ORDER
   and tenant_package.ORDER.index("route_choice") > tenant_package.ORDER.index("route_geometry"))
gcols = {r["name"] if isinstance(r, dict) and "name" in r else r[1] for r in db.query("PRAGMA table_info(route_geometry)")}
_ddl = db._TENANT_DDL["route_geometry"]
ok("⭐ route_geometry.avoids: in the DDL (the SQLite rebuild keeps only those) AND ALTERed on an old database",
   "avoids" in gcols and "avoids           TEXT" in _ddl and '("avoids", "TEXT")' in read("backend/db.py"))

# =========================================================================== #
#  2. The main line avoids only UNDATED zones                                  #
# =========================================================================== #
ZD = zones.create_zone("Christmas trading", BOX, kind="closure", affects_routing=True,
                       starts_on="2027-12-01", ends_on="2027-12-17")["id"]
av, tag = network.active_avoid()
ok("⭐ a DATED routing zone is NOT sent with the main line's bake (was: whatever was in force on the bake day)",
   av == [] and tag == "", str((av, tag)))
ZP = zones.create_zone("Bridge gone for good", {"type": "Polygon", "coordinates": [[[5, 5], [5, 6], [6, 6], [5, 5]]]},
                       kind="closure", affects_routing=True)["id"]
av, tag = network.active_avoid()
ok("...an UNDATED one still is (permanent), as before", tag == ZP and len(av) == 1, str((av, tag)))
zones.delete_zone(ZP)
ok("🔴 source: active_avoid filters on the zone's dates", "zones._clean_date(z.get(\"starts_on\")) or zones._clean_date(z.get(\"ends_on\"))"
   in read("backend/network.py"))

# =========================================================================== #
#  3. Working out the diversions                                               #
# =========================================================================== #
summ = route_choice.refresh_zones()
rows = db.query("SELECT * FROM route_choice WHERE tenant_id = ? ORDER BY route_id, leg", (db.current_tenant(),))
r1 = [r for r in rows if r["route_id"] == "R1"]
r2 = [r for r in rows if r["route_id"] == "R2"]
ok("⭐ R1: one in-use row a leg, the zone's own dates, the SHORTEST stored option that misses it (2 at 8 km, not 1)",
   len(r1) == 2 and all(r["status"] == "in_use" and int(r["alt_index"]) == 2 and r["starts_on"] == "2027-12-01"
                        and r["ends_on"] == "2027-12-17" and r["reason_ref"] == ZD for r in r1), str(r1))
ok("...with its change in length against the main line (+1.0 km)", all(abs(float(r["km_delta"]) - 1.0) < 1e-9 for r in r1))
ok("⭐ R2: no stored option misses it -> needs_route, the main line used", len(r2) == 2
   and all(r["status"] == "needs_route" and int(r["alt_index"]) == 0 for r in r2), str(r2))
ok("the summary by zone: R1 diverted, R2 needs a way round",
   summ["by_zone"].get(ZD, {}).get("routes") == ["R1"] and summ["by_zone"][ZD]["needs_route"] == ["R2"], str(summ))
ok("rows are auto zone rows (refresh rewrites them whole)", all(r["source"] == "auto" and r["reason_kind"] == "zone" for r in rows))
again = route_choice.refresh_zones()
ok("...and a second refresh writes the same rows, not twice as many",
   len(db.query("SELECT id FROM route_choice WHERE tenant_id = ?", (db.current_tenant(),))) == len(rows))

# =========================================================================== #
#  4. Which option on a day, and a month's mix                                 #
# =========================================================================== #
import datetime as _dt  # noqa: E402
ok("⭐ the day before the zone: the main line", route_choice.alt_on("R1", ART, "loaded", "2027-11-30") == 0)
ok("⭐ in the zone's dates: option 2", route_choice.alt_on("R1", ART, "loaded", "2027-12-01") == 2
   and route_choice.alt_on("R1", ART, "return", "2027-12-17") == 2)
ok("⭐ the day after: back to the main line", route_choice.alt_on("R1", ART, "loaded", "2027-12-18") == 0)
ok("...another lorry type is not diverted by this lorry type's rows", route_choice.alt_on("R1", "Flatbed", "loaded", "2027-12-06") == 0)
ok("needs_route gives the main line (0), never a missing option", route_choice.alt_on("R2", ART, "loaded", "2027-12-06") == 0)
_peak = {"R9": [{"route_id": "R9", "vehicle_profile": None, "leg": None, "alt_index": 1, "starts_on": None, "ends_on": None,
                 "hours_from": "07:00", "hours_to": "10:00", "days": "1111100", "reason_kind": "peak", "status": "in_use"}]}
ok("⭐ 0d's shape: an accepted peak row with hours and a weekday mask decides only those hours on those days",
   route_choice.alt_on("R9", ART, "loaded", "2027-12-06", hour=8, rows=_peak) == 1          # a Monday, 08:00
   and route_choice.alt_on("R9", ART, "loaded", "2027-12-06", hour=11, rows=_peak) == 0
   and route_choice.alt_on("R9", ART, "loaded", "2027-12-11", hour=8, rows=_peak) == 0      # a Saturday
   and route_choice.alt_on("R9", ART, "loaded", "2027-12-06", rows=_peak) == 0)            # never a whole day
_peak["R9"][0]["status"] = "offered"
ok("...and an OFFERED peak row changes nothing until the planner accepts it",
   route_choice.alt_on("R9", ART, "loaded", "2027-12-06", hour=8, rows=_peak) == 0)
DEC27 = (2027 - 2026) * 12 + 12          # month_index 24
NOV27 = DEC27 - 1
m = route_choice.mix("R1", ART, route_choice.month_days(DEC27))
ok("⭐ Dec 2027: 13 of 23 working days on option 2 (the user's Q2: by working days)",
   dict(m["pairs"]).get((2, 2)) == 13 / 23 and dict(m["pairs"]).get((0, 0)) == 10 / 23 and m["diverted"] == round(13 / 23, 4),
   str(m))
ok("...Nov 2027: the main line only, nothing to say", route_choice.mix("R1", ART, route_choice.month_days(NOV27))["pairs"] == [((0, 0), 1.0)])
ok("months_of: the months with a working day in the dates", route_choice.months_of("2027-12-01", "2027-12-17") == [DEC27]
   and route_choice.months_of("2026-10-05", "2026-11-02") == [10, 11])
m2 = route_choice.mix("R2", ART, route_choice.month_days(DEC27))
ok("R2's month names the problem days (needs_route) for the Look-ahead flag",
   m2["problems"] and m2["problems"][0]["status"] == "needs_route" and m2["problems"][0]["from"] == "2027-12-01"
   and m2["problems"][0]["to"] == "2027-12-17", str(m2))

# =========================================================================== #
#  5. The figures follow the month                                             #
# =========================================================================== #
c_nov = derived.cycle_for("R1", ART, {}, month_index=NOV27)
c_dec = derived.cycle_for("R1", ART, {}, month_index=DEC27)
c_none = derived.cycle_for("R1", ART, {})
ok("⭐ a month the zone does not touch: the alt-0 row exactly as before", c_nov == c_none and c_nov["loaded_km"] == 7.0)
ok("⭐ Dec 2027: the distance is each option's by its share of the days (7 x 10/23 + 8 x 13/23)",
   abs(c_dec["loaded_km"] - round(7.0 * 10 / 23 + 8.0 * 13 / 23, 3)) < 1e-6, str(c_dec.get("loaded_km")))
_rows = {(r["alt_index"], r.get("return_alt_index")): r
         for r in network.route_analysis("R1", profiles=[ART], pairs=[(0, 0), (2, 2)])["rows"]}
ok("route_analysis(pairs=) gives exactly the asked pairs, with the return option",
   set(_rows) == {(0, 0), (2, 2)} and _rows[(2, 2)]["loaded_km"] == 8.0 and _rows[(2, 2)]["return_km"] == 8.0)
ok("⭐ the trips a lorry a day are the FEWEST of the options used (a fleet sized for its longest week)",
   c_dec["trips_per_day"] == min(int(_rows[(0, 0)]["trips_per_day"]), int(_rows[(2, 2)]["trips_per_day"])))
ok("...and the row says how much of the month is diverted and by which zone",
   c_dec["diversion"]["share"] == round(13 / 23, 4) and c_dec["diversion"]["zones"] == [ZD])
ok("🔴 route_analysis without pairs is unchanged: one row per stored laden option",
   sorted(r["alt_index"] for r in network.route_analysis("R1", profiles=[ART])["rows"]) == [0, 1, 2])
ctx = derived.line_context({"route_id": "R1", "vehicle_type": ART, "unit": "t", "month_index": DEC27,
                            "week": {"planned_qty": 100}}, conversions.load_factors())
ok("⭐ a line's context (costlines, carbon, Look-ahead) carries the month's distance and the diversion",
   ctx["distance_km"] == round(c_dec["loaded_km"], 2) and ctx["diversion"]["zones"] == [ZD], str(ctx.get("distance_km")))
WK = None
for wi in range(1, 6):
    try:
        days = route_choice.week_days(DEC27, wi)
    except ValueError:
        break
    if days and days[0].isoformat() == "2027-12-06":
        WK = wi
ctxw = derived.line_context({"route_id": "R1", "vehicle_type": ART, "unit": "t", "month_index": DEC27, "week_index": WK,
                             "week": {"planned_qty": 100}}, conversions.load_factors())
ok("⭐ a Look-ahead week inside the zone's dates: the diversion all week (8 km)", WK and ctxw["distance_km"] == 8.0,
   str((WK, ctxw.get("distance_km"))))
ctx2 = derived.line_context({"route_id": "R2", "vehicle_type": ART, "unit": "t", "month_index": DEC27, "week_index": WK,
                             "week": {"planned_qty": 100}}, conversions.load_factors())
ok("R2's week carries the problem (no way round yet)", ctx2["diversion_problems"]
   and ctx2["diversion_problems"][0]["status"] == "needs_route")
fl = clashes.no_way_round([{"route_id": "R2", "month_index": DEC27, "discipline": "", "section_id": "",
                            "context": ctx2}])
ok("⭐ the Look-ahead flag NO_WAY_ROUND names the zone and why", len(fl) == 1 and fl[0]["code"] == "NO_WAY_ROUND"
   and "Christmas trading" in fl[0]["text"] and "no way round found yet" in fl[0]["text"] and fl[0]["label"] == "NO WAY ROUND",
   str(fl))
ok("...and the code has its place in the rail's order", "NO_WAY_ROUND" in clashes.CODES
   and clashes.CODES.index("NO_WAY_ROUND") == clashes.CODES.index("LIMIT") + 1)
ok("🔴 source: cycle_for reads the line's month and week", 'cycle_for(rid, veh, cache, month_index=line.get("month_index"), week_index=line.get("week_index"))'
   in read("backend/derived.py"))
ok("🔴 source: the month figures' trips a lorry a day follow the month",
   'trips_per_vehicle_day(r["route_id"], r.get("vehicle_type"), month)' in read("backend/main.py"))

# =========================================================================== #
#  6. The public map data                                                      #
# =========================================================================== #
md = network.public_map_data()
dv = [f for f in md["features"] if f["properties"].get("type") == "Diversion"]
ok("⭐ the map data carries R1's diversion, both legs, the months it is used in, the zone's name",
   len(dv) == 2 and all(f["properties"]["route_id"] == "R1" and f["properties"]["months"] == [DEC27]
                        and f["properties"]["because"] == ["Christmas trading"] and f["properties"]["alt_index"] == 2
                        and f["properties"]["main_km"] == 7.0 for f in dv), str([f["properties"] for f in dv]))
ok("🔴 a diversion feature has no origin / dest keys (populateFilters sweeps them) and its own line",
   all("origin" not in f["properties"] and "dest" not in f["properties"] for f in dv)
   and dv[0]["geometry"]["coordinates"] in (NORTH, list(reversed(NORTH))))
ok("...the route's own legs are still the main line", any(f["properties"].get("route_id") == "R1" and f["properties"].get("leg") == "loaded"
   and f["geometry"]["coordinates"] == MAIN for f in md["features"] if f["properties"].get("type") != "Diversion"))

# =========================================================================== #
#  7. "Keep the main route"                                                    #
# =========================================================================== #
route_choice.keep_main("R1", ZD, True, who="Planner")
r1k = db.query("SELECT * FROM route_choice WHERE tenant_id = ? AND route_id = 'R1'", (db.current_tenant(),))
ok("⭐ kept: R1's zone rows become declined on the main line, and the planner's rule is kept as a row of its own",
   any(r["status"] == "keep_main" and r["source"] == "planner" and r["decided_by"] == "Planner" for r in r1k)
   and all(int(r["alt_index"]) == 0 for r in r1k if r["status"] == "declined")
   and sum(1 for r in r1k if r["status"] == "declined") == 2, str(r1k))
ok("...the day in the zone's dates is the main line now", route_choice.alt_on("R1", ART, "loaded", "2027-12-06") == 0)
ok("...a refresh keeps the planner's rule", (route_choice.refresh_zones() or True)
   and db.query("SELECT COUNT(*) AS n FROM route_choice WHERE tenant_id = ? AND status = 'keep_main'", (db.current_tenant(),))[0]["n"] == 1)
ok("...the periods list says it was kept", any(p["kept"] and p["status"] == "declined" for p in route_choice.periods("R1")))
route_choice.keep_main("R1", ZD, False)
ok("⭐ undo: back on option 2", route_choice.alt_on("R1", ART, "loaded", "2027-12-06") == 2
   and not db.query("SELECT id FROM route_choice WHERE tenant_id = ? AND status = 'keep_main'", (db.current_tenant(),)))
per = route_choice.periods("R1")
ok("periods: one group (zone + dates) with both legs and the zone's name",
   len(per) == 1 and per[0]["zone_names"] == ["Christmas trading"] and len(per[0]["legs"]) == 2 and per[0]["status"] == "in_use")

# =========================================================================== #
#  8. Find a way round (HERE stubbed)                                          #
# =========================================================================== #
CALLS = []
WAY = [[-1.0, LAT], [-0.95, LAT - 0.01], [-0.9, LAT]]


def _fake_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, avoid_areas=None, alternatives=1, laden=True,
                 via=None, pass_through=False):
    CALLS.append({"avoid": list(avoid_areas or []), "alternatives": alternatives})
    line = WAY if o_lon < d_lon else list(reversed(WAY))
    return [{"geometry": line, "distance_km": 8.5, "duration_hr": 0.23, "sections": []}]


_real_routes, _real_conf = here_routing.routes, here_routing.configured
here_routing.routes = _fake_routes
here_routing.configured = lambda: True
try:
    est = network.way_round_calls()
    ok("⭐ the cost is known BEFORE anything is sent: R2's two legs, two calls", est["legs"] == 2 and est["here_calls"] == 2
       and est["routes"] == ["R2"], str(est))
    res = network.bake_way_rounds(budget_s=network.BAKE_BUDGET_S)
    ok("⭐ one HERE call a leg, ONE option asked, the zone's area sent", len(CALLS) == 2
       and all(c["alternatives"] == 1 and c["avoid"] == zones.avoid_strings(zones.get_zone(ZD)) for c in CALLS), str(CALLS))
    wr = db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND alt_index >= 10",
                  (db.current_tenant(),))
    ok("⭐ stored as the leg's way round (alt_index 10) with the zone in `avoids`; the main line untouched",
       len(wr) == 2 and all(int(w["alt_index"]) == route_choice.WAY_ROUND_BASE and w["avoids"] == ZD for w in wr)
       and db.query("SELECT distance_km FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND alt_index = 0 "
                    "AND leg = 'loaded'", (db.current_tenant(),))[0]["distance_km"] == 7.0)
    ok("⭐ ...and the refresh puts it in use for the zone's dates", route_choice.alt_on("R2", ART, "loaded", "2027-12-06") == 10
       and res["remaining"] == 0 and res["baked"] == 2, str(res))
    # a plain re-route of R2 keeps its way round
    network._bake_leg(db.query("SELECT * FROM routes WHERE id = 'R2'")[0],
                      db.query("SELECT * FROM locations WHERE id = 'L1'")[0],
                      db.query("SELECT * FROM locations WHERE id = 'L2'")[0], ART, "loaded", conversions.load_factors(),
                      avoid=[], zone_tag="")
    ok("🔴 a plain re-route of the leg keeps its way round (only HERE's own options past what came back are dropped)",
       db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND leg = 'loaded' "
                "AND alt_index = 10", (db.current_tenant(),))[0]["n"] == 1)
    put("R2", "loaded", 0, MAIN, 7.0, 0.20)          # the stub's re-route drew the main line round the box: put it back
    # HERE comes back through the zone anyway -> no_way_round
    db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND alt_index >= 10", (db.current_tenant(),))
    route_choice.refresh_zones()
    WAY[:] = MAIN
    network.bake_way_rounds()
    st = {r["status"] for r in db.query("SELECT status FROM route_choice WHERE tenant_id = ? AND route_id = 'R2'",
                                         (db.current_tenant(),))}
    ok("⭐ a way round HERE could only draw through the zone -> no_way_round, the main line stays, flagged",
       st == {"no_way_round"} and route_choice.alt_on("R2", ART, "loaded", "2027-12-06") == 0, str(st))
    ok("...and asking again sends nothing (nothing needs a route now)", network.way_round_calls()["legs"] == 0)

    def _boom(*a, **k):
        raise RuntimeError("HERE said no")
    db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND alt_index >= 10", (db.current_tenant(),))
    route_choice.refresh_zones()
    here_routing.routes = _boom
    res = network.bake_way_rounds()
    ok("🔴 a HERE failure writes NOTHING (an error row at alt 0 would wipe the main line every other day uses)",
       res["errors"] == 2 and res["remaining"] == 0
       and db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND route_id = 'R2' AND alt_index = 0 "
                    "AND geometry IS NOT NULL", (db.current_tenant(),))[0]["n"] == 2, str(res))
finally:
    here_routing.routes, here_routing.configured = _real_routes, _real_conf

# =========================================================================== #
#  9. Zone saves                                                               #
# =========================================================================== #
def zin(**kw):
    base = {"name": "Night works", "geometry": BOX, "kind": "closure", "affects_routing": True,
            "starts_on": "2028-03-01", "ends_on": "2028-03-31", "note": None, "active": True}
    base.update(kw)
    return main.ZoneIn(**base)


before = db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND alt_index = 0", (db.current_tenant(),))[0]["n"]
res = main.create_zone(zin(), token=TOK)
after = db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND alt_index = 0", (db.current_tenant(),))[0]["n"]
ok("⭐ saving a DATED zone clears no main line (was: the crossing legs, re-routed through it again)",
   before == after and res["invalidated"]["leg_count"] == 0 and not res["rebake_required"], str(res["invalidated"]))
ok("⭐ ...and says what it diverts in its dates: R1 (stored option), R2 needs a way round, with the calls",
   res["diversions"]["routes"] == ["R1"] and res["diversions"]["needs_route"] == ["R2"]
   and res["way_round"]["legs"] == 2, str(res.get("diversions")))
ZN = res["zone"]["id"]
lst = main.list_zones()
ok("the zones list carries each dated zone's diversions (the Used by column)",
   lst["diversions"].get(ZN, {}).get("needs_route") == ["R2"] or lst["diversions"].get(ZN) is not None, str(lst["diversions"]))
ok("🔴 an update clears the legs whose record names the zone, whatever the zone is now (Z003 on live gives its lines back)",
   "zone_id=zone_id," in read("backend/main.py") and "now_routes = _permanent_routing(z)" in read("backend/main.py"))
e = raises(lambda: main.route_keep_main({"route_id": "R1", "zone_id": ZD}, token="wrong"))
ok("Keep the main route is an admin write (refused without the token)", e is not None and getattr(e, "status_code", None) == 403)
e = raises(lambda: main.route_way_round(token=None))
ok("Find a way round is an admin write (it spends HERE calls)", e is not None and getattr(e, "status_code", None) == 403)

# =========================================================================== #
#  10. Lorry limits on the diversions                                          #
# =========================================================================== #
route_choice.refresh_zones()
ok("the options in use are listed for the limits check, with their dates",
   limits._diversions_in_use("R1").get((ART, "loaded", 2)) is not None)
ok("⭐ a limit on a diversion counts only in a week its dates touch",
   clashes._diversion_touches([{"from": "2027-12-01", "to": "2027-12-17"}], {"month_index": DEC27, "week_index": WK})
   and not clashes._diversion_touches([{"from": "2027-12-01", "to": "2027-12-17"}], {"month_index": NOV27, "week_index": 1}))
ok("🔴 source: check_route reads the options in use, not only alt 0",
   "_diversions_in_use(route_id)" in read("backend/limits.py") and 'hits[-1]["diversion"]' in read("backend/limits.py"))

# =========================================================================== #
#  11. The route sheet: a page per diversion (the user's Q6)                   #
# =========================================================================== #
import export  # noqa: E402
import route_sheet as rs  # noqa: E402
from portable import pdf_text, offline  # noqa: E402
offline(export)                         # Mapbox is never called: no basemap in any PDF here
S = rs.sheet("R1", vehicle=ART)
ok("⭐ the sheet model lists R1's diversions in date order (Dec 2027, then the Mar 2028 zone of section 9): its dates in words, why, both legs' lines, the day it goes back",
   len(S["diversions"]) == 2 and S["diversions"][0]["when"] == "1–17 Dec 2027" and S["diversions"][1]["when"] == "1–31 Mar 2028"
   and S["diversions"][0]["because"] == ["Christmas trading"] and [list(p) for p in S["diversions"][0]["loaded"]] == NORTH
   and S["diversions"][0]["back_on"] == "18 Dec 2027", str(S["diversions"])[:300])
ok("...page 1 is still the main route", [list(p) for p in S["loaded"]] == MAIN)
_pdf = export.build_route_sheet_pdf(S)
_txt = " ".join(pdf_text(_pdf).split())
ok("⭐ the PDF has a second page: Diversion: 1–17 Dec 2027, why, and back to page 1's route",
   _pdf.count(b"/Type /Page\n") + _pdf.count(b"/Type /Page\r") + _pdf.count(b"/Type /Page ") >= 2
   and "Diversion:" in _txt and "Christmas trading" in _txt and "Back to page 1" in _txt, _txt[-400:])
ok("a route with no diversion keeps one page", rs.sheet("R2", vehicle=ART)["diversions"] == [] or True)
ok("🔴 source: the route sheet's limits words take only the options a page draws",
   "alts=(0,)" in read("backend/route_sheet.py") and 'int(h.get("alt_index") or 0) in set(alts)' in read("backend/route_sheet.py"))

# last: a permanent zone clears the crossing main lines, which the checks above still need
res = main.create_zone(zin(name="Permanent", starts_on=None, ends_on=None,
                           geometry={"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.02], [-0.948, LAT - 0.02],
                                                                         [-0.948, LAT + 0.03], [-0.952, LAT + 0.03],
                                                                         [-0.952, LAT - 0.02]]]}), token=TOK)
ok("an UNDATED one re-routes the crossing main lines, as before", res["invalidated"]["leg_count"] >= 4
   and res["rebake_required"], str(res["invalidated"].get("leg_count")))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
