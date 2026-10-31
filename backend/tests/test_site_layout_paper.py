"""
Site layouts, PR 5 (31 Oct 2026, task 4c; mockup notes site-layout-paper-mockup-1031, John: "Yes, as recommended"):
a site's layout ON PAPER.

  - site_layout_svg: the style table's symbol and glyph SVG drawn in vector on a ReportLab canvas (no PNG files):
    every symbol and glyph uses only what the drawer reads, the arc maths, relative path commands.
  - site_layout_paper: the layout drawn layer for layer as the map draws it; the legend of only what is in the frame;
    the sheet (A3 / A4, fitted or a stated scale, the four map styles), refusals in words; the PDF read back; the PNG.
  - for_plan: the phase in force in a month for the CLP Site plan, security / CCTV left out (a CLP leaves the company).
  - the endpoints: planner / admin only, the Print panel's read, the PDF and PNG answers, 422 in words, 503 while
    another drawing is read (heavy_reads.solo "site-layout-read").
  - the hooks at source level: route_map_export.plan draws the layout on the Site plan only, clp_doc_pictures gives the
    plan the site's id, clp_doc §4 names the phase or lists "No site layout drawn for <site>"; the Print… item.

The layout is the demo's Tilton Viaduct "Site logistics" phase as live holds it: the National Grid sample DXF placed
with its default rows and the drainage left out (39 things), round the demo package's L019.

WHAT THIS DOES NOT PROVE: what the sheet looks like (the mockup's sheets were looked at; the UI audit does not open a
PDF), Mapbox's picture under it (offline: the "No base map" branch), Postgres, the HTTP layer (stubbed).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_site_layout_paper.py
"""
import io
import json
import math
import os
import re
import sys
import tempfile
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
FIX = os.path.join(HERE, "fixtures", "site_layouts")
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

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


class _Request:
    def __init__(self, headers=None, body=b"", cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = cookies or {}


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

TMP = tempfile.mkdtemp(prefix="rbe_paper_")
from portable import remove_scratch_db, offline, pdf_text   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import export  # noqa: E402
import heavy_reads  # noqa: E402
import limits  # noqa: E402
import site_layouts as SL  # noqa: E402
import site_layout_import as SI  # noqa: E402
import site_layout_styles as ST  # noqa: E402
import site_layout_svg as SVG  # noqa: E402
import site_layout_paper as SP  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
offline(export)                       # Mapbox is never called from a test: the sheet takes its "No base map" branch

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


def http(fn, *a, **k):
    try:
        return 200, fn(*a, **k)
    except _HTTPException as e:
        return e.status_code, e.detail


# =========================================================================== #
#  1. The symbols in vector                                                    #
# =========================================================================== #
glyphs = ST.GLYPHS if isinstance(ST.GLYPHS, dict) else {}
ok("1. the style table has 31 symbols and 9 glyphs to draw", len(ST.SYMBOLS) == 31 and len(glyphs) == 9, str(len(glyphs)))
bad = []
for key, inner in [(s["key"], s["svg"]) for s in ST.SYMBOLS] + [(k, (v["svg"] if isinstance(v, dict) else v))
                                                                for k, v in glyphs.items()]:
    tags, attrs, cmds = SVG.used(inner)
    if not tags <= set(SVG.TAGS) or not attrs <= set(SVG.ATTRS) or not cmds <= set(SVG._ARGS):
        bad.append((key, tags - set(SVG.TAGS), attrs - set(SVG.ATTRS), cmds - set(SVG._ARGS)))
ok("⭐ 1. every symbol and glyph uses only the SVG the drawer reads (a new one with more fails here first)", not bad,
   str(bad[:3]))

from reportlab.pdfgen import canvas as _canvas  # noqa: E402


class _Spy:
    """A ReportLab path stand-in that records the calls (for the arc and path maths)."""
    def __init__(self):
        self.calls = []

    def __getattr__(self, n):
        return lambda *a: self.calls.append((n, a))


class _SpyCanvas:
    def beginPath(self):
        return _Spy()


sp = SVG._path(_SpyCanvas(), "M4 32 A28 28 0 0 0 60 32 Z")
ends = [a[-2:] for n, a in sp.calls if n == "curveTo"]
ok("1. a half circle arc (the stop / go board) is two cubic pieces ending at (60, 32)",
   len(ends) == 2 and abs(ends[-1][0] - 60) < 1e-6 and abs(ends[-1][1] - 32) < 1e-6, str(ends))
mid = ends[0]
ok("1. ...through the circle's lowest point (32, 60): sweep 0 from (4, 32) goes below in the y-down box",
   abs(mid[0] - 32) < 1e-6 and abs(mid[1] - 60) < 1e-6, str(mid))
rp = SVG._path(_SpyCanvas(), "M24 24 h16 l4 18 v-6 z")
pts = [a for n, a in rp.calls if n in ("moveTo", "lineTo")]
ok("1. relative h / l / v follow the pen: (24,24) (40,24) (44,42) (44,36)",
   pts == [(24.0, 24.0), (40.0, 24.0), (44.0, 42.0), (44.0, 36.0)], str(pts))
ok("1. a path that never moves draws nothing", SVG._path(_SpyCanvas(), "z") is None)
buf = io.BytesIO()
cv = _canvas.Canvas(buf, pagesize=(400, 400))
err = raises(lambda: [SVG.draw(cv, s["svg"], 50, 50, 20, 30) for s in ST.SYMBOLS])
cv.showPage()
cv.save()
ok("1. every symbol draws on a canvas, turned", err is None and buf.getvalue()[:4] == b"%PDF", repr(err))

# =========================================================================== #
#  2. The drawing and the legend                                               #
# =========================================================================== #
PKG = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
L019 = next(r for r in PKG["tables"]["locations"] if r["id"] == "L019")
GATES = [g for g in PKG["tables"]["location_gates"] if g["location_id"] == "L019"]
raw = open(os.path.join(FIX, "tilton-logistics-bng.dxf"), "rb").read()
rd = SI.read(raw, "tilton-logistics-bng.dxf", grid="bng", near=[[L019["lon"], L019["lat"]]],
             site=[[L019["lon"], L019["lat"]]])
ch = {x["key"]: x["becomes"] for x in SI.rows(rd["things"], {})}
ch["C-DRAINAGE"] = "skip"
THINGS = SL.placed_things(rd["things"], ch, False, "tilton-logistics-bng.dxf (DXF)")
ok("2. the demo's Site logistics phase, rebuilt as live holds it: 39 things", len(THINGS) == 39, str(len(THINGS)))


def one_of_each():
    """A synthetic phase with every line style, every area style, every symbol and a word, round L019."""
    lon0, lat0 = L019["lon"], L019["lat"]
    out = []
    for i, k in enumerate(ST.LINE_STYLES):
        y = lat0 + 0.0002 * i
        out.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[lon0, y], [lon0 + 0.001, y]]},
                    "properties": {"style": k}})
    for i, k in enumerate(ST.AREA_STYLES):
        x = lon0 - 0.003 + 0.0003 * i
        ring = [[x, lat0], [x + 0.0002, lat0], [x + 0.0002, lat0 + 0.0002], [x, lat0 + 0.0002], [x, lat0]]
        out.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"style": k, **({"radius": 45} if k == "crane_radius" else {})}})
    for i, s in enumerate(ST.SYMBOLS):
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon0 + 0.00005 * i, lat0 - 0.0005]},
                    "properties": {"style": "sym", "sym": s["key"], "rot": 15 * i}})
    out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon0, lat0 - 0.0008]},
                "properties": {"style": "text", "text": "ALL DELIVERIES BOOKED"}})
    return out


ALL = one_of_each()


def P(lon, lat):                       # a plain projection for the drawing checks: 1 m ~ 2 pt round L019
    return ((lon - L019["lon"]) * 2 * 111320 * math.cos(math.radians(L019["lat"])) + 300,
            (lat - L019["lat"]) * 2 * 110540 + 300)


T = SP.prepare(ALL, P)
ok("2. prepare keeps every line, area, symbol and the words (11 + 10 + 31 + 1)", len(T) == 53, str(len(T)))
ok("2. prepare fills a line's colour and width and an area's fill, outline and opacity from the table",
   all(t["p"]["color"] == ST.LINE_STYLES[t["style"]]["color"] and t["p"]["w"] == ST.LINE_STYLES[t["style"]]["w"]
       for t in T if t["kind"] == "line")
   and all(t["p"]["fill"] == ST.AREA_STYLES[t["style"]]["fill"] and t["p"]["opacity"] == ST.AREA_STYLES[t["style"]]["opacity"]
           for t in T if t["kind"] == "area"))
ok("2. a thing of no known style is left out (never drawn as something else)",
   SP.prepare([{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"style": "sym", "sym": "flying_saucer"}}], P) == [])
buf = io.BytesIO()
cv = _canvas.Canvas(buf, pagesize=(1200, 1200))
err = raises(lambda: SP.draw(cv, ALL, P, 2.0))
cv.showPage()
cv.save()
ok("⭐ 2. every line style, area style and symbol draws (one of each)", err is None and len(buf.getvalue()) > 5000, repr(err))
rows = SP.legend_rows(T)
kinds = [r[0] for r in rows]
ok("2. the legend: one row a style used, areas then lines then symbols",
   len(rows) == 52 and kinds == sorted(kinds, key=["area", "line", "sym"].index), str(len(rows)))
ok("2. ...each row named as the style table names it",
   {r[2] for r in rows if r[0] == "line"} == {v["label"] for v in ST.LINE_STYLES.values()}
   and {r[2] for r in rows if r[0] == "sym"} == {s["label"] for s in ST.SYMBOLS}, str([r[2] for r in rows][:6]))
inside = SP.legend_rows(T, lambda x, y: x >= 290)
ok("⭐ 2. only what is inside the frame is in the legend (the areas to the west are out)",
   0 < len(inside) < len(rows) and not any(r[0] == "area" for r in inside), str(len(inside)))
buf = io.BytesIO()
cv = _canvas.Canvas(buf, pagesize=(400, 1200))
err = raises(lambda: [SP.draw_legend_swatch(cv, *r[:2], r[3], 10, 10 + 12 * i) for i, r in enumerate(rows)])
cv.save()
ok("2. every legend row's sample draws", err is None, repr(err))
ok("2. a line's width is in metres with the map's floor: 0.45 m at 2 pt/m = 0.9 pt, never under 0.5 px",
   abs(SP._Pen(None, 2.0, {}).m(0.45, 1) - 0.9) < 1e-9 and SP._Pen(None, 0.1, {}).m(0.45, 1) == 1 * SP.PX_PT)
ok("2. the months in words", (SP.month_words({}), SP.month_words({"month_from": "2027-03"}),
                               SP.month_words({"month_to": "2027-06"}),
                               SP.month_words({"month_from": "2027-03", "month_to": "2027-06"}),
                               SP.month_words({"month_from": "2027-03", "month_to": "2027-03"})) ==
   ("Every month", "From Mar 2027", "Until Jun 2027", "Mar 2027 to Jun 2027", "Mar 2027"))
ok("2. the scale in words", SP.scale_words(2500) == "1:2,500" and SP.scale_words(500) == "1:500")


# =========================================================================== #
#  3. The sheet                                                                #
# =========================================================================== #
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


reset_db()
TEN = db.current_tenant()
db.execute("INSERT INTO locations (tenant_id, id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (TEN, "L019", L019["name"], "Site", "destination", L019["lat"], L019["lon"]))
db.execute("INSERT INTO locations (tenant_id, id, name, loc_type, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (TEN, "L001", "Quarry (fictional)", "Quarry", "origin", 52.7, -0.95))
for g in GATES:
    db.execute("INSERT INTO location_gates (tenant_id, id, location_id, name, direction, lat, lon, active) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (TEN, g["id"], "L019", g["name"], g["direction"], g["lat"], g["lon"], True))
access.set_current("planner123")
e = raises(lambda: SP.sheet("L019"))
ok("3. a site with no layout: refused in words", isinstance(e, SP.SheetError) and str(e) == "This site has no layout yet.", repr(e))
PH = SL.add_phase("L019", {"name": "Site logistics", "features": THINGS}, "harness")
PH = PH if isinstance(PH, str) else PH.get("id")
lay = SL.get("L019")
ok("3. the phase saved with its 39 things", lay and lay["phases"][0]["things"] == 39 and lay["phases"][0]["id"] == PH)
S3 = SP.sheet("L019")
S4 = SP.sheet("L019", PH, "a4")
ok("⭐ 3. fitted: 1:2,500 at A3, 1:5,000 at A4 (as the mockup measured), Streets the default map",
   (S3["denom"], S3["fitted"], S4["denom"], S3["style"], S3["page"]) == (2500, True, 5000, "streets", "a3"),
   str((S3["denom"], S4["denom"], S3["style"])))
S1 = SP.sheet("L019", PH, "a4", "1:1,000", "aerial")
ok("3. a stated scale is kept ('1:1,000' and '1000' both read), the map style asked for", S1["denom"] == 1000
   and not S1["fitted"] and S1["style"] == "aerial" and SP.sheet("L019", None, "a4", "1000")["denom"] == 1000)
ok("3. the frame keeps the page's proportions (A3: 420 - 20 - 84 - 5 by 277 mm)",
   abs(S3["frame_w_mm"] - 311) < 1e-9 and abs(S3["frame_h_mm"] - 277) < 1e-9)
for args, words in ((("L019", PH, "a2"), "The page is A3 or A4."),
                    (("L019", PH, "a3", "1:300"), "The scale is one of"),
                    (("L019", PH, "a3", "big"), "The scale is a number"),
                    (("L019", "PH999"), "That phase is not on this site's layout."),
                    (("L404",), "That site is not on this network.")):
    e = raises(lambda: SP.sheet(*args))
    ok(f"3. refused in words: {words}", isinstance(e, SP.SheetError) and str(e).startswith(words), repr(e))
ok("3. no demo notice set here: no demo tag on the map", S3["map_demo_tag"] is None)

PDF = SP.build_pdf(S3)
TXT = pdf_text(PDF)
ok("3. a PDF of one page", PDF[:4] == b"%PDF" and PDF.count(b"/Type /Page\n") + PDF.count(b"/Type /Page ") +
   PDF.count(b"/Type /Page/") >= 1 and b"/Count 1" in PDF)
ok("3. A3 landscape: 1190.55 x 841.89 points", re.search(rb"/MediaBox \[\s*0 0 1190\.55\d* 841\.88\d*", PDF) is not None,
   str(re.findall(rb"/MediaBox[^\]]*\]", PDF)[:1]))
flat = " ".join(TXT.split())
for want in (L019["name"], "Site layout", "Site logistics", "Every month", "Scale 1:2,500 at A3",
             "A planning drawing. Check on site before work starts.", "Solid hoarding", "One-way traffic", "Site gate",
             "Areas", "Lines", "Symbols"):
    ok(f"3. the sheet says: {want}", want in flat, flat[:200])
ok("3. offline: the sheet says it has no base map, and draws the layout anyway",
   "No base map" in flat and S3.get("basemap_ok") is False)
ok("3. the scale bar's last figure in metres", re.search(r"\b100 m\b", flat) is not None, flat[-300:])
ok("🔴 3. no back-end word on the sheet", not re.search(r"\b(server|endpoint|API|token|geometry|cached)\b", flat, re.I))
S4p = SP.build_pdf(SP.sheet("L019", PH, "a4", "1000"))
ok("3. A4 at 1:1,000: 841.89 x 595.28 points and says so", re.search(rb"/MediaBox \[\s*0 0 841\.88\d* 595\.27\d*", S4p)
   is not None and "Scale 1:1,000 at A4" in " ".join(pdf_text(S4p).split()))
PNG = SP.build_png(PDF)
from PIL import Image  # noqa: E402
im = Image.open(io.BytesIO(PNG))
ok("3. the PNG: the same page at 200 dpi (3,307 x 2,339 px at A3)", PNG[:8] == b"\x89PNG\r\n\x1a\n"
   and abs(im.size[0] - 3307) <= 2 and abs(im.size[1] - 2339) <= 2, str(im.size))

# =========================================================================== #
#  4. The CLP Site plan's layout (for_plan)                                    #
# =========================================================================== #
priv = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [L019["lon"], L019["lat"]]},
         "properties": {"style": "sym", "sym": k}} for k in ST.PRIVATE_SYMBOLS]
PH2 = SL.add_phase("L019", {"name": "Deck", "month_from": "2027-06", "month_to": "2027-08",
                            "features": THINGS[:5] + priv}, "harness")
PH2 = PH2 if isinstance(PH2, str) else PH2.get("id")
import weeks  # noqa: E402


def mi_of(y, m):
    return next(i for i in range(1, 200) if weeks._month_of(i) == (y, m))


jul = mi_of(2027, 7)
F7 = SP.for_plan("L019", jul)
ok("⭐ 4. in a month two phases cover, the later one is in force (the Deck, Jun to Aug 2027)",
   F7 and F7["phase"] == "Deck" and F7["months"] == "Jun 2027 to Aug 2027", str(F7 and F7["phase"]))
ok("🔴 4. security and CCTV are left out of the CLP's plan", F7 and len(F7["things"]) == 5
   and not any((t["properties"] or {}).get("sym") in ST.PRIVATE_SYMBOLS for t in F7["things"]))
ok("4. ...kept when asked (the staff's own sheet prints them)", len(SP.for_plan("L019", jul, private=True)["things"]) == 7)
F1 = SP.for_plan("L019", mi_of(2027, 1))
ok("4. outside the Deck's months the every-month phase is in force", F1 and F1["phase"] == "Site logistics"
   and len(F1["things"]) == 39)
ok("4. a site with no layout, or a bad id: None (a plan without a layout is still a plan)",
   SP.for_plan("L001", jul) is None and SP.for_plan("L404", jul) is None)
lay = SL.get("L019")
ph2 = next(p for p in lay["phases"] if p["id"] == PH2)
ok("4. the phase in force by month string too", SP.phase_in_force("L019", "2027-07")["id"] == PH2
   and SP.phase_in_force("L019", "2027-09")["id"] == PH)

# =========================================================================== #
#  5. The endpoints                                                            #
# =========================================================================== #
access.set_current(None)
ok("5. signed out: the Print panel's read, the PDF and the PNG are refused (401)",
   http(main.site_layout_sheet_info, "L019")[0] == 401 and http(main.site_layout_sheet_pdf, "L019")[0] == 401
   and http(main.site_layout_sheet_png, "L019")[0] == 401)
access.set_current("submitter123")
ok("5. a team code cannot print a site layout (403: planner or admin)",
   http(main.site_layout_sheet_pdf, "L019")[0] == 403 and http(main.site_layout_sheet_info, "L019")[0] == 403)
access.set_current("planner123")
st, info = http(main.site_layout_sheet_info, "L019", PH)
ok("⭐ 5. the Print panel's read: A3 fitted 1:2,500, A4 1:5,000, the scales and the four styles, Streets first",
   st == 200 and [(p["key"], p["fitted"]) for p in info["pages"]] == [("a3", 2500), ("a4", 5000)]
   and info["scales"] == list(SP.SCALES) and set(info["styles"]) == {"light", "streets", "outdoors", "aerial"}
   and info["style"] == "streets", str(info)[:200])
st, r = http(main.site_layout_sheet_pdf, "L019", PH, "a3", None, None)
ok("5. the PDF: application/pdf, a download named for the site, phase, page and scale",
   st == 200 and r.media_type == "application/pdf" and r.body[:4] == b"%PDF"
   and 'filename="site-layout-L019-Site-logistics-a3-1-2500.pdf"' in r.headers["Content-Disposition"]
   and r.headers["Cache-Control"] == "no-store", str(getattr(r, "headers", r))[:200])
st, r = http(main.site_layout_sheet_png, "L019", PH, "a4", "500", "light")
ok("5. the PNG at A4 1:500 on Light", st == 200 and r.media_type == "image/png" and r.body[:4] == b"\x89PNG"
   and 'filename="site-layout-L019-Site-logistics-a4-1-500.png"' in r.headers["Content-Disposition"])
ok("5. a bad scale, page or phase: 422 in words; a bad style: 422",
   http(main.site_layout_sheet_pdf, "L019", PH, "a3", "300")[0] == 422
   and http(main.site_layout_sheet_pdf, "L019", PH, "a5")[1] == "The page is A3 or A4."
   and http(main.site_layout_sheet_pdf, "L019", "PH999")[1] == "That phase is not on this site's layout."
   and http(main.site_layout_sheet_pdf, "L019", PH, "a3", None, "neon")[0] == 422)
ok("5. a site with no layout: 422 'This site has no layout yet.'",
   http(main.site_layout_sheet_info, "L001")[1] == "This site has no layout yet.")
held = threading.Event()
done = threading.Event()


def _hold():
    with heavy_reads.solo("site-layout-read"):
        held.set()
        done.wait(10)


th = threading.Thread(target=_hold)
th.start()
held.wait(5)
_was = heavy_reads.SOLO_WAIT_S
heavy_reads.SOLO_WAIT_S = 0.1
st, why = http(main.site_layout_sheet_pdf, "L019", PH)
heavy_reads.SOLO_WAIT_S = _was
done.set()
th.join(5)
ok("⭐ 5. drawn ALONE: while a drawing is read, a sheet is 503 in words", st == 503
   and why == "Another site layout is being drawn. Try again in a minute.", f"{st} {why}")
MAIN0 = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("5. printing writes nothing: the three are GETs (no audit row, no data version)",
   all(f'@app.get("/api/locations/{{location_id}}/site-layout/sheet{x}")' in MAIN0 for x in ("", ".pdf", ".png")))
ok("5. the symbol 'welfare' is named Welfare cabin in the legend, the area 'welfare' Welfare compound",
   ("sym", "welfare", "Welfare cabin") in [r[:3] for r in rows] and ("area", "welfare", "Welfare compound") in [r[:3] for r in rows])

# =========================================================================== #
#  6. The hooks, at source level                                               #
# =========================================================================== #
RME = open(os.path.join(BACKEND, "route_map_export.py"), encoding="utf-8").read()
EXP = open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read()
PIC = open(os.path.join(BACKEND, "clp_doc_pictures.py"), encoding="utf-8").read()
DOC = open(os.path.join(BACKEND, "clp_doc.py"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
ok("6. route_map_export: the layout only on the Site plan, the phase in force in the plan's month, never raising",
   'if layout and kind == "site"' in RME and "site_layout_paper.for_plan(loc, S[\"month_index\"])" in RME
   and '"loc_id": loc_id' in RME)
ok("6. export: the layout drawn under the routes on the plan, the panel's rows only what is in the frame, at most 12",
   "site_layout_paper.draw(c, LY[\"things\"]" in EXP and "ROUTE_MAP_PANEL_MAX_LAYOUT = 12" in EXP
   and "Site layout · " in EXP and "on the site layout sheet" in EXP)
ok("6. the CLP's site plans know the site (loc_id) and say which phase they drew",
   '"loc_id": s["id"]' in PIC and '"layout": LY.get("phase")' in PIC)
ok("6. clp_doc §4: names the phase, or lists 'No site layout drawn for <site>' to complete",
   "site_layout_paper.for_plan(s[\"id\"]" in DOC and "No site layout drawn for {s['name']}" in DOC
   and "is drawn on its site plan in 2.2" in DOC)
import clp_doc  # noqa: E402
ok("6. §4's months mid-sentence keep a month's capital", (clp_doc._lower_lead("Every month"), clp_doc._lower_lead("From Mar 2027"),
                                                       clp_doc._lower_lead("Mar 2027 to Jun 2027")) ==
   ("every month", "from Mar 2027", "Mar 2027 to Jun 2027"))
ok("6. the page: Print… in each phase's ⋯ menu, the panel's Page / Scale / Map and PDF / PNG",
   "onClick={() => openPrint(p)}>Print…</button>" in APP and 'data-site-layout-print="1"' in APP
   and "/site-layout/sheet.${kind}?" in APP and "/site-layout/sheet?phase=" in APP
   and 'aria-label="Page"' in APP and 'printSheet("pdf")' in APP and 'printSheet("png")' in APP)
ok("6. the panel's failure goes through errSay (no status number on a screen)",
   'errSay("The sheet could not be made.", e)' in APP and 'errSay("The print settings could not be read.", e)' in APP)
MAIN = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("6. the sheet is drawn in heavy_reads.solo under the drawing reads' name",
   MAIN.count('heavy_reads.solo("site-layout-read"') >= 2)
ok("6. no PNG files of the symbols: drawn from the style table's SVG", not os.path.isdir(os.path.join(BACKEND, "symbols"))
   and "import site_layout_svg as svg" in open(os.path.join(BACKEND, "site_layout_paper.py"), encoding="utf-8").read())

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\ntest_site_layout_paper: {PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
