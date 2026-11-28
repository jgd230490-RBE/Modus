"""
The route-line specimen sheet (27 Nov 2026, the route lines plan's group 1): every role on every surface, drawn from the ONE
table (`backend/route_line_styles.py`), in colour and in black and white, as an HTML page and a PDF.

It is a tool for whoever changes a route line: build it before and after, put the two side by side. It is NOT served and
nothing links to it; it writes outside the checkout unless told otherwise.

  python backend/tools/route_line_specimen.py [--out <folder>]      (default: the system's temp folder, route-line-specimen)

writes <folder>/route-line-specimen.html and <folder>/route-line-specimen.pdf and prints both paths.

How a value is drawn: a width that is a zoom ramp is read at zoom 12 (the sheet says so); a screen width is in CSS px, a
paper width in pt (1 pt = 4/3 px on the HTML sheet); a casing is drawn first, its width the casing's own or the line's
plus `casing_extra`; a dash is the role's own pattern in line widths; band blues are five swatches. Every field the table
holds for a role on a surface is listed beside its sample, so nothing is left out because it has no picture.
"""
import argparse
import html
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

import route_line_styles as R   # noqa: E402

ZOOM = 12
PT_PX = 4 / 3


def at_zoom(v, z=ZOOM):
    """A Mapbox interpolate ramp ["interpolate", ["linear"], ["zoom"], z0, v0, z1, v1, …] read at zoom z; a number as it is."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list) and len(v) >= 5 and v[0] == "interpolate":
        stops = v[3:]
        pts = [(stops[i], stops[i + 1]) for i in range(0, len(stops) - 1, 2)]
        if not all(isinstance(y, (int, float)) for _, y in pts):
            return None
        if z <= pts[0][0]:
            return float(pts[0][1])
        for (z0, y0), (z1, y1) in zip(pts, pts[1:]):
            if z0 <= z <= z1:
                return float(y0 + (y1 - y0) * (z - z0) / (z1 - z0))
        return float(pts[-1][1])
    return None


def grey(c):
    """The colour as the grey of the same luminance (the black-and-white sheet)."""
    if not (isinstance(c, str) and c.startswith("#") and len(c) in (4, 7)):
        return c
    h = c[1:]
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    y = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return "#%02X%02X%02X" % (y, y, y)


def pairs():
    """(surface, role, spec) for every role a surface draws, surface by surface in the table's order."""
    for s in R.SURFACES:
        for role, sp in R.surface_roles(s).items():
            yield s, role, sp


def sample(sp, surface, dark=False):
    """What to draw for a spec: dict(colour, width, casing, casing_w, dash, opacity, bands) in px, or None for no line."""
    paper = R.SURFACES[surface]["ground"] == "paper"
    k = 1 if not paper else PT_PX
    pick = (lambda f: sp.get(f + "_dark", sp.get(f))) if dark else (lambda f: sp.get(f))
    colour = pick("color") or pick("fill") or pick("glow") or pick("x")
    w = at_zoom(sp.get("width")) if "width" in sp else None
    if w is None:
        w = 3.0 / k if colour else None
    cw = at_zoom(sp.get("casing_width")) if "casing_width" in sp else None
    if cw is None and "casing_extra" in sp and w is not None:
        cw = w + sp["casing_extra"]
    out = {"colour": colour, "width": (w or 0) * k, "casing": pick("casing"), "casing_w": (cw or 0) * k,
           "dash": sp.get("dash"), "opacity": sp.get("opacity", 1) if isinstance(sp.get("opacity", 1), (int, float)) else 1,
           "bands": sp.get("bands")}
    return out if (out["colour"] or out["bands"]) else None


def _svg(sp, surface, dark, bw):
    g = grey if bw else (lambda c: c)
    pick = (lambda f: sp.get(f + "_dark", sp.get(f))) if dark else (lambda f: sp.get(f))
    if "glyph" in sp:   # chevrons: the glyph itself, at its size and spacing, with its halo
        n = max(1, int(200 // max(sp.get("spacing", 34), 8)))
        t = "".join(f'<text x="{14 + i * sp.get("spacing", 34)}" y="21" font-size="{sp.get("size", 18)}" fill="{g(pick("color"))}"'
                    f' stroke="{g(pick("halo") or "#FFFFFF")}" stroke-width="{sp.get("halo_width", 1)}" paint-order="stroke">'
                    f'{html.escape(sp["glyph"])}</text>' for i in range(n))
        return f'<svg class="smp" viewBox="0 0 220 28" width="220" height="28" aria-hidden="true">{t}</svg>'
    if "fill" in sp:    # arrowheads: small triangles, the fill with its ring
        ring = pick("ring") or (R.surface_roles(surface).get("loaded_leg", {}).get("color_dark" if dark else "color"))
        t = "".join(f'<path d="M{20 + i * 40},8 L{30 + i * 40},14 L{20 + i * 40},20 Z" fill="{g(pick("fill"))}"'
                    f' stroke="{g(ring or "#1F2024")}" stroke-width="{sp.get("ring_width", sp.get("halo_width", 1))}"/>' for i in range(5))
        return f'<svg class="smp" viewBox="0 0 220 28" width="220" height="28" aria-hidden="true">{t}</svg>'
    if not sp.get("color") and sp.get("dash"):   # a haul-road stretch: dots in the leg's own colour
        leg = R.surface_roles(surface).get("loaded_leg", {})
        sp = dict(sp, color=leg.get("color", "#3A3C41"), color_dark=leg.get("color_dark", leg.get("color", "#3A3C41")))
    s = sample(sp, surface, dark)
    if not s:
        return '<svg class="smp" viewBox="0 0 220 28" width="220" height="28" aria-hidden="true"></svg>'
    parts = []
    if s["bands"]:
        for i, b in enumerate(s["bands"]):
            parts.append(f'<rect x="{8 + i * 41}" y="6" width="38" height="16" rx="2" fill="{g(b)}"/>')
    else:
        if s["casing"] and s["casing_w"]:
            parts.append(f'<line x1="10" y1="14" x2="210" y2="14" stroke="{g(s["casing"])}" stroke-width="{s["casing_w"]:.2f}" stroke-linecap="butt"/>')
        dash = ""
        if s["dash"] and s["width"]:
            dash = ' stroke-dasharray="' + " ".join(f"{max(d, 0.01) * s['width']:.2f}" for d in s["dash"]) + '"'
        parts.append(f'<line x1="10" y1="14" x2="210" y2="14" stroke="{g(s["colour"])}" stroke-width="{max(s["width"], 0.5):.2f}"'
                     f' stroke-opacity="{s["opacity"]}"{dash} stroke-linecap="{"round" if s["dash"] else "butt"}"/>')
    return f'<svg class="smp" viewBox="0 0 220 28" width="220" height="28" aria-hidden="true">{"".join(parts)}</svg>'


def dark_spec(surface, role, sp):
    """The spec as a dark ground draws it: the week map's legs take the Routes map's own Dark pair and casing (the page
    reads LEG_OUT_DARK / LEG_BACK_DARK / LEG_CASE_DARK there), everything else its own `_dark` fields."""
    if surface == "commit_map" and role in ("loaded_leg", "empty_leg"):
        rm = R.spec(role, "routes_map")
        return dict(sp, color_dark=rm["color_dark"], casing_dark=rm["casing_dark"])
    return sp


def _fields(sp):
    return "; ".join(f"{k} {v}" for k, v in sp.items())


def build_html(bw=False):
    rows = []
    for s, sv in R.SURFACES.items():
        roles = R.surface_roles(s)
        if not roles:
            continue
        screen = sv["ground"] == "screen"
        rows.append(f'<h2 id="s-{s}">{html.escape(sv["what"])} <small>({s}, {"screen, px" if screen else "paper, pt"})</small></h2>')
        rows.append('<table><thead><tr><th>Role</th><th>Key</th><th>Light</th>' + ('<th>Dark</th>' if screen else '') +
                    '<th>Every value</th></tr></thead><tbody>')
        for role, sp in roles.items():
            key = sp.get("key") or sp.get("key_today") or ""
            rows.append(f'<tr data-surface="{s}" data-role="{role}"><th scope="row">{html.escape(role)}</th><td>{html.escape(key)}</td>'
                        f'<td class="lt">{_svg(sp, s, False, bw)}</td>' + (f'<td class="dk">{_svg(dark_spec(s, role, sp), s, True, bw)}</td>' if screen else '') +
                        f'<td class="v">{html.escape(_fields(sp))}</td></tr>')
        rows.append('</tbody></table>')
    odd = "".join(f"<li>{html.escape(o)}</li>" for o in R.KNOWN_ODDITIES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Route-line specimen{' (black and white)' if bw else ''}</title>
<style>
body{{font:13px/1.45 system-ui,sans-serif;color:#1F2024;background:#FFFFFF;margin:24px;}}
h1{{font-size:20px;margin:0 0 4px;}} h2{{font-size:15px;margin:28px 0 6px;border-top:1px solid #1F2024;padding-top:8px;}}
h2 small{{font-weight:400;color:#5F6368;}} p{{margin:4px 0;color:#3A3C41;}}
table{{border-collapse:collapse;width:100%;}} th,td{{text-align:left;vertical-align:middle;padding:4px 8px;border-bottom:1px solid #E3E4E6;}}
thead th{{font-size:12px;color:#5F6368;font-weight:600;}} td.lt{{background:#F4F4F5;}} td.dk{{background:#1F2024;}}
td.v{{font:11px/1.35 ui-monospace,Consolas,monospace;color:#3A3C41;max-width:560px;}}
</style></head><body>
<h1>Route-line specimen{' · black and white' if bw else ''}</h1>
<p>Every route line the product draws, role by role and surface by surface, from <code>backend/route_line_styles.py</code>. A zoom ramp is read at zoom {ZOOM}; screens in CSS px, paper in pt (1 pt = 4/3 px here). Not served, not linked.</p>
{''.join(rows)}
<h2>Known oddities (recorded, not changed)</h2><ul>{odd}</ul>
</body></html>
"""


def build_pdf(path):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    W, H = landscape(A4)
    c = canvas.Canvas(path, pagesize=(W, H))
    c.setTitle("Route-line specimen")

    def rgb(h):
        h = h.lstrip("#")
        h = "".join(x * 2 for x in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def ok_hex(v):
        return isinstance(v, str) and v.startswith("#") and len(v) in (4, 7)

    for bw in (False, True):
        g = grey if bw else (lambda x: x)
        y = H - 40
        c.setFont("Helvetica-Bold", 14); c.drawString(30, y, "Route-line specimen" + (" - black and white" if bw else " - colour")); y -= 24
        for s, role, sp in pairs():
            if y < 50:
                c.showPage(); y = H - 40
            c.setFillColorRGB(0.12, 0.13, 0.14); c.setFont("Helvetica", 8)
            c.drawString(30, y, f"{s} / {role}")
            st = sample(sp, s, False)
            if st:
                if st["bands"]:
                    for i, b in enumerate(st["bands"]):
                        if ok_hex(b):
                            c.setFillColorRGB(*rgb(g(b))); c.rect(200 + i * 30, y - 2, 27, 9, stroke=0, fill=1)
                else:
                    k = 1 / PT_PX if R.SURFACES[s]["ground"] == "paper" else 0.75   # back to pt; a screen px drawn at 0.75 pt
                    if ok_hex(st["casing"]) and st["casing_w"]:
                        c.setStrokeColorRGB(*rgb(g(st["casing"]))); c.setLineWidth(st["casing_w"] * k); c.setDash()
                        c.line(200, y + 2.5, 340, y + 2.5)
                    if ok_hex(st["colour"]):
                        c.setStrokeColorRGB(*rgb(g(st["colour"]))); c.setLineWidth(max(st["width"] * k, 0.3))
                        c.setDash([max(d, 0.01) * st["width"] * k for d in st["dash"]] if st["dash"] else [])
                        c.line(200, y + 2.5, 340, y + 2.5); c.setDash()
            c.setFillColorRGB(0.23, 0.24, 0.25); c.setFont("Helvetica", 6.5)
            words = _fields(sp).replace("→", "to")
            c.drawString(350, y, words[:150])
            if len(words) > 150:
                y -= 8; c.drawString(350, y, words[150:300])
            y -= 15
        c.showPage()
    c.save()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "route-line-specimen"))
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    hp = os.path.join(a.out, "route-line-specimen.html")
    bp = os.path.join(a.out, "route-line-specimen-bw.html")
    pp = os.path.join(a.out, "route-line-specimen.pdf")
    with open(hp, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_html(False))
    with open(bp, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_html(True))
    build_pdf(pp)
    for p in (hp, bp, pp):
        print(p)
    return hp, bp, pp


if __name__ == "__main__":
    main()
