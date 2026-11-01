"""
The CLP document's appendices A–O, 1 Nov 2026 (task 4a, PR 4) — backend/clp_doc_appendices.py (the reads) and
clp_doc_appendices_render.py (the Word part).

What is asserted: each appendix is in the answer only when the plan has data for it and absent otherwise; every figure
equals the module that owns it (the busy-hour times = hour_times' evidence block, stock = the stockpile read, arrivals =
Gate arrivals, lorries = carbon.lorries_for over derived.cycle_for); a team's CLP counts the team's lorries only (pours,
abnormal loads, the gates' share) and leaves out the Simulation's day; the .docx READ BACK with python-docx: the
appendices after section 7 in order, the printed / left-out line, no banned word anywhere, no 'To complete' line added,
Appendix O only with a history; the source reads only, fetches nothing and carries the tenant predicate.

WHAT THIS DOES NOT PROVE
------------------------
  * The pours are read through a stub (the scheme has no mixer line); the real read ran on a demo copy by hand.
  * Collisions, community places, council clip lengths, holding areas and layout phases are not stored in this scheme, so
    H, I, J's figures and B are proved absent here, not present; they were looked at in a demo copy by hand.
  * How Word lays the pages out (looked at by hand in Word, 1 Nov 2026).
  * SQLite only.

Run (PowerShell, from Modus): set PYTHONUTF8 = 1, then run backend/tests/test_clp_doc_appendices.py with the .venv-tests python.
"""
import copy
import json
import io
import math
import os
import re
import sys
import tempfile
import types
import zipfile

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


TMP = tempfile.mkdtemp(prefix="rbe_clpdoc_")
from portable import remove_scratch_db, offline   # noqa: E402,F401  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import costing  # noqa: E402
import config  # noqa: E402
import gates  # noqa: E402
import gate_arrivals  # noqa: E402
import gate_hours  # noqa: E402
import network  # noqa: E402
import site_areas  # noqa: E402
import taxonomy  # noqa: E402
import carbon_target  # noqa: E402
import clp_doc  # noqa: E402
import export  # noqa: E402
offline(export)            # PR 2 draws plans: Mapbox is never called from a test (the schematic branch)
from docx import Document  # noqa: E402
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


ART = network.DEFAULT_PROFILE          # "Artic Tipper (44t)", 29 t a load
FLAT = "Artic Flatbed (44t)"
BAL = "Large aggregate / ballast"
SPOIL = "Earthworks / soil"
PRE = "Precast units"

# =========================================================================== #
#  0. A small scheme by hand                                                   #
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
_doc = copy.deepcopy(config.load(conversions, use_cache=False))
_doc["planning"]["peak_bands"] = [{"from": "08:00", "to": "09:00"}, {"from": "15:00", "to": "16:00"}]
_doc.setdefault("tenant", {})["demo_notice"] = "Fictional scheme"
_doc["tenant"]["name"] = "Test scheme"
for _k, _v in _doc["vehicles"].items():
    if isinstance(_v, dict):
        _v["euro_class"] = "Euro VI"
ok("a scheme with two peak bands, a demo notice and every lorry Euro VI passes Config", config.validate(_doc) == [],
   str(config.validate(_doc)))
config.save(_doc, by="tester")
config.invalidate()
factors = conversions.load_factors()
WD = 22.0

PIT = network.create_location("Pit West", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=[BAL])["id"]
YARD = network.create_location("Yard East", "destination", lat=52.6447, lon=-0.8822, loc_type="Compound", receives=[BAL, PRE], supplies=[BAL, SPOIL])["id"]
PILE = network.create_location("Pile North", "destination", lat=52.58, lon=-0.92, loc_type="Stockpile", receives=[BAL])["id"]
TIP = network.create_location("Tip South", "destination", lat=52.50, lon=-0.90, loc_type="Landfill", receives=[SPOIL])["id"]
RAIL = network.create_location("Rail Head", "origin", lat=52.48, lon=-0.92, loc_type="Railhead", supplies=[PRE])["id"]
R_IN = network.create_route(PIT, YARD, material_category=BAL, route_id="R001", ipt="IPT1")["id"]
R_OUT = network.create_route(YARD, TIP, material_category=SPOIL, route_id="R002", ipt="IPT1")["id"]
R_BTW = network.create_route(YARD, PILE, material_category=BAL, route_id="R003", ipt="IPT2")["id"]
R_RAIL = network.create_route(RAIL, YARD, material_category=PRE, route_id="R004", ipt="IPT2")["id"]
R_ELSE = network.create_route(PIT, PILE, material_category=BAL, route_id="R005", ipt="IPT1")["id"]


def add_geom(rid, km, profile):
    for leg in ("loaded", "return"):
        db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
                   "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (db.current_tenant(), rid, profile, leg, 0, "[]", km, 0.5, "2026-10-30T00:00:00Z"))


add_geom(R_IN, 32.5, ART)
add_geom(R_OUT, 20.0, ART)
add_geom(R_BTW, 6.0, ART)
add_geom(R_RAIL, 22.1, FLAT)          # R005 is never drawn


def _line(rid, disc, sect, month, veh, ipt, mat, approve=True):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline=disc, section_id=sect, material_type=mat, material_description=None,
        vehicle_type=veh, submitted_by="tester", unit="t", status="Pending",
        cells=[main.Cell(month_index=m, quantity=q) for m, q in month], ipt=ipt))
    if approve:
        main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline=disc, section_id=sect)


# month 10 = Oct 2026, 11 = Nov 2026, 13 = Jan 2027 (a new quarter and a new year)
_line(R_IN, "substructure", "WS1", [(10, 2900.0), (11, 5800.0), (13, 1450.0)], ART, "IPT1", BAL)   # 100, 200, 50 loads
_line(R_OUT, "earthworks", "WS2", [(11, 2900.0)], ART, "IPT1", SPOIL)                             # 100 loads out
_line(R_BTW, "substructure", "WS3", [(10, 580.0)], ART, "IPT2", BAL)                              # 20 loads yard -> pile
_line(R_RAIL, "structures", "WS4", [(13, 1100.0)], FLAT, "IPT2", PRE)                             # precast off the railhead
_line(R_ELSE, "earthworks", "WS5", [(10, 2900.0)], ART, "IPT1", BAL)                              # pit -> pile only
_line(R_IN, "earthworks", "WS6", [(12, 290.0)], ART, "IPT1", BAL, approve=False)                  # waiting for approval
config.invalidate()
factors = conversions.load_factors()

G_IN = gates.create_gate(YARD, "Yard gate in", 52.6447, -0.8822, direction="access", safety_minutes=3,
                         is_default=True, open_from="07:30", open_to="18:00", open_days="1111100",
                         note="Check in here")
G_OUT = gates.create_gate(YARD, "Yard gate out", 52.6449, -0.8820, direction="both", open_from="07:30",
                          open_to="18:00", closed_from="2027-03-01", closed_to="2027-05-31")
ok("the two gates are made", "id" in G_IN and "id" in G_OUT, f"{G_IN} {G_OUT}")
G_IN, G_OUT = G_IN.get("id"), G_OUT.get("id")
_ar = site_areas.create_area(YARD, "Pier bases", activity="unload", service_minutes=5, bays=1, level="river terrace")
ok("the work area is made", "error" not in _ar, str(_ar))
db.execute("INSERT INTO forecast_weeks (tenant_id, route_id, month_index, discipline, section_id, week_index, planned_qty, "
           "unit, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (db.current_tenant(), R_IN, 10, "substructure", "WS1", 40, 725.0, "t", "confirmed"))


def trips(rid, disc, sect, m):
    row = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND route_id = ? AND discipline = ? AND section_id = ? "
                   "AND month_index = ?", (db.current_tenant(), rid, disc, sect, m))[0]
    return gate_arrivals.trips_for(row, factors)


# =========================================================================== #
#  A. The appendices (task 4a PR 4)                                            #
# =========================================================================== #
import clp_doc_appendices as APP            # noqa: E402
import clp_doc_appendices_render as APR     # noqa: E402
import abnormal                             # noqa: E402
import pours                                # noqa: E402
import stockpiles                           # noqa: E402
import derived                              # noqa: E402
import carbon                               # noqa: E402
import hour_times                           # noqa: E402

TEAM1, TEAM2 = "IPT1", "IPT2"
BARE = clp_doc.gather([YARD], factors=factors, working_days=WD)
A0 = APP.gather(BARE, factors=factors)
ok("⭐ nothing breaks: no appendix read failed on a plain scheme", A0["_skipped"] == [], str(A0["_skipped"]))
ok("⭐ an appendix with nothing to say is not in the answer: no reason, times, holding area, layout, closure, pour, abnormal "
   "load, stockpile, collisions or places on this scheme",
   not any(k in A0 for k in ("A", "B", "C", "D", "E", "F", "H", "I")), str(sorted(A0)))
ok("...N is always there (the method), and a site with loads has L and M", "N" in A0 and "L" in A0 and "M" in A0, str(sorted(A0)))
ok("...A, the answer's keys are letters of the template's appendix list only",
   set(k for k in A0 if k != "_skipped") <= set(APP.LETTERS), str(sorted(A0)))

# ---- A: the route schedule ------------------------------------------------------------------------------------ #
db.execute("UPDATE routes SET route_reason = ?, permitted_deviations = ? WHERE tenant_id = ? AND id = ?",
           ("The only road a 44 t lorry may use.", "Follow a signed diversion, tell the gate.", db.current_tenant(), R_IN))
for _leg in ("loaded", "return"):
    for _h, _mins in (("06:00", 0.9), ("08:00", 1.1), ("09:00", 1.0), ("12:00", 0.95), ("15:00", 1.0), ("17:00", 1.2), ("18:00", 1.0)):
        db.execute("INSERT INTO route_hour_times (tenant_id, route_id, vehicle_profile, leg, hour, rank, depart_at, fingerprint, "
                   "alt_index, geom_computed_at, distance_km, duration_hr, duration_hr_here, error, computed_at) "
                   "VALUES (?, ?, ?, ?, ?, 0, ?, ?, 0, ?, ?, ?, ?, NULL, ?)",
                   (db.current_tenant(), R_IN, ART, _leg, _h, "2026-11-03T10:00:00", "fp", "2026-10-30T00:00:00Z", 32.5,
                    _mins, _mins, "2026-10-30T00:00:00Z"))
BA = clp_doc.gather([YARD], factors=factors, working_days=WD)
AA = APP.gather(BA, factors=factors)
rowA = next((r for r in AA.get("A", {}).get("rows", []) if r["route_id"] == R_IN), None)
ok("⭐ A: a typed reason, the deviations and the times at 08:00 / 12:00 / 17:00 from the stored times (both legs + turnaround)",
   rowA and rowA["reason"].startswith("The only road") and rowA["deviations"].startswith("Follow a signed")
   and set(rowA["hours"]) == {"08:00", "12:00", "17:00"} and all(v for v in rowA["hours"].values()), str(rowA))
_ev = hour_times.evidence_block(R_IN)
ok("...the 08:00 time is the evidence block's own figure for the route (the Routes page and the collision sheet read the same)",
   rowA and rowA["hours"]["08:00"] == _ev["series"][0]["minutes"][_ev["hours"].index("08:00")], str(rowA))
ok("...a route with neither a reason nor times is not a row", all(r["route_id"] == R_IN for r in AA["A"]["rows"]))

# ---- C: a closed area that crosses a route --------------------------------------------------------------------- #
db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, hours_from, "
           "hours_to, reason_kind, reason_ref, status, source, km_delta, created_at, updated_at) "
           "VALUES (?, 'RC1', ?, ?, 'loaded', 1, '2026-12-01', '2026-12-31', NULL, NULL, 'zone', 'Z999', 'in_use', 'auto', 4.2, 'x', 'x')",
           (db.current_tenant(), R_IN, ART))
db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, hours_from, "
           "hours_to, reason_kind, reason_ref, status, source, km_delta, created_at, updated_at) "
           "VALUES (?, 'RC2', ?, ?, 'loaded', 0, '2027-02-01', '2027-02-28', NULL, NULL, 'zone', 'Z998', 'no_way_round', 'auto', NULL, 'x', 'x')",
           (db.current_tenant(), R_OUT, ART))
db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, hours_from, "
           "hours_to, reason_kind, reason_ref, status, source, km_delta, created_at, updated_at) "
           "VALUES (?, 'RC3', ?, ?, 'loaded', 1, NULL, NULL, '07:00', '10:00', 'peak', NULL, 'offered', 'auto', NULL, 'x', 'x')",
           (db.current_tenant(), R_IN, ART))
AC = APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD), factors=factors)
cr = {g["route_id"]: g for g in AC.get("C", {}).get("rows", [])}
ok("⭐ C: a zone diversion in use with its distance change, and a closure that crosses a route with NO way round (Q4); "
   "a peak-hour offer is not a closure",
   set(cr) == {R_IN, R_OUT} and cr[R_IN]["status"] == "in_use" and cr[R_IN]["km_delta"] == 4.2
   and cr[R_OUT]["status"] == "no_way_round" and cr[R_OUT]["km_delta"] is None, str(cr))
ok("...every status the table prints has a sentence", set(APP.DIVERSION_WORDS) == {"in_use", "needs_route", "no_way_round", "declined"})
ok("...a route outside the CLP is not a row (the quarry's route to the pile)",
   "R005" not in cr and all(r in {R_IN, R_OUT} for r in cr))

# ---- F: storage ------------------------------------------------------------------------------------------------ #
stockpiles.set_capacity(PILE, 5000.0, "t", 0.0)
stockpiles.set_plan(PILE, 10, 13, planned_qty=300.0, note="test")
DPILE = clp_doc.gather([PILE], factors=factors, working_days=WD)
AF = APP.gather(DPILE, factors=factors)
ok("⭐ F: a site with a capacity or a planned use gets its monthly stock, and only the CLP's own sites",
   "F" in AF and [s["site"] for s in AF["F"]["sites"]] == ["Pile North"] and AF["F"]["sites"][0]["capacity"] == 5000.0
   and "F" not in APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD), factors=factors), str(AF.get("F"))[:200])
_bal = next(s for s in stockpiles.balances(1, 60)["stockpiles"] if s["location_id"] == PILE)
_m10 = next(m for m in AF["F"]["sites"][0]["months"] if m["month"] == 10)
_wk10 = [w for w in _bal["weeks"] if w["month_index"] == 10]
ok("...a month's stock is the stockpile read's last week of the month, its flow the sum of the weeks",
   abs(_m10["end"] - round(_wk10[-1]["balance_end"], 1)) < 0.06 and abs(_m10["in"] - round(sum(w["inbound"] for w in _wk10), 1)) < 0.06,
   f"{_m10} {_wk10[-1]['balance_end']}")

# ---- E: abnormal loads, with the team cut ---------------------------------------------------------------------- #
_ab = abnormal.create({"name": "Test unit", "origin_id": PIT, "dest_id": YARD, "date_from": "2026-12-07", "date_to": "2026-12-11",
                       "width_m": 4.2, "height_m": 3.5, "length_m": 14.0, "gross_t": 60.0, "ipt": TEAM1, "status": "approved"},
                      {"role": "planner"}, by="tester")
ok("an abnormal load is made for the test", isinstance(_ab, dict) and _ab.get("ok") and _ab["movement"]["id"], str(_ab)[:200])
abnormal.set_status(_ab["movement"]["id"], "approved", {"role": "planner"}, by="tester")
_ab2 = abnormal.create({"name": "Other team unit", "origin_id": PIT, "dest_id": PILE, "date_from": "2026-12-07", "date_to": "2026-12-11",
                        "width_m": 4.2, "height_m": 3.5, "length_m": 14.0, "gross_t": 60.0, "ipt": TEAM2, "status": "approved"},
                       {"role": "planner"}, by="tester")
abnormal.set_status(_ab2["movement"]["id"], "approved", {"role": "planner"}, by="tester")
AE = APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD), factors=factors)
ok("⭐ E: loads to or from the sites only (the load to the pile is not the yard's), with size, status and notice dates",
   [r["name"] for r in AE.get("E", {}).get("rows", [])] == ["Test unit"] and AE["E"]["rows"][0]["width_m"] == 4.2
   and AE["E"]["rows"][0]["status"] == "Approved" and AE["E"]["rows"][0]["notify_by"], str(AE.get("E")))
ok("...the other team's load is not in the team's appendix, nor the first team's in the other's",
   not APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD, team=TEAM2), factors=factors).get("E")
   and [r["name"] for r in APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD, team=TEAM1),
                                      factors=factors)["E"]["rows"]] == ["Test unit"])

# ---- D: pours (read stubbed: the demo's pours are made on a mixer line this scheme does not have) ------------------ #
_real = (pours.list_pours, pours.decorate)
_PR = [{"id": "P901", "route_id": R_IN, "pour_date": "2027-01-12", "start": "08:00", "m3": 60.0, "status": "planned", "ipt": TEAM1},
       {"id": "P902", "route_id": R_BTW, "pour_date": "2027-01-13", "start": "09:00", "m3": 30.0, "status": "planned", "ipt": TEAM2},
       {"id": "P903", "route_id": R_ELSE, "pour_date": "2027-01-14", "start": "09:00", "m3": 30.0, "status": "planned", "ipt": TEAM1}]
pours.list_pours = lambda **k: [dict(p) for p in _PR]
pours.decorate = lambda rows, factors=None, **k: [dict(p, origin_name="Pit", dest_name="Yard", gate_name="Yard gate in",
                                                         vehicle_name="Mixer", figures={"loads": 8, "needed": 6, "booked": None,
                                                                                         "transit": 82.5, "ends": "12:15",
                                                                                         "limits": {"transit_min": 120.0, "cold_joint_min": 30.0}},
                                                         flags=[{"code": "POUR_BAND"}]) for p in rows]
try:
    AD = APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD), factors=factors)
    AD1 = APP.gather(clp_doc.gather([YARD], factors=factors, working_days=WD, team=TEAM1), factors=factors)
    AD2 = APP.gather(clp_doc.gather([YARD, PILE], factors=factors, working_days=WD), factors=factors)
finally:
    pours.list_pours, pours.decorate = _real
ok("⭐ D: pours on the CLP's routes only: the yard's CLP has the pours on its two routes, not the quarry-to-pile route's; "
   "add the pile and that route's pour joins",
   [r["id"] for r in AD["D"]["rows"]] == ["P901", "P902"] and [r["id"] for r in AD2["D"]["rows"]] == ["P901", "P902", "P903"],
   str([r["id"] for r in AD["D"]["rows"]]))
ok("...a team's CLP holds that team's pours only; the flags are the screens' words",
   [r["id"] for r in AD1["D"]["rows"]] == ["P901"] and AD["D"]["rows"][0]["flags"] == ["IN A BAND"], str(AD1.get("D")))

# ---- L, M, G, J, K: figures equal the modules that own them ------------------------------------------------------- #
AL = APP.gather(BA, factors=factors)
gl = AL["L"]["gates"][0]
a11 = gate_arrivals.arrivals(11, {"role": "planner"}, factors=factors, working_days=WD)
g11 = next(g for g in a11["gates"] if g["location_id"] == YARD and g["arrivals_per_day"])
r11 = next(r for r in gl["rows"] if r["month"] == 11)
ok("⭐ L: arrivals a day and capacity % per month are Gate arrivals' own", abs(r11["arrivals"] - round(g11["arrivals_per_day"], 1)) < 0.06
   and r11["pct"] == g11["capacity_pct"], f"{r11} {g11['arrivals_per_day']}")
ok("...one table row per month with arrivals, in month order",
   [r["month"] for r in gl["rows"]] == sorted(r["month"] for r in gl["rows"]) and {r["month"] for r in gl["rows"]} <= {10, 11, 13})
tm = clp_doc.gather([YARD], factors=factors, working_days=WD, team=TEAM1)
AL1 = APP.gather(tm, factors=factors)
ok("⭐ a team's L is the team's own arrivals (the capacity % stays every team's, and says so)",
   AL1["L"]["all_teams_pct"] and AL1["L"]["gates"][0]["rows"][0]["arrivals"] <= gl["rows"][0]["arrivals"] + 0.06, str(AL1["L"]["gates"][0]["rows"][:1]))
ok("⭐ K: the Simulation's day is left out of a team's CLP (Q2) and held for the whole plan",
   "K" not in AL1 and "K" in AL, str(sorted(AL1)))
AM = AL["M"]
_cache = {}
_rowm = derived.cycle_for(R_IN, ART, _cache, month_index=BA["totals"]["peak_month"])
_mr = next(r for r in AM["rows"] if r["route_id"] == R_IN)
ok("⭐ M: lorries needed = ceil(loads ÷ (round trips a lorry makes a day × working days)), the trips from the drivers' hours rule",
   _mr["per_lorry"] == int(_rowm["trips_per_day"]) and _mr["lorries"] == carbon.lorries_for(_mr["trips"], _rowm["trips_per_day"], WD)
   and AM["month"] == BA["totals"]["peak_month"], f"{_mr} {_rowm.get('trips_per_day')}")
ok("...a route that is not drawn says so and counts no lorry (R004 is never drawn for the flatbed)",
   AM["unrouted"] >= 0 and AM["total"] == sum(r["lorries"] or 0 for r in AM["rows"]))
ok("G: the carbon rows are the plan's lines on the CLP's routes, by month, from the Carbon planner",
   "G" not in AL or (all(m["trips"] > 0 for m in AL["G"]["months"])
                     and sum(m["trips"] for m in AL["G"]["months"]) == BA["totals"]["trips"]), str(AL.get("G", {}).get("months", [])[:2]))

# ---- the Word file --------------------------------------------------------------------------------------------- #
def _doc_text(w):
    out = [p.text for p in w.paragraphs]
    for t in w.tables:
        for r in t.rows:
            for c in r.cells:
                out.append(c.text)
    return out


BIG = clp_doc.gather([YARD, PILE], factors=factors, working_days=WD)
WB = Document(io.BytesIO(clp_doc.build(BIG, pictures=False)))
heads = [p.text for p in WB.paragraphs if p.style.name.startswith("Heading")]
i7 = next(i for i, h in enumerate(heads) if h.startswith("7 Implementing"))
ap = [h for h in heads[i7:] if h.startswith("Appendi")]
ok("⭐ the appendices come after section 7, 'Appendices' first, then the letters in order, N last",
   ap[0] == "Appendices" and [h.split(" ")[1] for h in ap[1:]] == sorted(h.split(" ")[1] for h in ap[1:])
   and ap[-1].startswith("Appendix N "), str(ap))
ok("...the first page says what is printed and what is left out, by name",
   any(p.text.startswith("Printed: ") for p in WB.paragraphs) and any(p.text.startswith("Left out, because") for p in WB.paragraphs))
ok("...an appendix with no data has no heading", not any(h.startswith("Appendix B ") or h.startswith("Appendix H ") for h in heads))
ok("🔴 no banned word or back-end word in any paragraph or table of the whole file",
   not [x for x in _doc_text(WB) if clp_doc.banned_words(x)], str([x[:60] for x in _doc_text(WB) if clp_doc.banned_words(x)][:3]))
ok("...no appendix adds a 'To complete' line (the Still to complete list is section 1-7's)",
   all(not (p.style.name == "To complete") for p in WB.paragraphs[[p.text for p in WB.paragraphs].index("Appendices"):]))
ok("O: no history, no Appendix O; with a history it is one pointer line",
   not any(h.startswith("Appendix O") for h in heads))
_bh = clp_doc.gather([YARD], factors=factors, working_days=WD)
_bh["history"] = [{"no": 1, "date": "2026-11-01", "by": "A. Planner", "words": "First issue."}]
WH = Document(io.BytesIO(clp_doc.build(_bh, pictures=False)))
ok("...and with a history it is one pointer line", any(p.text.startswith("Appendix O") for p in WH.paragraphs)
   and any("Document history table at the front" in p.text for p in WH.paragraphs))
WN = Document(io.BytesIO(clp_doc.build(clp_doc.gather([YARD], factors=factors, working_days=WD), pictures=False, appendices=False)))
ok("appendices=False builds the document without them", not any(p.text.startswith("Appendi") for p in WN.paragraphs))
ok("a team's file has appendices too, and none of the other team's pour or load",
   any(p.text == "Appendices" for p in Document(io.BytesIO(clp_doc.build(tm, pictures=False))).paragraphs))
ok("data keeps the letters printed", BIG.get("appendix_letters") and "N" in BIG["appendix_letters"] and BIG["appendices_skipped"] == [])

# ---- found on live 1 Nov 2026 (L019): an H line for a route with no offers, and clock times without a leading zero ---- #
import collisions                           # noqa: E402
_fake = {"layers": {"collisions": {"fetched": True, "rows": [{"route_id": "R001"}], "period": "2021 to 2025"}},
         "routes": [{"route_id": "R001"}], "team": None}
_real_bh = collisions.busy_hours
collisions.busy_hours = lambda rid, acc=None: {"shown": True, "offers": [], "period": "2021 to 2025"}
try:
    _h0 = APP._h_collisions(_fake, {})
    collisions.busy_hours = lambda rid, acc=None: {"shown": True, "offers": [{"label": "Alternative 1", "alt": 1, "bands": [
        {"from": "07:00", "to": "10:00", "route": 17, "alt": 5}], "midday": None}], "period": "2021 to 2025"}
    _h1 = APP._h_collisions(_fake, {})
finally:
    collisions.busy_hours = _real_bh
ok("⭐ H: a route whose busy-hour read shows no offer is not a line (no empty 'R001:'); one with an offer is, in words",
   _h0["busy"] == [] and [b["route_id"] for b in _h1["busy"]] == ["R001"] and "5 against 17" in _h1["busy"][0]["offers"][0], str((_h0, _h1)))
ok("a clock time prints with two digits for the hour (07:47, not 7:47)", APR._hm(467.88) == "07:47" and APR._hm(None) == "—")

# ---- the source ---------------------------------------------------------------------------------------------- #
for nm in ("clp_doc_appendices.py", "clp_doc_appendices_render.py"):
    src = open(os.path.join(BACKEND, nm), encoding="utf-8").read()
    ok(f"🔴 {nm} reads only: no INSERT, UPDATE or DELETE", not re.search(r"\b(INSERT|UPDATE|DELETE)\b", src))
    ok(f"🔴 {nm} never fetches or calls an outside service", not re.search(r"^\s*(import|from)\s+(here_routing|basemap|requests|urllib|httpx|haul)\b", src, re.M))
    qs = re.findall(r'"(SELECT[^"]*)"', src)
    ok(f"🔴 {nm}: every SQL literal carries the tenant predicate", all("tenant_id = ?" in q for q in qs), str(qs))
    ok(f"🔴 {nm}: no team slot id, no BOOLEAN compared with a number",
       re.search(r"\bIPT ?[1-6]\b", src) is None and not re.search(r"\bactive\s*=\s*1\b", src))
ok("the appendices are built inside the CLP build's lock (heavy_reads.solo in main.py wraps clp_doc.build)",
   'heavy_reads.solo("clp-document"' in open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read())

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\ntest_clp_doc_appendices: {PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
