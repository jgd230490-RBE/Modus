"""
route_map_export.py — the route map export (backlog item 2, 14 Oct 2026; replaces the per-route sheet, backlog §2).

WHAT IT IS
----------
The map as the person has filtered it — the routes chosen in the map's Route filtering, one month, one team or all —
drawn on the SERVER (basemap.py behind, the bulletin's route drawing on top), never a screenshot of the browser map.
Staff only (the user, 14 Oct: "STAFF ONLY").

14 Oct 2026, evening (the user: "the only map export to be just the map so it can be added into documents … add certain
scales as in the CLP template"): ONLY THE MAP, as one of the three plans the CLOCS outline CLP template asks for (§2.2
"Three plans at different scales", §4 "Vehicle routing and site access"):

    Regional plan   the routes in their wider setting        1:20,000 or smaller (the template: smaller than 1:15,000),
                                                              fitted to the routes unless a scale is asked for
    Local plan      around one site or gate                  1:2,000, 1:2,500 or 1:3,000
    Site plan       around one site or gate                  1:500 or 1:1,000

A PDF (A4 landscape, the map filling the page: exactly at its stated scale when printed at 100 %) or a PNG of the same map
for a Word document (the scale bar stays right when the picture is resized; the stated ratio does not). The legend, the
title, the scale and a north arrow are drawn INSIDE the map. The per-route table, the scheme's block and the National
Highways Carbon Tool rows of the first build are gone (the user, 14 Oct: "Yes, remove them"); the figures stay on screen
(the Routes page, the Carbon planner).

D11: an approved route = the route plus its Approved lines. Each route's colour comes from the month roll-up the public
map's bar and the bulletin use (bulletin.rollup_payloads over /api/public/month-kpis lines, which are Approved only),
filtered to the chosen routes and team BEFORE the roll-up, so the figures are those routes' own.

    S = sheet(month_index, route_ids=None, team=None, acc=None, origin=None, dest=None, discipline=None)
    plan(S, kind="regional", scale=None, at=None)      adds S["plan"]: the view at the stated scale, the places in frame
    export.build_route_map_pdf(S) / export.route_map_png(pdf)
"""
import datetime

#: the PDF page (A4 landscape, mm), the map's frame on it and the basemap image that fills the frame
PAGE_W_MM, PAGE_H_MM = 297.0, 210.0
MARGIN_MM = 6.0
FRAME_W_MM, FRAME_H_MM = PAGE_W_MM - 2 * MARGIN_MM, PAGE_H_MM - 2 * MARGIN_MM       # 285 × 198 mm
W_PX = 1280                                                                         # basemap.MAX_PX (× 2 for @2x)
H_PX = int(round(W_PX * FRAME_H_MM / FRAME_W_MM))
PANEL_W_MM = 66.0          # the panel inside the map, top right: title, scale, legend, sites (kept clear of the routes)
PAD_PX = 28

#: the CLOCS outline CLP template's three plans (§2.2, §4). Scales are the N of 1:N, largest scale first.
PLANS = {
    "regional": {"name": "Regional plan", "centred": False, "default": None,
                 "scales": (20000, 25000, 50000, 75000, 100000, 125000, 150000, 200000, 250000, 500000, 1000000),
                 "what": "The routes in their wider setting: the strategic roads they use."},
    "local": {"name": "Local plan", "centred": True, "default": 2500, "scales": (2000, 2500, 3000),
              "what": "The last part of each route to the site: the local roads it uses."},
    "site": {"name": "Site plan", "centred": True, "default": 1000, "scales": (500, 1000),
             "what": "The site's own access: a base to draw gates, swept paths and marshal points on."},
}


class PlanError(ValueError):
    """A plan that cannot be drawn as asked (unknown plan, a scale it does not offer, a place not on these routes)."""


def scale_words(n):
    return f"1:{int(n):,}"


def _team_text(v):
    try:
        import taxonomy
        return taxonomy.team_text(v)
    except Exception:
        return v


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


def sheet(month_index, route_ids=None, team=None, acc=None, now=None, origin=None, dest=None, discipline=None):
    """
    The routes the filters let through for one month, each with its colour, letters and places, and the places at their
    ends. The filters are the public map's Route filtering, applied as the map applies them (map/index.html applyFilters
    and calculateKPIs): origin, destination and team from the ROUTE, discipline from the LINE; `route_ids` narrows
    further (the Routes page sends the routes it lists). Reads only.
    """
    import access
    import bulletin
    import bulletin_doc
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
    geo = bulletin_doc._geometries(ids, month_index=mi)     # 29 Oct 2026 (task 0c, PR B): the month's lines

    # letter pins, the busiest route's ends first (the bulletin's rule); `end` says which end of a route it is
    places, letter_of = [], {}
    for r in rows:
        g = geo.get(r["route_id"])
        for name, loc_id, at, end in ((r.get("origin"), g[1] if g else None, g[0][0] if g else None, "origin"),
                                      (r.get("dest"), g[2] if g else None, g[0][-1] if g else None, "dest")):
            key = loc_id or name
            if key and key not in letter_of:
                letter_of[key] = bulletin_doc._letters(len(places))
                places.append({"letter": letter_of[key], "name": name or "", "at": at, "end": end})

    def letters(r):
        g = geo.get(r["route_id"])
        o = letter_of.get((g[1] if g else None) or r.get("origin"), "")
        d = letter_of.get((g[2] if g else None) or r.get("dest"), "")
        return f"{o} → {d}" if o and d else ""

    n0 = bulletin_doc.n0
    out_rows = []
    for r in rows:
        a_day = r.get("two_way_a_day") or 0
        out_rows.append({
            "route_id": r["route_id"], "letters": letters(r),
            "places": f"{r.get('origin') or ''} → {r.get('dest') or ''}".strip(" →"),
            "a_day": a_day, "a_day_text": n0(a_day),
            "loads_text": n0(r.get("movements_in_month")),
            "tonnes_text": (n0(r.get("tonnes")) + " t") if r.get("tonnes") is not None else "—",
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
    return {
        "title": f"Route map · {month_long}",
        "tenant": export._tenant_name() or "Wayscope",
        "demo_notice": notice, "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "month_long": month_long, "team_words": team_words,
        "filter_words": " · ".join([f"{len(out_rows)} route{'s' if len(out_rows) != 1 else ''}", team_words, *narrowed,
                                    month_long, "approved lines only"]),
        "as_at": f"Approved plan as at {(now or datetime.date.today()):%d %b %Y}".replace(" 0", " "),
        "working_days": wd,
        "rows": out_rows, "map_routes": map_routes, "map_sections": [], "places": places, "controls": [],
        "volume_legend": bulletin_doc.volume_legend(), "map_legend_title": "Two-way movements a day",
        "not_drawn": [r for r in (R.get("routes_not_drawn") or {}).get("routes") or []],
        "empty": not out_rows,
    }


def centre_choices(S):
    """The places a local or site plan can be centred on: the ends of the chosen routes that have a stored road route,
    the sites (route destinations) first, then by letter. Names only (never an id)."""
    ps = [p for p in S["places"] if p.get("at")]
    return [p["name"] for p in sorted(ps, key=lambda p: (p.get("end") != "dest", p["letter"]))]


def plan(S, kind="regional", scale=None, at=None, community=True, collisions=False):
    """
    Adds S["plan"]: which plan, its stated scale, the basemap view drawn exactly at that scale (FRAME_W_MM wide), the
    place it is centred on, and the places inside the frame (the panel lists those). Raises PlanError on a plan, scale or
    place it does not offer. 14 Oct 2026: `community` (on unless the card's box leaves it out) adds the community
    considerations in the frame (community_in_frame), which the PDF draws and lists. 16 Oct 2026 (CLOCS v5 C1):
    `collisions` (off unless the card's box adds it) adds the collision history in the frame (collisions_in_frame).
    """
    import basemap
    import bulletin_doc
    kind = (kind or "regional").strip().lower()
    if kind not in PLANS:
        raise PlanError(f"no such plan: choose {', '.join(PLANS)}")
    spec = PLANS[kind]
    if scale is not None:
        try:
            scale = int(str(scale).replace(",", "").split(":")[-1])
        except ValueError:
            raise PlanError("the scale is a number, such as 2500 for 1:2,500")
        if scale not in spec["scales"]:
            raise PlanError(f"the {spec['name'].lower()} is drawn at " + ", ".join(scale_words(n) for n in spec["scales"]))
    reserve = int(round((PANEL_W_MM + 4) / FRAME_W_MM * W_PX))
    P = {"kind": kind, "name": spec["name"], "what": spec["what"], "frame_w_mm": FRAME_W_MM, "frame_h_mm": FRAME_H_MM,
         "view": None, "denom": None, "scale_words": None, "centre": None, "places": [], "fitted": False}
    choices = centre_choices(S)
    if spec["centred"]:
        if at:
            hit = [p for p in S["places"] if p.get("at") and p["name"].strip().lower() == str(at).strip().lower()]
            if not hit:
                raise PlanError(f"{at} is not at the end of a route on this map")
            centre = hit[0]
        else:
            # none asked for: the busiest route's site end (destination), else the first place drawn
            centre = next((p for p in S["places"] if p.get("at") and p["name"] == (choices[0] if choices else None)), None)
        if centre:
            n = scale or spec["default"]
            lon, lat = centre["at"]
            v = basemap.view_centred(lon, lat, basemap.zoom_for_scale(n, lat, FRAME_W_MM, W_PX), W_PX, H_PX, reserve)
            P.update(view=v, denom=n, centre=centre["name"])
    else:
        pts = bulletin_doc.map_points(S)
        if pts:
            if scale:
                n, v = basemap.view_to_scale(pts, (scale,), FRAME_W_MM, W_PX, H_PX, PAD_PX, reserve)
            else:
                n, v = basemap.view_to_scale(pts, spec["scales"], FRAME_W_MM, W_PX, H_PX, PAD_PX, reserve)
                P["fitted"] = True
            P.update(view=v, denom=n)
    if P["view"]:
        v = P["view"]
        P["scale_words"] = scale_words(P["denom"])
        P["true_denom"] = basemap.scale_denominator(v, FRAME_W_MM)
        inside = []
        for p in S["places"]:
            if p.get("at"):
                x, y = basemap.project(v, *p["at"])
                if 0 <= x <= v["w"] and 0 <= y <= v["h"]:
                    inside.append(p)
        P["places"] = inside
    P["centre_choices"] = choices
    P["community"] = community_in_frame(P["view"], omit=PLAN_OMITS.get(kind, ())) if (community and P["view"]) else None
    P["community_asked"] = bool(community)
    P["collisions"] = collisions_in_frame(P["view"], kind) if (collisions and P["view"]) else None
    P["collisions_asked"] = bool(collisions)
    S["plan"] = P
    return S


# 16 Oct 2026 (CLOCS v5 C1): the regional plan draws the killed-or-seriously-injured collisions only (slight ones crowd
# a 1:20,000 map the way bus stops do); the local and site plans draw all three. The panel says so.
COLLISION_KSI_ONLY = ("regional",)


def collisions_in_frame(v, kind):
    """The stored collisions inside the plan's frame (the KSI only on the regional plan), with the words its panel
    prints. None when nothing has been fetched. 16 Oct 2026: only those along the routes the plan draws (or round a
    site): a plan draws no alternatives, so a collision near a stored alternative only is left out (collisions.along)."""
    import basemap
    import collisions as cl
    st = cl.status()
    if not st["fetched_at"]:
        return {"records": [], "period": "", "credit": "", "ksi_only": False, "fetched": False}
    ksi_only = kind in COLLISION_KSI_ONLY
    keep = []
    for c in cl.records():
        if (ksi_only and not c["ksi"]) or c["along"] != "route":
            continue
        x, y = basemap.project(v, c["lon"], c["lat"])
        if 0 <= x <= v["w"] and 0 <= y <= v["h"]:
            keep.append(c)
    return {"records": keep, "period": st["period"], "credit": cl.credit_line(), "ksi_only": ksi_only, "fetched": True,
            "severities": sorted({c["severity"] for c in keep})}


# 15 Oct 2026 (the user: "leave bus stops off the regional plan"): kinds a plan leaves out of the community considerations.
# At a regional plan's scale (1:20,000 and smaller) the bus stops crowd every town into a smear; the local and site plans
# keep them. The panel says where they are, so the leaving out is never silent.
PLAN_OMITS = {"regional": ("bus_stops",)}


def community_in_frame(v, omit=()):
    """14 Oct 2026 — the community considerations layer on a plan: the stored features with a vertex inside the frame,
    or an outline that covers the frame's centre (a residential area larger than a site plan), the kinds among them in
    the legend's order, and the credit line for the sources those features came from. None when nothing is stored."""
    import basemap
    import community
    from community_sources import polygons_of, in_polygons
    feats = community.features()
    if not feats:
        return None
    w, h = v["w"], v["h"]
    keep = []
    for f in feats:
        g = f["geometry"]
        t = g.get("type")
        if t == "Point":
            cs = [g["coordinates"]]
        elif t == "LineString":
            cs = g["coordinates"]
        else:
            cs = [c for poly in polygons_of(g) for ring in poly for c in ring]
        hit = False
        for c in cs:
            x, y = basemap.project(v, c[0], c[1])
            if 0 <= x <= w and 0 <= y <= h:
                hit = True
                break
        if not hit and t in ("Polygon", "MultiPolygon"):
            lon, lat = basemap.unproject(v, w / 2, h / 2)
            hit = in_polygons(lon, lat, polygons_of(g))
        if hit:
            keep.append(f)
    left_out = [k["label"] for k in community.KINDS if k["key"] in omit and any(f["properties"]["kind"] == k["key"] for f in keep)]
    keep = [f for f in keep if f["properties"]["kind"] not in omit]
    kinds = [dict(k) for k in community.KINDS if any(f["properties"]["kind"] == k["key"] for f in keep)]
    sources = sorted({f["properties"].get("source_key") for f in keep if f["properties"].get("source_key")})
    return {"features": keep, "kinds": kinds, "credit": community.credit_line(sources) if keep else "", "left_out": left_out}
