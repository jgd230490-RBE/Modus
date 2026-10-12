"""
bulletin_doc.py — the monthly bulletin as people read it (C4, 12 Oct 2026; review §2.6, mockup 9).

WHAT THIS IS
------------
The composition half of the bulletin. bulletin.py (Track B) computes the month roll-up with
the public map bar's rules and the conditions of the month, as JSON. This module turns that
into ONE view model, `sheet(month)`, with every figure already formatted as the words a person
reads, and renders it twice from the same model:

    html(sheet)                  GET /bulletin/?month=N   (staff, gated like /help/), print CSS
    export.build_bulletin_pdf()  GET /api/bulletin/month.pdf?month=N   (staff), A4 portrait

so the page and the PDF cannot disagree: test_bulletin.py asserts the headline figures in
pdf_text() of the PDF and in the HTML equal the roll-up's.

WHAT IT PRINTS (review §2.6 "Gap and build", mockup 9)
------------------------------------------------------
Page 1: the counting line; four headline figures (two-way movements a day; movements in the
month with the working days from the scheme's settings; routes in use; tonnes); the month's
routes on a map (Mapbox Static Images in the PDF, a schematic when it cannot be had; an inline
schematic on the HTML page) with letter pins on the sites and numbered local controls; the
busiest routes with this month, in the month, last month and the planning flag; the one-sentence
definition of a two-way movement (the map's kpi-note sentence); the demo notice.
Page 2: movements a day by route with each typed cap dashed (print treatment: light fill, solid
edge, label in ink — colour-system-1010.md); what is being moved (by discipline, the bar's own
panel); works affecting the roads this month (stored restriction hits overlapping the month,
the local controls, stockpiles over capacity, seasonal windows, planning flags exceeded, and
which routes were never checked); what changed since last month (plan against plan: the
approved plan for each month as it stands today — no earlier issue is stored); terms explained;
caveats; the report-a-lorry block, with the scheme's typed fields as placeholders.

13 Oct 2026 (the user): two additions, after a read of real UK construction-traffic monitoring
reports (Sizewell C's Transport Monitoring Report, Hinkley Point C's Transport Forum packs, CLOCS
Standard v4, TfL's CLP guidance, FORS v6, DESNZ's local authority emissions statistics;
notes/bulletin-research-1013.md):
  * "This month at a glance" — the Sizewell C tracker's shape: each item, this month's figure and
    the KIND of data (Forecast / Stored check / Not reported). The items a monitoring report fills
    from observed records (lorries counted, route adherence and hours, FORS / CLOCS / Euro VI / DVS
    shares, collisions, complaints) are listed as NOT REPORTED, never filled: this is a plan.
  * "Carbon by council" — the districts alone, each in the council layer's orange ramp (the map's
    AREA_RAMP_CARBON and AREA_STOPS.carbon, the same colours and stops) with its t CO2e in the
    month, drawn from the stored boundary polygons (areas.area_load): no routes, no road network,
    no Mapbox call. "No figure" is hatched, never a zero; a district with no approved route is the
    neutral grey. A table beside it (district, highway authority, t CO2e, share of the scheme's),
    the tally against the scheme's carbon (what is driven outside the districts loaded is named),
    the basis sentence, the ONS / OS licence lines and the Carbon page's stamp. A tenant with no
    council areas: no section at all.

RULES KEPT
----------
* One load = one two-way movement, never doubled: every figure here is bulletin.py's.
* Working days come from the roll-up (main._working_days); this module carries no day count.
* A typed cap is a "planning flag", never a limit or a block.
* No team appears: the per-team rows of the roll-up are not printed (a tenant choice, D33).
* Carbon carries carbon.SUMMARY_STAMP ("… planning estimate, DESNZ 2026 basis, not Carbon
  Tool figures").
* UK words: lorry / HGV; none of the landing page's banned words.

WHAT IT DOES NOT DO
-------------------
No stored snapshot (D28 asks for one per issued bulletin: a new tenanted table, not built), no
actuals (plan only), no figure per road (needs the shared-section layer, §2.2d), no email, no
tenant `bulletin` block for the typed fields (hours, contact, other formats print as
placeholders), and the HGV threshold line is left out until D28 settles it.
"""
import datetime
import html as _html

_MONTHS_LONG = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")

# The print treatment (colour-system-1010.md): the plan blue as a solid edge, its light tint
# inside, labels in ink; the planning flag in the cap red WITH its word; closures amber.
PLAN_BLUE = "#4A72C9"
PLAN_TINT = "#D7E0F3"        # the plan blue at the documented light-fill strength, on white
INK = "#1F2024"
FLAG_RED = "#DC2626"
CLOSURE_AMBER = "#D97706"
MUTED = "#57534E"

TITLE_WORD = "Lorry movements in"
COUNTING_LINE = ("Counts are two-way movements: one lorry out laden and back empty is one delivery, "
                 "counted once, never doubled. Approved plan only: no lorry was counted.")
PLACEHOLDER = "a typed field this scheme has not set yet"
CHART_MAX_ROUTES = 24
ZONE_WORDS = {"closure": "closure", "weight_limit": "weight limit", "works": "works area", "other": "local control"}
# 13 Oct 2026: the council layer's carbon colouring, the public map's own (map/index.html AREA_RAMP_CARBON,
# AREA_NONE, AREA_STOPS.carbon and the hatch of areaHatchImage) — test_bulletin.py reads the map and holds them equal
COUNCIL_RAMP = ("#EE9150", "#E8590C", "#B8470A", "#7C2D06")
COUNCIL_NONE = "#E7E5E4"
COUNCIL_STOPS = (50, 100, 200)               # t CO2e in the month, fixed, so a colour means the same tonnes every month
HATCH_INK, HATCH_PAPER = "#B8B2A8", "#F3F1EC"
NOT_REPORTED = "Not reported"


# --------------------------------------------------------------------------- #
#  Formatting — one place, so the PDF, the HTML and the harness read alike      #
# --------------------------------------------------------------------------- #
def n0(v):
    return "—" if v is None else f"{float(v):,.0f}"


def n1(v):
    return "—" if v is None else f"{float(v):,.1f}"


def wd_text(wd):
    return f"{float(wd):g}"


def two_way_sentence(wd):
    """The public map's kpi-note sentence, verbatim (map/index.html, calculateKPIs)."""
    return (f"Two-way movements = loads (deliveries) per working day ({wd_text(wd)}/month); "
            "each is a lorry out laden and back empty.")


def _date_long(d):
    return f"{d.day} {_MONTHS_LONG[d.month - 1]} {d.year}"


def _iso_short(s):
    """'2026-10-16' → '16 Oct 2026'; anything else as it came."""
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
        return f"{d.day} {_MONTHS_LONG[d.month - 1][:3]} {d.year}"
    except (TypeError, ValueError):
        return str(s) if s else ""


def _span_text(a, b):
    if not a and not b:
        return "no dates: always applies"
    if a and b:
        return f"{_iso_short(a)} to {_iso_short(b)}"
    return f"from {_iso_short(a)}" if a else f"until {_iso_short(b)}"


def _letters(i):
    return chr(65 + i) if i < 26 else ""


# --------------------------------------------------------------------------- #
#  The view model                                                              #
# --------------------------------------------------------------------------- #
def _geometries(route_ids):
    """{route_id: [(lon, lat), …]} — the LADEN leg the public map draws, from the same read."""
    import network
    want, out = set(route_ids), {}
    for f in (network.public_map_data() or {}).get("features", []) or []:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        if p.get("route_id") in want and p.get("type") == "Inbound Highway" and g.get("type") == "LineString":
            cs = [(float(c[0]), float(c[1])) for c in (g.get("coordinates") or []) if len(c) >= 2]
            if len(cs) >= 2:
                out[p["route_id"]] = (cs, p.get("origin_id"), p.get("dest_id"))
    return out


def _controls(span_from, span_to):
    """The local controls in force in the month: active zones that are not haul roads, numbered."""
    import zones
    out = []
    try:
        zs = zones.list_zones(include_inactive=False)
    except Exception:
        zs = []
    a, b = span_from.isoformat(), span_to.isoformat()
    for z in zs:
        if z.get("kind") == zones.HAUL_KIND:
            continue
        s, e = z.get("starts_on"), z.get("ends_on")
        if (s and s > b) or (e and e < a):
            continue
        bb = z.get("bbox")
        out.append({"n": len(out) + 1, "id": z.get("id"), "name": z.get("name") or z.get("id"),
                    "kind": ZONE_WORDS.get(z.get("kind"), "local control"), "note": z.get("note") or "",
                    "when": _span_text(s, e),
                    "at": (((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2) if bb else None)})
    return out


def council_class(v, unclipped=False):
    """The map's step for a district's t CO2e: 'nofig' (hatched), 'none' (grey) or 0-3 (the orange ramp)."""
    if v is None or (unclipped and not v > 0):
        return "nofig"
    if v < 0.01:
        return "none"
    return sum(1 for s in COUNCIL_STOPS if v >= s)


def council_fill(cls):
    return COUNCIL_NONE if cls == "none" else (HATCH_PAPER if cls == "nofig" else COUNCIL_RAMP[cls])


def _t(v):
    """t CO2e as the map's district label prints it: whole tonnes from 10 t, one decimal below."""
    return f"{v:,.0f} t" if v >= 10 else f"{v:,.1f} t"


def _share(v, whole):
    """A district's share of the scheme's carbon: whole per cent, "under 1%" for a sliver, "—" with no figure."""
    if v is None or not whole or not v > 0:
        return "—"
    pc = 100 * v / whole
    return "under 1%" if pc < 0.5 else f"{pc:.0f}%"


def _council_legend():
    s = COUNCIL_STOPS
    return [{"label": f"under {s[0]} t", "fill": COUNCIL_RAMP[0], "hatch": False},
            {"label": f"{s[0]} to {s[1] - 1} t", "fill": COUNCIL_RAMP[1], "hatch": False},
            {"label": f"{s[1]} to {s[2] - 1} t", "fill": COUNCIL_RAMP[2], "hatch": False},
            {"label": f"{s[2]} t and over", "fill": COUNCIL_RAMP[3], "hatch": False},
            {"label": "no approved route", "fill": COUNCIL_NONE, "hatch": False},
            {"label": "no figure (never a zero)", "fill": HATCH_PAPER, "hatch": True}]


def _council_carbon(mi, wd, month_long):
    """
    The districts' t CO2e in the month (areas.area_load, the map's figures), formatted; None when the
    tenant has no council districts (then the bulletin prints nothing about them).
    """
    import areas
    stored = areas.stored_areas()
    if not any(a["tier"] == "district" for a in stored):
        return None
    try:
        A = areas.area_load(mi, working_days=wd, geometry=True)
    except Exception as e:                       # the section stays, and says why there is no figure
        return {"error": f"The council figures could not be read for {month_long} ({type(e).__name__}).",
                "title": f"Carbon by council in {month_long}", "districts": []}
    unclipped = bool(A.get("routes_not_clipped"))
    tot = A.get("totals") or {}
    scheme = tot.get("co2_t")
    districts = []
    for a in A.get("areas") or []:
        if a["tier"] != "district":
            continue
        v = a.get("co2_t")
        cls = council_class(v, unclipped)
        if cls == "nofig":
            text = "no figure yet" if (v is not None and unclipped) else "no figure"
        elif cls == "none":
            text = ("no approved route" if not (a.get("routes") or a.get("return_only_routes") or a.get("edge_routes"))
                    else "under 0.1 t")
        else:
            text = _t(v)
        districts.append({"area_id": a["area_id"], "name": a["name"], "co2_t": v, "cls": cls, "text": text,
                          "fill": council_fill(cls), "highway_authority": a.get("highway_authority") or "",
                          "share": _share(v, scheme),
                          "rings": areas.rings_of(a.get("geometry")), "label_at": a.get("label_point")})
    districts.sort(key=lambda d: (-(d["co2_t"] or 0), d["name"]))
    d_sum = (tot.get("co2_t_by_tier") or {}).get("district")
    n = len(districts)
    if scheme is None or d_sum is None:
        tally = "No total is given: at least one district, or the scheme, has no carbon figure this month."
    elif scheme <= 0:
        tally = f"No approved haul carbon in {month_long}."
    else:
        out = scheme - d_sum
        tally = (f"The {n} districts shown carry {_t(d_sum)} of the scheme's {_t(scheme)} CO2e in {month_long}"
                 + (f"; the other {_t(out)} is driven on roads outside them, in council areas not loaded."
                    if out >= 0.05 else ": all of it."))
    county_lines = []
    for a in A.get("areas") or []:
        if a["tier"] == "county" and a.get("co2_t") is not None:
            county_lines.append(f"{a['name']} ({a.get('tier_words') or 'county'}"
                                + (f"; highway authority {a['highway_authority']}" if a.get("highway_authority") else "")
                                + f"): {_t(a['co2_t'])} CO2e in {month_long} on its roads.")
    notes = [x for x in (A.get("notes") or []) if any(k in x for k in ("CO2e", "clipped", "carbon"))]
    sources = []
    for a in stored:
        if a["tier"] == "district" and a.get("source") and a["source"] not in sources:
            sources.append(a["source"])
    return {
        "error": None,
        "title": f"Carbon by council in {month_long}",
        "lede": (f"The haul carbon emitted inside each local authority district in {month_long}, t CO2e: each route's "
                 "carbon for the month split by the km it drives inside the district, laden and empty. Districts only: "
                 "no routes or roads are drawn."),
        "districts": districts,
        "legend": _council_legend(),
        "tally": tally,
        "basis": ("Split by the km inside each district; across one tier it adds up to the scheme's carbon. "
                  "These are this scheme's lorries only, a planning estimate: they are not comparable with the DESNZ "
                  "local authority greenhouse gas statistics, which count every vehicle and every source."),
        "county_lines": county_lines, "notes": notes,
        "attribution": list(A.get("attribution") or []),
        "sources": [f"Boundaries: {x}, generalised to 200 m." for x in sources],
        "stamp": (A.get("carbon") or {}).get("stamp") or "",
    }


def _glance(H, R, routes_view, works, controls, rs_status, never, checked_at, month_long):
    """
    "This month at a glance" in the Sizewell C tracker's shape: the item, this month's figure and the kind of
    data. What a monitoring report fills from observed records is listed, and marked Not reported.
    """
    import bulletin
    c = R.get("carbon") or {}
    flagged = [r for r in routes_view if r["cap"] is not None]
    over = [r for r in flagged if r["over_flag"]]
    fc = "Forecast: the approved plan"
    listed = f"{len(works) + len(controls)} listed"
    if rs_status == bulletin.NEVER_CHECKED:
        rw = (f"{len(controls)} local control{'s' if len(controls) != 1 else ''}",
              "Road works never checked for this month's routes")
    elif never:
        rw = (listed, f"Stored check; {len(never)} route{'s' if len(never) != 1 else ''} never checked")
    else:
        rw = (listed, f"Stored check of {_iso_short(checked_at)}" if checked_at else "Stored check")
    rows = [
        ("Two-way lorry movements a day", n0(H.get("two_way_a_day")), fc),
        ("Lorry movements in the month", n0(H.get("movements_in_month")), fc),
        ("Routes in use", n0(H.get("routes_in_use")) if H.get("routes_in_use") is not None else "—", fc),
        ("Routes planned above their planning flag",
         (f"{len(over)} of {len(flagged)}" if flagged else "no planning flag typed"), "Forecast against the scheme's typed flags"),
        ("Haul carbon in the month",
         (n1(c["co2_t_in_month"]) + " t CO2e") if c.get("co2_t_in_month") is not None else "—",
         "Forecast: a planning estimate on DESNZ 2026 factors"),
        (f"Road works, closures and local controls in {month_long}", rw[0], rw[1]),
        ("Lorries counted on the roads or at the site gates", NOT_REPORTED, "This bulletin is a plan: no lorry was counted"),
        ("Lorries kept to the approved routes and working hours", NOT_REPORTED, "Needs observed records; not in this bulletin"),
        ("Vehicle and operator standards (FORS, CLOCS, Euro VI, Direct Vision Standard)", NOT_REPORTED,
         "Not in this bulletin"),
        ("Collisions and near misses", NOT_REPORTED, "Not in this bulletin"),
        ("Enquiries and complaints", NOT_REPORTED, "Not in this bulletin; how to report a lorry is at the end"),
    ]
    return [{"item": a, "figure": b, "data": d, "not_reported": b == NOT_REPORTED} for a, b, d in rows]


def _flag_text(row):
    cap = row.get("cap")
    if cap is None:
        return row.get("cap_wording") or "no planning cap typed"
    a_day = row.get("two_way_a_day") or 0
    side = "plan is above it" if a_day > cap else "plan is within it"
    return f"{cap:,} a day · {side}"


def sheet(month_index, acc=None, now=None):
    """Everything the page and the PDF print for one month, formatted. Reads; never writes."""
    import bulletin
    import restrictions
    import weeks
    main = bulletin._main()
    mi = int(month_index)
    page = bulletin.month_page(mi, acc)
    R = page["rollup"]
    wd = page["working_days"]
    H = R.get("headline") or {}
    count = int(getattr(main, "MONTH_COUNT", mi))
    prev = bulletin.month_rollup(mi - 1, acc) if mi > 1 else None
    nxt = bulletin.month_rollup(mi + 1, acc) if mi < count else None
    span_from, span_to = weeks.month_span(mi)
    today = (now or datetime.datetime.now(datetime.timezone.utc)).date()
    month_long = page["month"]["label_long"]
    prev_long = bulletin.month_label_long(mi - 1) if mi > 1 else None
    next_long = bulletin.month_label_long(mi + 1) if nxt is not None else None

    rows = list(R.get("by_route") or [])
    prev_rows = {r["route_id"]: r for r in ((prev or {}).get("by_route") or [])}
    geo = _geometries([r["route_id"] for r in rows])

    # letter pins: the busiest route's sites first, so the top route reads "A → B"
    places, letter_of = [], {}
    for r in rows:
        g = geo.get(r["route_id"])
        for name, loc_id, at in ((r.get("origin"), g[1] if g else None, g[0][0] if g else None),
                                 (r.get("dest"), g[2] if g else None, g[0][-1] if g else None)):
            key = loc_id or name
            if not key or key in letter_of:
                continue
            letter_of[key] = _letters(len(places))
            places.append({"letter": letter_of[key], "name": name or "", "at": at})

    def letters_of(r):
        g = geo.get(r["route_id"])
        o = letter_of.get((g[1] if g else None) or r.get("origin"), "")
        d = letter_of.get((g[2] if g else None) or r.get("dest"), "")
        return f"{o} → {d}" if o and d else ""

    def route_view(r):
        pr = prev_rows.get(r["route_id"])
        last = ("no earlier month in the programme" if mi <= 1 else
                (f"{n0(pr['two_way_a_day'])} a day" if pr else "none planned"))
        return {"route_id": r["route_id"], "label": r.get("label") or r["route_id"], "letters": letters_of(r),
                "a_day": r.get("two_way_a_day"), "a_day_text": n0(r.get("two_way_a_day")),
                # 12 Oct 2026 (the user, evening): a page people read prints WHOLE movements ("6,874", never
                # "6,873.8"); the figure is still the fractional sum, rounded once for display
                "in_month_text": n0(r.get("movements_in_month")), "last_month_text": last,
                "cap": r.get("cap"), "flag_text": _flag_text(r),
                "over_flag": bool(r.get("cap") is not None and (r.get("two_way_a_day") or 0) > r["cap"])}

    routes_view = [route_view(r) for r in rows]
    vmax = max([r["a_day"] or 0 for r in routes_view] or [0])
    map_routes = [{"route_id": r["route_id"], "coords": geo[r["route_id"]][0], "a_day": r["a_day"] or 0,
                   "weight": ((r["a_day"] or 0) / vmax if vmax else 0.0)}
                  for r in routes_view if r["route_id"] in geo]
    controls = _controls(span_from, span_to)

    headline = [
        {"key": "two_way_a_day", "value": n0(H.get("two_way_a_day")),
         "label": "two-way movements a day, all routes, approved plan"},
        {"key": "movements_in_month", "value": n0(H.get("movements_in_month")),
         "label": f"movements in the month ({wd_text(wd)} working days, from the scheme's settings)"},
        {"key": "routes_in_use", "value": n0(H.get("routes_in_use")) if H.get("routes_in_use") is not None else "—",
         "label": "routes in use, approved, with a stored road route"},
        {"key": "tonnes", "value": (n0(H.get("tonnes")) + " t") if H.get("tonnes") is not None else "—",
         "label": "material moved in the month"},
    ]

    # what is being moved: the bar's own panel, by discipline; rows add up to the headline
    moved = [{"name": d["name"], "a_day": n0(d["two_way_a_day"]), "vehicles": n0(d["vehicles_a_day"]),
              "t_day": n0(d["tonnes_a_day"])} for d in (R.get("breakdown") or {}).get("discipline") or []]

    # works affecting the roads this month
    C = page["conditions"]
    prov = restrictions.provider() or {}
    rs = C["restrictions"]
    works, seen = [], {}
    for h in rs.get("hits") or []:
        k = (h.get("headline"), h.get("from"), h.get("to"))
        if k in seen:
            seen[k]["routes"].append(h["route_id"])
            continue
        where = " ".join(x for x in (h.get("road_nr"), h.get("road_name")) if x) or "on the route"
        what = h.get("what") or h.get("label") or "restriction"
        detail = h.get("headline") or ""
        w = {"where": where, "what": what,
             # "Mass limit: Mass limit 18 t" read twice; the headline alone when it already says what
             "detail": detail, "line": (detail if detail.lower().startswith(what.lower()) else f"{what}: {detail}".rstrip(": ")),
             "when": _span_text(h.get("from"), h.get("to")),
             "who": prov.get("name") or "the road authority's published list", "routes": [h["route_id"]],
             "kind": h.get("kind")}
        seen[k] = w
        works.append(w)
    for w in works:
        w["routes_text"] = (f"within the check distance of {len(w['routes'])} route{'s' if len(w['routes']) != 1 else ''} "
                            f"({', '.join(sorted(set(w['routes'])))})")
    never = rs.get("never_checked_routes") or []
    in_month = sorted({*(R.get("routes_in_use") or []), *never})
    checks = []
    if rs.get("status") == bulletin.NEVER_CHECKED:
        checks.append(f"Road works and closures: never checked for any of this month's routes; "
                      f"no stored check, so this list is not a clear road.")
    elif never:
        checks.append(f"Road works and closures: never checked for {len(never)} of this month's routes "
                      f"({', '.join(never)}); not a clear road.")
    elif rs.get("checked_at"):
        checks.append(f"Road works and closures: from the stored check of {_iso_short(rs['checked_at'])} "
                      f"({prov.get('name') or 'the road authority'}).")
    if rs.get("past_month_note"):
        checks.append(rs["past_month_note"])
    others = []
    for p in C.get("stockpiles_over") or []:
        others.append({"kind": "Over capacity", "text": p["wording"]})
    for s in C.get("seasonal") or []:
        others.append({"kind": "Seasonal window", "text": f"{s.get('name')}: {s.get('message') or ''} "
                       f"Applies to {len(s.get('routes') or [])} route(s) this month.".strip()})
    for e in (C.get("route_caps") or {}).get("exceeded") or []:
        others.append({"kind": "Planning flag", "text": f"Route {e['route_id']}: {n0(e['two_way_a_day'])} two-way "
                       f"movements a day planned against a planning flag of {e['cap']:,} a day. A planning flag "
                       "is never a block."})

    # what changed since last month — plan against plan
    def month_row(label, ro, this=False):
        if ro is None:
            return None
        h = ro.get("headline") or {}
        c = ro.get("carbon") or {}
        return {"label": label, "this": this, "a_day": n0(h.get("two_way_a_day")),
                "vehicles": n0((ro.get("vehicles") or {}).get("fleet")),
                "co2_day": (n1(c.get("co2_t_a_day")) + " t") if c.get("co2_t_a_day") is not None else "—",
                "routes": n0(h.get("routes_in_use")) if h.get("routes_in_use") is not None else "—"}
    change_rows = [x for x in (month_row(prev_long, prev) if prev is not None else None,
                               month_row(month_long, R, this=True),
                               month_row(f"{next_long} (next)" if next_long else None, nxt) if nxt is not None else None) if x]
    if prev is None:
        change_text = "This is the first month of the programme: there is no earlier month to compare."
    else:
        ph, pv = prev.get("headline") or {}, prev.get("vehicles") or {}
        was = set(prev.get("routes_in_use") or [])
        now_r = set(R.get("routes_in_use") or [])
        parts = [f"Two-way movements a day {n0(ph.get('two_way_a_day'))} → {n0(H.get('two_way_a_day'))}",
                 f"vehicles needed {n0(pv.get('fleet'))} → {n0((R.get('vehicles') or {}).get('fleet'))}",
                 f"CO2e a day {n1((prev.get('carbon') or {}).get('co2_t_a_day'))} → "
                 f"{n1((R.get('carbon') or {}).get('co2_t_a_day'))} t"]
        if was == now_r:
            parts.append(f"the same {len(now_r)} route{'s' if len(now_r) != 1 else ''}")
        else:
            added, gone = sorted(now_r - was), sorted(was - now_r)
            parts.append(f"routes {len(was)} → {len(now_r)}" + (f" (new: {', '.join(added)})" if added else "")
                         + (f" (finished: {', '.join(gone)})" if gone else ""))
        change_text = f"Since {prev_long}: " + "; ".join(parts) + "."

    glance = _glance(H, R, routes_view, works, controls, rs.get("status"), never, rs.get("checked_at"), month_long)
    council = _council_carbon(mi, wd, month_long)

    carbon = R.get("carbon") or {}
    veh = R.get("vehicles") or {}
    terms = [
        ("Two-way movement", "one lorry out laden and back empty: one delivery, counted once, never doubled. "
         + two_way_sentence(wd) + " " + page["terms"]["other_schemes"]),
        ("Forecast", f"the approved plan for the month divided by its working days ({wd_text(wd)}, from the "
                     "scheme's settings): a planning figure, not a count. The month's loads are summed as typed "
                     "(fractional), not rounded per line; the total is then shown to the nearest whole movement."),
        ("Vehicles needed", veh.get("rule") or ""),
        # the roll-up writes CO₂e; the view model keeps one spelling (Helvetica has no subscript two)
        # and the HTML page puts the subscript back
        ("CO2e", ((carbon.get("rule") or "") + " " + (carbon.get("stamp") or "")).replace("CO₂e", "CO2e")),
        ("Planning flag", page["terms"]["cap"] + " It is never a legal limit unless the scheme types it as agreed."),
    ]
    caveats = ["This bulletin is a planning forecast from the approved plan, not a monitoring report: no lorry was counted.",
               "Every figure is per route. Where several routes share a road, the lorries on that road are their sum; "
               "this bulletin does not yet print a figure per road.",
               "Other traffic, including local hauliers working for other customers, uses these roads too; "
               "the figures are this scheme's lorries only."]
    nd = R.get("routes_not_drawn") or {}
    if nd.get("lines"):
        _many = nd["lines"] != 1
        caveats.append(f"{nd['lines']} line{'s' if _many else ''} on route{'s' if len(nd.get('routes') or []) != 1 else ''} "
                       f"with no stored road route ({', '.join(nd.get('routes') or [])}) "
                       f"{'are' if _many else 'is'} not in these figures: listed here, not counted as zero.")
    if veh.get("excludes_unbaked_lines"):
        caveats.append(veh.get("label", "") + ".")
    if (R.get("payload_fallback") or {}).get("note"):
        caveats.append(R["payload_fallback"]["note"])
    if carbon.get("error"):
        caveats.append(carbon["error"])
    caveats.append(carbon.get("stamp") or "")

    return {
        "month": page["month"], "month_long": month_long, "prev_long": prev_long, "next_long": next_long,
        "month_index": mi, "has_prev": mi > 1, "has_next": nxt is not None,
        "title": f"{TITLE_WORD} {month_long}",
        "tenant": page.get("tenant_name") or "Wayscope",
        "demo_notice": page.get("demo_notice"),
        "as_at": f"Approved plan as at {_date_long(today)}",
        "counting_line": COUNTING_LINE,
        "two_way_sentence": two_way_sentence(wd),
        "other_schemes": page["terms"]["other_schemes"],
        "working_days": wd,
        "empty": bool(R.get("empty")), "empty_note": R.get("note"),
        "headline": headline,
        "routes": routes_view, "busiest": routes_view[:len(R.get("busiest_routes") or [])],
        "flagged_routes": sum(1 for r in routes_view if r["cap"] is not None),
        "places": places, "controls": controls, "map_routes": map_routes,
        "moved": moved,
        "moved_total": {"a_day": n0(H.get("two_way_a_day")), "vehicles": n0(veh.get("fleet")),
                        "t_day": n0((H.get("tonnes") / wd) if H.get("tonnes") is not None and wd else None)},
        "works": works, "checks": checks, "others": others,
        "glance": glance, "council": council,
        "change_rows": change_rows, "change_text": change_text,
        "terms": terms, "caveats": [c for c in caveats if c],
        # 12 Oct 2026 (Track C review): the tenant's typed concern_email (the map's "Report a concern"
        # address) when set; the placeholder only while it is not
        "report": {"lorry": f"Report a lorry off route: the date, time, place, direction of travel and registration, to "
                            + (f"{page['concern_email']}." if page.get("concern_email")
                               else f"[contact line and email: {PLACEHOLDER}]."),
                   "hours": f"Working hours: [{PLACEHOLDER}].",
                   "formats": f"Large print and other formats: [{PLACEHOLDER}]."},
        "carbon_stamp": carbon.get("stamp"),
        "foot": "A planning forecast, not a monitoring report · prepared with Wayscope",
        "pdf_href": f"/api/bulletin/month.pdf?month={mi}",
        "rollup": R,
    }


# --------------------------------------------------------------------------- #
#  The map projection (shared by the PDF schematic and the HTML page)           #
# --------------------------------------------------------------------------- #
def projector(points, w, h, pad):
    """f(lon, lat) → (x, y) with y UP, fitting every point into w × h with `pad` round it; None when empty."""
    import math
    pts = [p for p in points if p]
    if not pts:
        return None
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
    kx = math.cos(math.radians((lo_y + hi_y) / 2)) or 1.0
    span_x, span_y = max((hi_x - lo_x) * kx, 1e-6), max(hi_y - lo_y, 1e-6)
    scale = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_y)
    ox, oy = (w - span_x * scale) / 2, (h - span_y * scale) / 2
    return lambda lon, lat: (ox + (lon - lo_x) * kx * scale, oy + (lat - lo_y) * scale)


def council_points(C):
    return [p for d in (C or {}).get("districts") or [] for ring in d["rings"] for p in ring]


def map_points(S):
    return ([c for r in S["map_routes"] for c in r["coords"]]
            + [p["at"] for p in S["places"] if p.get("at")] + [z["at"] for z in S["controls"] if z.get("at")])


# --------------------------------------------------------------------------- #
#  HTML — GOV.UK's order: the page first, the PDF alongside                     #
# --------------------------------------------------------------------------- #
def _e(v):
    return _html.escape(str(v if v is not None else ""), quote=True)


def _co2(s):
    return str(s).replace("CO2e", "CO₂e")


def _svg_map(S, w=720, h=340):
    proj = projector(map_points(S), w, h, 24)
    if proj is None:
        return '<p class="muted">No route with a stored road route to draw this month.</p>'
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Schematic of this month\'s haul routes" class="map">',
           f'<rect x="0" y="0" width="{w}" height="{h}" fill="#FAFAF9" stroke="#D6D3D1"/>']
    for r in sorted(S["map_routes"], key=lambda r: r["weight"]):
        pts = " ".join(f"{x:.1f},{h - y:.1f}" for x, y in (proj(*c) for c in r["coords"]))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{PLAN_BLUE}" stroke-width="{1.5 + 5 * r["weight"]:.1f}" '
                   f'stroke-linecap="round" stroke-linejoin="round"><title>{_e(r["route_id"])}</title></polyline>')
    for p in S["places"]:
        if not p.get("at") or not p["letter"]:
            continue
        x, y = proj(*p["at"])
        out.append(f'<circle cx="{x:.1f}" cy="{h - y:.1f}" r="9" fill="{INK}"/>'
                   f'<text x="{x:.1f}" y="{h - y + 4.5:.1f}" text-anchor="middle" class="pin">{_e(p["letter"])}</text>')
    for z in S["controls"]:
        if not z.get("at"):
            continue
        x, y = proj(*z["at"])
        out.append(f'<rect x="{x - 9:.1f}" y="{h - y - 9:.1f}" width="18" height="18" rx="3" fill="{CLOSURE_AMBER}"/>'
                   f'<text x="{x:.1f}" y="{h - y + 4.5:.1f}" text-anchor="middle" class="pin">{z["n"]}</text>')
    out.append("</svg>")
    return "".join(out)


def _sw_style(fill, hatch):
    return (f"repeating-linear-gradient(45deg,{HATCH_INK} 0 2px,{HATCH_PAPER} 2px 6px)" if hatch else fill)


def _svg_council(C, w=720, h=560):
    """The districts alone in the orange ramp, a white 2.5 px border between them, one label each."""
    proj = projector(council_points(C), w, h, 16)
    if proj is None:
        return '<p class="muted">No district boundary to draw.</p>'
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Haul carbon by local authority district, t CO2e in the month" class="map">',
           f'<defs><pattern id="cc-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           f'<rect width="8" height="8" fill="{HATCH_PAPER}"/><rect width="2" height="8" fill="{HATCH_INK}"/></pattern></defs>']
    for d in C["districts"]:
        path = " ".join("M" + " L".join(f"{x:.1f},{h - y:.1f}" for x, y in (proj(*p) for p in ring)) + " Z" for ring in d["rings"])
        fill = "url(#cc-hatch)" if d["cls"] == "nofig" else d["fill"]
        out.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd" stroke="#FFFFFF" stroke-width="2.5" stroke-linejoin="round">'
                   f'<title>{_e(d["name"])}: {_e(_co2(d["text"]))}</title></path>')
    for d in C["districts"]:
        if not d.get("label_at"):
            continue
        x, y = proj(*d["label_at"])
        out.append(f'<text x="{x:.1f}" y="{h - y - 2:.1f}" text-anchor="middle" class="cl"><tspan class="cn">{_e(d["name"])}</tspan>'
                   f'<tspan x="{x:.1f}" dy="17">{_e(_co2(d["text"]))}</tspan></text>')
    out.append("</svg>")
    return "".join(out)


def _council_html(C):
    """The carbon-by-council section of the page; empty for a tenant with no council districts."""
    if not C:
        return ""
    e = _e
    if C.get("error"):
        return f'<h2>{e(C["title"])}</h2><p class="empty">{e(C["error"])}</p>'
    sw = "".join(f'<span class="lg"><span class="sw" style="background:{_sw_style(g["fill"], g["hatch"])}"></span>{e(g["label"])}</span>'
                 for g in C["legend"])
    rows = "".join(f'<tr><td><span class="sw" style="background:{_sw_style(d["fill"], d["cls"] == "nofig")}"></span>'
                   f'{e(d["name"])}</td><td>{e(d["highway_authority"])}</td><td class="n">{e(_co2(d["text"]))}</td>'
                   f'<td class="n">{e(d["share"])}</td></tr>' for d in C["districts"])
    notes = "".join(f"<li>{e(_co2(x))}</li>" for x in C["county_lines"] + C["notes"])
    lic = " ".join(e(x) for x in C["sources"] + C["attribution"])
    return (f'<h2>{e(C["title"])}</h2>'
            f'<p>{e(_co2(C["lede"]))}</p>'
            f'<div class="mapwrap" data-bulletin="council-map">{_svg_council(C)}</div>'
            f'<p class="legend cc-legend">t CO₂e in the month: {sw}</p>'
            f'<div class="tw"><table data-bulletin="council"><thead><tr><th>District</th><th>Highway authority</th>'
            f'<th>t CO₂e in the month</th><th>Share of the scheme&#39;s</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p>{e(_co2(C["tally"]))}</p>'
            + (f'<ul>{notes}</ul>' if notes else "")
            + f'<p class="muted">{e(_co2(C["basis"]))} {e(_co2(C["stamp"]))}.</p>'
            f'<p class="muted">{lic}</p>')


def _svg_chart(S, w=720):
    rows = S["routes"]                      # every route: the PDF charts the busiest CHART_MAX_ROUTES
    if not rows:
        return '<p class="muted">No route to chart this month.</p>'
    lab_w, row_h, top = 260, 24, 8
    h = top + row_h * len(rows) + 28
    vmax = max([r["a_day"] or 0 for r in rows] + [r["cap"] or 0 for r in rows]) or 1
    bw = w - lab_w - 60
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Two-way movements a day by route" class="chart">']
    for i, r in enumerate(rows):
        y = top + i * row_h
        lw = bw * (r["a_day"] or 0) / vmax
        out.append(f'<text x="{lab_w - 8}" y="{y + 15}" text-anchor="end" class="lab">{_e(r["label"])}</text>'
                   f'<rect x="{lab_w}" y="{y + 3}" width="{lw:.1f}" height="15" fill="{PLAN_TINT}" stroke="{PLAN_BLUE}" stroke-width="2"/>'
                   f'<text x="{lab_w + lw + 6:.1f}" y="{y + 15}" class="val">{_e(r["a_day_text"])}</text>')
        if r["cap"] is not None:
            cx = lab_w + bw * r["cap"] / vmax
            out.append(f'<line x1="{cx:.1f}" y1="{y}" x2="{cx:.1f}" y2="{y + row_h}" stroke="{FLAG_RED}" stroke-width="2" '
                       f'stroke-dasharray="4 3"><title>planning flag {r["cap"]} a day</title></line>')
    out.append(f'<text x="{lab_w}" y="{h - 8}" class="lab">0</text>'
               f'<text x="{lab_w + bw}" y="{h - 8}" text-anchor="end" class="lab">{_e(n0(vmax))} a day</text></svg>')
    return "".join(out)


def html(S):
    """The bulletin as an HTML page: one column on a phone, figures first, a print stylesheet."""
    e = _e
    head = "".join(f'<div class="fig"><div class="v">{e(f["value"])}</div><div class="l">{e(f["label"])}</div></div>'
                   for f in S["headline"])
    places = " · ".join(f'<b>{e(p["letter"])}</b> {e(p["name"])}' for p in S["places"] if p["letter"])
    controls = " · ".join(f'<b class="amber">{z["n"]}</b> {e(z["name"])}' for z in S["controls"])
    busiest = "".join(
        f'<tr><td>{e(r["label"])}{(" <span class=muted>(" + e(r["letters"]) + ")</span>") if r["letters"] else ""}</td>'
        f'<td class="n">{e(r["a_day_text"])}</td><td class="n">{e(r["in_month_text"])}</td><td>{e(r["last_month_text"])}</td>'
        f'<td class="{"flag" if r["over_flag"] else ""}">{e(r["flag_text"])}</td></tr>' for r in S["busiest"])
    moved = "".join(f'<tr><td>{e(m["name"])}</td><td class="n">{e(m["a_day"])}</td><td class="n">{e(m["vehicles"])}</td>'
                    f'<td class="n">{e(m["t_day"])}</td></tr>' for m in S["moved"])
    mt = S["moved_total"]
    works = "".join(f'<tr><td>{e(w["where"])}</td><td>{e(w["line"])}<br><span class="muted">'
                    f'{e(w["routes_text"])}</span></td><td>{e(w["when"])}<br><span class="muted">{e(w["who"])}</span></td></tr>'
                    for w in S["works"])
    works += "".join(f'<tr><td><b class="amber">{z["n"]}</b> {e(z["name"])}</td><td>{e(z["kind"])}'
                     f'{(": " + e(z["note"])) if z["note"] else ""}</td><td>{e(z["when"])}<br><span class="muted">'
                     f'typed by the scheme</span></td></tr>' for z in S["controls"])
    others = "".join(f'<li><b>{e(o["kind"])}.</b> {e(o["text"])}</li>' for o in S["others"])
    checks = "".join(f"<li>{e(c)}</li>" for c in S["checks"])
    change = "".join(f'<tr class="{"this" if c["this"] else ""}"><td>{e(c["label"])}</td><td class="n">{e(c["a_day"])}</td>'
                     f'<td class="n">{e(c["vehicles"])}</td><td class="n">{e(_co2(c["co2_day"]))}</td><td class="n">{e(c["routes"])}</td></tr>'
                     for c in S["change_rows"])
    terms = "".join(f"<dt>{e(_co2(k))}</dt><dd>{e(_co2(v))}</dd>" for k, v in S["terms"])
    caveats = "".join(f"<li>{e(_co2(c))}</li>" for c in S["caveats"])
    notice = (f'<div class="notice">{e(S["demo_notice"])}</div>' if S["demo_notice"] else "")
    mi = S["month_index"]
    nav = ((f'<a href="/bulletin/?month={mi - 1}">‹ {e(S["prev_long"])}</a>' if S["has_prev"] else "<span></span>")
           + (f'<a href="/bulletin/?month={mi + 1}">{e(S["next_long"])} ›</a>' if S["has_next"] else "<span></span>"))
    empty = (f'<p class="empty">{e(S["empty_note"])}</p>' if S["empty"] and S["empty_note"] else "")
    glance = "".join(f'<tr class="{"nr" if g["not_reported"] else ""}"><td>{e(_co2(g["item"]))}</td><td class="n">{e(_co2(g["figure"]))}</td>'
                     f'<td>{e(_co2(g["data"]))}</td></tr>' for g in S["glance"])
    v = {
        "page_title": e(S["title"]) + " · " + e(S["tenant"]) + ((" · " + e(S["demo_notice"])) if S["demo_notice"] else ""),
        "title": e(S["title"]), "tenant": e(S["tenant"]), "as_at": e(S["as_at"]), "pdf_href": e(S["pdf_href"]),
        "counting_line": e(S["counting_line"]),
        "controls_text": (" · Local controls: " + controls) if controls else "",
        "last_head": e(S["prev_long"] or "Last month"),
        "flagged": S["flagged_routes"], "n_routes": len(S["routes"]),
        "two_way_sentence": e(S["two_way_sentence"]), "other_schemes": e(S["other_schemes"]),
        "mt_a_day": e(mt["a_day"]), "mt_vehicles": e(mt["vehicles"]), "mt_t_day": e(mt["t_day"]),
        "month_long": e(S["month_long"]),
        "works": works or '<tr><td colspan="3" class="muted">Nothing stored for this month.</td></tr>',
        "change_text": e(_co2(S["change_text"])),
        "rep_lorry": e(S["report"]["lorry"]), "rep_hours": e(S["report"]["hours"]), "rep_formats": e(S["report"]["formats"]),
        "foot": e(S["foot"]), "svg_map": _svg_map(S), "svg_chart": _svg_chart(S),
        "glance": glance, "council": _council_html(S["council"]),
        "notice": notice, "nav": nav, "empty": empty, "head": head, "places": places, "busiest": busiest,
        "moved": moved, "checks": checks, "others": others, "change": change, "terms": terms, "caveats": caveats,
        "INK": INK, "MUTED": MUTED, "PLAN_BLUE": PLAN_BLUE, "PLAN_TINT": PLAN_TINT, "FLAG_RED": FLAG_RED,
        "CLOSURE_AMBER": CLOSURE_AMBER,
    }
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
:root{{color-scheme:light;--ink:{INK};--muted:{MUTED};--line:#E7E5E4;--plan:{PLAN_BLUE};--tint:{PLAN_TINT};--flag:{FLAG_RED};--amber:{CLOSURE_AMBER};}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:var(--ink);font:16px/1.5 Inter,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:880px;margin:0 auto;padding:16px}}
h1{{font-size:26px;line-height:1.2;margin:8px 0 4px}}
h2{{font-size:19px;margin:28px 0 8px;padding-top:12px;border-top:2px solid var(--ink)}}
p,li,dd,td,th{{font-size:15px}}
.muted{{color:var(--muted)}} .amber{{color:var(--amber)}}
.notice{{display:inline-block;background:#FFF7ED;color:#9A3412;border:1px solid #FDBA74;border-radius:999px;padding:3px 12px;font-size:14px;font-weight:700}}
.sub{{color:var(--muted);font-size:15px;margin:0}}
.count{{background:#F5F5F4;border-left:3px solid var(--plan);padding:10px 14px;margin:14px 0;font-size:15px}}
.figs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}}
@media (min-width:720px){{.figs{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
.fig{{border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.fig .v{{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}} .fig .l{{font-size:14px;color:var(--muted)}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}}
.btn{{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:6px;background:#C2410C;color:#fff;font-weight:600;text-decoration:none;font-size:15px}}
.lnk{{display:inline-flex;align-items:center;min-height:44px;color:#1D4ED8;font-size:15px}}
.nav{{display:flex;justify-content:space-between;margin:6px 0}} .nav a{{min-height:44px;display:inline-flex;align-items:center;color:#1D4ED8}}
svg{{width:100%;height:auto;display:block}} svg .pin{{fill:#fff;font:700 14px Inter,Arial,sans-serif}}
svg .lab,svg .val{{fill:var(--ink);font:14px Inter,Arial,sans-serif}}
.chartwrap{{overflow-x:auto}} .chartwrap svg{{min-width:720px}}   /* the chart's 14 px labels never scale below 14 px: it scrolls instead */
.mapwrap{{overflow-x:auto}} .mapwrap svg{{min-width:720px}}   /* the schematic's 14 px pin letters likewise (Track C review, 12 Oct) */
.legend{{font-size:14px;color:var(--muted);margin:6px 0}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:14px;color:var(--muted);font-weight:600}} td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.flag{{color:var(--flag);font-weight:600}} tr.this td{{font-weight:700}}
dt{{font-weight:700;margin-top:8px}} dd{{margin:0}}
.report{{border:2px solid var(--ink);border-radius:8px;padding:12px 14px;margin:16px 0}}
.empty{{background:#FFFBEB;border-left:3px solid var(--amber);padding:10px 14px}}
footer{{margin:28px 0 12px;font-size:14px;color:var(--muted)}}
tr.nr td{{color:var(--muted)}} tr.nr td.n{{font-style:italic}}
.sw{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px;border:1px solid rgba(0,0,0,.08)}}
.cc-legend .lg{{display:inline-block;margin-right:12px;white-space:nowrap}}
svg .cl{{fill:var(--ink);font:14px Inter,Arial,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}} svg .cn{{font-weight:700}}
@media print{{
  @page{{size:A4;margin:14mm}}
  body{{font-size:11pt}} main{{max-width:none;padding:0}}
  .actions,.nav{{display:none}}
  h2{{break-after:avoid}} table,svg,.fig,.report{{break-inside:avoid}}
  .chartwrap svg,.mapwrap svg{{min-width:0}}   /* on paper the page width, not a phone's scroll */
  .figs{{grid-template-columns:repeat(4,1fr)}}
  a{{color:inherit;text-decoration:none}}
}}
</style></head>
<body><main>
{notice}
<div class="nav">{nav}</div>
<h1>{title}</h1>
<p class="sub">{tenant} · monthly bulletin · {as_at}</p>
<div class="actions"><a class="btn" href="{pdf_href}">Download the PDF</a><a class="lnk" href="/map/">Open the public map</a></div>
<p class="count">{counting_line}</p>
{empty}
<div class="figs" data-bulletin="headline">{head}</div>

<h2>The month's routes</h2>
<div class="mapwrap" data-bulletin="map">{svg_map}</div>
<p class="legend">Haul routes in the plan blue: thicker = more two-way movements. Schematic, not to scale; positions
indicative. {places}{controls_text}</p>

<h2>The busiest routes</h2>
<div class="tw"><table data-bulletin="busiest"><thead><tr><th>Route</th><th>Two-way a day</th><th>In the month</th>
<th>{last_head}</th><th>Planning flag</th></tr></thead><tbody>{busiest}</tbody></table></div>
<p class="muted">A planning flag is a cap the scheme has typed, in two-way movements a day; it is never a legal limit.
{flagged} of {n_routes} routes carry one. Every route is charted below.</p>
<p><b>Terms explained.</b> {two_way_sentence} {other_schemes}</p>

<h2>This month at a glance</h2>
<div class="tw"><table data-bulletin="glance"><thead><tr><th>Item</th><th>This month</th><th>Data</th></tr></thead>
<tbody>{glance}</tbody></table></div>
<p class="muted">Forecast: from the approved plan. Not reported: what a monitoring report fills from observed records
(counts, gate and camera records, operators' returns). A planning forecast has none, so the line is left empty, never estimated.</p>

<h2>Two-way movements a day by route</h2>
<div class="chartwrap" data-bulletin="chart">{svg_chart}</div>
<p class="legend">Bars: two-way movements a day, approved plan. Dashed red mark: the planning flag typed on the route.</p>

<h2>What is being moved</h2>
<div class="tw"><table><thead><tr><th>Discipline</th><th>Two-way a day</th><th>Vehicles</th><th>Tonnes a day</th></tr></thead>
<tbody>{moved}<tr class="this"><td>All routes</td><td class="n">{mt_a_day}</td><td class="n">{mt_vehicles}</td>
<td class="n">{mt_t_day}</td></tr></tbody></table></div>

<h2>Works affecting the roads in {month_long}</h2>
<div class="tw"><table data-bulletin="works"><thead><tr><th>Location</th><th>Works</th><th>When and who</th></tr></thead>
<tbody>{works}</tbody></table></div>
<ul>{checks}{others}</ul>

<h2>What changed since last month</h2>
<div class="tw"><table><thead><tr><th>Month</th><th>Two-way a day</th><th>Vehicles</th><th>CO₂e a day</th><th>Routes</th></tr></thead>
<tbody>{change}</tbody></table></div>
<p>{change_text}</p>
<p class="muted">Plan against plan: each month's approved plan as it stands today. No earlier issue of this bulletin is stored.</p>

{council}

<h2>Terms explained</h2>
<dl>{terms}</dl>

<h2>Caveats</h2>
<ul>{caveats}</ul>

<div class="report"><p><b>{rep_lorry}</b></p><p>{rep_hours}</p><p>{rep_formats}</p></div>

<footer>{notice} {foot}</footer>
</main></body></html>""".format(**v)
