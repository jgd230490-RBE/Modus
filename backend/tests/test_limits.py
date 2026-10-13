"""
Lorry limits — weight, height, width and axle weight from OpenStreetMap and HERE (13 Oct 2026).

WHAT THIS PROVES
----------------
  * reading OSM values: tonnes, metres, feet-and-inches as signed in the UK, the words that
    are not values; the sanity ranges that keep a wrong unit off the map;
  * the Overpass query (bbox order, every tag, lorry roads only) and the parse of a fixture
    shaped like the 13 Oct live read round Market Harborough;
  * the table is GLOBAL and never in a tenant package; a re-import replaces only its box;
  * ⭐ the bridge trap: a height limit on a road the route crosses OVER is not a hit, one the
    route runs ALONG is; each leg is judged at its own weight (laden gross, empty tare);
    "except for access" is said, never used to drop a verdict; axle weight is never guessed;
  * the bake hook stores the check; the LIMIT clash per line's own vehicle; the map's
    collection (breaches from APPROVED lines only, attribution, advisory note, no "truck");
  * the endpoints: the gate prefix, the admin token, a stubbed import, a failed import that
    replaces nothing;
  * HERE: the documented response shape parsed (delta geometry, kg / cm), a wrong unit
    dropped, a failed call that replaces nothing.

WHAT THIS DOES NOT PROVE
------------------------
  * Overpass and HERE are stubbed. HERE's Map Attributes API has never been called: its
    layer names, field names, units and geometry encoding are from documentation, so the
    HERE half is a parser for an assumed shape until the probe on Render has been read.
  * Nothing about the live demo's routes: which real limits they run along is known only
    after the import runs on Render.
  * No Postgres branch runs (one plain CREATE on both backends).

Run:  python backend/tests/test_limits.py
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

TMP = tempfile.mkdtemp(prefix="wayscope_limits_")
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


import limits  # noqa: E402
import clashes  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def hav_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


PROFILE = network.DEFAULT_PROFILE          # "Artic Tipper (44t)": 44 t gross, 29 t payload, 4.00 m, 2.55 m
RIGID = "Rigid 8-wheeler (32t)"
BAL = "Large aggregate / ballast"
TEAM_ID = re.compile(r"\bIPT ?[1-6]\b")

# =========================================================================== #
#  1. Reading values                                                           #
# =========================================================================== #
ok("1. weight '7.5' -> 7.5 t", limits.parse_weight("7.5") == 7.5)
ok("1. weight '7.5 t', '18t', '7500 kg', '5,5'", limits.parse_weight("7.5 t") == 7.5 and limits.parse_weight("18t") == 18.0
   and limits.parse_weight("7500 kg") == 7.5 and limits.parse_weight("5,5") == 5.5)
ok("1. weight in another unit (st, lbs) or 'none' is None, never guessed",
   limits.parse_weight("3 st") is None and limits.parse_weight("6000 lbs") is None and limits.parse_weight("none") is None)
ok("1. height '4.4', '4.4 m', '4.4m' -> 4.4", limits.parse_length("4.4") == 4.4 and limits.parse_length("4.4 m") == 4.4
   and limits.parse_length("4.4m") == 4.4)
ok("1. ⭐ height 14'6\" -> 4.42 m (14 ft 6 in)", limits.parse_length("14'6\"") == 4.42, str(limits.parse_length("14'6\"")))
ok("1. ...14'6 (no inch mark), 14', '14 ft 6 in', curly quotes",
   limits.parse_length("14'6") == 4.42 and limits.parse_length("14'") == 4.27
   and limits.parse_length("14 ft 6 in") == 4.42 and limits.parse_length("14’6″") == 4.42)
ok("1. 'default', 'below_default', 'none' are None", all(limits.parse_length(x) is None for x in ("default", "below_default", "none", "")))
ok("1. imperial text: 4.42 -> 14'6\", 2.0 -> 6'7\"", limits.imperial_text(4.42) == "14'6\"" and limits.imperial_text(2.0) == "6'7\"")
ok("1. the sign legend: 7.5T for weight, 4.4m for height", limits.icon_text("weight", 7.5) == "7.5T" and limits.icon_text("height", 4.4) == "4.4m")
ok("1. sanity ranges: a 300 t weight, a 0.4 m height, a 12 m width are out",
   not limits.in_range("weight", 300) and not limits.in_range("height", 0.4) and not limits.in_range("width", 12)
   and limits.in_range("weight", 7.5) and limits.in_range("height", 4.4))

# =========================================================================== #
#  2. OpenStreetMap: the query and the parse                                   #
# =========================================================================== #
Q = limits.overpass_query((-1.0, 52.44, -0.88, 52.52))
ok("2. the Overpass bbox is (south,west,north,east)", "(52.44,-1.0,52.52,-0.88)" in Q)
ok("2. every limit tag is asked for, on ways and nodes",
   all(f'["{t}"]' in Q for tags in limits.OSM_TAGS.values() for t in tags) and 'node["maxheight"]' in Q)
ok("2. ways are limited to roads a lorry can use (no service, track, footway)",
   '"highway"~"^(motorway|' in Q and "service" not in limits.OSM_HIGHWAYS and "track" not in limits.OSM_HIGHWAYS)
ok("2. out tags geom (the way's own geometry comes back)", Q.endswith("out tags geom;"))
ok("2. tiles: a 0.6 x 0.3 degree box splits into 3 x 2 tiles of 0.25",
   len(limits.tiles((0.0, 0.0, 0.6, 0.3), 0.25)) == 6)
ok("2. the import tiles at 0.15 degrees (13 Oct: 0.25 drew 504s) and retries failed tiles twice",
   limits.OSM_TILE_DEG == 0.15 and limits.OSM_RETRY_ROUNDS == 2)


def way(i, coords, **tags):
    return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": c[1], "lon": c[0]} for c in coords]}


# the route below runs W -> E along 52.50 from -0.95 to -0.85; this fixture mirrors the 13 Oct live read
ELEMENTS = [
    way(101, [[-0.94, 52.50], [-0.938, 52.50], [-0.936, 52.50]], maxweight="5", hgv="destination",
        highway="unclassified", name="Back Lane"),                                  # 5 t, along the route
    way(102, [[-0.92, 52.499], [-0.92, 52.501]], maxheight="3.8", highway="tertiary",
        name="Kettering Road"),                                                     # 3.8 m, CROSSES the route
    way(103, [[-0.90, 52.50], [-0.898, 52.50]], maxheight="14'6\"", highway="trunk", name="Rockingham Road"),
    way(104, [[-0.89, 52.50], [-0.888, 52.50]], maxwidth="2", highway="unclassified"),
    {"type": "node", "id": 201, "lat": 52.50003, "lon": -0.87, "tags": {"maxheight": "3.6", "barrier": "height_restrictor"}},
    {"type": "node", "id": 202, "lat": 52.51, "lon": -0.87, "tags": {"maxheight": "3.0"}},    # 1 km off the route
    way(105, [[-0.86, 52.50], [-0.858, 52.50]], maxweight="300", highway="residential"),     # out of range
    way(106, [[-0.86, 52.52], [-0.858, 52.52]], maxheight="default", highway="residential"),  # not a value
    way(107, [[-0.861, 52.50], [-0.857, 52.50]], maxaxleload="10", highway="residential"),
]
ROWS, DROPPED = limits.parse_osm(ELEMENTS, fetched_at="2026-10-13T10:00:00+00:00")
by = {(r["ext_id"], r["kind"]): r for r in ROWS}
ok("2. parse: 7 limits read, 2 dropped (300 t out of range, 'default' not a value)",
   len(ROWS) == 7 and DROPPED == {"weight": 1, "height": 1}, f"{len(ROWS)} {DROPPED}")
ok("2. Back Lane: 5 t, except for access (hgv=destination), a line with its length",
   by[("w101", "weight")]["value"] == 5.0 and by[("w101", "weight")]["exceptions"] == "Except for access"
   and by[("w101", "weight")]["geom_type"] == "LineString" and by[("w101", "weight")]["length_m"] > 200)
ok("2. ⭐ Rockingham Road 14'6\": 4.42 m, the signed text kept for the sign",
   by[("w103", "height")]["value"] == 4.42 and by[("w103", "height")]["signed"] == "14'6\"")
ok("2. a metric height keeps no 'signed' text (the map shows the converted imperial)", by[("w102", "height")]["signed"] is None)
ok("2. a node limit is a Point with its own coordinates", by[("n201", "height")]["geom_type"] == "Point"
   and by[("n201", "height")]["geometry"] == [-0.87, 52.50003])
ok("2. a line's anchor (where the sign goes) is half-way along it",
   abs(by[("w101", "weight")]["anchor"][0] - (-0.938)) < 1e-6)
ok("2. axle weight read from maxaxleload", by[("w107", "axle")]["value"] == 10.0)

# =========================================================================== #
#  3. The table: global, never in a package                                    #
# =========================================================================== #
boot()
limits.init_db()
ok("3. road_limits exists", "road_limits" in {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")})
ok("3. ⭐ it is NOT a tenanted table and NOT in the package (OSM / HERE data never ships in a customer file)",
   "road_limits" not in db.TENANTED_TABLES and "road_limits" not in tenant_package.ORDER)
ok("3. the tenant audit lists it as untenanted, with a reason", '"road_limits": "public road facts' in read("backend/tests/test_tenant_audit.py"))
ok("3. routes carries the stored check (limits_hits, limits_checked_at, limits_status) in the DDL and the ALTERs",
   all(c in read("backend/db.py") for c in ('("routes", "limits_hits", "TEXT")', "limits_hits TEXT,", "limits_status TEXT,")))
_cols = {r[1] for r in db.get_conn().cursor().execute("PRAGMA table_info(routes)").fetchall()}
ok("3. ...and the scratch database has the three columns", {"limits_hits", "limits_checked_at", "limits_status"} <= _cols, str(_cols))

q1 = network.create_location("Pit West", "origin", lat=52.50, lon=-0.95, loc_type="Quarry", supplies=[BAL])
d1 = network.create_location("Yard East", "destination", lat=52.50, lon=-0.85, loc_type="Compound", receives=[BAL])
r1 = network.create_route(q1["id"], d1["id"], material_category=BAL, route_id="R001", ipt="IPT1")["id"]
r2 = network.create_route(q1["id"], d1["id"], material_category=BAL, route_id="R002", ipt="IPT2")["id"]
EXT = limits.tenant_extent()
ok("3. the tenant's extent is its sites padded by ~2 km", EXT == (-0.97, 52.48, -0.83, 52.52), str(EXT))
n = limits.replace_rows("osm", EXT, ROWS)
ok("3. replace_rows stores every parsed row", n == 7 and len(limits.stored()) == 7)
FAR = dict(ROWS[0], ext_id="w999", anchor=[1.5, 51.0], geometry=[[1.5, 51.0], [1.51, 51.0]])
limits.replace_rows("osm", (1.4, 50.9, 1.6, 51.1), [FAR])
limits.replace_rows("osm", EXT, ROWS[:6])
ok("3. ⭐ a re-import replaces only the rows inside its own box (another area's row survives)",
   len(limits.stored()) == 6 and len(limits.stored((1.4, 50.9, 1.6, 51.1))) == 1)
limits.replace_rows("osm", EXT, ROWS)
pkg = tenant_package.export_tenant()
ok("3. the exported package carries no limits table and no limit rows", "road_limits" not in pkg["tables"])

# =========================================================================== #
#  4. Matching to the baked route: the bridge trap                             #
# =========================================================================== #
LINE = [[round(-0.95 + 0.005 * i, 6), 52.50] for i in range(21)]          # W -> E along 52.50
before = len(limits.stored_checks([r1])[r1]["hits"])
network._upsert_geom(r1, PROFILE, json.dumps(LINE), 6.8, 0.2, None, leg="loaded", alt_index=0)
network._upsert_geom(r1, PROFILE, json.dumps(list(reversed(LINE))), 6.8, 0.2, None, leg="return", alt_index=0)
st = limits.stored_checks([r1])[r1]
ok("4. ⭐ the bake hook stores the check at once (no import, no refresh needed)",
   before == 0 and st["status"] == "ok" and st["checked_at"] and len(st["hits"]) > 0, str(st)[:200])
H = {(h["ext_id"], h["kind"], h["leg"]): h for h in st["hits"]}
ok("4. ⭐ THE BRIDGE TRAP: Kettering Road (3.8 m) CROSSES the route and is NOT a hit, though it is 0 m away in plan",
   not any(k[0] == "w102" for k in H), str(sorted(H)))
ok("4. Back Lane (5 t) runs along the route: a hit on both legs", ("w101", "weight", "loaded") in H and ("w101", "weight", "return") in H)
ok("4. ⭐ 44 t laden is over 5 t: exceeds; going back empty at 15 t (44 - 29 payload) is over it too",
   H[("w101", "weight", "loaded")]["verdict"] == "exceeds" and H[("w101", "weight", "loaded")]["vehicle_value"] == 44.0
   and H[("w101", "weight", "return")]["vehicle_value"] == 15.0 and H[("w101", "weight", "return")]["verdict"] == "exceeds")
ok("4. 'except for access' is in the note, the verdict kept", "Except for access" in (H[("w101", "weight", "loaded")]["note"] or ""))
ok("4. Rockingham Road 4.42 m against a 4.00 m artic: within, margin 0.42",
   H[("w103", "height", "loaded")]["verdict"] == "within" and H[("w103", "height", "loaded")]["margin"] == 0.42)
ok("4. a 2.0 m width against a 2.55 m artic: exceeds", H[("w104", "width", "loaded")]["verdict"] == "exceeds")
ok("4. the node 3 m off the route is a POINT hit, with the check-it note",
   H[("n201", "height", "loaded")]["point"] is True and "check whether the route passes it" in H[("n201", "height", "loaded")]["note"])
ok("4. the node 1 km away is not a hit", not any(k[0] == "n202" for k in H))
ok("4. axle weight: no vehicle figure, so 'unknown' with the reason, never a divided-out guess",
   H[("w107", "axle", "loaded")]["verdict"] == "unknown" and "axle" in H[("w107", "axle", "loaded")]["note"])
ok("4. hits are ordered exceeds first, and a limit run ALONG before a point limit",
   st["hits"][0]["verdict"] == "exceeds" and st["hits"][0]["point"] is False)
ok("4. a hit names the vehicle by its label and carries the sign's headline",
   H[("w103", "height", "loaded")]["vehicle_label"] == "Artic Tipper (44t)"
   and H[("w103", "height", "loaded")]["headline"] == "Height limit 4.42 m (14'6\") · Rockingham Road")
# an 18 t limit: the laden artic is over it, the empty one is not
limits.replace_rows("osm", EXT, ROWS + [dict(ROWS[0], ext_id="w150", value=18.0, exceptions=None,
                                             geometry=[[-0.93, 52.50], [-0.928, 52.50]], anchor=[-0.929, 52.50])])
res = limits.check_route(r1)
h18 = {h["leg"]: h for h in res["hits"] if h["ext_id"] == "w150"}
ok("4. ⭐ an 18 t limit: laden 44 t exceeds, empty 15 t is within (each leg at the weight HERE routed it)",
   h18["loaded"]["verdict"] == "exceeds" and h18["return"]["verdict"] == "within")
limits.replace_rows("osm", EXT, ROWS)
limits.store_checks()
# a short limit: 60 % of its length is enough
SHORT = dict(ROWS[0], ext_id="w160", geometry=[[-0.9105, 52.50], [-0.9100, 52.50]], anchor=[-0.91025, 52.5], length_m=34.0)
ok("4. a 34 m limit wholly on the route counts (60 % of a short one is enough)",
   any(h["ext_id"] == "w160" for h in limits.check_route(r1, _limits=[dict(SHORT, anchor_lon=-0.91025, anchor_lat=52.5)])["hits"]))
ok("4. an unbaked route has nothing to check", limits.check_route(r2)["baked"] is False)
ok("4. along_m of a perpendicular crossing is ~0; of a parallel stretch is its length",
   limits.along_m([[-0.92, 52.499], [-0.92, 52.501]], LINE) == 0.0
   and abs(limits.along_m([[-0.94, 52.50], [-0.936, 52.50]], LINE) - hav_m([-0.94, 52.5], [-0.936, 52.5])) < 0.5)

# =========================================================================== #
#  5. The clash rail: LIMIT                                                    #
# =========================================================================== #
ok("5. LIMIT is a clash code, after RESTRICTION and before UNBAKED",
   clashes.CODES.index("LIMIT") == clashes.CODES.index("RESTRICTION") + 1 and clashes.CODES.index("UNBAKED") == clashes.CODES.index("LIMIT") + 1)


def line(rid, veh, baked=True):
    return {"route_id": rid, "month_index": 10, "discipline": "", "section_id": "", "ipt": "IPT1",
            "context": {"baked": baked, "vehicle_type": veh, "origin_name": "Pit West", "dest_name": "Yard East"}}


fl, src = clashes.limit([line(r1, PROFILE)])
ok("5. ⭐ the artic line on R001 gets ONE LIMIT flag", len(fl) == 1 and fl[0]["code"] == "LIMIT" and fl[0]["label"] == "ROAD LIMIT", str(fl))
t = fl[0]["text"]
ok("5. the text names the vehicle, its weight, the limit, the road and the source",
   "Artic Tipper (44t) (44 t, loaded)" in t and "over the Weight limit 5 t · Back Lane" in t and "(OpenStreetMap)" in t, t)
ok("5. ...says 'except for access' and how many more", "except for access" in t and "(+" in t, t)
ok("5. no team id in the text", not TEAM_ID.search(t))
_pt = dict(limits.stored_checks([r1])[r1])
_only_point = [h for h in _pt["hits"] if h["point"] and h["verdict"] == "exceeds"]
db.execute("UPDATE routes SET limits_hits = ? WHERE tenant_id = ? AND id = ?", (json.dumps(_only_point), db.current_tenant(), r1))
ok("5. a point-limit breach says to check whether the route passes it",
   "a point limit: check whether the route passes it" in clashes.limit([line(r1, PROFILE)])[0][0]["text"])
limits.store_checks()
ok("5. a line whose vehicle was never checked on that route gets no flag (the verdict is per vehicle)",
   clashes.limit([line(r1, RIGID)])[0] == [])
ok("5. an unbaked line gets no flag", clashes.limit([line(r2, PROFILE, baked=False)])[0] == [])
ok("5. the source block says the check is stored", src["status"] == "ok" and src["checked_at"])
csrc = read("backend/clashes.py")
ok("5. compute() adds the LIMIT flags and reports the limits source",
   "lim, lim_source = limit(all_lines)" in csrc and '"limits": lim_source.get("status")' in csrc)
fe = read("frontend/index.html")
ok("5. the staff rail names it ROAD LIMIT in both label tables", fe.count('LIMIT: "ROAD LIMIT"') == 2)

# =========================================================================== #
#  6. The map's collection                                                     #
# =========================================================================== #
M = 10


def add_line(fid, rid, status="Approved", vehicle=PROFILE):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), fid, rid, M, "superstructure", "", 290.0, "t", BAL, "Type 1", vehicle,
                "test", status, None, "IPT1"))


fc0 = limits.feature_collection()
ok("6. no approved line yet: nothing is shown as a breach", all(f["properties"]["breach_count"] == 0 for f in fc0["features"]))
add_line("F1", r1, status="Pending")
ok("6. a PENDING line does not make a breach on the public map",
   all(f["properties"]["breach_count"] == 0 for f in limits.feature_collection()["features"]))
db.execute("UPDATE forecasts SET status = 'Approved' WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "F1"))
FC = limits.feature_collection()
P = {f["properties"]["id"]: f["properties"] for f in FC["features"]}
ok("6. ⭐ with the approved artic line, Back Lane shows R001 as a breach (loaded and empty)",
   P["osm:w101:weight"]["breach_count"] == 2 and {b["leg"] for b in P["osm:w101:weight"]["breaches"]} == {"loaded", "return"}
   and P["osm:w101:weight"]["breaches"][0]["route_id"] == "R001")
ok("6. the crossing (Kettering Road) is on the map but breached by nobody", P["osm:w102:height"]["breach_count"] == 0)
ok("6. a feature carries what the sign and the card need",
   all(k in P["osm:w103:height"] for k in ("kind", "value", "unit", "label", "headline", "icon_text", "imperial", "name",
                                           "exceptions", "source", "source_label", "attribution", "fetched_at", "anchor", "breaches")))
ok("6. Rockingham Road: legend 4.42m, imperial 14'6\" (the signed text)",
   P["osm:w103:height"]["icon_text"] == "4.42m" and P["osm:w103:height"]["imperial"] == "14'6\"")
ok("6. a metric-only height gets its imperial line computed (3.8 m -> 12'6\")", P["osm:w102:height"]["imperial"] == "12'6\"")
ok("6. weight has no imperial line", P["osm:w101:weight"]["imperial"] is None)
ok("6. lines stay lines, nodes stay points", FC["features"][0]["geometry"]["type"] in ("LineString", "Point")
   and any(f["geometry"]["type"] == "Point" for f in FC["features"]))
ok("6. ⭐ the attribution is on every feature and on the collection: © OpenStreetMap contributors",
   P["osm:w101:weight"]["attribution"].startswith("© OpenStreetMap contributors") and FC["sources"]["osm"]["fetched_at"])
ok("6. the collection says it is advisory", FC["note"].startswith("Advisory") and "check the signed limit on site" in FC["note"])
_copy = json.dumps([FC["note"], [s["note"] for s in limits.SOURCES.values()], [k["label"] for k in limits.KINDS.values()],
                    [f["properties"]["label"] for f in FC["features"]]])
ok("6. no 'truck' in anything the map shows", "truck" not in _copy.lower())
ok("6. no team id in the collection", not TEAM_ID.search(json.dumps(FC)))

# =========================================================================== #
#  7. Endpoints                                                                #
# =========================================================================== #
ok("7. GET /api/public/limits returns the collection", len(main.public_limits()["features"]) == 7)
ok("7. ...narrowed by a bbox", len(main.public_limits(bbox="-0.95,52.49,-0.93,52.51")["features"]) == 1)
try:
    main.public_limits(bbox="nonsense")
    ok("7. a bad bbox is a 400", False)
except Exception as e:
    ok("7. a bad bbox is a 400", getattr(e, "status_code", None) == 400)
msrc = read("backend/main.py")
ok("7. the public read sits under /api/public/ (behind the map gate)", '@app.get("/api/public/limits")' in msrc)
ok("7. the Look-ahead's restriction refresh re-runs the limits check too",
   "limits.store_checks()" in msrc[msrc.index("def forecast_week_restrictions_refresh"):msrc.index("def forecast_week_restrictions_refresh") + 900])
ok("7. the route read needs a staff code", 'def route_limits(route_id: str):\n    """13 Oct 2026. The stored lorry-limits check for one route (every baked vehicle and leg)."""\n    _require_access()' in msrc)
for fn, kw in (("limits_import", {"source": "osm"}), ("limits_status", {}), ("limits_recheck", {}),
               ("diagnostics_limits", {})):
    try:
        getattr(main, fn)(**kw)
        ok(f"7. {fn} without ADMIN_TOKEN is refused", False)
    except Exception as e:
        ok(f"7. {fn} without ADMIN_TOKEN is refused", getattr(e, "status_code", None) == 403, str(e))
os.environ["ADMIN_TOKEN"] = "t0k"
try:
    main.limits_import(source="tomtom", token="t0k")
    ok("7. an unknown source is a 400", False)
except Exception as e:
    ok("7. an unknown source is a 400", getattr(e, "status_code", None) == 400)
# a stubbed Overpass: every tile answers with the fixture
_calls = []
_real_overpass = limits._overpass
limits._overpass = lambda q: (_calls.append(q) or ({"elements": ELEMENTS}, "stub", []))
limits.replace_rows("osm", EXT, [])
st = main.limits_import(source="osm", sync=1, token="t0k")
ok("7. ⭐ an import (stubbed Overpass) stores the limits and re-checks every route",
   st["status"] == "ok" and st["imported"] == 7 and not st["running"] and len(limits.stored_checks([r1])[r1]["hits"]) > 0, str(st))
ok("7. one Overpass call per tile of the extent", len(_calls) == len(limits.tiles(EXT, limits.OSM_TILE_DEG)))
limits.OSM_RETRY_WAIT_S = 0
_busy = []
limits._overpass = lambda q: (_busy.append(q) or (None, None, ["https://overpass-api.de/api/interpreter: busy or error page"]))
st = main.limits_import(source="osm", sync=1, token="t0k")
ok("7. ⭐ Overpass busy everywhere: status unavailable and NOTHING replaced (the stored limits survive)",
   st["status"] == "unavailable" and len(limits.stored()) == 7, str(st))
ok("7. ...each tile was asked three times (once, then two retry rounds)", len(_busy) == 3 * len(limits.tiles(EXT, limits.OSM_TILE_DEG)))
# one tile busy for good, the rest answer: the busy tile keeps its rows, the others are replaced
BIG = (-1.0, 52.4, -0.7, 52.6)                     # 2 x 2 tiles of 0.15
_tl = limits.tiles(BIG, limits.OSM_TILE_DEG)
_bad = next(t for t in _tl if any(limits._in_box(r["anchor"], t) for r in ROWS))
_bad_q = limits.overpass_query(_bad)
_kept = sorted(r["ext_id"] for r in limits.stored() if limits._in_box([r["anchor_lon"], r["anchor_lat"]], _bad))
limits._overpass = lambda q: (None, None, ["busy"]) if q == _bad_q else ({"elements": []}, "stub", [])
st = limits.import_osm(BIG)
ok("7. the bigger box is 4 tiles", len(_tl) == 4)
ok("7. ⭐ one tile failing: status partial, the failed tile named, its limits KEPT (never read as 'no limits')",
   st["status"] == "partial" and st["failed_tiles"] == [list(_bad)] and _kept
   and sorted(r["ext_id"] for r in limits.stored()) == _kept, str(st)[:300])
ok("7. ...and the note says to run it again", "run the import again" in st["note"])
limits._overpass = lambda q: ({"elements": ELEMENTS}, "stub", [])
st = limits.import_osm(BIG)
ok("7. a later full answer restores every limit, each stored once (a way across two tiles is claimed by its sign's tile)",
   st["status"] == "ok" and len(limits.stored()) == 7 and st["imported"] == 7, str(st)[:200])
limits._overpass = _real_overpass
s2 = main.limits_status(token="t0k")
ok("7. status reports what is stored per source and kind", s2["stored"]["osm"]["height"] == 4 and s2["extent"])
ok("7. recheck runs without any external call", main.limits_recheck(token="t0k")["status"] == "ok")

# =========================================================================== #
#  8. HERE (unverified path: parse against the documented shape)               #
# =========================================================================== #
ok("8. delta-decoded geometry: '5250000,10,-5' -> 52.5, 52.5001, 52.50005",
   limits._here_coords("5250000,10,-5", "-90000,0,10") == [[-0.9, 52.5], [-0.9, 52.5001], [-0.8999, 52.50005]])
ok("8. an empty delta repeats the previous value", limits._here_coords("5250000,,10", "-90000,10,") == [[-0.9, 52.5], [-0.8999, 52.5], [-0.8999, 52.5001]])
ok("8. mismatched lists are refused", limits._here_coords("5250000,10", "-90000") is None)
PAY = {"Tiles": [{"tileId": 1, "Rows": [
    {"LINK_ID": "77", "LAT": "5250000,0", "LON": "-94000,400", "NAME": "Back Lane"},
    {"LINK_ID": "77", "WEIGHT_RESTRICTION": "7500"},
    {"LINK_ID": "78", "LAT": "5250000,0", "LON": "-92000,200"},
    {"LINK_ID": "78", "HEIGHT_RESTRICTION": "440"},
    {"LINK_ID": "79", "LAT": "5250000,0", "LON": "-91000,200"},
    {"LINK_ID": "79", "HEIGHT_RESTRICTION": "4.4"},          # metres where cm was expected: dropped, not drawn
    {"LINK_ID": "80", "WIDTH_RESTRICTION": "200"},           # no geometry row: unmatched
]}]}
HR, HD, HU = limits.parse_here([PAY])
hb = {r["ext_id"]: r for r in HR}
ok("8. HERE kg -> t, cm -> m on the documented units", hb["77:WEIGHT_RESTRICTION"]["value"] == 7.5 and hb["78:HEIGHT_RESTRICTION"]["value"] == 4.4)
ok("8. ⭐ a value in the wrong unit is DROPPED by the sanity range (4.4 'cm' = 0.044 m), never drawn",
   "79:HEIGHT_RESTRICTION" not in hb and HD.get("height") == 1)
ok("8. a restriction with no link geometry is counted, not invented", HU == 1, str(HU))
ok("8. HERE rows carry the HERE source and name", hb["77:WEIGHT_RESTRICTION"]["source"] == "here" and hb["77:WEIGHT_RESTRICTION"]["name"] == "Back Lane")
ok("8. lower-case field names are read too (case-insensitive)",
   len(limits.parse_here([{"tiles": [{"rows": [{"link_id": "1", "lat": "5250000,0", "lon": "-90000,100"},
                                                 {"link_id": "1", "weight_restriction": "18000"}]}]}])[0]) == 1)
os.environ.pop("HERE_API_KEY", None)
ok("8. no HERE key: the import says so and calls nothing", limits.import_here()["status"] == "no_key")
d = limits.diagnostics(source="here", probe=True)
ok("8. ...and the probe says so", d["probe"].get("error") == "HERE_API_KEY is not set on the server")
ok("8. the diagnostics list what is unverified about HERE",
   any("HERE Map Attributes has never been called" in u for u in d["unverified"]))
ids = limits.here_tiles_for((-0.97, 52.48, -0.83, 52.52), 12)
ok("8. tile ids for the extent are distinct and include both corners",
   len(ids) == len(set(ids)) and limits.here_tile_id(-0.97, 52.48, 12) in ids and limits.here_tile_id(-0.83, 52.52, 12) in ids)
_hcalls = []
_real_get = limits._here_get
os.environ["HERE_API_KEY"] = "test-key"
limits._here_get = lambda layers, tiles: (_hcalls.append((layers, tiles)) or PAY)
r = limits.import_here()
ok("8. ⭐ a HERE import (stubbed) asks TRUCK_RESTR + ROAD_GEOM for FC1-5 and stores the parsed rows",
   r["status"] == "ok" and r["imported"] == 2 and {l[0] for l, t in _hcalls} == {f"TRUCK_RESTR_FC{i}" for i in range(1, 6)}, str(r))
ok("8. OSM and HERE rows sit side by side", {x["source"] for x in limits.stored()} == {"osm", "here"})
ok("8. HERE features carry © HERE", any(f["properties"]["attribution"] == "© HERE" for f in limits.feature_collection()["features"]))
limits._here_get = lambda layers, tiles: (_ for _ in ()).throw(RuntimeError("HTTP 403"))
ok("8. a failed HERE call replaces nothing", limits.import_here()["status"] == "unavailable"
   and len([x for x in limits.stored() if x["source"] == "here"]) == 2)
limits._here_get = _real_get
os.environ.pop("HERE_API_KEY", None)
os.environ.pop("ADMIN_TOKEN", None)

lsrc = read("backend/limits.py")
ok("8. the module docstring says plainly HERE was never called and its terms are unchecked",
   "NEVER CALLED FROM A SESSION" in lsrc and "has NOT been checked" in lsrc)

remove_scratch_db(db, TMP)
print(f"test_limits.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
