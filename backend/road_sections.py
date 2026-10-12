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
     no segment and make no run. Runs are de-duplicated across the routes that walk them
     (the same vertex sequence, either direction, is one run; a run that is a
     sub-sequence of a longer run with the same owners is dropped).

The runs are stored in `route_sections` (tenanted, in the tenant package) and rebuilt
whenever a primary geometry is upserted or cleared, on import, or on demand.

THE MONTH READ (road_load)
--------------------------
One load = one two-way movement, never doubled. The LOADED leg carries the figure, and
the figure is the PUBLIC MAP BAR's: the per-route numbers come from the same per-line
payload the bar and the bulletin read (/api/public/month-kpis called as a function), so a
run drawn on the map and the bar beside it cannot disagree. Movements a day on a run =
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

    def resolve(self, p, route_id):
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
        self.owners[vid].add(route_id)
        return vid


def _run_id(leg, owners, first, last):
    """A short id that is stable across rebuilds of the same geometry."""
    s = "|".join([leg, ",".join(sorted(owners)),
                  f"{first[0]:.6f},{first[1]:.6f}", f"{last[0]:.6f},{last[1]:.6f}"])
    return "S" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def build_runs(polylines, leg="loaded"):
    """
    The shared runs of one leg.

    `polylines` is {route_id: [[lon, lat], ...]} (one per route, the primary option).
    Returns (runs, stats). Each run: id, leg, routes (sorted), geometry (lon/lat list),
    length_km, vertices, first, last. stats: routes_indexed, vertices_total,
    vertices_shared, runs.
    """
    V = _Vertices()
    walked = {}
    for rid in sorted(polylines):
        pts = polylines[rid]
        ids = []
        for p in pts:
            vid = V.resolve(p, rid)
            # a polyline can repeat a vertex (a gate approach that doubles back); the
            # second copy adds nothing to a run and would break the "consecutive" rule
            if ids and ids[-1] == vid:
                continue
            ids.append(vid)
        walked[rid] = ids

    # who drives each segment: the routes whose walk has this pair consecutively, in
    # either direction
    seg_owners = {}
    for rid, ids in walked.items():
        for k in range(1, len(ids)):
            a, b = ids[k - 1], ids[k]
            seg_owners.setdefault((min(a, b), max(a, b)), set()).add(rid)

    def _seg(a, b):
        return seg_owners[(min(a, b), max(a, b))]

    candidates = {}
    for rid in sorted(walked):
        ids = walked[rid]
        n = len(ids)
        k = 1
        while k < n:
            own = _seg(ids[k - 1], ids[k])
            if len(own) < MIN_OWNERS:
                k += 1
                continue
            j = k
            while j + 1 < n and _seg(ids[j], ids[j + 1]) == own:
                j += 1
            seq = tuple(ids[k - 1:j + 1])          # the chain's vertices, boundary included
            if len(seq) >= MIN_RUN:
                # one run per vertex sequence whichever route walks it, either direction
                key = (frozenset(own), min(seq, seq[::-1]))
                candidates.setdefault(key, seq)
            k = j + 1

    # drop a run that is a sub-sequence of a longer run with the same owners (a route
    # with an extra vertex of its own splits the shared stretch it walks; the route
    # without it walks the whole stretch, and that is the run)
    by_owner = {}
    for (own, _k), seq in candidates.items():
        by_owner.setdefault(own, []).append(seq)
    runs = []
    for own, seqs in by_owner.items():
        seqs = sorted(seqs, key=len, reverse=True)
        kept = []
        for s in seqs:
            s_set = set(s)
            if any(s_set <= set(k) for k in kept):
                continue
            kept.append(s)
        for s in kept:
            geom = [V.coord[v] for v in s]
            runs.append({
                "id": _run_id(leg, own, geom[0], geom[-1]),
                "leg": leg,
                "routes": sorted(own),
                "geometry": geom,
                "length_km": round(length_km(geom), 3),
                "vertices": len(s),
                "first": geom[0], "last": geom[-1],
            })
    runs.sort(key=lambda r: (-r["length_km"], r["routes"], r["id"]))
    stats = {
        "routes_indexed": len(polylines),
        "vertices_total": len(V.coord),
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
    """
    built = compute(profile)
    now = datetime.now(timezone.utc).isoformat()
    db.execute("DELETE FROM route_sections WHERE tenant_id = ?", (db.current_tenant(),))
    for leg in LEGS:
        for r in built["legs"][leg]["runs"]:
            db.execute(
                "INSERT INTO route_sections (tenant_id, section_id, leg, routes_json, "
                "geometry_json, length_km, built_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (db.current_tenant(), r["id"], leg, json.dumps(r["routes"]),
                 json.dumps(r["geometry"]), r["length_km"], now))
    return status(_built=built, built_at=now)


def _rebuild_quietly(where):
    """The hook the bake, the clear and the import call. Never raises into them."""
    try:
        return rebuild()
    except Exception as e:
        print(f"road_sections: index not rebuilt after {where}: {e}")
        return None


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
                    "geometry": geom, "length_km": float(r["length_km"] or 0.0),
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
              "unbaked_lines": 0, "co2_lines_unbaked": 0}


def _carbon_stamp():
    """carbon.SUMMARY_STAMP, imported late: carbon imports network, which imports this module."""
    import carbon
    return carbon.SUMMARY_STAMP


def road_load(month, factors=None, working_days=None, leg="loaded", profile=None):
    """
    One entry per stored run of `leg` that carries volume in `month`.

    The per-route figures are the public map bar's, from the one per-line payload the bar
    and the bulletin read (month_lines), so the three cannot disagree:
      loads              Σ the lines' vehicle_loads — tonnes ÷ payload, as typed, fractional
      movements_per_day  loads ÷ working days: two-way movements, one per load, never
                         doubled, never rounded per line (the bar's rule)
      vehicles           Σ per line ceil((loads ÷ working days) ÷ what one vehicle can do a
                         day on that route) — the bar's rule; a line whose route is not
                         baked for its vehicle has no cycle: counted in `unbaked_lines`,
                         never zeroed
      trips              Σ per line ceil(loads) — the Dashboard's rounded-up figure, kept
                         beside the bar's and named so a reader of both pages sees why
                         they differ by rounding; it is NOT the movements figure
      co2_t              Σ route month CO2e × run length ÷ the route's two-way length
                         (route_lengths): the carbon emitted ON the run. A route's shares
                         over its loaded-leg runs and its return-leg runs together never
                         exceed its month figure.
    The return leg is served separately and carries the SAME loads back empty: labelled
    as empties and never added to the loaded figure.

    `working_days` is the planning block's figure handed in by main's one reader of it;
    when not given, the payload's own `working_days` (the same reader) is used. `factors`
    is accepted for the endpoint's call shape and not read — the payload resolves its own.
    When the payload's carbon read failed it says so in `co2_error`: that rides through
    here, every co2_t reads 0 and nothing raises.
    """
    month = int(month)
    if leg not in LEGS:
        raise ValueError(leg_error())
    payload = month_lines(month)
    wd = float(working_days or payload.get("working_days") or 0) or None
    if not wd:
        raise ValueError("working days per month is not set")

    # per route: the bar's arithmetic over the month's Approved lines
    per_route = {}
    unbaked_lines = 0
    line_teams = {}
    for l in payload.get("lines", []) or []:
        rid = l["route_id"]
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
            names.add(taxonomy.team_name(t, labels))
        return sorted(n for n in names if n)

    def co2_share(rid, run_km):
        pr = per_route.get(rid)
        tw = (lens.get(rid) or {}).get("two_way") or 0.0
        return (pr["co2_t"] * run_km / tw) if (pr and tw > 0) else 0.0

    runs_out = []
    for run in stored_runs(leg):
        owners = run["routes"]
        loads = sum(per_route.get(r, _NO_VOLUME)["loads"] for r in owners)
        if loads <= 0:
            continue
        co2 = 0.0
        routes_out = []
        for r in owners:
            pr = per_route.get(r, _NO_VOLUME)
            share = co2_share(r, run["length_km"])
            co2 += share
            rl = lens.get(r) or {}
            routes_out.append({
                "route_id": r,
                "teams": team_names(r),
                "loads": round(pr["loads"], 3),
                "trips": pr["trips"],
                "movements_per_day": round(pr["loads"] / wd, 2),
                "vehicles": pr["vehicles"],
                "co2_t": round(share, 3),
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
            "co2_t": round(co2, 3),
            "length_km": run["length_km"],
            "vertices": run["vertices"],
            "first": run["first"], "last": run["last"],
            "route_shares": routes_out,
            "geometry": run["geometry"],
        })

    routes_with_volume = sorted(r for r, pr in per_route.items() if pr["loads"] > 0)
    total_loads = sum(pr["loads"] for pr in per_route.values())
    totals = {
        # per ROUTE, not a sum over runs: a route runs through many runs, so adding the
        # runs up would count its loads once per run
        "routes_with_volume": len(routes_with_volume),
        "routes_in_runs": len({r for run in runs_out for r in run["routes"]}),
        "loads": round(total_loads, 3),
        "trips": sum(pr["trips"] for pr in per_route.values()),
        "movements_per_day": round(total_loads / wd, 2),
        "vehicles": sum(pr["vehicles"] for pr in per_route.values()),
        "co2_t": round(sum(pr["co2_t"] for pr in per_route.values()), 3),
        "runs": len(runs_out),
        "shared_km": round(sum(r["length_km"] for r in runs_out), 3),
        "lines": sum(pr["lines"] for pr in per_route.values()),
        "unbaked_lines": unbaked_lines,
        "co2_lines_unbaked": sum(pr["co2_lines_unbaked"] for pr in per_route.values()),
    }
    notes = []
    if not per_route:
        notes.append("No approved volume in this month.")
    elif not runs_out:
        if not stored_runs(leg):
            notes.append("No shared road sections are indexed: the routes are not baked, "
                         "or the index has not been rebuilt.")
        else:
            notes.append("Approved volume this month runs on no shared road section.")
    if unbaked_lines:
        notes.append(f"{unbaked_lines} line(s) on routes that are not baked carry trips "
                     f"but no road section.")
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
                 "figure. `trips` is the Dashboard's rounded-up count, shown beside it.",
        "co2_basis": "CO2e on a section = Σ each route's month CO2e (routed km × the vehicle's "
                     "kg CO2e/km, both legs) × section length / the route's two-way length "
                     "(loaded + baked return): the carbon emitted on the section.",
        "runs": runs_out,
        "totals": totals,
        "notes": notes,
        # the Carbon page's stamp, read from carbon.py (deferred: carbon imports network,
        # which imports this module) — a CO2e figure a person reads is an estimate from the
        # plan and the feed says so beside it, in the Carbon page's own words
        "carbon": {
            "stamp": _carbon_stamp(),
            "rule": "CO₂e = routed km × the vehicle's kg CO₂e/km, approved plan only; a section's "
                    "share = that route's month CO₂e × section length ÷ that route's two-way length "
                    "(loaded + baked return).",
        },
    }
    if payload.get("co2_error"):
        out["co2_error"] = payload["co2_error"]
        notes.append("The carbon read failed, so every CO2e figure here is 0 — see co2_error.")
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
