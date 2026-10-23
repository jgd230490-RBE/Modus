"""
The public map's reads after the live out-of-memory kills (21 Oct 2026, notes live-502-1021.md) — branch
claude/map-read-memory.

On 21 Oct Render killed the app twice at its 512 MiB limit. Each map page load fired about twelve reads at once and
then read every month's figures one by one (/api/public/month-kpis, sixty reads, again on every reload); each of those
re-read the cost lines for months 1..M and called route_analysis() per (route, vehicle), which read every leg's whole
HERE polyline only to see whether it was empty. Overlapping loads emptied the database pool and filled the memory.

The fix:
  1. GET /api/public/month-kpis/months: every month's month-kpis answer in one read (forecasts once, cost lines once,
     each route's figures once); the map reads it once a page load and keeps the month read as its fallback.
  2. month-kpis passes a request-level `pre` to route_analysis(), and route_analysis() no longer reads the polyline
     text (network.ANALYSIS_GEOMETRY_SQL: a 1 / NULL in its place).
  3. heavy_reads.slot(): at most SLOTS heavy public reads at once (month-kpis, month-kpis/months, map-data,
     route-alternatives, forecast-matrix, areas/months); the rest wait; one log line of memory each.
  4. /api/health is `async def`, so it answers while every worker thread is busy.

WHAT IS ASSERTED
----------------
  * on the SHIPPED four-year demo package (905 approved line-months, 43 routes) with stand-in straight-line legs (some
    routes unbaked, an alternative, an empty and a NULL polyline, a drawn haul road): the bulk read's every month equals
    the month read's answer BYTE FOR BYTE, and both equal a REFERENCE copy of the month read as it was on main 10a308d
    (no `pre`, `SELECT *` geometry, its own 1..M cost-lines read) — all 60 months in vehicles, a spread in tonnes;
  * the bulk read makes a small fraction of the sixty month reads' database statements, and one route_analysis() per
    (route, vehicle) in all;
  * route_analysis(): the same answer with the light geometry query as with `SELECT *`, with and without `pre`, for
    every route; the rows it keeps carry no polyline text; an empty or NULL polyline is skipped as before;
  * a failed carbon read: every month says co2_error and every co2_t is None, the same in both reads;
  * heavy_reads: never more than SLOTS reads at once; a read inside a read on one thread takes no second slot and
    prints no second line; a read that finds no slot in WAIT_S is answered busy (the endpoint's 503); one memory line
    per read, with a figure on this platform;
  * the six endpoints hold a slot; /api/health is a coroutine and answers; the new path is behind the map gate.

WHAT THIS DOES NOT PROVE
------------------------
  * No Postgres branch runs: the light geometry query's `geometry = ''` on Postgres (no detoast) is from the
    documentation, not measured. The memory effect on Render (glibc arenas) is not measured here; the session note
    has the laptop's figures (Windows).
  * The HTTP transport is stubbed: endpoint BODIES run. http_smoke.py drives the real app (the gate, the 200s).
  * The stand-in legs are straight lines, not HERE's; the figures' equality does not depend on their shape.

Run:  python backend/tests/test_month_kpis_bulk.py
"""
import asyncio
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# --------------------------------------------------------------------------- #
#  Stubs (the same shape every other harness uses)                             #
# --------------------------------------------------------------------------- #
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None):
        super().__init__(detail)
        self.status_code, self.detail, self.headers = status_code, detail, headers


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

TMP = tempfile.mkdtemp(prefix="wayscope_kpibulk_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import costlines  # noqa: E402
import derived  # noqa: E402
import tenant_package  # noqa: E402
import heavy_reads  # noqa: E402
import gate  # noqa: E402
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
        return f.read()


def dumps(x):
    """Byte for byte, key order included (no sort_keys): the answer as the page receives it."""
    return json.dumps(x, ensure_ascii=False)


@contextlib.contextmanager
def quiet():
    """The heavy-read lines go to stdout; keep the harness's own output readable."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


# --------------------------------------------------------------------------- #
#  The shipped demo package, with stand-in legs                                #
# --------------------------------------------------------------------------- #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
PKG = json.loads(read("demo/uk-corridor.package.json"))
_res = tenant_package.import_tenant(PKG, replace=True)
ok("0. the shipped demo package imports into an empty tenant", _res.get("ok") is True, str(_res)[:200])
config.invalidate()
MC = main.MONTH_COUNT
APPROVED = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved'", (db.current_tenant(),))
ROUTES = db.query("SELECT * FROM routes WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
LOCS = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
ok("0. the four-year demo: 905 approved line-months on 43 routes",
   len(APPROVED) == 905 and len(ROUTES) == 43, f"{len(APPROVED)} {len(ROUTES)}")
VEH_BY_ROUTE = {}
for f in APPROVED:
    VEH_BY_ROUTE.setdefault(f["route_id"], set()).add(f["vehicle_type"])


def hav(a, b):
    R = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def line(o, d, n=40, bow=0.0):
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append([round(o[0] + (d[0] - o[0]) * t + bow * math.sin(math.pi * t), 6),
                    round(o[1] + (d[1] - o[1]) * t, 6)])
    return pts


def add_geom(rid, prof, leg, alt, geometry, km, hr, haul_zones=None):
    db.execute(
        "INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
        "duration_hr, computed_at, haul_zones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), rid, prof, leg, alt, geometry, km, hr, "2026-10-21T00:00:00Z", haul_zones))


UNBAKED = set()
SPECIAL = {}
for i, rt in enumerate(ROUTES):
    rid = rt["id"]
    if i % 7 == 3:                      # every seventh route not baked: no trips, no carbon (None, never zero)
        UNBAKED.add(rid)
        continue
    o, d = LOCS.get(rt["origin_id"]), LOCS.get(rt["dest_id"])
    if not o or not d or o.get("lon") is None or d.get("lon") is None:
        UNBAKED.add(rid)
        continue
    a, b = [float(o["lon"]), float(o["lat"])], [float(d["lon"]), float(d["lat"])]
    for prof in sorted(VEH_BY_ROUTE.get(rid, set()) | {network.DEFAULT_PROFILE}):
        out_pts, back_pts = line(a, b, bow=0.01), line(b, a, bow=-0.01)
        km_o = round(sum(hav(out_pts[k], out_pts[k + 1]) for k in range(len(out_pts) - 1)) * 1.25, 3)
        km_b = round(km_o * 1.04, 3)
        hz = "Z900" if i % 11 == 5 else None          # a drawn haul road on a few legs (drawn_road_on reads it)
        loaded_geom, return_geom = json.dumps(out_pts), json.dumps(back_pts)
        if i % 13 == 6:
            return_geom = ""                          # an empty return polyline: the outbound stands in
            SPECIAL[rid] = "empty return"
        if i % 17 == 9:
            loaded_geom = None                        # a NULL loaded polyline (a failed bake): no row costed
            SPECIAL[rid] = "null loaded"
        add_geom(rid, prof, "loaded", 0, loaded_geom, km_o, round(km_o / 48.0, 4), hz)
        add_geom(rid, prof, "return", 0, return_geom, km_b, round(km_b / 52.0, 4))
        if i % 5 == 1:                                # an alternative, as live carries
            add_geom(rid, prof, "loaded", 1, json.dumps(line(a, b, bow=0.03)), round(km_o * 1.1, 3),
                     round(km_o * 1.1 / 45.0, 4))
ok("0. the stand-in network: some routes unbaked, an empty and a NULL polyline, alternatives",
   len(UNBAKED) >= 5 and "empty return" in SPECIAL.values() and "null loaded" in SPECIAL.values()
   and db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND alt_index = 1",
                (db.current_tenant(),))[0]["n"] > 0, f"{len(UNBAKED)} {SPECIAL}")

# --------------------------------------------------------------------------- #
#  The month read as it was on main 10a308d (the reference)                   #
# --------------------------------------------------------------------------- #
OLD_GEOMETRY_SQL = "SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ?"


@contextlib.contextmanager
def old_geometry_query():
    keep = network.ANALYSIS_GEOMETRY_SQL
    network.ANALYSIS_GEOMETRY_SQL = OLD_GEOMETRY_SQL
    try:
        yield
    finally:
        network.ANALYSIS_GEOMETRY_SQL = keep


def reference_month_kpis(month, unit):
    """main.public_month_kpis on 10a308d, verbatim but for the endpoint wrapper: route_analysis without `pre` and with
    SELECT * geometry, the forecast query without the `id` tie-break, its own costlines read for months 1..month."""
    factors = conversions.load_factors()
    wd = main._working_days(factors)
    vs = factors.get("vehicles", {}) or {}
    fb_payload, fb_name = derived.payload_for(None, factors)
    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved' "
        "AND month_index = ? ORDER BY route_id, discipline, section_id",
        (db.current_tenant(), int(month)))
    _tpv_cache = {}

    def trips_per_vehicle_day(route_id, vehicle):
        key = (route_id, vehicle)
        if key not in _tpv_cache:
            tpv = None
            try:
                with old_geometry_query():
                    res = network.route_analysis(route_id, profiles=[vehicle] if vehicle else None)
                for row in res.get("rows", []):
                    if row.get("alt_index") == 0 and (not vehicle or row.get("profile") == vehicle):
                        tpv = max(1, int(row.get("trips_per_day") or 0))
                        break
            except Exception:
                tpv = None
            _tpv_cache[key] = tpv
        return _tpv_cache[key]

    lines = []
    for r in rows:
        ln = main._month_kpi_line(r, unit, factors, vs, fb_payload, fb_name)
        ln["trips_per_vehicle_day"] = trips_per_vehicle_day(r["route_id"], r.get("vehicle_type"))
        lines.append(ln)
    table, co2_error = main._approved_co2(factors, 1, int(month))
    co2_by_key, to_date, unbaked_to_date = {}, {}, 0
    for (rid, disc, sec, mi), co2 in table.items():
        if mi == int(month):
            co2_by_key[(rid, disc, sec)] = co2
        if co2 is None:
            unbaked_to_date += 1
            continue
        to_date[(rid, disc, sec)] = to_date.get((rid, disc, sec), 0.0) + float(co2)
    for l in lines:
        l["co2_t"] = co2_by_key.get((l["route_id"], l["discipline"], l["section_id"]))
    co2_to_date = [{"route_id": k[0], "discipline": k[1], "section_id": k[2], "co2_t": round(v, 3)}
                   for k, v in sorted(to_date.items())]
    out = {"month": int(month), "unit": unit, "working_days": wd,
           "payload_fallback_vehicle": fb_name,
           "payload_fallback_name": conversions.vehicle_label(factors, fb_name) if fb_name else None,
           "lines": lines,
           "co2_to_date": co2_to_date, "co2_to_date_unbaked_lines": unbaked_to_date}
    if co2_error:
        out["co2_error"] = co2_error
    return out


# a counter on every database statement and every route_analysis()
COUNT = {"q": 0, "ra": 0}
_q, _ra = db.query, network.route_analysis


def _cq(*a, **k):
    COUNT["q"] += 1
    return _q(*a, **k)


def _cra(*a, **k):
    COUNT["ra"] += 1
    return _ra(*a, **k)


db.query = _cq
network.route_analysis = _cra

# =========================================================================== #
#  1. The bulk read == the month read == the old month read                    #
# =========================================================================== #
with quiet():
    COUNT["q"] = COUNT["ra"] = 0
    t = time.perf_counter()
    BULK = main.public_month_kpis_months(unit="vehicles")
    bulk_s, bulk_q, bulk_ra = time.perf_counter() - t, COUNT["q"], COUNT["ra"]
    COUNT["q"] = COUNT["ra"] = 0
    t = time.perf_counter()
    ONE = {m: main.public_month_kpis(month=m, unit="vehicles") for m in range(1, MC + 1)}
    sweep_s, sweep_q, sweep_ra = time.perf_counter() - t, COUNT["q"], COUNT["ra"]
# the old month read for a spread of months (each re-reads the cost lines for 1..M: all sixty would double the run);
# with the bulk read equal to the new month read for all sixty, the spread pins the new code to the old answers
SPREAD = [1, 2, 7, 11, 12, 19, 25, 31, 38, 44, 47, 53, 59, 60]
REF = {m: reference_month_kpis(m, "vehicles") for m in SPREAD}
ok("1. the bulk answer is {unit, months}: one entry for each of the 60 months, keyed '1'..'60'",
   set(BULK) == {"unit", "months"} and BULK["unit"] == "vehicles" and list(BULK["months"]) == [str(m) for m in range(1, MC + 1)])
_diff = [m for m in range(1, MC + 1) if dumps(BULK["months"][str(m)]) != dumps(ONE[m])]
ok("1. ⭐ every month of the bulk read is the month read's answer byte for byte (all 60 months, vehicles)",
   not _diff, str(_diff[:5]))
# NARROWED 23 Oct 2026: abnormal_loads (the public abnormal loads' ids a month, for the public map's figures bar) is appended
# LAST to every month's answer; without it the answer is still what main 10a308d gave
_diff = [m for m in SPREAD if dumps({k: v for k, v in ONE[m].items() if k != "abnormal_loads"}) != dumps(REF[m])]
ok("1. ⭐ ...and the month read is byte for byte what it answered on main 10a308d (a spread of 14 months, the dearest "
   "last month included; abnormal_loads left out)", not _diff, str(_diff[:5]))
_lines = sum(len(ONE[m]["lines"]) for m in ONE)
_trips = [l["trips_per_vehicle_day"] for m in REF for l in REF[m]["lines"]]
_co2 = [l["co2_t"] for m in REF for l in REF[m]["lines"]]
ok("1. the comparison means something: all 905 approved line-months; in the spread, figures and Nones both and the "
   "carbon to date summed",
   _lines == 905 and any(x is None for x in _trips) and any(x for x in _trips)
   and any(x is None for x in _co2) and any(x for x in _co2)
   and any(REF[m]["co2_to_date"] for m in REF) and any(REF[m]["co2_to_date_unbaked_lines"] for m in REF),
   f"{_lines} lines")
_empty = [m for m in ONE if not ONE[m]["lines"]]
ok("1. ...a month with no lines (if the programme has one) still carries its carbon to date, and the last month carries "
   "the whole programme's", all(ONE[m]["co2_to_date"] or m < min(f["month_index"] for f in APPROVED) for m in _empty)
   and len(ONE[MC]["co2_to_date"]) >= len(ONE[1]["co2_to_date"]) and ONE[MC]["co2_to_date"], str(_empty))
with quiet():
    BULK_T = main.public_month_kpis_months(unit="t")
_diff = [m for m in (1, 12, 31, 47, 60) if dumps({k: v for k, v in BULK_T["months"][str(m)].items() if k != "abnormal_loads"}) != dumps(reference_month_kpis(m, "t"))]
ok("1. ⭐ in tonnes too: the bulk read equals the old month read for a spread of months (NARROWED 23 Oct 2026: abnormal_loads, appended last, left out)", not _diff, str(_diff))


def raises(fn, **k):
    try:
        with quiet():
            fn(**k)
    except Exception as e:      # noqa: BLE001
        return e
    return None


_e1, _e2 = raises(main.public_month_kpis_months, unit="furlongs"), raises(main.public_month_kpis, month=3, unit="furlongs")
ok("1. a unit the map does not know is refused (400) by the bulk read as by the month read",
   getattr(_e1, "status_code", None) == 400 and getattr(_e2, "status_code", None) == 400)

# =========================================================================== #
#  2. What the bulk read saves                                                 #
# =========================================================================== #
_pairs = len({(f["route_id"], f["vehicle_type"]) for f in APPROVED})
ok("2. ⭐ the bulk read makes two route_analysis() per (route, vehicle) in all — one for the trips a lorry a day, one in "
   "the cost lines' own read — where the sixty month reads made them per month",
   bulk_ra == 2 * _pairs and sweep_ra > 10 * bulk_ra, f"bulk {bulk_ra}, sweep {sweep_ra}, pairs {_pairs}")
ok("2. ⭐ ...and a small fraction of the database statements (under a tenth of the sixty month reads')",
   bulk_q * 10 < sweep_q, f"bulk {bulk_q}, sweep {sweep_q}")
print(f"   (bulk read {bulk_s:.2f} s, {bulk_q} statements, {bulk_ra} route analyses; 60 month reads {sweep_s:.2f} s, "
      f"{sweep_q} statements, {sweep_ra} route analyses)")
_calls = []
_keep = main._approved_co2
main._approved_co2 = lambda f, a, b: (_calls.append((a, b)), _keep(f, a, b))[1]
with quiet():
    main.public_month_kpis_months(unit="vehicles")
main._approved_co2 = _keep
ok("2. ⭐ ONE carbon read for the whole horizon, months 1..60 (was one 1..M read per month)", _calls == [(1, MC)], str(_calls))
_mk = read("backend/main.py")
_body = _mk[_mk.index("def _month_kpis_payloads("):_mk.index("def _month_kpi_line(")]
ok("2. the month read passes a request-level `pre` to route_analysis() (the Look-ahead's rule since 13 Oct)",
   "_pre = {}" in _body and "network.route_analysis(route_id, profiles=[vehicle] if vehicle else None, pre=_pre)" in _body
   and _body.count("_approved_co2(factors") == 1)

# =========================================================================== #
#  3. route_analysis() without the polyline text                               #
# =========================================================================== #
db.query, network.route_analysis = _q, _ra
_bad = []
for rt in ROUTES:
    rid = rt["id"]
    new = dumps(network.route_analysis(rid))
    with old_geometry_query():
        old = dumps(network.route_analysis(rid))
    pre = {}
    with_pre = dumps(network.route_analysis(rid, pre=pre))
    if not (new == old == with_pre):
        _bad.append(rid)
ok("3. ⭐ route_analysis(): every route's answer is the same with the light geometry query as with SELECT *, and with "
   "a request-level `pre` as without", not _bad, str(_bad))
_pre = {}
for rt in ROUTES:
    network.route_analysis(rt["id"], pre=_pre)
_kept = [g for rows in _pre["geom"].values() for g in rows]
ok("3. ⭐ the rows it keeps carry no polyline text: `geometry` is 1 or None, never the stored line",
   _kept and all(g["geometry"] in (1, None) for g in _kept) and any(g["geometry"] == 1 for g in _kept),
   str({type(g["geometry"]).__name__ for g in _kept}))
_full = db.query("SELECT * FROM route_geometry WHERE tenant_id = ?", (db.current_tenant(),))
_truth = {(g["route_id"], g["vehicle_profile"], g["leg"], g["alt_index"]): bool(g["geometry"]) for g in _full}
ok("3. ...and its truth is the stored polyline's: 1 where non-empty, None where NULL or '' (both kinds present)",
   all(_truth[(g["route_id"], g["vehicle_profile"], g["leg"], g["alt_index"])] == bool(g["geometry"]) for g in _kept)
   and any(x["geometry"] == "" for x in _full) and any(x["geometry"] is None for x in _full))
_cols = {c for g in _full for c in g} - {"geometry"}
ok("3. ...every other column is still read (drawn_road_on reads haul_zones; the cycle reads km, hours, haul km)",
   _cols <= set(_kept[0]) and "haul_zones" in _kept[0], str(sorted(_cols - set(_kept[0]))))
_er = [rid for rid, why in SPECIAL.items() if why == "empty return"][0]
_nl = [rid for rid, why in SPECIAL.items() if why == "null loaded"][0]
_ra_er = network.route_analysis(_er)["rows"]
ok("3. an empty return polyline: the outbound stands in and the row says return_estimated, as before",
   _ra_er and all(r["return_estimated"] for r in _ra_er if r["alt_index"] == 0))
ok("3. a NULL loaded polyline: no row costed for it, as before", network.route_analysis(_nl)["rows"] == [])
ok("3. drawn_road_on() reads haul_zones only (the light query keeps it)",
   'for z in (g.get("haul_zones") or "").split(","):' in read("backend/network.py")
   and "geometry" not in read("backend/network.py").split("def drawn_road_on(")[1].split("\ndef ")[0].split('"""')[2])
_net = read("backend/network.py")
_rab = _net[_net.index("def route_analysis("):]
_rab = _rab[:_rab.index("\ndef ")] if "\ndef " in _rab else _rab
ok("3. route_analysis() reads the geometry through ANALYSIS_GEOMETRY_SQL, never SELECT * FROM route_geometry",
   "db.query(ANALYSIS_GEOMETRY_SQL, (db.current_tenant(), route_id))" in _rab
   and "SELECT * FROM route_geometry" not in _rab
   and "CASE WHEN geometry IS NULL OR geometry = '' THEN NULL ELSE 1 END AS geometry" in network.ANALYSIS_GEOMETRY_SQL
   and "SELECT *" not in network.ANALYSIS_GEOMETRY_SQL)

# =========================================================================== #
#  4. A failed carbon read                                                     #
# =========================================================================== #
_keep_lines = costlines.lines
costlines.lines = lambda **k: (_ for _ in ()).throw(RuntimeError("no carbon today"))
with quiet():
    _bf = main.public_month_kpis_months(unit="vehicles")
    _of = {m: main.public_month_kpis(month=m, unit="vehicles") for m in (9, 31, 60)}
costlines.lines = _keep_lines
ok("4. ⭐ a failed carbon read: every month says co2_error, every co2_t is None, nothing to date — in both reads alike",
   all(_bf["months"][str(m)].get("co2_error") == main.CO2_ERROR_SENTENCE.format(cls="RuntimeError")
       and all(l["co2_t"] is None for l in _bf["months"][str(m)]["lines"])
       and _bf["months"][str(m)]["co2_to_date"] == [] for m in range(1, MC + 1))
   and all(dumps(_bf["months"][str(m)]) == dumps(_of[m]) for m in _of))
ok("4. ...and the volumes are not carbon's hostage (the lines are all there)",
   sum(len(_bf["months"][str(m)]["lines"]) for m in range(1, MC + 1)) == 905)

# =========================================================================== #
#  5. heavy_reads: a few at a time, one line each                              #
# =========================================================================== #
_live = {"now": 0, "max": 0}
_lk = threading.Lock()


def _hold(name, s=0.15):
    with heavy_reads.slot(name):
        with _lk:
            _live["now"] += 1
            _live["max"] = max(_live["max"], _live["now"])
        time.sleep(s)
        with _lk:
            _live["now"] -= 1


with quiet() as _out:
    _ths = [threading.Thread(target=_hold, args=(f"t{i}",)) for i in range(7)]
    for th in _ths:
        th.start()
    for th in _ths:
        th.join()
_logl = [l for l in _out.getvalue().splitlines() if l.startswith("🧮 heavy read t")]
ok("5. ⭐ seven reads at once: never more than SLOTS running together, every one ran", _live["max"] == heavy_reads.SLOTS
   and len(_logl) == 7 and heavy_reads.SLOTS in (2, 3), f"max {_live['max']}, lines {len(_logl)}")
ok("5. ⭐ one line each: memory before -> after in MB, how long it ran and waited, the others running and waiting",
   all(re.match(r"^🧮 heavy read t\d: memory \d+ -> \d+ MB \([+-]\d+\), ran \d+\.\d\d s, waited \d+\.\d\d s; "
                r"others \d+ running, \d+ waiting$", l) for l in _logl), _logl[0] if _logl else "")
ok("5. ...and later reads waited their turn", any(float(re.search(r"waited (\d+\.\d\d)", l).group(1)) >= 0.1 for l in _logl))
ok("5. the memory figure is read on this platform (Linux /proc, Windows working set)",
   isinstance(heavy_reads.memory_mb(), float) and heavy_reads.memory_mb() > 1)

# re-entrant: a read inside a read on the same thread takes no second slot, prints no second line
_hold_evt, _go = threading.Event(), threading.Event()


def _block():
    with heavy_reads.slot("blocker"):
        _hold_evt.set()
        _go.wait(5)


_blockers = [threading.Thread(target=_block) for _ in range(heavy_reads.SLOTS - 1)]
with quiet() as _out2:
    for th in _blockers:
        th.start()
    _hold_evt.wait(2)
    time.sleep(0.05)
    _t0 = time.perf_counter()
    with heavy_reads.slot("outer"):
        with heavy_reads.slot("inner"):
            with heavy_reads.slot("innermost"):
                pass
    _nested_s = time.perf_counter() - _t0
    _go.set()
    for th in _blockers:
        th.join()
_l2 = _out2.getvalue()
ok("5. ⭐ a read inside a read (the bulletin reads the month figures) runs in the slot it holds: no wait with every "
   "other slot taken, no second line", _nested_s < 1.0 and "heavy read outer:" in _l2 and "inner" not in _l2,
   f"{_nested_s:.2f} s")

# busy: no slot within WAIT_S
_keep_wait = heavy_reads.WAIT_S
heavy_reads.WAIT_S = 0.2
_go2 = threading.Event()
_started = threading.Barrier(heavy_reads.SLOTS + 1)


def _block2():
    with heavy_reads.slot("blocker"):
        _started.wait(2)
        _go2.wait(5)


_b2 = [threading.Thread(target=_block2) for _ in range(heavy_reads.SLOTS)]
with quiet() as _out3:
    for th in _b2:
        th.start()
    _started.wait(2)
    _busy = None
    try:
        main.public_map_data(profile=None)
    except Exception as e:      # noqa: BLE001
        _busy = e
    _go2.set()
    for th in _b2:
        th.join()
heavy_reads.WAIT_S = _keep_wait
ok("5. ⭐ a read that finds no slot in WAIT_S is answered busy: 503 with a Retry-After, and the log says so",
   getattr(_busy, "status_code", None) == 503 and (getattr(_busy, "headers", None) or {}).get("Retry-After") == "30"
   and "heavy read map-data: no slot after" in _out3.getvalue() and "answered busy" in _out3.getvalue(),
   repr(_busy))
ok("5. the busy words are plain and name no internals",
   main._heavy_busy().detail == "The map's figures are busy; try again in a minute.")
ok("5. ...and the slots are all free again afterwards",
   all(heavy_reads._sem.acquire(timeout=0.5) for _ in range(heavy_reads.SLOTS))
   and not heavy_reads._sem.acquire(blocking=False))
for _ in range(heavy_reads.SLOTS):
    heavy_reads._sem.release()
ok("5. heavy_reads.py names no team id, opens no network, and says why it exists",
   "IPT" not in read("backend/heavy_reads.py") and not re.search(r"\b(urllib|requests|socket)\b", read("backend/heavy_reads.py"))
   and "live-502-1021.md" in read("backend/heavy_reads.py"))

# =========================================================================== #
#  6. The endpoints, the health check, the gate                                #
# =========================================================================== #
for _path, _fn, _name in (("/api/public/month-kpis\")", "def public_month_kpis(", "month-kpis"),
                          ("/api/public/month-kpis/months\")", "def public_month_kpis_months(", "month-kpis/months"),
                          ("/api/public/map-data\")", "def public_map_data(", "map-data"),
                          ("/api/public/route-alternatives\")", "def public_route_alternatives(", "route-alternatives"),
                          ("/api/public/forecast-matrix\")", "def public_forecast_matrix(", "forecast-matrix"),
                          ("/api/public/areas/months\")", "def public_areas_months(", "areas/months")):
    _i = _mk.index('@app.get("' + _path)
    _b = _mk[_i:_mk.index("\n@app.", _i + 5)]
    ok(f"6. {_path[:-2]} holds a heavy-read slot", _fn in _b and f'with _heavy("{_name}"):' in _b)
ok("6. ⭐ /api/health is a coroutine (answered on the event loop, not in the busy thread pool) and still answers",
   asyncio.iscoroutinefunction(main.health)
   and asyncio.run(main.health()) == {"ok": True, "backend": "sqlite"})
ok("6. ...and it does no I/O (no db call in its body)",
   "db.query" not in _mk[_mk.index("async def health("):_mk.index("def _staff_request(")])
ok("6. the bulk read is behind the map gate like the month read (a map cookie or a staff session)",
   gate.scope_for("/api/public/month-kpis/months") == "map" == gate.scope_for("/api/public/month-kpis")
   and gate.decide("/api/public/month-kpis/months") == gate.decide("/api/public/month-kpis") != gate.ALLOW)
_mp = read("map/index.html")
ok("6. the map asks for the bulk read and keeps the month read as its fallback",
   "/public/month-kpis/months?unit=" in _mp and "/public/month-kpis?month=" in _mp)

remove_scratch_db(db, TMP)
# ---- 23 Oct 2026: the public abnormal loads per month (the user: the count on the public map's figures bar) ----
_abn = {m: ONE[m].get("abnormal_loads") for m in ONE}
ok("⭐ 23 Oct: every month carries abnormal_loads, the ids of the PUBLIC movements whose window touches it, appended last: the demo's "
   "approved AL001 (8–12 Mar 2027) in month 15 only; the pending crane and beams in none",
   all(isinstance(v, list) for v in _abn.values()) and _abn[15] == ["AL001"] and all(not v for m, v in _abn.items() if m != 15)
   and all(list(ONE[m].keys())[-1] == "abnormal_loads" for m in ONE), str({m: v for m, v in _abn.items() if v}))
ok("23 Oct: ...and the bulk read carries the same in every month",
   all(BULK["months"][str(m)].get("abnormal_loads") == _abn[m] for m in ONE))

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
