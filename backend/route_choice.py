"""
28 Oct 2026 (task 0c, the user: "Will the geofenced areas along a route divert to the alternative route
automatically?"). Which stored option a route uses on a given day, and why.

Before this, a zone with "Affects routing" shaped only the lines of the Route all that ran while it was in force
(network.active_avoid took the zones in force on the day of the bake), and those lines were then used for every
month. Now:

  * the MAIN line (alt_index 0) avoids only routing zones with no dates at all (network.active_avoid);
  * a DATED routing zone gives each route whose main line crosses it, for the zone's own dates only, the stored
    option that misses it (HERE's 1, 2, or a way round baked for it, alt_index >= WAY_ROUND_BASE). Which one: see
    pick_key() (11 Nov 2026: no lorry limit below the lorry first, then the quickest; it was the shortest). These are
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

5 Nov 2026 (task 0d-2, the user's Q1-Q20, all as recommended): a planner can USE a collision busy-hours offer
(collisions.busy_offers): a 'peak' row per (route, lorry type, leg) that has its own Alt N, hours_from / hours_to = the
offered band, days '1111100' (weekdays), source 'planner'. Statuses of a peak row:
  in_use     lorries setting off in those hours take Alt N (a leg that SETS OFF in the hours: Q2)
  paused     a Route all changed Alt N's line since it was put in use (line_fp): the main line, until Use again (Q11)
  stopped    the planner pressed Stop
A zone row still beats a peak row (Q10). A day's figures give an in-use peak row the share of the route's open window
(collisions.gate_span: earliest gate open to latest shut at either end) its hours cover (Q4) — mix(peaks=True), which
derived.cycle_for reads; month_weights (the shared-road index and the council clip) and periods (the Diversions list)
stay on the zone rows (Q9).
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


def _below_keys(line, profile, leg, lims):
    """The stored lorry limits this line runs along (or passes, for a point limit) that are BELOW this lorry on this leg
    (limits.assess verdict "exceeds", the Route sheet's "is over"), as a set of (source, ext_id, kind): each limit once.
    A limit "except for access" counts: whether this site is one is for a person to check, as the sheet says."""
    if not lims or not line:
        return set()
    import limits
    seen = set()
    for L, _point, _along in limits._matches(line, lims):
        k = (L.get("source"), L.get("ext_id"), L.get("kind"))
        if k not in seen and limits.assess(L, profile, leg)["verdict"] == "exceeds":
            seen.add(k)
    return seen


def limits_below(line, profile, leg, lims):
    """How many stored lorry limits below this lorry the line meets (_below_keys). Geometry only, no outside call."""
    return len(_below_keys(line, profile, leg, lims))


def limits_added(line, main_line, profile, leg, lims):
    """
    11 Nov 2026 (CLOCS B-F3 chip, John: "Yes, only new limits"): how many limits below this lorry a diversion meets that
    the route's own MAIN line (alt 0) of the same lorry type and leg does not. The same stored limit (source, ext_id,
    kind) is matched against each line separately by the one matching rule (limits._matches) and judged for that leg's
    weight (an empty lorry coming back is lighter); "adds" = on the diversion, not on the main line. A limit both pass is
    not new: the main route meets it anyway. The picker still uses limits_below (any limit, not only new ones).
    """
    return len(_below_keys(line, profile, leg, lims) - _below_keys(main_line, profile, leg, lims))


def pick_key(opt, below):
    """
    The order a dated zone's diversion is picked in, among the stored options that miss every routing zone in force.
    John, 11 Nov 2026 (CLOCS card B-F3, "No limit, then quickest"): REVERSES the user's Q3 answer of 28 Oct ("shortest,
    fewer road miles"). Picked on distance alone, a diversion could come out SHORTER than the main route and run on
    weight-limited roads (on live R002's diversion, its return leg, was 4.8 mi shorter). Now:
      1. an option with no lorry limit below this lorry (limits_below == 0) before one with any;
      2. then the quickest: the stored duration_hr of that leg, which HERE gave for a lorry of that size setting off at
         the pinned bake time (here_routing.bake_departure_time: the next Tuesday at least two days ahead, 10:00 in the
         tenant's time zone); an option
         with no stored time (0) goes after every timed one;
      3. on a tie, the shorter (distance_km), then the lower alt_index (HERE's own order, then the ways round).
    Where every option has a limit below the lorry, the quickest of them is used and its limits are shown (periods()).
    """
    hr = float(opt.get("hr") or 0)
    return (below > 0, hr <= 0, hr, float(opt.get("km") or 0))


def _load_limits():
    """The stored lorry limits for the picker; [] where none are held (every option then counts 0 below)."""
    try:
        import limits
        return limits.stored() or []
    except Exception as e:
        print("route_choice: lorry limits not read:", str(e)[:120])
        return []


def work_out(zs=None, lines=None, keep=None, lims=None):
    """
    The zone rows refresh_zones() would write, as dicts, without writing them. Pure: the stored lines, the zones and
    the stored lorry limits in, rows out. For each (route, lorry type, leg) whose MAIN line crosses a dated zone in a
    run of days: the stored option that misses every routing zone in force then, picked by pick_key() (11 Nov 2026: no
    lorry limit below the lorry first, then the quickest; it was the shortest, the user's Q3 answer of 28 Oct), else
    needs_route / no_way_round; 'keep_main' rules turn a run to declined.
    """
    zs = dated_zones() if zs is None else zs
    lines = _stored_lines() if lines is None else lines
    keep = _keep_main_rules() if keep is None else keep
    runs = _intervals(zs)
    if not runs:
        return []
    lims = _load_limits() if lims is None else lims
    hit_cache, below_cache = {}, {}

    def hits(key, alt, z):
        k = (key, alt, z["id"])
        if k not in hit_cache:
            hit_cache[k] = zones.line_hits_geometry(lines[key][alt]["line"], z["geometry"])
        return hit_cache[k]

    def below(key, alt):
        k = (key, alt)
        if k not in below_cache:
            below_cache[k] = limits_below(lines[key][alt]["line"], key[1], key[2], lims)
        return below_cache[k]

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
                    alt = min(cands, key=lambda x: pick_key(opts[x], below(key, x)) + (x,))
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
        _prev = db.query("SELECT route_id, vehicle_profile, leg, alt_index FROM route_choice WHERE tenant_id = ? "
                         "AND status = 'in_use' AND alt_index <> 0 AND reason_kind = 'zone' AND source = 'auto'",
                         (db.current_tenant(),))
        before = {r["route_id"] for r in _prev}
        before_use = {(r["route_id"], r["vehicle_profile"], r["leg"], int(r["alt_index"])) for r in _prev}
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
    # 29 Oct 2026 (task 0c, PR B): the shared-road index and the council clip know the options in use — rebuilt when
    # that set changed (a zone save, a way round, Keep the main route); a bake rebuilds them itself at its end
    after = {(r["route_id"], r["vehicle_profile"], r["leg"], r["alt_index"]) for r in rows
             if r["status"] == "in_use" and r["alt_index"]}
    if after != before_use:
        try:
            import road_sections
            road_sections._rebuild_quietly("diversions changed")
        except Exception as e:
            print("route_choice: shared roads not rebuilt:", str(e)[:120])
    # the lorry limits are checked on the options in use as well as the main line (limits.check_route)
    try:
        import limits
        touched = sorted({r["route_id"] for r in rows if r["status"] == "in_use" and r["alt_index"]} | set(before))
        if touched:                      # an empty list would mean "every route" to store_checks
            limits.store_checks(touched)
    except Exception as e:
        print("route_choice: lorry limits not re-checked:", str(e)[:120])
    try:
        check_busy()                     # 5 Nov 2026 (task 0d-2, Q11): a changed Alt N pauses its busy-hours use
    except Exception as e:
        print("route_choice: busy-hours uses not checked:", str(e)[:120])
    return summary(rows)


def preview():
    """
    11 Nov 2026 (CLOCS card B-F3): what refresh_zones() would change now, WITHOUT writing: per (route, lorry, leg, from)
    the option stored in use and the one the rule picks, with each one's distance and time against the main line and its
    lorry limits below the lorry. The admin read GET /api/admin/route-diversions/preview; POST …/refresh applies it.
    """
    new = {r["id"]: r for r in work_out()}
    try:
        old = {r["id"]: r for r in db.query("SELECT * FROM route_choice WHERE tenant_id = ? AND reason_kind = 'zone' "
                                            "AND source = 'auto'", (db.current_tenant(),))}
    except Exception:
        old = {}
    lines, lims = _stored_lines(), _load_limits()

    def figs(r):
        if not r:
            return None
        key = (r["route_id"], r["vehicle_profile"], r["leg"])
        opts, alt = lines.get(key) or {}, int(r.get("alt_index") or 0)
        o, m = opts.get(alt), opts.get(0)
        if not o or not m:
            return {"alt_index": alt, "status": r.get("status")}
        return {"alt_index": alt, "status": r.get("status"), "km_delta": round(o["km"] - m["km"], 3),
                "hr_delta": round(o["hr"] - m["hr"], 4), "limits_below": limits_below(o["line"], key[1], key[2], lims),
                "limits_new": limits_added(o["line"], m["line"], key[1], key[2], lims)}

    out = []
    for i in sorted(set(old) | set(new)):
        a, b = old.get(i), new.get(i)
        if a and b and int(a.get("alt_index") or 0) == int(b.get("alt_index") or 0) and a.get("status") == b.get("status"):
            continue
        r = b or a
        out.append({"id": i, "route_id": r["route_id"], "vehicle_profile": r["vehicle_profile"], "leg": r["leg"],
                    "starts_on": r.get("starts_on"), "ends_on": r.get("ends_on"), "now": figs(a), "rule": figs(b)})
    return {"changes": out, "rows_now": len(old), "rows_rule": len(new), "limits_held": len(lims)}


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


_MEMO = {}


def _rows_by_route():
    """{route_id: [row, …]} — one read per tenant and data version, so a month read over 60 months asks once. Its own
    memo, not read_cache: read_cache counts its builds for the council read, and this is read inside that build."""
    key = (db.current_tenant(), db.data_version())
    hit = _MEMO.get(key[0])
    if hit and hit[0] == key[1]:
        return hit[1]
    rows = _build_by_route()
    _MEMO[key[0]] = (key[1], rows)
    return rows


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
    # `days`: a seven-character Mon..Sun mask like the gates' open days ('1111100' = weekdays), NULL = every day (0d's peaks)
    mask = (row.get("days") or "").strip()
    if len(mask) == 7 and mask[day.weekday()] != "1":
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


def mix(route_id, profile, days, rows=None, peaks=True):
    """
    How a set of working days splits between options: {"pairs": [((loaded_alt, return_alt), share), …],
    "diverted": share of the days on any option but the main line, "zones": [zone ids that diverted],
    "problems": [{"zone": ids, "status": …, "from": iso, "to": iso}]} — problems are the days a zone in force
    crosses the line actually used. One pair of (0, 0) and nothing else when no row touches the route.

    5 Nov 2026 (task 0d-2): with `peaks` (the default), on a day no zone row decides a leg, an in-use busy-hours row
    takes the share of the route's open window its hours cover (busy_share), the rest of the day the main line. The
    result then carries "busy": {"share": of the trips, "options": [{"alt", "from", "to", "share"}]}; "diverted" stays
    the zones' share only.
    """
    rows = _rows_by_route() if rows is None else rows
    days = list(days)
    if not days or not has_rows(route_id, rows):
        return {"pairs": [((0, 0), 1.0)], "diverted": 0.0, "zones": [], "problems": []}
    count, zs, probs, busy = {}, set(), {}, {}
    span = busy_span(route_id) if peaks and _has_peak(route_id, rows) else None
    for day in days:
        cl = choice_on(route_id, profile, "loaded", day, rows=rows)
        cr = choice_on(route_id, profile, "return", day, rows=rows)
        la = int(cl["alt_index"]) if cl and cl.get("status") == "in_use" else 0
        ra = int(cr["alt_index"]) if cr and cr.get("status") == "in_use" else 0
        left = 1.0
        if span:
            bands = {}
            for leg, decided in (("loaded", cl), ("return", cr)):
                if decided is not None:
                    continue                             # Q10: a zone row decides this leg on this day
                for r in _peaks_on(route_id, profile, leg, day, rows):
                    bands.setdefault((r["hours_from"], r["hours_to"]), {})[leg] = int(r["alt_index"])
            for (hf, ht), by_leg in sorted(bands.items()):
                f = min(left, busy_share(hf, ht, span))
                if f <= 0:
                    continue
                pair = (by_leg.get("loaded", la), by_leg.get("return", ra))
                count[pair] = count.get(pair, 0) + f
                left -= f
                alt = by_leg.get("loaded", by_leg.get("return"))
                busy[(alt, hf, ht)] = busy.get((alt, hf, ht), 0.0) + f
        count[(la, ra)] = count.get((la, ra), 0) + left
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
    pairs = sorted(((k, v / n) for k, v in count.items() if v > 1e-12), key=lambda kv: kv[0])
    busy_total = sum(busy.values()) / n
    out = {"pairs": pairs, "diverted": round(max(0.0, sum(v for k, v in pairs if k != (0, 0)) - busy_total), 4),
           "zones": sorted(zs), "problems": list(probs.values())}
    if busy:
        out["busy"] = {"share": round(busy_total, 4),
                       "options": [{"alt": a, "from": hf, "to": ht, "share": round(v / n, 4)}
                                   for (a, hf, ht), v in sorted(busy.items())]}
    return out


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
    rows = [r for r in _all_rows() if r.get("status") != "keep_main" and (route_id is None or r["route_id"] == route_id)
            and r.get("reason_kind") != "peak"]     # 5 Nov 2026 (0d-2): busy-hours roads are busy_uses(), not a diversion
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
    _leg_figures(groups.values())
    out = []
    for g in groups.values():
        g["zone_names"] = [names.get(z) or z for z in g["zones"]]
        g["kept"] = any((g["route_id"], z) in keep for z in g["zones"])
        out.append(g)
    out.sort(key=lambda g: (g["route_id"], g["starts_on"] or "", g["status"]))
    return out


def _leg_figures(groups):
    """
    11 Nov 2026 (CLOCS cards B-F3 / B-I2): each in-use leg of a diversion also carries hr_delta (the option's stored
    time less the main line's, hours), limits_below (the stored lorry limits below that lorry on the option, as the
    picker counts them) and limits_new (those its main line does not meet, limits_added: the Zones list's chip); both
    None where no limits are held at all, so nothing claims a check that was not made. Read only:
    nothing here writes, so the Zones list shows what live has in use, whichever rule picked it.
    """
    want = {(g["route_id"], l.get("vehicle_profile"), l.get("leg"), int(l.get("alt_index") or 0))
            for g in groups for l in g["legs"] if g.get("status") == "in_use" and l.get("alt_index")}
    if not want:
        return
    rids = sorted({w[0] for w in want})
    lims = _load_limits()
    try:                                 # times for every option (no line text); a line only where limits are held
        rows = db.query("SELECT route_id, vehicle_profile, leg, alt_index, duration_hr FROM route_geometry "
                        f"WHERE tenant_id = ? AND route_id IN ({','.join('?' * len(rids))})",
                        (db.current_tenant(), *rids))
        fig = {(r["route_id"], r["vehicle_profile"], r["leg"], int(r["alt_index"] or 0)): dict(r) for r in rows}
        if lims:
            for r in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry FROM route_geometry "
                              f"WHERE tenant_id = ? AND route_id IN ({','.join('?' * len(rids))})",
                              (db.current_tenant(), *rids)):
                k = (r["route_id"], r["vehicle_profile"], r["leg"], int(r["alt_index"] or 0))
                if (k in want or (k[3] == 0 and any(w[:3] == k[:3] for w in want))) and k in fig:
                    fig[k]["geometry"] = r["geometry"]
    except Exception:
        return
    for g in groups:
        if g.get("status") != "in_use":
            continue
        for l in g["legs"]:
            k = (g["route_id"], l.get("vehicle_profile"), l.get("leg"), int(l.get("alt_index") or 0))
            if k not in want:
                continue
            a, m = fig.get(k), fig.get(k[:3] + (0,))
            if a and m and a.get("duration_hr") and m.get("duration_hr"):
                l["hr_delta"] = round(float(a["duration_hr"]) - float(m["duration_hr"]), 4)
            al = _line_of(a.get("geometry")) if a else None
            ml = _line_of(m.get("geometry")) if m else None
            l["limits_below"] = limits_below(al, k[1], k[2], lims) if lims else None
            l["limits_new"] = limits_added(al, ml, k[1], k[2], lims) if lims and al and ml else None


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


# --------------------------------------------------------------------------- #
#  29 Oct 2026 (task 0c, PR B): the readers that follow the month — shared     #
#  roads, councils, the bulletin / CLP / export maps, the Simulation and the  #
#  collision / community strips                                               #
# --------------------------------------------------------------------------- #
def leg_key(route_id, alt):
    """The key a stored option goes by in the indexes: the route's own id for its main line, "R012@1" for an option
    (collisions.route_key's form, so one key names one stored line everywhere)."""
    return str(route_id) if not int(alt or 0) else f"{route_id}@{int(alt)}"


def base_of(key):
    """The route id of an index key ("R012@1" → "R012")."""
    return str(key).split("@", 1)[0]


def in_use(profile=None, rows=None, kinds=("zone", "peak")):
    """{(route_id, profile, leg): {alt, …}} — the stored options a zone row has IN USE (alt ≠ 0) on some day; with
    `profile`, only the rows that apply to it (a row for every lorry type, or that one). 5 Nov 2026 (task 0d-2, Q9):
    `kinds` — the collision and community strips take the busy-hours roads too (the default); the shared-road index
    and the council clip pass ("zone",)."""
    rows = _rows_by_route() if rows is None else rows
    out = {}
    for rid, rs in rows.items():
        for r in rs:
            if r.get("status") != "in_use" or not int(r.get("alt_index") or 0):
                continue
            if r.get("reason_kind") not in kinds:
                continue
            prof = r.get("vehicle_profile")
            if profile is not None and prof not in (None, "", profile):
                continue
            legs = [r["leg"]] if r.get("leg") else ["loaded", "return"]
            for leg in legs:
                out.setdefault((rid, prof or profile, leg), set()).add(int(r["alt_index"]))
    return out


def in_use_keys(rows=None):
    """{"R012@1", …}: every stored option a diversion uses on some day, whatever the lorry type and leg."""
    return {leg_key(rid, a) for (rid, _p, _l), alts in in_use(rows=rows).items() for a in alts}


def month_weights(route_id, profile, month_index, rows=None):
    """
    The month's working days split by option: {"loaded": {alt: share}, "return": {alt: share},
    "pairs": [((loaded_alt, return_alt), share)]} — mix() over the month's days. A route no row touches is
    {"loaded": {0: 1.0}, "return": {0: 1.0}, "pairs": [((0, 0), 1.0)]}.
    """
    m = mix(route_id, profile, month_days(int(month_index)), rows=rows, peaks=False)   # 0d-2: Q9, zones only
    out = {"loaded": {}, "return": {}, "pairs": m["pairs"]}
    for (la, ra), w in m["pairs"]:
        out["loaded"][la] = out["loaded"].get(la, 0.0) + w
        out["return"][ra] = out["return"].get(ra, 0.0) + w
    return out


def majority_alt(route_id, profile, leg, days, rows=None):
    """The option a route uses on MOST of these days (ties: the main line) — for a reader that draws one line for a
    period (a week's map, the Simulation's average day)."""
    rows = _rows_by_route() if rows is None else rows
    if not days or not has_rows(route_id, rows):
        return 0
    n = {}
    for d in days:
        a = alt_on(route_id, profile, leg, d, rows=rows)
        n[a] = n.get(a, 0) + 1
    return max(sorted(n), key=lambda a: (n[a], a == 0))


# --------------------------------------------------------------------------- #
#  5 Nov 2026 (task 0d-2): use Alt N in the weekday busy hours                 #
# --------------------------------------------------------------------------- #
#: the days a busy-hours use applies on (the offer counted weekdays only)
BUSY_DAYS = "1111100"
#: statuses of a 'peak' row
BUSY_STATUSES = ("in_use", "paused", "stopped")


def _mins(hhmm):
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def busy_share(hours_from, hours_to, span):
    """The share of a day's trips that set off between hours_from and hours_to, trips spread evenly over `span`
    ((from, to) minutes, the route's open window): the overlap over the window. 0 when they do not meet."""
    a, b = _mins(hours_from), _mins(hours_to)
    if a is None or b is None or not span or span[1] <= span[0]:
        return 0.0
    lo, hi = max(a, span[0]), min(b, span[1])
    return max(0.0, (hi - lo) / float(span[1] - span[0]))


_SPAN = {}


def busy_span(route_id):
    """collisions.gate_span for the route, (from, to) minutes; one read per tenant, data version and route."""
    key = (db.current_tenant(), db.data_version(), route_id)
    if key in _SPAN:
        return _SPAN[key]
    span = None
    try:
        import collisions
        r = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), route_id))
        if r:
            span = collisions.gate_span(r[0])
    except Exception as e:
        print("route_choice: no open window for", route_id, str(e)[:120])
    if len(_SPAN) > 2000:
        _SPAN.clear()
    _SPAN[key] = span
    return span


def _has_peak(route_id, rows):
    return any(r.get("reason_kind") == "peak" and r.get("status") == "in_use" for r in rows.get(route_id) or [])


def _peaks_on(route_id, profile, leg, day, rows):
    """The in-use peak rows that apply to this leg on this day, whatever the hour."""
    out = []
    for r in rows.get(route_id) or []:
        if r.get("reason_kind") != "peak" or r.get("status") != "in_use":
            continue
        if _applies(dict(r, hours_from=None, hours_to=None), profile, leg, day):
            out.append(r)
    return out


def busy_alt_at(route_id, profile, leg, day, minute, rows=None):
    """The option a leg SETTING OFF at `minute` (from midnight) on `day` takes (Q2): a zone row first (Q10), then an
    in-use busy-hours row whose hours hold that minute, else the main line. The Simulation's per-trip road."""
    rows = _rows_by_route() if rows is None else rows
    day = _d(day)
    c = choice_on(route_id, profile, leg, day, rows=rows)
    if c is not None:
        return int(c["alt_index"]) if c.get("status") == "in_use" else 0
    for r in _peaks_on(route_id, profile, leg, day, rows):
        a, b = _mins(r.get("hours_from")), _mins(r.get("hours_to"))
        if a is not None and b is not None and a <= minute < b:
            return int(r["alt_index"])
    return 0


def _fp(raw):
    try:
        import here_routing
        return here_routing._fingerprint(_line_of(raw))
    except Exception:
        return None


def _stored_alt(route_id, alt):
    """[(profile, leg, row)] of the stored lines of option `alt` on this route."""
    return [(g["vehicle_profile"], g["leg"], g) for g in db.query(
        "SELECT vehicle_profile, leg, alt_index, geometry, distance_km FROM route_geometry WHERE tenant_id = ? "
        "AND route_id = ? AND alt_index = ? AND geometry IS NOT NULL", (db.current_tenant(), route_id, int(alt)))]


def _busy_id(route_id, profile, leg, hours_from):
    return f"P:{route_id}:{profile}:{leg}:{hours_from}"


class BusyError(ValueError):
    """A Use / Stop that cannot be done, in words for the screen."""


def use_busy(route_id, alt, hours_from, hours_to, who=None):
    """
    Put Alt N in use on weekdays between hours_from and hours_to (Q1: every lorry type and leg that has its own Alt N;
    a type without one stays on the main route). One row per (lorry type, leg) and band: a second Use of the same band
    replaces the first. Returns the number of legs.
    """
    alt = int(alt)
    if alt <= 0:
        raise BusyError("Pick one of the other roads.")
    if _mins(hours_from) is None or _mins(hours_to) is None or _mins(hours_to) <= _mins(hours_from):
        raise BusyError("Those hours do not read as a time of day.")
    legs = _stored_alt(route_id, alt)
    main = {(p, l): g for p, l, g in _stored_alt(route_id, 0)}
    if not legs:
        raise BusyError("That road is not stored for this route any more. Route it again first.")
    now = _now()
    for prof, leg, g in legs:
        rid = _busy_id(route_id, prof, leg, hours_from)
        db.execute("DELETE FROM route_choice WHERE tenant_id = ? AND id = ?", (db.current_tenant(), rid))
        m = main.get((prof, leg))
        km_delta = (round(float(g["distance_km"] or 0) - float(m["distance_km"] or 0), 3)
                    if m and g.get("distance_km") is not None and m.get("distance_km") is not None else None)
        db.execute(
            "INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, "
            "hours_from, hours_to, days, reason_kind, reason_ref, status, source, km_delta, decided_by, decided_at, "
            "created_at, updated_at, line_fp) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 'peak', ?, 'in_use', "
            "'planner', ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), rid, route_id, prof, leg, alt, hours_from, hours_to, BUSY_DAYS,
             f"{hours_from}-{hours_to}", km_delta, who, now, now, now, _fp(g["geometry"])))
    return len(legs)


def stop_busy(route_id, hours_from, who=None):
    """Stop the busy-hours use of this band (every lorry type and leg). Returns the number of rows stopped."""
    rows = [r for r in _all_rows() if r["route_id"] == route_id and r.get("reason_kind") == "peak"
            and r.get("hours_from") == hours_from and r.get("status") != "stopped"]
    if not rows:
        raise BusyError("Nothing is in use in those hours.")
    now = _now()
    for r in rows:
        db.execute("UPDATE route_choice SET status = 'stopped', decided_by = ?, decided_at = ?, updated_at = ? "
                   "WHERE tenant_id = ? AND id = ?", (who, now, now, db.current_tenant(), r["id"]))
    return len(rows)


def check_busy():
    """
    After a bake (refresh_zones): an in-use busy-hours row whose Alt N line is gone or is another road than when it
    was put in use is PAUSED (Q11) — the figures go back to the main line until a planner looks and presses Use again.
    Returns the route ids paused.
    """
    rows = [r for r in _all_rows() if r.get("reason_kind") == "peak" and r.get("status") == "in_use"]
    if not rows:
        return []
    cur = {}
    for g in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry FROM route_geometry WHERE tenant_id = ? "
                      "AND alt_index > 0 AND geometry IS NOT NULL", (db.current_tenant(),)):
        cur[(g["route_id"], g["vehicle_profile"], g["leg"], int(g["alt_index"]))] = g["geometry"]
    paused, now = set(), _now()
    for r in rows:
        raw = cur.get((r["route_id"], r["vehicle_profile"], r["leg"], int(r["alt_index"])))
        if raw is not None and r.get("line_fp") and _fp(raw) == r["line_fp"]:
            continue
        db.execute("UPDATE route_choice SET status = 'paused', updated_at = ? WHERE tenant_id = ? AND id = ?",
                   (now, db.current_tenant(), r["id"]))
        paused.add(r["route_id"])
    if paused:
        print(f"route_choice: busy-hours use paused, the road changed: {', '.join(sorted(paused))}")
    return sorted(paused)


def busy_uses(route_id=None):
    """
    The busy-hours uses, one per (route, band): [{"route_id", "alt", "from", "to", "status", "decided_by",
    "decided_at", "legs": [{"vehicle_profile", "leg", "km_delta", "status"}]}] — paused when any leg is paused, stopped
    only when every leg is.
    """
    groups = {}
    for r in _all_rows():
        if r.get("reason_kind") != "peak" or (route_id and r["route_id"] != route_id):
            continue
        g = groups.setdefault((r["route_id"], r.get("hours_from")), {
            "route_id": r["route_id"], "alt": int(r["alt_index"] or 0), "from": r.get("hours_from"),
            "to": r.get("hours_to"), "statuses": set(), "decided_by": r.get("decided_by"),
            "decided_at": r.get("decided_at"), "legs": []})
        g["statuses"].add(r.get("status"))
        if (r.get("decided_at") or "") > (g["decided_at"] or ""):
            g.update(decided_by=r.get("decided_by"), decided_at=r.get("decided_at"), alt=int(r["alt_index"] or 0))
        g["legs"].append({"vehicle_profile": r.get("vehicle_profile"), "leg": r.get("leg"),
                          "km_delta": r.get("km_delta"), "status": r.get("status")})
    out = []
    for g in groups.values():
        st = g.pop("statuses")
        g["status"] = "paused" if "paused" in st else ("in_use" if "in_use" in st else "stopped")
        out.append(g)
    out.sort(key=lambda g: (g["route_id"], g["from"] or ""))
    return out
