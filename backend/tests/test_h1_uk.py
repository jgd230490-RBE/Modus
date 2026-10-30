"""
H1, 2026-09-29 — UK localisation: a GB tenant sees no Estonian source, name or unit.

WHAT IS ASSERTED
----------------
  1. Providers per country: GB → DESNZ diesel + National Highways closures; EE → the EU
     bulletin + Tark Tee; NO country → typed diesel, no restriction provider (the
     pre-H1 fallback to Estonia is gone from every module).
  2. The demo tenant (GB, GBP, miles) imported into an empty tenant: every JSON value a
     GB page reads — /api/meta, /api/costing, /api/fuel-index, /api/restrictions/layers,
     /api/restrictions, /api/lookahead, /api/forecast-weeks/restrictions,
     /api/public/alignment — contains NO Estonian term, NO EU-bulletin term, NO "€" and
     NO "EE" country value. Same for the XLSX (read back with openpyxl) and the PDF
     (pdftotext) of the commit week.
  3. Source level: "Tark Tee" and "Maa-amet" reach a GB page only through code that is
     gated on the tenant's country or on the API's provider block (the guide, which
     documents both countries, is the deliberate exception).
  4. km/miles (HU5, per tenant): stored km, shown in the tenant's unit — the helpers in
     the app and the map, and the XLSX/PDF headers and figures.
  5. The GB vehicle set: lead names, the hidden list (Rigid 7.5t alone since the four EU
     type-approval names left the product on 11 Oct 2026), the two truck mixers, DESNZ 2026
     CO₂ factors with their source on every >17 t rigid and >33 t artic entry.
  6. The Mapbox token default in config.py equals the one in map/config.js; GB → Europe/London.
  7. The probes exist and are shaped for the deployment: /api/admin/diagnostics/fuel-index
     and the provider-aware /api/admin/diagnostics/restrictions.

WHAT THIS DOES NOT PROVE
------------------------
  * HTTP is stubbed; endpoints are called as functions (http_smoke.py has the real layer).
  * gov.uk (DESNZ) and the National Highways FeatureServer are NEVER called: both fetches
    run against fixtures shaped from their published schemas. The probes on Render are
    the first real run.
  * Nothing renders. The frontend and map assertions are source-level.

Run:  python3 backend/tests/test_h1_uk.py
"""
import io
import json
import os
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

TMP = tempfile.mkdtemp(prefix="wayscope_h1_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
# 12 Oct 2026 (C11 closed): the admin diagnostics REFUSE when ADMIN_TOKEN is unset, so the harness sets one
os.environ["ADMIN_TOKEN"] = "h1-admin-token"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import restrictions  # noqa: E402
import fuel  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import lookahead  # noqa: E402
import export  # noqa: E402
import here_routing  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
access.set_current("planner123")
# 17 Oct 2026 (demo redesign R2, D104): the harness pins its own date — the shipped demo's as-of date, Thu 26 Nov 2026
# (Nov W4), the week the package's history is typed up to — so the commit week, its lines and the figures below never
# move with the calendar (the old demo had no plan after the week of 28 Dec 2026)
from portable import pin_today, DEMO_AS_OF  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)

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


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    config.invalidate(); costing.invalidate()


def boot():
    reset_db()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate(); costing.invalidate()


def values_of(o, out=None):
    """Every string VALUE in a JSON-shaped object (keys are internal names, not shown)."""
    out = out if out is not None else []
    if isinstance(o, dict):
        for v in o.values():
            values_of(v, out)
    elif isinstance(o, (list, tuple)):
        for v in o:
            values_of(v, out)
    elif isinstance(o, str):
        out.append(o)
    return out


def js(o):
    """Round-trip through JSON, as the HTTP layer would."""
    return json.loads(json.dumps(o, default=str))


# Estonian names, EU-bulletin names and the euro must not reach a GB page. Case-insensitive.
FORBIDDEN = [r"tark\s?tee", r"tarktee", r"maa-?amet", r"estonia", r"eesti", r"tallinn",
             r"euro\s?oil\s?watch", r"oil bulletin", r"weekly oil", r"transpordiamet", r"€"]
FORBIDDEN_RX = re.compile("|".join(FORBIDDEN), re.IGNORECASE)


def leaks(o):
    vals = values_of(js(o))
    hits = [v[:80] for v in vals if FORBIDDEN_RX.search(v)]
    # a country VALUE of "EE" (never the lower-case 'ee' vehicle-label language key, which the
    # app hides for a non-Estonian tenant) or the Estonian time zone
    ee = [v for v in vals if v.strip() == "EE" or v.startswith("Europe/Tallinn")]
    return hits + ee


# =========================================================================== #
#  1. Providers per country — and the EE fallback is gone                       #
# =========================================================================== #
ok("fuel: GB → DESNZ (GBP/L), EE → the EU bulletin (EUR/L), NO → nothing, no country → nothing",
   fuel.provider_for("GB")["key"] == "desnz" and fuel.provider_for("EE")["key"] == "eu_bulletin"
   and fuel.provider_for("NO") is None and fuel.provider_for(None) is None
   and fuel.norm_country(None) == fuel.NO_COUNTRY)
ok("restrictions: GB → National Highways (100 m, dated, ROADWORKS), EE → Tark Tee (30 m, undated, TARK TEE)",
   restrictions.provider_for("GB")["key"] == "nh_closures" and restrictions.provider_for("GB")["match_m"] == 100.0
   and restrictions.provider_for("GB")["dated"] is True and restrictions.provider_for("GB")["flag_label"] == "ROADWORKS"
   and restrictions.provider_for("EE")["key"] == "tark_tee" and restrictions.provider_for("EE")["match_m"] == 30.0
   and restrictions.provider_for("EE")["dated"] is False and restrictions.provider_for("EE")["flag_label"] == "TARK TEE"
   and restrictions.provider_for("NO") is None and restrictions.provider_for(None) is None)
ok("config.RESTRICTION_PROVIDERS is read from restrictions.PROVIDERS (the two cannot drift)",
   config.RESTRICTION_PROVIDERS == set(restrictions.PROVIDERS) == {"EE", "GB"})
_srcs = {f: read(f) for f in ("backend/fuel.py", "backend/costing.py", "backend/derived.py", "backend/main.py",
                              "backend/export.py", "backend/restrictions.py", "backend/config.py")}
ok("🔴 no DEFAULT_COUNTRY anywhere in the backend — nothing falls back to Estonia",
   all("DEFAULT_COUNTRY" not in s for s in _srcs.values()))
ok("🔴 the frontend's fuel widget has no country fallback either", 'fuelS.country || "EE"' not in read("frontend/index.html"))

boot()
ok("a tenant with no country: no restriction provider, no automatic fuel index, typed only",
   restrictions.provider() is None and fuel.state(costing.settings()["fuel"]["country"])["no_country"] is True
   and costing.settings()["fuel"]["country"] == fuel.NO_COUNTRY
   and fuel.refresh(costing.settings()["fuel"]["country"], sync=True)["status"] == "manual_only")
_m0 = main.meta()["tenant"]
ok("...and /api/meta says so: no providers, unit km", _m0["fuel_provider"] is None and _m0["restrictions"] is None
   and _m0["restrictions_provider"] is False and _m0["distance_unit"] == "km")

# =========================================================================== #
#  2. The demo tenant: nothing Estonian reaches a GB page                       #
# =========================================================================== #
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
_fac = json.loads(next(r["value"] for r in DEMO["tables"]["config"] if r["key"] == "factors"))
ok("the demo package is GB / GBP / miles and its fuel country is GB",
   _fac["tenant"]["country"] == "GB" and _fac["tenant"]["currency"] == "GBP"
   and _fac["tenant"].get("distance_unit") == "mi"
   and json.loads(next(r["value"] for r in DEMO["tables"]["config"] if r["key"] == "costing"))["fuel"]["country"] == "GB",
   str(_fac["tenant"]))
ok("the demo package names no Estonian source anywhere in its values", not leaks(DEMO), str(leaks(DEMO))[:300])
boot()
res = tenant_package.import_tenant(DEMO, replace=True)
ok("the demo imports into an empty tenant", res.get("ok") is True, str(res)[:200])
config.invalidate(); costing.invalidate(); restrictions.clear_cache()
tn = main.meta()["tenant"]
ok("GB tenant: DESNZ and National Highways on /api/meta, £, miles",
   tn["country"] == "GB" and tn["fuel_provider"]["key"] == "desnz" and tn["restrictions"]["key"] == "nh_closures"
   and tn["currency_symbol"] == "£" and tn["distance_unit"] == "mi", str(tn))

# stub the two live sources with fixtures shaped from their published schemas
_CSV = ("Date,ULSP:  Pump price in pence/litre,ULSD:  Pump price in pence/litre,ULSP:  VAT (%) rate applicable,ULSD:  VAT (%) rate applicable\n"
        "14/09/2026,135.20,194.80,20,20\n21/09/2026,135.60,195.50,20,20\n")
fuel.fetch_desnz = lambda timeout=None: {"csv": _CSV, "csv_url": "https://assets.publishing.service.gov.uk/x.csv", "csv_title": "Weekly road fuel prices (CSV)"}
import time as _t
# NARROWED 17 Oct 2026 (R2, D104): restrictions' "current" filter reads the REAL clock (time.time()) while the look-ahead
# reads the pinned week, so the fixture closures are dated round BOTH: the live one from 2 days before the earlier of the
# two to 400 days after the later, the finished one ending 10 days before the earlier
import calendar as _cal
_real_ms = int(_t.time() * 1000)
_pin_ms = _cal.timegm(_PINNED.timetuple()) * 1000
_now_ms = min(_real_ms, _pin_ms)
_late_ms = max(_real_ms, _pin_ms)
_day = 86400000
# NARROWED 17 Oct 2026 (R2, D104, §3a): was the FIRST route by id, which had a line in every week of the 4-month demo; now
# the first route that HAS an approved line in the pinned commit week's month (R001, the Harborough platform stone)
import weeks as _wk  # noqa: E402
_CM = _wk.editable_week()[0]
_cw_routes = sorted({r["route_id"] for r in db.query(
    "SELECT route_id FROM forecasts WHERE tenant_id = ? AND month_index = ? AND status = 'Approved'", (db.current_tenant(), _CM))})
ok("D104: the pinned commit week (Nov W4 2026) has at least 2 routes with approved lines", len(_cw_routes) >= 2, str(_cw_routes))
_r1 = _cw_routes[0]
# bake the first route for every vehicle its forecast lines use, along the closure fixture below
_veh = [r["vehicle_type"] for r in db.query("SELECT DISTINCT vehicle_type FROM forecasts WHERE tenant_id = ? AND route_id = ?",
                                            (db.current_tenant(), _r1))] or ["Rigid 8-wheeler (32t)"]
for _v in _veh:
    network._upsert_geom(_r1, _v, "[[-0.905,52.499],[-0.8955,52.5052],[-0.885,52.515]]", 2.0, 0.1, None, leg="loaded", alt_index=0)
    network._upsert_geom(_r1, _v, "[[-0.885,52.515],[-0.8955,52.5052],[-0.905,52.499]]", 2.0, 0.1, None, leg="return", alt_index=0)


def _fake_nh_page(offset, count=restrictions.NH_PAGE, timeout=None):
    if offset:
        return {"type": "FeatureCollection", "features": []}
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.9, 52.5], [-0.89, 52.51]]},
         "properties": {"OBJECTID": 2, "description": "Lane closure for barrier works", "road_number": "A46",
                        "eventtype": "Lane closure", "natureofworks": "Barrier works", "formattedeventnumber": "NH-0002",
                        "scheduledplannedstartdate": _now_ms - 2 * _day, "scheduledplannedenddate": _late_ms + 400 * _day}},
        # 12 Oct 2026 (map review §2.2c (c)): a closure on the same route that ENDED ten days ago. Dropped by every
        # default read (the stored check, the look-ahead, /api/restrictions), kept only when a caller asks for the
        # past with include_expired — a past month on the public map's timeline.
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.905, 52.499], [-0.8955, 52.5052]]},
         "properties": {"OBJECTID": 1, "description": "Carriageway closure for resurfacing, finished", "road_number": "A6",
                        "eventtype": "Carriageway closure", "natureofworks": "Resurfacing", "formattedeventnumber": "NH-0001",
                        "scheduledplannedstartdate": _now_ms - 40 * _day, "scheduledplannedenddate": _now_ms - 10 * _day}}]}


# --- 5 Oct 2026, H2: demo v2 — what the stand needs is IN the data ------------------------
_T = DEMO["tables"]
ok("H2: the scheme is a road — tenant name, overlay note, discipline words; no railway term reaches a reader",
   "dualling" in _T["config"][0]["value"] or any("dualling" in c["value"] for c in _T["config"])
   and not re.search(r"track ballast|rail corridor|Melton South station|Rail and sleepers", json.dumps(_T, ensure_ascii=False))
   and [d["label"] for d in _T["disciplines"] if d["id"] == "superstructure"] == ["Pavement"]
   and [d["in_scope"] for d in _T["disciplines"] if d["id"] == "stations"] == [0])
ok("H2: every site has a gate at its own coordinates; the quarries and the town compound enter and leave by different gates",
   # NARROWED 14 Oct 2026 (civils materials): 17 gates — the batching plant's
   # RE-PINNED 17 Oct 2026 (demo redesign R2, §3a): 19 — the asphalt plant's and Welland Ready-Mix's; == one per site at least
   # RE-PINNED 22 Oct 2026 (abnormal loads, phase 3, D75): 21 — the precast works' and the crane depot's
   # RE-PINNED 28 Oct 2026 (simulation v2): 23 — the viaduct site's gate in and gate out
   # RE-PINNED 29 Oct 2026 (task 3c): 24 — the holding area's entrance
   len(_T["location_gates"]) == 24 and {g["location_id"] for g in _T["location_gates"]} == {l["id"] for l in _T["locations"]}
   and all(g["lat"] and g["lon"] for g in _T["location_gates"])
   and sorted(g["direction"] for g in _T["location_gates"] if g["location_id"] == "L001") == ["access", "egress"]
   and sorted(g["direction"] for g in _T["location_gates"] if g["location_id"] == "L005") == ["access", "egress"])
ok("H2: every route names its origin and destination gate",
   all(r["origin_gate_id"] and r["dest_gate_id"] for r in _T["routes"]))
# NARROWED 16 Oct 2026 (the user: "ensure there is a haul road drawn to every gate"): the demo also draws an ACCESS ROAD to
# each of its 17 gates (Z006-Z022, test_gate_access.py); the two haul roads ATTACHED to routes are still Z001 and Z002
_access = {g["access_zone_id"] for g in _T["location_gates"]}
ok("H2: two haul roads, spliced (HERE does not know them), attached to the routes that use them",
   # RE-PINNED 28 Oct 2026 (simulation v2): + the viaduct site's four roads INSIDE it (mode internal, never spliced into a route)
   [(z["id"], z["haul_mode"]) for z in _T["zones"] if z["kind"] == "haul_road" and z["id"] not in _access]
   == [("Z001", "splice"), ("Z002", "splice"), ("Z029", "internal"), ("Z030", "internal"), ("Z031", "internal"), ("Z032", "internal")]
   # RE-PINNED 17 Oct 2026 (R2, §3a): the Langton haul road is attached to EVERY route into Langton Compound (nine since the
   # four-year programme: + the asphalt, the two concrete plants, the precast and the 2030 coating-plant routes)
   and sorted((l["route_id"], l["zone_id"]) for l in _T["route_haul_roads"])
   == sorted([(r, "Z001") for r in ("R004", "R005", "R006", "R014", "R031", "R033", "R035", "R039", "R043")]
             + [("R016", "Z002"), ("R018", "Z002")])
   and {r["id"] for r in _T["routes"] if r["dest_id"] == "L006"} == {l["route_id"] for l in _T["route_haul_roads"] if l["zone_id"] == "Z001"})
# NARROWED 22 Oct 2026 (abnormal loads, phase 3, D75): 21 gates, the precast works' and the crane depot's among them
ok("16 Oct 2026: and one access road per gate (24 since 29 Oct, task 3c), all spliced haul roads, none attached to a route",
   len(_access) == 24 and all(z["kind"] == "haul_road" and z["haul_mode"] == "splice" for z in _T["zones"] if z["id"] in _access)
   and not ({l["zone_id"] for l in _T["route_haul_roads"]} & _access))
# RE-PINNED 17 Oct 2026 (R2, §3a, §1.8): the three geofences re-dated to the four-year programme (Z003 keeps its box and
# start date, ends with the junction build 17 Dec 2027; the Burrough limit runs the whole programme; the Melton works area
# Mar 2026 – Sep 2027), then the seven ADVISORY zones created after the access roads (Z025–Z031; Z027–Z033 since 22 Oct 2026,
# the two abnormal-load sites' access roads before them): nothing new steers routing
ok("H2: three geofences — a closure that re-routes (Tilton), an advisory 7.5 t village limit, an advisory works area — then seven dated zones, six advisory and Christmas trading 2027 re-routing (28 Oct)",
   [(z["id"], z["kind"], z["affects_routing"], z["starts_on"], z["ends_on"]) for z in _T["zones"] if z["kind"] != "haul_road"]
   == [("Z003", "closure", 1, "2026-10-05", "2027-12-17"), ("Z004", "weight_limit", 0, "2026-01-01", "2030-12-31"),
       ("Z005", "works", 0, "2026-03-01", "2027-09-30"),
       # RE-PINNED 28 Oct 2026 (simulation v2): Z033–Z039, after the viaduct site's two access roads and four internal roads
       ("Z033", "works", 0, "2026-05-01", "2028-05-31"), ("Z034", "works", 0, "2027-04-01", "2028-09-30"),
       ("Z035", "closure", 0, "2027-04-01", "2027-04-30"), ("Z036", "closure", 0, "2028-03-01", "2028-06-30"),
       ("Z037", "works", 0, "2029-06-01", "2029-10-31"),
       # NARROWED 28 Oct 2026 (the demo narrative's F4): Christmas trading 2027 now DIVERTS in its dates, as ticked on live
       ("Z038", "closure", 1, "2027-12-01", "2027-12-31"),
       ("Z039", "closure", 0, "2028-12-01", "2028-12-31")]
   and all("(fictional)" in (z["note"] or "") for z in _T["zones"] if z["kind"] != "haul_road")
   and "8 vehicles a day" in [z for z in _T["zones"] if z["id"] == "Z004"][0]["note"]
   and [z for z in _T["zones"] if z["id"] == "Z003"][0]["name"] == "A47 at the new Tilton junction: HGV diversion while the junction is built")
def _bbox(g):
    xs = [c[0] for c in g["coordinates"][0]]; ys = [c[1] for c in g["coordinates"][0]]
    return min(xs), min(ys), max(xs), max(ys)
_Z = {z["id"]: _bbox(json.loads(z["geometry"]) if isinstance(z["geometry"], str) else z["geometry"]) for z in _T["zones"] if z["kind"] != "haul_road"}
ok("H2: the Tilton closure box straddles the A47 as HERE baked it (52.620–52.622 N, west of the -0.922 turn) and is in force on the day of the bake, "
   "because a zone only steers routing while it applies today (zones.applies_on) — the 5 Oct live bake moved nothing with a 12 Oct start",
   _Z["Z003"][1] < 52.6208 < _Z["Z003"][3] and _Z["Z003"][0] < -0.949 < _Z["Z003"][2] and _Z["Z003"][3] < 52.6225
   and [z for z in _T["zones"] if z["id"] == "Z003"][0]["starts_on"] <= "2026-10-05")
ok("H2: the Burrough 7.5 t box straddles the lane the Stockpile North routes were baked along (-0.8879, 52.6993)",
   _Z["Z004"][0] < -0.8879 < _Z["Z004"][2] and _Z["Z004"][1] < 52.6993 < _Z["Z004"][3])
ok("H2: daily vehicle caps on the two village routes, so ROUTE_CAP has something to fire on",
   # RE-PINNED 17 Oct 2026 (R2, §3a, §1.8): the Burrough lane community agreement, 8 a day on each route (was 20 and 30)
   {r["id"]: r["max_vehicles_per_day"] for r in _T["routes"] if r["max_vehicles_per_day"]} == {"R016": 8, "R018": 8})
# NARROWED 17 Oct 2026 (demo redesign R2, §3a, §1.9): was "Oct W3 and W4 carry 22 lines, Oct W1/W2 44 actuals" — the
# 4-month demo's show week. Now the INVARIANT of the history typed to the as-of date (Thu 26 Nov 2026 = Nov W4): every
# approved line-month up to the as-of month has all of its weeks, nothing later is materialised, every approved
# line-week before the as-of week carries a typed actual and is confirmed, and the as-of week is confirmed for the
# North Team only (so Confirm is live for the other two)
_AWM, _AWW = 11, 4
_wk_by = {}
for _w in _T["forecast_weeks"]:
    _wk_by.setdefault((_w["route_id"], _w["month_index"], _w["discipline"], _w["section_id"]), {})[_w["week_index"]] = _w
_appr = [f for f in _T["forecasts"] if f["status"] == "Approved" and f["month_index"] <= _AWM]
_ipt_of = {(f["route_id"], f["month_index"], f["discipline"], f["section_id"]): f["ipt"] for f in _T["forecasts"]}
ok("H2: the history to the as-of week — every approved line-month to Nov 2026 has all its weeks, none later; every earlier "
   "line-week has an actual and is confirmed; the as-of week confirmed for the North Team only",
   _appr and all(sorted(_wk_by.get((f["route_id"], f["month_index"], f["discipline"], f["section_id"]), {}))
                 == list(range(1, _wk.weeks_in_month(f["month_index"]) + 1)) for f in _appr)
   and max(w["month_index"] for w in _T["forecast_weeks"]) == _AWM
   and all(w["actual_qty"] is not None and w["status"] == "confirmed" for w in _T["forecast_weeks"]
           if (w["month_index"], w["week_index"]) < (_AWM, _AWW))
   and {(_ipt_of[(w["route_id"], w["month_index"], w["discipline"], w["section_id"])], w["status"] == "confirmed")
        for w in _T["forecast_weeks"] if (w["month_index"], w["week_index"]) == (_AWM, _AWW)}
   == {("IPT1", True), ("IPT2", False), ("IPT3", False)},
   str(len(_appr)))
# NARROWED 14 Oct 2026 (the user took the recommendation): "the scheme and its plan are invented", was "nothing here is
# real" (the bulletin quotes real government figures); still "Fictional demo scheme" first, still under 121 characters
ok("H2: the tenant carries the demo notice, /api/meta serves it, and it validates as short text or null",
   # NARROWED 15 Oct 2026 (the user): the demo's bar wording is "Fictional scheme" behind the bar's DEMO badge
   main.meta()["tenant"]["demo_notice"] == "Fictional scheme"
   and "nothing here is real" not in json.dumps(DEMO, ensure_ascii=False)
   and 'DEMO_NOTICE = "Fictional scheme"' in open(os.path.join(BACKEND, "tools", "make_demo_tenant.py"), encoding="utf-8").read()
   and config.validate(dict(json.loads(DEMO["tables"]["config"][[c["key"] for c in DEMO["tables"]["config"]].index("factors")]["value"]), tenant={"name": "x", "demo_notice": "y" * 121})) != []
   and "demo_notice" in config.TENANT_DEFAULTS)
# 12 Oct 2026 (map review 2.1 / 2.3): "Report a concern" on the public map writes to a TYPED tenant address. The demo
# types none, so the map says no address has been typed; nothing invents one. One plain address or null.
_fac = dict(json.loads(DEMO["tables"]["config"][[c["key"] for c in DEMO["tables"]["config"]].index("factors")]["value"]))
ok("concern_email: a tenant field defaulting to null, and the demo tenant types none (the map shows a placeholder, never an invented address)",
   "concern_email" in config.TENANT_DEFAULTS and config.TENANT_DEFAULTS["concern_email"] is None
   and main.meta()["tenant"]["concern_email"] is None
   and not (_fac.get("tenant") or {}).get("concern_email"))
ok("concern_email: validated as ONE plain address or null — a list, a query string or a bare word is refused",
   config.validate(dict(_fac, tenant={"name": "x", "concern_email": "contact@scheme.example"})) == []
   and config.validate(dict(_fac, tenant={"name": "x", "concern_email": None})) == []
   and all(any("concern_email" in m for m in config.validate(dict(_fac, tenant={"name": "x", "concern_email": bad})))
           for bad in ("not an address", "a@b.example, c@d.example", "a@b.example?cc=x@y.example", "a@b", "x" * 250 + "@b.example", 7)))
ok("concern_email: tenant_settings serves a valid address trimmed, and drops an invalid one to null (the map then shows the placeholder)",
   config.tenant_settings(doc={"tenant": {"concern_email": "  contact@scheme.example "}})["concern_email"] == "contact@scheme.example"
   and config.tenant_settings(doc={"tenant": {"concern_email": "a@b.example; c@d.example"}})["concern_email"] is None
   and config.tenant_settings(doc={})["concern_email"] is None)
# NARROWED 11 Oct 2026 (the demo bar): the app carries the notice in the bar under its header on every view
# (DemoBar), not in a header badge, which is gone
ok("H2: the notice is on both exports (XLSX About row, PDF footer) and the app's demo bar under the header, and the map hides an empty rail layer",
   # NARROWED 13 Oct 2026 (D45): the footer line is red (the demo bar's #B91C1C), was grey bold
   '("Notice", _demo_notice() or "")' in read("backend/export.py")
   and """ft.insert(0, P(f'<font color=\"#{DEMO_FG_HEX}\"><b>' + E(_demo_notice()) + \"</b></font>\", st_grey))""" in read("backend/export.py")
   and '<span className="demo-bar-text" title={TENANT.demo_notice}>{TENANT.demo_notice}</span>' in read("frontend/index.html")
   and 'className="demo-badge' not in read("frontend/index.html") and "demo_notice: (tn.demo_notice || null)" in read("frontend/index.html")
   # REVERSED 28 Oct 2026 (task 0a, John): the map no longer has a rail layer to hide; no rail row at all
   and "railItem.hidden = !hasRail" not in read("map/index.html") and "Existing rail network" not in read("map/index.html")
   and "dn.textContent = TENANT.demo_notice" in read("map/index.html"))
# --- 30 Sep 2026: the national feed against baked routes must be pre-filtered by box -----
# The first GB run with baked routes put the live service at 100 % CPU for hours: 2,920
# closures × 170,000 vertices against 18 routes × 4 legs, vertex by segment. These pin the
# bounding-box short cut in _min_distance_km and that it never hides a real hit.
import random as _random
import time as _time
_random.seed(30)
_line = [[-0.905 + i * 0.0001, 52.499 + i * 0.00004] for i in range(500)]          # a 500-vertex HERE-like leg
_far = [{"type": "Feature", "geometry": {"type": "MultiLineString",
                                          "coordinates": [[[-0.23 + _random.random() * 0.01, 51.68 + _random.random() * 0.01] for _ in range(58)]]},
         "properties": {}} for _ in range(3000)]                                       # M25-sized, 90 km south
_near = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.9, 52.5], [-0.89, 52.51]]}, "properties": {}}
_calls = {"n": 0}
_orig_pts = restrictions._point_to_segment_km
def _counting(p, a, b):
    _calls["n"] += 1
    return _orig_pts(p, a, b)
restrictions._point_to_segment_km = _counting
try:
    _lb = restrictions._bbox(_line)
    _t0 = _time.time()
    _skipped = sum(1 for f in _far if restrictions._min_distance_km(f["geometry"], _line, max_km=0.1, line_bbox=_lb) is None)
    _dt = _time.time() - _t0
    ok("🔴 a closure whose box is further than the match distance is skipped without a single segment test",
       _skipped == 3000 and _calls["n"] == 0, f"skipped {_skipped}, segment tests {_calls['n']}")
    ok("🔴 …and 3,000 of them against a 500-vertex leg take well under a second, not hours", _dt < 1.0, f"{_dt:.2f}s")
    _calls["n"] = 0
    _d = restrictions._min_distance_km(_near["geometry"], [[-0.905, 52.499], [-0.8955, 52.5052], [-0.885, 52.515]], max_km=0.1)
    ok("🔴 a closure inside the box still goes through the exact test and is a hit", _d is not None and _d * 1000 <= 100 and _calls["n"] > 0, str(_d))
    ok("the box test is a lower bound on the exact distance (never hides a pair): 2,000 random pairs",
       all(restrictions._bbox_apart_km(restrictions._bbox([p]), restrictions._bbox([q])) <= _orig_pts(p, q, q) + 1e-9
           for p, q in (([-1 + _random.random() * 2, 51 + _random.random() * 4], [-1 + _random.random() * 2, 51 + _random.random() * 4]) for _ in range(2000))))
    ok("without max_km the old exact behaviour is unchanged (a far feature still gets a distance)",
       restrictions._min_distance_km(_far[0]["geometry"], _line) is not None)
    ok("check_route passes the match distance and the leg's box (source)",
       "max_km=max_km, line_bbox=line_bbox" in read("backend/restrictions.py") and "max_km = mm / 1000.0" in read("backend/restrictions.py"))
finally:
    restrictions._point_to_segment_km = _orig_pts

restrictions._nh_page = _fake_nh_page
fuel.refresh("GB", sync=True)
restrictions.refresh_async(sync=True)
ok("GB: the DESNZ row is stored (£1.955/L incl. VAT, £1.629 ex-VAT) and the NH check stored one hit on the baked route",
   (fuel.get_index("GB") or {}).get("eur_per_l") == 1.955 and fuel.state("GB")["ex_vat_per_l"] == 1.629
   and restrictions.stored_checks([_r1])[_r1]["hits"] and restrictions.stored_checks([_r1])[_r1]["status"] == "ok")

PAGES = {
    "/api/meta": main.meta(),
    "/api/costing": main.get_costing(),
    "/api/fuel-index": main.get_fuel_index(lazy=0),
    "/api/restrictions/layers": main.restriction_layers(),
    "/api/restrictions": json.loads(main.get_restrictions().body),     # NARROWED 30 Sep: a pre-serialised Response
    "/api/lookahead": main.lookahead_page(bucket="commit"),
    "/api/forecast-weeks/restrictions": main.forecast_week_restrictions(bucket="commit"),
    "/api/forecast-weeks/clashes": main.forecast_week_clashes(bucket="commit", restrictions_on=1),
    "/api/public/alignment": json.loads(main.public_alignment(_Request()).body),
    "/api/routes/{id}/restrictions": main.route_restrictions(_r1),
    "/api/admin/diagnostics/fuel-index": main.diagnostics_fuel_index(probe=False, token=os.environ["ADMIN_TOKEN"]),
    "/api/admin/diagnostics/restrictions (no probe)": restrictions.diagnostics(probe=False),
}
for path, payload in PAGES.items():
    lk = leaks(payload)
    ok(f"🔴 GB page {path}: no Estonian term, no EU-bulletin term, no €, no EE value", not lk, str(lk)[:240])
_la = PAGES["/api/lookahead"]
ok("GB look-ahead: the restriction source is National Highways with the ROADWORKS word and the week window",
   _la["clashes"]["sources"]["restrictions_provider"] == "nh_closures" and _la["clashes"]["sources"]["restrictions_label"] == "ROADWORKS"
   and _la["clashes"]["sources"]["restrictions_ui_label"] == "Road closures (National Highways)"
   and _la["clashes"]["sources"]["restrictions_week"] and len(_la["clashes"]["sources"]["restrictions_week"]) == 2)
_fi = PAGES["/api/fuel-index"]["index"]
ok("GB fuel index: provider DESNZ, unit GBP/L, attribution names gov.uk, VAT 20, ex-VAT derived",
   _fi["provider"]["key"] == "desnz" and _fi["unit"] == "GBP/L" and "gov.uk" in _fi["attribution"]
   and _fi["vat_pct"] == 20.0 and _fi["ex_vat_per_l"] == 1.629 and _fi["source"] == fuel.SOURCE_DESNZ, str(_fi)[:200])
ok("GB restrictions catalogue: one layer, planned road closures, 100 m, OGL attribution",
   [l["key"] for l in PAGES["/api/restrictions/layers"]["layers"]] == ["nh_closures"]
   and PAGES["/api/restrictions/layers"]["match_m"] == 100.0 and "Open Government Licence" in PAGES["/api/restrictions/layers"]["attribution"])
_r_ = main.get_restrictions()
_fc_ = restrictions.fetch_all(None, current_only=True)
ok("🔴 GET /api/restrictions is a pre-serialised JSON Response (not walked by FastAPI's encoder), cached per collection",
   getattr(_r_, "media_type", "") == "application/json" and isinstance(_r_.body, str)
   and json.loads(_r_.body)["type"] == "FeatureCollection"
   and restrictions.serialised(_fc_) is restrictions.serialised(_fc_))
_rr = PAGES["/api/routes/{id}/restrictions"]
ok("GB route check: the hit carries its dates, event number and the ROADWORKS word; verdict unknown (a closure, not a limit)",
   _rr["hits"] and _rr["hits"][0]["event_number"] == "NH-0002" and _rr["hits"][0]["from"] and _rr["hits"][0]["to"]
   and _rr["flag_label"] == "ROADWORKS" and _rr["hits"][0]["verdict"] == "unknown" and _rr["match_m"] == 100.0)
# 12 Oct 2026 (map review §2.2c (c)): the ENDED closure NH-0001 sits on the same route. Every default read drops it;
# include_expired keeps it, so a past month can list what applied then.
# (a hit is reported once per LEG — both legs of _r1 are baked along the same road, so each closure appears twice;
# the review's §2.2d notes that duplication, and these read the SET of event numbers)
_ev = lambda hits: sorted({h["event_number"] for h in hits})
ok("🔴 §2.2c: by default the ended closure is NOT in the route check — NH-0002 alone, and the check says one record was excluded",
   _ev(_rr["hits"]) == ["NH-0002"] and _rr["current_only"] is True and _rr["expired_or_future_excluded"] == 1,
   str(_ev(_rr["hits"])) + " " + str(_rr.get("expired_or_future_excluded")))
_ca = restrictions.check_all()
ok("§2.2c: check_all() default — the route's current hit only, current_only True, one record excluded, one feature checked",
   _ev(_ca["routes"][_r1]["hits"]) == ["NH-0002"] and _ca["current_only"] is True
   and _ca["expired_or_future_excluded"] == 1 and _ca["features_checked"] == 1, str(_ev(_ca.get("routes", {}).get(_r1, {}).get("hits", []))))
_cx = restrictions.check_all(current_only=False)
ok("⭐ §2.2c: check_all(current_only=False) lists the ENDED closure too — NH-0001 with its from/to in the past — and says so",
   _ev(_cx["routes"][_r1]["hits"]) == ["NH-0001", "NH-0002"] and _cx["current_only"] is False
   and _cx["expired_or_future_excluded"] == 0 and _cx["features_checked"] == 2
   and all(h["to"] and h["to"] < _t.strftime("%Y-%m-%d", _t.gmtime()) for h in _cx["routes"][_r1]["hits"] if h["event_number"] == "NH-0001"),
   str([(h["event_number"], h["from"], h["to"]) for h in _cx["routes"][_r1]["hits"]])[:300])
ok("§2.2c: GET /api/routes/restrictions?include_expired=1 is that call; the default is unchanged",
   _ev(main.all_route_restrictions(include_expired=True)["routes"][_r1]["hits"]) == ["NH-0001", "NH-0002"]
   and _ev(main.all_route_restrictions()["routes"][_r1]["hits"]) == ["NH-0002"])
ok("§2.2c: the stored check and the look-ahead still read CURRENT closures only (NH-0001 is in neither)",
   _ev(restrictions.stored_checks([_r1])[_r1]["hits"]) == ["NH-0002"]
   and "NH-0001" not in json.dumps(_la, default=str))
# §2.3: the national feed clipped to a window — the corridor's box keeps its closures, a window elsewhere keeps none
_corr = json.loads(main.get_restrictions(bbox="-1.0,52.4,-0.8,52.6", include_expired=True).body)
ok("§2.3: GET /api/restrictions?bbox=<the corridor>&include_expired=1 keeps both closures, clipped 0, window echoed",
   sorted(f["properties"]["event_number"] for f in _corr["features"]) == ["NH-0001", "NH-0002"] and _corr["clipped"] == 0
   and _corr["bbox"] == [-1.0, 52.4, -0.8, 52.6] and _corr["counts"] == {"nh_closures": 2}, str({k: _corr.get(k) for k in ("clipped", "bbox", "counts")}))
_far = json.loads(main.get_restrictions(bbox="-3.0,54.0,-2.0,55.0").body)
ok("§2.3: a window elsewhere keeps nothing and says what it clipped (1 — the default read had already dropped the ended one)",
   _far["features"] == [] and _far["clipped"] == 1 and _far["counts"] == {} and _far["total_records"] == 2)
_edge = json.loads(main.get_restrictions(bbox="-0.89,52.51,-0.5,53.0").body)
ok("§2.3: a window TOUCHING a closure's box at one corner keeps it (touching counts)",
   [f["properties"]["event_number"] for f in _edge["features"]] == ["NH-0002"] and _edge["clipped"] == 0)
try:
    main.get_restrictions(bbox="-0.8,52.4,-1.0,52.6")
    ok("§2.3: a window with west > east is refused", False)
except _HTTPException as e:
    ok("§2.3: a window with west > east is refused (400)", e.status_code == 400)
_ser_code = read("backend/restrictions.py").split("def serialised(")[1].split("\ndef ")[0].split('"""')[2]   # after the docstring
ok("12 Oct 2026: the serialised-body cache holds the collection it serialised and compares by identity, not by a reused id",
   "if hit and hit[0] is fc:" in _ser_code and "_SERIALISED[k] = (fc, body)" in _ser_code and "id(fc)" not in _ser_code)

# the exports, read back for real
try:
    import openpyxl
    xb = export.build_xlsx(_la)
    wb = openpyxl.load_workbook(io.BytesIO(xb), read_only=True)
    _xtext = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            _xtext.extend(str(c) for c in row if c is not None)
    _xall = "\n".join(_xtext)
    ok("GB XLSX: no Estonian term, no EU-bulletin term, no € anywhere on any sheet",
       not FORBIDDEN_RX.search(_xall) and not re.search(r"\bEE\b", _xall), str([t for t in _xtext if FORBIDDEN_RX.search(t)])[:200])
    _hdr = [c for c in _xtext]
    ok("GB XLSX (HU5): the day sheet's distance headers read mi/trip, mi/day and t·mi — not km",
       "mi/trip" in _hdr and "mi/day" in _hdr and "t·mi" in _hdr and "km/trip" not in _hdr and "t·km" not in _hdr)
    ok("GB XLSX: the Fuel sheet names DESNZ and the running rate per mile",
       any("DESNZ" in t for t in _xtext) and any("running £/mi" in t for t in _xtext))
except ImportError:
    for _ in range(3):
        ok("(XLSX read-back skipped — openpyxl not installed here)", True)
try:
    import reportlab  # noqa: F401
    pb = export.build_pdf(_la)
    from portable import pdf_text
    _ptxt = pdf_text(pb, "") if shutil.which("pdftotext") else ""
    if _ptxt:
        ok("GB PDF: no Estonian term, no EU-bulletin term, no € in the rendered text",
           not FORBIDDEN_RX.search(_ptxt), str(FORBIDDEN_RX.findall(_ptxt))[:200])
        ok("GB PDF (HU5): the week column is headed MI/TRIP and totals read t·mi",
           "MI/TRIP" in _ptxt and "t·mi" in _ptxt and "KM/TRIP" not in _ptxt)
    else:
        for _ in range(2):
            ok("(PDF text skipped — pdftotext missing)", True)
except ImportError:
    for _ in range(2):
        ok("(PDF skipped — reportlab not installed here)", True)

# 29 Sep 2026 first look on the LIVE demo tenant (miles, DESNZ): three wording leaks in the
# exports and one misleading caption. "km omitted" on every UNBAKED line, "Km from the baked
# HERE route" in the footer, "Bulletin date" on the Fuel sheet of a DESNZ tenant, and a PDF
# with nothing baked said "Mapbox could not be reached". Pinned here on the same GB page.
_KM_OK = re.compile(r"L/100\s?km")          # consumption stays per 100 km on purpose (README)
try:
    import openpyxl
    _xt = []
    for ws in openpyxl.load_workbook(io.BytesIO(export.build_xlsx(_la)), read_only=True).worksheets:
        for row in ws.iter_rows(values_only=True):
            _xt.extend(str(c) for c in row if c is not None)
    _km_leaks = [t for t in _xt if re.search(r"\b[Kk]m\b", _KM_OK.sub("", t))]
    ok("🔴 GB XLSX (miles): no 'km' word reaches a sheet except the L/100 km consumption line",
       not _km_leaks, str(_km_leaks)[:240])
    ok("GB XLSX (miles): an UNBAKED line says 'mi omitted', the footer says 'Miles from the baked HERE route'",
       any("mi omitted on that line" in t for t in _xt) and any("Miles from the baked HERE route" in t for t in _xt))
    ok("🔴 GB XLSX (DESNZ): the Fuel sheet never says 'bulletin' — the date row reads 'Published (week ending)'",
       not any(re.search(r"bulletin", t, re.IGNORECASE) for t in _xt)
       and "Published (week ending)" in _xt and "BAF base published (week ending)" in _xt, str([t for t in _xt if "ulletin" in t])[:200])
    _ee_cost = {"index_source": "eu_weekly_oil_bulletin", "fuel": {"country": "EE"}}
    ok("…while an Estonian tenant's sheet keeps 'Bulletin date' (the series IS a bulletin), a typed one 'Index date'",
       export._index_date_label(_ee_cost) == "Bulletin date"
       and export._index_date_label({"index_source": "manual", "fuel": {"country": "--"}}) == "Index date"
       and export._index_date_label({"index_source": "manual", "fuel": {"country": "GB"}}) == "Published (week ending)")
except ImportError:
    for _ in range(4):
        ok("(XLSX wording read-back skipped — openpyxl not installed here)", True)
try:
    import reportlab  # noqa: F401
    if shutil.which("pdftotext"):
        from portable import pdf_text, offline
        offline(export)   # the schematic branch everywhere: no live Mapbox call from a harness
        _pt = pdf_text(export.build_pdf(_la))
        ok("🔴 GB PDF (miles): no 'km' word in the rendered text except the L/100 km line",
           not re.search(r"\b[Kk]m\b", _KM_OK.sub("", _pt)), str(re.findall(r".{0,40}\b[Kk]m\b.{0,40}", _KM_OK.sub("", _pt)))[:240])
        _rg = export.route_geometries
        try:
            export.route_geometries = lambda page: []          # nothing baked at all
            _pt0 = pdf_text(export.build_pdf(_la))
        finally:
            export.route_geometries = _rg
        ok("🔴 PDF with nothing baked: the caption says so and does not blame Mapbox",
           "no baked route to draw" in _pt0 and "Mapbox could not be reached" not in _pt0, _pt0[:300])
        ok("…and with a baked route but no Mapbox, the schematic caption still names Mapbox (the branch the sandbox takes)",
           "schematic from the baked geometry" in _pt and "Mapbox could not be reached" in _pt)
    else:
        for _ in range(3):
            ok("(PDF wording skipped — pdftotext missing)", True)
except ImportError:
    for _ in range(3):
        ok("(PDF wording skipped — reportlab not installed here)", True)
_mp_src = read("map/index.html")
ok("🔴 the map's legend carries no first-tenant figure ('~60 km' unsurveyed, '7 package edges') — the words are generic",
   "~60" not in _mp_src and "7 package edges" not in _mp_src
   # NARROWED 28 Oct 2026 (task 0a, John: fewer words on the panel): both notes moved to the user guide §8.2
   and "Gaps in the survey are filled in." not in _mp_src and "Package edges · ticks from zoom 11" not in _mp_src)

# =========================================================================== #
#  3. Source level: Estonian things are gated                                   #
# =========================================================================== #
fe = read("frontend/index.html")
fe_code = "\n".join(l.split("//", 1)[0] if not re.search(r"https?://", l) else l for l in fe.splitlines())
ok("the staff app names Tark Tee only in comments — every label comes from the API's provider block",
   "Tark Tee" not in fe_code and "Estonian Transport Administration" not in fe
   and "TENANT.restrictions.short" in fe and "ttSrc.restrictions_ui_label" in fe)
ok("the staff app offers the Estonian orthophoto to an Estonian tenant only",
   'val !== "maaamet-ortho" || c === "EE"' in fe and "basemapsFor(TENANT.country).map" in fe and "{BASEMAPS.map(" not in fe)
ok("the staff app hides the tenant's hidden vehicles in its pickers and the EU label option for GB",
   "const vehShown = (v, keep) => !HIDDEN_VEHICLES.includes(v) || v === keep;" in fe
   and fe.count(".filter(v => vehShown(v") >= 4 and '(k === "eu" && String(TENANT.country || "").toUpperCase() !== "GB")' in fe)
# 29 Sep 2026 first look on the LIVE GB demo: the staff app still said "bulletin" (Dashboard
# status line, Config fuel widget), "km" on a miles tenant (Dashboard status line, hover hint,
# the model notes, the route form's help text), "the usual Estonian quote" on the route form,
# an "Estonian" label column on Config → Vehicles, a literal "Fair $£" in the Dashboard note,
# and the Submit form DEFAULTED to a hidden EU vehicle because the material categories list
# the N-category entries first. Pinned at source; the render harness covers the JSX.
import re as _re2
_fits = [m.start() for m in _re2.finditer(r"\.fitBounds\(", fe)]
ok("🔴 every fitBounds in the app is inside a try (30 Sep: a NaN bounds on the Look-ahead map white-screened the whole app)",
   # NARROWED 13 Oct 2026 (W1): four, the Routes / Zones map now frames the scheme's locations on first load
   # NARROWED 16 Oct 2026 (S7): five, the Dashboard's Simulation map frames the day's routes once a month
   # NARROWED 28 Oct 2026 (simulation v2): seven, the site view frames the chosen site and the whole scheme again
   len(_fits) == 7 and all("try {" in fe[max(0, i - 60):i] for i in _fits)
   and "try { m.fitBounds(b, { padding: 40, maxZoom: 12, duration: 0 }); store.framed = true; } catch(e){}" in fe, str([fe[max(0, i - 60):i] for i in _fits if "try {" not in fe[max(0, i - 60):i]])[:200])
# --- 5 Oct 2026: Appearance (Ink / Light / Dark) ------------------------------------------
_PAL = re.compile(r'(?:(?:hover|focus|disabled|group-hover|sm|md|lg):)?(?:bg|text|border|divide|ring|placeholder)-(?:white|black|transparent|current|\[color:[^\]]+\]|\[#[0-9a-fA-F]{3,8}\]|\[rgba?\([^\]]+\)\]|(?:slate|gray|red|amber|blue|emerald|green)-\d{2,3})(?:/\d{1,3})?')
_SKIP = re.compile(r'^(?:\w+:)?(?:text-white|bg-white/\d+|border-white/\d+|text-white/\d+|bg-black/\d+|\w+-transparent|\w+-current|(?:bg|text|border|ring)-\[color:var|ring-\[)')
_dark = fe[fe.index("/* DARK-REMAP-START"):fe.index("/* DARK-REMAP-END */")]
def _esc(u):
    for a, b in ((":", "\\:"), ("/", "\\/"), ("[", "\\["), ("]", "\\]"), ("(", "\\("), (")", "\\)"), (",", "\\,"), (".", "\\.")):
        u = u.replace(a, b)
    return u
_fe_wo = fe.replace(_dark, "")          # the utilities in the app markup, not the remap block itself
_uncovered = sorted({u for u in set(_PAL.findall(_fe_wo)) if not _SKIP.match(u) and ("." + _esc(u)) not in _dark})
ok("🔴 APPEARANCE: every Tailwind colour utility the app uses has a dark remap (generated block, html[data-theme=\"dark\"])",
   not _uncovered and _dark.count('html[data-theme="dark"]') >= 40, str(_uncovered)[:300])
ok("APPEARANCE: three looks as tokens — ink on :root, light = header tokens only, dark = a full palette with orange controls and color-scheme dark",
   '--hdr-logo:url("/brand/logo-header-on-dark.svg")' in fe and 'html[data-theme="light"]{' in fe and '--hdr-logo:url("/brand/logo-header-on-light.svg")' in fe
   and 'html[data-theme="dark"]{' in fe and "--navy:#FF8C14; --navy-deep:#F3F4F6; --blue:#FFA10A;" in fe and fe.count("color-scheme:dark;") == 1)
ok("APPEARANCE: the header reads header tokens, never a white literal — bar, lockup, rule, muted text, buttons, the language segment",
   ".brand-bar{background:var(--hdr-bg);color:var(--hdr-fg);" in fe and "content:var(--hdr-logo);" in fe and ".brand-rule{width:1px;height:28px;background:var(--hdr-rule);}" in fe
   and 'className="brand-bar shrink-0"' in fe and "bg-white/10" not in fe and "text-white/70" not in fe and "border-white/20" not in fe and "bg-white/25" not in fe)
ok("APPEARANCE: the picker is a 32 px button at the right of the header with a popover of menuitemradio items, closing on outside click and Escape",
   "function AppearancePicker()" in fe and "<AppearancePicker />" in fe and 'role="menuitemradio"' in fe and 'aria-haspopup="menu"' in fe
   and 'e.key === "Escape"' in fe and '.appearance-btn{width:32px;height:32px;' in fe and fe.index("<AppearancePicker />") < fe.index("Sign out\n"))
ok("APPEARANCE: the choice is per browser (localStorage modus_theme), applied before React mounts, an unknown value falls back to ink",
   'key: "modus_theme"' in fe and 'applyTheme(localStorage.getItem(THEME.key) || "ink", false)' in fe
   and 'if(!THEMES.some(([k]) => k === name)) name = "ink";' in fe and fe.index("applyTheme(localStorage.getItem") < fe.index("ReactDOM.createRoot"))
ok("APPEARANCE: charts rebuild on a change and read token colours — no literal blue left in the Dashboard's series",
   # 13 Oct 2026 (W16): narrowed — the chart also rebuilds on an accent change and once its box first has a size (W5)
   "}, [JSON.stringify(config), theme, accent, sized]);" in fe and 'window.Chart.defaults.color = tok("--muted"' in fe
   and 'backgroundColor: "#2563EB"' not in fe and 'backgroundColor: "#3B82F6"' not in fe and 'borderColor: "#2563EB"' not in fe and 'tok("--chart-1"' in fe)
ok("APPEARANCE: cards, the big-screen bar and the Look-ahead's white buttons read surface tokens — no literal white surface left in component CSS",
   ".card{background:var(--surface);" in fe and ".dash-wallbar{display:flex;flex-wrap:wrap;align-items:center;gap:7px;background:var(--surface);" in fe
   # NARROWED 27 Oct 2026 (pilot readiness F3 b): one exemption, the two-step QR code's frame — a QR code must be dark on
   # WHITE in either look or a phone camera cannot read it
   and 'background: "white"' not in fe and fe.count("background:#fff;") == 1 and ".auth-qr{display:inline-block;background:#fff;" in fe)
ok("APPEARANCE: the map's dark basemap and the exports are untouched — the exports keep the print palette (export.py has no theme code)",
   "data-theme" not in read("backend/export.py") and '["Dark", "mapbox://styles/mapbox/dark-v11"]' in fe)
ok("🔴 the Dashboard status line reads the tenant's unit word and dates the index 'published' / 'typed', never 'bulletin'",
   # 13 Oct 2026 (W3, narrowed): the same line in plain words ("leave out", not "exclude … unbaked")
   "· {DU()}, CO₂e and fair {CUR()} leave out the" in fe and "· km, CO₂e and fair" not in fe
   and '(${cost.index_source === "manual" ? "typed" : "published"} ${longDate(' in fe and "(bulletin ${" not in fe)
ok("🔴 the Config fuel widget dates the index 'published' / 'typed' like the compact card — no 'bulletin' word on a DESNZ screen",
   "`bulletin ${fuelDate(" not in fe and fe.count('? "published" : "typed"') >= 2)
ok("🔴 no 'km' in the Dashboard's hover hint or model notes, no '$' before the currency symbol",
   # 13 Oct 2026 (W6, narrowed): the route table's "on hover" hint left with the hover titles; the per-unit prices it
   # named are details lines, and their distance word is still DU()
   "{CUR()}/{DU()} on hover" not in fe and "{CUR()}/km on hover" not in fe
   and "parts.push(`${CUR()} ${(+distRate(u.per_km)).toFixed(2)}/${DU()}`)" in fe and "unitList(r.fairU)" in fe
   # 13 Oct 2026 (W3, narrowed): the Dashboard's model note left the screen for the technical guide; its info
   # boxes name both units ("per mile or km") and the tenant's own word stays in every figure's label
   and "{DU()}, cycle and vehicles from the baked HERE route" not in fe and "Fair {CUR()} = the cost model on Config" not in fe
   and "Fair ${CUR()} = the cost model on Config" not in fe and "a running cost per mile or km" in fe
   and "lorry-km      = trips × the routed (baked) route distance" in read("frontend/help/technical/index.html")
   and "+ {DU()} × running" in fe and "+ km × running" not in fe)
ok("🔴 the route form's rate help names no country and reads the tenant's unit",
   # NARROWED 22 Oct 2026 (UI fix 7, the user: fewer words): the help is one line and names no unit at all
   "usual Estonian quote" not in fe and 'Rates are added together. Blank = the target rate from Config, marked "target".' in fe)
# NARROWED 11 Oct 2026 (review): the column is gated on vehLangEditable("ee") — the COUNTRY rule alone. Gated on
# vehLangShown("ee") it also needed a vehicle to carry an Estonian name already, so an Estonian organisation on
# the new seed (English names only) could never type its first one. The header buttons keep vehLangShown.
ok("🔴 Config → Vehicles shows the Estonian label column to an Estonian tenant only",
   '.filter(h => h !== "Estonian" || vehLangEditable("ee"))' in fe and '{vehLangEditable("ee") && <td' in fe
   and 'const vehLangEditable = (k) => k === "en" || (k === "ee" && String(TENANT.country || "").toUpperCase() === "EE");' in fe
   and 'h !== "Estonian" || vehLangShown("ee")' not in fe and '{vehLangShown("ee") && <td' not in fe)
ok("🔴 the Submit form never defaults to a hidden vehicle (first SHOWN of the category's list)",
   "const firstShown = (list) => (list || []).find(v => !HIDDEN_VEHICLES.includes(v))" in fe
   and "useState(firstShown(vehicles))" in fe and "(firstShown(suggestedVehicles) || v)" in fe
   and "useState(vehicles[0] || \"\")" not in fe and "(suggestedVehicles[0] || v)" not in fe)
ok("🔴 the Look-ahead's UNBAKED text reads the tenant's unit (clashes._dist_word), never a fixed 'km'",
   "km omitted on that line" not in read("backend/clashes.py") and "{_dist_word()} omitted on that line" in read("backend/clashes.py"))
mp = read("map/index.html")
ok("the map hides the Estonian orthophoto unless the tenant is Estonian and labels Satellite as Aerial for GB",
   "bm.hidden = (TENANT.country || '').toUpperCase() !== 'EE';" in mp
   and "'Aerial' : 'Satellite'" in mp)   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): the basemap names no longer say Mapbox
ok("the map's restriction panel heading and source come from the API's provider",
   "cat.provider.ui_label" in mp and "restriction-heading" in mp and "Estonian Transport Administration" not in mp.split("<script>")[0])
hp = read("frontend/help/index.html")
ok("the guide documents BOTH providers and both diesel series (the one page that may name Estonia)",
   "National Highways" in hp and "Tark Tee" in hp and "DESNZ" in hp and "ROADWORKS" in hp)

# =========================================================================== #
#  4. km / miles (HU5)                                                          #
# =========================================================================== #
ok("config: distance_unit validated (km|mi), default km, stored on the tenant block",
   config.DISTANCE_UNITS == ("km", "mi") and abs(config.KM_PER_MILE - 1.609344) < 1e-9
   and config.TENANT_DEFAULTS["distance_unit"] == "km")
_doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
_doc["tenant"]["distance_unit"] = "furlongs"
ok("...a unit that is not km or mi is refused", not config.save(_doc, by="test")["ok"])
ok("export: km → mi at the sheet boundary only (60 km → 37.28 mi; £2/km → £3.22/mi); km tenant unchanged",
   abs(export._dist(60.0) - 37.282) < 0.01 and abs(export._dist_rate(2.0) - 3.219) < 0.01 and export._du() == "mi"
   and export._tkm() == "t·mi")
ok("the app's helpers convert at the display boundary (dist, distRate, distInRate, speed) and the map's (distU, fmtDist)",
   all(x in fe for x in ("const KM_PER_MI = 1.609344;", "const dist = (km) =>", "const distRate = (perKm) =>",
                          "const distInRate = (perUnit) =>", "const speed = (kph) =>", "const fmtDist = (km, dp) =>"))
   and all(x in mp for x in ("const KM_PER_MI = 1.609344;", "const distU = (km) =>", "const fmtDist = (km, dp) =>")))
ok("the app types per-distance rates in the tenant's unit and stores per km (route form, target rate, running coefficient)",
   fe.count("distInRate(") >= 3 and "rate_eur_per_km: route.rate_eur_per_km == null" in fe)

# =========================================================================== #
#  5. The GB vehicle set and the 2026 CO₂ factors                               #
# =========================================================================== #
F = conversions.load_factors()
lead = conversions.planning_vehicle_names(F)
hidden = conversions.hidden_vehicle_names(F)
# NARROWED 11 Oct 2026 (EU vehicles removed): the user removed the four EU type-approval names from the
# product, so the GB demo hides Rigid 7.5t alone and carries no N3 name at all. Nothing ELSE was removed.
ok("GB lead vehicles are the UK trade names, Rigid 7.5t is the one hidden, and no EU type-approval name is left",
   lead[:3] == ["Rigid 8-wheeler (32t)", "Rigid 6-wheeler (26t)", "Artic Tipper (44t)"]
   and "Truck mixer 8 m³ (32t)" in lead and hidden == ["Rigid 7.5t"]
   and not any(n.startswith("N3 ") for n in conversions.vehicle_names(F))
   and len(hidden) == 1 and all(h in conversions.vehicle_names(F) for h in hidden)
   and set(lead).isdisjoint(hidden), str((lead, hidden)))
_EU4 = ("N3 lorry (BA) 4-axle TPMLM 32 t tipper", "N3 lorry (BA) 4-axle mixer 32 t",
        "N3 tractor (BC) + O4 semi (DA) GCW 40 t", "N3 tractor (BC) + O4 tipping semi (DA) GCW 40/44 t")
_demo_txt = read("demo/uk-corridor.package.json")
ok("11 Oct 2026: ⭐ the demo package carries none of the four EU type-approval names or their codes, anywhere",
   not any(n in _demo_txt for n in _EU4)
   and not any(t in _demo_txt for t in ("N3 lorry", "N3 tractor", "TPMLM", "O4 semi", "O4 tipping", '"V07"', '"V10"', '"V11"', '"V12"')))
ok("11 Oct 2026: ...no vehicle in it carries a code, an alias or a non-English label, and its planning list is the UK six, flagged",
   not any(isinstance(v, dict) and (v.get("code") or v.get("aliases") or set(v.get("labels") or {}) - {"en"})
           for v in F["vehicles"].values())
   and F["planning_vehicles"][0] == "Rigid 8-wheeler (32t)" and len(F["planning_vehicles"]) == 6
   and all(F["vehicles"][n].get("planning_vehicle") is True for n in F["planning_vehicles"]))
ok("11 Oct 2026: the GB demo is offered English vehicle names only, so the header shows no language buttons",
   main.meta()["vehicle_labels"]["langs"] == ["en"] and main.meta()["vehicle_labels"]["fallbacks"] == {})
ok("/api/meta carries hidden_vehicles and the GB lead list", main.meta()["hidden_vehicles"] == hidden
   and main.meta()["planning_vehicles"] == lead)
V = F["vehicles"]
ok("the two GB truck mixers carry a stated payload basis (ASSUMPTION), drum m³ and the rigid CO₂ factor",
   V["Truck mixer 8 m³ (32t)"]["payload_t"] == 18.0 and V["Truck mixer 8 m³ (32t)"]["payload_m3"] == 7.5
   and "ASSUMPTION" in V["Truck mixer 8 m³ (32t)"]["_payload_basis"]
   and V["Truck mixer 6 m³ (26t)"]["payload_t"] == 14.4 and V["Truck mixer 6 m³ (26t)"]["gvw_t"] == 26)
_rigid = ("Rigid 4-wheeler (18t)", "Rigid 6-wheeler (26t)", "Rigid 8-wheeler (32t)", "Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)")
_artic = ("Artic Tipper (44t)", "Artic Flatbed (44t)")
ok("DESNZ 2026: rigid >17 t 0.99773 and artic >33 t 0.93939 kg CO₂e/km, average laden, with the source on every entry",
   all(V[k]["emissions_kg_co2e_per_km"] == 0.99773 and "DESNZ/DEFRA 2026" in V[k]["_emissions_basis"] for k in _rigid)
   and all(V[k]["emissions_kg_co2e_per_km"] == 0.93939 and "DESNZ/DEFRA 2026" in V[k]["_emissions_basis"] for k in _artic))
ok("...the laden/empty pair is stored with the figure and says it is not read by code yet",
   V["Rigid 8-wheeler (32t)"]["emissions_kg_co2e_per_km_empty"] == 0.77910 and V["Rigid 8-wheeler (32t)"]["emissions_kg_co2e_per_km_laden"] == 1.11639
   and V["Artic Tipper (44t)"]["emissions_kg_co2e_per_km_empty"] == 0.65383 and "NOT read by code yet" in V["Artic Tipper (44t)"]["_emissions_basis"])
# REVERSED (10 Oct 2026, carbon planner): the flat file v1.2 has been read; the note says so, with the row IDs
ok("...and the file says the figures were VERIFIED on 10 Oct 2026 against the gov.uk flat file, with the row IDs",
   "Verified 10 Oct 2026 against the gov.uk flat file v1.2" in V["Rigid 8-wheeler (32t)"]["_emissions_basis"]
   and "5_304_3120_4_1" in V["Rigid 8-wheeler (32t)"]["_emissions_basis"]
   and not any("VERIFY" in (v.get("_emissions_basis") or "") for v in V.values() if isinstance(v, dict)))
# 12 Oct 2026 (B2): the fallback is a PUBLISHED figure too — the 2026 set's average across all
# non-refrigerated diesel HGVs, average laden — and the file, the constant and the map agree on it
ok("B2: _default is the published Average-HGV 0.89743 (was an unpublished 0.97), the same figure as conversions.FALLBACK_KG_CO2E_PER_KM",
   V["_default"]["emissions_kg_co2e_per_km"] == 0.89743 == conversions.FALLBACK_KG_CO2E_PER_KM
   and "All HGVs" in V["_default"]["_emissions_basis"] and "DESNZ/DEFRA 2026" in V["_default"]["_emissions_basis"])
ok("B2: ...and every per-km reader resolves an unknown GB vehicle to it — _emissions, the flat factors /api/meta serves",
   conversions._emissions(F, "No such lorry") == 0.89743
   and main.meta()["factors"]["vehicle_emissions_kg_co2e_per_km"]["_default"] == 0.89743
   and main.meta()["factors"]["vehicle_emissions_kg_co2e_per_km"]["Artic Tipper (44t)"] == 0.93939)
# config.validate() returns the PROBLEMS (a list of sentences; empty = fine)
ok("a vehicle_sets entry naming an unknown vehicle, or a name both led and hidden, is refused",
   any("No such lorry" in x for x in config.validate(dict(_doc, tenant=dict(_doc["tenant"], distance_unit="mi"),
                                                          vehicle_sets={"GB": {"lead": ["No such lorry"], "hide": []}})))
   and any("both lead and hidden" in x for x in config.validate(dict(_doc, tenant=dict(_doc["tenant"], distance_unit="mi"),
                                                                     vehicle_sets={"GB": {"lead": ["Artic Tipper (44t)"], "hide": ["Artic Tipper (44t)"]}})))
   and not config.validate(dict(_doc, tenant=dict(_doc["tenant"], distance_unit="mi"))))

# =========================================================================== #
#  6. Token and time zone                                                       #
# =========================================================================== #
_js_tok = re.search(r'MAPBOX_TOKEN:\s*"([^"]+)"', read("map/config.js")).group(1)
ok("🔴 config.MAPBOX_TOKEN_DEFAULT equals the token in map/config.js (the revoked one is gone)",
   config.MAPBOX_TOKEN_DEFAULT == _js_tok and _js_tok.startswith("pk.")
   and "Y21xbnJzaTRrMDYyOTJxcXowczRxNTlxdyJ9" not in read("backend/config.py"))
ok("GB → Europe/London for the departure-time probe", here_routing.COUNTRY_TZ.get("GB") == "Europe/London"
   and "Europe/London" in here_routing.default_departure_times(country="GB")[1])

# =========================================================================== #
#  7. The probes                                                                #
# =========================================================================== #
_pf = main.diagnostics_fuel_index(probe=True, token=os.environ["ADMIN_TOKEN"])
ok("the fuel-index probe runs the DESNZ path inline and shows the resolved CSV and the parsed row",
   _pf["provider"]["key"] == "desnz" and _pf["probe"]["ok"] is True and _pf["probe"]["parsed"]["eur_per_l"] == 1.955
   and _pf["probe"]["detail"]["csv_url"].endswith(".csv") and _pf["urls"] == [fuel.DESNZ_CONTENT_API])
_pr = restrictions.diagnostics(probe=True)
ok("the restrictions probe on a GB tenant shows the NH field map, the raw property names and the mapped dates",
   _pr["provider"]["key"] == "nh_closures" and "field_map" in _pr and _pr["probe"]["sample_dates"]["from"]
   and "scheduledplannedstartdate" in _pr["probe"]["sample_property_names"])
ok("the probes are behind the admin check and shipped in main.py",
   '@app.get("/api/admin/diagnostics/fuel-index")' in _srcs["backend/main.py"]
   and "def diagnostics_fuel_index(" in _srcs["backend/main.py"] and "_nh_diagnostics(probe)" in _srcs["backend/restrictions.py"])

# --- 13 Oct 2026: D45 — the demo notice on the exports and the map password page takes Option A ------------------
_xsrc = read("backend/export.py")
ok("⭐ D45: export.py's demo colours are Option A (grey #F1F5F9, red #B91C1C text, #DC2626 rule), one place",
   "DEMO_BG_RGB = (0xF1 / 255, 0xF5 / 255, 0xF9 / 255)" in _xsrc and "DEMO_FG_RGB = (0xB9 / 255, 0x1C / 255, 0x1C / 255)" in _xsrc
   and "DEMO_RULE_RGB = (0xDC / 255, 0x26 / 255, 0x26 / 255)" in _xsrc and 'DEMO_FG_HEX, DEMO_BG_HEX = "B91C1C", "F1F5F9"' in _xsrc)
ok("D45: every PDF frame passes the notice in the demo red, and the week sheet now carries it in its frame too (it was in the footer only)",
   # NARROWED 13 Oct 2026 (W15): the bulletin's frame passes the notice under its brand band, in Inter (two frames at
   # H - 25 mm became one plus the bulletin's)
   _xsrc.count("8.5, DEMO_FG_RGB, H - 25 * mm) if notice else None)") == 1 and "8.5, NAVY_RGB, H - 25 * mm" not in _xsrc
   and 'notice=((_pdf_safe(notice), _BF("bold"), 8.5, DEMO_FG_RGB, H - band["height"] - 8.5 * mm)' in _xsrc
   and 'notice=((_pdf_safe(_demo_notice()), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 22.5 * mm)' in _xsrc
   and "top, bottom = (25 if _demo_notice() else 20) * mm, 12 * mm" in _xsrc)
# the frame itself, drawn on a recording canvas: the band, the rule, the tag, the words
class _RecCanvas:
    def __init__(self): self.calls, self.fill = [], None
    def __getattr__(self, name):
        def rec(*a, **k):
            if name == "setFillColorRGB": self.fill = tuple(round(x, 3) for x in a)
            self.calls.append((name, a, k, self.fill))
        return rec
    def stringWidth(self, t, f, s): return 6.0 * len(t)
class _Doc: page = 1
_rc = _RecCanvas()
export.page_frame(595.0, 842.0, 40.0, 40.0, "T", rule_y=800, title_font=("Helvetica-Bold", 13), title_y=790,
                  notice=("Fictional demo scheme", "Helvetica-Bold", 8.5, export.NAVY_RGB, 770))(_rc, _Doc())
_grey, _red = tuple(round(x, 3) for x in export.DEMO_BG_RGB), tuple(round(x, 3) for x in export.DEMO_FG_RGB)
_rects = [(c[1], c[3]) for c in _rc.calls if c[0] == "rect"]
_strs = [(c[1][2], c[3]) for c in _rc.calls if c[0] == "drawString"]
ok("⭐ D45: page_frame draws the notice as a grey band the width of the page, a red DEMO tag in white, the words in red",
   any(a[:4] == (40.0, 767, 515.0, 12.5) and f == _grey for a, f in _rects)
   and any(f == _red for a, f in _rects[1:]) and ("DEMO", (1, 1, 1)) in _strs and ("Fictional demo scheme", _red) in _strs,
   str(_strs)[:200])
ok("...with the red rule under the band, and no notice means no band (a real tenant's PDF is unchanged)",
   ("setStrokeColorRGB", tuple(export.DEMO_RULE_RGB)) in [(c[0], c[1]) for c in _rc.calls]
   and ("line", (40.0, 767, 555.0, 767)) in [(c[0], c[1]) for c in _rc.calls])
_rc0 = _RecCanvas()
export.page_frame(595.0, 842.0, 40.0, 40.0, "T", rule_y=800, title_font=("Helvetica-Bold", 13), title_y=790)(_rc0, _Doc())
ok("...(no notice: no rect drawn at all)", not [c for c in _rc0.calls if c[0] == "rect"])
try:
    import openpyxl
    _rn = export._demo_notice
    export._demo_notice = lambda: "Fictional demo scheme · nothing here is real"
    try:
        _wb = openpyxl.load_workbook(io.BytesIO(export.build_xlsx(_la)))
    finally:
        export._demo_notice = _rn
    _ab = _wb["About"]
    _nc = [r[1] for r in _ab.iter_rows() if r[0].value == "Notice"][0]
    ok("D45: the XLSX About sheet's notice is red bold on the grey (the demo bar's colours)",
       _nc.value == "Fictional demo scheme · nothing here is real" and _nc.font.bold
       and str(_nc.font.color.rgb).endswith("B91C1C") and str(_nc.fill.fgColor.rgb).endswith("F1F5F9"),
       f"{_nc.font.color.rgb if _nc.font.color else None} {_nc.fill.fgColor.rgb}")
except ImportError:
    ok("(XLSX notice read-back skipped — openpyxl not installed here)", True)
_gate = read("backend/main.py")
ok("D45: the map password page's notice takes the same colours and the red DEMO tag",
   "background:#F1F5F9; color:#B91C1C; border:1px solid #DC2626;" in _gate and "#FFF7ED" not in _gate
   and '.demo-notice::before { content:"DEMO"; content:"DEMO" / ""; display:inline-block;' in _gate)

# ---- 13 Oct 2026 (W16, bundle E; D39): every accent × look, every text / control / mark pair -------------------
# The tokens are read from the <style> exactly as the browser cascades them (:root, then the dark block, then the
# accent's own block). Text must be 4.5:1 (WCAG 1.4.3), a control's edge and a chart mark 3:1 (1.4.11). The status
# colours must be byte-identical in all twelve combinations. The colour-blind separation of the series is pinned in
# parse_frontend.js (the same method the 10 and 11 Oct palettes were chosen by).
import re as _re
_css = _re.search(r"<style>([\s\S]*?)</style>", fe).group(1)
def _blk(sel):
    i = _css.find(sel + "{")
    return None if i < 0 else _css[i + len(sel) + 1:_css.find("}", i)]
def _tk(b):
    return {k: v.strip() for k, v in _re.findall(r"--([a-z0-9-]+):([^;]+);", b or "")}
_ROOT, _DARK, _LIGHTHDR = _tk(_blk(":root")), _tk(_blk('html[data-theme="dark"]')), _tk(_blk('html[data-theme="light"]'))
def _eff(acc, look):
    t = dict(_ROOT)
    if look == "light":
        t.update(_LIGHTHDR)
    if look == "dark":
        t.update(_DARK)
        if acc in ("blue", "blue-shades"):   # one shared dark block (Blue shades in Dark draws Blue's series)
            t.update(_tk(_blk('html[data-theme="dark"][data-accent="blue"],html[data-theme="dark"][data-accent="blue-shades"]')))
        elif acc != "orange":
            t.update(_tk(_blk(f'html[data-theme="dark"][data-accent="{acc}"]')))
    else:
        if acc != "orange":
            t.update(_tk(_blk(f':root:not([data-theme="dark"])[data-accent="{acc}"]')))
        if look == "ink":
            t.update(_tk(_blk(f'html[data-theme="ink"][data-accent="{acc}"]')))
    return t
def _rgb(c):
    c = c.strip()
    if c.startswith("#"):
        return [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)], 1.0
    m = _re.match(r"rgba\(([\d.]+),([\d.]+),([\d.]+),([\d.]+)\)", c.replace(" ", ""))
    return [float(m.group(i)) / 255 for i in (1, 2, 3)], float(m.group(4))
def _over(fg, bg):            # an rgba token laid over its surface
    (f, a), (b, _) = _rgb(fg), _rgb(bg)
    return "#" + "".join(f"{round((a * x + (1 - a) * y) * 255):02X}" for x, y in zip(f, b))
def _lum(c):
    v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in _rgb(c)[0]]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
def _cr(a, b):
    x, y = sorted([_lum(a), _lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)
_ACC = ["orange", "blue", "blue-shades", "orange-shades"]
_bad = []
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        surf, bg = t["surface"], t["bg"]
        chip = _over(t["navy-soft"], t["surface"])
        pairs = [("button text on the button", t["action-fg"], t["action"], 4.5),
                 ("a button's edge on the page", t["action"], bg, 3.0),
                 ("the kicker (action colour) on the page", t["action"], bg, 4.5),
                 ("a link / active control on a card", t["navy"], surf, 4.5),
                 ("a link on the page", t["navy"], bg, 4.5),
                 ("text on a filled control (is-on)", t["control-fg"], t["navy"], 4.5),
                 ("a chip's text on its tint", t["navy"], chip, 4.5),
                 ("the header's text on the header", t["hdr-fg"], t["hdr-bg"], 4.5)]
        pairs += [(f"chart series {i} on a card", t[f"chart-{i}"], surf, 3.0) for i in range(1, 6) if t[f"chart-{i}"].upper() != t["chart-none"].upper()]
        for name, a, b, need in pairs:
            r = _cr(a, b)
            if r < need:
                _bad.append(f"{_a}/{_l}: {name} {a} on {b} = {r:.2f} < {need}")
ok("W16: 🔴 all 12 looks × accents pass every pair — text 4.5:1, control edges and chart marks 3:1 (buttons, kicker, links, "
   "filled controls, chips, header, series 1–5)", not _bad, "; ".join(_bad[:6]))
ok("W16: the status colours are byte-identical in all 12 combinations (the accents never touch them)",
   len({tuple(_eff(a, l)[k] for k in ("green", "gold", "red")) for a in _ACC for l in ("ink", "light")}) == 1
   and len({tuple(_eff(a, "dark")[k] for k in ("green", "gold", "red")) for a in _ACC}) == 1)
ok("W16: the brief's 'Orange primary' button #FF8C14 would fail on white (2.33:1, under 3:1) — so it is not used on the light looks",
   round(_cr("#FF8C14", "#FFFFFF"), 2) == 2.33 and all(_eff(a, l)["action"].upper() != "#FF8C14" for a in _ACC for l in ("ink", "light")))
ok("W16: Blue shades' navy header is the Ink look's only (white on it 10.36:1); the Light look keeps its white header",
   _eff("blue-shades", "ink")["hdr-bg"] == "#1E3A8A" and round(_cr("#FFFFFF", "#1E3A8A"), 2) == 10.36
   and _eff("blue-shades", "light")["hdr-bg"] == "#FFFFFF" and _eff("blue", "ink")["hdr-bg"] == "#1F2024")

# --- 17 Oct 2026: UI fix 2 (claude/ui-fix-dark) — the dark look's contrast failures that needed no decision -------------
# (notes/ui-audit-findings-1016.md, findings 1, 2 and 6's button). Ratios by the WCAG relative-luminance formula above.
# Finding 6: the Confirm week button has its own pair in every look. The status WORDS keep --green (open question 2).
_bad6 = []
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        for name, a, b, need in [("the Confirm week button's text on the button", t["ok-btn-fg"], t["ok-btn"], 4.5),
                                  ("the Confirm week button's edge on the page", t["ok-btn"], t["bg"], 3.0)]:
            r = _cr(a, b)
            if r < need:
                _bad6.append(f"{_a}/{_l}: {name} {a} on {b} = {r:.2f} < {need}")
ok("UI fix 2 (#6): the Confirm week pair --ok-btn / --ok-btn-fg reads 4.5:1 in all 12 looks × accents and 3:1 against the page — ink #047857 / white 5.48:1, dark #34D399 / #1F2024 8.47:1",
   not _bad6 and _ROOT["ok-btn"] == "#047857" and _ROOT["ok-btn-fg"] == "#FFFFFF" and _DARK["ok-btn"] == "#34D399" and _DARK["ok-btn-fg"] == "#1F2024"
   and round(_cr("#FFFFFF", "#047857"), 2) == 5.48 and round(_cr("#1F2024", "#34D399"), 2) == 8.47, "; ".join(_bad6[:4]))
ok("...only :root and the dark block define the pair (no accent touches it), and white on --green — the old button — fails 4.5:1 in every look (3.77 ink, 1.92 dark), which is why the words stay an open question",
   _css.count("--ok-btn:") == 2 and _css.count("--ok-btn-fg:") == 2
   and all(_cr("#FFFFFF", _eff(a, l)["green"]) < 4.5 for a in _ACC for l in ("ink", "light", "dark"))
   and round(_cr("#FFFFFF", _eff("orange", "ink")["green"]), 2) == 3.77 and round(_cr("#FFFFFF", _eff("orange", "dark")["green"]), 2) == 1.92)
# Finding 1: a filled control is `text-white` beside an INLINE background (no bg-[color:var(--navy)] utility since 7 Oct, so
# the old remap selector matched nothing and every primary button in Dark was white on orange, 2.33:1). The rule at the end
# of the DARK-REMAP block matches the inline form; here every text-white in the markup is classified by the fill it sits on.
_TW = re.compile(r"text-white(?!/)")
# 22 Oct 2026 (UI fix 6, card 6): one more known fill, the haul-road buttons' var(--haul-text) (decision 13)
_FILLS = [("navy", 'var(--navy)'), ("blue", 'var(--blue)'), ("slate-800", "bg-slate-800"), ("team palette", "IPT_PALETTE_C"),
          ("zone colour", "ZONE_HAUL"), ("zone colour", "ZONE_ROUTING"), ("red", 'var(--red)'), ("green", 'var(--green)'), ("ok-btn", 'var(--ok-btn)'),
          ("haul text", 'var(--haul-text)')]
_sites = {}
for _m in _TW.finditer(_fe_wo):
    _start = _fe_wo.rfind("<", 0, _m.start())
    _win = _fe_wo[_start:_start + 600]
    _found = sorted((_win.find(mark), kind) for kind, mark in _FILLS if mark in _win)
    _sites.setdefault(_found[0][1] if _found else "unknown", []).append(_win)
# NARROWED 22 Oct 2026 (UI fix 6): the Account's "spread on this week" is the standard btn-pri btn-sm now (card 2), so 13
# text-white sit on var(--navy), not 14; and the four haul-road buttons sit on var(--haul-text) (card 6, decision 13), which
# their own dark rule maps to --control-fg, so no text-white is left on a FIXED zone colour (finding 7 closed). The routing
# zone's "Stop placing" shares its button with the haul one and keeps ZONE_ROUTING #DC2626 (white on it 4.83:1, every look).
ok("UI fix 2 (#1): every text-white in the markup sits on a known fill — 13 on an inline var(--navy) and 1 on var(--blue) (the dark rule maps them to --control-fg), 2 on bg-slate-800 (remapped), the team pill, the 4 haul-road buttons on var(--haul-text) (their own dark rule, 22 Oct) and none on a fixed zone colour — none on var(--green) or the Confirm pair, none unknown",
   # NARROWED 27 Oct 2026 (stockpile forecast): 14 — the Dashboard stockpile chart's week chips are gone (−1); the
   # Stockpiles page's picked stockpile and picked year are white on var(--navy) (+2)
   # NARROWED 28 Oct 2026 (simulation v2): 15 and 2 — the site areas form's Save / Create button (navy) and its Place on map (blue)
   len(_sites.get("navy", [])) == 15 and len(_sites.get("blue", [])) == 2 and len(_sites.get("slate-800", [])) == 2
   and len(_sites.get("team palette", [])) == 1 and len(_sites.get("haul text", [])) == 4 and not _sites.get("zone colour")
   and not _sites.get("green") and not _sites.get("ok-btn") and not _sites.get("unknown"), str({k: len(v) for k, v in _sites.items()}))
ok("...the one text-white on var(--red) is the Locations form's Delete button (white on #F87171 is 2.77:1 in Dark — found 17 Oct, not in the audit's stops; its own fix)",
   len(_sites.get("red", [])) == 1 and ">Delete</button>" in _sites.get("red", [""])[0])
ok("...every inline navy / blue fill is written `background: \"var(--navy)\"` / `\"var(--blue)\"` (the form React writes as `background: var(--navy);`, which the rule's [style*=] matches), and the rule reads --control-fg",
   'html[data-theme="dark"] .text-white[style*="var(--navy)"],html[data-theme="dark"] .text-white[style*="var(--blue)"]{color:var(--control-fg)}' in _dark
   and ".bg-\\[color\\:var\\(--navy\\)\\]" not in fe
   and _fe_wo.count('background: "var(--navy)"') + _fe_wo.count('background:"var(--navy)"') >= 14 and _fe_wo.count('background: "var(--blue)"') >= 1
   and "backgroundColor: \"var(--navy)\"" not in _fe_wo and "backgroundColor: \"var(--blue)\"" not in _fe_wo)
_bad1 = []
for _a in _ACC:
    t = _eff(_a, "dark")
    for name, a, b in [("text on a --navy fill", t["control-fg"], t["navy"]), ("text on a --blue fill", t["control-fg"], t["blue"])]:
        r = _cr(a, b)
        if r < 4.5:
            _bad1.append(f"{_a}/dark: {name} {a} on {b} = {r:.2f}")
ok("...in the dark look --control-fg reads 4.5:1 on both fills in every accent (#1F2024 on #FF8C14 6.99:1, on #FFA10A 8.02:1; #141518 on #5B8FF0 5.77:1, on #8FB3F5 8.64:1) — the Ink/Light --blue fill stays white (3.68:1 on #3B82F6, the gate-place toggle; not this fix)",
   not _bad1 and round(_cr("#1F2024", "#FF8C14"), 2) == 6.99 and round(_cr("#FFFFFF", "#FF8C14"), 2) == 2.33, "; ".join(_bad1))
ok("...the Submit strip's labels sit at full opacity in the strip's own text colour (white/60 was 2.86:1 in Ink, 1.65:1 in Dark); the gold 'peak' values went with UI fix 4 (decision 3, 17 Oct)",
   # NARROWED 22 Oct 2026 (UI fix 7): the labels are 12 px now (text-xs)
   '<div className="text-xs uppercase tracking-wide">{label}</div>' in fe and "text-white/60" not in fe
   and '(tone === "peak" ? "text-[color:var(--gold)]" : "")' not in fe
   and '.unit-sw-seg button[aria-pressed="true"]{background:var(--navy);color:var(--control-fg);}' in fe)

# --- 17 Oct 2026: UI fix 4 (claude/ui-fix-captions) — the captions (finding 3, decision 1), the status WORDS (finding 6's words,
# finding 19, decision 2), the Submit strip's peak values (decision 3) and the small chips / captions (findings 19, 20). Ratios by the
# WCAG relative-luminance formula above; a token's effective value per look × accent from _eff; a tint laid over its surface by _over.
_TXT = {"ok-text": "#047857", "warn-text": "#B45309", "bad-text": "#B91C1C"}
_TXT_DARK = {"ok-text": "#34D399", "warn-text": "#FBBF24", "bad-text": "#F87171"}
ok("UI fix 4 (decision 2): three text-grade status colours, defined once in :root and once in the dark block and nowhere else — ok-text #047857, warn-text #B45309, bad-text #B91C1C; dark #34D399 / #FBBF24 / #F87171, which ARE the dark look's status colours, so Dark reads as before",
   all(_ROOT[k] == v for k, v in _TXT.items()) and all(_DARK[k] == v for k, v in _TXT_DARK.items())
   and all(_css.count(f"--{k}:") == 2 for k in _TXT)
   and _DARK["ok-text"] == _DARK["green"] and _DARK["warn-text"] == _DARK["gold"] and _DARK["bad-text"] == _DARK["red"])
_bad4 = []
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        _surfs = [("a card", t["surface"]), ("the page", t["bg"]), ("the rail", t["rail-bg"]), ("a second surface", t["surface-2"]),
                  ("a slate-50 table head", t["surface-2"] if _l == "dark" else "#F8FAFC"), ("a selected row", "#FFF4E6" if _a == "orange-shades" and _l != "dark" else "#EFF6FF" if _l != "dark" else _over(t["navy-soft"], t["surface"]))]
        for name in _TXT:
            for where, bgc in _surfs:
                r = _cr(t[name], bgc)
                if r < 4.5:
                    _bad4.append(f"{_a}/{_l}: {name} on {where} {t[name]} on {bgc} = {r:.2f}")
        for name, tint in [("ok-text", "rgba(3,158,134,.12)"), ("ok-text", "rgba(3,158,134,.10)"), ("ok-text", "rgba(3,158,134,.06)"),
                           ("bad-text", "rgba(197,48,48,.12)"), ("bad-text", "rgba(191,46,85,.12)"), ("warn-text", "rgba(217,119,6,.10)")]:
            r = _cr(t[name], _over(tint, t["surface"]))
            if r < 4.5:
                _bad4.append(f"{_a}/{_l}: {name} on its chip tint {tint} = {r:.2f}")
ok("UI fix 4 (decision 2): 🔴 in all 12 looks × accents the three read 4.5:1 or better on a card, the page, the rail, a second surface, a slate-50 head and a selected row, and on their chip tints (ok-text on the 12 %, 10 % and 6 % green tints, bad-text on the two 12 % red tints, warn-text on the 10 % amber tint)",
   not _bad4, "; ".join(_bad4[:6]))
ok("...the headline figures: ok-text 5.48:1 on white and 4.77:1 on the 12 % green tint; warn-text 5.02:1 on white and 4.50:1 on a 10 % amber tint (4.33:1 on the 14 % tint the stale chip had, which is why its tint came down); bad-text 6.47:1 on white and 5.38:1 on the red tint; dark 8.47 / 9.75 / 5.88 on the surface",
   round(_cr("#047857", "#FFFFFF"), 2) == 5.48 and round(_cr("#047857", _over("rgba(3,158,134,.12)", "#FFFFFF")), 2) == 4.77
   and round(_cr("#B45309", "#FFFFFF"), 2) == 5.02 and round(_cr("#B45309", _over("rgba(217,119,6,.10)", "#FFFFFF")), 2) == 4.50
   and round(_cr("#B45309", _over("rgba(217,119,6,.14)", "#FFFFFF")), 2) == 4.33
   and round(_cr("#B91C1C", "#FFFFFF"), 2) == 6.47 and round(_cr("#B91C1C", _over("rgba(197,48,48,.12)", "#FFFFFF")), 2) == 5.38
   and round(_cr("#34D399", "#1F2024"), 2) == 8.47 and round(_cr("#FBBF24", "#1F2024"), 2) == 9.75 and round(_cr("#F87171", "#1F2024"), 2) == 5.88)
ok("...and why the words moved: the green status colour reads 3.77:1 on white and the amber 3.19:1 — under 4.5:1 for text, fine for a fill or a dot (3:1)",
   round(_cr(_ROOT["green"], "#FFFFFF"), 2) == 3.77 and round(_cr(_ROOT["gold"], "#FFFFFF"), 2) == 3.19
   and _cr(_ROOT["green"], "#FFFFFF") >= 3 and _cr(_ROOT["gold"], "#FFFFFF") >= 3)
# at source level: the green and the amber are never a TEXT colour any more — every use left is a fill, a border or a dot
_FILLCTX = ("background", "borderColor", "fill:", "STATUS_DOT", "CARBON_TONE", "Approved:", "confirmed:", "held:", "Pending:", "edited:", "ASSUMPTION:")
def _text_uses(tok):
    out = []
    for m in _re.finditer(_re.escape(tok), _fe_wo):
        win = _fe_wo[max(0, m.start() - 70):m.start()]
        if not any(c in win for c in _FILLCTX):
            out.append(_fe_wo[max(0, m.start() - 60):m.end() + 20].replace("\n", " "))
    return out
ok("UI fix 4 (decision 2): 🔴 var(--green) is never a text colour in the markup — the 10 uses left are the progress bar's fill, a card's border (×4: the abnormal loads' note card since 22 Oct), the status dots (×3), the carbon-tone dot and the row-status icon",
   # NARROWED 27 Oct 2026: 11 — + the organisation file's message border (Config, F3 c), a border like the four above
   # NARROWED 27 Oct 2026 (stockpile forecast): 12 — + the Stockpiles page's saved-message border, a border like the others
   not _text_uses("var(--green)") and _fe_wo.count("var(--green)") == 12 and 'color: "var(--green)"' not in _fe_wo and "color:var(--green)" not in _fe_wo
   and "text-[color:var(--green)]" not in fe and "text-emerald-600" not in fe, str(_text_uses("var(--green)"))[:300])
# NARROWED 29 Oct 2026 (3b, the steel split): 8 — + the dot of Config's "Older: pick one of the three" chip (a status dot, not text)
ok("...nor var(--gold): the 8 uses left are the gate-arrivals key, the warning triangle, a note's border, the status dots (×2), the carbon-tone dot, the flag chip's triangle and the Older chip's dot; the Submit strip's text-[color:var(--gold)] is gone (decision 3)",
   not _text_uses("var(--gold)") and _fe_wo.count("var(--gold)") == 8 and "text-[color:var(--gold)]" not in fe and 'color: "var(--gold)"' not in _fe_wo and "color:var(--gold)" not in _fe_wo, str(_text_uses("var(--gold)"))[:300])
ok("UI fix 4 (decision 2): the status WORDS read the text-grade colours — In force on Zones, Delivered % on the Dashboard, the CatChips 'in' chip, the Routes vehicle chips, the set / held / routed tags, a variance, the simulation's checks and its no-wait line (ok-text); the stale chip (warn-text on a 10 % tint); the 'gate blocked' and vehicle-error chips and the Account's variance figures and the stockpile table's over-capacity figures on a rose-washed row (bad-text: --red is 4.83:1 on white but 4.4–4.5:1 on the wash); since 22 Oct the abnormal loads' .al-bad chip, route-error line and the limits a load is over (bad-text ×3), its .al-notes list, .al-warn chip, route notes and candidate notes (warn-text ×4)",
   '<span className="font-semibold" style={{ color: "var(--ok-text)" }}>In force</span>' in fe
   and '<span style={{ color: "var(--ok-text)" }}>{r.deliveredPct.toFixed(0)} %</span>' in fe
   and 'const fg = dir === "in" ? "var(--ok-text)" : "var(--navy)";' in fe
   and '["rgba(3,158,134,.12)", "var(--ok-text)"]' in fe and '["rgba(191,46,85,.12)", "var(--bad-text)"]' in fe
   and 'style={{ background: "rgba(3,158,134,.12)", color: "var(--ok-text)" }}>set</span>' in fe
   and 'style={{ color: "var(--ok-text)", background: "rgba(3,158,134,.12)" }}>held</span>' in fe and ': has ? ["routed", "var(--ok-text)"] : null;' in fe
   and '.sim-ok{color:var(--ok-text);font-weight:700;}' in fe and '.sim-tl-ok{font-size:14px;fill:var(--ok-text);}' in fe
   and '.sim-warn{color:var(--warn-text);}' in fe and ".sim-warn{color:var(--gold)" not in fe
   and 'style={{ color: "var(--warn-text)", background: "rgba(217,119,6,.10)" }} title="The last good published price is older than 8 days">stale</span>' in fe
   and 'style={{ background: "rgba(197,48,48,.12)", color: "var(--bad-text)" }}>' in fe
   # NARROWED 22 Oct 2026 (finding #40): bad-text 6 -> 8, the Horizon commit column's short and month-changed words;
   # NARROWED 27 Oct 2026 (UI fix 10): bad-text 11 -> 14, the two Look-ahead error boxes and the save message (--red was 4.39:1 on the rose)\n   # and (abnormal loads, the same day) bad-text 8 -> 11, warn-text 2 -> 6: the .al-bad / .al-warn chips, the route-error line, the limits over, .al-notes, the route and candidate notes
   # NARROWED 27 Oct 2026 (stockpile forecast): bad-text 14 -> 18, warn-text 6 -> 10 — the stockpile words: the Dashboard's message,
   # the Account's "Next 8 weeks", the Horizon strip's cells and the Stockpiles page's status, each red (over) or amber (runs out / near)
   # NARROWED 28 Oct 2026 (task 0c): bad-text 18 -> 23, warn-text 10 -> 12 — the diversions: the Routes chip (amber Diverted /
   # red Not diverted), the Zones Used by "no way round", the panel's no-road line and its no-way-round-yet box, the problem words (table and stacked rows)
   # NARROWED 29 Oct 2026 (task 3a): bad-text 23 -> 25, warn-text 12 -> 14 — the Pours page: its saved / not-saved line, each
   # flag's sentence (red COLD JOINT / TRANSIT, amber the rest) and a pour with no figures (amber)
   # NARROWED 29 Oct 2026 (task 3a PR C): bad-text 25 -> 26 — the Simulation's planned-pour flag line (.sim-pp-flag)
   # NARROWED 29 Oct 2026 (task 3c): warn-text 14 -> 15 — the Routes row's amber "Route again: does not pass the holding area" chip
   and _fe_wo.count("var(--ok-text)") >= 25 and _fe_wo.count("var(--bad-text)") == 26 and _fe_wo.count("var(--warn-text)") == 15
   and ".sim-pp-flag{color:var(--bad-text);" in fe
   and 'color: short ? (role === "commit" ? "var(--bad-text)" : "var(--red)")' in fe and 'color: role === "commit" ? "var(--bad-text)" : "var(--red)" }}> · month changed' in fe
   and "r.variance > 0 && !r.held ? \"var(--bad-text)\"" in fe and "r.eur_variance < 0 ? \"var(--bad-text)\"" in fe
   and "style={{ color: s.over ? \"var(--bad-text)\" : \"var(--ok-text)\" }}>" in fe and "style={{ color: s.over ? \"var(--bad-text)\" : \"var(--navy-deep)\" }}>" in fe)
ok("UI fix 4 (decision 1): 🔴 one rule maps text-slate-400 to --muted in the Ink and Light looks, written html:where(:not([data-theme=\"dark\"])) so it weighs as little as the utility and hover:text-slate-700 still wins; the dark look keeps its remap, whose value IS the dark --muted",
   'html:where(:not([data-theme="dark"])) .text-slate-400{color:var(--muted)}' in fe
   and 'html[data-theme="dark"] .text-slate-400{color:#9AA1AB}' in _dark and _DARK["muted"] == "#9AA1AB"
   and fe.count("/* CAPTIONS ") == 1 and "/* CAPTIONS-END */" in fe and fe.index("/* CAPTIONS ") > fe.index("/* ACCENTS-END */") and fe.index("/* CAPTIONS-END */") < fe.index("/* DARK-REMAP-START"))
_mb = []
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        for where, bgc in [("a card", t["surface"]), ("the page", t["bg"]), ("the rail", t["rail-bg"]), ("a second surface", t["surface-2"]), ("a slate-50 head", t["surface-2"] if _l == "dark" else "#F8FAFC")]:
            r = _cr(t["muted"], bgc)
            if r < 4.5:
                _mb.append(f"{_a}/{_l}: --muted on {where} {t['muted']} on {bgc} = {r:.2f}")
ok("...--muted reads 4.5:1 or better on a card, the page, the rail, a second surface and a slate-50 head in all 12 looks × accents: ink #64748B on white 4.76, on the rail #FAFAF9 4.56, on a slate-50 head 4.55; dark #9AA1AB on #1F2024 6.25 — where slate-400 (#94A3B8) read 2.56 on white and slate-300 (#CBD5E1) 1.48",
   not _mb and round(_cr("#64748B", "#FFFFFF"), 2) == 4.76 and round(_cr("#64748B", "#FAFAF9"), 2) == 4.56 and round(_cr("#64748B", "#F8FAFC"), 2) == 4.55
   and round(_cr("#9AA1AB", "#1F2024"), 2) == 6.25 and round(_cr("#94A3B8", "#FFFFFF"), 2) == 2.56 and round(_cr("#CBD5E1", "#FFFFFF"), 2) == 1.48, "; ".join(_mb[:4]))
ok("...on a washed surface --muted falls short — 4.37 on a selected row (blue-50 #EFF6FF; 4.38 on Orange shades' #FFF4E6), 4.28 on the Horizon's commit-week wash (navy-soft over white, #EEF3FD) and 4.43 on the Account's short-row wash (5 % rose, #FCF5F6) — so the second rule steps the greys there to slate-600 #475569 (6.96, 6.98, 6.81, 7.05), matching the inline washes by [style*=], again with :where() so a hover utility still wins",
   round(_cr("#64748B", "#EFF6FF"), 2) == 4.37 and round(_cr("#64748B", "#FFF4E6"), 2) == 4.38
   and round(_cr("#64748B", _over(_ROOT["navy-soft"], "#FFFFFF")), 2) == 4.28 and round(_cr("#64748B", _over("rgba(191,46,85,.05)", "#FFFFFF")), 2) == 4.43
   and round(_cr("#475569", "#EFF6FF"), 2) == 6.96 and round(_cr("#475569", "#FFF4E6"), 2) == 6.98
   and round(_cr("#475569", _over(_ROOT["navy-soft"], "#FFFFFF")), 2) == 6.81 and round(_cr("#475569", _over("rgba(191,46,85,.05)", "#FFFFFF")), 2) == 7.05
   and 'html:where(:not([data-theme="dark"])) :where(.bg-blue-50,[style*="--navy-soft"],[style*="rgba(191, 46, 85"],[style*="rgba(191,46,85"]) .text-slate-400,html:where(:not([data-theme="dark"])) :where(.bg-blue-50,[style*="--navy-soft"],[style*="rgba(191, 46, 85"],[style*="rgba(191,46,85"]) .text-slate-500{color:#475569}' in fe
   and _fe_wo.count('background: "var(--navy-soft)"') >= 7 and _fe_wo.count('background: "rgba(191,46,85,.05)"') == 2
   and ':root:not([data-theme="dark"])[data-accent="orange-shades"] .bg-blue-50{background-color:#FFF4E6}' in fe)
ok("...the rail's group headings lose their opacity:.85 (3.45 → 4.56), the big screen's two hard-coded greys (#9aa1ac, 2.60) and the Dashboard group title's default (#94a3b8) read --muted, and every slate-300 placeholder (rate not set ×3, not recorded, the dashes) reads slate-500 — the dark remaps for slate-300 and emerald-600 went with their last use",
   # NARROWED 22 Oct 2026 (UI fix 7, card 9, the user's choice): 12 px
   ".rail-group{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);}" in fe and "opacity:.85" not in fe
   and round(_cr(_over("rgba(100,116,139,.85)", "#FAFAF9"), "#FAFAF9"), 2) == 3.45
   and "9aa1ac" not in fe.lower() and round(_cr("#9AA1AC", "#FFFFFF"), 2) == 2.60
   and '"#94a3b8"' not in fe and 'style={{ color: tone || "var(--muted)" }}>{title}</div>' in fe
   and "text-slate-300" not in _fe_wo and ".text-slate-300{" not in _dark and ".text-emerald-600{" not in _dark
   and _fe_wo.count('<span className="text-slate-500">rate not set</span>') == 3 and 'className="text-slate-500">not recorded</span>' in fe)
ok("UI fix 4 (decision 3): the Submit strip's six values read in the strip's own text colour — the amber on the strip was 1.62:1 (1.4:1 in Dark) and the label already says Peak",
   '<div className="text-lg font-bold tabular-nums">{value}</div>' in fe and ".map(([label, value]) => (" in fe and '"peak"]' not in fe
   and '["Peak movements / day", fmt(perDay.peakTrips, "vehicles")],' in fe
   and round(_cr(_ROOT["gold"], _ROOT["navy"]), 2) == 1.62 and round(_cr(_DARK["gold"], _DARK["navy"]), 1) == 1.4)
# Every selector in the DARK-REMAP block must match something in the markup — the reverse of the coverage check above.
# (The selector this fix replaced, .bg-[color:var(--navy)].text-white, had matched nothing since 7 Oct and nobody noticed.)
_UTIL = set(_PAL.findall(_fe_wo))
_dead = []
for _line in _dark.splitlines():
    _line = _line.strip()
    if not _line.startswith('html[data-theme="dark"]'):
        continue
    for _sel in _re.split(r"(?<!\\),", _line[:_line.index("{")]):     # a comma between selectors, not an escaped one inside a class
        _rest = _sel.strip()[len('html[data-theme="dark"]'):].strip()
        if _rest.startswith(".mapboxgl-"):          # a class Mapbox GL adds at run time; never in the markup
            continue
        if not _rest.startswith("."):
            _tag = _re.match(r"[a-z]+", _rest).group(0)
            if f"<{_tag}" not in _fe_wo:
                _dead.append(_sel.strip())
            continue
        _i, _cls = 1, ""
        while _i < len(_rest):
            if _rest[_i] == "\\":
                _cls += _rest[_i + 1]; _i += 2; continue
            if _rest[_i] in ":[ ":
                break
            _cls += _rest[_i]; _i += 1
        _attr = _re.search(r'\[style\*="([^"]+)"\]', _rest[_i:])
        _used = (_cls in _UTIL) if _PAL.fullmatch(_cls) else (_cls in _fe_wo)
        if _attr and _attr.group(1) not in _fe_wo:
            _used = False
        if not _used:
            _dead.append(_sel.strip())
ok("UI fix 2: every selector in the DARK-REMAP block has a use in the markup — the four stale remaps found this way on 17 Oct (bg-[rgba(37,99,235,.06)], bg-slate-200, hover:text-slate-800 / -900: utilities no longer in the file) are gone",
   not _dead and _dark.count('html[data-theme="dark"]') >= 48 and "bg-slate-200{" not in _dark and "text-slate-900" not in _dark, str(_dead)[:300])

# --- 22 Oct 2026: UI fix 6 (claude/ui-fix-layout) — the approved mockup notes/ui-fix-layout-mockup-1022/ (the user: "i agree to
# all apart from 4"): the contrast of cards 2, 3, 5 and 6 and of the two extras the user said yes to (the Horizon's commit-week
# heading, finding #37; the Avoided chip). Every ratio by the WCAG 2.x relative-luminance formula above (_cr); a tint laid over
# its surface by _over; the tokens per look × accent from _eff. Tailwind's own values are v3's palette (the CDN build).
_TW_BLUE700, _TW_SLATE600 = "#1D4ED8", "#475569"
def _rule_colour(sel):
    m = _re.search(_re.escape(sel) + r"\{color:(#[0-9A-Fa-f]{6})\}", _css)
    return m.group(1) if m else None
# card 6 (decision 13): the haul-road colour as words and fills
_HT, _HT_DARK = {"haul-text": "#9A5F08", "haul-soft": "#FBF0DF"}, {"haul-text": "#F0A838", "haul-soft": "#3A2E1C"}
ok("UI fix 6 card 6 (decision 13): two haul-road tokens, once in :root and once in the dark block and nowhere else — haul-text #9A5F08 and haul-soft #FBF0DF, dark #F0A838 and #3A2E1C; no accent touches them",
   all(_ROOT.get(k) == v for k, v in _HT.items()) and all(_DARK.get(k) == v for k, v in _HT_DARK.items())
   and _css.count("--haul-text:") == 2 and _css.count("--haul-soft:") == 2
   and all(_eff(a, l)["haul-text"] == (_HT_DARK if l == "dark" else _HT)["haul-text"] for a in _ACC for l in ("ink", "light", "dark")))
_badH = []
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        _dk = _l == "dark"
        for name, a, b in [("a haul-road button's text on its fill (white; the control's text colour in Dark)", t["control-fg"] if _dk else "#FFFFFF", t["haul-text"]),
                           ("the words on a card", t["haul-text"], t["surface"]),
                           ("the words on the page", t["haul-text"], t["bg"]),
                           ("the dagger and its note on the expanded Routes row (slate-50/70)", t["haul-text"], _over("rgba(27,29,33,.7)", t["surface"]) if _dk else _over("rgba(248,250,252,.7)", "#FFFFFF")),
                           ("the 'Haul road' label on the amber wash (amber-50/60)", t["haul-text"], _over("rgba(251,191,36,.10)", t["surface"]) if _dk else _over("rgba(255,251,235,.6)", "#FFFFFF")),
                           ("the words on a slate-50 surface", t["haul-text"], t["surface-2"] if _dk else "#F8FAFC"),
                           ("a chip's words on its solid haul-soft", t["haul-text"], t["haul-soft"])]:
            r = _cr(a, b)
            if r < 4.5:
                _badH.append(f"{_a}/{_l}: {name} {a} on {b} = {r:.2f}")
ok("UI fix 6 card 6: 🔴 in all 12 looks × accents the haul-road colour reads 4.5:1 or better — a button's text on its fill, the words on a card, the page, the expanded Routes row, the amber wash, a slate-50 surface and a chip's solid haul-soft",
   not _badH, "; ".join(_badH[:6]))
ok("...the figures: white on #9A5F08 5.23:1 and #9A5F08 on white 5.23, on the expanded row 5.05, on the amber wash 5.13, on slate-50 5.00, on the chip's #FBF0DF 4.64; Dark: #1F2024 on #F0A838 8.03 (#141518 in the blue accents 9.01), #F0A838 on the surface 8.03, on the chip's #3A2E1C 6.53, on the amber wash 6.48",
   round(_cr("#FFFFFF", "#9A5F08"), 2) == 5.23 and round(_cr("#9A5F08", _over("rgba(248,250,252,.7)", "#FFFFFF")), 2) == 5.05
   and round(_cr("#9A5F08", _over("rgba(255,251,235,.6)", "#FFFFFF")), 2) == 5.13 and round(_cr("#9A5F08", "#F8FAFC"), 2) == 5.00
   and round(_cr("#9A5F08", "#FBF0DF"), 2) == 4.64 and round(_cr("#1F2024", "#F0A838"), 2) == 8.03 and round(_cr("#141518", "#F0A838"), 2) == 9.01
   and round(_cr("#F0A838", "#1F2024"), 2) == 8.03 and round(_cr("#F0A838", "#3A2E1C"), 2) == 6.53
   and round(_cr("#F0A838", _over("rgba(251,191,36,.10)", "#1F2024")), 2) == 6.48)
ok("...and why: the map line's #C2790B failed as text and fill (white on it 3.48:1; the chips 3.06 on white and 2.82 on a selected row under the see-through tint); the new brown under that tint falls to 4.24 on a selected row, so the chips are solid; white on the dark #F0A838 would be 2.03, so the dark fills take the control's text colour",
   round(_cr("#FFFFFF", "#C2790B"), 2) == 3.48 and round(_cr("#C2790B", _over("rgba(194,121,11,.12)", "#FFFFFF")), 2) == 3.06
   and round(_cr("#C2790B", _over("rgba(194,121,11,.12)", "#EFF6FF")), 2) == 2.82 and round(_cr("#9A5F08", _over("rgba(194,121,11,.12)", "#EFF6FF")), 2) == 4.24
   and round(_cr("#FFFFFF", "#F0A838"), 2) == 2.03 and 'const ZONE_HAUL = "#C2790B";' in fe)
ok("UI fix 6 card 6: the dark rule maps text-white on an inline var(--haul-text) to --control-fg (the navy / blue rule kept verbatim above it); the three fills are written background: \"var(--haul-text)\" and Stop placing takes it only for a haul road (a routing zone keeps ZONE_ROUTING #DC2626, white on it 4.83:1)",
   'html[data-theme="dark"] .text-white[style*="var(--haul-text)"]{color:var(--control-fg)}' in _dark
   and _dark.index('.text-white[style*="var(--blue)"]{color:var(--control-fg)}') < _dark.index('.text-white[style*="var(--haul-text)"]')
   and _fe_wo.count('background: "var(--haul-text)"') == 3 and 'style={zoneDraw ? { background: isHaul(zoneForm) ? "var(--haul-text)" : ZONE_ROUTING } : undefined}>' in fe
   and 'const ZONE_ROUTING = "#DC2626";' in fe and round(_cr("#FFFFFF", "#DC2626"), 2) == 4.83 and "(finding 7, open)" not in fe)
ok("UI fix 6 (the user's extra): the 'Avoided' chip is #B91C1C on its pink #FDE8EE, 5.53:1 (was #DC2626, 4.13:1), a fixed pair the same in every look — var(--bad-text) is #F87171 in the dark look and would read 2.36:1 on the pink",
   '<span className="text-xs font-semibold px-2 py-0.5 rounded" style={{ background: "#FDE8EE", color: "#B91C1C" }}>Avoided</span>' in fe
   and round(_cr("#B91C1C", "#FDE8EE"), 2) == 5.53 and round(_cr("#DC2626", "#FDE8EE"), 2) == 4.13
   and round(_cr(_DARK["bad-text"], "#FDE8EE"), 2) == 2.36 and "FDE8EE" not in _dark)
# card 3 (finding #11) + the user's yes to finding #37: the Horizon's commit week, heading and role word, on its shade
_b700 = {"os": _rule_colour(':root:not([data-theme="dark"])[data-accent="orange-shades"] .text-blue-700'),
         "dark": _rule_colour('html[data-theme="dark"] .text-blue-700'), "dark-blue": _rule_colour('html[data-theme="dark"][data-accent^="blue"] .text-blue-700')}
_s600_dark = _rule_colour('html[data-theme="dark"] .text-slate-600')
_badHz, _hzr = [], {}
for _a in _ACC:
    for _l in ["ink", "light", "dark"]:
        t = _eff(_a, _l)
        _dk = _l == "dark"
        shade = _over(t["navy-soft"], t["surface-2"] if _dk else "#F8FAFC")      # the thead is bg-slate-50 (dark: --surface-2)
        head = (_b700["dark-blue"] if _a.startswith("blue") else _b700["dark"]) if _dk else (_b700["os"] if _a == "orange-shades" else _TW_BLUE700)
        role = _s600_dark if _dk else _TW_SLATE600
        for name, a in [("the commit week's heading (text-blue-700)", head), ("its role word (text-slate-600)", role)]:
            if not a:
                _badHz.append(f"{_a}/{_l}: {name} has no colour")
                continue
            r = _cr(a, shade)
            _hzr[(_a, _l, name[:20])] = r
            if r < 4.5:
                _badHz.append(f"{_a}/{_l}: {name} {a} on {shade} = {r:.2f}")
ok("UI fix 6 card 3: 🔴 on the Horizon's commit-week shade the heading (text-blue-700, the accent's darker shade) and the role word (text-slate-600) read 4.5:1 or better in all 12 looks × accents",
   not _badHz and len(_hzr) == 24, "; ".join(_badHz[:6]))
ok("...the figures: the shade #E7EEFB (Ink and Light, Orange and Blue), heading #1D4ED8 5.75:1 (var(--navy) #2563EB was 4.44), Blue shades 5.66, Orange shades #9A3412 on #F4EBE9 6.23 (#C2410C was 4.42); Dark #FFB454 on #3B2D1F 7.53, Dark blue #8FB3F5 on #202632 7.17; the role word #475569 on #E7EEFB 6.50 (--muted would be 4.08), Dark #D5D8DE 9.30 / 10.62",
   _over(_ROOT["navy-soft"], "#F8FAFC") == "#E7EEFB" and round(_cr("#1D4ED8", "#E7EEFB"), 2) == 5.75 and round(_cr("#2563EB", "#E7EEFB"), 2) == 4.44
   and round(_cr("#1D4ED8", _over("rgba(29,78,216,.08)", "#F8FAFC")), 2) == 5.66
   and _over("rgba(194,65,12,.08)", "#F8FAFC") == "#F4EBE9" and round(_cr("#9A3412", "#F4EBE9"), 2) == 6.23 and round(_cr("#C2410C", "#F4EBE9"), 2) == 4.42
   and _over("rgba(255,140,20,.14)", "#1B1D21") == "#3B2D1F" and round(_cr("#FFB454", "#3B2D1F"), 2) == 7.53
   and _over("rgba(91,143,240,.08)", "#1B1D21") == "#202632" and round(_cr("#8FB3F5", "#202632"), 2) == 7.17
   and round(_cr("#475569", "#E7EEFB"), 2) == 6.50 and round(_cr("#64748B", "#E7EEFB"), 2) == 4.08
   and round(_cr("#D5D8DE", "#3B2D1F"), 2) == 9.30 and round(_cr("#D5D8DE", "#202632"), 2) == 10.62
   and _b700 == {"os": "#9A3412", "dark": "#FFB454", "dark-blue": "#8FB3F5"} and _s600_dark == "#D5D8DE")
ok("...var(--navy-deep) passes too (13.97:1 in Ink, 12.07 in Dark) but it is the ink colour, not the darker blue the mockup offered and the user said yes to, so the heading takes the remapped text-blue-700",
   round(_cr(_ROOT["navy-deep"], "#E7EEFB"), 2) == 13.97 and round(_cr(_DARK["navy-deep"], "#3B2D1F"), 2) == 12.07
   and '<div className={"font-semibold " + (role === "commit" ? "text-blue-700" : "text-slate-600")}>' in fe)
# card 2 (finding #11): the Account's headings and button; card 5: the count line; card 1: the pinned short-row cell
ok("UI fix 6 card 2: the Account headings are --muted on --surface-2 — 4.56:1 (Ink and Light), 6.48:1 (Dark), 4.5 or better in all 12 — and the button is the accent pair (white on #C2410C 5.18:1, on #2563EB 5.17; checked in all 12 by W16 above)",
   all(_cr(_eff(a, l)["muted"], _eff(a, l)["surface-2"]) >= 4.5 for a in _ACC for l in ("ink", "light", "dark"))
   and round(_cr("#64748B", "#FAFAF9"), 2) == 4.56 and round(_cr("#9AA1AB", "#1B1D21"), 2) == 6.48
   and round(_cr("#FFFFFF", "#C2410C"), 2) == 5.18 and round(_cr("#FFFFFF", "#2563EB"), 2) == 5.17
   and ".la-acct-head th{background:var(--surface-2);color:var(--muted);font-size:13px;" in fe and 'className="btn-pri btn-sm disabled:opacity-40"' in fe)
ok("UI fix 6 card 5: the big screen's '+ N more lines today' line is --muted on the card — 4.76:1 (Ink and Light), 6.25:1 (Dark), 4.5 or better in all 12",
   all(_cr(_eff(a, l)["muted"], _eff(a, l)["surface"]) >= 4.5 for a in _ACC for l in ("ink", "light", "dark"))
   and round(_cr("#64748B", "#FFFFFF"), 2) == 4.76 and round(_cr("#9AA1AB", "#1F2024"), 2) == 6.25
   and ".today-more{flex:none;margin-top:8px;padding-top:8px;border-top:1px solid var(--line);font-weight:600;color:var(--muted);}" in fe)
ok("UI fix 6 card 1: a short row's pinned Action cell paints the row's own colour — the 5 % rose over the surface, #FCF5F6 (Dark #272126) — so no stripe runs down the table",
   _over("rgba(191,46,85,.05)", _eff("orange", "ink")["surface"]) == "#FCF5F6" and _over("rgba(191,46,85,.05)", _eff("orange", "dark")["surface"]) == "#272126"
   and ".la-pin.la-pin-short{background:linear-gradient(rgba(191,46,85,.05),rgba(191,46,85,.05)),var(--surface);}" in fe
   and _fe_wo.count('background: "rgba(191,46,85,.05)"') == 2)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
