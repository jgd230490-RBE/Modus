"""
site_layout_styles.py — the ONE style table of a site layout (task 4c, 31 Oct 2026; the mockup John approved,
notes site-layouts-mockup-1030).

Every thing on a layout names a style here: 11 line styles, 10 area styles, 31 symbols (plus text). The page and the
Route map draw from this table (served as JSON by GET /api/site-layouts/styles), and the 1:500 sheet (PR 5) will read
the same table, so the map and the paper can never disagree. A style the table does not hold is refused on save.

The symbols are drawn once here as SVG in a 64 x 64 box (none copied from a sign catalogue: the usual families — green
square = safe condition, red square = fire, blue disc = do this, yellow triangle = warning, red ring = a limit). GLYPHS
are the marks a line style draws (arrowheads, the lights, chevrons, cones, the walk / bike marks).

Sizes and widths are METRES on the ground (`w`, `size`), drawn true to scale and never thinner than a hairline.
Written by a script from the mockup's app.js and symbols.js; edit here from now on.
"""

#: the eight layers a thing sits on (the editor shows / hides / locks by layer)
LAYERS = ["Traffic management", "Pedestrians and cycles", "Areas", "Access", "Plant", "Welfare and safety",
          "Text and notes", "Imported"]

#: an area's fill
FILLS = {"solid": "Solid", "hatch": "Hatched", "cross": "Cross-hatched", "dots": "Dotted", "none": "No fill"}
OUTLINES = ("solid", "dashed")

#: line styles: label, layer, colour, width in metres
LINE_STYLES = {
    "barrier":  {"label": "Red / white barrier", "layer": "Traffic management", "color": "#DC2626", "w": 0.5},
    "heras":    {"label": "Heras fence", "layer": "Traffic management", "color": "#4B5563", "w": 0.12},
    "hoarding": {"label": "Solid hoarding", "layer": "Traffic management", "color": "#1E3A8A", "w": 0.3},
    "cones":    {"label": "Cones", "layer": "Traffic management", "color": "#F97316", "w": 0.3},
    "lights":   {"label": "Temporary lights", "layer": "Traffic management", "color": "#111827", "w": 3.5},
    "oneway":   {"label": "One-way traffic", "layer": "Traffic management", "color": "#F59E0B", "w": 3.5},
    "twoway":   {"label": "Two-way traffic", "layer": "Traffic management", "color": "#F59E0B", "w": 6.5},
    "ped":      {"label": "Pedestrian route", "layer": "Pedestrians and cycles", "color": "#16A34A", "w": 1.2},
    "cycle":    {"label": "Cycle route", "layer": "Pedestrians and cycles", "color": "#2563EB", "w": 1.2},
    "leader":   {"label": "Leader arrow", "layer": "Text and notes", "color": "#111827", "w": 0.15},
    "imported": {"label": "Imported line", "layer": "Imported", "color": "#6B7280", "w": 0.2},
}

#: area styles: label, colour, opacity, fill, edge, the words drawn in it
AREA_STYLES = {
    "exclusion":     {"label": "Exclusion zone", "color": "#DC2626", "opacity": 0.55, "fill": "hatch", "outline": "solid", "text": "EXCLUSION ZONE"},
    "laydown":       {"label": "Laydown", "color": "#2563EB", "opacity": 0.25, "fill": "solid", "outline": "solid", "text": "LAYDOWN"},
    "stockpile":     {"label": "Stockpile", "color": "#92400E", "opacity": 0.65, "fill": "dots", "outline": "solid", "text": "STOCKPILE"},
    "parking":       {"label": "Parking", "color": "#475569", "opacity": 0.25, "fill": "solid", "outline": "solid", "text": "P"},
    "loading":       {"label": "Loading bay", "color": "#CA8A04", "opacity": 0.75, "fill": "cross", "outline": "solid", "text": "LOADING BAY"},
    "welfare":       {"label": "Welfare compound", "color": "#16A34A", "opacity": 0.22, "fill": "solid", "outline": "solid", "text": "WELFARE"},
    "holding":       {"label": "Lorry holding", "color": "#7C3AED", "opacity": 0.2, "fill": "solid", "outline": "dashed", "text": "LORRY HOLDING"},
    "services":      {"label": "Buried services", "color": "#DB2777", "opacity": 0.5, "fill": "hatch", "outline": "dashed", "text": "BURIED SERVICES"},
    "crane_radius":  {"label": "Crane swing radius", "color": "#DC2626", "opacity": 0.07, "fill": "solid", "outline": "dashed", "text": ""},
    "imported_area": {"label": "Imported area", "color": "#6B7280", "opacity": 0.15, "fill": "solid", "outline": "solid", "text": ""},
}

#: the symbol groups -> the layer a symbol sits on
SYMBOL_LAYER = {"Access": "Access", "Plant": "Plant", "Welfare and safety": "Welfare and safety"}

#: symbols that never go on the public map, whatever a layout's switch says (Q7)
PRIVATE_SYMBOLS = ("security", "cctv")

#: the 31 symbols: key, label, group, size across in metres, SVG in a 64 x 64 box
SYMBOLS = [
    {"key": "gate", "label": "Site gate", "group": "Access", "size": 6,
     "svg": "<rect x=\"2\" y=\"26\" width=\"6\" height=\"22\" fill=\"#111\"/><rect x=\"56\" y=\"26\" width=\"6\" height=\"22\" fill=\"#111\"/><path d=\"M8 30 L31 22 L31 44 L8 44 Z M56 30 L33 22 L33 44 L56 44 Z\" fill=\"#F59E0B\" stroke=\"#111\" stroke-width=\"2.5\"/><path d=\"M12 34 L28 29 M12 40 L28 36 M52 34 L36 29 M52 40 L36 36\" stroke=\"#111\" stroke-width=\"2\"/>"},
    {"key": "marshal", "label": "Marshal / banksman", "group": "Access", "size": 3,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#F97316\" stroke=\"#fff\" stroke-width=\"3\"/><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#111\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#111\"/><path d=\"M22 30 h20 v4 h-20 z\" fill=\"#E5E7EB\"/>"},
    {"key": "stopgo", "label": "Stop / go board", "group": "Access", "size": 3,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#C8102E\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M4 32 A28 28 0 0 0 60 32 Z\" fill=\"#047857\"/><text x=\"32\" y=\"26\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"13\" text-anchor=\"middle\" fill=\"#fff\">STOP</text><text x=\"32\" y=\"49\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"13\" text-anchor=\"middle\" fill=\"#fff\">GO</text>"},
    {"key": "speed5", "label": "Speed limit 5 mph", "group": "Access", "size": 2.5,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"27\" fill=\"#fff\" stroke=\"#C8102E\" stroke-width=\"7\"/><text x=\"32\" y=\"43\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"30\" text-anchor=\"middle\" fill=\"#111\">5</text>"},
    {"key": "speed10", "label": "Speed limit 10 mph", "group": "Access", "size": 2.5,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"27\" fill=\"#fff\" stroke=\"#C8102E\" stroke-width=\"7\"/><text x=\"32\" y=\"41\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"26\" text-anchor=\"middle\" fill=\"#111\">10</text>"},
    {"key": "noentry", "label": "No entry", "group": "Access", "size": 2.5,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#C8102E\" stroke=\"#fff\" stroke-width=\"3\"/><rect x=\"12\" y=\"26\" width=\"40\" height=\"12\" fill=\"#fff\"/>"},
    {"key": "giveway", "label": "Give way", "group": "Access", "size": 2.5,
     "svg": "<path d=\"M4 8 H60 L32 58 Z\" fill=\"#fff\" stroke=\"#C8102E\" stroke-width=\"7\" stroke-linejoin=\"round\"/>"},
    {"key": "pedx", "label": "Pedestrian crossing", "group": "Access", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#1D4ED8\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M12 50 h40\" stroke=\"#fff\" stroke-width=\"4\"/><path d=\"M14 46 l8 -8 M24 46 l8 -8 M34 46 l8 -8 M44 46 l8 -8\" stroke=\"#fff\" stroke-width=\"4\"/><g transform=\"translate(14,4) scale(0.55)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g>"},
    {"key": "height", "label": "Height limit", "group": "Access", "size": 3,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"27\" fill=\"#fff\" stroke=\"#C8102E\" stroke-width=\"7\"/><path d=\"M32 11 l-6 8 h12 z M32 53 l-6 -8 h12 z\" fill=\"#111\"/><text x=\"32\" y=\"38\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"15\" text-anchor=\"middle\" fill=\"#111\">4.4m</text>"},
    {"key": "turning", "label": "Turning head", "group": "Access", "size": 5,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#1D4ED8\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M22 50 V30 A10 10 0 0 1 42 30 V40\" fill=\"none\" stroke=\"#fff\" stroke-width=\"6\"/><path d=\"M34 38 h16 l-8 12 z\" fill=\"#fff\"/>"},
    {"key": "delivery", "label": "Delivery / unloading point", "group": "Access", "size": 4,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#0F172A\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M10 22 h26 v18 h-26 z M36 28 h10 l6 7 v5 h-16 z\" fill=\"#FBBF24\"/><circle cx=\"18\" cy=\"44\" r=\"5\" fill=\"#FBBF24\"/><circle cx=\"44\" cy=\"44\" r=\"5\" fill=\"#FBBF24\"/>"},
    {"key": "wheelwash", "label": "Wheel wash", "group": "Access", "size": 6,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#0369A1\" stroke=\"#fff\" stroke-width=\"3\"/><circle cx=\"22\" cy=\"40\" r=\"9\" fill=\"none\" stroke=\"#fff\" stroke-width=\"5\"/><circle cx=\"44\" cy=\"40\" r=\"9\" fill=\"none\" stroke=\"#fff\" stroke-width=\"5\"/><path d=\"M16 12 q3 6 0 9 M28 10 q3 6 0 9 M40 12 q3 6 0 9 M52 10 q3 6 0 9\" stroke=\"#BAE6FD\" stroke-width=\"3\" fill=\"none\"/>"},
    {"key": "towercrane", "label": "Tower crane (base)", "group": "Plant", "size": 8,
     "svg": "<rect x=\"20\" y=\"20\" width=\"24\" height=\"24\" fill=\"#FBBF24\" stroke=\"#111\" stroke-width=\"3\"/><path d=\"M20 20 L44 44 M44 20 L20 44\" stroke=\"#111\" stroke-width=\"2.5\"/><path d=\"M2 32 H62\" stroke=\"#111\" stroke-width=\"5\"/><rect x=\"2\" y=\"28\" width=\"9\" height=\"8\" fill=\"#111\"/>"},
    {"key": "mobilecrane", "label": "Mobile crane", "group": "Plant", "size": 10,
     "svg": "<rect x=\"10\" y=\"20\" width=\"44\" height=\"24\" rx=\"3\" fill=\"#FBBF24\" stroke=\"#111\" stroke-width=\"3\"/><path d=\"M6 14 h8 v36 h-8 z M50 14 h8 v36 h-8 z\" fill=\"#475569\"/><path d=\"M28 32 L62 10\" stroke=\"#111\" stroke-width=\"5\"/><circle cx=\"28\" cy=\"32\" r=\"5\" fill=\"#111\"/>"},
    {"key": "lighttower", "label": "Lighting tower", "group": "Plant", "size": 3,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#0F172A\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M32 30 V56\" stroke=\"#FDE68A\" stroke-width=\"4\"/><rect x=\"18\" y=\"12\" width=\"28\" height=\"16\" rx=\"2\" fill=\"#FDE68A\"/><path d=\"M22 20 h20\" stroke=\"#0F172A\" stroke-width=\"2\"/>"},
    {"key": "generator", "label": "Generator", "group": "Plant", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#334155\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M36 10 L20 36 h12 l-4 18 l16 -26 h-12 z\" fill=\"#FDE047\"/>"},
    {"key": "fuel", "label": "Fuel bowser", "group": "Plant", "size": 4,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#B45309\" stroke=\"#fff\" stroke-width=\"3\"/><rect x=\"14\" y=\"16\" width=\"22\" height=\"34\" rx=\"3\" fill=\"#fff\"/><rect x=\"18\" y=\"20\" width=\"14\" height=\"10\" fill=\"#B45309\"/><path d=\"M36 22 h6 l6 6 v16 a4 4 0 0 1 -8 0 v-8 h-4\" fill=\"none\" stroke=\"#fff\" stroke-width=\"4\"/>"},
    {"key": "washout", "label": "Concrete wash-out", "group": "Plant", "size": 5,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#57534E\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M10 28 h44 l-6 22 h-32 z\" fill=\"#D6D3D1\"/><path d=\"M18 18 q4 -6 8 0 q4 6 8 0 q4 -6 8 0\" stroke=\"#fff\" stroke-width=\"4\" fill=\"none\"/>"},
    {"key": "welfare", "label": "Welfare cabin", "group": "Welfare and safety", "size": 6,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M12 30 L32 14 L52 30 V50 H12 Z\" fill=\"#fff\"/><rect x=\"27\" y=\"36\" width=\"10\" height=\"14\" fill=\"#047857\"/>"},
    {"key": "toilets", "label": "Toilets", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><g transform=\"translate(-9,6) scale(0.8)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g><g transform=\"translate(21,6) scale(0.8)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g><path d=\"M32 14 V54\" stroke=\"#fff\" stroke-width=\"2\"/>"},
    {"key": "water", "label": "Drinking water", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M32 10 C24 24 18 32 18 40 a14 14 0 0 0 28 0 C46 32 40 24 32 10 Z\" fill=\"#fff\"/>"},
    {"key": "first_aid", "label": "First aid", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M26 14 h12 v12 h12 v12 h-12 v12 h-12 v-12 h-12 v-12 h12 z\" fill=\"#fff\"/>"},
    {"key": "defib", "label": "Defibrillator", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M32 52 L12 32 a10 10 0 0 1 20 -14 a10 10 0 0 1 20 14 Z\" fill=\"#fff\"/><path d=\"M34 22 l-8 12 h8 l-4 10 l10 -14 h-8 l4 -8 z\" fill=\"#047857\"/>"},
    {"key": "assembly", "label": "Assembly point", "group": "Welfare and safety", "size": 4,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#047857\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M10 54 L22 42 M54 54 L42 42 M10 10 L22 22 M54 10 L42 22\" stroke=\"#fff\" stroke-width=\"4\"/><g transform=\"translate(14,12) scale(0.55)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g><g transform=\"translate(6,22) scale(0.42)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g><g transform=\"translate(31,22) scale(0.42)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M24 24 h16 l4 18 h-6 l-2 -10 v24 h-6 v-14 h-2 v14 h-6 v-24 l-2 10 h-6 z\" fill=\"#fff\"/></g>"},
    {"key": "fire_point", "label": "Fire point", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#C8102E\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M32 10 C38 20 46 26 44 38 C43 46 37 52 32 52 C24 52 18 46 19 38 C20 31 26 30 26 22 C30 26 30 30 33 31 C35 26 34 18 32 10 Z\" fill=\"#fff\"/>"},
    {"key": "spill", "label": "Spill kit", "group": "Welfare and safety", "size": 3,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#CA8A04\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M14 18 h36 v32 h-36 z\" fill=\"#fff\"/><text x=\"32\" y=\"32\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"12\" text-anchor=\"middle\" fill=\"#111\">SPILL</text><text x=\"32\" y=\"45\" font-family=\"Arial,Helvetica,sans-serif\" font-weight=\"700\" font-size=\"12\" text-anchor=\"middle\" fill=\"#111\">KIT</text>"},
    {"key": "ppe", "label": "PPE to be worn", "group": "Welfare and safety", "size": 3,
     "svg": "<circle cx=\"32\" cy=\"32\" r=\"28\" fill=\"#1D4ED8\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M14 36 a18 16 0 0 1 36 0 Z\" fill=\"#fff\"/><rect x=\"10\" y=\"36\" width=\"44\" height=\"6\" rx=\"2\" fill=\"#fff\"/>"},
    {"key": "warning", "label": "Warning (general)", "group": "Welfare and safety", "size": 3,
     "svg": "<path d=\"M32 5 L60 56 H4 Z\" fill=\"#FFD100\" stroke=\"#111\" stroke-width=\"4\" stroke-linejoin=\"round\"/><rect x=\"29\" y=\"22\" width=\"6\" height=\"18\" fill=\"#111\"/><circle cx=\"32\" cy=\"47\" r=\"3.5\" fill=\"#111\"/>"},
    {"key": "security", "label": "Security cabin", "group": "Welfare and safety", "size": 4,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#1E293B\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M32 10 L50 16 V30 C50 42 42 50 32 54 C22 50 14 42 14 30 V16 Z\" fill=\"#fff\"/><path d=\"M24 31 l6 6 l11 -12\" stroke=\"#1E293B\" stroke-width=\"4\" fill=\"none\"/>"},
    {"key": "cctv", "label": "CCTV", "group": "Welfare and safety", "size": 2.5,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#1E293B\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M10 22 L42 14 L46 28 L14 36 Z\" fill=\"#fff\"/><path d=\"M36 30 l4 12 h12\" stroke=\"#fff\" stroke-width=\"4\" fill=\"none\"/>"},
    {"key": "skip", "label": "Skip / waste", "group": "Welfare and safety", "size": 5,
     "svg": "<rect x=\"4\" y=\"4\" width=\"56\" height=\"56\" rx=\"6\" fill=\"#57534E\" stroke=\"#fff\" stroke-width=\"3\"/><path d=\"M8 24 h48 l-6 24 h-36 z\" fill=\"#FBBF24\" stroke=\"#111\" stroke-width=\"2\"/><path d=\"M20 30 l-2 12 M32 30 v12 M44 30 l2 12\" stroke=\"#111\" stroke-width=\"2\"/>"},
]
SYMBOL_KEYS = {s["key"]: s for s in SYMBOLS}

#: the marks the line styles draw (arrowheads, chevrons, cones, the lights, the walk / bike marks), 64 x 64 SVG
GLYPHS = {
    "chev": "<path d=\"M18 14 L46 32 L18 50\" fill=\"none\" stroke=\"#fff\" stroke-width=\"9\" stroke-linejoin=\"round\"/><path d=\"M18 14 L46 32 L18 50\" fill=\"none\" stroke=\"#111\" stroke-width=\"5\" stroke-linejoin=\"round\"/>",
    "head": "<path d=\"M8 10 L60 32 L8 54 L18 32 Z\" fill=\"#111\" stroke=\"#fff\" stroke-width=\"3\" stroke-linejoin=\"round\"/>",
    "headw": "<path d=\"M8 10 L60 32 L8 54 L18 32 Z\" fill=\"#fff\" stroke=\"#111\" stroke-width=\"3\" stroke-linejoin=\"round\"/>",
    "cone": "<path d=\"M32 6 L46 52 H18 Z\" fill=\"#F97316\" stroke=\"#7C2D12\" stroke-width=\"2\"/><path d=\"M26 26 h12 l2 8 h-16 z\" fill=\"#fff\"/><rect x=\"12\" y=\"52\" width=\"40\" height=\"6\" rx=\"2\" fill=\"#111\"/>",
    "walk": "<circle cx=\"32\" cy=\"32\" r=\"26\" fill=\"#16A34A\" stroke=\"#fff\" stroke-width=\"3\"/><g transform=\"translate(9,9) scale(0.72)\"><circle cx=\"32\" cy=\"15\" r=\"6\" fill=\"#fff\"/><path d=\"M28 24 h8 l6 12 l-5 2 l-4 -6 v8 l6 14 h-6 l-5 -11 l-4 11 h-6 l6 -15 v-10 l-4 6 l-5 -2 z\" fill=\"#fff\"/></g>",
    "bike": "<circle cx=\"32\" cy=\"32\" r=\"26\" fill=\"#2563EB\" stroke=\"#fff\" stroke-width=\"3\"/><circle cx=\"21\" cy=\"38\" r=\"7\" fill=\"none\" stroke=\"#fff\" stroke-width=\"3.5\"/><circle cx=\"43\" cy=\"38\" r=\"7\" fill=\"none\" stroke=\"#fff\" stroke-width=\"3.5\"/><path d=\"M21 38 L29 26 H39 L43 38 M29 26 L33 38 H21 M36 22 h6\" fill=\"none\" stroke=\"#fff\" stroke-width=\"3.5\"/>",
    "lights": "<rect x=\"20\" y=\"4\" width=\"24\" height=\"56\" rx=\"6\" fill=\"#111\" stroke=\"#fff\" stroke-width=\"3\"/><circle cx=\"32\" cy=\"16\" r=\"6\" fill=\"#EF4444\"/><circle cx=\"32\" cy=\"32\" r=\"6\" fill=\"#F59E0B\"/><circle cx=\"32\" cy=\"48\" r=\"6\" fill=\"#22C55E\"/>",
    "post": "<rect x=\"22\" y=\"22\" width=\"20\" height=\"20\" fill=\"#374151\" stroke=\"#fff\" stroke-width=\"3\"/>",
    "pin": "<circle cx=\"32\" cy=\"32\" r=\"14\" fill=\"#fff\" stroke=\"#1D4ED8\" stroke-width=\"6\"/>",
}


def svg_doc(inner):
    """A symbol or glyph as a whole SVG document (128 px, the 64 box)."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="128" height="128">{inner}</svg>'


#: what an import row can become: "line:<style>", "area:<style>", "sym:<symbol>", "text" or "skip"
def choices():
    return ([f"line:{k}" for k in LINE_STYLES] + [f"area:{k}" for k in AREA_STYLES] + ["text"]
            + [f"sym:{s['key']}" for s in SYMBOLS] + ["skip"])


def choice_ok(v):
    return isinstance(v, str) and v in set(choices())


def choice_label(v):
    """The words a person reads for a choice (the mapping table's select)."""
    k, _, s = (v or "").partition(":")
    if k == "line" and s in LINE_STYLES:
        return "Line · " + LINE_STYLES[s]["label"]
    if k == "area" and s in AREA_STYLES:
        return "Area · " + AREA_STYLES[s]["label"]
    if k == "sym" and s in SYMBOL_KEYS:
        return "Symbol · " + SYMBOL_KEYS[s]["label"]
    return {"text": "Text", "skip": "Leave out"}.get(v, v)


#: a first guess for a source layer / block / symbol nobody has mapped yet, by words in its name (upper case,
#: first match wins). The organisation's saved table always wins over a guess.
GUESS_LAYER = [
    (("EXCLUSION",), "area:exclusion"), (("CRANE", "RADIUS"), "area:crane_radius"), (("SWING",), "area:crane_radius"),
    (("ONE", "WAY"), "line:oneway"), (("ONEWAY",), "line:oneway"), (("HERAS",), "line:heras"), (("FENC",), "line:heras"),
    (("HOARD",), "line:hoarding"), (("BARRIER",), "line:barrier"), (("CONE",), "line:cones"), (("LIGHTS",), "line:lights"),
    (("PEDESTRIAN",), "line:ped"), (("PED",), "line:ped"), (("FOOT",), "line:ped"), (("CYCLE",), "line:cycle"),
    (("WELFARE",), "area:welfare"), (("CABIN",), "area:welfare"), (("PARK",), "area:parking"),
    (("LOADING",), "area:loading"), (("UNLOAD",), "area:loading"), (("LAYDOWN",), "area:laydown"),
    (("STOCKPILE",), "area:stockpile"), (("HOLDING",), "area:holding"), (("SERVICE",), "area:services"),
    (("HAUL",), "line:twoway"), (("ROAD",), "line:twoway"), (("TEXT",), "text"), (("LABEL",), "text"),
    (("NOTE",), "text"), (("DIM",), "skip"),
    # 31 Oct 2026 (the mockup's LAYER_WORDS, checked on two contractor-style drawings): more of a CAD office's words
    (("LIFT", "ZONE"), "area:exclusion"), (("CRANE",), "area:crane_radius"), (("WALK",), "line:ped"),
    (("OFFICE",), "area:welfare"), (("CANTEEN",), "area:welfare"), (("DRAIN",), "skip"), (("EXIST",), "skip"),
    (("LEVEL",), "skip"),
]
GUESS_SYMBOL = [
    (("WHEEL",), "wheelwash"), (("WASH", "OUT"), "washout"), (("WASHOUT",), "washout"), (("GATE",), "gate"),
    (("MARSHAL",), "marshal"), (("BANKSMAN",), "marshal"), (("STOP",), "stopgo"), (("10",), "speed10"),
    (("5",), "speed5"), (("SPEED",), "speed5"), (("NO", "ENTRY"), "noentry"), (("NOENTRY",), "noentry"),
    (("GIVE",), "giveway"), (("CROSSING",), "pedx"), (("HEIGHT",), "height"), (("TURN",), "turning"),
    (("DELIVER",), "delivery"), (("TOWER", "CRANE"), "towercrane"), (("CRANE",), "mobilecrane"),
    (("LIGHT",), "lighttower"), (("GENERATOR",), "generator"), (("FUEL",), "fuel"), (("WELFARE",), "welfare"),
    (("TOILET",), "toilets"), (("WC",), "toilets"), (("WATER",), "water"), (("FIRST", "AID"), "first_aid"),
    (("FIRST_AID",), "first_aid"), (("DEFIB",), "defib"), (("ASSEMBLY",), "assembly"), (("FIRE",), "fire_point"),
    (("SPILL",), "spill"), (("PPE",), "ppe"), (("SECURITY",), "security"), (("CCTV",), "cctv"), (("SKIP",), "skip"),
    (("WASTE",), "skip"),
    (("BANKS",), "marshal"), (("MUSTER",), "assembly"), (("MPH",), "speed5"),
]


def _words(name):
    import re
    return re.sub(r"[^A-Z0-9]+", " ", str(name or "").upper().replace("-", " ").replace("_", " "))


def guess(key, kinds):
    """
    The first guess for one row of the mapping table. `key` is the row's key ("block GATE", "symbol first_aid", or a
    layer name); `kinds` the shapes on that row ({"Point", "LineString", "Polygon"} and "Text" for words).
    """
    kinds = set(kinds or ())
    if key.startswith("outline "):              # a footprint block (a cabin drawn as a block): an area by its name
        key, kinds = key.split(" ", 1)[1], {"Polygon"}
    elif key.startswith("block ") or key.startswith("symbol "):
        name = key.split(" ", 1)[1]
        if name in SYMBOL_KEYS:
            return "sym:" + name
        w = " " + _words(name) + " "
        if any(" " + n + " " in w for n in ("TAG", "LABEL", "TITLE")):   # a block that carries words (GATE_TAG)
            return "text"
        for need, sym in GUESS_SYMBOL:
            if all((" " + n + " " in w) if n.isdigit() else (n in w) for n in need):
                return "sym:" + sym
        return "sym:warning"
    w = _words(key)
    if w.startswith("EX ") or w.startswith("SV ") or "EXIST" in w:   # existing features and survey: not the logistics plan
        return "skip"
    if kinds == {"Text"}:
        return "text"
    for need, ch in GUESS_LAYER:
        if all(n in w for n in need):
            if ch.startswith("area:") and "Polygon" not in kinds and "LineString" not in kinds:
                continue
            if ch == "text" and not kinds <= {"Text", "Point"}:
                continue
            return ch
    if kinds and kinds <= {"Polygon"}:
        return "area:imported_area"
    if kinds and kinds <= {"Text"}:
        return "text"
    if kinds and kinds <= {"Point"}:
        return "sym:warning"
    return "line:imported"


def payload():
    """The table as the page and the Route map read it (GET /api/site-layouts/styles)."""
    return {
        "layers": LAYERS, "fills": FILLS,
        "lines": [{"key": k, **v} for k, v in LINE_STYLES.items()],
        "areas": [{"key": k, **v} for k, v in AREA_STYLES.items()],
        "symbols": [{**s, "layer": SYMBOL_LAYER[s["group"]]} for s in SYMBOLS],
        "glyphs": GLYPHS,
        "choices": [{"value": c, "label": choice_label(c)} for c in choices()],
        "private_symbols": list(PRIVATE_SYMBOLS),
    }
