"""
Cost lines, 2026-09-11 — ONE read for the Dashboard and the Forecasts page: every visible
forecast line × month with its volume, haul and cost figures, from the same functions the
Look-ahead uses. Nothing is derived in the browser any more.

WHY
---
Until 11 Sep the Dashboard worked its own figures out client-side: trips = tonnes ÷
payload (fractional), km from /api/routes/analysis-batch, CO2 from the emissions factor,
a fleet size from a monthly peak. The Look-ahead computes the same things on the server
(derived.py: trips rounded UP, the route's own cycle) — two sources for one number, the
shape of the 04 Sep fleet-size bug. Adding cost on top of the client arithmetic would
have made a third. So: this module reads the forecast rows the caller may see, runs each
through derived.line_context() / day_figures() exactly as a Look-ahead line, and returns
the result. The Dashboard sums; it no longer derives.

TWO VISIBLE CONSEQUENCES, chosen by the human on 11 Sep
-------------------------------------------------------
1. Trips round up per line-month (ceil(tonnes / payload)), so totals move up slightly
   against the old fractional figure. That is the Look-ahead's figure, and the right one.
2. An UNBAKED route (no geometry for the line's vehicle) has NO distance here — km, t·km,
   CO2, fair € are None and are EXCLUDED from totals, which say so (`baked_lines` of
   `lines`). The old Dashboard fell back to the route's headline distance × 2; the human's
   09 Sep rule ("the route has to be baked — if not, show a notification") applies here
   as everywhere else now.

THE THREE PRICES, EACH IN FOUR UNITS
------------------------------------
Every line-month carries `planned` (the route's typed rates, else the Config target —
`source` says which; None when neither) and `fair` (the model, fairprice.py), each as
{eur, per_t, per_trip, per_km} — because every haulier and every client presents a price
differently, and a comparison needs the same unit on both sides. per_km is on the km the
trips actually run (basis km × trips), never on a loaded-leg-only figure.

CO2 is km × the vehicle's kg CO2e/km from factors.json, as the Dashboard always did —
the same factor, now applied to the server's km.

DELIVERED TO DATE (11 Sep, afternoon — the Dashboard's progress figures)
------------------------------------------------------------------------
Each line-month also carries what has been REPORTED against it: `actual_qty` is the sum
of the typed week actuals (forecast_weeks.actual_qty — typed by a clerk, or the running
sum of day actuals; days.py rule 6), `actual_tonnes` the same through the line's payload,
`actual_eur` the sum of typed week costs, `weeks_reported` how many weeks carry an
actual. A line-month nobody has reported is None / 0 — never "0 delivered", and never a
share of the forecast. Totals: `actual_tonnes`, `actual_eur`, `reported_lines`,
`delivered_pct` (reported tonnes over ALL visible tonnes — the programme's progress, so
an unreported month counts as not yet delivered, which is what it is). ONE statement,
no materialisation (a read that writes would be wrong here — weeks.list_weeks does).
"""
import access
import conversions
import db
import derived
import limits


def _num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


unit_prices = derived.unit_prices        # one definition, in derived.py


def _rows(acc, from_month=None, to_month=None, status=None):
    # the tenant predicate is in the literal on every branch (test_tenant_audit.py reads
    # the text); the optional clauses are appended after it, ? first in the params
    clauses, params = [], []
    if from_month is not None:
        clauses.append("month_index >= ?"); params.append(int(from_month))
    if to_month is not None:
        clauses.append("month_index <= ?"); params.append(int(to_month))
    if status and status != "All":
        clauses.append("status = ?"); params.append(status)
    where = "".join(" AND " + c for c in clauses)
    rows = db.query(f"SELECT * FROM forecasts WHERE tenant_id = ?{where} "
                    f"ORDER BY route_id, discipline, section_id, month_index",
                    tuple([db.current_tenant()] + params))
    return access.filter_lines(rows, acc)


def _actuals():
    """{(route, month, discipline, section): {qty, eur, weeks}} — the reported weeks, one read."""
    out = {}
    for w in db.query("SELECT route_id, month_index, discipline, section_id, actual_qty, actual_cost_eur "
                      "FROM forecast_weeks WHERE tenant_id = ? "
                      "AND (actual_qty IS NOT NULL OR actual_cost_eur IS NOT NULL)",
                      (db.current_tenant(),)):
        k = (w["route_id"], int(w["month_index"]), w.get("discipline") or "", w.get("section_id") or "")
        a = out.setdefault(k, {"qty": None, "eur": None, "weeks": 0})
        if w.get("actual_qty") is not None:
            a["qty"] = (a["qty"] or 0.0) + float(w["actual_qty"]); a["weeks"] += 1
        if w.get("actual_cost_eur") is not None:
            a["eur"] = (a["eur"] or 0.0) + float(w["actual_cost_eur"])
    return out


def _limit(stored_entry, vehicle_type, baked):
    """{count, text, kind, checked_at} when this line's vehicle is over a limit its route runs
    along; None otherwise. Only a routed line is checked (clashes.limit's rule)."""
    if not baked:
        return None
    hits = limits.exceeding(stored_entry, vehicle_type)
    if not hits:
        return None
    return {"count": len(hits), "text": limits.breach_text(hits, vehicle_type), "kind": hits[0].get("kind"),
            "checked_at": (stored_entry or {}).get("checked_at")}


def lines(acc=None, from_month=None, to_month=None, status=None, factors=None):
    """
    {lines: [...], totals: {...}, costing: {...}} for the caller's visible forecast rows.
    One derived.costing_context() (two statements), one route map, one cycle per
    (route, vehicle) pair — the same budget shape as the Look-ahead's read.
    """
    acc = acc if acc is not None else access.current()
    factors = factors or conversions.load_factors()
    rows = _rows(acc, from_month, to_month, status)
    routes = derived._routes_and_names()
    cost = derived.costing_context()
    cache = {}
    actuals = _actuals()
    plan = factors.get("planning", {}) or {}
    work_days = float(plan.get("working_days_per_month") or 22)
    # 13 Oct 2026 (W6): the stored lorry-limits check, ONE read for every route in view — the same
    # rule and words as the Look-ahead's ROAD LIMIT flag (limits.exceeding / breach_text), so the
    # Dashboard's route table and Forecasts can show it in their status column. A route not
    # checked yet has no hits: `limit` is None, which says nothing either way (the flag's rule).
    stored_limits = limits.stored_checks(sorted({r["route_id"] for r in rows}))
    out = []
    tot = {"lines": 0, "baked_lines": 0, "tonnes": 0.0, "trips": 0, "km": 0.0, "tonne_km": 0.0,
           "co2_t": 0.0, "planned_eur": 0.0, "planned_lines": 0, "planned_target_lines": 0,
           "fair_eur": 0.0, "fair_lines": 0, "planned_tonnes": 0.0, "planned_km": 0.0,
           "fair_tonnes": 0.0, "fair_km": 0.0, "fair_trips": 0, "planned_trips": 0,
           "actual_t": None, "actual_eur": None, "reported_lines": 0}
    for r in rows:
        line = {"route_id": r["route_id"], "unit": r.get("unit"), "material_type": r.get("material_type"),
                "vehicle_type": r.get("vehicle_type"), "ipt": r.get("ipt"), "discipline": r.get("discipline"),
                "section_id": r.get("section_id"), "month_index": r.get("month_index"),
                "week": {"planned_qty": r.get("quantity")}}
        ctx = derived.line_context(line, factors, routes=routes, cache=cache, cost=cost)
        f = derived.day_figures(r.get("quantity"), ctx, factors)
        baked = bool(ctx.get("baked"))
        km = f.get("km_day") if baked else None                       # trips × km_trip
        basis_km_total = (float(ctx.get("basis_km") or 0) * f["trips"]) if baked else None
        co2_t = (round(km * conversions._emissions(factors, r.get("vehicle_type")) / 1000.0, 3)
                 if km is not None else None)
        cycles = int(ctx.get("cycles_per_vehicle_day") or 0)
        # the fleet this month needs: trips spread over the working days, at what one
        # vehicle can do in a shift on this route — None when unbaked (no cycle)
        vehicles = (int(-(-f["trips"] // max(1, cycles * work_days))) if (baked and cycles > 0 and f["trips"] > 0)
                    else (0 if baked else None))
        planned = unit_prices(f.get("eur"), f["tonnes"], f["trips"], basis_km_total)
        planned["source"] = ctx.get("rate_source")
        planned["partial"] = bool(f.get("eur_partial"))
        planned["eur_adj"] = f.get("eur_adj")
        fair = unit_prices(f.get("fair_eur"), f["tonnes"], f["trips"], basis_km_total)
        fair["flags"] = list(((ctx.get("fair") or {}).get("flags")) or [])
        fair["fuel_share_pct"] = (ctx.get("fair") or {}).get("fuel_share_pct")
        act = actuals.get((r["route_id"], int(r["month_index"]), r.get("discipline") or "", r.get("section_id") or ""),
                          {"qty": None, "eur": None, "weeks": 0})
        actual_t = (round(derived.tonnes_of(act["qty"], ctx, factors), 3) if act["qty"] is not None else None)
        out.append({
            "route_id": r["route_id"], "discipline": r.get("discipline") or "", "section_id": r.get("section_id") or "",
            "ipt": ctx.get("ipt") or r.get("ipt"), "month_index": int(r["month_index"]), "status": r.get("status"),
            "material_type": r.get("material_type"), "vehicle_type": r.get("vehicle_type"),
            "vehicle_short": ctx.get("vehicle_short"), "vehicle_name": ctx.get("vehicle_name"),
            "vehicle_class": ctx.get("vehicle_class"),
            "unit": r.get("unit"), "quantity": _num(r.get("quantity")),
            "origin_name": ctx.get("origin_name"), "dest_name": ctx.get("dest_name"),
            "tonnes": f["tonnes"], "trips": f["trips"], "vehicles": vehicles,
            "baked": baked, "km_trip": ctx.get("km_trip"), "basis_km": ctx.get("basis_km"),
            # 10 Oct 2026 (carbon planner): the one-way loaded km, the return km (None when the
            # return leg is not baked) and the payload the trips divide by — read by carbon.py so
            # the Carbon page and the Dashboard share one distance and one trip count
            "distance_km": ctx.get("distance_km"), "return_km": ctx.get("return_km"),
            "payload_t": ctx.get("payload_t"), "dest_id": ctx.get("dest_id"), "origin_id": ctx.get("origin_id"),
            "cycle_min": ctx.get("cycle_min"), "cycles_per_vehicle_day": (cycles if baked else None),
            "km": km, "tonne_km": f.get("tonne_km"), "co2_t": co2_t,
            "planned": planned, "fair": fair,
            "actual_qty": act["qty"], "actual_tonnes": actual_t, "actual_eur": act["eur"],
            "weeks_reported": act["weeks"],
            "flags": list(ctx.get("flags") or []),
            "limit": _limit(stored_limits.get(r["route_id"]), r.get("vehicle_type"), baked),
        })
        if actual_t is not None:
            tot["actual_t"] = (tot["actual_t"] or 0.0) + actual_t; tot["reported_lines"] += 1
        if act["eur"] is not None:
            tot["actual_eur"] = (tot["actual_eur"] or 0.0) + act["eur"]
        tot["lines"] += 1
        tot["tonnes"] += f["tonnes"]; tot["trips"] += f["trips"]
        if baked:
            tot["baked_lines"] += 1
            tot["km"] += km or 0.0; tot["tonne_km"] += f.get("tonne_km") or 0.0; tot["co2_t"] += co2_t or 0.0
        if planned["eur"] is not None:
            tot["planned_eur"] += planned["eur"]; tot["planned_lines"] += 1
            tot["planned_tonnes"] += f["tonnes"]; tot["planned_trips"] += f["trips"]
            tot["planned_km"] += basis_km_total or 0.0
            if planned["source"] == "target":
                tot["planned_target_lines"] += 1
        if fair["eur"] is not None:
            tot["fair_eur"] += fair["eur"]; tot["fair_lines"] += 1
            tot["fair_tonnes"] += f["tonnes"]; tot["fair_trips"] += f["trips"]; tot["fair_km"] += basis_km_total or 0.0
    totals = {
        "lines": tot["lines"], "baked_lines": tot["baked_lines"],
        "excludes_unbaked": tot["baked_lines"] < tot["lines"],
        "tonnes": round(tot["tonnes"], 3), "trips": tot["trips"],
        "km": round(tot["km"], 2), "tonne_km": round(tot["tonne_km"], 1), "co2_t": round(tot["co2_t"], 3),
        # kg CO2e per tonne, over the BAKED tonnes only (the unbaked ones have no km)
        "co2_kg_per_t": (round(tot["co2_t"] * 1000.0 / sum(l["tonnes"] for l in out if l["baked"]), 2)
                         if tot["baked_lines"] and sum(l["tonnes"] for l in out if l["baked"]) > 0 else None),
        "planned": (unit_prices(tot["planned_eur"], tot["planned_tonnes"], tot["planned_trips"], tot["planned_km"])
                    if tot["planned_lines"] else unit_prices(None, 0, 0, 0)),
        "planned_lines": tot["planned_lines"], "planned_target_lines": tot["planned_target_lines"],
        "fair": (unit_prices(tot["fair_eur"], tot["fair_tonnes"], tot["fair_trips"], tot["fair_km"])
                 if tot["fair_lines"] else unit_prices(None, 0, 0, 0)),
        "fair_lines": tot["fair_lines"],
        # delivered to date — reported tonnes over ALL visible tonnes; None until something is reported
        "actual_tonnes": (round(tot["actual_t"], 3) if tot["actual_t"] is not None else None),
        "actual_eur": (round(tot["actual_eur"], 2) if tot["actual_eur"] is not None else None),
        "reported_lines": tot["reported_lines"],
        "delivered_pct": (round(tot["actual_t"] * 100.0 / tot["tonnes"], 1)
                          if tot["actual_t"] is not None and tot["tonnes"] > 0 else None),
    }
    return {"lines": out, "totals": totals, "costing": cost,
            "working_days_per_month": work_days}


def preview(route_id, vehicle_type, material_type, unit, cells, factors=None):
    """
    11 Sep pm — the Submit-forecast matrix's cost preview: the typed cells of ONE line
    (route · vehicle · material · unit), priced exactly as they will be once saved — the
    same line_context() / day_figures() / unit_prices() as lines() above, so what the
    submitter sees while typing is what the Look-ahead, Dashboard and Forecasts will show.
    Reads nothing from the forecasts table (the cells are the body); writes nothing.
    Unbaked route ⇒ fair None, planned partial (the per-km term missing) — flagged, never
    estimated. No diesel index ⇒ fair None. A cell with no quantity is skipped.
    11 Oct 2026: + `carbon`, the all-in tCO2e of the typed cells (preview_carbon below).
    """
    factors = factors or conversions.load_factors()
    routes = derived._routes_and_names()
    cost = derived.costing_context()
    cache = {}
    out, tot = [], {"tonnes": 0.0, "trips": 0, "planned_eur": None, "planned_km": 0.0, "planned_trips": 0, "planned_tonnes": 0.0,
                    "fair_eur": None, "fair_km": 0.0, "fair_trips": 0, "fair_tonnes": 0.0, "target": 0, "flags": set()}
    baked, rate_source, vehicle_class = None, None, None
    return_baked, co2_t = None, 0.0
    for c in cells or []:
        q = _num(c.get("quantity") if isinstance(c, dict) else getattr(c, "quantity", None))
        mi = int(c.get("month_index") if isinstance(c, dict) else getattr(c, "month_index"))
        if not q or q <= 0:
            continue
        line = {"route_id": route_id, "unit": unit, "material_type": material_type, "vehicle_type": vehicle_type,
                "month_index": mi, "week": {"planned_qty": q}}
        ctx = derived.line_context(line, factors, routes=routes, cache=cache, cost=cost)
        f = derived.day_figures(q, ctx, factors)
        baked = bool(ctx.get("baked")); rate_source = ctx.get("rate_source"); vehicle_class = ctx.get("vehicle_class")
        return_baked = bool(ctx.get("return_baked"))
        if baked:
            # 11 Oct 2026 (carbon target): transport carbon by the SAME formula as lines() above,
            # km_day × the vehicle's kg CO2e per km ÷ 1000, rounded per cell as each saved line-month is
            co2_t += round(float(f.get("km_day") or 0.0) * conversions._emissions(factors, vehicle_type) / 1000.0, 3)
        bk = (float(ctx.get("basis_km") or 0) * f["trips"]) if baked else None
        planned = unit_prices(f.get("eur"), f["tonnes"], f["trips"], bk)
        planned["source"] = rate_source; planned["partial"] = bool(f.get("eur_partial"))
        fair = unit_prices(f.get("fair_eur"), f["tonnes"], f["trips"], bk)
        fair["flags"] = list(((ctx.get("fair") or {}).get("flags")) or [])
        out.append({"month_index": mi, "quantity": q, "tonnes": f["tonnes"], "trips": f["trips"],
                    "planned": planned, "fair": fair})
        tot["tonnes"] += f["tonnes"]; tot["trips"] += f["trips"]
        if planned["eur"] is not None:
            tot["planned_eur"] = (tot["planned_eur"] or 0.0) + planned["eur"]; tot["planned_tonnes"] += f["tonnes"]
            tot["planned_trips"] += f["trips"]; tot["planned_km"] += bk or 0.0
            if rate_source == "target":
                tot["target"] += 1
        if fair["eur"] is not None:
            tot["fair_eur"] = (tot["fair_eur"] or 0.0) + fair["eur"]; tot["fair_tonnes"] += f["tonnes"]
            tot["fair_trips"] += f["trips"]; tot["fair_km"] += bk or 0.0; tot["flags"].update(fair["flags"])
    totals = {
        "cells": len(out), "tonnes": round(tot["tonnes"], 3), "trips": tot["trips"],
        "planned": (unit_prices(tot["planned_eur"], tot["planned_tonnes"], tot["planned_trips"], tot["planned_km"])
                    if tot["planned_eur"] is not None else unit_prices(None, 0, 0, 0)),
        "planned_source": rate_source, "planned_target_cells": tot["target"],
        "fair": (unit_prices(tot["fair_eur"], tot["fair_tonnes"], tot["fair_trips"], tot["fair_km"])
                 if tot["fair_eur"] is not None else unit_prices(None, 0, 0, 0)),
        "fair_flags": sorted(tot["flags"]),
    }
    reason = (None if totals["fair"]["eur"] is not None else
              ("no cells" if not out else "not baked" if not baked else
               "no diesel index" if (cost or {}).get("index_eur_per_l") is None else "no fair price"))
    carbon_block = preview_carbon(material_type, (routes.get(route_id) or {}).get("dest_id"), tot["tonnes"],
                                  (round(co2_t, 3) if baked else None) if out else 0.0,
                                  bool(out) and not baked, return_baked, bool(out), factors)
    return {"route_id": route_id, "vehicle_type": vehicle_type, "vehicle_class": vehicle_class, "baked": baked,
            "cells": out, "totals": totals, "fair_reason": reason,
            "index_eur_per_l": (cost or {}).get("index_eur_per_l"), "index_bulletin_date": (cost or {}).get("index_bulletin_date"),
            "carbon": carbon_block}


def preview_carbon(material_type, dest_id, tonnes, transport_t, unrouted, return_baked, has_cells, factors):
    """
    11 Oct 2026 (carbon target) — the ALL-IN carbon of the cells being typed, for the Submit
    forecast strip: {material_t, transport_t, disposal_t, total_t, unrouted, basis}.

      transport  the figure preview() works out (lines()' co2_t formula); None, and unrouted, when
                 the route has no distance
      material   tonnes × the Government primary factor of the category's carbon material
                 (carbon.material_factor), unless the destination is a disposal site;
      disposal   then tonnes × the disposal factor for that site's method (carbon.disposal_route_of /
                 disposal_factor), and material is None;
      total      the sum of the parts that exist (None when none does).
    The factors are carbon.py's own, so the line reads here as it will on the Carbon page once
    approved. `basis` says what is counted in one plain sentence. Pure computation: one read of
    the locations, nothing stored.
    """
    import carbon as _carbon                     # carbon imports this module: imported at call time only
    cp = _carbon.params(factors)
    cm = _carbon.carbon_material_of(material_type, factors) if material_type else None
    row = (cp.get("materials") or {}).get(cm) if cm else None
    label = str((row or {}).get("label") or cm or "this material").lower()
    year = (row or {}).get("year") or 2026
    loc = _carbon._locations().get(dest_id) if dest_id else None
    route = _carbon.disposal_route_of(cp, loc)
    material_t = disposal_t = None
    if route:
        kg = _carbon.disposal_factor(cp, cm, route) if cm else None
        how = PREVIEW_DISPOSAL_WORDS.get(route, route)
        if kg is not None:
            disposal_t = round(float(tonnes) * kg / 1000.0, 3)
            what = f"disposal by {how} at the UK Government {year} factor for {label}"
        else:
            what = f"disposal is not counted (no Government factor is published for {label} by {how})"
    else:
        kg = _carbon.material_factor(cp, cm).get("kg_per_t") if cm else None
        if kg is not None:
            material_t = round(float(tonnes) * kg / 1000.0, 3)
            what = f"making the material at the UK Government {year} factor for {label}"
        elif cm:
            what = f"making the material is not counted (no Government factor is published for {label})"
        else:
            what = "making the material is not counted (this material has no Government material class)"
    if unrouted:
        move = "transport is not counted until the route has a distance"
    elif return_baked:
        move = "transport there and back on the routed distance"
    else:
        move = "transport on the loaded leg only (the return is not routed yet)"
    parts = [v for v in (material_t, transport_t, disposal_t) if v is not None]
    if not has_cells:
        basis = "Nothing typed yet."
    else:
        clauses = [move, what] if route else [what, move]
        basis = "; ".join(clauses) + "."
        basis = basis[0].upper() + basis[1:]
    return {"material_t": material_t, "transport_t": transport_t, "disposal_t": disposal_t,
            "total_t": round(sum(parts), 3) if parts else None, "unrouted": bool(unrouted), "basis": basis}


# the disposal methods in the words a sentence needs (carbon.DISPOSAL_WORDS carries brackets)
PREVIEW_DISPOSAL_WORDS = {"landfill": "landfill", "closed_loop": "closed-loop recycling",
                          "open_loop": "open-loop recycling", "combustion": "combustion"}
