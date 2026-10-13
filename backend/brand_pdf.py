"""
brand_pdf.py — the Wayscope brand in the bulletin's PDFs (13 Oct 2026, W15, bundle C).

WHAT THIS IS
------------
Two things the bulletin's newsletter and leaflet draw with, kept out of export.py:

  fonts()      Inter (Regular, Bold, Italic), registered once from backend/fonts/ — the SIL Open
               Font License 1.1 (backend/fonts/Inter-OFL.txt, shipped beside the files as the
               licence requires; no Reserved Font Name; documents made with it are not bound by
               it). Inter v4.1 (16 Nov 2024), the static TrueType files from the release's
               extras/ttf, downloaded 13 Oct 2026 with the user's permission. When a file is
               missing it falls back to Helvetica and says so (`fallback` True) — never an error.
  draw_logo()  the logo from the brand's own SVG master (frontend/brand/*.svg), drawn as VECTOR
               paths — no raster, no new dependency. A small SVG subset is read: <g>/<path>/
               <circle>, fill / stroke / stroke-width inherited from the group, translate()
               transforms, path commands M L H V Q C A Z (absolute and relative, implicit
               repeats). Arcs become cubic Béziers. One knowing deviation: reportlab cannot
               stroke with a gradient, so the mark's orange gradient (#FF8312 → #FFA10A) is
               stroked in the single colour halfway between them; the HTML page inlines the SVG
               itself, gradient and all.
"""
import math
import os
import re
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(_HERE, "fonts")
BRAND_DIR = os.path.join(os.path.dirname(_HERE), "frontend", "brand")
FONT_FILES = {"Inter": "Inter-Regular.ttf", "Inter-Bold": "Inter-Bold.ttf", "Inter-Italic": "Inter-Italic.ttf"}
FALLBACK = {"Inter": "Helvetica", "Inter-Bold": "Helvetica-Bold", "Inter-Italic": "Helvetica-Oblique"}
FILL_NON_ZERO = 1                 # reportlab.pdfgen.canvas.FILL_NON_ZERO, SVG's default fill rule
GRADIENT_MID = "#FF920E"          # halfway between the brand gradient's #FF8312 and #FFA10A
_STATE = {"fonts": None}


def fonts():
    """{"regular", "bold", "italic", "fallback"}: the registered Inter names, or Helvetica's when a file is missing."""
    if _STATE["fonts"] is not None:
        return _STATE["fonts"]
    names, fallback = {}, False
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for name, fname in FONT_FILES.items():
            path = os.path.join(FONT_DIR, fname)
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, path))
            names[name] = name
    except Exception:
        fallback = True
        names = dict(FALLBACK)
    _STATE["fonts"] = {"regular": names["Inter"], "bold": names["Inter-Bold"], "italic": names["Inter-Italic"],
                       "fallback": fallback}
    return _STATE["fonts"]


# --------------------------------------------------------------------------- #
#  The SVG subset                                                              #
# --------------------------------------------------------------------------- #
_NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_TOK = re.compile(r"[MmLlHhVvQqCcAaZz]|[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6, "A": 7, "Z": 0}


def _arc_to_beziers(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """The SVG arc (endpoint form) as cubic Bézier segments [(c1x, c1y, c2x, c2y, x, y), ...]."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x1, y1, x2, y2, x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, int(math.ceil(abs(dt) / (math.pi / 2) - 1e-9)))
    d = dt / n
    k = 4 / 3 * math.tan(d / 4)
    out = []
    for i in range(n):
        a1, a2 = t1 + i * d, t1 + (i + 1) * d
        e1x, e1y = math.cos(a1), math.sin(a1)
        e2x, e2y = math.cos(a2), math.sin(a2)
        p = [(e1x - k * e1y, e1y + k * e1x), (e2x + k * e2y, e2y - k * e2x), (e2x, e2y)]
        pts = []
        for ux, uy in p:
            X, Y = rx * ux, ry * uy
            pts += [cp * X - sp * Y + cx, sp * X + cp * Y + cy]
        out.append(tuple(pts))
    return out


def path_segments(d, ox=0.0, oy=0.0):
    """An SVG path's d as absolute segments: ("M", x, y) / ("L", x, y) / ("C", c1x, c1y, c2x, c2y, x, y) / ("Z",)."""
    toks = _TOK.findall(d or "")
    segs, i, cmd = [], 0, None
    cx = cy = sx = sy = 0.0
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                segs.append(("Z",))
                cx, cy = sx, sy
                continue
        if cmd is None:
            raise ValueError("path data starts with a number")
        n = _ARGS[cmd.upper()]
        a = [float(x) for x in toks[i:i + n]]
        i += n
        rel = cmd.islower()
        C = cmd.upper()
        if C == "M":
            x, y = (cx + a[0], cy + a[1]) if rel else (a[0], a[1])
            segs.append(("M", x + ox, y + oy))
            cx, cy, sx, sy = x, y, x, y
            cmd = "l" if rel else "L"            # implicit repeats after a moveto are lineto
        elif C == "L":
            x, y = (cx + a[0], cy + a[1]) if rel else (a[0], a[1])
            segs.append(("L", x + ox, y + oy)); cx, cy = x, y
        elif C == "H":
            x = cx + a[0] if rel else a[0]
            segs.append(("L", x + ox, cy + oy)); cx = x
        elif C == "V":
            y = cy + a[0] if rel else a[0]
            segs.append(("L", cx + ox, y + oy)); cy = y
        elif C == "Q":
            qx, qy, x, y = ((cx + a[0], cy + a[1], cx + a[2], cy + a[3]) if rel else tuple(a))
            c1 = (cx + 2 / 3 * (qx - cx), cy + 2 / 3 * (qy - cy))
            c2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            segs.append(("C", c1[0] + ox, c1[1] + oy, c2[0] + ox, c2[1] + oy, x + ox, y + oy)); cx, cy = x, y
        elif C == "C":
            p = [cx + v if rel else v for v in (a[0], a[2], a[4])], [cy + v if rel else v for v in (a[1], a[3], a[5])]
            segs.append(("C", p[0][0] + ox, p[1][0] + oy, p[0][1] + ox, p[1][1] + oy, p[0][2] + ox, p[1][2] + oy))
            cx, cy = p[0][2], p[1][2]
        elif C == "A":
            x, y = (cx + a[5], cy + a[6]) if rel else (a[5], a[6])
            for b in _arc_to_beziers(cx, cy, a[0], a[1], a[2], int(a[3]), int(a[4]), x, y):
                segs.append(("C", b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy, b[4] + ox, b[5] + oy))
            cx, cy = x, y
    return segs


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[k:k + 2], 16) / 255 for k in (0, 2, 4))


def logo_shapes(name="logo-header-on-dark"):
    """
    The SVG master as drawable shapes: (viewBox, [shape]) where a shape is {"kind": "path"|"circle", "segs" or
    (cx, cy, r), "fill": hex|None, "stroke": hex|None, "width": float}. A gradient reference resolves to
    GRADIENT_MID (the knowing deviation in the module docstring).
    """
    root = ET.parse(os.path.join(BRAND_DIR, name + ".svg")).getroot()
    vb = [float(x) for x in root.get("viewBox").split()]
    ns = "{http://www.w3.org/2000/svg}"
    shapes = []

    def colour(v):
        if not v or v == "none":
            return None
        return GRADIENT_MID if v.startswith("url(") else v

    def walk(el, style, tx):
        st = dict(style)
        for k in ("fill", "stroke", "stroke-width"):
            if el.get(k) is not None:
                st[k] = el.get(k)
        t = el.get("transform")
        dx, dy = tx
        if t:
            m = re.match(r"translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)", t)
            if m:
                dx, dy = dx + float(m.group(1)), dy + float(m.group(2))
        tag = el.tag.replace(ns, "")
        base = {"fill": colour(st.get("fill", "#000000")), "stroke": colour(st.get("stroke")),
                "width": float(st.get("stroke-width") or 1)}
        if tag == "path":
            shapes.append(dict(base, kind="path", segs=path_segments(el.get("d"), dx, dy)))
        elif tag == "circle":
            shapes.append(dict(base, kind="circle", circle=(float(el.get("cx")) + dx, float(el.get("cy")) + dy,
                                                              float(el.get("r")))))
        for ch in el:
            if ch.tag.replace(ns, "") not in ("defs", "title"):
                walk(ch, st, (dx, dy))
    walk(root, {}, (0.0, 0.0))
    return vb, shapes


def draw_logo(c, x, y, height, name="logo-header-on-dark"):
    """Draw the logo with its bottom-left at (x, y), `height` points tall; returns the width drawn."""
    vb, shapes = logo_shapes(name)
    s = height / vb[3]
    P = lambda px, py: (x + (px - vb[0]) * s, y + (vb[1] + vb[3] - py) * s)      # SVG y runs down
    c.saveState()
    c.setLineCap(1); c.setLineJoin(1)
    for sh in shapes:
        path = c.beginPath()
        if sh["kind"] == "circle":
            cx_, cy_, r = sh["circle"]
            X, Y = P(cx_, cy_)
            path.circle(X, Y, r * s)
        else:
            for sg in sh["segs"]:
                if sg[0] == "M":
                    path.moveTo(*P(sg[1], sg[2]))
                elif sg[0] == "L":
                    path.lineTo(*P(sg[1], sg[2]))
                elif sg[0] == "C":
                    path.curveTo(*P(sg[1], sg[2]), *P(sg[3], sg[4]), *P(sg[5], sg[6]))
                else:
                    path.close()
        stroke = bool(sh["stroke"])
        fill = bool(sh["fill"])
        if stroke:
            c.setStrokeColorRGB(*_hex(sh["stroke"])); c.setLineWidth(sh["width"] * s)
        if fill:
            c.setFillColorRGB(*_hex(sh["fill"]))
        # SVG fills non-zero; reportlab's default is even-odd, which punches holes where a letter's outlines overlap
        c.drawPath(path, stroke=1 if stroke else 0, fill=1 if fill else 0, fillMode=FILL_NON_ZERO)
    c.restoreState()
    return vb[2] * s


def inline_svg(name="logo-header-on-dark", height=34, label="Wayscope"):
    """The SVG master for the HTML page, inlined at `height` px (vector, gradient kept)."""
    with open(os.path.join(BRAND_DIR, name + ".svg"), encoding="utf-8") as f:
        svg = f.read().strip()
    svg = re.sub(r'\swidth="[^"]+"', "", svg, count=1)
    svg = re.sub(r'\sheight="[^"]+"', "", svg, count=1)
    return svg.replace("<svg ", f'<svg height="{height}" role="img" aria-label="{label}" class="brand-logo" ', 1)
