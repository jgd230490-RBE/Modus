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
# NARROWED 14 Oct 2026 (bundle G): five statements — location_visits() (the CLP section's chart 1b) adds two, each tenanted
ok("🔴 tenant isolation: the SQL literals in gate_arrivals.py constrain tenant_id",
   len(_stmts) == 5 and all("tenant_id = ?" in s for s in _stmts)
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
ok("working days and shift hours are the planning block's (22, 10) and open_minutes is 600.0",
   res["working_days"] == WD and res["shift_hours"] == SH and res["open_minutes"] == OPEN and res["month"] == 9 and res["scope"] == "scheme"
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
ok("the response carries every key of the contract on every gate",
   all(set(g) == {"gate_id", "gate_name", "location_id", "location_name", "loc_type", "role", "laden_per_day", "empty_per_day",
                  "arrivals_per_day", "gap_minutes", "gate_minutes", "capacity_per_day", "capacity_pct", "flag", "reason", "pending_lines", "pending_per_day",
                  "teams", "per_team", "origin_share_note", "fallthrough_routes",
                  "status_word", "open_minutes", "open_basis", "open_hours", "peak_minutes", "closed_days", "near_per_day"} for g in gl)
   and set(res) == {"month", "label", "working_days", "shift_hours", "open_minutes", "scope", "gates", "notes",
                    "near_pct", "peak_bands", "limit"})

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
   and m11["notes"] == ["No approved lines in Nov 2026.", "Averages only, if arrivals are spread evenly across the 10 h shift. No hourly peak is typed."],
   str(m11["notes"]))
m10 = gate_arrivals.arrivals(10, acc_planner, factors=factors, working_days=WD)
# NARROWED 11 Oct 2026 (review): month 10 now also carries the 44-vehicle line on R4 (laden at G004, empty at G003)
_m10b = {g["gate_id"]: g for g in m10["gates"]}
ok("a month with approved lines but no pending line carries no pending note; the vehicles line counts 44 trips: G004 laden 2.0, G003 empty 2.0",
   len(m10["gates"]) == 3 and m10["notes"] == ["Averages only, if arrivals are spread evenly across the 10 h shift. No hourly peak is typed."]
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
ok("the endpoint: main.gate_arrivals_month(9) returns the same dict as gate_arrivals.arrivals(9, acc, …)", ep == res)
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
   [b.get("error") for b in _bad] == ["type both open hours (from and to), or clear both to use the scheme's shift",
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
ok("a gate with no hours typed keeps the scheme's shift (600 min, basis 'shift', no closed days)",
   _r8["G001"]["open_minutes"] == 600.0 and _r8["G001"]["open_basis"] == "shift" and _r8["G001"]["closed_days"] is None)
_fpk = _copy.deepcopy(factors)
_fpk["planning"]["peak_bands"] = [{"from": "07:00", "to": "08:00"}, {"from": "16:00", "to": "19:00"}]
_rp = gate_arrivals.arrivals(9, acc_planner, factors=_fpk, working_days=WD)
_rpg = {g["gate_id"]: g for g in _rp["gates"]}
ok("⭐ the peak bands are taken off the gate's open hours: 07:00-15:00 less 07:00-08:00 = 420 min (16:00-19:00 is outside), capacity 140.0",
   _rpg["G003"]["open_minutes"] == 420.0 and _rpg["G003"]["peak_minutes"] == 60.0 and _rpg["G003"]["capacity_per_day"] == 140.0,
   str(_rpg.get("G003"))[:300])
ok("...and a gate on the scheme's shift keeps 600 min, with ONE note that the bands could not be taken off it; the bands ride on the response",
   _rpg["G001"]["open_minutes"] == 600.0 and _rp["peak_bands"] == _fpk["planning"]["peak_bands"]
   and sum(1 for n in _rp["notes"] if n.startswith("The peak bands (07:00–08:00 and 16:00–19:00, no deliveries) are taken off only")) == 1
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
ok("clearing the hours puts both gates back on the scheme's shift (blank and None both clear)",
   _rr.get("open_from") is None and _rr.get("open_to") is None and _rr.get("open_days") is None
   and _r3.get("open_from") is None and _r3.get("open_days") is None
   and {g["gate_id"]: g["open_basis"] for g in gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)["gates"]}.get("G003") == "shift")
_cg = gates.create_gate("L3", "Night gate", 58.702, 24.202, direction="access", safety_minutes=2, open_from="22:00", open_to="06:00", open_days="1111111")
ok("a gate created with hours past midnight stores them; one created half-typed is refused",
   _cg.get("open_from") == "22:00" and _cg.get("open_days") == "1111111"
   and gates.create_gate("L3", "Bad", 58.7, 24.2, open_to="06:00").get("error", "").startswith("type both open hours"), str(_cg))
gates.update_gate(_cg["id"], active=False)

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
