"""
CLP monitoring, 14 Oct 2026 (bundle G: W8 data fields, W7 charts) — backend/clp.py, GET /api/clp/monitoring,
and the W8 write paths (the site CLP cap, the peak bands and the Euro class on Config).

What is asserted: clp.py reads and never writes, names no team slot id, imports neither main nor network,
and every SQL literal carries the tenant predicate; each chart takes its figure from the module that owns
it (chart 1 = bulletin.route_cap_rows = the Conditions panel's exceeded list; chart 1b =
gate_arrivals.location_visits; chart 4 = costlines' trips per month and vehicle; chart 6 = areas.area_load;
chart 10's target = carbon_target.status's target_t; chart 16 = the scenario's delta_trips); an empty chart
names the missing field and carries no zero; team NAMES only; a team code's scope; the endpoint's edges;
the word rule over every string in the reply.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed (http_smoke.py drives the real one).
  * Nothing in a browser (parse_frontend / render_frontend / dom_frontend read the fixture written last).
  * SQLite only; hand-made polylines, not HERE geometry.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_clp.py
"""
import copy
import json
import math
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, as test_gate_arrivals.py ----------------------------------------------
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


def _Query(default=None, **k):
    return default


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query


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


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


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

TMP = tempfile.mkdtemp(prefix="rbe_clp_")
from portable import remove_scratch_db, offline   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import weeks  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import costing  # noqa: E402
import config  # noqa: E402
import costlines  # noqa: E402
import gates  # noqa: E402
import gate_arrivals  # noqa: E402
import gate_hours  # noqa: E402
import network  # noqa: E402
import taxonomy  # noqa: E402
import areas  # noqa: E402
import bulletin  # noqa: E402
import carbon_target  # noqa: E402
import clp  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
access.set_current("planner123")
days.START_YEAR = main.START_YEAR

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def _raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def plen(pts):
    return sum(hav(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]


def poly(*rings):
    return {"type": "Polygon", "coordinates": [list(r) for r in rings]}


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


ART = network.DEFAULT_PROFILE          # "Artic Tipper (44t)", 29 t a load
RIGID = "Rigid 8-wheeler (32t)"        # 20 t a load
BAL = "Large aggregate / ballast"
ATTR = ["Source: Office for National Statistics licensed under the Open Government Licence v.3.0",
        "Contains OS data © Crown copyright and database right 2026"]

# =========================================================================== #
#  0. A small scheme by hand: two pits, two yards, three routes, two vehicles    #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
taxonomy.seed_taxonomy()
config.invalidate()
config.seed_from_file(conversions)
config.invalidate()
costing.invalidate()
carbon_target.invalidate()
access.set_current("planner123")
q1 = network.create_location("Pit West", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=[BAL])["id"]
d1 = network.create_location("Yard East", "destination", lat=52.55, lon=-0.85, loc_type="Compound", receives=[BAL])["id"]
q2 = network.create_location("Pit North", "origin", lat=52.58, lon=-0.98, loc_type="Quarry", supplies=[BAL])["id"]
d2 = network.create_location("Yard North", "destination", lat=52.58, lon=-0.92, loc_type="Compound", receives=[BAL])["id"]
R1 = network.create_route(q1, d1, material_category=BAL, route_id="R001", ipt="IPT1")["id"]
R2 = network.create_route(q2, d2, material_category=BAL, route_id="R002", ipt="IPT2")["id"]
R3 = network.create_route(q1, d2, material_category=BAL, route_id="R003", ipt="IPT1")["id"]   # never routed
L1 = [[round(-0.95 + 0.01 * i, 6), 52.55] for i in range(11)]          # W -> E across -0.90
L2 = [[round(-0.98 + 0.01 * i, 6), 52.58] for i in range(7)]           # wholly in W
L2_RET = [[-0.92, 52.58], [-0.92, 52.45], [-0.98, 52.45], [-0.98, 52.58]]   # back via S


def add_geom(rid, pts, leg="loaded", profile=ART, hr=0.5):
    db.execute(
        "INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
        "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), rid, profile, leg, 0, json.dumps(pts), round(plen(pts), 3), hr, "2026-10-14T00:00:00Z"))


for _p in (ART, RIGID):
    add_geom(R1, L1, profile=_p); add_geom(R1, list(reversed(L1)), leg="return", profile=_p)
    add_geom(R2, L2, profile=_p); add_geom(R2, L2_RET, leg="return", profile=_p)


def _line(rid, sect, month, veh, ipt):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type=BAL, material_description=None,
        vehicle_type=veh, submitted_by="tester", unit="t", status="Pending",
        cells=[main.Cell(month_index=m, quantity=q) for m, q in month], ipt=ipt))
    main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id=sect)


_line(R1, "WS1", [(10, 2900.0), (11, 1450.0)], ART, "IPT1")     # 100 loads in Oct, 50 in Nov
_line(R2, "WS2", [(10, 2000.0)], RIGID, "IPT2")                 # 100 loads at 20 t
_line(R3, "WS3", [(10, 580.0)], ART, "IPT1")                    # 20 loads, not routed
config.invalidate()
factors = conversions.load_factors()
WD = 22.0
acc_planner = access.current()
M = clp.monitoring(10, acc_planner, factors=factors, working_days=WD)
C = M["charts"]

# =========================================================================== #
#  1. Source level                                                              #
# =========================================================================== #
src = open(os.path.join(BACKEND, "clp.py"), encoding="utf-8").read()
code_only = re.sub(r'"""[\s\S]*?"""', "", src)
ok("⭐ clp.py is read-only: no db.execute, no INSERT / UPDATE / DELETE",
   "db.execute" not in code_only and not re.search(r"\b(INSERT|UPDATE|DELETE)\b", code_only))
ok("⭐ clp.py imports neither main nor network and names no team slot id",
   not re.search(r"^\s*(import|from)\s+(network|main)\b", src, re.M) and re.search(r"\bIPT ?[1-6]\b", src) is None)
_stmts = re.findall(r'db\.query\(\s*((?:"[^"]*"\s*)+)', code_only)
# NARROWED 11 Nov 2026 (card 4, John's yes): a fourth literal, the weeks with a tonnage typed (the "recorded to" date)
# NARROWED 11 Nov 2026 (D-I4, John's yes): a fifth, each week's planned quantity (the plan to the same week)
ok("🔴 tenant isolation: all five SQL literals in clp.py constrain tenant_id (29 Oct 2026: the holding areas' lines; "
   "11 Nov 2026: the recorded weeks; D-I4: the weeks' planned quantity)",
   len(_stmts) == 5 and all("tenant_id = ?" in s for s in _stmts), str(_stmts))
# NARROWED 11 Nov 2026 (card 4, John's yes "First"): the planned and recorded tonnes lead the order; the reply gains recorded_line
ok("the reply's keys and the chart order are the contract's",
   set(M) == {"month", "label", "working_days", "distance_unit", "months", "order", "charts", "with_data", "peak_bands",
              "peak_words", "scope", "scope_line", "limit", "recorded_line", "demo_notice"}
   and M["order"] == ["recorded_tonnes", "route_caps", "site_caps", "holding_areas", "vehicle_types", "euro_class", "councils",
                      "carbon_rate", "trips_avoided"]
   and list(C) == M["order"] and M["label"] == "Oct 2026" and M["working_days"] == 22.0)
ok("every chart carries key, number, title, the CLP item it serves, state and missing",
   all({"key", "number", "title", "serves", "state", "missing"} <= set(c) and c["key"] == k for k, c in C.items())
   # NARROWED 11 Nov 2026 (card 4): the tonnes chart is not in the outside brief's table: "R" (recorded)
   and [C[k]["number"] for k in M["order"]] == ["R", "1", "1", "1", "4", "5", "6", "10", "16"])
ok("⭐ 11 Nov 2026 (card 4): the planned and recorded tonnes chart is FIRST in clp.ORDER, in CHARTS and in the reply",
   clp.ORDER[0] == "recorded_tonnes" and list(clp.CHARTS)[0] == "recorded_tonnes" and M["order"][0] == "recorded_tonnes"
   and list(C)[0] == "recorded_tonnes" and C["recorded_tonnes"]["title"] == "Planned and recorded tonnes"
   and "compl" not in C["recorded_tonnes"]["serves"].lower())
ok("🔴 card 4: the limit stays word for word (John says it on Friday)",
   M["limit"] == clp.SPREAD == "Planned figures, not observed: Wayscope holds no gate log or arrival times.")
ok("⭐ card 4, nothing typed on Account yet: the tonnes chart is empty with a plain sentence, no recorded line, no figure 0",
   C["recorded_tonnes"]["state"] == "empty" and C["recorded_tonnes"]["missing"] == "No tonnes typed on Account up to Oct 2026."
   and "months" not in C["recorded_tonnes"] and M["recorded_line"] is None, str(C["recorded_tonnes"]))
ok("29 Oct 2026 (task 3c): with no holding area the Holding areas table is empty and says what to type",
   C["holding_areas"]["state"] == "empty" and "Holding area" in (C["holding_areas"]["missing"] or ""), str(C["holding_areas"]))

# =========================================================================== #
#  2. Empty states before anything is typed: each names its field, never a 0     #
# =========================================================================== #
ok("⭐ chart 1 with no cap typed: empty, names the planning block's field, still lists the routes (no cap, no figure 0)",
   C["route_caps"]["state"] == "empty"
   and C["route_caps"]["missing"] == ("No planning cap typed on any route with volume this month (Data → Routes → a route's "
                                      "planning block: Max vehicles / day).")
   and all(r["cap"] is None and r["pct"] is None for r in C["route_caps"]["rows"]), str(C["route_caps"])[:300])
ok("⭐ chart 1b with no site cap: empty, names Data → Locations → CLP cap",
   C["site_caps"]["state"] == "empty" and "Data → Locations → a location: CLP cap, lorry visits a day" in C["site_caps"]["missing"])
ok("⭐ chart 5 with no Euro class typed: empty, names Config → Vehicles → Euro class, and the vehicles in use",
   C["euro_class"]["state"] == "empty"
   and C["euro_class"]["missing"] == "No Euro class typed for the vehicles the plan uses (Config → Vehicles → Euro class)."
   and sorted(C["euro_class"]["vehicles_untyped"]) == sorted([clp._veh_label(ART, factors), clp._veh_label(RIGID, factors)]))
ok("⭐ chart 6 with no council boundaries: empty, says an admin imports them",
   C["councils"]["state"] == "empty" and C["councils"]["missing"] == "No council boundaries are loaded for this scheme (an admin imports them).")
ok("⭐ chart 16 with no target: empty, 'No decisions agreed yet' and where they are set",
   C["trips_avoided"]["state"] == "empty"
   and C["trips_avoided"]["missing"] == "No decisions agreed yet: a planner sets them with the carbon target in the Carbon planner.")
ok("⭐ chart 10 with no target: still drawn (the plan's own figures), the target line None and the 'no target' sentence, never 0",
   C["carbon_rate"]["state"] == "set" and C["carbon_rate"]["target_kg_per_tonne"] is None and "target_kg_per_load" not in C["carbon_rate"]
   and C["carbon_rate"]["target_note"] == "No carbon target set yet. A planner sets it in the Carbon planner.")
ok("with_data lists exactly the charts in state 'set'", M["with_data"] == ["vehicle_types", "carbon_rate"], str(M["with_data"]))

# =========================================================================== #
#  3. Chart 4: loads by vehicle, the costlines trips rule                          #
# =========================================================================== #
VT = C["vehicle_types"]
_cl = costlines.lines(acc_planner, status="Approved", factors=factors)["lines"]
_by = {}
for _l in _cl:
    _by.setdefault((_l["vehicle_type"], _l["month_index"]), 0)
    _by[(_l["vehicle_type"], _l["month_index"])] += _l["trips"]
ok("the over-time window is every month with approved lines: Oct and Nov 2026",
   [m["label"] for m in M["months"]] == ["Oct 2026", "Nov 2026"] and [m["month_index"] for m in VT["months"]] == [10, 11])
ok("⭐ chart 4 equals costlines' trips per vehicle and month (the one trips rule): artic 120 + 50, rigid 100 + 0",
   {(s["group"], m): s["loads"][i] for s in VT["series"] for i, m in enumerate((10, 11))}
   == {(ART, 10): _by.get((ART, 10), 0), (ART, 11): _by.get((ART, 11), 0), (RIGID, 10): _by.get((RIGID, 10), 0), (RIGID, 11): 0}
   and _by[(ART, 10)] == 120 and _by[(RIGID, 10)] == 100 and VT["totals"] == [220, 50], str(VT["series"])[:300])
ok("⭐ shares are the server's: Oct artic round(120 × 100 ÷ 220, 1) = 54.5 %, rigid 45.5 %; Nov artic 100 %",
   VT["series"][0]["group"] == ART and VT["series"][0]["pct"] == [54.5, 100.0] and VT["series"][1]["pct"] == [45.5, 0.0])
ok("chart 4 headline names the biggest vehicle and its share of every load in the window (170 of 270 = 63 %)",
   VT["headline"] == f"{clp._veh_label(ART, factors)} carries 63 % of the loads", VT["headline"])

# =========================================================================== #
#  4. Chart 10: all-in carbon per load and per tonne                               #
# =========================================================================== #
CR = C["carbon_rate"]
import carbon  # noqa: E402
_sc = carbon.scenario(acc_planner, status="Approved", factors=factors)
_m10 = [l for l in _sc["lines"] if l["month_index"] == 10]
_t10 = sum(l["total_t"] for l in _m10)
ok("⭐ chart 10 per month = the scenario's all-in total ÷ its loads and ÷ its tonnes (Oct: 220 loads, 5 480 t)",
   CR["months"][0]["loads"] == 220 and CR["months"][0]["tonnes"] == 5480.0
   and CR["months"][0]["kg_per_load"] == round(_t10 * 1000 / 220, 1)
   and CR["months"][0]["kg_per_tonne"] == round(_t10 * 1000 / 5480, 2), str(CR["months"][0]))
ok("chart 10 says All-in and names the one forecast month with no road route (R003)",
   CR["unit_note"] == "All-in" and CR["lines_unrouted"] == 1 and "1 forecast month with no road route yet carries no transport carbon here." in CR["basis"])
ok("...no decisions line without a target", all(r["kg_per_load_decisions"] is None for r in CR["months"]))

# =========================================================================== #
#  5. Typing the fields (W8): caps, Euro class, areas, a target                    #
# =========================================================================== #
# the route cap through its real write path; the site cap through the location PUT
_rp = network.set_route_planning(R1, {"max_vehicles_per_day"}, max_vehicles_per_day=4)
ok("the route cap is written through network.set_route_planning", not (_rp or {}).get("error"), str(_rp))
ok("🔴 the site cap refuses 0, a negative and a word, each in words; blank is no cap",
   network.clp_cap_problem(0) == "the CLP cap must be above 0 (clear it to mean no cap)"
   and network.clp_cap_problem(-3) == "the CLP cap must be above 0 (clear it to mean no cap)"
   and network.clp_cap_problem("lots") == "the CLP cap must be a number of lorry visits a day"
   and network.clp_cap_problem("") is None and network.clp_cap_problem(None) is None
   and network.set_clp_cap("L999", 4).get("error") == "not found")
os.environ["ADMIN_TOKEN"] = "adm"
_loc = main.update_location(d1, main.LocationIn(name="Yard East", role="destination", receives=[BAL], lat=52.55, lon=-0.85,
                                                loc_type="Compound", clp_cap_per_day=4), token="adm")
ok("⭐ the location PUT with clp_cap_per_day stores it; GeoJSON properties carry it",
   not (_loc or {}).get("error") and db.query("SELECT clp_cap_per_day FROM locations WHERE tenant_id = ? AND id = ?",
                                               (db.current_tenant(), d1))[0]["clp_cap_per_day"] == 4.0
   and {f["properties"]["id"]: f["properties"].get("clp_cap_per_day") for f in network.locations_geojson()["features"]}.get(d1) == 4.0,
   str(_loc))
main.update_location(d1, main.LocationIn(name="Yard East", role="destination", receives=[BAL], lat=52.55, lon=-0.85,
                                         loc_type="Compound"), token="adm")
ok("🔴 a PUT that does not send clp_cap_per_day leaves it alone (an older client cannot blank it)",
   db.query("SELECT clp_cap_per_day FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), d1))[0]["clp_cap_per_day"] == 4.0)
_e400 = _raises(lambda: main.update_location(d1, main.LocationIn(name="Yard East", role="destination", receives=[BAL], lat=52.55,
                                                                 lon=-0.85, clp_cap_per_day=0), token="adm"))
ok("🔴 a PUT with clp_cap_per_day 0 is a 400 with the sentence, and nothing changes",
   getattr(_e400, "status_code", None) == 400 and "above 0" in getattr(_e400, "detail", "")
   and db.query("SELECT clp_cap_per_day FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), d1))[0]["clp_cap_per_day"] == 4.0)
os.environ.pop("ADMIN_TOKEN", None)
# Config: the Euro class and the peak bands go through config.validate
_doc = copy.deepcopy(config.load(conversions, use_cache=False))
_bad = copy.deepcopy(_doc)
_bad["vehicles"][ART]["euro_class"] = "Euro 6"
_bad["planning"]["peak_bands"] = [{"from": "07:00", "to": "10:00"}, {"from": "09:30", "to": "11:00"}]
_pr = config.validate(_bad)
ok("🔴 Config refuses an unknown Euro class and overlapping peak bands, each in words",
   f"vehicle '{ART}': euro_class must be one of Euro IV, Euro V, Euro VI, Zero emission" in _pr
   and "planning.peak_bands: peak band 2 overlaps another band" in _pr, str(_pr))
_bad2 = copy.deepcopy(_doc)
_bad2["planning"]["peak_bands"] = "07:00-10:00"
ok("...and peak bands that are not a list", "planning.peak_bands must be a list of {from, to} windows" in config.validate(_bad2),
   str(config.validate(_bad2)))
_doc["vehicles"][ART]["euro_class"] = "Euro VI"
_doc["planning"]["peak_bands"] = [{"from": "07:00", "to": "10:00"}, {"from": "16:00", "to": "19:00"}]
ok("a valid Euro class and two peak bands pass", config.validate(_doc) == [], str(config.validate(_doc)))
# 17 Oct 2026 (the user): the scheme's default gate hours on Config → Planning, checked by config.validate
_dg = lambda v: config.validate({**_doc, "planning": {**_doc["planning"], "default_gate_hours": v}})
# NARROWED 17 Oct 2026 (the review): the refusals are worded for the field a person sees, not the setting's path
ok("🔴 Config refuses default gate hours that close before they open (or past midnight), that are not times, half-typed, or "
   "not two times — in the field's own words",
   "Default gate hours: the closing time must be after the opening time (they stay within one day)" in _dg({"from": "17:00", "to": "08:00"})
   and "Default gate hours: the closing time must be after the opening time (they stay within one day)" in _dg({"from": "08:00", "to": "08:00"})
   and "Default gate hours: type both times, as 24-hour times such as 08:00" in _dg({"from": "8am", "to": "17:00"})
   and "Default gate hours: type both times, as 24-hour times such as 08:00" in _dg({"from": "", "to": "18:00"})
   and "Default gate hours must be two times, from and to" in _dg("08:00-17:00")
   and not any("planning.default_gate_hours" in p for p in _dg({"from": "17:00", "to": "08:00"})), str(_dg({"from": "17:00", "to": "08:00"})))
ok("default gate hours of the scheme's own pass (08:00–18:00), and leaving them out means 08:00–17:00",
   _dg({"from": "08:00", "to": "18:00"}) == [] and "default_gate_hours" not in _doc["planning"]
   and gate_hours.default_hours(_doc) == {"from": "08:00", "to": "17:00"}
   and gate_hours.default_hours({"planning": {"default_gate_hours": {"from": "08:00", "to": "18:00"}}}) == {"from": "08:00", "to": "18:00"}
   and gate_hours.default_hours({"planning": {"default_gate_hours": {"from": "18:00", "to": "08:00"}}}) == {"from": "08:00", "to": "17:00"})
config.save(_doc, by="tester")
config.invalidate()
factors = conversions.load_factors()
# the council boundaries (the test_areas boxes)
FC = {"type": "FeatureCollection", "attribution": ATTR, "features": [
    {"type": "Feature", "properties": {"area_id": "W", "name": "Westshire", "tier": "district"}, "geometry": poly(box(-1.0, 52.5, -0.9, 52.6))},
    {"type": "Feature", "properties": {"area_id": "E", "name": "Eastshire", "tier": "district"}, "geometry": poly(box(-0.9, 52.5, -0.8, 52.6))},
    {"type": "Feature", "properties": {"area_id": "S", "name": "Southshire", "tier": "district"}, "geometry": poly(box(-1.0, 52.4, -0.8, 52.5))},
    {"type": "Feature", "properties": {"area_id": "C", "name": "Testshire", "tier": "county"}, "geometry": poly(box(-1.0, 52.4, -0.8, 52.6))},
]}
_imp = areas.import_collection(FC)
ok("the four council areas import and the routed legs are clipped", _imp.get("imported") == 4, str(_imp)[:200])
# the target: the rigid on R002 swapped for the artic (2 000 t at 29 t = 69 loads, not 100)
DECISIONS = [{"driver": "vehicle", "scope": {"route_id": R2}, "vehicle": ART}]
_t = main.put_carbon_target(main.CarbonTargetIn(mode="pct", levers=DECISIONS, ui_state={}, updated_by="Sam (planner)"))
ok("the carbon target is set from one decision (a lorry swap on R002)", (_t.get("target") or {}).get("levers") == DECISIONS, str(_t)[:300])
# 29 Oct 2026 (task 3c): a holding area on R001's line, serving Yard East (Data -> Locations), its entrance gate typed
import holding  # noqa: E402
import gates as _gates  # noqa: E402
_had_tok = os.environ.get("ADMIN_TOKEN")
os.environ["ADMIN_TOKEN"] = "adm"
_h = main.create_location(main.LocationIn(name="Lane holding area", role="both", lat=52.55, lon=-0.88, loc_type="Holding area",
                                          holding_spaces=10, holding_call=2), token="adm")
H1 = _h["id"]
_gates.create_gate(H1, "Lane entrance", 52.55, -0.88, direction="both", open_from="07:00", open_to="20:30", open_days="1111100")
_hl = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}[d1]
main.update_location(d1, main.LocationIn(name=_hl["name"], role="destination", receives=[BAL], lat=_hl["lat"], lon=_hl["lon"],
                                         loc_type=_hl.get("loc_type") or "Compound", holding_id=H1), token="adm")
if _had_tok is None:
    os.environ.pop("ADMIN_TOKEN", None)
else:
    os.environ["ADMIN_TOKEN"] = _had_tok
# 11 Nov 2026 (card 4): tonnes typed on Account (a week's actual) — R001 Oct weeks 1 and 2, R002 Oct week 1; nothing in Nov
weeks.materialise_window(10, 11)
_ra = [weeks.set_actual(R1, 10, "earthworks", "WS1", 1, actual_qty=700.0, by="clerk"),
       weeks.set_actual(R1, 10, "earthworks", "WS1", 2, actual_qty=800.0, by="clerk"),
       weeks.set_actual(R2, 10, "earthworks", "WS2", 1, actual_qty=500.0, by="clerk")]
ok("card 4 set-up: three week actuals typed (Oct 2026)", all("error" not in (x or {}) for x in _ra), str(_ra)[:300])
M2 = clp.monitoring(10, acc_planner, factors=factors, working_days=WD)
C2 = M2["charts"]
RT = C2["recorded_tonnes"]
_dl = costlines.lines(acc_planner, status="Approved", factors=factors)["lines"]
_pl, _rd, _nl = {}, {}, {}
for _l in _dl:
    _pl[_l["month_index"]] = _pl.get(_l["month_index"], 0.0) + _l["tonnes"]
    if _l["actual_tonnes"] is not None:
        _rd[_l["month_index"]] = _rd.get(_l["month_index"], 0.0) + _l["actual_tonnes"]
        _nl[_l["month_index"]] = _nl.get(_l["month_index"], 0) + 1
_sun = weeks.week_span(10, 2)[1]
# D-I4: the plan of Oct's weeks 1-2 (the latest typed), restated here from the weeks' own planned quantities
_wq = {}
for _w in db.query("SELECT route_id, discipline, section_id, week_index, planned_qty FROM forecast_weeks WHERE tenant_id = ? AND month_index = 10",
                   (db.current_tenant(),)):
    _k = (_w["route_id"], _w["discipline"] or "", _w["section_id"] or "")
    _a, _b = _wq.get(_k, (0.0, 0.0))
    _wq[_k] = (_a + float(_w["planned_qty"] or 0), _b + (float(_w["planned_qty"] or 0) if int(_w["week_index"]) <= 2 else 0.0))
_pw10 = sum(_l["tonnes"] * (_wq[(_l["route_id"], _l["discipline"] or "", _l["section_id"] or "")][1]
                            / _wq[(_l["route_id"], _l["discipline"] or "", _l["section_id"] or "")][0])
            for _l in _dl if _l["month_index"] == 10)
ok("⭐ card 4: planned_month_t is the Dashboard's source exactly (the sum of costlines tonnes of the Approved lines that month: 5 480)",
   RT["state"] == "set" and [m.get("planned_month_t") for m in RT["months"]] == [round(_pl[10], 3)] and RT["months"][0].get("planned_month_t") == 5480.0,
   str(RT)[:400])   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks
ok("🔴 D-I4: Oct is typed to week 2 only (a part month), so its planned_t is the plan of weeks 1-2: 2 192 of 5 480 (2 of 5 weeks)",
   RT["months"][0]["planned_t"] == round(_pw10, 3) == 2192.0 and RT["months"][0].get("planned_to_week") == "2026-10-05", str(RT["months"]))
ok("⭐ card 4: recorded_t is the sum of costlines actual_tonnes (700 + 800 + 500 = 2 000), lines_reported 2, 91 % of the plan to that week",
   RT["months"][0]["recorded_t"] == round(_rd[10], 3) == 2000.0 and RT["months"][0]["lines_reported"] == _nl[10] == 2
   and RT["months"][0]["recorded_pct"] == round(2000 * 100 / _pw10) == 91, str(RT["months"]))   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks
ok("⭐ card 4: no month after the chosen one (the window runs Oct–Nov; Oct is picked, so Oct only)",
   [m["month_index"] for m in M2["months"]] == [10, 11] and [m["month_index"] for m in RT["months"]] == [10])
ok("⭐ card 4: recorded to the latest week typed (Oct week 2, Mon 5 to Sun 11 Oct 2026), the WEEK named in the headline and the line",
   RT["recorded_to"] == _sun.isoformat() == "2026-10-11" and RT.get("recorded_week") == "2026-10-05"
   and RT["headline"] == "Oct 2026: 2,000 t recorded, 91 % of the 2,192 t planned · recorded to the week of 5 Oct"   # D-I4: the plan to that week   # REVERSED 11 Nov 2026 (D-F1/D-F3, John's yes): commas for thousands; the week, not a day
   and M2["recorded_line"] == "Recorded tonnes as typed on Account, weeks to 5 Oct 2026."
   and M2["limit"] == clp.SPREAD, RT["headline"] + " | " + str(M2["recorded_line"]))
ok("card 4: the basis says what planned and recorded mean, and that a month with nothing typed is not recorded, not zero",
   "Recorded: tonnes typed on Account (a week's actual)" in RT["basis"] and "Delivered against plan" in RT["basis"]
   and "not recorded, not zero" in RT["basis"] and RT["source"].startswith("Wayscope"))
M11 = clp.monitoring(11, acc_planner, factors=factors, working_days=WD)
RT11 = M11["charts"]["recorded_tonnes"]
ok("⭐ card 4: a month nobody typed is None ('not recorded'), never 0; the headline names the latest month with a record",
   [m["month_index"] for m in RT11["months"]] == [10, 11] and RT11["months"][1]["recorded_t"] is None
   and RT11["months"][1]["recorded_pct"] is None and RT11["months"][1]["lines_reported"] == 0
   and RT11["months"][1]["planned_t"] == round(_pl[11], 3) == 1450.0
   and RT11["headline"].startswith("Oct 2026: 2,000 t recorded") and RT11["recorded_to"] == "2026-10-11", str(RT11["months"]))   # REVERSED 11 Nov 2026 (D-F1)
import datetime as _dt  # noqa: E402
_keep_today = clp._today_date
clp._today_date = lambda: _dt.date(2026, 10, 8)        # Thu of Oct week 2: that week is typed but ends on Sun 11 Oct
_RT8 = clp.monitoring(10, acc_planner, factors=factors, working_days=WD)
clp._today_date = _keep_today
ok("🔴 11 Nov 2026: a week typed part-way through never says a date after today (Thu 8 Oct: the week of 5 Oct, never Sun 11 Oct)",
   _RT8["charts"]["recorded_tonnes"]["recorded_to"] == "2026-10-08"
   and _RT8["charts"]["recorded_tonnes"]["headline"].endswith("· recorded to the week of 5 Oct")   # NARROWED 11 Nov 2026 (D-F3): the week
   and "11 Oct" not in _RT8["charts"]["recorded_tonnes"]["headline"] and "8 Oct" not in _RT8["charts"]["recorded_tonnes"]["headline"]
   and _RT8["recorded_line"] == "Recorded tonnes as typed on Account, weeks to 5 Oct 2026.", str(_RT8.get("recorded_line")))
_HA = C2["holding_areas"]
ok("⭐ 29 Oct 2026 (task 3c): the Holding areas table is set: one row, 10 spaces, its hours, the site it serves, the mixers straight to the gate",
   _HA["state"] == "set" and len(_HA["rows"]) == 1 and _HA["rows"][0]["holding_area"] == "Lane holding area" and _HA["rows"][0]["spaces"] == 10
   and _HA["rows"][0]["open"].startswith("07:00–20:30") and _HA["rows"][0]["serves"] == "Yard East"
   and "mixer" in _HA["rows"][0]["straight"].lower() and _HA["rows"][0]["straight"].endswith("abnormal loads"), str(_HA)[:400])
ok("⭐ ...and the lorries a day: R001's 100 loads into Yard East ÷ 22 (R002 and R003 serve no holding area; no return calls off)",
   _HA["rows"][0]["per_day"] == round(100 / 22.0, 1) and _HA["headline"].startswith("1 holding area, 4.5 lorries a day"), str(_HA["rows"][0]["per_day"]) + " " + _HA["headline"])
ok("...the most held at once comes from the Simulation's day (a figure, with its time, or a dash), never a crash",
   ("most" in _HA["rows"][0]) and (_HA["rows"][0]["most"] is None or isinstance(_HA["rows"][0]["most"], int)), str(_HA["rows"][0]))
ok("...basis and source are in words a reader can check", "÷ 22 working days" in _HA["basis"] and _HA["source"].startswith("Wayscope"))

# chart 1
RC = C2["route_caps"]
_cond = bulletin.conditions_of_month(10, factors=factors)
ok("⭐ chart 1: R001 carries round(100 ÷ 22, 3) = 4.545 movements a day against a cap of 4: over, 114 %, over by 0.545",
   RC["state"] == "set" and RC["rows"][0]["route_id"] == R1 and RC["rows"][0]["movements_per_day"] == round(100 / 22, 3)
   and RC["rows"][0]["cap"] == 4 and RC["rows"][0]["over"] and RC["rows"][0]["pct"] == round(100 / 22 * 100 / 4)
   and RC["rows"][0]["over_by"] == round(100 / 22 - 4, 3) and RC["rows"][0]["route"] == "Pit West → Yard East", str(RC)[:300])
ok("🔴 chart 1 is the Conditions panel's rule: its over rows are exactly conditions_of_month's exceeded list",
   [(r["route_id"], r["cap"], r["movements_per_day"], r["over_by"]) for r in RC["rows"] if r["over"]]
   == [(x["route_id"], x["cap"], x["two_way_a_day"], x["over_by"]) for x in _cond["route_caps"]["exceeded"]]
   and _cond["route_caps"]["routes_with_cap"] == RC["routes_with_cap"] == 1, str(_cond["route_caps"]))
ok("chart 1 lists the routes with no cap after the capped ones, never compared; the headline counts the over route",
   [r["route_id"] for r in RC["rows"]][1:] and all(r["cap"] is None and not r["over"] for r in RC["rows"][1:])
   and RC["routes_without_cap"] == 2 and RC["headline"] == "1 route over its cap" and clp.CAP_DIFF in RC["basis"],
   str(RC.get("headline")))
# chart 1b
SC = C2["site_caps"]
_lv = gate_arrivals.location_visits(10, factors=factors, working_days=WD)
ok("⭐ chart 1b: Yard East has 100 ÷ 22 = 4.5 visits a day against a CLP cap of 4: over, 114 %; the figures are location_visits'",
   SC["state"] == "set" and SC["rows"][0]["site"] == "Yard East" and SC["rows"][0]["visits_per_day"] == _lv[d1]["visits_per_day"] == 4.5
   and SC["rows"][0]["cap"] == 4.0 and SC["rows"][0]["over"] and SC["rows"][0]["pct"] == 114
   and SC["headline"] == "1 site over its CLP cap", str(SC)[:300])
ok("chart 1b: Pit West counts the lorries coming to load (R001 100 + R003 20 = 120 ÷ 22 = 5.5), no cap, not compared",
   {r["site"]: r for r in SC["rows"]}["Pit West"]["visits_per_day"] == round(120 / 22, 1)
   and {r["site"]: r for r in SC["rows"]}["Pit West"]["cap"] is None and not {r["site"]: r for r in SC["rows"]}["Pit West"]["over"])
# chart 5
EC = C2["euro_class"]
ok("⭐ chart 5 with the artic typed Euro VI: set; the rigid's loads are 'Not typed' (never guessed), drawn last",
   EC["state"] == "set" and [s["group"] for s in EC["series"]] == ["Euro VI", "Not typed"]
   and EC["series"][0]["loads"] == [120, 50] and EC["series"][1]["loads"] == [100, 0]
   and EC["vehicles_untyped"] == [clp._veh_label(RIGID, factors)] and EC["headline"] == "Euro VI: 63 % of the loads", str(EC)[:300])
# chart 6
CO = C2["councils"]
_al = areas.area_load(10, working_days=WD, geometry=False)
_ald = {a["name"]: a for a in _al["areas"] if a["tier"] == "district"}
ok("⭐ chart 6 is area_load's districts (the county row left out), sorted by distance; movements and laden km are its own",
   CO["state"] == "set" and CO["tier"] == "district" and {r["council"] for r in CO["rows"]} <= set(_ald)
   and all(r["movements_per_day"] == round(_ald[r["council"]]["movements_per_day"], 1)
           and r["laden_distance"] == round(_ald[r["council"]]["laden_lorry_km"], 1) for r in CO["rows"])
   and [r["distance"] for r in CO["rows"]] == sorted([r["distance"] for r in CO["rows"]], reverse=True), str(CO)[:400])
ok("chart 6: laden + empty = the area's lorry-km (to the rounding), the double-count sentence and the licence lines ride along",
   all(abs((r["laden_distance"] or 0) + (r["empty_distance"] or 0) - round(_ald[r["council"]]["lorry_km"], 1)) <= 0.11 for r in CO["rows"])
   and CO["double_count"] == areas.DOUBLE_COUNT and CO["attribution"] == ATTR and CO["distance_word"] == "lorry-km")
# REVERSED 9 Nov 2026 (v2.1 2.1-11b, question A): each PASS of a leg counts, so the empty way back through Southshire
# is its "out" movements; under 2 movements a visit it equals the loads ÷ working days of that leg (area_load's own figure)
ok("chart 6: Southshire carries R002's empty return only — its out movements and its distance, no laden km",
   ({r["council"]: r for r in CO["rows"]}.get("Southshire", {}).get("movements_per_day") or 0) > 0
   and {r["council"]: r for r in CO["rows"]}["Southshire"]["movements_per_day"]
       == round(_ald["Southshire"].get("out_per_day") or 0, 1)
   and {r["council"]: r for r in CO["rows"]}["Southshire"]["laden_distance"] == 0.0
   and ({r["council"]: r for r in CO["rows"]}.get("Southshire", {}).get("empty_distance") or 0) > 0, str(CO["rows"]))
# chart 10 with the target
CR2 = C2["carbon_rate"]
_st = carbon_target.status(acc_planner, carbon_target.get(), factors=factors)
_base = carbon.scenario(acc_planner, status="Approved", factors=factors)["baseline"]["totals"]
ok("⭐ chart 10's target is carbon_target.status's target_t shared out over the plan's tonnes",
   CR2["target_t"] == _st["target_t"]
   and CR2["target_kg_per_tonne"] == round(_st["target_t"] * 1000 / _base["tonnes"], 2) and CR2["target_note"] is None, str(CR2)[:300])
ok("🔴 per load carries NO target line, and says why: the lorry swap raises Oct's kg a load (fewer, heavier loads) while the total falls",
   "target_kg_per_load" not in CR2 and CR2["per_load_note"] == clp.PER_LOAD_NOTE and clp.PER_LOAD_NOTE in CR2["basis"]
   and CR2["months"][0]["kg_per_load_decisions"] > CR2["months"][0]["kg_per_load"]
   and CR2["months"][0]["kg_per_tonne_decisions"] < CR2["months"][0]["kg_per_tonne"], str(CR2["months"][0]))
ok("chart 10 with decisions: Oct per load with the decisions is the scenario's (fewer loads, so more kg a load); the headline names both figures",
   CR2["months"][0]["kg_per_load_decisions"] is not None and CR2["months"][0]["kg_per_tonne_decisions"] is not None
   and CR2["headline"] == f"{CR2['plan_kg_per_tonne']:g} kg CO₂e a tonne planned; the target allows {CR2['target_kg_per_tonne']:g}")
# chart 16
TA = C2["trips_avoided"]
ok("⭐ chart 16: the swap takes R002 from 100 loads to ceil(2000 ÷ 29) = 69 in Oct — 31 lorry trips avoided, said in the headline",
   TA["state"] == "set" and TA["avoided"] == 100 - math.ceil(2000 / 29) == 31
   and TA["months"][0] == {"month_index": 10, "label": "Oct 2026", "loads_planned": 220, "loads_with_decisions": 189, "avoided": 31}
   and TA["months"][1]["avoided"] == 0 and TA["headline"] == "31 lorry trips avoided", str(TA)[:300])
ok("chart 16 names the decision in words and the lorry-km it saves (a figure ≥ 0)",
   TA["decisions"] == (carbon_target.get() or {}).get("lever_words") and len(TA["decisions"]) == 1
   and TA["distance_saved"] is not None and TA["distance_saved"] >= 0 and TA["distance_word"] == "lorry-km")
ok("⭐ with everything typed every chart has data", M2["with_data"] == M2["order"], str(M2["with_data"]))
ok("the peak bands ride on the reply in words",
   M2["peak_bands"] == [{"from": "07:00", "to": "10:00"}, {"from": "16:00", "to": "19:00"}]
   and M2["peak_words"].startswith("No deliveries 07:00–10:00 and 16:00–19:00")
   # NARROWED 17 Oct 2026: every gate has clock hours now, so the bands come off every gate (not 'where they are typed')
   and M2["peak_words"].endswith("taken off each gate's open hours: 08:00–17:00 where none are typed).")
   and "where they are typed" not in M2["peak_words"], M2["peak_words"])

# =========================================================================== #
#  6. Miles, a team code, the endpoint, the words                                  #
# =========================================================================== #
_doc = copy.deepcopy(config.load(conversions, use_cache=False))
_doc.setdefault("tenant", {})["distance_unit"] = "mi"
config.save(_doc, by="tester"); config.invalidate()
Mmi = clp.monitoring(10, acc_planner, factors=conversions.load_factors(), working_days=WD)
_w = {r["council"]: r for r in Mmi["charts"]["councils"]["rows"]}
ok("⭐ a miles tenant reads lorry-miles: each distance is the km ÷ 1.609344",
   Mmi["distance_unit"] == "mi" and Mmi["charts"]["councils"]["distance_word"] == "lorry-miles"
   and all(abs(_w[k]["distance"] - round(_ald[k]["lorry_km"] / config.KM_PER_MILE, 1)) <= 0.051 for k in _w)
   and Mmi["charts"]["trips_avoided"]["distance_word"] == "lorry-miles", str(_w)[:200])
_doc["tenant"].pop("distance_unit", None)
config.save(_doc, by="tester"); config.invalidate()
_txt = json.dumps(M2, ensure_ascii=False)
ok("🔴 team NAMES only: no team slot id anywhere in the reply", re.search(r"\bIPT ?[1-6]\b", _txt) is None)
_banned = re.compile(r"\b(bake[ds]?|baking|line-month|cached|geometry|server|endpoint|truck|trucks|real-time|predict\w*|optimi[sz]\w*|telematics)\b|\btoken\b", re.I)
_hits = [s for s in strings(M2) if _banned.search(s)]
ok("🔴 the word rule over every string in the reply (no bake / line-month / cached / geometry / server / endpoint / token / truck …)",
   not _hits, str(_hits[:3]))
os.environ["IPT2_CODE"] = "ipt2-secret"
try:
    access.set_current("ipt2-secret")
    acc_t2 = access.current()
    MT = clp.monitoring(10, acc_t2, factors=conversions.load_factors(), working_days=WD)
finally:
    os.environ.pop("IPT2_CODE", None)
    access.set_current("planner123")
ok("⭐ a team code: scope team; the vehicle chart holds only its lines (100 rigid loads); the caps and councils are the scheme's",
   MT["scope"] == "team" and MT["charts"]["vehicle_types"]["totals"] == [100]
   and MT["charts"]["route_caps"]["rows"] == C2["route_caps"]["rows"] and MT["charts"]["councils"]["rows"] == C2["councils"]["rows"]
   and "the whole scheme for the caps and councils" in MT["scope_line"], str(MT["charts"]["vehicle_types"])[:200])
ok("...and its target is its own share (target_scope team)", MT["charts"]["carbon_rate"]["target_scope"] == "team")
ok("⭐ card 4, team scope: the team code's tonnes are its own lines only (R002: 2 000 t planned, 500 t recorded, one line)",
   MT["charts"]["recorded_tonnes"]["state"] == "set"
   and [(m.get("planned_month_t"), m["recorded_t"], m["lines_reported"]) for m in MT["charts"]["recorded_tonnes"]["months"]] == [(2000.0, 500.0, 1)]   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks
   and MT["charts"]["recorded_tonnes"]["months"][0]["planned_t"] == 400.0   # D-I4: R002 is typed to week 1 only: 1 of Oct's 5 weeks
   and MT["charts"]["recorded_tonnes"]["recorded_to"] == weeks.week_span(10, 1)[1].isoformat()
   and MT["recorded_line"] == f"Recorded tonnes as typed on Account, weeks to {clp._day_words(weeks.week_span(10, 1)[0], year=True)}.",   # REVERSED 11 Nov 2026 (D-F3): the week's Monday (Oct week 1 starts Mon 28 Sep)
   str(MT["charts"]["recorded_tonnes"])[:300])
ok("the endpoint: main.clp_monitoring(10) returns the same dict as clp.monitoring(10, acc, …)",
   main.clp_monitoring(10) == clp.monitoring(10, access.current(), factors=conversions.load_factors(), working_days=main._working_days(conversions.load_factors())))
_e = [_raises(lambda: main.clp_monitoring(0)), _raises(lambda: main.clp_monitoring(main.MONTH_COUNT + 1))]
ok("month 0 and 61 are a 400 with the sentence", all(getattr(x, "status_code", None) == 400 and "month must be 1.." in x.detail for x in _e))
access.set_current("")
_e401 = _raises(lambda: main.clp_monitoring(10))
access.set_current("planner123")
ok("no code -> 401", getattr(_e401, "status_code", None) == 401, repr(_e401))
ok("an empty month (Jan 2026): every chart empty, each with a sentence, no figure",
   all(c["state"] == "empty" and c["missing"] for c in clp.monitoring(1, acc_planner, factors=conversions.load_factors(), working_days=WD)["charts"].values()
       if c["key"] in ("route_caps", "site_caps", "councils")))

# =========================================================================== #
#  6b. W10: the CLP pack — exactly the charts with data, the demo notice on every page and sheet  #
# =========================================================================== #
import io as _io  # noqa: E402
import export as _export  # noqa: E402
import clp_pack  # noqa: E402
import openpyxl as _openpyxl  # noqa: E402
from portable import pdf_text as _pdf_text  # noqa: E402
offline(_export)
_doc = copy.deepcopy(config.load(conversions, use_cache=False))
_doc.setdefault("tenant", {})["demo_notice"] = "Fictional demo scheme · nothing here is real"
config.save(_doc, by="tester"); config.invalidate()
MP = clp.monitoring(10, acc_planner, factors=conversions.load_factors(), working_days=WD)
ok("the pack's month carries the demo notice from the tenant block", MP["demo_notice"] == "Fictional demo scheme · nothing here is real")
_pdf = clp_pack.build_pdf(MP, generated="14 Oct 2026")
_pt = re.sub(r"\s+", " ", _pdf_text(_pdf) or "")
_pages = len(re.findall(r"page \d+", _pt))
ok("⭐ W10 PDF: titled for the month, the demo notice on EVERY page, the stamp 'planned, not observed'",
   "Wayscope · CLP monitoring pack · Oct 2026" in _pt and _pages >= 2
   and _pt.count("Fictional demo scheme · nothing here is real") >= _pages
   and "Planned figures from the approved plan, not observed: Wayscope holds no gate log or arrival times." in _pt, f"{_pages} pages")
ok("⭐ W10 PDF: every chart with data, in the section's order, each with its headline, how it is worked out and its source",
   all(MP["charts"][k]["title"] in _pt and MP["charts"][k]["headline"] in _pt for k in MP["with_data"])
   and [_pt.index(MP["charts"][k]["title"]) for k in MP["with_data"]] == sorted(_pt.index(MP["charts"][k]["title"]) for k in MP["with_data"])
   and _pt.count("How it is worked out: ") == len(MP["with_data"]) and _pt.count("Source: Wayscope") == len(MP["with_data"]), _pt[:300])
ok("⭐ card 4 PDF: the planned and recorded tonnes come first, with their table (Oct 2026 5 480 2 000 36 % 2), and the "
   "recorded line follows the limit in the first paragraph; the page stamp is unchanged",
   MP["with_data"][0] == "recorded_tonnes" and "Planned and recorded tonnes" in _pt
   and _pt.index("Planned and recorded tonnes") < _pt.index(MP["charts"]["route_caps"]["title"])
   and "Oct 2026 (part) 2,192 to the week of 5 Oct 2,000 91 % 2" in _pt   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks   # NARROWED 11 Nov 2026 (7a): Oct is typed to 11 Oct only, so labelled a part month; REVERSED (D-F1/D-F3): "(part)", commas
   and "Planned figures, not observed: Wayscope holds no gate log or arrival times. Recorded tonnes as typed on Account, weeks to 5 Oct 2026." in _pt
   and _pt.count("Recorded tonnes as typed on Account") == 1
   and "Planned figures from the approved plan, not observed: Wayscope holds no gate log or arrival times." in _pt
   and "avoided" not in _pt[_pt.index("Planned and recorded tonnes"):_pt.index(MP["charts"]["route_caps"]["title"])], _pt[:600])
# 11 Nov 2026 (D-F8, John: "do it now"): the recorded words are their own line under the scope + limit, in the pack as on
# the screen (one line ran to 26 words and failed the audit's long-prose rule); the words themselves do not change
_ptl = [ln.strip() for ln in (_pdf_text(_pdf) or "").splitlines()]
ok("🔴 D-F8 PDF: the recorded line starts a line of its own; no line runs the limit and the recorded words together",
   any(ln.startswith("Recorded tonnes as typed on Account, weeks to 5 Oct 2026.") for ln in _ptl)   # REVERSED 12 Nov 2026 (batch 2, D-F3 on D-F8): the week's Monday, "weeks to"
   and not any("arrival times." in ln and "Recorded tonnes" in ln for ln in _ptl),
   str([ln for ln in _ptl if "Recorded tonnes" in ln or "arrival times." in ln][:4]))
ok("D-F8: each of the two note lines stays within the long-prose rule (25 words): the scope + limit, and the recorded line",
   len(f"{MP['scope_line']} {MP['limit']}".split()) <= 25 and 0 < len((MP["recorded_line"] or "").split()) <= 25,
   str((MP["scope_line"], MP["limit"], MP["recorded_line"])))
_M11P = clp.monitoring(11, acc_planner, factors=conversions.load_factors(), working_days=WD)
_h11, _r11 = clp_pack.table_of(_M11P["charts"]["recorded_tonnes"], _M11P)
_p11 = re.sub(r"\s+", " ", _pdf_text(clp_pack.build_pdf(_M11P, generated="11 Nov 2026")) or "")
ok("⭐ card 4 pack: a month nobody typed prints 'not recorded', never 0 (table, PDF)",
   _h11 == ["Month", "Planned t", "Recorded t", "Recorded share", "Lines reported"]
   and _r11 == [["Oct 2026 (part)", "2,192 to the week of 5 Oct", "2,000", "91 %", "2"], ["Nov 2026", "1,450", "not recorded", "—", "—"]]   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks   # NARROWED 11 Nov 2026 (7a); REVERSED (D-F1/D-F3)
   and "Nov 2026 1,450 not recorded — —" in _p11, str(_r11) + " | " + _p11[:300])
_ME0 = copy.deepcopy(MP)
_ME0["recorded_line"] = None
_ME0["charts"]["recorded_tonnes"] = {**{x: MP["charts"]["recorded_tonnes"][x] for x in ("key", "number", "title", "serves")},
                                     "state": "empty", "missing": "No tonnes typed on Account up to Oct 2026."}
_ME0["with_data"] = [k for k in _ME0["order"] if _ME0["charts"][k]["state"] == "set"]
_p0 = re.sub(r"\s+", " ", _pdf_text(clp_pack.build_pdf(_ME0, generated="11 Nov 2026")) or "")
ok("card 4 pack: with nothing recorded there is no recorded line, and the tonnes are listed as not drawn with their sentence",
   "Recorded tonnes as typed on Account" not in _p0 and "Planned and recorded tonnes: No tonnes typed on Account up to Oct 2026." in _p0)
ok("W10 PDF: the figures are printed as a table too (Pit West → Yard East 4.5 against 4, 114 %; 31 trips avoided)",
   "Pit West → Yard East 4.5 4 114 % Over the cap" in _pt and "Oct 2026 220 189 31" in _pt, _pt[:200])
ok("🔴 W10 PDF: no team id, none of the banned words",
   re.search(r"\bIPT ?[1-6]\b", _pt) is None
   and not re.search(r"\b(bake[ds]?|line-month|cached|geometry|server|endpoint|token|trucks?|real-time|predict\w*|optimi[sz]\w*)\b", _pt, re.I))
# a month with charts missing: they are named with what they need, never drawn as empty
_ME = copy.deepcopy(MP)
for _k in ("euro_class", "trips_avoided"):
    _ME["charts"][_k] = {**{x: _ME["charts"][_k][x] for x in ("key", "number", "title", "serves")}, "state": "empty",
                         "missing": clp.monitoring(10, acc_planner, factors=factors, working_days=WD)["charts"][_k].get("missing") or "no data"}
_ME["with_data"] = [k for k in _ME["order"] if _ME["charts"][k]["state"] == "set"]
_pe = re.sub(r"\s+", " ", _pdf_text(clp_pack.build_pdf(_ME, generated="14 Oct 2026")) or "")
ok("⭐ W10 PDF: a chart with no data is not drawn — it is listed under 'Not drawn this month' with what it needs",
   "Not drawn this month" in _pe and f"{_ME['charts']['euro_class']['title']}: " in _pe
   and _pe.count(_ME["charts"]["euro_class"]["title"]) == 1 and _pe.count("How it is worked out: ") == len(_ME["with_data"]))
_wb = _openpyxl.load_workbook(_io.BytesIO(clp_pack.build_xlsx(MP, generated="2026-10-14T12:00:00Z")))
ok("⭐ W10 XLSX: About first, then one sheet a chart with data, named for it",
   _wb.sheetnames == ["About"] + [clp_pack.SHEET[k] for k in MP["with_data"]], str(_wb.sheetnames))
_ab = [[c.value for c in r] for r in _wb["About"].iter_rows()]
ok("W10 XLSX: the demo notice heads every sheet in the demo bar's colours; About names the month, the scope and the basis",
   all(_wb[n]["A1"].value == "Fictional demo scheme · nothing here is real" and (_wb[n]["A1"].font.color.rgb or "").endswith(_export.DEMO_FG_HEX)
       for n in _wb.sheetnames)
   and ["Month", "Oct 2026"] == [x for x in _ab if x[0] == "Month"][0][:2] and any(x[0] == "Scope" and x[1] == MP["scope_line"] for x in _ab))
_rt_x = [[c.value for c in r] for r in _wb[clp_pack.SHEET["recorded_tonnes"]].iter_rows()]
ok("⭐ card 4 XLSX: the 'Planned and recorded' sheet comes right after About, with its table; About says the recorded line",
   _wb.sheetnames[1] == clp_pack.SHEET["recorded_tonnes"] == "Planned and recorded" and len(clp_pack.SHEET["recorded_tonnes"]) <= 31
   and ["Month", "Planned t", "Recorded t", "Recorded share", "Lines reported"] in [r[:5] for r in _rt_x]
   and ["Oct 2026 (part)", "2,192 to the week of 5 Oct", "2,000", "91 %", "2"] in [r[:5] for r in _rt_x]   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks   # NARROWED 11 Nov 2026 (7a); REVERSED (D-F1/D-F3)
   and any(x[0] == "Recorded" and x[1] == "Recorded tonnes as typed on Account, weeks to 5 Oct 2026." for x in _ab)   # REVERSED 11 Nov 2026 (D-F3)
   and any(x[0] == "Basis" and x[1] == clp.SPREAD for x in _ab), str(_wb.sheetnames))
_x11 = [[c.value for c in r] for r in _openpyxl.load_workbook(_io.BytesIO(clp_pack.build_xlsx(_M11P)))[clp_pack.SHEET["recorded_tonnes"]].iter_rows()]
ok("card 4 XLSX: the month nobody typed reads 'not recorded'", ["Nov 2026", "1,450", "not recorded", "—", "—"] in [r[:5] for r in _x11])   # REVERSED 11 Nov 2026 (D-F1)
_rc = [[c.value for c in r] for r in _wb[clp_pack.SHEET["route_caps"]].iter_rows()]
ok("🔴 D-F5: the XLSX route-cap sheet's header row reads Visits a day, never Movements a day",
   ["Route", "Visits a day", "Cap", "Share of cap", "Status"] in [r[:5] for r in _rc]
   and not any("Movements a day" in [str(x) for x in r] for r in _rc))
ok("W10 XLSX: a chart's sheet holds its table and says how it is worked out and its source",
   ["Pit West → Yard East", "4.5", "4", "114 %", "Over the cap"] in [r[:5] for r in _rc]
   and any(r[0] == "How it is worked out" and r[1] == MP["charts"]["route_caps"]["basis"] for r in _rc)
   and any(r[0] == "Source" for r in _rc))
_wbe = _openpyxl.load_workbook(_io.BytesIO(clp_pack.build_xlsx(_ME)))
ok("W10 XLSX: a chart with no data has no sheet; About lists it as not drawn with what it needs",
   clp_pack.SHEET["euro_class"] not in _wbe.sheetnames
   and any(x[0] == "Not drawn" and str(x[1]).startswith(_ME["charts"]["euro_class"]["title"] + ": ") for x in [[c.value for c in r] for r in _wbe["About"].iter_rows()]))
ok("W10: the file name is the month's: wayscope-clp-pack-2026-10.pdf / .xlsx",
   clp_pack.file_name(MP, "pdf") == "wayscope-clp-pack-2026-10.pdf" and clp_pack.file_name({"month": 13}, "xlsx") == "wayscope-clp-pack-2027-01.xlsx")
_rp = main.clp_pack_pdf(10)
_rx = main.clp_pack_xlsx(10)
ok("⭐ W10 endpoints: the PDF and the XLSX for a month, as attachments under the month's file name",
   _rp.media_type == "application/pdf" and _rp.headers["Content-Disposition"] == 'attachment; filename="wayscope-clp-pack-2026-10.pdf"'
   and (_rp.body or b"")[:4] == b"%PDF"
   and _rx.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
   and _rx.headers["Content-Disposition"] == 'attachment; filename="wayscope-clp-pack-2026-10.xlsx"' and (_rx.body or b"")[:2] == b"PK")
_e = [_raises(lambda: main.clp_pack_pdf(0)), _raises(lambda: main.clp_pack_xlsx(None))]
ok("W10 endpoints: no month or month 0 is a 400", all(getattr(x, "status_code", None) == 400 for x in _e))
access.set_current("")
_e401 = _raises(lambda: main.clp_pack_pdf(10))
access.set_current("planner123")
ok("🔴 W10 endpoints: no code -> 401", getattr(_e401, "status_code", None) == 401)
ok("W10 PDF: the trips avoided are written over the month's pair ('31 avoided') where there is room", "31 avoided" in _pt, _pt[-400:])

# 17 Oct 2026: a 24-month window with loads in every month (the four-year demo, branch claude/demo-programme) made the
# vehicle and Euro class tables 49 columns across, and build_pdf failed in reportlab ("negative availWidth") -> the pack
# PDF answered 500. On paper those two tables now run one row a month, and any table too wide for A4 is split into column
# groups that repeat the first column. The figures and the XLSX are unchanged.
import brand_pdf as _brand_pdf  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth as _sw  # noqa: E402
_M24 = copy.deepcopy(MP)
_lab24 = [f"{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i % 12]} {2026 + i // 12}" for i in range(24)]
_NAMES9 = [f"Vehicle type number {i} with a long name ({20 + i}t)" for i in range(1, 9)] + [clp_pack.NOT_TYPED]
for _k in ("vehicle_types", "euro_class"):
    _c = _M24["charts"][_k]
    _c["months"] = [{"month_index": i + 1, "label": _lab24[i]} for i in range(24)]
    _names = _NAMES9 if _k == "vehicle_types" else ["Euro VI", "Euro V", clp_pack.NOT_TYPED]
    _lds = [[1000 + 37 * _j + 101 * i for i in range(24)] for _j in range(len(_names))]
    _c["totals"] = [sum(ld[i] for ld in _lds) for i in range(24)]
    _c["series"] = [{"group": _nm, "label": _nm, "loads": _ld, "total": sum(_ld),
                     "pct": [round(100.0 * x / _c["totals"][i], 1) for i, x in enumerate(_ld)]} for _nm, _ld in zip(_names, _lds)]
for _k in ("carbon_rate", "trips_avoided"):
    _c = _M24["charts"][_k]
    _c["months"] = [dict(_c["months"][0], label=_lab24[i], month_index=i + 1) for i in range(24)]
for _i, _m in enumerate(_M24["charts"]["trips_avoided"]["months"]):
    _m["avoided"] = 31 + _i
    _m["loads_with_decisions"] = _m["loads_planned"] - _m["avoided"]
_F = _brand_pdf.fonts()
_usable = _export.A4[0] - 28 * _export.mm
try:
    _p24 = clp_pack.build_pdf(_M24, generated="17 Oct 2026")
    _e24 = ""
except Exception as e:  # noqa: BLE001
    _p24, _e24 = b"", f"{type(e).__name__}: {e}"
ok("⭐ 24-month window: the CLP pack PDF builds (49 columns across used to fail in reportlab -> a 500)", _p24[:4] == b"%PDF", _e24)
_t24 = re.sub(r"\s+", " ", _pdf_text(_p24) or "") if _p24 else ""
ok("⭐ 24-month window: every chart with data is in the PDF with its table, every month of the window named",
   all(_M24["charts"][k]["title"] in _t24 for k in _M24["with_data"])
   and _t24.count("How it is worked out: ") == len(_M24["with_data"])
   and all(_t24.count(m) >= 4 for m in _lab24), [m for m in _lab24 if _t24.count(m) < 4][:5])
ok("24-month window: nothing truncated — every vehicle type's full name is printed (the key used to cut at 30 letters)",
   all(n in _t24 for n in _NAMES9), [n for n in _NAMES9 if n not in _t24][:3])
ok("24-month window: where '31 avoided' does not fit over a pair, every month's figure stands alone and the key says what it is",
   "Figure over a pair: trips avoided" in _t24 and not re.search(r"\d avoided", _t24)
   and all(f"{31 + i}" in _t24 for i in range(24)), _t24[-600:])
_M24b = copy.deepcopy(_M24)
for _i, _m in enumerate(_M24b["charts"]["trips_avoided"]["months"]):
    _m["loads_planned"], _m["avoided"], _m["loads_with_decisions"] = 9000, 1200 + _i, 9000 - 1200 - _i
_t24b = re.sub(r"\s+", " ", _pdf_text(clp_pack.build_pdf(_M24b, generated="17 Oct 2026")) or "")
ok("24-month window: where not even every figure fits over its pair, none is drawn there and the key points to the table, "
   "which still holds every month", "Trips avoided each month: the table below" in _t24b and "Figure over a pair" not in _t24b
   and all(f"{_lab24[i]} 9,000 {_n24} {_a24}" in _t24b for i, _n24, _a24 in   # REVERSED 11 Nov 2026 (D-F1): commas for thousands
           [(i, f"{(9000 - 1200 - i):,}", f"{1200 + i:,}") for i in range(24)]),
   _t24b[-500:])


def _fits(tb):
    """Every column at least as wide as its widest figure; the table no wider than the page."""
    if tb["widths"] is None:
        return len(tb["header"][0]) <= 8
    good = sum(tb["widths"]) <= _usable + 0.01
    for r in tb["rows"]:
        for x, w in zip(r, tb["widths"]):
            if clp_pack.FIGURE.match(str(x)) and _sw(str(x), _F["regular"], 7) > w - 2 * clp_pack.PAD + 0.01:
                good = False
    return good


_all_fit = True
for _k in _M24["with_data"]:
    for _tb in clp_pack.pdf_tables(_M24["charts"][_k], _M24, _usable, _F):
        _all_fit = _all_fit and _fits(_tb)
ok("⭐ 24-month window: every table on paper fits A4 and no figure is narrower than its column", _all_fit)
_vt = clp_pack.pdf_tables(_M24["charts"]["vehicle_types"], _M24, _usable, _F)
ok("24-month window: nine vehicle types do not fit one table — split into column groups, each repeating the Month column",
   len(_vt) >= 2 and all(tb["header"][0][0] == "Month" and [r[0] for r in tb["rows"]] == _lab24 for tb in _vt), str(len(_vt)))
# every figure of the XLSX's table is on paper, in its month and vehicle type's place
_h, _rows = clp_pack.table_of(_M24["charts"]["vehicle_types"], _M24)
_paper = {}
for _tb in _vt:
    _top, _sub = _tb["header"]
    _cur = None
    for _j in range(1, len(_top)):
        _cur = _top[_j] if _top[_j] else _cur
        for _r in _tb["rows"]:
            _paper[(_r[0], _cur, _sub[_j] or _top[_j])] = _r[_j]
_want = {}
for _r in _rows:
    for _i, _m in enumerate(_lab24):
        if _r[0] == "All loads":
            _want[(_m, "All loads", "All loads")] = _r[1 + _i]
        else:
            _want[(_m, _r[0], "Loads")] = _r[1 + _i]
            _want[(_m, _r[0], "Share")] = _r[25 + _i]
ok("⭐ 24-month window: the paper tables hold exactly the XLSX table's figures (one row a month, the same strings)",
   _paper == _want, str(len(_paper)) + " vs " + str(len(_want)))
ok("24-month window: the XLSX is unchanged — one column a month for loads and for share",
   len(_h) == 49 and _h[0] == "Vehicle type" and _h[1] == f"{_lab24[0]} loads" and _h[25] == f"{_lab24[0]} share")
_wb24 = _openpyxl.load_workbook(_io.BytesIO(clp_pack.build_xlsx(_M24)))
_vs = [[c.value for c in r] for r in _wb24[clp_pack.SHEET["vehicle_types"]].iter_rows()]
ok("24-month window: the XLSX sheet's header row is table_of's 49 columns", _h in [r[:49] for r in _vs])
_rt = clp_pack.pdf_tables(MP["charts"]["route_caps"], MP, _usable, _F)
ok("a table that already fits A4 keeps its layout: one table, the XLSX's header, reportlab sharing the width out",
   len(_rt) == 1 and _rt[0]["widths"] is None and _rt[0]["header"] == [clp_pack.table_of(MP["charts"]["route_caps"], MP)[0]])
# ---- 11 Nov 2026 (D-F5, John's yes): the route figure is lorry VISITS a day (one load = one visit, the cap typed in visits),
# as the subtitle says; the bar words and the table header said "movements a day". Councils really are movements: unchanged.
ok("🔴 D-F5: the pack's route-cap table is headed 'Visits a day', never 'Movements a day'",
   clp_pack.table_of(MP["charts"]["route_caps"], MP)[0] == ["Route", "Visits a day", "Cap", "Share of cap", "Status"]
   and "Route Visits a day Cap Share of cap Status" in _pt and "Route Movements a day" not in _pt,
   str(clp_pack.table_of(MP["charts"]["route_caps"], MP)[0]))
ok("🔴 D-F5: the pack's route-cap bars read '4.5 visits a day · 114 % of 4'; no bar says 'movements a day · N % of'",
   "4.5 visits a day · 114 % of 4" in _pt and not re.search(r"movements a day · \d+ % of", _pt),
   _pt[_pt.find(MP["charts"]["route_caps"]["title"]):_pt.find(MP["charts"]["route_caps"]["title"]) + 300])
ok("D-F5: the subtitle still says lorry visits a day, and the councils keep 'Movements a day' (they count movements)",
   MP["charts"]["route_caps"]["subtitle"].startswith("lorry visits a day")
   and clp_pack.table_of(MP["charts"]["councils"], MP)[0][1] == "Movements a day" if MP["charts"].get("councils", {}).get("rows")
   else MP["charts"]["route_caps"]["subtitle"].startswith("lorry visits a day"))
_doc["tenant"]["demo_notice"] = None
config.save(_doc, by="tester"); config.invalidate()

# =========================================================================== #
#  7. The fixture for the frontend harnesses (planner, Oct 2026, every chart set)  #
# =========================================================================== #
_fix = os.path.join(HERE, "fixtures", "clp_monitoring.json")
if not FAIL:
    with open(_fix, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(M2, indent=1, ensure_ascii=False))
ok("the fixture backend/tests/fixtures/clp_monitoring.json is written from a clean run, LF on disk",
   os.path.exists(_fix) and b"\r\n" not in open(_fix, "rb").read())

# ---- 11 Nov 2026 (John: yes, 7c as recommended): "Generated <date>" off the pack's title line, to the foot
_lay = (_pdf_text(_pdf) or "").splitlines()
ok("🔴 7c: no line of the pack carries both the title and 'Generated' (they ran into each other on page 1)",
   not [l for l in _lay if "CLP monitoring pack · Oct 2026" in l and "Generated" in l], str([l for l in _lay if "Generated" in l][:3]))
ok("⭐ 7c: 'Generated 14 Oct 2026' is in the foot of every page, after the pack's name; the frame's right-hand stamp is not used",
   _pt.count("Generated 14 Oct 2026") >= _pages and "CLP monitoring pack · Generated 14 Oct 2026" in _pt
   and 'right=(f"Generated' not in open(os.path.join(BACKEND, "clp_pack.py"), encoding="utf-8").read(), f"{_pt.count('Generated 14 Oct 2026')} of {_pages}")

# ---- 11 Nov 2026 (John: yes, 7a as recommended): a part month is labelled "(to <date>)"; the headline names the last
# COMPLETE month (Oct, typed in weeks 1-2 above), never the part one, so Nov's first week does not read as a shortfall
_nw = weeks.set_actual(R1, 11, "earthworks", "WS1", 1, actual_qty=300.0, by="clerk")
_n1_end = weeks.week_span(11, 1)[1]
_keep_today = clp._today_date
clp._today_date = lambda: _dt.date(2026, 11, 12)
_M7a = clp.monitoring(11, acc_planner, factors=factors, working_days=WD)
clp._today_date = _keep_today
_R7a = _M7a["charts"]["recorded_tonnes"]
_byi = {m["month_index"]: m for m in _R7a.get("months") or []}
_nd = f"{_n1_end.day} Nov"
_nm = f"{weeks.week_span(11, 1)[0].day} Nov"       # D-F3: the week's Monday names it
ok("7a set-up: Nov week 1 typed (300 t on R001), its week ends before the month does", "error" not in (_nw or {})
   and _n1_end < _dt.date(2026, 11, 30), str(_nw)[:200])
ok("⭐ 7a: the part month keeps its bar and row, labelled 'Nov 2026 (part)' (D-F3: never a day); a complete month keeps its plain label",
   _byi[11]["recorded_t"] == 300.0 and _byi[11]["label"] == "Nov 2026 (part)" and _byi[11]["part_to"] == _n1_end.isoformat()   # NARROWED 11 Nov 2026 (D-F3)
   and _byi[10]["part_to"] is None and _byi[10]["label"] == "Oct 2026", str(_R7a.get("months")))
ok("🔴 7a: the headline names the last COMPLETE month (Oct), not the part month picked; 'recorded to' names the part month's week",
   _R7a["headline"].startswith("Oct 2026: 2,000 t recorded, 36 % of the 5,480 t planned") and _R7a["headline"].endswith(f"· recorded to the week of {_nm}")
   and not _R7a["headline"].startswith("Nov") and _M7a["recorded_line"] == f"Recorded tonnes as typed on Account, weeks to {_nm} 2026.", _R7a["headline"])   # REVERSED 11 Nov 2026 (D-F1/D-F3)
_p7a = re.sub(r"\s+", " ", _pdf_text(clp_pack.build_pdf(_M7a, generated="12 Nov 2026")) or "")
ok("7a: the pack's table prints the part month as 'Nov 2026 (part)' with its own figures", "Nov 2026 (part) 362 to the week of 2 Nov 300 83 % 1" in _p7a,   # NARROWED 11 Nov 2026 (D-I4, John's yes): a part month is set against the plan of the same weeks   # REVERSED 11 Nov 2026 (D-F1/D-F3)
   _p7a[_p7a.find("Month Planned"):_p7a.find("Month Planned") + 200])

# ---- 11 Nov 2026 (D-F1 / 7b, John's yes): thousands with a comma in CLP monitoring and the pack; percentages keep the space
ok("🔴 D-F1: the pack's number helper and the headline helper write a comma for thousands; a percentage keeps its space",
   clp_pack._n(28719, 0) == "28,719" and clp_pack._n(1234.56) == "1,234.6" and clp_pack._n(999, 0) == "999" and clp._t_words(32174.4) == "32,174"
   and "91 % 2" in _pt and "91 %" in RT["headline"])   # NARROWED 11 Nov 2026 (D-I4): Oct's share is of the plan to its typed week
ok("🔴 D-F1: no pack page prints a thousands figure with a space (5 480 / 2 000 / 1 450), and the trips-avoided headline has no space",
   all(x not in (_pt + _p11 + _p7a) for x in ("5 480", "2 000", "1 450", "9 000")) and "5,480" in _pt
   and not re.search(r"\d \d{3} (more )?lorry trips", str(MP["charts"].get("trips_avoided", {}).get("headline") or "")))
# ---- 11 Nov 2026 (D-I4, John's yes, option a): a part month is set against the plan of the same weeks
ok("🔴 D-I4: with Nov typed to week 1, Nov's planned bar is its week 1 (1 450 of 4 weeks = 362.5), its share 300 of that (83 %); "
   "Oct, now complete, keeps the whole month's plan and its 36 %",
   _byi[11]["planned_t"] == 362.5 and _byi[11].get("planned_month_t") == 1450.0 and _byi[11]["recorded_pct"] == 83
   and _byi[11].get("planned_to_week") == weeks.week_span(11, 1)[0].isoformat()
   and _byi[10]["planned_t"] == _byi[10].get("planned_month_t") == 5480.0 and _byi[10]["recorded_pct"] == 36 and _byi[10].get("planned_to_week", "missing") is None,
   str(_R7a.get("months")))
ok("D-I4: a line with no weeks on the Look-ahead yet is shared out evenly over the month's weeks (500 t, 2 of Oct's 5 weeks = 200)",
   getattr(clp, "_planned_to_week", lambda *a: None)([{"route_id": "RX9", "month_index": 10, "discipline": "", "section_id": "", "tonnes": 500.0}], 10, 2) == 200.0
   and weeks.weeks_in_month(10) == 5)
ok("D-I4: the basis says a part month is set against the plan of the same weeks", "A part month is set against the plan of the same weeks." in _R7a["basis"])
# ---- 11 Nov 2026 (D-F3, John's yes): the words name the latest typed WEEK, never a day (Account takes a week's tonnes)
ok("🔴 D-F3: a part month reads '(part)', never '(to <date>)'; nothing says 'recorded to <day>' without 'the week of'",
   all("(to " not in m["label"] for m in (_R7a.get("months") or []) + (RT.get("months") or []))
   and "(to " not in _pt and "(to " not in _p7a and not re.search(r"recorded to \d", _pt + _p7a + RT["headline"] + _R7a["headline"]))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
