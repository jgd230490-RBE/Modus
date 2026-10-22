"""
Gate arrivals (11 Oct 2026) — lorries a day at each gate for one month, every team summed.

THE DECISION (the user, 11 Oct 2026, late night)
------------------------------------------------
A staff-only "Gate arrivals" panel on the Dashboard. For each gate and month: the laden
arrivals a day at the DESTINATION's entry gate PLUS the empty arrivals (lorries coming to
load) at the ORIGIN's entry gate, summed across ALL teams. Average gap in minutes = the
gate's open minutes ÷ arrivals a day (17 Oct 2026: its hours, else the default gate hours, less
the no-delivery bands and its shut windows — gate_hours.open_minutes; it was the scheme's shift
hours × 60 until then). The gate's minutes per lorry is its existing
typed check-in (`location_gates.safety_minutes`); no new field, no data change, no
re-import. Red ONLY when the average gap is shorter than that check-in — a queue even with
perfect spacing. No amber. A gate with no check-in typed is never compared. Approved lines
make the figure; pending lines are a note, never in the figure.

14 Oct 2026 (bundle G, W17, the user's D42 follow-up): the gate's OWN open hours when typed (less the
scheme's peak bands, the no-delivery windows) replace the shift for that gate (17 Oct 2026: a gate with
none typed takes the default gate hours, 08:00–17:00 unless the scheme sets its own, and its shut
windows come off too; the lorry shift no longer sets any gate's day), and an AMBER step joins
the red: "Queue likely" at 85 % of capacity or more (gate_hours.NEAR_PCT). The red rule is unchanged
(gap < check-in, the displayed gap); its word on screen is now "Over gate capacity". gate_hours.py
holds the rules; this module only applies them to the month.

The data holds daily totals and no hourly arrival profile, so every sentence this module
writes says "if arrivals are spread evenly" and never implies anything live or booked.
On an origin gate (a quarry, a pit, the railhead) it says that Wayscope sees only this
scheme's share of that gate's traffic — a weighbridge serves other customers too.

THE RULES, EACH FROM THE MODULE THAT ALREADY OWNS IT
----------------------------------------------------
* trips rule = derived.day_figures with a minimal unbaked ctx: trips = ceil(qty / payload),
  or qty itself when the unit is vehicles, the payload by derived.payload_for. `baked`
  False returns trips and tonnes only, so no route analysis is run and no HERE call is
  made — the same trips costlines.lines() reports for the same row (asserted equal).
* gate at each end = gates.resolve(loc, 'entry', route gate id): the destination's
  `dest_gate_id` for the laden end, the origin's `origin_gate_id` for the empty end. A
  route that names its origin EXIT gate falls through to the access gate (resolve's
  rule) — correct, and `fallthrough_routes` records it. A route that names a gate that
  is INACTIVE or no longer recorded (resolve's `blocked`) still has lorries arriving,
  so they are counted at the location's default entry gate and a note names the cause;
  a location with no entry gate at all is skipped and one note names it.
* the red rule compares the DISPLAYED gap (one decimal place) with the typed check-in,
  so the screen never shows "3.0 min" flagged red against a 3 min check-in. A raw gap of
  2.96 min reads 3.0 and does not flag; 2.94 reads 2.9 and does (asserted at the edge).
* working days: the planning block's figure, the costlines.py rule (22 when untyped); main passes its
  own _working_days in. The reply still carries the lorry shift (`shift_hours`, derived.py's 10 h when
  untyped) for the record; no gate figure reads it since 17 Oct 2026.
* cross-team sums on the UNFILTERED rows, per_team masked for a team code — clashes.py's
  rule: a team code may see the total and WHICH teams share the gate (by name), never
  another team's figure. Planner, admin and the demo submitter see every team's row.
* never spell a team slot id in this file (test_modus.py scans shipped .py for the id
  form; this module is NOT on its allow-list). Teams reach the output as the tenant's
  names through taxonomy.team_name; the caller's team is acc.get("ipt").

READ-ONLY. Three SELECTs (forecasts of the month, routes, locations) plus the one gates
read, every literal carrying the tenant predicate. Nothing here changes any existing
figure: the Dashboard cards, the Look-ahead, the exports and the map are untouched.
"""
import datetime

import access
import conversions
import db
import derived
import gate_hours
import gates
import taxonomy
import weeks

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

SPREAD = "if arrivals are spread evenly"
#: 17 Oct 2026 (review): a gate whose no-delivery bands and shut times cover all its hours — one meaning everywhere:
#: shut all day, so any arrival is over what it can check in (red), with these words, never "no check-in typed"
NO_OPEN_TIME = ("No open time: the no-delivery bands and this gate's shut times cover all its hours, so every arrival "
                "is more than it can check in.")


def r1(x):
    """One decimal place, plain Python round — the harness rounds the same way."""
    return round(float(x) + 0.0, 1)


def month_label(month_index):
    """9 -> 'Sep 2026', 13 -> 'Jan 2027' (weeks._month_of, main's START_YEAR)."""
    year, m = weeks._month_of(month_index)
    return f"{MONTHS[m - 1]} {year}"


def _positive(value, default):
    """main._working_days' guard: a zero, negative or junk figure in a hand-edited
    factors.json must not produce negative arrivals or a division by zero."""
    try:
        v = float(value or default)
    except (TypeError, ValueError):
        return float(default)
    return v if v > 0 else float(default)


def shift_hours(factors):
    """The derived.py rule: the planning block's LORRY shift, 10 h when untyped (not a gate's day since 17 Oct 2026)."""
    plan = (factors or {}).get("planning", {}) or {}
    return _positive(plan.get("shift_hours_per_day"), 10)


def _working_days(factors):
    plan = (factors or {}).get("planning", {}) or {}
    return _positive(plan.get("working_days_per_month"), 22)


def working_days(factors):
    """The costlines.py rule: the planning block's working days, 22 when untyped."""
    return _working_days(factors)


def trips_for(row, factors):
    """
    The one trips rule, for one forecast row: derived.day_figures on an UNBAKED ctx, so
    only trips and tonnes are worked out and no route geometry is read.
    """
    payload_t, _fb = derived.payload_for(row.get("vehicle_type"), factors)
    ctx = {"unit": row.get("unit"), "payload_t": payload_t,
           "material_type": row.get("material_type"),
           "vehicle_type": row.get("vehicle_type"), "baked": False}
    return int(derived.day_figures(row.get("quantity"), ctx, factors)["trips"])


def entry_gate(loc, named, loc_gates):
    """
    (resolved, blocked) — the gate a lorry ARRIVES by at `loc`: gates.resolve(loc, 'entry', the route's named gate).
    A named gate that is inactive or no longer recorded (`blocked`) still has lorries arriving, so they are counted at
    the location's default entry gate. 16 Oct 2026 (S3): pulled out of arrivals() so the simulation (sim.py) and
    week_by_day() resolve every end by this one rule.
    """
    r = gates.resolve(loc, "entry", named, gates=loc_gates)
    blocked = r.get("blocked")
    if blocked:
        r = gates.resolve(loc, "entry", None, gates=loc_gates)
    return r, blocked


def judge(arr_raw, open_m, gm):
    """
    The panel's verdict for one gate, from arrivals a day (raw), its open minutes and its check-in minutes:
    {gap, cap_raw, cap_pct, red, amber, flag}. RED when the DISPLAYED gap (one decimal place) is shorter than the
    check-in; AMBER "Queue likely" at gate_hours.NEAR_PCT % of capacity or more; no check-in typed, never compared.
    16 Oct 2026 (S3): pulled out of arrivals() unchanged, so the simulation's day is judged by the same rule.
    """
    total = arr_raw is not None and arr_raw > 0
    gap = r1(open_m / arr_raw) if (total and open_m > 0) else (0.0 if total else None)
    red = gm is not None and gap is not None and gap < gm
    cap_raw = gate_hours.capacity(open_m, gm)
    cap_pct = (round(arr_raw * 100.0 / cap_raw) if (cap_raw and total) else None)
    amber = (not red) and cap_raw is not None and total and arr_raw * 100.0 / cap_raw >= gate_hours.NEAR_PCT - 1e-9
    return {"gap": gap, "cap_raw": cap_raw, "cap_pct": cap_pct, "red": red, "amber": amber,
            "flag": "red" if red else ("amber" if amber else None)}


def _new_gate_acc():
    return {"laden": 0, "empty": 0, "team_trips": {}, "roles": set(), "pending_roles": set(),
            "pending_trips": 0, "pending_lines": 0, "fallthrough": set()}


def _reason(arr, gap, gm, pct=None, amber=False):
    if arr is None or gap is None:
        return "No approved arrivals this month."
    if gm is None:
        return "No check-in time typed for this gate, so nothing is compared."
    if gap < gm:
        return (f"{arr} arrivals a day, one every {gap} min {SPREAD}, shorter than the "
                f"{gm:g} min check-in: a queue even with perfect spacing.")
    if amber:
        # 14 Oct 2026 (W17): the 85 % step — the gate copes on the average, with little room for bunching
        return (f"One every {gap} min {SPREAD}, against a {gm:g} min check-in: {pct} % of what the gate "
                f"can check in, so a queue is likely when lorries bunch. No hourly peak is typed.")
    return (f"One every {gap} min {SPREAD}, against a {gm:g} min check-in: spacing holds "
            f"on the average. No hourly peak is typed.")


def arrivals(month_index, acc, factors=None, working_days=None):
    """
    The contract behind GET /api/gates/arrivals?month=N. See the module docstring.
    `acc` is the caller's access ({role, ipt, label}); only its team is read, here.
    """
    factors = factors or conversions.load_factors()
    wd = _positive(working_days, _working_days(factors))
    sh = shift_hours(factors)
    # 17 Oct 2026: the default gate day — what a gate with no hours typed is open (before bands and shut windows)
    dw = gate_hours.default_words(factors)
    open_m = float(sum(b - a for a, b in gate_hours._intervals(*gate_hours.effective_window({}, factors)[0])))
    label = month_label(month_index)
    scope = "team" if (acc or {}).get("ipt") else "scheme"
    my_team = (acc or {}).get("ipt")

    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND month_index = ? "
        "AND status IN ('Approved', 'Pending') ORDER BY route_id, discipline, section_id",
        (db.current_tenant(), int(month_index)))
    routes = {r["id"]: r for r in db.query(
        "SELECT * FROM routes WHERE tenant_id = ?", (db.current_tenant(),))}
    locations = {l["id"]: l for l in db.query(
        "SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    gbl = gates.gates_by_location()
    gate_rows = {g["id"]: g for gs in gbl.values() for g in gs}

    per_gate = {}
    no_gate_locs = {}          # location id -> location row (note 3)
    blocked_at = {}            # (location id, named gate id) -> the inactive/missing gate, where counted, routes
    approved_n = 0
    pending_n = 0
    pending_lorries_per_day = 0.0      # each pending lorry once
    pending_per_day_total = 0.0        # each pending lorry at every gate it arrives by

    for row in rows:
        route = routes.get(row.get("route_id"))
        if not route:
            continue                      # a line without a route is another page's fault
        status = row.get("status")
        if status == "Approved":
            approved_n += 1
        elif status == "Pending":
            pending_n += 1
        else:
            continue
        trips = trips_for(row, factors)
        if status == "Pending":
            pending_lorries_per_day += trips / wd
        team_key = access.canonical_ipt(row.get("ipt")) or row.get("ipt")
        for end, loc_key, gate_key in (("destination", "dest_id", "dest_gate_id"),
                                       ("origin", "origin_id", "origin_gate_id")):
            loc = locations.get(route.get(loc_key))
            if not loc:
                continue
            named = route.get(gate_key)
            loc_gates = gbl.get(loc["id"]) or []
            # the route names a gate that is inactive or no longer recorded: resolve refuses to pick another (the bake
            # must not quietly move to a different road), but the lorries on an approved line still arrive, so
            # entry_gate counts them at the location's default entry gate, and a note here says so.
            r, blocked = entry_gate(loc, named, loc_gates)
            if blocked:
                b = blocked_at.setdefault((loc["id"], named), {
                    "loc": loc, "blocked": dict(blocked), "to": r.get("gate_name"), "routes": set()})
                b["routes"].add(route["id"])
            gid = r.get("gate_id")
            if gid is None:
                no_gate_locs.setdefault(loc["id"], loc)
                continue
            g = per_gate.setdefault(gid, _new_gate_acc())
            if named and r.get("source") == "default" and not blocked:
                g["fallthrough"].add(route["id"])     # an exit gate named, the access gate used
            if status == "Approved":
                if end == "destination":
                    g["laden"] += trips
                else:
                    g["empty"] += trips
                g["team_trips"][team_key] = g["team_trips"].get(team_key, 0) + trips
                g["roles"].add(end)
            else:
                g["pending_trips"] += trips
                g["pending_lines"] += 1
                g["pending_roles"].add(end)
                pending_per_day_total += trips / wd

    labels = taxonomy.team_labels()

    def team_name(key):
        return None if key is None else taxonomy.team_name(key, labels)

    out_gates = []
    for gid, g in per_gate.items():
        grow = gate_rows.get(gid) or {}
        loc = locations.get(grow.get("location_id")) or {}
        total = g["laden"] + g["empty"]
        arr_raw = total / wd
        arr = r1(arr_raw)
        # 14 Oct 2026 (W17): the gate's OWN open minutes when its hours are typed, else (17 Oct 2026) the default gate
        # hours; less the scheme's peak bands (the no-delivery windows) and the gate's shut windows, an overlap counted
        # once — gate_hours.open_minutes, the one rule
        om = gate_hours.open_minutes(grow, factors)
        open_g = om["minutes"]
        gm = grow.get("safety_minutes")
        gm = float(gm) if gm is not None else None
        # 14 Oct 2026 (the Dashboard's gate chart): the gate's CAPACITY, the most lorries it can check in a day if they
        # arrive evenly = the open minutes ÷ its check-in minutes a lorry — the red rule turned round (gap < check-in
        # ⇔ arrivals > capacity), sent from here so the browser only draws it. No check-in typed: no capacity.
        # 14 Oct 2026 (W17, the user's 85 % step): amber "Queue likely" at 85 % of capacity or more, below the red rule.
        # 16 Oct 2026 (S3): the rule lives in judge(), which the simulation's day reads too
        jd = judge(arr_raw, open_g, gm)
        gap, red, cap_raw, cap_pct, amber, flag = jd["gap"], jd["red"], jd["cap_raw"], jd["cap_pct"], jd["amber"], jd["flag"]
        cap = r1(cap_raw) if cap_raw is not None else None
        shut_all_day = open_g <= 0
        if shut_all_day:
            # 17 Oct 2026 (review): no open minute left — red whenever lorries come, check-in typed or not, capacity 0
            red, amber, flag, cap, cap_pct = total > 0, False, ("red" if total > 0 else None), 0.0, None
        roles = g["roles"] or g["pending_roles"]
        role = "both" if len(roles) == 2 else (next(iter(roles)) if roles else "destination")
        teams = sorted(((team_name(k), k) for k in g["team_trips"]),
                       key=lambda t: (t[0] is None, t[0] or ""))
        per_team = [{"team": team_name(k), "_key": k, "arrivals_per_day": r1(v / wd)}
                    for k, v in g["team_trips"].items()]
        per_team.sort(key=lambda t: (-t["arrivals_per_day"], t["team"] is None, t["team"] or ""))
        if scope == "team":
            per_team = [t for t in per_team if access.canonical_ipt(t["_key"]) == my_team]
        for t in per_team:
            t.pop("_key", None)
        loc_name = loc.get("name") or grow.get("location_id") or ""
        share = (f"{loc_name} serves other customers too; Wayscope sees only this scheme's "
                 f"share of this gate's traffic.") if (loc.get("role") == "origin") else None
        out_gates.append({
            "gate_id": gid,
            "gate_name": grow.get("name"),
            "location_id": grow.get("location_id"),
            "location_name": loc_name,
            "loc_type": loc.get("loc_type") or "",
            "role": role,
            "laden_per_day": r1(g["laden"] / wd),
            "empty_per_day": r1(g["empty"] / wd),
            "arrivals_per_day": arr,
            "gap_minutes": gap,
            "gate_minutes": gm,
            "capacity_per_day": cap,
            "capacity_pct": cap_pct,
            # 14 Oct 2026 (W17): the "Queue likely" step in lorries a day (85 % of capacity), for the chart's guide tick
            "near_per_day": (0.0 if shut_all_day else (r1(cap_raw * gate_hours.NEAR_PCT / 100.0) if cap_raw is not None else None)),
            "flag": flag,
            "status_word": gate_hours.STATUS_WORDS.get(flag),
            "open_minutes": open_g,
            "open_basis": om["basis"],
            "open_hours": om["hours"],
            "peak_minutes": om["peak_minutes"],
            # 17 Oct 2026: the gate's shut windows, the minutes they take off (beyond the bands) and their words
            "shut_windows": om["shut"],
            "shut_minutes": om["shut_minutes"],
            "shut_words": om["shut_words"],
            "no_open_time": shut_all_day,
            "closed_days": gate_hours.closed_days_words(grow),
            "reason": (NO_OPEN_TIME if (shut_all_day and total > 0) else _reason(arr if total > 0 else None, gap, gm, cap_pct, amber)),
            "pending_lines": g["pending_lines"],
            "pending_per_day": r1(g["pending_trips"] / wd),
            "teams": [t[0] for t in teams],
            "per_team": per_team,
            "origin_share_note": share,
            "fallthrough_routes": sorted(g["fallthrough"]),
        })
    out_gates.sort(key=lambda x: (-x["arrivals_per_day"], x["gate_id"]))

    notes = []
    if approved_n == 0:
        notes.append(f"No approved lines in {label}.")
    if pending_n:
        word = "pending line" if pending_n == 1 else "pending lines"
        # lorries once, gate arrivals at every gate a lorry arrives by (two for a line
        # with a gate at each end) — the table below counts gate arrivals, so both are said
        notes.append(f"{pending_n} {word} in {label} would add {r1(pending_lorries_per_day)} "
                     f"lorries a day ({r1(pending_per_day_total)} gate arrivals across the gates "
                     f"below); they are not in the figures.")
    for (lid, _named), b in sorted(blocked_at.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        name = b["loc"].get("name") or lid
        n = len(b["routes"])
        routes_word = "1 route names" if n == 1 else f"{n} routes name"
        gate_word = (f"gate {b['blocked'].get('name')}, which is inactive"
                     if b["blocked"].get("reason") == "inactive" else "a gate that is no longer recorded")
        if b["to"]:
            notes.append(f"{name}: {routes_word} {gate_word}, so arrivals there are counted at {b['to']}.")
        else:
            no_gate_locs.pop(lid, None)
            notes.append(f"{name}: {routes_word} {gate_word}, and no other entry gate is recorded, "
                         f"so arrivals there are not shown.")
    for lid in sorted(no_gate_locs):
        name = no_gate_locs[lid].get("name") or lid
        notes.append(f"{name} has no entry gate recorded, so arrivals there are not shown.")
    # 17 Oct 2026: every gate has clock hours now (typed, or the default), so the bands come off every gate and the note
    # that they could not (the shift had no clock times) is gone; one note says what the averages rest on
    bands = gate_hours.peak_bands(factors)
    off = [w for w, on in (("its shut times", any(g["shut_windows"] for g in out_gates)),
                           ("the no-delivery bands", bool(bands))) if on]
    notes.append(f"Averages only, {SPREAD} across each gate's open hours"
                 + (f" ({dw} where none are typed)" if any(g["open_basis"] == "default" for g in out_gates) else "")
                 + (", less " + " and ".join(off) if off else "") + ". No hourly peak is typed.")

    # 22 Oct 2026 (abnormal loads, phase 2, D70): a marker on a gate's row for each abnormal load arriving there in the
    # month (and leaving, for a crane) — NEVER in laden, empty, arrivals, the gap or the capacity. A database without the
    # table must not take the panel down.
    try:
        import abnormal as _abnormal
        _markers = _abnormal.gate_markers(month_index, acc)
    except Exception:                            # noqa: BLE001
        _markers = {}
    for g in out_gates:
        g["abnormal"] = _markers.get(g["gate_id"], [])
    abnormal_total = len({m["id"] for ms in _markers.values() for m in ms})
    if abnormal_total:
        notes.append(f"{abnormal_total} abnormal load{'s' if abnormal_total != 1 else ''} this month are marked on their gates "
                     f"and counted apart: not in the arrivals, the gap or the capacity.")

    return {
        "month": int(month_index),
        "label": label,
        "working_days": wd,
        "shift_hours": sh,
        "abnormal_total": abnormal_total,
        # 17 Oct 2026: the default gate day (was the shift's minutes) and its hours, for the screen's words
        "open_minutes": open_m,
        "default_hours": dw,
        "scope": scope,
        "gates": out_gates,
        "notes": notes,
        # 14 Oct 2026 (W17): the 85 % step, the scheme's no-delivery windows and the printed limit
        "near_pct": gate_hours.NEAR_PCT,
        "peak_bands": bands,
        "limit": gate_hours.LIMIT_WORDS,
    }


def location_visits(month_index, factors=None, working_days=None):
    """
    14 Oct 2026 (bundle G, the CLP section's chart 1b): lorry VISITS a day at each LOCATION in a month —
    the rows, the Approved status and the trips rule of arrivals(), every team summed. A visit is one
    lorry in and out: laden where the location is the route's destination, coming to load where it is
    the origin. No gate is needed: a site's CLP cap is the site's, whichever gate a lorry uses.
    Returns {location_id: {laden_per_day, empty_per_day, visits_per_day, visits_raw}}.
    """
    factors = factors or conversions.load_factors()
    wd = _positive(working_days, _working_days(factors))
    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND month_index = ? AND status = 'Approved' "
        "ORDER BY route_id, discipline, section_id", (db.current_tenant(), int(month_index)))
    routes = {r["id"]: r for r in db.query(
        "SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?", (db.current_tenant(),))}
    acc_by = {}
    for row in rows:
        route = routes.get(row.get("route_id"))
        if not route:
            continue
        t = trips_for(row, factors)
        for key, end in (("dest_id", "laden"), ("origin_id", "empty")):
            lid = route.get(key)
            if not lid:
                continue
            e = acc_by.setdefault(lid, {"laden": 0, "empty": 0})
            e[end] += t
    return {lid: {"laden_per_day": r1(e["laden"] / wd), "empty_per_day": r1(e["empty"] / wd),
                  "visits_per_day": r1((e["laden"] + e["empty"]) / wd),
                  "visits_raw": (e["laden"] + e["empty"]) / wd}
            for lid, e in acc_by.items()}


DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def day_words(iso):
    """'2026-10-14' -> 'Wed 14 Oct'."""
    d = datetime.date.fromisoformat(str(iso)[:10])
    return f"{DAY_SHORT[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def week_by_day(lines, factors=None, dates=None):
    """
    14 Oct 2026 (bundle G, W17): the committed week by day at each gate, against what the gate can check in.
    `lines` are the Look-ahead's DECORATED lines for the bucket — every team's (clashes.py's rule: a sum
    across teams needs the unfiltered lines; the caller filters the flags, and no team's own figure is in
    the reply). Each day's trips (derived.day_figures, the grid's own) arrive at the destination's entry gate
    laden and at the origin's entry gate coming to load — the month panel's ends, by gates.resolve; a route
    naming a gate that is inactive or gone counts at the location's default entry gate (arrivals()'s rule).
    Capacity a day = the gate's open minutes ÷ its check-in minutes (gate_hours); a day the gate is closed
    (its open days) has capacity 0 and any arrival is over it. Status by gate_hours.status: amber "Queue
    likely" at 85 %, red "Over gate capacity". `_lines` on each day lists the line keys arriving there (for
    the clash rail; the caller strips it). Weekends are listed only when some gate has arrivals on them.
    """
    factors = factors or conversions.load_factors()
    routes = {r["id"]: r for r in db.query(
        "SELECT id, origin_id, dest_id, origin_gate_id, dest_gate_id FROM routes WHERE tenant_id = ?",
        (db.current_tenant(),))}
    locations = {l["id"]: l for l in db.query(
        "SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    gbl = gates.gates_by_location()
    gate_rows = {g["id"]: g for gs in gbl.values() for g in gs}
    per, keys, all_dates = {}, {}, set(dates or [])
    for l in lines or []:
        route = routes.get(l.get("route_id"))
        if not route:
            continue
        lk = (l["route_id"], int(l["month_index"]), l.get("discipline") or "", l.get("section_id") or "")
        for d in l.get("days") or []:
            all_dates.add(d["day_date"])
        for loc_key, gate_key in (("dest_id", "dest_gate_id"), ("origin_id", "origin_gate_id")):
            loc = locations.get(route.get(loc_key))
            if not loc:
                continue
            r, _blocked = entry_gate(loc, route.get(gate_key), gbl.get(loc["id"]) or [])
            gid = r.get("gate_id")
            if gid is None:
                continue
            for d in l.get("days") or []:
                t = int(((d.get("derived") or {}).get("trips")) or 0)
                if t <= 0:
                    continue
                g = per.setdefault(gid, {})
                g[d["day_date"]] = g.get(d["day_date"], 0) + t
                kl = keys.setdefault((gid, d["day_date"]), [])
                if lk not in kl:
                    kl.append(lk)
    busy_weekend = {iso for g in per.values() for iso, n in g.items()
                    if n > 0 and datetime.date.fromisoformat(iso).weekday() >= 5}
    shown = sorted(iso for iso in all_dates if datetime.date.fromisoformat(iso).weekday() < 5 or iso in busy_weekend)
    out = []
    for gid, byday in per.items():
        grow = gate_rows.get(gid) or {}
        loc = locations.get(grow.get("location_id")) or {}
        om = gate_hours.open_minutes(grow, factors)
        gm = grow.get("safety_minutes")
        gm = float(gm) if gm is not None else None
        cap_raw = gate_hours.capacity(om["minutes"], gm)
        days_out, worst, peak_pct = [], None, None
        for iso in shown:
            arr = int(byday.get(iso, 0))
            # 17 Oct 2026: a gate whose bands and shut windows leave it no open minute is shut all day, like a closed day
            open_today = gate_hours.is_open_on(grow, datetime.date.fromisoformat(iso)) and om["minutes"] > 0
            flag = gate_hours.status(arr, cap_raw, open_today)
            cap_day = (r1(cap_raw) if cap_raw is not None else None) if open_today else 0.0
            pct = round(arr * 100.0 / cap_raw) if (cap_raw and arr and open_today) else None
            if pct is not None:
                peak_pct = pct if peak_pct is None else max(peak_pct, pct)
            if flag == "red" or (flag == "amber" and worst is None):
                worst = flag
            days_out.append({"date": iso, "day": day_words(iso), "arrivals": arr, "capacity": cap_day, "pct": pct,
                             "open": open_today, "flag": flag, "status_word": gate_hours.STATUS_WORDS.get(flag),
                             "_lines": keys.get((gid, iso), [])})
        no_open = om["minutes"] <= 0
        out.append({"gate_id": gid, "gate_name": grow.get("name"), "location_id": grow.get("location_id"),
                    "location_name": loc.get("name") or grow.get("location_id") or "",
                    "check_in_minutes": gm, "open_minutes": om["minutes"], "open_basis": om["basis"],
                    "open_hours": om["hours"], "peak_minutes": om["peak_minutes"],
                    "shut_windows": om["shut"], "shut_minutes": om["shut_minutes"], "shut_words": om["shut_words"],
                    # 17 Oct 2026 (review): the bands and shut times leave no open minute — every day is shut
                    "no_open_time": no_open,
                    "closed_days": gate_hours.closed_days_words(grow),
                    "capacity_per_day": (0.0 if no_open else (r1(cap_raw) if cap_raw is not None else None)),
                    "near_per_day": (0.0 if no_open else (r1(cap_raw * gate_hours.NEAR_PCT / 100.0) if cap_raw is not None else None)),
                    "peak_pct": peak_pct, "flag": worst, "status_word": gate_hours.STATUS_WORDS.get(worst),
                    "days": days_out})
    order = {"red": 0, "amber": 1, None: 2}
    out.sort(key=lambda x: (order.get(x["flag"], 2), -(x["peak_pct"] or -1), -max([d["arrivals"] for d in x["days"]] or [0]),
                            x["gate_id"]))
    return {"dates": shown, "days": [day_words(i) for i in shown], "gates": out, "near_pct": gate_hours.NEAR_PCT,
            "limit": gate_hours.LIMIT_WORDS, "default_hours": gate_hours.default_words(factors),
            "peak_bands": gate_hours.peak_bands(factors)}


def strip_lines(gw):
    """The week's reply without the line keys clashes.py needs (they name other teams' lines)."""
    if not gw:
        return gw
    out = dict(gw)
    out["gates"] = [dict(g, days=[{k: v for k, v in d.items() if k != "_lines"} for d in g["days"]]) for g in gw.get("gates") or []]
    return out
