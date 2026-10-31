"""
tools/make_demo_tenant.py — the synthetic UK demo tenant, as a package. Wayscope (G2, 16 Sep 2026).

    python3 backend/tools/make_demo_tenant.py --with-areas   # writes demo/uk-corridor.package.json (the shipped file)
    python3 backend/tools/make_demo_tenant.py --with-areas --out demo/with-areas.package.json
    python3 backend/tools/make_demo_tenant.py --with-areas --as-of 2027-02-25 --out ../demo-refresh/live.package.json
            --live-export ../demo-refresh/live-export.json      # one command: a live refresh (§1.9), outside the checkout

OPTION --with-areas (12 Oct 2026, public map review §2.2b, D27). Also loads the council
boundaries in backend/data/areas_demo.geojson (the eight ONS local authority districts round
the corridor, May 2026, and Leicestershire, Dec 2025 — OGL v3, with the two licence lines)
into the package's `areas` table, through areas.import_collection, the app's own path. OFF
by default; since 16 Oct 2026 (D102) the SHIPPED package is built WITH it, so the By council
view works straight after an import with no admin step. A deployment can still reload them
with POST /api/admin/areas/import?token= (the same file as the body). --out writes elsewhere,
so the shipped package is not rewritten by trying an option. The clip (route_area_km)
needs baked geometry, so it is empty here and fills on the first bake after import.
The seed file is 25,878 bytes (one line of JSON, 1,044 vertices), fetched 12 Oct 2026 from
the ONS ArcGIS FeatureServer's BSC layers named in its `sources`; areas.py says more.

OPTION --as-of (16 Oct 2026, D96, notes/demo-redesign-1016.md §1.9). The programme is fixed in time; what a viewer
reads as "now" depends on the real date (the commit week is the week holding today's Thursday). So the history —
typed actuals, the account week's shortages, the day actuals, the confirmations, the stockpile draw, the Pending and
Rejected lines — is typed up to an as-of date. Its default is SHIPPED_AS_OF, so a plain regeneration reproduces the
shipped history whichever session runs it. Any other date is accepted ONLY with --out to a path outside the checkout
(test_modus.py scans every .json in the repository for team-slot ids and allows only the shipped package).
OPTION --live-export (the same note, §1.9): with --as-of, copies the live demo's baked and fetched tables
(route_geometry, route_sections, route_area_km, areas, community_*, collision_*) and its carbon_target row from a
live export file (GET /api/admin/tenant/export) into the output, so a refresh needs no re-bake and no Fetch now.
It refuses when the live routes, gates or zones differ from the ones written here. Outside the checkout only: the
file holds HERE routes and OpenStreetMap-derived data.

WHAT IT MAKES
-------------
A fictional ~32 km A-ROAD DUALLING scheme in the East Midlands — "the Wolds Link",
running north from Market Harborough towards Melton Mowbray (H2, 5 Oct 2026: re-framed
from the v1 rail corridor for Highways UK) — with three quarries placed in the county's
real crushed-rock heartland under invented names, one rail freight terminal, four
compounds, three stockpiles, three delivery teams, six mainline work sections and two
point assets. Since 16 Oct 2026 (the demo redesign, notes/demo-redesign-1016.md, D95–D114) it is a FOUR-YEAR
PROGRAMME, north to south: main works from January 2026 (month 1), the northern half open December 2028, the whole
road October 2029, finishing works to December 2030 (month 60, the product's last). 905 approved line-months on 42
routes (R001–R043; R020 is the Carbon planner's alternative and carries none), plus one Pending and one Rejected
line on their own keys. Each section runs clearance → earthworks → drainage and capping → Type 1 → asphalt →
barrier and signs; the seasons bend it (earthworks April–October, thin surface course April–September, a two-week
Christmas stop). Earthworks appear only where they reach a public road (D98): the cut-to-fill haul on site is
moved by dumpers and is not shown. Sixteen sites: the fourteen of v2 plus a temporary on-site asphalt plant beside
Tilton Compound fed from the two quarries (D99; its feed on its own category with no material carbon, D112) and a
southern ready-mix plant (D100). The site settings of §1.8 (gate hours, check-ins, school-run bands, CLP caps,
Euro VI, stockpile sizes, the Burrough caps, zones, route-sheet words, site rules), contract rates and a target
rate, a fuel share, a carbon target (D105), GBP, miles, a UK country code, an alignment overlay with chainage,
package bands and boundaries, a gate or two on every site 35 m in from a public road with its access road drawn
as a haul road, two temporary haul roads ATTACHED to the routes that use them, closures and works areas dated
across the programme, and the tenant's demo notice on every screen and export. The concrete mixers carry the
ready-mixed concrete in m³ from the two batching plants.

NOTHING IN IT IS ANYONE'S DATA. Every name is invented; the quantities are sanity-checked against sourced UK rates
(the note's §1.6) and are otherwise ASSUMPTIONS; the coordinates are chosen so HERE's truck routing finds sensible
roads.

HOW IT MAKES IT
---------------
Not by hand-writing rows. It boots the product against a scratch SQLite database and
calls the same functions the app calls — create_location, create_route, the forecast
insert, weeks.materialise_window, set_actual, confirm_week, stockpiles.set_capacity,
tenant_package.set_overlay — then EXPORTS the tenant with tenant_package.export_tenant.
So every row in the package is one the product itself would have written, and the
package format is exercised end to end every time this runs. The programme itself is DATA (PROGRAMME below,
ported from the design tooling in notes/demo-redesign-1016/, which is not product code): one row per activity
with its month-by-month quantities; the line-months are those rows summed per (route, month, discipline, section,
vehicle), and the asphalt plant's feed is worked out from the asphalt it makes.

WHAT IT CANNOT MAKE
-------------------
Route geometry. Baking needs HERE, which is never called from a build sandbox. After
importing the package on a deployment, bake the network (Routes page → Bake all, or
POST /api/admin/bake-routes) for every vehicle the lines use. Until then every Look-ahead
line reads UNBAKED, by the product's own rule. A live refresh (--live-export) carries live's baked routes instead.
"""
import datetime
import json
import math
import os
import random
import sys
import tempfile
import types
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# --- stubs the backend needs outside a deployment -----------------------------------
if "flexpolyline" not in sys.modules:
    try:
        import flexpolyline  # noqa: F401
    except ImportError:
        _fp = types.ModuleType("flexpolyline")
        _fp.decode = lambda s: []
        _fp.encode = lambda pts: ""
        sys.modules["flexpolyline"] = _fp

os.environ.pop("DATABASE_URL", None)
os.environ["TENANT_ID"] = "wolds-link-demo"
TMP = tempfile.mkdtemp(prefix="modus_demo_")

import db                    # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "demo.db")
import conversions           # noqa: E402
import config                # noqa: E402
import taxonomy              # noqa: E402
import network               # noqa: E402
import weeks                 # noqa: E402
import days                  # noqa: E402
import stockpiles            # noqa: E402
import costing               # noqa: E402
import zones                 # noqa: E402
import gates                 # noqa: E402
import haul                  # noqa: E402
import carbon_target         # noqa: E402
import clashes               # noqa: E402
import tenant_package        # noqa: E402
import site_areas            # noqa: E402
import pours                 # noqa: E402

OUT = os.path.join(ROOT, "demo", "uk-corridor.package.json")
AREAS_SEED = os.path.join(BACKEND, "data", "areas_demo.geojson")   # --with-areas (§2.2b)
TENANT_NAME = "Wolds Link dualling — demo scheme"
DEMO_NOTICE = "Fictional scheme"   # 15 Oct 2026 (the user): the bar reads DEMO · FICTIONAL SCHEME (its badge says DEMO)
# 30 Oct 2026 (task 4b, John's yes): the contact lines the bulletin and the leaflet print, and the address behind the public map's
# "Report a concern" (John, 29 Oct: hello@wayscope.co.uk). The hours are the demo compounds' own (COMPOUND_HOURS below, DCO core
# hours); no phone and no newsletter link (the demo has no public page).
DEMO_CONTACT = {"concern_email": "hello@wayscope.co.uk",
                "working_hours": "Monday to Friday 07:30-18:00 (fictional scheme)",
                "other_formats": "email hello@wayscope.co.uk"}
START_YEAR = 2026
N_MONTHS = 60                     # Jan 2026 – Dec 2030: month_index = (year − 2026) × 12 + month
#: 31 Oct 2026 (task 4c PR 6): the drawing the demo's Tilton Viaduct layout is placed from, and what it must place
LAYOUT_SAMPLE = os.path.join(BACKEND, "tests", "fixtures", "site_layouts", "tilton-logistics-bng.dxf")
LAYOUT_THINGS = 39
SHIPPED_AS_OF = "2026-11-26"      # D96: Thursday, November week 4 — the shipped history; --as-of moves it (outside the checkout)
AS_OF = SHIPPED_AS_OF             # set by --as-of
LIVE_EXPORT = None                # set by --live-export

# ------------------------------------------------------------------------------------
#  Geometry helpers
# ------------------------------------------------------------------------------------
def metres(a, b):
    R = 6371000.0
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dlat = la2 - la1
    dlon = math.radians(b[0] - a[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def densify(waypoints, step_m=100.0):
    """A polyline through the waypoints with a vertex every ~step_m metres, plus the
    chainage (metres from the start) of every vertex."""
    pts, chain = [], []
    acc = 0.0
    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        d = metres(a, b)
        n = max(1, int(d // step_m))
        for k in range(n):
            t = k / n
            pts.append([round(a[0] + (b[0] - a[0]) * t, 6), round(a[1] + (b[1] - a[1]) * t, 6)])
            chain.append(acc + d * t)
        acc += d
    pts.append([waypoints[-1][0], waypoints[-1][1]])
    chain.append(acc)
    return pts, chain


def point_at(pts, chain, m):
    """The alignment point at chainage m (metres)."""
    for i in range(1, len(chain)):
        if chain[i] >= m:
            t = (m - chain[i - 1]) / max(1e-9, chain[i] - chain[i - 1])
            return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                    pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t]
    return pts[-1]


def offset(p, east_m=0.0, north_m=0.0):
    lat = p[1] + north_m / 111320.0
    lon = p[0] + east_m / (111320.0 * math.cos(math.radians(p[1])))
    return [round(lon, 6), round(lat, 6)]


def chain_text(m):
    v = int(round(m))
    return f"{v // 1000}+{v % 1000:03d}"


# ------------------------------------------------------------------------------------
#  The corridor
# ------------------------------------------------------------------------------------
# Waypoints (lon, lat): a plausible new dual carriageway east of Leicester, Market
# Harborough → Melton Mowbray. Fictional. Drawn across countryside, on no real road.
WAYPOINTS = [
    [-0.9060, 52.4790], [-0.9040, 52.5050], [-0.8990, 52.5300], [-0.9050, 52.5620],
    [-0.9000, 52.5950], [-0.8880, 52.6250], [-0.8790, 52.6580], [-0.8760, 52.6900],
    [-0.8720, 52.7200], [-0.8800, 52.7460], [-0.8870, 52.7620],
]
ALIGN_PTS, ALIGN_CHAIN = densify(WAYPOINTS, 100.0)
LENGTH_M = ALIGN_CHAIN[-1]
assert 31000 < LENGTH_M < 33000, LENGTH_M      # the section table below is sized to this

# Package bands along the corridor: three teams, six mainline sections.
# (section_id, name, team_id, design_section, chain_from, chain_to)
# Sized to the 31.8 km line; the last band runs to the end of the corridor. Names are
# taken from villages the fictional line passes; the features themselves are invented.
SECTIONS = [
    ("WS1", "Harborough approach", "IPT3", "DS1", 0, 5500),
    ("WS2", "Langton cutting", "IPT2", "DS1", 5500, 11000),
    ("WS3", "Noseley embankment", "IPT2", "DS1", 11000, 16500),
    ("WS4", "Tilton viaduct", "IPT1", "DS2", 16500, 21500),
    ("WS5", "Burrough Hill", "IPT1", "DS2", 21500, 26500),
    ("WS6", "Melton approach", "IPT1", "DS2", 26500, None),
]
DS_SPLIT_M = 16500                 # the design-section interface
POINT_SECTIONS = [
    ("WS7", "Noseley depot", "IPT2", "DS1", "WS3"),
    ("WS8", "Melton junction", "IPT1", "DS2", "WS6"),
]
TEAMS = [("IPT1", "North Team"), ("IPT2", "Central Team"), ("IPT3", "South Team")]
# the WS3/WS4 edge (the design-section interface) is the demo's one provisional boundary
PROVISIONAL_FROM, PROVISIONAL_WS, PROVISIONAL_AT = "WS3", "WS4", DS_SPLIT_M
assert [s for s in SECTIONS if s[0] == PROVISIONAL_WS][0][4] == PROVISIONAL_AT
# the same hexes the app paints team pills with (frontend IPT_PALETTE_C), so the map
# bands and the tables agree on a team's colour
BAND_COLOURS = {"IPT1": "#4C1D95", "IPT2": "#155E75", "IPT3": "#57534E"}


# ------------------------------------------------------------------------------------
#  The programme — DATA, ported from notes/demo-redesign-1016/ (16 Oct 2026; D95–D114)
# ------------------------------------------------------------------------------------
BALLAST, SMALL, EARTH = "Large aggregate / ballast", "Small aggregate", "Earthworks / soil"
PRECAST, GENERAL = "Precast / concrete", "General / imported"
# 29 Oct 2026 (3b, the steel split): the girders are Structural steel and the bar Reinforcement; the old Steel / rail is retired
STRUCT, REINF = "Structural steel", "Reinforcement"
# 29 Oct 2026 (3b-2): the reinforcement line is typed as m³ of concrete at the demo's own figure (see the forecasts step)
REBAR_KG_PER_M3, REBAR_STRUCTURE = 125, "Viaduct and overbridge (demo figure)"
READY, ASPHALT = "Ready-mixed concrete", "Asphalt"
FEED = "Aggregate for the asphalt plant"   # D112: the plant's feed, on its own category with NO material carbon
TIP, FLAT = "Artic Tipper (44t)", "Artic Flatbed (44t)"
MIX8, MIX6 = "Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)"   # the stored KEYS; every screen shows "Concrete mixer …"

# Every route, in id order: (origin, destination, material). R001–R022 keep their ends and materials (D101; Type 1
# rides "Large aggregate / ballast" and 6F2 "Small aggregate", as before); R023–R043 are appended. R020 (Langton
# Compound → the recycling hub) carries no forecast: it is the Carbon planner's disposal alternative.
ROUTES = [
    ("Q1", "C1", BALLAST), ("Q2", "C1", SMALL), ("RH", "C1", PRECAST),           # R001–R003
    ("Q1", "C2", BALLAST), ("Q2", "C2", SMALL), ("RH", "C2", GENERAL),           # R004–R006
    ("Q1", "C3", BALLAST), ("Q2", "C3", SMALL), ("RH", "C3", PRECAST),           # R007–R009
    ("Q1", "C4", BALLAST), ("Q2", "C4", SMALL), ("RH", "C4", GENERAL),           # R010–R012
    ("Q3", "C1", EARTH), ("Q3", "C2", EARTH), ("Q3", "S1", EARTH), ("Q3", "S3", EARTH),   # R013–R016
    ("Q1", "S2", BALLAST), ("Q2", "S3", SMALL),                                   # R017–R018
    ("C2", "TIP", EARTH), ("C2", "HUB", EARTH),                                   # R019–R020
    ("BP", "C3", READY), ("BP", "C4", READY),                                     # R021–R022
    ("Q3", "S2", EARTH), ("Q3", "C4", EARTH),                                     # R023–R024 imported fill, north
    ("C3", "TIP", EARTH), ("C1", "TIP", EARTH),                                   # R025–R026 exports to tip
    ("Q2", "AP", FEED), ("Q1", "AP", FEED),                                       # R027–R028 crushed rock into the asphalt plant
    ("AP", "C4", ASPHALT), ("AP", "C3", ASPHALT), ("AP", "C2", ASPHALT), ("AP", "C1", ASPHALT),   # R029–R032
    ("BP", "C2", READY), ("BP", "C1", READY),                                     # R033–R034 the long concrete hauls
    ("WR", "C2", READY), ("WR", "C1", READY),                                     # R035–R036 the southern ready-mix plant
    ("RH", "C3", GENERAL), ("RH", "C1", GENERAL), ("RH", "C2", PRECAST), ("RH", "C4", PRECAST),   # R037–R040
    ("Q2", "S1", SMALL), ("Q2", "S2", SMALL),                                     # R041–R042 capping stockpiled
    ("Q2", "C2", ASPHALT),                                                        # R043 a quarry coating plant (2030)
    # 28 Oct 2026 (simulation v2, task 0e): the Tilton Viaduct site — stone and concrete to the pier bases, reinforcement,
    # steel and precast to the laydown, piling arisings out to the tip (muck away: the empty lorry comes to LOAD)
    ("Q1", "VS", BALLAST), ("Q2", "VS", SMALL), ("RH", "VS", REINF), ("RH", "VS", PRECAST), ("RH", "VS", STRUCT),   # R044–R048 (R046 / R048 renamed 29 Oct, 3b)
    ("BP", "VS", READY), ("VS", "TIP", EARTH),                                    # R049–R050
]
assert len(ROUTES) == 50 and len(set(ROUTES)) == 50
ROUTE_ID = {r: f"R{i + 1:03d}" for i, r in enumerate(ROUTES)}

# Every activity: (section, discipline, material, origin, destination, vehicle, unit, first month, the quantity in
# each month from the first (t, or m³ for concrete; 0 = nothing that month), description). The months were spread by
# the design tooling (programme.py: a trapezoid × the sourced seasons × Christmas, rounded to 100 t / 10 m³) and are
# typed here as figures. A forecast line-month is every activity on the same (route, month, discipline, section,
# vehicle) summed, its descriptions joined with " + ". Order matters only for that join.
PROGRAMME = [
    ("WS6", "substructure", BALLAST, "Q1", "C4", TIP, "t", 1, [4500, 5500], "Compound platform and haul road stone (Type 1)"),
    ("WS6", "substructure", GENERAL, "RH", "C4", FLAT, "t", 1, [100, 200], "Site cabins, welfare units and fencing"),
    ("WS4", "substructure", BALLAST, "Q1", "C3", TIP, "t", 2, [3200, 4300, 4300, 3200], "Tilton Compound platform, piling mat and plant hardstanding stone (Type 1)"),
    ("WS4", "substructure", GENERAL, "RH", "C3", FLAT, "t", 2, [200, 100], "Site cabins, welfare units and fencing"),
    ("WS6", "earthworks", EARTH, "Q3", "C4", TIP, "t", 6, [1300, 1800, 2200, 2400, 1700, 600, 200, 300, 400, 1100, 1700, 1300], "Imported granular fill (Class 6N) — structure backfill"),
    ("WS6", "substructure", SMALL, "Q2", "C4", TIP, "t", 6, [2400, 3400, 4200, 4200, 4200, 3400, 1500, 1800, 1400], "Pipe bedding and filter drain stone"),
    ("WS6", "substructure", PRECAST, "RH", "C4", FLAT, "t", 6, [200, 300, 400, 400, 400, 300, 200, 200], "Drainage pipes, chambers and culvert units"),
    ("WS6", "substructure", SMALL, "Q2", "C4", TIP, "t", 9, [5400, 6500, 4500, 2100, 3100, 3500, 7900, 9900, 9900, 9000, 7200, 5400], "6F2 capping"),
    ("WS6", "superstructure", BALLAST, "Q1", "C4", TIP, "t", 22, [16700, 18500, 7400, 11900, 13200, 15000], "Type 1 sub-base"),
    ("WS6", "superstructure", ASPHALT, "AP", "C4", TIP, "t", 27, [9700, 19000, 19000, 19000, 19000, 12100], "Asphalt base and binder course"),
    ("WS6", "superstructure", ASPHALT, "AP", "C4", TIP, "t", 31, [4200, 5900, 5800], "Asphalt surface course"),
    ("WS6", "substructure", GENERAL, "RH", "C4", FLAT, "t", 29, [100, 100, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS6", "structures", READY, "BP", "C4", MIX8, "m3", 4, [310, 410, 500, 580, 580, 580, 580, 580, 320, 410, 430, 410, 310], "C32/40 concrete — WS6 culverts and overbridge"),
    ("WS6", "substructure", READY, "BP", "C4", MIX6, "m3", 12, [50, 80, 110, 150, 170, 180, 190, 190, 190, 190, 190, 190, 110, 140, 160, 190, 190, 180, 170, 150, 130, 110, 90], "C20/25 concrete — kerb bedding, drainage surrounds, barrier footings"),
    ("WS6", "structures", GENERAL, "RH", "C4", FLAT, "t", 6, [100, 100, 100, 100, 100, 100, 0, 100], "Reinforcement — WS6 structures"),
    ("WS8", "structures", READY, "BP", "C4", MIX8, "m3", 3, [320, 390, 460, 540, 610, 610, 610, 610, 610, 350, 440, 520, 610, 610, 540, 460, 390, 320], "C32/40 concrete — Melton junction bridges"),
    ("WS8", "structures", GENERAL, "RH", "C4", FLAT, "t", 6, [100, 100, 100, 100, 100, 100, 0, 100, 100, 100, 100, 100], "Reinforcement — Melton junction bridges"),
    ("WS5", "earthworks", EARTH, "Q3", "S3", TIP, "t", 10, [1000, 500, 200, 400, 400, 1300, 2600, 2600, 2500, 2000, 1500], "Imported granular fill (Class 6N) — structure backfill"),
    ("WS5", "substructure", SMALL, "Q2", "S3", TIP, "t", 10, [1600, 1700, 900, 1500, 1700, 2600, 2900, 2900, 2900, 2600, 2100, 1600], "Pipe bedding and filter drain stone"),
    ("WS5", "substructure", SMALL, "Q2", "S3", TIP, "t", 11, [2300, 1500, 3000, 3900, 4300, 4300, 4300, 4300, 4300, 4300, 4300, 3700, 3000, 1100], "6F2 capping (stockpiled at Stockpile North)"),
    ("WS5", "superstructure", BALLAST, "Q1", "C4", TIP, "t", 24, [3700, 9000, 10000, 17900, 13400], "Type 1 sub-base"),
    ("WS5", "superstructure", ASPHALT, "AP", "C4", TIP, "t", 28, [7700, 12200, 12100, 12100, 12100, 7700], "Asphalt base and binder course"),
    ("WS5", "superstructure", ASPHALT, "AP", "C4", TIP, "t", 31, [2800, 3800, 3800], "Asphalt surface course"),
    ("WS5", "substructure", GENERAL, "RH", "C4", FLAT, "t", 29, [100, 100, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS5", "structures", READY, "BP", "C4", MIX8, "m3", 8, [520, 670, 810, 960, 560, 720, 840, 990, 990, 990, 990, 960, 810, 670, 520], "C32/40 concrete — Burrough Road overbridge and accommodation bridges"),
    ("WS5", "substructure", READY, "BP", "C4", MIX6, "m3", 20, [150, 190, 240, 280, 160, 210, 250, 290, 290, 290, 290, 280, 240, 190, 150], "C20/25 concrete — kerb bedding, drainage surrounds, barrier footings"),
    ("WS5", "structures", GENERAL, "RH", "C4", FLAT, "t", 8, [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100], "Reinforcement — WS5 structures"),
    ("WS5", "structures", PRECAST, "RH", "C4", FLAT, "t", 10, [100, 200, 200, 200, 300, 300, 200, 200, 200, 200, 100], "Precast culvert units and parapets"),
    ("WS4", "earthworks", EARTH, "Q3", "S2", TIP, "t", 7, [1400, 1700, 2100, 1700, 700, 200, 400, 400, 1300, 2600, 2600, 2600, 2500, 2100, 1700, 1000], "Imported granular fill to the viaduct approaches"),
    # 29 Oct 2026 (John: the Simulation must show at least six lorries queuing, the prep for the vehicle holding areas):
    # the south approach cutting is dug to tip in Mar–May 2027, the three months the viaduct's gate out is closed —
    # 38,000 / 42,000 / 38,000 t, about 60–66 tipper loads a day against the Spoil loading bay's six an hour, so
    # 7–11 lorries wait there by mid-afternoon (sized on a copy of the demo; session-1028-sim-v2.md §8)
    ("WS4", "earthworks", EARTH, "VS", "TIP", TIP, "t", 5, [800, 1000, 1200, 1400, 1600, 1600, 1600, 900, 1100, 1300, 38000, 42000, 38000, 1200, 1000, 800], "Piling arisings, unsuitable material and the south approach cutting to tip"),
    ("WS4", "structures", READY, "BP", "VS", MIX8, "m3", 5, [840, 1070, 1290, 1510, 1630, 1630, 1620, 910, 1170, 1380, 1620, 1620, 1510, 1290, 1070, 840], "C32/40 concrete — Tilton viaduct piles, pile caps, piers and abutments"),
    ("WS4", "structures", READY, "BP", "VS", MIX8, "m3", 23, [580, 500, 690, 810, 960, 880, 580], "C32/40 concrete — Tilton viaduct deck slab, edge beams and approach slabs"),
    ("WS4", "structures", READY, "BP", "C3", MIX8, "m3", 10, [260, 340, 230, 350, 430, 500, 500, 500, 500, 500, 500, 490, 410, 340, 150], "C32/40 concrete — A47 junction overbridge"),
    ("WS4", "structures", REINF, "RH", "VS", FLAT, "t", 5, [100, 100, 100, 100, 100, 200, 200, 100, 100, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100, 100, 100, 100, 100, 100, 100], "Reinforcement — Tilton viaduct and A47 junction"),
    # 28 Oct 2026 (simulation v2): the viaduct site's own lines — the piling mat and pier drainage stone in, the deck's
    # structural steel (the longest girders go as abnormal loads, not here) and the precast parapets
    ("WS4", "substructure", BALLAST, "Q1", "VS", TIP, "t", 5, [2600, 3100, 3100, 2200, 1400], "Piling mat and working platform stone at the viaduct site (Type 1)"),
    ("WS4", "substructure", SMALL, "Q2", "VS", TIP, "t", 9, [900, 1200, 1200, 900], "Pier drainage and bedding stone"),
    ("WS4", "structures", STRUCT, "RH", "VS", FLAT, "t", 14, [300, 500, 600, 600, 600, 600, 500, 400, 300], "Structural steel girders for the composite deck (the longest go as abnormal loads)"),
    ("WS4", "structures", PRECAST, "RH", "VS", FLAT, "t", 24, [200, 300, 300, 300, 300, 200], "Precast parapet and deck edge units"),
    ("WS4", "substructure", SMALL, "Q2", "C3", TIP, "t", 12, [400, 800, 1100, 1900, 2200, 2200, 2100, 2100, 2100, 2100, 2100, 1700, 600, 800, 700], "Pipe bedding and filter drain stone"),
    ("WS4", "substructure", PRECAST, "RH", "C3", FLAT, "t", 12, [100, 100, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100], "Drainage pipes, chambers and culvert units"),
    ("WS4", "substructure", SMALL, "Q2", "S2", TIP, "t", 18, [4000, 5600, 7200, 7200, 7200, 7200, 3500, 5900, 5100, 4000], "6F2 capping (stockpiled at Stockpile Tilton)"),
    ("WS4", "superstructure", BALLAST, "Q1", "S2", TIP, "t", 23, [7300, 5400, 9700, 10700, 11900, 11000, 7200], "Type 1 sub-base (from Stockpile Tilton)"),
    ("WS4", "superstructure", ASPHALT, "AP", "C3", TIP, "t", 28, [9800, 15500, 15500, 15500, 15500, 9800], "Asphalt base and binder course"),
    ("WS4", "superstructure", ASPHALT, "AP", "C3", TIP, "t", 32, [6000, 7300], "Asphalt surface course"),
    ("WS4", "substructure", GENERAL, "RH", "C3", FLAT, "t", 30, [100, 100, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS4", "substructure", READY, "BP", "C3", MIX6, "m3", 22, [180, 240, 160, 240, 280, 340, 340, 340, 340, 330, 290, 240, 180], "C20/25 concrete — kerb bedding, drainage surrounds, barrier footings"),
    ("WS3", "substructure", BALLAST, "Q1", "C2", TIP, "t", 11, [2700, 2500, 3200, 4000, 2600], "Haul road and working platform stone (Type 1)"),
    ("WS3", "substructure", GENERAL, "RH", "C2", FLAT, "t", 11, [200, 100], "Site cabins, welfare units and fencing"),
    ("WS3", "earthworks", EARTH, "Q3", "C2", TIP, "t", 16, [1800, 2200, 2700, 3100, 3500, 3500, 2500, 900, 200, 500, 500, 1800, 3500, 3500, 3100, 2700, 2200, 1800], "Imported granular drainage blanket and culvert backfill"),
    ("WS3", "structures", PRECAST, "RH", "C2", FLAT, "t", 15, [200, 200, 300, 200, 200, 200, 200], "Precast box culverts (three watercourse crossings)"),
    ("WS3", "substructure", SMALL, "Q2", "C2", TIP, "t", 22, [1300, 1400, 700, 1300, 1500, 2300, 2500, 2500, 2500, 2500, 2500, 2500, 2100, 1400, 500], "Pipe bedding and filter drain stone"),
    ("WS3", "substructure", SMALL, "Q2", "C2", TIP, "t", 29, [5000, 7100, 8700, 8700, 8700, 7800, 4400, 1500, 1600], "6F2 capping"),
    ("WS3", "superstructure", BALLAST, "Q1", "C2", TIP, "t", 35, [8200, 5200, 8300, 9300, 16700, 11700], "Type 1 sub-base"),
    ("WS3", "superstructure", ASPHALT, "AP", "C2", TIP, "t", 38, [3900, 9300, 12600, 12600, 12600, 11600, 7700], "Asphalt base and binder course"),
    ("WS3", "superstructure", ASPHALT, "AP", "C2", TIP, "t", 43, [3600, 4300, 3500], "Asphalt surface course"),
    ("WS3", "substructure", GENERAL, "RH", "C2", FLAT, "t", 41, [100, 200, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS3", "structures", READY, "BP", "C2", MIX8, "m3", 14, [170, 240, 190], "C32/40 concrete — culvert bases and headwalls (before the southern plant)"),
    ("WS3", "structures", READY, "BP", "C3", MIX8, "m3", 13, [50, 80, 100, 70], "C32/40 concrete — WS3 north culvert, delivered via Tilton Compound"),
    ("WS3", "structures", READY, "WR", "C2", MIX8, "m3", 17, [570, 800, 1020, 1020, 1020, 1020, 1020, 570, 570, 490], "C32/40 concrete — culverts and Noseley underpass"),
    ("WS7", "structures", READY, "WR", "C2", MIX8, "m3", 34, [120, 140, 100, 150, 190, 230, 230, 230, 230, 220, 220, 220, 220, 200, 100, 100, 100], "C25/30 concrete — Noseley depot slabs and salt barn"),
    ("WS7", "structures", GENERAL, "RH", "C2", FLAT, "t", 38, [100, 100, 100, 100], "Reinforcement — Noseley depot"),
    ("WS2", "earthworks", EARTH, "C2", "TIP", TIP, "t", 16, [5400, 6700, 8000, 9300, 10600, 10600, 7400, 2600, 700, 1400, 1600, 5300, 10500, 10500, 9300, 8000, 6700, 5400], "Surplus and unsuitable cut to tip (Langton cutting)"),
    ("WS2", "structures", READY, "WR", "C2", MIX8, "m3", 17, [520, 670, 810, 960, 990, 990, 990, 560, 720, 840, 990, 960, 810, 670, 520], "C32/40 concrete — Langton Road overbridge and accommodation bridges"),
    ("WS2", "structures", GENERAL, "RH", "C2", FLAT, "t", 15, [100, 100, 100, 200, 200, 200, 200, 200, 200, 100, 200, 200, 200, 100, 100, 100], "Reinforcement — WS2 and WS3 structures"),
    ("WS2", "substructure", SMALL, "Q2", "C2", TIP, "t", 22, [1300, 1300, 700, 1200, 1400, 2200, 2400, 2400, 2400, 2400, 2400, 2400, 2200, 1500, 600, 700], "Pipe bedding and filter drain stone"),
    ("WS2", "substructure", PRECAST, "RH", "C2", FLAT, "t", 22, [100, 200, 100, 200, 300, 300, 200, 200, 200, 200, 200, 200, 100], "Drainage pipes and chambers"),
    ("WS2", "substructure", SMALL, "Q2", "C2", TIP, "t", 30, [6000, 8800, 10300, 10300, 9200, 5100, 1900, 1900], "6F2 capping"),
    ("WS2", "superstructure", BALLAST, "Q1", "C2", TIP, "t", 35, [8200, 5200, 8300, 9300, 16700, 11700], "Type 1 sub-base"),
    ("WS2", "superstructure", ASPHALT, "AP", "C2", TIP, "t", 38, [3900, 9300, 12600, 12600, 12600, 11600, 7700], "Asphalt base and binder course"),
    ("WS2", "superstructure", ASPHALT, "AP", "C2", TIP, "t", 43, [3600, 4300, 3500], "Asphalt surface course"),
    ("WS2", "substructure", GENERAL, "RH", "C2", FLAT, "t", 41, [100, 200, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS2", "substructure", READY, "WR", "C2", MIX6, "m3", 34, [400, 530, 370, 530, 620, 740, 740, 740, 730, 670, 530, 400], "C20/25 concrete — kerb bedding, drainage surrounds, barrier footings"),
    ("WS1", "substructure", BALLAST, "Q1", "C1", TIP, "t", 10, [2800, 3400, 1800], "Compound platform stone (Type 1)"),
    ("WS1", "substructure", GENERAL, "RH", "C1", FLAT, "t", 10, [100, 100, 100], "Site fencing, cabins and welfare units"),
    ("WS1", "structures", EARTH, "Q3", "C1", TIP, "t", 20, [900, 1300, 1200, 400, 100, 200, 300, 700, 900], "Class 6N backfill to the Welham Lane underpass"),
    ("WS1", "earthworks", EARTH, "Q3", "S1", TIP, "t", 16, [1300, 1700, 2100, 2400, 2600, 2600, 1800, 700, 200, 400, 400, 1300, 2400, 2100, 1700, 1300], "Imported granular fill (Class 1A) — low embankments"),
    ("WS1", "earthworks", EARTH, "C1", "TIP", TIP, "t", 16, [1100, 1400, 1700, 1900, 2100, 2100, 1500, 500, 100, 300, 300, 1000, 1900, 1600, 1400, 1100], "Unsuitable material to tip"),
    ("WS1", "structures", READY, "BP", "C1", MIX8, "m3", 16, [300], "C32/40 concrete — Welham Lane underpass base (before the southern plant)"),
    ("WS1", "structures", READY, "WR", "C1", MIX8, "m3", 17, [460, 590, 730, 860, 860, 860, 860, 480, 620, 740, 860, 730, 590, 460], "C32/40 concrete — Welham Lane underpass, culverts, accommodation bridge"),
    ("WS1", "structures", GENERAL, "RH", "C1", FLAT, "t", 17, [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100], "Reinforcement — WS1 structures"),
    ("WS1", "substructure", SMALL, "Q2", "C1", TIP, "t", 23, [1100, 600, 1100, 1500, 2300, 2600, 2600, 2600, 2600, 2500, 2500, 2500, 1700, 600, 700], "Pipe bedding and filter drain stone"),
    ("WS1", "substructure", PRECAST, "RH", "C1", FLAT, "t", 23, [100, 100, 200, 300, 300, 300, 300, 200, 200, 200, 200, 100], "Drainage pipes, chambers and culvert units"),
    ("WS1", "substructure", SMALL, "Q2", "S1", TIP, "t", 30, [6900, 10100, 11700, 11700, 11700, 11700, 4900, 5500], "6F2 capping (stockpiled at Stockpile South)"),
    ("WS1", "superstructure", BALLAST, "Q1", "C1", TIP, "t", 35, [11400, 7200, 11600, 12900, 23100, 16300], "Type 1 sub-base"),
    ("WS1", "superstructure", ASPHALT, "AP", "C1", TIP, "t", 38, [5300, 12900, 17500, 17500, 17500, 16200, 10700], "Asphalt base and binder course"),
    ("WS1", "superstructure", ASPHALT, "AP", "C1", TIP, "t", 43, [4900, 6100, 4900], "Asphalt surface course"),
    ("WS1", "substructure", GENERAL, "RH", "C1", FLAT, "t", 41, [100, 200, 100, 100, 100, 100], "Safety barrier, signs, lighting and fencing"),
    ("WS1", "substructure", READY, "WR", "C1", MIX6, "m3", 34, [200, 270, 190, 260, 310, 370, 370, 370, 370, 330, 260, 200], "C20/25 concrete — kerb bedding, drainage surrounds, barrier footings"),
    ("WS1", "superstructure", ASPHALT, "AP", "C1", TIP, "t", 45, [4000], "Tie-in surfacing at the Harborough end and the A47 junction (night works)"),
    ("WS2", "substructure", GENERAL, "RH", "C2", FLAT, "t", 45, [200, 200, 200], "Signs, road-marking materials and the last safety barrier"),
    ("WS3", "superstructure", BALLAST, "Q1", "C2", TIP, "t", 51, [1100, 1900, 1900, 1900, 1200], "Side-road and accommodation-track reconstruction (Type 1)"),
    ("WS3", "superstructure", ASPHALT, "Q2", "C2", TIP, "t", 52, [3700, 4600, 3700], "Old road resurfaced as it is handed back (de-trunking) and side roads, from a quarry coating plant"),
    ("WS1", "earthworks", EARTH, "C1", "TIP", TIP, "t", 48, [200, 700, 800, 2700, 3600], "Compound platform stone lifted and taken to the inert landfill"),
    ("WS2", "earthworks", EARTH, "C2", "TIP", TIP, "t", 49, [600, 900, 3100, 6200, 4200], "Compound platform stone lifted and taken to the inert landfill"),
    ("WS4", "earthworks", EARTH, "C3", "TIP", TIP, "t", 47, [8000, 2700, 4300], "Asphalt plant and Tilton Compound platform stone lifted and taken to the inert landfill"),
    ("WS1", "earthworks", GENERAL, "RH", "C1", FLAT, "t", 46, [100, 100, 100, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100, 100, 100], "Fencing, planting and environmental mitigation"),
    ("WS3", "earthworks", GENERAL, "RH", "C2", FLAT, "t", 46, [100, 100, 100, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100, 100, 100], "Fencing, planting and environmental mitigation"),
    ("WS6", "earthworks", GENERAL, "RH", "C4", FLAT, "t", 46, [100, 100, 100, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100, 100, 100], "Fencing, planting and environmental mitigation"),
    ("WS7", "structures", PRECAST, "RH", "C2", FLAT, "t", 42, [100, 200, 200, 200, 200, 200, 100, 200, 100], "Noseley depot: precast salt barn panels and drainage"),
]
# The asphalt plant's feed (D112): crushed rock at PLANT_FEED_SHARE of each tonne of asphalt it makes, split between
# the two quarries, booked to the section (and so the team) whose asphalt it makes, rounded to 100 t per quarry.
PLANT_FEED_SHARE = 0.95          # Heidelberg Materials: asphalt is "approx. 95 %" aggregate (by weight: ASSUMPTION)
PLANT_FEED_Q2 = 0.6              # 60 % Northfield, 40 % Kilby Ridge (ASSUMPTION)
FEED_DESC = "Crushed rock for the asphalt plant (coarse and fine aggregate)"

# The approval step (§1.9): one Pending and one Rejected line, each on its own line key (approval acts on every month
# of a line). (route, discipline, section, t, material description, reason)
#: 31 Oct 2026 (task 4a PR 3c, Q11): the demo's one client reviewer group (id, name, when made); no reviewer logins
DEMO_REVIEW_GROUP = ("rg-demo", "Highways client (fictional)", "2026-10-31T00:00:00Z")

#: 29 Oct 2026 (task 3a, John's Q10 "as recommended"): the planned concrete pours, on the batching plant's lines. When:
#: "as-of thursday" / "next tuesday" follow the as-of date (so the Look-ahead's this week / next week each show one), or a
#: fixed date. A pour whose line does not run in that month is left out (an as-of outside the line's months). The mixers
#: booked and the wash-out minutes are FICTIONAL, like the plant; the drive times are whatever the routes give.
#: (origin, destination, material, section, discipline, when, start, m³, m³ an hour, mixers booked, wash-out min, where,
#:  how)
DEMO_POURS = [
    ("BP", "VS", None, "WS4", "structures", "as-of thursday", "09:15", 60.0, 20.0, None, 10.0,
     "Pier 2 pile cap (fictional)", "Pump"),
    ("BP", "C4", None, "WS8", "structures", "next tuesday", "09:15", 180.0, 40.0, 6, 10.0,
     "Melton junction bridge deck (fictional)", "Pump"),
    ("BP", "VS", None, "WS4", "structures", "2028-04-19", "07:00", 400.0, 60.0, None, 10.0,
     "Viaduct deck slab, span 3 (fictional)", "Two pumps"),
]


def demo_pour_date(when, as_of):
    """The date a DEMO_POURS row names: the as-of week's Thursday, next week's Tuesday, or the date itself."""
    mon = as_of - datetime.timedelta(days=as_of.weekday())
    if when == "as-of thursday":
        return mon + datetime.timedelta(days=3)
    if when == "next tuesday":
        return mon + datetime.timedelta(days=8)
    return datetime.date.fromisoformat(when)


PENDING = ("R013", "earthworks", "WS1", 6400.0, "Imported Class 1A for the Harborough South roundabout embankment")
REJECTED = ("R005", "earthworks", "WS2", 24000.0, "Granular fill (6F2) for the Langton cutting embankments",
            "24,000 t in one month is more than Langton can place before the capping starts: resubmit spread over "
            "the earthworks season.")
EARTHWORKS_SEASON = range(4, 11)  # April–October (§1.3)

# The stockpiles' draw (§1.9, ASSUMPTION; reworked 28 Oct 2026, task 0b): a pile gives out what its sections LAY, and a
# crew lays at a pace, so the draw is a laying programme, not "everything the moment it lands". Each pile has a full
# laying rate (t a week, one or two capping / sub-base crews) in the laying season (April-October); out of season the
# formation is not left exposed and frozen material is unacceptable (SHW Series 600), so North and South lay nothing in
# November-March (the winter nudge of 27 Oct: North, filling all winter, goes over its 25 000 t in March 2027), while
# Tilton's Type 1 sub-base goes down on weather windows at WINTER_PACE of the full rate. A week lays the smaller of the
# rate and what the site can take from the pile: LAY_FROM_ARRIVALS of the week's arrivals plus LAY_FROM_STOCK of the
# stock held (so a pile never runs to nothing and there is always some in it). What was typed on site drifts from
# this plan (actual_draw below): faster and slower weeks, rain, and the stock counts.
LAY_RATE = {"S1": 3000.0, "S2": 4000.0, "S3": 2200.0}     # t a week, in season
WINTER_PACE = {"S1": 0.0, "S2": 0.55, "S3": 0.0}          # share of the rate laid November-March
LAY_FROM_ARRIVALS, LAY_FROM_STOCK = 0.6, 0.35
PILE_RESIDUE = 800.0                                      # t left in a pile when the programme has finished with it
#: planned use above what the pile will hold: Stockpile Tilton's July 2027 lay-down is planned for 3 500 t more than
#: July's arrivals and the stock held can cover, so the plan runs it out and August's deliveries top it up (the demo's
#: "runs short" story)
PLAN_SURGE = {("S2", 19): 3500.0}
#: stock counts the site types: (pile, month_index, week_index, tonnes above (+) or below (-) the book stock, by)
COUNTS = [("S2", 9, 3, 180.0, "Survey: more in the pile than the book says"),
          ("S3", 11, 2, -240.0, "Survey: less than the book says (wet fines and haul-road waste)")]
#: weeks that were laid slower (rain) or faster (catching up): (pile, month_index, week_index) -> share of the plan
ACTUAL_PACE = {("S2", 8, 2): 0.45, ("S2", 9, 4): 1.25, ("S2", 10, 2): 0.55, ("S3", 11, 1): 0.6}


def lay_draw(key, cal_m, held, week_in):
    """One week's planned laying from the pile `key` (a gate-key S1/S2/S3), tonnes."""
    f = 1.0 if 4 <= cal_m <= 10 else WINTER_PACE[key]
    if f <= 0:
        return 0.0
    return min(LAY_RATE[key] * f, (LAY_FROM_ARRIVALS * week_in + LAY_FROM_STOCK * held) * f)


def actual_draw(key, m, wk, planned):
    """What was typed as laid that week: the plan, drifted (+/- about 10 % by a fixed hash), or a week from ACTUAL_PACE."""
    if planned <= 0:
        return 0.0, None
    pace = ACTUAL_PACE.get((key, m, wk))
    if pace is None:
        pace = 0.9 + (zlib.crc32(f"{key}:{m}:{wk}".encode()) % 1000) / 1000.0 * 0.2
    note = (RAIN_NOTE if pace < 0.8 else "Extra capping laid to catch up" if pace > 1.1 else "Laid on the section")
    return planned * pace, note


RAIN_NOTE = "Rain: formation covered, capping stood down Tue–Wed"


def programme_lines():
    """{(origin, dest, material, discipline, section, vehicle, unit, month): [quantity, [descriptions]]} — the
    PROGRAMME summed per line-month, plus the asphalt plant's feed. Pure: no database."""
    lines, made = {}, {}
    for sec, disc, mat, o, d, veh, unit, m0, qs, desc in PROGRAMME:
        assert (o, d, mat) in ROUTE_ID, (o, d, mat)
        for i, q in enumerate(qs):
            if not q:
                continue
            m = m0 + i
            assert 1 <= m <= N_MONTHS, (sec, desc, m)
            e = lines.setdefault((o, d, mat, disc, sec, veh, unit, m), [0.0, []])
            e[0] += q
            if desc not in e[1]:
                e[1].append(desc)
            if o == "AP":
                made[(m, sec)] = made.get((m, sec), 0.0) + q
    for (m, sec), t in sorted(made.items()):
        agg = t * PLANT_FEED_SHARE
        for o, share in (("Q2", PLANT_FEED_Q2), ("Q1", 1 - PLANT_FEED_Q2)):
            q = round(agg * share / 100.0) * 100
            if q > 0:
                e = lines.setdefault((o, "AP", FEED, "superstructure", sec, TIP, "t", m), [0.0, []])
                e[0] += q
                e[1] = [FEED_DESC]
    return lines


def month_index_of(year, month):
    return (year - START_YEAR) * 12 + month


def _date(s):
    return datetime.date.fromisoformat(s) if isinstance(s, str) else s


def pending_month(as_of_month):
    """The first earthworks-season month at least two months after the as-of month (Apr 2027 for 26 Nov 2026)."""
    m = as_of_month + 2
    while (m - 1) % 12 + 1 not in EARTHWORKS_SEASON:
        m += 1
    return min(m, N_MONTHS)


def _outside_checkout(path):
    p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    r = os.path.normcase(os.path.realpath(ROOT))
    try:
        return os.path.commonpath([p, r]) != r
    except ValueError:          # another drive on Windows
        return True


def stock_plan_rows(loc):
    """Write stockpile_plan for the three stockpiles from the draw model over the planned deliveries (plan §6)."""
    tenant = db.current_tenant()
    planned = {}
    for r in db.query("SELECT f.month_index, f.quantity, f.unit, r.dest_id FROM forecasts f JOIN routes r "
                      "ON r.tenant_id = f.tenant_id AND r.id = f.route_id "
                      "WHERE f.tenant_id = ? AND f.status = 'Approved'", (tenant,)):
        if r["dest_id"] in [loc[k] for k in ("S1", "S2", "S3")]:
            assert (r["unit"] or "t") == "t", r
            k = (r["dest_id"], int(r["month_index"]))
            planned[k] = planned.get(k, 0.0) + float(r["quantity"] or 0)
    last = max(m for (_, m) in planned)
    for key in ("S1", "S2", "S3"):
        lid, held = loc[key], 0.0
        for m in range(1, min(last + 6, 60) + 1):      # six months past the last delivery: the stock still held is laid
            nw = weeks.weeks_in_month(m)
            week_in = planned.get((lid, m), 0.0) / nw
            cal_m = (m - 1) % 12 + 1
            used = 0.0
            done = not any(mm >= m for (l, mm) in planned if l == lid)       # no delivery from this month on
            for _ in range(nw):
                # after the last delivery the stock held is laid out at the full rate in the first laying season, down
                # to PILE_RESIDUE (the last of any pile stays for the reinstatement; it also absorbs a stock count)
                if done:
                    draw = min(LAY_RATE[key], max(0.0, held + week_in - PILE_RESIDUE)) if 4 <= cal_m <= 10 else 0.0
                else:
                    draw = lay_draw(key, cal_m, held, week_in)
                held = held + week_in - draw
                used += draw
            extra = PLAN_SURGE.get((key, m), 0.0)
            used += extra
            held = max(0.0, held - extra)           # a surge takes what the pile holds; the rest of it is the shortfall
            if used >= 0.5 or not done:
                res = stockpiles.set_plan(lid, m, m, planned_qty=round(used), by="tools/make_demo_tenant.py")
                assert "error" not in res, res


def build(with_areas=False, out=None):
    out = out or OUT
    as_of = _date(AS_OF)
    # --- schema, seeds -----------------------------------------------------------
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    # v2 (H2): the generic discipline seed is written for a railway; this tenant is a road.
    # Same ids (the forecasts key on them), road words on the labels and notes, and the
    # railway-only discipline out of scope so no picker offers it.
    for did, label, note, in_scope in (
            ("superstructure", "Pavement", "Sub-base, base, binder and surface courses.", True),
            ("substructure", "Substructure", "Capping, drainage, kerbs, foundations below the pavement.", True),
            ("structures", "Structures", "Bridges, culverts, retaining walls, noise barriers.", True),
            ("earthworks", "Earthworks", "Imported fill and exports to tip on public roads; cut to fill is moved on site by dumpers.", True),
            ("stations", "Stations", "Not part of a road scheme.", False)):
        db.execute("UPDATE disciplines SET label = ?, scope_note = ?, in_scope = ? WHERE tenant_id = ? AND id = ?",
                   (label, note, in_scope, db.current_tenant(), did))

    # --- the tenant block, GBP, UK --------------------------------------------------
    doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
    # H1 (29 Sep 2026): GB, GBP, and the tenant READS MILES (HU5, per tenant; km is stored)
    # 13 Oct 2026 (W12): the council carbon bands, 20 / 50 / 100 t in the month, chosen from the LIVE demo's district
    # figures for Sep-Dec 2026. 16 Oct 2026 (the redesign §4.1): held until the first live bake of the four-year
    # programme, when they are re-chosen from its district figures (R3b) and written here.
    # 18 Oct 2026 (R3b): re-chosen from the LIVE four-year demo's district figures over all 60 months, after its first
    # live bake (U8a): 349 district-months with traffic (the county left out: the map draws it as an outline). Carbon
    # 10 / 25 / 50 t in the month and movements 25 / 50 / 100 a day put about 57 / 23 / 13 / 7 % and 55 / 19 / 19 / 7 % of
    # them in the four steps; the old 20 / 50 / 100 and the product's 50 / 100 / 200 left three quarters in the palest.
    # The user saved them on live the same day.
    doc["tenant"] = {"name": TENANT_NAME, "team_label": "Team", "currency": "GBP", "country": "GB",
                     "distance_unit": "mi", "demo_notice": DEMO_NOTICE,
                     # 30 Oct 2026 (3d, John): where the public map's "Report a concern" link goes. The company's
                     # own address, not a person's; before this it was never saved on live. Task 4b: DEMO_CONTACT holds
                     # it with the leaflet's hours and other formats.
                     "council_breaks": {"movements": [25, 50, 100], "carbon": [10, 25, 50]}, **DEMO_CONTACT}
    # D106: NO seasonal windows — the product's are scheme-wide by calendar month and meant for statutory
    # restrictions; Market Harborough's Christmas trading goes in as an advisory zone each December instead.
    doc["seasonal_restrictions"] = []
    # H1: a GB coefficient set with its sources, in GBP. The three ASSUMPTIONS are labelled
    # as such, exactly as the EE seed's are; the rest carry a public source.
    # 14 Oct 2026 (HU7): the set lives in the seed now (factors.json fair_price_by_country.GB), written from
    # this tool's 29 Sep text word for word; the demo takes it from there, so there is one copy.
    fp = json.loads(json.dumps(doc["fair_price_by_country"]["GB"]))
    fp["_README"] = ("The FAIR PRICE model's coefficients (backend/fairprice.py) for this demo tenant, in £, each "
                     "with its source; three are ASSUMPTIONS to replace. Edit on Config → Costing · fuel. The diesel "
                     "price is NOT here: it is the live national index row (fuel.py — DESNZ weekly road fuel prices "
                     "for a GB tenant).")
    fp["_demo_note"] = ("Demo tenant (GB): a GBP coefficient set with sources, written 29 Sep 2026 (H1). "
                        "vehicle_new_price_eur, running_eur_per_km and margin_pct are ASSUMPTIONS to replace "
                        "with the fleet's own figures; the driver rate is derived from public statistics. "
                        "Field names keep their _eur_ suffix — every figure is in the tenant's currency, £.")
    doc["fair_price"] = fp
    # 14 Oct 2026 (merging HU7 into civils materials): the seed's note on fair_price_by_country describes the OTHER set
    # (the no-country one) by its country, and the package of a GB demo must name no Estonian source (test_h1_uk's leak
    # check). The demo keeps the GB set the seed carries, with a note in its own terms.
    doc["_fair_price_by_country_note"] = ("A coefficient set per country, used for a tenant whose country has one: this "
                                          "demo tenant is GB, and its fair_price above is the GB set. Config -> Costing · "
                                          "fuel offers the country's set as one click.")
    # D112: the asphalt plant's feed on its own category. carbon_material null = excluded ON PURPOSE (carbon.py's
    # carbon_material_of): the rock's production carbon is already inside the asphalt's own factor, so counting it
    # again on delivery would count it twice (~4,200 tCO2e here). Its haulage is still counted, like any line's.
    doc["material_categories"][FEED] = {
        "density_t_per_m3": 1.6, "default_unit": "t", "volume_convertible": False, "units": ["t"],
        "vehicles": [TIP], "carbon_material": None,
        "_note": ("16 Oct 2026 (demo, D112): crushed rock delivered INTO the on-site asphalt plant. No material carbon: "
                  "the asphalt it makes is priced with the asphalt factor, which already covers its aggregate. Haulage "
                  "is counted. Density as Small aggregate, stored, not used (planned in tonnes only).")}
    # §1.8: Euro VI on every vehicle the lines use (the CLP section's chart 5 has no "Not typed")
    for v in (TIP, FLAT, MIX8, MIX6):
        doc["vehicles"][v]["euro_class"] = "Euro VI"
    # §1.8: the school-run no-delivery bands (a fictional CLP condition; real CLPs restrict deliveries near schools in
    # term). Scheme-wide: the product takes them off every gate with hours typed.
    doc["planning"]["peak_bands"] = [{"from": "08:00", "to": "09:00"}, {"from": "15:00", "to": "16:00"}]
    res = config.save(doc, by="tools/make_demo_tenant.py", network=network)
    assert res["ok"], res
    config.invalidate()

    # --- teams, design sections, work sections --------------------------------------
    tenant_package.import_rows("ipts", [{"id": i, "label": l, "manager": None, "active": True, "merged_into": None}
                                        for i, l in TEAMS])
    tenant_package.import_rows("design_sections", [
        {"id": "DS1", "label": "Design Section 1 — south", "km_from": 0.0, "km_to": DS_SPLIT_M / 1000.0, "scope_note": "Harborough to Noseley."},
        {"id": "DS2", "label": "Design Section 2 — north", "km_from": DS_SPLIT_M / 1000.0, "km_to": round(LENGTH_M / 1000, 1), "scope_note": "Tilton to Melton."},
    ])
    ws_note = {"WS2": " The Langton cutting's cut to the Noseley embankment is moved on site by dumpers and is not shown.",
               "WS3": " Filled from the Langton cutting along the trace, moved on site by dumpers (not shown)."}
    ws_rows = []
    for sid, name, team, ds, a, b in SECTIONS:
        ws_rows.append({"section_id": sid, "parent_section_id": None, "design_section_id": ds, "ipt_id": team,
                        "name": name, "primary_discipline": None, "in_scope": True, "active": True,
                        "km_from": a / 1000.0, "km_to": (b if b is not None else LENGTH_M) / 1000.0,
                        "scope_note": "Mainline band. Chainage is the scheme's single global datum, 0+000 at the Harborough end."
                                      + ws_note.get(sid, ""),
                        "receives_override": None})
    for sid, name, team, ds, parent in POINT_SECTIONS:
        ws_rows.append({"section_id": sid, "parent_section_id": parent, "design_section_id": ds, "ipt_id": team,
                        "name": name, "primary_discipline": None, "in_scope": True, "active": True,
                        "km_from": None, "km_to": None, "scope_note": "A point asset inside its parent band, not a band of its own.",
                        "receives_override": None})
    tenant_package.import_rows("work_sections", ws_rows)
    team_of_section = {s[0]: s[2] for s in SECTIONS}
    team_of_section.update({s[0]: s[2] for s in POINT_SECTIONS})
    team_name = dict(TEAMS)

    # --- locations (L001–L016, in this order) ---------------------------------------------
    loc = {}

    def add(key, name, role, loc_type, lon, lat, supplies=None, receives=None, vendor=None, detail=None):
        r = network.create_location(name, role, materials=supplies or [], lat=lat, lon=lon, loc_type=loc_type,
                                    supplies=supplies or [], receives=receives or [], vendor=vendor, detail=detail)
        loc[key] = r["id"]
        return r["id"]

    # Quarries in the county's real crushed-rock heartland, invented names, positions near main roads.
    add("Q1", "Kilby Ridge Quarry", "origin", "Quarry", -1.2380, 52.5610, supplies=[BALLAST, SMALL, FEED],
        vendor="Kilby Ridge Aggregates Ltd (fictional)", detail="Granite. Weighbridge in, separate exit onto the main road. Road despatch 06:00–18:00 Monday to Saturday.")
    add("Q2", "Northfield Quarry", "origin", "Quarry", -1.1340, 52.7270, supplies=[BALLAST, SMALL, FEED, ASPHALT],
        vendor="Northfield Stone Co. (fictional)", detail="Granodiorite, with a coating plant (asphalt for the 2030 side roads). Weighbridge queue peaks 07:00–09:00.")
    add("Q3", "Brook Pit", "origin", "Quarry", -0.7520, 52.6940, supplies=[EARTH, SMALL],
        vendor="Brook Pit Sand & Gravel (fictional)", detail="Sand and gravel; imported granular fill.")
    add("RH", "Harborough Rail Freight Terminal", "origin", "Railhead", -0.9180, 52.4785, supplies=[PRECAST, GENERAL, SMALL, STRUCT, REINF],
        detail="Rail-delivered precast units, structural steel and aggregate transhipped to road. Fictional.")

    # Compounds and stockpiles along the corridor, ~400 m off the alignment.
    comp_chain = {"C1": 3000, "C2": 8500, "C3": 19000, "C4": 29500}
    comp_names = {"C1": "Harborough Compound", "C2": "Langton Compound", "C3": "Tilton Compound", "C4": "Melton Compound"}
    for key, m in comp_chain.items():
        p = offset(point_at(ALIGN_PTS, ALIGN_CHAIN, m), east_m=420, north_m=-120)
        add(key, comp_names[key], "destination", "Compound", p[0], p[1],
            receives=[BALLAST, SMALL, EARTH, PRECAST, STRUCT, REINF, GENERAL, READY, ASPHALT],
            detail=f"Site compound at chainage {chain_text(m)}. It stands for all of its section's site accesses: "
                   "the plan delivers to sites, not to work faces.")
    stock_chain = {"S1": 4500, "S2": 17500, "S3": 25000}
    stock_names = {"S1": "Stockpile South", "S2": "Stockpile Tilton", "S3": "Stockpile North"}
    for key, m in stock_chain.items():
        p = offset(point_at(ALIGN_PTS, ALIGN_CHAIN, m), east_m=-380, north_m=150)
        add(key, stock_names[key], "destination", "Stockpile", p[0], p[1],
            receives=[BALLAST, SMALL, EARTH], detail=f"Bulk stockpile at chainage {chain_text(m)}.")
    # §1.8: sizes as the design; every opening 0 on 1 Jan 2026 (the scheme starts with empty piles)
    for key, cap in (("S1", 60000), ("S2", 40000), ("S3", 25000)):
        stockpiles.set_capacity(loc[key], capacity_qty=cap, capacity_unit="t", opening_qty=0)

    # Carbon planner (10 Oct 2026): Langton Compound's surplus cut leaves site to a (fictional) inert landfill — the
    # baseline — and a (fictional) soil-recycling hub sits closer, with a route but no forecast: the alternative the
    # Carbon page's disposal control offers. The destinations' TYPES (Landfill / Soil recycling) are what mark the
    # lines as disposal (carbon.disposal_loc_types).
    c2 = point_at(ALIGN_PTS, ALIGN_CHAIN, comp_chain["C2"])
    tp, hb = offset(c2, east_m=7200, north_m=-3800), offset(c2, east_m=2100, north_m=1600)
    add("TIP", "Wolds Link Inert Landfill (fictional)", "destination", "Landfill", tp[0], tp[1], receives=[EARTH],
        detail="Inert landfill taking surplus cut, unsuitable material and lifted platform stone. Fictional: no such site.")
    add("HUB", "Wolds Link Soil Recycling Hub (fictional)", "destination", "Soil recycling", hb[0], hb[1], receives=[EARTH],
        detail="Soil treatment and reuse; takes surplus cut for reuse on other schemes. Fictional: no such site.")
    # civils materials (14 Oct 2026, D13): open ground on an unclassified road off the A606 south-east of Melton (OSM,
    # 14 Oct 2026: New Road, no premises)
    add("BP", "Wolds Link Batching Plant (fictional)", "origin", "Batching plant", -0.8620, 52.7440, supplies=[READY],
        vendor="Wolds Ready-Mix Ltd (fictional)",
        detail="Ready-mixed concrete for the structures; loading under the plant, a mixer an 8–10 minute turnaround. Fictional: no such plant.")
    # 16 Oct 2026 (D99): a temporary transferable asphalt plant ON SITE, on open ground beside Tilton Compound off Hyde
    # Lodge Road (OSM, 16 Oct 2026: farmland, no premises), as the A14 had at Godmanchester. A location type of its own,
    # "Asphalt plant", so the map can say what it is and no batching-plant count includes it.
    add("AP", "Wolds Link Asphalt Plant (fictional)", "both", "Asphalt plant", -0.8670, 52.6505,
        supplies=[ASPHALT], receives=[FEED], vendor="Wolds Link joint venture (fictional)",
        detail="A temporary transferable asphalt batch plant, 340 t an hour, beside Tilton Compound: base, binder and "
               "surface courses for both surfacing summers (Mar–Sep 2028, Feb–Sep 2029), fed with crushed rock from "
               "Northfield and Kilby Ridge. Its hardstanding comes with Tilton Compound's platform in 2026. Fictional: no such plant.")
    # 16 Oct 2026 (D100): a dedicated ready-mix plant for the south, on open ground off Welham Road north of Market
    # Harborough (OSM, 16 Oct 2026: farmland between Grange Farm and Wild Meadow Farm, no premises).
    add("WR", "Welland Ready-Mix (fictional)", "origin", "Batching plant", -0.8920, 52.5232, supplies=[READY],
        vendor="Welland Ready-Mix Ltd (fictional)",
        detail="Ready-mixed concrete for the southern structures (Langton and Harborough Compounds), commissioned May "
               "2027. Fictional: no such plant.")
    # 22 Oct 2026 (D75, abnormal loads phase 3): where the three fictional abnormal loads start. The precast works beside
    # the A47 (Clickers Way, the Earl Shilton bypass; Hinckley and Bosworth) sends the 32 m bridge beams; the crane depot
    # off Fosse Way at Syston (Charnwood) sends the 250 t-class crane for the beam lift. Neither carries a lorry line.
    # Positions 150 m / 110 m off the road the gate opens onto (Overpass, 22 Oct 2026).
    add("EP", "Earl Shilton Precast Works (fictional)", "origin", "Precast works", -1.322679, 52.567424, supplies=[PRECAST],
        vendor="Wolds Precast Ltd (fictional)",
        detail="Precast bridge beams, parapet and culvert units. Beams over 27.4 m long go as Special Order abnormal loads "
               "(the Melton junction bridges). Fictional: no such works.")
    add("CD", "Soar Valley Crane Hire (fictional)", "origin", "Depot", -1.081939, 52.703875,
        vendor="Soar Valley Crane Hire Ltd (fictional)",
        detail="Mobile cranes for the beam lifts; the 250 t-class crane travels in and out as an abnormal load in its own right. "
               "Fictional: no such depot.")
    assert [loc[k] for k in ("Q1", "BP", "AP", "WR", "EP", "CD")] == ["L001", "L014", "L015", "L016", "L017", "L018"], loc
    # 28 Oct 2026 (simulation v2, task 0e): the viaduct works site, on the line where it crosses the brook valley south-west
    # of Tilton Compound: the laydown at the top of the bank, the pier bases on the terrace 8 m below, a gate in and a
    # gate out on the lane south of it (the gate-out closed March–May 2027 for the deck steel's lift season).
    add("VS", "Tilton Viaduct site (fictional)", "destination", "Site", -0.8822, 52.6447,
        receives=[READY, GENERAL, PRECAST, STRUCT, REINF, BALLAST, SMALL], vendor="Wolds Link joint venture (fictional)",
        detail="The viaduct works: piling and pier bases on the river terrace, the laydown and crane pads at the top of "
               "the bank, a wheel wash on the way out. Check in 3 min; 5 mph on site. Fictional: no such site.")
    assert loc["VS"] == "L019", loc

    # --- routes (R001–R043, in ROUTES order) -------------------------------------------
    team_of = {"C1": "IPT3", "C2": "IPT2", "C3": "IPT1", "C4": "IPT1", "S1": "IPT3", "S2": "IPT1", "S3": "IPT1",
               "AP": "IPT1", "VS": "IPT1"}
    routes = {}
    for o, d, mat in ROUTES:
        # routes.ipt is free text; the demo writes the slot id, which every display turns into the team's name
        # (taxonomy.team_text / teamText). A route takes its site end's team; one to a tip, its compound's.
        r = network.create_route(loc[o], loc[d], material_category=mat, ipt=team_of.get(d) or team_of[o])
        assert "error" not in r, r
        assert r["id"] == ROUTE_ID[(o, d, mat)], (r["id"], o, d, mat)
        routes[r["id"]] = (o, d, mat)
    by_od = {}
    for rid, (o, d, mat) in routes.items():
        by_od.setdefault((o, d), rid)
    # contract rates (§1.8): a base charge per load plus £/km each way on the granite routes (the commonest quote
    # shape), £180 a load from the terminal, and a per-tonne rate on the asphalt plant's output. A target rate for
    # everything else.
    for rid, (o, d, mat) in routes.items():
        if o == "Q1":
            res = network.set_route_planning(rid, ("rate_eur_per_load", "rate_eur_per_km", "km_basis"),
                                             rate_eur_per_load=95.0, rate_eur_per_km=1.85, km_basis="round_trip")
        elif o == "RH":
            res = network.set_route_planning(rid, ("rate_eur_per_load", "km_basis"), rate_eur_per_load=180.0, km_basis="round_trip")
        elif o == "AP":
            res = network.set_route_planning(rid, ("rate_eur_per_t",), rate_eur_per_t=4.80)
        else:
            continue
        assert "error" not in res, res
    # 16 Oct 2026 (§4.3 item 4): the target rate was never saved — set_target was called with eur_per_* keys while
    # costing.TARGET_FIELDS are rate_eur_per_*, and the answer was not checked. Both fixed.
    res = costing.set_target({"rate_eur_per_load": 0.0, "rate_eur_per_t": 6.20, "rate_eur_per_km": 0.0}, by="demo")
    assert res["ok"] and res["target"]["rate_eur_per_t"] == 6.20, res
    res = costing.set_fuel({"country": "GB", "share_pct": 30.0}, by="demo")
    assert res["ok"], res
    # §1.8: the Burrough lane — 8 a day on each of the two village routes, a community agreement. The product compares
    # each route with its own cap (the lane's total is not checked); a planning flag on the public pages, never a block.
    # D113: no Look-ahead cap moment (the field is read as lorries there and as movements on the public pages).
    for key, cap in ((("Q3", "S3"), 8), (("Q2", "S3"), 8)):
        res = network.set_route_planning(by_od[key], ("max_vehicles_per_day",), max_vehicles_per_day=cap)
        assert "error" not in res, res
    # §1.8: the route sheets' words on the routes the stand shows. Every text says it is fictional.
    burrough = ("Burrough Road is the only lorry access to Stockpile North. A community agreement allows 8 lorries a "
                "day on this route, none before 07:30 (fictional).",
                "None through Burrough village. If Burrough Road is closed, hold at the quarry and call the North Team "
                "logistics desk (fictional).")
    hot = ("Hot load: the shortest time from the plant to the paver keeps the asphalt at laying temperature (fictional).",
           "Hot load, no stops: sheeted all the way, no waiting on the road. If the route is blocked, call the plant "
           "before diverting (fictional).")
    mix = ("Ready-mixed concrete: the shortest time from the plant, so the mix arrives well inside its workable life "
           "(fictional).",
           "Only a signed diversion. Tell the pour supervisor before the trip runs over 60 minutes (fictional).")
    a47 = ("While the A47 at the new Tilton junction is closed to HGVs (5 Oct 2026 – 17 Dec 2027), follow the signed "
           "HGV diversion and no other road (fictional).")
    for rid, (o, d, mat) in routes.items():
        words = burrough if d == "S3" else hot if o == "AP" else mix if mat == READY else (None, None)
        reason, dev = words
        if d in ("C3", "S2") or o == "C3":       # the A47 diversion is the one permitted deviation into Tilton
            dev = a47 + (" Hot load: no stops on the diversion either." if o == "AP" else "")
        if reason or dev:
            res = network.set_route_sheet_text(rid, ("route_reason", "permitted_deviations"),
                                               route_reason=reason, permitted_deviations=dev)
            assert "error" not in res, res
    # §1.8: the site rules on the compounds and plants (printed on every route sheet that loads or delivers there)
    rules = {
        "C1": "Site speed 10 mph. In by the A6 entrance, out by Mill Lane: one way on site. No deliveries 08:00–09:00 "
              "or 15:00–16:00 (school run). Wheel wash before leaving. Hi-vis, hard hat, boots, gloves (fictional).",
        "C2": "Site speed 10 mph. Langton haul road at 20 km/h; give way to dumpers. Wheel wash before leaving. Hi-vis, "
              "hard hat, boots, gloves (fictional).",
        "C3": "Site speed 10 mph. Wait in the bellmouth, never on Hyde Lodge Road. Wheel wash before leaving. Hi-vis, "
              "hard hat, boots, gloves (fictional).",
        "C4": "Site speed 10 mph. Call ahead when within 10 minutes; wait in the bellmouth, never on the A606. Wheel "
              "wash before leaving. Hi-vis, hard hat, boots, gloves (fictional).",
        "BP": "One-way loop under the plant. Wash out only in the wash-out bay. Ticket at the gate (fictional).",
        "WR": "One-way loop under the plant. Wash out only in the wash-out bay. Ticket at the gate (fictional).",
        "AP": "Weighbridge in and out. Sheet every asphalt load before it leaves. No stopping on the site roads. "
              "Hi-vis, hard hat, boots, gloves (fictional).",
    }
    for key, text in rules.items():
        res = network.set_site_rules(loc[key], text)
        assert "error" not in res, res
    # §1.8: the sites' CLP caps, in lorry visits a day (network.CLP_CAP_WORDS)
    for key, cap in (("C1", 50), ("C4", 60), ("AP", 140)):
        res = network.set_clp_cap(loc[key], cap)
        assert "error" not in res, res

    # --- two temporary haul roads (zones Z001, Z002) ---------------------------------------
    p1 = point_at(ALIGN_PTS, ALIGN_CHAIN, 7800)
    p2 = point_at(ALIGN_PTS, ALIGN_CHAIN, 9200)
    # v2: mode 'splice' — HERE does not know a road built across a field last month, and
    # 'via' would route between its ends along whatever public road HERE prefers and never
    # say so (haul.py). Spliced, the drawn line IS the geometry, at 20 km/h.
    zr = zones.create_zone("Langton haul road", {"type": "LineString", "coordinates": [offset(p1, 300, -60), offset(p2, 380, 40)]},
                           kind=zones.HAUL_KIND, affects_routing=True, note="Temporary haul road behind Langton Compound (fictional).",
                           speed_kph=20, haul_mode="splice", starts_on="2026-11-01", ends_on="2029-09-30")
    assert "error" not in zr, zr
    # a second haul road: the last 1.2 km into Stockpile North, off the public road
    p3 = point_at(ALIGN_PTS, ALIGN_CHAIN, 24200)
    zr2 = zones.create_zone("Stockpile North haul road", {"type": "LineString", "coordinates": [offset(p3, -900, -300), offset(p3, -420, 120)]},
                            kind=zones.HAUL_KIND, affects_routing=True, note="Temporary haul road from the lane into Stockpile North (fictional).",
                            speed_kph=25, haul_mode="splice", starts_on="2026-04-01", ends_on="2027-12-31")
    assert "error" not in zr2, zr2
    # ATTACHED to the routes that use them: every route into Langton Compound, and the two village routes
    for rid, (o, d, mat) in routes.items():
        if d == "C2":
            res = haul.attach(rid, zr["id"])
            assert "error" not in res, res
    for key in (("Q3", "S3"), ("Q2", "S3")):
        res = haul.attach(by_od[key], zr2["id"])
        assert "error" not in res, res

    # --- three geofences (Z003–Z005) ----------------------------------------------------
    def box(lon, lat, w_m, h_m):
        a = offset([lon, lat], -w_m / 2, -h_m / 2); b = offset([lon, lat], w_m / 2, h_m / 2)
        return {"type": "Polygon", "coordinates": [[[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]]]}
    # (a) the A47 at the new Tilton junction, closed to HGVs while the junction is built — AFFECTS ROUTING: the routes
    #     into Tilton Compound and Stockpile Tilton bake round it. A zone only steers HERE while it is in force on the
    #     day of the bake (zones.applies_on), and the box has to sit on the line HERE drew: the 5 Oct 2026 bake ran the
    #     A47 along 52.620–52.622 N here, turning north at Tilton (-0.922); the box straddles it 1.8 km west of that
    #     turn. Same box and start date as before (D106), so the 5 Oct check stands; dated to the junction's build.
    z_a = zones.create_zone("A47 at the new Tilton junction: HGV diversion while the junction is built",
                            box(-0.9490, 52.6208, 360, 240), kind="closure", affects_routing=True,
                            starts_on="2026-10-05", ends_on="2027-12-17",
                            note="A47 closed to through HGVs at the new junction while it is built; signed HGV diversion (fictional).")
    assert "error" not in z_a, z_a
    # (b) a village 7.5 t limit on the lane to Stockpile North — ADVISORY (the router is not told): the routes keep
    #     using it and the flag says so; paired with the daily caps above. For the whole programme.
    z_b = zones.create_zone("Burrough village 7.5 t limit", box(-0.8879, 52.6993, 420, 360), kind="weight_limit",
                            affects_routing=False, starts_on="2026-01-01", ends_on="2030-12-31",
                            note="Community liaison agreement: 7.5 t except for access, 8 vehicles a day on each route, no deliveries before 07:30 (fictional).")
    assert "error" not in z_b, z_b
    # (c) an advisory works area at the Melton end — drawn grey, changes nothing (the junction, Mar 2026 – Sep 2027)
    z_c = zones.create_zone("Melton junction works area", box(-0.8695, 52.7482, 380, 300), kind="works",
                            affects_routing=False, starts_on="2026-03-01", ends_on="2027-09-30",
                            note="Earthworks compound and crane standing for the junction structures (fictional).")
    assert "error" not in z_c, z_c

    # --- gates (G001–G019): a site is entered and left where its roads are, not at its centre ------------------
    # Quarries: weighbridge in, a separate exit onto the main road. Compounds: one gate on the access road. Harborough
    # Compound (the town end): in from the A6, out by Mill Lane. §1.8: open hours, check-in minutes (weighbridges 4,
    # Harborough Compound 5, every other gate with a check-in 3; the stockpile gates gain one), ONE default gate per
    # site (gates.py's documented rule): the gate that serves the site's own role.
    COMPOUND_HOURS = ("07:30", "18:00", "1111100")       # DCO core hours, Monday to Friday (§1.3)
    PLANT_HOURS = ("06:00", "18:00", "1111110")          # quarries, the Melton plant, the asphalt plant: Mon–Sat
    hours = {"Q1": PLANT_HOURS, "Q2": PLANT_HOURS, "Q3": PLANT_HOURS, "BP": PLANT_HOURS, "AP": PLANT_HOURS,
             "RH": ("07:00", "19:00", "1111100"), "WR": ("06:30", "17:00", "1111100")}

    def gate(key, name, east, north, direction, default=False, safety=None, internal=None, note=None):
        row = db.query("SELECT lat, lon FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), loc[key]))[0]
        pt = offset([row["lon"], row["lat"]], east, north)
        of, ot, od = hours.get(key, COMPOUND_HOURS)
        g = gates.create_gate(loc[key], name, pt[1], pt[0], direction=direction, safety_minutes=safety,
                              internal_travel_minutes=internal, is_default=default, note=note,
                              open_from=of, open_to=ot, open_days=od)
        assert "error" not in g, g
        return g["id"]
    G = {}
    G["Q1_in"]  = gate("Q1", "Weighbridge (in)", -260, 90, "access", safety=4, internal=6, note="Check in at the weighbridge; 10 mph site limit.")
    G["Q1_out"] = gate("Q1", "Main road exit", 310, -140, "egress", default=True, internal=4)
    G["Q2_in"]  = gate("Q2", "Weighbridge (in)", -240, -120, "access", safety=4, internal=5, note="Queue peaks 07:00–09:00.")
    # §4.3 item 7: renamed — the exit is on the A6 (it said "A46 exit")
    G["Q2_out"] = gate("Q2", "A6 exit", 280, 160, "egress", default=True, internal=3)
    G["Q3"]     = gate("Q3", "Pit entrance", 180, -60, "both", default=True, safety=3, internal=4)
    G["RH"]     = gate("RH", "Terminal gate", -150, 200, "both", default=True, safety=3, internal=5, note="Booking slot required at the terminal (fictional).")
    # §4.3 item 7: renamed — the entrance is on the A6 (it said "Station Road entrance")
    G["C1_in"]  = gate("C1", "A6 entrance (in)", -210, 150, "access", default=True, safety=5, internal=3, note="Town compound: in from the A6, out by Mill Lane — one-way on site.")
    G["C1_out"] = gate("C1", "Mill Lane exit", 230, -170, "egress", internal=3)
    G["C2"]     = gate("C2", "Compound gate", 190, 60, "both", default=True, safety=3)
    G["C3"]     = gate("C3", "Compound gate", -200, 80, "both", default=True, safety=3)
    G["C4"]     = gate("C4", "Compound gate", 210, -90, "both", default=True, safety=3)
    G["S1"]     = gate("S1", "Stockpile gate", 160, 100, "both", default=True, safety=3)
    G["S2"]     = gate("S2", "Stockpile gate", -170, -90, "both", default=True, safety=3)
    G["S3"]     = gate("S3", "Stockpile gate", 150, -120, "both", default=True, safety=3)
    G["TIP"]    = gate("TIP", "Weighbridge", -150, 80, "both", default=True, safety=4, internal=3,
                       note="Inert waste acceptance; a weighbridge ticket per load (fictional).")
    G["HUB"]    = gate("HUB", "Site gate", 120, -60, "both", default=True, safety=3, internal=2)
    G["BP"]     = gate("BP", "Plant gate", 140, -90, "both", default=True, safety=3, internal=3,
                       note="One-way loop under the batching plant; wash-out bay before the exit (fictional).")
    G["AP"]     = gate("AP", "Weighbridge", -180, 0, "both", default=True, safety=4, internal=4,
                       note="Weighbridge in and out; sheeting bay before the exit (fictional).")
    G["WR"]     = gate("WR", "Plant gate", 0, 130, "both", default=True, safety=3, internal=3,
                       note="One-way loop under the batching plant; wash-out bay before the exit (fictional).")
    assert G["WR"] == "G019", G
    # 28 Oct 2026 (simulation v2): the viaduct site's gate in (check-in 3 min) and gate out, both on the lane south of it;
    # the gate out is CLOSED 1 Mar – 31 May 2027 (the lane under the crane outriggers): in and out by the gate in meanwhile
    G["VS_in"]  = gate("VS", "South lane gate (in)", 150, -200, "access", default=True, safety=3,
                       note="Check in here; 5 mph on site; leave by the gate out past the wheel wash (fictional).")
    G["VS_out"] = gate("VS", "South lane gate (out)", -120, -230, "egress")
    assert G["VS_out"] == "G021", G
    res = gates.update_gate(G["VS_out"], closed_from="2027-03-01", closed_to="2027-05-31")
    assert "error" not in res, res
    # 29 Oct 2026 (task 3c, the user's Q10): the VEHICLE HOLDING AREA — a field beside the lane north from the A47 at
    # Billesdon, 300 m up it, where every tipper and flatbed route into the viaduct site and Tilton Compound already runs
    # (its entrance is a vertex of the stored lane line, read on live 29 Oct 2026, so nothing is drawn again); 15 spaces,
    # 2 called forward at a time, the concrete mixers straight to the gate (the default); the viaduct site and Tilton
    # Compound call off through it; the asphalt plant's route into the compound (600 m east of it) is ticked "does not
    # call off" (Q4). Fictional, like every site here.
    ha_gate = (-0.92094, 52.6226)
    ha_pt = offset(list(ha_gate), east_m=115, north_m=122)
    add("HA", "Billesdon Lane holding area (fictional)", "holding", "Holding area", ha_pt[0], ha_pt[1],
        detail="Vehicle holding area: lorries for Tilton Viaduct site and Tilton Compound wait here to be called forward. Fictional: no such site.")
    assert loc["HA"] == "L020", loc
    hours["HA"] = ("07:00", "20:30", "1111100")
    G["HA"] = gate("HA", "Lane entrance", -80, -100, "both", default=True)      # set back to 35 m from the lane below
    import holding as _holding
    res = _holding.set_holding(loc["HA"], {"holding_spaces", "holding_call"}, spaces=15, call=2)
    assert not res.get("error"), res
    for key in ("VS", "C3"):
        res = _holding.set_calls_through(loc[key], loc["HA"])
        assert not res.get("error"), res
    res = network.set_route_planning(by_od[("AP", "C3")], ("skip_holding",), skip_holding=1)
    assert not res.get("error"), res
    # the routes name their gates explicitly (the resolver would pick the defaults anyway;
    # an explicit choice is what a planner does on the route form)
    origin_gate = {"Q1": G["Q1_out"], "Q2": G["Q2_out"], "Q3": G["Q3"], "RH": G["RH"], "C1": G["C1_out"], "C2": G["C2"],
                   "C3": G["C3"], "BP": G["BP"], "AP": G["AP"], "WR": G["WR"], "VS": G["VS_out"]}
    dest_gate = {"C1": G["C1_in"], "C2": G["C2"], "C3": G["C3"], "C4": G["C4"], "S1": G["S1"], "S2": G["S2"], "S3": G["S3"],
                 "TIP": G["TIP"], "HUB": G["HUB"], "AP": G["AP"], "VS": G["VS_in"]}
    for rid, (o, d, mat) in routes.items():
        res = gates.set_route_gates(rid, origin_gate_id=origin_gate[o], dest_gate_id=dest_gate[d],
                                    origin_given=True, dest_given=True)
        assert "error" not in res, res

    # --- the forecasts: the programme's 905 approved line-months, plus Pending and Rejected -------------------
    aw_m, aw_w = weeks.week_of_date(as_of)                 # the as-of week (the Thursday rule)
    pw_m, pw_w = weeks.prev_week(aw_m, aw_w)               # the account week
    assert 1 <= aw_m <= N_MONTHS, (AS_OF, aw_m)
    plines = programme_lines()
    rows = sorted(((ROUTE_ID[(o, d, mat)], m, disc, sec, veh, unit, mat, q, descs)
                   for (o, d, mat, disc, sec, veh, unit, m), (q, descs) in plines.items()),
                  key=lambda r: (r[1], r[0], r[2], r[3]))
    hrng = random.Random(f"wolds-link-history:{as_of.isoformat()}")
    # §2 PARENT_CHANGED: one Central Team line in the as-of week was raised after its week was set. Typed below as
    # it happened: written lower, its as-of week set, then raised to the programme's figure.
    central = [r for r in rows if r[1] == aw_m and team_of_section[r[3]] == "IPT2"]
    raised = max(central, key=lambda r: (r[7], r[0])) if central else None
    raise_by = (max(100.0, round(raised[7] * 0.1 / 100.0) * 100) if raised else 0.0)

    def insert(n, rid, m, disc, sec, q, unit, mat, desc, veh, status, reason=None):
        team = team_of_section[sec]
        db.execute(
            "INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, "
            "quantity, unit, material_type, material_description, vehicle_type, submitted_by, "
            "status, reject_reason, ipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), f"F{n:04d}", rid, m, disc, sec, float(q), unit, mat, desc, veh,
             f"{team} planner", status, reason, team))
    n = 0
    for rid, m, disc, sec, veh, unit, mat, q, descs in rows:
        n += 1
        low = raised is not None and (rid, m, disc, sec) == raised[:4]
        insert(n, rid, m, disc, sec, q - raise_by if low else q, unit, mat, " + ".join(descs), veh, "Approved")
    insert(n + 1, PENDING[0], pending_month(aw_m), PENDING[1], PENDING[2], PENDING[3], "t", EARTH, PENDING[4], TIP, "Pending")
    if aw_m < N_MONTHS:
        insert(n + 2, REJECTED[0], aw_m + 1, REJECTED[1], REJECTED[2], REJECTED[3], "t", SMALL, REJECTED[4], TIP,
               "Rejected", REJECTED[5])

    # --- 29 Oct 2026 (3b-2): the viaduct's reinforcement line is TYPED AS M³ OF CONCRETE, as an engineer does before the bar
    # bending schedules exist: REBAR_KG_PER_M3 kg of bar a m³ (the demo's own figure, said so in the structure's name —
    # not a published one). Its tonnes are unchanged (100 t = 800 m³), so no load, lorry or carbon figure moves; the
    # Forecasts row then reads "800 m³ of concrete × 125 kg/m³ (Viaduct and overbridge, demo figure)".
    rebar_rid = ROUTE_ID[("RH", "VS", REINF)]
    rebar_rows = db.query("SELECT id, quantity FROM forecasts WHERE tenant_id = ? AND route_id = ? AND material_type = ?",
                          (db.current_tenant(), rebar_rid, REINF))
    assert rebar_rows, rebar_rid
    for r in rebar_rows:
        m3 = float(r["quantity"]) * 1000.0 / REBAR_KG_PER_M3
        assert m3 == round(m3), (r["id"], r["quantity"])          # every month a whole number of m³
        db.execute("UPDATE forecasts SET concrete_m3 = ?, rebar_kg_per_m3 = ?, structure_type = ? "
                   "WHERE tenant_id = ? AND id = ?",
                   (m3, float(REBAR_KG_PER_M3), REBAR_STRUCTURE, db.current_tenant(), r["id"]))

    # --- the concrete pours (29 Oct 2026, task 3a): before the weeks materialise, so the as-of week's split carries them
    pfactors = conversions.load_factors()
    for o, d, _mat, sec, disc, when, start, m3, rate, booked, wash, place, how in DEMO_POURS:
        pd = demo_pour_date(when, as_of)
        res = pours.create_pour({"route_id": ROUTE_ID[(o, d, READY)], "discipline": disc, "section_id": sec,
                                 "pour_date": pd.isoformat(), "start": start, "m3": m3, "rate_m3h": rate,
                                 "mixers_booked": booked, "washout_min": wash, "place": place, "method": how,
                                 "status": "planned"}, pfactors, by=f"{team_name[team_of_section[sec]]} planner")
        if res.get("error"):
            # the line does not run that month (an as-of outside its months): no pour, said on the console
            print(f"  pour left out ({place}, {pd}): {res['error']}")

    # --- the client's reviewers (31 Oct 2026, task 4a PR 3c, John's Q11): one fictional group, NO logins (a shared
    # reviewer login would be a code by another name). John adds his own second address as a reviewer to show it.
    db.execute("INSERT INTO clp_review_groups (tenant_id, id, name, created_by, created_at, updated_at, stopped_by, "
               "stopped_at) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
               (db.current_tenant(), DEMO_REVIEW_GROUP[0], DEMO_REVIEW_GROUP[1], "Wayscope demo",
                DEMO_REVIEW_GROUP[2], DEMO_REVIEW_GROUP[2]))

    # --- the history up to the as-of date (§1.9) -------------------------------------------------------------
    # Only weeks that carry history ship: every approved month up to the as-of month is materialised; later weeks
    # materialise on read, as on any deployment.
    weeks.materialise_window(1, aw_m)
    if raised is not None:
        r_rid, r_m, r_disc, r_sec = raised[:4]
        w = weeks.get_week(r_rid, r_m, r_disc, r_sec, aw_w)
        res = weeks.set_week(r_rid, r_m, r_disc, r_sec, aw_w, planned_qty=float(w["planned_qty"]), by=f"{team_name['IPT2']} planner")
        assert "error" not in res, res
        db.execute("UPDATE forecasts SET quantity = ? WHERE tenant_id = ? AND route_id = ? AND month_index = ? "
                   "AND discipline = ? AND section_id = ?", (float(raised[7]), db.current_tenant(), r_rid, r_m, r_disc, r_sec))
        weeks.materialise_line(r_rid, r_disc, r_sec, month_index=r_m)
    hist = [w for w in weeks.list_weeks(1, aw_m)
            if w.get("parent_status") == "Approved" and (int(w["month_index"]), int(w["week_index"])) < (aw_m, aw_w)]
    parents = {(f["route_id"], f["month_index"], f["discipline"], f["section_id"]): f for f in db.query(
        "SELECT route_id, month_index, discipline, section_id, material_type, material_description, vehicle_type, "
        "unit, ipt FROM forecasts WHERE tenant_id = ?", (db.current_tenant(),))}
    rmeta = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (db.current_tenant(),))}
    lmeta = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    factors = conversions.load_factors()

    def tonnes(qty, unit, mat, veh):
        return float(qty) if unit == "t" else conversions.convert(float(qty), unit, "t", mat, veh, factors)

    def km_one_way(rid):
        # ASSUMPTION for a typed actual cost only: 1.3 × the straight line between the two sites (no geometry here)
        a, b = lmeta[rmeta[rid]["origin_id"]], lmeta[rmeta[rid]["dest_id"]]
        return 1.3 * zones.haversine_km([a["lon"], a["lat"]], [b["lon"], b["lat"]])

    def actual_cost(rid, t, veh):
        r = rmeta[rid]
        if r.get("rate_eur_per_load") is None and r.get("rate_eur_per_t") is None:
            return None
        loads = math.ceil(t / float(factors["vehicles"][veh]["payload_t"]) - 1e-9)
        km = km_one_way(rid) * (2 if (r.get("km_basis") or "round_trip") == "round_trip" else 1)
        return round(loads * float(r.get("rate_eur_per_load") or 0) + t * float(r.get("rate_eur_per_t") or 0)
                     + loads * km * float(r.get("rate_eur_per_km") or 0))

    # the account week (the week before the as-of week): 2–3 chosen lines short, every other line held, so exactly
    # those show SHORTAGE in the as-of week (clashes.HOLD_BAND: under 98 % of plan and not carried)
    acct = [w for w in hist if (int(w["month_index"]), int(w["week_index"])) == (pw_m, pw_w)]
    in_aw = {(r[0], r[2], r[3]) for r in rows if r[1] == aw_m}
    short_pool = [w for w in acct if (w["route_id"], w["discipline"], w["section_id"]) in in_aw
                  and w["discipline"] in ("earthworks", "substructure") and float(w["planned_qty"] or 0) >= 200]
    prefer = [("R011", "substructure", "WS6"), ("R018", "substructure", "WS5"), ("R024", "earthworks", "WS6")]
    short_pool.sort(key=lambda w: (0 if (w["route_id"], w["discipline"], w["section_id"]) in prefer else 1,
                                   prefer.index((w["route_id"], w["discipline"], w["section_id"]))
                                   if (w["route_id"], w["discipline"], w["section_id"]) in prefer else 0,
                                   -float(w["planned_qty"] or 0), w["route_id"]))
    shortages = {(w["route_id"], w["discipline"], w["section_id"]) for w in short_pool[:3]}
    xmas = {datetime.date(y, 12, 25) for y in range(START_YEAR, START_YEAR + 6)} | \
           {datetime.date(y, 1, 1) for y in range(START_YEAR, START_YEAR + 6)}
    inbound = {}        # (location_id, month, week) -> tonnes delivered (typed actuals)
    for w in hist:
        rid, m, wk, disc, sec = w["route_id"], int(w["month_index"]), int(w["week_index"]), w["discipline"], w["section_id"]
        p = parents[(rid, m, disc, sec)]
        planned = float(w["planned_qty"] or 0)
        mon, sun = weeks.week_span(m, wk)
        cal_m = (m - 1) % 12 + 1
        note = None
        key = (rid, disc, sec)
        if (m, wk) == (pw_m, pw_w):
            f = hrng.uniform(0.80, 0.95) if key in shortages else hrng.uniform(0.98, 1.05)
            if key in shortages and disc in ("earthworks", "substructure"):
                note = RAIN_NOTE
        elif any(mon <= x <= sun for x in xmas):
            f, note = hrng.uniform(0.35, 0.60), "Christmas stop"
        elif cal_m in (11, 12, 1, 2) and (disc == "earthworks" or "capping" in (p["material_description"] or "")) \
                and hrng.random() < 0.35:
            f = hrng.uniform(0.70, 0.90)
            note = RAIN_NOTE if hrng.random() < 0.4 else None
        else:
            f = hrng.uniform(0.90, 1.05)
        step = 1.0 if (w["unit"] == "m3" or planned < 200) else 10.0
        actual = round(planned * f / step) * step
        if (m, wk) == (pw_m, pw_w) and key not in shortages:
            actual = max(actual, math.ceil(planned * clashes.HOLD_BAND - 1e-9))
        t = tonnes(actual, w["unit"], p["material_type"], p["vehicle_type"])
        cost = actual_cost(rid, t, p["vehicle_type"])
        res = weeks.set_actual(rid, m, disc, sec, wk, actual_qty=actual, actual_note=note, by="site clerk",
                               actual_cost_eur=cost, cost_given=cost is not None)
        assert "error" not in res, res
        res = weeks.confirm_week(rid, m, disc, sec, wk, by=f"{team_name[p['ipt']]} planner")
        assert "error" not in res, res
        dest = rmeta[rid]["dest_id"]
        inbound[(dest, m, wk)] = inbound.get((dest, m, wk), 0.0) + t
    # consumption, typed every week before the as-of week (§1.9): the compounds use what arrives; the stockpiles give
    # out what their sections lay (lay_draw, actual_draw). Nothing is typed for the as-of week itself, so a pile near
    # capacity forecasts over in the commit week (STOCKPILE_OVER).
    held = {loc[k]: 0.0 for k in ("S1", "S2", "S3")}
    for m in range(1, aw_m + 1):
        for wk in range(1, weeks.weeks_in_month(m) + 1):
            if (m, wk) >= (aw_m, aw_w):
                break
            cal_m = (m - 1) % 12 + 1
            for key in ("C1", "C2", "C3", "C4"):
                t = inbound.get((loc[key], m, wk), 0.0)
                if t > 0:
                    res = stockpiles.consume(loc[key], m, wk, consumed_qty=round(t, 1), unit="t",
                                             note="Used on the works as delivered", by="site clerk")
                    assert "error" not in res, res
            for key in ("S1", "S2", "S3"):
                lid = loc[key]
                t = inbound.get((lid, m, wk), 0.0)
                if t <= 0 and held[lid] <= 0:
                    continue
                plan_draw = lay_draw(key, cal_m, held[lid], t)
                draw, lay_note = actual_draw(key, m, wk, plan_draw)
                held[lid] = held[lid] + t - draw
                res = stockpiles.consume(lid, m, wk, consumed_qty=round(draw, 1), unit="t",
                                         note=(lay_note or "Stock held: formation not laid in winter"), by="site clerk")
                assert "error" not in res, res
                for ck, cm, cw, delta, cnote in COUNTS:
                    if (ck, cm, cw) == (key, m, wk):
                        # a survey: the pile measured against the book; the site then works from the measured stock
                        held[lid] = max(0.0, round(held[lid] + delta))
                        res = stockpiles.set_count(lid, m, wk, measured_qty=held[lid], note=cnote, by="site engineer")
                        assert "error" not in res, res
    # 27 Oct 2026 (stockpile forecast, plan §6; reworked 28 Oct, task 0b): each stockpile's PLANNED use, month by month —
    # the laying programme (LAY_RATE, WINTER_PACE, PLAN_SURGE) run over the PLANNED deliveries (every approved line into
    # the pile, its month spread evenly over the month's weeks). The history typed above drifts from it (actual_draw) and
    # carries the stock counts (COUNTS), so the plan and the actuals read apart on the Stockpiles page.
    stock_plan_rows(loc)
    # the as-of week: days for every line, day actuals for the days before the as-of date (Monday to Wednesday for a
    # Thursday), one South Team line's day split typed 10 t short of its week (DAYS_NE_WEEK), and the North Team's
    # week confirmed — so the Confirm button is still live for the Central and South Teams.
    days.materialise_commit_week(today=as_of)
    aw_lines = [w for w in weeks.list_weeks(aw_m, aw_m)
                if int(w["week_index"]) == aw_w and w.get("parent_status") == "Approved"]
    south = [w for w in aw_lines if parents[(w["route_id"], aw_m, w["discipline"], w["section_id"])]["ipt"] == "IPT3"
             and float(w["planned_qty"] or 0) >= 100]
    if south:
        s = max(south, key=lambda w: (float(w["planned_qty"] or 0), w["route_id"]))
        mon = weeks.week_span(aw_m, aw_w)[0]
        fri = mon + datetime.timedelta(days=4)
        share = float(s["planned_qty"]) / 5.0
        res = days.set_day(s["route_id"], aw_m, s["discipline"], s["section_id"], fri.isoformat(), share - 10.0,
                           by=f"{team_name['IPT3']} planner", today=as_of)
        assert "error" not in res, res
    mon = weeks.week_span(aw_m, aw_w)[0]
    for w in aw_lines:
        p = parents[(w["route_id"], aw_m, w["discipline"], w["section_id"])]
        for i in range(5):
            d = mon + datetime.timedelta(days=i)
            if d >= as_of:
                break
            share = float(w["planned_qty"] or 0) / 5.0
            step = 1.0 if (w["unit"] == "m3" or share < 200) else 10.0
            res = days.set_day_actual(w["route_id"], aw_m, w["discipline"], w["section_id"], d.isoformat(),
                                      actual_qty=round(share * hrng.uniform(0.90, 1.05) / step) * step,
                                      by="site clerk", today=as_of)
            assert "error" not in res, res
        if p["ipt"] == "IPT1":
            res = days.confirm_week(w["route_id"], aw_m, w["discipline"], w["section_id"], aw_w,
                                    by=f"{team_name['IPT1']} planner", today=as_of)
            assert "error" not in res, res

    # --- the overlay ------------------------------------------------------------------
    # Chainage markers at EXACT 100 m chainages, positioned along the line — the shape a
    # survey's chainage file has. (Markers at the alignment's own vertices would sit at
    # 100.4, 200.8 … and never land on a round tick, so the map's 10 km / 5 km / 1 km
    # ladder would have nothing to draw.)
    chainage_feats = []
    for m in range(0, int(LENGTH_M) + 1, 100):
        p = point_at(ALIGN_PTS, ALIGN_CHAIN, m)
        chainage_feats.append({"type": "Feature",
                               "geometry": {"type": "Point", "coordinates": [round(p[0], 6), round(p[1], 6)]},
                               "properties": {"chain": float(m), "chaintxt": chain_text(m),
                                              "chain_type": "Global", "dps_no": "WL-DPS1"}})
    bands, boundaries = [], []
    for sid, name, team, ds, a, b in SECTIONS:
        end = b if b is not None else int(LENGTH_M) + 1
        assert end > a, (sid, a, end)            # a band that runs backwards paints nothing
        bands.append({"ipt": dict(TEAMS)[team], "ws": [sid], "label": name, "ws_primary": sid,
                      "chain_from": a, "chain_to": end, "colour": BAND_COLOURS[team]})
    for i in range(1, len(SECTIONS)):
        b = {"chain_m": SECTIONS[i][4], "from_ws": SECTIONS[i - 1][0], "to_ws": SECTIONS[i][0],
             "from_ipt": dict(TEAMS)[SECTIONS[i - 1][2]], "to_ipt": dict(TEAMS)[SECTIONS[i][2]]}
        if SECTIONS[i][0] == PROVISIONAL_WS:
            # one boundary flagged unconfirmed, so the demo shows what a provisional edge looks like
            b["provisional"] = True
            b["note"] = "Design-section interface — position under review (demo)."
        boundaries.append(b)
    section_names = {sid: {"name": name, "ipt": dict(TEAMS)[team]} for sid, name, team, ds, a, b in SECTIONS}
    for sid, name, team, ds, parent in POINT_SECTIONS:
        section_names[sid] = {"name": name, "ipt": dict(TEAMS)[team]}
    overlay = {
        "version": "wolds-link-demo-2",
        "alignment": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": ALIGN_PTS},
             # align_type "Main Track" is the map style's key for the solid mainline — a style
             # value, not a word anyone reads; the name is what the popup shows.
             "properties": {"align_type": "Main Track", "name": "Wolds Link dual carriageway — mainline (fictional)"}}]},
        "chainage": {"type": "FeatureCollection", "features": chainage_feats},
        "bands": bands,
        "underlay": None,
        "section_names": section_names,
        "boundaries": boundaries,
        "provisional_bounds": [f"{PROVISIONAL_FROM}/{PROVISIONAL_WS} @ {PROVISIONAL_AT}"],
        "rail": None,
        "view": {"center": [-0.905, 52.62], "zoom": 9.6},
        "_note": "Fictional road scheme drawn across countryside. Not a real road or a proposal for one.",
    }
    res = tenant_package.set_overlay(overlay, by="tools/make_demo_tenant.py")
    assert res["ok"], res

    # 22 Oct 2026 (D75, abnormal loads phase 3): the two sites the abnormal loads start from, a gate each — south of the
    # works towards the A47, west of the depot towards Fosse Way — so the access-road step below draws theirs too.
    G["EP"] = gate("EP", "Works gate", 0, -120, "both", default=True, safety=3, internal=4,
                   note="Beams are loaded on the yard's gantry; the escort forms up on the works road (fictional).")
    G["CD"] = gate("CD", "Depot gate", -90, 0, "both", default=True, safety=3, internal=3)

    # --- 16 Oct 2026: EVERY GATE BY THE PUBLIC ROAD, WITH ITS ACCESS ROAD DRAWN --------------------------------
    # The user, 16 Oct 2026: "gates are usually right by the public road with a suitable bellmouth, maybe enough to fit
    # one or two vehicles before the gate. Please ensure there is a haul road drawn to every gate." Each gate is moved to
    # BELLMOUTH_M in from the nearest lorry road, and that stretch is drawn as the gate's access road (a haul road,
    # spliced, at 10 km/h): every route arriving by the gate ends along it and every route leaving starts along it
    # (haul.leg_steps). Done after every gate exists and after the five zones above, so those keep Z001–Z005 and the
    # access roads take Z006–Z028 in gate order (Z025, Z026 the two abnormal-load sites', 22 Oct 2026; Z027, Z028 the
    # viaduct site's, 28 Oct 2026), then the viaduct site's four internal roads (Z029–Z032); the advisory zones below
    # come after them (Z033 on).
    # The road points: the nearest OpenStreetMap way of class trunk / primary / secondary / tertiary / unclassified
    # (residential streets left out on purpose: no quarry gate on a housing close) to each gate's v2 position, one
    # Overpass query, 16 Oct 2026 (the two new plants' gates: one more query, 16 Oct 2026 night; the precast works and
    # the crane depot: one more, 22 Oct 2026). OSM data ©
    # OpenStreetMap contributors (ODbL); a point on a road, nothing else kept.
    BELLMOUTH_M = 35.0          # two 16.5 m artics off the carriageway before the gate
    ROAD_AT = {   # (site, gate): ([lon, lat] on the road, the road's name in OSM)
        ("Kilby Ridge Quarry", "Weighbridge (in)"): ([-1.237463, 52.559127], "Marion's Way"),
        ("Kilby Ridge Quarry", "Main road exit"): ([-1.235117, 52.55825], "Marion's Way"),
        ("Northfield Quarry", "Weighbridge (in)"): ([-1.136478, 52.72641], "Leicester Road"),
        ("Northfield Quarry", "A6 exit"): ([-1.130968, 52.72813], "A6"),
        ("Brook Pit", "Pit entrance"): ([-0.749217, 52.693492], "Ashwell Road"),
        ("Harborough Rail Freight Terminal", "Terminal gate"): ([-0.920385, 52.480157], "Doddridge Road"),
        ("Harborough Compound", "A6 entrance (in)"): ([-0.904551, 52.5023], "A6"),
        ("Harborough Compound", "Mill Lane exit"): ([-0.892606, 52.502515], "Welham Lane"),
        ("Langton Compound", "Compound gate"): ([-0.894045, 52.554637], "Harborough Road"),
        ("Tilton Compound", "Compound gate"): ([-0.873635, 52.646823], "Hyde Lodge Road"),
        ("Melton Compound", "Compound gate"): ([-0.862296, 52.742055], "A606"),
        ("Stockpile South", "Stockpile gate"): ([-0.908941, 52.52207], "Bowden Road"),
        ("Stockpile Tilton", "Stockpile gate"): ([-0.891951, 52.636202], "Loddington Road"),
        ("Stockpile North", "Stockpile gate"): ([-0.877212, 52.705444], "Burrough Road"),
        ("Wolds Link Inert Landfill (fictional)", "Weighbridge"): ([-0.800099, 52.519765], "Medbourne Road"),
        ("Wolds Link Soil Recycling Hub (fictional)", "Site gate"): ([-0.865023, 52.566747], "Goadby Road"),
        ("Wolds Link Batching Plant (fictional)", "Plant gate"): ([-0.861343, 52.744406], "New Road"),
        ("Wolds Link Asphalt Plant (fictional)", "Weighbridge"): ([-0.870439, 52.650658], "Hyde Lodge Road"),
        ("Welland Ready-Mix (fictional)", "Plant gate"): ([-0.892004, 52.525043], "Welham Road"),
        ("Earl Shilton Precast Works (fictional)", "Works gate"): ([-1.322679, 52.566067], "Clickers Way (A47)"),
        ("Soar Valley Crane Hire (fictional)", "Depot gate"): ([-1.08357, 52.703875], "Fosse Way"),
        # 28 Oct 2026 (simulation v2): two points on the lane south of Tilton Compound, read from the demo's own routed
        # line into the compound on a local copy (R007's last kilometre; Overpass was at capacity that evening)
        ("Tilton Viaduct site (fictional)", "South lane gate (in)"): ([-0.879952, 52.64273], "the lane south of Tilton Compound"),
        ("Tilton Viaduct site (fictional)", "South lane gate (out)"): ([-0.883957, 52.642399], "the lane south of Tilton Compound"),
        # 29 Oct 2026 (task 3c): the holding area's entrance — a vertex of the stored lane line north from the A47 at
        # Billesdon (read on live 29 Oct 2026), so every route along the lane passes it within the 50 m the mark allows
        ("Billesdon Lane holding area (fictional)", "Lane entrance"): ([-0.92094, 52.6226], "the lane north from the A47 at Billesdon"),
    }
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}

    def access_road(g):
        road, road_name = ROAD_AT[(names[g["location_id"]], g["name"])]     # a KeyError here = a gate with no road point
        # set back along the line from the road point towards where the gate was (into the site)
        kx = 111320.0 * math.cos(math.radians(road[1]))
        dx, dy = (g["lon"] - road[0]) * kx, (g["lat"] - road[1]) * 111320.0
        d = math.hypot(dx, dy) or 1.0
        at = offset(road, BELLMOUTH_M * dx / d, BELLMOUTH_M * dy / d)
        z = zones.create_zone(f"{names[g['location_id']]}: {g['name']} access road",
                              {"type": "LineString", "coordinates": [list(road), at]},
                              kind=zones.HAUL_KIND, affects_routing=True, speed_kph=10, haul_mode="splice",
                              note=f"Bellmouth off {road_name} to the gate: room for two lorries off the road (fictional).")
        assert "error" not in z, z
        res = gates.update_gate(g["id"], lat=at[1], lon=at[0], access_zone_id=z["id"])
        assert "error" not in res, res
        return z

    # 29 Oct 2026 (task 3c): the holding area's entrance gets its road LAST (after the advisory zones), so every zone id
    # the demo already carries — the access roads, the viaduct site's inside, the advisory zones — keeps its number
    for g in gates.list_gates():
        if g["location_id"] == loc["HA"]:
            continue
        z = access_road(g)
    assert z["id"] == "Z028", z        # 28 Oct 2026 (simulation v2): + the viaduct site's two gates (Z027, Z028)

    # --- 28 Oct 2026 (simulation v2, task 0e): the viaduct site's INSIDE — its roads, its areas, its speed ---------------
    # Drawn from the gates' final positions (35 m in from the lane): the top road up to the laydown and down the ramp to
    # the terrace, a spur to the spoil loading, the exit loop past the wheel wash to the gate out. Roads inside a site
    # are never spliced into a public route (zones.location_id); the simulation drives them at the site speed.
    vs = loc["VS"]
    g_in, g_out = gates.get_gate(G["VS_in"]), gates.get_gate(G["VS_out"])
    pin, pout = [g_in["lon"], g_in["lat"]], [g_out["lon"], g_out["lat"]]
    J0, J1, RT, RB = offset(pin, -60, 90), offset(pin, -180, 180), offset(pin, -300, 240), offset(pin, -420, 340)
    PB, SP, LD = offset(pin, -500, 410), offset(pin, -370, 440), offset(pin, -140, 310)
    E1, W = offset(pout, 110, 200), offset(pout, 40, 110)
    for name, pts in (("Tilton Viaduct site: top road and terrace ramp", [pin, J0, J1, RT, RB, PB]),
                      ("Tilton Viaduct site: spoil spur", [RB, SP]),
                      ("Tilton Viaduct site: laydown spur", [J1, LD]),
                      ("Tilton Viaduct site: exit loop", [J0, E1, W, pout])):
        z = zones.create_zone(name, {"type": "LineString", "coordinates": pts}, kind=zones.HAUL_KIND, location_id=vs,
                              note="Internal haul road at the site speed (fictional).")
        assert "error" not in z, z
    assert z["id"] == "Z032", z
    def rect(c, w, h):
        return {"type": "Polygon", "coordinates": [[offset(c, -w / 2, h / 2), offset(c, w / 2, h / 2), offset(c, w / 2, -h / 2),
                                                    offset(c, -w / 2, -h / 2), offset(c, -w / 2, h / 2)]]}
    for name, act, mats, mins, bays, level, geom, note in (
            ("Pier bases", "unload", [READY, BALLAST, SMALL], 5, 1, "river terrace, −8 m", rect(PB, 140, 110),
             "Concrete to the pump, stone to the piling mat; one pump bay (fictional)."),
            ("Deck and laydown", "unload", [STRUCT, REINF, PRECAST, GENERAL], 5, 2, "top of the bank", rect(LD, 120, 90),
             "Steel, precast and reinforcement off-loaded by the crawler crane; two bays (fictional)."),
            ("Spoil loading", "load", [EARTH], 10, 1, "river terrace, −8 m", {"type": "Point", "coordinates": SP},
             "Piling arisings loaded by the 360 (fictional)."),
            ("Wheel wash", "wash", [], 2, 1, None, {"type": "Point", "coordinates": W}, "Every lorry out (fictional).")):
        a = site_areas.create_area(vs, name, activity=act, materials=mats, service_minutes=mins, bays=bays, level=level,
                                   geometry=geom, note=note)
        assert "error" not in a, a
    assert a["id"] == "A004", a
    res = network.set_site_speed(vs, 8.0)         # 5 mph
    assert "error" not in res, res

    # --- the site's logistics layout (31 Oct 2026, task 4c PR 6): the sample National Grid drawing in the repo's test
    # fixtures, placed on the viaduct site as one phase with no months (every month), so a re-import keeps what the live
    # demo shows. Built from the repo's own file, not from a live export.
    import site_layouts
    with open(LAYOUT_SAMPLE, "rb") as f:
        held = site_layouts.read_file(vs, f.read(), os.path.basename(LAYOUT_SAMPLE), by="tools/make_demo_tenant.py")
    placed = site_layouts.place(vs, {"import_id": held["import_id"], "where": "new",
                                     "phase": {"name": "Site logistics"}}, by="tools/make_demo_tenant.py")
    assert placed["placed"] == LAYOUT_THINGS, placed

    # --- §1.8: the ADVISORY zones of the programme (Z033 on), created after the access roads and the site's inside ---------
    # Advisory: drawn on the map by month and listed in the bulletin's local controls; the router is not told.
    def at_chain(m, east=0.0, north=0.0):
        return offset(point_at(ALIGN_PTS, ALIGN_CHAIN, m), east, north)
    ADVISORY = [
        ("Tilton viaduct works area", box(*at_chain(18500), 700, 400), "works", "2026-05-01", "2028-05-31",
         "Piling, piers and deck of the Tilton viaduct; crane standings and the beam lifts (fictional)."),
        ("Langton cutting works area", box(*at_chain(8000), 900, 500), "works", "2027-04-01", "2028-09-30",
         "The deep cutting; its cut goes to the Noseley embankment by dumpers on site (fictional)."),
        ("A606 night closures for the Melton junction beam lift", box(-0.8650, 52.7462, 400, 250), "closure",
         "2027-04-01", "2027-04-30",
         "A606 closed overnight 22:00–06:00 on the beam-lift nights; signed diversion (fictional)."),
        ("A47 tie-in weekend closures at Tilton", box(-0.9490, 52.6208, 400, 260), "closure", "2028-03-01", "2028-06-30",
         "A47 closed at weekends while the new junction is tied in; signed diversion (fictional)."),
        ("Harborough A6 tie-in", box(*at_chain(0), 400, 300), "works", "2029-06-01", "2029-10-31",
         "The new road tied in to the A6 at the Harborough South roundabout; lane closures, nights mostly (fictional)."),
        ("Market Harborough town centre: Christmas trading 2027", box(-0.9205, 52.4775, 700, 500), "closure",
         "2027-12-01", "2027-12-31",
         "No scheme lorries through the town centre during Christmas trading, by agreement with the council (fictional)."),
        ("Market Harborough town centre: Christmas trading 2028", box(-0.9205, 52.4775, 700, 500), "closure",
         "2028-12-01", "2028-12-31",
         "No scheme lorries through the town centre during Christmas trading, by agreement with the council (fictional)."),
    ]
    # 28 Oct 2026 (task 0c, the demo narrative's F4): Christmas trading 2027 DIVERTS the routes through the town centre in
    # its dates, as ticked on live that evening (R003, R012, R038, R040 in Dec 2027); a live refresh compares the zones'
    # affects_routing, so the package says what live says. 2028 stays advisory, as on live.
    ROUTING_IN_DATES = {"Market Harborough town centre: Christmas trading 2027"}
    for name, geom, kind, s_on, e_on, note in ADVISORY:
        z = zones.create_zone(name, geom, kind=kind, affects_routing=name in ROUTING_IN_DATES,
                              starts_on=s_on, ends_on=e_on, note=note)
        assert "error" not in z, z
    # 29 Oct 2026 (task 3c): the holding area's access road, the last zone (see access_road above)
    z = access_road(next(g for g in gates.list_gates() if g["location_id"] == loc["HA"]))
    assert z["id"] == "Z040", z

    # --- D75 (22 Oct 2026, abnormal loads phase 3): three fictional abnormal loads ------------------------------------
    # Each is its own planned movement (D66a), counted apart from the lorries (D70, D71), unrouted in the package: a
    # planner presses Draw the route on live (one HERE call each; the demo's HERE key lives on Render). Statuses: the
    # units approved (so the public map shows one once drawn, D68), the crane and the beams pending (a planner's call).
    import abnormal
    PLANNER_ACC = {"role": "planner", "ipt": None, "label": "Planner"}
    ABNORMAL_LOADS = [
        ("approved", {"name": "Modular office units, 4.6 m wide, for Langton Compound", "ipt": "IPT2", "origin_id": loc["RH"],
                      "origin_gate_id": G["RH"], "dest_id": loc["C2"], "dest_gate_id": G["C2"], "date_from": "2027-03-08", "date_to": "2027-03-12",
                      "time_band": "day", "movements": 1, "width_m": 4.6, "height_m": 3.9, "length_m": 16.5, "gross_t": 40.0, "max_axle_t": 9.0,
                      "axle_count": 6, "vehicle_type": "low_loader", "indivisible": True, "escort_planned": "private",
                      "note": "Two-storey office units for the compound set-up, rail-delivered to the terminal; 4.6 m wide so the police are "
                              "told and an escort goes with it (fictional)."}),
        ("pending", {"name": "250 t-class mobile crane for the Melton beam lift, in and out", "ipt": "IPT1", "origin_id": loc["CD"],
                     "origin_gate_id": G["CD"], "dest_id": loc["C4"], "dest_gate_id": G["C4"], "date_from": "2027-04-05", "date_to": "2027-04-06",
                     "time_band": "day", "movements": 2, "return_abnormal": True, "width_m": 3.0, "height_m": 4.0, "length_m": 16.0,
                     "gross_t": 72.0, "max_axle_t": 12.0, "axle_count": 6, "vehicle_type": "mobile_crane", "indivisible": True,
                     "escort_planned": "none",
                     "note": "Travels under its own power at 72 t (STGO Category 2); the counterweight comes as ordinary loads. Back out "
                             "after the lift (fictional)."}),
        ("pending", {"name": "32 m precast bridge beams for the Melton junction bridges", "ipt": "IPT1", "origin_id": loc["EP"],
                     "origin_gate_id": G["EP"], "dest_id": loc["C4"], "dest_gate_id": G["C4"], "date_from": "2027-04-12", "date_to": "2027-04-14",
                     "time_band": "night", "movements": 9, "width_m": 2.8, "height_m": 4.2, "length_m": 36.0, "gross_t": 78.0, "max_axle_t": 11.0,
                     "axle_count": 8, "vehicle_type": "modular_trailer", "indivisible": True, "escort_planned": "private",
                     "note": "Nine beams, one a night, for the A606 overbridge deck; 36 m overall, so a Special Order (over 30 m), applied "
                             "for ten weeks ahead; the A606 night closures are booked for the lift (fictional)."}),
    ]
    for status, body in ABNORMAL_LOADS:
        r = abnormal.create(body, PLANNER_ACC, by="tools/make_demo_tenant.py")
        assert r.get("ok"), r
        if status != "pending":
            st = abnormal.set_status(r["movement"]["id"], status, PLANNER_ACC, by="tools/make_demo_tenant.py")
            assert st.get("ok"), st
    assert [m["id"] for m in abnormal.rows(PLANNER_ACC)] == ["AL001", "AL002", "AL003"]

    # --- D105: the carbon target, shipped -----------------------------------------------------------------------
    # A % target agreed at programme start from two decisions: Langton's surplus cut to the soil recycling hub (R019 →
    # R020) instead of the inert landfill, and recycled aggregate in "Large aggregate / ballast" (30 %: ASSUMPTION).
    # Both work on unbaked routes: a disposal figure and a material figure are tonnes × factor, with no distance. After
    # the bake the swap's haulage saving adds on top; re-set the % once on live only if it must match exactly.
    levers = [{"driver": "disposal", "scope": {"route_id": ROUTE_ID[("C2", "TIP", EARTH)]},
               "to_route": ROUTE_ID[("C2", "HUB", EARTH)]},
              {"driver": "recycled", "scope": {"category": BALLAST}, "pct": 30}]
    ui = {"recycled": {BALLAST: 30}, "epd": {}, "reused": {}, "vehicle": {}, "electric": False, "distance": {},
          "supplier": {}, "alt": {}, "disposal": {ROUTE_ID[("C2", "TIP", EARTH)]: {"to_route": ROUTE_ID[("C2", "HUB", EARTH)]}}}
    ct = carbon_target.set_from_levers({"role": "planner", "ipt": None}, "pct", levers, ui_state=ui,
                                       by="tools/make_demo_tenant.py")
    assert ct and ct["mode"] == "pct" and ct["pct_below"] > 0, ct

    # --- council areas (--with-areas; §2.2b; the shipped package since D102) -------------------
    if with_areas:
        import areas
        with open(AREAS_SEED, encoding="utf-8") as f:
            res = areas.import_collection(json.load(f), replace=True)
        assert res["ok"] and res["imported"] == 9, res

    # --- export -----------------------------------------------------------------------
    pkg = tenant_package.export_tenant(app_version="modus-g2")
    pkg["_readme"] = ("Synthetic demo tenant v3 — the Wolds Link, a fictional ~32 km A-road dualling scheme in the East "
                      "Midlands, as a four-year programme (Jan 2026 – Dec 2030; the north opens Dec 2028, the whole road "
                      "Oct 2029). Nothing in it is anyone's data. Import into an EMPTY tenant "
                      "(POST /api/admin/tenant/import; replace=1 over an older demo), then bake the network (HERE) for EVERY "
                      "planning vehicle the lines use (Artic Tipper, Artic Flatbed, and the two concrete mixers on the "
                      "batching plants' routes) — routes read UNBAKED until then, and the A47 closure only re-routes what "
                      "is baked while it is in force. History (actuals, the account week, day actuals, confirmations, "
                      f"stockpile draw) is typed up to {as_of.isoformat()} (the generator's --as-of). Diesel index: fetched "
                      "automatically from DESNZ weekly road fuel prices (H1); fuel_index below is a typed placeholder applied "
                      "on import if the GB row is empty. Distances read in miles (tenant.distance_unit); km is what is stored. "
                      "tenant.demo_notice puts 'DEMO · Fictional scheme' on every screen and export. The council areas "
                      "ship in the package (D102) and the carbon target too (D105). Carbon planner: Langton Compound's "
                      "surplus cut goes to a fictional inert landfill; a fictional soil-recycling hub nearer by has a route "
                      "and no forecast — the disposal alternative. The asphalt plant's crushed rock rides its own category "
                      "with no material carbon (D112). The two electric lorry profiles are scenario-only: they read the "
                      "diesel twin's baked distances and are never offered on a forecast.")
    # H1: a typed placeholder at the research's second-hand reading of the DESNZ series (≈195.5 p/L,
    # w/c 21 Sep 2026, pump price incl. VAT). The DESNZ fetch replaces it on the first refresh.
    pkg["fuel_index"] = [{"country": "GB", "eur_per_l": 1.955, "bulletin_date": "2026-09-21",
                          "note": "typed placeholder from a second-hand reading of the DESNZ weekly road fuel "
                                  "prices (ULSD pump price incl. VAT); the automatic DESNZ fetch replaces it"}]
    if LIVE_EXPORT:
        copy_live_tables(pkg, LIVE_EXPORT)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=1)
    return pkg


# The tables a live refresh carries over from the live demo unchanged (§1.9): baked and fetched, never generated here.
# 28 Oct 2026 (the demo narrative's F6): + route_choice (task 0c's diversions, made on live by a zone save or Find a way
# round; without it a refresh dropped every diversion) and traffic_counts (fetched with the collisions since 22 Oct).
# 29 Oct 2026 (task 0f-2): + route_hour_times, the busy-hour drive times worked out on live (HERE calls), named by the
# stored lines they matched — copied with route_geometry, so a refresh keeps both or neither
# 31 Oct 2026 (task 4a, PR 3a): + clp_documents and clp_issues, the CLPs people type, send and approve on live (an issue
# keeps its Word file): a refresh must not drop an approved issue
# 31 Oct 2026 (task 4a, PR 3b): + clp_notes, the notes and tasks people leave on those CLPs
# 31 Oct 2026 (task 4a, PR 3c): + clp_reviews, the issues sent to the client's reviewers and their decisions on live.
# The groups (clp_review_groups) are merged instead: the generator's fictional group plus every group made on live
# 31 Oct 2026 (found by test_demo_programme F6 when PR 3c regenerated the package): + the site layouts (task 4c), brought
# in on live (the demo's "Site logistics" layout of Tilton Viaduct, 31 Oct): a refresh must not drop them
# 31 Oct 2026 (task 4c PR 3): + site_layout_pictures, the plans pinned on a phase on live (the package ships none)
LIVE_TABLES = ("route_geometry", "route_sections", "route_area_km", "areas", "route_choice",
               "community_features", "community_meta", "collision_records", "collision_meta", "traffic_counts",
               "route_hour_times", "clp_documents", "clp_issues", "clp_notes", "clp_reviews",
               "site_layouts", "site_layout_phases", "site_layout_imports", "site_layout_pictures")

# 28 Oct 2026 (F6): an abnormal load is generated here but DRAWN on live (Draw the route, Check the roads again), in the
# same row. A refresh keeps live's drawing for a load whose ends and size are unchanged; any other load stays undrawn.
ABNORMAL_DRAWN_COLS = ("geometry_json", "return_geometry_json", "distance_km", "duration_hr", "baked_at", "bake_error",
                       "here_notices_json", "actions_json", "roads_json", "limits_hits_json", "limits_checked_at",
                       "pinch_json")
ABNORMAL_SAME_COLS = ("origin_id", "origin_gate_id", "dest_id", "dest_gate_id", "via_json", "return_abnormal",
                      "width_m", "height_m", "length_m", "rigid_length_m", "gross_t", "max_axle_t", "axle_count",
                      "axle_spacings_m", "vehicle_type")


def _same(v):
    """A value as the comparisons see it: a Postgres export carries BOOLEAN columns as true / false, a package built on
    SQLite as 1 / 0 (Python already treats True == 1; this says so on purpose); floats to 6 places."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        return round(v, 6)
    return v


def copy_abnormal_drawings(live_rows, new_rows):
    """Copy ABNORMAL_DRAWN_COLS from live's row to the new row of the same id when every ABNORMAL_SAME_COLS value
    matches; returns the ids copied."""
    live_by_id = {r.get("id"): r for r in live_rows or []}
    copied = []
    for r in new_rows or []:
        lr = live_by_id.get(r.get("id"))
        if lr is None or any(_same(lr.get(c)) != _same(r.get(c)) for c in ABNORMAL_SAME_COLS):
            continue
        for c in ABNORMAL_DRAWN_COLS:
            r[c] = lr.get(c)
        copied.append(r.get("id"))
    return copied


def copy_live_tables(pkg, path):
    """Copy LIVE_TABLES and the live carbon_target row from a live export into `pkg`. Refuses (SystemExit) when the
    live routes, gates or zones are not the ones written here: their baked geometry would then describe other roads."""
    with open(path, encoding="utf-8") as f:
        live = json.load(f)
    lt, nt = live.get("tables") or {}, pkg["tables"]

    def sig(rows, cols):
        return sorted(tuple(_same(r.get(c)) for c in cols) for r in rows or [])
    problems = []
    for t, cols in (("routes", ("id", "origin_id", "dest_id", "material_category")),
                    ("location_gates", ("id", "location_id", "lat", "lon", "access_zone_id")),
                    ("zones", ("id", "kind", "affects_routing", "geometry", "starts_on", "ends_on")),
                    ("route_haul_roads", ("route_id", "zone_id"))):
        if sig(lt.get(t), cols) != sig(nt.get(t), cols):
            problems.append(f"{t} differ between the live export and this build")
    if problems:
        raise SystemExit("--live-export refused: " + "; ".join(problems) + ". Re-bake on live instead (§4.2).")
    for t in LIVE_TABLES:
        nt[t] = list(lt.get(t) or [])
    # PR 3c: the reviewer groups by id: live's own (a send names one) and the generator's fictional one
    have = {r.get("id") for r in lt.get("clp_review_groups") or []}
    nt["clp_review_groups"] = list(lt.get("clp_review_groups") or []) + [
        r for r in nt.get("clp_review_groups") or [] if r.get("id") not in have]
    copy_abnormal_drawings(lt.get("abnormal_loads"), nt.get("abnormal_loads"))
    row = [r for r in lt.get("config") or [] if r.get("key") == "carbon_target"]
    nt["config"] = [r for r in nt["config"] if r.get("key") != "carbon_target"] + row


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Write the synthetic UK demo tenant package.")
    ap.add_argument("--with-areas", action="store_true",
                    help="also load backend/data/areas_demo.geojson into the package's areas table (off by default; "
                         "the shipped package is built with it)")
    ap.add_argument("--out", default=None, help="where to write the package (default demo/uk-corridor.package.json)")
    ap.add_argument("--as-of", default=SHIPPED_AS_OF,
                    help=f"type the history up to this date, YYYY-MM-DD (default {SHIPPED_AS_OF}, the shipped package); "
                         "another date needs --out outside the checkout")
    ap.add_argument("--live-export", default=None,
                    help="a live export (GET /api/admin/tenant/export) whose baked and fetched tables are copied across; "
                         "needs --out outside the checkout")
    args = ap.parse_args()
    try:
        datetime.date.fromisoformat(args.as_of)
    except ValueError:
        ap.error("--as-of must be a date, YYYY-MM-DD")
    if args.as_of != SHIPPED_AS_OF or args.live_export:
        if not args.out or not _outside_checkout(args.out):
            ap.error("--as-of (other than the shipped date) and --live-export need --out to a path OUTSIDE the "
                     "checkout: test_modus.py allows only the shipped package in the repository")
    AS_OF, LIVE_EXPORT = args.as_of, args.live_export
    OUT = args.out or OUT
    pkg = build(with_areas=args.with_areas, out=OUT)
    c = tenant_package.counts(pkg)
    print(f"wrote {OUT}")
    print("corridor length %.1f km; history to %s" % (LENGTH_M / 1000, AS_OF))
    for t in tenant_package.ORDER:
        print(f"  {t:22s} {c.get(t, 0)}")
