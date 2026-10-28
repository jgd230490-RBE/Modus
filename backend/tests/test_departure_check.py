"""
The departure check replays the bake (29 Oct 2026, task 0f-1a). John asked (28 Oct) whether a route could take an
alternative in the busy hours for quicker cycle times. The first step is a HERE probe: the same leg at several weekday
hours, asking whether HERE gives the same options at each hour and how their times move.

The app's departure check (GET /api/admin/diagnostics/departure/{route}) could not run that probe as it stood. Since
16 Oct every gate has an access road, and the bake routes each leg through haul.route_with_haul: one HERE call between
the two access roads' road ends, with HERE's alternatives spliced between them (D109). The check still asked plain
here_routing.routes() from the gate points, for one option, so it answered a different request and could never say
which stored option came back.

The change:
  * network.leg_request(): the bake's own resolution of one leg (the ends, the role and gate at each end, the drawn
    roads), shared by _bake_leg and the check, so the two cannot drift;
  * haul.route_with_haul(departure_time=...): the time reaches every HERE call of the leg (plain, between access
    roads, spliced, via). Without a time, the keyword is not even passed: the bake's calls are exactly what they were;
  * the check replays route_with_haul with the bake's ends, roads, permanent zones, laden flag and 3 options. Each
    row lists every option, each named by the STORED option with the same line (`stored_alt`, None = a road not
    stored). The summary reads the times (`time_spread_pct`, `times_read_as`, flat under 2 %) and the options
    (`option_sets_agree`, `quicker_than_first`). `plan=true` makes no HERE call, and the check writes nothing.

WHAT IS ASSERTED
----------------
  * the check's every HERE call has the bake's ends, options, laden flag and avoid areas, on both legs (a one-way site:
    the return leaves by the other gate), the controls send no time, each pinned row its own time, `any` "any";
  * a time reaches every call in every routing mode, and no time means no keyword at all;
  * every option is named by its stored option; a road HERE gives only at one hour reads as not stored and the option
    sets disagree; the hour at which a lower-ranked option is quicker is listed; flat and moving read as such;
  * the counts: calls made = the estimate before the run (one a request between two access roads; more with a haul road
    part way along, where only one option comes back); plan makes no call; nothing is written;
  * the source: _bake_leg and the check both use leg_request; the bake path still sends no departure time (test_phase4
    holds that too); the endpoint passes the options and plan and is admin-gated.

WHAT THIS DOES NOT PROVE
------------------------
HERE is never called. Whether HERE returns the same options at each hour, and how its times move, is what the live
probe (notes/busy-hours-0f-mockup-1028/README.md, 70 calls) is for. No Postgres branch runs.

Run:  python backend/tests/test_departure_check.py
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

# ---- stubs, verbatim from test_gate_access.py ---------------------------------
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

TMP = tempfile.mkdtemp(prefix="wayscope_depcheck_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("TENANT_ID", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import haul  # noqa: E402
import zones  # noqa: E402
import here_routing  # noqa: E402
import limits  # noqa: E402

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


def north(p, m):
    return [p[0], round(p[1] + m / 111320.0, 7)]


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture: a quarry (one gate both ways) and a one-way site (in by the north, #
#  out by the south), each gate 35 m in from its road, and one permanent       #
#  routing closure well away from both (so the avoid areas are not empty)      #
# =========================================================================== #
ART = "Artic Tipper (44t)"
LAT = 52.5
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
RQ = [-1.0, LAT + 0.002]
GQ = north(RQ, -35)
RIN = [-0.9, LAT + 0.002]
GIN = north(RIN, -35)
ROUT = [-0.9, LAT - 0.002]
GOUT = north(ROUT, 35)


def haul_zone(name, coords, **kw):
    z = zones.create_zone(name, {"type": "LineString", "coordinates": coords}, kind=zones.HAUL_KIND, affects_routing=True,
                          speed_kph=kw.pop("speed", 10), haul_mode="splice", **kw)
    assert "error" not in z, z
    return z["id"]


ZQ = haul_zone("Quarry access road", [RQ, GQ])
ZIN = haul_zone("Site in access road", [GIN, RIN])
ZOUT = haul_zone("Site out access road", [ROUT, GOUT])
CLOSURE = zones.create_zone("Bridge closure", {"type": "Polygon", "coordinates": [[[-0.5, 52.0], [-0.5, 52.01],
                                                                                    [-0.49, 52.01], [-0.5, 52.0]]]},
                            kind="closure", affects_routing=True)
gq = gates.create_gate("L1", "Quarry gate", GQ[1], GQ[0], direction="both", is_default=True, access_zone_id=ZQ)
gin = gates.create_gate("L2", "North gate (in)", GIN[1], GIN[0], direction="access", is_default=True, access_zone_id=ZIN)
gout = gates.create_gate("L2", "South gate (out)", GOUT[1], GOUT[0], direction="egress", is_default=True,
                         access_zone_id=ZOUT)
AVOID, ZTAG = network.active_avoid()
ok("fixture: the permanent closure is an avoid area the bake and the check both send", len(AVOID) == 1 and ZTAG,
   f"{AVOID} {ZTAG}")

# =========================================================================== #
#  HERE, faked: up to three options, each its own line; the time of day moves  #
#  the minutes, never the roads, unless a scenario says otherwise              #
# =========================================================================== #
CALLS = []
SC = {"factor": {6: 0.95, 8: 1.10, 12: 1.0, 17: 1.08}, "new_road_at": None, "cross_at": None}
T06, T08, T12, T17 = ("2026-11-10T06:00:00+00:00", "2026-11-10T08:00:00+00:00", "2026-11-10T12:00:00+00:00",
                      "2026-11-10T17:00:00+00:00")


def _hour(dep):
    if not dep or dep == here_routing.TIME_ANY:
        return None
    return int(str(dep)[11:13])


def _fake_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, **kw):
    dep = kw.get("departure_time")
    CALLS.append({"o": (round(o_lat, 7), round(o_lon, 7)), "d": (round(d_lat, 7), round(d_lon, 7)),
                  "alternatives": kw.get("alternatives", 1), "laden": kw.get("laden", True),
                  "avoid": tuple(kw.get("avoid_areas") or ()), "via": kw.get("via"),
                  "has_dep_kw": "departure_time" in kw, "dep": dep})
    h = _hour(dep)
    f = SC["factor"].get(h, 1.0) if h is not None else (0.9 if dep == here_routing.TIME_ANY else 1.0)
    out = []
    for i in range(max(1, int(kw.get("alternatives") or 1))):
        bend = 0.01 * i + (0.007 if (SC["new_road_at"] is not None and SC["new_road_at"] == dep and i == 1) else 0.0)
        mins = (0.25 + 0.05 * i) * f
        if SC["cross_at"] == dep and i == 1:
            mins = 0.20 * f                       # the second option overtakes the first at this hour
        out.append({"geometry": [[o_lon, o_lat], [(o_lon + d_lon) / 2, (o_lat + d_lat) / 2 + bend], [d_lon, d_lat]],
                    "distance_km": 10.0 + i, "duration_hr": round(mins, 4), "sections": []})
    return out


_real_routes, _real_conf = here_routing.routes, here_routing.configured
here_routing.routes = _fake_routes
here_routing.configured = lambda: True
FACT = conversions.load_factors()
BAKE_AT = here_routing.bake_departure_time()      # D94: what every bake and every check below asks for
try:
    R = db.query("SELECT * FROM routes WHERE id = 'R1'")[0]
    L = {l["id"]: l for l in db.query("SELECT * FROM locations")}

    # ---- the bake, both legs, the bake's own avoid set -------------------------------------------------------------
    BAKE = {}
    for leg in network.LEGS:
        CALLS.clear()
        n, e = network._bake_leg(R, L["L1"], L["L2"], ART, leg, FACT, avoid=AVOID, zone_tag=ZTAG)
        BAKE[leg] = list(CALLS)
        ok(f"the bake stores HERE's three options on the {leg} leg", (n, e) == (3, None), f"{n} {e}")
    # 29 Oct 2026 (D94): REVERSED from "the bake sends no departure time at all" (0f-1a): it now sends the pinned hour
    ok("⭐ D94: the bake sends the pinned weekday hour on its HERE call, never 'now' (no call without a time)",
       all(c["has_dep_kw"] and c["dep"] == BAKE_AT for leg in BAKE for c in BAKE[leg]) and all(len(BAKE[l]) == 1 for l in BAKE),
       str([c["dep"] for l in BAKE for c in BAKE[l]]))

    def snapshot():
        return json.dumps(db.query("SELECT * FROM route_geometry ORDER BY route_id, vehicle_profile, leg, alt_index"),
                          sort_keys=True, default=str)

    BEFORE = snapshot()

    # ---- 1. the check replays the bake's request -------------------------------------------------------------------
    D = {}
    for leg in network.LEGS:
        CALLS.clear()
        D[leg] = network.departure_diagnostics("R1", profile=ART, leg=leg, times=[T06, T08, T12, T17])
        D[leg]["_calls"] = list(CALLS)
    for leg in network.LEGS:
        b = BAKE[leg][0]
        calls = D[leg]["_calls"]
        ok(f"⭐ 1. {leg}: every HERE call of the check has the bake's ends, 3 options, laden flag and avoid areas",
           len(calls) == 8 and all((c["o"], c["d"], c["alternatives"], c["laden"], c["avoid"], c["via"])
                                   == (b["o"], b["d"], b["alternatives"], b["laden"], b["avoid"], b["via"]) for c in calls),
           f"{calls[:1]} vs {b}")
        ok(f"1. {leg}: the controls send no time (no keyword), `any` sends 'any', then the bake's own pinned hour, then "
           "each hour asked for, in order", [c["dep"] for c in calls] == [None, "any", BAKE_AT, T06, T08, T12, T17, None]
           and not calls[0]["has_dep_kw"] and not calls[-1]["has_dep_kw"])
    ok("⭐ 1. the one-way site: the check's return leg leaves by the SOUTH gate's road and arrives on the quarry's",
       D["return"]["_calls"][0]["o"] == (ROUT[1], ROUT[0]) and D["return"]["_calls"][0]["d"] == (RQ[1], RQ[0])
       and D["loaded"]["_calls"][0]["o"] == (RQ[1], RQ[0]) and D["loaded"]["_calls"][0]["d"] == (RIN[1], RIN[0]),
       f"{D['return']['_calls'][0]}")
    ok("1. ...the laden flag flips with the leg", D["loaded"]["_calls"][0]["laden"] is True
       and D["return"]["_calls"][0]["laden"] is False)
    ok("1. the report names the leg's drawn roads and says they are the gates' access roads only",
       [s["zone_id"] for s in D["loaded"]["steps"]] == [ZQ, ZIN] and D["loaded"]["access_roads_only"] is True
       and [s["zone_id"] for s in D["return"]["steps"]] == [ZOUT, ZQ])

    # ---- 2. options named by the stored line -----------------------------------------------------------------------
    rows = D["loaded"]["experiment"]["rows"]
    _r08 = next(r for r in rows if r["label"] == T08)
    ok("⭐ 2. every row lists three options, each named by the stored option with the same line (0, 1, 2)",
       len(rows) == 8 and all([o["stored_alt"] for o in r["option_list"]] == [0, 1, 2] for r in rows),
       str([[o["stored_alt"] for o in r["option_list"]] for r in rows]))
    ok("2. ...with each option's km and time, the two 35 m access roads included (HERE's own time beside it)",
       all(r["option_list"][2]["distance_km"] == 12.07 for r in rows)
       and _r08["option_list"][0]["duration_hr_here"] == round(0.25 * 1.10, 4)
       and abs(_r08["option_list"][0]["duration_hr"] - (0.275 + 0.007)) < 0.0006, str(_r08["option_list"][0]))
    ex = D["loaded"]["experiment"]
    ok("⭐ 2. the options agree at every hour; none overtakes the first", ex["option_sets_agree"] is True
       and ex["quicker_than_first"] == [])
    _t = [r["duration_hr"] for r in rows if r["label"] in (T06, T08, T12, T17)]
    ok("⭐ 2. the times are read: the first option's spread over the four hours (06:00 quickest, 08:00 slowest), "
       "read as moving", ex["time_spread_pct"] == round((max(_t) - min(_t)) / min(_t) * 100, 1)
       and ex["time_spread_pct"] > 10 and ex["times_read_as"].startswith("moving"), f"{ex.get('time_spread_pct')} {ex.get('times_read_as')}")
    ok("2. the old road verdict is still there (the same road at every pinned hour)",
       ex["control_stable"] is True and ex["pinned_all_agree"] is True and "does NOT clear" in ex["reads_as"])
    ok("⭐ 2. D94: the stored primary is compared with the answer at the bake's OWN pinned hour (not 'now'): same line, "
       "same km", D["loaded"]["bake_time"] == BAKE_AT and D["loaded"]["cached_reproduces"] is True
       and D["loaded"]["bake_time_is_stored_primary"] is True and D["loaded"]["cached_vs_live_km"] == 0.0)
    ok("2. the stored options are listed with their fingerprints",
       [s["alt_index"] for s in D["loaded"]["stored"]] == [0, 1, 2] and all(s["fingerprint"] for s in D["loaded"]["stored"]))

    # ---- 3. the counts and nothing written ------------------------------------------------------------------------
    ok("⭐ 3. calls made = the estimate before the run: 8 requests (4 hours + the bake's hour + any + 2 controls) x 1 call",
       D["loaded"]["here_calls"] == 8 and D["loaded"]["here_calls_estimate"] == 8 and len(D["loaded"]["_calls"]) == 8)
    ok("⭐ 3. the check writes nothing (route_geometry identical, every row)", snapshot() == BEFORE)
    CALLS.clear()
    P = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T08, T17], plan=True)
    ok("⭐ 3. plan=true makes NO HERE call and says what a run would cost (the bake's hour + 2 hours + any + 2 controls = 6)",
       len(CALLS) == 0 and P.get("plan_only") is True and "experiment" not in P and P["here_calls_estimate"] == 6
       and P["times"] == [BAKE_AT, T08, T17] and len(P["stored"]) == 3, str({k: P.get(k) for k in ("plan_only", "here_calls_estimate")}))
    ok("3. options are capped at the bake's three; one asked for gives one",
       network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T08], alternatives=9, plan=True)["alternatives"] == 3
       and len(network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T08], alternatives=1)
               ["experiment"]["rows"][0]["option_list"]) == 1)

    # ---- 4. the readings the probe's rules depend on --------------------------------------------------------------
    SC["new_road_at"] = T08
    X = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T06, T08, T17])["experiment"]
    r08 = next(r for r in X["rows"] if r["label"] == T08)
    ok("⭐ 4. a road HERE gives only at 08:00 reads as not stored, and the option sets disagree",
       [o["stored_alt"] for o in r08["option_list"]] == [0, None, 2] and X["option_sets_agree"] is False)
    SC["new_road_at"] = None
    SC["cross_at"] = T17
    X = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T06, T08, T17])["experiment"]
    ok("⭐ 4. the hour at which an option HERE ranks second is quicker is listed (John's question, measured)",
       X["quicker_than_first"] == [T17], str(X["quicker_than_first"]))
    SC["cross_at"] = None
    SC["factor"] = {6: 1.0, 8: 1.01, 12: 1.0, 17: 1.005}
    X = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T06, T08, T12, T17])["experiment"]
    ok("⭐ 4. a spread under 2 % reads as flat (the stop rule for 0f-2)", 0 < X["time_spread_pct"] < 2.0
       and X["times_read_as"].startswith("flat"), f"{X['time_spread_pct']} {X['times_read_as']}")
    ok("4. the flat line is fixed in code at 2 %", here_routing.FLAT_SPREAD_PCT == 2.0)
    SC["factor"] = {6: 0.95, 8: 1.10, 12: 1.0, 17: 1.08}

    def _boom(*a, **k):
        raise RuntimeError("HERE said 429")
    here_routing.routes = _boom
    X = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T08])
    ok("4. a refused call is a row with its error, never a crash, and no time is read",
       X["experiment"]["rows"][0]["error"] == "HERE said 429" and X["experiment"]["rows"][0]["option_list"] == []
       and X["experiment"]["times_read_as"].startswith("not measured"))
    here_routing.routes = _fake_routes

    # ---- 5. every routing mode carries the time, and none without one -----------------------------------------------
    ZMID = haul_zone("Langton haul road", [[-0.96, LAT], [-0.94, LAT]], speed=20)
    haul.attach("R1", ZMID)
    STEPS = haul.leg_steps("R1", [GQ[0], GQ[1]], [GIN[0], GIN[1]], "loaded", gq, gin)
    VIA = [dict(s, mode="via") for s in STEPS if s["zone_id"] == ZMID]
    cases = {"no drawn road": [], "between access roads": [s for s in STEPS if s["zone_id"] != ZMID],
             "a haul road part way (spliced)": STEPS, "via": VIA}
    for name, st in cases.items():
        CALLS.clear()
        haul.route_with_haul(GQ[1], GQ[0], GIN[1], GIN[0], ART, st, factors=FACT, alternatives=3)
        none_ok = CALLS and all(not c["has_dep_kw"] for c in CALLS)
        CALLS.clear()
        haul.route_with_haul(GQ[1], GQ[0], GIN[1], GIN[0], ART, st, factors=FACT, alternatives=3, departure_time=T08)
        ok(f"⭐ 5. {name}: no time = no keyword on any call; a time reaches EVERY call ({len(CALLS)})",
           none_ok and CALLS and all(c["dep"] == T08 for c in CALLS))
    CALLS.clear()
    M = network.departure_diagnostics("R1", profile=ART, leg="loaded", times=[T08, T17])
    ok("⭐ 5. with a haul road part way along, one option comes back (as the bake), two calls a request, and the "
       "estimate equals what was spent", all(len(r["option_list"]) == 1 for r in M["experiment"]["rows"])
       and all(r["here_calls"] == 2 for r in M["experiment"]["rows"]) and M["here_calls"] == 12
       and M["here_calls_estimate"] == 12 and len(CALLS) == 12 and M["access_roads_only"] is False,
       f"{M.get('here_calls')} {M.get('here_calls_estimate')} {len(CALLS)}")
    haul.detach("R1", ZMID)

    # ---- 7. D94: the bake's answers say which hour they asked for ---------------------------------------------------
    CALLS.clear()
    BR = network.bake_route("R1", profile=ART)
    ok("⭐ 7. bake_route says the pinned hour it asked for, and every HERE call of it carried that hour",
       BR.get("departure_time") == BAKE_AT and CALLS and all(c["dep"] == BAKE_AT for c in CALLS), str(BR.get("departure_time")))
    network.clear_geometry(profile=ART, route_id="R1")
    CALLS.clear()
    BB = network.bake_batch(profile=ART, limit=10)
    ok("⭐ 7. bake_batch (Route all) the same: one pinned hour for the whole batch, on every call",
       BB.get("departure_time") == BAKE_AT and BB.get("baked") == 2 and all(c["dep"] == BAKE_AT for c in CALLS),
       str({k: BB.get(k) for k in ("baked", "departure_time", "errors")}))
finally:
    here_routing.routes, here_routing.configured = _real_routes, _real_conf

# ---- 7. the pinned time, worked out --------------------------------------------------------------------------------
import datetime as _dt  # noqa: E402
_UTC = _dt.timezone.utc
ok("⭐ 7. D94: the pinned time is the next Tuesday at least two days ahead, 10:00 local (GB, winter: +00:00)",
   here_routing.bake_departure_time(now=_dt.datetime(2026, 10, 28, 21, 30, tzinfo=_UTC), country="GB") == "2026-11-03T10:00:00+00:00"
   and here_routing.bake_departure_time(now=_dt.datetime(2026, 11, 2, 9, 0, tzinfo=_UTC), country="GB") == "2026-11-10T10:00:00+00:00"
   and here_routing.bake_departure_time(now=_dt.datetime(2026, 11, 1, 12, 0, tzinfo=_UTC), country="GB") == "2026-11-03T10:00:00+00:00")
ok("7. ...in summer the same clock time (10:00 BST is +01:00), and UTC where the country has no known zone",
   here_routing.bake_departure_time(now=_dt.datetime(2026, 7, 1, 12, 0, tzinfo=_UTC), country="GB") == "2026-07-07T10:00:00+01:00"
   and here_routing.bake_departure_time(now=_dt.datetime(2026, 10, 28, 12, 0, tzinfo=_UTC), country="") == "2026-11-03T10:00:00+00:00")
ok("7. the pin is stated in code: Tuesday, 10:00, two days ahead",
   (here_routing.BAKE_WEEKDAY, here_routing.BAKE_HOUR, here_routing.BAKE_LEAD_DAYS) == (1, 10, 2))
_net = read("backend/network.py")
ok("7. all three bakes (Route all, one route, the ways round) resolve one pinned time and pass it to every leg",
   _net.count("depart = here_routing.bake_departure_time()") == 3 and _net.count("depart_at=depart)") == 3)

_ug, _tg = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
ok("7. the user guide says it in plain words (no supplier); the technical guide has the detail",
   "Every route is worked out for a weekday at 10:00, so the result does not depend on when you press it." in _ug
   and 'id="t2-bake-hour"' in _tg and "bake_departure_time" in _tg and "plan=true" in _tg)

ok("an unknown leg and route are refused in words",
   network.departure_diagnostics("R1", leg="sideways")["error"].startswith("leg must be one of")
   and network.departure_diagnostics("R999")["error"] == "route not found")

# =========================================================================== #
#  6. Source                                                                   #
# =========================================================================== #
net = read("backend/network.py")
_bake = net.split("def _bake_leg(")[1].split("\ndef ")[0]
_diag = net.split("def departure_diagnostics(")[1].split("\ndef ")[0]
_req = net.split("def leg_request(")[1].split("\ndef ")[0]
ok("⭐ 6. the bake and the check resolve a leg through the one leg_request()",
   "leg_request(r, o, d, leg, gates_by_loc)" in _bake and "leg_request(r, o, d, leg)" in _diag
   and "_waypoint_full" not in _bake and "_waypoint_full" not in _diag)
ok("6. leg_request keeps the return leg as exit-from-dest, entry-to-origin",
   'a, a_role, a_gate = d, "exit", d_gate' in _req and 'b, b_role, b_gate = o, "entry", o_gate' in _req)
ok("⭐ 6. the check replays route_with_haul with the time; the bake sends only the pinned one (D94)",
   "haul.route_with_haul(" in _diag and "departure_time=dep" in _diag
   and _bake.count("departure_time=") == _bake.count("departure_time=depart_at") == 2)
_m = read("backend/main.py").split("def diagnostics_departure(")[1].split("\n@app")[0]
ok("6. the endpoint passes the options and plan, and is admin-gated",
   "alternatives: int = network.ALTERNATIVES" in _m and "plan: bool = False" in _m
   and "alternatives=alternatives, plan=plan" in _m and "_check_admin(token)" in _m)
_h = read("backend/haul.py")
ok("6. haul.py passes the time only when there is one (_dep), on all six HERE calls",
   _h.count("**_dep(departure_time)") == 6 and 'return {"departure_time": departure_time} if departure_time else {}' in _h)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
