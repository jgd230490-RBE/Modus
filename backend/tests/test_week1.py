"""
Week-1 backend assertions — the 2026-09-01 build list, Tasks A–E.

  A   work_sections seeded (15 rows) + the planning vehicles (the four EU-named ones until
      11 Oct 2026; since then the six UK haulage trade names) — and A3, a document that
      still carries the four EU entries keeps loading and working
  B   multi-year Submit Forecast — one bulk POST across two years
  C   forecast_weeks: materialise on approve, edit, confirm
  D   typed actuals, variance, calibrate
  D2  stockpile capacity, weekly consumption, the balance read model
  E   the Railhead location type

Same harness as test_phase5a.py: a scratch SQLite database, no network, and `fastapi`
/ `flexpolyline` / `psycopg2` stubbed so main.py imports and its endpoint functions can
be called directly as plain Python.

WHAT THIS DOES NOT PROVE
------------------------
Read this before quoting the pass count.

  * **The HTTP layer is stubbed.** Endpoint BODIES run; the transport does not. Nothing
    here proves a route is actually mounted, that a query parameter is parsed, or that
    the admin token rejects a request.
  * **No Postgres branch runs.** `forecast_weeks` and `stockpile_weeks` are created
    against SQLite only. Their Postgres path is a plain CREATE plus the Phase 4.5
    tenant migration, which needs no key rebuild — but it has not been executed.
  * **HERE is never called**, and nothing here bakes a route.
  * **Nothing in a browser.** The Look-ahead tab, the stockpile panel, the year-range
    form and the rail layer are asserted at SOURCE level in parse_frontend.js and
    parse_map.js, not exercised. No assertion here proves a cell renders.
  * **The rail geometry is Natural Earth, not OSM or survey.** Its accuracy is asserted
    to be DECLARED, not to be good. See test_rail_data() and the README.

Run:  python3 backend/tests/test_week1.py
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

# --------------------------------------------------------------------------- #
#  Stubs                                                                       #
# --------------------------------------------------------------------------- #
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


# a CLASS, not a lambda: main.py subclasses this, and `class X(lambda)` is a TypeError
class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_week1_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
os.environ.pop("DATABASE_URL", None)
# 12 Oct 2026 (C11 closed): the admin endpoints REFUSE when ADMIN_TOKEN is unset, so the harness
# configures one and hands it to every admin call it makes (it passed token=None until then)
os.environ["ADMIN_TOKEN"] = "week1-admin-token"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")

import conversions  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import weeks  # noqa: E402
import stockpiles  # noqa: E402
import costlines   # noqa: E402  (2026-10-06: the map's CO2e must match it)
import main  # noqa: E402

# G2, 16 Sep 2026: the product ships no network, teams or sections. These tests keep
# their assertions by loading the same rows from TEST FIXTURES (see
# tests/fixtures/taxonomy_rbe.json's _note).
FIX_NET = os.path.join(HERE, "fixtures", "network_v2.json")
FIX_META = os.path.join(HERE, "fixtures", "node_meta.json")
FIX_TAX = os.path.join(HERE, "fixtures", "taxonomy_rbe.json")
# 2026-09-02, Task F: the staff endpoints now require an access code, resolved from the
# X-Access-Code header by a middleware the stubbed app never runs. The harness sets the
# request context itself, as a PLANNER, so every pre-existing assertion still exercises
# the same code paths it did. Nothing here proves the header is actually read.
import access  # noqa: E402
import gate  # noqa: E402  — 12 Oct 2026: the staff / map cookies for /api/meta's two shapes and whoami
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
# 15 Sep: the three demo codes are opt-in on the server now (access.DEMO_ENV).
# Every harness below signs in as planner123, so it asks for them explicitly.
os.environ["ALLOW_DEMO_CODES"] = "1"
access.set_current("planner123")

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db()
    db.init_network_db()
    db.init_taxonomy_db()
    db.init_zones_db()
    db.init_gates_db()
    db.init_weeks_db()
    db.init_config_db()
    db.init_tenant()
    import config as _cfg
    _cfg.invalidate()


def cols(table):
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return {r[1]: r for r in cur.fetchall()}
    finally:
        conn.close()


def pk_order(table):
    """Primary-key column names, in key order."""
    return [r[1] for r in sorted(
        (r for r in cols(table).values() if r[5]), key=lambda r: r[5])]


def tables():
    return {r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def seed_line(route_id="R1", disc="earthworks", sect="WS1", months=(1, 2, 3),
              qty=100.0, unit="t", status="Pending"):
    """One forecast line over `months`, through the real bulk endpoint."""
    return main.save_matrix_row(main.MatrixRow(
        route_id=route_id, discipline=disc, section_id=sect,
        material_type="Small aggregate", material_description=None,
        vehicle_type="Rigid 8-wheeler (32t)", submitted_by="tester",
        unit=unit, status=status,
        cells=[main.Cell(month_index=m, quantity=qty) for m in months]))


# =========================================================================== #
#  A. work_sections + the planning vehicles (UK trade names since 11 Oct 2026)  #
# =========================================================================== #
reset_db()
taxonomy.seed_taxonomy(taxonomy.load_bundle(FIX_TAX))

_ws = taxonomy.list_work_sections()
ok("A: fifteen work sections are seeded", len(_ws) == 15, f"got {len(_ws)}")
ok("A: they reach /api/meta's picker payload",
   len(main.meta()["work_sections"]) == 15)

F = conversions.load_factors()
PLANNING = conversions.planning_vehicle_names(F)
# NARROWED 11 Oct 2026 (EU vehicles removed): the user removed the four EU type-approval
# entries from the product. The seed now leads with six UK haulage trade names, flagged
# planning_vehicle: true, Rigid 8-wheeler first (it is also the payload fallback).
ok("A: exactly six planning vehicles — the UK haulage trade names, Rigid 8-wheeler first",
   len(PLANNING) == 6 and PLANNING == ["Rigid 8-wheeler (32t)", "Rigid 6-wheeler (26t)", "Artic Tipper (44t)",
                                       "Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)", "Artic Flatbed (44t)"],
   str(PLANNING))
ok("A (11 Oct 2026): the array and the flags agree — every planning vehicle is flagged, and nothing else is",
   F["planning_vehicles"] == PLANNING
   and sorted(k for k in conversions.vehicle_names(F) if F["vehicles"][k].get("planning_vehicle")) == sorted(PLANNING))
ok("A: /api/meta ships them as their own list",
   main.meta().get("planning_vehicles") == PLANNING)
# ⭐ THE POINT OF 'add four, keep six'. Every baked route_geometry row is keyed on
# vehicle_profile and network.DEFAULT_PROFILE is one of the six. If the six ever leave
# this file their routes' payload, CO2 and trips/day fall through to _default and every
# affected route then reports IDENTICAL figures — the exact fault
# network.factors_diagnostics() was written to surface.
ALL_V = conversions.vehicle_names(F)
# NARROWED (H1, 29 Sep 2026): twelve — the four added on 1 Sep, the six kept, and two UK
# truck mixers added for GB tenants. Nothing was removed (the point of this assertion).
# NARROWED again (10 Oct 2026, carbon planner): fifteen — three battery-electric variants
# added BESIDE the baked artic tipper, artic flatbed and 8-wheeler (new keys; nothing renamed, nothing removed).
# NARROWED 11 Oct 2026 (EU vehicles removed): eleven. The four EU type-approval entries added on
# 1 Sep were REMOVED on purpose (the user's decision) — the one deliberate removal; the six kept,
# the two GB mixers and the three electric variants are all still here.
ok("A: eleven vehicles in total — six kept, two GB mixers (H1), three electric variants (carbon); the four EU entries removed",
   len(ALL_V) == 11, str(len(ALL_V)))
ok("A: the three electric variants are the only additions since H1, each twinned to a profile that is still present",
   sorted(v for v in ALL_V if F["vehicles"][v].get("fuel") == "electric")
   == ["Artic Flatbed (44t) — electric", "Artic Tipper (44t) — electric", "Rigid 8-wheeler (32t) — electric"]
   and all(F["vehicles"][v]["geometry_twin"] in ALL_V for v in ALL_V if F["vehicles"][v].get("fuel") == "electric"))
# REVERSED 11 Oct 2026 (EU vehicles removed): the EU mixer is now GONE, with the other three.
ok("H1: the two GB truck mixers are present and the EU mixer is gone (11 Oct 2026)",
   "Truck mixer 8 m³ (32t)" in ALL_V and "Truck mixer 6 m³ (26t)" in ALL_V and "N3 lorry (BA) 4-axle mixer 32 t" not in ALL_V)
for legacy in ("Rigid 7.5t", "Rigid 4-wheeler (18t)", "Rigid 6-wheeler (26t)",
               "Rigid 8-wheeler (32t)", "Artic Tipper (44t)", "Artic Flatbed (44t)"):
    ok(f"A: legacy vehicle {legacy!r} is still present", legacy in ALL_V)
ok("A: ⭐ DEFAULT_PROFILE still resolves in factors.json",
   network.DEFAULT_PROFILE in ALL_V)
ok("A: ...and does NOT fall through to _default",
   conversions._payload(F, network.DEFAULT_PROFILE)
   != conversions._payload(F, "__no_such_vehicle__"))
# the payloads the build list gives, verbatim
# NARROWED 11 Oct 2026 (EU vehicles removed): those were the EU entries' build-list payloads
# (18 / 25.5 / 26 t). The lead list's payloads are the file's own UK figures.
for name, want in ((PLANNING[0], 20.0), (PLANNING[2], 29.0), (PLANNING[3], 18.0)):
    ok(f"A: {name[:28]}… carries its given payload {want} t",
       conversions._payload(F, name) == want)
# V10 is the one whose tonnage is DERIVED, and the file has to say so
# NARROWED 11 Oct 2026 (EU vehicles removed): V10 is gone; the lead list's drum mixer is the
# one whose tonnage is derived from a volume — 7.5 m³ (the drum's legal fill) × 2.4 t/m³.
v10 = F["vehicles"][PLANNING[3]]
ok("A: the lead mixer (Truck mixer 8 m³) keeps its m³ figure, the drum's legal fill (7.5)",
   v10.get("payload_m3") == 7.5)
ok("A: the lead mixer's payload_t is its m³ × the concrete density in the same file (7.5 × 2.4 = 18 t)",
   abs(v10["payload_t"] - 7.5 * F["material_categories"]["Precast / concrete"]
       ["density_t_per_m3"]) < 1e-9)
# NARROWED 11 Oct 2026 (EU vehicles removed): every planning vehicle declares its emissions
# basis; a payload basis is declared where the payload is a stated ASSUMPTION (the mixers).
ok("A: ⭐ and every figure not given in a source declares its basis",
   all("_emissions_basis" in F["vehicles"][v] for v in PLANNING)
   and all("ASSUMPTION" in F["vehicles"][v].get("_payload_basis", "") for v in PLANNING if F["vehicles"][v].get("payload_m3")))
# 2026-09-02: one vehicle, three labels. The key is the id; a label only changes the text.
_VL = conversions.vehicle_labels(F)
ok("A2: /api/meta ships vehicle_labels", main.meta().get("vehicle_labels") == _VL)
# NARROWED 11 Oct 2026 (EU vehicles removed): every OFFERED slot is filled, and the seed is
# offered English alone — no vehicle carries another language now.
ok("A2: every vehicle has every offered slot filled — English only in the seed",
   _VL["langs"] == ["en"] and all(set(v) == set(_VL["langs"]) for v in _VL["labels"].values())
   and set(_VL["labels"]) == set(ALL_V))
ok("A2: ⭐ a missing slot falls back to the KEY, not another language",
   all(_VL["labels"][k][l] == k for k, ls in _VL["fallbacks"].items() for l in ls))
# REVERSED 11 Oct 2026 (EU vehicles removed): no vehicle carries an EU label, so the EU option is
# not offered at all (it was offered with the planning vehicles' keys as its strings).
ok("A2: no vehicle carries an EU label any more, and the EU option is not offered",
   all("eu" not in (F["vehicles"][k].get("labels") or {}) for k in ALL_V)
   and "eu" not in _VL["langs"] and all("eu" not in v for v in _VL["labels"].values()))
# NARROWED 11 Oct 2026 (EU vehicles removed): still none invented — and the slot is not offered.
ok("A2: ⭐ no Estonian label was invented — no vehicle carries one, so the option is not offered",
   all("ee" not in (F["vehicles"][k].get("labels") or {}) for k in ALL_V)
   and "ee" not in _VL["langs"] and _VL["fallbacks"] == {})
ok("A2: the six legacy keys are their own English label",
   all(_VL["labels"][k]["en"] == k for k in ALL_V if k not in PLANNING))
# NARROWED 11 Oct 2026 (EU vehicles removed): V07 is gone; the first planning vehicle's English
# label is its UK trade name, which is also its key.
ok("A2: the first planning vehicle's English label is its UK trade name",
   _VL["labels"][PLANNING[0]]["en"] == "Rigid 8-wheeler (32t)" == PLANNING[0])

# a planning vehicle nobody can select is a planning vehicle that does not exist
selectable = {v for c in conversions.material_names(F)
              for v in F["material_categories"][c].get("vehicles", [])}
ok("A: every planning vehicle is offered by at least one material category",
   set(PLANNING) <= selectable, str(set(PLANNING) - selectable))
# absent dimensions must stay absent — borrowing another vehicle's would change which
# roads HERE allows, silently
import here_routing  # noqa: E402
# NARROWED 11 Oct 2026 (EU vehicles removed): the EU entries were the only seed vehicles with
# no dimensions, so "sends NO dimensions" was the absent-is-not-invented proof. The UK lead
# vehicles carry all three, so each must send EXACTLY its own (none borrowed, none dropped),
# and a SYNTHETIC vehicle with a weight and no dimensions carries the absent case below.
_DIMS = {"vehicle[height]": "height_cm", "vehicle[width]": "width_cm", "vehicle[length]": "length_cm"}
for name in PLANNING:
    p = here_routing._truck_params(name, F, laden=True)
    ok(f"A: {name[:24]}… sends a gross weight to HERE", "vehicle[grossWeight]" in p)
    ok(f"A: {name[:24]}… sends exactly the dimensions its own entry carries — none invented",
       {k for k in _DIMS if k in p} == {k for k, f in _DIMS.items() if (F["vehicles"][name].get("routing") or {}).get(f)}
       and all(p[k] == int(F["vehicles"][name]["routing"][f]) for k, f in _DIMS.items() if k in p))
SYN = "Synthetic 4-axle, weight only"
_FS = json.loads(json.dumps(F))
_FS["vehicles"][SYN] = {"gvw_t": 32, "payload_t": 18, "routing": {"gross_weight_kg": 32000}}
_ps = here_routing._truck_params(SYN, _FS, laden=True)
ok("A (11 Oct 2026): ⭐ a vehicle with a weight and NO dimensions sends the weight and NO invented dimensions or axles",
   _ps.get("vehicle[grossWeight]") == 32000
   and not ({"vehicle[height]", "vehicle[width]", "vehicle[length]", "vehicle[axleCount]"} & set(_ps)))
ok("A (11 Oct 2026): ...its unladen return leg is routed at the tare (gvw − payload = 14 t)",
   here_routing._truck_params(SYN, _FS, laden=False).get("vehicle[grossWeight]") == 14000)
# B4's turnaround split must still reproduce load+unload for the NEW profiles too
for name in PLANNING:
    load, unload = network._turnaround_minutes(name, F)
    parts = network._turnaround_parts(name, F)
    ok(f"A: {name[:24]}… turnaround is still exactly load + unload",
       abs(parts["total_minutes"] - (load + unload)) < 1e-9,
       f"{parts['total_minutes']} vs {load + unload}")
# 11 Oct 2026: the EU entries were the only seed vehicles without their own load/unload minutes,
# so they were the only proof of the fallback; the synthetic vehicle carries it now
ok("A (11 Oct 2026): a vehicle without its own load/unload minutes falls back to _default's 12 + 8",
   network._turnaround_minutes(SYN, _FS) == (12.0, 8.0)
   and abs(network._turnaround_parts(SYN, _FS)["total_minutes"] - 20.0) < 1e-9)

# --------------------------------------------------------------------------- #
#  A3. 11 Oct 2026 — the EU vehicles removed: what replaced them, and a        #
#      document that STILL carries them keeps loading and working             #
# --------------------------------------------------------------------------- #
# The user removed the four EU type-approval vehicles from the product (factors.json, the demo
# package). A live Config row saved before then (the live demo's) and any older tenant package
# still carry them, so they are rebuilt here as they were in the seed until 11 Oct 2026 (the
# fields the code reads) and pushed through the same paths.
import config  # noqa: E402
import derived  # noqa: E402
import fairprice  # noqa: E402
import inspect  # noqa: E402
EU_OLD = {
    "N3 lorry (BA) 4-axle TPMLM 32 t tipper": {
        "code": "V07", "planning_vehicle": True, "eu_category": "N3", "body_code": "BA", "licence": "C",
        "gvw_t": 32, "payload_t": 18, "emissions_kg_co2e_per_km": 0.99773, "aliases": ["8x4 tipper"],
        "routing": {"gross_weight_kg": 32000, "axle_count": 4},
        "labels": {"en": "8x4 rigid tipper (32 t)", "eu": "N3 lorry (BA) 4-axle TPMLM 32 t tipper"}, "fuel": "diesel"},
    "N3 lorry (BA) 4-axle mixer 32 t": {
        "code": "V10", "planning_vehicle": True, "eu_category": "N3", "body_code": "BA", "licence": "C",
        "gvw_t": 32, "payload_m3": 8, "payload_t": 19.2, "emissions_kg_co2e_per_km": 0.99773, "aliases": ["8x4 mixer"],
        "routing": {"gross_weight_kg": 32000, "axle_count": 4},
        "labels": {"en": "8x4 rigid mixer (32 t)", "eu": "N3 lorry (BA) 4-axle mixer 32 t"}, "fuel": "diesel"},
    "N3 tractor (BC) + O4 semi (DA) GCW 40 t": {
        "code": "V11", "planning_vehicle": True, "eu_category": "N3 + O4", "body_code": "BC + DA", "licence": "C+E",
        "gvw_t": 40, "payload_t": 25.5, "emissions_kg_co2e_per_km": 0.93939, "aliases": ["40 t artic"],
        "routing": {"gross_weight_kg": 40000},
        "labels": {"en": "Artic (40 t)", "eu": "N3 tractor (BC) + O4 semi (DA) GCW 40 t"}, "fuel": "diesel"},
    "N3 tractor (BC) + O4 tipping semi (DA) GCW 40/44 t": {
        "code": "V12", "planning_vehicle": True, "eu_category": "N3 + O4", "body_code": "BC + DA", "licence": "C+E",
        "gvw_t": 40, "payload_t": 26, "emissions_kg_co2e_per_km": 0.93939, "aliases": ["artic tipper"],
        "routing": {"gross_weight_kg": 40000},
        "labels": {"en": "Artic tipper (40/44 t)", "eu": "N3 tractor (BC) + O4 tipping semi (DA) GCW 40/44 t"}, "fuel": "diesel"},
}
V07, V10, V11, V12 = list(EU_OLD)
OLD = json.loads(json.dumps(F))
OLD["vehicles"].update(json.loads(json.dumps(EU_OLD)))
for _k in PLANNING:                 # until 11 Oct the UK entries carried no flag
    OLD["vehicles"][_k].pop("planning_vehicle", None)
OLD["planning_vehicles"] = [V07, V10, V11, V12]
for _c, _add in (("Earthworks / soil", [V07, V12]), ("Small aggregate", [V07, V12]), ("Large aggregate / ballast", [V07, V12]),
                 ("Precast / concrete", [V10, V11]), ("Steel / rail", [V11]), ("General / imported", [V11, V12]), ("_default", [V07])):
    OLD["material_categories"][_c]["vehicles"] = _add + OLD["material_categories"][_c]["vehicles"]
OLD["vehicle_sets"]["GB"]["hide"] = [V07, V10, V11, V12, "Rigid 7.5t"]
ok("A3: ⭐ a document still carrying the four EU entries passes validation — no rule refuses them (the live row must keep saving)",
   config.validate(OLD) == [] and config.validate(OLD, network=network) == [], str(config.validate(OLD, network=network))[:300])
_sv = config.save(OLD, by="test_week1 A3", network=network)
config.invalidate()
_m = main.meta()
ok("A3: ...it saves as the live document and /api/meta serves it: all fifteen vehicles, the four lead (no country set)",
   _sv.get("ok") is True and len(_m["vehicles"]) == 15 and _m["planning_vehicles"] == [V07, V10, V11, V12]
   and _m["hidden_vehicles"] == [], str(_sv)[:200])
_ovl = _m["vehicle_labels"]
ok("A3: ⭐ its EU strings keep resolving — 'eu' is OFFERED because its vehicles carry it, with English first",
   _ovl["langs"] == ["en", "eu"] and _ovl["labels"][V12]["eu"] == V12 and _ovl["labels"][V12]["en"] == "Artic tipper (40/44 t)"
   and _ovl["labels"]["Artic Tipper (44t)"]["eu"] == "Artic Tipper (44t)" and "eu" in _ovl["fallbacks"]["Artic Tipper (44t)"])
ok("A3: ...and the language list is only languages a vehicle uses — no 'ee' (no vehicle carries one)",
   "ee" not in _ovl["langs"] and all(set(v) == {"en", "eu"} for v in _ovl["labels"].values()))
ok("A3: its fallback payload is still its own first planning vehicle's (V07, 18 t), named",
   derived.payload_for("Ghost lorry", OLD) == (18.0, V07) and derived.payload_for(V12, OLD) == (26.0, None))
ok("A3: its chips still print the vehicle's own code, its artics still price as artics",
   derived.vehicle_short(V12, OLD) == "V12" and fairprice.vehicle_class(V11, OLD) == "artic" and fairprice.vehicle_class(V07, OLD) == "rigid")
ok("A3: its weight-only artic still routes on weight alone — no dimensions or axles invented",
   set(here_routing._truck_params(V11, OLD)) == {"transportMode", "vehicle[grossWeight]"})
_OGB = json.loads(json.dumps(OLD)); _OGB["tenant"]["country"] = "GB"
ok("A3: the same document for a GB tenant (the live demo's case): GB's lead list, the four + Rigid 7.5t hidden, English only offered",
   conversions.planning_vehicle_names(_OGB)[0] == "Rigid 8-wheeler (32t)"
   and conversions.hidden_vehicle_names(_OGB) == [V07, V10, V11, V12, "Rigid 7.5t"]
   and conversions.vehicle_labels(_OGB)["langs"] == ["en"] and derived.payload_for("Ghost lorry", _OGB) == (20.0, "Rigid 8-wheeler (32t)"))
# 11 Oct 2026 (review): Reset to file is now the one path where the file LACKS vehicles a live
# document carries, so it must be held to Save's rule — a vehicle the network is baked for cannot
# be removed. Until this fix the reset called save() with no network and dropped a baked EU
# vehicle silently (its geometry orphaned, every line on it re-based on the fallback payload).
# Baked here: V07 (which the file lacks) and the default profile (which the file keeps).
for _vp in (V07, "Artic Tipper (44t)"):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
               "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), "RA3", _vp, "loaded", 0, "[[-0.5,53.2],[-0.4,53.3]]", 30.0, 0.7))
_rr = None
try:
    main.reset_factors_config(updated_by="test_week1 A3", token=os.environ.get("ADMIN_TOKEN"))
except Exception as _e:
    _rr = _e
config.invalidate()
ok("A3 (11 Oct 2026 review): ⭐ Reset to file is REFUSED (400) while the network is baked for an EU vehicle the file lacks, naming it",
   getattr(_rr, "status_code", None) == 400
   and f"vehicle '{V07}' has baked route geometry and cannot be removed" in str(getattr(_rr, "detail", "")), repr(_rr)[:300])
ok("A3 (11 Oct 2026 review): ...and the refused reset leaves the live document as it was: all four EU entries, V07 still leads",
   set(EU_OLD) <= set(conversions.load_factors()["vehicles"]) and main.meta()["planning_vehicles"] == [V07, V10, V11, V12]
   and config.status(conversions)["differs_from_file"] is True)
ok("A3 (11 Oct 2026 review): ...the refusal names ONLY the vehicle the file lacks — the baked default profile, which the file keeps, is not a problem",
   "Artic Tipper (44t)" not in str(getattr(_rr, "detail", "")))
ok("A3 (11 Oct 2026 review): the reset endpoint and reset_to_file both pass the network through (source level)",
   # 14 Oct 2026 (G3): the name now goes through main._by() (a login's own name wins over the typed one)
   "reset_to_file(conversions, by=_by(updated_by), network=network)" in inspect.getsource(main.reset_factors_config)
   and "save(doc, by=f\"reset:factors.json ({by or 'unknown'})\", network=network)" in inspect.getsource(config.reset_to_file))
db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ?",
           (db.current_tenant(), "RA3", V07))
# NARROWED 11 Oct 2026 (review): the reset below now goes through the endpoint (which passes the
# network) once V07's geometry is gone; the default profile's baked row stays and must not block it.
_rok = main.reset_factors_config(updated_by="test_week1 A3", token=os.environ.get("ADMIN_TOKEN"))
config.invalidate()
ok("A3 (11 Oct 2026 review): with no baked geometry on a vehicle the file lacks, the endpoint's reset succeeds (a baked profile the file keeps does not block it)",
   _rok.get("ok") is True)
ok("A3: Reset to file brings back the seed: the six UK lead names, no EU entry",
   main.meta()["planning_vehicles"] == PLANNING and not set(EU_OLD) & set(main.meta()["vehicles"]))

# the never-empty lead list (conversions.planning_vehicle_names, 11 Oct 2026)
_NOPL = json.loads(json.dumps(F)); _NOPL["planning_vehicles"] = []
for _k in _NOPL["vehicles"]:
    if not _k.startswith("_"):
        _NOPL["vehicles"][_k].pop("planning_vehicle", None)
_fb = conversions.planning_vehicle_names(_NOPL)
_scen = {k for k in ALL_V if F["vehicles"][k].get("scenario_only")}
ok("A3: ⭐ with no planning array and no flag (no country set) the lead list is NOT empty: the vehicles the categories list, Rigid 8-wheeler first",
   _fb and _fb[0] == "Rigid 8-wheeler (32t)" and set(_fb) <= selectable, str(_fb))
ok("A3: ⭐ ...and it holds no scenario-only (electric) profile and no hidden one — a picker never offers those",
   not (set(_fb) & _scen) and "Rigid 7.5t" not in conversions.planning_vehicle_names({**_NOPL, "tenant": {**_NOPL["tenant"], "country": "NO"}})
   and not set(conversions.planning_vehicle_names(_NOPL, "GB")) & set(conversions.hidden_vehicle_names(_NOPL, "GB")))
_NOPL2 = json.loads(json.dumps(_NOPL)); _NOPL2["vehicle_sets"] = {}
ok("A3: ...a country with no vehicle set gets the same fallback, and the seed's own list for every such country is non-empty",
   conversions.planning_vehicle_names(_NOPL2, "NO") == _fb and conversions.planning_vehicle_names(F, "NO") == PLANNING
   and conversions.planning_vehicle_names(F, "EE") == PLANNING)
_NOCAT = json.loads(json.dumps(_NOPL))
for _c in _NOCAT["material_categories"].values():
    if isinstance(_c, dict):
        _c["vehicles"] = []
ok("A3: ...and with no category listing a vehicle either, every usable vehicle in file order (still no electric one)",
   conversions.planning_vehicle_names(_NOCAT) == [k for k in ALL_V if k not in _scen])
ok("A3: the payload fallback is a NAMED vehicle in every case above — never None while a vehicle is usable",
   derived.payload_for("Ghost lorry", _NOPL)[1] == "Rigid 8-wheeler (32t)" and derived.payload_for("Ghost lorry", _NOCAT)[1] == "Rigid 7.5t"
   and derived.payload_for("Ghost lorry", F) == (20.0, "Rigid 8-wheeler (32t)"))
ok("A3: a document with no usable vehicle at all falls back to its own _default payload, unnamed — not the old 18 t literal",
   derived.payload_for("Ghost lorry", {"vehicles": {"_default": {"payload_t": 20}}}) == (20.0, None)
   and derived.payload_for("Ghost lorry", {"vehicles": {}}) == (20.0, None))


# =========================================================================== #
#  B. Multi-year save                                                          #
# =========================================================================== #
reset_db()
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L1", "Pit", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L2", "Site", 58.6, 24.4))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R1", "L1", "L2"))

# Jan 2026 (1) .. Dec 2027 (24) in ONE post, values on the four corners of the range
res = main.save_matrix_row(main.MatrixRow(
    route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)",
    submitted_by="tester", unit="t", status="Pending",
    cells=[main.Cell(month_index=m, quantity=(50.0 if m in (1, 12, 13, 24) else 0.0))
           for m in range(1, 25)]))
ok("B: ⭐ one bulk POST saves across two calendar years",
   res["months_saved"] == 4, str(res))
rows = main.list_forecasts(route_id="R1")
ok("B: exactly the four non-zero months are stored", len(rows) == 4)
ok("B: and they are month_index 1, 12, 13, 24 — absolute, not per-year",
   sorted(r["month_index"] for r in rows) == [1, 12, 13, 24])
ok("B: ⭐ MONTH_COUNT is unchanged", main.MONTH_COUNT == 60)
ok("B: ⭐ and no `year` column was added to forecasts",
   "year" not in cols("forecasts"))
ok("B: the UNIQUE key is still the Phase 4.5 one",
   "UNIQUE (tenant_id, route_id, month_index, discipline, section_id)"
   in db._TENANT_DDL["forecasts"])
# re-saving the same range must UPDATE, not duplicate — the ON CONFLICT target has to
# keep matching the constraint across a 24-cell post exactly as it did across 12
main.save_matrix_row(main.MatrixRow(
    route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)",
    submitted_by="tester", unit="t", status="Pending",
    cells=[main.Cell(month_index=m, quantity=(70.0 if m in (1, 12, 13, 24) else 0.0))
           for m in range(1, 25)]))
rows = main.list_forecasts(route_id="R1")
ok("B: re-saving the range upserts rather than duplicating", len(rows) == 4)
ok("B: ...with the new quantities", all(r["quantity"] == 70.0 for r in rows))
# a zero inside the range clears that month and ONLY that month
main.save_matrix_row(main.MatrixRow(
    route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)",
    submitted_by="tester", unit="t", status="Pending",
    cells=[main.Cell(month_index=m, quantity=(70.0 if m in (1, 13, 24) else 0.0))
           for m in range(1, 25)]))
ok("B: a zero inside the range deletes that month",
   sorted(r["month_index"] for r in main.list_forecasts(route_id="R1")) == [1, 13, 24])
# ⭐ narrowing the range must not reach the year it no longer covers
main.save_matrix_row(main.MatrixRow(
    route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)",
    submitted_by="tester", unit="t", status="Pending",
    cells=[main.Cell(month_index=m, quantity=0.0) for m in range(1, 13)]))
ok("B: ⭐ saving 2026 alone leaves 2027's months untouched",
   sorted(r["month_index"] for r in main.list_forecasts(route_id="R1")) == [13, 24])
# and a second discipline on the same route+months is still its own line
seed_line(route_id="R1", disc="substructure", sect="WS2", months=(13, 24), qty=9.0)
ok("B: a second discipline over the same months is a separate line",
   len(main.list_forecasts(route_id="R1")) == 4)
ok("B: withdrawing one line's span leaves the other's",
   main.withdraw_route("R1", submitted_by="tester", **{"from_": 13, "to": 24},
                       discipline="substructure", section_id="WS2")["deleted"] == 2
   and len(main.list_forecasts(route_id="R1")) == 2)


# =========================================================================== #
#  C. forecast_weeks — schema, materialise-on-approve, edit, confirm           #
# =========================================================================== #
reset_db()
ok("C: forecast_weeks table is created", "forecast_weeks" in tables())
fw = cols("forecast_weeks")
for c in ("tenant_id", "route_id", "month_index", "discipline", "section_id",
          "week_index", "planned_qty", "unit", "status", "weather", "wetness",
          "traffic", "other", "confirmed_by", "confirmed_at",
          "actual_qty", "actual_note", "actual_by", "actual_at"):
    ok(f"C: forecast_weeks has {c}", c in fw)
# ⭐ Task D's four columns are created NOW, with Task C's table, precisely so there is
# no second migration on a live Postgres a day later.
ok("C: ⭐ the Task D actual columns exist from the first migration",
   all(c in fw for c in ("actual_qty", "actual_note", "actual_by", "actual_at")))
ok("C: tenant_id is FIRST in the primary key",
   pk_order("forecast_weeks")[0] == "tenant_id")
ok("C: the rest of the key is the line plus the week",
   pk_order("forecast_weeks") == ["tenant_id", "route_id", "month_index",
                                  "discipline", "section_id", "week_index"])
ok("C: forecast_weeks is registered in TENANTED_TABLES",
   "forecast_weeks" in db.TENANTED_TABLES)
ok("C: ...and has a _TENANT_DDL entry and a _TENANT_PK entry",
   "forecast_weeks" in db._TENANT_DDL and "forecast_weeks" in db._TENANT_PK)

db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L1", "Pit", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L2", "Site", 58.6, 24.4))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R1", "L1", "L2"))
seed_line(months=(9, 10), qty=100.0)

ok("C: ⭐ a Pending line materialises NO weeks",
   len(weeks.list_weeks(9, 10)) == 0)
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")
w = weeks.list_weeks(9, 10)
ok("C: approving the line creates the month's weeks — four for Sep 2026, five for Oct", len(w) == 9, str(len(w)))
ok("C: ⭐ planned_qty is the month divided by ITS number of weeks (÷4 in Sep, ÷5 in Oct)",
   all(abs(r["planned_qty"] - (25.0 if r["month_index"] == 9 else 20.0)) < 1e-9 for r in w))
ok("C: the weeks inherit the parent's unit", all(r["unit"] == "t" for r in w))
ok("C: they start as `derived`", all(r["status"] == "derived" for r in w))
ok("C: week_index runs 1-4 in Sep and 1-5 in Oct",
   sorted({r["week_index"] for r in w if r["month_index"] == 9}) == [1, 2, 3, 4]
   and sorted({r["week_index"] for r in w if r["month_index"] == 10}) == [1, 2, 3, 4, 5])

# an edit sticks, and moves the row to `edited`
weeks.set_week("R1", 9, "earthworks", "WS1", 2, planned_qty=40.0)
row = weeks.get_week("R1", 9, "earthworks", "WS1", 2)
ok("C: editing a week's planned quantity stores it", row["planned_qty"] == 40.0)
ok("C: ...and marks it `edited`", row["status"] == "edited")

# re-approving after the parent month changes: derived refreshes, edited does not
seed_line(months=(9,), qty=200.0, status="Pending")
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")
w9 = {r["week_index"]: r for r in weeks.list_weeks(9, 9)}
ok("C: ⭐ a re-approved month refreshes its `derived` weeks",
   abs(w9[1]["planned_qty"] - 50.0) < 1e-9, str(w9[1]["planned_qty"]))
ok("C: ⭐ ...and leaves an `edited` one alone", w9[2]["planned_qty"] == 40.0)
ok("C: the edited week is flagged as out of step with its parent",
   bool(w9[2].get("parent_changed")) and not w9[1].get("parent_changed"))

# confirm carries the four optional flags and nothing else
weeks.confirm_week("R1", 9, "earthworks", "WS1", 3, by="planner",
                   flags={"weather": "wet", "wetness": "", "traffic": "", "other": ""})
c3 = weeks.get_week("R1", 9, "earthworks", "WS1", 3)
ok("C: confirming a week sets `confirmed`", c3["status"] == "confirmed")
ok("C: ...records who and when", c3["confirmed_by"] == "planner" and c3["confirmed_at"])
ok("C: ...stores the flags as free text, empty allowed",
   c3["weather"] == "wet" and c3["wetness"] == "")
# week 3 was confirmed while the parent stood at 200, so it holds 200/4 = 50. Pushing
# the parent to 400 must move the derived weeks to 100 and leave week 3 at 50.
_before_confirmed = weeks.get_week("R1", 9, "earthworks", "WS1", 3)["planned_qty"]
seed_line(months=(9,), qty=400.0, status="Pending")
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")
ok("C: ⭐ a confirmed week is NOT refreshed by re-approving its parent",
   weeks.get_week("R1", 9, "earthworks", "WS1", 3)["planned_qty"] == _before_confirmed
   and _before_confirmed == 50.0, str(_before_confirmed))
ok("C: ...while the derived weeks around it DO move",
   weeks.get_week("R1", 9, "earthworks", "WS1", 1)["planned_qty"] == 100.0)
ok("C: ...and the edited one still does not",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["planned_qty"] == 40.0)
ok("C: the confirmed week is flagged as out of step with its parent",
   weeks.get_week("R1", 9, "earthworks", "WS1", 3)["parent_changed"] is True)

# week arithmetic — CALENDAR weeks since 10 Sep 2026 (Mon–Sun; a week belongs to the
# month holding its Thursday). 1 Sep 2026 is a Tuesday.
import datetime as _dt
ok("C: Tue 1 Sep 2026 is in week 1 of September", weeks.week_of_date(_dt.date(2026, 9, 1), 2026) == (9, 1))
ok("C: ⭐ Mon 31 Aug 2026 is ALSO week 1 of September (its Thursday is 3 Sep)",
   weeks.week_of_date(_dt.date(2026, 8, 31), 2026) == (9, 1))
ok("C: Sun 6 Sep is still week 1; Mon 7 Sep is week 2",
   weeks.week_of_date(_dt.date(2026, 9, 6), 2026) == (9, 1) and weeks.week_of_date(_dt.date(2026, 9, 7), 2026) == (9, 2))
ok("C: Wed 30 Sep 2026 belongs to OCTOBER week 1 (its Thursday is 1 Oct)",
   weeks.week_of_date(_dt.date(2026, 9, 30), 2026) == (10, 1))
ok("C: every week starts on a Monday", all(weeks.week_span(m, w, 2026)[0].weekday() == 0
   for m in range(1, 25) for w in range(1, weeks.weeks_in_month(m, 2026) + 1)))
ok("C: September 2026 has four weeks, October five", weeks.weeks_in_month(9, 2026) == 4 and weeks.weeks_in_month(10, 2026) == 5)
ok("C: months never overlap and never leave a gap",
   all(weeks.week_span(m + 1, 1, 2026)[0] == weeks.week_span(m, weeks.weeks_in_month(m, 2026), 2026)[1] + _dt.timedelta(days=1)
       for m in range(1, 24)))
ok("C: next week inside a month is the following bucket",
   weeks.next_week(month_index=9, week_index=1) == (9, 2))
ok("C: ⭐ past the month's last week, next week is week 1 of the NEXT month",
   weeks.next_week(month_index=9, week_index=4) == (10, 1) and weeks.next_week(10, 4) == (10, 5) and weeks.next_week(10, 5) == (11, 1))
ok("C: prev_week steps back into the previous month's LAST week (five in October)",
   weeks.prev_week(11, 1) == (10, 5) and weeks.prev_week(10, 1) == (9, 4))

# visibility: until Task F, the same as /api/forecasts
ok("C: the week feed is tenant-scoped like every other read",
   all("tenant_id" not in r for r in weeks.list_weeks(9, 10)))


# =========================================================================== #
#  D. Actuals, variance, calibrate                                             #
# =========================================================================== #
reset_db()
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L1", "Pit", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)",
           ("L2", "Site", 58.6, 24.4))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R1", "L1", "L2"))
seed_line(months=(9,), qty=100.0)
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")

weeks.set_actual("R1", 9, "earthworks", "WS1", 1, actual_qty=20.0,
                 actual_note="rain", by="foreman")
w1 = weeks.get_week("R1", 9, "earthworks", "WS1", 1)
ok("D: a typed actual is stored", w1["actual_qty"] == 20.0)
ok("D: ...with its note and author", w1["actual_note"] == "rain" and w1["actual_by"] == "foreman")
ok("D: ⭐ variance = planned - actual", w1["variance"] == 5.0, str(w1["variance"]))
ok("D: ⭐ variance is blank until an actual is typed",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["variance"] is None)
# ⭐ saving an actual must NOT calibrate. Two people reported that as the surprising
# behaviour to avoid, and it is one line away from happening by accident.
ok("D: ⭐ saving the actual does NOT move next week",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["planned_qty"] == 25.0)
ok("D: ...and does not change this week's plan either", w1["planned_qty"] == 25.0)

res = weeks.calibrate("R1", 9, "earthworks", "WS1", 1)
w2 = weeks.get_week("R1", 9, "earthworks", "WS1", 2)
ok("D: ⭐ calibrate adds the variance to next week only", w2["planned_qty"] == 30.0,
   str(w2["planned_qty"]))
ok("D: ...and marks next week `edited`", w2["status"] == "edited")
ok("D: weeks after next are untouched",
   weeks.get_week("R1", 9, "earthworks", "WS1", 3)["planned_qty"] == 25.0
   and weeks.get_week("R1", 9, "earthworks", "WS1", 4)["planned_qty"] == 25.0)
ok("D: this week's own plan is untouched",
   weeks.get_week("R1", 9, "earthworks", "WS1", 1)["planned_qty"] == 25.0)
ok("D: calibrate says which week it wrote", res.get("to") == {"month_index": 9, "week_index": 2})

# an explicit override replaces the formula, not adds to it
weeks.calibrate("R1", 9, "earthworks", "WS1", 1, override_qty=12.0)
ok("D: a typed override replaces next week's plan outright",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["planned_qty"] == 12.0)

# blocked when next week is confirmed
weeks.confirm_week("R1", 9, "earthworks", "WS1", 2, by="planner", flags={})
blocked = weeks.calibrate("R1", 9, "earthworks", "WS1", 1)
ok("D: ⭐ calibrate refuses when next week is already confirmed",
   bool(blocked.get("error")), str(blocked))
ok("D: ...and says so rather than failing quietly",
   "confirm" in (blocked.get("error") or "").lower())
ok("D: ...and next week's number did not move",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["planned_qty"] == 12.0)

# calibrating week 4 must reach into the next month, not off the end
seed_line(months=(9, 10), qty=100.0, status="Pending")
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")
weeks.set_actual("R1", 9, "earthworks", "WS1", 4, actual_qty=5.0, by="foreman")
weeks.calibrate("R1", 9, "earthworks", "WS1", 4)
ok("D: ⭐ calibrating week 4 writes week 1 of the NEXT month",
   weeks.get_week("R1", 10, "earthworks", "WS1", 1)["planned_qty"] == 40.0,   # 100÷5 + 20 short
   str(weeks.get_week("R1", 10, "earthworks", "WS1", 1)["planned_qty"]))

# ⭐ Crossing a month boundary calls materialise_line() for the next month, which is
# the ONE place a materialise happens outside an approval. It must still refuse to
# create weeks for a month that is not approved — otherwise pressing calibrate on the
# last week of an approved month silently brings a Pending month into the look-ahead.
seed_line(route_id="R1", disc="structures", sect="WS4", months=(11, 12), qty=80.0)
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="structures", section_id="WS4")
# reopen month 12 only
db.execute("UPDATE forecasts SET status = ? WHERE tenant_id = ? AND route_id = ? "
           "AND month_index = ? AND discipline = ? AND section_id = ?",
           ("Pending", db.current_tenant(), "R1", 12, "structures", "WS4"))
db.execute("DELETE FROM forecast_weeks WHERE tenant_id = ? AND route_id = ? "
           "AND month_index = ? AND discipline = ? AND section_id = ?",
           (db.current_tenant(), "R1", 12, "structures", "WS4"))
weeks.set_actual("R1", 11, "structures", "WS4", 4, actual_qty=1.0, by="foreman")
_cross = weeks.calibrate("R1", 11, "structures", "WS4", 4)
ok("D: ⭐ calibrating into a month that is NOT approved refuses",
   bool(_cross.get("error")), str(_cross))
ok("D: ...and creates no weeks for it",
   weeks.get_week("R1", 12, "structures", "WS4", 1) is None)
ok("D: ...and says which month is the problem", "12" in (_cross.get("error") or ""))


# =========================================================================== #
#  D2. Stockpile capacity + weekly consumption                                 #
# =========================================================================== #
reset_db()
ok("D2: stockpile_weeks table is created", "stockpile_weeks" in tables())
sw = cols("stockpile_weeks")
for c in ("tenant_id", "location_id", "month_index", "week_index",
          "consumed_qty", "unit", "note", "updated_by", "updated_at"):
    ok(f"D2: stockpile_weeks has {c}", c in sw)
ok("D2: tenant_id is FIRST in the primary key",
   pk_order("stockpile_weeks")[0] == "tenant_id")
ok("D2: stockpile_weeks is registered in TENANTED_TABLES",
   "stockpile_weeks" in db.TENANTED_TABLES)
lc = cols("locations")
for c in ("capacity_qty", "capacity_unit", "opening_qty"):
    ok(f"D2: locations has {c}", c in lc)
ok("D2: ⭐ the three new location columns are in _TENANT_DDL, not only ALTERed",
   all(c in db._TENANT_DDL["locations"]
       for c in ("capacity_qty", "capacity_unit", "opening_qty")))

db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
           ("L1", "Pit", 58.5, 24.0, "Quarry"))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
           ("L2", "North stockpile", 58.6, 24.4, "Stockpile"))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R1", "L1", "L2"))
stockpiles.set_capacity("L2", capacity_qty=3000.0, capacity_unit="t", opening_qty=200.0)

seed_line(months=(9,), qty=400.0)
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")

# NARROWED 27 Oct 2026 (stockpile forecast, John's D2 and D8): "no week actual = inbound 0" now holds for a place with
# neither a capacity nor a planned use (records only). A pile WITH a capacity runs forward from the plan: an unrecorded
# past week counts the plan, labelled (test_stockpile_forecast.py has every case). Both are pinned here.
stockpiles.set_capacity("L2", capacity_qty=None, capacity_unit=None, opening_qty=200.0)
bal = stockpiles.balances(9, 9)["stockpiles"]
L2 = [s for s in bal if s["location_id"] == "L2"][0]
w = {r["week_index"]: r for r in L2["weeks"]}
ok("D2: ⭐ inbound is 0 until a week ACTUAL is typed — never the month forecast (records only: no capacity, no plan)",
   all(r["inbound"] == 0 for r in w.values()) and L2["forecast"] is False)
ok("D2: balance therefore starts at the opening figure", w[1]["balance_end"] == 200.0)
stockpiles.set_capacity("L2", capacity_qty=3000.0, capacity_unit="t", opening_qty=200.0)
w = {r["week_index"]: r for r in
     [s for s in stockpiles.balances(9, 9)["stockpiles"] if s["location_id"] == "L2"][0]["weeks"]}
ok("D2: remaining = capacity - balance (with a capacity the plan stands in for the unrecorded week: 200 + 100)",
   w[1]["remaining"] == 2700.0 and w[1]["inbound"] == 100.0 and w[1]["basis"] == "plan", str(w[1]))
ok("D2: not over capacity", w[1]["over"] is False)

weeks.set_actual("R1", 9, "earthworks", "WS1", 1, actual_qty=500.0, by="foreman")
stockpiles.consume("L2", 9, 1, consumed_qty=100.0, unit="t", note="", by="foreman")
w = {r["week_index"]: r for r in
     [s for s in stockpiles.balances(9, 9)["stockpiles"]
      if s["location_id"] == "L2"][0]["weeks"]}
ok("D2: a week actual on a route INTO the stockpile becomes inbound", w[1]["inbound"] == 500.0)
ok("D2: typed consumption is stored", w[1]["consumed"] == 100.0)
ok("D2: ⭐ balance = opening + inbound - consumed", w[1]["balance_end"] == 600.0,
   str(w[1]["balance_end"]))
ok("D2: ⭐ remaining = capacity - (opening + inbound - consumed)",
   w[1]["remaining"] == 2400.0, str(w[1]["remaining"]))
# NARROWED 27 Oct 2026 (D2): week 2 has no record, so the plan's 100 t stands in (records only, it carried 600)
ok("D2: the balance carries forward into week 2, plus the plan where nothing was recorded",
   w[2]["balance_end"] == 700.0 and w[2]["in_basis"] == "plan", str(w[2]))

# over capacity is a FLAG, never a block
weeks.set_actual("R1", 9, "earthworks", "WS1", 2, actual_qty=5000.0, by="foreman")
w = {r["week_index"]: r for r in
     [s for s in stockpiles.balances(9, 9)["stockpiles"]
      if s["location_id"] == "L2"][0]["weeks"]}
ok("D2: ⭐ over capacity is flagged", w[2]["over"] is True)
ok("D2: ...and remaining goes negative rather than clamping", w[2]["remaining"] < 0)
ok("D2: ⭐ and nothing is blocked — the actual still saved",
   weeks.get_week("R1", 9, "earthworks", "WS1", 2)["actual_qty"] == 5000.0)

# no capacity recorded: the balance still computes, remaining is unknown
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
           ("L3", "Unmeasured stockpile", 58.7, 24.5, "Stockpile"))
L3 = [s for s in stockpiles.balances(9, 9)["stockpiles"]
      if s["location_id"] == "L3"][0]
ok("D2: ⭐ a stockpile with no capacity still balances", L3["weeks"][0]["balance_end"] == 0.0)
ok("D2: ...and reports remaining as unknown, not zero",
   L3["weeks"][0]["remaining"] is None and L3["capacity_qty"] is None)
ok("D2: ...and is never `over`", L3["weeks"][0]["over"] is False)

# dest_id missing: inbound stays 0, nothing is guessed
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R9", "L1", None))
seed_line(route_id="R9", disc="earthworks", sect="WS3", months=(9,), qty=999.0)
main.set_route_status("R9", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS3")
weeks.set_actual("R9", 9, "earthworks", "WS3", 1, actual_qty=999.0, by="foreman")
tot = sum(r["inbound"] for s in stockpiles.balances(9, 9)["stockpiles"]
          for r in s["weeks"])
# NARROWED 27 Oct 2026 (D2): 5 500 t recorded + the plan's 100 t for each of the two unrecorded weeks; R9's 999 t, with
# no destination, is still nowhere
ok("D2: ⭐ a route with no dest_id contributes nothing — no guessing",
   tot == 5700.0, str(tot))


# =========================================================================== #
#  E. Railhead                                                                #
# =========================================================================== #
reset_db()
r = network.create_location("Lelle railhead", "origin", lat=58.8797, lon=24.8236,
                            loc_type="Railhead", supplies=["Large aggregate / ballast"])
got = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?",
               (db.current_tenant(), r["id"]))[0]
ok("E: a location can be created with loc_type 'Railhead'",
   got["loc_type"] == "Railhead")
ok("E: ⭐ a railhead defaults to an origin role, like a quarry or a port",
   network._role_for("Railhead") == "origin")
ok("E: a Stockpile defaults to a destination role",
   network._role_for("Stockpile") == "destination")
fc = network.locations_geojson()
f = [x for x in fc["features"] if x["properties"]["id"] == r["id"]][0]
ok("E: it reaches the map's location feed as a Railhead",
   f["properties"]["loc_type"] == "Railhead")
# 2026-09-02 rename: 'Rail head' -> 'Railhead'. Old rows must not vanish, and the old
# string must never be written again.
ok("E2: the spelling is one word everywhere the type is declared",
   "Railhead" in stockpiles.STORAGE_TYPES and "Rail head" not in stockpiles.STORAGE_TYPES)
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) "
           "VALUES (?, ?, ?, ?, ?, ?)", ("default", "OLD1", "Old spelling", 58.9, 24.8, "Rail head"))
_old = [x for x in network.locations_geojson()["features"] if x["properties"]["id"] == "OLD1"][0]
ok("E2: ⭐ a row still spelled 'Rail head' is READ as 'Railhead'",
   _old["properties"]["loc_type"] == "Railhead")
ok("E2: ...and is still an origin", network._role_for("Rail head") == "origin")
ok("E2: ...and still counts as a storage location",
   any(l["id"] == "OLD1" for l in stockpiles.storage_locations()))
ok("E2: ...and reaches the public map as a Railhead node",
   [x for x in network.public_map_data()["features"]
    if x["properties"].get("id") == "OLD1"][0]["properties"]["node_type"] == "Railhead")
r2 = network.create_location("Posted old", "origin", lat=58.9, lon=24.8, loc_type="Rail head")
ok("E2: ⭐ a client that still POSTs 'Rail head' gets 'Railhead' WRITTEN",
   db.query("SELECT loc_type FROM locations WHERE tenant_id = ? AND id = ?",
            (db.current_tenant(), r2["id"]))[0]["loc_type"] == "Railhead")
network.update_location("OLD1", loc_type="Rail head")
ok("E2: ...and so does an update", db.query(
    "SELECT loc_type FROM locations WHERE tenant_id = ? AND id = ?",
    (db.current_tenant(), "OLD1"))[0]["loc_type"] == "Railhead")
db.execute("UPDATE locations SET loc_type = ? WHERE tenant_id = ? AND id = ?",
           ("Rail head", db.current_tenant(), "OLD1"))
db.init_weeks_db()
ok("E2: ⭐ the boot migration rewrites the old string in place",
   db.query("SELECT loc_type FROM locations WHERE tenant_id = ? AND id = ?",
            (db.current_tenant(), "OLD1"))[0]["loc_type"] == "Railhead")
ok("E2: no source file still declares the two-word type",
   not any("\"Rail head\"" in open(os.path.join(BACKEND, fn), encoding="utf-8").read()
           for fn in os.listdir(BACKEND) if fn.endswith(".py") and fn != "network.py"))


# =========================================================================== #
#  The rail geometry file — what it IS, and what it is NOT                     #
# =========================================================================== #
# G2, 16 Sep 2026: the existing-railway geometry is TENANT DATA — the `rail`
# FeatureCollection of the overlay package — not a shipped file. The honesty
# assertions that used to run against one project's provisional file now run against
# the demo package in test_modus.py. What is enforceable HERE: no static file ships,
# the map reads the rail from the package, and the layer still draws from the same
# global the overlay module fills.
RAIL = os.path.join(ROOT, "map", "data", "evr_rail.js")
ok("E: G2 — no static rail geometry file ships", not os.path.exists(RAIL))
_ov = open(os.path.join(ROOT, "map", "overlay.js"), encoding="utf-8").read()
ok("E: the overlay module fills window.evr_rail_data from the package's `rail`",
   "window.evr_rail_data = (o.rail" in _ov)
_mp = open(os.path.join(ROOT, "map", "index.html"), encoding="utf-8").read()
ok("E: the map no longer loads a static rail file", "data/evr_rail.js" not in _mp)
# REVERSED 28 Oct 2026 (task 0a, John: the rail option off the panel; the public map no longer draws the railway).
# The organisation file keeps its `rail` (the overlay module still fills the global, above); the map reads none of it.
ok("E: 🔴 the map no longer draws the corridor (reads nothing from window.evr_rail_data)",
   "window.evr_rail_data" not in _mp)
ok("E: 🔴 no evr-rail source or layer; the alignment keeps its own source",
   "alignment-source" in _mp and "'evr-rail" not in _mp and "Existing rail network" not in _mp)


# =========================================================================== #
#  Cross-cutting: units, the endpoint wrappers, and what must NOT exist        #
# =========================================================================== #
reset_db()
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
           ("L1", "Pit", 58.5, 24.0, "Quarry"))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)",
           ("L2", "Volume stockpile", 58.6, 24.4, "Stockpile"))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)",
           ("R1", "L1", "L2"))
# ⭐ A line entered in m3 delivering into a stockpile measured in TONNES. Adding those
# together untouched would produce a number with no meaning, and it would look right.
stockpiles.set_capacity("L2", capacity_qty=1000.0, capacity_unit="t", opening_qty=0.0)
main.save_matrix_row(main.MatrixRow(
    route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)",
    submitted_by="tester", unit="m3", status="Pending",
    cells=[main.Cell(month_index=9, quantity=400.0)]))
main.set_route_status("R1", main.StatusUpdate(status="Approved"),
                      discipline="earthworks", section_id="WS1")
weeks.set_actual("R1", 9, "earthworks", "WS1", 1, actual_qty=100.0, by="foreman")
_w1 = [s for s in stockpiles.balances(9, 9)["stockpiles"]
       if s["location_id"] == "L2"][0]["weeks"][0]
# Small aggregate is 1.6 t/m3 in the real factors.json
ok("⭐ an m3 movement into a tonnes stockpile is CONVERTED, not added raw",
   abs(_w1["inbound"] - 160.0) < 1e-6, str(_w1["inbound"]))
ok("...and the balance is in the stockpile's unit", _w1["unit"] == "t")
_dens = conversions.load_factors()["material_categories"]["Small aggregate"]["density_t_per_m3"]
ok("...using the density from factors.json, not a constant",
   abs(_w1["inbound"] - 100.0 * _dens) < 1e-6)
# consumption typed in m3 against the same tonnes stockpile
stockpiles.consume("L2", 9, 1, consumed_qty=10.0, unit="m3", note="", by="foreman")
_w1 = [s for s in stockpiles.balances(9, 9)["stockpiles"]
       if s["location_id"] == "L2"][0]["weeks"][0]
ok("⭐ typed consumption is converted the same way",
   abs(_w1["consumed"] - 16.0) < 1e-6, str(_w1["consumed"]))

# the START_YEAR epoch has one definition, not two
ok("⭐ stockpiles.START_YEAR is set from main, not maintained separately",
   stockpiles.START_YEAR == main.START_YEAR == 2026)

# capacity is clearable — "we do not know how big this stockpile is" is a real state
stockpiles.set_capacity("L2", capacity_qty=None, capacity_unit=None, opening_qty=0.0)
_L2 = [s for s in stockpiles.balances(9, 9)["stockpiles"] if s["location_id"] == "L2"][0]
ok("D2: a capacity can be cleared back to unknown", _L2["capacity_qty"] is None)
ok("...and remaining goes back to unknown with it", _L2["weeks"][0]["remaining"] is None)

# the endpoint wrappers, called as plain functions
_res = main.list_forecast_weeks(from_month=9, to_month=10)
ok("the /api/forecast-weeks payload carries the server-chosen next week",
   isinstance(_res.get("next_week"), dict)
   and set(_res["next_week"]) == {"month_index", "week_index"})
ok("...the three statuses", _res["statuses"] == list(weeks.WEEK_STATUSES))
ok("...and the four flag names", _res["flag_fields"] == list(weeks.FLAG_FIELDS))
_sp = main.list_stockpiles(from_month=9, to_month=10)
ok("the /api/stockpiles payload names the storage types",
   _sp["storage_types"] == list(stockpiles.STORAGE_TYPES))
ok("...and the two capacity units", _sp["capacity_units"] == ["m3", "t"])

# ⭐ NOTHING MAY UPLOAD. "Never build: file upload, OCR..." — asserted at source level
# across every backend module, so a later edit that adds one trips here.
_backend_src = ""
for _fn in sorted(os.listdir(BACKEND)):
    if _fn.endswith(".py"):
        _backend_src += open(os.path.join(BACKEND, _fn), encoding="utf-8").read()
# NARROWED 31 Oct 2026 (task 4c PR 1, the approved site layouts plan): 'File(' is FastAPI's form-file marker, not
# zipfile.ZipFile( (a shapefile zip / KMZ read in memory). The one way a file reaches the server is the site layout's
# drawing, sent as the raw request body to /api/site-layouts/read (no form, no multipart), read in a stream capped at 10 MB.
for _banned in ("UploadFile", "File(", "multipart", "python-multipart"):
    _hits = len(re.findall(r"(?<!Zip)File\(", _backend_src)) if _banned == "File(" else _backend_src.count(_banned)
    ok(f"⭐ no upload path in the backend: {_banned!r} is absent",
       _hits == 0, "found in backend/*.py")
_main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("⭐ ...the one file the server takes is the site layout's drawing, as the raw body of /api/site-layouts/read, capped at 10 MB",
   _main_src.count("request.stream()") == 1 and '@app.post("/api/site-layouts/read")' in _main_src
   and _main_src.index("request.stream()") > _main_src.index('@app.post("/api/site-layouts/read")')
   and "if len(buf) > site_layout_import.MAX_BYTES:" in _main_src)
_reqs = open(os.path.join(BACKEND, "requirements.txt"), encoding="utf-8").read()
ok("⭐ ...and python-multipart is not a dependency", "multipart" not in _reqs)

# =========================================================================== #
#  F. IPT access codes — 2026-09-02                                            #
# =========================================================================== #
# ⚠️ The middleware that reads X-Access-Code never runs here (stubbed app). What is
# exercised is everything BELOW it: resolution, the demo fallback, the per-line filter
# on every staff endpoint, the write guards, and the approve gate. The header itself is
# unverified — the first thing to check on the deployment is that a wrong code gets 401.
def _as(code):
    access.set_current(code)

reset_db()
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L1", "Pit", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L2", "Site", 58.6, 24.4))
db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", ("R1", "L1", "L2", "IPT 3 / IPT 6"))
db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?)", ("R5", "L1", "L2", "IPT 5"))

# --- 2026-09-15: the demo codes are OPT-IN, and the default is now closed ----------
# The sign-in box used to print all three codes and the server honoured them whenever a
# Render variable was missing — a published password on a public URL, failing OPEN.
# ⚠️ This block runs with ALLOW_DEMO_CODES=1 (set at the head of the file), so every
# assertion below it still exercises demo mode; these four pin the gate itself.
_demo_saved = os.environ.pop("ALLOW_DEMO_CODES", None)
ok("0915: 🔴 with no env codes AND no opt-in, NOTHING resolves — it fails closed",
   all(access.resolve(c) is None for c in ("submitter123", "planner123", "admin123")))
ok("0915: ...and demo_mode() is false, so the UI does not relax the IPT rule",
   access.demo_mode() is False and access.demo_codes_allowed() is False)
for _bad in ("", "0", "false", "no", "  "):
    os.environ["ALLOW_DEMO_CODES"] = _bad
    if access.resolve("planner123") is not None:
        break
else:
    _bad = None
ok("0915: a blank or falsy ALLOW_DEMO_CODES does not open the door",
   _bad is None, f"opened on {_bad!r}")
os.environ["ALLOW_DEMO_CODES"] = "1" if _demo_saved is None else _demo_saved
ok("0915: ...and the explicit opt-in brings them back",
   access.resolve("planner123") is not None and access.demo_mode() is True)
_FRONTEND_SRC = open(os.path.join(BACKEND, "..", "frontend", "index.html"),
                     encoding="utf-8").read()
ok("0915: the sign-in box no longer names a working credential",
   not any(c in _FRONTEND_SRC for c in ("submitter123", "planner123", "admin123")))

# --- demo mode: no real code configured ----------------------------------------
ok("F: with no env codes the three demo codes resolve",
   all(access.resolve(c) for c in ("submitter123", "planner123", "admin123")))
ok("F: ...and an unknown code does not", access.resolve("letmein") is None)
ok("F: demo submitter sees all and cannot approve",
   access.resolve("submitter123")["ipt"] is None and not access.can_approve(access.resolve("submitter123")))
ok("F: /api/auth describes what a code grants",
   main.auth(main.AuthIn(code="planner123"))["can_approve"] is True
   and main.auth(main.AuthIn(code="planner123"))["demo"] is True)
try:
    main.auth(main.AuthIn(code="nope")); ok("F: /api/auth rejects an unknown code", False)
except Exception as e:
    ok("F: /api/auth rejects an unknown code with 401", getattr(e, "status_code", None) == 401)
_as("planner123")
seed_line(route_id="R1", disc="earthworks", sect="WS1", months=(9,), qty=10.0)
ok("F: in demo mode a planner may save with no ipt (pre-F behaviour)",
   main.list_forecasts(route_id="R1")[0]["ipt"] is None)
seed_line(route_id="R5", disc="earthworks", sect="WS1", months=(9,), qty=10.0)

# --- the one-off backfill: single-IPT routes only --------------------------------
_bf = network.backfill_forecast_ipt()
ok("F: ⭐ backfill fills a line on a single-IPT route", _bf["filled"] == 1
   and main.list_forecasts(route_id="R5")[0]["ipt"] == "IPT5")
ok("F: ⭐ ...and leaves a line on a SHARED route NULL — no guessing between two IPTs",
   _bf["left"] == 1 and main.list_forecasts(route_id="R1")[0]["ipt"] is None)
ok("F: the backfill is idempotent", network.backfill_forecast_ipt() == {"filled": 0, "left": 1})

# --- real codes configured ---------------------------------------------------------
os.environ.update({"IPT3_CODE": "three-secret", "IPT6_CODE": "six-secret",
                   "PLANNER_CODE": "plan-secret", "ADMIN_CODE": "adm-secret"})
ok("F: ⭐ once real codes exist, the demo codes stop working",
   all(access.resolve(c) is None for c in ("submitter123", "planner123", "admin123")))
# NARROWED (G2 label-only): the label is what a person reads — the tenant's name for the
# slot, else "<team word> <n>". This section's tenant defines no team rows, so "Team 3".
ok("F: an IPT code resolves to its IPT and cannot approve",
   access.resolve("three-secret") == {"role": "ipt", "ipt": "IPT3", "label": "Team 3"}
   and not access.can_approve(access.resolve("three-secret")), str(access.resolve("three-secret")))
ok("F: 'IPT 3', 'ipt3' and 'IPT-3' all canonicalise to IPT3",
   all(access.canonical_ipt(v) == "IPT3" for v in ("IPT 3", "ipt3", " IPT-3 ", "IPT3")))
ok("F: ...and rubbish canonicalises to None",
   access.canonical_ipt("IPT 7") is None and access.canonical_ipt("Earthworks") is None)

# --- 12 Oct 2026 (map review): /api/public/whoami and the two shapes of /api/meta ----------
# The view flag for the public map. Never a code, never a team id: this tenant names no slot,
# so the team code's label is "Team 3", the way the app prints it.
_as("three-secret")
_w = main.public_whoami()
ok("whoami: a team code is staff, with its team's NAME — 'Team 3' here (no slot is named), never 'IPT3'",
   _w == {"level": "staff", "team_label": "Team 3"} and "IPT" not in json.dumps(_w), str(_w))
_as("plan-secret")
ok("whoami: a planner is staff with no team", main.public_whoami() == {"level": "staff", "team_label": None})
access.set_current("no-such-code")        # nothing recognised and no cookie
ok("whoami: no code and no cookie → level null (the gate would have refused the call before this)",
   main.public_whoami() == {"level": None, "team_label": None})
_staff_cookie = types.SimpleNamespace(cookies={gate.COOKIE: gate.sign(gate.LEVEL_STAFF)})
_map_cookie = types.SimpleNamespace(cookies={gate.COOKIE: gate.sign(gate.LEVEL_MAP)})
ok("whoami: a staff COOKIE alone (the app's iframe) is staff with no team; the MAP cookie is level map",
   main.public_whoami(_staff_cookie) == {"level": "staff", "team_label": None}
   and main.public_whoami(_map_cookie) == {"level": "map", "team_label": None})
# D31: /api/meta — the public shape to a caller with no code and no staff cookie
_mp = main.meta()
ok("D31: 🔴 /api/meta with no code is the PUBLIC shape: scope public, NO routes, NO teams, NO sections",
   _mp["scope"] == "public" and _mp["routes"] == [] and _mp["ipts"] == [] and _mp["work_sections"] == [],
   str({k: _mp.get(k) for k in ("scope", "routes", "ipts", "work_sections")})[:200])
ok("D31: ...but everything the sign-in screen and the public map read is still there (this section seeds no taxonomy, so disciplines is a present, empty list)",
   _mp["units"] and _mp["vehicles"] and _mp["vehicle_labels"] and _mp["tenant"] and _mp["months"]
   and isinstance(_mp["factors"], dict) and isinstance(_mp["seasonal_restrictions"], list) and isinstance(_mp["disciplines"], list))
ok("D31: the MAP cookie is not staff — still the public shape",
   main.meta(_map_cookie)["scope"] == "public" and main.meta(_map_cookie)["routes"] == [])
_ms = main.meta(_staff_cookie)
ok("D31: ⭐ a staff COOKIE alone (the app's iframe sends no header) gets the staff shape, routes included",
   _ms["scope"] == "staff" and [r["route_id"] for r in _ms["routes"]] == ["R1", "R5"]
   and set(_ms) == set(_mp), str([r["route_id"] for r in _ms["routes"]]))
_as("plan-secret")
ok("D31: ...and so does a valid code (the staff app's own fetches)",
   main.meta()["scope"] == "staff" and len(main.meta()["routes"]) == 2)

# planner writes lines for two IPTs
_as("plan-secret")
try:
    main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="substructure", section_id="WS2",
        material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="p",
        unit="t", status="Pending", cells=[main.Cell(month_index=9, quantity=5.0)]))
    ok("F: ⭐ a planner with real codes MUST name an IPT", False)
except Exception as e:
    ok("F: ⭐ a planner with real codes MUST name an IPT — no silent IPT 1",
       getattr(e, "status_code", None) == 400 and "required" in str(e))
for _ipt, _sect in (("IPT 3", "WS2"), ("IPT6", "WS3")):
    main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="substructure", section_id=_sect,
        material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="p",
        unit="t", status="Pending", cells=[main.Cell(month_index=9, quantity=5.0)], ipt=_ipt))
_all = main.list_forecasts(route_id="R1")
ok("F: the planner sees every line on the route, NULL-ipt included", len(_all) == 3)
ok("F: the planner's chosen IPT is written canonically",
   sorted(r["ipt"] for r in _all if r["section_id"] == "WS2") == ["IPT3"])

# --- an IPT3 code cannot read an IPT6 line -------------------------------------------
_as("three-secret")
_mine = main.list_forecasts(route_id="R1")
ok("F: ⭐ an IPT3 code sees only its own line", [r["section_id"] for r in _mine] == ["WS2"])
ok("F: ⭐ ...not the IPT6 line, and not the NULL-ipt line either",
   not any(r["section_id"] in ("WS1", "WS3") for r in _mine))
ok("F: the summary is filtered the same way",
   {r["section_id"] for r in main.forecasts_summary()} == {"WS2"})
# writes
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="substructure", section_id="WS2",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="i3",
    unit="t", status="Pending", cells=[main.Cell(month_index=9, quantity=7.0)], ipt="IPT6"))
ok("F: ⭐ an IPT code's save is FORCED to its own IPT whatever the body said",
   [r["ipt"] for r in main.list_forecasts(route_id="R1")] == ["IPT3"]
   and main.list_forecasts(route_id="R1")[0]["quantity"] == 7.0)
try:
    main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="substructure", section_id="WS3",
        material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="i3",
        unit="t", status="Pending", cells=[main.Cell(month_index=9, quantity=99.0)]))
    ok("F: ⭐ an IPT3 code cannot overwrite an IPT6 line", False)
except Exception as e:
    ok("F: ⭐ an IPT3 code cannot overwrite an IPT6 line — and gets 404, not 403",
       getattr(e, "status_code", None) == 404)
_as("plan-secret")
ok("F: ...and the IPT6 line is untouched",
   [r["quantity"] for r in main.list_forecasts(route_id="R1") if r["section_id"] == "WS3"] == [5.0])
# approve
_as("three-secret")
try:
    main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline="substructure", section_id="WS2")
    ok("F: an IPT code cannot approve", False)
except Exception as e:
    ok("F: ⭐ an IPT code cannot approve — 403", getattr(e, "status_code", None) == 403)
_as("plan-secret")
main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline="substructure", section_id="WS2")
main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline="substructure", section_id="WS3")
# look-ahead
_as("six-secret")
_w6 = main.list_forecast_weeks(from_month=9, to_month=9)["weeks"]
ok("F: ⭐ the look-ahead is filtered per IPT", {w["section_id"] for w in _w6} == {"WS3"} and len(_w6) == 4)
try:
    main.set_forecast_week_actual(main.WeekActual(route_id="R1", month_index=9, discipline="substructure",
        section_id="WS2", week_index=1, actual_qty=1.0))
    ok("F: an IPT6 code cannot type an actual on an IPT3 week", False)
except Exception as e:
    ok("F: ⭐ an IPT6 code cannot type an actual on an IPT3 week — 404",
       getattr(e, "status_code", None) == 404)
main.set_forecast_week_actual(main.WeekActual(route_id="R1", month_index=9, discipline="substructure",
    section_id="WS3", week_index=1, actual_qty=1.0))
ok("F: ...but can on its own", weeks.get_week("R1", 9, "substructure", "WS3", 1)["actual_qty"] == 1.0)
# withdraw
_as("three-secret")
_wd = main.withdraw_route("R1", discipline="substructure", section_id="WS3")
ok("F: ⭐ an IPT3 withdraw of an IPT6 line deletes nothing", _wd["deleted"] == 0)
_as("plan-secret")
ok("F: ...and the line is still there",
   any(r["section_id"] == "WS3" for r in main.list_forecasts(route_id="R1")))
# no code at all
_as(None)
try:
    main.list_forecasts(); ok("F: no code -> 401", False)
except Exception as e:
    ok("F: ⭐ no code at all gets 401 on a staff endpoint", getattr(e, "status_code", None) == 401)
ok("F: ...while the public map feed stays open",
   isinstance(main.public_route_forecasts(1, 60, "vehicles"), dict)
   and isinstance(main.meta(), dict))
# stockpiles: any code, NOT filtered
_as("six-secret")
ok("F: stockpiles are readable by an IPT code and are not IPT-filtered (a stockpile has no IPT)",
   isinstance(main.list_stockpiles(from_month=9, to_month=9)["stockpiles"], list))
# tidy: back to demo for the rest of the file
for _v in ("IPT3_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
_as("planner123")
ok("F: the ipt column is in _TENANT_DDL as well as ALTERed", "ipt" in db._ddl_columns(db._TENANT_DDL["forecasts"]))


# =========================================================================== #
#  §8 / §9 (2026-09-02) — the two public endpoints behind the map's cards/warnings #
# =========================================================================== #
reset_db()
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", ("L1", "Pit", 58.5, 24.0, "Quarry"))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", ("L2", "Stockpile", 58.6, 24.4, "Stockpile"))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)", ("R1", "L1", "L2"))
_as("planner123")
# three lines in month 9: tonnes on a known vehicle, m3 on a known vehicle, and a
# vehicle factors.json has never heard of
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="earthworks", section_id="WS1",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="p",
    unit="t", status="Approved", cells=[main.Cell(month_index=9, quantity=200.0)]))
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="substructure", section_id="WS2",
    material_type="Small aggregate", vehicle_type="Artic Tipper (44t)", submitted_by="p",
    unit="m3", status="Approved", cells=[main.Cell(month_index=9, quantity=100.0)]))
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="structures", section_id="WS3",
    material_type="Precast / concrete", vehicle_type="Unicorn lorry", submitted_by="p",
    unit="t", status="Approved", cells=[main.Cell(month_index=9, quantity=36.0)]))
# and a Pending one that must NOT appear
main.save_matrix_row(main.MatrixRow(route_id="R1", discipline="utilities", section_id="WS4",
    material_type="Small aggregate", vehicle_type="Rigid 8-wheeler (32t)", submitted_by="p",
    unit="t", status="Pending", cells=[main.Cell(month_index=9, quantity=999.0)]))
_as(None)      # PUBLIC: no code
_k = main.public_month_kpis(month=9, unit="vehicles")
ok("§9: /api/public/month-kpis is open without a code", isinstance(_k, dict))
ok("§9: Approved lines only", sorted(l["section_id"] for l in _k["lines"]) == ["WS1", "WS2", "WS3"])
_by = {l["section_id"]: l for l in _k["lines"]}
ok("§9: working days come from factors.planning", _k["working_days"] == 22)
ok("§9: a tonnes line -> vehicle-loads = t / payload", abs(_by["WS1"]["vehicle_loads"] - 200 / 20) < 1e-9)
ok("§9: an m3 line converts through density THEN payload",
   abs(_by["WS2"]["qty_t"] - 160.0) < 1e-6 and abs(_by["WS2"]["vehicle_loads"] - 160 / 29) < 1e-3)
# NARROWED 11 Oct 2026 (EU vehicles removed): the first planning vehicle is Rigid 8-wheeler (32t),
# 20 t — the same figure as _default's 20 t, so the payload can no longer tell the two apart.
# The NAME can: the fallback is the named planning vehicle, and month-kpis says so.
ok("§9: ⭐ an unknown vehicle falls back to the first planning vehicle (Rigid 8-wheeler, 20 t), named, and says so",
   _by["WS3"]["payload_t"] == 20.0 and abs(_by["WS3"]["vehicle_loads"] - 36.0 / 20.0) < 1e-9
   and _by["WS3"]["payload_fallback"] == PLANNING[0] == "Rigid 8-wheeler (32t)" and _by["WS1"]["payload_fallback"] is None
   and _k["payload_fallback_vehicle"] == PLANNING[0])
ok("§9: qty_unit is in the requested map unit",
   _by["WS1"]["qty_unit"] == 10 and main.public_month_kpis(month=9, unit="t")["lines"][0]["qty_t"] == 200.0)
ok("§9: never actuals", not any("actual" in k for l in _k["lines"] for k in l))
# ⭐ 2026-09-03: every line carries trips_per_vehicle_day from the route's baked cycle —
# None here because nothing is baked in this harness, and the map must then say so
ok("§9: ⭐ every line carries trips_per_vehicle_day, None when the route is not baked",
   all("trips_per_vehicle_day" in l and l["trips_per_vehicle_day"] is None for l in _k["lines"]))
# 2026-10-06 (map redesign): CO2e per line, None when unbaked (no km, no carbon), and the
# programme-to-date list is empty while nothing is baked — never a zero dressed as a figure
ok("2026-10-06: every line carries co2_t, None when the route is not baked",
   all("co2_t" in l and l["co2_t"] is None for l in _k["lines"]))
ok("2026-10-06: co2_to_date is a list and counts the unbaked lines it excludes",
   _k["co2_to_date"] == [] and _k["co2_to_date_unbaked_lines"] >= 3)
# bake R1 for the tipper (geometry only, no HERE) and the figure appears
db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
           "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           ("default", "R1", "Rigid 8-wheeler (32t)", "loaded", 0, "[[24.0,58.5],[24.4,58.6]]", 30.0, 0.75))
db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
           "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           ("default", "R1", "Rigid 8-wheeler (32t)", "return", 0, "[[24.4,58.6],[24.0,58.5]]", 30.0, 0.65))
_k2 = {l["section_id"]: l for l in main.public_month_kpis(month=9, unit="vehicles")["lines"]}
# cycle = 0.75 + 0.65 + (12 + 8)/60 = 1.7333 h; 10 h shift // 1.7333 = 5 trips
ok("§9: ⭐ a baked route reports how many movements one vehicle can make per day (10 h ÷ cycle)",
   _k2["WS1"]["trips_per_vehicle_day"] == 5, str(_k2["WS1"]["trips_per_vehicle_day"]))
ok("§9: ...and the same route on an UNBAKED vehicle still reads None",
   _k2["WS2"]["trips_per_vehicle_day"] is None)
# the baked line now carries carbon: km x the vehicle's kg CO2e/km, the Dashboard's figure
_kp = main.public_month_kpis(month=9, unit="vehicles")
ok("2026-10-06: ⭐ a baked line carries co2_t > 0 and the unbaked one still None",
   _k2["WS1"]["co2_t"] is not None and _k2["WS1"]["co2_t"] > 0 and _k2["WS2"]["co2_t"] is None,
   str(_k2["WS1"]["co2_t"]))
ok("2026-10-06: co2_t matches costlines exactly, so the map and the Dashboard agree",
   abs(_k2["WS1"]["co2_t"] - [l for l in costlines.lines(acc={"role": "planner"}, from_month=9, to_month=9, status="Approved")["lines"]
                              if l["section_id"] == "WS1"][0]["co2_t"]) < 1e-9)
_td = {(c["route_id"], c["discipline"], c["section_id"]): c["co2_t"] for c in _kp["co2_to_date"]}
ok("2026-10-06: co2_to_date is keyed (route, discipline, section) and covers the baked line",
   ("R1", "earthworks", "WS1") in _td and _td[("R1", "earthworks", "WS1")] >= _k2["WS1"]["co2_t"] - 1e-9)
ok("2026-10-06: an unbaked line never enters co2_to_date",
   ("R1", "substructure", "WS2") not in _td and ("R1", "structures", "WS3") not in _td)
# 12 Oct 2026 (B2): forecast-matrix carries the SAME carbon per line per month, so the map's timeline
# needs one call for a carbon paint and its KPI prefetch, and the drawer reads the server's figure
_pm = main.public_forecast_matrix(from_=9, to=9, unit="t")
_pmb = {r["section_id"]: r for r in _pm["routes"] if r["route_id"] == "R1"}
ok("⭐ B2: every forecast-matrix line carries co2_t, a {month: t} map keyed exactly like monthly",
   all("co2_t" in r and set(r["co2_t"]) == set(r["monthly"]) for r in _pm["routes"]) and set(_pmb["WS1"]["co2_t"]) == {"9"},
   str({k: r.get("co2_t") for k, r in _pmb.items()}))
ok("⭐ B2: the baked line's co2_t equals month-kpis' (one costlines figure) and the unbaked lines read None",
   abs(_pmb["WS1"]["co2_t"]["9"] - _k2["WS1"]["co2_t"]) < 1e-9 and _pmb["WS2"]["co2_t"]["9"] is None
   and _pmb["WS3"]["co2_t"]["9"] is None)
ok("B2: the response shape is otherwise identical — the keys the detail table and the drawer read, plus co2_t, and no co2_error",
   # NARROWED 14 Oct 2026 (civils materials): plus vehicle_name, the NAME the drawer prints (vehicle_type stays the key)
   set(_pmb["WS1"]) == {"route_id", "discipline", "section_id", "material_type", "material_description", "vehicle_type",
                        "vehicle_name", "monthly", "total", "co2_t"}
   # NARROWED 12 Oct 2026 (the review and fix pass): plus the Carbon page's stamp, which the route drawer prints
   and set(_pm) == {"unit", "from", "to", "working_days", "routes", "carbon_stamp"}
   and _pm["carbon_stamp"] == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures", str(sorted(_pmb["WS1"])))
ok("B2: month-kpis carries no co2_error on the happy path", "co2_error" not in _kp)
# the failure path: the costlines read raises → both feeds answer, every co2_t None, and SAY why.
# Until today month-kpis caught the error and blanked every carbon figure silently (a null factor
# saved on Config was one trigger); forecast-matrix had no carbon at all.
_real_lines = costlines.lines


def _boom(*a, **k):
    raise RuntimeError("fixture: the costlines read failed")


costlines.lines = _boom
try:
    _ke = main.public_month_kpis(month=9, unit="vehicles")
    _pme = main.public_forecast_matrix(from_=9, to=9, unit="t")
except Exception as e:                       # pragma: no cover — the assertion below reports it
    _ke, _pme = {"raised": repr(e)}, {"raised": repr(e)}
finally:
    costlines.lines = _real_lines
# NARROWED 12 Oct 2026 (the review and fix pass): co2_error is a fixed sentence naming the exception's class only —
# both feeds are /api/public/ (anyone with the map password), and an exception's text can carry SQL or internal keys;
# the message is printed to the server log instead
ok("⭐ B2: when the costlines read fails month-kpis never raises — co2_error names the reason and every co2_t is None",
   _ke.get("co2_error") == "The carbon figures could not be read (RuntimeError)." and "fixture" not in _ke.get("co2_error", "")
   and _ke.get("lines") and all(l["co2_t"] is None for l in _ke["lines"]) and _ke.get("co2_to_date") == []
   and _ke.get("co2_to_date_unbaked_lines") == 0, str(_ke)[:200])
ok("B2: ...the rest of the month-kpis answer is intact (the volumes are not carbon's hostage)",
   len(_ke.get("lines") or []) == len(_kp["lines"]) and _ke["lines"][0]["vehicle_loads"] == _kp["lines"][0]["vehicle_loads"])
ok("⭐ B2: forecast-matrix the same — answers, co2_error, every month's co2_t None, volumes intact",
   _pme.get("co2_error") == "The carbon figures could not be read (RuntimeError)."
   and all(v is None for r in _pme.get("routes") or [] for v in r["co2_t"].values())
   and [r["monthly"] for r in _pme["routes"]] == [r["monthly"] for r in _pm["routes"]], str(_pme)[:200])
ok("B2: the costlines read is restored and the happy path has no co2_error again",
   costlines.lines is _real_lines and "co2_error" not in main.public_forecast_matrix(from_=9, to=9, unit="t"))
_main_src_b2 = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("B2: both public feeds read ONE helper for carbon (_approved_co2) and main.py has no bare `except Exception:` left around the costlines read",
   # NARROWED 19 Oct 2026: a third reader, approved_lines_by_month() (the council figures for every month in one read),
   # goes through the same helper
   _main_src_b2.count("= _approved_co2(factors") == 3 and _main_src_b2.count("def _approved_co2(") == 1
   and "table, co2_error = _approved_co2(factors, 1, MONTH_COUNT)" in _main_src_b2
   and "co2_by_key, to_date = {}, {}" not in _main_src_b2)
ok("§9: ...matching route_analysis exactly, so the dashboard, the form and the map agree",
   [r for r in network.route_analysis("R1", profiles=["Rigid 8-wheeler (32t)"])["rows"]
    if r["alt_index"] == 0][0]["trips_per_day"] == 5)
ok("§9: an empty month returns no lines rather than zeros", main.public_month_kpis(month=10, unit="t")["lines"] == [])
# stockpile timeline
_as("planner123")
stockpiles.set_capacity("L2", capacity_qty=100.0, capacity_unit="t", opening_qty=0.0)
# the lines above were written Approved directly, so nothing materialised their weeks
weeks.materialise_line("R1", "earthworks", "WS1")
weeks.set_actual("R1", 9, "earthworks", "WS1", 1, actual_qty=150.0, by="f")
# NARROWED 27 Oct 2026 (stockpile forecast, D9 a + i): a pile over capacity is shown to STAFF only; the public reads the
# balance capped at the capacity and `full`. The balance runs forward (the plan stands in for weeks 2-4, D2).
_st_staff = main.public_stockpile_timeline(9, 10)
_ps = [s for s in _st_staff["stockpiles"] if s["location_id"] == "L2"][0]
_as(None)
_st = main.public_stockpile_timeline(9, 10)
ok("§8: /api/public/stockpile-timeline is open without a code", isinstance(_st, dict))
_p = [s for s in _st["stockpiles"] if s["location_id"] == "L2"][0]
ok("§8: ⭐ the stockpile is over at the end of month 9 (read by staff; 150 t recorded + the plan after it)",
   _ps["months"]["9"]["over"] is True and _ps["months"]["9"]["balance_end"] >= 150.0, str(_ps["months"]["9"]))
ok("§8: ...and still over in month 10 (staff)", _ps["months"]["10"]["over"] is True)
ok("§8: ...the PUBLIC reads it 'full', capped at the capacity, never over",
   _p["months"]["9"]["over"] is False and _p["months"]["9"]["full"] is True and _p["months"]["9"]["balance_end"] == 100.0,
   str(_p["months"]["9"]))
ok("§8: only stockpiles WITH a capacity appear — nothing can be 'over' an unknown limit",
   (stockpiles.set_capacity("L2", capacity_qty=None, opening_qty=0.0),
    main.public_stockpile_timeline(9, 10)["stockpiles"] == [])[1])
_as("planner123")


# =========================================================================== #
#  2.5b — route editing in place                                               #
# =========================================================================== #
reset_db()
_as("planner123")
for lid, nm, sup, rec in (("L1", "Pit A", '["Small aggregate"]', "[]"),
                          ("L2", "Pit B", '["Small aggregate","Earthworks / soil"]', "[]"),
                          ("L3", "Site X", "[]", '["Small aggregate"]'),
                          ("L4", "Site Y", "[]", '["Earthworks / soil"]')):
    db.execute("INSERT INTO locations (id, name, lat, lon, supplies, receives) VALUES (?, ?, ?, ?, ?, ?)",
               (lid, nm, 58.5, 24.0, sup, rec))
db.execute("INSERT INTO routes (id, origin_id, dest_id, ipt, origin_gate_id, dest_gate_id) "
           "VALUES (?, ?, ?, ?, ?, ?)", ("R1", "L1", "L3", "IPT 5", "G-old-origin", "G-dest"))
db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
           "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           ("default", "R1", "Rigid 8-wheeler (32t)", "loaded", 0, "[[24,58.5],[24.4,58.6]]", 30.0, 0.7))
seed_line(route_id="R1", disc="earthworks", sect="WS1", months=(9, 10), qty=10.0)
main.set_route_status("R1", main.StatusUpdate(status="Approved"), discipline="earthworks", section_id="WS1")

imp = network.route_edit_impact("R1")
ok("2.5b: the impact report names what an edit would touch",
   imp["forecast_lines"] == 1 and imp["forecast_rows"] == 2 and imp["week_rows"] == 9   # Sep 4 + Oct 5
   and imp["baked_profiles"] == ["Rigid 8-wheeler (32t)"])

# material / IPT only: nothing routed changes
r = network.update_route("R1", ipt="IPT 3", given={"ipt"})
ok("2.5b: changing IPT alone clears nothing", r["affected_routes"] == [] and r["gates_cleared"] == []
   and network.profiles_for_route("R1") == ["Rigid 8-wheeler (32t)"])
ok("2.5b: ...and is written", db.query("SELECT ipt FROM routes WHERE tenant_id = ? AND id = ?",
   (db.current_tenant(), "R1"))[0]["ipt"] == "IPT 3")
# supply/receive guard, same as create
r = network.update_route("R1", material_category="Earthworks / soil", given={"material_category"})
ok("2.5b: the supply/receive guard applies to an edit", "does not supply" in (r.get("error") or ""))

# move the origin
r = network.update_route("R1", origin_id="L2", given={"origin_id"})
row = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "R1"))[0]
ok("2.5b: ⭐ moving the origin keeps the route id", row["id"] == "R1" and row["origin_id"] == "L2")
ok("2.5b: ⭐ ...clears the baked geometry and returns the profiles to re-bake",
   network.profiles_for_route("R1") == [] and r["affected_routes"] == [{"id": "R1", "profiles": ["Rigid 8-wheeler (32t)"]}])
ok("2.5b: ⭐ ...clears the ORIGIN gate (it belonged to the old location) and keeps the destination's",
   row["origin_gate_id"] is None and row["dest_gate_id"] == "G-dest" and r["gates_cleared"] == ["origin"])
ok("2.5b: ⭐ ...and leaves the forecast lines and their weeks alone",
   len(main.list_forecasts(route_id="R1")) == 2 and len(weeks.list_weeks(9, 10, route_id="R1")) == 9)
ok("2.5b: origin == destination is refused",
   "different" in (network.update_route("R1", dest_id="L2", given={"dest_id"}).get("error") or ""))
ok("2.5b: an unknown location is refused",
   "not found" in (network.update_route("R1", dest_id="L9", given={"dest_id"}).get("error") or ""))
ok("2.5b: an unknown route is refused", network.update_route("R9", ipt="IPT1", given={"ipt"}).get("error") == "route not found")
# the endpoint only writes what was sent
main.update_route("R1", main.RoutePatch(ipt="IPT 6"), token=os.environ["ADMIN_TOKEN"])
row = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), "R1"))[0]
ok("2.5b: PATCH writes only the fields sent", row["ipt"] == "IPT 6" and row["origin_id"] == "L2" and row["dest_id"] == "L3")


# =========================================================================== #
#  2026-09-09 — changing which VEHICLES one route is baked for                 #
#                                                                             #
#  A route has no vehicle field: its vehicles ARE the profiles that have a     #
#  route_geometry row. Adding one to a single route was already possible from  #
#  the API (bake_route takes an arbitrary profile) and impossible from the UI; #
#  removing one from a single route was impossible from BOTH, because          #
#  clear_geometry() had no route filter and was network-wide by construction.  #
#                                                                             #
#  ⚠️ The delete is the dangerous half, so every assertion below is about what #
#  SURVIVES it, not only about what goes.                                      #
# =========================================================================== #
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)", ("R2", "L2", "L3"))


def _geom(rid, prof, leg="loaded", tenant="default"):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, "
               "geometry, distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (tenant, rid, prof, leg, 0, "[[24,58.5],[24.4,58.6]]", 30.0, 0.7))


def _rows(rid, tenant="default"):
    return sorted((g["vehicle_profile"], g["leg"]) for g in db.query(
        "SELECT vehicle_profile, leg FROM route_geometry WHERE tenant_id = ? AND route_id = ?",
        (tenant, rid)))


P8, P6 = "Rigid 8-wheeler (32t)", "Rigid 6-wheeler (26t)"
for rid in ("R1", "R2"):
    for prof in (P8, P6):
        for leg in ("loaded", "return"):
            _geom(rid, prof, leg)
# a second tenant holding the same route id and the same profile: the whole point of the
# 4.5 key is that this row is invisible to every delete below. Written and read with the
# tenant named explicitly, so the assertion cannot pass merely because the contextvar
# happened to be pointing somewhere else.
_geom("R1", P8, "loaded", tenant="other")

# 12 Oct 2026 (map review §2.5 row 2): the typed daily cap rides on every public route line, both legs,
# None while nobody has typed one (this schema has no planning columns at all — .get, never [])
_pm = {(f["properties"]["route_id"], f["properties"]["leg"]): f["properties"]
       for f in network.public_map_data()["features"] if f["geometry"]["type"] == "LineString"}
ok("§2.5: every public route line (both legs, both routes) carries max_vehicles_per_day — None, nobody typed a cap",
   len(_pm) == 4 and all(p.get("max_vehicles_per_day", "missing") is None for p in _pm.values()), str(sorted(_pm)))
ok("§2.5: ...and so does every meta_routes row",
   all(r.get("max_vehicles_per_day", "missing") is None for r in network.meta_routes()))

ok("09-09: one route, one profile — BOTH legs go",
   (network.clear_geometry(profile=P8, route_id="R1") is True)
   and _rows("R1") == [(P6, "loaded"), (P6, "return")])
ok("09-09: ⭐ ...and the same profile on ANOTHER route is untouched",
   _rows("R2") == [(P6, "loaded"), (P6, "return"), (P8, "loaded"), (P8, "return")])
ok("09-09: 🔴 ...and another tenant's identical row survives it",
   _rows("R1", tenant="other") == [(P8, "loaded")])

network.clear_geometry(route_id="R1")
ok("09-09: a route_id on its own strips that route of every vehicle",
   _rows("R1") == [] and len(_rows("R2")) == 4)
ok("09-09: ...which is exactly 'not baked' again", network.profiles_for_route("R1") == [])

# The branch with no filter at all still means ALL geometry for this tenant, because
# "Clear all routes" depends on it. Asserted so that adding route_id cannot quietly turn
# the no-argument call into a no-op — which would break that button silently.
network.clear_geometry()
ok("09-09: 🔴 no filter still means everything, for THIS tenant only", _rows("R2") == [])
ok("09-09: 🔴 ...and still not the other tenant's", _rows("R1", tenant="other") == [(P8, "loaded")])

# the endpoint, not just the function: route_id has to survive the signature
_geom("R1", P8)
# 12 Oct 2026 (C11 closed): no token → 403; the right token with ADMIN_TOKEN UNSET → 403 too (it used to pass)
_e = None
try:
    main.clear_geometry(profile=P8, route_id="R1", token=None)
except Exception as e:
    _e = e
ok("C11: 🔴 clear-geometry without the admin token is refused (403) and clears nothing",
   getattr(_e, "status_code", None) == 403 and _rows("R1") == [(P8, "loaded")], repr(_e)[:120])
_saved_tok = os.environ.pop("ADMIN_TOKEN")
_e = None
try:
    main.clear_geometry(profile=P8, route_id="R1", token=_saved_tok)
except Exception as e:
    _e = e
os.environ["ADMIN_TOKEN"] = _saved_tok
ok("C11: 🔴 with ADMIN_TOKEN unset the admin surface is CLOSED, not open — even the right token is refused (403)",
   getattr(_e, "status_code", None) == 403 and _rows("R1") == [(P8, "loaded")], repr(_e)[:120])
main.clear_geometry(profile=P8, route_id="R1", token=os.environ["ADMIN_TOKEN"])
ok("09-09: the endpoint passes route_id through", _rows("R1") == [])

# --- what a drop COSTS, so the UI can say it before doing it ----------------- #
# forecasts.vehicle_type holds the same string as route_geometry.vehicle_profile — the
# Forecasts page indexes route analysis by it — so a line naming a vehicle with no
# geometry left reads "not baked" where its km and cycle time were.
imp = network.route_edit_impact("R1")
ok("09-09: the impact report breaks the forecast lines down BY VEHICLE",
   isinstance(imp.get("forecast_vehicles"), dict))
seeded = imp["forecast_vehicles"]
ok("09-09: ...counting rows and Approved rows separately",
   sum(v["lines"] for v in seeded.values()) == imp["forecast_rows"] == 2
   and sum(v["approved"] for v in seeded.values()) == 2)
db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, "
           "unit, vehicle_type, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
           ("F-novehicle", "R1", 11, "earthworks", "WS9", 5.0, "t", None, "Pending"))
imp = network.route_edit_impact("R1")
ok("09-09: ⭐ a line naming NO vehicle is keyed apart, not blamed on a profile",
   imp["forecast_vehicles"].get("", {}).get("lines") == 1
   and "" not in {k for k in imp["forecast_vehicles"] if k})
# and it is Pending, so it discriminates the two counters. Without this the approved
# column could be a copy of `lines` and every assertion above would still pass.
# ⚠️ .get(), not [""]. Written with a subscript first, and breaking the key on purpose
# then raised KeyError and took the REPORT down with it -- so the assertion above, which
# had correctly failed, printed nothing and read as uncaught. An assertion that can crash
# the run is worse than one that can fail: it hides every assertion after it.
ok("09-09: 🔴 ...and a Pending line counts as a line but NOT as Approved",
   imp["forecast_vehicles"].get("", {}).get("approved") == 0)


# =========================================================================== #
#  2.5b — the config table: factors.json becomes the seed                       #
# =========================================================================== #
import config as cfg  # noqa: E402
reset_db()
_as("planner123")
FILE = conversions.load_factors_file()
ok("cfg: with no row, load_factors() is the file", conversions.load_factors() == FILE
   and cfg.status(conversions)["source"] == "file")
ok("cfg: ⭐ first boot seeds the row from the file", cfg.seed_from_file(conversions)["seeded"] is True
   and cfg.status(conversions)["source"] == "database")
ok("cfg: ...idempotently", cfg.seed_from_file(conversions)["seeded"] is False)
ok("cfg: ...and the live document is unchanged by the seed", conversions.load_factors() == FILE
   and cfg.status(conversions)["differs_from_file"] is False)
# an edit through the table is what everything reads from now on
doc = json.loads(json.dumps(FILE))
doc["vehicles"]["Rigid 8-wheeler (32t)"]["payload_t"] = 21.5
doc["planning"]["working_days_per_month"] = 20
res = cfg.save(doc, by="tester", network=network)
ok("cfg: a valid edit saves", res["ok"] is True, str(res))
ok("cfg: ⭐ load_factors() now reads the row, not the file",
   conversions._payload(conversions.load_factors(), "Rigid 8-wheeler (32t)") == 21.5
   and conversions.load_factors()["planning"]["working_days_per_month"] == 20)
ok("cfg: ...and every consumer follows — the meta payload carries the new working days",
   main.meta()["factors"]["planning"]["working_days_per_month"] == 20)
ok("cfg: the status says who and that the file has drifted",
   cfg.status(conversions)["updated_by"] == "tester" and cfg.status(conversions)["differs_from_file"] is True)
# validation refuses what would silently break the numbers
bad = json.loads(json.dumps(FILE)); bad["vehicles"]["Artic Tipper (44t)"]["payload_t"] = -1
ok("cfg: ⭐ a non-positive payload is refused", not cfg.save(bad, network=network)["ok"])
bad = json.loads(json.dumps(FILE)); del bad["vehicles"]["Artic Tipper (44t)"]
ok("cfg: ⭐ deleting the default routing profile is refused",
   any("default routing profile" in p for p in cfg.save(bad, network=network)["problems"]))
# 12 Oct 2026 (B2): the blank kg CO2e/km cell — the Config page writes null for it — is refused at save,
# naming the vehicle; until today it saved, and the live document then made every carbon figure vanish
bad = json.loads(json.dumps(FILE)); bad["vehicles"]["Rigid 8-wheeler (32t)"]["emissions_kg_co2e_per_km"] = None
_res_null = cfg.save(bad, network=network)
ok("cfg: ⭐ B2: a BLANK (null) emissions factor is refused at save, naming the vehicle",
   _res_null["ok"] is False and any("vehicle 'Rigid 8-wheeler (32t)'" in p and "blank" in p for p in _res_null["problems"]),
   str(_res_null["problems"]))
ok("cfg: ...and the live document is untouched by the refused save",
   conversions.load_factors()["vehicles"]["Rigid 8-wheeler (32t)"]["emissions_kg_co2e_per_km"] == 0.99773)
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L1", "a", 58.5, 24.0))
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES (?, ?, ?, ?)", ("L2", "b", 58.6, 24.4))
db.execute("INSERT INTO routes (id, origin_id, dest_id) VALUES (?, ?, ?)", ("R1", "L1", "L2"))
db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, "
           "distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           ("default", "R1", "Rigid 6-wheeler (26t)", "loaded", 0, "[[24,58.5],[24.4,58.6]]", 30.0, 0.7))
bad = json.loads(json.dumps(FILE)); del bad["vehicles"]["Rigid 6-wheeler (26t)"]
ok("cfg: ⭐ deleting a vehicle the network is BAKED for is refused, by name",
   any("Rigid 6-wheeler (26t)' has baked route geometry" in p for p in cfg.save(bad, network=network)["problems"]))
bad = json.loads(json.dumps(FILE)); bad["material_categories"]["Small aggregate"]["vehicles"].append("Ghost lorry")
ok("cfg: a material naming an unknown vehicle is refused", not cfg.save(bad, network=network)["ok"])
bad = json.loads(json.dumps(FILE)); bad["planning"]["working_days_per_month"] = 0
ok("cfg: zero working days is refused", not cfg.save(bad, network=network)["ok"])
ok("cfg: ...and the live document is still the last GOOD one",
   conversions.load_factors()["planning"]["working_days_per_month"] == 20)
# reset to file
ok("cfg: ⭐ reset to file puts the file back", cfg.reset_to_file(conversions, by="tester")["ok"]
   and conversions.load_factors() == FILE and cfg.status(conversions)["differs_from_file"] is False)
# the endpoint refuses a bad doc with the problems
_as("admin123")
try:
    main.put_factors_config(main.FactorsIn(doc={"vehicles": {}}, updated_by="x"), token=os.environ["ADMIN_TOKEN"])
    ok("cfg: PUT refuses a bad document", False)
except Exception as e:
    ok("cfg: PUT refuses a bad document with 400", getattr(e, "status_code", None) == 400)
ok("cfg: GET returns doc, status and the file", set(main.get_factors_config()) == {"doc", "status", "file"})
_as("planner123")


# =========================================================================== #
#  The UPGRADE path — a database that predates this delivery                   #
# =========================================================================== #
# ⭐ The highest-risk part of this week's work, because it runs once against live
# Postgres and there is no second chance. The trap db.py documents: the SQLite tenant
# rebuild copies the INTERSECTION of the live table's columns with the DDL, so a
# column ALTERed on AFTER that rebuild survives and one added BEFORE it and missing
# from the DDL is silently dropped. The three capacity columns are in
# _TENANT_DDL["locations"] as well as ALTERed for exactly that reason — and this
# asserts it against a database built the way the last deploy left one.
remove_scratch_db(db, TMP)
# 1. a PRE-week-1 database, with data in it
db.init_db()
db.init_network_db()
db.init_taxonomy_db()
db.init_zones_db()
db.init_gates_db()
db.init_tenant()
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type, vendor, "
           "detail, gate_lat, gate_lon, default_section_id) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           ("default", "C01", "Vao quarry", 59.4, 24.9, "Quarry", "OU Killustik",
            "Limestone - rockfill", 59.41, 24.91, "WS1"))
ok("upgrade: the pre-week-1 database has no forecast_weeks",
   "forecast_weeks" not in tables())
# 2. deploy: the lifespan order, init_weeks_db BEFORE init_tenant
db.init_network_db()
db.init_gates_db()
db.init_weeks_db()
db.init_tenant()
_lc = cols("locations")
for c in ("capacity_qty", "capacity_unit", "opening_qty"):
    ok(f"upgrade: locations gained {c}", c in _lc)
# ⭐ and NOTHING that was already there was lost to the rebuild
for c in ("vendor", "detail", "gate_lat", "gate_lon", "default_section_id",
          "supplies", "receives", "materials", "material", "role"):
    ok(f"upgrade: ⭐ the pre-existing column {c} survived", c in _lc)
_row = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?",
                (db.current_tenant(), "C01"))
ok("upgrade: ⭐ the row survived", len(_row) == 1)
ok("upgrade: ⭐ ...with its salvaged vendor intact",
   _row and _row[0]["vendor"] == "OU Killustik")
ok("upgrade: ...its gate pair intact", _row and _row[0]["gate_lat"] == 59.41)
ok("upgrade: ...and a NULL capacity, which is 'not recorded', not zero",
   _row and _row[0]["capacity_qty"] is None)
ok("upgrade: both new tables exist",
   "forecast_weeks" in tables() and "stockpile_weeks" in tables())
# 3. ⭐ THE ACTUAL TRAP, and it needs a PRE-4.5 table to bite.
#
# The step above cannot expose it: that database had already been through the tenant
# migration, so _migrate_table_to_tenant() returns "already", no rebuild happens, and
# the ALTERed columns simply stay. The live Postgres is in that state too (4.5
# confirmed 2026-08-30), so it is safe today — but a fresh SQLite database, or a
# second tenant, goes through the rebuild, and there the rebuild copies only the
# INTERSECTION of the live columns with _TENANT_DDL. A column ALTERed on but missing
# from the DDL is dropped, silently, with its data.
#
# So: a `locations` table with NO tenant_id, carrying the three capacity columns and a
# row, put through init_tenant().
db.execute("DROP TABLE IF EXISTS locations_pre45")
db.execute("DROP TABLE locations")
db.execute("""
    CREATE TABLE locations (
        id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, loc_type TEXT, role TEXT,
        materials TEXT, supplies TEXT, receives TEXT, lat REAL NOT NULL,
        lon REAL NOT NULL, material TEXT, default_section_id TEXT, vendor TEXT,
        detail TEXT, gate_lat REAL, gate_lon REAL,
        capacity_qty REAL, capacity_unit TEXT, opening_qty REAL
    )
""")
db.execute("INSERT INTO locations (id, name, lat, lon, vendor, capacity_qty, "
           "capacity_unit, opening_qty) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           ("C02", "Legacy stockpile", 58.9, 24.5, "OU Killustik", 2500.0, "t", 180.0))
ok("upgrade: a pre-4.5 locations table has no tenant_id",
   "tenant_id" not in cols("locations"))

# ⭐ 3a. THE PARSER THAT DECIDES WHAT SURVIVES THAT REBUILD.
#
# db._ddl_columns() splits a DDL body on top-level commas and takes the first token of
# each piece. Several blocks carry `-- …` comments, and prose contains commas: one of
# them splits a fragment mid-sentence, so the piece that declares the NEXT column
# begins with an English word and that column never reaches `want`. The rebuild copies
# only `[c for c in want if c in have]`, so it is dropped with its data.
#
# ⚠️ FOUND 2026-09-01 AND IT WAS ALREADY LIVE: routes.origin_gate_id (Phase 5a) had
# been invisible to this parser since it shipped, while dest_gate_id survived because
# it happened to start its own fragment. Fixed by stripping `--` first. Asserted for
# EVERY table so a future comment cannot re-open it.
import re as _re  # noqa: E402
_ddl_problems = []
for _t, _ddl in sorted(db._TENANT_DDL.items()):
    _got = set(db._ddl_columns(_ddl))
    for _line in _ddl.splitlines():
        _l = _line.strip()
        if not _l or _l.startswith("--"):
            continue
        _tok = _l.split()[0]
        # a declaration line starts with a bare identifier; skip the statement and
        # the table-level constraints. Matched on the WHOLE token, so `created_at`
        # is not mistaken for CREATE and `primary_discipline` not for PRIMARY.
        if _tok.upper() in ("CREATE", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK",
                            "CONSTRAINT", ")"):
            continue
        if not _re.fullmatch(r"[a-z_][a-z0-9_]*", _tok):
            continue
        if _tok not in _got:
            _ddl_problems.append(f"{_t}.{_tok}")
ok("⭐ every column declared in every _TENANT_DDL block is seen by _ddl_columns()",
   not _ddl_problems, str(_ddl_problems))
# and the specific pair that was broken
ok("⭐ routes.origin_gate_id is visible to the tenant rebuild (was NOT, pre-fix)",
   "origin_gate_id" in db._ddl_columns(db._TENANT_DDL["routes"]))
ok("...as is dest_gate_id, which survived by luck",
   "dest_gate_id" in db._ddl_columns(db._TENANT_DDL["routes"]))
ok("⭐ and the parser returns no English words from the comments",
   not [c for c in db._ddl_columns(db._TENANT_DDL["locations"])
        if c in ("--", "which", "and", "or", "not", "default", "so")])
db.init_tenant()
_lc2 = cols("locations")
for c in ("capacity_qty", "capacity_unit", "opening_qty"):
    ok(f"upgrade: ⭐ {c} survives the pre-4.5 tenant REBUILD", c in _lc2)
_r2 = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?",
               (db.current_tenant(), "C02"))
ok("upgrade: ⭐ and so does the capacity DATA in it",
   len(_r2) == 1 and _r2[0]["capacity_qty"] == 2500.0
   and _r2[0]["capacity_unit"] == "t" and _r2[0]["opening_qty"] == 180.0,
   str(_r2))

# 4. a second boot must change nothing
db.init_weeks_db()
_again = db.init_tenant()
ok("upgrade: ⭐ a second boot migrates nothing",
   not [t for t, r in _again.items() if r == "migrated"],
   str([t for t, r in _again.items() if r == "migrated"]))
ok("upgrade: ...and no table reports FAILED",
   not [t for t, r in _again.items() if r == "failed"])

# the week layer must not have leaked into the monthly key
ok("⭐ `forecasts` still has no week_index", "week_index" not in cols("forecasts"))
ok("⭐ ...and the public feed is still monthly",
   "week" not in main.public_route_forecasts.__doc__.lower())


# =========================================================================== #
print()
print(f"{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
