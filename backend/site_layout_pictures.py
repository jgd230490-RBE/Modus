"""
site_layout_pictures.py — a contractor's picture or PDF page pinned on a site layout by its four corners (task 4c PR 3,
31 Oct 2026; plan notes site-layouts-plan-1030.md §2 / §8, mockup notes/site-layout-pictures-mockup-1031/, John's Q1–Q11
"Yes, as recommended").

STAFF ONLY. A picture never reaches the public map: the public reads carry no picture, id or address, and the image
read answers only staff (a code, a login or the staff gate cookie).

* A PNG, JPG or one PDF page, at most MAX_BYTES a file. The file itself is not kept: the server makes the picture ONCE
  when it is added — a PDF page drawn at PDF_DPI (pypdfium2), any picture cut to MAX_SIDE dots a side (Pillow), white
  made see-through when asked (near-white dots clear, a soft edge between) — and keeps that, at most MAX_STORED bytes.
  A drawing or a cleared picture is kept as PNG, a photo as JPEG (plan §2 said PNG; a 4,096-dot photo as PNG would not
  fit 5 MB).
* Kept as base64 text (`image_b64`), as clp_issues.file_b64: one column type on SQLite and Postgres, and the
  organisation file is JSON.
* A picture belongs to one phase, or to every phase (phase_id NULL). At most MAX_PER_SITE a site.
* corners: 4 x [lon, lat] in Mapbox's order — top-left, top-right, bottom-right, bottom-left of the picture.
* It lands north up on the given middle: at its TRUE SIZE when a PDF's scale is typed (the PDF knows its paper), else
  DEFAULT_WIDTH_M wide.
* Every change carries the picture's `version` (site_layouts.STALE when someone saved first).

Making a picture is a heavy job (a 4,096-dot page is ~50 MB of pixels while it is made): main.py runs make() inside
heavy_reads.solo("site-layout-read"), the same name as the drawing reads, so the two never run at once on live's 512 MB.
Every SQL literal carries the tenant.
"""
import base64
import datetime
import io
import json
import math
import re

import db
import site_layouts as SL

MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 4096
MAX_STORED = 5 * 1024 * 1024
#: a picture with more dots than this is refused before it is decoded (a "decompression bomb")
MAX_PIXELS_IN = 60_000_000
PDF_DPI = 200
MAX_PER_SITE = 10
DEFAULT_WIDTH_M = 150.0
DEFAULT_OPACITY = 0.6
JPEG_QUALITY = 85
#: white see-through: a dot whose darkest channel is at least WHITE_FROM is clear; from SOFT_FROM up it fades
WHITE_FROM, SOFT_FROM = 242, 200
#: a pinned picture's side may be at most this long (a wrong drag across the country is refused)
MAX_SIDE_M = 5000.0
MAX_NAME = 80
KINDS = ("png", "jpg", "pdf")
MIME = {"png": "image/png", "jpg": "image/jpeg"}

Problem = SL.Problem
STALE = SL.STALE


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ----------------------------------------------------------------------------------------------------- the picture
def sniff(data, name=""):
    """'png' | 'jpg' | 'pdf' from the first bytes (the name is only for the words); Problem otherwise."""
    head = bytes(data[:8])
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"%PDF"):
        return "pdf"
    nm = str(name or "This file")[:80]
    if re.search(r"\.dwg$", nm, re.I):
        raise Problem(f"{nm} is a DWG drawing. Bring it in as a drawing (save it as DXF), or pin a PDF of it.")
    raise Problem(f"{nm} is not a PNG, JPG or PDF.")


def _clear_white(im):
    """Near-white dots made clear, the edge soft (the mockup's rule, card 4). RGBA in, RGBA out. Pillow only."""
    if im.mode != "RGB" and im.mode != "RGBA":
        im = im.convert("RGBA" if im.mode in ("LA", "PA", "P") or "transparency" in im.info else "RGB")
    return _clear_bands(*(im.getchannel(i) for i in range(len(im.getbands()))))


_LUT = [255 if v < SOFT_FROM else 0 if v >= WHITE_FROM else int(round(255 * (WHITE_FROM - v) / (WHITE_FROM - SOFT_FROM)))
        for v in range(256)]


def _clear_bands(r, g, b, a=None):
    """_clear_white from the separate channels, one 1-byte channel at a time (a 4,096-dot page's whole RGBA picture is
    48 MB: the step never holds two of those at once)."""
    from PIL import Image, ImageChops
    low = ImageChops.darker(r, g)
    low = ImageChops.darker(low, b)
    keep = low.point(_LUT)
    del low
    if a is not None:
        keep = ImageChops.multiply(a, keep)
    return Image.merge("RGBA", (r, g, b, keep))


def _encode(im, as_png):
    out = io.BytesIO()
    if as_png:
        im.save(out, "PNG", compress_level=6)
    else:
        im.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


#: a PDF page is drawn this many dot rows at a time
BAND_ROWS = 256


def _draw_page(pg, scale, clear):
    """A PDF page at `scale`, drawn in bands of BAND_ROWS rows into ONE picture (RGBA when white is made see-through,
    else RGB): only the finished picture and one band are ever held. 31 Oct 2026: drawn whole, an A0 page at 4,096 dots
    peaked +215 MB (pdfium's bitmap, Pillow's copy, the RGBA), then +145 with the copy gone; in bands +60 or so.
    pdfium places each band on the page's own dot grid (pypdfium2's crop is whole dots), so no seam."""
    import math
    from PIL import Image
    W = math.ceil(pg.get_width() * scale)
    H = math.ceil(pg.get_height() * scale)
    out = Image.new("RGBA", (W, H), (255, 255, 255, 0)) if clear else Image.new("RGB", (W, H), (255, 255, 255))
    for y0 in range(0, H, BAND_ROWS):
        y1 = min(H, y0 + BAND_ROWS)
        # crop (left, bottom, right, top) in page units; pypdfium2 turns each into ceil(c * scale) dots
        crop = (0, max(0.0, (H - y1 - 1e-6) / scale), 0, max(0.0, (y0 - 1e-6) / scale))
        bm = pg.render(scale=scale, crop=crop, rev_byteorder=True, prefer_bgrx=True)    # RGBX: Pillow reads it, no copy
        try:
            src = bm.to_pil()
            band = _clear_bands(*(src.getchannel(i) for i in range(3))) if clear else src.convert("RGB")
            del src
        finally:
            bm.close()
        out.paste(band.crop((0, 0, W, min(band.height, y1 - y0))), (0, y0))
        band.close()
    return out


def make(data, name="", page=1, clear=None):
    """The picture kept for a file: {kind, page, pages, mime, image (bytes), width, height, paper_mm [w, h] (a PDF page
    as drawn, else None)}. `clear` None = ticked for a PDF, not for a photo. Problem in words when refused."""
    from PIL import Image, ImageOps
    if not data:
        raise Problem("The file is empty.")
    if len(data) > MAX_BYTES:
        raise Problem("This file is over 10 MB.")
    kind = sniff(data, name)
    if clear is None:
        clear = kind == "pdf"
    pages, paper = 1, None
    nm = str(name or "The file")[:80]
    if kind == "pdf":
        import pypdfium2 as pdfium
        try:
            pdf = pdfium.PdfDocument(bytes(data))
        except Exception as e:  # noqa: BLE001  pdfium's own error: a password or a broken file
            if "password" in str(e).lower():
                raise Problem(f"{nm} is protected by a password. Save it without one and add it again.")
            raise Problem(f"{nm} could not be read as a PDF.")
        try:
            pages = len(pdf)
            try:
                page = int(page or 1)
            except (TypeError, ValueError):
                page = 1
            if not 1 <= page <= pages:
                raise Problem(f"{nm} has {pages} page{'s' if pages != 1 else ''}; there is no page {page}.")
            pg = pdf[page - 1]
            try:
                w_pt, h_pt = pg.get_size()
                scale = min(PDF_DPI / 72.0, MAX_SIDE / max(w_pt, h_pt, 1.0))
                im = _draw_page(pg, scale, clear)
            finally:
                pg.close()
        finally:
            pdf.close()
        # the paper as drawn (pdfium's size includes the page's turn), in millimetres
        paper = [round(w_pt * 25.4 / 72, 1), round(h_pt * 25.4 / 72, 1)]
    else:
        page = 1
        try:
            im = Image.open(io.BytesIO(bytes(data)))
            w, h = im.size
        except Exception:  # noqa: BLE001
            raise Problem(f"{nm} could not be read as a picture.")
        if w * h > MAX_PIXELS_IN:
            raise Problem(f"{nm} is {w:,} × {h:,} dots, too large to pin. Save it smaller (at most 4,096 a side).")
        if kind == "jpg":
            im.draft("RGB", (MAX_SIDE, MAX_SIDE))       # a big JPEG is decoded at a smaller size straight away
        try:
            im = ImageOps.exif_transpose(im)            # a phone photo the right way up
            im.load()
        except Exception:  # noqa: BLE001
            raise Problem(f"{nm} could not be read as a picture.")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    if clear and kind != "pdf":                          # a PDF page was made see-through as it was drawn
        im = _clear_white(im)
    elif im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("P", "PA") else "RGB")
    as_png = kind != "jpg" or clear
    out = _encode(im, as_png)
    # too big to keep: a picture with nothing clear becomes a JPEG; else it is drawn smaller until it fits
    while len(out) > MAX_STORED:
        has_alpha = im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 255
        if as_png and not has_alpha:
            as_png = False
        else:
            im = im.resize((max(1, int(im.width * 0.8)), max(1, int(im.height * 0.8))), Image.LANCZOS)
        out = _encode(im, as_png)
    width, height = im.size
    im.close()
    return {"kind": kind, "page": page, "pages": pages, "mime": "image/png" if as_png else "image/jpeg", "image": out,
            "width": width, "height": height, "paper_mm": paper, "clear": bool(clear)}


# ----------------------------------------------------------------------------------------------------- the corners
KY = 111320.0


def _kx(lat):
    return 111320.0 * math.cos(math.radians(lat))


def landing(centre, width, height, paper_mm=None, scale=None):
    """The four corners of a picture landing north up on `centre` [lon, lat]: at its true size from a PDF's paper and
    the typed scale (1:scale), else DEFAULT_WIDTH_M wide. Returns (corners, words)."""
    lon, lat = float(centre[0]), float(centre[1])
    if paper_mm and scale:
        w_m, h_m = paper_mm[0] * scale / 1000.0, paper_mm[1] * scale / 1000.0
        words = f"at its true size (1:{int(scale):,}: {w_m:,.0f} × {h_m:,.1f} m)"
    else:
        w_m = DEFAULT_WIDTH_M
        h_m = DEFAULT_WIDTH_M * height / max(1, width)
        words = f"{DEFAULT_WIDTH_M:.0f} m wide"
    kx = _kx(lat)
    dx, dy = w_m / 2 / kx, h_m / 2 / KY
    pts = [[lon - dx, lat + dy], [lon + dx, lat + dy], [lon + dx, lat - dy], [lon - dx, lat - dy]]
    return [[round(p[0], 7), round(p[1], 7)] for p in pts], words


def _metres(a, b):
    lat = (a[1] + b[1]) / 2
    return math.hypot((a[0] - b[0]) * _kx(lat), (a[1] - b[1]) * KY)


def clean_corners(c):
    """4 x [lon, lat] (7 dp) or Problem: four real points, no side longer than MAX_SIDE_M, not folded flat."""
    if not isinstance(c, (list, tuple)) or len(c) != 4:
        raise Problem("A picture needs its four corners.")
    pts = [SL._pt(p) for p in c]
    if None in pts:
        raise Problem("A corner is not a place on the map.")
    sides = [_metres(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    if max(sides) > MAX_SIDE_M:
        raise Problem("A side of the picture would be over 5 km. Move the corners closer.")
    if min(sides) < 0.5:
        raise Problem("Two corners are on top of each other.")
    return pts


def _opacity(v):
    x = SL._num(v, 0.05, 1.0)
    if x is None:
        raise Problem("The opacity must be a number from 0.05 to 1.")
    return round(x, 2)


def _name(v):
    n = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]+", " ", str(v or ""))).strip()[:MAX_NAME]
    if not n:
        raise Problem("Give the picture a name.")
    return n


# ----------------------------------------------------------------------------------------------------- records
COLS = ("id", "layout_id", "phase_id", "name", "kind", "page", "mime", "width", "height", "bytes", "corners_json",
        "opacity", "see_through", "on_sheet", "version", "created_by", "created_at", "updated_by", "updated_at")


def _out(r):
    try:
        corners = json.loads(r.get("corners_json") or "[]")
    except Exception:  # noqa: BLE001
        corners = []
    return {"id": r["id"], "layout_id": r["layout_id"], "phase_id": r.get("phase_id") or None,
            "every": not r.get("phase_id"), "name": r.get("name"), "kind": r.get("kind"), "page": int(r.get("page") or 1),
            "mime": r.get("mime"), "width": int(r.get("width") or 0), "height": int(r.get("height") or 0),
            "bytes": int(r.get("bytes") or 0), "corners": corners, "opacity": float(r.get("opacity") or DEFAULT_OPACITY),
            "clear": SL._truthy(r.get("see_through")), "on_sheet": SL._truthy(r.get("on_sheet")),
            "version": int(r.get("version") or 1), "by": r.get("updated_by") or r.get("created_by"),
            "at": r.get("updated_at") or r.get("created_at"),
            "url": f"/api/site-layouts/pictures/{r['id']}/image?v={int(r.get('version') or 1)}"}


def _row(pic_id):
    rows = db.query("SELECT " + ", ".join(COLS) + " FROM site_layout_pictures WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), str(pic_id or "")))
    if not rows:
        raise Problem("That picture is not there any more. Reload to see the layout.")
    return rows[0]


def for_layout(layout_id):
    """A layout's pictures, newest last, without the image (the page reads that by its own address)."""
    rows = db.query("SELECT " + ", ".join(COLS) + " FROM site_layout_pictures WHERE tenant_id = ? AND layout_id = ? "
                    "ORDER BY created_at, id", (db.current_tenant(), layout_id))
    return [_out(r) for r in rows]


def counts(layout_ids=None):
    """{layout id: {"every": n, phase id: n}} — the phase rows' "· 1 picture"."""
    out = {}
    for r in db.query("SELECT layout_id, phase_id FROM site_layout_pictures WHERE tenant_id = ?", (db.current_tenant(),)):
        if layout_ids is not None and r["layout_id"] not in layout_ids:
            continue
        b = out.setdefault(r["layout_id"], {})
        k = r.get("phase_id") or "every"
        b[k] = b.get(k, 0) + 1
    return out


def image(pic_id):
    """(mime, bytes, version) of a picture's image."""
    rows = db.query("SELECT mime, image_b64, version FROM site_layout_pictures WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), str(pic_id or "")))
    if not rows or not rows[0].get("image_b64"):
        raise Problem("That picture is not there any more. Reload to see the layout.")
    return rows[0]["mime"], base64.b64decode(rows[0]["image_b64"]), int(rows[0].get("version") or 1)


def _layout_phase(location_id, phase_id, every, by):
    """(layout row, phase id or None): the phase must be on this site's layout."""
    lay = SL._ensure_layout(location_id, by)
    if every:
        return lay, None
    if not phase_id:
        raise Problem("Choose the phase the picture belongs to, or Every phase.")
    ph = SL._phase_row(phase_id)
    if ph["layout_id"] != lay["id"]:
        raise Problem("That phase is not on this site's layout.")
    return lay, ph["id"]


def add(location_id, data, name, opts, by):
    """Make the picture and pin it. opts: {page, scale, clear (None = by kind), phase_id, every, centre [lon, lat]}.
    Returns {picture, words}. Run inside the heavy-read guard (main.py)."""
    loc = SL._location(location_id)
    lay = SL._layout_row(location_id)
    if lay:
        n = db.query("SELECT COUNT(*) AS n FROM site_layout_pictures WHERE tenant_id = ? AND layout_id = ?",
                     (db.current_tenant(), lay["id"]))[0]["n"]
        if int(n or 0) >= MAX_PER_SITE:
            raise Problem(f"This site has {MAX_PER_SITE} pictures, the most it can have. Delete one first.")
    every = bool(opts.get("every"))
    if not every and opts.get("phase_id"):
        SL._phase_row(opts.get("phase_id"))            # refuse a gone phase before the heavy work
    scale = opts.get("scale")
    try:
        scale = int(float(scale)) if scale not in (None, "") else None
    except (TypeError, ValueError):
        raise Problem("The scale must be a number, like 500 for 1:500.")
    if scale is not None and not 10 <= scale <= 100000:
        raise Problem("The scale must be from 1:10 to 1:100,000.")
    centre = opts.get("centre")
    if centre is None or SL._pt(centre) is None:
        if loc.get("lat") is None or loc.get("lon") is None:
            raise Problem("This location has no place on the map yet.")
        centre = [float(loc["lon"]), float(loc["lat"])]
    pic = make(data, name, opts.get("page") or 1, opts.get("clear"))
    lay, phase_id = _layout_phase(location_id, opts.get("phase_id"), every, by)
    corners, how = landing(SL._pt(centre), pic["width"], pic["height"], pic["paper_mm"] if pic["kind"] == "pdf" else None,
                           scale if pic["kind"] == "pdf" else None)
    base = re.sub(r"\.(pdf|png|jpe?g)$", "", str(name or "Picture"), flags=re.I)
    nm = _name(base + (f" (page {pic['page']})" if pic["kind"] == "pdf" and pic["pages"] > 1 else ""))
    pid = SL._next_id("site_layout_pictures", "PI")
    now = _now()
    db.execute("INSERT INTO site_layout_pictures (tenant_id, id, layout_id, phase_id, name, kind, page, mime, width, height, "
               "bytes, image_b64, corners_json, opacity, see_through, on_sheet, version, created_by, created_at, updated_by, "
               "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
               (db.current_tenant(), pid, lay["id"], phase_id, nm, pic["kind"], pic["page"], pic["mime"], pic["width"],
                pic["height"], len(pic["image"]), base64.b64encode(pic["image"]).decode("ascii"), json.dumps(corners),
                DEFAULT_OPACITY, bool(pic["clear"]), False, by, now, by, now))
    words = f"Added {how}, north up. Move it onto its place."
    if pic["kind"] == "pdf" and pic["pages"] > 1:
        words = f"Page {pic['page']} of {pic['pages']}. " + words
    return {"picture": _out(_row(pid)), "words": words, "pages": pic["pages"]}


def edit(pic_id, body, by):
    """Change a picture's corners, opacity, name or phase (body carries its `version`). Returns the picture."""
    cur = _row(pic_id)
    try:
        v = int(body.get("version"))
    except (TypeError, ValueError):
        raise Problem(STALE)
    if v != int(cur.get("version") or 1):
        raise Problem(STALE)
    sets, params = [], []
    if body.get("corners") is not None:
        sets.append("corners_json = ?")
        params.append(json.dumps(clean_corners(body["corners"])))
    if body.get("opacity") is not None:
        sets.append("opacity = ?")
        params.append(_opacity(body["opacity"]))
    if body.get("name") is not None:
        sets.append("name = ?")
        params.append(_name(body["name"]))
    if body.get("every") is not None or body.get("phase_id") is not None:
        if body.get("every"):
            phase_id = None
        else:
            ph = SL._phase_row(body.get("phase_id"))
            if ph["layout_id"] != cur["layout_id"]:
                raise Problem("That phase is not on this site's layout.")
            phase_id = ph["id"]
        sets.append("phase_id = ?")
        params.append(phase_id)
    if not sets:
        return _out(cur)
    stamp = datetime.datetime.utcnow().isoformat(timespec="microseconds") + "Z"
    db.execute("UPDATE site_layout_pictures SET {}, updated_by = ?, updated_at = ?, version = version + 1 "
               "WHERE tenant_id = ? AND id = ? AND version = ?".format(", ".join(sets)),
               tuple(params) + (by, stamp, db.current_tenant(), cur["id"], v))
    r = _row(pic_id)
    if int(r.get("version") or 0) != v + 1 or r.get("updated_at") != stamp:
        raise Problem(STALE)
    return _out(r)


def delete(pic_id, version):
    cur = _row(pic_id)
    if str(version) != str(cur.get("version") or 1):
        raise Problem(STALE)
    db.execute("DELETE FROM site_layout_pictures WHERE tenant_id = ? AND id = ? AND version = ?",
               (db.current_tenant(), cur["id"], int(cur.get("version") or 1)))
    return {"ok": True, "deleted": cur["id"]}


def delete_for_phase(phase_id):
    """A deleted phase takes its own pictures with it (an every-phase picture stays)."""
    db.execute("DELETE FROM site_layout_pictures WHERE tenant_id = ? AND phase_id = ?", (db.current_tenant(), phase_id))


def for_map(month, phases_in_force):
    """The staff Route map's pictures for `month`: every-phase ones and those of the phases in force, each with its site
    and address. `phases_in_force` = {phase id: location id}; every-phase pictures of a layout with any phase in
    force show too. Metadata only."""
    tenant = db.current_tenant()
    lays = {l["id"]: l["location_id"] for l in db.query("SELECT id, location_id FROM site_layouts WHERE tenant_id = ?",
                                                         (tenant,))}
    on = set(phases_in_force.values())
    out = []
    for r in db.query("SELECT " + ", ".join(COLS) + " FROM site_layout_pictures WHERE tenant_id = ? ORDER BY created_at, id",
                      (tenant,)):
        site = lays.get(r["layout_id"])
        if site is None:
            continue
        if (r.get("phase_id") and r["phase_id"] in phases_in_force) or (not r.get("phase_id") and site in on):
            p = _out(r)
            p["site"] = site
            out.append(p)
    return out
