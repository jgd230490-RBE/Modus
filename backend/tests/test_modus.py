"""
G2, 2026-09-16 — Wayscope (Modus until 29 Sep 2026): a product with no project data in it,
and a tenant package.

WHAT IS ASSERTED
----------------
  1. The tree ships NOTHING of the first project's: no seed data, no static alignment,
     no project names in any shipped file (source-level, every file outside tests/).
  2. A fresh tenant boots EMPTY — generic disciplines and the factors row only.
  3. /api/meta carries the tenant block; the defaults are Wayscope / Team / EUR / no country.
  4. The tenant package: export → import into an empty tenant round-trips every row;
     a non-empty tenant refuses without replace; a bad package is refused; an unknown
     column is dropped and reported; the boot seeds are superseded by the package's.
  5. The demo package (demo/uk-corridor.package.json) validates, imports, and is what
     it says: GBP, GB, invented names, 18 routes, four approved months, an overlay
     whose bands are contiguous and whose boundaries sit on band edges.
  6. Country gating (REVERSED for GB by H1, 29 Sep 2026): a GB tenant has National
     Highways' planned closures and the DESNZ diesel index; an EE tenant has Tark Tee and
     the EU bulletin; a tenant with NO country has neither. The map's restriction panel
     is provider-driven.
  7. The overlay endpoint: a tenant with no overlay gets {} + tenant; one with an
     overlay gets it back with an ETag, and a matching If-None-Match gets 304.
  8. Theme tokens: the shipped pages carry the Wayscope palette (ink #1F2024, blue
     #2563EB) and none of the old RBE palette, nor the retired G2 ink #0F172A.
  9. Rebrand (29 Sep 2026): the word "Modus" appears in NO shipped file; the brand files
     the pages reference exist under frontend/brand/; the favicon set is served at the
     root; the header carries the lockup and no longer the old caption.

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
# instructions), so one may exist — but only a Wayscope delivery note, never an older one
# (the prefix changed from "MODUS — " to "WAYSCOPE — " with the 29 Sep rebrand).
_rt = os.path.join(ROOT, "README.txt")
ok("no stale root-level README.txt — if present it is a Wayscope delivery note",
   not os.path.exists(_rt) or open(_rt, encoding="utf-8").read().startswith("WAYSCOPE — "))
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
ok("defaults: Wayscope / Team / EUR / no country",
   t.get("name") == "Wayscope" and t.get("team_label") == "Team" and t.get("currency") == "EUR"
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
# NARROWED 5 Oct 2026 (demo v2, H2): 74 lines — 72 Approved plus one Pending and one Rejected
# so the approval step can be shown live; 14 gates, 5 zones, 6 haul-road links are new.
ok("demo: 11 locations, 18 routes, 3 teams, 8 sections, 74 forecasts (72 approved + 1 pending + 1 rejected), 14 gates, 5 zones, 6 haul links",
   dc["locations"] == 11 and dc["routes"] == 18 and dc["ipts"] == 3 and dc["work_sections"] == 8 and dc["forecasts"] == 74
   and dc["location_gates"] == 14 and dc["zones"] == 5 and dc["route_haul_roads"] == 6, str(dc))
_st = {s_: sum(1 for r in demo["tables"]["forecasts"] if r["status"] == s_) for s_ in ("Approved", "Pending", "Rejected")}
ok("demo: 72 Approved, exactly one Pending and one Rejected (with a reason)",
   _st == {"Approved": 72, "Pending": 1, "Rejected": 1}
   and all(r["reject_reason"] for r in demo["tables"]["forecasts"] if r["status"] == "Rejected"), str(_st))
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

# --- 5a-bis. Postgres booleans (29 Sep 2026: the first demo import on Render) ---------
# `psycopg2.errors.DatatypeMismatch: column "in_scope" is of type boolean but expression
# is of type integer`. SQLite hands BOOLEAN columns back as 0/1 and accepts them again,
# so every harness passed while Postgres refused the package. The importer now binds by
# the LIVE column type; these pin that, on the shipped demo package itself.
_cur = db.get_conn().cursor()
_types = db._column_types_of(_cur, "disciplines")
ok("🔴 db._column_types_of reads the declared types (BOOLEAN on SQLite)",
   _types.get("in_scope", "").startswith("BOOL") and _types.get("active", "").startswith("BOOL")
   and _types.get("sort_order", "").startswith("INT") and _types.get("label", "") == "TEXT", str(_types))
ok("🔴 the demo package still carries its booleans as 0/1 — the regression fixture",
   all(isinstance(r["in_scope"], int) and not isinstance(r["in_scope"], bool) for r in demo["tables"]["disciplines"]))
_bool_cols = {"disciplines": ("in_scope", "active"), "ipts": ("active",), "work_sections": ("in_scope", "active"),
              "zones": ("affects_routing", "active"), "location_gates": ("is_default", "active")}
_bad = []
for _t, _cols in _bool_cols.items():
    _tt = db._column_types_of(_cur, _t)
    for _c in _cols:
        if not _tt.get(_c, "").startswith("BOOL"):
            _bad.append(f"{_t}.{_c}={_tt.get(_c)}")
ok("🔴 every boolean column the schema declares is seen as BOOLEAN", not _bad, str(_bad))
_bound = []
for _t, _cols in _bool_cols.items():
    _tt = db._column_types_of(_cur, _t)
    for _r in demo["tables"].get(_t) or []:
        _cs = [c for c in _r.keys() if c in _tt and c != "tenant_id"]
        _vals = dict(zip(_cs, tenant_package._bind(_r, _cs, _tt)))
        _bound += [(_t, _c, _vals[_c]) for _c in _cols if _c in _vals and not (_vals[_c] is None or isinstance(_vals[_c], bool))]
ok("🔴 every 0/1 in the demo's boolean columns is bound as a Python bool", not _bound, str(_bound[:5]))
ok("_coerce: ints, floats, words and bools all read as bool; None stays None",
   tenant_package._coerce(1, "BOOLEAN") is True and tenant_package._coerce(0, "BOOLEAN") is False
   and tenant_package._coerce(1.0, "boolean".upper()) is True and tenant_package._coerce("false", "BOOLEAN") is False
   and tenant_package._coerce("t", "BOOLEAN") is True and tenant_package._coerce(True, "BOOLEAN") is True
   and tenant_package._coerce(None, "BOOLEAN") is None)
ok("_coerce: a non-boolean column is untouched (1 stays an int, a dict becomes JSON text)",
   tenant_package._coerce(1, "INTEGER") == 1 and not isinstance(tenant_package._coerce(1, "INTEGER"), bool)
   and tenant_package._coerce({"a": 1}, "TEXT") == '{"a": 1}' and tenant_package._coerce("x", "") == "x")
try:
    tenant_package._coerce("maybe", "BOOLEAN")
    ok("_coerce: a word that is not a boolean is refused, not guessed", False)
except ValueError as e:
    ok("_coerce: a word that is not a boolean is refused, not guessed", "not a boolean" in str(e), str(e))
_pkg_bad = json.loads(json.dumps(demo))
_pkg_bad["tables"]["disciplines"][0]["in_scope"] = "maybe"
try:
    boot(); tenant_package.import_tenant(_pkg_bad)
    ok("import_tenant: a bad boolean names the table, row and column", False)
except ValueError as e:
    ok("import_tenant: a bad boolean names the table, row and column",
       "table disciplines, row 1: column in_scope" in str(e), str(e))
_after = db.query("SELECT COUNT(*) AS n FROM locations WHERE tenant_id = ?", (db.current_tenant(),))[0]["n"]
ok("import_tenant: …and the refused import wrote nothing (rolled back whole)", _after == 0, str(_after))
_src_main = read("backend/main.py")
ok("🔴 POST /api/admin/tenant/import turns a database error into a 500 WITH the reason, not a bare Internal Server Error",
   "import failed and was rolled back" in _src_main
   and _src_main.index("except Exception as e:\n        # 29 Sep 2026: the first import on Render") > _src_main.index("def tenant_import("))
boot()
out3 = tenant_package.import_tenant(demo)
ok("demo: imports again after the refused package (the tenant was left clean)", out3["ok"], str(out3)[:200])
config.invalidate()
m3 = main.meta()

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
# NARROWED (H1, 29 Sep): the code word comes from _flag_label(f), which reads the
# provider's word off a RESTRICTION flag (TARK TEE / ROADWORKS) and FLAG_LABEL otherwise.
ok("export: the Clashes sheet and the PDF name the codes and the teams",
   "code=_flag_label(f), ipt=_nm(f.get(\"ipt\")), text=_nm(f.get(\"text\"))" in read("backend/export.py")
   and "{_flag_label(f)}: {_nm(f['text'])}" in read("backend/export.py")
   and export.FLAG_LABEL["IPT_SHARE"] == "SHARE"
   and export._flag_label({"code": "RESTRICTION", "label": "ROADWORKS"}) == "ROADWORKS"
   and export._flag_label({"code": "RESTRICTION", "label": "TARK TEE"}) == "TARK TEE"
   and export._flag_label({"code": "IPT_SHARE"}) == "SHARE" and "TARK_TEE" not in export.FLAG_LABEL)
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
# NARROWED (H1, 29 Sep): the word comes from flagWord(f) — RAIL_LABEL, or the provider's own
# word off a RESTRICTION flag ("TARK TEE" / "ROADWORKS")
ok("frontend: the clash rail shows the code's name (the provider's for a restriction) and the teams' names",
   "{flagWord(f)}</span> {teamText(f.text)}" in fe_src and 'IPT_SHARE: "SHARE"' in fe_src
   and 'const flagWord = (f, table) => (f && f.code === "RESTRICTION" && f.label) ? f.label : ((table || RAIL_LABEL)[f.code] || f.code);' in fe_src
   and "{f.code}</span> {f.text}" not in fe_src and 'TARK_TEE: "TARK TEE"' not in fe_src)
ok("frontend: the map entry is not called public — the map is behind the gate",
   '{ id: "map", label: "Route map"' in fe_src and "Back to public map" not in fe_src and 'label: "Public route map"' not in fe_src)
ok("frontend: a long KPI value steps its size down rather than being cut off, and says itself on hover",
   '(len > 12 ? "text-sm" : len > 9 ? "text-base" : len > 7 ? "text-lg" : "text-2xl")' in fe_src
   and 'data-fuel-widget="compact" title={hasIndex ? String(price) : ""}' in fe_src)
# NARROWED (H1): "published" rather than "bulletin" — the GB series is not a bulletin
ok("frontend: a typed diesel price is dated as typed, a fetched one as published",
   '${autoIdx && idx.source !== "manual" ? "published" : "typed"} ${fuelDate(idx.bulletin_date)}' in fe_src)
ok("frontend: no team value is rendered raw in a cell or an option",
   "{r.ipt}</td>" not in fe_src and "{r.ipt || \"—\"}</td>" not in fe_src
   and "value={i}>{i}</option>" not in fe_src and "{route.ipt || \"—\"}" not in fe_src
   and "chip(g.ipt)" not in fe_src and "g.yearLabel, g.ipt," not in fe_src)

# =========================================================================== #
#  6. Country gating                                                           #
# =========================================================================== #
restrictions.COUNTRY_OVERRIDE = None
# REVERSED (H1, 29 Sep 2026): under G2 a GB tenant had NO restriction provider and NO
# automatic diesel index. H1 gives GB National Highways' planned closures and the DESNZ
# weekly price. The no-country case keeps the G2 behaviour (asserted in §3 above).
ok("GB (H1): the restriction provider is National Highways, flag word ROADWORKS, 100 m match",
   restrictions.enabled() is True and restrictions.provider()["key"] == "nh_closures"
   and restrictions.provider()["short"] == "National Highways" and restrictions.provider()["flag_label"] == "ROADWORKS"
   and restrictions.match_m() == 100.0 and restrictions.provider()["dated"] is True)
lay = main.restriction_layers()
ok("GB (H1): /api/restrictions/layers names the provider and ONE layer, planned road closures",
   lay["provider"]["key"] == "nh_closures" and [l["key"] for l in lay["layers"]] == ["nh_closures"]
   and lay["match_m"] == 100.0 and "Open Government Licence" in lay["attribution"], str(lay)[:200])
ok("GB (H1): the tenant block on /api/meta carries the provider block and the distance unit",
   m3["tenant"]["restrictions_provider"] is True and m3["tenant"]["restrictions"]["key"] == "nh_closures"
   and m3["tenant"]["distance_unit"] in ("km", "mi"))
# the NH feed, stubbed: two pages, an ended closure, a live one and a future one
_nh_calls = []
def _fake_nh_page(offset, count=restrictions.NH_PAGE, timeout=None):
    _nh_calls.append(offset)
    import time as _t
    day = 86400000
    now_ms = int(_t.time() * 1000)
    feats = []
    if offset == 0:
        feats = [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.9, 52.5], [-0.89, 52.51]]},
             "properties": {"OBJECTID": 1, "description": "Carriageway closure for resurfacing", "road_number": "A46",
                            "eventtype": "Carriageway closure", "natureofworks": "Resurfacing", "formattedeventnumber": "NH-0001",
                            "scheduledplannedstartdate": now_ms - 40 * day, "scheduledplannedenddate": now_ms - 30 * day}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.9, 52.5], [-0.89, 52.51]]},
             "properties": {"OBJECTID": 2, "description": "Lane closure", "road_number": "A46",
                            "eventtype": "Lane closure", "natureofworks": "Barrier works", "formattedeventnumber": "NH-0002",
                            "scheduledplannedstartdate": now_ms - 2 * day, "scheduledplannedenddate": now_ms + 5 * day}},
        ]
        return {"type": "FeatureCollection", "features": feats, "exceededTransferLimit": True}
    feats = [
        {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[-1.2, 52.7], [-1.19, 52.71]]]},
         "properties": {"OBJECTID": 3, "description": "Full closure", "road_number": "M1",
                        "eventtype": "Full closure", "natureofworks": "Bridge works", "formattedeventnumber": "NH-0003",
                        "scheduledplannedstartdate": now_ms + 20 * day, "scheduledplannedenddate": now_ms + 22 * day}},
    ]
    return {"type": "FeatureCollection", "features": feats}
_orig_nh_page = restrictions._nh_page
restrictions._nh_page = _fake_nh_page
restrictions.clear_cache()
try:
    fa = restrictions.fetch_all()
    ok("GB (H1): fetch_all() pages the FeatureServer (offset 0, then 2) and reads exceededTransferLimit",
       _nh_calls == [0, 2] and fa.get("pages") == 2 and fa["provider"] == "nh_closures", str(_nh_calls))
    ok("GB (H1): an ENDED closure is dropped, a live and a FUTURE one are kept (the look-ahead needs the future)",
       fa["total_records"] == 3 and len(fa["features"]) == 2 and fa["expired_or_future"] == 1
       and {f["properties"]["event_number"] for f in fa["features"]} == {"NH-0002", "NH-0003"})
    _p2 = next(f["properties"] for f in fa["features"] if f["properties"]["event_number"] == "NH-0002")
    ok("GB (H1): the published field names map to this module's (dates as ISO, road number, kind nh_closures)",
       _p2["_kind"] == "nh_closures" and _p2["road_nr"] == "A46" and _p2["_from"] and _p2["_to"]
       and _p2["_from"] < _p2["_to"] and _p2["_label"] == "Planned road closures" and _p2["_colour"] == "#DC2626"
       and _p2["_in_force"] is True and "_raw" not in _p2)     # the raw record is the probe's, not the map's
    ok("GB (H1): the headline leads with 'Planned closure', the road and the dates",
       _p2["_headline"].startswith("Planned closure · A46") and _p2["_from"] in _p2["_headline"])
    ok("GB (H1): a closure is never judged as a dimension limit — verdict unknown with the closure note",
       restrictions.assess(_p2, "Rigid 8-wheeler (32t)")["verdict"] == "unknown"
       and "planned closure" in restrictions.assess(_p2, "Rigid 8-wheeler (32t)")["note"])
    # a baked route along the A46 closure (within 100 m) and one far away
    db.execute("DELETE FROM route_geometry WHERE tenant_id = ?", (db.current_tenant(),))
    _rid = db.query("SELECT id FROM routes WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
    _r1, _r2 = _rid[0]["id"], _rid[1]["id"]
    network._upsert_geom(_r1, "Rigid 8-wheeler (32t)", "[[-0.905,52.499],[-0.8955,52.5052],[-0.885,52.515]]", 2.0, 0.1, None, leg="loaded", alt_index=0)
    network._upsert_geom(_r2, "Rigid 8-wheeler (32t)", "[[-1.5,52.9],[-1.45,52.95]]", 5.0, 0.2, None, leg="loaded", alt_index=0)
    cr = restrictions.check_route(_r1, _fc=fa)
    ok("GB (H1): a route running along the closure gets the hit within 100 m, with its dates and event number",
       cr["baked"] and len(cr["hits"]) == 1 and cr["hits"][0]["event_number"] == "NH-0002"
       and cr["hits"][0]["from"] and cr["hits"][0]["to"] and cr["hits"][0]["distance_m"] <= 100
       and cr["match_m"] == 100.0 and cr["flag_label"] == "ROADWORKS" and cr["hits"][0]["severity"] == "warn", str(cr["hits"])[:300])
    ok("GB (H1): a route far from every closure has no hit", restrictions.check_route(_r2, _fc=fa)["hits"] == [])
    sc = restrictions.store_checks()
    ok("GB (H1): store_checks() runs against National Highways and stores ONE hit",
       sc["status"] == "ok" and sc["hits"] == 1 and sc["features_checked"] == 2, str(sc))
    ok("GB (H1): the stored hit keeps its from/to for the rail's week test",
       restrictions.stored_checks([_r1])[_r1]["hits"][0].get("from") is not None)
    dg = restrictions.diagnostics(probe=True)
    ok("GB (H1): the probe shows the raw property names, the mapped dates and the paging flag",
       dg["provider"]["key"] == "nh_closures" and dg["probe"]["records_returned"] == 2
       and "scheduledplannedstartdate" in dg["probe"]["sample_property_names"] and dg["probe"]["sample_dates"]["from"]
       and dg["probe"]["reading"].startswith("field map found") and dg["field_map"]["scheduledplannedenddate"] == "date_to")
finally:
    restrictions._nh_page = _orig_nh_page
    restrictions.clear_cache()
ok("GB (H1): the automatic diesel index is DESNZ", fuel.auto_available("GB") is True and m3["tenant"]["fuel_index_auto"] is True
   and m3["tenant"]["fuel_provider"]["key"] == "desnz")
_orig_desnz = fuel.fetch_desnz
fuel.fetch_desnz = lambda timeout=None: (_ for _ in ()).throw(OSError("gov.uk unreachable from the sandbox"))
rs = fuel.refresh("GB", sync=True)
fuel.fetch_desnz = _orig_desnz
ok("GB (H1): a failed DESNZ fetch keeps the typed row and says why (never a 500, never a zero)",
   rs["status"] == "unavailable" and "unreachable" in (rs.get("error") or "")
   and (fuel.get_index("GB") or {}).get("last_error"), str(rs))
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
# 29 Sep 2026: the G2 ink #0F172A is RETIRED with the rebrand (ink is #1F2024 now) — it
# joins the old list because a grep showed it gone from every shipped file.
OLD = ("#003787", "#0A1446", "#3398DB", "#BF2E55", "#039E86", "#FFC101", "#0F172A")
NEW = ("#1F2024", "#2563EB")
for rel in ("frontend/index.html", "map/index.html", "map/config.js", "frontend/help/index.html"):
    src = read(rel)
    ok(f"{rel}: none of the old palette", not any(h.lower() in src.lower() for h in OLD),
       str([h for h in OLD if h.lower() in src.lower()]))
    ok(f"{rel}: the Wayscope ink and accent", all(h.lower() in src.lower() for h in NEW))
for rel in ("backend/export.py",):
    src = read(rel)
    ok(f"{rel}: none of the old palette", not any(h.lower() in src.lower() for h in OLD))

# =========================================================================== #
#  9. The rebrand (29 Sep 2026): Modus → Wayscope, everywhere a person can read it  #
# =========================================================================== #
# The "references are gone" assertion, same shape as PROJECT_TERMS: the old product name
# must not appear in ANY shipped file — code, comments and docstrings included — so that
# `grep -rn Modus` on the tree returns nothing. Test files are excluded by the walker
# (they may quote the history), and so is the root README.txt: it is the delivery note,
# which has to SAY what was renamed. Its own rule (the WAYSCOPE — prefix) is asserted above.
# The Render service names `modus-web` / `modus-db` and the `modus_*` cookie/storage
# keys are lower-case identifiers, kept on purpose, and do not match \bModus\b.
_modus_hits = {}
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "tests", "node_modules")]
    for fn in files:
        if not fn.endswith(SHIPPED_EXT + (".css", ".webmanifest", ".svg")):
            continue
        p = os.path.join(dirpath, fn)
        if os.path.relpath(p, ROOT) == "README.txt":
            continue
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        n = len(re.findall(r"\bModus\b", txt))
        if n:
            _modus_hits[os.path.relpath(p, ROOT)] = n
ok("🔴 REBRAND: the word \"Modus\" appears in no shipped file (code, comments, docstrings)",
   not _modus_hits, str(_modus_hits))

# the brand files the pages and main.py reference must ship
BRAND = os.path.join(ROOT, "frontend", "brand")
BRAND_REFERENCED = ("logo-header-on-dark.svg", "logo-stacked-on-dark.svg", "theme-tokens.css",
                    "favicon.ico", "favicon.svg", "apple-touch-icon.png", "site.webmanifest",
                    "icon-192.png", "icon-512.png", "icon-512-maskable.png")
_missing_brand = [f for f in BRAND_REFERENCED if not os.path.isfile(os.path.join(BRAND, f))]
ok("frontend/brand/ ships every file the pages reference (%d)" % len(BRAND_REFERENCED),
   os.path.isdir(BRAND) and not _missing_brand, str(_missing_brand))
if os.path.isfile(os.path.join(BRAND, "site.webmanifest")):
    _man = json.load(open(os.path.join(BRAND, "site.webmanifest"), encoding="utf-8"))
    _icon_srcs = [i.get("src", "") for i in _man.get("icons", [])]
    ok("the web manifest's icon paths are root-relative and every one has a root route in main.py",
       _icon_srcs and all(s.startswith("/") and s.lstrip("/") in main.ROOT_BRAND_FILES for s in _icon_srcs),
       str(_icon_srcs))
    ok("...and the manifest names Wayscope with the ink theme colour",
       "Wayscope" in (_man.get("name") or "") and (_man.get("theme_color") or "").upper() == "#1F2024", str(_man))

# main.py: the mount and the root routes
ok("main.py mounts /brand with the no-cache static class, before the \"/\" route",
   'app.mount("/brand", NoCacheStatic(directory=str(BRAND_DIR), check_dir=False)' in main_code
   and main_code.index('app.mount("/brand"') < main_code.index('@app.get("/")\ndef frontend_index'))
ok("main.py serves the favicon set and the manifest at the ROOT (browsers and iOS ask there)",
   set(main.ROOT_BRAND_FILES) == {"favicon.ico", "favicon.svg", "apple-touch-icon.png", "site.webmanifest",
                                   "icon-192.png", "icon-512.png", "icon-512-maskable.png"}
   and 'for _name in list(ROOT_BRAND_FILES):' in main_code and 'app.get("/" + _name' in main_code)
try:
    main._brand_file("../factors.json"); _esc = False
except Exception as e:
    _esc = getattr(e, "status_code", None) == 404
ok("a root brand route refuses a name outside the set with 404 ('../factors.json' cannot escape)", _esc)
import gate as _gate
ok("the gate does not police /brand/ or the root favicon paths (a refused visitor still sees the logo)",
   all(_gate.scope_for(p) is None for p in ("/brand/logo-header-on-dark.svg", "/favicon.ico", "/favicon.svg",
                                             "/site.webmanifest", "/apple-touch-icon.png")))
ok("the three gate pages are titled Wayscope, carry the stacked logo, and no RBE-era wording",
   all(("<title>Wayscope — " in pg and 'src="/brand/logo-stacked-on-dark.svg"' in pg
        and "alliance" not in pg.lower() and "Modus" not in pg)
       for pg in (main._MAP_PASSWORD_PAGE, main._HELP_SIGNIN_PAGE, main._MAP_UNCONFIGURED_PAGE)))
ok("...and the gate pages use the Wayscope ink, not the RBE navy",
   "background:#1F2024" in main._GATE_CSS and not any(h.lower() in main._GATE_CSS.lower() for h in OLD))
ok("FastAPI's app title is Wayscope", 'FastAPI(title="Wayscope"' in main_code)

# the staff app: head links, tokens, the header
_ICON_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="32x32">',
               '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
               '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
               '<link rel="manifest" href="/site.webmanifest">')
for rel in ("frontend/index.html", "map/index.html", "frontend/help/index.html"):
    src = read(rel)
    ok(f"{rel}: <head> carries the favicon links and the ink theme-color",
       all(l in src for l in _ICON_LINKS) and '<meta name="theme-color" content="#1F2024">' in src)
ok("the staff app's :root carries the ink and the brand orange tokens (orange = brand accent only)",
   "--navy-deep:#1F2024" in fe_src and "--brand-orange:#FF8C14" in fe_src and "--brand-gold:#D2931F" in fe_src)
ok("...amber is still the warning colour (--gold #D97706 untouched)", "--gold:#D97706" in fe_src)
ok("the header carries the lockup image and the 2 px orange rule, and the old gold bar + caption are gone",
   'src="/brand/logo-header-on-dark.svg"' in fe_src and "border-bottom:2px solid var(--brand-orange)" in fe_src
   and "Forecasting &amp; Route Map" not in fe_src and 'style={{background:"var(--gold)"}}' not in fe_src)
ok("the header shows the tenant's name beside the rule only when it is not the default",
   'TENANT.name && TENANT.name !== "Wayscope" && (' in fe_src and 'className="brand-rule hidden sm:block"' in fe_src)
ok("document.title: the tenant's name · Wayscope, plain Wayscope for the default tenant",
   'document.title = (TENANT.name && TENANT.name !== "Wayscope") ? TENANT.name + " · Wayscope" : "Wayscope";' in fe_src)
ok("the map's brand ink is #1F2024 and overlay.js reserves it (no band may reuse it)",
   'brandDark:         "#1F2024"' in read("map/config.js") and "'#1F2024'," in ov_src and "#0F172A" not in ov_src)
ok("the map's forecast routes stay BLUE (decision 29 Sep: orange would blur with amber warnings)",
   'brand:             "#2563EB"' in read("map/config.js") and 'forecast:          "#3B82F6"' in read("map/config.js")
   and "#FF8C14" not in read("map/config.js"))
_help = read("frontend/help/index.html")
# NARROWED (29 Sep): the nav names the product as TEXT until the brand SVG is in the repo
# (frontend/brand/logo-header-on-dark.svg — delivered separately, not yet applied); then it
# is inlined (data-brand="svg"), never fetched, so the guide keeps pulling in nothing.
_navb = _help.split('<div class="brand"', 1)[1][:6000] if '<div class="brand"' in _help else ""
ok("the guide's nav names Wayscope — the inline lockup (no new fetch) or, until the SVG ships, the word — and the intro says Wayscope",
   '<div class="brand"' in _help and ("<svg" in _navb or _navb.startswith(' data-brand="text">Wayscope'))
   and "Wayscope is a shared planning platform" in _help and "Modus" not in _help)
ok("exports: the default tenant name and the User-Agent are Wayscope, the PDF ink is #1F2024",
   'or "Wayscope"' in _exp_src and '"User-Agent": "Wayscope/1.0"' in _exp_src and 'NAVY = "1F2024"' in _exp_src)
ok("restrictions: the User-Agent is Wayscope", '"User-Agent": "Wayscope/1.0"' in read("backend/restrictions.py"))
ok("the seed's tenant name and config.TENANT_DEFAULTS are Wayscope",
   json.load(open(os.path.join(ROOT, "backend", "factors.json"), encoding="utf-8"))["tenant"]["name"] == "Wayscope"
   and config.TENANT_DEFAULTS["name"] == "Wayscope")

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
