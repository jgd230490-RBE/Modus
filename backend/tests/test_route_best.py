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
  7. stale keys (finding 4): after Make primary the history is "out of date" (by fingerprint, and for an older fetch by the
     audit log), no collision part is counted and nothing is suggested; promoted back, current again; a re-route too;
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
ok("1. labels: the main route, Alt n, a way round", (RB.label(0), RB.label(2), RB.label(10), RB.label(11)) ==
   ("The main route", "Alt 2", "Way round", "Way round 2"))
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
HELD = [W_ALT1, SHARED]
route_choice._load_limits = lambda: list(HELD)

# the closure on R2's main line, in force on DAY
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT2 - 0.002], [-0.948, LAT2 - 0.002], [-0.948, LAT2 + 0.002],
                                           [-0.952, LAT2 + 0.002], [-0.952, LAT2 - 0.002]]]}
_z = zones.create_zone("Mill bridge closure", BOX, kind="closure", starts_on="2027-01-01", ends_on="2027-03-31")
route_choice.refresh_zones()


# collisions: on the road (within 25 m) or beyond it, a few with a goods vehicle over 3.5 t
def rec(cid, routes, goods=False):
    return {"collision_id": cid, "year": 2024, "month": 5, "lon": -0.95, "lat": 52.5, "severity": 3, "road": "A6",
            "road2": None, "junction": None, "road_type": None, "speed_limit": 40, "light": None, "authority": None,
            "n_casualties": 1, "n_vehicles": 2, "vru": [], "vru_ksi": [], "goods": goods, "dist_m": 5, "routes": routes,
            "sites": {}}


RECS, _n = [], [0]


def many(n, routes, goods=0):
    for i in range(n):
        _n[0] += 1
        RECS.append(rec(f"C{_n[0]}", routes, goods=i < goods))


many(23, {"R1": 5}, goods=3)            # the main line: 23 on it, 3 with a goods vehicle
many(8, {"R1@2": 4}, goods=1)           # Alt 2: 8, 1 goods
many(5, {"R1@1": 6})                    # Alt 1: 5
many(4, {"R1": 60, "R1@2": 90})         # near both but on neither (beyond 25 m): never counted
many(20, {"R2@1": 5})                   # R2's diversion (Alt 1): 20
many(30, {"R2": 5})                     # R2's main line: 30 (not in use on DAY)
many(5, {"R2@2": 5})                    # R2 Alt 2: 5
many(23, {"R3": 5})
many(8, {"R3@1": 5})
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
DLAT = 1 / 110574.0
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
ok("⭐ 2. a limit both lines meet (the quarry gate's bridge) does NOT rule an option out",
   o2 and not o2["ruled_out"] and not o2["added_limits"], str(o2 and o2["ruled_out"]))
ok("2. ...though the line in use meets it (it is below this lorry: the old 'any limit' rule would have ruled out every option)",
   len(route_choice._below_keys(bent(LAT1, 0), ART, "loaded", HELD)) == 1)
ok("⭐ 2. R1: Suggested Alt 2 on clearly fewer collisions, the same time and carbon",
   R1["answer"] == RB.SUGGESTED and R1["option"] == "Alt 2" and R1["alt"] == 2
   and o2["heads"] == {"people": 1, "time": 0, "busy": None, "carbon": 0}, f"{R1['answer']} {R1['why']} {o2 and o2['heads']}")
ok("2. the why is a fixed sentence with the two counts", R1["why"].startswith("About a minute quicker a round trip, with fewer "
   "collisions on it (8 against 23)"), R1["why"])
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
   o20 and o20["ruled_out"] and "Mill bridge closure" in o20["ruled_out"][0] and "until 2027-03-31" in o20["ruled_out"][0],
   str(o20 and o20["ruled_out"]))
ok("3. ...and Alt 1 itself is not offered as a change", opt(R2, 1) is None)
ok("⭐ 3. Alt 2 has clearly fewer collisions than the diversion (5 against 20) but is slower: A trade-off, no pick",
   R2["answer"] == RB.TRADE_OFF and R2["option"] is None and o22["heads"]["people"] == 1 and o22["heads"]["time"] == -1
   and R2["trade"].startswith("Alt 2 has fewer collisions on it (5 against 20)") and ", but " in R2["trade"], str(R2["trade"]))
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
   and "it is shorter but slower" in R3["trade"], f"{R3['answer']} {R3['trade']}")
ok("4. its sentences say so", any("is shorter but slower" in s and "so it is never suggested" in s for s in o31["sentences"]))

# =========================================================================== #
#  5. Goods-vehicle counts                                                     #
# =========================================================================== #
ok("⭐ 5. goods-vehicle collisions on the road per option (route_best)",
   (R1["counts_in_use"]["goods"], o2["counts"]["goods"]) == (3, 1) and o2["parts"]["goods"] == 0, str(o2["counts"]))
ok("5. the goods sentence names the goods vehicle and gives the two counts",
   f"Alt 2 had 1 collision involving a goods vehicle over 3.5 t on it against 3 on the route in use, {PERIOD}."
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
network.promote_alternative("R1", ART, 2, leg="loaded")
R1p = run("R1")
keep_words(R1p)
ok("⭐ 7. after Make primary the keys name other lines: 'out of date', no collision part counted, nothing suggested",
   R1p["checks"]["collision_history"] == "out_of_date" and R1p["answer"] != RB.SUGGESTED
   and all(o["parts"]["collisions"] is None and o["parts"]["goods"] is None for o in R1p["options"])
   and any(RB.STALE_WORDS in o["sentences"] for o in R1p["options"]), f"{R1p['answer']} {R1p['held_back']}")
ok("7. ...and the swapped counts are never put in words", not any("had fewer collisions" in s or "had more collisions" in s
                                                                  for o in R1p["options"] for s in o["sentences"]))
write_history(prints=False)        # an older fetch: no fingerprints kept
ok("7. a fetch with no fingerprints and no event since: current (the promote above is not in the audit log)",
   run("R1")["checks"]["collision_history"] == "current")
db.execute("INSERT INTO audit_log (id, tenant_id, at, kind, method, path, status) VALUES ('a1', ?, '2026-11-03T13:00:00+00:00', "
           "'write', 'POST', '/api/admin/routes/R1/promote-alt', 200)", (T,))
ok("⭐ 7. ...with a Make primary in the audit log after the fetch: out of date", run("R1")["checks"]["collision_history"] == "out_of_date")
ok("7. ...on that route only", run("R3")["checks"]["collision_history"] == "current")
db.execute("DELETE FROM audit_log WHERE id = 'a1'")
network.promote_alternative("R1", ART, 2, leg="loaded")       # back as it was searched
write_history(prints=True)
ok("7. promoted back: the lines match the search again, current and Suggested", run("R1")["answer"] == RB.SUGGESTED)
network._upsert_geom("R1", ART, json.dumps(bent(LAT1, -0.011)), 7.2, 0.19, None, leg="loaded", alt_index=2)
ok("⭐ 7. a re-route of one option after the fetch: out of date (by fingerprint)", run("R1")["checks"]["collision_history"] == "out_of_date")
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
   "(21.4 against 20.3 min), N5", D003["answer"] == RB.TRADE_OFF and D003["trade"].startswith("Alt 2 has fewer collisions on it "
   "(8 against 23)") and "it is shorter but slower" in D003["trade"], f"{D003['answer']} {D003['trade']}")
D027 = demo(M(151, 0, 7, 20, 8.61, 9, 73.6, 88.0, 88.0 / 60 + 0.667, 4, 53.5),
            [(1, M(196, 0, 10, 21, 8.98, 8, 82.68, 104.2, 104.2 / 60 + 0.667, 3, 56.3)),
             (2, M(101, 0, 8, 17, 6.21, 8, 92.21, 106.7, 106.7 / 60 + 0.667, 3, 62.8))])
ok("⭐ 10. R027: 'A trade-off' as in the demo (Alt 2 fewer collisions, slower, a trip a day fewer, more carbon)",
   D027["answer"] == RB.TRADE_OFF and D027["option"] is None and "fewer collisions on it (101 against 151)" in D027["trade"]
   and "a lorry fits 3 trips a day, not 4" in D027["trade"], str(D027["trade"]))
D031 = demo(M(24, 0, 5, 1, 0.05, 1, 47.61, 55.3, 55.3 / 60 + 0.667, 0, 28.9),
            [(1, M(50, 0, 5, 1, 0.05, 6, 75.0, 86.3, 86.3 / 60 + 0.667, 0, 43.6)),
             (2, M(32, 0, 6, 1, 0.04, 2, 61.79, 74.5, 74.5 / 60 + 0.667, 0, 46.1))])
ok("⭐ 10. R031: 'Keep the route in use' as in the demo", D031["answer"] == RB.KEEP and D031["why"] ==
   "No other option is clearly ahead on any head.", str(D031["why"]))
D003g = demo(M(23, 0, 5, 3, 2.07, 6, 14.79, 20.3, 1.356, 6, 9.6),
             [(1, M(11, 0, 5, 6, 0.87, 5, 13.31, 23.3, 1.405, 6, 8.0)), (2, M(8, 0, 3, 3, 0.73, 4, 12.84, 21.4, 1.374, 6, 7.5))],
             community_all=True)
ok("10. R003 with the cycle and community parts counted: still 'A trade-off' (N5), with 2 fewer left turns and 2 fewer places",
   D003g["answer"] == RB.TRADE_OFF and "2 fewer left turns" in D003g["trade"]
   and "2 fewer schools, hospitals and health centres passed" in D003g["trade"], str(D003g["trade"]))

# =========================================================================== #
#  11. Words                                                                   #
# =========================================================================== #
_words = [w for w in ALL_WORDS if w]
_low = " ".join(_words).lower()
ok("⭐ 11. never 'safer', 'better', a rate, a ratio, a score or a risk; no supplier; lorry, not truck",
   not any(b in _low for b in ("safer", "better", " rate", "ratio", "score", "risk", "here ", "truck", "exposure")),
   [b for b in ("safer", "better", " rate", "ratio", "score", "risk", "here ", "truck", "exposure") if b in _low])
ok("⭐ 11. no '%' in any sentence about collisions", not any("%" in w for w in _words if "collision" in w.lower()),
   [w for w in _words if "collision" in w.lower() and "%" in w][:2])
ok("11. the words were read from every scenario", len(_words) > 60, str(len(_words)))

# =========================================================================== #
#  12. The admin read                                                          #
# =========================================================================== #
TAB = main.route_options_best(day="2027-02-02", token="best-admin-token")
ok("⭐ 12. the table: every route, a row a (route, option), the thresholds and the checks",
   TAB["day"] == "2027-02-02" and [r["route"] for r in TAB["routes"]] == ["R1", "R2", "R3", "R4"]
   and TAB["thresholds"]["set_by_john"] is False and TAB["checks"]["limits_held"] is True
   and TAB["checks"]["community_all_options"] is False and TAB["checks"]["collision_fingerprints_kept"] is True
   and TAB["totals"] == {RB.SUGGESTED: 1, RB.TRADE_OFF: 2, RB.KEEP: 1, "no_alternative": 1}, str(TAB["totals"]))
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
ok("⭐ 12. a heavy staff read: _staff_json, one Context (one pre, prefetch), placed after _gate_arrivals_build",
   '"/api/admin/route-options/best"' in _m and "_check_admin(token)" in _f and "_staff_json(" in _f
   and "route_best.table(d)" in _f and _m.index("def _gate_arrivals_build(") < _m.index("def route_options_best(")
   and "network.prefetch_analysis_geometry(self.pre)" in _rb)
ok("12. no outside call in the rule (no router, no fetch)", not any(x in _rb for x in ("here_routing.route", "requests.",
                                                                                       "urllib", "fetch_years", "refresh(")))
_tg = read("frontend/help/technical/index.html")
ok("12. the technical guide has the rule's section (the user guide waits for the card)",
   'id="t2-best-option"' in _tg and "/api/admin/route-options/best" in _tg and "searched_prints" in _tg
   and "route-options/best" not in read("frontend/help/index.html"))
_fe = read("frontend/index.html")
ok("12. no screen: the frontend does not read it, and 'Counts only: nothing is scored or ranked' is still on the Routes page",
   "route-options/best" not in _fe and "route_best" not in _fe and "Counts only: nothing is scored or ranked" in _fe)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
