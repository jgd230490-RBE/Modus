"""
5 Nov 2026 (task 0d-2, the user's Q17-Q19): what a busy-hours road SAVES or ADDS — cost, time and carbon.

Wayscope cannot see which road a lorry actually took, so nothing here is measured. Two figures, each saying which it is:

  planned   the Approved lines of the route from the month "Use" was pressed: their trips x the share of the trips that
            set off in the use's hours (route_choice.mix, the route's open window) x the difference one trip makes;
  so_far    the same for the loads the teams have RECORDED (forecast_weeks.actual_qty) in weeks from the Use date,
            labelled estimated: it assumes the lorries setting off in the hours took the road.

The difference one trip makes is the stored option against the main line for the line's own lorry type, at the stored
10:00 times (0f's Q4: busy-hour times stay beside the plan, never in it): km, cycle minutes, kg CO2e a trip, and the
fair price (fairprice.trip_cost — the model's fuel, time and running cost at the line's month). A negative figure is
a saving; a positive one is what the safer road ADDS (Q19), never hidden.
"""
import datetime

import conversions
import db
import derived
import fairprice
import network
import route_choice
import weeks


def _d(v):
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _pair_for(use, profile):
    """(loaded_alt, return_alt) the busy hours give this lorry type: Alt N on each leg that has its own Alt N."""
    legs = {l["leg"] for l in use["legs"] if l.get("vehicle_profile") in (None, "", profile)}
    return (use["alt"] if "loaded" in legs else 0, use["alt"] if "return" in legs else 0)


def per_trip(route_id, profile, pair, month_index, cost, factors, pre=None):
    """{"km", "min", "kg", "eur"}: one trip on `pair` less one on the main line (None when a row is missing)."""
    if pair == (0, 0):
        return None
    try:
        res = network.route_analysis(route_id, profiles=[profile], pre=pre, pairs=[(0, 0), pair])
    except Exception:
        return None
    rows = {(r.get("alt_index"), r.get("return_alt_index")): r for r in res.get("rows") or []
            if r.get("profile") == profile}
    a, b = rows.get((0, 0)), rows.get(pair)
    if not a or not b:
        return None
    cal = ((int(month_index) - 1) % 12) + 1
    payload, _fb = derived.payload_for(profile, factors)
    cls = fairprice.vehicle_class(profile, factors)

    def eur(r):
        c = fairprice.trip_cost({"baked": True, "distance_km": r.get("loaded_km"), "return_km": r.get("return_km"),
                                 "cycle_min": float(r.get("cycle_hr") or 0) * 60.0, "payload_t": payload,
                                 "vehicle_class": cls}, cal, cost.get("index_eur_per_l"), cost.get("fair_params") or {})
        return c["eur_trip"] if c else None
    ea, eb = eur(a), eur(b)
    return {"km": round(float(b.get("total_km") or 0) - float(a.get("total_km") or 0), 3),
            "min": round((float(b.get("cycle_hr") or 0) - float(a.get("cycle_hr") or 0)) * 60.0, 2),
            "kg": round(float(b.get("co2_kg_per_trip") or 0) - float(a.get("co2_kg_per_trip") or 0), 2),
            "eur": (round(eb - ea, 2) if ea is not None and eb is not None else None)}


def _share(route_id, profile, month_index, use, week_index=None):
    """The share of this period's trips that set off in the use's hours and take its road (route_choice.mix)."""
    days = (route_choice.week_days(int(month_index), int(week_index)) if week_index is not None
            else route_choice.month_days(int(month_index)))
    m = route_choice.mix(route_id, profile, days)
    return sum(o["share"] for o in ((m.get("busy") or {}).get("options") or [])
               if o["from"] == use["from"] and o["alt"] == use["alt"])


def _empty():
    return {"trips": 0.0, "of": 0, "km": 0.0, "min": 0.0, "kg": 0.0, "eur": 0.0, "eur_missing": False}


def _add(acc, n, d):
    acc["trips"] += n
    acc["km"] += n * d["km"]
    acc["min"] += n * d["min"]
    acc["kg"] += n * d["kg"]
    if d.get("eur") is None:
        acc["eur_missing"] = True
    else:
        acc["eur"] += n * d["eur"]


def _round(acc):
    return {"trips": round(acc["trips"], 1), "of": int(acc["of"]), "km": round(acc["km"], 1),
            "min": round(acc["min"], 1), "kg": round(acc["kg"], 1), "eur": round(acc["eur"], 2),
            "eur_missing": acc["eur_missing"]}


def for_use(use, factors=None, cost=None, routes=None, cache=None):
    """
    {"planned": {...}, "so_far": {...}, "per_trip": {...} (the route's main lorry type), "from_month": n} for one
    in-use busy-hours use (route_choice.busy_uses). Each figure block: trips in the hours (`trips`, of `of` in all),
    km, min, kg, eur — negative a saving.
    """
    factors = factors or conversions.load_factors()
    cost = cost if cost is not None else derived.costing_context()
    routes = routes if routes is not None else derived._routes_and_names()
    cache = cache if cache is not None else {}
    pre = cache.setdefault("__route_analysis_pre__", {})
    rid = use["route_id"]
    since = _d(use.get("decided_at")) or datetime.date.today()
    from_month = weeks.month_index_of(since)
    planned, so_far = _empty(), _empty()
    first = None
    lines = db.query("SELECT route_id, month_index, discipline, section_id, quantity, unit, material_type, vehicle_type, "
                     "ipt FROM forecasts WHERE tenant_id = ? AND route_id = ? AND status = 'Approved' AND month_index >= ?",
                     (db.current_tenant(), rid, int(from_month)))
    recorded = {}
    for w in db.query("SELECT month_index, discipline, section_id, week_index, actual_qty FROM forecast_weeks "
                      "WHERE tenant_id = ? AND route_id = ? AND actual_qty IS NOT NULL", (db.current_tenant(), rid)):
        recorded.setdefault((int(w["month_index"]), w.get("discipline") or "", w.get("section_id") or ""), []).append(w)
    deltas = {}
    for r in lines:
        veh = r.get("vehicle_type")
        pair = _pair_for(use, veh)
        mi = int(r["month_index"])
        if (veh, pair, mi) not in deltas:
            deltas[(veh, pair, mi)] = per_trip(rid, veh, pair, mi, cost, factors, pre)
        d = deltas[(veh, pair, mi)]
        line = {"route_id": rid, "unit": r.get("unit"), "material_type": r.get("material_type"), "vehicle_type": veh,
                "ipt": r.get("ipt"), "discipline": r.get("discipline"), "section_id": r.get("section_id"),
                "month_index": mi, "week": {"planned_qty": r.get("quantity")}}
        ctx = derived.line_context(line, factors, routes=routes, cache=cache, cost=cost)
        trips = derived.day_figures(r.get("quantity"), ctx, factors)["trips"]
        planned["of"] += trips
        if d is None:
            continue
        first = first or d
        share = _share(rid, veh, mi, use)
        _add(planned, trips * share, d)
        # recorded weeks from the Use date (Q18: estimated)
        for w in recorded.get((mi, r.get("discipline") or "", r.get("section_id") or ""), []):
            try:
                _mon, sun = weeks.week_span(mi, int(w["week_index"]))
            except Exception:
                continue
            if sun < since:
                continue                     # a week that ended before Use was pressed
            got = derived.day_figures(w["actual_qty"], ctx, factors)["trips"]
            so_far["of"] += got
            _add(so_far, got * _share(rid, veh, mi, use, int(w["week_index"])), d)
    return {"planned": _round(planned), "so_far": _round(so_far), "per_trip": first, "from_month": from_month,
            "since": since.isoformat()}


def for_route(route_id, **kw):
    """Every busy-hours use of a route, with its figures when in use: [use + {"savings": …}]."""
    out = []
    for u in route_choice.busy_uses(route_id):
        u = dict(u)
        if u["status"] == "in_use":
            try:
                u["savings"] = for_use(u, **kw)
            except Exception as e:
                print("busy savings:", route_id, str(e)[:160])
                u["savings"] = None
        out.append(u)
    return out


def all_uses():
    """The Carbon planner's "Route choices" block: every in-use busy-hours use with its figures, and the totals."""
    factors = conversions.load_factors()
    cost = derived.costing_context()
    routes = derived._routes_and_names()
    cache = {}
    uses, tot = [], {"planned": _empty(), "so_far": _empty()}
    for u in route_choice.busy_uses():
        if u["status"] != "in_use":
            continue
        u = dict(u)
        try:
            u["savings"] = for_use(u, factors=factors, cost=cost, routes=routes, cache=cache)
        except Exception as e:
            print("busy savings:", u["route_id"], str(e)[:160])
            u["savings"] = None
        if u["savings"]:
            for k in ("planned", "so_far"):
                s = u["savings"][k]
                t = tot[k]
                for f in ("trips", "km", "min", "kg", "eur"):
                    t[f] += s[f]
                t["of"] += s["of"]
                t["eur_missing"] = t["eur_missing"] or s["eur_missing"]
        uses.append(u)
    return {"uses": uses, "totals": {k: _round(v) for k, v in tot.items()}}


def better_all_day(route_id, alt, profile=None):
    """Q3: True when Alt N is shorter AND quicker than the main line for the route's main lorry type at the stored
    times and at every hour worked out (hour_times) — then "Make primary may suit better" is worth saying."""
    import hour_times
    profile = profile or network.DEFAULT_PROFILE
    try:
        res = hour_times.attach(network.route_analysis(route_id, profiles=[profile]))
    except Exception:
        return False
    rows = {r.get("alt_index"): r for r in (res or {}).get("rows") or [] if r.get("profile") == profile}
    a, b = rows.get(0), rows.get(int(alt))
    if not a or not b:
        return False
    if not (float(b.get("total_km") or 0) < float(a.get("total_km") or 0)
            and float(b.get("cycle_hr") or 0) < float(a.get("cycle_hr") or 0)):
        return False
    ha, hb = a.get("hours") or {}, b.get("hours") or {}
    return all(hb[h] < ha[h] for h in ha if ha.get(h) is not None and hb.get(h) is not None)
