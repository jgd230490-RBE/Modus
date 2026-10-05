"""
tools/make_demo_tenant.py — the synthetic UK demo tenant, as a package. Wayscope (G2, 16 Sep 2026).

    python3 backend/tools/make_demo_tenant.py            # writes demo/uk-corridor.package.json

WHAT IT MAKES
-------------
A fictional ~32 km A-ROAD DUALLING scheme in the East Midlands — "the Wolds Link",
running north from Market Harborough towards Melton Mowbray (H2, 5 Oct 2026: re-framed
from the v1 rail corridor for Highways UK) — with three quarries placed in the county's
real crushed-rock heartland under invented names, one rail freight terminal, four
compounds, three stockpiles, three delivery teams, six mainline work sections and two
point assets, eighteen routes, four months of approved forecasts (Sep–Dec 2026) plus one
Pending and one Rejected line, typed actuals into October, a confirmed commit week, a
stockpile near capacity, contract rates on some routes, a target rate, a fuel share,
GBP, miles, a UK country code, an alignment overlay with chainage, package bands and
boundaries — and, from v2: a gate or two on every site (entry and exit on different
roads where that is how the site works), two temporary haul roads ATTACHED to the routes
that use them, three geofences (a works-zone closure that re-routes three routes, an
advisory 7.5 t village limit, an advisory works area), daily vehicle caps on the village
routes, and the tenant's demo notice on every screen and export.

NOTHING IN IT IS ANYONE'S DATA. Every name is invented; the quantities are made up to
look plausible; the coordinates are chosen so HERE's truck routing finds sensible roads.

HOW IT MAKES IT
---------------
Not by hand-writing rows. It boots the product against a scratch SQLite database and
calls the same functions the app calls — create_location, create_route, the forecast
insert, weeks.materialise_window, set_actual, confirm_week, stockpiles.set_capacity,
tenant_package.set_overlay — then EXPORTS the tenant with tenant_package.export_tenant.
So every row in the package is one the product itself would have written, and the
package format is exercised end to end every time this runs.

WHAT IT CANNOT MAKE
-------------------
Route geometry. Baking needs HERE, which is never called from a build sandbox. After
importing the package on a deployment, bake the network (Routes page → Bake all, or
POST /api/admin/bake-routes) — 18 routes × the planning vehicles × 2 legs is a few
hundred HERE calls, inside the free tier. Until then every Look-ahead line reads
UNBAKED, by the product's own rule.
"""
import datetime
import json
import math
import os
import random
import sys
import tempfile
import types

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
import stockpiles            # noqa: E402
import costing               # noqa: E402
import zones                 # noqa: E402
import gates                 # noqa: E402
import haul                  # noqa: E402
import tenant_package        # noqa: E402

random.seed(20260916)

OUT = os.path.join(ROOT, "demo", "uk-corridor.package.json")
TENANT_NAME = "Wolds Link dualling — demo scheme"
DEMO_NOTICE = "Fictional demo scheme · nothing here is real"
START_YEAR = 2026
MONTHS = [9, 10, 11, 12]          # Sep–Dec 2026, month_index == month for 2026


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


def build():
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
            ("earthworks", "Earthworks", "Cut, fill, spoil to tip, landscaping.", True),
            ("stations", "Stations", "Not part of a road scheme.", False)):
        db.execute("UPDATE disciplines SET label = ?, scope_note = ?, in_scope = ? WHERE tenant_id = ? AND id = ?",
                   (label, note, in_scope, db.current_tenant(), did))

    # --- the tenant block, GBP, UK --------------------------------------------------
    doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
    # H1 (29 Sep 2026): GB, GBP, and the tenant READS MILES (HU5, per tenant; km is stored)
    doc["tenant"] = {"name": TENANT_NAME, "team_label": "Team", "currency": "GBP", "country": "GB",
                     "distance_unit": "mi", "demo_notice": DEMO_NOTICE}
    doc["seasonal_restrictions"] = []
    # H1: a GB coefficient set with its sources, in GBP. The three ASSUMPTIONS are labelled
    # as such, exactly as the EE seed's are; the rest carry a public source.
    fp = doc["fair_price"]
    fp["_demo_note"] = ("Demo tenant (GB): a GBP coefficient set with sources, written 29 Sep 2026 (H1). "
                        "vehicle_new_price_eur, running_eur_per_km and margin_pct are ASSUMPTIONS to replace "
                        "with the fleet's own figures; the driver rate is derived from public statistics. "
                        "Field names keep their _eur_ suffix — every figure is in the tenant's currency, £.")
    fp["_driver_source"] = ("ONS Annual Survey of Hours and Earnings 2025 (provisional), as quoted in DfT Road "
                            "Freight Statistics 2025 'HGV driver vacancies in the UK': median hourly pay for HGV "
                            "drivers £16.25 (RHA Pay Report 2026, survey Oct–Nov 2025: C+E median £15.05/h, C median "
                            "£14.50/h). Taken as £16.25 × 1.28 employer on-costs (employer NI ≈ 13 % effective at this "
                            "pay, 3 % pension, ≈ 12 % holiday accrual — ASSUMED multiplier) / 0.85 productive = £24.5/h, "
                            "rounded to £24.")
    fp["driver_eur_per_h"] = 24.0
    fp["_vehicle_standing_source"] = ("ASSUMPTION — no public UK source for a tipper fleet's standing cost. "
                                      "vehicle_new_price_eur £150,000 (a 44 t artic tipper outfit or an 8-wheeler "
                                      "tipper at the upper end) over 7 years to a 20 % residual = £17,143/yr; insurance "
                                      "3 % of price = £4,500/yr; VED + HGV road user levy ≈ £1,300/yr (check against the "
                                      "current VED tables); / 1,800 operating h/yr = £12.7/h, rounded to £13. Only the "
                                      "derivation is shown; the price is the number to replace.")
    fp["vehicle_new_price_eur"] = 150000
    fp["vehicle_standing_eur_per_h"] = 13.0
    fp["_running_source"] = ("ASSUMPTION — tyres, maintenance and repairs per km, EXCLUDING fuel (fuel comes from the "
                             "DESNZ index). £0.12/km ≈ 19 p/mile. The RHA Cost Tables 2026 running figure for a 44 t "
                             "artic (78.21 p/mile, members only, cited second-hand) INCLUDES fuel and is not used "
                             "directly. Replace with the fleet's own figure.")
    fp["running_eur_per_km"] = 0.12
    fp["_margin_source"] = "ASSUMPTION — a haulier's margin on top of cost. Replace with the figure the client considers fair."
    fp["margin_pct"] = 8.0
    fp["consumption"]["_source"] = ("artic laden ~34 L/100 km: ICCT 'Fuel efficiency technology in European heavy-duty "
                                    "vehicles' (2018), regional delivery cycle; +0.4 L/100 km per tonne of payload (low end): "
                                    "UK DfT 'Effects of payload on the fuel consumption of trucks' — both via lkw-control.com "
                                    "(read 2026-09-10). Empty = laden − 0.4 × payload: artic 34 − 0.4 × 26 = 23.6. Rigid 32 t "
                                    "average-laden 38.6 L/100 km DERIVED from the DESNZ 2026 factors in this file (rigid >17 t "
                                    "0.99773 kg CO2e/km ÷ 2.58354 kg CO2e/L diesel), then 38.6 − 0.4 × 20 = 30.6, rounded to 31 "
                                    "empty. The rigid figure is the weakest number in this block.")
    fp["consumption"]["rigid"]["l_per_100km_empty"] = 31.0
    fp["_README"] = ("The FAIR PRICE model's coefficients (backend/fairprice.py) for this demo tenant, in £, each "
                     "with its source; three are ASSUMPTIONS to replace. Edit on Config → Costing · fuel. The diesel "
                     "price is NOT here: it is the live national index row (fuel.py — DESNZ weekly road fuel prices "
                     "for a GB tenant).")
    fp["_sanity_source"] = ("IRU (2025): goods transport in Europe costs EUR 0.50–2.00 per km all-in — a check on the "
                            "model's output, not an input. In £ at £1.955/L diesel the fixture trip (60 km round trip, "
                            "20 t) lands inside that band; a figure outside it means a coefficient is wrong.")
    fp["season"]["thaw_months"] = []            # no spring axle-load season on UK roads
    fp["season"]["_source"] = ("Winter: US DOE fueleconomy.gov/feg/coldweather.shtml — cars ~15 % worse at −7 °C in city "
                               "driving; HGVs at road speed with warm engines suffer less, so +8 % Nov–Mar is an assumption "
                               "inside a sourced range. Thaw: none — Great Britain has no spring axle-load season.")
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
    ws_rows = []
    for sid, name, team, ds, a, b in SECTIONS:
        ws_rows.append({"section_id": sid, "parent_section_id": None, "design_section_id": ds, "ipt_id": team,
                        "name": name, "primary_discipline": None, "in_scope": True, "active": True,
                        "km_from": a / 1000.0, "km_to": (b if b is not None else LENGTH_M) / 1000.0,
                        "scope_note": "Mainline band. Chainage is the scheme's single global datum, 0+000 at the Harborough end.",
                        "receives_override": None})
    for sid, name, team, ds, parent in POINT_SECTIONS:
        ws_rows.append({"section_id": sid, "parent_section_id": parent, "design_section_id": ds, "ipt_id": team,
                        "name": name, "primary_discipline": None, "in_scope": True, "active": True,
                        "km_from": None, "km_to": None, "scope_note": "A point asset inside its parent band, not a band of its own.",
                        "receives_override": None})
    tenant_package.import_rows("work_sections", ws_rows)

    # --- locations ------------------------------------------------------------------
    BALLAST, SMALL, EARTH = "Large aggregate / ballast", "Small aggregate", "Earthworks / soil"
    PRECAST, STEEL, GENERAL = "Precast / concrete", "Steel / rail", "General / imported"
    loc = {}

    def add(key, name, role, loc_type, lon, lat, supplies=None, receives=None, vendor=None, detail=None):
        r = network.create_location(name, role, materials=supplies or [], lat=lat, lon=lon, loc_type=loc_type,
                                    supplies=supplies or [], receives=receives or [], vendor=vendor, detail=detail)
        loc[key] = r["id"]
        return r["id"]

    # Quarries in the county's real crushed-rock heartland, invented names, positions near main roads.
    add("Q1", "Kilby Ridge Quarry", "origin", "Quarry", -1.2380, 52.5610, supplies=[BALLAST, SMALL],
        vendor="Kilby Ridge Aggregates Ltd (fictional)", detail="Granite. Weighbridge in, separate exit onto the main road. Road despatch 06:00–18:00.")
    add("Q2", "Northfield Quarry", "origin", "Quarry", -1.1340, 52.7270, supplies=[BALLAST, SMALL],
        vendor="Northfield Stone Co. (fictional)", detail="Granodiorite. Weighbridge queue peaks 07:00–09:00.")
    add("Q3", "Brook Pit", "origin", "Quarry", -0.7520, 52.6940, supplies=[EARTH, SMALL],
        vendor="Brook Pit Sand & Gravel (fictional)", detail="Sand and gravel; earthworks fill.")
    add("RH", "Harborough Rail Freight Terminal", "origin", "Railhead", -0.9180, 52.4785, supplies=[PRECAST, GENERAL, SMALL],
        detail="Rail-delivered precast units, structural steel and aggregate transhipped to road. Fictional.")

    # Compounds and stockpiles along the corridor, ~400 m off the alignment.
    comp_chain = {"C1": 3000, "C2": 8500, "C3": 19000, "C4": 29500}
    comp_names = {"C1": "Harborough Compound", "C2": "Langton Compound", "C3": "Tilton Compound", "C4": "Melton Compound"}
    for key, m in comp_chain.items():
        p = offset(point_at(ALIGN_PTS, ALIGN_CHAIN, m), east_m=420, north_m=-120)
        add(key, comp_names[key], "destination", "Compound", p[0], p[1],
            receives=[BALLAST, SMALL, EARTH, PRECAST, STEEL, GENERAL],
            detail=f"Site compound at chainage {chain_text(m)}.")
    stock_chain = {"S1": 4500, "S2": 17500, "S3": 25000}
    stock_names = {"S1": "Stockpile South", "S2": "Stockpile Tilton", "S3": "Stockpile North"}
    for key, m in stock_chain.items():
        p = offset(point_at(ALIGN_PTS, ALIGN_CHAIN, m), east_m=-380, north_m=150)
        add(key, stock_names[key], "destination", "Stockpile", p[0], p[1],
            receives=[BALLAST, SMALL, EARTH], detail=f"Bulk stockpile at chainage {chain_text(m)}.")
    stockpiles.set_capacity(loc["S1"], capacity_qty=60000, capacity_unit="t", opening_qty=12000)
    stockpiles.set_capacity(loc["S2"], capacity_qty=40000, capacity_unit="t", opening_qty=31000)   # near capacity
    stockpiles.set_capacity(loc["S3"], capacity_qty=80000, capacity_unit="t", opening_qty=5000)

    # --- routes ---------------------------------------------------------------------
    # (origin, dest, material, team, discipline, section, t/month range, rates)
    section_of = {"C1": "WS1", "C2": "WS2", "C3": "WS4", "C4": "WS6", "S1": "WS1", "S2": "WS4", "S3": "WS5"}
    team_of = {"C1": "IPT3", "C2": "IPT2", "C3": "IPT1", "C4": "IPT1", "S1": "IPT3", "S2": "IPT1", "S3": "IPT1"}
    plan = []
    for d in ("C1", "C2", "C3", "C4"):
        plan.append(("Q1", d, BALLAST, "superstructure", (9000, 18000)))
        plan.append(("Q2", d, SMALL, "substructure", (5000, 14000)))
        plan.append(("RH", d, GENERAL if d in ("C2", "C4") else PRECAST, "superstructure" if d in ("C2", "C4") else "structures", (700, 2200)))
    plan.append(("Q3", "C1", EARTH, "earthworks", (12000, 28000)))
    plan.append(("Q3", "C2", EARTH, "earthworks", (12000, 28000)))
    plan.append(("Q3", "S1", EARTH, "earthworks", (8000, 20000)))
    plan.append(("Q3", "S3", EARTH, "earthworks", (8000, 20000)))
    plan.append(("Q1", "S2", BALLAST, "superstructure", (6000, 12000)))
    plan.append(("Q2", "S3", SMALL, "substructure", (5000, 11000)))
    assert len(plan) == 18, len(plan)

    routes = []
    for o, d, mat, disc, rng in plan:
        team = team_of[d]
        # routes.ipt is free text; the demo writes the slot id, which every display
        # turns into the team's name (taxonomy.team_text / teamText)
        r = network.create_route(loc[o], loc[d], material_category=mat, ipt=team)
        assert "error" not in r, r
        rid = r["id"] if isinstance(r, dict) and "id" in r else r.get("route", {}).get("id")
        routes.append((rid, o, d, mat, disc, section_of[d], team, rng))
    # contract rates on the granite routes (a base charge per load plus £/km each way —
    # the commonest quote shape), a typed target rate for everything else
    for rid, o, d, mat, disc, sec, team, rng in routes:
        if o == "Q1":
            network.set_route_planning(rid, ("rate_eur_per_load", "rate_eur_per_km", "km_basis"),
                                       rate_eur_per_load=95.0, rate_eur_per_km=1.85, km_basis="round_trip")
        elif o == "RH":
            network.set_route_planning(rid, ("rate_eur_per_load", "km_basis"), rate_eur_per_load=180.0, km_basis="round_trip")
    costing.set_target({"eur_per_load": 0.0, "eur_per_t": 6.20, "eur_per_km": 0.0}, by="demo")
    costing.set_fuel({"country": "GB", "share_pct": 30.0}, by="demo")

    # --- forecasts: four approved months per route ------------------------------------
    mi_of = {m: m for m in MONTHS}    # month_index == month for START_YEAR
    n = 0
    for rid, o, d, mat, disc, sec, team, (lo, hi) in routes:
        base = random.uniform(lo, hi)
        for m in MONTHS:
            qty = round(base * random.uniform(0.85, 1.15) / 100.0) * 100
            n += 1
            db.execute(
                "INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, "
                "quantity, unit, material_type, material_description, vehicle_type, submitted_by, "
                "status, reject_reason, ipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (db.current_tenant(), f"F{n:04d}", rid, mi_of[m], disc, sec, float(qty), "t", mat,
                 {BALLAST: "Type 1 sub-base", SMALL: "6F2 capping", EARTH: "Class 1A general fill",
                  STEEL: "Structural steel", PRECAST: "Precast units (culverts, parapets)", GENERAL: "Structural and reinforcement steel"}[mat],
                 "Artic Tipper (44t)" if mat in (BALLAST, SMALL, EARTH) else "Artic Flatbed (44t)",
                 f"{team} planner", "Approved", None, team))

    # --- weeks: materialise, type two weeks of actuals, confirm the commit week -------
    weeks.materialise_window(9, 12)
    sept_lines = db.query("SELECT route_id, discipline, section_id FROM forecasts WHERE tenant_id = ? AND month_index = 9",
                          (db.current_tenant(),))
    for line in sept_lines:
        for wk in (1, 2):
            w = weeks.get_week(line["route_id"], 9, line["discipline"], line["section_id"], wk)
            if not w:
                continue
            planned = float(w.get("planned_qty") or 0)
            actual = round(planned * random.uniform(0.82, 1.06) / 10.0) * 10
            weeks.set_actual(line["route_id"], 9, line["discipline"], line["section_id"], wk,
                             actual_qty=actual, actual_note=None, by="site clerk")
    for line in sept_lines:
        weeks.confirm_week(line["route_id"], 9, line["discipline"], line["section_id"], 3, by="Central Team planner")
    # a stockpile drawdown typed for week 2
    stockpiles.consume(loc["S1"], 9, 2, consumed_qty=4200, unit="t", note="Fill placed at 4+200", by="site clerk")

    # --- a temporary haul road (a zone) ------------------------------------------------
    p1 = point_at(ALIGN_PTS, ALIGN_CHAIN, 7800)
    p2 = point_at(ALIGN_PTS, ALIGN_CHAIN, 9200)
    # v2: mode 'splice' — HERE does not know a road built across a field last month, and
    # 'via' would route between its ends along whatever public road HERE prefers and never
    # say so (haul.py). Spliced, the drawn line IS the geometry, at 20 km/h.
    zr = zones.create_zone("Langton haul road", {"type": "LineString", "coordinates": [offset(p1, 300, -60), offset(p2, 380, 40)]},
                           kind=zones.HAUL_KIND, affects_routing=True, note="Temporary haul road behind Langton Compound (fictional).",
                           speed_kph=20, haul_mode="splice", starts_on="2026-09-01", ends_on="2026-12-31")
    assert "error" not in zr, zr
    # a second haul road: the last 1.2 km into Stockpile North, off the public road
    p3 = point_at(ALIGN_PTS, ALIGN_CHAIN, 24200)
    zr2 = zones.create_zone("Stockpile North haul road", {"type": "LineString", "coordinates": [offset(p3, -900, -300), offset(p3, -420, 120)]},
                            kind=zones.HAUL_KIND, affects_routing=True, note="Temporary haul road from the lane into Stockpile North (fictional).",
                            speed_kph=25, haul_mode="splice", starts_on="2026-09-15", ends_on="2026-12-31")
    assert "error" not in zr2, zr2
    # --- v2: ATTACH the haul roads to the routes that use them (v1 drew one and used it nowhere)
    by_od = {(o, d): rid for rid, o, d, mat, disc, sec, team, rng in routes}
    for key in (("Q1", "C2"), ("Q2", "C2"), ("RH", "C2"), ("Q3", "C2")):
        res = haul.attach(by_od[key], zr["id"])
        assert "error" not in res, res
    for key in (("Q3", "S3"), ("Q2", "S3")):
        res = haul.attach(by_od[key], zr2["id"])
        assert "error" not in res, res

    # --- v2: GATES — a site is entered and left where its roads are, not at its centre ----
    # Quarries: weighbridge in, a separate exit onto the main road. Compounds: one gate on the
    # access road. Harborough Compound (the town end): in from one street, out by another.
    def gate(key, name, east, north, direction, default=False, safety=None, internal=None, note=None):
        row = db.query("SELECT lat, lon FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), loc[key]))[0]
        pt = offset([row["lon"], row["lat"]], east, north)
        g = gates.create_gate(loc[key], name, pt[1], pt[0], direction=direction, safety_minutes=safety,
                              internal_travel_minutes=internal, is_default=default, note=note)
        assert "error" not in g, g
        return g["id"]
    G = {}
    G["Q1_in"]  = gate("Q1", "Weighbridge (in)", -260, 90, "access", default=True, safety=4, internal=6, note="Check in at the weighbridge; 10 mph site limit.")
    G["Q1_out"] = gate("Q1", "Main road exit", 310, -140, "egress", default=True, internal=4)
    G["Q2_in"]  = gate("Q2", "Weighbridge (in)", -240, -120, "access", default=True, safety=4, internal=5, note="Queue peaks 07:00–09:00.")
    G["Q2_out"] = gate("Q2", "A46 exit", 280, 160, "egress", default=True, internal=3)
    G["Q3"]     = gate("Q3", "Pit entrance", 180, -60, "both", default=True, safety=3, internal=4)
    G["RH"]     = gate("RH", "Terminal gate", -150, 200, "both", default=True, safety=5, internal=5, note="Booking slot required at the terminal (fictional).")
    G["C1_in"]  = gate("C1", "Station Road entrance (in)", -210, 150, "access", default=True, safety=5, internal=3, note="Town compound: in by Station Road, out by Mill Lane — one-way on site.")
    G["C1_out"] = gate("C1", "Mill Lane exit", 230, -170, "egress", default=True, internal=3)
    G["C2"]     = gate("C2", "Compound gate", 190, 60, "both", default=True, safety=3)
    G["C3"]     = gate("C3", "Compound gate", -200, 80, "both", default=True, safety=3)
    G["C4"]     = gate("C4", "Compound gate", 210, -90, "both", default=True, safety=3)
    G["S1"]     = gate("S1", "Stockpile gate", 160, 100, "both", default=True)
    G["S2"]     = gate("S2", "Stockpile gate", -170, -90, "both", default=True)
    G["S3"]     = gate("S3", "Stockpile gate", 150, -120, "both", default=True)
    # the routes name their gates explicitly (the resolver would pick the defaults anyway;
    # an explicit choice is what a planner does on the route form)
    origin_gate = {"Q1": G["Q1_out"], "Q2": G["Q2_out"], "Q3": G["Q3"], "RH": G["RH"]}
    dest_gate = {"C1": G["C1_in"], "C2": G["C2"], "C3": G["C3"], "C4": G["C4"], "S1": G["S1"], "S2": G["S2"], "S3": G["S3"]}
    for rid, o, d, mat, disc, sec, team, rng in routes:
        res = gates.set_route_gates(rid, origin_gate_id=origin_gate[o], dest_gate_id=dest_gate[d],
                                    origin_given=True, dest_given=True)
        assert "error" not in res, res

    # --- v2: GEOFENCES ------------------------------------------------------------------
    def box(lon, lat, w_m, h_m):
        a = offset([lon, lat], -w_m / 2, -h_m / 2); b = offset([lon, lat], w_m / 2, h_m / 2)
        return {"type": "Polygon", "coordinates": [[[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]]]}
    # (a) a realignment works closure on the A47 west of Tilton, IN FORCE NOW and for the
    #     show, AFFECTS ROUTING: the routes into Tilton Compound and Stockpile Tilton re-bake
    #     around it (longer, dearer, more CO2 — the before/after on the Dashboard).
    #     Two lessons from the first live bake (5 Oct): a zone only steers HERE while it is in
    #     force on the day of the bake (zones.applies_on — one geometry per route, not per
    #     date), so a closure dated from the show week moved nothing; and the box has to sit on
    #     the line HERE actually drew. The baked A47 runs along 52.620–52.622 N here and the
    #     routes turn north at Tilton (-0.922); the box straddles it 1.8 km west of that turn.
    z_a = zones.create_zone("A47 Tilton realignment works", box(-0.9490, 52.6208, 360, 240), kind="closure",
                            affects_routing=True, starts_on="2026-10-05", ends_on="2026-11-20",
                            note="Carriageway realignment at the new junction tie-in: A47 closed to through traffic, signed diversion (fictional).")
    assert "error" not in z_a, z_a
    # (b) a village 7.5 t limit on the lane to Stockpile North — ADVISORY (the router is not
    #     told): the routes keep using it and the flag says so; paired with the daily caps below
    #     (centred on the lane the two routes were baked along — 5 Oct check)
    z_b = zones.create_zone("Burrough village 7.5 t limit", box(-0.8879, 52.6993, 420, 360), kind="weight_limit",
                            affects_routing=False, starts_on="2026-09-01", ends_on="2026-12-31",
                            note="Community liaison agreement: 7.5 t except for access, 20 vehicles a day, no deliveries before 07:30 (fictional).")
    assert "error" not in z_b, z_b
    # (c) an advisory works area at the Melton end — drawn grey, changes nothing
    #     (straddles the baked Melton approach so grey-over-a-route is what is on screen)
    z_c = zones.create_zone("Melton junction works area", box(-0.8695, 52.7482, 380, 300), kind="works",
                            affects_routing=False, starts_on="2026-10-01", ends_on="2026-12-18",
                            note="Earthworks compound and crane standing for the junction structure (fictional).")
    assert "error" not in z_c, z_c

    # --- v2: daily vehicle caps on the two village routes (ROUTE_CAP fires in the show week) --
    for key, cap in ((("Q3", "S3"), 20), (("Q2", "S3"), 30)):
        res = network.set_route_planning(by_od[key], ("max_vehicles_per_day",), max_vehicles_per_day=cap)
        assert "error" not in res, res

    # --- v2: a Pending and a Rejected line in October, so the approval step is on screen ----
    n_extra = db.query("SELECT COUNT(*) AS n FROM forecasts WHERE tenant_id = ?", (db.current_tenant(),))[0]["n"]
    for status, reason, key, disc in (("Pending", None, ("Q3", "C1"), "structures"),
                                      ("Rejected", "Quantity is double the September rate — confirm with the earthworks lead before resubmitting.", ("Q2", "C2"), "earthworks")):
        n_extra += 1
        rid = by_od[key]
        db.execute(
            "INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, "
            "quantity, unit, material_type, material_description, vehicle_type, submitted_by, "
            "status, reject_reason, ipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), f"F{n_extra:04d}", rid, 10, disc, section_of[key[1]], 6400.0 if status == "Pending" else 24000.0, "t",
             EARTH if key[0] == "Q3" else SMALL, "Class 1A general fill" if key[0] == "Q3" else "6F2 capping",
             "Artic Tipper (44t)", f"{team_of[key[1]]} planner", status, reason, team_of[key[1]]))

    # --- v2: typed actuals into October, so "last week delivered" is not 0 of 18 on the stand --
    oct_lines = db.query("SELECT route_id, discipline, section_id FROM forecasts WHERE tenant_id = ? AND month_index = 10 AND status = 'Approved'",
                         (db.current_tenant(),))
    for line in oct_lines:
        for wk in (1, 2):
            w = weeks.get_week(line["route_id"], 10, line["discipline"], line["section_id"], wk)
            if not w:
                continue
            planned = float(w.get("planned_qty") or 0)
            actual = round(planned * random.uniform(0.86, 1.04) / 10.0) * 10
            weeks.set_actual(line["route_id"], 10, line["discipline"], line["section_id"], wk,
                             actual_qty=actual, actual_note=None, by="site clerk")

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

    # --- export -----------------------------------------------------------------------
    pkg = tenant_package.export_tenant(app_version="modus-g2")
    pkg["_readme"] = ("Synthetic demo tenant v2 — the Wolds Link, a fictional ~32 km A-road dualling scheme in the East "
                      "Midlands. Nothing in it is anyone's data. Import into an EMPTY tenant "
                      "(POST /api/admin/tenant/import; replace=1 over the v1 demo), then bake the network (HERE) for EVERY "
                      "planning vehicle the lines use (Artic Tipper, Artic Flatbed, Rigid 8-wheeler) — routes read "
                      "UNBAKED until then, and the works-zone geofence only re-routes what is baked. Diesel index: fetched "
                      "automatically from DESNZ weekly road fuel prices (H1); fuel_index below is a typed placeholder applied "
                      "on import if the GB row is empty. Distances read in miles (tenant.distance_unit); km is what is stored. "
                      "tenant.demo_notice puts 'Fictional demo scheme' on every screen and export.")
    # H1: a typed placeholder at the research's second-hand reading of the DESNZ series (≈195.5 p/L,
    # w/c 21 Sep 2026, pump price incl. VAT). The DESNZ fetch replaces it on the first refresh.
    pkg["fuel_index"] = [{"country": "GB", "eur_per_l": 1.955, "bulletin_date": "2026-09-21",
                          "note": "typed placeholder from a second-hand reading of the DESNZ weekly road fuel "
                                  "prices (ULSD pump price incl. VAT); the automatic DESNZ fetch replaces it"}]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=1)
    return pkg


if __name__ == "__main__":
    pkg = build()
    c = tenant_package.counts(pkg)
    print(f"wrote {OUT}")
    print("corridor length %.1f km" % (LENGTH_M / 1000))
    for t in tenant_package.ORDER:
        print(f"  {t:22s} {c.get(t, 0)}")
