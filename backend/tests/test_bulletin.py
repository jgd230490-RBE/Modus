"""
The monthly bulletin's server half (B4, 12 Oct 2026) — backend/bulletin.py.

WHAT IS ASSERTED
----------------
  * the month roll-up equals a HAND computation on a fixture of three drawn routes, five
    lines (one unbaked for its vehicle, one on a route the map does not draw) and one cap;
  * each of the public map bar's eleven rules (map/index.html calculateKPIs) by a case
    that BREAKS it: ceil per line (≠ ceil once over the total), fractional loads summed
    (≠ Σ ceil per line), the unbaked line counted in the movements and named in the fleet
    (never zeroed), the busiest month's fleet over a window (≠ the mean), the average over
    months WITH volume (≠ the window length), the material card hidden in a vehicles unit,
    the busiest five by two-way movements a day, the breakdown's team rows named by the
    tenant (never an id) and limited to a team code's own team, the undrawn route excluded
    and named;
  * the harness comparison the review asks for: a SECOND, independently written
    computation of calculateKPIs's rules over the same payload, equal to rollup_payloads;
  * the literal-22 ban on the module (working days come from main._working_days only);
  * conditions of the month: an ended closure is excluded, a stored hit overlapping the
    month is included, an undated hit always counts, "never checked" where no check is
    stored, a stockpile over at the END of the month only, a seasonal window for the
    calendar month and vehicle, a typed cap exceeded as a "planning flag";
  * the endpoint body: 401 without a code, the page's keys with the planner code, the
    team code's per-team rows.
  * (C4, 12 Oct 2026) the bulletin as people read it: the PDF's text carries the four headline
    figures equal to the hand computation, "fictional demo scheme" on every page, the map's
    kpi-note sentence verbatim, the planning flag, the works of the month, plan against plan,
    the carbon stamp, placeholders for the typed fields; the HTML page the same figures; no
    team id or name; the banned-word scan with the "Truck mixer" exception; the literal-22 ban
    on the composition; ONE page frame in export.py; the static map's URL; the endpoints' staff
    rule (a code or the STAFF cookie, never the map cookie).

WHAT THIS DOES NOT PROVE
------------------------
HERE is never called: the geometry rows are typed in, so every cycle time is what
network.route_analysis makes of typed distances. The HTTP layer is stubbed (http_smoke.py
drives the real one and the middleware). NARROWED 12 Oct 2026 (C4): the PDF and the HTML page now
exist and are asserted in section 8 (pdf_text of the PDF, the HTML's own markup); Mapbox is never
called (portable.offline, and a capturing stub for the static-image URL), so the Mapbox image itself
and how either document LOOKS are not checked here.

Run:  python3 backend/tests/test_bulletin.py
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

TMP = tempfile.mkdtemp(prefix="rbe_bulletin_")
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
# 17 Oct 2026: the disciplines carry LABELS unlike their ids (as the demo's "superstructure" reads "Pavement"), so a table
# that prints the id is caught. "structures" has no row: an id the tenant does not define falls back to itself.
tenant_package.import_rows("disciplines", [
    {"id": "earthworks", "label": "Bulk earthworks", "sort_order": 10, "in_scope": True, "scope_note": None, "active": True},
    {"id": "substructure", "label": "Foundations", "sort_order": 20, "in_scope": False, "scope_note": None, "active": True}])


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
#  1. The inputs are the map's                                                 #
# =========================================================================== #
ok("the payload is /api/public/month-kpis as a function: month 10, five approved lines, working days stated",
   P10["month"] == 10 and len(P10["lines"]) == 5 and P10["working_days"] == WD, str(P10)[:200])
ok("the drawn routes are the map's: R1 and R2 (baked for the artic), never R3 (no geometry)",
   set(ROUTES) == {"R1", "R2"} and ROUTES["R1"]["origin"] == "Kelsey Quarry" and ROUTES["R1"]["dest"] == "Mill Compound",
   str(sorted(ROUTES)))
ok("the typed cap is stamped on the drawn route's properties", ROUTES["R1"]["max_vehicles_per_day"] == 60
   and ROUTES["R2"]["max_vehicles_per_day"] is None)
ok("the rigid line on R1 has no cycle (unbaked for its vehicle) and no carbon; the artic lines have both",
   TPV[("R1", R8)] is None and TPV1 and TPV1 > 0 and TPV2 and TPV2 > 0
   and [l["co2_t"] for l in P10["lines"] if l["vehicle_type"] == R8] == [None], str(TPV))
ok("working days come from main._working_days", near(bulletin.working_days(FACTORS), WD) and WD > 0)

# =========================================================================== #
#  2. The hand computation, month 10                                           #
# =========================================================================== #
R = bulletin.rollup_payloads([P10], ROUTES, WD, acc=PLANNER)
H = R["headline"]
loads_r1_a, loads_r1_b, loads_r1_c, loads_r2 = 40000 / PAY_ART, 4400 / PAY_R8, 1500 / PAY_ART, 14500 / PAY_ART
LOADS = loads_r1_a + loads_r1_b + loads_r1_c + loads_r2              # 2151.034 at 29 t / 20 t
ok("hand: payloads are the seed's 29 t artic and 20 t rigid, so the month's loads are 2,151.034",
   PAY_ART == 29.0 and PAY_R8 == 20.0 and near(LOADS, 2151.034, 1e-3), f"{PAY_ART} {PAY_R8} {LOADS}")
ok("⭐ rule 2 (fractional sum): two-way movements a day = 2,151.034 ÷ working days — R3's 1,000 t is NOT in it",
   near(H["two_way_a_day"], LOADS / WD, 1e-3) and near(H["movements_in_month"], LOADS, 1e-3), str(H))
WRONG_CEILED = (math.ceil(loads_r1_a) + math.ceil(loads_r1_b) + math.ceil(loads_r1_c) + math.ceil(loads_r2)) / WD
ok("…and it is NOT Σ ceil(loads) ÷ working days (the breaking case)",
   not near(H["two_way_a_day"], WRONG_CEILED, 1e-3) and WRONG_CEILED > H["two_way_a_day"], f"{H['two_way_a_day']} vs {WRONG_CEILED}")
ok("headline: working days stated beside the month's movements, routes in use 2, tonnes 60,400 (R3 excluded)",
   H["working_days"] == WD and H["routes_in_use"] == 2 and near(H["tonnes"], 40000 + 4400 + 1500 + 14500, 1e-3), str(H))
FLEET = math.ceil((loads_r1_a / WD) / TPV1) + math.ceil((loads_r1_c / WD) / TPV1) + math.ceil((loads_r2 / WD) / TPV2)
ok("⭐ rule 3 (ceil per line): vehicles = Σ per line ceil(loads ÷ wd ÷ trips a vehicle can do on that route)",
   R["vehicles"]["fleet"] == FLEET, f"{R['vehicles']['fleet']} vs {FLEET} (tpv {TPV1} {TPV2})")
WRONG_ONCE = math.ceil((loads_r1_a + loads_r1_c) / WD / TPV1) + math.ceil(loads_r2 / WD / TPV2)
ok("…and NOT ceil once over R1's two artic lines together (the breaking case: the two lines' fractions)",
   FLEET != WRONG_ONCE and R["vehicles"]["fleet"] != WRONG_ONCE, f"{FLEET} vs {WRONG_ONCE}")
# NARROWED 12 Oct 2026 (the review and fix pass): plain words for a council reader — "no stored road route", not the team's "unbaked"
ok("⭐ rule 4 (unbaked named, not zeroed): the rigid line is in the movements, out of the fleet, and the label says so",
   R["vehicles"]["excludes_unbaked_lines"] == 1
   and R["vehicles"]["label"] == "Vehicles needed (excludes 1 line not routed yet for the vehicle)"   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): "not routed yet", as the map
   and "unbaked" not in R["vehicles"]["label"]
   and R["vehicles"]["not_baked"] is False and near(H["two_way_a_day"] - (LOADS - loads_r1_b) / WD, loads_r1_b / WD, 1e-3),
   str(R["vehicles"]))
R_NO_RIGID = bulletin.rollup_payloads([dict(P10, lines=[l for l in P10["lines"] if l["vehicle_type"] != R8])], ROUTES, WD)
ok("…the breaking case: without that line the movements drop by exactly its 220 loads a day and the label clears",
   near(R_NO_RIGID["headline"]["two_way_a_day"], (LOADS - loads_r1_b) / WD, 1e-3)
   and R_NO_RIGID["vehicles"]["label"] == "Vehicles needed" and R_NO_RIGID["vehicles"]["fleet"] == FLEET)
ok("⭐ rule 1 (undrawn route): R3's line is excluded AND named — 1 line, route R3 — never counted as zero",
   R["routes_not_drawn"] == {"lines": 1, "routes": ["R3"], "note": R["routes_not_drawn"]["note"]}
   and R["routes_not_drawn"]["note"] and "not counted as zero" in R["routes_not_drawn"]["note"]
   and R["lines_counted"] == 4, str(R["routes_not_drawn"]))
R_WITH_R3 = bulletin.rollup_payloads([P10], dict(ROUTES, R3={"route_id": "R3", "origin": "Kelsey Quarry", "dest": "Far Yard", "ipt": "IPT1"}), WD)
ok("…the breaking case: were R3 drawn, its 1,000 t would join the figures (routes 3, tonnes +1,000)",
   R_WITH_R3["headline"]["routes_in_use"] == 3 and near(R_WITH_R3["headline"]["tonnes"], H["tonnes"] + 1000, 1e-3)
   and R_WITH_R3["routes_not_drawn"]["lines"] == 0)

# rule 7: carbon — the costlines figure per line, unbaked named
CO2 = sum(l["co2_t"] for l in P10["lines"] if l["co2_t"] is not None and l["route_id"] in ROUTES)
ok("⭐ rule 7 (carbon): CO₂e a day = Σ co2_t ÷ wd, the month's total, 1 unbaked line named, the Carbon page's stamp",
   near(R["carbon"]["co2_t_a_day"], CO2 / WD, 1e-3) and near(R["carbon"]["co2_t_in_month"], CO2, 1e-3)
   and R["carbon"]["excludes_unbaked_lines"] == 1
   and R["carbon"]["label_day"] == "CO₂e a day (excl. 1 line not routed yet)"  # NARROWED 12 Oct 2026 (wording); NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): "not routed yet"
   and R["carbon"]["stamp"] == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"
   and CO2 > 0, str(R["carbon"]))
ok("…co2 to date follows the payload's programme-to-date list over the drawn routes",
   near(R["carbon"]["co2_t_to_date"], sum(c["co2_t"] for c in P10["co2_to_date"] if c["route_id"] in ROUTES), 1e-3))
ok("…with three of four counted lines carrying carbon the block is a figure: not_baked False, no error",
   R["carbon"]["not_baked"] is False and R["carbon"]["error"] is None)
# 12 Oct 2026 (the tests-and-regressions review): a month where NO counted line carries carbon is not
# "0.0 t (excl. 4 unbaked)" — the figures are None and the block says not_baked, as the fleet block does
R_NOCO2 = bulletin.rollup_payloads([dict(P10, lines=[dict(l, co2_t=None) for l in P10["lines"]])], ROUTES, WD)
ok("⭐ when no counted line carries carbon the figures read None and not_baked True — a sum of zero baked lines is "
   "not 0.0 t; the volumes are untouched",
   R_NOCO2["carbon"]["co2_t_a_day"] is None and R_NOCO2["carbon"]["co2_t_in_month"] is None
   and R_NOCO2["carbon"]["not_baked"] is True and R_NOCO2["carbon"]["excludes_unbaked_lines"] == 4
   and R_NOCO2["carbon"]["label_day"] == "CO₂e a day (excl. 4 lines not routed yet)" and R_NOCO2["headline"] == H   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): "not routed yet"
   and R_NOCO2["vehicles"] == R["vehicles"], str(R_NOCO2["carbon"]))
_real_cl = costlines.lines


def _boom(*a, **k):
    raise RuntimeError("fixture: the costlines read failed")


costlines.lines = _boom
try:
    P10_ERR = bulletin.month_payload(10)
finally:
    costlines.lines = _real_cl
R_ERR = bulletin.rollup_payloads([P10_ERR], ROUTES, WD)
ok("⭐ …and when the costlines read fails, the payload's co2_error rides on the carbon block as `error`, the figures None, "
   "the headline and fleet the same (volumes are not carbon's hostage)",
   # NARROWED 12 Oct 2026 (the review and fix pass): co2_error is a fixed sentence naming the class; the message is
   # logged server-side, never served on a /api/public/ feed (an exception's text can carry SQL or internal keys)
   P10_ERR.get("co2_error") == "The carbon figures could not be read (RuntimeError)."
   and "fixture" not in P10_ERR.get("co2_error", "")
   and R_ERR["carbon"]["error"] == P10_ERR["co2_error"] and R_ERR["carbon"]["not_baked"] is True
   and R_ERR["carbon"]["co2_t_in_month"] is None and R_ERR["carbon"]["co2_t_a_day"] is None
   and R_ERR["carbon"]["excludes_unbaked_lines"] == 4 and R_ERR["headline"] == H and R_ERR["vehicles"] == R["vehicles"],
   f"{P10_ERR.get('co2_error')} {R_ERR['carbon']}")
# 12 Oct 2026 (the review and fix pass): the to-date figure follows the same rule — it used to print 0.0 t beside
# not_baked True and the error, because a failed read empties co2_to_date and an empty sum is 0.0
ok("⭐ …and CO₂e to date is None too when the read failed (never 0.0 t beside the error)",
   R_ERR["carbon"]["co2_t_to_date"] is None, str(R_ERR["carbon"]))
R_NOTD = bulletin.rollup_payloads([dict(P10, lines=[dict(l, co2_t=None) for l in P10["lines"]], co2_to_date=[],
                                        co2_to_date_unbaked_lines=6)], ROUTES, WD)
ok("⭐ …and when nothing to date carries carbon (no row, 6 line-months without a stored route) to date is None, not 0.0 t",
   R_NOTD["carbon"]["co2_t_to_date"] is None and R_NOTD["carbon"]["to_date_excludes_unbaked_lines"] == 6, str(R_NOTD["carbon"]))
ok("…while a programme with rows to date keeps its figure (the happy month above)", R["carbon"]["co2_t_to_date"] is not None
   and R_NOCO2["carbon"]["co2_t_to_date"] is not None)
ok("…the read is restored: the next payload carries carbon and no co2_error again",
   costlines.lines is _real_cl and "co2_error" not in bulletin.month_payload(10)
   and bulletin.rollup_payloads([bulletin.month_payload(10)], ROUTES, WD)["carbon"]["error"] is None)

# rule 8: the material card
# qty_unit in a vehicles unit is rounded to WHOLE loads per line by the payload (round_for_unit), so the
# hidden card's figure sits within half a load per line of the fractional two-way figure
ok("⭐ rule 8 (material card): hidden in a vehicles unit — loads a day IS the two-way figure (to the payload's per-line rounding)",
   R["material"]["shown"] is False and R["material"]["unit"] == "vehicles"
   and abs(R["material"]["per_day"] - H["two_way_a_day"]) <= 2.0 / WD + 1e-9, f"{R['material']} vs {H['two_way_a_day']}")
P10_T = bulletin.month_payload(10, unit="t")
R_T = bulletin.rollup_payloads([P10_T], ROUTES, WD, unit="t")
ok("…shown for tonnes, where it is a different number (tonnes a day), and the two-way figure is unchanged",
   R_T["material"]["shown"] is True and near(R_T["material"]["per_day"], H["tonnes"] / WD, 1e-2)
   and near(R_T["headline"]["two_way_a_day"], H["two_way_a_day"], 1e-3), str(R_T["material"]))

# rule 9: the busiest routes with their four figures and the cap wording
B = R["busiest_routes"]
ok("⭐ rule 9 (busiest routes): ranked by two-way a day, R1 then R2, labelled origin → destination",
   [b["route_id"] for b in B] == ["R1", "R2"] and B[0]["label"] == "Kelsey Quarry → Mill Compound"
   and B[1]["label"] == "Ridge Pit → Mill Compound", str(B)[:300])
ok("…R1's four figures: two-way a day, in the month, vehicles (ceil per line, excl. the rigid), co2",
   near(B[0]["two_way_a_day"], (loads_r1_a + loads_r1_b + loads_r1_c) / WD, 1e-3)
   and near(B[0]["movements_in_month"], loads_r1_a + loads_r1_b + loads_r1_c, 1e-3)
   and B[0]["vehicles"] == math.ceil((loads_r1_a / WD) / TPV1) + math.ceil((loads_r1_c / WD) / TPV1)
   and B[0]["vehicles_excludes_unbaked_lines"] == 1
   and near(B[0]["co2_t"], sum(l["co2_t"] for l in P10["lines"] if l["route_id"] == "R1" and l["co2_t"] is not None), 1e-3),
   str(B[0]))
ok("…the typed cap reads \"planning flag\" on R1 (60) and \"no planning cap typed\" on R2",
   B[0]["cap"] == 60 and B[0]["cap_wording"] == "planning flag" and B[1]["cap"] is None
   and B[1]["cap_wording"] == "no planning cap typed")
# the top-five rule, with seven synthetic routes through the pure function
_seven_lines = [{"route_id": f"S{i}", "discipline": "earthworks", "section_id": "", "vehicle_loads": 100.0 * i,
                 "qty_unit": 0, "qty_t": 0, "co2_t": 0.1, "trips_per_vehicle_day": 5, "payload_fallback": None,
                 "vehicle_type": ART} for i in range(1, 8)]
_seven_routes = {f"S{i}": {"route_id": f"S{i}", "origin": f"O{i}", "dest": "D", "ipt": ""} for i in range(1, 8)}
R7 = bulletin.rollup_payloads([{"month": 10, "lines": _seven_lines, "co2_to_date": []}], _seven_routes, WD)
ok("…the breaking case: seven routes give FIVE rows, the busiest first (S7 … S3), S1 and S2 cut",
   [b["route_id"] for b in R7["busiest_routes"]] == ["S7", "S6", "S5", "S4", "S3"] and R7["headline"]["routes_in_use"] == 7)

# rule 10: the breakdown
BD = R["breakdown"]
ok("⭐ rule 10 (breakdown): discipline rows from the LINE, sorted by tonnes a day: earthworks, structures, substructure",
   [r["key"] for r in BD["discipline"]] == ["earthworks", "structures", "substructure"]
   and near(BD["discipline"][0]["two_way_a_day"], (loads_r1_a + loads_r2) / WD, 1e-3)
   and BD["discipline"][0]["vehicles_a_day"] == math.ceil((loads_r1_a / WD) / TPV1) + math.ceil((loads_r2 / WD) / TPV2)
   and near(BD["discipline"][0]["tonnes_a_day"], (40000 + 14500) / WD, 1e-3), str(BD["discipline"]))
ok("…the group fleets add up to the headline fleet (ceil per line, summed per group — never ceil of the group)",
   sum(r["vehicles_a_day"] for r in BD["discipline"]) == FLEET and sum(r["vehicles_a_day"] for r in BD["team"]) == FLEET
   and sum(r["vehicles_a_day"] for r in BD["section"]) == FLEET)
ok("…team rows from the ROUTE's team, named by the tenant: North Team (R1), Central Team (R2)",
   [r["key"] for r in BD["team"]] == ["North Team", "Central Team"]
   and near(BD["team"][0]["two_way_a_day"], (loads_r1_a + loads_r1_b + loads_r1_c) / WD, 1e-3), str(BD["team"]))
ok("…section rows from the line: WS1 then WS2", [r["key"] for r in BD["section"]] == ["WS1", "WS2"])
ID_FORM = re.compile(r"\bIPT\s*[-_ ]?\s*[1-6]\b", re.I)
ok("⭐ no team id anywhere in what a person reads (the whole roll-up, as JSON)",
   not ID_FORM.search(json.dumps(R, ensure_ascii=False)), str(ID_FORM.findall(json.dumps(R)))[:200])
R_TEAM = bulletin.rollup_payloads([P10], ROUTES, WD, acc=TEAM1)
ok("⭐ a team code: the scheme's headline, routes and carbon unchanged; the per-team rows limited to its own team",
   R_TEAM["headline"] == H and R_TEAM["busiest_routes"] == B and R_TEAM["carbon"] == R["carbon"]
   and [r["key"] for r in R_TEAM["breakdown"]["team"]] == ["North Team"]
   and R_TEAM["breakdown"]["discipline"] == BD["discipline"], str(R_TEAM["breakdown"]["team"]))
ok("the payload-fallback count is carried (none in this fixture) with the fallback vehicle named",
   R["payload_fallback"]["lines"] == 0 and R["payload_fallback"]["vehicle"] == P10["payload_fallback_vehicle"])

# =========================================================================== #
#  3. Over a window: busiest month, months with volume                         #
# =========================================================================== #
R2M = bulletin.rollup_payloads([P10, P11], ROUTES, WD)
F10 = FLEET
F11 = math.ceil((20000 / PAY_ART / WD) / TPV1) + math.ceil((29000 / PAY_ART / WD) / TPV2)
ok("⭐ rule 5 (busiest month): over Oct–Nov the fleet is the busier month's, not the mean",
   R2M["vehicles"]["fleet"] == max(F10, F11) and F10 != F11 and R2M["vehicles"]["fleet"] != (F10 + F11) / 2,
   f"{R2M['vehicles']['fleet']} vs {F10} {F11}")
ok("…and the label says busiest month", "busiest month" in R2M["vehicles"]["rule"] and "busiest month" not in R["vehicles"]["rule"])
V11 = (20000 + 29000) / PAY_ART
R3M = bulletin.rollup_payloads([P10, P11, P12], ROUTES, WD)
ok("⭐ rule 6 (months with volume): Oct–Dec averages over TWO months (Dec is empty), not three",
   R3M["months_with_volume"] == 2 and near(R3M["headline"]["two_way_a_day"], (LOADS + V11) / 2 / WD, 1e-3)
   and not near(R3M["headline"]["two_way_a_day"], (LOADS + V11) / 3 / WD, 1e-3), str(R3M["headline"]))
ok("…each breakdown group divides by the months IT appeared in: structures ran in Oct only, so its rate is Oct's",
   near([r for r in R3M["breakdown"]["discipline"] if r["key"] == "structures"][0]["two_way_a_day"], loads_r1_b / WD, 1e-3)
   and [r for r in R3M["breakdown"]["discipline"] if r["key"] == "structures"][0]["months_with_volume"] == 1)
ok("…a route that appeared in both months divides by two", R3M["busiest_routes"][0]["months_with_volume"] == 2)
R_EMPTY = bulletin.rollup_payloads([P12], ROUTES, WD)
# NARROWED 12 Oct 2026 (the tests-and-regressions review): the carbon figures are BOTH None on an empty
# month — co2_t_a_day used to read 0.0 beside a None co2_t_in_month
ok("an empty month says so: empty, four headline figures null, routes 0, no busiest rows, both carbon figures None",
   R_EMPTY["empty"] is True and R_EMPTY["headline"]["two_way_a_day"] is None and R_EMPTY["headline"]["routes_in_use"] == 0
   and R_EMPTY["busiest_routes"] == [] and R_EMPTY["note"] == "No approved forecast in this month."
   and R_EMPTY["carbon"]["co2_t_a_day"] is None and R_EMPTY["carbon"]["co2_t_in_month"] is None
   and R_EMPTY["carbon"]["not_baked"] is False and R_EMPTY["carbon"]["error"] is None)
R_UNDRAWN = bulletin.rollup_payloads([dict(P10, lines=[l for l in P10["lines"] if l["route_id"] == "R3"])], ROUTES, WD)
ok("…a month whose only lines sit on undrawn routes is empty too, but the note NAMES them rather than saying there is no forecast",
   R_UNDRAWN["empty"] is True and R_UNDRAWN["routes_not_drawn"] == {"lines": 1, "routes": ["R3"], "note": R_UNDRAWN["routes_not_drawn"]["note"]}
   # NARROWED 12 Oct 2026 (wording): "with no stored road route yet", not "not yet baked"
   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): "not routed yet"
   and R_UNDRAWN["note"] == ("No approved forecast on a route the map draws in this month: 1 line on 1 route "
                             "not routed yet, listed below and not counted."), R_UNDRAWN["note"])

# =========================================================================== #
#  4. The harness comparison: calculateKPIs's rules, written again, independently
# =========================================================================== #
def bar_rules(payloads, routes, wd):
    """
    The browser's calculateKPIs, re-derived from map/index.html by hand and written in a
    different shape (per-line records, Fractions, Counters) so it shares no code with
    bulletin.rollup_payloads. Filters are 'ALL' (whole scheme).
    """
    wd = Fraction(str(wd))
    recs = []
    for pi, p in enumerate(payloads):
        mk = p["month"] if p.get("month") is not None else pi
        for l in p["lines"]:
            if l["route_id"] not in routes:
                continue
            tpv = l.get("trips_per_vehicle_day")
            recs.append({"m": mk, "rid": l["route_id"], "loads": Fraction(str(l["vehicle_loads"])),
                         "t": Fraction(str(l.get("qty_t") or 0)), "co2": l.get("co2_t"),
                         "fleet": (math.ceil(Fraction(str(l["vehicle_loads"])) / wd / Fraction(str(tpv))) if tpv else None),
                         "disc": l.get("discipline") or "unassigned"})
    months = sorted({r["m"] for r in recs})
    if not months:
        return {"empty": True}
    per_month_loads = {m: sum((r["loads"] for r in recs if r["m"] == m), Fraction(0)) for m in months}
    per_month_fleet = {m: sum(r["fleet"] or 0 for r in recs if r["m"] == m) for m in months}
    per_month_co2 = {m: sum(r["co2"] for r in recs if r["m"] == m and r["co2"] is not None) for m in months}
    n = len(months)
    by_route = defaultdict(lambda: {"loads": Fraction(0), "months": set()})
    for r in recs:
        by_route[r["rid"]]["loads"] += r["loads"]
        by_route[r["rid"]]["months"].add(r["m"])
    busiest = sorted(by_route, key=lambda rid: (-(by_route[rid]["loads"] / len(by_route[rid]["months"]) / wd), rid))[:5]
    disc = defaultdict(lambda: {"loads": Fraction(0), "t": Fraction(0), "fleet": 0, "months": set()})
    for r in recs:
        g = disc[r["disc"]]
        g["loads"] += r["loads"]; g["t"] += r["t"]; g["fleet"] += r["fleet"] or 0; g["months"].add(r["m"])
    return {
        "empty": False,
        "two_way_a_day": float(sum(per_month_loads.values()) / n / wd),
        "fleet": max(per_month_fleet.values()),
        "unbaked": sum(1 for r in recs if r["fleet"] is None),
        "co2_unbaked": sum(1 for r in recs if r["co2"] is None),
        "co2_day": sum(per_month_co2.values()) / n / float(wd),
        "routes": len(by_route),
        "busiest": busiest,
        "busiest_rates": [float(by_route[rid]["loads"] / len(by_route[rid]["months"]) / wd) for rid in busiest],
        "disc": {k: (float(g["loads"] / len(g["months"]) / wd), float(g["t"] / len(g["months"]) / wd), g["fleet"] / len(g["months"]))
                 for k, g in disc.items()},
    }


for label, pays in (("Oct", [P10]), ("Oct–Nov", [P10, P11]), ("Oct–Dec", [P10, P11, P12]), ("Nov", [P11])):
    a = bulletin.rollup_payloads(pays, ROUTES, WD)
    b = bar_rules(pays, ROUTES, WD)
    ok(f"⭐ harness comparison, {label}: roll-up = the bar's rules — two-way a day, fleet (busiest month), unbaked counts, "
       f"co2 a day, routes, the busiest order and rates",
       near(a["headline"]["two_way_a_day"], b["two_way_a_day"], 1e-3) and a["vehicles"]["fleet"] == b["fleet"]
       and a["vehicles"]["excludes_unbaked_lines"] == b["unbaked"] and a["carbon"]["excludes_unbaked_lines"] == b["co2_unbaked"]
       and near(a["carbon"]["co2_t_a_day"], b["co2_day"], 1e-3) and a["headline"]["routes_in_use"] == b["routes"]
       and [x["route_id"] for x in a["busiest_routes"]] == b["busiest"]
       and all(near(x["two_way_a_day"], y, 1e-3) for x, y in zip(a["busiest_routes"], b["busiest_rates"])),
       f"{a['headline']} {a['vehicles']} | {b}")
    ok(f"…{label}: every discipline row agrees (two-way a day, tonnes a day, vehicles a day)",
       {r["key"] for r in a["breakdown"]["discipline"]} == set(b["disc"])
       and all(near(r["two_way_a_day"], b["disc"][r["key"]][0], 1e-3) and near(r["tonnes_a_day"], b["disc"][r["key"]][1], 1e-3)
               and near(r["vehicles_a_day"], b["disc"][r["key"]][2], 1e-6) for r in a["breakdown"]["discipline"]),
       f"{a['breakdown']['discipline']} | {b['disc']}")
ok("the seven-route synthetic payload agrees too (top five, order)",
   bar_rules([{"month": 10, "lines": _seven_lines}], _seven_routes, WD)["busiest"] == [b["route_id"] for b in R7["busiest_routes"]])

# =========================================================================== #
#  5. The module's rules at source level                                       #
# =========================================================================== #
SRC = read("backend/bulletin.py")
ok("🔴 the literal-22 ban: bulletin.py carries no '22' anywhere — working days come from main._working_days only",
   "22" not in SRC and "_working_days(" in SRC and "working_days_per_month" not in SRC)
ok("bulletin.py never names a team slot id", not ID_FORM.search(SRC))
ok("bulletin.py calls the map's own functions, not the endpoints over HTTP",
   "public_month_kpis(" in SRC and "public_map_data()" in SRC and "urlopen" not in SRC and "requests." not in SRC)
ok("bulletin.py reads the carbon stamp from carbon.py, not a copy", "carbon.SUMMARY_STAMP" in SRC
   and "planning estimate, DESNZ" not in SRC)
ok("every SQL in bulletin.py carries the tenant predicate (test_tenant_audit checks the AST; this pins the count)",
   SRC.count("tenant_id = ?") == 2 and SRC.count("db.query(") == 2)
# 12 Oct 2026 (the tenancy / wording review): rollup_payloads promises no database read, but team_text() without
# a `word` read the tenant settings for every line — with the word handed in it reads nothing
_real_word = taxonomy._team_word


def _no_db(*a, **k):
    raise AssertionError("rollup_payloads read the tenant settings")


taxonomy._team_word = _no_db
try:
    R_PURE = bulletin.rollup_payloads([P10], ROUTES, WD, acc=PLANNER, labels=taxonomy.team_labels(), team_word="Team")
    _pure_ok = [r["key"] for r in R_PURE["breakdown"]["team"]] == [r["key"] for r in R["breakdown"]["team"]] and R_PURE["headline"] == H
except AssertionError as e:
    _pure_ok = False
finally:
    taxonomy._team_word = _real_word
ok("⭐ rollup_payloads with labels and the team word handed in reads no tenant setting (pure, as its docstring says)",
   _pure_ok and "taxonomy.team_text(rp.get(\"ipt\"), labels, word)" in SRC)
ok("bulletin.py stamps generated_at from an aware UTC clock (utcnow is deprecated in Python 3.12)", "utcnow" not in SRC)
MAP = read("map/index.html")
ok("the map's rules the module mirrors are still the map's: ceil per line, the fractional sum, max over months, months with volume",
   "Math.ceil((l.vehicle_loads / wd) / l.trips_per_vehicle_day)" in MAP and "const fleet = Math.max(...mFleet)" in MAP
   and "veh += l.vehicle_loads" in MAP and "const n = mVeh.length;" in MAP and "if (!rp) return;" in MAP)
ok("the map's busiest list is five, by two-way a day, as the module's", ".sort((a, b) => b[2] - a[2]).slice(0, 5)" in MAP)
ok("the wording a person reads carries none of the banned words (public-facing rules)",
   not re.search(r"\b(secure|real[- ]time|telematics|AI|optimi[sz]e|predict|live tracking|truck)\b", SRC))
ok("main.py registers GET /api/bulletin/month behind _require_access and imports the module",
   '@app.get("/api/bulletin/month")' in read("backend/main.py") and "import bulletin" in read("backend/main.py")
   and re.search(r'@app\.get\("/api/bulletin/month"\)\ndef bulletin_month\(.*\):\n(?:\s+"""(?:.|\n)*?"""\n)?\s+acc = _require_access\(\)',
                 read("backend/main.py")))

# =========================================================================== #
#  6. Conditions of the month                                                  #
# =========================================================================== #
ok("weeks.month_span: October 2026 is 1–31 Oct; December runs to the 31st; February 2028 has 29 days",
   weeks.month_span(10) == (datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
   and weeks.month_span(12)[1] == datetime.date(2026, 12, 31)
   and weeks.month_span(26) == (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29)))
_mf, _mt = weeks.month_span(10)
ok("clashes._overlaps_span is the week rule generalised: the week name still answers, the span name takes a month",
   clashes._overlaps_span({"from": "2026-10-16", "to": "2026-10-17"}, _mf, _mt)
   and not clashes._overlaps_span({"from": "2026-09-10", "to": "2026-09-30"}, _mf, _mt)
   and clashes._overlaps_span({"from": None, "to": None}, _mf, _mt)
   and clashes._overlaps_span({"from": "2026-09-28", "to": "2026-10-02"}, _mf, _mt)
   and not clashes._overlaps_span({"from": "2026-11-01", "to": None}, _mf, _mt)
   and clashes._overlaps_week({"from": "2026-10-16", "to": "2026-10-17"}, _mf, _mt)
   and clashes._overlaps_week is not clashes._overlaps_span)

# no stored check anywhere yet
C0 = bulletin.conditions_of_month(10, payload=P10, factors=FACTORS)
ok("⭐ with no stored check on any route the restrictions block reads \"never checked\" and lists every route — never clean",
   C0["restrictions"]["status"] == "never checked" and C0["restrictions"]["never_checked_routes"] == ["R1", "R2", "R3"]
   and C0["restrictions"]["hits"] == [] and C0["restrictions"]["never_checked_wording"] == "never checked", str(C0["restrictions"]))
ok("the span is the calendar month", C0["span"] == ["2026-10-01", "2026-10-31"] and C0["calendar_month"] == 10)

# a stored check on R1: an ENDED closure, a closure in the month, an undated limit; R2 and R3 never checked
_hits = [
    {"headline": "A46 Barrier repairs (2026-09-10 → 2026-09-30)", "what": "Planned closure", "label": "Planned road closures",
     "kind": "closure", "from": "2026-09-10", "to": "2026-09-30", "severity": "note", "verdict": None, "road_nr": "A46"},
    {"headline": "A6 Resurfacing (2026-10-16 → 2026-10-17)", "what": "Planned closure", "label": "Planned road closures",
     "kind": "closure", "from": "2026-10-16", "to": "2026-10-17", "severity": "note", "verdict": None, "road_nr": "A6"},
    {"headline": "Mass limit 18 t", "what": "Mass limit", "label": "Mass limits", "kind": "mass",
     "from": None, "to": None, "severity": "breach", "verdict": "breach", "road_nr": "B6047"},
]
db.execute("UPDATE routes SET restrictions_hits = ?, restrictions_checked_at = ?, restrictions_status = ? "
           "WHERE tenant_id = ? AND id = ?", (json.dumps(_hits), "2026-10-11T20:00:00Z", "ok", "default", "R1"))
C10 = bulletin.conditions_of_month(10, payload=P10, factors=FACTORS)
_h = C10["restrictions"]["hits"]
ok("⭐ a stored hit overlapping the month is included; the undated limit always counts; the ENDED closure is excluded",
   [x["headline"] for x in _h] == ["A6 Resurfacing (2026-10-16 → 2026-10-17)", "Mass limit 18 t"]
   and all(x["route_id"] == "R1" and x["checked_at"] == "2026-10-11T20:00:00Z" for x in _h), str(_h))
ok("…the routes without a stored check are listed as never checked; the block is partly checked",
   C10["restrictions"]["never_checked_routes"] == ["R2", "R3"] and C10["restrictions"]["status"] == "partly checked"
   and C10["restrictions"]["checked_at"] == "2026-10-11T20:00:00Z")
C9 = bulletin.conditions_of_month(9, payload=P10, factors=FACTORS)
ok("…the breaking case: in September the ended closure IS a hit and the October one is not",
   [x["headline"] for x in C9["restrictions"]["hits"]] == ["A46 Barrier repairs (2026-09-10 → 2026-09-30)", "Mass limit 18 t"])
# 12 Oct 2026 (the review and fix pass): the stored check keeps only closures in force when it ran, so for a month
# that had ended by then it can be missing closures — the block says so instead of a bare "checked"
_C9r = C9["restrictions"]
ok("⭐ a month that ended before the stored check ran says the check came after it and may be incomplete",
   _C9r["checked_after_month"] is True and _C9r["past_month_note"] == (
       "Checked on 2026-10-11, after this month ended; closures that had ended by then are not stored, "
       "so this month's list may be incomplete."), str(_C9r.get("past_month_note")))
ok("…while the month the check ran in carries no such note", C10["restrictions"]["checked_after_month"] is False
   and C10["restrictions"]["past_month_note"] is None)
ok("the hit a person reads carries the dates, the road and the verdict, never a team id",
   _h[0]["from"] == "2026-10-16" and _h[0]["road_nr"] == "A6" and _h[1]["verdict"] == "breach"
   and not ID_FORM.search(json.dumps(C10)))

# stockpiles: over at the END of the month only
stockpiles.set_capacity("L2", capacity_qty=1000, capacity_unit="t", opening_qty=1200)
_c9 = bulletin.conditions_of_month(9, payload=P10, factors=FACTORS)["stockpiles_over"]
ok("⭐ a stockpile over capacity at the end of September is listed, with the figures",
   len(_c9) == 1 and _c9[0]["location_id"] == "L2" and _c9[0]["name"] == "Mill Compound"
   and _c9[0]["capacity_qty"] == 1000 and near(_c9[0]["balance_end"], 1200) and near(_c9[0]["over_by"], 200), str(_c9))
# NARROWED 27 Oct 2026 (stockpile forecast, D2): the stockpile has a capacity, so its balance runs forward from the plan (this
# harness's October lines into it stand in for the weeks nobody recorded); the breaking case types an Out in October's LAST
# week that brings it under by month END — the rule under test is unchanged: only the end of the month counts
_oct = [w for s_ in stockpiles.balances(10, 10)["stockpiles"] if s_["location_id"] == "L2" for w in s_["weeks"]]
_last = _oct[-1]
_before = (_oct[-2]["balance_end"] if len(_oct) > 1 else 1200.0)
stockpiles.consume("L2", 10, _last["week_index"], consumed_qty=_before + _last["inbound"] - 500, unit="t")
_c10 = bulletin.conditions_of_month(10, payload=P10, factors=FACTORS)["stockpiles_over"]
ok("…the breaking case: an Out typed in October's last week brings it under by month END, so October lists nothing",
   _c10 == [] and bulletin.conditions_of_month(9, payload=P10, factors=FACTORS)["stockpiles_over"], str(_c10))
ok("…and a location with no capacity is never 'over'", all(x["location_id"] != "L4" for x in _c9))
# 12 Oct 2026 (the tenancy / wording review; D23): the sentence a person reads says the balance is RECORDED —
# typed week actuals carried forward — never "the plan puts", which is what the map says today (`map/index.html`)
ok("⭐ the stockpile sentence reads \"recorded in it at the end of Sep 2026\", names the capacity and the unit, and never \"the plan puts\"",
   # NARROWED 12 Oct 2026 (the review and fix pass): "has a capacity of", not "holds" — "holds" read as the pile's
   # contents now, beside a different recorded figure
   _c9[0]["wording"] == ("Mill Compound has a capacity of 1,000 t; 1,200 t recorded in it at the end of Sep 2026, from the "
                         "week actuals typed so far, carried forward.")
   and " holds " not in _c9[0]["wording"]
   and _c9[0]["wording"] == bulletin.stockpile_wording("Mill Compound", 1000, 1200, "t", 9)
   and "plan puts" not in _c9[0]["wording"], str(_c9[0].get("wording")))
ok("…the wording is one function and bulletin.py never says \"The plan puts\"",
   "The plan puts" not in read("backend/bulletin.py") and "recorded in it at the end of" in read("backend/bulletin.py"))

# seasonal windows: the calendar month and the vehicle
F_SEAS = dict(FACTORS, seasonal_restrictions=[
    {"name": "Harvest", "months": [10], "restricted_vehicles": [R8], "message": "Rigid lorries avoid the lanes at harvest. Check the parish notice."},
    {"name": "Thaw", "months": [3, 4], "restricted_vehicles": [], "message": "Weight limits during the thaw."},
    {"name": "Fair week", "months": [10], "restricted_vehicles": [], "message": "The fair closes the square."},
])
_s = bulletin.conditions_of_month(10, payload=P10, factors=F_SEAS)["seasonal"]
ok("⭐ seasonal windows for THIS calendar month: Harvest applies to the one route with a rigid line (R1); Fair week, naming no vehicle, to every route",
   [(w["name"], w["routes"]) for w in _s] == [("Harvest", ["R1"]), ("Fair week", ["R1", "R2", "R3"])], str(_s))
ok("…the breaking case: the Thaw window (March–April) is not in October's list; in March nothing has volume, so no routes",
   all(w["name"] != "Thaw" for w in _s)
   and bulletin.conditions_of_month(3, payload=bulletin.month_payload(3), factors=F_SEAS)["seasonal"] == [])

# typed caps against loaded trips a day
_cap = C10["route_caps"]
ok("⭐ route caps: R1's 1,651 loads over the working days exceed its cap of 60 a day — listed as a planning flag",
   _cap["wording"] == "planning flag" and len(_cap["exceeded"]) == 1 and _cap["exceeded"][0]["route_id"] == "R1"
   and _cap["exceeded"][0]["cap"] == 60 and near(_cap["exceeded"][0]["two_way_a_day"], (loads_r1_a + loads_r1_b + loads_r1_c) / WD, 1e-3)
   and _cap["exceeded"][0]["wording"] == "planning flag" and _cap["routes_with_cap"] == 1
   and "never a block" in _cap["note"], str(_cap))
# 12 Oct 2026 (the review and fix pass): one name for the one figure — two-way movements a day, against a DAILY cap
ok("…the cap note names the figure 'two-way movements a day' (one load = one movement), never 'loaded trips'",
   _cap["note"] == ("Two-way movements a day (one load = one movement; the month's loads ÷ working days) against the "
                    "daily cap typed on the route — a planning flag, never a block.")
   and "Loaded trips" not in read("backend/bulletin.py") and "loaded trips a day" not in read("backend/bulletin.py"))
db.execute("UPDATE routes SET max_vehicles_per_day = ? WHERE tenant_id = ? AND id = ?", (80, "default", "R1"))
ok("…the breaking case: a cap of 80 is not exceeded, and R2 (no cap) is never listed",
   bulletin.conditions_of_month(10, payload=P10, factors=FACTORS)["route_caps"]["exceeded"] == [])
db.execute("UPDATE routes SET max_vehicles_per_day = ? WHERE tenant_id = ? AND id = ?", (60, "default", "R1"))
ok("the condition count adds the four sources", C10["count"] == len(_h) + len(C10["stockpiles_over"]) + len(C10["seasonal"]) + 1)

# =========================================================================== #
#  7. The endpoint body and the page                                           #
# =========================================================================== #
_tok = access._ACCESS.set(None)
try:
    main.bulletin_month(month=10)
    ok("🔴 /api/bulletin/month without a code — 401", False)
except _HTTPException as e:
    ok("🔴 /api/bulletin/month without a code — 401", e.status_code == 401)
finally:
    access._ACCESS.reset(_tok)
PAGE = main.bulletin_month(month=10)
ok("⭐ the page: rollup, conditions, month label, working days, demo notice, generated_at, terms",
   set(PAGE) >= {"rollup", "conditions", "month", "working_days", "demo_notice", "generated_at", "terms", "scope", "plan_only"}
   and PAGE["month"] == {"index": 10, "label": "Oct 2026", "label_long": "October 2026", "from": "2026-10-01", "to": "2026-10-31"}
   and PAGE["working_days"] == WD and PAGE["plan_only"] is True and PAGE["generated_at"].endswith("Z"), str(PAGE["month"]))
ok("…generated_at is an ISO UTC instant to the second (YYYY-MM-DDTHH:MM:SSZ)",
   bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", PAGE["generated_at"])), PAGE["generated_at"])
ok("…the roll-up on the page is the hand-computed one, with the typed cap on the busiest route and the section NAMES ready",
   PAGE["rollup"]["headline"] == H and PAGE["rollup"]["vehicles"] == R["vehicles"]
   and PAGE["rollup"]["busiest_routes"][0]["cap_wording"] == "planning flag" and PAGE["rollup"]["months"] == [10])
ok("…the conditions on the page are the month's: the two hits, the planning flag",
   len(PAGE["conditions"]["restrictions"]["hits"]) == 2 and PAGE["conditions"]["route_caps"]["exceeded"][0]["route_id"] == "R1")
# 14 Oct 2026 (the user took the recommendation): a stockpile over capacity is a site matter, so the PUBLIC page leaves it
# out; conditions_of_month still computes it (pinned in section 6 above)
_full9 = bulletin.conditions_of_month(9, payload=bulletin.month_payload(9), factors=FACTORS)
_pub9 = bulletin.public_conditions(_full9)
ok("⭐ the public page's conditions carry no stockpile: September's Mill Compound (over in the full list) is left out, the count with it",
   len(_full9["stockpiles_over"]) == 1 and "stockpiles_over" not in _pub9 and _pub9["count"] == _full9["count"] - 1
   and {k: v for k, v in _full9.items() if k not in ("stockpiles_over", "count")} == {k: v for k, v in _pub9.items() if k != "count"}
   and "stockpiles_over" not in PAGE["conditions"], str(sorted(_pub9)))
ok("…the page is built through public_conditions, and the bulletin document never prints a stockpile line",
   "public_conditions(conditions_of_month(" in read("backend/bulletin.py")
   and "stockpiles_over" not in read("backend/bulletin_doc.py") and '"Over capacity"' not in read("backend/bulletin_doc.py"))
ok("…the terms name the rule, the working days, the cap wording and that other schemes count differently",
   "lorry out laden and back empty" in PAGE["terms"]["two_way_movements"] and f"{WD:g}" in PAGE["terms"]["working_days"]
   and "planning flag" in PAGE["terms"]["cap"] and "no planning cap typed" in PAGE["terms"]["cap"]
   and "HS2" in PAGE["terms"]["other_schemes"] and PAGE["terms"]["carbon"].startswith("Wayscope planning estimate"))
ok("…no demo notice on a tenant that has none; the scope is the whole scheme for a planner",
   PAGE["demo_notice"] is None and PAGE["scope"] == {"team": None, "note": None})
ok("⭐ no team id anywhere on the page", not ID_FORM.search(json.dumps(PAGE, ensure_ascii=False)))
_tok = access._ACCESS.set(TEAM1)
try:
    PAGE_T = main.bulletin_month(month=10)
finally:
    access._ACCESS.reset(_tok)
# REVERSED 12 Oct 2026 (D37, the user: "all as recommended", option (a)): a team code sees every team's row, as a planner does
ok("⭐ a team code's page: the scheme's figures, EVERY team's rows (the planner's), the scope named by the tenant's label",
   PAGE_T["rollup"]["headline"] == H and PAGE_T["rollup"]["breakdown"]["team"] == PAGE["rollup"]["breakdown"]["team"]
   and len(PAGE_T["rollup"]["breakdown"]["team"]) >= 2
   and PAGE_T["scope"]["team"] == "North Team" and "limited to your team" not in PAGE_T["scope"]["note"]
   and PAGE_T["conditions"]["restrictions"]["hits"] == PAGE["conditions"]["restrictions"]["hits"], str(PAGE_T["scope"]))
# 12 Oct 2026 (the review and fix pass): the per-team limit hides nothing (the headline less the team's own row is the
# other teams' total, and the busiest routes and the other rows are the scheme's) — the note says so, in plain words.
# Whether a team code should see less is the user's decision; this pins what it sees TODAY.
ok("⭐ a team code's page says plainly that the headline, busiest routes and other rows include every team",
   PAGE_T["scope"]["note"] == bulletin.SCOPE_NOTE_TEAM and "include every team" in PAGE_T["scope"]["note"]
   and "map password" in PAGE_T["scope"]["note"])
ok("…and that is what it gets: the team code's busiest routes and discipline rows are the planner's",
   PAGE_T["rollup"]["busiest_routes"] == PAGE["rollup"]["busiest_routes"]
   and PAGE_T["rollup"]["breakdown"]["discipline"] == PAGE["rollup"]["breakdown"]["discipline"]
   and PAGE_T["rollup"]["breakdown"]["section"] == PAGE["rollup"]["breakdown"]["section"])
ok("month_rollup over a window reaches the same figures as the pure function",
   bulletin.month_rollup(10, PLANNER, months=[10, 11])["vehicles"]["fleet"] == R2M["vehicles"]["fleet"]
   and bulletin.month_rollup(10, PLANNER)["headline"] == H)
# 30 Oct 2026 (task 4b): the typed contact lines (Config -> Map and bulletin) a stubbed tenant may carry
CONTACTS = dict(concern_email="haulage.concerns@example.org", contact_phone="0116 000 0000",
                working_hours="Monday to Friday 07:30-18:00", other_formats="email haulage.concerns@example.org",
                newsletter_url="https://www.example.org/lorries")
_real_ts = bulletin.config.tenant_settings
bulletin.config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)",
                                                        demo_notice="Fictional demo scheme · nothing here is real")
try:
    PAGE_D = main.bulletin_month(month=10)
finally:
    bulletin.config.tenant_settings = _real_ts
ok("⭐ the demo notice rides on the page whenever the tenant sets one, with the tenant's name",
   PAGE_D["demo_notice"] == "Fictional demo scheme · nothing here is real" and PAGE_D["tenant_name"] == "Wolds Link (fictional)"
   and PAGE_D["rollup"]["headline"] == H)

# =========================================================================== #
#  8. The bulletin as people read it (C4, 12 Oct 2026): the PDF, the HTML page   #
# =========================================================================== #
# Review §2.6 / mockup 9. The PDF and the page are built from ONE view model (bulletin_doc.sheet), so
# the figures a person reads are asserted against the hand computation above (H, LOADS, WD), in
# pdf_text() of the PDF and in the HTML. Mapbox is never called: portable.offline() refuses every
# request, so the map is the schematic, and the static-image URL is read off a capturing stub.
import export  # noqa: E402
import bulletin_doc  # noqa: E402
import gate  # noqa: E402
import zones  # noqa: E402
from portable import pdf_text, offline  # noqa: E402

NOTICE = "Fictional demo scheme · nothing here is real"
_real_urlopen = offline(export)
zones.create_zone("Mill Lane 7.5 t limit except for access", {"type": "Polygon", "coordinates": [[[-0.5, 52.0], [-0.49, 52.0], [-0.49, 52.01], [-0.5, 52.0]]]},
                  kind="weight_limit", note="20 lorries a day typed")
zones.create_zone("Old bridge closure", {"type": "Polygon", "coordinates": [[[-0.6, 52.0], [-0.59, 52.0], [-0.59, 52.01], [-0.6, 52.0]]]},
                  kind="closure", starts_on="2026-09-01", ends_on="2026-09-30")
zones.create_zone("Quarry haul road", {"type": "LineString", "coordinates": [[-0.7, 52.0], [-0.69, 52.01]]}, kind="haul_road")
_real_ts2 = config.tenant_settings
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    S10 = bulletin_doc.sheet(10, PLANNER, now=datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc))
    S11 = bulletin_doc.sheet(11, PLANNER)
    PDF10 = export.build_bulletin_pdf(S10)
    PDF11 = export.build_bulletin_pdf(S11)
    HTML10 = bulletin_doc.html(S10)
finally:
    config.tenant_settings = _real_ts2
T10 = pdf_text(PDF10)
PAGES = [" ".join(p.split()) for p in T10.split("\f") if p.strip()]
T10J = " ".join(T10.split())
T11J = " ".join(pdf_text(PDF11).split())
PAGES11 = [" ".join(p.split()) for p in pdf_text(PDF11).split("") if p.strip()]
# 14 Oct 2026 (the publishing check): the Sources are set in two columns; pdftotext -layout reads across the columns line by
# line, so what is asserted IN the Sources is read in drawing order (-raw), each column whole
T10R = " ".join(pdf_text(PDF10, raw=True).split())
PAGESR = [" ".join(p.split()) for p in pdf_text(PDF10, raw=True).split("\f") if p.strip()]
HTML_TEXT = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", HTML10, flags=re.S)).split())
S10_ROLLUP_DISC = bulletin.month_page(10, PLANNER)["rollup"]["breakdown"]["discipline"]
import html as _hm  # noqa: E402
HTML_TEXT = _hm.unescape(HTML_TEXT)

ok("⭐ the bulletin PDF: a PDF of at least two A4 pages", PDF10[:5] == b"%PDF-" and len(PAGES) >= 2, f"{len(PAGES)} pages")
ok("⭐ \"fictional demo scheme\" on EVERY page of the PDF (the frame draws the tenant's notice on each)",
   all("fictional demo scheme" in p.lower() for p in PAGES), str([("fictional demo scheme" in p.lower()) for p in PAGES]))
# the four headline figures, formatted here independently of the module: the hand loads, not the roll-up
# REVERSED 12 Oct 2026 (the user, evening): movements in the month print whole ("2,151", was "2,151.0")
_fig = {"two_way": f"{LOADS / WD:,.0f}", "month": f"{LOADS:,.0f}", "routes": "2", "tonnes": f"{40000 + 4400 + 1500 + 14500:,.0f} t"}
ok("⭐ page 1 carries the four headline figures equal to the roll-up: two-way a day, movements in the month, routes, tonnes",
   _fig["two_way"] == "98" and _fig["month"] == "2,151" and _fig["tonnes"] == "60,400 t"
   and all(v in PAGES[0] for v in _fig.values())
   and [f["value"] for f in S10["headline"]] == [_fig["two_way"], _fig["month"], _fig["routes"], _fig["tonnes"]],
   f"{_fig} | {[f['value'] for f in S10['headline']]}")
ok("…each figure is the roll-up's (the sheet reads the same headline the JSON serves)",
   S10["rollup"]["headline"] == H and S10["headline"][0]["value"] == f"{H['two_way_a_day']:,.0f}"
   # REVERSED 12 Oct 2026 (the user, evening): whole movements on the page, rounded once from the fractional sum
   and S10["headline"][1]["value"] == f"{H['movements_in_month']:,.0f}" and "." not in S10["headline"][1]["value"])
# NARROWED 14 Oct 2026 (the publishing check): the label is short; "Working days are the scheme's settings" is in Sources
ok("…the movements in the month name the working days from the scheme's settings (the roll-up's day count)",
   S10["headline"][1]["label"] == f"movements in the month ({WD:g} working days)"
   and f"movements in the month ({WD:g}" in PAGES[0] and "Working days are the scheme's settings." in T10R)
ok("⭐ the HTML page carries the SAME four figures as the PDF (one view model): page and PDF cannot disagree",
   all(f'<div class="v">{v.replace("&", "&amp;")}</div>' in HTML10 for v in _fig.values())
   and all(v in HTML_TEXT for v in _fig.values()))
_KPI = f"Two-way movements = loads (deliveries) per working day ({WD:g}/month); each is a lorry out laden and back empty."
# NARROWED 14 Oct 2026 (the publishing check): page 1 prints the ONE short definition under the figures; the counting line and the map's
# kpi-note sentence, verbatim, are printed once, in Sources (they were on page 1 and again in the terms)
ok("⭐ page 1: the one-line definition; the counting line and the map's kpi-note sentence, verbatim, in Sources (PDF and page)",
   bulletin_doc.DEFINITION in PAGES[0] and bulletin_doc.DEFINITION in HTML_TEXT
   and "Counts are two-way movements: one lorry out laden and back empty is one delivery, counted once, never doubled." in PAGESR[-1]
   and _KPI in PAGESR[-1] and _KPI in HTML_TEXT and _KPI not in PAGESR[0]
   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): the map's hover note is short now; the bulletin's Sources keeps the full sentence
   and "Two-way movements = deliveries a working day (out laden, back empty)." in MAP)
# NARROWED 14 Oct 2026 (the publishing check): in Sources (page 4), with "Other schemes count differently" in the Two-way movement term
ok("…and the other-schemes line (HS2 counts HGVs visiting the site; EKFB printed each way)",
   "HS2 prints HGVs visiting the site" in PAGESR[-1] and "EKFB 2020 printed maximum HGV each way" in PAGESR[-1]
   and "Other schemes count differently." in T10J)
# NARROWED 13 Oct 2026 (W15, D43: the 4-page newsletter): the busiest routes table opens page 2 ("02 Routes and roads");
# page 1 names the busiest route in "This month in brief"
# NARROWED 14 Oct 2026 (the publishing check): ONE table of every route opens page 2 ("Every route this month", it replaced the busiest
# table and the chart); its flag cell is short ("60 · above", "—"); the brief says "Busiest route: ..."
ok("⭐ every route (page 2 of the newsletter): origin to destination, the planning flag typed on R1 and the plan above it; "
   "page 1's key points name the busiest route",
   "Every route this month" in PAGES[1] and "Kelsey Quarry to Mill Compound" in PAGES[1] and "Ridge Pit to Mill Compound" in PAGES[1]
   and "60 · above" in PAGES[1] and "no planning cap typed" not in PAGES[1]
   and "Busiest route: Kelsey Quarry to Mill Compound" in PAGES[0]
   and S10["busiest"][0]["flag_text"] == "60 a day · plan is above it" and S10["busiest"][0]["over_flag"] is True
   and S10["busiest"][0]["flag_short"] == "60 · above" and [r for r in S10["routes"] if r["cap"] is None][0]["flag_short"] == "—")
ok("…the letter pins: the busiest route's sites are A and B, in the legend under the map",
   [p["letter"] + " " + p["name"] for p in S10["places"]] == ["A Kelsey Quarry", "B Mill Compound", "C Ridge Pit"]
   and S10["busiest"][0]["letters"] == "A → B" and S10["busiest"][1]["letters"] == "C → B")
ok("…the busiest list is the roll-up's, in its order", [r["route_id"] for r in S10["busiest"]] == [b["route_id"] for b in B])
ok("⭐ last month, plan against plan: October's sheet says September had none planned; November's prints October's rate for R1",
   S10["busiest"][0]["last_month_text"] == "none planned"
   and [r for r in S11["routes"] if r["route_id"] == "R1"][0]["last_month_text"] == f"{(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f} a day"
   # NARROWED 14 Oct 2026 (the publishing check): the route table's last-month column is headed "Oct" and prints the figure
   and " Oct " in PAGES11[1].split("Every route this month")[1][:120]
   and f'<td class="n">{(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f}</td>' in bulletin_doc.html(S11))
ok("⭐ the roll-up's by_route list ranks EVERY drawn route the same way as the busiest five (the chart and the list agree)",
   R["by_route"][:len(R["busiest_routes"])] == R["busiest_routes"] and {r["route_id"] for r in R["by_route"]} == set(R["routes_in_use"])
   and [r["route_id"] for r in R7["by_route"]] == ["S7", "S6", "S5", "S4", "S3", "S2", "S1"] and R_EMPTY["by_route"] == [])
# REVERSED 14 Oct 2026 (the publishing check): the chart repeated the route table, so it is gone; each route's bar sits in the table, in its
# map colour, the planning flag a dashed red mark. Page 2: every route, what is moved, road works and limits, what changed;
# the last page: terms, caveats, Sources
ok("⭐ page 2: every route with its bar, what is being moved, the road works and limits, what changed; the last page terms, caveats, Sources",
   all(h in PAGES[1] for h in ("Every route this month", "What is being moved", "Road works and limits, October 2026",
                               "What changed since last month"))
   and all(h in PAGES[-1] for h in ("Terms", "Caveats", "Sources"))
   and "Two-way movements a day by route" not in T10J and "Terms explained" not in T10J)
# 17 Oct 2026: "What is being moved" printed the discipline IDS under a "Material" heading (R3's browser check on the
# four-year demo: "superstructure", "substructure"). It names each row by the tenant's discipline label, under "Discipline".
_MV = [m["name"] for m in S10["moved"]]
ok("🔴 What is being moved: each row is the tenant's discipline label (Bulk earthworks, Foundations), never the id",
   "Bulk earthworks" in _MV and "Foundations" in _MV and "earthworks" not in _MV and "substructure" not in _MV
   and "Structures" not in _MV and "structures" in _MV, str(_MV))
ok("…out of scope counts too (a line may still carry one): substructure is out of scope here and still reads Foundations",
   bulletin.discipline_names().get("substructure") == "Foundations")
_mv_html = HTML10[HTML10.index('data-bulletin="moved"'):HTML10.index("</table>", HTML10.index('data-bulletin="moved"'))]
ok("🔴 …the page's table: headed Discipline, the labels in its rows, no id",
   "<th>Discipline</th>" in _mv_html and "<th>Material</th>" not in HTML10 and "Bulk earthworks" in _mv_html
   and "Foundations" in _mv_html and ">earthworks<" not in _mv_html and ">substructure<" not in _mv_html, _mv_html[:400])
_p2 = PAGES[1][PAGES[1].index("What is being moved"):PAGES[1].index("Road works and limits")]
ok("🔴 …the PDF's table (page 2): headed Discipline, the labels, no id",
   "Discipline" in _p2 and "Material" not in _p2 and "Bulk earthworks" in _p2 and "Foundations" in _p2
   and not re.search(r"(?<![A-Za-z])(earthworks|substructure)\b", _p2.replace("Bulk earthworks", "")), _p2)
ok("…the roll-up keeps the id as the KEY (the filters and the sort read it); the pure roll-up with no names keeps name = key",
   {r["key"] for r in S10_ROLLUP_DISC} >= {"earthworks", "substructure"}
   and all(r["name"] == r["key"] for r in R["breakdown"]["discipline"]))
ok("…and month_rollup names them the same way (the bar's window roll-up)",
   {r["key"]: r["name"] for r in bulletin.month_rollup(10, PLANNER)["breakdown"]["discipline"]}.get("earthworks") == "Bulk earthworks")
ok("…the table's note names the bar colours and the dashed planning flag; the chart's caption and its 'flag 60' label are gone",
   "Bars in each route's map colour. Planning flag: the scheme's own daily limit, the dashed red mark (1 of 2 routes have one)." in T10J
   and "Dashed red mark: the planning flag typed on the route" not in T10J and "flag 60" not in T10J)
# NARROWED 17 Oct 2026 (no ids in text): the rows are the bar's panel's rows in its order, each named by the tenant's
# discipline label (BD is the pure roll-up, which has no names to hand: its name is the id)
ok("…what is being moved is the bar's discipline panel, with an All routes row equal to the headline",
   [m["name"] for m in S10["moved"]] == [bulletin.discipline_names().get(d["key"], d["name"]) for d in BD["discipline"]]
   and S10["moved_total"]["a_day"] == _fig["two_way"]
   and S10["moved_total"]["vehicles"] == f"{FLEET:,}")
ok("⭐ works affecting the roads: the stored A6 closure in October with its dates and provider; the ENDED closure is not there",
   "A6 Resurfacing" in T10J and "16 Oct 2026 to 17 Oct 2026" in T10J and "A46 Barrier repairs" not in T10J
   and "Mass limit 18 t" in T10J and "Mass limit: Mass limit" not in T10J and S10["works"][0]["who"] == (bulletin.restrictions.provider() or {}).get("name", S10["works"][0]["who"]))
ok("⭐ …the local controls are the zones in force in the month, numbered: the weight limit in; the September closure and the haul road out",
   [(z["n"], z["name"], z["kind"]) for z in S10["controls"]] == [(1, "Mill Lane 7.5 t limit except for access", "weight limit")]
   and "Mill Lane 7.5 t limit except for access" in T10J and "Old bridge closure" not in T10J and "Quarry haul road" not in T10J)
# NARROWED 14 Oct 2026 (the publishing check): plain words, no route ids; "never a block" is in the Planning flag term
ok("…the routes never checked are named as not checked — never a clear road",
   "2 of this month's routes not checked against published road works: other works may affect them." in T10J
   and "(R2, R3)" not in T10J)
ok("…the typed cap exceeded reads as a planning flag, never a block, by the route's places",
   f"Kelsey Quarry to Mill Compound: {(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f} a day planned, above its planning flag of 60 a day."
   in T10J and "It flags, never blocks, and is not a legal limit." in T10J and "Route R1" not in T10J)
ok("⭐ what changed since last month is plan against plan, and says so; October against an empty September; November against October",
   "Each month's approved plan as it stands today." in T10J     # NARROWED 14 Oct 2026: one short line
   and S10["change_text"].startswith("Since September 2026: Two-way movements a day — → 98")
   and f"Since October 2026: Two-way movements a day 98 to {(V11) / WD:,.0f}" in T11J
   and [c["label"] for c in S10["change_rows"]] == ["September 2026", "October 2026", "November 2026 (next)"], S10["change_text"])
# NARROWED 14 Oct 2026 (the publishing check): the rule is in Sources (the "Counting:" note), once
ok("⭐ the D28 rule is named: the month's loads summed as typed (fractional), not rounded per line",
   "The month's loads are summed as typed (fractional), not rounded per line" in T10R)
ok("⭐ whole movements (12 Oct, evening): the terms say the total is shown to the nearest whole movement, and no movement "
   "count on the page carries a decimal (the fractional sum stays in the JSON)",
   "the total is then shown to the nearest whole movement." in T10R       # NARROWED 14 Oct 2026: in Sources
   and all("." not in r["in_month_text"] for r in S10["routes"])
   and any(abs(r["a_day"] or 0) > 0 for r in S10["routes"]))
# REVERSED 14 Oct 2026 (the user took the recommendation): the PDF prints CO₂e with the subscript (Inter has U+2082); the
# view model still says CO2e, and only the Helvetica fallback keeps CO2e (pinned below)
ok("⭐ carbon carries the stamp: planning estimate, DESNZ 2026 basis, not Carbon Tool figures; CO₂e with its subscript in the PDF",
   "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in T10J and "CO₂e = routed km" in T10J
   and "CO2e = routed km" not in T10J
   and "₂" not in "".join(v for _, v in S10["terms"]) and "CO₂e = routed km" in HTML_TEXT
   and "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in HTML_TEXT)
import brand_pdf as _bpdf
_st = dict(_bpdf.fonts())
ok("⭐ CO₂e in the PDFs: no plain CO2e left anywhere in the newsletter text; Inter carries U+2082 in all three files",
   "CO2e" not in T10J and "CO₂e" in T10J and not _st["fallback"]
   and all(0x2082 in __import__("reportlab.pdfbase.ttfonts", fromlist=["TTFont"]).TTFont("chk" + f, os.path.join(BACKEND, "fonts", f"Inter-{f}.ttf")).face.charToGlyph
           for f in ("Regular", "Bold", "Italic")), str([T10J[max(0, m.start() - 70):m.end() + 30] for m in re.finditer("CO2e", T10J)][:6]))
_bpdf._STATE["fonts"] = dict(_st, fallback=True)
try:
    ok("🔴 …the breaking case: on Helvetica's fallback (no ₂ in WinAnsi) the helper keeps CO2e, and turns a CO₂e back",
       export._co2_pdf("t CO2e") == "t CO2e" and export._co2_pdf("t CO₂e") == "t CO2e")
finally:
    _bpdf._STATE["fonts"] = _st
ok("…and with Inter it prints the subscript", export._co2_pdf("t CO2e a day") == "t CO₂e a day" and export._co2_pdf(None) == "")
# NARROWED 14 Oct 2026 (the publishing check): the placeholder reads "[contact not set yet]" ("[... a typed field this scheme has not set yet]"
# read as an error)
# NARROWED 30 Oct 2026 (task 4b): only the report line keeps a visible gap; the hours and other formats lines are LEFT OUT
# while empty (they used to print "[not set yet]")
ok("⭐ the report-a-lorry block with nothing typed: the report line keeps its gap (no invented contact), the other lines are left out",
   "Report a lorry off route: the date, time, place, direction and registration, to [contact not set yet]." in T10J
   and "Working hours" not in T10J and "Large print and other formats" not in T10J and "not set yet" in T10J
   and T10J.count("not set yet") == T10J.count("[contact not set yet]") and "@" not in S10["report"]["lorry"]
   and S10["report"]["hours"] is None and S10["report"]["formats"] is None and S10["newsletter_url"] is None)
# 12 Oct 2026 (Track C review): the typed tenant.concern_email (the map's "Report a concern" address) is the
# bulletin's report-a-lorry address too; the placeholder prints only while it is not typed
_real_ts3 = config.tenant_settings
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE,
                                              concern_email="haulage.concerns@example.org")
try:
    S10C = bulletin_doc.sheet(10, PLANNER, now=datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc))
    HTML10C = bulletin_doc.html(S10C)
    T10CJ = " ".join(pdf_text(export.build_bulletin_pdf(S10C)).split())
finally:
    config.tenant_settings = _real_ts3
ok("⭐ report a lorry: a typed concern_email is printed (page and PDF), the placeholder is not",
   S10C["report"]["lorry"] == "Report a lorry off route: the date, time, place, direction and registration, to "
   "haulage.concerns@example.org." and "haulage.concerns@example.org" in HTML10C and "haulage.concerns@example.org" in T10CJ
   and "[contact" not in S10C["report"]["lorry"], S10C["report"]["lorry"])
ok("…and with none typed the same block keeps the placeholder (no invented contact)",
   S10["report"]["lorry"].endswith("[contact not set yet].")
   and "concern_email" not in S10["report"]["lorry"])
# NARROWED 13 Oct 2026 (W15): the band carries the brand title "Lorry movements bulletin · <month>" (the document's own
# title stays "Lorry movements in <month>"), the as-at stamp and the issue date; the foot adds wayscope.co.uk
ok("…the frame: the band's title, the as-at stamp and issue date, the plan-only foot on every page",
   "Lorry movements bulletin · October 2026" in PAGES[0] and S10["title"] == "Lorry movements in October 2026"
   and "Approved plan as at 12 October 2026 · Issued 12 October 2026" in PAGES[0]
   # NARROWED 14 Oct 2026 (the publishing check): the foot is "Planned figures, not counts"; pages 2 on carry a slim
   # running head (the band's title again, small) and every foot says "n of N"
   and all("Planned figures, not counts · prepared with Wayscope · wayscope.co.uk" in pg for pg in PAGES)
   and all(f"{i} of {len(PAGES)}" in pg for i, pg in enumerate(PAGES, 1))
   and all("Lorry movements bulletin · October 2026" in pg for pg in PAGES[1:]))
# NARROWED 14 Oct 2026 (the publishing check): the caption is one line ("Routes this month: 2 · ..." went: the table has the count); the map has
# its own title
ok("…the map is the schematic offline, and the caption says so", "Schematic from the stored road routes, not to scale." in PAGES[0]
   and "Routes this month: 2" not in PAGES[0] and "Planned lorry routes, October 2026" in PAGES[0])
ok("🔴 no team id in the PDF or the page, and no team name either (the per-team rows are not printed, D33)",
   not ID_FORM.search(T10J) and not ID_FORM.search(HTML10) and "North Team" not in T10J + HTML10 and "Central Team" not in T10J + HTML10)
_BANNED = re.compile(r"\b(secure|real[- ]time|telematics|optimi[sz]e|predict|live tracking)\b", re.I)
_trucks = lambda t: [m for m in re.findall(r"\btrucks?\b[ \w]{0,7}", t, re.I) if not m.lower().startswith("truck mixer")]
ok("🔴 the banned-word scan over the PDF text and the HTML (\"Truck mixer\" is a vehicle's name, the one exception)",
   not _BANNED.search(T10J + " " + HTML_TEXT) and not re.search(r"\bAI\b", T10J + " " + HTML_TEXT)
   and not _trucks(T10J + " " + HTML_TEXT) and _trucks("a Truck mixer (8 m3) and a truck") == ["truck"],
   str(_BANNED.findall(T10J + HTML_TEXT)) + str(_trucks(T10J + " " + HTML_TEXT)))
ok("…and over the two modules' own words", not _BANNED.search(read("backend/bulletin_doc.py"))
   and not re.search(r"\bAI\b", read("backend/bulletin_doc.py")) and not _trucks(read("backend/bulletin_doc.py")))
_EXP = read("backend/export.py")
# NARROWED 14 Oct 2026 (backlog item 2): the bulletin's PDF code ends where the route map export's begins (it was "to the
# end of the file", and the route map export now follows it in export.py)
_EXB = _EXP[_EXP.index("# ------------------------------------------------------------------ the monthly bulletin (C4"):
            _EXP.index("# ------------------------------------------------------------------ the route map export (14 Oct 2026")]
ok("🔴 the literal-22 ban on the composition: bulletin_doc.py and the bulletin's PDF code carry no '22' and never read the day count",
   "22" not in read("backend/bulletin_doc.py") and "22" not in _EXB
   and "working_days_per_month" not in read("backend/bulletin_doc.py") + _EXB and "[\"planning\"]" not in _EXB and "get(\"planning\")" not in _EXB)
ok("…the composition draws, it never computes the roll-up: no payload sum, no ceil, no SQL",
   "vehicle_loads" not in read("backend/bulletin_doc.py") + _EXB and "math.ceil" not in read("backend/bulletin_doc.py") + _EXB
   and "db." not in read("backend/bulletin_doc.py") + _EXB and "bulletin.month_page(" in read("backend/bulletin_doc.py"))

# the HTML page
ok("⭐ the HTML page: a document with a viewport, the demo notice, the PDF alongside, the public map linked, a print stylesheet",
   HTML10.startswith("<!doctype html>") and '<meta name="viewport" content="width=device-width,initial-scale=1">' in HTML10
   and f'<div class="notice">{NOTICE}</div>' in HTML10 and 'href="/api/bulletin/month.pdf?month=10">Download the PDF</a>' in HTML10
   and 'href="/map/">Open the public map</a>' in HTML10 and "@media print{" in HTML10 and "@page{size:A4;margin:14mm}" in HTML10)
ok("…the page moves a month either way", 'href="/bulletin/?month=9">‹ September 2026</a>' in HTML10
   and 'href="/bulletin/?month=11">November 2026 ›</a>' in HTML10)
_px = [int(x) for x in re.findall(r"(?:font-size:|font:(?:\d{3} )?)(\d+)px", HTML10)]
ok("🔴 the 14 px floor: no type on the page is set below 14 px (SVG labels included)", _px and min(_px) >= 14, str(sorted(set(_px))))
# REVERSED 14 Oct 2026 (the publishing check): the chart (plan-blue bars, its own flag line) is gone; each route's bar is in the route table,
# in the route's map colour, the planning flag a dashed red mark with its words in the title
_rt = HTML10.split('<table data-bulletin="routes">')[1].split("</table>")[0] if '<table data-bulletin="routes">' in HTML10 else ""
ok("…every route in one table, each bar in its map colour, the flag a dashed red mark with its words; no chart, no plan blue",
   _rt.count("<tr>") == 1 + len(S10["routes"]) and all(f'background:{r["color"]}' in _rt for r in S10["routes"])
   and '<span class="bc" style="left:' in _rt and 'title="planning flag 60 a day"' in _rt and '60 · above' in _rt
   and "border-left:2px dashed var(--flag)" in HTML10 and 'class="chart"' not in HTML10 and 'stroke="#4A72C9"' not in HTML10
   and "Bars in each route's map colour" in HTML_TEXT)
# NARROWED 12 Oct 2026 (wording review): 640 px let the 14 px labels of the 720-unit chart render at 12.4 px on a phone
# REVERSED 14 Oct 2026: there is no chart to scroll; offline the map is the inline schematic, with no basemap image
ok("…no chart wrapper; offline the map is the inline schematic: no basemap image and no Mapbox credit",
   "chartwrap" not in HTML10 and "mapbox" not in HTML10.lower() and "<image " not in HTML10
   and "Schematic, not to scale." in HTML_TEXT)
# NARROWED 17 Oct 2026 (UI audit #5, claude/ui-fix-keyboard): the wrapper is a named region a keyboard user can Tab to
ok("🔴 the 14 px floor on a phone: the bar column never squeezes (a min width; the table scrolls in its wrapper)",
   "td.bar{min-width:200px;white-space:nowrap}" in HTML10
   and '<div class="tw" tabindex="0" role="region" aria-label="Every route this month"><table data-bulletin="routes">' in HTML10)
# 12 Oct 2026 (Track C review): the schematic map is 720 units wide with 14 px pin letters; at width:100% on a 375 px
# phone they drew at about 6.7 px. It now sits in a scrolling wrapper and never draws narrower than its viewBox.
_mv = re.search(r'<div class="mapwrap" data-bulletin="map" tabindex="0" role="region" aria-label="[^"]+"><svg viewBox="0 0 (\d+) \d+" role="img"', HTML10)   # NARROWED 17 Oct 2026 (UI audit #5)
_mm = re.search(r"\.mapwrap svg\{min-width:(\d+)px\}", HTML10)
ok("🔴 the 14 px floor on a phone: the schematic map never draws narrower than its viewBox (it scrolls instead)",
   bool(_mv and _mm) and int(_mm.group(1)) >= int(_mv.group(1)) and ".mapwrap{overflow-x:auto" in HTML10,
   str((_mv and _mv.group(1), _mm and _mm.group(1))))
ok("…and on paper both figures take the page width (the phone's minimum is reset for print)",
   ".mapwrap svg{min-width:0}" in HTML10.split("@media print")[1])      # NARROWED 14 Oct 2026: no chart
ok("…every place a person reads text is escaped (a zone typed with markup prints as text)",
   "<script" not in bulletin_doc.html(dict(S10, title="<script>x</script>")).split("<style>")[1].split("</style>")[1]
   .replace("&lt;script&gt;", ""))

# --------------------------------------------------------------------------- #
#  8b. 13 Oct 2026 (the user): THIS MONTH AT A GLANCE and CARBON BY COUNCIL     #
# --------------------------------------------------------------------------- #
# The glance table is the Sizewell C monitoring report's tracker shape (item, figure, kind of data); what a monitoring
# report fills from OBSERVED records is listed and marked Not reported, never filled. Carbon by council: the districts
# alone in the map's orange ramp, from the stored polygons, no Mapbox call; a tenant with no districts prints nothing.
_G = {g["item"]: g for g in S10["glance"]}
ok("⭐ glance: the plan's figures equal the headline (two-way a day, movements in the month, routes) and say Forecast",
   _G["Two-way lorry movements a day"]["figure"] == _fig["two_way"] and _G["Lorry movements in the month"]["figure"] == _fig["month"]
   and _G["Routes in use"]["figure"] == _fig["routes"] and _G["Two-way lorry movements a day"]["data"] == "Forecast: the approved plan",
   str(S10["glance"][:3]))
ok("⭐ glance: the planning flag line counts the routes planned above their typed flag (R1 of the one route with a flag)",
   _G["Routes planned above their planning flag"]["figure"] == "1 of 1")
ok("⭐ glance: the month's haul carbon is the roll-up's t CO2e in the month, with the DESNZ basis named",
   # NARROWED 14 Oct 2026 (the publishing check): whole tonnes from 10 t (the panel's own rounding, _t), not one decimal
   _G["Haul carbon in the month"]["figure"] == bulletin_doc._t(R['carbon']['co2_t_in_month']) + " CO2e" == f"{R['carbon']['co2_t_in_month']:,.0f} t CO2e"
   and "DESNZ 2026" in _G["Haul carbon in the month"]["data"])
# NARROWED 14 Oct 2026 (the publishing check): the item is "Road works, closures and local limits"; "2 routes not checked"
ok("glance: road works say two of the month's routes were not checked (the stored check's own state), never a clear road",
   _G["Road works, closures and local limits"]["data"] == "2 routes not checked")
_NR = [g["item"] for g in S10["glance"] if g["not_reported"]]
ok("⭐ glance: the five things a monitoring report fills from observed records are listed and marked Not reported, never a figure",
   _NR == ["Lorries counted on the roads or at the site gates", "Lorries kept to the approved routes and working hours",
           "Vehicle and operator standards (FORS, CLOCS, Euro VI, Direct Vision Standard)", "Collisions and near misses",
           "Enquiries and complaints"]
   and all(g["figure"] == "Not reported" for g in S10["glance"] if g["not_reported"]), str(_NR))
# NARROWED in build 13 Oct (the rendered PDF): page 1 overflowed and split the table; it now opens page 2
# NARROWED 13 Oct 2026 (W15, D43): the tracker is part of page 1's summary now, after "This month in brief" (it opened
# page 2 of the 4-page bulletin of 13 Oct)
# NARROWED 14 Oct 2026 (the publishing check): the glance moved to the last page (carbon and the small print); page 1 is the front page
ok("⭐ glance: on the last page of the newsletter, after the carbon panel, and on the page, with its explanation",
   "This month at a glance" in PAGES[-1] and "This month at a glance" not in PAGES[0] and "This month in brief" not in T10J
   and "Key points" in PAGES[0] and "Not reported" in T10J and "FORS, CLOCS, Euro VI" in T10J and "Direct Vision" in T10J
   and '<table data-bulletin="glance">' in HTML10 and "never estimated" in HTML_TEXT and "never estimated" in T10J
   and HTML10.count('<tr class="nr">') == 5)
ok("🔴 no council districts: no carbon-by-council section anywhere, and nothing printed about it",
   S10["council"] is None and "Carbon by council" not in T10J and "Carbon by council" not in HTML10 and 'data-bulletin="council' not in HTML10)

# the colours and stops are the public map's own (read from map/index.html, never retyped by hand)
_mrc = re.search(r"const AREA_RAMP_CARBON = \[([^\]]+)\];", MAP)
_mst = re.search(r"const AREA_STOPS = \{ movements: \[[^\]]+\], carbon: \[([^\]]+)\] \};", MAP)
_mno = re.search(r"const AREA_NONE = '(#[0-9A-Fa-f]{6})';", MAP)
ok("⭐ council colours: the bulletin's ramp, stops and neutral are the map's AREA_RAMP_CARBON, AREA_STOPS.carbon and AREA_NONE; the hatch is areaHatchImage's",
   bool(_mrc and _mst and _mno)
   and list(bulletin_doc.COUNCIL_RAMP) == [x.strip().strip("'") for x in _mrc.group(1).split(",")]
   and list(bulletin_doc.COUNCIL_STOPS) == [int(x) for x in _mst.group(1).split(",")]
   and bulletin_doc.COUNCIL_NONE == _mno.group(1)
   and "on ? 0xB8 : 0xF3; data[i + 1] = on ? 0xB2 : 0xF1; data[i + 2] = on ? 0xA8 : 0xEC" in MAP
   and (bulletin_doc.HATCH_INK, bulletin_doc.HATCH_PAPER) == ("#B8B2A8", "#F3F1EC"))
_cc = bulletin_doc.council_class
ok("⭐ council classes, the map's step: None is 'no figure' (hatched), under 0.01 t the grey, then 50 / 100 / 200 t; a zero with routes not clipped is no figure, never a zero",
   _cc(None) == "nofig" and _cc(0) == "none" and _cc(0.004) == "none" and _cc(0.5) == 0 and _cc(49.99) == 0 and _cc(50) == 1
   and _cc(99.9) == 2 - 1 and _cc(100) == 2 and _cc(199) == 2 and _cc(200) == 3 and _cc(5000) == 3 and _cc(0, unclipped=True) == "nofig"
   and _cc(12, unclipped=True) == 0)

# the fixture's districts: the laden and return legs of R1 and R2 both run (-1.0, 52.5) -> (-1.1, 52.6), so by the
# segment's parameter: EAST holds lon -1.05..-1.0 = half, WEST lon -1.08..-1.05 = 0.3, the last 0.2 is in NO district
# (a neighbour not loaded); FAR has no route; the county holds EAST and WEST (0.8) with a hole that touches nothing
import areas  # noqa: E402
_ATTR = ["Source: Office for National Statistics licensed under the Open Government Licence v.3.0",
         "Contains OS data © Crown copyright and database right 2026"]
_sq = lambda x0, x1, y0=52.4, y1=52.7: [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
areas.import_collection({"type": "FeatureCollection", "attribution": _ATTR, "features": [
    {"type": "Feature", "properties": {"area_id": "E1", "name": "Eastshire", "tier": "district", "source": "Test districts (May 2026)",
                                        "highway_authority": "Test County Council"}, "geometry": {"type": "Polygon", "coordinates": [_sq(-1.05, -0.95)]}},
    {"type": "Feature", "properties": {"area_id": "W1", "name": "Westvale", "tier": "district", "source": "Test districts (May 2026)",
                                        "highway_authority": "Westvale City Council"}, "geometry": {"type": "Polygon", "coordinates": [_sq(-1.08, -1.05)]}},
    {"type": "Feature", "properties": {"area_id": "F1", "name": "Farmoor", "tier": "district", "source": "Test districts (May 2026)",
                                        "highway_authority": "Test County Council"}, "geometry": {"type": "Polygon", "coordinates": [_sq(0.0, 0.1)]}},
    {"type": "Feature", "properties": {"area_id": "C1", "name": "Testshire", "tier": "county", "source": "Test counties (Dec 2025)",
                                        "highway_authority": "Test County Council"},
     "geometry": {"type": "Polygon", "coordinates": [_sq(-1.08, -0.95), _sq(-0.97, -0.96, 52.41, 52.42)]}}]})
_CO2_ROUTE = {rid: sum(l["co2_t"] for l in P10["lines"] if l["route_id"] == rid and l["co2_t"] is not None) for rid in ("R1", "R2")}
_CT = _CO2_ROUTE["R1"] + _CO2_ROUTE["R2"]
_tt = lambda v: f"{v:,.0f} t" if v >= 10 else f"{v:,.1f} t"
_real_ts4 = config.tenant_settings
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE, **CONTACTS)
_calls = []
_real_open = export.urllib.request.urlopen


def _count_open(req, timeout=0):
    _calls.append(getattr(req, "full_url", str(req)))
    raise OSError("harness: counted, not fetched")


import basemap  # noqa: E402
try:
    export.urllib.request.urlopen = _count_open
    basemap._DOWN_UNTIL[0] = 0.0; basemap._CACHE.clear()
    _n0 = len(_calls); export.build_bulletin_pdf(S10); _no_council_calls = len(_calls) - _n0
    S10A = bulletin_doc.sheet(10, PLANNER, now=datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc))
    basemap._DOWN_UNTIL[0] = 0.0; basemap._CACHE.clear()
    _n0 = len(_calls); PDF10A = export.build_bulletin_pdf(S10A); _council_calls = len(_calls) - _n0
    HTML10A = bulletin_doc.html(S10A)
finally:
    export.urllib.request.urlopen = _real_open
    config.tenant_settings = _real_ts4
offline(export)
T10A = pdf_text(PDF10A)
T10AJ = " ".join(T10A.split())
T10AR = " ".join(pdf_text(PDF10A, raw=True).split())         # the Sources in drawing order (two columns)
HTML_TEXT_A = _hm.unescape(" ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", HTML10A, flags=re.S)).split()))
CA = S10A["council"]
_D = {d["name"]: d for d in (CA or {}).get("districts") or []}
ok("⭐ council: with districts loaded the section is there, titled for the month, with the three DISTRICTS only (the county is not drawn)",
   CA and CA["title"] == "Carbon by council in October 2026" and set(_D) == {"Eastshire", "Westvale", "Farmoor"}, str(CA and list(_D)))
ok("⭐ council (hand): each district's t CO2e is the routes' month carbon split by the km inside — Eastshire half, Westvale 0.3; "
   "largest first",
   near(_D["Eastshire"]["co2_t"], 0.5 * _CT, 1e-3) and near(_D["Westvale"]["co2_t"], 0.3 * _CT, 1e-3) and _CT > 0
   and _D["Eastshire"]["text"] == _tt(0.5 * _CT) and _D["Westvale"]["text"] == _tt(0.3 * _CT)
   and [d["name"] for d in CA["districts"]] == ["Eastshire", "Westvale", "Farmoor"],
   f"{_CT} {[(d['name'], d['co2_t'], d['text']) for d in CA['districts']]}")
ok("⭐ council: a district with no approved route is the neutral grey with its words, never an orange zero",
   _D["Farmoor"]["cls"] == "none" and _D["Farmoor"]["text"] == "no approved route" and _D["Farmoor"]["fill"] == "#E7E5E4"
   and _D["Farmoor"]["share"] == "—")
ok("council: each orange district's fill is the ramp step its tonnes fall in",
   all(d["fill"] == bulletin_doc.COUNCIL_RAMP[bulletin_doc.council_class(d["co2_t"])] for d in CA["districts"] if d["cls"] not in ("none", "nofig")))
ok("⭐ council: the tally names the carbon driven OUTSIDE the districts loaded (0.2 of the routes), never silently dropped",
   # NARROWED 14 Oct 2026 (the publishing check): one short sentence
   CA["tally"] == f"The 3 districts carry {_tt(0.8 * _CT)} of the scheme's {_tt(_CT)} CO2e; {_tt(0.2 * _CT)} is driven "
                  "outside them.", CA["tally"])
ok("council: shares of the scheme's carbon (50% and 30%) and the highway authority per district",
   _D["Eastshire"]["share"] == "50%" and _D["Westvale"]["share"] == "30%" and _D["Westvale"]["highway_authority"] == "Westvale City Council")
ok("council: a sliver of the scheme's carbon reads 'under 1%', never 0%",
   bulletin_doc._share(0.4, 100) == "under 1%" and bulletin_doc._share(0.6, 100) == "1%" and bulletin_doc._share(None, 100) == "—"
   and bulletin_doc._share(0, 100) == "—" and bulletin_doc._share(5, None) == "—")
ok("council: the county's figure is a line of text (its roads, its highway authority), not a second fill",
   # NARROWED 14 Oct 2026 (the publishing check): "<highway authority> roads: <t> CO2e."
   CA["county_lines"] == [f"Test County Council roads: {_tt(0.8 * _CT)} CO2e."], str(CA["county_lines"]))
# REVERSED 13 Oct 2026 (D40, the user: the council share "for scale"): it asserted "not comparable with the DESNZ local
# authority greenhouse gas statistics"; the basis now sets each district beside a month of its DESNZ road transport, for scale
ok("⭐ council: the basis sentence, the for-scale DESNZ wording, the Carbon page's stamp, the boundary source and the ONS / OS licence lines",
   # NARROWED 14 Oct 2026 (the publishing check): the basis in two sentences; the sources and licences once, in Sources
   "Each route's carbon is split by the km driven in each district, so the districts add up to the scheme's figure." in CA["basis"]
   and "not comparable" not in CA["basis"] and "for scale only" in CA["basis"]
   and "a month (one twelfth of the year) of its road transport CO2e in the government's local statistics (DESNZ, 2024" in CA["basis"]
   and CA["stamp"] == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"
   and CA["sources"] == ["Boundaries: Test districts (May 2026), generalised to 200 m."] and CA["attribution"] == _ATTR)
ok("⭐ council PDF: the section's title, each district and its figure, the tally, the stamp and both licence lines are in the PDF text",
   "Carbon by council in October 2026" in T10AJ and all(n in T10AJ for n in ("Eastshire", "Westvale", "Farmoor"))
   and _tt(0.5 * _CT) in T10AJ and "is driven outside them" in T10AJ
   # NARROWED 14 Oct 2026 (the publishing check): the licence lines and the stamp are in Sources, read in drawing order
   and "Contains OS data © Crown copyright and database right 2026" in T10AR
   and "Source: Office for National Statistics licensed under the Open Government Licence v.3.0" in T10AR
   and "not Carbon Tool figures" in T10AR, T10AR[-1500:])
# REVERSED 14 Oct 2026 (the user: "no map behind the route"): the districts are drawn over a basemap now, so a PDF asks
# Mapbox for a basemap — the basemap ALONE (no polygon, no route in the URL). The page fit is found on sizing passes with
# no fetch, and after one refusal nothing more is asked for DOWN_S seconds: ONE refused request per document, with or
# without districts, never one per map height or per map.
ok("🔴 council PDF: the only requests are basemaps (no route or polygon in any URL); one refused request per document, never one "
   "per map height or per map (sizing passes fetch nothing; the back-off)",
   _no_council_calls == 1 and _council_calls == 1 and all("/styles/v1/mapbox/light-v11/static/" in u and "path-" not in u
                                                          and "geojson" not in u for u in _calls),
   f"{_council_calls} vs {_no_council_calls} {[u.split('?')[0] for u in _calls]}")
ok("⭐ council PDF: 'fictional demo scheme' still on every page, which now number at least three",
   len([p for p in T10A.split("\f") if p.strip()]) >= 3 and all("fictional demo scheme" in p.lower() for p in T10A.split("\f") if p.strip()))
ok("⭐ council page: an inline SVG of the districts (even-odd fill, white 2.5 px borders), each label with name and figure; offline no basemap",
   # NARROWED 17 Oct 2026 (UI audit #5): the map wrapper is a named region with tabindex 0
   '<div class="mapwrap" data-bulletin="council-map" tabindex="0" role="region" aria-label="Carbon by council in October 2026 (map)"><svg viewBox="0 0 720 560"' in HTML10A
   and HTML10A.count('fill-rule="evenodd" stroke="#FFFFFF" stroke-width="2.5"') == 3
   and f'<tspan class="cn">Eastshire</tspan>' in HTML10A and f'dy="17">{_tt(0.5 * _CT)}</tspan>' in HTML10A
   and "mapbox" not in HTML10A.lower() and "<polyline" not in HTML10A.split('data-bulletin="council-map"')[1].split("</svg>")[0])
ok("council page: the district fills are the ramp's and the grey; the legend lists the four steps, the grey and the hatched no figure",
   f'fill="{_D["Eastshire"]["fill"]}" fill-rule="evenodd"' in HTML10A and 'fill="#E7E5E4" fill-rule="evenodd"' in HTML10A
   and all(t in HTML_TEXT_A for t in ("under 50 t", "50 to 99 t", "100 to 199 t", "200 t and over", "no approved route", "no figure (never a zero)")))
ok("council page: the table (district, highway authority, t CO₂e, share), the tally, the licence lines, the stamp",
   # NARROWED 14 Oct 2026 (the publishing check): the licences and the stamp are in Sources at the foot (once); the column
   # head is "t CO₂e"
   '<table data-bulletin="council">' in HTML10A and "Westvale City Council" in HTML_TEXT_A and "is driven outside them" in HTML_TEXT_A
   and "Contains OS data © Crown copyright and database right 2026" in HTML_TEXT_A.split("Sources")[-1]
   and "not Carbon Tool figures" in HTML_TEXT_A.split("Sources")[-1]
   and "<th class=\"n\">t CO₂e</th>" in HTML10A)
_pxA = [int(x) for x in re.findall(r"(?:font-size:|font:(?:\d{3} )?)(\d+)px", HTML10A)]
ok("🔴 the 14 px floor holds with the council section (its labels 14 px; the 720-unit map scrolls on a phone, never shrinks)",
   _pxA and min(_pxA) >= 14 and ".mapwrap svg{min-width:720px}" in HTML10A, str(sorted(set(_pxA))))
ok("🔴 the banned-word scan over the council section and the glance, page and PDF",
   not _BANNED.search(T10AJ + " " + HTML_TEXT_A) and not re.search(r"\bAI\b", T10AJ + " " + HTML_TEXT_A) and not _trucks(T10AJ + " " + HTML_TEXT_A))
ok("🔴 the literal-22 ban and the no-SQL rule still hold for the composition with the new section",
   "22" not in read("backend/bulletin_doc.py") and "db." not in read("backend/bulletin_doc.py")
   and "areas.area_load(mi, working_days=wd, geometry=True)" in read("backend/bulletin_doc.py"))
# a district with NO figure (its routes carry no carbon): hatched, never zero
_real_al = areas.area_load


def _al_nofig(*a, **k):
    out = _real_al(*a, **k)
    for x in out["areas"]:
        if x["area_id"] == "W1":
            x["co2_t"] = None
    out["totals"]["co2_t_by_tier"]["district"] = None
    return out


areas.area_load = _al_nofig
try:
    CN = bulletin_doc._council_carbon(10, WD, "October 2026")
finally:
    areas.area_load = _real_al
_DN = {d["name"]: d for d in CN["districts"]}
ok("⭐ council: a district with no carbon figure is HATCHED and says 'no figure', and no total is claimed",
   _DN["Westvale"]["cls"] == "nofig" and _DN["Westvale"]["text"] == "no figure" and _DN["Westvale"]["share"] == "—"
   and 'fill="url(#cc-hatch)"' in bulletin_doc._svg_council(CN) and CN["tally"].startswith("No total is given"))
_PN = export.build_bulletin_pdf(dict(S10A, council=CN))
ok("council: ...and the PDF draws it (the hatch is a clipped pattern) with the words", "no figure" in " ".join(pdf_text(_PN).split()))


def _al_boom(*a, **k):
    raise RuntimeError("fixture: the areas read failed")


areas.area_load = _al_boom
try:
    CE = bulletin_doc._council_carbon(10, WD, "October 2026")
finally:
    areas.area_load = _real_al
ok("🔴 council: a failed areas read keeps the section and says the figures could not be read (never a blank map of zeros)",
   CE["error"] == "The council figures could not be read for October 2026 (RuntimeError)." and CE["districts"] == []
   and "could not be read" in bulletin_doc._council_html(CE) and "could not be read" in " ".join(pdf_text(export.build_bulletin_pdf(dict(S10A, council=CE))).split()))
# NARROWED 14 Oct 2026: with no basemap the schematic projector; with one, Mapbox's own projection — both over council_points
ok("council: the shared projection — one projector for the page and the PDF (bulletin_doc.projector over council_points), "
   "or the basemap's view of the same points",
   "bulletin_doc.projector(bulletin_doc.council_points(C), w, h, 3 * mm)" in read("backend/export.py")
   and "P, img, v = _map_view(council_points(C), w, h, 16)" in read("backend/bulletin_doc.py")
   # NARROWED 28 Oct 2026 (8e): the call now ends in style="light" (the bulletin stays Light whatever Maps on paper says)
   and "_basemap_box(bulletin_doc.council_points(self.C), self.width, self.height, 20, style=\"light\")" in read("backend/export.py"))

# the static map's URL (a capturing stub, never the network)
_seen = []


def _capture(req, timeout=0):
    _seen.append(req.full_url)
    raise OSError("harness: captured, not fetched")


# REVERSED 14 Oct 2026 (the user: "no map behind the route"): the routes in the static-image URL (one plan blue, then
# bundle B's Volume colours with a casing per route and the shared sections on top) never fitted Mapbox's 8,192-character
# limit for a real month, so every PDF fell back to the blank schematic. basemap.py asks for the BASEMAP ALONE (a short
# URL whatever the month) and the routes, sections, pins and district fills are drawn over it in vector, in Mapbox's own
# projection. The URL is read off a capturing stub; the projection is checked by hand.
import basemap  # noqa: E402
_r1, _r2 = (LOADS - loads_r2) / WD, loads_r2 / WD
basemap._CACHE.clear(); basemap._DOWN_UNTIL[0] = 0.0          # the earlier refusals set the back-off
_v = basemap.view(bulletin_doc.map_points(S10), 1280, 600, 40)
basemap.urllib.request.urlopen = _capture
_none = basemap.fetch(_v, token="pk.test")
_down_after_refusal = basemap._DOWN_UNTIL[0] > 0
_seen_n = len(_seen)
basemap.fetch(basemap.view([(0.0, 51.0), (0.1, 51.1)], 400, 300), token="pk.test")
ok("🔴 basemap back-off: after a refused fetch the next one asks nothing (a document never waits on Mapbox twice)",
   _down_after_refusal and len(_seen) == _seen_n)
_seen[_seen_n:] = []
basemap._DOWN_UNTIL[0] = 0.0
_u = _seen[0] if _seen else ""
ok("⭐ the basemap URL: the light style, the view's centre and zoom, @2x, the token — and NO overlay (no path, no pin), so it "
   "always fits; a refused fetch is None (the caller draws the schematic)",
   _none is None and len(_seen) == 1
   and _u.startswith(f"https://api.mapbox.com/styles/v1/mapbox/light-v11/static/{_v['lon']:.5f},{_v['lat']:.5f},{_v['zoom']:.2f},0/1280x600@2x?access_token=pk.test")
   and "path-" not in _u and "pin-" not in _u and "geojson" not in _u and len(_u) < 200, _u)
_many = [{"route_id": f"X{i}", "coords": [(-1.0 + j * 0.0013 + i * 0.01, 52.5 + ((j * 7919) % 97) * 0.0011) for j in range(500)],
          "a_day": i} for i in range(1, 41)]
_seen.clear(); basemap._DOWN_UNTIL[0] = 0.0
basemap.fetch(basemap.view([c for r in _many for c in r["coords"]], 1280, 600, 40), token="pk.test")
ok("🔴 forty long routes: the URL is the same short basemap request (routes are never in it), far under 8,000 characters",
   len(_seen) == 1 and len(_seen[0]) < 200 and "path-" not in _seen[0], str([len(u) for u in _seen]))
_seen.clear(); basemap._DOWN_UNTIL[0] = 0.0
basemap.fetch(_v, token="pk.test", retina=False)
ok("…the HTML page asks for @1x (the PNG is inlined in the page), the PDF for @2x",
   len(_seen) == 1 and "/1280x600?access_token" in _seen[0] and "@2x" not in _seen[0])
basemap.urllib.request.urlopen = _real_urlopen
offline(export)
# the projection, by hand: the view's centre is the image's centre; every framed point lands inside the padding
_pc = basemap.project(_v, _v["lon"], _v["lat"])
_pp = [basemap.project(_v, *pt) for pt in bulletin_doc.map_points(S10)]
ok("⭐ basemap projection (hand): the centre at the image centre; every route point, pin and control inside the 40 px padding; "
   "the zoom kept to two decimals so the URL and the drawing use the same one",
   abs(_pc[0] - 640) < 1e-6 and abs(_pc[1] - 300) < 1e-6
   and all(39 <= x <= 1241 and 39 <= y <= 561 for x, y in _pp) and _v["zoom"] == round(_v["zoom"], 2)
   and (max(x for x, _ in _pp) - min(x for x, _ in _pp) > 1100 or max(y for _, y in _pp) - min(y for _, y in _pp) > 500))
# Web Mercator by hand: at zoom z one degree of longitude is 512 × 2^z / 360 px
_v0 = dict(_v, lon=0.0, lat=0.0, cx=0.5, cy=0.5, zoom=1.0)
ok("basemap projection (hand): one degree of longitude at zoom 1 is 1024/360 px; north is up (smaller y)",
   abs(basemap.project(_v0, 1.0, 0.0)[0] - 640 - 1024 / 360) < 1e-9 and basemap.project(_v0, 0.0, 10.0)[1] < 300)
# the scale bar: a round length near the asked width, from the ground resolution at the centre latitude
_km, _px = basemap.scale(dict(_v0, lat=52.5, zoom=10.0), 110)
_mpp = 40075016.686 * math.cos(math.radians(52.5)) / (512 * 2 ** 10)
ok("basemap scale (hand): at 52.5° N, zoom 10, a bar near 110 px is a round km length, drawn at exactly km ÷ metres a pixel",
   _km in (0.5, 1, 2, 5, 10) and abs(_px - _km * 1000 / _mpp) < 1e-9 and 110 / 1.6 <= _px <= 110 * 1.6, str((_km, _px)))
# NARROWED 23 Oct 2026: basemap offers path overlays for the ROUTE SHEET (its two legs under the road names, URL-limited,
# basemap.URL_MAX); the bulletin's own map builds none — its routes would overflow the URL, which is why it went
ok("🔴 the old route-in-URL map is gone (no bulletin_map_png, no static path or pin overlay built by the bulletin)",
   not hasattr(export, "bulletin_map_png") and "path_overlay(" not in _EXB and "path-{" not in _EXB
   and "pin-s-" not in _EXB and "URL_MAX = 7800" in read("backend/basemap.py"))
ok("🔴 basemap: the cache key is the URL WITHOUT the token; nothing is written to disk",
   'key = u.split("?", 1)[0]' in read("backend/basemap.py") and not re.search(r"(?<!url)open\(", read("backend/basemap.py")))


# --------------------------------------------------------------------------- #
#  8c. 13 Oct 2026 — BUNDLE B: W11 route colours, W12 council bands in Config,   #
#      W13 movements by council                                                 #
# --------------------------------------------------------------------------- #
_CFGJS = read("map/config.js")
# W11 — the page-1 route map takes the public map's Volume colours, one width
_mvs = re.search(r"const VOLUME_STOPS = \[([^\]]+)\];", MAP)
_mcr = re.search(r"const CARBON_RAMP = \[([^\]]+)\];", MAP)
_mcs = re.search(r'forecastCasing:\s*"(#[0-9A-Fa-f]{6})"', _CFGJS)
ok("⭐ W11 held equal: the bulletin's VOLUME_STOPS and VOLUME_RAMP are the map's VOLUME_STOPS and the CARBON_RAMP volumeColor() "
   "paints with; the casing is the map's forecastCasing",
   bool(_mvs and _mcr and _mcs)
   and list(bulletin_doc.VOLUME_STOPS) == [int(x) for x in _mvs.group(1).split(",")]
   and list(bulletin_doc.VOLUME_RAMP) == [x.strip().strip("'") for x in _mcr.group(1).split(",")]
   and "const s = stops, c = CARBON_RAMP;" in MAP and "volumeColor('f_avg', ROUTE_VOLUME_STOPS)" in MAP
   and bulletin_doc.ROUTE_CASING == _mcs.group(1))
ok("⭐ W11 held equal: the legend's five labels are the map's stepRanges() wording, the function read off the map",
   "return ['under ' + s[0] + unit, s[0] + ' to ' + s[1] + unit, s[1] + ' to ' + s[2] + unit, s[2] + ' to ' + s[3] + unit, s[3] + unit + ' and over'];" in MAP
   and [g["label"] for g in S10["volume_legend"]] == ["under 10", "10 to 25", "25 to 50", "50 to 100", "100 and over"]
   and [g["fill"] for g in S10["volume_legend"]] == list(bulletin_doc.VOLUME_RAMP))
_vc = bulletin_doc.volume_class
ok("W11: the step is the map's Mapbox step (at or over a stop takes the next colour); None and 0 the lightest",
   [_vc(x) for x in (None, 0, 9.99, 10, 24.9, 25, 49.9, 50, 99.9, 100, 4000)] == [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
_MR = {r["route_id"]: r for r in S10["map_routes"]}
ok("⭐ W11 (hand): R1 (~65 a day) is #0B55CB, R2 (~23 a day) #5A96F6; no width or weight is carried any more",
   _MR["R1"]["color"] == "#0B55CB" and _MR["R2"]["color"] == "#5A96F6" and near(_MR["R1"]["a_day"], _r1, 1e-3)
   and all("weight" not in r for r in S10["map_routes"]), str(S10["map_routes"]))
ok("W11: drawn quietest first, so the busiest route is on top", [r["route_id"] for r in S10["map_routes"]] == ["R2", "R1"])
_svgm = HTML10.split('data-bulletin="map"')[1].split("</svg>")[0]   # 17 Oct 2026: the wrapper carries tabindex / role / aria-label after the marker
ok("⭐ W11 page: every route at ONE width (5) in its Volume colour over a 7.5 casing in the map's ink; never the plan blue",
   _svgm.count('stroke-width="5"') == 2 and _svgm.count('stroke="#1F2024" stroke-width="7.5"') == 2
   and 'stroke="#0B55CB" stroke-width="5"' in _svgm and 'stroke="#5A96F6" stroke-width="5"' in _svgm
   and "#4A72C9" not in _svgm and _svgm.index('stroke-width="7.5"') < _svgm.index('stroke-width="5"'))
# NARROWED 14 Oct 2026 (the publishing check: legends too wordy): the legend title is "Two-way movements a day" (the map's own title names the month); the
# long "one width" sentences went (one width is a drawing rule, held at source below, not a thing a reader needs told)
ok("⭐ W11 page: the legend under the map — its title and the five swatches; the old 'thicker' line and the long one-width line are gone",
   'data-bulletin="map-legend"><b>Two-way movements a day:</b>' in HTML10
   and all(f"background:{c}" in HTML10.split('data-bulletin="map-legend"')[1].split("</p>")[0] for c in bulletin_doc.VOLUME_RAMP)
   and "thicker" not in HTML10 and "one width, so a width never carries a figure" not in HTML_TEXT
   and "Planned lorry routes, October 2026" in HTML_TEXT)
ok("⭐ W11 PDF: page 1 carries the legend (title and the five ranges); 'thicker' and the long caption nowhere",
   "Two-way movements a day:" in PAGES[0] and all(t in PAGES[0] for t in ("under 10", "10 to 25", "25 to 50", "50 to 100", "100 and over"))
   and "Volume colour for its two-way movements a day, one width" not in PAGES[0] and "thicker" not in T10J)
ok("🔴 W11 source: no line width is worked out from a volume in the bulletin's drawing code or the view model any more",
   all(x not in _EXB + read("backend/bulletin_doc.py") for x in ('r["weight"]', "r['weight']", '"weight":', "1.5 + 5 *", "0.8 + 3.2 *")))
# NARROWED 16 Oct 2026 (D115, the public map's flow lanes): the map's heat-map ribbon is 6 / 8.5 px now, so its two
# flow lanes fit inside it; the bulletin's map draws no lanes and keeps 5 / 7.5 — still one fixed width, never by volume
ok("🔴 W11 source: the schematic and the page draw the casing then the colour, at fixed widths",
   'c.setLineWidth(3.4)' in _EXB and 'c.setLineWidth(2.2)' in _EXB and "_hex_rgb(r[\"color\"])" in _EXB
   and "ROUTE_LINE_W, ROUTE_CASING_W = 5, 7.5" in read("backend/bulletin_doc.py")
   and "const CARBON_LINE_WIDTH = 6, CARBON_CASING_WIDTH = 8.5;" in MAP)

# W11 — the shared road sections, each by its routes summed (the map's Volume heat map: routes by their own figure,
# shared sections summed on top). R1 and R2 run the same road in the fixture, so after the index is built it is ONE shared
# section carrying both routes' loads (~98 a day, the 50-100 step), while each route alone is lighter.
# NARROWED 14 Oct 2026 (the publishing check: legends too wordy): one short sentence each way
ok("W11: with no shared-section index the map draws the routes only, and the note says each route has its own colour",
   S10["map_sections"] == [] and S10["map_note"] == "Each route is coloured by its own two-way movements a day.")
# REVERSED 14 Oct 2026 (the user took the recommendation): the map's Volume legend foot is shortened to match — it OPENS with the
# bulletin's note word for word, and the long "Each route is painted by its own figure; … summed, and labelled" is gone
# NARROWED 19 Oct 2026 (the user: "remove too much wording and put it into an info box"): the foot moved behind the heat
# map's "i" (`more`, written to #heat-info-more); it still OPENS with the bulletin's note word for word
# NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): the map's foot opens with the bulletin's sentence word for word (the shared-section count left it)
_mapfoot = re.search(r"more = 'Where routes share a road, its colour shows their total\. A colour means the same volume every month\. ' \+", MAP)
# NARROWED 14 Oct 2026 (the publishing check: legends too wordy): the bulletin's note says the rule in one sentence
ok("⭐ W11: the note says the map's rule in one sentence (shared roads show the routes' total), and the map's foot opens with it",
   bool(_mapfoot) and bulletin_doc.map_note(3) == "Where routes share a road, its colour shows their total."
   and "Each route is painted by its own figure; " not in MAP and "by the routes using it, summed, and labelled" not in MAP
   and MAP.count(bulletin_doc.map_note(3)[:-1]) >= 1
   and bulletin_doc.map_note(1) == bulletin_doc.map_note(3) and "Each route is painted" not in bulletin_doc.map_note(3))
import road_sections  # noqa: E402
_rb = road_sections.rebuild()
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    S10S = bulletin_doc.sheet(10, PLANNER)
    PDF10S = export.build_bulletin_pdf(S10S)
    HTML10S = bulletin_doc.html(S10S)
finally:
    config.tenant_settings = _real_ts4
_RL10 = road_sections.road_load(10, working_days=WD)
ok("⭐ W11 (hand): ONE shared section (R1 and R2's common road) at BOTH routes' loads ÷ working days = 98 a day, the 50-100 "
   "colour, while R2 alone is the 10-25 colour; the figure is road_load's (the map's /api/public/road-load)",
   len(S10S["map_sections"]) == 1 and near(S10S["map_sections"][0]["a_day"], LOADS / WD, 0.01)
   and S10S["map_sections"][0]["color"] == "#0B55CB" and S10S["map_sections"][0]["routes"] == 2
   and near(S10S["map_sections"][0]["a_day"], _RL10["runs"][0]["movements_per_day"], 1e-9)
   and {r["route_id"]: r["color"] for r in S10S["map_routes"]}["R2"] == "#5A96F6", str((_rb, S10S["map_sections"][:1] and S10S["map_sections"][0]["a_day"])))
_svgs = HTML10S.split('data-bulletin="map"')[1].split("</svg>")[0]
ok("⭐ W11 page: the shared section is drawn ON TOP of the routes (after them), with its own casing, in its summed colour",
   _svgs.count('class="sec"') == 2 and _svgs.rindex('stroke="#5A96F6"') < _svgs.index('class="sec"')
   and 'stroke="#0B55CB" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" class="sec"><title>shared by 2 routes: 98 two-way movements a day</title>' in _svgs
   and "Where routes share a road, its colour shows their total." in _hm.unescape(HTML10S))
# NARROWED 14 Oct 2026 (the publishing check: legends too wordy): the one-sentence note
ok("W11 PDF: the note under the legend says shared roads show the routes' total",
   "Where routes share a road, its colour shows their total." in " ".join(pdf_text(PDF10S).split()))
# REVERSED 14 Oct 2026: the sections were paths in the static-image URL; they are drawn over the basemap in vector now,
# casing then summed colour, after every route (the drawing code, read at source)
_dbs = _EXP[_EXP.index("def _draw_bulletin_schematic("):_EXP.index("class _BulletinMap(")]
ok("⭐ W11 map: the section's casing and its summed colour are drawn AFTER every route (on top), over the basemap or the schematic",
   _dbs.index('for r in S["map_routes"]:') < _dbs.index('for sct in S.get("map_sections") or []:')
   and "_hex_rgb(sct[\"color\"])" in _dbs)
_real_rl = road_sections.road_load


def _rl_boom(*a, **k):
    raise RuntimeError("fixture: road load failed")


road_sections.road_load = _rl_boom
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    S10F = bulletin_doc.sheet(10, PLANNER)
finally:
    road_sections.road_load = _real_rl
    config.tenant_settings = _real_ts4
ok("🔴 W11: a failed shared-section read keeps the routes on the map and SAYS the sections are missing (never a silent gap)",
   S10F["map_sections"] == [] and len(S10F["map_routes"]) == 2
   and S10F["sections_note"] == "The shared road sections could not be read (RuntimeError): each route is painted by its own figure only."
   and "could not be read (RuntimeError)" in bulletin_doc._volume_legend_html(S10F))
# NARROWED 14 Oct 2026 (the publishing check): the same caveat in one short sentence
ok("W11: the caveat is NARROWED — the map now colours shared roads by their sum; the tables stay per route; no figure on a road",
   "The tables are per route; on a road several routes share, the lorries are their sum (the map colours it, with no figure "
   "printed)." in " ".join(S10S["caveats"])
   and "does not yet print a figure per road" not in " ".join(S10S["caveats"]))

# W12 — the council bands per scheme, in Config, read by the map and the bulletin
ok("⭐ W12 default held equal three ways: config.COUNCIL_BREAKS_DEFAULT = the map's AREA_STOPS = the Config page's placeholder",
   config.council_breaks({}) == {"movements": [50, 100, 200], "carbon": [50, 100, 200]}
   and "const AREA_STOPS = { movements: [50, 100, 200], carbon: [50, 100, 200] };" in MAP
   and "const COUNCIL_BREAKS_DEFAULT = { movements: [50, 100, 200], carbon: [50, 100, 200] };" in read("frontend/index.html")
   and list(bulletin_doc.COUNCIL_STOPS) == list(config.COUNCIL_BREAKS_DEFAULT["carbon"]))
_cbp = config.council_breaks_problem
ok("🔴 W12 validation: three rising whole numbers of 1 or more, nothing else",
   _cbp([20, 50, 100]) is None and _cbp((1, 2, 3)) is None and _cbp([20.0, 50, 100]) is None
   and _cbp([100, 50, 200]) and _cbp([50, 50, 100]) and _cbp([0, 1, 2]) and _cbp([1.5, 2, 3]) and _cbp([1, 2])
   and _cbp([1, 2, 3, 4]) and _cbp([True, 2, 3]) and _cbp(["1", 2, 3]) and _cbp(None) and _cbp([1, 2, float("inf")]))
_doc0 = config.load(conversions)
_bad = json.loads(json.dumps(_doc0)); _bad.setdefault("tenant", {})["council_breaks"] = {"carbon": [100, 50, 20], "volume": [1, 2, 3]}
_pr = config.validate(_bad)
ok("🔴 W12 validation on save: falling bands and an unknown measure are refused with plain words",
   "tenant.council_breaks.carbon must rise from left to right" in _pr
   and "tenant.council_breaks.volume is not a measure (movements or carbon)" in _pr, str(_pr))
_bad2 = json.loads(json.dumps(_doc0)); _bad2.setdefault("tenant", {})["council_breaks"] = {"carbon": [1, None, 3]}
ok("🔴 W12 validation: a half-typed row (a blank among the three) is refused, never half-applied",
   "tenant.council_breaks.carbon must be whole numbers, 1 or more" in config.validate(_bad2), str(config.validate(_bad2)))
ok("W12: an unreadable stored row falls back per measure, never a crash (movements typed, carbon broken)",
   config.council_breaks({"tenant": {"council_breaks": {"movements": [5, 10, 20], "carbon": [3, 2, 1]}}})
   == {"movements": [5, 10, 20], "carbon": [50, 100, 200]}
   and config.council_breaks({"tenant": {"council_breaks": "nonsense"}}) == {"movements": [50, 100, 200], "carbon": [50, 100, 200]})
# type the demo's bands (20 / 50 / 100 t, chosen 13 Oct from the live demo's Sep-Dec district figures) and read them back
_doc1 = json.loads(json.dumps(_doc0)); _doc1.setdefault("tenant", {})["council_breaks"] = {"carbon": [20, 50, 100]}
_sv = config.save(_doc1, by="harness"); config.invalidate()
_A10 = areas.area_load(10, working_days=WD, geometry=False)
ok("⭐ W12: typed bands are saved and read back by ONE reader; a measure not typed keeps the default",
   _sv.get("ok") and config.council_breaks() == {"movements": [50, 100, 200], "carbon": [20, 50, 100]}
   and config.tenant_settings(conversions)["council_breaks"] == config.council_breaks(), str(_sv))
ok("⭐ W12 held equal, map side: both payloads the map reads carry the scheme's bands (shapes and the month's figures)",
   _A10["stops"] == config.council_breaks() and areas.shapes()["stops"] == config.council_breaks())
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE, **CONTACTS)
try:
    S10B = bulletin_doc.sheet(10, PLANNER, now=datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc))
    PDF10B = export.build_bulletin_pdf(S10B)
    HTML10B = bulletin_doc.html(S10B)
    S11B = bulletin_doc.sheet(11, PLANNER)
    _real_ts5 = config.tenant_settings
    config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE,
                                                  distance_unit="mi")
    S10M = bulletin_doc.sheet(10, PLANNER)
finally:
    config.tenant_settings = _real_ts4
T10B = pdf_text(PDF10B)
T10BJ = " ".join(T10B.split())
HTML_TEXT_B = _hm.unescape(" ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", HTML10B, flags=re.S)).split()))
CB, MB = S10B["council"], S10B["council_mv"]
ok("⭐ W12 held equal, bulletin side: the carbon section's bands are the payload's (the map's) and the legend reads them",
   CB["stops"] == _A10["stops"]["carbon"] == [20, 50, 100]
   and [g["label"] for g in CB["legend"][:4]] == ["under 20 t", "20 to 49 t", "50 to 99 t", "100 t and over"]
   and all(t in HTML_TEXT_B for t in ("under 20 t", "20 to 49 t", "50 to 99 t", "100 t and over"))
   and "under 20 t" in T10BJ and "100 t and over" in T10BJ, str(CB["stops"]))
_DB = {d["name"]: d for d in CB["districts"]}
ok("⭐ W12: each district's colour is its step on the SCHEME's bands (the same tonnes, a different step from the default)",
   all(d["fill"] == bulletin_doc.COUNCIL_RAMP[sum(1 for x in (20, 50, 100) if d["co2_t"] >= x)]
       for d in CB["districts"] if d["cls"] not in ("none", "nofig"))
   and all(_DB[n]["co2_t"] == _D[n]["co2_t"] for n in _D), str([(d["name"], d["co2_t"], d["cls"]) for d in CB["districts"]]))
ok("W12: the movements section reads the movements bands (default here: 50 / 100 / 200 a day, the map's blue)",
   MB["stops"] == [50, 100, 200] and [g["fill"] for g in MB["legend"][:4]] == list(bulletin_doc.COUNCIL_RAMP_MOVEMENTS)
   and [g["label"] for g in MB["legend"][:4]] == ["under 50", "50 to 99", "100 to 199", "200 and over"])
_mrm = re.search(r"const AREA_RAMP = \[([^\]]+)\];", MAP)
ok("⭐ W13 held equal: the movements colours are the map's AREA_RAMP (the plan blue in four steps)",
   bool(_mrm) and list(bulletin_doc.COUNCIL_RAMP_MOVEMENTS) == [x.strip().strip("'") for x in _mrm.group(1).split(",")])
ok("🔴 W12 source: neither reader works the bands out from the data (no max, no quantiles)",
   not re.search(r"max\(|quantile|percentile", read("backend/config.py").split("def council_breaks(")[1].split("\ndef ")[0])
   and "_stops()" in read("backend/areas.py") and "council_stops(" in read("backend/bulletin_doc.py"))

# W13 — movements by council
_DM = {d["name"]: d for d in MB["districts"]}
_mv10 = LOADS / WD
_mv11 = (20000 / PAY_ART + 29000 / PAY_ART) / WD
ok("⭐ W13 (hand): Eastshire and Westvale each carry BOTH routes' loads ÷ working days (both laden legs enter them) = the "
   "scheme's 98 a day; Farmoor none",
   near(_DM["Eastshire"]["a_day"], _mv10, 0.01) and near(_DM["Westvale"]["a_day"], _mv10, 0.01)
   and _DM["Eastshire"]["text"] == f"{_mv10:,.0f}" == "98" and _DM["Farmoor"]["text"] == "no approved laden route"
   and _DM["Farmoor"]["fill"] == "#E7E5E4" and _DM["Eastshire"]["routes"] == 2, str([(d["name"], d["a_day"], d["text"]) for d in MB["districts"]]))
ok("⭐ W13: the double count — the districts add up to MORE than the scheme, no total row, and the footnote says why in the "
   "map's own words (areas.DOUBLE_COUNT)",
   _DM["Eastshire"]["a_day"] + _DM["Westvale"]["a_day"] > H["two_way_a_day"]
   and MB["footnote"].startswith(areas.DOUBLE_COUNT) and MB["scheme_line"] == "Whole scheme: 98 two-way movements a day."     # NARROWED 14 Oct 2026
   and areas.DOUBLE_COUNT in _A10["basis"])
ok("⭐ W13 held equal: the map's district card says the same rule (the first clause of areas.DOUBLE_COUNT, word for word)",
   "a route counts in every area its laden leg enters" in MAP
   and areas.DOUBLE_COUNT.startswith("A route counts in every area its laden leg enters"))
ok("W13: lorry-km are the map's (areas.area_load lorry_km, laden and empty on the roads inside); Eastshire:Westvale = 5:3",
   all(near(_DM[a["name"]]["distance"], a["lorry_km"], 0.05) for a in _A10["areas"] if a["tier"] == "district")
   and near(_DM["Eastshire"]["distance"] / _DM["Westvale"]["distance"], 5 / 3, 0.01) and MB["distance_head"] == "Lorry-km in the month")
_DMM = {d["name"]: d for d in S10M["council_mv"]["districts"]}
ok("⭐ W13: a miles tenant reads lorry-miles (the km ÷ 1.609344), headed so",
   S10M["council_mv"]["distance_head"] == "Lorry-miles in the month"
   and near(_DMM["Eastshire"]["distance"], _DM["Eastshire"]["distance"] / 1.609344, 0.01)
   and "Lorry-miles: loaded and empty" in S10M["council_mv"]["footnote"])      # NARROWED 14 Oct 2026: plain "loaded"
_DM11 = {d["name"]: d for d in S11B["council_mv"]["districts"]}
ok("⭐ W13 (hand): the change since last month on the WHOLE figures printed — October 98 → November 77 is 'down 21'; "
   "September had none, so October reads 'new this month'",
   f"{_mv11:,.0f}" == "77" and _DM11["Eastshire"]["text"] == "77" and _DM11["Eastshire"]["change"] == "down 21"
   and _DM["Eastshire"]["change"] == "new this month" and _DM["Farmoor"]["change"] == "—"
   and S11B["council_mv"]["change_head"] == "Change since October 2026", str((_DM11["Eastshire"], _DM["Eastshire"]["change"])))
_cw_ = bulletin_doc._change_words
ok("W13: the change words — up / down / no change / new / none this month, never a bare sign",
   _cw_(98.4, 77.4) == "up 21" and _cw_(77.2, 98.1) == "down 21" and _cw_(10.2, 9.8) == "no change"
   and _cw_(5, 0) == "new this month" and _cw_(0, 7.6) == "none this month (was 8)" and _cw_(0, 0) == "—"
   and _cw_(0.3, 0) == "new this month" and bulletin_doc._mv(0.3) == "under 1")
ok("⭐ W13 page: the table (district, movements, routes, lorry distance, change), the blue legend, the scheme line, the footnote",
   '<table data-bulletin="council-movements">' in HTML10B and "Movements by council in October 2026" in HTML_TEXT_B
   and "Change since September 2026" in HTML_TEXT_B and "Lorry-km in the month" in HTML_TEXT_B
   and 'data-bulletin="double-count">' + areas.DOUBLE_COUNT.replace("'", "&#x27;") in HTML10B
   and "Whole scheme: 98 two-way movements a day." in HTML_TEXT_B       # NARROWED 14 Oct 2026
   and HTML10B.index("Movements by council") < HTML10B.index("Carbon by council"))
ok("⭐ W13 PDF: the section's title, each district with its figure and change, the scheme line and the double-count footnote",
   "Movements by council in October 2026" in T10BJ and "new this month" in T10BJ and "no approved laden route" in T10BJ
   and "Whole scheme: 98 two-way movements a day." in T10BJ and areas.DOUBLE_COUNT in T10BJ       # NARROWED 14 Oct 2026
   and T10BJ.index("Movements by council") < T10BJ.index("Carbon by council"))
ok("⭐ W13 PDF: 'fictional demo scheme' on every page, with both council sections in",
   all("fictional demo scheme" in p.lower() for p in T10B.split("\f") if p.strip()))
ok("🔴 W13: the banned-word scan and the UK words over both council sections, page and PDF",
   not _BANNED.search(T10BJ + " " + HTML_TEXT_B) and not re.search(r"\bAI\b", T10BJ + " " + HTML_TEXT_B)
   and not _trucks(T10BJ + " " + HTML_TEXT_B))
ok("🔴 W13: no district is ever printed with a fraction of a movement (whole movements on public pages, 12 Oct)",
   all(re.fullmatch(r"[\d,]+|under 1|no figure yet|empties only|no approved laden route", d["text"]) for d in MB["districts"] + S11B["council_mv"]["districts"]))
_px_b = [int(x) for x in re.findall(r"(?:font-size:|font:(?:\d{3} )?)(\d+)px", HTML10B)]
ok("🔴 the 14 px floor holds with both council sections and the map legend", _px_b and min(_px_b) >= 14, str(sorted(set(_px_b))))
ok("🔴 the literal-22 ban and the no-SQL rule still hold for the composition with bundle B",
   "22" not in read("backend/bulletin_doc.py") and "db." not in read("backend/bulletin_doc.py"))
# 13 Oct 2026 (found by LOOKING at the rendered PDF, not by a harness): equal legend slots let "no approved laden
# route" run into the next swatch and cut the title; the caption ran off page 1. Both measured here.
from reportlab.pdfbase.pdfmetrics import stringWidth as _sw  # noqa: E402
from reportlab.lib.units import mm as _mm  # noqa: E402
_U = 210 * _mm - 28 * _mm


def _legend_overlaps(dr):
    """[(end of one label, start of the next swatch)] where a label runs into the next item, or past the width."""
    strs = [x for x in dr.contents if type(x).__name__ == "String"]
    rects = sorted(x.x for x in dr.contents if type(x).__name__ in ("Rect", "Group") and getattr(x, "x", None) is not None)
    bad = []
    title = strs[0]
    if title.x + _sw(title.text, title.fontName, title.fontSize) > rects[0]:
        bad.append(("title", title.text))
    labels = strs[1:]
    for i, lb in enumerate(labels):
        end = lb.x + _sw(lb.text, lb.fontName, lb.fontSize)
        # 14 Oct 2026: a legend may run on to a second row; the next swatch is only "next" on the same row
        nxt = labels[i + 1].x - 10.5 if i + 1 < len(labels) and labels[i + 1].y == lb.y else _U
        if end > nxt:
            bad.append((lb.text, round(end, 1), round(nxt, 1)))
    return bad


# NARROWED 14 Oct 2026 (the publishing check): margins 15 mm (the page is 180 mm wide inside), legends at 7.5 pt (they
# shrank to 5.5), and the route map's legend measured too
_U = 210 * _mm - 30 * _mm
ok("🔴 the PDF legends never overlap: the title before the first swatch, each label before the next swatch, the row inside the page",
   _legend_overlaps(export._council_legend(MB, _U, "Two-way movements a day:")) == []
   and _legend_overlaps(export._council_legend(CB, _U)) == []
   and _legend_overlaps(export._volume_legend(S10, _U)) == []
   and min(x.fontSize for x in export._council_legend(CB, _U).contents if type(x).__name__ == "String") >= 7.0
   and min(x.fontSize for x in export._volume_legend(S10, _U).contents if type(x).__name__ == "String") >= 7.5,
   str((_legend_overlaps(export._council_legend(MB, _U, "Two-way movements a day:")), _legend_overlaps(export._council_legend(CB, _U)))))
# NARROWED 14 Oct 2026 (the publishing check): the caption is ONE short line (the credit, or "not to scale"), right
# under the map; the map has its own title above it
_cap = export._BulletinMapCaption(types.SimpleNamespace(kind="schematic"), 19)
ok("🔴 the map caption is one short line inside the page width; the schematic says it is not to scale",
   _cap.height < 8 * _mm and _sw("Schematic from the stored road routes, not to scale.", "Helvetica", 7.5) <= _U
   and "Schematic from the stored road routes, not to scale." in T10J and "(no map tiles)" not in T10J)

# 13 Oct 2026 (seen at 375 px in the built-in browser): the colour square wrapped above "Harborough"; it is now held to its name
ok("🔴 both council tables keep each colour square beside its district name on a phone (inline-flex, the square never shrinks)",
   HTML10B.count('<td><span class="dn"><span class="sw"') == 2 * len(MB["districts"])
   and ".dn{display:inline-flex;align-items:baseline} .dn .sw{flex:none}" in HTML10B)

# one areas read per month: sheet() reads this month once (both sections) and last month once
_calls_al = []


def _al_count(*a, **k):
    _calls_al.append((a, k.get("geometry")))
    return _real_al(*a, **k)


areas.area_load = _al_count
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    bulletin_doc.sheet(10, PLANNER)
finally:
    areas.area_load = _real_al
    config.tenant_settings = _real_ts4
ok("W13: one areas read for this month (with the polygons, for both sections) and one for last month (figures only)",
   [(a[0], g) for a, g in _calls_al] == [(10, True), (9, False)], str(_calls_al))
# a failed read: both sections stay, each says so
areas.area_load = _al_boom
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    S10E = bulletin_doc.sheet(10, PLANNER)
finally:
    areas.area_load = _real_al
    config.tenant_settings = _real_ts4
ok("🔴 W13: a failed areas read keeps BOTH council sections and each says the figures could not be read",
   S10E["council_mv"]["error"] == "The council figures could not be read for October 2026 (RuntimeError)."
   and S10E["council"]["error"] == S10E["council_mv"]["error"]
   and "could not be read" in bulletin_doc._council_mv_html(S10E["council_mv"]))
ok("🔴 W13: no districts, no movements section (the bulletin without council areas)",
   S10["council_mv"] is None and "Movements by council" not in T10J and 'data-bulletin="council-movements"' not in HTML10)
# put the default back for what follows
_doc2 = json.loads(json.dumps(_doc0)); config.save(_doc2, by="harness"); config.invalidate()

# --------------------------------------------------------------------------- #
#  8d. 13 Oct 2026 — BUNDLE C1: "Is it a lot?" (W14, D40, D44)                  #
# --------------------------------------------------------------------------- #
import comparisons  # noqa: E402
import carbon_target  # noqa: E402
_F = comparisons.factors()
ok("⭐ one table of comparison factors: every entry has a source, a year, the day it was checked and a next edition; the "
   "values are the sources' (DESNZ 2026 average car 0.16591 kg/km, row 4_301_3074_4_1; NTS0901a 7,100 miles, 2025; ±15 %)",
   set(_F) == {"car_kg_co2e_per_km", "car_miles_a_year", "car_range_pct", "la_road_transport"}
   and all(all(k in v for k in ("value", "unit", "what", "source", "year", "url", "checked_on", "next_edition")) for v in _F.values())
   and _F["car_kg_co2e_per_km"]["value"] == 0.16591 and "4_301_3074_4_1" in _F["car_kg_co2e_per_km"]["source"]
   and _F["car_kg_co2e_per_km"]["year"] == 2026 and _F["car_miles_a_year"]["value"] == 7100 and _F["car_miles_a_year"]["year"] == 2025
   and "NTS0901a" in _F["car_miles_a_year"]["source"] and _F["car_range_pct"]["value"] == 15 and _F["la_road_transport"]["year"] == 2024
   and all(v["checked_on"] == "2026-10-13" for v in _F.values()))
_LT = comparisons.la_table()
ok("⭐ the DESNZ 2024 road transport file: 362 councils, Table 1.1, published 25 June 2026, OGL v3 attribution; Harborough "
   "(E07000131) 69.620 / 130.173 / 85.682 kt (A / motorways / minor) as read 13 Oct; Melton has no motorway",
   len(_LT["rows"]) == 362 and _LT["year"] == 2024 and _LT["published"] == "2026-06-25"
   and _LT["table"].startswith("Table 1.1: Local authority territorial greenhouse gas emissions estimates 2005-2024 (kt CO2e)")
   and _LT["attribution"] == "Contains public sector information licensed under the Open Government Licence v3.0."
   and _LT["rows"]["E07000131"] == ["Harborough", 69.62, 130.173, 85.682] and _LT["rows"]["E07000133"][2] == 0
   and _LT["columns"] == ["name", "a_roads_kt", "motorways_kt", "minor_roads_kt"])
ok("🔴 no factor is typed outside the table: comparisons.py carries none of the outside figures",
   not re.search(r"0\.16591|7,?100\b|\b15\b", read("backend/comparisons.py").split('"""', 2)[2]))
# cars, by hand
_carm = 7100 * 1.609344 * 0.16591 / 12
_eq = comparisons.car_equivalents(384.2)
ok("⭐ cars (hand): one car-month = 7,100 mi × 1.609344 × 0.16591 ÷ 12 = 158 kg; 384.2 t = 2,431 cars → 'about 2,100–2,800' "
   "(±15 %, two significant figures); never one exact figure",
   abs(comparisons.car_month_kg() - _carm) < 1e-9 and abs(_carm - 157.98) < 0.01 and _eq["low"] == 2100 and _eq["high"] == 2800
   and _eq["words"] == "about 2,100–2,800 average cars driven for a month", str(_eq))
ok("cars: small figures and none — 'less than one', a single figure when both ends round alike, None for no carbon",
   comparisons.car_equivalents(0.05)["words"] == "less than one average car driven for a month"
   and comparisons.car_equivalents(None) is None and comparisons.car_equivalents(0) is None
   and comparisons.sig2(2431) == 2400 and comparisons.sig2(96.4) == 96 and comparisons.sig2(7.3) == 7)
# the council share, by hand on the real table
_sh = comparisons.la_share("E07000131", 150.0)
ok("⭐ council share (hand): Harborough 150 t ÷ ((69.620 + 130.173 + 85.682) kt × 1000 ÷ 12) = 0.63 % — all roads, motorways "
   "included, and it says the motorway question is open; Melton (no motorway) says A and minor roads",
   abs(_sh["pct"] - 100 * 150 / (285.475 * 1000 / 12)) < 1e-9 and _sh["pct_words"] == "0.6%" and _sh["has_motorway"]
   and _sh["roads"] == "all roads, motorways included; whether these lorries used one is not yet known"
   and comparisons.la_share("E07000133", 10)["roads"] == "A and minor roads: the government figures give no motorway in the district"
   and comparisons.la_share("E1", 10) is None and comparisons.la_share("E07000131", None) is None)
ok("council share words: under 0.1 % never reads 'about under'; one decimal under 10 %; whole from 10 %",
   comparisons.about("under 0.1%") == "under 0.1%" and comparisons.about("0.6%") == "about 0.6%"
   and comparisons.pct_words(0.04) == "under 0.1%" and comparisons.pct_words(12.4) == "12%" and comparisons.pct_words(3.25) == "3.2%")
# the panel on the fixture (no target set here; the fixture's districts carry test codes, so the council row falls back)
LOT10 = S10A["lot"]
_c10 = S10A["rollup"]["carbon"]["co2_t_in_month"]
_L = {r["label"]: r for r in LOT10["rows"]}
ok("⭐ the panel: six rows in the brief's order, titled 'Is <n> t CO2e a lot?' with the month's haul carbon",
   [r["label"] for r in LOT10["rows"]] == ["Against the plan", "Against last month", "Against the target",
                                           "The council's figures", "In everyday terms", "Per tonne, per movement"]
   and LOT10["title"] == f"Is {_tt(_c10)} of CO2e a lot?" and _c10 > 0, str([r["label"] for r in LOT10["rows"]]))
ok("⭐ row 1: NOT REPORTED — the bulletin is the plan; no measured carbon is invented to set against it",
   # NARROWED 14 Oct 2026 (the publishing check): one plain sentence
   _L["Against the plan"]["text"] == "Not reported: nothing was counted, so there is no measured carbon to compare with the plan."
   and _L["Against the plan"]["status"] is None)
ok("⭐ row 2 (hand): September had no approved haul, so October says so (never a % of nothing)",
   _L["Against last month"]["text"] == "There was no approved haul in September 2026.")
_c11 = S11B["rollup"]["carbon"]["co2_t_in_month"]
_r2_11 = next(r for r in S11B["lot"]["rows"] if r["label"] == "Against last month")["text"]
ok("⭐ row 2 (hand): November against October = (c11 − c10) ÷ c10, in words, with both tonnages",
   _r2_11 == f"{abs(100 * (_c11 - _c10) / _c10):.0f}% {'more' if _c11 > _c10 else 'less'} than October 2026 ({_tt(_c11)} against {_tt(_c10)}).", _r2_11)
ok("⭐ row 3: no target in the fixture — 'No carbon target set yet.', never 0 %",
   _L["Against the target"]["text"] == "No carbon target set yet." and "%" not in _L["Against the target"]["text"])
ok("row 4: the fixture's districts are not in the government table, so the row says so by name and code (never a guess)",
   _L["The council's figures"]["text"] == "No government figure for Eastshire (code E1).")
ok("⭐ row 5 (hand): the month's tonnes as cars driven for a month, the range from the table",
   # NARROWED 14 Oct 2026 (the publishing check): the figure is in the title; "exhaust only" is the plain word for tailpipe
   _L["In everyday terms"]["text"] == (comparisons.car_equivalents(_c10)['words'][0].upper() + comparisons.car_equivalents(_c10)['words'][1:]
                                       + " (exhaust only, as for the lorries).")
   and "0.16591 kg CO2e per km" in _L["In everyday terms"]["source"] and "7,100 miles a car in 2025" in _L["In everyday terms"]["source"]
   and "15% either side" in _L["In everyday terms"]["source"])
ok("⭐ row 6 (hand): kg CO2e per tonne (÷ 60,400 t) and per two-way movement (÷ the month's loads)",
   _L["Per tonne, per movement"]["text"] == f"{1000 * _c10 / 60400:,.1f} kg CO2e per tonne moved and {1000 * _c10 / LOADS:,.0f} kg per two-way movement.")
# NARROWED 13 Oct 2026 (the rendered smoke month): a council row with NO figure carries no source line; with one, it does
ok("⭐ every row with a figure carries its source; the outside rows name their publisher and year; no file path is printed; a "
   "council row with no figure has no source line",
   all(r["source"] and r["source"] != "—" for r in LOT10["rows"][1:] if r["label"] != "The council's figures")
   and _L["The council's figures"]["source"] == "—" and "2026" in _L["In everyday terms"]["source"]
   and not any("backend/" in r["source"] or ".json" in r["source"] for r in LOT10["rows"]))
ok("the demo tenant says the plan, target and tonnes are invented and the government figures real",
   LOT10["demo_note"] == "Fictional demo scheme: the plan, the target and the tonnes are invented; the government figures they are set beside are real.")
# the council row and the table column on a table that knows the fixture's codes
_saved_la = comparisons._CACHE.get(comparisons.LA_PATH)
comparisons._CACHE[comparisons.LA_PATH] = dict(_LT, rows={"E1": ["Eastshire", 12.0, 0, 12.0], "W1": ["Westvale", 6.0, 6.0, 6.0]})
try:
    _CK = bulletin_doc._council_carbon(10, WD, "October 2026")
    _LK = bulletin_doc._lot(10, "October 2026", "September 2026", S10A["rollup"], None, H, _CK, PLANNER, False)
finally:
    comparisons._CACHE[comparisons.LA_PATH] = _saved_la
_DK = {d["name"]: d for d in _CK["districts"]}
_LKs = next(r for r in _LK["rows"] if r["label"] == "The council's figures")["source"]
ok("...and a council row WITH a figure names DESNZ 2024, Table 1.1 and the OGL", "2024" in _LKs and "DESNZ" in _LKs
   and "Table 1.1" in _LKs and "Open Government Licence v3.0" in _LKs)
_eK = 100 * _DK["Eastshire"]["co2_t"] / (24.0 * 1000 / 12)
ok("⭐ row 4 (hand, a table that knows the codes): the district with the most haul carbon against a month of ITS figures, "
   "'about', with the road basis; no motorway → A and minor roads",
   next(r for r in _LK["rows"] if r["label"] == "The council's figures")["text"]
   # NARROWED 14 Oct 2026 (the publishing check): the road basis in three words; the table is on the page before
   == f"In Eastshire, {_tt(_DK['Eastshire']['co2_t'])} is {comparisons.about(comparisons.pct_words(_eK))} of a month of all road "
      "transport CO2e in the district (2024; A and minor roads).")
# NARROWED 13 Oct 2026 (the rendered newsletter: "(A and minor)" wrapped the narrow column): a † and one footnote
ok("⭐ the council table's for-scale column: each district against a month of its own road transport; † where no "
   "motorway (one footnote says so); '—' with no haul; 'no government figure' when the code is not in the table",
   _DK["Eastshire"]["la_share"] == comparisons.about(comparisons.pct_words(_eK)) + " †"
   and _DK["Westvale"]["la_share"] == comparisons.about(comparisons.pct_words(100 * _DK["Westvale"]["co2_t"] / (18.0 * 1000 / 12)))
   and _DK["Farmoor"]["la_share"] == "—" and _D["Eastshire"]["la_share"] == "no government figure")
# D44 — the monthly allowance, by hand, on a stubbed target (the real one is held by test_carbon_target)
_real_get, _real_status = carbon_target.get, carbon_target.status
_seen_acc = []


def _status_stub(acc, t, factors=None):
    _seen_acc.append(acc)
    return {"approved_t": 400.0, "target_t": 100.0, "invalid": None,
            "by_month": [{"month_index": 10, "approved_t": 120.0, "with_decisions_t": 25.0},
                         {"month_index": 11, "approved_t": 280.0, "with_decisions_t": 80.0}]}


carbon_target.get = lambda: {"mode": "cap", "cap_t": 100.0}
carbon_target.status = _status_stub
try:
    _T10 = bulletin_doc._target_row(10, "October 2026", {"role": "submitter", "ipt": "IPT2"})
    _T11 = bulletin_doc._target_row(11, "November 2026", None)
finally:
    carbon_target.get, carbon_target.status = _real_get, _real_status
ok("⭐ D44 (hand): October's allowance = target 100 × 120 ÷ 400 = 30 t; 25 t all-in with the decisions is WITHIN it (word + colour)",
   abs(_T10["allowance_t"] - 30.0) < 1e-9 and _T10["month_t"] == 25.0 and _T10["status"] == "Within the allowance" and _T10["status_ok"]
   # NARROWED 14 Oct 2026 (the publishing check): the panel's title names the month
   and _T10["text"].startswith("25 t CO2e all-in with the agreed decisions, against an allowance of 30 t."), _T10["text"])
ok("⭐ D44 (hand): November's allowance = 100 × 280 ÷ 400 = 70 t; 80 t is OVER by 10 t, said in words",
   abs(_T11["allowance_t"] - 70.0) < 1e-9 and _T11["status"] == "Over the allowance" and not _T11["status_ok"]
   and "against an allowance of 70 t: 10 t over." in _T11["text"])
ok("🔴 the target row is ALL-IN and says so beside the haul figures; it reads the scheme's target even for a team code (D37)",
   "All-in includes making the material, so it is larger than the haul figures." in _T10["text"]     # NARROWED 14 Oct 2026
   and _seen_acc[0].get("ipt") is None and _seen_acc[0].get("role") == "submitter")
_P10K = export.build_bulletin_pdf(dict(S10A, lot=dict(LOT10, rows=LOT10["rows"][:2] + [_T11] + LOT10["rows"][3:])))
_T10KJ = " ".join(pdf_text(_P10K).split())
# NARROWED 14 Oct 2026 (the publishing check): each row's source is a reference number into one Sources list (no
# "Source:" line under every row); the sources are all still printed, once
# NARROWED 14 Oct 2026: the title and labels as printed, CO₂e with its subscript
_SUB = lambda t: t.replace("CO2e", "CO₂e")
ok("⭐ the panel in the PDF: the title, each row's label, the status word, every source (once, numbered) and the demo note",
   _SUB(LOT10["title"]) in _T10KJ and all(_SUB(r["label"]).upper() in _T10KJ for r in LOT10["rows"]) and "Over the allowance" in _T10KJ
   and "Source:" not in _T10KJ.split("Is ")[1].split("This month at a glance")[0]
   and all(isinstance(r.get("ref"), int) for r in LOT10["rows"] if r["source"] != "—")
   and "Source: DfT National Travel Survey" not in _T10KJ.replace("; DfT National Travel Survey", "")
   and "NTS0901a" in _T10KJ and "Table 1.1" in _T10KJ and "Fictional demo scheme: the plan, the target and the tonnes are invented" in _T10KJ
   and "Factors checked 13 October 2026." in _T10KJ)
_H10A = bulletin_doc.html(dict(S10A, lot=dict(LOT10, rows=LOT10["rows"][:2] + [_T10] + LOT10["rows"][3:])))
ok("⭐ the panel on the page: its own section after the council sections, the status word with its colour AND its word and mark",
   'data-bulletin="lot"' in _H10A and _H10A.index("Carbon by council") < _H10A.index('data-bulletin="lot"')
   and '<b class="lot-st" style="color:#047857">✓ Within the allowance</b>' in _H10A and "Is " in _H10A and "a lot?" in _H10A)
ok("🔴 the panel's status colours are 4.5:1 or better on white (the dark green and the dark amber), never colour alone",
   bulletin_doc.STATUS_OK == "#047857" and bulletin_doc.STATUS_OVER == "#B45309")
_TXT_LOT = " ".join(r["text"] + " " + r["source"] for r in LOT10["rows"]) + _T10KJ
ok("🔴 the banned-word scan and the UK words over the panel; no trees, flights or households",
   not _BANNED.search(_TXT_LOT) and not _trucks(_TXT_LOT) and not re.search(r"\b(trees?|flights?|households?)\b", _TXT_LOT, re.I))
ok("🔴 no haul carbon figure → no panel (nothing to compare), and no section on page or PDF",
   bulletin_doc._lot(10, "October 2026", None, {"carbon": {"co2_t_in_month": None}}, None, H, None, PLANNER, False) is None
   and bulletin_doc._lot_html(None) == "")

# decision 2a: the road-class probe — plumbing only, against STUBS (what HERE really returns is the unknown it exists for)
import here_routing  # noqa: E402
import io as _io  # noqa: E402
import urllib.error as _ue  # noqa: E402
_saved_key = os.environ.pop("HERE_API_KEY", None)
_rc0 = here_routing.road_class_probe(52.5, -1.0, 52.6, -1.1, ART)
ok("🔴 road-class probe: no key → says so and calls nothing", _rc0.get("error") == "HERE_API_KEY is not set on the server"
   and _rc0["params_sent"]["spans"] == "functionalClass,routeNumbers,length" and "apiKey" not in _rc0["params_sent"])
os.environ["HERE_API_KEY"] = "harness-key"
_rc_urls = []


def _here_refuses(url, timeout=0):
    _rc_urls.append(url)
    raise _ue.HTTPError(url, 400, "Bad Request", {}, _io.BytesIO(b'{"title":"Malformed request","cause":"spans: unknown value"}'))


class _Resp:
    def __init__(self, body):
        self._b = body

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _here_spans(url, timeout=0):
    _rc_urls.append(url)
    return _Resp(json.dumps({"routes": [{"sections": [{"polyline": "x", "summary": {"length": 3000}, "spans": [
        {"offset": 0, "functionalClass": 1, "routeNumbers": [{"value": "M1"}], "length": 2000},
        {"offset": 5, "functionalClass": 3, "routeNumbers": [{"value": "A6"}], "length": 1000}]}]}]}).encode())


_real_uo = here_routing.urllib.request.urlopen
try:
    here_routing.urllib.request.urlopen = _here_refuses
    _rc1 = here_routing.road_class_probe(52.5, -1.0, 52.6, -1.1, ART)
    here_routing.urllib.request.urlopen = _here_spans
    _rc2 = here_routing.road_class_probe(52.5, -1.0, 52.6, -1.1, ART)
finally:
    here_routing.urllib.request.urlopen = _real_uo
    os.environ.pop("HERE_API_KEY", None)
    if _saved_key is not None:
        os.environ["HERE_API_KEY"] = _saved_key
ok("⭐ road-class probe (stub): the request asks for spans=functionalClass,routeNumbers,length with the truck parameters; "
   "a refusal reports HERE's own error body, never raises",
   "spans=functionalClass%2CrouteNumbers%2Clength" in _rc_urls[0] and "vehicle" in _rc_urls[0]
   and _rc1["error"].startswith("HTTP 400:") and "spans: unknown value" in _rc1["error"])
ok("road-class probe (stub): spans that come back are reported raw, with the length per class and the M-numbers",
   _rc2["spans_returned"] == 2 and _rc2["length_m_by_functional_class"] == {"1": 2000, "3": 1000}
   and _rc2["route_numbers_starting_M"] == ["M1"] and "functionalClass" in _rc2["span_keys"]
   and _rc2["reads_as"].startswith("HERE returned spans"))
_MAINSRC = read("backend/main.py")
ok("🔴 the endpoint is admin-only, costs one HERE call and stores nothing; nothing in the bulletin reads its answer",
   '@app.get("/api/admin/diagnostics/road-class/{route_id}")' in _MAINSRC
   and _MAINSRC.split('def diagnostics_road_class(')[1].split('return network.road_class_diagnostics(')[0].count("_check_admin(token)") == 1
   and "road_class" not in read("backend/bulletin_doc.py") and "road_class" not in read("backend/comparisons.py").split('"""', 2)[2]
   and "db.execute" not in read("backend/network.py").split("def road_class_diagnostics(")[1].split("\ndef ")[0])

# --------------------------------------------------------------------------- #
#  8e. 13 Oct 2026 — BUNDLE C2: the newsletter (4 pages), the leaflet (1 page),  #
#      the brand (W15), the D41 tag                                              #
# --------------------------------------------------------------------------- #
import brand_pdf  # noqa: E402
_pages = lambda pdf: [" ".join(x.split()) for x in pdf_text(pdf).split("\f") if x.strip()]
_PB = _pages(PDF10B)
ok("⭐ D43 the newsletter is FOUR pages — with council areas (S10B) and without (S10) — each page one numbered section, in order",
   len(PAGES) == 4 and len(_PB) == 4
   and all(k in _PB[i] for i, k in enumerate(("01 THE MONTH IN BRIEF", "02 ROUTES AND ROADS", "03 COUNCILS", "04 CARBON AND THE SMALL PRINT")))
   and "03 CARBON" in PAGES[2] and "Is " in PAGES[2] and "a lot?" in PAGES[2], str([len(PAGES), len(_PB)]))
# NARROWED 14 Oct 2026 (the publishing check): page 1 is the front page — the lede, the four figures, the definition, the
# map with its title, legend and key, the key points, how to report a lorry; the glance moved to page 4
ok("⭐ page 1 reads on its own: the lede, the four figures, the definition, the map and its legend and key, Key points, how to report a lorry",
   all(t in _PB[0] for t in ("The lorries Wolds Link (fictional) plans for October 2026: how many, where they go, and their carbon.",
                             bulletin_doc.DEFINITION, "Planned lorry routes, October 2026", "Two-way movements a day:",
                             "SITES", "ROAD WORKS AND LIMITS", "Key points", "Report a lorry off route"))
   and "This month at a glance" not in _PB[0] and all(f["value"] in _PB[0] for f in S10B["headline"]))
# NARROWED 14 Oct 2026 (the publishing check): what changed closes page 2; page 4 is the panel, the glance, the four
# terms, caveats, the numbered Sources (the council method notes are in them) and the report box
ok("⭐ page 3 holds both council sections; page 4 the panel, the glance, terms, caveats, Sources, the report box",
   "Movements by council in October 2026" in _PB[2] and "Carbon by council in October 2026" in _PB[2]
   and "What changed since last month" in _PB[1]
   and all(t in _PB[3] for t in ("a lot?", "This month at a glance", "Terms", "Caveats", "Sources"))
   and "Large print and other formats" in _PB[0] and "Large print and other formats" not in _PB[3]
   and "Carbon by council: how it is worked out" not in T10BJ and "Terms explained" not in T10BJ)
# NARROWED 14 Oct 2026 (the publishing check): the full band on page 1 only; pages 2 on carry a slim running head (the
# title and "<scheme> · monthly newsletter"); the demo bar and the foot on every page, which says "n of 4"
ok("⭐ W15 the brand band on page 1 (title, scheme, 'monthly newsletter', as-at stamp, issue date); a running head with the title "
   "on every later page; the demo bar on every page; the foot with wayscope.co.uk and 'n of 4'",
   all("Issued" in pg[0] and "Approved plan as at" in pg[0] for pg in (_PB, PAGES))
   and all("Issued" not in pg for pg in _PB[1:] + PAGES[1:])
   and all("Lorry movements bulletin · October 2026" in pg and "monthly newsletter" in pg
           and "Fictional demo scheme · nothing here is real" in pg and "wayscope.co.uk" in pg for pg in _PB + PAGES)
   and all(f"{i} of 4" in pg for i, pg in enumerate(_PB, 1)))
def _shown_fonts(pdf):
    """The fonts text is actually SHOWN in: per BT…ET block that shows text (Tj / TJ), the font set last before it.
    (reportlab writes empty font switches in its preambles — the page's initial Helvetica, a drawing's Times-Roman — that
    show nothing; they are not text in those fonts.)"""
    out = set()
    for blk in re.findall(rb"BT(.*?)ET", pdf, re.S):
        cur = None
        for m in re.finditer(rb"/(\S+) [\d.]+ Tf|(\)\s*Tj|\]\s*TJ)", blk):
            if m.group(1):
                cur = m.group(1)
            elif cur is not None:
                out.add(cur)
    return out


_SF = _shown_fonts(PDF10B)
ok("⭐ W15 Inter in the PDFs (embedded TrueType subsets): every piece of text the newsletter shows is in an embedded Inter "
   "subset — none in Helvetica or Times",
   b"Inter-Bold" in PDF10B and b"/FontFile2" in PDF10B and _SF and all(b"+" in f for f in _SF), str(_SF))
ok("⭐ W15 the logo is VECTOR: drawn from the brand SVG master, no image in an offline newsletter (the map is a schematic too)",
   b"/Subtype /Image" not in PDF10B and len(brand_pdf.logo_shapes()[1]) == 9
   and brand_pdf.logo_shapes()[0] == [15.0, 84.0, 1380.39, 263.0])
_ofl = read("backend/fonts/Inter-OFL.txt")
ok("🔴 the OFL ships beside the fonts (the licence's condition), three static TrueType files, no Reserved Font Name claimed",
   "SIL Open Font License, Version 1.1" in _ofl and "Copyright (c) 2016 The Inter Project Authors" in _ofl
   and sorted(f for f in os.listdir(os.path.join(BACKEND, "fonts")) if f.endswith(".ttf")) == ["Inter-Bold.ttf", "Inter-Italic.ttf", "Inter-Regular.ttf"]
   and all(open(os.path.join(BACKEND, "fonts", f), "rb").read(4) == b"\x00\x01\x00\x00" for f in ("Inter-Bold.ttf", "Inter-Italic.ttf", "Inter-Regular.ttf")))
# the SVG reader: an arc, a relative path, implicit repeats, a quadratic
_seg = brand_pdf.path_segments("M0,0 L10,0 A5,5 0 0 1 20,0 h5 v5 q1,1 2,2 Z m1,1 2,2")
ok("W15 the SVG path reader: absolute and relative moves, implicit linetos after a moveto, H/V, an arc into Béziers, Q into C, Z",
   _seg[0] == ("M", 0.0, 0.0) and _seg[1] == ("L", 10.0, 0.0) and _seg[2][0] == "C" and abs(_seg[-6 + 0][5] - 20) < 1e-6 if False else
   (_seg[0] == ("M", 0.0, 0.0) and _seg[1] == ("L", 10.0, 0.0) and any(x[0] == "C" for x in _seg)
    and ("L", 25.0, 0.0) in _seg and ("L", 25.0, 5.0) in _seg and ("Z",) in _seg and _seg[-1] == ("L", 3.0, 3.0)), str(_seg))
_arc = brand_pdf._arc_to_beziers(10, 0, 5, 5, 0, 0, 1, 20, 0)
ok("W15 an SVG arc (a half circle) becomes two Bézier quarters that end on the arc's end point",
   len(_arc) == 2 and abs(_arc[-1][4] - 20) < 1e-9 and abs(_arc[-1][5]) < 1e-9 and abs(_arc[0][5] - (-5)) < 1e-6 or abs(_arc[0][5] - 5) < 1e-6, str(_arc))
ok("🔴 the logo is filled with SVG's non-zero rule (even-odd punched holes where a letter's outlines overlap)",
   "fillMode=FILL_NON_ZERO" in read("backend/brand_pdf.py") and "FILL_NON_ZERO = 1" in read("backend/brand_pdf.py"))
# the leaflet
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
try:
    LF10 = export.build_bulletin_leaflet_pdf(S10)
    LF10B = export.build_bulletin_leaflet_pdf(S10B)
    LH10B = bulletin_doc.leaflet_html(S10B)
finally:
    config.tenant_settings = _real_ts4
_LP, _LPB = _pages(LF10), _pages(LF10B)
ok("⭐ D43 the leaflet is ONE page, with or without council areas",
   len(_LP) == 1 and len(_LPB) == 1, str([len(_LP), len(_LPB)]))
# NARROWED 14 Oct 2026 (the publishing check): the leaflet leads with a heading a resident reads first ("Lorries on your
# roads in <month>", which says what the lede said), the definition once, the map with its key, Key points; the placeholder
# reads "[link not set yet]"
ok("⭐ the leaflet: the band (leaflet), the demo bar, the heading, the four figures, the definition, the map and legend, Key points, "
   "how to report a lorry with the hours and other formats, and where to read the newsletter (a placeholder until typed)",
   all(t in _LPB[0] for t in ("Lorry movements bulletin · October 2026", "· leaflet ·", "Fictional demo scheme · nothing here is real",
                              "Lorries on your roads in October 2026", bulletin_doc.DEFINITION, "Two-way movements a day:",
                              "Key points", "Report a lorry off route", "Working hours:", "Large print and other formats:",
                              "Working hours: Monday to Friday 07:30-18:00.",
                              "Every route, the councils and the carbon are in the monthly newsletter: https://www.example.org/lorries"))
   and "(page 2)" not in _LPB[0] and "page 1" in _LPB[0]
   and all(f["value"] in _LPB[0] for f in S10B["headline"]) and b"Inter-Bold" in LF10B and all(b"+" in f for f in _shown_fonts(LF10B)))
# --------------------------------------------------------------------------- #
#  30 Oct 2026 (task 4b): the typed contact lines — Config -> Map and bulletin -> Contact lines
# --------------------------------------------------------------------------- #
_RL = bulletin_doc.report_lines
_LEAD = "Report a lorry off route: the date, time, place, direction and registration, "
ok("⭐ 4b the four states of the report box: nothing / address / address + phone / all typed",
   _RL({}) == {"lorry": _LEAD + "to [contact not set yet].", "hours": None, "formats": None}
   and _RL({"concern_email": "a@b.org"})["lorry"] == _LEAD + "to a@b.org."
   and _RL({"concern_email": "a@b.org", "contact_phone": "0116 000 0000"})["lorry"] == _LEAD + "to a@b.org or on 0116 000 0000."
   and _RL({"contact_phone": "0116 000 0000"})["lorry"] == _LEAD + "on 0116 000 0000."
   and _RL({"working_hours": "Mon-Fri 07:30-18:00.", "other_formats": "ask a@b.org"})["hours"] == "Working hours: Mon-Fri 07:30-18:00."
   and _RL({"other_formats": "ask a@b.org"})["formats"] == "Large print and other formats: ask a@b.org."
   and _RL({"working_hours": ""})["hours"] is None)
LH10 = bulletin_doc.leaflet_html(S10)
ok("⭐ 4b the leaflet page with nothing typed: the report gap only, no hours / formats / newsletter line, no 'not set yet' elsewhere",
   "[contact not set yet]" in LH10 and "Working hours" not in LH10 and "Large print" not in LH10
   and "monthly newsletter" not in LH10 and LH10.count("not set yet") == 1)
ok("🔴 4b the staff-only 'open it here' link is gone from the leaflet page, typed or not",
   "open it here" not in LH10 and "open it here" not in LH10B and "(staff)" not in LH10 + LH10B
   and "/bulletin/?month=" not in LH10B)
ok("⭐ 4b the leaflet page with every line typed: report, hours, formats, and the newsletter line with its link",
   "haulage.concerns@example.org or on 0116 000 0000." in LH10B and "Working hours: Monday to Friday 07:30-18:00." in LH10B
   and "Large print and other formats: email haulage.concerns@example.org." in LH10B
   and '<a href="https://www.example.org/lorries">https://www.example.org/lorries</a>' in LH10B
   and "not set yet" not in LH10B)
_LPJ = " ".join(_LP[0].split())
ok("⭐ 4b the leaflet PDF with nothing typed prints the gap only; with all typed (S10B) the hours, formats and link as text",
   "Working hours" not in _LPJ and "monthly newsletter" not in _LPJ and _LPJ.count("not set yet") == 1
   and "https://www.example.org/lorries" in " ".join(_LPB[0].split()) and "0116 000 0000" in " ".join(_LPB[0].split()))
ok("🔴 4b the newsletter's report box (page and PDF) follows the same lines; nothing typed leaves the other two out",
   HTML10B.count("Working hours: Monday to Friday 07:30-18:00.") == 2 and "Working hours" not in bulletin_doc.html(S10)
   and "Large print" not in bulletin_doc.html(S10))
# escaping: the typed text is plain text in the page (validation refuses < and >; the page escapes anyway)
_SE = dict(S10, report=_RL({"working_hours": "A & B", "concern_email": "a@b.org"}), newsletter_url="https://x.org/?a=1&b=2")
_LHE = bulletin_doc.leaflet_html(_SE)
ok("🔴 4b typed text is escaped in the leaflet page", "Working hours: A &amp; B." in _LHE and "A & B" not in _LHE
   and 'href="https://x.org/?a=1&amp;b=2"' in _LHE)
# the config side: validated on Save, cleaned when read
ok("⭐ 4b config: tenant_settings serves each typed line trimmed, None when empty or unusable; the defaults are None",
   all(config.TENANT_DEFAULTS[k] is None for k in ("contact_phone", "working_hours", "other_formats", "newsletter_url"))
   and config.tenant_settings(doc={"tenant": {"working_hours": "  Mon-Fri 08:00-18:00 ", "contact_phone": "0116 000 0000",
                                              "other_formats": "ask us", "newsletter_url": " https://www.x.org/l "}})["working_hours"] == "Mon-Fri 08:00-18:00"
   and config.tenant_settings(doc={"tenant": {"newsletter_url": "http://x.org"}})["newsletter_url"] is None
   and config.tenant_settings(doc={"tenant": {"working_hours": "a<b"}})["working_hours"] is None
   and config.tenant_settings(doc={"tenant": {"working_hours": "x" * 161}})["working_hours"] is None
   and config.tenant_settings(doc={})["other_formats"] is None)
_good = {"name": "x", "contact_phone": "0116 000 0000", "working_hours": "Mon-Fri", "other_formats": "ask",
         "newsletter_url": "https://www.example.org/lorries", "concern_email": "a@b.org"}
_bad4 = [("working_hours", "a<b"), ("working_hours", "x" * 161), ("other_formats", "line" + chr(10) + "break"), ("contact_phone", "1" * 41),
        ("newsletter_url", "http://x.org"), ("newsletter_url", "javascript:alert(1)"), ("newsletter_url", "https://x.org/a b"),
        ("newsletter_url", "https://"), ("newsletter_url", "https://nodot"), ("newsletter_url", "https://x.org/" + "a" * 300),
        ("working_hours", 5)]
_msgs = lambda t: config.validate(dict(json.loads(json.dumps(_doc0)), tenant=t))
ok("⭐ 4b config.validate: typed contact lines pass; HTML, line breaks, over-length, a non-https link and a bare host are refused",
   not [m for m in _msgs(_good) if any(k in m for k in ("phone number", "working hours", "large print", "newsletter link"))]
   and all(any((config.CONTACT_LABELS.get(f) or "newsletter link") in m for m in _msgs(dict(_good, **{f: v}))) for f, v in _bad4)
   and not [m for m in _msgs(dict(_good, contact_phone="", working_hours=None)) if "phone number" in m or "working hours" in m]
   and not any("tenant." in m or "null" in m for f, v in _bad4 for m in _msgs(dict(_good, **{f: v}))))   # plain words, no field names
ok("🔴 the leaflet: word ban, UK words, no team id or name", not _BANNED.search(_LPB[0]) and not _trucks(_LPB[0])
   and not ID_FORM.search(_LPB[0]) and "North Team" not in _LPB[0])
# NARROWED 14 Oct 2026 (the publishing check): bigger maps; the fit is found on sizing passes with no basemap, and
# the final build fetches it once. The newsletter's map is the biggest that keeps page 1 on its own page (it used to
# shrink until the WHOLE newsletter fitted four pages, so a long route table shrank the front-page map)
ok("🔴 the leaflet never spills: the map gives way first (100 → 90 → … → 50 mm), checked on the built page count, on sizing passes",
   "LEAFLET_MAP_HEIGHTS = (100 * mm, 90 * mm, 80 * mm, 70 * mm, 60 * mm, 50 * mm)" in _EXP
   and "if _leaflet(S, map_h)[1] <= 1:" in _EXP and "with _sizing():" in _EXP)
ok("🔴 the newsletter's page 1 never spills: its map gives way first (100 → … → 36 mm) until section 02 starts page 2",
   "NEWSLETTER_MAP_HEIGHTS = (100 * mm, 92 * mm, 84 * mm, 76 * mm, 68 * mm, 60 * mm, 52 * mm, 44 * mm, 36 * mm)" in _EXP
   and "if page2 == 2:" in _EXP and "return buf.getvalue(), doc.page, mark.page" in _EXP)
ok("🔴 a sizing pass fetches no basemap (the box is the same size either way); only the final build asks Mapbox",
   'if getattr(_SIZING, "on", False):\n        return None, None, None' in _EXP
   and _EXP.index("with _sizing():") < _EXP.index("return _newsletter(S, map_h, pages)[0]"))
# the brief, by hand
_BR = S10B["brief"]
# NARROWED 14 Oct 2026 (the publishing check): "Key points", shorter: no "laden legs", the district named as a district,
# the change said as up / down from last month
ok("⭐ Key points (hand): the busiest route with its flag, September empty, the works count, the busiest district, the carbon as cars",
   _BR == [f"Busiest route: {S10B['routes'][0]['label']}, {_r1:,.0f} two-way movements a day, above its planning flag of 60.",
           f"{_mv10:,.0f} two-way movements a day; no approved lorries in September 2026.",
           "3 road works, closures or local limits on or near the routes.",
           "Eastshire district sees the most: 98 two-way movements a day.",
           f"Haul carbon: {_tt(_c10)} CO2e, {comparisons.car_equivalents(_c10)['words']}."], str(_BR))
_BR11 = S11B["brief"]
ok("Key points (hand): November says its two-way movements a day, down from October's",
   f"{_mv11:,.0f} two-way movements a day, down from {_mv10:,.0f} in October 2026." in _BR11, str(_BR11))
# D41: the tag on the maps
ok("⭐ D41 'Fictional demo scheme' ON both maps of a demo tenant: the route map and the council map, PDF and page; none without "
   "a demo notice",
   # NARROWED 15 Oct 2026 (the user): the tag reads "Demo - fictional scheme"; the page bar keeps the tenant's notice
   S10B["map_demo_tag"] == "Demo - fictional scheme" and S10B["council"]["demo_tag"] == "Demo - fictional scheme"
   and _PB[0].count("Demo - fictional scheme") >= 1 and _PB[2].count("Demo - fictional scheme") >= 1
   and "Fictional demo scheme · nothing here is real" in _PB[0]
   and HTML10B.count('<g class="map-tag">') == 2 and LH10B.count('<g class="map-tag">') == 1
   and bulletin_doc._svg_tag(None) == "" and "map_demo_tag" in read("backend/bulletin_doc.py"))
# the HTML: the band, the brief, the leaflet links
ok("⭐ W15 the page: the ink band with the logo inlined as SVG (vector, gradient kept), the orange rule, Inter loaded, the mark "
   "at the foot; Key points after the map; links to the leaflet page and its PDF",
   '<header class="band">' in HTML10B and 'class="brand-logo"' in HTML10B and "ws-orange" in HTML10B and "<img" not in HTML10B
   and '<div class="band-rule"></div>' in HTML10B and "fonts.googleapis.com/css2?family=Inter" in HTML10B
   and '<ul class="brief" data-bulletin="brief">' in HTML10B and HTML10B.index('data-bulletin="map"') < HTML10B.index('data-bulletin="brief"')
   and 'href="/bulletin/leaflet/?month=10">The one-page leaflet</a>' in HTML10B and 'href="/api/bulletin/leaflet.pdf?month=10"' in HTML10B)
_pxL = [int(x) for x in re.findall(r"(?:font-size:|font:(?:\d{3} )?)(\d+)px", LH10B)]
ok("🔴 the leaflet page: the 14 px floor, a viewport, the demo notice, the map scrolls rather than shrinks on a phone",
   _pxL and min(_pxL) >= 14 and '<meta name="viewport" content="width=device-width,initial-scale=1">' in LH10B
   and f'<div class="notice">{NOTICE}</div>' in LH10B and ".mapwrap svg{min-width:720px}" in LH10B, str(sorted(set(_pxL))))
ok("🔴 the leaflet page: word ban and UK words", not _BANNED.search(re.sub(r"<[^>]+>", " ", LH10B)) and not _trucks(re.sub(r"<[^>]+>", " ", LH10B)))

# 17 Oct 2026 (UI audit #5, claude/ui-fix-keyboard): on a phone the two maps and five of the seven tables scroll sideways
# (the 720 px map floor and the nowrap figure columns are deliberate). Each such wrapper is now a named region a keyboard
# user can Tab to and scroll (tabindex 0; the role is required — a bare aria-label on a div is ignored), with a visible
# ring; the two tables whose every column wraps (works, glance) are not tab stops. The sideways scroll itself stays
# (open question 5: a phone-fit render).
_REG = re.compile(r'<div class="(mapwrap|tw)"( data-bulletin="[a-z-]+")? tabindex="0" role="region" aria-label="([^"]*)">')
_regB = [(m.group(1), m.group(3)) for m in _REG.finditer(HTML10B)]
ok("🔴 #5 the seven scrolling wrappers of the full bulletin are named regions with tabindex 0 — two maps, five tables, in page order, named by their headings",
   [c for c, _ in _regB] == ["mapwrap", "tw", "tw", "tw", "tw", "mapwrap", "tw"]
   and [l for _, l in _regB] == ["Planned lorry routes, October 2026", "Every route this month", "What is being moved",
                                 "What changed since last month", "Movements by council in October 2026",
                                 "Carbon by council in October 2026 (map)", "Carbon by council in October 2026 (table)"], str(_regB))
ok("#5 …the works and glance tables, whose columns wrap, stay plain wrappers (no needless tab stop); no other tabindex on the page; the names pass the word ban",
   '<div class="tw"><table data-bulletin="works">' in HTML10B and '<div class="tw"><table data-bulletin="glance">' in HTML10B
   and HTML10B.count('tabindex="0"') == len(_regB) == 7 and all(l.strip() for _, l in _regB)
   and not _BANNED.search(" ".join(l for _, l in _regB)) and not _trucks(" ".join(l for _, l in _regB)))
ok("#5 …a visible ring on a focused region in the page and in the leaflet (the link blue), and the leaflet's map is the same named region",
   ".mapwrap:focus-visible,.tw:focus-visible{outline:2px solid #1D4ED8;outline-offset:2px}" in HTML10B
   and ".mapwrap:focus-visible{outline:2px solid #1D4ED8;outline-offset:2px}" in LH10B
   and '<div class="mapwrap" data-bulletin="map" tabindex="0" role="region" aria-label="Planned lorry routes, October 2026"><svg' in LH10B
   and LH10B.count('tabindex="0"') == 1)
ok("#5 …the sideways scroll itself is unchanged (open question 5): the map's 720 px floor and the wrappers' overflow-x stay",
   ".mapwrap{overflow-x:auto;border:1px solid var(--line)} .mapwrap svg{min-width:720px}" in HTML10B and ".tw{overflow-x:auto}" in HTML10B
   and "tabindex" not in T10AJ)
_MS = read("backend/main.py")
# the leaflet endpoints, staff only like the bulletin (D10)
ok("🔴 the gate calls /bulletin/leaflet/ 'bulletin' (staff only); both endpoints check staff before reading anything",
   gate.scope_for("/bulletin/leaflet/?month=10") == "bulletin"
   and _MS.index('@app.get("/api/bulletin/leaflet.pdf")') > 0 and _MS.index('@app.get("/bulletin/leaflet/")') > 0
   and _MS.split("def bulletin_leaflet_pdf(")[1].split("def bulletin_leaflet_page(")[0].index("_staff_request(request)")
   < _MS.split("def bulletin_leaflet_pdf(")[1].split("def bulletin_leaflet_page(")[0].index("bulletin_doc.sheet(")
   and "export.build_bulletin_leaflet_pdf(sheet)" in _MS and "bulletin_doc.leaflet_html(bulletin_doc.sheet(" in _MS)

# the frame, shared
# NARROWED 14 Oct 2026 (D9): the Day sheet is a FOURTH caller of the same frame (it reuses it; it draws no frame of its own)
ok("⭐ ONE page frame: export.py draws its frame in page_frame() alone, called by the week sheet, the carbon summary, the bulletin and the Day sheet",
   # NARROWED 14 Oct 2026 (backlog item 2): + the route map export, a FIFTH caller of the same frame
   # NARROWED 14 Oct 2026, evening (the CLP plans): the route map is now just the map, ONE page drawn edge to edge on a
   # plain canvas (no running head, no page total), so it no longer calls the frame: four callers again
   _EXP.count("def on_page(") == 1 and _EXP.count("= page_frame(") == 4 and _EXP.count("c.line(lm, rule_y, W - rm, rule_y)") == 1
   and _EXP.count("BaseDocTemplate(buf") == 1 and "def page_frame(" in _EXP and "def frame_doc(" in _EXP
   and _EXP.count("doc = frame_doc(") == 4 and _EXP[_EXP.index("def build_day_sheet_pdf("):].count("on_page = page_frame(") >= 1
   and _EXP[_EXP.index("def build_route_map_pdf("):].count("page_frame(") == 0
   and "c = rl_canvas.Canvas(buf, pagesize=(W, H))" in _EXP[_EXP.index("def build_route_map_pdf("):])
ok("…the bulletin's frame carries the demo notice on every page and the plan-only foot",
   # NARROWED 13 Oct 2026 (D45): the notice is passed in the demo red; page_frame draws it as the demo bar
   # NARROWED 13 Oct 2026 (W15): in Inter, under the brand band, with wayscope.co.uk in the foot; one call for both PDFs
   "notice=((_pdf_safe(notice), _BF(\"bold\"), 8.5, DEMO_FG_RGB, H - band[\"height\"] - 8.5 * mm)" in _EXB
   and "foot=(_pdf_safe(S[\"foot\"] + \" · wayscope.co.uk\"), _BF(\"regular\"), 7, GREY), band=band)" in _EXB
   and _EXB.count("on_page = page_frame(") == 1)

# the endpoints (bodies; http_smoke drives the real HTTP layer and the middleware)
_tok = access._ACCESS.set(None)
try:
    try:
        main.bulletin_month_pdf(month=10, request=None)
        ok("🔴 the PDF without a code or a staff cookie — 401", False)
    except _HTTPException as e:
        ok("🔴 the PDF without a code or a staff cookie — 401", e.status_code == 401)
    _r = main.bulletin_page(month=10, request=None)
    ok("🔴 the HTML page without a code or a staff cookie — 401, the bulletin's own sign-in page",
       _r.status_code == 401 and "The monthly bulletin is for signed-in staff" in _r.body and "/bulletin/" in _r.body)
    os.environ["GATE_SECRET"] = "bulletin-harness-secret"


    class _CookieReq:
        def __init__(self, level):
            self.cookies = {gate.COOKIE: gate.sign(level)}
            self.headers = {}
    _r = main.bulletin_page(month=10, request=_CookieReq(gate.LEVEL_MAP))
    ok("🔴 …the MAP cookie does not open it (staff only, D10)", _r.status_code == 401)
    _r = main.bulletin_page(month=10, request=_CookieReq(gate.LEVEL_STAFF))
    ok("⭐ …the STAFF cookie does (the Dashboard's link opens it in a new tab with no header)",
       _r.status_code == 200 and _r.media_type.startswith("text/html") and "Lorry movements in October 2026" in _r.body
       and _r.headers.get("Cache-Control") == "no-store")
    _p = main.bulletin_month_pdf(month=10, request=_CookieReq(gate.LEVEL_STAFF))
    ok("…and the PDF the page links to opens on the staff cookie too", _p.media_type == "application/pdf" and _p.body[:5] == b"%PDF-")
finally:
    access._ACCESS.reset(_tok)
    os.environ.pop("GATE_SECRET", None)
_p = main.bulletin_month_pdf(month=10, request=None)
ok("⭐ the PDF with a code: application/pdf, named for the month, not cached",
   _p.media_type == "application/pdf" and _p.body[:5] == b"%PDF-"
   and _p.headers["Content-Disposition"] == 'attachment; filename="bulletin-2026-10.pdf"' and _p.headers["Cache-Control"] == "no-store")
_r = main.bulletin_page(month=None, request=None)
ok("…the page with no month opens the calendar month today, inside the programme",
   _r.status_code == 200 and main._bulletin_month_default() == max(1, min(main.MONTH_COUNT, weeks.month_index_of(datetime.date.today())))
   and bulletin.month_label_long(main._bulletin_month_default()) in _r.body)
_MS = read("backend/main.py")
_fp = _MS[_MS.index("def bulletin_month_pdf("):_MS.index("def bulletin_page(")].split(chr(34) * 3, 2)[2]     # the code, below its docstring
_fh = _MS[_MS.index("def bulletin_page("):_MS.index("def bulletin_page(") + 2200].split(chr(34) * 3, 2)[2]
ok("🔴 source: both endpoints check staff (_staff_request) before reading anything; the PDF and page come from bulletin_doc.sheet",
   '@app.get("/api/bulletin/month.pdf")' in _MS and '@app.get("/bulletin/")' in _MS
   and _fp.index("_staff_request(request)") < _fp.index("bulletin_doc.sheet(") and _fh.index("_staff_request(request)") < _fh.index("bulletin_doc.sheet(")
   # NARROWED 28 Oct 2026 (F1): the PDF is built inside the read cache's build, from the same sheet
   and ("export.build_bulletin_pdf(sheet)" in _fp or "export.build_bulletin_pdf(bulletin_doc.sheet(month, acc))" in _fp)
   and "bulletin_doc.html(bulletin_doc.sheet(" in _fh)
ok("…the middleware refuses /bulletin with the bulletin's page, not the guide's", 'if gate.scope_for(path) == "bulletin":' in _MS
   and "_BULLETIN_SIGNIN_PAGE" in _MS)

# 13 Oct 2026: D45 — the bulletin page's demo pill takes Option A, with the red DEMO tag
_BD = read("backend/bulletin_doc.py")
ok("D45: the bulletin page's notice is light grey with red text, a red edge (3 px under) and a red DEMO tag; no orange pill left",
   ".notice{{display:inline-block;background:#F1F5F9;color:#B91C1C;border:1px solid #DC2626;border-bottom-width:3px;" in _BD
   and ".notice::before{{content:'DEMO';content:'DEMO' / '';display:inline-block;" in _BD and "#FFF7ED" not in _BD)


# --------------------------------------------------------------------------- #
#  8f. 14 Oct 2026 — THE PUBLISHING CHECK (the user: "no map behind route,      #
#      layout needs improvement, legends too wordy")                            #
# --------------------------------------------------------------------------- #
# what a person reads: type no smaller than 7 pt (superscript reference numbers apart), the definition ONCE, every source
# ONCE and numbered, controls off the site pins, district labels apart, and a real basemap when Mapbox answers
def _sizes(pdf):
    out = {}
    for blk in re.findall(rb"BT(.*?)ET", pdf, re.S):
        cur = None
        for m in re.finditer(rb"/(\S+) ([\d.]+) Tf|(\)\s*Tj|\]\s*TJ)", blk):
            if m.group(1):
                cur = float(m.group(2))
            elif cur is not None:
                out[cur] = out.get(cur, 0) + 1
    return out


_SZ, _SZL = _sizes(PDF10B), _sizes(LF10B)
_nref = sum(1 for r in S10B["lot"]["rows"] if r.get("ref"))
ok("🔴 type floor: nothing the newsletter or the leaflet shows is under 7 pt, except the panel's superscript reference numbers "
   "(one per referenced row); body text 7.5 pt and up (the glance, sources and legends were 5.5–6.8 pt)",
   all(k >= 7.0 for k in _SZL) and all(k >= 7.0 or (k >= 6.5 and _SZ[k] <= _nref) for k in _SZ)
   and sum(v for k, v in _SZ.items() if k < 7.5) < 0.15 * sum(_SZ.values()), str((sorted(_SZ.items()), _nref)))
_DEFN = bulletin_doc.DEFINITION
ok("⭐ the definition is printed ONCE in the newsletter (under the four figures) and once on the page — it was seven times",
   T10BJ.count(_DEFN) == 1 and _PB[0].count(_DEFN) == 1 and HTML_TEXT_B.count(_DEFN) == 1)
_SRC = S10B["sources"]
ok("⭐ Sources: each source once, numbered in order; the panel's rows carry the number of THEIR source; the council row and "
   "the council table share ONE DESNZ entry (they were two)",
   len(_SRC) == len(set(_SRC)) and all(1 <= r["ref"] <= len(_SRC) for r in S10B["lot"]["rows"] if r.get("ref"))
   and all(_SRC[r["ref"] - 1] == r["source"] for r in S10B["lot"]["rows"] if r.get("ref") and r["label"] != "The council's figures")
   and sum("local authority and regional greenhouse gas" in x for x in _SRC) <= 1
   and any(x.startswith("Counting: ") for x in _SRC) and not any("Mapbox" in x for x in _SRC), str(_SRC))
ok("…on the page the references link to the numbered list at the foot",
   all(f'<li id="src-{i}">' in HTML10B for i in range(1, len(_SRC) + 1)) and '<ol class="src" data-bulletin="sources">' in HTML10B
   and all(f'<sup><a href="#src-{r["ref"]}">{r["ref"]}</a></sup>' in HTML10B for r in S10B["lot"]["rows"] if r.get("ref")))
# controls never sit on a site's pin
ok("⭐ control_spot: a control on a site's pin steps off by one step (up first) to a clear spot; a clear control stays put; "
   "a y-down caller (the page's SVG) passes a negative step and goes UP the screen",
   bulletin_doc.control_spot(10, 10, [(10, 10)]) == (10, 23.0) and bulletin_doc.control_spot(50, 50, [(10, 10)]) == (50, 50)
   and bulletin_doc.control_spot(10, 10, [(10, 10), (10, 23)])[0] > 10
   and bulletin_doc.control_spot(10, 100, [(10, 100)], clear=24, step=-26) == (10, 74.0))
_cs = [bulletin_doc.control_spot(0, 0, [(0, 0)] + [(13 * math.cos(math.pi / 2 - k * math.pi / 4), 13 * math.sin(math.pi / 2 - k * math.pi / 4)) for k in range(8)])]
ok("control_spot: boxed in on every side it goes one step up (never on the pin itself)", _cs == [(0, 13)])
_dbs2 = _EXP[_EXP.index("def _draw_bulletin_schematic("):_EXP.index("def _scale_bar(")]
ok("🔴 the PDF and the page both step controls off the pins and draw a leader back (one rule, bulletin_doc.control_spot)",
   "bulletin_doc.control_spot(ax, ay, pins)" in _dbs2 and "c.line(ax, ay, px, py)" in _dbs2
   and "control_spot(ax, ay, pins, clear=24, step=-26)" in read("backend/bulletin_doc.py"))
# labels apart
_ent = [(100, 100, 60), (104, 102, 60), (98, 96, 80), (300, 300, 40)]
_pl = bulletin_doc.place_labels(_ent, -9.5, 9, (0, 0, 400, 400))
_bx = [(x - w / 2, y - 9.5, x + w / 2, y + 9) for (x, y), (_, _, w) in zip(_pl, _ent)]
ok("⭐ place_labels (hand): three labels on one spot come out apart (no two boxes overlap), the first stays on its point, a "
   "lone label never moves, every box inside the bounds",
   _pl[0] == (100, 100) and _pl[3] == (300, 300)
   and not any(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3] for i, a in enumerate(_bx) for b in _bx[i + 1:])
   and all(b[0] >= 0 and b[2] <= 400 and b[1] >= 0 and b[3] <= 400 for b in _bx), str(_pl))
ok("🔴 the PDF's council labels and the page's are placed by the SAME rule (place_labels), biggest district first",
   "bulletin_doc.place_labels(ent, -9.5, 9, bounds)" in _EXP and "place_labels(ent, -14, 20, (4, 36, w - 4, h - 26), k=1.4)" in read("backend/bulletin_doc.py")
   and _EXP.count("key=lambda d: -(d.get(\"co2_t\") or d.get(\"a_day\") or 0))") == 1)
# the basemap path end to end, on a stubbed PNG (no Mapbox call): the PDF draws the image under the routes, says whose map
# it is and draws a scale bar; the page inlines the image and does the same
import struct as _st  # noqa: E402


def _tiny_png(w=4, h=3):
    raw = b"".join(b"\x00" + b"\xee\xee\xee" * w for _ in range(h))
    chunk = lambda t, d: _st.pack(">I", len(d)) + t + d + _st.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", _st.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


import zlib  # noqa: E402
_real_fetch = basemap.fetch
_fetched = []
# a different PNG per request (reportlab draws identical image bytes once and reuses them)
basemap.fetch = lambda v, token=None, timeout=12, retina=True, style=None: (_fetched.append((v["w"], v["h"], retina)), _tiny_png(4 + len(_fetched)))[1]
try:
    _PDFM = export.build_bulletin_pdf(S10B)
    _LFM = export.build_bulletin_leaflet_pdf(S10B)
    _HTM = bulletin_doc.html(S10B)
finally:
    basemap.fetch = _real_fetch
_TM = " ".join(pdf_text(_PDFM).split())
ok("⭐ with a basemap: the newsletter draws it under the route map and the council map (two images), credits Mapbox and "
   "OpenStreetMap under the map and draws a scale bar; still four pages",
   _PDFM.count(b"/Subtype /Image") == 2 and "© Mapbox © OpenStreetMap" in _TM and re.search(r"\b\d+(\.5)? km\b", _TM)
   and len([p for p in pdf_text(_PDFM).split("\f") if p.strip()]) == 4 and "not to scale" not in _TM.split("Key points")[0])
ok("⭐ …and ONE request per map: the page fit is found on sizing passes, so the newsletter asked for two basemaps (route map, "
   "council map) and the leaflet one, all @2x for print; the page two @1x",
   [r for _, _, r in _fetched].count(True) == 3 and [r for _, _, r in _fetched].count(False) == 2, str(_fetched))
ok("⭐ …the page inlines the basemap under its routes and districts (no Mapbox URL or token in the page), with the credit and a scale bar",
   _HTM.count('<image href="data:image/png;base64,') == 2 and "api.mapbox.com" not in _HTM and "access_token" not in _HTM
   and "© Mapbox © OpenStreetMap" in _HTM and _HTM.count('<g class="scale">') == 2 and 'fill-opacity="0.8"' in _HTM
   and ("aria-label=\"Map of this month's planned lorry routes\"" in _HTM
        or 'aria-label="Map of this month&#x27;s planned lorry routes"' in _HTM))
ok("⭐ the leaflet with a basemap: one image, still ONE page", _LFM.count(b"/Subtype /Image") == 1
   and len([p for p in pdf_text(_LFM).split("\f") if p.strip()]) == 1)
# the frame and the look, at source
ok("🔴 tables: a pale head band (#F1F5F9) in ink with a rule under it, hairlines between rows, no box (the ink heads made every page heavy)",
   'HEAD_TINT = colors.HexColor("#F1F5F9")' in _EXP and '("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.Color(*NAVY_RGB))' in _EXP
   and 'self.st_h = ParagraphStyle("h", parent=st, fontName=b, fontSize=7.5, leading=9.5, textColor=colors.Color(*NAVY_RGB))' in _EXP
   and "th{{font-size:14px;font-weight:700;background:var(--head);border-bottom:2px solid var(--ink)}}" in read("backend/bulletin_doc.py"))
# NARROWED 14 Oct 2026 (D9): four callers (+ the Day sheet)
ok("🔴 ONE page frame still: one on_page, the running head and the page total are page_frame's options, the four callers unchanged",
   _EXP.count("def on_page(") == 1 and _EXP.count("= page_frame(") == 4 and _EXP.count("doc = frame_doc(") == 4   # NARROWED 14 Oct 2026: + the route map export; evening: the route map is a plain one-page plan again
   and 'later = doc.page > 1 and band.get("running")' in _EXP and "autoNextPageTemplate=\"later\"" in _EXP)
ok("🔴 the report-a-lorry strip is on page 1 (all three lines) and not repeated at the end; the page keeps one at the foot too",
   "Working hours:" in _PB[0] and "Working hours:" not in _PB[3] and HTML10B.count('<div class="report">') == 2)
ok("🔴 the publishing check's words: no '[a typed field this scheme has not set yet]', no 'laden legs', no route id in the "
   "works or flags, no 'Terms explained', no chart",
   "a typed field this scheme has not set yet" not in T10BJ + HTML_TEXT_B and "laden legs" not in T10BJ + HTML_TEXT_B
   and not re.search(r"\bR\d+\b", " ".join(o["text"] for o in S10B["others"]) + " ".join(w["routes_text"] for w in S10B["works"]))
   and "Terms explained" not in T10BJ + HTML_TEXT_B and "by route" not in T10BJ)

# =========================================================================== #
#  17 Oct 2026 (the user: UK drivers' hours; the review): the bulletin's words for lorries needed                       #
# =========================================================================== #
_bsrc, _bdsrc = read("backend/bulletin.py"), read("backend/bulletin_doc.py")
ok("⭐ drivers' hours: the vehicles rule names a driver's day under the UK drivers' hours, ONE required break, the 9 h "
   "cap, and says it is a planning figure (weekly limits and drivers' own hours not checked)",
   "day under the UK drivers' hours: the shift less the required break, at most 9 h driving; a planning " in _bsrc
   and "figure, weekly limits and drivers' own hours not checked), rounded up per line" in _bsrc
   and "the required breaks" not in _bsrc)
ok("...the newsletter's 'Lorries needed' term says the same in its own words (and the page count holds: four pages, "
   "http_smoke D43)",
   "driver's day under the UK drivers' hours (break taken, at most 9 h driving; a planning figure)." in _bdsrc
   and "(breaks taken, at most 9 hours of driving)" not in _bdsrc)
ok("🔴 no compliance claim in the bulletin's drivers' hours words: never 'compliant', 'compliance' or 'legal'",
   not re.search(r"drivers' hours[^\"]{0,200}\b(compliant|compliance|legal)\b", _bsrc + _bdsrc, re.I))

# =========================================================================== #
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
