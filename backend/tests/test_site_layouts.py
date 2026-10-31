"""
Site layouts, PR 1 (31 Oct 2026, task 4c; plan notes site-layouts-plan-1030.md §8): the style table, the drawings
brought in (DXF on National Grid and on a site grid, KML, KMZ, GeoJSON, shapefile zip), the survey-point fit, the
"in the file -> becomes" table saved per organisation, placing on a phase, the phases (months, rename, delete, the
version check), the staff Route map's read, the organisation file, the refusals in plain words.

The six sample drawings in fixtures/site_layouts/ are ONE fictional contractor's logistics plan for the demo's Tilton
Viaduct site (L019), written by backend/tools/make_site_layout_samples.py around the demo's own gates. The mockup
measured them (40 of 40 from the National Grid DXF with Gate 1 0.00 m from G020; 32 of 32 from the others; the
site-grid fit turn 27.61°, scale 1.0003, worst miss 0.01 m) and this harness holds the build to the same figures.

31 Oct 2026 (PR 1b, plan §6 revised): two contractor-style drawings (fixtures contractor-style-mm.dxf and
contractor-style-r12-unitless.dxf, written by backend/tools/make_contractor_style.py): units scaled or worked out,
the leave-outs counted, block footprints, attribute labels, holes (section 2b).

31 Oct 2026 (PR 4): the public map (section 9) — the "Show on the public map" switch (planners / admins, the layout's
version), /api/public/site-layouts as an allow-list (no security / CCTV, no file name, no phase name, nothing a later
kind of thing writes), kept until the next write.

WHAT THIS DOES NOT PROVE: the screens (parse_frontend / dom_frontend / the UI audit), the Route map layer (parse_map),
Postgres, the HTTP layer (stubbed), the memory on Render (measured by hand before the merge).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_site_layouts.py
"""
import asyncio
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import types
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
FIX = os.path.join(HERE, "fixtures", "site_layouts")
sys.path.insert(0, BACKEND)

# --- the same stubs every backend harness uses (no FastAPI in .venv-tests) -------------------------------------------
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
    def __init__(self, status_code, detail="", headers=None):
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
    def __init__(self, headers=None, body=b"", cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = cookies or {}

    async def stream(self):
        for i in range(0, len(self._body), 65536):
            yield self._body[i:i + 65536]


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

TMP = tempfile.mkdtemp(prefix="rbe_layouts_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import limits  # noqa: E402
import tenant_package  # noqa: E402
import site_layouts as SL  # noqa: E402
import site_layout_import as SI  # noqa: E402
import site_layout_styles as ST  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"


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


def fx(name):
    return open(os.path.join(FIX, name), "rb").read()


def metres(a, b):
    return SI.metres(a, b)


# the demo's own records for L019 (read only), the site the samples were drawn round
PKG = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
L019 = next(r for r in PKG["tables"]["locations"] if r["id"] == "L019")
GATES = [g for g in PKG["tables"]["location_gates"] if g["location_id"] == "L019"]
G020 = next(g for g in GATES if g["id"] == "G020")
G021 = next(g for g in GATES if g["id"] == "G021")
NEAR = [[L019["lon"], L019["lat"]]]

# =========================================================================== #
#  0. The style table                                                          #
# =========================================================================== #
ok("0. 11 line styles, 10 area styles, 31 symbols, 8 layers",
   (len(ST.LINE_STYLES), len(ST.AREA_STYLES), len(ST.SYMBOLS), len(ST.LAYERS)) == (11, 10, 31, 8),
   str((len(ST.LINE_STYLES), len(ST.AREA_STYLES), len(ST.SYMBOLS), len(ST.LAYERS))))
ok("0. every symbol key once, each an SVG in a 64 box with a size in metres and a group the layers know",
   len(ST.SYMBOL_KEYS) == 31 and all(s["svg"].strip().startswith("<") and s["size"] > 0 and s["group"] in ST.SYMBOL_LAYER
                                     for s in ST.SYMBOLS))
ok("0. every line style sits on one of the eight layers; every colour is #RRGGBB",
   all(v["layer"] in ST.LAYERS and re.fullmatch(r"#[0-9A-F]{6}", v["color"]) for v in ST.LINE_STYLES.values())
   and all(re.fullmatch(r"#[0-9A-F]{6}", v["color"]) and v["fill"] in ST.FILLS and v["outline"] in ST.OUTLINES
           for v in ST.AREA_STYLES.values()))
ok("0. the import table offers 11 + 10 + 31 + text + leave out = 54 choices", len(ST.choices()) == 54
   and "skip" in ST.choices() and "text" in ST.choices() and not ST.choice_ok("line:flying") and not ST.choice_ok(None))
ok("0. security and CCTV are the two symbols never on the public map (Q7)",
   set(ST.PRIVATE_SYMBOLS) == {"security", "cctv"} and all(k in ST.SYMBOL_KEYS for k in ST.PRIVATE_SYMBOLS))
P = ST.payload()
ok("0. the payload the page reads carries the layers, lines, areas, symbols, glyphs and the choices with their words",
   {"layers", "lines", "areas", "symbols", "glyphs", "choices", "fills", "private_symbols"} <= set(P)
   and len(P["choices"]) == 54 and all(c.get("label") for c in P["choices"]), str(sorted(P)))
# NARROWED 31 Oct 2026 (PR 1b, plan §6 revised): a drainage layer is now guessed "leave out" (the mockup's LAYER_WORDS);
# an unknown layer is still an imported line (C-SETTING-OUT)
ok("0. guesses: a hoarding layer, a GATE block, a crane radius, a drainage layer (leave out), a text layer, an unknown line",
   ST.guess("C-HOARDING", {"LineString"}) == "line:hoarding" and ST.guess("block GATE", {"Point"}) == "sym:gate"
   and ST.guess("C-CRANE-RADIUS", {"Polygon"}) == "area:crane_radius" and ST.guess("C-DRAINAGE", {"LineString"}) == "skip"
   and ST.guess("C-TEXT", {"Text"}) == "text" and ST.guess("C-SETTING-OUT", {"LineString"}) == "line:imported")
ok("0. guesses from a contractor's words: lifting zone, office, canteen, walkway, banksman, muster point, 5 mph",
   ST.guess("TW_LIFTING ZONE", {"Polygon"}) == "area:exclusion" and ST.guess("TW_SITE OFFICE", {"Polygon"}) == "area:welfare"
   and ST.guess("TW_CANTEEN", {"Polygon"}) == "area:welfare" and ST.guess("TW_WALKWAY", {"LineString"}) == "line:ped"
   and ST.guess("block BANKSMAN", {"Point"}) == "sym:marshal" and ST.guess("block MUSTER_PT", {"Point"}) == "sym:assembly"
   and ST.guess("block SIGN_5MPH", {"Point"}) == "sym:speed5")
ok("0. existing and survey layers are left out, even their words (EX_, SV_, levels)",
   ST.guess("EX_DRAINAGE", {"LineString"}) == "skip" and ST.guess("SV_LEVELS", {"Text"}) == "skip"
   and ST.guess("SV_TOP OF BANK", {"LineString"}) == "skip" and ST.guess("EXISTING SERVICES", {"LineString"}) == "skip")
ok("0. a block footprint's outline row is guessed from its name as an area; a block that carries words is text",
   ST.guess("outline WELFARE_UNIT_32x10", {"Polygon"}) == "area:welfare" and ST.guess("block GATE_TAG", {"Point"}) == "text")

# =========================================================================== #
#  1. The grid and the six samples                                             #
# =========================================================================== #
GRID = os.path.join(BACKEND, "data", "proj", SI.GRID_FILE)
ok("1. the OSTN15 grid ships in backend/data/proj, the file PROJ-data published (sha256)",
   os.path.isfile(GRID) and hashlib.sha256(open(GRID, "rb").read()).hexdigest()
   == "5d6ed64d2119952c4c559fa1fccbc594b6520fc3ec3ef2fc10be13202c4384fa")
ok("1. its licence is written beside it (OS, 2-Clause BSD)",
   "2-Clause BSD" in open(os.path.join(BACKEND, "data", "proj", "README.md"), encoding="utf-8").read())
ok("1. the import is ready only with the grid in place", SI.grid_ready())

R = {}
for f in ("tilton-logistics-bng.dxf", "tilton-logistics.kml", "tilton-logistics.kmz", "tilton-logistics.geojson",
          "tilton-logistics-shp.zip"):
    R[f] = SI.read(fx(f), f, near=NEAR)
bng = R["tilton-logistics-bng.dxf"]
ok("1. DXF on National Grid: 40 things on 14 layers, as the mockup measured", bng["report"]["things"] == 40
   and bng["report"]["layers"] == 14 and bng["report"]["grid"] == "bng", str(bng["report"]))
ok("1. ...by OS's OSTN15 grid, named in the report (not PROJ's 2 m Helmert fallback)",
   bng["report"].get("transform") == "Inverse of British National Grid + OSGB36 to WGS 84 (9)", bng["report"].get("transform"))
first = bng["things"][0]
ok("1. ...the first haul road starts where the mockup put it (7 decimals)",
   first["geometry"]["coordinates"][0] == [-0.880001, 52.643043] and first["properties"]["width_m"] == 7.0
   and first["properties"]["color"] == "#FF7F00", str(first)[:200])
ok("1. ...the dimension and the title block are left out and said so",
   bng["report"]["left_out"].get("Dimensions") == 1
   and bng["report"]["left_out"].get("The title block and anything else in paper space") == 1, str(bng["report"]["left_out"]))
# NARROWED 31 Oct 2026 (PR 1b): the units say where they came from ("metres, from the file")
ok("1. ...units metres, the DXF version and what DXF keeps", bng["report"]["units"] == "metres, from the file"
   and bng["report"]["version"] and "Leaves out dimensions" in bng["report"]["keeps"]
   and "(with their holes)" in bng["report"]["keeps"] and "hidden layers" in bng["report"]["keeps"])
for f in ("tilton-logistics.kml", "tilton-logistics.kmz", "tilton-logistics.geojson", "tilton-logistics-shp.zip"):
    ok(f"1. {f}: 32 things on 12 layers, the haul road on the same spot",
       R[f]["report"]["things"] == 32 and R[f]["report"]["layers"] == 12
       and R[f]["things"][0]["geometry"]["coordinates"][0] == [-0.880001, 52.643043], str(R[f]["report"])[:200])
ok("1. the shapefile's .prj (British National Grid) went through the same OSTN15 transform",
   "OSGB36 to WGS 84 (9)" in R["tilton-logistics-shp.zip"]["report"]["transform"]
   and "British National Grid" in R["tilton-logistics-shp.zip"]["report"]["crs"])
ok("1. KMZ reads exactly as its KML", json.dumps(R["tilton-logistics.kmz"]["things"]) == json.dumps(R["tilton-logistics.kml"]["things"]))

rows = {r["key"]: r for r in SI.rows(bng["things"])}
ok("1. the table: one row per layer / block, each with its count and a first guess",
   rows["C-HAUL-ROAD"]["n"] == 3 and rows["C-HAUL-ROAD"]["becomes"] == "line:twoway"
   and rows["block GATE"]["n"] == 2 and rows["block GATE"]["becomes"] == "sym:gate"
   and rows["C-TEXT"]["becomes"] == "text" and rows["C-CRANE-RADIUS"]["becomes"] == "area:crane_radius"
   and rows["C-HERAS"]["kinds"] == ["LineString", "Polygon"] and len(rows) == 23, str(sorted(rows)))
krows = {r["key"]: r for r in SI.rows(R["tilton-logistics.kml"]["things"])}
ok("1. KML: folders as rows, icons as symbol rows, labels as text",
   krows["Haul roads"]["becomes"] == "line:twoway" and krows["symbol gate"]["becomes"] == "sym:gate"
   and krows["Labels"]["becomes"] == "text" and len(krows) == 20, str(sorted(krows)))
ok("1. a saved choice wins over the guess and says so",
   {r["key"]: r for r in SI.rows(bng["things"], {"C-DRAINAGE": "skip"})}["C-DRAINAGE"]["becomes"] == "skip"
   and {r["key"]: r for r in SI.rows(bng["things"], {"C-DRAINAGE": "skip"})}["C-DRAINAGE"]["saved"] is True)

gc = SI.gate_checks(bng["things"], [{"name": G020["name"], "lon": G020["lon"], "lat": G020["lat"]},
                                    {"name": G021["name"], "lon": G021["lon"], "lat": G021["lat"]}])
ok("1. the gate check: the drawing's two gates land on G020 / G021, 0.00 m", len(gc) == 2 and gc[0]["m"] <= 0.01
   and gc[1]["m"] <= 0.01 and {g["gate"] for g in gc} == {G020["name"], G021["name"]}, str(gc))

# =========================================================================== #
#  2. The site grid and the fit                                                #
# =========================================================================== #
site = SI.read(fx("tilton-logistics-site-grid.dxf"), "tilton-logistics-site-grid.dxf", near=NEAR)
ok("2. a DXF on its own grid with survey points: taken as a site grid, 40 things, three points CP1-CP3",
   site["report"]["grid"] == "site" and site["report"]["things"] == 40
   and [c["name"] for c in site["report"]["control"]] == ["CP1", "CP2", "CP3"], str(site["report"].get("control")))
TRUTH = json.load(open(os.path.join(FIX, "site-grid-control.json"), encoding="utf-8"))
tr = SI.transformer(27700)
pairs = []
for t in TRUTH:
    c = next(c for c in site["report"]["control"] if c["name"] == t["name"])
    ok(f"2. {t['name']} is read where it was drawn", [c["x"], c["y"]] == t["site_grid"], str(c))
    lon, lat = tr.transform(*t["bng"])
    pairs.append({"name": t["name"], "x": c["x"], "y": c["y"], "lon": lon, "lat": lat})
ft = SI.fit(pairs)
ok("2. the fit from three points: turn 27.61°, scale 1.0003, worst miss 0.01 m or less (the mockup's figures)",
   abs(ft["turn"] - 27.61) < 0.006 and abs(ft["scale"] - 1.0003) < 0.00006 and ft["worst"] <= 0.015
   and not ft["over"] and not ft["scale_flag"], str({k: ft[k] for k in ("turn", "scale", "worst")}))
ok("2. ...in one sentence", SI.fit_words(ft).startswith("Fitted from 3 points: the drawing turned 27.61°, scale 1.000"))
moved = SI.fitted(site["things"], ft)
gs = SI.gate_checks(moved, [{"name": G020["name"], "lon": G020["lon"], "lat": G020["lat"]},
                            {"name": G021["name"], "lon": G021["lon"], "lat": G021["lat"]}])
ok("2. ...both gates land on G020 / G021 within 0.01 m", len(gs) == 2 and max(g["m"] for g in gs) <= 0.015, str(gs))
ok("2. ...and the haul road starts where the National Grid drawing's does (within 2 cm)",
   metres(moved[0]["geometry"]["coordinates"][0], bng["things"][0]["geometry"]["coordinates"][0]) < 0.02)
ok("2. a symbol's angle loses the fit's turn", all(abs((m["properties"].get("rot") or 0) - ((s["properties"].get("rot") or 0) - ft["turn"])) < 1e-6
                                                  for m, s in zip(moved, site["things"]) if "rot" in s["properties"]))
ft2 = SI.fit(pairs[:2])
ok("2. two points are enough (no stretch: turn and scale from the pair)", abs(ft2["turn"] - 27.61) < 0.01 and ft2["points"] == 2)
bad = [dict(p) for p in pairs]
bad[2]["lat"] += 10 / 111000
ftb = SI.fit(bad)
ok("2. a point 10 m out: worst miss over 1 m, and the sentence says check the points",
   ftb["over"] and ftb["worst"] > 1 and "check the points" in SI.fit_words(ftb))
scaled = [dict(p, x=p["x"] * 1.01, y=p["y"] * 1.01) for p in pairs]
ok("2. a drawing scaled 1 % (wrong units, wrong points) is flagged", SI.fit(scaled)["scale_flag"]
   and "scale is not 1" in SI.fit_words(SI.fit(scaled)) or SI.fit(scaled)["over"])
e = raises(lambda: SI.fit(pairs[:1]))
ok("2. one point is refused in words", isinstance(e, SI.Refused) and "at least two" in str(e))
e = raises(lambda: SI.fit([pairs[0], dict(pairs[1], x=pairs[0]["x"], y=pairs[0]["y"])]))
ok("2. two points on top of each other are refused", isinstance(e, SI.Refused) and "on top of each other" in str(e))

# =========================================================================== #
#  2b. Two contractor-style drawings (31 Oct 2026, PR 1b; plan §6 revised)      #
# =========================================================================== #
# Fictional, written by backend/tools/make_contractor_style.py round the demo's L019: a drawing as a contractor's CAD
# office sends it (millimetres on National Grid x 1000, OS base mapping bound in, a hidden layer, a reference to a
# drawing not sent, the sheet drawn in model space with its key and title block, duplicates, dimensions, leaders, masks,
# a picture, arrowheads, blocks with attributes, a dynamic block, a mirrored welfare unit, a hatch with a hole, a
# gradient fill) and the same plan as an R12 file with no units. The parent session's reference reader measured 68 and
# 39 things, both with Gate 1 0.00 m from G020; this harness holds the build to the same figures.
SITE_PTS = [[L019["lon"], L019["lat"]]] + [[g["lon"], g["lat"]] for g in GATES]
C1 = SI.read(fx("contractor-style-mm.dxf"), "contractor-style-mm.dxf", near=NEAR, site=SITE_PTS)
C2 = SI.read(fx("contractor-style-r12-unitless.dxf"), "contractor-style-r12-unitless.dxf", near=NEAR, site=SITE_PTS)
c1, c2 = C1["report"], C2["report"]
ok("2b. the millimetre drawing: 68 things on 17 layers, on National Grid by OSTN15, its units from the file",
   c1["things"] == 68 and c1["layers"] == 17 and c1["grid"] == "bng" and c1["units"] == "millimetres, from the file"
   and c1["transform"] == "Inverse of British National Grid + OSGB36 to WGS 84 (9)" and c1["version"] == "AC1032", str(c1)[:300])
LO = c1["left_out"]
for label, key, n in [
        ("the OS base mapping bound in from another drawing", "Base mapping from another drawing (OSBASE)", 118),
        ("a hidden layer (OSBASE's words)", "On a hidden layer (OSBASE$0$Text)", 15),
        ("a frozen layer (OSBASE's spot heights)", "On a hidden layer (OSBASE$0$Spot Heights)", 50),
        ("a reference to a drawing that was not sent", "A drawing referred to but not sent (OS_Base_SK7303)", 1),
        ("the survey points", "Points", 20),
        ("a dimension", "Dimensions", 1),
        ("a leader arrow", "Leader arrows", 1),
        ("a mask behind words", "Masks behind words", 1),
        ("a picture", "Pictures (the picture file is not sent)", 1),
        ("an arrowhead fill", "Solid fills (arrowheads)", 1),
        ("the same thing twice on one layer", "The same thing twice", 3),
        ("the sheet's border layer", "The drawing sheet's border (Z_SHEET)", 8),
        ("the title block", "In the title block", 5),
        ("the key's sample lines and symbols", "In the drawing's key (its sample lines and symbols)", 14),
        ("anything over 1 km from the site", "Over 1 km from the site", 2)]:
    ok(f"2b. ...left out and counted: {label} ({n})", LO.get(key) == n, str(LO.get(key)))
ok("2b. ...and nothing else left out (241 in all, 15 reasons)", sum(LO.values()) == 241 and len(LO) == 15, str(LO))
ok("2b. ...every block named with what it became; the 32 x 10 welfare units (9.8 x 3.0 m) are outlines",
   c1["blocks"].get("WELFARE_UNIT_32x10: an outline, 9.8 × 3.0 m") == 4 and c1["blocks"].get("GATE: a symbol") == 2
   and c1["blocks"].get("GATE_TAG: a symbol") == 2 and c1["blocks"].get("(a dynamic block): a symbol") == 1
   and len(c1["blocks"]) == 13 and sum(c1["blocks"].values()) == 19, str(c1["blocks"]))
ok("2b. ...one block drawn mirrored, counted", c1.get("mirrored_blocks") == 1)
outl = [t for t in C1["things"] if t["properties"].get("outline") == "WELFARE_UNIT_32x10"]
ok("2b. a footprint block is its outline as an area, turned as inserted (4 units, each about 9.8 x 3.0 m)",
   len(outl) == 4 and all(t["geometry"]["type"] == "Polygon" for t in outl)
   and all(abs(metres(t["geometry"]["coordinates"][0][0], t["geometry"]["coordinates"][0][1]) - 9.8) < 0.15
           or abs(metres(t["geometry"]["coordinates"][0][0], t["geometry"]["coordinates"][0][1]) - 3.0) < 0.15 for t in outl),
   str([t["geometry"]["coordinates"][0][:2] for t in outl][:1]))
tags = sorted(t["properties"]["attribs"] for t in C1["things"] if t["properties"].get("attribs"))
ok("2b. a block's attribute values are its label (the two gate tags)", tags == ["GATE 1 (IN)", "GATE 2 (OUT)"], str(tags))
holed = [t for t in C1["things"] if t["geometry"]["type"] == "Polygon" and len(t["geometry"]["coordinates"]) > 1]
ok("2b. a hatch keeps its hole as an inner ring (the exclusion zone round the pier)", len(holed) == 1
   and holed[0]["properties"]["src_layer"] == "TW_EXCLUSION ZONE" and len(holed[0]["geometry"]["coordinates"]) == 2)
ok("2b. ...and the hole lies inside its area (31 Oct, seen in Chrome: the generator had cut it beside the zone)",
   all(SI._inside(p, holed[0]["geometry"]["coordinates"][0]) for p in holed[0]["geometry"]["coordinates"][1]))


def hatch_dxf(rings):
    import ezdxf
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = 6
    h = d.modelspace().add_hatch(dxfattribs={"layer": "C-EXCLUSION"})
    for i, r in enumerate(rings):
        h.paths.add_polyline_path(r, is_closed=True, flags=1 if i == 0 else 16)
    s_ = io.StringIO()
    d.write(s_)
    return s_.getvalue().encode("utf-8")


X1, Y1 = 475879.5, 305620.0
box = lambda x, y, d: [(x, y), (x + d, y), (x + d, y + d), (x, y + d)]
hz = SI.read(hatch_dxf([box(X1, Y1, 30), box(X1 + 10, Y1 + 10, 6), box(X1 + 40, Y1, 8)]), "h.dxf", near=NEAR, site=SITE_PTS)
ok("2b. a hatch's ring inside its area is a hole; a ring beside it is an area of its own (not a hole outside the area)",
   hz["report"]["things"] == 2 and sorted(len(t["geometry"]["coordinates"]) for t in hz["things"]) == [1, 2]
   and all(t["properties"]["src_layer"] == "C-EXCLUSION" for t in hz["things"]), str(hz["report"]))
hz = SI.read(hatch_dxf([box(X1, Y1, 30), box(X1 + 5, Y1 + 5, 20), box(X1 + 10, Y1 + 10, 6)]), "h.dxf", near=NEAR, site=SITE_PTS)
ok("2b. ...an island inside a hole (a target) is an area of its own too",
   hz["report"]["things"] == 2 and sorted(len(t["geometry"]["coordinates"]) for t in hz["things"]) == [1, 2])

grad = [t for t in C1["things"] if t["properties"].get("hatch") == "GRADIENT"]
ok("2b. a gradient fill takes its first colour", len(grad) == 1 and grad[0]["properties"]["color"] == "#C8DCFF", str(grad))
crow = {r["key"]: r for r in SI.rows(C1["things"])}
want = {"TW_HAUL ROAD": "line:twoway", "TW_HAUL ROAD ONE WAY": "line:oneway", "TW_HOARDING 2.4m": "line:hoarding",
        "TW_HERAS": "line:heras", "TW_BARRIER": "line:barrier", "TW_PED ROUTE": "line:ped", "TW_CAR PARK": "area:parking",
        "TW_LOADING BAY": "area:loading", "TW_EXCLUSION ZONE": "area:exclusion", "TW_CRANE RADIUS": "area:crane_radius",
        "EX_DRAINAGE": "skip", "SV_TOP OF BANK": "skip", "SV_LEVELS": "skip", "Z_TEXT": "text",
        "outline WELFARE_UNIT_32x10": "area:welfare", "block GATE_TAG": "text", "block GATE": "sym:gate",
        "block MARSHAL": "sym:marshal", "block SPEED_5": "sym:speed5", "block WHEEL_WASH": "sym:wheelwash",
        "block MOBILE_CRANE": "sym:mobilecrane", "block FIRST_AID": "sym:first_aid", "block FIRE_POINT": "sym:fire_point",
        "block TOILETS": "sym:toilets", "block ASSEMBLY": "sym:assembly", "block PED_CROSSING": "sym:pedx",
        "block (a dynamic block)": "sym:warning"}
ok("2b. the table's 27 rows are each guessed right from the contractor's words, before anyone chooses",
   {k: r["becomes"] for k, r in crow.items()} == want,
   str({k: (r["becomes"], want.get(k)) for k, r in crow.items() if r["becomes"] != want.get(k)}))
gc1 = SI.gate_checks(C1["things"], [{"name": g["name"], "lon": g["lon"], "lat": g["lat"]} for g in (G020, G021)])
ok("2b. ...Gate 1 lands 0.00 m from G020 (and Gate 2 on G021)", len(gc1) == 2 and max(g["m"] for g in gc1) <= 0.005, str(gc1))
ok("2b. the R12 drawing with no units: 39 things on 14 layers, read in metres from where it sits",
   c2["things"] == 39 and c2["layers"] == 14 and c2["grid"] == "bng" and c2["version"] == "AC1009"
   and c2["units"] == "metres, from where the drawing sits (no units in the file)" and c2["left_out"] == {}, str(c2)[:300])
gc2 = SI.gate_checks(C2["things"], [{"name": g["name"], "lon": g["lon"], "lat": g["lat"]} for g in (G020, G021)])
ok("2b. ...its gates land 0.00 m from G020 / G021", len(gc2) == 2 and max(g["m"] for g in gc2) <= 0.005, str(gc2))
ok("2b. ...and its haul road on the millimetre drawing's (the same plan, two ways of saving it)",
   metres(C2["things"][0]["geometry"]["coordinates"][0], C1["things"][0]["geometry"]["coordinates"][0]) < 0.01)
far = SI.read(fx("contractor-style-mm.dxf"), "c.dxf", near=NEAR)
ok("2b. with no site given (only the organisation's places), the far rule measures from the drawing's middle",
   far["report"]["grid"] == "bng" and far["report"]["things"] >= 68)

# ---- the holes on the way to the map: kept, wound for Mapbox, a broken one dropped (never the area)
sq = lambda x0, y0, d, ccw=True: ([[x0, y0], [x0 + d, y0], [x0 + d, y0 + d], [x0, y0 + d], [x0, y0]] if ccw
                                  else [[x0, y0], [x0, y0 + d], [x0 + d, y0 + d], [x0 + d, y0], [x0, y0]])


def area2(r):
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(r, r[1:]))


g = SL.clean_geometry({"type": "Polygon", "coordinates": [sq(-0.88, 52.64, 0.001, ccw=False), sq(-0.8798, 52.6402, 0.0002)]})
ok("2b. clean_geometry keeps a hole and winds it for the map: the outside anticlockwise, the hole clockwise",
   g and len(g["coordinates"]) == 2 and area2(g["coordinates"][0]) > 0 and area2(g["coordinates"][1]) < 0, str(g))
g = SL.clean_geometry({"type": "Polygon", "coordinates": [sq(-0.88, 52.64, 0.001), [[-0.8799, 52.6401], [-0.8798, 52.6401]]]})
ok("2b. ...a hole too short to be a ring is dropped, the area kept", g and len(g["coordinates"]) == 1)
ok("2b. ...a broken outside ring is refused", SL.clean_geometry({"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}) is None)
g = SL.clean_geometry({"type": "Polygon", "coordinates": [sq(-0.88, 52.64, 0.01)] + [sq(-0.8799 + i * 0.0001, 52.6401, 0.00005)
                                                                                     for i in range(SL.MAX_HOLES + 5)]})
ok(f"2b. ...at most {SL.MAX_HOLES} holes are kept", g and len(g["coordinates"]) == SL.MAX_HOLES + 1)

# =========================================================================== #
#  3. Refusals, in plain words                                                 #
# =========================================================================== #
import ezdxf  # noqa: E402


def dxf_bytes(units=6, x=475879.5, y=305620.0, control=False, k=1.0):
    """A one-line DXF; `k` = metres a drawing unit (31 Oct 2026: the line is 50 x 20 m whatever the units)."""
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = units
    m = d.modelspace()
    m.add_line((x, y), (x + 50 / k, y + 20 / k), dxfattribs={"layer": "C-HAUL-ROAD"})
    if control:
        m.add_point((x, y), dxfattribs={"layer": "SURVEY-CONTROL"})
        m.add_point((x + 100, y), dxfattribs={"layer": "SURVEY-CONTROL"})
    s = io.StringIO()
    d.write(s)
    return s.getvalue().encode("utf-8")


def refused(data, name, *words, **k):
    e = raises(lambda: SI.read(data, name, **k))
    return isinstance(e, SI.Refused) and all(w in str(e) for w in words), str(e)


for label, args in [
    ("DWG", (b"AC1032xxxx", "plan.dwg", "Save it as DXF in your CAD program")),
    # REVERSED 31 Oct 2026 (PR 1b, plan §6 revised): inches, millimetres and no units are read (checked after this
    # loop); a unit Wayscope does not read is the refusal now
    ("a drawing in decimetres", (dxf_bytes(units=14), "plan.dxf", "This drawing is in decimetres", "metres or millimetres")),
    ("a drawing in miles", (dxf_bytes(units=3), "plan.dxf", "This drawing is in miles")),
    ("a file that is not a DXF", (b"hello world", "plan.dxf", "not a DXF")),
    ("an empty file", (b"", "plan.kml", "empty")),
    ("a file over 10 MB", (b" " * (SI.MAX_BYTES + 1), "plan.geojson", "over 10 MB")),
    ("a PDF (a picture comes in PR 3)", (b"%PDF-1.7", "plan.pdf", "Wayscope reads DXF, KML, KMZ, GeoJSON and shapefile zips")),
    ("a GeoJSON on another grid",
     (json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:27700"}},
                  "features": []}).encode(), "plan.geojson", "not in longitude / latitude", "EPSG:4326")),
    ("a KML that is not one", (b"<<<", "plan.kml", "not a Google Earth file")),
]:
    good, why = refused(*args)
    ok(f"3. refused in words: {label}", good, why)

# REVERSED 31 Oct 2026 (PR 1b): a drawing in inches, millimetres or centimetres is scaled to metres and lands where the
# same drawing in metres does; one with no units is read in metres or millimetres from where it sits near the site
X0, Y0 = 475879.5, 305620.0
SITE = [[L019["lon"], L019["lat"]]] + [[g["lon"], g["lat"]] for g in GATES]
inm = SI.read(dxf_bytes(), "m.dxf", near=NEAR, site=SITE)
for code, k, word in ((1, 0.0254, "inches"), (2, 0.3048, "feet"), (4, 0.001, "millimetres"), (5, 0.01, "centimetres")):
    r = SI.read(dxf_bytes(units=code, x=X0 / k, y=Y0 / k, k=k), f"{word}.dxf", near=NEAR, site=SITE)
    ok(f"3. a drawing in {word} is scaled to metres: the same place, the same length, the units said",
       r["report"]["units"] == f"{word}, from the file" and r["report"]["grid"] == "bng"
       and metres(r["things"][0]["geometry"]["coordinates"][0], inm["things"][0]["geometry"]["coordinates"][0]) < 0.01
       and metres(r["things"][0]["geometry"]["coordinates"][1], inm["things"][0]["geometry"]["coordinates"][1]) < 0.01,
       str(r["report"]["units"]))
r = SI.read(dxf_bytes(units=0), "nounits.dxf", near=NEAR, site=SITE)
ok("3. no units, sitting on the site in metres: read in metres, and said so",
   r["report"]["units"] == "metres, from where the drawing sits (no units in the file)"
   and r["things"][0]["geometry"]["coordinates"][0] == inm["things"][0]["geometry"]["coordinates"][0], r["report"]["units"])
r = SI.read(dxf_bytes(units=0, x=X0 * 1000, y=Y0 * 1000, k=0.001), "nounits-mm.dxf", near=NEAR, site=SITE)
ok("3. no units, on the site only if read in millimetres: read in millimetres",
   r["report"]["units"] == "millimetres, from where the drawing sits (no units in the file)"
   and metres(r["things"][0]["geometry"]["coordinates"][0], inm["things"][0]["geometry"]["coordinates"][0]) < 0.01)
e = raises(lambda: SI.read(dxf_bytes(units=0, x=200000.0, y=900000.0), "far.dxf", near=NEAR, site=SITE))
ok("3. no units and not near the site in metres or millimetres, no survey points: the page asks",
   isinstance(e, SI.AskGrid), repr(e))
good, why = refused(dxf_bytes(units=0, x=200000.0, y=900000.0), "far.dxf", "has no units and does not sit near the site",
                    grid="bng", near=NEAR, site=SITE)
ok("3. ...answered National Grid, refused in words (its units cannot be told)", good, why)
ok("3. text heights and line widths are scaled too (a 7 m haul road in millimetres is 7 m)",
   SI.read(fx("contractor-style-mm.dxf"), "c.dxf", near=NEAR, site=SITE)["things"][0]["properties"].get("width_m")
   == bng["things"][0]["properties"].get("width_m") == 7.0)

zb = io.BytesIO()
with zipfile.ZipFile(zb, "w") as z:
    src = zipfile.ZipFile(io.BytesIO(fx("tilton-logistics-shp.zip")))
    for n in src.namelist():
        if not n.lower().endswith(".prj"):
            z.writestr(n, src.read(n))
good, why = refused(zb.getvalue(), "noprj.zip", "has no .prj file, so its position is unknown.")
ok("3. a shapefile with no .prj is refused, naming the file", good, why)
zb = io.BytesIO()
with zipfile.ZipFile(zb, "w") as z:
    z.writestr("readme.txt", "nothing here")
good, why = refused(zb.getvalue(), "empty.kmz", "holds no KML")
ok("3. a KMZ with no KML in it", good, why)
good, why = refused(zb.getvalue(), "empty.zip", "holds no shapefile")
ok("3. a zip with no shapefile in it", good, why)
zb = io.BytesIO()
with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("doc.kml", b" " * (SI.MAX_UNPACKED + 10))
good, why = refused(zb.getvalue(), "bomb.kmz", "unpacks to more than 50 MB")
ok("3. a zip that unpacks past 50 MB is refused before it is read whole", good, why)
many = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.88, 52.64]}, "properties": {"marker-symbol": "cone"}}
    for _ in range(SI.MAX_THINGS + 2)]}
good, why = refused(json.dumps(many).encode(), "many.geojson", "more than 5,000 things")
ok("3. more than 5,000 things is refused", good, why)
e = raises(lambda: SI.read(dxf_bytes(x=200000.0, y=900000.0), "far.dxf", near=NEAR))
ok("3. a DXF far from every location with no survey points: the page is asked which grid",
   isinstance(e, SI.AskGrid) and "National Grid" in str(e), repr(e))
r = SI.read(dxf_bytes(x=200000.0, y=900000.0), "far.dxf", grid="bng", near=NEAR)
ok("3. ...answered National Grid, it is read on National Grid", r["report"]["grid"] == "bng")
good, why = refused(dxf_bytes(x=200000.0, y=900000.0), "far.dxf", "fewer than two survey points", grid="site")
ok("3. ...answered site grid with no survey points, refused in words", good, why)
r = SI.read(dxf_bytes(x=1000.0, y=2000.0, control=True), "site.dxf", near=NEAR)
ok("3. a small drawing near (0, 0) with survey points is taken as a site grid", r["report"]["grid"] == "site"
   and len(r["report"]["control"]) == 2)
_g = SI.GRID_DIR
SI.GRID_DIR = os.path.join(TMP, "no-grid")
good, why = refused(fx("tilton-logistics.kml"), "plan.kml", "cannot be brought in on this server yet")
SI.GRID_DIR = _g
ok("3. without the OSTN15 grid every import is refused (no 2 m Helmert fallback)", good, why)

# =========================================================================== #
#  4. Through the endpoints: read, fit, place, the table kept                   #
# =========================================================================== #
reset_db()
T = db.current_tenant()
db.execute("INSERT INTO locations (tenant_id, id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (T, "L019", L019["name"], "Site", "destination", L019["lat"], L019["lon"]))
db.execute("INSERT INTO locations (tenant_id, id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (T, "L001", "Quarry (fictional)", "Quarry", "origin", 52.7, -0.95))
for g in GATES:
    db.execute("INSERT INTO location_gates (tenant_id, id, location_id, name, direction, lat, lon, active) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (T, g["id"], "L019", g["name"], g["direction"], g["lat"], g["lon"], True))


def as_code(code):
    return access.set_current(code)


def http(fn, *a, **k):
    """(status, answer) for a main.* endpoint: 200 and the value, or the HTTPException's code and detail."""
    try:
        return 200, fn(*a, **k)
    except _HTTPException as e:
        return e.status_code, e.detail


def read_ep(data, name, loc="L019", grid="auto"):
    return http(lambda: asyncio.run(main.read_site_layout_file(_Request({"content-length": str(len(data))}, data),
                                                                location_id=loc, name=name, grid=grid)))


as_code(None)
ok("4. signed out: every site layout read and write is refused (401)",
   http(main.site_layout_styles_ep)[0] == 401 and http(main.get_site_layout, "L019")[0] == 401
   and read_ep(fx("tilton-logistics.kml"), "x.kml")[0] == 401
   and http(main.site_layouts_map, None, _Request())[0] == 401)
ok("4. the map password's cookie alone does not open the staff layer (401)",
   http(main.site_layouts_map, None, _Request(cookies={"wayscope_map": "x"}))[0] == 401)
import gate  # noqa: E402
os.environ.setdefault("GATE_SECRET", "site-layouts-harness-secret")   # sign() needs a key
ok("4. the styles: signed out 401, the map password's cookie 401 (31 Oct: the read takes the request)",
   http(main.site_layout_styles_ep, _Request())[0] == 401
   and http(main.site_layout_styles_ep, _Request(cookies={gate.COOKIE: gate.sign(gate.LEVEL_MAP)}))[0] == 401
   and http(main.site_layouts_map, None, _Request(cookies={gate.COOKIE: gate.sign(gate.LEVEL_MAP)}))[0] == 401)
ok("4. the staff gate cookie alone (the public map sends no code) reads the styles and the map layer (200)",
   http(main.site_layout_styles_ep, _Request(cookies={gate.COOKIE: gate.sign(gate.LEVEL_STAFF)}))[0] == 200
   and http(main.site_layouts_map, None, _Request(cookies={gate.COOKIE: gate.sign(gate.LEVEL_STAFF)}))[0] == 200)
as_code("submitter123")
ok("4. a submitter reads the styles and a site's layout, but cannot bring in a drawing or save (403)",
   http(main.site_layout_styles_ep)[0] == 200 and http(main.get_site_layout, "L019")[0] == 200
   and read_ep(fx("tilton-logistics.kml"), "x.kml")[0] == 403
   and http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="x"))[0] == 403)
as_code("planner123")
st, g0 = http(main.get_site_layout, "L019")
ok("4. a site with no layout yet: none, and the import is ready", st == 200 and g0["layout"] is None and g0["ready"] is True)
st, rd = read_ep(fx("tilton-logistics-bng.dxf"), "tilton-logistics-bng.dxf")
ok("4. a planner brings in the National Grid DXF: held, 23 rows, the gate check, the site's gates for the map",
   st == 200 and rd.get("import_id") and len(rd["rows"]) == 23 and len(rd["gate_check"]) == 2
   and rd["gate_check"][0]["m"] <= 0.01 and len(rd["site_gates"]) == 2 and rd["bounds"], str(rd)[:300])
ok("4. ...nothing is saved by reading", db.query("SELECT COUNT(*) AS n FROM site_layouts WHERE tenant_id = ?", (T,))[0]["n"] == 0)
ok("4. ...reading is not an audited write (the place step is)", "/api/site-layouts/read" in main.AUDIT_SKIP
   and main._audited("/api/locations/L019/site-layout/place"))
st, big = read_ep(b" " * (SI.MAX_BYTES + 1), "big.geojson")
ok("4. an upload over 10 MB is refused before it is read (413, in words)", st == 413 and "over 10 MB" in big)
st, ask = read_ep(dxf_bytes(x=200000.0, y=900000.0), "far.dxf")
ok("4. a drawing whose grid cannot be told: the answer asks", st == 200 and "ask_grid" in ask)
st, bad = read_ep(b"AC1032", "plan.dwg")
ok("4. a DWG: 400 with the sentence", st == 400 and "Save it as DXF" in bad)

ch = {r["key"]: r["becomes"] for r in rd["rows"]}
ch["C-DRAINAGE"] = "skip"
st, pl = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(
    import_id=rd["import_id"], choices=ch, where="new", phase={"name": "Pier bases", "month_from": "2027-03",
                                                                "month_to": "2027-06"}))
ok("4. placed on a new phase: 39 things (the drainage left out by the table), the phase named and dated",
   st == 200 and pl["placed"] == 39 and pl["left_out"] == 1 and pl["phase"]["name"] == "Pier bases"
   and pl["phase"]["month_from"] == "2027-03" and pl["phase"]["things"] == 39, str(pl)[:300])
lay = main.get_site_layout("L019")["layout"]
ph = lay["phases"][0]
feats = ph["features"]["features"]
ok("4. the layout is made with its first phase; the import is logged with the transform",
   lay["location_id"] == "L019" and len(lay["phases"]) == 1 and len(lay["imports"]) == 1
   and lay["imports"][0]["things"] == 39 and lay["imports"][0]["format"] == "DXF"
   and "OSGB36 to WGS 84 (9)" in (lay["imports"][0]["transform"] or ""), str(lay["imports"]))
kinds = {}
for f in feats:
    kinds[f["properties"]["style"]] = kinds.get(f["properties"]["style"], 0) + 1
ok("4. each thing is an ordinary layout thing: styles from the table, the source kept",
   kinds.get("twoway") == 3 and kinds.get("sym") == 12 and kinds.get("text") == 8 and kinds.get("welfare") == 4
   and all(f["properties"].get("source") == "tilton-logistics-bng.dxf (DXF)" for f in feats), str(kinds))
haul = next(f for f in feats if f["properties"]["style"] == "twoway")
ok("4. a line keeps its drawn width; with 'ours' the style's colour, not the file's",
   haul["properties"]["w"] == 7.0 and haul["properties"]["color"] == ST.LINE_STYLES["twoway"]["color"])
gate = next(f for f in feats if f["properties"].get("sym") == "gate")
ok("4. a symbol is a point with the style table's size and layer", gate["geometry"]["type"] == "Point"
   and gate["properties"]["layer"] == "Access" and gate["properties"]["size"] == ST.SYMBOL_KEYS["gate"]["size"])
txt = [f for f in feats if f["properties"]["style"] == "text"]
ok("4. words keep their text and a size from the drawn height", all(t["properties"]["text"] for t in txt)
   and all(t["properties"]["size"] > 0 for t in txt) and any("GATE" in t["properties"]["text"] for t in txt))
ok("4. every saved coordinate has at most 7 decimals",
   all(len(str(c).split(".")[-1]) <= 7 for f in feats for c in json.dumps(f["geometry"]["coordinates"]).replace("[", ",").replace("]", ",").split(",") if c.strip() and "." in c))
ok("4. the organisation's table is kept in Config (site_layouts.import_map), the drainage as leave out",
   SL.import_map().get("C-DRAINAGE") == "skip" and SL.import_map().get("block GATE") == "sym:gate")
st, rd2 = read_ep(fx("tilton-logistics-bng.dxf"), "again.dxf")
r2 = {r["key"]: r for r in rd2["rows"]}
ok("4. the second drawing from the same contractor needs no choosing: the rows come back as saved",
   r2["C-DRAINAGE"]["becomes"] == "skip" and r2["C-DRAINAGE"]["saved"] is True and r2["C-HAUL-ROAD"]["saved"] is True)
st, pl2 = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rd2["import_id"], keep_colours=True,
                                                                      where=ph["id"], version=ph["version"]))
ok("4. placed on the phase shown (keeping the file's colours): 39 more on the same phase",
   st == 200 and pl2["placed"] == 39 and pl2["phase"]["things"] == 78 and pl2["phase"]["version"] == ph["version"] + 1, str(pl2)[:200])
ph = main.get_site_layout("L019")["layout"]["phases"][0]
ok("4. ...the file's colour kept where asked", any(f["properties"].get("color") == "#FF7F00" for f in ph["features"]["features"]))
st, again = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rd2["import_id"]))
ok("4. a held drawing is placed once: a second place asks for the file again", st == 400 and "Bring the file in again" in again)
st, rk = read_ep(fx("tilton-logistics.kml"), "tilton-logistics.kml")
st, other = http(main.place_site_layout, "L001", main.SiteLayoutPlaceIn(import_id=rk["import_id"]))
ok("4. a drawing held for one site cannot be placed on another", st == 400 and "no longer held" in other)

# the site grid through the endpoints
st, rs = read_ep(fx("tilton-logistics-site-grid.dxf"), "tilton-logistics-site-grid.dxf")
ok("4. the site-grid DXF: held, three survey points, no gate check until it is placed",
   st == 200 and [c["name"] for c in rs["control"]] == ["CP1", "CP2", "CP3"] and rs["gate_check"] == [] and rs["bounds"] is None)
pts = ";".join(f"{p['name']}:{p['lon']},{p['lat']}" for p in pairs)
st, fp = http(main.site_layout_fit, "L019", rs["import_id"], pts)
ok("4. the fit through the endpoint: turn 27.61°, each point's miss, the gates within 0.01 m",
   st == 200 and abs(fp["turn"] - 27.61) < 0.006 and len(fp["misses"]) == 3 and max(m["m"] for m in fp["misses"]) <= 0.015
   and max(g["m"] for g in fp["gate_check"]) <= 0.015 and fp["words"].startswith("Fitted from 3 points"), str(fp)[:300])
st, one = http(main.site_layout_fit, "L019", rs["import_id"], pts.split(";")[0])
ok("4. ...one point: 400, place at least two", st == 400 and "at least two" in one)
badpts = [dict(p) for p in pairs]
badpts[2]["lat"] += 10 / 111000
st, refuse = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rs["import_id"], points=badpts,
                                                                         phase={"name": "Site grid"}))
ok("4. a fit missing a point by more than 1 m is refused unless Place anyway", st == 400 and "Place anyway" in refuse)
# 31 Oct 2026 (seen in Chrome): two points always fit with no miss, so a stretched fit is refused on its scale alone
twopts = [dict(p) for p in pairs[:2]]
twopts[1]["lat"] += 60 / 111000
st, fsc = http(main.site_layout_fit, "L019", rs["import_id"], ";".join(f"{p['name']}:{p['lon']},{p['lat']}" for p in twopts))
st2, refuse2 = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rs["import_id"], points=twopts,
                                                                           phase={"name": "Site grid"}))
ok("4. two points picked wrong: no miss, but the scale is flagged and the place refused unless Place anyway",
   st == 200 and fsc["worst"] == 0 and not fsc["over"] and fsc["scale_flag"] and st2 == 400
   and "stretched" in refuse2 and "Place anyway" in refuse2, str(fsc)[:200] + " " + str(refuse2))
st, ps = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rs["import_id"], points=pairs,
                                                                     phase={"name": "Site grid"}))
ok("4. placed with good points: a second phase, the fit in the log", st == 200 and ps["placed"] == 39
   and ps["report"]["fit"]["worst"] <= 0.015 and "Fitted from 3 points" in ps["report"]["fit_words"], str(ps)[:200])
lay = main.get_site_layout("L019")["layout"]
ok("4. the log keeps the fit's sentence", lay["imports"][0]["fit"] and lay["imports"][0]["fit"].startswith("Fitted"))

# =========================================================================== #
#  5. Phases: months, rename, delete, the version check, the things checked    #
# =========================================================================== #
st, np_ = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="Deck lift", month_from="2027-07"))
ok("5. a new empty phase", st == 200 and np_["phase_id"] and len(np_["layout"]["phases"]) == 3)
pid = np_["phase_id"]
cur = next(p for p in np_["layout"]["phases"] if p["id"] == pid)
st, e1 = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name=" "))
ok("5. a phase needs a name", st == 400 and "name" in e1)
st, e2 = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="x", month_from="2027-13"))
ok("5. a month must be a month", st == 400 and "like 2027-04" in e2)
st, e3 = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="x", month_from="2027-06", month_to="2027-05"))
ok("5. To before From is refused", st == 400 and "before the From" in e3)
st, ed = http(main.edit_site_layout_phase, pid, main.SiteLayoutPhaseIn(name="Deck lift and launch", month_to="2027-09",
                                                                         version=cur["version"]))
ok("5. renamed and given its last month; the version moves on", st == 200 and ed["name"] == "Deck lift and launch"
   and ed["month_from"] == "2027-07" and ed["month_to"] == "2027-09" and ed["version"] == cur["version"] + 1, str(ed))
st, stale = http(main.edit_site_layout_phase, pid, main.SiteLayoutPhaseIn(name="Mine", version=cur["version"]))
ok("5. a save behind someone else's is refused (409) with the sentence", st == 409 and stale == SL.STALE)
st, stale2 = http(main.save_site_layout_things, pid, main.SiteLayoutThingsIn(version=cur["version"], features={"features": []}))
ok("5. ...the same for the things", st == 409 and stale2 == SL.STALE)
st, stale3 = http(main.delete_site_layout_phase, pid, cur["version"])
ok("5. ...and for a delete", st == 409 and stale3 == SL.STALE)
things = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.881, 52.644], [-0.8815, 52.6445]]},
     "properties": {"style": "heras", "evil": "<script>", "w": 0.12}},
    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-0.881, 52.644], [-0.8811, 52.644], [-0.8811, 52.6441]]]},
     "properties": {"style": "laydown", "fill": "polka"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]}, "properties": {"style": "sym", "sym": "towercrane"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]}, "properties": {"style": "flying"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]}, "properties": {"style": "sym", "sym": "dragon"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]}, "properties": {"style": "text"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]}, "properties": {"style": "heras"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.88123456789, 252.0]}, "properties": {"style": "sym", "sym": "towercrane"}},
]}
st, sv = http(main.save_site_layout_things, pid, main.SiteLayoutThingsIn(version=ed["version"], features=things))
ok("5. things saved after checking: three kept, five left out with a reason each", st == 200 and sv["things"] == 3
   and len(sv["left_out"]) == 5 and any("not one Wayscope draws" in w for w in sv["left_out"])
   and any("needs words" in w for w in sv["left_out"]) and any("must be a line" in w for w in sv["left_out"]), str(sv.get("left_out")))
kept = sv["features"]["features"]
ok("5. an unknown property is dropped, an unknown fill too; the ring is closed; the layer filled in",
   "evil" not in kept[0]["properties"] and kept[0]["properties"]["layer"] == "Traffic management"
   and "fill" not in kept[1]["properties"] and kept[1]["geometry"]["coordinates"][0][0] == kept[1]["geometry"]["coordinates"][0][-1]
   and kept[2]["properties"]["layer"] == "Plant", str(kept)[:300])
too_many = {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.881, 52.644]},
                          "properties": {"style": "sym", "sym": "cone"}}] * (SL.MAX_PHASE + 1)}
st, tm = http(main.save_site_layout_things, pid, main.SiteLayoutThingsIn(version=sv["version"], features=too_many))
ok("5. a phase holds at most 2,000 things", st == 400 and "2,000" in tm)
# 31 Oct 2026 (task 4c PR 2): what the drawing tools send — an area WITH a hole (the tools keep holes beside Terra Draw and put
# them back on save) keeps both rings; 7 dp coordinates come back as sent
holed = {"type": "FeatureCollection", "features": kept + [
    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
        [[-0.8810000, 52.6440000], [-0.8800000, 52.6440000], [-0.8800000, 52.6450000], [-0.8810000, 52.6450000], [-0.8810000, 52.6440000]],
        [[-0.8806000, 52.6444000], [-0.8806000, 52.6446000], [-0.8804000, 52.6446000], [-0.8804000, 52.6444000], [-0.8806000, 52.6444000]]]},
     "properties": {"style": "exclusion", "text": "LIFT ZONE", "mode": "polygon", "selected": True}}]}
st, sh = http(main.save_site_layout_things, pid, main.SiteLayoutThingsIn(version=sv["version"], features=holed))
hz = sh["features"]["features"][-1] if st == 200 else {}
ok("5. (PR 2) an area with a hole saved by the drawing tools keeps both rings, its 7 dp corners and its words; their own flags dropped",
   st == 200 and sh["things"] == 4 and len(hz["geometry"]["coordinates"]) == 2 and hz["geometry"]["coordinates"][1][1] == [-0.8806, 52.6446]
   and hz["properties"]["text"] == "LIFT ZONE" and "selected" not in hz["properties"], str(sh)[:300])
# Copy to a new phase (Q8): every thing, "<name> (copy)", no months, opened in the editor by the page
as_code("submitter123")
ok("5. (PR 2) a submitter cannot copy a phase (403)", http(main.copy_site_layout_phase, pid)[0] == 403)
as_code("planner123")
before_n = len(main.get_site_layout("L019")["layout"]["phases"])
st, cp = http(main.copy_site_layout_phase, pid)
cph = cp["phase"] if st == 200 else {}
lay_c = main.get_site_layout("L019")["layout"]
full = next((p for p in lay_c["phases"] if p["id"] == cph.get("id")), {})
src_ph = next(p for p in lay_c["phases"] if p["id"] == pid)
ok("⭐ 5. (PR 2) Copy to a new phase: a new phase with every thing (holes too), the name + ' (copy)', no months, version 1, last in order",
   st == 200 and cph["id"] != pid and cph["name"] == "Deck lift and launch (copy)" and cph["month_from"] is None and cph["month_to"] is None
   and cph["version"] == 1 and cph["things"] == 4 and len(lay_c["phases"]) == before_n + 1 and lay_c["phases"][-1]["id"] == cph["id"]
   and full["features"] == src_ph["features"] and "features" not in cph, str(cp)[:300])
ok("5. (PR 2) ...the copy leaves the phase it came from as it was (same version, same things)",
   src_ph["version"] == sh["version"] and src_ph["things"] == 4)
_max = SL.MAX_PHASES
SL.MAX_PHASES = len(lay_c["phases"])
st, cfull = http(main.copy_site_layout_phase, pid)
SL.MAX_PHASES = _max
ok("5. (PR 2) ...refused at the phase limit, in words", st == 400 and "at most" in cfull and "phases" in cfull, str(cfull))
st, cgone = http(main.copy_site_layout_phase, "PH999")
ok("5. (PR 2) ...a phase that is not there: refused in words, like every phase call", st == 400 and "not there" in cgone, str((st, cgone)))
st, dcp = http(main.delete_site_layout_phase, cph["id"], cph["version"])
ok("5. (PR 2) ...and the copy deletes like any phase", st == 200)
sv = sh
st, dl = http(main.delete_site_layout_phase, pid, sv["version"])
ok("5. deleted with its version", st == 200 and len(main.get_site_layout("L019")["layout"]["phases"]) == 2)
ok("5. in_month: open ends apply, closed ends bound", SL.in_month({"month_from": None, "month_to": None}, "2030-01")
   and SL.in_month({"month_from": "2027-03", "month_to": "2027-06"}, "2027-06")
   and not SL.in_month({"month_from": "2027-03", "month_to": "2027-06"}, "2027-07")
   and not SL.in_month({"month_from": "2027-03", "month_to": None}, "2027-02"))

# =========================================================================== #
#  6. The staff Route map's read                                               #
# =========================================================================== #
st, m4 = http(main.site_layouts_map, "2027-04", _Request())
ok("6. April 2027: both phases apply (Pier bases Mar-Jun, Site grid undated), each thing tagged with site and phase",
   st == 200 and len(m4["sites"]) == 1 and len(m4["sites"][0]["phases"]) == 2
   and len(m4["features"]["features"]) == 78 + 39
   and all(f["properties"]["site"] == "L019" and f["properties"]["phase"] for f in m4["features"]["features"]), str(m4["sites"]))
st, m8 = http(main.site_layouts_map, "2027-08", _Request())
ok("6. August 2027: only the undated phase", st == 200 and len(m8["features"]["features"]) == 39)
st, mbad = http(main.site_layouts_map, "Aug", _Request())
ok("6. a month must be YYYY-MM", st == 400)
st, mnow = http(main.site_layouts_map, None, _Request())
ok("6. no month: this month", st == 200 and re.fullmatch(r"\d{4}-\d{2}", mnow["month"]))
# NARROWED 31 Oct 2026 (task 4c PR 3): the summary also counts the site's pinned pictures (none here)
ok("6. the summary for the Locations list",
   main.site_layout_summary()["sites"] == {"L019": {"phases": 2, "things": 117, "pictures": 0}})

# =========================================================================== #
#  7. The organisation file, Config's check, the dependencies                  #
# =========================================================================== #
ok("7. the three tables are tenanted, in the package's order after the locations, and a layout makes it not empty",
   {"site_layouts", "site_layout_phases", "site_layout_imports"} <= db.TENANTED_TABLES
   and tenant_package.ORDER.index("site_layouts") > tenant_package.ORDER.index("location_gates")
   and tenant_package.ORDER.index("site_layout_phases") > tenant_package.ORDER.index("site_layouts")
   and "site_layouts" in tenant_package.EMPTY_CHECK and not tenant_package.is_empty())
pkg = tenant_package.export_tenant()
ok("7. exported: the layout, its two phases and its three imports",
   len(pkg["tables"]["site_layouts"]) == 1 and len(pkg["tables"]["site_layout_phases"]) == 2
   and len(pkg["tables"]["site_layout_imports"]) == 3)
before = main.get_site_layout("L019")["layout"]
res = tenant_package.import_tenant(pkg, replace=True)
after = main.get_site_layout("L019")["layout"]
ok("7. ...and back: the same layout, phases and things", res["ok"] and json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True))
doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
doc["site_layouts"] = {"import_map": {"C-HAUL": "line:flying"}}
ok("7. Config refuses an import table row that becomes no style", any("must become a style" in p for p in config.validate(doc)))
doc["site_layouts"] = {"import_map": {"C-HAUL": "line:twoway", "block X": "skip"}}
ok("7. ...and takes a good one", not any("site_layouts" in p for p in config.validate(doc)))
doc["site_layouts"] = []
ok("7. ...site_layouts must be an object", "site_layouts must be an object" in config.validate(doc))
req = open(os.path.join(BACKEND, "requirements.txt"), encoding="utf-8").read().split()
ok("7. ezdxf, pyproj and pyshp are pinned exact", {"ezdxf==1.4.5", "pyproj==3.8.0", "pyshp==3.1.6"} <= set(req))
src = open(os.path.join(BACKEND, "site_layout_import.py"), encoding="utf-8").read()
ok("7. PROJ never fetches a grid by itself; pyproj and ezdxf load only when a drawing is read",
   "set_network_enabled(False)" in src and not re.search(r"^import (ezdxf|pyproj|shapefile)", src, re.M))
ok("7. no fastkml (LGPL)", "fastkml" not in "".join(req))
mainsrc = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("7. the read runs alone under the heavy-read guard", 'heavy_reads.solo("site-layout-read"' in mainsrc)
ok("7. every write needs a planner or an admin (_require_approver), reads any signed-in code",
   all(re.search(r'def ' + fn + r'\([^)]*\):\n(?:    """[\s\S]*?"""\n)?    _require_approver\(\)', mainsrc)
       for fn in ("site_layout_fit", "place_site_layout", "add_site_layout_phase", "edit_site_layout_phase",
                  "save_site_layout_things", "delete_site_layout_phase")))

# =========================================================================== #
#  8. The contractor's drawing placed (31 Oct 2026, PR 1b)                     #
# =========================================================================== #
as_code("planner123")
# 31 Oct 2026 (PR 1b): the contractor's millimetre drawing through the endpoints, on a phase of its own, as guessed
st, rdc = read_ep(fx("contractor-style-mm.dxf"), "contractor-style-mm.dxf")
ok("8. the contractor's drawing is held: 27 rows, the gate check 0.00 m, the report's units and leave-outs",
   st == 200 and len(rdc["rows"]) == 27 and rdc["gate_check"] and rdc["gate_check"][0]["m"] <= 0.005
   and rdc["report"]["units"] == "millimetres, from the file" and sum(rdc["report"]["left_out"].values()) == 241,
   str(rdc)[:300])
st, plc = http(main.place_site_layout, "L019", main.SiteLayoutPlaceIn(import_id=rdc["import_id"], where="new",
                                                                      phase={"name": "Contractor (31 Oct)"}))
cf = [f for p in main.get_site_layout("L019")["layout"]["phases"] if p["name"] == "Contractor (31 Oct)"
      for f in p["features"]["features"]]
ok("8. placed as guessed: 46 things (the 22 the table leaves out not placed)",
   st == 200 and plc["placed"] == 46 and len(cf) == 46, str(plc)[:300])
hz = [f for f in cf if f["properties"]["style"] == "exclusion"]
ok("8. ...the exclusion zone is saved with its hole, wound for the map",
   len(hz) == 1 and len(hz[0]["geometry"]["coordinates"]) == 2 and area2(hz[0]["geometry"]["coordinates"][0]) > 0
   and area2(hz[0]["geometry"]["coordinates"][1]) < 0)
ok("8. ...the four welfare units are welfare areas; the gate tags are words reading GATE 1 (IN) / GATE 2 (OUT)",
   sum(1 for f in cf if f["properties"]["style"] == "welfare") == 4
   and sorted(f["properties"]["text"] for f in cf if f["properties"]["style"] == "text" and "(IN)" in f["properties"]["text"]
              or f["properties"]["style"] == "text" and "(OUT)" in f["properties"]["text"]) == ["GATE 1 (IN)", "GATE 2 (OUT)"])

# =========================================================================== #
#  9. The public map (31 Oct 2026, PR 4; mockup site-layout-public-mockup-1031) #
# =========================================================================== #
# A site of its own (L050) so the counts here do not move with the sections above.
import read_cache  # noqa: E402
db.execute("INSERT INTO locations (tenant_id, id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (T, "L050", "Gorse Lane depot (fictional)", "Site", "destination", 52.65, -0.89))
as_code("planner123")


def F(geom, **props):
    return {"type": "Feature", "geometry": geom, "properties": props}


P1 = {"type": "Point", "coordinates": [-0.8900, 52.6500]}
LN = {"type": "LineString", "coordinates": [[-0.8910, 52.6495], [-0.8890, 52.6505]]}
AR = {"type": "Polygon", "coordinates": [[[-0.8905, 52.6498], [-0.8895, 52.6498], [-0.8895, 52.6502], [-0.8905, 52.6498]]]}
pub_things = {"features": [
    F(LN, style="barrier", source="CONTRACTOR-LOGISTICS-REV-C.dxf", src_layer="TW_BARRIER"),
    F(AR, style="laydown", text="LAYDOWN"),
    F(P1, style="sym", sym="first_aid", label="First aid"),
    F(P1, style="sym", sym="security", label="Security"),
    F(P1, style="sym", sym="cctv"),
    F(P1, style="text", text="ALL DELIVERIES BOOKED", bold=True),
]}
st, ph1 = http(main.add_site_layout_phase, "L050", main.SiteLayoutPhaseIn(name="L1 test: internal only", month_from="2027-03",
                                                                          month_to="2027-06"))
lay50 = ph1["layout"]
cur50 = lay50["phases"][0]
st, sv50 = http(main.save_site_layout_things, ph1["phase_id"], main.SiteLayoutThingsIn(version=cur50["version"],
                                                                                        features=pub_things))
ok("9. a layout on L050: six things saved, the switch off when made", st == 200 and sv50["things"] == 6
   and lay50["public"] is False)
# a thing a LATER kind of thing might add (a pinned picture, an unknown style) written straight into the phase, as a
# future PR could: the public read must leave it out even though the save path never made it
raw = json.loads(db.query("SELECT features_json FROM site_layout_phases WHERE tenant_id = ? AND id = ?",
                          (T, ph1["phase_id"]))[0]["features_json"])
raw["features"] += [F(AR, style="picture", image="data:image/png;base64,AAAA", corners=[[0, 0]]),
                    F(P1, style="sym", sym="dragon"), F(LN, style="sym", sym="first_aid"),
                    F(P1, style="text", text="secret", note="staff only", by="jdavis")]
db.execute("UPDATE site_layout_phases SET features_json = ? WHERE tenant_id = ? AND id = ?",
           (json.dumps(raw), T, ph1["phase_id"]))

as_code(None)
st, off = http(main.public_site_layouts, "2027-04")
offj = json.loads(off.body)
ok("9. switched off: the public read sends no site and no thing", st == 200 and offj["sites"] == []
   and offj["features"]["features"] == [] and offj["any"] is False)
ok("9. the public read needs no code (it sits behind the map gate as every /api/public/ read)",
   any("/api/public/site-layouts".startswith(p) for p in __import__("gate").MAP_DATA_PREFIXES))

as_code("submitter123")
st, e_team = http(main.set_site_layout_public, "L050", main.SiteLayoutPublicIn(public=True, version=1))
ok("9. a team code cannot switch it (403)", st == 403, str((st, e_team)))
as_code("planner123")
v0 = main.get_site_layout("L050")["layout"]["version"]
st, stale_p = http(main.set_site_layout_public, "L050", main.SiteLayoutPublicIn(public=True, version=v0 + 5))
ok("9. a switch behind someone else's change is refused (409) with the sentence", st == 409 and stale_p == SL.STALE)
st, e_none = http(main.set_site_layout_public, "L001", main.SiteLayoutPublicIn(public=True, version=1))
ok("9. a site with no layout cannot be switched", st == 400 and "no layout" in e_none)
ver_before = db.data_version()
st, on = http(main.set_site_layout_public, "L050", main.SiteLayoutPublicIn(public=True, version=v0))
ok("9. a planner switches it on; the layout's version moves on; the write counts as a change",
   st == 200 and on["layout"]["public"] is True and on["layout"]["version"] == v0 + 1 and db.data_version() > ver_before)

as_code(None)
st, pa = http(main.public_site_layouts, "2027-04")
pj = json.loads(pa.body)
pf = pj["features"]["features"]
ok("9. April 2027: L050 only (L019's layout is still off), with its name and the middle of what is drawn",
   st == 200 and [s["location_id"] for s in pj["sites"]] == ["L050"] and pj["sites"][0]["name"] == "Gorse Lane depot (fictional)"
   and len(pj["sites"][0]["middle"]) == 2 and pj["any"] is True, str(pj["sites"]))
ok("9. ...five things go: the barrier, the laydown, first aid and the two sets of words (the written-in one stripped)",
   sorted(f["properties"]["style"] + ":" + f["properties"].get("sym", "") for f in pf)
   == ["barrier:", "laydown:", "sym:first_aid", "text:", "text:"], str([f["properties"] for f in pf]))
ok("9. ...the security cabin and CCTV never go (the server takes them off)",
   not any(f["properties"].get("sym") in ("security", "cctv") for f in pf) and "security" not in pa.body.decode()
   and '"cctv"' not in pa.body.decode())
ok("9. ...nor the picture, an unknown symbol, a symbol drawn as a line, or words with staff notes on them",
   not any(f["properties"]["style"] == "picture" or f["properties"].get("sym") == "dragon" for f in pf)
   and sum(1 for f in pf if f["properties"].get("sym") == "first_aid") == 1
   and "data:image" not in pa.body.decode() and "staff only" not in pa.body.decode() and "jdavis" not in pa.body.decode())
ok("9. ...nor the drawing's file name, its CAD layer, the phase's name or id",
   "CONTRACTOR-LOGISTICS" not in pa.body.decode() and "TW_BARRIER" not in pa.body.decode()
   and "L1 test" not in pa.body.decode() and ph1["phase_id"] not in pa.body.decode())
ok("9. ...each thing carries only the allow-listed look properties and its site",
   all(set(f["properties"]) <= set(SL.PUBLIC_KEYS) | {"site"} and f["properties"]["site"] == "L050" for f in pf))
ok("9. the style table sent: every line and area style, 29 symbols (no security, no CCTV), no import choices",
   len(pj["styles"]["lines"]) == len(ST.LINE_STYLES) and len(pj["styles"]["areas"]) == len(ST.AREA_STYLES)
   and len(pj["styles"]["symbols"]) == len(ST.SYMBOLS) - 2 == 29
   and not ({s["key"] for s in pj["styles"]["symbols"]} & set(ST.PRIVATE_SYMBOLS)) and "choices" not in pj["styles"])
st, pj8 = http(main.public_site_layouts, "2027-08")
pj8 = json.loads(pj8.body)
ok("9. August 2027: outside the phase's months, nothing drawn, but `any` keeps the map's tick", pj8["sites"] == []
   and pj8["features"]["features"] == [] and pj8["any"] is True)
st, pbad = http(main.public_site_layouts, "2027-4")
ok("9. a month must be YYYY-MM", st == 400)
st, pnow = http(main.public_site_layouts, None)
ok("9. no month: this month", st == 200 and re.fullmatch(r"\d{4}-\d{2}", json.loads(pnow.body)["month"]))

# kept until the next write, then built again
read_cache.clear()
b0 = read_cache.STATS["builds"]
http(main.public_site_layouts, "2027-04")
http(main.public_site_layouts, "2027-04")
ok("9. the read is kept: two reads, one build", read_cache.STATS["builds"] - b0 == 1)
as_code("planner123")
v1 = main.get_site_layout("L050")["layout"]["version"]
http(main.set_site_layout_public, "L050", main.SiteLayoutPublicIn(public=False, version=v1))
as_code(None)
st, after_off = http(main.public_site_layouts, "2027-04")
ok("9. switched off again: the next read is built afresh and sends nothing",
   read_cache.STATS["builds"] - b0 == 2 and json.loads(after_off.body)["features"]["features"] == [])
ok("9. public_thing: a thing with no geometry or a symbol not in the table is None",
   SL.public_thing({"properties": {"style": "heras"}}) is None
   and SL.public_thing(F(P1, style="sym", sym="cctv")) is None and SL.public_thing("x") is None)

as_code(None)
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
