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
   and R["vehicles"]["label"] == "Vehicles needed (excludes 1 line with no stored road route for the vehicle)"
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
   and R["carbon"]["label_day"] == "CO₂e a day (excl. 1 line with no stored road route)"  # NARROWED 12 Oct 2026 (wording)
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
   and R_NOCO2["carbon"]["label_day"] == "CO₂e a day (excl. 4 lines with no stored road route)" and R_NOCO2["headline"] == H
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
   and R_UNDRAWN["note"] == ("No approved forecast on a route the map draws in this month: 1 line on 1 route "
                             "with no stored road route yet, listed below and not counted."), R_UNDRAWN["note"])

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
stockpiles.consume("L2", 10, 1, consumed_qty=300, unit="t")
_c10 = bulletin.conditions_of_month(10, payload=P10, factors=FACTORS)["stockpiles_over"]
ok("…the breaking case: 300 t consumed in October's first week brings it under by month END, so October lists nothing",
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
HTML_TEXT = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", HTML10, flags=re.S)).split())
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
ok("…the movements in the month name the working days from the scheme's settings (the roll-up's day count)",
   S10["headline"][1]["label"] == f"movements in the month ({WD:g} working days, from the scheme's settings)"
   and f"movements in the month ({WD:g}" in PAGES[0] and "working days, from the scheme's" in PAGES[0])
ok("⭐ the HTML page carries the SAME four figures as the PDF (one view model): page and PDF cannot disagree",
   all(f'<div class="v">{v.replace("&", "&amp;")}</div>' in HTML10 for v in _fig.values())
   and all(v in HTML_TEXT for v in _fig.values()))
_KPI = f"Two-way movements = loads (deliveries) per working day ({WD:g}/month); each is a lorry out laden and back empty."
ok("⭐ page 1: the counting line and the one-sentence definition — the map's kpi-note sentence, verbatim",
   "Counts are two-way movements: one lorry out laden and back empty is one delivery, counted once, never doubled." in PAGES[0]
   and _KPI in PAGES[0] and _KPI in HTML_TEXT
   and "Two-way movements = loads (deliveries) per working day (${wd}/month); each is a lorry out laden and back empty." in MAP)
ok("…and the other-schemes line (HS2 counts HGVs visiting the site; EKFB printed each way)",
   "HS2 prints HGVs visiting the site" in PAGES[0] and "EKFB 2020 printed maximum HGV each way" in PAGES[0])
ok("⭐ the busiest routes on page 1: origin to destination (Helvetica has no arrow), the planning flag typed on R1 and the plan above it",
   "Kelsey Quarry to Mill Compound" in PAGES[0] and "Ridge Pit to Mill Compound" in PAGES[0]
   and "60 a day · plan is above it" in PAGES[0] and "no planning cap typed" in PAGES[0]
   and S10["busiest"][0]["flag_text"] == "60 a day · plan is above it" and S10["busiest"][0]["over_flag"] is True)
ok("…the letter pins: the busiest route's sites are A and B, in the legend under the map",
   [p["letter"] + " " + p["name"] for p in S10["places"]] == ["A Kelsey Quarry", "B Mill Compound", "C Ridge Pit"]
   and S10["busiest"][0]["letters"] == "A → B" and S10["busiest"][1]["letters"] == "C → B")
ok("…the busiest list is the roll-up's, in its order", [r["route_id"] for r in S10["busiest"]] == [b["route_id"] for b in B])
ok("⭐ last month, plan against plan: October's sheet says September had none planned; November's prints October's rate for R1",
   S10["busiest"][0]["last_month_text"] == "none planned"
   and [r for r in S11["routes"] if r["route_id"] == "R1"][0]["last_month_text"] == f"{(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f} a day"
   and f"{(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f} a day" in T11J)
ok("⭐ the roll-up's by_route list ranks EVERY drawn route the same way as the busiest five (the chart and the list agree)",
   R["by_route"][:len(R["busiest_routes"])] == R["busiest_routes"] and {r["route_id"] for r in R["by_route"]} == set(R["routes_in_use"])
   and [r["route_id"] for r in R7["by_route"]] == ["S7", "S6", "S5", "S4", "S3", "S2", "S1"] and R_EMPTY["by_route"] == [])
ok("⭐ page 2: the chart of movements a day by route, what is being moved, the works, what changed, terms, caveats",
   all(h in T10J for h in ("Two-way movements a day by route", "What is being moved", "Works affecting the roads in October 2026",
                           "What changed since last month", "Terms explained", "Caveats"))
   and "Two-way movements a day by route" not in PAGES[0])
ok("…the chart's caption names the print treatment and the dashed planning flag", "Dashed red mark: the planning flag typed on the route" in T10J
   and "flag 60" in T10J)
ok("…what is being moved is the bar's discipline panel, with an All routes row equal to the headline",
   [m["name"] for m in S10["moved"]] == [d["name"] for d in BD["discipline"]] and S10["moved_total"]["a_day"] == _fig["two_way"]
   and S10["moved_total"]["vehicles"] == f"{FLEET:,}")
ok("⭐ works affecting the roads: the stored A6 closure in October with its dates and provider; the ENDED closure is not there",
   "A6 Resurfacing" in T10J and "16 Oct 2026 to 17 Oct 2026" in T10J and "A46 Barrier repairs" not in T10J
   and "Mass limit 18 t" in T10J and "Mass limit: Mass limit" not in T10J and S10["works"][0]["who"] == (bulletin.restrictions.provider() or {}).get("name", S10["works"][0]["who"]))
ok("⭐ …the local controls are the zones in force in the month, numbered: the weight limit in; the September closure and the haul road out",
   [(z["n"], z["name"], z["kind"]) for z in S10["controls"]] == [(1, "Mill Lane 7.5 t limit except for access", "weight limit")]
   and "Mill Lane 7.5 t limit except for access" in T10J and "Old bridge closure" not in T10J and "Quarry haul road" not in T10J)
ok("…the routes never checked are named as never checked — never a clear road",
   "never checked for 2 of this month's routes (R2, R3); not a clear road." in T10J)
ok("…the typed cap exceeded reads as a planning flag, never a block",
   f"Route R1: {(loads_r1_a + loads_r1_b + loads_r1_c) / WD:,.0f} two-way movements a day planned against a planning flag of 60 a day. "
   "A planning flag is never a block." in T10J)
ok("⭐ what changed since last month is plan against plan, and says so; October against an empty September; November against October",
   "Plan against plan: each month's approved plan as it stands today. No earlier issue of this bulletin is stored." in T10J
   and S10["change_text"].startswith("Since September 2026: Two-way movements a day — → 98")
   and f"Since October 2026: Two-way movements a day 98 to {(V11) / WD:,.0f}" in T11J
   and [c["label"] for c in S10["change_rows"]] == ["September 2026", "October 2026", "November 2026 (next)"], S10["change_text"])
ok("⭐ the D28 rule is named: the month's loads summed as typed (fractional), not rounded per line",
   "The month's loads are summed as typed (fractional), not rounded per line" in T10J)
ok("⭐ whole movements (12 Oct, evening): the terms say the total is shown to the nearest whole movement, and no movement "
   "count on the page carries a decimal (the fractional sum stays in the JSON)",
   "the total is then shown to the nearest whole movement." in T10J
   and all("." not in r["in_month_text"] for r in S10["routes"])
   and any(abs(r["a_day"] or 0) > 0 for r in S10["routes"]))
ok("⭐ carbon carries the stamp: planning estimate, DESNZ 2026 basis, not Carbon Tool figures; CO2e spelled so Helvetica prints it",
   "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in T10J and "CO2e = routed km" in T10J
   and "₂" not in "".join(v for _, v in S10["terms"]) and "CO₂e = routed km" in HTML_TEXT
   and "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in HTML_TEXT)
ok("⭐ the report-a-lorry block with the typed fields as placeholders (no invented contact)",
   "Report a lorry off route: the date, time, place, direction of travel and registration, to [contact line and email: "
   "a typed field this scheme has not set yet]." in T10J and "Working hours: [a typed field this scheme has not set yet]." in T10J
   and "@" not in S10["report"]["lorry"])
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
   S10C["report"]["lorry"] == "Report a lorry off route: the date, time, place, direction of travel and registration, to "
   "haulage.concerns@example.org." and "haulage.concerns@example.org" in HTML10C and "haulage.concerns@example.org" in T10CJ
   and "[contact line and email:" not in S10C["report"]["lorry"], S10C["report"]["lorry"])
ok("…and with none typed the same block keeps the placeholder (no invented contact)",
   S10["report"]["lorry"].endswith("[contact line and email: a typed field this scheme has not set yet].")
   and "concern_email" not in S10["report"]["lorry"])
ok("…the frame: the title, the as-at stamp, the plan-only foot", "Lorry movements in October 2026" in PAGES[0]
   and "Approved plan as at 12 October 2026" in PAGES[0] and "A planning forecast, not a monitoring report" in PAGES[1])
ok("…the map is the schematic offline, and the caption says so", "schematic from the stored road routes, not to scale" in PAGES[0]
   and "Routes this month: 2" in PAGES[0])
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
_EXB = _EXP[_EXP.index("# ------------------------------------------------------------------ the monthly bulletin (C4"):]
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
ok("…the routes are blue, the bars in the print treatment (light fill, solid edge), the flag dashed in red with its word",
   'stroke="#4A72C9"' in HTML10 and 'fill="#D7E0F3" stroke="#4A72C9" stroke-width="2"' in HTML10
   and 'stroke="#DC2626" stroke-width="2" stroke-dasharray="4 3"><title>planning flag 60 a day</title>' in HTML10
   and "Dashed red mark: the planning flag typed on the route." in HTML10)
# NARROWED 12 Oct 2026 (wording review): 640 px let the 14 px labels of the 720-unit chart render at 12.4 px on a phone
ok("…the chart scrolls on a phone rather than shrinking its labels; the map is an inline schematic, not a second Mapbox",
   ".chartwrap svg{min-width:720px}" in HTML10 and "mapbox" not in HTML10.lower())
_cw = re.search(r'<svg viewBox="0 0 (\d+) \d+" role="img" aria-label="Two-way movements a day by route" class="chart">', HTML10)
_mw = re.search(r"\.chartwrap svg\{min-width:(\d+)px\}", HTML10)
ok("🔴 the 14 px floor on a phone: the chart never draws narrower than its viewBox, so its 14 px labels never render below 14 px",
   bool(_cw and _mw) and int(_mw.group(1)) >= int(_cw.group(1)), str((_cw and _cw.group(1), _mw and _mw.group(1))))
# 12 Oct 2026 (Track C review): the schematic map is 720 units wide with 14 px pin letters; at width:100% on a 375 px
# phone they drew at about 6.7 px. It now sits in a scrolling wrapper and never draws narrower than its viewBox.
_mv = re.search(r'<div class="mapwrap" data-bulletin="map"><svg viewBox="0 0 (\d+) \d+" role="img"', HTML10)
_mm = re.search(r"\.mapwrap svg\{min-width:(\d+)px\}", HTML10)
ok("🔴 the 14 px floor on a phone: the schematic map never draws narrower than its viewBox (it scrolls instead)",
   bool(_mv and _mm) and int(_mm.group(1)) >= int(_mv.group(1)) and ".mapwrap{overflow-x:auto}" in HTML10,
   str((_mv and _mv.group(1), _mm and _mm.group(1))))
ok("…and on paper both figures take the page width (the phone's minimum is reset for print)",
   ".chartwrap svg,.mapwrap svg{min-width:0}" in HTML10.split("@media print")[1])
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
   _G["Haul carbon in the month"]["figure"] == f"{R['carbon']['co2_t_in_month']:,.1f} t CO2e"
   and "DESNZ 2026" in _G["Haul carbon in the month"]["data"])
ok("glance: road works say two of the month's routes were never checked (the stored check's own state), never a clear road",
   "never checked" in _G["Road works, closures and local controls in October 2026"]["data"])
_NR = [g["item"] for g in S10["glance"] if g["not_reported"]]
ok("⭐ glance: the five things a monitoring report fills from observed records are listed and marked Not reported, never a figure",
   _NR == ["Lorries counted on the roads or at the site gates", "Lorries kept to the approved routes and working hours",
           "Vehicle and operator standards (FORS, CLOCS, Euro VI, Direct Vision Standard)", "Collisions and near misses",
           "Enquiries and complaints"]
   and all(g["figure"] == "Not reported" for g in S10["glance"] if g["not_reported"]), str(_NR))
# NARROWED in build 13 Oct (the rendered PDF): page 1 overflowed and split the table; it now opens page 2
ok("⭐ glance: at the top of page 2 of the PDF (page 1 keeps its shape) and on the page, with its explanation",
   "This month at a glance" in PAGES[1] and "This month at a glance" not in PAGES[0]
   and PAGES[1].index("This month at a glance") < PAGES[1].index("Two-way movements a day by route") and "Not reported" in T10J and "FORS, CLOCS, Euro VI" in T10J and "Direct Vision" in T10J
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
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
_calls = []
_real_open = export.urllib.request.urlopen


def _count_open(req, timeout=0):
    _calls.append(getattr(req, "full_url", str(req)))
    raise OSError("harness: counted, not fetched")


try:
    export.urllib.request.urlopen = _count_open
    _n0 = len(_calls); export.build_bulletin_pdf(S10); _no_council_calls = len(_calls) - _n0
    S10A = bulletin_doc.sheet(10, PLANNER, now=datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc))
    _n0 = len(_calls); PDF10A = export.build_bulletin_pdf(S10A); _council_calls = len(_calls) - _n0
    HTML10A = bulletin_doc.html(S10A)
finally:
    export.urllib.request.urlopen = _real_open
    config.tenant_settings = _real_ts4
offline(export)
T10A = pdf_text(PDF10A)
T10AJ = " ".join(T10A.split())
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
   CA["tally"] == f"The 3 districts shown carry {_tt(0.8 * _CT)} of the scheme's {_tt(_CT)} CO2e in October 2026; "
                  f"the other {_tt(0.2 * _CT)} is driven on roads outside them, in council areas not loaded.", CA["tally"])
ok("council: shares of the scheme's carbon (50% and 30%) and the highway authority per district",
   _D["Eastshire"]["share"] == "50%" and _D["Westvale"]["share"] == "30%" and _D["Westvale"]["highway_authority"] == "Westvale City Council")
ok("council: a sliver of the scheme's carbon reads 'under 1%', never 0%",
   bulletin_doc._share(0.4, 100) == "under 1%" and bulletin_doc._share(0.6, 100) == "1%" and bulletin_doc._share(None, 100) == "—"
   and bulletin_doc._share(0, 100) == "—" and bulletin_doc._share(5, None) == "—")
ok("council: the county's figure is a line of text (its roads, its highway authority), not a second fill",
   CA["county_lines"] == [f"Testshire (county or unitary authority; highway authority Test County Council): {_tt(0.8 * _CT)} CO2e "
                          "in October 2026 on its roads."], str(CA["county_lines"]))
ok("⭐ council: the basis sentence, the not-comparable-with-DESNZ line, the Carbon page's stamp, the boundary source and the ONS / OS licence lines",
   "Split by the km inside each district; across one tier it adds up to the scheme's carbon." in CA["basis"]
   and "not comparable with the DESNZ local authority greenhouse gas statistics" in CA["basis"]
   and CA["stamp"] == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"
   and CA["sources"] == ["Boundaries: Test districts (May 2026), generalised to 200 m."] and CA["attribution"] == _ATTR)
ok("⭐ council PDF: the section's title, each district and its figure, the tally, the stamp and both licence lines are in the PDF text",
   "Carbon by council in October 2026" in T10AJ and all(n in T10AJ for n in ("Eastshire", "Westvale", "Farmoor"))
   and _tt(0.5 * _CT) in T10AJ and "is driven on roads outside them" in T10AJ
   and "Contains OS data © Crown copyright and database right 2026" in T10AJ
   and "Source: Office for National Statistics licensed under the Open Government Licence v.3.0" in T10AJ
   and "not Carbon Tool figures" in T10AJ, T10AJ[-1500:])
ok("🔴 council PDF: drawing the districts makes NO network call (the same urlopen count as the bulletin without them)",
   _council_calls == _no_council_calls, f"{_council_calls} vs {_no_council_calls} {_calls}")
ok("⭐ council PDF: 'fictional demo scheme' still on every page, which now number at least three",
   len([p for p in T10A.split("\f") if p.strip()]) >= 3 and all("fictional demo scheme" in p.lower() for p in T10A.split("\f") if p.strip()))
ok("⭐ council page: an inline SVG of the districts (even-odd fill, white 2.5 px borders), each label with name and figure; no Mapbox",
   '<div class="mapwrap" data-bulletin="council-map"><svg viewBox="0 0 720 560"' in HTML10A
   and HTML10A.count('fill-rule="evenodd" stroke="#FFFFFF" stroke-width="2.5"') == 3
   and f'<tspan class="cn">Eastshire</tspan>' in HTML10A and f'dy="17">{_tt(0.5 * _CT)}</tspan>' in HTML10A
   and "mapbox" not in HTML10A.lower() and "<polyline" not in HTML10A.split('data-bulletin="council-map"')[1].split("</svg>")[0])
ok("council page: the district fills are the ramp's and the grey; the legend lists the four steps, the grey and the hatched no figure",
   f'fill="{_D["Eastshire"]["fill"]}" fill-rule="evenodd"' in HTML10A and 'fill="#E7E5E4" fill-rule="evenodd"' in HTML10A
   and all(t in HTML_TEXT_A for t in ("under 50 t", "50 to 99 t", "100 to 199 t", "200 t and over", "no approved route", "no figure (never a zero)")))
ok("council page: the table (district, highway authority, t CO₂e, share), the tally, the licence lines, the stamp",
   '<table data-bulletin="council">' in HTML10A and "Westvale City Council" in HTML_TEXT_A and "is driven on roads outside them" in HTML_TEXT_A
   and "Contains OS data © Crown copyright and database right 2026" in HTML_TEXT_A and "not Carbon Tool figures" in HTML_TEXT_A
   and "t CO₂e in the month" in HTML_TEXT_A)
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
ok("council: the shared projection — one projector for the page and the PDF (bulletin_doc.projector over council_points)",
   "bulletin_doc.projector(bulletin_doc.council_points(C), w, h, 3 * mm)" in read("backend/export.py")
   and "proj = projector(council_points(C), w, h, 16)" in read("backend/bulletin_doc.py"))

# the static map's URL (a capturing stub, never the network)
_seen = []


def _capture(req, timeout=0):
    _seen.append(req.full_url)
    raise OSError("harness: captured, not fetched")


export.urllib.request.urlopen = _capture
_none = export.bulletin_map_png(S10["map_routes"], S10["places"], S10["controls"], token="pk.test")
_u = _seen[0] if _seen else ""
# REVERSED 13 Oct 2026 (W11, the user's bundle B): the routes were one plan blue with the width by volume (R1 8 px, R2
# thinner); each now takes the public map's Volume colour for its two-way movements a day, all at ONE width over the
# map's dark casing. R1 (~65 a day) is the 50-100 step, R2 (~23 a day) the 10-25 step.
_r1, _r2 = (LOADS - loads_r2) / WD, loads_r2 / WD
ok("⭐ the static map: each route in its Volume colour (R1 50-100 a day = #0B55CB, R2 10-25 = #5A96F6), ONE width (4 px) over "
   "a 6 px dark casing per route, letter pins, the numbered amber control, within the URL limit; no plan-blue width-by-volume path",
   _none is None and len(_seen) == 1 and 50 <= _r1 < 100 and 10 <= _r2 < 25
   and "path-4+0B55CB-1(" in _u and "path-4+5A96F6-1(" in _u and _u.count("path-6+1F2024-0.9(") == 2
   and not re.search(r"path-\d+\+4A72C9", _u) and not re.search(r"path-(?!4\+|6\+1F2024)\d+\+", _u)
   and _u.index("path-6+1F2024") < _u.index("path-4+")
   and _u.index("path-4+5A96F6") < _u.index("path-4+0B55CB")
   and "pin-s-a+1F2024(" in _u and "pin-s-b+1F2024(" in _u and "pin-s-1+D97706(" in _u and len(_u) <= 8000
   and "/styles/v1/mapbox/light-v11/static/" in _u, _u[:300])
_many = [{"route_id": f"X{i}", "coords": [(-1.0 + j * 0.0013 + i * 0.01, 52.5 + ((j * 7919) % 97) * 0.0011) for j in range(500)],
          "a_day": i, "weight": i / 40} for i in range(1, 41)]
_seen.clear()
export.bulletin_map_png(_many, S10["places"], S10["controls"], token="pk.test")
ok("🔴 forty long routes: the URL is thinned (or the pins dropped) to fit 8,000 characters — never sent over the limit",
   all(len(u) <= 8000 for u in _seen), str([len(u) for u in _seen]))
export.urllib.request.urlopen = _real_urlopen
offline(export)


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
_svgm = HTML10.split('data-bulletin="map">')[1].split("</svg>")[0]
ok("⭐ W11 page: every route at ONE width (5) in its Volume colour over a 7.5 casing in the map's ink; never the plan blue",
   _svgm.count('stroke-width="5"') == 2 and _svgm.count('stroke="#1F2024" stroke-width="7.5"') == 2
   and 'stroke="#0B55CB" stroke-width="5"' in _svgm and 'stroke="#5A96F6" stroke-width="5"' in _svgm
   and "#4A72C9" not in _svgm and _svgm.index('stroke-width="7.5"') < _svgm.index('stroke-width="5"'))
ok("⭐ W11 page: the legend under the map — the title for the month and the five swatches; the old 'thicker' line is gone",
   'data-bulletin="map-legend"><b>Two-way movements a day in October 2026:</b>' in HTML10
   and all(f"background:{c}" in HTML10.split('data-bulletin="map-legend"')[1].split("</p>")[0] for c in bulletin_doc.VOLUME_RAMP)
   and "thicker" not in HTML10 and "one width, so a width never carries a figure" in HTML_TEXT)
ok("⭐ W11 PDF: page 1 carries the legend (title and the five ranges) and the caption says one width; 'thicker' nowhere",
   "Two-way movements a day in October 2026:" in PAGES[0] and all(t in PAGES[0] for t in ("under 10", "10 to 25", "25 to 50", "50 to 100", "100 and over"))
   and "Volume colour for its two-way movements a day, one width" in PAGES[0] and "thicker" not in T10J)
ok("🔴 W11 source: no line width is worked out from a volume in the bulletin's drawing code or the view model any more",
   all(x not in _EXB + read("backend/bulletin_doc.py") for x in ('r["weight"]', "r['weight']", '"weight":', "1.5 + 5 *", "0.8 + 3.2 *")))
ok("🔴 W11 source: the schematic and the page draw the casing then the colour, at fixed widths",
   'c.setLineWidth(3.4)' in _EXB and 'c.setLineWidth(2.2)' in _EXB and "_hex_rgb(r[\"color\"])" in _EXB
   and "ROUTE_LINE_W, ROUTE_CASING_W = 5, 7.5" in read("backend/bulletin_doc.py")
   and "const CARBON_LINE_WIDTH = 5, CARBON_CASING_WIDTH = 7.5;" in MAP)

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
config.tenant_settings = lambda *a, **k: dict(config.TENANT_DEFAULTS, name="Wolds Link (fictional)", demo_notice=NOTICE)
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
   and MB["footnote"].startswith(areas.DOUBLE_COUNT) and MB["scheme_line"] == "The scheme as a whole: 98 two-way movements a day in October 2026."
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
   and "Lorry-miles: laden and empty" in S10M["council_mv"]["footnote"])
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
   and "The scheme as a whole: 98 two-way movements a day in October 2026." in HTML_TEXT_B
   and HTML10B.index("Movements by council") < HTML10B.index("Carbon by council"))
ok("⭐ W13 PDF: the section's title, each district with its figure and change, the scheme line and the double-count footnote",
   "Movements by council in October 2026" in T10BJ and "new this month" in T10BJ and "no approved laden route" in T10BJ
   and "The scheme as a whole: 98 two-way movements a day" in T10BJ and areas.DOUBLE_COUNT in T10BJ
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
        nxt = labels[i + 1].x - 10.5 if i + 1 < len(labels) else _U
        if end > nxt:
            bad.append((lb.text, round(end, 1), round(nxt, 1)))
    return bad


ok("🔴 the PDF legends never overlap: the title before the first swatch, each label before the next swatch, the row inside the page",
   _legend_overlaps(export._council_legend(MB, _U, "Two-way movements a day:")) == []
   and _legend_overlaps(export._council_legend(CB, _U)) == [],
   str((_legend_overlaps(export._council_legend(MB, _U, "Two-way movements a day:")), _legend_overlaps(export._council_legend(CB, _U)))))
_cap = export._BulletinMapCaption(types.SimpleNamespace(kind="schematic"), 19)
ok("🔴 the map caption is two lines, each inside the page width (it ran off the page as one)",
   _cap.height >= 8 * _mm
   and _sw("Routes this month: 19 · each route in the public map's Volume colour for its two-way movements a day, one width",
           "Helvetica", 7.5) <= _U
   and "A schematic from the stored road routes, not to scale (no map tiles)." in T10J)

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

# the frame, shared
ok("⭐ ONE page frame: export.py draws its frame in page_frame() alone, called by the week sheet, the carbon summary and the bulletin",
   _EXP.count("def on_page(") == 1 and _EXP.count("= page_frame(") == 3 and _EXP.count("c.line(lm, rule_y, W - rm, rule_y)") == 1
   and _EXP.count("BaseDocTemplate(buf") == 1 and "def page_frame(" in _EXP and "def frame_doc(" in _EXP
   and _EXP.count("doc = frame_doc(") == 3)
ok("…the bulletin's frame carries the demo notice on every page and the plan-only foot",
   # NARROWED 13 Oct 2026 (D45): the notice is passed in the demo red; page_frame draws it as the demo bar
   "notice=((_pdf_safe(notice), \"Helvetica-Bold\", 8.5, DEMO_FG_RGB, H - 25 * mm) if notice else None)" in _EXB
   and "foot=(_pdf_safe(S[\"foot\"]), \"Helvetica\", 7, GREY)" in _EXB)

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
   and "export.build_bulletin_pdf(sheet)" in _fp and "bulletin_doc.html(bulletin_doc.sheet(" in _fh)
ok("…the middleware refuses /bulletin with the bulletin's page, not the guide's", 'if gate.scope_for(path) == "bulletin":' in _MS
   and "_BULLETIN_SIGNIN_PAGE" in _MS)

# 13 Oct 2026: D45 — the bulletin page's demo pill takes Option A, with the red DEMO tag
_BD = read("backend/bulletin_doc.py")
ok("D45: the bulletin page's notice is light grey with red text, a red edge (3 px under) and a red DEMO tag; no orange pill left",
   ".notice{{display:inline-block;background:#F1F5F9;color:#B91C1C;border:1px solid #DC2626;border-bottom-width:3px;" in _BD
   and ".notice::before{{content:'DEMO';content:'DEMO' / '';display:inline-block;" in _BD and "#FFF7ED" not in _BD)

# =========================================================================== #
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
