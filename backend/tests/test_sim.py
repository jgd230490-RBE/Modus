"""
The haulage simulation, 16 Oct 2026 (S3) — backend/sim.py, GET /api/sim/day and the Gate arrivals panel's busiest hour.

THE SPEC is the example the user approved on 16 Oct (notes/sim-example-1016/, not in git). This harness rebuilds the live
demo's shape of Sep 2026 — the 18 routes R001–R018, the 14 gates with the check-in minutes typed on the demo, the 18
approved lines (tonnes, vehicle, team), each route's HERE line as the public map served it on 16 Oct and the two haul
roads (fixtures/sim_demo_sep2026.json) — and asserts that the engine gives the example's day:

  * 312 loads (6,860 trips ÷ 22 days), the same whole loads per line, 646 gate arrivals with the example pour, every
    gate within 0.6 of the Dashboard's Sep 2026 figure, the playback 05:30–17:30;
  * the pour (Harborough Compound, 10:00, 160 m³, 7.5 m³ a load, 60 m³ an hour): 22 mixers, 101 arrivals, 84 %, the
    first wait at 10:00, up to 12 waiting at 12:38, 1,776 lorry-minutes lost, the longest wait 56 min;
  * pour off: no lorry waits anywhere (an even spread under 100 % never queues);
  * the example bands on 07:00–17:00, pour off: Kilby Ridge 119 %, Brook Pit 109 %, Harborough 110 %, all red;
  * the review's edge cases (a boundary minute, late check-ins with no queue, a window past midnight refused, the red
    rule on the displayed gap) and D85 (the bottleneck is the first wait longer than the check-in).

17 Oct 2026: the example's gates were open 07:00–17:00 (the lorry shift stood in at 07:00). The default gate hours are
now 08:00–17:00 (the user), so the spec's day is kept by setting 07:00–17:00 as the scheme's default gate hours
(planning.default_gate_hours, Config → Planning) — the setting a scheme uses for its own hours — and §8b checks the
shipped default on the same month: 08:00–17:00, no lorry arriving before the opening (the first set off before it), the
same pour at 94 %, amber; and the gates' shut windows (taken off once with the bands, under scenario hours too).

Plus: the module reads and never writes and carries the tenant on every SQL literal; scenarios are parsed or refused in
words; a team code sees other teams' lines by route only; the Gate arrivals reply carries the busiest hour; the
endpoint's 400 / 401 edges.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed (http_smoke.py drives the real one against the demo package).
  * The drawing (S7) — this checks the numbers the drawing will read, not the drawing.
  * SQLite only. The routes' lines are the live demo's as of 16 Oct; a re-bake on live moves drive times (D94), never
    the gate figures (they depend on arrivals and check-ins only).

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_sim.py
"""
import json
import math
import os
import re
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_gate_arrivals.py ------------------------------------
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

TMP = tempfile.mkdtemp(prefix="rbe_sim_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import gate_arrivals  # noqa: E402
import gate_hours  # noqa: E402
import network  # noqa: E402
import zones  # noqa: E402
import limits  # noqa: E402
import sim  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
days.START_YEAR = main.START_YEAR

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


def hm(m):
    return None if m is None else sim.hhmm(m)


# =========================================================================== #
#  0. The live demo's shape of Sep 2026 (the example's README §3)              #
# =========================================================================== #
FX = json.load(open(os.path.join(HERE, "fixtures", "sim_demo_sep2026.json"), encoding="utf-8"))


def decode(c):
    v = [int(x) for x in c.split(",")]
    pts, x, y = [], 0, 0
    for i in range(0, len(v), 2):
        x += v[i]
        y += v[i + 1]
        pts.append([x / 1e5, y / 1e5])
    return pts


TEAMS = {"IPT1": "North Team", "IPT2": "Central Team", "IPT3": "South Team"}
NODES = [("L001", "Kilby Ridge Quarry", "Quarry", "origin", -1.238, 52.561),
         ("L002", "Northfield Quarry", "Quarry", "origin", -1.134, 52.727),
         ("L003", "Brook Pit", "Quarry", "origin", -0.752, 52.694),
         ("L004", "Harborough Rail Freight Terminal", "Railhead", "origin", -0.918, 52.4785),
         ("L005", "Harborough Compound", "Compound", "destination", -0.897612, 52.504868),
         ("L006", "Langton Compound", "Compound", "destination", -0.897495, 52.55399),
         ("L007", "Tilton Compound", "Compound", "destination", -0.875475, 52.647045),
         ("L008", "Melton Compound", "Compound", "destination", -0.872505, 52.740814),
         ("L009", "Stockpile South", "Stockpile", "destination", -0.906743, 52.520683),
         ("L010", "Stockpile Tilton", "Stockpile", "destination", -0.890947, 52.63616),
         ("L011", "Stockpile North", "Stockpile", "destination", -0.880052, 52.703205)]
# id, name, location, direction, default, check-in (safety_minutes), internal minutes, lon, lat — as typed on the demo
GATES = [("G001", "Weighbridge (in)", "L001", "access", False, 4, 6, -1.241842, 52.56181),
         ("G002", "Main road exit", "L001", "egress", True, None, 4, -1.233419, 52.559742),
         ("G003", "Weighbridge (in)", "L002", "access", False, 4, 5, -1.13756, 52.72592),
         ("G004", "A46 exit", "L002", "egress", True, None, 3, -1.129847, 52.728436),
         ("G005", "Pit entrance", "L003", "both", True, 3, 4, -0.749332, 52.693462),
         ("G006", "Terminal gate", "L004", "both", True, 5, 5, -0.920212, 52.480297),
         ("G007", "Station Road entrance (in)", "L005", "access", False, 5, 3, -0.900711, 52.506214),
         ("G008", "Mill Lane exit", "L005", "egress", True, None, 3, -0.894218, 52.503338),
         ("G009", "Compound gate", "L006", "both", True, 3, None, -0.894688, 52.554527),
         ("G010", "Compound gate", "L007", "both", True, 3, None, -0.878436, 52.647766),
         ("G011", "Compound gate", "L008", "both", True, 3, None, -0.869389, 52.740005),
         ("G012", "Stockpile gate", "L009", "both", True, None, None, -0.904381, 52.52158),
         ("G013", "Stockpile gate", "L010", "both", True, None, None, -0.893463, 52.635357),
         ("G014", "Stockpile gate", "L011", "both", True, None, None, -0.877828, 52.70213)]
# route, origin, destination, team, origin's named gate, destination's named gate (the demo package's)
ROUTES = [("R001", "L001", "L005", "IPT3", "G002", "G007"), ("R002", "L002", "L005", "IPT3", "G004", "G007"),
          ("R003", "L004", "L005", "IPT3", "G006", "G007"), ("R004", "L001", "L006", "IPT2", "G002", "G009"),
          ("R005", "L002", "L006", "IPT2", "G004", "G009"), ("R006", "L004", "L006", "IPT2", "G006", "G009"),
          ("R007", "L001", "L007", "IPT1", "G002", "G010"), ("R008", "L002", "L007", "IPT1", "G004", "G010"),
          ("R009", "L004", "L007", "IPT1", "G006", "G010"), ("R010", "L001", "L008", "IPT1", "G002", "G011"),
          ("R011", "L002", "L008", "IPT1", "G004", "G011"), ("R012", "L004", "L008", "IPT1", "G006", "G011"),
          ("R013", "L003", "L005", "IPT3", "G005", "G007"), ("R014", "L003", "L006", "IPT2", "G005", "G009"),
          ("R015", "L003", "L009", "IPT3", "G005", "G012"), ("R016", "L003", "L011", "IPT1", "G005", "G014"),
          ("R017", "L001", "L010", "IPT1", "G002", "G013"), ("R018", "L002", "L011", "IPT1", "G004", "G014")]
TIP, FLAT = "Artic Tipper (44t)", "Artic Flatbed (44t)"
# Sep 2026 approved lines: route, tonnes, vehicle (live /api/public/forecast-matrix, 16 Oct)
LINES = [("R001", 15800, TIP), ("R002", 10600, TIP), ("R003", 1900, FLAT), ("R004", 16100, TIP), ("R005", 6100, TIP),
         ("R006", 1700, FLAT), ("R007", 8400, TIP), ("R008", 8200, TIP), ("R009", 1800, FLAT), ("R010", 15900, TIP),
         ("R011", 6200, TIP), ("R012", 2300, FLAT), ("R013", 22200, TIP), ("R014", 23300, TIP), ("R015", 20800, TIP),
         ("R016", 17200, TIP), ("R017", 12400, TIP), ("R018", 7500, TIP)]
# the example's numbers (its engine, run under Node on 16 Oct): whole loads per line and the Dashboard's figures
EX_PER_LINE = [25, 16, 3, 25, 10, 3, 13, 13, 3, 25, 10, 4, 35, 36, 33, 27, 19, 12]
EX_PANEL = {"G005": 131.0, "G001": 107.6, "G007": 79.3, "G009": 74.2, "G003": 60.6, "G014": 38.8, "G011": 38.5,
            "G012": 32.6, "G010": 29.0, "G013": 19.5, "G006": 12.6}
POUR = dict(pour_gate="G007", pour_start="10:00", pour_m3="160", pour_m3_per_load="7.5", pour_rate="60")


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
    limits.init_db()            # a stored route's limit check is cleared when its line is written
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    costing.invalidate()


def seed():
    reset_db()
    access.set_current("planner123")
    for tid, label in TEAMS.items():
        db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)",
                   (db.current_tenant(), tid, label, True))
    for lid, name, lt, role, lon, lat in NODES:
        db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
                   (lid, name, lt, role, lat, lon))
    for gid, name, loc, d, dflt, sm, itm, lon, lat in GATES:
        r = gates.create_gate(loc, name, lat, lon, direction=d, safety_minutes=sm, internal_travel_minutes=itm,
                              is_default=dflt, gate_id=gid)
        assert not r.get("error"), r
    for h in FX["haul"]:
        z = zones.create_zone(h["name"], {"type": "LineString", "coordinates": decode(h["c"])}, kind=zones.HAUL_KIND,
                              speed_kph=h["kph"], zone_id=h["id"])
        assert not (z or {}).get("error"), z
    for rid, o, d, ipt, og, dg in ROUTES:
        db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", (rid, o, d, ipt))
        r = gates.set_route_gates(rid, origin_gate_id=og, dest_gate_id=dg, origin_given=True, dest_given=True)
        assert not r.get("error"), r
    team_of = {r[0]: r[3] for r in ROUTES}
    for rid, t, veh in LINES:
        main.save_matrix_row(main.MatrixRow(
            route_id=rid, discipline="earthworks", section_id="WS1", material_type="Small aggregate",
            material_description=None, vehicle_type=veh, submitted_by="tester", unit="t", status="Pending",
            cells=[main.Cell(month_index=9, quantity=float(t))], ipt=team_of[rid]))
        main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id="WS1")
    # the routes' lines: the public map served the tipper's; the flatbed lines draw it (the example's stand-in)
    for L in FX["legs"]:
        hz = ",".join(sorted({z[0] for z in L["hz"]}))
        network._upsert_geom(L["r"], TIP, json.dumps(decode(L["c"])), L["km"], L["hr"], None, leg=L["l"],
                             haul_zones=hz)


seed()
# 17 Oct 2026: `factors_code` is the stored Config (no default gate hours typed: 08:00–17:00); `factors` sets the
# example's 07:00–17:00 as the scheme's default gate hours, so every spec figure below is the approved example's
factors_code = conversions.load_factors()
factors = json.loads(json.dumps(factors_code))
factors.setdefault("planning", {})["default_gate_hours"] = {"from": "07:00", "to": "17:00"}
WD = main._working_days(factors)
acc_planner = access.current()

# =========================================================================== #
#  1. Source level: reads only, the tenant on every SQL literal, no slot id   #
# =========================================================================== #
src = open(os.path.join(BACKEND, "sim.py"), encoding="utf-8").read()
code_only = src.split('"""', 2)[2]
ok("⭐ sim.py is read-only: no execute / INSERT / UPDATE / DELETE",
   "db.execute" not in code_only and not re.search(r"\b(INSERT|UPDATE|DELETE)\b", code_only))
ok("⭐ sim.py imports neither main nor network, and names no team slot id",
   not re.search(r"^\s*(import|from)\s+(network|main)\b", src, re.M) and re.search(r"\bIPT ?[1-6]\b", src) is None)
_stmts = re.findall(r'db\.query\(\s*(f?(?:"[^"]*"\s*)+)', code_only)
ok("🔴 tenant isolation: every SQL literal in sim.py constrains tenant_id",
   len(_stmts) == 4 and all("tenant_id = ?" in s for s in _stmts) and code_only.count("db.current_tenant()") >= 4,
   str(_stmts))
ok("the engine reuses the Dashboard's rules: trips_for, entry_gate, judge, gate_hours' capacity words and NEAR_PCT",
   "gate_arrivals.trips_for(" in code_only and "gate_arrivals.entry_gate(" in code_only
   and "gate_arrivals.judge(" in code_only and "gate_hours.STATUS_WORDS" in code_only and "gate_hours.NEAR_PCT" in code_only)
ga_src = open(os.path.join(BACKEND, "gate_arrivals.py"), encoding="utf-8").read()
ok("gate_arrivals resolves every end with entry_gate() (arrivals, week_by_day) and judges with judge()",
   ga_src.count("entry_gate(loc") == 3 and "jd = judge(arr_raw, open_g, gm)" in ga_src
   and ga_src.count('gates.resolve(loc, "entry"') == 2)
main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
_sd = main_src[main_src.index('@app.get("/api/sim/day")'):]
_sd = _sd[:_sd.index("\n@app.")]
ok("⭐ GET /api/sim/day: any signed-in code (_require_access), 400 in words for a scenario it cannot run, no write",
   "acc = _require_access()" in _sd and "except ValueError as e:" in _sd and "HTTPException(400, str(e))" in _sd
   and "db.execute" not in _sd and "save" not in _sd.lower().replace("nothing saved", ""))

# =========================================================================== #
#  2. The fixture is the live demo's Sep 2026: the Dashboard's own figures     #
# =========================================================================== #
panel = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
pfig = {g["gate_id"]: g["arrivals_per_day"] for g in panel["gates"]}
ok("⭐ the fixture: gate_arrivals.arrivals(Sep 2026) gives the eleven Dashboard figures the example used",
   pfig == EX_PANEL, str(pfig))

# =========================================================================== #
#  3. The example's day, with the example pour                                 #
# =========================================================================== #
t0 = time.time()
D = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR),
            send_lines=True)
t_day = time.time() - t0
byg = {g["gate_id"]: g for g in D["gates"]}
ok("⭐ 312 loads in the day (6,860 trips ÷ 22 working days, rounded)", D["loads"] == 312 and D["loads_month"] == 6860,
   f"{D['loads']} {D['loads_month']}")
ok("⭐ D88: the whole loads per line are the example's, line by line",
   [l["loads"] for l in D["lines"]] == EX_PER_LINE, str([l["loads"] for l in D["lines"]]))
ok("⭐ 646 gate arrivals (312 × 2 + 22 mixers): the table, the list and the expected count agree",
   D["gate_arrivals"] == 646 and len(D["arrivals"]) == 646 and D["checks"]["arrivals_expected"] == 646
   and D["checks"]["table_equals_arrivals"] is True, str(D["checks"]))
ok("each gate's hours add up to its day", D["checks"]["hours_add_up"] is True
   and all(sum(g["hours"]) == g["arrivals"] for g in D["gates"]))
ok("⭐ every gate's laden + empty arrivals are within 0.6 of the Dashboard's Sep 2026 figure",
   D["checks"]["largest_panel_difference"] is not None and D["checks"]["largest_panel_difference"] <= 0.6
   and all(abs(g["laden"] + g["empty"] - EX_PANEL[g["gate_id"]]) <= 0.6 for g in D["gates"]),
   str(D["checks"]["largest_panel_difference"]))
ok("D88 is exact on this month (every choice searched) and its worst gate difference is the one reported",
   D["rounding"]["exact"] is True and abs(D["rounding"]["worst"] - D["checks"]["largest_panel_difference"]) < 0.01)
g7 = byg["G007"]
ok("⭐ the pour: 22 mixers at Harborough Compound, 101 arrivals, 84 % of what it can check in",
   g7["pour"] == 22 and g7["arrivals"] == 101 and g7["pct"] == 84 and D["pour"]["loads"] == 22
   and D["pour"]["gap_minutes"] == 7.5 and D["pour"]["end"] == "12:38", str({k: g7[k] for k in ("pour", "arrivals", "pct")}))
ok("⭐ the queue at Harborough: the first wait at 10:00, up to 12 waiting at 12:38",
   hm(g7["queue_start"]) == "10:00" and g7["most_waiting"] == 12 and hm(g7["most_at"]) == "12:38",
   f"{hm(g7['queue_start'])} {g7['most_waiting']} {hm(g7['most_at'])}")
ok("⭐ 1,776 lorry-minutes lost at Harborough, the longest wait 56 min",
   sim.js_round(g7["minutes_lost"]) == 1776 and sim.js_round(g7["longest_wait"]) == 56,
   f"{g7['minutes_lost']} {g7['longest_wait']}")
ok("84 % is not amber (85 %) and the gap holds: no Dashboard flag at Harborough, whatever the queue shows",
   g7["flag"] is None and g7["status_word"] is None and g7["gap"] == 5.9)
_q7 = [a for a in D["arrivals"] if a["gate"] == "G007"]
_bn = next((a for a in _q7 if a["wait"] > 5 + sim.WAIT_EPS), None)
ok("⭐ D85: the bottleneck is the first wait LONGER than the 5 min check-in, after the first wait of any length",
   _bn is not None and g7["bottleneck_at"] == _bn["at"] and g7["bottleneck_at"] > g7["queue_start"]
   and all(a["wait"] <= 5 + sim.WAIT_EPS for a in _q7 if a["at"] < _bn["at"]),
   f"{hm(g7['bottleneck_at'])}")
ok("no other gate waits with the pour at Harborough",
   all(g["queue_start"] is None and g["minutes_lost"] == 0 for g in D["gates"] if g["gate_id"] != "G007"))
ok("⭐ the playback runs from the first lorry setting off to the last check-in: 05:30–17:30",
   D["window"]["from"] == "05:30" and D["window"]["to"] == "17:30", str(D["window"]))
ok("every arrival set off before it arrived and fits the window",
   all(a["depart"] is not None and a["depart"] <= a["at"] and a["depart"] >= D["window"]["start"]
       and a["done"] <= D["window"]["end"] for a in D["arrivals"]))
ok("open hours: the scheme's default gate hours, 07:00–17:00 here, on every gate (none typed on the demo), and the reply "
   "says so and where a gate's own hours are typed (Data → Locations; it said 'on Config', which was wrong)",
   all(g["open_basis"] == "default" and g["open_from"] == "07:00" and g["open_to"] == "17:00"
       and "the default gate hours" in (g["open_words"] or "") for g in D["gates"])
   and D["default_hours"] == {"from": "07:00", "to": "17:00"}
   # NARROWED 17 Oct 2026 (the review): `stand_in` stays one release as the same hours, for Dashboards open across the deploy
   and D["stand_in"] == {"from": "07:00", "to": "17:00", "shift_hours": 10.0}
   and any("07:00–17:00, the default gate hours" in n and "Data → Locations" in n for n in D["notes"])
   and not any("stood in" in n or "on Config." in n for n in D["notes"]), str(D["notes"]))
ok("⭐ D84: the quarries and the terminal carry the share note, the compounds and stockpiles do not",
   all((byg[g]["origin_share_note"] == sim.NOTE_ORIGIN) == (g in ("G001", "G003", "G005", "G006")) for g in byg)
   and "only this scheme's lorries are counted" in sim.NOTE_ORIGIN)
ok("teams are the tenant's names, never slot ids: Harborough South, Langton Central, Kilby Ridge all three",
   byg["G007"]["teams"] == ["South Team"] and byg["G009"]["teams"] == ["Central Team"]
   and byg["G001"]["teams"] == ["Central Team", "North Team", "South Team"], str(byg["G001"]["teams"]))
ok("no slot id anywhere in the reply", re.search(r"\bIPT ?[1-6]\b", json.dumps(D)) is None)
ok("the haul roads: 148 lorries on Langton haul road, 78 on Stockpile North's (the example's counts)",
   {h["zone_id"]: h["lorries"] for h in D["haul_roads"]} == {"Z001": 148, "Z002": 78},
   str([(h["zone_id"], h["lorries"]) for h in D["haul_roads"]]))
ok("the mixers drive the last 2.5 miles of the shortest road into the gate (R003's, 6.8 km)",
   D["pour"]["approach_leg"] == f"R003|{TIP}|loaded"
   and all(a["from_m"] > 0 for a in _q7 if a["kind"] == "pour"))
ok("the reply carries the limits: a planning view, congestion on the public road not modelled",
   any("Planning view, not a record" in x for x in D["limits"]) and any("Congestion on the public road is not modelled" in x for x in D["limits"]))
ok("the mixer is the app's own (key Truck mixer 8 m³ (32t), 7.5 m³ a load), read as Concrete mixer 8 m³ (32t)",
   D["mixer"] == {"m3_per_load": 7.5, "vehicle": sim.MIXER_NAME, "vehicle_label": "Concrete mixer 8 m³ (32t)"}, str(D["mixer"]))
ok("every vehicle a person reads is a label: Artic Tipper (44t) / Artic Flatbed (44t), never a 'Truck' word",
   all(l["vehicle_label"] == l["vehicle"] and l["vehicle_drawn_label"] == TIP for l in D["lines"])
   and not re.search(r"\btrucks?\b", json.dumps([l["vehicle_label"] for l in D["lines"]] + [D["mixer"]["vehicle_label"]]), re.I))
ok(f"a day is quick enough for a Dashboard read ({t_day:.2f} s, lines included)", t_day < 8.0, f"{t_day:.2f}")

# ---- the lines for the drawing
legs = D["legs"]
k1 = f"R001|{TIP}|loaded"
ok("⭐ each line's OWN vehicle's route; the flatbed lines (no flatbed route worked out) draw the tipper's, said",
   [l["vehicle_drawn"] for l in D["lines"]] == [TIP] * 18
   and [l["vehicle_as_planned"] for l in D["lines"]] == [v == TIP for _, _, v in LINES])
ok("a leg carries its line, length, metres along it and the parts at their speeds; the stored time is the plan's",
   legs[k1]["drawn"] and len(legs[k1]["coords"]) > 50 and abs(legs[k1]["minutes"] - 0.601 * 60) < 1e-6
   and abs(legs[k1]["plan_minutes"] - 0.601 * 60) < 1e-3 and len(legs[k1]["cum"]) == len(legs[k1]["coords"]))
k4 = f"R004|{TIP}|loaded"
_hp = [p for p in legs[k4]["parts"] if p[3] == "Z001"]
ok("a haul stretch runs at its assigned speed: R004 crosses Langton haul road at 20 km/h",
   len(_hp) == 1 and abs(_hp[0][2] - 20 * 1000 / 60) < 1e-3 and abs(legs[k4]["plan_minutes"] - 0.855 * 60) < 1e-3)
_found = {}
for L in FX["legs"]:
    st = sim.haul_stretches(decode(L["c"]), {h["id"]: decode(h["c"]) for h in FX["haul"]})
    _found[(L["r"], L["l"])] = [list(s) for s in st] == [list(z) for z in L["hz"]]
ok("⭐ the haul-stretch finder (within 4 m of the drawn road) finds the example's stretches on all 36 legs",
   all(_found.values()), str([k for k, v in _found.items() if not v]))
ok("every route is drawn on the fixture: not_drawn is empty", D["not_drawn"] == [])
ok("S7: with the lines, each haul road carries its drawn line (the map draws it); without them, none",
   all(h["coords"] and len(h["coords"]) >= 2 for h in D["haul_roads"]) and all(h["coords"] is None for h in D_nolines_h["haul_roads"])
   if (D_nolines_h := sim.day(9, acc_planner, factors=factors, working_days=WD)) else False)
_z3 = zones.create_zone("Unused haul road", {"type": "LineString", "coordinates": [[-0.5, 52.5], [-0.49, 52.51]]}, kind=zones.HAUL_KIND, speed_kph=15)
ok("S7: a haul road no route of the day runs along is not listed", [h["zone_id"] for h in sim.day(9, acc_planner, factors=factors, working_days=WD, send_lines=True)["haul_roads"]] == ["Z001", "Z002"])
zones.delete_zone(_z3["id"])
# a route whose return was never worked out: the empty lorries drive the loaded line backwards, said
db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R018' AND leg = 'return'", (db.current_tenant(),))
Drev = sim.day(9, acc_planner, factors=factors, working_days=WD, send_lines=True)
kr = f"R018|{TIP}|return"
ok("no return line worked out: the empty lorries drive the loaded line reversed, at the loaded leg's time, and say so",
   Drev["legs"][kr]["reversed"] is True and Drev["legs"][kr]["coords"][0] == Drev["legs"][f"R018|{TIP}|loaded"]["coords"][-1]
   and abs(Drev["legs"][kr]["minutes"] - 0.799 * 60) < 1e-6 and Drev["not_drawn"] == [])
db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R018'", (db.current_tenant(),))
Dnd = sim.day(9, acc_planner, factors=factors, working_days=WD, send_lines=True)
ok("no line at all: the route is named in not_drawn and its lorries still count at the gates (646 - 22 = 624 arrivals)",
   Dnd["not_drawn"] == ["R018"] and Dnd["gate_arrivals"] == 624
   and all(a["depart"] is None for a in Dnd["arrivals"] if a["route"] == "R018"))
for L in FX["legs"]:
    if L["r"] == "R018":
        network._upsert_geom(L["r"], TIP, json.dumps(decode(L["c"])), L["km"], L["hr"], None, leg=L["l"],
                             haul_zones=",".join(sorted({z[0] for z in L["hz"]})))
D_nolines = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR))
ok("without send_lines the reply has no coordinates, and the same arrivals",
   all("coords" not in v for v in D_nolines["legs"].values()) and D_nolines["arrivals"] == D["arrivals"])

# =========================================================================== #
#  4. Pour off, bands, and the review's edge cases                             #
# =========================================================================== #
Doff = sim.day(9, acc_planner, factors=factors, working_days=WD)
ok("⭐ pour off: no lorry waits anywhere (an even spread under 100 % never queues), 624 arrivals",
   Doff["gate_arrivals"] == 624 and all(g["queue_start"] is None and g["most_waiting"] == 0 and g["late"] == 0
                                        for g in Doff["gates"]) and Doff["pour"] is None)
ok("the default day has no pour and the bands off (none typed)", Doff["bands"]["on"] is False and Doff["bands"]["source"] is None)
_busy_ex = {"G001": (11, 7), "G003": (7, 12), "G005": (14, 12), "G006": (2, 8), "G007": (8, 7), "G009": (8, 8),
            "G010": (3, 7), "G011": (4, 7), "G012": (4, 8), "G013": (2, 7), "G014": (4, 7)}
ok("⭐ the busiest clock hour at every gate is the example's (lorries, first busiest hour)",
   {g["gate_id"]: (g["busiest"], g["busiest_hours"][0]) for g in Doff["gates"]} == _busy_ex,
   str({g["gate_id"]: (g["busiest"], g["busiest_hours"][0]) for g in Doff["gates"]}))

Dband = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bands="on"))
bb = {g["gate_id"]: g for g in Dband["gates"]}
ok("bands on with none typed: Config's example bands stand in (07:00–10:00 and 16:00–19:00), said in a note",
   Dband["bands"]["on"] and Dband["bands"]["source"] == "example" and Dband["bands"]["bands"] == gate_hours.PEAK_PLACEHOLDER
   and any("Config's example bands" in n for n in Dband["notes"]))
ok("⭐ bands on 07:00–17:00, pour off: Kilby Ridge 119 %, Brook Pit 109 %, Harborough 110 %, all three red",
   (bb["G001"]["pct"], bb["G005"]["pct"], bb["G007"]["pct"]) == (119, 109, 110)
   and all(bb[g]["flag"] == "red" and bb[g]["status_word"] == "Over gate capacity" for g in ("G001", "G005", "G007")),
   str([(g, bb[g]["pct"], bb[g]["flag"]) for g in ("G001", "G005", "G007")]))
ok("bands on: queues start between 10:04 and 10:07, up to 17, 11 and 7 waiting",
   (hm(bb["G005"]["queue_start"]), hm(bb["G001"]["queue_start"]), hm(bb["G007"]["queue_start"])) == ("10:04", "10:05", "10:07")
   and (bb["G001"]["most_waiting"], bb["G005"]["most_waiting"], bb["G007"]["most_waiting"]) == (17, 11, 7))
ok("⭐ D89: lorries still waiting after the last open minute are checked in late and counted (17, 11, 7), the last at 17:10",
   (bb["G001"]["late"], bb["G005"]["late"], bb["G007"]["late"]) == (17, 11, 7) and hm(bb["G001"]["last_done"]) == "17:10")
ok("bands on: the open minutes are 360 (600 less the two bands inside 07:00–17:00), and no arrival is placed in a band",
   all(g["open_minutes"] == 360 for g in Dband["gates"])
   and not any((420 <= a["at"] < 600 or 960 <= a["at"] < 1140) for a in Dband["arrivals"]))

# the same bands TYPED on Config are on by default
_f2 = json.loads(json.dumps(factors))
_f2.setdefault("planning", {})["peak_bands"] = gate_hours.PEAK_PLACEHOLDER
Dtyped = sim.day(9, acc_planner, factors=_f2, working_days=WD)
ok("bands typed on Config: on by default, source typed, the same figures as the example bands",
   Dtyped["bands"]["on"] and Dtyped["bands"]["source"] == "typed"
   and [(g["gate_id"], g["pct"], g["most_waiting"], g["late"]) for g in Dtyped["gates"]]
   == [(g["gate_id"], g["pct"], g["most_waiting"], g["late"]) for g in Dband["gates"]])
Dtyped_off = sim.day(9, acc_planner, factors=_f2, working_days=WD, scenario=sim.scenario_from_query(bands="off"))
ok("bands typed, switched off for the scenario: no queue anywhere",
   Dtyped_off["bands"]["on"] is False and all(g["queue_start"] is None for g in Dtyped_off["gates"]))

Dbp = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bands="on", **POUR))
g7bp = {g["gate_id"]: g for g in Dbp["gates"]}["G007"]
ok("bands and the pour together: Harborough 140 %, up to 29 waiting, the last check-in at 18:25",
   g7bp["pct"] == 140 and g7bp["most_waiting"] == 29 and hm(g7bp["last_done"]) == "18:25")

# a boundary minute belongs to the NEXT interval
Dbd = sim.day(9, acc_planner, factors=factors, working_days=WD,
              scenario=sim.scenario_from_query(hours=["all=05:00-17:00"], bands="on"))
lb = {g["gate_id"]: g for g in Dbd["gates"]}
ok("⭐ the boundary minute: every gate 05:00–17:00 with the bands, Langton does not queue",
   lb["G009"]["queue_start"] is None and lb["G009"]["open_basis"] == "scenario")
ok("no Langton arrival is placed inside the 07:00–10:00 band",
   not any(a["gate"] == "G009" and 420 <= a["at"] < 600 for a in Dbd["arrivals"]))
ok("clock_at_open: open minute 120 of [05:00–07:00, 10:00–16:00] is 10:00, never 07:00",
   sim.clock_at_open([(300, 420), (600, 960)], 120) == 600 and sim.clock_at_open([(300, 420), (600, 960)], 119.5) == 419.5)
D620 = sim.day(9, acc_planner, factors=factors, working_days=WD,
               scenario=sim.scenario_from_query(hours=["all=06:00-20:00"], bands="on"))
ok("06:00–20:00 with the bands: no arrival inside a band at any gate",
   not any((420 <= a["at"] < 600 or 960 <= a["at"] < 1140) for a in D620["arrivals"] if a["kind"] != "pour"))

# late check-ins counted with no queue
Dlate = sim.day(9, acc_planner, factors=factors, working_days=WD,
                scenario=sim.scenario_from_query(**dict(POUR, pour_start="17:30")))
gl = {g["gate_id"]: g for g in Dlate["gates"]}["G007"]
ok("⭐ D89 with no queue: a pour at 17:30 after the gate shuts at 17:00 — 22 late check-ins, nobody waits",
   gl["late"] == 22 and gl["queue_start"] is None and gl["most_waiting"] == 0, f"late {gl['late']}")

# the red rule is the Dashboard's displayed-gap rule
Dbr = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(hours=["G005=07:00-13:30"]))
gb = {g["gate_id"]: g for g in Dbr["gates"]}["G005"]
ok("⭐ the red rule: Brook Pit 07:00–13:30 — the displayed gap 3.0 is not shorter than its 3 min check-in: amber",
   gb["gap"] == 3.0 and gb["flag"] == "amber" and gb["status_word"] == "Queue likely" and gb["pct"] == 101,
   f"{gb['gap']} {gb['flag']} {gb['pct']}")
ok("…and the Dashboard's judge() says the same for the same figures",
   gate_arrivals.judge(131.0, 390.0, 3.0)["flag"] == "amber" and gate_arrivals.judge(131.0, 385.0, 3.0)["flag"] == "red")

# a pour into Langton crosses Langton haul road
Dlp = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**dict(POUR, pour_gate="G009")))
ok("a pour into Langton adds its mixers to Langton haul road (148 -> 170)",
   {h["zone_id"]: h["lorries"] for h in Dlp["haul_roads"]}["Z001"] == 170)

# =========================================================================== #
#  5. Refused in words: D93 and the pour                                       #
# =========================================================================== #
e1 = raises(lambda: sim.scenario_from_query(hours=["G001=22:00-06:00"]))
ok("⭐ D93: a window that ends before it starts is refused, in words",
   isinstance(e1, ValueError) and "past midnight is not simulated" in str(e1))
e1b = raises(lambda: sim.scenario_from_query(hours=["all=07:00-07:00"]))
ok("D93: a window that ends AT its start is refused too", isinstance(e1b, ValueError) and "close after it opens" in str(e1b))
e2 = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD,
                            scenario=sim.scenario_from_query(**dict(POUR, pour_start="23:00"))))
ok("⭐ a pour whose last mixer would come after 23:59 is refused, with the time",
   isinstance(e2, ValueError) and "past midnight" in str(e2) and "25:38" in str(e2), str(e2))
e3 = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD,
                            scenario=sim.scenario_from_query(**dict(POUR, pour_gate="G008"))))
ok("the pour's gate must be an entry gate (Mill Lane is exit only)", isinstance(e3, ValueError) and "entry gates" in str(e3))
for bad, words in ((dict(POUR, pour_m3="0"), "above nothing"), (dict(POUR, pour_rate="x"), "above nothing"),
                   (dict(POUR, pour_start="25:00"), "start time"), (dict(POUR, pour_m3="100000", pour_m3_per_load="1"), "at most")):
    e = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**bad)))
    ok(f"a pour that cannot be run is refused: {words}", isinstance(e, ValueError) and words in str(e), str(e))
for bad in (dict(hours=["G001"]), dict(hours=["G001=7-17"]), dict(check_in=["G001"]), dict(check_in=["G001=x"]),
            dict(check_in=["G001=-1"]), dict(check_in=["G001=999"]), dict(bands="maybe")):
    ok(f"a scenario that cannot be read is refused in words: {bad}", isinstance(raises(lambda: sim.scenario_from_query(**bad)), ValueError))
e4 = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(hours=["G999=07:00-17:00"])))
ok("a gate the scheme does not have is refused", isinstance(e4, ValueError) and "G999" in str(e4))

# 17 Oct 2026 (found on live): where a pour can go, and its default
_pg = D["pour_gates"]
ok("⭐ the pour goes to a working site only: the four compounds' entry gates, busiest first (laden a day), never a quarry, railhead or stockpile",
   [x["gate_id"] for x in _pg] == ["G007", "G009", "G011", "G010"]
   and [x["laden_per_day"] for x in _pg] == [79.3, 74.2, 38.5, 29.0] and all("Compound" in x["location_name"] for x in _pg), str(_pg))
ok("⭐ the default pour gate is the working site with the most laden lorries a day: Harborough Compound (79.3, ahead of Langton's 74.2)",
   D["pour_default"] == "G007" and Doff["pour_default"] == "G007")
e_sp = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**dict(POUR, pour_gate="G012"))))
ok("a pour at a stockpile is refused in words", isinstance(e_sp, ValueError) and "A pour goes to a working site (a compound or a site): Stockpile South is a stockpile." == str(e_sp), str(e_sp))
db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
           ("L012", "Wolds Link Inert Landfill (fictional)", "Landfill", "destination", 52.6, -0.95))
_lg = gates.create_gate("L012", "Weighbridge", 52.601, -0.951, direction="both", safety_minutes=4, is_default=True, gate_id="G015")
e_lf = raises(lambda: sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**dict(POUR, pour_gate="G015"))))
ok("⭐ a pour at the inert landfill is refused in words, and the landfill is never offered",
   isinstance(e_lf, ValueError) and str(e_lf) == "A pour goes to a working site (a compound or a site): Wolds Link Inert Landfill (fictional) is a landfill."
   and "G015" not in [x["gate_id"] for x in sim.day(9, acc_planner, factors=factors, working_days=WD)["pour_gates"]], str(e_lf))
ok("pour_site: Compound and Site (any case, spaces), nothing else",
   all(sim.pour_site({"loc_type": t}) for t in ("Compound", " site ", "COMPOUND"))
   and not any(sim.pour_site({"loc_type": t}) for t in ("Landfill", "Soil recycling", "Batching plant", "Stockpile", "Quarry", "Railhead", "Port", "Other", "", None)))
ok("the pour-site types are the working destinations the app already has (network._role_for; the Locations form's types)",
   all(network._role_for(t) == "destination" for t in sim.POUR_SITE_TYPES)
   and all(f'"{t.title()}"' in open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read().split("const LOC_TYPES = [", 1)[1].split("]", 1)[0]
           for t in sim.POUR_SITE_TYPES))
db.execute("DELETE FROM location_gates WHERE tenant_id = ? AND id = 'G015'", (db.current_tenant(),))
db.execute("DELETE FROM locations WHERE tenant_id = ? AND id = 'L012'", (db.current_tenant(),))

# 17 Oct 2026 (found on live): a gate's ACCESS ROAD is driven at its speed but not listed with the haul roads
_before = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR), send_lines=True)
gates.update_gate("G009", access_zone_id="Z001")          # Langton's gate takes Langton haul road as its access road
_after = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR), send_lines=True)
ok("⭐ a gate's access road is left out of the haul roads (Z001 now Langton's access road); the other haul road is still listed; the reply says one was left out",
   [h["zone_id"] for h in _after["haul_roads"]] == ["Z002"] and _after["access_roads_hidden"] == 1
   and [h["zone_id"] for h in _before["haul_roads"]] == ["Z001", "Z002"] and _before["access_roads_hidden"] == 0)
ok("⭐ ...and the drive is unchanged: every arrival's minute, check-in, wait and departure, and each leg's plan, are the same",
   _after["arrivals"] == _before["arrivals"] and _after["window"] == _before["window"]
   and all(_after["legs"][k].get("parts") == _before["legs"][k].get("parts") for k in _before["legs"]))
gates.update_gate("G009", access_zone_id=None)

# typed open hours past midnight: the gate is left out and named
gates.update_gate("G009", open_from="22:00", open_to="06:00")
Dpm = sim.day(9, acc_planner, factors=factors, working_days=WD)
lpm = {g["gate_id"]: g for g in Dpm["gates"]}["G009"]
ok("⭐ D93 typed on a gate: Langton open 22:00–06:00 is left out, its arrivals unplaced, the reply says why",
   lpm["open_basis"] == "refused" and lpm["arrivals"] == 0 and lpm["unplaced"] == 74
   and "runs past midnight" in (lpm["open_words"] or "") and any("Langton Compound left out" in n for n in Dpm["notes"]))
gates.update_gate("G009", open_from="06:00", open_to="18:00")
Dtyped_h = sim.day(9, acc_planner, factors=factors, working_days=WD)
lt = {g["gate_id"]: g for g in Dtyped_h["gates"]}["G009"]
ok("a gate's typed hours are used: Langton 06:00–18:00, basis gate, 720 open minutes",
   lt["open_basis"] == "gate" and lt["open_from"] == "06:00" and lt["open_to"] == "18:00" and lt["open_minutes"] == 720
   and lt["open_words"] is None)
Dov = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(hours=["G009=08:00-12:00", "all=07:00-17:00"]))
lo = {g["gate_id"]: g for g in Dov["gates"]}
ok("a scenario's hours win over the typed ones; a gate's own over 'all'",
   lo["G009"]["open_from"] == "08:00" and lo["G001"]["open_from"] == "07:00" and lo["G001"]["open_basis"] == "scenario")
gates.update_gate("G009", open_from=None, open_to=None)

# check-in overrides
Dci = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(check_in=["G007="], **POUR))
ok("a check-in cleared for the scenario: Harborough never queues, even with the pour",
   {g["gate_id"]: g for g in Dci["gates"]}["G007"]["queue_start"] is None
   and {g["gate_id"]: g for g in Dci["gates"]}["G007"]["capacity"] is None)
Dci2 = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(check_in=["G012=20"]))
g12 = {g["gate_id"]: g for g in Dci2["gates"]}["G012"]
ok("a check-in typed for the scenario on a stockpile with none: 33 lorries at 20 min a lorry queue (110 %, red)",
   g12["check_in"] == 20.0 and g12["queue_start"] is not None and g12["flag"] == "red" and g12["pct"] == 110, str(g12["pct"]))

# =========================================================================== #
#  6. The pure pieces                                                          #
# =========================================================================== #
pb = sim.pour_burst(600, 160, 7.5, 60)
ok("pour_burst: 160 m³ ÷ 7.5 = 22 mixers (21.3 up), one every 7.5 min, the last at 12:37:30",
   pb["loads"] == 22 and pb["gap"] == 7.5 and pb["end"] == 757.5 and len(pb["times"]) == 22)
ok("pour_burst: an exact multiple is not one more (150 ÷ 7.5 = 20)", sim.pour_burst(600, 150, 7.5, 60)["loads"] == 20)
ok("next_service: before opening -> the opening; in a band -> its end; after the last open minute -> the same minute",
   sim.next_service([(420, 600), (660, 1020)], 300) == 420 and sim.next_service([(420, 600), (660, 1020)], 610) == 660
   and sim.next_service([(420, 600), (660, 1020)], 1100) == 1100)
ok("open_intervals takes each band off, splitting the window",
   sim.open_intervals((420, 1020), [(420, 600), (960, 1140)]) == [(600, 960)]
   and sim.open_intervals((300, 1020), [(420, 600)]) == [(300, 420), (600, 1020)]
   and sim.open_intervals((420, 1020), []) == [(420, 1020)])
ok("band_intervals splits a band past midnight at midnight (gate_hours' rule)",
   sim.band_intervals([{"from": "22:00", "to": "02:00"}]) == [(1320, 1440), (0, 120)])
ok("js_round / hhmm round halves up, as the example does", sim.js_round(2.5) == 3 and sim.hhmm(757.5) == "12:38" and sim.hhmm(0) == "00:00")
_w = sim.waiting_at([{"t": 1.0, "start": 5.0, "at": 1}, {"t": 2.0, "start": 9.0, "at": 2}, {"t": 3.0, "start": 3.0, "at": 3}], 3.0)
ok("waiting_at: at minute 3, the two that came at 1 and 2 (the one arriving at 3 is being checked in)",
   [a["at"] for a in _w] == [1, 2])
ok("mixer_m3: the app's mixer when the tenant has it, the first mixer typed, else 7.5",
   sim.mixer_m3(factors) == (7.5, sim.MIXER_NAME)
   and sim.mixer_m3({"vehicles": {"Mix 6": {"payload_m3": 6}}}) == (6.0, "Mix 6") and sim.mixer_m3({}) == (7.5, None))

# whole_loads
sh = [x * 1.0 for x in (2.5, 1.5, 3.0)]
wl = sim.whole_loads(sh, [["A"], ["B"], ["A"]], {"A": 5.5, "B": 1.5})
ok("whole_loads: the day's total is the month's average day rounded (7.0 -> 7), and a whole-number line stays",
   sum(wl["per_line"]) == 7 and wl["per_line"][2] == 3)
wl2 = sim.whole_loads([0.5, 0.5], [["A"], ["B"]], {"A": 0.5, "B": 0.5})
ok("whole_loads: a tie goes to the lower route number", list(wl2["per_line"]) == [1, 0] and wl2["exact"])
wl3 = sim.whole_loads([0.5, 0.5], [["A"], ["A"]], {"A": 1.0})
ok("whole_loads: 0.5 + 0.5 = 1.0 -> one up, the lower line", list(wl3["per_line"]) == [1, 0])
_big = [((i * 37) % 100) / 10.0 + 0.37 for i in range(40)]
_bt = [[f"G{i % 7}", f"G{(i * 3) % 7}"] for i in range(40)]
_bav = {f"G{j}": sum(_big[i] for i in range(40) for g in _bt[i] if g == f"G{j}") for j in range(7)}
wl4 = sim.whole_loads(_big, _bt, _bav, node_budget=2000)
ok("whole_loads on a very large month stops searching, says so, and still gives the right total",
   wl4["exact"] is False and sum(wl4["per_line"]) == sim.js_round(sum(_big))
   and all(p in (math.floor(s), math.floor(s) + 1) for p, s in zip(wl4["per_line"], _big)))
ok("whole_loads is the same twice (memoised and deterministic)",
   sim.whole_loads(_big, _bt, _bav, node_budget=2000) == wl4)
Dsmall = sim.day(9, acc_planner, factors=factors, working_days=WD)
ok("the same month gives the same day twice", [l["loads"] for l in Dsmall["lines"]] == EX_PER_LINE)

# =========================================================================== #
#  7. A team code: other teams' lines by route only                            #
# =========================================================================== #
acc_team = {"role": "submitter", "ipt": "IPT1", "label": "North Team"}   # what access resolves a team code to
Dteam = sim.day(9, acc_team, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR))
mine = [l for l in Dteam["lines"] if "loads" in l]
ok("⭐ a team code: its own lines in full, other teams' lines by route only (no loads, tonnes or section)",
   Dteam["scope"] == "team" and mine and all(l["team"] == "North Team" for l in mine)
   and all(set(l) >= {"route_id", "team"} and "loads" not in l and "section_id" not in l
           for l in Dteam["lines"] if l["team"] != "North Team"), str(acc_team))
ok("a team code: other teams' arrivals carry no line, only their route; the gate figures are the scheme's",
   all(a["line"] is None for a in Dteam["arrivals"] if a["kind"] != "pour"
       and Dteam["lines"][[l["route_id"] for l in Dteam["lines"]].index(a["route"])]["team"] != "North Team")
   and [g["arrivals"] for g in Dteam["gates"]] == [g["arrivals"] for g in D["gates"]]
   and any("shown by route only" in n for n in Dteam["notes"]))
access.set_current("planner123")

# =========================================================================== #
#  8. The Gate arrivals panel's busiest hour, and the endpoint                 #
# =========================================================================== #
access.set_current("planner123")
GA = main.gate_arrivals_month(9)
gab = {g["gate_id"]: g for g in GA["gates"]}
# 17 Oct 2026: the endpoint reads the STORED Config (no default typed: 08:00–17:00), so its busiest hours are the
# simulation's day on 08:00–17:00 — the same engine, the same day, read two ways
_D8off = sim.day(9, acc_planner, factors=factors_code, working_days=WD)
_busy_8 = {g["gate_id"]: (g["busiest"], g["busiest_hours"][0]) for g in _D8off["gates"]}
# 17 Oct 2026 (the review): pinned as figures, as the example's are — the same month on 08:00–17:00
ok("⭐ the busiest clock hour at every gate on the shipped 08:00–17:00 (lorries, first busiest hour), pinned",
   _busy_8 == {"G005": (15, 8), "G001": (12, 8), "G007": (9, 8), "G009": (9, 10), "G003": (7, 8), "G011": (5, 9),
               "G014": (5, 9), "G012": (4, 8), "G010": (4, 10), "G013": (3, 12), "G006": (2, 9)}, str(_busy_8))
ok("⭐ GET /api/gates/arrivals carries each gate's busiest hour from the simulation's day (no pour, 08:00–17:00)",
   all(g.get("busiest_hour") for g in GA["gates"])
   and {k: (v["busiest_hour"]["lorries"], v["busiest_hour"]["hour"]) for k, v in gab.items()}
   == {k: (n, f"{h:02d}:00") for k, (n, h) in _busy_8.items()}
   and all(v["busiest_hour"]["open_basis"] == "default" and v["busiest_hour"]["open_from"] == "08:00" for v in gab.values()),
   str({k: v.get("busiest_hour") for k, v in gab.items()}))
ok("…with what the gate can check in an hour (60 ÷ the check-in), none where no check-in is typed",
   gab["G007"]["busiest_hour"]["per_hour"] == 12.0 and gab["G005"]["busiest_hour"]["per_hour"] == 20.0
   and gab["G012"]["busiest_hour"]["per_hour"] is None)
ok("the panel's note says where the busiest hour comes from (the default gate hours where none are typed, no pour)",
   "Busiest hour" in GA["busiest_note"] and "(08:00–17:00 where none are typed)" in GA["busiest_note"]
   and "stood in" not in GA["busiest_note"] and "No pour" in GA["busiest_note"]
   and "312 whole loads" in GA["busiest_note"], GA["busiest_note"])
ok("the panel's own figures are untouched by the busiest hour",
   {g["gate_id"]: g["arrivals_per_day"] for g in GA["gates"]} == EX_PANEL)
_ga_mod = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
ok("gate_arrivals.arrivals() itself is unchanged: no busiest_hour inside the module's reply",
   all("busiest_hour" not in g for g in _ga_mod["gates"]) and "busiest_note" not in _ga_mod)

E = main.sim_day(month=9, **POUR)
ok("⭐ GET /api/sim/day returns sim.day's reply (the example's pour: 646 arrivals, 22 mixers)",
   E["gate_arrivals"] == 646 and E["pour"]["loads"] == 22 and all("coords" not in v for v in E["legs"].values()))
E2 = main.sim_day(month=9, legs="1", **POUR)
ok("legs=1 adds each route's line", any("coords" in v for v in E2["legs"].values()))
e5 = raises(lambda: main.sim_day(month=9, hours=["G001=18:00-07:00"]))
ok("⭐ 400 in words for a window past midnight", getattr(e5, "status_code", None) == 400 and "past midnight" in e5.detail)
e6 = raises(lambda: main.sim_day(month=0))
ok("400 for a month outside the programme", getattr(e6, "status_code", None) == 400)
access.set_current(None)
e7 = raises(lambda: main.sim_day(month=9))
ok("🔴 401 without a sign-in (staff only, never public)", getattr(e7, "status_code", None) == 401)
access.set_current("planner123")
Eoct = main.sim_day(month=10)
ok("a month with no approved lines: no loads, no gates, nothing refused",
   Eoct["loads"] == 0 and Eoct["gates"] == [] and Eoct["arrivals"] == [])

# =========================================================================== #
#  8b. 17 Oct 2026: the default gate hours (08:00–17:00) and the gates' shut windows                              #
# =========================================================================== #
D8 = sim.day(9, acc_planner, factors=factors_code, working_days=WD, scenario=sim.scenario_from_query(**POUR))
b8 = {g["gate_id"]: g for g in D8["gates"]}
ok("⭐ the user's default: with none typed on Config, every gate with no hours of its own is open 08:00–17:00, said so",
   all(g["open_basis"] == "default" and g["open_from"] == "08:00" and g["open_to"] == "17:00"
       and g["open_minutes"] == 540 for g in D8["gates"]) and D8["default_hours"] == {"from": "08:00", "to": "17:00"}
   and any("08:00–17:00, the default gate hours" in n for n in D8["notes"]), str(D8["notes"]))
_reg8 = [a for a in D8["arrivals"] if a["kind"] != "pour"]
ok("⭐ the user, 17 Oct: no lorry arrives before its gate opens at 08:00, and the first set off before 08:00 (each "
   "leaves its route's drive time earlier)",
   _reg8 and min(a["at"] for a in _reg8) >= 480 and min(a["depart"] for a in _reg8) < 480
   and all(a["depart"] < a["at"] for a in _reg8), f"{hm(min(a['at'] for a in _reg8))} {hm(min(a['depart'] for a in _reg8))}")
ok("the playback runs from the first lorry setting off: 06:30–17:30", D8["window"]["from"] == "06:30"
   and D8["window"]["to"] == "17:30", str(D8["window"]))
g7d = b8["G007"]
ok("⭐ the example's pour on the 9-hour default: 101 arrivals, 94 % of what Harborough can check in, amber 'Queue likely' "
   "on the Dashboard rule, up to 14 waiting at 12:38, 2,765 lorry-minutes lost, the longest wait 67 min",
   g7d["arrivals"] == 101 and g7d["pct"] == 94 and g7d["flag"] == "amber" and g7d["status_word"] == "Queue likely"
   and g7d["most_waiting"] == 14 and hm(g7d["most_at"]) == "12:38" and sim.js_round(g7d["minutes_lost"]) == 2765
   and sim.js_round(g7d["longest_wait"]) == 67,
   str({k: g7d[k] for k in ("arrivals", "pct", "flag", "most_waiting", "minutes_lost", "longest_wait")}))
_D8b = sim.day(9, acc_planner, factors=factors_code, working_days=WD, scenario=sim.scenario_from_query(bands="on"))
ok("the example bands on the shipped default: 540 − 08:00–10:00 − 16:00–17:00 = 360 open minutes at every gate",
   all(g["open_minutes"] == 360 for g in _D8b["gates"]), str({g["gate_id"]: g["open_minutes"] for g in _D8b["gates"]}))
ok("a day with no lorry plays the scheme's own default gate hours (07:00–17:00 set here; 08:00–17:00 shipped)",
   sim.day(10, acc_planner, factors=factors, working_days=WD)["window"]["from"] == "07:00"
   and sim.day(10, acc_planner, factors=factors_code, working_days=WD)["window"] == {"start": 480, "end": 1020, "from": "08:00", "to": "17:00"})
_Dp7 = sim.day(9, acc_planner, factors=factors_code, working_days=WD, scenario=sim.scenario_from_query(**dict(POUR, pour_start="07:00")))
ok("⭐ a pour typed for 07:00 at a gate opening 08:00: 8 of its 22 mixers come while it is shut, they wait, and the notes say so",
   _Dp7["pour"]["while_shut"] == 8
   and any(n.startswith("8 of the pour's 22 mixers come while Harborough Compound is shut") for n in _Dp7["notes"])
   and all(a["start"] >= 480 for a in _Dp7["arrivals"] if a["gate"] == "G007"), str(_Dp7["notes"]))
ok("the example pour at 10:00 comes while the gate is open: no such note", D8["pour"]["while_shut"] == 0
   and not any("mixers come while" in n for n in D8["notes"]))
ok("pour off on the default: still no lorry waits anywhere (the busiest gate is under 100 %)",
   all(g["queue_start"] is None for g in _D8off["gates"]) and max(g["pct"] or 0 for g in _D8off["gates"]) < 100)

# a gate's shut windows (typed on the gate, Data → Locations)
_w = gates.update_gate("G007", shut_windows=[{"from": "12:00", "to": "12:30"}])
ok("a shut window is stored on the gate and read back as typed", _w.get("shut_windows") == [{"from": "12:00", "to": "12:30"}],
   str(_w))
Ds = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(**POUR))
s7 = {g["gate_id"]: g for g in Ds["gates"]}["G007"]
_q = [a for a in Ds["arrivals"] if a["gate"] == "G007"]
ok("⭐ Harborough shut 12:00–12:30: 570 open minutes of 07:00–17:00, two open intervals, the reply names the shut time",
   s7["open_minutes"] == 570 and s7["intervals"] == [[420, 720], [750, 1020]]
   and s7["shut_windows"] == [{"from": "12:00", "to": "12:30"}] and s7["shut_words"] == "12:00–12:30",
   str({k: s7[k] for k in ("open_minutes", "intervals", "shut_words")}))
ok("the pour's four mixers due inside 12:00–12:30 are counted as coming while the gate is shut", Ds["pour"]["while_shut"] == 4)
ok("⭐ no regular lorry is placed inside the shut time, and no check-in starts inside it (a mixer that comes then waits)",
   not any(720 <= a["at"] < 750 for a in _q if a["kind"] != "pour") and not any(720 <= a["start"] < 750 for a in _q)
   and any(a["kind"] == "pour" and 720 <= a["at"] < 750 and a["start"] >= 750 for a in _q))
ok("the other gates are untouched (600 open minutes each) and the notes say shut times are taken off",
   all(g["open_minutes"] == 600 for g in Ds["gates"] if g["gate_id"] != "G007")
   and any("shut times are taken off" in n for n in Ds["notes"]))
Dsh = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(hours=["G007=06:00-18:00"]))
ok("the shut time holds under the scenario's hours (they are the gate's agreements, not a what-if)",
   {g["gate_id"]: g for g in Dsh["gates"]}["G007"]["intervals"] == [[360, 720], [750, 1080]])
gates.update_gate("G007", shut_windows=[{"from": "08:30", "to": "09:15"}, {"from": "12:00", "to": "12:30"}])
Dsb = sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bands="on"))
ok("⭐ a shut time inside a no-delivery band counts once: 07:00–17:00 less the bands 07–10 and 16–19 and 12:00–12:30 = 330 "
   "(08:30–09:15 is inside 07:00–10:00)", {g["gate_id"]: g for g in Dsb["gates"]}["G007"]["open_minutes"] == 330)
_gap = gate_arrivals.arrivals(9, acc_planner, factors=factors, working_days=WD)
_g7p = {g["gate_id"]: g for g in _gap["gates"]}["G007"]
Dsn = sim.day(9, acc_planner, factors=factors, working_days=WD)
ok("⭐ one rule: the Dashboard's Gate arrivals takes the same minutes off as the simulation (525 = 600 − 45 − 30)",
   _g7p["open_minutes"] == 525 == {g["gate_id"]: g for g in Dsn["gates"]}["G007"]["open_minutes"]
   and _g7p["shut_minutes"] == 75 and _g7p["shut_words"] == "08:30–09:15 and 12:00–12:30", str(_g7p["open_minutes"]))
ok("the busiest hour's note says the shut times are taken off",
   "its shut times taken off" in sim.busiest(9, acc_planner, factors, WD, _gap)["note"])
# a gate whose shut times and the bands leave it no open time (the gate write cannot see a scenario's bands)
gates.update_gate("G007", shut_windows=[{"from": "10:00", "to": "16:00"}])
_Dz = sim.day(9, acc_planner, factors=factors_code, working_days=WD, scenario=sim.scenario_from_query(bands="on"))
_z7 = {g["gate_id"]: g for g in _Dz["gates"]}["G007"]
ok("⭐ no open time left (08:00–17:00 less the bands and 10:00–16:00): none of Harborough's lorries is placed, and a note "
   "says so naming the gate", _z7["open_minutes"] == 0 and _z7["arrivals"] == 0 and _z7["unplaced"] > 0 and any(n.startswith("Harborough Compound, Station Road entrance (in): the no-delivery bands and its "
                                                "shut times leave no open time, so its") for n in _Dz["notes"]), str(_Dz["notes"]))
gates.update_gate("G007", shut_windows=[])
# a gate closing at midnight is a same-day window (the Dashboard counted it; the simulation used to leave it out)
gates.update_gate("G012", open_from="16:00", open_to="00:00")
_g12m = {g["gate_id"]: g for g in sim.day(9, acc_planner, factors=factors, working_days=WD)["gates"]}["G012"]
ok("⭐ a gate open 16:00–00:00 is simulated 16:00 to midnight (480 open minutes), not left out as past midnight",
   _g12m["open_basis"] == "gate" and _g12m["open_minutes"] == 480 and _g12m["intervals"] == [[960, 1440]], str(_g12m)[:200])
gates.update_gate("G012", open_from="", open_to="")
gates.update_gate("G007", shut_windows=[])
ok("clearing the shut times puts Harborough back to the whole day", gates.get_gate("G007")["shut_windows"] == []
   and {g["gate_id"]: g for g in sim.day(9, acc_planner, factors=factors, working_days=WD)["gates"]}["G007"]["open_minutes"] == 600)

# =========================================================================== #
#  9. Nothing written                                                          #
# =========================================================================== #
_tables = ["forecasts", "routes", "locations", "location_gates", "zones", "route_geometry", "config"]
_before = {t: db.query(f"SELECT COUNT(*) AS n FROM {t} WHERE tenant_id = ?", (db.current_tenant(),))[0]["n"] for t in _tables}
sim.day(9, acc_planner, factors=factors, working_days=WD, scenario=sim.scenario_from_query(bands="on", **POUR), send_lines=True)
_after = {t: db.query(f"SELECT COUNT(*) AS n FROM {t} WHERE tenant_id = ?", (db.current_tenant(),))[0]["n"] for t in _tables}
ok("🔴 a simulation writes nothing (D86): every table's row count is the same after it", _before == _after, str(_after))

# =========================================================================== #
#  10. The fixture for the frontend harnesses (S7): the example's day with the pour, without the routes' lines    #
#      Written LAST and only from a clean run, LF on disk; the same every run (no date in it).                    #
# =========================================================================== #
_fix_path = os.path.join(HERE, "fixtures", "sim_day.json")
if not FAIL:
    with open(_fix_path, "w", encoding="utf-8", newline="\n") as _fh:
        _fh.write(json.dumps(D_nolines, ensure_ascii=False, separators=(",", ":")) + "\n")
_fx = json.load(open(_fix_path, encoding="utf-8")) if os.path.exists(_fix_path) else {}
ok("the fixture backend/tests/fixtures/sim_day.json is the example's day with the pour (646 arrivals, 22 mixers, no lines)",
   _fx.get("gate_arrivals") == 646 and (_fx.get("pour") or {}).get("loads") == 22
   and all("coords" not in v for v in (_fx.get("legs") or {}).values()) and b"\r\n" not in open(_fix_path, "rb").read())

print()
for f in FAIL:
    print("  FAIL ", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
