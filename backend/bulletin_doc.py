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
the local controls, seasonal windows, planning flags exceeded (no stockpiles since 14 Oct: a site matter), and
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
import math
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
# NARROWED 14 Oct 2026 (the publishing check): "[a typed field this scheme has not set yet]" read as an error
PLACEHOLDER = "not set yet"
# 14 Oct 2026 (the publishing check): the ONE definition, printed once under the figures (it was printed seven times)
DEFINITION = ("One two-way movement = one lorry there and back, counted once. Planned figures from the approved plan: "
              "no lorry was counted.")
CHART_MAX_ROUTES = 24
ZONE_WORDS = {"closure": "closure", "weight_limit": "weight limit", "works": "works area", "other": "local control"}
# 13 Oct 2026: the council layer's carbon colouring, the public map's own (map/index.html AREA_RAMP_CARBON,
# AREA_NONE, AREA_STOPS.carbon and the hatch of areaHatchImage) — test_bulletin.py reads the map and holds them equal
COUNCIL_RAMP = ("#EE9150", "#E8590C", "#B8470A", "#7C2D06")
COUNCIL_NONE = "#E7E5E4"
# NARROWED 13 Oct 2026 (W12): the DEFAULT bands only (config.COUNCIL_BREAKS_DEFAULT, the map's AREA_STOPS). A scheme
# types its own on Config -> Map and bulletin; council_stops() reads them, as the map does.
COUNCIL_STOPS = (50, 100, 200)               # t CO2e in the month, fixed, so a colour means the same tonnes every month
# 13 Oct 2026 (W13): the council layer's MOVEMENTS colouring, the public map's own (map/index.html AREA_RAMP, the plan
# blue in four steps); held equal by test_bulletin.py
COUNCIL_RAMP_MOVEMENTS = ("#89A3DC", "#6A8BD2", "#4A72C9", "#2D4E95")
# 13 Oct 2026 (W11): the page-1 route map takes the public map's Volume heat-map colours: VOLUME_STOPS (two-way
# movements a day, fixed in every month and every scheme) and its five-step blue (map/index.html CARBON_RAMP, which
# volumeColor() paints with), and ONE line width, so a width never carries a figure (the map's rule since PR #39).
# The map's casing colour (CONFIG.COLORS.forecastCasing) sits under each line so the light end reads on white paper.
VOLUME_STOPS = (10, 25, 50, 100)
VOLUME_RAMP = ("#94BBF9", "#5A96F6", "#2071F3", "#0B55CB", "#073888")
ROUTE_CASING = "#1F2024"
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


def _coords_of(geometry):
    """A stored run's polyline as [(lon, lat), ...]: a list of pairs, or a GeoJSON LineString."""
    g = geometry.get("coordinates") if isinstance(geometry, dict) else geometry
    out = []
    for c in g or []:
        try:
            out.append((float(c[0]), float(c[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def map_note(n_sections):
    """NARROWED 14 Oct 2026 (the publishing check: legends too wordy): one short sentence. It said the map's Volume legend
    foot word for word ("Each route is painted by its own figure; N shared sections … summed.")."""
    return ("Where routes share a road, its colour shows their total." if n_sections else
            "Each route is coloured by its own two-way movements a day.")


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


def council_stops(measure="carbon"):
    """The scheme's three bands for a measure ('movements' or 'carbon'), the map's: config.council_breaks()."""
    import config
    try:
        return tuple(config.council_breaks()[measure])
    except Exception:
        return tuple(config.COUNCIL_BREAKS_DEFAULT[measure])


def council_class(v, unclipped=False, stops=None):
    """The map's step for a district's figure: 'nofig' (hatched), 'none' (grey) or 0-3 (the ramp). `stops` defaults
    to COUNCIL_STOPS (the default carbon bands); the sections pass the scheme's."""
    if v is None or (unclipped and not v > 0):
        return "nofig"
    if v < 0.01:
        return "none"
    return sum(1 for s in (stops or COUNCIL_STOPS) if v >= s)


def council_fill(cls, ramp=COUNCIL_RAMP):
    return COUNCIL_NONE if cls == "none" else (HATCH_PAPER if cls == "nofig" else ramp[cls])


def volume_class(a_day):
    """The map's volumeColor() step for a route's two-way movements a day: 0-4 on VOLUME_STOPS (a Mapbox step:
    at or over a stop takes the next colour)."""
    return sum(1 for s in VOLUME_STOPS if (a_day or 0) >= s)


def step_ranges(stops, unit=""):
    """The map's stepRanges(s, unit), word for word: 'under 10', '10 to 25', ... '100 and over'."""
    s = stops
    return [f"under {s[0]}{unit}", f"{s[0]} to {s[1]}{unit}", f"{s[1]} to {s[2]}{unit}", f"{s[2]} to {s[3]}{unit}",
            f"{s[3]}{unit} and over"]


def volume_legend():
    return [{"label": t, "fill": VOLUME_RAMP[i]} for i, t in enumerate(step_ranges(VOLUME_STOPS))]


def _t(v):
    """t CO2e as the map's district label prints it: whole tonnes from 10 t, one decimal below."""
    return f"{v:,.0f} t" if v >= 10 else f"{v:,.1f} t"


def _share(v, whole):
    """A district's share of the scheme's carbon: whole per cent, "under 1%" for a sliver, "—" with no figure."""
    if v is None or not whole or not v > 0:
        return "—"
    pc = 100 * v / whole
    return "under 1%" if pc < 0.5 else f"{pc:.0f}%"


def _council_legend(stops=None, ramp=COUNCIL_RAMP, unit=" t", none_label="no approved route"):
    s = stops or COUNCIL_STOPS
    return [{"label": f"under {s[0]}{unit}", "fill": ramp[0], "hatch": False},
            {"label": f"{s[0]} to {s[1] - 1}{unit}", "fill": ramp[1], "hatch": False},
            {"label": f"{s[1]} to {s[2] - 1}{unit}", "fill": ramp[2], "hatch": False},
            {"label": f"{s[2]}{unit} and over", "fill": ramp[3], "hatch": False},
            {"label": none_label, "fill": COUNCIL_NONE, "hatch": False},
            {"label": "no figure (never a zero)", "fill": HATCH_PAPER, "hatch": True}]


def _council_carbon(mi, wd, month_long, A=None):
    """
    The districts' t CO2e in the month (areas.area_load, the map's figures), formatted; None when the
    tenant has no council districts (then the bulletin prints nothing about them). `A` is the month's
    area_load when the caller has read it already (sheet() reads it once for both council sections), or
    the exception that read raised.
    """
    import areas
    stored = areas.stored_areas()
    if not any(a["tier"] == "district" for a in stored):
        return None
    try:
        A = A if A is not None else areas.area_load(mi, working_days=wd, geometry=True)
        if isinstance(A, Exception):
            raise A
    except Exception as e:                       # the section stays, and says why there is no figure
        return {"error": f"The council figures could not be read for {month_long} ({type(e).__name__}).",
                "title": f"Carbon by council in {month_long}", "districts": []}
    stops = tuple((A.get("stops") or {}).get("carbon") or council_stops("carbon"))
    unclipped = bool(A.get("routes_not_clipped"))
    tot = A.get("totals") or {}
    scheme = tot.get("co2_t")
    districts = []
    for a in A.get("areas") or []:
        if a["tier"] != "district":
            continue
        v = a.get("co2_t")
        cls = council_class(v, unclipped, stops)
        if cls == "nofig":
            text = "no figure yet" if (v is not None and unclipped) else "no figure"
        elif cls == "none":
            text = ("no approved route" if not (a.get("routes") or a.get("return_only_routes") or a.get("edge_routes"))
                    else "under 0.1 t")
        else:
            text = _t(v)
        import comparisons
        las = comparisons.la_share(a["area_id"], v) if (v or 0) > 0 else None
        districts.append({"area_id": a["area_id"], "name": a["name"], "co2_t": v, "cls": cls, "text": text,
                          "fill": council_fill(cls), "highway_authority": a.get("highway_authority") or "",
                          "share": _share(v, scheme),
                          # 13 Oct 2026 (D40): about this share of a month of the district's road transport (DESNZ 2024)
                          "la_share": ((comparisons.about(las["pct_words"]) + ("" if las["has_motorway"] else " †"))
                                       if las else ("—" if not (v or 0) > 0 else "no government figure")),
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
        tally = (f"The {n} districts carry {_t(d_sum)} of the scheme's {_t(scheme)} CO2e"
                 + (f"; {_t(out)} is driven outside them." if out >= 0.05 else ": all of it."))
    county_lines = []
    for a in A.get("areas") or []:
        if a["tier"] == "county" and a.get("co2_t") is not None:
            county_lines.append(f"{a.get('highway_authority') or a['name']} roads: {_t(a['co2_t'])} CO2e.")
    notes = [x for x in (A.get("notes") or []) if any(k in x for k in ("CO2e", "clipped", "carbon"))]
    sources = []
    for a in stored:
        if a["tier"] == "district" and a.get("source") and a["source"] not in sources:
            sources.append(a["source"])
    return {
        "error": None,
        "title": f"Carbon by council in {month_long}",
        "lede": f"Lorry carbon on each district's roads in {month_long}, split by the distance driven there.",
        "districts": districts,
        "stops": list(stops),
        "legend": _council_legend(stops),
        "tally": tally,
        # REVERSED 13 Oct 2026 (D40, the user: the council share "for scale"): it said the figures are "not comparable with
        # the DESNZ local authority greenhouse gas statistics"; the share column now sets them beside those figures, for scale
        # NARROWED 14 Oct 2026 (the publishing check): the method in two sentences; the detail is in the sources
        "basis": ("Each route's carbon is split by the km driven in each district, so the districts add up to the "
                  "scheme's figure. The last column sets each district beside a month (one twelfth of the year) of its "
                  "road transport CO2e in the government's local statistics (DESNZ, 2024: every vehicle), for scale only, "
                  "on all roads where the district has a motorway."),
        "la_source": "Road transport: DESNZ, UK local authority and regional greenhouse gas emissions statistics, 2005 to "
                     "2024, Table 1.1 (published 25 June 2026). Contains public sector information licensed under the "
                     "Open Government Licence v3.0.",
        "county_lines": county_lines, "notes": notes,
        "attribution": list(A.get("attribution") or []),
        "sources": [f"Boundaries: {x}, generalised to 200 m." for x in sources],
        "stamp": (A.get("carbon") or {}).get("stamp") or "",
    }


def _mv(v):
    """Two-way movements a day as a page people read prints them: whole movements; "under 1" for a sliver."""
    if v is None:
        return "—"
    return "under 1" if 0 < v < 0.5 else n0(v)


def _change_words(now, was):
    """This month against last, in words, on the WHOLE figures the table prints (so the words match the columns)."""
    a, b = round(now or 0), round(was or 0)
    if not (was or 0) > 0 and (now or 0) > 0:
        return "new this month"
    if (was or 0) > 0 and not (now or 0) > 0:
        return f"none this month (was {_mv(was)})"
    if a == b:
        return "no change" if (now or 0) > 0 else "—"
    return f"up {a - b:,}" if a > b else f"down {b - a:,}"


def _council_movements(mi, wd, month_long, A=None, prev=None, prev_long=None, distance_unit="km"):
    """
    13 Oct 2026 (W13): two-way movements a day, lorry-miles (or lorry-km) and the change since last month for each
    local authority district, from the SAME areas.area_load the public map's By council layer reads (per area the
    approved loads of every route whose laden leg enters it ÷ the working days; the lorry distance on the roads
    inside, laden and empty). `A` / `prev` are this month's and last month's reads (or the exception a read raised);
    None when the tenant has no districts. The districts add up to MORE than the scheme (a route counts in every
    district its laden leg enters): the footnote says so in areas.DOUBLE_COUNT's words, and no total row is printed.
    """
    import areas
    import config
    stored = areas.stored_areas()
    if not any(a["tier"] == "district" for a in stored):
        return None
    title = f"Movements by council in {month_long}"
    try:
        A = A if A is not None else areas.area_load(mi, working_days=wd, geometry=False)
        if isinstance(A, Exception):
            raise A
    except Exception as e:
        return {"error": f"The council figures could not be read for {month_long} ({type(e).__name__}).",
                "title": title, "districts": []}
    if isinstance(prev, Exception):
        prev = None
    stops = tuple((A.get("stops") or {}).get("movements") or council_stops("movements"))
    unclipped = bool(A.get("routes_not_clipped"))
    mi_words = "miles" if distance_unit == "mi" else "km"
    per = config.KM_PER_MILE if distance_unit == "mi" else 1.0
    was = {a["area_id"]: a for a in ((prev or {}).get("areas") or [])}
    districts = []
    for a in A.get("areas") or []:
        if a["tier"] != "district":
            continue
        v = a.get("movements_per_day") or 0.0
        cls = council_class(v, unclipped, stops)
        if cls == "nofig":
            text = "no figure yet"
        elif cls == "none":
            text = "empties only" if a.get("return_only_routes") else "no approved laden route"
        else:
            text = _mv(v)
        if mi <= 1:
            change = "no earlier month"
        elif prev is None:
            change = "—"
        elif a["area_id"] not in was:
            change = "—"
        else:
            change = _change_words(v, was[a["area_id"]].get("movements_per_day"))
        dist = (a.get("lorry_km") or 0.0) / per
        districts.append({"area_id": a["area_id"], "name": a["name"], "a_day": v, "text": text, "cls": cls,
                          "fill": council_fill(cls, COUNCIL_RAMP_MOVEMENTS), "routes": a.get("routes_count") or 0,
                          "distance": dist, "distance_text": (n0(dist) if dist >= 0.5 else ("under 1" if dist > 0 else "0")),
                          "change": change})
    districts.sort(key=lambda d: (-(d["a_day"] or 0), d["name"]))
    tot = A.get("totals") or {}
    county_lines = [f"{a.get('highway_authority') or a['name']} roads: {_mv(a.get('movements_per_day'))} two-way "
                    "movements a day." for a in A.get("areas") or [] if a["tier"] == "county"]
    return {
        "error": None, "title": title,
        "lede": f"Two-way movements a day on each district's roads in {month_long}.",
        "districts": districts, "stops": list(stops),
        "legend": _council_legend(stops, COUNCIL_RAMP_MOVEMENTS, "", "no approved laden route"),
        "distance_head": f"Lorry-{mi_words} in the month",
        "change_head": f"Change since {prev_long}" if prev_long else "Change since last month",
        "scheme_line": f"Whole scheme: {_mv(tot.get('movements_per_day'))} two-way movements a day.",
        "footnote": (areas.DOUBLE_COUNT + f" Lorry-{mi_words}: loaded and empty, on the district's roads."),
        "county_lines": county_lines,
        "notes": [x for x in (A.get("notes") or []) if "clipped" in x or "no stored road route" in x],
    }


# 13 Oct 2026 (W14, D40, D44): the "Is it a lot?" panel. Status words carry their colour AND their word (never colour
# alone): within an allowance in the dark green, over it in the dark amber, both 4.5:1 or better on white.
STATUS_OK, STATUS_OVER = "#047857", "#B45309"
LOT_SOURCE_OWN = "This bulletin's own figures: the approved plan and the DESNZ 2026 lorry factors."


def _scheme_acc(acc):
    """The access the panel's target figures are read with: the whole scheme (D37), whoever opened the bulletin."""
    return dict(acc or {}, ipt=None)


def _target_row(mi, month_long, acc):
    """Row 3: the month's ALL-IN carbon against its share of the scheme's target (D44: target × plan_month ÷ plan_total)."""
    import carbon_target
    label = "Against the target"
    src = ("The scheme's carbon target on the Carbon planner. A month's allowance is the target × the month's share of "
           "the approved plan, so the allowance follows the shape of the plan.")
    try:
        t = carbon_target.get()
    except Exception as e:
        return {"label": label, "text": f"The carbon target could not be read ({type(e).__name__}).", "status": None, "source": src}
    if not t:
        return {"label": label, "text": "No carbon target set yet.", "status": None, "source": src}
    try:
        st = carbon_target.status(_scheme_acc(acc), t)
    except Exception as e:
        return {"label": label, "text": f"The carbon target could not be worked out ({type(e).__name__}).", "status": None,
                "source": src}
    month = next((m for m in st.get("by_month") or [] if m["month_index"] == mi), None)
    total, target_t = st.get("approved_t"), st.get("target_t")
    if month is None or not total or target_t is None:
        return {"label": label, "text": f"No all-in figure for {month_long} in the approved plan.", "status": None, "source": src}
    allowance = target_t * month["approved_t"] / total
    use_dec = month.get("with_decisions_t") is not None and not st.get("invalid")
    fig = month["with_decisions_t"] if use_dec else month["approved_t"]
    gap = fig - allowance
    within = gap <= carbon_target.ON_TARGET_TOL_T + 1e-9
    status = "Within the allowance" if within else "Over the allowance"
    how = "with the agreed decisions" if use_dec else "as forecast (the agreed decisions no longer fit the plan)"
    text = (f"{_t(fig)} CO2e all-in {how}, against an allowance of {_t(allowance)}"
            + ("." if within else f": {_t(gap)} over.")
            + " All-in includes making the material, so it is larger than the haul figures.")
    return {"label": label, "text": text, "status": status, "status_ok": within, "source": src,
            "allowance_t": allowance, "month_t": fig}


def _lot(mi, month_long, prev_long, R, prev, H, council, acc, demo):
    """
    The six rows of "Is <n> t CO2e a lot?" (D40: all six, each with its source and year; the outside ones say "about").
    None when the month has no haul carbon figure (the panel would compare nothing).
    """
    import comparisons
    c = (R.get("carbon") or {}).get("co2_t_in_month")
    if c is None:
        return None
    F = comparisons.factors()
    rows = [{"label": "Against the plan", "text": NOT_REPORTED + ": nothing was counted, so there is no measured carbon "
             "to compare with the plan.", "status": None, "source": "—"}]
    # 2. last month, recomputed (never read off an old PDF)
    if mi <= 1:
        t2 = "No earlier month in the programme."
    else:
        last = ((prev or {}).get("carbon") or {}).get("co2_t_in_month")
        if (prev or {}).get("empty"):
            t2 = f"There was no approved haul in {prev_long}."
        elif last is None:
            t2 = f"No haul carbon figure for {prev_long}."
        elif not last > 0:
            t2 = f"There was no approved haul in {prev_long}."
        else:
            ch = 100.0 * (c - last) / last
            t2 = (f"About the same as {prev_long} ({_t(c)} against {_t(last)})." if abs(ch) < 0.5 else
                  f"{abs(ch):.0f}% {'more' if ch > 0 else 'less'} than {prev_long} ({_t(c)} against {_t(last)}).")
    rows.append({"label": "Against last month", "text": t2, "status": None, "source": LOT_SOURCE_OWN})
    rows.append(_target_row(mi, month_long, acc))
    # 4. the council's own figures: the district that carries the most haul carbon, in its own government figures
    la_src = (f"{F['la_road_transport']['source']}; {comparisons.la_table()['attribution']} A month is one twelfth of the "
              "year. For scale only: those figures count every vehicle, estimated by a national model; these are this "
              "scheme's planned lorries on 2026 factors.")
    ds = [d for d in ((council or {}).get("districts") or []) if (d.get("co2_t") or 0) > 0]
    if not council:
        t4 = "No council areas are loaded for this scheme."
    elif council.get("error"):
        t4 = council["error"]
    elif not ds:
        t4 = f"No district carries haul carbon in {month_long}."
    else:
        top = ds[0]
        sh = comparisons.la_share(top["area_id"], top["co2_t"])
        t4 = (f"No government figure for {top['name']} (code {top['area_id']})." if sh is None else
              f"In {top['name']}, {_t(top['co2_t'])} is {comparisons.about(sh['pct_words'])} of a month of all road "
              f"transport CO2e in the district (2024; {'all roads' if sh['has_motorway'] else 'A and minor roads'}).")
    # a source only beside a figure it is the source of (no council areas, no figure: no source line)
    rows.append({"label": "The council's figures", "text": t4, "status": None,
                 "source": la_src if t4.startswith("In ") else "—"})
    # 5. cars
    eq = comparisons.car_equivalents(c)
    rows.append({"label": "In everyday terms", "text": f"{eq['words'][0].upper() + eq['words'][1:]} (exhaust only, as for "
                 "the lorries).", "status": None,
                 "source": (f"{F['car_kg_co2e_per_km']['source']}: {F['car_kg_co2e_per_km']['value']} kg CO2e per km; "
                            f"{F['car_miles_a_year']['source']}: {F['car_miles_a_year']['value']:,} miles a car in "
                            f"{F['car_miles_a_year']['year']}. A range of {F['car_range_pct']['value']}% either side: the "
                            "factor is a UK average for an unknown fuel and the mileage is England's.")})
    # 6. per tonne, per movement
    tn, mv = H.get("tonnes"), H.get("movements_in_month")
    per = []
    if tn:
        per.append(f"{1000.0 * c / tn:,.1f} kg CO2e per tonne moved")
    if mv:
        per.append(f"{1000.0 * c / mv:,.0f} kg per two-way movement")
    rows.append({"label": "Per tonne, per movement", "text": (" and ".join(per) + ".") if per else
                 "No tonnes or movements to divide by this month.", "status": None, "source": LOT_SOURCE_OWN})
    return {
        "title": f"Is {_t(c)} of CO2e a lot?",
        "co2_t": c,
        "lede": f"{month_long}'s haul carbon beside six comparisons.",
        "rows": rows,
        "demo_note": ("Fictional demo scheme: the plan, the target and the tonnes are invented; the government figures they "
                      "are set beside are real." if demo else None),
        "checked": "Factors checked 13 October 2026.",
    }


# 13 Oct 2026 (W15, D43): the newsletter's page 1 and the one-page leaflet share these words, from the view model only.
BRAND_TITLE = "Lorry movements bulletin"
DEMO_MAP_TAG = "Demo - fictional scheme"        # D41: on each map itself as well as in the page bar (15 Oct 2026, the user:
                                                # "DEMO - FICTIONAL SCHEME"; was "Fictional demo scheme")
NEWSLETTER_URL_PLACEHOLDER = f"[link {PLACEHOLDER}]"


def _brief(month_long, prev_long, H, prev, routes_view, works, controls, never_all, council_mv, lot):
    """
    "This month in brief": up to five plain sentences a resident can read alone (the newsletter's page 1, the
    leaflet). Each is built from a figure the bulletin prints elsewhere; nothing new is worked out here.
    """
    # REVERSED 14 Oct 2026 (the publishing check): shorter, plain, no "laden legs"; the road-works warning lives once,
    # under the works table (it was printed four times)
    out = []
    now = n0(H.get("two_way_a_day"))
    if routes_view:
        b = routes_view[0]
        out.append(f"Busiest route: {b['label']}, {b['a_day_text']} two-way movements a day"
                   + (f", above its planning flag of {b['cap']:,}." if b["over_flag"] else "."))
    if prev is not None:
        ph = (prev.get("headline") or {})
        if prev.get("empty") or ph.get("two_way_a_day") is None:
            out.append(f"{now} two-way movements a day; no approved lorries in {prev_long}.")
        else:
            was = ph.get("two_way_a_day") or 0
            nowv = H.get("two_way_a_day") or 0
            side = "up from" if round(nowv) > round(was) else ("down from" if round(nowv) < round(was) else "the same as")
            out.append(f"{now} two-way movements a day, {side} {n0(was)} in {prev_long}.")
    n = len(works) + len(controls)
    out.append(f"{n} road work{'s' if n != 1 else ''}, closure{'s' if n != 1 else ''} or local limit{'s' if n != 1 else ''} "
               f"on or near the routes." if n else "No road works, closures or local limits are listed.")
    ds = [d for d in ((council_mv or {}).get("districts") or []) if (d.get("a_day") or 0) > 0]
    if ds:
        out.append(f"{ds[0]['name']} district sees the most: {ds[0]['text']} two-way movements a day.")
    if lot:
        import comparisons
        eq = comparisons.car_equivalents(lot["co2_t"])
        out.append(f"Haul carbon: {_t(lot['co2_t'])} CO2e, {eq['words'] if eq else 'no comparison'}.")
    return out


def _sources(lot, council, council_mv, page, carbon, wd=None):
    """
    14 Oct 2026 (the publishing check): every source and method note ONCE, numbered, at the end; each "Is it a lot?" row
    gets the number of its source (`ref`). They were printed beside every row and repeated across pages.
    """
    out = []

    def add(text):
        if text and text not in out:
            out.append(text)
        return out.index(text) + 1 if text else None
    las = (council or {}).get("la_source") if council and not council.get("error") else None
    for r in (lot or {}).get("rows") or []:
        src = r.get("source")
        if las and src and "local authority and regional greenhouse gas" in src:
            src = las                       # the same DESNZ table the council section cites: ONE entry
        r["ref"] = add(src) if src and src != "—" else None
    add("Carbon: " + (carbon.get("rule") or "routed km × the vehicle's kg CO2e per km, approved plan only").replace("CO₂e", "CO2e")
        + " " + (carbon.get("stamp") or "") + ".")
    if council and not council.get("error"):
        add(council.get("la_source"))
        add(" ".join(council.get("sources") or []) + " " + " ".join(council.get("attribution") or []))
    if council_mv and not council_mv.get("error"):
        add("Council movements: a route counts in a district when at least 200 m of its loaded leg is inside; a route "
            "inside by less adds its distance there, not its movements.")
    add(page["terms"]["other_schemes"])
    # the counting rule (the map's kpi-note sentence, verbatim) and D28, once: they were printed on page 1 and in a long
    # "Forecast" term; the map's own credit is in its caption, only when a basemap is drawn
    add(f"Counting: {COUNTING_LINE} {two_way_sentence(wd)} The month's loads are summed as typed (fractional), not "
        "rounded per line; the total is then shown to the nearest whole movement. Working days are the scheme's settings.")
    return out


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
        rw = (f"{len(controls)} local limit{'s' if len(controls) != 1 else ''}",
              "Not checked against published works")
    elif never:
        rw = (listed, f"{len(never)} route{'s' if len(never) != 1 else ''} not checked")
    else:
        rw = (listed, f"Checked {_iso_short(checked_at)}" if checked_at else "Checked")
    rows = [
        ("Two-way lorry movements a day", n0(H.get("two_way_a_day")), fc),
        ("Lorry movements in the month", n0(H.get("movements_in_month")), fc),
        ("Routes in use", n0(H.get("routes_in_use")) if H.get("routes_in_use") is not None else "—", fc),
        ("Routes planned above their planning flag",
         (f"{len(over)} of {len(flagged)}" if flagged else "no planning flag set"), "Forecast against the scheme's flags"),
        ("Haul carbon in the month",
         (_t(c["co2_t_in_month"]) + " CO2e") if c.get("co2_t_in_month") is not None else "—",
         "Forecast: DESNZ 2026 factors"),
        # NARROWED 14 Oct 2026 (the publishing check): the data words fit one line
        ("Road works, closures and local limits", rw[0], rw[1]),
        ("Lorries counted on the roads or at the site gates", NOT_REPORTED, "A plan: no lorry was counted"),
        ("Lorries kept to the approved routes and working hours", NOT_REPORTED, "Needs observed records"),
        ("Vehicle and operator standards (FORS, CLOCS, Euro VI, Direct Vision Standard)", NOT_REPORTED,
         "Not in this bulletin"),
        ("Collisions and near misses", NOT_REPORTED, "Not in this bulletin"),
        ("Enquiries and complaints", NOT_REPORTED, "Not in this bulletin"),
    ]
    return [{"item": a, "figure": b, "data": d, "not_reported": b == NOT_REPORTED} for a, b, d in rows]


def flag_short(cap, over):
    """14 Oct 2026 (the publishing check): the route table's flag cell — "—" with none, "20 · above" / "30" with one
    ("no planning cap typed" wrapped to three lines in every row)."""
    if cap is None:
        return "—"
    return f"{cap:,} · above" if over else f"{cap:,}"


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
                # 14 Oct 2026 (the publishing check): the route's map colour, so the table's bar matches its line
                "color": VOLUME_RAMP[volume_class(r.get("two_way_a_day"))],
                "flag_short": flag_short(r.get("cap"), bool(r.get("cap") is not None
                                                            and (r.get("two_way_a_day") or 0) > r["cap"])),
                "over_flag": bool(r.get("cap") is not None and (r.get("two_way_a_day") or 0) > r["cap"])}

    routes_view = [route_view(r) for r in rows]
    # REVERSED 13 Oct 2026 (W11): no width by volume (it was 1.5-6.5 px by the month's busiest route, so the same width
    # meant different volumes in different months); each route takes the public map's Volume colour for its two-way
    # movements a day, at one width. Drawn quietest first, so the busiest sit on top.
    map_routes = sorted(({"route_id": r["route_id"], "coords": geo[r["route_id"]][0], "a_day": r["a_day"] or 0,
                          "step": volume_class(r["a_day"]), "color": VOLUME_RAMP[volume_class(r["a_day"])]}
                         for r in routes_view if r["route_id"] in geo), key=lambda r: (r["a_day"], r["route_id"]))
    controls = _controls(span_from, span_to)
    # 13 Oct 2026 (W11, the map's Volume heat map held equal): the shared road sections — a stretch two or more routes
    # use — drawn over the routes, each in the Volume colour of the routes using it, SUMMED (road_sections.road_load,
    # the same read as /api/public/road-load), so a shared trunk road shows as the busiest stretch, as on the map.
    map_sections, sections_note = [], None
    try:
        import road_sections
        for run in (road_sections.road_load(mi, working_days=wd).get("runs") or []):
            cs = _coords_of(run.get("geometry"))
            if len(cs) >= 2:
                v = float(run.get("movements_per_day") or 0.0)
                map_sections.append({"coords": cs, "a_day": v, "step": volume_class(v),
                                     "color": VOLUME_RAMP[volume_class(v)], "routes": len(run.get("routes") or [])})
        map_sections.sort(key=lambda x: x["a_day"])
    except Exception as e:
        sections_note = (f"The shared road sections could not be read ({type(e).__name__}): each route is painted by its "
                         "own figure only.")

    headline = [
        {"key": "two_way_a_day", "value": n0(H.get("two_way_a_day")),
         "label": "two-way movements a day"},
        {"key": "movements_in_month", "value": n0(H.get("movements_in_month")),
         "label": f"movements in the month ({wd_text(wd)} working days)"},
        {"key": "routes_in_use", "value": n0(H.get("routes_in_use")) if H.get("routes_in_use") is not None else "—",
         "label": "routes in use"},
        {"key": "tonnes", "value": (n0(H.get("tonnes")) + " t") if H.get("tonnes") is not None else "—",
         "label": "material moved"},
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
        # 14 Oct 2026: each route ONCE (a route's hits on both legs and every vehicle were all counted), and no ids
        _n = len(set(w["routes"]))
        w["routes_text"] = f"near {_n} of this month's route{'s' if _n != 1 else ''}"
    never = rs.get("never_checked_routes") or []
    in_month = sorted({*(R.get("routes_in_use") or []), *never})
    checks = []
    if rs.get("status") == bulletin.NEVER_CHECKED:
        checks.append("Not checked against published road works: other works may affect these roads.")
    elif never:
        checks.append(f"{len(never)} of this month's routes not checked against published road works: other works "
                      "may affect them.")
    elif rs.get("checked_at"):
        checks.append(f"Checked against {prov.get('name') or 'the road authority'} on {_iso_short(rs['checked_at'])}.")
    if rs.get("past_month_note"):
        checks.append(rs["past_month_note"])
    others = []
    # 14 Oct 2026 (the user took the recommendation): no stockpile line — a stockpile over capacity is a site matter,
    # not for a public bulletin (bulletin.public_conditions leaves it out of the page's conditions)
    for s in C.get("seasonal") or []:
        others.append({"kind": "Seasonal window", "text": f"{s.get('name')}: {s.get('message') or ''} "
                       f"Applies to {len(s.get('routes') or [])} route(s) this month.".strip()})
    _label = {r["route_id"]: r["label"] for r in routes_view}
    for e in (C.get("route_caps") or {}).get("exceeded") or []:
        # 14 Oct 2026: the route by its places, never its id
        others.append({"kind": "Planning flag", "text": f"{_label.get(e['route_id'], 'One route')}: "
                       f"{n0(e['two_way_a_day'])} a day planned, above its planning flag of {e['cap']:,} a day."})

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
                 f"lorries needed {n0(pv.get('fleet'))} → {n0((R.get('vehicles') or {}).get('fleet'))}",
                 f"CO2e a day {n1((prev.get('carbon') or {}).get('co2_t_a_day'))} → "
                 f"{n1((R.get('carbon') or {}).get('co2_t_a_day'))} t"]
        if was == now_r:
            parts.append(f"the same {len(now_r)} route{'s' if len(now_r) != 1 else ''}")
        else:
            added, gone = sorted(now_r - was), sorted(was - now_r)
            parts.append(f"routes {len(was)} → {len(now_r)}" + (f" ({len(added)} new)" if added else "")
                         + (f" ({len(gone)} finished)" if gone else ""))
        change_text = f"Since {prev_long}: " + "; ".join(parts) + "."

    glance = _glance(H, R, routes_view, works, controls, rs.get("status"), never, rs.get("checked_at"), month_long)
    # 13 Oct 2026 (W13): the month's areas read ONCE for both council sections (and last month's, figures only)
    import areas
    import config
    A = A_prev = None
    if any(a["tier"] == "district" for a in areas.stored_areas()):
        try:
            A = areas.area_load(mi, working_days=wd, geometry=True)
        except Exception as e:
            A = e
        if mi > 1:
            try:
                A_prev = areas.area_load(mi - 1, working_days=wd, geometry=False)
            except Exception as e:
                A_prev = e
    council = _council_carbon(mi, wd, month_long, A=A)
    lot = _lot(mi, month_long, prev_long, R, prev, H, council, acc, bool(page.get("demo_notice")))
    du = (config.tenant_settings().get("distance_unit") or "km")
    council_mv = _council_movements(mi, wd, month_long, A=A, prev=A_prev, prev_long=prev_long, distance_unit=du)
    brief = _brief(month_long, prev_long, H, prev, routes_view, works, controls,
                   rs.get("status") == bulletin.NEVER_CHECKED, council_mv, lot)
    demo_tag = DEMO_MAP_TAG if page.get("demo_notice") else None
    if council and demo_tag:
        council["demo_tag"] = demo_tag

    carbon = R.get("carbon") or {}
    veh = R.get("vehicles") or {}
    # REVERSED 14 Oct 2026 (the publishing check): five long terms that repeated the definition, the vehicle rule's
    # "baked cycle" and the carbon stamp are four one-liners; the method and the stamp are in the sources
    terms = [
        ("Two-way movement", "one lorry there and back (out loaded, back empty), counted once. "
         + page["terms"]["other_schemes"].split(":")[0] + "."),
        ("Forecast", f"the month's approved plan spread over its {wd_text(wd)} working days: planned, not counted."),
        ("Lorries needed", "how many lorries the plan needs on a working day, from each route's round-trip time."),
        ("Planning flag", "a daily limit the scheme set itself on a route. It flags, never blocks, and is not a legal limit."),
    ]
    caveats = ["Planned, not counted: this is a forecast from the approved plan, not a monitoring report.",
               "The tables are per route; on a road several routes share, the lorries are their sum (the map colours it, "
               "with no figure printed).",
               "Other traffic, including other firms' lorries, uses these roads too; the figures are this scheme's lorries only."]
    nd = R.get("routes_not_drawn") or {}
    if nd.get("lines"):
        _many = nd["lines"] != 1
        caveats.append(f"{nd['lines']} plan line{'s' if _many else ''} on route{'s' if len(nd.get('routes') or []) != 1 else ''} "
                       f"not yet mapped {'are' if _many else 'is'} left out of these figures (not counted as zero).")
    if veh.get("excludes_unbaked_lines"):
        caveats.append("Lorries needed leaves out plan lines whose lorry has no mapped route.")
    if (R.get("payload_fallback") or {}).get("note"):
        caveats.append(R["payload_fallback"]["note"])
    if carbon.get("error"):
        caveats.append(carbon["error"])

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
        "glance": glance, "council": council, "council_mv": council_mv, "lot": lot,
        # 13 Oct 2026 (W15, D43): the newsletter's masthead and page 1, the leaflet, the D41 map tag
        "brand_title": f"{BRAND_TITLE} · {month_long}",
        "issued": f"Issued {_date_long(today)}",
        "lede": (f"The lorries {page.get('tenant_name') or 'this scheme'} plans for {month_long}: how many, where they go, "
                 "and their carbon."),
        "definition": DEFINITION,
        "map_title": f"Planned lorry routes, {month_long}",
        "brief": brief, "map_demo_tag": demo_tag,
        "sources": _sources(lot, council, council_mv, page, carbon, wd),
        "newsletter_where": NEWSLETTER_URL_PLACEHOLDER,
        "leaflet_pdf_href": f"/api/bulletin/leaflet.pdf?month={mi}",
        "leaflet_href": f"/bulletin/leaflet/?month={mi}",
        "volume_legend": volume_legend(),
        "map_sections": map_sections, "sections_note": sections_note, "map_note": map_note(len(map_sections)),
        "map_legend_title": "Two-way movements a day",
        "change_rows": change_rows, "change_text": change_text,
        "terms": terms, "caveats": [c for c in caveats if c],
        # 12 Oct 2026 (Track C review): the tenant's typed concern_email (the map's "Report a concern"
        # address) when set; the placeholder only while it is not
        "report": {"lorry": f"Report a lorry off route: the date, time, place, direction and registration, to "
                            + (f"{page['concern_email']}." if page.get("concern_email")
                               else f"[contact {PLACEHOLDER}]."),
                   "hours": f"Working hours: [{PLACEHOLDER}].",
                   "formats": f"Large print and other formats: [{PLACEHOLDER}]."},
        "carbon_stamp": carbon.get("stamp"),
        "foot": "Planned figures, not counts · prepared with Wayscope",
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


MARKER_CLEAR = 11.0                      # PDF pt between marker centres before a control steps off a pin


def control_spot(x, y, taken, clear=MARKER_CLEAR, step=13.0):
    """
    14 Oct 2026 (the publishing check): a control's square covered a site's letter. Where it goes: at (x, y) if nothing
    taken is within `clear`, else the first clear spot `step` away (up, up-right, right ... round the clock; "up" is +y,
    so a y-down caller passes a negative step), else one step up. The caller draws a leader back to (x, y).
    """
    if all(math.hypot(x - a, y - b) >= clear for a, b in taken):
        return x, y
    for k in range(8):
        ang = math.pi / 2 - k * math.pi / 4
        cx, cy = round(x + abs(step) * math.cos(ang), 2), round(y + step * math.sin(ang), 2)
        if all(math.hypot(cx - a, cy - b) >= clear for a, b in taken):
            return cx, cy
    return x, y + step


LABEL_SPOTS = sorted(((dx, dy) for dx in range(-90, 91, 10) for dy in range(-72, 73, 9)),
                     key=lambda t: (t[0] ** 2 + t[1] ** 2, abs(t[0])))


def place_labels(entries, y_lo, y_hi, bounds=None, k=1.0):
    """
    14 Oct 2026 (the publishing check: small districts' labels sat on each other). entries: [(ax, ay, width)] in priority
    order; each label box spans width across and (y + y_lo, y + y_hi) up and down. Each goes at its own point or the
    nearest spot (LABEL_SPOTS × k) where it overlaps no label already placed and stays inside bounds (x0, y0, x1, y1);
    else at its own point. Returns [(x, y)].
    """
    placed, out = [], []
    for ax, ay, w in entries:
        pick = None
        for dx, dy in LABEL_SPOTS:
            x, y = ax + dx * k, ay + dy * k
            box = (x - w / 2, y + y_lo, x + w / 2, y + y_hi)
            if bounds and (box[0] < bounds[0] or box[2] > bounds[2] or box[1] < bounds[1] or box[3] > bounds[3]):
                continue
            if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                pick = (x, y, box)
                break
        if pick is None:
            pick = (ax, ay, (ax - w / 2, ay + y_lo, ax + w / 2, ay + y_hi))
        placed.append(pick[2])
        out.append(pick[:2])
    return out


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


def _map_view(points, w, h, pad):
    """
    14 Oct 2026 (the user: "no map behind the route"): (P, image, view) for an SVG of w × h — P maps (lon, lat) to SVG
    units (y down). With a basemap (basemap.py, @1x so the page stays light) the image is the PNG inline and P is
    Mapbox's own projection; without one, the schematic projector and no image. (None, "", None) with nothing to draw.
    """
    v = png = None
    try:
        import basemap
        v = basemap.view(points, w, h, pad)
        png = basemap.fetch(v, retina=False) if v else None
    except Exception:
        png = None
    if png:
        import base64
        img = (f'<image href="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" x="0" y="0" width="{w}" '
               f'height="{h}" preserveAspectRatio="none"/>')
        return (lambda lon, lat: basemap.project(v, lon, lat)), img, v
    proj = projector(points, w, h, pad)
    if proj is None:
        return None, "", None
    return (lambda lon, lat: (lambda x, y: (x, h - y))(*proj(lon, lat))), "", None


def _svg_scale(v, w, h):
    """A scale bar, bottom right, over a basemap only (the schematic is not to scale)."""
    if not v:
        return ""
    import basemap
    km, px = basemap.scale(v, 110)
    x1, y = w - 10, h - 24
    return (f'<g class="scale"><rect x="{x1 - px - 6:.1f}" y="{y - 16}" width="{px + 12:.1f}" height="24" fill="#fff" '
            f'fill-opacity="0.85"/><path d="M{x1 - px:.1f},{y - 4} v4 H{x1} v-4" fill="none" stroke="{INK}" stroke-width="1.5"/>'
            f'<text x="{x1 - px / 2:.1f}" y="{y - 6}" text-anchor="middle" class="sc">{km:g} km</text></g>')


def _svg_map(S, w=720, h=420):
    P, img, v = _map_view(map_points(S), w, h, 28)
    if P is None:
        return '<p class="muted">No route with a stored road route to draw this month.</p>'
    label = "Map of this month's planned lorry routes" if img else "Schematic of this month's planned lorry routes"
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{label}" class="map">',
           img or f'<rect x="0" y="0" width="{w}" height="{h}" fill="#FAFAF9" stroke="#D6D3D1"/>']
    # W11: the map's casing under every route first, then each route in its Volume colour, one width, quietest first
    lines = [(r, " ".join(f"{x:.1f},{y:.1f}" for x, y in (P(*c) for c in r["coords"]))) for r in S["map_routes"]]
    for r, pts in lines:
        out.append(f'<polyline points="{pts}" fill="none" stroke="{ROUTE_CASING}" stroke-width="{ROUTE_CASING_W}" '
                   'stroke-opacity="0.9" stroke-linecap="round" stroke-linejoin="round"/>')
    for r, pts in lines:
        out.append(f'<polyline points="{pts}" fill="none" stroke="{r["color"]}" stroke-width="{ROUTE_LINE_W}" '
                   f'stroke-linecap="round" stroke-linejoin="round"><title>{_e(r["route_id"])}: '
                   f'{_e(n0(r["a_day"]))} two-way movements a day</title></polyline>')
    # the shared sections on top, each by its routes summed (the map's road-load layer), quietest first
    for sct in S.get("map_sections") or []:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (P(*c) for c in sct["coords"]))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{ROUTE_CASING}" stroke-width="{ROUTE_CASING_W}" '
                   'stroke-opacity="0.9" stroke-linecap="round" stroke-linejoin="round" class="sec"/>'
                   f'<polyline points="{pts}" fill="none" stroke="{sct["color"]}" stroke-width="{ROUTE_LINE_W}" '
                   f'stroke-linecap="round" stroke-linejoin="round" class="sec"><title>shared by {sct["routes"]} routes: '
                   f'{_e(n0(sct["a_day"]))} two-way movements a day</title></polyline>')
    pins = []
    for p in S["places"]:
        if not p.get("at") or not p["letter"]:
            continue
        x, y = P(*p["at"])
        pins.append((x, y))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{INK}" stroke="#fff" stroke-width="1.5"/>'
                   f'<text x="{x:.1f}" y="{y + 4.5:.1f}" text-anchor="middle" class="pin">{_e(p["letter"])}</text>')
    # 14 Oct 2026: a control steps off a site's pin, with a leader back (control_spot, shared with the PDF; y down)
    for z in S["controls"]:
        if not z.get("at"):
            continue
        ax, ay = P(*z["at"])
        x, y = control_spot(ax, ay, pins, clear=24, step=-26)
        if (x, y) != (ax, ay):
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{CLOSURE_AMBER}" stroke-width="1.5"/>'
                       f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="2.5" fill="{CLOSURE_AMBER}"/>')
        pins.append((x, y))
        out.append(f'<rect x="{x - 9:.1f}" y="{y - 9:.1f}" width="18" height="18" rx="3" fill="{CLOSURE_AMBER}" stroke="#fff" '
                   f'stroke-width="1.5"/><text x="{x:.1f}" y="{y + 4.5:.1f}" text-anchor="middle" class="pin">{z["n"]}</text>')
    out.append(_svg_scale(v, w, h))
    out.append(_svg_tag(S.get("map_demo_tag")))
    out.append("</svg>")
    return "".join(out)


def _svg_tag(text):
    """D41 (13 Oct 2026): "Fictional demo scheme" on the map itself, top left: white with a red edge, red words."""
    if not text:
        return ""
    w = 12 + 8.6 * len(text)
    return (f'<g class="map-tag"><rect x="6" y="6" width="{w:.0f}" height="24" rx="3" fill="#FFFFFF" stroke="#B91C1C" '
            f'stroke-width="1.5"/><text x="12" y="23" class="tagt">{_e(text)}</text></g>')


# the map's CARBON_LINE_WIDTH / CARBON_CASING_WIDTH until 16 Oct 2026, in SVG units; the map's are 6 / 8.5 since then
# (D115: two flow lanes fit inside the line), and this map draws no lanes, so it keeps 5 / 7.5
ROUTE_LINE_W, ROUTE_CASING_W = 5, 7.5


def _volume_legend_html(S):
    sw = "".join(f'<span class="lg"><span class="sw" style="background:{g["fill"]}"></span>{_e(g["label"])}</span>'
                 for g in S["volume_legend"])
    return (f'<p class="legend cc-legend" data-bulletin="map-legend"><b>{_e(S["map_legend_title"])}:</b> {sw}</p>'
            f'<p class="legend">{_e(S["map_note"])}' + (f' {_e(S["sections_note"])}' if S.get("sections_note") else "")
            + f' <span class="credit">{"© Mapbox © OpenStreetMap" if S.get("_map_img") else "Schematic, not to scale."}</span></p>')


def _key_html(S):
    """14 Oct 2026 (the publishing check): the map's key in columns — sites by letter, road works and limits by number."""
    sites = "".join(f'<li><b>{_e(p["letter"])}</b> {_e(p["name"])}</li>' for p in S["places"] if p["letter"])
    lims = "".join(f'<li><b class="amber">{z["n"]}</b> {_e(z["name"])}</li>' for z in S["controls"])
    if not sites and not lims:
        return ""
    return ('<div class="key" data-bulletin="key">'
            f'<div><h3>Sites</h3><ul class="kl two">{sites or "<li>none</li>"}</ul></div>'
            f'<div><h3>Road works and limits</h3><ul class="kl">{lims or "<li>none this month</li>"}</ul></div></div>')


def _band_html(S, kind):
    """W15 (13 Oct 2026): the ink band with the logo inlined as the SVG master (vector, the brand gradient kept) and the
    brand title, the orange rule under it."""
    import brand_pdf
    return (f'<header class="band"><div class="band-in">{brand_pdf.inline_svg("logo-header-on-dark", 30)}'
            f'<div class="band-t">{_e(S["brand_title"])}</div><div class="band-s">{_e(S["tenant"])} · {_e(kind)} · '
            f'{_e(S["as_at"])} · {_e(S["issued"])}</div></div></header><div class="band-rule"></div>')


def _mark_html():
    import brand_pdf
    return brand_pdf.inline_svg("mark", 16, "Wayscope mark")


def _brief_html(S):
    # RENAMED 14 Oct 2026 (the publishing check): "This month in brief" is "Key points"
    if not S.get("brief"):
        return ""
    return ('<h2>Key points</h2><ul class="brief" data-bulletin="brief">'
            + "".join(f"<li>{_e(_co2(b))}</li>" for b in S["brief"]) + "</ul>")


def _map_block_html(S):
    """The map's title, the map, its legend and note, the key — the newsletter page and the leaflet page alike."""
    svg = _svg_map(S)
    S["_map_img"] = "<image " in svg
    return (f'<h2 class="mt">{_e(S["map_title"])}</h2><div class="mapwrap" data-bulletin="map">{svg}</div>'
            + _volume_legend_html(S) + _key_html(S))


def leaflet_html(S):
    """
    13 Oct 2026 (D43): the one-page leaflet as an HTML page, from the same view model as the newsletter. REVERSED 14 Oct
    2026 (the publishing check): a heading a resident reads first, the four figures, the definition once, the map over a
    basemap with its key, the key points, the report strip, where to read the newsletter.
    """
    e = _e
    head = "".join(f'<div class="fig"><div class="v">{e(f["value"])}</div><div class="l">{e(f["label"])}</div></div>'
                   for f in S["headline"])
    notice = (f'<div class="notice">{e(S["demo_notice"])}</div>' if S["demo_notice"] else "")
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{e(S['brand_title'])} · leaflet · {e(S['tenant'])}</title>"
            "<link rel=\"icon\" href=\"/favicon.svg\" type=\"image/svg+xml\">"
            "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
            "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap\" rel=\"stylesheet\">"
            f"<style>{LEAFLET_CSS}</style></head><body data-bulletin=\"leaflet\">"
            + _band_html(S, "leaflet") + "<main>" + notice
            + f'<h1>Lorries on your roads in {e(S["month_long"])}</h1><div class="figs">{head}</div>'
            + f'<p class="def">{e(S["definition"])}</p>'
            + _map_block_html(S)
            + _brief_html(S)
            + f'<div class="report"><p><b>{e(S["report"]["lorry"])}</b></p><p>{e(S["report"]["hours"])}</p>'
              f'<p>{e(S["report"]["formats"])}</p></div>'
            + f'<p>Every route, the councils and the carbon are in the monthly newsletter: <a href="/bulletin/?month='
              f'{S["month_index"]}">open it here</a> (staff) · {e(S["newsletter_where"])}</p>'
            + f'<p class="actions"><a class="btn" href="{e(S["leaflet_pdf_href"])}">Download the leaflet (PDF)</a></p>'
            + f'<p class="muted">{e(_co2(S.get("carbon_stamp") or ""))}</p>'
            + f'<footer>{notice} {_mark_html()} {e(S["foot"])} · wayscope.co.uk</footer></main></body></html>')


# 13 Oct 2026 (D43): the leaflet page's own stylesheet — the newsletter page's rules it needs, nothing below 14 px
LEAFLET_CSS = (":root{color-scheme:light} *{box-sizing:border-box} body{margin:0;background:#fff;color:#1F2024;"
               "font:16px/1.5 Inter,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
               " main{max-width:880px;margin:0 auto;padding:16px} .lede{font-size:17px}"
               " .band{background:#1F2024;color:#fff} .band-in{max-width:880px;margin:0 auto;padding:14px 16px 12px}"
               " .band-in .brand-logo{display:block;height:30px;width:auto;margin-bottom:6px}"
               " .band-t{font-size:23px;font-weight:700;line-height:1.25} .band-s{font-size:14px;color:#C9CED6}"
               " .band-rule{height:4px;background:linear-gradient(90deg,#FF8312,#FFA10A)}"
               " .notice{display:inline-block;background:#F1F5F9;color:#B91C1C;border:1px solid #DC2626;border-bottom-width:3px;"
               "border-radius:6px;padding:3px 12px;font-size:14px;font-weight:700}"
               " .notice::before{content:'DEMO';content:'DEMO' / '';display:inline-block;margin-right:8px;padding:0 6px;"
               "border-radius:3px;background:#B91C1C;color:#FFFFFF;letter-spacing:.08em}"
               " .figs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}"
               " @media (min-width:720px){.figs{grid-template-columns:repeat(4,minmax(0,1fr))}}"
               " .fig{border:1px solid #E7E5E4;border-radius:8px;padding:10px 12px}"
               " .fig .v{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums} .fig .l{font-size:14px;color:#57534E}"
               " svg{width:100%;height:auto;display:block} svg .pin{fill:#fff;font:700 14px Inter,Arial,sans-serif}"
               " svg .tagt{fill:#B91C1C;font:700 14px Inter,Arial,sans-serif}"
               " .mapwrap{overflow-x:auto} .mapwrap svg{min-width:720px} .legend{font-size:14px;color:#57534E;margin:6px 0}"
               " .sw{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px;"
               "border:1px solid rgba(0,0,0,.08)} .cc-legend .lg{display:inline-block;margin-right:12px;white-space:nowrap}"
               " h2{font-size:19px;margin:24px 0 8px;padding-top:12px;border-top:2px solid #1F2024} p,li{font-size:15px}"
               " .report{background:#FFF4E8;border-left:5px solid #FF8312;border-radius:4px;padding:10px 14px;margin:16px 0}"
               " .report p{margin:4px 0} h1{font-size:28px;line-height:1.2;margin:16px 0 8px}"
               " .def{font-size:14px;color:#57534E;margin:4px 0 0} h2.mt{border-top:0;padding-top:0}"
               " .credit{white-space:nowrap} svg .sc{fill:#1F2024;font:14px Inter,Arial,sans-serif}"
               " .key{display:grid;grid-template-columns:1fr;gap:4px 24px;margin:10px 0}"
               " @media (min-width:720px){.key{grid-template-columns:2fr 1fr}}"
               " .key h3{font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:#57534E;margin:0 0 4px;"
               "border-bottom:1px solid #E7E5E4;padding-bottom:2px} .kl{list-style:none;margin:0;padding:0}"
               " .kl li{font-size:15px;margin:2px 0} .kl.two{columns:2;column-gap:24px} .amber{color:#D97706}"
               " .btn{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:6px;background:#C2410C;"
               "color:#fff;font-weight:600;text-decoration:none;font-size:15px} .muted{color:#57534E;font-size:14px}"
               " footer{margin:28px 0 12px;font-size:14px;color:#57534E} footer .brand-logo{height:16px;width:auto;vertical-align:-3px}"
               " @media print{@page{size:A4;margin:12mm} .actions,.btn{display:none} .mapwrap svg{min-width:0}"
               " .band,.band-rule{-webkit-print-color-adjust:exact;print-color-adjust:exact}}")


def _sw_style(fill, hatch):
    return (f"repeating-linear-gradient(45deg,{HATCH_INK} 0 2px,{HATCH_PAPER} 2px 6px)" if hatch else fill)


def _svg_council(C, w=720, h=560):
    """The districts in the orange ramp over the basemap at the public map's 0.8 (no basemap: on their own), a white
    2.5 px border between them, one label each, placed apart (place_labels, shared with the PDF)."""
    P, img, v = _map_view(council_points(C), w, h, 16)
    if P is None:
        return '<p class="muted">No district boundary to draw.</p>'
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Haul carbon by local authority district, t CO2e in the month" class="map">',
           f'<defs><pattern id="cc-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           f'<rect width="8" height="8" fill="{HATCH_PAPER}"/><rect width="2" height="8" fill="{HATCH_INK}"/></pattern></defs>', img]
    op = ' fill-opacity="0.8"' if img else ""
    for d in C["districts"]:
        path = " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (P(*p) for p in ring)) + " Z" for ring in d["rings"])
        fill = "url(#cc-hatch)" if d["cls"] == "nofig" else d["fill"]
        out.append(f'<path d="{path}" fill="{fill}"{op} fill-rule="evenodd" stroke="#FFFFFF" stroke-width="2.5" stroke-linejoin="round">'
                   f'<title>{_e(d["name"])}: {_e(_co2(d["text"]))}</title></path>')
    ds = sorted((d for d in C["districts"] if d.get("label_at")), key=lambda d: -(d.get("co2_t") or d.get("a_day") or 0))
    pts = [P(*d["label_at"]) for d in ds]
    ent = [(x, y, max(8.4 * len(d["name"]), 7.8 * len(_co2(d["text"]))) + 6) for d, (x, y) in zip(ds, pts)]
    for d, (x, y), (ax, ay) in zip(ds, place_labels(ent, -14, 20, (4, 36, w - 4, h - 26), k=1.4), pts):
        if abs(x - ax) > 14 or abs(y - ay) > 14:
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{x:.1f}" y2="{y + (20 if y < ay else -14):.1f}" stroke="{INK}" '
                       f'stroke-width="1"/><circle cx="{ax:.1f}" cy="{ay:.1f}" r="2" fill="{INK}"/>')
        out.append(f'<text x="{x:.1f}" y="{y - 2:.1f}" text-anchor="middle" class="cl"><tspan class="cn">{_e(d["name"])}</tspan>'
                   f'<tspan x="{x:.1f}" dy="17">{_e(_co2(d["text"]))}</tspan></text>')
    out.append(_svg_scale(v, w, h))
    out.append(_svg_tag(C.get("demo_tag")))
    out.append("</svg>")
    return "".join(out)


def _council_mv_html(M):
    """13 Oct 2026 (W13): movements by council, the table and its footnote; empty for a tenant with no districts."""
    if not M:
        return ""
    e = _e
    if M.get("error"):
        return f'<h2>{e(M["title"])}</h2><p class="empty">{e(M["error"])}</p>'
    sw = "".join(f'<span class="lg"><span class="sw" style="background:{_sw_style(g["fill"], g["hatch"])}"></span>{e(g["label"])}</span>'
                 for g in M["legend"])
    rows = "".join(f'<tr><td><span class="dn"><span class="sw" style="background:{_sw_style(d["fill"], d["cls"] == "nofig")}"></span>'
                   f'<span>{e(d["name"])}</span></span></td><td class="n">{e(d["text"])}</td><td class="n">{d["routes"]}</td>'
                   f'<td class="n">{e(d["distance_text"])}</td><td>{e(d["change"])}</td></tr>' for d in M["districts"])
    notes = "".join(f"<li>{e(x)}</li>" for x in M["county_lines"] + M["notes"])
    return (f'<h2>{e(M["title"])}</h2>'
            f'<p>{e(M["lede"])}</p>'
            f'<div class="tw"><table data-bulletin="council-movements"><thead><tr><th>District</th>'
            f'<th class="n">Two-way movements a day</th><th class="n">Routes</th><th class="n">{e(M["distance_head"])}</th><th>{e(M["change_head"])}</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="legend cc-legend">Two-way movements a day: {sw}</p>'
            f'<p>{e(M["scheme_line"])}</p>'
            + (f'<ul>{notes}</ul>' if notes else "")
            + f'<p class="muted" data-bulletin="double-count">{e(M["footnote"])}</p>')


def _lot_html(L):
    """13 Oct 2026 (W14): the "Is it a lot?" panel. REVERSED 14 Oct 2026 (the publishing check): each row's source is a
    numbered reference into Sources at the foot of the page (a "Source:" line under every row before)."""
    if not L:
        return ""
    e = _e
    rows = []
    for r in L["rows"]:
        st = ""
        if r.get("status"):
            st = (f' <b class="lot-st" style="color:{STATUS_OK if r.get("status_ok") else STATUS_OVER}">'
                  f'{"✓" if r.get("status_ok") else "▲"} {e(r["status"])}</b>')
        ref = f'<sup><a href="#src-{r["ref"]}">{r["ref"]}</a></sup>' if r.get("ref") else ""
        rows.append(f'<div class="lot-row"><div class="lot-l">{e(r["label"])}</div>'
                    f'<p>{e(_co2(r["text"]))}{ref}{st}</p></div>')
    return (f'<h2>{e(_co2(L["title"]))}</h2><div class="lot" data-bulletin="lot"><p>{e(L["lede"])}</p>{"".join(rows)}'
            + f'<p class="lot-src">' + (f'<span class="lot-demo">{e(L["demo_note"])}</span> ' if L.get("demo_note") else "")
            + f'{e(L["checked"])}</p></div>')


def _council_html(C):
    """The carbon-by-council section of the page; empty for a tenant with no council districts."""
    if not C:
        return ""
    e = _e
    if C.get("error"):
        return f'<h2>{e(C["title"])}</h2><p class="empty">{e(C["error"])}</p>'
    sw = "".join(f'<span class="lg"><span class="sw" style="background:{_sw_style(g["fill"], g["hatch"])}"></span>{e(g["label"])}</span>'
                 for g in C["legend"])
    rows = "".join(f'<tr><td><span class="dn"><span class="sw" style="background:{_sw_style(d["fill"], d["cls"] == "nofig")}"></span>'
                   f'<span>{e(d["name"])}</span></span></td><td>{e(d["highway_authority"])}</td><td class="n">{e(_co2(d["text"]))}</td>'
                   f'<td class="n">{e(d["share"])}</td><td class="n">{e(d.get("la_share") or "—")}</td></tr>' for d in C["districts"])
    notes = "".join(f"<li>{e(_co2(x))}</li>" for x in C["county_lines"] + C["notes"])
    return (f'<h2>{e(C["title"])}</h2>'
            f'<p>{e(_co2(C["lede"]))}</p>'
            f'<div class="mapwrap" data-bulletin="council-map">{_svg_council(C)}</div>'
            f'<p class="legend cc-legend">t CO₂e in the month: {sw}</p>'
            f'<div class="tw"><table data-bulletin="council"><thead><tr><th>District</th><th>Highway authority</th>'
            f'<th class="n">t CO₂e</th><th class="n">Share of scheme</th><th class="n">Of the district&#39;s road CO₂e, a month (2024)</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p>{e(_co2(C["tally"]))}</p>'
            + (f'<ul>{notes}</ul>' if notes else "")
            # NARROWED 14 Oct 2026 (the publishing check): the method in two sentences; the DESNZ source, the boundary
            # licence and the carbon stamp are in Sources at the foot (they were printed here and again on the PDF)
            + f'<p class="muted">{e(_co2(C["basis"]))}</p>')


def _routes_html(S):
    """14 Oct 2026 (the publishing check): every route in ONE table with its bar in its map colour, the planning flag a
    dashed red mark — it replaces "The busiest routes" table and the chart below it, which printed the same figures."""
    e = _e
    rows = S["routes"]
    if not rows:
        return '<p class="muted">No route with a stored road route carries approved lorries this month.</p>'
    vmax = max([r["a_day"] or 0 for r in rows] + [r["cap"] or 0 for r in rows] + [1])
    prev = (S["prev_long"] or "")[:3] or "Last month"
    out = []
    for r in rows:
        cap = (f'<span class="bc" style="left:{100 * r["cap"] / vmax:.1f}%" title="planning flag {r["cap"]:,} a day"></span>'
               if r["cap"] is not None else "")
        out.append(f'<tr><td class="lt">{e(r["letters"].replace(" → ", "–"))}</td><td>{e(r["label"])}</td>'
                   f'<td class="bar"><span class="bn">{e(r["a_day_text"])}</span><span class="bt"><span class="bf" '
                   f'style="width:{100 * (r["a_day"] or 0) / vmax:.1f}%;background:{r["color"]}"></span>{cap}</span></td>'
                   f'<td class="n">{e(r["in_month_text"])}</td><td class="n">{e(r["last_month_text"].replace(" a day", ""))}</td>'
                   f'<td class="n{" flag" if r["over_flag"] else ""}">{e(r["flag_short"])}</td></tr>')
    return ('<div class="tw"><table data-bulletin="routes"><thead><tr><th>Map</th><th>Route</th><th>Two-way movements a day</th>'
            f'<th class="n">In the month</th><th class="n">{e(prev)}</th><th class="n">Planning flag</th></tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table></div>'
            f'<p class="legend">Bars in each route\'s map colour. Planning flag: the scheme\'s own daily limit, the dashed red '
            f'mark ({S["flagged_routes"]} of {len(rows)} routes have one).</p>')


def _sources_html(S):
    """14 Oct 2026 (the publishing check): every source and method note once, numbered; the panel's rows link here."""
    items = "".join(f'<li id="src-{i}">{_e(_co2(t))}</li>' for i, t in enumerate(S.get("sources") or [], 1))
    return f'<h2>Sources</h2><ol class="src" data-bulletin="sources">{items}</ol>' if items else ""


def html(S):
    """
    The bulletin as an HTML page: one column on a phone, figures first, a print stylesheet. REVERSED 14 Oct 2026 (the
    publishing check) to the newsletter's order: the month in brief (figures, the definition once, the map over a
    basemap with its key, key points, report); routes and roads (every route with its bar, what is moved, road works
    and limits, what changed); councils; carbon and the small print (the panel with numbered references, the glance,
    terms, caveats, Sources).
    """
    e = _e
    head = "".join(f'<div class="fig"><div class="v">{e(f["value"])}</div><div class="l">{e(f["label"])}</div></div>'
                   for f in S["headline"])
    moved = "".join(f'<tr><td>{e(m["name"])}</td><td class="n">{e(m["a_day"])}</td><td class="n">{e(m["vehicles"])}</td>'
                    f'<td class="n">{e(m["t_day"])}</td></tr>' for m in S["moved"])
    mt = S["moved_total"]
    works = "".join(f'<tr><td>{e(w["where"])}</td><td>{e(w["line"])}<br><span class="muted">'
                    f'{e(w["routes_text"])}</span></td><td>{e(w["when"])}<br><span class="muted">{e(w["who"])}</span></td></tr>'
                    for w in S["works"])
    works += "".join(f'<tr><td><b class="amber">{z["n"]}</b> {e(z["name"])}</td><td>{e(z["kind"])}'
                     f'{(": " + e(z["note"])) if z["note"] else ""}</td><td>{e(z["when"])}<br><span class="muted">'
                     f'set by the scheme</span></td></tr>' for z in S["controls"])
    others = "".join(f'<li><b>{e(o["kind"])}.</b> {e(o["text"])}</li>' for o in S["others"])
    checks = "".join(f"<li>{e(c)}</li>" for c in S["checks"])
    change = "".join(f'<tr class="{"this" if c["this"] else ""}"><td>{e(c["label"])}</td><td class="n">{e(c["a_day"])}</td>'
                     f'<td class="n">{e(c["vehicles"])}</td><td class="n">{e(_co2(c["co2_day"]))}</td><td class="n">{e(c["routes"])}</td></tr>'
                     for c in S["change_rows"])
    terms = "".join(f"<dt>{e(_co2(k))}</dt><dd>{e(_co2(v[0].upper() + v[1:]))}</dd>" for k, v in S["terms"])
    caveats = "".join(f"<li>{e(_co2(c))}</li>" for c in S["caveats"])
    notice = (f'<div class="notice">{e(S["demo_notice"])}</div>' if S["demo_notice"] else "")
    mi = S["month_index"]
    nav = ((f'<a href="/bulletin/?month={mi - 1}">‹ {e(S["prev_long"])}</a>' if S["has_prev"] else "<span></span>")
           + (f'<a href="/bulletin/?month={mi + 1}">{e(S["next_long"])} ›</a>' if S["has_next"] else "<span></span>"))
    empty = (f'<p class="empty">{e(S["empty_note"])}</p>' if S["empty"] and S["empty_note"] else "")
    glance = "".join(f'<tr class="{"nr" if g["not_reported"] else ""}"><td>{e(_co2(g["item"]))}</td><td class="n">{e(_co2(g["figure"]))}</td>'
                     f'<td>{e(_co2(g["data"]))}</td></tr>' for g in S["glance"])
    M, C = S.get("council_mv"), S["council"]
    v = {
        "page_title": e(S["title"]) + " · " + e(S["tenant"]) + ((" · " + e(S["demo_notice"])) if S["demo_notice"] else ""),
        "title": e(S["title"]), "tenant": e(S["tenant"]), "as_at": e(S["as_at"]), "pdf_href": e(S["pdf_href"]),
        "lede": e(S["lede"]), "definition": e(S["definition"]),
        "mt_a_day": e(mt["a_day"]), "mt_vehicles": e(mt["vehicles"]), "mt_t_day": e(mt["t_day"]),
        "month_long": e(S["month_long"]),
        "works": works or '<tr><td colspan="3" class="muted">Nothing listed for this month.</td></tr>',
        "change_text": e(_co2(S["change_text"])),
        "rep_lorry": e(S["report"]["lorry"]), "rep_hours": e(S["report"]["hours"]), "rep_formats": e(S["report"]["formats"]),
        "foot": e(S["foot"]), "map_block": _map_block_html(S), "routes": _routes_html(S),
        "band": _band_html(S, "monthly newsletter"), "brief": _brief_html(S), "mark": _mark_html(),
        "leaflet_href": e(S["leaflet_href"]), "leaflet_pdf_href": e(S["leaflet_pdf_href"]),
        "glance": glance, "council": _council_html(C), "council_mv": _council_mv_html(M),
        "councils_kicker": '<p class="kick">03 Councils</p>' if (M or C) else "",
        "lot": _lot_html(S.get("lot")), "sources": _sources_html(S),
        "notice": notice, "nav": nav, "empty": empty, "head": head,
        "moved": moved, "checks": checks, "others": others, "change": change, "terms": terms, "caveats": caveats,
        "INK": INK, "MUTED": MUTED, "PLAN_BLUE": PLAN_BLUE, "PLAN_TINT": PLAN_TINT, "FLAG_RED": FLAG_RED,
        "CLOSURE_AMBER": CLOSURE_AMBER,
    }
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{color-scheme:light;--ink:{INK};--muted:{MUTED};--line:#E7E5E4;--plan:{PLAN_BLUE};--tint:{PLAN_TINT};--flag:{FLAG_RED};--amber:{CLOSURE_AMBER};--head:#F1F5F9}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:var(--ink);font:16px/1.5 Inter,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:880px;margin:0 auto;padding:16px}}
h1{{font-size:26px;line-height:1.2;margin:8px 0 4px}}
h2{{font-size:19px;margin:28px 0 8px}} h2.mt{{margin-top:20px}}
.kick{{font-size:14px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#C2410C;margin:40px 0 0;padding-top:12px;border-top:2px solid var(--ink)}}
.kick+h2{{margin-top:6px}}
p,li,dd,td,th{{font-size:15px}}
.muted{{color:var(--muted)}} .amber{{color:var(--amber)}}
.notice{{display:inline-block;background:#F1F5F9;color:#B91C1C;border:1px solid #DC2626;border-bottom-width:3px;border-radius:6px;padding:3px 12px;font-size:14px;font-weight:700}}
.notice::before{{content:'DEMO';content:'DEMO' / '';display:inline-block;margin-right:8px;padding:0 6px;border-radius:3px;background:#B91C1C;color:#FFFFFF;letter-spacing:.08em}}
.sub{{color:var(--muted);font-size:15px;margin:0}}
.lede{{font-size:18px;line-height:1.45;margin:10px 0}}
.def{{font-size:14px;color:var(--muted);margin:4px 0 0}}
.figs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0 4px}}
@media (min-width:720px){{.figs{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
.fig{{border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.fig .v{{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}} .fig .l{{font-size:14px;color:var(--muted)}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}}
.btn{{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:6px;background:#C2410C;color:#fff;font-weight:600;text-decoration:none;font-size:15px}}
.lnk{{display:inline-flex;align-items:center;min-height:44px;color:#1D4ED8;font-size:15px}}
.nav{{display:flex;justify-content:space-between;margin:6px 0}} .nav a{{min-height:44px;display:inline-flex;align-items:center;color:#1D4ED8}}
svg{{width:100%;height:auto;display:block}} svg .pin{{fill:#fff;font:700 14px Inter,Arial,sans-serif}} svg .sc{{fill:var(--ink);font:14px Inter,Arial,sans-serif}}
.mapwrap{{overflow-x:auto;border:1px solid var(--line)}} .mapwrap svg{{min-width:720px}}   /* the map's 14 px pin letters never scale below 14 px: it scrolls instead */
.legend{{font-size:14px;color:var(--muted);margin:6px 0}} .credit{{white-space:nowrap}}
.key{{display:grid;grid-template-columns:1fr;gap:4px 24px;margin:12px 0}} @media (min-width:720px){{.key{{grid-template-columns:2fr 1fr}}}}
.key h3{{font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin:0 0 4px;border-bottom:1px solid var(--line);padding-bottom:2px}}
.kl{{list-style:none;margin:0;padding:0}} .kl li{{margin:2px 0}} .kl.two{{columns:2;column-gap:24px}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:14px;font-weight:700;background:var(--head);border-bottom:2px solid var(--ink)}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.flag{{color:var(--flag);font-weight:700}} tr.this td{{font-weight:700}} td.lt{{color:var(--muted);white-space:nowrap}}
td.bar{{min-width:200px;white-space:nowrap}} .bn{{display:inline-block;width:2.2em;text-align:right;font-weight:700;margin-right:8px;font-variant-numeric:tabular-nums}}
.bt{{position:relative;display:inline-block;width:calc(100% - 3em);height:12px;vertical-align:-1px}} .bf{{position:absolute;left:0;top:0;bottom:0;border-radius:2px}}
.bc{{position:absolute;top:-4px;bottom:-4px;border-left:2px dashed var(--flag)}}
dl.terms{{display:grid;grid-template-columns:1fr;gap:2px 16px}} @media (min-width:720px){{dl.terms{{grid-template-columns:11em 1fr}}}}
dt{{font-weight:700}} dd{{margin:0 0 6px}}
.report{{background:#FFF4E8;border-left:5px solid #FF8312;border-radius:4px;padding:10px 14px;margin:16px 0}} .report p{{margin:4px 0}}
.empty{{background:#FFFBEB;border-left:3px solid var(--amber);padding:10px 14px}}
footer{{margin:28px 0 12px;font-size:14px;color:var(--muted)}}
tr.nr td{{color:var(--muted)}} tr.nr td.n{{font-style:italic}}
.sw{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px;border:1px solid rgba(0,0,0,.08)}}
.cc-legend .lg{{display:inline-block;margin-right:12px;white-space:nowrap}}
.dn{{display:inline-flex;align-items:baseline}} .dn .sw{{flex:none}}   /* 13 Oct 2026: the square never wraps away from its name */
.band{{background:#1F2024;color:#fff}} .band-in{{max-width:880px;margin:0 auto;padding:14px 16px 12px}} .band-in .brand-logo{{display:block;height:30px;width:auto;margin-bottom:6px}} .band-t{{font-size:23px;font-weight:700;line-height:1.25}} .band-s{{font-size:14px;color:#C9CED6}} .band-rule{{height:4px;background:linear-gradient(90deg,#FF8312,#FFA10A)}} .brief li{{margin:4px 0}} svg .tagt{{fill:#B91C1C;font:700 14px Inter,Arial,sans-serif}} footer .brand-logo{{height:16px;width:auto;vertical-align:-3px}}
.lot{{border-top:2px solid var(--ink)}} .lot>p:first-child{{margin:8px 0}} .lot-row{{display:grid;grid-template-columns:1fr;gap:0 16px;border-bottom:1px solid var(--line);padding:8px 0}}
@media (min-width:720px){{.lot-row{{grid-template-columns:13em 1fr}}}}
.lot-l{{font-size:14px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}} .lot-row p{{margin:0}}
.lot-src{{font-size:14px;color:var(--muted)}} .lot-demo{{color:#B91C1C;font-weight:600}} .lot-st{{white-space:nowrap}}
sup{{font-size:14px;line-height:0}} sup a{{color:var(--muted);text-decoration:none;padding:0 2px}}
ol.src{{padding-left:24px}} ol.src li{{font-size:14px;color:var(--muted);margin:3px 0}}
@media (min-width:720px){{ol.src{{columns:2;column-gap:28px}} ol.src li{{break-inside:avoid}}}}
svg .cl{{fill:var(--ink);font:14px Inter,Arial,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}} svg .cn{{font-weight:700}}
@media print{{
  @page{{size:A4;margin:14mm}}
  body{{font-size:11pt}} main{{max-width:none;padding:0}}
  .actions,.nav{{display:none}}
  h2{{break-after:avoid}} table,svg,.fig,.report,.key{{break-inside:avoid}}
  .mapwrap svg{{min-width:0}}   /* on paper the page width, not a phone's scroll */
  .figs{{grid-template-columns:repeat(4,1fr)}}
  .kick{{break-before:page;margin-top:0}}
  th,.report,.band,.band-rule,.bf{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  a{{color:inherit;text-decoration:none}}
}}
</style></head>
<body>{band}<main>
{notice}
<div class="nav">{nav}</div>
<h1>{title}</h1>
<p class="sub">{tenant} · monthly bulletin · {as_at}</p>
<div class="actions"><a class="btn" href="{pdf_href}">Download the PDF</a><a class="lnk" href="{leaflet_href}">The one-page leaflet</a><a class="lnk" href="{leaflet_pdf_href}">Leaflet PDF</a><a class="lnk" href="/map/">Open the public map</a></div>
<p class="lede">{lede}</p>
{empty}
<div class="figs" data-bulletin="headline">{head}</div>
<p class="def">{definition}</p>
{map_block}
{brief}
<div class="report"><p><b>{rep_lorry}</b></p><p>{rep_hours}</p><p>{rep_formats}</p></div>

<p class="kick">02 Routes and roads</p>
<h2>Every route this month</h2>
{routes}

<h2>What is being moved</h2>
<div class="tw"><table><thead><tr><th>Material</th><th class="n">Two-way a day</th><th class="n">Lorries</th><th class="n">Tonnes a day</th></tr></thead>
<tbody>{moved}<tr class="this"><td>All routes</td><td class="n">{mt_a_day}</td><td class="n">{mt_vehicles}</td>
<td class="n">{mt_t_day}</td></tr></tbody></table></div>

<h2>Road works and limits, {month_long}</h2>
<div class="tw"><table data-bulletin="works"><thead><tr><th>Where</th><th>What</th><th>When and who</th></tr></thead>
<tbody>{works}</tbody></table></div>
<ul>{checks}{others}</ul>

<h2>What changed since last month</h2>
<div class="tw"><table><thead><tr><th>Month</th><th class="n">Two-way a day</th><th class="n">Lorries</th><th class="n">CO₂e a day</th><th class="n">Routes</th></tr></thead>
<tbody>{change}</tbody></table></div>
<p>{change_text} <span class="muted">Each month's approved plan as it stands today.</span></p>

{councils_kicker}
{council_mv}

{council}

<p class="kick">04 Carbon and the small print</p>
{lot}

<h2>This month at a glance</h2>
<div class="tw"><table data-bulletin="glance"><thead><tr><th>Item</th><th class="n">This month</th><th>Data</th></tr></thead>
<tbody>{glance}</tbody></table></div>
<p class="muted">Not reported: needs observed records (counts, gate or camera records). A forecast has none, so the line is left empty, never estimated.</p>

<h2>Terms</h2>
<dl class="terms">{terms}</dl>

<h2>Caveats</h2>
<ul>{caveats}</ul>

{sources}

<div class="report"><p><b>{rep_lorry}</b></p><p>{rep_hours}</p><p>{rep_formats}</p></div>

<footer>{notice} {mark} {foot} · wayscope.co.uk</footer>
</main></body></html>""".format(**v)
