"""
clp_doc_layers.py — the CLP document's §2.3 and §2.4 from what Wayscope already stores along the routes.
Wayscope, 30 Oct 2026 (task 4a, PR 2). Plan: notes/session-1030-clp-document.md §4 (not in git).

For one CLP (a set of locations and the routes with an end there, clp_doc.gather), it reads, never fetches:
  * the councils and highway authorities the routes run through (areas.area_load in the CLP's busiest month);
  * the stored lorry-limit and National Highways checks on those routes (limits / restrictions stored_checks);
  * the dated diversions on those routes (route_choice.periods);
  * the community considerations within the strip: 250 m of a route, 500 m of a site (community.STRIP_*), each with
    the route or site it is nearest and how far;
  * the police-reported injury collisions on and near each route (collisions.records / counts_for), five years.
Each part says when nothing is stored (never fetched) rather than printing a zero.

The strip is measured on the CLP's own routes (their main road route, both legs), not the whole scheme's: a school near
another site's route is not this plan's.
"""
import json
import math

import db

#: community kinds printed as a list of places in 2.4.2 (the rest are counted in 2.3.x)
PLACE_KINDS = ("schools", "hospitals", "health", "community", "sports")
MAX_PLACES = 40            # 2.4.2 lists the nearest; the rest are counted
LIMIT_SHOWN = ("exceeds", "at_limit", "unknown")


def _lines(route_ids):
    """[(route_id, [[lon, lat], …])] — each route's main road route (alt 0), both legs, every lorry type, once each."""
    import collisions
    import community
    out, seen = [], set()
    if not route_ids:
        return out
    marks = ",".join("?" for _ in route_ids)
    for r in db.query(f"SELECT route_id, geometry FROM route_geometry WHERE tenant_id = ? AND alt_index = 0 "
                      f"AND geometry IS NOT NULL AND route_id IN ({marks}) ORDER BY route_id, vehicle_profile, leg",
                      (db.current_tenant(), *route_ids)):
        coords = collisions._coords(r["geometry"])
        if len(coords) < 2:
            continue
        thin = community._thin(coords)
        sig = (r["route_id"], tuple((round(c[0], 3), round(c[1], 3)) for c in thin[:: max(1, len(thin) // 20)]))
        if sig in seen:
            continue
        seen.add(sig)
        out.append((r["route_id"], thin))
    return out


def _point_of(g):
    """A feature's representative point (lon, lat): a point itself, else the first vertex of a line or outline."""
    t, c = g.get("type"), g.get("coordinates")
    try:
        if t == "Point":
            return float(c[0]), float(c[1])
        if t == "LineString":
            return float(c[0][0]), float(c[0][1])
        if t == "MultiLineString":
            return float(c[0][0][0]), float(c[0][0][1])
        if t == "Polygon":
            return float(c[0][0][0]), float(c[0][0][1])
        if t == "MultiPolygon":
            return float(c[0][0][0][0]), float(c[0][0][0][1])
    except (TypeError, IndexError, ValueError):
        return None
    return None


def _vertices(g):
    t, c = g.get("type"), g.get("coordinates") or []
    if t == "Point":
        return [c]
    if t == "LineString":
        return c
    if t in ("MultiLineString", "Polygon"):
        return [p for part in c for p in part]
    if t == "MultiPolygon":
        return [p for poly in c for ring in poly for p in ring]
    return []


SAMPLE_M = 50.0            # a line or outline is measured every 50 m along it, not only at its vertices
MAX_SAMPLES = 400          # ...spread further apart on a very long one


def _samples(vs):
    """Points along the feature's vertices: each segment cut every SAMPLE_M (a cycle route crossing a route between two
    vertices 600 m apart is near it), at most about MAX_SAMPLES points."""
    pts = []
    for v in vs:
        try:
            pts.append((float(v[0]), float(v[1])))
        except (TypeError, ValueError, IndexError):
            continue
    if len(pts) < 2:
        return pts
    seg = []
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        kx = 111320.0 * math.cos(math.radians((a[1] + b[1]) / 2))
        d = math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * 110574.0)
        seg.append((a, b, d))
        total += d
    step = max(SAMPLE_M, total / MAX_SAMPLES)
    out = [pts[0]]
    for a, b, d in seg:
        k = max(1, int(math.ceil(d / step)))
        out += [(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k) for i in range(1, k + 1)]
    return out


def _nearest(index, g, site_names):
    """(where, metres) for the nearest of this CLP's routes or sites to the feature (sampled along it), else None."""
    best = None
    vs = _samples(_vertices(g))
    if not vs:
        return None
    bb = index.bbox            # the strip's own box: most of the scheme's features are nowhere near this plan's routes
    if (max(p[0] for p in vs) < bb[0] or min(p[0] for p in vs) > bb[2]
            or max(p[1] for p in vs) < bb[1] or min(p[1] for p in vs) > bb[3]):
        return None
    for lon, lat in vs:
        routes, sites = index.near(lon, lat)
        for k, d in routes.items():
            if best is None or d < best[1]:
                best = (k, d)
        for k, d in sites.items():
            if best is None or d < best[1]:
                best = (site_names.get(k, k), d)
    return best


def gather(data, area_month=None):
    """The layers part of the CLP's data: {councils, limits, closures, diversions, community, collisions}.
    area_month(month) -> areas.area_load(month, geometry=False) as the public map has it; the endpoint passes the
    copy the map already keeps in memory (31 Oct 2026: working it out again cost +22 MB a build), else it is read."""
    import collisions
    import community
    route_ids = [r["route_id"] for r in data["routes"]]
    sites = [s for s in data["sites"] if s.get("lat") is not None and s.get("lon") is not None]
    site_names = {s["id"]: s["name"] for s in sites}
    out = {"route_ids": route_ids}

    # ---- councils and highway authorities (the CLP's busiest month) -------------------------------------------- #
    councils = []
    pm = data["totals"]["peak_month"]
    if pm:
        try:
            import areas
            A = (area_month(pm) if area_month else None)                 or areas.area_load(pm, working_days=data["working_days"], geometry=False)
            names = {s["name"] for s in data["sites"]}
            ends = {}                              # a location's name -> this CLP's routes with an end there
            for r in data["routes"]:
                for nm in (r.get("from"), r.get("to")):
                    if nm:
                        ends.setdefault(nm, set()).add(r["route_id"])
            for a in A.get("areas") or []:
                held = set(a.get("sites") or [])
                # the roads clipped to the council (after a road-sections rebuild), plus every route with an end in it
                rs = sorted((set(a.get("routes") or []) & set(route_ids))
                            | {rid for nm in held for rid in ends.get(nm, ())})
                ss = sorted(held & names)
                if rs or ss:
                    councils.append({"name": a["name"], "tier": a.get("tier_words") or "",
                                     "highway_authority": a.get("highway_authority") or "", "routes": rs, "sites": ss})
        except Exception:                          # noqa: BLE001  no council boundaries imported
            councils = []
    out["councils"] = councils
    out["councils_month"] = pm

    # ---- lorry limits and National Highways checks -------------------------------------------------------------- #
    try:
        import limits
        lc = limits.stored_checks(route_ids)
    except Exception:                              # noqa: BLE001
        lc = {}
    lim_rows, within, checked = {}, 0, False
    for rid in route_ids:
        st = lc.get(rid) or {}
        if st.get("checked_at"):
            checked = True
        for h in st.get("hits") or []:
            if h.get("verdict") not in LIMIT_SHOWN:
                within += 1
                continue
            key = (h.get("headline") or h.get("kind") or "", h.get("verdict"))
            e = lim_rows.setdefault(key, {"what": key[0], "verdict": h.get("verdict"), "routes": set(),
                                          "lorries": set()})
            e["routes"].add(rid)
            if h.get("vehicle_label"):
                e["lorries"].add(h["vehicle_label"])
    order = {"exceeds": 0, "at_limit": 1, "unknown": 2}
    out["limits"] = {"checked": checked, "within": within,
                     "rows": [dict(e, routes=sorted(e["routes"]), lorries=sorted(e["lorries"]))
                              for e in sorted(lim_rows.values(), key=lambda e: (order[e["verdict"]], e["what"]))]}
    try:
        import restrictions
        rc = restrictions.stored_checks(route_ids)
    except Exception:                              # noqa: BLE001
        rc = {}
    cl_rows, cl_checked = {}, []
    for rid in route_ids:
        st = rc.get(rid) or {}
        if st.get("checked_at"):
            cl_checked.append(str(st["checked_at"]))
        for h in st.get("hits") or []:
            what = h.get("description") or h.get("headline") or h.get("what") or h.get("label") or ""
            e = cl_rows.setdefault(what, {"what": what, "severity": h.get("severity"), "routes": set()})
            e["routes"].add(rid)
    out["closures"] = {"checked": bool(cl_checked), "checked_at": max(cl_checked) if cl_checked else None,
                       "rows": [dict(e, routes=sorted(e["routes"])) for e in cl_rows.values()]}

    # ---- dated diversions ---------------------------------------------------------------------------------------- #
    divs = []
    try:
        import route_choice
        for g in route_choice.periods():
            if g["route_id"] in route_ids and g.get("reason_kind") == "zone" and g.get("status") in ("in_use", "offered"):
                divs.append({"route_id": g["route_id"], "zones": g.get("zone_names") or [], "from": g.get("starts_on"),
                             "to": g.get("ends_on"), "status": g.get("status"), "kept": bool(g.get("kept"))})
    except Exception:                              # noqa: BLE001  a database without the route choice table
        divs = []
    out["diversions"] = divs

    # ---- the strip: community considerations and collisions ----------------------------------------------------- #
    lines = _lines(route_ids)
    index = collisions.RouteIndex(lines, [(s["id"], s["name"], float(s["lon"]), float(s["lat"])) for s in sites],
                                  route_m=community.STRIP_ROUTE_M, site_m=community.STRIP_SITE_M)
    # 31 Oct 2026: only the places that touch the strip's own box are loaded (the scheme's others were read, kept and
    # then skipped one by one)
    feats = community.features(bbox=index.bbox) if index.bbox else []
    near = []
    for f in feats:
        g = f.get("geometry") or {}
        if not index.bbox:
            break
        p = _point_of(g)
        if p is None:
            continue
        hit = _nearest(index, g, site_names)
        if hit is None:
            continue
        pr = f["properties"]
        near.append({"kind": pr["kind"], "name": (pr.get("name") or "").strip(), "detail": pr.get("detail") or "",
                     "where": hit[0], "metres": int(round(hit[1])), "source_key": pr.get("source_key")})
    near.sort(key=lambda x: (x["metres"], x["kind"], x["name"]))
    by_kind = {}
    for x in near:
        by_kind.setdefault(x["kind"], []).append(x)
    places = [x for x in near if x["kind"] in PLACE_KINDS]
    labels = {k["key"]: k["label"] for k in community.KINDS}
    out["community"] = {
        "stored": bool(feats), "route_m": community.STRIP_ROUTE_M, "site_m": community.STRIP_SITE_M,
        "drawn_routes": sorted({k for k, _l in lines}),
        "counts": {k: len(v) for k, v in by_kind.items()}, "labels": labels,
        "places": places[:MAX_PLACES], "places_more": max(0, len(places) - MAX_PLACES),
        "stations": by_kind.get("stations", []), "bus_stops": len(by_kind.get("bus_stops", [])),
        "bus_stops_near_sites": sum(1 for x in by_kind.get("bus_stops", []) if x["where"] in site_names.values()),
        "cycle": sorted({x["name"] for x in by_kind.get("cycle", []) if x["name"]}),
        "cycle_unnamed": sum(1 for x in by_kind.get("cycle", []) if not x["name"]),
        "residential": len(by_kind.get("residential", [])),
        "credit": community.credit_line(sorted({x["source_key"] for x in near if x.get("source_key")})) if near else "",
    }

    st = collisions.status()
    coll = {"fetched": bool(st.get("fetched_at")), "period": st.get("period") or "", "rows": [], "sites": [],
            "credit": collisions.credit_line() if st.get("fetched_at") else ""}
    if coll["fetched"] and route_ids:
        all_recs = collisions.records()            # 31 Oct 2026: read once (was twice: by route, then all)
        recs = [c for c in all_recs if any(k in c["routes"] for k in route_ids)]
        for rid in route_ids:
            c = collisions.counts_for(recs, rid)
            coll["rows"].append({"route_id": rid, "on_all": c["on"]["all"], "on_ksi": c["on"]["ksi"],
                                 "near_all": c["near"]["all"], "near_ksi": c["near"]["ksi"],
                                 "near_vru": c["near"]["vru_any"], "near_goods": c["near"]["goods"]})
        for s in sites:
            ns = [c for c in all_recs if s["id"] in (c.get("sites") or {})]
            coll["sites"].append({"name": s["name"], "all": len(ns), "ksi": sum(1 for c in ns if c["ksi"])})
    out["collisions"] = coll
    return out


def summary_json(L):
    """A small JSON-safe digest (for the tests and, in PR 3, the issue record)."""
    return json.loads(json.dumps(L, default=list))
