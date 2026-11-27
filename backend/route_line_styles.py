"""
Every route line the product draws, in ONE table: colour, width, casing, side step, mark and key word, role by role and
surface by surface (27 Nov 2026, the route lines plan's group 1, `notes/route-lines-build-1126/README.md`).

WHAT IT IS
----------
The values here are TODAY's, read off the code on `main` e20c6f4 and moved here unchanged. Where two surfaces draw one
role two ways (the loaded leg is ink on the screens and dark blue on paper; the alternative is a grey on the public map
and another grey on Data → Routes), the table holds BOTH, named by surface: it records today, it does not tidy it. A
value that looks wrong stays as it is (see "Known oddities" at the end); changing a value is a decision, made on its
own branch with its own mockup.

WHO READS IT
------------
  * Python, by import: `route_map_export`, `export` (the route map export, the Route sheet, the collision evidence,
    the bulletin's printed map, the Look-ahead week sheet), `route_analysis_render`, `bulletin_doc` (the bulletin's
    web map), `clp_doc_pictures` (the CLP regional plan).
  * The two pages, through a GENERATED copy written into each page between the markers
    `<!-- route-line-styles:begin -->` and `<!-- route-line-styles:end -->` by `backend/tools/route_line_styles_build.py`:
    a plain script that sets `window.ROUTE_LINE_STYLES` (the page's surfaces only) and a style block of custom
    properties `--rl-…` for the HTML key samples. Inline, so a page loads nothing new and cannot lose its lines to a
    request that fails; `test_route_line_styles.py` fails when a page's copy is stale.

THE SHAPE
---------
ROLES[role][surface] = spec. A spec is a flat dict: `color` (and `color_dark` where the screen's Dark ground draws
another), `width` (a number, or a Mapbox zoom ramp as a list), `casing` / `casing_dark` / `casing_width`, `opacity`,
`offset` (the side step: negative is left of travel on the screens, a positive page-point step on paper), `dash`,
`blur`, `key` (the words its key row says) and a few role-own fields named where they are used. SURFACES says what
each surface is and which page draws it.
"""

import json

# ---- the surfaces -------------------------------------------------------------------------------------------------
SURFACES = {
    # the screens (a light and a Dark ground each)
    "public_map":     {"what": "The public map (map/index.html)", "page": "map", "ground": "screen"},
    "routes_map":     {"what": "Data → Routes' map (frontend/index.html, RouteMap)", "page": "frontend", "ground": "screen"},
    "commit_map":     {"what": "The Dashboard's and the Look-ahead's map of the week (frontend/index.html, CommitMap)", "page": "frontend", "ground": "screen"},
    "simulation_map": {"what": "The Simulation's map (frontend/index.html, SimMap)", "page": "frontend", "ground": "screen"},
    # paper (PDF / PNG); light only
    "plan":           {"what": "The route map export, approved routes with no month (export._draw_plan_legs, route_map_export)", "page": None, "ground": "paper"},
    "route_sheet":    {"what": "The Route sheet and its diversion page (export._rs_*)", "page": None, "ground": "paper"},
    "route_analysis": {"what": "The Route analysis' maps, sections C, E and F (route_analysis_render)", "page": None, "ground": "paper"},
    "collision_map":  {"what": "The collision evidence's map, inset, key and charts (export, CE_*)", "page": None, "ground": "paper"},
    "bulletin":       {"what": "The bulletin's printed map and the route map export with a month (export, bulletin_doc)", "page": None, "ground": "paper"},
    "bulletin_web":   {"what": "The bulletin's web page map, SVG (bulletin_doc)", "page": None, "ground": "paper"},
    "week_sheet":     {"what": "The Look-ahead week sheet's map (export: a path over the supplier's picture, or the schematic)", "page": None, "ground": "paper"},
    "clp_regional":   {"what": "The CLP's regional plan (clp_doc_pictures)", "page": None, "ground": "paper"},
}

# the public map's leg ramps (the style.load handler's OFFSET_IN / WIDTH_CORE / WIDTH_CASING)
_PM_OFFSET = ["interpolate", ["linear"], ["zoom"], 7, -1, 12, -4, 14, -3, 17, 0]
_PM_CORE = ["interpolate", ["linear"], ["zoom"], 7, 1.1, 12, 2.6, 16, 4.6]
_PM_CASING = ["interpolate", ["linear"], ["zoom"], 7, 2.9, 12, 4.8, 16, 7]
# the band blues: ONE list, the bulletin's VOLUME_RAMP == the public map's CARBON_RAMP (11 Nov 2026, PR #278)
BAND_BLUES = ["#72A7FF", "#006AFD", "#0051C4", "#00388E", "#00215B"]

ROLES = {
    # ---- the approved network ------------------------------------------------------------------------------------
    "loaded_leg": {
        "what": "A route's loaded leg, out",
        "public_map": {"color": "#3A3C41", "color_dark": "#D4D6DA", "width": _PM_CORE, "offset": _PM_OFFSET,
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": _PM_CASING, "cap": "round",
                       "key": "Laden (out)"},
        "routes_map": {"color": "#3A3C41", "color_dark": "#D4D6DA", "width": 3, "offset": ["interpolate", ["linear"], ["zoom"], 9, -2.2, 14, -4.5],
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": 5, "casing_opacity": 0.85,
                       # the tab in focus leans the shared map (EMPHASIS): the legs' width and opacity, the casing's opacity
                       "emphasis": {"locations": {"width": 2, "opacity": 0.45, "casing_opacity": 0.30},
                                    "routes": {"width": 3, "opacity": 1.00, "casing_opacity": 0.85},
                                    "zones": {"width": 2, "opacity": 0.55, "casing_opacity": 0.35}},
                       "dim_factor": 0.3, "key": "Out"},
        "commit_map": {"color": "#3A3C41", "color_dark": "#D4D6DA", "width": 4, "offset": ["interpolate", ["linear"], ["zoom"], 8, -1.5, 12, -4],
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": 6.5, "casing_opacity": 0.9,
                       "key": "Out (loaded)", "key_today": "Today, out (loaded)"},
        "plan": {"color": "#0051C4", "width": 2.2, "casing": "#ffffff", "casing_extra": 1.4, "offset": 1.5,
                 "keyline": "#1F2024", "keyline_extra": 0.4, "key": "Laden (out)"},
        "route_sheet": {"color": "#0051C4", "width": 2.8, "casing": "#ffffff", "casing_extra": 1.6, "offset": 1.8,
                        "key": "Out, loaded"},
        "route_analysis": {"color": "#0051C4", "width": 2.4, "width_section_f": 2.4, "key": "Out, loaded, A to B"},
    },
    "empty_leg": {
        "what": "A route's empty leg, back",
        "public_map": {"color": "#8E9197", "color_dark": "#9A9DA3", "width": _PM_CORE, "offset": _PM_OFFSET,
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": _PM_CASING, "cap": "round",
                       "key": "Empty (return)"},
        "routes_map": {"color": "#8E9197", "color_dark": "#9A9DA3", "width": 3, "offset": ["interpolate", ["linear"], ["zoom"], 9, -2.2, 14, -4.5],
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": 5, "casing_opacity": 0.85,
                       "key": "Back"},
        "commit_map": {"color": "#8E9197", "color_dark": "#9A9DA3", "width": 2.5, "offset": ["interpolate", ["linear"], ["zoom"], 8, -1.5, 12, -4],
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": 5, "casing_opacity": 0.9,
                       "key_height": 3, "key": "Back (empty)", "key_today": "Today, back (empty)"},
        "plan": {"color": "#72A7FF", "width": 2.2, "casing": "#ffffff", "casing_extra": 1.4, "offset": 1.5,
                 "key": "Empty (return)"},
        "route_sheet": {"color": "#72A7FF", "width": 2.8, "casing": "#ffffff", "casing_extra": 1.6, "offset": 1.8,
                        "key": "Back, empty"},
        # the Route analysis draws the return 0.3 pt thinner than the loaded leg and 3 pt to its side
        "route_analysis": {"color": "#72A7FF", "thinner": 0.3, "offset": 3.0, "width_section_f": 2.1, "key": "Back, empty, B to A"},
    },
    "later_this_week": {
        "what": "The rest of this week's lines, faded, on the map of today",
        "commit_map": {"color": "#C6C8CC", "color_dark": "#7D8087", "width": 2, "opacity": 0.9, "key": "Later this week"},
    },
    "quiet_route": {
        "what": "A route with no lorries in the month on screen: one quiet line on the road, no side step",
        "public_map": {"color": "#A9ABB0", "color_dark": "#6B6E74", "width": ["interpolate", ["linear"], ["zoom"], 7, 1, 12, 2, 16, 3.4],
                       "casing_width": ["interpolate", ["linear"], ["zoom"], 7, 2.6, 12, 4, 16, 5.6], "offset": 0},
    },
    "alternative": {
        "what": "Another option a route had",
        "public_map": {"color": "#A9ABB0", "color_dark": "#7D8087", "opacity": 0.9,
                       "width": ["interpolate", ["linear"], ["zoom"], 7, 0.6, 12, 1.2, 16, 2], "key": "Alternative routes"},
        "routes_map": {"color": "#8E9197", "color_dark": "#7D8087", "width": 2.4, "opacity": 1,
                       "casing": "#ffffff", "casing_dark": "#1F2024", "casing_width": 5.4, "key": "Alternative"},
        "collision_map": {"color": "#71717A", "width": 1.8},
    },
    "haul_stretch": {
        "what": "A leg's haul-road stretch: dots in the leg's own colour over a cut-out of the ground",
        "public_map": {"width": ["interpolate", ["linear"], ["zoom"], 7, 1.1, 12, 2.4, 16, 3.8], "dash": [0, 2.2],
                       "eraser": "#ffffff", "eraser_dark": "#1F2024"},
        "route_sheet": {"width": 1.7, "gap": 4.4},
        "simulation_map": {"color": "#7C3AED", "token": "--chart-4", "width": 4, "dash": [1.5, 1], "key_width": 3,
                           "key": "Haul road (assigned speed)"},
    },
    "temporary_haul": {
        "what": "A temporary haul road",
        "public_map": {"color": "#C2790B", "width": ["interpolate", ["linear"], ["zoom"], 7, 1.2, 12, 2.6], "opacity": 0.55,
                       "key": "Temporary haul"},
    },
    # ---- the month's lorries -------------------------------------------------------------------------------------
    "month_line": {
        "what": "A route's line in the month on screen: one width, the band blues by count (Volume) or carbon",
        "public_map": {"color": "#0B4EA2", "bands": BAND_BLUES, "no_value": "#A8A29E", "width": 4,
                       "casing": "#FFFFFF", "casing_dark": "#E7E5E4", "casing_width": 6.6,
                       "council": "#A8A29E", "council_width": 2},
        "bulletin": {"bands": BAND_BLUES, "width": 2.2, "casing": "#1F2024", "casing_width": 3.4},
        "bulletin_web": {"bands": BAND_BLUES, "width": 5, "casing": "#1F2024", "casing_width": 7.5, "casing_opacity": 0.9},
        "plan": {"color": "#0051C4"},
        "clp_regional": {"bands": BAND_BLUES, "no_lines": "#9CA3AF", "no_lines_key": "No approved lines yet"},
    },
    "shared_section": {
        "what": "A road two or more routes share, in its summed colour, over the month's lines",
        "public_map": {"color": "#0B4EA2", "casing": "#FFFFFF"},
        "bulletin": {"width": 2.2, "casing": "#1F2024", "casing_width": 3.4},
    },
    "flow_arrow": {
        "what": "The month's arrowheads along a line (drifting while Play runs)",
        "public_map": {"fill": "#ffffff", "ring": "#00215B", "ring_width": 0.8, "gap": 90, "speed": 13,
                       "length": 5.2, "side": 2.7},   # length and side on a 5 px line; the page scales them to its width
    },
    # ---- picking and hovering ------------------------------------------------------------------------------------
    "pick": {
        "what": "The route picked: both legs in ink on a white casing over a soft sign-blue halo; the rest dimmed",
        "public_map": {"color": "#1F2024", "color_dark": "#F5F5F4", "casing": "#ffffff", "casing_dark": "#1F2024",
                       "width": ["interpolate", ["linear"], ["zoom"], 7, 2, 12, 4.2, 16, 6.6],
                       "casing_width": ["interpolate", ["linear"], ["zoom"], 7, 4.4, 12, 6.6, 16, 9],
                       "offset": _PM_OFFSET, "glow": "#0B4EA2", "glow_opacity": 0.3, "glow_width": 14, "glow_blur": 3,
                       "dim_opacity": 0.42},
        "routes_map": {"color": "#0B4EA2", "color_dark": "#8AB4F8", "width": 3.4, "casing": "#ffffff", "casing_dark": "#1F2024",
                       "casing_width": 6.4, "halo": "#0B4EA2", "halo_opacity": 0.3,
                       "halo_width": ["interpolate", ["linear"], ["zoom"], 9, 11, 14, 16], "key": "Picked"},
    },
    "hover": {
        "what": "The route under the pointer on the public map",
        "public_map": {"color": "#ffffff", "width": 12, "blur": 4, "opacity": 0.85, "opacity_dim": 0.6},
    },
    "in_use": {
        "what": "An open route's line in use, on Data → Routes",
        # in the legs' own pair (loaded_leg / empty_leg); its width is set to the tab's leg width (EMPHASIS) once drawn
        "routes_map": {"width": 3.2, "casing": "#ffffff", "casing_width": 6, "casing_opacity": 1},
    },
    "ruled_out_stretch": {
        "what": "The stretch of a limit that rules an option out, solid and dark on the option's line, on Data → Routes",
        "routes_map": {"color": "#1F2024", "color_dark": "#E6E7EA", "width": 7, "cap": "butt"},
    },
    "leg_arrow": {
        "what": "The chevrons along a leg on Data → Routes, the way it runs (white with the leg's colour round it)",
        "routes_map": {"fill": "#ffffff", "fill_dark": "#1F2024", "halo_width": 2, "spacing": 110,
                       "size": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 14, 1.1],
                       "offset": ["interpolate", ["linear"], ["zoom"], 9, ["literal", [0, -5]], 14, ["literal", [0, -8]]]},
    },
    "not_routed": {
        "what": "A route the router could not work out, on Data → Routes",
        "routes_map": {"color": "#DC2626", "width": 2, "opacity": 0.9, "dash": [2, 2], "key": "No route found"},
    },
    # ---- the ways round ------------------------------------------------------------------------------------------
    "peak_hours_road": {
        "what": "A route's busy-hours road",
        "public_map": {"color": "#0B4EA2", "width": 2.6, "casing": "#ffffff", "casing_width": 5.5,
                       "label": "#1F2024", "label_dark": "#F4F4F5", "label_halo": "#ffffff", "label_halo_dark": "#1F2024"},
        # drawn unseen (opacity 0); in its hours the frame shows it at on_opacity with its glow, and the main road's stretch
        # it replaces fades to main_faded_opacity (else the route's own 0.75)
        "simulation_map": {"color": "#1D4ED8", "token": "--navy", "width": 2.6, "glow_width": 12, "glow_blur": 6, "glow_opacity": 0,
                           "on_opacity": 0.95, "glow_on_opacity": 0.16, "main_faded_opacity": 0.25,
                           "main_width": 1.6, "key_width": 3, "key_shadow": "rgba(29,78,216,.25)"},
        "plan": {"color": "#3A3C41", "width": 1.2, "casing": "#ffffff", "casing_extra": 1.4, "key": "Busy-hours road"},
        "route_analysis": {"color": "#3A3C41", "width": 2.2, "offset": -7.0, "width_back": 1.8, "offset_back": -4.2},
    },
    "usual_road": {
        "what": "The usual road while a closure diverts a route: pale grey with crosses",
        "public_map": {"color": "#B4B6BA", "color_dark": "#6E7177", "casing": "#FFFFFF", "casing_dark": "#26282C",
                       "x": "#6B6E74", "x_dark": "#C9CBCF", "width": 2.6, "casing_width": 5, "x_every": 70, "x_size": 15},
        "routes_map": {"color": "#B4B6BA", "color_dark": "#6E7177", "casing": "#FFFFFF", "casing_dark": "#26282C",
                       "x": "#6B6E74", "x_dark": "#C9CBCF", "width": 2.6, "casing_width": 5, "x_every": 66, "x_size": 15},
        "route_analysis": {"color": "#71717A", "width": 1.8, "dash": [4, 3], "casing": "#ffffff", "casing_extra": 1.6,
                           "key": "The usual road"},
    },
    "way_round": {
        "what": "The way round a closure: amber rails (screens) or a soft amber edge (paper)",
        "public_map": {"color": "#F59E0B", "near_m": 25, "beyond": 1.7},
        "routes_map": {"color": "#F59E0B", "width": 10.5, "near_m": 30, "min_run_m": 150},
        "plan": {"color": "#F59E0B", "width": 7.0, "opacity": 0.5, "key": "Way round a closure"},
    },
    # ---- the rest ------------------------------------------------------------------------------------------------
    "holding_chevrons": {
        "what": "The run from a holding area to the gate (called forward): chevrons",
        "public_map": {"glyph": "›", "size": 18, "spacing": 34, "color": "#1F2024", "halo": "#FFFFFF", "halo_width": 1.2},
        "simulation_map": {"glyph": "›", "size": 18, "spacing": 34, "color": "#1F2024", "token": "--ink", "halo": "#FFFFFF", "halo_width": 1.2},
        "route_sheet": {"color": "#1F2024", "width": 1.1, "casing": "#ffffff", "casing_width": 2.6, "every": 11.0},
    },
    "abnormal_load": {
        "what": "An abnormal load's route",
        "public_map": {"color": "#BE185D", "width": ["interpolate", ["linear"], ["zoom"], 8, 1.6, 13, 3.2, 16, 4.4],
                       "casing": "#ffffff", "casing_width": ["interpolate", ["linear"], ["zoom"], 8, 3.8, 13, 5.4, 16, 6.6]},
    },
    "simulation_route": {
        "what": "A route on the Simulation's map, and the end of a lorry's run",
        "simulation_map": {"color": "#A9ABB0", "width": 1.6, "opacity": 0.75, "end": "#94A3B8", "end_width": 1, "end_dash": [2, 2],
                           "end_key_width": 1.5, "end_key": "Route end to its gate"},
    },
    "collision_route": {
        "what": "The route on the collision evidence's map and inset (greys), and its own chart series",
        "collision_map": {"color": "#A9ABB0", "color_back": "#C6C8CC", "width": 2.6, "width_back": 2.2, "offset_back": 3.0,
                          "inset_width": 3.2, "inset_width_back": 2.6, "inset_offset_back": 3.6, "key_width": 2.6,
                          "chart": "#059669", "chart_alt2": "#7C3AED"},
    },
    "week_route": {
        "what": "A route on the Look-ahead week sheet: a path over the supplier's picture, or the schematic",
        "week_sheet": {"color": "#1F2024", "opacity": 0.9, "width": 3, "schematic_width": 1.4},
    },
}

# Known oddities, recorded and NOT changed (each is a decision for a later branch):
KNOWN_ODDITIES = [
    "band 1 of the band blues (#72A7FF) reads at about 2.4:1 on white",
    "the month's lines and the shared sections have square ends (no line-cap set), the legs round ones",
    "on the public map the alternative and the quiet route share #A9ABB0; on Data → Routes the alternative and the empty leg share #8E9197",
    "the loaded leg is ink on the screens and dark blue on paper (John, 26 Nov: \"Go with blue\" for paper)",
    "the bulletin's casing is ink (#1F2024) where the public map's is white",
    "the Simulation's busy-hours road and haul read app tokens (--navy, --chart-4) with fallbacks",
    "the Routes map's picked line is sign blue, the public map's picked line ink",
]


# ---- the readers ----------------------------------------------------------------------------------------------------
def spec(role, surface):
    """The spec of one role on one surface (KeyError if that surface does not draw it)."""
    return ROLES[role][surface]


def get(role, surface, field):
    return ROLES[role][surface][field]


def surface_roles(surface):
    """{role: spec} for one surface, in the table's order."""
    return {r: v[surface] for r, v in ROLES.items() if surface in v}


def page_surfaces(page):
    return [s for s, v in SURFACES.items() if v["page"] == page]


def _css_name(surface, role, field):
    return "--rl-" + "-".join(x.replace("_", "-") for x in (surface, role, field))


_GEN = "GENERATED by backend/tools/route_line_styles_build.py from backend/route_line_styles.py; do not edit"


def page_data(page):
    """The data region written as the first statement of a page's main script: the page's surfaces, as JSON.
    `var`, so a harness that evaluates the script reads it as a global. Deterministic: compared byte for byte."""
    data = {s: surface_roles(s) for s in page_surfaces(page)}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"// route-line-styles:begin ({_GEN})\nvar ROUTE_LINE_STYLES = {js};\n// route-line-styles:end"


def page_css(page):
    """The style region written in a page's head: a custom property for every colour field (the HTML key samples)."""
    props = []
    for s in page_surfaces(page):
        for r, sp in surface_roles(s).items():
            for f, v in sp.items():
                if isinstance(v, str) and (v.startswith("#") or v.startswith("rgba(")):
                    props.append(f"{_css_name(s, r, f)}:{v};")
    return (f"<!-- route-line-styles:css:begin ({_GEN}) -->\n"
            "<style id=\"route-line-styles\">html{" + "".join(props) + "}</style>\n"
            "<!-- route-line-styles:css:end -->")


def css_var(surface, role, field):
    """`var(--rl-…)` for a page's CSS (the property is in the generated style block)."""
    return f"var({_css_name(surface, role, field)})"


def all_colours():
    """Every colour string the table holds, upper case (the guard's list)."""
    out = set()

    def walk(v):
        if isinstance(v, str) and v.startswith("#"):
            out.add(v.upper())
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(ROLES)
    return out
