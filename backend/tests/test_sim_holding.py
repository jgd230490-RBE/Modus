"""
Vehicle holding areas in the Simulation (29 Oct 2026, task 3c, PR 2): backend/sim_holding.py and sim.day()'s holding
blocks. A small fictional scheme: a quarry, a works site (a gate in with a 3-minute check-in, a gate out, a tipping
face, one spoil bay at 10 minutes), a tip, a second quarry whose line to the site does NOT pass the holding area, and
the holding area on the straight quarry -> site line with its own entrance gate. Lines for Sep 2026: stone in, a big
muck-away out (the spoil bay has more work than the gate's open day), stone from the far quarry.
Asserted: the invariant (the holding area off, or every lorry type exempt, gives the plain day to the digit); the rule
from the reply's own arrivals (called after arriving, the gate reached after the run from the holding area, never into
a shut gate, at most 2 waiting at the gate at any call, at most N on the way to a bay); the figures; the scenario
what-ifs and their refusals; the line that does not pass it (drawn straight, said); the legs' mark for the drawing; the
bay-over-its-day sentence; the endpoint.
WHAT THIS DOES NOT PROVE: the drawing (PR 3), the demo's own figures, Postgres, the HTTP layer (stubbed).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_sim_holding.py
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

TMP = tempfile.mkdtemp(prefix="rbe_simhold_")
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


def raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


# =========================================================================== #
#  0. The scheme                                                                #
# =========================================================================== #
TIP = "Artic Tipper (44t)"
SMALL, EARTH, BALLAST = "Small aggregate", "Earthworks / soil", "Large aggregate / ballast"
GQ, GA, GB, GT, GP = (-0.901, 52.601), (-0.8803, 52.6535), (-0.8835, 52.6525), (-0.801, 52.521), (-0.861, 52.741)
HG = ((GQ[0] + GA[0]) / 2, (GQ[1] + GA[1]) / 2)
NODES = [("L1", "Brook Quarry", "Quarry", "origin", -0.90, 52.60), ("L2", "Viaduct site", "Site", "destination", -0.8810, 52.6540),
         ("L3", "Inert tip", "Landfill", "destination", -0.80, 52.52), ("L4", "Ridge Quarry", "Quarry", "origin", -0.86, 52.74)]
GATES = [("GQ", "Pit gate", "L1", "both", True, 3, *GQ), ("GA", "Lane gate (in)", "L2", "access", True, 3, *GA),
         ("GB", "Lane gate (out)", "L2", "egress", False, None, *GB), ("GT", "Weighbridge", "L3", "both", True, 4, *GT),
         ("GP", "Quarry gate", "L4", "both", True, 3, *GP)]
ROUTES = [("R1", "L1", "L2", "GQ", "GA", SMALL), ("R2", "L2", "L3", "GB", "GT", EARTH), ("R3", "L4", "L2", "GP", "GA", BALLAST)]
LINES = [("R1", 8800, SMALL), ("R2", 38000, EARTH), ("R3", 6100, BALLAST)]


def km(a, b):
    return sim.metres(list(a), list(b)) / 1000.0


def store(rid, profile, leg, pts, alt=0):
    dist = sum(km(a, b) for a, b in zip(pts, pts[1:]))
    network._upsert_geom(rid, profile, json.dumps([list(p) for p in pts]), round(dist, 3), round(dist / 40.0, 4), None,
                         leg=leg, alt_index=alt, zones_applied="", haul_zones="")
    return dist


def seed():
    reset_db()
    access.set_current("planner123")
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (db.current_tenant(), "IPT1", "North Team", True))
    for lid, name, lt, role, lon, lat in NODES:
        db.execute("INSERT INTO locations (id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", (lid, name, lt, role, lat, lon))
    for gid, name, loc, d, dflt, sm, lon, lat in GATES:
        r = gates.create_gate(loc, name, lat, lon, direction=d, safety_minutes=sm, is_default=dflt, gate_id=gid)
        assert not r.get("error"), r
    for rid, o, d, og, dg, mat in ROUTES:
        db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt, material_category) VALUES (?, ?, ?, ?, ?)", (rid, o, d, "IPT1", mat))
        r = gates.set_route_gates(rid, origin_gate_id=og, dest_gate_id=dg, origin_given=True, dest_given=True)
        assert not r.get("error"), r
    for rid, t, mat in LINES:
        main.save_matrix_row(main.MatrixRow(
            route_id=rid, discipline="earthworks", section_id="WS1", material_type=mat,
            material_description=None, vehicle_type=TIP, submitted_by="tester", unit="t", status="Pending",
            cells=[main.Cell(month_index=9, quantity=float(t))], ipt="IPT1"))
        main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id="WS1")
    for name, act, mats, mins, bays, pt in (("Tipping face", "unload", [SMALL, BALLAST], 4, 1, (-0.8822, 52.6548)),
                                           ("Spoil loading", "load", [EARTH], 10, 1, (-0.8840, 52.6555))):
        r = main.create_site_area(main.SiteAreaIn(location_id="L2", name=name, activity=act, materials=mats, service_minutes=mins, bays=bays,
                                                  geometry={"type": "Point", "coordinates": list(pt)}), token=TOK)
        assert not r.get("error"), r
    store("R1", TIP, "loaded", [GQ, HG, GA])
    store("R1", TIP, "return", [GA, HG, GQ])
    store("R2", TIP, "loaded", [GB, GT])
    store("R2", TIP, "return", [GT, HG, GA])
    store("R3", TIP, "loaded", [GP, GA])
    store("R3", TIP, "return", [GA, GP])


seed()
factors = conversions.load_factors()
WD = main._working_days(factors)
acc = access.current()


def day(**kw):
    sc = sim.scenario_from_query(**{k: v for k, v in kw.items() if k in ("holding", "holding_call", "holding_spaces", "bands", "hours")})
    return sim.day(9, acc, factors=factors, working_days=WD, scenario=sc, send_lines=kw.get("legs", False))


def figures(D):
    """The figures a holding area may move, stripped of the keys it adds — for the invariant."""
    g = [{k: v for k, v in x.items() if k not in ("held",)} for x in D["gates"]]
    s = copy.deepcopy(D["sites"])
    a = [{k: v for k, v in x.items() if k != "held"} for x in D["arrivals"]]
    return json.dumps({"gates": g, "sites": s, "arrivals": a}, sort_keys=True, default=str)


# =========================================================================== #
#  1. Source level, and the plain day                                           #
# =========================================================================== #
src = open(os.path.join(BACKEND, "sim_holding.py"), encoding="utf-8").read()
ok("⭐ sim_holding.py is pure: no SQL, no db", "import db" not in src and not re.search(r"\b(INSERT|UPDATE|DELETE|SELECT)\b", src))
ok("1. the gate lane rule is one number, 2", sim_holding.GATE_LANE == 2)
D_plain = day()
ok("1. no holding area yet: the reply says so and runs as before", D_plain["holding"] == [] and D_plain["holding_on"] is True
   and all(a.get("held") is None for a in D_plain["arrivals"]))
ga0 = next(g for g in D_plain["gates"] if g["gate_id"] == "GA")
spoil0 = next(st for s in D_plain["sites"] for st in s["stations"] if st["name"] == "Spoil loading")
ok("1. the plain day queues at the one spoil bay (the story this harness needs)", spoil0["most_waiting"] >= 3 and spoil0["minutes_lost"] > 100, str(spoil0))

# the holding area, serving the site
h = main.create_location(main.LocationIn(name="Lane holding area", role="both", lat=HG[1], lon=HG[0], loc_type="Holding area",
                                         holding_spaces=12, holding_call=2), token=TOK)
H1 = h["id"]
gates.create_gate(H1, "Lane entrance", HG[1], HG[0], direction="both", safety_minutes=None, is_default=True, gate_id="GH",
                  open_from="07:00", open_to="20:30")
L2 = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}["L2"]
main.update_location("L2", main.LocationIn(name=L2["name"], role="destination", lat=L2["lat"], lon=L2["lon"], loc_type="Site", holding_id=H1), token=TOK)

# =========================================================================== #
#  2. The invariant                                                             #
# =========================================================================== #
D_off = day(holding="off")
ok("⭐ 2. the holding area switched off: every gate, station and arrival figure is the plain day's to the digit",
   figures(D_off) == figures(D_plain) and D_off["holding_on"] is False and len(D_off["holding"]) == 1 and D_off["holding"][0]["held"] == 0)
holding.set_holding(H1, {"holding_exempt"}, exempt=[TIP])
D_ex = day()
ok("⭐ 2. every lorry type exempt: the one loop runs the gates and stations and gives the plain day to the digit",
   figures(D_ex) == figures(D_plain) and D_ex["holding"][0]["held"] == 0, str(D_ex["holding"][0])[:200])
holding.set_holding(H1, {"holding_exempt"}, exempt=None)

# =========================================================================== #
#  3. The day with the holding area                                             #
# =========================================================================== #
D = day(legs=True)
Hf = D["holding"][0]
ga = next(g for g in D["gates"] if g["gate_id"] == "GA")
line_of = {l["line"]: l for l in D["lines"]}
loads = {l["route_id"]: l["loads"] for l in D["lines"]}
expect_held = loads["R1"] + loads["R2"] + loads["R3"]           # R1 laden in, R2's empty lorry to load, R3 laden in (straight)
ok("3. ⭐ every tipper for the site is held once: R1's deliveries, R2's empty lorries coming to load, R3's deliveries",
   Hf["held"] == expect_held and sum(1 for a in D["arrivals"] if a.get("held")) == expect_held, str((Hf["held"], loads)))
ok("3. the block: id, name, the site served, spaces 12, called forward 2, the mixers exempt by label, its entrance",
   Hf["id"] == H1 and Hf["name"] == "Lane holding area" and [s["id"] for s in Hf["served"]] == ["L2"] and Hf["spaces"] == 12
   and Hf["call"] == 2 and all("mixer" in x.lower() for x in Hf["exempt_labels"]) and Hf["gate_name"] == "Lane entrance"
   and Hf["on"] is True and Hf["gate_lane"] == 2, str(Hf)[:300])
ok("3. ⭐ every held lorry was called forward and reached the gate (the check)",
   D["checks"]["held_all_called"] is True and all(a["held"]["called"] is not None for a in D["arrivals"] if a.get("held")))
ok("3. the gate's arrivals are the plain day's count; its hours add up", ga["arrivals"] == ga0["arrivals"] and D["checks"]["hours_add_up"] and D["checks"]["table_equals_arrivals"])
held = [a for a in D["arrivals"] if a.get("held")]
ok("3. called at or after arriving; the gate reached the run later (R1 and R2's lines pass it, R3's is drawn straight)",
   all(a["held"]["called"] >= a["held"]["at"] - 0.01 for a in held)
   and all(abs(a["at"] - (a["held"]["called"] + a["held"]["tail"])) < 0.02 for a in held)
   and all((a["held"]["straight"] is True) == (a["route"] == "R3") for a in held), str(held[:2]))
iv = [tuple(x) for x in ga["intervals"]]
last_open = ga["last_open"]
ok("3. ⭐ never into a shut gate: every held lorry reaches the gate in an open minute (or after its last open minute, counted late)",
   all(any(p <= a["at"] < q for p, q in iv) or a["at"] >= last_open - 0.01 for a in held))
ga_arr = [a for a in D["arrivals"] if a["gate"] == "GA"]
calls = sorted(a["held"]["called"] for a in held)


def waiting_at_gate(t):
    return sum(1 for a in ga_arr if a["at"] <= t + 1e-6 < a["start"])


ok("3. ⭐ at most 2 waiting at the gate at every call", all(waiting_at_gate(c) <= 2 for c in calls), str([(c, waiting_at_gate(c)) for c in calls if waiting_at_gate(c) > 2][:3]))


def on_way(t, target):
    n = 0
    for a in held:
        tgt = (a["stops"][0]["st"] if a["stops"] else "gate:GA")
        if tgt != target:
            continue
        c = a["held"]["called"]
        started = (a["stops"][0]["start"] if a["stops"] else a["start"])
        if c is not None and c <= t + 1e-6 and started > t + 1e-6:
            n += 1
    return n


bad = [(a["held"]["called"], on_way(a["held"]["called"], a["stops"][0]["st"] if a["stops"] else "gate:GA")) for a in held]
ok("3. ⭐ at most 2 on the way to or waiting at any one bay at every call (the one just called included)", all(n <= 2 for _c, n in bad), str([b for b in bad if b[1] > 2][:3]))
spoil = next(st for s in D["sites"] for st in s["stations"] if st["name"] == "Spoil loading")
ok("3. ⭐ the queue moves off the site: at most 1 waits at the spoil bay (was %d), and the holding area holds the rest" % spoil0["most_waiting"],
   spoil["most_waiting"] <= 1 and Hf["most"] >= spoil0["most_waiting"] - 1 and Hf["minutes_held"] > 0, str((spoil["most_waiting"], Hf["most"], Hf["minutes_held"])))
ok("3. the figures: most held and when, call-off begins, the longest hold, arrivals by hour add up",
   Hf["most_at"] is not None and Hf["first"] is not None and Hf["longest"] >= Hf["minutes_held"] / max(1, Hf["held"]) and sum(Hf["hours"]) == Hf["held"])
ok("3. ⭐ the day with and without it: the site's most waiting falls, the held minutes appear, both sides filled",
   Hf["with"] and Hf["without"] and Hf["with"]["site_most"] <= 1 < Hf["without"]["site_most"]
   and Hf["without"]["minutes_held"] == 0 and Hf["with"]["minutes_held"] == Hf["minutes_held"]
   and Hf["without"]["site_minutes_lost"] == spoil0["minutes_lost"] + sum(st["minutes_lost"] for s in D_plain["sites"] for st in s["stations"] if st["name"] != "Spoil loading" and st["kind"] != "gate"),
   str((Hf["with"], Hf["without"])))
ok("3. over its spaces: 12 spaces against the most held", Hf["over_spaces"] == max(0, Hf["most"] - 12))
notes = " ".join(D["notes"])
ok("3. the words: the rule in one sentence, the mixers straight to the gate, the straight lines said",
   "call off at Lane holding area: 2 called forward at a time" in notes and "go straight to the gate" in notes
   and "drawn straight from the holding area to the gate" in notes and Hf["straight"] == loads["R3"], notes[:400])
ok("3. ⭐ the bay with more work than its gate's open day is named (Q13): the spoil bay's loading minutes against the gate's open minutes",
   spoil.get("over_day") is True and spoil["work_minutes"] >= spoil["open_minutes"] and "Spoil loading needs" in notes and "whatever happens before the gate" in notes,
   str((spoil.get("work_minutes"), spoil.get("open_minutes"))))
tf = next(st for s in D["sites"] for st in s["stations"] if st["name"] == "Tipping face")
ok("3. ...and a bay with less work is not", tf.get("over_day") is False and tf["work_minutes"] < tf["open_minutes"])
k1 = line_of[[l["line"] for l in D["lines"] if l["route_id"] == "R1"][0]]["laden_leg"]
k3 = line_of[[l["line"] for l in D["lines"] if l["route_id"] == "R3"][0]]["laden_leg"]
ok("3. ⭐ the drawing's legs carry the stop: R1's at the holding area's metres along the line, R3's none (straight)",
   D["legs"][k1]["hold_id"] == H1 and abs(D["legs"][k1]["hold_m"] - km(GQ, HG) * 1000) < 20 and D["legs"][k3]["hold_m"] is None and D["legs"][k3]["hold_id"] == H1,
   str((D["legs"][k1].get("hold_m"), D["legs"][k3].get("hold_m"))))
k2 = line_of[[l["line"] for l in D["lines"] if l["route_id"] == "R2"][0]]["empty_leg"]
ok("3. R2's EMPTY leg carries it (the lorry coming to load), its laden leg to the tip does not",
   D["legs"][k2]["hold_id"] == H1 and D["legs"][line_of[[l["line"] for l in D["lines"] if l["route_id"] == "R2"][0]]["laden_leg"]].get("hold_id") is None)
ok("3. the sites add up and every lorry left by a gate", D["checks"]["sites_add_up"] and all(a["out_at"] is not None for a in held))
ok("3. the window runs to the last lorry out (a held day ends later than the plain one)", D["window"]["end"] >= D_plain["window"]["end"])

# =========================================================================== #
#  4. The scenario                                                              #
# =========================================================================== #
D1 = day(holding_call=["%s=1" % H1])
ok("4. called forward 1 at a time: fewer on the way to the bay, more held, the bay never queues",
   D1["holding"][0]["call"] == 1 and D1["holding"][0]["most"] >= Hf["most"]
   and next(st for s in D1["sites"] for st in s["stations"] if st["name"] == "Spoil loading")["most_waiting"] == 0, str(D1["holding"][0])[:200])
D3 = day(holding_spaces=["%s=3" % H1])
ok("4. spaces 3 as a what-if: over its spaces follows", D3["holding"][0]["spaces"] == 3 and D3["holding"][0]["over_spaces"] == max(0, D3["holding"][0]["most"] - 3))
e = raises(lambda: day(holding_call=["L9=1"]))
ok("4. an unknown holding area is refused in words", e is not None and "not one of this scheme's holding areas" in str(e), str(e))
e = raises(lambda: sim.scenario_from_query(holding="maybe"))
ok("4. holding must be on or off", e is not None and "on or off" in str(e))
e = raises(lambda: sim.scenario_from_query(holding_call=["%s=0" % H1]))
ok("4. called forward below 1 is refused", e is not None and "between 1 and 50" in str(e), str(e))
e = raises(lambda: sim.scenario_from_query(holding_spaces=["x"]))
ok("4. spaces need LOCATION=n", e is not None and "LOCATION=n" in str(e))
Db = day(bands="on")
ok("4. with the example bands on, no held lorry reaches the gate inside a band",
   all(any(p <= a["at"] < q for p, q in [tuple(x) for x in next(g for g in Db["gates"] if g["gate_id"] == "GA")["intervals"]])
       or a["at"] >= next(g for g in Db["gates"] if g["gate_id"] == "GA")["last_open"] - 0.01
       for a in Db["arrivals"] if a.get("held")))
r = main.sim_day(month=9, holding="off")
ok("4. the endpoint: holding=off", r["holding_on"] is False)
r = main.sim_day(month=9, holding="on", holding_call=["%s=3" % H1], holding_spaces=["%s=20" % H1])
ok("4. the endpoint: the what-ifs reach the day", r["holding"][0]["call"] == 3 and r["holding"][0]["spaces"] == 20)
e = raises(lambda: main.sim_day(month=9, holding="sideways"))
ok("4. the endpoint refuses in words with a 400", e is not None and "400" in str(e))

# =========================================================================== #
#  5. The tick and the mixers in the day                                        #
# =========================================================================== #
main.set_route_planning("R3", main.RoutePlanning(skip_holding=1), token=TOK)
Ds = day()
ok("5. a ticked route's lorries go straight to the gate: R3 no longer held, R1 and R2 still are",
   Ds["holding"][0]["held"] == loads["R1"] + loads["R2"] and not any(a.get("held") for a in Ds["arrivals"] if a["route"] == "R3")
   and Ds["holding"][0]["straight"] == 0)
main.set_route_planning("R3", main.RoutePlanning(skip_holding=0), token=TOK)
holding.set_calls_through("L2", None)
Dn = day()
ok("5. a site that calls off nowhere: nothing held, the holding area not in the day", Dn["holding"] == [] and figures(Dn) == figures(D_plain))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
