"""
route_map_export.py — the route map export (backlog item 2, 14 Oct 2026; replaces the per-route sheet, backlog §2).

WHAT IT IS
----------
A PDF of the map as the person has filtered it — the routes chosen in the map's Route filtering, one month, one team or
all — drawn on the SERVER (basemap.py behind, the bulletin's route drawing on top), never a screenshot of the browser map.
Under the map, one row per chosen route: its places (never an id), two-way movements a day, loads and tonnes in the month,
the vehicles, the planning flag (a flag, never a block) and the date its road closures were last checked ("not checked"
when never). Then a fixed block the scheme fills in: what Wayscope does not hold (hours, wheel wash, holding area,
contacts). Staff only (the user, 14 Oct: "STAFF ONLY").

D11: an approved route = the route plus its Approved lines. Every figure comes from the month roll-up the public map's bar
and the bulletin use (bulletin.rollup_payloads over /api/public/month-kpis lines, which are Approved only), filtered to the
chosen routes and team BEFORE the roll-up, so the figures are those routes' own.

    S = sheet(month_index, route_ids=None, team=None, acc=None, carbon_tool=False)    the view model (formatted)
    export.build_route_map_pdf(S)                                                       the PDF

`carbon_tool=True` adds the National Highways Carbon Tool rows (H3: tonnes and one-way LOADED km per origin → destination
for the month, by Carbon Tool sheet), from carbon.scenario's baseline — offered as an option, not decided.
"""
import datetime

#: the scheme's own fields a CLP / CTMP appendix needs and Wayscope does not hold (backlog §2, the CLOCS / CTMP sources)
SCHEME_FIELDS = (
    ("Working hours", "Site delivery hours, and any times lorries must not arrive."),
    ("Wheel wash", "Where it is and when it must be used before a lorry leaves site."),
    ("Holding area", "Where a lorry waits if it arrives early or the gate is full; never on the public road."),
    ("Contacts", "The site's traffic marshal or logistics manager, and an out-of-hours number."),
)

FLAG_WORDS = "A planning flag, never a block: the scheme's own daily figure for a route, not a legal limit."


def _team_text(v):
    try:
        import taxonomy
        return taxonomy.team_text(v)
    except Exception:
        return v


def _vehicle_word(key):
    """The vehicle as people read it: the English label the factors carry for it, else its key."""
    try:
        import conversions
        v = (conversions.load_factors().get("vehicles") or {}).get(key) or {}
        return ((v.get("labels") or {}).get("en")) or key
    except Exception:
        return key


def _date_words(iso):
    if not iso:
        return "not checked"
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return f"{d.day} {d:%b %Y}"
    except ValueError:
        return "not checked"


def team_id(team):
    """The team filter as the map sends it — the slot id (its select's value) or the team's NAME (a deep link) — as a
    slot id, or None for every team."""
    if not team or str(team).upper() == "ALL":
        return None
    import access
    t = access.canonical_ipt(team)
    if t:
        return t
    try:
        import taxonomy
        for k, v in (taxonomy.team_labels() or {}).items():
            if str(v).strip().lower() == str(team).strip().lower():
                return access.canonical_ipt(k) or k
    except Exception:
        pass
    return str(team)


def sheet(month_index, route_ids=None, team=None, acc=None, carbon_tool=False, now=None,
          origin=None, dest=None, discipline=None, map_only=False):
    """
    Everything the route map export prints for one month and the routes the filters let through. The filters are the
    public map's Route filtering, applied as the map applies them (map/index.html applyFilters and calculateKPIs):
    origin, destination and team from the ROUTE, discipline from the LINE; `route_ids` narrows further (the Routes page
    sends the routes it lists). Reads only.
    """
    import access
    import bulletin
    import bulletin_doc
    import restrictions
    mi = int(month_index)
    wd = bulletin.working_days()
    # a team code sees its own team only, whatever it asks for
    own = (acc or {}).get("ipt") if isinstance(acc, dict) else None
    team = own or team_id(team)
    norm = lambda v: None if (v is None or str(v).upper() == "ALL" or v == "") else v
    origin, dest, discipline = norm(origin), norm(dest), norm(discipline)
    want = set(route_ids) if route_ids else None
    routes = bulletin.drawn_routes()
    bulletin._stamp_caps(routes)

    def route_ok(rid):
        rp = routes.get(rid)
        if rp is None:                       # not drawn: let it through, the roll-up names it as not drawn
            return want is None or rid in want
        return ((want is None or rid in want) and (not origin or rp.get("origin") == origin)
                and (not dest or rp.get("dest") == dest)
                and (not team or (access.canonical_ipt(rp.get("ipt")) or rp.get("ipt")) == team))
    payload = dict(bulletin.month_payload(mi))
    lines = [l for l in (payload.get("lines") or [])
             if route_ok(l.get("route_id")) and (not discipline or l.get("discipline") == discipline)]
    payload["lines"] = lines
    R = bulletin.rollup_payloads([payload], routes, wd, acc=acc)
    rows = list(R.get("by_route") or [])
    ids = [r["route_id"] for r in rows]
    veh = {}
    for l in lines:
        veh.setdefault(l["route_id"], [])
        w = _vehicle_word(l.get("vehicle_type"))
        if w and w not in veh[l["route_id"]]:
            veh[l["route_id"]].append(w)
    checks = restrictions.stored_checks(ids) if ids else {}
    geo = bulletin_doc._geometries(ids)

    # letter pins, the busiest route's ends first (the bulletin's rule)
    places, letter_of = [], {}
    for r in rows:
        g = geo.get(r["route_id"])
        for name, loc_id, at in ((r.get("origin"), g[1] if g else None, g[0][0] if g else None),
                                 (r.get("dest"), g[2] if g else None, g[0][-1] if g else None)):
            key = loc_id or name
            if key and key not in letter_of:
                letter_of[key] = bulletin_doc._letters(len(places))
                places.append({"letter": letter_of[key], "name": name or "", "at": at})

    def letters(r):
        g = geo.get(r["route_id"])
        o = letter_of.get((g[1] if g else None) or r.get("origin"), "")
        d = letter_of.get((g[2] if g else None) or r.get("dest"), "")
        return f"{o} → {d}" if o and d else ""

    n0 = bulletin_doc.n0
    out_rows = []
    for r in rows:
        cap, a_day = r.get("cap"), r.get("two_way_a_day") or 0
        ck = checks.get(r["route_id"]) or {}
        out_rows.append({
            "route_id": r["route_id"], "letters": letters(r),
            "places": f"{r.get('origin') or ''} → {r.get('dest') or ''}".strip(" →"),
            "a_day": a_day, "a_day_text": n0(a_day),
            "loads_text": n0(r.get("movements_in_month")),
            "tonnes_text": (n0(r.get("tonnes")) + " t") if r.get("tonnes") is not None else "—",
            "vehicles_text": ", ".join(veh.get(r["route_id"]) or []) or "—",
            "lorries_text": n0(r.get("vehicles")) if r.get("vehicles") else "—",
            "flag_text": ("none set" if cap is None else
                          f"{cap:,} a day: above it" if a_day > cap else f"{cap:,} a day"),
            "flag_over": bool(cap is not None and a_day > cap),
            "checked_text": _date_words(ck.get("checked_at")),
            "color": bulletin_doc.VOLUME_RAMP[bulletin_doc.volume_class(a_day)],
        })
    map_routes = sorted(({"route_id": r["route_id"], "coords": geo[r["route_id"]][0], "a_day": r["a_day"],
                          "color": r["color"]} for r in out_rows if r["route_id"] in geo),
                        key=lambda r: (r["a_day"], r["route_id"]))
    month_long = bulletin.month_label_long(mi)
    import export      # the tenant's name and demo notice exactly as every other PDF reads them
    notice = export._demo_notice() or None
    team_words = _team_text(team) if team else "All teams"
    narrowed = [w for w in ((f"from {origin}" if origin else None), (f"to {dest}" if dest else None),
                            (discipline if discipline else None)) if w]
    S = {
        "title": f"Route map · {month_long}",
        "tenant": export._tenant_name() or "Wayscope",
        "demo_notice": notice, "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "month_long": month_long, "team_words": team_words,
        "filter_words": " · ".join([f"{len(out_rows)} route{'s' if len(out_rows) != 1 else ''}", team_words, *narrowed,
                                    month_long, "approved lines only"]),
        "map_only": bool(map_only),
        "as_at": f"Approved plan as at {(now or datetime.date.today()):%d %b %Y}".replace(" 0", " "),
        "working_days": wd,
        "rows": out_rows, "map_routes": map_routes, "map_sections": [], "places": places, "controls": [],
        "volume_legend": bulletin_doc.volume_legend(), "map_legend_title": "Two-way movements a day",
        "scheme_fields": SCHEME_FIELDS, "flag_words": FLAG_WORDS,
        "two_way_sentence": bulletin_doc.two_way_sentence(wd),
        "not_drawn": [r for r in (R.get("routes_not_drawn") or {}).get("routes") or []],
        "empty": not out_rows,
    }
    if carbon_tool:
        S["carbon_tool"] = carbon_tool_rows(mi, set(ids), discipline, acc)
    return S


def carbon_tool_rows(month_index, route_ids, discipline, acc):
    """H3: the NH Carbon Tool's transport inputs for the month — per Carbon Tool sheet, material and origin → destination:
    tonnes and the ONE-WAY LOADED km (carbon.scenario's baseline, Approved lines, the chosen routes and team)."""
    import carbon
    try:
        sc = carbon.scenario(acc=acc, from_month=month_index, to_month=month_index)
    except Exception as e:
        return {"rows": [], "error": f"{type(e).__name__}: {e}"}
    agg = {}
    for l in (sc.get("lines") or []):
        # the same lines as the map rows: the routes the filters let through, the discipline from the line
        if l.get("route_id") not in route_ids or (discipline and l.get("discipline") != discipline):
            continue
        # the scheme's own material name (a person reads "Precast / concrete", never the factor key "concrete")
        # one row per vehicle as well: the loaded km is the route worked out for THAT vehicle (none when it is not)
        k = (l.get("sheet") or "—", l.get("material_type") or "—", l.get("route_id"), l.get("vehicle") or "")
        a = agg.setdefault(k, {"tonnes": 0.0, "km": l.get("one_way_km")})
        a["tonnes"] += float(l.get("tonnes") or 0.0)
        if a["km"] is None and l.get("one_way_km") is not None:
            a["km"] = l.get("one_way_km")
    rows = [{"sheet": k[0], "material": k[1], "route_id": k[2], "tonnes": round(v["tonnes"], 1),
             "one_way_km": (round(v["km"], 1) if v["km"] is not None else None), "vehicle": _vehicle_word(k[3])}
            for k, v in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3]))]
    return {"rows": rows, "error": None}
