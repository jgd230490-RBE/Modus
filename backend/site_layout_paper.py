"""
site_layout_paper.py — a site's logistics layout ON PAPER (task 4c PR 5, 31 Oct 2026; plan notes
site-layouts-plan-1030.md §3.4, §4, §5; the mockup notes/site-layout-paper-mockup-1031/).

ONE drawing of a layout on a ReportLab canvas, read from the same style table as the maps (site_layout_styles), so the
map and the paper never disagree:

    draw(c, things, P, ppm)          things = saved layout things (GeoJSON features); P(lon, lat) -> (x, y) PDF points;
                                     ppm = PDF points a metre on the ground at this scale

It follows map/site-layouts.js layer for layer: areas (fill, hatch / cross / dots clipped to the shape, edge), the
traffic bands and their marks, the white edge under the thin lines, the barrier, Heras posts, hoarding, cones, the
pedestrian / cycle dashes and their marks, leaders; then arrowheads, lights, the crane and its radius, the area words;
then the symbols (site_layout_svg, vector) and the text. Widths and sizes are METRES on the ground, drawn to scale and
never thinner / smaller than the map's own floor (MIN_* in CSS pixels, PX_PT points each).

Two users:
  * the layout's own sheet — sheet() + build_pdf(): one phase, A3 or A4 landscape, fitted to the layout or at a stated
    scale, the basemap (basemap.fetch) under it, the legend of only what is inside the frame, scale bar, north arrow,
    the phase and its months. GET /api/locations/{id}/site-layout/sheet.pdf | .png (main.py, heavy_reads.solo).
  * the CLOCS CLP site plan (route_map_export.plan kind "site", so the staff map export and 4a's CLP document §4):
    for_plan() gives the phase in force in the plan's month, inside the plan's frame, without the private symbols
    (security / CCTV: a CLP goes to the client), which export.build_route_map_pdf draws under the routes.
"""
import datetime
import io
import math

import site_layout_styles as styles
import site_layout_svg as svg

#: a CSS pixel of the map's floors (map/site-layouts.js metres(val, minPx)) in PDF points on paper
PX_PT = 0.5
#: the scales a sheet is fitted to (the N of 1:N, largest first); a person may pick any of them
SCALES = (200, 250, 500, 1000, 1250, 2000, 2500, 5000, 10000)
#: the pages (landscape, mm): page size, margin, the column beside the map
PAGES = {"a3": {"name": "A3", "w": 420.0, "h": 297.0, "margin": 10.0, "col": 84.0, "gap": 5.0},
         "a4": {"name": "A4", "w": 297.0, "h": 210.0, "margin": 7.0, "col": 70.0, "gap": 4.0}}
DEFAULT_PAGE = "a3"
#: the sheet's basemap: Streets (4a Q12: Light is nearly blank at site scale)
DEFAULT_STYLE = "streets"
W_PX = 1280                      # basemap.MAX_PX; @2x
PAD_PX = 18
#: marks along a line, metres apart on the ground (the plan §4), never closer than this many times the mark's size
CHEVRON_EVERY_M, CONE_EVERY_M, ICON_EVERY_M, POST_EVERY = 12.0, 2.5, 30.0, None
INK = "#111827"
NAVY = (0x1F / 255.0, 0x20 / 255.0, 0x24 / 255.0)
GREY = (0x5B / 255.0, 0x64 / 255.0, 0x70 / 255.0)
LEGEND_MAX = 30


class SheetError(ValueError):
    """A sheet that cannot be drawn as asked (unknown phase, page or scale) — the words are shown as they are."""


def _rgb(hx, default=INK):
    hx = (hx or default).lstrip("#")
    if len(hx) != 6:
        hx = default.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def darker(hx):
    """The map's darker() (site-layouts.js): each channel × 0.62 — an area's words."""
    r, g, b = _rgb(hx, "#6B7280")
    return tuple(math.floor(v * 255 * 0.62 + 0.5) / 255.0 for v in (r, g, b))


def _area_m2(ring):
    if len(ring) < 3:
        return 0.0
    o = ring[0]
    kx = 111320 * math.cos(math.radians(o[1]))
    s = 0.0
    for a, b in zip(ring, ring[1:]):
        ax, ay = (a[0] - o[0]) * kx, (a[1] - o[1]) * 110574
        bx, by = (b[0] - o[0]) * kx, (b[1] - o[1]) * 110574
        s += ax * by - bx * ay
    return abs(s / 2)


def _centroid(g):
    t, cs = g["type"], g["coordinates"]
    pts = [cs] if t == "Point" else cs if t == "LineString" else cs[0]
    n = len(pts) - (1 if t == "Polygon" else 0)
    n = max(1, n)
    return [sum(p[0] for p in pts[:n]) / n, sum(p[1] for p in pts[:n]) / n]


def kind_of(p):
    st = p.get("style")
    if st == "sym":
        return "sym" if p.get("sym") in styles.SYMBOL_KEYS else None
    if st == "text":
        return "text"
    if st in styles.AREA_STYLES:
        return "area"
    if st in styles.LINE_STYLES:
        return "line"
    return None


# --------------------------------------------------------------------------------------------------- the drawing
class _Pen:
    """The canvas plus the scale: metres -> points with the map's floors."""

    def __init__(self, c, ppm, fonts):
        self.c, self.ppm, self.F = c, float(ppm), fonts

    def m(self, metres, min_px=0.0, add_px=0.0):
        return max(float(metres) * self.ppm, min_px * PX_PT) + add_px * PX_PT

    def path(self, pts, close=False):
        p = self.c.beginPath()
        p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        if close:
            p.close()
        return p

    def stroke(self, pts, rgb, width, dash=None, cap=1, join=1, alpha=1.0):
        if len(pts) < 2 or width <= 0:
            return
        c = self.c
        c.saveState()
        c.setStrokeColorRGB(*rgb)
        c.setStrokeAlpha(max(0.0, min(1.0, alpha)))
        c.setLineWidth(width)
        c.setLineCap(cap)
        c.setLineJoin(join)
        if dash:
            c.setDash([max(0.01, d * width) for d in dash], 0)
        c.drawPath(self.path(pts), stroke=1, fill=0)
        c.restoreState()

    def words(self, text, x, y, size, rgb, bold=True, rot=0.0, halo=None, halo_w=0.0, anchor="middle", spacing=0.0):
        """Words centred on (x, y) (anchor "top": their top at y), turned clockwise, an optional halo under them."""
        if not text:
            return
        c = self.c
        from reportlab.lib.utils import simpleSplit
        font = self.F["bold"] if bold else self.F["regular"]
        # wrapped at 40 ems, as the map's text-max-width
        lines = [w for ln in str(text).split("\n") for w in (simpleSplit(ln, font, size, 40 * size) or [""])]
        lead = size * 1.15
        c.saveState()
        c.translate(x, y)
        if rot:
            c.rotate(-float(rot))
        top = (lead * len(lines)) / 2.0 if anchor == "middle" else 0.0
        for i, ln in enumerate(lines):
            base = top - size * 0.78 - i * lead
            w = c.stringWidth(ln, font, size) + spacing * size * max(0, len(ln) - 1)
            for mode in ((1, 0) if halo else (0,)):
                # each pass in its own graphics state: the text render mode outlives the text object, and ReportLab
                # does not write "0 Tr" for a new object it believes is already filling (seen: every word white)
                c.saveState()
                if mode == 1:                      # the halo: the words' outline, round-joined, under the fill
                    c.setLineWidth(halo_w)
                    c.setLineJoin(1)
                tt = c.beginText()
                tt.setFont(font, size)
                if spacing:
                    tt.setCharSpace(spacing * size)
                tt.setTextOrigin(-w / 2.0, base)
                tt.setTextRenderMode(mode)
                if mode == 1:
                    tt.setStrokeColorRGB(*halo)
                else:
                    tt.setFillColorRGB(*rgb)
                tt.textLine(ln)
                c.drawText(tt)
                c.restoreState()
        c.restoreState()


def _along(pts, every, first=None):
    """Points (x, y, angle°) every `every` points along a polyline, starting at first (default half a step)."""
    out = []
    if every <= 0 or len(pts) < 2:
        return out
    at = every / 2.0 if first is None else first
    run = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        while L > 0 and at <= run + L:
            f = (at - run) / L
            out.append((x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, math.degrees(math.atan2(y2 - y1, x2 - x1))))
            at += every
        run += L
    return out


def _seg_angle(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def prepare(things, P):
    """The things in paper coordinates with their style filled in from the table (the map's prepare())."""
    out = []
    for f in things or []:
        g = (f or {}).get("geometry") or {}
        p = dict((f or {}).get("properties") or {})
        k = kind_of(p)
        if not k or not g.get("coordinates"):
            continue
        t = g["type"]
        if t == "Point":
            xy = [P(*g["coordinates"][:2])]
        elif t == "LineString":
            xy = [P(*q[:2]) for q in g["coordinates"]]
        elif t == "Polygon":
            xy = [[P(*q[:2]) for q in ring] for ring in g["coordinates"]]
        else:
            continue
        st = p.get("style")
        if k == "line":
            s = styles.LINE_STYLES[st]
            p.setdefault("color", s["color"])
            if p.get("w") is None:
                p["w"] = s["w"]
        elif k == "area":
            s = styles.AREA_STYLES[st]
            p.setdefault("fill", s["fill"])
            p.setdefault("color", s["color"])
            p.setdefault("outline", s["outline"])
            if p.get("opacity") is None:
                p["opacity"] = s["opacity"]
            if p.get("text") is None:
                p["text"] = s["text"]
        out.append({"kind": k, "style": st, "p": p, "g": g, "xy": xy, "z": int(p.get("z") or 0)})
    out.sort(key=lambda t: t["z"])
    return out


def draw(c, things, P, ppm, fonts=None, prepared=None):
    """Every thing of a layout on canvas c (inside whatever clip the caller set). Returns the prepared things."""
    import brand_pdf
    F = fonts or brand_pdf.fonts()
    T = prepared if prepared is not None else prepare(things, P)
    pen = _Pen(c, ppm, F)
    areas = [t for t in T if t["kind"] == "area"]
    lines = [t for t in T if t["kind"] == "line"]
    L = lambda key: [t for t in lines if t["style"] == key]

    # ---- areas: fill, pattern, edge
    for t in areas:
        _area(pen, t)
    # ---- the traffic bands, their middles and the one-way chevrons
    for key in ("oneway", "twoway", "lights"):
        for t in L(key):
            pen.stroke(t["xy"], _rgb(t["p"]["color"]), pen.m(t["p"]["w"], 6), cap=0, join=1,
                       alpha=(0.22 if key == "lights" else 0.35) * float(t["p"].get("opacity", 1) or 1))
    for t in L("twoway"):
        pen.stroke(t["xy"], (1, 1, 1), pen.m(0.15, 1.5), dash=(6, 4), cap=0)
    for t in L("lights"):
        pen.stroke(t["xy"], _rgb(INK), pen.m(0.2, 2), dash=(1, 2), cap=0)
    for t in L("oneway"):
        size = pen.m(0.7 * float(t["p"]["w"]), 0.18 * 64)
        for x, y, a in _along(t["xy"], max(CHEVRON_EVERY_M * ppm, 2.2 * size)):
            svg.draw(c, styles.GLYPHS["chev"], x, y, size, -a, F)
    # ---- the thin lines: a white edge first, so they read on the photo
    thin = ("barrier", "heras", "hoarding", "ped", "cycle", "leader", "imported")
    for t in lines:
        if t["style"] in thin:
            pen.stroke(t["xy"], (1, 1, 1), pen.m(t["p"]["w"], 2, 2.5), alpha=0.85)
    for t in L("barrier"):
        w = pen.m(t["p"]["w"], 4)
        pen.stroke(t["xy"], (1, 1, 1), w, cap=0)
        pen.stroke(t["xy"], _rgb(t["p"]["color"]), w, dash=(2, 2), cap=0, alpha=float(t["p"].get("opacity", 1) or 1))
    for t in L("heras"):
        pen.stroke(t["xy"], _rgb(t["p"]["color"]), pen.m(t["p"]["w"], 1.6), alpha=float(t["p"].get("opacity", 1) or 1))
        pen.stroke(t["xy"], _rgb(INK), pen.m(0.45, 4), dash=(1, 6.8), cap=0)
    for t in L("hoarding"):
        pen.stroke(t["xy"], _rgb(t["p"]["color"]), pen.m(t["p"]["w"], 4), cap=0, join=0,
                   alpha=float(t["p"].get("opacity", 1) or 1))
    for t in L("cones"):
        pen.stroke(t["xy"], _rgb(t["p"]["color"]), 1.5 * PX_PT, dash=(2, 3), alpha=0.45)
        size = pen.m(0.9, 0.14 * 64)
        for x, y, a in _along(t["xy"], max(CONE_EVERY_M * ppm, 1.6 * size)):
            svg.draw(c, styles.GLYPHS["cone"], x, y, size, 0, F)
    for key, glyph in (("ped", "walk"), ("cycle", "bike")):
        for t in L(key):
            pen.stroke(t["xy"], _rgb(t["p"]["color"]), pen.m(t["p"]["w"], 3), dash=(1.6, 1) if key == "ped" else (3, 1.2),
                       cap=0, alpha=float(t["p"].get("opacity", 1) or 1))
            size = pen.m(2.2, 0.2 * 64)
            for x, y, a in _along(t["xy"], max(ICON_EVERY_M * ppm, 4 * size)):
                svg.draw(c, styles.GLYPHS[glyph], x, y, size, 0, F)
    for key in ("leader", "imported"):
        for t in L(key):
            pen.stroke(t["xy"], _rgb(t["p"]["color"]), pen.m(t["p"]["w"], 1.6))
    # ---- the derived marks: arrowheads, lights at the ends, the crane in its radius, the area words
    for t in lines:
        xy, st = t["xy"], t["style"]
        if len(xy) < 2:
            continue
        end, start = _seg_angle(xy[-2], xy[-1]), _seg_angle(xy[1], xy[0])
        if st in ("oneway", "leader"):
            svg.draw(c, styles.GLYPHS["head"], *xy[-1], pen.m(1.6 if st == "leader" else 3, 0.22 * 64), -end, F)
        if st == "twoway":
            svg.draw(c, styles.GLYPHS["headw"], *xy[-1], pen.m(4, 0.22 * 64), -end, F)
            svg.draw(c, styles.GLYPHS["headw"], *xy[0], pen.m(4, 0.22 * 64), -start, F)
        if st == "lights":
            for q in (xy[0], xy[-1]):
                svg.draw(c, styles.GLYPHS["lights"], *q, pen.m(3.2, 0.22 * 64), 0, F)
    for t in areas:
        _area_words(pen, t)
    # ---- symbols, then words
    for t in T:
        if t["kind"] == "sym":
            p = t["p"]
            x, y = t["xy"][0]
            size = pen.m(p.get("size") or styles.SYMBOL_KEYS[p["sym"]]["size"], 0.3 * 64)
            svg.draw(c, styles.SYMBOL_KEYS[p["sym"]]["svg"], x, y, size, p.get("rot") or 0, F)
            if p.get("label"):
                ts = pen.m(1.4, 10)
                pen.words(p["label"], x, y - 1.4 * ts, ts, _rgb(INK), True, 0, (1, 1, 1), 1.6 * PX_PT * 2, anchor="top")
    for t in T:
        if t["kind"] == "text":
            p = t["p"]
            x, y = t["xy"][0]
            halo = _rgb(p.get("halo_color") or "#FFFFFF") if p.get("halo") else None
            pen.words(p.get("text"), x, y, pen.m(p.get("size") or 2.2, 9), _rgb(p.get("color") or INK), bool(p.get("bold")),
                      p.get("rot") or 0, halo, 1.8 * PX_PT * 2)
    return T


def _area(pen, t):
    c, p = pen.c, t["p"]
    rings = [r for r in t["xy"] if len(r) >= 3]
    if not rings:
        return
    rgb, op = _rgb(p["color"]), float(p.get("opacity") if p.get("opacity") is not None else 1)

    def shape():
        q = c.beginPath()
        for r in rings:
            q.moveTo(*r[0])
            for v in r[1:]:
                q.lineTo(*v)
            q.close()
        return q
    from reportlab.pdfgen.canvas import FILL_EVEN_ODD
    fill = p.get("fill") or "solid"
    if fill == "solid":
        c.saveState()
        c.setFillColorRGB(*rgb)
        c.setFillAlpha(max(0.0, min(1.0, op)))
        c.drawPath(shape(), stroke=0, fill=1, fillMode=FILL_EVEN_ODD)
        c.restoreState()
    elif fill in ("hatch", "cross", "dots"):
        xs = [v[0] for v in rings[0]]
        ys = [v[1] for v in rings[0]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        step = 8 * PX_PT * 2          # the map's 16 px pattern step, at paper's px
        c.saveState()
        c.clipPath(shape(), stroke=0, fill=0, fillMode=FILL_EVEN_ODD)
        c.setStrokeColorRGB(*rgb)
        c.setFillColorRGB(*rgb)
        a = min(1.0, 0.25 + op)
        c.setStrokeAlpha(a)
        c.setFillAlpha(a)
        c.setLineWidth(1.5 * PX_PT * 2 * 0.5)
        span = (x1 - x0) + (y1 - y0)
        if fill in ("hatch", "cross"):
            k = -span
            while k <= span:
                c.line(x0 + k, y1, x0 + k + (y1 - y0), y0)          # down-right, as the map's pattern
                if fill == "cross":
                    c.line(x0 + k, y0, x0 + k + (y1 - y0), y1)
                k += step
        else:
            yy, row = y0, 0
            while yy <= y1 + step:
                xx = x0 + (step / 2 if row % 2 else 0)
                while xx <= x1 + step:
                    c.circle(xx, yy, 1.6 * PX_PT * 1.2, stroke=0, fill=1)
                    xx += step
                yy += step / 2
                row += 1
        c.restoreState()
    w = pen.m(0.25, 1.6 if p.get("outline") != "dashed" else 1.8)
    for r in rings:
        pen.stroke(r, rgb, w, dash=(4, 3) if p.get("outline") == "dashed" else None, cap=0)


def _area_words(pen, t):
    p, g = t["p"], t["g"]
    label = p.get("text") or ""
    if t["style"] == "crane_radius" and g["type"] == "Polygon":
        ring = g["coordinates"][0]
        r = math.sqrt(_area_m2(ring) / math.pi)
        cx, cy = _centroid_xy(t["xy"][0])
        svg.draw(pen.c, styles.SYMBOL_KEYS["mobilecrane"]["svg"], cx, cy, pen.m(6, 0.22 * 64), 0, pen.F)
        at = t["xy"][0][len(ring) // 8]
        pen.words(f"R {round(r)} m", at[0], at[1], pen.m(2, 10), _rgb(p["color"]), True, 0, (1, 1, 1), 1.6 * PX_PT * 2,
                  spacing=0.06)
        label = ""
    if label:
        cx, cy = _centroid_xy(t["xy"][0])
        pen.words(label, cx, cy, pen.m(2.4, 10), darker(p["color"]), True, 0, (1, 1, 1), 1.6 * PX_PT * 2, spacing=0.06)


def _centroid_xy(ring):
    n = max(1, len(ring) - 1)
    return sum(v[0] for v in ring[:n]) / n, sum(v[1] for v in ring[:n]) / n


# --------------------------------------------------------------------------------------------------- the legend
def legend_rows(prepared, inside=None):
    """[(kind, key, label, sample props)] for the styles drawn (inside the frame when `inside(x, y)` is given), in the
    order: areas, lines, symbols, then the table's own order. A colour is the one most things of that style carry."""
    seen = {}
    for t in prepared:
        if t["kind"] == "text":
            continue
        if inside is not None:
            pts = t["xy"] if t["kind"] != "area" else [v for r in t["xy"] for v in r]
            if t["kind"] == "sym":
                pts = t["xy"]
            if not any(inside(x, y) for x, y in pts):
                continue
        key = (t["kind"], t["p"].get("sym") if t["kind"] == "sym" else t["style"])
        seen.setdefault(key, []).append(t["p"])
    order = ([("area", k) for k in styles.AREA_STYLES] + [("line", k) for k in styles.LINE_STYLES]
             + [("sym", s["key"]) for s in styles.SYMBOLS])
    out = []
    for kd, k in order:
        if (kd, k) not in seen:
            continue
        ps = seen[(kd, k)]
        cols = {}
        for q in ps:
            cols[q.get("color")] = cols.get(q.get("color"), 0) + 1
        top = max(cols, key=cols.get) if cols else None
        table = {"area": styles.AREA_STYLES, "line": styles.LINE_STYLES, "sym": styles.SYMBOL_KEYS}[kd]
        label = (table.get(k) or {}).get("label", k)      # by kind: the symbol "welfare" is a cabin, the area a compound
        sample = dict(ps[0])
        if top:
            sample["color"] = top
        out.append((kd, k, label, sample))
    return out


def draw_legend_swatch(c, kind, key, sample, x, y, w=22.0, h=9.0, fonts=None):
    """One legend row's swatch, (x, y) its bottom-left, drawn by the same code as the map things at a fixed size."""
    import brand_pdf
    F = fonts or brand_pdf.fonts()
    pen = _Pen(c, 1.0, F)
    cy = y + h / 2
    if kind == "sym":
        svg.draw(c, styles.SYMBOL_KEYS[key]["svg"], x + w / 2, cy, h + 1, 0, F)
        return
    p = dict(sample)
    if kind == "area":
        s = styles.AREA_STYLES[key]
        for k2 in ("fill", "color", "outline", "opacity"):
            if p.get(k2) is None:
                p[k2] = s[k2]
        t = {"kind": "area", "style": key, "p": p, "xy": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]}
        _area(pen, t)
        if key == "crane_radius":
            pen.stroke([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], _rgb(p["color"]), 0.9, dash=(4, 3), cap=0)
        return
    s = styles.LINE_STYLES[key]
    col = _rgb(p.get("color") or s["color"])
    xy = [(x, cy), (x + w, cy)]
    width = {"oneway": 6.0, "twoway": 8.0, "lights": 6.0}.get(key)
    if width:
        pen.stroke(xy, col, width, cap=0, alpha=0.22 if key == "lights" else 0.35)
        if key == "twoway":
            pen.stroke(xy, (1, 1, 1), 0.75, dash=(6, 4), cap=0)
            svg.draw(c, styles.GLYPHS["headw"], x + w, cy, 6.5, 0, F)
            svg.draw(c, styles.GLYPHS["headw"], x, cy, 6.5, 180, F)
        elif key == "oneway":
            svg.draw(c, styles.GLYPHS["chev"], x + w * 0.45, cy, 5.5, 0, F)
            svg.draw(c, styles.GLYPHS["head"], x + w, cy, 6.5, 0, F)
        else:
            pen.stroke(xy, _rgb(INK), 1.0, dash=(1, 2), cap=0)
            svg.draw(c, styles.GLYPHS["lights"], x + w, cy, 7, 0, F)
        return
    if key == "barrier":
        pen.stroke(xy, (1, 1, 1), 3.4, cap=0)
        pen.stroke(xy, col, 3.4, dash=(2, 2), cap=0)
    elif key == "heras":
        pen.stroke(xy, col, 0.9)
        pen.stroke(xy, _rgb(INK), 2.2, dash=(1, 3.4), cap=0)
    elif key == "hoarding":
        pen.stroke(xy, col, 2.4, cap=0)
    elif key == "cones":
        pen.stroke(xy, col, 0.75, dash=(2, 3), alpha=0.45)
        for k in (0.2, 0.55, 0.9):
            svg.draw(c, styles.GLYPHS["cone"], x + w * k, cy, 6.5, 0, F)
    elif key in ("ped", "cycle"):
        pen.stroke(xy, col, 2.4, dash=(1.6, 1) if key == "ped" else (3, 1.2), cap=0)
        svg.draw(c, styles.GLYPHS["walk" if key == "ped" else "bike"], x + w / 2, cy, 8, 0, F)
    elif key == "leader":
        pen.stroke(xy, col, 0.8)
        svg.draw(c, styles.GLYPHS["head"], x + w, cy, 5, 0, F)
    else:
        pen.stroke(xy, col, 0.9)


# --------------------------------------------------------------------------------------------------- reads
def month_words(ph):
    """'Every month' / 'From Apr 2027' / 'Until Jun 2027' / 'Apr 2027 to Jun 2027'."""
    def mw(v):
        try:
            return datetime.date(int(v[:4]), int(v[5:7]), 1).strftime("%b %Y")
        except Exception:
            return v
    a, b = ph.get("month_from"), ph.get("month_to")
    if a and b:
        return f"{mw(a)} to {mw(b)}" if a != b else mw(a)
    if a:
        return f"From {mw(a)}"
    if b:
        return f"Until {mw(b)}"
    return "Every month"


def _location(location_id):
    import db
    rows = db.query("SELECT id, name, lat, lon FROM locations WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), location_id))
    return rows[0] if rows else None


def _phase(location_id, phase_id):
    import site_layouts as SL
    lay = SL.get(location_id)
    if not lay or not lay["phases"]:
        raise SheetError("This site has no layout yet.")
    if phase_id:
        ph = next((p for p in lay["phases"] if p["id"] == phase_id), None)
        if not ph:
            raise SheetError("That phase is not on this site's layout.")
    else:
        ph = lay["phases"][0]
    return lay, ph


def _points(things):
    pts = []
    for f in things:
        g = f.get("geometry") or {}
        t, cs = g.get("type"), g.get("coordinates")
        if t == "Point":
            pts.append(tuple(cs[:2]))
        elif t == "LineString":
            pts += [tuple(q[:2]) for q in cs]
        elif t == "Polygon":
            pts += [tuple(q[:2]) for q in cs[0]]
    return pts


def scale_words(n):
    return f"1:{int(n):,}"


def month_of_index(month_index):
    """The 'YYYY-MM' of a month index (weeks' calendar)."""
    import weeks
    y, mo = weeks._month_of(int(month_index))
    return f"{y:04d}-{mo:02d}"


def phase_in_force(location_id, month):
    """The phase of a site's layout in force in 'YYYY-MM', or None. Where phases overlap (the map draws them all), a
    dated phase wins over an every-month one and the later start over the earlier: a "Deck" phase for Jun to Aug is
    the plan for those months, not the every-month "Site logistics" under it."""
    import site_layouts as SL
    lay = SL.get(location_id)
    if not lay:
        return None
    hits = [p for p in lay["phases"] if SL.in_month(p, month) and p.get("things")]
    if not hits:
        return None
    return max(enumerate(hits), key=lambda ip: (bool(ip[1].get("month_from") or ip[1].get("month_to")),
                                                ip[1].get("month_from") or "", ip[0]))[1]


def for_plan(location_id, month_index, private=False):
    """The CLP site plan's hook (route_map_export.plan kind "site"): {site, phase, months, things} of the site's phase
    in force in the plan's month, or None when it has none. The private symbols (security, CCTV) are left out unless
    `private`: a CLP goes to the client. Never raises (a plan without a layout is still a plan)."""
    try:
        ph = phase_in_force(location_id, month_of_index(month_index))
    except Exception:
        return None
    if not ph:
        return None
    things = [f for f in (ph.get("features") or {}).get("features") or []
              if private or (f.get("properties") or {}).get("sym") not in styles.PRIVATE_SYMBOLS]
    loc = _location(location_id) or {}
    return {"location_id": location_id, "site": loc.get("name") or location_id, "phase": ph["name"],
            "phase_id": ph["id"], "months": month_words(ph), "things": things}


def sheet(location_id, phase_id=None, page=None, scale=None, style=None, now=None):
    """Everything the sheet draws: the site, the phase (its things), the page and frame, the view at the stated or
    fitted scale. Raises SheetError in words."""
    import basemap
    pg = (page or DEFAULT_PAGE).strip().lower()
    if pg not in PAGES:
        raise SheetError("The page is A3 or A4.")
    spec = PAGES[pg]
    if scale not in (None, "", "fit"):
        try:
            scale = int(str(scale).replace(",", "").split(":")[-1])
        except ValueError:
            raise SheetError("The scale is a number, such as 500 for 1:500.")
        if scale not in SCALES:
            raise SheetError("The scale is one of " + ", ".join(scale_words(n) for n in SCALES) + ".")
    else:
        scale = None
    st = basemap.clean_style(style) or DEFAULT_STYLE
    loc = _location(location_id)
    if not loc:
        raise SheetError("That site is not on this network.")
    lay, ph = _phase(location_id, phase_id)
    things = (ph.get("features") or {}).get("features") or []
    fw = spec["w"] - 2 * spec["margin"] - spec["col"] - spec["gap"]
    fh = spec["h"] - 2 * spec["margin"]
    h_px = int(round(W_PX * fh / fw))
    pts = _points(things)
    if not pts and loc.get("lat") is not None:
        pts = [(float(loc["lon"]), float(loc["lat"]))]
    if not pts:
        raise SheetError("This phase has nothing on it to print.")
    if scale:
        n, v = basemap.view_to_scale(pts, (scale,), fw, W_PX, h_px, PAD_PX)
    else:
        n, v = basemap.view_to_scale(pts, SCALES, fw, W_PX, h_px, PAD_PX)
    import export
    notice = export._demo_notice() or None
    import bulletin_doc
    return {"location_id": location_id, "site": loc.get("name") or location_id, "phase": ph, "things": things,
            "page": pg, "spec": spec, "frame_w_mm": fw, "frame_h_mm": fh, "view": v, "denom": n, "fitted": not scale,
            "style": st, "tenant": export._tenant_name() or "Wayscope", "demo_notice": notice,
            "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
            "drawn": f"{(now or datetime.date.today()):%d %b %Y}".lstrip("0")}


def build_pdf(S):
    """The sheet as ONE landscape page: the map at its stated scale when printed at 100 %, the column beside it."""
    import basemap
    import brand_pdf
    import export
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    F = brand_pdf.fonts()
    sp = S["spec"]
    W, H = sp["w"] * mm, sp["h"] * mm
    m = sp["margin"] * mm
    fw, fh = S["frame_w_mm"] * mm, S["frame_h_mm"] * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(export._pdf_safe(f"{S['site']} · Site layout · {S['phase']['name']}"))
    c.setAuthor("Wayscope")
    v = S["view"]
    with basemap.use(S["style"]):
        pic = basemap.fetch(v) if v else None
        credit = basemap.credit()
    S["basemap_ok"] = bool(pic)
    k = fw / v["w"]

    def P(lon, lat):
        x, y = basemap.project(v, lon, lat)
        return m + x * k, m + fh - y * k
    ppm = k / basemap.m_per_px(v["lat"], v["zoom"])
    c.saveState()
    clip = c.beginPath()
    clip.rect(m, m, fw, fh)
    c.clipPath(clip, stroke=0, fill=0)
    if pic:
        c.drawImage(ImageReader(io.BytesIO(pic)), m, m, width=fw, height=fh)
    else:
        c.setFillColorRGB(0.965, 0.969, 0.973)
        c.rect(m, m, fw, fh, stroke=0, fill=1)
    T = draw(c, S["things"], P, ppm, F)
    c.restoreState()
    inside = lambda x, y: m <= x <= m + fw and m <= y <= m + fh
    S["legend"] = legend_rows(T, inside)
    if S.get("map_demo_tag"):
        _tag(c, S["map_demo_tag"], m, m + fh, F)
    _scale_bar(c, v, m, m, fw, k, F)
    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.6)
    c.rect(m, m, fw, fh, stroke=1, fill=0)
    _column(c, S, m + fw + sp["gap"] * mm, m, sp["col"] * mm, fh, credit, F)
    c.showPage()
    c.save()
    return buf.getvalue()


def _tag(c, text, x, top, F):
    c.saveState()
    c.setFont(F["bold"], 7.5)
    w = c.stringWidth(text, F["bold"], 7.5) + 10
    c.setFillColorRGB(1, 1, 1)
    c.setFillAlpha(0.92)
    c.rect(x + 6, top - 18, w, 12, stroke=0, fill=1)
    c.setFillAlpha(1)
    c.setFillColorRGB(0.72, 0.11, 0.11)
    c.drawString(x + 11, top - 14.6, text)
    c.restoreState()


def _scale_bar(c, v, x0f, y0f, fw, k, F):
    import basemap
    from reportlab.lib.units import mm
    metres, px = basemap.bar_metres(v, 50 * mm / k)
    bar = px * k
    x1, y = x0f + fw - 14, y0f + 20
    x0 = x1 - bar
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.setFillAlpha(0.9)
    c.rect(x0 - 10, y - 7, bar + 22, 21, stroke=0, fill=1)
    c.restoreState()
    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.6)
    for i in range(4):
        c.setFillColorRGB(*(NAVY if i % 2 == 0 else (1, 1, 1)))
        c.rect(x0 + i * bar / 4, y - 1.5, bar / 4, 3.5, stroke=1, fill=1)
    c.setFillColorRGB(*NAVY)
    c.setFont(F["regular"], 6.8)
    c.drawCentredString(x0, y + 4.5, "0")
    c.drawCentredString(x0 + bar / 2, y + 4.5, basemap.length_words(metres / 2).replace(" km", "").replace(" m", ""))
    c.drawCentredString(x1, y + 4.5, basemap.length_words(metres))


def _north(c, x, y, h=18):
    w = h * 0.55
    c.saveState()
    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.7)
    c.setLineJoin(1)
    for fill, sx in ((NAVY, -1), ((1, 1, 1), 1)):
        p = c.beginPath()
        p.moveTo(x, y + h)
        p.lineTo(x + sx * w / 2, y)
        p.lineTo(x, y + h * 0.28)
        p.close()
        c.setFillColorRGB(*fill)
        c.drawPath(p, stroke=1, fill=1)
    c.restoreState()


def _column(c, S, x, y, w, h, credit, F):
    """The column beside the map: the site and phase, scale and north, the legend, then the footer."""
    import export
    from reportlab.lib.utils import simpleSplit
    R, B = F["regular"], F["bold"]
    top = y + h
    cur = [top]

    def text(s, font=R, size=8, lead=None, rgb=NAVY, width=w):
        lead = lead or size * 1.25
        for ln in simpleSplit(export._pdf_safe(s), font, size, width):
            c.setFillColorRGB(*rgb)
            c.setFont(font, size)
            c.drawString(x, cur[0] - size, ln)
            cur[0] -= lead
    ph = S["phase"]
    text(S["site"], B, 13, 16, width=w - 24)
    text("Site layout", R, 9, 12, GREY, width=w - 24)
    cur[0] -= 4
    _north(c, x + w - 9, top - 26)
    c.setFont(B, 8)
    c.setFillColorRGB(*NAVY)
    c.drawCentredString(x + w - 9, top - 5, "N")
    text(ph["name"], B, 10, 13)
    text(month_words(ph), R, 8.4, 11)
    text(f"Scale {scale_words(S['denom'])} at {S['spec']['name']}", B, 8.4, 11)
    cur[0] -= 6
    c.setStrokeColorRGB(0.85, 0.87, 0.9)
    c.setLineWidth(0.5)
    c.line(x, cur[0], x + w, cur[0])
    cur[0] -= 8
    rows = S.get("legend") or []
    shown = rows[:LEGEND_MAX]
    groups = (("area", "Areas"), ("line", "Lines"), ("sym", "Symbols"))
    row_h = 12.5 if S["page"] == "a3" else 11.0
    for kd, title in groups:
        rs = [r for r in shown if r[0] == kd]
        if not rs:
            continue
        text(title, B, 8, 11)
        for _, key, label, sample in rs:
            draw_legend_swatch(c, kd, key, sample, x, cur[0] - row_h + 2, 22, row_h - 4, F)
            c.setFillColorRGB(*NAVY)
            c.setFont(R, 7.8)
            c.drawString(x + 28, cur[0] - row_h + 4.2, export._pdf_safe(label))
            cur[0] -= row_h
        cur[0] -= 4
    if len(rows) > len(shown):
        text(f"+{len(rows) - len(shown)} more", R, 7.6, 10, GREY)
    if not rows:
        text("Nothing of this phase is inside the frame.", R, 7.6, 10, GREY)
    # the footer, from the bottom up
    foot = [(f"{S['tenant']} · drawn {S['drawn']}", R, 7, GREY),
            ("A planning drawing. Check on site before work starts.", R, 7, GREY)]
    if not S.get("basemap_ok"):
        foot.append(("No base map could be had: the layout alone, still to scale.", B, 7, (0.72, 0.11, 0.11)))
    else:
        foot.append(("Map " + credit + ".", R, 6.8, GREY))
    yy = y
    for s, font, size, rgb in reversed(foot):
        for ln in reversed(simpleSplit(export._pdf_safe(s), font, size, w)):
            c.setFillColorRGB(*rgb)
            c.setFont(font, size)
            c.drawString(x, yy + 1, ln)
            yy += size * 1.3


def build_png(pdf_bytes, dpi=200):
    """The sheet as a PNG for a Word document (rasterised, margins kept white)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[0]
        img = page.render(scale=dpi / 72.0).to_pil()
        page.close()
    finally:
        pdf.close()
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", dpi=(dpi, dpi))
    return out.getvalue()
