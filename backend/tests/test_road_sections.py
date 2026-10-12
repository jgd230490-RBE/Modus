"""
Shared road sections (public map review §2.2d, option A, the server half) — 12 Oct 2026.

Same harness shape as test_phase5a.py / test_modus.py: a scratch SQLite database, no
network, `fastapi` / `flexpolyline` stubbed so main.py imports and its endpoint bodies run
as plain Python.

WHAT THIS PROVES
----------------
  * the vertex-run index on synthetic polylines: two routes sharing 5 of 9 vertices give
    ONE run of 5 with both ids and the haversine length; a third route that joins for
    part splits the stretch into two runs with the right owner sets; a vertex 3e-6
    degrees off still matches (the snap) and one 5e-5 off does not; the return leg is
    indexed separately;
  * the month read: movements on a run = the two routes' Approved LOADS (the public map
    bar's fractional figure, from the same month-kpis payload the bar reads) ÷ the planning
    block's working days, equal to the sum of the per-route figures and NEVER doubled, and
    never Σ ceil per line (the breaking case: a 10.4-load line and a 0.5-load line);
    vehicles = Σ ceil per line, the bar's rule; CO2e apportioned by length over the route's
    TWO-WAY length (loaded + baked return), so a run carries the carbon emitted on it, not
    the whole trip's; a failed carbon read answers with co2_error and never raises;
    team NAMES, never an id; a month with no volume gives empty runs and a note;
  * the index is rebuilt by network._upsert_geom (alt 0 only), by clear_geometry and by
    the package import; the package carries the table; the public endpoint sits behind the
    map scope and the admin endpoints behind the token.

WHAT THIS DOES NOT PROVE
------------------------
  * No Postgres branch runs (the table is a plain CREATE on both backends).
  * The HTTP transport is stubbed: endpoint BODIES run, the gate middleware does not —
    http_smoke.py drives the real app for the 401 / 403 and the empty demo answer.
  * Nothing about the live tenant's real HERE vertices: the fixture is synthetic.

Run:  python backend/tests/test_road_sections.py
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

# --------------------------------------------------------------------------- #
#  Stubs (the same shape every other harness uses)                             #
# --------------------------------------------------------------------------- #
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

TMP = tempfile.mkdtemp(prefix="wayscope_sections_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import costlines  # noqa: E402
import tenant_package  # noqa: E402
import road_sections  # noqa: E402
import gate  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    config.invalidate()


def boot():
    reset_db()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate()


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def tables():
    return {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}


def cols(table):
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return {r[1]: r for r in cur.fetchall()}
    finally:
        conn.close()


PROFILE = network.DEFAULT_PROFILE          # "Artic Tipper (44t)" — payload 29 t in the seed
BAL = "Large aggregate / ballast"
TEAM_ID = re.compile(r"\bIPT ?[1-6]\b")

# --------------------------------------------------------------------------- #
#  Synthetic polylines. A runs east along lat 52.55 in 0.002° steps (nine vertices,   #
#  ~136 m apart); B comes in from the north, shares A's vertices 2..6, leaves south;  #
#  C joins for vertices 4..6 only.                                                   #
# --------------------------------------------------------------------------- #
def V(i, lat=52.55):
    return [round(-0.95 + 0.002 * i, 6), lat]


A = [V(i) for i in range(9)]
B = [[V(2)[0], 52.56], [V(2)[0], 52.555]] + [V(i) for i in range(2, 7)] + [[V(6)[0], 52.545], [V(6)[0], 52.54]]
C = [[V(4)[0], 52.565], [V(4)[0], 52.56]] + [V(i) for i in range(4, 7)] + [[V(7)[0], 52.56]]
A_RET = list(reversed(A))
B_RET = [[V(7)[0], 52.54]] + [V(7), V(6), V(5)] + [[V(5)[0], 52.56]]      # shares 3 on the way back


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def plen(pts):
    return sum(hav(pts[i - 1], pts[i]) for i in range(1, len(pts)))


# =========================================================================== #
#  1. The index on polylines alone (no database)                               #
# =========================================================================== #
runs, st = road_sections.build_runs({"R001": A, "R002": B})
ok("1. two routes sharing 5 of 9 vertices give ONE run", len(runs) == 1, str(len(runs)))
r = runs[0]
ok("1. ...of five vertices", r["vertices"] == 5 and len(r["geometry"]) == 5, str(r.get("vertices")))
ok("1. ...owned by both routes, sorted", r["routes"] == ["R001", "R002"], str(r["routes"]))
ok("1. ...with the haversine length of A's vertices 2..6", abs(r["length_km"] - round(plen(A[2:7]), 3)) < 1e-6,
   f"{r['length_km']} vs {plen(A[2:7])}")
ok("1. ...and ~0.54 km, i.e. four ~136 m steps along 52.55 N", 0.53 < r["length_km"] < 0.55, str(r["length_km"]))
ok("1. ...first and last vertex are A's 2 and 6", r["first"] == A[2] and r["last"] == A[6], f"{r['first']} {r['last']}")
ok("1. ...the run's polyline is the shared vertices in walking order", r["geometry"] == A[2:7])
ok("1. stats: 2 routes indexed, 13 distinct vertices, 5 shared, 1 run",
   st == {"routes_indexed": 2, "vertices_total": 13, "vertices_shared": 5, "runs": 1}, str(st))
ok("1. the run id is stable across rebuilds of the same geometry",
   road_sections.build_runs({"R001": A, "R002": B})[0][0]["id"] == r["id"] and r["id"].startswith("S"))
ok("1. a lone route gives no run", road_sections.build_runs({"R001": A}) == ([], {"routes_indexed": 1, "vertices_total": 9,
                                                                                "vertices_shared": 0, "runs": 0}))
ok("1. two routes with nothing in common give no run",
   road_sections.build_runs({"R001": A, "R009": [[0.5, 51.0], [0.51, 51.0], [0.52, 51.0]]})[0] == [])
ok("1. a single shared vertex (a crossing) is not a run",
   road_sections.build_runs({"R001": A, "R009": [[V(4)[0], 52.56], V(4), [V(4)[0], 52.54]]})[0] == [])

# three routes: A+B share 2..6, C joins for 4..6 -> two runs with the right owner sets
runs3, st3 = road_sections.build_runs({"R001": A, "R002": B, "R003": C})
ok("1. three routes where the third joins for part give TWO runs", len(runs3) == 2, str([(x["routes"], x["vertices"]) for x in runs3]))
by_owner = {tuple(x["routes"]): x for x in runs3}
ok("1. ...one owned by A+B+C over vertices 4..6", by_owner.get(("R001", "R002", "R003"), {}).get("geometry") == A[4:7],
   str(by_owner.get(("R001", "R002", "R003"), {}).get("geometry")))
ok("1. ...one owned by A+B over vertices 2..4 — ownership is per SEGMENT, so the boundary vertex 4 is in both runs",
   by_owner.get(("R001", "R002"), {}).get("geometry") == A[2:5],
   str(by_owner.get(("R001", "R002"), {}).get("geometry")))
ok("1. ⭐ ...and the two runs' lengths add up to the A+B run's length: no road is lost between them",
   abs(sum(x["length_km"] for x in runs3) - r["length_km"]) < 2e-3,
   f"{[x['length_km'] for x in runs3]} vs {r['length_km']}")
ok("1. ...and the stats count 5 shared vertices (the owner split does not double them)", st3["vertices_shared"] == 5
   and st3["routes_indexed"] == 3 and st3["runs"] == 2, str(st3))
ok("1. runs come longest first", runs3[0]["length_km"] >= runs3[1]["length_km"])

# the snap: 3e-6 off still matches; 5e-5 off is another vertex
B_near = [p[:] for p in B]
B_near[3] = [B[3][0] + 3e-6, B[3][1] - 3e-6]            # B's copy of A's vertex 3, nudged
rn, sn = road_sections.build_runs({"R001": A, "R002": B_near})
ok("1. ⭐ a vertex 3e-6° off still matches: still ONE run of five", len(rn) == 1 and rn[0]["vertices"] == 5,
   str([(x["routes"], x["vertices"]) for x in rn]))
ok("1. ...and the stats still count 13 vertices, not 14", sn["vertices_total"] == 13, str(sn))
B_far = [p[:] for p in B]
B_far[3] = [B[3][0] + 5e-5, B[3][1]]
rf, sf = road_sections.build_runs({"R001": A, "R002": B_far})
ok("1. a vertex 5e-5° off is a different vertex: the run breaks to the three past it (the single before it is no run)",
   len(rf) == 1 and rf[0]["vertices"] == 3 and rf[0]["geometry"] == A[4:7] and sf["vertices_total"] == 14,
   str([(x["routes"], x["vertices"]) for x in rf]) + " " + str(sf))
# a cell boundary between two near points must not defeat the snap
P = [[-0.950004, 52.55], [-0.948, 52.55], [-0.946, 52.55]]
Q = [[-0.949997, 52.55], [-0.948, 52.55], [-0.946, 52.55]]          # 7e-6 apart, across the 1e-5 grid line at -0.95
rq, _ = road_sections.build_runs({"R001": P, "R002": Q})
ok("1. two points 7e-6 apart on either side of a snap-grid line are one vertex", len(rq) == 1 and rq[0]["vertices"] == 3,
   str([(x["routes"], x["vertices"]) for x in rq]))
ok("1. the walk direction does not matter: B reversed gives the same run",
   road_sections.build_runs({"R001": A, "R002": list(reversed(B))})[0][0]["vertices"] == 5)
ok("1. a repeated consecutive vertex (a gate approach that doubles back) does not break a run",
   road_sections.build_runs({"R001": A, "R002": B[:4] + [B[3]] + B[4:]})[0][0]["vertices"] == 5)
ok("1. coords_of reads the bake's plain list AND a GeoJSON LineString",
   road_sections.coords_of(json.dumps(A)) == A and road_sections.coords_of(json.dumps({"type": "LineString", "coordinates": A})) == A
   and road_sections.coords_of("not json") == [] and road_sections.coords_of(None) == [])
ok("1. haversine: one degree of latitude is ~111.2 km", abs(road_sections.haversine_km([0, 0], [0, 1]) - 111.195) < 0.01)

# 12 Oct 2026 (the review and fix pass): every shared SEGMENT is in exactly one run. Until then a run was a walk
# sequence: a route that doubled back over a shared stretch made a run with a U-turn (2.738 km where the other owner
# drives 2.054), so that owner's CO2e share came out at 1.33 × its month figure; two routes that both looped made two
# runs over one segment, counted twice.


def _owner_km(runs_):
    km = {}
    for x in runs_:
        for rid in x["routes"]:
            km[rid] = km.get(rid, 0.0) + x["length_km"]
    return km


def _segments(runs_):
    segs = []
    for x in runs_:
        g = [tuple(p) for p in x["geometry"]]
        segs += [tuple(sorted((g[i - 1], g[i]))) for i in range(1, len(g))]
    return segs


W = [V(i) for i in range(5)]
UA = [W[0], W[1], W[2], W[3], W[2], [W[2][0], 52.54]]                 # A drives 0..3, turns back to 2, leaves south
UB = [W[0], W[1], W[2], W[3]]
ru, su = road_sections.build_runs({"R001": UA, "R002": UB})
ok("1. 🔴 a route that doubles back over the shared stretch gives ONE run with no U-turn in it: vertices 0..3",
   len(ru) == 1 and ru[0]["geometry"] == W[0:4] and ru[0]["vertices"] == 4,
   str([(x["routes"], x["vertices"]) for x in ru]))
ok("1. ⭐ ...so no owner's runs add up to more than its own length (B: the run is all of B, never 1.33 × it)",
   all(km <= plen({"R001": UA, "R002": UB}[rid]) + 1e-3 for rid, km in _owner_km(ru).items())
   and abs(_owner_km(ru)["R002"] - plen(UB)) < 2e-3, str(_owner_km(ru)))
X_, Y_ = [W[4][0], 52.56], [W[2][0], 52.54]
LPA = [W[1], W[2], W[3], W[4], X_, W[4], [V(5)[0], 52.55], [V(6)[0], 52.55]]          # A loops out to X and back
LPB = [W[1], W[2], W[3], Y_, W[3], W[4], [V(5)[0], 52.55], [V(6)[0], 52.55]]          # B loops out to Y and back
rl_, sl_ = road_sections.build_runs({"R001": LPA, "R002": LPB})
ok("1. 🔴 two routes that both loop: no segment is in two runs (segment 3-4 used to be counted twice)",
   len(_segments(rl_)) == len(set(_segments(rl_))), str([x["geometry"] for x in rl_]))
ok("1. ...and the stretch both drive, 1..6, is one run (the chains either side of A's loop are joined)",
   len(rl_) == 1 and rl_[0]["geometry"] == [W[1], W[2], W[3], W[4], [V(5)[0], 52.55], [V(6)[0], 52.55]],
   str([(x["routes"], x["vertices"]) for x in rl_]))
ok("1. ...and each owner's runs add up to no more than its own length",
   all(km <= plen({"R001": LPA, "R002": LPB}[rid]) + 1e-3 for rid, km in _owner_km(rl_).items()), str(_owner_km(rl_)))
ok("1. ...over every fixture above too: no segment twice, no owner over its length",
   all(len(_segments(rr)) == len(set(_segments(rr))) for rr in (runs, runs3, rn, rf, ru, rl_))
   and all(km <= plen({"R001": A, "R002": B, "R003": C}[rid]) + 1e-3 for rid, km in _owner_km(runs3).items()))
ok("1. run ids are unique within a leg (the id hashes every vertex, not only the two ends)",
   len({x["id"] for x in runs3}) == len(runs3) and len({x["id"] for x in rl_}) == len(rl_))
# the documented limit, pinned as it is: an extra vertex on one route between two shared vertices loses that stretch
EA = [W[1], W[2], [round((W[2][0] + W[3][0]) / 2, 6), 52.55], W[3], W[4]]
re_, _ = road_sections.build_runs({"R001": EA, "R002": [W[1], W[2], W[3], W[4]]})
ok("1. the known limit (different vertex sets): A with an extra vertex between 2 and 3 gives runs 1-2 and 3-4, and 2-3 is lost",
   sorted(x["geometry"] for x in re_) == sorted([[W[1], W[2]], [W[3], W[4]]])
   and "stretch 2-3 is B's alone and is lost" in read("backend/road_sections.py"), str([x["geometry"] for x in re_]))
r1v, s1v = road_sections.build_runs({"R001": A, "R009": [A[3], A[3]]})
ok("1. a 'route' of one repeated point has no segment: not indexed, owns no vertex, makes no run",
   r1v == [] and s1v == {"routes_indexed": 1, "vertices_total": 9, "vertices_shared": 0, "runs": 0}, str(s1v))

# =========================================================================== #
#  2. Schema, registry, package order                                          #
# =========================================================================== #
boot()
ok("2. route_sections is created", "route_sections" in tables())
sc = cols("route_sections")
for c in ("tenant_id", "section_id", "leg", "routes_json", "geometry_json", "length_km", "built_at"):
    ok(f"2. route_sections has {c}", c in sc)
ok("2. tenant_id is the FIRST primary key column", sc["tenant_id"][5] == 1, str(sc["tenant_id"][5]))
ok("2. route_sections is registered as tenanted", "route_sections" in db.TENANTED_TABLES)
ok("2. ...with a primary key for the Postgres path", db._TENANT_PK.get("route_sections") == "(tenant_id, leg, section_id)")
ok("2. ...in the package ORDER exactly once, after route_geometry",
   tenant_package.ORDER.count("route_sections") == 1
   and tenant_package.ORDER.index("route_sections") > tenant_package.ORDER.index("route_geometry"))
ok("2. ...and in the tenant audit's own registry", '"route_sections"' in read("backend/tests/test_tenant_audit.py"))
ok("2. an empty tenant indexes to nothing without error",
   road_sections.rebuild()["runs"] == 0 and road_sections.status()["stale"] is False)
ok("2. ...and the month read on an empty tenant is empty with a note",
   road_sections.road_load(10)["runs"] == [] and road_sections.road_load(10)["notes"] == ["No approved volume in this month."])

# =========================================================================== #
#  3. A baked network: the stored index                                        #
# =========================================================================== #
q1 = network.create_location("Pit A", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=[BAL])
q2 = network.create_location("Pit B", "origin", lat=52.56, lon=-0.946, loc_type="Quarry", supplies=[BAL])
q3 = network.create_location("Pit C", "origin", lat=52.565, lon=-0.942, loc_type="Quarry", supplies=[BAL])
d1 = network.create_location("Yard D", "destination", lat=52.55, lon=-0.934, loc_type="Compound", receives=[BAL])
rA = network.create_route(q1["id"], d1["id"], material_category=BAL, route_id="R001", ipt="IPT1")["id"]
rB = network.create_route(q2["id"], d1["id"], material_category=BAL, route_id="R002", ipt="IPT2")["id"]
rC = network.create_route(q3["id"], d1["id"], material_category=BAL, route_id="R003", ipt="IPT4")["id"]
tenant_package.import_rows("ipts", [
    {"id": "IPT1", "label": "North Team", "manager": None, "active": True, "merged_into": None},
    {"id": "IPT2", "label": "Central Team", "manager": None, "active": True, "merged_into": None}])
if hasattr(taxonomy, "invalidate"):
    taxonomy.invalidate()          # the team labels are read fresh below


def add_geom(rid, pts, leg="loaded", profile=PROFILE, alt=0, dur=1.0):
    db.execute(
        "INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
        "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), rid, profile, leg, alt, json.dumps(pts), round(plen(pts), 3), dur, "2026-10-12T00:00:00Z"))


add_geom(rA, A); add_geom(rB, B)
add_geom(rA, A_RET, leg="return"); add_geom(rB, B_RET, leg="return")
add_geom(rA, [[-0.95, 52.55], [-0.934, 52.55]], alt=1)             # an alternative: never indexed
st = road_sections.rebuild()
ok("3. rebuild indexes the two routes on the loaded leg", st["routes_indexed"] == 2 and st["profile"] == PROFILE, str(st))
ok("3. ...one loaded run, five shared vertices", st["runs"] == 1 and st["vertices_shared"] == 5, str(st))
ok("3. ⭐ the return leg is indexed SEPARATELY: its own run of three shared vertices",
   st["legs"]["return"]["runs"] == 1 and st["legs"]["return"]["vertices_shared"] == 3
   and st["legs"]["return"]["routes_indexed"] == 2, str(st["legs"]["return"]))
ok("3. ...and the loaded leg's figures are untouched by it", st["legs"]["loaded"]["vertices_shared"] == 5)
ok("3. the index is not stale after a rebuild", st["stale"] is False and st["built_at"])
rows = db.query("SELECT * FROM route_sections WHERE tenant_id = ? ORDER BY leg", (db.current_tenant(),))
ok("3. two rows stored, one per leg, stamped with the tenant", len(rows) == 2 and {r["leg"] for r in rows} == {"loaded", "return"}
   and all(r["tenant_id"] == db.current_tenant() for r in rows))
loaded_row = [r for r in rows if r["leg"] == "loaded"][0]
ok("3. the stored row carries the owner set and the polyline as JSON",
   json.loads(loaded_row["routes_json"]) == ["R001", "R002"] and json.loads(loaded_row["geometry_json"]) == A[2:7]
   and abs(loaded_row["length_km"] - round(plen(A[2:7]), 3)) < 1e-6)
stored = road_sections.stored_runs("loaded")
ok("3. stored_runs reads it back, longest first, with first/last", len(stored) == 1 and stored[0]["first"] == A[2]
   and stored[0]["last"] == A[6] and stored[0]["vertices"] == 5)
ok("3. the alternative (alt 1) was not indexed: a straight line sharing both ends would otherwise add a run",
   len(stored) == 1 and stored[0]["routes"] == ["R001", "R002"])
db.execute("DELETE FROM route_sections WHERE tenant_id = ?", (db.current_tenant(),))
ok("3. status reports STALE when the stored rows disagree with the geometry", road_sections.status()["stale"] is True)
road_sections.rebuild()

# the profile fallback: only another profile baked -> that profile
ok("3. index_profile is the network default while it has geometry", road_sections.index_profile() == PROFILE)
db.execute("UPDATE route_geometry SET vehicle_profile = ? WHERE tenant_id = ?", ("Rigid 8-wheeler (32t)", db.current_tenant()))
ok("3. ...and falls back to the only baked profile when the default has none (the map's own rule)",
   road_sections.index_profile() == "Rigid 8-wheeler (32t)" and road_sections.rebuild()["routes_indexed"] == 2)
db.execute("UPDATE route_geometry SET vehicle_profile = ? WHERE tenant_id = ?", (PROFILE, db.current_tenant()))
road_sections.rebuild()

# =========================================================================== #
#  4. Rebuilt by the bake path, the clear and the promote                      #
# =========================================================================== #
before = len(road_sections.stored_runs("loaded"))
network._upsert_geom(rC, PROFILE, json.dumps(C), round(plen(C), 3), 1.0, None, leg="loaded", alt_index=0)
after = road_sections.stored_runs("loaded")
ok("4. ⭐ _upsert_geom of a primary geometry rebuilds the index without being asked: 1 run -> 2",
   before == 1 and len(after) == 2, f"{before} -> {len(after)}")
owners = sorted(tuple(x["routes"]) for x in after)
ok("4. ...with the owner sets A+B and A+B+C", owners == [("R001", "R002"), ("R001", "R002", "R003")], str(owners))
network._upsert_geom(rC, PROFILE, json.dumps([[-0.942, 52.565], [-0.934, 52.55]]), 1.0, 1.0, None, leg="loaded", alt_index=2)
ok("4. an alternative's upsert (alt 2) does not change the index", len(road_sections.stored_runs("loaded")) == 2)
ok("4. the upsert source calls the rebuild hook for alt 0 only",
   "if int(alt_index or 0) == 0:\n        road_sections._rebuild_quietly(" in read("backend/network.py"))
network.clear_geometry(route_id=rC)
ok("4. clear_geometry rebuilds: back to one run", len(road_sections.stored_runs("loaded")) == 1
   and road_sections.stored_runs("loaded")[0]["routes"] == ["R001", "R002"])
src_net = read("backend/network.py")
ok("4. delete_route, clear_routes and promote_alternative also rebuild (source)",
   src_net.count("road_sections._rebuild_quietly(") == 5)
ok("4. the hook never raises into the bake: it prints and returns None",
   "def _rebuild_quietly(where):" in read("backend/road_sections.py")
   and "except Exception as e:\n        print(f\"road_sections: index not rebuilt after {where}: {e}\")" in read("backend/road_sections.py"))
# re-add C for the month read below
network._upsert_geom(rC, PROFILE, json.dumps(C), round(plen(C), 3), 1.0, None, leg="loaded", alt_index=0)

# 12 Oct 2026 (the review and fix pass): a bake batch rebuilds the index ONCE, not after every leg it upserts
_real_rebuild = road_sections.rebuild
_calls = []
road_sections.rebuild = lambda profile=None: (_calls.append(1), _real_rebuild(profile))[1]
try:
    with road_sections.batched("test"):
        network._upsert_geom(rC, PROFILE, json.dumps(C), round(plen(C), 3), 1.0, None, leg="loaded", alt_index=0)
        network._upsert_geom(rA, PROFILE, json.dumps(A), round(plen(A), 3), 1.0, None, leg="loaded", alt_index=0)
        with road_sections.batched("nested"):
            network._upsert_geom(rB, PROFILE, json.dumps(B), round(plen(B), 3), 1.0, None, leg="loaded", alt_index=0)
        ok("4. inside batched() an upsert marks the index dirty and does not rebuild", _calls == [], str(_calls))
    ok("4. ⭐ ...and the block's end rebuilds ONCE for three upserts (a nested block defers to the outer one)",
       _calls == [1], str(_calls))
    _calls.clear()
    with road_sections.batched("nothing"):
        pass
    ok("4. a block that changed nothing does not rebuild", _calls == [])
    # bake_batch end to end, HERE stubbed: four legs upserted, one rebuild
    _real_conf, _real_leg = network.here_routing.configured, network._bake_leg

    def _fake_leg(r, o, d, profile, leg, factors, alternatives=None, avoid=None, zone_tag=None, gates_by_loc=None):
        pts = {"R001": A, "R002": B, "R003": C}.get(r["id"], C)
        pts = pts if leg == "loaded" else list(reversed(pts))
        network._upsert_geom(r["id"], profile, json.dumps(pts), round(plen(pts), 3), 1.0, None, leg=leg, alt_index=0)
        return 1, None
    network.here_routing.configured = lambda: True
    network._bake_leg = _fake_leg
    try:
        _out = network.bake_batch(profile="Test profile (no geometry yet)", limit=4)
        ok("4. ⭐ bake_batch over four legs rebuilds the index ONCE (it used to be once per primary upsert)",
           _out.get("baked") == 4 and _calls == [1], f"{_out.get('baked')} {_calls}")
        _calls.clear()
        network.bake_route("R003", profile="Test profile (no geometry yet)")
        ok("4. bake_route over both legs rebuilds once too", _calls == [1], str(_calls))
    finally:
        network.here_routing.configured, network._bake_leg = _real_conf, _real_leg
        db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND vehicle_profile = ?",
                   (db.current_tenant(), "Test profile (no geometry yet)"))
finally:
    road_sections.rebuild = _real_rebuild
road_sections.rebuild()
ok("4. bake_batch and bake_route carry the rebuild-once decorator (source)",
   '@road_sections.rebuild_once("bake batch")\ndef bake_batch(' in read("backend/network.py")
   and '@road_sections.rebuild_once("route bake")' in read("backend/network.py"))
# the rebuild is one transaction: a failure part-way leaves the previous index whole
_before = sorted((x["id"], x["leg"]) for leg in road_sections.LEGS for x in road_sections.stored_runs(leg))
_real_compute = road_sections.compute


def _dup_compute(profile=None):
    b = _real_compute(profile)
    rr = b["legs"]["loaded"]["runs"]
    if rr:
        rr.append(dict(rr[0]))          # the same id twice: the INSERT collides on the primary key
    return b


road_sections.compute = _dup_compute
try:
    road_sections.rebuild()
    ok("4. a rebuild whose INSERT fails raises (here: a duplicate id)", False)
except Exception:
    ok("4. a rebuild whose INSERT fails raises (here: a duplicate id)", True)
finally:
    road_sections.compute = _real_compute
_after = sorted((x["id"], x["leg"]) for leg in road_sections.LEGS for x in road_sections.stored_runs(leg))
ok("4. ⭐ ...and the stored index is the previous one, whole: the DELETE was rolled back with the INSERTs",
   _after == _before and len(_before) == 3, f"{_before} vs {_after}")
ok("4. the rebuild writes through db.execute_atomic (one connection, one commit)",
   "db.execute_atomic([" in read("backend/road_sections.py") and "def execute_atomic(steps):" in read("backend/db.py"))

# =========================================================================== #
#  5. The month read                                                           #
# =========================================================================== #
factors = conversions.load_factors()
WD = float(factors["planning"]["working_days_per_month"])
PAYLOAD = float(factors["vehicles"][PROFILE]["payload_t"])
M = 10


def add_line(fid, rid, qty, ipt, month=M, status="Approved", section=""):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), fid, rid, month, "superstructure", section, qty, "t", BAL, "Type 1", PROFILE,
                "test", status, None, ipt))


add_line("F1", rA, 100 * PAYLOAD, "IPT1")           # 100 trips
add_line("F2", rB, 50 * PAYLOAD, "IPT2")            # 50 trips
add_line("F3", rA, 10 * PAYLOAD, "IPT1", month=11)  # another month: must not count in October
add_line("F4", rB, 999 * PAYLOAD, "IPT2", status="Pending", section="WS9")   # not approved: must not count

cl = costlines.lines(acc={"role": "planner"}, from_month=M, to_month=M, status="Approved", factors=factors)
per_route = {}
for l in cl["lines"]:
    pr = per_route.setdefault(l["route_id"], {"trips": 0, "vehicles": 0, "co2_t": 0.0})
    pr["trips"] += l["trips"]; pr["vehicles"] += (l["vehicles"] or 0); pr["co2_t"] += (l["co2_t"] or 0.0)
ok("5. fixture: costlines gives A 100 trips and B 50 in October (ceil(t / payload)), both baked with CO2e",
   per_route.get("R001", {}).get("trips") == 100 and per_route.get("R002", {}).get("trips") == 50
   and per_route["R001"]["co2_t"] > 0 and per_route["R002"]["co2_t"] > 0, str(per_route))
ok("5. fixture: the working days come from the planning block, not a literal", WD == cl["working_days_per_month"] and WD > 0)
# the bar's payload for the same month: fractional loads, ceil-per-line fleet, the same co2 — what the map bar reads
P10 = main.public_month_kpis(month=M)
bar = {}
for l in P10["lines"]:
    b = bar.setdefault(l["route_id"], {"loads": 0.0, "fleet": 0, "co2_t": 0.0})
    b["loads"] += l["vehicle_loads"]; b["co2_t"] += (l["co2_t"] or 0.0)
    if l["trips_per_vehicle_day"]:
        b["fleet"] += math.ceil((l["vehicle_loads"] / WD) / l["trips_per_vehicle_day"])
ok("5. fixture: the bar's payload gives A 100 loads and B 50 (whole numbers here, so equal to costlines' trips) and the same carbon",
   bar["R001"]["loads"] == 100 and bar["R002"]["loads"] == 50 and P10["working_days"] == WD
   and abs(bar["R001"]["co2_t"] - per_route["R001"]["co2_t"]) < 1e-6, str(bar))

pay = road_sections.road_load(M, factors=factors, working_days=WD)
ok("5. the October read serves the loaded leg, the working days and a basis sentence",
   pay["month"] == 10 and pay["leg"] == "loaded" and pay["working_days"] == WD
   and "one load = one two-way movement" in pay["basis"], str({k: pay[k] for k in ("month", "leg", "working_days")}))
ok("5. one run carries volume (A+B); the A+B+C run has no C volume but still carries A and B",
   len(pay["runs"]) == 2 and sorted(tuple(x["routes"]) for x in pay["runs"]) == [("R001", "R002"), ("R001", "R002", "R003")],
   str([(x["routes"], x["trips"]) for x in pay["runs"]]))
ab = [x for x in pay["runs"] if x["routes"] == ["R001", "R002"]][0]
abc = [x for x in pay["runs"] if x["routes"] == ["R001", "R002", "R003"]][0]
ok("5. ⭐ movements on the run = (100 + 50) trips / working days — the two routes' loaded trips, NEVER doubled",
   ab["trips"] == 150 and ab["movements_per_day"] == round(150 / WD, 2), f"{ab['trips']} {ab['movements_per_day']}")
ok("5. ...equal to the sum of the per-route figures the payload also lists",
   abs(sum(s["movements_per_day"] for s in ab["route_shares"]) - ab["movements_per_day"]) < 0.02
   and [s["route_id"] for s in ab["route_shares"]] == ["R001", "R002"])
ok("5. ...and NOT the per-route figure times two (the A8 bug on the label)",
   ab["movements_per_day"] != round(2 * 150 / WD, 2) and ab["movements_per_day"] < 2 * per_route["R001"]["trips"] / WD)
ok("5. the other month's line and the Pending line do not count (150, not 160 or 1149)", ab["trips"] == 150 and abc["trips"] == 150)
ok("5. vehicles on the run = the sum of the lines' rounded-up vehicles, as the bar does",
   ab["vehicles"] == per_route["R001"]["vehicles"] + per_route["R002"]["vehicles"] and ab["vehicles"] >= 2, str(ab["vehicles"]))
# co2 share proportional to length — over the route's TWO-WAY length, because the route's month CO2e is
# costlines' both-legs figure (km_trip = loaded + baked return). Both A and B have a baked return here.
LA, LB = plen(A), plen(B)
LA2, LB2 = LA + plen(A_RET), LB + plen(B_RET)
exp_ab = per_route["R001"]["co2_t"] * ab["length_km"] / LA2 + per_route["R002"]["co2_t"] * ab["length_km"] / LB2
exp_ab_loaded_only = per_route["R001"]["co2_t"] * ab["length_km"] / LA + per_route["R002"]["co2_t"] * ab["length_km"] / LB
ok("5. ⭐ CO2e on the run = Σ route month CO2e × run length / the route's TWO-WAY length (loaded + baked return): the carbon emitted on the stretch",
   abs(ab["co2_t"] - exp_ab) < 2e-3, f"{ab['co2_t']} vs {exp_ab}")
ok("5. 🔴 ...and NOT over the loaded leg alone, which put the whole trip's carbon on the laden half of the road (about twice the figure)",
   abs(ab["co2_t"] - exp_ab_loaded_only) > 1e-3 and exp_ab_loaded_only > 1.8 * exp_ab, f"{ab['co2_t']} vs loaded-only {exp_ab_loaded_only}")
ok("5. ...each route share names this leg's length and the two-way length it was divided over",
   [s for s in ab["route_shares"] if s["route_id"] == "R001"][0]["two_way_length_km"] == round(LA2, 3)
   and [s for s in ab["route_shares"] if s["route_id"] == "R002"][0]["two_way_length_km"] == round(LB2, 3))
ok("5. ...and the run and each share carry the bar's fractional loads beside the Dashboard's trips",
   ab["loads"] == 150 and [s["loads"] for s in ab["route_shares"]] == [100, 50] and ab["trips"] == 150)
shareA_ab = [s for s in ab["route_shares"] if s["route_id"] == "R001"][0]
shareA_abc = [s for s in abc["route_shares"] if s["route_id"] == "R001"][0]
ok("5. ...A's share on the two runs is in the ratio of their lengths",
   abs(shareA_ab["co2_t"] / shareA_abc["co2_t"] - ab["length_km"] / abc["length_km"]) < 0.02
   and shareA_ab["route_length_km"] == round(LA, 3), f"{shareA_ab} {shareA_abc}")
ok("5. ...and a route's shares over all its runs never exceed its month CO2e",
   shareA_ab["co2_t"] + shareA_abc["co2_t"] <= per_route["R001"]["co2_t"] + 1e-6)
ok("5. the run carries its geometry, length and vertex count for the map",
   ab["geometry"] == A[2:5] and abc["geometry"] == A[4:7] and ab["vertices"] == 3 and abc["vertices"] == 3
   and ab["length_km"] > 0 and ab["first"] == A[2])
# team names, never ids
blob = json.dumps(pay)
ok("5. ⭐ team NAMES on the run and on each route share — North Team, Central Team",
   ab["teams"] == ["Central Team", "North Team"] and shareA_ab["teams"] == ["North Team"], str(ab["teams"]))
ok("5. ...an unnamed slot reads 'Team 4', not its id",
   [s for s in abc["route_shares"] if s["route_id"] == "R003"][0]["teams"] == ["Team 4"])
ok("5. 🔴 no team id anywhere in the payload", not TEAM_ID.search(blob) and "IPT" not in blob)
tot = pay["totals"]
ok("5. totals are per ROUTE (150 trips, 2 routes with volume), not a sum over runs (which would be 300)",
   tot["trips"] == 150 and tot["routes_with_volume"] == 2 and tot["movements_per_day"] == round(150 / WD, 2)
   and tot["runs"] == 2 and tot["routes_in_runs"] == 3, str(tot))
ok("5. totals' CO2e is the routes' month CO2e", abs(tot["co2_t"] - round(per_route["R001"]["co2_t"] + per_route["R002"]["co2_t"], 3)) < 2e-3)
ok("5. totals carry the shared km", abs(tot["shared_km"] - round(ab["length_km"] + abc["length_km"], 3)) < 2e-3)
ok("5. no note when there is volume on shared road", pay["notes"] == [], str(pay["notes"]))
empty = road_sections.road_load(1, factors=factors, working_days=WD)
ok("5. ⭐ a month with no volume gives empty runs and a note", empty["runs"] == [] and empty["totals"]["runs"] == 0
   and empty["notes"] == ["No approved volume in this month."], str(empty["notes"]))
nov = road_sections.road_load(11, factors=factors, working_days=WD)
ok("5. November: A's 10 trips alone still show on the shared runs (10 / wd), B contributes 0",
   len(nov["runs"]) == 2 and all(x["trips"] == 10 for x in nov["runs"])
   and [s["trips"] for s in nov["runs"][0]["route_shares"] if s["route_id"] == "R002"] == [0])
ok("5. working_days not given: the payload's figure (main._working_days, the one reader) is used",
   road_sections.road_load(M, factors=factors)["working_days"] == WD == P10["working_days"])
ret = road_sections.road_load(M, factors=factors, working_days=WD, leg="return")
ok("5. the return leg is served separately: its own run (V5..V7), the same 150 loads, and a note that they are not added",
   ret["leg"] == "return" and len(ret["runs"]) == 1 and ret["runs"][0]["trips"] == 150
   and ret["runs"][0]["geometry"] == [V(7), V(6), V(5)] and any("never added" in n for n in ret["notes"]), str(ret["notes"]))
ok("5. ...and the loaded read never contains the return run", not any(x["geometry"] == [V(7), V(6), V(5)] for x in pay["runs"]))
try:
    road_sections.road_load(M, leg="sideways")
    ok("5. an unknown leg is refused", False)
except ValueError:
    ok("5. an unknown leg is refused", True)
# an unbaked route with volume is reported, not invented
rE = network.create_route(q3["id"], d1["id"], material_category=BAL, route_id="R005", ipt="IPT1")["id"]
add_line("F5", rE, 20 * PAYLOAD, "IPT1")
pay2 = road_sections.road_load(M, factors=factors, working_days=WD)
# REVERSED 12 Oct 2026 (the review and fix pass): the feed claims the public map bar's figures, and the bar (and the
# bulletin's rule 1) leaves out a line on a route the map does not draw. This line used to count in the totals
# (170 trips against the bar's 150); it is now named in routes_not_drawn and not counted, exactly as the bulletin does.
ok("5. 🔴 a line on a route the map does not draw is NOT in the totals (150, the bar's figure, not 170) and reaches no run",
   pay2["totals"]["trips"] == 150 and pay2["totals"]["loads"] == 150 and pay2["totals"]["unbaked_lines"] == 0
   and pay2["totals"]["routes_with_volume"] == 2
   and ab["trips"] == [x for x in pay2["runs"] if x["routes"] == ["R001", "R002"]][0]["trips"], str(pay2["totals"]))
ok("5. ⭐ ...it is NAMED in routes_not_drawn (lines, routes, a sentence), never counted as zero",
   pay2["routes_not_drawn"]["lines"] == 1 and pay2["routes_not_drawn"]["routes"] == ["R005"]
   and "not in these figures" in pay2["routes_not_drawn"]["note"] and pay2["notes"] == [], str(pay2["routes_not_drawn"]))
import bulletin  # noqa: E402
_bar_m = bulletin.rollup_payloads([main.public_month_kpis(month=M, unit="vehicles")], bulletin.drawn_routes(), WD)
ok("5. ⭐ ...so the feed's totals equal the bar's own roll-up for the month (the bulletin's: movements, loads, routes, vehicles)",
   pay2["totals"]["movements_per_day"] == round(_bar_m["headline"]["two_way_a_day"], 2)
   and pay2["totals"]["loads"] == _bar_m["headline"]["movements_in_month"]
   and pay2["totals"]["routes_with_volume"] == _bar_m["headline"]["routes_in_use"]
   and pay2["totals"]["vehicles"] == _bar_m["vehicles"]["fleet"]
   and _bar_m["routes_not_drawn"]["routes"] == pay2["routes_not_drawn"]["routes"],
   f"{pay2['totals']} vs {_bar_m['headline']} {_bar_m['vehicles']}")
ok("5. the empty month's routes_not_drawn block is empty and has no sentence",
   empty["routes_not_drawn"] == {"lines": 0, "routes": [], "note": None} and empty["routes_off_index"] == [])
# the return read's carbon: A's loaded shares + A's return share never exceed A's month CO2e, and the
# return run is divided over the same two-way length
ret_shareA = sum(s["co2_t"] for x in ret["runs"] for s in x["route_shares"] if s["route_id"] == "R001")
ok("5. ⭐ a route's loaded-leg shares plus its return-leg shares stay within its month CO2e (nothing counted twice across the legs)",
   shareA_ab["co2_t"] + shareA_abc["co2_t"] + ret_shareA <= per_route["R001"]["co2_t"] + 1e-6 and ret_shareA > 0,
   f"{shareA_ab['co2_t']} + {shareA_abc['co2_t']} + {ret_shareA} vs {per_route['R001']['co2_t']}")
ok("5. ...the return run's share is A's CO2e × its length / the same two-way length",
   abs(ret_shareA - per_route["R001"]["co2_t"] * ret["runs"][0]["length_km"] / LA2) < 2e-3)

# ⭐ the breaking case for the movements figure: FRACTIONAL loads. The bar sums loads as typed (tonnes ÷ payload);
# the Dashboard's costlines rounds up per line. December: A carries 10.4 loads, B 0.5 — the bar says 10.9 a month,
# ceil-per-line says 12. The run on the public map must say what the bar beside it says.
add_line("F6", rA, 10.4 * PAYLOAD, "IPT1", month=12)
add_line("F7", rB, 0.5 * PAYLOAD, "IPT2", month=12)
P12 = main.public_month_kpis(month=12)
bar12 = sum(l["vehicle_loads"] for l in P12["lines"] if l["route_id"] in ("R001", "R002"))
dec = road_sections.road_load(12, factors=factors, working_days=WD)
dab = [x for x in dec["runs"] if x["routes"] == ["R001", "R002"]][0]
ok("5. ⭐ December: the run's loads are the bar's 10.9 (10.4 + 0.5), and movements a day = 10.9 / working days",
   abs(dab["loads"] - 10.9) < 1e-6 and abs(bar12 - 10.9) < 1e-6 and dab["movements_per_day"] == round(10.9 / WD, 2),
   f"{dab['loads']} {dab['movements_per_day']} bar {bar12}")
ok("5. 🔴 ...NOT Σ ceil per line (12 / working days): the public map's run and its bar cannot disagree by rounding",
   dab["trips"] == 12 and dab["movements_per_day"] != round(12 / WD, 2) and dec["totals"]["loads"] == round(10.9, 3)
   and dec["totals"]["movements_per_day"] == round(10.9 / WD, 2), f"{dab['trips']} {dab['movements_per_day']} vs {round(12 / WD, 2)}")
ok("5. ...the per-route shares carry the fractional loads too (10.4 and 0.5) and the basis sentence names the rule",
   [s["loads"] for s in dab["route_shares"]] == [10.4, 0.5] and "not rounded per line" in dec["basis"]
   and "two-way length" in dec["co2_basis"])
ok("5. ...vehicles on the run follow the bar's rule, ceil per line of (loads / wd) / what one vehicle can do on that route",
   dab["vehicles"] == sum(math.ceil((l["vehicle_loads"] / WD) / l["trips_per_vehicle_day"]) for l in P12["lines"]
                          if l["route_id"] in ("R001", "R002") and l["trips_per_vehicle_day"]) and dab["vehicles"] >= 2)

# 12 Oct 2026 (the review and fix pass): a run whose owners carry volume but no carbon (their routes are not stored
# for the lines' vehicle) prints no 0.0 t — its co2_t is None and it names the lines left out
RIGID = "Rigid 8-wheeler (32t)"
for _fid, _rid in (("F8", rA), ("F9", rB)):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), _fid, _rid, 2, "superstructure", "", 400, "t", BAL, "Type 1", RIGID, "test",
                "Approved", None, "IPT1"))
feb = road_sections.road_load(2, factors=factors, working_days=WD)
fab = [x for x in feb["runs"] if x["routes"] == ["R001", "R002"]]
ok("5. ⭐ a run whose owners' lines carry no carbon (not stored for the rigid) reads co2_t None, never 0.0 t, and names the 2 lines",
   len(fab) == 1 and fab[0]["co2_t"] is None and fab[0]["co2_lines_unbaked"] == 2 and fab[0]["loads"] > 0
   and all(s["co2_t"] is None for s in fab[0]["route_shares"]), str(fab[:1] and {k: fab[0][k] for k in ("co2_t", "co2_lines_unbaked")}))
ok("5. ...the month's totals CO2e is None too (no line carries carbon), with the count", feb["totals"]["co2_t"] is None
   and feb["totals"]["co2_lines_unbaked"] == 2 and feb["totals"]["unbaked_lines"] == 2, str(feb["totals"]))
ok("5. ...while a run with one owner's carbon and another's missing keeps the figure it has (October: C has no volume, 0 not None)",
   abc["co2_t"] is not None and [s for s in abc["route_shares"] if s["route_id"] == "R003"][0]["co2_t"] == 0.0)
# a line team value that is not exactly one id (two joined) is named through team_text, never passed through raw
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
           "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (db.current_tenant(), "F10", rA, 3, "superstructure", "", 5 * PAYLOAD, "t", BAL, "Type 1", PROFILE, "test",
            "Approved", None, "IPT1 / IPT2"))
mar = road_sections.road_load(3, factors=factors, working_days=WD)
ok("5. 🔴 a compound line team value ('two ids joined by a slash') reaches the feed as NAMES, never as ids",
   len(mar["runs"]) == 2 and "IPT" not in json.dumps(mar) and not TEAM_ID.search(json.dumps(mar))
   and any("North Team" in t and "Central Team" in t for x in mar["runs"] for t in x["teams"]), str([x["teams"] for x in mar["runs"]]))

# ⭐ the carbon read fails: the month read answers, says why, and never raises (B2's co2_error, carried through)
_real_lines = costlines.lines
costlines.lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("factors document broken"))
try:
    broken = road_sections.road_load(M, factors=factors, working_days=WD)
    # NARROWED 12 Oct 2026 (the review and fix pass): every CO2e is None (null), not 0 — a failed read is not 0.0 t
    # of carbon (the bulletin's e85b491 rule) — and co2_error is a fixed sentence naming the class only (main logs the
    # message: an exception's text can carry SQL or internal keys to a map-password holder)
    ok("5. ⭐ when costlines fails the month read still answers: the runs and movements intact, every CO2e null (never 0), co2_error naming the reason",
       len(broken["runs"]) == 2 and broken["runs"][0]["movements_per_day"] > 0 and all(x["co2_t"] is None for x in broken["runs"])
       and all(s["co2_t"] is None for x in broken["runs"] for s in x["route_shares"])
       and broken["totals"]["co2_t"] is None and "RuntimeError" in str(broken.get("co2_error", ""))
       and "factors document broken" not in str(broken.get("co2_error", ""))
       and any("co2_error" in n for n in broken["notes"]), str(broken.get("co2_error")))
except Exception as e:  # pragma: no cover — the assertion reports it
    ok("5. ⭐ when costlines fails the month read still answers: the runs and movements intact, every CO2e null (never 0), co2_error naming the reason",
       False, repr(e))
finally:
    costlines.lines = _real_lines
ok("5. ...and with the read restored there is no co2_error and the carbon is back",
   "co2_error" not in road_sections.road_load(M, factors=factors, working_days=WD)
   and road_sections.road_load(M, factors=factors, working_days=WD)["totals"]["co2_t"] > 0)
# 12 Oct 2026 (the tenancy / wording review): the carbon on a run is a planning estimate and the feed SAYS so
# with the Carbon page's stamp, read from carbon.py — the road-load popup prints CO2e and had nothing beside it
import carbon  # noqa: E402
ok("5. ⭐ the feed carries the Carbon page's planning-estimate stamp, read from carbon.py, with the apportioning rule",
   pay["carbon"]["stamp"] == carbon.SUMMARY_STAMP == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"
   and "approved plan only" in pay["carbon"]["rule"] and "÷ that route's two-way length" in pay["carbon"]["rule"]
   and "loaded length" not in pay["carbon"]["rule"]
   and empty["carbon"]["stamp"] == carbon.SUMMARY_STAMP and ret["carbon"]["stamp"] == carbon.SUMMARY_STAMP, str(pay.get("carbon")))
try:
    road_sections.road_load(M, leg="sideways")
    ok("5. the unknown-leg refusal reads as words, not a Python tuple", False)
except ValueError as e:
    ok("5. the unknown-leg refusal reads as words, not a Python tuple",
       str(e) == road_sections.leg_error() == "leg must be one of 'loaded' or 'return'" and "(" not in str(e) and "[" not in str(e), str(e))

# =========================================================================== #
#  6. The endpoints (bodies) and the gate scope                                #
# =========================================================================== #
ok("6. /api/public/road-load is behind the map scope", gate.scope_for("/api/public/road-load?month=10") == "map"
   and gate.scope_for("/api/public/road-load") == "map")
ok("6. the admin paths are not the map's (they are token-protected)",
   gate.scope_for("/api/admin/road-sections/rebuild?token=x") is None
   and gate.scope_for("/api/admin/diagnostics/road-sections") is None)
body = main.public_road_load(month=M)
ok("6. the public endpoint body serves the October read with the one working-days reader",
   body["working_days"] == main._working_days(conversions.load_factors()) and len(body["runs"]) == 2)
try:
    main.public_road_load(month=M, leg="sideways")
    ok("6. the endpoint refuses an unknown leg with 400", False)
except _HTTPException as e:
    # NARROWED 12 Oct 2026 (the tenancy / wording review): the detail reads as words, not "['loaded', 'return']"
    ok("6. the endpoint refuses an unknown leg with 400 whose detail reads \"leg must be one of 'loaded' or 'return'\"",
       e.status_code == 400 and e.detail == "leg must be one of 'loaded' or 'return'", str(e.detail))
os.environ["ADMIN_TOKEN"] = "adm-test"
for fn, label in ((lambda t: main.road_sections_rebuild(token=t), "rebuild"),
                  (lambda t: main.road_sections_status(token=t), "status"),
                  (lambda t: main.diagnostics_road_sections(token=t), "diagnostics")):
    try:
        fn("wrong")
        ok(f"6. 🔴 admin {label} refuses a wrong token", False)
    except _HTTPException as e:
        ok(f"6. 🔴 admin {label} refuses a wrong token", e.status_code == 403)
    try:
        fn(None)
        ok(f"6. 🔴 admin {label} refuses a missing token", False)
    except _HTTPException as e:
        ok(f"6. 🔴 admin {label} refuses a missing token", e.status_code == 403)
    # 12 Oct 2026 (the review and fix pass): a non-ASCII token was a TypeError in hmac.compare_digest — a 500
    try:
        fn("é-adm")
        ok(f"6. 🔴 admin {label} refuses a non-ASCII token with 403, not a 500", False)
    except _HTTPException as e:
        ok(f"6. 🔴 admin {label} refuses a non-ASCII token with 403, not a 500", e.status_code == 403)
    except TypeError as e:
        ok(f"6. 🔴 admin {label} refuses a non-ASCII token with 403, not a 500", False, repr(e))
rb = main.road_sections_rebuild(token="adm-test")
ok("6. the rebuild answers the status counts: 3 routes, 2 runs, 5 vertices shared",
   rb["routes_indexed"] == 3 and rb["runs"] == 2 and rb["vertices_shared"] == 5 and rb["stale"] is False, str(rb))
ok("6. status matches", main.road_sections_status(token="adm-test")["runs"] == 2)
dg = main.diagnostics_road_sections(token="adm-test")
ok("6. the diagnostic prints the longest runs with their route sets, longest first",
   {tuple(x["routes"]) for x in dg["longest"]} == {("R001", "R002", "R003"), ("R001", "R002")}
   and dg["longest"][0]["length_km"] >= dg["longest"][1]["length_km"]
   and "R001+R002+R003" in dg["text"] and "3 routes indexed, 2 runs (2 stored)" in dg["text"], dg["text"])
ok("6. ...and names the profile and both legs", PROFILE in dg["text"] and "return:" in dg["text"] and "loaded:" in dg["text"])
ok("6. the diagnostic is read-only: no row changed", len(db.query("SELECT * FROM route_sections WHERE tenant_id = ?",
                                                                   (db.current_tenant(),))) == 3)
os.environ.pop("ADMIN_TOKEN", None)
src_main = read("backend/main.py")
ok("6. main.py registers the four routes", all(s in src_main for s in (
    '@app.get("/api/public/road-load")', '@app.post("/api/admin/road-sections/rebuild")',
    '@app.get("/api/admin/road-sections/status")', '@app.get("/api/admin/diagnostics/road-sections")')))
ok("6. the public endpoint hands _working_days() in — one reader of the figure",
   "working_days=_working_days(factors), leg=leg)" in src_main)

# =========================================================================== #
#  7. The package carries the table                                            #
# =========================================================================== #
pkg = tenant_package.export_tenant(app_version="test")
cnt = tenant_package.counts(pkg)
ok("7. the export carries route_sections: 3 rows (2 loaded, 1 return)", cnt.get("route_sections") == 3, str(cnt))
secs = pkg["tables"]["route_sections"]
ok("7. ...with the spec's columns and no tenant_id",
   all(set(r) == {"section_id", "leg", "routes_json", "geometry_json", "length_km", "built_at"} for r in secs), str(secs[0].keys()))
ok("7. validate() passes the export", tenant_package.validate(pkg) == [])
ids_before = {(r["leg"], r["section_id"]) for r in secs}
boot()
out = tenant_package.import_tenant(pkg)
ok("7. import into an empty tenant succeeds and reports the table", out["ok"] and out["inserted"].get("route_sections") == 3, str(out))
ids_after = {(r["leg"], r["section_id"]) for r in db.query("SELECT leg, section_id FROM route_sections WHERE tenant_id = ?",
                                                             (db.current_tenant(),))}
ok("7. ⭐ the same run ids after the round trip (the import's rebuild agrees with the package)", ids_after == ids_before,
   f"{ids_before} vs {ids_after}")
ok("7. ...stamped with the CURRENT tenant", {r["tenant_id"] for r in db.query("SELECT tenant_id FROM route_sections")} == {db.current_tenant()})
ok("7. the month read works on the imported tenant", len(road_sections.road_load(M)["runs"]) == 2)
# an older package without the table still gets an index on import
pkg_old = json.loads(json.dumps(pkg))
pkg_old["tables"].pop("route_sections")
boot()
tenant_package.import_tenant(pkg_old)
ok("7. ⭐ a package written before the table existed is indexed on import", len(road_sections.stored_runs("loaded")) == 2)
ok("7. the import source rebuilds the index", "_road_sections._rebuild_quietly(\"tenant import\")" in read("backend/tenant_package.py"))

# =========================================================================== #
#  8. Source-level rules                                                       #
# =========================================================================== #
src = read("backend/road_sections.py")
ok("8. no literal working-day count in the module", not re.search(r"\b22\b", src))
ok("8. no team id literal in the module", not TEAM_ID.search(src) and "IPT" not in src)
ok("8. UK public wording: none of the banned words", not re.search(
    r"\b(truck|real[- ]time|live tracking|telematics|optimi[sz]|predict|secure)\b", src, re.I))
import ast
_sel = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.lstrip().upper().startswith(("SELECT", "DELETE", "INSERT"))]
ok("8. every SELECT / DELETE / INSERT in the module names tenant_id (the audit's rule, restated)",
   len(_sel) >= 6 and all("tenant_id" in q for q in _sel) and src.count("db.current_tenant()") >= 6, str(len(_sel)))
ok("8. nothing external: no urllib, requests or HERE", not re.search(r"\b(urllib|requests|here_routing)\b", src))
ok("8. ⭐ the month read takes the bar's payload (public_month_kpis as a function) and no longer sums costlines' rounded-up trips itself",
   'main.public_month_kpis(month=int(month), unit="vehicles")' in src and "import costlines" not in src
   and "math.ceil((loads / wd) / float(tpv))" in src and 'float(l.get("vehicle_loads")' in src)
ok("8. ...and divides a route's CO2e over its two-way length, the legs costlines summed it over",
   'lk + rk' in src and '"two_way"' in src and "return_baked" in src)
# 12 Oct 2026 (the tenancy / wording review)
ok("8. the stamp is read from carbon.py, never copied into this module", "carbon.SUMMARY_STAMP" in src
   and "planning estimate" not in src.replace("planning-estimate", ""))
ok("8. no Python tuple or list is rendered into a message a person reads: the leg refusals read leg_error() everywhere",
   "{LEGS}" not in src and "{list(" not in src and src.count("leg_error()") >= 2
   and src_main.count("road_sections.leg_error()") == 2 and "{list(road_sections.LEGS)}" not in src_main)
ok("8. no US spelling in the module's sentences", not re.search(r"\b(color|center|meter|kilometer|neighbor|analyze|optimize)\b", src, re.I))
ok("8. the module says what it does not do", "WHAT THIS DOES NOT DO" in src)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
