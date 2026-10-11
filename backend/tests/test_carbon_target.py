"""
Carbon target, 11 Oct 2026 (before the freeze) — backend/carbon_target.py, GET / PUT / DELETE
/api/carbon/target in main.py, and the all-in `carbon` block on POST /api/costing/preview.

What is asserted, every expected figure worked by hand in the comment beside it:
  * setting a "% below the approved plan" target from a known set of decisions: the server runs
    carbon.scenario itself and stores pct_below, cap_t, set_at_approved_t, set_at_alternative_t,
    the decisions and their words, the page state and the audit fields;
  * progress in both modes for the planner (scope "scheme") and two team codes (scope "team"; a
    fixed cap has no team share, so target_t is null there): as forecast, with the decisions, the
    gaps, the lines waiting for approval, the transport part and the months;
  * switching pct <-> cap without decisions keeps every number;
  * the refusals, each a 400 with a plain sentence that leaves the stored target untouched: no
    decisions, decisions that do not lower carbon (higher, unchanged, under 0.1 %), a bad mode, an
    oversized page state, decisions the rules refuse, a switch with no target;
  * 403 for a team code and the demo submitter on PUT and DELETE, 401 with no code on all three;
  * the row is tenant-scoped (a second tenant sees none) and travels in the tenant package; the
    demo package carries none;
  * decisions that stop applying (a route deleted) give status.invalid, never an error;
  * the preview's carbon: a delivery line, a muck-away line to a landfill, a muck-away line to a
    soil hub, an unrouted line, a material with no factor, no cells;
  * carbon.py still writes nothing.

WHAT THIS DOES NOT PROVE
------------------------
  * Anything over HTTP (http_smoke.py does the 401 / 403 / 200 and a round trip on the demo
    package) or in a browser. The route geometry is seeded by hand, not baked by HERE.
  * PostgreSQL: SQLite only. The row is the same config table the costing settings use.
  * That a scheme-wide % is reachable by every team: a team code sees the same % applied to its
    own lines, which is the contract, not a judgement that each team can meet it.

Run:  python3 backend/tests/test_carbon_target.py
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

# ---- stubs, verbatim from test_carbon.py -----------------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_ctarget_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
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
import costlines  # noqa: E402
import carbon  # noqa: E402
import carbon_target  # noqa: E402
import tenant_package  # noqa: E402
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


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def as_team(n):
    """Sign in as team n's code (a real configured code; the demo codes stop while it is set)."""
    os.environ[f"IPT{n}_CODE"] = f"team{n}-secret"
    try:
        access.set_current(f"team{n}-secret")
    finally:
        os.environ.pop(f"IPT{n}_CODE", None)
    return access.current()


ART = "Artic Tipper (44t)"
SA, SOIL = "Small aggregate", "Earthworks / soil"

# =========================================================================== #
#  0. A small network, seeded by hand                                           #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
config.invalidate()
config.seed_from_file(conversions)
config.invalidate()
costing.invalidate()
carbon_target.invalidate()
access.set_current("planner123")
for _id, _name, _type in (("L1", "Pit A", "Quarry"), ("L2", "Compound", "Compound"), ("L3", "Tip", "Landfill"),
                          ("L4", "Soil hub", "Soil recycling"), ("L5", "Pit B", "Quarry"), ("L6", "Pit C", "Quarry")):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", (_id, _name, 52.5, -1.0, _type))
for _rid, _o, _d, _m in (("R1", "L1", "L2", SA), ("R2", "L5", "L2", SA), ("R3", "L2", "L3", SOIL),
                         ("R4", "L2", "L4", SOIL), ("R5", "L6", "L2", SA)):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, ?)", (_rid, _o, _d, _m, "IPT 1"))


def _geom(rid, prof, leg, km, hr, alt=0):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, "
               "geometry, distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               ("default", rid, prof, leg, alt, "[[-1,52.5],[-1.1,52.6]]", km, hr))


# R1 artic 30/30 km; R2 10/10; R3 20/20 (to the landfill); R4 8/8 (to the soil hub); R5 NOT BAKED
for _rid, _l, _r, _lh, _rh in (("R1", 30, 30, 0.6, 0.5), ("R2", 10, 10, 0.25, 0.2),
                               ("R3", 20, 20, 0.4, 0.35), ("R4", 8, 8, 0.2, 0.15)):
    _geom(_rid, ART, "loaded", _l, _lh); _geom(_rid, ART, "return", _r, _rh)


def _line(rid, sect, month, qty, mat, ipt, approve=True):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type=mat, material_description=None,
        vehicle_type=ART, submitted_by="tester", unit="t", status="Pending",
        cells=[main.Cell(month_index=month, quantity=qty)], ipt=ipt))
    if approve:
        main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id=sect)


_line("R1", "WS1", 10, 2900.0, SA, "IPT1")       # 100 trips at 29 t, 30 + 30 km
_line("R3", "WS2", 10, 5800.0, SOIL, "IPT2")     # 200 trips, muck-away to the LANDFILL, 20 + 20 km
_line("R2", "WS3", 11, 1450.0, SA, "IPT1")       # 50 trips, 10 + 10 km
_line("R1", "WS4", 11, 580.0, SA, "IPT1", approve=False)   # PENDING: 20 trips, waiting for approval
config.invalidate()

# The approved plan, by hand (aggregates 7.80307 kg/t primary, 3.22398 closed-loop; soils to landfill
# 19.55376 kg/t, closed-loop 1.01398; the artic 0.93939 kg CO2e per km; 29 t a load):
#   R1  material 2900 × 7.80307 = 22.628903   transport 100 × 60 × 0.93939 = 5.63634   → 28.265243
#   R3  disposal 5800 × 19.55376 = 113.411808 transport 200 × 40 × 0.93939 = 7.51512   → 120.926928
#   R2  material 1450 × 7.80307 = 11.3144515  transport  50 × 20 × 0.93939 = 0.93939   → 12.2538415
#   approved plan = 161.4460125 t; transport 14.09085 t
# The decisions: 30 % recycled content on Small aggregate, and R3's soil to the soil hub (R4):
#   R1  2900 × (0.7 × 7.80307 + 0.3 × 3.22398 = 6.429343) = 18.6450947 + 5.63634     → 24.2814347
#   R3→R4  disposal 5800 × 1.01398 = 5.881084; transport 200 × 16 × 0.93939 = 3.006048 → 8.887132
#   R2  1450 × 6.429343 = 9.32254735 + 0.93939                                         → 10.26193735
#   with the decisions = 43.43050405 t; −118.01550845 t = 73.0990…% → 73.1 %
# Pending: R1 WS4 580 × 7.80307 = 4.5257806 + 20 × 60 × 0.93939 = 1.127268 → 5.6530486
DECISIONS = [{"driver": "recycled", "scope": {"category": SA}, "pct": 30},
             {"driver": "disposal", "scope": {"route_id": "R3"}, "to_route": "R4"}]
UI = {"recycled": {SA: 30}, "epd": {}, "reused": {}, "vehicle": {}, "electric": False, "distance": {},
      "supplier": {}, "alt": {}, "disposal": {"R3": {"to_route": "R4"}}}


def PUT(**kw):
    return main.put_carbon_target(main.CarbonTargetIn(**kw))


def GET():
    return main.get_carbon_target()


# =========================================================================== #
#  1. No target                                                                 #
# =========================================================================== #
ok("⭐ no target yet: GET says so, target and status both null", GET() == {"target": None, "status": None})
e = _raises(lambda: PUT(mode="cap", updated_by="Sam"))
ok("🔴 switching how a target is held when there is none is a 400 with a plain sentence",
   getattr(e, "status_code", None) == 400 and e.detail == "There is no target to change yet: set one on the Carbon page first.", repr(e))
ok("...and nothing was written", carbon_target.get_row() is None and GET()["target"] is None)

# =========================================================================== #
#  2. Setting a % target from the agreed decisions                              #
# =========================================================================== #
_q = {"n": 0, "x": 0}
_oq, _ox = db.query, db.execute
db.query = lambda *a, **k: (_q.__setitem__("n", _q["n"] + 1), _oq(*a, **k))[1]
db.execute = lambda *a, **k: (_q.__setitem__("x", _q["x"] + 1), _ox(*a, **k))[1]
try:
    P = PUT(mode="pct", levers=DECISIONS, ui_state=UI, updated_by="Sam (planner)")
finally:
    db.query, db.execute = _oq, _ox
T = P["target"]
ok("⭐ the server works the target out: 73.1 % below the approved plan (−118.016 of 161.446 t, on the unrounded sums)",
   T["mode"] == "pct" and T["pct_below"] == 73.1, str(T))
ok("⭐ ...the plan with the decisions is the cap figure: 43.431 t (43.43050405); set at 161.446 → 43.431",
   T["cap_t"] == 43.431 and T["set_at_approved_t"] == 161.446 and T["set_at_alternative_t"] == 43.431, str(T))
ok("...the decisions are stored as sent, with their words, and the page's state as sent",
   T["levers"] == DECISIONS and T["ui_state"] == UI
   and T["lever_words"] == ["Recycled content 30% — Small aggregate", "Receiving site: Soil hub (route R4) — route R3: Compound → Tip"],
   str(T["lever_words"]))
ok("⭐ audit: updated_by is the name typed at sign-in; updated_at is server UTC",
   T["updated_by"] == "Sam (planner)" and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", T["updated_at"] or ""), str(T))
ok("the write is ONE statement (an INSERT into config), the rest are reads", _q["x"] == 1, str(_q))
_row = db.query("SELECT tenant_id, key, value, updated_by FROM config WHERE key = ?", ("carbon_target",))
ok("⭐ stored as ONE tenanted config row, key carbon_target, holding exactly the document's keys",
   len(_row) == 1 and _row[0]["tenant_id"] == "default" and _row[0]["updated_by"] == "Sam (planner)"
   and sorted(json.loads(_row[0]["value"])) == sorted(["mode", "pct_below", "cap_t", "set_at_approved_t", "set_at_alternative_t",
                                                       "levers", "lever_words", "ui_state"]), str(_row)[:300])
ok("the response keys are the contract's",
   sorted(P) == ["status", "target"] and sorted(T) == sorted(["mode", "pct_below", "cap_t", "set_at_approved_t", "set_at_alternative_t",
                                                              "levers", "lever_words", "ui_state", "updated_by", "updated_at"])
   and sorted(P["status"]) == sorted(["scope", "approved_t", "with_decisions_t", "target_t", "gap_as_forecast_t",
                                      "gap_with_decisions_t", "pending_t", "approved_transport_t", "by_month", "invalid"]))

# =========================================================================== #
#  3. Progress, % mode                                                          #
# =========================================================================== #
_q = {"n": 0, "x": 0}
db.query = lambda *a, **k: (_q.__setitem__("n", _q["n"] + 1), _oq(*a, **k))[1]
db.execute = lambda *a, **k: (_q.__setitem__("x", _q["x"] + 1), _ox(*a, **k))[1]
try:
    G = GET()
finally:
    db.query, db.execute = _oq, _ox
S = G["status"]
ok("🔴 the read writes nothing", _q["x"] == 0, str(_q))
ok("...within a sane statement budget (two scenarios: the approved plan and the pending lines)", _q["n"] <= 120, str(_q))
ok("⭐ planner: scope scheme; approved plan as forecast 161.446 t; with the decisions 43.431 t",
   S["scope"] == "scheme" and S["approved_t"] == 161.446 and S["with_decisions_t"] == 43.431, str(S))
# 161.446 × (1 − 0.731) = 43.428974 → 43.429; 161.446 − 43.429 = 118.017; 43.431 − 43.429 = 0.002
ok("⭐ % mode: target = approved × (1 − 73.1 %) = 43.429 t; as forecast 118.017 over; with the decisions 0.002 over",
   S["target_t"] == 43.429 and S["gap_as_forecast_t"] == 118.017 and S["gap_with_decisions_t"] == 0.002, str(S))
ok("⭐ the lines waiting for approval would add 5.653 t (580 t of aggregate, 20 trips of 60 km)",
   S["pending_t"] == 5.653, str(S["pending_t"]))
ok("the approved plan's transport part, 14.091 t (5.63634 + 7.51512 + 0.93939), ties to the Dashboard's transport sum",
   near(S["approved_transport_t"], 14.091, 0.0011)
   and near(S["approved_transport_t"], sum(l["co2_t"] for l in costlines.lines(status="Approved")["lines"]), 0.002), str(S))
# month 10: R1 + R3 = 149.192171 → 33.1685667 with; month 11: R2 12.2538415 → 10.26193735 with
ok("⭐ by month: Oct 149.192 → 33.169, Nov 12.254 → 10.262 (they add up to the totals)",
   S["by_month"] == [{"month_index": 10, "approved_t": 149.192, "with_decisions_t": 33.169},
                     {"month_index": 11, "approved_t": 12.254, "with_decisions_t": 10.262}], str(S["by_month"]))
ok("...and nothing is invalid", S["invalid"] is None)
ok("the target is cached per tenant and the cache returns a copy (a caller cannot change it)",
   (lambda t: (t.__setitem__("pct_below", 1.0), carbon_target.get()["pct_below"] == 73.1)[1])(carbon_target.get()))

# a team code: its own lines only, the same % applied to them
as_team(2)
S2 = GET()["status"]
# R3 only: 120.926928 → 120.927; with 8.887132 → 8.887; × 0.269 = 32.529363 → 32.529
ok("⭐ team code (Central's soil line only): scope team, 120.927 as forecast, 8.887 with the decisions",
   S2["scope"] == "team" and S2["approved_t"] == 120.927 and S2["with_decisions_t"] == 8.887, str(S2))
ok("⭐ ...% mode applies to the team's own plan: target 32.529; 88.398 over as forecast; 23.642 under with the decisions",
   S2["target_t"] == 32.529 and S2["gap_as_forecast_t"] == 88.398 and S2["gap_with_decisions_t"] == -23.642, str(S2))
ok("...no pending lines of its own; its transport 7.515; one month",
   S2["pending_t"] == 0.0 and near(S2["approved_transport_t"], 7.515, 0.0011)
   and S2["by_month"] == [{"month_index": 10, "approved_t": 120.927, "with_decisions_t": 8.887}], str(S2))
as_team(1)
S1 = GET()["status"]
# R1 + R2: 40.5190845 → 40.519; with 34.54337205 → 34.543; × 0.269 = 10.899611 → 10.9; pending 5.653
ok("team 1 (the aggregate lines): 40.519 → 34.543 with the decisions; target 10.9; its pending 5.653",
   S1["scope"] == "team" and S1["approved_t"] == 40.519 and S1["with_decisions_t"] == 34.543 and S1["target_t"] == 10.9
   and S1["gap_as_forecast_t"] == 29.619 and S1["gap_with_decisions_t"] == 23.643 and S1["pending_t"] == 5.653, str(S1))
access.set_current("submitter123")
ok("the demo submitter sees every line: scope scheme, the planner's figures",
   GET()["status"] == S)
access.set_current("planner123")

# =========================================================================== #
#  4. Switching to a fixed cap and back keeps every number                       #
# =========================================================================== #
C = PUT(mode="cap", updated_by="Alex (admin)")
CT, CS = C["target"], C["status"]
ok("⭐ the switch needs no decisions and keeps every number: cap 43.431, 73.1 %, 161.446 → 43.431, same decisions and state",
   CT["mode"] == "cap" and CT["cap_t"] == 43.431 and CT["pct_below"] == 73.1 and CT["set_at_approved_t"] == 161.446
   and CT["set_at_alternative_t"] == 43.431 and CT["levers"] == DECISIONS and CT["ui_state"] == UI
   and CT["lever_words"] == T["lever_words"], str(CT))
ok("...and stamps who switched it", CT["updated_by"] == "Alex (admin)")
# 161.446 − 43.431 = 118.015; 43.431 − 43.431 = 0
ok("⭐ cap mode, planner: target 43.431 t; 118.015 over as forecast; on target with the decisions (0.0)",
   CS["scope"] == "scheme" and CS["target_t"] == 43.431 and CS["gap_as_forecast_t"] == 118.015
   and CS["gap_with_decisions_t"] == 0.0 and CS["approved_t"] == 161.446 and CS["pending_t"] == 5.653, str(CS))
as_team(2)
CS2 = GET()["status"]
ok("🔴 cap mode, team code: a fixed scheme cap has no team share — target_t and both gaps null, the plan figures still there",
   CS2["scope"] == "team" and CS2["target_t"] is None and CS2["gap_as_forecast_t"] is None and CS2["gap_with_decisions_t"] is None
   and CS2["approved_t"] == 120.927 and CS2["with_decisions_t"] == 8.887, str(CS2))
access.set_current("planner123")
B = PUT(mode="pct", updated_by="Sam (planner)")
ok("...and back to % mode: the same numbers as when it was set", B["target"]["pct_below"] == 73.1 and B["target"]["cap_t"] == 43.431
   and B["status"]["target_t"] == 43.429 and B["target"]["mode"] == "pct")
ok("a switch sent with an empty body's mode left out is refused (mode is required)",
   getattr(_raises(lambda: PUT(updated_by="x")), "status_code", None) == 400)

# =========================================================================== #
#  5. Refusals: each a 400 with a plain sentence, the target untouched           #
# =========================================================================== #
_before = carbon_target.get(use_cache=False)
for _label, _kw, _want in (
        ("no decisions", dict(mode="pct", levers=[]), "Choose at least one decision before setting a target."),
        # R2's 50 loads moved onto R1's 60 km: 50 × 60 × 0.93939 = 2.81817 against 0.93939 → +1.879 t
        ("decisions that RAISE carbon", dict(mode="pct", levers=[{"driver": "source", "scope": {"route_id": "R2"}, "to_route": "R1"}]),
         "These decisions do not lower carbon, so no target was set."),
        # HERE alternative 2 is not baked on R1: flagged, nothing changes → delta 0
        ("decisions that change nothing", dict(mode="cap", levers=[{"driver": "route", "scope": {"route_id": "R1"}, "alt_index": 2}]),
         "These decisions do not lower carbon, so no target was set."),
        # R2 at 99.9 % of its distance: 0.93939 × 0.001 = 0.00094 t of 161.446 → 0.0006 %
        ("decisions that lower carbon by under 0.1 %", dict(mode="pct", levers=[{"driver": "source", "scope": {"route_id": "R2"}, "distance_pct": 99.9}]),
         "These decisions lower carbon by less than 0.1%, so no target was set."),
        ("a bad mode", dict(mode="half", levers=DECISIONS), "Choose how to hold the target: % below the approved plan, or a fixed tCO2e cap."),
        ("no mode", dict(levers=DECISIONS), "Choose how to hold the target: % below the approved plan, or a fixed tCO2e cap."),
        ("a page state over 20 000 characters", dict(mode="pct", levers=DECISIONS, ui_state={"x": "a" * 20000}),
         "The page state is too large to store (at most 20 000 characters)."),
        ("decisions the rules refuse (an unknown vehicle)", dict(mode="pct", levers=[{"driver": "vehicle", "vehicle": "Hovercraft"}]),
         "These decisions cannot be worked out: vehicle 'Hovercraft' is not on Config."),
        ("decisions the rules refuse (a supplier swap to another destination)",
         dict(mode="pct", levers=[{"driver": "source", "scope": {"route_id": "R1"}, "to_route": "R3"}]),
         "These decisions cannot be worked out: a supplier swap must keep the destination: R3 goes elsewhere.")):
    e = _raises(lambda kw=_kw: PUT(updated_by="Mallory", **kw))
    ok(f"🔴 {_label} → 400: “{_want}”", getattr(e, "status_code", None) == 400 and getattr(e, "detail", None) == _want, repr(e))
_after = carbon_target.get(use_cache=False)
ok("⭐ ...and not one refusal changed the stored target (still 73.1 %, still Sam's)", _after == _before and _after["updated_by"] == "Sam (planner)")
ok("a page state of exactly 20 000 characters of JSON is accepted (the limit is inclusive)",
   PUT(mode="pct", levers=DECISIONS, ui_state={"x": "a" * (20000 - len(json.dumps({"x": ""})))}, updated_by="Sam (planner)")["target"]["pct_below"] == 73.1)
PUT(mode="pct", levers=DECISIONS, ui_state=UI, updated_by="Sam (planner)")

# =========================================================================== #
#  6. Who may write                                                             #
# =========================================================================== #
as_team(2)
for _label, _fn in (("PUT", lambda: PUT(mode="cap")), ("DELETE", lambda: main.delete_carbon_target())):
    e = _raises(_fn)
    ok(f"🔴 a team code cannot {_label} the target — 403", getattr(e, "status_code", None) == 403, repr(e))
access.set_current("submitter123")
for _label, _fn in (("PUT", lambda: PUT(mode="cap")), ("DELETE", lambda: main.delete_carbon_target())):
    e = _raises(_fn)
    ok(f"🔴 the demo submitter cannot {_label} the target — 403", getattr(e, "status_code", None) == 403, repr(e))
access.set_current(None)
for _label, _fn in (("GET", GET), ("PUT", lambda: PUT(mode="cap")), ("DELETE", lambda: main.delete_carbon_target())):
    e = _raises(_fn)
    ok(f"🔴 no code → 401 on {_label}", getattr(e, "status_code", None) == 401, repr(e))
access.set_current("planner123")
ok("...and none of them touched it", carbon_target.get(use_cache=False)["mode"] == "pct"
   and carbon_target.get(use_cache=False)["updated_by"] == "Sam (planner)")
access.set_current("admin123")
ok("an admin code may write (the switch, by an admin)", PUT(mode="pct", updated_by="Admin")["target"]["updated_by"] == "Admin")
access.set_current("planner123")
PUT(mode="pct", levers=DECISIONS, ui_state=UI, updated_by="Sam (planner)")

# =========================================================================== #
#  7. The fixture the render harness draws step 6 and the strips from            #
# =========================================================================== #
def _scrub(o):
    if isinstance(o, dict):
        return {k: ("<ts>" if k.endswith("_at") and isinstance(v, str) else _scrub(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(x) for x in o]
    return o


FX = GET()
_fix = os.path.join(HERE, "fixtures", "carbon_target.json")
with open(_fix, "w", encoding="utf-8", newline=chr(10)) as fh:
    fh.write(json.dumps(_scrub(FX), indent=1, ensure_ascii=False, sort_keys=True) + chr(10))
ok("the carbon-target fixture is written (a % target, the planner's GET)", os.path.exists(_fix)
   and json.load(open(_fix, encoding="utf-8"))["target"]["mode"] == "pct"
   and json.load(open(_fix, encoding="utf-8"))["target"]["updated_at"] == "<ts>")

# =========================================================================== #
#  8. Tenant scope and the package                                              #
# =========================================================================== #
_tok = db.set_current_tenant("tenant-b")
try:
    ok("🔴 a second tenant sees no target (the cache is keyed by tenant too)",
       carbon_target.get() is None and GET() == {"target": None, "status": None})
    ok("...and its export carries no carbon_target row",
       not [r for r in tenant_package.export_tenant()["tables"]["config"] if r.get("key") == "carbon_target"])
finally:
    db.reset_current_tenant(_tok)
ok("...while the first still has its own", carbon_target.get()["pct_below"] == 73.1)
_pk = tenant_package.export_tenant()
_ct = [r for r in _pk["tables"]["config"] if r.get("key") == "carbon_target"]
ok("⭐ the tenant package carries the target like every config row (key, value, updated_by)",
   len(_ct) == 1 and json.loads(_ct[0]["value"])["pct_below"] == 73.1 and _ct[0]["updated_by"] == "Sam (planner)")
_demo = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
ok("🔴 the demo package ships NO target (a planner sets one at the show)",
   [r["key"] for r in _demo["tables"]["config"]] == ["costing", "factors", "overlay"])

# =========================================================================== #
#  9. Decisions that stop applying                                              #
# =========================================================================== #
_r4 = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", ("default", "R4"))[0]
db.execute("DELETE FROM routes WHERE tenant_id = ? AND id = ?", ("default", "R4"))
try:
    e = None
    try:
        GI = GET()
    except Exception as ex:
        e, GI = ex, {"status": {}}
    SI = GI["status"]
    ok("🔴 the soil hub's route deleted: the read still answers (no error)", e is None, repr(e))
    ok("⭐ ...status.invalid says why in a sentence; the plan with the decisions and its gap are null",
       SI.get("invalid") == ("The agreed decisions no longer fit the plan (route 'R4' does not exist), so the plan with them "
                             "cannot be worked out. Set the target again on the Carbon page.")
       and SI.get("with_decisions_t") is None and SI.get("gap_with_decisions_t") is None, str(SI))
    ok("...while the plan as forecast, the target and the pending lines still read",
       SI.get("approved_t") == 161.446 and SI.get("target_t") == 43.429 and SI.get("gap_as_forecast_t") == 118.017
       and SI.get("pending_t") == 5.653 and [m["with_decisions_t"] for m in SI.get("by_month") or []] == [None, None], str(SI))
    ok("...and the stored target is left as it was (a planner sets it again)", GI["target"]["levers"] == DECISIONS)
finally:
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, ?)",
               (_r4["id"], _r4["origin_id"], _r4["dest_id"], _r4["material_category"], _r4["ipt"]))
ok("(R4 back: the decisions apply again)", GET()["status"]["invalid"] is None)

# =========================================================================== #
#  10. DELETE                                                                   #
# =========================================================================== #
D = main.delete_carbon_target()
ok("⭐ DELETE clears it and returns the GET payload with target null", D == {"target": None, "status": None}
   and carbon_target.get_row() is None and GET() == {"target": None, "status": None})
ok("...and a second DELETE is harmless", main.delete_carbon_target() == {"target": None, "status": None})
ok("set again after a clear: the same 73.1 %", PUT(mode="pct", levers=DECISIONS, ui_state=UI, updated_by="Sam (planner)")["target"]["pct_below"] == 73.1)

# =========================================================================== #
#  11. The Submit forecast preview's carbon                                      #
# =========================================================================== #
_q = {"n": 0, "x": 0}
db.query = lambda *a, **k: (_q.__setitem__("n", _q["n"] + 1), _oq(*a, **k))[1]
db.execute = lambda *a, **k: (_q.__setitem__("x", _q["x"] + 1), _ox(*a, **k))[1]
try:
    PV = main.costing_preview(main.CostPreview(route_id="R1", vehicle_type=ART, material_type=SA, unit="t",
                                               cells=[main.Cell(month_index=10, quantity=2900.0)]))
finally:
    db.query, db.execute = _oq, _ox
PC = PV["carbon"]
ok("🔴 the preview still writes nothing", _q["x"] == 0, str(_q))
# 2900 × 7.80307 = 22.628903 → 22.629; 100 trips × 60 km × 0.93939 = 5.63634 → 5.636; 28.265
ok("⭐ a delivery line: material 22.629 + transport 5.636 = 28.265 tCO2e, no disposal, routed",
   PC == {"material_t": 22.629, "transport_t": 5.636, "disposal_t": None, "total_t": 28.265, "unrouted": False,
          "basis": "Making the material at the UK Government 2026 factor for aggregates; transport there and back on the routed distance."},
   str(PC))
_cl = [l for l in costlines.lines(status="Approved")["lines"] if l["route_id"] == "R1" and l["month_index"] == 10]
_sl = [l for l in carbon.scenario()["lines"] if l["route_id"] == "R1" and l["month_index"] == 10]
ok("⭐ ONE number: the preview's transport equals the saved line's co2_t (Dashboard) and its all-in the Carbon page's line",
   len(_cl) == 1 and PC["transport_t"] == _cl[0]["co2_t"] and len(_sl) == 1 and near(PC["total_t"], _sl[0]["total_t"], 0.0011),
   f"{_cl} {_sl}")
PL = costlines.preview("R3", ART, SOIL, "t", [{"month_index": 10, "quantity": 2900.0}, {"month_index": 11, "quantity": 2900.0}])["carbon"]
# 5800 × 19.55376 = 113.411808 → 113.412; each cell 100 × 40 × 0.93939 = 3.75756 → 3.758, two = 7.516; 120.928
ok("⭐ a muck-away line to a LANDFILL: disposal 113.412 + transport 7.516 (3.758 a month, as each saved month rounds) = 120.928, no material",
   PL == {"material_t": None, "transport_t": 7.516, "disposal_t": 113.412, "total_t": 120.928, "unrouted": False,
          "basis": "Transport there and back on the routed distance; disposal by landfill at the UK Government 2026 factor for soils."},
   str(PL))
PH = costlines.preview("R4", ART, SOIL, "t", [{"month_index": 10, "quantity": 580.0}])["carbon"]
# 580 × 1.01398 = 0.5881084 → 0.588; 20 trips × 16 km × 0.93939 = 0.3006048 → 0.301; 0.889
ok("...to the soil hub: closed-loop 0.588 + transport 0.301 = 0.889",
   PH["disposal_t"] == 0.588 and PH["transport_t"] == 0.301 and PH["total_t"] == 0.889 and PH["material_t"] is None
   and "disposal by closed-loop recycling at the UK Government 2026 factor for soils" in PH["basis"], str(PH))
PU = costlines.preview("R5", ART, SA, "t", [{"month_index": 10, "quantity": 1000.0}])["carbon"]
ok("🔴 an UNROUTED line: transport null and unrouted, never estimated; material 1000 × 7.80307 = 7.803 is the total",
   PU == {"material_t": 7.803, "transport_t": None, "disposal_t": None, "total_t": 7.803, "unrouted": True,
          "basis": "Making the material at the UK Government 2026 factor for aggregates; transport is not counted until the route has a distance."},
   str(PU))
PS = costlines.preview("R1", ART, SOIL, "t", [{"month_index": 10, "quantity": 2900.0}])["carbon"]
ok("soil delivered to a compound: no Government primary factor for soils, so making it is not counted (said, not zero)",
   PS["material_t"] is None and PS["transport_t"] == 5.636 and PS["total_t"] == 5.636
   and PS["basis"] == "Making the material is not counted (no Government factor is published for soils); transport there and back on the routed distance.",
   str(PS))
P0 = costlines.preview("R1", ART, SA, "t", [])["carbon"]
ok("no cells: nothing typed, zero, and it says so", P0 == {"material_t": 0.0, "transport_t": 0.0, "disposal_t": None, "total_t": 0.0,
                                                          "unrouted": False, "basis": "Nothing typed yet."}, str(P0))
ok("🔴 the basis sentences use none of the words a public page must not use, and say lorry words only",
   not any(w in (b or "").lower() for b in (PC["basis"], PL["basis"], PU["basis"], PS["basis"], PH["basis"])
           for w in ("secure", "truck", "real-time", "optimis", "predict", "ai ")))
_pf = os.path.join(HERE, "fixtures", "cost_preview_carbon.json")
with open(_pf, "w", encoding="utf-8", newline=chr(10)) as fh:
    fh.write(json.dumps(_scrub(PV), indent=1, ensure_ascii=False, sort_keys=True) + chr(10))
ok("the preview-with-carbon fixture is written (sorted keys, stable on every OS)", os.path.exists(_pf))

# =========================================================================== #
#  12. Source-level                                                             #
# =========================================================================== #
_cb = read("backend/carbon.py").split('"""', 2)[2]
ok("🔴 carbon.py still writes nothing: no INSERT, UPDATE or DELETE in its code, the same two tenant reads",
   "INSERT" not in _cb and "UPDATE " not in _cb and "DELETE" not in _cb and _cb.count("WHERE tenant_id = ?") == 2)
ok("...and its docstring still says so", "Nothing here writes." in read("backend/carbon.py").split('"""', 2)[1])
_ctsrc = read("backend/carbon_target.py")
_ctdoc, _ctcode = " ".join(_ctsrc.split('"""', 2)[1].split()), _ctsrc.split('"""', 2)[2]
ok("carbon_target.py's docstring says what it stores, who may write, no identity until G3, and that it is all-in",
   "key 'carbon_target'" in _ctdoc and "planner or admin" in _ctdoc and "G3" in _ctdoc and "updated_by" in _ctdoc
   and "ALL-IN" in _ctdoc and "typed at sign-in" in _ctdoc)
_sql = re.findall(r'"((?:SELECT|INSERT|UPDATE|DELETE)[^"]*"(?:\s*"[^"]*")*)', _ctcode)
ok("🔴 every statement in carbon_target.py names the tenant (SELECT / UPDATE / DELETE filter on it, the INSERT writes it)",
   len(_sql) >= 4 and all("tenant_id" in s for s in _sql) and _ctcode.count("db.current_tenant()") >= 5, str(_sql))
ok("...it keeps no figure of its own: every number comes from carbon.scenario",
   _ctcode.count("carbon.scenario(") == 4 and not re.search(r"\b0\.9\d{3}|\b7\.8\d|\b19\.5\d", _ctcode))
ok("🔴 no team id in the new module (people see team names)", not re.search(r"\bIPT ?[1-6]\b", _ctsrc))
_mp = read("backend/main.py")


def _fn(name):
    s = _mp[_mp.index(f"def {name}("):]
    return s[:s.index("\n@app.") if "\n@app." in s else len(s)]


ok("⭐ the three routes are registered next to the carbon endpoints",
   '@app.get("/api/carbon/target")' in _mp and '@app.put("/api/carbon/target")' in _mp and '@app.delete("/api/carbon/target")' in _mp
   and _mp.index('@app.post("/api/carbon/summary.pdf")') < _mp.index('@app.get("/api/carbon/target")') < _mp.index("public feed (map)"))
ok("🔴 GET's first act is _require_access(); PUT's and DELETE's is _require_approver()",
   _fn("get_carbon_target").split('"""', 2)[2].strip().startswith("acc = _require_access()")
   and _fn("put_carbon_target").split('"""', 2)[2].strip().startswith("acc = _require_approver()")
   and _fn("delete_carbon_target").split('"""', 2)[2].strip().startswith("acc = _require_approver()"))
ok("...a refusal becomes a 400 with the sentence; the endpoints hold no SQL of their own",
   "except carbon_target.TargetError as e:" in _fn("put_carbon_target") and "raise HTTPException(400, str(e))" in _fn("put_carbon_target")
   and not any("db." in _fn(n) for n in ("get_carbon_target", "put_carbon_target", "delete_carbon_target")))
ok("the body model carries updated_by as typed, like the costing target", "class CarbonTargetIn(BaseModel):" in _mp
   and "updated_by: Optional[str] = None" in _mp[_mp.index("class CarbonTargetIn("):_mp.index("class CarbonTargetIn(") + 700])
_cls = read("backend/costlines.py")
_pvc = _cls[_cls.index("def preview(") :]
ok("⭐ the preview's transport is the SAME formula as the saved lines' co2_t (km_day × the vehicle's kg per km ÷ 1000)",
   "conversions._emissions(factors, r.get(\"vehicle_type\")) / 1000.0" in _cls
   and "conversions._emissions(factors, vehicle_type) / 1000.0" in _pvc and 'f.get("km_day")' in _pvc)
ok("...and its material and disposal factors are carbon.py's own functions, no figure typed in",
   "_carbon.material_factor(cp, cm)" in _pvc and "_carbon.disposal_factor(cp, cm, route)" in _pvc
   and "_carbon.disposal_route_of(cp, loc)" in _pvc and not re.search(r"\b7\.8\d|\b19\.5\d|\b1\.01\d", _pvc))
ok("🔴 the tenant import clears the target's cache with the config cache", "_carbon_target.invalidate()" in read("backend/tenant_package.py"))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
