"""
Week 1, 2026-09-01 (Task D2) — stockpile max capacity and typed weekly consumption.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is **storage on a location**: how much a pile can hold, how much was in it to
start with, and how much somebody typed as consumed in a given week. It is NOT the
haul/gate capacity model — that is Phase 5a/5b, it lives on routes and gates, and
nothing here touches it.

There is no file, no CSV, no importer and no upload endpoint. Consumption is typed.

THE BALANCE IS A READ MODEL
---------------------------
Nothing below is stored. `balances()` recomputes every time from what people typed:
the forecast lines and their week rows, typed Out (`stockpile_weeks.consumed_qty`), the
stock counts (`stockpile_weeks.measured_qty`), the planned use (`stockpile_plan`) and the
opening stock (`locations.opening_qty`, the stock at the start of month 1).

    balance_end(W) = count(W) if a stock count is typed, else balance_end(W-1) + In(W) - Out(W)
    remaining      = capacity_qty - balance_end        (null when no capacity is set)
    over           = balance_end > capacity_qty

Storing it would be a second copy that drifts the moment anyone edits an actual, and
actuals are edited constantly — that is the point of the look-ahead.

27 OCT 2026 — THE BALANCE RUNS FORWARD (stockpile forecast; John's decisions D1–D11)
------------------------------------------------------------------------------------
A place with a CAPACITY or a PLANNED USE (D8) gets a forecast. Weeks before the current
week are PAST, the current week and later are FORECAST.

    In(W)   every APPROVED line whose route ENDS at the pile, one line-week at a time:
            past + actual typed -> the actual; past + nothing typed -> the plan, counted in
            `not_recorded` (D2); forecast -> the week row's planned_qty (edited, confirmed,
            calibrated) or else the approved month / its 4 or 5 weeks.
    Out(W)  a typed Out is everything that left the pile (D3), road hauls out included.
            Otherwise the plan: the month's planned use / its weeks, plus approved lines
            whose route STARTS at the pile (actual or plan, as for In).
            ⚠️ A planned Out never takes more than the pile holds: the rest is `short`, and
            the week is `empty` (decided 27 Oct) — that is what STOCKPILE EMPTY reports.

⚠️ THIS REVERSES THE OLD RULE 1 ("no week actual means inbound 0") for those piles, on
purpose: with it every unrecorded week read as nothing, and the demo's piles sat at 0–2 %.
The plan standing in is labelled (`basis`, `in_basis`, `out_basis`, `not_recorded`), and a
stock count is how a site corrects it.

⚠️ WHAT IT STILL DOES NOT GUESS
-------------------------------
1. **A place with neither a capacity nor a planned use keeps the old rule**: inbound is
   the typed actuals only, Out is the typed figure only. A compound that uses what arrives
   would otherwise fill with every planned delivery (D8).
2. **A route with no dest_id contributes nothing.** Old routes may have a null
   destination. Attributing their tonnage to the nearest pile would be inventing it.
3. **No capacity recorded is not zero capacity.** `remaining` comes back null and
   `over` stays false; the balance still computes and the UI shows "—" for max.
4. **Pending and Rejected lines never count.**

The running total starts at month_index 1 regardless of the window asked for, because
`opening_qty` is defined as the stock at the start of month 1. Windowing the sum as
well as the output would silently drop everything that happened before the window.
"""
import datetime

import conversions
import db
import weeks as weeks_mod

# Location types that can hold stock. The build list names these four for the capacity
# fields; a Quarry or a Port is a source, not a store, and showing it a capacity box
# invites a number nobody means.
STORAGE_TYPES = ("Stockpile", "Site", "Compound", "Railhead")

# The build list's default. Applied on WRITE, not as a column default — see the note in
# db.init_weeks_db() for why "not recorded" has to stay distinguishable from "tonnes".
DEFAULT_CAPACITY_UNIT = "t"
CAPACITY_UNITS = ("m3", "t")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
#  Master data                                                                 #
# --------------------------------------------------------------------------- #
def set_capacity(location_id, capacity_qty=None, capacity_unit=None, opening_qty=None):
    """
    Write a location's storage figures.

    Passing capacity_qty=None CLEARS the capacity, which is a real state — "we do not
    know how big this pile is" — and not the same as zero. The unit defaults to tonnes
    only when a capacity is actually being set.
    """
    cur = db.query("SELECT id, loc_type FROM locations WHERE tenant_id = ? AND id = ?",
                   (db.current_tenant(), location_id))
    if not cur:
        return {"error": "location not found"}
    cap = _num(capacity_qty)
    unit = (capacity_unit or "").strip() or None
    if cap is not None and unit not in CAPACITY_UNITS:
        unit = DEFAULT_CAPACITY_UNIT
    if cap is None:
        unit = unit if unit in CAPACITY_UNITS else None
    db.execute(
        "UPDATE locations SET capacity_qty = ?, capacity_unit = ?, opening_qty = ? "
        "WHERE tenant_id = ? AND id = ?",
        (cap, unit, _num(opening_qty), db.current_tenant(), location_id))
    return {"location_id": location_id, "capacity_qty": cap, "capacity_unit": unit,
            "opening_qty": _num(opening_qty)}


def storage_locations():
    """
    Locations that can hold stock, with their capacity figures.

    Two ways in, and the second one matters. A location of one of the four storage
    types is always listed, even with nothing recorded against it — that is how a new
    pile appears so somebody can give it a capacity. Anything ELSE is listed only once
    a figure has actually been entered against it, which is how a Quarry or a Port
    whose role is destination-or-both (the case the Data Management form shows the
    capacity fields for) reaches the panel without dragging in all 27 nodes that have
    never held anything.
    """
    rows = db.query(
        "SELECT id, name, loc_type, role, material, capacity_qty, capacity_unit, "
        "opening_qty FROM locations WHERE tenant_id = ? ORDER BY id",
        (db.current_tenant(),))
    import network  # local: network imports stockpiles, so this cannot be top-level
    for r in rows:
        r["loc_type"] = network.canonical_loc_type(r.get("loc_type"))
    return [r for r in rows
            if (r.get("loc_type") or "") in STORAGE_TYPES
            or r.get("capacity_qty") is not None
            or r.get("opening_qty") is not None]


# --------------------------------------------------------------------------- #
#  Consumption                                                                 #
# --------------------------------------------------------------------------- #
def consume(location_id, month_index, week_index, consumed_qty=None, unit=None,
            note=None, by=None):
    """Upsert one week's typed consumption for one location."""
    if not db.query("SELECT id FROM locations WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), location_id)):
        return {"error": "location not found"}
    wi = int(week_index)
    n_weeks = weeks_mod.weeks_in_month(month_index)
    if not 1 <= wi <= n_weeks:
        return {"error": f"week_index must be 1-{n_weeks} for month {month_index}"}
    q = _num(consumed_qty)
    u = (unit or DEFAULT_CAPACITY_UNIT)
    have = db.query(
        "SELECT location_id FROM stockpile_weeks WHERE tenant_id = ? "
        "AND location_id = ? AND month_index = ? AND week_index = ?",
        (db.current_tenant(), location_id, int(month_index), wi))
    if have:
        db.execute(
            "UPDATE stockpile_weeks SET consumed_qty = ?, unit = ?, note = ?, "
            "updated_by = ?, updated_at = ? WHERE tenant_id = ? AND location_id = ? "
            "AND month_index = ? AND week_index = ?",
            (q, u, note, by, _now(), db.current_tenant(), location_id,
             int(month_index), wi))
    else:
        db.execute(
            "INSERT INTO stockpile_weeks (tenant_id, location_id, month_index, "
            "week_index, consumed_qty, unit, note, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), location_id, int(month_index), wi, q, u, note,
             by, _now()))
    return {"location_id": location_id, "month_index": int(month_index),
            "week_index": wi, "consumed_qty": q, "unit": u}


# --------------------------------------------------------------------------- #
#  27 Oct 2026 — the plan and the count (stockpile forecast, D1 a and D5)       #
# --------------------------------------------------------------------------- #
def plan_rows(location_id=None):
    """{(location_id, month_index): planned_qty} — each pile's planned use by month."""
    sql = ("SELECT location_id, month_index, planned_qty FROM stockpile_plan "
           "WHERE tenant_id = ?")
    args = [db.current_tenant()]
    if location_id:
        sql += " AND location_id = ?"
        args.append(location_id)
    return {(r["location_id"], int(r["month_index"])): float(r["planned_qty"])
            for r in db.query(sql, tuple(args)) if r.get("planned_qty") is not None}


def set_plan(location_id, from_month, to_month=None, planned_qty=None, note=None, by=None):
    """
    Type a pile's planned use for one month, or the same figure for every month from–to
    ("Same each month from … to …"). The figure is in the pile's own unit. None CLEARS the
    month(s): no plan is not the same as a plan of 0.
    """
    loc = [l for l in storage_locations() if l["id"] == location_id]
    if not loc:
        return {"error": "That place cannot hold stock."}
    lo = int(from_month)
    hi = int(to_month if to_month is not None else from_month)
    if hi < lo:
        lo, hi = hi, lo
    if lo < 1:
        return {"error": "The first month is before the programme starts."}
    q = _num(planned_qty)
    if q is not None and q < 0:
        return {"error": "Planned use cannot be below zero."}
    unit = loc[0].get("capacity_unit") or DEFAULT_CAPACITY_UNIT
    for m in range(lo, hi + 1):
        db.execute("DELETE FROM stockpile_plan WHERE tenant_id = ? AND location_id = ? "
                   "AND month_index = ?", (db.current_tenant(), location_id, m))
        if q is not None:
            db.execute(
                "INSERT INTO stockpile_plan (tenant_id, location_id, month_index, planned_qty, "
                "unit, note, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (db.current_tenant(), location_id, m, q, unit, note, by, _now()))
    return {"location_id": location_id, "from_month": lo, "to_month": hi,
            "planned_qty": q, "unit": unit}


def set_count(location_id, month_index, week_index, measured_qty=None, note=None, by=None):
    """
    A stock count (a survey) at the end of one week, in the pile's unit. It replaces the
    worked-out balance from that week on; the difference shows as the count adjustment.
    None clears it.
    """
    loc = [l for l in storage_locations() if l["id"] == location_id]
    if not loc:
        return {"error": "That place cannot hold stock."}
    wi = int(week_index)
    n_weeks = weeks_mod.weeks_in_month(month_index)
    if not 1 <= wi <= n_weeks:
        return {"error": f"That month has {n_weeks} weeks."}
    q = _num(measured_qty)
    if q is not None and q < 0:
        return {"error": "A stock count cannot be below zero."}
    have = db.query(
        "SELECT location_id FROM stockpile_weeks WHERE tenant_id = ? AND location_id = ? "
        "AND month_index = ? AND week_index = ?",
        (db.current_tenant(), location_id, int(month_index), wi))
    if have:
        db.execute(
            "UPDATE stockpile_weeks SET measured_qty = ?, updated_by = ?, updated_at = ? "
            "WHERE tenant_id = ? AND location_id = ? AND month_index = ? AND week_index = ?",
            (q, by, _now(), db.current_tenant(), location_id, int(month_index), wi))
    else:
        db.execute(
            "INSERT INTO stockpile_weeks (tenant_id, location_id, month_index, week_index, "
            "consumed_qty, unit, note, updated_by, updated_at, measured_qty) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.current_tenant(), location_id, int(month_index), wi, None,
             loc[0].get("capacity_unit") or DEFAULT_CAPACITY_UNIT, note, by, _now(), q))
    return {"location_id": location_id, "month_index": int(month_index), "week_index": wi,
            "measured_qty": q}


# --------------------------------------------------------------------------- #
#  The balance read model                                                      #
# --------------------------------------------------------------------------- #
def _to_pile_unit(qty, from_unit, pile_unit, material, vehicle, factors):
    """
    Convert one movement into the pile's own unit.

    A forecast line can be entered in m3, tonnes or vehicles while a pile's capacity is
    in tonnes; adding those together untouched would produce a number with no meaning.
    conversions.py pivots everything through tonnes using the material density and the
    vehicle payload, so both are needed — which is why the parent forecast row is read
    for material_type and vehicle_type rather than the week row alone.

    ⚠️ A conversion that cannot be done returns None and the caller drops the movement
    rather than adding a raw figure. That undercounts visibly; adding it would
    overcount invisibly.
    """
    if qty is None:
        return None
    fu = from_unit or pile_unit
    if fu == pile_unit:
        return float(qty)
    try:
        return conversions.convert(float(qty), fu, pile_unit, material, vehicle, factors)
    except Exception:
        return None


#: how far ahead STOCKPILE SOON and the Account's "Next 8 weeks" look (D7)
AHEAD_WEEKS = 8
#: a week "runs out" when at least this much planned use cannot be met (one tonne or m³)
EMPTY_MIN = 1.0


def _flow():
    return {"rec": 0.0, "plan": 0.0, "plan_unrec": 0.0, "lines": 0, "unrec": 0}


#: 27 Oct 2026: the last few whole computations, keyed on the data version and the current week, so one page that
#: reads the balance three times (the Account rows, the rail, the Horizon strip) works it out once
_MEMO = {}
_MEMO_MAX = 6


def balances(from_month, to_month, location_id=None, today=None):
    """
    Per-location, per-week stock for a month window.

    The running total starts at month 1 whatever window is asked for; only the OUTPUT
    is windowed. See the module docstring: a pile with a capacity or a planned use runs
    FORWARD from the plan; any other place keeps the records-only figure.
    """
    lo, hi = min(int(from_month), int(to_month)), max(int(from_month), int(to_month))
    cur = weeks_mod.editable_week(today=today)
    key = (db.current_tenant(), db.data_version(), cur, location_id)
    full = _MEMO.get(key)
    if full is None or full["to"] < hi:
        full = _balances_full(hi, location_id, cur)
        if len(_MEMO) >= _MEMO_MAX:
            _MEMO.pop(next(iter(_MEMO)))
        _MEMO[key] = full
    return {"from": lo, "to": hi, "current_week": full["current_week"],
            "stockpiles": [dict(sp, weeks=[dict(w) for w in sp["weeks"] if lo <= w["month_index"] <= hi])
                           for sp in full["stockpiles"]]}


def _balances_full(hi, location_id, cur):
    """Every week from month 1 to the end of the plan (never short of `hi`), for every place that holds stock."""
    lo = 1
    factors = conversions.load_factors()

    locs = storage_locations()
    if location_id:
        locs = [l for l in locs if l["id"] == location_id]
    if not locs:
        return {"from": lo, "to": hi, "current_week": {"month_index": cur[0], "week_index": cur[1]},
                "stockpiles": []}

    tenant = db.current_tenant()
    cm, cw = cur                                            # the current week: past is before it
    plans = plan_rows(location_id)
    planned_locs = {k[0] for k in plans}
    fc_ids = {l["id"] for l in locs
              if _num(l.get("capacity_qty")) is not None or l["id"] in planned_locs}

    routes = {r["id"]: r for r in db.query(
        "SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?", (tenant,))}
    dest_of = {k: r.get("dest_id") for k, r in routes.items()}
    # the parent forecast lines, for material and vehicle — a week row carries neither
    parents = db.query(
        "SELECT route_id, month_index, discipline, section_id, quantity, unit, status, "
        "material_type, vehicle_type FROM forecasts WHERE tenant_id = ?", (tenant,))
    parent = {(f["route_id"], f["month_index"], f["discipline"] or "", f["section_id"] or ""): f
              for f in parents}
    week_rows = db.query(
        "SELECT route_id, month_index, discipline, section_id, week_index, planned_qty, "
        "actual_qty, unit FROM forecast_weeks WHERE tenant_id = ?", (tenant,))
    wrow = {(w["route_id"], w["month_index"], w["discipline"] or "", w["section_id"] or "",
             int(w["week_index"])): w for w in week_rows}
    sw_rows = db.query(
        "SELECT location_id, month_index, week_index, consumed_qty, unit, measured_qty "
        "FROM stockpile_weeks WHERE tenant_id = ?", (tenant,))

    # how far the forward balance runs: to the end of the plan, never short of the window
    last_m = hi
    for f in parents:
        if f["status"] == "Approved":
            last_m = max(last_m, int(f["month_index"]))
    for (_, m) in plans:
        last_m = max(last_m, m)
    n_weeks = {m: weeks_mod.weeks_in_month(m) for m in range(1, last_m + 1)}
    # each week's Monday, so a screen can say "the week of 22 Mar" without its own calendar
    _mon = {}

    def week_from(m, w):
        if (m, w) not in _mon:
            _mon[(m, w)] = weeks_mod.week_span(m, w)[0].isoformat()
        return _mon[(m, w)]
    is_past = lambda m, w: (m, w) < (cm, cw)

    # -- road lines into and out of the forecast piles, one line-week at a time (§2) ----------
    pile_unit = {l["id"]: (l.get("capacity_unit") or DEFAULT_CAPACITY_UNIT) for l in locs}
    mat_of = {l["id"]: l.get("material") for l in locs}
    flows = {lid: {"in": {}, "out": {}} for lid in fc_ids}
    dropped = {l["id"]: 0 for l in locs}
    for key, f in parent.items():
        if f["status"] != "Approved":
            continue
        r = routes.get(f["route_id"]) or {}
        ends = [(r.get("dest_id"), "in"), (r.get("origin_id"), "out")]
        ends = [(lid, way) for lid, way in ends if lid in fc_ids]
        if not ends:
            continue
        m = int(f["month_index"])
        if m > last_m:
            continue
        for wi in range(1, n_weeks[m] + 1):
            w = wrow.get(key + (wi,))
            if w is not None and w.get("planned_qty") is not None:
                plan_q, plan_u = w["planned_qty"], w.get("unit") or f.get("unit")
            else:
                plan_q, plan_u = float(f["quantity"] or 0) / n_weeks[m], f.get("unit")
            act_q = w.get("actual_qty") if w is not None else None
            for lid, way in ends:
                pu = pile_unit[lid]
                mat = f.get("material_type") or mat_of.get(lid)
                pv = _to_pile_unit(plan_q, plan_u, pu, mat, f.get("vehicle_type"), factors)
                av = (_to_pile_unit(act_q, (w.get("unit") or f.get("unit")), pu, mat,
                                    f.get("vehicle_type"), factors) if act_q is not None else None)
                if pv is None or (act_q is not None and av is None):
                    dropped[lid] += 1
                    continue
                c = flows[lid][way].setdefault((m, wi), _flow())
                c["lines"] += 1
                c["plan"] += pv
                if av is not None:
                    c["rec"] += av
                else:
                    c["unrec"] += 1
                    c["plan_unrec"] += pv

    # -- records-only places: today's rule, unchanged (actuals only, typed Out only) ---------
    rec_in = {}
    for w in week_rows:
        if w.get("actual_qty") is None or int(w["month_index"]) > last_m:
            continue
        lid = dest_of.get(w["route_id"])
        if lid is None or lid in fc_ids or lid not in pile_unit:
            continue
        p = parent.get((w["route_id"], w["month_index"], w["discipline"] or "",
                        w["section_id"] or "")) or {}
        v = _to_pile_unit(w["actual_qty"], w["unit"], pile_unit[lid],
                          p.get("material_type") or mat_of.get(lid), p.get("vehicle_type"), factors)
        if v is None:
            dropped[lid] += 1
            continue
        k = (lid, int(w["month_index"]), int(w["week_index"]))
        rec_in[k] = rec_in.get(k, 0.0) + v

    typed_out, counts = {}, {}
    for c in sw_rows:
        lid = c["location_id"]
        if lid not in pile_unit:
            continue
        k = (lid, int(c["month_index"]), int(c["week_index"]))
        if c.get("consumed_qty") is not None:
            v = _to_pile_unit(c["consumed_qty"], c["unit"], pile_unit[lid], mat_of.get(lid), None, factors)
            if v is None:
                dropped[lid] += 1
            else:
                typed_out[k] = v
        if c.get("measured_qty") is not None and lid in fc_ids:
            counts[k] = float(c["measured_qty"])

    out = []
    for loc in locs:
        lid = loc["id"]
        unit = pile_unit[lid]
        cap = _num(loc.get("capacity_qty"))
        opening = _num(loc.get("opening_qty")) or 0.0
        forecast = lid in fc_ids
        has_plan = lid in planned_locs
        running = opening
        rows, ahead = [], []
        m_end = last_m
        for m in range(1, m_end + 1):
            nw = n_weeks.get(m) or weeks_mod.weeks_in_month(m)
            for wi in range(1, nw + 1):
                k = (lid, m, wi)
                if not forecast:
                    inb = rec_in.get(k, 0.0)
                    con = typed_out.get(k, 0.0)
                    running = running + inb - con
                    rows.append({
                        "month_index": m, "week_index": wi,
                        "inbound": round(inb, 3), "consumed": round(con, 3),
                        "balance_end": round(running, 3),
                        # null, NOT zero, when no capacity is recorded
                        "remaining": (round(cap - running, 3) if cap is not None else None),
                        "over": bool(cap is not None and running > cap),
                        "unit": unit, "basis": "recorded", "from": week_from(m, wi)})
                    continue
                past = is_past(m, wi)
                fin = flows[lid]["in"].get((m, wi)) or _flow()
                fout = flows[lid]["out"].get((m, wi)) or _flow()
                use_plan = plans.get((lid, m), 0.0) / nw
                # In: the recorded figure, the plan standing in for any line not recorded (D2)
                if past:
                    inb = fin["rec"] + fin["plan_unrec"]
                    in_basis = ("none" if not fin["lines"] else "recorded" if not fin["unrec"]
                                else "plan" if fin["unrec"] == fin["lines"] else "part")
                else:
                    inb, in_basis = fin["plan"], ("forecast" if fin["lines"] else "none")
                # Out: a typed Out is everything that left (D3); otherwise the plan
                plan_out = use_plan + fout["plan"]
                typed = typed_out.get(k)
                short = 0.0
                if typed is not None:
                    con, out_basis = typed, "recorded"
                else:
                    want = (use_plan + fout["rec"] + fout["plan_unrec"]) if past else plan_out
                    avail = max(0.0, running + inb)
                    # planned use never takes more than the pile holds (decided 27 Oct): the
                    # shortfall is what STOCKPILE EMPTY reports
                    con = min(want, avail)
                    short = want - con
                    out_basis = ("none" if want <= 0 else "plan" if past else "forecast")
                computed = running + inb - con
                cnt = counts.get(k)
                running = cnt if cnt is not None else computed
                not_rec = (fin["unrec"] if past else 0) + (1 if past and typed is None and plan_out > 0 else 0)
                if not past:
                    basis = "forecast"
                elif in_basis in ("recorded", "none") and out_basis in ("recorded", "none"):
                    basis = "recorded"
                elif in_basis in ("plan", "none") and out_basis in ("plan", "none"):
                    basis = "plan"
                else:
                    basis = "part"
                row = {
                    "month_index": m, "week_index": wi,
                    "inbound": round(inb, 3), "consumed": round(con, 3),
                    "balance_end": round(running, 3),
                    "remaining": (round(cap - running, 3) if cap is not None else None),
                    "over": bool(cap is not None and running > cap),
                    "unit": unit, "basis": basis, "in_basis": in_basis, "out_basis": out_basis,
                    "from": week_from(m, wi),
                    "plan_in": round(fin["plan"], 3), "plan_out": round(plan_out, 3),
                    # what was RECORDED coming in (None when no line into it has an actual yet)
                    "in_recorded": (round(fin["rec"], 3) if past and fin["lines"] > fin["unrec"] else None),
                    "not_recorded": not_rec, "short": round(short, 3),
                    # runs out: at least one whole unit of planned use cannot be met (less is the
                    # rounding of a typed monthly plan), or a typed Out took more than was there
                    "empty": bool(short >= EMPTY_MIN or running < -1e-9),
                    "count": cnt, "count_adjust": (round(cnt - computed, 3) if cnt is not None else None),
                }
                if not past:
                    ahead.append(row)
                rows.append(row)
        sp = {
            "location_id": lid, "name": loc["name"],
            "loc_type": loc.get("loc_type"), "role": loc.get("role"),
            "capacity_qty": cap, "capacity_unit": unit,
            "opening_qty": opening,
            "unconvertible_movements": dropped[lid],
            "forecast": forecast, "use_planned": has_plan,
            "weeks": rows,
        }
        if forecast:
            wk = lambda r: ({"month_index": r["month_index"], "week_index": r["week_index"], "from": r["from"],
                             "balance_end": r["balance_end"], "short": r["short"]} if r else None)
            first_over = next((r for r in ahead if r["over"]), None)
            first_empty = next((r for r in ahead if r["empty"]), None)
            peak = max(ahead, key=lambda r: r["balance_end"]) if ahead else None
            near = ahead[:AHEAD_WEEKS]
            sp.update({
                "first_over": wk(first_over), "first_empty": wk(first_empty), "peak": wk(peak),
                "peak_pct": (round(peak["balance_end"] * 100 / cap, 1) if peak and cap else None),
                # STOCKPILE SOON's question: over, or runs out, within the next 8 weeks
                "soon_over": wk(next((r for r in near if r["over"]), None)),
                "soon_empty": wk(next((r for r in near if r["empty"]), None)),
                "near_peak_pct": (round(max(r["balance_end"] for r in near) * 100 / cap, 1)
                                  if near and cap else None),
            })
        out.append(sp)
    return {"from": lo, "to": last_m, "current_week": {"month_index": cm, "week_index": cw},
            "stockpiles": out}


def popup_summary(location_id):
    """
    'Stock 1 240 t / 3 000 t' for the public map popup, or None.

    Returns None rather than a half-sentence when either number is missing — the build
    list asks for the string only "when both numbers exist". The balance is taken at
    the LAST week of the current month, which is the most recent complete figure.
    """
    locs = [l for l in storage_locations() if l["id"] == location_id]
    if not locs:
        return None
    loc = locs[0]
    if _num(loc.get("capacity_qty")) is None:
        return None
    today = datetime.date.today()
    mi = weeks_mod.month_index_of(today, START_YEAR)
    if mi < 1:
        return None
    b = balances(mi, mi, location_id=location_id)["stockpiles"]
    if not b or not b[0]["weeks"]:
        return None
    last = b[0]["weeks"][-1]
    return {"balance": last["balance_end"], "capacity": b[0]["capacity_qty"],
            "unit": b[0]["capacity_unit"], "over": last["over"]}


# month_index 1 == January of this year. Mirrors main.START_YEAR; imported lazily to
# avoid a circular import, and asserted equal in the tests.
START_YEAR = 2026
