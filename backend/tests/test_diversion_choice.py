#!/usr/bin/env python3
"""
test_diversion_choice.py — 11 Nov 2026, CLOCS cards B-F3 + B-I2 (branch claude/clocs-b-diversion-choice).

John, 11 Nov 2026, "No limit, then quickest" (reverses the 28 Oct Q3 answer "shortest"): a dated zone's diversion is the
stored option that misses the zone with NO lorry limit below the lorry first, then the QUICKEST (stored duration_hr, the
HERE time at the pinned bake departure), a tie to the shorter, then the lower alt; where every option has a limit below
the lorry, the quickest of them. The Zones list says "+x mi · +y min each way" and a chip counting only the limits the
diversion ADDS over its own main route (John, 11 Nov: "Yes, only new limits"): "No new limit below this lorry" /
"1 new lorry limit · check"; an admin can preview the change and apply it; nothing changes at the merge itself.

  1. pick_key: the order (no limit first, quickest, shorter, alt; no stored time last)
  2. limits_below: below the lorry only, each limit once, a point limit counts, per leg (an empty lorry is lighter);
     limits_added: only those the main line of the same leg does not meet
  3. work_out: the old rule's shortest loses to a limit-free quicker option; no limits held = the quickest
  4. periods(): hr_delta, limits_below and limits_new on each in-use leg (None when no limits are held)
  5. preview() lists the change without writing; refresh_zones() applies it; then preview() is empty
  6. source pins: the dated reversal in route_choice.py, the two admin endpoints, the Zones list's words

WHAT THIS DOES NOT PROVE: HERE is not called (times are typed); Postgres is not run; the real demo routes' picks are in
the session note (a local copy of live's lines, read once); the Zones list in Chrome is the UI audit's and the card's
picture.

Run:  python3 backend/tests/test_diversion_choice.py
"""
import json
import os
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
        self.cookies = {}


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

TMP = tempfile.mkdtemp(prefix="rbe_dvc_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402,F401
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import route_choice  # noqa: E402
import limits  # noqa: E402
import access  # noqa: E402

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
access.set_current("planner123")

ART = "Artic Tipper (44t)"
LAT = 52.5
MAIN = [[-1.0, LAT], [-0.95, LAT], [-0.9, LAT]]
SHORT = [[-1.0, LAT], [-0.95, LAT + 0.004], [-0.9, LAT]]       # alt 1: the shortest, a weight limit on it
SLOW = [[-1.0, LAT], [-0.95, LAT + 0.01], [-0.9, LAT]]         # alt 2: longer, slower
QUICK = [[-1.0, LAT], [-0.95, LAT + 0.02], [-0.9, LAT]]        # alt 3: longest, quicker than 2
BOX = {"type": "Polygon", "coordinates": [[[-0.952, LAT - 0.002], [-0.948, LAT - 0.002], [-0.948, LAT + 0.002],
                                           [-0.952, LAT + 0.002], [-0.952, LAT - 0.002]]]}


def along(line, t0, t1, n=4):
    """Points on the first piece of a line between fractions t0 and t1 (a limit drawn along that road)."""
    (x0, y0), (x1, y1) = line[0], line[1]
    if n == 1:
        return [[x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0]]
    return [[x0 + (x1 - x0) * (t0 + (t1 - t0) * i / (n - 1)), y0 + (y1 - y0) * (t0 + (t1 - t0) * i / (n - 1))]
            for i in range(n)]


def lim(ext, kind, value, geom, gtype="LineString"):
    return {"source": "test", "ext_id": ext, "kind": kind, "value": value, "geom_type": gtype, "geometry": geom,
            "length_m": None, "signed": None, "tags": {}}


DIMS_L = limits.leg_dimensions(ART, "loaded")
DIMS_R = limits.leg_dimensions(ART, "return")
ok("the tipper has a gross weight on both legs, lighter coming back", bool(DIMS_L.get("mass_t") and DIMS_R.get("mass_t")
   and DIMS_R["mass_t"] < DIMS_L["mass_t"]), f"{DIMS_L} {DIMS_R}")
W75 = lim("w75", "weight", 7.5, along(SHORT, 0.4, 0.5))                         # below the lorry both ways
MID = round(((DIMS_L.get("mass_t") or 44) + (DIMS_R.get("mass_t") or 15)) / 2, 1)
WMID = lim("wmid", "weight", MID, along(SHORT, 0.4, 0.5))                       # below the laden lorry only
H3 = lim("h3", "height", 3.0, along(SLOW, 0.45, 0.45, 1)[0], "Point")           # a low bridge on alt 2
H9 = lim("h9", "height", 6.9, along(QUICK, 0.4, 0.5))                           # a high one on alt 3: within
SHARED = lim("sh", "height", 3.0, [-1.0, LAT], "Point")                          # at the start: every line passes it

# =========================================================================== #
#  1. pick_key                                                                 #
# =========================================================================== #
pk = route_choice.pick_key
ok("⭐ 1. an option with no limit below the lorry beats a shorter, quicker one with a limit",
   pk({"km": 9, "hr": 0.4}, 0) < pk({"km": 5, "hr": 0.1}, 1))
ok("⭐ 1. among limit-free options the quicker wins, even when longer", pk({"km": 10, "hr": 0.22}, 0) < pk({"km": 7, "hr": 0.25}, 0))
ok("1. a tie on time goes to the shorter", pk({"km": 7, "hr": 0.25}, 0) < pk({"km": 8, "hr": 0.25}, 0))
ok("1. a full tie is broken by the alt index (min over key + (alt,))",
   min([2, 1], key=lambda x: pk({"km": 7, "hr": 0.25}, 0) + (x,)) == 1)
ok("1. an option with no stored time goes after every timed one", pk({"km": 9, "hr": 0.9}, 0) < pk({"km": 1, "hr": 0}, 0)
   and pk({"km": 9, "hr": None}, 0) > pk({"km": 9, "hr": 0.9}, 0))
ok("1. where every option has a limit, the quickest of them", pk({"km": 9, "hr": 0.2}, 3) < pk({"km": 5, "hr": 0.3}, 1))

# =========================================================================== #
#  2. limits_below                                                             #
# =========================================================================== #
lb = route_choice.limits_below
ok("⭐ 2. a 7.5 t limit along the line is below the laden tipper", lb(SHORT, ART, "loaded", [W75]) == 1)
ok("2. ...and below the empty one coming back", lb(list(reversed(SHORT)), ART, "return", [W75]) == 1)
ok("⭐ 2. a limit between the empty and the laden weight counts on the laden leg only",
   lb(SHORT, ART, "loaded", [WMID]) == 1 and lb(list(reversed(SHORT)), ART, "return", [WMID]) == 0, f"{MID}")
ok("2. the same limit listed twice counts once", lb(SHORT, ART, "loaded", [W75, dict(W75)]) == 1)
ok("2. a point limit (a low bridge) counts", lb(SLOW, ART, "loaded", [H3]) == 1)
ok("2. a limit above the lorry (6.9 m) does not", lb(QUICK, ART, "loaded", [H9]) == 0)
ok("2. a limit on another road does not", lb(MAIN, ART, "loaded", [W75, H3]) == 0)
ok("2. no limits held / no line = 0", lb(SHORT, ART, "loaded", []) == 0 and lb(None, ART, "loaded", [W75]) == 0)
la = route_choice.limits_added
ok("⭐ 2. limits_added: the 7.5 t limit on the diversion and not on the main line is new", la(SHORT, MAIN, ART, "loaded", [W75]) == 1)
ok("⭐ 2. ...a limit the main line passes too is not new (below 1, added 0)",
   lb(SHORT, ART, "loaded", [SHARED]) == 1 and lb(MAIN, ART, "loaded", [SHARED]) == 1
   and la(SHORT, MAIN, ART, "loaded", [SHARED]) == 0)
ok("2. ...shared and new together: 1 new of 2 below", lb(SHORT, ART, "loaded", [W75, SHARED]) == 2
   and la(SHORT, MAIN, ART, "loaded", [W75, SHARED]) == 1)
ok("2. ...judged for the leg's weight: the mid limit adds one laden, none empty",
   la(SHORT, MAIN, ART, "loaded", [WMID]) == 1 and la(list(reversed(SHORT)), list(reversed(MAIN)), ART, "return", [WMID]) == 0)
ok("2. ...a limit only the main line passes adds nothing (the diversion leaves it)", la(SHORT, MAIN, ART, "loaded",
   [lim("m1", "weight", 7.5, along(MAIN, 0.4, 0.5))]) == 0)

# =========================================================================== #
#  3. work_out                                                                 #
# =========================================================================== #
ZONE = {"id": "Z1", "name": "Mill bridge closure", "geometry": BOX, "starts_on": "2027-01-01", "ends_on": "2027-03-31",
        "affects_routing": True, "kind": "closure"}


def opts(rev=False):
    f = (lambda l: list(reversed(l))) if rev else (lambda l: l)
    return {0: {"line": f(MAIN), "km": 7.0, "hr": 0.20, "avoids": []},
            1: {"line": f(SHORT), "km": 7.2, "hr": 0.21, "avoids": []},
            2: {"line": f(SLOW), "km": 9.0, "hr": 0.30, "avoids": []},
            3: {"line": f(QUICK), "km": 10.0, "hr": 0.24, "avoids": []}}


LINES = {("R1", ART, "loaded"): opts(), ("R1", ART, "return"): opts(True)}


def pick(lims, leg="loaded", lines=None):
    rows = route_choice.work_out(zs=[ZONE], lines=lines or LINES, keep={}, lims=lims)
    r = [x for x in rows if x["leg"] == leg]
    return (r[0]["alt_index"], r[0]["status"], r[0]["km_delta"]) if r else (None, None, None)


ok("3. the main line crosses the zone and every alternative misses it",
   all(zones.line_hits_geometry(o["line"], BOX) == (a == 0) for a, o in opts().items()))
got = pick([W75, H3])
ok("⭐ 3. a 7.5 t limit on the shortest (alt 1) and a low bridge on alt 2: alt 3, limit-free and quickest of the rest",
   got == (3, "in_use", 3.0), str(got))
ok("🔴 3. the old rule (shortest) would have taken alt 1: the pick moved off it",
   got[0] != min((1, 2, 3), key=lambda x: (opts()[x]["km"], opts()[x]["hr"], x)))
ok("⭐ 3. no limits held: the quickest (alt 1, 0.21 h)", pick([])[:2] == (1, "in_use"), str(pick([])))
ok("3. only alt 1 limited: alt 3 (0.24 h) before alt 2 (0.30 h)", pick([W75])[0] == 3, str(pick([W75])))
ok("⭐ 3. a limit below the laden lorry only: laden leg alt 3, the empty return keeps alt 1",
   pick([WMID])[0] == 3 and pick([WMID], "return")[0] == 1, f"{pick([WMID])} {pick([WMID], 'return')}")
ALL = [W75, H3, lim("w3", "weight", 7.5, along(QUICK, 0.4, 0.5))]
ok("⭐ 3. every option limited: the quickest of them (alt 1)", pick(ALL)[0] == 1, str(pick(ALL)))
SLOWQ = {("R1", ART, "loaded"): {0: opts()[0], 1: dict(opts()[1], hr=0.40), 2: opts()[2], 3: opts()[3]}}
ok("🔴 3. no limits held, the shortest is the slowest: the quickest (alt 3) wins, not the shortest",
   pick([], lines=SLOWQ)[0] == 3, str(pick([], lines=SLOWQ)))
TIE = {("R1", ART, "loaded"): {0: opts()[0], 2: dict(opts()[2], hr=0.24), 3: opts()[3]}}
ok("3. a tie on time (0.24 h): the shorter (alt 2, 9 km)", pick([], lines=TIE)[0] == 2, str(pick([], lines=TIE)))
FULL = {("R1", ART, "loaded"): {0: opts()[0], 2: dict(opts()[3]), 3: opts()[3]}}
ok("3. a full tie: the lower alt", pick([], lines=FULL)[0] == 2)
ok("3. km_delta is still the option's distance less the main line's", pick([W75, H3])[2] == 3.0)
ok("3. a limit every option passes (at the quarry gate) leaves no option limit-free: the quickest (alt 1), as the demo's "
   "return legs do", pick([W75, H3, SHARED])[0] == 1, str(pick([W75, H3, SHARED])))

# =========================================================================== #
#  4–5. The stored rows: periods(), preview(), refresh                         #
# =========================================================================== #
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
for leg, rev in (("loaded", False), ("return", True)):
    for a, o in opts(rev).items():
        network._upsert_geom("R1", ART, json.dumps(o["line"]), o["km"], o["hr"], None, leg=leg, alt_index=a,
                             zones_applied="", haul_zones="", avoids=None)
z = zones.create_zone("Mill bridge closure", BOX, kind="closure", starts_on="2027-01-01", ends_on="2027-03-31")
ZID = (z or {}).get("id") or ((z or {}).get("zone") or {}).get("id")
ok("4. the dated zone is stored and dated", any(d["id"] == ZID for d in route_choice.dated_zones()), str(z)[:200])

HELD = [W75, H3, SHARED]
_real_load = route_choice._load_limits
route_choice._load_limits = lambda: list(HELD)
# the rows as the OLD rule wrote them (shortest: alt 1 both legs), as live holds them until applied
for r in route_choice.work_out(lims=[]):
    db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, "
               "reason_kind, reason_ref, status, source, km_delta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'zone', ?, ?, 'auto', ?)",
               (db.current_tenant(), r["id"], r["route_id"], r["vehicle_profile"], r["leg"], r["alt_index"],
                r["starts_on"], r["ends_on"], r["reason_ref"], r["status"], r["km_delta"]))


def stored_alts():
    return sorted((r["leg"], r["alt_index"]) for r in db.query("SELECT leg, alt_index FROM route_choice WHERE tenant_id = ?",
                                                                 (db.current_tenant(),)))


ok("4. the stored rows hold alt 1 (as the shortest rule left them)", stored_alts() == [("loaded", 1), ("return", 1)],
   str(stored_alts()))

P = route_choice.periods("R1")
legs = {l["leg"]: l for g in P for l in g["legs"]}
ok("⭐ 4. periods(): each in-use leg carries hr_delta (stored time less the main line's)",
   abs((legs.get("loaded") or {}).get("hr_delta", 9) - 0.01) < 1e-6, str(legs.get("loaded")))
ok("⭐ 4. ...and limits_below: alt 1 has the 7.5 t limit and the shared low bridge", (legs.get("loaded") or {}).get("limits_below") == 2,
   str(legs.get("loaded")))
ok("⭐ 4. ...and limits_new: only the 7.5 t limit is new (the main route passes the bridge too)",
   (legs.get("loaded") or {}).get("limits_new") == 1, str(legs.get("loaded")))
ok("4. periods() shows what is STORED (alt 1), whichever rule picked it", (legs.get("loaded") or {}).get("alt_index") == 1)
route_choice._load_limits = lambda: []
l0 = ([l for g in route_choice.periods("R1") for l in g["legs"] if l["leg"] == "loaded"] or [{}])[0]
ok("⭐ 4. no limits held: limits_below and limits_new are None (no chip claims a check)", l0.get("limits_below", "x") is None
   and l0.get("limits_new", "x") is None
   and l0.get("hr_delta") is not None, str(l0))
HELD = [W75, H3]                          # the preview: alt 3 limit-free, so the rule moves off alt 1
route_choice._load_limits = lambda: list(HELD)

v0 = db.data_version()
PV = route_choice.preview()
ch = {c["leg"]: c for c in PV["changes"]}
cl = ch.get("loaded") or {}
ok("⭐ 5. preview(): both legs move from alt 1 to alt 3", (cl.get("now") or {}).get("alt_index") == 1
   and (cl.get("rule") or {}).get("alt_index") == 3
   and ((ch.get("return") or {}).get("rule") or {}).get("alt_index") == 3, str(PV)[:400])
ok("5. ...with distance, time and limits for each", (cl.get("now") or {}).get("km_delta") == 0.2
   and abs((cl.get("rule") or {}).get("hr_delta", 9) - 0.04) < 1e-6 and (cl.get("now") or {}).get("limits_below") == 1
   and (cl.get("rule") or {}).get("limits_below") == 0 and (cl.get("now") or {}).get("limits_new") == 1
   and (cl.get("rule") or {}).get("limits_new") == 0, str(cl))
ok("⭐ 5. preview() writes nothing", db.data_version() == v0 and stored_alts() == [("loaded", 1), ("return", 1)])
ok("5. preview() says how many limits it read and the rows on each side",
   PV["limits_held"] == 2 and PV["rows_now"] == 2 and PV["rows_rule"] == 2, str({k: PV[k] for k in PV if k != "changes"}))
route_choice.refresh_zones()
ok("⭐ 5. refresh_zones() (the apply step) stores alt 3 on both legs", stored_alts() == [("loaded", 3), ("return", 3)],
   str(stored_alts()))
ok("5. after it, preview() lists no change", route_choice.preview()["changes"] == [])
route_choice._load_limits = _real_load
ok("5. _load_limits reads the stored limits (limits.stored)", "return limits.stored() or []" in read("backend/route_choice.py"))

# =========================================================================== #
#  6. Source pins                                                              #
# =========================================================================== #
RC = read("backend/route_choice.py")
ok("🔴 6. route_choice.py records the reversal, dated and why", "11 Nov 2026" in RC and '"No limit, then quickest"' in RC
   and "REVERSES the user's Q3 answer of 28 Oct" in RC and "SHORTER than the main route" in RC
   and "weight-limited roads" in RC)
ok("🔴 6. ...and says how quickest is measured, ties and the no-free-option case",
   "here_routing.bake_departure_time" in RC and "on a tie, the shorter" in RC and "the quickest of them is used" in RC)
ok("🔴 6. the shortest-only key is gone", 'key=lambda x: (opts[x]["km"], opts[x]["hr"], x)' not in RC
   and "pick_key(opts[x], below(key, x)) + (x,)" in RC)
M = read("backend/main.py")
for path, fn in (('@app.get("/api/admin/route-diversions/preview")', "route_choice.preview()"),
                 ('@app.post("/api/admin/route-diversions/refresh")', "route_choice.refresh_zones()")):
    i = M.find(path)
    seg = M[i:i + 900] if i >= 0 else ""
    ok(f"🔴 6. {path}: admin only, calls {fn}", i > 0 and "_check_admin(token)" in seg and fn in seg)
FE = read("frontend/index.html")
ok("🔴 6. the Zones list says the time as well (divEach in both layouts)", FE.count("{divEach(p, prof)}") == 2
   and "· ${divMins(hr)}" in FE)
ok("🔴 6. the chip's words (B-I2, only new limits): 'No new limit below this lorry' / '1 new lorry limit · check', tip 'Compared with the main route'",
   '"No new limit below this lorry"' in FE and 'new lorry limit${n === 1 ? "" : "s"} · check' in FE
   and 'title="Compared with the main route"' in FE and '"No limit below this lorry"' not in FE
   and FE.count("<DivLimits p={p} prof={prof} />") == 2)
ok("🔴 6. the chip reads limits_new, not limits_below", "x.limits_new != null" in FE and "map(x => x.limits_new)" in FE
   and "x.limits_below" not in FE)
_dl = FE[FE.find("function DivLimits"):FE.find("function DivLimits") + 500]
ok("6. the chip is the one status chip (RowStatus), amber / green", "<RowStatus" in _dl and 'tone="warn"' in _dl
   and 'tone="ok"' in _dl)

remove_scratch_db(db, TMP)
print(f"test_diversion_choice: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  ✗", f)
sys.exit(1 if FAIL else 0)
