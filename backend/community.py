"""
community.py — the COMMUNITY CONSIDERATIONS layer (14 Oct 2026; item B of the civils / community sessions).

The CLOCS outline CLP template asks each of its three plans to show "community considerations". This module
keeps, per tenant, the schools, hospitals, health centres, community centres, sports facilities, stations,
cycle routes, bus stops and residential areas that lie along the tenant's routes, fetched ONCE from public
sources by a staff action (community.start_refresh) and never on a page view. Staff only: the map shows it
when whoami says staff, the three CLP plans draw it, and GET /api/community refuses the map cookie (401).

THE STRIP (the user, 14 Oct 2026): 250 m each side of every stored route line (the primary road route of
every route, both legs, every vehicle) and 500 m round every site. A feature is kept when any part of it is
inside: a point within the distance, a line or outline with a vertex within it, an outline that contains a
route vertex or a site. Its distance (metres, 0 inside) is stored.

THE SOURCES (decided 14 Oct 2026 after the live diagnostic, notes/community-sources-1014.md): DfE GIAS for
schools, DfT NaPTAN for bus stops and stations, OpenStreetMap (a Geofabrik county extract) for the rest and
for nurseries. community_sources.py downloads and parses; this module decides, stores and serves.

A refresh replaces a source's features only when that source succeeded; a failed source keeps what it had
and its failure is said in words beside the date it was last fetched.

EVERY OPTION (16 Nov 2026, step 2 of the best-option work; notes/session-1116-community-all-options.md): a Fetch now's
strip covers every option the router gave (alt_index 0-9) as well as the ways round a diversion uses (ALL_OPTIONS), so
an alternative's places and cycle routes are counted as fairly as the main route's. Live has had 2 GB since PR #208; the
29 Oct widening ran out of memory on 512 MB. The OpenStreetMap passes can read the county files once per slice of
SLICE_LINES lines (None = one pass); a slice that fails fails its source, so nothing of it is replaced. status() says
whether the stored layer covers every option that exists NOW ("all_options"): each source records the stamp of the
options it was fetched along (options_stamp: no line text read), and a re-route, a new option or a changed diversion
changes the stamp.
"""
import hashlib
import json
import math
import os
import shutil
import tempfile
import threading
from datetime import datetime, date, timedelta, timezone

import db

STRIP_ROUTE_M = 250
STRIP_SITE_M = 500
# the colour system's print rule for an outline: a light tint fill with the full colour as its edge — the PDF
# (export.COMM_FILL_ALPHA) and the map (the payload's fill_alpha) read this one figure
FILL_ALPHA = 0.22

# One colour, one symbol and one word per kind, in the order every legend lists them. Colours from the free
# hues the colour system leaves (notes/colour-system-1010.md): no Volume blue, no breach red, no orange, no
# amber status colour, none of the reserved team / rail / status hexes. Nine categories break the "about
# four" rule, so every kind also carries a shape and its word on the legend (rules 9 and 11).
KINDS = [
    {"key": "residential", "label": "Residential areas", "colour": "#8C6E4A", "symbol": "fill", "geom": "polygon"},
    {"key": "schools", "label": "Schools", "colour": "#DB2777", "symbol": "triangle", "geom": "point"},
    {"key": "hospitals", "label": "Hospitals", "colour": "#4338CA", "symbol": "square-h", "geom": "point"},
    {"key": "health", "label": "Health centres", "colour": "#A21CAF", "symbol": "cross", "geom": "point"},
    {"key": "community", "label": "Community centres", "colour": "#A16207", "symbol": "diamond", "geom": "point"},
    {"key": "sports", "label": "Sports facilities", "colour": "#0891B2", "symbol": "circle", "geom": "point+polygon"},
    {"key": "stations", "label": "Stations and tram stops", "colour": "#1F2024", "symbol": "square", "geom": "point"},
    {"key": "cycle", "label": "Cycle routes (National Cycle Network and cycle paths)", "colour": "#65A30D",
     "symbol": "dash", "geom": "line"},
    {"key": "bus_stops", "label": "Bus stops", "colour": "#78716C", "symbol": "dot", "geom": "point"},
]
KIND_KEYS = [k["key"] for k in KINDS]
KIND_BY_KEY = {k["key"]: k for k in KINDS}

SOURCES = {
    "osm": {"name": "OpenStreetMap", "licence": "ODbL 1.0",
            "attribution": "© OpenStreetMap contributors (ODbL)",
            "url": "https://www.openstreetmap.org/copyright",
            "via": "Geofabrik county extract",
            "kinds": ["residential", "hospitals", "health", "community", "sports", "cycle", "schools"]},
    "gias": {"name": "DfE Get Information about Schools", "licence": "OGL v3.0",
             "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 "
                            "(DfE Get Information about Schools)",
             "url": "https://get-information-schools.service.gov.uk/", "kinds": ["schools"]},
    "naptan": {"name": "DfT NaPTAN", "licence": "OGL v3.0",
               "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 "
                              "(DfT NaPTAN)",
               "url": "https://beta-naptan.dft.gov.uk/", "kinds": ["bus_stops", "stations"]},
    # 22 Oct 2026 (abnormal loads, phase 3): the structures and limits along the roads, from the SAME county extract
    # in a second pass. Not a community layer kind: abnormal_route reads them for a load's potential pinch points.
    "osm_structures": {"name": "OpenStreetMap structures and limits along the roads", "licence": "ODbL 1.0",
                       "attribution": "© OpenStreetMap contributors (ODbL)",
                       "url": "https://www.openstreetmap.org/copyright",
                       "via": "the same Geofabrik county extract, a second pass",
                       "kinds": ["s_bridge", "s_rail", "s_level_crossing", "s_calming", "s_power", "s_limit"]},
}
SOURCE_ORDER = ("osm", "osm_structures", "gias", "naptan")
OSM_SOURCES = ("osm", "osm_structures")      # both credited as OpenStreetMap, never under the OGL
META_ID = "current"
STALE_RUN = timedelta(minutes=30)       # a 'running' row older than this is a dead run, not a live one
# 16 Nov 2026: measured from the run's last sign of life (detail "beat", written at most every BEAT_S while the
# OpenStreetMap passes read), not from its start: the wide strip's pass can outlast 30 minutes and is still alive
BEAT_S = 60
_LOCK = threading.Lock()
# 16 Nov 2026: Fetch now covers every stored option the router gave, not only the main routes and diversions
ALL_OPTIONS = True
MAX_ROUTER_ALT = 9                      # alt_index 10+ is a way round a closed zone (route_choice.WAY_ROUND_BASE)
# the OpenStreetMap passes read the county files once per slice of this many strip lines; None = one pass (measured
# 16 Nov 2026 on live's own lines: see the session note)
SLICE_LINES = None
# the sources the places and cycle routes come from: all three must have been fetched along every option for
# status()["all_options"] (the structures pass feeds no count)
COUNT_SOURCES = ("osm", "gias", "naptan")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
#  The strip                                                                   #
# --------------------------------------------------------------------------- #
class Strip:
    """Route polylines and site points, with distances in metres on a local equirectangular projection
    (well under 1 % at a scheme's size) and a grid of segments so a county's worth of features is quick."""
    CELL = 600.0

    def __init__(self, lines, sites, route_m=STRIP_ROUTE_M, site_m=STRIP_SITE_M):
        self.lines = [l for l in (lines or []) if len(l) >= 2]
        self.sites = list(sites or [])
        self.route_m, self.site_m = route_m, site_m
        pts = [c for l in self.lines for c in l] + [list(s) for s in self.sites]
        lat0 = (sum(p[1] for p in pts) / len(pts)) if pts else 52.0
        self.kx, self.ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
        self.grid = {}
        reach = max(route_m, site_m)
        for l in self.lines:
            for a, b in zip(l, l[1:]):
                A, B = self._xy(a), self._xy(b)
                self._index((A, B, route_m), min(A[0], B[0]) - reach, max(A[0], B[0]) + reach,
                            min(A[1], B[1]) - reach, max(A[1], B[1]) + reach)
        for s in self.sites:
            S = self._xy(s)
            self._index((S, S, site_m), S[0] - reach, S[0] + reach, S[1] - reach, S[1] + reach)
        self.probe = [tuple(c) for l in self.lines for c in l[::5]] + [tuple(s) for s in self.sites]
        # 16 Nov 2026: the probe points and the bare route segments (lon / lat, no reach added) in the same cells, so an
        # outline asks only the cells under its own box instead of every probe and every segment of the strip (the wide
        # strip's OpenStreetMap pass took 62 min on a laptop, 2/3 of it in _crosses). Same answers: an outline's box and a
        # segment's box that overlap share a cell.
        self.probe_grid, self.seg_grid = {}, {}
        for p in self.probe:
            X, Y = self._xy(p)
            self.probe_grid.setdefault((int(X // self.CELL), int(Y // self.CELL)), []).append(p)
        for l in self.lines:
            for a, b in zip(l, l[1:]):
                A, B = self._xy(a), self._xy(b)
                for gx in range(int(min(A[0], B[0]) // self.CELL), int(max(A[0], B[0]) // self.CELL) + 1):
                    for gy in range(int(min(A[1], B[1]) // self.CELL), int(max(A[1], B[1]) // self.CELL) + 1):
                        self.seg_grid.setdefault((gx, gy), []).append((tuple(a), tuple(b)))
        pad_x, pad_y = (reach + 100) / self.kx, (reach + 100) / self.ky
        self.bbox = ([min(p[0] for p in pts) - pad_x, min(p[1] for p in pts) - pad_y,
                      max(p[0] for p in pts) + pad_x, max(p[1] for p in pts) + pad_y] if pts else None)

    def _xy(self, c):
        return (c[0] * self.kx, c[1] * self.ky)

    def _index(self, item, x0, x1, y0, y1):
        for gx in range(int(x0 // self.CELL), int(x1 // self.CELL) + 1):
            for gy in range(int(y0 // self.CELL), int(y1 // self.CELL) + 1):
                self.grid.setdefault((gx, gy), []).append(item)

    @staticmethod
    def _seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    def margin(self, lon, lat):
        """How far INSIDE the strip a point is (>= 0 inside, metres) and its distance to the nearest route or
        site: (inside, distance). Outside the strip → (False, None)."""
        p = (lon * self.kx, lat * self.ky)
        best, inside = None, False
        for a, b, lim in self.grid.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            d = self._seg(p, a, b)
            if d <= lim:
                inside = True
            best = d if best is None or d < best else best
        return inside, (best if inside else None)

    def distance(self, geometry):
        """Metres from the nearest route or site to a GeoJSON geometry when any part of it is in the strip
        (0 when an outline contains a route vertex or a site); None when it is not."""
        from community_sources import polygons_of, in_polygons, bbox_of_coords
        t = (geometry or {}).get("type")
        if t == "Point":
            ok, d = self.margin(*geometry["coordinates"][:2])
            return round(d, 1) if ok else None
        if t == "LineString":
            coords = geometry["coordinates"]
        else:
            polys = polygons_of(geometry)
            coords = [c for poly in polys for ring in poly for c in ring]
            if coords:
                bb = bbox_of_coords(coords)
                for x, y in self._in_cells(self.probe_grid, bb):
                    if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and in_polygons(x, y, polys):
                        return 0.0
                # a route that CROSSES the outline between its vertices (a long straight stretch through a housing
                # estate): any route segment meeting an edge, or ending inside, is in at 0 m
                if self._crosses(polys, bb):
                    return 0.0
        best = None
        for c in coords:
            ok, d = self.margin(c[0], c[1])
            if ok and (best is None or d < best):
                best = d
        return round(best, 1) if best is not None else None

    @staticmethod
    def _seg_cross(p1, p2, q1, q2):
        def o(a, b, c):
            v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            return 0 if abs(v) < 1e-18 else (1 if v > 0 else -1)
        return o(p1, p2, q1) != o(p1, p2, q2) and o(q1, q2, p1) != o(q1, q2, p2)

    def _in_cells(self, grid, bb):
        """Every item of `grid` filed in a cell under the lon / lat box bb, each once (a segment can sit in many)."""
        x0, y0 = self._xy((bb[0], bb[1]))
        x1, y1 = self._xy((bb[2], bb[3]))
        seen = set()
        for gx in range(int(x0 // self.CELL), int(x1 // self.CELL) + 1):
            for gy in range(int(y0 // self.CELL), int(y1 // self.CELL) + 1):
                for item in grid.get((gx, gy), ()):
                    if item not in seen:
                        seen.add(item)
                        yield item

    def _crosses(self, polys, bb):
        from community_sources import in_polygons
        edges = None
        for a, b in self._in_cells(self.seg_grid, bb):
            if max(a[0], b[0]) < bb[0] or min(a[0], b[0]) > bb[2] or max(a[1], b[1]) < bb[1] or min(a[1], b[1]) > bb[3]:
                continue
            if in_polygons(a[0], a[1], polys) or in_polygons(b[0], b[1], polys):
                return True
            if edges is None:
                edges = [(r[i - 1], r[i]) for poly in polys for r in poly for i in range(1, len(r))]
            if any(self._seg_cross(a, b, e1, e2) for e1, e2 in edges):
                return True
        return False

    def keep(self, kind, geometry):
        return self.distance(geometry)


def _thin(coords, step_m=60.0):
    """Every vertex at least step_m apart, and the last one (a route of 4,000 vertices → a few hundred)."""
    if len(coords) < 3:
        return coords
    out, last = [coords[0]], coords[0]
    for c in coords[1:-1]:
        dx = (c[0] - last[0]) * 111320.0 * math.cos(math.radians(c[1]))
        dy = (c[1] - last[1]) * 110574.0
        if math.hypot(dx, dy) >= step_m:
            out.append(c)
            last = c
    out.append(coords[-1])
    return out


def _used_alts():
    """{(route_id, leg, alt_index)} of the stored options a diversion or a busy-hours road uses (route_choice)."""
    try:
        import route_choice
        use = route_choice.in_use()
    except Exception:
        use = {}
    return {(rid, lg, a) for (rid, _p, lg), alts in use.items() for a in alts}


def _option_wanted(row, all_options, used_alt):
    """Whether a stored route_geometry row is in the strip: the main line always; an option the router gave
    (alt_index 1-9) when all_options; a way round a closed zone (10+) only while a diversion uses it."""
    a = int(row.get("alt_index") or 0)
    if not a:
        return True
    if (row["route_id"], row["leg"], a) in used_alt:
        return True
    return bool(all_options) and a <= MAX_ROUTER_ALT


def option_rows():
    """Every stored option the WIDE strip covers now, one short line each: route, lorry type, leg, when the line was
    worked out and its length, never the line text (a light read), sorted. The option NUMBER is left out, so Make
    primary (a swap of numbers) changes nothing; a re-route (even one that gives the same line back), a new option or a
    diversion taking up a way round adds a line no fetch has covered."""
    used_alt = _used_alts()
    rows = set()
    for r in db.query("SELECT route_id, vehicle_profile, leg, alt_index, computed_at, distance_km FROM route_geometry "
                      "WHERE tenant_id = ? AND geometry IS NOT NULL", (db.current_tenant(),)):
        if not _option_wanted(r, True, used_alt):
            continue
        km = r.get("distance_km")
        rows.add("|".join((str(r["route_id"]), str(r["vehicle_profile"]), str(r["leg"]), str(r.get("computed_at") or ""),
                           "" if km is None else f"{float(km):.3f}")))
    return sorted(rows)


def options_stamp(rows=None):
    """A short stamp of option_rows(); None when no option is stored."""
    rows = option_rows() if rows is None else rows
    if not rows:
        return None
    return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def strip_from_db(all_options=False):
    """The tenant's strip: every PRIMARY stored road route (both legs, every vehicle, duplicates thinned out)
    and every site with a position.
    29 Oct 2026 (task 0c, PR B): + every stored option a dated zone's diversion uses (lorries drive it in those
    months), so a fetch covers the schools and homes along a diversion too.
    29 Oct 2026 (the route options compared, route_compare.py): `all_options=True` adds every option HERE gave
    (alt_index 1-9), so the schools, homes and cycle routes along an alternative are fetched too. A way round a closed
    zone (alt_index 10+) stays in only while a diversion uses it.
    16 Nov 2026: a Fetch now asks for the wide strip (refresh(all_options=ALL_OPTIONS)); on 29 Oct it was too heavy for
    the 512 MB deployment, live has had 2 GB since PR #208. Called with no argument this is still the narrow strip."""
    tenant = db.current_tenant()
    lines, seen = [], set()
    used_alt = _used_alts()
    for r in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry FROM route_geometry WHERE tenant_id = ? "
                      "AND geometry IS NOT NULL", (tenant,)):
        if not _option_wanted(r, all_options, used_alt):
            continue
        try:
            coords = json.loads(r["geometry"]) if isinstance(r["geometry"], str) else r["geometry"]
        except Exception:
            continue
        if not coords or len(coords) < 2:
            continue
        thin = _thin([[float(c[0]), float(c[1])] for c in coords])
        key = tuple((round(c[0], 3), round(c[1], 3)) for c in thin[:: max(1, len(thin) // 20)])
        if key in seen:
            continue
        seen.add(key)
        lines.append(thin)
    # 22 Oct 2026 (abnormal loads, phase 3): each load's own drawn line (both legs), so a fetch after a Draw covers
    # the roads an abnormal load takes and not only the lorries' routes
    try:
        for r in db.query("SELECT geometry_json, return_geometry_json FROM abnormal_loads WHERE tenant_id = ? "
                          "AND status != 'withdrawn'", (tenant,)):
            for col in ("geometry_json", "return_geometry_json"):
                try:
                    coords = json.loads(r[col]) if isinstance(r.get(col), str) else r.get(col)
                except Exception:
                    continue
                if not coords or len(coords) < 2:
                    continue
                thin = _thin([[float(c[0]), float(c[1])] for c in coords])
                key = tuple((round(c[0], 3), round(c[1], 3)) for c in thin[:: max(1, len(thin) // 20)])
                if key in seen:
                    continue
                seen.add(key)
                lines.append(thin)
    except Exception:       # noqa: BLE001 — a database without the table (an old copy) keeps the lorries' strip
        pass
    sites = [(float(l["lon"]), float(l["lat"])) for l in db.query(
        "SELECT lon, lat FROM locations WHERE tenant_id = ? AND lat IS NOT NULL AND lon IS NOT NULL", (tenant,))]
    return Strip(lines, sites)


# --------------------------------------------------------------------------- #
#  Storage                                                                     #
# --------------------------------------------------------------------------- #
def _meta_row():
    rows = db.query("SELECT * FROM community_meta WHERE tenant_id = ? AND meta_id = ?", (db.current_tenant(), META_ID))
    return rows[0] if rows else None


def _detail(row):
    try:
        return json.loads(row["detail_json"]) if row and row.get("detail_json") else {}
    except Exception:
        return {}


def _write_meta(state, detail, by=None, started_at=None, fetched_at=None):
    tenant = db.current_tenant()
    row = _meta_row()
    if row:
        db.execute("UPDATE community_meta SET state = ?, started_at = COALESCE(?, started_at), "
                   "fetched_at = COALESCE(?, fetched_at), by_whom = COALESCE(?, by_whom), detail_json = ? "
                   "WHERE tenant_id = ? AND meta_id = ?",
                   (state, started_at, fetched_at, by, json.dumps(detail, ensure_ascii=False), tenant, META_ID))
    else:
        db.execute("INSERT INTO community_meta (tenant_id, meta_id, state, started_at, fetched_at, by_whom, detail_json) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (tenant, META_ID, state, started_at, fetched_at, by, json.dumps(detail, ensure_ascii=False)))


def replace_source(source, feats, fetched_at):
    """One source's features, replaced in one transaction (a failed refresh leaves the old ones)."""
    tenant = db.current_tenant()
    rows, ids = [], set()
    for f in feats:
        fid = f"{source}:{f['source_ref']}"
        if fid in ids:
            continue
        ids.add(fid)
        rows.append((tenant, fid, f["kind"], source, f["source_ref"], f.get("name"), f.get("detail"),
                     json.dumps(f["geometry"], separators=(",", ":")), f.get("dist_m"), fetched_at))
    db.execute_atomic([
        ("DELETE FROM community_features WHERE tenant_id = ? AND source = ?", (tenant, source)),
        ("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
         "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows, True),
    ])
    return len(rows)


def features(kinds=None, bbox=None):
    """Stored features as GeoJSON Features (kind, name, detail, source, distance), in KINDS order."""
    tenant = db.current_tenant()
    want = [k for k in (kinds or KIND_KEYS) if k in KIND_BY_KEY]
    out = []
    for r in db.query("SELECT kind, source, source_ref, name, detail, geometry_json, dist_m FROM community_features "
                      "WHERE tenant_id = ? ORDER BY kind, dist_m, feature_id", (tenant,)):
        if r["kind"] not in want:
            continue
        try:
            g = json.loads(r["geometry_json"])
        except Exception:
            continue
        if bbox and not _geom_touches(g, bbox):
            continue
        out.append({"type": "Feature", "geometry": g,
                    "properties": {"kind": r["kind"], "name": r["name"], "detail": r["detail"],
                                   "source": SOURCES.get(r["source"], {}).get("name", r["source"]), "source_key": r["source"],
                                   "dist_m": r["dist_m"]}})
    order = {k: i for i, k in enumerate(KIND_KEYS)}
    out.sort(key=lambda f: order.get(f["properties"]["kind"], 99))
    return out


def _geom_touches(g, bbox):
    from community_sources import polygons_of
    t = g.get("type")
    if t == "Point":
        cs = [g["coordinates"]]
    elif t == "LineString":
        cs = g["coordinates"]
    elif t == "MultiLineString":           # 31 Oct 2026: the CLP document filters by box; a multi-part line touched nothing
        cs = [c for part in g["coordinates"] for c in part]
    else:
        cs = [c for p in polygons_of(g) for ring in p for c in ring]
    xs, ys = [c[0] for c in cs], [c[1] for c in cs]
    return not (max(xs) < bbox[0] or min(xs) > bbox[2] or max(ys) < bbox[1] or min(ys) > bbox[3]) if cs else False


def status():
    """What the page says: the state of the last refresh, when each source was fetched and what from, the
    strip, the counts per kind, the credit lines."""
    row = _meta_row()
    det = _detail(row)
    counts = {k: 0 for k in KIND_KEYS}
    for r in db.query("SELECT kind, COUNT(*) AS n FROM community_features WHERE tenant_id = ? GROUP BY kind",
                      (db.current_tenant(),)):
        if r["kind"] in counts:
            counts[r["kind"]] = int(r["n"])
    state = (row or {}).get("state") or "never"
    if state == "running" and row and row.get("started_at"):
        try:
            last = max(x for x in (row["started_at"], det.get("beat")) if x)
            if datetime.now(timezone.utc) - datetime.fromisoformat(last.replace("Z", "+00:00")) > STALE_RUN:
                state = "failed"
                det.setdefault("error", "the last refresh stopped without finishing (the server restarted?)")
        except ValueError:
            pass
    sources = []
    for s in SOURCE_ORDER:
        d = (det.get("sources") or {}).get(s) or {}
        sources.append({"key": s, **{k: v for k, v in SOURCES[s].items() if k != "kinds"},
                        "fetched_at": d.get("fetched_at"), "data_date": d.get("data_date"), "files": d.get("files"),
                        "count": d.get("count"), "error": d.get("error")})
    return {"state": state, "all_options": covers_all_options(det),
            "started_at": (row or {}).get("started_at"), "fetched_at": (row or {}).get("fetched_at"),
            "by": (row or {}).get("by_whom"), "error": det.get("error"), "notes": det.get("notes") or [],
            "strip": {"route_m": det.get("route_m", STRIP_ROUTE_M), "site_m": det.get("site_m", STRIP_SITE_M)},
            "counts": counts, "total": sum(counts.values()), "sources": sources,
            "kinds": [dict(k, count=counts[k["key"]]) for k in KINDS],
            "credit": credit_line([s["key"] for s in sources if s["fetched_at"]])}


def covers_all_options(det=None):
    """True only when the stored places and cycle routes were fetched along every stored option that exists NOW: each
    of COUNT_SOURCES last stored its features from a wide strip whose options_stamp equals today's. False after a
    narrow fetch, before any fetch, when a source's last wide fetch failed (it keeps an older layer), and after a
    re-route, a new or dropped option or a diversion's new way round (the stamp moves). The best-option rule reads
    exactly (community.status() or {}).get("all_options")."""
    det = _detail(_meta_row()) if det is None else det
    stamps = {((det.get("sources") or {}).get(s) or {}).get("options_stamp") for s in COUNT_SOURCES}
    if None in stamps:
        return False
    try:
        now = option_rows()
        if not now:
            return False
        stamp = options_stamp(now)
        sets = det.get("option_sets") or {}
        # each source's layer covers today's options when today's are the ones it was fetched along, or fewer
        return all(s == stamp or set(now) <= set(sets.get(s) or ()) for s in stamps)
    except Exception:       # noqa: BLE001 — a read that fails never claims a fair count
        return False


def credit_line(source_keys=None):
    keys = [s for s in SOURCE_ORDER if (source_keys is None or s in source_keys)]
    if not keys:
        return ""
    parts = []
    if any(k in OSM_SOURCES for k in keys):
        parts.append("© OpenStreetMap contributors (ODbL)")
    gov = [SOURCES[s]["name"] for s in keys if s not in OSM_SOURCES]
    if gov:
        parts.append("contains public sector information licensed under the Open Government Licence v3.0 ("
                     + ", ".join(gov) + ")")
    return "Community considerations: " + "; ".join(parts) + "."


def payload(kinds=None):
    """GET /api/community: the features as one GeoJSON FeatureCollection and the status beside it."""
    st = status()
    return {"type": "FeatureCollection", "features": features(kinds), "fill_alpha": FILL_ALPHA, **{k: st[k] for k in (
        "state", "fetched_at", "strip", "counts", "kinds", "sources", "credit", "notes", "error")}}


# --------------------------------------------------------------------------- #
#  Refresh                                                                     #
# --------------------------------------------------------------------------- #
def _osm_files(strip, workdir, fetch):
    """The county extracts the strip touches, downloaded into workdir once per refresh (a file already there — the
    second OSM pass of the same refresh — is not fetched again). Returns (paths, files, data_date)."""
    from community_sources import GEOFABRIK_INDEX, geofabrik_regions, extract_date
    idx_path = os.path.join(workdir, "geofabrik-index.json")
    if not os.path.exists(idx_path):
        fetch["download"](GEOFABRIK_INDEX, idx_path)
    with open(idx_path, encoding="utf-8") as f:
        index = json.load(f)
    regions = geofabrik_regions(index, strip.bbox, strip.probe)
    if not regions:
        raise RuntimeError("no OpenStreetMap county extract covers these routes (outside Great Britain?)")
    if len(regions) > 6:
        raise RuntimeError(f"the routes span {len(regions)} county extracts; the limit is 6")
    paths, files, dates = [], [], []
    for rid, name, url in regions:
        p = os.path.join(workdir, rid.replace("/", "_") + ".osm.pbf")
        meta = p + ".meta.json"
        if os.path.exists(p) and os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                final, n = json.load(f)
        else:
            final, n = fetch["download"](url, p)
            with open(meta, "w", encoding="utf-8") as f:
                json.dump([final, n], f)
        paths.append(p)
        files.append(f"{name} ({final.rsplit('/', 1)[-1]}, {round(n / 1e6, 1)} MB)")
        dates.append(extract_date(final))
    ds = sorted(d for d in dates if d)
    return paths, files, (ds[0] if ds else None)


def strip_slices(strip, size=None):
    """The strip cut into strips of at most `size` lines (every site in each), or [strip] when it is no longer than
    that or size is None. A feature in the whole strip is in at least one slice, at the same nearest distance."""
    size = SLICE_LINES if size is None else size
    if not size or len(strip.lines) <= size:
        return [strip]
    return [Strip(strip.lines[i:i + size], strip.sites, strip.route_m, strip.site_m)
            for i in range(0, len(strip.lines), size)]


def _beating(keep, beat):
    """keep() as it was, calling beat() at most every BEAT_S seconds (the run's sign of life for the stale rule)."""
    if beat is None:
        return keep
    import time as _time
    last = [_time.monotonic()]

    def kept(kind, geometry):
        now = _time.monotonic()
        if now - last[0] >= BEAT_S:
            last[0] = now
            try:
                beat()
            except Exception:       # noqa: BLE001 — a missed beat never stops the fetch
                pass
        return keep(kind, geometry)
    return kept


def _extract_sliced(extract, paths, strip, beat=None):
    """One OpenStreetMap pass per slice over the same files, merged: an object kept by two slices once, at its nearest
    distance. An exception in any slice goes up, so the source fails and nothing of it is replaced."""
    parts = strip_slices(strip)
    if len(parts) == 1:
        return extract(paths, _beating(strip.keep, beat))
    best = {}
    for part in parts:
        for f in extract(paths, _beating(part.keep, beat)):
            k = (f.get("kind"), f["source_ref"])
            old = best.get(k)
            if old is None or (f.get("dist_m") is not None and (old.get("dist_m") is None or f["dist_m"] < old["dist_m"])):
                best[k] = f
    return list(best.values())


def _fetch_osm(strip, workdir, fetch, beat=None):
    paths, files, data_date = _osm_files(strip, workdir, fetch)
    feats = _extract_sliced(fetch["osm_extract"], paths, strip, beat)
    return feats, files, data_date


def _fetch_osm_structures(strip, workdir, fetch, beat=None):
    """22 Oct 2026 (abnormal loads, phase 3): the second pass over the same files."""
    paths, files, data_date = _osm_files(strip, workdir, fetch)
    feats = _extract_sliced(fetch["osm_structures_extract"], paths, strip, beat)
    return feats, files, data_date


def _fetch_gias(strip, workdir, fetch, today):
    from community_sources import gias_url, gias_extract
    p = os.path.join(workdir, "gias.csv")
    err = None
    for back in range(0, 4):           # the extract is dated: today's may not be published yet
        day = today - timedelta(days=back)
        try:
            final, n = fetch["download"](gias_url(day), p)
            feats = gias_extract(p, strip.keep, strip.bbox)
            return feats, [f"{final.rsplit('/', 1)[-1]} ({round(n / 1e6, 1)} MB)"], day.isoformat()
        except Exception as e:      # noqa: BLE001
            err = e
    raise RuntimeError(f"the schools file could not be read: {str(err)[:160]}")


def _fetch_naptan(strip, workdir, fetch):
    from community_sources import NAPTAN_URL, naptan_area_codes, naptan_extract
    codes = naptan_area_codes(strip.bbox)
    p = os.path.join(workdir, "naptan.csv")
    final, n = fetch["download"](NAPTAN_URL.format(codes=",".join(codes)), p)
    with open(p, "rb") as f:
        text = f.read().decode("utf-8-sig", errors="replace")
    return naptan_extract(text, strip.keep, strip.bbox), [f"areas {', '.join(codes)} ({round(n / 1e6, 1)} MB)"], None


def default_fetchers():
    import community_sources as cs
    return {"download": cs.download, "osm_extract": cs.osm_extract, "osm_structures_extract": cs.osm_structures_extract}


def refresh(by=None, fetchers=None, strip=None, today=None, sources=SOURCE_ORDER, all_options=None):
    """Fetch every source along the tenant's strip and store what each gave. Synchronous; start_refresh()
    runs it on a thread. Returns status()."""
    fetch = dict(default_fetchers(), **(fetchers or {}))
    # 16 Nov 2026: the strip is every stored option (all_options, default ALL_OPTIONS); each source that succeeds records
    # the options_stamp it was fetched along (None for a narrow strip or a strip handed in), which status() compares
    today = today or date.today()
    started = _now()
    old = _detail(_meta_row())
    det = {"route_m": STRIP_ROUTE_M, "site_m": STRIP_SITE_M, "sources": dict(old.get("sources") or {}), "notes": []}
    _write_meta("running", det, by=by, started_at=started)
    all_options = ALL_OPTIONS if all_options is None else bool(all_options)
    stamp, rows = None, None
    if strip is None:
        # the options are read BEFORE the lines: a re-route while the fetch runs is left out of the record, never in it
        if all_options:
            rows = option_rows()
            stamp = options_stamp(rows)
        strip = strip_from_db(all_options=all_options)
    det["all_options_asked"] = all_options
    # the option lists the sources were fetched along, kept only while a source still points at one
    sets = dict(old.get("option_sets") or {})
    if stamp:
        sets[stamp] = rows
    det["option_sets"] = sets
    if not strip.bbox:
        det["error"] = "nothing to fetch along: no route is worked out and no site has a position yet"
        _write_meta("failed", det)
        return status()
    if not strip.lines:
        det["notes"].append("No route is routed yet, so only the sites were searched round.")
    def beat():
        det["beat"] = _now()
        _write_meta("running", det)
    workdir = tempfile.mkdtemp(prefix="wayscope_community_")
    ok_any = False
    try:
        for s in sources:
            entry = dict(det["sources"].get(s) or {})
            try:
                if s == "osm":
                    feats, files, data_date = _fetch_osm(strip, workdir, fetch, beat)
                elif s == "osm_structures":
                    feats, files, data_date = _fetch_osm_structures(strip, workdir, fetch, beat)
                elif s == "gias":
                    feats, files, data_date = _fetch_gias(strip, workdir, fetch, today)
                else:
                    feats, files, data_date = _fetch_naptan(strip, workdir, fetch)
                now = _now()
                n = replace_source(s, feats, now)
                entry.update({"fetched_at": now, "data_date": data_date or now[:10], "files": files, "count": n,
                              "error": None, "options_stamp": stamp, "lines": len(strip.lines)})
                ok_any = True
            except Exception as e:      # noqa: BLE001 — one source failing never loses another's rows
                entry["error"] = str(e)[:240]
            det["sources"][s] = entry
            _write_meta("running", det)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    used = {(e or {}).get("options_stamp") for e in det["sources"].values()}
    det["option_sets"] = {k: v for k, v in det["option_sets"].items() if k in used}
    failed = [SOURCES[s]["name"] for s in sources if (det["sources"].get(s) or {}).get("error")]
    if failed:
        det["error"] = ("could not fetch " + ", ".join(failed) + "; what it had before is kept") if ok_any else \
            "no source could be fetched; nothing was changed"
    _write_meta("done" if ok_any else "failed", det, fetched_at=_now() if ok_any else None)
    return status()


def start_refresh(by=None, sync=False, **kw):
    """Start a refresh on a thread (or run it now with sync=True). Refuses while one is running."""
    import fetch_guard
    tenant = db.current_tenant()
    # 29 Oct 2026: one big fetch at a time — the collision history's and this one together took live over its memory
    with fetch_guard.LOCK, _LOCK:
        st = status()
        if st["state"] == "running":
            return dict(st, started=False, message="a refresh is already running")
        busy = fetch_guard.other_running("community")
        if busy:
            return dict(st, started=False, message=busy)
        _write_meta("running", dict(_detail(_meta_row()), error=None), by=by, started_at=_now())

    def run():
        tok = db.set_current_tenant(tenant)
        try:
            refresh(by=by, **kw)
        except Exception as e:      # noqa: BLE001
            det = _detail(_meta_row())
            det["error"] = f"the refresh stopped: {str(e)[:200]}"
            _write_meta("failed", det)
        finally:
            try:
                db.reset_current_tenant(tok)
            except Exception:
                pass

    if sync:
        run()
    else:
        threading.Thread(target=run, name="community-refresh", daemon=True).start()
    return dict(status(), started=True)


# --------------------------------------------------------------------------- #
#  The CLP plans                                                               #
# --------------------------------------------------------------------------- #
def structures(bbox=None, kinds=None):
    """22 Oct 2026 (abnormal loads, phase 3): the stored structures and limits (source osm_structures), optionally
    those touching a bbox — as plain dicts {kind, name, detail, geometry, dist_m, source_ref}, never GeoJSON for a
    map: nothing of this is drawn on its own."""
    tenant = db.current_tenant()
    want = set(kinds or ("s_bridge", "s_rail", "s_level_crossing", "s_calming", "s_power", "s_limit"))
    out = []
    for r in db.query("SELECT kind, source_ref, name, detail, geometry_json, dist_m FROM community_features "
                      "WHERE tenant_id = ? AND source = ? ORDER BY kind, feature_id", (tenant, "osm_structures")):
        if r["kind"] not in want:
            continue
        try:
            g = json.loads(r["geometry_json"])
        except Exception:
            continue
        if bbox and not _geom_touches(g, bbox):
            continue
        out.append({"kind": r["kind"], "name": r["name"], "detail": r["detail"], "geometry": g, "dist_m": r["dist_m"],
                    "source_ref": r["source_ref"]})
    return out


def structures_fetched_at():
    """When the structures were last fetched (ISO) or None — the words on a load's candidates say so."""
    d = (_detail(_meta_row()).get("sources") or {}).get("osm_structures") or {}
    return d.get("fetched_at")


def in_view(bbox):
    """For a plan: the stored features touching the plan's frame, and the kinds among them (legend order)."""
    feats = features(bbox=bbox)
    kinds = [k for k in KIND_KEYS if any(f["properties"]["kind"] == k for f in feats)]
    return feats, kinds
