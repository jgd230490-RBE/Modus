"""
G2, 2026-09-16 — Modus: a product with no project data in it, and a tenant package.

WHAT IS ASSERTED
----------------
  1. The tree ships NOTHING of the first project's: no seed data, no static alignment,
     no project names in any shipped file (source-level, every file outside tests/).
  2. A fresh tenant boots EMPTY — generic disciplines and the factors row only.
  3. /api/meta carries the tenant block; the defaults are Modus / Team / EUR / no country.
  4. The tenant package: export → import into an empty tenant round-trips every row;
     a non-empty tenant refuses without replace; a bad package is refused; an unknown
     column is dropped and reported; the boot seeds are superseded by the package's.
  5. The demo package (demo/uk-corridor.package.json) validates, imports, and is what
     it says: GBP, GB, invented names, 18 routes, four approved months, an overlay
     whose bands are contiguous and whose boundaries sit on band edges.
  6. Country gating: a GB tenant has no restriction provider and no automatic diesel
     index; an EE tenant has both. The map's restriction panel is provider-driven.
  7. The overlay endpoint: a tenant with no overlay gets {} + tenant; one with an
     overlay gets it back with an ETag, and a matching If-None-Match gets 304.
  8. Theme tokens: the three shipped pages carry the Modus palette and none of the old.

WHAT THIS DOES NOT PROVE
------------------------
  * HTTP is stubbed; the endpoints are called as functions.
  * Nothing renders. The map's overlay loader is asserted at source level only.
  * The demo package's routes are UNBAKED — HERE is never called from here.

Run:  python3 backend/tests/test_modus.py
"""
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

# --------------------------------------------------------------------------- #
#  Stubs (the same shape every other harness uses)                             #
# --------------------------------------------------------------------------- #
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
    get = post = put = delete = patch = _deco      # no `middleware`: main.py skips the gate wiring

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


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

TMP = tempfile.mkdtemp(prefix="modus_g2_")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import restrictions  # noqa: E402
import fuel  # noqa: E402
import tenant_package  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
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
    if os.path.exists(db._SQLITE_PATH):
        os.remove(db._SQLITE_PATH)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    config.invalidate()


def boot():
    """What main.lifespan does after the schema: the generic seeds only."""
    reset_db()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate()


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# =========================================================================== #
#  1. Nothing of the first project's ships                                     #
# =========================================================================== #
ok("no seed_data directory", not os.path.exists(os.path.join(BACKEND, "seed_data")))
ok("no seed.py", not os.path.exists(os.path.join(BACKEND, "seed.py")))
ok("no static map data directory", not os.path.exists(os.path.join(ROOT, "map", "data")))
ok("no ipt_segments.js", not os.path.exists(os.path.join(ROOT, "map", "ipt_segments.js")))
ok("overlay.js is the product module", os.path.exists(os.path.join(ROOT, "map", "overlay.js")))
ok("no artifacts/ mockups", not os.path.exists(os.path.join(ROOT, "artifacts")))
for stale in ("main.py", "db.py", "network.py", "config.py", "conversions.py",
              "README-DIAGNOSTICS.txt", "README-STEP-B-C.txt"):
    ok(f"no stale root-level {stale}", not os.path.exists(os.path.join(ROOT, stale)))
# NARROWED: README.txt is the delivery note a session checks HEAD against (project
# instructions), so one may exist — but only a Modus delivery note, never the old one.
_rt = os.path.join(ROOT, "README.txt")
ok("no stale root-level README.txt — if present it is a Modus delivery note",
   not os.path.exists(_rt) or open(_rt, encoding="utf-8").read().startswith("MODUS — "))
ok("the guide's placeholder.pl orphan is gone",
   not os.path.exists(os.path.join(ROOT, "frontend", "help", "media", "placeholder.pl")))

# Source-level: the names that identified the first project must not appear in any
# SHIPPED file. Test fixtures are the deliberate exception (see fixtures/taxonomy_rbe.json).
PROJECT_TERMS = [r"\bRBE\b", r"Rail\s?Baltic", r"\bAlliance\s?1\b", r"OnEST", r"\bNGE\b", r"\bMerko\b",
                 r"\bGRK\b", r"\bSweco\b", r"Muuga", r"Soodevahe", r"[ÜU]lemiste", r"P[äa]rnu",
                 r"Tootsi", r"Timmermanni", r"Papiniidu", r"Rääma", r"Orasselja", r"\bLelle\b",
                 r"\bRapla\b", r"Kivimae", r"Appendix E", r"\bWP3\b", r"\bIPT [1-6]\b", r"\bIPT[1-6]\b"]
SHIPPED_EXT = (".py", ".html", ".js", ".json", ".yaml", ".yml", ".md", ".txt", ".example")
hits = {}
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "tests", "node_modules")]
    for fn in files:
        if not fn.endswith(SHIPPED_EXT):
            continue
        p = os.path.join(dirpath, fn)
        rel = os.path.relpath(p, ROOT)
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for term in PROJECT_TERMS:
            n = len(re.findall(term, txt))
            if n:
                hits.setdefault(rel, []).append(f"{term}×{n}")
# NARROWED (G2 label-only decision): team SLOT ids — IPT1…IPT6 — are internal identifiers.
# The access codes (IPT1_CODE…), forecasts.ipt and canonical_ipt() are built on them, so
# the id form may appear where that plumbing lives and in the demo data that uses it.
# What a person READS goes through taxonomy.team_text() / teamText(), asserted in §4b
# below. The human form "IPT 3" is still refused everywhere except access.py's docstring.
ID_FORM_ALLOWED = {"backend/access.py", "backend/taxonomy.py", "backend/db.py", "backend/network.py",
                   "backend/main.py", "frontend/index.html", "map/index.html",
                   "backend/tools/make_demo_tenant.py", "demo/uk-corridor.package.json",
                   "README.md", "README.txt", "env.example"}   # these name the IPTn_CODE variables
HUMAN_FORM_ALLOWED = {"backend/access.py"}
for rel in list(hits):
    keep = []
    for h in hits[rel]:
        if h.startswith(r"\bIPT[1-6]\b") and rel in ID_FORM_ALLOWED:
            continue
        if h.startswith(r"\bIPT [1-6]\b") and rel in HUMAN_FORM_ALLOWED:
            continue
        keep.append(h)
    if keep:
        hits[rel] = keep
    else:
        hits.pop(rel)
ok("⭐ no shipped file names the first project or its places",
   not hits, json.dumps(hits, ensure_ascii=False)[:1500])

# =========================================================================== #
#  2. A fresh tenant boots empty                                               #
# =========================================================================== #
boot()
ok("no locations after boot", db.count_locations() == 0)
ok("no routes after boot", not db.query("SELECT id FROM routes"))
ok("no teams after boot", taxonomy.list_ipts() == [])
ok("no work sections after boot", taxonomy.list_work_sections() == [])
ok("the generic disciplines are seeded", len(taxonomy.list_disciplines(include_out_of_scope=True)) == 10)
ok("the factors row is seeded", config.get_row() is not None)
ok("tenant_package.is_empty() agrees", tenant_package.is_empty() is True)
main_src = read("backend/main.py")
main_code = "\n".join(l.split("#", 1)[0] for l in main_src.splitlines())
ok("main.py seeds no network at boot", "seed_network(" not in main_code)
ok("main.py imports no seed module", "import seed" not in main_code)

# =========================================================================== #
#  3. The tenant block on /api/meta                                            #
# =========================================================================== #
meta = main.meta()
t = meta.get("tenant") or {}
ok("meta carries the tenant block", bool(t))
ok("defaults: Modus / Team / EUR / no country",
   t.get("name") == "Modus" and t.get("team_label") == "Team" and t.get("currency") == "EUR"
   and t.get("country") is None, str(t))
ok("the currency symbol is derived", t.get("currency_symbol") == "€")
ok("no country → no restriction provider, no automatic fuel index",
   t.get("restrictions_provider") is False and t.get("fuel_index_auto") is False)
doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
doc["tenant"] = {"name": "Test Co", "team_label": "Package", "currency": "GBP", "country": "gb"}
r = config.save(doc, by="test")
ok("a tenant block saves through validate()", r["ok"], str(r))
config.invalidate()
t2 = main.meta()["tenant"]
ok("…and reads back with the symbol and an upper-cased country",
   t2["team_label"] == "Package" and t2["currency_symbol"] == "£" and t2["country"] == "GB", str(t2))
doc["tenant"] = {"currency": "XXX"}
ok("an unknown currency is refused", not config.save(doc, by="test")["ok"])
doc["tenant"] = {"country": "Great Britain"}
ok("a non-ISO country is refused", not config.save(doc, by="test")["ok"])
doc["tenant"] = {"team_label": ""}
ok("an empty team label is refused", not config.save(doc, by="test")["ok"])

# =========================================================================== #
#  4. The package round trip                                                   #
# =========================================================================== #
ok("every tenanted table is in the package ORDER exactly once",
   sorted(tenant_package.ORDER) == sorted(db.TENANTED_TABLES) and len(tenant_package.ORDER) == len(set(tenant_package.ORDER)),
   str(set(db.TENANTED_TABLES) ^ set(tenant_package.ORDER)))

boot()
BAL, SMALL = "Large aggregate / ballast", "Small aggregate"
q = network.create_location("Pit A", "origin", lat=52.5, lon=-1.2, loc_type="Quarry", supplies=[BAL])
c = network.create_location("Yard B", "destination", lat=52.6, lon=-0.9, loc_type="Compound", receives=[BAL, SMALL])
rr = network.create_route(q["id"], c["id"], material_category=BAL, ipt="IPT 1")
rid = rr["id"]
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
           "material_type, material_description, vehicle_type, submitted_by, status, reject_reason, ipt) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (db.current_tenant(), "F1", rid, 10, "superstructure", "", 1200.0, "t", BAL, "ballast",
            "Artic Tipper (44t)", "t", "Approved", None, "IPT1"))
# a fake baked leg, so geometry round-trips too
db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
           "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (db.current_tenant(), rid, "Artic Tipper (44t)", "loaded", 0,
            json.dumps({"type": "LineString", "coordinates": [[-1.2, 52.5], [-0.9, 52.6]]}), 24.5, 0.6, "2026-09-16T00:00:00Z"))
tenant_package.import_rows("ipts", [{"id": "IPT1", "label": "Team One", "manager": None, "active": True, "merged_into": None}])
res = tenant_package.set_overlay({"version": "t1", "alignment": None, "chainage": None,
                                  "bands": [{"ipt": "Team One", "ws": [], "label": "all", "chain_from": 0, "chain_to": 1000, "colour": "#123456"}],
                                  "view": {"center": [-1.0, 52.55], "zoom": 9}}, by="test")
ok("an overlay stores", res["ok"], str(res))
ok("the tenant is no longer empty", tenant_package.is_empty() is False)

pkg = tenant_package.export_tenant(app_version="test")
ok("export has the format marker", pkg["modus_package"] == tenant_package.FORMAT)
cnt = tenant_package.counts(pkg)
ok("export carries the rows written", cnt["locations"] == 2 and cnt["routes"] == 1 and cnt["forecasts"] == 1
   and cnt["route_geometry"] == 1 and cnt["ipts"] == 1 and cnt["config"] == 2, str(cnt))
ok("no row in the export carries tenant_id",
   all("tenant_id" not in r for rows in pkg["tables"].values() for r in rows))
ok("validate() passes the export", tenant_package.validate(pkg) == [], str(tenant_package.validate(pkg)))

try:
    tenant_package.import_tenant(pkg)
    ok("🔴 a non-empty tenant refuses an import without replace", False)
except ValueError as e:
    ok("🔴 a non-empty tenant refuses an import without replace", "replace" in str(e), str(e))

boot()                                   # a fresh, empty tenant with the boot seeds in it
before_disc = len(taxonomy.list_disciplines(include_out_of_scope=True))
pkg2 = json.loads(json.dumps(pkg))
pkg2["tables"]["locations"][0]["not_a_column"] = 1     # an older/newer schema mismatch
out = tenant_package.import_tenant(pkg2)
ok("import into an empty tenant succeeds", out["ok"], str(out))
ok("…and reports the dropped column", out["dropped_columns"].get("locations") == ["not_a_column"], str(out["dropped_columns"]))
ok("locations round-trip", db.count_locations() == 2)
ok("routes round-trip with their rate fields",
   db.query("SELECT * FROM routes")[0]["id"] == rid)
ok("forecasts round-trip", db.query("SELECT quantity FROM forecasts")[0]["quantity"] == 1200.0)
g = db.query("SELECT * FROM route_geometry")
ok("⭐ baked geometry round-trips — no re-bake after a move",
   len(g) == 1 and g[0]["distance_km"] == 24.5 and json.loads(g[0]["geometry"])["type"] == "LineString")
ok("the team round-trips", [i["id"] for i in taxonomy.list_ipts()] == ["IPT1"])
ok("the boot-seeded disciplines are superseded by the package's, not doubled",
   len(taxonomy.list_disciplines(include_out_of_scope=True)) == before_disc)
ov = tenant_package.get_overlay_row()
ok("the overlay config row round-trips", ov is not None and json.loads(ov["value"])["version"] == "t1")
ok("every row is stamped with the CURRENT tenant, not the package's",
   {r["tenant_id"] for r in db.query("SELECT tenant_id FROM locations")} == {db.current_tenant()})

bad = json.loads(json.dumps(pkg))
bad["modus_package"] = 99
ok("a wrong format version is refused", tenant_package.validate(bad) != [])
bad = json.loads(json.dumps(pkg))
bad["tables"]["forecasts_legacy"] = []
ok("an unknown table is refused", any("unknown table" in p for p in tenant_package.validate(bad)))
bad = json.loads(json.dumps(pkg))
for row in bad["tables"]["config"]:
    if row["key"] == "factors":
        row["value"] = json.dumps({"material_categories": {}, "vehicles": {}, "planning": {}})
ok("a factors row that fails config.validate() is refused",
   any("config.factors" in p for p in tenant_package.validate(bad)))

# replace=True over a populated tenant
out2 = tenant_package.import_tenant(pkg, replace=True)
ok("replace=True re-imports over a populated tenant", out2["ok"] and out2["replaced"] and db.count_locations() == 2)

# the endpoints, as functions
st = main.tenant_status(token=None)
ok("GET /api/admin/tenant/status reports counts and emptiness", st["empty"] is False and st["counts"]["locations"] == 2)
ex = main.tenant_export(token=None)
ok("GET /api/admin/tenant/export is a JSON attachment",
   ex.media_type == "application/json" and "attachment" in ex.headers.get("Content-Disposition", ""))
ok("…whose body is a valid package", tenant_package.validate(json.loads(ex.body)) == [])
try:
    main.tenant_import(pkg, replace=0, token=None)
    ok("POST /api/admin/tenant/import refuses a non-empty tenant with 400", False)
except _HTTPException as e:
    ok("POST /api/admin/tenant/import refuses a non-empty tenant with 400", e.status_code == 400)

# =========================================================================== #
#  5. The demo package                                                         #
# =========================================================================== #
DEMO = os.path.join(ROOT, "demo", "uk-corridor.package.json")
ok("the demo package exists", os.path.exists(DEMO))
demo = json.load(open(DEMO, encoding="utf-8"))
ok("the demo package validates", tenant_package.validate(demo) == [], str(tenant_package.validate(demo))[:300])
dc = tenant_package.counts(demo)
ok("demo: 11 locations, 18 routes, 3 teams, 8 sections, 72 approved forecasts",
   dc["locations"] == 11 and dc["routes"] == 18 and dc["ipts"] == 3 and dc["work_sections"] == 8 and dc["forecasts"] == 72, str(dc))
ok("demo: every forecast is Approved", all(r["status"] == "Approved" for r in demo["tables"]["forecasts"]))
ok("demo: weeks are materialised and some actuals typed",
   dc["forecast_weeks"] > 0 and any(r.get("actual_qty") for r in demo["tables"]["forecast_weeks"]))
ok("demo: the commit week is confirmed for every September line",
   any(r.get("status") == "confirmed" for r in demo["tables"]["forecast_weeks"]))
ok("demo: no geometry — routes are UNBAKED until baked on a deployment", dc["route_geometry"] == 0)
fac = json.loads([r for r in demo["tables"]["config"] if r["key"] == "factors"][0]["value"])
ok("demo: GBP and GB", fac["tenant"]["currency"] == "GBP" and fac["tenant"]["country"] == "GB", str(fac["tenant"]))
ok("demo: no thaw season, no seasonal restrictions",
   fac["fair_price"]["season"]["thaw_months"] == [] and fac["seasonal_restrictions"] == [])
cst = json.loads([r for r in demo["tables"]["config"] if r["key"] == "costing"][0]["value"])
ok("demo: the fuel country is GB and a share is typed", cst["fuel"]["country"] == "GB" and cst["fuel"]["share_pct"] == 30.0, str(cst["fuel"]))
ovl = json.loads([r for r in demo["tables"]["config"] if r["key"] == "overlay"][0]["value"])
ok("demo: the overlay validates", tenant_package.validate_overlay(ovl) == [], str(tenant_package.validate_overlay(ovl)))
bands = ovl["bands"]
ok("demo: bands are contiguous", all(bands[i]["chain_to"] == bands[i + 1]["chain_from"] for i in range(len(bands) - 1)))
edges = {b["chain_from"] for b in bands} | {b["chain_to"] for b in bands}
ok("demo: every boundary sits on a band edge", all(b["chain_m"] in edges for b in ovl["boundaries"]))
ok("demo: the alignment is one Main Track LineString across the corridor",
   len(ovl["alignment"]["features"]) == 1 and ovl["alignment"]["features"][0]["properties"]["align_type"] == "Main Track"
   and len(ovl["alignment"]["features"][0]["geometry"]["coordinates"]) > 200)
ok("demo: chainage markers every ~100 m", len(ovl["chainage"]["features"]) > 250)
chains = [f["properties"]["chain"] for f in ovl["chainage"]["features"]]
ok("demo: ⭐ markers sit on EXACT 100 m chainages, so the map's 10/5/1 km ladder has ticks to draw",
   all(float(c) % 100 == 0 for c in chains) and sum(1 for c in chains if float(c) % 10000 == 0) >= 3,
   str(chains[:5]))
ok("demo: every band runs forwards, and the last one ends at the corridor's end",
   all(b["chain_to"] > b["chain_from"] for b in bands)
   and abs(bands[-1]["chain_to"] - max(float(c) for c in chains)) < 100, str(bands[-1]))
ok("demo: every placed location lies on the corridor (chainage in range)",
   all(int(re.search(r"(\d+)\+(\d{3})", r["detail"]).group(1)) * 1000 < max(float(c) for c in chains)
       for r in demo["tables"]["locations"] if "chainage" in (r.get("detail") or "")))
prov = [b for b in ovl["boundaries"] if b.get("provisional")]
ok("demo: exactly one provisional boundary, at the design-section interface, and it is listed in provisional_bounds",
   len(prov) == 1 and prov[0]["chain_m"] == 16500 and ovl["provisional_bounds"] == ["WS3/WS4 @ 16500"]
   and prov[0].get("note"), str(prov))
ds = {r["id"]: r for r in demo["tables"]["design_sections"]}
ok("demo: the design-section split is the provisional edge", ds["DS1"]["km_to"] == 16.5 and ds["DS2"]["km_from"] == 16.5)

# the validator catches the defects a hand-edited overlay actually has
_bad = json.loads(json.dumps(ovl)); _bad["bands"][-1]["chain_to"] = 100
ok("validate_overlay: a band that runs backwards is refused",
   any("runs backwards" in x for x in tenant_package.validate_overlay(_bad)))
_bad = json.loads(json.dumps(ovl)); _bad["boundaries"][0]["chain_m"] = _bad["boundaries"][0]["chain_m"] + 1
ok("validate_overlay: ⭐ a boundary off every band edge is refused — a tick must sit on its colour change",
   any("not a band edge" in x for x in tenant_package.validate_overlay(_bad)))
_bad = json.loads(json.dumps(ovl)); _bad["bands"][0]["colour"] = "teal"
ok("validate_overlay: a colour that is not #RRGGBB is refused",
   any("#RRGGBB" in x for x in tenant_package.validate_overlay(_bad)))
_bad = json.loads(json.dumps(ovl)); _bad["bands"][0]["chain_from"] = "0"
ok("validate_overlay: chainage given as text is refused (metres are numbers)",
   any("must be numbers" in x for x in tenant_package.validate_overlay(_bad)))
_bad = json.loads(json.dumps(ovl)); _bad["boundaries"] = [{"from_ws": "WS1"}]
ok("validate_overlay: a boundary with no chain_m is refused",
   any("numeric chain_m" in x for x in tenant_package.validate_overlay(_bad)))
ok("validate_overlay: an empty overlay (a tenant with no alignment) is fine",
   tenant_package.validate_overlay({}) == [])
lons = [c[0] for c in ovl["alignment"]["features"][0]["geometry"]["coordinates"]]
lats = [c[1] for c in ovl["alignment"]["features"][0]["geometry"]["coordinates"]]
ok("demo: the corridor is in the East Midlands, not Estonia",
   -1.5 < min(lons) and max(lons) < -0.5 and 52.3 < min(lats) and max(lats) < 52.9)
ok("demo: the view opens on the corridor", -1.2 < ovl["view"]["center"][0] < -0.6 and 52.4 < ovl["view"]["center"][1] < 52.8)
names = " ".join(r["name"] for r in demo["tables"]["locations"])
ok("demo: every location name is invented", "(fictional)" in json.dumps(demo["tables"]["locations"]) or "Wolds" in json.dumps(demo))
demo_txt = json.dumps(demo, ensure_ascii=False)
ok("demo: nothing of the first project's in it",
   not any(re.search(t_, demo_txt) for t_ in PROJECT_TERMS if "IPT" not in t_))

boot()
out3 = tenant_package.import_tenant(demo)
ok("demo: imports into an empty tenant", out3["ok"], str(out3)[:200])
ok("demo: the suggested GB fuel index is applied where none existed", out3["fuel_index_applied"] == ["GB"], str(out3["fuel_index_applied"]))
config.invalidate()
m3 = main.meta()
ok("demo: /api/meta reads the tenant back — £, Team, GB",
   m3["tenant"]["currency_symbol"] == "£" and m3["tenant"]["country"] == "GB" and m3["tenant"]["team_label"] == "Team", str(m3["tenant"]))
ok("demo: the pickers see three teams and eight sections",
   len(m3["ipts"]) == 3 and len(m3["work_sections"]) == 8)
ok("demo: the routes reach /api/meta with no distance (unbaked)",
   len(m3["routes"]) == 18 and all(not r.get("distance_km") for r in m3["routes"]))

# --- 5b. Team ids never reach a person (G2 label-only decision) --------------------
import clashes  # noqa: E402
import export  # noqa: E402
labels = taxonomy.team_labels()
ok("teams: the demo names its three slots",
   labels == {"IPT1": "North Team", "IPT2": "Central Team", "IPT3": "South Team"}, str(labels))
ok("teams: team_name() gives the tenant's label for any spelling of the id",
   taxonomy.team_name("IPT1") == "North Team" and taxonomy.team_name("ipt 2") == "Central Team"
   and taxonomy.team_name("IPT-3") == "South Team")
ok("teams: an unnamed slot reads '<team word> <n>', never the id", taxonomy.team_name("IPT6") == "Team 6")
ok("teams: team_text() names every id inside a shared value",
   taxonomy.team_text("IPT1 / IPT 6") == "North Team / Team 6", taxonomy.team_text("IPT1 / IPT 6"))
ok("teams: free text, look-alikes and empties are left alone",
   taxonomy.team_text("Contractor A") == "Contractor A" and taxonomy.team_text("receipt 3") == "receipt 3"
   and taxonomy.team_text(None) is None and taxonomy.team_text("") == "" and taxonomy.team_name("Contractor A") == "Contractor A")
_doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
_doc["tenant"]["team_label"] = "Crew"
config.save(_doc, by="test", network=network); config.invalidate()
ok("teams: the tenant's word is used for an unnamed slot", taxonomy.team_name("IPT6") == "Crew 6", taxonomy.team_name("IPT6"))
_doc["tenant"]["team_label"] = "Team"
config.save(_doc, by="test", network=network); config.invalidate()
ok("access: describe() offers the tenant's own three slots, not all six",
   access.describe({"role": "planner", "label": "Planner", "ipt": None})["ipts"] == ["IPT1", "IPT2", "IPT3"])
os.environ["IPT1_CODE"] = "north-secret"
ok("access: a team code's label is the team's name",
   access.resolve("north-secret") == {"role": "ipt", "ipt": "IPT1", "label": "North Team"}, str(access.resolve("north-secret")))
os.environ.pop("IPT1_CODE", None)
_lines = [{"route_id": "R9", "month_index": 9, "ipt": i, "discipline": "", "section_id": "", "context": {},
           "days": [{"day_date": "2026-09-14", "planned_qty": 10}]} for i in ("IPT1", "IPT2")]
_share = clashes.ipt_share(_lines)
ok("clashes: the shared-route flag keeps the ids (text and `ipts`) — naming them would cost a read on the page path",
   _share and all(f["text"].startswith("IPT1 + IPT2 ") for f in _share)
   and all(f["ipts"] == ["IPT1", "IPT2"] for f in _share), str(_share)[:200])
_nm = export._team_namer()
ok("export: one bound read names the ids in a flag's text for the sheets",
   _nm(_share[0]["text"]).startswith("North Team + Central Team ") and _nm(None) is None, _nm(_share[0]["text"]))
ok("export: the Clashes sheet and the PDF name the codes and the teams",
   "code=FLAG_LABEL.get(f.get(\"code\"), f.get(\"code\")), ipt=_nm(f.get(\"ipt\")), text=_nm(f.get(\"text\"))" in read("backend/export.py")
   and "{FLAG_LABEL.get(f['code'], f['code'])}: {_nm(f['text'])}" in read("backend/export.py")
   and export.FLAG_LABEL["IPT_SHARE"] == "SHARE")
ok("export: the team namer is built once per sheet, not per row",
   read("backend/export.py").count("= _team_namer()") == 4)   # day rows, Clashes sheet, PDF rows, PDF flags
_page = {"commit": {"lines": [{"route_id": "R9", "context": {"ipt": "IPT3", "origin_name": "A", "dest_name": "B"},
                               "days": [{"day_date": "2026-09-14", "derived": {}}]}]}}
_rows = export._line_rows(_page)
ok("export: the Team column carries the team's name", _rows and _rows[0]["ipt"] == "South Team", str(_rows[:1])[:200])
ok("export: the Team column header is the tenant's word", dict((k, h) for h, k in export.xlsx_cols())["ipt"] == "Team")
_exp_src = read("backend/export.py")
ok("export: the PDF's team column is headed with the tenant's word, not 'IPT / WS'",
   '"IPT / WS"' not in _exp_src and "(_tenant().get('team_label') or 'Team').upper())} / WS" in _exp_src)
ok("export: the Clashes sheet heads its team column with the tenant's word",
   '("IPT", "ipt"), ("WS", "section_id")' not in _exp_src and '(_tenant().get("team_label") or "Team", "ipt")' in _exp_src)
_ra = json.loads(main.public_alignment(_Request()).body)
ok("map: the overlay response carries the team names the map shows",
   {t["id"]: t["label"] for t in _ra["teams"]} == labels, str(_ra.get("teams")))
fe_src = read("frontend/index.html")
ok("frontend: the team pill shows the name, with the id only as a tooltip",
   "title={k}>{teamName(k)}</span>" in fe_src)
ok("frontend: the submit picker has no hard-coded six-team fallback",
   '["IPT1","IPT2","IPT3","IPT4","IPT5","IPT6"]' not in fe_src and "Object.keys(TEAM_LABELS)" in fe_src)
ok("frontend: signed-in role text shows the team's name",
   fe_src.count("{role.ipt ? teamName(role.ipt) : role.label}") == 2 and "` · ${role.ipt}`" not in fe_src)
ok("frontend: the clash rail shows the code's name and the teams' names",
   "{RAIL_LABEL[f.code] || f.code}</span> {teamText(f.text)}" in fe_src and 'IPT_SHARE: "SHARE"' in fe_src
   and "{f.code}</span> {f.text}" not in fe_src)
ok("frontend: the map entry is not called public — the map is behind the gate",
   '{ id: "map", label: "Route map"' in fe_src and "Back to public map" not in fe_src and 'label: "Public route map"' not in fe_src)
ok("frontend: a long KPI value steps its size down rather than being cut off, and says itself on hover",
   '(len > 12 ? "text-sm" : len > 9 ? "text-base" : len > 7 ? "text-lg" : "text-2xl")' in fe_src
   and 'data-fuel-widget="compact" title={hasIndex ? String(price) : ""}' in fe_src)
ok("frontend: a typed diesel price is dated as typed, a fetched one as the bulletin",
   '${autoIdx && idx.source !== "manual" ? "bulletin" : "typed"} ${fuelDate(idx.bulletin_date)}' in fe_src)
ok("frontend: no team value is rendered raw in a cell or an option",
   "{r.ipt}</td>" not in fe_src and "{r.ipt || \"—\"}</td>" not in fe_src
   and "value={i}>{i}</option>" not in fe_src and "{route.ipt || \"—\"}" not in fe_src
   and "chip(g.ipt)" not in fe_src and "g.yearLabel, g.ipt," not in fe_src)

# =========================================================================== #
#  6. Country gating                                                           #
# =========================================================================== #
restrictions.COUNTRY_OVERRIDE = None
ok("GB: no restriction provider", restrictions.enabled() is False and restrictions.provider() is None)
lay = main.restriction_layers()
ok("GB: /api/restrictions/layers answers provider: null and no layers", lay["provider"] is None and lay["layers"] == [])
fa = restrictions.fetch_all()
ok("GB: fetch_all() returns an empty collection with a note, and calls nothing",
   fa["features"] == [] and fa.get("note") == restrictions.NO_PROVIDER_NOTE)
sc = restrictions.store_checks()
ok("GB: stored checks record no_provider, not unavailable", sc["status"] == "no_provider" and sc["routes"] == 18, str(sc))
ok("GB: no automatic diesel index", fuel.auto_available("GB") is False and m3["tenant"]["fuel_index_auto"] is False)
rs = fuel.refresh("GB", sync=True)
ok("GB: refresh() declines to fetch and says so", rs["status"] == "manual_only", str(rs))
ok("GB: the typed index from the package is readable", (fuel.get_index("GB") or {}).get("source") == fuel.SOURCE_MANUAL)
ok("EE: the provider exists and the bulletin covers it",
   fuel.auto_available("EE") is True and restrictions.PROVIDER["country"] == "EE")
doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
doc["tenant"]["country"] = "EE"
config.save(doc, by="test"); config.invalidate()
ok("EE tenant: the provider switches on", restrictions.enabled() is True and main.restriction_layers()["provider"]["short"] == "Tark Tee")
map_src = read("map/index.html")
ok("the map hides the restriction panel until the API names a provider",
   'id="restrictions-group" hidden' in map_src and "cat.provider" in map_src)
ok("the map no longer hard-codes the Estonian authority in its panel",
   "Estonian Transport Administration" not in map_src.split("<script>")[0])
ok("...nor in the restriction popup — the attribution is the provider the API named",
   "Estonian Transport Administration" not in map_src and "RESTR.provider = cat.provider;" in map_src
   and "const pvd = RESTR.provider || {};" in map_src)

# =========================================================================== #
#  7. The overlay endpoint                                                     #
# =========================================================================== #
boot()
r0 = main.public_alignment(_Request())
b0 = json.loads(r0.body)
ok("no overlay → {} plus the tenant block and its (empty) team names",
   set(b0.keys()) == {"tenant", "teams"} and b0["teams"] == [] and r0.headers.get("ETag"))
tenant_package.set_overlay(ovl, by="test")
r1 = main.public_alignment(_Request())
b1 = json.loads(r1.body)
ok("with an overlay → bands, alignment, view and the tenant", b1["version"] == ovl["version"] and "tenant" in b1 and b1["view"] == ovl["view"])
r2 = main.public_alignment(_Request({"If-None-Match": r1.headers["ETag"]}))
ok("a matching If-None-Match gets 304", r2.status_code == 304)
ok("the map fetches the overlay once and waits for it in style.load",
   "OVERLAY_READY = (async () =>" in map_src and "await OVERLAY_READY;" in map_src
   and "/public/alignment" in map_src and "applyOverlayPackage(o)" in map_src)
ok("the map loads overlay.js, not the old data files",
   'src="overlay.js' in map_src and "data/alignment.js" not in map_src and "ipt_segments.js?v" not in map_src)
ov_src = read("map/overlay.js")
ok("overlay.js ships empty defaults and reads the globals at call time",
   "window.IPT_SEGMENTS = window.IPT_SEGMENTS || [];" in ov_src and "window.applyOverlayPackage = function" in ov_src)
ok("overlay.js computes the grid scale from the data's latitude, not a constant",
   "LON_SCALE = Math.max(0.2, Math.cos(" in ov_src)

# =========================================================================== #
#  8. Theme tokens                                                             #
# =========================================================================== #
OLD = ("#003787", "#0A1446", "#3398DB", "#BF2E55", "#039E86", "#FFC101")
NEW = ("#0F172A", "#2563EB")
for rel in ("frontend/index.html", "map/index.html", "map/config.js", "frontend/help/index.html"):
    src = read(rel)
    ok(f"{rel}: none of the old palette", not any(h.lower() in src.lower() for h in OLD),
       str([h for h in OLD if h.lower() in src.lower()]))
    ok(f"{rel}: the Modus ink and accent", all(h.lower() in src.lower() for h in NEW))
for rel in ("backend/export.py",):
    src = read(rel)
    ok(f"{rel}: none of the old palette", not any(h.lower() in src.lower() for h in OLD))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
