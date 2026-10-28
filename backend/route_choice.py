"""
28 Oct 2026 (task 0c, the user: "Will the geofenced areas along a route divert to the alternative route
automatically?"). Which stored option a route uses on a given day, and why.

Before this, a zone with "Affects routing" shaped only the lines of the Route all that ran while it was in force
(network.active_avoid took the zones in force on the day of the bake), and those lines were then used for every
month. Now:

  * the MAIN line (alt_index 0) avoids only routing zones with no dates at all (network.active_avoid);
  * a DATED routing zone gives each route whose main line crosses it, for the zone's own dates only, the stored
    option that misses it (HERE's 1, 2, or a way round baked for it, alt_index >= WAY_ROUND_BASE). These are
    the 'zone' rows of the route_choice table, worked out by refresh_zones() from the zones and the stored lines
    (geometry only: never a HERE call) and rewritten whole each time;
  * readers ask alt_on() (one day) or mix() (a set of days: a month, a week) and nothing else.

The table is shared with 0d (peak hours): a 'peak' row carries hours_from / hours_to and stays 'offered' until a
planner accepts it. A zone row beats a peak row (a closed road is closed at every hour).

Statuses of a zone row, each for a run of dates on one (route, lorry type, leg):
  in_use        the option in alt_index is used on those days
  needs_route   no stored option misses the zone(s): the main line is used and the screens / Look-ahead say so,
                with "Find a way round" (network.bake_way_round) offered
  no_way_round  a way round was baked and HERE's line still crosses the zone: the main line is used, flagged
  declined      the planner pressed "Keep the main route" (a 'keep_main' row): the main line, flagged

Days: a month's figures weigh each option by its share of the month's WORKING days (Mon–Fri; bank holidays are
not taken off), the user's Q2 answer of 28 Oct.
"""
import datetime
import json

import db
import zones

#: alt_index of the first way round baked for a dated zone; HERE's own ranking stays below it (0..ALTERNATIVES-1)
WAY_ROUND_BASE = 10

#: statuses on which the main line is used although a zone in force crosses it (the Look-ahead flags them)
PROBLEM = ("needs_route", "no_way_round", "declined")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _d(v):
    """An ISO date string -> date, or None."""
    if not v:
        return None
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _iso(d):
    return d.isoformat() if d else None


def _line_of(raw):
    try:
        c = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return c if isinstance(c, list) and len(c) >= 2 else None


# --------------------------------------------------------------------------- #
#  The zones that divert                                                      #
# --------------------------------------------------------------------------- #
def dated_zones():
    """Active zones with Affects routing, a drawn shape, not a haul road, and at least one date."""
    try:
        zs = zones.list_zones(include_inactive=False)
    except Exception:
        return []
    return [z for z in zs if z["affects_routing"] and z["geometry"] and z["kind"] != zones.HAUL_KIND
            and (zones._clean_date(z.get("starts_on")) or zones._clean_date(z.get("ends_on")))]


def _intervals(zs):
    """
    [(start, end, [zone, …])]: the programme cut at every dated zone's start and end, keeping only the runs of
    days in which at least one zone is in force. start / end are dates, None = open (before the first / after
    the last boundary). Inside one run the set of zones in force does not change.
    """
    pts = set()
    for z in zs:
        s, e = _d(z.get("starts_on")), _d(z.get("ends_on"))
        if s:
            pts.add(s)
        if e:
            pts.add(e + datetime.timedelta(days=1))
    pts = sorted(pts)
    bounds = [None] + pts + [None]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        end = b - datetime.timedelta(days=1) if b else None
        rep = a or end
        if rep is None:
            continue
        active = [z for z in zs if zones.applies_on(z, rep.isoformat())]
        if active:
            out.append((a, end, active))
    return out


def _stored_lines():
    """{(route, profile, leg): {alt: {"line", "km", "hr", "avoids"}}} for every stored line with a geometry."""
    try:
        rows = db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry, distance_km, duration_hr, avoids "
                        "FROM route_geometry WHERE tenant_id = ? AND geometry IS NOT NULL", (db.current_tenant(),))
    except Exception:
        return {}
    out = {}
    for r in rows:
        line = _line_of(r["geometry"])
        if not line:
            continue
        out.setdefault((r["route_id"], r["vehicle_profile"], r["leg"]), {})[int(r["alt_index"] or 0)] = {
            "line": line, "km": float(r["distance_km"] or 0), "hr": float(r["duration_hr"] or 0),
            "avoids": [x for x in (r.get("avoids") or "").split(",") if x]}
    return out


def _keep_main_rules():
    """{(route_id, zone_id): vehicle_profile or None} from the planner's 'Keep the main route' rows."""
    try:
        rows = db.query("SELECT route_id, vehicle_profile, reason_ref FROM route_choice WHERE tenant_id = ? "
                        "AND status = 'keep_main'", (db.current_tenant(),))
    except Exception:
        return {}
    return {(r["route_id"], r["reason_ref"]): r.get("vehicle_profile") for r in rows}


def work_out(zs=None, lines=None, keep=None):
    """
    The zone rows refresh_zones() would write, as dicts, without writing them. Pure: the stored lines and the
    zones in, rows out. For each (route, lorry type, leg) whose MAIN line crosses a dated zone in a run of days:
    the shortest stored option that misses every routing zone in force then (the user's Q3 answer: shortest,
    fewer road miles), else needs_route / no_way_round; 'keep_main' rules turn a run to declined.
    """
    zs = dated_zones() if zs is None else zs
    lines = _stored_lines() if lines is None else lines
    keep = _keep_main_rules() if keep is None else keep
    runs = _intervals(zs)
    if not runs:
        return []
    hit_cache = {}

    def hits(key, alt, z):
        k = (key, alt, z["id"])
        if k not in hit_cache:
            hit_cache[k] = zones.line_hits_geometry(lines[key][alt]["line"], z["geometry"])
        return hit_cache[k]

    out = []
    for key in sorted(lines):
        opts = lines[key]
        if 0 not in opts:
            continue
        rid, prof, leg = key
        segs = []
        for a, end, active in runs:
            crossing = [z for z in active if hits(key, 0, z)]
            if not crossing:
                continue
            ids = sorted(z["id"] for z in crossing)
            if any((rid, zid) in keep and keep[(rid, zid)] in (None, prof) for zid in ids):
                alt, status = 0, "declined"
            else:
                cands = [alt for alt in opts if alt != 0 and not any(hits(key, alt, z) for z in active)]
                if cands:
                    alt = min(cands, key=lambda x: (opts[x]["km"], opts[x]["hr"], x))
                    status = "in_use"
                else:
                    tried = [x for x in opts if x >= WAY_ROUND_BASE and set(ids) <= set(opts[x]["avoids"])]
                    alt, status = 0, ("no_way_round" if tried else "needs_route")
            segs.append([a, end, alt, status, ids])
        # one row per run of touching days with the same option, status and zones
        merged = []
        for s in segs:
            if (merged and merged[-1][1] and s[0] and merged[-1][1] + datetime.timedelta(days=1) == s[0]
                    and merged[-1][2:] == s[2:]):
                merged[-1][1] = s[1]
            else:
                merged.append(list(s))
        for a, end, alt, status, ids in merged:
            km0 = opts[0]["km"]
            out.append({
                "id": f"Z:{rid}:{prof}:{leg}:{_iso(a) or 'start'}",
                "route_id": rid, "vehicle_profile": prof, "leg": leg, "alt_index": alt,
                "starts_on": _iso(a), "ends_on": _iso(end), "hours_from": None, "hours_to": None,
                "reason_kind": "zone", "reason_ref": ",".join(ids), "status": status, "source": "auto",
                "km_delta": (round(opts[alt]["km"] - km0, 3) if status == "in_use" else None)})
    return out


def refresh_zones():
    """
    Rewrite the zone rows from the dated zones and the stored lines. Run after a zone is saved / deleted, after a
    route is routed again and after a way round is baked. Geometry only — never a HERE call. Returns a summary.
    """
    rows = work_out()
    try:
        before = {r["route_id"] for r in db.query(
            "SELECT DISTINCT route_id FROM route_choice WHERE tenant_id = ? AND status = 'in_use' AND alt_index <> 0",
            (db.current_tenant(),))}
        db.execute("DELETE FROM route_choice WHERE tenant_id = ? AND reason_kind = 'zone' AND source = 'auto'",
                   (db.current_tenant(),))
    except Exception as e:
        print("route_choice: table not ready:", str(e)[:120])
        return {"rows": 0}
    now = _now()
    for r in rows:
        db.execute(
            "INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, "
            "hours_from, hours_to, reason_kind, reason_ref, status, source, km_delta, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), r["id"], r["route_id"], r["vehicle_profile"], r["leg"], r["alt_index"],
             r["starts_on"], r["ends_on"], None, None, "zone", r["reason_ref"], r["status"], "auto",
             r["km_delta"], now, now))
    # the lorry limits are checked on the options in use as well as the main line (limits.check_route)
    try:
        import limits
        touched = sorted({r["route_id"] for r in rows if r["status"] == "in_use" and r["alt_index"]} | set(before))
        if touched:                      # an empty list would mean "every route" to store_checks
            limits.store_checks(touched)
    except Exception as e:
        print("route_choice: lorry limits not re-checked:", str(e)[:120])
    return summary(rows)


def refresh_quietly(why):
    """refresh_zones() for a writer that must not fail because of it (a bake, a zone save)."""
    try:
        return refresh_zones()
    except Exception as e:
        print(f"route_choice: not refreshed after {why}:", str(e)[:160])
        return None


# --------------------------------------------------------------------------- #
#  Readers                                                                     #
# --------------------------------------------------------------------------- #
def _all_rows():
    try:
        return db.query("SELECT * FROM route_choice WHERE tenant_id = ? ORDER BY route_id, starts_on",
                        (db.current_tenant(),))
    except Exception:
        return []


def _rows_by_route():
    """{route_id: [row, …]} — one read per data version (read_cache), so a month read over 60 months asks once."""
    try:
        import read_cache
        return read_cache.cached("route_choice", "rows", _build_by_route)
    except Exception:
        return _build_by_route()


def _build_by_route():
    out = {}
    for r in _all_rows():
        if r.get("status") == "keep_main":
            continue
        out.setdefault(r["route_id"], []).append(r)
    return out


def _applies(row, profile, leg, day, hour=None):
    if row.get("vehicle_profile") not in (None, "", profile):
        return False
    if row.get("leg") not in (None, "", leg):
        return False
    s, e = _d(row.get("starts_on")), _d(row.get("ends_on"))
    if s and day < s:
        return False
    if e and day > e:
        return False
    hf, ht = row.get("hours_from"), row.get("hours_to")
    if hf or ht:
        if hour is None:
            return False          # an hours row never decides a whole day
        hhmm = f"{int(hour):02d}:00" if not isinstance(hour, str) else hour
        if (hf and hhmm < hf) or (ht and hhmm >= ht):
            return False
    return True


def choice_on(route_id, profile, leg, day, hour=None, rows=None):
    """The route_choice row that decides this day (a zone row before a peak row), or None."""
    rows = (_rows_by_route() if rows is None else rows).get(route_id) or []
    day = _d(day)
    if not rows or day is None:
        return None
    best = None
    for r in rows:
        if r.get("reason_kind") == "peak" and r.get("status") != "in_use":
            continue                                     # 0d: an offer changes nothing until accepted
        if not _applies(r, profile, leg, day, hour):
            continue
        if best is None or (best.get("reason_kind") != "zone" and r.get("reason_kind") == "zone"):
            best = r
    return best


def alt_on(route_id, profile, leg, day, hour=None, rows=None):
    """The alt_index used on this day: the row's option when it is in use, else the main line (0)."""
    r = choice_on(route_id, profile, leg, day, hour, rows)
    return int(r["alt_index"]) if r and r.get("status") == "in_use" else 0


def has_rows(route_id, rows=None):
    return bool((_rows_by_route() if rows is None else rows).get(route_id))


def working_days(dates):
    return [d for d in dates if d.weekday() < 5]


def month_days(month_index):
    import weeks
    y, m = weeks._month_of(month_index)
    d = datetime.date(y, m, 1)
    out = []
    while d.month == m:
        out.append(d)
        d += datetime.timedelta(days=1)
    return working_days(out)


def week_days(month_index, week_index):
    import weeks
    mon, sun = weeks.week_span(month_index, week_index)
    return working_days([mon + datetime.timedelta(days=i) for i in range(7)])


#: the months months_of() lists for an open-ended run: the public map's horizon (main.MONTH_COUNT)
HORIZON_MONTHS = 60


def months_of(starts_on, ends_on, horizon=HORIZON_MONTHS):
    """The month indexes (1 = Jan of the start year) with at least one working day in [starts_on, ends_on]."""
    s, e = _d(starts_on), _d(ends_on)
    out = []
    for mi in range(1, int(horizon) + 1):
        days = month_days(mi)
        if not days:
            continue
        if (s is None or days[-1] >= s) and (e is None or days[0] <= e):
            if any((s is None or d >= s) and (e is None or d <= e) for d in days):
                out.append(mi)
    return out


def mix(route_id, profile, days, rows=None):
    """
    How a set of working days splits between options: {"pairs": [((loaded_alt, return_alt), share), …],
    "diverted": share of the days on any option but the main line, "zones": [zone ids that diverted],
    "problems": [{"zone": ids, "status": …, "from": iso, "to": iso}]} — problems are the days a zone in force
    crosses the line actually used. One pair of (0, 0) and nothing else when no row touches the route.
    """
    rows = _rows_by_route() if rows is None else rows
    days = list(days)
    if not days or not has_rows(route_id, rows):
        return {"pairs": [((0, 0), 1.0)], "diverted": 0.0, "zones": [], "problems": []}
    count, zs, probs = {}, set(), {}
    for day in days:
        cl = choice_on(route_id, profile, "loaded", day, rows=rows)
        cr = choice_on(route_id, profile, "return", day, rows=rows)
        la = int(cl["alt_index"]) if cl and cl.get("status") == "in_use" else 0
        ra = int(cr["alt_index"]) if cr and cr.get("status") == "in_use" else 0
        count[(la, ra)] = count.get((la, ra), 0) + 1
        for c in (cl, cr):
            if not c:
                continue
            if c.get("status") == "in_use":
                zs.update(x for x in (c.get("reason_ref") or "").split(",") if x)
            elif c.get("status") in PROBLEM:
                k = (c.get("reason_ref"), c.get("status"))
                p = probs.setdefault(k, {"zone": c.get("reason_ref"), "status": c.get("status"),
                                         "from": day.isoformat(), "to": day.isoformat()})
                p["to"] = day.isoformat()
    n = float(len(days))
    pairs = sorted(((k, v / n) for k, v in count.items()), key=lambda kv: kv[0])
    return {"pairs": pairs, "diverted": round(sum(v for k, v in pairs if k != (0, 0)), 4),
            "zones": sorted(zs), "problems": list(probs.values())}


# --------------------------------------------------------------------------- #
#  Screens                                                                     #
# --------------------------------------------------------------------------- #
def summary(rows=None):
    """{"rows", "by_zone": {zone: {"routes": [ids in use], "needs_route": [...], "no_way_round": [...],
    "declined": [...]}}} — route ids, each once per list."""
    rows = [r for r in (_all_rows() if rows is None else rows) if r.get("reason_kind") == "zone"]
    by = {}
    for r in rows:
        for zid in (r.get("reason_ref") or "").split(","):
            if not zid:
                continue
            b = by.setdefault(zid, {"routes": [], "needs_route": [], "no_way_round": [], "declined": []})
            lst = b["routes"] if r["status"] == "in_use" else b.get(r["status"])
            if lst is not None and r["route_id"] not in lst:
                lst.append(r["route_id"])
    for b in by.values():
        for k in b:
            b[k].sort()
    return {"rows": len(rows), "by_zone": by}


def periods(route_id=None):
    """The zone rows (and accepted / offered peak rows) for one route or all, with the zone's name — the Routes
    page's Diversions list. Grouped by (zone set, dates, status) across lorry types and legs, each group listing
    its legs; km_delta per group is the main lorry type's laden leg where there is one."""
    rows = [r for r in _all_rows() if r.get("status") != "keep_main" and (route_id is None or r["route_id"] == route_id)]
    names = {}
    try:
        names = {z["id"]: z.get("name") for z in zones.list_zones()}
    except Exception:
        pass
    keep = _keep_main_rules()
    groups = {}
    for r in rows:
        k = (r["route_id"], r.get("reason_kind"), r.get("reason_ref"), r.get("starts_on"), r.get("ends_on"),
             r.get("status") if r.get("status") != "in_use" else "in_use")
        g = groups.setdefault(k, {"route_id": r["route_id"], "reason_kind": r.get("reason_kind"),
                                  "zones": [x for x in (r.get("reason_ref") or "").split(",") if x],
                                  "starts_on": r.get("starts_on"), "ends_on": r.get("ends_on"),
                                  "status": r.get("status"), "legs": []})
        g["legs"].append({"vehicle_profile": r.get("vehicle_profile"), "leg": r.get("leg"),
                          "alt_index": r.get("alt_index"), "km_delta": r.get("km_delta")})
    out = []
    for g in groups.values():
        g["zone_names"] = [names.get(z) or z for z in g["zones"]]
        g["kept"] = any((g["route_id"], z) in keep for z in g["zones"])
        out.append(g)
    out.sort(key=lambda g: (g["route_id"], g["starts_on"] or "", g["status"]))
    return out


def keep_main(route_id, zone_id, keep=True, who=None):
    """The planner's "Keep the main route" (keep=True) for one route through one zone, or its undo. Then refresh."""
    rid = f"K:{route_id}:{zone_id}"
    db.execute("DELETE FROM route_choice WHERE tenant_id = ? AND id = ?", (db.current_tenant(), rid))
    if keep:
        now = _now()
        db.execute(
            "INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, reason_kind, "
            "reason_ref, status, source, decided_by, decided_at, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, NULL, 0, 'zone', ?, 'keep_main', 'planner', ?, ?, ?, ?)",
            (db.current_tenant(), rid, route_id, zone_id, who, now, now, now))
    return refresh_zones()


def needs_route(route_id=None):
    """[(route_id, profile, leg, [zone ids])] with no stored option that misses a zone in force: what "Find a way
    round" would bake, one HERE call each (+ one per haul road spliced on the leg)."""
    seen = {}
    for r in _all_rows():
        if r.get("status") != "needs_route" or (route_id and r["route_id"] != route_id):
            continue
        k = (r["route_id"], r["vehicle_profile"], r["leg"])
        ids = seen.setdefault(k, set())
        ids.update(x for x in (r.get("reason_ref") or "").split(",") if x)
    return [(k[0], k[1], k[2], sorted(v)) for k, v in sorted(seen.items())]
