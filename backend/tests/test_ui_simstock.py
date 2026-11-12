r"""
UI critique wave 1, branch claude/ui-fix-sim-stock (9 Nov 2026): the Simulation opens on the programme's busiest month and the
Stockpiles page on the pile with the earliest problem. Its own harness, so parallel UI branches never meet in parse_frontend.
Asserted: sim.busiest_month (the month with the most approved whole loads, the first on a tie, None with no approved line, a
Pending line not counted) and GET /api/sim/busiest-month; at source level the page's opening (the read before the first day, the
headline from the reply's own peak, the clock at it, the one line saying nothing queues with the busiest-day button, the labels),
the caveat said once, the holding area's plain words, the phone's tags only when flagged, the Stockpiles page's earliest-problem
pick, the tab dot and word, the one number format, and the two guides.
WHAT THIS DOES NOT PROVE: the drawing in a browser (checked in Chrome by hand, see the session note), Postgres, live figures.
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\Scripts\python backend/tests/test_ui_simstock.py
"""
import copy
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

TMP = tempfile.mkdtemp(prefix="rbe_uisimstock_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import config  # noqa: E402
import gates  # noqa: E402
import network  # noqa: E402
import holding  # noqa: E402
import limits  # noqa: E402
import sim  # noqa: E402
import sim_holding  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "simhold-admin-token"
TOK = "simhold-admin-token"
days.START_YEAR = main.START_YEAR

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
    limits.init_db()
    config.invalidate()
    config.seed_from_file(conversions)


PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())



PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


TIP = "Artic Tipper (44t)"
SMALL = "Small aggregate"


def seed():
    reset_db()
    access.set_current("planner123")
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (db.current_tenant(), "IPT1", "North Team", True))
    for lid, name, lt, role, lon, lat in (("L1", "Quarry", "Quarry", "origin", -0.90, 52.60), ("L2", "Site", "Site", "destination", -0.88, 52.65)):
        db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", (lid, name, lt, role, lat, lon))
    db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt, material_category) VALUES (?, ?, ?, ?, ?)", ("R1", "L1", "L2", "IPT1", SMALL))


def line(month, qty, status="Approved", disc="earthworks"):
    sec = "WS" + disc[:2]
    main.save_matrix_row(main.MatrixRow(route_id="R1", discipline=disc, section_id=sec, material_type=SMALL, material_description=None,
                                        vehicle_type=TIP, submitted_by="tester", unit="t", status="Pending",
                                        cells=[main.Cell(month_index=month, quantity=float(qty))], ipt="IPT1"))
    if status == "Approved":
        main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline=disc, section_id=sec)


seed()
factors = conversions.load_factors()
ok("1. no approved line: no busiest month", sim.busiest_month(factors) is None)
line(3, 4000)
line(5, 9000, disc="drainage")
line(7, 12000, status="Pending", disc="structures")      # a Pending line is not counted
b = sim.busiest_month(factors)
ok("1. the busiest month is the one with the most approved loads (May 2026, not the Pending July)", b and b["month_index"] == 5 and b["label"] == "May 2026" and b["loads"] > 0, str(b))
line(8, 9000, disc="surfacing")
b2 = sim.busiest_month(factors)
ok("1. a tie goes to the first month", b2["month_index"] == 5 and b2["loads"] == b["loads"], str(b2))
r = main.sim_busiest_month()
ok("1. the endpoint answers the same", r["busiest"]["month_index"] == 5, str(r))

# ---------------------------------------------------------------- source level
ROOT2 = ROOT
html = open(os.path.join(ROOT2, "frontend", "index.html"), encoding="utf-8").read()
i0 = html.index("function SimulationPage(")
i1 = html.index("function SimDashLine(")
sim_page = html[i0:i1]
ok("2. the Simulation reads the busiest month before its first day", "sim/busiest-month" in sim_page and "if(!ready) return;" in sim_page and "setMonth(b.month_index)" in sim_page)
ok("2. a failed read opens on this month as before", ".catch(() => { if(live) setReady(true); })" in sim_page)
ok("2. the headline comes first, from the reply's own peak, in the sentence the card drew",
   "simPeak(D, site)" in sim_page and "waiting at {peak.name} at {simHM(peak.at)}" in sim_page and "the busiest point of this day." in sim_page
   and sim_page.index('data-sim-head="queue"') < sim_page.index('data-sim-lead="1"'))
ok("2. no queue: one line says so and offers the busiest day", 'data-sim-head="none"' in sim_page and "Nothing queues on this day (" in sim_page
   and "Show the busiest day (" in sim_page and 'data-sim-busiest="1"' in sim_page)
ok("2. the clock opens at the busiest point", "startAt={peak ? peak.at : null}" in sim_page and "useState(() => (startAt != null" in html)
ok("2. the scale and the period are named apart", ">Scale</span>" in sim_page and "Which month <select" in sim_page and "Which week <select" in sim_page and "Which day <select" in sim_page)
peak_fn = html[html.index("function simPeak("):html.index("function simHoldWords(")]
ok("2. the peak is the most waiting at once, the earliest on a tie, and only a real queue", "(b.n - a.n) || (a.at - b.at)" in peak_fn and "k.n >= 1" in peak_fn)
ok("2. a site's gate in is named once (the site's station, not the gate row beside it)", "onSite.has(g.gate_id)" in peak_fn and "gate in" in peak_fn)
tbl = html[html.index("const SimTable"):html.index("function SimulationPage(")]
ok("3. the quarries' caveat is said once, in the table fold and on the phone",
   html.count("{SIM_OTHER_CUSTOMERS}") == 2 and "origin_share_note && <div" not in tbl)
# NARROWED 11 Nov 2026 (CLOCS card C-F5): the words also read the day's gates (whose lorries came), on the card and the phone
ok("3. the holding area reads in plain words: passed through, none waited", "passed through · none waited." in html and html.count("{simHoldWords(h, D)}") == 2 and "{simHoldWords(h)}" not in html and "held this day" not in html)
ok("3. the with-and-without table is folded unless someone waited", 'className="sim-hold-fold" open={!!h.most}' in html)
ok("3. the phone shows a tag only for a flagged gate or station",
   'g.flag === "red" || g.flag === "amber" ? <RowStatus word={simWord(g)}' in html and 'st.flag === "red" || st.flag === "amber" ? <RowStatus word={st.status_word}' in html)
ok("3. the Hours and check-in gate select stays inside its column", ".sim-hc .sim-lbl .ga-sel{flex:1 1 0;min-width:0;max-width:100%;}" in html)
sp_src = open(os.path.join(BACKEND, "sim.py"), encoding="utf-8").read()
ok("3. the server's holding note is the plain sentence, not the rule", "wait at {H['name']} and are called forward" in sp_src and "waiting at the gate, never into a shut gate.\"" not in sp_src)

st0 = html.index("function StockpilesPage(")
st1 = html.index("function AbnormalPage(")
stock = html[st0:st1]
ok("4. Stockpiles opens on the pile with the earliest problem", "firstProblem" in stock and "stockProblem(a).from < stockProblem(b).from" in stock and "|| firstProblem || stockList[0]" in stock)
ok("4. each tab with a problem carries a dot and a word", 'data-stock-tab-flag={pr.kind}' in stock and '"over" : "runs out"' in stock and "sp-dot-bad" in stock and "sp-dot-warn" in stock)
ok("4. the headline names how long it stays over", "Goes over capacity in the week of" in stock and "and stays over for" in stock and "stockOverWeeks(sp)" in stock)
ok("4. one number format: boxes show 11 000, typing is read with the spaces out",
   "const stockTxt =" in html and "const stockNum = (v) => numOr(String(v == null ? \"\" : v).replace(/\\s+/g, \"\"), NaN);" in html
   and "value={draft[k] ?? stockTxt(v)}" in stock and "defaultValue={stockTxt(v)}" in stock and "String(Math.round(v * 10) / 10)" not in stock)
ok("4. no raw number is parsed straight from a box", "numOr(v, NaN)" not in stock and "numOr(fill.qty, NaN)" not in stock and "numOr(count.qty, NaN)" not in stock)

ug = open(os.path.join(ROOT2, "frontend", "help", "index.html"), encoding="utf-8").read()
ok("5. the user guide says what the Simulation opens on", "opens on the programme&#39;s busiest month" in ug and "Show the busiest day</strong>" in ug and "Which month</strong>" in ug)
ok("5. the user guide says what Stockpiles opens on", "opens on the stockpile with the earliest problem" in ug and "<em>over 22 Mar 2027</em>" in ug)
tg = open(os.path.join(ROOT2, "frontend", "help", "technical", "index.html"), encoding="utf-8").read()
ok("5. the technical guide holds the endpoint", 'id="t1-sim-opening"' in tg and "/api/sim/busiest-month" in tg)

ok("3. the Now card and the gates are no taller than the map, a named scroll region (no empty hole under the map)",
   ".sim-side{max-height:max(360px,min(62vh,720px));overflow:auto;}" in html and 'className="sim-side kb-scroll" tabIndex={0} role="region" aria-label="Now and gates"' in html)

# ---- 10 Nov 2026: how saving is shown on Stockpiles (the mockup John approved, "Yes to all three")
ok("6. planned use says where it stands: not saved yet / saved, beside the boxes",
   'data-stock-plan-state={dirty ? "dirty" : savedPlan ? "saved" : "none"}' in stock and "Not saved yet: leave the box to save" in stock
   and "setSavedPlan(`Saved: " in stock and "`✓ ${savedPlan}`" in stock)
ok("6. a changed box carries an amber ring until it is saved", 'draft[k] !== undefined ? { borderColor: "#D97706"' in stock)
ok("6. the false footer 'Saves as you type.' is gone, and the success toast is gone (failures still speak at the top)",
   "Saves as you type" not in stock and 'then(() => { setNote(null); setTick(t => t + 1); return true; })' in stock and 'say(false, errSay(what, e))' in stock)
ok("6. the stock count is its own box that says it saves only on the button; the button is grey until a figure is typed; a line names what was saved",
   'data-stock-count-box="1"' in stock and "Saved only when you press Save count" in stock
   and 'disabled={String(count.qty).trim() === "" || isNaN(stockNum(count.qty))}' in stock and 'data-stock-count-saved="1"' in stock
   and "setSavedCount(`Saved: " in stock)
ok("6. the saved lines clear when another stockpile is picked", 'setPick(x.location_id); setSavedPlan(""); setSavedCount("");' in stock)
ok("6. the user guide says how saving is shown", "<em>Not saved yet</em>" in ug and "press <strong>Save count</strong>" in ug)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
