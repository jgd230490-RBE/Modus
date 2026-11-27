"""
The pieces of a route's options, and what lies along a line, by ONE rule on the server (27 Nov 2026, branch
claude/route-pieces; the route lines plan's Q6, Q8, Q12 and Q16, John's "Yes, all as recommended" of 26 Nov).

WHY. Three later things need the same facts: an alternative drawn only where it differs from the line in use (Q6), a
way round railed only where it differs from the usual road (Q8), and the route strip (Q12). Until now the browser worked
out where a diversion leaves its usual road twice, by two rules: the public map's `divOffPieces` (a point counts as off
beyond 25 m, the line's own vertices only, no minimum run) and the Routes page's `olOffPieces` (beyond 30 m on points
25 m apart, runs of 150 m or more). This module is the server's one rule; the pages keep their own until a visible task,
with its own mockup, moves them onto it. The comparison of the three rules over live's lines of 24 Nov, and why this
rule, is in notes/session-1127-route-pieces.md.

THE RULE (pieces): for one option against one base line (the line in use):
  1. both lines are walked at their own vertices and at points STEP_M apart between them, each point with its metres
     along its own line (chainage.py, the server's one distance-along walk);
  2. a point of the option is ON the base when it lies within NEAR_M of the base's segments; it is matched to the
     place on the base it is near, the base's metres only moving forward (less 2 x NEAR_M of slack), so a road the base
     passes twice is matched where the walk has got to, never on the other pass;
  3. a piece is a gap between two matched points: option points off the base between them (the option goes another
     way), or the base running on more than 2 x STEP_M + NEAR_M further than the option (the base goes another way: a
     short cut, a piece whose option side is about 0 m); the start and the end are gaps when either line has more
     before its first match or after its last. So a piece names its stretch on BOTH lines, where it leaves and rejoins
     and its extra length;
  4. pieces closer than JOIN_M on both lines are one piece (a way round that crosses or touches the usual road);
  5. within each piece each side's "off" runs are measured against the OTHER line anywhere (what a map would draw: a
     stretch that only takes the other line's road at another point of the trip is not another road);
  6. a piece counts only when it has an off run AND is at least MIN_RUN_M long on one of the two lines or gets more
     than CLEAR_M away from the other line somewhere: a dual carriageway's two sides, a lay-by or a slip road beside
     its road are left out, a real turn off is kept however short.
Stored data only: no router call, no outside fetch. Lines are the stored HERE polylines (route_geometry).

WHAT LIES ALONG A LINE (`along`): one ordered list, metres from A, for a route, a leg and a lorry type, of: the stored
limits the lorry is at or over (exceeds, at the limit, allowed); schools, hospitals and health centres within
route_compare.NEAR_M of the line with their distance off; cycle-route crossings (collisions.cycle_along's "meets");
the collision evidence's numbered stretches (collisions.stretches on this line); haul-road stretches (the public map's
own rule, within HAUL_NEAR_M of a haul road in force); and the pieces of every dated diversion (in its dates) and
busy-hours road (with its hours). Everything is read from what is stored; what the stored data CANNOT give (a road's
number along the whole line, a junction's name) is listed in the note and in GAPS below.
"""
import bisect
import datetime
import functools
import math

import chainage
import db

# --------------------------------------------------------------------------- #
#  Thresholds (the rule's whole set; the note says how each was chosen)        #
# --------------------------------------------------------------------------- #
NEAR_M = 25.0          # a point within this of the other line is ON it (the public map's divOffPieces uses 25)
STEP_M = 10.0          # the walk's spacing between a line's own vertices
MIN_RUN_M = 100.0      # a piece at least this long on one of the two lines counts...
CLEAR_M = 60.0         # ...and so does a shorter one that gets more than this far from the other line
JOIN_M = 50.0          # two pieces closer than this on BOTH lines are one
HAUL_NEAR_M = 9.0      # = the public map's HAUL_NEAR_M (withHaulPieces): a leg point this close to a haul road is on it

#: the limit verdicts the along list carries ("every limit the lorry is at or over"); "within" and "unknown" are counted
AT_OR_OVER = ("exceeds", "at_limit", "allowed")
#: the community kinds the along list names (= route_best.DECIDING_KINDS, = route_analysis_doc.NAMED_KINDS)
PLACE_KINDS = ("schools", "hospitals", "health")

#: what the stored data cannot fill for the route strip (Q12); the note says what filling each would take
GAPS = {
    "road_number": "No road number is stored along a line: an ordinary bake keeps the line and its summary only. "
                   "Where a collision, a traffic count or a limit lies on the line its record names a road there.",
    "junction_name": "No junction or roundabout name is stored anywhere.",
    "speed_limit": "No speed limit is stored along a line; a collision's record has the limit where it happened.",
}


# --------------------------------------------------------------------------- #
#  The walk                                                                    #
# --------------------------------------------------------------------------- #
def walk(proj, line, step=STEP_M):
    """[(lon, lat, metres along)] at the line's own vertices and every `step` metres between them."""
    out = []
    ch = chainage.vertex_chainage(proj, line)
    for i, c in enumerate(line):
        if i:
            a, m0 = line[i - 1], ch[i - 1]
            seg = ch[i] - m0
            n = int(seg // step)
            for k in range(1, n + 1):
                t = k * step / seg
                if t >= 1.0:
                    break
                out.append((a[0] + t * (c[0] - a[0]), a[1] + t * (c[1] - a[1]), m0 + t * seg))
        out.append((c[0], c[1], ch[i]))
    return out


def _counts(p, min_run=MIN_RUN_M, clear=CLEAR_M):
    """Step 6: a piece counts when one of its two stretches leaves the other line somewhere (an "off" run: a stretch
    that only takes the other line's road at another point of the trip is not another road) AND it is at least
    min_run long on one line or gets more than `clear` from the other line."""
    if not (p["option"]["off"] or p["base"]["off"]):
        return False
    return max(p["option"]["length_m"], p["base"]["length_m"]) >= min_run or p["apart_m"] > clear


def _off(samples, lo, hi, grid, near, cap, join):
    """Within [lo, hi] metres of one line (its walk `samples`): the runs of points more than `near` from the other line
    ANYWHERE along it (grid), each widened to the point before and after (so it meets the junction) and clamped to
    [lo, hi]; runs closer than `join` are one. Returns ([[from_m, to_m]], how far the stretch gets from the other line,
    capped at `cap`)."""
    xs, ms = samples
    i = max(0, bisect.bisect_left(ms, lo))
    runs, best, start, prev = [], 0.0, None, None
    while i < len(ms) and ms[i] <= hi:
        d = grid.dist(xs[i])
        if d > near:
            best = max(best, cap if d == float("inf") else min(d, cap))
            if start is None:
                start = ms[i - 1] if i and ms[i - 1] >= lo else ms[i]
        elif start is not None:
            runs.append([max(lo, start), min(hi, ms[i])])
            start = None
        prev = ms[i]
        i += 1
    if start is not None:
        runs.append([max(lo, start), min(hi, prev if prev is not None else hi)])
    out = []
    for r in runs:
        if out and r[0] - out[-1][1] <= join:
            out[-1][1] = max(out[-1][1], r[1])
        else:
            out.append(r)
    return [[round(a, 1), round(b, 1)] for a, b in out], best


def pieces(proj, opt, base, near=NEAR_M, step=STEP_M, min_run=MIN_RUN_M, clear=CLEAR_M, join=JOIN_M, keep_all=False):
    """The pieces of option line `opt` against base line `base` (see THE RULE): [{"option": {"from_m", "to_m",
    "length_m"}, "base": {...}, "leaves": [lon, lat], "rejoins": [lon, lat], "extra_m", "apart_m", "counts"}] in order
    along the option. `keep_all` keeps the pieces step 6 leaves out ("counts": False), for the comparison.

    How: the option is walked; each point within `near` of the base is matched to the place on the base it is near,
    the base's metres only moving forward (less a little slack), so a road the base passes twice is matched where the
    walk has got to. A piece is a gap between two matched points: points off the base between them (the option goes
    another way), or the base running on further than the option between them (the base goes another way: a short
    cut). The line's start and end are gaps too when either line has more before its first or after its last match."""
    if len(opt) < 2 or len(base) < 2:
        return []
    reach = max(near, clear + 1.0)
    g_base, g_opt = chainage.Grid(proj, base, reach), chainage.Grid(proj, opt, reach)
    lo_len, lb_len = g_opt.length, g_base.length
    jump = 2 * step + near                      # the base running on this much more than the option is a gap
    back = 2 * near                             # how far back along the base a match may step
    o_w = walk(proj, opt, step)
    o_s = ([proj._xy((x, y)) for x, y, _m in o_w], [m for _x, _y, m in o_w])
    b_w = walk(proj, base, step)
    b_s = ([proj._xy((x, y)) for x, y, _m in b_w], [m for _x, _y, m in b_w])
    matched, last_b = [], None
    for i, P in enumerate(o_s[0]):
        c = g_base.along_near(P, near)
        if last_b is not None:
            c = [m for m in c if m >= last_b - back]
        if not c:
            continue
        mb = min(c)
        matched.append((i, o_s[1][i], mb))
        last_b = max(mb, last_b) if last_b is not None else mb
    items = []
    if not matched:
        items.append([0.0, lo_len, 0.0, lb_len])
    else:
        i0, o0, b0 = matched[0]
        if i0 > 0 or b0 > jump:
            items.append([0.0, o0, 0.0, b0])
        for (i1, o1, b1), (i2, o2, b2) in zip(matched, matched[1:]):
            if i2 > i1 + 1 or (b2 - b1) - (o2 - o1) > jump:
                items.append([o1, o2, b1, max(b1, b2)])
        ik, ok, bk = matched[-1]
        if ik < len(o_s[0]) - 1 or lb_len - bk > jump:
            items.append([ok, lo_len, bk, lb_len])
    merged = []
    for it in items:
        if merged and it[0] - merged[-1][1] <= join and it[2] - merged[-1][3] <= join:
            merged[-1][1], merged[-1][3] = max(merged[-1][1], it[1]), max(merged[-1][3], it[3])
            continue
        merged.append(list(it))
    out = []
    cap = clear + 1.0
    for o0, o1, b0, b1 in merged:
        o_off, o_apart = _off(o_s, o0, o1, g_base, near, cap, join)
        b_off, b_apart = _off(b_s, b0, b1, g_opt, near, cap, join)
        p = {"option": {"from_m": round(o0, 1), "to_m": round(o1, 1), "length_m": round(o1 - o0, 1), "off": o_off},
             "base": {"from_m": round(b0, 1), "to_m": round(b1, 1), "length_m": round(b1 - b0, 1), "off": b_off},
             "leaves": [round(x, 6) for x in chainage.point_at(proj, opt, o0)],
             "rejoins": [round(x, 6) for x in chainage.point_at(proj, opt, o1)],
             "extra_m": round((o1 - o0) - (b1 - b0), 1), "apart_m": round(max(o_apart, b_apart), 1)}
        p["counts"] = _counts(p, min_run, clear)
        if p["counts"] or keep_all:
            out.append(p)
    return out


def compare(proj, opt, base, **kw):
    """One option against one base line: its pieces, where it first leaves and last rejoins (metres along both), the
    metres that differ on each, and the extra length of the whole option."""
    ps = pieces(proj, opt, base, **kw)
    lo, lb = chainage.line_length_m(proj, opt), chainage.line_length_m(proj, base)
    counted = [p for p in ps if p.get("counts", True)]
    return {"pieces": ps,
            "leaves": ({"option_m": counted[0]["option"]["from_m"], "base_m": counted[0]["base"]["from_m"],
                        "at": counted[0]["leaves"]} if counted else None),
            "rejoins": ({"option_m": counted[-1]["option"]["to_m"], "base_m": counted[-1]["base"]["to_m"],
                         "at": counted[-1]["rejoins"]} if counted else None),
            "differs_m": {"option": round(sum(p["option"]["length_m"] for p in counted), 1),
                          "base": round(sum(p["base"]["length_m"] for p in counted), 1)},
            "length_m": round(lo, 1), "base_length_m": round(lb, 1), "extra_m": round(lo - lb, 1),
            "same": not counted}


# --------------------------------------------------------------------------- #
#  The stored options of one leg, against the line in use                      #
# --------------------------------------------------------------------------- #
def _day(day):
    if isinstance(day, datetime.date):
        return day
    if day:
        return datetime.date.fromisoformat(str(day)[:10])
    return datetime.date.today()


def leg_lines(rid, profile, leg):
    """{alt: coords} of one route's stored lines for one lorry type and leg."""
    import collisions
    out = {}
    for g in db.query("SELECT alt_index, geometry FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND "
                      "vehicle_profile = ? AND leg = ? AND geometry IS NOT NULL", (db.current_tenant(), rid, profile, leg)):
        c = collisions._coords(g["geometry"])
        if len(c) >= 2:
            out[int(g.get("alt_index") or 0)] = c
    return out


def uses_of(rid, profile, leg, rows=None):
    """{alt: [use]} for one leg: each stored route_choice row that puts an option on the road, as {"kind": "diversion" |
    "busy_hours", "from", "to" (dates, a diversion), "hours_from", "hours_to", "days" (a busy-hours road), "zones",
    "status"}. An offer not accepted (a busy-hours row not in use) is left out, as route_choice.choice_on leaves it."""
    import route_choice
    out = {}
    for r in (route_choice._rows_by_route() if rows is None else rows).get(rid) or []:
        if r.get("vehicle_profile") not in (None, "", profile) or r.get("leg") not in (None, "", leg):
            continue
        if r.get("status") != "in_use" or not int(r.get("alt_index") or 0):
            continue
        kind = "busy_hours" if r.get("reason_kind") == "peak" else "diversion"
        u = {"kind": kind, "status": r.get("status"),
             "zones": [z for z in (r.get("reason_ref") or "").split(",") if z] if kind == "diversion" else []}
        if kind == "diversion":
            u.update({"from": r.get("starts_on"), "to": r.get("ends_on")})
        else:
            u.update({"hours_from": r.get("hours_from"), "hours_to": r.get("hours_to"), "days": r.get("days")})
        out.setdefault(int(r["alt_index"]), []).append(u)
    return out


def in_use_alt(rid, profile, leg, day, lines, rows=None):
    """The option on the road for this leg on `day` (a whole day: busy hours never decide it), as route_best reads it."""
    import route_choice
    ch = route_choice.choice_on(rid, profile, leg, day, rows=rows)
    alt = int(ch["alt_index"]) if ch and ch.get("status") == "in_use" else 0
    return alt if alt in lines else 0


def option_kind(alt, uses):
    """"main route" for option 0; else what puts it on the road ("diversion", "busy_hours"), else "alternative"."""
    if not alt:
        return "main route"
    ks = [u["kind"] for u in uses or []]
    return "diversion" if "diversion" in ks else ("busy_hours" if "busy_hours" in ks else "alternative")


def for_leg(rid, profile, leg, day=None, rows=None, lines=None, proj=None, base_alt=None):
    """Every stored option of one leg against the line in use on `day` (or against option `base_alt` when given: the
    public map always draws option 0 as the route): {"route", "lorry", "leg", "day", "in_use": {"alt", "kind", "uses",
    "length_m"}, "options": [{"alt", "kind", "uses", ...compare()}]}. Read only, stored data only."""
    day = _day(day)
    lines = leg_lines(rid, profile, leg) if lines is None else lines
    out = {"route": rid, "lorry": profile, "leg": leg, "day": day.isoformat(), "in_use": None, "options": []}
    if not lines:
        return out
    uses = uses_of(rid, profile, leg, rows)
    use = in_use_alt(rid, profile, leg, day, lines, rows) if base_alt is None else int(base_alt)
    if use not in lines:
        return out
    proj = proj or chainage.Proj.around(list(lines.values()))
    out["in_use"] = {"alt": use, "kind": option_kind(use, uses.get(use)), "uses": uses.get(use) or [],
                     "length_m": round(chainage.line_length_m(proj, lines[use]), 1)}
    for alt in sorted(lines):
        if alt == use:
            continue
        o = {"alt": alt, "kind": option_kind(alt, uses.get(alt)), "uses": uses.get(alt) or []}
        o.update(compare(proj, lines[alt], lines[use]))
        out["options"].append(o)
    return out


# --------------------------------------------------------------------------- #
#  What lies along a line                                                      #
# --------------------------------------------------------------------------- #
class Context:
    """One read of what the along list needs that is not per route: the route-choice rows, the routes' stored limit
    checks, the community features of the three named kinds, the cycle routes, the haul roads in force, the collision
    records. Built once for one route or for all of them; each part is read the first time it is asked for, so the
    public read (limits and haul roads only) never reads the community or collision tables."""

    def __init__(self, day=None, route_ids=None):
        import route_choice
        self.day = _day(day)
        self.tenant = db.current_tenant()
        self.route_ids = list(route_ids) if route_ids else None
        self.rows = route_choice._rows_by_route()
        # ONE projection for every route the context reads (centred on the organisation's places), so the cycle routes'
        # and the haul roads' grids are built once, and a route's metres do not depend on which other routes were read
        locs = [float(r["lat"]) for r in db.query("SELECT lat FROM locations WHERE tenant_id = ?", (self.tenant,))
                if r.get("lat") is not None]
        self.proj = chainage.Proj(sum(locs) / len(locs) if locs else 52.0)

    @functools.cached_property
    def cycle_grid(self):
        import collisions
        return collisions._SegGrid(self.proj, self.cycle) if self.cycle else None

    @functools.cached_property
    def haul_grids(self):
        out = []
        for zid, name, hl in self.haul:
            P = [self.proj._xy(c) for c in hl]
            box = (min(x for x, _ in P) - HAUL_NEAR_M, min(y for _, y in P) - HAUL_NEAR_M,
                   max(x for x, _ in P) + HAUL_NEAR_M, max(y for _, y in P) + HAUL_NEAR_M)
            out.append((zid, name, box, chainage.Grid(self.proj, hl, HAUL_NEAR_M)))
        return out

    @functools.cached_property
    def checks(self):
        import limits
        return limits.stored_checks(self.route_ids) if self.route_ids else limits.stored_checks()

    @functools.cached_property
    def places(self):
        import community
        out = []
        for f in community.features(list(PLACE_KINDS)):
            g = f.get("geometry") or {}
            if g.get("type") == "Point":
                p = f.get("properties") or {}
                out.append((p.get("kind"), p.get("name") or None, g["coordinates"][:2]))
        return out

    @functools.cached_property
    def cycle(self):
        import collisions
        return collisions.cycle_lines()

    @functools.cached_property
    def records(self):
        import collisions
        if not (collisions.status() or {}).get("years"):
            return []
        keys = None
        if self.route_ids:
            keys = [k for rid in self.route_ids for k in self._keys(rid)]
        return collisions.records(keys)

    def _keys(self, rid):
        import collisions
        alts = {int(g.get("alt_index") or 0) for g in db.query(
            "SELECT DISTINCT alt_index FROM route_geometry WHERE tenant_id = ? AND route_id = ?", (self.tenant, rid))}
        return [collisions.route_key(rid, a) for a in sorted(alts | {0})]

    @functools.cached_property
    def haul(self):
        """[(zone id, name, line)] of the haul roads in force on the day (zones.haul_roads, the public map's own list)."""
        import zones
        out = []
        try:
            for z in zones.haul_roads(on=self.day.isoformat()):
                line = zones.as_line(z["geometry"])
                if line and len(line) >= 2:
                    out.append((z["id"], z.get("name"), line))
        except Exception:
            pass
        return out


def _limits_on(rid, profile, leg, alt, line, proj, ctx):
    """The stored limit hits of this leg's line (the lorry's own, on this option) that the lorry is at or over, placed
    by their anchor as the Route analysis places them; and the counts of those left out (within, unknown)."""
    import limits
    st = ctx.checks.get(rid) or {}
    rows, left = [], {}
    for h in st.get("hits") or []:
        if not isinstance(h, dict) or h.get("vehicle_profile") != profile or h.get("leg") != leg:
            continue
        if int(h.get("alt_index") or 0) != alt:
            continue
        v = h.get("verdict")
        if v not in AT_OR_OVER:
            left[v or "unknown"] = left.get(v or "unknown", 0) + 1
            continue
        a = h.get("anchor")
        off, at = (chainage.project(proj, line, (a[0], a[1])) if a and a[0] is not None else (None, None))
        value = None
        if h.get("limit") is not None:
            value = limits.icon_text(h.get("kind"), float(h["limit"])).replace("T", "t")
        rows.append({"what": "limit", "at_m": round(at, 1) if at is not None else None,
                     "off_m": round(off, 1) if off is not None else None,
                     "kind": h.get("kind"), "value": value, "limit": h.get("limit"), "unit": h.get("unit"),
                     "verdict": v, "allowed": v == "allowed", "point": bool(h.get("point")),
                     "road": h.get("name") or None, "ref": h.get("ref") or None, "exceptions": h.get("exceptions"),
                     "run_m": h.get("along_m")})
    return rows, {"checked": st.get("checked_at"), "left_out": left}


def _places_on(line, proj, ctx):
    import route_compare
    near = route_compare.NEAR_M
    xs = [c[0] for c in line]
    ys = [c[1] for c in line]
    pad_x, pad_y = (max(near.get(k, 250) for k in PLACE_KINDS) + 50) / proj.kx, 300 / proj.ky
    box = (min(xs) - pad_x, min(ys) - pad_y, max(xs) + pad_x, max(ys) + pad_y)
    out = []
    grid = chainage.Grid(proj, line, max(near.get(k, 250) for k in PLACE_KINDS))
    for kind, name, p in ctx.places:
        if not (box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]):
            continue
        off, at = grid.nearest(proj._xy(p))
        if at is not None and off <= near.get(kind, 250):
            out.append({"what": "place", "at_m": round(at, 1), "off_m": round(off), "kind": kind, "name": name})
    return out


def _cycle_on(line, proj, ctx):
    import collisions
    if ctx.cycle_grid is None:
        return []
    meets = collisions.cycle_along(proj, line, ctx.cycle_grid)["meets"]
    return [{"what": "cycle", "at_m": round(m, 1), "name": n} for m, n in meets]


def _haul_on(line, proj, ctx):
    """The stretches of the line within HAUL_NEAR_M of a haul road in force: the public map's withHaulPieces, on the
    line's own vertices, with each stretch's metres along."""
    if not ctx.haul:
        return []
    ch = chainage.vertex_chainage(proj, line)
    grids = ctx.haul_grids
    out, run = [], None
    for i, c in enumerate(line):
        P = proj._xy(c)
        hit = next(((zid, name) for zid, name, bx, g in grids
                    if bx[0] <= P[0] <= bx[2] and bx[1] <= P[1] <= bx[3] and g.dist(P) <= HAUL_NEAR_M), None)
        if hit and run and run["zone"] == hit[0]:
            run["to_m"] = ch[i]
            run["n"] += 1
            continue
        if run and run["n"] >= 2:
            out.append(run)
        run = {"zone": hit[0], "name": hit[1], "from_m": ch[i], "to_m": ch[i], "n": 1} if hit else None
    if run and run["n"] >= 2:
        out.append(run)
    return [{"what": "haul_road", "at_m": round(r["from_m"], 1), "to_m": round(r["to_m"], 1),
             "zone": r["zone"], "name": r["name"]} for r in out]


def _stretches_on(rid, line, proj, ctx):
    """The collision evidence's numbered stretches (collisions.stretches) cut on THIS line from the collisions stored
    for the route that lie within collisions.ON_ROUTE_M of it."""
    import collisions
    if not ctx.records:
        return []
    on = []
    grid = chainage.Grid(proj, line, collisions.ON_ROUTE_M)
    for c in ctx.records:
        if not any(collisions.route_key(rid) == k or str(k).startswith(f"{rid}@") for k in (c.get("routes") or {})):
            continue
        off, at = grid.nearest(proj._xy((c["lon"], c["lat"])))
        if at is not None:
            on.append((at, c))
    on.sort(key=lambda mc: (mc[0], mc[1]["collision_id"]))
    if not on:
        return []
    parts = collisions.stretches(on, chainage.line_length_m(proj, line))
    return [{"what": "stretch", "at_m": round(s["from_m"], 1), "to_m": round(s["to_m"], 1), "no": s.get("no"),
             "road": s.get("road"), "collisions": len(s.get("on") or [])} for s in parts]


def along(rid, profile, leg, day=None, ctx=None):
    """What lies along the line in use of one leg on `day`, as ONE list ordered by metres from A (see the module's
    docstring): {"route", "lorry", "leg", "day", "alt", "length_m", "items", "limits", "gaps", "pieces"}. A diversion
    in use on the day IS the line: its rows then say where that line leaves the usual road ("in_use": True)."""
    ctx = ctx or Context(day, [rid])
    day = ctx.day
    lines = leg_lines(rid, profile, leg)
    out = {"route": rid, "lorry": profile, "leg": leg, "day": day.isoformat(), "alt": None, "length_m": None,
           "items": [], "limits": None, "gaps": GAPS}
    if not lines:
        return out
    use = in_use_alt(rid, profile, leg, day, lines, ctx.rows)
    line = lines[use]
    proj = ctx.proj
    out["alt"], out["length_m"] = use, round(chainage.line_length_m(proj, line), 1)
    items = []
    lim, out["limits"] = _limits_on(rid, profile, leg, use, line, proj, ctx)
    items += lim
    items += _places_on(line, proj, ctx)
    items += _cycle_on(line, proj, ctx)
    items += _stretches_on(rid, line, proj, ctx)
    items += _haul_on(line, proj, ctx)
    # the pieces of the options that come onto the road in their dates or hours, against the line in use
    pieces_of = for_leg(rid, profile, leg, day, rows=ctx.rows, lines=lines, proj=proj)
    on_road = pieces_of["in_use"] or {}
    for o in pieces_of["options"]:
        if o["kind"] in ("diversion", "busy_hours"):
            kind, uses, in_use = o["kind"], o["uses"], False
        elif o["kind"] == "main route" and on_road.get("kind") == "diversion":
            kind, uses, in_use = "diversion", on_road.get("uses") or [], True
        else:
            continue
        for u in uses:
            if u.get("kind") != kind:
                continue
            for p in o["pieces"]:
                row = {"what": kind, "alt": on_road.get("alt") if in_use else o["alt"], "in_use": in_use,
                       "at_m": p["base"]["from_m"], "to_m": p["base"]["to_m"],
                       "option_m": [p["option"]["from_m"], p["option"]["to_m"]],
                       "extra_m": -p["extra_m"] if in_use else p["extra_m"]}
                if kind == "diversion":
                    row.update({"from": u.get("from"), "to": u.get("to"), "zones": u.get("zones")})
                else:
                    row.update({"hours_from": u.get("hours_from"), "hours_to": u.get("hours_to"), "days": u.get("days")})
                items.append(row)
    order = {"limit": 0, "diversion": 1, "busy_hours": 2, "haul_road": 3, "stretch": 4, "place": 5, "cycle": 6}
    items.sort(key=lambda r: (r["at_m"] is None, r["at_m"] if r["at_m"] is not None else 0, order.get(r["what"], 9)))
    out["items"] = items
    out["pieces"] = pieces_of
    return out


# --------------------------------------------------------------------------- #
#  All routes, and the public map's share                                      #
# --------------------------------------------------------------------------- #
def lorry_for(rid, profile=None):
    """The lorry type a read is for: `profile` when the route has a line for it (else None), else the public map's own
    choice (network.DEFAULT_PROFILE when the route has a line for it, else the first by name)."""
    import network
    have = sorted({g["vehicle_profile"] for g in db.query(
        "SELECT DISTINCT vehicle_profile FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND geometry IS NOT NULL",
        (db.current_tenant(), rid))})
    if profile:
        return profile if profile in have else None
    if not have:
        return None
    return network.DEFAULT_PROFILE if network.DEFAULT_PROFILE in have else have[0]


def along_all(day=None, legs=("loaded", "return")):
    """`along` for every route (the public map's lorry type, each leg) through ONE Context: {route: {leg: along}}.
    For the timing of all 50 and for a later reader that needs every route at once; no endpoint serves it yet."""
    ctx = Context(day)
    out = {}
    for r in db.query("SELECT id FROM routes WHERE tenant_id = ? ORDER BY id", (ctx.tenant,)):
        prof = lorry_for(r["id"])
        if prof:
            out[r["id"]] = {leg: along(r["id"], prof, leg, ctx=ctx) for leg in legs}
    return out


#: what the public read carries: the things the public map is already sent today (network.public_map_data, its
#: route-alternatives and its limits). Places, cycle routes and the collision evidence are staff only (the community
#: and collision layers answer 401 to the map's cookie), so they never reach it.
PUBLIC_WHATS = ("limit", "haul_road")          # the items; the options (alternatives, diversions, busy hours) beside
#: what of an option's use the public read carries (network.public_map_data sends a diversion's periods and zones and a
#: busy-hours road's hours, never its days)
PUBLIC_USE_KEYS = ("kind", "from", "to", "zones", "hours_from", "hours_to")


def public(rid, leg, profile=None, day=None):
    """The public map's share of one leg: every stored option against option 0 (the line the public map draws as the
    route; a diversion and a busy-hours road come with their dates or hours, as map-data sends them), the haul-road
    stretches of option 0, and the limits the public map's own collection lists for this route (an Approved lorry over
    it, "exceeds" or "allowed"). Nothing new becomes public: see PUBLIC_WHATS."""
    prof = lorry_for(rid, profile)
    out = {"route": rid, "leg": leg, "lorry": prof, "length_m": None, "options": [], "items": []}
    if not prof:
        return out
    ctx = Context(day, [rid])
    lines = leg_lines(rid, prof, leg)
    if 0 not in lines:
        return out
    proj = ctx.proj
    f = for_leg(rid, prof, leg, ctx.day, rows=ctx.rows, lines=lines, proj=proj, base_alt=0)
    out["length_m"] = f["in_use"]["length_m"] if f["in_use"] else None
    for o in f["options"]:
        row = {k: o[k] for k in ("alt", "kind", "pieces", "leaves", "rejoins", "differs_m", "length_m", "extra_m", "same")}
        # a use as map-data sends it: a diversion's dates and zones, a busy-hours road's hours (map-data sends no days)
        row["uses"] = [{k: v for k, v in u.items() if k in PUBLIC_USE_KEYS} for u in o["uses"]]
        out["options"].append(row)
    planned = {(r["route_id"], r["vehicle_type"]) for r in db.query(
        "SELECT DISTINCT route_id, vehicle_type FROM forecasts WHERE tenant_id = ? AND status = 'Approved' AND route_id = ?",
        (ctx.tenant, rid))}
    lim, _info = _limits_on(rid, prof, leg, 0, lines[0], proj, ctx)
    items = [dict(r, verdict=r["verdict"]) for r in lim
             if r["verdict"] in ("exceeds", "allowed") and (rid, prof) in planned]
    items += _haul_on(lines[0], proj, ctx)
    for r in items:
        r.pop("run_m", None)
        r.pop("off_m", None)
    items.sort(key=lambda r: (r["at_m"] is None, r["at_m"] if r["at_m"] is not None else 0))
    out["items"] = items
    return out
