"""
The Route analysis (9 Nov 2026, v2.1 task 2.1-6; John's yes to notes\\route-analysis-mockup-1108, Q1-Q13 as recommended,
and to the six section maps). One download on Data → Routes in place of "Collision evidence (PDF)" and "XLSX": one or
more routes (up to MAX_ROUTES), one lorry, the sections ticked —

    A  Restrictions and lorry limits   the stored lorry-limits check, the planned road closures as HELD, the zones crossed
    B  Community places                schools, hospitals and health named along the route; the other kinds counted
    C  Collisions                      today's Route collision evidence, its pages as they are (export.build_collision_
                                       evidence_pdf drawn into this file)
    D  Cycle routes and left turns     the collision evidence's own rules (collisions.cycle_along / left_turns)
    E  Busy-hour times                 the round trip by the hour it sets off; the busy-hours road and what it saves
    F  Diversions                      a dated zone's way taken, its dates, why, how much further
    the page for the assessor          the CLOCS questions, each pointing at its section

STORED DATA ONLY: nothing is fetched while the file is made (the closures are the feed the app already holds, and the
file says when it was read). Counts only: nothing is scored, ranked or divided, except the collision evidence's own
"Compared with roads like these" range. No collision's date or hour is printed. Built in heavy_reads.solo("route-analysis")
by main.py. gather() here; the pages in route_analysis_render.py.
"""
import datetime
import json
import math

import db

MAX_ROUTES = 12
SECTIONS = [  # (key, letter, title) — the order in the file and in the dialog
    ("limits", "A", "Restrictions and lorry limits"),
    ("community", "B", "Community places"),
    ("collisions", "C", "Collisions"),
    ("cycle", "D", "Cycle routes and left turns"),
    ("hours", "E", "Busy-hour times"),
    ("diversions", "F", "Diversions"),
    ("assessor", None, "The page for the assessor"),
]
SECTION_KEYS = [k for k, _, _ in SECTIONS]
LETTER = {k: l for k, l, _ in SECTIONS}
TITLE = {k: t for k, _, t in SECTIONS}
NAMED_KINDS = ("schools", "hospitals", "health")            # named on the page (Q9); the rest counted, listed in the XLSX
COUNTED_KINDS = ("community", "sports", "stations", "bus_stops", "residential")
CLOSURE_NEAR_M = 100                                        # restrictions.match_m()'s default; the file says the figure
VERDICT_WORDS = {"exceeds": "Below this lorry", "at_limit": "At this lorry's limit",
                 "unknown": "Not known for this lorry", "within": "Above this lorry"}


class AnalysisError(LookupError):
    """A route that is not here (or not this team's): a 404."""


class AskError(ValueError):
    """A request that cannot be made as asked: a 422, the words as they are."""


def parse_sections(raw):
    """The ticked sections in the file's order. None / empty = every section."""
    if raw is None or not str(raw).strip():
        return list(SECTION_KEYS)
    want = [s.strip() for s in str(raw).split(",") if s.strip()]
    bad = [s for s in want if s not in SECTION_KEYS]
    if bad:
        raise AskError("Pick the sections from the list.")
    return [k for k in SECTION_KEYS if k in want]


def parse_routes(raw):
    ids = []
    for s in str(raw or "").split(","):
        s = s.strip()
        if s and s not in ids:
            ids.append(s)
    if not ids:
        raise AskError("Pick at least one route.")
    if len(ids) > MAX_ROUTES:
        raise AskError(f"Pick up to {MAX_ROUTES} routes for one file.")
    return ids


def default_lorry(route_id):
    """Q3: the lorry the route's Approved lines use most (by number of lines), where the route is drawn for it; else the
    app's default lorry where drawn; else the first drawn."""
    import network
    tenant = db.current_tenant()
    baked = {g["vehicle_profile"] for g in db.query(
        "SELECT DISTINCT vehicle_profile FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND alt_index = 0 "
        "AND geometry IS NOT NULL", (tenant, route_id))}
    counts = {}
    for r in db.query("SELECT vehicle_type FROM forecasts WHERE tenant_id = ? AND route_id = ? AND status = 'Approved'",
                      (tenant, route_id)):
        v = r.get("vehicle_type")
        if v in baked:
            counts[v] = counts.get(v, 0) + 1
    if counts:
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0] != network.DEFAULT_PROFILE, kv[0]))[0][0]
    if network.DEFAULT_PROFILE in baked:
        return network.DEFAULT_PROFILE
    return sorted(baked)[0] if baked else None


def _words_date(v):
    if not v:
        return None
    try:
        d = datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return str(v)[:10]
    return f"{d.day} {d:%b %Y}"


def _miles(m):
    import export
    return export._dist(m / 1000.0)


# --------------------------------------------------------------------------- #
#  A — restrictions and lorry limits                                           #
# --------------------------------------------------------------------------- #
def _limits(rid, used, loaded, ret, index):
    import limits
    import collisions
    st = (limits.stored_checks([rid]) or {}).get(rid) or {}
    hits = [h for h in st.get("hits") or [] if isinstance(h, dict)]
    out = {"checked": _words_date(st.get("checked_at")), "status": st.get("status"), "items": [], "others": None,
           "diversion_items": []}
    if not st.get("checked_at"):
        return out
    mine = [h for h in hits if h.get("vehicle_profile") == used]
    groups = {}
    for h in mine:
        alt = int(h.get("alt_index") or 0)
        k = (h.get("source"), h.get("ext_id"), h.get("kind"), alt)
        g = groups.setdefault(k, {"headline": h.get("headline"), "name": h.get("name"), "ref": h.get("ref"),
                                  "exceptions": h.get("exceptions"), "verdict": h.get("verdict"),
                                  "point": bool(h.get("point")), "anchor": h.get("anchor"), "source": h.get("source"),
                                  "legs": set(), "kind": h.get("kind"), "limit": h.get("limit"), "unit": h.get("unit"),
                                  "alt": alt, "diversion": h.get("diversion")})
        g["legs"].add(h.get("leg"))
    order = {"exceeds": 0, "at_limit": 1, "unknown": 2, "within": 3}
    for g in groups.values():
        a = g.get("anchor")
        g["along_m"], g["off_m"] = None, None
        if a and len(loaded) >= 2 and a[0] is not None:
            off, along = collisions._project(index, loaded, (a[0], a[1]))
            g["along_m"], g["off_m"] = along, off
        g["legs"] = sorted(g["legs"], key=lambda x: 0 if x == "loaded" else 1)
        g["legs_words"] = ("out and back" if len(g["legs"]) == 2 else ("out" if g["legs"][0] == "loaded" else "back"))
        g["verdict_words"] = VERDICT_WORDS.get(g["verdict"], g["verdict"] or "")
        g["road"] = g.get("name") or g.get("ref") or "Road not named"
        g["value"] = limits.icon_text(g["kind"], float(g["limit"])).replace("T", "t") if g.get("limit") is not None else None
        g["where"] = (_point_words(g) if g["point"] else None)
    main = [g for g in groups.values() if not g["alt"]]
    main.sort(key=lambda g: (g["along_m"] if g["along_m"] is not None else 1e12, order.get(g["verdict"], 3)))
    for i, g in enumerate(main, 1):
        g["no"] = i
        g["from_a"] = (f"{_miles(g['along_m']):.1f}" if g["along_m"] is not None else None)
    out["items"] = main
    out["diversion_items"] = sorted((g for g in groups.values() if g["alt"]),
                                    key=lambda g: (order.get(g["verdict"], 3), g["road"]))
    # Q7: the other lorries on this route — the same limits, or the differences in a line
    by_prof = {}
    for h in hits:
        if int(h.get("alt_index") or 0):
            continue
        by_prof.setdefault(h.get("vehicle_profile"), set()).add((h.get("source"), h.get("ext_id"), h.get("verdict")))
    mine_set = by_prof.get(used, set())
    others = [p for p in by_prof if p != used]
    same = [p for p in others if by_prof[p] == mine_set]
    diff = [p for p in others if by_prof[p] != mine_set]
    out["others"] = {"same": same, "different": diff, "n": len(others)}
    return out


def _point_words(g):
    """A limit recorded as a point beside the route (5-25 m off the line): it may be on a side road at a junction the
    route passes, where an "except for access" sign does not bind this lorry — said, never decided."""
    off = g.get("off_m")
    if off is None:
        return "beside the route: check the route passes it"
    return f"{int(round(off))} m from the route: it may be on a side road at a junction"


def _held_closures(rid, used):
    """The planned road closures the app ALREADY holds (never fetched for this file), checked against the route's stored
    line: {"held": bool, "when": words, "hits": [...], "near_m", "credit"}. Not held = said so."""
    import restrictions
    try:
        if not restrictions.enabled():
            return {"held": False, "why": "No road closures are set up for this organisation.", "hits": []}
        prov = restrictions.current() or {}
        keys = ["nh_closures"] if prov.get("key") == "nh_closures" else list(getattr(restrictions, "LAYERS", {}) or [])
        feats, when = [], None
        for k in keys:
            hit = restrictions._cache.get(f"lyr:{k}")
            if not hit and k == "nh_closures" and getattr(restrictions, "_NH_GOOD", None):
                hit = restrictions._NH_GOOD
            if not hit:
                continue
            fc = hit[1] or {}
            feats += list(fc.get("features") or [])
            t = fc.get("stale_since") or fc.get("fetched_at") or hit[0]
            when = max(when or 0, t or 0)
        if when is None:
            return {"held": False, "why": "No planned road closures are held at the moment.",
                    "hits": []}
        today = datetime.date.today().isoformat()
        feats = [f for f in feats if not str(((f.get("properties") or {}).get("_to")) or "9999")[:10] < today]
        res = restrictions.check_route(rid, profile=used, _fc={"features": feats, "layers": keys})
        seen, hits = set(), []
        for h in res.get("hits") or []:
            k = (h.get("event_number") or h.get("what"), h.get("from"), h.get("to"))
            if k in seen:
                continue
            seen.add(k)
            hits.append({"what": h.get("headline") or h.get("what") or h.get("label"),
                         "road": " ".join(x for x in (h.get("road_nr"), h.get("road_name")) if x) or None,
                         "from": _words_date(h.get("from")), "to": _words_date(h.get("to")),
                         "leg": h.get("leg"), "distance_m": h.get("distance_m")})
        d = datetime.datetime.fromtimestamp(when, datetime.timezone.utc).date()
        return {"held": True, "when": f"{d.day} {d:%b %Y}", "hits": hits, "near_m": res.get("match_m"),
                "credit": prov.get("attribution")}
    except Exception as e:                       # the file never fails for the closures: it says so instead
        print("route analysis: closures not read:", str(e)[:160])
        return {"held": False, "why": "The road closures could not be read for this file.", "hits": []}


def _zones_crossed(loaded, ret):
    """The scheme's own zones (not haul roads, not a site's inside roads, not a dated zone — those are section F) that the
    route's stored line touches."""
    import zones
    out = []
    lines = [l for l in (loaded, ret) if len(l) >= 2]
    for z in zones.list_zones(include_inactive=False):
        if (z.get("kind") == "haul_road" or z.get("location_id") or not z.get("geometry")
                or z.get("starts_on") or z.get("ends_on")):
            continue
        try:
            if any(zones.line_hits_geometry(l, z["geometry"]) for l in lines):
                out.append({"id": z["id"], "name": z.get("name") or z["id"], "kind": z.get("kind"),
                            "affects_routing": z.get("affects_routing"), "geometry": z["geometry"]})
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- #
#  B — community places                                                        #
# --------------------------------------------------------------------------- #
def _community(rid, loaded, index, feats):
    """Every stored community consideration within route_compare.NEAR_M[kind] of the route (its route key: both legs,
    every lorry type — the Routes page's rule), named for schools / hospitals / health, counted for the rest."""
    import collisions
    import community
    import route_compare
    st = community.status() or {}
    out = {"fetched": _words_date(st.get("fetched_at")), "counts": {}, "named": [], "others": [],
           "near_m": dict(route_compare.NEAR_M),
           "labels": {k: community.KIND_BY_KEY[k]["label"] for k in route_compare.KINDS},
           "colours": {k: community.KIND_BY_KEY[k]["colour"] for k in route_compare.KINDS},
           "credit": community.credit_line() if st.get("fetched_at") else None}
    if not st.get("fetched_at"):
        return out
    key = collisions.route_key(rid)
    counts = {k: 0 for k in route_compare.KINDS}
    for f in feats:
        kind = (f.get("properties") or {}).get("kind")
        if kind not in counts:
            continue
        best, at = None, None
        for p in route_compare._points(f.get("geometry")):
            near, _s = index.near(p[0], p[1])
            d = near.get(key)
            if d is not None and (best is None or d < best):
                best, at = d, p
        if best is None or best > route_compare.NEAR_M[kind]:
            continue
        counts[kind] += 1
        props = f.get("properties") or {}
        along = collisions._chainage(index, loaded, at) if len(loaded) >= 2 else None
        row = {"kind": kind, "kind_label": community.KIND_BY_KEY[kind]["label"],
               "name": props.get("name") or None, "m": int(round(best)), "at": [at[0], at[1]],
               "along_m": along, "from_a": (f"{_miles(along):.1f}" if along is not None else None)}
        (out["named"] if kind in NAMED_KINDS else out["others"]).append(row)
    srt = lambda r: (r["along_m"] if r["along_m"] is not None else 1e12, r["m"])
    out["named"].sort(key=srt)
    out["others"].sort(key=srt)
    for i, r in enumerate(out["named"], 1):
        r["no"] = i
    out["counts"] = counts
    return out


# --------------------------------------------------------------------------- #
#  D — cycle routes and left turns (from the collision evidence's own pass)    #
# --------------------------------------------------------------------------- #
def _cycle(ev, index):
    import collisions
    head = ev.get("headline") or []
    turns = []
    for i, t in enumerate(ev.get("turns") or [], 1):
        at = collisions.point_at(index, ev["loaded"], t["m"]) if len(ev.get("loaded") or []) >= 2 else None
        turns.append({"no": i, "words": t.get("words"), "m": t["m"], "at": at, "cycle": t.get("cycle"),
                      "cycle_m": t.get("cycle_m"), "angle": t.get("deg") or t.get("angle")})
    meets = []
    for x in (ev.get("cycle") or {}).get("meets") or []:
        at = collisions.point_at(index, ev["loaded"], x["m"]) if len(ev.get("loaded") or []) >= 2 else None
        meets.append({"m": x["m"], "words": x["words"], "name": x.get("name"), "at": at})
    return {"shown": bool(ev.get("cycle_shown")), "columns": head, "turns": turns, "meets": meets,
            "lines": ev.get("cycle_lines") or [], "beside_m": collisions.CYCLE_BESIDE_M,
            "meets_m": collisions.CYCLE_MEETS_M, "turn_min": collisions.TURN_MIN_DEG,
            "turn_cycle_m": collisions.TURN_CYCLE_M, "turn_window_m": collisions.TURN_WINDOW_M,
            "period": ev.get("period"), "credit": ev.get("community_credit")}


# --------------------------------------------------------------------------- #
#  E — busy-hour times                                                         #
# --------------------------------------------------------------------------- #
def _hours(rid, base, ev, used):
    import network
    import hour_times
    import busy_savings
    import collisions
    a = hour_times.attach(network.route_analysis(rid, profiles=[hour_times.PROFILE]))
    rows = []
    for row in sorted((x for x in (a or {}).get("rows") or [] if x["alt_index"] < 10), key=lambda x: x["alt_index"]):
        hrs = row.get("hours") or {}
        rows.append({"alt": row["alt_index"], "label": collisions.column_label(row["alt_index"]),
                     "out_km": row.get("loaded_km"), "back_km": row.get("return_km"),
                     "plan_hr": ((row.get("loaded_hr") or 0) + (row.get("return_hr") or 0) + (row.get("turnaround_hr") or 0))
                     if row.get("loaded_hr") is not None else None,
                     "at": {h: hrs.get(h) for h in hour_times.HOURS}})
    uses = []
    try:
        for u in busy_savings.for_route(rid):
            if u["status"] == "stopped":
                continue
            road = next((d for d in base.get("diversions") or [] if d.get("kind") == "busy"
                         and d.get("when") == f"Weekdays {u['from']}–{u['to']}"), None)
            uses.append({"alt": u["alt"], "from": u["from"], "to": u["to"], "status": u["status"],
                         "since": _words_date(u.get("decided_at")), "savings": u.get("savings"),
                         "loaded": (road or {}).get("loaded") or [], "return": (road or {}).get("return") or []})
    except Exception as e:
        print("route analysis: busy-hours uses not read:", str(e)[:160])
    offers = ((ev or {}).get("time_of_day") or {}).get("offers") or []
    return {"profile": hour_times.PROFILE, "hours": list(hour_times.HOURS), "busy": [("07:00", "10:00"), ("16:00", "19:00")],
            "rows": rows, "worked_out": bool(a and a.get("hour_times")),
            "status": (a or {}).get("hour_times", {}) and a["hour_times"].get("worked_out"),
            "cycle_by_hour": (ev or {}).get("cycle_by_hour"), "uses": uses, "offers": offers,
            "drawn_for": used}


# --------------------------------------------------------------------------- #
#  F — diversions                                                              #
# --------------------------------------------------------------------------- #
def _diversions(rid, base, index):
    import route_choice
    import zones
    import collisions
    zs = {z["id"]: z for z in zones.list_zones()}
    out = []
    main_out = collisions.line_length_m(index, base["loaded"]) if len(base["loaded"]) >= 2 else None
    main_back = collisions.line_length_m(index, base["return"]) if len(base["return"]) >= 2 else None
    for d in base.get("diversions") or []:
        if d.get("kind") == "busy":
            continue                                           # Q12: the busy-hours road is section E
        zids = [z for z in zs if (zs[z].get("name") or z) in (d.get("because") or [])]
        lo = collisions.line_length_m(index, d["loaded"]) if len(d.get("loaded") or []) >= 2 else None
        bk = collisions.line_length_m(index, d["return"]) if len(d.get("return") or []) >= 2 else None
        out.append({"when": d.get("when"), "from": d.get("from"), "to": d.get("to"), "back_on": d.get("back_on"),
                    "because": d.get("because") or [], "notes": [zs[z].get("note") for z in zids if zs[z].get("note")],
                    "zones": [{"id": z, "name": zs[z].get("name") or z, "geometry": zs[z].get("geometry")} for z in zids],
                    "loaded": d.get("loaded") or [], "return": d.get("return") or [],
                    "loaded_words": d.get("loaded_words"), "return_words": d.get("return_words"),
                    "out_more_m": (lo - main_out) if (lo is not None and main_out is not None) else None,
                    "back_more_m": (bk - main_back) if (bk is not None and main_back is not None) else None,
                    "out_diverted": d.get("loaded") != base["loaded"], "back_diverted": d.get("return") != base["return"],
                    "limits_status": d.get("limits_status"), "limits_lines": d.get("limits_lines") or []})
    no_way, seen = [], set()
    try:
        for p in route_choice.periods(rid):
            if p.get("reason_kind") != "zone" or p.get("status") not in ("needs_route", "no_way_round", "declined"):
                continue
            k = (p.get("starts_on"), p.get("ends_on"), tuple(p.get("zone_names") or []), p.get("status"))
            if k in seen:
                continue
            seen.add(k)
            no_way.append({"when": _when(p.get("starts_on"), p.get("ends_on")), "because": p.get("zone_names") or [],
                           "kept": p.get("status") == "declined"})
    except Exception as e:
        print("route analysis: diversion periods not read:", str(e)[:160])
    return {"items": out, "no_way": no_way}


def _when(s, e):
    import route_sheet
    try:
        return route_sheet._when(s or None, e or None)
    except Exception:
        return " – ".join(x for x in (s, e) if x)


# --------------------------------------------------------------------------- #
#  The whole file's data                                                       #
# --------------------------------------------------------------------------- #
def gather(route_ids, lorry=None, sections=None, acc=None, now=None):
    """Everything the file prints, as data. AnalysisError for a route that is not here (or another team's)."""
    import collisions
    import community
    import conversions
    import export
    import bulletin_doc
    import route_sheet
    route_ids = parse_routes(",".join(route_ids) if isinstance(route_ids, (list, tuple)) else route_ids)
    sections = parse_sections(",".join(sections) if isinstance(sections, (list, tuple)) else sections)
    if not [s for s in sections if s != "assessor"]:
        raise AskError("Pick at least one section.")
    factors = conversions.load_factors()
    used = lorry or default_lorry(route_ids[0])
    as_at = now or datetime.date.today()
    index = collisions.index_from_db()
    feats = community.features(list(__import__("route_compare").KINDS)) if "community" in sections else []
    routes = []
    for rid in route_ids:
        try:
            base = route_sheet.sheet(rid, vehicle=used, acc=acc, now=as_at)
        except route_sheet.SheetError as e:
            raise AnalysisError(str(e))
        R = {"id": rid, "origin": base["origin"], "dest": base["dest"], "loaded": base["loaded"], "return": base["return"],
             "loaded_words": base["loaded_words"], "return_words": base["return_words"], "vehicle": base["vehicle"],
             "vehicle_text": base["vehicle_text"], "drawn": base["drawn"], "team": base.get("team"),
             "drawn_for_other": bool(used and base["vehicle"] and base["vehicle"] != used)}
        R["out_m"] = collisions.line_length_m(index, base["loaded"]) if len(base["loaded"]) >= 2 else None
        R["back_m"] = collisions.line_length_m(index, base["return"]) if len(base["return"]) >= 2 else None
        if "limits" in sections:
            R["limits"] = _limits(rid, base["vehicle"], base["loaded"], base["return"], index)
            R["closures"] = _held_closures(rid, base["vehicle"]) if base["drawn"] else {"held": False, "hits": [],
                                                                                         "why": "No road route yet."}
            R["zones"] = _zones_crossed(base["loaded"], base["return"])
        if "community" in sections:
            R["community"] = _community(rid, base["loaded"], index, feats)
        ev = None
        if any(s in sections for s in ("collisions", "cycle", "hours")):
            try:
                ev = collisions.evidence(rid, acc=acc, now=as_at)
            except collisions.EvidenceError as e:
                raise AnalysisError(str(e))
        if "collisions" in sections:
            R["evidence"] = ev
        if "cycle" in sections:
            R["cycle"] = _cycle(ev, index)
        if "hours" in sections:
            R["hours"] = _hours(rid, base, ev, base["vehicle"])
        if "diversions" in sections:
            R["diversions"] = _diversions(rid, base, index)
        R["summary"] = _summary(R, ev)
        routes.append(R)
    notice = export._demo_notice() or None
    return {
        "routes": routes, "sections": sections, "lorry": used,
        "lorry_text": conversions.vehicle_label(factors, used) if used else None,
        "tenant": export._tenant_name() or "Wayscope", "demo_notice": notice,
        "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "made": f"{as_at:%d %b %Y}".lstrip("0"), "unit": export._du(),
    }


def _summary(R, ev):
    """The first page's row for one route (Q5): only what the sections gathered; None where a section was not ticked."""
    s = {"out_back": None, "limits_below": None, "closures": None, "schools_health": None, "collisions": None,
         "cycle": None, "busy": None, "diversions": None}
    if R.get("out_m") is not None:
        s["out_back"] = f"{_miles(R['out_m']):.1f} · {_miles(R['back_m'] or 0):.1f}"
    if "limits" in R:
        L = R["limits"]
        if L.get("checked"):
            below = [g for g in L["items"] if g["verdict"] == "exceeds"]
            o = sum(1 for g in below if "loaded" in g["legs"])
            b = sum(1 for g in below if "return" in g["legs"])
            s["limits_below"] = f"{o} out · {b} back"
        else:
            s["limits_below"] = "not checked"
        c = R.get("closures") or {}
        s["closures"] = str(len(c.get("hits") or [])) if c.get("held") else "not held"
    if "community" in R:
        C = R["community"]
        s["schools_health"] = (f"{C['counts'].get('schools', 0)} · {C['counts'].get('health', 0) + C['counts'].get('hospitals', 0)}"
                               if C.get("fetched") else "not fetched")
    if ev and "evidence" in R:
        h = (ev.get("headline") or [{}])[0]
        s["collisions"] = f"{h.get('on', 0)} ({h.get('ksi', 0)})" if ev.get("fetched") else "not fetched"
    if "cycle" in R and ev:
        h = (ev.get("headline") or [{}])[0]
        s["cycle"] = f"{h.get('beside') or '—'} · {h.get('turns', 0)}"
    if "hours" in R:
        u = [x for x in R["hours"]["uses"] if x["status"] == "in_use"]
        s["busy"] = "; ".join(f"Alt {x['alt']}, {x['from']}–{x['to']}" for x in u) or "—"
    if "diversions" in R:
        s["diversions"] = str(len(R["diversions"]["items"])) if R["diversions"]["items"] else "—"
    return s


def file_name(D, ext="pdf"):
    ids = [R["id"] for R in D["routes"]]
    if len(ids) == 1:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(ids[0]))
        return f"route-analysis-{safe}.{ext}"
    return f"route-analysis-{len(ids)}-routes.{ext}"
