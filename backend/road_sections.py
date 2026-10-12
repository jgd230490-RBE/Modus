"""
road_sections.py — shared road sections. Wayscope, 12 Oct 2026 (public map review §2.2d, option A).

WHY THIS EXISTS
---------------
Every figure on the public map was per route: one line feature per route per leg, each
stamped with its own daily figure. A highway authority reads the ROAD, not the route —
where three routes use the same lane the honest number is the three added together, and
nothing in the product added them. Measured on the live demo (11 Oct): 76 % of the laden
leg vertices are shared by two or more routes.

HOW
---
Vertex-run matching on the stored HERE polylines (route_geometry, alt 0, one vehicle
profile, each leg indexed separately):

  1. every vertex is keyed at 6 decimal places; a second key on a 1e-5 degree grid
     (with a neighbour-cell search) joins near-identical vertices two bakes drew a few
     millionths of a degree apart;
  2. each canonical vertex records the SET of routes that pass through it, and so does
     each SEGMENT (a consecutive pair of vertices, either direction);
  3. walking each route's polyline in order, a RUN is a maximal chain of consecutive
     segments with the same owner set of two or more routes — two or more consecutive
     shared vertices. Ownership is per segment, not per vertex, so where the owner set
     changes mid-road (a third route joins) the boundary vertex belongs to both runs and
     no length is lost between them; and two routes that merely CROSS at one vertex share
     no segment and make no run. Every shared segment belongs to exactly ONE run (12 Oct
     2026, the review and fix pass): a chain stops at a segment already used, so a route
     that doubles back or loops never puts a stretch in two runs or a U-turn in one, and
     chains of one owner set that meet end to end where that set does not branch are
     joined. So per route, its runs' lengths add up to no more than its own length, and
     a CO2e share apportioned by length never exceeds the route's figure.

A known limit: two bakes that drew one road with DIFFERENT vertex sets share only the
segments whose two ends both match. A route with an extra vertex of its own between two
shared vertices (A = 1, 2, 2.5, 3, 4 and B = 1, 2, 3, 4) gives runs 1-2 and 3-4; the
stretch 2-3 is B's alone and is lost to the shared figure.

The runs are stored in `route_sections` (tenanted, in the tenant package) and rebuilt
whenever a primary geometry is upserted or cleared, on import, or on demand.

THE MONTH READ (road_load)
--------------------------
One load = one two-way movement, never doubled. The LOADED leg carries the figure, and
the figure is the PUBLIC MAP BAR's: the per-route numbers come from the same per-line
payload the bar and the bulletin read (/api/public/month-kpis called as a function), over
the same routes — the ones the map draws; a line on a route with no stored laden road route
is named in `routes_not_drawn`, never counted (12 Oct 2026, the review and fix pass) — so a
run drawn on the map and the bar beside it cannot disagree. One limit: the sections are
worked out on ONE vehicle profile's road routes (index_profile), while the map draws each
route from whichever profile is stored for it; a route stored only for another profile is
in the totals and on no section, and `routes_off_index` names it. Movements a day on a run =
the sum, over the routes that own it, of their Approved lines' loads in the month (tonnes
÷ payload, as typed, fractional — the bar's rule, never rounded per line) ÷ the working
days. Vehicles = Σ per line ceil((loads ÷ working days) ÷ what one vehicle can do a day
on that route), the bar's rule; the Dashboard's rounded-up `trips` rides beside it,
named. CO2e for the month is apportioned by length: a route's co2_t (costlines' figure,
both legs) × run length ÷ the route's TWO-WAY length (loaded + baked return) — the carbon
emitted ON the run, both lengths haversine over the stored vertices. (Until 12 Oct the
divisor was the loaded leg alone, which put the whole trip's carbon on the laden half of
the road: twice the carbon emitted there wherever the return leg was baked.) Teams are
NAMES, through taxonomy — a team id never leaves this module.

WHAT THIS DOES NOT DO
---------------------
It does not know road names or numbers (route_geometry stores no HERE span data), it
cannot see two bakes that drew one road with different vertex sets, and it does not call
HERE, Mapbox or anything else.
"""
import contextlib
import contextvars
import functools
import hashlib
import json
import math
from datetime import datetime, timezone

import db
import taxonomy

LEGS = ("loaded", "return")


def leg_error():
    """
    The one sentence a caller reads when `leg` names no leg — words, not a Python tuple
    or list rendered into the message (12 Oct 2026 review: the 400s used to print
    "['loaded', 'return']"). main.py's two 400s and road_load's ValueError all read this.
    """
    return "leg must be one of " + " or ".join(f"'{l}'" for l in LEGS)


KEY_DP = 6              # the exact key: six decimal places (~0.1 m)
SNAP_DEG = 1e-5         # the second key: vertices within this (in both axes) are one vertex
MIN_RUN = 2             # a run is two or more consecutive shared vertices
MIN_OWNERS = 2          # ...owned by two or more routes

_EARTH_KM = 6371.0088


# --------------------------------------------------------------------------- #
#  Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def coords_of(geometry):
    """
    The [lon, lat] list of a stored geometry. The bake stores a plain coordinate list;
    an older package (and one harness) stores a GeoJSON LineString — both are read.
    """
    g = geometry
    if isinstance(g, str):
        try:
            g = json.loads(g)
        except Exception:
            return []
    if isinstance(g, dict):
        g = g.get("coordinates") or []
    out = []
    for p in g or []:
        try:
            out.append([float(p[0]), float(p[1])])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def haversine_km(a, b):
    """Great-circle distance between two [lon, lat] points, in km."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def length_km(coords):
    return sum(haversine_km(coords[i - 1], coords[i]) for i in range(1, len(coords)))


def _key(p):
    return (round(p[0], KEY_DP), round(p[1], KEY_DP))


def _cell(p):
    return (int(math.floor(p[0] / SNAP_DEG)), int(math.floor(p[1] / SNAP_DEG)))


class _Vertices:
    """
    Canonical vertex ids. Exact 6 dp key first; else the 1e-5 degree grid, searching the
    cell and its eight neighbours for a canonical vertex within SNAP_DEG on both axes, so
    two points 3e-6 apart match even when a cell boundary falls between them.
    """

    def __init__(self):
        self.by_key = {}        # exact key -> id
        self.by_cell = {}       # grid cell -> [ids]
        self.coord = []         # id -> [lon, lat] of the first point seen
        self.owners = []        # id -> set of route ids

    def resolve(self, p):
        """The canonical vertex id of a point. Owners are added by build_runs once the
        route's walk is known to have a segment (12 Oct 2026: a one-vertex 'route' owns
        nothing and is not counted)."""
        k = _key(p)
        vid = self.by_key.get(k)
        if vid is None:
            cx, cy = _cell(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for cand in self.by_cell.get((cx + dx, cy + dy), ()):
                        c = self.coord[cand]
                        if abs(c[0] - p[0]) <= SNAP_DEG and abs(c[1] - p[1]) <= SNAP_DEG:
                            vid = cand
                            break
                    if vid is not None:
                        break
                if vid is not None:
                    break
            if vid is None:
                vid = len(self.coord)
                self.coord.append([p[0], p[1]])
                self.owners.append(set())
                self.by_cell.setdefault((cx, cy), []).append(vid)
            self.by_key[k] = vid
        return vid


def _run_id(leg, owners, geom):
    """
    A short id that is stable across rebuilds of the same geometry. 12 Oct 2026 (the
    review and fix pass): the hash covers every vertex, not only the two ends — two runs
    with one owner set and the same two ends (a loop, or two ways between one pair of
    junctions) had one id and collided on the table's primary key.
    """
    s = "|".join([leg, ",".join(sorted(owners))] + [f"{p[0]:.6f},{p[1]:.6f}" for p in geom])
    return "S" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def build_runs(polylines, leg="loaded"):
    """
    The shared runs of one leg.

    `polylines` is {route_id: [[lon, lat], ...]} (one per route, the primary option).
    Returns (runs, stats). Each run: id, leg, routes (sorted), geometry (lon/lat list),
    length_km, vertices, first, last. stats: routes_indexed, vertices_total,
    vertices_shared, runs.

    12 Oct 2026 (the review and fix pass): every shared SEGMENT belongs to exactly ONE
    stored run. Until then a run was a walk sequence, so a route that doubled back over a
    shared stretch (a gate approach) made a run with a U-turn in it — the stretch's length
    counted twice, and the other owner's CO2e share came out larger than its month total —
    and two routes that both looped made two runs over one segment. Now a chain stops at a
    segment it has already used, and chains of one owner set that meet end to end at a
    vertex where nothing else of that owner set branches are joined, so a run is still the
    longest stretch it can be. A route whose walk has fewer than two distinct vertices is
    not indexed and owns no vertex (it has no segment).
    """
    V = _Vertices()
    walked = {}
    for rid in sorted(polylines):
        ids = []
        for p in polylines[rid]:
            vid = V.resolve(p)
            # a polyline can repeat a vertex (a gate approach that doubles back); the
            # second copy adds nothing to a run and would break the "consecutive" rule
            if ids and ids[-1] == vid:
                continue
            ids.append(vid)
        if len(ids) < MIN_RUN:
            continue                       # no segment: not indexed, owns nothing
        for vid in ids:
            V.owners[vid].add(rid)
        walked[rid] = ids

    def _sk(a, b):
        return (a, b) if a < b else (b, a)

    # who drives each segment: the routes whose walk has this pair consecutively, in
    # either direction
    seg_owners = {}
    for rid, ids in walked.items():
        for k in range(1, len(ids)):
            seg_owners.setdefault(_sk(ids[k - 1], ids[k]), set()).add(rid)

    # 1. chains in walking order; a segment joins at most one chain
    used = set()
    chains = []                            # [(frozenset owners, [vertex ids])]
    for rid in sorted(walked):
        ids = walked[rid]
        n = len(ids)
        k = 1
        while k < n:
            sk = _sk(ids[k - 1], ids[k])
            own = seg_owners[sk]
            if len(own) < MIN_OWNERS or sk in used:
                k += 1
                continue
            used.add(sk)
            seq = [ids[k - 1], ids[k]]
            j = k
            while j + 1 < n:
                nk = _sk(ids[j], ids[j + 1])
                if nk in used or seg_owners[nk] != own:
                    break                  # a used segment (a U-turn, a loop) or a new owner set
                used.add(nk)
                seq.append(ids[j + 1])
                j += 1
            chains.append((frozenset(own), seq))
            k = j + 1

    # 2. join chains of one owner set that meet end to end where that owner set does not
    # branch (the joint vertex has exactly two of its segments)
    by_owner = {}
    for own, seq in chains:
        by_owner.setdefault(own, []).append(seq)
    runs = []
    for own, seqs in by_owner.items():
        deg = {}
        for sk, o in seg_owners.items():
            if o == own:
                deg[sk[0]] = deg.get(sk[0], 0) + 1
                deg[sk[1]] = deg.get(sk[1], 0) + 1
        merged = True
        while merged and len(seqs) > 1:
            merged = False
            for i in range(len(seqs)):
                a = seqs[i]
                if a[0] == a[-1]:
                    continue               # a closed loop: nothing to join
                for j in range(len(seqs)):
                    if i == j:
                        continue
                    b = seqs[j]
                    if b[0] == b[-1]:
                        continue
                    if a[-1] == b[0] and deg.get(a[-1]) == 2:
                        new = a + b[1:]
                    elif a[-1] == b[-1] and deg.get(a[-1]) == 2:
                        new = a + b[::-1][1:]
                    elif a[0] == b[-1] and deg.get(a[0]) == 2:
                        new = b + a[1:]
                    elif a[0] == b[0] and deg.get(a[0]) == 2:
                        new = b[::-1] + a[1:]
                    else:
                        continue
                    seqs = [s for x, s in enumerate(seqs) if x not in (i, j)] + [new]
                    merged = True
                    break
                if merged:
                    break
        for s in seqs:
            if len(s) < MIN_RUN:
                continue
            geom = [V.coord[v] for v in s]
            runs.append({
                "id": _run_id(leg, own, geom),
                "leg": leg,
                "routes": sorted(own),
                "geometry": geom,
                "length_km": round(length_km(geom), 3),
                "vertices": len(s),
                "first": geom[0], "last": geom[-1],
            })
    runs.sort(key=lambda r: (-r["length_km"], r["routes"], r["id"]))
    stats = {
        "routes_indexed": len(walked),
        "vertices_total": sum(1 for o in V.owners if o),
        "vertices_shared": sum(1 for o in V.owners if len(o) >= MIN_OWNERS),
        "runs": len(runs),
    }
    return runs, stats


# --------------------------------------------------------------------------- #
#  The stored index                                                            #
# --------------------------------------------------------------------------- #
def index_profile():
    """
    The vehicle profile the index is built on: the network default where it has any
    primary geometry, else the most-baked other profile (the public map's own
    "whichever is baked, labelled" rule), else the default with nothing to index.
    """
    import network   # lazy: network imports this module
    want = network.DEFAULT_PROFILE
    rows = db.query(
        "SELECT vehicle_profile, COUNT(*) AS n FROM route_geometry "
        "WHERE tenant_id = ? AND alt_index = 0 AND geometry IS NOT NULL "
        "GROUP BY vehicle_profile", (db.current_tenant(),))
    have = {r["vehicle_profile"]: int(r["n"]) for r in rows}
    if want in have or not have:
        return want
    return sorted(have, key=lambda p: (-have[p], p))[0]


def polylines_for(leg, profile):
    """{route_id: coords} of the primary geometry of one leg for one profile."""
    out = {}
    for g in db.query(
            "SELECT route_id, geometry FROM route_geometry WHERE tenant_id = ? "
            "AND vehicle_profile = ? AND leg = ? AND alt_index = 0 AND geometry IS NOT NULL",
            (db.current_tenant(), profile, leg)):
        pts = coords_of(g["geometry"])
        if len(pts) >= 2:
            out[g["route_id"]] = pts
    return out


def compute(profile=None):
    """Build both legs in memory. {profile, legs: {leg: {runs, stats}}}."""
    profile = profile or index_profile()
    legs = {}
    for leg in LEGS:
        runs, stats = build_runs(polylines_for(leg, profile), leg=leg)
        legs[leg] = {"runs": runs, "stats": stats}
    return {"profile": profile, "legs": legs}


def rebuild(profile=None):
    """
    Recompute the index for the current tenant and replace the stored rows. Returns
    the status counts. Nothing external is called; a tenant with no geometry ends with
    an empty table.

    12 Oct 2026 (the review and fix pass): the DELETE and every INSERT go in ONE
    transaction (db.execute_atomic), so a road-load read never sees a half-written
    index, and a rebuild that fails — two at once colliding on the primary key — leaves
    the previous index whole instead of a partial one.
    """
    built = compute(profile)
    now = datetime.now(timezone.utc).isoformat()
    tenant = db.current_tenant()
    rows = [(tenant, r["id"], leg, json.dumps(r["routes"]), json.dumps(r["geometry"]),
             r["length_km"], now)
            for leg in LEGS for r in built["legs"][leg]["runs"]]
    db.execute_atomic([
        ("DELETE FROM route_sections WHERE tenant_id = ?", (tenant,)),
        ("INSERT INTO route_sections (tenant_id, section_id, leg, routes_json, "
         "geometry_json, length_km, built_at) VALUES (?, ?, ?, ?, ?, ?, ?)", rows, True),
    ])
    return status(_built=built, built_at=now)


# 12 Oct 2026 (the review and fix pass): a bake batch upserts up to 25 legs, and each
# primary upsert used to rebuild the whole index — 25 full rebuilds a batch. Inside
# `batched()` the hook only marks the index dirty; the block's end rebuilds ONCE.
_DEFER = contextvars.ContextVar("road_sections_defer", default=None)


@contextlib.contextmanager
def batched(where):
    """
    Hold every rebuild the hooks ask for inside the block and run one at its end, if
    any was asked for (also when the block raises: the geometry may have changed before
    it did). Nested blocks defer to the outermost.
    """
    if _DEFER.get() is not None:
        yield
        return
    box = {"dirty": False}
    tok = _DEFER.set(box)
    try:
        yield
    finally:
        _DEFER.reset(tok)
        if box["dirty"]:
            _rebuild_quietly(where)


def rebuild_once(where):
    """A decorator: run the function inside batched(where) — one rebuild at its end."""
    def deco(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            with batched(where):
                return fn(*a, **k)
        return inner
    return deco


def _rebuild_quietly(where):
    """
    The hook the bake, the clear and the import call. Never raises into them.

    12 Oct 2026 (§2.2b): the one hook for EVERY index derived from the primary geometry —
    after the shared sections it re-clips the routes against the council areas
    (areas.rebuild_quietly), so a bake batch still rebuilds each index once, at its end.
    """
    box = _DEFER.get()
    if box is not None:
        box["dirty"] = True
        return None
    try:
        res = rebuild()
    except Exception as e:
        print(f"road_sections: index not rebuilt after {where}: {e}")
        res = None
    _rebuild_areas(where)
    return res


def _rebuild_areas(where):
    """The council-area clip (areas.py), imported late: areas imports this module."""
    try:
        import areas
        areas.rebuild_quietly(where)
    except Exception as e:
        print(f"road_sections: council areas not re-clipped after {where}: {e}")


def stored_runs(leg="loaded"):
    """The stored runs of one leg, geometry parsed, longest first."""
    rows = db.query(
        "SELECT section_id, leg, routes_json, geometry_json, length_km, built_at "
        "FROM route_sections WHERE tenant_id = ? AND leg = ?",
        (db.current_tenant(), leg))
    out = []
    for r in rows:
        try:
            routes = json.loads(r["routes_json"] or "[]")
            geom = json.loads(r["geometry_json"] or "[]")
        except Exception:
            continue
        out.append({"id": r["section_id"], "leg": r["leg"], "routes": sorted(routes),
                    # rounded on read: the column is REAL, a 4-byte float on Postgres
                    # (12.345 comes back 12.345000267), an 8-byte one on SQLite
                    "geometry": geom, "length_km": round(float(r["length_km"] or 0.0), 3),
                    "vertices": len(geom), "first": (geom[0] if geom else None),
                    "last": (geom[-1] if geom else None), "built_at": r["built_at"]})
    out.sort(key=lambda r: (-r["length_km"], r["routes"], r["id"]))
    return out


def status(_built=None, built_at=None):
    """
    Counts: per leg the routes indexed, the runs and the vertices shared (recomputed
    from the geometry, so the figure is exact), and the runs STORED — `stale` when the
    stored count differs from what the geometry gives now.
    """
    built = _built or compute()
    stored = db.query(
        "SELECT leg, COUNT(*) AS n, MAX(built_at) AS built_at FROM route_sections "
        "WHERE tenant_id = ? GROUP BY leg", (db.current_tenant(),))
    stored_n = {r["leg"]: int(r["n"]) for r in stored}
    built_at = built_at or max([r["built_at"] for r in stored if r["built_at"]] or [None])
    legs = {}
    for leg in LEGS:
        st = dict(built["legs"][leg]["stats"])
        st["stored_runs"] = stored_n.get(leg, 0)
        st["shared_km"] = round(sum(r["length_km"] for r in built["legs"][leg]["runs"]), 3)
        legs[leg] = st
    return {
        "tenant_id": db.current_tenant(),
        "profile": built["profile"],
        "built_at": built_at,
        "legs": legs,
        # the headline trio, for the loaded leg
        "routes_indexed": legs["loaded"]["routes_indexed"],
        "runs": legs["loaded"]["runs"],
        "vertices_shared": legs["loaded"]["vertices_shared"],
        "stale": any(legs[l]["stored_runs"] != legs[l]["runs"] for l in LEGS),
    }


# --------------------------------------------------------------------------- #
#  The month read                                                              #
# --------------------------------------------------------------------------- #
def _route_teams():
    """{route_id: team value as typed} for the tenant's routes."""
    return {r["id"]: r.get("ipt") for r in db.query(
        "SELECT id, ipt FROM routes WHERE tenant_id = ?", (db.current_tenant(),))}


def month_lines(month):
    """
    The public map bar's per-line payload for one month — /api/public/month-kpis called
    as a function (as bulletin.month_payload does), never over HTTP. The import is
    deferred because main imports network, which imports this module.
    """
    import main
    # `unit` handed in: called as a function the parameter's default is FastAPI's Query
    # object, not "vehicles", and the endpoint answers 400 (found by http_smoke, 12 Oct)
    return main.public_month_kpis(month=int(month), unit="vehicles")


def route_lengths(profile):
    """
    {route_id: {"loaded", "return", "two_way"}} in km, measured the one way this module
    measures a run — haversine over the stored primary vertices of `profile`. `two_way` is
    loaded + return where the return leg is baked, else the loaded alone: derived's km_trip
    rule (`distance_km + (return_km if return_baked else 0)`), so a route's month CO2e,
    which costlines works out over km_trip, is divided over the same legs it was summed on.
    """
    loaded = {rid: length_km(pts) for rid, pts in polylines_for("loaded", profile).items()}
    ret = {rid: length_km(pts) for rid, pts in polylines_for("return", profile).items()}
    out = {}
    for rid in set(loaded) | set(ret):
        lk, rk = loaded.get(rid, 0.0), ret.get(rid, 0.0)
        out[rid] = {"loaded": lk, "return": rk, "two_way": lk + rk}
    return out


_NO_VOLUME = {"loads": 0.0, "trips": 0, "vehicles": 0, "co2_t": 0.0, "lines": 0,
              "unbaked_lines": 0, "co2_lines": 0, "co2_lines_unbaked": 0}


def _carbon_stamp():
    """carbon.SUMMARY_STAMP, imported late: carbon imports network, which imports this module."""
    import carbon
    return carbon.SUMMARY_STAMP


def drawn_route_ids():
    """
    The routes the public map draws (bulletin.drawn_routes, the browser's routePropsById):
    the bar counts only these, and so does road_load. Imported late: bulletin imports
    carbon, which imports network, which imports this module.
    """
    import bulletin
    return set(bulletin.drawn_routes())


def road_load(month, factors=None, working_days=None, leg="loaded", profile=None, drawn=None):
    """
    One entry per stored run of `leg` that carries volume in `month`.

    The per-route figures are the public map bar's, from the one per-line payload the bar
    and the bulletin read (month_lines), over the same routes the bar counts — the ones
    the map DRAWS (12 Oct 2026, the review and fix pass: a line on a route with no stored
    laden geometry is named in `routes_not_drawn` and left out, as the bar and the
    bulletin's rule 1 do; until then the totals counted it and exceeded the bar):
      loads              Σ the lines' vehicle_loads — tonnes ÷ payload, as typed, fractional
      movements_per_day  loads ÷ working days: two-way movements, one per load, never
                         doubled, never rounded per line (the bar's rule)
      vehicles           Σ per line ceil((loads ÷ working days) ÷ what one vehicle can do a
                         day on that route) — the bar's rule; a line whose route has no
                         stored road route for ITS vehicle has no cycle: counted in
                         `unbaked_lines`, never zeroed
      trips              Σ per line ceil(loads) — the Dashboard's rounded-up figure, kept
                         beside the bar's and named so a reader of both pages sees why
                         they differ by rounding; it is NOT the movements figure
      co2_t              Σ route month CO2e × run length ÷ the route's two-way length
                         (route_lengths): the carbon emitted ON the run. A route's shares
                         over its loaded-leg runs and its return-leg runs together never
                         exceed its month figure (every shared segment is in one run).
    The return leg is served separately and carries the SAME loads back empty: labelled
    as empties and never added to the loaded figure.

    Carbon is never a zero dressed as a figure (12 Oct 2026, the review and fix pass, the
    bulletin's e85b491 rule): when the payload's carbon read failed (`co2_error`), every
    co2_t here is None; a route share is None when the route has volume and none of its
    lines carries carbon; a run's co2_t is None when none of its owners with volume has a
    figure, and it names the lines left out in `co2_lines_unbaked`.

    `working_days` is the planning block's figure handed in by main's one reader of it;
    when not given, the payload's own `working_days` (the same reader) is used. `factors`
    is accepted for the endpoint's call shape and not read — the payload resolves its own.
    `drawn` (a set of route ids) is for a caller that already has the map's routes.
    """
    month = int(month)
    if leg not in LEGS:
        raise ValueError(leg_error())
    payload = month_lines(month)
    wd = float(working_days or payload.get("working_days") or 0) or None
    if not wd:
        raise ValueError("working days per month is not set")
    co2_failed = bool(payload.get("co2_error"))
    drawn = drawn_route_ids() if drawn is None else set(drawn)

    # per route: the bar's arithmetic over the month's Approved lines on drawn routes
    per_route = {}
    not_drawn = {}
    unbaked_lines = 0
    line_teams = {}
    for l in payload.get("lines", []) or []:
        rid = l["route_id"]
        if rid not in drawn:
            not_drawn[rid] = not_drawn.get(rid, 0) + 1      # named, not counted (the bar's rule 1)
            continue
        pr = per_route.setdefault(rid, dict(_NO_VOLUME))
        pr["lines"] += 1
        loads = float(l.get("vehicle_loads") or 0.0)
        pr["loads"] += loads
        pr["trips"] += int(math.ceil(round(loads, 9))) if loads > 0 else 0
        tpv = l.get("trips_per_vehicle_day")
        if tpv and float(tpv) > 0:
            pr["vehicles"] += int(math.ceil((loads / wd) / float(tpv))) if loads > 0 else 0
        else:
            pr["unbaked_lines"] += 1
            unbaked_lines += 1
        if l.get("co2_t") is None:
            pr["co2_lines_unbaked"] += 1
        else:
            pr["co2_t"] += float(l["co2_t"])
            pr["co2_lines"] += 1
        if l.get("ipt"):
            line_teams.setdefault(rid, set()).add(l["ipt"])

    profile = profile or index_profile()
    lens = route_lengths(profile)
    route_team = _route_teams()
    labels = taxonomy.team_labels()

    def team_names(rid):
        names = set()
        if route_team.get(rid):
            names.add(taxonomy.team_text(route_team[rid], labels))
        for t in line_teams.get(rid, ()):
            # team_text, not team_name: a line value that is not exactly one id (two ids
            # joined by a slash) would pass team_name unchanged and reach the feed as ids
            names.add(taxonomy.team_text(t, labels))
        return sorted(n for n in names if n)

    def route_co2(rid):
        """The route's month CO2e, or None when it is not a figure (read failed, or the
        route has volume and none of its lines carries carbon). No volume reads 0.0."""
        pr = per_route.get(rid)
        if co2_failed:
            return None
        if not pr or pr["loads"] <= 0:
            return 0.0
        return pr["co2_t"] if pr["co2_lines"] else None

    def co2_share(rid, run_km):
        c = route_co2(rid)
        if c is None:
            return None
        tw = (lens.get(rid) or {}).get("two_way") or 0.0
        return (c * run_km / tw) if tw > 0 else 0.0

    runs_out = []
    for run in stored_runs(leg):
        owners = run["routes"]
        loads = sum(per_route.get(r, _NO_VOLUME)["loads"] for r in owners)
        if loads <= 0:
            continue
        co2, co2_known = 0.0, False
        routes_out = []
        for r in owners:
            pr = per_route.get(r, _NO_VOLUME)
            share = co2_share(r, run["length_km"])
            if share is not None:
                co2 += share
                if pr["loads"] > 0:
                    co2_known = True
            rl = lens.get(r) or {}
            routes_out.append({
                "route_id": r,
                "teams": team_names(r),
                "loads": round(pr["loads"], 3),
                "trips": pr["trips"],
                "movements_per_day": round(pr["loads"] / wd, 2),
                "vehicles": pr["vehicles"],
                "co2_t": (None if share is None else round(share, 3)),
                "co2_lines_unbaked": pr["co2_lines_unbaked"],
                "route_length_km": round(rl.get(leg, 0.0), 3),
                "two_way_length_km": round(rl.get("two_way", 0.0), 3),
            })
        runs_out.append({
            "id": run["id"],
            "leg": leg,
            "routes": owners,
            "teams": sorted({t for r in owners for t in team_names(r)}),
            "loads": round(loads, 3),
            "trips": sum(per_route.get(r, _NO_VOLUME)["trips"] for r in owners),
            "movements_per_day": round(loads / wd, 2),
            "vehicles": sum(per_route.get(r, _NO_VOLUME)["vehicles"] for r in owners),
            "co2_t": (round(co2, 3) if (co2_known and not co2_failed) else None),
            "co2_lines_unbaked": sum(per_route.get(r, _NO_VOLUME)["co2_lines_unbaked"] for r in owners),
            "length_km": run["length_km"],
            "vertices": run["vertices"],
            "first": run["first"], "last": run["last"],
            "route_shares": routes_out,
            "geometry": run["geometry"],
        })

    routes_with_volume = sorted(r for r, pr in per_route.items() if pr["loads"] > 0)
    total_loads = sum(pr["loads"] for pr in per_route.values())
    co2_lines = sum(pr["co2_lines"] for pr in per_route.values())
    co2_unb = sum(pr["co2_lines_unbaked"] for pr in per_route.values())
    totals = {
        # per ROUTE, not a sum over runs: a route runs through many runs, so adding the
        # runs up would count its loads once per run
        "routes_with_volume": len(routes_with_volume),
        "routes_in_runs": len({r for run in runs_out for r in run["routes"]}),
        "loads": round(total_loads, 3),
        "trips": sum(pr["trips"] for pr in per_route.values()),
        "movements_per_day": round(total_loads / wd, 2),
        "vehicles": sum(pr["vehicles"] for pr in per_route.values()),
        "co2_t": (None if (co2_failed or (co2_unb and not co2_lines))
                  else round(sum(pr["co2_t"] for pr in per_route.values()), 3)),
        "runs": len(runs_out),
        "shared_km": round(sum(r["length_km"] for r in runs_out), 3),
        "lines": sum(pr["lines"] for pr in per_route.values()),
        "unbaked_lines": unbaked_lines,
        "co2_lines_unbaked": co2_unb,
    }
    # the index is built on ONE vehicle profile; the map draws a route from whichever
    # profile is stored for it, so a route drawn only from another profile is on no section
    off_index = sorted(r for r in routes_with_volume if r not in lens)
    notes = []
    if not per_route and not not_drawn:
        notes.append("No approved volume in this month.")
    elif not per_route:
        n_nd = sum(not_drawn.values())
        notes.append(f"No approved volume on a route the map draws in this month: {n_nd} "
                     f"line{'' if n_nd == 1 else 's'} on routes with no stored road route, "
                     "listed in routes_not_drawn and not counted.")
    elif not runs_out:
        if not stored_runs(leg):
            notes.append("No shared road sections are indexed: no road routes are stored, "
                         "or the index has not been rebuilt.")
        else:
            notes.append("Approved volume this month runs on no shared road section.")
    if unbaked_lines:
        notes.append(f"{unbaked_lines} line(s) on a route with no stored road route for the "
                     f"line's vehicle: counted in the movements, left out of the vehicles.")
    if off_index:
        notes.append(f"The sections are worked out on the {profile} road routes; "
                     f"{len(off_index)} route(s) with volume have none stored for it and are "
                     "on no section (they are in the totals).")
    if leg == "return":
        notes.append("Return leg: the same loads running back empty. These are not "
                     "additional movements and are never added to the loaded figure.")
    out = {
        "month": month,
        "leg": leg,
        "working_days": wd,
        "profile": profile,
        "basis": "two-way movements a day: one load = one two-way movement; the month's "
                 "approved loads (tonnes ÷ payload, as typed, not rounded per line) / working "
                 "days, summed over the routes that share the section — the public map bar's "
                 "figure, over the routes the map draws. `trips` is the Dashboard's rounded-up "
                 "count, shown beside it.",
        "co2_basis": "CO2e on a section = Σ each route's month CO2e (routed km × the vehicle's "
                     "kg CO2e/km, both legs) × section length / the route's two-way length "
                     "(loaded + stored return): the carbon emitted on the section.",
        "runs": runs_out,
        "totals": totals,
        "routes_not_drawn": {
            "lines": sum(not_drawn.values()), "routes": sorted(not_drawn),
            "note": ("Lines on routes the map does not draw (no stored road route for any "
                     "vehicle) are not in these figures. They are listed here, not counted "
                     "as zero.") if not_drawn else None,
        },
        "routes_off_index": off_index,
        "notes": notes,
        # the Carbon page's stamp, read from carbon.py (deferred: carbon imports network,
        # which imports this module) — a CO2e figure a person reads is an estimate from the
        # plan and the feed says so beside it, in the Carbon page's own words
        "carbon": {
            "stamp": _carbon_stamp(),
            "rule": "CO₂e = routed km × the vehicle's kg CO₂e/km, approved plan only; a section's "
                    "share = that route's month CO₂e × section length ÷ that route's two-way length "
                    "(loaded + stored return).",
        },
    }
    if co2_failed:
        out["co2_error"] = payload["co2_error"]
        notes.append("The carbon figures could not be read, so no CO2e figure is given here "
                     "(each reads null) — see co2_error.")
    return out


# --------------------------------------------------------------------------- #
#  Diagnostics                                                                 #
# --------------------------------------------------------------------------- #
def diagnostics(top=10, leg="loaded"):
    """Read-only: the status and the `top` longest stored runs of one leg with their route sets."""
    st = status()
    runs = stored_runs(leg)[:top]
    lines = [f"road sections — tenant {st['tenant_id']}, profile {st['profile']}, "
             f"built {st['built_at'] or 'never'}{' (STALE)' if st['stale'] else ''}"]
    for l in LEGS:
        s = st["legs"][l]
        lines.append(f"  {l}: {s['routes_indexed']} routes indexed, {s['runs']} runs "
                     f"({s['stored_runs']} stored), {s['vertices_shared']} of "
                     f"{s['vertices_total']} vertices shared, {s['shared_km']} km of shared road")
    lines.append(f"the {len(runs)} longest {leg} runs:")
    for r in runs:
        lines.append(f"  {r['id']}  {r['length_km']:7.3f} km  {r['vertices']:4d} vertices  "
                     f"{'+'.join(r['routes'])}")
    return {"status": st, "leg": leg,
            "longest": [{k: r[k] for k in ("id", "routes", "length_km", "vertices", "first", "last")}
                        for r in runs],
            "text": "\n".join(lines)}
