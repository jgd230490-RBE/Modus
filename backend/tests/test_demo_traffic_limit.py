"""
The demo package carries the B6047 traffic limit (11 Nov 2026, card M-F1, John's "Yes, as recommended").

The limit was drawn on live by hand on 11 Nov (zone Z041, the CLOCS meeting's slide 7). Until the package held it, a
live refresh (make_demo_tenant --live-export) refused ("zones differ") and a full re-import would have dropped it.

WHAT IS ASSERTED
----------------
  1. the package: Z041 is the LAST zone and no other id moved (Z001-Z041 in order); a traffic limit, routing off, no
     dates, active, 150 lorry movements a day, average, public; its line is the B6047 from the Cold Newton turn to
     Tilton on the Hill (24 points, about 2.79 km, the generator's constant) and carries no note;
  2. the figures on the generated plan: with stand-in lines for the seven routes live counts on the stretch (every
     loaded leg on it, R021's and R023's way back elsewhere, as live's in / out split shows), Mar 2027 reads NEAR
     (147.3, live 147.35) and Apr 2027 OVER (162.1, live 162.07);
  3. a refresh: a live export whose Z041 has live's own line and another limit is NOT refused, and the output keeps
     live's row (line and limit); one without Z041 (live before 11 Nov), with Z041 dated, or with another zone's shape
     changed is still refused.

WHAT THIS DOES NOT PROVE
------------------------
The stand-in lines are not HERE's (the package carries no route geometry): on live the figures come from the baked
routes. Live itself is not touched; the refresh is John's step (notes\\session-1111-demo-package-b6047.md).

Run:  python3 backend/tests/test_demo_traffic_limit.py
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

# ---- stubs, verbatim from test_zone_diversions_b.py ---------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_mf1_")
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
import zones  # noqa: E402
import route_choice  # noqa: E402
import counting  # noqa: E402
import traffic_limits as TL  # noqa: E402
import datetime as dt  # noqa: E402

import limits  # noqa: E402
import tenant_package  # noqa: E402
import copy as _copy  # noqa: E402
import math  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


PKG = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
ZS = PKG["tables"]["zones"]
Z = ZS[-1] if ZS else {}


def geom_of(z):
    g = z.get("geometry")
    return json.loads(g) if isinstance(g, str) else g


# =========================================================================== #
#  1. The package                                                             #
# =========================================================================== #
ok("1. ⭐ the package's last zone is Z041, the B6047 limit, and no zone id moved (Z001-Z041 in order)",
   [z["id"] for z in ZS] == [f"Z{n:03d}" for n in range(1, 42)]
   and Z.get("name") == "B6047 Melton Road, Cold Newton turn to Tilton on the Hill",
   str([z["id"] for z in ZS[-3:]]))
ok("1. Z041 is a traffic limit as drawn on live: routing off, no dates, active, no note",
   (Z.get("kind"), bool(Z.get("affects_routing")), Z.get("starts_on"), Z.get("ends_on"), bool(Z.get("active")),
    Z.get("note")) == ("traffic_limit", False, None, None, True, None), str({k: Z.get(k) for k in ("kind", "affects_routing")}))
ok("1. its limit: 150 lorry movements a day, the average of working days, public",
   (Z.get("limit_value"), Z.get("limit_counts"), Z.get("limit_basis"), bool(Z.get("limit_public")))
   == (150.0, "movements", "average", True),
   str({k: Z.get(k) for k in ("limit_value", "limit_counts", "limit_basis", "limit_public")}))
G = geom_of(Z) or {}
C = G.get("coordinates") or []


def _km(pts):
    k = 0.0
    for a, b in zip(pts, pts[1:]):
        dx = (b[0] - a[0]) * 111320 * math.cos(math.radians(52.63))
        dy = (b[1] - a[1]) * 110540
        k += math.hypot(dx, dy)
    return k / 1000


ok("1. its line: the B6047 north from the Cold Newton turn to Tilton on the Hill, 24 points, about 2.79 km",
   G.get("type") == "LineString" and len(C) == 24 and 2.75 < _km(C) < 2.83
   and C[0] == [-0.92079, 52.622928] and C[-1] == [-0.904592, 52.644152], f"{len(C)} pts {_km(C):.3f} km")
_gen = open(os.path.join(BACKEND, "tools", "make_demo_tenant.py"), encoding="utf-8").read()
ok("1. the generator makes it LAST (after Z040's assert) and says where the line came from (OpenStreetMap, ODbL)",
   _gen.index('assert z["id"] == "Z040", z') < _gen.index('assert z.get("id") == "Z041", z')
   and "OSM data © OpenStreetMap contributors, ODbL" in _gen and "card M-F1" in _gen)

# =========================================================================== #
#  2. The figures on the generated plan (stand-in lines)                      #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
limits.init_db()
res = tenant_package.import_tenant(PKG, replace=True)
ok("2. setup: the demo package imports", bool(res.get("ok")), str(res)[:200])
LIM = [z for z in zones.list_zones() if z["id"] == "Z041"]
ok("2. imported, Z041 reads as a public limit of 150 movements a day",
   len(LIM) == 1 and LIM[0].get("limit") == {"value": 150.0, "counts": "movements", "basis": "average", "public": True},
   str(LIM[0].get("limit") if LIM else None))

ART = network.DEFAULT_PROFILE
ON = ("R009", "R021", "R023", "R046", "R048", "R049", "R050")   # live's routes on the stretch, Apr 2027
BACK_ELSEWHERE = ("R021", "R023")                               # live: in 84.8, out 77.3 = 84.8 - R021 - R023
AWAY = [[p[0], p[1] + 0.01] for p in C]                         # about 1.1 km north of the stretch
for rid in ON:
    network._upsert_geom(rid, ART, json.dumps(C), 2.8, 0.07, None, leg="loaded", alt_index=0,
                         zones_applied="", haul_zones="")
    back = AWAY if rid in BACK_ELSEWHERE else C
    network._upsert_geom(rid, ART, json.dumps(list(reversed(back))), 2.8, 0.07, None, leg="return", alt_index=0,
                         zones_applied="", haul_zones="")
DRAWN = {rid: ART for rid in ON}
CTX = {"drawn": DRAWN, "legs": TL._legs(DRAWN), "rows": route_choice._rows_by_route(), "share_cache": {},
       "wd": main._working_days(conversions.load_factors()), "lines_by_month": main.approved_lines_by_month,
       "months": main.MONTH_COUNT}
MAR27, APR27 = 15, 16   # (2027 - 2026) * 12 + month
CH = TL.check(LIM[0], [MAR27, APR27], ctx=CTX) if LIM else {}
mar, apr = CH.get(MAR27, {}), CH.get(APR27, {})
ok("2. ⭐ Mar 2027 reads NEAR: 147.3 lorry movements a day against 150 (live 147.35)",
   mar.get("state") == "near" and abs((mar.get("value") or 0) - 147.35) < 0.05, str(mar.get("value")))
ok("2. ⭐ Apr 2027 reads OVER: 162.1 against 150 (live 162.07)",
   apr.get("state") == "over" and abs((apr.get("value") or 0) - 162.07) < 0.05, str(apr.get("value")))
ok("2. Apr 2027's in / out is live's: 84.8 in, 77.3 out, on the seven routes",
   abs((apr.get("in_per_day") or 0) - 84.8) < 0.05 and abs((apr.get("out_per_day") or 0) - 77.27) < 0.05
   and sorted(r["route_id"] for r in apr.get("routes") or []) == list(ON),
   str((apr.get("in_per_day"), apr.get("out_per_day"))))
SUM = TL.summary(months=[MAR27, APR27], public_only=True, ctx=CTX)
ok("2. the public read lists it (the map's Traffic limits layer, the bulletin): Apr over, Mar near",
   [(l["id"], l["months_over"], l["months_near"]) for l in SUM["limits"]] == [("Z041", [APR27], [MAR27])],
   str([(l["id"], l["months_over"], l["months_near"]) for l in SUM["limits"]]))

# =========================================================================== #
#  3. A live refresh keeps live's limit (the generator is loaded last: it      #
#     points db at its own scratch file)                                      #
# =========================================================================== #
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("make_demo_tenant_mf1", os.path.join(BACKEND, "tools", "make_demo_tenant.py"))
GEN = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(GEN)

LIVE_LINE = [[-0.92081, 52.62293], [-0.92068, 52.62338], [-0.91853, 52.62976], [-0.90459, 52.64415]]


def live_export(mutate=None):
    live = _copy.deepcopy(PKG)
    for rows in live["tables"].values():
        for r in rows:
            for c in ("affects_routing", "active", "limit_public"):
                if c in r and r[c] in (0, 1):
                    r[c] = bool(r[c])          # Postgres hands BOOLEAN columns out as true / false
    z41 = next((z for z in live["tables"]["zones"] if z["id"] == "Z041"), None)
    if z41 is not None:
        z41["geometry"] = json.dumps({"type": "LineString", "coordinates": LIVE_LINE})
    if mutate:
        mutate(live["tables"])
    return live


def refresh(live):
    path = os.path.join(TMP, "live-export-mf1.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(live, f)
    pkg = _copy.deepcopy(PKG)
    try:
        GEN.copy_live_tables(pkg, path)
        return pkg, None
    except SystemExit as e:
        return None, str(e)


def _z(tables, zid):
    return next((z for z in tables["zones"] if z["id"] == zid), None)


def _limit_140(t):
    if _z(t, "Z041"):
        _z(t, "Z041")["limit_value"] = 140.0


out, err = refresh(live_export(_limit_140))
ok("3. ⭐ a live export whose Z041 has live's own line (and a limit edited there) is NOT refused", out is not None, err or "")
o41 = _z(out["tables"], "Z041") if out else {}
ok("3. ...and the refreshed package keeps live's row: live's line and live's 140",
   geom_of(o41 or {}) == {"type": "LineString", "coordinates": LIVE_LINE} and (o41 or {}).get("limit_value") == 140.0,
   str((o41 or {}).get("limit_value")))
ok("3. ...every other zone is the package's own",
   out is not None and [z for z in out["tables"]["zones"] if z["id"] != "Z041"] == [z for z in ZS if z["id"] != "Z041"])
ok("3. keep_live_traffic_limits keeps only traffic limits, by id",
   GEN.keep_live_traffic_limits([{"id": "Z041", "kind": "traffic_limit", "geometry": "L"},
                                 {"id": "Z001", "kind": "closure", "geometry": "L"}],
                                [{"id": "Z001", "kind": "closure", "geometry": "P"},
                                 {"id": "Z041", "kind": "traffic_limit", "geometry": "P"}]) == ["Z041"])


def _drop_41(t):
    t["zones"] = [z for z in t["zones"] if z["id"] != "Z041"]


def _date_41(t):
    if _z(t, "Z041"):
        _z(t, "Z041")["starts_on"] = "2027-01-01"


def _move_33(t):
    g = geom_of(_z(t, "Z033"))
    g["coordinates"][0][0] = [g["coordinates"][0][0][0] + 0.001, g["coordinates"][0][0][1]]
    _z(t, "Z033")["geometry"] = json.dumps(g)


for label, fn in (("without Z041 (live before 11 Nov)", _drop_41), ("with Z041 dated", _date_41),
                  ("with another zone's shape changed (Z033)", _move_33)):
    _o, _e = refresh(live_export(fn))
    ok(f"3. a live export {label} is still refused (zones differ)", _o is None and "zones differ" in (_e or ""), _e or "")

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
