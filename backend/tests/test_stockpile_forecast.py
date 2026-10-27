"""
27 Oct 2026 — stockpile balances that run FORWARD (branch `claude/stockpile-forecast`; the plan
notes/stockpile-forecast-plan-1027.md, John's decisions D0–D12 and the mockup's Q1–Q7, all taken 27 Oct).

Run from the repo root:  python backend/tests/test_stockpile_forecast.py

What this proves, on a scratch SQLite database (FastAPI stubbed, so the endpoint bodies run as plain functions):
  1. the schema: `stockpile_plan` (tenanted, in the package, in the empty check) and `stockpile_weeks.measured_qty`.
  2. typing the plan and the count: one month, a from–to range, a clear, refusals (negative, a place that cannot hold
     stock, a week the month lacks), the pile's own unit.
  3. the forward balance (stockpiles.balances): every In / Out case — recorded, not recorded (the plan stands in, D2),
     a typed Out is everything that left (D3), a typed 0 is 0, a forecast week, an edited week row, the month's 4 / 5
     week split, Pending and Rejected lines left out, road lines OUT of a pile, the unit conversion; the stock count
     resets the balance and reports the adjustment; planned use stops at empty and the shortfall is `empty` (decided
     27 Oct; less than one unit is rounding); first over / first empty / peak / the 8 weeks ahead; a place with no
     capacity and no plan keeps the records-only rule (D8), a capacity-only pile runs forward but is not "use planned".
  4. the rail: STOCKPILE_OVER on the forecast, STOCKPILE_SOON (over or runs out within 8 weeks), STOCKPILE_EMPTY, their
     sentences (no ids, UK words), none of the two new ones for a pile with no plan; the codes and the sheet's words.
  5. the Account rows (lookahead.account_stock): the plan figures and the 8 weeks ahead.
  6. the endpoints: planners and admins type (D6), a team login and nobody are refused; the public timeline caps a pile
     over capacity at "full" for the public and shows it to staff only (D9 a + i); `basis` per month.
  7. the package round trip carries the plan; one balance read is a FIXED number of queries (the 21 Oct lesson).

What it does not prove: the screens (parse_frontend.js / dom_frontend.js / parse_map.js), the demo's own figures
(test_demo_programme.py), Postgres (the ALTER IF NOT EXISTS branch is not run here).
"""
import datetime
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


# --------------------------------------------------------------------------- the FastAPI stub (as test_teams.py)
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


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Client:
    host = "203.0.113.50"


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})
        self.client = _Client()


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
    def __init__(self, content=None, status_code=200, headers=None, media_type=None, background=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type
        self.background = background

    def set_cookie(self, **kw):
        pass

    def delete_cookie(self, key, **kw):
        pass


class _JSONResponse(_Response):
    pass


_resp.Response = _Response
_resp.JSONResponse = _JSONResponse
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)
_st = types.ModuleType("starlette")
_stbg = types.ModuleType("starlette.background")


class _BackgroundTask:
    def __init__(self, fn, *a, **k):
        self.fn, self.a, self.k = fn, a, k


_stbg.BackgroundTask = _BackgroundTask
_st.background = _stbg
sys.modules.setdefault("starlette", _st)
sys.modules.setdefault("starlette.background", _stbg)

TMP = tempfile.mkdtemp(prefix="wayscope_stockfc_")
from portable import remove_scratch_db, pin_today   # noqa: E402  tests/portable.py
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "MAP_GATE", "IPT1_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-for-tests", "MAP_PASSWORD": "map-pass-abc",
                   "GATE_SECRET": "gate-secret-for-tests", "WAYSCOPE_WARM_CACHE": "0"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import access  # noqa: E402
import clashes  # noqa: E402
import config  # noqa: E402
import conversions  # noqa: E402
import export  # noqa: E402
import lookahead  # noqa: E402
import network  # noqa: E402
import read_cache  # noqa: E402
import stockpiles  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import weeks  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def status_of(fn):
    try:
        fn()
    except _HTTPException as e:
        return e.status_code
    return 200


T = db.current_tenant
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)

ADMIN = {"role": "admin", "ipt": None, "label": "Admin", "via": "login", "user_id": "u-a", "name": "Ada Admin",
         "email": "ada@example.org", "kind": "staff"}
PLANNER = {"role": "planner", "ipt": None, "label": "Planner", "via": "login", "user_id": "u-p", "name": "Pat Plan",
           "email": "pat@example.org", "kind": "staff"}
TEAM = {"role": "ipt", "ipt": "IPT1", "label": "North Team", "via": "login", "user_id": "u-n", "name": "Nia North",
        "email": "nia@example.org", "kind": "staff"}


def as_(acc):
    return access._ACCESS.set(acc)


# The calendar: October 2026 owns five weeks (28 Sep, 5, 12, 19, 26 Oct), November four (2, 9, 16, 23 Nov).
# "Today" is Wed 14 Oct 2026: the current week is October week 3, so weeks 1 and 2 are PAST.
TODAY = datetime.date(2026, 10, 14)
OCT, NOV, DEC = 10, 11, 12
ok("the calendar this harness reads: October has 5 weeks, November 4, today is October week 3",
   weeks.weeks_in_month(OCT) == 5 and weeks.weeks_in_month(NOV) == 4 and weeks.editable_week(today=TODAY) == (OCT, 3))

# =========================================================================== #
#  1. the schema                                                               #
# =========================================================================== #
cols = lambda t: {r[1] for r in db.get_conn().execute(f"PRAGMA table_info({t})").fetchall()}
ok("stockpile_plan exists with its columns",
   {"tenant_id", "location_id", "month_index", "planned_qty", "unit", "note", "updated_by", "updated_at"} <= cols("stockpile_plan"))
ok("stockpile_weeks gains measured_qty (the stock count)", "measured_qty" in cols("stockpile_weeks"))
ok("🔴 stockpile_plan is tenanted, registered in the same edit", "stockpile_plan" in db.TENANTED_TABLES
   and db._TENANT_PK["stockpile_plan"] == "(tenant_id, location_id, month_index)")
ok("🔴 measured_qty is in the stockpile_weeks DDL, not only ALTERed (the SQLite rebuild keeps the DDL's columns)",
   "measured_qty REAL" in db._TENANT_DDL["stockpile_weeks"])
ok("the tenant package carries stockpile_plan, after the locations it names", "stockpile_plan" in tenant_package.ORDER
   and tenant_package.ORDER.index("stockpile_plan") > tenant_package.ORDER.index("locations"))
ok("...and an organisation with only a plan is not 'empty'", "stockpile_plan" in tenant_package.EMPTY_CHECK)

# =========================================================================== #
#  the scene                                                                   #
# =========================================================================== #
LOC = "INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?, ?)"
db.execute(LOC, (T(), "Q", "Kilby Pit", 52.5, -1.2, "Quarry"))
db.execute(LOC, (T(), "P", "Stockpile North", 52.7, -0.9, "Stockpile"))
db.execute(LOC, (T(), "P2", "Stockpile Tilton", 52.6, -0.9, "Stockpile"))
db.execute(LOC, (T(), "C", "Melton Compound", 52.7, -0.8, "Compound"))
db.execute(LOC, (T(), "U", "Unmeasured stockpile", 52.6, -0.8, "Stockpile"))
RT = "INSERT INTO routes (tenant_id, id, origin_id, dest_id) VALUES (?, ?, ?, ?)"
db.execute(RT, (T(), "R1", "Q", "P"))       # into the pile
db.execute(RT, (T(), "R2", "Q", "C"))       # into the compound (records only)
db.execute(RT, (T(), "R3", "P", "C"))       # a road haul OUT of the pile
db.execute(RT, (T(), "R4", "Q", "U"))       # into a pile with no capacity
stockpiles.set_capacity("P", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)
stockpiles.set_capacity("P2", capacity_qty=500.0, capacity_unit="t", opening_qty=100.0)
FC = ("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, material_type, "
      "vehicle_type, submitted_by, status, ipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
_n = [0]


def line(route, month, qty, disc="earthworks", sect="WS1", status="Approved", unit="t", mat="Earthworks / soil"):
    _n[0] += 1
    db.execute(FC, (T(), f"F{_n[0]}", route, month, disc, sect, qty, unit, mat, "Tipper (44t)", "test", status, "IPT1"))


for m in (OCT, NOV):
    line("R1", m, 400.0)                     # 80 a week in October, 100 a week in November
    line("R2", m, 400.0)
    line("R4", m, 400.0)
line("R1", OCT, 9999.0, disc="substructure", status="Pending")     # never counts
line("R1", OCT, 8888.0, disc="superstructure", status="Rejected")  # never counts
line("R3", NOV, 40.0)                        # 10 a week out of the pile by road in November
for r in ("R1", "R2", "R3", "R4"):
    weeks.materialise_line(r, "earthworks", "WS1")


def bal(lid, frm=1, to=NOV, today=TODAY):
    return [s for s in stockpiles.balances(frm, to, today=today)["stockpiles"] if s["location_id"] == lid][0]


def wk(sp, m, w):
    return [r for r in sp["weeks"] if (r["month_index"], r["week_index"]) == (m, w)][0]


# =========================================================================== #
#  2. typing the plan and the count                                            #
# =========================================================================== #
r = stockpiles.set_plan("P", OCT, NOV, planned_qty=50.0, by="Pat Plan")
ok("planned use: the same figure for every month from–to", r.get("from_month") == OCT and r.get("to_month") == NOV
   and stockpiles.plan_rows("P") == {("P", OCT): 50.0, ("P", NOV): 50.0}, str(r))
ok("...in the pile's own unit", r.get("unit") == "t")
stockpiles.set_plan("P", DEC, planned_qty=7.0)
ok("one month on its own", stockpiles.plan_rows("P").get(("P", DEC)) == 7.0)
stockpiles.set_plan("P", DEC, planned_qty=None)
ok("🔴 None CLEARS a month (no plan is not a plan of 0)", ("P", DEC) not in stockpiles.plan_rows("P"))
ok("a range typed backwards is put the right way round", stockpiles.set_plan("P", NOV, OCT, planned_qty=50.0)["from_month"] == OCT)
ok("🔴 planned use below zero is refused", "error" in stockpiles.set_plan("P", OCT, planned_qty=-1))
ok("🔴 a place that cannot hold stock is refused", "error" in stockpiles.set_plan("Q", OCT, planned_qty=10))
ok("...and so is one that does not exist", "error" in stockpiles.set_plan("NOPE", OCT, planned_qty=10))
ok("the refusals are sentences, no ids", stockpiles.set_plan("Q", OCT, planned_qty=10)["error"] == "That place cannot hold stock.")
ok("🔴 a stock count in a week the month lacks is refused", "error" in stockpiles.set_count("P", NOV, 5, 10))
ok("🔴 a stock count below zero is refused", "error" in stockpiles.set_count("P", OCT, 1, -5))

# =========================================================================== #
#  3. the forward balance                                                      #
# =========================================================================== #
sp = bal("P")
ok("a pile with a capacity and a plan runs forward", sp["forecast"] is True and sp["use_planned"] is True)
w1 = wk(sp, OCT, 1)
ok("🔴 D2: a PAST week nobody recorded uses the plan (80 t), it is not 0 any more",
   w1["inbound"] == 80.0 and w1["in_basis"] == "plan", str(w1))
ok("...counted as 'not recorded' (the line, and the Out nobody typed)", w1["not_recorded"] == 2, str(w1["not_recorded"]))
ok("...and the week's basis says so", w1["basis"] == "plan")
ok("planned use is the month over its weeks: 50 / 5 = 10 t in October", w1["plan_out"] == 10.0 and w1["consumed"] == 10.0)
ok("balance = opening + In − Out", w1["balance_end"] == 70.0, str(w1["balance_end"]))
ok("nothing recorded coming in: in_recorded is None, not 0", w1["in_recorded"] is None)

weeks.set_actual("R1", OCT, "earthworks", "WS1", 2, actual_qty=60.0, by="clerk")
sp = bal("P")
w2 = wk(sp, OCT, 2)
ok("a recorded actual replaces the plan for its line", w2["inbound"] == 60.0 and w2["in_basis"] == "recorded"
   and w2["in_recorded"] == 60.0 and w2["plan_in"] == 80.0, str(w2))
ok("...the Out nobody typed is still the plan: the week is 'part'", w2["out_basis"] == "plan" and w2["basis"] == "part")
stockpiles.consume("P", OCT, 2, consumed_qty=5.0, unit="t", by="clerk")
w2 = wk(bal("P"), OCT, 2)
ok("🔴 D3: a typed Out is everything that left — the plan's 10 t is not added", w2["consumed"] == 5.0
   and w2["out_basis"] == "recorded" and w2["basis"] == "recorded", str(w2))
stockpiles.consume("P", OCT, 2, consumed_qty=0.0, unit="t", by="clerk")
w2 = wk(bal("P"), OCT, 2)
ok("a typed 0 is 0, not 'not typed'", w2["consumed"] == 0.0 and w2["out_basis"] == "recorded")
ok("...and the balance follows: 70 + 60 − 0", w2["balance_end"] == 130.0, str(w2["balance_end"]))

sp = bal("P")
w3 = wk(sp, OCT, 3)
ok("the CURRENT week is a forecast week: the plan, labelled forecast", w3["basis"] == "forecast"
   and w3["inbound"] == 80.0 and w3["in_basis"] == "forecast" and w3["consumed"] == 10.0, str(w3))
ok("...and it does not count as 'not recorded'", w3["not_recorded"] == 0)
weeks.set_week("R1", OCT, "earthworks", "WS1", 4, planned_qty=200.0, by="planner")
w4 = wk(bal("P"), OCT, 4)
ok("an EDITED week row is what the forecast uses (as the Look-ahead shows it)", w4["inbound"] == 200.0, str(w4["inbound"]))
n1 = wk(bal("P"), NOV, 1)
ok("November's week: 400 / 4 = 100 t in", n1["inbound"] == 100.0)
ok("🔴 Pending and Rejected lines never count (9 999 t and 8 888 t left out)", all(r["inbound"] < 9000 for r in bal("P")["weeks"]))
ok("a road line OUT of the pile adds to its Out: 50/4 + 40/4 = 22.5 t", n1["consumed"] == 22.5 and n1["plan_out"] == 22.5, str(n1))

# the stock count
stockpiles.set_count("P", OCT, 2, measured_qty=500.0, by="engineer")
sp = bal("P")
w2 = wk(sp, OCT, 2)
ok("D5: a stock count replaces the worked-out balance at its week's end", w2["balance_end"] == 500.0 and w2["count"] == 500.0)
ok("...the difference is the count adjustment (500 − 130)", w2["count_adjust"] == 370.0, str(w2["count_adjust"]))
ok("...and the weeks after run on from the count", wk(sp, OCT, 3)["balance_end"] == 570.0, str(wk(sp, OCT, 3)["balance_end"]))
ok("a week without a count has count None", wk(sp, OCT, 3)["count"] is None and wk(sp, OCT, 3)["count_adjust"] is None)
stockpiles.set_count("P", OCT, 2, measured_qty=None)
ok("a count can be cleared", wk(bal("P"), OCT, 2)["count"] is None and wk(bal("P"), OCT, 2)["balance_end"] == 130.0)

# over, first over, peak, 8 weeks ahead
stockpiles.set_capacity("P", capacity_qty=300.0, capacity_unit="t", opening_qty=0.0)
sp = bal("P")
ok("the forecast goes over a capacity: `over` on that week", wk(sp, OCT, 4)["over"] is True, str(wk(sp, OCT, 4)))
ok("first_over is the first FUTURE week over (October week 4)",
   sp["first_over"] and (sp["first_over"]["month_index"], sp["first_over"]["week_index"]) == (OCT, 4), str(sp["first_over"]))
ok("...and it is within the 8 weeks ahead (soon_over)", sp["soon_over"] == sp["first_over"])
ok("the peak is the fullest future week, with its %", sp["peak"]["balance_end"] == max(r["balance_end"] for r in sp["weeks"]
                                                                                       if (r["month_index"], r["week_index"]) >= (OCT, 3))
   and sp["peak_pct"] == round(sp["peak"]["balance_end"] * 100 / 300.0, 1))
ok("🔴 remaining goes negative over capacity rather than clamping (staff read the real figure)", wk(sp, OCT, 4)["remaining"] < 0)
sp_late = bal("P", today=datetime.date(2026, 11, 25))
ok("📅 'today' moves the window: on 25 Nov October is all past (plan stands in), nothing ahead in October",
   wk(sp_late, OCT, 4)["basis"] != "forecast" and all(r["basis"] != "forecast" for r in sp_late["weeks"] if r["month_index"] == OCT))

# planned use stops at empty (decided 27 Oct)
stockpiles.set_plan("P2", OCT, NOV, planned_qty=1000.0)      # 200 a week out of a 100 t pile, nothing coming in
sp2 = bal("P2")
o1 = wk(sp2, OCT, 1)
ok("🔴 planned use never takes more than the pile holds: 100 t out, not 200", o1["consumed"] == 100.0
   and o1["balance_end"] == 0.0, str(o1))
ok("...the shortfall is reported and the week is EMPTY", o1["short"] == 100.0 and o1["empty"] is True)
ok("...the balance never goes below zero from the plan", all(r["balance_end"] >= 0 for r in sp2["weeks"]))
ok("first_empty / soon_empty name the first future week that runs out",
   sp2["first_empty"] and (sp2["first_empty"]["month_index"], sp2["first_empty"]["week_index"]) == (OCT, 3)
   and sp2["soon_empty"] == sp2["first_empty"], str(sp2["first_empty"]))
stockpiles.set_capacity("P2", capacity_qty=500.0, capacity_unit="t", opening_qty=100.4)
stockpiles.set_plan("P2", OCT, OCT, planned_qty=502.0)     # 100.4 a week: 0.4 t short the first week is rounding
o1 = wk(bal("P2"), OCT, 1)
ok("🔴 less than one unit short is rounding, not 'runs out' (EMPTY_MIN)", o1["short"] < 1 and o1["empty"] is False
   and stockpiles.EMPTY_MIN == 1.0, str(o1))
stockpiles.set_plan("P2", OCT, NOV, planned_qty=None)
stockpiles.set_capacity("P2", capacity_qty=500.0, capacity_unit="t", opening_qty=100.0)

# D8: who gets a forecast
c = bal("C")
cw1 = wk(c, OCT, 1)
ok("🔴 D8: a compound with no capacity and no plan keeps the RECORDS-ONLY rule: an unrecorded week is 0 in",
   c["forecast"] is False and cw1["inbound"] == 0.0 and cw1["basis"] == "recorded", str(cw1))
weeks.set_actual("R2", OCT, "earthworks", "WS1", 1, actual_qty=33.0, by="clerk")
ok("...a recorded actual still counts", wk(bal("C"), OCT, 1)["inbound"] == 33.0)
ok("...a road haul out of a pile into it is NOT added from the plan", wk(bal("C"), NOV, 1)["inbound"] == 0.0)
ok("...and it carries none of the forecast fields", "first_over" not in c and "plan_in" not in cw1)
u = bal("U")
ok("a pile with no capacity and no plan: records only, never over", u["forecast"] is False and not any(r["over"] for r in u["weeks"]))
stockpiles.set_plan("U", OCT, planned_qty=0.0)
u = bal("U")
ok("a planned use (even 0) with no capacity: it runs forward, remaining unknown, never over", u["forecast"] is True
   and all(r["remaining"] is None and r["over"] is False for r in u["weeks"]))
stockpiles.set_plan("U", OCT, planned_qty=None)
ok("a capacity with NO plan runs forward but is not 'use planned' (no STOCKPILE SOON for it)",
   bal("P2")["forecast"] is True and bal("P2")["use_planned"] is False)

# m³ into a tonnes pile is converted on the forecast too
line("R1", DEC, 100.0, unit="m3", mat="Small aggregate")
weeks.materialise_line("R1", "earthworks", "WS1", month_index=DEC)
d1 = wk(bal("P", to=DEC), DEC, 1)
_dens = conversions.load_factors()["material_categories"]["Small aggregate"]["density_t_per_m3"]
ok("🔴 an m³ line forecast into a tonnes pile is CONVERTED (density from factors.json)",
   abs(d1["plan_in"] - 100.0 / weeks.weeks_in_month(DEC) * _dens) < 1e-3, str(d1["plan_in"]))

# the read's cost: a fixed number of queries
_calls = [0]
_real_query = db.query


def _counting(*a, **k):
    _calls[0] += 1
    return _real_query(*a, **k)


db.query = _counting
stockpiles.balances(1, NOV, today=TODAY)
n_all = _calls[0]
_calls[0] = 0
stockpiles.balances(1, 24, today=TODAY)
n_long = _calls[0]
db.query = _real_query
ok("🔴 one balance read is a FIXED number of queries, not one per pile or per week", n_all == n_long and n_all <= 10,
   f"{n_all} vs {n_long}")

# =========================================================================== #
#  4. the rail                                                                 #
# =========================================================================== #
ok("the codes: STOCKPILE_EMPTY and STOCKPILE_SOON are rail codes", {"STOCKPILE_EMPTY", "STOCKPILE_SOON"} <= set(clashes.CODES))
ok("the sheet's and the rail's words", export.FLAG_LABEL["STOCKPILE_SOON"] == "STOCKPILE SOON"
   and export.DAY_FLAG_WORD["STOCKPILE_EMPTY"] == "STOCKPILE EMPTY" and len(export.DAY_FLAG_WORD["STOCKPILE_EMPTY"]) <= 15)
ok("...ranked with the warnings on the Day sheet", "STOCKPILE_SOON" in export.DAY_FLAG_RANK
   and export.DAY_FLAG_RANK.index("STOCKPILE_SOON") > export.DAY_FLAG_RANK.index("STOCKPILE_OVER"))

_pin = pin_today(TODAY)
LINE_P = {"route_id": "R1", "month_index": OCT, "discipline": "earthworks", "section_id": "WS1", "ipt": "IPT1",
          "context": {"dest_id": "P"}}
LINE_P2 = dict(LINE_P, route_id="R9", context={"dest_id": "P2"})
stock = clashes.stock_forecast([], OCT, 3)
s_p = [s for s in stock if s["location_id"] == "P"][0]
ok("stock_forecast reads the commit week off the forward balance", s_p["forecast"] == wk(bal("P"), OCT, 3)["balance_end"]
   and s_p["opening"] == wk(bal("P"), OCT, 2)["balance_end"], str(s_p))
f_over = clashes.stockpile_over([LINE_P], [dict(s_p, over=True, over_by=26.0, forecast=326.0)])
ok("🔴 STOCKPILE_OVER: the sentence names the pile, the forecast, how far over and the capacity — no id",
   f_over and f_over[0]["text"] == "Stockpile North: 326 t forecast at the week's end, 26 t over its 300 t."
   and "P" not in f_over[0]["text"].split(), str(f_over))
stockpiles.set_capacity("P", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)
stockpiles.set_capacity("P2", capacity_qty=500.0, capacity_unit="t", opening_qty=100.0)
stock = clashes.stock_forecast([], OCT, 3)
s_p = [s for s in stock if s["location_id"] == "P"][0]
ok("a pile well under its capacity raises nothing", not clashes.stockpile_over([LINE_P], stock)
   and not clashes.stockpile_soon([LINE_P], stock), str(s_p))
stockpiles.set_capacity("P", capacity_qty=450.0, capacity_unit="t", opening_qty=0.0)
stock = clashes.stock_forecast([], OCT, 3)
soon = clashes.stockpile_soon([LINE_P], stock)
s_p = [s for s in stock if s["location_id"] == "P"][0]
ok("🔴 STOCKPILE_SOON: a pile that goes over within 8 weeks", soon and soon[0]["code"] == "STOCKPILE_SOON"
   and soon[0]["kind"] == "over", str(soon) + str(s_p))
_so = s_p["soon_over"]
_mon = weeks.week_span(_so["month_index"], _so["week_index"])[0]
ok("...'goes over 450 t in the week of <Monday> (forecast N t)' — UK date words, whole tonnes, spaces in thousands",
   soon and soon[0]["text"] == f"Stockpile North goes over 450 t in the week of {_mon.day} {_mon.strftime('%b')} "
                               f"(forecast {clashes._qty(_so['balance_end'])} t).", soon[0]["text"] if soon else "")
ok("...only on lines into that pile", not clashes.stockpile_soon([LINE_P2], stock))
ok("🔴 no STOCKPILE_SOON for a pile with NO planned use", not [s for s in stock if s["location_id"] == "P2"][0]["use_planned"]
   and not clashes.stockpile_soon([LINE_P2], [dict(s, soon_over={"month_index": NOV, "week_index": 1, "balance_end": 9e9})
                                              for s in stock if s["location_id"] == "P2"]))
stockpiles.set_capacity("P", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)
stockpiles.set_plan("P2", OCT, NOV, planned_qty=2000.0)
stock = clashes.stock_forecast([], OCT, 3)
emp = clashes.stockpile_soon([LINE_P2], stock)
ok("🔴 STOCKPILE_EMPTY: the planned use this week is more than the pile holds", emp and emp[0]["code"] == "STOCKPILE_EMPTY",
   str(emp))
ok("...'runs out this week: N t planned use, N t in stock. Bring deliveries forward.'",
   emp and emp[0]["text"].startswith("Stockpile Tilton runs out this week: ")
   and emp[0]["text"].endswith("t in stock. Bring deliveries forward."), emp[0]["text"] if emp else "")
stockpiles.set_plan("P2", OCT, NOV, planned_qty=None)

# =========================================================================== #
#  5. the Account rows                                                         #
# =========================================================================== #
acc = {r["location_id"]: r for r in lookahead.account_stock(OCT, 2)}
ok("the Account row of a forecast pile carries the plan figures", acc["P"]["forecast"] is True
   and acc["P"]["plan_in"] == 80.0 and acc["P"]["plan_out"] == 10.0, str(acc["P"]))
ok("...what was RECORDED coming in, apart from what the balance used", acc["P"]["inbound_recorded"] == 60.0)
ok("...and the 8 weeks ahead: 'fine' with the fullest it gets", acc["P"]["next"]["kind"] == "fine"
   and acc["P"]["next"]["peak_pct"] is not None, str(acc["P"]["next"]))
ok("a records-only place has no plan figures and no 'next'", acc["C"]["forecast"] is False and acc["C"]["next"] is None
   and acc["C"]["plan_in"] is None)
stockpiles.set_capacity("P", capacity_qty=450.0, capacity_unit="t", opening_qty=0.0)
acc = {r["location_id"]: r for r in lookahead.account_stock(OCT, 2)}
ok("...'over' with the week it goes over", acc["P"]["next"]["kind"] == "over" and acc["P"]["next"]["week_from"])
stockpiles.set_capacity("P", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)

# =========================================================================== #
#  6. the endpoints                                                            #
# =========================================================================== #
ok("nobody signed in: the plan is refused (401)", status_of(lambda: main.put_stockpile_plan(
    main.StockPlanIn(location_id="P", from_month=OCT, planned_qty=5))) == 401)
_t = as_(TEAM)
ok("🔴 D6: a team login cannot type the plan (403)", status_of(lambda: main.put_stockpile_plan(
    main.StockPlanIn(location_id="P", from_month=OCT, planned_qty=5))) == 403)
ok("...nor a stock count", status_of(lambda: main.put_stockpile_count(
    main.StockCountIn(location_id="P", month_index=OCT, week_index=1, measured_qty=5))) == 403)
ok("...but reads the plan", "P" in main.stockpile_plan()["plans"])
access._ACCESS.reset(_t)
_t = as_(PLANNER)
r = main.put_stockpile_plan(main.StockPlanIn(location_id="P", from_month=OCT, to_month=NOV, planned_qty=60))
ok("a planner types the plan", r["planned_qty"] == 60.0 and stockpiles.plan_rows("P")[("P", NOV)] == 60.0)
ok("...a month outside the programme is refused", status_of(lambda: main.put_stockpile_plan(
    main.StockPlanIn(location_id="P", from_month=0, planned_qty=5))) == 400)
ok("...and a place that cannot hold stock (400, a sentence)", status_of(lambda: main.put_stockpile_plan(
    main.StockPlanIn(location_id="Q", from_month=OCT, planned_qty=5))) == 400)
r = main.put_stockpile_count(main.StockCountIn(location_id="P", month_index=OCT, week_index=1, measured_qty=55))
ok("a planner types a count", r["measured_qty"] == 55.0)
main.put_stockpile_count(main.StockCountIn(location_id="P", month_index=OCT, week_index=1, measured_qty=None))
ok("GET /api/stockpiles/plan: plans by pile and month", main.stockpile_plan(location_id="P")["plans"]["P"][str(OCT)] == 60.0)
ok("GET /api/stockpiles says how far ahead it looks", main.list_stockpiles(from_month=OCT, to_month=OCT)["ahead_weeks"] == 8)
access._ACCESS.reset(_t)
_t = as_(ADMIN)
ok("an admin types the plan too", status_of(lambda: main.put_stockpile_plan(
    main.StockPlanIn(location_id="P", from_month=OCT, planned_qty=60))) == 200)
access._ACCESS.reset(_t)

# the public timeline (D9 a + i)
stockpiles.set_capacity("P", capacity_qty=300.0, capacity_unit="t", opening_qty=0.0)
pub = main.public_stockpile_timeline(1, NOV, request=_Request())
pp = [s for s in pub["stockpiles"] if s["location_id"] == "P"][0]
ok("🔴 D9 (a + i): the PUBLIC never reads a pile over capacity: capped at the capacity, over False, 'full' True",
   pub["staff"] is False and pp["months"][str(NOV)]["balance_end"] == 300.0 and pp["months"][str(NOV)]["over"] is False
   and pp["months"][str(NOV)]["full"] is True, str(pp["months"].get(str(NOV))))
ok("...and no 'remaining' below zero", pp["months"][str(NOV)]["remaining"] == 0.0)
ok("future months are the forecast, past ones recorded (or part)", pp["months"][str(NOV)]["basis"] == "forecast"
   and pp["months"]["9"]["basis"] in ("recorded", "part"), str({k: v["basis"] for k, v in pp["months"].items()}))
_t = as_(PLANNER)
stf = main.public_stockpile_timeline(1, NOV, request=_Request())
sp_ = [s for s in stf["stockpiles"] if s["location_id"] == "P"][0]
ok("🔴 ...a signed-in STAFF caller reads the real figure and `over`", stf["staff"] is True
   and sp_["months"][str(NOV)]["over"] is True and sp_["months"][str(NOV)]["balance_end"] > 300.0, str(sp_["months"][str(NOV)]))
access._ACCESS.reset(_t)
ok("the timeline is worked out once per data version (read_cache)", read_cache.peek(main.STOCK_TIMELINE_CACHE,
   (main.MONTH_COUNT, TODAY.isoformat())) is not None)
stockpiles.set_capacity("P", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)

# =========================================================================== #
#  7. the package round trip                                                   #
# =========================================================================== #
pkg = tenant_package.export_tenant(app_version="test")
_rows = pkg["tables"]["stockpile_plan"] if "tables" in pkg else pkg["stockpile_plan"]
ok("the export carries the plan rows", any(r["location_id"] == "P" and r["planned_qty"] == 60.0 for r in _rows), str(_rows)[:200])
res = tenant_package.import_tenant(pkg, replace=True)
ok("...and an import brings them back", res.get("ok") is True and stockpiles.plan_rows("P").get(("P", OCT)) == 60.0, str(res)[:200])
ok("...the stock count column comes back too (measured_qty in the package's stockpile_weeks)",
   all("measured_qty" in r for r in (pkg["tables"]["stockpile_weeks"] if "tables" in pkg else pkg["stockpile_weeks"])))

print(f"\ntest_stockpile_forecast: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
