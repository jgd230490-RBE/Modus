"""
Look-ahead v2, slice 3 (2026-09-09) — the clash rail. FLAGS, NEVER BLOCKS.

Every code in the brief's §6, computed on read from the decorated day lines
(derived.decorate() output) plus the week layer, the stock read model and — when it can
be reached — Tark Tee. Nothing here is stored, nothing here refuses a confirm.

    SHORTAGE        last week's actual < planned and calibrate has not carried it
    DAYS_NE_WEEK    sum(day planned) ≠ week planned      (slice 1's flag, surfaced)
    STOCKPILE_OVER       the destination stockpile's forecast balance at week end > capacity
                    (27 Oct 2026: read from the forward balance, stockpiles.balances, so an Out
                    nobody has typed yet is the planned use, not 0)
    STOCKPILE_SOON  27 Oct 2026 (stockpile forecast, D7): the pile goes over, or runs out, in one of
                    the next 8 weeks — amber, on the commit week's lines into it. Not raised for a
                    pile with no planned use (it could only ever say "goes over")
    STOCKPILE_EMPTY 27 Oct 2026: the planned use in the commit week is more than the pile holds —
                    amber, "bring deliveries forward"
    ROUTE_CAP       max_vehicles_per_day typed on the route and the vehicles that day
                    on that route_id — across EVERY IPT — exceed it
    IPT_SHARE       two or more IPTs with quantity the same day on the same route_id,
                    or the same origin+dest, or the same haul-road id
    RESTRICTION     the country's road-restriction provider has a hit on the route's
                    baked geometry — a Tark Tee limit (EE), or a National Highways
                    planned closure (GB) whose dates overlap THIS week (HU4, 29 Sep).
                    Shown with the provider's word: "TARK TEE" / "ROADWORKS". Until H1
                    the code was TARK_TEE.
    GATE_OVER       14 Oct 2026 (bundle G, W17): planned arrivals at a gate on a day of the committed week are
                    more than it can check in (open minutes ÷ check-in minutes, gate_hours.py), or the gate is
                    closed that day — every team's lorries summed, on every line arriving there that day
    GATE_NEAR       the same at 85 % of capacity or more: "near capacity", a warning ("Queue likely")
    LIMIT           13 Oct 2026: the line's vehicle is over a weight / height / width limit
                    its baked route runs along (limits.py: OpenStreetMap and HERE). Only an
                    "exceeds" verdict for THIS line's vehicle and leg raises it; "except for
                    access" is said in the text. Standing limits: no week test.
    UNBAKED         quantity on a route not baked for the line's vehicle (slice 2)
    PARENT_CHANGED  the month moved under a set week (Task C's flag, surfaced)

Rules that are the module, not details:

* **Cross-IPT sums are computed on the UNFILTERED lines.** ROUTE_CAP and IPT_SHARE only
  mean something if they see every IPT's quantity on a route; an IPT code that could
  only see its own lines would never be told it shares a route. So the caller passes
  the whole tenant's decorated lines and the flags are then filtered to what the
  caller may see by `line_key` — the other IPT's quantity is never in the response,
  only the fact that it exists.
* **A source that cannot be reached says so.** The restriction provider is live data;
  when it is down the rail must not read "no restrictions" — `sources.restrictions` is
  'unavailable' and no RESTRICTION flag is raised or suppressed. Never cache a failure
  (warning-stack lesson).
  🔴 **And the LIVE check is never on a page read.** The page reads the STORED per-route
  check (restrictions.store_checks, run on demand or after a bake) and reports its age;
  a route never checked is listed as such, not shown clean.
* **Nothing invents a 40-trip constant.** ROUTE_CAP fires only on a typed cap.
"""
import datetime

import conversions
import db
import derived
import gate_arrivals
import limits
import restrictions
import stockpiles
import weeks

CODES = ("SHORTAGE", "DAYS_NE_WEEK", "STOCKPILE_OVER", "ROUTE_CAP", "GATE_OVER", "IPT_SHARE", "RESTRICTION",
         "LIMIT", "NO_WAY_ROUND", "UNBAKED", "GATE_NEAR", "STOCKPILE_EMPTY", "STOCKPILE_SOON", "PARENT_CHANGED")

#: The 98 % band (brief L5): a line "holds" when actual ≥ 98 % of planned.
HOLD_BAND = 0.98


def line_key(l):
    return (l["route_id"], int(l["month_index"]), l.get("discipline") or "",
            l.get("section_id") or "")


def _flag(code, line, text, **extra):
    d = {"code": code, "route_id": line.get("route_id"), "month_index": line.get("month_index"),
         "discipline": line.get("discipline") or "", "section_id": line.get("section_id") or "",
         "ipt": line.get("ipt"), "text": text}
    d.update(extra)
    return d


def _label(line):
    c = line.get("context") or {}
    o, d = c.get("origin_name") or line.get("route_id"), c.get("dest_name") or ""
    return f"{o} → {d}" if d else str(o)


def _dist_word():
    """'km' or 'mi' — the tenant's reading unit (HU5). 29 Sep 2026 first look: the
    UNBAKED text said "km omitted" on a miles tenant's Look-ahead, XLSX and PDF."""
    try:
        import config as _config
        import conversions as _conversions
        return "mi" if (_config.tenant_settings(_conversions).get("distance_unit") or "km") == "mi" else "km"
    except Exception:
        return "km"


# --------------------------------------------------------------------------- #
#  Per-line flags                                                              #
# --------------------------------------------------------------------------- #
def per_line(lines, account_rows):
    """
    UNBAKED, DAYS_NE_WEEK, PARENT_CHANGED from the decorated lines; SHORTAGE from the
    account week's rows (keyed by line key, minus week_index).
    """
    out = []
    short = {}
    for a in account_rows or []:
        if a.get("actual_qty") is None:
            continue
        planned, actual = float(a.get("planned_qty") or 0), float(a["actual_qty"])
        if planned <= 0 or actual >= HOLD_BAND * planned:
            continue
        # carried already? calibrated_qty records the variance carried; a shortage
        # remains only for the part not yet carried
        variance = planned - actual
        carried = float(a.get("calibrated_qty") or 0)
        if variance - carried > 1e-6:
            short[(a["route_id"], a.get("discipline") or "", a.get("section_id") or "")] = {
                "short": round(variance - carried, 3), "unit": a.get("unit")}
    for l in lines:
        c = l.get("context") or {}
        if derived.FLAG_UNBAKED in (c.get("flags") or []):
            out.append(_flag("UNBAKED", l,
                             f"{_label(l)} is not baked for {c.get('vehicle_short') or conversions.vehicle_word_rule(c.get('vehicle_type')) or 'its vehicle'} — {_dist_word()} omitted on that line"))
        if l.get("days_ne_week"):
            out.append(_flag("DAYS_NE_WEEK", l,
                             f"days ≠ week on {_label(l)} — days sum {l.get('days_sum')} against week {(l.get('week') or {}).get('planned_qty')}",
                             days_sum=l.get("days_sum"), week_qty=(l.get("week") or {}).get("planned_qty")))
        if (l.get("week") or {}).get("parent_changed"):
            out.append(_flag("PARENT_CHANGED", l, f"month changed under {_label(l)}'s set week"))
        k = (l["route_id"], l.get("discipline") or "", l.get("section_id") or "")
        if k in short:
            s = short[k]
            out.append(_flag("SHORTAGE", l,
                             f"{_label(l)} last week {s['short']:g} {s['unit'] or ''} short, not yet carried".strip(),
                             short=s["short"]))
    return out


# --------------------------------------------------------------------------- #
#  Cross-line flags (need every IPT's lines)                                   #
# --------------------------------------------------------------------------- #
def route_cap(lines):
    """ROUTE_CAP: per route per day, vehicles across every line vs the typed cap."""
    by = {}                                   # (route_id, date) -> [veh_sum, cap, lines]
    for l in lines:
        c = l.get("context") or {}
        cap = c.get("max_vehicles_per_day")
        if cap is None:
            continue
        for d in l.get("days", []) or []:
            v = (d.get("derived") or {}).get("vehicles")
            if not v:
                continue
            e = by.setdefault((l["route_id"], d["day_date"]), [0, int(cap), []])
            e[0] += int(v)
            e[2].append(l)
    out = []
    for (rid, day), (veh, cap, ls) in sorted(by.items()):
        if veh > cap:
            for l in ls:
                out.append(_flag("ROUTE_CAP", l,
                                 f"{rid} {day}: {veh} veh against a cap of {cap}",
                                 day_date=day, vehicles=veh, cap=cap))
    return out


def gate_capacity(lines, gw):
    """
    14 Oct 2026 (bundle G, W17): GATE_OVER / GATE_NEAR from gate_arrivals.week_by_day (every team's lines),
    one flag per line arriving at the gate that day. The text names the gate, the day and the figures —
    the gate's total, never another team's share. Flags, never blocks.
    """
    by_key = {line_key(l): l for l in lines or []}
    out = []
    for g in (gw or {}).get("gates") or []:
        where = f"{g['location_name']}, {g['gate_name']}"
        for d in g["days"]:
            if d["flag"] not in ("red", "amber"):
                continue
            code = "GATE_OVER" if d["flag"] == "red" else "GATE_NEAR"
            if not d["open"] and g.get("no_open_time"):
                # 17 Oct 2026 (review): not a closed day — the bands and the gate's shut times cover all its hours
                text = (f"{where} on {d['day']}: {d['arrivals']} lorries planned, but the no-delivery bands and the "
                        f"gate's shut times leave it no open time")
            elif not d["open"]:
                text = (f"{where} on {d['day']}: {d['arrivals']} lorries planned, but the gate is "
                        f"{g['closed_days'] or 'closed that day'}")
            else:
                text = (f"{where} on {d['day']}: {d['arrivals']} lorries against the {g['capacity_per_day']:g} it can "
                        f"check in ({d['pct']} %)" + ("" if code == "GATE_OVER" else ", near capacity"))
            for lk in d.get("_lines") or []:
                l = by_key.get(lk)
                if l is None:
                    continue
                out.append(_flag(code, l, text, day_date=d["date"], gate_id=g["gate_id"], arrivals=d["arrivals"],
                                 capacity=d["capacity"], pct=d["pct"]))
    return out


def ipt_share(lines):
    """
    IPT_SHARE: two+ IPTs with quantity the same day on the same route_id, the same
    origin+dest, or the same haul-road id. One flag per (line, day, reason).
    """
    haul, haul_name = {}, {}
    # the haul road's NAME rides on the same read (a join, no second query): the text names it
    for r in db.query("SELECT h.route_id, h.zone_id, z.name FROM route_haul_roads h "
                      "LEFT JOIN zones z ON z.tenant_id = h.tenant_id AND z.id = h.zone_id "
                      "WHERE h.tenant_id = ?", (db.current_tenant(),)):
        haul.setdefault(r["route_id"], set()).add(r["zone_id"])
        if r.get("name"):
            haul_name[r["zone_id"]] = r["name"]
    od_name = {}                              # "L014→L007" -> "Harborough → Langton"
    # group key -> date -> {ipt: [lines]}
    groups = {}
    for l in lines:
        ipt = l.get("ipt")
        if not ipt:
            continue                          # a line with no IPT cannot share one
        c = l.get("context") or {}
        keys = [("route", l["route_id"])]
        if c.get("origin_id") and c.get("dest_id"):
            od = f"{c['origin_id']}→{c['dest_id']}"
            keys.append(("od", od))
            if c.get("origin_name") and c.get("dest_name"):
                od_name.setdefault(od, f"{c['origin_name']} → {c['dest_name']}")
        for z in haul.get(l["route_id"], ()):
            keys.append(("haul", z))
        for d in l.get("days", []) or []:
            if float(d.get("planned_qty") or 0) <= 0:
                continue
            for k in keys:
                groups.setdefault(k, {}).setdefault(d["day_date"], {}).setdefault(ipt, []).append(l)
    out, seen = [], set()
    for (kind, what), days in groups.items():
        for day, by_ipt in days.items():
            if len(by_ipt) < 2:
                continue
            ipts = sorted(by_ipt)
            for ipt, ls in by_ipt.items():
                for l in ls:
                    sig = (line_key(l), day, kind, what)
                    if sig in seen:
                        continue
                    seen.add(sig)
                    # 17 Oct 2026: the text names the PLACES. Until then it printed the location
                    # ids ("on the same haul L014→L007") and the haul road's zone id, which no
                    # page turns into a name. The route keeps its id: R021 is the route's
                    # reference a person reads everywhere (Routes page, row details "Route",
                    # route sheet, ROUTE_CAP's text). The team ids stay in the text — the app
                    # (teamText) and the exports (team_text) show the tenant's team names (G2).
                    # share_id keeps the ids (machine field, never printed).
                    where = {"route": f"on route {what}",
                             "od": f"on the same haul {od_name.get(what) or 'between the same two places'}",
                             "haul": f"on {haul_name.get(what) or 'the same haul road'}"}[kind]
                    out.append(_flag("IPT_SHARE", l,
                                     f"{' + '.join(ipts)} {where} on {day}",
                                     day_date=day, ipts=ipts, share=kind, share_id=what))
    return out


# --------------------------------------------------------------------------- #
#  Stock and road restrictions                                                 #
# --------------------------------------------------------------------------- #
def _qty(q):
    """26 200 — whole units, grouped with a space as the app prints them."""
    return f"{round(float(q)):,}".replace(",", " ")


def _week_of(m, w):
    """'22 Mar' — the Monday of a week, as the flags name it."""
    mon = weeks.week_span(m, w)[0]
    return f"{mon.day} {mon.strftime('%b')}"


def stock_forecast(lines, month_index, week_index):
    """
    Per stockpile: the commit week from the forward balance (stockpiles.balances, 27 Oct
    2026): opening (the balance at the end of the week before), what comes in and goes out
    in the week, the balance at its end, and whether it goes over or runs out this week or
    in the next 8 weeks. Stockpiles with no capacity are listed with `over` False.

    `lines` is kept for the call's shape; the week's lines are what the balance reads.
    """
    mi, wi = int(month_index), int(week_index)
    bal = stockpiles.balances(1, min(mi + 3, max(mi, 60)))
    pm, pw = weeks.prev_week(mi, wi)
    out = []
    for sp in bal["stockpiles"]:
        rows = sp["weeks"]
        wk = {(w["month_index"], w["week_index"]): w for w in rows}
        prev = wk.get((pm, pw))
        this = wk.get((mi, wi)) or {}
        opening = float(prev["balance_end"]) if prev else float(sp.get("opening_qty") or 0)
        forecast = float(this.get("balance_end", opening))
        cap = sp.get("capacity_qty")
        # the 8 weeks AFTER the commit week
        after = [w for w in rows if (w["month_index"], w["week_index"]) > (mi, wi)][:stockpiles.AHEAD_WEEKS]
        soon_over = next((w for w in after if w["over"]), None)
        soon_empty = next((w for w in after if w.get("empty")), None)
        out.append({
            "location_id": sp["location_id"], "name": sp["name"],
            "unit": sp["capacity_unit"], "capacity_qty": cap,
            "forecast_pile": bool(sp.get("forecast")), "use_planned": bool(sp.get("use_planned")),
            "opening": round(opening, 3), "inbound_planned": round(float(this.get("inbound", 0)), 3),
            "consume": round(float(this.get("consumed", 0)), 3),
            "forecast": round(forecast, 3),
            "remaining": (round(cap - forecast, 3) if cap is not None else None),
            "over": bool(cap is not None and forecast > cap),
            "over_by": (round(forecast - cap, 3) if cap is not None and forecast > cap else None),
            "short": round(float(this.get("short") or 0), 3),
            "empty": bool(this.get("empty")),
            "soon_over": ({"month_index": soon_over["month_index"], "week_index": soon_over["week_index"],
                           "balance_end": soon_over["balance_end"]} if soon_over else None),
            "soon_empty": ({"month_index": soon_empty["month_index"], "week_index": soon_empty["week_index"],
                            "balance_end": soon_empty["balance_end"]} if soon_empty else None),
            "unconvertible_lines": sp.get("unconvertible_movements", 0),
        })
    return out


def _unit_word(u):
    return "m³" if u == "m3" else (u or "t")


def stockpile_over(lines, stock):
    """STOCKPILE_OVER on every line whose destination stockpile forecasts over capacity."""
    over = {s["location_id"]: s for s in stock if s.get("over")}
    out = []
    for l in lines:
        c = l.get("context") or {}
        s = over.get(c.get("dest_id"))
        if s:
            u = _unit_word(s["unit"])
            out.append(_flag("STOCKPILE_OVER", l,
                             f"{s['name']}: {_qty(s['forecast'])} {u} forecast at the week's end, "
                             f"{_qty(s['over_by'])} {u} over its {_qty(s['capacity_qty'])} {u}.",
                             location_id=s["location_id"], over_by=s["over_by"]))
    return out


def stockpile_soon(lines, stock):
    """
    27 Oct 2026 (D7). STOCKPILE_EMPTY when the commit week's planned use is more than the pile
    holds; STOCKPILE_SOON when it goes over, or runs out, in one of the next 8 weeks. Both amber,
    on the week's lines into the pile; neither for a pile already over this week (STOCKPILE_OVER
    says it) nor for a pile with no planned use.
    """
    by = {s["location_id"]: s for s in stock if s.get("use_planned") and not s.get("over")}
    out = []
    for l in lines:
        c = l.get("context") or {}
        s = by.get(c.get("dest_id"))
        if not s:
            continue
        u = _unit_word(s["unit"])
        if s.get("empty"):
            want = s["consume"] + s["short"]
            held = s["opening"] + s["inbound_planned"]
            out.append(_flag("STOCKPILE_EMPTY", l,
                             f"{s['name']} runs out this week: {_qty(want)} {u} planned use, "
                             f"{_qty(held)} {u} in stock. Bring deliveries forward.",
                             location_id=s["location_id"], short=s["short"]))
            continue
        so, se = s.get("soon_over"), s.get("soon_empty")
        first = min([x for x in (so, se) if x], key=lambda x: (x["month_index"], x["week_index"]), default=None)
        if first is None:
            continue
        if first is so:
            text = (f"{s['name']} goes over {_qty(s['capacity_qty'])} {u} in the week of "
                    f"{_week_of(so['month_index'], so['week_index'])} (forecast {_qty(so['balance_end'])} {u}).")
        else:
            text = f"{s['name']} runs out in the week of {_week_of(se['month_index'], se['week_index'])}."
        out.append(_flag("STOCKPILE_SOON", l, text, location_id=s["location_id"],
                         week={"month_index": first["month_index"], "week_index": first["week_index"]},
                         kind=("over" if first is so else "empty")))
    return out


def _overlaps_span(hit, span_from, span_to):
    """
    HU4 (decided 29 Sep 2026): a DATED hit counts only in the span it overlaps. `from`
    and `to` are ISO dates on the stored hit (NULL = open-ended, as in restrictions.
    in_force). An undated hit — a Tark Tee mass or height limit — always counts. With
    no span given (a caller without a bucket) every hit counts, as before H1.

    12 Oct 2026: generalised from the week so the bulletin can ask the same question of a
    calendar month (weeks.month_span). One rule, two callers; `_overlaps_week` is kept
    as the week-shaped name the Look-ahead and its harness use.
    """
    if span_from is None or span_to is None:
        return True
    a, b = hit.get("from"), hit.get("to")
    try:
        a = datetime.date.fromisoformat(str(a)[:10]) if a else None
        b = datetime.date.fromisoformat(str(b)[:10]) if b else None
    except ValueError:
        return True                       # an unreadable date must not hide a hit
    if a and a > span_to:
        return False
    if b and b < span_from:
        return False
    return True


def _overlaps_week(hit, week_from, week_to):
    """The week-shaped name: see _overlaps_span."""
    return _overlaps_span(hit, week_from, week_to)


def restriction(lines, month_index=None, week_index=None):
    """
    RESTRICTION from the STORED per-route check (restrictions.store_checks) — a DB read,
    instant, always part of the page. `month_index` / `week_index` name the bucket the
    lines belong to, so a dated hit (a planned closure) is raised only when its dates
    overlap that week. Returns (flags, source) where source says how current the stored
    result is:

        status      'ok' every route on the page has a stored check
                    'partial' some have, some never checked (or re-baked since)
                    'unchecked' none has
                    'skipped' no baked line on the page
        checked_at  the OLDEST stored check among the page's routes
        unchecked   the routes with no stored check — a refresh fills them

    🔴 History: the live check (six services + a geometry loop) was on the page's
    critical path on 09 Sep and froze the Look-ahead; then, off the path, it still took
    30 s+ per read. It now runs on demand / after a bake and is stored on the route.
    A stored result is never a silent clean: the source block carries its age.
    """
    routes = sorted({l["route_id"] for l in lines if (l.get("context") or {}).get("baked")})
    prov = restrictions.provider() or {}
    if not routes:
        return [], {"status": "skipped", "checked_at": None, "unchecked": [], "routes": [],
                    "provider": prov.get("key"), "flag_label": prov.get("flag_label")}
    wf = wt = None
    if month_index is not None and week_index is not None:
        try:
            wf, wt = weeks.week_span(int(month_index), int(week_index))
        except Exception:
            wf = wt = None
    stored = restrictions.stored_checks(routes)
    unchecked = [r for r in routes if not (stored.get(r) or {}).get("checked_at")]
    checked = [stored[r]["checked_at"] for r in routes if (stored.get(r) or {}).get("checked_at")]
    status = ("unchecked" if len(unchecked) == len(routes)
              else "partial" if unchecked else "ok")
    out = []
    word = prov.get("kind_word") or "restriction"
    for l in lines:
        st = stored.get(l["route_id"]) or {}
        hits = [h for h in (st.get("hits") or []) if isinstance(h, dict) and _overlaps_week(h, wf, wt)]
        if hits:
            first = hits[0]
            what = first.get("headline") or first.get("layer") or f"a {word}"
            extra = {"from": first.get("from"), "to": first.get("to")} if prov.get("dated") else {}
            out.append(_flag("RESTRICTION", l,
                             f"{_label(l)} crosses {what}" + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""),
                             hits=len(hits), checked_at=st.get("checked_at"),
                             label=prov.get("flag_label") or "RESTRICTION",
                             provider=prov.get("key"), **extra))
    return out, {"status": status, "checked_at": (min(checked) if checked else None),
                 "unchecked": unchecked, "routes": routes,
                 "provider": prov.get("key"), "flag_label": prov.get("flag_label"),
                 "week": ([wf.isoformat(), wt.isoformat()] if wf and wt else None)}


def _diversion_touches(periods, line):
    """True when one of a diversion's date runs [{"from", "to"}] touches the line's week (or month)."""
    try:
        import route_choice
        days = (route_choice.week_days(int(line["month_index"]), int(line["week_index"]))
                if line.get("week_index") is not None else route_choice.month_days(int(line["month_index"])))
    except Exception:
        return True
    if not days:
        return False
    lo, hi = days[0].isoformat(), days[-1].isoformat()
    return any((not p.get("from") or p["from"] <= hi) and (not p.get("to") or p["to"] >= lo) for p in periods)


def limit(lines):
    """
    LIMIT (13 Oct 2026) from the STORED per-route limits check (limits.store_checks): the
    line's own vehicle is over a limit on a leg of its baked route. One flag per line,
    naming the first breach and how many more. Returns (flags, source) like restriction().
    """
    routes = sorted({l["route_id"] for l in lines if (l.get("context") or {}).get("baked")})
    if not routes:
        return [], {"status": "skipped", "checked_at": None}
    stored = limits.stored_checks(routes)
    checked = [stored[r]["checked_at"] for r in routes if (stored.get(r) or {}).get("checked_at")]
    out = []
    for l in lines:
        veh = (l.get("context") or {}).get("vehicle_type") or l.get("vehicle_type")
        # 13 Oct 2026 (W6): the rule and the words live in limits.py, shared with costlines
        hits = limits.exceeding(stored.get(l["route_id"]), veh)
        # 28 Oct 2026 (task 0c): a limit on a diversion counts only in a week its dates touch
        hits = [h for h in hits if not h.get("diversion") or _diversion_touches(h["diversion"], l)]
        if not hits:
            continue
        h = hits[0]
        text = f"{_label(l)}: {limits.breach_text(hits, veh)}"
        out.append(_flag("LIMIT", l, text, label="ROAD LIMIT", hits=len(hits),
                         kind=h.get("kind"), limit=h.get("limit"), unit=h.get("unit"),
                         source=h.get("source"), checked_at=(stored.get(l["route_id"]) or {}).get("checked_at")))
    return out, {"status": "ok" if checked else "unchecked", "checked_at": (min(checked) if checked else None)}


#: 28 Oct 2026 (task 0c): why a line still runs through a dated zone in force this week, in the rail's words
NO_WAY_WORDS = {"needs_route": "no way round found yet",
                "no_way_round": "there is no road round it",
                "declined": "kept on the main route"}


def no_way_round(lines):
    """
    NO_WAY_ROUND (28 Oct 2026, task 0c): a dated zone with Affects routing is in force on some of this week's days
    and the line's route still goes through it — no stored option misses it yet, HERE found no road round it, or the
    planner kept the main route (route_choice). One flag per line, from its context (derived.cycle_for's mix).
    """
    try:
        import zones as _zones
        names = {z["id"]: z.get("name") for z in _zones.list_zones()}
    except Exception:
        names = {}
    out = []
    for l in lines:
        probs = (l.get("context") or {}).get("diversion_problems") or []
        if not probs:
            continue
        p = probs[0]
        zn = ", ".join(names.get(z) or z for z in (p.get("zone") or "").split(",") if z)
        text = f"{_label(l)}: {zn} is in force; {NO_WAY_WORDS.get(p.get('status'), 'no way round')}."
        out.append(_flag("NO_WAY_ROUND", l, text, label="NO WAY ROUND", zone=p.get("zone"),
                         status=p.get("status"), date_from=p.get("from"), date_to=p.get("to")))
    return out


# --------------------------------------------------------------------------- #
#  The rail                                                                    #
# --------------------------------------------------------------------------- #
def compute(all_lines, visible_keys, account_rows, month_index, week_index,
            with_restrictions=True):
    """
    Every flag for the visible lines. `all_lines` is the WHOLE tenant's decorated lines
    (cross-IPT sums need them); `visible_keys` is the set of line_key() the caller may
    see, and only their flags are returned.
    """
    stock = stock_forecast(all_lines, month_index, week_index)
    flags = []
    flags += per_line(all_lines, account_rows)
    flags += route_cap(all_lines)
    # 14 Oct 2026 (bundle G, W17): the committed week at each gate, against what it can check in
    try:
        gw = gate_arrivals.week_by_day(all_lines)
    except Exception as e:                       # a missing column on an old database must not take the rail down
        gw = {"dates": [], "days": [], "gates": [], "error": str(e)[:120]}
    flags += gate_capacity(all_lines, gw)
    flags += ipt_share(all_lines)
    flags += stockpile_over(all_lines, stock)
    flags += stockpile_soon(all_lines, stock)
    flags += no_way_round(all_lines)              # 28 Oct 2026 (task 0c)
    # the STORED check — a DB read, so it is always on. `with_restrictions=False` is for a
    # caller that wants the rail without it (none today).
    prov = restrictions.provider() or {}
    tt_source = {"status": "off", "checked_at": None, "unchecked": [], "routes": [],
                 "provider": prov.get("key"), "flag_label": prov.get("flag_label")}
    if with_restrictions:
        tt, tt_source = restriction(all_lines, month_index, week_index)
        flags += tt
    lim_source = {"status": "off", "checked_at": None}
    try:
        lim, lim_source = limit(all_lines)
        flags += lim
    except Exception as e:                       # a missing column on an old database
        lim_source = {"status": "error: " + str(e)[:80], "checked_at": None}
    vis = [f for f in flags
           if (f["route_id"], int(f["month_index"]), f["discipline"], f["section_id"]) in visible_keys]
    order = {c: i for i, c in enumerate(CODES)}
    vis.sort(key=lambda f: (order.get(f["code"], 99), f["route_id"], f.get("day_date") or ""))
    by_code = {}
    for f in vis:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
    return {"flags": vis, "count": len(vis), "by_code": by_code,
            "codes": list(CODES), "hold_band": HOLD_BAND,
            "gates_week": gate_arrivals.strip_lines(gw),
            "sources": {"restrictions": tt_source["status"], "restrictions_checked_at": tt_source["checked_at"],
                        "restrictions_unchecked": tt_source["unchecked"],
                        "restrictions_refresh": restrictions.refresh_state(),
                        "restrictions_provider": tt_source.get("provider"),
                        "restrictions_label": tt_source.get("flag_label"),
                        "restrictions_ui_label": prov.get("ui_label"),
                        "restrictions_week": tt_source.get("week"),
                        "limits": lim_source.get("status"), "limits_checked_at": lim_source.get("checked_at")},
            "stock": stock}
