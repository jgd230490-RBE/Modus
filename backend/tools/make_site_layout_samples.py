"""The import samples (30 Oct 2026, the 4c mockup; kept 31 Oct as backend/tests/fixtures/site_layouts/): ONE fictional
contractor's site logistics layout for the demo's Tilton Viaduct site (L019), drawn around the site's real demo records
(gates G020 / G021, areas A001-A004, internal roads Z029-Z032 from demo/uk-corridor.package.json, read only), written out
the ways a contractor might send it:

    tilton-logistics-bng.dxf        CAD, British National Grid (EPSG:27700) metres        -- the usual case
    tilton-logistics-site-grid.dxf  CAD, the same drawing in a local site grid + 3 survey control points
    tilton-logistics.kml / .kmz     Google Earth (folders = layers)
    tilton-logistics.geojson        GIS export, WGS 84 (RFC 7946), simplestyle colours
    tilton-logistics-shp.zip        GIS export, three shapefiles, .prj = EPSG:27700

    python backend/tools/make_site_layout_samples.py <l019.json> --grid-dir backend/data/proj

ezdxf 1.4.5, pyproj 3.8.0, pyshp 3.1.6 (all MIT), the versions in backend/requirements.txt.
"""
import argparse
import io
import json
import math
import zipfile

import ezdxf
import pyproj
import shapefile
from ezdxf.enums import TextEntityAlignment
from pyproj import Transformer

ap = argparse.ArgumentParser()
ap.add_argument("l019")
ap.add_argument("--grid-dir", required=True)
A = ap.parse_args()
pyproj.datadir.append_data_dir(A.grid_dir)
TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)
D = json.load(open(A.l019, encoding="utf-8"))
G = {g["id"]: g for g in D["gates"]}
AR = {a["id"]: json.loads(a["geometry"]) for a in D["areas"]}
Z = {z["id"]: json.loads(z["geometry"]) for z in D["zones"]}


def bng(lon, lat):
    e, n = TO_BNG.transform(lon, lat)
    return (round(e, 3), round(n, 3))


bng(-0.88, 52.64); print("WGS 84 -> BNG by:", TO_BNG.get_last_used_operation().description)


def line(coords):
    return [bng(*c) for c in coords]


def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return dx / L, dy / L


def offset_line(pts, d):
    """a polyline moved d metres to its left (simple mitre-free offset; good enough for a sample drawing)"""
    out = []
    for i, p in enumerate(pts):
        a, b = (pts[i - 1], p) if i else (p, pts[1])
        ux, uy = unit(a, b)
        out.append((round(p[0] - uy * d, 3), round(p[1] + ux * d, 3)))
    return out


def along(a, b, t):
    return (round(a[0] + (b[0] - a[0]) * t, 3), round(a[1] + (b[1] - a[1]) * t, 3))


def ang(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def rect(c, w, h, rot):
    r = math.radians(rot)
    cs, sn = math.cos(r), math.sin(r)
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(round(c[0] + x * cs - y * sn, 3), round(c[1] + x * sn + y * cs, 3)) for x, y in pts]


def grow(poly, d):
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    out = []
    for p in poly:
        vx, vy = p[0] - cx, p[1] - cy
        L = math.hypot(vx, vy)
        out.append((round(p[0] + vx / L * d * 1.414, 3), round(p[1] + vy / L * d * 1.414, 3)))
    return out


# ---------------------------------------------------------------- the layout, in BNG metres
g_in, g_out = bng(G["G020"]["lon"], G["G020"]["lat"]), bng(G["G021"]["lon"], G["G021"]["lat"])
top = line(Z["Z029"]["coordinates"])           # top road and terrace ramp (two-way)
spoil = line(Z["Z030"]["coordinates"])         # spoil spur
lay = line(Z["Z031"]["coordinates"])           # laydown spur
loop = line(Z["Z032"]["coordinates"])          # exit loop (one-way), past the wheel wash to the gate out
piers = line(AR["A001"]["coordinates"][0])[:-1]
deck = line(AR["A002"]["coordinates"][0])[:-1]
spoil_pt = bng(*AR["A003"]["coordinates"])
wash_pt = bng(*AR["A004"]["coordinates"])

# the site boundary along the south lane, through the gates, from 90 m east of gate in to 90 m west of gate out,
# a gap of 9 m at each gate
ux, uy = unit(g_out, g_in)                     # west -> east along the lane
nx, ny = -uy, ux                               # north of the lane
south = lambda p, d=0: (round(p[0] - nx * d, 3), round(p[1] - ny * d, 3))
b_e, b_w = south((g_in[0] + ux * 90, g_in[1] + uy * 90)), south((g_out[0] - ux * 90, g_out[1] - uy * 90))
gi, go = south(g_in), south(g_out)
gap = lambda p, s: (round(p[0] + ux * 4.5 * s, 3), round(p[1] + uy * 4.5 * s, 3))
hoarding = [[b_w, gap(go, -1)], [gap(go, 1), gap(gi, -1)], [gap(gi, 1), b_e]]
# up each side of the site to the north, 120 m
north = lambda p, d: (round(p[0] + nx * d, 3), round(p[1] + ny * d, 3))
hoarding[0].insert(0, north(b_w, 120))
hoarding[2].append(north(b_e, 120))

heras_deck = grow(deck, 6)
heras_deck_open = heras_deck[1:] + heras_deck[:1]           # opened at the laydown spur's end (south side)
heras_piers = grow(piers, 8)
crane_c = (round(sum(p[0] for p in piers) / 4, 3), round(sum(p[1] for p in piers) / 4, 3))
lift_zone = rect((crane_c[0] + 18, crane_c[1] - 6), 26, 16, ang(top[3], top[4]))
barrier = offset_line(top[2:5], -6.5)                       # the terrace ramp's drop side
ramp_note = along(top[3], top[4], 0.5)

wel_c = (g_in[0] + nx * 40 + ux * 30, g_in[1] + ny * 40 + uy * 30)
cabins = [rect((wel_c[0] + ux * 4 * i, wel_c[1] + uy * 4 * i), 3.0, 9.8, ang(g_out, g_in) + 90) for i in range(4)]
parking = rect((wel_c[0] + ux * 36, wel_c[1] + uy * 36 + 6), 30, 16, ang(g_out, g_in))
loading = rect(spoil_pt, 32, 14, ang(spoil[0], spoil[1]))
ped = [(wel_c[0] - ux * 6, wel_c[1] - uy * 6), along(top[1], top[2], 0.45), along(lay[0], lay[1], 0.35), (deck[0][0] + 6, deck[0][1] - 4)]
ped = [(round(x, 3), round(y, 3)) for x, y in ped]
drain = [north(along(top[0], top[1], 0.2), 14), north(along(top[1], top[2], 0.5), 18), north(along(top[2], top[3], 0.6), 16), north(top[3], 22)]

# ---------------------------------------------------------------- DXF (BNG)
LAYERS = [  # name, ACI colour, linetype
    ("C-HAUL-ROAD", 30, "CONTINUOUS"), ("C-HAUL-ONEWAY", 30, "CONTINUOUS"), ("C-HOARDING", 5, "CONTINUOUS"),
    ("C-HERAS", 8, "FENCE"), ("C-BARRIER-RW", 1, "DASHED"), ("C-PEDESTRIAN", 3, "DASHED"), ("C-WELFARE", 140, "CONTINUOUS"),
    ("C-PARKING", 160, "CONTINUOUS"), ("C-LOADING", 40, "CONTINUOUS"), ("C-EXCLUSION", 1, "CONTINUOUS"),
    ("C-CRANE-RADIUS", 1, "DASHED"), ("C-DRAINAGE", 4, "HIDDEN"), ("C-SYMBOLS", 7, "CONTINUOUS"), ("C-TEXT", 7, "CONTINUOUS"),
    ("C-DIMS", 2, "CONTINUOUS"),
]
BLOCKS = ["GATE", "MARSHAL", "SPEED_5", "WHEEL_WASH", "MOBILE_CRANE", "FIRST_AID", "FIRE_POINT", "ASSEMBLY", "PED_CROSSING", "TOILETS"]


def new_doc():
    doc = ezdxf.new("R2018", setup=True)            # setup=True adds DASHED, HIDDEN and the standard text styles
    doc.header["$INSUNITS"] = 6                      # metres
    doc.header["$MEASUREMENT"] = 1
    if "FENCE" not in doc.linetypes:
        doc.linetypes.add("FENCE", pattern=[3.5, 3.4, -0.1], description="Fence ----|----|----")
    for name, aci, lt in LAYERS:
        doc.layers.add(name, color=aci, linetype=lt)
    for b in BLOCKS:                                   # a simple drawn symbol per block, 1 m across: the import reads the
        blk = doc.blocks.new(b)                        # block NAME (and its rotation / scale), not what is drawn inside
        blk.add_circle((0, 0), 0.5)
        blk.add_text(b[:2], dxfattribs={"height": 0.4}).set_placement((0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    return doc


def write_dxf(path, X, control=None, title=""):
    """X(p) = the point in this drawing's coordinates"""
    doc = new_doc()
    msp = doc.modelspace()
    P = lambda pts: [X(p) for p in pts]
    msp.add_lwpolyline(P(top), dxfattribs={"layer": "C-HAUL-ROAD", "const_width": 7.0})
    msp.add_lwpolyline(P(spoil), dxfattribs={"layer": "C-HAUL-ROAD", "const_width": 6.0})
    msp.add_lwpolyline(P(lay), dxfattribs={"layer": "C-HAUL-ROAD", "const_width": 6.0})
    msp.add_lwpolyline(P(loop), dxfattribs={"layer": "C-HAUL-ONEWAY", "const_width": 4.5})
    for h in hoarding:
        msp.add_lwpolyline(P(h), dxfattribs={"layer": "C-HOARDING"})
    msp.add_lwpolyline(P(heras_deck_open), dxfattribs={"layer": "C-HERAS"})
    msp.add_lwpolyline(P(heras_piers), close=True, dxfattribs={"layer": "C-HERAS"})
    msp.add_lwpolyline(P(barrier), dxfattribs={"layer": "C-BARRIER-RW"})
    msp.add_lwpolyline(P(ped), dxfattribs={"layer": "C-PEDESTRIAN"})
    for c in cabins:
        msp.add_lwpolyline(P(c), close=True, dxfattribs={"layer": "C-WELFARE"})
    msp.add_lwpolyline(P(parking), close=True, dxfattribs={"layer": "C-PARKING"})
    msp.add_lwpolyline(P(loading), close=True, dxfattribs={"layer": "C-LOADING"})
    h = msp.add_hatch(color=1, dxfattribs={"layer": "C-EXCLUSION"})           # a hatched lift exclusion zone
    h.set_pattern_fill("ANSI31", scale=0.5)
    h.paths.add_polyline_path(P(lift_zone), is_closed=True)
    msp.add_circle(X(crane_c), 45.0, dxfattribs={"layer": "C-CRANE-RADIUS"})
    msp.add_spline(P(drain), dxfattribs={"layer": "C-DRAINAGE"})            # a ditch drawn as a spline
    # symbols (block inserts); rotation is DXF's: degrees anticlockwise from the drawing's x axis
    rot = lambda a, b: (ang(X(a), X(b)))
    lane = rot(g_out, g_in)
    ins = [("GATE", g_in, lane), ("GATE", g_out, lane), ("MARSHAL", north(g_in, 8), lane), ("MARSHAL", north(g_out, 8), lane),
           ("SPEED_5", north(along(top[0], top[1], 0.25), 6), lane), ("WHEEL_WASH", wash_pt, rot(loop[1], loop[2]) - 90),
           ("MOBILE_CRANE", crane_c, rot(piers[0], piers[1])), ("FIRST_AID", (wel_c[0] - ux * 8 + nx * 8, wel_c[1] - uy * 8 + ny * 8), 0),
           ("FIRE_POINT", (wel_c[0] - ux * 8 - nx * 2, wel_c[1] - uy * 8 - ny * 2), 0), ("TOILETS", (wel_c[0] + ux * 18, wel_c[1] + uy * 18), 0),
           ("ASSEMBLY", (parking[0][0] + nx * 22, parking[0][1] + ny * 22), 0), ("PED_CROSSING", along(top[1], top[2], 0.45), rot(top[1], top[2]) + 90)]
    for name, p, r in ins:
        msp.add_blockref(name, X(p), dxfattribs={"layer": "C-SYMBOLS", "rotation": r, "xscale": 1, "yscale": 1})
    # words
    T = lambda s, p, hgt, r=0.0: msp.add_text(s, dxfattribs={"layer": "C-TEXT", "height": hgt, "rotation": r}).set_placement(X(p), align=TextEntityAlignment.MIDDLE_CENTER)
    T("GATE 1 - IN", north(g_in, 18), 2.5, lane)
    T("GATE 2 - OUT", north(g_out, 18), 2.5, lane)
    T("DECK & LAYDOWN", (sum(p[0] for p in deck) / 4, sum(p[1] for p in deck) / 4), 4.0, lane)
    T("PIER BASES", (crane_c[0], crane_c[1] + 22), 4.0, lane)
    T("SPOIL LOADING", (spoil_pt[0], spoil_pt[1] - 12), 3.0, rot(spoil[0], spoil[1]) - 90)
    T("TERRACE RAMP - BARRIER ON DROP SIDE", ramp_note, 2.0, rot(top[3], top[4]))
    T("WELFARE", (wel_c[0] + ux * 6 + nx * 12, wel_c[1] + uy * 6 + ny * 12), 2.5, lane)
    msp.add_mtext("ALL DELIVERIES BOOKED - REPORT TO GATE 1\\PBANKSMAN FOR ALL REVERSING\\PSITE SPEED LIMIT 5 MPH",
                  dxfattribs={"layer": "C-TEXT", "char_height": 1.8, "rotation": lane}).set_location(X(north(along(g_in, b_e, 0.6), 48)))
    # a dimension (not drawn by Wayscope: counted as left out)
    d = msp.add_aligned_dim(p1=X(deck[0]), p2=X(deck[1]), distance=8, dxfattribs={"layer": "C-DIMS"})
    d.render()
    if control:                                                   # survey control points of a site-grid drawing
        doc.layers.add("SURVEY-CONTROL", color=6)
        for name, p in control:
            q = X(p)
            msp.add_point(q, dxfattribs={"layer": "SURVEY-CONTROL"})
            msp.add_text(f"{name}  E {q[0]:.3f}  N {q[1]:.3f}", dxfattribs={"layer": "SURVEY-CONTROL", "height": 1.5}).set_placement((q[0] + 2, q[1] + 2))
    # the title block lives in paper space: Wayscope reads model space only
    ps = doc.layout("Layout1")
    ps.add_text(title, dxfattribs={"height": 5}).set_placement((20, 20))
    doc.saveas(path)
    return doc


write_dxf("tilton-logistics-bng.dxf", lambda p: p, title="TV-LOG-001 rev C  Site logistics plan (FICTIONAL)  OSGB36 National Grid")

# the same drawing in a local site grid: origin 1000 / 2000 at gate 1, the grid turned 28.5 deg from National Grid
TH = math.radians(28.5)
SG = lambda p: (round(1000 + (p[0] - g_in[0]) * math.cos(TH) + (p[1] - g_in[1]) * math.sin(TH), 3),
                round(2000 - (p[0] - g_in[0]) * math.sin(TH) + (p[1] - g_in[1]) * math.cos(TH), 3))
CONTROL = [("CP1", g_in), ("CP2", g_out), ("CP3", piers[3])]
write_dxf("tilton-logistics-site-grid.dxf", SG, control=CONTROL, title="TV-LOG-001 rev C  Site logistics plan (FICTIONAL)  SITE GRID")
cp_truth = [{"name": n, "site_grid": SG(p), "bng": p} for n, p in CONTROL]
json.dump(cp_truth, open("site-grid-control.json", "w"), indent=1)

# ---------------------------------------------------------------- WGS 84 for the GIS formats
TO_LL = Transformer.from_crs(27700, 4326, always_xy=True)
ll = lambda p: [round(v, 7) for v in TO_LL.transform(*p)]
W = []   # (layer, name, geometry type, coordinates in WGS 84, style dict, symbol)
W += [("Haul roads", "Top road and terrace ramp", "LineString", [ll(p) for p in top], {"stroke": "#D97706", "stroke-width": 4}, None),
      ("Haul roads", "Spoil spur", "LineString", [ll(p) for p in spoil], {"stroke": "#D97706", "stroke-width": 4}, None),
      ("Haul roads", "Laydown spur", "LineString", [ll(p) for p in lay], {"stroke": "#D97706", "stroke-width": 4}, None),
      ("One-way", "Exit loop", "LineString", [ll(p) for p in loop], {"stroke": "#B45309", "stroke-width": 3}, None)]
W += [("Hoarding", f"Hoarding {i + 1}", "LineString", [ll(p) for p in h], {"stroke": "#1E3A8A", "stroke-width": 3}, None) for i, h in enumerate(hoarding)]
W += [("Heras fencing", "Deck laydown fence", "LineString", [ll(p) for p in heras_deck_open], {"stroke": "#6B7280", "stroke-width": 2}, None),
      ("Heras fencing", "Pier bases fence", "LineString", [ll(p) for p in heras_piers + heras_piers[:1]], {"stroke": "#6B7280", "stroke-width": 2}, None),
      ("Barriers", "Ramp barrier", "LineString", [ll(p) for p in barrier], {"stroke": "#DC2626", "stroke-width": 3}, None),
      ("Pedestrian route", "Welfare to deck", "LineString", [ll(p) for p in ped], {"stroke": "#16A34A", "stroke-width": 2}, None)]
W += [("Welfare", f"Cabin {i + 1}", "Polygon", [[ll(p) for p in c + c[:1]]], {"stroke": "#0E7490", "fill": "#67E8F9", "fill-opacity": 0.5}, None) for i, c in enumerate(cabins)]
W += [("Parking", "Staff parking", "Polygon", [[ll(p) for p in parking + parking[:1]]], {"stroke": "#4338CA", "fill": "#A5B4FC", "fill-opacity": 0.4}, None),
      ("Loading", "Spoil loading bay", "Polygon", [[ll(p) for p in loading + loading[:1]]], {"stroke": "#B45309", "fill": "#FCD34D", "fill-opacity": 0.45}, None),
      ("Exclusion", "Lift exclusion zone", "Polygon", [[ll(p) for p in lift_zone + lift_zone[:1]]], {"stroke": "#DC2626", "fill": "#FCA5A5", "fill-opacity": 0.45}, None)]
SYM = [("gate", "Gate 1 (in)", g_in), ("gate", "Gate 2 (out)", g_out), ("marshal", "Marshal", north(g_in, 8)), ("marshal", "Marshal", north(g_out, 8)),
       ("speed5", "5 mph", north(along(top[0], top[1], 0.25), 6)), ("wheelwash", "Wheel wash", wash_pt), ("mobilecrane", "Mobile crane", crane_c),
       ("first_aid", "First aid", (wel_c[0] - ux * 8 + nx * 8, wel_c[1] - uy * 8 + ny * 8)), ("fire_point", "Fire point", (wel_c[0] - ux * 8 - nx * 2, wel_c[1] - uy * 8 - ny * 2)),
       ("toilets", "Toilets", (wel_c[0] + ux * 18, wel_c[1] + uy * 18)), ("assembly", "Assembly point", (parking[0][0] + nx * 22, parking[0][1] + ny * 22))]
W += [("Signs and points", name, "Point", ll(p), {"marker-symbol": s}, s) for s, name, p in SYM]
W += [("Labels", t, "Point", ll(p), {}, None) for t, p in [("Deck and laydown", (sum(p[0] for p in deck) / 4, sum(p[1] for p in deck) / 4)),
                                                          ("Pier bases", (crane_c[0], crane_c[1] + 22)), ("Spoil loading", (spoil_pt[0], spoil_pt[1] - 12))]]

# GeoJSON (RFC 7946: WGS 84, lon / lat), simplestyle-spec colours as geojson.io and Mapbox write them
gj = {"type": "FeatureCollection", "name": "tilton-logistics", "features": [
    {"type": "Feature", "properties": {"layer": layer, "name": name, **st}, "geometry": {"type": gt, "coordinates": co}} for layer, name, gt, co, st, s in W]}
json.dump(gj, open("tilton-logistics.geojson", "w", encoding="utf-8"), indent=1)


# KML as Google Earth writes it: a folder per layer, a shared style per folder, colours aabbggrr
def kml_colour(hexc, a=1.0):
    h = hexc.lstrip("#")
    return f"{int(a * 255):02x}{h[4:6]}{h[2:4]}{h[0:2]}"


def kml_coords(gt, co):
    if gt == "Point":
        return f"{co[0]},{co[1]},0"
    pts = co if gt == "LineString" else co[0]
    return " ".join(f"{x},{y},0" for x, y in pts)


styles, folders = {}, {}
for layer, name, gt, co, st, s in W:
    sid = "s-" + (s or layer.lower().replace(" ", "-"))
    if sid not in styles:
        if gt == "Point" and s:
            styles[sid] = f'<Style id="{sid}"><IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/shapes/{s}.png</href></Icon></IconStyle></Style>'
        elif gt == "Point":
            styles[sid] = f'<Style id="{sid}"><IconStyle><scale>0</scale></IconStyle><LabelStyle><scale>1.1</scale></LabelStyle></Style>'
        else:
            ls = f'<LineStyle><color>{kml_colour(st.get("stroke", "#000000"))}</color><width>{st.get("stroke-width", 2)}</width></LineStyle>'
            ps = f'<PolyStyle><color>{kml_colour(st["fill"], st.get("fill-opacity", 0.5))}</color></PolyStyle>' if "fill" in st else ""
            styles[sid] = f'<Style id="{sid}">{ls}{ps}</Style>'
    geom = {"Point": "Point", "LineString": "LineString", "Polygon": "Polygon"}[gt]
    inner = f"<coordinates>{kml_coords(gt, co)}</coordinates>"
    if gt == "Polygon":
        inner = f"<outerBoundaryIs><LinearRing>{inner}</LinearRing></outerBoundaryIs>"
    folders.setdefault(layer, []).append(f"<Placemark><name>{name}</name><styleUrl>#{sid}</styleUrl><{geom}>{inner}</{geom}></Placemark>")
kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Tilton Viaduct site logistics (FICTIONAL)</name>'
       + "".join(styles.values()) + "".join(f"<Folder><name>{f}</name>{''.join(p)}</Folder>" for f, p in folders.items()) + "</Document></kml>\n")
open("tilton-logistics.kml", "w", encoding="utf-8").write(kml)
with zipfile.ZipFile("tilton-logistics.kmz", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("doc.kml", kml)

# Shapefiles (a GIS export): one file per geometry type, a LAYER / NAME / SYMBOL table, .prj in National Grid
TO_BNG2 = lambda c: list(TO_BNG.transform(*c))
prj = pyproj.CRS.from_epsg(27700).to_wkt(pyproj.enums.WktVersion.WKT1_ESRI)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for base, gt, shp_type in (("site_lines", "LineString", shapefile.POLYLINE), ("site_areas", "Polygon", shapefile.POLYGON), ("site_points", "Point", shapefile.POINT)):
        sh, sx, db = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=sh, shx=sx, dbf=db, shapeType=shp_type, encoding="utf-8")
        w.field("LAYER", "C", 30)
        w.field("NAME", "C", 60)
        w.field("SYMBOL", "C", 20)
        for layer, name, g2, co, st, s in W:
            if g2 != gt:
                continue
            if gt == "Point":
                w.point(*TO_BNG2(co))
            elif gt == "LineString":
                w.line([[TO_BNG2(c) for c in co]])
            else:
                ring = [TO_BNG2(c) for c in co[0]]
                if sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])) > 0:
                    ring.reverse()                      # a shapefile's outer ring runs clockwise
                w.poly([ring])
            w.record(layer, name, s or "")
        w.close()
        for ext, b in (("shp", sh), ("shx", sx), ("dbf", db)):
            z.writestr(f"{base}.{ext}", b.getvalue())
        z.writestr(f"{base}.prj", prj)
        z.writestr(f"{base}.cpg", "UTF-8")
open("tilton-logistics-shp.zip", "wb").write(buf.getvalue())
print("wrote 2 DXF, KML, KMZ, GeoJSON, shapefile zip;", len(W), "GIS features; control points:", cp_truth)
