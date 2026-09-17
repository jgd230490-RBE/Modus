"""
tools/make_demo_tenant.py — the synthetic UK demo tenant, as a package. Modus G2, 16 Sep 2026.

    python3 backend/tools/make_demo_tenant.py            # writes demo/uk-corridor.package.json

WHAT IT MAKES
-------------
A fictional ~32 km rail corridor in the East Midlands — "the Wolds Link", running
north from a railhead at Market Harborough towards Melton Mowbray — with three quarries
placed in the county's real crushed-rock heartland under invented names, one railhead,
four compounds, three stockpiles, three delivery teams, six mainline work sections and
two point assets, eighteen routes, four months of approved forecasts (Sep–Dec 2026), two
weeks of typed actuals, a confirmed commit week, a stockpile near capacity, contract
rates on some routes, a target rate, a fuel share, GBP, a UK country code, and an
alignment overlay with chainage, package bands and boundaries.

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
import tenant_package        # noqa: E402

random.seed(20260916)

OUT = os.path.join(ROOT, "demo", "uk-corridor.package.json")
TENANT_NAME = "Wolds Link — demo corridor"
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
# Waypoints (lon, lat): a plausible new line east of Leicester, Market Harborough →
# Melton Mowbray. Fictional. It is drawn across countryside, not on any real railway.
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
    ("WS8", "Melton South station", "IPT1", "DS2", "WS6"),
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

    # --- the tenant block, GBP, UK --------------------------------------------------
    doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
    doc["tenant"] = {"name": TENANT_NAME, "team_label": "Team", "currency": "GBP", "country": "GB"}
    doc["seasonal_restrictions"] = []
    doc["fair_price"]["season"]["thaw_months"] = []
    doc["fair_price"]["_demo_note"] = ("Demo tenant: the seeded fair-price coefficients are EUR-based public "
                                       "benchmarks read as £ for the demo. Replace with UK figures before "
                                       "quoting a fair price to anyone.")
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
                        "scope_note": "Mainline band. Chainage is the corridor's single global datum, 0+000 at the Harborough railhead.",
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
        vendor="Kilby Ridge Aggregates Ltd (fictional)", detail="Granite. Rail-connected; road despatch 06:00–18:00.")
    add("Q2", "Northfield Quarry", "origin", "Quarry", -1.1340, 52.7270, supplies=[BALLAST, SMALL],
        vendor="Northfield Stone Co. (fictional)", detail="Granodiorite. Weighbridge queue peaks 07:00–09:00.")
    add("Q3", "Brook Pit", "origin", "Quarry", -0.7520, 52.6940, supplies=[EARTH, SMALL],
        vendor="Brook Pit Sand & Gravel (fictional)", detail="Sand and gravel; earthworks fill.")
    add("RH", "Harborough Railhead", "origin", "Railhead", -0.9180, 52.4785, supplies=[STEEL, PRECAST, GENERAL],
        detail="Rail-delivered steel, sleepers and precast units transhipped to road.")

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
        plan.append(("RH", d, STEEL if d in ("C2", "C4") else PRECAST, "superstructure" if d in ("C2", "C4") else "structures", (700, 2200)))
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
                 {BALLAST: "Type 1 / track ballast", SMALL: "6F2 sub-base", EARTH: "Class 1A general fill",
                  STEEL: "Rail and sleepers", PRECAST: "Precast units", GENERAL: "Site consumables"}[mat],
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
    zr = zones.create_zone("Langton haul road", {"type": "LineString", "coordinates": [offset(p1, 300, -60), offset(p2, 380, 40)]},
                           kind=zones.HAUL_KIND, affects_routing=True, note="Temporary haul road behind Langton Compound.",
                           speed_kph=20, haul_mode="via", starts_on="2026-09-01", ends_on="2026-12-31")
    assert "error" not in zr, zr

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
        "version": "wolds-link-demo-1",
        "alignment": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": ALIGN_PTS},
             "properties": {"align_type": "Main Track", "name": "Wolds Link mainline (fictional)"}}]},
        "chainage": {"type": "FeatureCollection", "features": chainage_feats},
        "bands": bands,
        "underlay": None,
        "section_names": section_names,
        "boundaries": boundaries,
        "provisional_bounds": [f"{PROVISIONAL_FROM}/{PROVISIONAL_WS} @ {PROVISIONAL_AT}"],
        "rail": None,
        "view": {"center": [-0.905, 52.62], "zoom": 9.6},
        "_note": "Fictional corridor drawn across countryside. Not a real railway or a proposal for one.",
    }
    res = tenant_package.set_overlay(overlay, by="tools/make_demo_tenant.py")
    assert res["ok"], res

    # --- export -----------------------------------------------------------------------
    pkg = tenant_package.export_tenant(app_version="modus-g2")
    pkg["_readme"] = ("Synthetic demo tenant — the Wolds Link, a fictional ~32 km rail corridor in the East "
                      "Midlands. Nothing in it is anyone's data. Import into an EMPTY tenant "
                      "(POST /api/admin/tenant/import), then bake the network (HERE) — routes read "
                      "UNBAKED until then. Diesel index: type the DESNZ weekly price on Config "
                      "(fuel_index below is applied on import if the GB row is empty).")
    pkg["fuel_index"] = [{"country": "GB", "eur_per_l": 1.43, "bulletin_date": "2026-09-14",
                          "note": "typed placeholder — replace with the current DESNZ weekly average"}]
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
