"""
Route options compared (29 Oct 2026). John: "there must be some narrative on how HERE selects its routes safely … this
is a bit of a selling point if we can actually show that HERE chooses the safer / more sustainable route". HERE's own
documentation says only that its truck mode keeps to the lorry's legal and physical limits and prefers main roads to
residential streets and town centres (technical guide #t2-ranking). Whether that makes its choice safer for the people
along the road, or greener, is an empirical question; this module answers it for one tenant's routes, so a claim rests on
counts, never on a guess.

compare(profile) — for every route and every stored option HERE gave (alt_index 0-2; a way round a closed zone, 10+, is
left out: it is not HERE's choice between options), on that lorry type:
  * distance and minutes of the round trip (the pairing route_analysis costs), carbon a trip (the plan's own per-km
    figure), the busy-hour drive minutes at 08:00 and 17:00 when the busy-hour times are worked out;
  * collisions within collisions.ON_ROUTE_M of the option (both legs, every lorry type: its route key), all, killed or
    seriously injured, people walking, cycling or riding hurt badly, cyclists;
  * the community considerations near the option (NEAR_M by kind; an area counts when one of its outline points is that
    close; a point when it is), from the stored community layer. ⚠️ On live that layer is fetched along the main routes
    and diversions only (a wider fetch is too heavy for the deployment), so an alternative's counts there are UNDER-counted
    where it leaves the main route by more than 250 m; a fair count needs community.strip_from_db(all_options=True) run
    on a machine with more memory;
  * the laden leg's cycle-route stretches and meeting points and its left turns (the collision evidence's own rules).
summary(rows) — for each route with an alternative, HERE's first option against each alternative, kind by kind:
fewer / same / more. Counts only, never rates or a verdict; the words come from whoever reads the table.

WHAT IS NOT VERIFIED: the community layer is OpenStreetMap / GIAS / NaPTAN as fetched (it can be incomplete); collisions
are police-reported injury collisions, five final years; a count beside a road is not a risk.
"""
import json

import db
import collisions
import community
import network

PROFILE = "Artic Tipper (44t)"
MAX_HERE_ALT = 9                     # alt_index 10+ is a way round (route_choice.WAY_ROUND_BASE), not HERE's choice
NEAR_M = {"schools": 250, "hospitals": 250, "health": 250, "community": 250, "sports": 250, "stations": 250,
          "bus_stops": 100, "residential": 100}
KINDS = list(NEAR_M)
COLLISION_KINDS = ("collisions", "ksi", "vru_ksi", "cyclist")
COMPARE_KINDS = COLLISION_KINDS + tuple(KINDS) + ("left_turns", "cycle_meets", "km", "co2_kg")


def _points(g):
    t, c = (g or {}).get("type"), (g or {}).get("coordinates")
    if not c:
        return []
    if t == "Point":
        return [c[:2]]
    if t in ("LineString", "MultiPoint"):
        return [p[:2] for p in c]
    if t in ("Polygon", "MultiLineString"):
        return [p[:2] for ring in c for p in ring]
    if t == "MultiPolygon":
        return [p[:2] for poly in c for ring in poly for p in ring]
    return []


def compare(profile=PROFILE):
    index = collisions.index_from_db()
    tenant = db.current_tenant()
    routes = [r["id"] for r in db.query("SELECT id FROM routes WHERE tenant_id = ? ORDER BY id", (tenant,))]
    # the laden line of each option of this lorry type, for the cycle routes and the left turns
    laden = {}
    for g in db.query("SELECT route_id, alt_index, geometry FROM route_geometry WHERE tenant_id = ? AND vehicle_profile = ? "
                      "AND leg = 'loaded' AND geometry IS NOT NULL AND alt_index <= ?", (tenant, profile, MAX_HERE_ALT)):
        laden[(g["route_id"], int(g["alt_index"] or 0))] = collisions._coords(g["geometry"])
    keys = {collisions.route_key(r, a): (r, a) for (r, a) in laden}
    # collisions on each option: one pass over the stored records
    col = {k: {c: 0 for c in COLLISION_KINDS} for k in keys}
    for c in collisions.records():
        for k, d in (c.get("routes") or {}).items():
            if k in col and d <= collisions.ON_ROUTE_M:
                col[k]["collisions"] += 1
                col[k]["ksi"] += 1 if c["ksi"] else 0
                col[k]["vru_ksi"] += 1 if c.get("vru_ksi") else 0
                col[k]["cyclist"] += 1 if "cyclist" in (c.get("vru") or []) else 0
    # the community considerations near each option: one pass over the stored features
    com = {k: {kind: 0 for kind in KINDS} for k in keys}
    for f in community.features(KINDS):
        kind = f["properties"]["kind"]
        best = {}
        for p in _points(f.get("geometry")):
            near, _sites = index.near(p[0], p[1])
            for k, d in near.items():
                if k in com and (k not in best or d < best[k]):
                    best[k] = d
        for k, d in best.items():
            if d <= NEAR_M[kind]:
                com[k][kind] += 1
    cl = collisions.cycle_lines()
    grid = collisions._SegGrid(index, cl) if cl else None
    rows = []
    for rid in routes:
        a = network.route_analysis(rid, profiles=[profile])
        try:
            import hour_times
            a = hour_times.attach(a)
        except Exception:
            pass
        for r in sorted((x for x in (a.get("rows") or []) if x["alt_index"] <= MAX_HERE_ALT), key=lambda x: x["alt_index"]):
            alt = r["alt_index"]
            key = collisions.route_key(rid, alt)
            line = laden.get((rid, alt)) or []
            cyc = collisions.cycle_along(index, line, grid) if (grid is not None and len(line) >= 2) else None
            turns = collisions.left_turns(index, line, grid) if len(line) >= 2 else []
            hrs = r.get("hours") or {}
            drive = lambda h: (round((hrs[h] - r["turnaround_hr"]) * 60, 1) if hrs.get(h) is not None else None)
            rows.append(dict(
                {"route": rid, "alt": alt, "here_rank": alt + 1, "km": round(r["total_km"], 2),
                 "minutes": round((r["loaded_hr"] + r["return_hr"]) * 60, 1), "min_08": drive("08:00"),
                 "min_17": drive("17:00"), "co2_kg": r["co2_kg_per_trip"], "return_alt": r.get("return_alt_used"),
                 "left_turns": len(turns), "cycle_meets": (len(cyc["meets"]) if cyc else None),
                 "cycle_beside_km": (round(len(cyc["beside_m"]) * 10 / 1000, 2) if cyc else None)},
                **col.get(key, {c: 0 for c in COLLISION_KINDS}), **com.get(key, {k: 0 for k in KINDS})))
    meta = community.status()
    return {"profile": profile, "rows": rows, "summary": summary(rows), "near_m": NEAR_M, "on_route_m": collisions.ON_ROUTE_M,
            "community_fetched_at": (meta or {}).get("fetched_at"), "collisions_period": collisions.status().get("period")}


def summary(rows):
    """HERE's first option against each alternative of the same route, kind by kind: how many pairs the first option has
    FEWER, the SAME or MORE. A pair is one (route, alternative). Counts only."""
    by = {}
    for r in rows:
        by.setdefault(r["route"], {})[r["alt"]] = r
    pairs = [(opts[0], o) for rid, opts in sorted(by.items()) if 0 in opts for a, o in sorted(opts.items()) if a > 0]
    out = {"routes": len(by), "routes_with_alternatives": len({p[0]["route"] for p in pairs}), "pairs": len(pairs), "kinds": {}}
    for kind in COMPARE_KINDS:
        tally = {"fewer": 0, "same": 0, "more": 0, "total_first": 0, "total_alt": 0}
        for first, alt in pairs:
            f, o = first.get(kind), alt.get(kind)
            if f is None or o is None:
                continue
            tally["total_first"] += f
            tally["total_alt"] += o
            tally["fewer" if f < o else "more" if f > o else "same"] += 1
        tally["total_first"] = round(tally["total_first"], 1)
        tally["total_alt"] = round(tally["total_alt"], 1)
        out["kinds"][kind] = tally
    return out
