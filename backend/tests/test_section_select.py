"""
The public map's road card and "Select an area" (10 Nov 2026, v2.1 task 2.1-4): backend/section_select.py and the
two public reads /api/public/road-at and /api/public/area-sum. John's Q1-Q10 (9 Nov) as recommended.

WHAT IS ASSERTED
----------------
  * a click finds the nearest drawn leg within its reach and asks about a ~150 m piece of it; the routes on THAT road
    come back, each with In (the loaded leg's passes) / Out (the way back's) / A day, from 2.1-1's
    traffic_limits.through — the same count as a traffic limit on that road;
  * a click on a road one route uses still answers (Q1: a one-route road has a card too); off any road: nothing;
  * no month: the routes by reference, no figures (Q4); the organisation's count (1 = visits) decides "A day";
  * a box counts every route with a leg that ENTERS it at all (Q5), once: a route on two roads in the box is one row;
    a corner the road clips counts here where an area limit's 200 m rule would not; a box beside the road counts
    nothing; a bad box is refused in words;
  * what is read once is kept until the next write; no team name in either answer; both reads behind the map gate.

WHAT THIS DOES NOT PROVE
------------------------
HERE and Mapbox are never called; Postgres is not run; the map's card, hover, box tool and Copy are pinned in
parse_map.js and were looked at in Chrome.

Run:  python3 backend/tests/test_section_select.py
"""
import json
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_traffic_limits.py ---------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_secsel_")
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
import route_choice  # noqa: E402
import counting  # noqa: E402
import gate  # noqa: E402
import traffic_limits as TL  # noqa: E402
import section_select as SS  # noqa: E402

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
#  Fixture (test_traffic_limits.py's): R1 loaded west->east along lat 52.5    #
#  (MAIN), back along the northern road (lat 52.51). R2 both ways on MAIN.    #
#  R3 only on a southern spur (one route on that road).                       #
# =========================================================================== #
ART = network.DEFAULT_PROFILE
LAT = 52.5
for lid, lon in (("L1", -1.0), ("L2", -0.9), ("L3", -1.0), ("L4", -0.95)):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, 'Quarry')", (lid, lid, LAT, lon))
for rid, o, d in (("R1", "L1", "L2"), ("R2", "L3", "L2"), ("R3", "L4", "L2")):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) "
               "VALUES (?, ?, ?, 'Small aggregate', 'IPT1')", (rid, o, d))


def pts(lats, lon0=-1.0, lon1=-0.9, n=11):
    return [[round(lon0 + (lon1 - lon0) * i / (n - 1), 6), lats(i)] for i in range(n)]


MAIN = pts(lambda i: LAT)
NORTH = [[-1.0, LAT]] + pts(lambda i: LAT + 0.01, -0.99, -0.91, 9) + [[-0.9, LAT]]
SOUTH = [[-0.95, LAT - 0.02], [-0.95, LAT - 0.01], [-0.95, LAT - 0.003]]


def put(rid, leg, alt, line, km):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, ART, json.dumps(line), km, km / 40.0, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="")


put("R1", "loaded", 0, MAIN, 7.0)
put("R1", "return", 0, NORTH, 8.0)
put("R2", "loaded", 0, MAIN, 7.0)
put("R2", "return", 0, MAIN, 7.0)
put("R3", "loaded", 0, SOUTH, 2.0)
put("R3", "return", 0, SOUTH, 2.0)
DRAWN = {"R1": ART, "R2": ART, "R3": ART}
M = 23
LINES = {M: [{"route_id": "R1", "vehicle_loads": 230.0, "co2_t": 1.0, "ipt": "IPT1"},
             {"route_id": "R2", "vehicle_loads": 100.0, "co2_t": 1.0, "ipt": "IPT1"},
             {"route_id": "R3", "vehicle_loads": 40.0, "co2_t": 1.0, "ipt": "IPT1"}]}
BUILDS = []


def fake_context():
    BUILDS.append(1)
    return {"drawn": DRAWN, "legs": TL._legs(DRAWN), "rows": route_choice._rows_by_route(), "share_cache": {},
            "wd": 20.0, "lines_by_month": (lambda: (LINES, None)), "months": 30}


TL.context = fake_context
SS.forget()
DEG_M = 111320.0 * math.cos(math.radians(LAT))      # metres in one degree of longitude here


def plen(line):
    return sum(math.hypot((b[0] - a[0]) * DEG_M, (b[1] - a[1]) * 110540.0) for a, b in zip(line, line[1:]))


def rows(ans):
    return {r["route_id"]: (r.get("in"), r.get("out"), r.get("a_day")) for r in ans["routes"]}


# =========================================================================== #
#  1. A road under a click                                                     #
# =========================================================================== #
a = SS.road_at(-0.95, LAT, M)
ok("⭐ 1. a click on MAIN: R1 (loaded in, back another way) and R2 (both ways), In / Out / A day a day",
   rows(a) == {"R1": (11.5, 0.0, 11.5), "R2": (5.0, 5.0, 10.0)}, str(rows(a)))
ok("1. the totals: In 16.5, Out 5, A day 21.5 (movements: In + Out)",
   (a["in"], a["out"], a["a_day"]) == (16.5, 5.0, 21.5), str((a["in"], a["out"], a["a_day"])))
ok("1. busiest first", [r["route_id"] for r in a["routes"]] == ["R1", "R2"])
ok("⭐ 1. the same figure 2.1-1's through() gives for that piece of road (one count)",
   TL.through({"type": "LineString", "coordinates": a["piece"]}, M, ctx=SS._ctx())["movements_per_day"] == a["a_day"])
ok("1. the piece asked about is ~150 m of the clicked road", 145 <= plen(a["piece"]) <= 155, str(plen(a["piece"])))
ok("1. ...and lies on it", all(abs(p[1] - LAT) < 1e-6 for p in a["piece"]), str(a["piece"][:3]))
ok("1. the answer says its kind, month and the count's words", a["kind"] == "road" and a["month"] == M
   and a["counting"]["label"] == counting.words()["label"])
near = SS.road_at(-0.95, LAT + 15 / 110540.0, M, r_m=30)
ok("1. a click 15 m off the line still finds the road (reach 30 m)", rows(near) == rows(a), str(rows(near)))
far = SS.road_at(-0.95, LAT + 200 / 110540.0, M, r_m=30)
ok("🔴 1. a click 200 m from any road: no piece, no routes", far["piece"] is None and far["routes"] == [], str(far))
ok("1. the reach is clamped (a 1 km reach still asks within 120 m)",
   SS.road_at(-0.95, LAT + 200 / 110540.0, M, r_m=1000)["piece"] is None)
north = SS.road_at(-0.95, LAT + 0.01, M)
ok("⭐ 1. Q2: the northern road carries only R1's way back: In 0, Out 11.5",
   rows(north) == {"R1": (0.0, 11.5, 11.5)}, str(rows(north)))
spur = SS.road_at(-0.95, LAT - 0.015, M)
ok("⭐ 1. Q1: a road ONE route uses answers too (no shared section needed)",
   rows(spur) == {"R3": (2.0, 2.0, 4.0)}, str(rows(spur)))
end = SS.road_at(-0.9999, LAT, M)
ok("1. a click near a leg's end still asks about ~150 m (lengthened the other way)",
   145 <= plen(end["piece"]) <= 155, str(plen(end["piece"])))
nm = SS.road_at(-0.95, LAT, None)
ok("⭐ 1. Q4: no month — the routes by reference, no figures", [r["route_id"] for r in nm["routes"]] == ["R1", "R2"]
   and nm["a_day"] is None and nm["in"] is None and all(set(r) == {"route_id"} for r in nm["routes"]), str(nm))
_pv = counting.per_visit
counting.per_visit = lambda *x, **k: 1
v1 = SS.road_at(-0.95, LAT, M)
counting.per_visit = _pv
ok("1. an organisation that counts visits: A day = each route's lorries once (R2 5, not 10)",
   rows(v1) == {"R1": (11.5, 0.0, 11.5), "R2": (5.0, 5.0, 5.0)} and v1["a_day"] == 16.5
   and v1["counting"]["unit"] == "visits", str((rows(v1), v1["a_day"])))
# where two roads meet under a click, the clicked route's road is the one asked about
JUNC = (-1.0, LAT + 0.0002)        # 22 m from MAIN's west end and from the northern road's first stretch alike
jr = SS.road_at(*JUNC, M, r_m=60, route="R1")
ok("1. a click where roads meet: the clicked route's own road (R1 is on it)", "R1" in rows(jr), str(rows(jr)))
ok("1. an unknown clicked route: the nearest road, as with none",
   rows(SS.road_at(-0.95, LAT, M, route="R99")) == rows(a))
ok("1. the endpoint passes the clicked route through",
   main.public_road_at(lon=-0.95, lat=LAT + 0.01, r=30, month=M, route="R1")["routes"] == north["routes"])
empty = SS.road_at(-0.95, LAT, 5)
ok("1. a month with nothing approved: the road answers with no routes",
   empty["routes"] == [] and empty["a_day"] == 0.0, str(empty))

# =========================================================================== #
#  2. A box                                                                    #
# =========================================================================== #
b = SS.in_box(-0.96, LAT - 0.002, -0.94, LAT + 0.002, M)
ok("⭐ 2. a box on MAIN: R1 in only (its way back is north), R2 both",
   rows(b) == {"R1": (11.5, 0.0, 11.5), "R2": (5.0, 5.0, 10.0)}, str(rows(b)))
ok("2. the answer carries its box", b["kind"] == "area" and b["box"] == [-0.96, LAT - 0.002, -0.94, LAT + 0.002])
big = SS.in_box(-1.01, LAT - 0.03, -0.89, LAT + 0.02, M)
ok("⭐ 2. Q5: a box over both roads counts R1 ONCE, In and Out (not once per road)",
   rows(big) == {"R1": (11.5, 11.5, 23.0), "R2": (5.0, 5.0, 10.0), "R3": (2.0, 2.0, 4.0)} and big["a_day"] == 37.0,
   str((rows(big), big["a_day"])))
corner = [-0.95, LAT - 0.002, -0.95 + 30 / DEG_M, LAT + 0.002]
cb = SS.in_box(*corner, M)
ok("⭐ 2. Q5: a box the road crosses for only 30 m counts (it enters)", set(rows(cb)) == {"R1", "R2"}, str(rows(cb)))
poly = {"type": "Polygon", "coordinates": [[[corner[0], corner[1]], [corner[2], corner[1]], [corner[2], corner[3]],
                                            [corner[0], corner[3]], [corner[0], corner[1]]]]}
_lim = TL.through(poly, M, ctx=SS._ctx())["routes"]
ok("2. ...where an area traffic limit's entry rule (2.1-1) would not: the box is its own rule", _lim == [], str(_lim))
side = SS.in_box(-0.96, LAT + 0.0005, -0.94, LAT + 0.003, M)
ok("🔴 2. a box beside the road (55 m off) counts nothing", side["routes"] == [] and side["a_day"] == 0.0, str(side))
bn = SS.in_box(-0.96, LAT - 0.002, -0.94, LAT + 0.002, None)
ok("2. Q4: a box with no month names the routes, no figures", [r["route_id"] for r in bn["routes"]] == ["R1", "R2"]
   and bn["a_day"] is None)
for txt, why in (("1,2,3", "three numbers"), ("a,b,c,d", "words"), ("-0.9,52,-1.0,53", "west east of east"),
                 ("-1,53,-0.9,52", "south north of north"), ("-1,52,-1,53", "no width"), ("nan,52,-0.9,53", "nan"),
                 ("-6,50,2,56", "the country")):
    try:
        SS.parse_box(txt)
        ok(f"🔴 2. a bad box is refused ({why})", False)
    except SS.BadBox as e:
        ok(f"🔴 2. a bad box is refused in words ({why})",
           str(e) in ("A box is four numbers: west, south, east, north.", "Draw a smaller box."), str(e))
ok("2. a good box parses", SS.parse_box(" -0.96,52.498,-0.94,52.502 ") == (-0.96, 52.498, -0.94, 52.502))

# =========================================================================== #
#  3. Kept until the next write; no team names; the endpoints and the gate     #
# =========================================================================== #
SS.forget()
BUILDS.clear()
SS.road_at(-0.95, LAT, M)
SS.in_box(-0.96, LAT - 0.002, -0.94, LAT + 0.002, M)
SS.road_at(-0.95, LAT + 0.01, M)
ok("⭐ 3. what is read once is read once for many clicks and boxes", len(BUILDS) == 1, str(len(BUILDS)))
ok("3. warm() says so (a warm click needs no heavy-read slot)", SS.warm() is True)
db.execute("UPDATE routes SET material_category = 'Small aggregate' WHERE id = 'R1'")
ok("3. ...a write makes it cold", SS.warm() is False)
SS.road_at(-0.95, LAT, M)
ok("3. ...and read again after a write", len(BUILDS) == 2, str(len(BUILDS)))
blob = json.dumps([a, b, big, nm, SS.road_at(-0.95, LAT, M)])
ok("🔴 3. no team (slot id or name) in either answer", "IPT1" not in blob and "team" not in blob.lower(), blob[:200])
ok("3. the endpoints answer as the module does",
   main.public_road_at(lon=-0.95, lat=LAT, r=30, month=M, route=None)["routes"] == SS.road_at(-0.95, LAT, M)["routes"]
   and main.public_area_sum(bbox="-0.96,52.498,-0.94,52.502", month=M)["routes"] == b["routes"])
try:
    main.public_area_sum(bbox="1,2,3", month=M)
    ok("🔴 3. a bad box is a 400", False)
except Exception as e:
    ok("🔴 3. a bad box is a 400 in words", getattr(e, "status_code", None) == 400
       and "west, south, east, north" in str(getattr(e, "detail", "")), str(e))
ok("⭐ 3. both reads are behind the map gate", gate.scope_for("/api/public/road-at?lon=1&lat=2") == "map"
   and gate.scope_for("/api/public/area-sum?bbox=1,2,3,4") == "map")
MS = read("backend/main.py")
ok("3. both reads take a heavy-read slot while cold, and none once warm",
   'with _heavy("road-at"):' in MS and 'with _heavy("area-sum"):' in MS and MS.count("if section_select.warm():") == 2)
ok("3. the reads are GETs at the public paths",
   '@app.get("/api/public/road-at")' in MS and '@app.get("/api/public/area-sum")' in MS)
SSRC = read("backend/section_select.py")
ok("3. one count: section_select calls traffic_limits.through, and counts nothing itself",
   "traffic_limits.through(" in SSRC and "vehicle_loads" not in SSRC)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
