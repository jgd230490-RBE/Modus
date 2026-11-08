"""
Works area from a site layout (task 2.1-12, 8 Nov 2026; the mockup John approved: notes works-from-layout-mockup-1108,
Q1-Q8 as recommended): the Site boundary area style and its import guesses, the outline around everything drawn (10 m
out) and the Site boundary area as outlines, a phase's months as dates, the demo package's Z033 made from its layout,
admins only, the plan the panel shows, making a new works area or giving an existing one the outline (its name, dates
and routing kept), the refusals in words, "layout changed since" / "changed on Zones" / Update, the Zones read and the
organisation file.

WHAT THIS DOES NOT PROVE: the screens (parse_frontend, the UI audit), the map preview, Postgres, the HTTP layer (stubbed).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_works_from_layout.py
"""
import asyncio
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import types
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
FIX = os.path.join(HERE, "fixtures", "site_layouts")
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
    def __init__(self, status_code, detail="", headers=None):
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
    def __init__(self, headers=None, body=b"", cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = cookies or {}

    async def stream(self):
        for i in range(0, len(self._body), 65536):
            yield self._body[i:i + 65536]


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

TMP = tempfile.mkdtemp(prefix="rbe_works_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import limits  # noqa: E402
import tenant_package  # noqa: E402
import site_layouts as SL  # noqa: E402
import site_layout_import as SI  # noqa: E402
import site_layout_styles as ST  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"


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


import works_from_layout as WL  # noqa: E402
import zones  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def http(fn, *a, **k):
    """(status, answer) for a main.* endpoint: 200 and the value, or the HTTPException's code and detail."""
    try:
        return 200, fn(*a, **k)
    except _HTTPException as e:
        return e.status_code, e.detail


ADMIN = {"via": "login", "role": "admin", "ipt": None, "can_approve": True, "name": "Test admin", "user_id": "U-test"}
PLANNER = {"via": "code", "role": "planner", "ipt": None, "can_approve": True, "label": "Planner"}


def as_(acc):
    access._ACCESS.set(acc)


def m_frame(lat0):
    return 111320.0 * math.cos(math.radians(lat0)), 110574.0


def dist_to_ring_m(p, ring):
    """Shortest distance (m) from a [lon, lat] point to a ring's edges, in a flat frame about the point."""
    kx, ky = m_frame(p[1])
    P = (0.0, 0.0)
    best = 1e18
    for a, b in zip(ring, ring[1:]):
        A = ((a[0] - p[0]) * kx, (a[1] - p[1]) * ky)
        B = ((b[0] - p[0]) * kx, (b[1] - p[1]) * ky)
        dx, dy = B[0] - A[0], B[1] - A[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((P[0] - A[0]) * dx + (P[1] - A[1]) * dy) / L))
        best = min(best, math.hypot(A[0] + t * dx, A[1] + t * dy))
    return best


def inside(p, ring):
    x, y = p
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def convex(ring):
    r = ring[:-1]
    sgn = set()
    for i in range(len(r)):
        a, b, c = r[i], r[(i + 1) % len(r)], r[(i + 2) % len(r)]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) > 1e-14:
            sgn.add(cr > 0)
    return len(sgn) == 1


def coords(g):
    return WL._coords(g.get("coordinates"), [])


PKG = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
reset_db()
res = tenant_package.import_tenant(PKG, replace=True)
ok("setup: the demo package imports", res.get("ok"), str(res)[:200])

# =========================================================================== #
#  1. The Site boundary style and the import guesses (Q1 b, card 5)           #
# =========================================================================== #
B = ST.AREA_STYLES.get("boundary") or {}
ok("1. a Site boundary area style: dashed edge, no fill, no words", (B.get("label"), B.get("fill"), B.get("outline"), B.get("text"))
   == ("Site boundary", "none", "dashed", ""), str(B))
ok("1. it is drawn by the editor's table (the styles read lists it)", any(a["key"] == "boundary" for a in ST.payload()["areas"]))
ok("1. a no-fill style is a fill the table knows", "none" in ST.FILLS)
for name in ("SITE_BOUNDARY", "Boundary", "RED_LINE", "REDLINE", "C-SITE-BOUNDARY"):
    ok(f"1. a drawing's layer {name} lands on the Site boundary area", ST.guess(name, {"LineString"}) == "area:boundary",
       ST.guess(name, {"LineString"}))
ok("1. other layers keep their guesses (HOARDING, HERAS FENCE, LAYDOWN)",
   (ST.guess("HOARDING", {"LineString"}), ST.guess("HERAS FENCE", {"LineString"}), ST.guess("LAYDOWN", {"Polygon"}))
   == ("line:hoarding", "line:heras", "area:laydown"))
t, why = SL.clean_thing({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-0.88, 52.64], [-0.879, 52.64], [-0.879, 52.641], [-0.88, 52.64]]]},
                         "properties": {"style": "boundary"}})
ok("1. a Site boundary thing saves (layer Areas)", t is not None and t["properties"]["layer"] == "Areas", str(why))
ok("1. it is not one of the words-on-the-map styles: the public read passes it as an area",
   SL.public_thing(t) is not None and SL.public_thing(t)["properties"].get("style") == "boundary")

# =========================================================================== #
#  2. The outline around everything drawn (Q1 a)                               #
# =========================================================================== #
ph_rows = PKG["tables"]["site_layout_phases"]
PH = ph_rows[0]
THINGS = json.loads(PH["features_json"])["features"]
ok("2. the demo has one phase on L019, Site logistics, 39 things",
   (len(ph_rows), PH["id"], PH["name"], len(THINGS)) == (1, "PH001", "Site logistics", 39))
G = WL.outline_all(THINGS)
ring = G["coordinates"][0]
ok("2. a closed GeoJSON Polygon", G["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) >= 4)
ok("2. convex", convex(ring))
pts = [p for f in THINGS for p in coords(f["geometry"])]
ok("2. every coordinate of every thing is inside it", all(inside(p, ring) for p in pts),
   str(sum(1 for p in pts if not inside(p, ring))))
dmin = min(dist_to_ring_m(p, ring) for p in pts)
ok("2. no thing closer than 10 m to the edge (the margin), none much further at its nearest", 9.999 <= dmin <= 10.3, f"{dmin:.3f}")
ok("2. coordinates to 7 decimal places", all(round(c, 7) == c for p in ring for c in p))
ha = WL.ring_area_m2(ring) / 1e4
ok("2. its area is the mockup's 24.6 ha within 0.6 ha (the mockup pushed corners out, this buffers exactly)", abs(ha - 24.6) <= 0.6, f"{ha:.2f}")
G0 = WL.outline_all(THINGS, margin_m=0)
ok("2. a 0 m margin is smaller and still holds every coordinate (on its edge or inside)",
   WL.ring_area_m2(G0["coordinates"][0]) < WL.ring_area_m2(ring)
   and all(inside(p, G0["coordinates"][0]) or dist_to_ring_m(p, G0["coordinates"][0]) < 0.05 for p in pts))
ok("2. nothing drawn -> None", WL.outline_all([]) is None and WL.outline_all(None) is None)
one = WL.outline_all([{"geometry": {"type": "Point", "coordinates": [-0.88, 52.64]}}])
ok("2. one symbol -> a 10 m circle round it (about 314 m², the 16-gon round it)", one and 314 <= WL.ring_area_m2(one["coordinates"][0]) <= 322,
   str(one and WL.ring_area_m2(one["coordinates"][0])))

# =========================================================================== #
#  3. The Site boundary area as the outline                                     #
# =========================================================================== #
def box(lon, lat, w, h):
    return [[lon, lat], [lon + w, lat], [lon + w, lat + h], [lon, lat + h], [lon, lat]]


small = {"geometry": {"type": "Polygon", "coordinates": [box(-0.885, 52.643, 0.001, 0.001)]}, "properties": {"style": "boundary"}}
big = {"geometry": {"type": "Polygon", "coordinates": [box(-0.888, 52.642, 0.008, 0.004), box(-0.886, 52.643, 0.001, 0.001)]},
       "properties": {"style": "boundary"}}
lay = {"geometry": {"type": "Polygon", "coordinates": [box(-0.889, 52.641, 0.02, 0.02)]}, "properties": {"style": "laydown"}}
bd = WL.outline_boundary([small, big, lay])
ok("3. no Site boundary area -> None", WL.outline_boundary(THINGS) is None and WL.outline_boundary([lay]) is None)
ok("3. the largest Site boundary area wins (a bigger laydown does not count)", bd["coordinates"][0] == box(-0.888, 52.642, 0.008, 0.004))
ok("3. its holes are dropped (a works area is the whole site)", len(bd["coordinates"]) == 1)
unc = WL.outline_boundary([{"geometry": {"type": "Polygon", "coordinates": [box(-0.888, 52.642, 0.001, 0.001)[:-1]]}, "properties": {"style": "boundary"}}])
ok("3. an unclosed ring comes back closed", unc["coordinates"][0][0] == unc["coordinates"][0][-1])

# =========================================================================== #
#  4. The phase's months as dates (Q3)                                          #
# =========================================================================== #
ok("4. Feb 2027 -> 1 Feb to 28 Feb", WL.month_dates("2027-02", "2027-02") == ("2027-02-01", "2027-02-28"))
ok("4. Feb 2028 (a leap year) ends on the 29th", WL.month_dates("2028-01", "2028-02") == ("2028-01-01", "2028-02-29"))
ok("4. an open end stays open; every month = no dates (always)",
   WL.month_dates("2027-05", None) == ("2027-05-01", None) and WL.month_dates(None, None) == (None, None))

# =========================================================================== #
#  5. The demo package (John, 8 Nov: "do this for the current site layouts")   #
# =========================================================================== #
Z033 = next(z for z in PKG["tables"]["zones"] if z["id"] == "Z033")
zg = json.loads(Z033["geometry"]) if isinstance(Z033["geometry"], str) else Z033["geometry"]
ok("5. the package's Z033 is the Tilton viaduct works area, works, routing off, its dates kept",
   (Z033["name"], Z033["kind"], bool(Z033["affects_routing"]), Z033["starts_on"], Z033["ends_on"])
   == ("Tilton viaduct works area", "works", False, "2026-05-01", "2028-05-31"))
ok("5. its outline IS the layout's outline (around everything drawn), not the typed box", zg == G)
ok("5. it remembers the phase and its version", (Z033.get("from_phase_id"), Z033.get("from_phase_version")) == ("PH001", 1))
others = [z for z in PKG["tables"]["zones"] if z["id"] != "Z033"]
ok("5. no other zone in the package came from a layout", all(not z.get("from_phase_id") for z in others))
ok("5. zone ids unchanged: 40 zones, Z040 the last", (len(PKG["tables"]["zones"]), PKG["tables"]["zones"][-1]["id"]) == (40, "Z040"),
   str((len(PKG["tables"]["zones"]), PKG["tables"]["zones"][-1]["id"])))
ok("5. imported: by_phase says PH001 made Z033 and they match", WL.by_phase().get("PH001") ==
   {"zone_id": "Z033", "name": "Tilton viaduct works area", "state": "same"}, str(WL.by_phase()))
L019_NAME = next(r["name"] for r in PKG["tables"]["locations"] if r["id"] == "L019")
ok("5. sources(): Z033 is from L019's layout", WL.sources() == {"Z033": {"location_id": "L019", "site": L019_NAME}}, str(WL.sources()))

# =========================================================================== #
#  6. Who may (Q7): admins only                                                #
# =========================================================================== #
as_(PLANNER)
st, _ = http(main.works_area_plan, "PH001")
ok("6. a planner is refused the plan (403)", st == 403, str(st))
st, _ = http(main.works_area_make, "PH001", main.WorksAreaIn())
ok("6. and the write (403); nothing changed", st == 403 and WL.by_phase()["PH001"]["state"] == "same", str(st))
as_(None)
st, _ = http(main.works_area_plan, "PH001")
ok("6. signed out: 403", st == 403, str(st))
as_(ADMIN)
st, P = http(main.works_area_plan, "PH001")
ok("6. an admin login reads the plan", st == 200, str(P)[:200])

# =========================================================================== #
#  7. The plan the panel shows                                                  #
# =========================================================================== #
ok("7. the default outline is around everything drawn (no Site boundary area on the demo)",
   (P["default_outline"], P["outlines"]["boundary"], P["hectares"]["boundary"]) == ("all", None, None))
ok("7. the outline is outline_all's", P["outlines"]["all"] == G)
ok("7. hectares to one place", P["hectares"]["all"] == round(ha, 1), str(P["hectares"]))
ok("7. name '<site> works area'", P["name"] == f"{L019_NAME} works area", P["name"])
ok("7. an every-month phase gives no dates", (P["starts_on"], P["ends_on"]) == (None, None))
ok("7. the works area made from this phase is offered first (Q6)",
   P["works_areas"] and P["works_areas"][0]["id"] == "Z033" and P["works_areas"][0]["from_this_phase"])
ok("7. only works areas are offered (no closure / haul road / weight limit)",
   all(zones.get_zone(z["id"])["kind"] == "works" for z in P["works_areas"]))
ok("7. a works area far away is not offered (Z005 Melton)", all(z["id"] != "Z005" for z in P["works_areas"]))
ok("7. the phase's version is sent", P["version"] == 1)
st, _ = http(main.works_area_plan, "PH999")
ok("7. a phase that does not exist: 404", st == 404)

# =========================================================================== #
#  8. Make a new works area                                                     #
# =========================================================================== #
n0 = len(zones.list_zones())
st, j = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", name="  Viaduct works (new)  ", starts_on="2027-01-01",
                                                               ends_on="2027-06-30", affects_routing=False, version=1))
ok("8. a new works area is made", st == 200 and len(zones.list_zones()) == n0 + 1, str(j)[:300])
NZ = j["zone"] if st == 200 else {}
ok("8. kind works, routing off, the name trimmed, the dates as typed",
   (NZ.get("kind"), NZ.get("affects_routing"), NZ.get("name"), NZ.get("starts_on"), NZ.get("ends_on"))
   == ("works", False, "Viaduct works (new)", "2027-01-01", "2027-06-30"), str(NZ)[:300])
ok("8. its outline is the layout's", NZ.get("geometry") == G)
ok("8. it remembers PH001 version 1", WL.sources().get(NZ.get("id"), {}).get("location_id") == "L019")
ok("8. a routing-off works area re-routes nothing", j.get("rebake_required") is False and j.get("here_calls") == 0, str(j.get("invalidated")))
st, j2 = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", name="", version=1))
ok("8. a blank name takes '<site> works area', no dates = always",
   st == 200 and (j2["zone"]["name"], j2["zone"]["starts_on"], j2["zone"]["ends_on"]) == (f"{L019_NAME} works area", None, None),
   str(j2)[:200])
zones.delete_zone(j2["zone"]["id"])
st, j3 = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", name="With routing", starts_on="2027-01-01",
                                                                ends_on="2027-01-31", affects_routing=True, version=1))
ok("8. Affects routing ticked is kept (a dated one diverts in its dates only)", st == 200 and j3["zone"]["affects_routing"] is True, str(j3)[:200])
zones.delete_zone(j3["zone"]["id"])
zones.delete_zone(NZ["id"])

# =========================================================================== #
#  9. Refusals in words                                                         #
# =========================================================================== #
st, d = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", version=7))
ok("9. a stale version: 409 in words", st == 409 and "saved this layout since" in str(d), str((st, d)))
st, d = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="boundary", version=1))
ok("9. Site boundary asked for, none drawn: 422 in words", st == 422 and "no Site boundary area" in str(d), str((st, d)))
st, d = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="hull", version=1))
ok("9. an unknown outline: 422", st == 422, str((st, d)))
st, d = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", zone_id="Z001", version=1))
ok("9. a zone that is not a works area cannot take the outline (Z001 a haul road): 404", st == 404, str((st, d)))
st, d = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", zone_id="Z999", version=1))
ok("9. a zone that does not exist: 404", st == 404)
ok("9. none of them changed Z033", zones.get_zone("Z033")["geometry"] == G and WL.by_phase()["PH001"]["state"] == "same")

# =========================================================================== #
# 10. The layout changes, then Update; an edit on Zones (Q5)                   #
# =========================================================================== #
moved = json.loads(json.dumps(THINGS))
moved.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.8800, 52.6500]},
              "properties": {"style": "sym", "sym": "fuel", "layer": "Plant"}})
SL.save_things("PH001", {"features": {"type": "FeatureCollection", "features": moved}, "version": 1}, "test")
ok("10. the phase saved again: 'layout changed since'", WL.by_phase()["PH001"]["state"] == "layout_changed", str(WL.by_phase()))
ok("10. and Z033 has NOT moved by itself", zones.get_zone("Z033")["geometry"] == G)
st, lay_r = http(main.get_site_layout, "L019")
ok("10. the layout read carries it on the phase", st == 200 and lay_r["layout"]["phases"][0].get("works_area", {}).get("state") == "layout_changed")
st, P2 = http(main.works_area_plan, "PH001")
st, j = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", zone_id="Z033", name="ignored", starts_on="2030-01-01",
                                                               affects_routing=True, version=P2["version"]))
z33 = zones.get_zone("Z033")
ok("10. Update gives Z033 the new outline (it now holds the new symbol)", st == 200 and inside([-0.8800, 52.6500], z33["geometry"]["coordinates"][0]),
   str(j)[:200])
ok("10. keeping a zone keeps its name, dates and routing (what the body says is ignored)",
   (z33["name"], z33["starts_on"], z33["ends_on"], z33["affects_routing"]) == ("Tilton viaduct works area", "2026-05-01", "2028-05-31", False))
ok("10. back to 'same', at the phase's new version", WL.by_phase()["PH001"]["state"] == "same"
   and j.get("works_area", {}).get("state") == "same")
G2 = z33["geometry"]
st, _ = http(main.update_zone, "Z033", main.ZoneIn(name="Tilton viaduct works area (renamed)", geometry=G2))
ok("10. an edit on Zones that keeps the outline keeps 'same'", st == 200 and WL.by_phase()["PH001"]["state"] == "same")
g3 = {"type": "Polygon", "coordinates": [box(-0.888, 52.642, 0.01, 0.005)]}
st, _ = http(main.update_zone, "Z033", main.ZoneIn(name="Tilton viaduct works area", geometry=g3))
ok("10. an outline edited on Zones: 'changed on Zones'", st == 200 and WL.by_phase()["PH001"]["state"] == "zone_changed", str(WL.by_phase()))
ok("10. and still listed as from the layout on Zones", "Z033" in WL.sources())
st, P3 = http(main.works_area_plan, "PH001")
http(main.works_area_make, "PH001", main.WorksAreaIn(outline="all", zone_id="Z033", version=P3["version"]))
ok("10. Update again: 'same'", WL.by_phase()["PH001"]["state"] == "same" and zones.get_zone("Z033")["geometry"] == G2)

# =========================================================================== #
# 11. A Site boundary area on the phase                                         #
# =========================================================================== #
ring_b = box(-0.8880, 52.6430, 0.0060, 0.0030)
with_b = moved + [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring_b]},
                   "properties": {"style": "boundary", "layer": "Areas"}}]
SL.save_things("PH001", {"features": {"type": "FeatureCollection", "features": with_b}, "version": P3["version"]}, "test")
st, P4 = http(main.works_area_plan, "PH001")
ok("11. with a Site boundary area the panel offers it first", P4["default_outline"] == "boundary"
   and P4["outlines"]["boundary"]["coordinates"][0] == [[round(a, 7), round(b, 7)] for a, b in ring_b])
ok("11. both hectares given", P4["hectares"]["boundary"] and P4["hectares"]["all"] and P4["hectares"]["boundary"] < P4["hectares"]["all"],
   str(P4["hectares"]))
st, j = http(main.works_area_make, "PH001", main.WorksAreaIn(outline="boundary", zone_id="Z033", version=P4["version"]))
ok("11. Z033 takes the boundary's outline", st == 200 and zones.get_zone("Z033")["geometry"] == P4["outlines"]["boundary"])

# =========================================================================== #
# 12. The reads: Zones and the organisation file                               #
# =========================================================================== #
zl = main.list_zones()
ok("12. /api/zones carries from_layout (Zones' 'From the <site> site layout')", zl.get("from_layout", {}).get("Z033", {}).get("site") == L019_NAME)
exp = tenant_package.export_tenant()
z33x = next(z for z in exp["tables"]["zones"] if z["id"] == "Z033")
ok("12. the organisation file keeps the link", (z33x.get("from_phase_id"), z33x.get("from_phase_version")) == ("PH001", P4["version"]))
st, _ = http(main.works_area_plan, "PH001")
db.execute("DELETE FROM site_layout_phases WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "PH001"))
ok("12. the phase deleted: the card has nothing to show and Zones drops the line (the zone stays)",
   "PH001" not in WL.by_phase() and "Z033" not in WL.sources() and zones.get_zone("Z033") is not None)
st, _ = http(main.works_area_plan, "PH001")
ok("12. and the plan is a 404", st == 404)

# =========================================================================== #
# 13. Source checks: the endpoints are admin writes and the page's words      #
# =========================================================================== #
src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
for ep in ("def works_area_plan", "def works_area_make"):
    i = src.index(ep)
    ok(f"13. {ep[4:]} checks the admin first", "_check_admin(token)" in src[i:i + 900].split("\n\n\n")[0])
ok("13. the write goes through the Zones write (same re-routing)", "update_zone(body.zone_id, ZoneIn(" in src and "create_zone(ZoneIn(" in src)
ok("13. a Zones outline edit marks the zone as changed", "works_from_layout.zone_outline_edited(zone_id)" in src)

as_(None)
# 14. a database with no site layout tables (an older harness schema): the Zones read and the layout card's read answer
# "none", any other failure still raises
ok("14. no site layout table reads as none (SQLite and Postgres words); another error does not",
   WL._no_layout_tables(Exception("no such table: site_layout_phases"))
   and WL._no_layout_tables(Exception('relation "site_layouts" does not exist'))
   and not WL._no_layout_tables(Exception("no such table: zones"))
   and not WL._no_layout_tables(Exception("database is locked")))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
