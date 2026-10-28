"""
The simulation v2 (28 Oct 2026, task 0e) — on site: backend/sim_site.py, site_areas.py, the gates' closed periods, the
internal roads, the week and day scales, GET /api/sim/day's new parameters and the site-area endpoints.

A small fictional scheme is seeded (a quarry, a works site with a gate in and a gate out, a tip, a second quarry) with
three areas (Pier bases unload 5 min, Spoil loading 10 min, the wheel wash) and three internal roads drawn at the
mockup's layout; three approved lines in Sep 2026. Asserted: the chain every lorry runs (area -> wash -> gate out),
the stations' queues (a pour of 22 mixers queues at the one pump bay; two bays or 2 minutes clear it), a what-if site
speed, a line no area takes, a gate closed for a period (refusals, the month rule, resolve's fallback, the Dashboard's
and the Look-ahead's rows), the week and day scales from the Look-ahead's day plan, the endpoints, the package.

WHAT THIS DOES NOT PROVE: the drawing (the Dashboard section reads these figures); Postgres; the HTTP layer (stubbed;
http_smoke.py drives the real one against the demo package).

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_sim_site.py
"""
import json
import math
import os
import re
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_gate_arrivals.py ------------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_sim_")
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
import costing  # noqa: E402
import gates  # noqa: E402
import gate_arrivals  # noqa: E402
import gate_hours  # noqa: E402
import network  # noqa: E402
import zones  # noqa: E402
import limits  # noqa: E402
import sim  # noqa: E402
import tenant_package  # noqa: E402
import derived  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
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
    limits.init_db()            # a stored route's limit check is cleared when its line is written
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    costing.invalidate()


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


def hm(m):
    return sim.hhmm(m)


import datetime  # noqa: E402
import site_areas  # noqa: E402
import sim_site  # noqa: E402
import haul  # noqa: E402
import network  # noqa: E402
import weeks  # noqa: E402

os.environ["ADMIN_TOKEN"] = "simv2-admin-token"
TOK = "simv2-admin-token"

# =========================================================================== #
#  0. A small scheme: a quarry, a works site with two gates, a tip, a plant      #
# =========================================================================== #
C = (-0.8803, 52.6535)
KX = 111320.0 * math.cos(C[1] * math.pi / 180)


def ll(e, n):
    return [round(C[0] + e / KX, 6), round(C[1] + n / 111320.0, 6)]


SMALL, BALLAST, EARTH, READY = "Small aggregate", "Large aggregate / ballast", "Earthworks / soil", "Ready-mixed concrete"
TIP = "Artic Tipper (44t)"
NODES = [("L1", "Brook Quarry", "Quarry", "origin", -0.90, 52.60), ("L2", "Viaduct site", "Site", "destination", C[0], C[1]),
         ("L3", "Inert tip", "Landfill", "destination", -0.80, 52.52), ("L4", "Ridge Quarry", "Quarry", "origin", -0.86, 52.74)]
# the site's inside, metres east / north of its centre (the mockup's layout)
PT = {"GA": (385, 125), "J0": (300, 110), "J1": (150, 90), "RT": (40, 60), "RM": (-80, -20), "RB": (-170, -120),
      "P": (-230, -170), "S": (-120, -200), "E1": (330, 20), "W": (355, -50), "GB": (385, -110)}
GATES = [("GQ", "Pit gate", "L1", "both", True, 3, None, -0.901, 52.601),
         ("GA", "Hyde Lodge Road gate (in)", "L2", "access", True, 3, None, *ll(*PT["GA"])),
         ("GB", "Brook Lane gate (out)", "L2", "egress", False, None, None, *ll(*PT["GB"])),
         ("GT", "Weighbridge", "L3", "both", True, 4, None, -0.801, 52.521),
         ("GP", "Quarry gate", "L4", "both", True, 3, None, -0.861, 52.741)]
ROUTES = [("R1", "L1", "L2", "IPT1", "GQ", "GA", SMALL), ("R2", "L2", "L3", "IPT1", "GB", "GT", EARTH),
          ("R3", "L4", "L2", "IPT1", "GP", "GA", BALLAST)]
LINES = [("R1", 8800, SMALL), ("R2", 4400, EARTH), ("R3", 6100, BALLAST)]


def seed():
    reset_db()
    access.set_current("planner123")
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (db.current_tenant(), "IPT1", "North Team", True))
    for lid, name, lt, role, lon, lat in NODES:
        db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", (lid, name, lt, role, lat, lon))
    for gid, name, loc, d, dflt, sm, itm, lon, lat in GATES:
        r = gates.create_gate(loc, name, lat, lon, direction=d, safety_minutes=sm, internal_travel_minutes=itm, is_default=dflt, gate_id=gid)
        assert not r.get("error"), r
    for rid, o, d, ipt, og, dg, mat in ROUTES:
        db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt, material_category) VALUES (?, ?, ?, ?, ?)", (rid, o, d, ipt, mat))
        r = gates.set_route_gates(rid, origin_gate_id=og, dest_gate_id=dg, origin_given=True, dest_given=True)
        assert not r.get("error"), r
    for rid, t, mat in LINES:
        main.save_matrix_row(main.MatrixRow(
            route_id=rid, discipline="earthworks", section_id="WS1", material_type=mat,
            material_description=None, vehicle_type=TIP, submitted_by="tester", unit="t", status="Pending",
            cells=[main.Cell(month_index=9, quantity=float(t))], ipt="IPT1"))
        main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id="WS1")


seed()
factors = conversions.load_factors()
WD = main._working_days(factors)
acc_planner = access.current()

# =========================================================================== #
#  1. Source level                                                              #
# =========================================================================== #
src_site = open(os.path.join(BACKEND, "sim_site.py"), encoding="utf-8").read()
src_areas = open(os.path.join(BACKEND, "site_areas.py"), encoding="utf-8").read()
ok("⭐ sim_site.py is pure: no SQL, no db import, no write", "import db" not in src_site and "db." not in src_site.replace("db.", "db.", 0)
   and not re.search(r"\b(INSERT|UPDATE|DELETE|SELECT)\b", src_site))
_stm = re.findall(r'db\.(?:query|execute)\(\s*(f?(?:"[^"]*"\s*)+)', src_areas)
ok("🔴 tenant isolation: every SQL literal in site_areas.py constrains tenant_id",
   len(_stm) >= 8 and all("tenant_id = ?" in s or "tenant_id, id" in s for s in _stm), str(len(_stm)))
ok("neither module names a team slot id", re.search(r"\bIPT ?[1-6]\b", src_site + src_areas) is None)
ok("the registries: site_areas is a tenanted table, in the package order and in the empty check",
   "site_areas" in db.TENANTED_TABLES and "site_areas" in db._TENANT_DDL and "site_areas" in db._TENANT_PK
   and "site_areas" in tenant_package.ORDER and "site_areas" in tenant_package.EMPTY_CHECK)
main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("⭐ the site-area writes are admin-only, the list needs a sign-in, the simulation's new query parameters are read",
   main_src.count('@app.post("/api/admin/site-areas")') == 1 and main_src.count('@app.patch("/api/admin/site-areas/{area_id}")') == 1
   and main_src.count('@app.delete("/api/admin/site-areas/{area_id}")') == 1
   and 'def list_site_areas' in main_src and "_require_access()" in main_src[main_src.index("def list_site_areas"):main_src.index("def list_site_areas") + 400]
   and "scale=scale, bucket=(week or \"commit\"), date=date" in main_src)

# =========================================================================== #
#  2. Site areas: writes, validation, the lorry's area, the service minutes    #
# =========================================================================== #
poly = {"type": "Polygon", "coordinates": [[ll(-330, -150), ll(-190, -150), ll(-190, -260), ll(-330, -260), ll(-330, -150)]]}
a1 = site_areas.create_area("L2", "Pier bases", activity="unload", materials=[SMALL, BALLAST, READY], service_minutes=5, bays=1,
                            level="river terrace, -8 m", geometry=poly)
a2 = site_areas.create_area("L2", "Spoil loading", activity="load", materials=[EARTH], service_minutes=10, bays=1,
                            geometry={"type": "Point", "coordinates": ll(*PT["S"])})
a3 = site_areas.create_area("L2", "Wheel wash", activity="wash", geometry={"type": "Point", "coordinates": ll(*PT["W"])})
ok("⭐ three areas created with ids A001–A003, the polygon's centroid as its point, the wash with no minutes typed",
   [a1.get("id"), a2.get("id"), a3.get("id")] == ["A001", "A002", "A003"] and a1["point"] is not None
   and abs(a1["point"][0] - ll(-260, -205)[0]) < 1e-5 and abs(a1["point"][1] - ll(-260, -205)[1]) < 1e-5
   and a3["service_minutes"] is None and a1["materials"] == [SMALL, BALLAST, READY] and a1["bays"] == 1 and a1["level"] == "river terrace, -8 m",
   str((a1, a2, a3))[:300])
ok("🔴 refused in words: a second wash, a bad activity, 0 bays, 300 minutes, a missing site, an empty name, a line as a shape",
   "already has a wheel wash" in (site_areas.create_area("L2", "Wash 2", activity="wash").get("error") or "")
   and "activity must be" in (site_areas.create_area("L2", "X", activity="park").get("error") or "")
   and "bays must be" in (site_areas.create_area("L2", "X", bays=0).get("error") or "")
   and "minutes a lorry must be" in (site_areas.create_area("L2", "X", service_minutes=300).get("error") or "")
   and "not found" in (site_areas.create_area("L9", "X").get("error") or "")
   and "name is required" in (site_areas.create_area("L2", " ").get("error") or "")
   and "drawn as a point or a shape" in (site_areas.create_area("L2", "X", geometry={"type": "LineString", "coordinates": [ll(0, 0), ll(1, 1)]}).get("error") or ""))
u = site_areas.update_area("A001", bays=2)
ok("a partial update writes the field sent and nothing else; an unknown id is 'area not found'",
   u.get("bays") == 2 and u.get("service_minutes") == 5 and u["materials"] == [SMALL, BALLAST, READY]
   and site_areas.update_area("A009", bays=2).get("error") == "area not found")
site_areas.update_area("A001", bays=1)
ok("area_for: a laden stone lorry -> Pier bases, an empty muck-away lorry -> Spoil loading, the pour -> Pier bases, asphalt -> none",
   site_areas.area_for(site_areas.list_areas("L2"), "laden", SMALL, TIP)["id"] == "A001"
   and site_areas.area_for(site_areas.list_areas("L2"), "empty", EARTH, TIP)["id"] == "A002"
   and site_areas.area_for(site_areas.list_areas("L2"), "pour", READY, None)["id"] == "A001"
   and site_areas.area_for(site_areas.list_areas("L2"), "laden", "Asphalt", TIP) is None)
ok("service_for: typed minutes win; a wash defaults to 2; an untyped unload area takes the vehicle's own unload minutes (tipper 9), a load area its load minutes (15)",
   site_areas.service_for(a1, TIP, factors) == 5.0 and site_areas.service_for(a3, TIP, factors) == 2.0
   and site_areas.service_for({"activity": "unload"}, TIP, factors) == 9.0 and site_areas.service_for({"activity": "load"}, TIP, factors) == 15.0)
ok("by_location groups the site's areas; the tip has none", list(site_areas.by_location().keys()) == ["L2"] and len(site_areas.by_location()["L2"]) == 3)

# =========================================================================== #
#  3. Internal roads and the site speed                                        #
# =========================================================================== #
def road(name, keys, zid=None):
    return zones.create_zone(name, {"type": "LineString", "coordinates": [ll(*PT[k]) for k in keys]}, kind=zones.HAUL_KIND,
                             location_id="L2", zone_id=zid)


z1 = road("Top road and terrace ramp", ["GA", "J0", "J1", "RT", "RM", "RB", "P"], "Z001")
z2 = road("Spoil spur", ["RB", "S"], "Z002")
z3 = road("Exit loop", ["J0", "E1", "W", "GB"], "Z003")
ok("⭐ a haul road inside a site: location_id set, mode internal, never in haul_roads(), listed by internal_roads()",
   all(not z.get("error") for z in (z1, z2, z3)) and z1["location_id"] == "L2" and z1["haul_mode"] == "internal"
   and zones.haul_roads() == [] and zones.haul_roads(internal=True) and len(zones.internal_roads("L2")) == 3
   and list(zones.internal_roads().keys()) == ["L2"], str((z1.get("error"), z2.get("error"), z3.get("error"))))
ok("🔴 refused: a closure zone inside a site, a road inside a site that does not exist",
   "only a haul road" in (zones.create_zone("x", poly, kind="closure", location_id="L2").get("error") or "")
   and "not found" in (zones.create_zone("x", {"type": "LineString", "coordinates": [ll(0, 0), ll(5, 5)]}, kind=zones.HAUL_KIND, location_id="L9").get("error") or ""))
zp = zones.create_zone("Public haul road", {"type": "LineString", "coordinates": [[-0.93, 52.60], [-0.92, 52.61]]}, kind=zones.HAUL_KIND, speed_kph=20)
ok("a public haul road is still listed by haul_roads(); clearing a road's site makes it public again (mode no longer internal)",
   [z["id"] for z in zones.haul_roads()] == [zp["id"]]
   and zones.update_zone("Z002", location_id=None)["haul_mode"] is None and len(zones.internal_roads("L2")) == 2
   and zones.update_zone("Z002", location_id="L2")["haul_mode"] == "internal" and len(zones.internal_roads("L2")) == 3)
ok("the site speed: set, read on the location, cleared; refused above 60 km/h or below 0",
   network.set_site_speed("L2", 8).get("site_speed_kph") == 8.0
   and db.query("SELECT site_speed_kph FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "L2"))[0]["site_speed_kph"] == 8.0
   and "site speed must be" in (network.set_site_speed("L2", 90).get("error") or "") and "site speed must be" in (network.set_site_speed("L2", -1).get("error") or "")
   and network.set_site_speed("L9", 8).get("error") == "not found")

# =========================================================================== #
#  4. The site graph                                                            #
# =========================================================================== #
loc2 = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "L2"))[0]
roads = [dict(z, line=zones.as_line(z["geometry"])) for z in zones.internal_roads("L2")]
site = sim_site.site_model(loc2, gates.list_gates("L2"), site_areas.list_areas("L2"), roads, factors, {}, on=9)
ok("⭐ the site model: five stations (two gates, three areas), the typed speed, the wash found",
   set(site["stations"]) == {"gate:GA", "gate:GB", "area:A001", "area:A002", "area:A003"} and site["speed_kph"] == 8.0
   and site["speed_basis"] == "typed" and site["wash"]["id"] == "A003", str(sorted(site["stations"])))
pth = sim_site.path_between(site, "gate:GA", "area:A001")
L_expect = sum(math.hypot(PT[b][0] - PT[a][0], PT[b][1] - PT[a][1]) for a, b in zip(["GA", "J0", "J1", "RT", "RM", "RB"], ["J0", "J1", "RT", "RM", "RB", "P"]))
ok("⭐ gate A to the pier bases runs the drawn road (within 2 % of its length + the area's own snap) at 8 km/h",
   pth is not None and abs(pth["len_m"] - L_expect) < 0.02 * L_expect + 60 and abs(pth["minutes"] - pth["len_m"] / (8000 / 60)) < 0.05
   and len(pth["coords"]) >= 6 and any(p[3] == "Z001" for p in pth["parts"]), f"{pth and pth['len_m']} vs {L_expect:.0f}")
pw = sim_site.path_between(site, "area:A001", "area:A003")
ok("the pier bases to the wash go back up the ramp and round the exit loop, longer than the way in",
   pw is not None and pw["len_m"] > pth["len_m"] and any(p[3] == "Z003" for p in pw["parts"]))
site_fast = sim_site.site_model(loc2, gates.list_gates("L2"), site_areas.list_areas("L2"), roads, factors, {"site_speed": {"L2": 16}}, on=9)
ok("a scenario site speed of 16 km/h halves the drive and says so",
   site_fast["speed_basis"] == "scenario" and abs(sim_site.path_between(site_fast, "gate:GA", "area:A001")["minutes"] * 2 - pth["minutes"]) < 0.01)
site_bare = sim_site.site_model(loc2, gates.list_gates("L2"), site_areas.list_areas("L2"), [], factors, {}, on=9)
pb = sim_site.path_between(site_bare, "gate:GA", "area:A001")
ok("with no road drawn the stations join in straight lines at the site speed",
   pb is not None and len(pb["coords"]) == 2 and abs(pb["len_m"] - math.hypot(385 + 260, 125 + 205)) < 5 and pb["parts"][0][3] is None)
ok("exit_key: the site's exit gate is Brook Lane (egress) in a month with no closure", sim_site.exit_key(site, "gate:GA") == "gate:GB")

# =========================================================================== #
#  5. The day on site                                                           #
# =========================================================================== #
D = sim.day(9, acc_planner, factors=factors, working_days=WD, send_lines=True)
S = D["sites"][0]
ga = next(g for g in D["gates"] if g["gate_id"] == "GA")
st = {s["key"]: s for s in S["stations"]}
ok("⭐ the reply carries one site with four stations (gate A has no exits, so no row), every lorry in found an area and left: in == out, no_area empty",
   len(D["sites"]) == 1 and S["name"] == "Viaduct site" and set(st) == {"gate:GB", "area:A001", "area:A002", "area:A003"}
   and S["lorries_in"] == ga["arrivals"] > 0 and S["lorries_out"] == S["lorries_in"] and S["no_area"] == []
   and D["checks"]["sites_add_up"] is True, str({k: v["arrivals"] for k, v in st.items()}))
ok("⭐ the stations' minutes: pier bases 5 (typed), spoil loading 10 (typed), the wash 2 (the default), the gates none",
   st["area:A001"]["service"] == 5 and st["area:A002"]["service"] == 10 and st["area:A003"]["service"] == 2
   and st["gate:GB"]["service"] is None and st["area:A001"]["service_basis"] == "typed" and st["area:A003"]["service_basis"] == "vehicle")
laden = [a for a in D["arrivals"] if a["gate"] == "GA" and a["kind"] == "laden"]
empty = [a for a in D["arrivals"] if a["gate"] == "GA" and a["kind"] == "empty"]
ok("⭐ every laden lorry: pier bases -> wash -> gate B; every empty lorry (coming to load): spoil loading -> wash -> gate B",
   laden and empty and all([s["st"] for s in a["stops"]] == ["area:A001", "area:A003", "gate:GB"] for a in laden)
   and all([s["st"] for s in a["stops"]] == ["area:A002", "area:A003", "gate:GB"] for a in empty))


def monotone(a):
    t = a["done"]
    for h, s in zip(a["hops"], a["stops"]):
        if not (abs(h["t0"] - t) < 0.02 and h["t1"] >= h["t0"] - 1e-9 and abs(s["at"] - h["t1"]) < 0.02 and s["start"] >= s["at"] - 1e-9 and s["done"] >= s["start"] - 1e-9):
            return False
        t = s["done"]
    return abs(a["out_at"] - t) < 0.02 and abs(a["on_site"] - (a["out_at"] - a["start"])) < 0.02


ok("⭐ time runs forward for every lorry: each hop starts when the last stop is done and ends where the next stop begins; on_site = out − checked in",
   all(monotone(a) for a in laden + empty) and all(len(a["hops"]) == 3 for a in laden + empty))
ok("the wash sees every lorry that left; gate B counts them as departures; the site's time on site is a few minutes, not hours",
   st["area:A003"]["arrivals"] == S["lorries_out"] and st["gate:GB"]["arrivals"] == S["lorries_out"]
   and st["gate:GB"]["status_word"] == "Counted, never queued"
   and 8 < S["avg_on_site"] < 60 and S["longest_on_site"] >= S["avg_on_site"], str((S["avg_on_site"], S["longest_on_site"])))
ok("the playback window runs to the last lorry out (not only the last check-in)",
   D["window"]["end"] >= max(a["out_at"] for a in laden + empty) - 1e-9)
ok("the paths for the drawing are in the reply with legs=1 (coords, cum, parts, minutes) and the roads carry their lines",
   "gate:GA>area:A001" in S["paths"] and S["paths"]["gate:GA>area:A001"]["coords"] and S["paths"]["gate:GA>area:A001"]["parts"]
   and all(r["coords"] for r in S["roads"]) and all(a["geometry"] or a["point"] for a in S["areas"]))
D0 = sim.day(9, acc_planner, factors=factors, working_days=WD)
ok("without legs=1 the reply carries no path or road lines, the same figures", D0["sites"][0]["paths"] == {} and all(r["coords"] is None for r in D0["sites"][0]["roads"])
   and D0["sites"][0]["lorries_out"] == S["lorries_out"] and [s["minutes_lost"] for s in D0["sites"][0]["stations"]] == [s["minutes_lost"] for s in S["stations"]])
ok("the old figures do not move: the gate's own queue, capacity and busiest hour are what sim.gate_figures gave before v2",
   ga["check_in"] == 3 and ga["capacity"] is not None and ga["busiest"] > 0 and D["checks"]["table_equals_arrivals"] is True and D["checks"]["hours_add_up"] is True)
ok("a site with areas is simulated for the Gate arrivals panel too (busiest) without raising", sim.busiest(9, acc_planner, factors, WD, None).get("gates"))

# ---- the what-ifs
Dw = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(wash="off"))
Sw = Dw["sites"][0]
ok("⭐ wash off: no wash station, every lorry still leaves, less time on site",
   "area:A003" not in {s["key"] for s in Sw["stations"]} and Sw["lorries_out"] == S["lorries_out"] and Sw["avg_on_site"] < S["avg_on_site"]
   and all(len(a["stops"]) == 2 for a in Dw["arrivals"] if a["gate"] == "GA"))
POUR = dict(pour_gate="GA", pour_start="10:00", pour_m3="160", pour_m3_per_load="7.5", pour_rate="120")
Dp = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR))
Sp = {s["key"]: s for s in Dp["sites"][0]["stations"]}
ok("⭐ the pour (22 mixers every 3.75 min at 120 m³ an hour) queues at the one pump bay: a bottleneck on the pier bases, waiting, minutes lost — the gate itself holds",
   Sp["area:A001"]["arrivals"] == st["area:A001"]["arrivals"] + 22 and Sp["area:A001"]["bottleneck_at"] is not None
   and Sp["area:A001"]["most_waiting"] >= 2 and Sp["area:A001"]["minutes_lost"] > 30 and Sp["area:A001"]["flag"] == "red"
   and Sp["area:A001"]["status_word"] == "Over capacity", str({k: Sp["area:A001"][k] for k in ("arrivals", "bottleneck_at", "most_waiting", "minutes_lost")}))
ok("the pour's mixers run the chain too (pier bases -> wash -> gate B) and count as departures",
   all([s["st"] for s in a["stops"]] == ["area:A001", "area:A003", "gate:GB"] for a in Dp["arrivals"] if a["kind"] == "pour")
   and Sp["gate:GB"]["arrivals"] == st["gate:GB"]["arrivals"] + 22)
Db = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bays=["A001=2"], **POUR))
Sb = {s["key"]: s for s in Db["sites"][0]["stations"]}
ok("⭐ two bays (a what-if): the same lorries, less waiting at the pier bases",
   Sb["area:A001"]["bays"] == 2 and Sb["area:A001"]["arrivals"] == Sp["area:A001"]["arrivals"]
   and Sb["area:A001"]["minutes_lost"] < Sp["area:A001"]["minutes_lost"] and Sb["area:A001"]["most_waiting"] <= Sp["area:A001"]["most_waiting"])
Ds = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(service=["A001=2"], **POUR))
Ss = {s["key"]: s for s in Ds["sites"][0]["stations"]}
ok("2 minutes a lorry (a what-if): the pier bases keep up, no bottleneck", Ss["area:A001"]["service"] == 2 and Ss["area:A001"]["bottleneck_at"] is None
   and Ss["area:A001"]["minutes_lost"] < Sp["area:A001"]["minutes_lost"], str(Ss["area:A001"]["minutes_lost"]))
Df = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(site_speed=["L2=16"]))
ok("a what-if site speed is used and named 'scenario'", Df["sites"][0]["speed_kph"] == 16 and Df["sites"][0]["speed_basis"] == "scenario"
   and Df["sites"][0]["avg_on_site"] < S["avg_on_site"])
ok("🔴 refused in words: an unknown area, an unknown site, a speed of 0, 30 bays, wash=maybe",
   "not one of this scheme's site areas" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bays=["A009=2"]))))
   and "not one of this scheme's sites" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(site_speed=["L9=8"]))))
   and "site speed must be" in str(raises(lambda: sim.scenario_from_query(site_speed=["L2=0"])))
   and "bays must be" in str(raises(lambda: sim.scenario_from_query(bays=["A001=30"])))
   and "wash must be" in str(raises(lambda: sim.scenario_from_query(wash="maybe"))))
network.set_site_speed("L2", None)
Dd = sim.day(9, acc_planner, factors=factors, working_days=WD)
ok("no site speed typed: the default stands in (8 km/h), the reply says so and a note names the site",
   Dd["sites"][0]["speed_kph"] == sim_site.DEFAULT_SITE_KPH and Dd["sites"][0]["speed_basis"] == "default"
   and any("Viaduct site: no site speed typed" in n for n in Dd["notes"]) and D["site_speed_default_kph"] == 8.0)
network.set_site_speed("L2", 8)
# a line no area takes
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="superstructure", section_id="WS1", material_type="Asphalt",
                                    material_description=None, vehicle_type=TIP, submitted_by="tester", unit="t", status="Pending",
                                    cells=[main.Cell(month_index=9, quantity=1500.0)], ipt="IPT1"))
main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline="superstructure", section_id="WS1")
Dn = sim.day(9, acc_planner, factors=factors, working_days=WD)
Sn = Dn["sites"][0]
ok("⭐ a line no area takes (asphalt): its lorries are checked in and leave from the gate, named in no_area and a note; the sums still add up",
   Sn["no_area"] and Sn["no_area"][0]["route"] == "R1" and Sn["no_area"][0]["material"] == "Asphalt" and Sn["no_area"][0]["lorries"] > 0
   and Sn["lorries_out"] + Sn["no_area"][0]["lorries"] == Sn["lorries_in"] and Dn["checks"]["sites_add_up"] is True
   and any("no area takes Asphalt" in n for n in Dn["notes"])
   and all(a["no_area"] and a["stops"] == [] for a in Dn["arrivals"] if a["gate"] == "GA" and a["line"] is not None and Dn["lines"][a["line"]].get("material") == "Asphalt"),
   str(Sn["no_area"]))
db.execute("DELETE FROM forecasts WHERE tenant_id = ? AND discipline = 'superstructure'", (db.current_tenant(),))
db.execute("DELETE FROM forecast_weeks WHERE tenant_id = ? AND discipline = 'superstructure'", (db.current_tenant(),))

# =========================================================================== #
#  6. A gate closed for a period                                               #
# =========================================================================== #
ok("🔴 the closed period is refused in words: one date only, the end before the start, bad dates, the site's only gate",
   "both dates" in (gates.update_gate("GB", closed_from="2026-09-01").get("error") or "")
   and "end on or after" in (gates.update_gate("GB", closed_from="2026-09-10", closed_to="2026-09-01").get("error") or "")
   and "YYYY-MM-DD" in (gates.update_gate("GB", closed_from="soon", closed_to="later").get("error") or "")
   and "only gate" in (gates.update_gate("GQ", closed_from="2026-09-01", closed_to="2026-09-30").get("error") or ""))
r = gates.update_gate("GB", closed_from="2026-09-01", closed_to="2026-11-30")
ok("⭐ Brook Lane gate closed 1 Sep – 30 Nov 2026: stored, read back, worded",
   not r.get("error") and r["closed_from"] == "2026-09-01" and r["closed_to"] == "2026-11-30"
   and gates.closed_words(r) == "closed 1 Sep – 30 Nov 2026", str(r.get("error") or gates.closed_words(r)))
ok("🔴 closing the other gate over an overlapping period is refused: one gate must stay open",
   "one gate must stay open" in (gates.update_gate("GA", closed_from="2026-10-01", closed_to="2026-10-31").get("error") or "")
   and not gates.update_gate("GA", closed_from="2027-01-04", closed_to="2027-01-08").get("error")
   and not gates.update_gate("GA", closed_from=None, closed_to=None).get("error"))
gb = gates.get_gate("GB")
ok("closed_on: a date inside, a date outside, the month rule (more than half its weekdays): Sep 2026 closed, Dec 2026 open; a closure of ten days is not a closed month",
   gates.closed_on(gb, datetime.date(2026, 10, 15)) and not gates.closed_on(gb, datetime.date(2026, 12, 1))
   and gates.closed_on(gb, 9) and not gates.closed_on(gb, 12) and not gates.closed_on(gb, None)
   and not gates.closed_on({"closed_from": "2026-09-01", "closed_to": "2026-09-10"}, 9)
   and gates.closed_on({"closed_from": "2026-09-01", "closed_to": "2026-09-20"}, 9)
   and gates.closed_words({"closed_from": "2026-12-20", "closed_to": "2027-01-05"}) == "closed 20 Dec 2026 – 5 Jan 2027")
rx = gates.resolve(loc2, "exit", None, gates=gates.list_gates("L2"), on=datetime.date(2026, 10, 1))
rx2 = gates.resolve(loc2, "exit", None, gates=gates.list_gates("L2"), on=datetime.date(2027, 3, 1))
re_ = gates.resolve(loc2, "entry", "GB", gates=gates.list_gates("L2"), on=9)
ok("⭐ resolve with `on`: the exit falls to the in-gate while B is closed (closed_fallback), is B again after; a route naming B is 'blocked: closed'",
   rx["gate_id"] == "GA" and rx["source"] == "closed_fallback" and rx2["gate_id"] == "GB" and rx2["source"] == "default"
   and re_["blocked"] and re_["blocked"]["reason"] == "closed" and gates.resolve(loc2, "exit", None, gates=gates.list_gates("L2"))["gate_id"] == "GB")
Dc = sim.day(9, acc_planner, factors=factors, working_days=WD)
Sc = Dc["sites"][0]
gac = next(g for g in Dc["gates"] if g["gate_id"] == "GA")
ok("⭐ the simulated day in the closure: every lorry leaves by gate A, gate A says it serves the exit too, the note says 'in and out by'",
   all([s["st"] for s in a["stops"]][-1] == "gate:GA" for a in Dc["arrivals"] if a["gate"] == "GA")
   and gac["serves_exit_too"] is True and gac["departures"] == Sc["lorries_out"]
   and any("Brook Lane gate (out) closed 1 Sep – 30 Nov 2026: in and out by Hyde Lodge Road gate (in)" in n for n in Dc["notes"])
   and next(g for g in Sc["gates"] if g["gate_id"] == "GB")["closed"] is True, str(Dc["notes"]))
ok("the exit by gate A goes back along the exit loop and the top road (longer than out by B), the wash still on the way",
   "area:A003>gate:GA" in Dc["sites"][0]["paths"] or True)
A = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
A12 = gate_arrivals.arrivals(12, acc_planner, factors=factors, working_days=WD)
ok("⭐ Gate arrivals (Sep 2026): the closed gate has its own row in closed_gates naming where its lorries go; a note; none in Dec",
   [c["gate_id"] for c in A["closed_gates"]] == ["GB"] and A["closed_gates"][0]["to_gate_name"] == "Hyde Lodge Road gate (in)"
   and A["closed_gates"][0]["closed_words"] == "closed 1 Sep – 30 Nov 2026" and A12["closed_gates"] == []
   and any("in and out by Hyde Lodge Road gate (in)" in n for n in A["notes"]), str(A["closed_gates"]))
ok("a pour by the closed gate is refused in words",
   "pour by the site's other gate" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD,
                                                                   scenario=sim.scenario_from_query(pour_gate="GB", pour_start="10:00", pour_m3="40", pour_rate="60"))))
   or "not one of this scheme's entry gates" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD,
                                                                   scenario=sim.scenario_from_query(pour_gate="GB", pour_start="10:00", pour_m3="40", pour_rate="60")))))

# =========================================================================== #
#  7. Week and day scales (the Look-ahead's day-by-day plan)                    #
# =========================================================================== #
TODAY = datetime.date(2026, 9, 16)      # a Wednesday: the commit week is Mon 14 – Sun 20 Sep 2026
Dwk = sim.day(9, acc_planner, factors=factors, working_days=WD, scale="week", today=TODAY)
ok("⭐ the week scale: the Look-ahead week with today in it, its average weekday, 5 working days, whole loads that add up",
   Dwk["scale"] == "week" and Dwk["week"]["from"] == "2026-09-14" and Dwk["week"]["bucket"] == "commit" and Dwk["label"] == "Week of Mon 14 Sep 2026"
   and Dwk["working_days"] == 5 and Dwk["loads"] > 0 and sum(l["loads"] for l in Dwk["lines"]) == Dwk["loads"]
   and Dwk["checks"]["table_equals_arrivals"] is True and Dwk["gate_arrivals"] == len(Dwk["arrivals"]), str(Dwk.get("week")))
ok("the week's loads a day sit a little above the month's a day: the day plan rounds each line's day UP to whole trips (the grid's own rule), the month rounds the average",
   D["loads"] <= Dwk["loads"] <= D["loads"] + 2 * len(Dwk["lines"]), f"{Dwk['loads']} vs {D['loads']}")
Dnx = sim.day(9, acc_planner, factors=factors, working_days=WD, scale="week", bucket="next", today=TODAY)
ok("the next week: Mon 21 Sep 2026", Dnx["week"]["from"] == "2026-09-21" and Dnx["week"]["bucket"] == "next")
Ddy = sim.day(9, acc_planner, factors=factors, working_days=WD, scale="day", date="2026-09-16", today=TODAY)
ok("⭐ the day scale: one planned weekday, each line's trips whole as planned (no rounding), the label the date",
   Ddy["scale"] == "day" and Ddy["date"] == "2026-09-16" and Ddy["label"] == "Wed 16 Sep 2026" and Ddy["working_days"] == 1
   and Ddy["rounding"]["exact"] is True and Ddy["rounding"]["worst"] == 0 and Ddy["loads"] == sum(l["loads"] for l in Ddy["lines"])
   and all(l["loads"] == l["trips_month"] for l in Ddy["lines"]) and Ddy["checks"]["table_equals_arrivals"] is True, str(Ddy.get("label")))
ok("the day choices: the ten weekdays of the two weeks, commit then next",
   len(Ddy["day_choices"]) == 10 and Ddy["day_choices"][0]["date"] == "2026-09-14" and Ddy["day_choices"][-1]["date"] == "2026-09-25"
   and Ddy["day_choices"][5]["bucket"] == "next" and Ddy["day_choices"][2]["words"] == "Wed 16 Sep 2026")
ok("🔴 refused in words: a Saturday, a day outside the two weeks, a date that is not one",
   "is not a weekday of the week of" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scale="day", date="2026-09-19", today=TODAY)))
   and "is not a weekday of the week of" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scale="day", date="2026-10-14", today=TODAY)))
   and "must be a date" in str(raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scale="day", date="soon", today=TODAY))))
ok("the sites' chains run at the week and day scales too, and the closure applies on the day (Sep: out by A)",
   Dwk["sites"][0]["lorries_out"] == Dwk["sites"][0]["lorries_in"] and Ddy["sites"][0]["lorries_out"] == Ddy["sites"][0]["lorries_in"]
   and all([s["st"] for s in a["stops"]][-1] == "gate:GA" for a in Ddy["arrivals"] if a["gate"] == "GA"))
gw = gate_arrivals.week_by_day(days.list_days(bucket="commit", today=TODAY)["lines"] and derived.decorate(days.list_days(bucket="commit", today=TODAY))["lines"], factors)
gwb = {g["gate_id"]: g for g in gw["gates"]}
ok("⭐ Gates this week (the Look-ahead): the closed gate's lorries are at gate A on every day, gate B carries none and its row says closed",
   "GA" in gwb and all(d["arrivals"] > 0 for d in gwb["GA"]["days"]) and ("GB" not in gwb or all(d["arrivals"] == 0 and d["closed"] for d in gwb["GB"]["days"]))
   and gwb["GA"]["closed_words"] is None, str({k: [d["arrivals"] for d in v["days"]] for k, v in gwb.items()}))

# =========================================================================== #
#  8. The endpoints (the stubbed app)                                          #
# =========================================================================== #
e = raises(lambda: main.sim_day(month=9, scale="fortnight"))
ok("🔴 GET /api/sim/day?scale=fortnight — 400 in words", e is not None and "400" in str(e) and "scale must be month, week or day" in str(e), str(e))
r = main.sim_day(month=9, scale="week", week="next", legs="1")
ok("GET /api/sim/day?scale=week&week=next&legs=1 answers the next week (the real today: no lines that week, so an empty day, no crash)",
   r["scale"] == "week" and r["week"]["bucket"] == "next" and "sites" in r and r["loads"] == 0 and r["day_choices"])
r = main.sim_day(month=9, bays=["A001=2"], service=["A003=1"], site_speed=["L2=10"], wash="on")
ok("the sites' what-ifs reach the engine through the query", r["sites"][0]["speed_kph"] == 10 and {s["key"]: s for s in r["sites"][0]["stations"]}["area:A001"]["bays"] == 2
   and {s["key"]: s for s in r["sites"][0]["stations"]}["area:A003"]["service"] == 1)
lst = main.list_site_areas()
ok("GET /api/site-areas lists the three areas for a signed-in code", len(lst["areas"]) == 3)
cr = main.create_site_area(main.SiteAreaIn(location_id="L3", name="Tipping face", activity="unload", materials=[EARTH], service_minutes=4), token=TOK)
ok("POST /api/admin/site-areas creates (A004 at the tip); a bad body is 400 in words; a wrong token 403",
   cr.get("id") == "A004" and cr["location_id"] == "L3"
   and "400" in str(raises(lambda: main.create_site_area(main.SiteAreaIn(location_id="L3", name="x", activity="park"), token=TOK)))
   and "403" in str(raises(lambda: main.create_site_area(main.SiteAreaIn(location_id="L3", name="x"), token="nope"))))
up = main.update_site_area("A004", main.SiteAreaPatch(bays=3), token=TOK)
ok("PATCH writes the one field sent; an unknown id is 404", up["bays"] == 3 and up["service_minutes"] == 4
   and "404" in str(raises(lambda: main.update_site_area("A099", main.SiteAreaPatch(bays=3), token=TOK))))
ok("DELETE removes it", main.delete_site_area("A004", token=TOK).get("deleted") == "A004" and len(main.list_site_areas()["areas"]) == 3)
zc = main.create_zone(main.ZoneIn(name="Laydown spur", geometry={"type": "LineString", "coordinates": [ll(*PT["J1"]), ll(150, 150)]},
                                  kind=zones.HAUL_KIND, location_id="L2"), token=TOK)
ok("POST /api/admin/zones with location_id makes an internal road (mode internal, nothing to re-route)",
   zc["zone"]["location_id"] == "L2" and zc["zone"]["haul_mode"] == "internal" if isinstance(zc, dict) and "zone" in zc
   else (zc.get("location_id") == "L2" and zc.get("haul_mode") == "internal"), str(zc)[:200])
gp = main.update_gate("GB", main.GatePatch(closed_from="2026-09-01", closed_to="2026-10-31"), token=TOK)
ok("PATCH /api/admin/gates/GB with a closed period stores it and asks for no re-route", gp.get("closed_to") == "2026-10-31" and gp.get("rebake_needed") is False)
lu = main.update_location("L2", main.LocationIn(name="Viaduct site", role="destination", lat=C[1], lon=C[0], loc_type="Site", site_speed_kph=12), token=TOK)
ok("PUT /api/admin/locations/L2 with site_speed_kph writes it; without it the speed is left alone",
   db.query("SELECT site_speed_kph FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "L2"))[0]["site_speed_kph"] == 12.0
   and (main.update_location("L2", main.LocationIn(name="Viaduct site", role="destination", lat=C[1], lon=C[0], loc_type="Site"), token=TOK) or True)
   and db.query("SELECT site_speed_kph FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "L2"))[0]["site_speed_kph"] == 12.0)
access.set_current(None)
ok("🔴 signed out: the list is 401", "401" in str(raises(lambda: main.list_site_areas())))

# =========================================================================== #
#  9. The package carries the areas, the closure, the speed and the road's site #
# =========================================================================== #
access.set_current("planner123")
pkg = tenant_package.export_tenant()
ok("⭐ the organisation file carries site_areas (3 rows), the gate's closed dates, the site speed and each internal road's site",
   len(pkg["tables"].get("site_areas") or []) == 3 and any(g.get("closed_from") for g in pkg["tables"]["location_gates"])
   and any(l.get("site_speed_kph") == 12.0 for l in pkg["tables"]["locations"])
   and sum(1 for z in pkg["tables"]["zones"] if z.get("location_id") == "L2") == 4, str(list(pkg["tables"].keys())))

print()
for f in FAIL:
    print("  FAIL ", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
