"""
The route-line table, 27 Nov 2026 (the route lines plan's group 1) — branch claude/route-line-spec.

WHAT IS ASSERTED
----------------
  1. TODAY'S VALUES, as literals: every role on every surface (PINNED below, read off `main` before the move), the band
     blues and the surfaces. A change to a value fails here first: changing one is a decision with its own mockup.
  2. The generated copies: each page carries the table's copy as the FIRST statement of its main script and the custom
     properties just before `</head>`, both exactly what `route_line_styles_build.py` writes now (a stale page fails);
     the copy holds that page's surfaces only; the build is deterministic.
  3. THE GUARD, on the two pages: every route-line layer (the ids listed) is found and carries no colour literal; every
     other line layer with a colour literal is a known non-route one, at most as many as today (the ceiling may only come
     down); no setPaintProperty writes a colour literal; the strays that are not route lines but look like one are
     pinned with a ceiling (the Routes labels' picked edge); the dead colours are gone (`ROUTE_COLOR` "#2563EB" in the
     app, `COLORS.forecast`, `forecastCasing` and `selection` in the map's config).
  4. THE GUARD, on the five Python modules: each named route-line constant is read from the table on its own line (no
     colour literal on that line) and equals the table's value.
  5. Every key's words on a page are the table's (the public map's legend, the Routes key, the week map's key, the
     Simulation's key), and each key sample on the public map and the week map reads the table's custom property.
  6. The readers: spec / get / surface_roles / page_surfaces / css_var / all_colours.

WHAT THIS DOES NOT PROVE
------------------------
  * That a page DRAWS what the table says: the pages' own harnesses (parse_map, parse_frontend, map_lines_*,
    ui_fix_routes_*) pin each read, and the before / after pictures in notes\\route-lines-build-1126\\spec\\ show nothing
    moved. No browser runs here.
  * Labels, badges and text near a line (a haul road's name, the cap badge) are not route lines and are not guarded.

Run:  python backend/tests/test_route_line_styles.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "tools"))

PASS = FAIL = 0


def ok(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL += 1
        print("  FAIL", label, ("  " + str(extra)[:600]) if extra else "")


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


import route_line_styles as R          # noqa: E402
import route_line_styles_build as B    # noqa: E402

# today's values (27 Nov 2026), read off the code on `main` before the move: a literal, so a change to the table fails here
PINNED = {'loaded_leg': {'public_map': {'color': '#3A3C41',
                               'color_dark': '#D4D6DA',
                               'width': ['interpolate', ['linear'], ['zoom'], 7, 1.1, 12, 2.6, 16, 4.6],
                               'offset': ['interpolate', ['linear'], ['zoom'], 7, -1, 12, -4, 14, -3, 17, 0],
                               'casing': '#ffffff',
                               'casing_dark': '#1F2024',
                               'casing_width': ['interpolate', ['linear'], ['zoom'], 7, 2.9, 12, 4.8, 16, 7],
                               'cap': 'round',
                               'key': 'Laden (out)'},
                'routes_map': {'color': '#3A3C41',
                               'color_dark': '#D4D6DA',
                               'width': 3,
                               'offset': ['interpolate', ['linear'], ['zoom'], 9, -2.2, 14, -4.5],
                               'casing': '#ffffff',
                               'casing_dark': '#1F2024',
                               'casing_width': 5,
                               'casing_opacity': 0.85,
                               'emphasis': {'locations': {'width': 2, 'opacity': 0.45, 'casing_opacity': 0.3},
                                            'routes': {'width': 3, 'opacity': 1.0, 'casing_opacity': 0.85},
                                            'zones': {'width': 2, 'opacity': 0.55, 'casing_opacity': 0.35}},
                               'dim_factor': 0.3,
                               'key': 'Out'},
                'commit_map': {'color': '#3A3C41',
                               'width': 4,
                               'offset': ['interpolate', ['linear'], ['zoom'], 8, -1.5, 12, -4],
                               'casing': '#ffffff',
                               'casing_width': 6.5,
                               'casing_opacity': 0.9,
                               'key': 'Out (loaded)',
                               'key_today': 'Today, out (loaded)'},
                'plan': {'color': '#0051C4',
                         'width': 2.2,
                         'casing': '#ffffff',
                         'casing_extra': 1.4,
                         'offset': 1.5,
                         'keyline': '#1F2024',
                         'keyline_extra': 0.4,
                         'key': 'Laden (out)'},
                'route_sheet': {'color': '#0051C4',
                                'width': 2.8,
                                'casing': '#ffffff',
                                'casing_extra': 1.6,
                                'offset': 1.8,
                                'key': 'Loaded, A to B'},
                'route_analysis': {'color': '#0051C4',
                                   'width': 2.4,
                                   'width_section_f': 2.4,
                                   'key': 'Out, loaded, A to B'}},
 'empty_leg': {'public_map': {'color': '#8E9197',
                              'color_dark': '#9A9DA3',
                              'width': ['interpolate', ['linear'], ['zoom'], 7, 1.1, 12, 2.6, 16, 4.6],
                              'offset': ['interpolate', ['linear'], ['zoom'], 7, -1, 12, -4, 14, -3, 17, 0],
                              'casing': '#ffffff',
                              'casing_dark': '#1F2024',
                              'casing_width': ['interpolate', ['linear'], ['zoom'], 7, 2.9, 12, 4.8, 16, 7],
                              'cap': 'round',
                              'key': 'Empty (return)'},
               'routes_map': {'color': '#8E9197',
                              'color_dark': '#9A9DA3',
                              'width': 3,
                              'offset': ['interpolate', ['linear'], ['zoom'], 9, -2.2, 14, -4.5],
                              'casing': '#ffffff',
                              'casing_dark': '#1F2024',
                              'casing_width': 5,
                              'casing_opacity': 0.85,
                              'key': 'Back'},
               'commit_map': {'color': '#8E9197',
                              'width': 2.5,
                              'offset': ['interpolate', ['linear'], ['zoom'], 8, -1.5, 12, -4],
                              'casing': '#ffffff',
                              'casing_width': 5,
                              'casing_opacity': 0.9,
                              'key_height': 3,
                              'key_today': 'Today, back (empty)'},
               'plan': {'color': '#72A7FF',
                        'width': 2.2,
                        'casing': '#ffffff',
                        'casing_extra': 1.4,
                        'offset': 1.5,
                        'key': 'Empty (return)'},
               'route_sheet': {'color': '#72A7FF',
                               'width': 2.8,
                               'casing': '#ffffff',
                               'casing_extra': 1.6,
                               'offset': 1.8,
                               'key': 'Empty, back to A'},
               'route_analysis': {'color': '#72A7FF',
                                  'thinner': 0.3,
                                  'offset': 3.0,
                                  'width_section_f': 2.1,
                                  'key': 'Back, empty, B to A'}},
 'later_this_week': {'commit_map': {'color': '#C6C8CC',
                                    'color_dark': '#7D8087',
                                    'width': 2,
                                    'opacity': 0.9,
                                    'key': 'Later this week'}},
 'quiet_route': {'public_map': {'color': '#A9ABB0',
                                'color_dark': '#6B6E74',
                                'width': ['interpolate', ['linear'], ['zoom'], 7, 1, 12, 2, 16, 3.4],
                                'casing_width': ['interpolate', ['linear'], ['zoom'], 7, 2.6, 12, 4, 16, 5.6],
                                'offset': 0}},
 'alternative': {'public_map': {'color': '#A9ABB0',
                                'color_dark': '#7D8087',
                                'opacity': 0.9,
                                'width': ['interpolate', ['linear'], ['zoom'], 7, 0.6, 12, 1.2, 16, 2],
                                'key': 'Alternative routes'},
                 'routes_map': {'color': '#8E9197',
                                'color_dark': '#7D8087',
                                'width': 2.4,
                                'opacity': 1,
                                'casing': '#ffffff',
                                'casing_dark': '#1F2024',
                                'casing_width': 5.4,
                                'key': 'Alternative'},
                 'collision_map': {'color': '#71717A', 'width': 1.8}},
 'haul_stretch': {'public_map': {'width': ['interpolate', ['linear'], ['zoom'], 7, 1.1, 12, 2.4, 16, 3.8],
                                 'dash': [0, 2.2],
                                 'eraser': '#ffffff',
                                 'eraser_dark': '#1F2024'},
                  'route_sheet': {'width': 1.7, 'gap': 4.4},
                  'simulation_map': {'color': '#7C3AED',
                                     'app_var': '--chart-4',
                                     'width': 4,
                                     'dash': [1.5, 1],
                                     'key_width': 3,
                                     'key': 'Haul road (assigned speed)'}},
 'temporary_haul': {'public_map': {'color': '#C2790B',
                                   'width': ['interpolate', ['linear'], ['zoom'], 7, 1.2, 12, 2.6],
                                   'opacity': 0.55,
                                   'key': 'Temporary haul'}},
 'month_line': {'public_map': {'color': '#0B4EA2',
                               'bands': ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'],
                               'no_value': '#A8A29E',
                               'width': 4,
                               'casing': '#FFFFFF',
                               'casing_dark': '#E7E5E4',
                               'casing_width': 6.6,
                               'council': '#A8A29E',
                               'council_width': 2},
                'bulletin': {'bands': ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'],
                             'width': 2.2,
                             'casing': '#1F2024',
                             'casing_width': 3.4},
                'bulletin_web': {'bands': ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'],
                                 'width': 5,
                                 'casing': '#1F2024',
                                 'casing_width': 7.5,
                                 'casing_opacity': 0.9},
                'plan': {'color': '#0051C4'},
                'clp_regional': {'bands': ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'],
                                 'no_lines': '#9CA3AF',
                                 'no_lines_key': 'No approved lines yet'}},
 'shared_section': {'public_map': {'color': '#0B4EA2', 'casing': '#FFFFFF'},
                    'bulletin': {'width': 2.2, 'casing': '#1F2024', 'casing_width': 3.4}},
 'flow_arrow': {'public_map': {'fill': '#ffffff',
                               'ring': '#00215B',
                               'ring_width': 0.8,
                               'gap': 90,
                               'speed': 13,
                               'length': 5.2,
                               'side': 2.7}},
 'pick': {'public_map': {'color': '#1F2024',
                         'color_dark': '#F5F5F4',
                         'casing': '#ffffff',
                         'casing_dark': '#1F2024',
                         'width': ['interpolate', ['linear'], ['zoom'], 7, 2, 12, 4.2, 16, 6.6],
                         'casing_width': ['interpolate', ['linear'], ['zoom'], 7, 4.4, 12, 6.6, 16, 9],
                         'offset': ['interpolate', ['linear'], ['zoom'], 7, -1, 12, -4, 14, -3, 17, 0],
                         'glow': '#0B4EA2',
                         'glow_opacity': 0.3,
                         'glow_width': 14,
                         'glow_blur': 3,
                         'dim_opacity': 0.42},
          'routes_map': {'color': '#0B4EA2',
                         'color_dark': '#8AB4F8',
                         'width': 3.4,
                         'casing': '#ffffff',
                         'casing_dark': '#1F2024',
                         'casing_width': 6.4,
                         'halo': '#0B4EA2',
                         'halo_opacity': 0.3,
                         'halo_width': ['interpolate', ['linear'], ['zoom'], 9, 11, 14, 16],
                         'key': 'Picked'}},
 'hover': {'public_map': {'color': '#ffffff', 'width': 12, 'blur': 4, 'opacity': 0.85, 'opacity_dim': 0.6}},
 'in_use': {'routes_map': {'width': 3.2, 'casing': '#ffffff', 'casing_width': 6, 'casing_opacity': 1}},
 'ruled_out_stretch': {'routes_map': {'color': '#1F2024', 'color_dark': '#E6E7EA', 'width': 7, 'cap': 'butt'}},
 'leg_arrow': {'routes_map': {'fill': '#ffffff',
                              'fill_dark': '#1F2024',
                              'halo_width': 2,
                              'spacing': 110,
                              'size': ['interpolate', ['linear'], ['zoom'], 9, 0.8, 14, 1.1],
                              'offset': ['interpolate',
                                         ['linear'],
                                         ['zoom'],
                                         9,
                                         ['literal', [0, -5]],
                                         14,
                                         ['literal', [0, -8]]]}},
 'not_routed': {'routes_map': {'color': '#DC2626',
                               'width': 2,
                               'opacity': 0.9,
                               'dash': [2, 2],
                               'key': 'No route found'}},
 'peak_hours_road': {'public_map': {'color': '#0B4EA2',
                                    'width': 2.6,
                                    'casing': '#ffffff',
                                    'casing_width': 5.5,
                                    'label': '#1F2024',
                                    'label_dark': '#F4F4F5',
                                    'label_halo': '#ffffff',
                                    'label_halo_dark': '#1F2024'},
                     'simulation_map': {'color': '#1D4ED8',
                                        'app_var': '--navy',
                                        'width': 2.6,
                                        'glow_width': 12,
                                        'glow_blur': 6,
                                        'glow_opacity': 0,
                                        'on_opacity': 0.95,
                                        'glow_on_opacity': 0.16,
                                        'main_faded_opacity': 0.25,
                                        'main_width': 1.6,
                                        'key_width': 3,
                                        'key_shadow': 'rgba(29,78,216,.25)'},
                     'plan': {'color': '#3A3C41',
                              'width': 1.2,
                              'casing': '#ffffff',
                              'casing_extra': 1.4,
                              'key': 'Busy-hours road'},
                     'route_analysis': {'color': '#3A3C41',
                                        'width': 2.2,
                                        'offset': -7.0,
                                        'width_back': 1.8,
                                        'offset_back': -4.2}},
 'usual_road': {'public_map': {'color': '#B4B6BA',
                               'color_dark': '#6E7177',
                               'casing': '#FFFFFF',
                               'casing_dark': '#26282C',
                               'x': '#6B6E74',
                               'x_dark': '#C9CBCF',
                               'width': 2.6,
                               'casing_width': 5,
                               'x_every': 70,
                               'x_size': 15},
                'routes_map': {'color': '#B4B6BA',
                               'color_dark': '#6E7177',
                               'casing': '#FFFFFF',
                               'casing_dark': '#26282C',
                               'x': '#6B6E74',
                               'x_dark': '#C9CBCF',
                               'width': 2.6,
                               'casing_width': 5,
                               'x_every': 66,
                               'x_size': 15},
                'route_analysis': {'color': '#71717A',
                                   'width': 1.8,
                                   'dash': [4, 3],
                                   'casing': '#ffffff',
                                   'casing_extra': 1.6,
                                   'key': 'The usual road'}},
 'way_round': {'public_map': {'color': '#F59E0B', 'near_m': 25, 'beyond': 1.7},
               'routes_map': {'color': '#F59E0B', 'width': 10.5, 'near_m': 30, 'min_run_m': 150},
               'plan': {'color': '#F59E0B', 'width': 7.0, 'opacity': 0.5, 'key': 'Way round a closure'}},
 'holding_chevrons': {'public_map': {'glyph': '›',
                                     'size': 18,
                                     'spacing': 34,
                                     'color': '#1F2024',
                                     'halo': '#FFFFFF',
                                     'halo_width': 1.2},
                      'simulation_map': {'glyph': '›',
                                         'size': 18,
                                         'spacing': 34,
                                         'color': '#1F2024',
                                         'app_var': '--ink',
                                         'halo': '#FFFFFF',
                                         'halo_width': 1.2},
                      'route_sheet': {'color': '#1F2024',
                                      'width': 1.1,
                                      'casing': '#ffffff',
                                      'casing_width': 2.6,
                                      'every': 11.0}},
 'abnormal_load': {'public_map': {'color': '#BE185D',
                                  'width': ['interpolate', ['linear'], ['zoom'], 8, 1.6, 13, 3.2, 16, 4.4],
                                  'casing': '#ffffff',
                                  'casing_width': ['interpolate', ['linear'], ['zoom'], 8, 3.8, 13, 5.4, 16, 6.6]}},
 'simulation_route': {'simulation_map': {'color': '#A9ABB0',
                                         'width': 1.6,
                                         'opacity': 0.75,
                                         'end': '#94A3B8',
                                         'end_width': 1,
                                         'end_dash': [2, 2],
                                         'end_key_width': 1.5,
                                         'end_key': 'Route end to its gate'}},
 'collision_route': {'collision_map': {'color': '#A9ABB0',
                                       'color_back': '#C6C8CC',
                                       'width': 2.6,
                                       'width_back': 2.2,
                                       'offset_back': 3.0,
                                       'inset_width': 3.2,
                                       'inset_width_back': 2.6,
                                       'inset_offset_back': 3.6,
                                       'key_width': 2.6,
                                       'chart': '#059669',
                                       'chart_alt2': '#7C3AED'}},
 'week_route': {'week_sheet': {'color': '#1F2024', 'opacity': 0.9, 'width': 3, 'schematic_width': 1.4}}}

# ================================================================================================================
print("1. today's values")
ok("1: the band blues are the one list (the bulletin's VOLUME_RAMP == the public map's CARBON_RAMP)",
   R.BAND_BLUES == ["#72A7FF", "#006AFD", "#0051C4", "#00388E", "#00215B"])
ok("1: the surfaces: four screens and eight kinds of paper, each screen on its page",
   list(R.SURFACES) == ["public_map", "routes_map", "commit_map", "simulation_map", "plan", "route_sheet", "route_analysis",
                        "collision_map", "bulletin", "bulletin_web", "week_sheet", "clp_regional"]
   and [R.SURFACES[s]["page"] for s in ("public_map", "routes_map", "commit_map", "simulation_map")] == ["map", "frontend", "frontend", "frontend"]
   and all(v["page"] is None for k, v in R.SURFACES.items() if v["ground"] == "paper"))
ok("1: the roles, in the table's order", list(R.ROLES) == list(PINNED), [r for r in R.ROLES if r not in PINNED])
for role, want in PINNED.items():
    have = {k: v for k, v in R.ROLES.get(role, {}).items() if k != "what"}
    ok(f"1: {role}: every surface's values are today's", have == want,
       {s: (have.get(s), want.get(s)) for s in set(have) | set(want) if have.get(s) != want.get(s)})
    ok(f"1: {role}: says what it is", isinstance(R.ROLES.get(role, {}).get("what"), str) and len(R.ROLES[role]["what"]) > 10)
ok("1: every surface a role names is a surface in SURFACES",
   all(s in R.SURFACES for v in R.ROLES.values() for s in v if s != "what"))
ok("1: the known oddities are recorded, not changed (at least the nine of 27 Nov 2026)", len(R.KNOWN_ODDITIES) >= 9)

# ================================================================================================================
print("2. the generated copies")
ok("2: no page's copy is stale (run backend/tools/route_line_styles_build.py after a change to the table)",
   B.stale(ROOT) == [], B.stale(ROOT))
ok("2: the build is deterministic", R.page_data("map") == R.page_data("map") and R.page_css("frontend") == R.page_css("frontend"))
mp, fe = read("map", "index.html"), read("frontend", "index.html")
for name, text, page, opener, ind in (("map", mp, "map", '<div id="map"></div>\n\n<script>\n', "    "),
                                      ("app", fe, "frontend", '<script type="text/babel" data-presets="react">\n', "")):
    data = "\n".join(ind + l for l in R.page_data(page).split("\n"))
    css = "\n".join(ind + l for l in R.page_css(page).split("\n"))
    ok(f"2: {name}: the data copy is the first statement of the page's main script", (opener + data + "\n") in text)
    ok(f"2: {name}: the custom properties sit just before </head>, after the page's own stylesheet",
       re.search(re.escape(css) + r"\n</head>", text) is not None and text.index(css) > text.index("</style>"))
    ok(f"2: {name}: one copy and one style block only",
       text.count("// route-line-styles:begin") == 1 and text.count("<!-- route-line-styles:css:begin") == 1)
    m = re.search(r"var ROUTE_LINE_STYLES = (\{.*\});\n", text)
    import json
    got = json.loads(m.group(1)) if m else {}
    ok(f"2: {name}: the copy holds the page's surfaces only, each the table's", list(got) == R.page_surfaces(page)
       and all(got[s] == json.loads(json.dumps(R.surface_roles(s))) for s in got))
ok("2: the map page names its surface once (RLSP)", "const RLSP = ROUTE_LINE_STYLES.public_map;" in mp)
ok("2: the app names its three (RLS_R, RLS_C, RLS_S)",
   "var RLS_R = ROUTE_LINE_STYLES.routes_map, RLS_C = ROUTE_LINE_STYLES.commit_map, RLS_S = ROUTE_LINE_STYLES.simulation_map;" in fe)
ok("2: every colour of a page's surfaces is a custom property there",
   all(f"{R._css_name(s, r, f)}:{v};" in (mp if R.SURFACES[s]["page"] == "map" else fe)
       for s in R.SURFACES if R.SURFACES[s]["page"] for r, sp in R.surface_roles(s).items()
       for f, v in sp.items() if isinstance(v, str) and v.startswith("#")))

# ================================================================================================================
print("3. the guard on the pages")
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")
COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


def strip_generated(t):
    t = re.sub(r"// route-line-styles:begin.*?// route-line-styles:end", "", t, flags=re.S)
    return re.sub(r"<!-- route-line-styles:css:begin.*?route-line-styles:css:end -->", "", t, flags=re.S)


def layers(text):
    out = []
    for m in re.finditer(r"addLayer\(\s*\{", text):
        i = j = m.end() - 1
        depth = 0
        while j < len(text):
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            if depth == 0:
                break
            j += 1
        body = text[i:j + 1]
        idm = re.search(r"""['"]?\bid['"]?\s*:\s*(['"`])([^'"`]+)\1""", body)
        tm = re.search(r"""['"]?\btype['"]?\s*:\s*['"](line|symbol|circle|fill|heatmap|raster|background|fill-extrusion)['"]""", body)
        out.append((idm.group(2) if idm else "?", tm.group(1) if tm else "?", COMMENT.sub("", body)))
    return out


ROUTE_LAYERS = {
    "map": ["route-alt-lines", "outbound-lines-casing", "outbound-lines", "inbound-lines-casing", "inbound-lines", "haul-eraser",
            "haul-dots", "temp-haul-lines", "global-route-hover", "forecast-casing", "forecast-layer", "busy-casing", "busy-core",
            "sel-glow", "sel-casing", "sel-core", "road-load-casing", "road-load-line", "diversion-edge", "div-usual-casing",
            "div-usual", "abnormal-casing", "abnormal-lines", "abnormal-public-casing", "abnormal-public-lines",
            "busy-hours-at", "road-load-labels", "forecast-flow-light", "holding-chevrons", "div-usual-x"],
    "frontend": ["sim-routes", "sim-busy-main", "sim-busy-glow", "sim-busy", "sim-ends", "sim-haul", "la-faded", "la-routes-casing",
                 "la-back", "la-routes", "route-casing", "route-line", "alt-casing", "alt-line", "ol-usual-casing", "ol-usual-line",
                 "ol-div-edge", "ol-use-casing", "ol-use-line", "route-failed", "sel-casing", "sel-line", "ol-mark", "sel-halo",
                 "route-arrows", "ol-use-arrows", "sel-arrows", "ol-usual-x"],
}
# line layers that are NOT route lines and still carry a colour literal (27 Nov 2026); the list may only shrink
OTHER_LINES = {
    "map": {"rail-alignment-survey", "rail-alignment-underlay", "rail-alignment", "area-outline", "restriction-hit", "area-pick-line"},
    "frontend": {"sim-areas-line", "rl-closure-line", "draw-line", "?"},
}
OTHER_CEILING = {"map": 6, "frontend": 4}
for page, text in (("map", mp), ("frontend", fe)):
    L = layers(strip_generated(text))
    ids = [i for i, _, _ in L]
    for lid in ROUTE_LAYERS[page]:
        found = [b for i, _, b in L if i == lid]
        ok(f"3: {page}: route-line layer {lid} is drawn and carries no colour literal",
           found and not any(HEX.search(b) for b in found), [HEX.findall(b) for b in found] or "not found")
    others = sorted({i for i, t, b in L if t == "line" and HEX.search(b) and i not in ROUTE_LAYERS[page]})
    ok(f"3: {page}: every other line layer with a colour literal is a known non-route one",
       set(others) <= OTHER_LINES[page], sorted(set(others) - OTHER_LINES[page]))
    ok(f"3: {page}: at most {OTHER_CEILING[page]} of them (the ceiling may only come down)",
       len(others) <= OTHER_CEILING[page] and len(OTHER_LINES[page]) <= OTHER_CEILING[page], others)
    ok(f"3: {page}: no setPaintProperty writes a colour literal",
       not re.search(r"setPaintProperty\([^;\n]*#[0-9A-Fa-f]{3,6}\b", COMMENT.sub("", strip_generated(text))))
    ok(f"3: {page}: every listed route-line layer id is still a layer (a renamed layer is listed again)",
       all(l in ids for l in ROUTE_LAYERS[page]), [l for l in ROUTE_LAYERS[page] if l not in ids])

# strays: route-looking colours that are not route lines, pinned with a ceiling
STRAYS = {
    "frontend": ['.ol-lab[aria-pressed="true"]{border-color:#1D4ED8;'],   # the Routes label's picked edge (a label, not a line)
}
STRAY_CEILING = 1
ok("3: the strays are where they were and no more than the ceiling (it may only come down)",
   sum(len(v) for v in STRAYS.values()) <= STRAY_CEILING and all(s in fe for s in STRAYS["frontend"]))
ok("3: the app's dead ROUTE_COLOR (a stock blue #2563EB) is gone",
   not re.search(r"\bROUTE_COLOR\b", COMMENT.sub("", strip_generated(fe))))
cfg = COMMENT.sub("", read("map", "config.js"))
ok("3: the map's config no longer holds the route lines (forecast, forecastCasing, selection)",
   not re.search(r"\b(forecast|forecastCasing|selection)\s*:", cfg) and "brand:" in cfg and "brandDark:" in cfg)
ok("3: and nothing on the map page reads them", not re.search(r"CONFIG\.COLORS\.(forecast|forecastCasing|selection)\b",
                                                              COMMENT.sub("", mp)))
ok("3: the public map's council grey and the CLP's no-lines grey are the table's (no longer strays)",
   R.get("month_line", "public_map", "council") == "#A8A29E" and R.get("month_line", "clp_regional", "no_lines") == "#9CA3AF"
   and "#9CA3AF" not in read("backend", "clp_doc_pictures.py").upper())
ok("3: site-layouts.js draws no route line (it reads only the site-layout styles)",
   "line-color" not in read("map", "site-layouts.js") or "route" not in " ".join(
       re.findall(r"id:\s*['\"]([^'\"]+)['\"]", read("map", "site-layouts.js"))))

# ================================================================================================================
print("4. the guard on the Python modules")
import bulletin_doc, clp_doc_pictures, export, route_analysis_render, route_map_export  # noqa: E402
CONSTS = [
    (bulletin_doc, "VOLUME_RAMP", None, None, None, tuple(R.BAND_BLUES)),
    (bulletin_doc, "ROUTE_CASING", "month_line", "bulletin", "casing", None),
    (bulletin_doc, "ROUTE_LINE_W", "month_line", "bulletin_web", "width", None),
    (bulletin_doc, "ROUTE_CASING_W", "month_line", "bulletin_web", "casing_width", None),
    (bulletin_doc, "ROUTE_CASING_OPACITY", "month_line", "bulletin_web", "casing_opacity", None),
    (export, "PLAN_LEG_W", "loaded_leg", "plan", "width", None),
    (export, "PLAN_LEG_EDGE", "loaded_leg", "plan", "casing_extra", None),
    (export, "PLAN_LEG_OFFSET", "loaded_leg", "plan", "offset", None),
    (export, "PLAN_BUSY_W", "peak_hours_road", "plan", "width", None),
    (export, "PLAN_BUSY_EDGE", "peak_hours_road", "plan", "casing_extra", None),
    (export, "PLAN_DIV_HALO_W", "way_round", "plan", "width", None),
    (export, "PLAN_DIV_HALO_ALPHA", "way_round", "plan", "opacity", None),
    (export, "PLAN_CASING", "loaded_leg", "plan", "casing", None),
    (export, "PLAN_KEYLINE", "loaded_leg", "plan", "keyline", None),
    (export, "PLAN_KEYLINE_EXTRA", "loaded_leg", "plan", "keyline_extra", None),
    (export, "RS_LOADED", "loaded_leg", "route_sheet", "color", None),
    (export, "RS_RETURN", "empty_leg", "route_sheet", "color", None),
    (export, "RS_CASING", "loaded_leg", "route_sheet", "casing", None),
    (export, "RS_W", "loaded_leg", "route_sheet", "width", None),
    (export, "RS_CASING_EXTRA", "loaded_leg", "route_sheet", "casing_extra", None),
    (export, "RS_HAUL_W", "haul_stretch", "route_sheet", "width", None),
    (export, "RS_HAUL_GAP", "haul_stretch", "route_sheet", "gap", None),
    (export, "RS_OFFSET", "loaded_leg", "route_sheet", "offset", None),
    (export, "RS_CHEVRON_EVERY_PT", "holding_chevrons", "route_sheet", "every", None),
    (export, "CE_ALT", "alternative", "collision_map", "color", None),
    (export, "CE_ROUTE_OUT", "collision_route", "collision_map", "color", None),
    (export, "CE_ROUTE_BACK", "collision_route", "collision_map", "color_back", None),
    (export, "CE_ROUTE_CHART", "collision_route", "collision_map", "chart", None),
    (export, "CE_HOUR_ALT2", "collision_route", "collision_map", "chart_alt2", None),
    (route_analysis_render, "BUSY_BLUE", "peak_hours_road", "route_analysis", "color", None),
    (route_analysis_render, "USUAL_GREY", "usual_road", "route_analysis", "color", None),
    (route_map_export, "LEG_LADEN", "loaded_leg", "plan", "color", None),
    (route_map_export, "LEG_EMPTY", "empty_leg", "plan", "color", None),
    (route_map_export, "BUSY_ROAD", "peak_hours_road", "plan", "color", None),
    (route_map_export, "DIVERSION_EDGE", "way_round", "plan", "color", None),
    (clp_doc_pictures, "NO_LINES_FILL", "month_line", "clp_regional", "no_lines", None),
    (clp_doc_pictures, "NO_LINES_LABEL", "month_line", "clp_regional", "no_lines_key", None),
]
for mod, name, role, surface, field, want in CONSTS:
    src = read("backend", os.path.basename(mod.__file__))
    line = next((l for l in src.split("\n") if re.match(r"\s*" + r"[A-Z_0-9, ]*\b" + name + r"\b[A-Z_0-9, ]*=", l)), "")
    val = want if want is not None else R.get(role, surface, field)
    ok(f"4: {mod.__name__}.{name} is read from the table and is today's value",
       "_RLS." in line and not HEX.search(line.split("#", 1)[0] if "  #" not in line else line.split("  #", 1)[0])
       and getattr(mod, name) == val, (line[:140], getattr(mod, name, None), val))
for mod in (bulletin_doc, clp_doc_pictures, export, route_analysis_render, route_map_export):
    ok(f"4: {mod.__name__} imports the table as _RLS", "import route_line_styles as _RLS" in read("backend", os.path.basename(mod.__file__)))
ok("4: the route map export's key rows read their words from the table",
   [k["label"] for k in route_map_export.LEG_LEGEND if k["kind"] in ("laden", "empty", "busy", "diversion")]
   == [R.get("loaded_leg", "plan", "key"), R.get("empty_leg", "plan", "key"), R.get("peak_hours_road", "plan", "key"),
       R.get("way_round", "plan", "key")]
   and all(f'_RLS.get("{r}", "plan", "key")' in read("backend", "route_map_export.py") for r in ("loaded_leg", "empty_leg", "peak_hours_road", "way_round")))

# ================================================================================================================
print("5. the keys' words")
ok("5: the public map's legend says the table's words, each sample the table's colour",
   all(re.search(r"> " + re.escape(R.get(role, "public_map", "key")) + r"(?: <span[^>]*></span>)?</label><span class=\"color-dot\" style=\"background:var\(--rl-public-map-"
                 + role.replace("_", "-") + r"-color\);\"", mp)
       for role in ("loaded_leg", "empty_leg", "temporary_haul", "alternative")))
ok("5: the Routes map's key says the table's words",
   all(re.search(r"<span style=\{sw\(K\.\w+, \d\)\} />" + re.escape(R.get(role, "routes_map", "key")) + r"\n", fe)
       for role in ("loaded_leg", "empty_leg", "pick", "alternative"))
   and ("transparent 4px 7px)` }} />" + R.get("not_routed", "routes_map", "key") + "\n") in fe)
ok("5: the week map's key says the table's words",
   ('{today ? "' + R.get("loaded_leg", "commit_map", "key_today") + '" : "' + R.get("loaded_leg", "commit_map", "key") + '"}') in fe
   and ('aria-hidden="true" />' + R.get("empty_leg", "commit_map", "key_today") + "</span>") in fe
   and ('aria-hidden="true" />' + R.get("later_this_week", "commit_map", "key") + "</span>") in fe)
ok("5: the Simulation's key says the table's words",
   ('["sim-line sim-line-end", "' + R.get("simulation_route", "simulation_map", "end_key") + '"]') in fe
   and ('["sim-line sim-line-haul", "' + R.get("haul_stretch", "simulation_map", "key") + '"]') in fe)
ra = read("backend", "route_analysis_render.py")
ok("5: the Route analysis key reads its words from the table (section C's legs, section F's usual road)",
   '_k_line(RS_LOADED)(c, cx, cy), _RA_OUT["key"])' in ra and '_k_line(RS_RETURN)(c, cx, cy), _RA_BACK["key"])' in ra
   and '_RLS.get("usual_road", "route_analysis", "key")' in ra
   and (R.get("loaded_leg", "route_analysis", "key"), R.get("empty_leg", "route_analysis", "key"), R.get("usual_road", "route_analysis", "key"))
   == ("Out, loaded, A to B", "Back, empty, B to A", "The usual road"))
ok("5: the Route sheet's key words are the table's (the sheet keeps them as words: its holding-area rows vary them)",
   ('(RS_LOADED, False, "' + R.get("loaded_leg", "route_sheet", "key") + '" + (f') in read("backend", "export.py")
   and ('(RS_RETURN, False, "' + R.get("empty_leg", "route_sheet", "key") + '")]') in read("backend", "export.py"))

# ================================================================================================================
print("6. the readers")
ok("6: spec / get / surface_roles", R.spec("pick", "routes_map")["color"] == "#0B4EA2" and R.get("pick", "public_map", "color") == "#1F2024"
   and list(R.surface_roles("commit_map")) == ["loaded_leg", "empty_leg", "later_this_week"])
ok("6: page_surfaces", R.page_surfaces("map") == ["public_map"] and R.page_surfaces("frontend") == ["routes_map", "commit_map", "simulation_map"])
ok("6: css_var names the generated property", R.css_var("commit_map", "loaded_leg", "color") == "var(--rl-commit-map-loaded-leg-color)")
ok("6: all_colours holds every colour, upper case", {"#0B4EA2", "#3A3C41", "#72A7FF", "#F59E0B", "#BE185D"} <= R.all_colours()
   and all(c == c.upper() for c in R.all_colours()))
try:
    R.spec("pick", "bulletin")
    ok("6: a surface that does not draw a role is a KeyError", False)
except KeyError:
    ok("6: a surface that does not draw a role is a KeyError", True)

# ================================================================================================================
print("7. the specimen sheet (built offline here; not served, not linked)")
import shutil, tempfile  # noqa: E401,E402
import route_line_specimen as SPEC  # noqa: E402
from portable import pdf_text  # noqa: E402
_tmp = tempfile.mkdtemp(prefix="rl-specimen-")
try:
    hp, bp, pp = SPEC.main(["--out", _tmp])
    H_, BW = open(hp, encoding="utf-8").read(), open(bp, encoding="utf-8").read()
    PAIRS = [(s, r) for s, r, _ in SPEC.pairs()]
    ok("7: the sheet has a row for every role on every surface (and no other)",
       all(f'data-surface="{s}" data-role="{r}"' in H_ for s, r in PAIRS) and H_.count("data-surface=") == len(PAIRS) == sum(
           len(R.surface_roles(s)) for s in R.SURFACES), (len(PAIRS), H_.count("data-surface=")))
    ok("7: every surface has its section, screens with a Dark column, paper without",
       all(f'id="s-{s}"' in H_ for s in R.SURFACES if R.surface_roles(s))
       and H_.count("<th>Dark</th>") == sum(1 for s, v in R.SURFACES.items() if v["ground"] == "screen" and R.surface_roles(s)))
    ok("7: every colour the table holds is drawn or listed on the colour sheet", all(c in H_.upper() for c in R.all_colours()),
       sorted(c for c in R.all_colours() if c not in H_.upper()))
    _smp = re.findall(r'<svg class="smp".*?</svg>', BW, flags=re.S)
    _cols = set(re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', " ".join(_smp)))
    ok("7: the black-and-white sheet draws every sample in greys only",
       _smp and _cols and all(c[1:3] == c[3:5] == c[5:7] for c in _cols), sorted(c for c in _cols if not (c[1:3] == c[3:5] == c[5:7])))
    ok("7: the colour sheet draws in colour (the loaded leg's dark blue on paper, the sign blue)",
       'stroke="#0051C4"' in H_ and 'stroke="#0B4EA2"' in H_)
    ok("7: the week map's Dark legs are drawn in the Routes map's own Dark pair (as the page reads them)",
       re.search(r'data-surface="commit_map" data-role="loaded_leg".*?<td class="dk">.*?stroke="#1F2024".*?stroke="#D4D6DA"', H_, flags=re.S) is not None)
    _pt = pdf_text(open(pp, "rb").read(), raw=True)
    ok("7: the PDF names every role on every surface, in colour and in black and white",
       all(_pt.count(f"{s} / {r}") >= 2 for s, r in PAIRS) and "colour" in _pt and "black and white" in _pt,
       [f"{s} / {r}" for s, r in PAIRS if _pt.count(f"{s} / {r}") < 2][:8])
    ok("7: a ramp is read at zoom 12", SPEC.at_zoom(["interpolate", ["linear"], ["zoom"], 7, 1.1, 12, 2.6, 16, 4.6]) == 2.6
       and abs(SPEC.at_zoom(["interpolate", ["linear"], ["zoom"], 9, 11, 14, 16]) - 14) < 1e-9 and SPEC.at_zoom(3) == 3.0)
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
_served = read("backend", "main.py") + read("frontend", "index.html") + read("map", "index.html")
ok("7: the sheet is not served and nothing links to it", "route-line-specimen" not in _served and "route_line_specimen" not in _served)
ok("7: the sheet writes outside the checkout by default (the system's temp folder)",
   'ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "route-line-specimen"))' in read("backend", "tools", "route_line_specimen.py")
   and not tempfile.gettempdir().startswith(ROOT))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
