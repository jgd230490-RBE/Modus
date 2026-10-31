"""
Site layouts, PR 3 (31 Oct 2026, task 4c; plan notes site-layouts-plan-1030.md §8, mockup
notes/site-layout-pictures-mockup-1031/, John's Q1–Q11 "Yes, as recommended"): pictures and PDF pages pinned on a site
layout by their four corners.

Holds: the picture made once (a PDF page drawn at 200 dpi, never past 4,096 dots a side; a photo the right way up and
kept as JPEG; white made see-through, a soft edge), the refusals in plain words (not a picture, a DWG, a password PDF,
a page that is not there, over 10 MB, over 60 million dots, the eleventh picture), the landing (a PDF at its true size
from its paper and scale, else 150 m wide, north up), the corners (moved, a side over 5 km refused), the version check,
a phase's pictures going with it, the staff reads (the layout, the summary, the staff Route map), the image read (staff
code or staff cookie 200 and private; the map password's cookie and no credential 401), the audit row, no kept read
thrown away, the organisation file, and NEVER PUBLIC: every /api/public/ read in main.py, called with the demo loaded
and a picture pinned, carries no picture, id or address.

WHAT THIS DOES NOT PROVE: the editor and the staff map (parse_frontend / parse_map / the UI audit, after PR 2), Postgres,
the HTTP layer (stubbed), the memory on Render (the harness prints this laptop's figure).
Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_site_layout_pictures.py
"""
import asyncio
import base64
import inspect
import io
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


class _URL:
    def __init__(self, path):
        self.path = path


class _Request:
    def __init__(self, headers=None, body=b"", cookies=None, path="/", query=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = cookies or {}
        self.url = _URL(path)
        self.query_params = dict(query or {})
        self.client = None

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

TMP = tempfile.mkdtemp(prefix="rbe_pictures_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.setdefault("GATE_SECRET", "site-layout-pictures-harness-secret")
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import gate  # noqa: E402
import heavy_reads  # noqa: E402
import limits  # noqa: E402
import tenant_package  # noqa: E402
import users  # noqa: E402
import site_layouts as SL  # noqa: E402
import site_layout_pictures as PIC  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

from PIL import Image, ImageDraw  # noqa: E402
from reportlab.lib.pagesizes import A3, landscape  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402

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
    db.init_users_db()
    db.init_demo_requests_db()
    config.invalidate()
    config.seed_from_file(conversions)


# ---------------------------------------------------------------------------------------------------- the samples
def pdf_bytes(pages=1, password=None, size=landscape(A3)):
    """A fictional A3 lift plan: white paper, black frame and lines (one PDF, `pages` pages)."""
    buf = io.BytesIO()
    kw = {"pagesize": size}
    if password:
        kw["encrypt"] = password
    c = rl_canvas.Canvas(buf, **kw)
    w, h = size
    for n in range(pages):
        c.setLineWidth(2)
        c.rect(20, 20, w - 40, h - 40)
        c.line(60, 60, w - 60, h - 60)
        c.drawString(40, h - 40, f"LIFT PLAN (fictional) - sheet {n + 1} - 1:500 at A3")
        c.showPage()
    c.save()
    return buf.getvalue()


def png_bytes(w=800, h=600, alpha=False):
    im = Image.new("RGBA" if alpha else "RGB", (w, h), (255, 255, 255, 0) if alpha else (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, w - 10, h - 10], outline=(0, 0, 0, 255) if alpha else (0, 0, 0), width=4)
    d.line([0, 0, w, h], fill=(200, 30, 30, 255) if alpha else (200, 30, 30), width=6)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def jpg_bytes(w=1200, h=800, orientation=None):
    im = Image.new("RGB", (w, h), (90, 120, 80))
    ImageDraw.Draw(im).rectangle([0, 0, w // 4, h // 4], fill=(250, 250, 20))     # a yellow corner, top-left
    out = io.BytesIO()
    if orientation:
        ex = Image.Exif()
        ex[0x0112] = orientation
        im.save(out, "JPEG", quality=90, exif=ex.tobytes())
    else:
        im.save(out, "JPEG", quality=90)
    return out.getvalue()


def img_of(b):
    return Image.open(io.BytesIO(b))


# =========================================================================== #
#  1. The picture made once                                                    #
# =========================================================================== #
P1 = pdf_bytes()
m = PIC.make(P1, "lift.pdf")
ok("1. a PDF page is drawn at 200 dpi: A3 landscape = 3,308 x 2,339 dots, kept as PNG", m["kind"] == "pdf"
   and (m["width"], m["height"]) == (3308, 2339) and m["mime"] == "image/png" and m["image"][:8] == b"\x89PNG\r\n\x1a\n",
   str((m["width"], m["height"], m["mime"])))
ok("1. ...its paper is read from the page: 420 x 297 mm", m["paper_mm"] == [420.0, 297.0], str(m["paper_mm"]))
ok("1. ...white is made see-through by default for a PDF (the paper clear, the lines kept)", m["clear"] is True)
im = img_of(m["image"])
ok("1. ...the paper is clear, a line is solid", im.mode == "RGBA" and im.getpixel((5, 5))[3] == 0
   and im.getpixel((int(20 / 72 * 200), im.height // 2))[3] == 255, str((im.mode, im.getpixel((5, 5)))))
m_keep = PIC.make(P1, "lift.pdf", clear=False)
ok("1. white kept when asked: no clear dot", img_of(m_keep["image"]).convert("RGBA").getextrema()[3][0] == 255)
ok("1. the white rule: dark kept, near-white clear, a soft edge between",
   PIC._clear_white(Image.new("RGB", (1, 1), (30, 30, 30))).getpixel((0, 0))[3] == 255
   and PIC._clear_white(Image.new("RGB", (1, 1), (250, 248, 252))).getpixel((0, 0))[3] == 0
   and 0 < PIC._clear_white(Image.new("RGB", (1, 1), (221, 221, 221))).getpixel((0, 0))[3] < 255)
big = PIC.make(pdf_bytes(size=(2384, 3370)), "a0.pdf")      # A0 portrait in points
ok("1. a big page is drawn smaller, never past 4,096 dots a side (A0 -> 2,898 x 4,096)",
   max(big["width"], big["height"]) == 4096 and big["width"] < big["height"], str((big["width"], big["height"])))
ok("1. ...and its paper is still its real size (841 x 1,189 mm)",
   abs(big["paper_mm"][0] - 841) < 1 and abs(big["paper_mm"][1] - 1189) < 1, str(big["paper_mm"]))
two = pdf_bytes(pages=2)
m2 = PIC.make(two, "two.pdf", page=2)
ok("1. the page asked for is drawn (page 2 of 2)", m2["page"] == 2 and m2["pages"] == 2)
ph = PIC.make(jpg_bytes(), "photo.jpg")
ok("1. a photo is kept as JPEG with nothing made clear (deviation from plan §2: a photo as PNG would not fit 5 MB)",
   ph["kind"] == "jpg" and ph["mime"] == "image/jpeg" and ph["clear"] is False and ph["image"][:3] == b"\xff\xd8\xff")
rot = PIC.make(jpg_bytes(orientation=6), "phone.jpg")
ok("1. a phone photo is turned the right way up (EXIF 6: 1,200 x 800 -> 800 x 1,200)",
   (rot["width"], rot["height"]) == (800, 1200), str((rot["width"], rot["height"])))
pa = PIC.make(png_bytes(alpha=True), "plan.png")
ok("1. a PNG with its own clear parts stays PNG and keeps them", pa["mime"] == "image/png"
   and img_of(pa["image"]).convert("RGBA").getpixel((400, 5))[3] == 0)
huge_jpg = Image.new("RGB", (6000, 4000), (120, 90, 60))
_b = io.BytesIO()
huge_jpg.save(_b, "JPEG", quality=80)
hj = PIC.make(_b.getvalue(), "drone.jpg")
ok("1. a 6,000-dot photo is cut to 4,096 a side", max(hj["width"], hj["height"]) == 4096, str((hj["width"], hj["height"])))
ok("1. every kept picture is at most 5 MB", all(len(x["image"]) <= PIC.MAX_STORED for x in (m, m_keep, big, m2, ph, rot, pa, hj)))

# --- the refusals in words -------------------------------------------------------------------------------------------
def why(fn):
    e = raises(fn)
    return str(e) if isinstance(e, PIC.Problem) else f"not a Problem: {e!r}"


ok("1. not a picture: 'x.txt is not a PNG, JPG or PDF.'", why(lambda: PIC.make(b"hello", "x.txt")) == "x.txt is not a PNG, JPG or PDF.")
ok("1. a DWG is pointed at the drawing import", "DWG" in why(lambda: PIC.make(b"AC1032\x00\x00", "site.dwg")))
ok("1. an empty file", why(lambda: PIC.make(b"", "x.png")) == "The file is empty.")
ok("1. over 10 MB", why(lambda: PIC.make(b"\x89PNG\r\n\x1a\n" + b"0" * (PIC.MAX_BYTES + 1), "x.png")) == "This file is over 10 MB.")
ok("1. a page that is not there", why(lambda: PIC.make(two, "two.pdf", page=3)) == "two.pdf has 2 pages; there is no page 3.")
ok("1. a PDF behind a password", "password" in why(lambda: PIC.make(pdf_bytes(password="pw"), "locked.pdf")))
ok("1. a broken PDF", why(lambda: PIC.make(b"%PDF-1.4 nonsense", "bad.pdf")) == "bad.pdf could not be read as a PDF.")
_bomb = io.BytesIO()
Image.new("1", (8000, 8000)).save(_bomb, "PNG")      # 64 million dots, a few kB on disk
ok("1. a picture over 60 million dots is refused before it is decoded",
   "too large" in why(lambda: PIC.make(_bomb.getvalue(), "bomb.png")))
ok("1. a broken PNG", why(lambda: PIC.make(b"\x89PNG\r\n\x1a\n garbage", "bad.png")) == "bad.png could not be read as a picture.")

# --- memory (this laptop; Render's figure is the 🧮 line on live) ---------------------------------------------------
mb0 = heavy_reads.memory_mb()
_ = PIC.make(pdf_bytes(size=(2384, 3370)), "a0.pdf")
mb1 = heavy_reads.memory_mb()
print(f"   memory: an A0 page drawn at 4,096 dots: {mb0:.0f} -> {mb1:.0f} MB" if mb0 and mb1 else "   memory: not readable here")

# =========================================================================== #
#  2. Landing and corners                                                      #
# =========================================================================== #
C = [-0.85, 52.62]
cs, words = PIC.landing(C, 3307, 2339, [420.0, 297.0], 500)
w_m = PIC._metres(cs[0], cs[1])
h_m = PIC._metres(cs[1], cs[2])
ok("2. a PDF with its scale lands at its true size: A3 at 1:500 = 210 x 148.5 m, north up",
   abs(w_m - 210) < 0.5 and abs(h_m - 148.5) < 0.5 and cs[0][1] == cs[1][1] and cs[0][0] == cs[3][0],
   str((w_m, h_m)))
ok("2. ...centred on the given middle, corners top-left first", cs[0][0] < C[0] < cs[1][0] and cs[2][1] < C[1] < cs[0][1])
ok("2. ...the words say so", words == "at its true size (1:500: 210 × 148.5 m)", words)
cs2, words2 = PIC.landing(C, 800, 600)
ok("2. without a scale it lands 150 m wide, the height from the picture (112.5 m)",
   abs(PIC._metres(cs2[0], cs2[1]) - 150) < 0.5 and abs(PIC._metres(cs2[1], cs2[2]) - 112.5) < 0.5 and words2 == "150 m wide")
ok("2. corners: four places, rounded to 7 places", PIC.clean_corners([[-0.851234567891, 52.6], [-0.85, 52.6],
                                                                       [-0.85, 52.59], [-0.851, 52.59]])[0] == [-0.8512346, 52.6])
ok("2. corners: three are refused", why(lambda: PIC.clean_corners([[0, 52], [0.001, 52], [0.001, 51.999]])) ==
   "A picture needs its four corners.")
ok("2. corners: not a place", why(lambda: PIC.clean_corners([[0, 52], [0.001, 52], ["x", 1], [0, 51.999]])) ==
   "A corner is not a place on the map.")
ok("2. corners: a side over 5 km is refused", "over 5 km" in why(lambda: PIC.clean_corners([[0, 52], [0.1, 52], [0.1, 51.99], [0, 51.99]])))
ok("2. corners: two on top of each other", "on top of each other" in why(lambda: PIC.clean_corners([[0, 52], [0, 52], [0.001, 51.999], [0, 51.999]])))
ok("2. corners move freely (a slanted scan is kept as sent)",
   PIC.clean_corners([[0, 52.001], [0.0012, 52.0013], [0.0011, 51.9999], [-0.0001, 51.9998]])[1] == [0.0012, 52.0013])

# =========================================================================== #
#  3. Through the endpoints                                                    #
# =========================================================================== #
reset_db()
PKG = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
res = tenant_package.import_tenant(PKG, replace=True)
ok("3. the demo package loads (the never-public reads run on it)", res.get("ok"), str(res)[:200])
L019 = next(r for r in PKG["tables"]["locations"] if r["id"] == "L019")


def as_code(code):
    return access.set_current(code)


def http(fn, *a, **k):
    """(status, answer) for a main.* endpoint: 200 and the value, or the HTTPException's code and detail."""
    try:
        return 200, fn(*a, **k)
    except _HTTPException as e:
        return e.status_code, e.detail


def add_ep(data, name, loc="L019", **q):
    req = _Request({"content-length": str(len(data))}, data, path=f"/api/locations/{loc}/site-layout/pictures",
                   query=dict(q, name=name))
    args = dict(name=name, page=q.get("page", 1), scale=q.get("scale"), clear=q.get("clear"), phase_id=q.get("phase_id"),
                every=q.get("every", False), lon=q.get("lon"), lat=q.get("lat"))
    return http(lambda: asyncio.run(main.add_site_layout_picture(req, location_id=loc, **args)))


STAFF = {gate.COOKIE: gate.sign(gate.LEVEL_STAFF)}
MAPC = {gate.COOKIE: gate.sign(gate.LEVEL_MAP)}

as_code(None)
ok("3. signed out: adding is refused (401)", add_ep(P1, "lift.pdf")[0] == 401)
as_code("submitter123")
ok("3. a team login cannot add a picture (403)", add_ep(P1, "lift.pdf")[0] == 403)
as_code("planner123")
st, lay = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="Piers", month_from="2027-03",
                                                                          month_to="2027-06"))
ok("3. a phase to pin on", st == 200, str(lay)[:200])
PH1 = lay["phase_id"]
st, lay2 = http(main.add_site_layout_phase, "L019", main.SiteLayoutPhaseIn(name="Deck", month_from="2027-07"))
PH2 = lay2["phase_id"]
mid = [L019["lon"], L019["lat"]]

audit_before = len(db.query("SELECT id FROM audit_log WHERE tenant_id = ?", (db.current_tenant(),)))
v0 = db.data_version()
st, a1 = add_ep(P1, "Lift plan.pdf", scale="500", phase_id=PH1, lon=mid[0], lat=mid[1])
ok("3. a planner pins page 1 of a PDF at 1:500 on a phase", st == 200 and a1["picture"]["id"] == "PI001"
   and a1["picture"]["phase_id"] == PH1 and a1["picture"]["kind"] == "pdf", str(a1)[:300])
pic = a1["picture"]
ok("3. ...it lands 210 m wide on the site, north up, in plain words",
   abs(PIC._metres(pic["corners"][0], pic["corners"][1]) - 210) < 0.5
   and a1["words"] == "Added at its true size (1:500: 210 × 148.5 m), north up. Move it onto its place.", a1["words"])
# NARROWED 31 Oct 2026 (the editor): the address carries when it was added, not the version (moving the corners must
# not fetch the image again; a re-used id must not be served from the browser's old copy)
STAMP1 = PIC._stamp(db.query("SELECT created_at FROM site_layout_pictures WHERE tenant_id = ? AND id = 'PI001'",
                             (db.current_tenant(),))[0]["created_at"])
ok("3. ...its name is the file's without .pdf; opacity 0.6; not on the sheet; its address carries when it was added",
   pic["name"] == "Lift plan" and pic["opacity"] == 0.6 and pic["on_sheet"] is False and len(STAMP1) >= 14
   and pic["url"] == "/api/site-layouts/pictures/PI001/image?v=" + STAMP1, pic["url"])
aud = db.query("SELECT path, detail FROM audit_log WHERE tenant_id = ? ORDER BY rowid DESC LIMIT 1", (db.current_tenant(),))
ok("3. ...one audit row, with the query and no file in it",
   len(db.query("SELECT id FROM audit_log WHERE tenant_id = ?", (db.current_tenant(),))) == audit_before + 1
   and aud[0]["path"] == "/api/locations/L019/site-layout/pictures" and "Lift plan" in (aud[0]["detail"] or "")
   and "JVBER" not in (aud[0]["detail"] or ""), str(aud)[:300])
ok("3. ...and no kept read is thrown away (the data version did not move)", db.data_version() == v0,
   f"{v0} -> {db.data_version()}")
ok("3. the upload path is not audited by the middleware (its own row) and ends no kept read; a picture's PATCH / DELETE "
   "is audited and ends none",
   not main._audited("/api/locations/L019/site-layout/pictures") and main._audited("/api/site-layouts/pictures/PI001")
   and main._PICTURE_PATH.match("/api/site-layouts/pictures/PI001")
   and main._PICTURE_PATH.match("/api/locations/L019/site-layout/pictures")
   and not main._PICTURE_PATH.match("/api/site-layouts/phases/PH001") and "site_layout_pictures" in db.NO_DATA_TABLES)

st, a2 = add_ep(two, "Sheets.pdf", page="2", every=True, clear="0")
ok("3. page 2 of a two-page PDF, every phase, white kept: named '(page 2)', 150 m wide (no scale), 'Page 2 of 2.'",
   st == 200 and a2["picture"]["every"] and a2["picture"]["phase_id"] is None and a2["picture"]["name"] == "Sheets (page 2)"
   and a2["picture"]["clear"] is False and a2["words"].startswith("Page 2 of 2. Added 150 m wide"), str(a2)[:300])
st, a3 = add_ep(jpg_bytes(), "drone.jpg", phase_id=PH2)
ok("3. a photo on the Deck phase lands 150 m wide on the site's middle", st == 200 and a3["picture"]["mime"] == "image/jpeg"
   and abs(PIC._metres(a3["picture"]["corners"][0], a3["picture"]["corners"][1]) - 150) < 0.5)
ok("3. refusals through the endpoint are 400 in words",
   add_ep(b"hello", "notes.txt")[1] == "notes.txt is not a PNG, JPG or PDF." and add_ep(b"hello", "notes.txt")[0] == 400
   and add_ep(P1, "x.pdf", scale="abc")[1] == "The scale must be a number, like 500 for 1:500."
   and add_ep(P1, "x.pdf", scale="5")[1] == "The scale must be from 1:10 to 1:100,000."
   and add_ep(P1, "x.pdf", phase_id="PH999")[1] == "That phase is not there any more. Reload to see the layout."
   and add_ep(P1, "x.pdf", loc="L999")[1] == "That location is not set up here.")
st, d = add_ep(b"\x89PNG" + b"0" * (PIC.MAX_BYTES + 10), "big.png")
ok("3. over 10 MB is 413 before it is read", st == 413 and d == "This file is over 10 MB.")

# while another drawing or picture is being read, a picture waits at most 5 s, then 503
import threading  # noqa: E402
hold, go = threading.Event(), threading.Event()


def _hold():
    with heavy_reads.solo("site-layout-read"):
        hold.set()
        go.wait(20)


t = threading.Thread(target=_hold)
t.start()
hold.wait(5)
_old = heavy_reads.SOLO_WAIT_S
heavy_reads.SOLO_WAIT_S = 0.2
st, d = add_ep(P1, "busy.pdf")
heavy_reads.SOLO_WAIT_S = _old
go.set()
t.join()
ok("3. another drawing being read: 503 'Another drawing or picture is being read. Try again in a minute.'",
   st == 503 and d == "Another drawing or picture is being read. Try again in a minute.", str((st, d)))

# --- reads ------------------------------------------------------------------------------------------------------------
as_code("submitter123")
st, g = http(main.get_site_layout, "L019")
lay = g["layout"]
ok("3. a team login reads the layout with its pictures (metadata only, no image in the read)",
   st == 200 and [p["id"] for p in lay["pictures"]] == ["PI001", "PI002", "PI003"]
   and not any("image" in p or "image_b64" in p for p in lay["pictures"])
   and not re.search(r"image_b64|iVBORw0KGgo|/9j/", json.dumps(lay)), str(lay.get("pictures"))[:300])
ok("3. ...each phase counts its own pictures ('· 1 picture'); the every-phase one is not counted on a phase",
   {p["id"]: p["pictures"] for p in lay["phases"]}.get(PH1) == 1 and {p["id"]: p["pictures"] for p in lay["phases"]}.get(PH2) == 1)
ok("3. the Locations summary counts the site's pictures (3)", main.site_layout_summary()["sites"]["L019"]["pictures"] == 3)
as_code(None)
fm = main.site_layouts_map("2027-04", _Request(cookies=STAFF))
ok("3. the staff Route map in Apr 2027: the Piers picture and the every-phase one, with their site; not the Deck's",
   sorted(p["id"] for p in fm["pictures"]) == ["PI001", "PI002"] and all(p["site"] == "L019" for p in fm["pictures"]),
   str([p["id"] for p in fm["pictures"]]))
fm2 = main.site_layouts_map("2027-08", _Request(cookies=STAFF))
ok("3. ...in Aug 2027 the Deck's and the every-phase one", sorted(p["id"] for p in fm2["pictures"]) == ["PI002", "PI003"])
fm3 = main.site_layouts_map("2026-01", _Request(cookies=STAFF))
ok("3. ...in a month with no phase of the site in force, none (an every-phase picture shows with its layout)",
   fm3["pictures"] == [])

# --- the image --------------------------------------------------------------------------------------------------------
st, r = http(main.site_layout_picture_image, "PI001", _Request(cookies=STAFF))
ok("3. the staff gate cookie reads the image: a PNG, private, its ETag by when it was added",
   st == 200 and r.media_type == "image/png" and r.body[:8] == b"\x89PNG\r\n\x1a\n"
   and r.headers["Cache-Control"].startswith("private") and r.headers["ETag"] == f'"PI001-{STAMP1}"')
st, r304 = http(main.site_layout_picture_image, "PI001", _Request({"If-None-Match": f'"PI001-{STAMP1}"'}, cookies=STAFF))
ok("3. ...and answers 304 to its own ETag", st == 200 and r304.status_code == 304 and r304.body is None)
ok("3. the map password's cookie and no credential get 401 for the image",
   http(main.site_layout_picture_image, "PI001", _Request(cookies=MAPC))[0] == 401
   and http(main.site_layout_picture_image, "PI001", _Request())[0] == 401
   and http(main.site_layout_picture_image, "PI001", None)[0] == 401)
as_code("submitter123")
ok("3. a team login's code reads it (200); a gone picture is 404",
   http(main.site_layout_picture_image, "PI003", _Request())[0] == 200
   and http(main.site_layout_picture_image, "PI099", _Request())[0] == 404)

# --- edits ------------------------------------------------------------------------------------------------------------
ok("3. a team login cannot move or delete a picture (403)",
   http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=1, opacity=0.5))[0] == 403
   and http(main.delete_site_layout_picture, "PI001", 1)[0] == 403)
as_code("planner123")
turned = [[c[0] + 0.0001, c[1]] for c in pic["corners"]]
v0 = db.data_version()
st, e1 = http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=1, corners=turned, opacity=0.8,
                                                                              name="Lift plan rev B"))
ok("3. a planner moves the corners, sets the opacity and renames it: version 2, the SAME address (the image is unchanged)",
   st == 200 and e1["picture"]["version"] == 2 and e1["picture"]["opacity"] == 0.8
   and e1["picture"]["name"] == "Lift plan rev B" and e1["picture"]["corners"][0] == [round(turned[0][0], 7), turned[0][1]]
   and e1["picture"]["url"] == pic["url"], str(e1)[:300])
ok("3. ...no kept read thrown away", db.data_version() == v0)
ok("3. the old version is refused in words (409)",
   http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=1, opacity=0.3)) == (409, SL.STALE))
ok("3. an opacity of 0 is kept at 0.05 (never invisible by mistake); a word is refused",
   http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=2, opacity=0))[1]["picture"]["opacity"] == 0.05)
ok("3. a corner moved across the country is refused (400)",
   http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(
       version=3, corners=[[-0.85, 52.6], [-0.5, 52.6], [-0.5, 52.5], [-0.85, 52.5]]))[0] == 400)
st, e2 = http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=3, every=True))
ok("3. 'Show in every phase' moves it off its phase", st == 200 and e2["picture"]["every"] and e2["picture"]["phase_id"] is None)
st, e3 = http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=4, every=False, phase_id=PH1))
ok("3. ...and back onto the Piers phase", st == 200 and e3["picture"]["phase_id"] == PH1)
ok("3. a blank name is refused", http(main.edit_site_layout_picture, "PI001", main.SiteLayoutPictureIn(version=5, name="  "))
   == (400, "Give the picture a name."))

# ten a site
for i in range(7):
    add_ep(png_bytes(200, 100), f"p{i}.png", every=True)
ok("3. a site holds ten pictures; the eleventh is refused in words",
   len(main.get_site_layout("L019")["layout"]["pictures"]) == 10
   and add_ep(png_bytes(200, 100), "eleven.png") == (400, "This site has 10 pictures, the most it can have. Delete one first."))

# delete: the version, then a phase takes its own pictures with it
ok("3. deleting with an old version is refused (409)", http(main.delete_site_layout_picture, "PI004", 9)[0] == 409)
st, dd = http(main.delete_site_layout_picture, "PI004", 1)
ok("3. a planner deletes a picture", st == 200 and dd["deleted"] == "PI004"
   and http(main.site_layout_picture_image, "PI004", _Request())[0] == 404)
ph1v = next(p for p in main.get_site_layout("L019")["layout"]["phases"] if p["id"] == PH1)["version"]
http(main.delete_site_layout_phase, PH1, ph1v)
left = [p["id"] for p in main.get_site_layout("L019")["layout"]["pictures"]]
ok("3. deleting the Piers phase deletes its picture; every-phase pictures and the Deck's stay",
   "PI001" not in left and "PI002" in left and "PI003" in left, str(left))

# =========================================================================== #
#  4. NEVER PUBLIC                                                             #
# =========================================================================== #
SRC = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
PUB = re.findall(r'@app\.get\("(/api/public/[^"]+)"\)\s*\n(?:@[^\n]*\n)*(?:async )?def (\w+)\(', SRC)
ok("4. main.py has public reads to check (at least 15)", len(PUB) >= 15, str(len(PUB)))
bodies = {}
for i, (path, fn) in enumerate(PUB):
    start = SRC.index(f"def {fn}(")
    nxt = SRC.find("\n@app.", start)
    bodies[path] = SRC[start: nxt if nxt > 0 else len(SRC)]
ok("4. no public read in main.py calls the pictures, the staff layout reads or the image",
   not [p for p, b in bodies.items() if re.search(r"site_layout_pictures|site_layouts\.(get|for_map|summary)\(|"
                                                  r"site_layout_picture_image|/pictures/", b)],
   str([p for p, b in bodies.items() if "site_layout" in b]))
# NARROWED 31 Oct 2026 (task 4c PR 5): + site_layout_paper.py — the sheet (planners and admins) draws the ticked pictures
ok("4. site_layout_pictures is read only by main.py's staff endpoints, site_layouts' staff reads and the staff sheet (no other module)",
   sorted(f for f in os.listdir(BACKEND) if f.endswith(".py") and f != "site_layout_pictures.py"
          and re.search(r"import site_layout_pictures", open(os.path.join(BACKEND, f), encoding="utf-8").read()))
   == ["main.py", "site_layout_paper.py", "site_layouts.py"])
if hasattr(SL, "for_public_map"):    # PR 4 (claude/site-layout-public): the public layer has an allow-list of its own
    pubsl = json.dumps(SL.for_public_map("2027-08"))
    ok("4. the public site layout layer (PR 4) carries no picture", "PI00" not in pubsl and "picture" not in pubsl)

# every public read, called with the map password's cookie as the public map would, the demo loaded, pictures pinned
LEAK = re.compile(r"PI0\d\d|/pictures/|image_b64|site_layout_pictures|\"pictures\"|iVBORw0KGgo|/9j/")
as_code(None)
called, leaked, skipped = [], [], []
_offline = None
try:
    from portable import offline   # noqa: E402
    import export  # noqa: E402
    _offline = offline(export)
except Exception:
    pass
for path, fn in PUB:
    f = getattr(main, fn, None)
    if f is None:
        skipped.append(path)
        continue
    sig = inspect.signature(f)
    kw = {}
    good = True
    for name, prm in sig.parameters.items():
        if name == "request":
            kw[name] = _Request(cookies=MAPC, path=path)
        elif name == "month" and prm.default is inspect.Parameter.empty:
            kw[name] = "2027-08"
        elif prm.default is inspect.Parameter.empty:
            good = False
    if not good:
        skipped.append(path)
        continue
    try:
        out = f(**kw)
        if inspect.iscoroutine(out):
            out = asyncio.run(out)
    except _HTTPException as e:
        out = {"status": e.status_code, "detail": e.detail}
    except Exception as e:  # noqa: BLE001  a read that needs the network or a fetched layer: its words still checked
        out = {"error": repr(e)[:200]}
    if isinstance(out, _Response):
        body = out.body if isinstance(out.body, (bytes, bytearray)) else str(out.body).encode()
        text = body.decode("utf-8", "replace")
    else:
        text = json.dumps(out, default=str)
    called.append(path)
    if LEAK.search(text):
        leaked.append(path)
    # the same read for a month the pictures show in
    if "month" in sig.parameters:
        try:
            o2 = f(**dict(kw, month="2027-08"))
            t2 = o2.body.decode("utf-8", "replace") if isinstance(o2, _Response) and isinstance(o2.body, (bytes, bytearray)) \
                else json.dumps(o2, default=str)
            if LEAK.search(t2):
                leaked.append(path + "?month=2027-08")
        except Exception:
            pass
ok("4. every public read was called (none skipped for a required argument)", len(called) >= 15 and not skipped,
   f"called {len(called)}, skipped {skipped}")
ok("4. NO public read carries a picture, its id, its address or its image", not leaked, str(leaked))
st, meta = http(main.meta, _Request(cookies=MAPC))
ok("4. /api/meta's public shape carries no picture either", st == 200 and not LEAK.search(json.dumps(meta, default=str)))

# =========================================================================== #
#  5. The organisation file                                                    #
# =========================================================================== #
ok("5. the table is tenanted, keyed (tenant, id), and in the organisation file after the phases",
   "site_layout_pictures" in db.TENANTED_TABLES
   and tenant_package.ORDER.index("site_layout_pictures") > tenant_package.ORDER.index("site_layout_phases"))
pkg = tenant_package.export_tenant()
rows = pkg["tables"].get("site_layout_pictures") or []
ok("5. the organisation file carries the pictures with their images", len(rows) == len(left)
   and all(r.get("image_b64") for r in rows), str((len(rows), len(left))))
before = {r["id"]: (r["image_b64"], r["corners_json"]) for r in rows}
res = tenant_package.import_tenant(pkg, replace=True)
after = {r["id"]: (r["image_b64"], r["corners_json"]) for r in
         db.query("SELECT id, image_b64, corners_json FROM site_layout_pictures WHERE tenant_id = ?", (db.current_tenant(),))}
ok("5. ...and brings them back byte for byte", res.get("ok") and before == after, str(res)[:200])

as_code(None)
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
