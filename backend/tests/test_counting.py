"""
The movement counting setting (v2.1 task 2.1-11b, 9 Nov 2026; John's Q1-Q7 and questions A-G, all as recommended):
backend/counting.py, planning.count_visit_as, the council bands' movements_unit, and where the setting reaches.

WHAT IS ASSERTED
----------------
  * counting.py: per_visit / unit from planning.count_visit_as (absent, rubbish or out of range = 2), setting_problem,
    convert (movements = visits x 2; None stays None; a bad unit is refused), from_visits, on_road (each pass under 2,
    once under 1), the words for each unit (no "two-way"; the cap's words always visits, Q4);
  * the seed factors.json carries count_visit_as 2 (live takes 2 movements on merge, question F);
  * config.validate refuses a count that is not 1 or 2 and a movements_unit that is not movements or visits;
  * config.council_breaks reads the bands in the organisation's count: the defaults and bands typed with no unit are
    visits (x2 under 2), bands typed in movements are read as typed under 2 and halved under 1, never below 1;
  * the reach (source): /api/meta and /api/public/alignment send counting.words(); the map's PV() / CW() read
    TENANT.counting; the Dashboard / Config read meta.counting / planning.count_visit_as; the CLP, Gate arrivals,
    Look-ahead and Simulation stay in vehicles / visits (Q3).

WHAT THIS DOES NOT PROVE
------------------------
The road-section, council, bulletin and map figures under each setting are asserted where they are built
(test_road_sections, test_areas, test_bulletin, parse_map). Nothing here runs the app over HTTP (http_smoke does).

Run:  python3 backend/tests/test_counting.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import counting  # noqa: E402
import config    # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {detail}"[:600])


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ---- 1. the setting ---------------------------------------------------------------------------------------------------
P = lambda v: {"planning": {"count_visit_as": v}}
ok("1: absent, an empty document, rubbish or out of range = 2 movements a visit (the default, John's Q1)",
   counting.per_visit({}) == 2 and counting.per_visit({"planning": {}}) == 2 and counting.per_visit(P(None)) == 2
   and counting.per_visit(P("x")) == 2 and counting.per_visit(P(3)) == 2 and counting.per_visit(P(0)) == 2
   and counting.DEFAULT_PER_VISIT == 2)
ok("1: 1 and 2 are read as set (a string from a form too)",
   counting.per_visit(P(1)) == 1 and counting.per_visit(P(2)) == 2 and counting.per_visit(P("1")) == 1)
ok("1: the unit follows: 2 = movements, 1 = visits",
   counting.unit(P(2)) == "movements" and counting.unit(P(1)) == "visits" and counting.unit({}) == "movements")
ok("1: setting_problem: None for absent, 1, 2; one sentence for anything else (a bool is not a number here)",
   counting.setting_problem(None) is None and counting.setting_problem(1) is None and counting.setting_problem(2) is None
   and counting.setting_problem(3) == counting.setting_problem("2") == counting.setting_problem(True)
   == "planning.count_visit_as must be 1 or 2 (or left out)")

# ---- 2. convert (Q5: the one place a figure changes unit; 2.1-1's limits call it) --------------------------------------
ok("⭐ 2: convert: movements = visits x 2, both ways, never rounded; the same unit unchanged; None stays None",
   counting.convert(25, "visits", "movements") == 50.0 and counting.convert(51, "movements", "visits") == 25.5
   and counting.convert(7, "visits", "visits") == 7.0 and counting.convert(None, "visits", "movements") is None
   and counting.convert("40", "movements", "visits") == 20.0)
try:
    counting.convert(1, "lorries", "visits")
    _bad = False
except ValueError:
    _bad = True
ok("2: convert refuses a unit it does not know", _bad)
ok("2: from_visits: loads in the organisation's count", counting.from_visits(10, pv=2) == 20.0 and counting.from_visits(10, pv=1) == 10.0
   and counting.from_visits(None, pv=2) is None and counting.from_visits(3, P(1)) == 3.0)
ok("⭐ 2 (question A): on_road counts each pass under 2 (in + out), a route once under 1 (either leg)",
   counting.on_road(10, True, True, 2) == 20.0 and counting.on_road(10, True, False, 2) == 10.0
   and counting.on_road(10, False, True, 2) == 10.0 and counting.on_road(10, False, False, 2) == 0.0
   and counting.on_road(10, True, True, 1) == 10.0 and counting.on_road(10, False, True, 1) == 10.0
   and counting.on_road(10, False, False, 1) == 0.0)

# ---- 3. the words ------------------------------------------------------------------------------------------------------
W2, W1 = counting.words(P(2)), counting.words(P(1))
ok("⭐ 3: the words of each count: 'Lorry movements a day' (2) / 'Lorry visits a day' (1), with per_visit and unit",
   W2["label"] == "Lorry movements a day" and W2["per_visit"] == 2 and W2["unit"] == "movements"
   and W1["label"] == "Lorry visits a day" and W1["per_visit"] == 1 and W1["unit"] == "visits"
   and W2["col"] == "Movements a day" and W1["col"] == "Visits a day", json.dumps([W2, W1])[:300])
ok("3: words_for(pv) is words() for a known count", counting.words_for(2) == W2 and counting.words_for(1) == W1)
ok("⭐ 3 (Q2): 'two-way' is retired from every word the setting gives", "two-way" not in json.dumps(counting.WORDS).lower())
ok("3 (Q7): each count's sources line says how the bulletin counts",
   W2["sources"].startswith("Movements: this bulletin counts an HGV arriving and leaving as 2 movements, as council conditions do;")
   and W1["sources"].startswith("Visits: this bulletin counts an HGV arriving and leaving once, as a visit"))
ok("3 (Q4): a route cap is always lorry visits a day", counting.CAP_UNIT_WORDS == "lorry visits a day")
ok("3: the area and road bases say what they count",
   "each leg of a route that enters an area is one movement a load" in counting.area_basis(2)
   and "each lorry once" in counting.area_basis(1) and counting.road_basis(2) and counting.road_basis(1))
_bad_words = re.compile(r"\b(truck|real-time|AI|optimi[sz]e|predict|telematics|secure)\b", re.I)
ok("3: the words pass the public-word rule (lorry, never truck; no banned word)", not _bad_words.search(json.dumps(counting.WORDS)))

# ---- 4. the seed and the checks ---------------------------------------------------------------------------------------
SEED = json.loads(read("backend/factors.json"))
ok("⭐ 4 (question F): the seed counts a visit as 2 movements, so live takes 2 on merge with no re-import",
   SEED["planning"].get("count_visit_as") == 2)
ok("4: validate refuses a count that is not 1 or 2, accepts 1, 2 and none",
   "planning.count_visit_as must be 1 or 2 (or left out)" in config.validate(dict(SEED, planning=dict(SEED["planning"], count_visit_as=3)))
   and not any("count_visit_as" in x for x in config.validate(dict(SEED, planning=dict(SEED["planning"], count_visit_as=1))))
   and not any("count_visit_as" in x for x in config.validate(SEED)))
_t = lambda cb: dict(SEED, tenant=dict(SEED.get("tenant") or {}, council_breaks=cb))
ok("4: validate refuses a movements_unit that is not movements or visits; accepts both",
   "tenant.council_breaks.movements_unit must be movements or visits" in config.validate(_t({"movements": [10, 20, 30], "movements_unit": "lorries"}))
   and not any("movements_unit" in x for x in config.validate(_t({"movements": [10, 20, 30], "movements_unit": "visits"})))
   and not any("movements_unit" in x for x in config.validate(_t({"movements": [10, 20, 30], "movements_unit": "movements"}))))

# ---- 5. the council bands in the organisation's count (question B) ------------------------------------------------------
CB = config.council_breaks
ok("⭐ 5: the default bands are visits: 100 / 200 / 400 movements under 2, 50 / 100 / 200 visits under 1",
   CB({})["movements"] == [100, 200, 400] and CB(P(1))["movements"] == [50, 100, 200]
   and CB({})["carbon"] == [50, 100, 200] and CB(P(1))["carbon"] == [50, 100, 200])
_live = {"tenant": {"council_breaks": {"movements": [25, 50, 100], "carbon": [10, 25, 50]}}}       # live's R3b bands, typed before
ok("⭐ 5: bands typed before the setting (no unit) are visits: live's 25 / 50 / 100 read 50 / 100 / 200 movements; carbon untouched",
   CB(_live) == {"movements": [50, 100, 200], "carbon": [10, 25, 50]}
   and CB(dict(_live, planning={"count_visit_as": 1}))["movements"] == [25, 50, 100])
_mv = lambda pv: {"planning": {"count_visit_as": pv}, "tenant": {"council_breaks": {"movements": [3, 50, 100], "movements_unit": "movements"}}}
ok("5: bands typed in movements are read as typed under 2, halved under 1 and never below 1",
   CB(_mv(2))["movements"] == [3, 50, 100] and CB(_mv(1))["movements"] == [2, 25, 50]
   and CB({"planning": {"count_visit_as": 1}, "tenant": {"council_breaks": {"movements": [1, 50, 100], "movements_unit": "movements"}}})["movements"][0] == 1)
ok("5: bands that are not three rising figures fall back to the default, read in the count",
   CB({"tenant": {"council_breaks": {"movements": [30, 20, 10], "movements_unit": "movements"}}})["movements"] == [100, 200, 400])

# ---- 6. where the setting reaches (source) ------------------------------------------------------------------------------
MAIN = read("backend/main.py")
MAP = read("map/index.html")
APP = read("frontend/index.html")
ok("⭐ 6: /api/meta and the public map's alignment send the organisation's count",
   '"counting": counting.words(factors),' in MAIN and 'tenant["counting"] = counting.words()' in MAIN)
ok("6: the public map reads it through PV() / CW() (absent = 2)",
   "const PV = () => (TENANT.counting && Number(TENANT.counting.per_visit) === 1 ? 1 : 2);" in MAP)
ok("6: the Dashboard reads meta.counting; Config edits planning.count_visit_as with its own switch",
   "const countPV = (meta) => (meta && meta.counting && Number(meta.counting.per_visit) === 1 ? 1 : 2);" in APP
   and 'data-cfg="count-visit-as"' in APP and "d.planning.count_visit_as = pv;" in APP)
# Q3: the CLP's figures, Gate arrivals, the Look-ahead and the Simulation stay in vehicles / visits
_stay = {f: read(f"backend/{f}") for f in ("clp_doc.py", "lookahead.py", "sim.py", "gate_arrivals.py") if os.path.exists(os.path.join(BACKEND, f))}
ok("⭐ 6 (Q3): the CLP document, Look-ahead, Simulation and Gate arrivals do not read the setting",
   len(_stay) >= 3 and not any(re.search(r"\bcounting\.(per_visit|words|unit|from_visits|on_road)\b", t) for t in _stay.values()),
   ", ".join(k for k, t in _stay.items() if re.search(r"\bcounting\.", t)))
ok("6 (Q4): the cap chart in CLP monitoring says lorry visits a day", "lorry visits a day" in read("backend/clp.py").lower())

for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
