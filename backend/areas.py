"""
areas.py — movements and carbon per council. Wayscope, 12 Oct 2026 (public map review §2.2b, D27).

WHY THIS EXISTS
---------------
A highway authority reads its own area. The public map's figures were per route (and, since
§2.2d, per shared road section); nothing said how many lorries a day the plan puts into
Harborough, or how much of the month's carbon is emitted inside Melton. DESNZ's national
method apportions road transport to councils by splitting every road link at the authority
boundary and summing per authority (technical report §8.2); this module does that split on
the stored HERE polylines.

THE DATA
--------
  * `areas` (tenanted, in the tenant package): one row per boundary polygon — an id (the ONS
    code for ONS data), a name, a TIER ('district' or 'county'), the GeoJSON geometry
    (Polygon or MultiPolygon, holes kept), the dataset it came from, the licence lines that
    must be printed beside it, and the highway authority where the import names one. Loaded
    by POST /api/admin/areas/import (a GeoJSON FeatureCollection). Nothing is seeded: the
    demo's file, backend/data/areas_demo.geojson (the eight ONS districts round the
    corridor and Leicestershire), is imported by hand or by the demo generator's
    --with-areas option.
    THE SEED FILE, size and provenance: backend/data/areas_demo.geojson is 25,878 bytes, one
    line of JSON, nine Polygons, 1,044 vertices, WGS84 coordinates at most 6 decimal places.
    Fetched 12 Oct 2026 from the ONS Open Geography Portal's ArcGIS FeatureServer, BSC
    (super generalised, 200 m, clipped) editions: Local_Authority_Districts_May_2026_Boundaries_UK_BSC for
    the eight districts and Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BSC
    for Leicestershire (the file names both layer URLs in `sources` and the date in
    `fetched`). Open Government Licence v3.0; its `attribution` is the ONS licence page's two
    lines word for word, which the map prints wherever the polygons are drawn.
  * `route_area_km` (tenanted, derived, in the package): per (route, vehicle profile, leg,
    area) the kilometres of the PRIMARY (alt 0) polyline inside the area, and one row per
    (route, profile, leg) with area_id '*' carrying the leg's whole length — the divisor.
    Rewritten whole, in one transaction, on every rebuild: whenever a primary geometry is
    upserted, cleared or promoted, a bake batch ends, a route is deleted, a package is
    imported (all through road_sections' one hook, so a bake batch still rebuilds once), and
    on an areas import. A tenant with no areas stores no rows.

THE CLIP (pure Python, no geometry library)
-------------------------------------------
Segment by segment: every crossing of the segment with every ring edge near it (a 0.01°
grid of the edges; holes and every polygon of a MultiPolygon are rings like any other) cuts
the segment into pieces; a piece counts when its midpoint is inside by the even-odd rule
over ALL the area's rings. Lengths are haversine, the piece's share by its parameter along
the segment. A piece that runs ALONG a ring edge (a road that IS the boundary) counts half to
the area — so two neighbours sharing that edge get half each and nothing is counted twice.
A segment that no edge comes near takes the inside state of the point before it, so a long
route costs one point-in-polygon test per area plus the stretches near a boundary.

THE MONTH READ (area_load)
--------------------------
The per-route figures are the public map bar's: the same per-line payload the bar, the
bulletin and road_load read (/api/public/month-kpis called as a function), over the routes
the map draws, each on the profile the map draws it with (bulletin.drawn_routes, the
browser's routePropsById). Per area:
  movements_per_day  Σ the month's approved LOADS (tonnes ÷ payload, fractional, the bar's
                     rule) of the routes whose LADEN leg enters the area ÷ the working days.
                     One load = one two-way movement, never doubled; the empty return leg
                     never adds a movement. A route counts in EVERY area its laden leg
                     enters, so the district figures add up to more than the scheme's —
                     the basis sentence says so. "Enters" means at least ENTER_KM (200 m)
                     of the laden leg inside (12 Oct 2026, Track C review): the seed is the
                     ONS BSC edition, generalised to 200 m, so a road running beside a
                     boundary can stray a few metres over the drawn line; a leg inside by
                     less than that is an EDGE route — its km and carbon still count in
                     the area (they are split by km), its movements do not.
  laden_lorry_km     Σ loads × the laden leg's km inside.
  lorry_km           Σ loads × (laden km inside + return km inside): every lorry-km driven
                     in the area, empties included.
  co2_t              Σ route month CO2e (costlines' figure, both legs) × (laden km inside +
                     return km inside) ÷ the route's two-way length (laden + stored return):
                     the carbon emitted inside the area, the DESNZ split. Over the areas of
                     one tier that cover a route it adds up to the route's figure exactly.
                     (Not "÷ the laden length": that would put the empty return's carbon in
                     the council the laden leg runs through — the defect road_sections fixed
                     on 12 Oct.) Never kg per tonne per council.
Carbon is never a zero dressed as a figure: a failed carbon read gives every co2_t None and
names the error; an area's co2_t is None when it has volume and none of its routes has a
figure.

WHAT THIS DOES NOT DO
---------------------
It does not know road names, it does not call HERE, Mapbox, ONS or anything else (the
boundaries arrive as a file), it does not compute parishes, and it does not reproject:
coordinates are lon/lat (WGS84) and the clip is planar in degrees, which at a council's
scale moves a crossing by centimetres.
"""
import json
import math
from datetime import datetime, timezone

import db
import road_sections

TIERS = ("district", "county")
TIER_WORDS = {"district": "local authority district", "county": "county or unitary authority"}
WHOLE_LEG = "*"           # the route_area_km row that carries the leg's whole length
GRID_DEG = 0.01           # the edge grid: about 1.1 km north-south
ON_EDGE_DEG = 1e-9        # a piece's midpoint this close to an edge runs along the boundary
MIN_KM = 0.0005           # half a metre: a polyline that only touches a corner does not enter
# 12 Oct 2026 (Track C review): a route's movements count in an area only when at least this
# much of its laden leg is inside. The seed boundaries are ONS BSC (generalised to 200 m), so a
# road beside a boundary can cross the drawn line for a few metres; that must not add the
# route's whole daily movements to the neighbour. The km and the carbon are split by km and
# keep every piece above MIN_KM.
ENTER_KM = 0.2
MAX_FEATURES = 1000
MAX_VERTICES = 400000


# --------------------------------------------------------------------------- #
#  Geometry                                                                    #
# --------------------------------------------------------------------------- #
def rings_of(geometry):
    """Every ring of a Polygon or MultiPolygon as a list of (lon, lat), closed."""
    g = geometry
    if isinstance(g, str):
        g = json.loads(g)
    t = (g or {}).get("type")
    polys = [g.get("coordinates") or []] if t == "Polygon" else (
        (g.get("coordinates") or []) if t == "MultiPolygon" else [])
    out = []
    for poly in polys:
        for ring in poly or []:
            pts = [(float(p[0]), float(p[1])) for p in ring]
            if len(pts) >= 3 and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) >= 4:
                out.append(pts)
    return out


class Area:
    """One area prepared for clipping: its rings' edges, its box and an edge grid."""

    def __init__(self, area_id, geometry):
        self.id = area_id
        self.edges = []
        for ring in rings_of(geometry):
            for i in range(1, len(ring)):
                a, b = ring[i - 1], ring[i]
                if a != b:
                    self.edges.append((a[0], a[1], b[0], b[1]))
        xs = [e[0] for e in self.edges] + [e[2] for e in self.edges]
        ys = [e[1] for e in self.edges] + [e[3] for e in self.edges]
        self.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, -1.0, -1.0)
        self.grid = {}
        for k, (x1, y1, x2, y2) in enumerate(self.edges):
            for cx in range(_c(min(x1, x2)), _c(max(x1, x2)) + 1):
                for cy in range(_c(min(y1, y2)), _c(max(y1, y2)) + 1):
                    self.grid.setdefault((cx, cy), []).append(k)

    def overlaps(self, x1, y1, x2, y2):
        b = self.bbox
        return not (x2 < b[0] or x1 > b[2] or y2 < b[1] or y1 > b[3])

    def edges_near(self, x1, y1, x2, y2):
        found = set()
        g = self.grid
        for cx in range(_c(x1), _c(x2) + 1):
            for cy in range(_c(y1), _c(y2) + 1):
                ks = g.get((cx, cy))
                if ks:
                    found.update(ks)
        return [self.edges[k] for k in sorted(found)]

    def contains(self, x, y):
        """Even-odd over every ring: a ray east from (x, y), using only the grid row."""
        b = self.bbox
        if x < b[0] or x > b[2] or y < b[1] or y > b[3]:
            return False
        cy = _c(y)
        seen = set()
        inside = False
        for cx in range(_c(x), _c(b[2]) + 1):
            for k in self.grid.get((cx, cy), ()):
                if k in seen:
                    continue
                seen.add(k)
                x1, y1, x2, y2 = self.edges[k]
                if (y1 > y) != (y2 > y):
                    xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                    if xi > x:
                        inside = not inside
        return inside


def _c(v):
    return int(math.floor(v / GRID_DEG))


def _ring_area(ring):
    """Planar (shoelace) area of a closed ring in degrees², unsigned — only to pick the largest part."""
    return abs(sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(1, len(ring)))) / 2.0


def label_point(geometry, scans=15):
    """
    One point INSIDE the area for its label, [lon, lat] — the map draws one label per area from
    it (a label placed on the polygon itself is repeated by Mapbox on every tile the polygon
    crosses: seen in Chrome on 12 Oct, Harborough labelled twice). The largest part of a
    MultiPolygon; across `scans` horizontal lines through it, the middle of the widest stretch
    inside (holes and the other rings of that part cut the stretches), so a concave or holed
    area still gets a point inside. None when the geometry has no ring.
    """
    g = json.loads(geometry) if isinstance(geometry, str) else (geometry or {})
    t = g.get("type")
    polys = [g.get("coordinates") or []] if t == "Polygon" else ((g.get("coordinates") or []) if t == "MultiPolygon" else [])
    best_poly, best_area = None, -1.0
    for poly in polys:
        rings = rings_of({"type": "Polygon", "coordinates": poly})
        if rings and _ring_area(rings[0]) > best_area:
            best_poly, best_area = rings, _ring_area(rings[0])
    if not best_poly:
        return None
    ys = [y for (_, y) in best_poly[0]]
    y0, y1 = min(ys), max(ys)
    best, best_w = None, -1.0
    for k in range(1, scans + 1):
        y = y0 + (y1 - y0) * k / (scans + 1)
        xs = []
        for ring in best_poly:
            for i in range(1, len(ring)):
                (ax, ay), (bx, by) = ring[i - 1], ring[i]
                if (ay > y) != (by > y):
                    xs.append(ax + (y - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):            # even-odd: [x0, x1], [x2, x3], ... are inside
            w = xs[i + 1] - xs[i]
            if w > best_w:
                best, best_w = [(xs[i] + xs[i + 1]) / 2.0, y], w
    if best is None:
        xs = [x for (x, _) in best_poly[0]]
        best = [(min(xs) + max(xs)) / 2.0, (y0 + y1) / 2.0]
    return [round(best[0], 5), round(best[1], 5)]


def _cuts(px, py, qx, qy, edges):
    """The parameters t in [0, 1] along P->Q where it meets an edge (collinear overlaps give both ends)."""
    ts = []
    dx, dy = qx - px, qy - py
    for (x1, y1, x2, y2) in edges:
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        wx, wy = x1 - px, y1 - py
        if abs(den) < 1e-18:
            # parallel: collinear only when the edge's start is on the segment's line
            if abs(wx * dy - wy * dx) > 1e-18:
                continue
            dd = dx * dx + dy * dy
            if dd <= 0:
                continue
            for (ax, ay) in ((x1, y1), (x2, y2)):
                t = ((ax - px) * dx + (ay - py) * dy) / dd
                if 0.0 <= t <= 1.0:
                    ts.append(t)
            continue
        t = (wx * ey - wy * ex) / den
        u = (wx * dy - wy * dx) / den
        if -1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12:
            ts.append(min(1.0, max(0.0, t)))
    return ts


def _on_edge(x, y, edges):
    for (x1, y1, x2, y2) in edges:
        ex, ey = x2 - x1, y2 - y1
        ll = ex * ex + ey * ey
        if ll <= 0:
            continue
        t = ((x - x1) * ex + (y - y1) * ey) / ll
        if t < 0 or t > 1:
            continue
        cx, cy = x1 + t * ex, y1 + t * ey
        if abs(cx - x) <= ON_EDGE_DEG and abs(cy - y) <= ON_EDGE_DEG:
            return True
    return False


def clip_km(coords, area):
    """Kilometres of the polyline `coords` ([[lon, lat], ...]) inside `area` (an Area)."""
    if len(coords) < 2:
        return 0.0
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    if not area.overlaps(min(xs), min(ys), max(xs), max(ys)):
        return 0.0
    total = 0.0
    state = None                       # inside state at the current point, when known
    for i in range(1, len(coords)):
        px, py = coords[i - 1][0], coords[i - 1][1]
        qx, qy = coords[i][0], coords[i][1]
        x1, x2 = (px, qx) if px <= qx else (qx, px)
        y1, y2 = (py, qy) if py <= qy else (qy, py)
        if not area.overlaps(x1, y1, x2, y2):
            state = False              # Q is outside the area's box, so outside
            continue
        near = area.edges_near(x1, y1, x2, y2)
        if not near:
            # no edge comes near this segment: it cannot cross the boundary
            if state is None:
                state = area.contains(px, py)
            if state:
                total += road_sections.haversine_km((px, py), (qx, qy))
            continue
        seg_km = road_sections.haversine_km((px, py), (qx, qy))
        ts = sorted(set([0.0, 1.0] + _cuts(px, py, qx, qy, near)))
        for j in range(1, len(ts)):
            a, b = ts[j - 1], ts[j]
            if b - a <= 1e-12:
                continue
            m = (a + b) / 2
            mx, my = px + m * (qx - px), py + m * (qy - py)
            if _on_edge(mx, my, near):
                w = 0.5                # along the boundary: half to each side
            else:
                w = 1.0 if area.contains(mx, my) else 0.0
            total += seg_km * (b - a) * w
        state = None                   # Q may sit on an edge: work it out when next needed
    return total


# --------------------------------------------------------------------------- #
#  The areas table                                                             #
# --------------------------------------------------------------------------- #
def _first(props, *keys):
    for k in keys:
        v = props.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _ons_field(props, suffix):
    """An ONS code or name field (LAD26CD, CTYUA25NM, ...) when the feature carries one."""
    for k, v in props.items():
        ku = str(k).upper()
        if ku.endswith(suffix) and (ku.startswith("LAD") or ku.startswith("CTYUA") or ku.startswith("CTY")
                                    or ku.startswith("UTLA") or ku.startswith("LTLA")) and v not in (None, ""):
            return str(v).strip()
    return ""


def _attribution_lines(v):
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def parse_collection(fc):
    """
    A GeoJSON FeatureCollection -> the rows to store, or ValueError naming every problem.
    Each feature needs a Polygon or MultiPolygon, an id (`area_id`, `id`, or an ONS ..CD
    field), a name (`name` or an ONS ..NM field) and a tier ('district' or 'county'; an ONS
    LAD field means district, a CTYUA field county). The licence lines are REQUIRED — the
    collection's `attribution` (a list of lines) or each feature's own — because the map
    prints them beside the polygons and must never print another dataset's.
    """
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection" or not isinstance(fc.get("features"), list):
        raise ValueError("the body must be a GeoJSON FeatureCollection with a list of features")
    feats = fc["features"]
    if not feats:
        raise ValueError("the FeatureCollection has no features")
    if len(feats) > MAX_FEATURES:
        raise ValueError(f"too many features ({len(feats)}; at most {MAX_FEATURES})")
    top_attr = _attribution_lines(fc.get("attribution"))
    problems, rows, seen, vertices = [], [], set(), 0
    for n, f in enumerate(feats, start=1):
        if not isinstance(f, dict):
            problems.append(f"feature {n} is not an object")
            continue
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        aid = _first(p, "area_id", "id") or str(f.get("id") or "").strip() or _ons_field(p, "CD")
        name = _first(p, "name") or _ons_field(p, "NM")
        tier = _first(p, "tier").lower()
        if not tier:
            if any(str(k).upper().startswith("LAD") for k in p):
                tier = "district"
            elif any(str(k).upper().startswith(("CTYUA", "CTY", "UTLA")) for k in p):
                tier = "county"
        label = f"feature {n}" + (f" ({name})" if name else "")
        if not aid:
            problems.append(f"{label} has no id (area_id, id or an ONS code)")
        elif aid == WHOLE_LEG:
            problems.append(f"{label}: '{WHOLE_LEG}' is not a usable id")
        elif aid in seen:
            problems.append(f"{label}: the id {aid} appears twice")
        if not name:
            problems.append(f"{label} has no name")
        if tier not in TIERS:
            problems.append(f"{label}: tier must be 'district' or 'county'")
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            problems.append(f"{label} must be a Polygon or MultiPolygon")
            continue
        try:
            rings = rings_of(g)
        except (TypeError, ValueError, IndexError, AttributeError):
            problems.append(f"{label} has coordinates that are not numbers")
            continue
        if not rings:
            problems.append(f"{label} has no ring of three or more points")
            continue
        if any(not (-180 <= x <= 180 and -90 <= y <= 90) for r in rings for (x, y) in r):
            problems.append(f"{label} has a coordinate outside longitude/latitude: send WGS84 (EPSG:4326)")
            continue
        vertices += sum(len(r) for r in rings)
        attr = _attribution_lines(p.get("attribution")) or top_attr
        if not attr:
            problems.append(f"{label} has no licence lines: give the collection an `attribution` list "
                            "(for ONS boundaries the two lines the ONS licence page names)")
        seen.add(aid)
        rows.append({
            "area_id": aid, "name": name, "tier": tier,
            "geometry_json": json.dumps({"type": g["type"], "coordinates": g["coordinates"]}, separators=(",", ":")),
            "source": _first(p, "source") or str(fc.get("name") or "").strip() or None,
            "attribution_json": json.dumps(attr, ensure_ascii=False),
            "highway_authority": _first(p, "highway_authority") or None,
        })
    if vertices > MAX_VERTICES:
        problems.append(f"too many vertices ({vertices}; at most {MAX_VERTICES}) — use a simplified (BSC or BGC) edition")
    if problems:
        raise ValueError("; ".join(problems))
    return rows


def import_collection(fc, replace=False):
    """
    Store the areas of a FeatureCollection for the current tenant (an area with the same id
    is replaced; replace=True clears every area first), then re-clip every route. One
    transaction for the areas; the clip is its own.
    """
    rows = parse_collection(fc)
    tenant = db.current_tenant()
    now = datetime.now(timezone.utc).isoformat()
    steps = []
    if replace:
        steps.append(("DELETE FROM areas WHERE tenant_id = ?", (tenant,)))
    else:
        steps.append(("DELETE FROM areas WHERE tenant_id = ? AND area_id = ?",
                      [(tenant, r["area_id"]) for r in rows], True))
    steps.append(("INSERT INTO areas (tenant_id, area_id, name, tier, geometry_json, source, "
                  "attribution_json, highway_authority, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  [(tenant, r["area_id"], r["name"], r["tier"], r["geometry_json"], r["source"],
                    r["attribution_json"], r["highway_authority"], now) for r in rows], True))
    db.execute_atomic(steps)
    clip = rebuild()
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    return {"ok": True, "imported": len(rows), "tiers": tiers, "replaced": bool(replace),
            "attribution": sorted({l for r in rows for l in json.loads(r["attribution_json"])}),
            "clip": clip}


def stored_areas():
    """The tenant's areas, geometry parsed, tier then name."""
    out = []
    for r in db.query("SELECT area_id, name, tier, geometry_json, source, attribution_json, "
                      "highway_authority, imported_at FROM areas WHERE tenant_id = ?",
                      (db.current_tenant(),)):
        try:
            geom = json.loads(r["geometry_json"] or "null")
            attr = json.loads(r["attribution_json"] or "[]")
        except Exception:
            continue
        out.append({"area_id": r["area_id"], "name": r["name"], "tier": r["tier"], "geometry": geom,
                    "source": r["source"], "attribution": attr,
                    "highway_authority": r["highway_authority"], "imported_at": r["imported_at"]})
    out.sort(key=lambda a: (TIERS.index(a["tier"]) if a["tier"] in TIERS else 9, a["name"], a["area_id"]))
    return out


# --------------------------------------------------------------------------- #
#  The clip index                                                              #
# --------------------------------------------------------------------------- #
def compute():
    """Every primary leg of every profile clipped against every area: a list of row tuples."""
    prepared = [Area(a["area_id"], a["geometry"]) for a in stored_areas()]
    prepared = [a for a in prepared if a.edges]
    if not prepared:
        return []
    rows = []
    for g in db.query(
            "SELECT route_id, vehicle_profile, leg, geometry FROM route_geometry WHERE tenant_id = ? "
            "AND alt_index = 0 AND geometry IS NOT NULL", (db.current_tenant(),)):
        pts = road_sections.coords_of(g["geometry"])
        if len(pts) < 2:
            continue
        key = (g["route_id"], g["vehicle_profile"], g["leg"])
        rows.append(key + (WHOLE_LEG, road_sections.length_km(pts)))
        for a in prepared:
            km = clip_km(pts, a)
            if km >= MIN_KM:
                rows.append(key + (a.id, km))
    return rows


def rebuild():
    """
    Re-clip the current tenant's routes against its areas and replace route_area_km whole,
    in ONE transaction (a reader never sees half an index; a failure keeps the old one).
    Returns the status counts.
    """
    rows = compute()
    tenant = db.current_tenant()
    now = datetime.now(timezone.utc).isoformat()
    db.execute_atomic([
        ("DELETE FROM route_area_km WHERE tenant_id = ?", (tenant,)),
        ("INSERT INTO route_area_km (tenant_id, route_id, vehicle_profile, leg, area_id, km, built_at) "
         "VALUES (?, ?, ?, ?, ?, ?, ?)",
         [(tenant,) + r[:4] + (round(r[4], 4), now) for r in rows], True),
    ])
    return status()


def rebuild_quietly(where):
    """The hook road_sections calls after its own rebuild. Never raises into the bake."""
    try:
        return rebuild()
    except Exception as e:
        print(f"areas: route_area_km not rebuilt after {where}: {e}")
        return None


def status():
    tenant = db.current_tenant()
    n_areas = db.query("SELECT tier, COUNT(*) AS n FROM areas WHERE tenant_id = ? GROUP BY tier", (tenant,))
    rows = db.query("SELECT area_id, COUNT(*) AS n, MAX(built_at) AS built_at FROM route_area_km "
                    "WHERE tenant_id = ? GROUP BY area_id", (tenant,))
    legs = sum(int(r["n"]) for r in rows if r["area_id"] == WHOLE_LEG)
    return {
        "tenant_id": tenant,
        "areas": {r["tier"]: int(r["n"]) for r in n_areas},
        "legs_clipped": legs,
        "rows": sum(int(r["n"]) for r in rows if r["area_id"] != WHOLE_LEG),
        "built_at": max([r["built_at"] for r in rows if r["built_at"]] or [None]),
    }


def clip_table():
    """{route_id: {profile: {leg: {area_id: km}}}} from the stored index ('*' = the whole leg)."""
    out = {}
    for r in db.query("SELECT route_id, vehicle_profile, leg, area_id, km FROM route_area_km WHERE tenant_id = ?",
                      (db.current_tenant(),)):
        out.setdefault(r["route_id"], {}).setdefault(r["vehicle_profile"], {}).setdefault(
            r["leg"], {})[r["area_id"]] = float(r["km"] or 0.0)
    return out


def list_areas():
    """The admin listing: each area without its geometry, with its vertex count, box and how many routes' laden legs enter it."""
    clips = clip_table()
    out = []
    for a in stored_areas():
        rings = rings_of(a["geometry"])
        xs = [x for r in rings for (x, _) in r]
        ys = [y for r in rings for (_, y) in r]
        entering = sorted({rid for rid, per in clips.items() for prof in per.values()
                           if (prof.get("loaded") or {}).get(a["area_id"], 0) >= ENTER_KM})
        out.append({k: a[k] for k in ("area_id", "name", "tier", "source", "attribution", "highway_authority", "imported_at")}
                   | {"vertices": sum(len(r) for r in rings), "rings": len(rings),
                      "bbox": ([round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)] if xs else None),
                      "routes_entering": entering})
    return {"status": status(), "areas": out}


# --------------------------------------------------------------------------- #
#  The month read                                                              #
# --------------------------------------------------------------------------- #
def _drawn():
    """{route_id: the vehicle profile the map draws it with} (bulletin.drawn_routes)."""
    import bulletin
    return {rid: p.get("vehicle_profile") for rid, p in bulletin.drawn_routes().items()}


def _sites_in(prepared):
    """
    ({area_id: [location names inside]}, the number of the tenant's sites with coordinates) —
    the sites by point-in-polygon, and the "of N" the card prints beside an area's count.
    """
    locs = db.query("SELECT name, lat, lon FROM locations WHERE tenant_id = ?", (db.current_tenant(),))
    placed = 0
    for l in locs:
        try:
            float(l["lon"]), float(l["lat"])
            placed += 1
        except (TypeError, ValueError):
            continue
    out = {}
    for a in prepared:
        names = []
        for l in locs:
            try:
                if a.contains(float(l["lon"]), float(l["lat"])):
                    names.append(l["name"] or "")
            except (TypeError, ValueError):
                continue
        out[a.id] = sorted(n for n in names if n)
    return out, placed


# 13 Oct 2026 (W13): the double count, in ONE sentence the area payload's basis, the bulletin's movements-by-council
# footnote and (its first clause) the map's district card all print. test_bulletin.py holds the three equal.
DOUBLE_COUNT = ("A route counts in every area its laden leg enters, so the areas' figures add up to more than "
                "the scheme's.")


def _stops():
    """The tenant's council colour bands (config.council_breaks): {"movements": [..3], "carbon": [..3]}."""
    import config
    return config.council_breaks()


def shapes():
    """
    12 Oct 2026 (Track C review): the polygons, their label points and the licence lines,
    with NO month roll-up — what the map reads once to learn whether the tenant has areas
    and to draw them. The month's figures come from area_load(month, geometry=False) and
    are joined on area_id in the browser, so Play does not re-send every polygon each month.
    """
    areas = stored_areas()
    attribution = []
    for a in areas:
        for line in a["attribution"]:
            if line not in attribution:
                attribution.append(line)
    return {
        "areas": [{"area_id": a["area_id"], "name": a["name"], "tier": a["tier"],
                   "tier_words": TIER_WORDS.get(a["tier"], a["tier"]),
                   "highway_authority": a["highway_authority"], "source": a["source"],
                   "geometry": a["geometry"], "label_point": label_point(a["geometry"])}
                  for a in areas],
        "attribution": attribution,
        "stops": _stops(),             # 13 Oct 2026 (W12): the scheme's colour bands (config.council_breaks)
    }


def area_load(month, working_days=None, drawn=None, geometry=True):
    """
    One entry per stored area with the month's figures (see the module docstring), the
    polygon and the licence lines. `working_days` is main._working_days()'s figure handed
    in; when not given the payload's own (the same reader). `drawn` is {route_id: profile}.
    `geometry=False` leaves out each area's polygon and label point (the map has them from
    shapes()).
    """
    month = int(month)
    payload = road_sections.month_lines(month)
    wd = float(working_days or payload.get("working_days") or 0) or None
    if not wd:
        raise ValueError("working days per month is not set")
    ctx = _month_context(drawn)
    return _area_month(month, payload.get("lines", []) or [], payload.get("co2_error"), wd, ctx, geometry)


def _month_context(drawn=None):
    """19 Oct 2026: what area_load reads that does not change with the month — the routes the map draws, the clip
    table, the stored areas (prepared for point-in-polygon), the sites inside each — read once for every month by
    area_load_all()."""
    drawn = _drawn() if drawn is None else dict(drawn)
    areas = stored_areas()
    prepared = [Area(a["area_id"], a["geometry"]) for a in areas]
    sites, sites_placed = _sites_in(prepared)
    return {"drawn": drawn, "clips": clip_table(), "areas": areas, "sites": sites, "sites_placed": sites_placed,
            "stops": _stops()}


def _area_month(month, lines, co2_error, wd, ctx, geometry=True):
    """One month's area payload (area_load's), from that month's approved lines and the month context."""
    co2_failed = bool(co2_error)
    drawn = ctx["drawn"]

    per_route, not_drawn = {}, {}
    for l in lines:
        rid = l["route_id"]
        if rid not in drawn:
            not_drawn[rid] = not_drawn.get(rid, 0) + 1
            continue
        pr = per_route.setdefault(rid, {"loads": 0.0, "co2_t": 0.0, "co2_lines": 0, "co2_lines_unbaked": 0})
        pr["loads"] += float(l.get("vehicle_loads") or 0.0)
        if l.get("co2_t") is None:
            pr["co2_lines_unbaked"] += 1
        else:
            pr["co2_t"] += float(l["co2_t"])
            pr["co2_lines"] += 1

    def route_co2(rid):
        pr = per_route.get(rid)
        if co2_failed:
            return None
        if not pr or pr["loads"] <= 0:
            return 0.0
        return pr["co2_t"] if pr["co2_lines"] else None

    clips, areas = ctx["clips"], ctx["areas"]
    sites, sites_placed = ctx["sites"], ctx["sites_placed"]
    with_volume = sorted(r for r, pr in per_route.items() if pr["loads"] > 0)

    # each route on the profile the map draws it with
    legs_of = {}
    not_clipped = []
    for rid in with_volume:
        prof = (clips.get(rid) or {}).get(drawn.get(rid)) or {}
        if WHOLE_LEG not in (prof.get("loaded") or {}):
            not_clipped.append(rid)
            continue
        legs_of[rid] = prof

    out_areas = []
    for a in areas:
        aid = a["area_id"]
        loads = laden_km = lorry_km = co2 = 0.0
        co2_known, co2_unbaked = False, []
        routes, return_only, edge = [], [], []
        for rid, prof in legs_of.items():
            lin = (prof.get("loaded") or {}).get(aid, 0.0)
            rin = (prof.get("return") or {}).get(aid, 0.0)
            if lin <= 0 and rin <= 0:
                continue
            ld = per_route[rid]["loads"]
            if lin >= ENTER_KM:
                routes.append(rid)
                loads += ld                         # one load = one two-way movement, laden leg only
            elif lin <= 0 and rin >= ENTER_KM:
                return_only.append(rid)             # empties only: no movement added
            else:
                edge.append(rid)                    # under 200 m inside: km and carbon, no movement
            laden_km += ld * lin
            lorry_km += ld * (lin + rin)
            c = route_co2(rid)
            if c is None:
                co2_unbaked.append(rid)
                continue
            two_way = (prof.get("loaded") or {}).get(WHOLE_LEG, 0.0) + (prof.get("return") or {}).get(WHOLE_LEG, 0.0)
            if two_way > 0:
                co2 += c * (lin + rin) / two_way
                co2_known = True
        has_volume = bool(routes or return_only or edge)
        co2_val = None if co2_failed else (round(co2, 3) if (co2_known or not has_volume) else None)
        out_areas.append({
            "area_id": aid, "name": a["name"], "tier": a["tier"],
            "tier_words": TIER_WORDS.get(a["tier"], a["tier"]),
            "highway_authority": a["highway_authority"], "source": a["source"],
            "movements_per_day": round(loads / wd, 2),
            "loads": round(loads, 3),
            "routes": sorted(routes), "routes_count": len(routes),
            "return_only_routes": sorted(return_only),
            "edge_routes": sorted(edge),
            "laden_lorry_km": round(laden_km, 1),
            "lorry_km": round(lorry_km, 1),
            "co2_t": co2_val,
            "co2_t_per_day": (None if co2_val is None else round(co2_val / wd, 3)),
            "co2_routes_unbaked": sorted(co2_unbaked),
            "sites": sites.get(aid, []), "sites_count": len(sites.get(aid, [])),
        })
        if geometry:
            out_areas[-1]["geometry"] = a["geometry"]
            out_areas[-1]["label_point"] = label_point(a["geometry"])

    total_loads = sum(per_route[r]["loads"] for r in with_volume)
    co2_lines = sum(per_route[r]["co2_lines"] for r in with_volume)
    co2_unb = sum(per_route[r]["co2_lines_unbaked"] for r in with_volume)
    # road_load's rule: the routes' month CO2e, None when it is not a figure
    scheme_co2 = (None if (co2_failed or (co2_unb and not co2_lines))
                  else round(sum(per_route[r]["co2_t"] for r in with_volume), 3))
    by_tier = {}
    for t in TIERS:
        vals = [x["co2_t"] for x in out_areas if x["tier"] == t]
        by_tier[t] = (None if (co2_failed or not vals or any(v is None for v in vals)) else round(sum(vals), 3))
    notes = []
    if not areas:
        notes.append("No council areas are loaded for this tenant.")
    if not with_volume:
        notes.append("No approved volume in this month.")
    if not_clipped:
        # The words sweep (Oct 2026): plain words on the public map; the clip itself (it runs on the next routing
        # or council-areas import) is in the technical guide, T10
        notes.append(f"{len(not_clipped)} route(s) with volume are not placed in a council yet. "
                     "They are in the scheme totals.")
    if co2_unb and not co2_failed:
        notes.append(f"{co2_unb} line(s) not routed yet: left out of the carbon, not counted as zero.")
    if not_drawn:
        n = sum(not_drawn.values())
        notes.append(f"{n} line(s) not routed yet are not in these figures.")
    attribution = []
    for a in areas:
        for line in a["attribution"]:
            if line not in attribution:
                attribution.append(line)
    out = {
        "month": month,
        "working_days": wd,
        "enter_km": ENTER_KM,
        "basis": "Two-way movements a day: one load = one two-way movement. An area counts the month's approved "
                 "loads of every route whose laden leg enters it, divided by the working days; the empty return "
                 "adds none. " + DOUBLE_COUNT + " A laden leg enters an area when at least 200 m of it is inside (the "
                 "boundaries are generalised to 200 m); a route inside by less adds its km and carbon there, "
                 "not its movements.",
        "co2_basis": "CO2e in an area = each route's month CO2e (routed km × the vehicle's kg CO2e/km, both legs) × "
                     "its km inside the area (laden and return) ÷ its two-way length: the carbon emitted inside "
                     "the area, the DESNZ split by boundary. Over the areas of one tier that cover a route it adds "
                     "up to the route's figure. Never kg per tonne per council.",
        "areas": out_areas,
        "totals": {
            "movements_per_day": round(total_loads / wd, 2),
            "loads": round(total_loads, 3),
            "routes_with_volume": len(with_volume),
            "sites": sites_placed,
            "co2_t": scheme_co2,
            "co2_t_by_tier": by_tier,
        },
        "routes_not_clipped": not_clipped,
        "routes_not_drawn": sorted(not_drawn),
        # 13 Oct 2026 (W12): the scheme's colour bands, so the map paints with the figures the bulletin prints by
        "stops": ctx["stops"],
        "notes": notes,
        "attribution": attribution,
        "carbon": {"stamp": road_sections._carbon_stamp(),
                   "rule": "CO₂e = routed km × the vehicle's kg CO₂e/km, approved plan only; an area's share = "
                           "that route's month CO₂e × its km inside ÷ its two-way length."},
    }
    if co2_failed:
        out["co2_error"] = co2_error
        notes.append("The carbon figures could not be read, so no CO2e figure is given.")
    return out


# --------------------------------------------------------------------------- #
#  19 Oct 2026 — every month in one read                                       #
# --------------------------------------------------------------------------- #
#: the payload keys that are the same in every month: sent once, under "common"
ALL_COMMON_KEYS = ("working_days", "enter_km", "basis", "co2_basis", "stops", "attribution", "carbon")
#: an area's keys that do not change with the month: sent once per area, under "area_fixed"
ALL_AREA_FIXED_KEYS = ("name", "tier", "tier_words", "highway_authority", "source", "sites", "sites_count")


def area_load_all(working_days, months):
    """
    19 Oct 2026 (the user: "the council heat map doesn't seem to work"). area_load(m, geometry=False) for every month
    1..`months` in ONE read: the month context once, every month's approved lines from one pass
    (main.approved_lines_by_month), then each month by the same _area_month. On Render each month's read took 3.7-7.4 s
    (19 Oct, timed in the user's Chrome), so the councils showed no colour while Play ran at 0.75 s a month.

    Packed so the horizon stays small: what every month shares once under "common", what an area keeps all horizon once
    under "area_fixed", and per month only what changes. unpack_month(packed, m) (and the map's areaUnpack) rebuild
    exactly area_load(m, geometry=False); test_areas.py holds the two equal for every month.
    """
    import main
    wd = float(working_days or 0) or None
    if not wd:
        raise ValueError("working days per month is not set")
    by_month, co2_error = main.approved_lines_by_month()
    ctx = _month_context()
    common, fixed, out = None, {}, {}
    for m in range(1, int(months) + 1):
        pay = _area_month(m, by_month.get(m, []), co2_error, wd, ctx, geometry=False)
        if common is None:
            common = {k: pay[k] for k in ALL_COMMON_KEYS}
        entry = {k: v for k, v in pay.items() if k not in ALL_COMMON_KEYS and k != "areas"}
        entry["areas"] = []
        for a in pay["areas"]:
            fixed.setdefault(a["area_id"], {k: a[k] for k in ALL_AREA_FIXED_KEYS})
            entry["areas"].append({k: v for k, v in a.items() if k not in ALL_AREA_FIXED_KEYS})
        out[str(m)] = entry
    return {"months_count": int(months), "common": common or {}, "area_fixed": fixed, "months": out}


def unpack_month(packed, month):
    """One month of area_load_all()'s pack as area_load(month, geometry=False) returns it (the map's areaUnpack)."""
    entry = (packed.get("months") or {}).get(str(int(month)))
    if entry is None:
        return None
    out = dict(packed.get("common") or {})
    out.update({k: v for k, v in entry.items() if k != "areas"})
    fixed = packed.get("area_fixed") or {}
    out["areas"] = [dict(fixed.get(a["area_id"]) or {}, **a) for a in entry.get("areas") or []]
    return out
