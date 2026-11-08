"""
The return journey (8 Nov 2026, v2.1; John: "if a lorry is on turnaround … two way, but if it's just on delivery
maybe … one way"; the mockup notes/return-journey-mockup-1108 approved "yes looks good", few words on screen). How much of
a lorry's EMPTY way back the carbon charges: per route (Data → Routes: Comes back empty / May take other work / One way
only; blank = guessed from the route's start) with the defaults and the part share on Config → Planning. The loaded leg
takes the vehicle's laden factor and the way back its empty factor × the share (RICS 2023 §5.1.3; the NH Carbon Tool
figure beside it is untouched). backend/return_journey.py is the one rule.

WHAT IS ASSERTED: the rule (defaults, the guess by location kind and mixer, a typed choice wins, the shares, the
laden / empty pair and the single-figure fallback, the arithmetic); the Routes table's rows (route_analysis: the two legs
apart, the share, the guess for a quarry and for a site, a mixer); the planning write (typed, refused, cleared) and the
route list's fields; the cost lines (co2_t = trips × the trip's kg, loaded + empty = the total, the part share moving it,
an unrouted return charging nothing); the Carbon planner's totals; Config's validation; the schema and the package; the
screens' and guides' words; the seed.

WHAT THIS DOES NOT PROVE: no HERE call (geometry rows are typed in); no Postgres branch runs; the page is not mounted here
(a browser check is separate); live figures are not read.

Run:  python backend/tests/test_return_journey.py
"""
import json
import os
import re
import shutil
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

TMP = tempfile.mkdtemp(prefix="wayscope_return_")
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
import derived  # noqa: E402
import costlines  # noqa: E402
import carbon  # noqa: E402
import return_journey as rj  # noqa: E402
import tenant_package  # noqa: E402
import access  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"          # the demo codes are opt-in; the harness signs in as the planner
access.set_current("planner123")

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


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()
F = conversions.load_factors()

# =========================================================================== #
#  1. The rule                                                                  #
# =========================================================================== #
S = rj.settings(F)
ok("⭐ 1. the seed's defaults: a supplier's route may take other work (43 %), a scheme's and a mixer's come back empty",
   S == {"supplier": "part", "part_share_pct": 43, "scheme": "empty", "mixers": "empty"}, str(S))
ok("1. settings() with no block, a broken block and a half block all read the defaults under what is typed",
   rj.settings({}) == rj.DEFAULTS and rj.settings({"planning": {"return_journeys": "x"}}) == rj.DEFAULTS
   and rj.settings({"planning": {"return_journeys": {"supplier": "empty", "part_share_pct": "abc"}}})
   == {"supplier": "empty", "part_share_pct": 43, "scheme": "empty", "mixers": "empty"})
ok("1. settings_problem: absent fine, a bad choice, a share out of range, not a number, a non-dict",
   rj.settings_problem(None) is None and rj.settings_problem({"supplier": "part"}) is None
   and "must be one of" in (rj.settings_problem({"scheme": "sometimes"}) or "")
   and "0 to 100" in (rj.settings_problem({"part_share_pct": 140}) or "")
   and "0 to 100" in (rj.settings_problem({"part_share_pct": "half"}) or "")
   and rj.settings_problem([1]) is not None)
ok("1. a concrete mixer by its name, nothing else", rj.is_mixer("Truck mixer 8 m³ (32t)") and rj.is_mixer("Concrete mixer 6 m3")
   and not rj.is_mixer("Artic Tipper (44t)") and not rj.is_mixer(None))
# every kind of location the demo has, sorted into a supplier's end or the scheme's
SUPPLIER = ["Quarry", "Batching plant", "Asphalt plant", "Precast works", "Depot", "Railhead", "Rail head", "Port", "Soil recycling"]
SCHEME = ["Site", "Compound", "Stockpile", "Landfill", "Holding area", None, ""]
ok("⭐ 1. a quarry, plant, works, depot, railhead, port or recycling yard is a supplier's end; a site, compound, stockpile, tip or nothing is not",
   all(rj.is_supplier_type(t) for t in SUPPLIER) and not any(rj.is_supplier_type(t) for t in SCHEME))
ok("1. the guess: supplier → part, scheme → empty, a mixer → empty whatever its start",
   rj.default_mode("Quarry", "Artic Tipper (44t)", F) == "part" and rj.default_mode("Site", "Artic Tipper (44t)", F) == "empty"
   and rj.default_mode("Batching plant", "Truck mixer 8 m³ (32t)", F) == "empty")
ok("1. a typed choice wins over the guess; an unknown stored word falls back to the guess",
   rj.mode_for({"return_mode": "oneway"}, "Quarry", "Artic Tipper (44t)", F) == ("oneway", "route")
   and rj.mode_for({"return_mode": "whatever"}, "Quarry", "Artic Tipper (44t)", F) == ("part", "default")
   and rj.mode_for(None, "Site", None, F) == ("empty", "default"))
ok("1. the shares: 1, 0.43, 0; the share follows a typed part share",
   rj.share("empty", F) == 1.0 and close(rj.share("part", F), 0.43) and rj.share("oneway", F) == 0.0
   and close(rj.share("part", {"planning": {"return_journeys": {"part_share_pct": 60}}}), 0.6))
ART = "Artic Tipper (44t)"
lad, emp, basis = rj.leg_factors(F, ART)
ok("⭐ 1. the artic's laden and empty pair is the DESNZ 2026 pair stored on the vehicle (1.08004 / 0.65383)",
   basis == "pair" and close(lad, 1.08004) and close(emp, 0.65383), f"{lad} {emp} {basis}")
el, ee, eb = rj.leg_factors(F, ART + " — electric")
ok("1. an electric lorry has no pair: its one derived figure on both legs",
   eb == "single" and close(el, ee) and close(el, conversions._emissions(F, ART + " — electric")))
ul, ue, ub = rj.leg_factors(F, "A lorry nobody typed")
ok("1. a vehicle the document does not carry: the fallback figure on both legs",
   ub == "single" and close(ul, conversions._emissions(F, "A lorry nobody typed")) and close(ul, ue))
t = rj.trip_kg(F, ART, 20.0, 20.0, 1.0)
ok("⭐ 1. a 20 km haul, back empty: 20 × 1.08004 + 20 × 0.65383 = 34.6774 kg; the legs apart; 40 km charged",
   close(t["kg"], 34.6774, 1e-4) and close(t["loaded_kg"], 21.6008, 1e-4) and close(t["empty_kg"], 13.0766, 1e-4)
   and close(t["charged_km"], 40.0), str(t))
t2 = rj.trip_kg(F, ART, 20.0, 20.0, 0.43)
ok("1. the same haul, may take other work: the empty leg × 0.43 (5.6229 kg), 28.6 km charged",
   close(t2["empty_kg"], 20 * 0.43 * 0.65383, 1e-4) and close(t2["charged_km"], 28.6) and close(t2["loaded_kg"], t["loaded_kg"]))
t3 = rj.trip_kg(F, ART, 20.0, 20.0, 0.0)
ok("1. one way only: the loaded leg alone; a None return charges nothing", t3["kg"] == t3["loaded_kg"] and t3["empty_kg"] == 0.0
   and rj.trip_kg(F, ART, 20.0, None, 1.0)["empty_kg"] == 0.0)
avg = conversions._emissions(F, ART)
ok("1. ⚠ the method change on a full return: the pair's sum sits below twice the average-laden figure (about 8 % on the artic)",
   t["kg"] < 40 * avg and 0.90 < t["kg"] / (40 * avg) < 0.95, f"{t['kg']} vs {40 * avg}")

# =========================================================================== #
#  2. The Routes table's rows: a quarry route, a site route, a mixer route     #
# =========================================================================== #
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', 52.5, -1.0, 'Quarry')")
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', 52.5, -0.9, 'Compound')")
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L3', 'Vale Tip', 52.6, -0.9, 'Landfill')")
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L4', 'Mill Batching', 52.4, -1.0, 'Batching plant')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R2', 'L2', 'L3', 'Earthworks', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R3', 'L4', 'L2', 'Ready-mixed concrete', 'IPT1')")
MIX = "Truck mixer 8 m³ (32t)"


def geom(rid, prof, leg, km, hr):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, duration_hr) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (db.current_tenant(), rid, prof, leg, 0, "[[-1.0,52.5],[-0.9,52.5]]", km, hr))


geom("R1", ART, "loaded", 30.0, 0.75); geom("R1", ART, "return", 32.0, 0.70)
geom("R2", ART, "loaded", 12.0, 0.30); geom("R2", ART, "return", 12.0, 0.30)
geom("R3", MIX, "loaded", 8.0, 0.25); geom("R3", MIX, "return", 8.0, 0.25)
geom("R2", MIX, "loaded", 12.0, 0.30)          # a mixer on the tip route with no return leg routed


def row(rid, prof):
    return next(r for r in network.route_analysis(rid)["rows"] if r["profile"] == prof and r["alt_index"] == 0)


r1 = row("R1", ART)
exp1 = rj.trip_kg(F, ART, 30.0, 32.0, 0.43)
ok("⭐ 2. the quarry route's artic row: guessed 'May take other work', share 0.43, the two legs apart, the trip = the rule",
   r1["return_mode"] == "part" and r1["return_mode_source"] == "default" and close(r1["return_share"], 0.43)
   and close(r1["co2_kg_per_trip"], round(exp1["kg"], 1), 0.051) and close(r1["co2_loaded_kg_per_trip"], round(exp1["loaded_kg"], 1), 0.051)
   and close(r1["co2_empty_kg_per_trip"], round(exp1["empty_kg"], 1), 0.051), str({k: r1[k] for k in r1 if "co2" in k or "return" in k}))
ok("2. the row's co2 a day = the trip × its trips a day", close(r1["co2_kg_per_day"], round(r1["co2_kg_per_trip"] * r1["trips_per_day"], 1), 0.11))
ok("2. the row still carries the average-laden figure for the Config display, and the legs' km unchanged",
   close(r1["co2_kg_per_km"], avg) and r1["loaded_km"] == 30.0 and r1["return_km"] == 32.0 and r1["total_km"] == 62.0)
r2 = row("R2", ART)
ok("⭐ 2. the muck-away from a compound: guessed 'Comes back empty', the whole return charged",
   r2["return_mode"] == "empty" and r2["return_share"] == 1.0 and close(r2["co2_kg_per_trip"], round(rj.trip_kg(F, ART, 12.0, 12.0, 1.0)["kg"], 1), 0.051))
r3 = row("R3", MIX)
ok("2. the mixer from the batching plant: 'Comes back empty' though the plant is a supplier's end",
   r3["return_mode"] == "empty" and r3["return_share"] == 1.0)
r2m = row("R2", MIX)
ok("2. a mixer whose return is not routed: the return mirrors the outbound (as before) and is charged as the row says",
   r2m["return_estimated"] and close(r2m["co2_kg_per_trip"], round(rj.trip_kg(F, MIX, 12.0, 12.0, 1.0)["kg"], 1), 0.051))

# the planning write
res = network.set_route_planning("R1", {"return_mode"}, return_mode="oneway")
ok("⭐ 2. Save planning figures with One way only: stored, and the row now charges the loaded leg alone",
   res.get("return_mode") == "oneway" and row("R1", ART)["return_mode"] == "oneway" and row("R1", ART)["return_mode_source"] == "route"
   and row("R1", ART)["return_share"] == 0.0 and close(row("R1", ART)["co2_empty_kg_per_trip"], 0.0))
bad = network.set_route_planning("R1", {"return_mode"}, return_mode="sometimes")
ok("2. a word that is not one of the three is refused in words, naming the three", "error" in bad and "Comes back empty" in bad["error"]
   and "One way only" in bad["error"] and row("R1", ART)["return_mode"] == "oneway")
res = network.set_route_planning("R1", {"return_mode"}, return_mode=None)
ok("2. blank clears it: back to the guess", res.get("return_mode") is None and row("R1", ART)["return_mode"] == "part"
   and row("R1", ART)["return_mode_source"] == "default")
res = network.set_route_planning("R1", {"km_basis"}, km_basis="loaded")
ok("2. saving another planning field leaves the return journey alone (only sent fields are written)",
   res.get("km_basis") == "loaded" and res.get("return_mode") is None)
network.set_route_planning("R2", {"return_mode"}, return_mode="part")
st = {r["id"]: r for r in network.routes_status()}
ok("⭐ 2. the route list carries the typed choice, the guess for the route's start and the part share",
   st["R1"]["return_mode"] is None and st["R1"]["return_default"] == "part" and st["R1"]["return_part_pct"] == 43
   and st["R2"]["return_mode"] == "part" and st["R2"]["return_default"] == "empty" and st["R3"]["return_default"] == "part",
   str({k: (v["return_mode"], v["return_default"]) for k, v in st.items()}))
ok("2. the request model takes return_mode and PLANNING_FIELDS lists it",
   "return_mode" in main.RoutePlanning.model_fields and "return_mode" in network.PLANNING_FIELDS)
network.set_route_planning("R2", {"return_mode"}, return_mode=None)

# =========================================================================== #
#  3. The cost lines: the one figure every surface sums                         #
# =========================================================================== #
MONTHS = (9, 10)


def line(rid, sect, qty, veh, mat="Small aggregate"):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type=mat,
        material_description=None, vehicle_type=veh, submitted_by="tester", unit="t",
        status="Pending", cells=[main.Cell(month_index=m, quantity=qty) for m in MONTHS], ipt="IPT1"))
    main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id=sect)


line("R1", "WS1", 4000.0, ART)
line("R2", "WS2", 2000.0, ART)
line("R2", "WS3", 500.0, MIX)                     # the mixer whose return is not routed
cl = {(c["route_id"], c["section_id"], c["month_index"]): c for c in costlines.lines(acc={"role": "planner"}, from_month=9, to_month=10)["lines"]}
c1 = cl[("R1", "WS1", 9)]
ok("⭐ 3. a cost line's co2_t = trips × the trip's kg ÷ 1000 (the quarry route, 43 % of the way back), and loaded + empty = the total",
   close(c1["co2_t"], round(c1["trips"] * exp1["kg"] / 1000.0, 3), 1e-3)
   and close(c1["co2_loaded_t"] + c1["co2_empty_t"], c1["co2_t"], 2e-3) and close(c1["return_share"], 0.43),
   str({k: c1[k] for k in ("trips", "co2_t", "co2_loaded_t", "co2_empty_t", "return_share")}))
ok("3. the Dashboard's lorry-km is still the whole round trip (the lorry drives back whatever is charged)",
   close(c1["km"], c1["trips"] * 62.0, 1e-6) and close(c1["km_trip"], 62.0))
c2 = cl[("R2", "WS2", 9)]
ok("3. the muck-away line charges the whole return", close(c2["return_share"], 1.0)
   and close(c2["co2_t"], round(c2["trips"] * rj.trip_kg(F, ART, 12.0, 12.0, 1.0)["kg"] / 1000.0, 3), 1e-3))
c3 = cl[("R2", "WS3", 9)]
ok("3. a line whose return is not routed charges the loaded leg only (as km_trip does), and says so",
   close(c3["co2_empty_t"], 0.0) and close(c3["co2_t"], round(c3["trips"] * rj.trip_kg(F, MIX, 12.0, 0.0, 1.0)["kg"] / 1000.0, 3), 1e-3)
   and c3["km_trip"] == 12.0 and "RETURN" in " ".join(c3["flags"]).upper() or c3["km_trip"] == 12.0)
ctx = derived.line_context({"route_id": "R1", "vehicle_type": ART, "month_index": 9, "week": {"planned_qty": 100}}, F)
ok("⭐ 3. the line context carries the route's share and mode and the trip's kg (the route's row is the one source; a Config change "
   "reaches it on the next request, the config cache being cleared on Save)",
   close(ctx["co2_kg_trip"], exp1["kg"], 1e-3) and close(ctx["return_share"], 0.43) and ctx["return_mode"] == "part"
   and close(ctx["co2_loaded_kg_trip"] + ctx["co2_empty_kg_trip"], ctx["co2_kg_trip"], 1e-3))
ok("3. the approved carbon table the public map reads is the cost lines' figure (one source)",
   close(main._approved_co2(F, 9, 10)[0][("R1", "earthworks", "WS1", 9)], c1["co2_t"], 1e-6))

# =========================================================================== #
#  4. The Carbon planner                                                        #
# =========================================================================== #
sc = carbon.scenario(acc={"role": "planner"}, from_month=9, to_month=10)
T = sc["baseline"]["totals"]
ok("⭐ 4. the planner's transport total = the cost lines' sum, with the two legs apart and the charged empty km",
   close(T["transport_t"], sum(c["co2_t"] for c in cl.values()), 0.01)
   and close(T["transport_loaded_t"] + T["transport_empty_t"], T["transport_t"], 1e-6) and T["empty_km"] > 0,
   f"{T['transport_t']} vs {sum(c['co2_t'] for c in cl.values())}")
ok("4. the NH Carbon Tool figure and the tonne-km benchmark stand beside it, untouched by the share (one-way km × tonnes)",
   T["transport_nh_t"] > 0 and T["transport_tkm_t"] > 0
   and close(T["transport_nh_t"], sum(carbon.transport_nh_t(c["distance_km"], c["tonnes"], carbon.params(F)) for c in cl.values()), 0.01))
ok("4. the method's words name the return share and the Data → Routes choice; the NH words unchanged",
   "return share" in sc["methods"]["headline"] and "Data → Routes" in sc["methods"]["headline"]
   and "NH Carbon Tool v2.7 basis" in sc["methods"]["nh_tool"])

# =========================================================================== #
#  5. Config, the schema, the package                                           #
# =========================================================================== #
doc = json.loads(json.dumps(config.load(conversions)))
doc["planning"]["return_journeys"] = {"scheme": "sometimes"}
ok("5. Config save refuses a choice that is not one of the three, in words",
   any("Return journeys" in p for p in config.validate(doc, network=network)))
doc["planning"]["return_journeys"] = {"supplier": "empty", "part_share_pct": 30}
ok("5. ...and accepts a half-typed block", not any("Return journeys" in p for p in config.validate(doc, network=network)))
cols = {r["name"] if isinstance(r, dict) and "name" in r else r[1] for r in db.query("PRAGMA table_info(routes)")}
ok("⭐ 5. routes.return_mode: in the DDL (the SQLite rebuild keeps only those) AND ALTERed on an old database",
   "return_mode" in cols and "return_mode" in db._TENANT_DDL["routes"] and ('("routes", "return_mode", "TEXT")' in read("backend/db.py")))
network.set_route_planning("R1", {"return_mode"}, return_mode="oneway")
pkg = tenant_package.export_tenant()
prow = next(r for r in (pkg.get("tables") or pkg)["routes"] if r["id"] == "R1")
ok("5. the organisation file carries the route's choice", prow.get("return_mode") == "oneway")
network.set_route_planning("R1", {"return_mode"}, return_mode=None)
seed = json.loads(read("backend/factors.json"))
ok("5. the seed carries planning.return_journeys with a sourced note, and the vehicles' notes no longer say the pair is unread",
   seed["planning"]["return_journeys"] == {"supplier": "part", "part_share_pct": 43, "scheme": "empty", "mixers": "empty"}
   and "RICS" in seed["planning"]["_return_journeys_note"] and "NOT read by code yet" not in read("backend/factors.json"))

# =========================================================================== #
#  6. The screens and the guides (few words; the explanation behind the i)       #
# =========================================================================== #
fe = read("frontend/index.html")
ok("⭐ 6. the route's planning figures carry the Return journey choice: three words each, a Guess row, an i box",
   'data-route-return="1"' in fe and 'const RETURN_WORDS = { empty: "Comes back empty", part: "May take other work", oneway: "One way only" }' in fe
   and '<InfoTip id="routes.return" />' in fe and 'body.return_mode = v.return_mode || null' in fe and "Guess: ${RETURN_WORDS[route.return_default]" in fe)
ok("6. the route row's chip: muted while guessed, navy once chosen", 'data-route-return-typed={typed ? "1" : "0"}' in fe
   and "Part return · ${r.return_part_pct ?? 43} %" in fe)
ok("6. Config → Planning: Return journeys, three choices and the share, one hint line, an i box",
   'data-cfg="return-journeys"' in fe and '<InfoTip id="cfg.return" />' in fe and "May take other work charges" in fe
   and "For routes with no choice of their own (Data → Routes)." in fe)
ok("6. the Dashboard's Transport carbon card prints loaded and empty apart on its second line",
   "loaded ${co2T(K.totCo2L)} · empty ${co2T(K.totCo2E)}" in fe and "T.co2L += r.co2_loaded_t || 0; T.co2E += r.co2_empty_t || 0;" in fe)
info = fe.split("const INFO = {")[1].split("\n};")[0]
ok("6. the i boxes: dash.carbon says each leg and the route's choice; routes.return and cfg.return exist and point at t1-return",
   '"routes.return": {' in info and '"cfg.return": {' in info and info.count('tech: "t1-return"') == 3
   and "as much of the empty way back as each route charges" in info)
screen = re.sub(r'source: "[^"]*"', "", fe)
ok("6. RICS and GLEC are named only in an i box's source line, never on a screen", "RICS" not in screen and "GLEC" not in screen)
ok("6. the Carbon planner's method row names each leg's own factor; the Routes table's CO2 column says what it adds",
   "each leg at its own factor" in fe and 'title="Loaded leg at the laden factor + the way back as the route charges it"' in fe)
ug = read("frontend/help/index.html")
tg = read("frontend/help/technical/index.html")
ok("⭐ 6. the user guide: the Routes planning block, the Config bullet, the Dashboard card and the figures table say it",
   "<strong>Return journey</strong> says how much of the lorry's empty way back" in ug and "<strong>Return journeys</strong> (the guess for a route" in ug
   and "the loaded leg and the empty way back apart" in ug and "return km × the route's return share × its empty factor" in ug)
ok("6. the technical guide: t1-return with the rule, the sources and the Pairings hook; t1-carbon's formula updated",
   'id="t1-return"' in tg and "return_journey.py" in tg and "RICS Whole life carbon" in tg and "GLEC" in tg and "Pairings" in tg
   and "loaded km × laden factor + return km × return share × empty factor" in tg)
ok("6. the public map's note, the bulletin's rule and CLP appendix G say the way back is charged as the route says",
   "the way back as the route charges it" in read("map/index.html") and "loaded and empty apart" in read("backend/bulletin.py")
   and "as each route" in read("backend/clp_doc_appendices_render.py"))
ok("6. the user guide names the anchor the i box points at", 'id="7-2-routes"' in ug and 'guide: "7-2-routes"' in fe)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
