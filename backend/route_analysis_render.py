"""
The Route analysis as a PDF and an XLSX (9 Nov 2026, v2.1 task 2.1-6). The data is route_analysis_doc.gather()'s.

The PDF: a first page (the routes side by side, what is in the file and on which page), then route by route (Q6) each
ticked section — A, B, D, E and F as A4 LANDSCAPE pages, a map on the left drawn from the stored lines and a panel on the
right (John, 8 Nov: "route maps with depictions for each category … clear, clean and professional"), C as today's Route
collision evidence pages (A4 portrait, export.build_collision_evidence_pdf drawn into this file), then the page for the
assessor. Page numbers run through the whole file; the first page's page list comes from a sizing pass (no basemap).
Maps: basemap pictures in the tenant's "Maps on paper" style, the lines drawn over them (as the collision evidence does);
an offline harness gets a grey ground. Sections A to F: counts only; no collision's date or hour; loads and lorries,
never "movements".

16 Nov 2026 (step 1c, John: "Yes, as recommended"): a SUMMARY page a route comes first, all of them before the contents
page (S2), and a "Summary" sheet first in the XLSX: the best-option rule's answer for the route's stored options. It
REVERSES "counts only" where it appears: it compares by fixed rules and gives one suggestion. Its collisions stay counts:
no percentage, no "better", every collision bar grey (S4).
"""
import io
import math

import export as X
from export import (NAVY_RGB, GREY, BAND, BAND_GREY_RGB, DEMO_FG_RGB, RS_LOADED, RS_RETURN, _BF, _wrap, _pdf_safe,
                    _hex_rgb)
import route_analysis_doc as RA

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
except Exception:                       # the harness without reportlab stops at build_pdf
    A4 = landscape = mm = ImageReader = rl_canvas = None

RED = "#B91C1C"
# 26 Nov 2026 (the printed maps' route lines, card 3b; John, Q10 "Go with blue"): the legs are band blues now, so the
# busy-hours road leaves the blues for ink, as route_map_export.BUSY_ROAD did (it was the stock blue #2563EB, which sat
# beside the dark blue legs as a second near-identical blue). The name is kept: one constant, read in two places.
BUSY_BLUE = "#3A3C41"
ZONE_RED = "#DC2626"
CYCLE_BLUE = "#0369A1"
USUAL_GREY = "#71717A"
LIMIT_RED = "#C81E1E"
CLAUSES = {"limits": "4.3a iv, 5.6a, 5.6d", "community": "4.3a ii · CLP template §2.4", "collisions": "4.1a, 5.1a, 5.6a",
           "cycle": "5.6a · §2.7", "hours": "5.5a iii", "diversions": "5.6d, 5.6f", "assessor": "5.6a, 5.2c"}
# 10 Nov 2026 (F4): the summary says once whose distance the 250 m is
SEARCH_WORDS = "250 m is Wayscope's search distance, not a CLOCS figure."
SUMMARY_ROWS = [
    ("out_back", "Out · back ({du})"),
    ("limits_below", "Weight, height or width limits below this lorry"),
    ("closures", "Planned road closures on the route"),
    ("schools_health", "Schools · health within 250 m"),
    ("collisions", "Injury collisions on the route (killed or seriously injured)"),
    ("cycle", "Beside a cycle route ({du}) · left turns"),
    ("busy", "Busy-hours road in use (weekdays)"),
    ("diversions", "Dated diversions"),
]
# the questions for the assessor (CLOCS Standard v5; not a CLOCS form). Each points at its sections.
ASSESSOR = [
    ("Which vehicles use this route, how many loads a day at the peak, and at what hours?", ("first", "hours"),
     "4.1a, 5.1a, 5.5a iii", "Finding", "Measures / action"),
    ("What does the police-reported collision record along the route show: where, how severe, who was hurt?",
     ("collisions",), "4.1a, 5.1a", "Finding", "Measures / action"),
    ("Which roads, junctions or lengths carry a recorded collision history, and what is your finding for each?",
     ("collisions",), "5.1a", "Finding", "Measures / action"),
    ("Where could the lorries meet vulnerable road users: cycle routes, crossings, left turns, busy footways?",
     ("cycle", "collisions"), "5.6a, §2.7", "Finding", "Measures / action"),
    ("Were goods vehicles over 3.5 t involved in collisions on the route, and with whom?", ("collisions",),
     "§2.4, 4.1a, 5.1a", "Finding", "Measures / action"),
    ("Which schools, health sites and other community places lie along the route; do they call for timing or other "
     "measures?", ("community",), "§2.7, CLP template §2.4", "Finding", "Measures / action"),
    ("How does this route compare with the alternatives, and why is it the route proposed?", ("collisions", "hours"),
     "5.6a, 5.6f", "Finding", "Reasons for the route"),
    ("Which weight, height and width limits does the lorry meet, and are the \"except for access\" limits for this "
     "site?", ("limits",), "4.3a iv, 5.6a", "Finding", "Measures / action"),
    ("What are the acceptable reasons for leaving the route, and which diversions are permitted?", ("diversions",),
     "5.2b iii, 5.6d", "Finding", "Measures / action"),
    ("What other road user demand is there (traffic, walking and cycling), and from what source?",
     ("collisions", "cycle"), "4.1a, 5.1a", "Finding", "Source"),
    ("What measures are proposed, what are the project's own incidents so far, and when is this next reviewed?",
     (), "5.1a, 5.2c", "Measures (committed / proposed)", "Next review (before phase …)"),
]


def _rgb(h):
    return _hex_rgb(h)


class Doc:
    """One canvas, the page counter, the page furniture (header, footer with the page's own credits)."""

    def __init__(self, D, sizing=False):
        self.D, self.sizing = D, sizing
        self.buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self.buf, pagesize=landscape(A4))
        ids = ", ".join(R["id"] for R in D["routes"])
        self.c.setTitle(_pdf_safe(f"{D['tenant']} · Route analysis · {ids}"))
        self.c.setAuthor("Wayscope")
        self.page = 1
        self.R, self.B = _BF("regular"), _BF("bold")
        self.credits = []
        self.starts = {}           # (route_id, section) -> page
        self.basemap = False
        self.open = False
        self._cont = False

    # ---- pages ----
    def landscape_page(self, credits=()):
        c = self.c
        c.setPageSize(landscape(A4))
        self.W, self.H = landscape(A4)
        self.m = 12 * mm
        self.cw = self.W - 2 * self.m
        self.credits = [x for x in credits if x]
        self.open = True

    def portrait_page(self, credits=()):
        c = self.c
        c.setPageSize(A4)
        self.W, self.H = A4
        self.m = 12 * mm
        self.cw = self.W - 2 * self.m
        self.credits = [x for x in credits if x]
        self.open = True

    def end_page(self):
        c, m = self.c, self.m
        if self.basemap_on_page:
            self.credits.append("Map " + __import__("basemap").credit() + ".")
        text = " ".join(dict.fromkeys(self.credits))
        lines = _wrap(text, self.R, 6.4, self.cw - 50)[:3]
        c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.5)
        c.line(m, m + 8 + len(lines) * 7.6, self.W - m, m + 8 + len(lines) * 7.6)
        y = m + len(lines) * 7.6
        for ln in lines:
            c.setFillColorRGB(*GREY); c.setFont(self.R, 6.4); c.drawString(m, y, ln)
            y -= 7.6
        c.setFillColorRGB(*GREY); c.setFont(self.R, 6.6); c.drawRightString(self.W - m, m + 1, f"Page {self.page}")
        c.showPage()
        self.page += 1
        self.open = False
        self.basemap_on_page = False

    basemap_on_page = False

    def footer_h(self):
        return 34

    def header(self, letter, title, R=None, cont=False):
        """The section's heading: a letter badge, the title, the route's line; the scheme and the date at the right."""
        c, m, W, H, D = self.c, self.m, self.W, self.H, self.D
        y = H - m
        x = m
        if letter:
            c.setFillColorRGB(*_rgb("#1D4ED8")); c.roundRect(x, y - 16, 16, 16, 2.5, stroke=0, fill=1)
            c.setFillColorRGB(1, 1, 1); c.setFont(self.B, 10.5); c.drawCentredString(x + 8, y - 12, letter)
            x += 22
        c.setFillColorRGB(*NAVY_RGB); c.setFont(self.B, 15)
        c.drawString(x, y - 13.5, _pdf_safe(title + (" (continued)" if cont else "")))
        if R:
            sub = f"{R['id']} · {R['origin']} → {R['dest']}"
            if R.get("out_m") is not None:
                du = D["unit"]
                sub += f" · {RA._miles(R['out_m']):.1f} {du} out, {RA._miles(R['back_m'] or 0):.1f} {du} back"
            c.setFillColorRGB(*GREY); c.setFont(self.R, 8.2)
            c.drawString(m, y - 27, _pdf_safe(_fit(sub, self.R, 8.2, self.cw * 0.7)))
        c.setFillColorRGB(*NAVY_RGB); c.setFont(self.B, 8.4); c.drawRightString(W - m, y - 8, _pdf_safe(D["tenant"]))
        yy = y - 18
        if D.get("demo_notice"):
            c.setFillColorRGB(*DEMO_FG_RGB); c.setFont(self.B, 7.4)
            c.drawRightString(W - m, yy, _pdf_safe("DEMO · " + D["demo_notice"]).upper())
            yy -= 9
        c.setFillColorRGB(*GREY); c.setFont(self.R, 7.2); c.drawRightString(W - m, yy, f"Route analysis · made {D['made']}")
        c.setStrokeColorRGB(*NAVY_RGB); c.setLineWidth(0.8); c.line(m, y - 34, W - m, y - 34)
        return y - 42

    # ---- text ----
    def para(self, text, x, y, w, size=7.4, rgb=None, bold=False, lead=None):
        c = self.c
        f = self.B if bold else self.R
        for ln in _wrap(_pdf_safe(text), f, size, w):
            c.setFillColorRGB(*(rgb or NAVY_RGB)); c.setFont(f, size); c.drawString(x, y - size, ln)
            y -= (lead or size + 2.2)
        return y

    def bottom(self):
        return self.m + self.footer_h()


def _fit(text, font, size, w):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    if stringWidth(text, font, size) <= w:
        return text
    while text and stringWidth(text + "…", font, size) > w:
        text = text[:-1]
    return text + "…"


# --------------------------------------------------------------------------- #
#  Maps                                                                        #
# --------------------------------------------------------------------------- #
def _draw_map(doc, x, ytop, w, h, frame, draw, pad=40, max_zoom=15.5, border=False, deco=True, caption=None):
    """A basemap picture framing `frame` (lon, lat points) in w × h points at (x, ytop), `draw(P)` drawing the overlay in
    page points; the demo tag, the scale bar and the north arrow on top. Returns (view, P)."""
    import basemap
    c = doc.c
    pts = [p for p in frame if p]
    if not pts:
        c.setFillColorRGB(0.965, 0.969, 0.973); c.rect(x, ytop - h, w, h, stroke=0, fill=1)
        c.setFillColorRGB(*GREY); c.setFont(doc.R, 8.5)
        c.drawCentredString(x + w / 2, ytop - h / 2, "No road route has been worked out for this route yet.")
        return None, None
    ppt = 1280.0 / max(w, h)
    v = basemap.view(pts, int(round(w * ppt)), int(round(h * ppt)), pad_px=int(pad * ppt / 2.2), max_zoom=max_zoom)
    k = w / v["w"]

    def P(lon, lat):
        px, py = basemap.project(v, lon, lat)
        return x + px * k, ytop - py * k
    c.saveState()
    clip = c.beginPath(); clip.rect(x, ytop - h, w, h); c.clipPath(clip, stroke=0, fill=0)
    png = None if (doc.sizing or getattr(X._SIZING, "on", False)) else basemap.fetch(v)
    if png:
        c.drawImage(ImageReader(io.BytesIO(_jpeg(png))), x, ytop - h, width=w, height=h)
        doc.basemap = doc.basemap_on_page = True
    else:
        c.setFillColorRGB(0.965, 0.969, 0.973); c.rect(x, ytop - h, w, h, stroke=0, fill=1)
    draw(P)
    c.restoreState()
    c.saveState()
    c.translate(x, ytop - h)
    X._map_tag(c, doc.D.get("map_demo_tag"), w, h)
    if deco:
        X._plan_scale_bar(c, v, w)
        X._north_arrow(c, w - 14, h - 30)
    c.restoreState()
    if border:
        c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.7); c.rect(x, ytop - h, w, h, stroke=1, fill=0)
    if caption:
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 7.4); c.drawString(x, ytop + 4, _pdf_safe(caption))
    return v, P


def _jpeg(png):
    """The basemap picture as a JPEG (quality 85, the CLP's): a PNG of each map made a 13 MB file for one route. The
    picture as it came when PIL cannot read it."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception:
        return png


def _legs(doc, P, R, loaded=None, ret=None, out_colour=RS_LOADED, back_colour=RS_RETURN, w=2.4, dashed=False):
    c = doc.c
    lo = R["loaded"] if loaded is None else loaded
    rt = R["return"] if ret is None else ret
    if dashed:
        for coords in (lo, rt):
            _dash_line(c, P, coords, USUAL_GREY, 1.8)
        return
    X._rs_line(c, lambda lon, lat: P(lon, lat), rt, back_colour, w - 0.3, offset=3.0)
    X._rs_line(c, lambda lon, lat: P(lon, lat), lo, out_colour, w)


def _dash_line(c, P, coords, colour, width, dash=(4, 3), offset=0.0):
    if len(coords) < 2:
        return
    pts = X._rs_offset([P(*q) for q in coords], offset)
    p = c.beginPath(); p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    c.saveState(); c.setLineCap(1); c.setLineJoin(1)
    c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(width + 1.6); c.drawPath(p, stroke=1, fill=0)
    c.setStrokeColorRGB(*_rgb(colour)); c.setLineWidth(width); c.setDash(list(dash), 0); c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def _ends(doc, P, R):
    if R["loaded"]:
        X._rs_pin(doc.c, *P(*R["loaded"][0]), "A")
        X._rs_pin(doc.c, *P(*R["loaded"][-1]), "B")


def _num(c, x, y, n, rgb=NAVY_RGB, r=5.4, font=None, square=False):
    t = str(n)
    c.saveState()
    c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(1.0); c.setFillColorRGB(*rgb)
    if square:
        c.rect(x - r, y - r, 2 * r, 2 * r, stroke=1, fill=1)
    else:
        c.circle(x, y, r, stroke=1, fill=1)
    c.setFillColorRGB(1, 1, 1); c.setFont(font or _BF("bold"), 6.6 if len(t) < 3 else 5.4)
    c.drawCentredString(x, y - 2.3, t)
    c.restoreState()


def _roundel(c, x, y, text, n=None):
    """A limit sign: a white disc in a red ring, the figure inside; its number on a small badge."""
    r = 9.5
    c.saveState()
    c.setFillColorRGB(1, 1, 1); c.setStrokeColorRGB(*_rgb(LIMIT_RED)); c.setLineWidth(2.4)
    c.circle(x, y, r, stroke=1, fill=1)
    c.setFillColorRGB(*NAVY_RGB); c.setFont(_BF("bold"), 6.2 if len(text) <= 4 else 5.2)
    c.drawCentredString(x, y - 2.1, _pdf_safe(text))
    c.restoreState()
    if n is not None:
        _num(c, x + 8, y + 8, n, r=4.4)


def _place(placed, x, y, r, offsets):
    """The first offset from (x, y) whose circle of radius r clears every placed one; (x, y) when none does."""
    for dx, dy in offsets:
        cx, cy = x + dx, y + dy
        if all(math.hypot(cx - px, cy - py) >= r + pr + 1.5 for px, py, pr in placed):
            placed.append((cx, cy, r))
            return cx, cy
    placed.append((x + offsets[0][0], y + offsets[0][1], r))
    return x + offsets[0][0], y + offsets[0][1]


OFFSETS = [(0, 17), (15, 11), (-15, 11), (17, -10), (-17, -10), (0, -19), (24, 2), (-24, 2), (26, 18), (-26, 18),
           (26, -18), (-26, -18), (0, 32), (0, -32), (36, 0), (-36, 0)]


def _cluster(points, within_m):
    """The largest group of points (each with "at") where every one is within `within_m` of the group's first: the
    close-up's subject. [] when no two are that close."""
    best = []
    for i, p in enumerate(points):
        g = [q for q in points if q.get("at") and p.get("at") and _hav(p["at"], q["at"]) <= within_m]
        if len(g) > len(best):
            best = g
    return best if len(best) >= 2 else []


def _hav(a, b):
    R_ = 6371000.0
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R_ * math.asin(min(1.0, math.sqrt(h)))


def _key(doc, x, y, rows, w):
    """A legend: [(draw(cx, cy), words)] one per line. Returns the new y."""
    c = doc.c
    for draw, words in rows:
        draw(x + 8, y - 4)
        yy = doc.para(words, x + 20, y, w - 20, 7.0, NAVY_RGB)
        y = min(yy, y - 10.5)
    return y - 2


def _k_line(colour, w=2.4, dash=None):
    def f(c, x, y):
        c.saveState(); c.setLineCap(1); c.setStrokeColorRGB(*_rgb(colour)); c.setLineWidth(w)
        if dash:
            c.setDash(list(dash), 0)
        c.line(x - 8, y, x + 8, y); c.restoreState()
    return f


def _k_dot(colour, r=3.4, ring=False):
    def f(c, x, y):
        c.saveState(); c.setStrokeColorRGB(*_rgb(colour)); c.setFillColorRGB(*((1, 1, 1) if ring else _rgb(colour)))
        c.setLineWidth(1.2); c.circle(x, y, r, stroke=1, fill=1); c.restoreState()
    return f


# --------------------------------------------------------------------------- #
#  The panel: rows that run on to a continuation page when they do not fit    #
# --------------------------------------------------------------------------- #
def _rows(doc, items, x, y, w, row, title_cont, R, letter, credits, floor=None):
    """Draw item rows from y down; the ones that do not fit go to continuation pages (full width). `row(item, x, y, w,
    measure)` returns the row's height (measure=True only measures). Returns y on the last page drawn."""
    floor = floor if floor is not None else doc.bottom()
    i = 0
    while i < len(items):
        hgt = row(items[i], x, y, w, True)
        if y - hgt < floor:
            doc.end_page()
            doc.landscape_page(credits)
            doc._cont = True
            y = doc.header(letter, title_cont, R, cont=True)
            x, w, floor = doc.m, doc.cw, doc.bottom()
            continue
        row(items[i], x, y, w, False)
        y -= hgt
        i += 1
    return y


# --------------------------------------------------------------------------- #
#  A — restrictions and lorry limits                                           #
# --------------------------------------------------------------------------- #
def _geom_points(g):
    import route_compare
    return route_compare._points(g)


def _section_frame(doc):
    m, H = doc.m, doc.H
    top = H - m - 46
    mw = doc.cw * 0.655
    return m, top, mw, top - doc.bottom() - 4, m + mw + 14, doc.cw - mw - 14


def page_limits(doc, R):
    D = doc.D
    L, Cl, Z = R["limits"], R.get("closures") or {}, R.get("zones") or []
    import limits as lim
    srcs = {g.get("source") for g in L["items"] + L["diversion_items"]}
    credits = ["Lorry limits: " + "; ".join(lim.SOURCES[s]["attribution"] for s in sorted(srcs) if s in lim.SOURCES) + "."
               if srcs else None,
               (f"Road closures: {Cl['credit']}." if Cl.get("credit") else None)]
    doc.landscape_page(credits)
    doc._cont = False
    title = "Restrictions and lorry limits"
    y0 = doc.header("A", title, R)
    mx, top, mw, mh, px, pw = _section_frame(doc)
    items = L["items"]
    c = doc.c

    def draw(P):
        for z in Z:
            _zone(c, P, z["geometry"], ZONE_RED, 0.12)
        _legs(doc, P, R)
        placed = []
        for g in items:
            if not g.get("anchor"):
                continue
            ax, ay = P(*g["anchor"])
            c.setFillColorRGB(*_rgb(LIMIT_RED)); c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(0.8)
            c.circle(ax, ay, 2.2, stroke=1, fill=1)
            rx, ry = _place(placed, ax, ay, 11, OFFSETS)
            c.setStrokeColorRGB(*_rgb(LIMIT_RED)); c.setLineWidth(0.6); c.line(ax, ay, rx, ry)
            _roundel(c, rx, ry, g.get("value") or "!", g["no"])
        _ends(doc, P, R)
    frame = R["loaded"] + R["return"] + [g["anchor"] for g in items if g.get("anchor")]
    _draw_map(doc, mx, top, mw, mh, frame, draw)
    y = top
    who = R["vehicle_text"] or "this lorry"
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9.5); c.drawString(px, y - 9.5, "On the route")
    y -= 13
    if not L.get("checked"):
        y = doc.para("The lorry limits have not been checked on this route yet (Data → Routes, Check lorry limits).",
                     px, y, pw, 7.4) - 4
    else:
        y = doc.para(f"{who} · checked {L['checked']}" + (f" · {len(items)} on the route" if items else ""),
                     px, y, pw, 7.2, GREY) - 3
        if not items:
            y = doc.para(f"No stored weight, height or width limit along this route for the {who}.", px, y, pw, 7.4) - 4

    def row(g, x, yy, w, measure):
        right = g["verdict_words"]
        rw = 64 if w < 300 else 110
        head = f"{g['headline'] or 'Limit'} · {g['road']}"
        sub = " · ".join(s for s in ((f"{g['from_a']} {D['unit']} from A" if g.get("from_a") else None), g["legs_words"],
                                     (g["exceptions"].lower() if g.get("exceptions") else None), g.get("where")) if s)
        hl = _wrap(_pdf_safe(head), doc.B, 7.4, w - 18 - rw)
        sl = _wrap(_pdf_safe(sub), doc.R, 6.6, w - 18 - rw)
        h = max(16, len(hl) * 9 + len(sl) * 8 + 5)
        if measure:
            return h
        _num(c, x + 6, yy - 6, g["no"])
        yt = yy
        for ln in hl:
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 7.4); c.drawString(x + 16, yt - 7.4, ln); yt -= 9
        for ln in sl:
            c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.6); c.drawString(x + 16, yt - 6.6, ln); yt -= 8
        c.setFillColorRGB(*(_rgb(RED) if g["verdict"] == "exceeds" else NAVY_RGB)); c.setFont(doc.B, 6.8)
        for j, ln in enumerate(_wrap(right, doc.B, 6.8, rw)):
            c.drawRightString(x + w, yy - 7.4 - j * 8, ln)
        c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.4); c.line(x, yy - h + 2, x + w, yy - h + 2)
        return h
    y = _rows(doc, items, px, y, pw, row, title, R, "A", credits)
    # the rest of the panel (on whichever page the rows ended)
    x, w = (px, pw) if not _on_cont(doc, px) else (doc.m, doc.cw)
    blocks = []
    o = L.get("others")
    if o and o["n"]:
        if not o["different"]:
            blocks.append((7.0, GREY, f"The same limits for the other {o['n']} lorr{'y' if o['n'] == 1 else 'ies'} on this route."))
        else:
            blocks.append((7.0, GREY, "Different for " + ", ".join(o["different"]) + " (the Routes page lists each lorry's)."))
    if L["diversion_items"]:
        blocks.append((7.0, NAVY_RGB, "On a diversion (section F): " + "; ".join(
            f"{g['headline']} · {g['road']} — {g['verdict_words'].lower()}" for g in L["diversion_items"][:6])
            + (" …" if len(L["diversion_items"]) > 6 else "")))
    if any(g.get("exceptions") and g["verdict"] != "allowed" for g in items):
        blocks.append((6.8, GREY, "\"Except for access\": a lorry may use the road to reach premises on it — check whether "
                                  "this site is one. The signs on the road come first."))
    if any(g["verdict"] == "allowed" for g in items):
        blocks.append((6.8, GREY, "Allowed: the site is on this road. Check the sign names this site. "
                                  "The signs on the road come first."))
    if Cl.get("held"):
        n = len(Cl["hits"])
        t = (f"None of the planned closures held on {Cl['when']} is on this route (within {Cl.get('near_m') or RA.CLOSURE_NEAR_M} m)."
             if not n else f"{n} held on {Cl['when']} touch the route: " + "; ".join(
                 " ".join(s for s in (h.get("road"), h.get("what"), (f"{h['from']} – {h['to']}" if h.get("from") else None)) if s)
                 for h in Cl["hits"][:5]) + (" …" if n > 5 else "") + ".")
    else:
        t = Cl.get("why") or "Not held."
    blocks.append(("h", None, "Planned road closures"))
    blocks.append((7.0, NAVY_RGB, t))
    blocks.append(("h", None, "The scheme's own zones"))
    blocks.append((7.0, NAVY_RGB, ("Crossed: " + ", ".join(z["name"] for z in Z) + ".") if Z else
                   "None crossed. (A dated zone that diverts the route is in section F.)"))
    y -= 4
    for size, rgb, text in blocks:
        need = 14 if size == "h" else len(_wrap(text, doc.R, size, w)) * (size + 2.2) + 4
        if y - need < doc.bottom():
            doc.end_page(); doc.landscape_page(credits)
            y = doc.header("A", title, R, cont=True); x, w = doc.m, doc.cw
        if size == "h":
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.4); c.drawString(x, y - 8.4, text); y -= 12
        else:
            y = doc.para(text, x, y, w, size, rgb) - 4
    if not _on_cont(doc, px) and y - 50 > doc.bottom():
        y = _key(doc, x, y - 4, [(lambda cx, cy: _k_line(RS_LOADED)(c, cx, cy), "Out, loaded, A to B"),
                                 (lambda cx, cy: _k_line(RS_RETURN)(c, cx, cy), "Back, empty, B to A"),
                                 (lambda cx, cy: _roundel_small(c, cx, cy), "A weight, height or width limit; red dot: "
                                  "where it is recorded")], w)
    doc.end_page()


def _roundel_small(c, x, y):
    c.saveState(); c.setFillColorRGB(1, 1, 1); c.setStrokeColorRGB(*_rgb(LIMIT_RED)); c.setLineWidth(1.6)
    c.circle(x, y, 4.6, stroke=1, fill=1); c.restoreState()


def _on_cont(doc, px):
    """True once the panel's rows have run onto a continuation page (the header's "(continued)" page)."""
    return getattr(doc, "_cont", False)


def _zone(c, P, geom, colour, alpha):
    if not geom:
        return
    t = geom.get("type")
    polys = ([geom["coordinates"]] if t == "Polygon" else geom["coordinates"] if t == "MultiPolygon" else [])
    c.saveState()
    for poly in polys:
        for ring in poly[:1]:
            if len(ring) < 3:
                continue
            p = c.beginPath(); p.moveTo(*P(*ring[0][:2]))
            for q in ring[1:]:
                p.lineTo(*P(*q[:2]))
            p.close()
            c.setFillColorRGB(*_rgb(colour)); c.setFillAlpha(alpha); c.drawPath(p, stroke=0, fill=1)
            c.setFillAlpha(1); c.setStrokeColorRGB(*_rgb(colour)); c.setLineWidth(1.2); c.drawPath(p, stroke=1, fill=0)
    if t in ("LineString", "MultiLineString"):
        lines = [geom["coordinates"]] if t == "LineString" else geom["coordinates"]
        for ln in lines:
            _dash_line(c, P, [q[:2] for q in ln], colour, 2.0, dash=(2, 2))
    c.restoreState()


# --------------------------------------------------------------------------- #
#  B — community places                                                        #
# --------------------------------------------------------------------------- #
def page_community(doc, R):
    D, C = doc.D, R["community"]
    c = doc.c
    credits = [C.get("credit")]
    title = "Community places"
    doc.landscape_page(credits)
    doc._cont = False
    doc.header("B", title, R)
    mx, top, mw, mh, px, pw = _section_frame(doc)
    named = C["named"]
    near = C["near_m"]
    clus = _cluster(named, 900) if len(named) > 6 else []
    in_inset = {id(p) for p in clus}

    def draw(P):
        if R["loaded"]:
            _band(c, P, R["loaded"], near.get("schools", 250))
        _legs(doc, P, R)
        for p in C["others"]:
            if p["kind"] in ("bus_stops", "residential"):
                continue
            x, y = P(*p["at"])
            c.setFillColorRGB(*_rgb(C["colours"][p["kind"]])); c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(0.5)
            c.circle(x, y, 1.9, stroke=1, fill=1)
        placed = []
        for p in named:
            x, y = P(*p["at"])
            if id(p) in in_inset:
                c.setFillColorRGB(*_rgb(C["colours"][p["kind"]])); c.circle(x, y, 2.4, stroke=0, fill=1)
                continue
            nx, ny = _place(placed, x, y, 6, [(0, 0), (9, 7), (-9, 7), (9, -7), (-9, -7), (0, 12), (0, -12), (14, 0), (-14, 0)])
            if (nx, ny) != (x, y):
                c.setStrokeColorRGB(*_rgb(C["colours"][p["kind"]])); c.setLineWidth(0.5); c.line(x, y, nx, ny)
            _num(c, nx, ny, p["no"], _rgb(C["colours"][p["kind"]]), r=5.2, square=p["kind"] != "schools")
        _ends(doc, P, R)
    _, Pm = _draw_map(doc, mx, top, mw, mh, R["loaded"] + R["return"], draw)
    y = top
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9.5)
    c.drawString(px, y - 9.5, f"Within {near.get('schools', 250)} m of the route"); y -= 13
    if not C.get("fetched"):
        y = doc.para("The community places have not been fetched yet (Config → Map and bulletin).", px, y, pw, 7.4)
        doc.end_page()
        return
    dists = sorted({v for v in near.values() if isinstance(v, (int, float))}, reverse=True)
    dist_words = " and ".join(f"{v:g} m" for v in dists) or "250 m"
    y = doc.para(f"As fetched {C['fetched']}. Both directions, every lorry. {dist_words} "
                 f"{'are' if len(dists) > 1 else 'is'} Wayscope's search distance{'s' if len(dists) > 1 else ''}, "
                 "not a CLOCS figure.", px, y, pw, 6.8, GREY) - 3
    # the counts, two columns
    kinds = list(C["counts"])
    half = (len(kinds) + 1) // 2
    for i, k in enumerate(kinds):
        col, r_ = divmod(i, half)
        xx = px + col * pw / 2
        yy = y - r_ * 10
        lab = C["labels"][k] + (f" ({near[k]} m)" if near.get(k) != near.get("schools") else "")
        c.setFillColorRGB(*_rgb(C["colours"][k])); c.rect(xx, yy - 6.6, 5, 5, stroke=0, fill=1)
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.6); c.drawString(xx + 8, yy - 6.4, _fit(lab, doc.R, 6.6, pw / 2 - 30))
        c.setFont(doc.B, 6.8); c.drawRightString(xx + pw / 2 - 6, yy - 6.4, str(C["counts"][k]))
    y -= half * 10 + 6
    rows_h = sum(_place_row_h(doc, p, pw) for p in named) + 12
    if clus:
        ih = 112
        if y - ih - 18 - rows_h > doc.bottom() or (y - rows_h < doc.bottom() and len(named) > 20):
            def drawi(P):
                if R["loaded"]:
                    _band(c, P, R["loaded"], near.get("schools", 250))
                _legs(doc, P, R)
                pl = []
                for p in clus:
                    x_, y_ = P(*p["at"])
                    nx, ny = _place(pl, x_, y_, 6, [(0, 0), (10, 8), (-10, 8), (10, -8), (-10, -8), (0, 13), (0, -13)])
                    if (nx, ny) != (x_, y_):
                        c.setStrokeColorRGB(*_rgb(C["colours"][p["kind"]])); c.setLineWidth(0.5); c.line(x_, y_, nx, ny)
                    _num(c, nx, ny, p["no"], _rgb(C["colours"][p["kind"]]), r=5.2, square=p["kind"] != "schools")
            _draw_map(doc, px, y - 12, pw, ih, [p["at"] for p in clus], drawi, pad=30, max_zoom=16.5, border=True,
                      deco=False, caption=f"Closer: {clus[0]['no']}–{clus[-1]['no']}, where they crowd together")
            y -= ih + 18
            if Pm:                             # where the close-up is, on the main map
                xs = [Pm(*p["at"]) for p in clus]
                x0, y0 = min(q[0] for q in xs) - 6, min(q[1] for q in xs) - 6
                x1, y1 = max(q[0] for q in xs) + 6, max(q[1] for q in xs) + 6
                c.saveState(); c.setStrokeColorRGB(*NAVY_RGB); c.setLineWidth(0.6); c.setDash(3, 2)
                c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0); c.restoreState()
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.4)
    c.drawString(px, y - 8.4, "Schools, hospitals and health, A to B" if named else "No school, hospital or health place"); y -= 12

    def row(p, x, yy, w, measure):
        name = p["name"] or p["kind_label"]
        sub = " · ".join(s for s in ((f"{p['from_a']} {D['unit']} from A" if p.get("from_a") else None),
                                     p["kind_label"][:-1] if p["kind_label"].endswith("s") else p["kind_label"],
                                     f"{p['m']} m from the route") if s)
        hl = _wrap(_pdf_safe(name), doc.B, 7.0, w - 18)
        h = len(hl) * 8.6 + 8.2 + 3
        if measure:
            return h
        _num(c, x + 6, yy - 5.8, p["no"], _rgb(C["colours"][p["kind"]]), r=5.0, square=p["kind"] != "schools")
        yt = yy
        for ln in hl:
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 7.0); c.drawString(x + 16, yt - 7.0, ln); yt -= 8.6
        c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.4); c.drawString(x + 16, yt - 6.4, _fit(_pdf_safe(sub), doc.R, 6.4, w - 18))
        return h
    _rows(doc, named, px, y, pw, row, title, R, "B", credits)
    doc.end_page()


def _place_row_h(doc, p, w):
    """A named place's row height in the B panel (the row() below draws it)."""
    return len(_wrap(_pdf_safe(p["name"] or p["kind_label"]), doc.B, 7.0, w - 18)) * 8.6 + 8.2 + 3


def _band(c, P, line, metres):
    """The strip `metres` either side of the line, shaded: the line drawn wide at the map's scale."""
    if len(line) < 2:
        return
    import basemap  # noqa: F401  (the scale comes from the projection P itself)
    a, b = P(*line[0]), P(*line[min(len(line) - 1, 1)])
    # points per metre at this latitude, measured on the first stretch of the line
    p0 = line[0]
    p1 = [p0[0], p0[1] + metres / 111320.0]
    w = abs(P(*p1)[1] - P(*p0)[1]) * 2
    p = c.beginPath(); p.moveTo(*P(*line[0]))
    for q in line[1:]:
        p.lineTo(*P(*q))
    c.saveState(); c.setLineCap(1); c.setLineJoin(1)
    c.setStrokeColorRGB(*_rgb("#1D4ED8")); c.setStrokeAlpha(0.10); c.setLineWidth(max(w, 2))
    c.drawPath(p, stroke=1, fill=0); c.restoreState()
    del a, b


# --------------------------------------------------------------------------- #
#  D — cycle routes and left turns                                             #
# --------------------------------------------------------------------------- #
def page_cycle(doc, R):
    D, Q = doc.D, R["cycle"]
    c = doc.c
    credits = [Q.get("credit")]
    title = "Cycle routes and left turns"
    doc.landscape_page(credits)
    doc._cont = False
    doc.header("D", title, R)
    mx, top, mw, mh, px, pw = _section_frame(doc)
    frame = R["loaded"] + R["return"]
    bb = _bbox(frame)

    def draw(P):
        _legs(doc, P, R)
        for _n, line in Q["lines"]:
            if bb and _bbox(line) and not _overlap(_bbox(line), bb, 0.02):
                continue
            _dash_line(c, P, line, CYCLE_BLUE, 1.5, dash=(3, 2))
        for x in Q["meets"]:
            if x.get("at"):
                cx, cy = P(*x["at"])
                c.setFillColorRGB(*_rgb(CYCLE_BLUE)); c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(0.6)
                c.circle(cx, cy, 2.0, stroke=1, fill=1)
        placed = []
        for t in Q["turns"]:
            if not t.get("at"):
                continue
            x0, y0 = P(*t["at"])
            nx, ny = _place(placed, x0, y0, 6, [(0, 12), (11, 8), (-11, 8), (12, -8), (-12, -8), (0, -13), (18, 0), (-18, 0)])
            c.setStrokeColorRGB(*NAVY_RGB); c.setLineWidth(0.5); c.line(x0, y0, nx, ny)
            _num(c, nx, ny, t["no"], _rgb("#B45309") if t.get("cycle") else NAVY_RGB)
        _ends(doc, P, R)
    _draw_map(doc, mx, top, mw, mh, frame, draw)
    y = top
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9.5); c.drawString(px, y - 9.5, "This route and its alternatives"); y -= 14
    cols = Q["columns"][:4]
    if not Q["shown"]:
        y = doc.para("No cycle routes: the community places have not been fetched (Config → Map and bulletin). The left "
                     "turns are counted from the road route.", px, y, pw, 7.2) - 4
    rows_ = [(f"Beside a cycle route ({D['unit']}, within {Q['beside_m']} m)", "beside"),
             (f"Places a cycle route meets it (within {Q['meets_m']} m)", "meets"),
             (f"Left turns of {Q['turn_min']}° or more", "turns"),
             (f"…of those, within {Q['turn_cycle_m']} m of a cycle route", "turns_cycle"),
             ("Cyclists hurt on the route (killed or seriously injured)", "cyc")]
    lab_w = pw - 44 * len(cols)
    c.setFillColorRGB(*BAND); c.rect(px, y - 11, pw, 11, stroke=0, fill=1)
    for j, h in enumerate(cols):
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 6.4)
        c.drawRightString(px + lab_w + (j + 1) * 44 - 3, y - 8, _pdf_safe(h.get("label", "")).replace("Alternative", "Alt"))
    y -= 12
    for lab, k in rows_:
        lines_ = _wrap(lab, doc.R, 6.6, lab_w - 4)
        for i, ln in enumerate(lines_):
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.6); c.drawString(px + 2, y - 7.2 - i * 7.6, ln)
        for j, h in enumerate(cols):
            v = (f"{h.get('cyclist', 0)} ({h.get('cyclist_ksi', 0)})" if k == "cyc" else h.get(k))
            c.setFont(doc.B if j == 0 else doc.R, 6.8)
            c.drawRightString(px + lab_w + (j + 1) * 44 - 3, y - 7.2, "—" if v is None else str(v))
        y -= max(10, len(lines_) * 7.6 + 2.4)
    y -= 6
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.4); c.drawString(px, y - 8.4, "Left turns, A to B"); y -= 12
    if not Q["turns"]:
        y = doc.para("None of 45° or more on the road route.", px, y, pw, 7.2) - 4

    def row(t, x, yy, w, measure):
        txt = f"{t['words']} from A" + (f" · {t['cycle']} {t['cycle_m']} m away" if t.get("cycle") else " · no cycle route within "
                                         f"{Q['turn_cycle_m']} m")
        ln = _wrap(_pdf_safe(txt), doc.R, 6.8, w - 18)
        h = max(13, len(ln) * 8.2 + 3)
        if measure:
            return h
        _num(c, x + 6, yy - 5.6, t["no"], _rgb("#B45309") if t.get("cycle") else NAVY_RGB, r=5.0)
        for i, s in enumerate(ln):
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.8); c.drawString(x + 16, yy - 7.2 - i * 8.2, s)
        return h
    y = _rows(doc, Q["turns"], px, y, pw, row, title, R, "D", credits)
    x, w = (doc.m, doc.cw) if doc._cont else (px, pw)
    notes = [f"Left turns come from the stored road route (the heading over the next {Q['turn_window_m']} m against the "
             "last), so a roundabout's gentle entry may not count. Cycle routes are mapped by volunteers: one can be missing. "
             "Nothing is scored."]
    if Q["meets"]:
        notes.insert(0, "A cycle route meets the route at " + ", ".join(m_["words"] for m_ in Q["meets"][:16])
                     + (" …" if len(Q["meets"]) > 16 else "") + ".")
    for t in notes:
        if y - 30 < doc.bottom():
            break
        y = doc.para(t, x, y - 2, w, 6.6, GREY) - 3
    if not doc._cont and y - 46 > doc.bottom():
        _key(doc, x, y - 4, [(lambda cx, cy: _k_line(CYCLE_BLUE, 1.5, (3, 2))(c, cx, cy), "A cycle route; dot: where one meets the route"),
                             (lambda cx, cy: _num(c, cx, cy, "1", NAVY_RGB, r=4.6), "A left turn"),
                             (lambda cx, cy: _num(c, cx, cy, "1", _rgb("#B45309"), r=4.6), "A left turn near a cycle route")], w)
    doc.end_page()


def _bbox(pts):
    pts = [p for p in pts if p]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _overlap(a, b, pad):
    return not (a[2] < b[0] - pad or a[0] > b[2] + pad or a[3] < b[1] - pad or a[1] > b[3] + pad)


# --------------------------------------------------------------------------- #
#  E — busy-hour times                                                         #
# --------------------------------------------------------------------------- #
def _hr_words(h):
    if h is None:
        return "—"
    return f"{h:.2f} h"


def page_hours(doc, R):
    D, E = doc.D, R["hours"]
    c = doc.c
    title = "Busy-hour times"
    credits = ["Drive times: HERE, worked out for a weekday from the route's stored road."]
    doc.landscape_page(credits)
    doc._cont = False
    doc.header("E", title, R)
    m, top = doc.m, doc.H - doc.m - 46
    use = next((u for u in E["uses"] if u["status"] == "in_use" and u["loaded"]), None)
    Q = E.get("cycle_by_hour")
    if Q:
        mw, mh = doc.cw * 0.47, 228
    else:
        _mx, _t, mw, mh, _px, _pw = _section_frame(doc)
    px, pw = m + mw + 14, doc.cw - mw - 14

    def draw(P):
        _legs(doc, P, R)
        if use:
            X._rs_line(c, P, use["return"], BUSY_BLUE, 1.8, offset=-4.2)
            X._rs_line(c, P, use["loaded"], BUSY_BLUE, 2.2, offset=-7.0)
        _ends(doc, P, R)
    frame = R["loaded"] + R["return"] + ((use["loaded"] + use["return"]) if use else [])
    _draw_map(doc, m, top, mw, mh, frame, draw)
    y = top
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9.5); c.drawString(px, y - 9.5, "Round trip by the hour it sets off, weekdays"); y -= 13
    y = doc.para(f"The {E['profile']}: drive time both ways plus loading, tipping and turnaround.", px, y, pw, 6.8, GREY) - 3
    if not E["worked_out"]:
        y = doc.para("The busy-hour times are not worked out for this route yet (Data → Routes, Busy-hour times).",
                     px, y, pw, 7.4) - 4
    else:
        hrs = ["08:00", "12:00", "17:00"]
        heads = ["Option", f"Out · back ({D['unit']})"] + hrs + ["Plan"]
        hw, ow = (46, 70) if pw >= 360 else (38, 56)
        cwid = [pw - 4 * hw - ow, ow, hw, hw, hw, hw]
        c.setFillColorRGB(*BAND); c.rect(px, y - 11, pw, 11, stroke=0, fill=1)
        xx = px
        for h_, w_ in zip(heads, cwid):
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 6.4)
            if h_ == "Option":
                c.drawString(xx + 2, y - 8, h_)
            else:
                c.drawRightString(xx + w_ - 3, y - 8, h_)
            xx += w_
        y -= 12
        best = {}
        for h_ in hrs:
            have = [(r_["at"].get(h_), i) for i, r_ in enumerate(E["rows"]) if r_["at"].get(h_) is not None]
            best[h_] = min(have)[1] if len(have) > 1 else None
        for i, r_ in enumerate(E["rows"]):
            vals = [r_["label"] if pw >= 360 else r_["label"].replace("Alternative", "Alt"), (f"{X._dist(r_['out_km']):.1f} · {X._dist(r_['back_km']):.1f}" if r_["out_km"] is not None else "—")]
            vals += [_hr_words(r_["at"].get(h_)) for h_ in hrs] + [_hr_words(r_["plan_hr"])]
            xx = px
            for j, (v, w_) in enumerate(zip(vals, cwid)):
                quick = j >= 2 and j < 5 and best.get(hrs[j - 2]) == i
                if quick:
                    c.setFillColorRGB(*X.CE_QUICK_FILL); c.rect(xx + 1, y - 9.5, w_ - 2, 10, stroke=0, fill=1)
                c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B if quick or j == 0 else doc.R, 6.8)
                if j == 0:
                    c.drawString(xx + 2, y - 7.2, _pdf_safe(v))
                else:
                    c.drawRightString(xx + w_ - 3, y - 7.2, v)
                xx += w_
            y -= 10.5
        y = doc.para("Green, bold: the quicker option at that hour. \"—\": not worked out at that hour. Plan: the figure the "
                     "plan uses.", px, y - 2, pw, 6.4, GREY) - 4
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.4); c.drawString(px, y - 8.4, "Another road in the busy hours"); y -= 12
    lines = []
    for u in E["uses"]:
        s = u.get("savings") or {}
        p = s.get("planned") or {}
        t = (f"{'In use' if u['status'] == 'in_use' else 'Paused'} since {u['since']}: Alt {u['alt']} on weekdays "
             f"{u['from']}–{u['to']}.")
        if p and p.get("of"):
            t += (f" Planned to the end of the plan: {p['trips']:.0f} of {p['of']} trips take it; "
                  + _saving_words(p) + " (estimated).")
        lines.append(t)
    if not E["uses"]:
        offers = E.get("offers") or []
        if offers:
            for o in offers:
                bands = ", ".join(f"{b['from']}–{b['to']}" for b in o.get("bands") or [])
                lines.append(f"Offered, not in use: Alt {o['alt']} on weekdays {bands} (fewer collisions on it in those hours;"
                             " section C).")
        else:
            lines.append("None in use or offered for this route.")
    for t in lines:
        y = doc.para(t, px, y, pw, 7.0) - 3
    if use and (y - 30 > top - mh or not Q):
        y = _key(doc, px, y - 2, [(lambda cx, cy: _k_line(RS_LOADED)(c, cx, cy), "The usual road out (back in light blue)"),
                                  (lambda cx, cy: _k_line(BUSY_BLUE)(c, cx, cy), f"Alt {use['alt']}, weekdays {use['from']}–{use['to']}")],
                 pw)
    # the chart, full width under the map (the collision evidence's own "Cycle by hour")
    yb = min(y, top - mh - 10)
    if Q:
        def cont():
            doc.end_page(); doc.landscape_page(credits)
            return doc.header("E", title, R, cont=True)
        X._ce_cycle_by_hour(c, {"cycle_by_hour": Q, "route_id": R["id"]}, m, yb, doc.cw, doc.R, doc.B,
                            lambda t, y_, s=7.2, *a: doc.para(t, m, y_, doc.cw, s, GREY), cont, doc.footer_h())
    doc.end_page()


def _saving_words(p):
    cur = X._cur()
    parts = [(p.get("eur"), lambda v: f"{cur}{abs(v):,.0f}"), (p.get("min"), lambda v: (f"{abs(v) / 60:.1f} h" if abs(v) >= 90 else f"{abs(v):.0f} min")),
             (p.get("kg"), lambda v: (f"{abs(v) / 1000:.2f} t CO₂e" if abs(v) >= 1000 else f"{abs(v):.0f} kg CO₂e")),
             (p.get("km"), lambda v: f"{X._dist(abs(v)):,.0f} {X._du()}")]
    parts = [(v, f) for v, f in parts if v is not None and not (f is parts[0][1] and p.get("eur_missing"))]
    less = all(v <= 0 for v, _ in parts)
    more = all(v >= 0 for v, _ in parts)
    words = [f(v) for v, f in parts]
    lst = (", ".join(words[:-1]) + " and " + words[-1]) if len(words) > 1 else (words[0] if words else "")
    if less:
        return "saves about " + lst
    if more:
        return "adds about " + lst
    return ", ".join(f"{f(v)} {'more' if v > 0 else 'less'}" for v, f in parts)


# --------------------------------------------------------------------------- #
#  F — diversions                                                              #
# --------------------------------------------------------------------------- #
def page_diversions(doc, R):
    D, F = doc.D, R["diversions"]
    c = doc.c
    title = "Diversions"
    credits = ["Zones are the scheme's own."]
    if not F["items"]:
        return False
    for k, d in enumerate(F["items"]):
        doc.landscape_page(credits)
        doc._cont = False
        doc.header("F", title + (f" ({k + 1} of {len(F['items'])})" if len(F["items"]) > 1 else ""), R)
        mx, top, mw, mh, px, pw = _section_frame(doc)

        def draw(P, d=d):
            for z in d["zones"]:
                _zone(c, P, z["geometry"], ZONE_RED, 0.14)
            _legs(doc, P, R, dashed=True)
            X._rs_line(c, P, d["return"], RS_RETURN, 2.1, offset=3.0)
            X._rs_line(c, P, d["loaded"], RS_LOADED, 2.4)
            _ends(doc, P, R)
        zpts = [p for z in d["zones"] for p in _geom_points(z["geometry"])]
        _draw_map(doc, mx, top, mw, mh, R["loaded"] + R["return"] + d["loaded"] + d["return"] + zpts, draw)
        y = top
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9.5); c.drawString(px, y - 9.5, d["when"] or "Dated"); y -= 13
        if d["because"]:
            y = doc.para("Because of " + "; ".join(d["because"]) + ".", px, y, pw, 7.4) - 2
        for n in d["notes"][:2]:
            y = doc.para(n, px, y, pw, 6.8, GREY) - 2
        if d.get("back_on"):
            y = doc.para(f"Back on the usual road from {d['back_on']}.", px, y, pw, 6.8, GREY) - 4
        du = D["unit"]
        for leg, more, words, div in (("Out", d["out_more_m"], d["loaded_words"], d["out_diverted"]),
                                     ("Back", d["back_more_m"], d["return_words"], d["back_diverted"])):
            t = (f"{leg}: " + (("the way round, " + (words or "")) if div else "the usual road")
                 + (f" ({'+' if more >= 0 else '−'}{abs(RA._miles(more)):.1f} {du})" if (div and more is not None) else ""))
            y = doc.para(t, px, y, pw, 7.2) - 2
        if d.get("limits_lines"):
            y -= 3
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.0); c.drawString(px, y - 8, "Lorry limits on the way taken"); y -= 11
            for ln in d["limits_lines"][:4]:
                y = doc.para(ln, px, y, pw, 6.8) - 2
        zp = [p for z in d["zones"] for p in _geom_points(z["geometry"])]
        if zp and y - 140 > doc.bottom():
            def drawz(P, d=d):
                for z in d["zones"]:
                    _zone(c, P, z["geometry"], ZONE_RED, 0.14)
                _legs(doc, P, R, dashed=True)
                X._rs_line(c, P, d["return"], RS_RETURN, 2.1, offset=3.0)
                X._rs_line(c, P, d["loaded"], RS_LOADED, 2.4)
            _draw_map(doc, px, y - 14, pw, 112, zp, drawz, pad=40, max_zoom=15.5, border=True, deco=False,
                      caption="Closer: the zone")
            y -= 132
        if y - 46 > doc.bottom():
            _key(doc, px, y - 4, [(lambda cx, cy: _k_line(USUAL_GREY, 1.8, (4, 3))(c, cx, cy), "The usual road"),
                                  (lambda cx, cy: _k_line(RS_LOADED)(c, cx, cy), "The way taken out (back in light blue)"),
                                  (lambda cx, cy: _k_zone(c, cx, cy), "The zone")], pw)
        doc.end_page()
    return True


def _k_zone(c, x, y):
    c.saveState(); c.setFillColorRGB(*_rgb(ZONE_RED)); c.setFillAlpha(0.18); c.setStrokeColorRGB(*_rgb(ZONE_RED))
    c.setLineWidth(1); c.rect(x - 7, y - 4, 14, 8, stroke=1, fill=1); c.restoreState()


def diversions_line(F):
    """The words when there is no diversion page: said on the route's assessor page and the first page (no page)."""
    if F["items"]:
        return None
    t = "No diversion is planned for this route."
    if F["no_way"]:
        t += " " + "; ".join(("Kept on its usual road" if n["kept"] else "No way round yet") + f" in {n['when']}"
                             + (f" ({', '.join(n['because'])})" if n["because"] else "") for n in F["no_way"]) + "."
    return t


# --------------------------------------------------------------------------- #
#  The first page and the assessor                                             #
# --------------------------------------------------------------------------- #
def page_first(doc, pages):
    D = doc.D
    c = doc.c
    doc.landscape_page(["Made from what Wayscope holds; nothing was fetched for this file."])
    m, W, H = doc.m, doc.W, doc.H
    y = H - m
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 20); c.drawString(m, y - 20, "Route analysis")
    c.setFont(doc.B, 9); c.drawRightString(W - m, y - 9, _pdf_safe(D["tenant"]))
    yy = y - 21
    if D.get("demo_notice"):
        c.setFillColorRGB(*DEMO_FG_RGB); c.setFont(doc.B, 8); c.drawRightString(W - m, yy, _pdf_safe("DEMO · " + D["demo_notice"]).upper())
        yy -= 11
    c.setFillColorRGB(*GREY); c.setFont(doc.R, 8); c.drawRightString(W - m, yy, f"Made {D['made']}")
    y -= 28
    if len(D["routes"]) == 1:
        R = D["routes"][0]
        sub = f"{R['id']} · {R['origin']} → {R['dest']}"
    else:
        sub = f"{len(D['routes'])} routes"
    sub += f" · drawn for the {D['lorry_text']}" if D.get("lorry_text") else ""
    y = doc.para(sub, m, y, doc.cw * 0.7, 11, NAVY_RGB, bold=True) - 2
    y = doc.para("Evidence for a route risk assessment, not the assessment. Sections A to F are counts side by side: "
                 "nothing in them is divided or ranked. The summary compares each option by fixed rules. Each section "
                 "says when its data was last brought in.",
                 m, y, doc.cw * 0.7, 7.6, GREY) - 8
    # the contents (left) and the routes side by side (right)
    lw = doc.cw * 0.36
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 10); c.drawString(m, y - 10, "In this file"); y1 = y - 15
    c.setFillColorRGB(*BAND); c.rect(m, y1 - 11, lw, 11, stroke=0, fill=1)
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 6.6)
    c.drawString(m + 2, y1 - 8, "Section"); c.drawString(m + lw * 0.55, y1 - 8, "CLOCS Standard v5"); c.drawRightString(m + lw - 2, y1 - 8, "Page")
    y1 -= 13
    spg = [p for p in (pages.get((R["id"], "summary")) for R in D["routes"]) if p]
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 7.2); c.drawString(m + 2, y1 - 7.6, "Summary · one page a route")
    c.drawRightString(m + lw - 2, y1 - 7.6, (f"{spg[0]}–{spg[-1]}" if len(spg) > 1 else str(spg[0])) if spg else "—")
    c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.3); c.line(m, y1 - 10.5, m + lw, y1 - 10.5)
    y1 -= 11.5
    for k in D["sections"]:
        lab = (f"{RA.LETTER[k]} · " if RA.LETTER[k] else "") + RA.TITLE[k]
        pg = [pages.get((R["id"], k)) for R in D["routes"]]
        pg = [p for p in pg if p]
        pw_ = (", ".join(map(str, pg)) if len(pg) <= 3 else f"{pg[0]}, {pg[1]} … {pg[-1]}") if pg else "—"
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 7.2); c.drawString(m + 2, y1 - 7.6, lab)
        c.setFillColorRGB(*GREY); c.drawString(m + lw * 0.55, y1 - 7.6, CLAUSES.get(k, ""))
        c.setFillColorRGB(*NAVY_RGB); c.drawRightString(m + lw - 2, y1 - 7.6, pw_)
        c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.3); c.line(m, y1 - 10.5, m + lw, y1 - 10.5)
        y1 -= 11.5
    left_out = [RA.TITLE[k] for k in RA.SECTION_KEYS if k not in D["sections"]]
    if left_out:
        y1 = doc.para("Not in this file: " + ", ".join(left_out) + ".", m, y1 - 3, lw, 6.6, GREY)
    if len(D["routes"]) > 1:
        y1 -= 6
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 8.4); c.drawString(m, y1 - 8.4, "Routes, in order"); y1 -= 12
        for R in D["routes"]:
            p = pages.get((R["id"], "_start"))
            c.setFont(doc.R, 6.8); c.setFillColorRGB(*NAVY_RGB)
            c.drawString(m + 2, y1 - 7, _fit(_pdf_safe(f"{R['id']} · {R['origin']} → {R['dest']}"), doc.R, 6.8, lw - 30))
            c.drawRightString(m + lw - 2, y1 - 7, str(p or ""))
            y1 -= 9.2
    # the routes side by side
    rx = m + lw + 18
    rw = doc.cw - lw - 18
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 10); c.drawString(rx, y - 10, "The routes side by side" if len(D["routes"]) > 1 else "The route at a glance")
    y2 = y - 15
    routes = D["routes"]
    per = 6
    for start in range(0, len(routes), per):
        chunk = routes[start:start + per]
        labw = rw - 64 * len(chunk)
        c.setFillColorRGB(*BAND); c.rect(rx, y2 - 11, rw, 11, stroke=0, fill=1)
        for j, R in enumerate(chunk):
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 6.8); c.drawRightString(rx + labw + (j + 1) * 64 - 3, y2 - 8, R["id"])
        y2 -= 12
        for key, lab in SUMMARY_ROWS:
            vals = [R["summary"].get(key) for R in chunk]
            if all(v is None for v in vals):
                continue
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.8)
            c.drawString(rx + 2, y2 - 7.4, _fit(lab.format(du=D["unit"]), doc.R, 6.8, labw - 4))
            for j, v in enumerate(vals):
                c.setFont(doc.B if j == 0 else doc.R, 6.6)
                c.drawRightString(rx + labw + (j + 1) * 64 - 3, y2 - 7.4, _fit(_pdf_safe(v if v is not None else "—"), doc.R, 6.6, 60))
            c.setStrokeColorRGB(*BAND_GREY_RGB); c.setLineWidth(0.3); c.line(rx, y2 - 10.5, rx + rw, y2 - 10.5)
            y2 -= 11.5
        y2 -= 8
        if y2 < doc.bottom() + 60 and start + per < len(routes):
            doc.end_page(); doc.landscape_page([]); y2 = doc.header(None, "Route analysis", None, cont=True); rx, rw = m, doc.cw
    doc.para("Counts side by side; nothing here is divided or ranked. \"—\": not in this file "
             "or none." + (" " + SEARCH_WORDS if any(R["summary"].get("schools_health") is not None for R in routes) else ""),
             rx, y2, rw, 6.6, GREY)
    doc.end_page()


# --------------------------------------------------------------------------- #
#  The summary (16 Nov 2026, step 1c; notes\route-best-summary-mockup-1116,  #
#  John: "Yes, as recommended")                                                #
# --------------------------------------------------------------------------- #
SUM_BLUE = "#2563EB"          # the suggested option's column head (S4)
SUM_GREY = "#94A3B8"          # the route in use's bars and every collision bar (the rule's "grey")
SUM_INK = "#64748B"           # an option's bar (the rule's "ink"): the file's own grey ink, export.GREY
SUM_PICK = "#F5F8FE"          # the suggested option's column, a light tint under its cells
SUM_OK = "#047857"            # a difference on the better side: a dot and its words
SUM_WARN = "#B45309"          # on the worse side: a diamond and its words
SUM_LINE = "#E2E8F0"
SUM_SOFT = "#F8FAFC"
SUM_TITLE = "Route analysis · Summary"
SUM_DECIDES = "The planner decides; nothing here changes the plan."
#: 25 Nov 2026: the "(*)" went with the starred figures of "The figures" table (the rows say "Not counted yet")
SUM_SHOWN = "Cycle routes and community places are shown, not counted: not fetched along every option yet."
#: 24 Nov 2026 (the Routes page rethink, Q7; John: "Yes, as recommended"): step 3 in the card 4 / 5 words ("A trade-off"
#: is "Planner to decide"; nothing says ahead, behind or trade); step 2 names the measures (the "People" heading went)
SUM_STEPS = [("1 · Rule out", "An option that adds a lorry limit below this lorry, or crosses a road closed on the day."),
             ("2 · Compare", "Each option left against the route in use: collisions, cycle routes, community, time, busy "
                             "hours, carbon."),
             ("3 · Answer", "Clearly better on one measure and worse on none: suggested. Mixed: the planner decides. "
                            "Otherwise: keep.")]
#: 24 Nov 2026 (Q9): a collision with a goods vehicle over 3.5 t is "involving an HGV" (CLOCS Standard v5, 2.7)
SUM_HGV = "Involving an HGV"
SUM_READ = [("Collisions", "Injury collisions the police recorded on the road. Counts only: never a percentage or a "
                           "rate. A count beside a road is not a risk."),
            ("Cycle, places", "What a lorry passes on a round trip, with each option's change against the route in use."),
            ("Time, carbon", "One round trip, a planning figure. A small gap reads \"same\"."),
            ("Sections A to F", "The counts behind this page, unchanged. Section C keeps its own rules.")]
#: why the summary's collision count can differ from section C's (John, 17 Nov 2026: "Yes, add it"): the rule counts the
#: line in use / an option on the chosen lorry's own two lines as they are now (route_best.count_on_lines); section C a
#: column's option number over every lorry type's lines, both legs, by the distances stored at the last fetch
#: (collisions.counts_for)
SUM_COUNT_NOTE = ("Collisions here are counted on this lorry's own lines, out and back. Section C counts each option's "
                  "lines for every lorry type, as at the last fetch.")


def _n(x, d=1):
    if x is None:
        return "–"
    x = round(float(x), d)
    return f"{int(x):,}" if x == int(x) else f"{x:,.{d}f}"


def _pct_words(p, less=False):
    """An option's change against the route in use (cycle routes, left turns and places only: never collisions)."""
    if p is None:
        return ""
    if p == 0:
        return "the same"
    return f"{abs(p)} % {('less' if less else 'fewer') if p < 0 else 'more'}"


def _sum_pick(B):
    return next((c["label"] for c in B["cols"] if c.get("chosen")), None)


# --------------------------------------------------------------------------- #
#  The schedule (25 Nov 2026, the Routes page rethink, Q11 Direction 1; John:  #
#  "Yes, as recommended"): the six panels and "The figures" are ONE table, a   #
#  row a measure, a column for the route in use and for each option, every    #
#  figure with its bar from zero on the row's own scale. The rows, their marks #
#  and their words are the rule's (route_best.option_rows, an option's         #
#  "rows"): the page prints them and works nothing out. Two rows are the       #
#  page's own, figures only and never marked: the other places shown near and  #
#  the length, which the old table carried and the rule does not compare.      #
# --------------------------------------------------------------------------- #
SUM_SCHED = "The options, measure by measure"
SUM_SCALE = "Every bar starts at zero; each row has its own scale."
SUM_HEAD = "A round trip"
SUM_DIFF = "Against the route in use"
SUM_HOW = "How the answer was reached"
SUM_SHOWN_ROW = "other places near (shown)"
SUM_KM_ROW = "Length, km a round trip"
SUM_OUT = "ruled out"
SUM_NO_BUSY = "No busy-hour times are worked out for this route."
SUM_STEP, SUM_PAD = 7.8, 4.4      # a schedule row: a line of 7.8 pt, 4.4 pt of air
#: the order of the rows (the rule's keys; "shown" and "km" are the page's own)
SUM_ORDER = ("collisions", "goods", "left_turns", "cycle_meets", "cycle_beside_km", "places", "shown", "round_trip",
             "trips", "busy_08:00", "busy_17:00", "busy", "carbon", "km", "limits")
#: a key's figure in an option's counts (a ruled-out option has no rows: its figures are read from its counts, so the
#: column keeps them as the old page did; pinned equal to the rule's own figures for every option it writes rows for)
SUM_COUNT_OF = {"collisions": ("collisions", 0), "goods": ("goods", 0), "left_turns": ("left_turns", 0),
                "cycle_meets": ("cycle_meets", 0), "cycle_beside_km": ("cycle_beside_km", 2), "places": ("places", 0),
                "round_trip": ("cycle_min", 1), "trips": ("trips", 0), "busy_08:00": ("busy_min", 1),
                "busy_17:00": ("busy_min", 1), "carbon": ("co2_kg", 1), "km": ("km", 1), "shown": ("shown", 0)}
#: the rule's labels, for a page where it wrote no rows (every option ruled out, or none stored); pinned equal to
#: route_best.option_rows' own labels
SUM_LABELS = {"left_turns": "Left-hand turns", "cycle_meets": "Cycle routes met",
              "cycle_beside_km": "km beside a cycle route",
              "places": "Community: schools, hospitals, health centres", "round_trip": "Round trip, min",
              "trips": "Trips a lorry fits a day", "busy_08:00": "Setting off at 08:00",
              "busy_17:00": "Setting off at 17:00", "carbon": "Carbon, kg CO₂e a trip"}


def _sum_safe(t):
    """Words for the schedule: the rule's "Config → Map and bulletin" keeps its arrow where the file's font has one
    (Inter; Helvetica, the fallback, has none and reads "to", as _pdf_safe gives)."""
    import brand_pdf
    t = str(t if t is not None else "")
    return _pdf_safe(t) if brand_pdf.fonts().get("fallback") else t


def _sum_count(col, key):
    """A column's figure for a row key, from its counts (None where it has none)."""
    if key not in SUM_COUNT_OF:
        return None
    k, _d = SUM_COUNT_OF[key]
    v = (col.get("counts") or {}).get(k)
    if key.startswith("busy_"):
        return (v or {}).get(key[5:]) if isinstance(v, dict) else None
    if key == "shown":
        return sum(v.values()) if isinstance(v, dict) else None
    return v


def _sum_text(v, key):
    return "" if v is None else _n(v, SUM_COUNT_OF.get(key, (None, 1))[1])


def schedule(B):
    """The schedule as data: {"cols", "rows", "diff_col"}. A column: {label, in_use, chosen, out (ruled out)}. A row:
    {key, label, sub, span (words across every figure cell, or None), cells: one a column {text, v, bar ("grey",
    "ink", "hatch" or None), mark, words, none}}. `diff_col`: the difference has its own last column (exactly one
    option, not ruled out, as card 5 draws it); otherwise it sits under each option's figure."""
    import route_best
    cols = [dict(label=c["label"], in_use=bool(c["in_use"]), chosen=bool(c.get("chosen")),
                 out=bool(c.get("ruled_out")), src=c) for c in B["cols"]]
    opts = [c for c in cols if not c["in_use"]]
    live = [c for c in opts if not c["out"]]
    hist = B.get("history") == "current"
    by = {id(c): {r["key"]: r for r in (c["src"].get("rows") or [])} for c in live}
    keys = {k for c in live for k in by[id(c)]}
    hours = {k for k in keys if k.startswith("busy_")}
    if hours:
        keys.discard("busy")       # an option with no hour held says so in its own cells of the hour rows
    has_rows = bool(keys)
    if not has_rows:
        # the rule writes no rows (every option ruled out, or none stored): the route in use's figures, and a ruled-out
        # option's, under the rule's own labels; collisions as counts or the rule's own words why not
        keys = {"left_turns", "places", "round_trip", "trips", "carbon"}
        keys |= {"collisions", "goods"} if hist else {"collisions"}
        if B.get("cycle_held"):
            keys |= {"cycle_meets", "cycle_beside_km"}
        hours = {f"busy_{h}" for h in RA.BUSY_HOURS if any(_sum_count(c["src"], f"busy_{h}") is not None for c in cols)}
        keys |= hours or {"busy"}
    if all(isinstance((c["src"].get("counts") or {}).get("shown"), dict) for c in cols):
        keys.add("shown")
    keys.add("km")
    rows = []
    for key in (k for k in SUM_ORDER if k in keys):
        first = next((by[id(c)][key] for c in live if key in by[id(c)] and by[id(c)][key].get("none") is None), None)
        anyrow = first or next((by[id(c)][key] for c in live if key in by[id(c)]), None)
        if anyrow:
            label, sub = anyrow["label"], bool(anyrow.get("sub"))
        elif key == "collisions":
            label, sub = (f"{route_best.ROW_COLLISIONS}, {B['period']}" if B.get("period") else route_best.ROW_COLLISIONS), False
        elif key == "goods":
            label, sub = route_best.HGV_WORDS, True
        elif key == "shown":
            label, sub = SUM_SHOWN_ROW, True
        elif key == "km":
            label, sub = SUM_KM_ROW, False
        elif key == "busy":
            label, sub = "Busy hours", False
        else:
            label, sub = SUM_LABELS.get(key, key), False
        cells = []
        for c in cols:
            cell = {"text": "", "v": None, "bar": None, "mark": None, "words": "", "none": None}
            if c["in_use"]:
                if first is not None:
                    cell.update(text=first["in_use_text"], v=first["in_use"], bar="grey")
                elif key in ("shown", "km") or (not has_rows and key in SUM_COUNT_OF
                                                and (hist or key not in ("collisions", "goods"))):
                    v = _sum_count(c["src"], key)
                    cell.update(text=_sum_text(v, key), v=v, bar="grey" if v is not None else None)
            elif c["out"] or not by[id(c)]:
                # a ruled-out option (hatched), or one left in with no rows: its figures from its counts, never marked
                if key in SUM_COUNT_OF and (hist or key not in ("collisions", "goods")):
                    v = _sum_count(c["src"], key)
                    kind = "hatch" if c["out"] else "grey" if key in ("collisions", "goods") else "ink"
                    cell.update(text=_sum_text(v, key), v=v, bar=kind if v is not None else None)
            else:
                r = by[id(c)].get(key)
                if r is None and key.startswith("busy_"):
                    r = by[id(c)].get("busy")
                if r is None and key in ("shown", "km"):
                    v = _sum_count(c["src"], key)
                    cell.update(text=_sum_text(v, key), v=v, bar="ink" if v is not None else None)
                elif r is not None and r.get("none") is not None:
                    cell["none"] = r["none"]
                elif r is not None and r.get("key") == key:
                    cell.update(text=r["option_text"], v=r["option"], bar=r.get("bars"), mark=r["mark"],
                                words=r.get("words") or "")
            cells.append(cell)
        # a measure no column has a figure for: said once across the figure cells where every option says the same
        span = None
        if not has_rows and key == "busy":
            span = SUM_NO_BUSY
        elif not has_rows and key == "collisions" and not hist:
            span = (route_best.ROW_STALE if B.get("history") == "out_of_date" else route_best.NO_HISTORY_WORDS)
        else:
            nones = {cells[j]["none"] for j, c in enumerate(cols) if not c["in_use"]}
            if (len(nones) == 1 and None not in nones and not any(c["out"] for c in opts)
                    and all(cl["v"] is None for cl in cells)):
                span = nones.pop()
        rows.append({"key": key, "label": label, "sub": sub, "span": span, "cells": cells})
    return {"cols": [{k: c[k] for k in ("label", "in_use", "chosen", "out")} for c in cols], "rows": rows,
            "diff_col": len(opts) == 1 and len(live) == 1}


def _sum_wrap(t, font, size, width):
    from reportlab.lib.utils import simpleSplit
    return simpleSplit(_sum_safe(t), font, size, width)


def _sum_shape(c, x, y, mark):
    """The status shape before a difference's words: a dot for the mark "ok", a diamond for "warn"."""
    if mark == "ok":
        c.setFillColorRGB(*_rgb(SUM_OK)); c.circle(x + 2.4, y + 2.2, 2.2, stroke=0, fill=1)
    elif mark == "warn":
        c.setFillColorRGB(*_rgb(SUM_WARN))
        p = c.beginPath()
        if p is None:              # the measuring pass draws nothing (_NoCanvas)
            return
        p.moveTo(x + 2.4, y + 4.8); p.lineTo(x + 4.8, y + 2.2); p.lineTo(x + 2.4, y - 0.4)
        p.lineTo(x, y + 2.2); p.close(); c.drawPath(p, stroke=0, fill=1)


def _sum_words(doc, x, y, mark, words, size=6.4):
    """A difference: the shape and the rule's words (green for "ok", amber for "warn"), plain words otherwise."""
    c = doc.c
    if not words:
        return
    if mark in ("ok", "warn"):
        _sum_shape(c, x, y, mark)
        c.setFillColorRGB(*_rgb(SUM_OK if mark == "ok" else SUM_WARN)); c.setFont(doc.R, size)
        c.drawString(x + 7.5, y, _pdf_safe(words))
    else:
        c.setFillColorRGB(*(NAVY_RGB if mark == "plain" else GREY)); c.setFont(doc.R, size)
        c.drawString(x, y, _pdf_safe(words))


def _sum_bar(c, x, y, w, kind):
    if w <= 0:
        return
    if kind == "hatch":
        c.setFillColorRGB(1, 1, 1); c.setStrokeColorRGB(*_rgb("#CBD5E1")); c.setLineWidth(0.4)
        c.rect(x, y, w, 5, stroke=1, fill=1)
        c.setStrokeColorRGB(*_rgb("#CBD5E1"))
        s = 0
        while s < w:
            c.line(x + s, y, x + min(s + 3, w), y + 5)
            s += 2.6
    else:
        c.setFillColorRGB(*_rgb(SUM_INK if kind == "ink" else SUM_GREY))
        c.roundRect(x, y, w, 5, 1.2, stroke=0, fill=1)


def _sum_schedule(doc, x, y, w, B):
    """Draws the schedule; returns the y below it."""
    c = doc.c
    S = schedule(B)
    cols, rows = S["cols"], S["rows"]
    nc = len(cols)
    lab_w = 168
    diff_w = 112 if S["diff_col"] else 0
    cw = (w - lab_w - diff_w) / max(1, nc)
    num_w = 30
    bar_max = min(170.0, cw - num_w - 10)
    fs = 7.0 if nc <= 4 else 6.4
    pk = _sum_pick(B)
    out_any = any(col["out"] for col in cols)
    hh = 21 if out_any else 13
    # the head: the band, the suggested option's column headed in blue (as before)
    c.setFillColorRGB(*BAND); c.rect(x, y - hh, w, hh, stroke=0, fill=1)
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, fs); c.drawString(x + 2, y - 9, SUM_HEAD)
    for j, col in enumerate(cols):
        cx = x + lab_w + cw * j
        if col["chosen"]:
            c.setFillColorRGB(*_rgb("#DBEAFE")); c.rect(cx, y - hh, cw, hh, stroke=0, fill=1)
        c.setFillColorRGB(*(_rgb(SUM_BLUE) if col["chosen"] else NAVY_RGB)); c.setFont(doc.B, fs)
        c.drawString(cx + 4, y - 9, _pdf_safe(_fit(col["label"], doc.B, fs, cw - 6)))
        if col["out"]:
            c.setFillColorRGB(*GREY); c.setFont(doc.R, 6); c.drawString(cx + 4, y - 17.5, SUM_OUT)
    if diff_w:
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, fs); c.drawString(x + w - diff_w + 4, y - 9, SUM_DIFF)
    y -= hh
    under = not S["diff_col"]
    for r in rows:
        # the row's height: a line, a second for words under a figure, more for words that wrap in a cell
        n_lines = 1
        if under and any(cl["words"] for cl in r["cells"]):
            n_lines = 2
        if r["span"] is None:
            for cl in r["cells"]:
                if cl["none"]:
                    n_lines = max(n_lines, len(_sum_wrap(cl["none"], doc.R, 6.2, cw - 8)))
        rh = SUM_PAD + n_lines * SUM_STEP
        if r["span"] is not None:
            rh = SUM_PAD + len(_sum_wrap(r["span"], doc.R, 6.4, w - lab_w - 8)) * SUM_STEP
        # the label
        c.setFillColorRGB(*(GREY if r["sub"] else NAVY_RGB)); c.setFont(doc.R, fs)
        lx = x + (12 if r["sub"] else 2)
        c.drawString(lx, y - 8.6, _pdf_safe(_fit(r["label"], doc.R, fs, lab_w - (lx - x) - 4)))
        if pk and r["span"] is None:
            j = next(j for j, col in enumerate(cols) if col["chosen"])
            c.setFillColorRGB(*_rgb(SUM_PICK)); c.rect(x + lab_w + cw * j, y - rh, cw, rh, stroke=0, fill=1)
        if r["span"] is not None:
            yy = y
            for ln in _sum_wrap(r["span"], doc.R, 6.4, w - lab_w - 8):
                c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.4); c.drawString(x + lab_w + 4, yy - 8.6, ln); yy -= SUM_STEP
        else:
            vals = [cl["v"] for cl in r["cells"] if cl["v"] is not None and cl["bar"]]
            mx = max([float(v) for v in vals] or [0]) or 1.0
            for j, (col, cl) in enumerate(zip(cols, r["cells"])):
                cx = x + lab_w + cw * j
                if cl["none"]:
                    yy = y
                    for ln in _sum_wrap(cl["none"], doc.R, 6.2, cw - 8):
                        c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.2); c.drawString(cx + 4, yy - 8.6, ln); yy -= SUM_STEP
                    continue
                if cl["v"] is None:
                    c.setFillColorRGB(*GREY); c.setFont(doc.R, fs)
                    c.drawRightString(cx + num_w, y - 8.6, _pdf_safe(cl["text"] or "–"))
                    continue
                c.setFillColorRGB(*(GREY if col["out"] else NAVY_RGB))
                c.setFont(doc.B if col["chosen"] else doc.R, fs)
                c.drawRightString(cx + num_w, y - 8.6, _pdf_safe(cl["text"]))
                bw = max(0.0, float(cl["v"]) / mx * bar_max)
                if bw > 0:
                    _sum_bar(c, cx + num_w + 4, y - 9.2, max(bw, 1.0), cl["bar"])
                if under and cl["words"]:
                    _sum_words(doc, cx + num_w + 4, y - 8.6 - SUM_STEP, cl["mark"], cl["words"], 6.2)
            if S["diff_col"]:
                cl = next(cl for col, cl in zip(cols, r["cells"]) if not col["in_use"])
                if not cl["none"]:
                    _sum_words(doc, x + w - diff_w + 4, y - 8.6, cl["mark"], cl["words"])
        c.setStrokeColorRGB(*_rgb(SUM_LINE)); c.setLineWidth(0.4); c.line(x, y - rh + 0.5, x + w, y - rh + 0.5)
        if r["span"] is None:      # the columns' thin rules, so a figure reads with its column (none across a span)
            for j in range(1, nc + (1 if diff_w else 0)):
                c.line(x + lab_w + cw * j, y, x + lab_w + cw * j, y - rh + 0.5)
        y -= rh
    return y


def _sum_how_line():
    """"How the answer was reached" as one line in SUM_STEPS' own words: "1 Rule out an option … → 2 Compare each … →
    3 Clearly better …" (card 5)."""
    parts = []
    for ttl, t in SUM_STEPS:
        n, name = ttl.split(" · ")
        if name == "Answer":
            parts.append(f"{n} {t}")
        else:
            parts.append(f"{n} {name} {t[0].lower()}{t[1:]}".rstrip("."))
    return " → ".join(parts)


#: 17 Nov 2026 (the live check, finding 1; John: "Yes, as recommended"): no reason may push the page's content off the
#: sheet. On live R011's reason was 443 words and the page drew ten lines of text below its foot (lowest text 15 pt
#: under the page's edge; 35 pt above it on the other 49). The rule now says an added limit road by road, so a reason is
#: a line or two; as a second guard every reason on this page (the answer's why, a "held back" line, a "ruled out"
#: line) is cut at SUM_REASON_LINES lines, its last line ending SUM_CUT. Every stretch is listed in section A.
SUM_REASON_LINES = 4
SUM_CUT = "… section A has the rest"


def cut_lines(lines, font, size, width, most=SUM_REASON_LINES, tail=SUM_CUT):
    """Wrapped lines cut at `most`: the first `most`, the last shortened word by word until `tail` fits after it."""
    if len(lines) <= most:
        return list(lines)
    keep = list(lines[:most])
    words = keep[-1].split(" ")
    end = " " + _pdf_safe(tail)
    while len(words) > 1 and _w(" ".join(words) + end, font, size) > width:
        words.pop()
    keep[-1] = " ".join(words).rstrip(" ,;:") + end
    return keep


def in_use_limit_words(L, diversion):
    """The card's own sentence for a limit the line in use meets (frontend boInUseLimit, word for word, so the two agree):
    "The diversion in use meets a 7.5 t limit below this lorry." from `short`; the long words where no short is held."""
    leg = " (loaded leg)" if L.get("legs") == "loaded" else " (return leg)" if L.get("legs") == "return" else ""
    what = f"The {'diversion' if diversion else 'route'} in use meets a"
    if L.get("short"):
        return f"{what} {L['short']} below this lorry{leg}."
    return f"{what} limit below this lorry: {L.get('words') or ''}{leg}."


def page_summary(doc, R, i, n, pages):
    """The summary page for one route (S1): the answer and the rule's one sentence on top, the six panels, the figures,
    how the answer was reached and how to read the page. One page; all of them first in the file (S2)."""
    D, c = doc.D, doc.c
    B = R.get("best") or {"error": RA.SUMMARY_UNAVAILABLE}
    foot = ["Made from what Wayscope holds; nothing was fetched for this file."]
    if n > 1:
        st = pages.get((R["id"], "_start"))
        foot.append(f"Summary {i} of {n}." + (f" {R['id']}'s sections start on page {st}." if st else ""))
    doc.landscape_page(foot)
    m, W, H = doc.m, doc.W, doc.H
    y = H - m
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 18); c.drawString(m, y - 17, SUM_TITLE)
    c.setFont(doc.B, 9); c.drawRightString(W - m, y - 9, _pdf_safe(D["tenant"]))
    yy = y - 20
    if D.get("demo_notice"):
        c.setFillColorRGB(*DEMO_FG_RGB); c.setFont(doc.B, 8); c.drawRightString(W - m, yy, _pdf_safe("DEMO · " + D["demo_notice"]).upper())
        yy -= 11
    c.setFillColorRGB(*GREY); c.setFont(doc.R, 8); c.drawRightString(W - m, yy, f"Made {D['made']}")
    y -= 24
    y = doc.para(f"{R['id']} · {R['origin']} → {R['dest']}", m, y, doc.cw * 0.7, 10.5, NAVY_RGB, bold=True) - 1
    if B.get("error"):
        y = doc.para(B["error"], m, y - 6, doc.cw * 0.7, 9, NAVY_RGB)
        doc.end_page()
        return
    sub = f"For the {B['lorry_text']}, " + ("the lorry most of its approved loads use" if B.get("lorry_basis") ==
                                             "approved loads" else "as no load is approved on it yet")
    if B["others_text"]:
        sub += ". Not for: " + ", ".join(B["others_text"])
    if B.get("in_use_words"):
        sub += f". Route in use on {D['made']}: {B['in_use_words']}"
    sub += "."
    if D.get("lorry") and B.get("lorry") and D["lorry"] != B["lorry"]:
        sub += f" Sections A to F are drawn for the {D.get('lorry_text') or D['lorry']}."
    y = doc.para(sub, m, y, doc.cw * 0.72, 7.2, GREY) - 5
    for L in B.get("in_use_limits") or []:
        y = doc.para(in_use_limit_words(L, B.get("in_use_diversion")), m, y + 3, doc.cw * 0.72, 7.2, GREY) - 5
    # the answer and the rule's own sentence (S4: one navy box for every answer)
    head = B["answer"] + (f": {B['option']}" if B.get("option") else "")
    hw_ = _w(head, doc.B, 13) + 16
    why = cut_lines(_wrap(_pdf_safe(B.get("why") or ""), doc.R, 8, doc.cw - hw_ - 18) or [""], doc.R, 8,
                    doc.cw - hw_ - 18)
    bh = max(24, 10 + len(why) * 10)
    c.setStrokeColorRGB(*_rgb(SUM_LINE)); c.setLineWidth(0.6); c.roundRect(m, y - bh, doc.cw, bh, 3, stroke=1, fill=0)
    c.setFillColorRGB(*NAVY_RGB); c.rect(m, y - bh, 3.2, bh, stroke=0, fill=1)
    c.setFont(doc.B, 13); c.drawString(m + 11, y - bh / 2 - 4.5, _pdf_safe(head))
    ty = y - (bh - len(why) * 10) / 2
    for ln in why:
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 8); c.drawString(m + 11 + hw_, ty - 8, ln); ty -= 10
    y -= bh + 2
    y = doc.para(SUM_DECIDES, m, y, doc.cw, 6.6, GREY) - 1
    notes = []
    if B.get("held_back") and B["held_back"] not in (B.get("why") or ""):
        notes.append("Held back: " + B["held_back"])
    if not B["counted"]:
        notes.append(SUM_SHOWN)
    outs = [k for k in B["cols"] if k["ruled_out"]]
    if not (outs and len(outs) == len(B["cols"]) - 1 and (B.get("why") or "").startswith("Every other option is ruled out")):
        notes += [f"{k['label']} ruled out: {k['ruled_out'][0]}." for k in outs]
    # the notes take only the room the rest of the page leaves (measured first, drawn on nothing): a note that would
    # not fit is cut shorter, and one with no line left is not drawn
    below = _sum_lower_h(doc, B)
    for t in notes:
        fit = int((y - 1 - below - doc.bottom()) // 8.8)
        if fit < 1:
            break
        for ln in cut_lines(_wrap(_pdf_safe(t), doc.R, 6.6, doc.cw), doc.R, 6.6, doc.cw, most=min(SUM_REASON_LINES, fit)):
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.6); c.drawString(m, y - 6.6, ln)
            y -= 8.8
        y -= 1
    _sum_lower(doc, y, B)
    doc.end_page()


class _NoCanvas:
    """A canvas that draws nothing: the summary page's lower half is laid out on it once to learn its height."""

    def __getattr__(self, name):
        return lambda *a, **k: None


def _sum_lower_h(doc, B):
    """The height of the summary page's lower half (the panels, the figures, the steps, how to read the page)."""
    real, doc.c = doc.c, _NoCanvas()
    try:
        return 10000 - _sum_lower(doc, 10000, B)
    finally:
        doc.c = real


def _sum_lower(doc, y, B):
    """The summary page from the schedule down; returns the lowest y drawn."""
    c, m = doc.c, doc.m
    y -= 4
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9); c.drawString(m, y - 9, SUM_SCHED)
    kx = m + _w(SUM_SCHED, doc.B, 9) + 10
    c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.2); c.drawString(kx, y - 9, SUM_SCALE)
    if _sum_pick(B):
        kx += _w(SUM_SCALE, doc.R, 6.2) + 10
        c.setFillColorRGB(*_rgb("#DBEAFE")); c.rect(kx, y - 10, 10, 6.4, stroke=0, fill=1)
        c.setFillColorRGB(*GREY); c.drawString(kx + 13, y - 9, "The suggested option")
    y = _sum_schedule(doc, m, y - 14, doc.cw, B) - 6
    # how the answer was reached: one line in the steps' own words (card 5)
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9); c.drawString(m, y - 9, SUM_HOW); y -= 12
    from reportlab.lib.utils import simpleSplit
    for ln in simpleSplit(_sum_safe(_sum_how_line()), doc.R, 6.6, doc.cw):
        c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.R, 6.6); c.drawString(m, y - 6.6, ln); y -= 8.8
    y -= 5
    c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 9); c.drawString(m, y - 9, "How to read this page"); y -= 13
    half = doc.cw / 2
    for j in range(0, len(SUM_READ), 2):
        low = y
        for k, (lab, t) in enumerate(SUM_READ[j:j + 2]):
            x0 = m + k * half
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 6.6); c.drawString(x0, y - 6.6, lab)
            low = min(low, doc.para(t, x0 + 62, y, half - 74, 6.4, NAVY_RGB))
        y = low - 2
    y = doc.para(SUM_COUNT_NOTE, m + 62, y, doc.cw - 74, 6.4, NAVY_RGB) - 2
    return y


SUMMARY_SHEET_HEAD = ["Route", "Option", "Answer", "Why", "Ruled out by", "Collisions on the road",
                      SUM_HGV, "Left-hand turns", "Left-hand turns, % against in use", "Cycle routes met",
                      "Cycle routes met, %", "km beside a cycle route", "km beside, %",
                      "Schools, hospitals, health centres (250 m)", "Those places, %", "Other places near (shown)",
                      "Round trip with loading, min", "Trips a day", "Setting off 08:00, min", "Setting off 17:00, min",
                      "kg CO2e a round trip", "km a round trip", "Cycle and places counted", SUM_DIFF]


def diff_words(col):
    """An option's differences in the rule's own words, measure by measure ("Left-hand turns: 13 more; …"), for the
    Summary sheet's last column (25 Nov 2026, Q11): from its schedule rows, so the sheet and the page say the same;
    empty for the route in use and a ruled-out option (which has no rows)."""
    return "; ".join(f"{r['label']}: {r['words']}" for r in (col.get("rows") or []) if r.get("words")
                     and r.get("none") is None)


def summary_rows(R):
    """One route's rows on the Summary sheet: the route in use, then each option (card 7)."""
    B = R.get("best") or {"error": RA.SUMMARY_UNAVAILABLE}
    if B.get("error"):
        return [[R["id"], None, None, B["error"]] + [None] * (len(SUMMARY_SHEET_HEAD) - 4)]
    hist = B["history"] == "current"
    cnt = "yes" if B["counted"] else "no (shown only)"
    out = []
    for k in B["cols"]:
        c, p = k["counts"], k["pct"] or {}
        shown = c.get("shown")
        bm = c.get("busy_min") or {}
        out.append([R["id"],
                    ("In use: " + (B.get("in_use_words") or "")).strip() if k["in_use"]
                    else k["label"] + (" (suggested)" if k.get("chosen") else ""),
                    B["answer"] + (f": {B['option']}" if B.get("option") else ""),
                    (B.get("why") or "") if k["in_use"] else "", "; ".join(k["ruled_out"] or []),
                    c.get("collisions") if hist else "not compared", c.get("goods") if hist else "not compared",
                    c.get("left_turns"), p.get("left_turns"), c.get("cycle_meets"), p.get("cycle_meets"),
                    c.get("cycle_beside_km"), p.get("cycle_beside_km"), c.get("places"), p.get("places"),
                    sum(shown.values()) if isinstance(shown, dict) else None, c.get("cycle_min"), c.get("trips"),
                    bm.get("08:00"), bm.get("17:00"), c.get("co2_kg"), c.get("km"), cnt, diff_words(k) or None])
    return out


def _w(text, font, size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(_pdf_safe(text), font, size)


def page_assessor(doc, R):
    D = doc.D
    c = doc.c
    doc.portrait_page([])
    y = doc.header(None, "For the route risk assessment", R)
    m, cw = doc.m, doc.cw
    y = doc.para("Questions drawn from CLOCS Standard v5 clauses 4.1a, 4.3a, 5.1a, 5.2c, 5.5a and 5.6a; not a CLOCS form. "
                 "Evidence for the assessor, not a verdict on the route. The boxes are the assessor's.", m, y, cw, 7.4) - 4
    line_f = diversions_line(R["diversions"]) if "diversions" in R else None
    for i, (q, secs, clauses, b1, b2) in enumerate(ASSESSOR, 1):
        where = []
        for s in secs:
            if s == "first":
                where.append("the first page")
            elif s in D["sections"]:
                where.append(f"{RA.LETTER[s]} · {RA.TITLE[s]}")
            else:
                where.append(f"{RA.TITLE[s]}: section not in this file")
        ev = ("Evidence: " + "; ".join(where) if where else "Evidence: the project's own records") + f" · {clauses}"
        if s_has(secs, "diversions") and line_f:
            ev += f" · {line_f}"
        ql = _wrap(_pdf_safe(f"{i}. {q}"), doc.B, 7.6, cw)
        el = _wrap(_pdf_safe(ev), doc.R, 6.6, cw)
        need = len(ql) * 9 + len(el) * 8 + 36
        if y - need < doc.bottom():
            doc.end_page(); doc.portrait_page([]); y = doc.header(None, "For the route risk assessment", R, cont=True)
        for ln in ql:
            c.setFillColorRGB(*NAVY_RGB); c.setFont(doc.B, 7.6); c.drawString(m, y - 7.6, ln); y -= 9
        for ln in el:
            c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.6); c.drawString(m, y - 6.6, ln); y -= 8
        bw2 = (cw - 8) / 2
        for k, lab in enumerate((b1, b2)):
            bx2 = m + k * (bw2 + 8)
            c.saveState(); c.setStrokeColorRGB(0.63, 0.63, 0.67); c.setLineWidth(0.6); c.setDash(2, 2)
            c.rect(bx2, y - 30, bw2, 28, stroke=1, fill=0); c.restoreState()
            c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.2); c.drawString(bx2 + 3, y - 9, lab)
        y -= 36
    if y - 34 < doc.bottom():
        doc.end_page(); doc.portrait_page([]); y = doc.header(None, "For the route risk assessment", R, cont=True)
    y -= 6
    for k, lab in enumerate(("Assessed by", "Role", "Date", "Review before phase")):
        bx2 = m + k * (cw / 4)
        c.setStrokeColorRGB(0.63, 0.63, 0.67); c.setLineWidth(0.6); c.line(bx2, y - 18, bx2 + cw / 4 - 10, y - 18)
        c.setFillColorRGB(*GREY); c.setFont(doc.R, 6.4); c.drawString(bx2, y - 26, lab)
    doc.end_page()


def s_has(secs, k):
    return k in secs


def page_no_diversion(doc, R):
    """F with nothing to draw: one line on a short page would waste paper — so it goes on the assessor page and here
    only when the assessor page is not in the file: a small page with the line."""
    doc.landscape_page([])
    y = doc.header("F", "Diversions", R)
    doc.para(diversions_line(R["diversions"]), doc.m, y, doc.cw, 8.4)
    doc.end_page()


# --------------------------------------------------------------------------- #
#  The file                                                                    #
# --------------------------------------------------------------------------- #
def _render(D, sizing, pages_in):
    doc = Doc(D, sizing=sizing)
    starts = {}
    n = len(D["routes"])
    for i, R in enumerate(D["routes"], 1):         # the summaries first, then the contents page (S2, John 16 Nov 2026)
        starts[(R["id"], "summary")] = doc.page
        page_summary(doc, R, i, n, pages_in)
    page_first(doc, pages_in)
    for R in D["routes"]:
        starts[(R["id"], "_start")] = doc.page
        for k in D["sections"]:
            if k == "assessor":
                continue
            starts[(R["id"], k)] = doc.page
            if k == "limits":
                page_limits(doc, R)
            elif k == "community":
                page_community(doc, R)
            elif k == "collisions":
                ev = R["evidence"]
                ev["title"] = "C · Collisions"
                skip = {"assessor"} | ({"cycle"} if "cycle" in D["sections"] else set()) \
                    | ({"cycle_by_hour"} if "hours" in D["sections"] else set())
                if sizing:
                    X._SIZING.on = True
                try:
                    # 11 Nov 2026 (CLOCS card B-F7): "Made", as every other page of the file says, not "Issued"
                    doc.page = X.build_collision_evidence_pdf(dict(ev, head_word="Made"), canvas=doc.c,
                                                              page_start=doc.page, skip=skip)
                finally:
                    if sizing:
                        X._SIZING.on = False
                doc.basemap = doc.basemap or bool(ev.get("basemap"))
            elif k == "cycle":
                page_cycle(doc, R)
            elif k == "hours":
                page_hours(doc, R)
            elif k == "diversions":
                if not page_diversions(doc, R):
                    if "assessor" in D["sections"]:
                        starts.pop((R["id"], k), None)       # said on the assessor page instead
                    else:
                        page_no_diversion(doc, R)
        if "assessor" in D["sections"]:
            starts[(R["id"], "assessor")] = doc.page
            page_assessor(doc, R)
    doc.c.save()
    return doc, starts


def build_pdf(D):
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed")
    _doc, starts = _render(D, True, {})          # the sizing pass: where each section starts (no basemap)
    doc, _ = _render(D, False, starts)
    D["pages"] = doc.page - 1
    D["basemap"] = doc.basemap
    return doc.buf.getvalue()


# --------------------------------------------------------------------------- #
#  The workbook                                                                #
# --------------------------------------------------------------------------- #
def build_xlsx(D):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    head, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=X.NAVY)
    du = D["unit"]

    def sheet(name, titles, rows, widths=None):
        ws = wb.create_sheet(name[:31])
        for j, t in enumerate(titles, 1):
            cell = ws.cell(row=1, column=j, value=t)
            cell.font, cell.fill = head, fill
            ws.column_dimensions[get_column_letter(j)].width = (widths or {}).get(j, max(10, min(46, len(str(t)) + 4)))
        for i, r in enumerate(rows, 2):
            for j, v in enumerate(r, 1):
                ws.cell(row=i, column=j, value=v)
        ws.freeze_panes = "B2"
        return ws

    # the Summary sheet FIRST (16 Nov 2026, step 1c; card 7 of notes\route-best-summary-mockup-1116): a row for the route
    # in use and a row an option, by the best-option rule; collisions as counts, never a percentage
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = (f"Summary · each route's options against the route in use, by fixed rules. The planner decides. "
                f"Collisions are counts, never a percentage. Made {D['made']}.")
    ws["A1"].font = Font(bold=True)
    if D.get("demo_notice"):
        ws["A2"] = "DEMO · " + D["demo_notice"]
        ws["A2"].font = Font(bold=True, color=X.DEMO_FG_HEX)
    ws["A3"] = SUM_COUNT_NOTE
    for j, t in enumerate(SUMMARY_SHEET_HEAD, 1):
        cell = ws.cell(row=4, column=j, value=t)
        cell.font, cell.fill = head, fill
        ws.column_dimensions[get_column_letter(j)].width = {1: 10, 2: 22, 3: 22, 4: 60, 5: 40,
                                                                  len(SUMMARY_SHEET_HEAD): 70}.get(j, 14)
    for i, r in enumerate((r for R in D["routes"] for r in summary_rows(R)), 5):
        for j, v in enumerate(r, 1):
            ws.cell(row=i, column=j, value=v)
    ws.freeze_panes = "B5"

    ws = wb.create_sheet("Contents")
    ws["A1"] = f"Route analysis · {D['tenant']} · made {D['made']}"
    ws["A1"].font = Font(bold=True)
    ws["A2"] = (f"{len(D['routes'])} route{'s' if len(D['routes']) > 1 else ''} · drawn for the {D['lorry_text']}"
                if D.get("lorry_text") else "")
    if D.get("demo_notice"):
        ws["A3"] = "DEMO · " + D["demo_notice"]
        ws["A3"].font = Font(bold=True, color=X.DEMO_FG_HEX)
    ws["A5"] = ("Every sheet has the route in its first column, so it can be filtered. Sections A to F: counts only. "
                "The Summary sheet compares by fixed rules. Made from what Wayscope holds.")
    ws.column_dimensions["A"].width = 100
    r0 = 7
    for k in D["sections"]:
        ws.cell(row=r0, column=1, value=(f"{RA.LETTER[k]} · " if RA.LETTER[k] else "") + RA.TITLE[k])
        r0 += 1

    # the routes side by side
    rows = []
    for key, lab in SUMMARY_ROWS:
        vals = [R["summary"].get(key) for R in D["routes"]]
        if all(v is None for v in vals):
            continue
        rows.append([lab.format(du=du)] + [v if v is not None else "—" for v in vals])
    sheet("Routes side by side", ["What"] + [R["id"] for R in D["routes"]], rows, {1: 52})

    if "limits" in D["sections"]:
        rows, crows = [], []
        for R in D["routes"]:
            L = R["limits"]
            for g in L["items"] + L["diversion_items"]:
                rows.append([R["id"], g.get("no"), "Diversion" if g["alt"] else "Main", g["legs_words"], g["headline"],
                             g["road"], g.get("exceptions"), g["verdict_words"],
                             float(g["from_a"]) if g.get("from_a") else None,
                             round(g["off_m"]) if g.get("off_m") is not None else None,
                             "point" if g["point"] else "along the road", L["checked"]])
            Cl = R.get("closures") or {}
            for h in Cl.get("hits") or []:
                crows.append([R["id"], "Planned road closure", h.get("road"), h.get("what"), h.get("from"), h.get("to"),
                              Cl.get("when")])
            if Cl.get("held") and not Cl.get("hits"):
                crows.append([R["id"], "Planned road closure", None, "None on the route", None, None, Cl.get("when")])
            if not Cl.get("held"):
                crows.append([R["id"], "Planned road closure", None, Cl.get("why"), None, None, None])
            for z in R.get("zones") or []:
                crows.append([R["id"], "The scheme's own zone", None, z["name"], None, None, None])
        sheet("A Limits", ["Route", "No", "Line", "Leg", "Limit", "Road", "Signed", "For this lorry", f"From A ({du})",
                           "From the route (m)", "Recorded as", "Checked"], rows, {5: 22, 6: 30, 7: 22})
        sheet("A Closures and zones", ["Route", "Kind", "Road", "What", "From", "To", "Held on"], crows, {4: 60})
    if "community" in D["sections"]:
        rows = []
        for R in D["routes"]:
            C = R["community"]
            for p in C["named"] + C["others"]:
                rows.append([R["id"], p.get("no"), p["kind_label"], p["name"], p["m"],
                             float(p["from_a"]) if p.get("from_a") else None, p["at"][1], p["at"][0], C.get("fetched")])
        sheet("B Community places", ["Route", "No", "Kind", "Name", "From the route (m)", f"From A ({du})", "Latitude",
                                     "Longitude", "Fetched"], rows, {3: 26, 4: 40})
    if "collisions" in D["sections"]:
        _merge_evidence(wb, D)
    if "cycle" in D["sections"]:
        rows = []
        for R in D["routes"]:
            Q = R["cycle"]
            for h in Q["columns"]:
                rows.append([R["id"], h.get("label"), "summary", h.get("beside"), h.get("meets"), h.get("turns"),
                             h.get("turns_cycle"), h.get("cyclist"), h.get("cyclist_ksi"), None, None])
            for t in Q["turns"]:
                rows.append([R["id"], "This route", "left turn", None, None, t["no"], None, None, None,
                             t.get("words"), t.get("cycle")])
            for m_ in Q["meets"]:
                rows.append([R["id"], "This route", "cycle route meets", None, None, None, None, None, None,
                             m_.get("words"), m_.get("name")])
        sheet("D Cycle and left turns", ["Route", "Option", "Row", f"Beside a cycle route ({du})", "Cycle routes meet it",
                                         "Left turns", "Left turns near a cycle route", "Cyclists hurt", "Cyclists KSI",
                                         "Where (from A)", "Cycle route"], rows)
    if "hours" in D["sections"]:
        rows = []
        for R in D["routes"]:
            E = R["hours"]
            for r_ in E["rows"]:
                rows.append([R["id"], r_["label"], X._dist(r_["out_km"]) if r_["out_km"] is not None else None,
                             X._dist(r_["back_km"]) if r_["back_km"] is not None else None]
                            + [r_["at"].get(h) for h in E["hours"]] + [r_["plan_hr"]])
            for u in E["uses"]:
                p = ((u.get("savings") or {}).get("planned") or {})
                rows.append([R["id"], f"Busy-hours road: Alt {u['alt']}, weekdays {u['from']}–{u['to']} ({u['status'].replace('_', ' ')})",
                             None, None] + [None] * len(E["hours"]) + [None, p.get("trips"), p.get("of"), p.get("km"),
                                                                       p.get("min"), p.get("kg"), p.get("eur")])
        hrs = D["routes"][0]["hours"]["hours"] if D["routes"] else []
        sheet("E Busy-hour times", ["Route", "Option", f"Out ({du})", f"Back ({du})"] + [f"Round trip at {h} (h)" for h in hrs]
              + ["Plan (h)", "Trips in the hours, planned", "Of all planned trips", "km (− = less)", "Minutes (− = less)",
                 "kg CO₂e (− = less)", f"Cost {X._cur()} (− = less)"], rows, {2: 40})
    if "diversions" in D["sections"]:
        rows = []
        for R in D["routes"]:
            F = R["diversions"]
            for d in F["items"]:
                rows.append([R["id"], d["when"], "; ".join(d["because"]), d["loaded_words"] if d["out_diverted"] else "usual road",
                             RA._miles(d["out_more_m"]) if (d["out_diverted"] and d["out_more_m"] is not None) else None,
                             d["return_words"] if d["back_diverted"] else "usual road",
                             RA._miles(d["back_more_m"]) if (d["back_diverted"] and d["back_more_m"] is not None) else None,
                             d.get("back_on")])
            for n in F["no_way"]:
                rows.append([R["id"], n["when"], "; ".join(n["because"]),
                             "kept on the usual road" if n["kept"] else "no way round yet", None, None, None, None])
            if not F["items"] and not F["no_way"]:
                rows.append([R["id"], None, "No diversion is planned for this route.", None, None, None, None, None])
        sheet("F Diversions", ["Route", "When", "Why", "Out", f"Out, further ({du})", "Back", f"Back, further ({du})",
                               "Back on the usual road"], rows, {3: 50, 4: 30, 6: 30})
    ab = wb.create_sheet("About")
    for i, t in enumerate([
            "Route analysis: evidence for a route risk assessment, not the assessment.",
            "Made from what Wayscope holds when the file was made; nothing was fetched for it.",
            "Sections A to F: counts only, nothing scored, ranked or divided, except section C's \"Compared with roads "
            "like these\" range. The Summary sheet gives one suggestion a route by fixed rules; its collisions are "
            "counts, never a percentage.",
            "Section C's sheets are today's Route collision evidence, one block per route.",
    ], 1):
        ab.cell(row=i, column=1, value=t)
    ab.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _merge_evidence(wb, D):
    """Section C: each route's collision evidence workbook (export.build_collision_evidence_xlsx), sheet by sheet, into
    "C <sheet>" with the route in a first column; the first route's heading row is the sheet's heading (a later route's
    same heading row is not repeated); a blank row between routes. The cycle sheet is section D's when D is ticked."""
    import openpyxl
    from openpyxl.styles import Font
    targets = {}
    for R in D["routes"]:
        ev = R["evidence"]
        src = openpyxl.load_workbook(io.BytesIO(X.build_collision_evidence_xlsx(ev)))
        for ws in src.worksheets:
            if "cycle" in D["sections"] and ws.title.lower().startswith("cycle"):
                continue
            name = ("C " + ws.title)[:31]
            rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
            if not rows:
                continue
            t = targets.get(name)
            if t is None:
                t = wb.create_sheet(name)
                targets[name] = (t, rows[0])
                t.cell(row=1, column=1, value="Route").font = Font(bold=True)
                for j, v in enumerate(rows[0], 2):
                    t.cell(row=1, column=j, value=v).font = Font(bold=True)
                    t.column_dimensions[_col(j)].width = max(12, min(40, len(str(v or "")) + 4))
                t.column_dimensions["A"].width = 10
                t.freeze_panes = "B2"
                rows, start = rows[1:], 2
            else:
                t, head = t
                if rows[0] == head:
                    rows = rows[1:]
                start = t.max_row + 2
            for i, row in enumerate(rows):
                t.cell(row=start + i, column=1, value=R["id"])
                for j, v in enumerate(row, 2):
                    t.cell(row=start + i, column=j, value=v)


def _col(j):
    from openpyxl.utils import get_column_letter
    return get_column_letter(j)
