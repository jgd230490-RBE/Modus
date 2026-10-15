"""
The route map export (14 Oct 2026, backlog item 2: replaces the per-route sheet) — backend/route_map_export.py,
export.build_route_map_pdf and GET /api/routes/map-export.pdf.

WHAT IS ASSERTED
----------------
  * the figures per route are the bulletin roll-up's (bulletin.rollup_payloads, the public map bar's rules) on the
    same fixture test_bulletin hand-computes: three routes (one not drawn), five approved lines, one pending, one cap;
  * the filters work as the public map applies them: origin, destination and team from the ROUTE, discipline from the
    LINE; the Routes page's list of ids; a team code held to its own team;
  * places never ids, team names never ids, the flag a flag, closures "not checked" until a check is stored;
  * the NH Carbon Tool rows (H3) only when asked: per sheet, material, route and vehicle, one-way loaded km;
  * the PDF: A4 landscape, the scheme's block, the demo bar and the map tag, no banned word; MAP ONLY one page with the
    legend inside the map; forty routes run on to more pages; basemap.view frames the routes clear of the legend;
  * the endpoint is staff only (source; http_smoke drives it over HTTP).

WHAT THIS DOES NOT PROVE
------------------------
Mapbox is never called (portable.offline): the map here is the schematic. How the PDF LOOKS was checked by reading the
rendered pages (notes/session-1014-route-map-export.md). HERE is never called: geometry rows are typed in.

Run:  python3 backend/tests/test_route_map_export.py
"""
import datetime
import io
import json
import math
import os
import re
import sys
import tempfile
import types
from collections import defaultdict
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_carbon.py --------------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_rme_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import stockpiles  # noqa: E402
import clashes  # noqa: E402
import weeks  # noqa: E402
import costlines  # noqa: E402
import bulletin  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
access.set_current("planner123")
PLANNER = access.current()
TEAM1 = {"role": "ipt", "ipt": "IPT1", "label": "North Team"}

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
    db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
    db.init_tenant()
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    costing.invalidate()


# =========================================================================== #
#  Fixture                                                                     #
# =========================================================================== #
ART, R8 = "Artic Tipper (44t)", "Rigid 8-wheeler (32t)"

reset_db()
FACTORS = conversions.load_factors()
PAY_ART = float(FACTORS["vehicles"][ART]["payload_t"])
PAY_R8 = float(FACTORS["vehicles"][R8]["payload_t"])
WD = main._working_days(FACTORS)

for _id, _name, _type in (("L1", "Kelsey Quarry", "Quarry"), ("L2", "Mill Compound", "Compound"),
                          ("L3", "Ridge Pit", "Quarry"), ("L4", "Far Yard", "Compound")):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
               (_id, _name, 52.5, -1.0, _type))
# R1 and R2 are drawn (baked for the artic); R3 is NOT baked at all, so the map never draws it
for _rid, _o, _d, _ipt, _cap in (("R1", "L1", "L2", "IPT 1", 60), ("R2", "L3", "L2", "IPT 2", None),
                                 ("R3", "L1", "L4", "IPT 1", None)):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt, max_vehicles_per_day) "
               "VALUES (?, ?, ?, ?, ?, ?)", (_rid, _o, _d, "Small aggregate", _ipt, _cap))
tenant_package.import_rows("ipts", [
    {"id": "IPT1", "label": "North Team", "manager": None, "active": True, "merged_into": None},
    {"id": "IPT2", "label": "Central Team", "manager": None, "active": True, "merged_into": None}])


def _geom(rid, prof, leg, km, hr):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, "
               "geometry, distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               ("default", rid, prof, leg, 0, "[[-1,52.5],[-1.1,52.6]]", km, hr))


_geom("R1", ART, "loaded", 30, 0.6); _geom("R1", ART, "return", 30, 0.5)
_geom("R2", ART, "loaded", 10, 0.25); _geom("R2", ART, "return", 10, 0.2)

_n = [0]


def _line(rid, month, disc, sect, qty, veh, ipt, status="Approved"):
    _n[0] += 1
    db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, vehicle_type, submitted_by, status, ipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (f"F{_n[0]}", rid, month, disc, sect, qty, "t", "Small aggregate", veh, "tester", status, ipt))


# month 10: four approved lines (+ one pending that must not count)
_line("R1", 10, "earthworks", "WS1", 40000, ART, "IPT1")     # 1379.310 loads
_line("R1", 10, "structures", "WS2", 4400, R8, "IPT1")       # 220 loads — R1 is NOT baked for the rigid: unbaked line
_line("R1", 10, "substructure", "WS2", 1500, ART, "IPT1")    # 51.724 loads — a second artic line on R1 (ceil per line)
_line("R2", 10, "earthworks", "WS1", 14500, ART, "IPT2")     # 500 loads
_line("R3", 10, "earthworks", "WS1", 1000, ART, "IPT1")      # a route the map does not draw
_line("R2", 10, "earthworks", "WS3", 99999, ART, "IPT2", status="Pending")
# month 11: R1 lighter, R2 heavier; month 12: nothing
_line("R1", 11, "earthworks", "WS1", 20000, ART, "IPT1")
_line("R2", 11, "earthworks", "WS1", 29000, ART, "IPT2")     # 1000 loads

P10 = bulletin.month_payload(10)
P11 = bulletin.month_payload(11)
P12 = bulletin.month_payload(12)
ROUTES = bulletin.drawn_routes()
bulletin._stamp_caps(ROUTES)
TPV = {(l["route_id"], l["vehicle_type"]): l["trips_per_vehicle_day"] for l in P10["lines"] + P11["lines"]}
TPV1, TPV2 = TPV[("R1", ART)], TPV[("R2", ART)]


# =========================================================================== #
#  The route map export (14 Oct 2026, backlog item 2)                          #
# =========================================================================== #
import copy as _copy  # noqa: E402
import export  # noqa: E402
import basemap  # noqa: E402
import bulletin_doc  # noqa: E402
import route_map_export as rme  # noqa: E402
from portable import pdf_text, offline  # noqa: E402
offline(export)            # Mapbox is never called: the map is the schematic here (the browser check saw the basemap)

R10 = bulletin.rollup_payloads([P10], ROUTES, WD, acc=PLANNER)
BYR = {r["route_id"]: r for r in R10["by_route"]}
n0 = bulletin_doc.n0

# ---- 1. the figures are the roll-up's, per route ------------------------------------------------
S = rme.sheet(10, acc=PLANNER)
ok("⭐ every drawn route of the month, busiest first, with the bulletin roll-up's own figures (two-way a day, loads, tonnes)",
   [r["route_id"] for r in S["rows"]] == [r["route_id"] for r in R10["by_route"]] == ["R1", "R2"]
   and all(r["a_day_text"] == n0(BYR[r["route_id"]]["two_way_a_day"]) and r["loads_text"] == n0(BYR[r["route_id"]]["movements_in_month"])
           and r["tonnes_text"] == n0(BYR[r["route_id"]]["tonnes"]) + " t" for r in S["rows"]),
   str([(r["route_id"], r["a_day_text"], r["loads_text"], r["tonnes_text"]) for r in S["rows"]]))
ok("...hand: R1's loads in the month = 40,000 ÷ 29 + 4,400 ÷ 20 + 1,500 ÷ 29 (fractional, rounded once), its tonnes 45,900",
   S["rows"][0]["loads_text"] == n0(40000 / PAY_ART + 4400 / PAY_R8 + 1500 / PAY_ART) and S["rows"][0]["tonnes_text"] == "45,900 t",
   str(S["rows"][0]))
ok("🔴 approved lines only: R2's pending 99,999 t is not in it (D11: an approved route = the route + its Approved lines)",
   S["rows"][1]["tonnes_text"] == "14,500 t")
ok("...a route the map does not draw (R3, no stored road route) is named, not counted",
   S["not_drawn"] == ["R3"] and "R3" not in [r["route_id"] for r in S["rows"]])
ok("places, never an id; letters from the bulletin's rule (the busiest route's ends first); each place knows which end it is",
   S["rows"][0]["places"] == "Kelsey Quarry → Mill Compound" and S["rows"][0]["letters"] == "A → B"
   and S["rows"][1]["places"] == "Ridge Pit → Mill Compound" and S["rows"][1]["letters"] == "C → B"
   and [(p["name"], p["end"]) for p in S["places"]] == [("Kelsey Quarry", "origin"), ("Mill Compound", "dest"), ("Ridge Pit", "origin")])
# REVERSED 14 Oct 2026, evening (the user: "the only map export to be just the map"): the per-route table is gone, so the
# rows no longer carry the vehicles, the lorries needed, the planning flag or the closures date (nothing prints them)
ok("🔴 the rows carry no table fields any more: no vehicles, lorries needed, planning flag or closures date",
   not any(k in r for r in S["rows"] for k in ("vehicles_text", "lorries_text", "flag_text", "flag_over", "checked_text"))
   and "restrictions" not in read("backend/route_map_export.py") and not hasattr(rme, "_vehicle_word"))
db.execute("UPDATE routes SET restrictions_checked_at = ? WHERE id = ?", ("2026-10-12T08:30:00Z", "R1"))
ok("🔴 ...a stored closures check changes nothing on the map's rows",
   rme.sheet(10, acc=PLANNER)["rows"] == S["rows"])
db.execute("UPDATE routes SET restrictions_checked_at = NULL WHERE id = ?", ("R1",))
ok("the map draws each route in the public map's Volume colour for its two-way movements a day, quietest first",
   [m["route_id"] for m in S["map_routes"]] == ["R2", "R1"]
   and all(m["color"] == bulletin_doc.VOLUME_RAMP[bulletin_doc.volume_class(BYR[m["route_id"]]["two_way_a_day"])] for m in S["map_routes"]))
ok("the line in the panel says what was filtered: routes, team, month, approved lines only",
   S["filter_words"] == "2 routes · All teams · October 2026 · approved lines only", S["filter_words"])
# REVERSED 14 Oct 2026, evening: no Carbon Tool rows and no map-only switch — the export is only ever the map
import inspect  # noqa: E402
ok("🔴 sheet() takes no Carbon Tool or map-only option and the module has no Carbon Tool rows or scheme block left",
   "carbon_tool" not in inspect.signature(rme.sheet).parameters and "map_only" not in inspect.signature(rme.sheet).parameters
   and not hasattr(rme, "carbon_tool_rows") and not hasattr(rme, "SCHEME_FIELDS") and not hasattr(rme, "FLAG_WORDS")
   and "carbon_tool" not in S and "map_only" not in S and "scheme_fields" not in S)

# ---- 2. the filters, as the public map applies them ----------------------------------------------
ids = lambda s: [r["route_id"] for r in s["rows"]]
ok("⭐ team from the ROUTE (the map's rule): the slot id, a spaced id, or the team's NAME all pick R1",
   ids(rme.sheet(10, team="IPT1", acc=PLANNER)) == ["R1"] and ids(rme.sheet(10, team="IPT 1", acc=PLANNER)) == ["R1"]
   and ids(rme.sheet(10, team="North Team", acc=PLANNER)) == ["R1"] and ids(rme.sheet(10, team="Central Team", acc=PLANNER)) == ["R2"]
   and ids(rme.sheet(10, team="ALL", acc=PLANNER)) == ["R1", "R2"])
# the breaking case for "team from the ROUTE": a North Team line on Central's route R2 stays with R2's team (Central)
_line("R2", 10, "earthworks", "WS9", 2900, ART, "IPT1")
_xid = f"F{_n[0]}"
_tn, _tc = rme.sheet(10, team="IPT1", acc=PLANNER), rme.sheet(10, team="IPT2", acc=PLANNER)
ok("🔴 ...the breaking case: a North Team LINE on Central's ROUTE counts under Central (the route's team), as on the map",
   ids(_tn) == ["R1"] and ids(_tc) == ["R2"] and _tc["rows"][0]["tonnes_text"] == "17,400 t", str((ids(_tn), ids(_tc), _tc["rows"][0]["tonnes_text"] if _tc["rows"] else None)))
db.execute("DELETE FROM forecasts WHERE id = ?", (_xid,))
ok("...and the filter line names the team in words, never its id",
   rme.sheet(10, team="IPT1", acc=PLANNER)["filter_words"].startswith("1 route · North Team · "))
ok("origin and destination from the route, by name (the map's select values)",
   ids(rme.sheet(10, origin="Kelsey Quarry", acc=PLANNER)) == ["R1"] and ids(rme.sheet(10, dest="Mill Compound", acc=PLANNER)) == ["R1", "R2"]
   and ids(rme.sheet(10, origin="Nowhere", acc=PLANNER)) == [])
SD = rme.sheet(10, discipline="structures", acc=PLANNER)
# NARROWED 14 Oct 2026, evening: the vehicles are no longer in the rows (no table), so the check is the tonnes and loads
ok("⭐ discipline from the LINE: 'structures' keeps R1's rigid line only — 4,400 t, 4,400 ÷ 20 loads",
   ids(SD) == ["R1"] and SD["rows"][0]["tonnes_text"] == "4,400 t" and SD["rows"][0]["loads_text"] == n0(4400 / PAY_R8)
   and "structures" in SD["filter_words"])
ok("the Routes page's list: routes=R2 alone", ids(rme.sheet(10, route_ids=["R2"], acc=PLANNER)) == ["R2"])
ok("🔴 a team code gets its OWN team's routes, whatever it asks for", ids(rme.sheet(10, team="IPT2", acc=TEAM1)) == ["R1"]
   and ids(rme.sheet(10, acc=TEAM1)) == ["R1"])
ok("an empty month says so (no rows, empty)", rme.sheet(12, acc=PLANNER)["empty"] is True and rme.sheet(12, acc=PLANNER)["rows"] == [])

# ---- 3. the CLP plans: three plans, each at a STATED scale (14 Oct 2026, evening) ---------------------
# the CLOCS outline CLP template §2.2 / §4: regional smaller than 1:15,000; local 1:2,000-1:3,000; site 1:500-1:1,000
ok("⭐ the three plans and their scales are the CLP template's: regional 1:20,000 and smaller, local 1:2,000 to 1:3,000, site 1:500 to 1:1,000",
   list(rme.PLANS) == ["regional", "local", "site"] and min(rme.PLANS["regional"]["scales"]) > 15000
   and all(2000 <= n <= 3000 for n in rme.PLANS["local"]["scales"]) and all(500 <= n <= 1000 for n in rme.PLANS["site"]["scales"])
   and rme.PLANS["local"]["default"] == 2500 and rme.PLANS["site"]["default"] == 1000 and rme.PLANS["regional"]["default"] is None
   and list(rme.PLANS["regional"]["scales"]) == sorted(rme.PLANS["regional"]["scales"]))
ok("...the frame is A4 landscape less a 6 mm margin (285 × 198 mm) and the basemap image keeps its proportions",
   (rme.FRAME_W_MM, rme.FRAME_H_MM) == (285.0, 198.0) and rme.W_PX == basemap.MAX_PX
   and abs(rme.H_PX / rme.W_PX - rme.FRAME_H_MM / rme.FRAME_W_MM) < 1 / rme.W_PX)
# the zoom for a scale, worked out by hand: 1:2,500 printed 285 mm wide from 1,280 px = 0.5566 m a pixel at 52.5° N
_mpp = 2500 / 1000 * 285 / 1280
_z = math.log2(40075016.686 * math.cos(math.radians(52.5)) / (512 * _mpp))
ok("⭐ basemap.zoom_for_scale: by hand, 1:2,500 at 52.5° N on a 1,280 px image printed 285 mm wide is zoom "
   f"{_z:.2f}", basemap.zoom_for_scale(2500, 52.5, 285, 1280) == round(_z, 2), str(basemap.zoom_for_scale(2500, 52.5, 285, 1280)))
_errs = []
for _n_ in (500, 1000, 2000, 2500, 3000, 20000, 125000, 1000000):
    for _lat in (50.0, 52.5, 55.8):
        _vv = basemap.view_centred(-1.0, _lat, basemap.zoom_for_scale(_n_, _lat, 285, 1280), 1280, 889)
        _errs.append(abs(basemap.scale_denominator(_vv, 285) / _n_ - 1))
ok("⭐ ...the scale the view REALLY is at its centre is within 0.5 % of the stated one, at every plan scale and from Cornwall to Scotland "
   "(the zoom is rounded to two decimals: at most ±0.35 %)", max(_errs) < 0.005, f"{max(_errs):.4%}")

SR = rme.plan(rme.sheet(10, acc=PLANNER))["plan"]
_pts = bulletin_doc.map_points(S)
_res = int(round((rme.PANEL_W_MM + 4) / rme.FRAME_W_MM * rme.W_PX))
_xy = [basemap.project(SR["view"], *p) for p in _pts]
ok("⭐ REGIONAL, fitted: the largest scale of the series at which every route point fits left of the panel (with the padding) …",
   SR["kind"] == "regional" and SR["fitted"] is True and SR["denom"] in rme.PLANS["regional"]["scales"]
   and all(rme.PAD_PX - 1 <= x <= rme.W_PX - _res - rme.PAD_PX + 1 and rme.PAD_PX - 1 <= y <= rme.H_PX - rme.PAD_PX + 1 for x, y in _xy),
   f"{SR['denom']} {_xy}")
_prev = [n for n in rme.PLANS["regional"]["scales"] if n < SR["denom"]]
_vp = basemap.view_centred(SR["view"]["lon"], SR["view"]["lat"], basemap.zoom_for_scale(_prev[-1], SR["view"]["lat"], 285, 1280), 1280, rme.H_PX, _res) if _prev else None
_xyp = [basemap.project(_vp, *p) for p in _pts] if _vp else []
ok("🔴 ...and the next larger scale would NOT fit (so the fitted scale is the largest that does)",
   not _prev or not all(rme.PAD_PX <= x <= rme.W_PX - _res - rme.PAD_PX and rme.PAD_PX <= y <= rme.H_PX - rme.PAD_PX for x, y in _xyp),
   f"{_prev[-1:]} {_xyp}")
ok("...its stated scale reads 1:N and every place is in the frame", SR["scale_words"] == f"1:{SR['denom']:,}"
   and [p["name"] for p in SR["places"]] == ["Kelsey Quarry", "Mill Compound", "Ridge Pit"])
SR25 = rme.plan(rme.sheet(10, acc=PLANNER), "regional", 25000)["plan"]
ok("...a regional scale can be asked for (1:25,000 here, not fitted): the routes centred, whatever does not fit is cut off",
   SR25["denom"] == 25000 and SR25["fitted"] is False and abs(basemap.scale_denominator(SR25["view"], 285) / 25000 - 1) < 0.005)

SL = rme.plan(rme.sheet(10, acc=PLANNER), "local")["plan"]
_cx, _cy = basemap.project(SL["view"], -1.1, 52.6)
ok("⭐ LOCAL, as asked for nothing else: 1:2,500, centred on the busiest route's SITE end (Mill Compound) in the part of the map "
   "the panel leaves free", SL["denom"] == 2500 and SL["centre"] == "Mill Compound" and SL["scale_words"] == "1:2,500"
   and abs(_cx - (rme.W_PX - _res) / 2) < 2 and abs(_cy - rme.H_PX / 2) < 2, f"{SL['centre']} {_cx} {_cy}")
ok("...only the places inside the frame are listed (Kelsey Quarry and Ridge Pit are 13 km away at 1:2,500)",
   [p["name"] for p in SL["places"]] == ["Mill Compound"])
ok("...the places to centre on are the routes' ends, the sites first, names only",
   SL["centre_choices"] == ["Mill Compound", "Kelsey Quarry", "Ridge Pit"])
SK = rme.plan(rme.sheet(10, acc=PLANNER), "local", "1:2,000", at="kelsey quarry")["plan"]
ok("...a place by its name (any case) and a scale written 1:2,000 are taken", SK["centre"] == "Kelsey Quarry" and SK["denom"] == 2000
   and [p["name"] for p in SK["places"]] == ["Kelsey Quarry", "Ridge Pit"])
SS = rme.plan(rme.sheet(10, acc=PLANNER), "site", 500)["plan"]
ok("SITE: 1:500 and 1:1,000, centred the same way", SS["denom"] == 500 and SS["centre"] == "Mill Compound"
   and rme.plan(rme.sheet(10, acc=PLANNER), "site")["plan"]["denom"] == 1000)


def _err(*a, **k):
    try:
        rme.plan(rme.sheet(10, acc=PLANNER), *a, **k)
        return None
    except rme.PlanError as e:
        return str(e)


ok("🔴 a scale the plan does not offer, an unknown plan, a place not on these routes: refused in words",
   _err("site", 2500) == "the site plan is drawn at 1:500, 1:1,000" and _err("county") == "no such plan: choose regional, local, site"
   and _err("local", at="Nowhere") == "Nowhere is not at the end of a route on this map" and _err("local", "two") is not None)
SE = rme.plan(rme.sheet(12, acc=PLANNER), "local")["plan"]
ok("an empty month: no view, no scale, nothing to centre on (the PDF says so)", SE["view"] is None and SE["denom"] is None
   and SE["centre_choices"] == [] and rme.plan(rme.sheet(12, acc=PLANNER))["plan"]["view"] is None)
ok("the scale bar: 1, 2 or 5 × 10^k metres under 50 mm — 100 m at 1:2,500, 20 m at 1:500 — in words",
   basemap.bar_metres(SL["view"], 50 * 1280 / 285)[0] == 100 and basemap.bar_metres(SS["view"], 50 * 1280 / 285)[0] == 20
   and basemap.length_words(500) == "500 m" and basemap.length_words(2000) == "2 km" and basemap.length_words(2500) == "2.5 km")

# ---- 4. the PDF: just the map, one page ---------------------------------------------------------------
SP = rme.plan(rme.sheet(10, acc=PLANNER))
PDF = export.build_route_map_pdf(SP)
T = " ".join(pdf_text(PDF).split())
ok("⭐ ONE A4 LANDSCAPE page; the panel on the map: the plan, the scheme, its stated scale 'at A4', the filters",
   PDF[:5] == b"%PDF-" and PDF.count(b"/Type /Page\n") == 1 and b"/MediaBox [ 0 0 841.8898 595.2756 ]" in PDF
   and "Regional plan" in T and f"Scale {SR['scale_words']} at A4 (fitted to the routes)" in T
   and "2 routes · All teams · October 2026 · approved lines only" in T, T[:500])
ok("...the legend (the map's Volume steps) and every site in the frame by its letter",
   "Two-way movements a day" in T and all(g["label"] in T for g in bulletin_doc.volume_legend()) and "Sites" in T
   and all(p["name"] in T for p in SR["places"]))
ok("⭐ 'a planning document, not an approved CLP', approved lines only, the as-at date",
   "A planning document, not an approved CLP." in T and "Approved lines only." in T and "Approved plan as at" in T)
ok("offline (no basemap) the routes are still drawn to scale and it says so; no Mapbox credit is claimed for a map it did not draw",
   "No basemap could be had: the routes alone, still to scale." in T and "Mapbox" not in T and SP["plan"]["drawn"] == "routes only")
# REVERSED 14 Oct 2026, evening (the user: "just the map"; "Yes, remove them"): the table, the scheme's block and the
# Carbon Tool rows are gone from every export
ok("🔴 no route table, no scheme's block, no Carbon Tool rows: just the map",
   not any(h in T for h in ("PLANNING FLAG", "LOADS IN", "LORRIES", "CLOSURES", "To be completed by the scheme", "Working hours",
                            "Wheel wash", "Carbon Tool", "ONE-WAY LOADED")), T)
ok("🔴 no team id, no 'truck', no 'baked', no route id where a person reads it",
   not re.search(r"\bIPT ?\d\b", T) and not re.search(r"\btrucks?\b", T, re.I) and not re.search(r"\b(un)?baked?\b", T, re.I)
   and not re.search(r"\bR[123]\b", T))
TL_ = " ".join(pdf_text(export.build_route_map_pdf(rme.plan(rme.sheet(10, acc=PLANNER), "local"))).split())
ok("⭐ the local plan: its name, 'Scale 1:2,500 at A4', centred on the site, only that site in the key, a 100 m scale bar",
   "Local plan" in TL_ and "Scale 1:2,500 at A4" in TL_ and "(fitted" not in TL_ and "Centred on Mill Compound" in TL_
   and "B Mill Compound" in TL_ and "Kelsey Quarry" not in TL_ and "100 m" in TL_, TL_)
TS_ = " ".join(pdf_text(export.build_route_map_pdf(rme.plan(rme.sheet(10, acc=PLANNER), "site", 500))).split())
ok("...the site plan at 1:500: a 20 m scale bar", "Site plan" in TS_ and "Scale 1:500 at A4" in TS_ and "20 m" in TS_)
ok("...the north arrow and the scale bar are drawn on every plan with a view; the routes are clipped to the frame",
   "_north_arrow(c, x0 + pw - pad - 6, y0 + ph - pad - 26)" in read("backend/export.py")
   and "_plan_scale_bar(c, v, fw)" in read("backend/export.py") and "c.clipPath(clip, stroke=0, fill=0)" in read("backend/export.py"))
_rn = export._demo_notice
export._demo_notice = lambda: "Fictional demo scheme · the scheme and its plan are invented"
try:
    SDm = rme.plan(rme.sheet(10, acc=PLANNER), "local")
    TD = " ".join(pdf_text(export.build_route_map_pdf(SDm)).split())
finally:
    export._demo_notice = _rn
# NARROWED 14 Oct 2026, evening: no page bar any more (the page is the map); the tag ON the map says it
# NARROWED 15 Oct 2026 (the user: the bar reads DEMO · FICTIONAL SCHEME; the map tag "Demo - fictional scheme")
ok("⭐ on a demo tenant: the 'Demo - fictional scheme' tag on the map itself", SDm["map_demo_tag"] == bulletin_doc.DEMO_MAP_TAG
   and bulletin_doc.DEMO_MAP_TAG == "Demo - fictional scheme" and "Demo - fictional scheme" in TD)
_many = rme.plan(rme.sheet(10, acc=PLANNER))
_many["plan"] = dict(_many["plan"], places=[{"letter": bulletin_doc._letters(i), "name": f"Site {i}", "at": None} for i in range(20)])
ok("...the panel lists at most 16 sites, then '+N more sites'",
   export.ROUTE_MAP_PANEL_MAX_PLACES == 16 and "+4 more sites" in " ".join(pdf_text(export.build_route_map_pdf(_many)).split()))
TE = " ".join(pdf_text(export.build_route_map_pdf(rme.plan(rme.sheet(12, acc=PLANNER), "local"))).split())
ok("an empty month: one page that says so, no scale claimed", "No approved line on the chosen routes in this month." in TE
   and "Scale 1:" not in TE)

# ---- 5. the PNG: the same page, for a Word document -------------------------------------------------------
from PIL import Image  # noqa: E402
PNG = export.route_map_png(PDF)
IM = Image.open(io.BytesIO(PNG))
ok("⭐ PNG: the PDF page rasterised at 228 dpi, the margin cut: ≈ 2,560 px wide (the basemap's own pixels), the frame's shape",
   PNG[:8] == b"\x89PNG\r\n\x1a\n" and 2550 <= IM.size[0] <= 2570 and abs(IM.size[1] / IM.size[0] - 198 / 285) < 0.003
   and abs(IM.info.get("dpi", (0, 0))[0] - 228) < 0.5, f"{IM.size} {IM.info.get('dpi')}")
_px = IM.convert("RGB")
ok("...the frame's keyline is kept at the edge (the cut is inside the margin, not through the map)",
   sum(_px.getpixel((IM.size[0] // 2, 0))) < 600 and sum(_px.getpixel((0, IM.size[1] // 2))) < 600,
   f"{_px.getpixel((IM.size[0] // 2, 0))} {_px.getpixel((0, IM.size[1] // 2))}")
_real = sys.modules.get("pypdfium2")
sys.modules["pypdfium2"] = None
try:
    try:
        export.route_map_png(PDF)
        _msg = None
    except RuntimeError as e:
        _msg = str(e)
finally:
    if _real is not None:
        sys.modules["pypdfium2"] = _real
    else:
        sys.modules.pop("pypdfium2", None)
ok("🔴 without pypdfium2 the PNG is refused in words (the endpoint answers 503), never a crash at start-up",
   _msg == "the PNG needs pypdfium2, which is not installed here (backend/requirements.txt)"
   and "pypdfium2==" in read("backend/requirements.txt") and "\nimport pypdfium2" not in read("backend/export.py"))

# ---- 6. the basemap leaves the panel's strip free ---------------------------------------------
_pts = [(-1.20, 52.40), (-0.60, 52.80), (-0.90, 52.55)]
_v0 = basemap.view(_pts, 1200, 800, 40)
_v1 = basemap.view(_pts, 1200, 800, 40, reserve_right_px=300)
_xs0 = [basemap.project(_v0, *p)[0] for p in _pts]
_xs1 = [basemap.project(_v1, *p)[0] for p in _pts]
ok("⭐ basemap.view(reserve_right_px): every point is framed left of the reserved strip (with the padding), and without it the frame is centred as before",
   max(_xs1) <= 1200 - 300 - 40 + 1 and min(_xs1) >= 40 - 1 and abs((min(_xs0) + max(_xs0)) / 2 - 600) < 1
   and _v1["zoom"] <= _v0["zoom"], f"{_xs0} {_xs1} {_v0['zoom']} {_v1['zoom']}")
# NARROWED 14 Oct 2026, evening: the map-only flowable is gone; every plan keeps the panel's width (+4 mm) free
ok("...every plan reserves the panel's width (+4 mm): the regional fit and the local / site centring both",
   "reserve = int(round((PANEL_W_MM + 4) / FRAME_W_MM * W_PX))" in read("backend/route_map_export.py")
   and read("backend/route_map_export.py").count(", reserve)") == 3 and "class _RouteMap" not in read("backend/export.py"))

# ---- 7. the endpoints ----------------------------------------------------------------------------
_mn = read("backend/main.py")
_ep = _mn[_mn.index("def _route_map_plan("):_mn.index('@app.get("/api/public/route-alternatives")')]
ok("⭐ STAFF ONLY: a valid code or the staff cookie (_staff_request), else 401 — the map password's cookie is not staff — in the one "
   "read the PDF, the PNG and the card's places all go through",
   "if not _staff_request(request):" in _ep and 'raise HTTPException(401, "sign in — the route map export is for staff")' in _ep
   and _ep.count("S = _route_map_plan(request, month, origin, dest, discipline, team, routes,") == 3)
ok("the read passes the map's filters and the Routes page's list; a plan it cannot draw is a 422 with the sentence",
   "route_ids=ids, team=team, acc=access.current(), origin=origin, dest=dest," in _ep
   and "except route_map_export.PlanError as e:\n        raise HTTPException(422, str(e))" in _ep
   and "carbon_tool" not in _ep and "map_only" not in _ep)
ok("both files are named by month, plan and scale (route-map-2026-10-local-1-2500.pdf), never cached",
   'return f"route-map-{y}-{m:02d}-{PL[\'kind\']}{tail}.{ext}"' in _ep and _ep.count('"Cache-Control": "no-store"') == 2
   and 'media_type="image/png"' in _ep and "export.route_map_png(export.build_route_map_pdf(S))" in _ep)
ok("one read, nothing stored: the module writes nothing", "db.execute" not in read("backend/route_map_export.py")
   and "INSERT" not in read("backend/route_map_export.py") and "UPDATE" not in read("backend/route_map_export.py"))

# =========================================================================== #
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
