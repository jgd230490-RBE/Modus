"""
site_layout_import.py — a contractor's site logistics drawing read into map things (task 4c PR 1, 31 Oct 2026; the
plan notes site-layouts-plan-1030.md §6, the mockup's imports\\convert.py in full).

Every format ends in the SAME shape: things in WGS 84 (or, for a DXF on a site grid, in the drawing's own metres with
its survey points), each carrying what the file said about it — its layer, type, colour, line type, width, words,
block or symbol name, angle — plus a report of what was kept and what was left out. Nothing is saved here: the page
shows the report and the "in the file -> becomes" table, and site_layouts.place() turns the things into layout things.

  DXF, National Grid     ezdxf 1.4.5; EPSG:27700 -> WGS 84 by pyproj with OS's OSTN15 grid (backend/data/proj)
  DXF, site grid         the same reader; placed by 2+ survey points (fit(): turn, scale, shift, no stretch)

  31 Oct 2026 (plan §6 revised after two contractor-style test drawings, notes site-layouts-mockup-1030 / imports):
  a DXF in millimetres, centimetres, inches or feet is SCALED (no units: metres or millimetres from where it sits
  within 50 km of the site, else ask); left out and counted: hidden or frozen layers, layers bound in from another
  drawing, references to drawings not sent, a drawing sheet drawn in model space (its key, title block and border),
  anything over 1 km from the site, the same thing twice, points / leaders / masks / pictures / solid fills /
  dimensions; a block 2 m or more each way is a FOOTPRINT (its outline as an area, as inserted); attribute values
  label a symbol; a hatch keeps its holes; a gradient's first colour is its colour.
  KML / KMZ              Python's own XML reader (fastkml is LGPL)
  GeoJSON                Python's own JSON reader; a file whose crs names another grid is refused
  Shapefile zip          pyshp 3.1.6 + each file's .prj; no .prj is refused
  DWG                    refused: "Save it as DXF in your CAD program and send that." (ezdxf cannot read it)

Limits (plan §6): 10 MB an upload, a zip at most 50 MB unpacked (only the files a format needs are read), 5,000
things. Without the OSTN15 grid PROJ falls back to a Helmert fit 2.1 m out, so an import refuses until the grid is in
place (grid_ready()). Run by the endpoint inside heavy_reads.solo (one at a time; live has 512 MB).
"""
import io
import json
import math
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import site_layout_styles as styles

MAX_BYTES = 10 * 1024 * 1024
MAX_UNPACKED = 50 * 1024 * 1024
MAX_THINGS = 5000
#: a curve is flattened to within this many metres
FLATTEN_M = 0.05
#: a site-grid fit that misses a survey point by more than this asks before placing
MISS_LIMIT_M = 1.0
#: a fitted scale outside this band is flagged (wrong units, or the wrong points)
SCALE_BAND = (0.999, 1.001)
#: a DXF is taken as National Grid when it lands within this distance of the organisation's own locations
NEAR_KM = 50.0

GRID_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "proj")
GRID_FILE = "uk_os_OSTN15_NTv2_OSGBtoETRS.tif"

#: the words each format keeps and leaves out (the page shows them under the report)
KEEPS = {
    "DXF": "Keeps layers, colours, line types, widths, words and their angle, blocks, hatched and closed shapes "
           "(with their holes), circles, arcs and curves. Leaves out dimensions, pictures, 3D, hidden layers, base "
           "mapping, the key and the title block.",
    "KML": "Keeps folders as layers, names, line colour and width, fill colour and icons. Leaves out dashes, "
           "descriptions, heights and pictures laid on the ground.",
    "KMZ": "A KML in a zip: the same as KML.",
    "GeoJSON": "Keeps every property (one names the layer) and the stroke, fill and marker colours. No line types or "
               "words of its own.",
    "Shapefile": "Keeps the attribute table (one field names the layer, one the symbol) and each file's projection. "
                 "No styles; words only from an attribute.",
}

UNIT_WORDS = {0: None, 1: "inches", 2: "feet", 3: "miles", 4: "millimetres", 5: "centimetres", 7: "kilometres",
              8: "microinches", 9: "mils", 10: "yards", 14: "decimetres"}


class Refused(Exception):
    """A file Wayscope will not read, with the reason in plain words (shown as it is)."""


class AskGrid(Exception):
    """A DXF whose grid cannot be told: the page asks National Grid or a site grid."""


R7 = lambda c: [round(float(c[0]), 7), round(float(c[1]), 7)]


def grid_ready():
    return os.path.isfile(os.path.join(GRID_DIR, GRID_FILE))


_PROJ = {"ready": False}


def _proj():
    """pyproj with the OSTN15 grid on its search path and no network (PROJ must never fetch a grid on its own)."""
    import pyproj
    if not _PROJ["ready"]:
        try:
            pyproj.network.set_network_enabled(False)
        except Exception:
            pass
        pyproj.datadir.append_data_dir(GRID_DIR)
        _PROJ["ready"] = True
    return pyproj


def transformer(src):
    pyproj = _proj()
    return pyproj.Transformer.from_crs(src, 4326, always_xy=True)


def _op_words(tr):
    try:
        op = tr.get_last_used_operation()
        return op.description.replace(" (with axis order normalized for visualization)", "") if op else ""
    except Exception:
        return ""


def metres(a, b):
    k = 111320.0
    return math.hypot((a[0] - b[0]) * k * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * k)


def _hex(c):
    if isinstance(c, str) and re.fullmatch(r"#?[0-9A-Fa-f]{6}", c.strip()):
        return "#" + c.strip().lstrip("#").upper()
    return None


def _thing(geom, **p):
    return {"geometry": geom, "properties": {k: v for k, v in p.items() if v not in (None, "")}}


def row_key(p):
    """The mapping table's row for a thing: its block, a footprint block's outline, its symbol, else its layer."""
    if p.get("outline"):
        return "outline " + str(p["outline"])
    if p.get("block"):
        return "block " + str(p["block"])
    if p.get("sym_hint"):
        return "symbol " + str(p["sym_hint"])
    return str(p.get("src_layer") or "(no layer)")


def kind_of(t):
    return "Text" if t["properties"].get("text") and t["geometry"]["type"] == "Point" and not t["properties"].get("block") \
        and not t["properties"].get("sym_hint") else t["geometry"]["type"]


# --------------------------------------------------------------------------------------------------------- DXF
#: $INSUNITS -> (words, metres per drawing unit). 31 Oct 2026 (plan §6, revised): a drawing in millimetres is scaled,
#: not refused — most UK CAD is in millimetres.
UNITS = {1: ("inches", 0.0254), 2: ("feet", 0.3048), 4: ("millimetres", 0.001), 5: ("centimetres", 0.01), 6: ("metres", 1.0)}
#: a footprint block (a welfare cabin drawn as a block) is at least this many metres each way
FOOTPRINT_M = 2.0
#: anything whose middle is further than this from the site is left out (a stray line from 0,0)
FAR_M = 1000.0
#: the types a logistics plan never needs, each counted in the report
LEFT_TYPES = {"DIMENSION": "Dimensions", "ARC_DIMENSION": "Dimensions", "IMAGE": "Pictures (the picture file is not sent)",
              "WIPEOUT": "Masks behind words", "LEADER": "Leader arrows", "MULTILEADER": "Leader arrows",
              "SOLID": "Solid fills (arrowheads)", "3DFACE": "3D shapes", "3DSOLID": "3D shapes", "MESH": "3D shapes",
              "VIEWPORT": "Viewports", "XLINE": "Endless lines", "RAY": "Endless lines", "OLE2FRAME": "Embedded objects",
              "ATTDEF": "Block attributes", "POINT": "Points"}


def _inside(pt, ring):
    """Is a point inside a closed ring (even-odd)?"""
    x, y, c = pt[0], pt[1], False
    for (xi, yi), (xj, yj) in zip(ring, ring[1:]):
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
    return c


def _bound_layer(name):
    """A layer bound in from another drawing (OS base mapping and the like): 'NAME$0$layer' or 'NAME|layer'."""
    n = str(name or "")
    return n.split("$0$")[0].split("|")[0] if ("$0$" in n or "|" in n) else None


def read_dxf(data, grid="auto", near=None, site=None):
    """
    `grid`: 'bng' (EPSG:27700), 'site' (left in the drawing's metres + its survey points) or 'auto'. `site`: the
    location's own position and its gates as [lon, lat] (the far rule and the units guess measure from them); `near`:
    the organisation's locations (the National Grid guess). Every coordinate, height, width and radius comes out in
    METRES, whatever the drawing's units.
    """
    import ezdxf
    from ezdxf import bbox as ezbbox
    from ezdxf import colors as ezcolors
    from ezdxf import path as ezpath
    head = data[:4096]
    if not (b"SECTION" in head or head.startswith(b"AutoCAD Binary DXF")):
        raise Refused("This file is not a DXF drawing.")
    fd, tmp = tempfile.mkstemp(suffix=".dxf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            doc = ezdxf.readfile(tmp)
        except Exception:
            raise Refused("This DXF could not be read. Save it again from your CAD program (any DXF version).")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    msp = doc.modelspace()
    layer_info = {l.dxf.name: l for l in doc.layers}
    left_out = {}

    def lo(k, n=1):
        left_out[k] = left_out.get(k, 0) + n

    def hidden(layer):
        ly = layer_info.get(layer)
        try:
            return ly is not None and (not ly.is_on() or ly.is_frozen())
        except Exception:
            return False

    def is_xref(e):
        try:
            blk = doc.blocks.get(e.dxf.name)
            return blk is None or bool(blk.block_record.is_xref)
        except Exception:
            return False

    def usable(e):
        lay = e.dxf.layer
        return not hidden(lay) and not _bound_layer(lay) and not (e.dxftype() == "INSERT" and is_xref(e))

    # ---- where the drawing sits: the middle (median) of its inserts, words and line starts, in drawing units
    sample = []
    for e in msp:
        try:
            if not usable(e):
                continue
            t = e.dxftype()
            if t in ("INSERT", "TEXT", "MTEXT"):
                sample.append((e.dxf.insert[0], e.dxf.insert[1]))
            elif t == "LINE":
                sample.append((e.dxf.start[0], e.dxf.start[1]))
            elif t in ("LWPOLYLINE", "POLYLINE"):
                v = next(iter(e.points()))
                sample.append((v[0], v[1]))
            elif t in ("CIRCLE", "ARC"):
                sample.append((e.dxf.center[0], e.dxf.center[1]))
            elif t == "HATCH" and e.paths and getattr(e.paths[0], "vertices", None):
                v = e.paths[0].vertices[0]
                sample.append((v[0], v[1]))
        except Exception:
            pass
    mid = ((sorted(v[0] for v in sample)[len(sample) // 2], sorted(v[1] for v in sample)[len(sample) // 2])
           if sample else None)
    has_control = any(_is_control_layer(e.dxf.layer) for e in msp.query("POINT"))

    # the site (and the organisation's places) on National Grid, for the units guess and the far rule
    site_bng, near_bng = [], []
    try:
        to_bng = _proj().Transformer.from_crs(4326, 27700, always_xy=True)
        site_bng = [to_bng.transform(p[0], p[1]) for p in (site or [])]
        near_bng = [to_bng.transform(p[0], p[1]) for p in (near or [])]
    except Exception:
        pass

    def near_m(xy, pts):
        return min((math.hypot(xy[0] - q[0], xy[1] - q[1]) for q in pts), default=float("inf"))

    # ---- units
    code = doc.header.get("$INSUNITS", 0)
    if code in UNITS:
        uname, k = UNITS[code]
        units_words = f"{uname}, from the file"
    elif code == 0:
        k = None
        if mid and grid != "site":
            for f in (1.0, 0.001):
                if near_m((mid[0] * f, mid[1] * f), site_bng or near_bng) <= NEAR_KM * 1000:
                    k = f
                    break
        if k is not None:
            uname = "metres" if k == 1 else "millimetres"
            units_words = f"{uname}, from where the drawing sits (no units in the file)"
        elif grid == "site" or has_control:
            k, units_words = 1.0, "metres (no units in the file; the survey points check it)"
        elif grid == "bng":
            raise Refused("This drawing has no units and does not sit near the site. Set its units in your CAD "
                          "program and save it again.")
        else:
            raise AskGrid("Is this drawing on National Grid, or on the site's own grid?")
    else:
        w = UNIT_WORDS.get(code) or "units Wayscope does not read"
        raise Refused(f"This drawing is in {w}. Save it in metres or millimetres and send it again.")

    # ---- which grid
    if grid == "auto":
        if mid and near_m((mid[0] * k, mid[1] * k), site_bng or near_bng) <= NEAR_KM * 1000:
            grid = "bng"
        elif has_control:
            grid = "site"
        else:
            raise AskGrid("Is this drawing on National Grid, or on the site's own grid?")
    # the far rule's centre, in metres: the site on National Grid, else the drawing's own middle
    centres = site_bng if (grid == "bng" and site_bng) else [(mid[0] * k, mid[1] * k)] if mid else []

    def colour(e, lay=None):
        try:
            if e.dxf.hasattr("true_color"):
                return "#%02X%02X%02X" % tuple(e.rgb)
        except Exception:
            pass
        aci = e.dxf.get("color", 256)
        if aci in (0, 256):
            ly = layer_info.get(lay or e.dxf.layer)
            aci = abs(ly.dxf.color) if ly else 7
        return "#%02X%02X%02X" % tuple(ezcolors.aci2rgb(aci)) if 0 < aci < 256 else None

    def linetype(e):
        lt = e.dxf.get("linetype", "BYLAYER")
        if lt.upper() in ("BYLAYER", "BYBLOCK"):
            ly = layer_info.get(e.dxf.layer)
            lt = ly.dxf.linetype if ly else "CONTINUOUS"
        return lt.upper()

    # ---- a drawing sheet drawn in model space: its key, its title block and its border's layer
    def box(e):
        p = [(v[0], v[1]) for v in e.get_points("xy")]
        return (min(q[0] for q in p), min(q[1] for q in p), max(q[0] for q in p), max(q[1] for q in p))

    rects = []
    for e in msp.query("LWPOLYLINE"):
        try:
            if e.closed and len(e) == 4 and usable(e):
                rects.append((box(e), e))
        except Exception:
            pass

    def around(v):
        inside = [(b, e) for b, e in rects if b[0] <= v[0] <= b[2] and b[1] <= v[1] <= b[3]]
        return min(inside, key=lambda be: (be[0][2] - be[0][0]) * (be[0][3] - be[0][1])) if inside else None

    zones = {}
    for tx in msp.query("TEXT MTEXT"):
        try:
            if not usable(tx):
                continue
            words = (tx.plain_text() if tx.dxftype() == "MTEXT" else tx.dxf.text).strip().upper()
            v = tx.dxf.insert
        except Exception:
            continue
        if words in ("KEY", "LEGEND"):
            hit = around(v)
            if hit:
                zones["In the drawing's key (its sample lines and symbols)"] = hit[0]
        elif re.search(r"SCALE\s+1\s*:|\bDRG\b|DRAWING NO|\bREV\b", words):
            hit = around(v)
            if hit:
                zones["In the title block"] = hit[0]
    sheet_layer = None
    tb = zones.get("In the title block")
    if tb:
        big = [(b, e) for b, e in rects if (b[2] - b[0]) * k > 200 and b[0] <= tb[0] and b[2] >= tb[2]
               and b[1] <= tb[1] and b[3] >= tb[3]]
        if big:
            sheet_layer = max(big, key=lambda be: be[0][2] - be[0][0])[1].dxf.layer

    def extents(e):
        try:
            ext = ezbbox.extents([e])
            return ext if ext.has_data else None
        except Exception:
            return None

    def in_zone(ext):
        if ext is None:
            return None
        for why, b in zones.items():
            if b[0] <= ext.extmin.x and ext.extmax.x <= b[2] and b[1] <= ext.extmin.y and ext.extmax.y <= b[3]:
                return why
        return None

    def where(e, ext):
        if e.dxf.hasattr("insert"):
            return e.dxf.insert
        t = e.dxftype()
        if t == "LINE":
            return e.dxf.start.lerp(e.dxf.end)
        if t == "CIRCLE":
            return e.dxf.center
        return ext.center if ext is not None else None

    M = lambda v: (v[0] * k, v[1] * k)            # drawing units -> metres (still on the drawing's grid)
    flat = FLATTEN_M / k                           # the flattening tolerance in drawing units

    def ring_of(path):
        r = [M(v) for v in path.flattening(flat)]
        if len(r) >= 3 and r[0] != r[-1]:
            r.append(r[0])
        return r if len(r) >= 4 else None

    def area2(r):
        return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:])))

    raw, control, ctl_text, seen = [], [], [], set()
    blocks, mirrored = {}, 0
    for e in msp:
        extra = []                                   # a hatch's separate islands, each its own area
        try:
            t, layer = e.dxftype(), e.dxf.layer
        except Exception:
            lo("Things that could not be read")
            continue
        if len(raw) > MAX_THINGS:
            raise Refused(f"This drawing has more than {MAX_THINGS:,} things. Send the logistics layers only.")
        try:
            if hidden(layer):
                lo(f"On a hidden layer ({layer})")
                continue
            if _bound_layer(layer):
                lo(f"Base mapping from another drawing ({_bound_layer(layer)})")
                continue
            if t == "INSERT" and is_xref(e):
                lo(f"A drawing referred to but not sent ({e.dxf.name})")
                continue
            if sheet_layer and layer == sheet_layer:
                lo(f"The drawing sheet's border ({layer})")
                continue
            if t == "POINT":
                loc = e.dxf.location
                if _is_control_layer(layer) and grid == "site":
                    control.append(M(loc))
                else:
                    lo("Survey points" if _is_control_layer(layer) else "Points")
                continue
            if t in LEFT_TYPES:
                lo(LEFT_TYPES[t])
                continue
            ext = extents(e)
            z = in_zone(ext)
            if z:
                lo(z)
                continue
            w = where(e, ext)
            if w is not None and centres and near_m(M(w), centres) > FAR_M:
                lo("Over 1 km from the site")
                continue
            base = dict(src_layer=layer, src_type=t, color=colour(e), linetype=linetype(e))
            if t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "SPLINE", "ELLIPSE"):
                if t == "POLYLINE" and (e.is_3d_polyline is False and e.is_2d_polyline is False):
                    lo("3D shapes")
                    continue
                pts = [M(v) for v in ezpath.make_path(e).flattening(flat)]
                if len(pts) < 2:
                    continue
                closed = (t == "LWPOLYLINE" and e.closed) or (t == "POLYLINE" and e.is_closed)
                wid = (e.dxf.get("const_width", 0) if t == "LWPOLYLINE" else 0) * k
                if closed and len(pts) >= 3:
                    if pts[0] != pts[-1]:
                        pts.append(pts[0])
                    item = ("Polygon", [pts], dict(base, width_m=round(wid, 2) or None))
                else:
                    item = ("LineString", pts, dict(base, width_m=round(wid, 2) or None))
            elif t == "HATCH":
                rings = [r for r in (ring_of(p) for p in ezpath.from_hatch(e)) if r]
                if not rings:
                    lo("Hatches with no edge")
                    continue
                rings.sort(key=lambda r: -area2(r))      # the biggest is the outside
                # a ring inside the outside (and not inside a hole) is a hole; any other is an island of its own
                # (seen 31 Oct on a contractor-style drawing: a pad cut out beside the zone, not in it)
                outer, holes, islands = rings[0], [], []
                for r in rings[1:]:
                    (holes if _inside(r[0], outer) and not any(_inside(r[0], h) for h in holes) else islands).append(r)
                p = dict(base, hatch=e.dxf.pattern_name)
                if e.gradient is not None:
                    try:
                        p["color"] = "#%02X%02X%02X" % tuple(e.gradient.color1)
                    except Exception:
                        pass
                    p["hatch"] = "GRADIENT"
                item = ("Polygon", [outer] + holes[:50], p)
                extra = [("Polygon", [r], dict(p)) for r in islands[:50]]
            elif t == "CIRCLE":
                c, r = e.dxf.center, e.dxf.radius
                ring = [M((c[0] + r * math.cos(2 * math.pi * i / 64), c[1] + r * math.sin(2 * math.pi * i / 64))) for i in range(64)]
                item = ("Polygon", [ring + [ring[0]]], dict(base, radius_m=round(r * k, 2)))
            elif t in ("TEXT", "MTEXT"):
                if t == "TEXT":
                    v = e.get_placement()[1]
                    txt, hgt, rot = e.dxf.text, e.dxf.get("height", 2.5), e.dxf.get("rotation", 0.0)
                else:
                    v = e.dxf.insert
                    txt, hgt, rot = e.plain_text(), e.dxf.get("char_height", 2.5), e.get_rotation()
                if _is_control_layer(layer):
                    ctl_text.append((txt, M(v)))
                    continue
                txt = re.sub(r"\s+", " ", txt or "").strip()
                if not txt or not re.search(r"\w", txt):
                    continue
                item = ("Point", M(v), dict(base, text=txt[:200], height_m=round(hgt * k, 2), dxf_rot=rot))
            elif t == "INSERT":
                name = e.dxf.name
                shown = "(a dynamic block)" if name.startswith("*U") else name
                label = " / ".join(a.dxf.text.strip() for a in e.attribs if (a.dxf.text or "").strip())[:80] or None
                xs, ys = e.dxf.get("xscale", 1.0), e.dxf.get("yscale", 1.0)
                if xs * ys < 0:
                    mirrored += 1
                blk = doc.blocks.get(name)
                outs = [b for b in blk if (b.dxftype() == "LWPOLYLINE" and b.closed)
                        or (b.dxftype() == "POLYLINE" and b.is_closed)] if blk is not None else []
                local = ezbbox.extents(outs) if outs else None
                bw = local.size.x * abs(xs) * k if local is not None and local.has_data else 0
                bh = local.size.y * abs(ys) * k if local is not None and local.has_data else 0
                if bw >= FOOTPRINT_M and bh >= FOOTPRINT_M:
                    m44 = e.matrix44()                    # turned, scaled and mirrored as inserted
                    big = max(outs, key=lambda b: area2([(v[0], v[1]) for v in ezpath.make_path(b).flattening(flat)] or [(0, 0)]))
                    ring = [M(m44.transform((v[0], v[1], 0))) for v in ezpath.make_path(big).flattening(flat)]
                    if ring and ring[0] != ring[-1]:
                        ring.append(ring[0])
                    blocks[f"{shown}: an outline, {bw:.1f} × {bh:.1f} m"] = blocks.get(f"{shown}: an outline, {bw:.1f} × {bh:.1f} m", 0) + 1
                    item = ("Polygon", [ring], dict(base, outline=shown, name=label))
                else:
                    v = e.dxf.insert
                    blocks[f"{shown}: a symbol"] = blocks.get(f"{shown}: a symbol", 0) + 1
                    item = ("Point", M(v), dict(base, block=shown, name=label, attribs=label,
                                                scale=round(xs, 3), dxf_rot=e.dxf.get("rotation", 0.0)))
            else:
                lo(t.title())
                continue
            sig = (layer, t, json.dumps(item[1], default=list))
            if sig in seen:
                lo("The same thing twice")
                continue
            seen.add(sig)
            raw.append(item)
            raw.extend(extra)
        except Refused:
            raise
        except Exception:
            lo("Things that could not be read")
    paper = sum(len(lay) for lay in doc.layouts if lay.name != "Model")
    if paper:
        lo("The title block and anything else in paper space", paper)
    if not raw:
        raise Refused("This drawing has nothing Wayscope can place in model space.")

    rep = {"format": "DXF", "version": doc.dxfversion, "units": units_words, "left_out": left_out}
    if blocks:
        rep["blocks"] = blocks
    if mirrored:
        rep["mirrored_blocks"] = mirrored
    things = []
    if grid == "bng":
        xs_ = [c[0] for g, cs, _ in raw for c in _flat(g, cs)]
        ys_ = [c[1] for g, cs, _ in raw for c in _flat(g, cs)]
        if not (-1000 <= min(xs_) and max(xs_) <= 800_000 and -1000 <= min(ys_) and max(ys_) <= 1_400_000):
            raise Refused("This drawing is not on National Grid: its coordinates are outside Great Britain. "
                          "Bring it in as a site-grid drawing.")
        tr = transformer(27700)
        P = lambda v: R7(tr.transform(v[0], v[1]))
        for g, cs, p in raw:
            if g == "Point":
                c = P(cs)
                if "dxf_rot" in p:
                    p["rot"] = _bearing_rot(tr, cs, p.pop("dxf_rot"), c)
                things.append(_thing({"type": "Point", "coordinates": c}, **p))
            elif g == "LineString":
                things.append(_thing({"type": "LineString", "coordinates": [P(v) for v in cs]}, **p))
            else:
                things.append(_thing({"type": "Polygon", "coordinates": [[P(v) for v in r] for r in cs]}, **p))
        rep.update(grid="bng", crs="British National Grid", transform=_op_words(tr))
    else:
        r3 = lambda v: [round(v[0], 3), round(v[1], 3)]
        for g, cs, p in raw:
            if "dxf_rot" in p:
                p["rot"] = round(-p.pop("dxf_rot"), 2)          # the fitted turn is taken off at place()
            geom = ({"type": "Point", "coordinates": r3(cs)} if g == "Point" else
                    {"type": "LineString", "coordinates": [r3(v) for v in cs]} if g == "LineString" else
                    {"type": "Polygon", "coordinates": [[r3(v) for v in r] for r in cs]})
            things.append(_thing(geom, **p))
        if len(control) < 2:
            raise Refused("This drawing is on its own site grid and has fewer than two survey points, so it cannot be "
                          "placed. Add the survey control points (as points on a layer named CONTROL or SURVEY) and "
                          "save it again.")
        cps = []
        for i, v in enumerate(control):
            near_t = min(ctl_text, key=lambda tv: math.hypot(tv[1][0] - v[0], tv[1][1] - v[1])) if ctl_text else None
            name = near_t[0].split()[0] if near_t and math.hypot(near_t[1][0] - v[0], near_t[1][1] - v[1]) < 25 else f"CP{i + 1}"
            cps.append({"name": name[:20], "x": round(v[0], 3), "y": round(v[1], 3)})
        names = [c["name"] for c in cps]
        for i, c in enumerate(cps):                       # two points named alike keep both
            if names.count(c["name"]) > 1:
                c["name"] = f"{c['name']}-{i + 1}"
        rep.update(grid="site", crs="a site grid (no map position in the file)",
                   control=sorted(cps, key=lambda c: c["name"])[:12])
    return things, rep


def _flat(g, cs):
    return [cs] if g == "Point" else cs if g == "LineString" else cs[0]


def _is_control_layer(name):
    n = str(name or "").upper()
    return "CONTROL" in n or "SURVEY" in n


def _bearing_rot(tr, v, dxf_rot, a0):
    """Our `rot` (degrees; 0 = upright on a north-up map) from DXF's rotation (anticlockwise from the drawing's x
    axis), with the grid's convergence here taken in."""
    q = (v[0] + 10 * math.cos(math.radians(dxf_rot)), v[1] + 10 * math.sin(math.radians(dxf_rot)))
    a1 = tr.transform(q[0], q[1])
    dx = (a1[0] - a0[0]) * math.cos(math.radians(a0[1]))
    return round((math.degrees(math.atan2(dx, a1[1] - a0[1])) + 360) % 360 - 90, 2)


# --------------------------------------------------------------------------------------------------------- KML / KMZ
KML_NS = "{http://www.opengis.net/kml/2.2}"


def _kml_colour(c):
    """KML's aabbggrr -> (#RRGGBB, opacity)"""
    c = (c or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{8}", c):
        return None, None
    return "#" + (c[6:8] + c[4:6] + c[2:4]).upper(), round(int(c[0:2], 16) / 255, 2)


def read_kml(data, fmt="KML"):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise Refused("This KML could not be read: it is not a Google Earth file.")
    ns = KML_NS if root.tag.startswith(KML_NS) else ""
    q = lambda path: "/".join(ns + p for p in path.split("/"))
    styles_ = {}
    for s in root.iter(ns + "Style"):
        d = {}
        lc, lw = s.find(q("LineStyle/color")), s.find(q("LineStyle/width"))
        pc, href, isc = s.find(q("PolyStyle/color")), s.find(q("IconStyle/Icon/href")), s.find(q("IconStyle/scale"))
        if lc is not None and lc.text:
            d["color"] = _kml_colour(lc.text)[0]
        if lw is not None and lw.text:
            try:
                d["width_px"] = float(lw.text)
            except ValueError:
                pass
        if pc is not None and pc.text:
            d["fill"], d["fill_opacity"] = _kml_colour(pc.text)
        if href is not None and href.text:
            d["sym_hint"] = re.sub(r"\.(png|jpe?g|gif)$", "", href.text.strip().rsplit("/", 1)[-1], flags=re.I)[:40]
        if isc is not None and isc.text:
            try:
                if float(isc.text) == 0:
                    d["label_only"] = True
            except ValueError:
                pass
        if s.get("id"):
            styles_["#" + s.get("id")] = d
    things, left_out = [], {}

    def lo(k):
        left_out[k] = left_out.get(k, 0) + 1

    def coords(el):
        out = []
        for t in (el.text or "").split():
            try:
                v = [float(x) for x in t.split(",")[:2]]
            except ValueError:
                continue
            if len(v) == 2 and -180 <= v[0] <= 180 and -90 <= v[1] <= 90:
                out.append(R7(v))
        return out

    parent = {c: p for p in root.iter() for c in p}
    for pm in root.iter(ns + "Placemark"):
        if len(things) > MAX_THINGS:
            raise Refused(f"This file has more than {MAX_THINGS:,} things. Send the logistics layers only.")
        f = parent.get(pm)
        while f is not None and f.tag != ns + "Folder":
            f = parent.get(f)
        layer = (f.findtext(ns + "name") if f is not None else None) or "(no folder)"
        name = (pm.findtext(ns + "name") or "").strip()
        st = styles_.get((pm.findtext(ns + "styleUrl") or "").strip(), {})
        base = dict(src_layer=layer.strip()[:120], name=name[:200], color=st.get("color"), width_px=st.get("width_px"),
                    fill=st.get("fill"), fill_opacity=st.get("fill_opacity"))
        if pm.find(ns + "description") is not None:
            lo("Descriptions")
        pt, ls = pm.find(q("Point/coordinates")), pm.find(q("LineString/coordinates"))
        pg = pm.find(q("Polygon/outerBoundaryIs/LinearRing/coordinates"))
        if pt is not None and coords(pt):
            c = coords(pt)[0]
            if st.get("label_only") or not st.get("sym_hint"):
                if name:
                    things.append(_thing({"type": "Point", "coordinates": c}, **base, src_type="Label", text=name))
                else:
                    lo("Points with no name")
            else:
                things.append(_thing({"type": "Point", "coordinates": c}, **base, src_type="Point", sym_hint=st.get("sym_hint")))
        elif ls is not None and len(coords(ls)) >= 2:
            things.append(_thing({"type": "LineString", "coordinates": coords(ls)}, **base, src_type="LineString"))
        elif pg is not None and len(coords(pg)) >= 3:
            ring = coords(pg)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            things.append(_thing({"type": "Polygon", "coordinates": [ring]}, **base, src_type="Polygon"))
            if pm.find(q("Polygon/innerBoundaryIs")) is not None:
                lo("Holes in areas")
        else:
            lo("Other shapes")
    n_over = len(list(root.iter(ns + "GroundOverlay")))
    if n_over:
        left_out["Pictures laid on the ground"] = n_over
    if not things:
        raise Refused("This file has no points, lines or areas Wayscope can place.")
    return things, {"format": fmt, "grid": "wgs84", "crs": "longitude / latitude", "left_out": left_out}


def read_kmz(data):
    z = _zip(data)
    kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
    if not kmls:
        raise Refused("This KMZ holds no KML.")
    name = "doc.kml" if "doc.kml" in kmls else kmls[0]
    return read_kml(_zip_read(z, name), "KMZ")


# --------------------------------------------------------------------------------------------------------- GeoJSON
def read_geojson(data):
    try:
        d = json.loads(data.decode("utf-8-sig"))
    except Exception:
        raise Refused("This GeoJSON could not be read.")
    crs = ((d.get("crs") or {}).get("properties") or {}).get("name", "") if isinstance(d, dict) else ""
    if crs and "4326" not in crs and "CRS84" not in crs:
        raise Refused("This GeoJSON is not in longitude / latitude. Export it as WGS 84 (EPSG:4326).")
    feats = d.get("features") if isinstance(d, dict) and d.get("type") == "FeatureCollection" else \
        [d] if isinstance(d, dict) and d.get("type") == "Feature" else None
    if feats is None:
        raise Refused("This GeoJSON holds no features.")
    things, left_out = [], {}
    for f in feats:
        if len(things) > MAX_THINGS:
            raise Refused(f"This file has more than {MAX_THINGS:,} things. Send the logistics layers only.")
        p, g = (f.get("properties") or {}) if isinstance(f, dict) else {}, (f.get("geometry") or {}) if isinstance(f, dict) else {}
        parts = []
        gt = g.get("type")
        if gt in ("Point", "LineString", "Polygon"):
            parts = [(gt, g.get("coordinates"))]
        elif gt in ("MultiPoint", "MultiLineString", "MultiPolygon"):
            parts = [(gt[5:], c) for c in (g.get("coordinates") or [])]
        else:
            left_out[gt or "Things with no shape"] = left_out.get(gt or "Things with no shape", 0) + 1
            continue
        sym = p.get("marker-symbol")
        layer = p.get("layer") or p.get("Layer") or p.get("LAYER") or "(no layer)"
        for t, c in parts:
            try:
                if t == "Point":
                    geom = {"type": "Point", "coordinates": R7(c)}
                elif t == "LineString":
                    geom = {"type": "LineString", "coordinates": [R7(v) for v in c]}
                else:
                    geom = {"type": "Polygon", "coordinates": [[R7(v) for v in c[0]]]}
                    if len(c) > 1:
                        left_out["Holes in areas"] = left_out.get("Holes in areas", 0) + 1
            except Exception:
                left_out["Shapes that could not be read"] = left_out.get("Shapes that could not be read", 0) + 1
                continue
            label = t == "Point" and not sym
            things.append(_thing(geom, src_layer=str(layer)[:120], src_type="Label" if label else t,
                                 name=(str(p["name"])[:200] if p.get("name") is not None else None),
                                 text=(str(p.get("name"))[:200] if label and p.get("name") else None),
                                 sym_hint=(str(sym)[:40] if sym else None), color=_hex(p.get("stroke")),
                                 fill=_hex(p.get("fill")), fill_opacity=p.get("fill-opacity")))
    things = [t for t in things if t["geometry"]["type"] != "Point" or t["properties"].get("sym_hint") or t["properties"].get("text")]
    if not things:
        raise Refused("This GeoJSON has no points, lines or areas Wayscope can place.")
    return things, {"format": "GeoJSON", "grid": "wgs84", "crs": "longitude / latitude", "left_out": left_out}


# --------------------------------------------------------------------------------------------------------- shapefile zip
def read_shp_zip(data):
    import shapefile
    pyproj = _proj()
    z = _zip(data)
    names = z.namelist()
    low = {n.lower(): n for n in names}
    shps = [n for n in names if n.lower().endswith(".shp") and not n.startswith("__MACOSX")]
    if not shps:
        raise Refused("This zip holds no shapefile (.shp).")
    things, left_out, crs_words, ops = [], {}, set(), set()
    for shp in shps:
        base = shp[:-4]
        get = lambda ext: low.get((base + ext).lower())
        if not get(".prj"):
            raise Refused(f"{shp.rsplit('/', 1)[-1]} has no .prj file, so its position is unknown.")
        if not get(".shx") or not get(".dbf"):
            raise Refused(f"{shp.rsplit('/', 1)[-1]} needs its .shx and .dbf files in the same zip.")
        try:
            crs = pyproj.CRS.from_wkt(_zip_read(z, get(".prj")).decode("utf-8", "replace"))
        except Exception:
            raise Refused(f"The .prj of {shp.rsplit('/', 1)[-1]} could not be read, so its position is unknown.")
        crs_words.add(crs.name)
        tr = pyproj.Transformer.from_crs(crs, 4326, always_xy=True)
        enc = "utf-8"
        if get(".cpg"):
            enc = (_zip_read(z, get(".cpg")).decode("ascii", "ignore").strip() or "utf-8")
        try:
            r = shapefile.Reader(shp=io.BytesIO(_zip_read(z, shp)), shx=io.BytesIO(_zip_read(z, get(".shx"))),
                                 dbf=io.BytesIO(_zip_read(z, get(".dbf"))), encoding=enc, encodingErrors="replace")
        except Exception:
            raise Refused(f"{shp.rsplit('/', 1)[-1]} could not be read.")
        fields = [f[0] for f in r.fields[1:]]
        up = {f.upper(): f for f in fields}
        for sr in r.iterShapeRecords():
            if len(things) > MAX_THINGS:
                raise Refused(f"This zip has more than {MAX_THINGS:,} things. Send the logistics layers only.")
            rec = dict(zip(fields, sr.record))
            try:
                gi = sr.shape.__geo_interface__
            except Exception:
                left_out["Empty shapes"] = left_out.get("Empty shapes", 0) + 1
                continue
            T = lambda c: R7(tr.transform(c[0], c[1]))
            gt, co = gi["type"], gi["coordinates"]
            parts = ([(gt, co)] if gt in ("Point", "LineString", "Polygon") else
                     [(gt[5:], c) for c in co] if gt in ("MultiPoint", "MultiLineString", "MultiPolygon") else [])
            if not parts:
                left_out[gt] = left_out.get(gt, 0) + 1
                continue
            val = lambda k: (str(rec[up[k]]).strip() or None) if k in up and rec.get(up[k]) not in (None, "") else None
            sym, name = val("SYMBOL"), val("NAME") or val("LABEL") or val("TEXT")
            layer = val("LAYER") or base.rsplit("/", 1)[-1]
            for t, c in parts:
                if t == "Point":
                    geom = {"type": "Point", "coordinates": T(c)}
                elif t == "LineString":
                    geom = {"type": "LineString", "coordinates": [T(v) for v in c]}
                else:
                    geom = {"type": "Polygon", "coordinates": [[T(v) for v in c[0]]]}
                label = t == "Point" and not sym
                if label and not name:
                    left_out["Points with no name"] = left_out.get("Points with no name", 0) + 1
                    continue
                things.append(_thing(geom, src_layer=layer[:120], src_type="Label" if label else t, name=(name or None) and name[:200],
                                     text=name[:200] if label else None, sym_hint=sym[:40] if sym else None))
            ops.add(_op_words(tr))
    if not things:
        raise Refused("This shapefile has no points, lines or areas Wayscope can place.")
    return things, {"format": "Shapefile", "grid": "wgs84", "crs": " / ".join(sorted(crs_words)),
                    "transform": " / ".join(sorted(o for o in ops if o)), "left_out": left_out}


def _zip(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Refused("This zip could not be opened.")
    return z


def _zip_read(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_UNPACKED:
        raise Refused("This zip unpacks to more than 50 MB.")
    with z.open(info) as f:
        out = f.read(MAX_UNPACKED + 1)
    if len(out) > MAX_UNPACKED:
        raise Refused("This zip unpacks to more than 50 MB.")
    return out


# --------------------------------------------------------------------------------------------------------- one entry
def read(data, file_name, grid="auto", near=None, site=None):
    """
    The file's things and report: {"things": [...], "report": {...}}. Raises Refused (plain words) or AskGrid.
    `near` = the organisation's locations as [lon, lat] (a DXF on National Grid lands near one of them); `site` = the
    location itself and its gates (a DXF's units guess and its 1 km rule measure from them).
    """
    if not grid_ready():
        raise Refused("Drawings cannot be brought in on this server yet. Ask your admin.")
    name = (file_name or "").strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if len(data) > MAX_BYTES:
        raise Refused("This file is over 10 MB. Send the logistics layers only.")
    if not data:
        raise Refused("This file is empty.")
    if ext == "dwg":
        raise Refused("Wayscope cannot read DWG. Save it as DXF in your CAD program and send that.")
    if ext == "dxf":
        things, rep = read_dxf(data, grid=grid, near=near, site=site)
    elif ext == "kml":
        things, rep = read_kml(data)
    elif ext == "kmz":
        things, rep = read_kmz(data)
    elif ext in ("geojson", "json"):
        things, rep = read_geojson(data)
    elif ext == "zip":
        things, rep = read_shp_zip(data)
    else:
        raise Refused("Wayscope reads DXF, KML, KMZ, GeoJSON and shapefile zips.")
    if len(things) > MAX_THINGS:
        raise Refused(f"This file has more than {MAX_THINGS:,} things. Send the logistics layers only.")
    rep["file"] = name[:200]
    rep["things"] = len(things)
    rep["layers"] = len({t["properties"].get("src_layer") for t in things})
    rep["keeps"] = KEEPS.get(rep["format"], "")
    return {"things": things, "report": rep}


def rows(things, saved=None):
    """The mapping table: one row per source layer / block / symbol, with its count, colour, line type, the shapes on
    it and what it becomes (the organisation's saved choice, else a guess)."""
    saved = saved or {}
    out = {}
    for t in things:
        p = t["properties"]
        k = row_key(p)
        r = out.setdefault(k, {"key": k, "n": 0, "color": p.get("color"), "linetype": p.get("linetype"), "kinds": set()})
        r["n"] += 1
        r["kinds"].add(kind_of(t))
    res = []
    for k, r in out.items():
        g = styles.guess(k, r["kinds"])
        s = saved.get(k)
        res.append({"key": k, "n": r["n"], "color": r["color"],
                    "linetype": (r["linetype"] if r["linetype"] and r["linetype"] != "CONTINUOUS" else None),
                    "kinds": sorted(r["kinds"]), "becomes": s if styles.choice_ok(s) else g, "saved": styles.choice_ok(s)})
    return res


# --------------------------------------------------------------------------------------------------------- the site-grid fit
# a flat plane at the points on the WGS 84 ellipsoid (its two radii at their latitude): good to millimetres over a site.
EA, EE = 6378137.0, 0.00669437999014


def _plane(lat0):
    ph = math.radians(lat0)
    sn = 1 - EE * math.sin(ph) ** 2
    return EA * (1 - EE) / sn ** 1.5, EA / math.sqrt(sn) * math.cos(ph)


def fit(pairs):
    """
    pairs: [{"name", "x", "y" (the drawing's metres), "lon", "lat" (where it is)}], two or more. A similarity (turn,
    scale, shift; no stretch), least squares from three or more. Returns {turn, scale, worst, misses: [{name, m}],
    over (worst > MISS_LIMIT_M), scale_flag, f: drawing (x, y) -> [lon, lat]}.
    """
    if len(pairs) < 2:
        raise Refused("Place at least two survey points.")
    lon0 = sum(p["lon"] for p in pairs) / len(pairs)
    lat0 = sum(p["lat"] for p in pairs) / len(pairs)
    rm, rn = _plane(lat0)
    to_xy = lambda lon, lat: (math.radians(lon - lon0) * rn, math.radians(lat - lat0) * rm)
    pts = [(p["x"], p["y"]) + to_xy(p["lon"], p["lat"]) for p in pairs]
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    MX, MY = sum(p[2] for p in pts) / n, sum(p[3] for p in pts) / n
    sxx = a = b = 0.0
    for x, y, X, Y in pts:
        x, y, X, Y = x - mx, y - my, X - MX, Y - MY
        sxx += x * x + y * y
        a += x * X + y * Y
        b += x * Y - y * X
    if sxx < 1e-6:
        raise Refused("The survey points are on top of each other in the drawing. Pick points further apart.")
    a, b = a / sxx, b / sxx

    def f_xy(x, y):
        return a * (x - mx) - b * (y - my) + MX, b * (x - mx) + a * (y - my) + MY

    def f(x, y):
        X, Y = f_xy(x, y)
        return [round(lon0 + math.degrees(X / rn), 7), round(lat0 + math.degrees(Y / rm), 7)]

    misses = [{"name": p["name"], "m": round(math.hypot(f_xy(q[0], q[1])[0] - q[2], f_xy(q[0], q[1])[1] - q[3]), 3)}
              for p, q in zip(pairs, pts)]
    scale = math.hypot(a, b)
    worst = max(m["m"] for m in misses)
    return {"turn": round(math.degrees(math.atan2(b, a)), 2), "scale": round(scale, 5), "worst": round(worst, 3),
            "misses": misses, "points": n, "over": worst > MISS_LIMIT_M,
            "scale_flag": not (SCALE_BAND[0] <= scale <= SCALE_BAND[1]), "f": f}


def fit_words(ft):
    """The fit in one sentence (the page shows it; the import log keeps it)."""
    s = (f"Fitted from {ft['points']} points: the drawing turned {ft['turn']:.2f}°, scale {ft['scale']:.4f}, "
         f"worst miss {ft['worst']:.2f} m.")
    if ft["over"]:
        s += " A point misses by more than 1 m: check the points."
    elif ft["scale_flag"]:
        s += " The scale is not 1: check the drawing's units and the points."
    return s


def fitted(things, ft):
    """A site-grid drawing's things moved onto the map by a fit; each symbol and word turned by the fit's turn."""
    out = []
    for t in things:
        g, p = t["geometry"], dict(t["properties"])
        if g["type"] == "Point":
            ng = {"type": "Point", "coordinates": ft["f"](*g["coordinates"])}
        elif g["type"] == "LineString":
            ng = {"type": "LineString", "coordinates": [ft["f"](*c) for c in g["coordinates"]]}
        else:
            ng = {"type": "Polygon", "coordinates": [[ft["f"](*c) for c in r] for r in g["coordinates"]]}
        if "rot" in p:
            p["rot"] = round(p["rot"] - ft["turn"], 2)
        out.append({"geometry": ng, "properties": p})
    return out


def gate_checks(things, gates):
    """How far each of the drawing's gates lands from the nearest of the site's own gates: the page's check that the
    drawing is in the right place. things in WGS 84; gates [{name, lon, lat}]."""
    if not gates:
        return []
    out = []
    for t in things:
        p = t["properties"]
        if t["geometry"]["type"] != "Point":
            continue
        k = row_key(p)
        is_gate = styles.guess(k, {"Point"}) == "sym:gate" if (p.get("block") or p.get("sym_hint")) else False
        if not is_gate:
            continue
        c = t["geometry"]["coordinates"]
        g = min(gates, key=lambda g: metres(c, (g["lon"], g["lat"])))
        out.append({"thing": p.get("name") or p.get("block") or p.get("sym_hint") or "gate", "gate": g["name"],
                    "m": round(metres(c, (g["lon"], g["lat"])), 2)})
    return sorted(out, key=lambda r: r["m"])[:6]
