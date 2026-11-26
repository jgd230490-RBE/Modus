"""
The best-option RULE (16 Nov 2026, step 1a, branch claude/route-best-rule). John's decisions of 16 Nov
(notes/session-1116-best-option-check.md §4b to §4h): one answer a route (Suggested / A trade-off / Keep the route in use)
from a rule and fixed sentences, no screen. route_best.py holds it; GET /api/admin/route-options/best runs it on every
route.

WHAT IS ASSERTED (each would fail on a fault the 16 Nov check found):
  1. the pure parts: the collision test, steps, mixing, percentages with a zero or small base, labels;
  2. limits (N1): a limit both lines meet does not rule an option out; one the option ADDS does, with its words and the
     "except for access" note; the plain route answers Suggested on fewer collisions, with the two counts in words;
  3. a route on a dated zone's diversion is compared against the DIVERSION (not option 0), and option 0, which crosses the
     closure, is ruled out;
  4. N5: a shorter but slower option is "A trade-off" at most;
  5. goods-vehicle counts per option (route_best and route_compare);
  6. the gate: cycle and community parts are shown and move nothing while community.status() has no "all_options" (or
     False); with it True a rise from 0 places shows (counts alone, no percentage) and turns the answer into a trade-off;
  7. the collision history (finding 4, narrowed 16 Nov evening): REVERSED: a Make primary moves no line, so it stays
     current and the counts follow the lines to their new numbers (and the audit log is no longer read); a re-route after
     the fetch is "out of date" (a road on it may not have been searched), no collision part counted, nothing suggested;
 10b. (16 Nov evening, the mother session's first live read) collisions counted on each pair's OWN two lines from each
     record's position: an option costed with the main line's way back reads "fewer" when its own road has fewer (R5;
     the count by option number could never); a collision near both legs counts once; and the fixed sentences: no five
     words said twice, "but" once, the time said once, both busy hours in one phrase, a limit on both legs named once;
  8. no limits held = nothing suggested; no alternative = Keep;
  9. the lorry (N2): the type the Approved loads mostly use, among the types with a line;
 10. the three example routes of rule_demo.py (13 Nov) through the same option code, and where the decisions changed them;
 11. words: no "safer", "better", rate, ratio, score, risk or supplier; no "%" on a collision sentence;
 12. the admin read: admin only, a bad day is 400, the table's shape, kept through _staff_json, placed after
     _gate_arrivals_build; no frontend change; "Counts only" still on the Routes page (a later branch takes it off).

WHAT THIS DOES NOT PROVE: live's figures (the rule has not been run on live; local lines are stand-ins, no limits); the
community layer's all-options flag as claude/community-all-options will write it (stubbed here); Postgres.

Run:  python backend/tests/test_route_best.py
"""
import datetime
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

# ---- stubs, verbatim from test_route_compare.py ------------------------------
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

TMP = tempfile.mkdtemp(prefix="wayscope_best_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
os.environ["ADMIN_TOKEN"] = "best-admin-token"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import limits  # noqa: E402
import collisions  # noqa: E402
import community  # noqa: E402
import route_choice  # noqa: E402
import route_compare  # noqa: E402
import route_best as RB  # noqa: E402

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


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant(); db.init_users_db()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  1. The pure parts                                                           #
# =========================================================================== #
ok("⭐ 1. the collision test is the app's own: at least 10 on the side with more, a gap by chance under 1 in 20",
   RB.COLLISIONS_MIN == collisions.OFFER_MIN == 10 and RB.COLLISIONS_P == collisions.OFFER_P == 0.05
   and RB.clearly(23, 8) == 1 and RB.clearly(8, 23) == -1 and RB.clearly(9, 0) == 0 and RB.clearly(12, 10) == 0)
ok("1. a step counts a gap of the threshold or more each way; None stays None",
   (RB.step(-2, 2), RB.step(2, 2), RB.step(1, 2), RB.step(None, 2)) == (1, -1, 0, None))
ok("1. parts mix: one ahead and one behind is mixed; parts not counted are left out; none counted is None",
   (RB.mix([1, -1]), RB.mix([1, 0, None]), RB.mix([0, -1]), RB.mix([None, None]), RB.mix([1, RB.MIXED])) ==
   (RB.MIXED, 1, -1, None, RB.MIXED))
ok("⭐ 1. 4f: a percentage only where the base is 5 or more; a zero base or a small one gives the counts alone",
   RB.pct(3, 0, 5) is None and RB.pct(4, 4, 5) is None and RB.pct(10, 20, 5) == -50 and RB.pct(6, 5, 5) == 20)
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): a line baked round a closure is "Diversion" (it read "Way round")
ok("1. labels: the main route, Alt n, a diversion", (RB.label(0), RB.label(2), RB.label(10), RB.label(11)) ==
   ("The main route", "Alt 2", "Diversion", "Diversion 2") and RB.DIVERSION_LABEL == "Diversion"
   and "Way round" not in __import__("inspect").getsource(RB.label))
_doc = read("backend/route_analysis_doc.py")
ok("⭐ 1. 4d: the deciding places are the Route analysis's named kinds, within 250 m; the other kinds are shown only",
   'NAMED_KINDS = ("schools", "hospitals", "health")' in _doc and RB.DECIDING_KINDS == ("schools", "hospitals", "health")
   and all(route_compare.NEAR_M[k] == RB.PLACES_M == 250 for k in RB.DECIDING_KINDS)
   and set(RB.SHOWN_KINDS) == set(route_compare.KINDS) - set(RB.DECIDING_KINDS))
TH = RB.thresholds()
ok("1. every threshold is named in one place and marked as not set by John",
   TH["set_by_john"] is False and {"time_min", "time_pct", "carbon_pct", "left_turns", "cycle_meets", "beside_km",
                                   "places", "slower_min", "pct_base_min", "collisions_min", "collisions_p"} <= set(TH))
_rb = read("backend/route_best.py")
ok("1. the module says the thresholds are starting values John has not set",
   "STARTING VALUES" in _rb and "John has not set" in _rb)

# =========================================================================== #
#  Fixture                                                                     #
# =========================================================================== #
ART = route_compare.PROFILE
FLAT = "Artic Flatbed (44t)"
T = db.current_tenant()
DAY = datetime.date(2027, 2, 2)              # a Tuesday inside the closure below
FETCHED = "2026-11-02T12:00:00Z"            # after the lines were stored (2026-11-01), before today


def bent(lat, dlat):
    return [[-1.0, lat], [-0.95, lat + dlat], [-0.9, lat]]


def add_route(rid, lat, opts):
    o, d = f"L{rid}a", f"L{rid}b"
    db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, -1.0, 'Quarry')",
               (T, o, f"Pit {rid}", lat))
    db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, -0.9, 'Compound')",
               (T, d, f"Yard {rid}", lat))
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, "
               "'Small aggregate', 'IPT1')", (T, rid, o, d))
    for alt, (line, km, hr) in opts.items():
        network._upsert_geom(rid, ART, json.dumps(line), km, hr, None, leg="loaded", alt_index=alt)
        network._upsert_geom(rid, ART, json.dumps(list(reversed(line))), km, hr, None, leg="return", alt_index=alt)


LAT1, LAT2, LAT3, LAT4 = 52.5, 52.6, 52.7, 52.8
# R1: the main line straight; Alt 1 north (a 7.5 t limit on it only); Alt 2 south, a little quicker, a little longer
add_route("R1", LAT1, {0: (bent(LAT1, 0), 7.0, 0.20), 1: (bent(LAT1, 0.01), 7.4, 0.19), 2: (bent(LAT1, -0.01), 7.2, 0.19)})
# R2: a dated closure crosses the main line; the diversion (quickest, no limit) is Alt 1; Alt 2 slower, fewer collisions
add_route("R2", LAT2, {0: (bent(LAT2, 0), 7.0, 0.20), 1: (bent(LAT2, 0.01), 7.4, 0.21), 2: (bent(LAT2, -0.01), 7.6, 0.23)})
# R3: Alt 1 shorter but slower (N5), fewer collisions
add_route("R3", LAT3, {0: (bent(LAT3, 0), 7.0, 0.20), 1: (bent(LAT3, 0.004), 6.5, 0.205)})
# R4: one option only
add_route("R4", LAT4, {0: (bent(LAT4, 0), 7.0, 0.20)})


def along(line, t0, t1, n=4):
    (x0, y0), (x1, y1) = line[0], line[1]
    return [[x0 + (x1 - x0) * (t0 + (t1 - t0) * i / (n - 1)), y0 + (y1 - y0) * (t0 + (t1 - t0) * i / (n - 1))]
            for i in range(n)]


def lim(ext, kind, value, geom, gtype="LineString", exceptions=None, name=None):
    return {"source": "test", "ext_id": ext, "kind": kind, "value": value, "geom_type": gtype, "geometry": geom,
            "length_m": None, "signed": None, "tags": {}, "exceptions": exceptions, "name": name}


W_ALT1 = lim("w1", "weight", 7.5, along(bent(LAT1, 0.01), 0.4, 0.5), exceptions="Except for access", name="Back Lane")
SHARED = lim("sh", "height", 3.0, [-1.0, LAT1], "Point", name="Quarry gate bridge")   # every R1 line passes it
# R4's main line (its only option) meets a 7.5 t limit mid-way, and starts on an "except for access" 7.5 t road the site
# is on (limits.site_allowed allows that one): in_use_limits lists the first and not the second (16 Nov evening)
W4_MID = lim("w4", "weight", 7.5, along(bent(LAT4, 0), 0.4, 0.5), name="Mill Road")
W4_SITE = lim("w4s", "weight", 7.5, along(bent(LAT4, 0), 0.0, 0.15), exceptions="Except for access", name="Pit Lane")
HELD = [W_ALT1, SHARED, W4_MID, W4_SITE]
route_choice._load_limits = lambda: list(HELD)

# the closure on R2's main line, in force on DAY
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT2 - 0.002], [-0.948, LAT2 - 0.002], [-0.948, LAT2 + 0.002],
                                           [-0.952, LAT2 + 0.002], [-0.952, LAT2 - 0.002]]]}
_z = zones.create_zone("Mill bridge closure", BOX, kind="closure", starts_on="2027-01-01", ends_on="2027-03-31")
route_choice.refresh_zones()


# R5 (16 Nov evening): the main line's two legs are DIFFERENT roads (loaded straight, back by the north road), and
# Alt 1 has a loaded line only, so it is costed with the main line's way back (return option 0), as on live's R003
LAT5 = 52.9
R5_A, R5_B, R5_C = bent(LAT5, 0), list(reversed(bent(LAT5, 0.01))), bent(LAT5, -0.01)
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'LR5a', 'Pit R5', ?, -1.0, 'Quarry')",
           (T, LAT5))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'LR5b', 'Yard R5', ?, -0.9, 'Compound')",
           (T, LAT5))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R5', 'LR5a', 'LR5b', "
           "'Small aggregate', 'IPT1')", (T,))
network._upsert_geom("R5", ART, json.dumps(R5_A), 7.0, 0.20, None, leg="loaded", alt_index=0)
network._upsert_geom("R5", ART, json.dumps(R5_B), 7.4, 0.21, None, leg="return", alt_index=0)
network._upsert_geom("R5", ART, json.dumps(R5_C), 7.0, 0.20, None, leg="loaded", alt_index=1)

DLAT = 1 / 110574.0


def on_line(lat, dlat, k, n, off_m=0.0):
    """The k-th of n points along the middle of bent(lat, dlat) (x from -0.962 to -0.938, where every option is at least
    800 m from every other), off_m metres north of it."""
    x = -0.962 + 0.024 * (k + 0.5) / n
    y = lat + dlat * (((x + 1) / 0.05) if x <= -0.95 else ((-0.9 - x) / 0.05))
    return x, y + off_m * DLAT


# collisions: on the road (within 25 m) or beyond it, a few with a goods vehicle over 3.5 t. Since 16 Nov evening the rule
# measures each record's own position to the option's lines, so each sits on (or off) the road it is said to be on; the
# stored per-key distances (`routes`) are kept as the fetch would write them, for route_compare and the grouping by route.
def rec(cid, routes, goods=False, lon=-0.95, lat=52.5):
    return {"collision_id": cid, "year": 2024, "month": 5, "lon": lon, "lat": lat, "severity": 3, "road": "A6",
            "road2": None, "junction": None, "road_type": None, "speed_limit": 40, "light": None, "authority": None,
            "n_casualties": 1, "n_vehicles": 2, "vru": [], "vru_ksi": [], "goods": goods, "dist_m": 5, "routes": routes,
            "sites": {}}


RECS, _n = [], [0]


def many(n, routes, at, goods=0, off_m=0.0):
    for i in range(n):
        _n[0] += 1
        lon, lat = on_line(at[0], at[1], i, n, off_m)
        RECS.append(rec(f"C{_n[0]}", routes, goods=i < goods, lon=lon, lat=lat))


many(23, {"R1": 5}, (LAT1, 0), goods=3)           # the main line: 23 on it, 3 with a goods vehicle
many(8, {"R1@2": 4}, (LAT1, -0.01), goods=1)      # Alt 2: 8, 1 goods
many(5, {"R1@1": 6}, (LAT1, 0.01))                # Alt 1: 5
many(4, {"R1": 60, "R1@2": 90}, (LAT1, 0), off_m=60)   # 60 m off the main line, on no road: never counted
many(20, {"R2@1": 5}, (LAT2, 0.01))               # R2's diversion (Alt 1): 20
many(30, {"R2": 5}, (LAT2, 0))                    # R2's main line: 30 (not in use on DAY)
many(5, {"R2@2": 5}, (LAT2, -0.01))               # R2 Alt 2: 5
many(23, {"R3": 5}, (LAT3, 0))
many(8, {"R3@1": 5}, (LAT3, 0.004))
many(23, {"R5": 5}, (LAT5, 0))                    # R5's main LOADED road: 23
many(5, {"R5": 5}, (LAT5, 0.01))                  # R5's main RETURN road (the north road): 5
many(8, {"R5@1": 5}, (LAT5, -0.01))               # R5 Alt 1's loaded road: 8
collisions.replace_all(RECS, FETCHED)


def write_history(prints=True, fetched_at=FETCHED):
    det = {"years": [2021, 2022, 2023, 2024, 2025], "files": [], "notes": [], "error": None, "hours": True,
           "vehicle_details": True, "searched": sorted(collisions.route_line_prints())}
    if prints:
        det["searched_prints"] = collisions.route_line_prints()
    collisions._write_meta("done", det, fetched_at=fetched_at)


# the lines were stored before the fetch: make every computed_at older than it
db.execute("UPDATE route_geometry SET computed_at = '2026-11-01T10:00:00+00:00' WHERE tenant_id = ?", (T,))
write_history()

# community: three schools 100 m south of R1's Alt 2, near nothing else
community.replace_source("gias", [{"source_ref": f"URN {i}", "kind": "schools", "name": f"School {i}",
                                   "geometry": {"type": "Point", "coordinates": [-0.95 + i * 0.001, LAT1 - 0.01 - 100 * DLAT]}}
                                  for i in range(3)], "2026-11-16T09:00:00Z")
_REAL_STATUS = community.status


def gate(open_):
    if open_ is None:
        community.status = _REAL_STATUS
    else:
        community.status = lambda: dict(_REAL_STATUS() or {}, all_options=open_)


PERIOD = collisions.period_words([2021, 2022, 2023, 2024, 2025])      # the app's own words for the five years


def run(rid, day=DAY):
    return RB.evaluate(rid, RB.Context(day=day))


def opt(r, alt):
    return next((o for o in r["options"] if o["alt"] == alt), None)


ALL_WORDS = []


def keep_words(r):
    ALL_WORDS.extend([r.get("why") or "", r.get("trade") or "", r.get("held_back") or ""] + list(r.get("sentences") or []))
    for o in r.get("options") or []:
        ALL_WORDS.extend(o["sentences"] + o["ruled_out"])


# =========================================================================== #
#  2. Limits (N1) and the plain answer                                         #
# =========================================================================== #
# NARROWED 16 Nov 2026 (the rule merged with claude/community-all-options): community.status() now carries the key. It
# reads False until a Fetch now has covered every stored option; a status with no key at all (an older layer's) still
# reads False. Before the merge this check asserted that the key was absent.
ok("2. the gate reads False while the layer was not fetched along every option (the key is there, and False)",
   (community.status() or {}).get("all_options") is False and RB.Context(day=DAY).community_all is False)
_status_was = community.status
community.status = lambda: {}
try:
    ok("2. ...and False where community.status() has no all_options key at all",
       RB.Context(day=DAY).community_all is False)
finally:
    community.status = _status_was
R1 = run("R1")
keep_words(R1)
o1, o2 = opt(R1, 1), opt(R1, 2)
ok("⭐ 2. a limit the option ADDS over the route in use rules it out, named, with its 'except for access' note",
   o1 and len(o1["added_limits"]) >= 1 and o1["ruled_out"] and "Back Lane" in o1["ruled_out"][0]
   and "except for access" in o1["ruled_out"][0] and o1["added_limits"][0]["except_for_access"] is True,
   str(o1 and o1["ruled_out"]))
# 17 Nov 2026 (ui-best-option-1117, Q1; John: "Yes, as recommended"): REVERSED. The reason read "it meets 1 road limit
# below this lorry that the route in use does not: Weight limit 7.5 t · Back Lane (except for access: ...) (both legs)";
# an added limit is now said road by road. Still named once and counted once, still both legs said once.
ok("2. a limit the option meets on both legs is named once and counted once (16 Nov evening: it was said twice, as 2)",
   o1 and o1["ruled_out"][0] == "it adds a 7.5 t limit, except for access, on Back Lane (both legs)"
   and not o1["ruled_out"][0].startswith("it meets 1 road limit below")
   and o1["ruled_out"][0].count("Back Lane") == 1 and len(o1["added_limits"]) == 2, str(o1 and o1["ruled_out"]))
ok("⭐ 2. a limit both lines meet (the quarry gate's bridge) does NOT rule an option out",
   o2 and not o2["ruled_out"] and not o2["added_limits"], str(o2 and o2["ruled_out"]))
ok("2. ...though the line in use meets it (it is below this lorry: the old 'any limit' rule would have ruled out every option)",
   len(route_choice._below_keys(bent(LAT1, 0), ART, "loaded", HELD)) == 1)
ok("⭐ 2. R1: Suggested Alt 2 on clearly fewer collisions, the same time and carbon",
   R1["answer"] == RB.SUGGESTED and R1["option"] == "Alt 2" and R1["alt"] == 2
   and o2["heads"] == {"people": 1, "time": 0, "busy": None, "carbon": 0}, f"{R1['answer']} {R1['why']} {o2 and o2['heads']}")
# 17 Nov 2026 (Q7): REVERSED. It began "About a minute quicker a round trip": a difference in minutes is said to the
# nearest half everywhere, so the card, the file and the record say one figure.
ok("2. the why is a fixed sentence with the two counts", R1["why"].startswith("1 min quicker a round trip, with fewer "
   "collisions on it (8 against 23)") and "About a minute" not in R1["why"], R1["why"])
ok("⭐ 2. collisions in plain words with the two counts and the period (4e)",
   f"Alt 2 had fewer collisions on it: 8 against 23 on the route in use, {PERIOD}." in R1["sentences"], str(R1["sentences"]))
ok("2. the route in use is option 0 on both legs on a day no zone touches R1", R1["in_use"]["pair"] == [0, 0]
   and R1["in_use"]["loaded"]["why"] == "main route")
ok("2. the lorry with no Approved load is the comparison's profile", R1["lorry"] == ART and R1["lorry_basis"] == "no approved loads")

# =========================================================================== #
#  3. A route on a dated zone's diversion                                      #
# =========================================================================== #
ok("3. the closure diverts R2 to Alt 1 (route_choice, the quickest with no limit) on DAY",
   route_choice.alt_on("R2", ART, "loaded", DAY) == 1 and route_choice.alt_on("R2", ART, "return", DAY) == 1)
R2 = run("R2")
keep_words(R2)
ok("⭐ 3. R2 is compared against its DIVERSION (Alt 1), not option 0: the in-use counts are Alt 1's",
   R2["in_use"]["pair"] == [1, 1] and R2["counts_in_use"]["collisions"] == 20 and R2["in_use"]["loaded"]["why"] == "diversion"
   and R2["in_use"]["loaded"]["until"] == "2027-03-31", f"{R2['in_use']} {R2.get('counts_in_use', {}).get('collisions')}")
o20, o22 = opt(R2, 0), opt(R2, 2)
ok("⭐ 3. option 0 crosses the closure in force and is ruled out (it would send lorries back through it)",
   o20 and o20["ruled_out"] and "Mill bridge closure" in o20["ruled_out"][0] and "until 31 Mar 2027" in o20["ruled_out"][0],
   str(o20 and o20["ruled_out"]))
ok("⭐ 3. (reversed 16 Nov evening) the closure's end reads as a person reads a date, never ISO (live R027: "
   "'closed until 2027-12-17')", "2027-03-31" not in " ".join(o20["ruled_out"]) and RB.date_words("2027-12-17") == "17 Dec 2027"
   and RB.date_words("2027-03-01") == "1 Mar 2027", str(o20["ruled_out"]))
import clp_doc  # noqa: E402
ok("3. the date words are the app's own (clp_doc._date_words' rule)",
   all(RB.date_words(d) == clp_doc._date_words(d) for d in ("2027-12-17", "2027-03-01", "2026-01-09", "2028-02-29")))
ok("⭐ 3. a closure the option crosses on BOTH legs is named once, '(both legs)' (it was a reason a leg, and the why named "
   "the loaded leg only)", len([r for r in o20["ruled_out"] if "Mill bridge closure" in r]) == 1
   and o20["ruled_out"][0].endswith("closed until 31 Mar 2027 (both legs)"), str(o20["ruled_out"]))
ok("⭐ 3. an option ruled out for ONE reason on both legs returns ONE string in options[i].ruled_out (the card's rows read "
   "it, never the why): the closure here, the added limit on R1's Alt 1",
   o20["ruled_out"] == ["it crosses Mill bridge closure, closed until 31 Mar 2027 (both legs)"]
   and len(opt(R1, 1)["ruled_out"]) == 1 and opt(R1, 1)["ruled_out"][0].endswith("(both legs)"),
   f"{o20['ruled_out']} {opt(R1, 1)['ruled_out']}")
_why_all = {"options": [o20], "answer": RB.KEEP, "option": None, "trade": None, "why": None, "held_back": None,
            "sentences": []}
RB._answer(_why_all, {}, RB.Context(day=DAY), "current")
keep_words(_why_all)
ok("3. ...and so the why says it once for both legs", _why_all["why"] == "Every other option is ruled out: The main route: it "
   "crosses Mill bridge closure, closed until 31 Mar 2027 (both legs).", _why_all["why"])
ok("3. ...and Alt 1 itself is not offered as a change", opt(R2, 1) is None)
ok("⭐ 3. Alt 2 has clearly fewer collisions than the diversion (5 against 20) but is slower: A trade-off, no pick",
   R2["answer"] == RB.TRADE_OFF and R2["option"] is None and o22["heads"]["people"] == 1 and o22["heads"]["time"] == -1
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the long line is "<option>: gains; losses" (it read "Alt 2 has …, but …")
   and R2["trade"].startswith("Alt 2: fewer collisions on it (5 against 20); ") and " but " not in R2["trade"], str(R2["trade"]))
R2_out = run("R2", day=datetime.date(2027, 6, 1))
ok("3. after the closure ends the route in use is option 0 again and Alt 1 is an option like any other",
   R2_out["in_use"]["pair"] == [0, 0] and opt(R2_out, 1) is not None and opt(R2_out, 0) is None)

# =========================================================================== #
#  4. N5: shorter but slower                                                   #
# =========================================================================== #
R3 = run("R3")
keep_words(R3)
o31 = opt(R3, 1)
ok("⭐ 4. N5: R3's Alt 1 is shorter but slower; ahead on people and carbon, behind on nothing: still not Suggested",
   o31 and o31["n5"] and o31["heads"]["people"] == 1 and o31["heads"]["time"] == 0 and R3["answer"] == RB.TRADE_OFF
   and "; it is a shorter road that takes longer" in R3["trade"], f"{R3['answer']} {R3['trade']}")
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the gains and losses are joined by "; " (it read ", but "); NARROWED: never "but" at all
ok("⭐ 4. (reversed 16 Nov evening) the trade line says no 'but': never '…, but it is shorter but slower'",
   R3["trade"].count(" but ") == 0 and R3["trade"].count("; ") == 1 and "shorter but slower" not in R3["trade"], R3["trade"])
ok("4. its sentences say so", any("is a shorter road that takes longer" in s and "so it is never suggested" in s
                                  for s in o31["sentences"]) and not any("shorter but slower" in s for s in o31["sentences"]))

# =========================================================================== #
#  5. Goods-vehicle counts                                                     #
# =========================================================================== #
ok("⭐ 5. goods-vehicle collisions on the road per option (route_best)",
   (R1["counts_in_use"]["goods"], o2["counts"]["goods"]) == (3, 1) and o2["parts"]["goods"] == 0, str(o2["counts"]))
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "involving an HGV" (it read "involving a goods vehicle over 3.5 t")
ok("5. the goods sentence says 'involving an HGV' and gives the two counts",
   f"Alt 2 had 1 collision involving an HGV on it against 3 on the route in use, {PERIOD}."
   in o2["sentences"], str(o2["sentences"]))
_cmp = {(r["route"], r["alt"]): r for r in route_compare.compare()["rows"]}
ok("⭐ 5. ...and route_compare.compare carries them too (all lorry types, the stored key)",
   _cmp[("R1", 0)]["goods"] == 3 and _cmp[("R1", 2)]["goods"] == 1 and _cmp[("R1", 0)]["collisions"] == 23)

# =========================================================================== #
#  6. The gate: cycle routes and community places                              #
# =========================================================================== #
ok("⭐ 6. gate closed: the places are counted and shown (3 against 0), marked not counted, and move nothing",
   o2["counts"]["places"] == 3 and R1["counts_in_use"]["places"] == 0 and o2["parts"]["community"] is None
   and o2["part_words"]["community"] == "not counted" and o2["parts"]["cycle"] is None
   and RB.NOT_FETCHED_WORDS in o2["sentences"])
ok("⭐ 6. a zero base gives the counts alone, no percentage (4f)",
   o2["pct"]["places"] is None and "It passes 3 schools, hospitals and health centres within 250 m against 0." in o2["sentences"],
   str(o2["sentences"]))
gate(True)
R1g = run("R1")
keep_words(R1g)
o2g = opt(R1g, 2)
ok("⭐ 6. gate open: the rise from 0 to 3 places shows and moves the answer (fewer collisions, more places): A trade-off",
   o2g["parts"]["community"] == -1 and o2g["heads"]["people"] == RB.MIXED and R1g["answer"] == RB.TRADE_OFF
   and "3 more schools, hospitals and health centres passed" in R1g["trade"] and RB.NOT_FETCHED_WORDS not in o2g["sentences"],
   f"{R1g['answer']} {R1g['trade']}")
ok("6. the other kinds are returned as shown only", set(o2g["counts"]["shown"]) == set(RB.SHOWN_KINDS))
gate(False)
ok("6. all_options False reads as closed", RB.Context(day=DAY).community_all is False and run("R1")["answer"] == RB.SUGGESTED)
gate(None)
ok("6. no blended exposure figure anywhere: a percentage per measure only", "exposure" not in json.dumps(R1g)
   and set(o2g["pct"]) == {"left_turns", "cycle_meets", "cycle_beside_km", "places"})

# =========================================================================== #
#  7. Stale collision keys (finding 4)                                         #
# =========================================================================== #
ok("7. with the fetch's fingerprints and no change since: current", R1["checks"]["collision_history"] == "current")
ok("7. the fetch keeps the fingerprints of the lines it searched (collisions.refresh)",
   'det["searched_prints"] = prints' in read("backend/collisions.py") and "prints = route_line_prints()" in read("backend/collisions.py"))
_p = collisions.route_line_prints()
ok("7. route_line_prints: one key an option, both legs and every lorry type under it", set(_p["R1@2"]) and len(_p["R1"]) == 2
   and "R1@10" not in _p, str(sorted(_p))[:200])
# 16 Nov evening (REVERSED): the counts are measured on the lines, so a Make primary, which swaps option numbers and
# changes no line, no longer makes the history out of date, and the counts follow the lines to their new numbers.
network.promote_alternative("R1", ART, 2, leg="loaded")
network.promote_alternative("R1", ART, 2, leg="return")
R1p = run("R1")
keep_words(R1p)
o2p = opt(R1p, 2)
ok("⭐ 7. (reversed) after Make primary the lines are the ones searched, only their numbers moved: current",
   R1p["checks"]["collision_history"] == "current", R1p["checks"]["collision_history"])
ok("⭐ 7. a Make primary swap no longer changes the counts: the south road is option 0 now and keeps its 8 (1 goods); the "
   "straight road is Alt 2 and keeps its 23 (3 goods)",
   (R1p["counts_in_use"]["collisions"], R1p["counts_in_use"]["goods"]) == (8, 1)
   and o2p and (o2p["counts"]["collisions"], o2p["counts"]["goods"]) == (23, 3) and o2p["parts"]["collisions"] == -1,
   f"{R1p.get('counts_in_use', {}).get('collisions')} {o2p and o2p['counts']['collisions']}")
ok("7. ...and they are put in words as they are", f"Alt 2 had more collisions on it: 23 against 8 on the route in use, {PERIOD}."
   in o2p["sentences"] and R1p["answer"] != RB.SUGGESTED, str(o2p["sentences"][:2]))
write_history(prints=False)        # an older fetch: no fingerprints kept
ok("7. a fetch with no fingerprints and no event since: current", run("R1")["checks"]["collision_history"] == "current")
db.execute("INSERT INTO audit_log (id, tenant_id, at, kind, method, path, status) VALUES ('a1', ?, '2026-11-03T13:00:00+00:00', "
           "'write', 'POST', '/api/admin/routes/R1/promote-alt', 200)", (T,))
ok("⭐ 7. (reversed) a Make primary in the audit log after an older fetch no longer makes it out of date (it moves no line)",
   run("R1")["checks"]["collision_history"] == "current")
ok("7. ...on any route", run("R3")["checks"]["collision_history"] == "current")
ok("7. the audit log is no longer read for it", "promote-alt" not in _rb.split("def history_state(")[1].split("\ndef ")[0]
   and "promoted_since" not in read("backend/route_best.py"))
db.execute("DELETE FROM audit_log WHERE id = 'a1'")
network.promote_alternative("R1", ART, 2, leg="loaded")       # back as it was searched
network.promote_alternative("R1", ART, 2, leg="return")
write_history(prints=True)
ok("7. promoted back: the lines match the search again, current and Suggested", run("R1")["answer"] == RB.SUGGESTED)
network._upsert_geom("R1", ART, json.dumps(bent(LAT1, -0.011)), 7.2, 0.19, None, leg="loaded", alt_index=2)
R1rr = run("R1")
keep_words(R1rr)
ok("⭐ 7. a re-route of one option after the fetch: out of date (by fingerprint): a road on it may not have been searched",
   R1rr["checks"]["collision_history"] == "out_of_date" and R1rr["answer"] != RB.SUGGESTED
   and all(o["parts"]["collisions"] is None for o in R1rr["options"])
   and "may not have been searched" in RB.STALE_WORDS and any(RB.STALE_WORDS in o["sentences"] for o in R1rr["options"]))
write_history(prints=False)
ok("7. ...and by its time for an older fetch", run("R1")["checks"]["collision_history"] == "out_of_date")
network._upsert_geom("R1", ART, json.dumps(bent(LAT1, -0.01)), 7.2, 0.19, None, leg="loaded", alt_index=2)
db.execute("UPDATE route_geometry SET computed_at = '2026-11-01T10:00:00+00:00' WHERE tenant_id = ?", (T,))
write_history(prints=True)
ok("7. restored", run("R1")["answer"] == RB.SUGGESTED)

# =========================================================================== #
#  8. No limits held; no alternative; no history                               #
# =========================================================================== #
route_choice._load_limits = lambda: []
R1n = run("R1")
keep_words(R1n)
ok("⭐ 8. with no road limits held nothing is suggested (no option could be checked); the reason is given",
   R1n["answer"] == RB.KEEP and R1n["held_back"] == RB.NO_LIMITS_WORDS and R1n["why"].startswith("Not suggested yet"),
   f"{R1n['answer']} {R1n['why']}")
ok("8. ...and a route with nothing to suggest carries no 'held back' note (it holds nothing back)",
   run("R4")["held_back"] is None)
route_choice._load_limits = lambda: list(HELD)
R4 = run("R4")
keep_words(R4)
ok("8. one option only: Keep the route in use", R4["answer"] == RB.KEEP and R4["options"] == []
   and R4["why"] == "No other option is stored for this lorry.")
collisions._write_meta("never", {}, fetched_at=None)
R1h = run("R1")
keep_words(R1h)
ok("8. no collision history fetched: collisions not compared, nothing suggested",
   R1h["checks"]["collision_history"] == "not_fetched" and R1h["answer"] == RB.KEEP and R1h["held_back"] == RB.NO_HISTORY_WORDS)
write_history(prints=True)

# =========================================================================== #
#  9. The lorry (N2)                                                           #
# =========================================================================== #
for i, (veh, qty, unit, status) in enumerate(((FLAT, 10, "vehicles", "Approved"), (ART, 4, "vehicles", "Approved"),
                                              (ART, 500, "vehicles", "Pending"))):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "vehicle_type, status) VALUES (?, ?, 'R1', ?, '', '', ?, ?, ?, ?)", (T, f"F{i}", i + 1, qty, unit, veh, status))
_loads = RB.approved_loads(conversions.load_factors())
ok("9. Approved loads only, by lorry type", _loads.get("R1") == {FLAT: 10, ART: 4}, str(_loads))
_ctx = RB.Context(day=DAY)
ok("⭐ 9. N2: the lorry the Approved loads mostly use, among the types with a line",
   RB.pick_lorry("R1", _ctx, [ART, FLAT]) == (FLAT, "approved loads") and RB.pick_lorry("R1", _ctx, [ART]) == (ART, "approved loads"))
ok("9. R1 holds Tipper lines only, so the Tipper speaks for it", run("R1")["lorry"] == ART)

# =========================================================================== #
#  10. The three example routes of rule_demo.py (13 Nov, live's figures then)  #
# =========================================================================== #


class Fake:
    lims = [1]
    community_all = False
    period = collisions.period_words([2021, 2025])


def M(col, goods, lt, meets, beside, places, km, drive, cyc_h, trips, co2):
    return {"collisions": col, "goods": goods, "left_turns": lt, "cycle_meets": meets, "cycle_beside_km": beside,
            "places": places, "km": km, "drive_min": drive, "cycle_min": round(cyc_h * 60, 1), "trips": trips,
            "co2_kg": co2, "busy_min": {h: None for h in RB.BUSY_HOURS}, "shown": {}}


def demo(use, alts, community_all=False):
    Fake.community_all = community_all
    use = dict(use, busy_at={h: None for h in RB.BUSY_HOURS})
    out = {"options": [RB.option_entry(a, m, use, Fake, "current") for a, m in alts], "answer": RB.KEEP, "option": None,
           "trade": None, "why": None, "held_back": None, "sentences": []}
    RB._answer(out, use, Fake, "current")
    keep_words(out)
    return out


# the demo's own figures (rule_demo.py ROUTES; places = schools + hospitals + health centres; goods 0 as it held)
D003 = demo(M(23, 0, 5, 3, 2.07, 6, 14.79, 20.3, 1.356, 6, 9.6),
            [(1, M(11, 0, 5, 6, 0.87, 5, 13.31, 23.3, 1.405, 6, 8.0)), (2, M(8, 0, 3, 3, 0.73, 4, 12.84, 21.4, 1.374, 6, 7.5))])
ok("⭐ 10. R003 (demo: 'Suggested Alt 2') is now 'A trade-off': Alt 2 is shorter (12.84 against 14.79 km) but slower "
   "(21.4 against 20.3 min), N5", D003["answer"] == RB.TRADE_OFF and D003["trade"].startswith("Alt 2: fewer collisions on it "
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "Alt 2: …; it is …" (it read "Alt 2 has …, but it is …")
   "(8 against 23)") and "; it is a shorter road that takes longer" in D003["trade"]
   and D003["trade"].count(" but ") == 0, f"{D003['answer']} {D003['trade']}")
D027 = demo(M(151, 0, 7, 20, 8.61, 9, 73.6, 88.0, 88.0 / 60 + 0.667, 4, 53.5),
            [(1, M(196, 0, 10, 21, 8.98, 8, 82.68, 104.2, 104.2 / 60 + 0.667, 3, 56.3)),
             (2, M(101, 0, 8, 17, 6.21, 8, 92.21, 106.7, 106.7 / 60 + 0.667, 3, 62.8))])
ok("⭐ 10. R027: 'A trade-off' as in the demo (Alt 2 fewer collisions, slower, a trip a day fewer, more carbon)",
   D027["answer"] == RB.TRADE_OFF and D027["option"] is None and "fewer collisions on it (101 against 151)" in D027["trade"]
   and "a lorry fits 3 trips a day, not 4" in D027["trade"], str(D027["trade"]))
D031 = demo(M(24, 0, 5, 1, 0.05, 1, 47.61, 55.3, 55.3 / 60 + 0.667, 0, 28.9),
            [(1, M(50, 0, 5, 1, 0.05, 6, 75.0, 86.3, 86.3 / 60 + 0.667, 0, 43.6)),
             (2, M(32, 0, 6, 1, 0.04, 2, 61.79, 74.5, 74.5 / 60 + 0.667, 0, 46.1))])
# 17 Nov 2026 (Q4): REVERSED. It read "No other option is clearly ahead on any head." ("head" is the rule's own word).
ok("⭐ 10. R031: 'Keep the route in use' as in the demo", D031["answer"] == RB.KEEP and D031["why"] ==
   "No other option is clearly better." and "head" not in D031["why"], str(D031["why"]))
D003g = demo(M(23, 0, 5, 3, 2.07, 6, 14.79, 20.3, 1.356, 6, 9.6),
             [(1, M(11, 0, 5, 6, 0.87, 5, 13.31, 23.3, 1.405, 6, 8.0)), (2, M(8, 0, 3, 3, 0.73, 4, 12.84, 21.4, 1.374, 6, 7.5))],
             community_all=True)
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "left-hand turns" (it read "left turns")
ok("10. R003 with the cycle and community parts counted: still 'A trade-off' (N5), with 2 fewer left-hand turns and 2 fewer places",
   D003g["answer"] == RB.TRADE_OFF and "2 fewer left-hand turns" in D003g["trade"]
   and "2 fewer schools, hospitals and health centres passed" in D003g["trade"], str(D003g["trade"]))

# =========================================================================== #
#  10b. Collisions counted on each pair's OWN lines (16 Nov evening)           #
# =========================================================================== #
R5 = run("R5")
keep_words(R5)
o51 = opt(R5, 1)
ok("10b. R5's Alt 1 has a loaded line only: it is costed with the main line's way back (return option 0)",
   o51 is not None and o51["return_alt"] == 0 and R5["in_use"]["pair"] == [0, 0], str(o51 and o51["return_alt"]))
ok("⭐ 10b. an option whose way back is the main line, with fewer collisions on its own loaded road than the main loaded "
   "road, reads FEWER: 13 (8 + 5 on the shared way back) against 28 (23 + 5)",
   o51 and (o51["counts"]["collisions"], R5["counts_in_use"]["collisions"]) == (13, 28) and o51["parts"]["collisions"] == 1
   and R5["answer"] == RB.SUGGESTED and R5["option"] == "Alt 1",
   f"{o51 and o51['counts']['collisions']} vs {R5.get('counts_in_use', {}).get('collisions')} {R5['answer']}")
ok("10b. ...the count by option number (the stored keys R5 and R5@1, both legs pooled) would read 36 against 28: never fewer",
   sum(1 for c in RECS if any(k in c["routes"] and c["routes"][k] <= collisions.ON_ROUTE_M for k in ("R5", "R5@1"))) == 36)
ok("⭐ 10b. a collision near both the loaded and the return line counts once",
   RB.count_on_lines([rec("X1", {}, goods=True, lon=-0.9995, lat=LAT5)], [R5_A, R5_B]) == {"all": 1, "goods": 1}
   and RB.count_on_lines([rec("X2", {}, lon=-0.95, lat=LAT5)], [R5_A, list(reversed(R5_A))]) == {"all": 1, "goods": 0})
ok("10b. ...and R1's main pair (the same road both ways) counts its 23 once, not 46", R1["counts_in_use"]["collisions"] == 23)
ok("10b. a collision 60 m off every line of a pair is not counted, wherever the stored distances say it is",
   RB.count_on_lines([rec("X3", {"R5": 5}, lon=-0.95, lat=LAT5 + 60 * DLAT)], [R5_A]) == {"all": 0, "goods": 0}
   and RB.count_on_lines([rec("X4", {}, lon=-0.95, lat=LAT5 + 20 * DLAT)], [R5_A]) == {"all": 1, "goods": 0})
ok("10b. the rule reads no stored per-key distance for its counts", 'c.get("routes")' not in _rb.split("def count_on_lines(")[1]
   .split("\ndef ")[0] and "_collision_counts" not in read("backend/route_best.py"))

# --- the fixed sentences: no phrase said twice, one "but" (16 Nov evening, live's R050 / R036 / R003 words) -------------
import re  # noqa: E402


def repeats(s, n=5):
    """The first run of n words said twice in s (figures and signs left out), or None."""
    w = re.findall(r"[a-z]+", s.lower())
    seen = set()
    for i in range(len(w) - n + 1):
        g = tuple(w[i:i + n])
        if g in seen:
            return " ".join(g)
        seen.add(g)
    return None


ok("10b. the check finds live's three faults", repeats("4 min quicker a round trip, with 4 min quicker a round trip.")
   and repeats("2 min quicker a round trip, with fewer collisions on it (2 against 10), 2 min quicker a round trip and "
               "4.6 kg CO2e less a trip.") and "Alt 2 has 2.1 kg CO2e less a trip, but it is shorter but slower.".count(" but ") == 2)
B = {h: 30.0 for h in RB.BUSY_HOURS}
GEN = []
for col in (4, 20, 40):
    for dt in (-6.0, 0.0, 6.0):
        for km in (8.0, 10.0, 12.0):
            for dco2 in (-1.5, 0.0, 1.5):
                for trips in (5, 6, 7):
                    for busy in (None, (-5.0, -5.0), (5.0, -5.0), (5.0, 5.0)):
                        for cmty in (False, True):
                            u = M(20, 2, 5, 3, 2.0, 4, 10.0, 20.0, 0.9, 6, 9.0)
                            u["busy_min"] = dict(B)
                            m = M(col, col // 10, 3 if cmty else 5, 3, 2.0, 1 if cmty else 4, km, 20.0 + dt,
                                  0.9 + dt / 60, trips, 9.0 + dco2)
                            m["busy_min"] = ({h: None for h in RB.BUSY_HOURS} if busy is None
                                             else {"08:00": 30.0 + busy[0], "17:00": 30.0 + busy[1]})
                            Fake.community_all = cmty
                            out = {"options": [RB.option_entry(2, m, dict(u, busy_at=dict(B)), Fake, "current")],
                                   "answer": RB.KEEP, "option": None, "trade": None, "why": None, "held_back": None,
                                   "sentences": []}
                            RB._answer(out, dict(u, busy_at=dict(B)), Fake, "current")
                            GEN.append(out)
Fake.community_all = False
_gen_words = [w for g in GEN for w in [g["why"] or "", g["trade"] or ""] + g["options"][0]["sentences"] if w]
_answers = {g["answer"] for g in GEN}
ok("10b. the typed combinations reach every answer (so every kind of line was written)", _answers == set(RB.ANSWERS), str(_answers))
_rep = [(w, repeats(w)) for w in _gen_words + [w for w in ALL_WORDS if w] if repeats(w)]
ok("⭐ 10b. no fixed sentence, why or trade line says a phrase of five words twice (live: 'min quicker a round trip')",
   not _rep, str(_rep[:2]))
_but = [w for w in _gen_words + ALL_WORDS if w and w.count(" but ") > 1]
ok("⭐ 10b. 'but' at most once in any line (live: '…, but it is shorter but slower')", not _but, str(_but[:2]))
ok("10b. 'shorter but slower' is said nowhere", not any("shorter but slower" in w for w in _gen_words + ALL_WORDS))
_q = [g for g in GEN if g["answer"] == RB.SUGGESTED and g["options"][0]["heads"]["time"] == 1
      and g["options"][0]["counts"]["cycle_min"] <= 0.9 * 60 - 1]
ok("⭐ 10b. a Suggested option quicker a round trip says its time once, first (live R050: 'with 4 min quicker a round trip')",
   _q and all(g["why"].count("quicker a round trip") == 1 and "quicker a round trip" in g["why"].split(",")[0] for g in _q),
   str([g["why"] for g in _q][:1]))
_bb = [g for g in GEN if "setting off at" in (g["why"] or "") + (g["trade"] or "")]
ok("10b. both busy hours ahead are said in one phrase ('quicker setting off at 08:00 (5 min) and 17:00 (5 min)')",
   any("quicker setting off at 08:00 (5 min) and 17:00 (5 min)" in (g["why"] or "") + (g["trade"] or "") for g in _bb),
   str([g["why"] for g in _bb][:1]))

# =========================================================================== #
#  10c. trade_short and in_use_limits (John's yes to the third draft, 16 Nov)  #
# =========================================================================== #
def wc(s):
    return len((s or "").split())


# the card's words (John's yes to the third draft, card 10): "Alt 2 is ahead on cycle routes and carbon, behind on places
# and time."; collisions said first as a fact, never ahead / behind (R5). Reversed 16 Nov night from the first wording
# ("Alt 2: fewer collisions, but slower.").
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): said as facts, "Alt 2: fewer collisions; slower." (it read "Alt 2 had fewer collisions and is behind on time.")
ok("⭐ 10c. trade_short: R2's trade in one line naming the heads only, in the card's words",
   R2["trade_short"] == "Alt 2: fewer collisions; slower." and wc(R2["trade"]) > wc(R2["trade_short"]),
   f"{R2.get('trade_short')!r} / {R2['trade']!r}")
ok("⭐ 10c. ...R3's: the N5 words once, last, no counts and no 'but'", R3["trade_short"].startswith("Alt 1: fewer collisions; ")
   and R3["trade_short"].endswith("; a shorter road that takes longer.") and " but " not in R3["trade_short"]
   and R3["trade_short"].count("a shorter road") == 1,
   R3.get("trade_short"))
ok("10c. trade_short is null where the answer is not a trade-off", R1["trade_short"] is None and run("R4")["trade_short"] is None
   and R5["trade_short"] is None and RB.Context and "trade_short" in run("R4"))
_trades = [g for g in GEN if g["answer"] == RB.TRADE_OFF] + [x for x in (R2, R3, R1g, D003, D027, D003g) if x["answer"] == RB.TRADE_OFF]
_shorts = [g["trade_short"] for g in _trades]  # (the live shapes below are pinned on their own)
ok("10c. the typed combinations make many trade-offs to measure", len(_trades) > 200, str(len(_trades)))
ok("⭐ 10c. every trade_short the harness makes is at most 25 words, holds no 'but', and every trade-off has one",
   all(s and wc(s) <= RB.SHORT_MAX and " but " not in s for s in _shorts),
   [s for s in _shorts if not s or wc(s) > RB.SHORT_MAX or " but " in s][:2])
ok("10c. ...about 20 words: the middle one of every trade_short the harness makes is 20 words or under (19 on 16 Nov, "
   "over the typed combinations, which load many heads at once)",
   sorted(wc(s) for s in _shorts)[len(_shorts) // 2] <= 20, str(sorted(wc(s) for s in _shorts)[len(_shorts) // 2]))
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the option's name and a colon (it read "<option> had … / is ahead …"); "Diversion" for "Way round"
_LABEL_RE = re.compile(r"^(The main route|Alt \d+|Diversion(?: \d+)?): ")


def _after_label(s):
    return _LABEL_RE.sub("", s or "", count=1)


# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): NARROWED: no "ahead", "behind" or "trade" either (Q8)
_BANNED_SHORT = ("better", "safer", "mixed by", "less by", "%", " rate", "ratio", "risk", " but ", "ahead", "behind", "trade",
                 "worse")
ok("⭐ 10c. heads only: no figure in trade_short but the option's own name; never 'better', 'safer', 'mixed by', "
   "'less by', 'but', a percentage, a rate or a ratio",
   all(_LABEL_RE.match(s) for s in _shorts)
   and not [s for s in _shorts if re.search(r"\d", _after_label(s))]
   and not [s for s in _shorts if any(b in s.lower() for b in _BANNED_SHORT)],
   [s for s in _shorts if re.search(r"\d", _after_label(s)) or any(b in s.lower() for b in _BANNED_SHORT)][:2])
# the card's pattern: "<option> [had fewer|more collisions and] is ahead on <heads>, behind on <heads>[; mixed on <heads>]
# [; a shorter road that takes longer]." with the five plain head names only
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the card 6 pattern, "<option>: <collisions>; <fewer …, less carbon>; <more …>; <quicker|slower>; <… mixed>; <N5>."
# (it read "<option> had fewer collisions and is ahead on …, behind on …; mixed on …")
def _hl(names):
    return rf"{names}(?:, {names})*(?: and {names})?"


_HEAD_NAMES = r"(?:cycle routes|places|time|busy hours|carbon)"
_HEAD_LIST = _hl(_HEAD_NAMES)
_TW = r"(?:quicker|slower)"
_SHORT_RE = re.compile(rf"^(?:The main route|Alt \d+|Diversion(?: \d+)?): (?:"
                       rf"(?:(?:fewer|more) collisions(?: involving an HGV)?(?: and (?:fewer|more) involving an HGV)?)?"
                       rf"(?:(?:^|(?<=: )|; )(?:fewer {_hl('(?:cycle routes|places)')}(?:, less carbon)?|less carbon))?"
                       rf"(?:(?:(?<=: )|; )more {_hl('(?:cycle routes|places|carbon)')})?"
                       rf"(?:(?:(?<=: )|; )(?:{_TW}(?:, {_TW} in the busy hours)?|{_TW} in the busy hours))?"
                       rf"(?:(?:(?<=: )|; ){_HEAD_LIST} mixed)?"
                       rf"(?:(?:(?<=: )|; )a shorter road that takes longer)?"
                       rf"|the same on every measure)\.$")
ok("⭐ 10c. every trade_short is in the card's pattern: '<option>: fewer …; more …; slower; … mixed.' with the plain head names; "
   "collisions first as a fact; a mixed head last; the N5 words last of all",
   all(_SHORT_RE.match(s) for s in _shorts), [s for s in _shorts if not _SHORT_RE.match(s)][:3])
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): nothing is "ahead" or "behind" now; collisions are still never better or worse, and never "mixed"
ok("⭐ 10c. collisions are never 'ahead' or 'behind' (R5: plain words): no 'ahead', 'behind' or 'collisions mixed' in any line",
   not [s for s in _shorts if re.search(r"ahead|behind|collisions[^;.]* mixed", s)] and _shorts)
ok("10c. a mixed head is in neither list: no head named twice in one line",
   not [s for s in _shorts if any(len(re.findall(rf"\b{h}\b", s)) > 1 for h in ("cycle routes", "places", "time",
                                                                              "busy hours", "carbon"))])
ok("10c. no five words said twice in any trade_short", not [s for s in _shorts if repeats(s)])
# the three live shapes: R001's long line 44 words, R003's 39, R036's 31 (16 Nov 19:20 UTC); typed here as their heads
D001 = demo(M(165, 9, 9, 6, 3.1, 5, 41.0, 50.0, 50.0 / 60 + 0.667, 5, 30.0),
            [(1, M(84, 2, 14, 9, 4.6, 9, 44.0, 47.0, 47.0 / 60 + 0.667, 4, 32.2))], community_all=True)
D036 = demo(M(10, 1, 6, 2, 0.4, 2, 20.0, 30.0, 0.5 + 0.667, 6, 14.0),
            [(1, M(2, 0, 6, 2, 0.4, 2, 21.0, 28.0, 28.0 / 60 + 0.667, 5, 9.4))])
# R006: its figures are not in route-best-live-1116\examples.md; typed as the heads of live's second short line quoted by
# the mother session on 16 Nov night ("Alt 1: less by cycle routes, but slower and more carbon."): cycle routes ahead,
# time and carbon behind, collisions no clear gap
D006 = demo(M(20, 1, 6, 8, 3.0, 4, 30.0, 40.0, 1.2, 6, 20.0),
            [(1, M(20, 1, 4, 5, 1.5, 4, 32.0, 46.0, 1.3, 6, 22.0))], community_all=True)
_shapes = {"R001": D001, "R003": D003, "R006": D006, "R036": D036}
L001 = demo(M(165, 12, 4, 42, 15.81, 18, 62.64, 78.3, 120.3 / 60, 4, 42.2),
            [(1, M(97, 5, 17, 29, 14.26, 23, 83.96, 101.8, 143.8 / 60, 3, 57.8))], community_all=True)
L003 = demo(M(23, 0, 9, 7, 4.7, 6, 14.79, 20.3, 81.4 / 60, 6, 9.6),
            [(1, M(28, 0, 9, 9, 3.92, 9, 13.31, 23.3, 84.3 / 60, 6, 8.0)),
             (2, M(26, 0, 7, 7, 3.38, 9, 12.84, 21.4, 82.4 / 60, 6, 7.5))], community_all=True)
L036 = demo(M(10, 1, 4, 1, 0.6, 1, 17.48, 19.9, 63.9 / 60, 8, 16.3),
            [(1, M(2, 0, 4, 2, 1.79, 0, 12.34, 17.8, 61.7 / 60, 8, 11.7)),
             (2, M(6, 0, 12, 4, 1.73, 1, 16.15, 22.0, 66.0 / 60, 8, 14.8))], community_all=True)
_live = {"R001": L001, "R003": L003, "R036": L036}
ok("⭐ 10c. live's own figures give live's own long lines, word for word (so the shapes are live's)",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "Alt 1: gains; losses." (it read "Alt 1 has gains, but losses."); "left-hand turns"
   L001["trade"] == "Alt 1: fewer collisions on it (97 against 165), 13 fewer cycle routes met and 1.55 km less beside "
   # 17 Nov 2026 (Q7, Q5): REVERSED in two places. "24 min more a round trip" is "23.5 min more" (halves); and the
   # rule writes CO₂e, as the card's own rows do (it wrote "CO2e").
   "a cycle route; 13 more left-hand turns, 5 more schools, hospitals and health centres passed, 23.5 min more a round trip, "
   "a lorry fits 3 trips a day, not 4 and 15.6 kg CO₂e more a trip."
   and L003["trade"] == "Alt 2: 2 fewer left-hand turns, 1.32 km less beside a cycle route and 2.1 kg CO₂e less a trip; "
   "3 more schools, hospitals and health centres passed and it is a shorter road that takes longer."
   and L036["trade"] == "Alt 1: fewer collisions on it (2 against 10), 2 min quicker a round trip and 4.6 kg CO₂e less "
   "a trip; 1.19 km more beside a cycle route."
   and not any("CO2e" in str(x.get("trade")) for x in (L001, L003, L036)),
   " | ".join(str(x.get("trade")) for x in _live.values()))
ok("⭐ 10c. ...and their short lines in the card's words (R006 typed from its heads)",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the card 6 words; R001's is the card's own example word for word
   L001["trade_short"] == "Alt 1: fewer collisions; more places and carbon; slower; cycle routes mixed."
   and L003["trade_short"] == "Alt 2: fewer cycle routes, less carbon; more places; a shorter road that takes longer."
   and L036["trade_short"] == "Alt 1: fewer collisions; less carbon; more cycle routes; quicker."
   and all(_SHORT_RE.match(x["trade_short"]) and wc(x["trade_short"]) <= RB.SHORT_MAX
           and not any(b in x["trade_short"].lower() for b in _BANNED_SHORT)
           and not re.search(r"\d", _after_label(x["trade_short"]))
           for x in list(_live.values()) + list(_shapes.values())),
   " | ".join(str(x.get("trade_short")) for x in _live.values()))
ok("⭐ 10c. the live shapes: each a trade-off whose long line runs long, and whose trade_short is at most 25 words",
   all(x["answer"] == RB.TRADE_OFF and x["trade_short"] and wc(x["trade_short"]) <= RB.SHORT_MAX for x in _shapes.values())
   and wc(D001["trade"]) > RB.SHORT_MAX,
   {k: (x["answer"], wc(x.get("trade")), wc(x.get("trade_short")), x.get("trade_short")) for k, x in _shapes.items()})
ok("10c. the live shapes read as written in the card's words (reversed 16 Nov night from 'Alt 2: fewer collisions and "
   "less carbon, but a shorter road that takes longer.' and 'Alt 1: fewer collisions, quicker and less carbon, but fewer "
   "trips a day.')",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the card 6 words (they read "… had fewer collisions and is ahead on …")
   D003["trade_short"] == "Alt 2: fewer collisions; less carbon; a shorter road that takes longer."
   and D036["trade_short"] == "Alt 1: fewer collisions; less carbon; time mixed."
   and D001["trade_short"] == "Alt 1: fewer collisions; more cycle routes, places and carbon; time mixed."
   and D006["trade_short"] == "Alt 1: fewer cycle routes; more carbon; slower."
   and wc(D001["trade"]) > 40,
   f"{D003.get('trade_short')} | {D036.get('trade_short')} | {D001.get('trade_short')} | {D006.get('trade_short')}")
_big = dict(D001["options"][0], parts={"collisions": 1, "goods": -1, "cycle": -1, "community": -1},
            heads={"people": RB.MIXED, "time": 1, "busy": -1, "carbon": -1}, n5=False)
_bs = RB.trade_short(_big)
ok("10c. every head and part at once still fits (the levels take over past 25)", wc(_bs) <= RB.SHORT_MAX
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "fewer collisions and more involving an HGV" (it read "had fewer collisions")
   and _bs == "Alt 1: fewer collisions and more involving an HGV; more cycle routes, places and carbon; quicker, slower in "
   "the busy hours." and _SHORT_RE.match(_bs), f"{wc(_bs)} {_bs}")
# the mixed words live in ONE place (SHORT_MIXED): changed or emptied there, every line follows
_mx = dict(D001["options"][0], parts={"collisions": 0, "goods": 0, "cycle": RB.MIXED, "community": -1},
           heads={"people": RB.MIXED, "time": 1, "busy": None, "carbon": RB.MIXED}, n5=False)
_mx_on = RB.trade_short(_mx)
_keep_mixed = RB.SHORT_MIXED
RB.SHORT_MIXED = ""
_mx_off = RB.trade_short(_mx)
RB.SHORT_MIXED = _keep_mixed
ok("⭐ 10c. a mixed head is said last ('; mixed on cycle routes and carbon'); the words sit in SHORT_MIXED alone",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "; cycle routes and carbon mixed" (it read "; mixed on cycle routes and carbon")
   _mx_on == "Alt 1: more places; quicker; cycle routes and carbon mixed."
   and _mx_off == "Alt 1: more places; quicker." and RB.SHORT_MIXED == "mixed"
   and read("backend/route_best.py").count('SHORT_MIXED = "mixed"') == 1, f"{_mx_on!r} / {_mx_off!r}")
# a mixed time head (quicker a round trip, a trip a day fewer) is said as mixed, not "slower"
_mt = dict(D001["options"][0], parts={"collisions": 1, "goods": 1, "cycle": 0, "community": 0},
           heads={"people": 1, "time": RB.MIXED, "busy": None, "carbon": 1}, n5=True)
ok("10c. a mixed time is said as mixed, and the N5 words are left out where time is not ahead or level",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended")
   RB.trade_short(_mt) == "Alt 1: fewer collisions; less carbon; time mixed.", RB.trade_short(_mt))
# goods-vehicle collisions that go the other way from all collisions are said, and dropped first when the line runs long
_gd = dict(D001["options"][0], parts={"collisions": 1, "goods": -1, "cycle": 0, "community": 0},
           heads={"people": RB.MIXED, "time": -1, "busy": None, "carbon": 0}, n5=False)
_gd2 = dict(_gd, parts={"collisions": 0, "goods": 1, "cycle": 0, "community": 0},
            heads={"people": 1, "time": -1, "busy": None, "carbon": 0})
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "involving an HGV" (it read "goods-vehicle collisions")
ok("10c. HGV collisions said where they go their own way",
   RB.trade_short(_gd) == "Alt 1: fewer collisions and more involving an HGV; slower."
   and RB.trade_short(_gd2) == "Alt 1: fewer collisions involving an HGV; slower.",
   f"{RB.trade_short(_gd)!r} / {RB.trade_short(_gd2)!r}")

ok("⭐ 10c. in_use_limits: the limit the line in use itself meets, with its name, on both legs (R1: the quarry gate's bridge)",
   [(x["legs"], "Quarry gate bridge" in x["words"]) for x in R1["in_use_limits"]] == [("both", True)],
   str(R1["in_use_limits"]))
ok("10c. ...reported only: R1's answer is still Suggested Alt 2", R1["answer"] == RB.SUGGESTED and R1["option"] == "Alt 2")
R4l = run("R4")
_w4 = [x["words"] for x in R4l["in_use_limits"]]
ok("⭐ 10c. a 7.5 t limit on the line in use is listed in the added-limit words ('Weight limit 7.5 t', the road's name)",
   len(_w4) == 1 and _w4[0].startswith("Weight limit 7.5 t") and "Mill Road" in _w4[0] and R4l["in_use_limits"][0]["legs"] == "both"
   and R4l["answer"] == RB.KEEP, str(R4l["in_use_limits"]))
ok("⭐ 10c. ...and the 'except for access' road the site is on (limits.site_allowed) is NOT listed",
   not any("Pit Lane" in w for w in _w4), str(_w4))
_no_exc = dict(W4_SITE, exceptions=None)
_ctx4 = RB.Context(day=DAY)
_ctx4.lims = [W4_MID, _no_exc]
ok("10c. ...it is the site rule that leaves it out: the same road with no exception on its sign is listed",
   any("Pit Lane" in x["words"] for x in RB.in_use_limits({"loaded": bent(LAT4, 0), "return": list(reversed(bent(LAT4, 0)))},
                                                           ART, _ctx4)))
ok("10c. a line in use with no limit below the lorry gives an empty list", R3["in_use_limits"] == [] and R2["in_use_limits"] == [])
ok("10c. one leg only reads 'loaded' or 'return'", RB.in_use_limits({"loaded": bent(LAT4, 0), "return": None}, ART, _ctx4)[0]["legs"]
   == "loaded")
# 17 Nov: `short`, the limit as a person names it inside a sentence ("The diversion in use meets a 7.5 t limit below this
# lorry."), beside `words` (unchanged)
ok("⭐ 10c. in_use_limits: each entry carries `short` beside `words` (R4: '7.5 t limit'; R1's bridge too)",
   [x.get("short") for x in R4l["in_use_limits"]] == ["7.5 t limit"] and R4l["in_use_limits"][0]["words"].startswith("Weight limit 7.5 t")
   and all(x.get("short", "").endswith(" limit") for x in R1["in_use_limits"]),
   str(R4l["in_use_limits"]) + " / " + str(R1["in_use_limits"]))
_shorts_by_kind = {(k, v): RB.limit_short({"kind": k, "value": v}) for k, v in
                   (("weight", 7.5), ("weight", 18), ("height", 4.2), ("height", 4.0), ("width", 2.5), ("width", 2.0),
                    ("axle", 10), ("axle", 11.5))}
ok("⭐ 10c. `short` for each kind the app holds, in the app's own figures (limits.fmt_value: heights and widths keep one decimal)",
   _shorts_by_kind == {("weight", 7.5): "7.5 t limit", ("weight", 18): "18 t limit", ("height", 4.2): "4.2 m height limit",
                       ("height", 4.0): "4.0 m height limit", ("width", 2.5): "2.5 m width limit",
                       ("width", 2.0): "2.0 m width limit", ("axle", 10): "10 t axle limit", ("axle", 11.5): "11.5 t axle limit"},
   str(_shorts_by_kind))
_all_kind_shorts = list(_shorts_by_kind.values()) + [RB.limit_short({"kind": k, "value": None}) for k in ("weight", "height", "width", "axle")]
ok("⭐ 10c. `short` carries no capital and no colon, no double space, no road name, and ends 'limit' (every kind, with and "
   "without a value)",
   all(s == s.lower() and ":" not in s and "  " not in s and s.endswith(" limit") and "·" not in s for s in _all_kind_shorts)
   and set(RB._SHORT_NOUN) == set(__import__("limits").KINDS),
   str(_all_kind_shorts))

# =========================================================================== #
#  11. Words                                                                   #
# =========================================================================== #
_words = [w for w in ALL_WORDS + _gen_words if w]
# 17 Nov 2026 (Q4; John: "Yes, as recommended"): NARROWED. "better" is still in no sentence about an option's counts,
# but ONE fixed sentence may say it, word for word: "No other option is clearly better." (it read "... clearly ahead on
# any head."). Every other sentence is checked as before.
_low = " ".join(w for w in _words if w != RB.NONE_BETTER_WORDS).lower()
ok("⭐ 11. never 'safer', 'better', a rate, a ratio, a score or a risk; no supplier; lorry, not truck",
   not any(b in _low for b in ("safer", "better", " rate", "ratio", "score", "risk", "here ", "truck", "exposure"))
   and RB.NONE_BETTER_WORDS == "No other option is clearly better.",
   [b for b in ("safer", "better", " rate", "ratio", "score", "risk", "here ", "truck", "exposure") if b in _low])
ok("⭐ 11. no '%' in any sentence about collisions", not any("%" in w for w in _words if "collision" in w.lower()),
   [w for w in _words if "collision" in w.lower() and "%" in w][:2])
ok("11. the words were read from every scenario", len(_words) > 60, str(len(_words)))
import re as _re  # noqa: E402
ok("⭐ 11. no line of the rule carries an ISO date (16 Nov evening: 'closed until 2027-12-17')",
   not [w for w in _words if _re.search(r"\b\d{4}-\d{2}-\d{2}\b", w)],
   [w for w in _words if _re.search(r"\b\d{4}-\d{2}-\d{2}\b", w)][:2])
ok("11. the rule writes no date but through date_words", "until {date_words(until)}" in _rb
   and "until {until}" not in _rb)

# =========================================================================== #
#  12. The admin read                                                          #
# =========================================================================== #
TAB = main.route_options_best(day="2027-02-02", token="best-admin-token")
ok("⭐ 12. the table: every route, a row a (route, option), the thresholds and the checks",
   TAB["day"] == "2027-02-02" and [r["route"] for r in TAB["routes"]] == ["R1", "R2", "R3", "R4", "R5"]
   and TAB["thresholds"]["set_by_john"] is False and TAB["checks"]["limits_held"] is True
   and TAB["checks"]["community_all_options"] is False and TAB["checks"]["collision_fingerprints_kept"] is True
   # R5 (added 16 Nov evening) is the second Suggested
   and TAB["totals"] == {RB.SUGGESTED: 2, RB.TRADE_OFF: 2, RB.KEEP: 1, "no_alternative": 1}, str(TAB["totals"]))
_rows = {(r["route"], r["option"]): r for r in TAB["rows"]}
ok("12. each row: route, from, to, lorry, answer, the option, each head, the counts on both sides, why, what ruled it out",
   all(k in _rows[("R1", "Alt 2")] for k in ("from", "to", "lorry", "answer", "heads", "counts", "counts_in_use", "pct",
                                             "why", "ruled_out", "chosen", "traded"))
   and _rows[("R1", "Alt 2")]["chosen"] is True and _rows[("R1", "Alt 1")]["ruled_out"]
   and _rows[("R2", "Alt 2")]["traded"] is True and _rows[("R4", None)]["answer"] == RB.KEEP
   and _rows[("R1", "Alt 2")]["heads"]["people"] == "fewer" and _rows[("R1", "Alt 2")]["from"] == "Pit R1")
try:
    main.route_options_best(day="2027-02-02", token="wrong")
    _refused = False
except _HTTPException as e:
    _refused = e.status_code == 403
ok("⭐ 12. admin only (a wrong token is refused)", _refused)
try:
    main.route_options_best(day="2 Feb", token="best-admin-token")
    _bad = None
except _HTTPException as e:
    _bad = e.status_code
ok("12. a day that is not YYYY-MM-DD is a 400", _bad == 400)
_m = read("backend/main.py")
_f = _m.split("def route_options_best(")[1].split("\n@app")[0]
_bt = (_m.split("def _best_table(") + [""])[1].split("\ndef ")[0]
ok("⭐ 12. a heavy staff read: _staff_json, one Context (one pre, prefetch), placed after _gate_arrivals_build",
   # NARROWED 17 Nov 2026 (claude/warm-best-option): the admin table and the card share ONE helper, _best_table, which
   # holds the _staff_json call (it was written out in each endpoint)
   '"/api/admin/route-options/best"' in _m and "_check_admin(token)" in _f and "return _best_table(d)" in _f
   and "_staff_json(" in _bt and "route_best.table(d)" in _bt and _m.index("def _gate_arrivals_build(") < _m.index("def route_options_best(")
   and "network.prefetch_analysis_geometry(self.pre)" in _rb)
ok("12. no outside call in the rule (no router, no fetch)", not any(x in _rb for x in ("here_routing.route", "requests.",
                                                                                       "urllib", "fetch_years", "refresh(")))
_tg = read("frontend/help/technical/index.html")
# NARROWED 16 Nov 2026 (step 1b): the user guide now has the card's section; it still names no admin endpoint
ok("12. the technical guide has the rule's section; the user guide names no endpoint of it",
   'id="t2-best-option"' in _tg and "/api/admin/route-options/best" in _tg and "searched_prints" in _tg
   and "route-options/best" not in read("frontend/help/index.html") and 'id="ug-best-option"' in read("frontend/help/index.html"))
_fe = read("frontend/index.html")
# REVERSED 16 Nov 2026 (step 1b, John's yes to the third draft): the card on Data -> Routes reads the rule through the
# staff read /best-option (never the admin table), and 'Counts only: nothing is scored or ranked' is gone (Q1)
ok("12. the card: the frontend reads /best-option, not the admin table, and 'Counts only: nothing is scored or ranked' is gone",
   "route-options/best" not in _fe and "/best-option`" in _fe and "Counts only: nothing is scored or ranked" not in _fe)

ok("⭐ 12. every row of the admin table carries trade_short and in_use_limits (the card is built to these names)",
   all("trade_short" in r and "in_use_limits" in r for r in TAB["rows"])
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended")
   and _rows[("R2", "Alt 2")]["trade_short"] == "Alt 2: fewer collisions; slower."
   and _rows[("R1", "Alt 2")]["trade_short"] is None
   and [x["legs"] for x in _rows[("R4", None)]["in_use_limits"]] == ["both"]
   and [x["short"] for x in _rows[("R4", None)]["in_use_limits"]] == ["7.5 t limit"]
   and all(isinstance(r["in_use_limits"], list) for r in TAB["rows"]), str(_rows[("R4", None)].get("in_use_limits")))
_tab_words = [w for r in TAB["routes"] for w in [r.get("why") or "", r.get("trade") or "", r.get("held_back") or ""]
              + list(r.get("sentences") or []) + [s for o in r["options"] for s in o["sentences"] + o["ruled_out"]]] \
    + [r.get("ruled_out") or "" for r in TAB["rows"]]
ok("⭐ 12. ...nor does any line of the admin table (why, trade, held back, sentences, what ruled an option out)",
   not [w for w in _tab_words if _re.search(r"\b\d{4}-\d{2}-\d{2}\b", w)] and any("31 Mar 2027" in w for w in _tab_words),
   [w for w in _tab_words if _re.search(r"\b\d{4}-\d{2}-\d{2}\b", w)][:2])

# =========================================================================== #
#  13. One kept copy for every staff caller, built by the warm-up (17 Nov 2026) #
# =========================================================================== #
# John, 17 Nov 2026: "Yes, add it". On live the first card after a deploy, a write or midnight waited 29 to 35 s for the
# rule's table, and each role and team built its own copy of the same table.
import access  # noqa: E402
import read_cache  # noqa: E402


def _as(acc, fn):
    tok = access._ACCESS.set(acc)
    try:
        return fn()
    finally:
        access._ACCESS.reset(tok)


_ADMIN = {"role": "admin", "ipt": None, "label": "Admin", "via": "login", "kind": "staff"}
_TEAM = {"role": "ipt", "ipt": "IPT1", "label": "Team 1", "via": "login", "kind": "staff"}
_PLAN = {"role": "planner", "ipt": None, "label": "Planner", "via": "login", "kind": "staff"}
read_cache.clear()
_b0 = read_cache.STATS["builds"]
_c1 = _as(_ADMIN, lambda: main.route_best_option("R1"))
_b1 = read_cache.STATS["builds"]
_c2 = _as(_TEAM, lambda: main.route_best_option("R1"))
_c3 = _as(_PLAN, lambda: main.route_best_option("R2"))
_b2 = read_cache.STATS["builds"]
# REVERSED 17 Nov 2026 (claude/best-option-one-first; the frontier check's Idea 2, John: "All as recommended"): with no
# table held a card no longer builds the table: it works out its OWN route (one build), a second caller of the same
# route builds nothing, another route is one more build, and the table is still not held. It read "an admin's first
# card builds the table once; a team's and a planner's cards build nothing more".
ok("⭐ 13. the card's read with no table held: the first card works out its own route once; a team's card for the same "
   "route builds nothing; a planner's other route is one more build; no table is built",
   _b1 - _b0 == 1 and _b2 - _b1 == 1 and _c1["route"]["route"] == "R1" and _c2["route"] == _c1["route"]
   and _c3["route"]["route"] == "R2" and getattr(main, "_best_table_held", lambda d: "?")(datetime.date.today()) is None,
   f"builds {_b1 - _b0} then {_b2 - _b1}")
_today = datetime.date.today().isoformat()
_t_today = main.route_options_best(day=None, token="best-admin-token")
# NARROWED 17 Nov 2026 (claude/best-option-one-first): the cards above built no table, so the admin read builds it (one
# build); the card that follows is served from it and builds nothing (it read "the same kept copy (no build)")
_b2a = read_cache.STATS["builds"]
_c1t = _as(_ADMIN, lambda: main.route_best_option("R1"))
ok("13. the admin table for today is one build, held for every staff caller; the card after it builds nothing",
   _b2a == _b2 + 1 and read_cache.STATS["builds"] == _b2a and _t_today["day"] == _today
   and [r["route"] for r in _t_today["routes"]] == ["R1", "R2", "R3", "R4", "R5"]
   and getattr(main, "_best_table_held", lambda d: "?")(datetime.date.today()) is not None and _c1t["route"]["route"] == "R1")
try:
    main.route_best_option("R1")
    _open = True
except _HTTPException as e:
    _open = e.status_code != 401
ok("⭐ 13. the wall stays: with no sign-in the card's read is refused although a copy is held", _open is False)
try:
    _as(_ADMIN, lambda: main.route_best_option("NOPE"))
    _nf = None
except _HTTPException as e:
    _nf = e.status_code
ok("13. an unknown route is still a 404", _nf == 404)
read_cache.clear()
_b3 = read_cache.STATS["builds"]
read_cache.WARMERS["best_option"]()
_b4 = read_cache.STATS["builds"]
_c4 = _as(_TEAM, lambda: main.route_best_option("R1"))
ok("⭐ 13. the warm-up builds today's table, and the first card after it (any staff caller) builds nothing",
   _b4 - _b3 == 1 and read_cache.STATS["builds"] == _b4 and _c4["route"]["route"] == "R1")
ok("13. it is registered last, after the Dashboard's and the public map's reads, and warm() runs it without an error",
   list(read_cache.WARMERS)[-1] == "best_option" and read_cache.WARMERS["best_option"] is main._warm_best
   and all(k in read_cache.WARMERS for k in ("staff", "public_map")))
ok("13. one _staff_json call for the table in main.py, with the shared scope (never the caller's)",
   _m.count('_staff_json("route-options/best"') == 1 and "BEST_SCOPE)" in _bt
   and main._staff_scope(main.BEST_SCOPE) == "staff|-"
   and main._staff_name("route-options/best", {"day": _today}, main.BEST_SCOPE)
   == main._staff_name("route-options/best", {"day": _today}, dict(main.BEST_SCOPE)))
_db_v = db.data_version()
db.bump_data_version()
_b5 = read_cache.STATS["builds"]
_as(_ADMIN, lambda: main.route_best_option("R1"))
ok("13. never stale: after a write the next card builds it again", read_cache.STATS["builds"] == _b5 + 1
   and db.data_version() != _db_v)

# =========================================================================== #
#  14. The card answers its own route first (17 Nov 2026, the frontier check)  #
# =========================================================================== #
# John, 17 Nov 2026: "All as recommended" (F3). After any write the first card waited for all the routes (29 to 37 s on
# live); one route on its own read cost 5.6 to 6.8 s there. While the table is not held, the card's read works out its
# own route and keeps it in ONE slot; the warm-up builds the table, and the card reads that once it is held.
read_cache.clear()
_tab14 = main._best_table(datetime.date.today())
_by14 = {r["route"]: r for r in _tab14["routes"]}
read_cache.clear()
_one14 = {rid: _as(_ADMIN, lambda rid=rid: main.route_best_option(rid)) for rid in ("R1", "R2", "R3", "R4", "R5")}
_ONE14 = getattr(main, "BEST_ONE", "?")             # a plain failure, not a crash, against a main.py without the slot
_held14 = getattr(main, "_best_table_held", lambda d: "?")
ok("⭐ 14. a route worked out on its own is the table's own answer for it, for every route (answer, option, why, counts)",
   all(_one14[rid]["route"] == _by14[rid] for rid in _by14)
   and all(_one14[rid]["checks"] == _tab14["checks"] and _one14[rid]["thresholds"] == _tab14["thresholds"]
           and _one14[rid]["day"] == _tab14["day"] for rid in _by14),
   str([rid for rid in _by14 if _one14[rid]["route"] != _by14[rid]]))
ok("⭐ 14. ONE slot: five routes asked for leave one kept entry, the last, and no table",
   sum(1 for (n, _t) in read_cache._STORE if n == _ONE14) == 1
   and read_cache.peek(_ONE14, (datetime.date.today().isoformat(), "R5")) is not None
   and read_cache.peek(_ONE14, (datetime.date.today().isoformat(), "R1")) is None
   and _held14(datetime.date.today()) is None)
_b14 = read_cache.STATS["builds"]
try:
    _as(_ADMIN, lambda: main.route_best_option("NOPE"))
    _nf14 = None
except _HTTPException as e:
    _nf14 = e.status_code
ok("14. an unknown route with no table held is a 404", _nf14 == 404)
_b14b = read_cache.STATS["builds"]
try:
    main.route_best_option("R1")
    _open14 = True
except _HTTPException as e:
    _open14 = e.status_code != 401
ok("⭐ 14. the wall first: with no sign-in the read is refused and nothing is worked out",
   _open14 is False and read_cache.STATS["builds"] == _b14b)
read_cache.WARMERS["best_option"]()
_b14c = read_cache.STATS["builds"]
_c14 = _as(_PLAN, lambda: main.route_best_option("R3"))
ok("⭐ 14. once the warm-up has built the table the card reads the table (no build), whatever the slot holds",
   read_cache.STATS["builds"] == _b14c and _c14["route"] == _by14["R3"]
   and _held14(datetime.date.today()) is not None)
db.bump_data_version()
_b14d = read_cache.STATS["builds"]
_c14w = _as(_ADMIN, lambda: main.route_best_option("R5"))
ok("14. after a write neither the table nor the slot is served: the card works its route out again (one build, no table)",
   read_cache.STATS["builds"] == _b14d + 1 and _c14w["route"]["route"] == "R5"
   and _held14(datetime.date.today()) is None)
_ep14 = _m.split('@app.get("/api/routes/{route_id}/best-option")')[1].split("\n@app")[0]
ok("14. source: the card's read never builds the table itself (peek, then its own route), and the admin read still does",
   "_best_table_held(d)" in _ep14 and "_best_one(route_id, d)" in _ep14 and "_best_table(d)" not in _ep14
   and "return _best_table(d)" in _f and "read_cache.peek(" in _m.split("def _best_table_held(")[1].split("\ndef ")[0])

# 15. 17 Nov 2026 (route option labels; test_route_option_labels.py has the words): the card's read carries `lines`
# for a real route: the line in use first, then one entry for each option the rule judged, by number
for _c15 in (_c14, _c14w):
    _r15 = _c15["route"]
    ok(f"⭐ 15. {_r15['route']}: the card's read carries the labels for the map: the line in use first, then an entry an option",
       bool(_r15.get("lines")) and _r15["lines"][0]["state"] == "in_use" and _r15["lines"][0]["name"] == "In use"
       and _r15["lines"][0]["words"].endswith(" min")
       and [x["alt"] for x in _r15["lines"][1:1 + len(_r15["options"])]] == sorted(o["alt"] for o in _r15["options"])
       and all(set(x) == {"alt", "return_alt", "name", "words", "state"} for x in _r15["lines"]), _r15.get("lines"))

# 16. 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the WORDS changed and no DECISION
# did. Every case this harness makes (R1 to R5, the typed combinations, the demo and live shapes, the admin table) is
# reduced to what the rule decided: the answer's kind, the option, its alt, and for every option its heads, parts,
# chosen / traded / n5 and whether it was ruled out. The digest was written by this same section running on the rule
# as it stood before the rewording (`main` 87c52b7, its route_best.py put in place for one run with
# WS_WRITE_DECISIONS=1), and is compared here; a change to the rule's DECISIONS is a change to this fixture, made on
# purpose and said in its PR.
_KIND = {RB.SUGGESTED: "suggested", RB.KEEP: "keep", "A trade-off": "planner", "Planner to decide": "planner"}


def _decided(x):
    if not isinstance(x, dict) or "answer" not in x:
        return None
    return {"route": x.get("route"), "answer": _KIND.get(x["answer"], x["answer"]), "option": x.get("option"),
            "alt": x.get("alt"),
            "options": [{"alt": o.get("alt"), "label": (o.get("label") or "").replace("Way round", "Diversion"),
                         "heads": {k: o["heads"].get(k) for k in sorted(o.get("heads") or {})},
                         "parts": {k: o["parts"].get(k) for k in sorted(o.get("parts") or {})},
                         "chosen": bool(o.get("chosen")), "traded": bool(o.get("traded")), "n5": bool(o.get("n5")),
                         "ruled_out": bool(o.get("ruled_out"))} for o in (x.get("options") or [])]}


_cases16 = {"R1": R1, "R2": R2, "R2_out": R2_out, "R3": R3, "R1g": R1g, "R5": R5, "D003": D003, "D027": D027,
            "D031": D031, "D003g": D003g, "D001": D001, "D036": D036, "D006": D006, "L001": L001, "L003": L003,
            "L036": L036}
_cases16.update({f"GEN{i}": g for i, g in enumerate(GEN)})
_cases16.update({f"TAB:{r['route']}": r for r in TAB["routes"]})
_dig16 = {k: _decided(v) for k, v in _cases16.items() if _decided(v) is not None}
_fx16 = os.path.join(ROOT, "backend", "tests", "fixtures", "route_best_decisions_1124.json")
if os.environ.get("WS_WRITE_DECISIONS") == "1":
    with open(_fx16, "w", encoding="utf-8", newline="\n") as f_:
        f_.write("{\n" + ",\n".join(json.dumps(k) + ": " + json.dumps(v, sort_keys=True, ensure_ascii=False,
                                                                       separators=(",", ":"))
                                       for k, v in sorted(_dig16.items())) + "\n}\n")
_old16 = json.load(open(_fx16, encoding="utf-8")) if os.path.exists(_fx16) else {}
_moved16 = [k for k in sorted(set(_old16) | set(_dig16)) if _old16.get(k) != _dig16.get(k)]
ok("⭐ 16. the rewording moved no decision: every case's answer, option and every option's heads and parts are the "
   "rule's before the words changed (the fixture, written on main 87c52b7)",
   len(_old16) > 200 and not _moved16, f"{len(_old16)} cases; moved: {_moved16[:5]}")
ok("16. ...the answer keys still total as before (the admin table's totals are keyed by the new words)",
   sorted({v["answer"] for v in _dig16.values()}) == ["keep", "planner", "suggested"]
   and TAB["totals"].get("Planner to decide") == 2 and "A trade-off" not in TAB["totals"], str(TAB["totals"]))
ok("⭐ 16. an answer kept in the older words is read in the new ones (route_best.answer_words); the rule writes only the "
   "new ones",
   RB.answer_words("A trade-off") == "Planner to decide" and RB.answer_words(RB.SUGGESTED) == RB.SUGGESTED
   and RB.TRADE_OFF == "Planner to decide" and RB.ANSWERS == (RB.SUGGESTED, "Planner to decide", RB.KEEP)
   and not [k for k, v in _cases16.items() if isinstance(v, dict) and v.get("answer") == "A trade-off"])
# the old words are gone from every sentence the rule writes (comments may still quote them)
_said16 = []
for _v in _cases16.values():
    if not isinstance(_v, dict):
        continue
    _said16 += [_v.get("why") or "", _v.get("trade") or "", _v.get("trade_short") or "", _v.get("held_back") or ""]
    _said16 += list(_v.get("sentences") or [])
    for _o in _v.get("options") or []:
        _said16 += list(_o.get("sentences") or []) + list(_o.get("ruled_out") or []) + [_o.get("label") or ""]
    _said16 += [f"{x.get('name')} · {x.get('words')}" for x in (_v.get("lines") or [])]
_GONE16 = ("A trade-off", "trade-off", "trades too", "ahead on", "behind on", "Way round", "goods vehicle", "goods-vehicle",
           "Make primary", "Best option", " left turn")
ok("⭐ 16. GONE: no sentence, label or reason the rule writes says 'A trade-off', 'trades', 'ahead on', 'behind on', "
   "'Way round', 'goods vehicle', 'Make primary', 'Best option' or 'left turns' (Q7 to Q9)",
   len(_said16) > 1000 and not [s for s in _said16 if any(g in s for g in _GONE16)],
   [s for s in _said16 if any(g in s for g in _GONE16)][:3])
ok("16. GONE: no long reason joins its gains and losses with ', but' (it is '; ')",
   not [s for s in _said16 if ", but " in s], [s for s in _said16 if ", but " in s][:2])
# the one place the old answer is still written: OLD_ANSWERS, which reads an older copy's words as the new ones
_rbc16 = "\n".join(l.split("#")[0] for l in read("backend/route_best.py").splitlines()
                   if not l.startswith("OLD_ANSWERS = ") and '"""An answer in today' not in l)
ok("16. GONE (source): the rule's code holds none of the old words outside its comments, docstrings and OLD_ANSWERS",
   'OLD_ANSWERS = {"A trade-off": TRADE_OFF}' in read("backend/route_best.py") and not re.search(r'"[^"\n]*(A trade-off|trades too|ahead on|behind on|Way round|goods vehicle over|goods-vehicle)[^"\n]*"',
                 _rbc16.split('"""', 2)[-1]))
_all_short16 = [x["trade_short"] for x in _cases16.values() if isinstance(x, dict) and x.get("trade_short")]
ok("⭐ 16. Q8: every short line this harness makes is at most SHORT_MAX (25) words; the longest is said",
   _all_short16 and max(len(s.split()) for s in _all_short16) <= RB.SHORT_MAX,
   max(_all_short16, key=lambda s: len(s.split())) if _all_short16 else "")

# =========================================================================== #
#  17. The schedule's rows (25 Nov 2026, the Routes page rethink, cards 4, 5   #
#      and 7; John: "Yes, as recommended", Q11 to Q13)                         #
# =========================================================================== #
# The card and the summary page print route_best.option_rows: one row a measure, its two figures, a mark and the
# difference in words. Every mark must be read from the option's parts, heads and detail as the rule set them (nothing
# new is decided), and a collision row is never ok or warn, never a percentage or a ratio (4c, 4e: kept).
_cases17 = dict(_cases16)
_cases17.update({"R1rr": R1rr, "R1h": R1h, "R1n": R1n, "R4": R4, "R1p": R1p})
_opts17 = [(k, v, o) for k, v in _cases17.items() if isinstance(v, dict) for o in (v.get("options") or [])]
_ORDER17 = ["collisions", "goods", "left_turns", "cycle_meets", "cycle_beside_km", "places", "round_trip", "trips",
            "busy_08:00", "busy_17:00", "busy", "carbon", "limits"]
_KEYS17 = {"key", "label", "sub", "unit", "in_use", "option", "in_use_text", "option_text", "mark", "words", "bars", "none"}
_bad17 = []
for k, v, o in _opts17:
    rows = o.get("rows")
    if o.get("ruled_out"):
        if rows is not None:
            _bad17.append((k, o["label"], "a ruled-out option has rows"))
        continue
    if not isinstance(rows, list) or not rows:
        _bad17.append((k, o["label"], "no rows"))
        continue
    keys = [x["key"] for x in rows]
    if keys != [x for x in _ORDER17 if x in keys] or len(set(keys)) != len(keys):
        _bad17.append((k, o["label"], "order", keys))
    for x in rows:
        if set(x) != _KEYS17 or x["mark"] not in RB.ROW_MARKS:
            _bad17.append((k, o["label"], "shape", x))
        if x["none"] is not None and (x["bars"] is not None or x["in_use"] is not None):
            _bad17.append((k, o["label"], "a 'none' row with figures", x["key"]))
        if x["mark"] in ("ok", "warn") and not x["words"]:
            _bad17.append((k, o["label"], "a mark with no words", x["key"]))
        if x["mark"] == "none" and x["none"] is None and x["words"] != RB.ROW_SAME:
            _bad17.append((k, o["label"], "'the same' missing", x["key"]))
ok("⭐ 17. every option left in has its rows in the card's order and shape; a ruled-out option has none",
   len(_opts17) > 300 and not _bad17, _bad17[:3])

# the marks follow the rule's own steps, row by row
_MK17 = {1: "ok", -1: "warn", 0: "none", None: "off"}
_mis17 = []
for k, v, o in _opts17:
    if o.get("ruled_out"):
        continue
    R = {x["key"]: x for x in o["rows"]}
    det, pt, hd = o["detail"], o["parts"], o["heads"]
    for key in ("left_turns", "cycle_meets", "cycle_beside_km"):
        if key in R:
            want = _MK17[det["cycle_measures"].get(key)] if pt.get("cycle") is not None else "off"
            if R[key]["mark"] != want:
                _mis17.append((k, o["label"], key, R[key]["mark"], want))
    if R["places"]["mark"] != (_MK17[det["community_part"]] if pt.get("community") is not None else "off"):
        _mis17.append((k, o["label"], "places"))
    if R["carbon"]["mark"] != _MK17[hd.get("carbon")]:
        _mis17.append((k, o["label"], "carbon"))
    # the time head is exactly the round trip's and the trips' steps put together
    tv = {"ok": 1, "warn": -1, "none": 0}
    if RB.mix([tv[R["round_trip"]["mark"]], tv[R["trips"]["mark"]]]) != hd.get("time"):
        _mis17.append((k, o["label"], "time", R["round_trip"]["mark"], R["trips"]["mark"], hd.get("time")))
    bus = [tv[R[b]["mark"]] for b in ("busy_08:00", "busy_17:00") if b in R]
    if (RB.mix(bus) if bus else None) != hd.get("busy") or (not bus and "busy" not in R):
        _mis17.append((k, o["label"], "busy"))
    # the cycle part is the three cycle rows' steps put together, as the rule mixes them
    if pt.get("cycle") is not None and RB.mix([tv[R[c]["mark"]] for c in ("left_turns", "cycle_meets", "cycle_beside_km")
                                               if c in R]) != pt["cycle"]:
        _mis17.append((k, o["label"], "cycle part"))
ok("⭐ 17. every mark is the rule's own step for that measure: cycle measures, community, carbon, the two halves of the "
   "time head (they mix to the head) and each busy hour (they mix to the head); nothing decides again",
   not _mis17, _mis17[:3])

# collisions: plain, two counts and the rule's word; never ok or warn, never a percentage or a ratio
_col17 = [(k, o["label"], x) for k, v, o in _opts17 if not o.get("ruled_out") for x in o["rows"]
          if x["key"] in ("collisions", "goods")]
_colbad17 = [c for c in _col17 if c[2]["mark"] not in ("plain", "off") or c[2]["words"] not in ("", "fewer", "more")
             or "%" in (c[2]["words"] + c[2]["label"] + (c[2]["none"] or "")) or " per " in c[2]["label"]
             or (c[2]["none"] is None and c[2]["bars"] != "grey")]
ok("⭐ 17. GUARD: a collision row is never 'ok' or 'warn', never a percentage, a rate or a ratio, its bars grey and its "
   "words only the rule's 'fewer' / 'more' (4c, 4e kept)", len(_col17) > 300 and not _colbad17, _colbad17[:2])
_colw17 = [c for c in _col17 if c[2]["none"] is None and c[2]["words"] != {1: "fewer", -1: "more"}.get(
    next(o for k, v, o in _opts17 if o["label"] == c[1] and k == c[0])["parts"].get(c[2]["key"]), "")]
ok("17. ...and its word is the rule's collision test's ('fewer' only where clearly fewer)", not _colw17, _colw17[:2])
ok("17. GUARD (source): the rows' code writes no percentage on a collision row",
   "p_=" not in read("backend/route_best.py").split("# collisions (4c, 4e)")[1].split("# the cycle measures")[0])
# a percentage only where the rule gives one
_pct17 = []
for k, v, o in _opts17:
    if o.get("ruled_out"):
        continue
    for x in o["rows"]:
        pk = {"left_turns": "left_turns", "cycle_meets": "cycle_meets", "cycle_beside_km": "cycle_beside_km",
              "places": "places"}.get(x["key"])
        has = "%" in x["words"]
        if has != bool(pk and o["pct"].get(pk) and x["mark"] in ("ok", "warn")):
            _pct17.append((k, o["label"], x["key"], x["words"]))
ok("⭐ 17. a percentage only where the rule gives one and the row is marked (4f: a base under 5 is counts alone)",
   not _pct17, _pct17[:3])

# the history and the checks the rows say in words
_hist17 = {}
for k, v, o in _opts17:
    if not o.get("ruled_out"):
        _hist17.setdefault((v.get("checks") or {}).get("collision_history"), set()).add(o["rows"][0]["none"])
ok("⭐ 17. collisions out of date or not fetched: one row that says so, no counts and no HGV row",
   _hist17.get("out_of_date") == {RB.ROW_STALE} and _hist17.get("not_fetched") == {RB.NO_HISTORY_WORDS}
   and all(o["rows"][1]["key"] != "goods" for k, v, o in _opts17 if not o.get("ruled_out")
           and (v.get("checks") or {}).get("collision_history") in ("out_of_date", "not_fetched")), str(_hist17))
_lim17 = {x["none"] for o in (R1n.get("options") or []) if not o.get("ruled_out") for x in o["rows"] if x["key"] == "limits"}
ok("17. no road limits held: 'Limits added' reads 'Not checked: …'; with limits held an option left in reads 'None'",
   _lim17 == {RB.ROW_NO_LIMITS} and {x["none"] for o in R1["options"] if not o.get("ruled_out") for x in o["rows"]
                                      if x["key"] == "limits"} == {"None"}, str(_lim17))
_nc17 = [x for o in (R1["options"] or []) if not o.get("ruled_out") for x in o["rows"]
         if x["key"] in ("left_turns", "places")]
ok("17. the community layer not fetched along every option: the cycle and community rows read 'Not counted yet', off",
   R1["checks"]["community_all_options"] is False and _nc17 and all(x["mark"] == "off" and x["words"] == RB.ROW_NOT_COUNTED
                                                                    for x in _nc17))

# live's R001 (24 Nov, the figures card 4 was drawn with): the rows, word for word as drawn
_r17 = {x["key"]: x for x in L001["options"][0]["rows"]}
_want17 = {"collisions": ("165", "97", "plain", "fewer"), "goods": ("12", "5", "plain", ""),
           "left_turns": ("4", "17", "warn", "13 more"), "cycle_meets": ("42", "29", "ok", "31 % fewer"),
           "cycle_beside_km": ("15.81", "14.26", "ok", "10 % less"), "places": ("18", "23", "warn", "28 % more"),
           "round_trip": ("120.3", "143.8", "warn", "23.5 min longer"), "trips": ("4", "3", "warn", "1 fewer"),
           "carbon": ("42.2", "57.8", "warn", "15.6 kg more")}
_got17 = {k: (x["in_use_text"], x["option_text"], x["mark"], x["words"]) for k, x in _r17.items() if x["none"] is None}
ok("⭐ 17. live's R001 (card 4's figures): every row's figures, mark and words as drawn", _got17 == _want17,
   {k: (_got17.get(k), w) for k, w in _want17.items() if _got17.get(k) != w})
ok("17. ...its labels as drawn, the HGV row a sub-row, the busy hours not compared, no limit added",
   [x["label"] for x in L001["options"][0]["rows"]] == [
       "Collisions on the road, 2021–2025", "involving an HGV", "Left-hand turns", "Cycle routes met",
       "km beside a cycle route", "Community: schools, hospitals, health centres", "Round trip, min",
       "Trips a lorry fits a day", "Busy hours", "Carbon, kg CO₂e a trip", "Limits added"]
   and _r17["goods"]["sub"] and _r17["busy"]["none"] == "Not compared: no busy-hour times held for Alt 1."
   and _r17["limits"]["none"] == "None", [x["label"] for x in L001["options"][0]["rows"]])
# busy hours held: a row an hour, the minutes to the nearest half
_busy17 = [(k, o["label"], x) for k, v, o in _opts17 if not o.get("ruled_out") for x in o["rows"]
           if x["key"].startswith("busy_")]
ok("17. busy-hour times held: a row 'Setting off at 08:00' / '17:00' each, its words in half minutes",
   _busy17 and all(x["label"] == "Setting off at " + x["key"][5:] and (x["words"] == RB.ROW_SAME or
                   re.fullmatch(r"\d+(\.5)? min (longer|quicker)", x["words"])) for _, _, x in _busy17),
   [x for _, _, x in _busy17][:2])
# nothing a row says is longer than the rule's short line allows, and no word the 24 Nov renames took out
_txt17 = [t for k, v, o in _opts17 if not o.get("ruled_out") for x in o["rows"]
          for t in (x["label"], x["words"], x["none"] or "")]
ok("17. every row's words at most 15 words and none of the old words (trade, ahead, behind, goods vehicle, left turn, "
   "Way round, People, Places)",
   _txt17 and max(len(t.split()) for t in _txt17) <= 15
   and not [t for t in _txt17 if re.search(r"trade|\bahead\b|\bbehind\b|goods vehicle|\bleft turn|Way round|People|Places", t)],
   max(_txt17, key=lambda t: len(t.split())))

# the rows for the card's own harness (ui_fix_routes_schedule.js): live's R001 and R003 shapes, a stale history, no
# limits held; sorted keys, so a run rewrites the same bytes
def _fx17(v):
    keep = ("route", "answer", "option", "alt", "why", "trade_short", "trade_also", "held_back", "counts_in_use", "checks")
    return dict({k: v.get(k) for k in keep},
                options=[{k: o.get(k) for k in ("alt", "label", "ruled_out", "chosen", "traded", "rows", "return_alt")}
                         for o in v.get("options") or []])
with open(os.path.join(ROOT, "backend", "tests", "fixtures", "route_rows_1125.json"), "w", encoding="utf-8", newline="\n") as f_:
    json.dump({"L001": _fx17(L001), "L003": _fx17(L003), "R1rr": _fx17(R1rr), "R1n": _fx17(R1n), "R2_out": _fx17(R2_out)},
              f_, sort_keys=True, ensure_ascii=False, indent=1)
    f_.write("\n")

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
