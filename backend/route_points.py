"""
route_points.py — "Take care on this route": what Wayscope holds about a route that a driver should know, from STORED
data only (25 Nov 2026, the Look-ahead rethink, card 4; John: "the driver sheet should also include highlighting high
risk areas but ensure its clear and consise not overloaded with info"; his "Yes, as recommended" to Q12 to Q16).

WHAT IT GIVES
-------------
    P = points(route_id, vehicle, day=None, alts=None, ctx=None)      one route, one lorry type, both ways
    cut(P, places=3)                                                    the Driver sheet's cut
    drop_shared(blocks)                                                 a point two routes of a day share, once

For the line IN USE (a dated diversion in force on `day` is the road the driver drives; `alts` names the options for a
Route sheet's diversion page; neither = the main line), each way (loaded, return):
  1. limits     every stored limit hit for this lorry and leg whose verdict is "at_limit" or "exceeds" (never one that
                reads "allowed", never "within"), a line each, never cut, with a mile mark where the hit's stored sign
                position lies on the leg's line (LIMIT_ON_LINE_M);
  2. closures   a dated closure in force that day: its diversion ("Diversion in force until …: route sheet, page n"),
                or "no diversion stored"; a peak-hours road in use that day ("16:00 to 19:00: the peak-hours road,
                route sheet, page n"). Never cut. A closure only planned for a later day is not printed. With no day (the
                Route sheet's first page) every diversion page and peak-hours page is named with its dates;
  3. places     hospitals, schools and health centres of the stored community layer within route_best.PLACES_M (250 m)
                of the leg's line, measured as route_best._places measures them (the line thinned as community._thin,
                collisions.RouteIndex, the feature's nearest point), each with its distance along the leg; places of one
                kind within PLACE_GROUP_KM of each other along the leg are one line with a count and the stretch;
                printed by the STORED name (the layer holds no town: none is printed);
  4. the sentence over the limits, one a kind; "nothing stored"; "Limits not checked for this lorry";
  5. the gate line and the holding area's line; the foot "What Wayscope holds within 250 m of the route. Road signs
     come first."

Collisions are NOT here (Q14). A cycle route beside the road is NOT here: only totals are worked out (route_best counts
beside_km on the fly); no stretch with its position is stored. No fetch, no write, no map picture. Words such as "safe",
"clear" and "dangerous" are never used (test_route_points asserts it on every built block).
"""
import datetime
import json
import math

#: the three kinds of place that decide (route_best.DECIDING_KINDS) in the order a cut keeps them (Q13)
PLACE_KINDS = ("hospitals", "schools", "health")
#: places of one kind closer than this along the leg are one line ("First ¼ mi · 4 schools")
PLACE_GROUP_KM = 1.0
#: a cut keeps this many place lines each way; limits and closures are never cut
CUT_PLACES = 3
#: a limit's stored sign position counts as ON the leg (and gets a mile mark) within this of the line
LIMIT_ON_LINE_M = 30.0
VERDICTS = ("exceeds", "at_limit")

HEAD = "Take care on this route"
FOOT = "What Wayscope holds within 250 m of the route. Road signs come first."
NOT_CHECKED = "Limits not checked for this lorry"
NOT_ROUTED = "No road route has been worked out for this lorry on this route yet."
NOTHING = ("Wayscope holds no record of a limit for this lorry, a closure, or a school, hospital or health centre "
           "within 250 m of this route.")
NOTHING_PLACES = ("Wayscope holds no record of a closure, or a school, hospital or health centre within 250 m of this "
                  "route.")
OVER = "This lorry is over a limit below. Ask the site team before you run."
PLACES_NOT_FETCHED = "Schools, hospitals and health centres: not fetched along this route yet."
NO_NAME = "no road name stored"
NO_NAME_SEE = "no road name stored: see the map on the route sheet"
WAIT = "Wait there until called to site."
#: the words a driver must never read on this block (a harness asserts it over every built block)
BANNED = ("safe", "clear", "dangerous", "collision", "accident", "risk")

KIND_ONE = {"hospitals": "a hospital", "schools": "a school", "health": "a health centre"}
KIND_MANY = {"hospitals": "hospitals", "schools": "schools", "health": "health centres"}
_DIM_WORDS = {"height": ("high", "height"), "width": ("wide", "width"), "weight": ("", "weight")}


# --------------------------------------------------------------------------- distances
def _unit():
    import export
    return export._du()


def _hav_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, h)))


def _frac(mi):
    """0.5 -> '½', 0.75 -> '¾', 0.25 -> '¼' (a quarter mile at most from a whole one)."""
    q = int(round(mi * 4))
    whole, part = divmod(q, 4)
    return (str(whole) if whole else "") + {0: "", 1: "¼", 2: "½", 3: "¾"}[part] if q else "¼"


def mark(km, unit=None):
    """Where a point is along a leg, in the organisation's unit: 'First ¼ mi', '½ mi', '¾ mi', whole miles from 1;
    '0.4 km' (one decimal, at least 0.1) in km."""
    unit = unit or _unit()
    if km is None:
        return None
    if unit == "mi":
        mi = float(km) / 1.609344
        if mi <= 0.25:
            return "First ¼ mi"
        if mi < 0.875:
            return f"{_frac(mi)} mi"
        return f"{max(1, int(round(mi)))} mi"
    return f"{max(0.1, round(float(km), 1)):.1f} km"


def stretch(a_km, b_km, unit=None):
    """A stretch along a leg: one mark when both ends read the same ('14 mi'), 'First ½ mi' from the start,
    '14–15 mi' / '3.2–4.0 km' otherwise."""
    unit = unit or _unit()
    m1, m2 = mark(a_km, unit), mark(b_km, unit)
    if m1 == m2:
        return m1
    if m1.startswith("First "):
        return "First " + m2
    n1, n2 = m1.rsplit(" ", 1)[0], m2.rsplit(" ", 1)[0]
    return f"{n1}–{n2} {unit}"


def leg_length(km, unit=None):
    """'34 miles' / '1 mile' / 'under 1 mile' / '54.8 km' (a leg's heading)."""
    unit = unit or _unit()
    if km is None:
        return None
    if unit == "mi":
        mi = float(km) / 1.609344
        if mi < 0.5:
            return "under 1 mile"
        n = int(round(mi))
        return f"{n} mile{'' if n == 1 else 's'}"
    return f"{float(km):.1f} km"


class _Line:
    """A leg's stored line on a local plane: the distance along it of the nearest point to any position."""

    def __init__(self, coords):
        self.coords = [(float(c[0]), float(c[1])) for c in coords or []]
        lat0 = (sum(c[1] for c in self.coords) / len(self.coords)) if self.coords else 52.0
        self.kx, self.ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
        self.xy = [(c[0] * self.kx, c[1] * self.ky) for c in self.coords]
        self.cum = [0.0]
        for a, b in zip(self.coords, self.coords[1:]):
            self.cum.append(self.cum[-1] + _hav_m(a, b))

    @property
    def km(self):
        return self.cum[-1] / 1000.0 if self.cum else 0.0

    def along(self, lon, lat):
        """(km along the line of the nearest point, metres off the line), or (None, None) for an empty line."""
        if len(self.xy) < 2:
            return None, None
        px, py = lon * self.kx, lat * self.ky
        best = None
        for i, ((ax, ay), (bx, by)) in enumerate(zip(self.xy, self.xy[1:])):
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
            d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if best is None or d < best[0]:
                best = (d, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]))
        return best[1] / 1000.0, best[0]


# --------------------------------------------------------------------------- what is read once
class Context:
    """The reads every route's points share: the stored places of the three kinds (gridded once), whether the layer is
    fetched and along every option, the factors, the gates, the route-choice rows. Build one for a whole sheet."""
    CELL = 0.01            # degrees: the places' grid (about 0.7 km × 1.1 km here)

    def __init__(self, day=None):
        import db
        import community
        import conversions
        import gates
        import route_choice
        self.tenant = db.current_tenant()
        self.day = day
        self.factors = conversions.load_factors()
        self.unit = _unit()
        st = {}
        try:
            st = community.status() or {}
        except Exception:                                             # noqa: BLE001 — a read that fails claims nothing
            st = {}
        self.fetched = bool(st.get("fetched_at"))
        self.all_options = bool(st.get("all_options"))
        self.places, self.grid = [], {}
        if self.fetched:
            for r in db.query("SELECT feature_id, kind, source, name, geometry_json FROM community_features "
                              "WHERE tenant_id = ? ORDER BY kind, feature_id", (self.tenant,)):
                if r["kind"] not in PLACE_KINDS:
                    continue
                try:
                    import route_compare
                    pts = route_compare._points(json.loads(r["geometry_json"]))
                except Exception:                                     # noqa: BLE001
                    continue
                if not pts:
                    continue
                i = len(self.places)
                self.places.append({"id": r["feature_id"], "kind": r["kind"], "source": r.get("source"),
                                    "name": (r.get("name") or "").strip() or None, "pts": pts})
                for cell in {(int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))) for p in pts}:
                    self.grid.setdefault(cell, []).append(i)
        self.gbl = gates.gates_by_location(include_inactive=True)
        self.choice_rows = route_choice._rows_by_route()
        self.all_choice = route_choice._all_rows()
        self._zone_names = None
        self.sources_used = set()

    def zone_names(self):
        if self._zone_names is None:
            import zones
            try:
                self._zone_names = {z["id"]: z.get("name") for z in zones.list_zones()}
            except Exception:                                         # noqa: BLE001
                self._zone_names = {}
        return self._zone_names

    def near(self, coords, metres=None):
        """The places within `metres` (route_best.PLACES_M) of a line, measured as route_best._places measures them:
        [(place, metres off)]. Candidates come from the grid cells under the line, never a scan of every place."""
        import collisions
        import community
        import route_best
        metres = route_best.PLACES_M if metres is None else metres
        if not coords or len(coords) < 2 or not self.places:
            return []
        thin = community._thin([list(c) for c in coords])
        pad_lat = (metres + 50) / 110574.0
        cand = set()
        for p in thin:
            pad_lon = (metres + 50) / (111320.0 * max(0.2, math.cos(math.radians(p[1]))))
            for gx in range(int(math.floor((p[0] - pad_lon) / self.CELL)), int(math.floor((p[0] + pad_lon) / self.CELL)) + 1):
                for gy in range(int(math.floor((p[1] - pad_lat) / self.CELL)), int(math.floor((p[1] + pad_lat) / self.CELL)) + 1):
                    cand.update(self.grid.get((gx, gy), ()))
        if not cand:
            return []
        idx = collisions.RouteIndex([("o", thin)], [])
        out = []
        for i in sorted(cand):
            pl = self.places[i]
            best = None
            for p in pl["pts"]:
                d = idx.near(p[0], p[1])[0].get("o")
                if d is not None and (best is None or d < best[0]):
                    best = (d, p)
            if best is not None and best[0] <= metres:
                out.append((pl, best[0], best[1]))
        return out


# --------------------------------------------------------------------------- one route
def _route_row(route_id):
    import db
    rows = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), route_id))
    return rows[0] if rows else None


def _lines(route_id, vehicle):
    """{(leg, alt): row} of the stored lines of this route for this lorry type."""
    import db
    out = {}
    for g in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry, distance_km, duration_hr, computed_at "
                      "FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? "
                      "AND geometry IS NOT NULL", (db.current_tenant(), route_id, vehicle)):
        out[(g["leg"], int(g.get("alt_index") or 0))] = g
    return out


def _coords(raw):
    import route_sheet
    return route_sheet._coords(raw)


def _date_words(d):
    d = d if isinstance(d, datetime.date) else datetime.date.fromisoformat(str(d)[:10])
    return f"{d.day} {d:%b %Y}"


def sheet_pages(route_id, vehicle, ctx=None):
    """The Route sheet's pages after the first, in its own order (route_sheet._diversions, then _busy_roads), without
    reading a line: [{"page", "kind": "diversion"|"peak", "from", "to", "when", "legs"}]."""
    import route_choice
    rows = (ctx.all_choice if ctx is not None else route_choice._all_rows())
    runs = {}
    for r in rows:
        if (r["route_id"] == route_id and r.get("reason_kind") == "zone" and r.get("status") == "in_use"
                and int(r.get("alt_index") or 0) and r.get("vehicle_profile") in (None, "", vehicle)):
            runs.setdefault((r.get("starts_on") or "", r.get("ends_on") or ""), set()).add(r["leg"])
    out = []
    import route_sheet
    for (s, e), legs in sorted(runs.items()):
        out.append({"page": len(out) + 2, "kind": "diversion", "from": s or None, "to": e or None,
                    "when": route_sheet._when(s or None, e or None), "legs": legs})
    for u in route_choice.busy_uses(route_id):
        if u["status"] != "in_use":
            continue
        mine = {l["leg"] for l in u["legs"] if l.get("status") == "in_use" and l.get("vehicle_profile") in (None, "", vehicle)}
        if not mine:
            continue
        out.append({"page": len(out) + 2, "kind": "peak", "from": u["from"], "to": u["to"],
                    "when": f"{u['from']} to {u['to']}", "legs": mine})
    return out


def _when_of(v):
    try:
        t = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _later(a, b):
    """True when time `a` is after time `b` (both stored ISO texts; compared as text when one does not parse)."""
    ta, tb = _when_of(a), _when_of(b)
    if ta is None or tb is None:
        return str(a) > str(b)
    return ta > tb


def _limits_state(route, vehicle, lines_used):
    """('checked' | 'not_checked', checked_at date or None, [hits]). Not checked: no check stored, the last check did not
    finish, or a line in use was worked out after the check (a re-route since), so it cannot be shown clean."""
    import limits
    st = (limits.stored_checks([route["id"]]) or {}).get(route["id"]) or {}
    at = st.get("checked_at")
    if not at or str(st.get("status") or "").startswith("error"):
        return "not_checked", None, []
    for g in lines_used.values():
        if g is not None and g.get("computed_at") and _later(g["computed_at"], at):
            return "not_checked", None, []
    hits = [h for h in st.get("hits") or [] if isinstance(h, dict) and h.get("vehicle_profile") == vehicle]
    return "checked", str(at)[:10], hits


def _limit_item(h, line, see_map, unit=None):
    import limits
    kind = h.get("kind")
    lab = (limits.KINDS.get(kind) or {}).get("label") or "Limit"
    try:
        val = limits.fmt_value(kind, float(h.get("limit")))
    except (TypeError, ValueError):
        val = str(h.get("limit") or "")
    if kind in ("height", "width") and h.get("limit") is not None:
        try:
            lab += f" ({h.get('signed') or limits.imperial_text(float(h['limit']))})"
        except (TypeError, ValueError):
            pass
    where = ", ".join(x for x in (h.get("name"), h.get("ref")) if x)
    text = lab + " · " + (where or (NO_NAME_SEE if see_map else NO_NAME))
    if h.get("exceptions"):
        text += f", {str(h['exceptions']).lower()}"
    if h.get("verdict") == "exceeds":
        text += " · this lorry is over it"
    at_km = None
    anc = h.get("anchor")
    if anc and len(anc) == 2 and anc[0] is not None and line is not None:
        km, off = line.along(float(anc[0]), float(anc[1]))
        if km is not None and off is not None and off <= LIMIT_ON_LINE_M:
            at_km = km
            text += f" · {mark(km, unit)}"
    return {"kind": "limit", "limit_kind": kind, "w": val, "text": text, "at_km": at_km,
            "state": "over" if h.get("verdict") == "exceeds" else "at",
            "key": ("limit", h.get("source"), h.get("ext_id"), kind), "source": h.get("source")}


def _sentences(items, vehicle_values):
    """The sentence over the limits, one a kind (Q13): any limit this lorry is over -> OVER once; a kind where every
    hit is at the limit -> 'This lorry is 4.0 m high: at the limit at every height limit below. Check its real height
    before you set off.'"""
    out = []
    lims = [i for i in items if i["kind"] == "limit"]
    if any(i["state"] == "over" for i in lims):
        out.append(OVER)
    kinds = []
    for i in lims:
        if i["limit_kind"] not in kinds:
            kinds.append(i["limit_kind"])
    for k in kinds:
        mine = [i for i in lims if i["limit_kind"] == k]
        if any(i["state"] == "over" for i in mine) or k not in _DIM_WORDS:
            continue
        vals = sorted({v for v in vehicle_values.get(k, ()) if v is not None})
        adj, noun = _DIM_WORDS[k]
        if len(vals) == 1:
            v = vals[0]
            fig = f"{v:.1f} m {adj}" if k in ("height", "width") else f"{v:g} t"
            out.append(f"This lorry is {fig}: at the limit at every {noun} limit below. "
                       f"Check its real {noun} before you set off.")
        else:
            out.append(f"This lorry is at the limit at every {noun} limit below. Check its real {noun} before you set off.")
    return out


def _gate_line(route, ctx, dest, with_closed):
    """'Melton Compound: Compound gate. Open 07:30–18:00. No deliveries 08:00–09:00 or 15:00–16:00.' — the arriving
    gate as route_sheet words it (gates.resolve, the bake's rule; the default hours said as the default)."""
    import route_sheet
    import gate_hours
    e = route_sheet._gate_words(dest, "entry", route.get("dest_gate_id"), ctx.gbl.get(route["dest_id"]), ctx.factors)
    parts = [f"{dest.get('name') or route['dest_id']}:"]
    parts.append(f"{e['name']}." if e.get("name") else "no gate typed.")
    if e.get("hours"):
        parts.append(f"Open {e['hours']}" + (f", {e['closed']}" if (with_closed and e.get('closed')) else "") + ".")
    elif e.get("default_hours"):
        parts.append(f"Open hours not typed (planned on {e['default_hours']}, the default).")
    if e.get("shut"):
        parts.append(f"Gate shut {e['shut']}.")
    pw = gate_hours.peak_words(gate_hours.peak_bands(ctx.factors))
    if pw:
        parts.append("No deliveries " + pw.replace(" and ", " or ") + ".")
    return " ".join(parts)


def _holding_line(route, vehicle, legs_rows, ctx):
    """The holding area's line when this lorry calls off at one (route_sheet._holding_stop, the rule's own)."""
    import route_sheet
    import export
    legs = {"loaded": legs_rows.get("loaded"), "return": legs_rows.get("return")}
    loaded = _coords(legs["loaded"]["geometry"]) if legs.get("loaded") else []
    ret = _coords(legs["return"]["geometry"]) if legs.get("return") else []
    try:
        h = route_sheet._holding_stop(route, vehicle, {k: v for k, v in legs.items() if v}, loaded, ret, ctx.gbl,
                                      ctx.factors, export._du())
    except Exception:                                                 # noqa: BLE001 — never fails the sheet
        h = None
    if not h:
        return None
    where = f", {h['before_words']}" if h.get("before_words") else ""
    lead = "Coming back: go to " if h.get("leg") == "return" else "Go to "
    return f"{lead}{h['name']} first{where}. {WAIT}"


def _closures(route, vehicle, day, ctx):
    """(lines, alts by leg): the closures and peak-hours roads in force on `day` (Q13), each line once for the route,
    and the option each leg takes that day (a diversion in force is the road driven)."""
    import route_choice
    pages = sheet_pages(route["id"], vehicle, ctx)
    lines, alts, seen = [], {"loaded": 0, "return": 0}, set()
    names = ctx.zone_names()
    if day is None:
        for p in pages:
            leg = "" if len(p["legs"]) != 1 else (" going loaded" if "loaded" in p["legs"] else " coming back")
            if p["kind"] == "diversion":
                lines.append({"kind": "closure", "text": f"Diversion {p['when']}{leg}: page {p['page']}"})
            else:
                lines.append({"kind": "peak", "text": f"Weekdays {p['when']}: the peak-hours road{leg}, page {p['page']}"})
        for r in ctx.all_choice:
            if (r["route_id"] == route["id"] and r.get("reason_kind") == "zone" and r.get("status") in route_choice.PROBLEM
                    and r.get("vehicle_profile") in (None, "", vehicle)):
                k = (r.get("starts_on"), r.get("ends_on"), r.get("reason_ref"))
                if k in seen:
                    continue
                seen.add(k)
                import route_sheet
                why = ", ".join(n for n in (names.get(z) or z for z in (r.get("reason_ref") or "").split(",") if z) if n)
                lines.append({"kind": "closure", "text": f"Closure {route_sheet._when(r.get('starts_on'), r.get('ends_on'))}"
                                                         + (f" · {why}" if why else "") + ": no diversion stored"})
        return lines, alts
    d = route_choice._d(day)
    for leg in ("loaded", "return"):
        c = route_choice.choice_on(route["id"], vehicle, leg, d, rows=ctx.choice_rows)
        if c is not None and c.get("reason_kind") == "zone":
            until = f" until {_date_words(c['ends_on'])}" if c.get("ends_on") else ""
            if c.get("status") == "in_use":
                alts[leg] = int(c.get("alt_index") or 0)
                pg = next((p["page"] for p in pages if p["kind"] == "diversion"
                           and (p["from"] or "") == (c.get("starts_on") or "") and (p["to"] or "") == (c.get("ends_on") or "")), None)
                key = ("div", c.get("starts_on"), c.get("ends_on"))
                txt = f"Diversion in force{until}" + (f": route sheet, page {pg}" if pg else "")
            else:
                why = ", ".join(n for n in (names.get(z) or z for z in (c.get("reason_ref") or "").split(",") if z) if n)
                key = ("closed", c.get("starts_on"), c.get("ends_on"), c.get("reason_ref"))
                txt = f"Closure in force{until}" + (f" · {why}" if why else "") + ": no diversion stored"
            if key not in seen:
                seen.add(key)
                lines.append({"kind": "closure", "text": txt, "legs": {leg}})
            else:
                next(x for x in lines if x["text"] == txt)["legs"].add(leg)
            continue
        for r in route_choice._peaks_on(route["id"], vehicle, leg, d, ctx.choice_rows):
            key = ("peak", r.get("hours_from"), r.get("hours_to"))
            pg = next((p["page"] for p in pages if p["kind"] == "peak" and p["from"] == r.get("hours_from")), None)
            txt = f"{r.get('hours_from')} to {r.get('hours_to')}: the peak-hours road" + (f", route sheet, page {pg}" if pg else "")
            if key not in seen:
                seen.add(key)
                lines.append({"kind": "peak", "text": txt, "legs": {leg}})
            else:
                next(x for x in lines if x["text"] == txt)["legs"].add(leg)
    for x in lines:                    # one leg only: say which
        legs = x.pop("legs", {"loaded", "return"})
        if len(legs) == 1:
            x["text"] += " (going loaded)" if "loaded" in legs else " (coming back)"
    return lines, alts


def _places(line_obj, coords, ctx):
    """The leg's places as printed lines: one a place, or one a group of one kind within PLACE_GROUP_KM of each other
    along the leg. Each line: {kind: "place", place_kind, w, text, at_km, n, off_m, keys, names}."""
    hits = []
    for pl, off, pt in ctx.near(coords):
        km, _o = line_obj.along(pt[0], pt[1])
        hits.append({"place": pl, "off": off, "km": km})
        if pl.get("source"):
            ctx.sources_used.add(pl["source"])
    out = []
    for kind in PLACE_KINDS:
        mine = sorted([h for h in hits if h["place"]["kind"] == kind], key=lambda h: (h["km"], h["place"]["id"]))
        group = []
        for h in mine + [None]:
            if h is not None and (not group or h["km"] - group[-1]["km"] <= PLACE_GROUP_KM):
                group.append(h)
                continue
            if group:
                out.append(_place_line(kind, group, ctx.unit))
            group = [h] if h is not None else []
    out.sort(key=lambda x: (x["at_km"], PLACE_KINDS.index(x["place_kind"])))
    return out


def _place_line(kind, group, unit):
    if len(group) == 1:
        h = group[0]
        text = h["place"]["name"] or KIND_ONE[kind]
        w = mark(h["km"], unit)
    else:
        text = f"{len(group)} {KIND_MANY[kind]}"
        w = stretch(group[0]["km"], group[-1]["km"], unit)
    return {"kind": "place", "place_kind": kind, "w": w, "text": text, "at_km": group[0]["km"], "n": len(group),
            "off_m": min(h["off"] for h in group), "keys": [("place", h["place"]["id"]) for h in group],
            "names": [h["place"]["name"] for h in group]}


def points(route_id, vehicle=None, day=None, alts=None, ctx=None, see_map=True):
    """
    The block for one route and one lorry type (see the module docstring). `day` (a date or ISO string): the line in use
    that day and only the closures in force that day. `alts` ({leg: alt}): a Route sheet's diversion page. Neither: the
    main line, every diversion page named. `see_map`: an unnamed limit points to the route sheet's map (the Driver sheet).
    Returns a dict; nothing is fetched or written.
    """
    import conversions
    import db
    ctx = ctx or Context(day)
    route = _route_row(route_id)
    if route is None:
        raise LookupError(f"no route {route_id}")
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ? AND id IN (?, ?)",
                                         (ctx.tenant, route["origin_id"], route["dest_id"]))}
    o, dest = locs.get(route["origin_id"]) or {}, locs.get(route["dest_id"]) or {}
    stored = _lines(route_id, vehicle) if vehicle else {}
    P = {"route_id": route_id, "vehicle": vehicle,
         "vehicle_text": conversions.vehicle_label(ctx.factors, vehicle) if vehicle else None,
         "day": (str(day)[:10] if day else None), "origin": o.get("name") or route["origin_id"],
         "dest": dest.get("name") or route["dest_id"], "head": HEAD, "foot": FOOT, "unit": ctx.unit,
         "routed": bool(stored.get(("loaded", 0))), "sentences": [], "closures": [], "legs": [],
         "nothing": None, "limits": "not_checked", "limits_checked": None, "places_fetched": ctx.fetched,
         "gate": None, "holding": None}
    P["gate"] = _gate_line(route, ctx, dest, with_closed=day is None)
    if not P["routed"]:
        P["sentences"] = [NOT_ROUTED]
        return P
    closures, by_leg = _closures(route, vehicle, day, ctx) if alts is None else ([], dict(alts))
    if day is None and alts is None:
        by_leg = {"loaded": 0, "return": 0}
    P["closures"] = closures
    used = {leg: (stored.get((leg, int(by_leg.get(leg) or 0))) or stored.get((leg, 0))) for leg in ("loaded", "return")}
    P["alts"] = {leg: (int(by_leg.get(leg) or 0) if stored.get((leg, int(by_leg.get(leg) or 0))) else 0)
                 for leg in ("loaded", "return")}
    state, checked, hits = _limits_state(route, vehicle, used)
    P["limits"], P["limits_checked"] = state, checked
    places_ok = ctx.fetched and (ctx.all_options or not any(P["alts"].values()))
    P["places_fetched"] = places_ok
    vehicle_values, all_items = {}, []
    for leg in ("loaded", "return"):
        g = used.get(leg)
        coords = _coords(g["geometry"]) if g else []
        line = _Line(coords)
        alt = P["alts"][leg]
        items = []
        if state == "checked":
            seen = set()
            for h in hits:
                if h.get("leg") != leg or int(h.get("alt_index") or 0) != alt or h.get("verdict") not in VERDICTS:
                    continue
                k = (h.get("source"), h.get("ext_id"), h.get("kind"))
                if k in seen:
                    continue
                seen.add(k)
                it = _limit_item(h, line, see_map, ctx.unit)
                items.append(it)
                vehicle_values.setdefault(h.get("kind"), set()).add(h.get("vehicle_value"))
            items.sort(key=lambda i: (i["at_km"] is None, i["at_km"] or 0.0))
        places = _places(line, coords, ctx) if (places_ok and coords) else []
        km = float(g["distance_km"]) if (g and g.get("distance_km") is not None) else (line.km if coords else None)
        P["legs"].append({"leg": leg, "title": "Going loaded" if leg == "loaded" else "Coming back",
                          "length": leg_length(km, ctx.unit), "km": km, "limits": items, "places": places,
                          "more": 0, "shared": 0})
        all_items += items + places
    P["vehicle_values"] = {k: sorted(v for v in vs if v is not None) for k, vs in vehicle_values.items()}
    P["sentences"] = _sentences(all_items, vehicle_values)
    if state == "not_checked":
        P["sentences"].insert(0, NOT_CHECKED + ".")
    if not places_ok:
        P["sentences"].append(PLACES_NOT_FETCHED)
    empty = not all_items and not closures
    if empty and places_ok:
        P["nothing"] = NOTHING if state == "checked" else NOTHING_PLACES
    P["holding"] = _holding_line(route, vehicle, {leg: used.get(leg) for leg in ("loaded", "return")}, ctx)
    return P


# --------------------------------------------------------------------------- the cut and the shared points
def _rank(line):
    """Q13: hospitals first, then schools nearest the road first, then health centres."""
    return (PLACE_KINDS.index(line["place_kind"]), line["off_m"] if line["place_kind"] == "schools" else 0.0,
            line["at_km"])


def cut(P, places=CUT_PLACES):
    """The Driver sheet's cut, in place on a copy: at most `places` place lines each way, chosen by _rank and printed
    in the order a driver meets them; the rest counted in `more` (places, not lines) for "+n more on the route sheet".
    Limits and closures are never cut."""
    import copy
    Q = copy.deepcopy(P)
    for L in Q["legs"]:
        keep = sorted(L["places"], key=_rank)[:places]
        dropped = [x for x in L["places"] if x not in keep]
        L["more"] += sum(x["n"] for x in dropped)
        L["places"] = sorted(keep, key=lambda x: x["at_km"])
    return Q


def drop_shared(blocks):
    """A point two of the day's routes share (the same limit, the same place) is printed once, under the first block
    that has it (Q13). Works in place on the blocks (each from points()); `shared` counts what a leg left out and
    `shared_from` the routes it was printed under. A block that lost limits says its sentence again over what is left
    (a sentence never speaks of a limit "below" that is printed above)."""
    seen = {}
    for P in blocks:
        mine = set()
        lost = False
        for L in P.get("legs") or []:
            L.setdefault("shared_from", [])
            keep_l = []
            for it in L["limits"]:
                if it["key"] in seen:
                    L["shared"] += 1
                    lost = True
                    if seen[it["key"]] not in L["shared_from"]:
                        L["shared_from"].append(seen[it["key"]])
                else:
                    keep_l.append(it)
                    mine.add(it["key"])
            L["limits"] = keep_l
            keep_p = []
            for it in L["places"]:
                ks = [k for k in it["keys"] if k not in seen]
                for k in it["keys"]:
                    if k in seen and seen[k] not in L["shared_from"]:
                        L["shared_from"].append(seen[k])
                if not ks:
                    L["shared"] += it["n"]
                    continue
                if len(ks) < len(it["keys"]):            # part of a group shown above: the rest stays, counted
                    L["shared"] += len(it["keys"]) - len(ks)
                    it = dict(it, keys=ks, n=len(ks), text=(f"{len(ks)} {KIND_MANY[it['place_kind']]}" if len(ks) > 1
                                                          else (next(n for k, n in zip(it["keys"], it["names"]) if k in ks)
                                                                or KIND_ONE[it["place_kind"]])))
                keep_p.append(it)
                mine.update(ks)
            L["places"] = keep_p
        for k in mine:
            seen[k] = P.get("route_id")
        if lost:
            _resay(P)
    return blocks


def _resay(P):
    """The block's sentences again over the limits it still prints; the not-checked and not-fetched sentences stay."""
    keep_first = [x for x in P.get("sentences") or [] if x == NOT_CHECKED + "."]
    keep_last = [x for x in P.get("sentences") or [] if x in (PLACES_NOT_FETCHED, NOT_ROUTED)]
    items = [i for L in P.get("legs") or [] for i in L["limits"]]
    P["sentences"] = keep_first + _sentences(items, {k: set(v) for k, v in (P.get("vehicle_values") or {}).items()}) + keep_last


def all_words(P):
    """Every word the block prints, for the banned-word check and the longest-block measure."""
    out = [P["head"], P["foot"], P.get("gate") or "", P.get("holding") or "", P.get("nothing") or ""]
    out += list(P.get("sentences") or []) + [c["text"] for c in P.get("closures") or []]
    for L in P.get("legs") or []:
        out.append(f"{L['title']} · {L.get('length') or ''}")
        out += [f"{i['w']} {i['text']}" for i in L["limits"] + L["places"]]
        if L.get("more"):
            out.append(more_words(L["more"]))
    return [w for w in out if w]


def more_words(n):
    return f"+{n} more on the route sheet"


def shared_words(n, first_route):
    """"3 more shown under R012 above"; printed under several routes: "3 more shown above"."""
    if not n:
        return ""
    rs = [first_route] if isinstance(first_route, str) else [r for r in (first_route or []) if r]
    return f"{n} more shown under {rs[0]} above" if len(rs) == 1 else f"{n} more shown above"


def checked_words(P):
    return f"Limits checked {_date_words(P['limits_checked'])}." if P.get("limits_checked") else None


def credit(ctx):
    """'Community considerations: © OpenStreetMap contributors (ODbL).' for the places printed (community.credit_line)."""
    import community
    if not ctx.sources_used:
        return None
    try:
        return community.credit_line(sorted(ctx.sources_used)) or None
    except Exception:                                                 # noqa: BLE001
        return None
