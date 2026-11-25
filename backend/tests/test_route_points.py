"""
"Take care on this route" (25 Nov 2026, the Look-ahead rethink, card 4; John's "Yes, as recommended" to Q12 to Q16) —
backend/route_points.py, the block on the Driver sheet (lorry_plan.build_pdf / sheet_pages) and the Route sheet
(export.build_route_sheet_pdf), and the read GET /api/forecast-weeks/lorry-plan/sheet.

WHAT IS ASSERTED
----------------
  * the words of a distance (First ¼ mi, ¾ mi, whole miles, one decimal in km) and of a stretch;
  * the rule on made-up lines, places and stored limit hits: every limit at or over a line each, never one that reads
    "allowed", "within" or "unknown", another lorry's never; a mile mark only where the stored sign sits on the line;
    the sentence over the limits, one a kind, and the OVER sentence; places within 250 m by the best-option rule's own
    measure (the same places route_best._places counts), by their stored name, a group of one kind within 1 km as one
    line with its stretch; the line IN USE that day (a diversion in force: its line, its limits, its page; a day before
    it: the main line, nothing printed about it); a peak-hours road on a weekday only; a closure with no diversion;
    "Limits not checked for this lorry" (never checked, a re-route since the check) never shown clean; nothing stored;
    the gate line; the cut (three place lines each way: hospitals, schools nearest the road, health centres; in travel
    order; "+n more"); a point two routes share printed once;
  * the Route sheet's pages after the first as route_sheet.sheet lists them;
  * every demo route (stand-in straight lines, made-up places): no banned word ("safe", "clear", "dangerous", a
    collision); the longest block is printed;
  * the module reads only: no fetch, no basemap, no write (source).

WHAT THIS DOES NOT PROVE
------------------------
The lines here are made up: the demo package draws no routes. The rule on live's REAL lines, limits and places was run
on a local copy of live's 24 Nov organisation file by backend/tests/lib/points_livecopy.py (notes/session-1125-driver-
sheet-points.md). Postgres is not run.

Run:  python3 backend/tests/test_route_points.py
"""
import copy
import datetime
import io
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

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
        self.cookies = {}


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

TMP = tempfile.mkdtemp(prefix="wayscope_route_points_")
from portable import remove_scratch_db, pdf_text, offline, pin_today   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "route-points-admin-token"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import export  # noqa: E402
import access  # noqa: E402
import route_points as rp  # noqa: E402

offline(export)
TODAY = pin_today(datetime.date(2026, 11, 26))

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


# --------------------------------------------------------------------------- 1. the words of a distance
ok("1: miles: First ¼ mi to a quarter mile, quarters below a mile, whole miles from 1",
   [rp.mark(k, "mi") for k in (0.1, 0.4, 0.6, 0.85, 1.2, 1.5, 21.0, 45.0)]
   == ["First ¼ mi", "First ¼ mi", "¼ mi", "½ mi", "¾ mi", "1 mi", "13 mi", "28 mi"],
   str([rp.mark(k, "mi") for k in (0.1, 0.4, 0.6, 0.85, 1.2, 1.5, 21.0, 45.0)]))
ok("1: kilometres: one decimal, at least 0.1", [rp.mark(k, "km") for k in (0.02, 0.44, 12.345)] == ["0.1 km", "0.4 km", "12.3 km"])
ok("1: a stretch: one mark when both ends read the same, 'First …' from the start, 'a–b mi' otherwise",
   rp.stretch(21.0, 21.3, "mi") == "13 mi" and rp.stretch(0.1, 0.9, "mi") == "First ½ mi"
   and rp.stretch(22.0, 24.0, "mi") == "14–15 mi" and rp.stretch(3.2, 4.04, "km") == "3.2–4.0 km",
   str((rp.stretch(21.0, 21.3, "mi"), rp.stretch(0.1, 0.9, "mi"), rp.stretch(22.0, 24.0, "mi"), rp.stretch(3.2, 4.04, "km"))))
ok("1: a leg's length: '34 miles', '1 mile', 'under 1 mile', '54.8 km'",
   rp.leg_length(54.76, "mi") == "34 miles" and rp.leg_length(1.7, "mi") == "1 mile" and rp.leg_length(0.55, "mi") == "under 1 mile"
   and rp.leg_length(54.76, "km") == "54.8 km")

# --------------------------------------------------------------------------- 2. the demo, with made-up lines, places and limits
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
config.invalidate(); costing.invalidate()
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
res = tenant_package.import_tenant(DEMO, replace=True)
ok("2: the demo imports", res.get("ok") is True, str(res)[:200])
config.invalidate(); costing.invalidate()
access.set_current("planner123")
T = db.current_tenant()
UNIT = export._du()
ok("2: the demo reads miles", UNIT == "mi", UNIT)
FLAT, TIP = "Artic Flatbed (44t)", "Artic Tipper (44t)"
CHECKED = "2026-11-24T14:56:24+00:00"
BAKED = "2026-10-31T09:22:14.928888+00:00"
LAT0 = 52.50
KX = 111320.0 * __import__("math").cos(__import__("math").radians(LAT0))
KY = 110574.0


def P(lon0, km, north_m=0.0, lat0=LAT0):
    """A position `km` east of lon0 along the parallel lat0, `north_m` metres north of it."""
    return [round(lon0 + km * 1000.0 / KX, 7), round(lat0 + north_m / KY, 7)]


def line(lon0, km, lat0=LAT0, step=0.1):
    n = int(round(km / step))
    return [P(lon0, i * step, 0.0, lat0) for i in range(n + 1)]


def put_line(rid, veh, leg, alt, coords, computed=BAKED):
    import math
    km = sum(rp._hav_m(a, b) for a, b in zip(coords, coords[1:])) / 1000.0
    db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? AND leg = ? AND alt_index = ?",
               (T, rid, veh, leg, alt))
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (T, rid, veh, leg, alt, json.dumps(coords), km, km / 50.0, computed))


def put_hits(rid, hits, checked=CHECKED, status="ok"):
    db.execute("UPDATE routes SET limits_hits = ?, limits_checked_at = ?, limits_status = ? WHERE tenant_id = ? AND id = ?",
               (json.dumps(hits), checked, status, T, rid))


def hit(leg, verdict, kind="height", value=4.0, name=None, ref=None, anchor=None, veh=FLAT, alt=0, point=False, ext="w1",
        vv=4.0, exceptions=None, signed=None):
    import limits
    h = {"vehicle_profile": veh, "leg": leg, "source": "osm", "ext_id": ext, "kind": kind, "limit": value,
         "unit": "m" if kind in ("height", "width") else "t", "signed": signed, "name": name, "ref": ref,
         "exceptions": exceptions, "point": point, "along_m": 10.0, "verdict": verdict, "vehicle_value": vv,
         "anchor": anchor, "headline": "x"}
    if alt:
        h["alt_index"] = alt
    return h


FEATS = []


def feature(fid, kind, pos, name=None):
    FEATS.append((fid, kind, pos, name))
    db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
               "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (T, fid, kind, "osm", fid, name, None, json.dumps({"type": "Point", "coordinates": pos}), 10.0, CHECKED))


db.execute("DELETE FROM community_features WHERE tenant_id = ?", (T,))
db.execute("INSERT INTO community_meta (tenant_id, meta_id, state, started_at, fetched_at, by_whom, detail_json) "
           "VALUES (?, 'current', 'done', ?, ?, 'test', '{}')", (T, CHECKED, CHECKED))

# R012: 34 km east along 52.50 N; back the same way; a diversion (alt 1) 3 km north in Dec 2027
LON_A = -0.90
OUT = line(LON_A, 34.0)
BACK = list(reversed(OUT))
DIV_OUT = line(LON_A, 34.0, lat0=LAT0 + 3000.0 / KY)
put_line("R012", FLAT, "loaded", 0, OUT); put_line("R012", FLAT, "return", 0, BACK)
put_line("R012", FLAT, "loaded", 1, DIV_OUT); put_line("R012", FLAT, "return", 1, list(reversed(DIV_OUT)))
put_hits("R012", [
    hit("loaded", "at_limit", name="Melton Road", ref="B6047", anchor=P(LON_A, 5.0), signed="13'0\""),
    hit("loaded", "allowed", kind="weight", value=7.5, name="Hunters Way", anchor=P(LON_A, 7.0), ext="w2", vv=44.0),
    hit("loaded", "within", kind="weight", value=60.0, name="Big Road", anchor=P(LON_A, 8.0), ext="w3", vv=44.0),
    hit("loaded", "unknown", kind="axle", value=10.0, name="Axle Lane", anchor=P(LON_A, 9.0), ext="w4", vv=None),
    hit("return", "at_limit", anchor=P(LON_A, 20.0, 40.0), point=True, ext="n5"),
    hit("return", "at_limit", name="Kettering Road", anchor=P(LON_A, 30.0), ext="w6", signed="13'1\""),
    hit("return", "at_limit", name="Diversion Lane", anchor=P(LON_A, 12.0, 3000.0), ext="w7", alt=1),
    hit("loaded", "exceeds", kind="weight", value=7.5, name="Tipper Lane", anchor=P(LON_A, 3.0), veh=TIP, ext="w8", vv=44.0),
])
# places along R012 (km east of LON_A, metres north of the line)
feature("s1", "schools", P(LON_A, 0.10, 120), "The Divergent School Harborough")
feature("s2", "schools", P(LON_A, 0.20, 200), "Little Angels Day Nursery")
feature("s3", "schools", P(LON_A, 0.30, -90), "Brooke House College")
feature("s4", "schools", P(LON_A, 0.38, 60), "Market Harborough CofE Academy")
feature("h1", "hospitals", P(LON_A, 1.25, 200), "St Lukes Hospital")
feature("s5", "schools", P(LON_A, 4.0, 30), None)
feature("s6", "schools", P(LON_A, 21.0, 240), "Tugby CofE Primary School")
feature("s7", "schools", P(LON_A, 21.5, 260), "Too Far School")
feature("c1", "health", P(LON_A, 31.8, 50), "Uppingham Surgery")
feature("s8", "schools", P(LON_A, 33.9, 10), "Langham CofE (Controlled) Primary School")
feature("x1", "sports", P(LON_A, 15.0, 5), "Rugby Ground")
feature("x2", "community", P(LON_A, 16.0, 5), "Village Hall")
feature("d1", "schools", P(LON_A, 12.0, 3010.0), "Diversion Primary")

DAY = "2026-11-24"           # a Tuesday
CTX = rp.Context(DAY)
A = rp.points("R012", FLAT, DAY, ctx=CTX)
LO, RE = A["legs"]
ok("2: the block: its heading and foot, both ways, routed, limits checked on the check's date",
   A["head"] == "Take care on this route" and A["foot"] == "What Wayscope holds within 250 m of the route. Road signs come first."
   and [L["leg"] for L in A["legs"]] == ["loaded", "return"] and A["routed"] and A["limits"] == "checked"
   and A["limits_checked"] == "2026-11-24" and rp.checked_words(A) == "Limits checked 24 Nov 2026.")
ok("2: the legs' headings: 'Going loaded' and 'Coming back', the length in miles",
   (LO["title"], RE["title"], LO["length"], RE["length"]) == ("Going loaded", "Coming back", "21 miles", "21 miles"),
   str((LO["length"], RE["length"])))
ok("2: limits: the at-limit height out only; never 'allowed', 'within', 'unknown' or another lorry's hit",
   [i["text"] for i in LO["limits"]] == ["Height limit (13'0\") · Melton Road, B6047 · 3 mi"], str([i["text"] for i in LO["limits"]]))
ok("2: ...a limit's value is its own column", LO["limits"][0]["w"] == "4.0 m" and LO["limits"][0]["state"] == "at")
ok("2: back: Kettering Road with its mile mark; the point limit 40 m off the line: no road name stored, NO mile mark; "
   "the diversion's limit (alt 1) not on today's line",
   [i["text"] for i in RE["limits"]] == ["Height limit (13'1\") · Kettering Road · 2 mi",
                                         "Height limit (13'1\") · no road name stored: see the map on the route sheet"],
   str([i["text"] for i in RE["limits"]]))
ok("2: the sentence over the limits, one a kind: the height",
   A["sentences"] == ["This lorry is 4.0 m high: at the limit at every height limit below. Check its real height before you set off."],
   str(A["sentences"]))
pl = [(i["w"], i["text"]) for i in LO["places"]]
ok("2: places out: four schools in the first quarter mile as one line; the hospital by its name; an unnamed school; "
   "Tugby at 240 m; not the school at 260 m; the surgery; Langham; in travel order",
   pl == [("First ¼ mi", "4 schools"), ("¾ mi", "St Lukes Hospital"), ("2 mi", "a school"), ("13 mi", "Tugby CofE Primary School"),
          ("20 mi", "Uppingham Surgery"), ("21 mi", "Langham CofE (Controlled) Primary School")], str(pl))
ok("2: no sports ground, community centre or other kind is a place on the block",
   not any(i["place_kind"] not in ("schools", "hospitals", "health") for L in A["legs"] for i in L["places"]))
plb = [(i["w"], i["text"]) for i in RE["places"]]
ok("2: places back: the same places from the other end, in the order met",
   plb[0] == ("First ¼ mi", "Langham CofE (Controlled) Primary School") and plb[-1][1] == "4 schools" and len(plb) == 6, str(plb))
# the best-option rule's own measure: the same places on these two lines
import route_best  # noqa: E402
import route_compare  # noqa: E402


class _RB:
    features = []


for fid, kind, pos, _n in FEATS:
    _RB.features.append((kind, [pos], (pos[0], pos[1], pos[0], pos[1])))
_rb = route_best._places([OUT, BACK], _RB)
_ids = {k for L in A["legs"] for i in L["places"] for k in i["keys"]}
ok("2: the places are the best-option rule's own: as many schools, hospitals and health centres as route_best._places counts on the pair",
   len(_ids) == sum(_rb[k] for k in route_best.DECIDING_KINDS) == 9, f"{len(_ids)} {_rb}")
ok("2: the 250 m is the rule's own measure", route_best.PLACES_M == 250 and all(route_compare.NEAR_M[k] == 250 for k in rp.PLACE_KINDS))
ok("2: nothing stored is not said when something is", A["nothing"] is None and A["closures"] == [])
ok("2: the gate line: the site, its gate, its hours or the default, the scheme's no-delivery windows",
   A["gate"].startswith(A["dest"] + ":") and "No deliveries" in A["gate"] and A["gate"].endswith("."), A["gate"])

# the cut
C = rp.cut(A)
cl = [i["text"] for i in C["legs"][0]["places"]]
ok("2: the cut: three place lines out: the hospital, then the schools nearest the road (Langham 10 m, the unnamed 30 m); "
   "printed in travel order", cl == ["St Lukes Hospital", "a school", "Langham CofE (Controlled) Primary School"], str(cl))
ok("2: ...the rest counted in places, not lines: the 4 schools and Tugby and the surgery = +6 more",
   C["legs"][0]["more"] == 6 and rp.more_words(6) == "+6 more on the route sheet", str(C["legs"][0]["more"]))
ok("2: ...limits are never cut", C["legs"][0]["limits"] == LO["limits"] and C["legs"][1]["limits"] == RE["limits"])
ok("2: ...the cut works on a copy", len(A["legs"][0]["places"]) == 6)
C2 = rp.cut(A, places=10)
ok("2: a cut with room for everything leaves nothing over", C2["legs"][0]["more"] == 0 and len(C2["legs"][0]["places"]) == 6)

# the over sentence, and a lorry whose limits were never checked or re-routed since
OUT40 = line(-0.50, 6.0, lat0=52.30)
put_line("R040", FLAT, "loaded", 0, OUT40); put_line("R040", FLAT, "return", 0, list(reversed(OUT40)))
put_hits("R040", [hit("loaded", "exceeds", kind="weight", value=7.5, name="Hunters Way", anchor=P(-0.50, 2.0, 0, 52.30),
                      ext="w9", vv=44.0, exceptions="Except for access"),
                  hit("loaded", "at_limit", kind="height", anchor=P(-0.50, 3.0, 0, 52.30), ext="w10", name="Low Bridge Road")])
B = rp.points("R040", FLAT, DAY, ctx=CTX)
ok("2: a limit this lorry is OVER: its line says so with the sign's exception; the OVER sentence first; the height at-limit sentence kept",
   B["legs"][0]["limits"][0]["text"] == "Weight limit · Hunters Way, except for access · this lorry is over it · 1 mi"
   and B["sentences"][0] == rp.OVER == "This lorry is over a limit below. Ask the site team before you run."
   and any("at every height limit" in s for s in B["sentences"]) and B["legs"][0]["limits"][0]["state"] == "over",
   str((B["legs"][0]["limits"], B["sentences"])))
OUT41 = line(-0.50, 4.0, lat0=52.20)
put_line("R041", FLAT, "loaded", 0, OUT41); put_line("R041", FLAT, "return", 0, list(reversed(OUT41)))
db.execute("UPDATE routes SET limits_hits = NULL, limits_checked_at = NULL, limits_status = NULL WHERE tenant_id = ? AND id = ?", (T, "R041"))
N = rp.points("R041", FLAT, DAY, ctx=CTX)
ok("2: limits never checked: 'Limits not checked for this lorry.', and NEVER the no-record sentence",
   N["limits"] == "not_checked" and N["sentences"][0] == "Limits not checked for this lorry." and N["nothing"] != rp.NOTHING
   and N["nothing"] == rp.NOTHING_PLACES and rp.checked_words(N) is None, str((N["sentences"], N["nothing"])))
OUT42 = line(-0.50, 4.0, lat0=52.10)
put_line("R042", FLAT, "loaded", 0, OUT42, computed="2026-11-25T08:00:00.5+00:00")
put_line("R042", FLAT, "return", 0, list(reversed(OUT42)))
put_hits("R042", [])
N2 = rp.points("R042", FLAT, DAY, ctx=CTX)
ok("2: a line worked out AFTER the last check (a re-route since): not checked, never shown clean",
   N2["limits"] == "not_checked" and N2["nothing"] != rp.NOTHING, str(N2["sentences"]))
put_hits("R042", [], status="error: timed out")
put_line("R042", FLAT, "loaded", 0, OUT42)
ok("2: a check that did not finish: not checked", rp.points("R042", FLAT, DAY, ctx=CTX)["limits"] == "not_checked")
put_hits("R042", [])
E = rp.points("R042", FLAT, DAY, ctx=CTX)
ok("2: nothing stored: the one sentence, word for word",
   E["nothing"] == "Wayscope holds no record of a limit for this lorry, a closure, or a school, hospital or health centre "
   "within 250 m of this route." and E["sentences"] == [] and not any(L["limits"] or L["places"] for L in E["legs"]), str(E))
U = rp.points("R043", FLAT, DAY, ctx=CTX)
ok("2: a route with no line for this lorry: said so, nothing else claimed", not U["routed"] and U["sentences"] == [rp.NOT_ROUTED]
   and U["nothing"] is None and U["legs"] == [])
try:
    rp.points("R999", FLAT, DAY, ctx=CTX)
    ok("2: an unknown route is refused", False)
except LookupError:
    ok("2: an unknown route is refused", True)

# --------------------------------------------------------------------------- 3. the line in use: a diversion, a peak-hours road, a closure
import route_choice  # noqa: E402


def choice(cid, rid, leg, alt, kind, status, starts=None, ends=None, hf=None, ht=None, days=None, ref=None, veh=FLAT):
    db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, hours_from, "
               "hours_to, days, reason_kind, reason_ref, status, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (T, cid, rid, veh, leg, alt, starts, ends, hf, ht, days, kind, ref, status, "auto" if kind == "zone" else "planner"))


db.execute("DELETE FROM route_choice WHERE tenant_id = ?", (T,))
choice("c1", "R012", "loaded", 1, "zone", "in_use", "2027-12-01", "2027-12-31", ref="Z038")
choice("c2", "R012", "return", 1, "zone", "in_use", "2027-12-01", "2027-12-31", ref="Z038")
put_line("R040", FLAT, "loaded", 2, line(-0.50, 6.5, lat0=52.31))
choice("c3", "R040", "loaded", 2, "peak", "in_use", hf="16:00", ht="19:00", days="1111100")
choice("c4", "R041", "loaded", 0, "zone", "needs_route", "2026-11-01", "2026-12-31", ref="Z003")
choice("c5", "R041", "return", 0, "zone", "needs_route", "2026-11-01", "2026-12-31", ref="Z003")
route_choice._MEMO.clear()
D_IN = "2027-12-08"
CTXD = rp.Context(D_IN)
CTXD.all_options = True
Dv = rp.points("R012", FLAT, D_IN, ctx=CTXD)
ok("3: a diversion in force that day: one line for the route, its end date and its page on the route sheet",
   [c["text"] for c in Dv["closures"]] == ["Diversion in force until 31 Dec 2027: route sheet, page 2"], str(Dv["closures"]))
ok("3: ...the points follow the diversion's line: its own limit back, not Kettering Road; its school; not the main line's",
   Dv["alts"] == {"loaded": 1, "return": 1} and [i["text"].split(" · ")[1] for i in Dv["legs"][1]["limits"]] == ["Diversion Lane"]
   and [i["text"] for i in Dv["legs"][0]["places"]] == ["Diversion Primary"], str((Dv["alts"], Dv["legs"][1]["limits"], Dv["legs"][0]["places"])))
CTXD2 = rp.Context(D_IN)
CTXD2.all_options = False
Dv2 = rp.points("R012", FLAT, D_IN, ctx=CTXD2)
ok("3: ...places not fetched along the diversion: said so, none listed, never 'no record'",
   rp.PLACES_NOT_FETCHED in Dv2["sentences"] and not any(L["places"] for L in Dv2["legs"]) and Dv2["nothing"] is None)
Db = rp.points("R012", FLAT, "2027-11-30", ctx=rp.Context("2027-11-30"))
ok("3: the day before the diversion: the main line and NOTHING about the planned closure",
   Db["closures"] == [] and Db["alts"] == {"loaded": 0, "return": 0} and [i["text"].split(" · ")[1] for i in Db["legs"][1]["limits"]][0] == "Kettering Road")
CTX3 = rp.Context(DAY)          # the choice rows are read when a Context is made
Pk = rp.points("R040", FLAT, DAY, ctx=CTX3)
ok("3: a peak-hours road in use on a weekday: its hours and its page; one leg only says which",
   [c["text"] for c in Pk["closures"]] == ["16:00 to 19:00: the peak-hours road, route sheet, page 2 (going loaded)"], str(Pk["closures"]))
ok("3: ...the day's points stay on the main line (the peak road is for those hours only)", Pk["alts"] == {"loaded": 0, "return": 0})
ok("3: ...not on a Saturday", rp.points("R040", FLAT, "2026-11-28", ctx=rp.Context("2026-11-28"))["closures"] == [])
Cl = rp.points("R041", FLAT, DAY, ctx=CTX3)
ok("3: a closure in force with no diversion stored: said once for both ways, with the zone's name",
   [c["text"] for c in Cl["closures"]] == ["Closure in force until 31 Dec 2026 · A47 at the new Tilton junction: HGV diversion while the "
                                           "junction is built: no diversion stored"] and Cl["nothing"] is None, str(Cl["closures"]))
# the Route sheet's first page (no day): every page named with its dates
R0 = rp.points("R012", FLAT, ctx=rp.Context())
ok("3: the Route sheet's first page: the main line, every diversion page named by its dates",
   [c["text"] for c in R0["closures"]] == ["Diversion 1–31 Dec 2027: page 2"] and R0["alts"] == {"loaded": 0, "return": 0}, str(R0["closures"]))
ok("3: ...a peak-hours page by its weekday hours", [c["text"] for c in rp.points("R040", FLAT, ctx=rp.Context())["closures"]]
   == ["Weekdays 16:00 to 19:00: the peak-hours road going loaded, page 2"])
ok("3: ...the closure with no diversion, by its dates", [c["text"] for c in rp.points("R041", FLAT, ctx=rp.Context())["closures"]]
   == ["Closure 1 Nov – 31 Dec 2026 · A47 at the new Tilton junction: HGV diversion while the junction is built: no diversion stored"])
# a Route sheet's diversion page: the alts given
Rd = rp.points("R012", FLAT, alts={"loaded": 1, "return": 1}, ctx=CTXD)
ok("3: a diversion page's block: that page's lines, no closure line of its own", Rd["alts"] == {"loaded": 1, "return": 1} and Rd["closures"] == [])
import route_sheet  # noqa: E402
S12 = route_sheet.sheet("R012", vehicle=FLAT)
S40 = route_sheet.sheet("R040", vehicle=FLAT)
ok("3: the pages after the first are route_sheet.sheet's own, in its order",
   [(p["kind"], p["when"]) for p in rp.sheet_pages("R012", FLAT)] == [("diversion", d["when"]) for d in S12["diversions"]]
   and len(rp.sheet_pages("R040", FLAT)) == len(S40["diversions"]) == 1 and S40["diversions"][0].get("kind") == "busy",
   str((rp.sheet_pages("R012", FLAT), [d["when"] for d in S12["diversions"]])))

# --------------------------------------------------------------------------- 4. a point two routes share, once
OUT44 = line(LON_A, 2.0)
put_line("R044", FLAT, "loaded", 0, OUT44); put_line("R044", FLAT, "return", 0, list(reversed(OUT44)))
put_hits("R044", [hit("loaded", "at_limit", name="Melton Road", ref="B6047", anchor=P(LON_A, 1.9), signed="13'0\"")])
blocks = [rp.cut(rp.points("R012", FLAT, DAY, ctx=CTX)), rp.cut(rp.points("R044", FLAT, DAY, ctx=CTX))]
rp.drop_shared(blocks)
b2 = blocks[1]["legs"]
ok("4: the second route's shared limit and shared places are not printed again; what it left out is counted",
   b2[0]["limits"] == [] and not any("St Lukes" in i["text"] for L in b2 for i in L["places"]) and b2[0]["shared"] >= 2,
   str([(L["limits"], [i["text"] for i in L["places"]], L["shared"]) for L in b2]))
ok("4: ...the first route keeps all of its own", blocks[0]["legs"][0]["limits"] and blocks[0]["legs"][0]["places"])
ok("4: the shared words", rp.shared_words(3, "R012") == "3 more shown under R012 above" and rp.shared_words(0, "R012") == "")
ok("4: ...the second route's leg names the route it was printed under", b2[0]["shared_from"] == ["R012"], str(b2[0].get("shared_from")))
ok("4: ...printed under several routes: no route named", rp.shared_words(5, ["R012", "R044"]) == "5 more shown above"
   and rp.shared_words(2, ["R044"]) == "2 more shown under R044 above")
ok("4: a block whose every limit was printed above loses the at-limit sentence (nothing 'below' is left)",
   blocks[1]["sentences"] == [] and blocks[0]["sentences"] == A["sentences"], str(blocks[1]["sentences"]))

# --------------------------------------------------------------------------- 5. every demo route, stand-in lines: no banned word
import math  # noqa: E402
locs = {l["id"]: l for l in db.query("SELECT id, lat, lon FROM locations WHERE tenant_id = ?", (T,))}
routes = db.query("SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ? ORDER BY id", (T,))
n_feat = 0
for r in routes:
    o, d = locs.get(r["origin_id"]), locs.get(r["dest_id"])
    if not (o and d and o.get("lat") and d.get("lat")):
        continue
    a, b = (float(o["lon"]), float(o["lat"])), (float(d["lon"]), float(d["lat"]))
    steps = max(2, int(rp._hav_m(a, b) // 150))
    ln = [[a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps] for i in range(steps + 1)]
    put_line(r["id"], TIP, "loaded", 0, ln); put_line(r["id"], TIP, "return", 0, list(reversed(ln)))
    k = int(r["id"][1:])
    for j in range(k % 7):
        q = ln[(j * 37 + k) % len(ln)]
        feature(f"z{k}-{j}", ("schools", "hospitals", "health")[j % 3], [q[0] + 0.0005, q[1] + 0.0005],
                None if j % 4 == 3 else f"Place {k}-{j}")
        n_feat += 1
    put_hits(r["id"], [hit("loaded", "at_limit", name=f"Road {k}", anchor=ln[len(ln) // 2], veh=TIP)] if k % 3 == 0 else [])
CTXA = rp.Context(DAY)
ALL = [rp.points(r["id"], TIP, DAY, ctx=CTXA) for r in routes]
ALL = [x for x in ALL if x["routed"]]
ok("5: every demo route has a stand-in line and a block", len(ALL) == len(routes) == 50, str(len(ALL)))
BANNED_RE = re.compile(r"\b(" + "|".join(rp.BANNED) + r")\w*", re.I)
bad = [(x["route_id"], w) for x in ALL + [A, B, N, E, Dv, Cl, R0] for w in rp.all_words(x) if BANNED_RE.search(w)]
ok("5: no block says 'safe', 'clear', 'dangerous', a collision, an accident or a risk", not bad, str(bad[:3]))
ok("5: every routed block ends with the foot and carries the gate line", all(x["foot"] == rp.FOOT and x["gate"] for x in ALL))
longest = max(ALL + [A, Dv], key=lambda x: len(rp.all_words(x)))
print(f"longest block (stand-in lines): {longest['route_id']}, {len(rp.all_words(longest))} lines whole, "
      f"{len(rp.all_words(rp.cut(longest)))} cut")
ok("5: the cut of every block keeps at most three place lines each way", all(len(L["places"]) <= 3 for x in ALL for L in rp.cut(x)["legs"]))

# --------------------------------------------------------------------------- 6. reads only (source)
SRC = read("backend/route_points.py")
code = re.sub(r'""".*?"""', "", SRC, flags=re.S)
ok("6: route_points fetches nothing, draws no map, writes nothing",
   not re.search(r"urlopen|requests\.|basemap|httpx|db\.execute|INSERT |UPDATE |DELETE ", code))
ok("6: no collision count is read", "collision_records" not in code and "count_on_lines" not in code)
ok("6: places come from the grid's cells, never every place for every route", "self.grid.get((gx, gy)" in code)


print(f"test_route_points: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
