"""
site_layout_svg.py — draws the style table's symbol and glyph SVG (site_layout_styles.SYMBOLS / GLYPHS) on a ReportLab
canvas, in vector (task 4c PR 5, 31 Oct 2026).

The plan (notes site-layouts-plan-1030.md §2) had a script write 256 px PNGs of each symbol into the repo for the PDF.
Drawn here instead from the SAME SVG the map loads, so a symbol changed in the table can never be stale on paper and
prints sharp at any size. Only what the table's SVG uses is read: <rect> (rx), <circle>, <path> (M L H V C Q A Z, upper
and lower case), <text> and <g transform="translate(..) scale(..)">, with fill, stroke, stroke-width,
stroke-linejoin, font-size, font-weight and text-anchor. test_site_layout_paper checks every symbol and glyph in the
table uses nothing else.

    draw(c, inner_svg, cx, cy, size_pt, rot_deg=0)    the 64 x 64 box centred on (cx, cy), size_pt across, turned
                                                       rot_deg CLOCKWISE (as Mapbox's icon-rotate)
"""
import math
import re
import xml.etree.ElementTree as ET

BOX = 64.0
TAGS = ("rect", "circle", "path", "text", "g")
ATTRS = ("x", "y", "width", "height", "rx", "cx", "cy", "r", "d", "fill", "stroke", "stroke-width", "stroke-linejoin",
         "font-family", "font-weight", "font-size", "text-anchor", "transform")
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOK = re.compile(r"[MmLlHhVvCcQqAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4, "A": 7, "Z": 0}


def parse(inner):
    """The SVG's elements as an ElementTree root (the 64 box)."""
    return ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">' + inner + "</svg>")


def _tag(el):
    return el.tag.split("}", 1)[-1]


def used(inner):
    """(tags, attributes, path commands) an SVG uses: what draw() must understand."""
    tags, attrs, cmds = set(), set(), set()
    for el in parse(inner).iter():
        t = _tag(el)
        if t == "svg":
            continue
        tags.add(t)
        attrs.update(el.attrib)
        if t == "path":
            cmds.update(x.upper() for x in re.findall(r"[A-Za-z]", el.get("d", "")))
    return tags, attrs, cmds


def _hex(v):
    v = (v or "").strip()
    if v.lower() in ("#fff", "white"):
        return (1, 1, 1)
    if v.lower() in ("#111", "black"):
        return (0x11 / 255.0,) * 3
    if re.match(r"^#[0-9a-fA-F]{3}$", v):
        return tuple(int(ch * 2, 16) / 255.0 for ch in v[1:])
    if re.match(r"^#[0-9a-fA-F]{6}$", v):
        return tuple(int(v[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return None


def _arc(p, x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """An SVG elliptical arc from (x1, y1) to (x2, y2) added to path p as cubic Béziers (SVG 1.1 appendix F.6)."""
    if (x1, y1) == (x2, y2):
        return
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        p.lineTo(x2, y2)
        return
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
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
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2.0, sp * cxp + cp * cyp + (y1 + y2) / 2.0

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
    k = 4.0 / 3.0 * math.tan(d / 4)
    for i in range(n):
        a1, a2 = t1 + i * d, t1 + (i + 1) * d
        e1 = (math.cos(a1) - k * math.sin(a1), math.sin(a1) + k * math.cos(a1))
        e2 = (math.cos(a2) + k * math.sin(a2), math.sin(a2) - k * math.cos(a2))
        e3 = (math.cos(a2), math.sin(a2))
        pts = []
        for ex, ey in (e1, e2, e3):
            X, Y = rx * ex, ry * ey
            pts += [cp * X - sp * Y + cx, sp * X + cp * Y + cy]
        p.curveTo(*pts)


def _path(c, d):
    """A ReportLab path of an SVG path's `d` (absolute and relative M L H V C Q A Z)."""
    p = c.beginPath()
    toks = _TOK.findall(d or "")
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    started = False
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                p.close()
                x, y = sx, sy
                continue
        n = _ARGS[cmd.upper()]
        a = [float(v) for v in toks[i:i + n]]
        if len(a) < n:
            break
        i += n
        rel = cmd.islower()
        U = cmd.upper()
        if U == "M":
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            p.moveTo(x, y)
            sx, sy, started = x, y, True
            cmd = "l" if rel else "L"            # further pairs after a moveto are linetos
        elif U == "L":
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            p.lineTo(x, y)
        elif U == "H":
            x = x + a[0] if rel else a[0]
            p.lineTo(x, y)
        elif U == "V":
            y = y + a[0] if rel else a[0]
            p.lineTo(x, y)
        elif U == "C":
            q = [v + (x if k % 2 == 0 else y) for k, v in enumerate(a)] if rel else a
            p.curveTo(*q)
            x, y = q[4], q[5]
        elif U == "Q":
            q = [v + (x if k % 2 == 0 else y) for k, v in enumerate(a)] if rel else a
            qx, qy, ex, ey = q
            p.curveTo(x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), ex + 2 / 3 * (qx - ex), ey + 2 / 3 * (qy - ey), ex, ey)
            x, y = ex, ey
        elif U == "A":
            ex, ey = (x + a[5], y + a[6]) if rel else (a[5], a[6])
            _arc(p, x, y, a[0], a[1], a[2], int(a[3]), int(a[4]), ex, ey)
            x, y = ex, ey
    return p if started else None


def _paint(c, el, inh):
    """Set fill / stroke from the element (inherited from its group); (fill?, stroke?)."""
    fill = el.get("fill", inh.get("fill", "#000"))
    stroke = el.get("stroke", inh.get("stroke"))
    f, s = _hex(fill) if fill != "none" else None, _hex(stroke) if stroke and stroke != "none" else None
    if f:
        c.setFillColorRGB(*f)
    if s:
        c.setStrokeColorRGB(*s)
        c.setLineWidth(float(el.get("stroke-width", inh.get("stroke-width", 1))))
        c.setLineJoin(1 if el.get("stroke-linejoin", inh.get("stroke-linejoin")) == "round" else 0)
    return bool(f), bool(s)


def _el(c, el, inh, F):
    t = _tag(el)
    if t == "g":
        c.saveState()
        tr = el.get("transform", "")
        for fn, args in re.findall(r"(translate|scale)\(([^)]*)\)", tr):
            v = [float(n) for n in _NUM.findall(args)]
            if fn == "translate":
                c.translate(v[0], v[1] if len(v) > 1 else 0)
            else:
                c.scale(v[0], v[1] if len(v) > 1 else v[0])
        sub = dict(inh)
        for k in ("fill", "stroke", "stroke-width", "stroke-linejoin"):
            if el.get(k) is not None:
                sub[k] = el.get(k)
        for ch in el:
            _el(c, ch, sub, F)
        c.restoreState()
        return
    fill, stroke = _paint(c, el, inh)
    if not (fill or stroke):
        return
    from reportlab.pdfgen.canvas import FILL_NON_ZERO
    if t == "rect":
        x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
        rx = float(el.get("rx", 0))
        if rx:
            c.roundRect(x, y, w, h, rx, stroke=int(stroke), fill=int(fill))
        else:
            c.rect(x, y, w, h, stroke=int(stroke), fill=int(fill))
    elif t == "circle":
        c.circle(float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0)), stroke=int(stroke), fill=int(fill))
    elif t == "path":
        p = _path(c, el.get("d"))
        if p is not None:
            c.drawPath(p, stroke=int(stroke), fill=int(fill), fillMode=FILL_NON_ZERO)
    elif t == "text":
        size = float(el.get("font-size", 12))
        font = F["bold"] if el.get("font-weight") in ("700", "bold") else F["regular"]
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        c.saveState()
        c.translate(x, y)
        c.scale(1, -1)                        # the box is y-down; words read upright
        c.setFont(font, size)
        txt = el.text or ""
        anchor = el.get("text-anchor")
        if anchor == "middle":
            c.drawCentredString(0, 0, txt)
        elif anchor == "end":
            c.drawRightString(0, 0, txt)
        else:
            c.drawString(0, 0, txt)
        c.restoreState()


_CACHE = {}


def draw(c, inner, cx, cy, size_pt, rot_deg=0.0, fonts=None):
    """One symbol / glyph: the 64 box centred on (cx, cy) (PDF points, y up), size_pt across, turned clockwise."""
    import brand_pdf
    F = fonts or brand_pdf.fonts()
    root = _CACHE.get(inner)
    if root is None:
        root = _CACHE[inner] = parse(inner)
    c.saveState()
    c.translate(cx, cy)
    if rot_deg:
        c.rotate(-float(rot_deg))
    k = size_pt / BOX
    c.scale(k, -k)                            # y down inside the box, as SVG
    c.translate(-BOX / 2, -BOX / 2)
    for el in root:
        _el(c, el, {}, F)
    c.restoreState()
