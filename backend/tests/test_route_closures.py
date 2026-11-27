"""
The closure lines on the best-option rule (25 Nov 2026, branch claude/route-closures-line; the Routes page rethink,
card 3, John's "Yes, as recommended" to Q5 and Q6). route_best.evaluate() REPORTS a field "closures": one entry a routing
closure a line of the route runs through, in force on the rule's day or starting after it, each with the two halves a
person reads (the head "Closure in force" / "Closure planned" / "Closure planned on Alt 1", and the line
"name · dates · what the diversion does").

WHAT IS ASSERTED (each fails on the base, which has no such field):
  1. the pure parts: the name cut at its first colon; the dates in words (in force "until ..."; planned "1–31 Dec 2027",
     across months, across years, "from ..."); the diversion's figures in the Diversions table's own form (divSigned,
     divMins: a tenth of the unit, whole minutes, the minus sign, no time where the table has none); the problem words;
     "and N more closures"; KM_PER_MILE is config's;
  2. a closure IN FORCE that a diversion in use goes round: "Closure in force", "until ...", "the diversion is in use";
  3. a closure PLANNED over the line in use: "Closure planned" and the figures route_choice.periods() gives the
     Diversions table for that closure (the same function GET /api/routes/diversions reads);
  4. a closure planned over an ALTERNATIVE only: "Closure planned on Alt 1", no figures;
  5. an advisory zone (affects no routing) and an ENDED closure give no entry;
  6. three closures on one route: soonest first, "and 1 more closure";
  7. a closure in force with no way round: "no diversion yet";
  8. Q6: with the field turned off every route's answer, options, reasons, sentences and labels are the same
     (the same check was run on the 50 routes of a copy of live, 25 Nov: notes\\session-1124-route-closures-line.md);
  9. the words: no ISO date, no "zone", no id, at most 25 words a head and line together.

WHAT THIS DOES NOT PROVE: live's closures (read on a local copy of live only); Postgres; the card and the map (they are
ui_fix_routes_closures.js).

Run:  python backend/tests/test_route_closures.py
"""
import datetime
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
sys.path.insert(0, HERE)

# ---- stubs, verbatim from test_route_best.py ---------------------------------
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

TMP = tempfile.mkdtemp(prefix="wayscope_closures_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
os.environ["ADMIN_TOKEN"] = "closures-admin-token"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402,F401
import config  # noqa: E402
import costing  # noqa: E402
import zones  # noqa: E402
import limits  # noqa: E402
import route_choice  # noqa: E402
import route_compare  # noqa: E402
import route_best as RB  # noqa: E402

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


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant(); db.init_users_db()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  1. The pure parts                                                           #
# =========================================================================== #
ok("⭐ 1. the name is cut at its first colon; a name with none is kept; an empty one reads 'A closure'",
   RB.closure_name("A47 at the new Tilton junction: HGV diversion while the junction is built")
   == "A47 at the new Tilton junction"
   and RB.closure_name("Market Harborough town centre") == "Market Harborough town centre"
   and RB.closure_name("Mill bridge: lorries: both ways") == "Mill bridge"
   and RB.closure_name(": nothing first") == ": nothing first" and RB.closure_name("") == "A closure")
ok("⭐ 1. the dates in words: in force 'until ...'; planned in a month, across months, across years, open-ended",
   (RB.closure_dates("2026-10-05", "2027-12-17", True), RB.closure_dates("2027-12-01", "2027-12-31", False),
    RB.closure_dates("2027-10-05", "2027-12-17", False), RB.closure_dates("2026-10-05", "2027-12-17", False),
    RB.closure_dates("2027-12-01", None, False), RB.closure_dates("2026-10-05", None, True)) ==
   ("until 17 Dec 2027", "1–31 Dec 2027", "5 Oct – 17 Dec 2027", "5 Oct 2026 – 17 Dec 2027", "from 1 Dec 2027", ""))
_per = {"status": "in_use", "legs": [
    {"vehicle_profile": "Other lorry", "leg": "loaded", "alt_index": 1, "km_delta": 9.0, "hr_delta": 0.5},
    {"vehicle_profile": "Artic", "leg": "return", "alt_index": 1, "km_delta": 1.0, "hr_delta": 0.1},
    {"vehicle_profile": "Artic", "leg": "loaded", "alt_index": 1, "km_delta": 4.345, "hr_delta": -0.05}]}
ok("⭐ 1. the figures are the Diversions table's (divLeg, divSigned, divMins): the lorry's loaded leg, a tenth of the "
   "unit, whole minutes, the minus sign",
   RB.diversion_words(_per, "Artic", "mi") == "diverts, +2.7 mi · −3 min"
   and RB.diversion_words(_per, "Artic", "km") == "diverts, +4.3 km · −3 min"
   and RB.diversion_words(_per, "Nobody", "km") == "diverts, +9.0 km · +30 min",
   RB.diversion_words(_per, "Artic", "mi"))
ok("1. a shorter diversion reads '−'; no time where the table has none; no figure at all reads 'diverts'",
   RB.diversion_words({"status": "in_use", "legs": [{"leg": "loaded", "km_delta": -1.6093, "hr_delta": None}]}, "x", "mi")
   == "diverts, −1.0 mi"
   and RB.diversion_words({"status": "in_use", "legs": [{"leg": "loaded", "km_delta": None}]}, "x", "km") == "diverts"
   and RB.diversion_words({"status": "in_use", "legs": [{"leg": "loaded", "km_delta": 0.2, "hr_delta": 0.004}]}, "x",
                          "km") == "diverts, +0.2 km · +0 min")
ok("1. a period with no way round says so in the rule's lower case; none at all is None",
   [RB.diversion_words({"status": s, "legs": []}, "x", "km") for s in ("needs_route", "no_way_round", "declined")]
   == ["no diversion yet", "no road round it", "kept on the main route"] and RB.diversion_words(None, "x", "km") is None)
ok("1. the more line: none at two, 'and 1 more closure', 'and 3 more closures'; the card shows two",
   RB.CLOSURES_SHOWN == 2 and RB.closures_more([1, 2]) is None and RB.closures_more([1, 2, 3]) == "and 1 more closure"
   and RB.closures_more([1] * 5) == "and 3 more closures" and RB.closures_more(None) is None)
ok("1. KM_PER_MILE is config's own", RB.KM_PER_MILE == config.KM_PER_MILE)

# =========================================================================== #
#  Fixture                                                                     #
# =========================================================================== #
ART = route_compare.PROFILE
T = db.current_tenant()
DAY = datetime.date(2027, 2, 2)


def bent(lat, dlat):
    return [[-1.0, lat], [-0.95, lat + dlat], [-0.9, lat]]


def add_route(rid, lat, opts):
    o, d = f"L{rid}a", f"L{rid}b"
    db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, -1.0, 'Quarry')",
               (T, o, f"Pit {rid}", lat))
    db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, -0.9, 'Compound')",
               (T, d, f"Yard {rid}", lat))
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, "
               "'Small aggregate', 'IPT1')", (T, rid, o, d))
    for alt, (line, km, hr) in opts.items():
        network._upsert_geom(rid, ART, json.dumps(line), km, hr, None, leg="loaded", alt_index=alt)
        network._upsert_geom(rid, ART, json.dumps(list(reversed(line))), km, hr, None, leg="return", alt_index=alt)


def box(x, lat, r=0.002):
    return {"type": "Polygon", "coordinates": [[[x - r, lat - r], [x + r, lat - r], [x + r, lat + r], [x - r, lat + r],
                                                [x - r, lat - r]]]}


L1, L2, L3, L4, L5 = 52.5, 52.6, 52.7, 52.8, 52.9
# C1: a main line closed now, the diversion (Alt 1, north) in use round it
add_route("C1", L1, {0: (bent(L1, 0), 7.0, 0.20), 1: (bent(L1, 0.01), 7.4, 0.21)})
# C2: a main line closed in June, its diversion Alt 1 (0.4 km longer, a little slower)
add_route("C2", L2, {0: (bent(L2, 0), 7.0, 0.20), 1: (bent(L2, 0.01), 7.4, 0.21)})
# C3: a closure planned on Alt 1 only; an advisory zone and an ended closure over the main line
add_route("C3", L3, {0: (bent(L3, 0), 7.0, 0.20), 1: (bent(L3, 0.01), 7.4, 0.21)})
# C4: three closures planned over the main line (Jul, Aug, Oct)
add_route("C4", L4, {0: (bent(L4, 0), 7.0, 0.20), 1: (bent(L4, 0.01), 7.4, 0.21)})
# C5: one line only, closed now: no way round
add_route("C5", L5, {0: (bent(L5, 0), 7.0, 0.20)})
route_choice._load_limits = lambda: []

Z = {}
Z["now"] = zones.create_zone("Mill bridge: lorries diverted by the north road", box(-0.95, L1), kind="closure",
                             starts_on="2027-01-01", ends_on="2027-03-31")
Z["june"] = zones.create_zone("Station Road resurfacing", box(-0.95, L2), kind="closure",
                              starts_on="2027-06-01", ends_on="2027-06-30")
Z["alt"] = zones.create_zone("North Lane bridge works", box(-0.95, L3 + 0.01), kind="closure",
                             starts_on="2027-09-01", ends_on="2027-09-30")
Z["advisory"] = zones.create_zone("Village fete (for information)", box(-0.95, L3), kind="closure",
                                  affects_routing=False, starts_on="2027-02-01", ends_on="2027-02-28")
Z["ended"] = zones.create_zone("Old gas main", box(-0.97, L3), kind="closure",
                               starts_on="2026-01-01", ends_on="2026-02-01")
Z["c4a"] = zones.create_zone("Ford Lane", box(-0.97, L4), kind="closure", starts_on="2027-08-01", ends_on="2027-08-31")
Z["c4b"] = zones.create_zone("Church Street", box(-0.95, L4), kind="closure", starts_on="2027-07-01",
                             ends_on="2027-07-31")
Z["c4c"] = zones.create_zone("Mill Street", box(-0.93, L4), kind="closure", starts_on="2027-10-01", ends_on="2027-10-31")
Z["c5"] = zones.create_zone("Long bridge", box(-0.95, L5), kind="closure", starts_on="2027-01-15", ends_on="2027-04-30")
ok("fixture: every zone was made", all(isinstance(z, dict) and z.get("id") for z in Z.values()),
   [z for z in Z.values() if not (isinstance(z, dict) and z.get("id"))])
ZID = {k: z.get("id") for k, z in Z.items()}
route_choice.refresh_zones()


def run(rid, day=DAY):
    return RB.evaluate(rid, RB.Context(day=day))


R = {rid: run(rid) for rid in ("C1", "C2", "C3", "C4", "C5")}
CTX = RB.Context(day=DAY)
U = CTX.unit
ok("fixture: the organisation's unit is read ('mi' for a GB organisation, else 'km')", U in ("mi", "km"), U)
ALL = [c for r in R.values() for c in (r.get("closures") or [])]


def one(rid):
    cl = R[rid].get("closures") or []
    return cl[0] if len(cl) == 1 else None


# =========================================================================== #
#  2. In force, the diversion in use round it                                  #
# =========================================================================== #
c1 = one("C1")
ok("⭐ 2. a closure in force that the diversion goes round: one entry, 'Closure in force', the name to its colon, "
   "'until 31 Mar 2027', 'the diversion is in use'",
   c1 and c1["head"] == "Closure in force" and c1["state"] == "in_force" and c1["whose"] == "in_use"
   and c1["name"] == "Mill bridge" and c1["dates"] == "until 31 Mar 2027" and c1["does"] == "the diversion is in use"
   and c1["line"] == "Mill bridge · until 31 Mar 2027 · the diversion is in use" and c1["zone"] == ZID["now"]
   and c1["legs"] == "both" and c1["alts"] == [] and c1["labels"] == [], c1)
ok("2. the route's answer still compares with the diversion (in_use reads it), so the line and the card agree",
   (R["C1"].get("in_use") or {}).get("loaded", {}).get("why") == "diversion", R["C1"].get("in_use"))
ok("2. a day before the closure starts it is 'Closure planned' with the diversion's figures, not 'in use'",
   (lambda c: c and c["head"] == "Closure planned" and c["dates"] == "1 Jan – 31 Mar 2027"
    and c["does"].startswith("diverts, +"))(((run("C1", datetime.date(2026, 12, 1)).get("closures")) or [None])[0]))
ok("2. a day after it ends: no entry", run("C1", datetime.date(2027, 4, 1)).get("closures") == [])

# =========================================================================== #
#  3. Planned over the line in use: the Diversions table's figures             #
# =========================================================================== #
c2 = one("C2")
_p2 = next((p for p in route_choice.periods("C2") if ZID["june"] in p["zones"]), None)
ok("⭐ 3. a closure planned over the line in use: 'Closure planned', '1–30 Jun 2027', the figures the Diversions "
   "table reads (route_choice.periods, the function GET /api/routes/diversions reads)",
   c2 and _p2 and c2["head"] == "Closure planned" and c2["state"] == "planned" and c2["whose"] == "in_use"
   and c2["dates"] == "1–30 Jun 2027" and c2["does"] == RB.diversion_words(_p2, R["C2"]["lorry"], U)
   and c2["does"] == ("diverts, +0.2 mi · +1 min" if U == "mi" else "diverts, +0.4 km · +1 min")
   and c2["line"] == f"Station Road resurfacing · 1–30 Jun 2027 · {c2['does']}", (c2, _p2))
ok("3. Q6: a closure planned later changes nothing in the answer (C2 keeps its main line in use)",
   (R["C2"].get("in_use") or {}).get("loaded", {}).get("alt") == 0)

# =========================================================================== #
#  4. Planned on an alternative only                                           #
# =========================================================================== #
c3 = R["C3"].get("closures") or []
ok("⭐ 4. a closure planned over Alt 1 only: 'Closure planned on Alt 1', name and dates, no figures",
   len(c3) == 1 and c3[0]["head"] == "Closure planned on Alt 1" and c3[0]["whose"] == "option"
   and c3[0]["alts"] == [1] and c3[0]["labels"] == ["Alt 1"] and c3[0]["does"] is None
   and c3[0]["line"] == "North Lane bridge works · 1–30 Sep 2027", c3)

# =========================================================================== #
#  5. Advisory and ended: no entry                                             #
# =========================================================================== #
ok("⭐ 5. an advisory zone (affects no routing) and an ended closure give no entry anywhere",
   not [c for c in ALL if c["zone"] in (ZID["advisory"], ZID["ended"])]
   and not [c for c in ALL if "fete" in c["line"] or "gas main" in c["line"]])

# =========================================================================== #
#  6. Three: soonest first, "and 1 more closure"                               #
# =========================================================================== #
c4 = R["C4"].get("closures") or []
ok("⭐ 6. three closures over one route: soonest first (Jul, Aug, Oct), 'and 1 more closure'",
   [c["name"] for c in c4] == ["Church Street", "Ford Lane", "Mill Street"]
   and R["C4"].get("closures_more") == "and 1 more closure", ([c["line"] for c in c4], R["C4"].get("closures_more")))
ok("6. a route with one or none has no more line", all(R[r].get("closures_more") is None for r in ("C1", "C2", "C3", "C5")))

# =========================================================================== #
#  7. In force with no way round                                               #
# =========================================================================== #
c5 = one("C5")
ok("⭐ 7. a closure in force over the route's only line, no way round stored: 'no diversion yet'",
   c5 and c5["head"] == "Closure in force" and c5["does"] == "no diversion yet"
   and c5["line"] == "Long bridge · until 30 Apr 2027 · no diversion yet", c5)

# =========================================================================== #
#  8. Q6: nothing else moves                                                   #
# =========================================================================== #


def strip(r):
    r = json.loads(json.dumps(r, default=str))
    r.pop("closures", None); r.pop("closures_more", None)
    return r


_on = {rid: strip(run(rid)) for rid in R}
RB.CLOSURES_ON = False
_off_raw = {rid: run(rid) for rid in R}
_off = {rid: strip(r) for rid, r in _off_raw.items()}
_tab_off = RB.table(DAY)
RB.CLOSURES_ON = True
_tab_on = RB.table(DAY)
ok("⭐ 8. Q6: turned off, every route's answer, options, ruled-out reasons, sentences and labels are the same",
   _on == _off, [rid for rid in R if _on[rid] != _off[rid]])
ok("8. turned off the field is empty, not missing", all(r.get("closures") == [] and r.get("closures_more") is None
                                                        for r in _off_raw.values()))


def strip_t(t):
    t = json.loads(json.dumps(t, default=str))
    for r in t["routes"]:
        r.pop("closures", None); r.pop("closures_more", None)
    return t


ok("⭐ 8. Q6: the whole table (totals, rows, routes) is the same with the field off and on",
   strip_t(_tab_on) == strip_t(_tab_off) and _tab_on["totals"] == _tab_off["totals"])
ok("8. the table carries each route's closures", any(r.get("closures") for r in _tab_on["routes"]))
_rb = read("backend/route_best.py")
_ev = _rb[_rb.index("def evaluate("):]
_ev = "\n".join(l.split("#")[0] for l in _ev[:_ev.index('out["closures"] = closures(')].splitlines())
ok("8. (source) the field is worked out after the answer is made, and nothing before it reads it",
   'out["lines"] = line_labels(' in _ev and "closures" not in _ev.replace('"closures": [], "closures_more": None', ""))

# =========================================================================== #
#  9. The words                                                                #
# =========================================================================== #
ok("⭐ 9. the words: no ISO date, no 'zone', no zone id, at most 25 words a head and line together",
   ALL and not [c for c in ALL if re.search(r"\d{4}-\d{2}-\d{2}", c["head"] + c["line"])
                or re.search(r"\bzones?\b", (c["head"] + " " + c["line"]).lower())
                or any(z and z in c["head"] + c["line"] for z in ZID.values())
                or len((c["head"] + " " + c["line"]).split()) > 25], ALL)
ok("9. the heads are the rule's three", {c["head"] for c in ALL} <= {RB.CLOSURE_IN_FORCE, RB.CLOSURE_PLANNED} |
   {RB.CLOSURE_PLANNED_ON + c["head"][len(RB.CLOSURE_PLANNED_ON):] for c in ALL if c["whose"] == "option"})
ok("9. the line is the three halves joined by ' · ' (the card prints the halves, the file the line)",
   all(c["line"] == " · ".join(x for x in (c["name"], c["dates"], c["does"]) if x) for c in ALL))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
