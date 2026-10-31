"""
clp_doc.py — the outline Construction Logistics Plan as a Word file, for one site or a set of sites.
Wayscope, 30 Oct 2026 (task 4a, PR 1 of 4). Plan: notes/session-1030-clp-document.md (not in git); mockup approved
by the user 30 Oct ("any site can have one no matter how big or small, you could also include multple sites in one clp
if needed. the rest is all your reccomendation").

WHAT IT IS
----------
A .docx a planner downloads, completes and signs. It keeps the section numbers and headings of the CLOCS outline CLP
template (so a reviewer finds each part) and copies none of its guidance sentences and no logo; every placeholder is in
Wayscope's own words. Three kinds of text, visibly different:
  * filled by Wayscope: normal text and real Word tables, each block with a small grey source line;
  * "To complete": the paragraph style TODO_STYLE (yellow, a left bar), listed again under "Still to complete";
  * signatures and dates: empty boxes on the cover.
A figure is read from the platform or it is a placeholder, never invented. It is a dated snapshot and says so on the
cover and in every footer; a demo tenant's notice heads every page.

WHICH LORRIES
-------------
A CLP is a list of one or more locations, any type. Its lorries = every APPROVED line whose route has an end at one of
them. One load = one lorry visit = one trip (gate_arrivals.trips_for, the one trips rule). A route with BOTH ends in the
list counts once and is called "between sites in this plan". Lines waiting for approval are a note, never a figure.

THE CLOCS TOOL'S RULES (clp_tool_example.xlsm, read 30 Oct)
-----------------------------------------------------------
  * a stage's "trips (monthly)" = its busiest month; "peak trips (daily)" = that ÷ the working days (one decimal);
  * the period of a stage in quarters;
  * vehicles in three weight bands by gross weight: 3.5 t and under, 3.5 t to 7.5 t, over 7.5 t;
  * the hourly arrival profile in the peak month, and the minutes between arrivals in each hour.
Wayscope's hourly profile is the plan's even spread over each gate's open hours less the no-delivery bands and its shut
times (gate_hours.open_minutes, the Gate arrivals rule), and the document says so: it is not a count.

STAGES
------
The template's stages are made of Wayscope disciplines (planning.clp on Config; DEFAULT_STAGES when absent). A
discipline no stage names becomes a stage of its own after the last, so no load is ever lost. Building programmes use
3.1's six stages, infrastructure 3.2's (plus 3.2.7 Pavement and surfacing, the user's Q3).

RULES
-----
* Reads only; every SQL literal carries the tenant predicate. No team id or name is printed: a CLP is the site's.
* The word rule: WORD_BAN over every string the document holds (test_clp_doc), no API or back-end words.
* PR 2 adds the charts, the three plans and §2.3 / §2.4 from the map layers; PR 3 the CLP records, the cover fields
  and the issue record; PR 4 the appendices.
"""
import datetime
import io
import re

import access
import config
import conversions
import db
import derived
import export
import gate_arrivals
import gate_hours
import gates
import site_areas
import site_layout_paper  # 31 Oct 2026 (4c PR 5): the site's layout phase for §4
import taxonomy
import weeks

MONTHS = gate_arrivals.MONTHS
MAX_STAGES = 8
IMPACT = ("higher", "medium")

#: the template's stages; each lists the Wayscope disciplines (the generic seed's ids) that make it
DEFAULT_STAGES = {
    "infrastructure": [
        {"number": "3.2.1", "name": "Site establishment, clearance and alterations", "disciplines": ["utilities", "temporary_works"]},
        {"number": "3.2.2", "name": "Excavation and foundations", "disciplines": ["earthworks"]},
        {"number": "3.2.3", "name": "Sub-structure", "disciplines": ["substructure"]},
        {"number": "3.2.4", "name": "Super-structure", "disciplines": ["structures"]},
        {"number": "3.2.5", "name": "Services and systems installation", "disciplines": ["mep", "ene", "ccs"]},
        {"number": "3.2.6", "name": "Fit-out, testing and commissioning", "disciplines": ["stations"]},
        {"number": "3.2.7", "name": "Pavement and surfacing", "disciplines": ["superstructure"]},
    ],
    "building": [
        {"number": "3.1.1", "name": "Site setup and demolition", "disciplines": ["utilities", "temporary_works"]},
        {"number": "3.1.2", "name": "Basement excavation and piling", "disciplines": ["earthworks"]},
        {"number": "3.1.3", "name": "Sub-structure", "disciplines": ["substructure"]},
        {"number": "3.1.4", "name": "Super-structure", "disciplines": ["structures"]},
        {"number": "3.1.5", "name": "Cladding", "disciplines": []},
        {"number": "3.1.6", "name": "Fit-out, testing and commissioning", "disciplines": ["stations", "mep", "ene", "ccs"]},
    ],
}

BANDS = (("3.5 t and under", 3.5), ("3.5 t to 7.5 t", 7.5), ("Over 7.5 t", None))
NOT_TYPED_BAND = "Weight not typed"

#: words no string in the document may carry (the landing page's list, the back-end words of the screens' rule)
WORD_BAN = ("secure", "trusted by", "testimonial", "real-time", "real time", "optimise", "optimize", "predict",
            "telematics", "live tracking", "truck", "api", "endpoint", "server", "backend", "back-end", "database",
            "json", "token", "cached", "geometry", "here routing", "mapbox")
_BAN_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in WORD_BAN) + r")\b", re.IGNORECASE)
_AI_RE = re.compile(r"\bAI\b")

#: the §5 checklist: (group, row) in the template's order
MEASURES = (
    ("Measures influencing construction vehicles and deliveries", (
        "Safety and environmental standards and programmes", "Adherence to designated routes", "Delivery scheduling",
        "Re-timing for out of peak deliveries", "Re-timing for out of hours deliveries",
        "Use of holding areas and vehicle call off areas", "Use of logistics and consolidation centres",
        "Vehicle choice")),
    ("Measures to encourage sustainable freight", ("Freight by water*", "Freight by rail*")),
    ("Material procurement measures", ("DfMA and offsite manufacture", "Re-use of material on site", "Smart procurement")),
    ("Other measures", ("Collaboration with other sites in the area", "Implement a staff travel plan")),
)
STAR_NOTE = ("* Where the site, a consolidation centre or a holding area is within 100 m of a navigable waterway or a rail "
             "freight siding. Wayscope does not hold waterways or sidings yet.")


def banned_words(text):
    """The banned words in `text` (lower-cased matches; 'AI' only as a capitalised word)."""
    out = [m.group(0).lower() for m in _BAN_RE.finditer(text or "")]
    out += [m.group(0) for m in _AI_RE.finditer(text or "")]
    return out


# --------------------------------------------------------------------------- #
#  Settings                                                                    #
# --------------------------------------------------------------------------- #
def settings_problem(v):
    """None, or one sentence for Config: planning.clp = {programme, stages: [{number, name, disciplines}]} (absent = the
    defaults). At most MAX_STAGES stages; a discipline in one stage only."""
    if v is None:
        return None
    if not isinstance(v, dict):
        return "planning.clp must be a block with a programme and its stages"
    prog = v.get("programme", "infrastructure")
    if prog not in DEFAULT_STAGES:
        return "planning.clp.programme must be infrastructure or building"
    st = v.get("stages")
    if st is None:
        return None
    if not isinstance(st, list) or not st:
        return "planning.clp.stages must be a list of stages"
    if len(st) > MAX_STAGES:
        return f"planning.clp.stages: at most {MAX_STAGES} stages"
    seen = {}
    for i, s in enumerate(st):
        if not isinstance(s, dict) or not str(s.get("name") or "").strip():
            return f"planning.clp.stages[{i}] needs a name"
        ds = s.get("disciplines") or []
        if not isinstance(ds, list) or not all(isinstance(d, str) for d in ds):
            return f"planning.clp.stages[{i}].disciplines must be a list of disciplines"
        for d in ds:
            if d in seen:
                return f"planning.clp.stages: {d} is in two stages ({seen[d] + 1} and {i + 1})"
            seen[d] = i
    return None


def settings(factors):
    """{programme, stages} from planning.clp, else the defaults for the programme."""
    v = ((factors or {}).get("planning") or {}).get("clp")
    if v is not None and settings_problem(v) is not None:
        v = None
    v = v or {}
    prog = v.get("programme") or "infrastructure"
    stages = v.get("stages") or DEFAULT_STAGES[prog]
    prefix = "3.1" if prog == "building" else "3.2"
    out = []
    for i, s in enumerate(stages):
        out.append({"number": str(s.get("number") or f"{prefix}.{i + 1}"), "name": str(s["name"]).strip(),
                    "disciplines": list(s.get("disciplines") or []), "added": False})
    return {"programme": prog, "prefix": prefix, "stages": out}


# --------------------------------------------------------------------------- #
#  Small words                                                                 #
# --------------------------------------------------------------------------- #
def month_label(mi):
    return gate_arrivals.month_label(mi)


def quarter_label(mi):
    y, m = weeks._month_of(mi)
    return f"Q{(m - 1) // 3 + 1} {y}"


def period_words(a, b, quarters=False):
    f = quarter_label if quarters else month_label
    return f(a) if f(a) == f(b) else f"{f(a)} – {f(b)}"


def n(x):
    """1234 -> '1,234'; 12.5 -> '12.5'."""
    if x is None:
        return "—"
    if isinstance(x, float) and not x.is_integer():
        return f"{x:,.1f}"
    return f"{int(round(x)):,}"


def r1(x):
    return round(float(x) + 0.0, 1)


def _days_words(days):
    """'1111100' -> 'Mon–Fri'; anything else as a list."""
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    d = gate_hours.clean_days(days) if days else None
    if not d:
        return "every day"
    on = [i for i, c in enumerate(d) if c == "1"]
    if not on:
        return "no day"
    if on == list(range(on[0], on[-1] + 1)) and len(on) > 2:
        return f"{names[on[0]]}–{names[on[-1]]}"
    return ", ".join(names[i] for i in on)


def band_of(gvw):
    if gvw is None:
        return NOT_TYPED_BAND
    for name, top in BANDS:
        if top is None or float(gvw) <= top + 1e-9:
            return name
    return BANDS[-1][0]


def _unit():
    try:
        return "mi" if (config.tenant_settings(conversions).get("distance_unit") or "km") == "mi" else "km"
    except Exception:
        return "km"


# --------------------------------------------------------------------------- #
#  The read                                                                    #
# --------------------------------------------------------------------------- #
def _figures(row, factors):
    """(trips, tonnes) for one forecast row: the Gate arrivals trips rule, tonnes on the same payload."""
    payload_t, _fb = derived.payload_for(row.get("vehicle_type"), factors)
    ctx = {"unit": row.get("unit"), "payload_t": payload_t, "material_type": row.get("material_type"),
           "vehicle_type": row.get("vehicle_type"), "baked": False}
    f = derived.day_figures(row.get("quantity"), ctx, factors)
    return int(f["trips"]), float(f["tonnes"])


def gather(location_ids, factors=None, working_days=None, now=None, layers=True, team=None):
    """
    Every figure the document prints, as data (test_clp_doc compares the .docx with this, and this with the modules
    that own each figure). ValueError for an empty or unknown location.
    31 Oct 2026 (PR 3a, John: "each section only see their clp"): `team` = a team slot counts that team's
    lines only — every figure, route, plan, gate and collision row follows from `lines`; None = every team.
    """
    factors = factors or conversions.load_factors()
    wd = float(working_days or gate_arrivals.working_days(factors))
    ids = []
    for x in location_ids or []:
        x = str(x).strip()
        if x and x not in ids:
            ids.append(x)
    if not ids:
        raise ValueError("Pick at least one location.")
    team = access.canonical_ipt(team) if team else None
    tenant_id = db.current_tenant()
    all_locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (tenant_id,))}
    missing = [x for x in ids if x not in all_locs]
    if missing:
        raise ValueError("No such location: " + ", ".join(missing) + ".")
    locs = [all_locs[x] for x in ids]
    inset = set(ids)
    routes = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (tenant_id,))}
    touching = {rid: r for rid, r in routes.items() if r.get("origin_id") in inset or r.get("dest_id") in inset}
    rows = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND status IN ('Approved', 'Pending') "
                    "ORDER BY route_id, discipline, section_id, month_index", (tenant_id,))
    discs = {d["id"]: d for d in taxonomy.list_disciplines(include_out_of_scope=True)}
    st = settings(factors)
    stage_of = {}
    for s in st["stages"]:
        for d in s["disciplines"]:
            stage_of[d] = s["number"]
    stages = [dict(s) for s in st["stages"]]
    next_no = len(stages) + 1

    lines = []
    pending = 0
    for row in rows:
        r = touching.get(row.get("route_id"))
        if not r:
            continue
        if team and access.canonical_ipt(row.get("ipt")) != team:
            continue
        if row.get("status") != "Approved":
            pending += 1
            continue
        trips, tonnes = _figures(row, factors)
        if trips <= 0 and tonnes <= 0:
            continue
        o_in, d_in = r.get("origin_id") in inset, r.get("dest_id") in inset
        direction = "between" if (o_in and d_in) else ("in" if d_in else "out")
        disc = row.get("discipline") or ""
        if disc not in stage_of:
            label = (discs.get(disc) or {}).get("label") or disc or "Other work"
            num = f"{st['prefix']}.{next_no}"
            next_no += 1
            stages.append({"number": num, "name": label, "disciplines": [disc], "added": True})
            stage_of[disc] = num
        lines.append({"route_id": r["id"], "month": int(row["month_index"]), "discipline": disc,
                      "stage": stage_of[disc], "vehicle": row.get("vehicle_type") or "",
                      "material": row.get("material_type") or "", "trips": trips, "tonnes": tonnes,
                      "direction": direction})

    vs = (factors or {}).get("vehicles") or {}

    def vlabel(v):
        return conversions.vehicle_label(factors, v) or "Vehicle not named"

    # ---- totals --------------------------------------------------------------------------------------------- #
    by_month = {}
    for l in lines:
        by_month[l["month"]] = by_month.get(l["month"], 0) + l["trips"]
    months = sorted(m for m, v in by_month.items() if v > 0)
    peak = None
    if months:
        peak = min(months, key=lambda m: (-by_month[m], m))
    totals = {
        "trips": sum(l["trips"] for l in lines),
        "tonnes": round(sum(l["tonnes"] for l in lines), 1),
        "in": sum(l["trips"] for l in lines if l["direction"] == "in"),
        "out": sum(l["trips"] for l in lines if l["direction"] == "out"),
        "between": sum(l["trips"] for l in lines if l["direction"] == "between"),
        "first": months[0] if months else None, "last": months[-1] if months else None,
        "peak_month": peak, "peak_trips": by_month.get(peak, 0) if peak else 0,
        "peak_daily": r1(by_month[peak] / wd) if peak else None,
        "pending_lines": pending,
    }

    # ---- stages --------------------------------------------------------------------------------------------- #
    for s in stages:
        sl = [l for l in lines if l["stage"] == s["number"]]
        bm = {}
        for l in sl:
            bm[l["month"]] = bm.get(l["month"], 0) + l["trips"]
        ms = sorted(m for m, v in bm.items() if v > 0)
        s["trips_total"] = sum(bm.values())
        s["tonnes"] = round(sum(l["tonnes"] for l in sl), 1)
        s["by_month"] = bm
        s["discipline_labels"] = [(discs.get(d) or {}).get("label") or d for d in s["disciplines"]]
        if not ms:
            s.update({"first": None, "last": None, "peak_month": None, "peak_trips": 0, "peak_daily": None,
                      "vehicles": [], "bands": {}, "materials": [], "routes": []})
            continue
        pm = min(ms, key=lambda m: (-bm[m], m))
        vby = {}
        for l in sl:
            if l["month"] == pm:
                vby[l["vehicle"]] = vby.get(l["vehicle"], 0) + l["trips"]
        vrows = [{"vehicle": v, "label": vlabel(v), "gvw_t": (vs.get(v) or {}).get("gvw_t"),
                  "band": band_of((vs.get(v) or {}).get("gvw_t")), "trips": k}
                 for v, k in sorted(vby.items(), key=lambda kv: (-kv[1], kv[0]))]
        bands = {}
        for v in vrows:
            bands[v["band"]] = bands.get(v["band"], 0) + v["trips"]
        mats = {}
        for l in sl:
            mats[l["material"]] = mats.get(l["material"], 0.0) + l["tonnes"]
        s.update({"first": ms[0], "last": ms[-1], "peak_month": pm, "peak_trips": bm[pm], "peak_daily": r1(bm[pm] / wd),
                  "vehicles": vrows, "bands": bands,
                  "materials": [{"material": k, "tonnes": round(v, 1)} for k, v in sorted(mats.items(), key=lambda kv: -kv[1])],
                  "routes": sorted({l["route_id"] for l in sl})})

    # ---- routes --------------------------------------------------------------------------------------------- #
    unit = _unit()
    rl = {}
    for l in lines:
        e = rl.setdefault(l["route_id"], {"trips": 0, "tonnes": 0.0, "months": set(), "veh": {}, "mat": {}, "dir": l["direction"]})
        e["trips"] += l["trips"]
        e["tonnes"] += l["tonnes"]
        e["months"].add(l["month"])
        e["veh"][l["vehicle"]] = e["veh"].get(l["vehicle"], 0) + l["trips"]
        e["mat"][l["material"]] = e["mat"].get(l["material"], 0.0) + l["tonnes"]
    geo = {}
    for g in db.query("SELECT route_id, vehicle_profile, distance_km FROM route_geometry WHERE tenant_id = ? "
                      "AND leg = 'loaded' AND alt_index = 0 AND (error IS NULL OR error = '')", (tenant_id,)):
        geo[(g["route_id"], g["vehicle_profile"])] = g.get("distance_km")
    route_rows = []
    for rid in sorted(rl):
        e, r = rl[rid], routes[rid]
        veh = max(e["veh"].items(), key=lambda kv: (kv[1], kv[0]))[0]
        km = geo.get((rid, veh))
        dist = None if km is None else (float(km) / config.KM_PER_MILE if unit == "mi" else float(km))
        route_rows.append({
            "route_id": rid, "direction": e["dir"],
            "from": (all_locs.get(r.get("origin_id")) or {}).get("name") or r.get("origin_id") or "",
            "to": (all_locs.get(r.get("dest_id")) or {}).get("name") or r.get("dest_id") or "",
            "from_id": r.get("origin_id"), "to_id": r.get("dest_id"),
            "distance": (None if dist is None else r1(dist)), "unit": unit, "routed": km is not None,
            "vehicles": [vlabel(v) for v, _k in sorted(e["veh"].items(), key=lambda kv: (-kv[1], kv[0]))],
            "materials": [m for m, _t in sorted(e["mat"].items(), key=lambda kv: -kv[1])],
            "first": min(e["months"]), "last": max(e["months"]), "trips": e["trips"], "tonnes": round(e["tonnes"], 1)})

    # ---- materials ------------------------------------------------------------------------------------------ #
    mats = {}
    for l in lines:
        k = (l["material"], l["direction"])
        mats[k] = mats.get(k, 0.0) + l["tonnes"]
    materials = [{"material": m, "direction": d, "tonnes": round(v, 1)}
                 for (m, d), v in sorted(mats.items(), key=lambda kv: -kv[1])]

    # ---- gates, areas and the hourly profile ---------------------------------------------------------------- #
    gbl = gates.gates_by_location(include_inactive=False)
    peak_bands = gate_hours.peak_bands(factors)
    sites = []
    for loc in locs:
        grows = []
        for g in gbl.get(loc["id"]) or []:
            om = gate_hours.open_minutes(g, factors)
            check = g.get("safety_minutes")
            cap = gate_hours.capacity(om["minutes"], check)
            grows.append({"id": g["id"], "name": g.get("name") or g["id"],
                          "direction": {"access": "in", "egress": "out"}.get(g.get("direction"), "in and out"),
                          "hours": om["hours"], "days": _days_words(g.get("open_days")),
                          "shut": om["shut_words"], "check_in": check,
                          "capacity": (None if cap is None else r1(cap)), "closed": gates.closed_words(g) or None,
                          "note": (g.get("note") or "").strip() or None, "access_road": bool(g.get("access_zone_id"))})
        areas = [{"name": a["name"], "activity": a["activity"], "bays": a["bays"], "minutes": a["service_minutes"],
                  "level": a["level"]} for a in site_areas.list_areas(loc["id"], include_inactive=False)]
        speed = loc.get("site_speed_kph")
        sites.append({"id": loc["id"], "name": loc.get("name") or loc["id"], "type": loc.get("loc_type") or "",
                      "lat": loc.get("lat"), "lon": loc.get("lon"), "gates": grows, "areas": areas,
                      "site_speed_kph": (float(speed) if speed not in (None, "") else None),
                      "clp_cap": (float(loc["clp_cap_per_day"]) if loc.get("clp_cap_per_day") not in (None, "") else None),
                      "site_rules": (loc.get("site_rules") or "").strip() or None,
                      "trips": sum(l["trips"] for l in lines if routes[l["route_id"]].get("origin_id") == loc["id"]
                                   or routes[l["route_id"]].get("dest_id") == loc["id"])})
    # one profile per site, in THAT site's busiest month (a set of sites peaks in different months; a combined chart
    # would hide which gate queues)
    hourly = []
    gate_by_id = {g["id"]: g for gs in gbl.values() for g in gs}
    ar_by_month = {}
    for site in sites:
        sm = {}
        for l in lines:
            r = routes[l["route_id"]]
            if site["id"] in (r.get("origin_id"), r.get("dest_id")):
                sm[l["month"]] = sm.get(l["month"], 0) + l["trips"]
        if not sm:
            site["peak_month"] = None
            continue
        pm = min(sm, key=lambda m: (-sm[m], m))
        site["peak_month"], site["peak_trips"] = pm, sm[pm]
        if pm not in ar_by_month:
            ar_by_month[pm] = gate_arrivals.arrivals(pm, ({"role": "ipt", "ipt": team} if team else {"role": "planner"}),
                                                     factors=factors, working_days=wd)
        for g in ar_by_month[pm]["gates"]:
            if g["location_id"] != site["id"] or not g["arrivals_per_day"]:
                continue
            if team:
                # 31 Oct 2026 (PR 3a): the team's own lorries at the gate (gate_arrivals' per-team figure); the gate's
                # load against its capacity stays every team's, and the document says so
                mine = (g.get("per_team") or [{}])[0].get("arrivals_per_day") or 0.0
                if not mine:
                    continue
                share = mine / g["arrivals_per_day"]
                g = dict(g, arrivals_per_day=mine, laden_per_day=r1(g["laden_per_day"] * share),
                         empty_per_day=r1(g["empty_per_day"] * share))
            grow = gate_by_id.get(g["gate_id"]) or gates.get_gate(g["gate_id"]) or {}
            iv = gate_hours.open_minutes(grow, factors)["intervals"]
            total_open = sum(b - a for a, b in iv)
            per = []
            for h in range(24):
                mins = sum(max(0, min(b, (h + 1) * 60) - max(a, h * 60)) for a, b in iv)
                lorries = (g["arrivals_per_day"] * mins / total_open) if total_open else 0.0
                per.append({"hour": h, "open_minutes": mins, "lorries": r1(lorries),
                            "minutes_between": (r1(mins / lorries) if lorries > 0 else None)})
            hourly.append({"gate": g["gate_name"], "site": g["location_name"], "month": pm,
                           "arrivals_per_day": g["arrivals_per_day"], "laden_per_day": g["laden_per_day"],
                           "empty_per_day": g["empty_per_day"], "capacity_pct": g["capacity_pct"],
                           "hours": g["open_hours"], "per_hour": per, "all_teams_pct": bool(team)})

    # ---- §5 evidence ---------------------------------------------------------------------------------------- #
    measures = _measures(lines, route_rows, factors, peak_bands, touching, all_locs, vlabel)

    tenant = export._tenant()
    when = now or datetime.datetime.now(_london())
    name = ", ".join(s["name"] for s in sites) if len(sites) <= 3 else f"{sites[0]['name']} and {len(sites) - 1} more sites"
    other_ends = sorted({(all_locs.get(rid_end) or {}).get("name") or rid_end
                         for r in touching.values() if r["id"] in rl
                         for rid_end in (r.get("origin_id"), r.get("dest_id")) if rid_end not in inset})
    out = {
        "name": name, "site_names": [s["name"] for s in sites], "location_ids": ids,
        "team": team, "team_name": (taxonomy.team_name(team) if team else None),
        # PR 3a: what the CLP record adds (cover details, the issue, the history); build() reads them, gather() never
        "cover": {}, "issue": None, "history": [],
        "scheme": tenant.get("name") or "", "demo_notice": tenant.get("demo_notice") or None,
        "snapshot": when, "working_days": wd, "programme": st["programme"], "prefix": st["prefix"],
        "stages": stages, "lines": lines, "by_month": by_month, "totals": totals, "routes": route_rows,
        "materials": materials, "sites": sites, "hourly": hourly, "peak_bands": peak_bands,
        "peak_band_words": gate_hours.peak_words(peak_bands), "measures": measures, "other_ends": other_ends,
        "unit": unit, "layers": None,
    }
    if layers:
        # 30 Oct 2026 (PR 2): §2.3 / §2.4 from what is stored along these routes (clp_doc_layers)
        import clp_doc_layers
        out["layers"] = clp_doc_layers.gather(out)
    return out


def _london():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/London")
    except Exception:
        return datetime.timezone.utc


def _measures(lines, route_rows, factors, bands, touching, all_locs, vlabel):
    """{row: {tick, evidence}} — a tick only where the approved plan already does it (the user's Q8)."""
    vs = (factors or {}).get("vehicles") or {}
    m = {}
    used = sorted({l["vehicle"] for l in lines})
    euro = {(vs.get(v) or {}).get("euro_class") for v in used}
    if used and euro and None not in euro and "" not in euro:
        cls = sorted(euro)
        m["Safety and environmental standards and programmes"] = {
            "tick": False, "evidence": (f"Every lorry type planned is {cls[0]}." if len(cls) == 1 else
                                        "The lorry types planned are " + ", ".join(cls) + ".")}
    if route_rows:
        unrouted = [r["route_id"] for r in route_rows if not r["routed"]]
        k = len(route_rows)
        if not unrouted:
            m["Adherence to designated routes"] = {"tick": True, "evidence": (
                f"{k} approved route{'s' if k != 1 else ''}, each worked out as a lorry route for its vehicle's size and "
                f"weight, with a driver route sheet for each.")}
        else:
            m["Adherence to designated routes"] = {"tick": False, "evidence": (
                f"{k - len(unrouted)} of {k} routes drawn as lorry routes; not drawn yet: {', '.join(unrouted)}.")}
    rids = sorted(touching)
    conf = None
    if rids:
        marks = ",".join("?" for _ in rids)
        try:
            conf = db.query(f"SELECT COUNT(*) AS n FROM forecast_weeks WHERE tenant_id = ? AND status = 'confirmed' "
                            f"AND route_id IN ({marks})", (db.current_tenant(), *rids))
        except Exception:                          # noqa: BLE001  a database without the Look-ahead tables
            conf = None
        if conf and int(conf[0]["n"] or 0) > 0:
            m["Delivery scheduling"] = {"tick": True, "evidence": (
                "Weeks are confirmed in the weekly Look-ahead, with each gate's arrivals against its capacity and a Day "
                "sheet for each day.")}
    if bands:
        m["Re-timing for out of peak deliveries"] = {"tick": True, "evidence": (
            f"No deliveries {gate_hours.peak_words(bands)} at any gate.")}
    if lines:
        by_v = {}
        for l in lines:
            e = by_v.setdefault(l["vehicle"], {"trips": 0, "mat": set()})
            e["trips"] += l["trips"]
            e["mat"].add(l["material"])
        parts = [f"{vlabel(v)} for {', '.join(sorted(e['mat']))} ({n(e['trips'])} loads)"
                 for v, e in sorted(by_v.items(), key=lambda kv: -kv[1]["trips"])]
        m["Vehicle choice"] = {"tick": True, "evidence": "; ".join(parts) + "."}
    rail = [l for l in lines if "rail" in ((all_locs.get((touching.get(l["route_id"]) or {}).get("origin_id")) or {})
                                         .get("loc_type") or "").lower()]
    if rail:
        names = sorted({(all_locs.get(touching[l["route_id"]]["origin_id"]) or {}).get("name") for l in rail})
        m["Freight by rail*"] = {"tick": False, "evidence": (
            f"Delivered by rail to {', '.join(x for x in names if x)}, then by lorry: {n(sum(l['trips'] for l in rail))} "
            f"loads, {n(round(sum(l['tonnes'] for l in rail)))} t.")}
    pre = [l for l in lines if "precast" in (l["material"] or "").lower()]
    if pre:
        m["DfMA and offsite manufacture"] = {"tick": False, "evidence": (
            f"Precast units planned: {n(sum(l['trips'] for l in pre))} loads, {n(round(sum(l['tonnes'] for l in pre)))} t.")}
    return m


# --------------------------------------------------------------------------- #
#  The Word file                                                               #
# --------------------------------------------------------------------------- #
TODO_STYLE = "To complete"
SOURCE_STYLE = "Wayscope source"
NAVY = (0x0B, 0x3B, 0x66)


class _Doc:
    """python-docx with the three kinds of text and the list of what is still to complete."""

    def __init__(self):
        from docx import Document
        from docx.enum.style import WD_STYLE_TYPE
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor, Cm
        self.Pt, self.RGB, self.Cm, self.OX, self.qn = Pt, RGBColor, Cm, OxmlElement, qn
        self.d = Document()
        sec = self.d.sections[0]
        sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
        sec.left_margin = sec.right_margin = Cm(2.0)
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
        st = self.d.styles
        normal = st["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(10.5)
        for h, size in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11)):
            s = st[h]
            s.font.name = "Calibri"
            s.font.size = Pt(size)
            s.font.color.rgb = RGBColor(*NAVY)
        todo = st.add_style(TODO_STYLE, WD_STYLE_TYPE.PARAGRAPH)
        todo.base_style = normal
        todo.font.italic = True
        todo.font.color.rgb = RGBColor(0x5A, 0x43, 0x00)
        ppr = todo.element.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "FFF6C8")
        bdr = OxmlElement("w:pBdr")
        left = OxmlElement("w:left")
        for k, v in (("w:val", "single"), ("w:sz", "24"), ("w:space", "6"), ("w:color", "C89500")):
            left.set(qn(k), v)
        bdr.append(left)
        ppr.append(bdr)
        ppr.append(shd)
        src = st.add_style(SOURCE_STYLE, WD_STYLE_TYPE.PARAGRAPH)
        src.base_style = normal
        src.font.size = Pt(8.5)
        src.font.color.rgb = RGBColor(0x5B, 0x64, 0x70)
        self.todos = []
        self.section = ""
        self.pictures = 0

    # -- text ---------------------------------------------------------------------------------------------------- #
    def h(self, text, level=1):
        self.section = text.split(" ")[0]
        return self.d.add_heading(text, level=level)

    def p(self, text="", bold=False, italic=False, size=None):
        para = self.d.add_paragraph()
        if text:
            r = para.add_run(text)
            r.bold, r.italic = bold, italic
            if size:
                r.font.size = self.Pt(size)
        return para

    def bullets(self, items):
        for it in items:
            self.d.add_paragraph(it, style="List Bullet")

    def src(self, text):
        return self.d.add_paragraph(text, style=SOURCE_STYLE)

    def todo(self, what, where=None):
        """A 'To complete' paragraph; `where` is the line under Still to complete (defaults to the section number)."""
        para = self.d.add_paragraph(style=TODO_STYLE)
        r = para.add_run("To complete: ")
        r.bold = True
        r.italic = False
        para.add_run(what)
        self.todos.append(f"{where or self.section}: {what}")
        return para

    # -- tables -------------------------------------------------------------------------------------------------- #
    def table(self, head, rows, widths=None, numeric=()):
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        t = self.d.add_table(rows=1, cols=len(head))
        t.style = "Table Grid"
        for i, txt in enumerate(head):
            c = t.rows[0].cells[i]
            c.text = ""
            run = c.paragraphs[0].add_run(str(txt))
            run.bold = True
            self._shade(c, "EEF2F6")
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = "" if v is None else str(v)
                if i in numeric:
                    cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if widths:
            self._widths(t, widths)
        self.d.add_paragraph()
        return t

    def _widths(self, t, widths):
        """Fixed column widths (Word ignores a cell's width while the table fits itself to its text)."""
        t.autofit = False
        for i, w in enumerate(widths):
            t.columns[i].width = self.Cm(w)
            for c in t.columns[i].cells:
                c.width = self.Cm(w)

    def kv(self, rows, widths=(5.5, 11.5)):
        """A two-column label | value table with no header row (the cover)."""
        t = self.d.add_table(rows=0, cols=2)
        t.style = "Table Grid"
        for label, value in rows:
            c = t.add_row().cells
            c[0].text = label
            c[0].paragraphs[0].runs[0].bold = True
            self._shade(c[0], "EEF2F6")
            c[1].text = value or ""
        self._widths(t, widths)
        self.d.add_paragraph()
        return t

    def _shade(self, cell, fill):
        tcpr = cell._tc.get_or_add_tcPr()
        shd = self.OX("w:shd")
        shd.set(self.qn("w:val"), "clear")
        shd.set(self.qn("w:color"), "auto")
        shd.set(self.qn("w:fill"), fill)
        tcpr.append(shd)

    def todo_cell(self, cell, what, where):
        cell.text = ""
        para = cell.paragraphs[0]
        para.style = self.d.styles[TODO_STYLE]
        r = para.add_run("To complete: ")
        r.bold = True
        para.add_run(what)
        self.todos.append(f"{where}: {what}")

    def field(self, para, code, placeholder=""):
        """A Word field (PAGE, TOC …) with the text shown until Word updates it."""
        def fc(kind):
            e = self.OX("w:fldChar")
            e.set(self.qn("w:fldCharType"), kind)
            return e
        r1 = para.add_run()._r
        r1.append(fc("begin"))
        r2 = para.add_run()._r
        it = self.OX("w:instrText")
        it.set(self.qn("xml:space"), "preserve")
        it.text = f" {code} "
        r2.append(it)
        r3 = para.add_run()._r
        r3.append(fc("separate"))
        para.add_run(placeholder)
        r4 = para.add_run()._r
        r4.append(fc("end"))

    def update_fields_on_open(self):
        s = self.d.settings.element
        e = self.OX("w:updateFields")
        e.set(self.qn("w:val"), "true")
        s.append(e)

    def page_break(self):
        from docx.enum.text import WD_BREAK
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def picture(self, data, width_cm, alt, caption=None):
        """A picture (PNG or JPEG bytes) `width_cm` wide with its alternative text, and a caption in the source style."""
        para = self.d.add_paragraph()
        shape = para.add_run().add_picture(io.BytesIO(data), width=self.Cm(width_cm))
        shape._inline.docPr.set("descr", alt)
        self.pictures += 1
        if caption:
            self.src(caption)
        return para


def file_name(data, when=None):
    when = when or data["snapshot"]
    base = data["site_names"][0] if len(data["site_names"]) == 1 else data["name"]
    base = re.sub(r'[\\/:*?"<>|]+', " ", base).strip()
    return f"CLP {base} {when:%Y-%m-%d}.docx"


def _lower_lead(words):
    """'Every month' / 'From Mar 2027' / 'Until …' mid-sentence; a month name keeps its capital."""
    first = words.split(" ", 1)[0]
    return words[0].lower() + words[1:] if first in ("Every", "From", "Until") else words


def build(data, impact="higher", pictures=True, acc=None):
    """The .docx bytes for gather()'s data. `impact` picks the §5 checklist (higher or medium). `pictures` adds the
    charts and the three plans (clp_doc_pictures; the plans call the basemap); `acc` is the caller's access."""
    if impact not in IMPACT:
        raise ValueError("impact must be higher or medium")
    D = _Doc()
    d = data
    import clp_doc_pictures as PIC
    plan_pics = PIC.plans(d, acc=acc) if pictures else []
    L = d.get("layers") or {}
    T = d["totals"]
    when = d["snapshot"]
    snap_words = f"{when.day} {MONTHS[when.month - 1]} {when.year} at {when:%H:%M}"
    snap_short = f"{when.day} {MONTHS[when.month - 1]} {when.year}"
    title = d.get("title") or d["name"]
    demo = f"DEMO · {d['demo_notice']}" if d["demo_notice"] else None
    # 31 Oct 2026 (PR 3a): a draft says so on every page and keeps nothing; an approved issue carries its number and date
    iss = d.get("issue")
    issue_words = (f"Issue {iss['no']} · approved {_date_words(iss['date'])}" if iss else "DRAFT · not issued")
    cover = d.get("cover") or {}
    team_name = d.get("team_name")
    sites_word = "these sites" if len(d["sites"]) > 1 else "this site"
    wd = d["working_days"]

    # header and footer on every page
    sec = D.d.sections[0]
    hp = sec.header.paragraphs[0]
    hp.text = " · ".join(x for x in (demo, issue_words) if x)
    hp.alignment = 2
    fp = sec.footer.paragraphs[0]
    fp.style = D.d.styles[SOURCE_STYLE]
    fp.add_run(" · ".join(x for x in (demo, f"CLP {title}" + (f" · {team_name}" if team_name else ""),
                                      (f"Issue {iss['no']}" if iss else "Draft"), f"snapshot {snap_short}") if x)
               + " · page ")
    D.field(fp, "PAGE", "1")

    # ---------------------------------------------------------------- cover
    D.p("Construction Logistics Plan: outline", size=12)
    D.d.add_heading(title, level=0)
    if team_name:
        D.p(team_name, size=12, bold=True)
    if d["scheme"]:
        D.p(d["scheme"], size=12)
    if team_name:
        # 31 Oct 2026 (PR 3a, John's Q4): a team's plan counts the team's lorries only, and says so
        D.p(f"This plan covers the {team_name}'s lorries only. Other teams' lorries to {sites_word} are in their own "
            f"plans, and all of them together are in the plan for all teams.", italic=True)
    # PR 3a: the cover details typed on the CLP documents page fill these; a blank one stays a yellow "To complete"
    todo_rows = (("Landowner", "landowner", "who owns the land the site sits on."),
                 ("Site address", "address", "the postal address of the site entrance."),
                 ("Site postcode", "postcode", "the postcode."),
                 ("Existing site use", "site_use", "what the land is used for now."),
                 ("Summary of works", "summary", "one or two sentences on what is built here."))
    t = D.kv([("Development name", f"{d['scheme']}: {title}" if d["scheme"] else title)]
             + [(label, str(cover.get(key) or "").strip()) for label, key, _w in todo_rows]
             + [("Site position", "; ".join(f"{s['name']}: {_grid_words(s['lat'], s['lon'])}" for s in d["sites"]))])
    for i, (label, key, what) in enumerate(todo_rows):
        if not str(cover.get(key) or "").strip():
            D.todo_cell(t.rows[i + 1].cells[1], what, f"Cover, {label.lower()}")
    people = (("Construction logistics manager", "manager"), ("Logistics provider contact", "provider"))
    t2 = D.kv([(label, contact_words(cover, key)) for label, key in people])
    for i, (label, key) in enumerate(people):
        if not contact_words(cover, key):
            D.todo_cell(t2.rows[i].cells[1], "name, phone and email.", f"Cover, {label.lower()}")
    D.table(["CLP produced by", "Name", "Signature", "Date"],
            [["", "", "", ""], ["CLP accreditation date", "", "", ""]], widths=[5, 4, 4, 4])
    D.table(["CLP reviewed by", "Name", "Signature", "Date"],
            [["", "", "", ""], ["CLP accreditation date", "", "", ""]], widths=[5, 4, 4, 4])
    if iss:
        D.p(f"Issue {iss['no']} · approved by {iss.get('by') or 'a planner'} on {_date_words(iss['date'])} · a snapshot "
            f"of the approved plan in Wayscope on {snap_words}.", bold=True)
    else:
        D.p(f"DRAFT · not issued · a snapshot of the approved plan in Wayscope on {snap_words}.", bold=True)
    D.p("The figures change as the plan changes; download a new copy to bring them up to date.")
    D.p("Produced by Wayscope. The section numbers follow the CLOCS outline CLP template so a reviewer can find each "
        "part; this is not a CLOCS publication.")
    if demo:
        D.p(f"{demo}: every site, route and figure in this document is fictional.", bold=True)
    D.page_break()

    # ---------------------------------------------------------------- front: still to complete, contents
    D.h("Still to complete", 1)
    D.p("Wayscope filled what it holds. These parts need a person; each is shaded yellow where it stands.")
    anchor = D.p("")
    hist = d.get("history") or []
    if hist:
        # 31 Oct 2026 (PR 3a, Q8 / Q9): every issue, newest first, with what changed (worked out by Wayscope) and the notes
        D.h("Document history", 1)
        D.table(["Issue", "Date", "Approved by", "What changed"],
                [[str(h["no"]), _date_words(h["date"]), h.get("by") or "", h.get("words") or ""] for h in hist],
                widths=[1.4, 3, 3, 9.6])
    D.h("Contents", 1)
    D.field(D.p(), 'TOC \\o "1-3" \\h \\z \\u', "Word fills the contents and page numbers when the file is opened.")
    D.page_break()

    # ---------------------------------------------------------------- 1
    D.h("1 Introduction", 1)
    D.h("1.1 CLP objectives", 2)
    obj = []
    if d["peak_band_words"]:
        obj.append(f"No deliveries {d['peak_band_words']} at any gate.")
    for h in d["hourly"]:
        if h["capacity_pct"] is not None:
            obj.append(f"{h['gate']} kept under 85 % of its capacity; in its busiest month ({month_label(h['month'])}) "
                       f"the plan uses {h['capacity_pct']} %" + (", every team's lorries together." if h.get("all_teams_pct")
                                                                 else "."))
    if d["routes"]:
        obj.append(f"Every lorry on its designated route: {len(d['routes'])} route{'s' if len(d['routes']) != 1 else ''}, "
                   "a driver route sheet for each.")
    if obj:
        D.p("Objectives Wayscope can measure (keep, change or delete):")
        D.bullets(obj)
        D.src("From the gates' hours and no-delivery bands, Gate arrivals and the routes.")
    D.todo("any other aim of this plan (fewer lorries, lower emissions, less disruption) and how it will be measured.", "1.1")
    D.h("1.2 Site context", 2)
    if d["other_ends"]:
        D.p(f"Lorries to and from {sites_word} use {len(d['routes'])} route{'s' if len(d['routes']) != 1 else ''}. "
            f"The other ends: {', '.join(d['other_ends'])}.")
        D.src("From the approved plan's routes.")
    D.todo("where the site is, the roads around it, its transport links and anything else a reader needs to know.", "1.2")
    D.h("1.3 Development proposal", 2)
    for s in d["sites"]:
        if s["areas"]:
            D.p(f"Work areas at {s['name']}: " + ", ".join(
                a["name"] + (f" ({a['level']})" if a.get("level") else "") for a in s["areas"]) + ".")
    if d["materials"]:
        dir_word = {"in": "in", "out": "out", "between": "between sites in this plan"}
        D.table(["Material", "Tonnes", "Direction"],
                [[m["material"], n(round(m["tonnes"])), dir_word[m["direction"]]] for m in d["materials"]]
                + [["Total", n(round(T["tonnes"])), f"{n(T['trips'])} loads"]], widths=[8, 4, 5], numeric=(1,))
        D.src(f"From the approved plan, {period_words(T['first'], T['last'])}.")
    else:
        D.p(f"No approved lorry loads in Wayscope for {sites_word} on {snap_short}.")
    D.todo("what is being built, its size, and how it will be built.", "1.3")
    D.h("1.4 CLP structure", 2)
    D.p("The contents are on page 2. Sections 1 to 7 follow the outline CLP template's numbering.")

    # ---------------------------------------------------------------- 2
    D.h("2 Context, considerations and challenges", 1)
    D.h("2.1 Policy context", 2)
    D.todo("the national and local policies, plans and planning conditions this plan answers to.", "2.1")
    D.h("2.2 Three plans at different scales", 2)
    if plan_pics:
        D.p("Drawn by Wayscope from the approved plan. Each picture carries its own scale bar: use it, not the stated "
            "ratio, once the picture is resized to fit the page.")
        for pp in plan_pics:
            where = f" of {pp['site']}" if pp["site"] else ""
            D.picture(pp["jpg"], 17.0, pp["alt"], f"{pp['name']}{where} · {pp['scale']} · routes in use in "
                                                   f"{month_label(pp['month'])}.")
    else:
        D.todo("a regional plan (1:15,000 or smaller), a local plan (1:2,000 to 1:3,000) and a site plan (1:500 to 1:1,000) "
               "with the routes, the gates and the places that need care.", "2.2")
    D.todo("consolidation centres, the nearest wharf, and areas where lorries could be marshalled.", "2.2")
    D.h("2.3 Local access including highway, public transport, cycling, walking and waterways", 2)
    C = L.get("community") or {}
    strip_words = (f"within {C.get('route_m', 250)} m of this plan's routes or {C.get('site_m', 500)} m of "
                   f"{sites_word}")
    D.h("2.3.1 Highways, carriageways and footways", 3)
    if L.get("councils"):
        D.p(f"The routes run through these councils in {month_label(L['councils_month'])}, the busiest month:")
        D.table(["Council", "Highway authority", "Routes"],
                [[f"{c['name']} ({c['tier']})" if c["tier"] else c["name"], c["highway_authority"] or "—",
                  ", ".join(c["routes"]) or "the site only"] for c in L["councils"]], widths=[6, 6, 5])
    lim = L.get("limits") or {}
    if lim.get("checked"):
        if lim["rows"]:
            vw = {"exceeds": "over the limit", "at_limit": "at the limit", "unknown": "to be checked"}
            D.p("Signed and mapped lorry limits on the routes that need a look:")
            D.table(["Limit", "Lorry", "Routes"],
                    [[e["what"], f"{', '.join(e['lorries']) or 'all'}: {vw[e['verdict']]}", ", ".join(e["routes"])]
                     for e in lim["rows"]], widths=[8, 5, 4])
        w = lim["within"]
        D.p(f"{n(w)} other lorry limit{'s' if w != 1 else ''} on the routes {'are' if w != 1 else 'is'} within every "
            "lorry's size and weight." if w else "No other lorry limits are recorded on the routes.")
        D.src("Lorry limits as last checked in Wayscope: a planning check from mapped and signed limits, not a survey.")
    cl = L.get("closures") or {}
    if cl.get("checked"):
        if cl["rows"]:
            D.bullets([f"{e['what']} ({', '.join(e['routes'])})" for e in cl["rows"]])
        else:
            D.p("No National Highways closures on the routes when last checked.")
        D.src(f"National Highways closures, last checked {str(cl['checked_at'])[:10]}.")
    if L.get("diversions"):
        D.p("Dated diversions round a closure or works on these routes:")
        D.table(["Route", "Round", "From", "To"],
                [[g["route_id"], ", ".join(g["zones"]) or "a closed area", _date_words(g["from"]), _date_words(g["to"])]
                 for g in L["diversions"]], widths=[2, 8, 3.5, 3.5])
    D.todo("Traffic Regulation Orders needed, suspensions, and roads or footways that need extra care.", "2.3.1")
    D.h("2.3.2 Railway / underground", 3)
    if C.get("stations"):
        D.p(f"Stations and tram stops {strip_words}: " + ", ".join(
            f"{x['name'] or 'unnamed'} ({n(x['metres'])} m from {x['where']})" for x in C["stations"]) + ".")
    D.todo("railway lines and bridges near the site or its routes, and the precautions taken.", "2.3.2")
    D.h("2.3.3 Bus routes", 3)
    if C.get("stored"):
        D.p(f"{n(C['bus_stops'])} bus stop{'s' if C['bus_stops'] != 1 else ''} {strip_words}"
            # 31 Oct 2026 (PR 3a): "0 of them nearest this site" read oddly (live L019) — the clause only when some are
            + (f", {n(C['bus_stops_near_sites'])} of them nearer {sites_word} than any route." if C["bus_stops_near_sites"] else "."))
    D.todo("the bus routes affected, and the precautions taken.", "2.3.3")
    D.h("2.3.4 Cycling", 3)
    if C.get("stored"):
        if C["cycle"] or C["cycle_unnamed"]:
            D.p(f"Cycle routes {strip_words}: " + ", ".join(C["cycle"] + (
                [f"{n(C['cycle_unnamed'])} unnamed cycle path{'s' if C['cycle_unnamed'] != 1 else ''}"]
                if C["cycle_unnamed"] else [])) + ".")
        else:
            D.p(f"No cycle routes recorded {strip_words}.")
    D.todo("precautions for people cycling (crossings, marshals, signs).", "2.3.4")
    D.h("2.3.5 Waterways", 3)
    D.todo("waterways near the site, and the precautions taken.", "2.3.5")
    if C.get("credit"):
        D.src(C["credit"])
    D.h("2.4 Community considerations", 2)
    D.h("2.4.1 Local policy", 3)
    if L.get("councils"):
        for c in L["councils"]:
            D.todo(f"{c['name']}: the code of construction practice or local rule this plan follows.", "2.4.1")
    else:
        D.todo("each council's code of construction practice or local rule this plan follows.", "2.4.1")
    D.h("2.4.2 Schools, hospitals and other sensitive places", 3)
    if C.get("stored"):
        labels = C["labels"]
        unnamed = C.get("places_unnamed") or []
        if C["places"] or unnamed:
            if C["places"]:
                D.p(f"Places {strip_words}: schools, hospitals and health centres first, then the others, each nearest "
                    "first:")
                D.table(["Place", "What", "Nearest", "Metres"],
                        [[x["name"], labels.get(x["kind"], x["kind"]), x["where"], n(x["metres"])]
                         for x in C["places"]], widths=[6.5, 4, 4.5, 2], numeric=(3,))
            if C["places_more"]:
                D.p(f"{n(C['places_more'])} more named place{'s' if C['places_more'] != 1 else ''} further away.")
            if unnamed:
                D.p("With no name on the map: " + ", ".join(
                    f"{n(u['count'])} {_unnamed_word(u)}" for u in unnamed) + ".")
        else:
            D.p(f"No schools, hospitals, health or community centres or sports facilities recorded {strip_words}.")
        if C["residential"]:
            D.p(f"{n(C['residential'])} residential area{'s' if C['residential'] != 1 else ''} {strip_words}.")
        if C.get("credit"):
            D.src(C["credit"])
    co = L.get("collisions") or {}
    if co.get("fetched") and co["rows"]:
        D.p(f"Injury collisions reported to the police, {co['period']}:")
        D.table(["Route", "On the route", "Killed or seriously injured", "Within 250 m",
                 "A person on foot, cycle or motorcycle hurt", "A goods vehicle over 3.5 t involved"],
                [[r["route_id"], n(r["on_all"]), n(r["on_ksi"]), n(r["near_all"]), n(r["near_vru"]), n(r["near_goods"])]
                 for r in co["rows"]], widths=[1.8, 2.4, 3.2, 2.4, 4, 3.2], numeric=(1, 2, 3, 4, 5))
        for sc in co["sites"]:
            D.p(f"Within 500 m of {sc['name']}: {n(sc['all'])} collision{'s' if sc['all'] != 1 else ''}, "
                f"{n(sc['ksi'])} killed or seriously injured.")
        D.src("Counts, not a rate: the traffic on each road is not the same. Each route's collision evidence sheet "
              "gives the detail. " + co["credit"])
    D.todo("how lorries will be managed near these places (times, speeds, marshals, signs).", "2.4.2")

    # ---------------------------------------------------------------- 3
    D.h("3 Construction programme and methodology", 1)
    D.todo("the programme for this site in a few sentences.", "3")
    D.p("Each stage below is made of Wayscope disciplines. A stage's dates are the first and last months with approved "
        "lorry loads in its disciplines.")
    D.table(["Stage", "Wayscope disciplines", "Start", "End", "Loads"],
            [[f"{s['number']} {s['name']}", ", ".join(s["discipline_labels"]) or "—",
              month_label(s["first"]) if s["first"] else "No lorry loads in Wayscope", month_label(s["last"]) if s["last"] else "",
              n(s["trips_total"]) if s["trips_total"] else ""] for s in d["stages"]],
            widths=[6, 4.5, 2.5, 2.5, 1.5], numeric=(4,))
    D.src("From the approved plan.")
    if pictures:
        ch = PIC.programme_chart(d)
        if ch:
            D.picture(ch["png"], 17.0, ch["alt"], "The construction programme at " + sites_word + ".")
    other = "3.1 (stages of a building programme)" if d["programme"] == "infrastructure" else \
        "3.2 (stages of an infrastructure programme)"
    D.p(f"{other} is left out: this programme is set as {d['programme']}.", italic=True)
    D.h(f"{d['prefix']} {'Infrastructure' if d['programme'] == 'infrastructure' else 'Construction'} programme phases", 2)
    for s in d["stages"]:
        D.h(f"{s['number']} {s['name']}", 3)
        if not s["first"]:
            D.p("No lorry loads in Wayscope for this stage at " + sites_word + ".")
            D.todo("if this stage happens here, what it involves and the vehicles it needs.", f"{s['number']} {s['name']}")
            continue
        mats = "; ".join(f"{m['material']} {n(round(m['tonnes']))} t" for m in s["materials"])
        veh = ", ".join(v["label"] for v in s["vehicles"])
        D.p(f"{period_words(s['first'], s['last'])} · {n(s['trips_total'])} loads · {mats}. Busiest "
            f"{month_label(s['peak_month'])}: {n(s['peak_trips'])} loads ({s['peak_daily']:g} a day), on {veh}. "
            f"Routes: {', '.join(s['routes'])}.")
        D.todo("the plant used and the works in this stage.", f"{s['number']} {s['name']}")

    # ---------------------------------------------------------------- 4
    D.h("4 Vehicle routing and site access", 1)
    D.h("Routes to and from " + sites_word, 2)
    if d["routes"]:
        dist_head = "Miles" if d["unit"] == "mi" else "Km"
        D.table(["Route", "From → to", dist_head, "Lorry", "Months", "Loads"],
                [[r["route_id"], f"{r['from']} → {r['to']}", (n(r["distance"]) if r["distance"] is not None else "not drawn"),
                  ", ".join(r["vehicles"]), period_words(r["first"], r["last"]), n(r["trips"])] for r in d["routes"]],
                widths=[1.5, 6, 1.5, 4, 3.5, 1.5], numeric=(2, 5))
        if T["between"]:
            D.p(f"{n(T['between'])} loads run between sites in this plan; they are counted once.")
        D.src("Each route is the lorry route for its vehicle's size and weight. Each route has a driver route sheet.")
    else:
        D.p("No approved routes to or from " + sites_word + ".")
    for s in d["sites"]:
        D.h(f"Gates at {s['name']}", 2)
        if s["gates"]:
            D.table(["Gate", "Use", "Open", "Check-in", "Lorries a day it can check in", "Notes"],
                    [[g["name"], g["direction"], f"{g['days']} {g['hours']}" + (
                        f", not {d['peak_band_words']}" if d["peak_band_words"] else "") + (
                        f", shut {g['shut']}" if g["shut"] else ""),
                      (f"{g['check_in']:g} min" if g["check_in"] is not None else "not typed"),
                      (n(g["capacity"]) if g["capacity"] is not None else "—"),
                      "; ".join(x for x in (g["closed"], g["note"]) if x) or ""] for g in s["gates"]],
                    widths=[3, 1.6, 4.4, 1.8, 2.2, 4], numeric=(4,))
            if any(g["access_road"] for g in s["gates"]):
                D.p("Each gate with an access road is reached by its own road from the public road.")
        else:
            D.p("No gates recorded for this location.")
        bits = []
        if s["site_speed_kph"]:
            bits.append(f"Site speed {s['site_speed_kph']:g} km/h ({s['site_speed_kph'] / 1.609344:.0f} mph).")
        if s["site_rules"]:
            bits.append(s["site_rules"])
        if bits:
            D.p(" ".join(bits))
        if s["areas"]:
            D.table(["Area", "Activity", "Bays", "Minutes a lorry", "Level"],
                    [[a["name"], a["activity"], n(a["bays"]), (f"{a['minutes']:g}" if a["minutes"] is not None else "—"),
                      a["level"] or ""] for a in s["areas"]], widths=[5, 3, 1.5, 3, 4.5], numeric=(2, 3))
        # 31 Oct 2026 (4c PR 5): the site's layout phase in force in its busiest month (the month its site plan shows)
        LY = site_layout_paper.for_plan(s["id"], PIC._site_month(d, s["id"]) or T["peak_month"])             if T.get("peak_month") else None
        if LY and LY["things"]:
            where = " is drawn on its site plan in 2.2" if pictures else ""
            D.p(f"The site layout for {s['name']}{where}: phase {LY['phase']}, {_lower_lead(LY['months'])}.")
        else:
            D.todo(f"No site layout drawn for {s['name']}. Draw one on Locations, or attach the contractor's drawing.", "4")
    D.src("From Data → Locations: gates, their hours and the work areas.")
    if any(pp["site"] for pp in plan_pics):
        D.p("The local and site plans of each site are in 2.2.")
    D.todo("hoarding lines and gates for vehicles, people on foot and cycles; routes for people on foot and on cycles "
           "into and around the site; changes to roads and footways; swept paths; crane positions; where conflicts could "
           "happen and where marshals stand; parking, loading and unloading.", "4")

    # ---------------------------------------------------------------- 5
    D.h("5 Strategies to reduce impacts", 1)
    D.p(f"{'Higher' if impact == 'higher' else 'Medium'} impact site: planned measures. Wayscope ticked a row only where "
        "the approved plan already does it, with the evidence under the row. Change any tick before signing.")
    head = [f"{'Higher' if impact == 'higher' else 'Medium'} impact site planned measures", "Committed", "Proposed", "Considered"]
    t = D.table(head, [], widths=[9.6, 2.5, 2.5, 2.4])
    for group, rows in MEASURES:
        c = t.add_row().cells
        c[0].text = group
        c[0].paragraphs[0].runs[0].bold = True
        for row in rows:
            ev = d["measures"].get(row)
            c = t.add_row().cells
            c[0].text = row
            if ev:
                pe = c[0].add_paragraph(style=SOURCE_STYLE)
                pe.add_run("Evidence: " + ev["evidence"])
                if ev["tick"]:
                    c[1].text = "✔"
                    c[1].paragraphs[0].alignment = 1
    D.p(STAR_NOTE)
    for group, rows in MEASURES:
        D.h(f"{_group_no(group)} {group}", 3)
        for row in rows:
            D.p(row.rstrip("*"), bold=True)
            ev = d["measures"].get(row)
            if ev:
                D.p(ev["evidence"])
            D.todo("how this measure will be carried out here, or why it is not used.",
                   f"{_group_no(group)} {row.rstrip('*')}")

    # ---------------------------------------------------------------- 6
    D.h("6 Estimated vehicle movements", 1)
    D.p(f"One trip is one lorry visit to {sites_word} (in and out), loaded either way. A day is the busiest month's trips "
        f"÷ {wd:g} working days.")
    D.h("Estimated construction vehicles: monthly and daily", 3)
    rows = []
    for s in d["stages"]:
        if s["first"]:
            rows.append([s["name"], period_words(s["first"], s["last"], quarters=True),
                         f"{n(s['peak_trips'])} ({month_label(s['peak_month'])})", f"{s['peak_daily']:g}"])
        else:
            rows.append([s["name"], "No lorry loads in Wayscope", "", ""])
    if T["peak_month"]:
        rows.append(["Peak period of construction", month_label(T["peak_month"]), n(T["peak_trips"]), f"{T['peak_daily']:g}"])
    D.table(["Construction stage", "Period of stage", "No. of trips (busiest month)", "Peak no. of trips (daily)"], rows,
            widths=[6, 4, 4, 3], numeric=(2, 3))
    D.src(f"From the approved plan: {n(T['trips'])} trips" + (f", {period_words(T['first'], T['last'])}." if T["first"] else "."))
    if pictures:
        ch = PIC.monthly_chart(d)
        if ch:
            D.picture(ch["png"], 17.0, ch["alt"], "Trips a month by stage; the right-hand scale is the same trips a day.")
    if T["pending_lines"]:
        D.p(f"{T['pending_lines']} line{'s' if T['pending_lines'] != 1 else ''} waiting for approval "
            f"{'are' if T['pending_lines'] != 1 else 'is'} not in these figures.", italic=True)
    D.h("Number and vehicle type in each stage's busiest month", 3)
    vrows = []
    for s in d["stages"]:
        for v in s["vehicles"]:
            vrows.append([f"{s['name']} ({month_label(s['peak_month'])})", v["label"],
                          (f"{v['gvw_t']:g} t" if v["gvw_t"] is not None else "not typed"), v["band"], n(v["trips"])])
    if vrows:
        D.table(["Stage (busiest month)", "Lorry type", "Gross weight", "Weight band", "Trips"], vrows,
                widths=[5, 4.5, 2.2, 3, 2], numeric=(4,))
        D.src("Weight bands from each lorry type's gross weight: 3.5 t and under, 3.5 t to 7.5 t, over 7.5 t.")
    D.h("Hourly arrival profile of vehicles during peak", 3)
    if d["hourly"]:
        for h in d["hourly"]:
            open_rows = [x for x in h["per_hour"] if x["open_minutes"] > 0]
            split = ", ".join(x for x in ((f"{h['laden_per_day']:g} loaded" if h["laden_per_day"] else ""),
                                         (f"{h['empty_per_day']:g} coming to load" if h["empty_per_day"] else "")) if x)
            D.p(f"{h['gate']}, {h['site']}, {month_label(h['month'])} (its busiest month): {h['arrivals_per_day']:g} "
                f"{TEAM_LORRIES if h.get('all_teams_pct') else 'lorries'} a day ({split}), open {h['hours']}.")
            if pictures:
                ch = PIC.hourly_chart(h)
                if ch:
                    D.picture(ch["png"], 17.0, ch["alt"])
            D.table(["Hour", "Lorries arriving", "Minutes between arrivals"],
                    [[f"{x['hour']:02d}:00–{x['hour'] + 1:02d}:00", f"{x['lorries']:g}",
                      (f"{x['minutes_between']:g}" if x["minutes_between"] is not None else "—")] for x in open_rows],
                    widths=[4, 4, 5], numeric=(1, 2))
        D.src("The plan's arrivals spread evenly over each gate's open hours, less the no-delivery bands and its shut "
              "times. It is the plan's spread, not a count.")
    else:
        D.p("No gate arrivals in Wayscope for the busiest month.")
    D.todo("if arrivals will not be spread evenly, the planned arrivals in each hour.", "6")

    # ---------------------------------------------------------------- 7
    D.h("7 Implementing, monitoring and updating", 1)
    D.p("What Wayscope keeps for " + sites_word + ", month by month:")
    D.bullets([
        "Lorry visits a day against each site's CLP cap.",
        "Trips by lorry type and by Euro class; carbon per tonne against the scheme's target; trips avoided by the agreed "
        "decisions.",
        "Each confirmed week: the planned quantities, and the quantities recorded as delivered.",
        "Each gate's planned arrivals against its capacity (\"Queue likely\" from 85 %, \"Over gate capacity\" over 100 %).",
    ])
    caps = [f"{s['name']}: {s['clp_cap']:g} lorry visits a day" for s in d["sites"] if s["clp_cap"] is not None]
    if caps:
        D.p("CLP caps typed in Wayscope: " + "; ".join(caps) + ".")
    no_cap = [s["name"] for s in d["sites"] if s["clp_cap"] is None]
    if no_cap:
        D.todo(f"a CLP cap (lorry visits a day) for {', '.join(no_cap)}, if one is agreed. Typed on Data → Locations, it "
               "fills the next copy.", "7")
    D.src("From CLP monitoring and Gate arrivals. The CLP pack prints them for any month.")
    D.todo("how this plan is put in place on site, who checks it and how often, how complaints are taken and answered, "
           "and when the plan is reviewed.", "7")

    # the Still to complete list, now every placeholder is known: inserted before the Contents heading
    data["todos"] = list(D.todos)   # 31 Oct 2026 (PR 3b): kept after the build, so a task can start from a line
    for item in D.todos:
        anchor.insert_paragraph_before(item, style="List Number")
    anchor._p.getparent().remove(anchor._p)
    D.update_fields_on_open()
    D.d.core_properties.title = f"Construction Logistics Plan: {title}"
    D.d.core_properties.author = "Wayscope"
    out = io.BytesIO()
    D.d.save(out)
    return out.getvalue()


TEAM_LORRIES = "of this team's lorries"
#: 31 Oct 2026 (PR 3a): the cover details a CLP record holds, in the order the page and the cover print them
COVER_FIELDS = (("address", "Site address"), ("postcode", "Postcode"), ("landowner", "Landowner"),
                ("site_use", "Existing site use"), ("summary", "Summary of works"),
                ("manager_name", "Logistics manager"), ("manager_phone", "Logistics manager's phone"),
                ("manager_email", "Logistics manager's email"),
                ("provider_name", "Logistics provider"), ("provider_phone", "Logistics provider's phone"),
                ("provider_email", "Logistics provider's email"))


def contact_words(cover, who):
    """'A. Example · 07700 900123 · a@example.com' from the typed parts, or '' when none is typed."""
    return " · ".join(x for x in (str((cover or {}).get(f"{who}_{k}") or "").strip() for k in ("name", "phone", "email")) if x)


def _unnamed_word(u):
    import clp_doc_layers
    one, many = clp_doc_layers.UNNAMED_WORDS.get(u["kind"], (u["kind"], u["kind"]))
    return one if u["count"] == 1 else many


def _date_words(v):
    """'2027-12-20' -> '20 Dec 2027'; anything else as it is."""
    try:
        dt = datetime.date.fromisoformat(str(v)[:10])
        return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"
    except (TypeError, ValueError):
        return str(v or "")


def _group_no(group):
    return {"Measures influencing construction vehicles and deliveries": "5.1.1",
            "Measures to encourage sustainable freight": "5.1.2", "Material procurement measures": "5.1.3",
            "Other measures": "5.1.4"}[group]


# --------------------------------------------------------------------------- #
#  OS grid reference (OSGB36), for the cover                                   #
# --------------------------------------------------------------------------- #
def os_grid(lat, lon):
    """(easting, northing) on the OS National Grid for a WGS84 point: a Helmert shift to OSGB36, then the transverse
    Mercator projection (the Ordnance Survey's own formulae, 'A guide to coordinate systems in Great Britain'). Good to a
    few metres, which is all a cover needs. None outside Great Britain's grid."""
    import math
    if lat is None or lon is None:
        return None
    a, b = 6378137.0, 6356752.314245
    e2 = 1 - (b * b) / (a * a)
    phi, lam = math.radians(float(lat)), math.radians(float(lon))
    nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    x = nu * math.cos(phi) * math.cos(lam)
    y = nu * math.cos(phi) * math.sin(lam)
    z = (1 - e2) * nu * math.sin(phi)
    tx, ty, tz, s = -446.448, 125.157, -542.060, 20.4894e-6
    rx, ry, rz = [math.radians(v / 3600) for v in (-0.1502, -0.2470, -0.8421)]
    x2 = tx + (1 + s) * x - rz * y + ry * z
    y2 = ty + rz * x + (1 + s) * y - rx * z
    z2 = tz - ry * x + rx * y + (1 + s) * z
    a, b = 6377563.396, 6356256.909
    e2 = 1 - (b * b) / (a * a)
    p = math.sqrt(x2 * x2 + y2 * y2)
    phi = math.atan2(z2, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z2 + e2 * nu * math.sin(phi), p)
    lam = math.atan2(y2, x2)
    F0, phi0, lam0, N0, E0 = 0.9996012717, math.radians(49), math.radians(-2), -100000, 400000
    n_ = (a - b) / (a + b)
    nu = a * F0 * (1 - e2 * math.sin(phi) ** 2) ** -0.5
    rho = a * F0 * (1 - e2) * (1 - e2 * math.sin(phi) ** 2) ** -1.5
    eta2 = nu / rho - 1
    M = b * F0 * ((1 + n_ + 5 / 4 * n_ ** 2 + 5 / 4 * n_ ** 3) * (phi - phi0)
                  - (3 * n_ + 3 * n_ ** 2 + 21 / 8 * n_ ** 3) * math.sin(phi - phi0) * math.cos(phi + phi0)
                  + (15 / 8 * n_ ** 2 + 15 / 8 * n_ ** 3) * math.sin(2 * (phi - phi0)) * math.cos(2 * (phi + phi0))
                  - 35 / 24 * n_ ** 3 * math.sin(3 * (phi - phi0)) * math.cos(3 * (phi + phi0)))
    sp, cp, tp = math.sin(phi), math.cos(phi), math.tan(phi)
    I = M + N0
    II = nu / 2 * sp * cp
    III = nu / 24 * sp * cp ** 3 * (5 - tp ** 2 + 9 * eta2)
    IIIA = nu / 720 * sp * cp ** 5 * (61 - 58 * tp ** 2 + tp ** 4)
    IV = nu * cp
    V = nu / 6 * cp ** 3 * (nu / rho - tp ** 2)
    VI = nu / 120 * cp ** 5 * (5 - 18 * tp ** 2 + tp ** 4 + 14 * eta2 - 58 * tp ** 2 * eta2)
    dl = lam - lam0
    N = I + II * dl ** 2 + III * dl ** 4 + IIIA * dl ** 6
    E = E0 + IV * dl + V * dl ** 3 + VI * dl ** 5
    if not (0 <= E < 700000 and 0 <= N < 1300000):
        return None
    return E, N


def grid_ref(lat, lon, digits=6):
    """'SK 757 058' (6 figures, 100 m) for a WGS84 point in Great Britain, else None."""
    en = os_grid(lat, lon)
    if not en:
        return None
    E, N = en
    e100, n100 = int(E // 100000), int(N // 100000)
    l1 = (19 - n100) - (19 - n100) % 5 + (e100 + 10) // 5
    l2 = (19 - n100) * 5 % 25 + e100 % 5
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"     # no I
    half = digits // 2
    e = int(E % 100000) // 10 ** (5 - half)
    n_ = int(N % 100000) // 10 ** (5 - half)
    return f"{letters[l1]}{letters[l2]} {e:0{half}d} {n_:0{half}d}"


def _grid_words(lat, lon):
    g = grid_ref(lat, lon)
    ll = f"{abs(float(lat)):.4f}° {'N' if float(lat) >= 0 else 'S'}, {abs(float(lon)):.4f}° {'E' if float(lon) >= 0 else 'W'}" \
        if lat is not None and lon is not None else "no position"
    return f"{ll} · OS grid reference {g}" if g else ll
