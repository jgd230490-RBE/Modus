"""A CONTRACTOR-STYLE logistics drawing for the demo's Tilton Viaduct site L019 (31 Oct 2026, 4c). John has no real
contractor DXF, and none with an open licence was found on the web. So this takes the tidy sample
(tilton-logistics-bng.dxf, made by make_l019_samples.py) and re-saves it the way a contractor's CAD office really
sends one. Everything is fictional; "Example Civils Ltd" is made up.

    contractor-style-mm.dxf          R2018, MILLIMETRES (National Grid x 1000), the usual UK CAD office habits
    contractor-style-r12-unitless.dxf R12 (AC1009), no units in the file at all, metres, an old export

What the mm file carries that the tidy sample does not (each is a thing the importer must survive):
  1  units mm ($INSUNITS 4), coordinates National Grid in mm, text heights in mm, $LTSCALE 500
  2  another office's layer names (TW_..., Z_..., EX_...)
  3  OS base mapping BOUND into the drawing (layers "OSBASE$0$...": buildings, field boundaries, road edges), one of
     its layers OFF and one FROZEN
  4  an unresolved XREF (the OS tile it was drawn on) inserted at 0,0
  5  the welfare cabins as BLOCKS whose lines are the cabin's footprint (32 ft x 10 ft), nested door block, one mirrored
  6  the gates as blocks with an ATTRIBUTE (GATE_NO), an anonymous dynamic block (*U), BYBLOCK colours
  7  polylines with arcs (bulges) and an elevation (87.5 m AOD), a 3D polyline survey string, survey POINTs + levels
  8  MTEXT with formatting codes, a LEADER, a WIPEOUT, an IMAGE (an aerial photo that is not sent), SOLID arrowheads
  9  a hatch with a hole (the lift zone round the crane pad), a gradient hatch, a custom linetype
 10  an A1 sheet border, title block and KEY drawn in MODEL space at 1:500, its key samples on the REAL layers
 11  a north arrow, a scale bar, a stray line from 0,0, duplicate overlapping hoarding lines

    python make_contractor_style.py <l019.json> --grid-dir <folder with the OSTN15 grid>
ezdxf 1.4.5 (MIT). Copied into backend/tools/ on 31 Oct 2026; the two drawings it writes are fixtures in backend/tests/fixtures/site_layouts/
"""
import argparse
import json
import math
import random

import ezdxf
from ezdxf.addons import Importer
from ezdxf.math import Matrix44

ap = argparse.ArgumentParser()
ap.add_argument("l019")
ap.add_argument("--grid-dir", required=True)
A = ap.parse_args()
random.seed(31)
MM = 1000.0
SRC = "tilton-logistics-bng.dxf"
RENAME = {
    "C-HAUL-ROAD": "TW_HAUL ROAD", "C-HAUL-ONEWAY": "TW_HAUL ROAD ONE WAY", "C-HOARDING": "TW_HOARDING 2.4m",
    "C-HERAS": "TW_HERAS", "C-BARRIER-RW": "TW_BARRIER", "C-PEDESTRIAN": "TW_PED ROUTE", "C-WELFARE": "TW_WELFARE",
    "C-PARKING": "TW_CAR PARK", "C-LOADING": "TW_LOADING BAY", "C-EXCLUSION": "TW_EXCLUSION ZONE",
    "C-CRANE-RADIUS": "TW_CRANE RADIUS", "C-DRAINAGE": "EX_DRAINAGE", "C-SYMBOLS": "TW_SYMBOLS", "C-TEXT": "Z_TEXT",
    "C-DIMS": "Z_DIMS",
}

src = ezdxf.readfile(SRC)
doc = ezdxf.new("R2018", setup=True)
doc.header["$INSUNITS"] = 4                 # millimetres
doc.header["$MEASUREMENT"] = 1
doc.header["$LTSCALE"] = 500.0
imp = Importer(src, doc)
imp.import_modelspace()
imp.import_tables(table_names=("layers", "linetypes"))
imp.finalize()
msp = doc.modelspace()

# ---------------------------------------------------------------- 1 + 2: millimetres and another office's layer names
S = Matrix44.scale(MM, MM, MM)
welfare = []
for e in list(msp):
    e.transform(S)
    if e.dxf.layer == "C-WELFARE":           # 5: the cabins become blocks (below), the polylines go
        welfare.append([(v[0], v[1]) for v in e.get_points("xy")])
        msp.delete_entity(e)
        continue
    e.dxf.layer = RENAME.get(e.dxf.layer, e.dxf.layer)
for old, new in RENAME.items():
    if old in doc.layers:
        doc.layers.get(old).rename(new)
# the blocks were drawn in metres: their contents to millimetres too, so a scale of 1 still means "as drawn"
for b in doc.blocks:
    if b.name.startswith("*") or b.name.startswith("_"):
        continue
    for e in b:
        e.transform(S)
for e in msp.query("INSERT"):
    e.dxf.xscale = e.dxf.yscale = e.dxf.zscale = 1.0     # the transform had set 1000
pts = [v for e in msp.query("LWPOLYLINE") for v in e.get_points("xy")]
cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
print("site centre (mm):", round(cx), round(cy))

L = doc.layers
L.add("TW_SYMBOLS", color=7) if "TW_SYMBOLS" not in L else None
L.add("TW_SECURITY", color=6)
L.add("Z_SHEET", color=8)
L.add("Z_TITLE", color=7)
L.add("Z_KEY", color=7)
L.add("SV_LEVELS", color=3)
L.add("SV_TOP OF BANK", color=3)
L.add("XREF", color=7)
L.add("IMAGES", color=7)

# 9: a custom linetype on the Heras (a complex type with an "H" in it), the gradient + hole further down
try:
    doc.linetypes.add("HERAS_TXT", pattern='A,4000,-750,["H",STANDARD,S=600,R=0.0,X=-250,Y=-300],-750',
                      description="Heras ----H----H----", length=5500)
    L.get("TW_HERAS").dxf.linetype = "HERAS_TXT"
except Exception as ex:                       # keep going: the plain FENCE type stays
    print("complex linetype not written:", ex)

# ---------------------------------------------------------------- 3: OS base mapping bound in (fictional linework)
for name, colour in (("OSBASE$0$Building", 8), ("OSBASE$0$Field Boundary", 9), ("OSBASE$0$Road Edge", 8),
                     ("OSBASE$0$Text", 8), ("OSBASE$0$Spot Heights", 8)):
    L.add(name, color=colour)
L.get("OSBASE$0$Text").off()
L.get("OSBASE$0$Spot Heights").freeze()
R = 600 * MM
for i in range(36):                          # field boundaries: wandering hedgerow lines
    x0, y0 = cx + random.uniform(-R, R), cy + random.uniform(-R, R)
    a = random.uniform(0, math.pi)
    line = [(x0 + k * 40 * MM * math.cos(a) + random.uniform(-3, 3) * MM, y0 + k * 40 * MM * math.sin(a) + random.uniform(-3, 3) * MM) for k in range(6)]
    msp.add_lwpolyline(line, dxfattribs={"layer": "OSBASE$0$Field Boundary"})
for i in range(40):                          # farm buildings, a hatched footprint each
    bx, by = cx + random.uniform(-R, R), cy + random.uniform(-R, R)
    if math.hypot(bx - cx, by - cy) < 180 * MM:
        continue
    w, h, a = random.uniform(8, 30) * MM, random.uniform(6, 15) * MM, math.radians(random.uniform(0, 90))
    c, s = math.cos(a), math.sin(a)
    ring = [(bx + x * c - y * s, by + x * s + y * c) for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
    msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "OSBASE$0$Building"})
    hh = msp.add_hatch(color=8, dxfattribs={"layer": "OSBASE$0$Building"})
    hh.paths.add_polyline_path(ring, is_closed=True)
for d in (-260, -252, 300, 308):             # two lanes' edges
    msp.add_lwpolyline([(cx - R, cy + d * MM + k) for k in (0,)] + [(cx + R, cy + d * MM + 40 * MM)], dxfattribs={"layer": "OSBASE$0$Road Edge"})
for i in range(15):
    msp.add_text("Tilton Lane" if i % 2 else "Drain", height=2500, dxfattribs={"layer": "OSBASE$0$Text",
                 "insert": (cx + random.uniform(-R, R), cy + random.uniform(-R, R))})
for i in range(25):
    p = (cx + random.uniform(-R, R), cy + random.uniform(-R, R))
    msp.add_point(p, dxfattribs={"layer": "OSBASE$0$Spot Heights"})
    msp.add_text(f"{random.uniform(80, 110):.1f}", height=1500, dxfattribs={"layer": "OSBASE$0$Spot Heights", "insert": p})

# ---------------------------------------------------------------- 4: the unresolved xref
doc.add_xref_def(r"..\Base\OS_SK7303.dwg", "OS_Base_SK7303")
msp.add_blockref("OS_Base_SK7303", (0, 0), dxfattribs={"layer": "XREF"})

# ---------------------------------------------------------------- 5: welfare cabins as footprint blocks
door = doc.blocks.new("DOOR_900")
door.add_line((0, 0), (900, 0), dxfattribs={"color": 0})
door.add_arc((0, 0), 900, 0, 90, dxfattribs={"color": 0})
cab = doc.blocks.new("WELFARE_UNIT_32x10")   # 32 ft x 10 ft, drawn in mm from its centre
cab.add_lwpolyline([(-4877, -1524), (4877, -1524), (4877, 1524), (-4877, 1524)], close=True, dxfattribs={"color": 0})
cab.add_line((-4877, -1524), (4877, 1524), dxfattribs={"color": 0})
cab.add_blockref("DOOR_900", (-3500, -1524))
cab.add_text("WELFARE", height=500, dxfattribs={"color": 0, "insert": (-1200, -200)})
for k, ring in enumerate(welfare):
    mx, my = sum(p[0] for p in ring[:4]) / 4, sum(p[1] for p in ring[:4]) / 4
    rot = math.degrees(math.atan2(ring[1][1] - ring[0][1], ring[1][0] - ring[0][0]))
    msp.add_blockref("WELFARE_UNIT_32x10", (mx, my), dxfattribs={"layer": "TW_WELFARE", "rotation": rot,
                     "xscale": -1.0 if k == 3 else 1.0, "color": 140})

# ---------------------------------------------------------------- 6: gate tags with an attribute, a dynamic block
tag = doc.blocks.new("GATE_TAG")
tag.add_circle((0, 0), 1500, dxfattribs={"color": 0})
tag.add_attdef("GATE_NO", (0, -400), dxfattribs={"height": 900, "color": 0})
gates = [e for e in msp.query("INSERT") if e.dxf.name == "GATE"]
for g, no in zip(gates, ("GATE 1 (IN)", "GATE 2 (OUT)")):
    p = g.dxf.insert
    br = msp.add_blockref("GATE_TAG", (p[0], p[1] - 12000), dxfattribs={"layer": "TW_SECURITY"})
    br.add_auto_attribs({"GATE_NO": no})
turn = doc.blocks.new_anonymous_block("U")   # what a dynamic block (turnstile, stretched) leaves in a DXF
turn.add_lwpolyline([(0, 0), (1200, 0), (1200, 2000), (0, 2000)], close=True)
turn.add_line((0, 1000), (1200, 1000))
g1 = gates[0].dxf.insert
msp.add_blockref(turn.name, (g1[0] + 8000, g1[1] + 3000), dxfattribs={"layer": "TW_SECURITY"})

# ---------------------------------------------------------------- 7: bulges, elevation, a 3D survey string, levels
road = msp.query('LWPOLYLINE[layer=="TW_HAUL ROAD"]').first
end = road.get_points("xy")[-1]
head = msp.add_lwpolyline([(end[0], end[1], 0, 0, 0), (end[0] + 9000, end[1], 0, 0, 1.0), (end[0] + 9000, end[1] + 12000, 0, 0, 0),
                           (end[0], end[1] + 12000, 0, 0, 0)], format="xyseb", dxfattribs={"layer": "TW_HAUL ROAD"})
head.dxf.elevation = 87500
head.dxf.const_width = 0
top = [(cx - 120000 + k * 20000, cy + 60000 + random.uniform(-2000, 2000), 88000 + k * 150) for k in range(12)]
msp.add_polyline3d(top, dxfattribs={"layer": "SV_TOP OF BANK"})
for k in range(20):
    p = (cx + random.uniform(-90000, 90000), cy + random.uniform(-60000, 60000), random.uniform(86000, 92000))
    msp.add_point(p, dxfattribs={"layer": "SV_LEVELS"})
    msp.add_text(f"+{p[2] / 1000:.2f}", height=1000, dxfattribs={"layer": "SV_LEVELS", "insert": (p[0] + 800, p[1])})

# ---------------------------------------------------------------- 8: MTEXT codes, leader, wipeout, image, solids
g = gates[0].dxf.insert
msp.add_mtext(r"{\fArial|b1|i0|c0|p34;SITE ACCESS}\PALL VEHICLES REPORT TO\P\LSECURITY\l", dxfattribs={
    "layer": "Z_TEXT", "insert": (g[0] - 30000, g[1] - 25000), "char_height": 1800, "width": 22000})
msp.add_leader([(g[0] - 9000, g[1] - 22000), (g[0] - 2000, g[1] - 4000)], dxfattribs={"layer": "Z_TEXT"})
msp.add_text("SECURITY GATEHOUSE", height=1500, dxfattribs={"layer": "Z_TEXT", "insert": (g[0] - 26000, g[1] - 23000)})
msp.add_wipeout([(g[0] - 31000, g[1] - 31000), (g[0] - 7000, g[1] - 19000)], dxfattribs={"layer": "Z_TEXT"})
img_def = doc.add_image_def(filename=r"..\Images\aerial_2026-06.jpg", size_in_pixel=(6000, 4000))
msp.add_image(img_def, insert=(cx - 300000, cy - 200000), size_in_units=(600000, 400000), dxfattribs={"layer": "IMAGES"})
loop = msp.query('LWPOLYLINE[layer=="TW_HAUL ROAD ONE WAY"]').first
lp = loop.get_points("xy")
for i in range(1, len(lp) - 1, 2):            # one-way arrows drawn as SOLIDs
    a, b = lp[i], lp[i + 1]
    ux, uy = (b[0] - a[0]), (b[1] - a[1])
    n = math.hypot(ux, uy) or 1
    ux, uy = ux / n * 3000, uy / n * 3000
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    msp.add_solid([(m[0] + ux, m[1] + uy), (m[0] - uy / 2, m[1] + ux / 2), (m[0] + uy / 2, m[1] - ux / 2)], dxfattribs={"layer": "TW_HAUL ROAD ONE WAY", "color": 30})

# ---------------------------------------------------------------- 9: the lift zone with the crane pad cut out, a gradient
ex = msp.query('HATCH[layer=="TW_EXCLUSION ZONE"]').first
# 31 Oct 2026: the pad is cut from the zone's own middle (it had been cut round the crane's insert, which sits BESIDE the
# zone, so the "hole" lay outside its area; the fixture was corrected in place to match)
ov = [v[:2] for v in ex.paths[0].vertices]
crane = (sum(v[0] for v in ov) / len(ov), sum(v[1] for v in ov) / len(ov))
pad = [(crane[0] - 3000, crane[1] - 3000), (crane[0] + 3000, crane[1] - 3000), (crane[0] + 3000, crane[1] + 3000), (crane[0] - 3000, crane[1] + 3000)]
ex.paths.add_polyline_path(pad, is_closed=True, flags=16)          # an inner path = a hole
park = msp.query('LWPOLYLINE[layer=="TW_CAR PARK"]').first
gh = msp.add_hatch(dxfattribs={"layer": "TW_CAR PARK"})
gh.paths.add_polyline_path(park.get_points("xy"), is_closed=True)
gh.set_gradient((200, 220, 255), (255, 255, 255), name="LINEAR")
for e in msp.query('LWPOLYLINE[layer=="TW_HOARDING 2.4m"]'):
    e.rgb = (0, 84, 147)                      # a brand blue as a true colour
    d = e.copy()                              # 11: copied twice by accident
    msp.add_entity(d)

# ---------------------------------------------------------------- 10: an A1 sheet at 1:500 in MODEL space
W, H = 841 * 500, 594 * 500                   # mm on the ground
x0, y0 = cx - W / 2, cy - H / 2
msp.add_lwpolyline([(x0, y0), (x0 + W, y0), (x0 + W, y0 + H), (x0, y0 + H)], close=True, dxfattribs={"layer": "Z_SHEET"})
tb = (x0 + W - 180 * 500, y0)
msp.add_lwpolyline([tb, (x0 + W, y0), (x0 + W, y0 + 60 * 500), (tb[0], y0 + 60 * 500)], close=True, dxfattribs={"layer": "Z_TITLE"})
for k, t in enumerate(("EXAMPLE CIVILS LTD (FICTIONAL)", "TILTON VIADUCT - TEMPORARY WORKS LOGISTICS PLAN",
                       "DRG No. TV-TW-LOG-001   REV C02", "SCALE 1:500 @ A1   DATE 31/10/26   DRAWN JB  CHKD RT")):
    msp.add_text(t, height=3.5 * 500, dxfattribs={"layer": "Z_TITLE", "insert": (tb[0] + 6 * 500, y0 + (48 - k * 12) * 500)})
kx, ky = x0 + 10 * 500, y0 + 10 * 500           # the KEY, bottom left, its samples on the real layers
msp.add_lwpolyline([(kx, ky), (kx + 120 * 500, ky), (kx + 120 * 500, ky + 80 * 500), (kx, ky + 80 * 500)], close=True, dxfattribs={"layer": "Z_KEY"})
msp.add_text("KEY", height=5 * 500, dxfattribs={"layer": "Z_KEY", "insert": (kx + 5 * 500, ky + 70 * 500)})
for k, (lay, words) in enumerate((("TW_HOARDING 2.4m", "2.4m SOLID HOARDING"), ("TW_HERAS", "HERAS FENCING"),
                                   ("TW_BARRIER", "RED/WHITE BARRIER"), ("TW_PED ROUTE", "PEDESTRIAN ROUTE"),
                                   ("TW_HAUL ROAD", "HAUL ROAD"))):
    yy = ky + (58 - k * 11) * 500
    msp.add_lwpolyline([(kx + 5 * 500, yy), (kx + 35 * 500, yy)], dxfattribs={"layer": lay})
    msp.add_text(words, height=2.5 * 500, dxfattribs={"layer": "Z_KEY", "insert": (kx + 40 * 500, yy - 1 * 500)})
msp.add_blockref("GATE", (kx + 20 * 500, ky + 4 * 500), dxfattribs={"layer": "TW_SYMBOLS"})
msp.add_text("SITE GATE", height=2.5 * 500, dxfattribs={"layer": "Z_KEY", "insert": (kx + 40 * 500, ky + 3 * 500)})

# ---------------------------------------------------------------- 11: north arrow, scale bar, the stray line
na = doc.blocks.new("NORTH_ARROW")
na.add_solid([(0, 6000), (-2000, -2000), (2000, -2000)])
na.add_text("N", height=2500, dxfattribs={"insert": (-800, 7000)})
msp.add_blockref("NORTH_ARROW", (x0 + W - 30 * 500, y0 + H - 40 * 500), dxfattribs={"layer": "Z_SHEET"})
for k in range(5):
    msp.add_lwpolyline([(x0 + W - 150 * 500 + k * 10000, y0 + 70 * 500), (x0 + W - 150 * 500 + (k + 1) * 10000, y0 + 70 * 500)],
                       dxfattribs={"layer": "Z_SHEET", "const_width": 800 if k % 2 == 0 else 0})
msp.add_text("0      10      20      30      40      50m", height=1250, dxfattribs={"layer": "Z_SHEET", "insert": (x0 + W - 150 * 500, y0 + 66 * 500)})
msp.add_line((0, 0), (1000, 1000), dxfattribs={"layer": "0"})
msp.add_text(".", height=250, dxfattribs={"layer": "0", "insert": (0, 0)})

doc.saveas("contractor-style-mm.dxf")
print("contractor-style-mm.dxf", len(msp), "model-space things")

# ---------------------------------------------------------------- the old export: R12, no units, metres
r12 = ezdxf.new("R12")
m12 = r12.modelspace()
for name in {e.dxf.layer for e in src.modelspace()}:
    lay = src.layers.get(name)
    if name not in r12.layers:
        r12.layers.add(RENAME.get(name, name), color=abs(lay.dxf.color))
for b in ("GATE", "MARSHAL", "SPEED_5", "WHEEL_WASH", "MOBILE_CRANE", "FIRST_AID", "FIRE_POINT", "ASSEMBLY", "PED_CROSSING", "TOILETS"):
    blk = r12.blocks.new(b)
    blk.add_circle((0, 0), 1.0)
for e in src.modelspace():
    lay = RENAME.get(e.dxf.layer, e.dxf.layer)
    t = e.dxftype()
    if t == "LWPOLYLINE":
        m12.add_polyline2d(list(e.get_points("xy")), close=e.closed, dxfattribs={"layer": lay})
    elif t == "CIRCLE":
        m12.add_circle(e.dxf.center, e.dxf.radius, dxfattribs={"layer": lay})
    elif t == "TEXT":
        m12.add_text(e.dxf.text, height=e.dxf.height, dxfattribs={"layer": lay, "insert": e.dxf.insert, "rotation": e.dxf.get("rotation", 0)})
    elif t == "INSERT":
        m12.add_blockref(e.dxf.name, e.dxf.insert, dxfattribs={"layer": lay, "rotation": e.dxf.get("rotation", 0)})
    elif t == "HATCH":                          # R12 has no HATCH: an old export leaves its outline only
        for p in ezdxf.path.from_hatch(e):
            m12.add_polyline2d([(v[0], v[1]) for v in p.flattening(0.05)], close=True, dxfattribs={"layer": lay})
    elif t == "SPLINE":                         # nor SPLINE: flattened to a polyline
        m12.add_polyline2d([(v[0], v[1]) for v in ezdxf.path.make_path(e).flattening(0.05)], dxfattribs={"layer": lay})
    # MTEXT and DIMENSION dropped, as R12 exports often do
r12.saveas("contractor-style-r12-unitless.dxf")
print("contractor-style-r12-unitless.dxf", len(m12), "things; $INSUNITS in header:", "$INSUNITS" in r12.header)
