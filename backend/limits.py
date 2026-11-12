"""
Lorry limits on the road network — weight, height, width and axle weight (13 Oct 2026).

WHAT THIS IS
------------
The map and the Look-ahead had closures (National Highways) but no standing limits for a
GB tenant: no "7.5 t" on a village lane, no "4.4 m" under a railway bridge. This module
imports those limits from two sources the user chose on 13 Oct (D25 reopened by the user:
"just OpenStreetMap and HERE, not typed"):

    osm   OpenStreetMap, through the public Overpass API. Ways and nodes tagged maxweight,
          maxweightrating(:hgv), maxaxleload, maxheight(:physical), maxwidth(:physical).
          Licence: ODbL. Shown with "© OpenStreetMap contributors". Coverage is whatever
          volunteers have mapped — measured 13 Oct around Market Harborough: 5 limits in a
          9 × 9 km box (two 5 t "except for access" on Back Lane, 4 m on Rockingham Road and
          Kettering Road, 2 m on a service road). Patchy, and the map says so.
    here  HERE, through the Map Attributes API v8 (the truck-restriction layers), on the
          HERE key the deployment already holds. ⚠️ NEVER CALLED FROM A SESSION: the layer
          names, field names, units and the geometry encoding below come from HERE's
          published documentation as remembered, not from a response. The importer runs
          only after `/api/admin/diagnostics/limits?source=here&probe=true` has been read;
          every value goes through the same sanity ranges as OSM, so a wrong unit shows as
          "all dropped", never as a wrong limit on the map. Whether HERE's terms allow its
          data to be drawn over a Mapbox basemap has NOT been checked (todo, before a real
          tenant).

ONE GLOBAL TABLE, NOT TENANTED (by design, like fuel_index)
------------------------------------------------------------
A limit is a fact about a public road, not a tenant's data, and two tenants in one county
share it. `road_limits` is keyed by (source, ext_id). It is NOT in the tenant package: a
package carries a customer's work, and carrying third-party map data in it would mean
redistributing an OSM extract (ODbL share-alike) or HERE content inside a customer file.
An import replaces the rows of that source whose anchor point lies in the tenant's extent.

THE CHECK AGAINST ROUTES — AND THE BRIDGE TRAP
----------------------------------------------
A height limit is tagged on the road UNDER a bridge. A route that crosses OVER that bridge
passes within 0 m of the restricted way in plan, and a naive "within 30 m" test would say
a 4.0 m artic hits a 3.2 m headroom it never goes under. So a LINE limit counts only when
the route runs ALONG it: the length of the limit's own segments lying within MATCH_M of the
route must reach min(ALONG_MIN_M, ALONG_SHARE × the limit's length). A crossing shares a
few metres; travelling it shares the stretch.
THE SIDE-ROAD MOUTH (10 Nov 2026): the map data often puts a weight limit on a short stub at a
side road's mouth (7–52 m). All of it lies within MATCH_M of the main road, so the share rule
counted it on every route that only PASSES the junction (16 of the 30 limits live flagged). So
a piece counts as "along" only where it runs within ALONG_ANGLE_DEG of the route's own
direction there, OR the route carries on CARRY_ON_M past the limit's far end in the limit's own
direction (a route that turns into the side road and uses it). Both read the same index.
A POINT limit (a node: a barrier, a bridge
point) cannot be told apart from a crossing by geometry alone, so it is reported as a
"point" hit with the verdict and a note to check, never silently.

Verdicts reuse restrictions.assess()'s idea: two numbers in one unit give "exceeds" or
"within"; anything else is "unknown" with the reason. Weight is compared at the leg's own
weight — gross on the loaded leg, gross minus payload on the return — the same weights
HERE routed each leg at. Axle weight has no vehicle figure in factors.json, so it is always
"unknown" (nothing is divided out to invent one).

"Except for access" (OSM hgv=destination and friends) keeps the verdict and adds the note:
a lorry may use the road to reach premises on it, and whether this site is one is a human
question.

NOT VERIFIED
------------
Overpass and HERE are never called by the test harnesses (stubbed). HERE has never been
called at all. The 13 Oct Overpass query above is the only live read.
"""
import contextlib
import contextvars
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import db

# --------------------------------------------------------------------------- #
#  Sources and kinds                                                           #
# --------------------------------------------------------------------------- #
SOURCES = {
    "osm": {
        "key": "osm", "short": "OpenStreetMap",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "licence": "ODbL 1.0",
        "note": "Mapped by volunteers: coverage is incomplete. Check the signed limit on site.",
    },
    "here": {
        "key": "here", "short": "HERE",
        "attribution": "© HERE",
        "licence": "HERE terms (not yet reviewed for display over a Mapbox map)",
        "note": "From HERE's map data. Check the signed limit on site.",
    },
}

#: kind -> label, unit, the vehicle_dimensions() key it is compared with, sanity range
KINDS = {
    "weight": {"label": "Weight limit", "unit": "t", "dimension": "mass_t", "range": (1.0, 60.0)},
    "height": {"label": "Height limit", "unit": "m", "dimension": "height_m", "range": (1.5, 7.0)},
    "width":  {"label": "Width limit", "unit": "m", "dimension": "width_m", "range": (1.5, 4.0)},
    "axle":   {"label": "Axle weight limit", "unit": "t", "dimension": None, "range": (1.0, 15.0)},
}

#: Matching (judgement, not measured — same status as restrictions.MATCH_M)
MATCH_M = 20.0          # a limit's vertex within this of the route counts as "on it"
ALONG_MIN_M = 30.0      # a line limit counts when this much of it runs along the route…
ALONG_SHARE = 0.6       # …or this share of a shorter one does
POINT_M = 12.0          # a node limit within this of the route is a "point" hit
ALONG_ANGLE_DEG = 20.0  # 10 Nov 2026: a piece runs "along" only within this of the route's direction…
CARRY_ON_M = 40.0       # …unless the route carries on this far past the limit's far end (it uses the road)
# Set against the 30 weight limits live flagged on 10 Nov 2026 (real lines, measured read only): this pair keeps the 14
# roads the routes run along and drops the 16 side-road mouths; 30° let an unnamed 41 m mouth (29°) back in.

TIMEOUT_S = 90

# --------------------------------------------------------------------------- #
#  The table                                                                   #
# --------------------------------------------------------------------------- #
DDL = """
    CREATE TABLE IF NOT EXISTS road_limits (
        source        TEXT NOT NULL,
        ext_id        TEXT NOT NULL,
        kind          TEXT NOT NULL,
        value         REAL NOT NULL,
        unit          TEXT NOT NULL,
        signed        TEXT,
        geom_type     TEXT NOT NULL,
        geometry_json TEXT NOT NULL,
        anchor_lon    REAL NOT NULL,
        anchor_lat    REAL NOT NULL,
        length_m      REAL,
        name          TEXT,
        ref           TEXT,
        exceptions    TEXT,
        tags_json     TEXT,
        fetched_at    TEXT NOT NULL,
        PRIMARY KEY (source, ext_id, kind)
    )
"""


def init_db():
    """GLOBAL table (untenanted, by design — see the module docstring). Idempotent."""
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(DDL)
        cur.execute("CREATE INDEX IF NOT EXISTS ix_road_limits_anchor ON road_limits (anchor_lon, anchor_lat)")
        conn.commit()
        db.bump_data_version()   # 22 Oct 2026: its own connection, so db.note_write never saw it (read_cache)
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
#  Parsing values                                                              #
# --------------------------------------------------------------------------- #
_NON_VALUES = {"", "none", "default", "below_default", "no_sign", "no_indications",
               "unsigned", "unknown", "physical", "no", "yes"}


def parse_weight(raw):
    """OSM maxweight → tonnes, or None. '7.5', '7.5 t', '18t', '7500 kg'. Anything with
    another unit (st, lbs, cwt) is None — counted as unparsed, never guessed."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(",", ".")
    if s in _NON_VALUES:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(t|tonnes?|kg)?", s)
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2) == "kg":
        v /= 1000.0
    return round(v, 2)


def parse_length(raw):
    """OSM maxheight / maxwidth → metres, or None. '4.4', '4.4 m', "14'6\"", "14'6",
    "14'", '14 ft 6 in'. 'default', 'below_default' and the like are None."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(",", ".").replace("’", "'").replace("″", '"').replace("′", "'")
    if s in _NON_VALUES:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m)?", s)
    if m:
        return round(float(m.group(1)), 2)
    m = re.fullmatch(r"(\d+)\s*(?:'|ft)\s*(?:(\d+(?:\.\d+)?)\s*(?:\"|in|'')?)?", s)
    if m:
        ft = int(m.group(1))
        inch = float(m.group(2) or 0)
        return round(ft * 0.3048 + inch * 0.0254, 2)
    return None


def is_imperial(raw):
    s = str(raw or "")
    return ("'" in s) or ("ft" in s.lower()) or ("’" in s)


def in_range(kind, value):
    lo, hi = KINDS[kind]["range"]
    return value is not None and lo <= value <= hi


def fmt_value(kind, value):
    """'7.5 t', '4.4 m', '4.0 m' (heights and widths keep one decimal, as the sign does)."""
    if kind in ("height", "width"):
        return f"{float(value):.1f} m"
    return f"{value:g} {KINDS[kind]['unit']}"


def icon_text(kind, value):
    """The legend on the sign: '7.5T' for weight, '4.4m' / '4.0m' for height and width."""
    if kind in ("weight", "axle"):
        return f"{value:g}T"
    return f"{float(value):.1f}m"


def signed_metric(raw):
    """The metric figure a UK dual sign shows beside an imperial one, or None.

    13 Oct 2026, checked on Street View: Melton Road, East Langton is signed **4.0 m and 13'0"**.
    OSM carries only `maxheight=13'0"`; converted exactly that is 3.96 m, and a 4.0 m artic read
    as OVER a limit it is exactly at. The metric on the sign is the imperial figure to the nearest
    0.1 m (13'0" = 3.96 -> 4.0; 14'6" = 4.42 -> 4.4), so an imperial-only value is read as that.
    One sign seen, not a published table: if a sign is ever found that disagrees, the signed
    metric wins and this rule is wrong for it."""
    if not is_imperial(raw):
        return None
    m = parse_length(raw)
    return round(m, 1) if m is not None else None


def imperial_text(value_m):
    """4.42 m → 14'6" (the way UK height and width signs carry it)."""
    inches = round(value_m / 0.0254)
    return f"{inches // 12}'{inches % 12}\""


# --------------------------------------------------------------------------- #
#  Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def _hav_m(a, b):
    """Haversine metres between two [lon, lat] points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(min(1.0, math.sqrt(h)))


def _line_len_m(coords):
    return sum(_hav_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def _pt_seg_m(p, a, b):
    """Point to segment in metres, on a local equirectangular plane (fine at road scale)."""
    lat0 = math.radians(p[1])
    kx = 111320.0 * math.cos(lat0)
    ky = 110540.0
    ax, ay = (a[0] - p[0]) * kx, (a[1] - p[1]) * ky
    bx, by = (b[0] - p[0]) * kx, (b[1] - p[1]) * ky
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx, cy)


def _pt_line_m(p, line, bbox=None):
    best = None
    for i in range(len(line) - 1):
        d = _pt_seg_m(p, line[i], line[i + 1])
        if best is None or d < best:
            best = d
    return best if best is not None else float("inf")


def _bbox(coords):
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _bbox_near(a, b, pad_deg):
    return not (a[0] - pad_deg > b[2] or a[2] + pad_deg < b[0]
                or a[1] - pad_deg > b[3] or a[3] + pad_deg < b[1])


def along_m(limit_coords, route_line):
    """Metres of the limit's own segments whose BOTH ends lie within MATCH_M of the route —
    how far the route travels along it. A crossing scores ~0 (the bridge trap)."""
    return _along(limit_coords, lambda c: _pt_line_m(c, route_line) <= MATCH_M)


class _LineIndex:
    """
    A route line's segments filed in a grid, so "is this point within X m of the route" looks at
    the few segments near the point instead of all of them (17 Oct 2026, Route all 502s).

    Measured locally (HERE stubbed with real HERE lines from the live backup, 1,631 stored limits,
    the demo's 22 routes): the brute check, every limit vertex against every route segment, took
    ~9 s a leg and was 99 % of a Route all batch, so a 30-leg batch ran ~4.6 min here and longer
    on Render. The answer is the SAME: a segment is filed in every cell its box padded by `reach`
    touches (padded a little more than needed), so every segment that could be within `reach` of
    a point is among that point's candidates, and each candidate is measured with the same
    _pt_seg_m the brute check uses. test_limits asserts the hits are identical.
    """
    CELL_DEG = 0.005        # ~550 m north-south, ~330 m east-west at 53°N

    def __init__(self, line, reach_m):
        self.line = line
        self.reach_m = reach_m
        self.grid = {}
        c = self.CELL_DEG
        pad_lat = reach_m / 110540.0 * 1.05
        for i in range(len(line) - 1):
            a, b = line[i], line[i + 1]
            w, e = min(a[0], b[0]), max(a[0], b[0])
            s_, n = min(a[1], b[1]), max(a[1], b[1])
            # _pt_seg_m scales longitude at the POINT's latitude; the smallest cosine a point
            # within reach could have bounds the pad from above
            lat_far = min(89.0, max(abs(s_), abs(n)) + pad_lat)
            pad_lon = reach_m / (111320.0 * math.cos(math.radians(lat_far))) * 1.05
            for gx in range(math.floor((w - pad_lon) / c), math.floor((e + pad_lon) / c) + 1):
                for gy in range(math.floor((s_ - pad_lat) / c), math.floor((n + pad_lat) / c) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)

    def candidates(self, p):
        c = self.CELL_DEG
        return self.grid.get((math.floor(p[0] / c), math.floor(p[1] / c)), ())

    def near(self, p, within_m):
        """True when some segment of the line is within `within_m` (<= reach) of p."""
        return self.first_within(p, within_m) is not None

    def first_within(self, p, within_m):
        """The distance to the FIRST segment found within `within_m` (<= reach) of p, or None: near()'s answer with
        its distance, at the same cost (10 Nov 2026: runs_along reads it to tell a limit's far end)."""
        line = self.line
        for i in self.candidates(p):
            d = _pt_seg_m(p, line[i], line[i + 1])
            if d <= within_m:
                return d
        return None


def _bearing(a, b):
    """The direction a -> b in radians on the local plane (_pt_seg_m's scaling)."""
    kx = 111320.0 * math.cos(math.radians((a[1] + b[1]) / 2.0))
    return math.atan2((b[1] - a[1]) * 110540.0, (b[0] - a[0]) * kx)


def _angle_deg(t1, t2):
    """The angle between two undirected lines, 0–90 degrees."""
    d = abs(math.degrees(t1 - t2)) % 180.0
    return 180.0 - d if d > 90.0 else d


def _past(a, b, metres):
    """The point `metres` beyond b on the line a -> b (local plane)."""
    kx = 111320.0 * math.cos(math.radians(b[1]))
    dx, dy = (b[0] - a[0]) * kx, (b[1] - a[1]) * 110540.0
    n = math.hypot(dx, dy)
    if n == 0:
        return None
    return [b[0] + dx / n * metres / kx, b[1] + dy / n * metres / 110540.0]


def runs_along(coords, idx, length_m=None):
    """
    The one matching rule for a LINE limit (check_route and _matches): metres the route runs along it, or None when
    it does not count. The old rule first (min(ALONG_MIN_M, ALONG_SHARE × length) of the limit's pieces with both ends
    within MATCH_M); then (10 Nov 2026, the side-road mouth) enough of those pieces must run within ALONG_ANGLE_DEG
    of the route's direction, or the route must carry on CARRY_ON_M past the limit's far end. Only ever drops a hit.
    """
    if not coords or len(coords) < 2:
        return None
    need = min(ALONG_MIN_M, ALONG_SHARE * (length_m or _line_len_m(coords)))
    dist = [idx.first_within(c, MATCH_M) for c in coords]          # the old rule's own look-ups, distances kept
    near = [d is not None for d in dist]
    pieces = [(coords[i], coords[i + 1]) for i in range(len(coords) - 1) if near[i] and near[i + 1]]
    along = sum(_hav_m(a, b) for a, b in pieces)
    if along <= 0 or along < need:
        return None
    # the direction, piece by piece: a piece runs along when a stretch of the route within MATCH_M of its middle runs the
    # same way (within ALONG_ANGLE_DEG). The angle is read before any distance is measured, so only the route's stretches
    # that run the piece's way are measured, and the loop stops once enough does (Route all's measuring budget)
    line, par = idx.line, 0.0
    for a, b in pieces:
        s = _hav_m(a, b)
        if s <= 0:
            continue
        mid, tb = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0], _bearing(a, b)
        py = MATCH_M / 110540.0
        px = MATCH_M / (111320.0 * max(0.01, math.cos(math.radians(mid[1]))))
        if any(min(line[i][0], line[i + 1][0]) - px <= mid[0] <= max(line[i][0], line[i + 1][0]) + px
               and min(line[i][1], line[i + 1][1]) - py <= mid[1] <= max(line[i][1], line[i + 1][1]) + py
               and _angle_deg(tb, _bearing(line[i], line[i + 1])) <= ALONG_ANGLE_DEG
               and _pt_seg_m(mid, line[i], line[i + 1]) <= MATCH_M for i in idx.candidates(mid)):
            par += s
            if par >= need:
                return along
    # else the route carries on CARRY_ON_M past the limit's far end, in the limit's own direction: it uses the road (it
    # bends with it, or turned into the side road). The far end is the one further from the route, read from the look-ups
    # above (an end off the route is the far one); nothing more is measured
    first, last = coords[0], coords[-1]
    d0 = dist[0] if dist[0] is not None else float("inf")
    d1 = dist[-1] if dist[-1] is not None else float("inf")
    q, e = (first, last) if d1 >= d0 else (last, first)
    p = _past(q, e, CARRY_ON_M)
    return along if p is not None and idx.near(p, MATCH_M) else None


def _along(limit_coords, is_near):
    near = [is_near(c) for c in limit_coords]
    total = 0.0
    for i in range(len(limit_coords) - 1):
        if near[i] and near[i + 1]:
            total += _hav_m(limit_coords[i], limit_coords[i + 1])
    return total


def anchor_of(geom_type, coords):
    """Where the sign is drawn: the point itself, or the vertex nearest half-way along."""
    if geom_type == "Point":
        return coords
    if len(coords) == 1:
        return coords[0]
    half = _line_len_m(coords) / 2.0
    run = 0.0
    for i in range(len(coords) - 1):
        seg = _hav_m(coords[i], coords[i + 1])
        if run + seg >= half and seg > 0:
            f = (half - run) / seg
            return [coords[i][0] + f * (coords[i + 1][0] - coords[i][0]),
                    coords[i][1] + f * (coords[i + 1][1] - coords[i][1])]
        run += seg
    return coords[-1]


# --------------------------------------------------------------------------- #
#  The tenant's extent                                                         #
# --------------------------------------------------------------------------- #
EXTENT_PAD_DEG = 0.02        # ~2 km round the sites and baked routes


def tenant_extent():
    """(w, s, e, n) round the tenant's locations and its baked route geometry, or None."""
    tenant = db.current_tenant()
    pts = []
    for r in db.query("SELECT lat, lon FROM locations WHERE tenant_id = ?", (tenant,)):
        if r.get("lat") is not None and r.get("lon") is not None:
            pts.append((float(r["lon"]), float(r["lat"])))
    for r in db.query("SELECT geometry FROM route_geometry WHERE tenant_id = ? AND geometry IS NOT NULL", (tenant,)):
        try:
            line = json.loads(r["geometry"])
        except Exception:
            continue
        b = _bbox(line) if line else None
        if b:
            pts += [(b[0], b[1]), (b[2], b[3])]
    if not pts:
        return None
    w = min(p[0] for p in pts) - EXTENT_PAD_DEG
    s = min(p[1] for p in pts) - EXTENT_PAD_DEG
    e = max(p[0] for p in pts) + EXTENT_PAD_DEG
    n = max(p[1] for p in pts) + EXTENT_PAD_DEG
    return (round(w, 5), round(s, 5), round(e, 5), round(n, 5))


def tiles(box, size_deg):
    """Split (w, s, e, n) into tiles no bigger than size_deg on a side."""
    w, s, e, n = box
    out = []
    y = s
    while y < n:
        x = w
        y2 = min(n, y + size_deg)
        while x < e:
            x2 = min(e, x + size_deg)
            out.append((round(x, 5), round(y, 5), round(x2, 5), round(y2, 5)))
            x = x2
        y = y2
    return out


# --------------------------------------------------------------------------- #
#  OpenStreetMap (Overpass)                                                    #
# --------------------------------------------------------------------------- #
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
OSM_TILE_DEG = 0.15          # 13 Oct: 0.25 drew 504s on a busy day; lighter queries
OSM_RETRY_ROUNDS = 2         # failed tiles are asked again this many times…
OSM_RETRY_WAIT_S = 20        # …after this pause
#: roads a lorry could be routed on; service roads, tracks and paths are left out (a 2 m
#: car-park barrier is not a lorry limit worth drawing)
OSM_HIGHWAYS = ("motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|"
                "secondary_link|tertiary|tertiary_link|unclassified|residential|living_street|road")
#: tag → kind, in order of preference (the first present wins for each kind)
OSM_TAGS = {
    "weight": ("maxweight", "maxweightrating:hgv", "maxweightrating", "maxweight:hgv"),
    "height": ("maxheight", "maxheight:physical"),
    "width":  ("maxwidth", "maxwidth:physical"),
    "axle":   ("maxaxleload",),
}
_ACCESS_ONLY = ("destination", "delivery", "customers", "private")


def overpass_query(box):
    w, s, e, n = box
    bb = f"({s},{w},{n},{e})"
    hw = f'["highway"~"^({OSM_HIGHWAYS})$"]'
    parts = []
    for tags in OSM_TAGS.values():
        for tag in tags:
            parts.append(f'way{hw}["{tag}"]{bb};')
            parts.append(f'node["{tag}"]{bb};')
    return f"[out:json][timeout:{TIMEOUT_S}];(" + "".join(parts) + ");out tags geom;"


def _overpass(query):
    """POST one query, trying each public server in turn. Returns (json, server, errors)."""
    errors = []
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "Wayscope/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S + 30) as resp:
                raw = resp.read().decode("utf-8", "replace")
            if not raw.lstrip().startswith("{"):
                errors.append(f"{url}: busy or error page")
                continue
            return json.loads(raw), url, errors
        except Exception as e:
            errors.append(f"{url}: {str(e)[:120]}")
    return None, None, errors


def _exceptions(tags):
    """'Except for access' when the tags say lorries may still use it to reach premises."""
    for k in ("hgv", "goods", "motor_vehicle", "access"):
        if str(tags.get(k) or "").lower() in _ACCESS_ONLY:
            return "Except for access"
    for k, v in tags.items():
        if k.endswith(":conditional") and k.startswith("max") and re.search(r"destination|delivery", str(v), re.I):
            return "Except for access"
    return None


def parse_osm(elements, fetched_at=None):
    """Overpass elements → road_limits rows. Returns (rows, dropped) where dropped counts
    values that could not be read or fell outside the sanity range, by kind."""
    rows, dropped = [], {}
    fetched_at = fetched_at or _now()
    for el in elements or []:
        tags = el.get("tags") or {}
        if el.get("type") == "node":
            if el.get("lat") is None or el.get("lon") is None:
                continue
            geom_type, coords = "Point", [round(float(el["lon"]), 6), round(float(el["lat"]), 6)]
        elif el.get("type") == "way":
            g = el.get("geometry") or []
            coords = [[round(float(p["lon"]), 6), round(float(p["lat"]), 6)] for p in g
                      if p.get("lat") is not None and p.get("lon") is not None]
            if len(coords) < 2:
                continue
            geom_type = "LineString"
        else:
            continue
        for kind, keys in OSM_TAGS.items():
            raw = next((tags[k] for k in keys if k in tags), None)
            if raw is None:
                continue
            val = parse_weight(raw) if kind in ("weight", "axle") else (signed_metric(raw) or parse_length(raw))
            if not in_range(kind, val):
                dropped[kind] = dropped.get(kind, 0) + 1
                continue
            signed = str(raw).strip() if (kind in ("height", "width") and is_imperial(raw)) else None
            rows.append({
                "source": "osm", "ext_id": f"{el['type'][0]}{el['id']}", "kind": kind,
                "value": val, "unit": KINDS[kind]["unit"], "signed": signed,
                "geom_type": geom_type, "geometry": coords,
                "anchor": anchor_of(geom_type, coords),
                "length_m": round(_line_len_m(coords), 1) if geom_type == "LineString" else None,
                "name": tags.get("name") or (tags.get("bridge:name") if tags.get("bridge") else None),
                "ref": tags.get("ref"),
                "exceptions": _exceptions(tags),
                "tags": {k: v for k, v in tags.items()
                         if k.startswith(("max", "hgv", "goods", "bridge", "highway", "name", "ref", "access"))},
                "fetched_at": fetched_at,
            })
    return rows, dropped


# --------------------------------------------------------------------------- #
#  HERE (Map Attributes API v8) — UNVERIFIED, probe first                      #
# --------------------------------------------------------------------------- #
HERE_ATTR_URL = "https://smap.hereapi.com/v8/maps/attributes"
#: functional class → tile level (HERE's documented PDE scheme; unverified from here)
HERE_FC_LEVEL = {1: 9, 2: 10, 3: 11, 4: 12, 5: 13}
#: published field name → (kind, the unit HERE is documented to use, factor to t / m)
HERE_FIELDS = {
    "WEIGHT_RESTRICTION": ("weight", "kg", 0.001),
    "HEIGHT_RESTRICTION": ("height", "cm", 0.01),
    "WIDTH_RESTRICTION": ("width", "cm", 0.01),
    "WEIGHT_PER_AXLE": ("axle", "kg", 0.001),
}
HERE_MAX_TILES_PER_CALL = 32


def here_key():
    import os
    return os.environ.get("HERE_API_KEY") or ""


def here_tile_id(lon, lat, level):
    """HERE's tiling: tile size 180 / 2^level degrees, id = row * 2 * 2^level + col."""
    size = 180.0 / (2 ** level)
    col = int((lon + 180.0) // size)
    row = int((lat + 90.0) // size)
    return row * 2 * (2 ** level) + col


def here_tiles_for(box, level):
    w, s, e, n = box
    size = 180.0 / (2 ** level)
    ids = set()
    lat = s
    while lat <= n + size:
        lon = w
        while lon <= e + size:
            ids.add(here_tile_id(min(lon, e), min(lat, n), level))
            lon += size
        lat += size
    return sorted(ids)


def _here_get(layers, tile_ids):
    q = urllib.parse.urlencode({"layers": ",".join(layers),
                                "in": "tile:" + ",".join(str(t) for t in tile_ids),
                                "apiKey": here_key()})
    req = urllib.request.Request(f"{HERE_ATTR_URL}?{q}", headers={"User-Agent": "Wayscope/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def _here_coords(lat_s, lon_s):
    """HERE PDE geometry strings: comma-separated, the first value absolute in 10^-5 degrees
    and each next one a delta from the previous (documented convention; unverified). An
    empty delta means 'same as previous'."""
    def run(s):
        out, cur = [], None
        for part in str(s or "").split(","):
            part = part.strip()
            if part == "":
                d = 0
            else:
                try:
                    d = int(part)
                except ValueError:
                    return None
            cur = d if cur is None else cur + d
            out.append(cur / 100000.0)
        return out
    la, lo = run(lat_s), run(lon_s)
    if not la or not lo or len(la) != len(lo):
        return None
    return [[round(x, 6), round(y, 6)] for x, y in zip(lo, la)]


def _ci(row, name):
    """Case-insensitive field read."""
    for k, v in (row or {}).items():
        if str(k).upper() == name:
            return v
    return None


def parse_here(tiles_payload, fetched_at=None):
    """Map Attributes responses (TRUCK_RESTR_FCn + ROAD_GEOM_FCn) → road_limits rows.
    Returns (rows, dropped, unmatched) — unmatched = restriction rows with no link geometry."""
    fetched_at = fetched_at or _now()
    geom, restr = {}, []
    for payload in tiles_payload or []:
        for t in (payload or {}).get("Tiles", payload.get("tiles", [])) or []:
            for row in t.get("Rows", t.get("rows", [])) or []:
                link = _ci(row, "LINK_ID")
                if link is None:
                    continue
                if _ci(row, "LAT") is not None and _ci(row, "LON") is not None:
                    c = _here_coords(_ci(row, "LAT"), _ci(row, "LON"))
                    if c and len(c) >= 2:
                        geom[str(link)] = (c, _ci(row, "NAME") or _ci(row, "BASE_NAME"))
                if any(_ci(row, f) not in (None, "") for f in HERE_FIELDS):
                    restr.append(row)
    rows, dropped, unmatched = [], {}, 0
    for row in restr:
        link = str(_ci(row, "LINK_ID"))
        g = geom.get(link)
        if not g:
            unmatched += 1
            continue
        coords, name = g
        for field, (kind, _unit, factor) in HERE_FIELDS.items():
            raw = _ci(row, field)
            if raw in (None, ""):
                continue
            try:
                val = round(float(raw) * factor, 2)
            except (TypeError, ValueError):
                val = None
            if not in_range(kind, val):
                dropped[kind] = dropped.get(kind, 0) + 1
                continue
            rows.append({
                "source": "here", "ext_id": f"{link}:{field}", "kind": kind,
                "value": val, "unit": KINDS[kind]["unit"], "signed": None,
                "geom_type": "LineString", "geometry": coords,
                "anchor": anchor_of("LineString", coords),
                "length_m": round(_line_len_m(coords), 1),
                "name": name, "ref": None, "exceptions": None,
                "tags": {k: v for k, v in row.items() if str(k).upper() not in ("LAT", "LON")},
                "fetched_at": fetched_at,
            })
    return rows, dropped, unmatched


# --------------------------------------------------------------------------- #
#  Storing                                                                     #
# --------------------------------------------------------------------------- #
def replace_rows(source, box, rows):
    """Replace this source's rows whose anchor lies in `box` with `rows`, in one transaction."""
    w, s, e, n = box
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(db._adapt("DELETE FROM road_limits WHERE source = ? AND anchor_lon BETWEEN ? AND ? "
                              "AND anchor_lat BETWEEN ? AND ?"), (source, w, e, s, n))
        seen = set()
        for r in rows:
            k = (r["source"], r["ext_id"], r["kind"])
            if k in seen:
                continue
            seen.add(k)
            cur.execute(db._adapt(
                "INSERT INTO road_limits (source, ext_id, kind, value, unit, signed, geom_type, geometry_json, "
                "anchor_lon, anchor_lat, length_m, name, ref, exceptions, tags_json, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
                (r["source"], r["ext_id"], r["kind"], r["value"], r["unit"], r.get("signed"),
                 r["geom_type"], json.dumps(r["geometry"]), r["anchor"][0], r["anchor"][1],
                 r.get("length_m"), r.get("name"), r.get("ref"), r.get("exceptions"),
                 json.dumps(r.get("tags") or {}, ensure_ascii=False), r["fetched_at"]))
        conn.commit()
        db.bump_data_version()   # 22 Oct 2026: its own connection, so db.note_write never saw it (read_cache)
        return len(seen)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def stored(box=None, sources=None):
    """Rows (decoded) whose anchor lies in box (default: the tenant's extent)."""
    box = box or tenant_extent()
    if not box:
        return []
    w, s, e, n = box
    rows = db.query("SELECT * FROM road_limits WHERE anchor_lon BETWEEN ? AND ? AND anchor_lat BETWEEN ? AND ?",
                    (w, e, s, n))
    out = []
    for r in rows:
        if sources and r["source"] not in sources:
            continue
        d = dict(r)
        try:
            d["geometry"] = json.loads(d.pop("geometry_json"))
        except Exception:
            continue
        try:
            d["tags"] = json.loads(d.pop("tags_json") or "{}")
        except Exception:
            d["tags"] = {}
        # 13 Oct 2026: a row imported before signed_metric() existed holds the exact conversion
        # (13'0" -> 3.96); read it as the signed metric so a re-check fixes it without a re-import
        if d.get("kind") in ("height", "width") and d.get("signed"):
            sm = signed_metric(d["signed"])
            if sm is not None:
                d["value"] = sm
        out.append(d)
    out.sort(key=lambda d: (d["source"], d["kind"], d["ext_id"]))
    return out


# --------------------------------------------------------------------------- #
#  Imports (background, one at a time)                                         #
# --------------------------------------------------------------------------- #
_STATE = {"running": False, "source": None, "started_at": None, "finished_at": None,
          "status": None, "imported": 0, "dropped": {}, "errors": [], "tiles": 0, "tiles_failed": 0}
_LOCK = threading.Lock()


def import_state():
    with _LOCK:
        return json.loads(json.dumps(_STATE))


def _in_box(anchor, box):
    w, s, e, n = box
    return w <= anchor[0] <= e and s <= anchor[1] <= n


def import_osm(box=None):
    """Fetch every OSM limit in the tenant's extent, TILE BY TILE, and replace the stored OSM
    rows tile by tile: a tile that answered replaces the rows whose sign sits in it; a tile that
    did not answer (after OSM_RETRY_ROUNDS more rounds) keeps whatever it had — a failed tile
    must never read as 'no limits there'. Status: ok · partial (some tiles failed, named) ·
    unavailable (none answered).

    13 Oct 2026: the first live run on the demo's extent got 4 of 6 tiles (504s from every
    public server on the other two) and, all-or-nothing, stored none. Per-tile is the same
    rule — never drop a limit on a failure — at the granularity the failure actually has."""
    box = box or tenant_extent()
    if not box:
        return {"status": "no_extent", "note": "the tenant has no locations or baked routes yet", "imported": 0}
    fetched_at = _now()
    dropped, errors, n = {}, [], 0
    tl = tiles(box, OSM_TILE_DEG)
    pending = list(tl)
    for rnd in range(1 + OSM_RETRY_ROUNDS):
        if rnd and pending:
            time.sleep(OSM_RETRY_WAIT_S)
        still = []
        for t in pending:
            data, server, errs = _overpass(overpass_query(t))
            errors += errs
            if data is None:
                still.append(t)
                continue
            r, d = parse_osm(data.get("elements"), fetched_at)
            n += replace_rows("osm", t, [x for x in r if _in_box(x["anchor"], t)])
            for k, v in d.items():
                dropped[k] = dropped.get(k, 0) + v
        pending = still
        if not pending:
            break
    status = "ok" if not pending else ("unavailable" if len(pending) == len(tl) else "partial")
    out = {"status": status, "imported": n, "tiles": len(tl), "tiles_failed": len(pending),
           "failed_tiles": [list(t) for t in pending], "dropped": dropped,
           "errors": errors[-6:], "box": list(box), "fetched_at": fetched_at}
    if pending:
        out["note"] = ("the failed tiles kept their previous limits (nothing there was replaced); "
                       "run the import again when Overpass is less busy")
    return out


def import_here(box=None):
    """Fetch HERE's truck restrictions for the tenant's extent. ⚠️ Unverified: see the
    module docstring. Any failed call aborts the replace."""
    if not here_key():
        return {"status": "no_key", "imported": 0, "note": "HERE_API_KEY is not set on the server"}
    box = box or tenant_extent()
    if not box:
        return {"status": "no_extent", "imported": 0}
    fetched_at = _now()
    payloads, errors, calls = [], [], 0
    for fc, level in HERE_FC_LEVEL.items():
        ids = here_tiles_for(box, level)
        for i in range(0, len(ids), HERE_MAX_TILES_PER_CALL):
            calls += 1
            try:
                payloads.append(_here_get([f"TRUCK_RESTR_FC{fc}", f"ROAD_GEOM_FC{fc}"],
                                          ids[i:i + HERE_MAX_TILES_PER_CALL]))
            except urllib.error.HTTPError as e:
                errors.append(f"FC{fc}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:160]}")
            except Exception as e:
                errors.append(f"FC{fc}: {str(e)[:160]}")
    if errors:
        return {"status": "unavailable", "imported": 0, "calls": calls, "errors": errors[:6],
                "note": "nothing replaced; run the probe and read the raw answer"}
    rows, dropped, unmatched = parse_here(payloads, fetched_at)
    n = replace_rows("here", box, rows)
    return {"status": "ok", "imported": n, "calls": calls, "dropped": dropped,
            "unmatched_restrictions": unmatched, "box": list(box), "fetched_at": fetched_at}


def import_async(source, sync=False):
    """Start an import (osm | here) in a thread, then re-check every route."""
    if source not in SOURCES:
        return {"error": f"unknown source '{source}'", "known": sorted(SOURCES)}
    with _LOCK:
        if _STATE["running"]:
            return json.loads(json.dumps(_STATE))
        _STATE.update({"running": True, "source": source, "started_at": _now(), "finished_at": None,
                       "status": None, "imported": 0, "dropped": {}, "errors": [], "tiles": 0,
                       "tiles_failed": 0})
    tenant = db.current_tenant()

    def run():
        tok = db.set_current_tenant(tenant)
        try:
            res = import_osm() if source == "osm" else import_here()
            if res.get("status") in ("ok", "partial"):
                try:
                    store_checks()
                except Exception as e:
                    res.setdefault("errors", []).append(f"route check: {str(e)[:160]}")
            with _LOCK:
                _STATE.update({"status": res.get("status"), "imported": res.get("imported", 0),
                               "dropped": res.get("dropped") or {}, "errors": res.get("errors") or [],
                               "tiles": res.get("tiles", res.get("calls", 0)),
                               "tiles_failed": res.get("tiles_failed", 0), "note": res.get("note"),
                               "failed_tiles": res.get("failed_tiles") or []})
        except Exception as e:
            with _LOCK:
                _STATE.update({"status": "error", "errors": [str(e)[:200]]})
        finally:
            with _LOCK:
                _STATE.update({"running": False, "finished_at": _now()})
            try:
                db.reset_current_tenant(tok)
            except Exception:
                pass

    if sync:
        run()
    else:
        threading.Thread(target=run, name="limits-import", daemon=True).start()
    return import_state()


# --------------------------------------------------------------------------- #
#  Checking routes                                                             #
# --------------------------------------------------------------------------- #
def leg_dimensions(profile, leg):
    """The figures a limit is compared with on this leg: gross on the loaded leg, gross
    minus payload on the return (the weights HERE routed each leg at)."""
    try:
        import restrictions
        dims = dict(restrictions.vehicle_dimensions(profile))
    except Exception:
        dims = {}
    if leg != "loaded" and dims.get("mass_t") is not None:
        try:
            import conversions
            v = (conversions.load_factors().get("vehicles", {}) or {}).get(profile, {}) or {}
            if v.get("payload_t") is not None:
                dims["mass_t"] = round(dims["mass_t"] - float(v["payload_t"]), 1)
        except Exception:
            pass
    return dims


def vehicle_label(profile):
    """The vehicle's NAME (conversions.vehicle_label). 14 Oct 2026: read wherever a hit is SHOWN,
    from its vehicle_profile, not from the vehicle_label a check stored — a stored name goes stale
    when Config renames the vehicle (the mixers became "Concrete mixer …" on 14 Oct 2026)."""
    import conversions
    try:
        return conversions.vehicle_label(conversions.load_factors(), profile)
    except Exception:
        return conversions.vehicle_word_rule(profile)


def assess(limit, profile, leg="loaded"):
    """{verdict, vehicle, margin, note}. 'exceeds' / 'within' only when two numbers in one
    unit exist; otherwise 'unknown' with the reason."""
    kind = limit["kind"]
    dim = KINDS[kind]["dimension"]
    if not dim:
        return {"verdict": "unknown", "vehicle": None, "margin": None,
                "note": "no axle weight is held for this vehicle, so no comparison is made"}
    have = leg_dimensions(profile, leg).get(dim)
    if have is None:
        return {"verdict": "unknown", "vehicle": None, "margin": None,
                "note": f"factors.json has no {dim} for this vehicle"}
    lim = float(limit["value"])
    # 13 Oct 2026: a vehicle exactly at the signed limit is legal, and is said, not counted as a breach or hidden
    if abs(have - lim) < 0.005:
        return {"verdict": "at_limit", "vehicle": have, "margin": 0.0,
                "note": "exactly at the signed limit: legal, but check the vehicle's real height and the sign"}
    verdict = "exceeds" if have > lim else "within"
    return {"verdict": verdict, "vehicle": have, "margin": round(lim - have, 2), "note": None}


def headline(limit):
    v = fmt_value(limit["kind"], limit["value"])
    if limit["kind"] in ("height", "width"):
        v += f" ({limit.get('signed') or imperial_text(float(limit['value']))})"
    where = limit.get("name") or limit.get("ref")
    return f"{KINDS[limit['kind']]['label']} {v}" + (f" · {where}" if where else "")


def check_route(route_id, _limits=None):
    """Which stored limits each baked leg of a route runs along. Reports, never blocks."""
    tenant = db.current_tenant()
    # 28 Oct 2026 (task 0c): the options a dated zone's diversion USES are checked too, each hit carrying the
    # diversion's dates (clashes.limit counts it only in a week those dates touch)
    div = _diversions_in_use(route_id)
    geoms = [g for g in db.query("SELECT vehicle_profile, leg, alt_index, geometry FROM route_geometry WHERE tenant_id = ? "
                                 "AND route_id = ? AND geometry IS NOT NULL", (tenant, route_id))
             if int(g.get("alt_index") or 0) == 0 or (g["vehicle_profile"], g["leg"], int(g["alt_index"])) in div]
    if not any(int(g.get("alt_index") or 0) == 0 for g in geoms):
        return {"route_id": route_id, "baked": False, "hits": []}
    lims = _limits if _limits is not None else stored()
    hits, seen = [], set()
    pad = MATCH_M / 111000.0 * 2
    for g in geoms:
        try:
            line = json.loads(g["geometry"])
        except Exception:
            continue
        if not line or len(line) < 2:
            continue
        lb = _bbox(line)
        idx = None          # built on the first limit near the line (17 Oct 2026: see _LineIndex)
        for L in lims:
            coords = L["geometry"]
            if L["geom_type"] == "Point":
                if not _bbox_near((coords[0], coords[1], coords[0], coords[1]), lb, pad):
                    continue
                idx = idx or _LineIndex(line, max(MATCH_M, POINT_M))
                if not idx.near(coords, POINT_M):
                    continue
                along, point = None, True
            else:
                fb = _bbox(coords)
                if not fb or not _bbox_near(fb, lb, pad):
                    continue
                idx = idx or _LineIndex(line, max(MATCH_M, POINT_M))
                along = runs_along(coords, idx, L.get("length_m"))
                if along is None:
                    continue
                point = False
            alt = int(g.get("alt_index") or 0)
            key = (g["vehicle_profile"], g["leg"], alt, L["source"], L["ext_id"], L["kind"])
            if key in seen:
                continue
            seen.add(key)
            a = assess(L, g["vehicle_profile"], g["leg"])
            note = a["note"]
            if point:
                note = ("a point limit on or beside the route: check whether the route passes it or "
                        "crosses over or under it") + (f"; {note}" if note else "")
            if L.get("exceptions"):
                note = (f"{L['exceptions']}: a lorry may use it to reach premises on it — check whether "
                        "this site is one") + (f"; {note}" if note else "")
            hits.append({
                "vehicle_profile": g["vehicle_profile"], "vehicle_label": vehicle_label(g["vehicle_profile"]),
                "leg": g["leg"], "source": L["source"], "ext_id": L["ext_id"], "kind": L["kind"],
                "limit": L["value"], "unit": L["unit"], "signed": L.get("signed"),
                "headline": headline(L), "name": L.get("name"), "ref": L.get("ref"),
                "exceptions": L.get("exceptions"), "point": point,
                "along_m": round(along, 1) if along is not None else None,
                "verdict": a["verdict"], "vehicle_value": a["vehicle"], "margin": a["margin"], "note": note,
                "anchor": [L["anchor_lon"], L["anchor_lat"]],
            })
            if alt:
                hits[-1]["alt_index"] = alt
                hits[-1]["diversion"] = div[(g["vehicle_profile"], g["leg"], alt)]
    order = {"exceeds": 0, "at_limit": 1, "unknown": 2, "within": 3}
    # a limit the route runs ALONG outranks a point limit (which may be a crossing)
    hits.sort(key=lambda h: (order.get(h["verdict"], 3), bool(h["point"]), h["kind"], h["vehicle_profile"], h["leg"]))
    return {"route_id": route_id, "baked": True, "hits": hits,
            "exceeds": len([h for h in hits if h["verdict"] == "exceeds"])}


def _diversions_in_use(route_id):
    """{(profile, leg, alt): [{"from", "to"}, …]} — the stored options route_choice has in use on this route."""
    try:
        rows = db.query("SELECT vehicle_profile, leg, alt_index, starts_on, ends_on FROM route_choice WHERE tenant_id = ? "
                        "AND route_id = ? AND status = 'in_use' AND alt_index <> 0", (db.current_tenant(), route_id))
    except Exception:
        return {}
    out = {}
    for r in rows:
        out.setdefault((r["vehicle_profile"], r["leg"], int(r["alt_index"])), []).append(
            {"from": r.get("starts_on"), "to": r.get("ends_on")})
    return out


def _matches(line, lims):
    """
    The stored limits one polyline runs along, as (limit, point?, along_m) — the matching rule of check_route()
    (MATCH_M, ALONG_MIN_M / ALONG_SHARE for a line limit, POINT_M for a node), the geometry only, no verdict.
    22 Oct 2026 (abnormal loads): pulled out so a movement's own line can be checked at the LOAD's size.
    """
    out = []
    if not line or len(line) < 2:
        return out
    lb = _bbox(line)
    pad = MATCH_M / 111000.0 * 2
    idx = None
    for L in lims:
        coords = L["geometry"]
        if L["geom_type"] == "Point":
            if not _bbox_near((coords[0], coords[1], coords[0], coords[1]), lb, pad):
                continue
            idx = idx or _LineIndex(line, max(MATCH_M, POINT_M))
            if not idx.near(coords, POINT_M):
                continue
            out.append((L, True, None))
        else:
            fb = _bbox(coords)
            if not fb or not _bbox_near(fb, lb, pad):
                continue
            idx = idx or _LineIndex(line, max(MATCH_M, POINT_M))
            along = runs_along(coords, idx, L.get("length_m"))
            if along is None:
                continue
            out.append((L, False, along))
    return out


def assess_dims(limit, dims):
    """assess() for a set of typed figures: dims = {mass_t, height_m, width_m, axle_t} (an abnormal load's own)."""
    kind = limit["kind"]
    dim = KINDS[kind]["dimension"] or ("axle_t" if kind == "axle" else None)
    have = (dims or {}).get(dim) if dim else None
    if have is None:
        return {"verdict": "unknown", "vehicle": None, "margin": None, "note": f"no {kind} figure is typed for this load, so no comparison is made"}
    lim = float(limit["value"])
    if abs(float(have) - lim) < 0.005:
        return {"verdict": "at_limit", "vehicle": float(have), "margin": 0.0,
                "note": "exactly at the signed limit: legal, but check the load's real figure and the sign"}
    return {"verdict": "exceeds" if float(have) > lim else "within", "vehicle": float(have), "margin": round(lim - float(have), 2), "note": None}


def check_line(line, dims, leg="loaded", label="the load", _limits=None):
    """
    22 Oct 2026 (abnormal loads, D67): the stored limits one polyline runs along, each judged against the LOAD's
    typed figures (gross, height, width, heaviest axle) rather than a factors.json profile. Reports, never blocks.
    Same shape as check_route()'s hits (vehicle_profile = the label).
    """
    lims = _limits if _limits is not None else stored()
    hits = []
    for L, point, along in _matches(line, lims):
        a = assess_dims(L, dims)
        note = a["note"]
        if point:
            note = ("a point limit on or beside the route: check whether the route passes it or "
                    "crosses over or under it") + (f"; {note}" if note else "")
        if L.get("exceptions"):
            note = (f"{L['exceptions']}: a lorry may use it to reach premises on it — check whether "
                    "this site is one") + (f"; {note}" if note else "")
        hits.append({
            "vehicle_profile": label, "vehicle_label": label, "leg": leg, "source": L["source"], "ext_id": L["ext_id"],
            "kind": L["kind"], "limit": L["value"], "unit": L["unit"], "signed": L.get("signed"), "headline": headline(L),
            "name": L.get("name"), "ref": L.get("ref"), "exceptions": L.get("exceptions"), "point": point,
            "along_m": round(along, 1) if along is not None else None,
            "verdict": a["verdict"], "vehicle_value": a["vehicle"], "margin": a["margin"], "note": note,
            "anchor": [L["anchor_lon"], L["anchor_lat"]],
        })
    order = {"exceeds": 0, "at_limit": 1, "unknown": 2, "within": 3}
    hits.sort(key=lambda h: (order.get(h["verdict"], 3), bool(h["point"]), h["kind"]))
    return hits


def store_checks(route_ids=None):
    """Check every route (or the given ones) against the stored limits and store the hits on
    the route (routes.limits_hits). Synchronous."""
    tenant = db.current_tenant()
    ids = [r["id"] for r in db.query("SELECT id FROM routes WHERE tenant_id = ? ORDER BY id", (tenant,))
           if not route_ids or r["id"] in set(route_ids)]
    lims = stored()
    now = _now()
    n = 0
    for rid in ids:
        try:
            res = check_route(rid, _limits=lims)
            status = "ok" if res.get("baked") else "not_baked"
            hits = res.get("hits") or []
        except Exception as e:
            status, hits = "error: " + str(e)[:120], None
        n += len(hits or [])
        db.execute("UPDATE routes SET limits_hits = ?, limits_checked_at = ?, limits_status = ? "
                   "WHERE tenant_id = ? AND id = ?",
                   (json.dumps(hits) if hits is not None else None, now, status, tenant, rid))
    return {"status": "ok", "routes": len(ids), "hits": n, "limits": len(lims), "checked_at": now}


# 17 Oct 2026 (Route all 502s): a bake used to re-check its route after EVERY leg it stored
# (_upsert_geom -> store_checks([route_id])), and each check covers every baked leg of the route,
# so a 30-leg batch checked some legs a dozen times. Inside checks_batched() the hook only notes the
# route; the block's end checks each noted route ONCE, against one read of the stored limits.
_DEFER = contextvars.ContextVar("limits_defer", default=None)


@contextlib.contextmanager
def checks_batched():
    """Hold every check_soon() inside the block and check the noted routes once at its end (also
    when the block raises: geometry may have been stored before it did). Nested blocks defer to the
    outermost."""
    if _DEFER.get() is not None:
        yield
        return
    box = set()
    tok = _DEFER.set(box)
    try:
        yield
    finally:
        _DEFER.reset(tok)
        if box:
            try:
                store_checks(sorted(box))
            except Exception as e:
                print("limits: route checks not stored:", str(e)[:120])


def check_soon(route_id):
    """The hook the bake calls after storing a primary leg: now, or at the end of checks_batched()."""
    box = _DEFER.get()
    if box is not None:
        box.add(route_id)
        return None
    return store_checks([route_id])


def stored_checks(route_ids=None):
    tenant = db.current_tenant()
    out = {}
    want = set(route_ids) if route_ids else None
    for r in db.query("SELECT id, limits_hits, limits_checked_at, limits_status FROM routes WHERE tenant_id = ?", (tenant,)):
        if want is not None and r["id"] not in want:
            continue
        try:
            hits = json.loads(r["limits_hits"]) if r.get("limits_hits") else []
        except Exception:
            hits = []
        out[r["id"]] = {"hits": hits or [], "checked_at": r.get("limits_checked_at"),
                        "status": r.get("limits_status")}
    return out



def exceeding(stored_entry, vehicle_type):
    """The stored hits where THIS vehicle is over the limit (13 Oct 2026). One rule for the
    Look-ahead's LIMIT flag (clashes.limit) and the Dashboard / Forecasts rows (costlines)."""
    return [h for h in ((stored_entry or {}).get("hits") or [])
            if isinstance(h, dict) and h.get("verdict") == "exceeds" and h.get("vehicle_profile") == vehicle_type]


#: 11 Nov 2026 (CLOCS card C-F1): the words when a limit's sign carries no exception, as the public map's rows say it
NO_EXCEPTION = "no exception recorded: check the sign"


def breach_text(hits, vehicle_type=None):
    """The words for the first breach and how many more: "<vehicle>, <value> <unit> <leg>, is over
    the <headline>, <exception>" (+N more). The clash rail puts the line's name in front of it.

    11 Nov 2026 (CLOCS card C-F1, John's yes): ONE wording wherever a limit is printed (the Look-ahead's
    flag, the Day sheet, the Route sheet, the Dashboard / Forecasts rows), in the public map's words (PR #253):
    no supplier in brackets (the sheets carry `credit_for` at their foot instead), the sign's exception after a
    comma, or NO_EXCEPTION when the sign has none recorded."""
    h = hits[0]
    leg = "going back empty" if h.get("leg") != "loaded" else "loaded"
    text = (f"{vehicle_label(h.get('vehicle_profile') or vehicle_type)}, {h.get('vehicle_value'):g} {h.get('unit')} {leg}, "
            f"is over the {h.get('headline')}")
    if h.get("exceptions"):
        text += f", {h['exceptions'].lower()}"
    else:
        text += f" · {NO_EXCEPTION}"
    if h.get("point"):
        text += " · a point limit: check whether the route passes it or crosses over or under it"
    if len(hits) > 1:
        text += f" (+{len(hits) - 1} more)"
    return text


def credit_for(route_ids):
    """11 Nov 2026 (CLOCS card C-F1): the credit line a sheet prints at its foot for the limits it names, now that
    the sentence names no supplier: "Road limits © OpenStreetMap contributors (ODbL)." (each source of a stored
    hit on these routes, once), or None when the routes carry no stored limit."""
    srcs = set()
    ids = [r for r in (route_ids or []) if r]
    for st in (stored_checks(ids) if ids else {}).values():     # stored_checks([]) would read every route
        for h in (st or {}).get("hits") or []:
            if isinstance(h, dict) and h.get("source") in SOURCES:
                srcs.add(h["source"])
    if not srcs:
        return None
    return "Road limits " + "; ".join(SOURCES[s]["attribution"] for s in sorted(srcs)) + "."

# --------------------------------------------------------------------------- #
#  The map's collection                                                        #
# --------------------------------------------------------------------------- #
def feature_collection(box=None):
    """Every stored limit in the tenant's extent (or box) as GeoJSON, each with the routes
    whose APPROVED vehicle is over it on a baked leg (`breaches`)."""
    lims = stored(box)
    checks = stored_checks()
    # only the vehicles the APPROVED plan puts on each route: a route is often baked for
    # more vehicles than anyone plans to send, and the public map shows the approved plan
    planned = {(r["route_id"], r["vehicle_type"]) for r in db.query(
        "SELECT DISTINCT route_id, vehicle_type FROM forecasts WHERE tenant_id = ? AND status = 'Approved'",
        (db.current_tenant(),))}
    over = {}
    for rid, st in checks.items():
        for h in st.get("hits") or []:
            if h.get("verdict") != "exceeds" or (rid, h.get("vehicle_profile")) not in planned:
                continue
            k = (h["source"], h["ext_id"], h["kind"])
            lst = over.setdefault(k, [])
            item = {"route_id": rid, "vehicle": vehicle_label(h["vehicle_profile"]),
                    "vehicle_value": h.get("vehicle_value"), "leg": h["leg"]}
            if item not in lst:
                lst.append(item)
    feats, counts, fetched = [], {}, {}
    for L in lims:
        k = (L["source"], L["ext_id"], L["kind"])
        br = over.get(k, [])
        kind = L["kind"]
        counts[kind] = counts.get(kind, 0) + 1
        fetched[L["source"]] = max(fetched.get(L["source"]) or "", L["fetched_at"] or "")
        props = {
            "id": f"{L['source']}:{L['ext_id']}:{kind}", "kind": kind, "value": L["value"], "unit": L["unit"],
            "label": f"{KINDS[kind]['label']} {fmt_value(kind, L['value'])}",
            "headline": headline(L),
            "icon_text": icon_text(kind, L["value"]),
            "imperial": (L.get("signed") or imperial_text(float(L["value"]))) if kind in ("height", "width") else None,
            "signed": L.get("signed"), "name": L.get("name"), "ref": L.get("ref"),
            "exceptions": L.get("exceptions"), "source": L["source"],
            "source_label": SOURCES[L["source"]]["short"], "attribution": SOURCES[L["source"]]["attribution"],
            "fetched_at": L["fetched_at"], "length_m": L.get("length_m"),
            "geom_type": L["geom_type"], "anchor": [L["anchor_lon"], L["anchor_lat"]],
            "breaches": br, "breach_count": len(br),
        }
        geom = ({"type": "Point", "coordinates": L["geometry"]} if L["geom_type"] == "Point"
                else {"type": "LineString", "coordinates": L["geometry"]})
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": feats, "counts": counts,
            "sources": {s: {"label": SOURCES[s]["short"], "attribution": SOURCES[s]["attribution"],
                            "fetched_at": fetched.get(s) or None, "note": SOURCES[s]["note"]}
                        for s in SOURCES},
            "kinds": {k: {"label": v["label"], "unit": v["unit"]} for k, v in KINDS.items()},
            "note": "Advisory. Limits come from OpenStreetMap and HERE and can be incomplete or out of date: "
                    "check the signed limit on site."}


# --------------------------------------------------------------------------- #
#  Diagnostics                                                                 #
# --------------------------------------------------------------------------- #
def diagnostics(source=None, probe=False):
    out = {"sources": SOURCES, "kinds": KINDS, "extent": tenant_extent(),
           "stored": {}, "import": import_state(),
           "match": {"match_m": MATCH_M, "along_min_m": ALONG_MIN_M, "along_share": ALONG_SHARE, "point_m": POINT_M},
           "here_fields": {k: list(v) for k, v in HERE_FIELDS.items()},
           "unverified": [
               "HERE Map Attributes has never been called: layer names (TRUCK_RESTR_FCn, ROAD_GEOM_FCn), "
               "field names, units (kg, cm) and the LAT/LON delta encoding are from documentation",
               "whether HERE's terms allow its limits to be drawn over a Mapbox basemap",
               "the matching distances are judgement, not measured against HERE polylines",
           ]}
    for r in db.query("SELECT source, kind, COUNT(*) AS n FROM road_limits GROUP BY source, kind"):
        out["stored"].setdefault(r["source"], {})[r["kind"]] = r["n"]
    if not probe:
        return out
    box = tenant_extent()
    if not box:
        out["probe"] = {"error": "the tenant has no extent (no locations or baked routes)"}
        return out
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if source == "here":
        p = {"key_set": bool(here_key()), "endpoint": HERE_ATTR_URL}
        if not p["key_set"]:
            p["error"] = "HERE_API_KEY is not set on the server"
        else:
            tile = here_tile_id(cx, cy, 12)
            p["tile_level"], p["tile_id"] = 12, tile
            try:
                raw = _here_get(["TRUCK_RESTR_FC4", "ROAD_GEOM_FC4"], [tile])
                p["raw_top_level_keys"] = sorted(raw.keys()) if isinstance(raw, dict) else str(type(raw))
                p["raw_sample"] = json.dumps(raw)[:3000]
                rows, dropped, unmatched = parse_here([raw])
                p["parsed"] = len(rows)
                p["dropped"] = dropped
                p["unmatched_restrictions"] = unmatched
                p["sample_rows"] = [{k: r[k] for k in ("kind", "value", "unit", "name", "length_m")} for r in rows[:5]]
                p["reading"] = ("parsed limits from HERE's answer — read sample_rows against the signs before importing"
                                if rows else "⚠️ nothing parsed: read raw_sample and fix HERE_FIELDS / the layer names")
            except urllib.error.HTTPError as e:
                p["error"] = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}"
                p["reading"] = ("a 401/403 means the key's plan does not include Map Attributes; "
                                "a 400 names the parameter HERE did not accept")
            except Exception as e:
                p["error"] = str(e)[:400]
        out["probe"] = p
    else:
        small = (round(cx - 0.05, 5), round(cy - 0.05, 5), round(cx + 0.05, 5), round(cy + 0.05, 5))
        data, server, errs = _overpass(overpass_query(small))
        p = {"box": list(small), "server": server, "errors": errs}
        if data is not None:
            rows, dropped = parse_osm(data.get("elements"))
            p["elements"] = len(data.get("elements") or [])
            p["parsed"] = len(rows)
            p["dropped"] = dropped
            p["sample_rows"] = [{k: r[k] for k in ("kind", "value", "unit", "signed", "name", "exceptions")}
                                for r in rows[:8]]
        out["probe"] = p
    return out
