"""
Gate arrivals, 11 Oct 2026 — backend/gate_arrivals.py and GET /api/gates/arrivals.

What is asserted: the module reads and never writes; it imports neither network nor main and
names no team slot id; running it changes NO existing figure (costlines.lines, lookahead.page,
derived.day_figures are byte-identical before and after); its trips per line equal costlines'
trips for the same rows (the one trips rule); the gate at each end is gates.resolve(…, "entry")
with the exit-gate fall-through recorded; arrivals a day = trips ÷ working days, the gap =
shift minutes ÷ arrivals; RED only when the rounded gap is shorter than the gate's typed
check-in, nothing amber, an untyped gate never compared (and never 0.0); pending lines a note
and never a figure; rejected lines nowhere; the origin-share sentence on origin locations only;
team NAMES, never ids; a team code gets the totals and the names but only its own per_team row;
the tenant predicate on every SQL literal; and the endpoint's 400 / 401 edges.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed (http_smoke.py drives the real one against the demo package).
  * Nothing in a browser; the panel itself is parse_frontend / render_frontend / dom_frontend's.
  * SQLite only.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_gate_arrivals.py
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

# ---- stubs, verbatim from test_costlines.py --------------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_gate_arrivals_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import weeks  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import derived  # noqa: E402
import costing  # noqa: E402
import lookahead  # noqa: E402
import config  # noqa: E402
import costlines  # noqa: E402
import gates  # noqa: E402
import gate_arrivals  # noqa: E402
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


def _scrub(o):
    if isinstance(o, dict):
        return {k: ("<ts>" if k.endswith("_at") and isinstance(v, str) else _scrub(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(x) for x in o]
    return o


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db()
    db.init_network_db()
    db.init_taxonomy_db()
    db.init_zones_db()
    db.init_gates_db()
    db.init_weeks_db()
    db.init_lookahead_db()
    db.init_config_db()
    db.init_costing_db()
    db.init_tenant()
    # this tenant has no country: factors.json's planning block (22 d / 10 h) is what is asserted
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    # 17 Oct 2026: the figures below rest on a 600-minute gate day (they were the 10 h shift's). Since a gate with no
    # hours typed takes the default gate hours (08:00–17:00, the user), this scheme sets its own default to 07:00–17:00
    # on Config → Planning — the setting a scheme uses for its hours — so every figure stands; §8b checks 08:00–17:00
    _doc = json.loads(json.dumps(conversions.load_factors()))
    _doc.setdefault("planning", {})["default_gate_hours"] = {"from": "07:00", "to": "17:00"}
    assert config.save(_doc, by="test_gate_arrivals")["ok"]
    config.invalidate()
    costing.invalidate()


# =========================================================================== #
#  0. The seed (spec §2.6): a quarry with an in-weighbridge and an exit, a compound,  #
#     a stockpile; four routes naming their gates; approved, pending and rejected lines #
# =========================================================================== #
reset_db()
access.set_current("planner123")
V8 = "Rigid 8-wheeler (32t)"          # payload_t 20 in factors.json
for _id, _name, _lt, _role, _lat, _lon in (("L1", "West pit", "Quarry", "origin", 58.5, 24.0),
                                           ("L2", "East compound", "Compound", "destination", 58.6, 24.4),
                                           ("L3", "North stockpile", "Stockpile", "destination", 58.7, 24.2)):
    db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
               (_id, _name, _lt, _role, _lat, _lon))
G = {}
for _key, (_loc, _name, _dir, _sm, _dflt, _lat, _lon) in (
        ("G001", ("L1", "Weighbridge (in)", "access", 2.0, False, 58.501, 24.001)),
        ("G002", ("L1", "Main road exit", "egress", None, True, 58.502, 24.002)),
        ("G003", ("L2", "Compound gate", "both", 3.0, True, 58.601, 24.401)),
        ("G004", ("L3", "Stockpile gate", "both", None, True, 58.701, 24.201))):
    _r = gates.create_gate(_loc, _name, _lat, _lon, direction=_dir, safety_minutes=_sm, is_default=_dflt)
    assert not _r.get("error"), _r
    G[_key] = _r["id"]
ok("the four gates are G001..G004 in creation order", [G[k] for k in ("G001", "G002", "G003", "G004")] == ["G001", "G002", "G003", "G004"], str(G))
for _rid, _o, _d, _ipt, _og, _dg in (("R1", "L1", "L2", "IPT1", "G002", "G003"),
                                     ("R2", "L1", "L3", "IPT1", "G002", "G004"),
                                     ("R3", "L1", "L2", "IPT2", "G002", "G003"),
                                     ("R4", "L2", "L3", "IPT1", "G003", "G004")):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", (_rid, _o, _d, _ipt))
    _r = gates.set_route_gates(_rid, origin_gate_id=_og, dest_gate_id=_dg, origin_given=True, dest_given=True)
    assert not _r.get("error"), _r


def _line(rid, sect, qty, ipt, status="Approved", months=(9,), unit="t"):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type="Small aggregate",
        material_description=None, vehicle_type=V8, submitted_by="tester", unit=unit,
        status="Pending", cells=[main.Cell(month_index=m, quantity=qty) for m in months], ipt=ipt))
    if status != "Pending":
        main.set_route_status(rid, main.StatusUpdate(status=status), discipline="earthworks", section_id=sect)


_line("R1", "WS1", 60000.0, "IPT1")                       # 3000 trips, laden at G003, empty at G001 (via G002 fall-through)
_line("R3", "WS1", 40000.0, "IPT2")                       # 2000 trips, same gates, the other team
_line("R2", "WS1", 11000.0, "IPT1")                       # 550 trips, laden at G004, empty at G001
_line("R4", "WS1", 2000.0, "IPT1")                        # 100 trips, muck-away: laden at G004, empty at G003
_line("R2", "WS2", 2200.0, "IPT1", status="Pending")      # 110 trips, a note only
_line("R2", "WS3", 1000.0, "IPT1", status="Rejected")     # counts nowhere
_line("R1", "WS1", 2200.0, "IPT1", months=(10,))          # month 10: approved, no pending
_line("R4", "WS4", 44.0, "IPT1", months=(10,), unit="vehicles")   # month 10: 44 vehicles = 44 trips (the unit rule), laden at G004, empty at G003

factors = conversions.load_factors()
WD, SH, OPEN = 22.0, 10.0, 600.0

# =========================================================================== #
#  1. Source-level: read-only, no forbidden import, no slot id, tenant predicate   #
# =========================================================================== #
src = open(os.path.join(BACKEND, "gate_arrivals.py"), encoding="utf-8").read()
code_only = src.split('"""', 2)[2]          # past the module docstring
ok("⭐ the module is read-only: no execute/INSERT/UPDATE/DELETE in gate_arrivals.py",
   "db.execute" not in code_only and not re.search(r"\b(INSERT|UPDATE|DELETE)\b", code_only))
ok("⭐ it imports neither network nor main, and names no team slot id",
   not re.search(r"^\s*(import|from)\s+(network|main)\b", src, re.M)
   and re.search(r"\bIPT ?[1-6]\b", src) is None)
_stmts = re.findall(r'db\.query\(\s*((?:"[^"]*"\s*)+)', code_only)
# NARROWED 14 Oct 2026 (bundle G): seven statements — location_visits() (the CLP section's chart 1b) adds two and
# week_by_day() (W17, the Look-ahead's gates) two more, each tenanted
ok("🔴 tenant isolation: the SQL literals in gate_arrivals.py constrain tenant_id",
   len(_stmts) == 7 and all("tenant_id = ?" in s for s in _stmts)
   and all(re.search(r"FROM (\w+)", s) for s in _stmts)
   and code_only.count("db.current_tenant()") >= 3, str(_stmts))

# =========================================================================== #
#  2. INVARIANTS: nothing that exists moves                                    #
# =========================================================================== #
_cl_before = json.dumps(_scrub(costlines.lines(status="All")), sort_keys=True)
_la_before = json.dumps(_scrub(lookahead.page("commit")), sort_keys=True)
_ctx_line = {"route_id": "R1", "unit": "t", "material_type": "Small aggregate", "vehicle_type": V8,
             "month_index": 9, "week": {"planned_qty": 60000.0}}
_df_before = derived.day_figures(60000.0, derived.line_context(_ctx_line, factors), factors)
acc_planner = access.current()
res = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=main._working_days(factors))
_cl_after = json.dumps(_scrub(costlines.lines(status="All")), sort_keys=True)
_la_after = json.dumps(_scrub(lookahead.page("commit")), sort_keys=True)
_df_after = derived.day_figures(60000.0, derived.line_context(_ctx_line, factors), factors)
ok("🔴 INVARIANT: costlines.lines() (every status) is byte-identical before and after arrivals() runs", _cl_before == _cl_after)
ok("🔴 INVARIANT: lookahead.page(\"commit\") is unchanged by the new module", _la_before == _la_after)
ok("🔴 INVARIANT: derived.day_figures on a baked ctx is untouched (the §5 turnaround figures of test_phase5a are not this module's business)",
   _df_before == _df_after and _df_before["trips"] == 3000)

# =========================================================================== #
#  3. The trips rule, the label, the planning block                           #
# =========================================================================== #
_cl = costlines.lines(status="All", factors=factors)
cl_trips = {(l["route_id"], l["month_index"], l["discipline"], l["section_id"]): l["trips"] for l in _cl["lines"]}
_rows9 = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND month_index = ? AND status = 'Approved'",
                  (db.current_tenant(), 9))
ok("⭐ trips per line equal costlines.lines()' trips for the same rows (the one trips rule)",
   len(_rows9) == 4 and all(gate_arrivals.trips_for(r, factors) == cl_trips[(r["route_id"], 9, r["discipline"] or "", r["section_id"] or "")]
                            for r in _rows9), str([(r["route_id"], gate_arrivals.trips_for(r, factors)) for r in _rows9]))
# 11 Oct 2026 (review): the "qty itself when the unit is vehicles" branch, against costlines' own figure for that row
_rows10v = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND month_index = ? AND unit = 'vehicles'", (db.current_tenant(), 10))
ok("⭐ the vehicles branch of the trips rule: 44 vehicles on R4 WS4 are 44 trips here and in costlines.lines()",
   len(_rows10v) == 1 and gate_arrivals.trips_for(_rows10v[0], factors) == 44 == cl_trips[("R4", 10, "earthworks", "WS4")],
   str([(r["route_id"], r["unit"], gate_arrivals.trips_for(r, factors)) for r in _rows10v]))
_junk = {"planning": {"working_days_per_month": -5, "shift_hours_per_day": "abc"}}
_zero = {"planning": {"working_days_per_month": 0, "shift_hours_per_day": 0}}
ok("a negative, zero or junk planning figure in a hand-edited factors.json falls to 22 d / 10 h (main._working_days' guard), including a bad working_days passed in",
   gate_arrivals.working_days(_junk) == 22.0 and gate_arrivals.shift_hours(_junk) == 10.0
   and gate_arrivals.working_days(_zero) == 22.0 and gate_arrivals.shift_hours(_zero) == 10.0
   and gate_arrivals.arrivals(11, acc_planner, factors=factors, working_days=-3)["working_days"] == 22.0
   and gate_arrivals.arrivals(11, acc_planner, factors=_junk)["shift_hours"] == 10.0)
ok('the month label: 9 -> "Sep 2026", 13 -> "Jan 2027"',
   gate_arrivals.month_label(9) == "Sep 2026" and gate_arrivals.month_label(13) == "Jan 2027" and res["label"] == "Sep 2026")
# NARROWED 17 Oct 2026: open_minutes is now the default gate day (07:00–17:00 set on Config by this harness = 600), not the
# lorry shift's minutes; shift_hours stays the lorry shift (10)
ok("working days and shift hours are the planning block's (22, 10) and open_minutes is 600.0, the default gate day "
   "(07:00–17:00 here), its hours in words",
   res["working_days"] == WD and res["shift_hours"] == SH and res["open_minutes"] == OPEN and res["month"] == 9 and res["scope"] == "scheme"
   and res["default_hours"] == "07:00–17:00"
   and gate_arrivals.working_days(factors) == 22.0 and gate_arrivals.shift_hours(factors) == 10.0)

# =========================================================================== #
#  4. The gates                                                               #
# =========================================================================== #
gl = res["gates"]
byg = {g["gate_id"]: g for g in gl}
ok("⭐ three gates listed, sorted by arrivals a day: G001, G003, G004",
   [g["gate_id"] for g in gl] == ["G001", "G003", "G004"], str([(g["gate_id"], g["arrivals_per_day"]) for g in gl]))
g1, g3, g4 = byg.get("G001", {}), byg.get("G003", {}), byg.get("G004", {})
ok("⭐ the resolve fall-through: routes naming the EXIT gate G002 are counted at the access gate G001, and fallthrough_routes names them",
   g1.get("fallthrough_routes") == ["R1", "R2", "R3"] and "G002" not in byg and g3.get("fallthrough_routes") == [] and g4.get("fallthrough_routes") == [],
   str(g1.get("fallthrough_routes")))
# the trips the harness summed itself, per gate: laden at the destination's gate, empty at the origin's
T_LADEN = {"G001": 0, "G003": 3000 + 2000, "G004": 550 + 100}
T_EMPTY = {"G001": 3000 + 550 + 2000, "G003": 100, "G004": 0}
ok('⭐ West pit (origin): empty arrivals 5550 trips ÷ 22 = round(5550/22, 1), laden 0.0, role "origin"',
   g1.get("empty_per_day") == round(5550 / WD, 1) and g1.get("laden_per_day") == 0.0 and g1.get("role") == "origin"
   and g1.get("location_name") == "West pit" and g1.get("loc_type") == "Quarry" and g1.get("gate_name") == "Weighbridge (in)", str(g1)[:300])
ok('⭐ East compound (both): laden 5000 + empty 100 (the muck-away route R4), arrivals round(5100/22, 1), role "both"',
   g3.get("laden_per_day") == round(5000 / WD, 1) and g3.get("empty_per_day") == round(100 / WD, 1)
   and g3.get("arrivals_per_day") == round(5100 / WD, 1) and g3.get("role") == "both", str(g3)[:300])
ok('North stockpile (destination): laden 550 + 100 = round(650/22, 1), empty 0.0, role "destination"',
   g4.get("laden_per_day") == round(650 / WD, 1) and g4.get("empty_per_day") == 0.0 and g4.get("arrivals_per_day") == round(650 / WD, 1)
   and g4.get("role") == "destination", str(g4)[:300])
ok("arrivals_per_day is rounded from the sum: |laden + empty − arrivals| ≤ 0.1 on every gate",
   all(abs(g["laden_per_day"] + g["empty_per_day"] - g["arrivals_per_day"]) <= 0.1 for g in gl)
   and all(g["arrivals_per_day"] == round((T_LADEN.get(g["gate_id"], 0) + T_EMPTY.get(g["gate_id"], 0)) / WD, 1) for g in gl))
ok("gap_minutes = round(600 ÷ unrounded arrivals, 1) on every gate",
   all(g["gap_minutes"] == round(OPEN / (max(T_LADEN.get(g["gate_id"], 0) + T_EMPTY.get(g["gate_id"], 0), 1) / WD), 1) for g in gl),
   str([(g["gate_id"], g["gap_minutes"]) for g in gl]))

# 14 Oct 2026: the gate's capacity (for the Dashboard's chart) — shift minutes ÷ check-in minutes, and the share of it
ok("⭐ capacity_per_day = round(600 ÷ the check-in minutes, 1) where a check-in is typed, None where it is not",
   all((g["capacity_per_day"] == round(OPEN / g["gate_minutes"], 1)) if g.get("gate_minutes") else (g["capacity_per_day"] is None) for g in gl)
   and g3.get("capacity_per_day") == 200.0, str([(g["gate_id"], g.get("gate_minutes"), g.get("capacity_per_day")) for g in gl]))
ok("⭐ capacity_pct = round(unrounded arrivals × 100 ÷ capacity) (None with no check-in)",
   all((g["capacity_pct"] == round(((T_LADEN.get(g["gate_id"], 0) + T_EMPTY.get(g["gate_id"], 0)) / WD) * 100 / (OPEN / g["gate_minutes"])))
       if g.get("gate_minutes") else (g["capacity_pct"] is None) for g in gl),
   str([(g["gate_id"], g.get("capacity_pct")) for g in gl]))
ok("🔴 the chart cannot disagree with the flag: every red gate is over 100 % of its capacity, every compared gate that is not red is at or under it (to the rounding of the gap)",
   all(((g["capacity_pct"] or 0) > 100) for g in gl if g.get("flag") == "red")
   and all(((g["capacity_pct"] or 0) <= 102) for g in gl if g.get("flag") != "red" and g.get("capacity_pct") is not None),
   str([(g["gate_id"], g.get("flag"), g.get("capacity_pct")) for g in gl]))

# the flag rule
ok('🔴 the red rule: East compound\'s 2.6 min gap is shorter than its 3 min check-in -> flag "red" and the reason reads "a queue even with perfect spacing"',
   g3.get("gap_minutes") == 2.6 and g3.get("gate_minutes") == 3.0 and g3.get("flag") == "red"
   and g3.get("reason") == f"{g3.get('arrivals_per_day')} arrivals a day, one every 2.6 min if arrivals are spread evenly, shorter than the 3 min check-in: a queue even with perfect spacing.",
   str(g3.get("reason")))
# 11 Oct 2026 (review): the edge of the red rule, pinned deliberately. The DISPLAYED gap (1 dp) is compared, so the
# screen never reads "3.0 min" flagged red against a 3 min check-in. East compound's 5 100 trips at chosen day counts:
_edge = lambda wd: {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=wd)["gates"]}["G003"]
_e_eq, _e_rd, _e_lt = _edge(25.5), _edge(25.245), _edge(24.5)
# NARROWED 14 Oct 2026 (bundle G, W17): the edge is still NOT red, but at 100 % of capacity it is now the amber step
# ("Queue likely", 85 % or more) — flag "amber" where it was None. The red rule itself is unchanged.
ok("🔴 the edge: 5100 ÷ 25.5 = 200.0 a day, gap exactly 3.0 against 3 min -> NOT red (shorter than, not equal); amber since 14 Oct (100 % ≥ 85 %)",
   _e_eq["arrivals_per_day"] == 200.0 and _e_eq["gap_minutes"] == 3.0 and _e_eq["flag"] == "amber"
   and _e_eq["status_word"] == "Queue likely"
   and _e_eq["reason"].startswith("One every 3.0 min if arrivals are spread evenly, against a 3 min check-in"), str(_e_eq)[:200])
ok("🔴 the edge: a raw gap of 2.97 min (5100 ÷ 25.245) is shown as 3.0 and does NOT flag red — the displayed figure is what is compared (amber since 14 Oct)",
   round(600 / (5100 / 25.245), 3) == 2.97 and _e_rd["gap_minutes"] == 3.0 and _e_rd["flag"] == "amber", str(_e_rd)[:200])
ok("the edge: a raw gap of 2.88 min (5100 ÷ 24.5) is shown as 2.9 and flags red",
   _e_lt["gap_minutes"] == 2.9 and _e_lt["flag"] == "red" and "one every 2.9 min" in _e_lt["reason"], str(_e_lt)[:200])
_txt = json.dumps(res, ensure_ascii=False)
ok('🔴 red only: West pit (2.4 min against 2 min) and North stockpile carry flag None; nothing is "amber" anywhere in the response text',
   g1.get("gap_minutes") == 2.4 and g1.get("gate_minutes") == 2.0 and g1.get("flag") is None and g4.get("flag") is None
   and "amber" not in _txt.lower() and set(g["flag"] for g in gl) == {"red", None})
ok('⭐ no check-in time typed: North stockpile has gate_minutes None, flag None, reason "No check-in time typed for this gate, so nothing is compared."',
   g4.get("gate_minutes") is None and g4.get("gate_minutes") != 0.0 and g4.get("flag") is None
   and g4.get("reason") == "No check-in time typed for this gate, so nothing is compared." and g4.get("gap_minutes") == round(OPEN / (650 / WD), 1))
ok('the typed-and-holding reason says "spacing holds on the average" and "No hourly peak is typed."',
   g1.get("reason") == "One every 2.4 min if arrivals are spread evenly, against a 2 min check-in: spacing holds on the average. No hourly peak is typed.")
_sentences = [g["reason"] for g in gl] + res["notes"]
_allowed_other = ("No check-in time typed for this gate, so nothing is compared.", "No approved arrivals this month.")
ok('🔴 every reason and note says "if arrivals are spread evenly" or is the untyped/none sentence; the banned words appear nowhere in the response',
   all(("if arrivals are spread evenly" in s) or (s in _allowed_other) or s.endswith("they are not in the figures.")
       or s.endswith("so arrivals there are not shown.") or " so arrivals there are counted at " in s
       or s.startswith("No approved lines in") for s in _sentences)
   and not re.search(r"real-time|\blive\b|booking|peak hour|truck|optimi|predict|\bAI\b|telematics", _txt, re.I),
   _txt[:300])

# pending and rejected
# NARROWED 11 Oct 2026 (review): the month note said "10.0 arrivals a day", which a reader takes as lorries; it is 5.0 lorries,
# each arriving at two gates. The note now says both.
ok('⭐ pending lines are a note, not a figure: R2\'s pending 2 200 t (110 trips) adds 5.0/day at G001 and G004 (pending_lines 1, pending_per_day 5.0), the month note says "5.0 lorries a day (10.0 gate arrivals …)", and the approved figures exclude it',
   g1.get("pending_lines") == 1 and g1.get("pending_per_day") == round(110 / WD, 1) == 5.0
   and g4.get("pending_lines") == 1 and g4.get("pending_per_day") == 5.0
   and g3.get("pending_lines") == 0 and g3.get("pending_per_day") == 0.0
   and res["notes"][0] == "1 pending line in Sep 2026 would add 5.0 lorries a day (10.0 gate arrivals across the gates below); they are not in the figures."
   and g1["empty_per_day"] == round(5550 / WD, 1), str(res["notes"]))
# the rejected line (R2 WS3, 1 000 t = 50 trips) is in the database and in none of the figures
_rej = db.query("SELECT status FROM forecasts WHERE tenant_id = ? AND route_id = ? AND section_id = ?", (db.current_tenant(), "R2", "WS3"))
ok("🔴 a rejected line counts nowhere",
   _rej and _rej[0]["status"] == "Rejected" and g1["empty_per_day"] == round(5550 / WD, 1) and g4["laden_per_day"] == round(650 / WD, 1)
   and g1["pending_lines"] == 1 and g4["pending_lines"] == 1 and len(res["notes"]) == 2, str(_rej))

# origin share, teams
ok("⭐ origin-share note on the quarry gate only",
   g1.get("origin_share_note") == "West pit serves other customers too; Wayscope sees only this scheme's share of this gate's traffic."
   and g3.get("origin_share_note") is None and g4.get("origin_share_note") is None)
ok('teams are names, never ids: ["Team 1", "Team 2"] on G001 and G003, ["Team 1"] on G004; no "IPT" in the JSON',
   g1.get("teams") == ["Team 1", "Team 2"] and g3.get("teams") == ["Team 1", "Team 2"] and g4.get("teams") == ["Team 1"]
   and "IPT" not in _txt, _txt[:300])
ok("⭐ planner: per_team carries every team with its figure (G001: Team 1 161.4, Team 2 90.9)",
   g1.get("per_team") == [{"team": "Team 1", "arrivals_per_day": round(3550 / WD, 1)}, {"team": "Team 2", "arrivals_per_day": round(2000 / WD, 1)}]
   and round(3550 / WD, 1) == 161.4 and round(2000 / WD, 1) == 90.9
   and g3.get("per_team") == [{"team": "Team 1", "arrivals_per_day": round(3100 / WD, 1)}, {"team": "Team 2", "arrivals_per_day": round(2000 / WD, 1)}]
   and g4.get("per_team") == [{"team": "Team 1", "arrivals_per_day": round(650 / WD, 1)}], str(g1.get("per_team")))
# 14 Oct 2026 (narrowed): + capacity_per_day and capacity_pct, for the Dashboard's gate chart
# 14 Oct 2026, later (narrowed again, bundle G W17): + status_word, the gate's own open minutes, basis, hours, peak
# minutes and closed days; the response + near_pct, peak_bands, limit
# NARROWED 22 Oct 2026 (abnormal loads, phase 2, D70): + abnormal, the markers on the gate's row (never in the figures)
ok("the response carries every key of the contract on every gate",
   all(set(g) == {"gate_id", "gate_name", "location_id", "location_name", "loc_type", "role", "laden_per_day", "empty_per_day",
                  "arrivals_per_day", "gap_minutes", "gate_minutes", "capacity_per_day", "capacity_pct", "flag", "reason", "pending_lines", "pending_per_day",
                  "teams", "per_team", "origin_share_note", "fallthrough_routes", "abnormal",
                  "status_word", "open_minutes", "open_basis", "open_hours", "peak_minutes", "closed_days", "near_per_day",
                  # 17 Oct 2026 (narrowed): the gate's shut windows, the minutes they take off and their words
                  "shut_windows", "shut_minutes", "shut_words",
                  # 17 Oct 2026 (narrowed, the review): a gate whose bands and shut times leave no open minute says so
                  "no_open_time"} for g in gl)
   # NARROWED 22 Oct 2026 (abnormal loads, phase 2): + abnormal_total, how many abnormal loads the month's markers name
   and set(res) == {"month", "label", "working_days", "shift_hours", "open_minutes", "scope", "gates", "notes",
                    "near_pct", "peak_bands", "limit", "default_hours", "abnormal_total"})

# =========================================================================== #
#  5. A team code: totals and names, never the other team's figure              #
# =========================================================================== #
os.environ["IPT2_CODE"] = "ipt2-secret"
try:
    access.set_current("ipt2-secret")
    team_acc = access.current()
    team_res = gate_arrivals.arrivals(9, team_acc, factors=factors, working_days=main._working_days(factors))
    tb = {g["gate_id"]: g for g in team_res["gates"]}
    ok('🔴 a team code gets scope "team", the same totals on every gate, the same teams list, and per_team holding ONLY its own row (G001: Team 2 90.9; G004: [])',
       team_res["scope"] == "team"
       and [(g["gate_id"], g["arrivals_per_day"], g["laden_per_day"], g["empty_per_day"], g["gap_minutes"], g["flag"], g["teams"]) for g in team_res["gates"]]
       == [(g["gate_id"], g["arrivals_per_day"], g["laden_per_day"], g["empty_per_day"], g["gap_minutes"], g["flag"], g["teams"]) for g in gl]
       and tb["G001"]["per_team"] == [{"team": "Team 2", "arrivals_per_day": 90.9}]
       and tb["G003"]["per_team"] == [{"team": "Team 2", "arrivals_per_day": 90.9}]
       and tb["G004"]["per_team"] == [] and tb["G004"]["teams"] == ["Team 1"], str(tb.get("G001"))[:300])
    _ttxt = json.dumps(team_res, ensure_ascii=False)
    ok("🔴 the other team's figure is nowhere in a team code's response",
       "161.4" not in _ttxt and "140.9" not in _ttxt and str(round(650 / WD, 1)) in _ttxt and team_res["notes"] == res["notes"])
finally:
    os.environ.pop("IPT2_CODE", None)
    access.set_current("planner123")
access.set_current("submitter123")
sub_res = gate_arrivals.arrivals(9, access.current(), factors=factors, working_days=main._working_days(factors))
ok('the demo submitter (role submitter, no ipt) sees scope "scheme" and every per_team row',
   sub_res["scope"] == "scheme" and [g["per_team"] for g in sub_res["gates"]] == [g["per_team"] for g in gl])
access.set_current("planner123")
access.set_current("admin123")
adm_res = gate_arrivals.arrivals(9, access.current(), factors=factors)
ok("the demo admin sees the same as the planner (and working_days defaults to the planning block when not passed)",
   adm_res == res)
access.set_current("planner123")

# =========================================================================== #
#  6. Months: empty, approved-only; a location with no gate                   #
# =========================================================================== #
m11 = gate_arrivals.arrivals(11, acc_planner, factors=factors, working_days=WD)
ok('empty month: month 11 -> gates [], notes ["No approved lines in Nov 2026.", "Averages only, …"]',
   m11["gates"] == [] and m11["label"] == "Nov 2026"
   # NARROWED 17 Oct 2026: no gate rests on the lorry shift any more; with no gate listed there is no default to name
   and m11["notes"] == ["No approved lines in Nov 2026.", "Averages only, if arrivals are spread evenly across each gate's open hours. No hourly peak is typed."],
   str(m11["notes"]))
m10 = gate_arrivals.arrivals(10, acc_planner, factors=factors, working_days=WD)
# NARROWED 11 Oct 2026 (review): month 10 now also carries the 44-vehicle line on R4 (laden at G004, empty at G003)
_m10b = {g["gate_id"]: g for g in m10["gates"]}
ok("a month with approved lines but no pending line carries no pending note; the vehicles line counts 44 trips: G004 laden 2.0, G003 empty 2.0",
   len(m10["gates"]) == 3 and m10["notes"] == ["Averages only, if arrivals are spread evenly across each gate's open hours (07:00–17:00 where none are typed). No hourly peak is typed."]
   and set(_m10b) == {"G001", "G003", "G004"}
   and _m10b["G004"]["laden_per_day"] == round(44 / WD, 1) == 2.0 and _m10b["G003"]["empty_per_day"] == 2.0
   and _m10b["G003"]["laden_per_day"] == round(110 / WD, 1) and _m10b["G001"]["empty_per_day"] == round(110 / WD, 1)
   and all(g["pending_lines"] == 0 for g in m10["gates"]), str(m10["notes"]) + str([(g["gate_id"], g["laden_per_day"], g["empty_per_day"]) for g in m10["gates"]]))
ok("a pending-only gate would list with no approved arrivals: gap None and the none sentence (unit check of the reason helper)",
   gate_arrivals._reason(None, None, 3.0) == "No approved arrivals this month."
   and gate_arrivals._reason(10.0, 3.0, 3.0).startswith("One every 3.0 min if arrivals are spread evenly, against a 3 min check-in")
   and gate_arrivals._reason(10.0, 2.9, 3.0).startswith("10.0 arrivals a day, one every 2.9 min")
   and gate_arrivals._reason(10.0, 2.9, 2.5).startswith("One every 2.9 min"))

# =========================================================================== #
#  7. The endpoint                                                             #
# =========================================================================== #
ep = main.gate_arrivals_month(9)
# NARROWED 16 Oct 2026 (S3): the endpoint adds the simulation's busiest hour to each gate (busiest_hour) and one note
# (busiest_note); everything arrivals() sends is unchanged
_ep_core = {k: v for k, v in ep.items() if k != "busiest_note"}
_ep_core["gates"] = [{k: v for k, v in g.items() if k != "busiest_hour"} for g in ep["gates"]]
ok("the endpoint: main.gate_arrivals_month(9) returns gate_arrivals.arrivals(9, acc, …) plus each gate's busiest hour and its note",
   _ep_core == res and all("busiest_hour" in g for g in ep["gates"]) and "busiest_note" in ep
   and all((g["busiest_hour"] or {}).get("lorries", 0) > 0 for g in ep["gates"] if g["arrivals_per_day"] > 0))
e0, e61 = _raises(lambda: main.gate_arrivals_month(0)), _raises(lambda: main.gate_arrivals_month(61))
ok("month 0 and 61 raise 400 with the sentence",
   getattr(e0, "status_code", None) == 400 and getattr(e61, "status_code", None) == 400 and "month must be 1..60" in str(e0))
_tok = access.set_current(None)
e401 = _raises(lambda: main.gate_arrivals_month(9))
access.set_current("planner123")
ok("no code -> 401", getattr(e401, "status_code", None) == 401)
_today = max(1, min(main.MONTH_COUNT, weeks.month_index_of(__import__("datetime").date.today())))
ok("no month -> today's month, clamped to the horizon", main.gate_arrivals_month()["month"] == _today)
main_code = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
_ep_body = main_code.split("def gate_arrivals_month(", 1)[1].split("\n@app.", 1)[0]
ok("the endpoint reads the working days through main._working_days (one reader) and requires any access code",
   "_working_days(factors)" in _ep_body and "_require_access()" in _ep_body and "gate_arrivals.arrivals(" in _ep_body
   and '@app.get("/api/gates/arrivals")' in main_code and "import gate_arrivals" in main_code)

# =========================================================================== #
#  8. A location with no gate rows: the end is skipped and ONE note names it  #
#     (11 Oct 2026, review) a route naming an INACTIVE or deleted gate: the lorries still  #
#     arrive, counted at the location's default entry gate, the note naming the cause;     #
#     an egress-only location; an inactive gate with no other entry gate                    #
# =========================================================================== #
db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
           ("L4", "Far tip", "Landfill", "destination", 58.8, 24.3))
db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", ("R5", "L1", "L4", "IPT1"))
gates.set_route_gates("R5", origin_gate_id="G002", origin_given=True)
_line("R5", "WS1", 2200.0, "IPT1")                        # 110 trips: empty at G001, laden end has no gate
res5 = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
b5 = {g["gate_id"]: g for g in res5["gates"]}
# NARROWED 11 Oct 2026 (review): "has no gate recorded" -> "has no entry gate recorded" (a location whose only gate is an exit has a gate)
ok("a location with no gate rows: resolve falls to the node, the end is skipped and ONE note names the location",
   b5["G001"]["empty_per_day"] == round((5550 + 110) / WD, 1) and "R5" in b5["G001"]["fallthrough_routes"]
   and res5["notes"].count("Far tip has no entry gate recorded, so arrivals there are not shown.") == 1
   and not any("has no gate recorded" in n for n in res5["notes"])
   and len(res5["gates"]) == 3 and res5["notes"][-1].startswith("Averages only"), str(res5["notes"]))

# an inactive named gate (G005) with another entry gate (G006, default, 4 min); a route naming a gate that no longer exists;
# an egress-only location (G007); an inactive gate with nothing else (G008)
for _id, _name, _lt in (("L5", "Shut tip", "Landfill"), ("L6", "Exit-only yard", "Compound"), ("L7", "Shut yard", "Compound")):
    db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
               (_id, _name, _lt, "destination", 58.9, 24.5))
for _key, (_loc, _name, _dir, _sm, _dflt) in (("G005", ("L5", "Old gate", "access", None, False)),
                                            ("G006", ("L5", "Main gate", "access", 4.0, True)),
                                            ("G007", ("L6", "Out only", "egress", None, True)),
                                            ("G008", ("L7", "Only gate", "access", 2.0, True))):
    _r = gates.create_gate(_loc, _name, 58.901, 24.501, direction=_dir, safety_minutes=_sm, is_default=_dflt)
    assert _r.get("id") == _key, _r
for _rid, _d, _dg in (("R6", "L5", "G005"), ("R7", "L6", None), ("R8", "L5", "G005"), ("R9", "L7", "G008")):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", (_rid, "L1", _d, "IPT1"))
    gates.set_route_gates(_rid, origin_gate_id="G002", dest_gate_id=_dg, origin_given=True, dest_given=True)
assert not gates.update_gate("G005", active=False).get("error")
assert not gates.update_gate("G008", active=False).get("error")
db.execute("UPDATE routes SET dest_gate_id = ? WHERE tenant_id = ? AND id = ?", ("G999", db.current_tenant(), "R8"))   # a deleted gate
_line("R6", "WS1", 4400.0, "IPT1")                        # 220 trips: laden at L5, named gate inactive -> G006
_line("R8", "WS1", 2200.0, "IPT1")                        # 110 trips: laden at L5, named gate gone -> G006
_line("R7", "WS1", 2200.0, "IPT1")                        # 110 trips: laden end has an exit only -> not shown
_line("R9", "WS1", 2200.0, "IPT1")                        # 110 trips: laden end's only gate is inactive -> not shown
assert gates.resolve({"id": "L5", "lat": 58.9, "lon": 24.5}, "entry", "G005", gates=gates.list_gates("L5"))["blocked"] == {"gate_id": "G005", "name": "Old gate", "reason": "inactive"}
res6 = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
b6 = {g["gate_id"]: g for g in res6["gates"]}
ok("⭐ a route naming an INACTIVE gate: its lorries are counted at the location's default entry gate (Main gate: 220 + 110 trips = 15.0 a day, 4 min check-in, holding), the inactive gate is not listed",
   "G006" in b6 and "G005" not in b6 and b6["G006"]["laden_per_day"] == round(330 / WD, 1) == 15.0 and b6["G006"]["gate_minutes"] == 4.0
   and b6["G006"]["flag"] is None and b6["G006"]["location_name"] == "Shut tip" and b6["G006"]["fallthrough_routes"] == []
   and b6["G001"]["empty_per_day"] == round((5550 + 110 + 220 + 110 + 110 + 110) / WD, 1), str(b6.get("G006"))[:300])
ok("...and the note names the cause, not a false 'no gate': inactive by name, deleted as 'no longer recorded'",
   res6["notes"].count("Shut tip: 1 route names gate Old gate, which is inactive, so arrivals there are counted at Main gate.") == 1
   and res6["notes"].count("Shut tip: 1 route names a gate that is no longer recorded, so arrivals there are counted at Main gate.") == 1
   and not any("Shut tip has no" in n for n in res6["notes"]), str(res6["notes"]))
ok("an egress-only location: not listed, and the note says 'no entry gate recorded' (it has a gate, an exit)",
   "G007" not in b6 and res6["notes"].count("Exit-only yard has no entry gate recorded, so arrivals there are not shown.") == 1, str(res6["notes"]))
ok("an inactive gate with no other entry gate: not listed, ONE note naming the inactive gate and that nothing else is recorded (no second 'no gate' note)",
   "G008" not in b6
   and res6["notes"].count("Shut yard: 1 route names gate Only gate, which is inactive, and no other entry gate is recorded, so arrivals there are not shown.") == 1
   and not any(n.startswith("Shut yard has no") for n in res6["notes"]) and len(res6["gates"]) == 4
   and all(("if arrivals are spread evenly" in s) or (s in _allowed_other) or s.endswith("they are not in the figures.")
           or s.endswith("so arrivals there are not shown.") or " so arrivals there are counted at " in s for s in [g["reason"] for g in res6["gates"]] + res6["notes"]),
   str(res6["notes"]))

# =========================================================================== #
#  8b. 14 Oct 2026 (bundle G, W17): each gate's open hours, the peak bands, the 85 % step  #
# =========================================================================== #
import copy as _copy  # noqa: E402
import gate_hours  # noqa: E402
ok("gate_hours: 07:30 is 450 min; 24:00, 7:00 and '' are not times; a window past midnight (22:00-06:00) is 480 min",
   gate_hours.minutes_of("07:30") == 450 and gate_hours.minutes_of("24:00") is None and gate_hours.minutes_of("7:00") is None
   and gate_hours.minutes_of("") is None
   and gate_hours.open_minutes({"open_from": "22:00", "open_to": "06:00"}, factors)["minutes"] == 480.0)
ok("gate_hours: open days are seven flags Monday first; none open is refused; a list of booleans is accepted",
   gate_hours.clean_days([1, 1, 1, 1, 1, 0, 0]) == "1111100" and bool(gate_hours.days_problem("0000000"))
   and bool(gate_hours.days_problem("11111")) and gate_hours.days_problem("1111100") is None and gate_hours.clean_days("") is None)
ok("gate_hours: peak bands — at most four, times, no overlap, not the same time",
   gate_hours.peak_bands_problem([{"from": "07:00", "to": "10:00"}, {"from": "09:00", "to": "11:00"}]) == "peak band 2 overlaps another band"
   and gate_hours.peak_bands_problem([{"from": "07:00", "to": "07:00"}]).endswith("the same time")
   and gate_hours.peak_bands_problem([{"from": "7", "to": "10:00"}]).startswith("peak band 1: from and to must be")
   and gate_hours.peak_bands_problem([{"from": "0%d:00" % i, "to": "0%d:30" % i} for i in range(5)]) == "at most 4 peak bands"
   and gate_hours.peak_bands_problem(gate_hours.PEAK_PLACEHOLDER) is None and gate_hours.peak_bands_problem(None) is None)
ok("gate_hours.status: 84 % none, 85 % amber, 100 % amber, 100.4 % red, anything on a closed day red, no capacity none",
   gate_hours.status(84, 100) is None and gate_hours.status(85, 100) == "amber" and gate_hours.status(100, 100) == "amber"
   and gate_hours.status(100.4, 100) == "red" and gate_hours.status(1, 100, open_today=False) == "red"
   and gate_hours.status(50, None) is None and gate_hours.status(0, 100) is None
   and gate_hours.STATUS_WORDS == {"red": "Over gate capacity", "amber": "Queue likely"})
# the hours, written through the gate write path
_bad = [gates.update_gate("G003", open_from="07:00"), gates.update_gate("G003", open_from="7am", open_to="15:00"),
        gates.update_gate("G003", open_from="07:00", open_to="07:00"), gates.update_gate("G003", open_days="0000000")]
ok("🔴 the gate write refuses half-typed hours, a non-time, the same time twice and a gate open on no day — each in words",
   [b.get("error") for b in _bad] == ["type both open hours (from and to), or clear both to use the default gate hours",
                                      "open from must be a 24-hour time such as 07:00",
                                      "open from and open to are the same time",
                                      "a gate must be open on at least one day (clear the days to mean every day)"], str(_bad))
_g3 = gates.update_gate("G003", open_from="07:00", open_to="15:00", open_days="1111100")
ok("the hours are stored and read back on the gate (open_days as seven flags)",
   _g3.get("open_from") == "07:00" and _g3.get("open_to") == "15:00" and _g3.get("open_days") == "1111100", str(_g3))
_r8 = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["gates"]}
ok("⭐ East compound open 07:00-15:00 (480 min): capacity 480 ÷ 3 = 160.0 a day, gap round(480 ÷ (5100 ÷ 22), 1), basis 'gate', closed on Saturdays and Sundays",
   _r8["G003"]["open_minutes"] == 480.0 and _r8["G003"]["capacity_per_day"] == 160.0 and _r8["G003"]["open_basis"] == "gate"
   and _r8["G003"]["gap_minutes"] == round(480 / (5100 / WD), 1) and _r8["G003"]["open_hours"] == "07:00–15:00"
   and _r8["G003"]["closed_days"] == "closed on Saturdays and Sundays" and _r8["G003"]["flag"] == "red"
   and _r8["G003"]["status_word"] == "Over gate capacity", str(_r8.get("G003"))[:300])
ok("near_per_day is 85 % of the capacity, rounded once from the unrounded figure (160 -> 136.0); None with no check-in",
   _r8["G003"]["near_per_day"] == round(480 / 3 * 0.85, 1) == 136.0 and {g["gate_id"]: g for g in gl}["G004"]["near_per_day"] is None)
# REVERSED 17 Oct 2026 (the user): a gate with no hours typed takes the default gate hours, with clock times — no longer
# the lorry shift
ok("a gate with no hours typed takes the default gate hours (07:00–17:00 set on Config here: 600 min, basis 'default', "
   "its hours in words, no closed days)",
   _r8["G001"]["open_minutes"] == 600.0 and _r8["G001"]["open_basis"] == "default"
   and _r8["G001"]["open_hours"] == "07:00–17:00" and _r8["G001"]["closed_days"] is None)
_fdef = _copy.deepcopy(factors)
_fdef["planning"].pop("default_gate_hours", None)
_rdef = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=_fdef, working_days=WD)["gates"]}
ok("⭐ with no default typed on Config, it is the user's 08:00–17:00: 540 min, capacity 540 ÷ 2 = 270.0 at West pit",
   _rdef["G001"]["open_minutes"] == 540.0 and _rdef["G001"]["open_hours"] == "08:00–17:00"
   and _rdef["G001"]["open_basis"] == "default" and _rdef["G001"]["capacity_per_day"] == 270.0
   and gate_hours.DEFAULT_GATE_HOURS == {"from": "08:00", "to": "17:00"}, str(_rdef.get("G001"))[:300])
ok("the lorry shift is not a gate's day: a 12 h shift on Config moves no gate's minutes",
   {g["gate_id"]: g["open_minutes"] for g in gate_arrivals.arrivals(
       9, acc_planner, factors={**_fdef, "planning": {**_fdef["planning"], "shift_hours_per_day": 12}}, working_days=WD)["gates"]}["G001"] == 540.0)
_fpk = _copy.deepcopy(factors)
_fpk["planning"]["peak_bands"] = [{"from": "07:00", "to": "08:00"}, {"from": "16:00", "to": "19:00"}]
_rp = gate_arrivals.arrivals(9, acc_planner, factors=_fpk, working_days=WD)
_rpg = {g["gate_id"]: g for g in _rp["gates"]}
ok("⭐ the peak bands are taken off the gate's open hours: 07:00-15:00 less 07:00-08:00 = 420 min (16:00-19:00 is outside), capacity 140.0",
   _rpg["G003"]["open_minutes"] == 420.0 and _rpg["G003"]["peak_minutes"] == 60.0 and _rpg["G003"]["capacity_per_day"] == 140.0,
   str(_rpg.get("G003"))[:300])
# REVERSED 17 Oct 2026: a gate on the default gate hours has clock times, so the bands come off it too, and the note that
# they could not be taken off is gone; the averages note says what comes off
ok("...and a gate on the default hours loses the bands too: 07:00-17:00 less 07:00-08:00 and 16:00-17:00 = 480 min; no "
   "note that the bands could not be taken off; the bands ride on the response",
   _rpg["G001"]["open_minutes"] == 480.0 and _rpg["G001"]["peak_minutes"] == 120.0
   and _rp["peak_bands"] == _fpk["planning"]["peak_bands"]
   and not any("taken off only" in n for n in _rp["notes"])
   and any(n.startswith("Averages only") and "less the no-delivery bands" in n for n in _rp["notes"])
   and _rp["limit"] == gate_hours.LIMIT_WORDS, str(_rp["notes"]))
# amber: West pit carries 6 210 trips by now (section 8 added the Shut tip lines), 282.3 a day at a 2 min check-in;
# 07:00-16:30 = 570 min -> capacity 285, 99 %: under the red rule (gap 2.0 = check-in), over the 85 % step
gates.update_gate("G001", open_from="07:00", open_to="16:30")
_ra = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["gates"]}
ok("⭐ the 85 % step: West pit at 570 open minutes is round(6210 ÷ 22 × 100 ÷ 285) = 99 % -> amber 'Queue likely' (gap 2.0 is not shorter than 2 min), and the reason says so",
   _ra["G001"]["capacity_per_day"] == 285.0 and _ra["G001"]["capacity_pct"] == round(6210 / WD * 100 / 285) == 99
   and _ra["G001"]["gap_minutes"] == 2.0
   and _ra["G001"]["flag"] == "amber" and _ra["G001"]["status_word"] == "Queue likely"
   and "99 % of what the gate can check in, so a queue is likely when lorries bunch" in _ra["G001"]["reason"]
   and "if arrivals are spread evenly" in _ra["G001"]["reason"], str(_ra.get("G001"))[:300])
_rr = gates.update_gate("G001", open_from="", open_to="", open_days="")
_r3 = gates.update_gate("G003", open_from=None, open_to=None, open_days=None)
ok("clearing the hours puts both gates back on the default gate hours (blank and None both clear)",
   _rr.get("open_from") is None and _rr.get("open_to") is None and _rr.get("open_days") is None
   and _r3.get("open_from") is None and _r3.get("open_days") is None
   and {g["gate_id"]: g["open_basis"] for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["gates"]}.get("G003") == "default")
_cg = gates.create_gate("L3", "Night gate", 58.702, 24.202, direction="access", safety_minutes=2, open_from="22:00", open_to="06:00", open_days="1111111")
ok("a gate created with hours past midnight stores them; one created half-typed is refused",
   _cg.get("open_from") == "22:00" and _cg.get("open_days") == "1111111"
   and gates.create_gate("L3", "Bad", 58.7, 24.2, open_to="06:00").get("error", "").startswith("type both open hours"), str(_cg))
gates.update_gate(_cg["id"], active=False)

# 17 Oct 2026 (the user: "planned close times throughout the day"): the gate's shut windows, through the gate write path
_sbad = [gates.update_gate("G003", shut_windows=[{"from": "12:00", "to": "11:00"}]),
         gates.update_gate("G003", shut_windows=[{"from": "08:00", "to": "09:00"}, {"from": "08:30", "to": "10:00"}]),
         gates.update_gate("G003", shut_windows=[{"from": "1pm", "to": "13:30"}]),
         gates.update_gate("G003", shut_windows=[{"from": "1%d:00" % i, "to": "1%d:10" % i} for i in range(5)]),
         gates.update_gate("G003", shut_windows=[{"from": "18:00", "to": "19:00"}]),
         gates.update_gate("G003", shut_windows=[{"from": "07:00", "to": "17:00"}]),
         gates.update_gate("G003", shut_windows="junk"),
         gates.update_gate("G003", shut_windows=[{"from": "12:00", "to": "12:00"}])]
# NARROWED 17 Oct 2026 (the review): each refusal names the shut time as typed, never its place in the list (the form
# drops blank rows, so a number would not match the row on screen)
ok("🔴 the gate write refuses a shut time that ends before it starts, overlapping ones, a non-time, more than four, one "
   "outside the gate's hours, ones that leave no open time, a bad shape and the same time twice — each in words, naming it",
   [b.get("error") for b in _sbad] == ["shut time 12:00–11:00 must end after it starts (a shut time stays within one day)",
                                       "shut time 08:30–10:00 overlaps another shut time",
                                       "shut time 1pm–13:30: from and to must be 24-hour times such as 12:00",
                                       "at most 4 shut times a gate",
                                       "shut time 18:00–19:00 is outside the open hours 07:00–17:00 (the default)",
                                       "the shut times leave the gate no open time within 07:00–17:00 (the default)",
                                       "shut times must be a list of from–to times",
                                       "shut time 12:00–12:00: from and to are the same time"], str(_sbad))
ok("🔴 a half-typed shut time (one box blank) is refused in words that say both times are needed",
   gates.update_gate("G003", shut_windows=[{"from": "12:00", "to": ""}]).get("error")
   == "a shut time needs both times, from and to (12:00 to blank)")
_s4 = gates.update_gate("G003", shut_windows=[{"from": "1%d:00" % i, "to": "1%d:10" % i} for i in range(4)])
ok("⭐ exactly four shut times are accepted (the cap is four, not three) and two back to back are too",
   len(_s4.get("shut_windows") or []) == 4
   and gates.update_gate("G003", shut_windows=[{"from": "09:00", "to": "10:00"}, {"from": "08:00", "to": "09:00"}]).get("shut_windows")
   == [{"from": "08:00", "to": "09:00"}, {"from": "09:00", "to": "10:00"}], str(_s4))
gates.update_gate("G003", shut_windows=[])
_ng = gates.create_gate("L3", "Late gate", 58.703, 24.203, direction="access", safety_minutes=2, open_from="18:00",
                        open_to="02:00", shut_windows=[{"from": "23:00", "to": "00:00"}])
ok("⭐ a shut time can end at midnight (23:00–00:00, 'to 00:00' is the end of the day): on an 18:00–02:00 gate, 480 − 60 = 420",
   _ng.get("shut_windows") == [{"from": "23:00", "to": "00:00"}]
   and gate_hours.open_minutes(_ng, factors)["minutes"] == 420.0 and gate_hours.open_minutes(_ng, factors)["shut_minutes"] == 60.0, str(_ng))
gates.update_gate(_ng["id"], active=False)
ok("the stored shut text in the API's own shape (a JSON list, as another tool might write it) reads too",
   gate_hours.shut_windows({"shut_windows": '[{"from": "08:30", "to": "09:15"}]'}) == [{"from": "08:30", "to": "09:15"}]
   and gate_hours.shut_windows({"shut_windows": '[{"from": "08:30"'}) == [])
# creating a gate with shut times (the INSERT's 19 columns), and refused at creation as on an edit
_cs = gates.create_gate("L3", "Shut gate", 58.704, 24.204, direction="access", safety_minutes=2,
                        shut_windows=[{"from": "15:00", "to": "15:45"}, {"from": "08:30", "to": "09:15"}])
_csrow = db.query("SELECT shut_windows, safety_minutes, open_from, access_zone_id FROM location_gates WHERE tenant_id = ? AND id = ?",
                  (db.current_tenant(), _cs.get("id")))[0]
ok("⭐ a gate CREATED with shut times stores them start-sorted beside its other columns, and one outside the hours is refused",
   _cs.get("shut_windows") == [{"from": "08:30", "to": "09:15"}, {"from": "15:00", "to": "15:45"}]
   and _csrow["shut_windows"] == "08:30-09:15,15:00-15:45" and _csrow["safety_minutes"] == 2.0 and _csrow["open_from"] is None
   and _csrow["access_zone_id"] is None
   and gates.create_gate("L3", "Bad shut", 58.7, 24.2, shut_windows=[{"from": "18:00", "to": "19:00"}]).get("error")
   == "shut time 18:00–19:00 is outside the open hours 07:00–17:00 (the default)", str(_csrow))
gates.update_gate(_cs["id"], active=False)
_s3 = gates.update_gate("G003", shut_windows=[{"from": "15:00", "to": "15:45"}, {"from": "08:30", "to": "09:15"}])
_s3row = db.query("SELECT shut_windows FROM location_gates WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "G003"))[0]
ok("⭐ shut times are stored start-sorted ('08:30-09:15,15:00-15:45') and read back as typed",
   _s3.get("shut_windows") == [{"from": "08:30", "to": "09:15"}, {"from": "15:00", "to": "15:45"}]
   and _s3row["shut_windows"] == "08:30-09:15,15:00-15:45", str(_s3))
_rs = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["gates"]}
ok("⭐ East compound shut 08:30–09:15 and 15:00–15:45: 600 − 90 = 510 open minutes, capacity 170.0, the shut time words",
   _rs["G003"]["open_minutes"] == 510.0 and _rs["G003"]["shut_minutes"] == 90.0 and _rs["G003"]["capacity_per_day"] == 170.0
   and _rs["G003"]["shut_words"] == "08:30–09:15 and 15:00–15:45"
   and _rs["G003"]["shut_windows"] == [{"from": "08:30", "to": "09:15"}, {"from": "15:00", "to": "15:45"}], str(_rs.get("G003"))[:300])
_fsb = _copy.deepcopy(factors)
_fsb["planning"]["peak_bands"] = [{"from": "07:00", "to": "10:00"}]
_rsb = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=_fsb, working_days=WD)["gates"]}
ok("⭐ a shut time inside a no-delivery band counts once: 600 − the band 180 − 15:00–15:45 = 375 (08:30–09:15 is in the band)",
   _rsb["G003"]["open_minutes"] == 375.0 and _rsb["G003"]["peak_minutes"] == 180.0 and _rsb["G003"]["shut_minutes"] == 45.0,
   str(_rsb.get("G003"))[:300])
_fpo = _copy.deepcopy(factors)
_fpo["planning"]["peak_bands"] = [{"from": "07:00", "to": "10:00"}]
_gpo = {"open_from": None, "open_to": None, "shut_windows": "09:30-10:30"}
ok("⭐ a shut time PARTLY inside a band counts its other part only: 09:30–10:30 against 07:00–10:00 = 600 − 180 − 30 = 390",
   (gate_hours.open_minutes(_gpo, _fpo)["minutes"], gate_hours.open_minutes(_gpo, _fpo)["peak_minutes"],
    gate_hours.open_minutes(_gpo, _fpo)["shut_minutes"]) == (390.0, 180.0, 30.0))
ok("...and one across the closing time counts its part inside the hours (16:30–17:30 on 07:00–17:00 takes 30) and is accepted",
   gate_hours.open_minutes({"shut_windows": "16:30-17:30"}, factors)["shut_minutes"] == 30.0
   and gate_hours.fit_problem({"shut_windows": "16:30-17:30"}, factors) is None)
ok("the averages note says the shut times come off", any(n.startswith("Averages only") and "less its shut times" in n
   for n in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["notes"]))
ok("🔴 new hours that would leave a stored shut time outside them are refused, naming it; the hours stay as they were",
   gates.update_gate("G003", open_from="10:00", open_to="14:00").get("error")
   == "shut time 08:30–09:15 is outside the open hours 10:00–14:00" and gates.get_gate("G003")["open_from"] is None)
import tenant_package  # noqa: E402
_pk = [r for r in tenant_package.export_tenant()["tables"]["location_gates"] if r["id"] == "G003"]
ok("the shut times travel in the tenant package (the column, by name)", _pk and _pk[0].get("shut_windows") == "08:30-09:15,15:00-15:45")
ok("a stored shut text that is not valid (a package imports rows unchecked) reads as no shut times, never an error",
   gate_hours.shut_windows({"shut_windows": "25:00-26:00"}) == [] and gate_hours.shut_windows({"shut_windows": None}) == []
   and gate_hours.open_minutes({"shut_windows": "garbage"}, factors)["minutes"] == 600.0)
ok("bands that leave a gate no open minute: 0 minutes, no capacity (the week then treats the day as shut)",
   gate_hours.open_minutes({}, {"planning": {"peak_bands": [{"from": "06:00", "to": "18:00"}]}})["minutes"] == 0.0
   and gate_hours.capacity(0.0, 3) is None)
ok("clearing the shut times ([]) stores none", gates.update_gate("G003", shut_windows=[]).get("shut_windows") == []
   and db.query("SELECT shut_windows FROM location_gates WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "G003"))[0]["shut_windows"] is None)

# =========================================================================== #
#  8c. 14 Oct 2026 (bundle G, W17): the committed week at each gate, and the clash flags    #
# =========================================================================== #
import datetime as _dtm  # noqa: E402
import clashes as _clashes  # noqa: E402
_TODAY = _dtm.date(2026, 9, 16)                        # a Wednesday in Sep 2026, the fixture's month
_pg = lookahead.page("commit", today=_TODAY)
_gw = _pg.get("gates_week") or {}
_gwg = {g["gate_id"]: g for g in _gw.get("gates") or []}
# the expectation, independently: East compound (G003) takes R1 + R3 laden and R4's lorries coming to load, per day
_exp3 = {}
for _l in _pg["commit"]["lines"]:
    if _l["route_id"] in ("R1", "R3", "R4"):
        for _d in _l["days"]:
            _exp3[_d["day_date"]] = _exp3.get(_d["day_date"], 0) + int((_d.get("derived") or {}).get("trips") or 0)
ok("⭐ W17: the Look-ahead page carries the committed week at each gate: weekdays only (no weekend arrivals), the busiest first",
   _gw.get("dates") and all(_dtm.date.fromisoformat(x).weekday() < 5 for x in _gw["dates"]) and len(_gw["dates"]) == 5
   and _gw.get("near_pct") == 85 and _gw.get("limit") == gate_hours.LIMIT_WORDS and "G003" in _gwg, str(_gw)[:300])
ok("⭐ W17: East compound's arrivals each day are the grid's own trips of R1 + R3 (laden) + R4 (coming to load), summed",
   [d["arrivals"] for d in _gwg["G003"]["days"]] == [_exp3.get(x, 0) for x in _gw["dates"]] and sum(_exp3.values()) > 0,
   f"{[d['arrivals'] for d in _gwg['G003']['days']]} vs {[_exp3.get(x, 0) for x in _gw['dates']]}")
_c3 = _gwg["G003"]["capacity_per_day"]
ok("W17: capacity a day = 600 open minutes ÷ the 3 min check-in = 200.0; the 85 % step 170.0; every weekday's % = round(arrivals × 100 ÷ 200)",
   _c3 == 200.0 and _gwg["G003"]["near_per_day"] == 170.0
   and all(d["pct"] == (round(d["arrivals"] * 100 / 200) if d["arrivals"] else None) for d in _gwg["G003"]["days"]))
ok("⭐ W17: the status of each day is gate_hours.status: over 100 % red 'Over gate capacity', 85 % or more amber 'Queue likely'",
   all(d["flag"] == gate_hours.status(d["arrivals"], 200.0) and d["status_word"] == gate_hours.STATUS_WORDS.get(d["flag"]) for d in _gwg["G003"]["days"])
   and any(d["flag"] == "red" for d in _gwg["G003"]["days"]), str([(d["arrivals"], d["flag"]) for d in _gwg["G003"]["days"]]))
ok("W17: a gate with no check-in typed (North stockpile) is listed with its arrivals, no capacity and no flag — never compared",
   "G004" in _gwg and _gwg["G004"]["capacity_per_day"] is None and all(d["flag"] is None and d["pct"] is None for d in _gwg["G004"]["days"]))
ok("🔴 W17: the page's week carries no line keys (they would name other teams' lines): _lines stripped",
   "_lines" not in json.dumps(_gw))
_fl = [f for f in _pg["clashes"]["flags"] if f["code"] in ("GATE_OVER", "GATE_NEAR")]
_red_days = [d["date"] for d in _gwg["G003"]["days"] if d["flag"] == "red"]
ok("⭐ W17: the clash rail raises GATE_OVER on every line arriving at East compound on each red day (R1, R3 laden; R4 coming to load)",
   _red_days and all({f["route_id"] for f in _fl if f["code"] == "GATE_OVER" and f["gate_id"] == "G003" and f["day_date"] == x}
                     == {l["route_id"] for l in _pg["commit"]["lines"] if l["route_id"] in ("R1", "R3", "R4")
                         and any(dd["day_date"] == x and int((dd.get("derived") or {}).get("trips") or 0) > 0 for dd in l["days"])}
                     for x in _red_days), str([(f["route_id"], f["day_date"]) for f in _fl])[:300])
_f0 = next((f for f in _fl if f["gate_id"] == "G003" and f["code"] == "GATE_OVER"), {})
_d0 = next((d for d in _gwg["G003"]["days"] if d["date"] == _f0.get("day_date")), {})
ok("W17: the flag's words name the gate, the day and the gate's total against capacity (never a team's share)",
   _f0.get("text") == f"East compound, Compound gate on {_d0.get('day')}: {_d0.get('arrivals')} lorries against the 200 it can check in ({_d0.get('pct')} %)"
   and _f0.get("arrivals") == _d0.get("arrivals") and _f0.get("capacity") == 200.0, str(_f0))
ok("W17: the codes sit in the rail's order — GATE_OVER after ROUTE_CAP, GATE_NEAR (a warning) after UNBAKED; flags, never blocks",
   _clashes.CODES.index("GATE_OVER") == _clashes.CODES.index("ROUTE_CAP") + 1 and _clashes.CODES.index("GATE_NEAR") == _clashes.CODES.index("UNBAKED") + 1)
# the exports: the XLSX Clashes sheet and the commit-week PDF name the gate flags and print the honest limit
import io as _io  # noqa: E402
import export as _export  # noqa: E402
import openpyxl as _openpyxl  # noqa: E402
from portable import offline as _offline, pdf_text as _pdf_text  # noqa: E402
_offline(_export)
_wb = _openpyxl.load_workbook(_io.BytesIO(_export.build_xlsx(_pg)))
_cl_rows = [[c.value for c in r] for r in _wb["Clashes"].iter_rows()]
_gate_rows = [r for r in _cl_rows if r and r[0] == "GATE OVER CAPACITY"]
ok("⭐ W17 XLSX: the Clashes sheet lists each GATE OVER CAPACITY flag with its route, day and words, and prints the limit under them",
   _gate_rows and all(r[4] in _red_days for r in _gate_rows) and any(r[5] == _f0.get("text") for r in _gate_rows)
   and any(r and r[0] == _export.GATE_LIMIT for r in _cl_rows)
   and any(r and r[0] == "Gate capacity" and r[1] == _export.GATE_LIMIT for r in ([[c.value for c in x] for x in _wb["About"].iter_rows()])),
   str(_cl_rows[:4]))
_ptxt = _pdf_text(_export.build_pdf(_pg))
_flat = re.sub(r"\s+", " ", _ptxt or "")
ok("⭐ W17 PDF: the flags list names GATE OVER CAPACITY and the gate, and prints the limit",
   "GATE OVER CAPACITY" in _flat and "East compound, Compound gate" in _flat
   # NARROWED 17 Oct 2026: the limit names the shut times and bands; it is built from gate_hours.LIMIT_WORDS now
   and "Gate capacity: planned arrivals spread evenly over the gate's open hours, less its shut times and the no-delivery bands; no hourly peak is known." in _flat
   and _export.GATE_LIMIT == "Gate capacity: p" + gate_hours.LIMIT_WORDS[1:], _flat[:300])

# ---- 17 Oct 2026: the Look-ahead's Day sheet (export.day_sheet_rows / build_day_sheet_pdf) and the gate flags ----
# Two bugs on main since W17: the sheet printed the raw code "GATE_OVER" (no word, no rank: it sorted after NOT ROUTED,
# so a gate over capacity hid behind SHARE), and it joined flags to a line by key only, so a gate flag dated Wednesday
# printed on Monday's sheet too. A flag that carries day_date belongs on that day's sheet only.
import copy as _cp  # noqa: E402
_fe = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
_lfl = dict(re.findall(r'(\w+): "([^"]*)"', re.search(r"const LINE_FLAG_LABEL = \{([^}]*)\}", _fe).group(1)))
_lfr = [c for c, v in sorted(re.findall(r"(\w+): ([\d.]+)", re.search(r"const LA_FLAG_RANK = \{([^}]*)\}", _fe).group(1)),
                             key=lambda cv: float(cv[1]))]
ok("⭐ DAY SHEET: the gate flags read GATE OVER / GATE NEAR, the grid's and the phone day card's words (LINE_FLAG_LABEL); "
   "every clash code has a word, so no code prints raw",
   _export.DAY_FLAG_WORD.get("GATE_OVER") == "GATE OVER" == _lfl.get("GATE_OVER")
   and _export.DAY_FLAG_WORD.get("GATE_NEAR") == "GATE NEAR" == _lfl.get("GATE_NEAR")
   and set(_export.DAY_FLAG_WORD) == set(_lfl) == set(_clashes.CODES)
   # the one word that differs: Helvetica on the PDF has no ≠
   and all(_export.DAY_FLAG_WORD[c] == _lfl[c] for c in _lfl if c != "DAYS_NE_WEEK")
   and _export.DAY_FLAG_WORD["DAYS_NE_WEEK"] == "DAYS NOT = WEEK" and _lfl["DAYS_NE_WEEK"] == "DAYS ≠ WEEK",
   str((_export.DAY_FLAG_WORD, _lfl)))
ok("⭐ DAY SHEET: the flags rank as the grid's LA_FLAG_RANK — GATE OVER after CAP, before STOCKPILE OVER; GATE NEAR after "
   "MONTH CHANGED, before NOT ROUTED",
   list(_export.DAY_FLAG_RANK) == _lfr and set(_export.DAY_FLAG_RANK) == set(_clashes.CODES)
   and _export.DAY_FLAG_RANK.index("GATE_OVER") == _export.DAY_FLAG_RANK.index("ROUTE_CAP") + 1
   # NARROWED 27 Oct 2026 (stockpile forecast, D7): STOCKPILE EMPTY and STOCKPILE SOON, the two amber stockpile warnings,
   # rank after GATE NEAR and before NOT ROUTED
   and _export.DAY_FLAG_RANK.index("GATE_NEAR") == _export.DAY_FLAG_RANK.index("UNBAKED") - 3
   and _export.DAY_FLAG_RANK[_export.DAY_FLAG_RANK.index("GATE_NEAR") + 1:_export.DAY_FLAG_RANK.index("UNBAKED")] == ("STOCKPILE_EMPTY", "STOCKPILE_SOON"),
   str((_export.DAY_FLAG_RANK, _lfr)))
# the week as the page reads it: every weekday's rows carry only that day's dated flags (and every undated one)
_dsw = {}
for _x in _gw["dates"]:
    _dsw[_x] = _export.day_sheet_rows(_pg, _x)
_want = {}
for _x in _gw["dates"]:
    for _r in _dsw[_x]:
        _own = sorted((f for f in _pg["clashes"]["flags"] if _export._line_key(f) == _r["key"] and f.get("day_date") in (None, "", _x)),
                      key=lambda f: _export.DAY_FLAG_RANK.index(f["code"]) if f["code"] in _export.DAY_FLAG_RANK else 99)
        _want[(_x, _r["key"])] = [f["code"] for f in _own]
_dw = {d["date"]: d["day"] for d in _gwg["G003"]["days"]}
ok("⭐ DAY SHEET: each day's rows carry that day's gate / share flags only (were all five days'), every undated flag still",
   _want and all(_r.get("codes", []) == _want[(_x, _r["key"])] for _x in _gw["dates"] for _r in _dsw[_x])
   and any("GATE_OVER" in _r.get("codes", []) for _x in _red_days for _r in _dsw[_x])
   # the gate sentences name the sheet's own day, never another
   and all(t.startswith("GATE OVER: East compound, Compound gate on " + _dw[_x] + ":")
           for _x in _gw["dates"] for _r in _dsw[_x] for t in _r["flag_texts"] if "Compound gate" in t)
   and all((" on " + _dw[_x] + ":") in t for _x in _gw["dates"] for _r in _dsw[_x] for t in _r["flag_texts"] if t.startswith("GATE ")),
   str([(_x, _r["route_id"], _r.get("codes", [])) for _x in _gw["dates"][:2] for _r in _dsw[_x]])[:400])
ok("DAY SHEET: on a red day a line with a gate over capacity and a share shows GATE OVER first (it was SHARE), +N other kinds",
   any({"GATE_OVER", "IPT_SHARE"} <= set(_r.get("codes", [])) for _x in _red_days for _r in _dsw[_x])
   and all(_r["flag"] == "GATE OVER" and _r["more"] == len(set(_r.get("codes", []))) - 1
           for _x in _red_days for _r in _dsw[_x] if {"GATE_OVER", "IPT_SHARE"} <= set(_r.get("codes", []))),
   str([(_r["route_id"], _r["flag"], _r.get("codes", [])) for _r in _dsw[_red_days[0]]]) if _red_days else "no red day")
# the bug as reported: a line with a gate flag dated ONE day (X); another day Y of the same line has loads and no gate flag
_X = _red_days[0] if _red_days else None
_L = next((r for r in _dsw.get(_X, []) if "GATE_OVER" in r.get("codes", [])), None)
_Y = next((y for y in _gw["dates"] if y != _X and any(r["key"] == (_L or {}).get("key") for r in _dsw[y])), None)
_pg1 = _cp.deepcopy(_pg)
_pg1["clashes"]["flags"] = [f for f in _pg1["clashes"]["flags"] if f["code"] not in ("GATE_OVER", "GATE_NEAR") or f.get("day_date") == _X]
_ry = {r["key"]: r for r in _export.day_sheet_rows(_pg1, _Y)} if _Y else {}
_rx = {r["key"]: r for r in _export.day_sheet_rows(_pg1, _X)} if _X else {}
_ty = " ".join(_pdf_text(_export.build_day_sheet_pdf(_pg1, _Y)).split()) if _Y else ""
_tx = " ".join(_pdf_text(_export.build_day_sheet_pdf(_pg1, _X)).split()) if _X else ""
ok("⭐ DAY SHEET: a gate flag dated one day is on THAT day's sheet only — none on another day of the same line, no limit line there",
   _L and _Y and "GATE_OVER" in _rx[_L["key"]].get("codes", []) and _rx[_L["key"]]["flag"] == "GATE OVER"
   and not any(c in ("GATE_OVER", "GATE_NEAR") for r in _ry.values() for c in r.get("codes", []))
   and "GATE OVER" not in _ty and "Compound gate" not in _ty and _export.GATE_LIMIT not in _ty
   # an undated flag stays on both days (NOT ROUTED is the line's all week)
   and ("UNBAKED" in _rx[_L["key"]].get("codes", [])) == ("UNBAKED" in _ry[_L["key"]].get("codes", [])),
   f"X {_X} Y {_Y} line {(_L or {}).get('route_id')}: {_ty[:300]}")
ok("⭐ DAY SHEET PDF: the gate day reads GATE OVER in words — counted per kind, the sentence with the gate and the day — "
   "and prints the gate limit under the flags; no raw code anywhere",
   _X and re.search(r"GATE OVER on \d+ lines?", _tx) is not None
   and ("GATE OVER: East compound, Compound gate on " + _dw[_X] + ":") in _tx and _export.GATE_LIMIT in _tx
   and not re.search(r"GATE_(OVER|NEAR)", _tx) and not re.search(r"GATE_(OVER|NEAR)", _ty), _tx[:400])
# GATE NEAR, the warning: after SHARE, before NOT ROUTED; on its own it heads the row and prints the limit too
_ln = _cp.deepcopy(next(l for l in _pg["commit"]["lines"] if _export._line_key(l) == _L["key"])) if _L else {}
_mk = lambda code, **kw: dict(code=code, route_id=_ln.get("route_id"), month_index=_ln.get("month_index"),
                              discipline=_ln.get("discipline") or "", section_id=_ln.get("section_id") or "",
                              ipt=_ln.get("ipt"), text="words of the test", **kw)
_pgn = {"today": _pg.get("today"), "commit": {"lines": [_ln]},
        "clashes": {"flags": [_mk("UNBAKED"), _mk("GATE_NEAR", day_date=_X), _mk("IPT_SHARE", day_date=_X)]}}
_pgo = {"today": _pg.get("today"), "commit": {"lines": [_ln]},
        "clashes": {"flags": [_mk("STOCKPILE_OVER"), _mk("GATE_OVER", day_date=_X), _mk("ROUTE_CAP", day_date=_X)]}}
_rn = _export.day_sheet_rows(_pgn, _X) if _X else []
_ro = _export.day_sheet_rows(_pgo, _X) if _X else []
_tn = " ".join(_pdf_text(_export.build_day_sheet_pdf({**_pgn, "clashes": {"flags": [_mk("GATE_NEAR", day_date=_X)]}}, _X)).split()) if _X else ""
ok("DAY SHEET: the ranks in use — SHARE > GATE NEAR > NOT ROUTED; CAP > GATE OVER > STOCKPILE OVER; a GATE NEAR alone heads "
   "its row and prints the gate limit",
   len(_rn) == 1 and _rn[0].get("codes", []) == ["IPT_SHARE", "GATE_NEAR", "UNBAKED"] and _rn[0]["flag"] == "SHARE" and _rn[0]["more"] == 2
   and len(_ro) == 1 and _ro[0].get("codes", []) == ["ROUTE_CAP", "GATE_OVER", "STOCKPILE_OVER"] and _ro[0]["flag"] == "CAP"
   and "GATE NEAR: words of the test" in _tn and _export.GATE_LIMIT in _tn and re.search(r"GATE NEAR on 1 line\b", _tn) is not None
   and not re.search(r"GATE_(OVER|NEAR)", _tn),
   str((_rn, _ro))[:400] + " | " + _tn[:300])

# a closed day, and the near step: East compound closed on Wednesdays; West pit's hours cut to make it near
gates.update_gate("G003", open_from="07:00", open_to="17:00", open_days="1101111")
gates.update_gate("G001", open_from="07:00", open_to="16:00")          # 540 min ÷ 2 = 270 a day
_pg2 = lookahead.page("commit", today=_TODAY)
_g2 = {g["gate_id"]: g for g in _pg2["gates_week"]["gates"]}
_wed = next(d for d in _g2["G003"]["days"] if _dtm.date.fromisoformat(d["date"]).weekday() == 2)
ok("⭐ W17: a gate closed on Wednesdays has capacity 0 that day, and its arrivals are 'Over gate capacity' with the reason in words",
   _wed["open"] is False and _wed["capacity"] == 0.0 and _wed["pct"] is None and (_wed["arrivals"] == 0 or _wed["flag"] == "red")
   and _g2["G003"]["closed_days"] == "closed on Wednesdays", str(_wed))
_fw = [f for f in _pg2["clashes"]["flags"] if f["code"] == "GATE_OVER" and f["gate_id"] == "G003" and f["day_date"] == _wed["date"]]
ok("W17: ...and the clash text says the gate is closed that day, not a percentage",
   (_wed["arrivals"] == 0) or (_fw and _fw[0]["text"] == f"East compound, Compound gate on {_wed['day']}: {_wed['arrivals']} lorries planned, but the gate is closed on Wednesdays"),
   str(_fw[:1]))
_near = [d for d in _g2["G001"]["days"] if d["flag"] == "amber"]
_fn = [f for f in _pg2["clashes"]["flags"] if f["code"] == "GATE_NEAR" and f["gate_id"] == "G001"]
ok("⭐ W17: West pit at 270 a day: the days at 85 % or more are amber, each with a GATE_NEAR flag saying 'near capacity'",
   all((85 <= d["pct"] <= 100) for d in _near) and {f["day_date"] for f in _fn} == {d["date"] for d in _near}
   and all(f["text"].endswith(", near capacity") for f in _fn), str([(d["arrivals"], d["pct"], d["flag"]) for d in _g2["G001"]["days"]]))
gates.update_gate("G003", open_from="", open_to="", open_days="")
gates.update_gate("G001", open_from="", open_to="", open_days="")
os.environ["IPT2_CODE"] = "ipt2-secret"
try:
    access.set_current("ipt2-secret")
    _pgt = lookahead.page("commit", today=_TODAY)
finally:
    os.environ.pop("IPT2_CODE", None)
    access.set_current("planner123")
ok("🔴 W17: a team code sees the gate's total (same arrivals as the planner) but flags on its own lines only (R3 for Team 2)",
   [d["arrivals"] for d in {g["gate_id"]: g for g in _pgt["gates_week"]["gates"]}["G003"]["days"]] == [d["arrivals"] for d in _gwg["G003"]["days"]]
   and {f["route_id"] for f in _pgt["clashes"]["flags"] if f["code"] in ("GATE_OVER", "GATE_NEAR")} <= {"R3"}
   and any(f["code"] == "GATE_OVER" for f in _pgt["clashes"]["flags"]), str({f["route_id"] for f in _pgt["clashes"]["flags"]}))
# 17 Oct 2026 (the review): a gate whose shut times and the scheme's bands leave it NO open time — one meaning everywhere.
# The gate write and a Config save from the page both refuse it; it can still arrive by a package or a save made
# elsewhere, so the read says it in words: shut all day, red when lorries come, capacity 0, never "no check-in typed".
import network as _network  # noqa: E402
_cfg0 = json.loads(json.dumps(config.load(conversions, use_cache=False)))
ok("the gate write accepts 10:00–16:00 on East compound while the scheme has no bands",
   gates.update_gate("G003", shut_windows=[{"from": "10:00", "to": "16:00"}]).get("shut_windows") == [{"from": "10:00", "to": "16:00"}])
_cfgb = json.loads(json.dumps(_cfg0))
_cfgb["planning"]["peak_bands"] = [{"from": "07:00", "to": "10:00"}, {"from": "16:00", "to": "19:00"}]
_gp = config.gate_problems(_cfgb, before=_cfg0)
ok("⭐ a Config save that adds bands leaving a gate no open time is REFUSED from the page, naming the gate and why",
   "Default gate hours and no-delivery bands: East compound, Compound gate: the shut times and the no-delivery bands leave the "
   "gate no open time within 07:00–17:00 (the default). Change the gate on Data → Locations first, or keep the hours." in _gp
   and config.save(_cfgb, by="test", network=_network)["ok"] is False
   and config.gate_problems(_cfg0, before=_cfg0) == [], str(_gp))
_cfgd = json.loads(json.dumps(_cfg0))
_cfgd["planning"]["default_gate_hours"] = {"from": "11:00", "to": "17:00"}
gates.update_gate("G001", shut_windows=[{"from": "08:00", "to": "08:45"}])
ok("⭐ ...and one that moves the default gate hours off a gate's shut time names it too (the shut time would take nothing off)",
   any("West pit, Weighbridge (in): shut time 08:00–08:45 is outside the open hours 11:00–17:00 (the default)" in p
       for p in config.gate_problems(_cfgd, before=_cfg0)), str(config.gate_problems(_cfgd, before=_cfg0)))
gates.update_gate("G001", shut_windows=[])
config.save(_cfgb, by="test (no page check)")              # as a package or a hand edit could leave it
config.invalidate()
_pgz = lookahead.page("commit", today=_TODAY)
_gz = {g["gate_id"]: g for g in _pgz["gates_week"]["gates"]}.get("G003") or {}
_fz = [f for f in _pgz["clashes"]["flags"] if f["code"] == "GATE_OVER" and f["gate_id"] == "G003"]
ok("⭐ Gates this week: no open time = every day shut (capacity 0, any arrival red), said so, and the rail says why, not 'closed'",
   _gz.get("no_open_time") is True and _gz.get("capacity_per_day") == 0.0 and _gz.get("open_minutes") == 0.0
   and all(d["open"] is False and d["capacity"] == 0.0 and (d["arrivals"] == 0 or d["flag"] == "red") for d in _gz.get("days", []))
   and _fz and all(f["text"].endswith("but the no-delivery bands and the gate's shut times leave it no open time") for f in _fz),
   str(_fz[:1]) + str(_gz)[:200])
_mz = {g["gate_id"]: g for g in gate_arrivals.arrivals(9, acc_planner, factors=conversions.load_factors(), working_days=WD)["gates"]}["G003"]
ok("⭐ the Dashboard's month: the same gate is red 'Over gate capacity' with the no-open-time words and capacity 0",
   _mz["no_open_time"] is True and _mz["flag"] == "red" and _mz["status_word"] == "Over gate capacity"
   and _mz["capacity_per_day"] == 0.0 and _mz["reason"] == gate_arrivals.NO_OPEN_TIME, str(_mz)[:300])
assert config.save(_cfg0, by="test (restore)")["ok"]
config.invalidate()
gates.update_gate("G003", shut_windows=[])
# 17 Oct 2026 (the review): the default gate hours are a GATE's day; the lorry shift that sets trips per lorry is untouched
ok("🔴 the lorry figures never read the gate hours: derived.py names neither the default gate hours nor gate_hours, and the "
   "trips rule gives the same with the default absent or 06:00–20:00",
   "default_gate_hours" not in open(os.path.join(BACKEND, "derived.py"), encoding="utf-8").read()
   and "gate_hours" not in open(os.path.join(BACKEND, "derived.py"), encoding="utf-8").read()
   and all(gate_arrivals.trips_for(r, {**factors, "planning": {**factors["planning"], "default_gate_hours": {"from": "06:00", "to": "20:00"}}})
           == gate_arrivals.trips_for(r, _fdef) for r in db.query("SELECT * FROM forecasts WHERE tenant_id = ?", (db.current_tenant(),))))

# the frontend fixture: the planner's committed week with its gates (the Look-ahead's W17 card reads it)
_fx_w = os.path.join(HERE, "fixtures", "lookahead_gates_week.json")
if not FAIL:
    with open(_fx_w, "w", encoding="utf-8", newline="\n") as _fh:
        _fh.write(json.dumps(_pg["gates_week"], indent=1, ensure_ascii=False))
ok("the fixture backend/tests/fixtures/lookahead_gates_week.json is written from a clean run, LF on disk",
   os.path.exists(_fx_w) and b"\r\n" not in open(_fx_w, "rb").read())

# =========================================================================== #
#  9. The fixture for the frontend harnesses (planner view, month 9)          #
#     Written LAST and only from a clean run (a regressed module must not move the "server truth" render_frontend reads). #
#     LF on disk (.gitattributes); it is tracked, so a change shows in git status.                                         #
# =========================================================================== #
_fix_dir = os.path.join(HERE, "fixtures")
_fix_path = os.path.join(_fix_dir, "gate_arrivals.json")
if not FAIL:
    os.makedirs(_fix_dir, exist_ok=True)
    with open(_fix_path, "w", encoding="utf-8", newline="\n") as _fh:
        _fh.write(json.dumps(res, indent=1, ensure_ascii=False))
ok("the fixture backend/tests/fixtures/gate_arrivals.json is written from a clean run (planner view, month 9, three gates: one red, one untyped, one holding), LF on disk",
   os.path.exists(_fix_path) and len(gl) == 3 and b"\r\n" not in open(_fix_path, "rb").read()
   and [g["flag"] for g in gl].count("red") == 1 and [g["gate_minutes"] for g in gl].count(None) == 1)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
