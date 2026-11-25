"""
25 Nov 2026 (the Look-ahead rethink, task A, John's "Yes, as recommended" to Q1 to Q7): the week's list grouped by SITE.

ONE rule gives every forecast line its site, from its route's two ends and the types typed on Data → Locations:

    - the destination: a line sits under the place it delivers to;
    - the ORIGIN, direction "out", when the origin is one of the organisation's own places (a Compound, a Site or a
      Stockpile: `network._role_for` already reads those three as the scheme's own) and the destination is not one
      (muck away: a line taking material out of a site sits under the site it leaves);
    - the destination when both ends are the organisation's own (Q2: a line between two of its sites is listed ONCE,
      under the site that receives it, so its loads are never counted twice).

No new data and no tick on a location (Q1). The sites are listed in the order of Data → Locations (Q3: the locations
read ORDER BY id, as `network.locations_geojson` lists them), never flagged first or busiest first.

`stamp()` puts `site` on any row that has a `route_id` (the commit week's lines, the Account rows, the Horizon rows);
`roll_up()` adds the commit week's lines up by site (`commit.sites`): each site's line keys, its totals a day and for
the week in tonnes, loads and lorries (everything through the gate, in and out together), the part going out apart, and
its team when every line is one team's. Nothing here decides a status word: the page's `laStatus`, `LA_FLAG_RANK` and
`LINE_FLAG_LABEL` stay the only source of one. A read only: one locations query a page, no fetch, no write.
"""
import db
import network

OWN_TYPES = ("compound", "site", "stockpile")


def _key(line):
    """The page's own line key (`lineKeyOf` in frontend/index.html): route|discipline|section|month."""
    return "|".join([str(line.get("route_id") or ""), str(line.get("discipline") or ""),
                     str(line.get("section_id") or ""), str(line.get("month_index") if line.get("month_index") is not None else "")])


def places():
    """{location id: {id, name, type, own, order}} for the tenant, in the order of Data → Locations."""
    out = {}
    rows = db.query("SELECT id, name, loc_type FROM locations WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
    for i, r in enumerate(rows):
        typ = network.canonical_loc_type(r.get("loc_type"))
        out[r["id"]] = {"id": r["id"], "name": r.get("name") or "", "type": typ or "",
                        "own": (typ or "").strip().lower() in OWN_TYPES, "order": i}
    return out


def site_of(origin_id, dest_id, where):
    """The ONE rule. Returns {id, name, type, dir} or None when neither end is a known place."""
    o, d = where.get(origin_id), where.get(dest_id)
    if o and o["own"] and not (d and d["own"]):
        return {"id": o["id"], "name": o["name"], "type": o["type"], "dir": "out"}
    if d:
        return {"id": d["id"], "name": d["name"], "type": d["type"], "dir": "in"}
    if o:                       # a route whose destination is no longer a place: under where it starts, as delivered
        return {"id": o["id"], "name": o["name"], "type": o["type"], "dir": "in"}
    return None


def stamp(rows, routes, where):
    """Put `site` on every row with a `route_id` (lines, Account rows, Horizon rows). Mutates and returns `rows`."""
    for r in rows or []:
        rt = routes.get(r.get("route_id")) or {}
        r["site"] = site_of(rt.get("origin_id"), rt.get("dest_id"), where)
    return rows


def _num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def roll_up(lines, where):
    """
    The commit week's lines added up by site, in the order of Data → Locations. Each line must already carry `site`
    (stamp) and be decorated (`derived.decorate`: `days[].derived`, `week_derived`, `context`). A day's lorries add
    up the routed lines' lorries that day (as the page's own busiest-day figure does); the week's lorries are the site's
    busiest day. Lines with no site at all go last, under a site with `id` None.
    """
    groups = {}
    for line in lines or []:
        s = line.get("site")
        sid = s["id"] if s else None
        g = groups.get(sid)
        if g is None:
            p = where.get(sid) or {}
            g = groups[sid] = {"id": sid, "name": (s or {}).get("name") or "", "type": (s or {}).get("type") or "",
                               "order": p.get("order", 10 ** 6), "lines": [], "out_lines": 0, "ipts": set(),
                               "days": {}, "week": {"t": 0.0, "loads": 0, "lorries": 0},
                               "out_week": {"t": 0.0, "loads": 0, "lorries": 0}}
        out = bool(s and s.get("dir") == "out")
        g["lines"].append(_key(line))
        g["out_lines"] += 1 if out else 0
        ctx = line.get("context") or {}
        g["ipts"].add(ctx.get("ipt") or line.get("ipt") or "")
        baked = bool(ctx.get("baked"))
        for d in line.get("days") or []:
            f = d.get("derived") or {}
            day = g["days"].setdefault(d.get("day_date"), {"t": 0.0, "loads": 0, "lorries": 0,
                                                         "out_t": 0.0, "out_loads": 0, "out_lorries": 0})
            t, n, v = _num(f.get("tonnes")), int(f.get("trips") or 0), (int(f.get("vehicles") or 0) if baked else 0)
            day["t"] += t
            day["loads"] += n
            day["lorries"] += v
            if out:
                day["out_t"] += t
                day["out_loads"] += n
                day["out_lorries"] += v
        wk = line.get("week_derived") or {}
        g["week"]["t"] += _num(wk.get("tonnes"))
        g["week"]["loads"] += int(wk.get("trips") or 0)
        if out:
            g["out_week"]["t"] += _num(wk.get("tonnes"))
            g["out_week"]["loads"] += int(wk.get("trips") or 0)
    res = []
    for g in sorted(groups.values(), key=lambda x: (x["order"], x["name"])):
        for day in g["days"].values():
            day["t"] = round(day["t"], 3)
            day["out_t"] = round(day["out_t"], 3)
        g["week"]["t"] = round(g["week"]["t"], 3)
        g["out_week"]["t"] = round(g["out_week"]["t"], 3)
        g["week"]["lorries"] = max([d["lorries"] for d in g["days"].values()] or [0])
        g["out_week"]["lorries"] = max([d["out_lorries"] for d in g["days"].values()] or [0])
        ipts = g.pop("ipts")
        g["ipt"] = (next(iter(ipts)) or None) if len(ipts) == 1 else None
        g.pop("order")
        res.append(g)
    return res
