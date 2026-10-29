"""
Civils materials, 14 Oct 2026 (backlog item 3, D13) — branch claude/civils-materials.

WHAT IS ASSERTED
----------------
  1. The seed (backend/factors.json): four categories ADDED — Ready-mixed concrete (m³, 2.4 t/m³,
     mixers only), Precast units, Structural steel / rebar, Asphalt — each density with its source
     (_density_basis), Asphalt's an ASSUMPTION; the six old category keys all still there (never
     renamed); "Precast / concrete" lists no mixer any more (the user, 14 Oct); every new category
     names a carbon class the carbon block carries.
  2. The two mixers: keys unchanged ("Truck mixer …", stored on lines, routes and geometry), labels
     "Concrete mixer …", payload and turnaround labelled ASSUMPTION.
  3. DISCIPLINE_MATERIALS: every old pair kept, every new category linked, only real categories;
     seed_taxonomy() does not link a category the tenant's own Config lacks (the live demo's row).
  4. The NAME a person reads, never the key: conversions.vehicle_label / vehicle_labels (seed label,
     a config row whose label equals the key, a blank label, a typed label, an unknown key);
     derived.vehicle_short; Config's problem sentences; limits' breach words read on display.
  5. network._known_cats: a category added by a Config save is known at once (fails without the
     invalidation: the mutation check in the session note).
  6. The regenerated demo package: the batching plant, two mixer routes, three lines in m³ on the
     mixers, actuals typed; imported, every server output a person reads — the Look-ahead page JSON,
     its XLSX and PDF, the Day sheet, the clash words, costlines, the public month-kpis and
     forecast-matrix NAMES, the monthly bulletin, the CLP pack (PDF + XLSX), the carbon page's
     factor list and its PDF — says "Concrete mixer" and never "truck".
  7. Source level: the staff app, the public map and the guides print no vehicle key: the fixed
     places go through vehLabel / vehName, the word rule is in both helpers, and the literal
     "Truck mixer" appears in no screen's source.

WHAT THIS DOES NOT PROVE
------------------------
  * Nothing is baked (HERE is never called): every mixer line reads UNBAKED here, so km, carbon
    and the bulletin's map are exercised on the unbaked branch. The live bake is the user's step.
  * Nothing renders in a browser here; the session note records the browser check.
  * Mapbox is never called (portable.offline).

Run:  python backend/tests/test_civils.py
"""
import io
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

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class _App:
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = patch = _deco

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = {}


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query
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

TMP = tempfile.mkdtemp(prefix="wayscope_civils_")
from portable import remove_scratch_db, pdf_text, offline   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "civils-admin-token"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import derived  # noqa: E402
import limits  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import lookahead  # noqa: E402
import export  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
access.set_current("planner123")
offline(export)

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


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    config.invalidate(); costing.invalidate()


def boot():
    reset_db()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate(); costing.invalidate()


TRUCK = re.compile(r"\btrucks?\b", re.I)
M8, M6 = "Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)"
N8, N6 = "Concrete mixer 8 m³ (32t)", "Concrete mixer 6 m³ (26t)"
NEW = ("Ready-mixed concrete", "Precast units", "Structural steel / rebar", "Asphalt")
OLD = ("Earthworks / soil", "Small aggregate", "Large aggregate / ballast", "Precast / concrete",
       "Steel / rail", "General / imported", "_default")

# --------------------------------------------------------------------------- #
#  1-2. The seed                                                               #
# --------------------------------------------------------------------------- #
F = conversions.load_factors_file()
C = F["material_categories"]
ok("1: the six old category keys and _default are all still in the seed (never renamed)", all(k in C for k in OLD),
   str([k for k in OLD if k not in C]))
ok("1: the four new categories are in the seed", all(k in C for k in NEW), str([k for k in NEW if k not in C]))
rmc = C.get("Ready-mixed concrete") or {}
ok("1: Ready-mixed concrete is m³, 2.4 t/m³, convertible, the two mixers ONLY",
   rmc.get("default_unit") == "m3" and rmc.get("density_t_per_m3") == 2.4 and rmc.get("volume_convertible") is True
   and rmc.get("vehicles") == [M8, M6], str(rmc)[:200])
ok("1: Precast units: tonnes, 2.5, not converted, flatbed and 8-wheeler",
   (C.get("Precast units") or {}).get("default_unit") == "t" and (C.get("Precast units") or {}).get("density_t_per_m3") == 2.5
   and (C.get("Precast units") or {}).get("volume_convertible") is False
   and (C.get("Precast units") or {}).get("vehicles") == ["Artic Flatbed (44t)", "Rigid 8-wheeler (32t)"])
ok("1: Structural steel / rebar: tonnes, 7.85, not converted, artic flatbed",
   (C.get("Structural steel / rebar") or {}).get("density_t_per_m3") == 7.85
   and (C.get("Structural steel / rebar") or {}).get("default_unit") == "t"
   and (C.get("Structural steel / rebar") or {}).get("vehicles") == ["Artic Flatbed (44t)"])
ok("1: Asphalt: tonnes, not converted, tippers, carbon class asphalt",
   (C.get("Asphalt") or {}).get("default_unit") == "t" and (C.get("Asphalt") or {}).get("volume_convertible") is False
   and (C.get("Asphalt") or {}).get("vehicles") == ["Rigid 8-wheeler (32t)", "Artic Tipper (44t)"]
   and (C.get("Asphalt") or {}).get("carbon_material") == "asphalt")
ok("1: every new density carries its source; the Eurocode ones name BS EN 1991-1-1",
   all(len((C.get(k) or {}).get("_density_basis") or "") > 80 for k in NEW)
   and all("BS EN 1991-1-1" in C[k]["_density_basis"] for k in ("Ready-mixed concrete", "Precast units", "Structural steel / rebar")))
ok("1: Asphalt's density has no single published source and says ASSUMPTION",
   (C.get("Asphalt") or {}).get("_density_basis", "").startswith("ASSUMPTION"))
_cm = set((F.get("carbon") or {}).get("materials") or {})
ok("1: every new category names a carbon class the carbon block carries", all(C[k].get("carbon_material") in _cm for k in NEW))
ok("1: 'Precast / concrete' (key unchanged) lists no mixer any more, and says why",
   not any("mixer" in v.lower() for v in C["Precast / concrete"]["vehicles"])
   and C["Precast / concrete"]["vehicles"] == ["Artic Flatbed (44t)", "Rigid 8-wheeler (32t)"]
   and "Ready-mixed concrete" in C["Precast / concrete"].get("_vehicles_note", ""))
ok("1: the seed validates", config.validate(F) == [], str(config.validate(F))[:300])

V = F["vehicles"]
ok("2: the mixer KEYS are unchanged (stored on lines, routes, geometry)", M8 in V and M6 in V)
ok("2: their names are 'Concrete mixer …'", V[M8]["labels"]["en"] == N8 and V[M6]["labels"]["en"] == N6)
ok("2: payload and turnaround with no public source say ASSUMPTION",
   all("ASSUMPTION" in V[k].get("_payload_basis", "") and V[k].get("_turnaround_note", "").startswith("ASSUMPTION")
       for k in (M8, M6)))
ok("2: no name the seed gives a person says 'truck' (every vehicle label, every category name)",
   not any(TRUCK.search((v.get("labels") or {}).get("en") or "") for k, v in V.items() if not k.startswith("_"))
   and not any(TRUCK.search(k) for k in C))

# --------------------------------------------------------------------------- #
#  3. Disciplines                                                              #
# --------------------------------------------------------------------------- #
DM = taxonomy.DISCIPLINE_MATERIALS
_OLD_DM = {
    "earthworks": ["Earthworks / soil", "Small aggregate"],
    "substructure": ["Small aggregate", "Large aggregate / ballast", "Precast / concrete", "General / imported"],
    "utilities": ["General / imported", "Precast / concrete"],
    "structures": ["Precast / concrete", "Steel / rail", "General / imported"],
    "superstructure": ["Large aggregate / ballast", "Steel / rail", "Precast / concrete"],
    "stations": ["Precast / concrete", "Steel / rail", "General / imported"],
    "temporary_works": ["Small aggregate", "Large aggregate / ballast", "General / imported"],
}
# NARROWED 29 Oct 2026 (3b, the steel split; the user said yes): the two RETIRED steel categories are no longer seeded
# (Rail / Reinforcement / Structural steel take their place); every other pair of before 14 Oct is kept, in order, at the front
_RET = ("Steel / rail", "Structural steel / rebar", "Rail", "Reinforcement", "Structural steel")   # every steel name, old and new
ok("3: every discipline ↔ material pair of before 14 Oct is kept, in order, at the front (bar the two retired steel ones)",
   all([x for x in DM.get(d, []) if x not in _RET][:len([x for x in c if x not in _RET])] == [x for x in c if x not in _RET]
       for d, c in _OLD_DM.items()))
ok("3: every new category is linked to at least one discipline (bar the retired Structural steel / rebar)",
   all(any(k in c for c in DM.values()) for k in NEW if k not in _RET))
ok("3: ready-mixed concrete reaches structures, substructure, utilities, stations; asphalt the pavement",
   all("Ready-mixed concrete" in DM[d] for d in ("structures", "substructure", "utilities", "stations"))
   and "Asphalt" in DM["superstructure"])
ok("3: every linked category is a category of the seed", all(c in C for cs in DM.values() for c in cs))

boot()
_have = {(r["discipline_id"], r["material_category"]) for r in db.query(
    "SELECT discipline_id, material_category FROM discipline_materials WHERE tenant_id = ?", (db.current_tenant(),))}
ok("3: a fresh tenant (Config = the seed) gets the new links", ("structures", "Ready-mixed concrete") in _have
   and ("superstructure", "Asphalt") in _have)
# a tenant whose stored Config predates the categories (the live demo's row): no link to a category it lacks
reset_db()
_old = conversions.load_factors_file()
for k in NEW:
    _old["material_categories"].pop(k)
ok("3: (setup) the pre-14-Oct document validates", config.save(_old, by="test")["ok"])
config.invalidate()
taxonomy.seed_taxonomy()
_have = {(r["discipline_id"], r["material_category"]) for r in db.query(
    "SELECT discipline_id, material_category FROM discipline_materials WHERE tenant_id = ?", (db.current_tenant(),))}
ok("3: a tenant whose Config lacks the new categories is NOT linked to them on boot",
   not any(c in NEW for _, c in _have) and ("structures", "Precast / concrete") in _have, str(sorted(_have))[:300])
ok("3: ...and seeding stays idempotent", not any(taxonomy.seed_taxonomy().values()))

# --------------------------------------------------------------------------- #
#  4. The name, never the key                                                  #
# --------------------------------------------------------------------------- #
_live_like = {"vehicles": {M8: {"labels": {"en": M8}}, M6: {"labels": {"en": ""}}, "Artic Tipper (44t)": {"labels": {"en": "Artic Tipper (44t)"}},
                           "Ready-mix wagon": {"labels": {"en": "Ready-mix wagon"}}, "Truck mixer 9": {"labels": {"en": "Our 9 m³ mixer"}}}}
ok("4: the seed's mixer reads 'Concrete mixer …'", conversions.vehicle_label(F, M8) == N8 and conversions.vehicle_label(F, M6) == N6)
ok("4: a config row whose label still EQUALS the key (the live demo's) reads 'Concrete mixer …'",
   conversions.vehicle_label(_live_like, M8) == N8)
ok("4: a BLANK label falls to the key through the word rule", conversions.vehicle_label(_live_like, M6) == N6)
ok("4: a label the tenant typed wins untouched", conversions.vehicle_label(_live_like, "Truck mixer 9") == "Our 9 m³ mixer")
ok("4: a key the document does not carry still passes the rule", conversions.vehicle_label({}, "truck mixer 7 m³") == "Concrete mixer 7 m³")
ok("4: other names are untouched", conversions.vehicle_label(_live_like, "Artic Tipper (44t)") == "Artic Tipper (44t)"
   and conversions.vehicle_word_rule("Artic Tipper (44t)") == "Artic Tipper (44t)" and conversions.vehicle_label(F, None) == "")
_vl = conversions.vehicle_labels(_live_like)["labels"]
ok("4: /api/meta's vehicle_labels carry the name for every key (the pickers)",
   _vl[M8]["en"] == N8 and _vl[M6]["en"] == N6 and _vl["Truck mixer 9"]["en"] == "Our 9 m³ mixer")
ok("4: no label /api/meta sends for the seed says 'truck'",
   not any(TRUCK.search(x["en"]) for x in conversions.vehicle_labels(F)["labels"].values()))
ok("4: the chip's short name comes from the NAME (derived.vehicle_short)",
   derived.vehicle_short(M8, F) == N8 and derived.vehicle_short("Artic Tipper (44t)", F) == "Tipper (44t)"
   and derived.vehicle_short(M8, _live_like) == N8)
_bad = json.loads(json.dumps(F))
_bad["vehicles"][M8]["payload_t"] = -1
_bad["material_categories"]["Ready-mixed concrete"]["vehicles"].append("Truck mixer 12 m³")
_probs = config.validate(_bad)
ok("4: Config's problem sentences name the vehicle, not the key",
   any(N8 in p for p in _probs) and any("Concrete mixer 12 m³" in p for p in _probs)
   and not any(TRUCK.search(p) for p in _probs), str(_probs)[:300])
_hits = [{"vehicle_profile": M8, "vehicle_label": M8, "leg": "loaded", "vehicle_value": 3.9, "unit": "m",
          "headline": "Height limit 3.6 m", "source": "osm", "verdict": "exceeds"}]
config.invalidate()
ok("4: a stored limit check that saved the OLD name is shown with the name read now",
   limits.breach_text(_hits, M8).startswith(N8) and not TRUCK.search(limits.breach_text(_hits, M8)),
   limits.breach_text(_hits, M8))

# --------------------------------------------------------------------------- #
#  5. The category cache                                                       #
# --------------------------------------------------------------------------- #
boot()
ok("5: (setup) an unknown category is unknown", network._to_cat("Geotextile rolls") is None)
_doc = conversions.load_factors_file()
_doc["material_categories"]["Geotextile rolls"] = {"density_t_per_m3": 0.9, "default_unit": "t", "volume_convertible": False,
                                                  "vehicles": ["Artic Flatbed (44t)"]}
ok("5: (setup) the Config save is accepted", config.save(_doc, by="test")["ok"])
ok("5: a category added by a Config save is known to the network AT ONCE (no restart)",
   network._to_cat("Geotextile rolls") == "Geotextile rolls")
_doc["material_categories"].pop("Geotextile rolls")
config.save(_doc, by="test")
ok("5: ...and one removed is forgotten at once", network._to_cat("Geotextile rolls") is None)
_src = read("backend/config.py")
ok("5: config.invalidate() clears the network's cache (source)", "net.invalidate_categories()" in _src.split("def invalidate():")[1].split("\ndef ")[0])

# --------------------------------------------------------------------------- #
#  6. The regenerated demo package                                             #
# --------------------------------------------------------------------------- #
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
T = DEMO["tables"]
_bp = [l for l in T["locations"] if l["loc_type"] == "Batching plant"]
# RE-PINNED 17 Oct 2026 (demo redesign R2, §3a, D100): TWO batching plants — the Melton plant and Welland Ready-Mix for the
# south. The on-site asphalt plant has its own type ("Asphalt plant"), so it is not counted here.
ok("6: the demo has TWO batching plants (Melton and Welland Ready-Mix), each fictional, supplying only ready-mixed concrete",
   sorted(l["name"] for l in _bp) == ["Welland Ready-Mix (fictional)", "Wolds Link Batching Plant (fictional)"]
   and all(json.loads(l["supplies"]) == ["Ready-mixed concrete"] for l in _bp)
   and [l["loc_type"] for l in T["locations"] if "Asphalt Plant" in l["name"]] == ["Asphalt plant"])
_bp_id = {l["name"]: l["id"] for l in _bp}
_pr = {n: sorted(r["id"] for r in T["routes"] if r["origin_id"] == i) for n, i in _bp_id.items()}
# RE-PINNED 28 Oct 2026 (simulation v2): + R049, the Melton plant to the Tilton Viaduct site
ok("6: the mixer routes leave each plant by id (Melton R021, R022, R033, R034, R049; Welland R035, R036), each with both gates named",
   _pr == {"Wolds Link Batching Plant (fictional)": ["R021", "R022", "R033", "R034", "R049"], "Welland Ready-Mix (fictional)": ["R035", "R036"]}
   and all(r["material_category"] == "Ready-mixed concrete" and r["origin_gate_id"] and r["dest_gate_id"]
           for r in T["routes"] if r["origin_id"] in _bp_id.values()))
_pl = [f for f in T["forecasts"] if f["material_type"] == "Ready-mixed concrete"]
_lines = {(f["route_id"], f["discipline"], f["section_id"], f["vehicle_type"]) for f in _pl}
# RE-PINNED 17 Oct 2026 (R2, §3a): the mixer line keys read once from the regenerated package — 16 lines (structures on the
# 8 m³ mixer, kerbs and surrounds on the 6 m³), 210 line-months
# RE-PINNED 28 Oct 2026 (simulation v2): the viaduct's piles and deck concrete are the site's own line now (R049), no longer
# summed with the A47 junction's months at the compound: 17 lines, 223 line-months
ok("6: seventeen mixer lines (12 structures, 5 substructure), 223 line-months in m³, approved, both mixers used",
   len(_lines) == 17 and len(_pl) == 223 and all(f["unit"] == "m3" and f["status"] == "Approved" for f in _pl)
   and {l[3] for l in _lines} == {M8, M6} and sorted(l[1] for l in _lines).count("structures") == 12
   and all((l[1] == "structures") == (l[3] == M8) for l in _lines))
ok("6: every other line is on a lorry, never a mixer: 721 others (the programme's 942 approved less 223, + Pending and Rejected; RE-PINNED 28 Oct)",
   len([f for f in T["forecasts"] if f["material_type"] != "Ready-mixed concrete"]) == 721
   and not any("mixer" in (f["vehicle_type"] or "").lower() for f in T["forecasts"] if f["material_type"] != "Ready-mixed concrete"))
ok("6: the package's own factors carry the new categories and the mixer names",
   all(k in json.loads(next(r["value"] for r in T["config"] if r["key"] == "factors"))["material_categories"] for k in NEW)
   and json.loads(next(r["value"] for r in T["config"] if r["key"] == "factors"))["vehicles"][M8]["labels"]["en"] == N8)
ok("6: the package's readme tells the importer to bake the mixers too", "concrete mixers" in DEMO.get("_readme", ""))

boot()
# NARROWED 17 Oct 2026 (demo redesign R2, D102, §3a): the shipped package now carries the nine council areas; the bulletin
# check below is about a tenant WITHOUT areas (the sources' empty column), so this copy is imported with no area rows
DEMO_NO_AREAS = dict(DEMO, tables=dict(DEMO["tables"], areas=[], route_area_km=[]))
res = tenant_package.import_tenant(DEMO_NO_AREAS, replace=True)
ok("6: the demo imports into an empty tenant", res.get("ok") is True, str(res)[:200])
config.invalidate(); costing.invalidate()
FAC = conversions.load_factors()
_one = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND vehicle_type = ? ORDER BY id LIMIT 1", (db.current_tenant(), M8))[0]
ok("6: a mixer line in m³ converts at 2.4 t/m³", abs(conversions.to_tonnes(_one["quantity"], "m3", "Ready-mixed concrete", M8, FAC)
                                                    - _one["quantity"] * 2.4) < 1e-6)

import datetime as _dt  # noqa: E402
TODAY = _dt.date(2026, 10, 14)          # a Wednesday with mixer lines in its week (the demo's months are Sep–Dec 2026)
PG = lookahead.page(bucket="commit", acc=access.current(), with_restrictions=False, today=TODAY)


def strings(o, out=None, skip=("vehicle_type", "vehicle_profile", "payload_fallback", "payload_fallback_vehicle", "vehicle",
                                "vehicles", "key", "group", "profile")):
    """Every string VALUE a page could print. The stored-key fields (`skip`) are ids the pages never print: the app maps
    them through vehLabel (the carbon page's vehicles, the CLP chart's `group` beside its `label`), and `key` is a
    factor's id beside its `label`."""
    out = out if out is not None else []
    if isinstance(o, dict):
        for k, v in o.items():
            if k in skip:
                continue
            strings(v, out, skip)
    elif isinstance(o, (list, tuple)):
        for v in o:
            strings(v, out, skip)
    elif isinstance(o, str):
        out.append(o)
    return out


_pgs = " ".join(strings(PG))
ok("6: the Look-ahead read carries mixer lines this week", M8 in json.dumps(PG, ensure_ascii=False))
ok("6: ...and every printable value says 'Concrete mixer', never 'truck'", N8 in _pgs and not TRUCK.search(_pgs),
   str(TRUCK.findall(_pgs))[:100])
def _contexts(o, out):
    if isinstance(o, dict):
        if o.get("vehicle_type") == M8 and "vehicle_short" in o:
            out.append(o)
        for v in o.values():
            _contexts(v, out)
    elif isinstance(o, list):
        for v in o:
            _contexts(v, out)
    return out
_ctx = _contexts(PG, [])
ok("6: a mixer line's context carries vehicle_name and a short name from it",
   bool(_ctx) and _ctx[0].get("vehicle_name") == N8 and _ctx[0].get("vehicle_short") == N8)
import clashes  # noqa: E402
_cl = clashes.page_flags(PG) if hasattr(clashes, "page_flags") else None
_flags = " ".join(strings(PG.get("flags") or PG.get("clashes") or []))
ok("6: the UNBAKED flag on a mixer line names the Concrete mixer", ("not baked for " + N8) in _pgs, _flags[:200])

import openpyxl  # noqa: E402
_x = []
for ws in openpyxl.load_workbook(io.BytesIO(export.build_xlsx(PG)), read_only=True).worksheets:
    for row in ws.iter_rows(values_only=True):
        _x += [str(c) for c in row if c is not None]
_x = " ".join(_x)
ok("6: the Look-ahead XLSX names the Concrete mixer and never says 'truck'", N8 in _x and not TRUCK.search(_x), str(TRUCK.findall(_x))[:100])
_have_pdf = bool(shutil.which("pdftotext"))
# -raw, not -layout (16 Oct 2026): the Vehicle cell wraps "Concrete / mixer 8 m³ / (32t)" over three lines, and -layout
# reads each line across the row, so "Concrete" and "mixer" sit apart with the day columns between them. Xpdf (this
# laptop) happened to print one wrapped cell alone and passed; poppler (CI) did not. -raw keeps a cell's lines together.
_p = " ".join(pdf_text(export.build_pdf(PG), "", raw=True).split()) if _have_pdf else ""     # words, not line breaks
ok("6: the Look-ahead PDF names the Concrete mixer and never says 'truck'",
   not _have_pdf or ("Concrete mixer" in _p and not TRUCK.search(_p)), _p[:0])
_ds = " ".join(pdf_text(export.build_day_sheet_pdf(PG, TODAY.isoformat()), "").split()) if _have_pdf else ""
ok("6: the Day sheet names the Concrete mixer and never says 'truck'",
   not _have_pdf or ("Concrete mixer" in _ds and not TRUCK.search(_ds)))

import costlines  # noqa: E402
_cls = costlines.lines(acc=access.current(), from_month=11, to_month=11, status="Approved", factors=FAC)["lines"]
_mx = [l for l in _cls if l.get("vehicle_type") == M8]
ok("6: costlines (Dashboard, Forecasts) carry vehicle_name and a short name from it",
   bool(_mx) and _mx[0].get("vehicle_name") == N8 and _mx[0].get("vehicle_short") == N8)
ok("6: no printable costlines value says 'truck'", not TRUCK.search(" ".join(strings(_cls))))

_kp = main.public_month_kpis(month=11)
_kpm = [l for l in _kp["lines"] if l["vehicle_type"] == M8]
ok("6: the public month-kpis send each line's NAME beside its key", bool(_kpm) and _kpm[0]["vehicle_name"] == N8
   and all("vehicle_name" in l for l in _kp["lines"]) and "payload_fallback_name" in _kp)
_fm = main.public_forecast_matrix(from_=9, to=12, unit="t", sections=0)
_fm = _fm if isinstance(_fm, (list, dict)) else json.loads(_fm.body)
_fml = _fm if isinstance(_fm, list) else (_fm.get("rows") or _fm.get("lines") or _fm.get("routes") or [])
_fmm = [r for r in _fml if isinstance(r, dict) and r.get("vehicle_type") == M8]
ok("6: the public forecast-matrix sends the NAME beside the key", bool(_fmm) and _fmm[0].get("vehicle_name") == N8, str(type(_fm)))
ok("6: no printable public value says 'truck'", not TRUCK.search(" ".join(strings(_kp) + strings(_fm))))

import bulletin_doc  # noqa: E402
_bs = bulletin_doc.sheet(11, access.current())
ok("6: the bulletin's view model says no 'truck'", not TRUCK.search(" ".join(strings(_bs))))
try:
    _bb = export.build_bulletin_pdf(_bs)
    # 14 Oct 2026: a tenant with no council areas (the shipped demo package) put every source in the left column, and the
    # empty right column ([""]) made reportlab fail the whole bulletin — fixed in export.Kit.sources
    ok("6: the bulletin PDF builds for a tenant with no council areas (the sources' empty column)", _bb[:4] == b"%PDF")
except Exception as e:
    _bb = b""
    ok("6: the bulletin PDF builds for a tenant with no council areas (the sources' empty column)", False, f"{type(e).__name__}: {e}")
if _have_pdf and _bb:
    _bt = pdf_text(_bb, "")
    ok("6: the bulletin PDF says no 'truck'", _bt != "" and not TRUCK.search(_bt))
import clp  # noqa: E402
import clp_pack  # noqa: E402
_M = clp.monitoring(11, acc=access.current())
_ms = " ".join(strings(_M))
ok("6: the CLP monitoring read names the Concrete mixer and never says 'truck'", N8 in _ms and not TRUCK.search(_ms), str(TRUCK.findall(_ms))[:100])
_cx = []
for ws in openpyxl.load_workbook(io.BytesIO(clp_pack.build_xlsx(_M)), read_only=True).worksheets:
    for row in ws.iter_rows(values_only=True):
        _cx += [str(c) for c in row if c is not None]
ok("6: the CLP pack XLSX says no 'truck'", not TRUCK.search(" ".join(_cx)))
if _have_pdf:
    _ct = pdf_text(clp_pack.build_pdf(_M), "")
    ok("6: the CLP pack PDF says no 'truck'", _ct != "" and not TRUCK.search(_ct))
import carbon  # noqa: E402
try:
    _sc = carbon.scenario(acc=access.current(), from_month=11, to_month=11)
    _scs = " ".join(strings(_sc))
    ok("6: the carbon page (scenario, factor list, notes) says no 'truck'", not TRUCK.search(_scs), str(TRUCK.findall(_scs))[:100])
    if _have_pdf:
        _cp = pdf_text(export.build_carbon_pdf(_sc), "")
        ok("6: the carbon PDF says no 'truck'", not TRUCK.search(_cp))
except carbon.CarbonError as e:
    ok("6: the carbon page builds on the demo", False, str(e))

# --------------------------------------------------------------------------- #
#  7. Source level                                                             #
# --------------------------------------------------------------------------- #
APP, MAP = read("frontend/index.html"), read("map/index.html")
GUIDE, TECH = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
LAND = read("landing/index.html") if os.path.exists(os.path.join(ROOT, "landing", "index.html")) else ""
ok("7: the literal 'Truck mixer' is in no screen's source (app, map, both guides, landing)",
   not any("Truck mixer" in s for s in (APP, MAP, GUIDE, TECH, LAND)))
ok("7: the app's vehLabel applies the word rule to every key it falls back to",
   'const vehWord = (v) => String(v == null ? "" : v).replace(/^\\s*truck\\s+mixer\\b/i, "Concrete mixer");' in APP
   and "return (l && l !== v) ? l : vehWord(v || \"\");" in APP)
ok("7: the map's vehName / vehWord carry the same rule",
   "function vehWord(v){ return String(v == null ? '' : v).replace(/^\\s*truck\\s+mixer\\b/i, 'Concrete mixer'); }" in MAP
   and "function vehName(key, name){ return name || vehWord(key); }" in MAP)
# the places the sweep found printing a key, each now through a name helper
for label, gone, now in (
    ("Routes form vehicle ticks", "                        {v}\n                        {tag &&", "{vehLabel(v)}\n                        {tag &&"),
    ("Routes 'Show' picker", "<option key={v}>{v}</option>", "<option key={v} value={v}>{vehLabel(v)}</option>"),
    ("Routes count line", "routed for {showProfile}", "routed for {vehLabel(showProfile)}"),
    ("Routes create message", "routing ${prof} (", "routing ${vehLabel(prof)} ("),
    ("Routes chip tooltip", "`${k} · not routed`", "`${vehLabel(k)} · not routed`"),
    ("Look-ahead map popup", "drawn for ${r.vehicle_profile}", "drawn for ${vehLabel(r.vehicle_profile)}"),
    ("Look-ahead last-week tooltip", "title={r.vehicle_type}", "title={vehLabel(r.vehicle_type)}"),
    ("Look-ahead payload fallback", "(${c.payload_fallback} fallback)", "(${vehLabel(c.payload_fallback)} fallback)"),
    ("Forecasts CSV", 'g.material_description || "", g.vehicle || "",', 'g.material_description || "", vehLabel(g.vehicle),'),
    ("Dashboard full name", "r.vehicle !== veh ? r.vehicle : null", "vehLabel(r.vehicle) !== veh ? vehLabel(r.vehicle) : null"),
    ("Look-ahead full name", "c.vehicle_type !== veh ? c.vehicle_type : null", "vehLabel(c.vehicle_type) !== veh ? vehLabel(c.vehicle_type) : null"),
    ("Dashboard Today", "vehicle_full: ctx.vehicle_type || l.vehicle_type,", "vehicle_full: vehLabel(ctx.vehicle_type || l.vehicle_type),"),
    ("Config row name", '<div className="font-medium text-slate-800 leading-tight">{k}</div>', "data-cfg-vehname>{nm}</div>"),
):
    ok(f"7: app — {label} prints the name, not the key", gone not in APP and now in APP)
_vt = APP[APP.index("data-cfg-vehname"):]
_vt = _vt[:_vt.index("</tbody>")]
ok("7: Config's vehicle table: no placeholder or label reads the bare key",
   "placeholder={k}" not in _vt and "aria-label={`${k} " not in _vt and "aria-label={`${nm} " in _vt
   and '"Vehicle (id)"' not in APP)
# a stored English name equal to its id (the live demo's config row) counts as none typed: the box is empty and its
# placeholder shows the name the rule gives (browser check, 14 Oct 2026: the box showed the stored id-like text)
ok("7: Config's English-name box shows a label equal to the id as empty, the rule's name as its placeholder",
   "value={(lab.en && lab.en !== k) ? lab.en : \"\"} placeholder={vehWord(k)}" in _vt and "value={lab.en || \"\"}" not in _vt)
for label, gone, now in (
    ("route drawer caption", "mat+' · '+veh+' · payload", "mat+' · '+vehN+' · payload"),
    ("route drawer, several lines", "+' · '+(r.vehicle_type||'—')", "+' · '+(vehName(r.vehicle_type,r.vehicle_name)||'—')"),
    ("KPI bar payload note", "const fbName = payloads[0].payload_fallback_vehicle;",
     "const fbName = vehName(payloads[0].payload_fallback_vehicle, payloads[0].payload_fallback_name);"),
):
    ok(f"7: map — {label} prints the name, not the key", gone not in MAP and now in MAP)
_srv = {f: read(f"backend/{f}") for f in ("export.py", "clashes.py", "bulletin.py", "carbon.py", "road_sections.py", "network.py", "limits.py")}
ok("7: server — no export or flag falls back to the bare vehicle_type key",
   "c.get('vehicle_short') or c.get('vehicle_type')" not in _srv["export.py"] + _srv["clashes.py"]
   and 'c.get("vehicle_short") or c.get("vehicle_type")' not in _srv["export.py"])
# the map's limit card and conditions warning print breaches[].vehicle as sent: the server sends the NAME (below)
ok("7: server — limits read the name on display, not the stored vehicle_label (the map's limit card prints it as sent)",
   "h.get('vehicle_label') or vehicle_type" not in _srv["limits.py"] and 'h.get("vehicle_label") or h["vehicle_profile"]' not in _srv["limits.py"])
ok("7: server — carbon's factor list and note, the road-load note, the bulletin's fallback and the alternatives error use the name",
   "label=conversions.vehicle_label(doc, vname)" in _srv["carbon.py"] and "label=vname," not in _srv["carbon.py"]
   and "conversions.vehicle_label(ctx['doc'], s['vehicle'])" in _srv["carbon.py"]
   and "have no {conversions.vehicle_label(conversions.load_factors(), profile)} route" in _srv["road_sections.py"]   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end words on screens): the note is shorter, still the name
   and "fb_name = conversions.vehicle_label(conversions.load_factors(), fb_name)" in _srv["bulletin.py"]
   and "cached for {conversions.vehicle_label(conversions.load_factors(), profile)} /" in _srv["network.py"])
ok("7: the guide names the four categories and the Concrete mixers with their sources",
   all(k in GUIDE for k in NEW) and "Concrete mixer 8 m³ (32t) 18 t" in GUIDE and "BS EN 1991-1-1" in GUIDE
   and "concrete mixers 10 + 20 (an assumption with no published source)" in GUIDE)

# --------------------------------------------------------------------------- #
#  9. Steel in tonnes only (the user, 15 Oct 2026)                             #
# --------------------------------------------------------------------------- #
# WIDENED 29 Oct 2026 (3b): the three steel categories of the split are tonnes only too
STEEL = ("Steel / rail", "Structural steel / rebar", "Rail", "Reinforcement", "Structural steel")
F9 = conversions.load_factors_file()
ok("9: every steel category (the two older ones and the three of the split) is tonnes only in the seed, with the reason",
   all(F9["material_categories"][k].get("units") == ["t"] and F9["material_categories"][k].get("default_unit") == "t"
       and "tonnes only" in F9["material_categories"][k].get("_units_note", "") for k in STEEL))
# NARROWED 22 Oct 2026 (abnormal loads, B2's bare category): "Abnormal loads" is movements only (units ["vehicles"])
ok("9: no other category is restricted (they keep every unit) — except Abnormal loads, counted in movements only",
   all("units" not in c for k, c in F9["material_categories"].items() if k not in STEEL + ("Abnormal loads",) and isinstance(c, dict))
   and F9["material_categories"]["Abnormal loads"].get("units") == ["vehicles"])
ok("9: allowed_units: steel → tonnes only; another material, or one the document lacks → all three",
   conversions.allowed_units(F9, "Steel / rail") == ["t"] and conversions.allowed_units(F9, "Structural steel / rebar") == ["t"]
   and conversions.allowed_units(F9, "Small aggregate") == ["m3", "t", "vehicles"]
   and conversions.allowed_units(F9, "Unknown stuff") == ["m3", "t", "vehicles"]
   and conversions.units_words(["t"]) == "tonnes")
ok("9: the seed validates with the new key", config.validate(F9) == [])
_b9 = json.loads(json.dumps(F9))
_b9["material_categories"]["Steel / rail"]["units"] = ["tons"]
_b9["material_categories"]["Structural steel / rebar"]["default_unit"] = "vehicles"
_p9 = config.validate(_b9)
ok("9: Config refuses a unit that is not m³, tonnes or vehicles, and a default unit outside a material's units",
   any("Steel / rail" in x and "units must be a list" in x for x in _p9)
   and any("Structural steel / rebar" in x and "default unit is not one of its units" in x for x in _p9), str(_p9))
boot()
access.set_current("planner123")
for _u, _want in (("vehicles", True), ("m3", True), ("t", False)):
    _row = main.MatrixRow(route_id="R-none", discipline="structures", section_id="", material_type="Steel / rail",
                          vehicle_type="Artic Flatbed (44t)", unit=_u, cells=[], ipt="IPT1")
    try:
        main.save_matrix_row(_row)
        _e9 = None
    except Exception as e:      # noqa: BLE001
        _e9 = e
    _refused = getattr(_e9, "status_code", None) == 400 and "is planned in tonnes only" in str(getattr(_e9, "detail", ""))
    ok(f"9: the server {'refuses' if _want else 'accepts'} a steel line typed in {_u}" + (" — 400, in words" if _want else ""),
       _refused == _want, f"{_e9!r}"[:200])
APP9 = read("frontend/index.html")
ok("9: the Submit form offers only the category's units, and moves off a unit the category does not allow",
   'const allowedUnits = units.filter(u => (u !== "m3" || volumeOk) && (!catUnits || catUnits.includes(u)));' in APP9
   and '(catUnits && !catUnits.includes(u))) ? (cat.default_unit || (catUnits || ["t"])[0]) : u);' in APP9)
ok("9: Config → Materials has a 'Tonnes only' tick that sets units ['t'] and the default unit, or removes the rule",
   '"Tonnes only"' in APP9 and 'if(e.target.checked){ m.units = ["t"]; m.default_unit = "t"; } else delete m.units;' in APP9
   and "disabled={isTonnesOnly(c)}" in APP9)
ok("9: the guide says steel can only be typed in tonnes", "can only be typed in tonnes" in read("frontend/help/index.html"))

# --------------------------------------------------------------------------- #
#  10. The steel split (3b, 29 Oct 2026; the user: yes to Q1-Q6 as recommended) #
# --------------------------------------------------------------------------- #
F10 = conversions.load_factors_file()
C10 = F10["material_categories"]
SPLIT = ("Rail", "Reinforcement", "Structural steel")
RET10 = ("Steel / rail", "Structural steel / rebar")
ok("10: the three new categories are in the seed, in that order, just before Asphalt",
   [k for k in C10 if not k.startswith("_")].index("Asphalt") - 3 == [k for k in C10 if not k.startswith("_")].index("Rail")
   and [k for k in C10 if k in SPLIT] == list(SPLIT))
ok("10: each new one carries the old steel numbers exactly: 7.85, tonnes only, no m³ conversion, flatbed, metals",
   all(C10[k]["density_t_per_m3"] == 7.85 and C10[k]["default_unit"] == "t" and C10[k]["units"] == ["t"]
       and C10[k]["volume_convertible"] is False and C10[k]["vehicles"] == ["Artic Flatbed (44t)"]
       and C10[k]["carbon_material"] == "metals" for k in SPLIT))
ok("10: same numbers as the two older steel categories (so no figure moves when a line changes category)",
   all(C10[k][f] == C10["Steel / rail"][f] == C10["Structural steel / rebar"][f]
       for k in SPLIT for f in ("density_t_per_m3", "default_unit", "units", "volume_convertible", "vehicles", "carbon_material")))
ok("10: each new density names its source; Rail's note names Network Rail's 45 ft road limit and its source",
   all("BS EN 1993-1-1" in C10[k]["_density_basis"] for k in SPLIT)
   and "45 ft" in C10["Rail"]["_note"] and "NRA22-01" in C10["Rail"]["_note"])
ok("10: no new category is retired; the two older ones are, with the reason, and keep every number they had",
   all(C10[k].get("retired") is not True for k in SPLIT)
   and all(C10[k].get("retired") is True and "RETIRED" in C10[k].get("_retired_note", "") for k in RET10)
   and C10["Steel / rail"]["vehicles"] == ["Artic Flatbed (44t)"] and C10["Structural steel / rebar"]["density_t_per_m3"] == 7.85)
ok("10: retired_materials names exactly the two older ones; material_names still lists them (old lines stay valid)",
   conversions.retired_materials(F10) == list(RET10)
   and all(k in conversions.material_names(F10) for k in RET10 + SPLIT)
   and conversions.retired_materials({}) == [] and conversions.retired_materials({"material_categories": {"X": {"retired": "yes"}}}) == [])
ok("10: an older category still converts and still counts in tonnes (density 7.85, tonnes only)",
   conversions.allowed_units(F10, "Steel / rail") == ["t"] and conversions.to_tonnes(12, "t", "Steel / rail", "Artic Flatbed (44t)", F10) == 12)
_c10 = (F10.get("carbon") or {}).get("materials") or {}
ok("10: carbon: all five steel categories read the one government metals figure", "metals" in _c10
   and len({C10[k]["carbon_material"] for k in SPLIT + RET10}) == 1)
ok("10: the seed validates with the retired flag", config.validate(F10) == [], str(config.validate(F10))[:300])
_b10 = json.loads(json.dumps(F10))
_b10["material_categories"]["Rail"]["retired"] = "yes"
ok("10: Config refuses a retired flag that is not true or false", any("Rail" in x and "retired must be true or false" in x
                                                                      for x in config.validate(_b10)))
_c10b = json.loads(json.dumps(F10))
for _k, _c in _c10b["material_categories"].items():
    if not _k.startswith("_") and isinstance(_c, dict):
        _c["retired"] = True
ok("10: Config refuses a document whose every category is retired (nothing left to pick)",
   any("at least one category that is not retired" in x for x in config.validate(_c10b)))
ok("10: the disciplines link the new categories and no retired one",
   not any(k in c for c in taxonomy.DISCIPLINE_MATERIALS.values() for k in RET10)
   and all(k in taxonomy.DISCIPLINE_MATERIALS["structures"] for k in ("Reinforcement", "Structural steel"))
   and "Rail" in taxonomy.DISCIPLINE_MATERIALS["superstructure"]
   and all(k in taxonomy.DISCIPLINE_MATERIALS["substructure"] for k in ("Reinforcement", "Structural steel")))
boot()
access.set_current("planner123")
_m10 = main.meta(None)
ok("10: /api/meta lists every category (the older ones too) and names the retired ones",
   all(k in _m10["materials"] for k in SPLIT + RET10) and _m10["retired_materials"] == list(RET10))
for _k in SPLIT:
    _row = main.MatrixRow(route_id="R-none", discipline="structures", section_id="", material_type=_k,
                          vehicle_type="Artic Flatbed (44t)", unit="vehicles", cells=[], ipt="IPT1")
    try:
        main.save_matrix_row(_row)
        _e10 = None
    except Exception as e:      # noqa: BLE001
        _e10 = e
    ok(f"10: a {_k} line in vehicles is refused in words (tonnes only)",
       getattr(_e10, "status_code", None) == 400 and "is planned in tonnes only" in str(getattr(_e10, "detail", "")), f"{_e10!r}"[:200])
APP10 = read("frontend/index.html")
ok("10: the app has one picker rule: every category that is not retired, plus the record's own value",
   "function pickMaterials(all, meta, keep) {" in APP10
   and "const ret = new Set((meta && meta.retired_materials) || []);" in APP10
   and "return (all || []).filter(m => !ret.has(m) || k.has(m));" in APP10)
ok("10: the Submit picker, a location's supplies and receives, and a site area's materials all go through it",
   "{pickMaterials(materials, meta, material).map(m => <option key={m}>{m}</option>)}" in APP10
   and "{pickMaterials(materials, meta, form.supplies).map(cat => (" in APP10
   and "{pickMaterials(materials, meta, form.receives).map(cat => (" in APP10
   and "{pickMaterials(materials, meta, areaForm.materials).map(cat =>" in APP10)
ok("10: Config → Materials marks a retired category 'Older: pick one of the three' and lists it last",
   "{c.retired === true && <span" in APP10 and "Older: pick one of the three" in APP10
   and ".sort((x, y) => ((doc.material_categories[x] || {}).retired === true) - ((doc.material_categories[y] || {}).retired === true))" in APP10)
ok("10: no screen source names a steel category (they come from Config)",
   not any(x in APP10 for x in ('"Steel / rail"', '"Structural steel / rebar"', '"Structural steel"', '"Reinforcement"')))
GEN10 = read("backend/tools/make_demo_tenant.py")
ok("10: the demo generator no longer uses a retired steel category; the girders are Structural steel, the bar Reinforcement",
   '"Steel / rail"' not in GEN10 and '"Structural steel / rebar"' not in GEN10
   and 'STRUCT, REINF = "Structural steel", "Reinforcement"' in GEN10
   and '("RH", "VS", REINF), ("RH", "VS", PRECAST), ("RH", "VS", STRUCT),   # R044–R048' in GEN10
   and '("WS4", "structures", STRUCT, "RH", "VS", FLAT, "t", 14,' in GEN10
   and '("WS4", "structures", REINF, "RH", "VS", FLAT, "t", 5,' in GEN10
   and '("Deck and laydown", "unload", [STRUCT, REINF, PRECAST, GENERAL],' in GEN10)
G10 = read("frontend/help/index.html")
ok("10: the guide names the three, says the older two are marked Older and how a line moves, and the carbon and density rows",
   "Rail, Reinforcement and Structural steel) can only be typed in tonnes" in G10
   and "The older Steel / rail and Structural steel / rebar are marked Older on Config" in G10
   and "to move a line, edit its category (no figure changes)" in G10
   and "Rail, Reinforcement and Structural steel 7.85" in G10
   and "Rail, Reinforcement and Structural steel (and the older Steel / rail, Structural steel / rebar) 3821.94858" in G10)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
