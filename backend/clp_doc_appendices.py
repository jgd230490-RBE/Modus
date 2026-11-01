"""
clp_doc_appendices.py — the CLP document's Part B appendices A–O (task 4a, PR 4 of 4).
Wayscope, 1 Nov 2026. Plan: notes/session-1030-clp-document.md §6 (not in git); mockup
notes/clp-appendices-mockup-1101/ (not in git).

WHAT THEY ARE
-------------
What Wayscope does that the outline CLP template has no heading for, printed after section 7. Each appendix prints ONLY
when the CLP's routes and sites have data for it; an appendix with nothing to say is left out, never printed empty.
Anything already in sections 2 to 7 is pointed to there, not printed twice (the routes, the gates and the work areas are
in section 4, the councils in 2.3.1, the places and collisions in 2.4.2).

  A  Route schedule              why each route, permitted deviations, drive time at 08:00 / 12:00 / 17:00, the quicker option
  B  Gates and site layout       the holding area a site's lorries call through, the site layout phases
  C  Closures, works, diversions the dated diversions in force or offered, with the extra or saved distance
  D  Concrete pours              planned pours on the routes, the transit and cold-joint checks
  E  Abnormal loads              loads to or from the sites: dates, size, status, notice dates
  F  Storage                     capacity and the stock forecast of each storage site, "runs out" and "over capacity" weeks
  G  Carbon                      lorry and all-in tonnes CO2e by month, the target and the agreed decisions that touch the plan
  H  Collision history           the busy-hour counts by route and the alternatives offered
  I  Community                   the places in the strip by kind, the nearest of each
  J  Councils crossed            movements a day and lorry distance per council in the busiest month, cut to this plan
  K  The busiest day             the Simulation's average day: lorries in and out, time on site, the longest queue
  L  Gate arrivals               arrivals a day against capacity, month by month
  M  Lorries needed              lorries needed in the busiest month under the UK drivers' hours rule
  N  Sources and method          how the figures are made
  O  Document history           a pointer to the table at the front

RULES
-----
* STORED DATA ONLY. Nothing here fetches, calls a routing or map service, or writes. (The Simulation's day and the
  carbon scenario are worked out from stored lines, as their own screens do.)
* A team's CLP counts the team's lorries only (data["team"]): pours and abnormal loads are cut to the team, the gate
  figures to the team's share (the capacity stays every team's, as section 6 says), and the Simulation's day — every
  team's lorries together — is left out.
* Every string goes through clp_doc.banned_words in test_clp_doc_appendices; no supplier or back-end word is printed.
* gather() returns {letter: block}; a letter missing = nothing to print. `_skipped` lists an appendix whose read failed
  (a database without that table), so one optional table can never stop a CLP being made.
"""
import datetime
import math

import db

#: route_choice's zone-row statuses in the document's words (a closure that crosses a route and has no way round is the
#: row a reader most needs, so the problem statuses are printed too)
DIVERSION_WORDS = {"in_use": "Diverted: the figures follow the way round", "needs_route": "Crosses the route: no way round drawn yet",
                   "no_way_round": "Crosses the route: no way round found", "declined": "Crosses the route: main route kept"}
MAX_ROWS = 40          # a long table keeps its first rows and says how many more there are
LETTERS = "ABCDEFGHIJKLMNO"
TITLES = {
    "A": "Route schedule", "B": "Gates and site layout", "C": "Closures, works and diversions", "D": "Concrete pours",
    "E": "Abnormal loads", "F": "Storage", "G": "Carbon", "H": "Collision history", "I": "Community considerations",
    "J": "Councils crossed", "K": "The busiest day in the Simulation", "L": "Gate arrivals month by month",
    "M": "Lorries needed", "N": "Sources and how the figures are made", "O": "Document history",
}


def _n(x):
    from clp_doc import n
    return n(x)


def _r1(x):
    return None if x is None else round(float(x), 1)


def _acc(team):
    return {"role": "ipt", "ipt": team} if team else {"role": "planner"}


def _route_ids(d):
    return [r["route_id"] for r in d["routes"]]


def _sites(d):
    return {s["id"]: s for s in d["sites"]}


def _month(mi):
    from clp_doc import month_label
    return month_label(mi)


def _date_words(iso):
    from clp_doc import _date_words as dw
    return dw(iso)


def _more(rows, k=MAX_ROWS):
    return rows[:k], max(0, len(rows) - k)


# --------------------------------------------------------------------------- #
#  A  Route schedule                                                           #
# --------------------------------------------------------------------------- #
def _a_routes(d, ctx):
    import hour_times
    rows = db.query("SELECT id, route_reason, permitted_deviations FROM routes WHERE tenant_id = ?", (db.current_tenant(),))
    typed = {r["id"]: r for r in rows}
    out, profile = [], hour_times.PROFILE
    worked = False
    for r in d["routes"]:
        rid = r["route_id"]
        t = typed.get(rid) or {}
        reason = (t.get("route_reason") or "").strip()
        dev = (t.get("permitted_deviations") or "").strip()
        hrs, quicker = {}, []
        if hour_times.times_for(rid):
            ev = hour_times.evidence_block(rid)
            if ev and ev["series"]:
                worked = True
                this = ev["series"][0]
                for h in hour_times.SCREEN_HOURS:
                    k = ev["hours"].index(h)
                    hrs[h] = this["minutes"][k]
                    q = ev["quicker"][k]
                    if q not in (None, 0):
                        quicker.append(f"{ev['series'][q]['label']} at {h} ({ev['series'][q]['minutes'][k]} min)")
        if reason or dev or any(v is not None for v in hrs.values()):
            out.append({"route_id": rid, "reason": reason, "deviations": dev, "hours": hrs, "quicker": quicker})
    if not out:
        return None
    import conversions
    return {"rows": out, "profile_label": conversions.vehicle_label(ctx["factors"], profile) or profile,
            "hours": list(hour_times.SCREEN_HOURS), "has_times": worked}


# --------------------------------------------------------------------------- #
#  B  Gates and site layout                                                    #
# --------------------------------------------------------------------------- #
def _b_site(d, ctx):
    import holding
    import site_layout_paper
    import site_layouts
    sites = _sites(d)
    held = []
    try:
        summary = holding.summary(ctx["factors"])
    except Exception:                                  # noqa: BLE001
        summary = {"holding_areas": []}
    for h in summary.get("holding_areas") or []:
        serves = [s["name"] for s in h["served"] if s["id"] in sites]
        if serves:
            held.append({"name": h["name"], "spaces": h["spaces"], "call": h["call"], "serves": serves,
                         "straight_to_gate": h["exempt_labels"], "check_minutes": h["gate"].get("check_minutes")})
    layouts = []
    for s in d["sites"]:
        lay = site_layouts.get(s["id"], with_things=False)
        if not lay or not lay["phases"]:
            continue
        in_force = None
        pm = s.get("peak_month")
        if pm:
            try:
                ph = site_layout_paper.phase_in_force(s["id"], site_layout_paper.month_of_index(pm))
                in_force = ph["id"] if ph else None
            except Exception:                          # noqa: BLE001
                in_force = None
        phases = []
        for ph in lay["phases"]:
            n_things = int(ph.get("things") or 0)
            if not n_things:
                continue
            phases.append({"name": ph["name"], "months": site_layout_paper.month_words(ph), "things": n_things,
                           "in_force": ph["id"] == in_force})
        if phases:
            layouts.append({"site": s["name"], "peak_month": pm, "phases": phases})
    if not held and not layouts:
        return None
    return {"holding": held, "layouts": layouts}


# --------------------------------------------------------------------------- #
#  C  Closures, works and diversions                                           #
# --------------------------------------------------------------------------- #
def _c_diversions(d, ctx):
    import route_choice
    route_ids = set(_route_ids(d))
    out = []
    for g in route_choice.periods():
        if g["route_id"] not in route_ids or g.get("reason_kind") != "zone" or g.get("status") not in DIVERSION_WORDS:
            continue
        km = [x["km_delta"] for x in g["legs"] if x.get("leg") == "loaded" and x.get("km_delta") is not None]
        out.append({"route_id": g["route_id"], "zones": g.get("zone_names") or [], "from": g.get("starts_on"),
                    "to": g.get("ends_on"), "status": g["status"], "km_delta": (min(km, key=abs) if km else None),
                    "kept": bool(g.get("kept"))})
    if not out:
        return None
    out.sort(key=lambda g: (g["from"] or "", g["route_id"]))
    return {"rows": out, "unit": d["unit"]}


# --------------------------------------------------------------------------- #
#  D  Concrete pours                                                           #
# --------------------------------------------------------------------------- #
def _d_pours(d, ctx):
    import pours
    route_ids = set(_route_ids(d))
    rows = [p for p in pours.list_pours(include_cancelled=False) if p["route_id"] in route_ids]
    if d.get("team"):
        rows = [p for p in rows if (p.get("ipt") or "") == d["team"]]
    if not rows:
        return None
    rows = pours.decorate(rows, ctx["factors"])
    out = []
    for p in rows:
        f = p.get("figures") or {}
        out.append({"id": p["id"], "date": p["pour_date"], "start": p["start"], "m3": p["m3"], "route_id": p["route_id"],
                    "plant": p.get("origin_name") or "", "site": p.get("dest_name") or "", "gate": p.get("gate_name") or "",
                    "vehicle": p.get("vehicle_name") or "", "status": p["status"],
                    "loads": f.get("loads"), "needed": f.get("needed"), "booked": f.get("booked"),
                    "transit": f.get("transit"), "ends": f.get("ends"), "limits": f.get("limits") or {},
                    "flags": [pours.WORDS.get(x["code"], x["code"]) for x in p.get("flags") or []],
                    "problem": p.get("problem")})
    return {"rows": out}


# --------------------------------------------------------------------------- #
#  E  Abnormal loads                                                           #
# --------------------------------------------------------------------------- #
def _e_abnormal(d, ctx):
    import abnormal
    ids = {s["id"] for s in d["sites"]}
    rows = [r for r in abnormal.rows(_acc(d.get("team"))) if r.get("origin_id") in ids or r.get("dest_id") in ids]
    if not rows:
        return None
    out = []
    for r in rows:
        x = abnormal.decorate(r)
        adv = x.get("advice") or {}
        notices = adv.get("notices") or {}
        out.append({"id": x["id"], "name": x.get("name") or "", "from": x.get("origin_name") or "", "to": x.get("dest_name") or "",
                    "from_date": x.get("date_from"), "to_date": x.get("date_to"), "movements": x.get("movements"),
                    "length_m": x.get("length_m"), "width_m": x.get("width_m"), "height_m": x.get("height_m"),
                    "gross_t": x.get("gross_t"), "vehicle": x.get("vehicle_word") or "", "status": x.get("status_word") or "",
                    "category": adv.get("category_words") or "", "notify_by": adv.get("notify_by"),
                    "police_by": notices.get("police_by"), "applied_on": x.get("applied_on"),
                    "notified_on": x.get("notified_on")})
    return {"rows": out}


# --------------------------------------------------------------------------- #
#  F  Storage                                                                  #
# --------------------------------------------------------------------------- #
def _f_storage(d, ctx):
    import stockpiles
    ids = {s["id"] for s in d["sites"]}
    bal = stockpiles.balances(1, 60)
    out = []
    for sp in bal["stockpiles"]:
        if sp["location_id"] not in ids or not (sp.get("forecast") or sp.get("use_planned") or sp.get("capacity_qty")):
            continue
        by_month = {}
        for w in sp["weeks"]:
            m = by_month.setdefault(w["month_index"], {"in": 0.0, "out": 0.0, "end": None, "over": False, "empty": False})
            m["in"] += float(w.get("inbound") or 0)
            m["out"] += float(w.get("consumed") or 0)
            m["end"] = w.get("balance_end")
            m["over"] = m["over"] or bool(w.get("over"))
            m["empty"] = m["empty"] or bool(w.get("empty"))
        months = [(mi, v) for mi, v in sorted(by_month.items()) if v["in"] or v["out"] or v["over"] or v["empty"]]
        if not months:
            continue
        empty_wk = [w for w in sp["weeks"] if w.get("empty")]
        over_wk = [w for w in sp["weeks"] if w.get("over")]
        out.append({"site": sp["name"], "capacity": sp.get("capacity_qty"), "unit": sp.get("capacity_unit") or "t",
                    "opening": sp.get("opening_qty"),
                    "runs_out": (empty_wk[0]["from"] if empty_wk else None), "runs_out_weeks": len(empty_wk),
                    "over_from": (over_wk[0]["from"] if over_wk else None), "over_weeks": len(over_wk),
                    "months": [{"month": mi, "in": round(v["in"], 1), "out": round(v["out"], 1),
                                "end": (None if v["end"] is None else round(float(v["end"]), 1)),
                                "over": v["over"], "empty": v["empty"]} for mi, v in months]})
    return {"sites": out} if out else None


# --------------------------------------------------------------------------- #
#  G  Carbon                                                                   #
# --------------------------------------------------------------------------- #
def _lever_touches(lv, route_ids, materials, vehicles):
    sc = lv.get("scope") or {}
    if sc.get("route_id") and sc["route_id"] in route_ids:
        return True
    if lv.get("to_route") and lv["to_route"] in route_ids:
        return True
    if sc.get("category") and sc["category"] in materials:
        return True
    if sc.get("vehicle") and sc["vehicle"] in vehicles:
        return True
    return bool(not sc.get("route_id") and not sc.get("category") and not sc.get("vehicle") and not lv.get("to_route"))


def _g_carbon(d, ctx):
    import carbon
    import carbon_target
    acc = _acc(d.get("team"))
    target = carbon_target.get()
    levers = (target or {}).get("levers") or []
    sc = carbon.scenario(acc, alternatives=([{"name": "Agreed decisions", "levers": levers}] if levers else None),
                         status="Approved", factors=ctx["factors"])
    route_ids = set(_route_ids(d))
    by = {}
    unbaked = 0
    for l in sc["lines"]:
        if str(l["route_id"]).split("@")[0] not in route_ids:
            continue
        m = by.setdefault(int(l["month_index"]), {"trips": 0, "lorry": 0.0, "total": 0.0})
        m["trips"] += int(l.get("trips") or 0)
        if l.get("transport_t") is None:
            unbaked += 1
        m["lorry"] += float(l.get("transport_t") or 0.0)
        m["total"] += float(l.get("total_t") or 0.0)
    if not by:
        return None
    st = None
    if target:
        try:
            st = carbon_target.status(acc, target, factors=ctx["factors"])
        except Exception:                              # noqa: BLE001
            st = None
    materials = {x["material"] for x in d["materials"]}
    vehicles = {l["vehicle"] for l in d["lines"]}
    words = []
    for lv, w in zip(levers, (target or {}).get("lever_words") or []):
        if _lever_touches(lv, route_ids, materials, vehicles):
            words.append(w)
    return {"months": [{"month": mi, "trips": v["trips"], "lorry": round(v["lorry"], 2), "total": round(v["total"], 2)}
                       for mi, v in sorted(by.items())],
            "lorry_total": round(sum(v["lorry"] for v in by.values()), 1),
            "total": round(sum(v["total"] for v in by.values()), 1), "unbaked_lines": unbaked,
            "target": (None if not st else {"scope": st["scope"], "approved_t": st["approved_t"],
                                            "with_decisions_t": st["with_decisions_t"], "target_t": st["target_t"],
                                            "on_target": st["on_target_with_decisions"], "invalid": st.get("invalid")}),
            "decisions": words}


# --------------------------------------------------------------------------- #
#  H  Collision history                                                        #
# --------------------------------------------------------------------------- #
def _h_collisions(d, ctx):
    import collisions
    L = d.get("layers") or {}
    co = L.get("collisions") or {}
    if not co.get("fetched") or not co.get("rows"):
        return None
    out = []
    for rid in _route_ids(d):
        try:
            bh = collisions.busy_hours(rid, acc=_acc(d.get("team")))
        except Exception:                              # noqa: BLE001  EvidenceError: a route this caller may not read
            continue
        if bh.get("shown"):
            out.append({"route_id": rid, "period": bh.get("period") or "",
                        "offers": [collisions.offer_words(o, bh.get("period") or "") for o in bh.get("offers") or []]})
    return {"routes": [r["route_id"] for r in co["rows"]], "busy": out, "period": co.get("period") or ""}


# --------------------------------------------------------------------------- #
#  I  Community                                                                #
# --------------------------------------------------------------------------- #
def _i_community(d, ctx):
    C = (d.get("layers") or {}).get("community") or {}
    if not C.get("stored") or not C.get("counts"):
        return None
    labels = C["labels"]
    rows = []
    for kind, count in sorted(C["counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        nr = (C.get("nearest") or {}).get(kind) or {}
        rows.append({"kind": labels.get(kind, kind), "count": count, "nearest": nr.get("name") or "",
                     "metres": nr.get("metres"), "where": nr.get("where") or ""})
    return {"rows": rows, "route_m": C["route_m"], "site_m": C["site_m"]}


# --------------------------------------------------------------------------- #
#  J  Councils crossed                                                         #
# --------------------------------------------------------------------------- #
def _j_councils(d, ctx):
    import areas
    pm = d["totals"]["peak_month"]
    L = d.get("layers") or {}
    if not pm or not L.get("councils"):
        return None
    wd = d["working_days"]
    clips = areas.clip_table()
    drawn = areas._drawn()
    loads = {}
    for l in d["lines"]:
        if l["month"] == pm:
            loads[l["route_id"]] = loads.get(l["route_id"], 0) + l["trips"]
    unit_div = 1.609344 if d["unit"] == "mi" else 1.0
    store = {c["name"]: c for c in areas.stored_areas()}
    ids = {a["name"]: a["area_id"] for a in areas.stored_areas()}
    out = []
    for c in L["councils"]:
        aid = ids.get(c["name"])
        mv = km = 0.0
        for rid in c["routes"]:
            ld = loads.get(rid, 0)
            if not ld or not aid:
                continue
            prof = (clips.get(rid) or {}).get(drawn.get(rid)) or {}
            lin = (prof.get("loaded") or {}).get(aid, 0.0)
            rin = (prof.get("return") or {}).get(aid, 0.0)
            if lin >= areas.ENTER_KM:
                mv += ld
            km += ld * (lin + rin)
        out.append({"name": c["name"], "tier": c["tier"], "authority": c["highway_authority"], "routes": c["routes"],
                    "movements_per_day": round(mv / wd, 1), "lorry_km": round(km / unit_div, 1)})
    return {"rows": out, "month": pm, "unit": d["unit"], "store": len(store)}


# --------------------------------------------------------------------------- #
#  K  The busiest day                                                          #
# --------------------------------------------------------------------------- #
def _k_simulation(d, ctx):
    if d.get("team"):
        return None            # the day mixes every team's lorries: it belongs to the plan for all teams
    import sim
    out = []
    cache = {}
    for s in d["sites"]:
        pm = s.get("peak_month")
        if not pm:
            continue
        if pm not in cache:
            cache[pm] = sim.day(pm, {"role": "planner"}, factors=ctx["factors"], working_days=d["working_days"],
                                with_lines=False)
        day = cache[pm]
        site = next((x for x in day["sites"] if x["location_id"] == s["id"]), None)
        if not site or not (site.get("lorries_in") or site.get("lorries_out")):
            continue
        stations = [x for x in site.get("stations") or [] if x.get("kind") != "gate"]
        busy = max(stations, key=lambda x: (x.get("most_waiting") or 0, x.get("longest_wait") or 0), default=None)
        gates = [g for g in day["gates"] if g["location_id"] == s["id"]]
        gate_wait = max((g.get("most_waiting") or 0 for g in gates), default=0)
        out.append({"site": s["name"], "month": pm, "in": site["lorries_in"], "out": site["lorries_out"],
                    "avg": _r1(site.get("avg_on_site")), "longest": _r1(site.get("longest_on_site")),
                    "lost": _r1(site.get("minutes_lost")),
                    "queue_area": (busy["name"] if busy and (busy.get("most_waiting") or 0) > 0 else None),
                    "queue_most": (busy.get("most_waiting") if busy else 0), "queue_at": (busy.get("most_at") if busy else None),
                    "queue_wait": _r1(busy.get("longest_wait")) if busy else None, "gate_most_waiting": gate_wait})
    if not out:
        return None
    day = cache[next(iter(cache))]
    return {"rows": out, "bands": day.get("bands", {}).get("words"), "loads": day.get("loads")}


# --------------------------------------------------------------------------- #
#  L  Gate arrivals month by month                                             #
# --------------------------------------------------------------------------- #
def _l_gate_months(d, ctx):
    import gate_arrivals
    ids = {s["id"] for s in d["sites"]}
    acc = _acc(d.get("team"))
    months = sorted({l["month"] for l in d["lines"]})
    gates = {}
    for mi in months:
        a = gate_arrivals.arrivals(mi, acc, factors=ctx["factors"], working_days=d["working_days"])
        for g in a["gates"]:
            if g["location_id"] not in ids or not g["arrivals_per_day"]:
                continue
            per = g["arrivals_per_day"]
            if d.get("team"):
                per = (g.get("per_team") or [{}])[0].get("arrivals_per_day") or 0.0
                if not per:
                    continue
            e = gates.setdefault(g["gate_id"], {"gate": g["gate_name"], "site": g["location_name"], "rows": []})
            e["rows"].append({"month": mi, "arrivals": _r1(per), "capacity": g.get("capacity_per_day"),
                              "pct": g.get("capacity_pct"), "word": g.get("status_word")})
    out = [v for v in gates.values() if v["rows"]]
    return {"gates": out, "all_teams_pct": bool(d.get("team"))} if out else None


# --------------------------------------------------------------------------- #
#  M  Lorries needed                                                           #
# --------------------------------------------------------------------------- #
def _m_lorries(d, ctx):
    import carbon
    import derived
    import drivers_hours
    pm = d["totals"]["peak_month"]
    if not pm:
        return None
    wd = d["working_days"]
    cache = {}
    groups = {}
    for l in d["lines"]:
        if l["month"] == pm:
            k = (l["route_id"], l["vehicle"])
            groups[k] = groups.get(k, 0) + l["trips"]
    rows, unrouted = [], 0
    import conversions
    for (rid, veh), trips in sorted(groups.items()):
        row = derived.cycle_for(rid, veh, cache, month_index=pm)
        tpd = None if not row else row.get("trips_per_day")
        if tpd is None:
            unrouted += 1
            rows.append({"route_id": rid, "lorry": conversions.vehicle_label(ctx["factors"], veh) or veh, "trips": trips,
                         "per_lorry": None, "lorries": None})
            continue
        rows.append({"route_id": rid, "lorry": conversions.vehicle_label(ctx["factors"], veh) or veh, "trips": trips,
                     "per_lorry": int(tpd), "lorries": carbon.lorries_for(trips, tpd, wd)})
    if not rows:
        return None
    return {"month": pm, "rows": rows, "total": sum(r["lorries"] or 0 for r in rows), "unrouted": unrouted,
            "shift_note": drivers_hours.shift_note(ctx["factors"])}


# --------------------------------------------------------------------------- #
#  N  Sources                                                                  #
# --------------------------------------------------------------------------- #
def _n_sources(d, ctx):
    import collisions
    import community
    import limits
    L = d.get("layers") or {}
    stored = []
    cs = community.status() if hasattr(community, "status") else {}
    if cs and cs.get("fetched_at"):
        stored.append(("The places in section 2 and Appendix I", f"last fetched {str(cs['fetched_at'])[:10]}"))
    co = L.get("collisions") or {}
    if co.get("fetched"):
        stored.append(("Injury collisions (Appendix H)", co.get("period") or "stored"))
    cl = L.get("closures") or {}
    if cl.get("checked"):
        stored.append(("National Highways closures", f"last checked {str(cl['checked_at'])[:10]}"))
    if (L.get("limits") or {}).get("checked"):
        stored.append(("Lorry limits on the routes", "last checked in Wayscope"))
    return {"stored": stored}


# --------------------------------------------------------------------------- #
#  gather                                                                      #
# --------------------------------------------------------------------------- #
def gather(d, factors=None):
    """{letter: block} for the CLP data `d` (clp_doc.gather's). A letter is present only when the CLP has data for it;
    `_skipped` names an appendix whose read failed."""
    import conversions
    ctx = {"factors": factors or conversions.load_factors()}
    out, skipped = {}, []
    for key, fn in (("A", _a_routes), ("B", _b_site), ("C", _c_diversions), ("D", _d_pours), ("E", _e_abnormal),
                    ("F", _f_storage), ("G", _g_carbon), ("H", _h_collisions), ("I", _i_community), ("J", _j_councils),
                    ("K", _k_simulation), ("L", _l_gate_months), ("M", _m_lorries)):
        try:
            v = fn(d, ctx)
        except Exception as e:                         # noqa: BLE001  one optional read never stops a CLP
            skipped.append(f"{key}: {type(e).__name__}")
            v = None
        if v:
            out[key] = v
    out["N"] = _n_sources(d, ctx)
    out["_skipped"] = skipped
    return out
