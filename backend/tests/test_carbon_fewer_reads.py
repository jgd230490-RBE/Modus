"""
The carbon build reads each table once (11 Nov 2026, X-F1 part 2; card in notes clocs-meeting-1113).

One Dashboard carbon target read ran carbon.scenario two or three times, and each scenario called
network.route_analysis once per route with no shared `pre`: the route, every location, every gate and the route's
geometry rows were read again for every route (and the holding area's location row for every row), about 300
statements on the demo. Now: network.prefetch_analysis_geometry reads every route's geometry rows in ONE statement,
the scenarios of one read share one `pre` (carbon_target.status), carbon.scenario hands it to costlines.lines, and
holding.cycle_minutes takes the location rows route_analysis already holds.

WHAT THIS PROVES
----------------
  * the demo (with stand-in route lines for every route and lorry, and its holding area) answers the carbon target
    read in a handful of statements (one geometry read, no location-by-id read), for the scheme and for a team;
  * the answer is the SAME as with the per-route reads (the old read pattern forced back on): the whole payload, the
    scenarios, the cost lines and every route's figures;
  * prefetch_analysis_geometry: one statement, every route filed (an empty list for a route with no rows, as its own
    read gives), the same rows as each route's own read, a route already read keeps its rows, a second call reads
    nothing;
  * holding.cycle_minutes gives the same minutes with the caller's location rows, and reads nothing then.

WHAT THIS DOES NOT PROVE
------------------------
  * Postgres or live timings (checked on live after the merge, read only); real HERE lines (the byte-identical check
    on a demo DB copy with route lines is in notes session-1111-carbon-build-fewer-reads.md).

Run:  python backend/tests/test_carbon_fewer_reads.py
"""
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
sys.path.insert(0, HERE)

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

TMP = tempfile.mkdtemp(prefix="wayscope_carbonfew_")
from portable import remove_scratch_db   # noqa: E402
for _v in ("DATABASE_URL", "TENANT_ID", "HERE_API_KEY", "MAPBOX_TOKEN", "IPT1_CODE", "IPT2_CODE", "IPT3_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import access  # noqa: E402
import basemap  # noqa: E402
import read_cache  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL.append(f"{label} {extra}".strip())
        print(f"  FAIL {label} {extra}".rstrip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------- #
#  The demo, imported into a scratch database                                  #
# --------------------------------------------------------------------------- #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
config.invalidate()
_pkg = json.loads(read("demo/uk-corridor.package.json"))
_imp = tenant_package.import_tenant(_pkg, replace=True)
config.invalidate()
ok("the shipped demo imports into the scratch database", bool(_imp.get("ok")), str(_imp)[:200])

ADMIN = {"role": "admin", "label": "Admin", "ipt": None, "via": "login", "kind": "staff"}
PLANNER = {"role": "planner", "label": "Planner", "ipt": None, "via": "login", "kind": "staff"}
TEAM1 = {"role": "ipt", "label": "Team 1", "ipt": "IPT1", "via": "login", "kind": "staff"}
TEAM2 = {"role": "ipt", "label": "Team 2", "ipt": "IPT2", "via": "login", "kind": "staff"}


def as_(acc, fn):
    tok = access._ACCESS.set(acc)
    try:
        return fn()
    finally:
        access._ACCESS.reset(tok)


def stats():
    return dict(read_cache.STATS)




import carbon  # noqa: E402
import carbon_target  # noqa: E402
import costlines  # noqa: E402
import holding  # noqa: E402
import network  # noqa: E402

T = db.current_tenant()

# --------------------------------------------------------------------------- #
#  Stand-in route lines: every route x every lorry its lines use, laden and    #
#  empty legs, a second laden option on every third route, every tenth route   #
#  not baked                                                                   #
# --------------------------------------------------------------------------- #
_routes = db.query("SELECT id FROM routes WHERE tenant_id = ?", (T,))
_rids = sorted(x["id"] for x in _routes)
_vehs = sorted({r["vehicle_type"] for r in db.query("SELECT vehicle_type FROM forecasts WHERE tenant_id = ?", (T,))
                if r.get("vehicle_type")})
for _i, _r in enumerate(_rids):
    if _i % 10 == 9:
        continue
    for _v in _vehs:
        for _leg, _f in (("loaded", 1.0), ("return", 0.9)):
            for _alt in ((0, 1) if (_leg == "loaded" and _i % 3 == 0) else (0,)):
                db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
                           "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (T, _r, _v, _leg, _alt, "[[-1,52.5],[-1.1,52.6]]",
                            round((8 + _i * 1.7) * _f + _alt * 2.5, 2), round((0.2 + _i * 0.03) * _f + _alt * 0.05, 3)))
config.invalidate()
_n_geo = db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ?", (T,))[0]["n"]
ok(f"stand-in route lines seeded ({_n_geo} rows, {len(_rids)} routes, {len(_vehs)} lorry types)",
   _n_geo > 100 and len(_vehs) >= 1)
_hold_ends = [l for l in db.query("SELECT id, holding_id FROM locations WHERE tenant_id = ?", (T,))
              if l.get("holding_id")]
ok("the demo has locations that call off at a holding area (so its minutes are in the figures)", len(_hold_ends) >= 1,
   str(len(_hold_ends)))
ok("the demo holds a carbon target to read progress against", carbon_target.get() is not None)
# the demo's holding area has no check minutes at its gate: give it 12, so its minutes are in every figure below
for _hid in sorted({l["holding_id"] for l in _hold_ends}):
    db.execute("UPDATE location_gates SET safety_minutes = 12 WHERE tenant_id = ? AND location_id = ?", (T, _hid))
ok("the holding area's gate has check minutes", any(float(g.get("safety_minutes") or 0) == 12 for g in db.query(
    "SELECT * FROM location_gates WHERE tenant_id = ?", (T,))))

# --------------------------------------------------------------------------- #
#  Counting statements                                                         #
# --------------------------------------------------------------------------- #
COUNT = {"all": 0, "geom": 0, "loc_by_id": 0, "route_by_id": 0}
_orig_run = db._run


def _run(sql, params, fetch):
    s = " ".join(sql.split())
    COUNT["all"] += 1
    if "FROM route_geometry" in s and "CASE WHEN geometry" in s:
        COUNT["geom"] += 1
    if s.startswith("SELECT * FROM locations WHERE tenant_id = ? AND id = ?"):
        COUNT["loc_by_id"] += 1
    if s.startswith("SELECT * FROM routes WHERE tenant_id = ? AND id = ?"):
        COUNT["route_by_id"] += 1
    return _orig_run(sql, params, fetch)


db._run = _run


def counted(fn):
    for k in COUNT:
        COUNT[k] = 0
    r = fn()
    return r, dict(COUNT)


def canon(x):
    return json.dumps(x, sort_keys=True, default=str)


# --------------------------------------------------------------------------- #
#  1. The carbon target read: a handful of statements                          #
# --------------------------------------------------------------------------- #
print("\n1. the carbon target read")
NEW_ADMIN, c_admin = counted(lambda: as_(ADMIN, lambda: carbon_target.payload(ADMIN)))
NEW_TEAM, c_team = counted(lambda: as_(TEAM1, lambda: carbon_target.payload(TEAM1)))
print("   statements: scheme", c_admin, " team", c_team)
ok("the scheme's read has its figures", (NEW_ADMIN.get("status") or {}).get("approved_t") not in (None, 0))
ok("the scheme's read takes at most 40 statements (was about 300 on the demo)", c_admin["all"] <= 40, str(c_admin))
ok("the team's read takes at most 45 statements (it runs a third scenario on the whole scheme)", c_team["all"] <= 45,
   str(c_team))
ok("the scheme's read reads the route lines ONCE (one statement for every route)", c_admin["geom"] == 1, str(c_admin))
ok("the team's read reads the route lines ONCE too", c_team["geom"] == 1, str(c_team))
ok("no route is read one by one", c_admin["route_by_id"] == 0 and c_team["route_by_id"] == 0, f"{c_admin} {c_team}")
ok("the holding area's location is not read row by row", c_admin["loc_by_id"] == 0 and c_team["loc_by_id"] == 0,
   f"{c_admin} {c_team}")

# --------------------------------------------------------------------------- #
#  2. The same answer as the per-route reads                                   #
# --------------------------------------------------------------------------- #
print("\n2. the same answer as the old per-route reads")
_pf, _cm, _sc, _cl = (network.prefetch_analysis_geometry, holding.cycle_minutes, carbon.scenario, costlines.lines)


def old_reads(fn):
    """The read pattern before 11 Nov: no prefetch, no location rows handed to the holding check, no pre shared
    between the scenarios of one read or with the cost lines."""
    network.prefetch_analysis_geometry = lambda pre: None
    holding.cycle_minutes = lambda *a, locs=None, **k: _cm(*a, **k)
    carbon.scenario = lambda *a, pre=None, **k: _sc(*a, **k)
    costlines.lines = lambda *a, pre=None, **k: _cl(*a, **k)
    try:
        return counted(fn)
    finally:
        network.prefetch_analysis_geometry, holding.cycle_minutes, carbon.scenario, costlines.lines = _pf, _cm, _sc, _cl


OLD_ADMIN, o_admin = old_reads(lambda: as_(ADMIN, lambda: carbon_target.payload(ADMIN)))
OLD_TEAM, o_team = old_reads(lambda: as_(TEAM1, lambda: carbon_target.payload(TEAM1)))
print("   statements with the old pattern: scheme", o_admin, " team", o_team)
ok("the old pattern really is the per-route one (many more statements, a geometry read per route)",
   o_admin["all"] > 3 * c_admin["all"] and o_admin["geom"] > 20, str(o_admin))
ok("the scheme's carbon target answer is identical", canon(NEW_ADMIN) == canon(OLD_ADMIN))
ok("the team's carbon target answer is identical", canon(NEW_TEAM) == canon(OLD_TEAM))
_levers = (carbon_target.get() or {}).get("levers") or []
for _label, _acc, _kw in (("approved plan with the agreed decisions", ADMIN,
                           {"alternatives": [{"name": "T", "levers": _levers}], "status": "Approved"}),
                          ("pending lines", ADMIN, {"status": "Pending"}),
                          ("a team's approved plan", TEAM1, {"status": "Approved"})):
    _new = as_(_acc, lambda: carbon.scenario(_acc, **_kw))
    _old = old_reads(lambda: as_(_acc, lambda: carbon.scenario(_acc, **_kw)))[0]
    ok(f"carbon.scenario, {_label}: identical", canon(_new) == canon(_old))
_new_cl = as_(ADMIN, lambda: costlines.lines(ADMIN))
_old_cl = old_reads(lambda: as_(ADMIN, lambda: costlines.lines(ADMIN)))[0]
ok("the cost lines (Dashboard / Forecasts figures) are identical", canon(_new_cl) == canon(_old_cl))
_pre = {}
_ra_shared = [network.route_analysis(r, pre=_pre) for r in _rids]
_ra_own = old_reads(lambda: [network.route_analysis(r) for r in _rids])[0]
ok("every route's figures are identical, read alone or with one shared pre",
   canon(_ra_shared) == canon(_ra_own) and any(x.get("rows") for x in _ra_own))

# --------------------------------------------------------------------------- #
#  3. prefetch_analysis_geometry                                               #
# --------------------------------------------------------------------------- #
print("\n3. prefetch_analysis_geometry")
_pre = {}
_, _c = counted(lambda: network.prefetch_analysis_geometry(_pre))
ok("one geometry statement (and one for the routes)", _c["geom"] == 1 and _c["all"] == 2, str(_c))
ok("every route of the tenant is filed", set(_pre["geom"]) == set(_rids), str(len(_pre["geom"])))
_same = all(sorted(map(canon, _pre["geom"][r])) == sorted(map(canon, db.query(network.ANALYSIS_GEOMETRY_SQL, (T, r))))
            for r in _rids)
ok("each route's rows are the rows its own read gives (same columns and values)", _same)
_empty = [r for r in _rids if not _pre["geom"][r]]
ok("a route with no lines gets an empty list, as its own read gives", len(_empty) >= 1 and all(
    db.query(network.ANALYSIS_GEOMETRY_SQL, (T, r)) == [] for r in _empty), str(_empty))
_, _c2 = counted(lambda: network.prefetch_analysis_geometry(_pre))
ok("a second call reads nothing", _c2["all"] == 0, str(_c2))
_keep = {"geom": {_rids[0]: ["kept"]}}
network.prefetch_analysis_geometry(_keep)
ok("a route already read keeps its rows", _keep["geom"][_rids[0]] == ["kept"] and len(_keep["geom"]) == len(_rids))
ok("no pre: nothing happens", network.prefetch_analysis_geometry(None) is None)

# --------------------------------------------------------------------------- #
#  4. holding.cycle_minutes with the caller's location rows                    #
# --------------------------------------------------------------------------- #
print("\n4. holding.cycle_minutes")
_locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (T,))}
_rows = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (T,))}
import gates  # noqa: E402
_gbl = gates.gates_by_location()
_tried, _all_same, _free, _nonzero = 0, True, True, 0
for _r in _rows.values():
    _o, _d = _locs.get(_r.get("origin_id")), _locs.get(_r.get("dest_id"))
    if not ((_o or {}).get("holding_id") or (_d or {}).get("holding_id")):
        continue
    for _v in _vehs:
        _tried += 1
        _a = holding.cycle_minutes(_r, _o, _d, _v, gates_by_loc=_gbl)
        _b, _cc = counted(lambda: holding.cycle_minutes(_r, _o, _d, _v, gates_by_loc=_gbl, locs=_locs))
        _all_same = _all_same and _a == _b
        _free = _free and _cc["all"] == 0
        _nonzero += 1 if _a else 0
print(f"   pairs tried {_tried}, with holding minutes {_nonzero}")
ok("routes ending at a location that calls off at a holding area were tried", _tried >= 1, str(_tried))
ok("some of them pay the holding area's minutes (the check is not of zeros)", _nonzero >= 1, str(_nonzero))
ok("the same minutes with the caller's location rows", _all_same)
ok("and no statement then", _free)
_r0 = _rows[_rids[0]]
_fake = {"holding_id": _hold_ends[0]["holding_id"]} if _hold_ends else None
if _fake:
    _a = holding.cycle_minutes(_r0, None, _fake, _vehs[0], gates_by_loc=_gbl)
    _b, _cc = counted(lambda: holding.cycle_minutes(_r0, None, _fake, _vehs[0], gates_by_loc=_gbl, locs={"other": {}}))
    ok("an id not in the caller's rows is read as before", _a == _b and _cc["loc_by_id"] >= 1, str(_cc))

# --------------------------------------------------------------------------- #
#  5. At source                                                                #
# --------------------------------------------------------------------------- #
print("\n5. at source")
ct_src = read("backend/carbon_target.py")
c_src = read("backend/carbon.py")
n_src = read("backend/network.py")
d_src = read("backend/derived.py")
_status = ct_src[ct_src.index("def status("):ct_src.index("def status(") + 4000]
ok("carbon_target.status shares one pre with each of its scenarios",
   "pre = {}" in _status and _status.count("pre=pre)") == 4, str(_status.count("pre=pre)")))
ok("carbon._Geo takes the shared pre and prefetches every route's lines",
   "def __init__(self, pre=None)" in c_src and "network.prefetch_analysis_geometry(self.pre)" in c_src
   and "network.route_analysis(route_id, pre=self.pre)" in c_src and '"geo": _Geo(pre)' in c_src)
ok("carbon.scenario hands its pre to the cost lines", 'pre=ctx["geo"].pre)' in c_src)
ok("route_analysis hands its location rows to the holding check", "gates_by_loc=gates_by_loc, locs=locs)" in n_src
   and "locs=locs)" in n_src[n_src.index("def _turnaround_parts("):n_src.index("def route_analysis(")])
ok("derived.cycle_for prefetches every route's lines into its request's pre",
   d_src.count("network.prefetch_analysis_geometry(pre)") == 2)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
