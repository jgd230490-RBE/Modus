"""
The pieces of a route's options and what lies along a line, by ONE rule on the server (27 Nov 2026, branch
claude/route-pieces; the route lines plan's Q6, Q8, Q12 and Q16, John's "Yes, all as recommended" of 26 Nov).
route_pieces.py holds the rule; chainage.py the server's one distance-along walk; GET /api/routes/{id}/along (staff) and
GET /api/public/route-pieces (the public map's share) serve it. Nothing a person sees changes: no page reads them yet.

WHAT IS ASSERTED (each would fail on the code before this branch, or on a fault found while it was built):
  1. ONE distance-along walk: chainage.project / chainage / point_at / line_between / line_length_m are the functions
     collisions.py had (its old names are aliases, its own bodies gone); route_analysis_doc and traffic call chainage.*;
     chainage.Grid.nearest gives what chainage.project gives within its reach (the same metres, the first segment on a
     tie) and nothing beyond it;
  2. the rule on drawn lines: the same line has no piece; a detour is one piece with its stretch on BOTH lines, where it
     leaves and rejoins and its extra length; a short cut (the base goes round a spur the option skips) is a piece with
     a zero-length option side; a road 15 m beside is the same road; a 40 m slip road for 80 m is left out; a way round
     that crosses the usual road is one piece (two with JOIN 0); a base that passes the same place twice is matched
     where the walk has got to (the fault of the first build: R018's way back read 68 km of difference on a 41.5 km
     line); a stretch only "off" in order, on the other line's road elsewhere, does not count; every threshold in one
     top block;
  3. the stored options of a leg against the line in use: on a day inside a diversion's dates the diversion is the line
     in use and option 0 is compared against it; outside, option 0 is; an alternative, a dated diversion and a
     busy-hours road are named by what puts them on the road, with their dates or hours; an offer not accepted is not;
  4. what lies along a line: ONE list in metres from A, in order: the limits the lorry is at or over (its value,
     "allowed"), none it is within (counted aside), schools, hospitals and health centres within 250 m with their
     distance off (a bus stop and a place 400 m off left out), a cycle-route crossing, the collision evidence's numbered
     stretches cut on this line, a haul-road stretch, the diversion's pieces in its dates (and, while it is in use,
     where the line in use leaves the usual road); the gaps the data cannot fill are named;
  5. the public share: only limits (an Approved lorry, exceeds or allowed) and haul-road stretches as items, every
     option against option 0 on any day; no place, cycle route or collision stretch;
  6. the reads: the staff read after _gate_arrivals_build, any staff login, a bad leg or day is 400, a team code's
     other team's route is 404, kept through _staff_json; the public read in a heavy slot, kept by route and leg; no
     BOOLEAN compared with 1; no frontend or map file names route_pieces; the pages keep their own rules (divOffPieces 25 m,
     olOffPieces 30 m and 150 m: a later visible task reverses these two pins when it moves them).

WHAT THIS DOES NOT PROVE: live's lines (the comparison over live's lines of 24 Nov is in the note, run on a copy, not
here); Postgres; the reads through a real server (http_smoke and smoke_reviewer_wall sweep every /api route).

Run:  python backend/tests/test_route_pieces.py
"""
import datetime
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
sys.path.insert(0, HERE)

# ---- stubs, as test_route_best.py --------------------------------------------
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


class _Response:
    def __init__(self, content=None, media_type=None, **k):
        self.body, self.media_type = content, media_type


_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_pieces_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import limits  # noqa: E402
import collisions  # noqa: E402
import chainage  # noqa: E402
import route_analysis_doc  # noqa: E402
import traffic  # noqa: E402
import route_choice  # noqa: E402
import route_pieces as RP  # noqa: E402

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


def near(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


# =========================================================================== #
#  1. One distance-along walk                                                  #
# =========================================================================== #
_col = read("backend/collisions.py")
_rad = read("backend/route_analysis_doc.py")
_tra = read("backend/traffic.py")
ok("⭐ 1. collisions' distance-along functions are chainage's own (aliases), their bodies moved, not copied",
   collisions._project is chainage.project and collisions._chainage is chainage.chainage
   and collisions.point_at is chainage.point_at and collisions.line_between is chainage.line_between
   and collisions.line_length_m is chainage.line_length_m
   and "def _project(" not in _col and "def _chainage(" not in _col and "def point_at(" not in _col)
ok("⭐ 1. the Route analysis and the traffic counts call chainage.* (no collisions._project / _chainage left)",
   "collisions._project(" not in _rad and "collisions._chainage(" not in _rad and "collisions.point_at(" not in _rad
   and "collisions.line_length_m(" not in _rad and "chainage.project(index, loaded" in _rad
   and "chainage.chainage(index, loaded" in _rad and "cl._project(" not in _tra and "chainage.project(index, line" in _tra)
ok("1. route_pieces walks through chainage only (no walk of its own beside chainage's)",
   "def project(" not in read("backend/route_pieces.py") and "chainage.vertex_chainage(" in read("backend/route_pieces.py"))

PJ = chainage.Proj(52.5)
X0, Y0 = -1.0, 52.5


def P(x, y):
    """A point x metres east and y metres north of (X0, Y0), on PJ."""
    return [X0 + x / PJ.kx, Y0 + y / PJ.ky]


def L(*xy, step=50.0):
    """A line through metre points, with vertices every `step` m (a stored line has many)."""
    out = []
    for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) // step))
        for k in range(n):
            out.append(P(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out.append(P(*xy[-1]))
    return out


SQ = L((0, 0), (1000, 0), (1000, 800), (0, 800))
_g = chainage.Grid(PJ, SQ, 120)
_probe = [P(500, 30), P(1030, 400), P(1000, 0), P(600, 760), P(-50, 10), P(500, 400)]
_same = all(near(_g.nearest(PJ._xy(p))[1], chainage.project(PJ, SQ, p)[1], 1e-6)
            and near(_g.nearest(PJ._xy(p))[0], chainage.project(PJ, SQ, p)[0], 1e-6) for p in _probe[:5])
ok("⭐ 1. chainage.Grid.nearest = chainage.project within its reach (metres off and along, a corner included)", _same)
ok("1. ...and nothing beyond its reach (a point 400 m from every side)",
   _g.nearest(PJ._xy(_probe[5])) == (float("inf"), None) and _g.dist(PJ._xy(_probe[5])) == float("inf"))
ok("1. vertex_chainage is the walk's own metres (2,600 m round three sides)",
   near(chainage.vertex_chainage(PJ, SQ)[-1], chainage.line_length_m(PJ, SQ), 1e-6)
   and near(chainage.line_length_m(PJ, SQ), 2800, 1.0))

# =========================================================================== #
#  2. The rule on drawn lines                                                  #
# =========================================================================== #
BASE = L((0, 0), (3000, 0))
ok("2. the same line: no piece, 'same'", RP.pieces(PJ, BASE, BASE) == [] and RP.compare(PJ, BASE, BASE)["same"] is True)
DET = L((0, 0), (1000, 0), (1000, 300), (2000, 300), (2000, 0), (3000, 0))
ps = RP.pieces(PJ, DET, BASE)
p = ps[0] if ps else {}
ok("⭐ 2. a detour is ONE piece named on BOTH lines: the option 1,000 to 2,600 m, the base 1,000 to 2,000 m",
   len(ps) == 1 and near(p["option"]["from_m"], 1000, 30) and near(p["option"]["to_m"], 2600, 30)
   and near(p["base"]["from_m"], 1000, 30) and near(p["base"]["to_m"], 2000, 30), str(ps))
ok("2. ...600 m longer, it gets well clear of the base, and leaves / rejoins at the two junctions",
   near(p.get("extra_m"), 600, 60) and p.get("apart_m", 0) > RP.CLEAR_M
   and chainage.project(PJ, BASE, p["leaves"])[0] <= RP.NEAR_M + 1 and chainage.project(PJ, BASE, p["rejoins"])[0] <= RP.NEAR_M + 1
   and near(chainage.chainage(PJ, BASE, p["leaves"]), 1000, 30) and near(chainage.chainage(PJ, BASE, p["rejoins"]), 2000, 30))
c = RP.compare(PJ, DET, BASE)
ok("2. compare(): where it first leaves and last rejoins on both lines, the metres that differ, the extra length",
   c["same"] is False and near(c["leaves"]["base_m"], 1000, 30) and near(c["rejoins"]["option_m"], 2600, 30)
   and near(c["differs_m"]["option"], 1600, 60) and near(c["differs_m"]["base"], 1000, 60) and near(c["extra_m"], 600, 1))
ok("2. each side carries its 'off' runs (what a map draws: off the other line anywhere)",
   len(p["option"]["off"]) == 1 and len(p["base"]["off"]) == 1 and near(p["base"]["off"][0][0], 1000, 30))
SPUR = L((0, 0), (1000, 0), (1000, 300), (1000, 0), (3000, 0))
ps = RP.pieces(PJ, BASE, SPUR)
ok("⭐ 2. a short cut: the base goes up a 300 m spur and back that the option skips: ONE piece, the option side ~0 m",
   len(ps) == 1 and ps[0]["option"]["length_m"] <= 30 and near(ps[0]["base"]["length_m"], 600, 40)
   and near(ps[0]["base"]["from_m"], 1000, 30) and near(ps[0]["extra_m"], -600, 60), str(ps))
ok("2. a road 15 m beside the whole way is the same road", RP.pieces(PJ, L((0, 15), (3000, 15)), BASE) == [])
SLIP = L((0, 0), (1000, 0), (1000, 40), (1040, 40), (1040, 0), (3000, 0), step=10)
_all = RP.pieces(PJ, SLIP, BASE, keep_all=True)
ok("⭐ 2. a lay-by 40 m out for 40 m is found but does not count (under MIN_RUN on both lines, never CLEAR away)",
   RP.pieces(PJ, SLIP, BASE) == [] and len(_all) == 1 and _all[0]["counts"] is False
   and _all[0]["apart_m"] <= RP.CLEAR_M)
CROSS = L((0, 0), (1000, 0), (1000, 300), (1500, 300), (1500, -300), (2000, -300), (2000, 0), (3000, 0), step=10)
ok("⭐ 2. a way round that crosses the usual road is ONE piece (the browser's rules make two); JOIN 0 makes two",
   len(RP.pieces(PJ, CROSS, BASE)) == 1 and len(RP.pieces(PJ, CROSS, BASE, join=0)) == 2,
   str([len(RP.pieces(PJ, CROSS, BASE)), len(RP.pieces(PJ, CROSS, BASE, join=0))]))
TWICE = L((0, 0), (1000, 0), (0, 0), (0, 2000))
TWICE_OPT = L((0, 0), (1000, 0), (0, 0), (500, 500), (0, 2000))
ps = RP.pieces(PJ, TWICE_OPT, TWICE)
ok("⭐ 2. a base that passes the same road twice is matched where the walk has got to: the piece starts at 2,000 m on "
   "both lines, not on the first pass (the first build's fault)",
   len(ps) == 1 and near(ps[0]["base"]["from_m"], 2000, 40) and near(ps[0]["option"]["from_m"], 2000, 40)
   and ps[0]["base"]["length_m"] < 2200, str(ps))
ok("2. step 6: a piece with no 'off' run on either side (only the order differs) never counts",
   RP._counts({"option": {"length_m": 500, "off": []}, "base": {"length_m": 500, "off": []}, "apart_m": 0}) is False
   and RP._counts({"option": {"length_m": 50, "off": [[0, 50]]}, "base": {"length_m": 0, "off": []}, "apart_m": 70}) is True
   and RP._counts({"option": {"length_m": 50, "off": [[0, 50]]}, "base": {"length_m": 0, "off": []}, "apart_m": 40}) is False
   and RP._counts({"option": {"length_m": 120, "off": [[0, 120]]}, "base": {"length_m": 0, "off": []}, "apart_m": 30}) is True)
_src = read("backend/route_pieces.py")
_top = _src[:_src.index("class Context")]
ok("2. every threshold is named once in the top block, with the public map's haul-road distance",
   all(f"\n{n} = " in _top for n in ("NEAR_M", "STEP_M", "MIN_RUN_M", "CLEAR_M", "JOIN_M", "HAUL_NEAR_M"))
   and (RP.NEAR_M, RP.MIN_RUN_M, RP.CLEAR_M, RP.JOIN_M, RP.HAUL_NEAR_M) == (25.0, 100.0, 60.0, 50.0, 9.0)
   and "const HAUL_NEAR_M = 9;" in read("map/index.html"))
ok("2. no router call and no outside fetch in the module",
   not any(w in _src for w in ("here_routing.route", "requests.", "urllib", "httpx", "fetch_guard", "basemap.fetch")))

# =========================================================================== #
#  Fixture: one route with a main line, an alternative and a dated diversion   #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant(); db.init_users_db()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()
T = db.current_tenant()
ART = network.DEFAULT_PROFILE
DAY_IN = datetime.date(2027, 2, 2)       # a Tuesday inside the diversion's dates
DAY_OUT = datetime.date(2027, 6, 1)      # a Tuesday after them
MAIN = L((0, 0), (3000, 0))
ALT1 = L((0, 0), (1000, 0), (1000, 300), (2000, 300), (2000, 0), (3000, 0))
DIV = L((0, 0), (1200, 0), (1200, -400), (2200, -400), (2200, 0), (3000, 0))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'A', 'Pit', ?, ?, 'Quarry')",
           (T, MAIN[0][1], MAIN[0][0]))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'B', 'Yard', ?, ?, 'Compound')",
           (T, MAIN[-1][1], MAIN[-1][0]))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R1', 'A', 'B', "
           "'Small aggregate', 'IPT1')", (T,))
for alt, line in ((0, MAIN), (1, ALT1), (10, DIV)):
    network._upsert_geom("R1", ART, json.dumps(line), 3.0, 0.1, None, leg="loaded", alt_index=alt)
    network._upsert_geom("R1", ART, json.dumps(list(reversed(line))), 3.0, 0.1, None, leg="return", alt_index=alt)


def choice(cid, alt, kind, status, **kw):
    cols = {"tenant_id": T, "id": cid, "route_id": "R1", "vehicle_profile": ART, "leg": "loaded", "alt_index": alt,
            "reason_kind": kind, "status": status, "source": "auto" if kind == "zone" else "planner"}
    cols.update(kw)
    db.execute(f"INSERT INTO route_choice ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", tuple(cols.values()))


choice("c1", 10, "zone", "in_use", starts_on="2027-01-01", ends_on="2027-03-31", reason_ref="Z9")
choice("c2", 1, "peak", "in_use", hours_from="16:00", hours_to="19:00", days="1111100", reason_ref="16:00-19:00")
choice("c3", 1, "peak", "offered", hours_from="07:00", hours_to="09:00", days="1111100")


def hit(ext, alt, verdict, x, kind="weight", value=7.5, name="Mill Road", ref="B1"):
    h = {"vehicle_profile": ART, "leg": "loaded", "source": "osm", "ext_id": ext, "kind": kind, "limit": value,
         "unit": "t", "name": name, "ref": ref, "exceptions": "Except for access" if verdict == "allowed" else None,
         "point": False, "along_m": 40.0, "verdict": verdict, "anchor": P(x, 0)}
    if alt:
        h["alt_index"] = alt
    return h


HITS = [hit("w1", 0, "exceeds", 500), hit("w2", 0, "within", 700), hit("w3", 0, "allowed", 2800, name="Yard Lane"),
        hit("h1", 10, "at_limit", 2500, kind="height", value=4.0, name="Rail bridge"), hit("w4", 10, "unknown", 100)]
db.execute("UPDATE routes SET limits_hits = ?, limits_checked_at = '2026-11-24T14:56:24+00:00', limits_status = 'checked' "
           "WHERE tenant_id = ? AND id = 'R1'", (json.dumps(HITS), T))


def feat(fid, kind, name, x, y):
    db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, "
               "geometry_json, dist_m, fetched_at) VALUES (?, ?, ?, 'test', ?, ?, NULL, ?, 0, '2026-11-20')",
               (T, fid, kind, fid, name, json.dumps({"type": "Point", "coordinates": P(x, y)})))


feat("s1", "schools", "Langham Primary", 600, 100)        # 100 m off the main line at 600 m
feat("s2", "health", "Far Clinic", 800, 400)               # 400 m off: left out
feat("s3", "bus_stops", "Mill Lane stop", 900, 10)         # not a deciding kind: left out
feat("s4", "hospitals", "Wolds Hospital", 1700, -460)      # beside the diversion only
db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
           "dist_m, fetched_at) VALUES (?, 'c1', 'cycle', 'test', 'c1', 'NCN 48', NULL, ?, 0, '2026-11-20')",
           (T, json.dumps({"type": "LineString", "coordinates": [P(2700, -300), P(2700, 300)]})))
zones.create_zone("Pit access road", {"type": "LineString", "coordinates": [P(0, 0), P(60, 0)]}, kind="haul_road",
                  affects_routing=True)


def rec(cid, x, y, road):
    return {"collision_id": cid, "lon": P(x, y)[0], "lat": P(x, y)[1], "road": road, "road2": None, "speed_limit": 30,
            "routes": {"R1": 3.0}, "severity": 3}


RECS = [rec(f"a{i}", 100 + 100 * i, 2, "A6") for i in range(5)] + [rec(f"b{i}", 1300 + 100 * i, -398, "B676") for i in range(5)]


def ctx_for(day, route_ids=("R1",)):
    x = RP.Context(day, list(route_ids))
    x.__dict__["records"] = list(RECS)        # the collision history, as stored records (collisions.records' shape)
    return x


# =========================================================================== #
#  3. The stored options of a leg, against the line in use                     #
# =========================================================================== #
f_in = RP.for_leg("R1", ART, "loaded", DAY_IN)
f_out = RP.for_leg("R1", ART, "loaded", DAY_OUT)
by = lambda f: {o["alt"]: o for o in f["options"]}
ok("⭐ 3. inside the diversion's dates the diversion is the line in use, and the main route is compared against it",
   f_in["in_use"]["alt"] == 10 and f_in["in_use"]["kind"] == "diversion" and set(by(f_in)) == {0, 1}
   and by(f_in)[0]["kind"] == "main route" and len(by(f_in)[0]["pieces"]) == 1
   and near(by(f_in)[0]["pieces"][0]["base"]["from_m"], 1200, 30), str(f_in["in_use"]))
ok("⭐ 3. after the dates the main route is in use: the diversion with its dates and zone, the alternative named by its "
   "accepted busy hours only (an offer is not a use)",
   f_out["in_use"]["alt"] == 0 and by(f_out)[10]["kind"] == "diversion"
   and by(f_out)[10]["uses"] == [{"kind": "diversion", "status": "in_use", "zones": ["Z9"], "from": "2027-01-01",
                                  "to": "2027-03-31"}]
   and by(f_out)[1]["kind"] == "busy_hours" and len(by(f_out)[1]["uses"]) == 1
   and by(f_out)[1]["uses"][0]["hours_from"] == "16:00" and by(f_out)[1]["uses"][0]["days"] == "1111100",
   str([by(f_out)[1]["uses"], by(f_out)[10]["uses"]]))
ok("3. the diversion against the main line: leaves at 1,200 m, rejoins at 2,200 m, 800 m longer",
   near(by(f_out)[10]["leaves"]["base_m"], 1200, 30) and near(by(f_out)[10]["rejoins"]["base_m"], 2200, 30)
   and near(by(f_out)[10]["extra_m"], 800, 5))
ok("3. base_alt pins the base (the public map always draws option 0)",
   RP.for_leg("R1", ART, "loaded", DAY_IN, base_alt=0)["in_use"]["alt"] == 0)
ok("3. a leg with no stored line answers empty, never fails", RP.for_leg("R1", ART, "sideways", DAY_IN)["options"] == [])

# =========================================================================== #
#  4. What lies along a line                                                   #
# =========================================================================== #
a_out = RP.along("R1", ART, "loaded", DAY_OUT, ctx=ctx_for(DAY_OUT))
whats = [i["what"] for i in a_out["items"]]
ms = [i["at_m"] for i in a_out["items"]]
ok("⭐ 4. ONE list in metres from A, in order", ms == sorted(ms) and a_out["alt"] == 0 and near(a_out["length_m"], 3000, 2))
lims = [i for i in a_out["items"] if i["what"] == "limit"]
ok("⭐ 4. the limits the lorry is at or over on the line in use, placed by their anchor, with value and 'allowed'; the one "
   "it is within is counted aside, the diversion's own are not on the main line",
   [(round(i["at_m"]), i["verdict"], i["allowed"], i["value"]) for i in lims] == [(500, "exceeds", False, "7.5t"),
                                                                                (2800, "allowed", True, "7.5t")]
   and a_out["limits"]["left_out"] == {"within": 1} and lims[0]["road"] == "Mill Road" and lims[0]["ref"] == "B1",
   str([(i["at_m"], i["verdict"], i["value"]) for i in lims]) + str(a_out["limits"]))
pl = [i for i in a_out["items"] if i["what"] == "place"]
ok("⭐ 4. schools, hospitals and health centres within 250 m, with their distance off; a bus stop and a clinic 400 m off "
   "are left out", [(i["name"], round(i["at_m"]), i["off_m"]) for i in pl] == [("Langham Primary", 600, 100)], str(pl))
cy = [i for i in a_out["items"] if i["what"] == "cycle"]
ok("4. a cycle route crossing at 2,700 m", len(cy) == 1 and near(cy[0]["at_m"], 2700, 15) and cy[0]["name"] == "NCN 48")
st = [i for i in a_out["items"] if i["what"] == "stretch"]
ok("⭐ 4. the collision evidence's numbered stretches, cut on THIS line by collisions.stretches (the main line has only "
   "the A6's five; the B676's lie on the diversion)",
   [(s["no"], s["road"], s["collisions"]) for s in st] == [(1, "A6", 5)] and st[0]["at_m"] == 0.0
   and near(st[0]["to_m"], 3000, 2), str(st))
hl = [i for i in a_out["items"] if i["what"] == "haul_road"]
ok("4. the haul-road stretch at the start (the public map's 9 m rule, on the line's own vertices)",
   len(hl) == 1 and hl[0]["at_m"] == 0.0 and near(hl[0]["to_m"], 50, 1) and hl[0]["name"] == "Pit access road", str(hl))
dv = [i for i in a_out["items"] if i["what"] == "diversion"]
bh = [i for i in a_out["items"] if i["what"] == "busy_hours"]
ok("⭐ 4. the diversion's piece in its dates and the busy-hours road's with its hours, on the line in use",
   len(dv) == 1 and dv[0]["from"] == "2027-01-01" and dv[0]["to"] == "2027-03-31" and dv[0]["in_use"] is False
   and near(dv[0]["at_m"], 1200, 30) and near(dv[0]["to_m"], 2200, 30) and near(dv[0]["extra_m"], 800, 60)
   and len(bh) == 1 and bh[0]["hours_from"] == "16:00" and bh[0]["hours_to"] == "19:00" and near(bh[0]["at_m"], 1000, 30),
   str(dv) + str(bh))
a_in = RP.along("R1", ART, "loaded", DAY_IN, ctx=ctx_for(DAY_IN))
dv = [i for i in a_in["items"] if i["what"] == "diversion"]
lim_in = [i for i in a_in["items"] if i["what"] == "limit"]
st_in = [i for i in a_in["items"] if i["what"] == "stretch"]
ok("⭐ 4. while the diversion is in use the list is the diversion's: its own limit (at the limit), the hospital beside it, "
   "its stretches (A6 then B676), and where it leaves the usual road (in_use, 800 m longer)",
   a_in["alt"] == 10 and [(i["verdict"], i["value"]) for i in lim_in] == [("at_limit", "4.0m")]
   and a_in["limits"]["left_out"] == {"unknown": 1}
   and [i["name"] for i in a_in["items"] if i["what"] == "place"] == ["Langham Primary", "Wolds Hospital"]
   and [s["road"] for s in st_in] == ["A6", "B676"]
   and len(dv) == 1 and dv[0]["in_use"] is True and dv[0]["alt"] == 10 and near(dv[0]["at_m"], 1200, 30)
   and near(dv[0]["extra_m"], 800, 60), str([a_in["limits"], [i for i in a_in["items"] if i["what"] == "place"], dv]))
ok("4. the gaps the stored data cannot fill are named (a road's number along the line, a junction's name)",
   set(RP.GAPS) >= {"road_number", "junction_name"} and a_out["gaps"] is RP.GAPS)
ok("4. the list carries the pieces it was cut from", a_out["pieces"]["in_use"]["alt"] == 0 and len(a_out["pieces"]["options"]) == 2)

# =========================================================================== #
#  5. The public share                                                         #
# =========================================================================== #
pub = RP.public("R1", "loaded", day=DAY_IN)
ok("⭐ 5. the public share carries no place, cycle route or collision stretch; no limit while no Approved lorry is planned",
   {i["what"] for i in pub["items"]} == {"haul_road"} and set(RP.PUBLIC_WHATS) == {"limit", "haul_road"})
ok("⭐ 5. every option against option 0 (the public map's route), on any day", {o["alt"] for o in pub["options"]} == {1, 10}
   and next(o for o in pub["options"] if o["alt"] == 10)["uses"][0]["from"] == "2027-01-01")
ok("⭐ 5. a use carries only what map-data already sends: a busy-hours road's hours, never its days",
   next(o for o in pub["options"] if o["alt"] == 1)["uses"] == [{"kind": "busy_hours", "zones": [], "hours_from": "16:00",
                                                                 "hours_to": "19:00"}]
   and all(set(u) <= set(RP.PUBLIC_USE_KEYS) for o in pub["options"] for u in o["uses"])
   and '"from": r.get("hours_from"), "to": r.get("hours_to")' in read("backend/network.py")
   and 'r.get("days")' not in read("backend/network.py")[read("backend/network.py").index("def _busy_features("):
                                                            read("backend/network.py").index("def route_alternatives_geojson(")],
   str([o["uses"] for o in pub["options"]]))
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, quantity, unit, vehicle_type, status) "
           "VALUES (?, 'f1', 'R1', 14, 100, 't', ?, 'Approved')", (T, ART))
pub = RP.public("R1", "loaded", day=DAY_IN)
pl = [i for i in pub["items"] if i["what"] == "limit"]
ok("⭐ 5. with an Approved lorry, the limits the public map's own collection lists (exceeds, allowed), never at_limit or "
   "within, and no metres off or run length",
   [(i["verdict"], round(i["at_m"])) for i in pl] == [("exceeds", 500), ("allowed", 2800)]
   and all("off_m" not in i and "run_m" not in i for i in pub["items"]), str(pl))
_fc = limits.feature_collection()
ok("5. (the public collection lists exceeds and allowed for an Approved lorry: limits.feature_collection's own rule)",
   'h.get("verdict") not in ("exceeds", "allowed")' in read("backend/limits.py"))

# =========================================================================== #
#  6. The reads                                                                #
# =========================================================================== #
_m = read("backend/main.py")
ga = _m.index("def _gate_arrivals_build(")
ok("⭐ 6. both reads come after _gate_arrivals_build", ga < _m.index('@app.get("/api/routes/{route_id}/along")')
   and ga < _m.index('@app.get("/api/public/route-pieces")'))
_ra = _m[_m.index("def route_along("):_m.index("def public_route_pieces(")]
_pr = _m[_m.index("def public_route_pieces("):]
_pr = _pr[:_pr.index("\n\n\n")]
ok("⭐ 6. the staff read: any staff login, the team check, kept through _staff_json; the public read in a heavy slot, kept",
   "_require_access()" in _ra and "collisions._route_row(route_id, acc)" in _ra and '_staff_json("routes/along"' in _ra
   and 'with _heavy("route-pieces"):' in _pr and "read_cache.cached(" in _pr and "_require_access" not in _pr)
_real_cur = access.current
access.current = lambda: {"role": "admin", "label": "Admin", "ipt": None}
try:
    r = main.route_along("R1", leg="loaded", profile=None, day="2027-06-01")
    ok("6. the staff read answers the along list", r["route"] == "R1" and r["alt"] == 0 and r["items"])
    bad = []
    for kw in ({"leg": "sideways"}, {"day": "tomorrow"}):
        try:
            main.route_along("R1", **dict({"leg": "loaded", "profile": None, "day": None}, **kw))
        except _HTTPException as e:
            bad.append(e.status_code)
    try:
        main.route_along("R9", leg="loaded", profile=None, day=None)
    except _HTTPException as e:
        bad.append(e.status_code)
    try:
        main.route_along("R1", leg="loaded", profile="Unicycle", day=None)
    except _HTTPException as e:
        bad.append(e.status_code)
    ok("6. a bad leg or day is 400; an unknown route or a lorry with no line 404", bad == [400, 400, 404, 404], str(bad))
    access.current = lambda: {"role": "ipt", "label": "Team 2", "ipt": "IPT2"}
    try:
        main.route_along("R1", leg="loaded", profile=None, day=None)
        team = None
    except _HTTPException as e:
        team = e.status_code
    ok("⭐ 6. a team code asking for another team's route gets 404", team == 404, str(team))
    access.current = lambda: None
    try:
        main.route_along("R1", leg="loaded", profile=None, day=None)
        anon = None
    except _HTTPException as e:
        anon = e.status_code
    ok("6. signed out (and so a reviewer, whose access.current() is None): 401", anon == 401, str(anon))
finally:
    access.current = _real_cur
r = main.public_route_pieces("R1", leg="loaded", profile=None)
body = json.loads(r.body)
ok("6. the public read answers JSON bytes with the public share", body["route"] == "R1" and {o["alt"] for o in body["options"]} == {1, 10}
   and r.media_type == "application/json")
try:
    main.public_route_pieces("R1", leg="up", profile=None)
    pb = None
except _HTTPException as e:
    pb = e.status_code
ok("6. the public read refuses a bad leg", pb == 400)
import re  # noqa: E402
_sql = [q for q in re.findall(r'"([^"\n]*)"', _src) if re.search(r"\b(SELECT|WHERE|AND)\b", q)]
ok("6. no BOOLEAN compared with 1 in the new SQL; every read names tenant_id",
   bool(_sql) and not any(re.search(r"=\s*(1|TRUE|true)\b", q) for q in _sql)
   and all("tenant_id = ?" in q for q in re.findall(r'"SELECT[^"]*"', _src)), str(_sql))
_fe, _map = read("frontend/index.html"), read("map/index.html")
ok("⭐ 6. nothing a person sees: no page names the new reads", "route_pieces" not in _fe + _map
   and "/along" not in _fe + _map and "route-pieces" not in _fe + _map)
ok("6. the pages keep their own rules for now (a later visible task reverses these two pins when it moves them): the "
   "public map's divOffPieces at 25 m, the Routes page's olOffPieces at 30 m and 150 m",
   "near_m: 25" in _map and "function divOffPieces(divCoords, mainCoords)" in _map
   and "near: 30, minRun: 150" in _fe and "function olOffPieces(A, B)" in _fe)

remove_scratch_db(db, TMP)
print(f"\ntest_route_pieces: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
