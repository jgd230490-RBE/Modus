"""
Busy-hour times (29 Oct 2026, task 0f-2; John's yes to notes/busy-hours-0f-mockup-1028, cards 1-4, and "7 hours, 602
calls"). An admin's run works out each route's drive times for a lorry setting off at 06:00-18:00 on the bake's Tuesday,
asked as the bake asks, each HERE option named by the stored option with the same line. The Routes table shows the cycle
at 08:00, 12:00 and 17:00 with the quicker option green and bold, 0d's busy-hours line gains the time difference, and
the collision evidence gets a cycle-by-hour chart and table. Never in the plan's figures.

WHAT IS ASSERTED: the plan (calls before the run, no call); the run (the bake's question at each hour, one call a leg
an hour, every option named or "not stored", the stored lines untouched, a second run idle, a refused call kept as a
row, the time budget); the read (only rows whose stored line is still the one matched; a re-route retires them); the
cycle at an hour = both legs + the turnaround; other lorries on the same road scaled and saying so; the plan's own
figures unchanged; the evidence block, its sentence and its PDF drawing; the page's columns, marking, note, busy-hours
words and the button; the registrations; the guides.

WHAT THIS DOES NOT PROVE: HERE is never called (stubbed); the PDF is drawn on a bare canvas, not the whole sheet; the
XLSX is checked in source only; no Postgres branch runs; the page is not mounted here (a browser check is separate).

Run:  python backend/tests/test_hour_times.py
"""
import json
import re
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_gate_access.py ---------------------------------
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


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


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
_resp.Response = object
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_hourtimes_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("TENANT_ID", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import haul  # noqa: E402
import zones  # noqa: E402
import here_routing  # noqa: E402
import limits  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def north(p, m):
    return [p[0], round(p[1] + m / 111320.0, 7)]


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture: a quarry (one gate both ways) and a one-way site (in by the north, #
#  out by the south), each gate 35 m in from its road, and one permanent       #
#  routing closure well away from both (so the avoid areas are not empty)      #
# =========================================================================== #
ART = "Artic Tipper (44t)"
LAT = 52.5
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
RQ = [-1.0, LAT + 0.002]
GQ = north(RQ, -35)
RIN = [-0.9, LAT + 0.002]
GIN = north(RIN, -35)
ROUT = [-0.9, LAT - 0.002]
GOUT = north(ROUT, 35)


def haul_zone(name, coords, **kw):
    z = zones.create_zone(name, {"type": "LineString", "coordinates": coords}, kind=zones.HAUL_KIND, affects_routing=True,
                          speed_kph=kw.pop("speed", 10), haul_mode="splice", **kw)
    assert "error" not in z, z
    return z["id"]


ZQ = haul_zone("Quarry access road", [RQ, GQ])
ZIN = haul_zone("Site in access road", [GIN, RIN])
ZOUT = haul_zone("Site out access road", [ROUT, GOUT])
CLOSURE = zones.create_zone("Bridge closure", {"type": "Polygon", "coordinates": [[[-0.5, 52.0], [-0.5, 52.01],
                                                                                    [-0.49, 52.01], [-0.5, 52.0]]]},
                            kind="closure", affects_routing=True)
gq = gates.create_gate("L1", "Quarry gate", GQ[1], GQ[0], direction="both", is_default=True, access_zone_id=ZQ)
gin = gates.create_gate("L2", "North gate (in)", GIN[1], GIN[0], direction="access", is_default=True, access_zone_id=ZIN)
gout = gates.create_gate("L2", "South gate (out)", GOUT[1], GOUT[0], direction="egress", is_default=True,
                         access_zone_id=ZOUT)
AVOID, ZTAG = network.active_avoid()
ok("fixture: the permanent closure is an avoid area the bake and the check both send", len(AVOID) == 1 and ZTAG,
   f"{AVOID} {ZTAG}")


import hour_times  # noqa: E402
import export  # noqa: E402

# =========================================================================== #
#  HERE, faked: three options, each its own line; the hour moves the minutes;  #
#  at 08:00 the second option overtakes the first; at 17:00 HERE's second road  #
#  is one the bake never stored                                                 #
# =========================================================================== #
CALLS = []
FACTOR = {6: 0.90, 8: 1.20, 9: 1.10, 12: 1.00, 15: 1.02, 17: 1.15, 18: 1.05}
SC = {"boom": False}


def _hour(dep):
    if not dep or dep == here_routing.TIME_ANY:
        return None
    return int(str(dep)[11:13])


def _fake_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, **kw):
    dep = kw.get("departure_time")
    CALLS.append({"o": (round(o_lat, 7), round(o_lon, 7)), "d": (round(d_lat, 7), round(d_lon, 7)), "dep": dep,
                  "alternatives": kw.get("alternatives", 1), "laden": kw.get("laden", True), "profile": profile})
    if SC["boom"]:
        raise RuntimeError("HERE said 429")
    h = _hour(dep)
    f = FACTOR.get(h, 1.0) if h is not None else 1.0
    out = []
    for i in range(max(1, int(kw.get("alternatives") or 1))):
        bend = 0.01 * i + (0.007 if (h == 17 and i == 1) else 0.0)
        mins = (0.25 + 0.05 * i) * f
        if h == 8 and i == 1:
            mins = 0.27                       # the second option is quicker at 08:00
        out.append({"geometry": [[o_lon, o_lat], [(o_lon + d_lon) / 2, (o_lat + d_lat) / 2 + bend], [d_lon, d_lat]],
                    "distance_km": 10.0 + i, "duration_hr": round(mins, 4), "sections": []})
    return out


_real_routes, _real_conf = here_routing.routes, here_routing.configured
here_routing.routes = _fake_routes
here_routing.configured = lambda: True
FACT = conversions.load_factors()
TIP, FLAT = hour_times.PROFILE, "Artic Flatbed (44t)"
try:
    R = db.query("SELECT * FROM routes WHERE id = 'R1'")[0]
    L = {l["id"]: l for l in db.query("SELECT * FROM locations")}
    BAKE = {}
    for prof in (TIP, FLAT):
        for leg in network.LEGS:
            CALLS.clear()
            n, e = network._bake_leg(R, L["L1"], L["L2"], prof, leg, FACT)
            BAKE[(prof, leg)] = list(CALLS)
    ok("fixture: the bake stored three options a leg for the tipper and the flatbed", all(len(v) == 1 for v in BAKE.values()))
    DAY = here_routing.bake_departure_time()[:10]
    ok("bake_departure_time(hour=) is the same Tuesday at that hour",
       here_routing.bake_departure_time(hour="17:00") == here_routing.bake_departure_time().replace("T10:00", "T17:00"))

    # ---- 1. the plan: what a run costs, no call ---------------------------------------------------------------------
    CALLS.clear()
    P = hour_times.plan()
    ok("⭐ 1. the plan: 1 route, 2 legs, 7 hours, 14 calls (one a leg an hour between two access roads), no HERE call",
       (P["routes"], P["legs"], len(P["hours"]), P["here_calls"]) == (1, 2, 7, 14) and not CALLS and P["worked_out"] is None, str(P))
    ok("1. the hours are 06, 08, 09, 12, 15, 17, 18; the screen shows 08, 12, 17",
       hour_times.HOURS == ("06:00", "08:00", "09:00", "12:00", "15:00", "17:00", "18:00")
       and hour_times.SCREEN_HOURS == ("08:00", "12:00", "17:00"))

    # ---- 2. the run ---------------------------------------------------------------------------------------------------
    BEFORE = json.dumps(db.query("SELECT * FROM route_geometry ORDER BY vehicle_profile, leg, alt_index"), default=str)
    CALLS.clear()
    B1 = hour_times.bake_batch(limit=30)
    ok("⭐ 2. one batch works out all 14 (route, leg, hour) times; nothing left", (B1["baked"], B1["errors"], B1["remaining"],
       B1["here_calls"]) == (14, 0, 0, 14) and len(CALLS) == 14, str(B1))
    ok("⭐ 2. every call asks the bake's question (its ends, 3 options, laden flag) at that hour on the bake's Tuesday",
       all(c["dep"][:10] == DAY and c["alternatives"] == 3 and c["profile"] == TIP for c in CALLS)
       and sorted({c["dep"][11:16] for c in CALLS}) == list(hour_times.HOURS)
       and all((c["o"], c["d"], c["laden"]) == (BAKE[(TIP, "loaded")][0]["o"], BAKE[(TIP, "loaded")][0]["d"], True)
               for c in CALLS if c["laden"])
       and all((c["o"], c["d"]) == (BAKE[(TIP, "return")][0]["o"], BAKE[(TIP, "return")][0]["d"])
               for c in CALLS if not c["laden"]))
    ok("⭐ 2. the run never touches the stored lines (the plan's figures stay the pinned bake)",
       json.dumps(db.query("SELECT * FROM route_geometry ORDER BY vehicle_profile, leg, alt_index"), default=str) == BEFORE)
    rows = db.query("SELECT * FROM route_hour_times ORDER BY leg, hour, rank")
    ok("2. three rows a (leg, hour), each with its fingerprint, km, time and the day asked for",
       len(rows) == 42 and all(r["fingerprint"] and r["distance_km"] and r["depart_at"][:10] == DAY for r in rows))
    a17 = [r["alt_index"] for r in rows if r["leg"] == "loaded" and r["hour"] == "17:00"]
    a08 = [r["alt_index"] for r in rows if r["leg"] == "loaded" and r["hour"] == "08:00"]
    ok("⭐ 2. each option is named by the stored option with the same line; 17:00's second road is not stored (None)",
       a08 == [0, 1, 2] and a17 == [0, None, 2], f"{a08} {a17}")
    CALLS.clear()
    ok("2. a second batch has nothing to do and calls nothing", hour_times.bake_batch()["attempted"] == 0 and not CALLS)
    ok("2. the plan says when they were worked out", (hour_times.plan()["worked_out"] or {}).get("day") == DAY)

    # ---- 3. the read: only rows whose stored line is still the one matched --------------------------------------------
    T = hour_times.times_for("R1")
    ok("⭐ 3. times_for: the tipper's three options on both legs, at every hour except the road not stored",
       set(T) == {TIP} and sorted(T[TIP]["loaded"]) == [0, 1, 2] and "17:00" not in T[TIP]["loaded"][1]
       and len(T[TIP]["loaded"][0]) == 7 and len(T[TIP]["loaded"][2]) == 7)
    A = hour_times.attach(network.route_analysis("R1"))
    t0 = next(x for x in A["rows"] if x["profile"] == TIP and x["alt_index"] == 0)
    t1 = next(x for x in A["rows"] if x["profile"] == TIP and x["alt_index"] == 1)
    exp = T[TIP]["loaded"][0]["08:00"] + T[TIP]["return"][0]["08:00"] + t0["turnaround_hr"]
    ok("⭐ 3. a row's cycle at an hour = both legs at that hour + its own turnaround", abs(t0["hours"]["08:00"] - exp) < 0.0006
       and t0["return_alt_used"] == 0, f"{t0['hours']['08:00']} {exp}")
    ok("3. at 08:00 the second option's cycle is the shorter; at 17:00 it has none (its road was not HERE's then)",
       t1["hours"]["08:00"] < t0["hours"]["08:00"] and t1["hours"]["17:00"] is None and t0["hours"]["17:00"] is not None)
    ok("⭐ 3. the plan's own figures are untouched (cycle, trips, CO2 as without the times)",
       all(x["cycle_hr"] == y["cycle_hr"] and x["trips_per_day"] == y["trips_per_day"] and x["co2_kg_per_trip"] == y["co2_kg_per_trip"]
           for x, y in zip(A["rows"], network.route_analysis("R1")["rows"])))
    f0 = next(x for x in A["rows"] if x["profile"] == FLAT and x["alt_index"] == 0)
    expf = (f0["loaded_hr"] * T[TIP]["loaded"][0]["12:00"] / t0["loaded_hr"]
            + f0["return_hr"] * T[TIP]["return"][0]["12:00"] / t0["return_hr"] + f0["turnaround_hr"])
    ok("⭐ 3. another lorry type on the tipper's road is scaled by the tipper's hour-to-pinned ratio, and says so",
       f0["hours_scaled"] is True and abs(f0["hours"]["12:00"] - expf) < 0.0006 and t0["hours_scaled"] is False)
    ok("3. the answer says which hours and which lorry", A["hour_times"]["screen_hours"] == ["08:00", "12:00", "17:00"]
       and A["hour_times"]["profile"] == TIP and len(A["hour_times"]["hours"]) == 7)

    # ---- 4. the evidence block and its words --------------------------------------------------------------------------
    Q = hour_times.evidence_block("R1")
    k08 = Q["hours"].index("08:00")
    ok("⭐ 4. the evidence block: this route and its alternatives in minutes at every hour, the quicker one each hour",
       [s_["label"] for s_ in Q["series"]] == ["This route", "Alternative 1", "Alternative 2"]
       and Q["quicker"][k08] == 1 and Q["quicker"][0] == 0 and Q["series"][1]["minutes"][Q["hours"].index("17:00")] is None
       and Q["busy"] == ["08:00", "09:00", "17:00", "18:00"], str(Q["quicker"]))
    w = export.ce_cycle_words(Q)
    ok("4. the sentence names who is quicker when, and the gap at 08:00",
       w.startswith("The quicker option changes with the hour: this route at 06:00") and "Alternative 1 at 08:00" in w
       and "Alternative 1 takes" in w and "less at 08:00" in w, w)
    Q1 = {"hours": ["08:00", "12:00"], "series": [{"alt": 0, "label": "This route", "minutes": [100, 90]},
                                                  {"alt": 1, "label": "Alternative 1", "minutes": [123, 110]}],
          "quicker": [0, 0]}
    Q2 = {"hours": ["06:00", "08:00", "12:00"], "series": [{"alt": 0, "label": "This route", "minutes": [100, 120, 110]},
                                                           {"alt": 1, "label": "Alternative 1", "minutes": [None, 133, 125]}],
          "quicker": [None, 0, 0]}
    ok("4. ...and names the hours when only some had another option to compare",
       export.ce_cycle_words(Q2).startswith("This route is quicker at 08:00 and 12:00, the hours another option has a time."),
       export.ce_cycle_words(Q2))
    ok("4. an hour where only one option has a time marks nothing quicker (as the screen)",
       Q["quicker"][Q["hours"].index("17:00")] == 0 and all(
           (q is None) == (sum(1 for s_ in Q["series"] if s_["minutes"][k] is not None) < 2) for k, q in enumerate(Q["quicker"])))
    ok("4. ...and 'quicker at every hour tried' when one option always is", export.ce_cycle_words(Q1)
       == "This route is quicker at every hour tried. Alternative 1 takes 23 min longer at 08:00.", export.ce_cycle_words(Q1))
    from reportlab.pdfgen import canvas as _cv
    import io as _io
    _buf = _io.BytesIO(); _c = _cv.Canvas(_buf)
    _S = {"cycle_by_hour": Q, "route_id": "R1"}
    _para = lambda text, y, size=7.2, colour=None, width=None: y - 10
    y1 = export._ce_cycle_by_hour(_c, _S, 30, 700, 520, "Helvetica", "Helvetica-Bold", _para, lambda: 800, 64)
    ok("⭐ 4. the PDF block draws (chart, table, words) and moves the page down; nothing at all without the times",
       y1 < 560 and export._ce_cycle_by_hour(_c, {"cycle_by_hour": None}, 30, 700, 520, "Helvetica", "Helvetica-Bold",
                                             _para, lambda: 800, 64) == 700)

    # ---- 5. a re-route retires the times; a failed call is kept as a row; clear ----------------------------------------
    import time as _t
    _t.sleep(1.1)
    network._bake_leg(R, L["L1"], L["L2"], TIP, "loaded", FACT)
    T2 = hour_times.times_for("R1")
    ok("⭐ 5. re-routing a leg retires its times (the stored line is not the one they matched); the other leg keeps its",
       "loaded" not in (T2.get(TIP) or {}) and "return" in T2.get(TIP, {}), str(list((T2.get(TIP) or {}).keys())))
    hour_times.clear()
    ok("5. clear drops every time", not db.query("SELECT 1 FROM route_hour_times") and hour_times.times_for("R1") == {})
    SC["boom"] = True
    B3 = hour_times.bake_batch(limit=30)
    SC["boom"] = False
    ok("⭐ 5. a refused call is a row with its reason (rank -1), counted, and the run still finishes",
       (B3["baked"], B3["errors"], B3["remaining"]) == (0, 14, 0)
       and db.query("SELECT COUNT(*) AS n FROM route_hour_times WHERE rank = -1")[0]["n"] == 14
       and db.query("SELECT error FROM route_hour_times LIMIT 1")[0]["error"] == "HERE said 429"
       and hour_times.times_for("R1") == {} and hour_times.attach(network.route_analysis("R1"))["hour_times"] is None)
    hour_times.clear()
    B4 = hour_times.bake_batch(limit=30, budget_s=0)
    ok("5. a spent time budget still does one, and says how many are left", B4["attempted"] == 1 and B4["remaining"] == 13)
    hour_times.clear()
finally:
    here_routing.routes, here_routing.configured = _real_routes, _real_conf

# =========================================================================== #
#  6. Source: endpoints, the page, the registrations                           #
# =========================================================================== #
_m = read("backend/main.py")
ok("6. the analysis read carries the hours; the plan, clear and run are admin-only",
   "return hour_times.attach(network.route_analysis(" in _m
   and all(f'"/api/admin/hour-times/{x}"' in _m for x in ("plan", "clear", "bake"))
   and _m.split("def hour_times_bake(")[1].split("\n@app")[0].count("_check_admin(token)") == 1
   and "budget_s=network.BAKE_BUDGET_S" in _m.split("def hour_times_bake(")[1].split("\n@app")[0])
_fe = read("frontend/index.html")
_ra = _fe.split("function RouteAnalysis(")[1].split("\nfunction ")[0]
ok("⭐ 6. the Routes table: a column a screen hour, the quicker cell green and bold, the note under the table",
   "{hourCols.map(h => <th key={h} className={head} data-hour-col={h}>{h}</th>)}" in _ra
   and 'data-quick={q ? "1" : undefined}' in _ra and 'color: "var(--ok-text)", fontWeight: 700' in _ra
   and "= the cycle for a lorry setting off then on a weekday. Green, bold: the quicker option at" in _ra
   and "Other lorries scaled from the Artic Tipper." in _ra)
ok("6. a cell is marked quicker only where another option of the same lorry has a time at that hour",
   "data.rows.filter(x => x.profile === r.profile && x.hours && x.hours[h] != null).length > 1" in _ra)
ok("⭐ 6. 0d's busy-hours line gains the time difference at 08:00 and 17:00 (the tipper's)",
   "{busyGap(o.alt)}" in _ra and "a round trip at 08:00 and at 17:00." in _ra)
_dm = _fe.split("const hourBake = async")[1].split("const bulkBake = async")[0]
ok("⭐ 6. the button: admins only, its call count on it and in the question, clear then batches until none are left",
   "{`Busy-hour times · ${hourPlan.here_calls} calls`}" in _fe and "if(!canEdit) return;" in _fe
   and "routing calls. ` +" in _dm and "The plan's figures do not change." in _dm
   and "admin/hour-times/clear" in _dm and 'postRouteBatch(new URLSearchParams({ limit: "30" }), setRouteMsg, "hour-times/bake")' in _dm
   and "if(left >= last) throw" in _dm)
ok("6. the header's buttons wrap as whole buttons; the new one keeps its words on one line (card 2)",
   '<span className="flex items-center gap-2" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>' in _fe
   and 'data-hour-bake style={{ whiteSpace: "nowrap" }}' in _fe)
_shown = (re.findall(r"setRouteMsg\(`([^`]*)`\)", _dm) + re.findall(r"confirm\(`([^`]*)`", _dm)
          + re.findall(r"` It takes [^`]*`", _ra)
          + [_ra.split("data-hour-note>")[1].split("</p>")[0], "Busy-hour times · calls"])
ok("6. the words the screen shows name no supplier and no back end",
   len(_shown) >= 5 and not re.search(r"\bHERE\b|\bAPI\b|endpoint|server|token|\bbak(e|ed|ing)\b", " ".join(_shown)),
   str(_shown))
ok("6. the table is registered five times (schema, key, tenanted, package order, audit)",
   "route_hour_times" in db.TENANTED_TABLES and "route_hour_times" in db._TENANT_DDL and "route_hour_times" in db._TENANT_PK
   and "route_hour_times" in read("backend/tenant_package.py") and "route_hour_times" in read("backend/tests/test_tenant_audit.py"))
_x = read("backend/export.py")
ok("6. the evidence PDF draws the block after By time of day, and the XLSX puts the same cells on that sheet",
   "y = _ce_cycle_by_hour(c, S, m, y, cw, R, B, para, new_page, footer_h)" in _x
   and 'cell.fill = PatternFill("solid", fgColor="DCFCE7")' in _x and '"cycle_by_hour": _cycle_by_hour(route_id)' in read("backend/collisions.py"))
_ug, _tg = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
ok("6. the user guide says it in plain words; the technical guide has the detail",
   "<strong>Busy-hour times</strong> (admins, beside Route all)" in _ug and "The plan's own figures do not change." in _ug
   and 'id="t2-hour-times"' in _tg and "route_hour_times" in _tg)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
