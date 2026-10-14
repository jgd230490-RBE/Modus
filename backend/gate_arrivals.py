"""
Gate arrivals (11 Oct 2026) — lorries a day at each gate for one month, every team summed.

THE DECISION (the user, 11 Oct 2026, late night)
------------------------------------------------
A staff-only "Gate arrivals" panel on the Dashboard. For each gate and month: the laden
arrivals a day at the DESTINATION's entry gate PLUS the empty arrivals (lorries coming to
load) at the ORIGIN's entry gate, summed across ALL teams. Average gap in minutes = the
tenant's shift hours × 60 ÷ arrivals a day. The gate's minutes per lorry is its existing
typed check-in (`location_gates.safety_minutes`); no new field, no data change, no
re-import. Red ONLY when the average gap is shorter than that check-in — a queue even with
perfect spacing. No amber. A gate with no check-in typed is never compared. Approved lines
make the figure; pending lines are a note, never in the figure.

14 Oct 2026 (bundle G, W17, the user's D42 follow-up): the gate's OWN open hours when typed (less the
scheme's peak bands, the no-delivery windows) replace the shift for that gate, and an AMBER step joins
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
* working days and shift hours: the planning block's figures, the costlines.py and
  derived.py rules (22 and 10 when untyped). main passes its own _working_days in.
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
    """The derived.py rule: the planning block's shift, 10 h when untyped."""
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
    open_m = sh * 60.0
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
            r = gates.resolve(loc, "entry", named, gates=loc_gates)
            blocked = r.get("blocked")
            if blocked:
                # the route names a gate that is inactive or no longer recorded. resolve
                # refuses to pick another (the bake must not quietly move to a different
                # road), but the lorries on an approved line still arrive: count them at
                # the location's default entry gate and say so in a note.
                r = gates.resolve(loc, "entry", None, gates=loc_gates)
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
        # 14 Oct 2026 (W17): the gate's OWN open minutes when its hours are typed (less the scheme's peak bands, the
        # no-delivery windows), else the scheme's shift — gate_hours.open_minutes, the one rule
        om = gate_hours.open_minutes(grow, factors)
        open_g = om["minutes"]
        gap = r1(open_g / arr_raw) if (total > 0 and open_g > 0) else (0.0 if total > 0 else None)
        gm = grow.get("safety_minutes")
        gm = float(gm) if gm is not None else None
        red = gm is not None and gap is not None and gap < gm
        # 14 Oct 2026 (the Dashboard's gate chart): the gate's CAPACITY, the most lorries it can check in a day if they
        # arrive evenly = the open minutes ÷ its check-in minutes a lorry — the red rule turned round (gap < check-in
        # ⇔ arrivals > capacity), sent from here so the browser only draws it. No check-in typed: no capacity.
        cap_raw = gate_hours.capacity(open_g, gm)
        cap = r1(cap_raw) if cap_raw is not None else None
        cap_pct = (round(arr_raw * 100.0 / cap_raw) if (cap_raw and total > 0) else None)
        # 14 Oct 2026 (W17, the user's 85 % step): amber "Queue likely" at 85 % of capacity or more, below the red rule
        amber = (not red) and cap_raw is not None and total > 0 and arr_raw * 100.0 / cap_raw >= gate_hours.NEAR_PCT - 1e-9
        flag = "red" if red else ("amber" if amber else None)
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
            "near_per_day": (r1(cap_raw * gate_hours.NEAR_PCT / 100.0) if cap_raw is not None else None),
            "flag": flag,
            "status_word": gate_hours.STATUS_WORDS.get(flag),
            "open_minutes": open_g,
            "open_basis": om["basis"],
            "open_hours": om["hours"],
            "peak_minutes": om["peak_minutes"],
            "closed_days": gate_hours.closed_days_words(grow),
            "reason": _reason(arr if total > 0 else None, gap, gm, cap_pct, amber),
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
    if any(g["open_basis"] == "gate" for g in out_gates):
        notes.append(f"Averages only, {SPREAD} across each gate's open hours (the {sh:g} h shift where a gate has "
                     f"none typed). No hourly peak is typed.")
    else:
        notes.append(f"Averages only, {SPREAD} across the {sh:g} h shift. No hourly peak is typed.")
    bands = gate_hours.peak_bands(factors)
    if bands and any(g["open_basis"] == "shift" for g in out_gates):
        notes.append(f"The peak bands ({gate_hours.peak_words(bands)}, no deliveries) are taken off only the gates "
                     f"with open hours typed: the scheme's shift has no clock times.")

    return {
        "month": int(month_index),
        "label": label,
        "working_days": wd,
        "shift_hours": sh,
        "open_minutes": open_m,
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
