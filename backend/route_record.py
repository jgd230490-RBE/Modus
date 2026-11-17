"""
17 Nov 2026 (best option step 3, John's "Yes, as recommended" to the third draft, Q1 to Q9): the ROUTE CHOICES RECORD.

John, 13 Nov: cost, carbon and time, more or less, for the approved quantities and a trip, through the project (his words
in notes/session-1117-route-choices-record.md).

What is kept (Q1): a Make primary (kind 'primary', one route and one lorry type, Q3) and a busy-hours road put in use
(kind 'busy', every lorry type that has the road). A dated diversion is a closure, not a choice: never kept (one line
says how many). "Keep the main route" is not kept either.

A row is written on the SERVER, inside the paths that make the choice (network.promote_alternative, route_choice.use_busy),
so no screen needs a change. It holds a trip's figures BEFORE and AFTER as stored that day, per lorry type: km, minutes,
kg CO2e (network.route_analysis, which goes through return_journey.trip_kg), left turns, cycle routes met, places
(schools, hospitals and health centres) and the collisions on each pair's own lines (route_best.measures, read only), and
the chosen lines' fingerprints. A later re-route never rewrites them: it ENDS the row (Q8), never deletes it.

Ends (Q8): "routed_again" (the main line is no longer the one chosen: a bake, Route all, a way round), "undone" (Make
primary back to the line in use before), "stopped" (Stop on a busy-hours road, or a band used again with another road),
"road_changed" (a busy-hours road paused by a re-route; or a later Make primary of another line on the same route and
lorry). One-leg presses for the same route and lorry within JOIN_MIN minutes join one row (Q3).

The sums are worked out on each read (Q4, Q6): planned = the Approved loads from the day of the choice to its end (each
month's working days in the period; a busy-hours road the share of the route's open window its hours cover,
route_choice.busy_share) x a trip's difference; so far = the RECORDED loads (forecast_weeks.actual_qty) of the weeks in
the period, estimated (it assumes the lorries took the road). Fair cost (model) is worked out at each month's diesel price
from the saved distances and times (fairprice.trip_cost, as busy_savings does). A negative figure is a saving; what a
choice adds is shown, never hidden. Collisions are a record of the road: two counts, never x loads, never totalled.

Planned or estimated, never measured: Wayscope cannot see which road a lorry took.
"""
import datetime
import json

import conversions
import db
import derived
import fairprice
import network
import route_choice
import weeks

TABLE = "route_choice_record"
KINDS = ("primary", "busy")
JOIN_MIN = 10                         # Q3: one-leg presses for one route and lorry within this many minutes join a row
ENDED_WORDS = {"routed_again": "routed again", "undone": "undone", "stopped": "stopped",
               "road_changed": "the road changed"}
#: the per-trip figures every side carries, and the ones multiplied by loads (collisions never are: Q9)
SIDE_KEYS = ("loaded_km", "return_km", "km", "cycle_min", "drive_min", "kg", "left_turns", "cycle_meets", "places",
             "collisions")
TIMES_LOADS = ("km", "min", "kg", "eur", "left_turns", "cycle_meets", "places")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _d(v):
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _ts(v):
    try:
        t = datetime.datetime.fromisoformat(str(v))
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _tag():
    """A short random tag: two choices in the same second never share an id."""
    import uuid
    return uuid.uuid4().hex[:6]


def _label(alt):
    return "Main route" if not alt else f"Alt {int(alt)}"


# --------------------------------------------------------------------------- #
#  Measuring a trip (read only)                                                #
# --------------------------------------------------------------------------- #
def _lines(route_id):
    """{(profile, leg, alt): coords} and {(profile, leg, alt): fingerprint} of the route's stored lines now."""
    import collisions
    import here_routing
    lines, prints = {}, {}
    for g in db.query("SELECT vehicle_profile, leg, alt_index, geometry FROM route_geometry WHERE tenant_id = ? "
                      "AND route_id = ? AND geometry IS NOT NULL", (db.current_tenant(), route_id)):
        coords = collisions._coords(g["geometry"])
        if len(coords) < 2:
            continue
        k = (g["vehicle_profile"], g["leg"], int(g.get("alt_index") or 0))
        lines[k] = coords
        prints[k] = here_routing._fingerprint(coords)
    return lines, prints


class _Ctx:
    """route_best.Context, made once per write and only when a count is wanted (it reads the collision records, the
    community features and the cycle routes); None when it cannot be made (the counts are then left out)."""

    def __init__(self):
        self._c = False

    def get(self):
        if self._c is False:
            try:
                import route_best
                self._c = route_best.Context()
            except Exception as e:
                print("route record: no counts:", str(e)[:160])
                self._c = None
        return self._c


def _measure(route_id, profile, pair, lines, ctx):
    """A trip on (loaded_alt, return_alt) for one lorry type: the SIDE_KEYS, or None when the pair is not costed."""
    c = ctx.get()
    try:
        # never the Context's `pre`: it holds the geometry rows as they were BEFORE a swap (one route's own read is cheap)
        ana = network.route_analysis(route_id, profiles=[profile], pairs=[tuple(pair)])
    except Exception as e:
        print("route record: not measured:", route_id, str(e)[:160])
        return None
    row = next((r for r in ana.get("rows") or [] if r.get("profile") == profile
                and (r.get("alt_index"), r.get("return_alt_index")) == tuple(pair)), None)
    if row is None:
        return None
    out = {"loaded_alt": int(pair[0]), "return_alt": int(pair[1]),
           "loaded_km": round(float(row.get("loaded_km") or 0), 3), "return_km": round(float(row.get("return_km") or 0), 3),
           "km": round(float(row.get("total_km") or 0), 3), "cycle_min": round(float(row.get("cycle_hr") or 0) * 60, 2),
           "drive_min": round((float(row.get("loaded_hr") or 0) + float(row.get("return_hr") or 0)) * 60, 2),
           "kg": round(float(row.get("co2_kg_per_trip") or 0), 2),
           "left_turns": None, "cycle_meets": None, "places": None, "collisions": None}
    if c is not None:
        try:
            import route_best
            m = route_best.measures(route_id, row, lines, profile, c)
            out.update(left_turns=m["left_turns"], cycle_meets=m["cycle_meets"], places=m["places"],
                       collisions=(m["collisions"] if c.fetched else None))
        except Exception as e:
            print("route record: no counts for", route_id, str(e)[:160])
    return out


def _side_prints(prints, profile, pair):
    return {"loaded": prints.get((profile, "loaded", int(pair[0]))), "return": prints.get((profile, "return", int(pair[1])))}


# --------------------------------------------------------------------------- #
#  The rows                                                                    #
# --------------------------------------------------------------------------- #
def _decode(r):
    r = dict(r)
    for k in ("figures", "prints"):
        try:
            r[k] = json.loads(r.get(k) or "{}")
        except Exception:
            r[k] = {}
    r["alt_index"] = int(r.get("alt_index") or 0)
    r["legs"] = [l for l in (r.get("legs") or "").split(",") if l]
    return r


def rows(route_id=None, open_only=False):
    """The record's rows, newest choice first, decoded."""
    q = f"SELECT * FROM {TABLE} WHERE tenant_id = ?"
    args = [db.current_tenant()]
    if route_id:
        q += " AND route_id = ?"
        args.append(route_id)
    if open_only:
        q += " AND status = 'in_use'"
    try:
        got = db.query(q, tuple(args))
    except Exception as e:
        print("route record: table not ready:", str(e)[:120])
        return []
    out = [_decode(r) for r in got]
    out.sort(key=lambda r: (r.get("decided_at") or "", r["id"]), reverse=True)
    return out


def _insert(rec):
    now = _now()
    db.execute(
        f"INSERT INTO {TABLE} (tenant_id, id, route_id, kind, vehicle_profile, alt_index, legs, hours_from, hours_to, "
        "since, status, ended_on, ended_why, figures, prints, decided_by, decided_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_use', NULL, NULL, ?, ?, ?, ?, ?)",
        (db.current_tenant(), rec["id"], rec["route_id"], rec["kind"], rec.get("vehicle_profile"), int(rec["alt_index"]),
         ",".join(rec["legs"]), rec.get("hours_from"), rec.get("hours_to"), rec["since"],
         json.dumps(rec["figures"], sort_keys=True), json.dumps(rec.get("prints") or {}, sort_keys=True),
         rec.get("decided_by"), rec.get("decided_at") or now, now))


def end(rec_id, why, on=None):
    """End a row (never delete it): the day and the reason. Returns True when a row in use was ended."""
    if why not in ENDED_WORDS:
        raise ValueError(f"no such end: {why}")
    on = (on or datetime.date.today()).isoformat() if not isinstance(on, str) else on
    got = db.query(f"SELECT status FROM {TABLE} WHERE tenant_id = ? AND id = ?", (db.current_tenant(), rec_id))
    if not got or got[0]["status"] != "in_use":
        return False
    db.execute(f"UPDATE {TABLE} SET status = 'ended', ended_on = ?, ended_why = ?, updated_at = ? "
               "WHERE tenant_id = ? AND id = ?", (on, why, _now(), db.current_tenant(), rec_id))
    return True


# --------------------------------------------------------------------------- #
#  Make primary (network.promote_alternative)                                  #
# --------------------------------------------------------------------------- #
def before_promote(route_id, profile, leg, alt_index):
    """Read BEFORE the swap: a trip on the line in use (the main line, both legs) for this lorry, and its prints. The
    state after_promote needs; never raises (the swap must not fail because of the record)."""
    try:
        ctx = _Ctx()
        lines, prints = _lines(route_id)
        before = _measure(route_id, profile, (0, 0), lines, ctx)
        if before is None:
            return None
        before["prints"] = _side_prints(prints, profile, (0, 0))
        return {"route_id": route_id, "profile": profile, "leg": leg, "alt": int(alt_index), "before": before,
                "ctx": ctx}
    except Exception as e:
        print("route record: before the swap:", route_id, str(e)[:160])
        return None


def after_promote(state, who=None, now=None):
    """After the swap: measure the new main line and write, join or end (module docstring). Returns the row id written
    or joined, or None. Never raises."""
    if not state:
        return None
    try:
        return _after_promote(state, who, now)
    except Exception as e:
        print("route record: after the swap:", state.get("route_id"), str(e)[:160])
        return None


def _after_promote(state, who, now):
    rid, prof, leg = state["route_id"], state["profile"], state["leg"]
    lines, prints = _lines(rid)
    after = _measure(rid, prof, (0, 0), lines, state["ctx"])
    if after is None:
        return None
    after["prints"] = _side_prints(prints, prof, (0, 0))
    now_ts = now or datetime.datetime.now(datetime.timezone.utc)
    stamp = now_ts.isoformat(timespec="seconds")
    open_rows = [r for r in rows(rid, open_only=True) if r["kind"] == "primary" and r.get("vehicle_profile") == prof]
    for r in open_rows:
        f = (r["figures"] or {}).get(prof) or {}
        was = (f.get("before") or {}).get("prints") or {}
        if was and was == after["prints"]:
            end(r["id"], "undone", now_ts.date())         # back to the line in use before the choice
            return r["id"]
        t = _ts(r.get("decided_at"))
        if t is not None and (now_ts - t) <= datetime.timedelta(minutes=JOIN_MIN):
            legs = list(r["legs"])
            if leg not in legs:
                legs.append(leg)
            f = dict(f, after=after)
            figs = dict(r["figures"] or {}, **{prof: f})
            db.execute(f"UPDATE {TABLE} SET legs = ?, figures = ?, prints = ?, updated_at = ? WHERE tenant_id = ? "
                       "AND id = ?", (",".join(sorted(legs)), json.dumps(figs, sort_keys=True),
                                      json.dumps({prof: after["prints"]}, sort_keys=True), stamp,
                                      db.current_tenant(), r["id"]))
            return r["id"]
        end(r["id"], "road_changed", now_ts.date())       # another line made the main route since
    rec = {"id": f"M:{rid}:{prof}:{stamp}:{_tag()}", "route_id": rid, "kind": "primary", "vehicle_profile": prof,
           "alt_index": state["alt"], "legs": [leg], "since": now_ts.date().isoformat(),
           "figures": {prof: {"before": state["before"], "after": after}}, "prints": {prof: after["prints"]},
           "decided_by": who, "decided_at": stamp}
    _insert(rec)
    return rec["id"]


# --------------------------------------------------------------------------- #
#  Busy-hours roads (route_choice.use_busy / stop_busy / check_busy)           #
# --------------------------------------------------------------------------- #
def _busy_pair(legs_have, alt):
    return (alt if "loaded" in legs_have else 0, alt if "return" in legs_have else 0)


def open_busy(route_id, alt, hours_from, hours_to, who=None, since=None, decided_at=None, ctx=None):
    """A busy-hours road put in use: one row, every lorry type that has the road. A band used again with the same road
    and hours keeps its row; with another road or hours the old row ends ("stopped") and a new one starts. Never
    raises. Returns the row id."""
    try:
        alt = int(alt)
        for r in rows(route_id, open_only=True):
            if r["kind"] == "busy" and r.get("hours_from") == hours_from:
                if r["alt_index"] == alt and r.get("hours_to") == hours_to:
                    return r["id"]
                end(r["id"], "stopped")
        ctx = ctx or _Ctx()
        lines, prints = _lines(route_id)
        by_prof = {}
        for (p, leg, a) in lines:
            if a == alt:
                by_prof.setdefault(p, set()).add(leg)
        figs, pr, legs_all = {}, {}, set()
        for p, legs_have in sorted(by_prof.items()):
            pair = _busy_pair(legs_have, alt)
            b = _measure(route_id, p, (0, 0), lines, ctx)
            a = _measure(route_id, p, pair, lines, ctx)
            if b is None or a is None:
                continue
            b["prints"] = _side_prints(prints, p, (0, 0))
            a["prints"] = _side_prints(prints, p, pair)
            figs[p] = {"before": b, "after": a}
            pr[p] = a["prints"]
            legs_all |= legs_have
        if not figs:
            return None
        stamp = decided_at or _now()
        rec = {"id": f"B:{route_id}:{hours_from}:{stamp}:{_tag()}", "route_id": route_id, "kind": "busy", "vehicle_profile": None,
               "alt_index": alt, "legs": sorted(legs_all), "hours_from": hours_from, "hours_to": hours_to,
               "since": (since or _d(stamp) or datetime.date.today()).isoformat(), "figures": figs, "prints": pr,
               "decided_by": who, "decided_at": stamp}
        _insert(rec)
        return rec["id"]
    except Exception as e:
        print("route record: busy-hours road not kept:", route_id, str(e)[:160])
        return None


def stop_busy(route_id, hours_from):
    """Stop pressed on a busy-hours band: its row ends ("stopped"). Never raises."""
    try:
        for r in rows(route_id, open_only=True):
            if r["kind"] == "busy" and r.get("hours_from") == hours_from:
                end(r["id"], "stopped")
    except Exception as e:
        print("route record: busy-hours stop not kept:", route_id, str(e)[:160])


# --------------------------------------------------------------------------- #
#  Keeping the rows true (route_choice.refresh_zones, and the read)            #
# --------------------------------------------------------------------------- #
def sync(take_in=True):
    """
    End every row whose choice no longer holds, and take in a busy-hours road in use that has no row (Q2: R013's, put in
    use on 6 Nov before the record existed; only while its road is still the one put in use). Run after every bake and
    zone save (route_choice.refresh_zones) and on the record's read. Geometry only; returns {"ended": n, "taken_in": n}.
    """
    out = {"ended": 0, "taken_in": 0}
    try:
        open_rows = rows(open_only=True)
    except Exception:
        return out
    by_route = {}
    if open_rows:
        cur = {}
        for g in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry FROM route_geometry "
                          "WHERE tenant_id = ? AND geometry IS NOT NULL AND route_id IN (%s)"
                          % ",".join("?" * len({r["route_id"] for r in open_rows})),
                          (db.current_tenant(), *sorted({r["route_id"] for r in open_rows}))):
            cur[(g["route_id"], g["vehicle_profile"], g["leg"], int(g["alt_index"] or 0))] = g["geometry"]
        for r in open_rows:
            by_route.setdefault(r["route_id"], []).append(r)
            if r["kind"] != "primary":
                continue
            for prof, want in (r.get("prints") or {}).items():
                changed = False
                for leg in ("loaded", "return"):
                    raw = cur.get((r["route_id"], prof, leg, 0))
                    have = route_choice._fp(raw) if raw is not None else None
                    if want.get(leg) and have != want.get(leg):
                        changed = True
                if changed and end(r["id"], "routed_again"):
                    out["ended"] += 1
                    break
    uses = route_choice.busy_uses()
    state = {(u["route_id"], u["from"]): u for u in uses}
    for r in open_rows:
        if r["kind"] != "busy":
            continue
        u = state.get((r["route_id"], r.get("hours_from")))
        st = (u or {}).get("status")
        if st == "in_use" and u["alt"] == r["alt_index"]:
            continue
        if end(r["id"], "road_changed" if st == "paused" else "stopped"):
            out["ended"] += 1
    if take_in:
        have = {(r["route_id"], r.get("hours_from")) for r in rows(open_only=True) if r["kind"] == "busy"}
        ctx = None
        for u in uses:
            if u["status"] != "in_use" or (u["route_id"], u["from"]) in have or not _busy_road_unchanged(u):
                continue
            ctx = ctx or _Ctx()
            if open_busy(u["route_id"], u["alt"], u["from"], u["to"], who=u.get("decided_by"),
                         since=_d(u.get("decided_at")), decided_at=u.get("decided_at"), ctx=ctx):
                out["taken_in"] += 1
    return out


def _busy_road_unchanged(use):
    """Q2: the busy-hours road is still the line put in use (route_choice.check_busy's own test, on every leg)."""
    for r in route_choice._all_rows():
        if (r.get("reason_kind") != "peak" or r["route_id"] != use["route_id"] or r.get("hours_from") != use["from"]
                or r.get("status") != "in_use"):
            continue
        g = db.query("SELECT geometry FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? "
                     "AND leg = ? AND alt_index = ? AND geometry IS NOT NULL",
                     (db.current_tenant(), r["route_id"], r["vehicle_profile"], r["leg"], int(r["alt_index"])))
        if not g or not r.get("line_fp") or route_choice._fp(g[0]["geometry"]) != r["line_fp"]:
            return False
    return True


def sync_quietly(why):
    try:
        return sync()
    except Exception as e:
        print(f"route record: not checked after {why}:", str(e)[:160])
        return None


# --------------------------------------------------------------------------- #
#  The sums (read)                                                             #
# --------------------------------------------------------------------------- #
def _empty():
    return {"trips": 0.0, "of": 0.0, "km": 0.0, "min": 0.0, "kg": 0.0, "eur": 0.0, "eur_missing": False, "left_turns": 0.0,
            "cycle_meets": 0.0, "places": 0.0, "counts_missing": False}


def _add(acc, n, d):
    acc["trips"] += n
    for k in ("km", "min", "kg"):
        acc[k] += n * d[k]
    if d.get("eur") is None:
        acc["eur_missing"] = True
    else:
        acc["eur"] += n * d["eur"]
    for k in ("left_turns", "cycle_meets", "places"):       # a count not held stays None (a dash), the others still add
        if d.get(k) is None or acc[k] is None:
            acc["counts_missing"] = True
            acc[k] = None
        else:
            acc[k] += n * d[k]


def _round(acc):
    out = {k: (None if acc[k] is None else round(acc[k], 2 if k == "eur" else 1))
           for k in ("trips", "of", "km", "min", "kg", "eur", "left_turns", "cycle_meets", "places")}
    out["eur_missing"], out["counts_missing"] = acc["eur_missing"], acc["counts_missing"]
    return out


def per_trip(side_b, side_a, profile, month_index, cost, factors):
    """A trip's difference (after less before) for this lorry type in this month: km, min (the round trip), kg,
    eur (fair cost (model) at the month's diesel price), left turns, cycle routes met, places."""
    cal = ((int(month_index) - 1) % 12) + 1
    payload, _fb = derived.payload_for(profile, factors)
    cls = fairprice.vehicle_class(profile, factors)

    def eur(s):
        c = fairprice.trip_cost({"baked": True, "distance_km": s.get("loaded_km"), "return_km": s.get("return_km"),
                                 "cycle_min": float(s.get("cycle_min") or 0), "payload_t": payload,
                                 "vehicle_class": cls}, cal, cost.get("index_eur_per_l"), cost.get("fair_params") or {})
        return c["eur_trip"] if c else None
    eb, ea = eur(side_b), eur(side_a)

    def diff(k):
        if side_a.get(k) is None or side_b.get(k) is None:
            return None
        return float(side_a[k]) - float(side_b[k])
    return {"km": round(diff("km") or 0, 3), "min": round(diff("cycle_min") or 0, 2), "kg": round(diff("kg") or 0, 2),
            "eur": (round(ea - eb, 2) if ea is not None and eb is not None else None),
            "left_turns": diff("left_turns"), "cycle_meets": diff("cycle_meets"), "places": diff("places")}


def _days_in(month_index, since, until):
    """(working days of the month inside [since, until), working days of the month)."""
    days = route_choice.month_days(int(month_index))
    inside = [d for d in days if d >= since and (until is None or d < until)]
    return len(inside), len(days)


def sums(rec, factors=None, cost=None, routes=None, cache=None, today=None):
    """{"planned", "so_far", "per_trip" (the row's main lorry type), "lorry", "loads"} for one row (module docstring)."""
    factors = factors or conversions.load_factors()
    cost = cost if cost is not None else derived.costing_context()
    routes = routes if routes is not None else derived._routes_and_names()
    cache = cache if cache is not None else {}
    rid = rec["route_id"]
    since = _d(rec.get("since")) or datetime.date.today()
    until = _d(rec.get("ended_on")) if rec.get("status") == "ended" else None
    profs = sorted((rec.get("figures") or {}).keys())
    share = 1.0
    if rec["kind"] == "busy":
        share = route_choice.busy_share(rec.get("hours_from"), rec.get("hours_to"), route_choice.busy_span(rid))
    planned, so_far = _empty(), _empty()
    loads_by = {}
    from_month = weeks.month_index_of(since)
    q = ("SELECT route_id, month_index, discipline, section_id, quantity, unit, material_type, vehicle_type, ipt "
         "FROM forecasts WHERE tenant_id = ? AND route_id = ? AND status = 'Approved' AND month_index >= ?")
    args = [db.current_tenant(), rid, int(from_month)]
    if until is not None:
        q += " AND month_index <= ?"
        args.append(int(weeks.month_index_of(until)))
    lines = [r for r in db.query(q, tuple(args)) if r.get("vehicle_type") in profs]
    recorded = {}
    if lines:
        for w in db.query("SELECT month_index, discipline, section_id, week_index, actual_qty FROM forecast_weeks "
                          "WHERE tenant_id = ? AND route_id = ? AND actual_qty IS NOT NULL", (db.current_tenant(), rid)):
            recorded.setdefault((int(w["month_index"]), w.get("discipline") or "", w.get("section_id") or ""), []).append(w)
    deltas = {}
    for r in lines:
        veh, mi = r["vehicle_type"], int(r["month_index"])
        f = rec["figures"][veh]
        if (veh, mi) not in deltas:
            deltas[(veh, mi)] = per_trip(f["before"], f["after"], veh, mi, cost, factors)
        d = deltas[(veh, mi)]
        line = {"route_id": rid, "unit": r.get("unit"), "material_type": r.get("material_type"), "vehicle_type": veh,
                "ipt": r.get("ipt"), "discipline": r.get("discipline"), "section_id": r.get("section_id"),
                "month_index": mi, "week": {"planned_qty": r.get("quantity")}}
        ctx = derived.line_context(line, factors, routes=routes, cache=cache, cost=cost)
        trips = derived.day_figures(r.get("quantity"), ctx, factors)["trips"]
        inside, all_days = _days_in(mi, since, until)
        frac = inside / float(all_days) if all_days else 0.0
        n = trips * frac * share
        planned["of"] += trips * frac
        loads_by[veh] = loads_by.get(veh, 0.0) + n
        _add(planned, n, d)
        for w in recorded.get((mi, r.get("discipline") or "", r.get("section_id") or ""), []):
            try:
                mon, sun = weeks.week_span(mi, int(w["week_index"]))
            except Exception:
                continue
            if sun < since or (until is not None and mon >= until):
                continue                       # a week before the choice, or after its end
            got = derived.day_figures(w["actual_qty"], ctx, factors)["trips"]
            _add(so_far, got * share, d)
    lorry = (max(loads_by, key=lambda v: (loads_by[v], v)) if loads_by else (rec.get("vehicle_profile") or
                                                                            (profs[0] if profs else None)))
    pt = None
    if lorry and lorry in rec["figures"]:
        f = rec["figures"][lorry]
        pt = per_trip(f["before"], f["after"], lorry, weeks.month_index_of(today or datetime.date.today()), cost, factors)
    return {"planned": _round(planned), "so_far": _round(so_far), "per_trip": pt, "lorry": lorry,
            "share": round(share, 4)}


def _diversions():
    """Routes on a dated diversion today (a closure, not a choice): how many, for the one line under the table."""
    try:
        today = datetime.date.today()
        n = set()
        for r in route_choice._all_rows():
            if r.get("reason_kind") == "zone" and r.get("status") == "in_use" and int(r.get("alt_index") or 0) != 0:
                s, e = _d(r.get("starts_on")), _d(r.get("ends_on"))
                if (s is None or s <= today) and (e is None or today <= e):
                    n.add(r["route_id"])
        return len(n)
    except Exception:
        return 0


def record(today=None):
    """The Dashboard fold's read: {"rows": [...], "totals": {"planned", "so_far"}, "diversions": n}. Each row: the choice
    in words' parts, its status and end, the lorry, a trip's difference, the planned and so-far sums, the two collision
    counts. Runs sync() first (Q2's take-in, and any row a re-route ended)."""
    sync_quietly("the record's read")
    factors = conversions.load_factors()
    cost = derived.costing_context()
    routes = derived._routes_and_names()
    cache = {}
    out_rows = []
    tot = {"planned": _empty(), "so_far": _empty()}
    for rec in rows():
        try:
            s = sums(rec, factors=factors, cost=cost, routes=routes, cache=cache, today=today)
        except Exception as e:
            print("route record: no sums for", rec["id"], str(e)[:160])
            continue
        f = (rec["figures"] or {}).get(s["lorry"]) or {}
        b, a = f.get("before") or {}, f.get("after") or {}
        rt = routes.get(rec["route_id"]) or {}
        row = {"id": rec["id"], "route_id": rec["route_id"], "kind": rec["kind"], "alt": rec["alt_index"],
               "from": rt.get("origin_name") or rt.get("origin_id"), "to": rt.get("dest_name") or rt.get("dest_id"),
               "label": _label(rec["alt_index"]), "legs": rec["legs"], "hours_from": rec.get("hours_from"),
               "hours_to": rec.get("hours_to"), "since": rec.get("since"), "status": rec["status"],
               "ended_on": rec.get("ended_on"), "ended_why": rec.get("ended_why"),
               "ended_words": ENDED_WORDS.get(rec.get("ended_why") or ""),
               "lorry": s["lorry"], "lorry_name": (conversions.vehicle_label(factors, s["lorry"]) if s["lorry"] else None),
               "lorries": sorted((rec["figures"] or {}).keys()), "all_lorries": rec["kind"] == "busy",
               "decided_by": rec.get("decided_by"), "decided_at": rec.get("decided_at"),
               "per_trip": s["per_trip"], "planned": s["planned"], "so_far": s["so_far"], "share": s["share"],
               "before": {k: b.get(k) for k in SIDE_KEYS}, "after": {k: a.get(k) for k in SIDE_KEYS},
               "collisions": {"before": b.get("collisions"), "after": a.get("collisions"),
                              "before_label": ("Main route" if rec["kind"] == "busy" else "Old main route"),
                              "after_label": _label(rec["alt_index"])}}
        out_rows.append(row)
        for k in ("planned", "so_far"):
            src, acc = s[k], tot[k]
            for x in ("trips", "of", "km", "min", "kg", "eur", "left_turns", "cycle_meets", "places"):
                acc[x] = None if (acc[x] is None or src[x] is None) else acc[x] + src[x]
            acc["eur_missing"] = acc["eur_missing"] or src["eur_missing"]
            acc["counts_missing"] = acc["counts_missing"] or src["counts_missing"]
    try:
        import collisions
        period = (collisions.status() or {}).get("period") or None
    except Exception:
        period = None
    return {"rows": out_rows, "totals": {k: _round(v) for k, v in tot.items()}, "diversions": _diversions(),
            "collision_period": period, "day": (today or datetime.date.today()).isoformat()}


# --------------------------------------------------------------------------- #
#  Words and the spreadsheet (Q7)                                              #
# --------------------------------------------------------------------------- #
def choice_words(row):
    """'Alt 1 made the main route', '… (loaded leg)' when one leg only; 'Alt 2, weekdays 16:00–19:00'."""
    if row["kind"] == "busy":
        return f"{row['label']}, weekdays {row.get('hours_from') or ''}–{row.get('hours_to') or ''}"
    legs = row.get("legs") or []
    return f"{row['label']} made the main route" + (f" ({legs[0]} leg)" if len(legs) == 1 else "")


def ended_words(row):
    return f"Ended: {row['ended_words']}" if row.get("status") == "ended" and row.get("ended_words") else ""


SHEET_HEAD = ("Route", "Choice", "Lorry types", "Made", "By", "Ended", "Why ended", "Loads planned", "Loads recorded",
              "CO2e a trip before (kg)", "CO2e a trip after (kg)", "Round trip before (min)", "Round trip after (min)",
              "Distance before ({du})", "Distance after ({du})", "CO2e planned (t)", "CO2e so far (t)",
              "Lorry time planned (h)", "Distance planned ({du})", "Fair cost (model) planned ({cur})",
              "Fair cost (model) so far ({cur})", "Left turns planned", "Cycle routes met planned", "Places planned",
              "Collisions, road before", "Collisions, road after")


def _sheet_date(v):
    d = _d(v)
    return d.strftime("%d/%m/%Y") if d else ""


def sheet_rows(R):
    """The spreadsheet's rows (lists in SHEET_HEAD's order), from record()'s reply. A minus figure is a saving."""
    import export
    import users
    out = []
    for r in R["rows"]:
        b, a, p, s = r["before"], r["after"], r["planned"], r["so_far"]
        dist = lambda km: (round(export._dist(km), 2) if km is not None else None)
        out.append([
            r["route_id"], choice_words(r), ("All" if r["all_lorries"] else (r.get("lorry_name") or "")),
            _sheet_date(r.get("since")), users.csv_cell(r.get("decided_by") or ""), _sheet_date(r.get("ended_on")),
            (r.get("ended_words") or ""), round(p["trips"], 1), round(s["trips"], 1),
            b.get("kg"), a.get("kg"), b.get("cycle_min"), a.get("cycle_min"), dist(b.get("km")), dist(a.get("km")),
            round(p["kg"] / 1000.0, 2), round(s["kg"] / 1000.0, 2), round(p["min"] / 60.0, 1), dist(p["km"]),
            (None if p["eur_missing"] else round(p["eur"])), (None if s["eur_missing"] else round(s["eur"])),
            (None if p["left_turns"] is None else round(p["left_turns"])),
            (None if p["cycle_meets"] is None else round(p["cycle_meets"])),
            (None if p["places"] is None else round(p["places"])),
            r["collisions"]["before"], r["collisions"]["after"]])
    return out


def build_xlsx(R):
    """The record as one sheet: the demo line, a title, the head, a row a choice; About on a second sheet."""
    import export
    if export.openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + export.MISSING.get("xlsx", ""))
    Font, PatternFill = export.Font, export.PatternFill
    wb = export.openpyxl.Workbook()
    ws = wb.active
    ws.title = "Route choices"
    r = 1
    notice = export._demo_notice()
    if notice:
        cv = ws.cell(row=r, column=1, value="DEMO · " + notice)
        cv.font = Font(bold=True, color=export.DEMO_FG_HEX)
        cv.fill = PatternFill("solid", fgColor=export.DEMO_BG_HEX)
        r += 1
    ws.cell(row=r, column=1, value=f"Route choices: what each saved or added · {export._tenant_name()} · "
                                   f"{_sheet_date(R.get('day'))}").font = Font(bold=True, size=12)
    r += 1
    ws.cell(row=r, column=1, value="Planned from the approved loads, so far from recorded loads (estimated); never "
                                   "measured. A minus figure is a saving.")
    r += 2
    du, cur = export._du(), export._cur()
    for j, h in enumerate(SHEET_HEAD, 1):
        ws.cell(row=r, column=j, value=h.format(du=du, cur=cur)).font = Font(bold=True)
    ws.freeze_panes = ws.cell(row=r + 1, column=3)
    r += 1
    for vals in sheet_rows(R):
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            if isinstance(v, str):
                c.data_type = "s"            # a typed name is text, never a formula
        r += 1
    for j, w in enumerate([8, 34, 20, 11, 16, 11, 16] + [12] * (len(SHEET_HEAD) - 7), 1):
        ws.column_dimensions[export.openpyxl.utils.get_column_letter(j)].width = w
    ab = wb.create_sheet("About")
    lines = [("Document", "Route choices: what each saved or added"), ("Scheme", export._tenant_name()),
             ("As at", _sheet_date(R.get("day"))),
             ("Kept", "Another main route (Make primary) and a road for the busy hours. A dated diversion is a closure, "
                      "not a choice, so not counted here."),
             ("A trip", "The figures saved on the day of the choice, before and after."),
             ("Fair cost (model)", "The model's fuel, time and running cost at each month's diesel price, not the rate "
                                   "agreed with a haulier."),
             ("Places", "Schools, hospitals and health centres within 250 m. Both legs of a trip."),
             ("Collisions", "Injury collisions the police recorded on each road. A record of the road, never multiplied "
                            "by loads."),
             ("Dated diversions now", R.get("diversions", 0))]
    for i, (k, v) in enumerate(lines, 1):
        ab.cell(row=i, column=1, value=k).font = Font(bold=True)
        ab.cell(row=i, column=2, value=v)
    ab.column_dimensions["A"].width = 20
    ab.column_dimensions["B"].width = 100
    import io
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def file_name(R):
    return f"route-choices-{(R.get('day') or datetime.date.today().isoformat())}.xlsx"
