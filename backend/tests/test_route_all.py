"""
Route all without 502s (17 Oct 2026). On live, Data -> Routes -> "Route all" answered 502 on most
30-leg batches and ran about one route a minute. Measured locally (HERE stubbed with real HERE lines
from the live backup of 17 Oct, the demo's 22 routes, 1,631 stored lorry limits): a 30-leg batch took
279 s, and 276 s of it was the stored lorry-limits check (limits.store_checks), run after EVERY leg
and each time over every baked leg of the route, every limit vertex against every route segment.
The HERE stub took 0.15 s, the shared-section rebuild 0.24 s, the council-area clip 0.69 s; the
community and collision strips are not touched by a bake.

The fix, none of it a change in what anyone sees:
  1. limits._LineIndex: the route's segments in a grid, so a limit vertex is measured against the
     few segments near it. The hits are the SAME (asserted here against the brute check).
  2. limits.checks_batched() / check_soon(): a bake checks each route it stored ONCE, at its end.
  3. network.bake_batch(budget_s=...): a batch stops starting legs after BAKE_BUDGET_S (20 s) and
     reports what is left; the endpoint passes it. At least one leg a batch, so it always moves.
  4. The Routes page: one request helper for Route all and the re-route after a zone write; a 502,
     503, 504 or no answer is tried again after 30, 60 and 90 s; the loop stops only when
     `remaining` stops falling (was: a cap of 200 calls).

WHAT IS ASSERTED
----------------
  * the index answers "within X m" exactly as the brute _pt_line_m does, on random lines at 52 and
    60 degrees N, with vertices placed just inside and just outside 12 m and 20 m;
  * check_route gives identical hits with the index and with a brute index, and measures far fewer
    segments;
  * checks_batched: nothing is checked inside the block, each noted route once at its end, nested
    blocks defer to the outermost, a raise still checks; outside a block the check runs at once;
  * bake_batch: one limits check per batch (not per leg), the stored hits equal a fresh check, the
    time budget stops it after the leg that crosses the budget, `remaining` / `attempted` /
    `stopped_for_time` add up, a slow first leg still finishes, a whole Route all bakes every leg
    exactly once; bake_route checks once for both legs;
  * the endpoint passes the budget; the page's request helper (run in node) retries 502 / 503 /
    504 / no answer three times with 30 / 60 / 90 s waits, and never retries a 403 or a 500.

WHAT THIS DOES NOT PROVE
------------------------
  * HERE is never called, and Render is not here: how long a HERE call takes on Render, and what
    Render's own request limit is, are not measured. The budget makes each request short whatever
    they are; the first Route all on live after merging is the check.
  * No Postgres branch runs.

Run:  python backend/tests/test_route_all.py
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_limits.py ---------------------------------------
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

TMP = tempfile.mkdtemp(prefix="wayscope_routeall_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN", "HERE_API_KEY"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import here_routing  # noqa: E402
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


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def boot():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); limits.init_db(); db.init_tenant()
    config.invalidate()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate()


PROFILE = network.DEFAULT_PROFILE
BAL = "Large aggregate / ballast"
KY = 110540.0


def kx(lat):
    return 111320.0 * math.cos(math.radians(lat))


def walk(rng, lon, lat, n, step_m):
    """A wandering line of n vertices, steps of up to step_m, with the odd long straight."""
    pts, h = [[lon, lat]], rng.uniform(0, 2 * math.pi)
    for _ in range(n - 1):
        h += rng.uniform(-0.6, 0.6)
        d = step_m * (8 if rng.random() < 0.03 else rng.uniform(0.2, 1.0))
        lon += d * math.cos(h) / kx(lat)
        lat += d * math.sin(h) / KY
        pts.append([round(lon, 7), round(lat, 7)])
    return pts


def offset_from(line, i, t, d_m, rng):
    """A point d_m from segment i of the line, at fraction t along it, to one side."""
    a, b = line[i], line[i + 1]
    lat = a[1] + t * (b[1] - a[1])
    x, y = (b[0] - a[0]) * kx(lat), (b[1] - a[1]) * KY
    L = math.hypot(x, y) or 1.0
    s = rng.choice((-1, 1))
    px, py = -y / L * d_m * s, x / L * d_m * s
    return [a[0] + t * (b[0] - a[0]) + px / kx(lat), lat + py / KY]


# =========================================================================== #
#  1. The index answers exactly as the brute check                             #
# =========================================================================== #
rng = random.Random(1017)
checks = mism = 0
for lat0 in (52.5, 60.0):
    for k in range(12):
        line = walk(rng, -1.0 + 0.05 * k, lat0, rng.randint(40, 300), rng.choice((15, 60, 250)))
        idx = limits._LineIndex(line, max(limits.MATCH_M, limits.POINT_M))
        probes = []
        for _ in range(60):
            i = rng.randrange(len(line) - 1)
            for d in (0.0, 5.0, 11.9, 12.0, 12.1, 19.9, 20.0, 20.1, 25.0, 60.0, 400.0):
                probes.append(offset_from(line, i, rng.random(), d, rng))
        for p in probes:
            for within in (limits.POINT_M, limits.MATCH_M):
                checks += 1
                if idx.near(p, within) != (limits._pt_line_m(p, line) <= within):
                    mism += 1
ok(f"1. ⭐ the index says 'within 12 m / 20 m' exactly as the brute check ({checks} probes at 52.5 and 60 N, "
   "inside, on and outside both thresholds)", checks > 30000 and mism == 0, f"{mism} differ")
ok("1. along_m keeps its brute answer for its other readers (a crossing ~0, a parallel stretch its length)",
   limits.along_m([[-0.92, 52.499], [-0.92, 52.501]], [[-0.95, 52.5], [-0.85, 52.5]]) == 0.0
   and limits.along_m([[-0.94, 52.50], [-0.936, 52.50]], [[-0.95, 52.5], [-0.85, 52.5]]) > 250)

# =========================================================================== #
#  2. check_route: identical hits, far fewer segments measured                 #
# =========================================================================== #
boot()
q1 = network.create_location("Pit West", "origin", lat=52.50, lon=-0.95, loc_type="Quarry", supplies=[BAL])
d1 = network.create_location("Yard East", "destination", lat=52.53, lon=-0.80, loc_type="Compound", receives=[BAL])
RIDS = [network.create_route(q1["id"], d1["id"], material_category=BAL, route_id=f"R{n:03d}", ipt="IPT1")["id"]
        for n in range(1, 7)]
LINES = {}
for rid in RIDS:
    LINES[rid] = walk(rng, -0.95, 52.50, 400, 60)
# limits: lines along each route (some with a vertex just off it), crossings, points near and far
rows, n = [], 0
CROSSINGS = set()


def lim(kind, value, geom_type, geometry, length_m=None, unit=None):
    global n
    n += 1
    anchor = geometry if geom_type == "Point" else geometry[len(geometry) // 2]
    rows.append({"source": "osm", "ext_id": f"w{n}", "kind": kind, "value": value,
                 "unit": unit or ("t" if kind in ("weight", "axle") else "m"), "signed": None,
                 "geom_type": geom_type, "geometry": geometry, "anchor": anchor, "length_m": length_m,
                 "name": f"Road {n}", "ref": None, "exceptions": None, "tags": {},
                 "fetched_at": "2026-10-17T10:00:00+00:00"})


for rid, line in LINES.items():
    for _ in range(60):
        i = rng.randrange(len(line) - 6)
        d = rng.choice((0.0, 6.0, 19.5, 20.5, 35.0))
        g = [offset_from(line, j, 0.5, d + rng.uniform(-0.4, 0.4), rng) for j in range(i, i + rng.randint(2, 5))]
        lim(rng.choice(("weight", "height", "width")), rng.choice((7.5, 18.0, 4.4, 3.8, 2.0)), "LineString", g,
            length_m=None)
    for _ in range(40):
        i = rng.randrange(len(line) - 1)
        lim("height", rng.choice((3.6, 4.4)), "Point", offset_from(line, i, rng.random(), rng.choice((3.0, 11.8, 12.3, 80.0)), rng))
    for _ in range(15):                 # crossings: a short line square across the route
        i = rng.randrange(len(line) - 1)
        a = offset_from(line, i, 0.5, 40.0, rng)
        b = [2 * line[i][0] - a[0] + (line[i + 1][0] - line[i][0]), 2 * line[i][1] - a[1] + (line[i + 1][1] - line[i][1])]
        lim("height", 3.8, "LineString", [a, b])
        CROSSINGS.add(rows[-1]["ext_id"])
EXT = limits.tenant_extent() or (-1.2, 52.3, -0.5, 52.8)
box = (min(EXT[0], -1.2), min(EXT[1], 52.3), max(EXT[2], -0.5), max(EXT[3], 52.8))
limits.replace_rows("osm", box, rows)
for rid, line in LINES.items():
    network._upsert_geom(rid, PROFILE, json.dumps(line), 40.0, 1.0, None, leg="loaded", alt_index=0)
    network._upsert_geom(rid, PROFILE, json.dumps(list(reversed(line))), 40.0, 1.0, None, leg="return", alt_index=0)
LIMS = limits.stored(box)

SEG = {"n": 0}
_real_seg = limits._pt_seg_m


def counting_seg(p, a, b):
    SEG["n"] += 1
    return _real_seg(p, a, b)


class Brute(limits._LineIndex):
    def __init__(self, line, reach_m):
        self.line = line

    def candidates(self, p):
        return range(len(self.line) - 1)


limits._pt_seg_m = counting_seg
new = {r: limits.check_route(r, _limits=LIMS) for r in RIDS}
seg_new = SEG["n"]; SEG["n"] = 0
_real_index = limits._LineIndex
limits._LineIndex = Brute
old = {r: limits.check_route(r, _limits=LIMS) for r in RIDS}
seg_old = SEG["n"]
limits._LineIndex = _real_index
limits._pt_seg_m = _real_seg
nhits = sum(len(v["hits"]) for v in new.values())
ok(f"2. ⭐ check_route: identical hits with the index and with every segment measured ({nhits} hits on 6 routes, "
   f"{len(LIMS)} limits)", json.dumps(new, sort_keys=True) == json.dumps(old, sort_keys=True) and nhits > 100,
   f"{nhits}")
ok("2. ...the hits include runs along, points and near-misses both sides (not a trivial match)",
   any(h["point"] for v in new.values() for h in v["hits"]) and any(not h["point"] for v in new.values() for h in v["hits"])
   and any(h["leg"] == "return" for v in new.values() for h in v["hits"]))
ok(f"2. ⭐ ...measuring under 2 % of the segments ({seg_new:,} against {seg_old:,})",
   seg_old > 0 and seg_new < 0.02 * seg_old, f"{seg_new} / {seg_old}")
# a wandering line can come back past a crossing's ends, so only the crossings whose ends are both off
# the route count here
_lim_by = {x["ext_id"]: x for x in rows}
_clear = {c for c in CROSSINGS if all(min(limits._pt_line_m(e, LINES[rid]) for rid in RIDS) > limits.MATCH_M
                                      for e in _lim_by[c]["geometry"])}
ok(f"2. the {len(_clear)} crossings with both ends off the route are not hits, though each is ~0 m from it "
   "half-way (the bridge trap holds through the index)",
   len(_clear) >= 60 and not any(h["ext_id"] in _clear for v in new.values() for h in v["hits"]), str(len(_clear)))

# =========================================================================== #
#  3. checks_batched / check_soon                                              #
# =========================================================================== #
CALLS = []
_real_store = limits.store_checks


def counting_store(route_ids=None):
    CALLS.append(list(route_ids) if route_ids else None)
    return _real_store(route_ids)


limits.store_checks = counting_store
with limits.checks_batched():
    limits.check_soon("R002"); limits.check_soon("R001"); limits.check_soon("R002")
    inside = list(CALLS)
ok("3. inside checks_batched nothing is checked; at its end each noted route ONCE, in one call",
   inside == [] and CALLS == [["R001", "R002"]], str(CALLS))
CALLS.clear()
with limits.checks_batched():
    with limits.checks_batched():
        limits.check_soon("R003")
    nested = list(CALLS)
    limits.check_soon("R004")
ok("3. a nested block defers to the outermost", nested == [] and CALLS == [["R003", "R004"]], str(CALLS))
CALLS.clear()
try:
    with limits.checks_batched():
        limits.check_soon("R005")
        raise RuntimeError("boom")
except RuntimeError:
    pass
ok("3. a block that raises still checks what it stored", CALLS == [["R005"]], str(CALLS))
CALLS.clear()
limits.check_soon("R006")
ok("3. outside a block the check runs at once (a single-leg write, as on 13 Oct)", CALLS == [["R006"]])
CALLS.clear()
with limits.checks_batched():
    pass
ok("3. an empty block checks nothing (never the whole network by accident)", CALLS == [])

# =========================================================================== #
#  4. bake_batch: one check a batch, the time budget                           #
# =========================================================================== #
os.environ["HERE_API_KEY"] = "test-key"
CLOCK = [1000.0]
LEG_S = [8.0]
HERE_LEGS = []


def stub_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, avoid_areas=None, alternatives=1,
                laden=True, via=None, pass_through=False, departure_time=None):
    CLOCK[0] += LEG_S[0]
    HERE_LEGS.append((round(o_lat, 5), round(o_lon, 5), laden))
    # the stored route line, reversed for the return, so the limits check has work to do
    line = LINES["R001"] if laden else list(reversed(LINES["R001"]))
    return [{"geometry": [[o_lon, o_lat]] + line + [[d_lon, d_lat]], "distance_km": 40.0, "duration_hr": 1.0,
             "sections": []}]


here_routing.routes = stub_routes
network.time = types.SimpleNamespace(monotonic=lambda: CLOCK[0])
network.clear_geometry()
CALLS.clear()
r = network.bake_batch(profile=PROFILE, limit=30, budget_s=20.0)
ok("4. ⭐ the budget stops the batch after the leg that crosses 20 s (8 s legs: 3 legs, 24 s)",
   r["attempted"] == 3 and r["baked"] == 3 and r["stopped_for_time"] is True and r["seconds"] == 24.0, str(r)[:300])
ok("4. ...and `remaining` is everything not reached (12 legs - 3)", r["remaining"] == 9, str(r["remaining"]))
ok("4. ⭐ one lorry-limits check for the whole batch, for the routes it stored (not one a leg)",
   len(CALLS) == 1 and CALLS[0] == ["R001", "R002"], str(CALLS))
fresh = {rid: limits.check_route(rid) for rid in ("R001", "R002")}
st = limits.stored_checks(["R001", "R002"])
ok("4. the stored hits after the batch equal a fresh check (nothing stale left by deferring it)",
   all(json.dumps(st[rid]["hits"], sort_keys=True) == json.dumps(fresh[rid]["hits"], sort_keys=True) for rid in st)
   and len(st["R001"]["hits"]) > 0)
LEG_S[0] = 100.0
r = network.bake_batch(profile=PROFILE, limit=30, budget_s=20.0)
ok("4. a leg slower than the whole budget still finishes: every batch does at least one",
   r["attempted"] == 1 and r["baked"] == 1 and r["stopped_for_time"] is True and r["remaining"] == 8, str(r)[:200])
LEG_S[0] = 0.5
r = network.bake_batch(profile=PROFILE, limit=4, budget_s=20.0)
ok("4. inside the budget `limit` still governs (4 legs, stopped_for_time False)",
   r["attempted"] == 4 and r["stopped_for_time"] is False and r["remaining"] == 4, str(r)[:200])
r = network.bake_batch(profile=PROFILE, limit=30)
ok("4. no budget passed: as before, `limit` alone (the other callers)", r["attempted"] == 4 and r["remaining"] == 0)
network.clear_geometry()
HERE_LEGS.clear()
LEG_S[0] = 3.0
loops = 0
while True:
    loops += 1
    r = network.bake_batch(profile=PROFILE, limit=30, budget_s=20.0)
    if not r["remaining"] or loops > 50:
        break
legs_now = db.query("SELECT route_id, leg FROM route_geometry WHERE tenant_id = ? AND vehicle_profile = ? "
                    "AND alt_index = 0 AND geometry IS NOT NULL", (db.current_tenant(), PROFILE))
ok("4. ⭐ a whole Route all in short batches bakes every leg exactly once (12 legs, 12 HERE calls, 2 batches of 7 + 5)",
   len(legs_now) == 12 and len(HERE_LEGS) == 12 and loops == 2, f"{len(legs_now)} {len(HERE_LEGS)} {loops}")

CALLS.clear()
network.clear_geometry(route_id="R003")
CALLS.clear()
network.bake_route("R003", profile=PROFILE)
ok("4. bake_route (one route, both legs) checks the route once, at its end", CALLS == [["R003"]], str(CALLS))

src = read("backend/network.py")
ok("4. bake_batch and bake_route run inside _limits_once; the store hook calls check_soon, not store_checks",
   "@_limits_once                                  # 17 Oct 2026: one lorry-limits check a route\n"
   "@road_sections.rebuild_once(\"bake batch\")\ndef bake_batch(" in src
   and re.search(r"@_limits_once[^\n]*\n@road_sections\.rebuild_once\(\"route bake\"\)[^\n]*\ndef bake_route\(", src)
   and "_limits.check_soon(route_id)" in src and "_limits.store_checks([route_id])" not in src)
ok("4. the budget is 20 s, a module constant", network.BAKE_BUDGET_S == 20.0)

# =========================================================================== #
#  5. The endpoint passes the budget                                           #
# =========================================================================== #
seen = {}
_real_batch = network.bake_batch
network.bake_batch = lambda **k: seen.update(k) or {"remaining": 0}
os.environ["ADMIN_TOKEN"] = "adm-test"
main.bake_routes(profile=PROFILE, limit=30, legs=None, token="adm-test")
network.bake_batch = _real_batch
os.environ.pop("ADMIN_TOKEN", None)
ok("5. ⭐ POST /api/admin/bake-routes hands network.BAKE_BUDGET_S to every batch",
   seen.get("budget_s") == network.BAKE_BUDGET_S and seen.get("limit") == 30, str(seen))

# =========================================================================== #
#  6. The page: one request helper, retries, the loop guard                    #
# =========================================================================== #
fe = read("frontend/index.html")
i = fe.index("  const ROUTE_RETRY_S = [30, 60, 90];")
j = fe.index("  // Bulk bake.", i)
helper = fe[i:j]
# 22 Oct 2026 (claude/error-words): the loop now says its failures through the page's error helper (errFrom / errLog),
# so the node run below gets that helper too, sliced the same way (const ERR_WORDS … function errSay)
_eh = fe[fe.index("const ERR_WORDS = {"):fe.index("\n", fe.index("function errSay("))]
bulk = fe[fe.index("const bulkBake = async"):fe.index("const clearRoutes")]
zone = fe[fe.index("const rebakeAfterZone = async"):fe.index("const saveZone = async")]
ok("6. Route all and the re-route after a zone write both go through postRouteBatch",
   "postRouteBatch(q, setRouteMsg)" in bulk and "postRouteBatch(q, setZoneMsg)" in zone
   and "fetch(" not in bulk.split("postRouteBatch")[0][-400:])
ok("6. the batch URL is fetched in ONE place now", fe.count("fetch(`${API}/admin/bake-routes?${q}`") == 1)
ok("6. 🔴 the old 200-call cap is gone from both loops; each stops when `remaining` stops falling",
   "guard++ < 200" not in bulk and "guard++ < 200" not in zone
   and bulk.count("if(left >= last) throw") == 1 and zone.count("if(left >= last) throw") == 1)
ok("6. Route all still refreshes the table after every batch", "await reloadNetwork();\n          if(left <= 0) break;" in bulk)
_say = [ln for ln in helper.splitlines() if "say(`" in ln]
ok("6. the retry words follow the word rule (no server, no bake)",
   len(_say) == 1 and "Wayscope did not answer" in _say[0] and not re.search(r"\bservers?\b|\bbak(e|ed|ing)\b", _say[0]), str(_say))

node = shutil.which("node")
ok("6. node is on the PATH (the suite's JS harnesses need it too)", bool(node))
if node:
    js = _eh + "\n" + helper + r"""
    ;(async () => {
      const out = {};
      const run = async (name, seq) => {
        const waits = [], says = [];
        let calls = 0;
        global.setTimeout = (f, ms) => { waits.push(ms / 1000); f(); };
        global.fetch = async (url, opt) => {
          const s = seq[Math.min(calls++, seq.length - 1)];
          if (s === "net") throw new TypeError("Failed to fetch");
          return { ok: s === 200, status: s, json: async () => ({ remaining: 0, url, method: opt.method }),
                   text: async () => "body " + s };
        };
        try { const j = await postRouteBatch(new URLSearchParams({ profile: "P", limit: "30" }), m => says.push(m));
              out[name] = { ok: true, j, waits, says, calls }; }
        catch (e) { out[name] = { ok: false, err: e.message, waits, says, calls }; }
      };
      await run("502x2", [502, 502, 200]);
      await run("504", [504, 200]);
      await run("503", [503, 200]);
      await run("net", ["net", 200]);
      await run("down", ["net", "net", 502, 503]);
      await run("403", [403]);
      await run("500", [500]);
      console.log(JSON.stringify(out));
    })();
    """
    p = subprocess.run([node, "-e", "const API = '/api';\n" + js], capture_output=True, text=True, timeout=60)
    try:
        R = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        R = {}
        ok("6. the helper runs in node", False, (p.stdout + p.stderr)[-400:])
    if R:
        a = R["502x2"]
        ok("6. ⭐ two 502s then an answer: tried again after 30 s and 60 s, the answer returned",
           a["ok"] and a["calls"] == 3 and a["waits"] == [30, 60] and a["j"]["method"] == "POST"
           and a["j"]["url"].startswith("/api/admin/bake-routes?profile=P&limit=30"), str(a))
        # NARROWED 22 Oct 2026 (claude/error-words): no status number in the words; the why is errWords' sentence
        ok("6. ...and it said so each time, in plain words",
           a["says"] == ["Wayscope did not answer. Trying again in 30 s (1 of 3)…",
                         "Wayscope did not answer. Trying again in 60 s (2 of 3)…"], str(a["says"]))
        ok("6. a 504 and a 503 are tried again too", R["504"]["ok"] and R["504"]["calls"] == 2 and R["503"]["ok"] and R["503"]["calls"] == 2)
        ok("6. no answer at all (a restart during a deploy) is tried again", R["net"]["ok"] and R["net"]["calls"] == 2
           and "did not answer" in R["net"]["says"][0])   # NARROWED 22 Oct 2026 (error-words): was "(no answer)" in brackets
        d = R["down"]
        ok("6. ⭐ after three tries (30, 60, 90 s) it stops and says why; the loop's own message says what is kept",
           not d["ok"] and d["calls"] == 4 and d["waits"] == [30, 60, 90] and d["err"] == "No answer after 4 tries.", str(d))   # NARROWED 22 Oct 2026 (error-words): was "503 — tried 4 times"
        ok("6. 🔴 a 403 is never retried: the admin sentence at once",   # NARROWED 22 Oct 2026 (error-words): was 'admin token rejected'
           not R["403"]["ok"] and R["403"]["calls"] == 1
           and R["403"]["err"] == "Not allowed: sign in as an admin, or type the admin token." and R["403"]["waits"] == [])
        ok("6. 🔴 a 500 (a real fault) is never retried", not R["500"]["ok"] and R["500"]["calls"] == 1   # NARROWED 22 Oct 2026 (error-words): was "500 body 500"
           and R["500"]["err"] == "Wayscope could not do this just now. Try again in a minute.")
ok("6. the loop's stop message still says finished routes are kept and Route all can run again",
   "Routes already worked out are kept, so you can run it again" in bulk)   # NARROWED 22 Oct 2026 (error-words): a sentence of its own now

remove_scratch_db(db, TMP)
print(f"test_route_all.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
