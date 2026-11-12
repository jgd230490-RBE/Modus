"""
CLOCS idea C-I1 (11 Nov 2026, John's yes): backend/gate_arrivals.queue_months, db.select_memo and
GET /api/gates/queue-months — the months with a gate at the 85 % step or over, for the Dashboard's
"Next queue likely" line.

What is asserted: the months and gates are each month's own arrivals() flags (amber / red), in order; a
pending line and a gate with no check-in typed are never a queue; a team code gets the same totals and no
team figure; the memo answers the repeated reads once (far fewer statements, the same answer), hands
each caller its own copy, is on only inside its `with` and never in another thread; the endpoint is kept
until the next write and refuses no code.

WHAT THIS DOES NOT PROVE: Postgres (SQLite here) and live's timing; the panel's line (ui_fix_clocs_c_site_sim.js).

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests/Scripts/python backend/tests/test_clocs_c_queue.py
"""
import threading
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

TMP = tempfile.mkdtemp(prefix="rbe_clocs_c_queue_")
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
    assert config.save(_doc, by="test_clocs_c_queue")["ok"]
    config.invalidate()
    costing.invalidate()




# =========================================================================== #
#  The seed: a pit (no check-in typed: never compared) and a compound gate with a 3 min check-in on a 07:00–17:00 day  #
#  (600 min: capacity 200 lorries a day). Month 5 at 90 %, 9 at 25 %, 12 at 90 %, 15 at 120 %, 20 at 50 %.            #
# =========================================================================== #
reset_db()
access.set_current("planner123")
V8 = "Rigid 8-wheeler (32t)"          # payload_t 20 in factors.json
for _id, _name, _lt, _role, _lat, _lon in (("L1", "West pit", "Quarry", "origin", 58.5, 24.0),
                                           ("L2", "East compound", "Compound", "destination", 58.6, 24.4)):
    db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
               (_id, _name, _lt, _role, _lat, _lon))
_ga = gates.create_gate("L1", "Weighbridge", 58.501, 24.001, direction="both", safety_minutes=None, is_default=True)
_gb = gates.create_gate("L2", "Compound gate", 58.601, 24.401, direction="both", safety_minutes=3.0, is_default=True)
assert not _ga.get("error") and not _gb.get("error")
db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", ("R1", "L1", "L2", "IPT1"))
gates.set_route_gates("R1", origin_gate_id=_ga["id"], dest_gate_id=_gb["id"], origin_given=True, dest_given=True)


def _line(sect, month, per_day, status="Approved"):
    qty = per_day * 22 * 20.0                      # lorries a day x 22 working days x 20 t a load
    main.save_matrix_row(main.MatrixRow(
        route_id="R1", discipline="earthworks", section_id=sect, material_type="Small aggregate",
        material_description=None, vehicle_type=V8, submitted_by="tester", unit="t",
        status="Pending", cells=[main.Cell(month_index=month, quantity=qty)], ipt="IPT1"))
    if status != "Pending":
        main.set_route_status("R1", main.StatusUpdate(status=status), discipline="earthworks", section_id=sect)


_line("WS5", 5, 180)
_line("WS9", 9, 50)
_line("WS12", 12, 180)
_line("WS15", 15, 240)
_line("WS20", 20, 100)
_line("WS30", 30, 240, status="Pending")         # a pending line is never a figure, so never a queue

PLAN = {"role": "planner", "ipt": None, "label": "Planner"}
q = gate_arrivals.queue_months(PLAN, working_days=22)
ms = [m["month"] for m in q["months"]]
ok("⭐ C-I1: the months with a gate at 85 % or over are listed in order (5, 12, 15); 25 %, 50 % and a pending month are not",
   ms == [5, 12, 15] and q["near_pct"] == 85, str(ms))
by = {m["month"]: m for m in q["months"]}
ok("⭐ C-I1: each month's gate, flag and percentage are the panel's own (arrivals() for that month)",
   all([{k: g.get(k) for k in gate_arrivals.QUEUE_FIELDS} for g in gate_arrivals.arrivals(m, PLAN, working_days=22)["gates"]
        if g.get("flag") in ("red", "amber")] == by[m]["gates"] for m in ms)
   and [(by[m]["gates"][0]["capacity_pct"], by[m]["gates"][0]["flag"]) for m in ms] == [(90, "amber"), (90, "amber"), (120, "red")],
   str([(by[m]["gates"][0]["capacity_pct"], by[m]["gates"][0]["flag"]) for m in ms]))
ok("C-I1: only the compound's gate is named (the pit has no check-in typed: never compared, never a queue); labels are months",
   all(len(by[m]["gates"]) == 1 and by[m]["gates"][0]["location_name"] == "East compound" for m in ms)
   and by[5]["label"] == gate_arrivals.month_label(5) and set(by[5]["gates"][0]) == set(gate_arrivals.QUEUE_FIELDS))
ok("C-I1: month_count leaves out months past the horizon", [m["month"] for m in gate_arrivals.queue_months(PLAN, working_days=22, month_count=12)["months"]] == [5, 12])
_team = gate_arrivals.queue_months({"role": "ipt", "ipt": "IPT2", "label": "Team 2"}, working_days=22)
ok("C-I1: a team code gets the same months and gates (totals, like the panel) and never a team's figure",
   [m["month"] for m in _team["months"]] == ms and "per_team" not in json.dumps(_team) and "IPT" not in json.dumps(_team))

# ---- the select memo: the same answer, far fewer statements
_n = {"c": 0}
_orig_run = db._run


def _count_run(sql, params, fetch):
    _n["c"] += 1
    return _orig_run(sql, params, fetch)


db._run = _count_run
_n["c"] = 0
q_memo = gate_arrivals.queue_months(PLAN, working_days=22)
with_memo = _n["c"]
_n["c"] = 0
plain = {}
for _m in (5, 9, 12, 15, 20):
    plain[_m] = gate_arrivals.arrivals(_m, PLAN, working_days=22)
without_memo = _n["c"]
db._run = _orig_run
ok("⭐ C-I1: the five months' reads run in far fewer statements inside db.select_memo (repeated reads answered once)",
   0 < with_memo < without_memo / 2, f"{with_memo} vs {without_memo}")
ok("...and the answer is the same as reading each month on its own",
   [m["month"] for m in q_memo["months"]] == [m for m in (5, 9, 12, 15, 20) if any(g.get("flag") in ("red", "amber") for g in plain[m]["gates"])]
   and q_memo == q)
with db.select_memo():
    _r1 = db.query("SELECT id, name FROM locations WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
    _r1[0]["name"] = "changed by a caller"
    _r2 = db.query("SELECT id, name FROM locations WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
    _inside = db._SELECT_MEMO.get() is not None
    _seen = {}
    _t = threading.Thread(target=lambda: _seen.setdefault("memo", db._SELECT_MEMO.get()))
    _t.start(); _t.join()
ok("⭐ select_memo: each caller gets its own copy (a caller changing a row never changes the next answer)",
   _r2[0]["name"] == "West pit" and _r1 is not _r2)
ok("select_memo: on inside the `with` only, and never in another thread (another request)",
   _inside and db._SELECT_MEMO.get() is None and _seen.get("memo") is None)
_before = db.query("SELECT name FROM locations WHERE id = ?", ("L2",))[0]["name"]
db.execute("UPDATE locations SET name = ? WHERE id = ?", ("East compound 2", "L2"))
ok("select_memo: outside it, a read after a write sees the write", db.query("SELECT name FROM locations WHERE id = ?", ("L2",))[0]["name"] == "East compound 2"
   and _before == "East compound")
db.execute("UPDATE locations SET name = ? WHERE id = ?", ("East compound", "L2"))

# ---- the endpoint
ep = main.gate_queue_months()
ok("⭐ GET /api/gates/queue-months answers the same months for a planner", [m["month"] for m in ep["months"]] == ms, str(ep)[:200])
_tok = access.set_current(None)
e401 = _raises(lambda: main.gate_queue_months())
access.set_current("planner123")
ok("no code -> 401", getattr(e401, "status_code", None) == 401)
main_code = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
_ep_body = main_code.split("def gate_queue_months(", 1)[1].split("\n@app.", 1)[0]
ok("the endpoint is kept until the next write (_staff_json), reads the working days through main._working_days, needs any code",
   '_staff_json("gates/queue-months", {}, build, acc)' in _ep_body and "_working_days(factors)" in _ep_body
   and "_require_access()" in _ep_body and '@app.get("/api/gates/queue-months")' in main_code)
ok("🔴 it sits after the Gate arrivals endpoint's helper (that endpoint's body, read up to the next route, stays whole)",
   main_code.index("def _gate_arrivals_build(") < main_code.index('@app.get("/api/gates/queue-months")') < main_code.index('@app.get("/api/sim/day")'))
_qm_src = open(os.path.join(BACKEND, "gate_arrivals.py"), encoding="utf-8").read().split("def queue_months(", 1)[1].split("\ndef ", 1)[0]
ok("queue_months reads only (no write) and binds the tenant to a name holding 'tenant'",
   "db.execute" not in _qm_src and "tenant_id = db.current_tenant()" in _qm_src and "(tenant_id,)" in _qm_src
   and "with db.select_memo():" in _qm_src)

remove_scratch_db(db, TMP)
print("\n".join("  FAIL: " + f for f in FAIL))
print(f"test_clocs_c_queue.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
