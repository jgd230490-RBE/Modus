"""
The staff screens' reads kept until the next write (28 Oct 2026, the demo narrative's F1).

On the live demo the Dashboard's reads took 4-21 s, the Carbon planner's 25 s, the Routes page's 11 s, the CLP pack
47 s and the bulletin 95 s when the server was busy (timed in the user's Chrome, notes demo-narrative-1028 §7a); the
same reads take 0.1-2.5 s on a laptop copy. main._staff_json / _staff_bytes keep each answer in read_cache, per
read, parameters, ROLE and TEAM and today's date, until the next write; the admin's first-visit set is warmed.

WHAT THIS PROVES
----------------
  * a second read is served from memory (no build) and is the same answer; a write in between rebuilds it;
  * a team login never gets the scheme's answer or another team's, and the scheme's answer is never a team's;
  * the parameters split entries (the Look-ahead with and without the restriction check; two Carbon planner bodies;
    two months of gate arrivals); a refused Carbon planner body is a 400 and keeps nothing;
  * the store's cap (entries and bytes, least recently used first) and `keep` (served, not kept);
  * the bulletin PDF is kept only when no map fell back to the schematic while it was drawn; the CLP pack reads the
    CLP monitoring reply from memory (29 Oct), so a second pack builds nothing;
  * the warmer builds the admin's Dashboard / Look-ahead / Routes set, after which those reads build nothing;
  * at source: every one of the cached endpoints goes through the helpers.

WHAT THIS DOES NOT PROVE
------------------------
  * Postgres, Render's timings (the live check after merging is the test of the speed), the HTTP layer (stubbed here;
    http_smoke drives the real app through the same endpoints), or a second process (Render runs one; db.py).

Run:  python backend/tests/test_staff_cache.py
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

TMP = tempfile.mkdtemp(prefix="wayscope_staffcache_")
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


def lines_of(reply):
    rows = reply.get("lines") if isinstance(reply, dict) else reply
    return rows or []


# =========================================================================== #
#  1. A second read is served from memory; a write rebuilds it                 #
# =========================================================================== #
read_cache.clear()
s0 = stats()
a1 = as_(ADMIN, lambda: main.costing_lines(from_=None, to=None, status="All"))
s1 = stats()
a2 = as_(ADMIN, lambda: main.costing_lines(from_=None, to=None, status="All"))
s2 = stats()
ok("⭐ the Dashboard's cost lines: the first read builds, the second is served from memory (no build)",
   s1["builds"] == s0["builds"] + 1 and s2["builds"] == s1["builds"] and s2["hits"] == s1["hits"] + 1,
   f"{s0} {s1} {s2}")
ok("...and it is the same answer", a2 is a1 and len(lines_of(a1)) > 0, str(len(lines_of(a1))))
_row = db.query("SELECT route_id, month_index, discipline, section_id, quantity FROM forecasts WHERE tenant_id = ? "
                "AND status = 'Approved' ORDER BY route_id, month_index LIMIT 1", (db.current_tenant(),))[0]
v0 = db.data_version()
db.execute("UPDATE forecasts SET quantity = ? WHERE tenant_id = ? AND route_id = ? AND month_index = ? AND discipline = ? "
           "AND section_id = ?", (float(_row["quantity"]) + 1000.0, db.current_tenant(), _row["route_id"],
                                  _row["month_index"], _row["discipline"], _row["section_id"]))
a3 = as_(ADMIN, lambda: main.costing_lines(from_=None, to=None, status="All"))
s3 = stats()
ok("⭐ a write in between (one line's quantity) moves the data version and the next read is BUILT again, not served",
   db.data_version() > v0 and s3["builds"] == s2["builds"] + 1 and a3 is not a1)


def _qty(reply, r):
    return sum(float(l.get("quantity") or 0) for l in lines_of(reply)
               if l.get("route_id") == r["route_id"] and int(l.get("month_index") or 0) == int(r["month_index"])
               and (l.get("discipline") or "") == (r["discipline"] or ""))


ok("...and the rebuilt answer carries the change", abs(_qty(a3, _row) - _qty(a1, _row) - 1000.0) < 1e-6,
   f"{_qty(a1, _row)} -> {_qty(a3, _row)}")

# =========================================================================== #
#  2. A team never gets another scope's answer                                 #
# =========================================================================== #
t1 = as_(TEAM1, lambda: main.costing_lines(from_=None, to=None, status="All"))
t2 = as_(TEAM2, lambda: main.costing_lines(from_=None, to=None, status="All"))
a4 = as_(ADMIN, lambda: main.costing_lines(from_=None, to=None, status="All"))
_t1_ipts = {access.canonical_ipt(l.get("ipt")) for l in lines_of(t1)}
_t2_ipts = {access.canonical_ipt(l.get("ipt")) for l in lines_of(t2)}
_all_ipts = {access.canonical_ipt(l.get("ipt")) for l in lines_of(a4)}
ok("⭐ a team login gets ONLY its own team's lines (its own entry), after the scheme's answer was in memory",
   _t1_ipts == {"IPT1"} and _t2_ipts == {"IPT2"}, f"{_t1_ipts} {_t2_ipts}")
ok("...and the admin, after the teams read, still gets every team's lines (the admin's entry, not a team's)",
   {"IPT1", "IPT2"} <= _all_ipts and len(lines_of(a4)) > len(lines_of(t1)), f"{_all_ipts}")
ok("...the entries are keyed by role and team: four different names for admin / planner / team 1 / team 2",
   len({main._staff_name("x", {}, acc) for acc in (ADMIN, PLANNER, TEAM1, TEAM2)}) == 4
   and main._staff_scope(TEAM1) == "ipt|IPT1" and main._staff_scope(None) == "-|-")
gt1 = as_(TEAM1, lambda: main.gate_arrivals_month(month=None))
ga = as_(ADMIN, lambda: main.gate_arrivals_month(month=None))
ok("...the gate arrivals too: a team's answer is not the admin's (the admin's carries every team's figures)",
   gt1 is not ga and isinstance(ga, dict) and isinstance(gt1, dict))

# =========================================================================== #
#  3. The parameters split entries                                             #
# =========================================================================== #
s4 = stats()
la_first = as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=0, tark_tee=None))
s4b = stats()
ok("the Look-ahead's first read of a new week writes that week's rows, so it is served but NOT kept (a write landed "
   "during the build: read_cache keeps nothing older than the data)",
   s4b["discarded"] == s4["discarded"] + 1 and isinstance(la_first, dict), f"{s4} {s4b}")
la_off = as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=0, tark_tee=None))
la_on = as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=1, tark_tee=None))
la_off2 = as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=0, tark_tee=None))
s5 = stats()
ok("...from the second read on it is kept; with and without the restriction check are two entries (the Dashboard's "
   "and the page's)", la_off is la_off2 and la_on is not la_off and s5["discarded"] == s4b["discarded"],
   f"same={la_off is la_off2} differ={la_on is not la_off} {s4b} {s5}")
m1 = as_(ADMIN, lambda: main.gate_arrivals_month(month=10))
m2 = as_(ADMIN, lambda: main.gate_arrivals_month(month=11))
ok("...two months of gate arrivals are two entries", m1 is not m2
   and as_(ADMIN, lambda: main.gate_arrivals_month(month=10)) is m1)
c1 = as_(ADMIN, lambda: main.carbon_scenario(main.CarbonScenarioIn()))
c2 = as_(ADMIN, lambda: main.carbon_scenario(main.CarbonScenarioIn(status="All")))
c3 = as_(ADMIN, lambda: main.carbon_scenario(main.CarbonScenarioIn()))
ok("⭐ the Carbon planner: the same body is served from memory, another body is its own answer",
   c3 is c1 and c2 is not c1 and isinstance(c1, dict))
s6 = stats()
try:
    as_(ADMIN, lambda: main.carbon_scenario(main.CarbonScenarioIn(status="Nonsense")))
    _code = None
except _HTTPException as e:
    _code = e.status_code
ok("...a refused body is still a 400, and keeps nothing", _code == 400 and stats()["builds"] == s6["builds"])

# =========================================================================== #
#  4. The store's cap, and `keep`                                              #
# =========================================================================== #
read_cache.clear()
_old = (read_cache.MAX_ENTRIES, read_cache.MAX_BYTES)
read_cache.MAX_ENTRIES, read_cache.MAX_BYTES = 3, 10_000
for i in range(5):
    read_cache.cached(f"cap-test-{i}", "k", lambda i=i: f"v{i}")
_names = sorted(n for (n, _t) in read_cache._STORE if n.startswith("cap-test-"))
ok("the cap: at most MAX_ENTRIES entries, the least recently used dropped first",
   _names == ["cap-test-2", "cap-test-3", "cap-test-4"], str(_names))
read_cache.cached("cap-test-2", "k", lambda: "never")       # a hit: now the most recently used
read_cache.cached("cap-test-5", "k", lambda: "v5")
_names = sorted(n for (n, _t) in read_cache._STORE if n.startswith("cap-test-"))
ok("...a hit counts as a use (cap-test-2 stays, cap-test-3 goes)", _names == ["cap-test-2", "cap-test-4", "cap-test-5"],
   str(_names))
read_cache.clear()
read_cache.cached("bytes-a", "k", lambda: b"x" * 6000)
read_cache.cached("bytes-b", "k", lambda: b"y" * 6000)
ok("...and MAX_BYTES: two 6,000-byte answers do not both fit in 10,000",
   [n for (n, _t) in read_cache._STORE] == ["bytes-b"], str(list(read_cache._STORE)))
read_cache.MAX_ENTRIES, read_cache.MAX_BYTES = _old
read_cache.clear()
s7 = stats()
v = read_cache.cached("keep-test", "k", lambda: "served", keep=lambda: False)
ok("keep=False: the value is served, nothing is kept, the next read builds again",
   v == "served" and ("keep-test", db.current_tenant()) not in read_cache._STORE
   and read_cache.cached("keep-test", "k", lambda: "again", keep=lambda: False) == "again"
   and stats()["not_kept"] == s7.get("not_kept", 0) + 2)

# =========================================================================== #
#  5. The bulletin PDF: kept only when every map was Mapbox's picture          #
# =========================================================================== #
_real_build = main.export.build_bulletin_pdf
_calls = []


def _fake_build_missed(sheet):
    _calls.append("missed")
    basemap.MISSES[0] += 1               # a map fell back to the schematic while this one was drawn
    return b"%PDF-schematic"


def _fake_build_ok(sheet):
    _calls.append("ok")
    return b"%PDF-mapbox"


_req = _Request()
try:
    main.export.build_bulletin_pdf = _fake_build_missed
    r1 = as_(ADMIN, lambda: main.bulletin_month_pdf(month=10, request=_req))
    r2 = as_(ADMIN, lambda: main.bulletin_month_pdf(month=10, request=_req))
    ok("⭐ a bulletin drawn with a schematic map is served but NOT kept: the next one is drawn again",
       r1.body == b"%PDF-schematic" and _calls == ["missed", "missed"], str(_calls))
    main.export.build_bulletin_pdf = _fake_build_ok
    r3 = as_(ADMIN, lambda: main.bulletin_month_pdf(month=10, request=_req))
    r4 = as_(ADMIN, lambda: main.bulletin_month_pdf(month=10, request=_req))
    ok("...one drawn with every map is kept: the second is served from memory",
       r3.body == r4.body == b"%PDF-mapbox" and _calls == ["missed", "missed", "ok"], str(_calls))
    ok("...and the reply is still a PDF download, never cached by the browser",
       r4.media_type == "application/pdf" and r4.headers.get("Cache-Control") == "no-store"
       and "bulletin-2026-10.pdf" in r4.headers.get("Content-Disposition", ""))
finally:
    main.export.build_bulletin_pdf = _real_build

# 29 Oct 2026 (F1 follow-up): the CLP pack reads the CLP monitoring reply from memory, so a second pack builds nothing
read_cache.clear()
_p1 = as_(ADMIN, lambda: main.clp_pack_pdf(month=10))
s_p = stats()
_p2 = as_(ADMIN, lambda: main.clp_pack_pdf(month=10))
ok("⭐ the CLP pack: a second download builds nothing (neither the CLP figures nor the PDF), same bytes",
   stats()["builds"] == s_p["builds"] and _p1.body == _p2.body and _p1.body[:5] == b"%PDF-", f"{s_p} {stats()}")
ok("...and the figures it was drawn from are the Dashboard's CLP monitoring answer for that month (one entry)",
   as_(ADMIN, lambda: main.clp_monitoring(month=10)) is as_(ADMIN, lambda: main._clp_pack_reply(10)))

# =========================================================================== #
#  6. The warmer                                                               #
# =========================================================================== #
read_cache.clear()
_res = read_cache.warm(db.current_tenant())
ok("⭐ the warmer has a 'staff' entry and it runs without an error", _res.get("staff") == "ok", str(_res))
s8 = stats()
as_(ADMIN, lambda: main.costing_lines(from_=None, to=None, status="All"))
as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=0, tark_tee=None))
as_(ADMIN, lambda: main.lookahead_page(bucket="commit", route_id=None, restrictions_on=1, tark_tee=None))
as_(ADMIN, lambda: main.gate_arrivals_month(month=None))
as_(ADMIN, lambda: main.clp_monitoring(month=None))
as_(ADMIN, lambda: main.forecasts_summary())
as_(ADMIN, lambda: main.routes_status())
as_(ADMIN, lambda: main.routes_summary())
as_(ADMIN, lambda: main.routes_diversions(route_id=None))
ok("...after it, the admin's Dashboard, Look-ahead and Routes reads build nothing (all nine served from memory)",
   stats()["builds"] == s8["builds"] and stats()["hits"] == s8["hits"] + 9, f"{s8} {stats()}")
s9 = stats()
as_(TEAM1, lambda: main.costing_lines(from_=None, to=None, status="All"))
ok("...a team login's first read is still built for that team (the warmer builds the admin's scope only)",
   stats()["builds"] == s9["builds"] + 1)

# =========================================================================== #
#  7. At source                                                                #
# =========================================================================== #
_main = read("backend/main.py")


def _body(fn):
    i = _main.index(f"def {fn}(")
    j = _main.find("\n@app.", i)
    return _main[i:j if j > 0 else None]


_JSON_READS = ("forecasts_summary", "lookahead_page", "lookahead_geometry", "costing_lines", "carbon_scenario",
               "routes_status", "routes_summary", "routes_diversions", "gate_arrivals_month", "clp_monitoring")
ok("⭐ every cached staff read goes through _staff_json (the key with role and team)",
   all("_staff_json(" in _body(f) for f in _JSON_READS), str([f for f in _JSON_READS if "_staff_json(" not in _body(f)]))
ok("...the two PDFs through _staff_bytes, the bulletin with its keep on basemap.MISSES",
   "_staff_bytes(\"clp/pack.pdf\"" in _body("clp_pack_pdf")
   and "_staff_bytes(\"bulletin/month.pdf\"" in _body("bulletin_month_pdf")
   and "keep=lambda: basemap.MISSES[0] == misses" in _body("bulletin_month_pdf"))
ok("...the scope is the role and the canonical team, and the key carries today's date",
   "access.canonical_ipt(acc.get('ipt'))" in _main and "_dt.date.today().isoformat()" in _body("_staff_json"))
_bm = read("backend/basemap.py")
ok("basemap.fetch counts every None it answers with a token (down, refused, unreachable, not a picture)",
   _bm.count("MISSES[0] += 1") == 4)
ok("the Carbon planner's read (a POST) still does not count as a write (else it would empty every entry)",
   '"/api/carbon/scenario"' in _main[_main.index("AUDIT_SKIP = ("):_main.index("AUDIT_SKIP_PREFIXES")])

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
