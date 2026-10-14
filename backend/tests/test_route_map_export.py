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
ok("⭐ every drawn route of the month, busiest first, with the bulletin roll-up's own figures (two-way a day, loads, tonnes, lorries)",
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
ok("places, never an id; letters from the bulletin's rule (the busiest route's ends first)",
   S["rows"][0]["places"] == "Kelsey Quarry → Mill Compound" and S["rows"][0]["letters"] == "A → B"
   and S["rows"][1]["places"] == "Ridge Pit → Mill Compound" and S["rows"][1]["letters"] == "C → B"
   and [p["name"] for p in S["places"]] == ["Kelsey Quarry", "Mill Compound", "Ridge Pit"])
ok("vehicles as people read them, each once per route",
   S["rows"][0]["vehicles_text"] == f"{rme._vehicle_word(ART)}, {rme._vehicle_word(R8)}" and S["rows"][1]["vehicles_text"] == rme._vehicle_word(ART))
ok("the planning flag: the typed figure, 'above it' exactly when the route's two-way a day is over it; 'none set' with none",
   S["rows"][0]["flag_text"] == ("60 a day: above it" if BYR["R1"]["two_way_a_day"] > 60 else "60 a day")
   and S["rows"][0]["flag_over"] == (BYR["R1"]["two_way_a_day"] > 60) and S["rows"][1]["flag_text"] == "none set")
ok("closures: 'not checked' while no check is stored", all(r["checked_text"] == "not checked" for r in S["rows"]))
db.execute("UPDATE routes SET restrictions_checked_at = ? WHERE id = ?", ("2026-10-12T08:30:00Z", "R1"))
ok("...and the stored check's date once there is one", rme.sheet(10, acc=PLANNER)["rows"][0]["checked_text"] == "12 Oct 2026")
db.execute("UPDATE routes SET restrictions_checked_at = NULL WHERE id = ?", ("R1",))
ok("the map draws each route in the public map's Volume colour for its two-way movements a day, quietest first",
   [m["route_id"] for m in S["map_routes"]] == ["R2", "R1"]
   and all(m["color"] == bulletin_doc.VOLUME_RAMP[bulletin_doc.volume_class(BYR[m["route_id"]]["two_way_a_day"])] for m in S["map_routes"]))
ok("the line under the title says what was filtered: routes, team, month, approved lines only",
   S["filter_words"] == "2 routes · All teams · October 2026 · approved lines only", S["filter_words"])
ok("no Carbon Tool rows unless asked, and the full layout unless map only is asked", "carbon_tool" not in S and S["map_only"] is False)

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
ok("⭐ discipline from the LINE: 'structures' keeps R1's rigid line only — 4,400 t, 4,400 ÷ 20 loads",
   ids(SD) == ["R1"] and SD["rows"][0]["tonnes_text"] == "4,400 t" and SD["rows"][0]["loads_text"] == n0(4400 / PAY_R8)
   and SD["rows"][0]["vehicles_text"] == rme._vehicle_word(R8) and "structures" in SD["filter_words"])
ok("the Routes page's list: routes=R2 alone", ids(rme.sheet(10, route_ids=["R2"], acc=PLANNER)) == ["R2"])
ok("🔴 a team code gets its OWN team's routes, whatever it asks for", ids(rme.sheet(10, team="IPT2", acc=TEAM1)) == ["R1"]
   and ids(rme.sheet(10, acc=TEAM1)) == ["R1"])
ok("an empty month says so (no rows, empty)", rme.sheet(12, acc=PLANNER)["empty"] is True and rme.sheet(12, acc=PLANNER)["rows"] == [])

# ---- 3. the National Highways Carbon Tool rows (H3), only when asked ---------------------------------
SC = rme.sheet(10, acc=PLANNER, carbon_tool=True)
CT = SC["carbon_tool"]["rows"]
r1a = [r for r in CT if r["route_id"] == "R1" and r["vehicle"] == rme._vehicle_word(ART)]
r1r = [r for r in CT if r["route_id"] == "R1" and r["vehicle"] == rme._vehicle_word(R8)]
ok("⭐ one row per Carbon Tool sheet, material, route and VEHICLE: R1's artic lines 41,500 t at the artic's 30 km loaded, one way",
   len(r1a) == 1 and r1a[0]["tonnes"] == 41500.0 and r1a[0]["one_way_km"] == 30.0 and r1a[0]["material"] == "Small aggregate",
   str(CT))
ok("...R1's rigid line on its own row, with no km (its route is not worked out for the rigid), never the artic's",
   len(r1r) == 1 and r1r[0]["tonnes"] == 4400.0 and r1r[0]["one_way_km"] is None)
ok("...R2 14,500 t at 10 km; R3 (not drawn) has no row; every row names its Carbon Tool sheet",
   [(r["tonnes"], r["one_way_km"]) for r in CT if r["route_id"] == "R2"] == [(14500.0, 10.0)]
   and not [r for r in CT if r["route_id"] == "R3"] and all(r["sheet"] and r["sheet"] != "—" for r in CT), str(CT))
ok("...the discipline filter reaches the Carbon Tool rows too",
   [(r["route_id"], r["tonnes"]) for r in rme.sheet(10, discipline="structures", acc=PLANNER, carbon_tool=True)["carbon_tool"]["rows"]] == [("R1", 4400.0)])

# ---- 4. the PDF: the full export -----------------------------------------------------------------
PDF = export.build_route_map_pdf(S)
T = " ".join(pdf_text(PDF).split())
ok("⭐ A4 LANDSCAPE, the map then the table: title, filter line, the eight columns, both routes by their places",
   PDF[:5] == b"%PDF-" and b"/MediaBox [ 0 0 841.8898 595.2756 ]" in PDF and "Route map · October 2026" in T
   and "2 routes · All teams · October 2026 · approved lines only" in T
   # the two-line headings come out of the text one line at a time ("TWO-WAY … A DAY")
   and all(h in T for h in ("ROUTE", "TWO-WAY", "A DAY", "LOADS IN", "THE MONTH", "TONNES", "VEHICLES", "LORRIES", "NEEDED", "PLANNING FLAG", "CLOSURES", "CHECKED"))
   and "Kelsey Quarry to Mill Compound" in T and "Ridge Pit to Mill Compound" in T, T[:400])
ok("...the figures printed are the view model's", S["rows"][0]["loads_text"] in T and "45,900 t" in T and "14,500 t" in T)
ok("⭐ 'a planning document, not an approved CLP' and the flag is a flag, never a block",
   "a planning document, not an approved CLP" in T and "A planning flag, never a block" in T)
ok("⭐ the fixed block the scheme fills in: working hours, wheel wash, holding area, contacts — Wayscope does not hold them",
   "To be completed by the scheme" in T and all(k in T for k in ("Working hours", "Wheel wash", "Holding area", "Contacts"))
   and "Wayscope does not hold these" in T)
ok("the legend (the map's Volume steps) and the site key under the map",
   "Two-way movements a day:" in T and all(g["label"] in T for g in bulletin_doc.volume_legend()) and "A Kelsey Quarry" in T)
ok("offline the map is the schematic and says so (the browser check saw the basemap and its credit)",
   "Schematic from the stored road routes, not to scale." in T)
ok("🔴 no Carbon Tool block unless asked", "Carbon Tool" not in T)
ok("🔴 no team id, no 'truck', no 'baked', no route id where a person reads the route",
   not re.search(r"\bIPT ?\d\b", T) and not re.search(r"\btrucks?\b", T, re.I) and not re.search(r"\b(un)?baked?\b", T, re.I)
   and not re.search(r"\bR[123]\b", T))
PDFC = export.build_route_map_pdf(SC)
TC = " ".join(pdf_text(PDFC).split())
ok("⭐ with the option: the National Highways Carbon Tool rows — sheet, material, from / to, tonnes, one-way loaded km, vehicle",
   "National Highways Carbon Tool: transport inputs for the month" in TC and "ONE-WAY LOADED" in TC and "FROM / TO" in TC
   and "41,500" in TC and "30.0" in TC and "Wayscope's own carbon figures are not Carbon Tool figures" in TC)
_rn = export._demo_notice
export._demo_notice = lambda: "Fictional demo scheme · the scheme and its plan are invented"
try:
    SDm = rme.sheet(10, acc=PLANNER)
    TD = " ".join(pdf_text(export.build_route_map_pdf(SDm)).split())
    TDm = " ".join(pdf_text(export.build_route_map_pdf(rme.sheet(10, acc=PLANNER, map_only=True))).split())
finally:
    export._demo_notice = _rn
ok("⭐ on a demo tenant: the demo bar on the page AND the 'Fictional demo scheme' tag on the map, in both layouts",
   SDm["map_demo_tag"] == bulletin_doc.DEMO_MAP_TAG and "DEMO" in TD and "the scheme and its plan are invented" in TD
   and TD.count("Fictional demo scheme") >= 2 and "DEMO" in TDm and TDm.count("Fictional demo scheme") >= 2)
_big = _copy.deepcopy(S)
_big["rows"] = [dict(S["rows"][i % 2], places=f"Site {i} → Yard {i}") for i in range(40)]
PB = export.build_route_map_pdf(_big)
TB = pdf_text(PB)
_np = PB.count(b"/Type /Page\n")
ok("forty routes run on to more pages with the header row repeated (the table is not one block that cannot split)",
   _np >= 2 and _np - 1 <= TB.count("PLANNING FLAG") <= _np, f"{_np} pages, {TB.count('PLANNING FLAG')} headers")

# ---- 5. the PDF: map only, the legend inside the map ---------------------------------------------
SM = rme.sheet(10, acc=PLANNER, map_only=True, carbon_tool=True)
PM = export.build_route_map_pdf(SM)
TM = " ".join(pdf_text(PM).split())
ok("⭐ MAP ONLY: one A4 landscape page, the legend drawn on the map (the Volume steps and every site by its letter)",
   PM.count(b"/Type /Page\n") == 1 and b"/MediaBox [ 0 0 841.8898 595.2756 ]" in PM and "Two-way movements a day" in TM
   and all(g["label"] in TM for g in bulletin_doc.volume_legend()) and "Sites" in TM
   and all(p["name"] in TM for p in SM["places"]), TM[:500])
ok("...no table, no scheme block, no Carbon Tool rows (map only wins over the option)",
   "PLANNING FLAG" not in TM and "To be completed by the scheme" not in TM and "Carbon Tool" not in TM
   and "figures by route are in the full export" in TM)
ok("...the inset key lists at most 16 sites, then '+N more sites'",
   export.ROUTE_MAP_INSET_MAX_PLACES == 16 and "+4 more sites" in " ".join(pdf_text(export.build_route_map_pdf(
       dict(SM, places=[{"letter": bulletin_doc._letters(i), "name": f"Site {i}", "at": None} for i in range(20)]))).split()))

# ---- 6. the basemap leaves the legend's strip free ---------------------------------------------
_pts = [(-1.20, 52.40), (-0.60, 52.80), (-0.90, 52.55)]
_v0 = basemap.view(_pts, 1200, 800, 40)
_v1 = basemap.view(_pts, 1200, 800, 40, reserve_right_px=300)
_xs0 = [basemap.project(_v0, *p)[0] for p in _pts]
_xs1 = [basemap.project(_v1, *p)[0] for p in _pts]
ok("⭐ basemap.view(reserve_right_px): every point is framed left of the reserved strip (with the padding), and without it the frame is centred as before",
   max(_xs1) <= 1200 - 300 - 40 + 1 and min(_xs1) >= 40 - 1 and abs((min(_xs0) + max(_xs0)) / 2 - 600) < 1
   and _v1["zoom"] <= _v0["zoom"], f"{_xs0} {_xs1} {_v0['zoom']} {_v1['zoom']}")
ok("...the export's map reserves the legend's width (+12 pt) only on the map-only page",
   "self.reserve_right = (ROUTE_MAP_INSET_W + 12) if inset else 0" in read("backend/export.py")
   and 'reserve_right_pt=getattr(self, "reserve_right", 0))' in read("backend/export.py"))

# ---- 7. the endpoint ----------------------------------------------------------------------------
_mn = read("backend/main.py")
_ep = _mn[_mn.index('@app.get("/api/routes/map-export.pdf")'):_mn.index('@app.get("/api/public/route-alternatives")')]
ok("⭐ STAFF ONLY: a valid code or the staff cookie (_staff_request), else 401 — the map password's cookie is not staff",
   "if not _staff_request(request):" in _ep and 'raise HTTPException(401, "sign in — the route map export is for staff")' in _ep)
ok("the endpoint passes the map's filters, the Routes page's list and the two options; map only drops the Carbon Tool rows",
   "route_ids=ids, team=team, acc=access.current(), origin=origin, dest=dest," in _ep
   and "carbon_tool=bool(carbon_tool) and not map_only" in _ep and "map_only=bool(map_only)" in _ep
   and 'filename="route-map-{y}-{m:02d}{"-map" if map_only else ""}.pdf"' in _ep and '"Cache-Control": "no-store"' in _ep)
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
