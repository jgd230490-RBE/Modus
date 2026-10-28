"""
The demo programme (17 Oct 2026, demo redesign R2; the design: notes/demo-redesign-1016.md, decisions D95–D114).
The shipped demo package is a four-year programme on the fictional Wolds Link: main works from January 2026, the north
open December 2028, the whole road October 2029, finishing works to December 2030. The other harnesses re-pin what they
already read from the package; this one asserts the DESIGN itself, so a regeneration that drifts from it fails here.

WHAT IS ASSERTED
----------------
  * the calendar: months 1–60 only; the north starts first (WS6, January 2026); no WS1–WS3 earthworks line before the
    southern earthworks season opens (April 2027, D111); no thin surface course October–March (SHW 945); asphalt within
    the fictional plant's reach (≤ 56,000 t in every month, D99); the South Team under 10 loads a day before April 2027
    (D80); at least two routes with lines in every month to December 2030;
  * the totals the note's §1.5 quotes (905 line-months, 2,722,900 t, 100,839 loads, 114,000 m³ of concrete), by the
    app's own load rule (loads = ceil(tonnes ÷ the vehicle's payload) per line-month, concrete at 2.4 t/m³);
  * the asphalt plant's feed on its own category (D112): only the two quarry-to-plant routes carry it, its material
    class is null on purpose, and the carbon read counts its haulage but no material carbon;
  * the history typed to the shipped as-of date (Thu 26 Nov 2026, D96): read through the app's own Look-ahead with the
    harness's date pinned (D104), the as-of week shows EXACTLY three SHORTAGE lines, one DAYS_NE_WEEK and one
    PARENT_CHANGED; no stockpile is over capacity; every compound's stock stays bounded (they use what arrives);
  * the sites: every invented site says "(fictional)", every site lies inside the nine shipped council areas, the
    asphalt plant has a type of its own;
  * the generator's own constants agree with the harnesses' pinned date, and its --as-of guard is in place.

WHAT THIS DOES NOT PROVE
------------------------
That the programme is realistic: that is the note's §1.6 (sourced comparators, and every ASSUMPTION it marks). Nothing
here is baked (no route geometry ships), so no transport figure, no gate queue and no Volume map is read; a live refresh
(--as-of) is not built here.

Run:  python3 backend/tests/test_demo_programme.py
"""
import datetime
import json
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

for _v in ("DATABASE_URL", "HERE_API_KEY", "MAPBOX_TOKEN"):
    os.environ.pop(_v, None)
os.environ["TENANT_ID"] = "default"
TMP = tempfile.mkdtemp(prefix="demo_programme_")

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "programme.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import stockpiles  # noqa: E402
import weeks  # noqa: E402
import lookahead  # noqa: E402
import carbon  # noqa: E402
import areas  # noqa: E402
from portable import pin_today, DEMO_AS_OF, remove_scratch_db  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


PKG = json.loads(read("demo/uk-corridor.package.json"))
T = PKG["tables"]
FAC = json.loads(next(r["value"] for r in T["config"] if r["key"] == "factors"))
PAYLOAD = {k: float(v["payload_t"]) for k, v in FAC["vehicles"].items() if isinstance(v, dict) and v.get("payload_t")}
WD = float(FAC["planning"]["working_days_per_month"])
LOC = {l["id"]: l for l in T["locations"]}
RTE = {r["id"]: r for r in T["routes"]}
TEAM = {r["id"]: r["label"] for r in T["ipts"]}
APPROVED = [f for f in T["forecasts"] if f["status"] == "Approved"]


def month_of_year(m):
    return (int(m) - 1) % 12 + 1


def tonnes(f):
    return float(f["quantity"]) * (2.4 if f["unit"] == "m3" else 1.0)


def loads(f):
    return math.ceil(tonnes(f) / PAYLOAD[f["vehicle_type"]] - 1e-9)


# =========================================================================== #
#  1. The calendar                                                             #
# =========================================================================== #
ok("⭐ every forecast line sits in months 1–60 (Jan 2026 – Dec 2030), and every one of the 60 months carries work",
   all(1 <= int(f["month_index"]) <= 60 for f in T["forecasts"])
   and {int(f["month_index"]) for f in APPROVED} == set(range(1, 61)))
_first = min(int(f["month_index"]) for f in APPROVED)
ok("⭐ the north starts first: the earliest month is January 2026 and every line in it is WS6's (D78)",
   _first == 1 and {f["section_id"] for f in APPROVED if int(f["month_index"]) == 1} == {"WS6"})
_south_early = [f for f in APPROVED if f["section_id"] in ("WS1", "WS2", "WS3") and f["discipline"] == "earthworks"
                and int(f["month_index"]) < 16]
ok("⭐ no WS1–WS3 earthworks line before April 2027, the southern earthworks season (D111)", not _south_early,
   str([(f["route_id"], f["month_index"]) for f in _south_early][:5]))
_sc = [f for f in APPROVED if "surface course" in (f["material_description"] or "").lower()]
ok("⭐ the thin surface course is laid April–September only (SHW 945), and there is some",
   _sc and all(4 <= month_of_year(f["month_index"]) <= 9 for f in _sc),
   str(sorted({month_of_year(f["month_index"]) for f in _sc})))
_asp = {}
for f in APPROVED:
    if f["material_type"] == "Asphalt":
        _asp[int(f["month_index"])] = _asp.get(int(f["month_index"]), 0.0) + tonnes(f)
ok("⭐ asphalt stays within the fictional 340 t/h plant: at most 56,000 t in any month (the peak 55,400 t, Aug 2028)",
   _asp and max(_asp.values()) <= 56000 and max(_asp.values()) == 55400 and max(_asp, key=_asp.get) == 32, str(max(_asp.values())))
_south = {}
for f in APPROVED:
    if TEAM[f["ipt"]] == "South Team" and int(f["month_index"]) < 16:
        _south[int(f["month_index"])] = _south.get(int(f["month_index"]), 0) + loads(f)
ok("⭐ the South Team runs under 10 loads a day before April 2027 (it only sets up Harborough Compound, D80)",
   _south and all(v / WD < 10 for v in _south.values()), str({m: round(v / WD, 1) for m, v in _south.items()}))
_rpm = {}
for f in APPROVED:
    _rpm.setdefault(int(f["month_index"]), set()).add(f["route_id"])
ok("⭐ at least two routes carry lines in every month to December 2030",
   all(len(_rpm.get(m, ())) >= 2 for m in range(1, 61)), str({m: len(v) for m, v in _rpm.items() if len(v) < 2}))
ok("the whole road opens in October 2029: no Type 1 sub-base, base or binder course is delivered after September 2029",
   not [f for f in APPROVED if int(f["month_index"]) > 45 and f["section_id"] in ("WS1", "WS2", "WS3")
        and any(w in (f["material_description"] or "") for w in ("Type 1 sub-base", "base and binder"))])
ok("the north opens in December 2028: no WS4–WS6 pavement line after November 2028 until the finishing works",
   not [f for f in APPROVED if 36 <= int(f["month_index"]) <= 45 and f["section_id"] in ("WS4", "WS5", "WS6")
        and f["discipline"] == "superstructure"])

# =========================================================================== #
#  2. The totals the note quotes (§1.5)                                        #
# =========================================================================== #
# RE-PINNED 28 Oct 2026 (simulation v2, the Tilton Viaduct site L019): + 7 routes (R044–R050) and 24 line-months of its own,
# + 13 where the viaduct's concrete and reinforcement left the compound's summed lines: 942 on 49 routes
ok("⭐ 942 approved line-months on 49 routes (R020, the Carbon planner's alternative, carries none)",
   len(APPROVED) == 942 and len({f["route_id"] for f in APPROVED}) == 49
   and "R020" not in {f["route_id"] for f in APPROVED} and len(T["routes"]) == 50)
ok("⭐ 2,745,500 t over the programme (concrete at 2.4 t/m³; RE-PINNED 28 Oct: + 22,600 t for the viaduct site) and 114,000 m³ of ready-mixed concrete",
   round(sum(tonnes(f) for f in APPROVED)) == 2745500
   and round(sum(float(f["quantity"]) for f in APPROVED if f["unit"] == "m3")) == 114000)
_lt = {}
for f in APPROVED:
    _lt[TEAM[f["ipt"]]] = _lt.get(TEAM[f["ipt"]], 0) + loads(f)
ok("⭐ 101,641 loads by the app's rule: North 49,932 (RE-PINNED 28 Oct: + 802 for the viaduct site), Central 32,893, South 18,816",
   sum(_lt.values()) == 101641 and _lt == {"North Team": 49932, "Central Team": 32893, "South Team": 18816}, str(_lt))
_byk = {}
for f in APPROVED:
    _byk.setdefault((f["route_id"], f["discipline"], f["section_id"]), set()).add(f["vehicle_type"])
ok("every line keeps one vehicle across its months (a line is route, discipline and section)",
   all(len(v) == 1 for v in _byk.values()))

# =========================================================================== #
#  3. The asphalt plant's feed (D112)                                          #
# =========================================================================== #
FEED = "Aggregate for the asphalt plant"
_fl = [f for f in APPROVED if f["material_type"] == FEED]
_ap = [l["id"] for l in T["locations"] if l["loc_type"] == "Asphalt plant"]
ok("⭐ the feed rides its own category, only on the two quarry-to-plant routes (R027 Northfield, R028 Kilby Ridge)",
   _fl and {f["route_id"] for f in _fl} == {"R027", "R028"} and len(_ap) == 1
   and all(RTE[r]["dest_id"] == _ap[0] and RTE[r]["material_category"] == FEED for r in ("R027", "R028"))
   and all(f["vehicle_type"] == "Artic Tipper (44t)" and f["unit"] == "t" for f in _fl))
ok("...535,600 t in all: 0.95 t of rock per tonne of asphalt the plant makes, booked to the section it is for",
   round(sum(tonnes(f) for f in _fl)) == 535600
   and {f["section_id"] for f in _fl} == {f["section_id"] for f in APPROVED if RTE[f["route_id"]]["origin_id"] == _ap[0]})
ok("...its material class is null ON PURPOSE (the asphalt's own factor covers the rock), present, never absent",
   "carbon_material" in FAC["material_categories"][FEED] and FAC["material_categories"][FEED]["carbon_material"] is None
   and FAC["material_categories"][FEED].get("units") == ["t"])

# =========================================================================== #
#  4. The history to the shipped as-of date, through the app                   #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
_res = tenant_package.import_tenant(PKG, replace=True)
ok("the package imports into an empty tenant", _res.get("ok") is True, str(_res)[:200])
config.invalidate()
_PIN = pin_today(DEMO_AS_OF)
_ACC = {"role": "planner", "ipt": None}
_pg = lookahead.page(acc=_ACC, with_restrictions=False)
_fl_by = {}
for x in (_pg.get("clashes") or {}).get("flags") or []:
    _fl_by.setdefault(x["code"], []).append(x)
ok("⭐ D104: with the date pinned to the shipped as-of date the commit week is Nov W4 2026 (23–29 Nov)",
   (_pg.get("commit_week") or {}).get("month_index") == 11 and (_pg.get("commit_week") or {}).get("week_index") == 4
   and (_pg.get("commit_week") or {}).get("from") == "2026-11-23", str(_pg.get("commit_week")))
_short = sorted({(x.get("route_id"), x.get("section_id")) for x in _fl_by.get("SHORTAGE", [])})
ok("⭐ the account week typed EXACTLY three short lines, so EXACTLY three lines show SHORTAGE (R001, R011, R018)",
   _short == [("R001", "WS1"), ("R011", "WS6"), ("R018", "WS5")], str(_short))
ok("...one South Team line's day split typed 10 t short of its week (DAYS_NE_WEEK) and one Central Team line raised "
   "after its week was set (PARENT_CHANGED)",
   len(_fl_by.get("DAYS_NE_WEEK", [])) == 1 and len(_fl_by.get("PARENT_CHANGED", [])) == 1,
   str({k: len(v) for k, v in _fl_by.items()}))
_wk = T["forecast_weeks"]
_acct = [w for w in _wk if (w["month_index"], w["week_index"]) == (11, 3) and w["actual_qty"] is not None]
ok("...and every other account-week line held (≥ 98 % of its plan): the shortage is on the chosen lines only",
   _acct and sum(1 for w in _acct if float(w["actual_qty"]) < 0.98 * float(w["planned_qty"])) == 3)
_days = T["forecast_days"]
ok("the as-of week carries day actuals Monday to Wednesday only (the days before the as-of Thursday)",
   _days and {d["day_date"] for d in _days if d.get("actual_qty") is not None} == {"2026-11-23", "2026-11-24", "2026-11-25"})
_bal = stockpiles.balances(1, 11)
_over = [(s["name"], w["month_index"], w["week_index"]) for s in _bal["stockpiles"] for w in s["weeks"] if w["over"]]
ok("⭐ no stockpile goes over capacity in the shipped history (the flag shows only on a live refresh, §1.9)", not _over, str(_over[:3]))
_comp = {s["name"]: max(w["balance_end"] for w in s["weeks"]) for s in _bal["stockpiles"] if s["loc_type"] == "Compound"}
ok("⭐ the compounds' stock stays bounded (they use what arrives): never below 0, never above 5,000 t",
   len(_comp) == 4 and all(0 <= v <= 5000 for v in _comp.values())
   and all(w["balance_end"] >= -1e-6 for s in _bal["stockpiles"] for w in s["weeks"]), str(_comp))
ok("the stockpiles open empty on 1 January 2026 (§1.8) at 60,000 / 40,000 / 25,000 t",
   {s["name"]: (s["capacity_qty"], s["opening_qty"]) for s in _bal["stockpiles"] if s["loc_type"] == "Stockpile"}
   == {"Stockpile South": (60000.0, 0.0), "Stockpile Tilton": (40000.0, 0.0), "Stockpile North": (25000.0, 0.0)})
_sc = carbon.scenario(_ACC, alternatives=[], status="Approved")
_cats = _sc["baseline"].get("by_category")
_cats = {c["category"]: c for c in _cats} if isinstance(_cats, list) else (_cats or {})
ok("⭐ the carbon read gives the feed NO material carbon (counted once, in the asphalt) and prices the asphalt itself",
   FEED in _cats and _cats[FEED]["carbon_material"] is None and (_cats[FEED]["material_t"] or 0) == 0
   and round(_cats[FEED]["tonnes"]) == 535600 and (_cats["Asphalt"]["material_t"] or 0) > 0, str(_cats.get(FEED))[:200])

# =========================================================================== #
#  5. The sites                                                                #
# =========================================================================== #
_kept = {"Kilby Ridge Quarry", "Northfield Quarry", "Brook Pit", "Harborough Rail Freight Terminal", "Harborough Compound",
         "Langton Compound", "Tilton Compound", "Melton Compound", "Stockpile South", "Stockpile Tilton", "Stockpile North"}
# NARROWED 22 Oct 2026 (abnormal loads, phase 3, D75): eighteen — the precast works and the crane depot the three abnormal loads start from
ok("⭐ nineteen sites (RE-PINNED 28 Oct: + the Tilton Viaduct site): the eleven named after places, and every other one says \"(fictional)\" in its name",
   len(T["locations"]) == 19 and {l["name"] for l in T["locations"]} >= _kept
   and all("(fictional)" in l["name"] for l in T["locations"] if l["name"] not in _kept))
ok("⭐ D75 (phase 3): the three fictional abnormal loads ship in the package — the 4.6 m units (approved) from the rail terminal to Langton Compound, the 72 t crane (pending, in and out) from the crane depot and the 32 m beams (pending, a Special Order) from the precast works to Melton Compound; the two new sites with a gate each; nothing routed in the file (a planner draws on live)",
   [(m["id"], m["status"], m["origin_id"], m["dest_id"], bool(m.get("return_abnormal")), m.get("geometry_json")) for m in T["abnormal_loads"]]
   == [("AL001", "approved", "L004", "L006", False, None), ("AL002", "pending", "L018", "L008", True, None), ("AL003", "pending", "L017", "L008", False, None)]
   and {(l["id"], l["name"], l["loc_type"]) for l in T["locations"] if l["id"] in ("L017", "L018")}
   == {("L017", "Earl Shilton Precast Works (fictional)", "Precast works"), ("L018", "Soar Valley Crane Hire (fictional)", "Depot")}
   and {g["name"] for g in T["location_gates"] if g["location_id"] in ("L017", "L018")} == {"Works gate", "Depot gate"}
   and [m["gross_t"] for m in T["abnormal_loads"]] == [40.0, 72.0, 78.0] and all("fictional" in (m.get("note") or "") for m in T["abnormal_loads"]),
   str([(m["id"], m["status"], m["origin_id"], m["dest_id"]) for m in T.get("abnormal_loads", [])]))
ok("...the two new ones as designed: the asphalt plant (its own type) and Welland Ready-Mix (a batching plant)",
   {(l["id"], l["name"], l["loc_type"]) for l in T["locations"] if l["id"] in ("L015", "L016")}
   == {("L015", "Wolds Link Asphalt Plant (fictional)", "Asphalt plant"), ("L016", "Welland Ready-Mix (fictional)", "Batching plant")})
_areas = [areas.Area(a["area_id"], json.loads(a["geometry_json"])) for a in T["areas"]]
ok("⭐ every site lies inside the nine shipped council areas (the By council view counts all sixteen)",
   len(_areas) == 9 and all(any(a.contains(l["lon"], l["lat"]) for a in _areas) for l in T["locations"]),
   str([l["name"] for l in T["locations"] if not any(a.contains(l["lon"], l["lat"]) for a in _areas)]))
ok("every gate is open Monday to Friday at least, with its hours typed (§1.8), and one default per site",
   all(g["open_from"] and g["open_to"] and (g["open_days"] or "")[:5] == "11111" for g in T["location_gates"])
   and all(sum(1 for g in T["location_gates"] if g["location_id"] == l["id"] and g["is_default"]) == 1 for l in T["locations"]))

# =========================================================================== #
#  5b. 27 Oct 2026 — the stockpile story (stockpile forecast, plan §6, D11)    #
# =========================================================================== #
import stockpiles  # noqa: E402
import weeks  # noqa: E402
_bal = {s_["name"]: s_ for s_ in stockpiles.balances(1, 60)["stockpiles"]}
_wo = lambda w: weeks.week_span(w["month_index"], w["week_index"])[0].isoformat() if w else None
ok("⭐ the package carries a planned use for each of the three stockpiles (stockpile_plan)",
   {r["location_id"] for r in T.get("stockpile_plan", [])} == {_bal[n]["location_id"] for n in
                                                              ("Stockpile South", "Stockpile Tilton", "Stockpile North")},
   str(len(T.get("stockpile_plan", []))))
# 28 Oct 2026 (task 0b): the plan is a LAYING PROGRAMME (a rate a week, winter pace, a residue) and the history drifts
# from it, so the three stockpiles tell three different stories. The 27 Oct assertions on Tilton and North are narrowed
# to these (Tilton no longer goes over: it is the pile that runs short and is topped up; North stays the pile that goes
# over, now for months, not weeks).
_N, _T, _S = _bal["Stockpile North"], _bal["Stockpile Tilton"], _bal["Stockpile South"]
ok("⭐ Stockpile North fills over the winter (no capping laid Nov-Mar) and goes over its 25 000 t in the week of 22 Mar 2027",
   _wo(_N["first_over"]) == "2027-03-22" and 25000 < _N["first_over"]["balance_end"] < 27000, str(_N["first_over"]))
_nover = [w for w in _N["weeks"] if w["over"]]
ok("...and stays over for months (about 17 weeks), not a week (the laying rate is below the arrivals), peaking 105-110 % of its capacity",
   14 <= len(_nover) <= 30 and 105 <= _N["peak_pct"] <= 110 and _wo(_nover[-1]) < "2027-09-01",
   f"{len(_nover)} weeks, peak {_N['peak_pct']} %, last {_wo(_nover[-1])}")
ok("⭐ Stockpile Tilton runs short once and is topped up: Jul 2027's laying is planned for more than the pile can supply "
   "(a shortfall of 1 000-2 000 t from the week of 12 Jul 2027), and August's deliveries refill it",
   _T["first_empty"] is not None and _wo(_T["first_empty"]) == "2027-07-12"
   and 1000 <= sum(w["short"] for w in _T["weeks"]) <= 2000
   and not any(w["empty"] for w in _T["weeks"] if w["month_index"] > 19)
   and next(w for w in _T["weeks"] if (w["month_index"], w["week_index"]) == (20, 4))["balance_end"] > 0,
   str(_T["first_empty"]))
ok("...Stockpile Tilton is never over (its winter peak is about 60 %), Stockpile South never over or empty (peak under 50 %): "
   "the healthy pile",
   _T["first_over"] is None and _T["peak_pct"] < 70 and _S["first_over"] is None and _S["first_empty"] is None
   and _S["peak_pct"] < 50 and _N["first_empty"] is None, f"{_T['peak_pct']} {_S['peak_pct']}")
_cnt = [(n_, w["month_index"], w["week_index"], w["count_adjust"]) for n_, s_ in _bal.items() for w in s_["weeks"]
        if w.get("count") is not None]
ok("...two stock counts: Tilton the week of 14 Sep 2026, about 180 t MORE than the book; North the week of 9 Nov 2026, "
   "about 240 t LESS",
   sorted(_cnt) == sorted([("Stockpile Tilton", 9, 3, _cnt[[c[0] for c in _cnt].index("Stockpile Tilton")][3]),
                           ("Stockpile North", 11, 2, _cnt[[c[0] for c in _cnt].index("Stockpile North")][3])])
   and len(_cnt) == 2 and all(c[0] != "Stockpile Tilton" or abs(c[3] - 180) < 2 for c in _cnt)
   and all(c[0] != "Stockpile North" or abs(c[3] + 240) < 2 for c in _cnt), str(_cnt))
_past = [w for s_ in (_T, _N) for w in s_["weeks"] if w["basis"] == "recorded" and w["consumed"] > 0]
ok("...the history carries ACTUAL laying that differs from the plan: of the weeks typed, most differ from the planned use "
   "by 5 % or more, with both over and under (rain weeks and catch-up weeks)",
   len(_past) >= 25 and sum(1 for w in _past if abs(w["consumed"] - w["plan_out"]) > 0.05 * max(1, w["plan_out"])) > len(_past) / 2
   and any(w["consumed"] > w["plan_out"] * 1.1 for w in _past) and any(w["consumed"] < w["plan_out"] * 0.8 for w in _past),
   f"{len(_past)} weeks")
ok("...the four compounds and the railhead keep the records-only figure (no capacity, no plan)",
   all(not s_["forecast"] for n, s_ in _bal.items() if not n.startswith("Stockpile ")))
_gen0 = read("backend/tools/make_demo_tenant.py")
ok("the generator: the laying programme (LAY_RATE, WINTER_PACE, PLAN_SURGE, COUNTS, ACTUAL_PACE) and the plan from it",
   all(x in _gen0 for x in ("LAY_RATE = {", "WINTER_PACE = {", "PLAN_SURGE = {", "COUNTS = [", "ACTUAL_PACE = {",
                            "def lay_draw(", "def actual_draw(", "def stock_plan_rows(loc):"))
   and "LAY_SHARE" not in _gen0)

# =========================================================================== #
#  6. The generator agrees                                                     #
# =========================================================================== #
_gen = read("backend/tools/make_demo_tenant.py")
ok("the generator's shipped as-of date is the date the harnesses pin (portable.DEMO_AS_OF)",
   f'SHIPPED_AS_OF = "{DEMO_AS_OF.isoformat()}"' in _gen and _PIN == DEMO_AS_OF == datetime.date(2026, 11, 26))
ok("...and it refuses another as-of date (or a live export) unless --out is outside the checkout",
   'ap.add_argument("--as-of"' in _gen and 'ap.add_argument("--live-export"' in _gen
   and "need --out to a path OUTSIDE the" in _gen and "def _outside_checkout(path):" in _gen)
ok("...and the package's readme names the as-of date it was built for", "2026-11-26" in PKG.get("_readme", ""))
# 18 Oct 2026 (R3b): the council colour bands re-chosen from the live four-year demo's district figures (60 months,
# after the first live bake) ship in the package for BOTH measures, and the generator says where they came from
ok("⭐ R3b: the package's council bands are the ones chosen from the live four-year figures — movements 25 / 50 / 100 a "
   "day, carbon 10 / 25 / 50 t in the month — and the generator records why",
   FAC.get("tenant", {}).get("council_breaks") == {"movements": [25, 50, 100], "carbon": [10, 25, 50]}
   and '"council_breaks": {"movements": [25, 50, 100], "carbon": [10, 25, 50]}' in _gen
   and "18 Oct 2026 (R3b)" in _gen, str(FAC.get("tenant", {}).get("council_breaks")))

# =========================================================================== #
#  7. A live refresh keeps what only live has (28 Oct 2026, the demo F6)       #
# =========================================================================== #
# The generator is loaded last: it points db at its own scratch file, after this harness is done with its own.
import copy as _copy  # noqa: E402
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("make_demo_tenant_f6", os.path.join(BACKEND, "tools", "make_demo_tenant.py"))
GEN = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(GEN)

_xmas = {z["name"]: z for z in PKG["tables"]["zones"] if "Christmas trading" in z["name"]}
ok("⭐ F4: Christmas trading 2027 in Market Harborough DIVERTS routes in its dates (as ticked on live, 28 Oct); 2028 stays "
   "advisory",
   _xmas.get("Market Harborough town centre: Christmas trading 2027", {}).get("affects_routing") in (1, True)
   and _xmas.get("Market Harborough town centre: Christmas trading 2028", {}).get("affects_routing") in (0, False)
   and (_xmas.get("Market Harborough town centre: Christmas trading 2027") or {}).get("starts_on") == "2027-12-01",
   str({k: v.get("affects_routing") for k, v in _xmas.items()}))
_empty = sorted(t for t, rows in PKG["tables"].items() if not rows)
ok("⭐ F6: every table the shipped package leaves empty (made on live: baked, fetched, chosen) is one a refresh copies "
   "from live — so a new live-only table cannot be dropped by a refresh unnoticed",
   set(_empty) <= set(GEN.LIVE_TABLES), f"empty {_empty}; LIVE_TABLES {GEN.LIVE_TABLES}")
ok("...route_choice (the diversions, task 0c) and traffic_counts are among them",
   "route_choice" in GEN.LIVE_TABLES and "traffic_counts" in GEN.LIVE_TABLES)


def _live_export(mutate=None):
    """A stand-in for a live export: the shipped package as Postgres hands it out (BOOLEAN columns true / false), with
    what only live has: a diversion, a traffic count, two drawn abnormal loads."""
    live = _copy.deepcopy(PKG)
    for t, rows in live["tables"].items():
        for r in rows:
            for c in ("affects_routing", "active", "return_abnormal", "indivisible", "axle_driving", "cu_vehicle"):
                if c in r and r[c] in (0, 1):
                    r[c] = bool(r[c])
    lt = live["tables"]
    lt["route_choice"] = [{"tenant_id": "default", "route_id": "R012", "zone_id": "Z038", "status": "applied"}]
    lt["traffic_counts"] = [{"tenant_id": "default", "id": "CP1", "aadf_hgv": 812}]
    ab = lt["abnormal_loads"]
    for r in ab:
        r["geometry_json"] = '[[-0.9, 52.5], [-0.8, 52.6]]'
        r["distance_km"] = 12.3
        r["pinch_json"] = '[{"what": "bridge"}]'
        r["baked_at"] = "2026-10-22T22:30:00Z"
    if len(ab) > 1:
        ab[1]["width_m"] = (ab[1].get("width_m") or 3.0) + 1.0      # this load's size changed since it was drawn
    if mutate:
        mutate(lt)
    return live


def _refresh(live):
    path = os.path.join(TMP, "live-export-f6.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(live, f)
    pkg = _copy.deepcopy(PKG)
    GEN.copy_live_tables(pkg, path)
    return pkg


try:
    _r = _refresh(_live_export())
    _err = None
except SystemExit as e:
    _r, _err = None, str(e)
ok("F6: a live export from Postgres (BOOLEAN columns true / false) is not refused when its zones, routes and gates are "
   "the package's", _r is not None, _err or "")
_rt = (_r or {}).get("tables", {})
ok("...its diversions (route_choice) and traffic counts come across",
   _rt.get("route_choice") == [{"tenant_id": "default", "route_id": "R012", "zone_id": "Z038", "status": "applied"}]
   and _rt.get("traffic_counts", [{}])[0].get("aadf_hgv") == 812)
_ab = _rt.get("abnormal_loads") or []
ok("...an abnormal load drawn on live keeps its drawing (line, distance, pinch points, when drawn)",
   len(_ab) >= 2 and _ab[0].get("geometry_json") == '[[-0.9, 52.5], [-0.8, 52.6]]' and _ab[0].get("distance_km") == 12.3
   and _ab[0].get("pinch_json") == '[{"what": "bridge"}]' and _ab[0].get("baked_at") == "2026-10-22T22:30:00Z",
   str([(a.get("id"), a.get("distance_km")) for a in _ab]))
ok("...but one whose size changed since it was drawn is left undrawn (the drawing would be for another lorry)",
   len(_ab) >= 2 and not _ab[1].get("geometry_json") and _ab[1].get("distance_km") is None)


def _flip_xmas(lt):
    for z in lt["zones"]:
        if z["name"] == "Market Harborough town centre: Christmas trading 2027":
            z["affects_routing"] = False


try:
    _refresh(_live_export(_flip_xmas))
    _refused = False
except SystemExit as e:
    _refused = "zones differ" in str(e)
ok("...and a live export whose zones DO differ (a routing tick not in the package) is still refused", _refused)
shutil_tmp = getattr(GEN, "TMP", None)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
if shutil_tmp:
    import shutil as _sh  # noqa: E402
    _sh.rmtree(shutil_tmp, ignore_errors=True)
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
