"""
route_sheet.py — the route sheet for drivers (CLOCS v5 C3, 16 Oct 2026; notes/clocs-v5-gap-1016.md).

WHAT IT IS
----------
ONE A4 portrait page per route, for the hauliers and drivers who run it — the CLOCS Standard v5 asks the principal
contractor to "distribute maps or other routing information to all operators accessing the site" (§5.6c), to
communicate "routes and site rules to the operator" (§5.5a.v), the permitted deviations (§5.6d), the reasons for the
route (§5.6f) and "route information upon egress from site" (§5.6g), and to define the "last mile" (§5.2b.iii).

    the whole route        the loaded leg (green) and the empty return (amber), solid with a white edge, each left of its
                           travel, a stretch on a haul road dotted and thinner, on a basemap, A = load point, B = site
    the last mile          the last ~1.5 km into the site and the first ~1.5 km out, with the community considerations
    arriving / leaving     the gate in, its open hours and closed days, the scheme's no-delivery windows; the gate out
    the typed words        why this route, the permitted diversions (routes), the site rules (locations) — C2 / C3
    lorry limits           the stored lorry-limits check for this vehicle (limits.py): the limits it is over, or none

It prints what the scheme typed and what Wayscope stored, and says so where a field is empty ("Not typed"). It never
writes an instruction of its own: no invented speed, phone number or rule. Reads only; stores nothing.

    S = sheet(route_id, vehicle=None, now=None)        export.build_route_sheet_pdf(S)
"""
import datetime
import json
import math

#: the page (A4 portrait, mm) and its two maps
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
MARGIN_MM = 10.0
MAP1_W_MM, MAP1_H_MM = PAGE_W_MM - 2 * MARGIN_MM, 80.0          # the whole route, full width
MAP2_W_MM, MAP2_H_MM = 96.0, 70.0                               # the last mile, left half
PX_PER_MM = 1280 / MAP1_W_MM                                    # basemap.MAX_PX across the widest map
LAST_MILE_M = 1500.0                                            # how far along each leg the last mile reaches
# 16 Oct 2026 (the user): a gate is by the public road, a bellmouth for one or two lorries in from it (2 × 16.5 m). With
# its access road drawn, a stored route ENDS at the gate; a leg ending further than this from its gate is noted.
GATE_FAR_M = 50.0

NOT_TYPED = "Not typed"


class SheetError(LookupError):
    """No such route (for this tenant, or for this team code)."""


def _haversine_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, h)))


def within(coords, metres, from_end=False):
    """The part of a polyline within `metres` (along the line) of its start — or of its end with from_end."""
    pts = list(reversed(coords)) if from_end else list(coords)
    if not pts:
        return []
    out, run = [pts[0]], 0.0
    for p in pts[1:]:
        run += _haversine_m(out[-1], p)
        out.append(p)
        if run >= metres:
            break
    return list(reversed(out)) if from_end else out


def _coords(geometry_json):
    try:
        g = json.loads(geometry_json) if isinstance(geometry_json, str) else geometry_json
    except (TypeError, ValueError):
        return []
    g = g.get("coordinates") if isinstance(g, dict) else g
    out = []
    for c in g or []:
        try:
            out.append((float(c[0]), float(c[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _gate_words(loc, role, gate_id, gate_list, factors=None):
    """{name, hours, default_hours, shut, closed, source} for the gate a leg uses at one end (gates.resolve, the bake's
    own rule). `hours` only when typed on the gate; a gate row with none typed carries `default_hours` (17 Oct 2026),
    which the sheet prints as the default, never as the gate's own. `shut` = the gate's shut windows in words."""
    import gates
    import gate_hours
    r = gates.resolve(loc, role, gate_id, gates=gate_list)
    g = next((x for x in gate_list or [] if x["id"] == r.get("gate_id")), None)
    w = gate_hours.window_of(g) if g else None
    return {
        "name": r.get("gate_name") or ("the site's access point" if r.get("source") == "legacy_pair" else None),
        "hours": f"{g['open_from'].strip()}–{g['open_to'].strip()}" if w else None,
        "default_hours": (gate_hours.default_words(factors) if (g and not w and factors is not None) else None),
        "shut": gate_hours.peak_words(gate_hours.shut_windows(g)) if g else None,
        "closed": gate_hours.closed_days_words(g) if g else None,
        "at": (r["lon"], r["lat"]),
        "source": r.get("source"),
        "access_zone_id": (g or {}).get("access_zone_id"),
    }


def _limits_words(route_id, profile, vehicle_text, alts=(0,)):
    """The stored lorry-limits check for this route and vehicle, in words: (status, [lines]).
    28 Oct 2026 (task 0c): `alts` = the stored options this page draws — page 1 the main line (0), a diversion page its
    own options; a limit on a diversion is not the main route's (limits.check_route tags it with alt_index)."""
    import limits
    st = dict((limits.stored_checks([route_id]) or {}).get(route_id) or {})
    st["hits"] = [h for h in st.get("hits") or [] if isinstance(h, dict) and int(h.get("alt_index") or 0) in set(alts)]
    if not st.get("checked_at"):
        return "not_checked", ["Not checked yet on this route. Follow the road signs."]
    when = str(st["checked_at"])[:10]
    if str(st.get("status") or "").startswith("error"):
        return "not_checked", [f"The last check ({when}) did not finish. Follow the road signs."]
    mine = [h for h in st.get("hits") or [] if isinstance(h, dict) and h.get("vehicle_profile") == profile]
    over = limits.exceeding(st, profile)
    if over:
        lines = [limits.breach_text([h], profile) for h in over[:3]]
        if len(over) > 3:
            lines.append(f"+{len(over) - 3} more")
        lines.append(f"Checked {when}. Ask the site team before running this vehicle on this route.")
        return "over", lines
    look = [h for h in mine if h.get("verdict") in ("at_limit", "unknown")]
    if look:
        words = {"at_limit": "at the limit for this lorry", "unknown": "not known for this lorry"}
        lines = [f"{h.get('headline')}: {words[h['verdict']]}" for h in look[:3]]
        if len(look) > 3:
            lines.append(f"+{len(look) - 3} more")
        lines.append(f"None is below the {vehicle_text} (checked {when}). The signs on the road come first.")
        return "look", lines
    n = len(mine)
    first = (f"None of the {n} stored weight, height or width limits along this route is below the {vehicle_text}"
             if n else "No stored weight, height or width limit along this route")
    return "clear", [f"{first} (checked {when}). The signs on the road come first."]


def sheet(route_id, vehicle=None, now=None, acc=None):
    """
    Everything one route sheet prints, as data. `vehicle` picks which baked vehicle's road route is drawn (a route is
    baked per vehicle and they can differ); without one, the public map's rule: the default lorry where it is baked,
    else the first baked. A team code (acc with an ipt) reads its own team's routes only: SheetError otherwise.
    """
    import db
    import network
    import gates
    import gate_hours
    import conversions
    import export
    import bulletin_doc
    tenant = db.current_tenant()
    rows = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (tenant, route_id))
    if not rows:
        raise SheetError(f"no route {route_id}")
    r = rows[0]
    own = (acc or {}).get("ipt") if isinstance(acc, dict) else None
    if own:
        import access
        if (access.canonical_ipt(r.get("ipt")) or r.get("ipt")) != (access.canonical_ipt(own) or own):
            raise SheetError(f"no route {route_id}")
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ? AND id IN (?, ?)",
                                         (tenant, r["origin_id"], r["dest_id"]))}
    o, d = locs.get(r["origin_id"]) or {}, locs.get(r["dest_id"]) or {}
    gbl = gates.gates_by_location(include_inactive=True)

    geo = {}
    for g in db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND alt_index = 0",
                      (tenant, route_id)):
        if g.get("geometry"):
            geo.setdefault(g["vehicle_profile"], {})[g["leg"]] = g
    baked = sorted(geo)
    if vehicle and vehicle in geo:
        used = vehicle
    elif network.DEFAULT_PROFILE in geo:
        used = network.DEFAULT_PROFILE
    else:
        used = baked[0] if baked else None
    legs = geo.get(used) or {}
    loaded = _coords(legs["loaded"]["geometry"]) if legs.get("loaded") else []
    ret = _coords(legs["return"]["geometry"]) if legs.get("return") else []

    factors = conversions.load_factors()
    vehicle_text = conversions.vehicle_label(factors, used) if used else None
    du = export._du()

    def leg_words(g):
        if not g or g.get("distance_km") is None:
            return None
        km = float(g["distance_km"])
        out = f"{export._dist(km):.1f} {du}"
        if g.get("duration_hr"):
            m = int(round(float(g["duration_hr"]) * 60))
            out += f", about {m // 60} h {m % 60:02d} min driving" if m >= 60 else f", about {m} min driving"
        return out

    entry = _gate_words(d, "entry", r.get("dest_gate_id"), gbl.get(r["dest_id"]), factors)
    exit_site = _gate_words(d, "exit", r.get("dest_gate_id"), gbl.get(r["dest_id"]), factors)
    # Each gate is drawn where it is typed. With the gate's access road drawn (a haul road from the public road to the
    # gate, network._bake_leg splices it), a stored route ends AT the gate. A leg ending further than GATE_FAR_M from its
    # gate has no access road to follow, or was worked out before the gate or its road was placed; the sheet says so in
    # metres and says which (16 Oct 2026: on the local demo copy, before the access roads, the legs ended 84-685 m off).
    entry["gap_m"] = round(_haversine_m(entry["at"], loaded[-1])) if loaded else None
    exit_site["gap_m"] = round(_haversine_m(exit_site["at"], ret[0])) if ret else None
    # one gate both ways (a gate with direction "both"): drawn once, named once
    same_gate = bool(entry.get("at") and entry.get("at") == exit_site.get("at"))
    far = [(g, leg) for g, leg in ((entry, "loaded"), (exit_site, "return"))
           if g.get("gap_m") is not None and g["gap_m"] > GATE_FAR_M and g.get("name")]
    gate_notes = []
    def fix(g):
        return ("work the route out again (the gate or its access road has moved since)" if g.get("access_zone_id")
                else "draw the gate's access road from the public road, then work the route out again")
    if same_gate and len(far) == 2 and far[0][0]["gap_m"] == far[1][0]["gap_m"]:
        gate_notes.append(f"The route on file ends and starts {entry['gap_m']:,} m from {entry['name']}: {fix(entry)}.")
    else:
        for g, leg in far:
            gate_notes.append(f"The {leg} route on file {'ends' if leg == 'loaded' else 'starts'} {g['gap_m']:,} m from "
                              f"{g['name']}: {fix(g)}.")
    load_exit = _gate_words(o, "exit", r.get("origin_gate_id"), gbl.get(r["origin_id"]))
    # 17 Oct 2026 (review): the gate a lorry comes IN by to load at A — the gate the Dashboard and the Simulation time the
    # empty arrival against — with its hours (or the default, said so), closed days and shut times
    load_entry = _gate_words(o, "entry", r.get("origin_gate_id"), gbl.get(r["origin_id"]), factors)
    bands = gate_hours.peak_bands(factors)
    lim_status, lim_lines = _limits_words(route_id, used, vehicle_text) if used else ("not_checked", [
        "No road route has been worked out for this route yet."])

    try:
        import taxonomy
        team = taxonomy.team_text(r.get("ipt")) if r.get("ipt") else None
    except Exception:
        team = r.get("ipt")
    notice = export._demo_notice() or None
    as_at = (now or datetime.date.today())
    roads = _haul_roads()
    last_in, last_out = within(loaded, LAST_MILE_M, from_end=True), within(ret, LAST_MILE_M)
    return {
        "route_id": route_id,
        "title": "Route sheet",
        "tenant": export._tenant_name() or "Wayscope",
        "demo_notice": notice, "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "origin": o.get("name") or r["origin_id"], "dest": d.get("name") or r["dest_id"],
        "team": team, "material": r.get("material_category") or None,
        "vehicle": used, "vehicle_text": vehicle_text, "baked_vehicles": baked,
        "loaded": loaded, "return": ret,
        "loaded_words": leg_words(legs.get("loaded")), "return_words": leg_words(legs.get("return")),
        "last_mile_in": last_in,
        "last_mile_out": last_out,
        "haul_loaded": haul_pieces(loaded, roads), "haul_return": haul_pieces(ret, roads),
        "haul_last_in": haul_pieces(last_in, roads), "haul_last_out": haul_pieces(last_out, roads),
        "last_mile_m": LAST_MILE_M,
        "load_exit": load_exit, "load_entry": load_entry, "entry": entry, "exit": exit_site,
        "peak_words": gate_hours.peak_words(bands),
        "gate_notes": gate_notes, "same_gate": same_gate,
        "route_reason": r.get("route_reason"), "permitted_deviations": r.get("permitted_deviations"),
        "site_rules_dest": d.get("site_rules"), "site_rules_origin": o.get("site_rules"),
        "limits_status": lim_status, "limits_lines": lim_lines,
        "issued": f"{as_at:%d %b %Y}".lstrip("0"),
        "drawn": bool(loaded),
        # 28 Oct 2026 (task 0c, the user's Q6): one more page per diversion, in date order
        "diversions": _diversions(route_id, used, legs, leg_words, vehicle_text) if used else [],
    }


def _diversions(route_id, used, legs, leg_words, vehicle_text):
    """The dated zones' diversions of this route for the lorry drawn, one entry per run of dates: the line of each leg
    (the diversion's, or the main one where that leg is not diverted), the words, why, and the day it goes back."""
    import db
    import route_choice
    import zones
    tenant = db.current_tenant()
    rows = [r for r in route_choice._all_rows() if r["route_id"] == route_id and r.get("reason_kind") == "zone"
            and r.get("status") == "in_use" and int(r.get("alt_index") or 0) and r.get("vehicle_profile") in (None, "", used)]
    if not rows:
        return []
    names = {z["id"]: z.get("name") for z in zones.list_zones()}
    runs = {}
    for r in rows:
        runs.setdefault((r.get("starts_on") or "", r.get("ends_on") or ""), {})[r["leg"]] = r
    out = []
    for (s, e), by_leg in sorted(runs.items()):
        drawn = {}
        for leg in ("loaded", "return"):
            r = by_leg.get(leg)
            if r:
                g = db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? "
                             "AND leg = ? AND alt_index = ?", (tenant, route_id, used, leg, int(r["alt_index"])))
                drawn[leg] = g[0] if g else legs.get(leg)
            else:
                drawn[leg] = legs.get(leg)
        zids = sorted({z for r in by_leg.values() for z in (r.get("reason_ref") or "").split(",") if z})
        back = None
        if e:
            d = datetime.date.fromisoformat(e) + datetime.timedelta(days=1)
            back = f"{d.day} {d:%b %Y}"
        alts = sorted({0} | {int(r["alt_index"]) for r in by_leg.values()})
        lim_status, lim_lines = _limits_words(route_id, used, vehicle_text, alts=alts)
        out.append({
            "from": s or None, "to": e or None,
            "when": _when(s or None, e or None),
            "because": [names.get(z) or z for z in zids],
            "loaded": _coords(drawn["loaded"]["geometry"]) if drawn.get("loaded") else [],
            "return": _coords(drawn["return"]["geometry"]) if drawn.get("return") else [],
            "loaded_words": leg_words(drawn.get("loaded")), "return_words": leg_words(drawn.get("return")),
            "back_on": back, "limits_status": lim_status, "limits_lines": lim_lines,
        })
    return out


def _when(s, e):
    """"1–31 Dec 2027" / "1 Jun – 31 Oct 2029" / "5 Oct 2026 – 17 Dec 2027" / "from 5 Oct 2026" (the app's divWhen)."""
    a = datetime.date.fromisoformat(s) if s else None
    b = datetime.date.fromisoformat(e) if e else None
    if a and not b:
        return f"from {a.day} {a:%b %Y}"
    if b and not a:
        return f"until {b.day} {b:%b %Y}"
    if not a:
        return ""
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b.day} {b:%b %Y}"
    if a.year == b.year:
        return f"{a.day} {a:%b} – {b.day} {b:%b %Y}"
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


# 23 Oct 2026 (the route line redesign): a leg's stretch on a drawn haul road is drawn dotted and thinner, as on the public
# map (withHaulPieces there, this here): every point of the leg within HAUL_NEAR_M of a haul road, each run of two or more
# points one piece. The spliced points sit on the drawn road to the metre, so 9 m takes in a public-road point only where
# it IS the road's end.
HAUL_NEAR_M = 9.0


def haul_pieces(coords, roads, near_m=HAUL_NEAR_M):
    """The runs of `coords` ([(lon, lat), …]) on one of `roads` ([(lon, lat), …] each), as lists of (lon, lat)."""
    import math as _m
    if not coords or not roads:
        return []
    lat0 = coords[len(coords) // 2][1]
    kx, ky = _m.cos(_m.radians(lat0)) * 111320.0, 110540.0
    segs = []
    for line in roads:
        pts = [(p[0] * kx, p[1] * ky) for p in line]
        segs += list(zip(pts, pts[1:]))
    if not segs:
        return []
    n2 = near_m * near_m

    def near(lon, lat):
        x, y = lon * kx, lat * ky
        for (ax, ay), (bx, by) in segs:
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2)) if l2 else 0.0
            px, py = ax + t * dx - x, ay + t * dy - y
            if px * px + py * py <= n2:
                return True
        return False
    pieces, run = [], []
    for q in coords:
        if near(q[0], q[1]):
            run.append((q[0], q[1]))
        else:
            if len(run) >= 2:
                pieces.append(run)
            run = []
    if len(run) >= 2:
        pieces.append(run)
    return pieces


def _haul_roads():
    """The drawn haul roads in force, as lines."""
    import zones
    try:
        return [ln for ln in (zones.as_line(z["geometry"]) for z in zones.haul_roads()) if ln]
    except Exception:
        return []


def views(S):
    """Adds S["view1"] (the whole route, both legs) and S["view2"] (the last mile) and the community considerations
    inside the last mile's frame. Each view is None when there is nothing to frame."""
    import basemap
    import route_map_export as rme
    w1, h1 = int(round(MAP1_W_MM * PX_PER_MM)), int(round(MAP1_H_MM * PX_PER_MM))
    w2, h2 = int(round(MAP2_W_MM * PX_PER_MM)), int(round(MAP2_H_MM * PX_PER_MM))
    S["view1"] = basemap.view(list(S["loaded"]) + list(S["return"]), w1, h1, pad_px=80, max_zoom=15.0)
    near = list(S["last_mile_in"]) + list(S["last_mile_out"])
    if near:      # the gates in frame too, so a gate just off the end of the road route is on the map
        near += [g["at"] for g in (S["entry"], S["exit"]) if g.get("at")]
    S["view2"] = basemap.view(near, w2, h2, pad_px=70, max_zoom=17.0) if near else None
    S["community"] = rme.community_in_frame(S["view2"]) if S["view2"] else None
    return S


def file_name(S):
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(S["route_id"]))
    return f"route-sheet-{safe}.pdf"
