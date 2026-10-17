"""
Fair price, 2026-09-10 (night) — the cost MODEL (backend/fairprice.py) and its seeded coefficients.

What is asserted: the seeded block in factors.json (every coefficient with a source line
beside it, the three assumptions labelled as such); the vehicle class rule; litres per
100 km laden / empty / winter; the trip formula on the fixture geometry (EUR 113.78 —
the figure in the research note) and its components; the IRU sanity band; None — never
a guess — for an unbaked route, a missing index or a blank coefficient; the fallback from
a live document without the block to the file's; the fair figure on days, weeks, totals
and Account rows; config validation; the XLSX column; and that the supplier's PDF does
NOT carry it.

WHAT THIS DOES NOT PROVE
------------------------
  * That the coefficients are RIGHT. They are public benchmarks read on 10 Sep 2026 and
    three are assumptions; the file says which. The assertions pin what was seeded so a
    silent change is caught, not that the number is true.
  * The HTTP layer is stubbed; nothing in a browser (the JS harnesses cover the section).

Run:  python3 backend/tests/test_fairprice.py
"""
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_lookahead.py --------------------------------------
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

# G2, 16 Sep: main.py also imports Request (the overlay endpoint reads If-None-Match)
# and Response (the overlay, export and import endpoints return raw JSON / a 304).
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

TMP = tempfile.mkdtemp(prefix="rbe_fairprice_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import weeks  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import derived  # noqa: E402
import costing  # noqa: E402
import fuel  # noqa: E402
import lookahead  # noqa: E402
import export  # noqa: E402
import fairprice  # noqa: E402
import config  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
# 15 Sep: the three demo codes are opt-in on the server now (access.DEMO_ENV).
# Every harness below signs in as planner123, so it asks for them explicitly.
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
    # NARROWED (H1, 29 Sep 2026): this harness models an ESTONIAN tenant — its EE diesel
    # index and Tark Tee assertions need tenant.country = "EE" now that a tenant with no
    # country has NO automatic index (no more silent fallback to Estonia).
    import config as _h1cfg
    import conversions as _h1conv
    _h1cfg.invalidate()
    _h1cfg.seed_from_file(_h1conv)
    _h1doc = json.loads(json.dumps(_h1cfg.load(_h1conv, use_cache=False)))
    _h1doc["tenant"] = dict(_h1doc.get("tenant") or {}, country="EE")
    _h1r = _h1cfg.save(_h1doc, by="harness-h1")
    assert _h1r["ok"], _h1r
    _h1cfg.invalidate()
    try:
        import costing as _h1cst
        _h1cst.invalidate()
    except Exception:
        pass
    import config as _cfg
    _cfg.invalidate()
    costing.invalidate()




def _code_tokens(src):
    """NAME and NUMBER tokens only — docstrings and comments may NAME a thing the code must not hold."""
    import io as _io
    import tokenize
    names, nums = set(), set()
    for t in tokenize.generate_tokens(_io.StringIO(src).readline):
        if t.type == tokenize.NAME:
            names.add(t.string.lower())
        elif t.type == tokenize.NUMBER:
            try:
                nums.add(float(t.string))
            except ValueError:
                pass
    return names, nums


FACT_FILE = json.load(open(os.path.join(BACKEND, "factors.json"), encoding="utf-8"))
FP = FACT_FILE.get("fair_price") or {}

# =========================================================================== #
#  0. The seeded block — sourced, labelled, and pinned                         #
# =========================================================================== #
ok("factors.json carries a fair_price block with a README", isinstance(FP, dict) and len(FP.get("_README", "")) > 100)
ok("...every coefficient has a source line beside it",
   "_source" in (FP.get("consumption") or {}) and "_driver_source" in FP and "_vehicle_standing_source" in FP
   and "_running_source" in FP and "_margin_source" in FP and "_source" in (FP.get("season") or {}))
ok("🔴 the three unsourced numbers are LABELLED as assumptions in the file",
   all("ASSUMPTION" in FP.get(k, "") for k in ("_vehicle_standing_source", "_running_source", "_margin_source"))
   and "ASSUMPTION" not in FP.get("_driver_source", ""))
ok("...and the sourced ones name where they came from",
   "ICCT" in FP["consumption"]["_source"] and "DfT" in FP["consumption"]["_source"]
   and "Statistics Estonia" in FP["_driver_source"] and "Transpordiamet" in FP["season"]["_source"]
   and "fueleconomy.gov" in FP["season"]["_source"])
ok("the seeded values are what the research note said (a silent change is caught here)",
   FP["driver_eur_per_h"] == 20.0 and FP["vehicle_standing_eur_per_h"] == 16.0 and FP["running_eur_per_km"] == 0.12
   and FP["margin_pct"] == 8.0 and FP["consumption"]["l_per_100km_per_tonne"] == 0.4
   and FP["consumption"]["rigid"]["l_per_100km_empty"] == 27.0 and FP["consumption"]["artic"]["l_per_100km_empty"] == 23.6
   and FP["season"]["winter_months"] == [11, 12, 1, 2, 3] and FP["season"]["winter_consumption_uplift_pct"] == 8.0
   and FP["season"]["thaw_months"] == [3, 4])
ok("the standing-cost derivation is written down and arithmetically consistent (190k, 7 yr, 20 % residual, 3 %, vignette 1,100, 1,800 h)",
   abs((190000 * 0.8 / 7 + 190000 * 0.03 + 1100) / 1800 - 15.8) < 0.1 and FP.get("vehicle_new_price_eur") == 190000)
ok("🔴 the diesel price is NOT in the block — it is the live index",
   not any(("diesel" in k.lower() or "eur_per_l" in k.lower()) for k in FP if not k.startswith("_")))
_fsrc = open(os.path.join(BACKEND, "fairprice.py"), encoding="utf-8").read()
ok("fairprice.py reads no database — pure arithmetic on what derived.py hands it",
   "import db" not in _fsrc and "db." not in _fsrc.replace("db.py", ""))

# =========================================================================== #
#  1. The pure functions                                                       #
# =========================================================================== #
P = fairprice.params(FACT_FILE)
ok("params() strips the _source lines and keeps the numbers",
   P["driver_eur_per_h"] == 20.0 and "_README" not in P and "_source" not in P["consumption"]
   and P["consumption"]["rigid"]["l_per_100km_empty"] == 27.0)
ok("params() on a document WITHOUT the block falls back to the file's, key by key",
   fairprice.params({"vehicles": {}})["driver_eur_per_h"] == 20.0
   and fairprice.params({"fair_price": {"driver_eur_per_h": 25}})["driver_eur_per_h"] == 25
   and fairprice.params({"fair_price": {"driver_eur_per_h": 25}})["running_eur_per_km"] == 0.12
   and fairprice.params({"fair_price": {"consumption": {"artic": {"l_per_100km_empty": 22}}}})["consumption"]["rigid"]["l_per_100km_empty"] == 27.0)
V8 = "Rigid 8-wheeler (32t)"
# NARROWED 11 Oct 2026 (EU vehicles removed): the seed's tractor + O4 semi (V12) is gone, and it never isolated
# the O4 test anyway (its gvw, 40 t, passed the >= 36 t test too). A synthetic entry does: a tractor + O4 semi
# under 36 t, with no "Artic" in its name, is an artic because of its category alone. R2 below runs on the
# UK Artic Tipper (44t); the name V12 stays so every use reads the same.
V12 = "Artic Tipper (44t)"
_O4 = {"vehicles": {"Tractor + semi (34 t)": {"eu_category": "N3 + O4", "gvw_t": 34, "payload_t": 20},
                    "Tractor + semi, O3 (30 t)": {"eu_category": "N3 + O3", "gvw_t": 30, "payload_t": 17},
                    "Rigid N3 (34 t)": {"eu_category": "N3", "gvw_t": 34, "payload_t": 20}}}
ok("vehicle_class: a rigid is 'rigid'; a tractor + O4 semi, a 44 t artic, are 'artic'; unknown ⇒ rigid",
   fairprice.vehicle_class(V8, FACT_FILE) == "rigid" and fairprice.vehicle_class(V12, FACT_FILE) == "artic"
   and fairprice.vehicle_class("Tractor + semi (34 t)", _O4) == "artic" and fairprice.vehicle_class("Tractor + semi, O3 (30 t)", _O4) == "artic"
   and fairprice.vehicle_class("Rigid N3 (34 t)", _O4) == "rigid"
   and fairprice.vehicle_class("Artic Tipper (44t)", FACT_FILE) == "artic" and fairprice.vehicle_class("Rigid 7.5t", FACT_FILE) == "rigid"
   and fairprice.vehicle_class("Ghost truck", FACT_FILE) == "rigid")
ok("litres: rigid empty 27, with 20 t 35 (= 27 + 0.4 × 20), artic with 26 t 34.0 (= the ICCT figure)",
   fairprice.litres_per_100km("rigid", 0, P) == 27.0 and abs(fairprice.litres_per_100km("rigid", 20, P) - 35.0) < 1e-9
   and abs(fairprice.litres_per_100km("artic", 26, P) - 34.0) < 1e-9)
ok("...winter: January × 1.08; September not", abs(fairprice.litres_per_100km("rigid", 20, P, month=1) - 37.8) < 1e-9
   and abs(fairprice.litres_per_100km("rigid", 20, P, month=9) - 35.0) < 1e-9)
ok("...a blank coefficient ⇒ None, never a guess",
   fairprice.litres_per_100km("rigid", 20, {"consumption": {"l_per_100km_per_tonne": None, "rigid": {"l_per_100km_empty": 27}}}) is None)
CTX = {"baked": True, "distance_km": 30.0, "return_km": 30.0, "cycle_min": 104.0, "payload_t": 20.0, "vehicle_class": "rigid"}
t = fairprice.trip_cost(CTX, 9, 1.922, P)
ok("⭐ the fixture trip (60 km round trip, 20 t, 1.73 h, diesel 1.922) costs € 113.78 — the research note's figure",
   t is not None and t["eur_trip"] == 113.78, str(t))
ok("...its components: 18.6 L → € 35.75 fuel · € 62.40 time · € 7.20 running · € 8.43 margin; fuel 33.9 % of cost",
   t and t["litres_trip"] == 18.6 and t["fuel_eur"] == 35.75 and t["time_eur"] == 62.4 and t["running_eur"] == 7.2
   and t["margin_eur"] == 8.43 and t["fuel_share_pct"] == 33.9)
ok("...€ 5.69 / t and € 1.896 / km — inside the IRU 0.50–2.00 €/km band", t and t["eur_per_t"] == 5.69 and 0.5 <= t["eur_per_km"] <= 2.0)
ok("...the same arithmetic by hand: (fuel + time + running) × 1.08",
   t and abs((t["fuel_eur"] + t["time_eur"] + t["running_eur"]) * 1.08 - t["eur_trip"]) < 0.02)
tw = fairprice.trip_cost(CTX, 1, 1.922, P)
ok("January costs more than September (the uplift on the fuel term only) and carries the WINTER flag",
   tw["eur_trip"] > t["eur_trip"] and abs((tw["eur_trip"] - t["eur_trip"]) - t["fuel_eur"] * 0.08 * 1.08) < 0.02
   and tw["flags"] == ["WINTER"] and t["flags"] == [])
ok("March carries BOTH flags (winter month and thaw month); April thaw only",
   fairprice.trip_cost(CTX, 3, 1.922, P)["flags"] == ["WINTER", "THAW"] and fairprice.trip_cost(CTX, 4, 1.922, P)["flags"] == ["THAW"])
ta = fairprice.trip_cost({**CTX, "vehicle_class": "artic", "payload_t": 26.0}, 9, 1.922, P)
ok("an artic carrying 26 t: 34.0 laden / 23.6 empty, cheaper per tonne than the rigid", ta["l_per_100km_laden"] == 34.0
   and ta["l_per_100km_empty"] == 23.6 and ta["eur_per_t"] < t["eur_per_t"])
ok("🔴 unbaked ⇒ None; no index ⇒ None; a blank coefficient ⇒ None — nothing invented",
   fairprice.trip_cost({**CTX, "baked": False}, 9, 1.922, P) is None and fairprice.trip_cost(CTX, 9, None, P) is None
   and fairprice.trip_cost(CTX, 9, 1.922, {**P, "driver_eur_per_h": None}) is None)
tr = fairprice.trip_cost({**CTX, "return_km": None}, 9, 1.922, P)
ok("a return leg that is not baked: the outbound stands in for its distance (as the cycle already does)",
   tr is not None and tr["litres_trip"] == t["litres_trip"])
ok("a higher diesel index raises only the fuel term", fairprice.trip_cost(CTX, 9, 2.922, P)["time_eur"] == t["time_eur"]
   and fairprice.trip_cost(CTX, 9, 2.922, P)["fuel_eur"] > t["fuel_eur"])
S = fairprice.summary(P, 1.922)
ok("summary() reports the coefficients in force and 'complete'", S["complete"] is True and S["driver_eur_per_h"] == 20.0
   and fairprice.summary(P, None)["complete"] is False)

# =========================================================================== #
#  2. On the Look-ahead — days, weeks, totals, Account                         #
# =========================================================================== #
reset_db()
access.set_current("planner123")
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L1", "Pit", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L2", "Site", 58.6, 24.4))
for _rid in ("R1", "R2", "R3"):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", (_rid, "L1", "L2", "IPT 1"))


def _geom(rid, prof, leg, km, hr):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, "
               "geometry, distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               ("default", rid, prof, leg, 0, "[[24,58.5],[24.4,58.6]]", km, hr))


_geom("R1", V8, "loaded", 30.0, 0.75); _geom("R1", V8, "return", 30.0, 0.65)
_geom("R2", V12, "loaded", 30.0, 0.75); _geom("R2", V12, "return", 30.0, 0.65)
# NARROWED 17 Oct 2026 (demo redesign R2, D104): was a fixed range(1, 25), which runs out on Mon 3 Jan 2028 (the real
# commit week falls in month 25, unseeded, and L["WS1"] is missing). As test_lookahead (PR #82): at least two years and
# always two months past the commit month, so the real week is seeded whatever the date.
MONTHS = tuple(range(1, max(24, days.commit_bucket()[0] + 2) + 1))


def _line(rid, sect, qty, veh):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type="Small aggregate",
        material_description=None, vehicle_type=veh, submitted_by="tester", unit="t",
        status="Pending", cells=[main.Cell(month_index=m, quantity=qty) for m in MONTHS], ipt="IPT1"))
    main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id=sect)


_line("R1", "WS1", 4000.0, V8)       # rigid, baked, no rate
_line("R2", "WS2", 4000.0, V12)      # artic, baked, no rate
_line("R3", "WS3", 900.0, V8)        # unbaked
res = main.list_forecast_days()
L = {l["section_id"]: l for l in res["lines"]}
ok("🔴 with NO index row there is no fair price anywhere — the model needs the live diesel price",
   all(d["derived"]["fair_eur"] is None for l in res["lines"] for d in l["days"]) and res["totals"]["fair_eur"] is None
   and res["costing"]["fair"]["complete"] is False and L["WS1"]["context"]["fair"] is None)
fuel.set_manual(1.922, "2026-09-07", by="admin", country="EE")  # NARROWED H1: the country is explicit now
res = main.list_forecast_days()
L = {l["section_id"]: l for l in res["lines"]}
c1 = L["WS1"]["context"]
ok("⭐ with the index: R1 (rigid, 20 t, 60 km, cycle from HERE) carries a fair price per trip, class 'rigid', its calendar month",
   c1["fair"] is not None and c1["vehicle_class"] == "rigid" and c1["fair"]["eur_trip"] > 0
   and c1["month"] == ((L["WS1"]["month_index"] - 1) % 12) + 1, str(c1.get("fair")))
d1 = [d for d in L["WS1"]["days"] if datetime.date.fromisoformat(d["day_date"]).weekday() <= 4][0]["derived"]
ok("...a day's fair € = trips × € / trip — the same trips slice 2 derives",
   abs(d1["fair_eur"] - round(d1["trips"] * c1["fair"]["eur_trip"], 2)) < 0.011)
ok("...no quote, no target — fair is the ONLY figure on the line, and it is its own field",
   d1["eur"] is None and d1["eur_adj"] is None and d1["fair_eur"] is not None and c1["rate_source"] is None)
ok("...the cycle the model used is the line's own (context.cycle_min)", c1["fair"]["month"] == c1["month"]
   and abs(c1["fair"]["time_eur"] - round(c1["cycle_min"] / 60.0 * (20.0 + 16.0), 2)) < 0.011)
# NARROWED 11 Oct 2026 (EU vehicles removed): R2 runs on the Artic Tipper (44t), 29 t (was V12, 26 t, whose laden
# figure was exactly the ICCT 34.0): laden = empty 23.6 + 0.4 × 29 = 35.2
ok("R2 (artic, 29 t) prices as an artic", L["WS2"]["context"]["vehicle_class"] == "artic"
   and abs(L["WS2"]["context"]["fair"]["l_per_100km_laden"] - 35.2) < 1e-9)
ok("🔴 R3 (unbaked) has NO fair price — no distance, nothing invented", L["WS3"]["context"]["fair"] is None
   and all(d["derived"]["fair_eur"] is None for d in L["WS3"]["days"]) and L["WS3"]["week_derived"]["fair_eur"] is None)
ok("week and totals sum the fair figure over the lines that have one: 2 of 3",
   L["WS1"]["week_derived"]["fair_eur"] is not None and res["totals"]["fair_lines"] == 2
   and abs(res["totals"]["fair_eur"] - (L["WS1"]["week_derived"]["fair_eur"] + L["WS2"]["week_derived"]["fair_eur"])) < 0.05)
ok("...and a typed target does not touch the fair figure (three independent columns)",
   (costing.set_target({"rate_eur_per_t": 3.0}, by="a") or True)
   and {l["section_id"]: l for l in main.list_forecast_days()["lines"]}["WS1"]["week_derived"]["fair_eur"] == L["WS1"]["week_derived"]["fair_eur"]
   and {l["section_id"]: l for l in main.list_forecast_days()["lines"]}["WS1"]["week_derived"]["eur"] is not None)
pg = lookahead.page(bucket="commit")
if pg["account"].get("rows"):
    A = {r["section_id"]: r for r in pg["account"]["rows"]}
    ok("account rows carry planned_fair_eur and the season flags; the unbaked row None",
       A["WS1"]["planned_fair_eur"] is not None and isinstance(A["WS1"]["fair_flags"], list) and A["WS3"]["planned_fair_eur"] is None
       and pg["account"]["fair_lines"] == 2, str({k: v.get("planned_fair_eur") for k, v in A.items()}))
else:
    ok("(no account week in this bucket — the account assertion did not run)", False)
ok("the page's costing block carries the model's coefficients in force",
   pg["costing"]["fair"]["driver_eur_per_h"] == 20.0 and pg["costing"]["fair"]["complete"] is True)
# the live document without the block prices from the file; with an override it prices from the override
config.save({**FACT_FILE, "fair_price": {**FP, "driver_eur_per_h": 40.0}}, by="t")
res2 = main.list_forecast_days()
c1b = {l["section_id"]: l for l in res2["lines"]}["WS1"]["context"]["fair"]
ok("⭐ a coefficient changed on Config moves the figure on the next read (driver 20 → 40: time term doubles the driver share)",
   c1b is not None and abs(c1b.get("time_eur", 0) - round(c1["cycle_min"] / 60.0 * (40.0 + 16.0), 2)) < 0.011
   and c1b.get("eur_trip", 0) > c1["fair"]["eur_trip"])
_doc_no_block = {k: v for k, v in FACT_FILE.items() if k != "fair_price"}
config.save(_doc_no_block, by="t")
c1c = {l["section_id"]: l for l in main.list_forecast_days()["lines"]}["WS1"]["context"]["fair"]
ok("...and a live document WITHOUT the block prices from the file's seeded values", (c1c or {}).get("eur_trip") == c1["fair"]["eur_trip"])
config.reset_to_file(conversions, by="t")

# =========================================================================== #
#  3. Validation, export, what must not exist                                  #
# =========================================================================== #
ok("config.validate: a negative driver rate, a month 13, a zero empty consumption are refused; the block absent passes",
   any("driver_eur_per_h" in x for x in config.validate({**FACT_FILE, "fair_price": {**FP, "driver_eur_per_h": -1}}))
   and any("winter_months" in x for x in config.validate({**FACT_FILE, "fair_price": {**FP, "season": {**FP["season"], "winter_months": [13]}}}))
   and any("l_per_100km_empty" in x for x in config.validate({**FACT_FILE, "fair_price": {**FP, "consumption": {**FP["consumption"], "rigid": {"l_per_100km_empty": 0}}}}))
   and not config.validate(_doc_no_block) and not config.validate(FACT_FILE))
pg = lookahead.page(bucket="commit")
xb = export.build_xlsx(pg)
import openpyxl as _ox
wb = _ox.load_workbook(io.BytesIO(xb))
ws = wb["Commit week"]
hdr = [ws.cell(row=1, column=j).value for j in range(1, ws.max_column + 1)]
ok("XLSX: '€ fair (model)', 'fair €/t' and 'fair flags' columns follow '€ + BAF'",
   "€ fair (model)" in hdr and hdr.index("€ fair (model)") == hdr.index("€ + BAF") + 1 and "fair €/t" in hdr and "fair flags" in hdr)
cf = hdr.index("€ fair (model)") + 1
vals = [ws.cell(row=i, column=cf).value for i in range(2, ws.max_row + 1)]
ok("...baked rows carry a fair figure and the unbaked rows are blank", sum(1 for v in vals if v is not None) == 10 and sum(1 for v in vals if v is None) == 5)
wf = wb["Fuel"]
ftxt = " ".join(str(wf.cell(row=i, column=j).value or "") for i in range(1, wf.max_row + 1) for j in (1, 2))
ok("...the Fuel sheet states the coefficients the fair figures used", "Fair price: driver" in ftxt and "Fair price: margin" in ftxt and "winter months" in ftxt)
from portable import pdf_text, offline
offline(export)   # never a live Mapbox call from a harness
pb = export.build_pdf(pg)
_txt = pdf_text(pb)
ok("🔴 the supplier's PDF does NOT carry the fair price — it is the planner's negotiating figure",
   "fair" not in _txt.lower() and "model" not in _txt.lower())
_fe = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
ok("the page: FairPriceSection defined once and mounted in the Costing tab; the Account column and the KPI caption say 'model'",
   len(re.findall(r"function FairPriceSection\(", _fe)) == 1 and _fe.count("<FairPriceSection") == 1
   # NARROWED (G2): the currency symbol is the tenant's — {CUR()} where it said €
   and "Fair {CUR()} <span" in _fe and "Fair € <span" not in _fe
   and "(model, ${totals.fair_lines} of ${totals.lines})" in _fe)
ok("...the copy calls it a floor for negotiation, never a quote", "a floor for negotiation, never a quote" in _fe)
ok("🔴 no fair price on the public map", "fair price" not in open(os.path.join(ROOT, "map", "index.html"), encoding="utf-8").read().lower())
ok("no route type field was invented: no 'route_type' / 'road_surface' NAME in the backend (docstrings may say the word)",
   all(not any(x in n for n in _code_tokens(open(os.path.join(BACKEND, f), encoding="utf-8").read())[0] for x in ("route_type", "road_surface", "surface_factor"))
       for f in ("fairprice.py", "derived.py", "lookahead.py")))

# =========================================================================== #
#  4. HU7 (14 Oct 2026): a GB set in the SEED, beside the Estonian one          #
# =========================================================================== #
# Until today only the demo package carried a GB set; a GB tenant set up without it priced in £ on
# Estonian figures (driver from Statistics Estonia, a thaw season Great Britain does not have).
BYC = FACT_FILE.get("fair_price_by_country") or {}
GB = BYC.get("GB") or {}
ok("⭐ factors.json carries fair_price_by_country with a GB set and a README; fair_price (the EE set) is unchanged",
   isinstance(BYC, dict) and isinstance(GB, dict) and len(GB.get("_README", "")) > 100
   and "Great Britain" in GB["_README"] and "_fair_price_by_country_note" in FACT_FILE
   and FP["driver_eur_per_h"] == 20.0 and FP["consumption"]["rigid"]["l_per_100km_empty"] == 27.0)
ok("...every GB coefficient has a source line beside it",
   "_source" in (GB.get("consumption") or {}) and "_driver_source" in GB and "_vehicle_standing_source" in GB
   and "_running_source" in GB and "_margin_source" in GB and "_source" in (GB.get("season") or {}) and "_sanity_source" in GB)
ok("🔴 C25: the three unsourced GB numbers are LABELLED as assumptions; the driver rate is not one",
   all(GB.get(k, "").startswith("ASSUMPTION") for k in ("_vehicle_standing_source", "_running_source", "_margin_source"))
   and "ASSUMPTION" in GB["_README"] and "ASSUMED multiplier" in GB["_driver_source"]
   and not GB["_driver_source"].startswith("ASSUMPTION"))
ok("...and the sourced GB ones name where they came from (ONS ASHE via DfT, RHA, ICCT, DfT payload, DESNZ, US DOE)",
   "ONS Annual Survey of Hours and Earnings" in GB["_driver_source"] and "DfT Road Freight Statistics" in GB["_driver_source"]
   and "RHA Pay Report 2026" in GB["_driver_source"] and "ICCT" in GB["consumption"]["_source"]
   and "DESNZ 2026" in GB["consumption"]["_source"] and "fueleconomy.gov" in GB["season"]["_source"])
ok("the GB values are pinned (a silent change is caught here): £24/h driver, £13/h standing from £150k, £0.12/km, 8 %, rigid 31, artic 23.6, no thaw",
   GB["driver_eur_per_h"] == 24.0 and GB["vehicle_standing_eur_per_h"] == 13.0 and GB["vehicle_new_price_eur"] == 150000
   and GB["running_eur_per_km"] == 0.12 and GB["margin_pct"] == 8.0 and GB["consumption"]["l_per_100km_per_tonne"] == 0.4
   and GB["consumption"]["rigid"]["l_per_100km_empty"] == 31.0 and GB["consumption"]["artic"]["l_per_100km_empty"] == 23.6
   and GB["season"]["winter_months"] == [11, 12, 1, 2, 3] and GB["season"]["winter_consumption_uplift_pct"] == 8.0
   and GB["season"]["thaw_months"] == [])
# Sources checked 14 Oct 2026 (a research pass; VED, levy and RHA re-read here): the 29 Sep text's "VED + levy ≈ £1,300"
# was wrong — HGV VED is £1 for a lorry taxed 1 Jul 2026 – 30 Jun 2027 (gov.uk) and the 44 t Euro VI levy is £619.
ok("...the GB standing derivation is arithmetically consistent (150k, 7 yr, 20 % residual, 3 %, tax + levy £620 now / ~£1,200 full, 1,800 h → 12.4 / 12.7, rounded 13)",
   abs((150000 * 0.8 / 7 + 150000 * 0.03 + 620) / 1800 - 12.4) < 0.05 and abs((150000 * 0.8 / 7 + 150000 * 0.03 + 1199) / 1800 - 12.7) < 0.05
   and "£12.4/h now, £12.7/h at the full rate, rounded to £13" in GB["_vehicle_standing_source"])
ok("🔴 ...and states the vehicle tax as gov.uk has it now: levy £619 + VED £1 (1 Jul 2026 – 30 Jun 2027), never the old ≈ £1,300",
   "levy £619" in GB["_vehicle_standing_source"] and "£1 for a lorry taxed between 1 Jul 2026 and 30 Jun 2027" in GB["_vehicle_standing_source"]
   and "VED + HGV road user levy ≈ £1,300/yr" not in GB["_vehicle_standing_source"])
ok("...the GB driver derivation is too (£16.25 × 1.28 / 0.85 = £24.5, rounded 24), and says the £16.25 is gross (with overtime) and the RHA rates basic",
   abs(16.25 * 1.28 / 0.85 - 24.5) < 0.05 and "£24.5/h" in GB["_driver_source"]
   and "£16.25 GROSS, which includes overtime (£16.01 excluding overtime)" in GB["_driver_source"]
   and "BASIC hourly rate medians C+E £15.05, C £14.50" in GB["_driver_source"]
   and abs(0.15 * (16.25 * 2000 - 5000) / (16.25 * 2000) - 0.127) < 0.001)
ok("...the running ASSUMPTION is set against the RHA's own tyre and repair figures (17.74 p/mile tractor + 9.92 trailer ≈ £0.17/km), not the 78.21 that includes fuel",
   abs((3.13 + 14.61) - 17.74) < 1e-9 and abs((17.74 + 9.92) / 160.934 - 0.172) < 0.001
   and "17.74 p/mile for the tractor" in GB["_running_source"] and "about £0.17/km for the whole outfit" in GB["_running_source"]
   and "is not used" in GB["_running_source"])
ok("...and the IRU band is called what it is: a page with no method, source or scope — a loose check, not a benchmark",
   "no method, source or scope given" in GB["_sanity_source"] and "not a benchmark and not an input" in GB["_sanity_source"])
ok("...the rigid 31 is the 2026 derivation the EE block's note names (0.99773 / 2.58354 × 100 − 0.4 × 20 = 30.6)",
   abs(0.99773 / 2.58354 * 100 - 0.4 * 20 - 30.6) < 0.05 and "would be 31" not in GB["consumption"]["_source"])
ok("🔴 the GB set carries no diesel price (DESNZ is the live index) and no Estonian source or term",
   not any(("diesel" in k.lower() or "eur_per_l" in k.lower()) for k in GB if not k.startswith("_"))
   and not any(w in json.dumps(GB, ensure_ascii=False) for w in ("Estonia", "stat.ee", "emta", "palgad", "Transpordiamet",
                                                               "Virumaa", "vignette", "Tark Tee", "€")))
ok("...the per-country sets are keyed by two-letter capitals, and GB is the only one today", sorted(k for k in BYC if not k.startswith("_")) == ["GB"])

# the model's fallback picks the tenant country's set
_gbp = fairprice.params({"tenant": {"country": "GB"}})
_eep = fairprice.params({"tenant": {"country": "EE"}})
ok("⭐ params(): a GB tenant WITHOUT a block prices on the GB set (24 / 13 / rigid 31 / no thaw); an EE one on the EE set",
   _gbp["driver_eur_per_h"] == 24.0 and _gbp["vehicle_standing_eur_per_h"] == 13.0
   and _gbp["consumption"]["rigid"]["l_per_100km_empty"] == 31.0 and _gbp["season"]["thaw_months"] == []
   and _eep["driver_eur_per_h"] == 20.0 and _eep["consumption"]["rigid"]["l_per_100km_empty"] == 27.0
   and _eep["season"]["thaw_months"] == [3, 4])
ok("...no country, a country the file has no set for, or a blank one ⇒ the fair_price set (EE), as before",
   fairprice.params({})["driver_eur_per_h"] == 20.0 and fairprice.params({"tenant": {"country": "FR"}})["driver_eur_per_h"] == 20.0
   and fairprice.params({"tenant": {"country": ""}})["driver_eur_per_h"] == 20.0
   and fairprice.params({"tenant": {"country": None}})["driver_eur_per_h"] == 20.0)
ok("...the country is read case-blind ('gb' = GB), and a GB tenant's own keys still win key by key over the GB set",
   fairprice.params({"tenant": {"country": "gb"}})["driver_eur_per_h"] == 24.0
   and fairprice.params({"tenant": {"country": "GB"}, "fair_price": {"driver_eur_per_h": 30}})["driver_eur_per_h"] == 30
   and fairprice.params({"tenant": {"country": "GB"}, "fair_price": {"driver_eur_per_h": 30}})["vehicle_standing_eur_per_h"] == 13.0
   and fairprice.params({"tenant": {"country": "GB"}, "fair_price": {"consumption": {"artic": {"l_per_100km_empty": 22}}}})["consumption"]["rigid"]["l_per_100km_empty"] == 31.0)
ok("...file_defaults(country) returns the set itself; file_defaults() the EE set",
   fairprice.file_defaults("GB") is fairprice.file_defaults("gb") and fairprice.file_defaults("GB")["driver_eur_per_h"] == 24.0
   and fairprice.file_defaults()["driver_eur_per_h"] == 20.0 and fairprice.file_defaults("FR") is fairprice.file_defaults())
_tg = fairprice.trip_cost(CTX, 9, 1.955, _gbp)
_tg3 = fairprice.trip_cost(CTX, 3, 1.955, _gbp)
# REVERSED before it was ever committed (14 Oct 2026): the 29 Sep note said this trip "lands inside that band". It does
# not — £2.02/km, above the 2.00 top of an EUR band. The note now gives the figure; this pins it, so the note cannot drift.
ok("the fixture trip on the GB set at £1.955/L costs £121.38 = £2.02/km, just ABOVE the IRU band, and the sanity note says so; March is WINTER, never THAW",
   _tg is not None and _tg["eur_trip"] == 121.38 and _tg["eur_per_km"] == 2.023 and _tg["eur_per_km"] > 2.0
   and "£121.38 a trip = £2.02/km" in GB["_sanity_source"] and "lands inside that band" not in GB["_sanity_source"]
   and _tg3["flags"] == ["WINTER"]
   and abs(_tg["eur_trip"] - round((_tg["fuel_eur"] + _tg["time_eur"] + _tg["running_eur"]) * 1.08, 2)) < 0.02,
   str(_tg))

# validation: each set held to fair_price's rules
_bad = lambda s: config.validate({**FACT_FILE, "fair_price_by_country": s})
ok("config.validate: a GB set with a negative driver rate, a month 13 or a zero empty consumption is refused, by name",
   any("fair_price_by_country.GB.driver_eur_per_h" in x for x in _bad({"GB": {**GB, "driver_eur_per_h": -1}}))
   and any("fair_price_by_country.GB.season.thaw_months" in x for x in _bad({"GB": {**GB, "season": {**GB["season"], "thaw_months": [13]}}}))
   and any("fair_price_by_country.GB.consumption.rigid" in x for x in _bad({"GB": {**GB, "consumption": {**GB["consumption"], "rigid": {"l_per_100km_empty": 0}}}})))
ok("...a lower-case or three-letter key, a set that is not an object, and a block that is not an object are refused",
   any("two-letter country code" in x for x in _bad({"gb": GB})) and any("two-letter country code" in x for x in _bad({"GBR": GB}))
   and any("fair_price_by_country.GB must be an object" in x for x in _bad({"GB": 5}))
   and any("fair_price_by_country must be an object" in x for x in _bad([GB])))
ok("...the seed passes, the block absent passes, and an _note key inside it is ignored",
   not config.validate(FACT_FILE) and not config.validate({k: v for k, v in FACT_FILE.items() if k != "fair_price_by_country"})
   and not _bad({"_note": "x", "GB": GB}))

# one copy: the demo package's GB block IS the seed's, and the tool takes it from the seed
_pkg = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
_dfp = json.loads([r for r in _pkg["tables"]["config"] if r["key"] == "factors"][0]["value"])["fair_price"]
_strip = lambda d: {k: v for k, v in d.items() if k not in ("_README", "_demo_note")}
ok("⭐ the demo package's fair_price is the seed's GB set word for word (bar its README and demo note)",
   _strip(_dfp) == _strip(GB) and "_demo_note" in _dfp)
_tool = open(os.path.join(BACKEND, "tools", "make_demo_tenant.py"), encoding="utf-8").read()
ok("...and make_demo_tenant.py takes it from the seed instead of carrying its own copy of the figures",
   'doc["fair_price_by_country"]["GB"]' in _tool and "£16.25" not in _tool and 'fp["driver_eur_per_h"] = 24.0' not in _tool)

# the live path: a GB tenant whose document has no block prices on the GB set
_gbdoc = {k: v for k, v in FACT_FILE.items() if k != "fair_price"}
_gbdoc["tenant"] = dict(FACT_FILE.get("tenant") or {}, country="GB", currency="GBP")
_r = config.save(_gbdoc, by="t")
config.invalidate()
costing.invalidate()
fuel.set_manual(1.955, "2026-09-21", by="admin", country="GB")
_lg = {l["section_id"]: l for l in main.list_forecast_days()["lines"]}["WS1"]["context"]
_fg = _lg.get("fair") or {}
ok("⭐ live: a GB tenant with no block on its document prices WS1 on the GB set (time term = cycle × (24 + 13))",
   _r["ok"] and _fg.get("time_eur") is not None
   and abs(_fg["time_eur"] - round(_lg["cycle_min"] / 60.0 * (24.0 + 13.0), 2)) < 0.011, str(_fg))
config.reset_to_file(conversions, by="t")
config.invalidate()
costing.invalidate()

# the page: the country's set is shown, copied and offered
ok("the page: FairPriceSection reads the file's set for the tenant's country, falling back to fair_price",
   "(fileDoc.fair_price_by_country || {})[cc]" in _fe and "const fileFp = countryFp || (fileDoc && fileDoc.fair_price) || {};" in _fe)
ok("...and offers it as one click when the live block differs (numbers only), saved with the page's Save",
   "data-fair-country-offer={cc}" in _fe and "Use the {countryName} set" in _fe
   and "d.fair_price = JSON.parse(JSON.stringify(countryFp))" in _fe and "Nothing changes until you Save." in _fe
   and "fairCanon(doc.fair_price) !== fairCanon(countryFp)" in _fe)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
