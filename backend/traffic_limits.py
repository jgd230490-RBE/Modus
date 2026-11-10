"""
traffic_limits.py — a limit on the lorries a road or an area may carry. Wayscope, 9 Nov 2026 (v2.1 task 2.1-1).

THE ASK (John, 8 Nov 2026): "no more than 200 a day on average on this road" — a planning condition, a council's
request, a section 278 agreement. Drawn on Data -> Zones as kind "Traffic limit" (a line along a road or an area),
typed in its own unit as the condition was written, checked against the approved plan. A FLAG, never a block: a
limit never moves a route (Q11) and has no "Affects routing" (zones.create_zone stores it off).

THE COUNT (Q2, 2.1-11b's question A, counting.py): each PASS of a leg is a movement — the loaded leg is "in" on the
roads it runs, the empty way back "out" on the roads it runs. A movements limit compares in + out; a visits limit
counts a route's lorries once when either leg passes. Only this scheme's lorries (Q3): Wayscope knows no other traffic.

WHICH ROUTES PASS (Q5)
  a LINE  — a leg passes when it runs within LINE_NEAR_M of the line for at least LINE_SHARE of the line's length
            (the line sampled every SAMPLE_M);
  an AREA — a leg passes when at least min(ENTER_KM, AREA_ENTER_SHARE of the area's diagonal) of it is inside (the
            council view's 200 m, so a road beside the edge does not count; shrunk for an area smaller than a village
            so a route right through a small area still counts).
  A route counts once however often it passes. Every stored option of a leg is tested; a dated diversion's share of
  the in-force days (route_choice.mix, zones only — the heat map's rule) decides how much of the route's month runs
  on each.

THE FIGURE (Q4, Q7)
  basis "average"     — the in-force working days' average: the month's approved loads ÷ the working days (even
                        spread, D59), on the option each in-force day uses. Months the limit is not in force: none.
  basis "busiest_day" — checked on the planned days (the Look-ahead's two weeks, the Simulation's day); further out
                        the month's average is shown with "no day plan yet" — never a made-up busiest day.
  Over = above the limit (red, TRAFFIC LIMIT); near = NEAR_SHARE of it or more (amber, TRAFFIC NEAR) — fixed (Q8).

`through(geometry, month)` is the sum with no limit: 2.1-4 (a stretch a reader draws on the public map) calls it.
"""
import json
import math

import counting
import db
import zones

KIND = "traffic_limit"
LINE_NEAR_M = 25.0
LINE_SHARE = 0.5
SAMPLE_M = 20.0
MAX_SAMPLES = 400
ENTER_KM = 0.2
AREA_ENTER_SHARE = 0.25
NEAR_SHARE = 0.9
BASES = ("average", "busiest_day")
STATES = ("over", "near", "ok", "none")

#: the rail's words (Q1: ROAD LIMIT is the signed weight / height flag)
FLAG_WORDS = {"over": "TRAFFIC LIMIT", "near": "TRAFFIC NEAR"}
CODES = {"over": "TRAFFIC_LIMIT", "near": "TRAFFIC_NEAR"}

_PASS_CACHE = {}


# --------------------------------------------------------------------------- #
#  The limit's fields                                                         #
# --------------------------------------------------------------------------- #
def clean_fields(kind, limit_value=None, limit_counts=None, limit_basis=None, limit_public=None, partial=False):
    """({column: value}, error or None) for a zone of `kind`. Another kind: every limit column NULL."""
    if kind != KIND:
        return {"limit_value": None, "limit_counts": None, "limit_basis": None, "limit_public": None}, None
    out = {}
    if not partial or limit_value is not None:
        try:
            v = float(limit_value)
        except (TypeError, ValueError):
            return {}, "a traffic limit needs a number (lorries a day)"
        if not (v > 0) or math.isinf(v):
            return {}, "a traffic limit must be more than 0"
        out["limit_value"] = v
    if not partial or limit_counts is not None:
        c = (limit_counts or counting.MOVEMENTS).strip().lower()
        if c not in counting.UNITS:
            return {}, "a traffic limit counts movements or visits"
        out["limit_counts"] = c
    if not partial or limit_basis is not None:
        b = (limit_basis or "average").strip().lower()
        if b not in BASES:
            return {}, "a traffic limit is a daily average or a busiest day"
        out["limit_basis"] = b
    if not partial or limit_public is not None:
        out["limit_public"] = 0 if limit_public is False or str(limit_public).lower() in ("0", "false", "no") else 1
    return out, None


def shape(z):
    """The limit's own fields as a zone row carries them (zones._row)."""
    if (z.get("kind") or "") != KIND:
        return None
    try:
        v = float(z.get("limit_value")) if z.get("limit_value") not in (None, "") else None
    except (TypeError, ValueError):
        v = None
    pub = z.get("limit_public")
    return {"value": v,
            "counts": z.get("limit_counts") if z.get("limit_counts") in counting.UNITS else counting.MOVEMENTS,
            "basis": z.get("limit_basis") if z.get("limit_basis") in BASES else "average",
            "public": (True if pub is None else zones._truthy(pub))}


def chip(lim):
    """'Limit 200 / day' — the Zones list's chip."""
    if not lim or lim.get("value") is None:
        return None
    return f"Limit {_n(lim['value'])} / day"


def unit_words(unit, basis="average"):
    w = "lorry movements a day, in and out counted separately" if unit == counting.MOVEMENTS else "lorry visits a day"
    return w + (" (busiest day)" if basis == "busiest_day" else " (daily average)")


def _n(x):
    x = float(x)
    return f"{int(x):,}" if x == int(x) else f"{x:,.1f}"


def limit_zones(public_only=False):
    """Every active traffic-limit zone with geometry, as zones._row shapes it plus `limit`."""
    out = []
    for z in zones.list_zones(include_inactive=False):
        if z["kind"] != KIND or not z.get("geometry"):
            continue
        lim = z.get("limit") or {}
        if lim.get("value") is None:
            continue
        if public_only and not lim.get("public"):
            continue
        out.append(z)
    return out


# --------------------------------------------------------------------------- #
#  Geometry: which stored legs pass                                           #
# --------------------------------------------------------------------------- #
def _proj(lat0):
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0

    def f(p):
        return (p[0] * kx, p[1] * ky)
    return f


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L <= 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _samples(line_m):
    """Points every SAMPLE_M along a projected polyline (at most MAX_SAMPLES), the ends included."""
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line_m, line_m[1:]))
    if total <= 0:
        return line_m[:1]
    step = max(SAMPLE_M, total / MAX_SAMPLES)
    out, acc, nxt = [line_m[0]], 0.0, step
    for a, b in zip(line_m, line_m[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        while seg > 0 and nxt <= acc + seg:
            t = (nxt - acc) / seg
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            nxt += step
        acc += seg
    if out[-1] != line_m[-1]:
        out.append(line_m[-1])
    return out


class _Shape:
    """A limit's geometry prepared once: a line's sample points, or an area for clipping."""

    def __init__(self, geometry, enter_km=None):
        g = json.loads(geometry) if isinstance(geometry, str) else (geometry or {})
        self.kind = None
        line = zones.as_line(g) if g.get("type") in ("LineString", "MultiLineString") else None
        if line and len(line) >= 2:
            self.kind = "line"
            lat0 = sum(p[1] for p in line) / len(line)
            self.f = _proj(lat0)
            self.pts = _samples([self.f(p) for p in line])
            xs = [p[0] for p in line]
            ys = [p[1] for p in line]
            pad = 0.001     # ~100 m in degrees: a leg outside this box cannot be within 25 m
            self.bbox = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        elif g.get("type") in ("Polygon", "MultiPolygon"):
            import areas
            self.kind = "area"
            self.area = areas.Area("limit", g)
            b = self.area.bbox
            diag = math.hypot((b[2] - b[0]) * 111.32 * math.cos(math.radians((b[1] + b[3]) / 2)),
                              (b[3] - b[1]) * 110.54)
            self.enter_km = min(ENTER_KM, AREA_ENTER_SHARE * diag) if enter_km is None else float(enter_km)
            self.bbox = b

    def passes(self, coords):
        if self.kind is None or len(coords) < 2:
            return False
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        b = self.bbox
        if max(xs) < b[0] or min(xs) > b[2] or max(ys) < b[1] or min(ys) > b[3]:
            return False
        if self.kind == "area":
            import areas
            return areas.clip_km(coords, self.area) >= self.enter_km - 1e-9
        segs = []
        for a, c in zip(coords, coords[1:]):
            if max(a[0], c[0]) < b[0] or min(a[0], c[0]) > b[2] or max(a[1], c[1]) < b[1] or min(a[1], c[1]) > b[3]:
                continue
            segs.append((self.f(a), self.f(c)))
        if not segs:
            return False
        near = 0
        for p in self.pts:
            if any(_seg_dist(p, a, c) <= LINE_NEAR_M for a, c in segs):
                near += 1
        return near >= LINE_SHARE * len(self.pts) - 1e-9


def _drawn():
    """{route_id: the vehicle profile the map draws it with} (the council view's rule)."""
    import bulletin
    return {rid: p.get("vehicle_profile") for rid, p in bulletin.drawn_routes().items()}


def _legs(drawn):
    """[(route_id, leg, alt, coords)] — every stored option of both legs, on the profile the map draws the route with."""
    import road_sections
    out = []
    for g in db.query("SELECT route_id, vehicle_profile, leg, alt_index, geometry FROM route_geometry "
                      "WHERE tenant_id = ? AND geometry IS NOT NULL", (db.current_tenant(),)):
        rid = g["route_id"]
        if rid not in drawn or g.get("vehicle_profile") != drawn[rid]:
            continue
        if g.get("leg") not in ("loaded", "return"):
            continue
        pts = road_sections.coords_of(g["geometry"])
        if len(pts) >= 2:
            out.append((rid, g["leg"], int(g.get("alt_index") or 0), pts))
    return out


def passing(geometry, drawn=None, legs=None, enter_km=None):
    """{route_id: {"loaded": {alt, ...}, "return": {alt, ...}}} — the stored options that pass `geometry`.
    Kept until the next write per tenant and shape. `enter_km` (an area only) replaces the entry rule: 2.1-4's box on
    the public map counts a leg that enters it at all (section_select.BOX_ENTER_KM)."""
    gkey = json.dumps(geometry, sort_keys=True) if not isinstance(geometry, str) else geometry
    ck = (db.current_tenant(), db.data_version(), gkey, enter_km)
    if legs is None and ck in _PASS_CACHE:
        return _PASS_CACHE[ck]
    drawn = _drawn() if drawn is None else drawn
    legs = _legs(drawn) if legs is None else legs
    shp = _Shape(geometry, enter_km=enter_km)
    out = {}
    for rid, leg, alt, pts in legs:
        if shp.passes(pts):
            out.setdefault(rid, {"loaded": set(), "return": set()})[leg].add(alt)
    if len(_PASS_CACHE) > 64:
        _PASS_CACHE.clear()
    _PASS_CACHE[ck] = out
    return out


# --------------------------------------------------------------------------- #
#  The month's figure                                                         #
# --------------------------------------------------------------------------- #
def in_force_days(zone, month):
    """The month's working days the limit is in force on (Q7), as dates."""
    import route_choice
    days = route_choice.month_days(int(month))
    s, e = zones._clean_date(zone.get("starts_on")), zones._clean_date(zone.get("ends_on"))
    return [d for d in days if (not s or d.isoformat() >= s) and (not e or d.isoformat() <= e)]


def _shares(rid, profile, days, rows, cache):
    """{"loaded": {alt: share}, "return": {alt: share}} of `days` (zones only; the heat map's rule)."""
    import route_choice
    ck = (rid, tuple(days[:1]), tuple(days[-1:]), len(days))
    if ck in cache:
        return cache[ck]
    m = route_choice.mix(rid, profile, days, rows=rows, peaks=False)
    out = {"loaded": {}, "return": {}}
    for (la, ra), w in m["pairs"]:
        out["loaded"][la] = out["loaded"].get(la, 0.0) + w
        out["return"][ra] = out["return"].get(ra, 0.0) + w
    cache[ck] = out
    return out


def through(geometry, month, lines=None, wd=None, days=None, ctx=None, enter_km=None):
    """
    What passes `geometry` in `month`, a day on average: {"in_per_day", "out_per_day", "movements_per_day",
    "visits_per_day", "routes": [{route_id, in_per_day, out_per_day, visits_per_day}]} — the approved plan, the
    routes the map draws, both units (the caller picks). `days` = the in-force working days (default: the month's).
    `lines` = the month's approved lines (main.approved_lines_by_month's), read when not given.
    """
    import route_choice
    ctx = ctx if ctx is not None else context()
    month = int(month)
    if lines is None:
        by_month, _err = ctx["lines_by_month"]()
        lines = by_month.get(month, [])
    wd = float(wd or ctx["wd"] or 0)
    if days is None:
        days = route_choice.month_days(month)
    zero = {"in_per_day": 0.0, "out_per_day": 0.0, "movements_per_day": 0.0, "visits_per_day": 0.0, "routes": []}
    if not wd or not days:
        return zero
    pas = passing(geometry, drawn=ctx["drawn"], legs=ctx["legs"], enter_km=enter_km)
    loads = {}
    for l in lines or []:
        rid = l["route_id"]
        if rid in pas:
            loads[rid] = loads.get(rid, 0.0) + float(l.get("vehicle_loads") or 0.0)
    tot_in = tot_out = tot_any = 0.0
    routes = []
    for rid in sorted(loads):
        if loads[rid] <= 0:
            continue
        sh = _shares(rid, ctx["drawn"].get(rid), days, ctx["rows"], ctx["share_cache"])
        w_in = min(1.0, sum(w for a, w in sh["loaded"].items() if a in pas[rid]["loaded"]))
        w_out = min(1.0, sum(w for a, w in sh["return"].items() if a in pas[rid]["return"]))
        if w_in <= 0 and w_out <= 0:
            continue
        per_day = loads[rid] / wd
        r_in, r_out, r_any = per_day * w_in, per_day * w_out, per_day * max(w_in, w_out)
        tot_in += r_in
        tot_out += r_out
        tot_any += r_any
        routes.append({"route_id": rid, "in_per_day": round(r_in, 2), "out_per_day": round(r_out, 2),
                       "visits_per_day": round(r_any, 2)})
    return {"in_per_day": round(tot_in, 2), "out_per_day": round(tot_out, 2),
            "movements_per_day": round(tot_in + tot_out, 2), "visits_per_day": round(tot_any, 2),
            "routes": routes}


def state_of(value, limit):
    if value is None or limit is None:
        return "none"
    if value > limit + 1e-9:
        return "over"
    if value >= NEAR_SHARE * limit - 1e-9:
        return "near"
    return "ok"


def figure_for(lim, fig):
    """The figure in the limit's own unit (counting.convert is the one conversion; Q2's per-pass count)."""
    if lim["counts"] == counting.MOVEMENTS:
        return fig["movements_per_day"]
    return fig["visits_per_day"]


def context():
    """What a check reads once for every limit and month."""
    import main
    import route_choice
    import conversions
    drawn = _drawn()
    cache = {}

    def lines_by_month():
        if "v" not in cache:
            cache["v"] = main.approved_lines_by_month()
        return cache["v"]
    return {"drawn": drawn, "legs": _legs(drawn), "rows": route_choice._rows_by_route(), "share_cache": {},
            "wd": main._working_days(conversions.load_factors()), "lines_by_month": lines_by_month,
            "months": main.MONTH_COUNT}


def check(zone, months, ctx=None, route_filter=None):
    """
    {month: {"value", "in_per_day", "out_per_day", "state", "days", "routes"}} for each month the limit is in force
    in. `route_filter` (a set of route ids, the Dashboard's Sites) keeps only those routes' lorries; the limit is
    unchanged.
    """
    ctx = ctx if ctx is not None else context()
    lim = zone["limit"]
    by_month, _err = ctx["lines_by_month"]()
    out = {}
    for m in months:
        days = in_force_days(zone, m)
        if not days:
            continue
        lines = by_month.get(int(m), [])
        if route_filter is not None:
            lines = [l for l in lines if l["route_id"] in route_filter]
        fig = through(zone["geometry"], m, lines=lines, days=days, ctx=ctx)
        v = figure_for(lim, fig)
        out[int(m)] = {"value": round(v, 2), "in_per_day": fig["in_per_day"], "out_per_day": fig["out_per_day"],
                       "visits_per_day": fig["visits_per_day"],
                       "state": state_of(v, lim["value"]), "days": len(days), "routes": fig["routes"]}
    return out


def summary(months=None, public_only=False, route_filter=None, with_routes=True, ctx=None):
    """Every limit with its months — the Dashboard, the public map, the bulletin and the CLP read this."""
    ctx = ctx if ctx is not None else context()
    months = list(months) if months is not None else list(range(1, int(ctx["months"]) + 1))
    out = []
    for z in limit_zones(public_only=public_only):
        ms = check(z, months, ctx=ctx, route_filter=route_filter)
        if not with_routes:
            for v in ms.values():
                v.pop("routes", None)
        over = sorted(m for m, v in ms.items() if v["state"] == "over")
        near = sorted(m for m, v in ms.items() if v["state"] == "near")
        out.append({"id": z["id"], "name": z["name"], "geometry": z["geometry"], "limit": z["limit"],
                    "starts_on": z.get("starts_on"), "ends_on": z.get("ends_on"),
                    "unit_words": unit_words(z["limit"]["counts"], z["limit"]["basis"]),
                    "months": {str(m): v for m, v in sorted(ms.items())},
                    "months_over": over, "months_near": near})
    return {"limits": out, "near_share": NEAR_SHARE, "counting": counting.words(),
            "note": "This scheme's lorries only, from the approved plan."}


# --------------------------------------------------------------------------- #
#  The planned days (Q4): the Look-ahead and the Simulation                    #
# --------------------------------------------------------------------------- #
def day_counts(zone, day_trips, ctx=None):
    """
    {date: {"value", "in", "out", "visits", "routes"}} for a set of planned days. `day_trips` is
    {date: {route_id: trips}} (the Look-ahead's day figures). The diversion option of each date decides the pass.
    """
    ctx = ctx if ctx is not None else context()
    import datetime
    pas = passing(zone["geometry"], drawn=ctx["drawn"], legs=ctx["legs"])
    s, e = zones._clean_date(zone.get("starts_on")), zones._clean_date(zone.get("ends_on"))
    out = {}
    for d, per_route in sorted(day_trips.items()):
        if (s and d < s) or (e and d > e):
            continue
        dd = datetime.date.fromisoformat(d)
        i = o = a = 0.0
        rs = []
        for rid, trips in sorted(per_route.items()):
            if rid not in pas or not trips:
                continue
            sh = _shares(rid, ctx["drawn"].get(rid), [dd], ctx["rows"], ctx["share_cache"])
            w_in = min(1.0, sum(w for al, w in sh["loaded"].items() if al in pas[rid]["loaded"]))
            w_out = min(1.0, sum(w for al, w in sh["return"].items() if al in pas[rid]["return"]))
            if w_in <= 0 and w_out <= 0:
                continue
            i += trips * w_in
            o += trips * w_out
            a += trips * max(w_in, w_out)
            rs.append(rid)
        v = (i + o) if zone["limit"]["counts"] == counting.MOVEMENTS else a
        out[d] = {"value": round(v, 2), "in": round(i, 2), "out": round(o, 2), "visits": round(a, 2), "routes": rs,
                  "state": state_of(v, zone["limit"]["value"])}
    return out


def flag_text(zone, state, value, when):
    lim = zone["limit"]
    unit = "movements" if lim["counts"] == counting.MOVEMENTS else "visits"
    return (f"{zone['name']} {when}: {_n(round(value))} lorry {unit} against a limit of {_n(lim['value'])}"
            + ("" if state == "over" else ", near the limit"))


_STATE_ORDER = {"over": 0, "near": 1, "ok": 2, "none": 3}


def sim_day(trips_by_route, days, ctx=None):
    """
    The Simulation's line (card 7): every limit in force on any of `days` (the day, or the week's / month's working days
    the simulated day stands for), with the simulated day's whole loads per route ({route_id: trips}, pours and the rush
    included) counted against it — a busiest-day and a daily-average limit alike (Q4). Worst first. On screen only.
    """
    ctx = ctx if ctx is not None else context()
    out = []
    for z in limit_zones():
        s, e = zones._clean_date(z.get("starts_on")), zones._clean_date(z.get("ends_on"))
        d_in = [d for d in (days or []) if (not s or d.isoformat() >= s) and (not e or d.isoformat() <= e)]
        if not d_in:
            continue
        pas = passing(z["geometry"], drawn=ctx["drawn"], legs=ctx["legs"])
        i = o = a = 0.0
        rs = []
        for rid, trips in sorted((trips_by_route or {}).items()):
            if rid not in pas or not trips:
                continue
            sh = _shares(rid, ctx["drawn"].get(rid), d_in, ctx["rows"], ctx["share_cache"])
            w_in = min(1.0, sum(w for al, w in sh["loaded"].items() if al in pas[rid]["loaded"]))
            w_out = min(1.0, sum(w for al, w in sh["return"].items() if al in pas[rid]["return"]))
            if w_in <= 0 and w_out <= 0:
                continue
            i += trips * w_in
            o += trips * w_out
            a += trips * max(w_in, w_out)
            rs.append(rid)
        lim = z["limit"]
        v = (i + o) if lim["counts"] == counting.MOVEMENTS else a
        out.append({"id": z["id"], "name": z["name"], "value": round(v, 1), "in": round(i, 1), "out": round(o, 1),
                    "limit": lim["value"], "counts": lim["counts"], "basis": lim["basis"],
                    "state": state_of(v, lim["value"]), "routes": rs})
    out.sort(key=lambda r: (_STATE_ORDER[r["state"]], -(r["value"] / r["limit"] if r["limit"] else 0), r["name"]))
    return out
