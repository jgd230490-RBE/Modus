"""
Movements and carbon per council (public map review §2.2b, D27, the server half) — 12 Oct 2026.

Same harness shape as test_road_sections.py: a scratch SQLite database, no network,
`fastapi` / `flexpolyline` stubbed so main.py imports and its endpoint bodies run as plain
Python.

WHAT THIS PROVES
----------------
  * the pure-Python clip: a synthetic square with a line crossing it gives exactly the
    haversine length of the part inside; a hole is cut out; a MultiPolygon counts both
    parts; a road that IS the boundary counts half to each neighbour (so two neighbours add
    up to its length); a line through a corner, a line in and out three times, a line that
    never comes near;
  * the import: the seed file (the eight ONS districts round the corridor and
    Leicestershire, May 2026 / Dec 2025, BSC) loads, carries the two licence lines and puts
    the demo's sites where the package coordinates say; a collection with no licence
    lines, a bad tier, a non-polygon, a duplicate id or projected coordinates is refused;
  * the stored clip: route_area_km per (route, profile, leg, area) plus the whole-leg row,
    rebuilt by _upsert_geom, clear_geometry, the bake batch (once) and the areas import;
  * the month read: movements = the loads of routes whose LADEN leg enters the area ÷ the
    working days (never doubled; a return leg in another area adds no movement there but
    does carry its lorry-km and carbon); an unbaked line is in no area; CO2e apportioned by
    km inside over the TWO-WAY length sums over a tier to the route's total — and is NOT
    the laden-length split; a failed carbon read gives None, never 0.0;
  * the package round trip, the gate scope, the admin token, the source rules.

WHAT THIS DOES NOT PROVE
------------------------
  * No Postgres branch runs (the tables are plain CREATEs on both backends).
  * The HTTP transport is stubbed: endpoint BODIES run, the gate middleware does not —
    http_smoke.py drives the real app for the 401 / 403 and the empty demo answer.
  * Nothing about the live demo's HERE polylines: which districts the baked routes really
    cross (Leicester? Oadby and Wigston?) is known only after the seed is imported on
    Render and the clip has run there.

Run:  python backend/tests/test_areas.py
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

TMP = tempfile.mkdtemp(prefix="wayscope_areas_")
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
import areas  # noqa: E402
import gate  # noqa: E402
import limits  # noqa: E402
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


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def plen(pts):
    return sum(hav(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]


def poly(*rings):
    return {"type": "Polygon", "coordinates": [list(r) for r in rings]}


PROFILE = network.DEFAULT_PROFILE          # "Artic Tipper (44t)"
RIGID = "Rigid 8-wheeler (32t)"
BAL = "Large aggregate / ballast"
TEAM_ID = re.compile(r"\bIPT ?[1-6]\b")
ATTR = ["Source: Office for National Statistics licensed under the Open Government Licence v.3.0",
        "Contains OS data © Crown copyright and database right 2026"]

# =========================================================================== #
#  1. The clip on polygons alone (no database)                                 #
# =========================================================================== #
SQ = areas.Area("SQ", poly(box(0, 0, 1, 1)))
km = areas.clip_km([[-0.5, 0.5], [1.5, 0.5]], SQ)
ok("1. ⭐ a line crossing a square: the km inside = the haversine of its part inside (0..1 at 0.5 N)",
   abs(km - hav([0, 0.5], [1, 0.5])) < 1e-6, f"{km} vs {hav([0, 0.5], [1, 0.5])}")
ok("1. ...and not the whole line's length", km < plen([[-0.5, 0.5], [1.5, 0.5]]) - 50)
ok("1. a line wholly inside counts whole", abs(areas.clip_km([[0.2, 0.2], [0.8, 0.2], [0.8, 0.7]], SQ)
                                               - plen([[0.2, 0.2], [0.8, 0.2], [0.8, 0.7]])) < 1e-6)
ok("1. a line wholly outside (and outside the box) counts nothing", areas.clip_km([[2, 2], [3, 3]], SQ) == 0.0)
ok("1. a line in the box but outside an L-shape counts nothing",
   areas.clip_km([[0.7, 0.7], [0.9, 0.9]], areas.Area("L", poly([[0, 0], [1, 0], [1, 0.5], [0.5, 0.5], [0.5, 1], [0, 1], [0, 0]]))) == 0.0)
ok("1. a crossing line split over many vertices gives the same km as one segment",
   abs(areas.clip_km([[-0.5 + 0.05 * i, 0.5] for i in range(41)], SQ) - km) < 1e-6)
ok("1. in, out and in again: three crossings of a U-shape counted piece by piece",
   abs(areas.clip_km([[-0.5, 0.25], [2.5, 0.25]], areas.Area("U2", {"type": "MultiPolygon", "coordinates": [
       [box(0, 0, 1, 1)], [box(1.5, 0, 2, 1)]]})) - (hav([0, 0.25], [1, 0.25]) + hav([1.5, 0.25], [2, 0.25]))) < 1e-6)
H = areas.Area("H", poly(box(0, 0, 1, 1), box(0.25, 0.25, 0.75, 0.75)))
ok("1. ⭐ a hole is cut out: 0..0.25 and 0.75..1 count, the hole does not",
   abs(areas.clip_km([[-0.5, 0.5], [1.5, 0.5]], H) - 2 * hav([0, 0.5], [0.25, 0.5])) < 1e-6)
ok("1. ...a line wholly inside the hole counts nothing", areas.clip_km([[0.3, 0.5], [0.7, 0.5]], H) == 0.0)
MP = areas.Area("MP", {"type": "MultiPolygon", "coordinates": [[box(0, 0, 1, 1)], [box(2, 0, 3, 1)]]})
ok("1. ⭐ a MultiPolygon counts both of its parts, not the gap between them",
   # 1e-4 km: a piece's length is its parameter share of the segment's haversine, which is within
   # millimetres of the piece's own great-circle length on a 4-degree segment
   abs(areas.clip_km([[-0.5, 0.5], [3.5, 0.5]], MP) - (hav([0, 0.5], [1, 0.5]) + hav([2, 0.5], [3, 0.5]))) < 1e-4)
EAST = areas.Area("EAST", poly(box(1, 0, 2, 1)))
along = [[1.0, 0.2], [1.0, 0.8]]
ok("1. ⭐ a road that IS the boundary counts half to each neighbour, so the two add up to its length",
   abs(areas.clip_km(along, SQ) - plen(along) / 2) < 1e-6 and abs(areas.clip_km(along, EAST) - plen(along) / 2) < 1e-6)
ok("1. a road crossing from one neighbour to the other: the two shares add up to its length, nothing lost or doubled",
   abs(areas.clip_km([[0.5, 0.5], [1.5, 0.5]], SQ) + areas.clip_km([[0.5, 0.5], [1.5, 0.5]], EAST)
       - hav([0.5, 0.5], [1.5, 0.5])) < 1e-6)
ok("1. a line through a corner (touching at one point) does not enter",
   areas.clip_km([[1.0, 0.0], [2.0, -1.0]], SQ) == 0.0 and areas.clip_km([[0.5, 1.5], [1.5, 0.5]], SQ) == 0.0)
ok("1. a polygon whose ring is not closed is closed for it", abs(areas.clip_km([[-0.5, 0.5], [1.5, 0.5]],
   areas.Area("OPEN", poly([[0, 0], [1, 0], [1, 1], [0, 1]]))) - km) < 1e-6)
ok("1. contains(): inside, outside, in a hole", SQ.contains(0.5, 0.5) and not SQ.contains(1.5, 0.5)
   and not H.contains(0.5, 0.5) and H.contains(0.1, 0.5))
# 12 Oct 2026 (the Chrome check): one label point per area, inside it — a label placed on the polygon
# itself is repeated by Mapbox on every tile the polygon crosses (Harborough was labelled twice)
_lp = areas.label_point(poly(box(0, 0, 1, 1)))
ok("1. ⭐ label_point: a square's label sits on its middle line, inside", SQ.contains(*_lp) and abs(_lp[0] - 0.5) < 1e-9, str(_lp))
_L = poly([[0, 0], [1, 0], [1, 0.2], [0.2, 0.2], [0.2, 1], [0, 1], [0, 0]])
ok("1. ⭐ ...a thin L-shape's label is inside the L, not at its box's middle (which is outside)",
   areas.Area("L2", _L).contains(*areas.label_point(_L)) and not areas.Area("L2", _L).contains(0.5, 0.5),
   str(areas.label_point(_L)))
ok("1. ...a ring with a hole keeps its label out of the hole", H.contains(*areas.label_point(poly(box(0, 0, 1, 1), box(0.25, 0.25, 0.75, 0.75)))))
ok("1. ...a MultiPolygon is labelled once, in its largest part",
   2 <= areas.label_point({"type": "MultiPolygon", "coordinates": [[box(0, 0, 0.5, 0.5)], [box(2, 0, 3, 1)]]})[0] <= 3)
ok("1. ...a geometry with no ring has no label point (never a made-up place)", areas.label_point({"type": "Polygon", "coordinates": []}) is None)
# a fine grid cell boundary between a point and the edge east of it must not lose a crossing
FINE = areas.Area("FINE", poly(box(0.0, 0.0, 0.0345, 0.0345)))
ok("1. the edge grid: a point and the polygon's east edge several cells apart still find each other",
   FINE.contains(0.001, 0.02) and not FINE.contains(0.04, 0.02)
   and abs(areas.clip_km([[-0.01, 0.02], [0.05, 0.02]], FINE) - hav([0, 0.02], [0.0345, 0.02])) < 1e-6)

# parse_collection refusals
GOOD = {"type": "FeatureCollection", "attribution": ATTR, "features": [
    {"type": "Feature", "properties": {"area_id": "A1", "name": "Alpha", "tier": "district"}, "geometry": poly(box(0, 0, 1, 1))}]}


def refused(fc, needle):
    try:
        areas.parse_collection(fc)
        return False
    except ValueError as e:
        return needle in str(e)


ok("1. a good collection parses to one row with the licence lines as JSON",
   [r["area_id"] for r in areas.parse_collection(GOOD)] == ["A1"]
   and json.loads(areas.parse_collection(GOOD)[0]["attribution_json"]) == ATTR)
_noattr = json.loads(json.dumps(GOOD)); _noattr.pop("attribution")
ok("1. ⭐ no licence lines: refused, naming the lines (the map must never print another dataset's)",
   refused(_noattr, "no licence lines"))
_tier = json.loads(json.dumps(GOOD)); _tier["features"][0]["properties"]["tier"] = "parish"
ok("1. a tier other than district or county is refused (parishes stay out, D27)", refused(_tier, "tier must be"))
_line = json.loads(json.dumps(GOOD)); _line["features"][0]["geometry"] = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
ok("1. a LineString is refused", refused(_line, "Polygon or MultiPolygon"))
_dup = json.loads(json.dumps(GOOD)); _dup["features"].append(json.loads(json.dumps(GOOD["features"][0])))
ok("1. a duplicate id is refused", refused(_dup, "appears twice"))
_bng = json.loads(json.dumps(GOOD)); _bng["features"][0]["geometry"] = poly(box(450000, 300000, 451000, 301000))
ok("1. British National Grid metres are refused with the reason (send WGS84)", refused(_bng, "WGS84"))
ok("1. not a FeatureCollection, or an empty one, is refused",
   refused({"type": "Feature"}, "FeatureCollection") and refused({"type": "FeatureCollection", "features": []}, "no features"))
_ons = {"type": "FeatureCollection", "attribution": ATTR, "features": [
    {"type": "Feature", "properties": {"LAD26CD": "E07000131", "LAD26NM": "Harborough"}, "geometry": poly(box(0, 0, 1, 1))},
    {"type": "Feature", "properties": {"CTYUA25CD": "E10000018", "CTYUA25NM": "Leicestershire"}, "geometry": poly(box(0, 0, 2, 2))}]}
ok("1. an ONS layer as downloaded reads its own code, name and tier (LAD = district, CTYUA = county)",
   [(r["area_id"], r["name"], r["tier"]) for r in areas.parse_collection(_ons)]
   == [("E07000131", "Harborough", "district"), ("E10000018", "Leicestershire", "county")])

# =========================================================================== #
#  2. Schema, registry, package order                                          #
# =========================================================================== #
boot()
ok("2. areas and route_area_km are created", {"areas", "route_area_km"} <= tables())
ca, ck = cols("areas"), cols("route_area_km")
for c in ("tenant_id", "area_id", "name", "tier", "geometry_json", "source", "attribution_json", "highway_authority"):
    ok(f"2. areas has {c}", c in ca)
for c in ("tenant_id", "route_id", "vehicle_profile", "leg", "area_id", "km"):
    ok(f"2. route_area_km has {c}", c in ck)
ok("2. tenant_id is the FIRST primary key column of both", ca["tenant_id"][5] == 1 and ck["tenant_id"][5] == 1)
ok("2. both are registered as tenanted, with a Postgres primary key",
   {"areas", "route_area_km"} <= db.TENANTED_TABLES and db._TENANT_PK.get("areas") == "(tenant_id, area_id)"
   and db._TENANT_PK.get("route_area_km") == "(tenant_id, route_id, vehicle_profile, leg, area_id)")
O = tenant_package.ORDER
ok("2. ...in the package ORDER once each: areas before the routes, route_area_km after route_geometry and areas",
   O.count("areas") == 1 and O.count("route_area_km") == 1 and O.index("areas") < O.index("routes")
   and O.index("route_area_km") > O.index("route_geometry") and O.index("route_area_km") > O.index("areas"))
ok("2. ...and in the tenant audit's own registry", '"areas", "route_area_km"' in read("backend/tests/test_tenant_audit.py"))
ok("2. an empty tenant: no areas, the clip stores nothing, the month read says so",
   areas.rebuild()["rows"] == 0 and areas.area_load(10)["areas"] == []
   and "No council areas are loaded for this tenant." in areas.area_load(10)["notes"])

# =========================================================================== #
#  3. The seed file (the demo's eight districts and the county)                #
# =========================================================================== #
SEED_PATH = os.path.join(BACKEND, "data", "areas_demo.geojson")
seed_raw = read("backend/data/areas_demo.geojson")
seed = json.loads(seed_raw)
names = sorted(f["properties"]["name"] for f in seed["features"] if f["properties"]["tier"] == "district")
ok("3. ⭐ the seed is the eight districts round the corridor and Leicestershire county",
   names == sorted(["Harborough", "Melton", "Charnwood", "Blaby", "Rutland", "Leicester", "Oadby and Wigston",
                    "Hinckley and Bosworth"])
   and [f["properties"]["name"] for f in seed["features"] if f["properties"]["tier"] == "county"] == ["Leicestershire"],
   str(names))
ok("3. ⭐ it carries the two licence lines word for word (ONS licence page)", seed["attribution"] == ATTR, str(seed.get("attribution")))
ok("3. ...the OGL v3 and both FeatureServer layers it came from (May 2026 districts, Dec 2025 counties, BSC)",
   "Open Government Licence v3.0" in seed["licence"]
   and any("Local_Authority_Districts_May_2026_Boundaries_UK_BSC" in s for s in seed["sources"])
   and any("Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BSC" in s for s in seed["sources"]))
ok("3. it is under 300 KB (the BSC edition)", len(seed_raw.encode("utf-8")) < 300 * 1024, str(len(seed_raw)))
# 12 Oct 2026 (wording review): the seed's size and provenance are stated in a comment, and the comment matches the file
_asrc = read("backend/areas.py")
_n_bytes = len(seed_raw.encode("utf-8"))
_n_vert = sum(len(r) for f in seed["features"] for r in areas.rings_of(f["geometry"]))
ok("3. ⭐ areas.py states the seed's size (its exact byte count and vertex count) and where it came from (both ONS layers, the date)",
   f"is {_n_bytes:,} bytes" in _asrc and f"{_n_vert:,} vertices" in _asrc
   and "Local_Authority_Districts_May_2026_Boundaries_UK_BSC" in _asrc
   and "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BSC" in _asrc
   and "Fetched 12 Oct 2026" in _asrc and seed.get("fetched") == "2026-10-12"
   and "Open Government Licence v3.0" in _asrc,
   f"{_n_bytes:,} bytes / {_n_vert:,} vertices")
ok("3. ...and the demo generator that loads it says the same size",
   f"The seed file is {_n_bytes:,} bytes" in read("backend/tools/make_demo_tenant.py"))
ok("3. ids are the ONS codes (E06 unitary, E07 district, E10 county)",
   all(re.fullmatch(r"E(06|07|10)\d{6}", f["properties"]["area_id"]) for f in seed["features"]))
ok("3. LF endings and one line of JSON", "\r" not in seed_raw and seed_raw.endswith("\n"))
ok("3. the unitary councils name themselves as highway authority, the two-tier districts the county",
   {f["properties"]["name"]: f["properties"]["highway_authority"] for f in seed["features"]}["Leicester"] == "Leicester City Council"
   and {f["properties"]["name"]: f["properties"]["highway_authority"] for f in seed["features"]}["Harborough"]
   == "Leicestershire County Council")
res_seed = areas.import_collection(seed)
ok("3. the seed imports through the app's own path: 9 areas, 8 districts and 1 county, the two lines back",
   res_seed["imported"] == 9 and res_seed["tiers"] == {"district": 8, "county": 1}
   and res_seed["attribution"] == sorted(ATTR), str(res_seed))
# the demo's sites by point-in-polygon, from the shipped package's own coordinates
_pkg = json.loads(read("demo/uk-corridor.package.json"))
tenant_package.import_rows("locations", _pkg["tables"]["locations"])
sp = {a["name"]: a for a in areas.area_load(10)["areas"]}
# NARROWED 14 Oct 2026 (civils materials): the batching plant sits in Melton (14 sites)
# RE-PINNED 17 Oct 2026 (demo redesign R2, §3a): the asphalt plant and Welland Ready-Mix both sit in Harborough (16 sites)
# NARROWED 22 Oct 2026 (abnormal loads, phase 3, D75): the precast works in Hinckley and Bosworth and the crane depot in Charnwood (18 sites)
# RE-PINNED 28 Oct 2026 (simulation v2, the Tilton Viaduct site L019: two gates G020 / G021 with access roads Z027 / Z028, four internal roads Z029–Z032, seven routes R044–R050, 942 approved line-months)
# RE-PINNED 29 Oct 2026 (task 3c): + the Billesdon Lane holding area, in Harborough (12 of 20)
ok("3. ⭐ the demo's 20 sites by point-in-polygon: Harborough 12, Melton 3, Charnwood 2, Blaby 1, Rutland 1, Hinckley and Bosworth 1 (the mockup's recount, not the chain's 9)",
   {n: sp[n]["sites_count"] for n in ("Harborough", "Melton", "Blaby", "Charnwood", "Rutland", "Leicester",
                                       "Oadby and Wigston", "Hinckley and Bosworth")}
   == {"Harborough": 12, "Melton": 3, "Blaby": 1, "Charnwood": 2, "Rutland": 1, "Leicester": 0,
       "Oadby and Wigston": 0, "Hinckley and Bosworth": 1}
   and sp["Leicestershire"]["sites_count"] == 19 and len(_pkg["tables"]["locations"]) == 20,
   str({n: a["sites_count"] for n, a in sp.items()}))
ok("3. ...Kilby Ridge in Blaby, Northfield and the crane depot in Charnwood, Brook Pit in Rutland, the precast works in Hinckley and Bosworth",
   sp["Blaby"]["sites"] == ["Kilby Ridge Quarry"] and sorted(sp["Charnwood"]["sites"]) == ["Northfield Quarry", "Soar Valley Crane Hire (fictional)"]
   and sp["Rutland"]["sites"] == ["Brook Pit"] and sp["Hinckley and Bosworth"]["sites"] == ["Earl Shilton Precast Works (fictional)"])
ok("3. ...and the totals say 19 sites, so the card reads Harborough '11 of 19' (NARROWED 14 Oct: the batching plant; RE-PINNED 17 Oct: the two plants; 22 Oct: the two abnormal-load sites; 28 Oct: the viaduct site)",
   areas.area_load(10)["totals"]["sites"] == 20)   # RE-PINNED 29 Oct 2026 (task 3c): + the holding area
_seed_areas = {a["name"]: a for a in areas.area_load(10)["areas"]}
ok("3. ⭐ every seed area carries ONE label point, inside its own polygon (the map's one label per area)",
   len(_seed_areas) == 9 and all(a["label_point"] and areas.Area(a["area_id"], a["geometry"]).contains(*a["label_point"])
                                 for a in _seed_areas.values()),
   str({n: a["label_point"] for n, a in _seed_areas.items()}))
# NARROWED 13 Oct 2026 (bundle C regenerated the package once): a fresh export lists every tenanted table, so the
# `areas` and `route_area_km` tables are present — EMPTY. The intent holds: the shipped demo carries no area rows.
# REVERSED 17 Oct 2026 (R2, D102): the shipped package is built WITH --with-areas, so the By council view works straight
# after an import with no admin step: the nine seeded areas ship (8 districts and the county, the seed's own ids); the
# clip (route_area_km) stays empty until a bake. The generator's option is still off by default (checked below).
_seed_ids = sorted(f["properties"]["area_id"] for f in seed["features"])
ok("3. ⭐ the shipped demo package carries the nine seeded area ROWS (D102) and no clip rows (no geometry until a bake)",
   sorted(a["area_id"] for a in (_pkg["tables"].get("areas") or [])) == _seed_ids and len(_seed_ids) == 9
   and not (_pkg["tables"].get("route_area_km") or []))
gen = read("backend/tools/make_demo_tenant.py")
ok("3. the demo generator has the documented --with-areas option, off by default, through areas.import_collection",
   'ap.add_argument("--with-areas", action="store_true"' in gen and "def build(with_areas=False, out=None):" in gen
   and "areas.import_collection(json.load(f), replace=True)" in gen and "OPTION --with-areas" in gen
   and 'AREAS_SEED = os.path.join(BACKEND, "data", "areas_demo.geojson")' in gen)
ok("3. ...and --out, so trying the option does not rewrite the shipped package",
   'ap.add_argument("--out"' in gen and "shipped package is not rewritten" in gen)

# =========================================================================== #
#  4. A synthetic network: the stored clip                                     #
# =========================================================================== #
boot()
# W | E side by side over 52.5-52.6; S below both; the county C covers all three
FC = {"type": "FeatureCollection", "name": "test squares", "attribution": ["Test boundaries, made up"], "features": [
    {"type": "Feature", "properties": {"area_id": "W", "name": "Westshire", "tier": "district",
                                       "highway_authority": "Test County Council"}, "geometry": poly(box(-1.0, 52.5, -0.9, 52.6))},
    {"type": "Feature", "properties": {"area_id": "E", "name": "Eastshire", "tier": "district"}, "geometry": poly(box(-0.9, 52.5, -0.8, 52.6))},
    {"type": "Feature", "properties": {"area_id": "S", "name": "Southshire", "tier": "district"}, "geometry": poly(box(-1.0, 52.4, -0.8, 52.5))},
    {"type": "Feature", "properties": {"area_id": "C", "name": "Testshire", "tier": "county"}, "geometry": poly(box(-1.0, 52.4, -0.8, 52.6))},
]}
q1 = network.create_location("Pit West", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=[BAL])
d1 = network.create_location("Yard East", "destination", lat=52.55, lon=-0.85, loc_type="Compound", receives=[BAL])
q2 = network.create_location("Pit North", "origin", lat=52.58, lon=-0.98, loc_type="Quarry", supplies=[BAL])
d2 = network.create_location("Yard North", "destination", lat=52.58, lon=-0.92, loc_type="Compound", receives=[BAL])
far = network.create_location("Far Away", "destination", lat=51.0, lon=0.6, loc_type="Compound", receives=[BAL])
r1 = network.create_route(q1["id"], d1["id"], material_category=BAL, route_id="R001", ipt="IPT1")["id"]
r2 = network.create_route(q2["id"], d2["id"], material_category=BAL, route_id="R002", ipt="IPT2")["id"]
r3 = network.create_route(q1["id"], d2["id"], material_category=BAL, route_id="R003", ipt="IPT1")["id"]   # never baked
r4 = network.create_route(q1["id"], far["id"], material_category=BAL, route_id="R004", ipt="IPT1")["id"]  # outside every area

R1 = [[round(-0.95 + 0.01 * i, 6), 52.55] for i in range(11)]          # W -> E across -0.90
R1_RET = list(reversed(R1))
R2 = [[round(-0.98 + 0.01 * i, 6), 52.58] for i in range(7)]           # wholly in W
R2_RET = [[-0.92, 52.58], [-0.92, 52.45], [-0.98, 52.45], [-0.98, 52.58]]   # back via S: a return leg in another area
R4 = [[0.5, 51.0], [0.6, 51.0]]


def add_geom(rid, pts, leg="loaded", profile=PROFILE, alt=0):
    db.execute(
        "INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
        "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), rid, profile, leg, alt, json.dumps(pts), round(plen(pts), 3), 1.0, "2026-10-12T00:00:00Z"))


add_geom(r1, R1); add_geom(r1, R1_RET, leg="return")
add_geom(r2, R2); add_geom(r2, R2_RET, leg="return")
add_geom(r4, R4); add_geom(r4, list(reversed(R4)), leg="return")
add_geom(r1, [[-0.95, 52.55], [-0.95, 52.45]], alt=1)                    # an alternative: never clipped
add_geom(r1, [[-0.85, 52.58], [-0.82, 52.58]], profile=RIGID)            # another profile, wholly in E
ok("4. no areas yet: the clip stores nothing", areas.rebuild()["rows"] == 0 and areas.status()["legs_clipped"] == 0)
imp = areas.import_collection(FC)
ok("4. ⭐ the areas import re-clips at once: 4 areas, every primary leg clipped",
   imp["imported"] == 4 and imp["tiers"] == {"district": 3, "county": 1} and imp["clip"]["legs_clipped"] == 7,
   str(imp["clip"]))
CL = areas.clip_table()


def kin(rid, leg, aid, profile=PROFILE):
    return ((CL.get(rid) or {}).get(profile) or {}).get(leg, {}).get(aid, 0.0)


half = plen(R1) / 2
ok("4. ⭐ R001's laden leg: half in Westshire, half in Eastshire (the boundary at -0.90 is its middle)",
   abs(kin("R001", "loaded", "W") - half) < 1e-3 and abs(kin("R001", "loaded", "E") - half) < 1e-3,
   f"{kin('R001', 'loaded', 'W')} {kin('R001', 'loaded', 'E')} vs {half}")
ok("4. ...all of it in the county, and the whole-leg row carries its length",
   abs(kin("R001", "loaded", "C") - plen(R1)) < 1e-3 and abs(kin("R001", "loaded", "*") - plen(R1)) < 1e-3)
ok("4. ...and nothing in Southshire", kin("R001", "loaded", "S") == 0.0 and "S" not in CL["R001"][PROFILE]["loaded"])
w_ret = hav([-0.92, 52.58], [-0.92, 52.5]) + hav([-0.98, 52.5], [-0.98, 52.58])
s_ret = hav([-0.92, 52.5], [-0.92, 52.45]) + hav([-0.92, 52.45], [-0.98, 52.45]) + hav([-0.98, 52.45], [-0.98, 52.5])
ok("4. ⭐ R002's return leg in another area: its km in Southshire and the rest in Westshire, the two adding to the leg",
   abs(kin("R002", "return", "S") - s_ret) < 1e-3 and abs(kin("R002", "return", "W") - w_ret) < 1e-3
   and abs(kin("R002", "return", "S") + kin("R002", "return", "W") - plen(R2_RET)) < 1e-3
   and kin("R002", "loaded", "S") == 0.0, f"{kin('R002', 'return', 'S')} vs {s_ret}")
ok("4. R004 (outside every area) has its whole-leg rows and no area row",
   set(CL["R004"][PROFILE]["loaded"]) == {"*"} and set(CL["R004"][PROFILE]["return"]) == {"*"})
ok("4. the never-baked R003 has no row at all", "R003" not in CL)
ok("4. the alternative (alt 1) was never clipped: R001 has nothing in Southshire on any leg",
   all("S" not in legs.get("loaded", {}) for legs in CL["R001"].values()))
ok("4. every profile is clipped: R001 on the rigid is wholly in Eastshire",
   abs(kin("R001", "loaded", "E", RIGID) - hav([-0.85, 52.58], [-0.82, 52.58])) < 1e-3 and kin("R001", "loaded", "W", RIGID) == 0.0)
rows = db.query("SELECT * FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),))
ok("4. the rows are stamped with the tenant and a build time", rows and all(r["tenant_id"] == db.current_tenant() and r["built_at"] for r in rows))

# rebuilt by the bake path: the one hook road_sections owns
db.execute("DELETE FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),))
network._upsert_geom(r2, PROFILE, json.dumps(R2), round(plen(R2), 3), 1.0, None, leg="loaded", alt_index=0)
ok("4. ⭐ _upsert_geom of a primary geometry re-clips without being asked (through road_sections' one hook)",
   abs(kin("R001", "loaded", "W") - half) < 1e-3 and areas.clip_table().get("R002", {}).get(PROFILE, {}).get("loaded", {}).get("W", 0) > 0)
network.clear_geometry(route_id=r4)
ok("4. clear_geometry re-clips: R004's rows are gone", "R004" not in areas.clip_table())
add_geom(r4, R4); add_geom(r4, list(reversed(R4)), leg="return")
_real_ab = areas.rebuild
_calls = []
areas.rebuild = lambda: (_calls.append(1), _real_ab())[1]
try:
    with road_sections.batched("test"):
        network._upsert_geom(r1, PROFILE, json.dumps(R1), round(plen(R1), 3), 1.0, None, leg="loaded", alt_index=0)
        network._upsert_geom(r2, PROFILE, json.dumps(R2), round(plen(R2), 3), 1.0, None, leg="loaded", alt_index=0)
        ok("4. inside a bake batch an upsert does not re-clip", _calls == [], str(_calls))
    ok("4. ⭐ ...and the batch's end re-clips ONCE for two upserts (the same deferral as the sections)", _calls == [1], str(_calls))
finally:
    areas.rebuild = _real_ab
ok("4. after the batch R004 is clipped again (the hook's rebuild reads the geometry as it now is)",
   set(areas.clip_table()["R004"][PROFILE]["loaded"]) == {"*"})
rs_src = read("backend/road_sections.py")
ok("4. the hook source: road_sections._rebuild_quietly calls the areas re-clip after its own rebuild, never raising",
   "_rebuild_areas(where)\n    return res" in rs_src and "areas.rebuild_quietly(where)" in rs_src
   and 'print(f"road_sections: council areas not re-clipped after {where}: {e}")' in rs_src)
ok("4. areas.rebuild_quietly never raises into the bake",
   'print(f"areas: route_area_km not rebuilt after {where}: {e}")' in read("backend/areas.py"))
# the clip is one transaction: a failing INSERT leaves the previous index whole
_before = sorted((r["route_id"], r["vehicle_profile"], r["leg"], r["area_id"]) for r in db.query(
    "SELECT * FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),)))
_real_compute = areas.compute
areas.compute = lambda: (lambda rr: rr + [rr[0]])(_real_compute())      # one row twice: the INSERT collides
try:
    areas.rebuild()
    ok("4. a clip whose INSERT fails raises", False)
except Exception:
    ok("4. a clip whose INSERT fails raises", True)
finally:
    areas.compute = _real_compute
_after = sorted((r["route_id"], r["vehicle_profile"], r["leg"], r["area_id"]) for r in db.query(
    "SELECT * FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),)))
ok("4. ⭐ ...and the stored clip is the previous one, whole (one transaction)", _after == _before and len(_before) > 10)

# =========================================================================== #
#  5. The month read                                                           #
# =========================================================================== #
factors = conversions.load_factors()
WD = float(factors["planning"]["working_days_per_month"])
PAYLOAD = float(factors["vehicles"][PROFILE]["payload_t"])
M = 10


def add_line(fid, rid, qty, ipt="IPT1", month=M, status="Approved", vehicle=PROFILE, section=""):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), fid, rid, month, "superstructure", section, qty, "t", BAL, "Type 1", vehicle,
                "test", status, None, ipt))


add_line("F1", r1, 100 * PAYLOAD)
add_line("F2", r2, 50 * PAYLOAD, ipt="IPT2")
add_line("F3", r3, 30 * PAYLOAD)                      # an unbaked line: never in an area
add_line("F4", r4, 20 * PAYLOAD)
add_line("F5", r1, 999 * PAYLOAD, status="Pending", section="WS9")   # not approved: never counts
add_line("F6", r1, 10 * PAYLOAD, month=11)            # another month

P = main.public_month_kpis(month=M)
co2 = {}
for l in P["lines"]:
    co2[l["route_id"]] = co2.get(l["route_id"], 0.0) + (l["co2_t"] or 0.0)
ok("5. fixture: the bar's payload gives R001 and R002 carbon from both legs; R003 has none (unbaked)",
   co2["R001"] > 0 and co2["R002"] > 0 and co2.get("R003", 0) == 0 and P["working_days"] == WD)
pay = areas.area_load(M, working_days=WD)
A_ = {a["area_id"]: a for a in pay["areas"]}
ok("5. one entry per area, districts before the county", [a["area_id"] for a in pay["areas"]] == ["E", "S", "W", "C"],
   str([a["area_id"] for a in pay["areas"]]))
ok("5. ⭐ Westshire: R001 (100) and R002 (50) both enter laden: (100 + 50) loads / working days",
   A_["W"]["routes"] == ["R001", "R002"] and A_["W"]["loads"] == 150 and A_["W"]["movements_per_day"] == round(150 / WD, 2))
ok("5. ⭐ Eastshire: R001's 100 loads count there too — a route counts in every area its laden leg enters",
   A_["E"]["routes"] == ["R001"] and A_["E"]["movements_per_day"] == round(100 / WD, 2))
ok("5. 🔴 ...and NEVER doubled for the return leg: Westshire is not (100 + 50) × 2",
   A_["W"]["movements_per_day"] != round(300 / WD, 2) and A_["E"]["movements_per_day"] != round(200 / WD, 2))
ok("5. ⭐ Southshire, where only R002's EMPTY return runs: no movement, the route named as return-only",
   A_["S"]["movements_per_day"] == 0 and A_["S"]["routes"] == [] and A_["S"]["return_only_routes"] == ["R002"])
ok("5. ...but its lorry-km are there (50 loads × the return km inside), and no laden lorry-km",
   abs(A_["S"]["lorry_km"] - round(50 * s_ret, 1)) <= 0.11 and A_["S"]["laden_lorry_km"] == 0,
   f"{A_['S']['lorry_km']} vs {50 * s_ret}")
ok("5. Westshire's lorry-km: laden and empty km inside × loads",
   abs(A_["W"]["lorry_km"] - round(100 * (half + half) + 50 * (plen(R2) + w_ret), 1)) <= 0.11
   and abs(A_["W"]["laden_lorry_km"] - round(100 * half + 50 * plen(R2), 1)) <= 0.11)
ok("5. ⭐ the county counts each laden route once: (100 + 50) / wd, the same as the scheme's drawn routes in it",
   A_["C"]["movements_per_day"] == round(150 / WD, 2) and A_["C"]["routes"] == ["R001", "R002"])
ok("5. the districts' movements add up to MORE than the scheme's — and the basis sentence says so",
   A_["W"]["loads"] + A_["E"]["loads"] + A_["S"]["loads"] == 250 and pay["totals"]["loads"] == 170
   and "add up to more than the scheme's" in pay["basis"] and "one load = one two-way movement" in pay["basis"])
ok("5. ⭐ the unbaked line (R003) is in no area and in no figure — named in routes_not_drawn",
   all("R003" not in a["routes"] + a["return_only_routes"] for a in pay["areas"])
   and pay["routes_not_drawn"] == ["R003"] and pay["totals"]["loads"] == 170
   and any("not routed yet" in n for n in pay["notes"]), str(pay["notes"]))   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): "not routed yet"
ok("5. the Pending line and the other month's line do not count", A_["E"]["loads"] == 100)
ok("5. R004, outside every area, is in the scheme totals (170 = 100 + 50 + 20) and in no area",
   all("R004" not in a["routes"] for a in pay["areas"]) and pay["totals"]["routes_with_volume"] == 3)
# carbon
L1, L1R = plen(R1), plen(R1_RET)
L2, L2R = plen(R2), plen(R2_RET)
exp_W = co2["R001"] * (half + half) / (L1 + L1R) + co2["R002"] * (L2 + w_ret) / (L2 + L2R)
exp_E = co2["R001"] * (half + half) / (L1 + L1R)
exp_S = co2["R002"] * s_ret / (L2 + L2R)
ok("5. ⭐ CO2e in an area = Σ route CO2e × (laden + return km inside) / the route's two-way length",
   abs(A_["W"]["co2_t"] - exp_W) < 2e-3 and abs(A_["E"]["co2_t"] - exp_E) < 2e-3 and abs(A_["S"]["co2_t"] - exp_S) < 2e-3,
   f"W {A_['W']['co2_t']} vs {exp_W}; E {A_['E']['co2_t']} vs {exp_E}; S {A_['S']['co2_t']} vs {exp_S}")
ok("5. ⭐ the apportionment sums to the routes' totals over the district tier (W + E + S = R001 + R002, to the kg)",
   abs(A_["W"]["co2_t"] + A_["E"]["co2_t"] + A_["S"]["co2_t"] - (co2["R001"] + co2["R002"])) < 2e-3
   and abs(pay["totals"]["co2_t_by_tier"]["district"] - (co2["R001"] + co2["R002"])) < 2e-3)
ok("5. ...and over the county tier too (one county covers both routes)", abs(A_["C"]["co2_t"] - (co2["R001"] + co2["R002"])) < 2e-3)
ok("5. ...the scheme's CO2e includes R004's, which is emitted in no area",
   abs(pay["totals"]["co2_t"] - (co2["R001"] + co2["R002"] + co2["R004"])) < 2e-3 and co2["R004"] > 0)
exp_W_laden_only = co2["R001"] * half / L1 + co2["R002"] * L2 / L2
ok("5. 🔴 NOT the laden-length split (km inside ÷ laden km), which puts the empty return's carbon where the laden leg runs",
   abs(A_["W"]["co2_t"] - exp_W_laden_only) > 0.01 and exp_S > 0, f"{A_['W']['co2_t']} vs laden-only {exp_W_laden_only}")
ok("5. CO2e a day = the month's / working days", A_["W"]["co2_t_per_day"] == round(A_["W"]["co2_t"] / WD, 3))
ok("5. ⭐ each route on the profile the map DRAWS (the default here): the rigid's Eastshire-only geometry is not used",
   A_["W"]["routes"] == ["R001", "R002"] and abs(A_["E"]["co2_t"] - exp_E) < 2e-3)
ok("5. the payload carries the polygon, the tier words, the highway authority and the licence lines",
   A_["W"]["geometry"]["type"] == "Polygon" and A_["W"]["tier_words"] == "local authority district"
   and A_["C"]["tier_words"] == "county or unitary authority" and A_["W"]["highway_authority"] == "Test County Council"
   and pay["attribution"] == ["Test boundaries, made up"])
ok("5. the sites inside each area by point-in-polygon", A_["W"]["sites"] == ["Pit North", "Pit West", "Yard North"]
   and A_["E"]["sites"] == ["Yard East"] and A_["C"]["sites_count"] == 4, str(A_["W"]["sites"]))
ok("5. the totals carry the tenant's sites with coordinates (5, Far Away included), the card's 'of N'",
   pay["totals"]["sites"] == 5, str(pay["totals"].get("sites")))
ok("5. the carbon stamp is the Carbon page's, read from carbon.py, and the rule names the two-way split",
   pay["carbon"]["stamp"] == road_sections._carbon_stamp() and "two-way length" in pay["carbon"]["rule"]
   and "Never kg per tonne per council" in pay["co2_basis"])
blob = json.dumps(pay)
ok("5. 🔴 no team id anywhere in the payload (the card names no team)", not TEAM_ID.search(blob) and "IPT" not in blob)
ok("5. working days not handed in: the payload's own figure (main._working_days, the one reader)",
   areas.area_load(M)["working_days"] == WD == main._working_days(conversions.load_factors()))
nov = areas.area_load(11, working_days=WD)
ok("5. November: R001's 10 loads only", {a["area_id"]: a["loads"] for a in nov["areas"]} == {"E": 10, "S": 0, "W": 10, "C": 10})
emp = areas.area_load(1, working_days=WD)
ok("5. a month with no volume: every area 0 movements and 0.0 t (a true zero, nothing approved runs), and a note",
   all(a["movements_per_day"] == 0 and a["co2_t"] == 0.0 for a in emp["areas"])
   and "No approved volume in this month." in emp["notes"])
# a route with volume but no clip yet (geometry arrived and the clip has not run)
db.execute("DELETE FROM route_area_km WHERE tenant_id = ? AND route_id = ?", (db.current_tenant(), "R004"))
nc = areas.area_load(M, working_days=WD)
ok("5. a route with volume and no clip is named in routes_not_clipped with a sentence, never invented",
   nc["routes_not_clipped"] == ["R004"] and any("not placed in a council yet" in n for n in nc["notes"]))   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): no "clip" on the map
areas.rebuild()
# no carbon on a route's lines (not stored for the lines' vehicle): None, never 0.0
add_line("F7", r2, 5 * PAYLOAD, month=2, vehicle=RIGID)
feb = {a["area_id"]: a for a in areas.area_load(2, working_days=WD)["areas"]}
ok("5. ⭐ an area whose only route carries no carbon reads co2_t None, never 0.0 t, and names the route",
   feb["S"]["co2_t"] is None and feb["S"]["co2_routes_unbaked"] == ["R002"] and feb["W"]["co2_t"] is None
   and feb["E"]["co2_t"] == 0.0, str({k: v["co2_t"] for k, v in feb.items()}))
# the carbon read fails
_real_lines = costlines.lines
costlines.lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("factors document broken"))
try:
    br = areas.area_load(M, working_days=WD)
    ok("5. ⭐ when the carbon read fails: movements intact, every CO2e None (never 0), co2_error carried, a note",
       br["areas"][0]["movements_per_day"] > 0 and all(a["co2_t"] is None for a in br["areas"])
       and br["totals"]["co2_t"] is None and all(v is None for v in br["totals"]["co2_t_by_tier"].values())
       and "RuntimeError" in str(br.get("co2_error", ""))   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): the note no longer points at a field name
       and any("The carbon figures could not be read" in n for n in br["notes"]) and not any("co2_error" in n for n in br["notes"]))
except Exception as e:  # pragma: no cover
    ok("5. ⭐ when the carbon read fails: movements intact, every CO2e None (never 0), co2_error carried, a note", False, repr(e))
finally:
    costlines.lines = _real_lines

# 12 Oct 2026 (Track C review): a laden leg that grazes an area — inside by under ENTER_KM (200 m), as a road beside a
# generalised (BSC, 200 m) boundary does — adds its km and carbon there but NOT the route's whole daily movements
_dip = areas.Area("D", poly(box(0.0, 0.0, 1.0, 1.0)))
_graze = [[-0.001, 0.5], [0.0003, 0.5003], [-0.001, 0.5006]]          # about 20 m over the line and back
ok("5. the clip of a road that strays 20 m over a boundary is under ENTER_KM (and over MIN_KM, so its km still count)",
   areas.MIN_KM <= areas.clip_km(_graze, _dip) < areas.ENTER_KM, str(areas.clip_km(_graze, _dip)))
_before = {a["area_id"]: a for a in areas.area_load(M, working_days=WD)["areas"]}
_e_r1 = db.query("SELECT km FROM route_area_km WHERE tenant_id = ? AND route_id = 'R001' AND leg = 'loaded' AND area_id = 'E'",
                 (db.current_tenant(),))
db.execute("UPDATE route_area_km SET km = 0.05 WHERE tenant_id = ? AND route_id = 'R001' AND leg = 'loaded' AND area_id = 'E'",
           (db.current_tenant(),))
_g = {a["area_id"]: a for a in areas.area_load(M, working_days=WD)["areas"]}
ok("5. ⭐ a laden leg inside an area by 50 m adds NO movements there: the route is an edge route, not one that enters",
   bool(_e_r1) and "R001" in _before["E"]["routes"] and "R001" not in _g["E"]["routes"] and _g["E"]["edge_routes"] == ["R001"]
   and _g["E"]["loads"] < _before["E"]["loads"] and _g["W"]["loads"] == _before["W"]["loads"],
   str((_g["E"]["routes"], _g["E"]["edge_routes"], _g["E"]["loads"], _before["E"]["loads"])))
ok("5. ...its carbon there still counts, split by its km inside (the DESNZ split is by km, not by entry)",
   _g["E"]["co2_t"] is not None and _g["E"]["co2_t"] > 0 and "R001" not in _g["E"]["co2_routes_unbaked"])
ok("5. ...and the basis sentence says which threshold applies", "at least 200 m" in areas.area_load(M, working_days=WD)["basis"]
   and areas.area_load(M, working_days=WD)["enter_km"] == 0.2)
areas.rebuild()
ok("5. (the clip restored)", {a["area_id"]: a["routes"] for a in areas.area_load(M, working_days=WD)["areas"]}
   == {a["area_id"]: a["routes"] for a in _before.values()})
# the polygons once, the figures per month (Play no longer re-sends every polygon)
_real_ml = road_sections.month_lines
road_sections.month_lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("shapes must not read a month"))
try:
    _sh = areas.shapes()
    ok("5. ⭐ shapes(): every area's polygon, label point and licence lines, with NO month roll-up (month_lines never called)",
       [a["area_id"] for a in _sh["areas"]] == [a["area_id"] for a in areas.stored_areas()]
       and all(a["geometry"]["type"] in ("Polygon", "MultiPolygon") and isinstance(a["label_point"], list) for a in _sh["areas"])
       and "movements_per_day" not in _sh["areas"][0] and _sh["attribution"] == ["Test boundaries, made up"])
except Exception as e:  # pragma: no cover
    ok("5. ⭐ shapes(): every area's polygon, label point and licence lines, with NO month roll-up (month_lines never called)", False, repr(e))
finally:
    road_sections.month_lines = _real_ml
_ng = areas.area_load(M, working_days=WD, geometry=False)
ok("5. area_load(geometry=False): the same figures without the polygons or label points",
   all("geometry" not in a and "label_point" not in a for a in _ng["areas"])
   and [(a["area_id"], a["movements_per_day"], a["co2_t"]) for a in _ng["areas"]]
   == [(a["area_id"], a["movements_per_day"], a["co2_t"]) for a in areas.area_load(M, working_days=WD)["areas"]])

# =========================================================================== #
#  5b. 19 Oct 2026 — every month in one read (the user: "the council heat map  #
#      doesn't seem to work": 3.7-7.4 s a month on Render, longer than Play)   #
# =========================================================================== #
_all = areas.area_load_all(WD, main.MONTH_COUNT)
_diff = [m for m in range(1, main.MONTH_COUNT + 1)
         if json.dumps(areas.unpack_month(_all, m), sort_keys=True)
         != json.dumps(areas.area_load(m, working_days=WD, geometry=False), sort_keys=True)]
ok("5b. ⭐ area_load_all(): EVERY month unpacks to exactly area_load(m, geometry=False) — all " + str(main.MONTH_COUNT) + " months",
   _diff == [] and len(_all["months"]) == main.MONTH_COUNT, str(_diff[:10]))
ok("5b. ...and the month with routes in this file carries figures (not a vacuous pass)",
   any(a["movements_per_day"] > 0 for a in areas.unpack_month(_all, M)["areas"]))
ok("5b. the pack sends what every month shares ONCE (basis, stops, attribution, carbon, working days) and each area's fixed fields once",
   set(_all["common"]) == set(areas.ALL_COMMON_KEYS)
   and all(not (set(e) & set(areas.ALL_COMMON_KEYS)) for e in _all["months"].values())
   and all(not (set(a) & set(areas.ALL_AREA_FIXED_KEYS)) for e in _all["months"].values() for a in e["areas"])
   and set(_all["area_fixed"]) == {a["area_id"] for a in areas.area_load(M, working_days=WD, geometry=False)["areas"]})
ok("5b. unpack_month() of a month outside the pack is None, never an empty month dressed as a figure",
   areas.unpack_month(_all, main.MONTH_COUNT + 1) is None)
_kpl = {}
_by, _err = main.approved_lines_by_month()
for _m in range(1, main.MONTH_COUNT + 1):
    _one = main.public_month_kpis(month=_m, unit="vehicles")
    _kpl[_m] = [{k: v for k, v in l.items() if k != "trips_per_vehicle_day"} for l in _one["lines"]]
ok("5b. ⭐ approved_lines_by_month(): every month's lines equal the month read's (/api/public/month-kpis) less trips a vehicle-day",
   all(_kpl[_m] == _by.get(_m, []) for _m in _kpl) and sum(len(v) for v in _by.values()) > 0 and _err is None)
ok("5b. the month read and the every-month read build a line with ONE function (_month_kpi_line)",
   read("backend/main.py").count("= _month_kpi_line(r, ") == 2 and "def _month_kpi_line(r, unit, factors, vs, fb_payload, fb_name):" in read("backend/main.py"))
ok("5b. the every-month read makes ONE forecast query and ONE carbon read for the horizon (no route_analysis)",
   "_approved_co2(factors, 1, MONTH_COUNT)" in read("backend/main.py")
   and "network.route_analysis(" not in read("backend/main.py").split("def approved_lines_by_month():", 1)[1].split("\ndef ", 1)[0]
   and read("backend/main.py").split("def approved_lines_by_month():", 1)[1].split("\ndef ", 1)[0].count("db.query(") == 1)
# a carbon read that fails: every month says so, as the month read does
_real_co2 = main._approved_co2
try:
    main._approved_co2 = lambda f, a, b: ({}, "The carbon figures could not be read (Boom).")
    _allf = areas.area_load_all(WD, main.MONTH_COUNT)
    _mf = areas.unpack_month(_allf, M)
    ok("5b. a failed carbon read: every month carries co2_error and no CO2e figure (never a zero)",
       all(e.get("co2_error") == "The carbon figures could not be read (Boom)." for e in _allf["months"].values())
       and all(a["co2_t"] is None for a in _mf["areas"]))
finally:
    main._approved_co2 = _real_co2

# =========================================================================== #
#  6. The endpoints (bodies) and the gate scope                                #
# =========================================================================== #
ok("6. ⭐ /api/public/areas is behind the map scope", gate.scope_for("/api/public/areas?month=10") == "map"
   and gate.scope_for("/api/public/areas") == "map")
ok("6. ⭐ /api/public/areas/shapes is behind the map scope too, and its body is shapes()",
   gate.scope_for("/api/public/areas/shapes") == "map" and main.public_area_shapes() == areas.shapes()
   and '@app.get("/api/public/areas/shapes")' in read("backend/main.py"))
# NARROWED 22 Oct 2026 (read_cache): the endpoint now answers the JSON bytes it keeps, so its body is parsed first
ok("6. ⭐ /api/public/areas/months (19 Oct) is behind the map scope, and its body is area_load_all() for the whole horizon",
   gate.scope_for("/api/public/areas/months") == "map"
   and json.dumps(json.loads(main.public_areas_months().body), sort_keys=True) == json.dumps(areas.area_load_all(WD, main.MONTH_COUNT), sort_keys=True)
   and '@app.get("/api/public/areas/months")' in read("backend/main.py"))
ok("6. the admin paths are not the map's (they are token-protected)",
   gate.scope_for("/api/admin/areas/import?token=x") is None and gate.scope_for("/api/admin/areas") is None)
body = main.public_areas(month=M)
ok("6. the public endpoint body serves the month with the one working-days reader",
   body["working_days"] == main._working_days(conversions.load_factors()) and len(body["areas"]) == 4)
os.environ["ADMIN_TOKEN"] = "adm-test"
for fn, label in ((lambda t: main.areas_import(FC, token=t), "import"), (lambda t: main.areas_list(token=t), "list")):
    for bad in ("wrong", None, "é-adm"):
        try:
            fn(bad)
            ok(f"6. 🔴 admin {label} refuses the token {bad!r}", False)
        except _HTTPException as e:
            ok(f"6. 🔴 admin {label} refuses the token {bad!r}", e.status_code == 403)
try:
    main.areas_import(_noattr, token="adm-test")
    ok("6. the import refuses a bad collection with 400 and the reason", False)
except _HTTPException as e:
    ok("6. the import refuses a bad collection with 400 and the reason", e.status_code == 400 and "licence lines" in e.detail)
lst = main.areas_list(token="adm-test")
ok("6. the admin list: every area without its geometry, with vertices, box and the routes whose laden leg enters it",
   [a["area_id"] for a in lst["areas"]] == ["E", "S", "W", "C"] and "geometry" not in lst["areas"][0]
   and {a["area_id"]: a["routes_entering"] for a in lst["areas"]}["W"] == ["R001", "R002"]
   and {a["area_id"]: a["routes_entering"] for a in lst["areas"]}["S"] == []
   and lst["areas"][0]["vertices"] == 5 and lst["status"]["areas"] == {"district": 3, "county": 1})
FC2 = json.loads(json.dumps(FC)); FC2["features"] = [FC2["features"][0]]
FC2["features"][0]["properties"]["name"] = "Westshire (renamed)"
r_up = main.areas_import(FC2, token="adm-test")
ok("6. a re-import of one id replaces that area and keeps the others",
   r_up["imported"] == 1 and len(areas.stored_areas()) == 4
   and {a["area_id"]: a["name"] for a in areas.stored_areas()}["W"] == "Westshire (renamed)")
r_rep = main.areas_import(FC2, replace=1, token="adm-test")
ok("6. replace=1 clears every area first and re-clips (only W left, no row for E, S or C)",
   r_rep["replaced"] and [a["area_id"] for a in areas.stored_areas()] == ["W"]
   and not db.query("SELECT 1 FROM route_area_km WHERE tenant_id = ? AND area_id IN ('E', 'S', 'C')", (db.current_tenant(),)))
main.areas_import(FC, replace=1, token="adm-test")
os.environ.pop("ADMIN_TOKEN", None)
src_main = read("backend/main.py")
ok("6. main.py registers the three routes", all(s in src_main for s in (
    '@app.get("/api/public/areas")', '@app.post("/api/admin/areas/import")', '@app.get("/api/admin/areas")')))
# NARROWED 12 Oct 2026 (Track C review): the call may also pass geometry=bool(geometry) (the figures-only month read)
ok("6. the public endpoint hands _working_days() in — one reader of the figure",
   re.search(r"areas\.area_load\(int\(month\), working_days=_working_days\(factors\)(, geometry=bool\(geometry\))?\)", src_main) is not None)

# =========================================================================== #
#  6b. 22 Oct 2026 — the read cache (read_cache.py): the first council view on #
#      live waited 7-11 s; now built once per data version, never stale        #
# =========================================================================== #
import threading  # noqa: E402
import read_cache  # noqa: E402


def months_body():
    """The endpoint's body as the browser gets it (bytes) and parsed."""
    r = main.public_areas_months()
    return r.body, json.loads(r.body.decode("utf-8"))


def fresh():
    """What the every-month read is RIGHT NOW, built from the database with no cache."""
    return read_cache.json_bytes(areas.area_load_all(WD, main.MONTH_COUNT))


def w_loads(body):
    return {a["area_id"]: a["loads"] for a in json.loads(body)["months"][str(M)]["areas"]}


read_cache.clear()
_b0 = dict(read_cache.STATS)
_body1, _js1 = months_body()
_b1 = dict(read_cache.STATS)
_n = [0]
_real_run = db._run


def _count_run(sql, params, fetch):
    _n[0] += 1
    return _real_run(sql, params, fetch)


_heavy_calls = []
_real_heavy = main._heavy
db._run = _count_run
main._heavy = lambda name: (_heavy_calls.append(name), _real_heavy(name))[1]
try:
    _body2, _js2 = months_body()
finally:
    db._run = _real_run
    main._heavy = _real_heavy
_b2 = dict(read_cache.STATS)
ok("6b. ⭐ the first read builds once; a second read is a cache hit with the IDENTICAL bytes",
   _b1["builds"] == _b0["builds"] + 1 and _b2["builds"] == _b1["builds"] and _b2["hits"] == _b1["hits"] + 1
   and _body2 == _body1)
ok("6b. ⭐ ...and those bytes are exactly the uncached read (area_load_all, as JSONResponse would encode it)",
   _body1 == fresh() and _js1 == areas.area_load_all(WD, main.MONTH_COUNT))
ok("6b. ...the cached body parses to every month and unpacks like the month read (not a vacuous pass)",
   len(_js1["months"]) == main.MONTH_COUNT and w_loads(_body1).get("W") == 150
   and json.dumps(areas.unpack_month(_js1, M), sort_keys=True)
   == json.dumps(areas.area_load(M, working_days=WD, geometry=False), sort_keys=True))
ok("6b. ⭐ a hit asks the database nothing beyond the config (0 or 1 query) and takes no heavy-read slot",
   _n[0] <= 1 and _heavy_calls == [], f"{_n[0]} queries, slots {_heavy_calls}")
ok("6b. the endpoint answers application/json bytes (FastAPI's own separators, UTF-8)",
   main.public_areas_months().media_type == "application/json" and isinstance(_body1, bytes)
   and b'": ' not in _body1[:2000] and _body1.startswith(b"{"))


def after_write(label, write, undo=None, changes=True):
    """Read (cached), write, read again: the second read must be rebuilt and equal the database now."""
    before, _ = months_body()
    months_body()                                    # a hit, so the next miss is the write's doing
    v0, b0 = db.data_version(), read_cache.STATS["builds"]
    write()
    after, _ = months_body()
    ok(f"6b. ⭐ {label}: the next read is rebuilt (data version moved, one build) and equals the database now",
       db.data_version() > v0 and read_cache.STATS["builds"] == b0 + 1 and after == fresh())
    if changes:
        ok(f"6b. ...{label}: the figures DID change, so the old cached body would have been stale",
           after != before)
    if undo:
        undo()
        back, _ = months_body()
        ok(f"6b. ...{label} undone: the read is back to the first figures", back == before and back == fresh())


# a forecast: F2 (R002, 50 loads into Westshire) un-approved, as the approve / reject endpoints write it
after_write("an approved line set back to Pending",
            lambda: db.execute("UPDATE forecasts SET status = 'Pending' WHERE tenant_id = ? AND id = 'F2'", (db.current_tenant(),)),
            lambda: db.execute("UPDATE forecasts SET status = 'Approved' WHERE tenant_id = ? AND id = 'F2'", (db.current_tenant(),)))
db.execute("UPDATE forecasts SET status = 'Pending' WHERE tenant_id = ? AND id = 'F2'", (db.current_tenant(),))
ok("6b. ⭐ Westshire reads 100 loads with F2 Pending — straight after the write, from the endpoint",
   w_loads(months_body()[0]).get("W") == 100)
db.execute("UPDATE forecasts SET status = 'Approved' WHERE tenant_id = ? AND id = 'F2'", (db.current_tenant(),))
ok("6b. ...and 150 again once it is approved again", w_loads(months_body()[0]).get("W") == 150)
# a new forecast line
after_write("a new approved line",
            lambda: add_line("F9", r1, 7 * PAYLOAD, section="WS7"),
            lambda: db.execute("DELETE FROM forecasts WHERE tenant_id = ? AND id = 'F9'", (db.current_tenant(),)))
# route geometry: R002's stored legs taken away (the map stops drawing it), then put back
_geo = db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ?", (db.current_tenant(), r2))


def _geo_back():
    for g in _geo:
        cols_ = [c for c in g.keys()]
        db.execute(f"INSERT INTO route_geometry ({', '.join(cols_)}) VALUES ({', '.join('?' for _ in cols_)})",
                   tuple(g[c] for c in cols_))


after_write("a route's stored geometry removed",
            lambda: db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = ?", (db.current_tenant(), r2)),
            _geo_back)
# the council areas, through the admin import endpoint's body
os.environ["ADMIN_TOKEN"] = "adm-test"
after_write("a council area renamed by the admin import",
            lambda: main.areas_import(FC2, token="adm-test"),
            lambda: main.areas_import(FC, replace=1, token="adm-test"))
os.environ.pop("ADMIN_TOKEN", None)
# a location: the first site inside an area moved far away, then back
_site = next(l for l in db.query("SELECT id, name, lat, lon FROM locations WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
             if any(l["name"] in (a.get("sites") or []) for a in areas.area_load(M, working_days=WD)["areas"]))
after_write("a site moved",
            lambda: db.execute("UPDATE locations SET lat = ? WHERE tenant_id = ? AND id = ?", (_site["lat"] + 20, db.current_tenant(), _site["id"])),
            lambda: db.execute("UPDATE locations SET lat = ? WHERE tenant_id = ? AND id = ?", (_site["lat"], db.current_tenant(), _site["id"])))
# the config, through config.save (the Config page's Save): the council colour bands
_cfg = json.loads(json.dumps(config.load(conversions, use_cache=False)))
_cfg2 = json.loads(json.dumps(_cfg))
_cfg2.setdefault("tenant", {})["council_breaks"] = {"movements": [3, 6, 9], "carbon": [4, 8, 12]}
after_write("the council bands saved on Config",
            lambda: ok("6b. (the config save itself worked)", config.save(_cfg2, by="test")["ok"]),
            lambda: ok("6b. (the config put back)", config.save(_cfg, by="test")["ok"]))
# working days: the key moves as well as the version
_cfg3 = json.loads(json.dumps(_cfg)); _cfg3["planning"]["working_days_per_month"] = WD + 1
before_wd, _ = months_body()
config.save(_cfg3, by="test")
_wd_body, _wd_js = months_body()
ok("6b. ⭐ working days changed on Config: the read is rebuilt with the new divisor",
   _wd_js["common"]["working_days"] == WD + 1 and _wd_body != before_wd)
config.save(_cfg, by="test")
ok("6b. ...and back", months_body()[0] == before_wd)
# the writers that commit on their own connection
_v = db.data_version()
tenant_package.import_rows("forecasts", [])
ok("6b. ⭐ tenant_package.import_rows (its own connection) bumps the data version even for no rows", db.data_version() > _v)
_v = db.data_version()
limits.init_db()
ok("6b. limits.init_db (its own connection) bumps it", db.data_version() > _v)
_v = db.data_version()
limits.replace_rows("test", (0, 0, 0, 0), [])
ok("6b. limits.replace_rows (its own connection) bumps it", db.data_version() > _v)

# writes that are not figures do NOT throw the cache away (else a staff session's touch would empty it on every page)
db.init_users_db()
months_body()
_v, _b = db.data_version(), read_cache.STATS["builds"]
db.execute("UPDATE user_sessions SET last_seen_at = ? WHERE tenant_id = ? AND token_hash = ?", ("x", db.current_tenant(), "none"))
db.execute_atomic([("DELETE FROM auth_attempts WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "none"))])
months_body()
ok("6b. ⭐ a session touch and the sign-in throttle (NO_DATA_TABLES) leave the version and the cached read alone",
   db.data_version() == _v and read_cache.STATS["builds"] == _b)
# NARROWED 31 Oct 2026 (task 4a PR 3c): + clp_review_groups, clp_reviews (the client's reviewers; no figure is built from them)
# NARROWED 31 Oct 2026 (task 4a PR 3b): + clp_notes, the notes and tasks on each CLP (no kept read is built from them,
# and a note must not end a kept CLP draft)
# NARROWED 31 Oct 2026 (task 4c PR 3): + site_layout_pictures, the pinned pictures (the staff map reads them fresh; moving
# one must not end the kept staff reads)
ok("6b. the tables that do not bump are exactly the account / audit / lead tables, the CLP notes, the reviewers and the pinned pictures",
   db.NO_DATA_TABLES == {"audit_log", "auth_attempts", "auth_tokens", "user_sessions", "users", "demo_requests", "clp_notes",
                         "clp_review_groups", "clp_reviews", "site_layout_pictures"})
ok("6b. ⭐ written_table(): INSERT / INSERT OR REPLACE / REPLACE / UPDATE / DELETE name their table; anything else is None (and bumps)",
   db.written_table("INSERT INTO forecasts (a) VALUES (?)") == "forecasts"
   and db.written_table("  insert or replace into Audit_Log (a) values (?)") == "audit_log"
   and db.written_table("REPLACE INTO users (a) VALUES (?)") == "users"
   and db.written_table("UPDATE user_sessions SET x = 1") == "user_sessions"
   and db.written_table("\nDELETE FROM route_geometry WHERE 1") == "route_geometry"
   and db.written_table("ALTER TABLE locations ADD COLUMN x TEXT") is None
   and db.written_table("WITH x AS (SELECT 1) INSERT INTO users SELECT * FROM x") is None
   and db.written_table(None) is None)
_v = db.data_version()
db.note_write("CREATE TABLE IF NOT EXISTS t_new (a TEXT)")
db.note_write("INSERT INTO some_new_table (a) VALUES (?)")
ok("6b. ⭐ a statement it does not recognise, and a table nobody listed, BUMP (a new table can only cost a rebuild)",
   db.data_version() == _v + 2)
_v = db.data_version()
db.execute_atomic([("UPDATE user_sessions SET last_seen_at = ? WHERE tenant_id = ? AND token_hash = ?", ("y", db.current_tenant(), "none")),
                   ("UPDATE forecasts SET quantity = quantity WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "F1"))])
ok("6b. an atomic set that writes one figure table among account tables bumps", db.data_version() > _v)

# a write that lands WHILE the read is being built: that build is served to its viewer but never kept
_d0 = read_cache.STATS["discarded"]


def _build_with_write():
    db.execute("UPDATE forecasts SET quantity = quantity WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "F1"))
    return b"built-across-a-write"


_got = read_cache.cached("t/midwrite", 1, _build_with_write)
ok("6b. ⭐ a write mid-build: the viewer gets that build, nothing is kept, the next read builds again",
   _got == b"built-across-a-write" and read_cache.STATS["discarded"] == _d0 + 1
   and read_cache.peek("t/midwrite", 1) is None)
ok("6b. ...the version is noted BEFORE the build and the entry kept only if it has not moved (source)",
   read("backend/read_cache.py").index("version = db.data_version()") < read("backend/read_cache.py").index("value = build()")
   and "if db.data_version() == version:" in read("backend/read_cache.py"))
# a different key (other working days, another horizon) never answers from this entry
read_cache.cached("t/key", ("a", 1), lambda: b"one")
ok("6b. a different key is a miss, never the other key's value",
   read_cache.cached("t/key", ("a", 2), lambda: b"two") == b"two" and read_cache.peek("t/key", ("a", 1)) is None)
# per tenant
months_body()
_bt = read_cache.STATS["builds"]
_tok = db.set_current_tenant("other-tenant")
try:
    _other = main.public_areas_months().body
finally:
    db.reset_current_tenant(_tok)
ok("6b. ⭐ another tenant gets its own build (never this tenant's figures): no areas there",
   read_cache.STATS["builds"] == _bt + 1 and json.loads(_other)["area_fixed"] == {} and _other != months_body()[0])
ok("6b. ...and this tenant's entry is still there afterwards (one entry per tenant)", read_cache.STATS["builds"] == _bt + 1)

# single-flight: four first viewers at once build it once
_sf = [0]


def _slow():
    import time as _t
    _sf[0] += 1
    _t.sleep(0.3)
    return b"slow"


_res = []
_ths = [threading.Thread(target=lambda: _res.append(read_cache.cached("t/sf", 1, _slow))) for _ in range(4)]
for _t_ in _ths:
    _t_.start()
for _t_ in _ths:
    _t_.join()
ok("6b. ⭐ four viewers at once on a cold entry: ONE build, all four get it", _sf[0] == 1 and _res == [b"slow"] * 4)

# the warmer builds exactly what a viewer would read
read_cache.clear()
_w = read_cache.warm(db.current_tenant())
_bw = read_cache.STATS["builds"]
_wb, _ = months_body()
ok("6b. ⭐ warm(): builds the council read for the tenant, and the next viewer's read is a hit with the same bytes",
   # NARROWED 27 Oct 2026 (group 2a): main also registers the closures check as a warmer ("restrictions_check"), so the
   # result holds both names, each "ok"; the council read is still built and served the same way
   # NARROWED 28 Oct 2026 (the demo narrative's F1): + "staff", the admin's Dashboard / Look-ahead / Routes reads
   {k: _w.get(k) for k in ("areas/months", "restrictions_check")} == {"areas/months": "ok", "restrictions_check": "ok"}
   and set(_w) == {"areas/months", "restrictions_check", "staff"}
   and read_cache.STATS["builds"] == _bw and _wb == fresh())
ok("6b. a warmer that fails says so and never raises",
   (lambda: (read_cache.WARMERS.__setitem__("t/boom", lambda: 1 / 0), read_cache.warm(db.current_tenant()),
             read_cache.WARMERS.pop("t/boom"))[1])().get("t/boom", "").startswith("ZeroDivisionError"))
ok("6b. the warmer starts only from main's lifespan (never on import) and WAYSCOPE_WARM_CACHE=0 turns it off",
   src_main.count("read_cache.start_warmer(") == 1
   and src_main.index("read_cache.start_warmer(") < src_main.index("    yield\n")
   and 'os.environ.get("WAYSCOPE_WARM_CACHE", "1").strip() != "0"' in src_main
   and not re.search(r"^\s*(read_cache\.)?start_warmer\(", read("backend/read_cache.py") + read("backend/main.py").replace(
       "        read_cache.start_warmer(db.current_tenant())", ""), re.M))

# the wiring that the stubbed HTTP layer cannot run (http_smoke.py runs it for real)
_mw = src_main[src_main.index("async def _access_middleware("):src_main.index("GUARD_HEADER = ")]
ok("6b. ⭐ the middleware bumps the version after EVERY audited /api/ write, worked or not (in a finally round call_next)",
   "try:\n                response = await call_next(request)\n            finally:" in _mw
   # NARROWED 31 Oct 2026 (task 4a PR 3b): every audited write but a CLP's notes and tasks (_CLP_NOTES_PATH)
   # NARROWED 31 Oct 2026 (task 4a PR 3c): nor the client reviewers' writes (_REVIEW_PATH)
   # NARROWED 31 Oct 2026 (task 4c PR 3): ...and a pinned picture's writes (_PICTURE_PATH; nothing is built from a picture)
   and ("if (write and _audited(path) and not _CLP_NOTES_PATH.match(path) and not _REVIEW_PATH.match(path)\n"
        "                        and not _PICTURE_PATH.match(path)):\n"
        "                    db.bump_data_version()") in _mw
   and '_PICTURE_PATH = re.compile(r"^/api/(site-layouts/pictures/[^/]+|locations/[^/]+/site-layout/pictures)$")' in src_main
   and '_CLP_NOTES_PATH = re.compile(r"^/api/clp/documents/[^/]+/(notes|tasks)(/|$)")' in src_main)
ok("6b. ⭐ db._run bumps after the commit and execute_atomic after its commit (not before: a reader could re-cache old figures)",
   "conn.commit()\n            note_write(sql)" in read("backend/db.py")
   and "conn.commit()\n            if any(written_table(step[0]) not in NO_DATA_TABLES for step in steps):\n                bump_data_version()" in read("backend/db.py"))
_own = {}
for _f in sorted(os.listdir(os.path.join(ROOT, "backend"))):
    if _f.endswith(".py") and _f != "db.py":
        _lines = read("backend/" + _f).split("\n")
        for _i, _l in enumerate(_lines):
            if "conn.commit()" in _l:
                _own.setdefault(_f, []).append("db.bump_data_version()" in _lines[_i + 1])
ok("6b. ⭐ every module that commits on its own connection bumps the version on the next line",
   _own and all(all(v) for v in _own.values()) and set(_own) == {"limits.py", "tenant_package.py"}, str(_own))
_dbsrc = read("backend/db.py")
_fn, _bad = None, []
for _l in _dbsrc.split("\n"):
    if _l.startswith("def "):
        _fn = _l[4:].split("(")[0]
    if "conn.commit()" in _l and not (_fn.startswith(("init_", "_migrate_")) or _fn in ("_run", "execute_atomic")):
        _bad.append(_fn)
ok("6b. db.py's other commits are start-up migrations only (init_* / _migrate_*), before anything is cached",
   _bad == [], str(_bad))
ok("6b. ⭐ Render runs ONE process: the start command has no --workers (the version is per process; see db.py)",
   "--workers" not in read("render.yaml") and "WEB_CONCURRENCY" not in read("render.yaml")
   and "uvicorn main:app" in read("render.yaml"))
ok("6b. the endpoint serves from read_cache and builds inside the heavy-read slot",
   "read_cache.cached(AREAS_MONTHS_CACHE, _areas_months_key(), _areas_months_build)" in src_main
   and 'with _heavy("areas/months"):\n        return read_cache.json_bytes(areas.area_load_all(wd, months))' in src_main)
ok("6b. read_cache.py says what it does not do, and names no team id", "WHAT THIS DOES NOT DO" in read("backend/read_cache.py")
   and "IPT" not in read("backend/read_cache.py"))
read_cache.clear()

# =========================================================================== #
#  7. The package round trip                                                   #
# =========================================================================== #
pkg = tenant_package.export_tenant(app_version="test")
cnt = tenant_package.counts(pkg)
n_clip = len(db.query("SELECT 1 FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),)))
ok("7. the export carries areas (4) and route_area_km (every stored row)", cnt.get("areas") == 4
   and cnt.get("route_area_km") == n_clip and n_clip > 10, str(cnt))
ok("7. ...with no tenant_id in a row", all("tenant_id" not in r for r in pkg["tables"]["areas"] + pkg["tables"]["route_area_km"]))
ok("7. validate() passes the export", tenant_package.validate(pkg) == [])
before_ids = sorted((r["route_id"], r["vehicle_profile"], r["leg"], r["area_id"]) for r in pkg["tables"]["route_area_km"])
before_load = areas.area_load(M, working_days=WD)
boot()
out = tenant_package.import_tenant(pkg)
ok("7. import into an empty tenant succeeds and reports both tables",
   out["ok"] and out["inserted"].get("areas") == 4 and out["inserted"].get("route_area_km") == n_clip, str(out["inserted"]))
after_ids = sorted((r["route_id"], r["vehicle_profile"], r["leg"], r["area_id"]) for r in db.query(
    "SELECT * FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),)))
ok("7. ⭐ the same clip rows after the round trip (the import's re-clip agrees with the package)", after_ids == before_ids)
after_load = areas.area_load(M, working_days=WD)
ok("7. ⭐ ...and the same month figures per area (movements and carbon)",
   [(a["area_id"], a["movements_per_day"], a["co2_t"]) for a in after_load["areas"]]
   == [(a["area_id"], a["movements_per_day"], a["co2_t"]) for a in before_load["areas"]]
   and after_load["attribution"] == ["Test boundaries, made up"])
ok("7. ...stamped with the CURRENT tenant", {r["tenant_id"] for r in db.query("SELECT tenant_id FROM areas")} == {db.current_tenant()})
pkg_old = json.loads(json.dumps(pkg))
pkg_old["tables"].pop("route_area_km")
boot()
tenant_package.import_tenant(pkg_old)
ok("7. ⭐ a package without the clip table is clipped on import (the hook re-clips from its areas and geometry)",
   sorted((r["route_id"], r["vehicle_profile"], r["leg"], r["area_id"]) for r in db.query(
       "SELECT * FROM route_area_km WHERE tenant_id = ?", (db.current_tenant(),))) == before_ids)
pkg_none = json.loads(json.dumps(pkg))
pkg_none["tables"].pop("areas"); pkg_none["tables"].pop("route_area_km")
boot()
tenant_package.import_tenant(pkg_none)
ok("7. a package with no areas (the shipped demo today) imports to no areas and no clip rows",
   areas.stored_areas() == [] and areas.status()["rows"] == 0 and areas.status()["legs_clipped"] == 0)

# =========================================================================== #
#  8. Source-level rules                                                       #
# =========================================================================== #
src = read("backend/areas.py")
ok("8. no literal working-day count in the module", not re.search(r"\b22\b", src))
ok("8. no team id literal in the module", not TEAM_ID.search(src) and "IPT" not in src)
ok("8. UK public wording: none of the banned words", not re.search(
    r"\b(truck|real[- ]time|live tracking|telematics|optimi[sz]|predict|secure)\b", src, re.I))
import ast  # noqa: E402
_sel = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.lstrip().upper().startswith(("SELECT", "DELETE", "INSERT"))]
ok("8. every SELECT / DELETE / INSERT in the module names tenant_id", len(_sel) >= 8 and all("tenant_id" in q for q in _sel), str(len(_sel)))
ok("8. nothing external: no urllib, requests, HERE, shapely", not re.search(r"\b(urllib|requests|here_routing|shapely)\b", src))
ok("8. no geometry library added to the requirements", "shapely" not in read("backend/requirements.txt").lower())
ok("8. the month read takes the bar's payload through road_sections.month_lines (one read of the month)",
   "payload = road_sections.month_lines(month)" in src and "import costlines" not in src)
# NARROWED 29 Oct 2026 (task 0c, PR B): the same divisor for each (laden option, empty option) pair a month uses, the
# share of the month's working days on that pair (w) in front: a route no dated zone diverts is one pair, w = 1.0
ok("8. ⭐ the carbon divisor is the two-way length, the laden km plus the stored return",
   "two_way = L.get(WHOLE_LEG, 0.0) + Rt.get(WHOLE_LEG, 0.0)" in src
   and "co2 += c * w * (lin + rin) / two_way" in src)
# NARROWED 12 Oct 2026 (Track C review): "enters" is at least ENTER_KM (200 m, the BSC generalisation) of the laden leg,
# not any length over half a metre; the return still adds none
# NARROWED 29 Oct 2026 (task 0c, PR B): the loads of the share of the month whose LADEN line enters (w_in: 1.0 for a
# route no dated zone diverts), still only one place that adds loads
ok("8. ⭐ movements: the loads of routes whose LADEN leg enters (200 m or more inside), the return adds none",
   "w_in = sum(w for w, L, Rt in opts if L.get(aid, 0.0) >= ENTER_KM)" in src
   and "if w_in > 0:\n                routes.append(rid)\n                loads += ld * w_in" in src and "ENTER_KM = 0.2" in src
   and src.count("loads += ld") == 1)
ok("8. no US spelling in the module's sentences", not re.search(r"\b(color|center|meter|kilometer|neighbor|analyze|optimize)\b", src, re.I))
ok("8. the module says what it does not do", "WHAT THIS DOES NOT DO" in src)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
