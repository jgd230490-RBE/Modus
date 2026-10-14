"""
clp.py — CLP monitoring: the Construction Logistics Plan charts from the data Wayscope holds.
Wayscope, 14 Oct 2026 (bundle G: W7, read by the W10 pack). Design note: notes/clp-design.md (not in git).

WHY
---
TfL / CLOCS guidance expects a Detailed CLP to be monitored against its estimate and the results shared
with a working group. Wayscope holds the PLAN, not the gate log (D42, the user 13 Oct: no DMS data), so
these charts are the planned side only, each from the module that already owns its figure. ONE read
builds them for a month and the months around it; the Dashboard's "CLP monitoring" section and the CLP
pack export (PDF and XLSX) both call monitoring(), so a screen and a printed pack cannot disagree.

THE CHARTS (numbers as in the outside brief's item 5 table)
-----------------------------------------------------------
  1   route_caps     two-way movements a day per route (one load = one movement; loads ÷ working days)
                     against the route's typed planning cap — bulletin.route_cap_rows, the Conditions
                     panel's rule (the Look-ahead's ROUTE_CAP counts lorries needed on a day: the user
                     kept both, 14 Oct). Routes with volume and no cap are listed, never compared.
  1b  site_caps      lorry visits a day per location against its CLP cap (locations.clp_cap_per_day) —
                     gate_arrivals.location_visits, the Gate arrivals trips rule.
  4   vehicle_types  approved loads per month by vehicle type, with each month's shares
  5   euro_class     the same loads by the Euro class typed for each vehicle type; untyped is its own
                     "Not typed" group, never guessed (the user, 14 Oct: field + chart)
  6   councils       per district for the month: movements a day, laden and empty lorry-miles (or km) —
                     areas.area_load, W13's read (the bulletin's), with its double-count sentence
  10  carbon_rate    ALL-IN kg CO2e per load and per tonne each month, as planned and with the agreed
                     decisions, against the carbon target shared out (target ÷ the plan's loads, ÷ its
                     tonnes) — carbon.scenario + carbon_target.status (the user, 14 Oct: all-in)
  16  trips_avoided  loads per month as planned and with the agreed decisions; the difference, and the
                     lorry-miles it saves — the same scenario

RULES
-----
* Every chart carries `state` "set" or "empty"; an empty one names what is missing in `missing`, in
  words. A missing figure is None, never 0 (a zero is only printed when it is a computed zero).
* Scope: 4, 5, 10, 16 are the lines the caller may see (the Carbon planner's and the Dashboard's rule);
  1, 1b, 6 are the scheme's (the bulletin's and the public map's figures). `scope_line` says so.
* Team NAMES only; no team id in this file (test_modus scans shipped .py files).
* No database write; every SQL literal carries the tenant predicate.
"""
import access
import areas
import bulletin
import carbon
import carbon_target
import config
import conversions
import db
import gate_arrivals
import gate_hours

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MAX_MONTHS = 24          # the over-time charts show at most two years around the chosen month
NOT_TYPED = "Not typed"
ORDER = ("route_caps", "site_caps", "vehicle_types", "euro_class", "councils", "carbon_rate", "trips_avoided")

#: Each chart's number in the outside brief's table, its title and the CLP item it serves.
CHARTS = {
    "route_caps": {"number": "1", "title": "Routes against their planning cap",
                   "serves": "TfL CLP guidance: estimated vehicle movements, kept within what was agreed"},
    "site_caps": {"number": "1", "title": "Sites against their CLP cap",
                  "serves": "TfL CLP guidance: the peak number of vehicles a site can take"},
    "vehicle_types": {"number": "4", "title": "Movements by vehicle type",
                      "serves": "TfL CLP guidance: vehicle movements by type and size"},
    "euro_class": {"number": "5", "title": "Movements by Euro class",
                   "serves": "TfL CLP guidance: vehicle age and emissions standard"},
    "councils": {"number": "6", "title": "Movements and lorry distance by council",
                 "serves": "TfL CLP guidance: routes and the roads the scheme's lorries use"},
    "carbon_rate": {"number": "10", "title": "Carbon per delivery and per tonne against the target",
                    "serves": "The scheme's carbon target"},
    "trips_avoided": {"number": "16", "title": "Lorry trips avoided by the agreed decisions",
                      "serves": "TfL CLP guidance: measures that reduce vehicle trips"},
}

CAP_DIFF = ("The Look-ahead's ROUTE CAP flag compares the same cap with the lorries needed on a day; this chart, "
            "like the bulletin, compares it with movements a day.")
SPREAD = "Planned figures, not observed: Wayscope holds no gate log or arrival times."


def month_label(mi):
    return gate_arrivals.month_label(mi)


def _r1(x):
    return None if x is None else round(float(x) + 0.0, 1)


def _r3(x):
    return None if x is None else round(float(x) + 0.0, 3)


def _unit():
    try:
        return "mi" if (config.tenant_settings(conversions).get("distance_unit") or "km") == "mi" else "km"
    except Exception:
        return "km"


def _dist(km, unit):
    if km is None:
        return None
    return float(km) / config.KM_PER_MILE if unit == "mi" else float(km)


def _chart(key, state, missing=None, **body):
    c = dict(CHARTS[key])
    c.update({"key": key, "state": state, "missing": missing})
    c.update(body)
    return c


def _veh_label(v, factors):
    vs = (factors or {}).get("vehicles") or {}
    lab = ((vs.get(v) or {}).get("labels") or {}).get("en")
    return lab or v or "Unknown vehicle"


def _window(month_index, months_with):
    """The months the over-time charts show: every month with approved lines, at most MAX_MONTHS around the chosen one."""
    if not months_with:
        return []
    lo, hi = min(months_with), max(months_with)
    if hi - lo + 1 <= MAX_MONTHS:
        return list(range(lo, hi + 1))
    start = max(lo, min(int(month_index) - MAX_MONTHS // 2, hi - MAX_MONTHS + 1))
    return list(range(start, start + MAX_MONTHS))


# --------------------------------------------------------------------------- #
#  Chart 1 and 1b — caps                                                       #
# --------------------------------------------------------------------------- #
def _names():
    locs = {l["id"]: l for l in db.query("SELECT id, name, clp_cap_per_day FROM locations WHERE tenant_id = ?",
                                        (db.current_tenant(),))}
    routes = {r["id"]: r for r in db.query("SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?",
                                          (db.current_tenant(),))}
    return locs, routes


def _route_words(rid, routes, locs):
    r = routes.get(rid) or {}
    o = (locs.get(r.get("origin_id")) or {}).get("name") or r.get("origin_id") or rid
    d = (locs.get(r.get("dest_id")) or {}).get("name") or r.get("dest_id") or ""
    return f"{o} → {d}" if d else str(o)


def route_caps(mi, wd, payload, locs, routes):
    loads = bulletin.loads_by_route_of(payload)
    label = month_label(mi)
    if not loads:
        return _chart("route_caps", "empty", f"No approved lines in {label}.")
    capped = {r["route_id"]: r for r in bulletin.route_cap_rows(loads, wd)}
    rows = []
    for rid, ld in loads.items():
        c = capped.get(rid)
        rows.append({"route_id": rid, "route": _route_words(rid, routes, locs),
                     "movements_per_day": (c["two_way_a_day"] if c else _r3(ld / wd)),
                     "cap": (c["cap"] if c else None), "pct": (c["pct"] if c else None),
                     "over": bool(c and c["over"]), "over_by": (c["over_by"] if c else None)})
    rows.sort(key=lambda x: ((x["pct"] is None), -(x["pct"] or 0), -(x["movements_per_day"] or 0), x["route_id"]))
    n_cap = sum(1 for x in rows if x["cap"] is not None)
    if not n_cap:
        return _chart("route_caps", "empty",
                      "No planning cap typed on any route with volume this month (Data → Routes → a route's "
                      "planning block: Max vehicles / day).", rows=rows, routes_without_cap=len(rows))
    n_over = sum(1 for x in rows if x["over"])
    return _chart("route_caps", "set", rows=rows, routes_with_cap=n_cap, routes_without_cap=len(rows) - n_cap,
                  over=n_over,
                  headline=(f"{n_over} route{'' if n_over == 1 else 's'} over {'its' if n_over == 1 else 'their'} cap"
                            if n_over else f"Every capped route within its cap ({n_cap} of {len(rows)} capped)"),
                  subtitle=f"two-way movements a day, {label}",
                  basis=("Two-way movements a day: one load = one movement; the month's approved loads ÷ "
                         f"{wd:g} working days, against the cap typed on the route. A flag, never a block. "
                         + CAP_DIFF),
                  source="Wayscope: the approved plan and each route's typed cap")


def site_caps(mi, wd, factors, locs):
    label = month_label(mi)
    visits = gate_arrivals.location_visits(mi, factors=factors, working_days=wd)
    if not visits:
        return _chart("site_caps", "empty", f"No approved lines in {label}.")
    rows = []
    for lid, v in visits.items():
        loc = locs.get(lid) or {}
        cap = loc.get("clp_cap_per_day")
        cap = float(cap) if cap is not None else None
        over = cap is not None and v["visits_raw"] > cap + 1e-9
        rows.append({"location_id": lid, "site": loc.get("name") or lid,
                     "visits_per_day": v["visits_per_day"], "laden_per_day": v["laden_per_day"],
                     "empty_per_day": v["empty_per_day"], "cap": cap,
                     "pct": (round(v["visits_raw"] * 100.0 / cap) if cap else None), "over": over,
                     "over_by": (_r1(v["visits_raw"] - cap) if over else None)})
    rows.sort(key=lambda x: ((x["pct"] is None), -(x["pct"] or 0), -(x["visits_per_day"] or 0), x["location_id"]))
    n_cap = sum(1 for x in rows if x["cap"] is not None)
    if not n_cap:
        return _chart("site_caps", "empty",
                      "No CLP cap typed on any site with lorries this month (Data → Locations → a location: CLP cap, "
                      "lorry visits a day).", rows=rows)
    n_over = sum(1 for x in rows if x["over"])
    return _chart("site_caps", "set", rows=rows, sites_with_cap=n_cap, over=n_over,
                  headline=(f"{n_over} site{'' if n_over == 1 else 's'} over {'its' if n_over == 1 else 'their'} CLP cap"
                            if n_over else f"Every capped site within its CLP cap ({n_cap} of {len(rows)} capped)"),
                  subtitle=f"lorry visits a day, {label}",
                  basis=("A visit is one lorry in and out: a delivery where the site is the destination, or a lorry "
                         f"coming to load where it is the origin; the month's approved trips ÷ {wd:g} working days, "
                         "every team together, against the CLP cap typed on the location. A flag, never a block."),
                  source="Wayscope: the approved plan and each site's typed CLP cap")


# --------------------------------------------------------------------------- #
#  Charts 4 and 5 — by vehicle type and by Euro class                         #
# --------------------------------------------------------------------------- #
def _grouped(key, lines, months, group_of, label_of, title_missing, label):
    if not lines:
        return _chart(key, "empty", f"No approved lines in the months around {label}.")
    idx = {m: i for i, m in enumerate(months)}
    groups = {}
    tot = [0] * len(months)
    for l in lines:
        i = idx.get(int(l["month_index"]))
        if i is None:
            continue
        g = group_of(l)
        arr = groups.setdefault(g, [0] * len(months))
        arr[i] += int(l.get("trips") or 0)
        tot[i] += int(l.get("trips") or 0)
    order = sorted(groups, key=lambda g: (g == NOT_TYPED, -sum(groups[g]), str(g)))
    series = [{"group": g, "label": label_of(g), "loads": groups[g],
               "pct": [(round(groups[g][i] * 100.0 / tot[i], 1) if tot[i] else None) for i in range(len(months))],
               "total": sum(groups[g])} for g in order]
    return series, tot


def vehicle_types(lines, months, factors, label):
    r = _grouped("vehicle_types", lines, months, lambda l: l.get("vehicle") or "Unknown vehicle",
                 lambda g: _veh_label(g, factors), None, label)
    if isinstance(r, dict):
        return r
    series, tot = r
    if not sum(tot):
        return _chart("vehicle_types", "empty", f"No approved loads in the months around {label}.")
    top = series[0]
    share = round(top["total"] * 100.0 / sum(tot)) if sum(tot) else None
    return _chart("vehicle_types", "set", months=_month_rows(months), series=series, totals=tot,
                  headline=f"{top['label']} carries {share} % of the loads",
                  subtitle="share of approved loads each month (one load = one movement)",
                  basis="Approved loads (trips, rounded up per forecast month) by the vehicle each line plans to use.",
                  source="Wayscope: the approved plan; vehicle types from Config → Vehicles")


def euro_class(lines, months, factors, label):
    vs = (factors or {}).get("vehicles") or {}
    used = sorted({l.get("vehicle") for l in lines if l.get("vehicle")})
    if not lines:
        return _chart("euro_class", "empty", f"No approved lines in the months around {label}.")
    if not any((vs.get(v) or {}).get("euro_class") for v in used):
        return _chart("euro_class", "empty",
                      "No Euro class typed for the vehicles the plan uses (Config → Vehicles → Euro class).",
                      vehicles_untyped=[_veh_label(v, factors) for v in used])
    r = _grouped("euro_class", lines, months, lambda l: (vs.get(l.get("vehicle")) or {}).get("euro_class") or NOT_TYPED,
                 lambda g: g, None, label)
    if isinstance(r, dict):
        return r
    series, tot = r
    untyped = [_veh_label(v, factors) for v in used if not (vs.get(v) or {}).get("euro_class")]
    typed = [s for s in series if s["group"] != NOT_TYPED]
    top = typed[0] if typed else None
    share = round(top["total"] * 100.0 / sum(tot)) if (top and sum(tot)) else None
    return _chart("euro_class", "set", months=_month_rows(months), series=series, totals=tot,
                  vehicles_untyped=untyped,
                  headline=(f"{top['group']}: {share} % of the loads" if top else "No Euro class typed"),
                  subtitle="share of approved loads each month, by the Euro class typed for each vehicle type",
                  basis=("The Euro class the plan assumes for each vehicle type (Config → Vehicles), not a check of "
                         "any haulier's fleet. A vehicle type with none typed is counted as Not typed, never guessed."),
                  source="Wayscope: the approved plan; Euro classes typed on Config → Vehicles")


def _month_rows(months):
    return [{"month_index": m, "label": month_label(m)} for m in months]


# --------------------------------------------------------------------------- #
#  Chart 6 — councils                                                         #
# --------------------------------------------------------------------------- #
def councils(mi, wd, unit):
    label = month_label(mi)
    try:
        al = areas.area_load(mi, working_days=wd, geometry=False)
    except Exception as e:
        return _chart("councils", "empty", f"The council figures could not be read ({str(e)[:80]}).")
    rows_all = al.get("areas") or []
    if not rows_all:
        return _chart("councils", "empty", "No council boundaries are loaded for this scheme (an admin imports them).")
    tier = "district" if any(a["tier"] == "district" for a in rows_all) else "county"
    rows = []
    for a in rows_all:
        if a["tier"] != tier:
            continue
        laden = _dist(a.get("laden_lorry_km"), unit)
        total = _dist(a.get("lorry_km"), unit)
        if not (a.get("movements_per_day") or total):
            continue
        rows.append({"area_id": a["area_id"], "council": a["name"],
                     "movements_per_day": _r1(a.get("movements_per_day")),
                     "laden_distance": _r1(laden), "empty_distance": _r1((total or 0.0) - (laden or 0.0)),
                     "distance": _r1(total), "routes": a.get("routes_count")})
    if not rows:
        return _chart("councils", "empty", f"No approved lorry movements in any council area in {label}.")
    rows.sort(key=lambda x: (-(x["distance"] or 0), x["council"]))
    word = "lorry-miles" if unit == "mi" else "lorry-km"
    top = max(rows, key=lambda x: x["movements_per_day"] or 0)
    return _chart("councils", "set", rows=rows, tier=tier, unit=unit, distance_word=word,
                  scheme_movements_per_day=_r1((al.get("totals") or {}).get("movements_per_day")),
                  headline=f"{top['council']} takes the most: {top['movements_per_day']:g} movements a day",
                  subtitle=f"{word} in {label}, laden and empty, and two-way movements a day",
                  basis=(al.get("basis") or "") + " " + ("Distance: every lorry-mile driven inside the area, laden and "
                                                         "empty." if unit == "mi" else
                                                         "Distance: every lorry-km driven inside the area, laden and empty."),
                  double_count=areas.DOUBLE_COUNT,
                  attribution=al.get("attribution") or [],
                  source="Wayscope: the approved plan on the stored road routes; council boundaries as the map prints them")


# --------------------------------------------------------------------------- #
#  Charts 10 and 16 — carbon and trips, from one scenario                      #
# --------------------------------------------------------------------------- #
def _scenario(acc, factors):
    """(scenario, target row, target status, invalid sentence). The decisions are the stored target's."""
    t = carbon_target.get()
    invalid = None
    if t is not None:
        try:
            sc = carbon.scenario(acc, alternatives=[{"name": "Agreed decisions", "levers": t.get("levers") or []}],
                                 status="Approved", factors=factors)
        except carbon.CarbonError as e:
            invalid = (f"The agreed decisions no longer fit the plan ({e}). A planner needs to set the target again "
                       f"on the Carbon planner.")
            sc = carbon.scenario(acc, status="Approved", factors=factors)
        st = carbon_target.status(acc, t, factors=factors)
    else:
        sc = carbon.scenario(acc, status="Approved", factors=factors)
        st = None
    return sc, t, st, invalid


def _by_month(lines, months):
    idx = {m: i for i, m in enumerate(months)}
    trips, tonnes, total = [0] * len(months), [0.0] * len(months), [0.0] * len(months)
    for l in lines:
        i = idx.get(int(l["month_index"]))
        if i is None:
            continue
        trips[i] += int(l.get("trips") or 0)
        tonnes[i] += float(l.get("tonnes") or 0.0)
        total[i] += float(l.get("total_t") or 0.0)
    return trips, tonnes, total


def carbon_rate(sc, t, st, invalid, months, label):
    lines = sc.get("lines") or []
    if not lines:
        return _chart("carbon_rate", "empty", f"No approved lines in the months around {label}.")
    trips, tonnes, total = _by_month(lines, months)
    alt = (sc.get("alternatives") or [None])[0]
    alt_m = {m["month_index"]: m for m in (alt or {}).get("by_month") or []}
    rows = []
    for i, m in enumerate(months):
        am = alt_m.get(m)
        rows.append({"month_index": m, "label": month_label(m), "loads": trips[i], "tonnes": _r3(tonnes[i]),
                     "kg_per_load": (_r1(total[i] * 1000.0 / trips[i]) if trips[i] else None),
                     "kg_per_tonne": (round(total[i] * 1000.0 / tonnes[i], 2) if tonnes[i] else None),
                     "kg_per_load_decisions": (_r1(am["total_t"] * 1000.0 / am["trips"]) if (am and am.get("trips")) else None),
                     "kg_per_tonne_decisions": (round(am["total_t"] * 1000.0 / tonnes[i], 2) if (am and tonnes[i]) else None)})
    tot = sc["baseline"]["totals"]
    plan_trips, plan_t, plan_total = tot.get("trips") or 0, tot.get("tonnes") or 0.0, tot.get("total_t") or 0.0
    target_t = (st or {}).get("target_t")
    # 14 Oct 2026 (found building it): the target is shared out PER TONNE only. A decision that puts the load on a
    # bigger lorry makes fewer, heavier loads, so the carbon a LOAD can rise while the total falls — a per-load
    # target line would flag a good decision. Per load is drawn as planned and with the decisions, with no target.
    tgt_tonne = round(target_t * 1000.0 / plan_t, 2) if (target_t is not None and plan_t) else None
    plan_load = _r1(plan_total * 1000.0 / plan_trips) if plan_trips else None
    plan_tonne = round(plan_total * 1000.0 / plan_t, 2) if plan_t else None
    if t is None:
        target_note, headline = carbon_target_none(), (f"{plan_tonne:g} kg CO₂e a tonne as planned" if plan_tonne is not None else None)
    else:
        target_note = None
        headline = (f"{plan_tonne:g} kg CO₂e a tonne planned; the target allows {tgt_tonne:g}"
                    if (plan_tonne is not None and tgt_tonne is not None) else None)
    unbaked = int((tot.get("lines") or 0) - (tot.get("baked_lines") or 0))
    return _chart("carbon_rate", "set", months=rows, unit_note="All-in", headline=headline,
                  plan_kg_per_load=plan_load, plan_kg_per_tonne=plan_tonne,
                  target_kg_per_tonne=tgt_tonne, target_t=_r3(target_t), per_load_note=PER_LOAD_NOTE,
                  target_scope=(st or {}).get("scope"), target_note=target_note, invalid=invalid or (st or {}).get("invalid"),
                  lines_unrouted=unbaked,
                  subtitle="kg CO₂e per load and per tonne, all-in (making the material, transport and waste disposal)",
                  basis=("All-in carbon of the approved plan each month ÷ its loads and ÷ its tonnes; with the agreed "
                         "decisions where a target is set. The target line is the carbon target shared out evenly "
                         "over the tonnes: the target ÷ the whole plan's tonnes. " + PER_LOAD_NOTE
                         + (f" {unbaked} forecast month{'' if unbaked == 1 else 's'} with no road route yet "
                            f"carr{'ies' if unbaked == 1 else 'y'} no transport carbon here." if unbaked else "")),
                  source="Wayscope Carbon planner: DESNZ 2026 conversion factors and the factors it names; the target set on the Carbon planner")


PER_LOAD_NOTE = ("Per load has no target line: a decision that moves material to a bigger lorry makes fewer, heavier "
                 "loads, so the carbon a load can rise while the total falls.")


def carbon_target_none():
    return "No carbon target set yet. A planner sets it in the Carbon planner."


def trips_avoided(sc, t, invalid, months, label, unit):
    lines = sc.get("lines") or []
    if not lines:
        return _chart("trips_avoided", "empty", f"No approved lines in the months around {label}.")
    if t is None:
        return _chart("trips_avoided", "empty",
                      "No decisions agreed yet: a planner sets them with the carbon target in the Carbon planner.")
    if invalid:
        return _chart("trips_avoided", "empty", invalid)
    alt = (sc.get("alternatives") or [None])[0] or {}
    trips, _tonnes, _total = _by_month(lines, months)
    alt_m = {m["month_index"]: m for m in alt.get("by_month") or []}
    rows = []
    for i, m in enumerate(months):
        a = alt_m.get(m)
        a_trips = int(a["trips"]) if a else trips[i]
        rows.append({"month_index": m, "label": month_label(m), "loads_planned": trips[i],
                     "loads_with_decisions": a_trips, "avoided": trips[i] - a_trips})
    avoided = -int(alt.get("delta_trips") or 0)
    dist_saved = _dist(-(alt.get("delta_vkm_km") or 0.0), unit)
    word = "lorry-miles" if unit == "mi" else "lorry-km"
    if avoided > 0:
        headline = f"{avoided:,} lorry trips avoided".replace(",", " ")
    elif avoided < 0:
        headline = f"{-avoided:,} more lorry trips with the decisions".replace(",", " ")
    else:
        headline = "The agreed decisions change no lorry trips"
    return _chart("trips_avoided", "set", months=rows, avoided=avoided, distance_saved=_r1(dist_saved),
                  distance_word=word, decisions=list(t.get("lever_words") or []),
                  headline=headline,
                  subtitle="approved loads each month, as planned and with the agreed decisions",
                  basis=("Loads as planned against the same plan with the decisions agreed with the carbon target "
                         "(a bigger lorry, a nearer supplier, another route). A decision that changes only the "
                         "material changes no trips. Planned, not observed."),
                  source="Wayscope Carbon planner: the decisions stored with the carbon target")


# --------------------------------------------------------------------------- #
#  The read                                                                    #
# --------------------------------------------------------------------------- #
def monitoring(month_index, acc=None, factors=None, working_days=None):
    """What GET /api/clp/monitoring?month=N returns, and what the CLP pack prints."""
    acc = acc if acc is not None else access.current()
    factors = factors or conversions.load_factors()
    mi = int(month_index)
    wd = gate_arrivals._positive(working_days, gate_arrivals._working_days(factors))
    unit = _unit()
    label = month_label(mi)
    locs, routes = _names()
    payload = bulletin.month_payload(mi)
    sc, t, st, invalid = _scenario(acc, factors)
    lines = sc.get("lines") or []
    months = _window(mi, sorted({int(l["month_index"]) for l in lines}))
    charts = {
        "route_caps": route_caps(mi, wd, payload, locs, routes),
        "site_caps": site_caps(mi, wd, factors, locs),
        "vehicle_types": vehicle_types(lines, months, factors, label),
        "euro_class": euro_class(lines, months, factors, label),
        "councils": councils(mi, wd, unit),
        "carbon_rate": carbon_rate(sc, t, st, invalid, months, label),
        "trips_avoided": trips_avoided(sc, t, invalid, months, label, unit),
    }
    bands = gate_hours.peak_bands(factors)
    team = bool((acc or {}).get("ipt"))
    return {
        "month": mi, "label": label, "working_days": wd, "distance_unit": unit,
        "months": _month_rows(months),
        "order": list(ORDER),
        "charts": charts,
        "with_data": [k for k in ORDER if charts[k]["state"] == "set"],
        "peak_bands": bands,
        "peak_words": (f"No deliveries {gate_hours.peak_words(bands)} (the CLP's peak bands, taken off each gate's "
                       f"open hours where they are typed)." if bands else None),
        "scope": "team" if team else "scheme",
        "scope_line": (("Your team's lines for the vehicle, carbon and trip charts; the whole scheme for the caps and "
                        "councils, as the public map shows them.") if team else
                       "Every team's approved lines."),
        "limit": SPREAD,
        "demo_notice": (config.tenant_settings(conversions).get("demo_notice") or None),
    }
