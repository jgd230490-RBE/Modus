"""
Vehicle holding areas (29 Oct 2026, task 3c) — PR 1: backend/holding.py, the location type "Holding area", a site's
"Lorries call off through", a route's "does not call off" tick, the MARK on every stored line (where a leg stops, on or
off the line), the bake THROUGH a holding area, the holding area's check minutes in the cycle, the package.
A small fictional scheme is seeded: two quarries, a works site with a gate in and a gate out, a tip, a holding area
whose entrance lies exactly on the straight line between the first quarry and the site, and a second one 2 km off it;
straight stored lines stand in for HERE's. Asserted: the type and its role, every refusal, the mark for each leg and
lorry type (the tipper stops, the mixer is exempt, the return leg stops only where it arrives at a served site, a way
round is marked too), the tick and the exemption re-marking, the cycle minutes, a bake through the holding area with a
stubbed HERE (two calls, one option, the stored line passes it), the package round trip, the delete.
WHAT THIS DOES NOT PROVE: the Simulation's call-off rule (PR 2), the screens (PR 3), Postgres, the HTTP layer (stubbed).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_holding.py
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

# --- the same stubs every backend harness uses (no FastAPI in .venv-tests) -------------------------------------------
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


def _Query(default=None, **k):
    return default


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query


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


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


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

TMP = tempfile.mkdtemp(prefix="rbe_hold_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import config  # noqa: E402
import gates  # noqa: E402
import network  # noqa: E402
import haul  # noqa: E402
import here_routing  # noqa: E402
import holding  # noqa: E402
import limits  # noqa: E402
import sim  # noqa: E402
import tenant_package  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "hold-admin-token"
TOK = "hold-admin-token"
days.START_YEAR = main.START_YEAR


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db()
    db.init_network_db()
    db.init_taxonomy_db()
    db.init_zones_db()
    db.init_gates_db()
    db.init_weeks_db()
    db.init_lookahead_db()
    db.init_config_db()
    db.init_costing_db()
    db.init_tenant()
    limits.init_db()
    config.invalidate()
    config.seed_from_file(conversions)


PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


def row(table, rid):
    r = db.query(f"SELECT * FROM {table} WHERE tenant_id = ? AND id = ?", (db.current_tenant(), rid))
    return r[0] if r else None


def geom(rid, profile, leg, alt=0):
    r = db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? AND leg = ? "
                 "AND alt_index = ?", (db.current_tenant(), rid, profile, leg, alt))
    return r[0] if r else None


def marks(rid, profile, leg, alt=0):
    g = geom(rid, profile, leg, alt)
    return (g["holding_id"], g["holding_at_km"], g["holding_tail_hr"]) if g else None


# =========================================================================== #
#  0. A small scheme                                                            #
# =========================================================================== #
TIP = "Artic Tipper (44t)"
MIX = "Truck mixer 8 m³ (32t)"
SMALL, EARTH, BALLAST = "Small aggregate", "Earthworks / soil", "Large aggregate / ballast"
GQ, GA, GB, GT, GP = (-0.901, 52.601), (-0.8803, 52.6535), (-0.8835, 52.6525), (-0.801, 52.521), (-0.861, 52.741)
HG = ((GQ[0] + GA[0]) / 2, (GQ[1] + GA[1]) / 2)          # the holding area's entrance: on the straight quarry -> site line
NODES = [("L1", "Brook Quarry", "Quarry", "origin", -0.90, 52.60), ("L2", "Viaduct site", "Site", "destination", -0.8810, 52.6540),
         ("L3", "Inert tip", "Landfill", "destination", -0.80, 52.52), ("L4", "Ridge Quarry", "Quarry", "origin", -0.86, 52.74)]
GATES = [("GQ", "Pit gate", "L1", "both", True, 3, *GQ), ("GA", "Lane gate (in)", "L2", "access", True, 3, *GA),
         ("GB", "Lane gate (out)", "L2", "egress", False, None, *GB), ("GT", "Weighbridge", "L3", "both", True, 4, *GT),
         ("GP", "Quarry gate", "L4", "both", True, 3, *GP)]
ROUTES = [("R1", "L1", "L2", "GQ", "GA", SMALL), ("R2", "L2", "L3", "GB", "GT", EARTH), ("R3", "L4", "L2", "GP", "GA", BALLAST),
          ("R4", "L1", "L3", "GQ", "GT", SMALL), ("R5", "L1", "L2", "GQ", "GA", "Ready-mixed concrete")]


def km(a, b):
    return sim.metres(list(a), list(b)) / 1000.0


def store(rid, profile, leg, pts, alt=0):
    dist = sum(km(a, b) for a, b in zip(pts, pts[1:]))
    network._upsert_geom(rid, profile, json.dumps([list(p) for p in pts]), round(dist, 3), round(dist / 40.0, 4), None,
                         leg=leg, alt_index=alt, zones_applied="", haul_zones="")
    return dist


def seed():
    reset_db()
    access.set_current("planner123")
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (db.current_tenant(), "IPT1", "North Team", True))
    for lid, name, lt, role, lon, lat in NODES:
        db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", (lid, name, lt, role, lat, lon))
    for gid, name, loc, d, dflt, sm, lon, lat in GATES:
        r = gates.create_gate(loc, name, lat, lon, direction=d, safety_minutes=sm, is_default=dflt, gate_id=gid)
        assert not r.get("error"), r
    for rid, o, d, og, dg, mat in ROUTES:
        db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt, material_category) VALUES (?, ?, ?, ?, ?)", (rid, o, d, "IPT1", mat))
        r = gates.set_route_gates(rid, origin_gate_id=og, dest_gate_id=dg, origin_given=True, dest_given=True)
        assert not r.get("error"), r


seed()
factors = conversions.load_factors()

# =========================================================================== #
#  1. Source level                                                              #
# =========================================================================== #
src = open(os.path.join(BACKEND, "holding.py"), encoding="utf-8").read()
_stm = re.findall(r'db\.(?:query|execute)\(\s*(f?(?:"[^"]*"\s*)+)', src)
ok("🔴 tenant isolation: every SQL literal in holding.py constrains tenant_id",
   len(_stm) >= 8 and all("tenant_id = ?" in s for s in _stm), str(len(_stm)))
ok("1. holding.py never writes a line: no INSERT into route_geometry, only the three mark columns are UPDATEd",
   "INSERT INTO route_geometry" not in src and src.count("UPDATE route_geometry SET holding_id") == 2)
ok("1. the words are the UK's: lorry, never truck (the vehicle KEY 'Truck mixer' is data, not a word of this module)",
   "truck" not in src.replace("Truck mixer", "").lower())
_net = open(os.path.join(BACKEND, "network.py"), encoding="utf-8").read()
ok("1. a plain bake's leg_request call is exactly what it was; the holding stop joins only on via_holding",
   "leg_request(r, o, d, leg, gates_by_loc) if hold is None else" in _net and '{"via_holding": True} if via_holding else {}' in _net)
for col in ("holding_spaces", "holding_call", "holding_exempt", "holding_id"):
    ok(f"1. locations.{col} exists", db.query(f"SELECT {col} FROM locations WHERE tenant_id = ? LIMIT 1", (db.current_tenant(),)) is not None)
ok("1. routes.skip_holding exists", db.query("SELECT skip_holding FROM routes WHERE tenant_id = ? LIMIT 1", (db.current_tenant(),)) is not None)
for col in ("holding_id", "holding_at_km", "holding_tail_hr"):
    ok(f"1. route_geometry.{col} exists", db.query(f"SELECT {col} FROM route_geometry WHERE tenant_id = ? LIMIT 1", (db.current_tenant(),)) is not None)

# =========================================================================== #
#  2. The type, its role, its fields                                            #
# =========================================================================== #
ok("2. ⭐ the type 'Holding area' has the role 'holding' (never a route's start or end)",
   network._role_for("Holding area") == "holding" and network._role_for("Site") == "destination")
ok("2. the default exemption is the concrete mixers, found by their word, not a hard-coded key",
   set(holding.default_exempt(factors)) == {"Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)"}, str(holding.default_exempt(factors)))
h1 = main.create_location(main.LocationIn(name="Lane holding area", role="both", lat=HG[1], lon=HG[0], loc_type="Holding area",
                                          supplies=[SMALL], receives=[EARTH], holding_spaces=15, holding_call=2), token=TOK)
H1 = h1.get("id")
hrow = row("locations", H1)
ok("2. ⭐ a holding area made with supplies and receives keeps neither, and its role is 'holding' whatever was sent",
   H1 and hrow["role"] == "holding" and json.loads(hrow["supplies"] or "[]") == [] and json.loads(hrow["receives"] or "[]") == []
   and hrow["holding_spaces"] == 15 and hrow["holding_call"] == 2 and hrow["holding_exempt"] is None, str(hrow))
g = gates.create_gate(H1, "Lane entrance", HG[1], HG[0], direction="both", safety_minutes=5, is_default=True, gate_id="GH",
                      open_from="07:00", open_to="20:30")
ok("2. the holding area's entrance is an ordinary gate row (hours, check minutes)", not g.get("error"), str(g))
h2 = main.create_location(main.LocationIn(name="Far holding area", role="both", lat=HG[1] + 0.018, lon=HG[0], loc_type="Holding area"),
                          token=TOK)
H2 = h2.get("id")
e = raises(lambda: main.create_location(main.LocationIn(name="x", role="both", lat=52.6, lon=-0.9, loc_type="Holding area", holding_spaces=0), token=TOK))
ok("2. spaces below 1 are refused in words", e is not None and "400" in str(e) and "lorries" in str(e), str(e))
e = raises(lambda: main.create_location(main.LocationIn(name="x", role="both", lat=52.6, lon=-0.9, loc_type="Holding area", holding_call=0), token=TOK))
ok("2. called forward below 1 is refused", e is not None and "400" in str(e), str(e))
e = raises(lambda: main.create_location(main.LocationIn(name="x", role="both", lat=52.6, lon=-0.9, loc_type="Holding area", holding_exempt=["Flying lorry"]), token=TOK))
ok("2. an unknown vehicle in the exemption is refused and named", e is not None and "400" in str(e) and "Flying lorry" in str(e), str(e))
e = raises(lambda: main.create_location(main.LocationIn(name="x", role="destination", lat=52.6, lon=-0.9, loc_type="Site", holding_spaces=10), token=TOK))
ok("2. the holding area's fields on a site are refused", e is not None and "400" in str(e) and "holding area" in str(e), str(e))
e = raises(lambda: main.create_location(main.LocationIn(name="x", role="both", lat=52.6, lon=-0.9, loc_type="Holding area", holding_id=H1), token=TOK))
ok("2. a holding area does not call off through another", e is not None and "400" in str(e), str(e))
ok("2. the exempt list as typed is validated against the scheme's vehicles and stored as JSON",
   holding.set_holding(H1, {"holding_exempt"}, exempt=[MIX]).get("holding_exempt") == [MIX]
   and json.loads(row("locations", H1)["holding_exempt"]) == [MIX])
ok("2. a blank exemption goes back to the default (the mixers)",
   holding.set_holding(H1, {"holding_exempt"}, exempt=None).get("holding_exempt") == holding.default_exempt(factors)
   and row("locations", H1)["holding_exempt"] is None)
ok("2. set_holding on a site is refused", holding.set_holding("L2", {"holding_spaces"}, spaces=3).get("error"))

# the site calls off through it
L2 = row("locations", "L2")
r = main.update_location("L2", main.LocationIn(name=L2["name"], role="destination", lat=L2["lat"], lon=L2["lon"], loc_type="Site",
                                                 holding_id=H1), token=TOK)
ok("2. ⭐ a site names the holding area its lorries call off through", not r.get("error") and row("locations", "L2")["holding_id"] == H1, str(r))
e = raises(lambda: main.update_location("L2", main.LocationIn(name=L2["name"], role="destination", lat=L2["lat"], lon=L2["lon"], loc_type="Site",
                                                              holding_id="L1"), token=TOK))
ok("2. a quarry is not a holding area: refused and named", e is not None and "400" in str(e) and "Brook Quarry" in str(e), str(e))
e = raises(lambda: main.update_location("L2", main.LocationIn(name=L2["name"], role="destination", lat=L2["lat"], lon=L2["lon"], loc_type="Site",
                                                              holding_id="L9"), token=TOK))
ok("2. an unknown holding area is refused", e is not None and "400" in str(e), str(e))
ok("2. an update that does not mention holding_id leaves it alone",
   not main.update_location("L2", main.LocationIn(name=L2["name"], role="destination", lat=L2["lat"], lon=L2["lon"], loc_type="Site"), token=TOK).get("error")
   and row("locations", "L2")["holding_id"] == H1)
ok("2. a route never starts or ends at a holding area (create)",
   "holding area" in str(network.create_route(H1, "L2").get("error")) and "holding area" in str(network.create_route("L1", H1).get("error")))
e = raises(lambda: main.update_route("R4", main.RoutePatch(dest_id=H1), token=TOK))
ok("2. ...nor by an edit", e is not None and "holding area" in str(e), str(e))
geo = network.locations_geojson()
fh = next(f for f in geo["features"] if f["properties"]["id"] == H1)
fs = next(f for f in geo["features"] if f["properties"]["id"] == "L2")
ok("2. the locations feed carries the fields (the forms read them)",
   fh["properties"]["holding_spaces"] == 15 and fh["properties"]["holding_call"] == 2 and fh["properties"]["holding_exempt"] is None
   and fh["properties"]["role"] == "holding" and fs["properties"]["holding_id"] == H1)

# =========================================================================== #
#  3. The mark on every stored line                                             #
# =========================================================================== #
d1 = store("R1", TIP, "loaded", [GQ, HG, GA])             # passes the holding area's entrance exactly
store("R1", TIP, "return", [GA, HG, GQ])                  # back to the quarry: arrives at L1, not served
store("R1", MIX, "loaded", [GQ, HG, GA])                  # a mixer: exempt
store("R1", TIP, "loaded", [GQ, (HG[0] - 0.004, HG[1]), GA], alt=1)   # an alternative 270 m west: off the line
d1w = store("R1", TIP, "loaded", [GQ, HG, GA], alt=10)    # a way round (0c) through it: marked like any row
store("R2", TIP, "loaded", [GB, GT])
d2r = store("R2", TIP, "return", [GT, HG, GB])            # the empty tipper back to the site to load: stops
store("R3", TIP, "loaded", [GP, GA])                      # does not pass it (2 km off)
store("R4", TIP, "loaded", [GQ, GT])                      # neither end served
store("R5", MIX, "loaded", [GQ, HG, GA])                  # a mixer-only route
res = holding.mark_all()
ok("3. ⭐ mark_all counts what it did", res["routes"] == 5 and res["marked"] == 3 and res["off_line"] == 2, str(res))
m = marks("R1", TIP, "loaded")
at_km = km(GQ, HG)
ok("3. ⭐ the tipper into the site stops at the holding area, at its km along the line, the tail time shared by distance",
   m[0] == H1 and abs(m[1] - at_km) < 0.02 and abs(m[2] - (d1 / 40.0) * (1 - at_km / d1)) < 0.002, str((m, at_km, d1)))
ok("3. the return to the quarry does not stop (the quarry calls off nowhere)", marks("R1", TIP, "return") == (None, None, None))
ok("3. ⭐ the mixer is exempt: its row carries no stop", marks("R1", MIX, "loaded") == (None, None, None))
ok("3. an alternative 270 m west of the entrance: the leg should stop but the line does not pass it (holding_id set, no km)",
   marks("R1", TIP, "loaded", 1) == (H1, None, None), str(marks("R1", TIP, "loaded", 1)))
ok("3. a way round (alt 10) through it is marked like any row", marks("R1", TIP, "loaded", 10)[0] == H1 and marks("R1", TIP, "loaded", 10)[1] is not None)
m2 = marks("R2", TIP, "return")
ok("3. ⭐ the empty tipper coming back to the site to load calls off: the RETURN leg is the one that stops",
   m2[0] == H1 and abs(m2[1] - km(GT, HG)) < 0.02 and marks("R2", TIP, "loaded") == (None, None, None), str(m2))
ok("3. a route into the site whose line does not pass it: 'route again'", marks("R3", TIP, "loaded") == (H1, None, None))
ok("3. a route serving no site with a holding area: nothing", marks("R4", TIP, "loaded") == (None, None, None))
S = main.holding_summary()
st = {r["route_id"]: r["state"] for r in S["routes"]}
ok("3. ⭐ the summary names each route's state: calls / route_again / exempt, and leaves R4 out",
   st == {"R1": "calls", "R2": "calls", "R3": "route_again", "R5": "exempt"}, str(st))
a1 = S["holding_areas"][0]
ok("3. the summary's holding area: spaces, call, the mixers by their label, its entrance gate, the site it serves",
   a1["id"] == H1 and a1["spaces"] == 15 and a1["call"] == 2 and a1["exempt"] == holding.default_exempt(factors)
   and all("mixer" in x.lower() for x in a1["exempt_labels"]) and a1["gate"]["gate_id"] == "GH" and a1["gate"]["check_minutes"] == 5
   and [s["id"] for s in a1["served"]] == ["L2"], str(a1))
r1 = next(r for r in S["routes"] if r["route_id"] == "R1")
ok("3. a route's legs in the summary: the tipper's loaded leg on the line, with its km and tail",
   any(l["profile"] == TIP and l["leg"] == "loaded" and l["on_line"] and l["at_km"] is not None for l in r1["legs"])
   and r1["stops"] == {"loaded": H1}, str(r1))

# the tick
r = main.set_route_planning("R1", main.RoutePlanning(skip_holding=1), token=TOK)
ok("3. ⭐ the route's 'does not call off' tick clears its marks", r.get("skip_holding") == 1 and marks("R1", TIP, "loaded") == (None, None, None)
   and {x["route_id"]: x["state"] for x in main.holding_summary()["routes"]}["R1"] == "skip", str(r))
r = main.set_route_planning("R1", main.RoutePlanning(skip_holding=0), token=TOK)
ok("3. ...and untick marks them again", r.get("skip_holding") == 0 and marks("R1", TIP, "loaded")[0] == H1)
ok("3. the other planning fields are untouched by the tick", row("routes", "R1")["max_vehicles_per_day"] is None)
# the exemption
holding.set_holding(H1, {"holding_exempt"}, exempt=[TIP])
ok("3. ⭐ exempting the tipper instead: its rows clear and the mixer's rows are marked",
   marks("R1", TIP, "loaded") == (None, None, None) and marks("R1", MIX, "loaded")[0] == H1 and marks("R5", MIX, "loaded")[0] == H1)
holding.set_holding(H1, {"holding_exempt"}, exempt=None)
ok("3. ...and back to the default", marks("R1", TIP, "loaded")[0] == H1 and marks("R1", MIX, "loaded") == (None, None, None))
# the site's choice
holding.set_calls_through("L2", None)
ok("3. a site that calls off nowhere: every mark of its routes clears", marks("R1", TIP, "loaded") == (None, None, None)
   and marks("R2", TIP, "return") == (None, None, None) and main.holding_summary()["routes"] == [])
holding.set_calls_through("L2", H1)
ok("3. ...and naming it again marks them", marks("R1", TIP, "loaded")[0] == H1)
ok("3. the far holding area serves nothing: no route stops there", not any(m[0] == H2 for m in (marks("R1", TIP, "loaded"), marks("R3", TIP, "loaded"))))
_K = math.pi / 180 * holding.R_EARTH                      # metres a degree at the equator (the module's own constant)
ok("3. nearest_on_line: a point 30 m beside a 1 km line, 400 m along",
   (lambda n: n and abs(n[0] - 30) < 0.5 and abs(n[1] - 400) < 0.5 and abs(n[2] - 1000) < 0.5)(
       holding.nearest_on_line([[0.0, 52.0], [1000 / (_K * math.cos(52 * math.pi / 180)), 52.0]],
                               400 / (_K * math.cos(52 * math.pi / 180)), 52.0 + 30 / _K)))
ok("3. with_step puts the stop before the arrival gate's access road, else last",
   [s.get("holding_id") for s in holding.with_step([{"gate_role": "exit"}, {"gate_role": "entry"}], {"id": H1, "name": "x", "gate": {"lat": 52.6, "lon": -0.9}})] == [None, H1, None]
   and [s.get("holding_id") for s in holding.with_step([], {"id": H1, "name": "x", "gate": {"lat": 52.6, "lon": -0.9}})] == [H1])

# =========================================================================== #
#  4. The cycle: the holding area's check minutes                                #
# =========================================================================== #
gbl = gates.gates_by_location()
L1, L2, L3, L4 = (row("locations", x) for x in ("L1", "L2", "L3", "L4"))
R1, R2, R3, R4 = (row("routes", x) for x in ("R1", "R2", "R3", "R4"))
p = network._turnaround_parts(TIP, factors, origin=L1, dest=L2, route=R1, gates_by_loc=gbl)
ok("4. ⭐ the tipper into the site pays the holding area's 5 check minutes once a cycle, on top of the gates' 3 + 3",
   p["holding_minutes"] == 5.0 and p["safety_minutes"] == 6.0 and abs(p["total_minutes"] - (p["load_minutes"] + p["unload_minutes"] + 11.0)) < 1e-9, str(p))
ok("4. the mixer pays nothing at the holding area", network._turnaround_parts(MIX, factors, origin=L1, dest=L2, route=R1, gates_by_loc=gbl)["holding_minutes"] == 0.0)
ok("4. the empty tipper back to the site to load (R2) pays it on its return", network._turnaround_parts(TIP, factors, origin=L2, dest=L3, route=R2, gates_by_loc=gbl)["holding_minutes"] == 5.0)
ok("4. a route serving no holding area pays nothing", network._turnaround_parts(TIP, factors, origin=L1, dest=L3, route=R4, gates_by_loc=gbl)["holding_minutes"] == 0.0)
main.set_route_planning("R1", main.RoutePlanning(skip_holding=1), token=TOK)
ok("4. the tick takes the minutes off the cycle too (the route row as stored after the tick)",
   network._turnaround_parts(TIP, factors, origin=L1, dest=L2, route=row("routes", "R1"), gates_by_loc=gbl)["holding_minutes"] == 0.0)
main.set_route_planning("R1", main.RoutePlanning(skip_holding=0), token=TOK)
ra = network.route_analysis("R1")


def _find(o, key):
    """every value of `key` in a nested reply"""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from _find(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from _find(v, key)


_tp = [p for p in _find(ra, "turnaround_parts") if isinstance(p, dict)]
ok("4. route_analysis carries the minutes in each row's turnaround parts (the Routes page's cycle)",
   _tp and all("holding_minutes" in p for p in _tp) and any(p["holding_minutes"] == 5.0 for p in _tp)
   and any(p["holding_minutes"] == 0.0 for p in _tp), str(_tp)[:300])

# =========================================================================== #
#  5. The bake THROUGH the holding area (HERE stubbed)                          #
# =========================================================================== #
CALLS = []


def _fake_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, **kw):
    CALLS.append((round(o_lat, 5), round(o_lon, 5), round(d_lat, 5), round(d_lon, 5), kw.get("alternatives")))
    d = km((o_lon, o_lat), (d_lon, d_lat))
    return [{"geometry": [[o_lon, o_lat], [d_lon, d_lat]], "distance_km": round(d, 3), "duration_hr": round(d / 40.0, 4), "sections": []}]


_real = (here_routing.routes, here_routing.configured)
here_routing.routes, here_routing.configured = _fake_routes, (lambda: True)
try:
    CALLS.clear()
    r = network.bake_route("R3", TIP, legs=("loaded",))
    plain = marks("R3", TIP, "loaded")
    ok("5. a plain bake: one HERE call, the straight line does not pass the holding area, so the row says 'route again'",
       r.get("baked") and len(CALLS) == 1 and plain == (H1, None, None), str((r, CALLS, plain)))
    CALLS.clear()
    r = network.bake_route("R3", TIP, legs=("loaded",), via_holding=True)
    g3 = geom("R3", TIP, "loaded")
    m3 = marks("R3", TIP, "loaded")
    ok("5. ⭐ via_holding: TWO HERE calls, quarry -> the entrance -> the gate, and the stored line now passes it (marked, on the line)",
       r.get("baked") and len(CALLS) == 2 and CALLS[0][2:4] == (round(HG[1], 5), round(HG[0], 5)) and CALLS[1][0:2] == (round(HG[1], 5), round(HG[0], 5))
       and m3[0] == H1 and m3[1] is not None and abs(m3[1] - km(GP, HG)) < 0.02, str((r, CALLS, m3)))
    ok("5. the row's haul_zones names the stop (never a zone id) and its distance is the two straight legs",
       "hold:" + H1 in (g3["haul_zones"] or "") and abs(g3["distance_km"] - (km(GP, HG) + km(HG, GA))) < 0.01, str(g3["haul_zones"]))
    ok("5. one option only (spliced), said by the bake", r["legs"]["loaded"]["alternatives"] == 1, str(r))
    CALLS.clear()
    r = network.bake_route("R1", MIX, legs=("loaded",), via_holding=True)
    ok("5. via_holding on an exempt lorry type is a plain bake (one call, no stop)", r.get("baked") and len(CALLS) == 1 and marks("R1", MIX, "loaded") == (None, None, None), str(CALLS))
    CALLS.clear()
    r = network.bake_route("R4", TIP, legs=("loaded",), via_holding=True)
    ok("5. via_holding on a route that serves no holding area is a plain bake", r.get("baked") and len(CALLS) == 1 and marks("R4", TIP, "loaded") == (None, None, None))
    main.set_route_planning("R3", main.RoutePlanning(skip_holding=1), token=TOK)
    CALLS.clear()
    r = network.bake_route("R3", TIP, legs=("loaded",), via_holding=True)
    ok("5. via_holding on a ticked route is a plain bake", r.get("baked") and len(CALLS) == 1 and marks("R3", TIP, "loaded") == (None, None, None))
    main.set_route_planning("R3", main.RoutePlanning(skip_holding=0), token=TOK)
    ok("5. the endpoint takes via_holding", not main.bake_route("R3", TIP, legs="loaded", via_holding=True, token=TOK).get("error") and len(CALLS) == 3)
    st = {x["route_id"]: x["state"] for x in main.holding_summary()["routes"]}
    ok("5. after the bake through it, R3 calls", st.get("R3") == "calls", str(st))
    # a bake writes a plain row again: the next bake without via_holding loses the stop and says so
    CALLS.clear()
    network.bake_route("R3", TIP, legs=("loaded",))
    ok("5. the next plain bake routes the straight way again: 'route again' once more (a bake is not durable, as promote is not)",
       marks("R3", TIP, "loaded") == (H1, None, None))
finally:
    here_routing.routes, here_routing.configured = _real

# =========================================================================== #
#  6. The package, the delete, the invariant                                    #
# =========================================================================== #
pkg = tenant_package.export_tenant()
before = (row("locations", H1)["holding_spaces"], row("locations", "L2")["holding_id"], marks("R1", TIP, "loaded"))
res = tenant_package.import_tenant(pkg, replace=True)
after = (row("locations", H1)["holding_spaces"], row("locations", "L2")["holding_id"], marks("R1", TIP, "loaded"))
ok("6. ⭐ the package carries the holding area, the site's choice, the tick and the marks (a round trip changes nothing)",
   res.get("ok") and not res.get("dropped_columns") and before == after and before[0] == 15 and before[1] == H1 and before[2][0] == H1, str((res, before, after)))
# the invariant: a scheme with no holding area
holding.set_calls_through("L2", None)
r = network.delete_location(H1)
ok("6. deleting the holding area: nothing references it", not r.get("error") and row("locations", "L2")["holding_id"] is None
   and not db.query("SELECT 1 FROM route_geometry WHERE tenant_id = ? AND holding_id IS NOT NULL", (db.current_tenant(),)))
network.delete_location(H2)
ok("6. ⭐ with no holding area: no minutes in any cycle, mark_all does nothing, the summary is empty",
   network._turnaround_parts(TIP, factors, origin=L1, dest=L2, route=R1, gates_by_loc=gbl)["holding_minutes"] == 0.0
   and holding.mark_all() == {"marked": 0, "off_line": 0, "cleared": 0, "routes": 0}
   and main.holding_summary()["holding_areas"] == [] and main.holding_summary()["routes"] == [])
p0 = network._turnaround_parts(TIP, factors, origin=L1, dest=L2, route=R1, gates_by_loc=gbl)
ok("6. the turnaround invariant: load + unload + the gates' minutes to the digit",
   abs(p0["total_minutes"] - (p0["load_minutes"] + p0["unload_minutes"] + p0["safety_minutes"] + p0["internal_travel_minutes"])) < 1e-9)
# a site that was a holding area and changes type loses its sites' choice
h3 = main.create_location(main.LocationIn(name="Temp holding area", role="both", lat=52.61, lon=-0.91, loc_type="Holding area", holding_spaces=4), token=TOK)
holding.set_calls_through("L2", h3["id"])
main.update_location(h3["id"], main.LocationIn(name="Now a depot", role="both", lat=52.61, lon=-0.91, loc_type="Depot"), token=TOK)
ok("6. a holding area re-typed as something else: its role follows the type and the site no longer calls off through it",
   row("locations", h3["id"])["role"] == "both" and row("locations", "L2")["holding_id"] is None, str(row("locations", h3["id"])))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
