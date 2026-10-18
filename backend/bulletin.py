"""
bulletin.py — the monthly bulletin's server half (B4, 12 Oct 2026; review §2.6, D10 / D28).

WHAT THIS IS
------------
The month roll-up the public map's figures bar computes in the browser (`calculateKPIs`,
map/index.html), reproduced on the server from the SAME per-line payload the bar reads
(`/api/public/month-kpis`, called as a function here, not over HTTP), whole scheme, no
sidebar filters — plus the "conditions of the month" the map assembles from three sources,
read from what is STORED rather than from a live check. The HTML / PDF composition is
bulletin_doc.py (C4: the HTML page and the PDF from one view model); this module returns JSON only.

THE BAR'S RULES, AS REPRODUCED (one function, `rollup_payloads`, so a harness can hand it
the same payload the browser gets and assert equality)
------------------------------------------------------------------------------------------
  1. A line whose route is not drawn on the map (no baked laden geometry for any vehicle)
     is NOT counted — the map never sees it. It is NAMED here (`routes_not_drawn`), never
     silently dropped and never counted as zero.
  2. Two-way movements a day = the FRACTIONAL vehicle-loads of the month summed, ÷ working
     days. One load = one delivery = one two-way movement (out laden, back empty), never
     doubled, never rounded per line.
  3. Vehicles needed = Σ per LINE ceil((loads ÷ working days) ÷ what one vehicle can do a
     day on THAT route). Ceil per line, never once over the total: a vehicle on one route
     cannot also be working another. 17 Oct 2026: "a day" is a driver's day under the UK
     drivers' hours (drivers_hours.lorry_day: the shift less the required break, driving at
     most 9 h), read from route_analysis's trips_per_day like every other surface.
  4. A line whose route is not baked for ITS vehicle has no cycle: it is counted in the
     movements and the tonnes, left out of the fleet, and the fleet says "excludes N
     lines with no stored road route for the vehicle" — named, not zeroed. (The map bar
     still says "unbaked"; the bulletin is read by councils and says it in plain words.)
  5. Over a window of months the fleet is the BUSIEST month's, not the average: a fleet
     one lorry short in the peak month is short.
  6. Every per-day average divides by the months WITH volume, not the window length.
  7. CO2e a day = Σ the lines' co2_t (routed km × the vehicle's kg CO2e/km, the costlines
     figure) ÷ working days; a null co2_t (unbaked) is counted and named, not zeroed.
  8. The material card: in a vehicles unit "loads a day" IS the two-way figure, so it is
     shown for tonnes / m³ only. Tonnes is always the third headline, whatever the unit.
  9. The busiest routes: ranked by two-way movements a day (loads ÷ months the route
     appeared in ÷ working days), the top five, labelled origin → destination.
 10. The breakdown: per discipline (from the LINE), per team (from the ROUTE, named by the
     tenant's label, never an id), per work section (from the line); each group's rate is
     divided by the months IT appeared in; the group fleet is Σ ceil per line, so the rows
     add up to the headline.
 11. Working days come from main._working_days(factors) — the one reader of the planning
     block's day count. This module never reads that key and carries no fallback day count
     of its own (test_bulletin.py greps it for the literal).

ACCESS
------
The figures are the scheme's (they are the public map's figures). A team code gets the
same page as a planner: the headline, routes, carbon AND every team's breakdown row (D37,
decided 12 Oct 2026: the per-team limit hid nothing a team code could not work out, since
the headline less its own row is the other teams' total). The page's scope note says so
(SCOPE_NOTE_TEAM). Team ids never leave this module: `taxonomy.team_text` names them.

WHAT THIS DOES NOT DO
---------------------
No PDF, no HTML, no email, no stored snapshot, no actuals (plan only), no per-road-section
figure (that needs the shared-section layer, review §2.2d). Nothing here says a cap is
enforced: a typed cap is a "planning flag", and the wording says so.
"""
import datetime
import math
import re

import access
import carbon
import clashes
import config
import conversions
import db
import restrictions
import stockpiles
import taxonomy
import weeks

# The words a person reads. Asserted in test_bulletin.py and http_smoke.py.
CAP_WORDING = "planning flag"
NO_CAP_WORDING = "no planning cap typed"
NEVER_CHECKED = "never checked"
BUSIEST_N = 5
SCOPE_NOTE_TEAM = ("The figures are the whole scheme's, as the public map shows them to anyone with the map "
                   "password: the headline, the busiest routes and the discipline, section and team rows "
                   "include every team.")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_LONG = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")


def stockpile_wording(name, capacity_qty, balance_end, unit, month_index):
    """
    The sentence a person reads about a stockpile over capacity (D23, 12 Oct 2026). The
    balance is a running total of the week ACTUALS typed on the Look-ahead, carried
    forward — not a plan figure — so it is "recorded in it", never "the plan puts".
    """
    u = unit or "t"
    # 12 Oct 2026 (the review and fix pass): "has a capacity of", not "holds" — "holds" read as
    # what is in the pile now, and the next figure is a different "contents" figure
    return (f"{name} has a capacity of {float(capacity_qty):,.0f} {u}; {float(balance_end):,.0f} {u} "
            f"recorded in it at the end of {month_label(month_index)}, from the week actuals typed so far, "
            "carried forward.")


# --------------------------------------------------------------------------- #
#  The inputs — the same functions the public map's endpoints run                #
# --------------------------------------------------------------------------- #
def _main():
    # main imports this module; the import is deferred so neither side is half-loaded
    import main
    return main


def working_days(factors=None):
    """The planning month's working days — main._working_days, the one reader."""
    return _main()._working_days(factors or conversions.load_factors())


def month_payload(month_index, unit="vehicles"):
    """One month of approved forecast per line — `/api/public/month-kpis` as a function."""
    return _main().public_month_kpis(month=int(month_index), unit=unit)


def drawn_routes():
    """
    {route_id: properties of the laden leg} for every route the public map draws — the
    browser's routePropsById(), from the same `public_map_data()` the map fetches. A route
    with no baked laden geometry for any vehicle is absent, and the bar never counts it.
    """
    import network
    out = {}
    for f in (network.public_map_data() or {}).get("features", []) or []:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        if g.get("type") == "LineString" and p.get("route_id") and p.get("type") == "Inbound Highway":
            out[p["route_id"]] = p
    return out


def month_label(month_index, start_year=None):
    y, m = weeks._month_of(month_index, start_year)
    return f"{_MONTHS[m - 1]} {y}"


def month_label_long(month_index, start_year=None):
    y, m = weeks._month_of(month_index, start_year)
    return f"{_MONTHS_LONG[m - 1]} {y}"


# --------------------------------------------------------------------------- #
#  The roll-up (pure: payloads in, figures out)                                  #
# --------------------------------------------------------------------------- #
def _route_in_scope(route_ipt, scope):
    """Does a route's team field (which may read 'A / B' on a shared route) name the slot?"""
    if not scope:
        return True
    parts = re.split(r"[/,+&]", str(route_ipt or ""))
    return any(access.canonical_ipt(p) == scope for p in parts)


def _lines(n):
    return "line" if n == 1 else "lines"


def _avg(xs):
    return (sum(xs) / len(xs)) if xs else 0.0


def _r(v, dp=3):
    return None if v is None else round(float(v), dp)


def rollup_payloads(payloads, routes, wd, acc=None, unit="vehicles", labels=None,
                    team_word=None, section_names=None, discipline_names=None):
    """
    The eleven rules over one or more month payloads (each the dict
    `/api/public/month-kpis` returns), `routes` = drawn_routes(), `wd` = working_days().
    Pure: no database read, so a harness can hand it a payload and the map's rules side
    by side. `acc` limits the per-team rows only.
    """
    wd = float(wd)
    scope = (acc or {}).get("ipt")
    labels = taxonomy.team_labels() if labels is None else labels
    word = team_word or taxonomy._team_word()
    section_names = section_names or {}
    discipline_names = discipline_names or {}
    fb_name = (payloads[0] or {}).get("payload_fallback_vehicle") if payloads else None
    # 14 Oct 2026: the NAME a reader sees (the key may say "Truck mixer"; conversions.vehicle_label)
    fb_name = conversions.vehicle_label(conversions.load_factors(), fb_name) if fb_name else None

    m_veh, m_qty, m_t, m_fleet, m_co2 = [], [], [], [], []
    routes_in, not_drawn = set(), {}
    unbaked_lines = co2_unbaked = co2_lines = fell_back = lines_counted = 0
    groups = {"discipline": {}, "team": {}, "section": {}}
    by_route = {}

    for pi, p in enumerate(payloads):
        mk = p.get("month") if p.get("month") is not None else pi
        veh = qty = tonnes = co2 = 0.0
        fleet, any_line = 0, False
        for l in p.get("lines", []) or []:
            rid = l.get("route_id")
            rp = routes.get(rid)
            if not rp:
                not_drawn[rid] = not_drawn.get(rid, 0) + 1       # rule 1: named, not counted
                continue
            any_line = True
            lines_counted += 1
            loads = float(l.get("vehicle_loads") or 0.0)         # rule 2: fractional
            veh += loads
            qty += float(l.get("qty_unit") or 0.0)
            t = float(l.get("qty_t") or 0.0)
            tonnes += t
            routes_in.add(rid)
            if l.get("co2_t") is not None:                       # rule 7
                co2 += float(l["co2_t"])
                co2_lines += 1
            else:
                co2_unbaked += 1
            tpv = l.get("trips_per_vehicle_day")
            line_fleet = None
            if tpv and float(tpv) > 0:
                line_fleet = math.ceil((loads / wd) / float(tpv))   # rule 3: ceil per line
                fleet += line_fleet
            else:
                unbaked_lines += 1                               # rule 4: named, not zeroed
            if l.get("payload_fallback"):
                fell_back += 1
            keys = {
                "discipline": l.get("discipline") or "unassigned",
                # `word` handed in: team_text would otherwise read the tenant settings
                # for every line, and this function promises no database read
                "team": taxonomy.team_text(rp.get("ipt"), labels, word) or f"no {str(word).lower()}",
                "section": l.get("section_id") or "no work section",
            }
            for by, key in keys.items():                         # rule 10
                if by == "team" and scope and not _route_in_scope(rp.get("ipt"), scope):
                    continue
                g = groups[by].setdefault(key, {"veh": 0.0, "t": 0.0, "fleet": 0, "months": set()})
                g["veh"] += loads
                g["t"] += t
                g["fleet"] += line_fleet or 0
                g["months"].add(mk)
            br = by_route.setdefault(rid, {"rp": rp, "months": {}})
            bm = br["months"].setdefault(mk, {"veh": 0.0, "t": 0.0, "fleet": 0, "co2": 0.0,
                                              "co2_unbaked": 0, "unbaked": 0, "lines": 0})
            bm["veh"] += loads
            bm["t"] += t
            bm["lines"] += 1
            if line_fleet is None:
                bm["unbaked"] += 1
            else:
                bm["fleet"] += line_fleet
            if l.get("co2_t") is None:
                bm["co2_unbaked"] += 1
            else:
                bm["co2"] += float(l["co2_t"])
        if any_line:                                             # rule 6: months with volume
            m_veh.append(veh)
            m_qty.append(qty)
            m_t.append(tonnes)
            m_fleet.append(fleet)
            m_co2.append(co2)

    n = len(m_veh)
    not_drawn_block = {"lines": sum(not_drawn.values()), "routes": sorted(not_drawn),
                       "note": ("Lines on routes the map does not draw (no stored road route for any vehicle) "
                                "are not in these figures. They are listed here, not counted as zero.")
                       if not_drawn else None}
    if not n:
        nd_lines, nd_routes = sum(not_drawn.values()), len(not_drawn)
        empty_note = ("No approved forecast in this month." if not not_drawn else
                      f"No approved forecast on a route the map draws in this month: {nd_lines} line"
                      f"{'' if nd_lines == 1 else 's'} on {nd_routes} route{'' if nd_routes == 1 else 's'} "
                      "with no stored road route yet, listed below and not counted.")
        return {"empty": True, "months_with_volume": 0, "working_days": wd,
                "headline": {"two_way_a_day": None, "movements_in_month": None,
                             "working_days": wd, "routes_in_use": 0, "tonnes": None},
                "vehicles": {"fleet": None, "excludes_unbaked_lines": 0, "label": "Vehicles needed",
                             "not_baked": False},
                "material": {"shown": unit != "vehicles", "unit": unit, "per_day": None},
                "carbon": _carbon_block(None, None, 0, payloads, routes, wd, co2_lines=0),
                "busiest_routes": [], "by_route": [], "breakdown": {"discipline": [], "team": [], "section": []},
                "routes_not_drawn": not_drawn_block, "payload_fallback": {"lines": 0, "vehicle": fb_name},
                "note": empty_note}

    fleet_peak = max(m_fleet)                                    # rule 5: busiest month
    two_way_a_day = _avg(m_veh) / wd
    unb_label = (f"excludes {unbaked_lines} {_lines(unbaked_lines)} with no stored road route for the vehicle"
                 if unbaked_lines else None)

    # rule 9: the busiest routes, with the four figures the page prints per route
    ranked = []
    for rid, br in by_route.items():
        ms = br["months"]
        gm = max(1, len(ms))
        veh_sum = sum(x["veh"] for x in ms.values())
        rp = br["rp"]
        cap = _cap_of(rp)
        ranked.append((veh_sum / gm / wd, rid, {
            "route_id": rid,
            "origin": rp.get("origin") or rid, "dest": rp.get("dest") or "",
            "label": f"{rp.get('origin') or rid} → {rp.get('dest') or ''}".strip(),
            "two_way_a_day": _r(veh_sum / gm / wd),
            "movements_in_month": _r(veh_sum / gm),
            "vehicles": max(x["fleet"] for x in ms.values()),
            "vehicles_excludes_unbaked_lines": max(x["unbaked"] for x in ms.values()),
            "co2_t": _r(sum(x["co2"] for x in ms.values()) / gm),
            "co2_excludes_unbaked_lines": max(x["co2_unbaked"] for x in ms.values()),
            "tonnes": _r(sum(x["t"] for x in ms.values()) / gm),
            "months_with_volume": len(ms),
            "cap": cap,
            "cap_wording": CAP_WORDING if cap is not None else NO_CAP_WORDING,
        }))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    busiest = [row for _, _, row in ranked[:BUSIEST_N]]
    # 12 Oct 2026 (C4, the bulletin's page 2 chart): EVERY drawn route of the window, ranked the same
    # way and with the same four figures, so the chart and the busiest list cannot disagree
    by_route = [row for _, _, row in ranked]

    # rule 10: the breakdown rows, sorted by tonnes like the bar's chips
    breakdown = {}
    for by, gs in groups.items():
        rows = []
        for key, g in gs.items():
            gm = max(1, len(g["months"]))
            row = {"key": key, "name": key,
                   "vehicles_a_day": _r(g["fleet"] / gm), "two_way_a_day": _r(g["veh"] / gm / wd),
                   "tonnes_a_day": _r(g["t"] / gm / wd), "months_with_volume": len(g["months"])}
            if by == "section" and key in section_names:
                row["name"] = section_names[key]
            # 17 Oct 2026: the discipline row is NAMED by the tenant's label ("Pavement"), the key stays the id
            # ("superstructure"). Until then the bulletin's "What is being moved" table printed the ids.
            if by == "discipline" and key in discipline_names:
                row["name"] = discipline_names[key]
            rows.append(row)
        rows.sort(key=lambda r: (-(r["tonnes_a_day"] or 0), r["key"]))
        breakdown[by] = rows

    return {
        "empty": False,
        "months_with_volume": n,
        "working_days": wd,
        "lines_counted": lines_counted,
        "headline": {
            # the bar's fractional-sum figure, and the rule named beside it (D28)
            "two_way_a_day": _r(two_way_a_day),
            "movements_in_month": _r(_avg(m_veh)),
            "working_days": wd,
            "routes_in_use": len(routes_in),
            "tonnes": _r(_avg(m_t)),
            "rule": ("Two-way movements = loads (deliveries) per working day; each is a lorry out laden "
                     "and back empty. The month's loads are summed as typed (fractional), not rounded per line."),
        },
        "vehicles": {
            "fleet": fleet_peak,
            "excludes_unbaked_lines": unbaked_lines,
            "label": "Vehicles needed" + (f" ({unb_label})" if unb_label else ""),
            "not_baked": bool(unbaked_lines and not fleet_peak),
            "rule": ("Vehicles = movements ÷ what one vehicle can do per day on that route (baked cycle, in a driver's "
                     "day under the UK drivers' hours: the shift less the required break, at most 9 h driving; a planning "
                     "figure, weekly limits and drivers' own hours not checked), rounded up per line"
                     + (", busiest month" if n > 1 else "") + "."),
        },
        "material": {
            "shown": unit != "vehicles",                         # rule 8
            "unit": unit,
            "per_day": _r(_avg(m_qty) / wd),
            "note": ("In a vehicles unit loads a day is the two-way movements figure, so the card is shown "
                     "for tonnes / m³ only."),
        },
        "carbon": _carbon_block(_avg(m_co2), _avg(m_co2) / wd, co2_unbaked, payloads, routes, wd,
                                co2_lines=co2_lines),
        "busiest_routes": busiest,
        "by_route": by_route,
        "breakdown": breakdown,
        "routes_in_use": sorted(routes_in),
        "routes_not_drawn": not_drawn_block,
        "payload_fallback": {"lines": fell_back, "vehicle": fb_name,
                             "note": (f"{fell_back} line(s) use the {fb_name} payload because their vehicle "
                                      "is not in factors.json." if fell_back else None)},
    }


def _cap_of(rp):
    """The typed planning cap on a route's properties, if the caller stamped one."""
    v = rp.get("max_vehicles_per_day")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _carbon_block(co2_month, co2_day, co2_unbaked, payloads, routes, wd, co2_lines=None):
    """
    The costlines figure (co2_t per line is costlines' own) with the Carbon page's stamp.

    12 Oct 2026 (the tests-and-regressions review): when NO counted line carries carbon —
    every drawn route unbaked for its vehicle, or the costlines read failed and the payload
    says so in `co2_error` — the figures are None and `not_baked` is True, as the fleet
    block already does for a fleet with no cycle. A sum of zero baked lines is not 0.0 t of
    carbon. The payload's `co2_error` rides along as `error` so the page can say why.
    """
    last = payloads[-1] if payloads else {}
    to_date, to_date_rows = 0.0, 0
    for c in (last.get("co2_to_date") or []):
        if c.get("route_id") in routes:
            to_date += float(c.get("co2_t") or 0.0)
            to_date_rows += 1
    errors = [p.get("co2_error") for p in payloads if isinstance(p, dict) and p.get("co2_error")]
    not_baked = bool(co2_unbaked and not co2_lines)
    if not_baked or errors:
        co2_month = co2_day = None
    # 12 Oct 2026 (the review and fix pass): the to-date figure follows the same rule — a failed
    # read empties co2_to_date, and a programme with nothing stored to date is not 0.0 t
    to_date_unbaked = int(last.get("co2_to_date_unbaked_lines") or 0)
    if errors or (not to_date_rows and to_date_unbaked):
        to_date = None
    return {
        "co2_t_a_day": _r(co2_day),
        "co2_t_in_month": _r(co2_month),
        "co2_t_to_date": _r(to_date),
        "excludes_unbaked_lines": co2_unbaked,
        "not_baked": not_baked,
        "error": (errors[0] if errors else None),
        "to_date_excludes_unbaked_lines": to_date_unbaked,
        # 12 Oct 2026 (the review and fix pass): plain words for a council reader — "baked" is the
        # team's word for a stored road route; the JSON keys keep it
        "label_day": ("CO₂e a day" + (f" (excl. {co2_unbaked} {_lines(co2_unbaked)} with no stored road route)"
                                      if co2_unbaked else "")),
        "stamp": carbon.SUMMARY_STAMP,
        "rule": "CO₂e = routed km × the vehicle's kg CO₂e/km, approved plan only.",
    }


def month_rollup(month_index, acc=None, unit="vehicles", months=None):
    """
    The roll-up for one month (or, with `months`, a window averaged the bar's way), whole
    scheme, from the same functions the map's endpoints run. `acc` limits the per-team
    rows only; the figures are the scheme's.
    """
    factors = conversions.load_factors()
    wd = working_days(factors)
    idx = [int(m) for m in (months or [month_index])]
    payloads = [month_payload(m, unit) for m in idx]
    routes = drawn_routes()
    _stamp_caps(routes)
    names = {}
    try:
        names = {r["section_id"]: (r.get("name") or r["section_id"]) for r in taxonomy.list_work_sections()}
    except Exception:
        names = {}
    out = rollup_payloads(payloads, routes, wd, acc=acc, unit=unit, section_names=names,
                          discipline_names=discipline_names())
    out["months"] = idx
    return out


def discipline_names():
    """id -> the tenant's label, every discipline (out of scope too: a line may still carry one). {} on a failed read."""
    try:
        return {r["id"]: (r.get("label") or r["id"]) for r in taxonomy.list_disciplines(include_out_of_scope=True)}
    except Exception:
        return {}


def _stamp_caps(routes):
    """Put each drawn route's typed cap on its properties (the map's feature carries none)."""
    if not routes:
        return
    for r in db.query("SELECT id, max_vehicles_per_day FROM routes WHERE tenant_id = ?",
                      (db.current_tenant(),)):
        if r["id"] in routes:
            routes[r["id"]]["max_vehicles_per_day"] = r.get("max_vehicles_per_day")


# --------------------------------------------------------------------------- #
#  Conditions of the month                                                      #
# --------------------------------------------------------------------------- #
def loads_by_route_of(payload):
    """{route_id: the month's approved loads} from a month payload (fractional, the bar's rule)."""
    out = {}
    for l in (payload or {}).get("lines", []) or []:
        out[l["route_id"]] = out.get(l["route_id"], 0.0) + float(l.get("vehicle_loads") or 0.0)
    return out


def route_cap_rows(loads_by_route, wd):
    """
    14 Oct 2026 (bundle G): the Conditions panel's cap rule as ONE function, read by conditions_of_month and
    by the CLP section's chart 1 — every route with a typed cap AND approved volume in the month: two-way
    movements a day (one load = one movement; the month's loads ÷ working days) against the cap. A flag,
    never a block. The Look-ahead's ROUTE_CAP counts the lorries needed on a day instead (the user, 14 Oct:
    "keep both as now").
    """
    caps = db.query("SELECT id, max_vehicles_per_day FROM routes WHERE tenant_id = ? "
                    "AND max_vehicles_per_day IS NOT NULL", (db.current_tenant(),))
    out = []
    for r in caps:
        if r["id"] not in loads_by_route:
            continue
        a_day = loads_by_route[r["id"]] / wd
        cap = int(r["max_vehicles_per_day"])
        over = a_day > cap
        out.append({"route_id": r["id"], "cap": cap, "two_way_a_day": _r(a_day), "over": over,
                     "over_by": (_r(a_day - cap) if over else None), "pct": (round(a_day * 100.0 / cap) if cap > 0 else None)})
    out.sort(key=lambda x: x["route_id"])
    return out


def conditions_of_month(month_index, payload=None, factors=None):
    """
    What the map's Conditions panel shows for a month, from what is STORED:
      restrictions  the stored per-route check (restrictions.store_checks) — the hits whose
                    dates overlap the CALENDAR month (undated hits always count); a route
                    with no stored check reads "never checked", never "clean"
      stockpiles    over capacity at the END of the month (the map's rule: the last week
                    of the month wins), from stockpiles.balances
      seasonal      the factors.json windows that name this calendar month and a vehicle
                    the month's lines use (or no vehicle, so every route)
      route_caps    two-way movements a day (one load = one movement; the month's loads
                    ÷ working days) against the daily cap typed on the route — a planning
                    flag, never a block
    Routes are the month's approved routes, drawn or not: a condition on the plan does not
    wait for a bake.
    """
    mi = int(month_index)
    factors = factors or conversions.load_factors()
    wd = working_days(factors)
    span_from, span_to = weeks.month_span(mi)
    cal = ((mi - 1) % 12) + 1
    payload = payload or month_payload(mi)
    lines = payload.get("lines", []) or []
    routes_in_month = sorted({l["route_id"] for l in lines})
    veh_by_route, loads_by_route = {}, {}
    for l in lines:
        veh_by_route.setdefault(l["route_id"], set()).add(l.get("vehicle_type"))
        loads_by_route[l["route_id"]] = loads_by_route.get(l["route_id"], 0.0) + float(l.get("vehicle_loads") or 0.0)

    # 1. the stored restriction check, month-aware
    prov = restrictions.provider() or {}
    stored = restrictions.stored_checks(routes_in_month) if routes_in_month else {}
    never = [r for r in routes_in_month if not (stored.get(r) or {}).get("checked_at")]
    checked = [stored[r]["checked_at"] for r in routes_in_month if (stored.get(r) or {}).get("checked_at")]
    hits = []
    for rid in routes_in_month:
        st = stored.get(rid) or {}
        if not st.get("checked_at"):
            continue
        for h in st.get("hits") or []:
            if not isinstance(h, dict) or not clashes._overlaps_span(h, span_from, span_to):
                continue
            hits.append({
                "route_id": rid,
                "headline": h.get("headline") or h.get("label") or f"a {prov.get('kind_word') or 'restriction'}",
                "what": h.get("what"), "label": h.get("label"), "kind": h.get("kind"),
                "from": h.get("from"), "to": h.get("to"),
                "severity": h.get("severity"), "verdict": h.get("verdict"),
                "road_nr": h.get("road_nr"), "road_name": h.get("road_name"),
                "checked_at": st.get("checked_at"),
            })
    if not routes_in_month:
        r_status = "no routes"
    elif len(never) == len(routes_in_month):
        r_status = NEVER_CHECKED
    elif never:
        r_status = "partly checked"
    else:
        r_status = "checked"
    restr = {"status": r_status, "hits": hits, "never_checked_routes": never,
             "never_checked_wording": NEVER_CHECKED,
             "checked_at": (min(checked) if checked else None),
             "provider": prov.get("key"), "label": prov.get("flag_label"),
             "span": [span_from.isoformat(), span_to.isoformat()],
             "note": ("Hits are from the stored check on each route, dated hits only where their dates "
                      "overlap this calendar month; undated limits always count. A route never checked is "
                      "listed as such, not as clear.")}
    # 12 Oct 2026 (the review and fix pass): the stored check keeps only closures in force WHEN
    # it ran (restrictions' current_only), so for a month that had ended by then the closures of
    # that month that had also ended are not stored — "checked" would overstate it
    after = sorted({str(c)[:10] for c in checked if str(c)[:10] > span_to.isoformat()})
    restr["checked_after_month"] = bool(after)
    restr["past_month_note"] = (
        f"Checked on {after[0]}, after this month ended; closures that had ended by then are not "
        "stored, so this month's list may be incomplete." if after else None)

    # 2. stockpiles over at the end of the month
    piles = []
    for sp in stockpiles.balances(mi, mi)["stockpiles"]:
        if sp.get("capacity_qty") is None:
            continue
        last = None
        for w in sp.get("weeks") or []:
            if int(w["month_index"]) == mi:
                last = w                                          # the last week of the month wins
        if last and last.get("over"):
            piles.append({"location_id": sp["location_id"], "name": sp["name"],
                          "capacity_qty": sp["capacity_qty"], "unit": sp["capacity_unit"],
                          "balance_end": last["balance_end"],
                          "over_by": _r(float(last["balance_end"]) - float(sp["capacity_qty"])),
                          "wording": stockpile_wording(sp["name"], sp["capacity_qty"], last["balance_end"],
                                                       sp["capacity_unit"], mi)})

    # 3. seasonal windows for this calendar month
    seasonal = []
    for w in (factors.get("seasonal_restrictions") or []):
        if cal not in (w.get("months") or []):
            continue
        rv = w.get("restricted_vehicles") or []
        applies = sorted(rid for rid, vs in veh_by_route.items()
                         if not rv or any(v in rv for v in vs))
        if applies:
            seasonal.append({"name": w.get("name"), "message": w.get("message"),
                             "months": w.get("months"), "restricted_vehicles": rv, "routes": applies})

    # 4. typed caps against the month's two-way movements a day (14 Oct 2026: route_cap_rows, shared with the CLP section)
    rows_cap = route_cap_rows(loads_by_route, wd)
    checked_caps = len(rows_cap)
    exceeded = [{"route_id": r["route_id"], "cap": r["cap"], "two_way_a_day": r["two_way_a_day"],
                 "over_by": r["over_by"], "wording": CAP_WORDING} for r in rows_cap if r["over"]]
    route_caps = {"wording": CAP_WORDING, "exceeded": exceeded, "routes_with_cap": checked_caps,
                  "note": ("Two-way movements a day (one load = one movement; the month's loads ÷ working "
                           "days) against the daily cap typed on the route — a planning flag, never a block.")}

    return {"month": mi, "calendar_month": cal, "span": [span_from.isoformat(), span_to.isoformat()],
            "restrictions": restr, "stockpiles_over": piles, "seasonal": seasonal,
            "route_caps": route_caps,
            "count": len(hits) + len(piles) + len(seasonal) + len(exceeded)}


def public_conditions(c):
    """
    14 Oct 2026 (the user took the recommendation): the bulletin is read by councils and residents, and a stockpile
    over its capacity is a site matter, so the public page leaves the stockpile list out and the count with it.
    conditions_of_month still computes it (the Dashboard and the map's own rules are unchanged).
    """
    out = {k: v for k, v in (c or {}).items() if k != "stockpiles_over"}
    out["count"] = int((c or {}).get("count") or 0) - len((c or {}).get("stockpiles_over") or [])
    return out


# --------------------------------------------------------------------------- #
#  The page                                                                     #
# --------------------------------------------------------------------------- #
def month_page(month_index, acc):
    """What GET /api/bulletin/month returns."""
    mi = int(month_index)
    factors = conversions.load_factors()
    wd = working_days(factors)
    payload = month_payload(mi)
    routes = drawn_routes()
    _stamp_caps(routes)
    try:
        names = {r["section_id"]: (r.get("name") or r["section_id"]) for r in taxonomy.list_work_sections()}
    except Exception:
        names = {}
    # D37 (12 Oct 2026): the whole scheme for every code, team rows included (acc=None: no per-team limit)
    rollup = rollup_payloads([payload], routes, wd, acc=None, section_names=names,
                             discipline_names=discipline_names())
    rollup["months"] = [mi]
    span_from, span_to = weeks.month_span(mi)
    try:
        tenant = config.tenant_settings(conversions)
    except Exception:
        tenant = dict(config.TENANT_DEFAULTS)
    return {
        "month": {"index": mi, "label": month_label(mi), "label_long": month_label_long(mi),
                  "from": span_from.isoformat(), "to": span_to.isoformat()},
        "working_days": wd,
        "rollup": rollup,
        "conditions": public_conditions(conditions_of_month(mi, payload=payload, factors=factors)),
        # 12 Oct 2026: the note says plainly what a team code sees — everything, every team's row
        # included (D37, the user's decision: the public map's own figures, which
        # /api/public/month-kpis gives anyone with the map password).
        "scope": {"team": taxonomy.team_name(acc.get("ipt")) if acc and acc.get("ipt") else None,
                  "note": (SCOPE_NOTE_TEAM if acc and acc.get("ipt") else None)},
        "demo_notice": tenant.get("demo_notice") or None,
        "tenant_name": tenant.get("name"),
        # 12 Oct 2026 (Track C review): the typed, validated address the map's "Report a concern"
        # link uses, so the bulletin's report-a-lorry block prints the same one (None until typed)
        "concern_email": tenant.get("concern_email") or None,
        "plan_only": True,
        "terms": {
            "two_way_movements": rollup["headline"].get("rule") if not rollup.get("empty") else
            "Two-way movements = loads (deliveries) per working day; each is a lorry out laden and back empty.",
            "working_days": f"Working days a month: {wd:g}, from the tenant's planning settings.",
            "cap": f"A typed route cap is a {CAP_WORDING}, never a block; a route without one reads \"{NO_CAP_WORDING}\".",
            "other_schemes": ("Other schemes count differently: HS2 prints HGVs visiting the site (one count per lorry); "
                              "EKFB 2020 printed maximum HGV each way. Wayscope prints two-way movements."),
            "carbon": carbon.SUMMARY_STAMP,
        },
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
