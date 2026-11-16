"""
The best option for a route (16 Nov 2026, step 1a of the "best option" idea). John, 13 Nov: "a comparison of the complete
analysis … to give an overall best decision and why". His decisions of 16 Nov (notes: session-1116-best-option-check.md
§4b to §4h) are the spec; this module is the RULE only: no screen, no export, nothing a person reads yet. The card on the
Routes page and the summary page of the Route analysis file are later branches.

For one route, one lorry type and one day, evaluate() returns ONE answer:

  "Suggested"               one stored option is clearly ahead on at least one head and behind on none;
  "A trade-off"             heads pull apart: the trade in one line, NO pick (Q3; the planner decides);
  "Keep the route in use"   nothing else is clearly ahead, every other option is ruled out, or a check the answer needs
                            is missing (then `held_back` says which);

with the heads, every count behind them and fixed sentences. The rule decides and fixed sentences write (Q2): no model
decides or words anything here.

How each decision of John's is held (section numbers of the 16 Nov note):
  * The route in use (4, point 4) is worked out per lorry type, leg and DAY: route_choice.choice_on, so on a dated zone's
    days a leg's line in use is the diversion's option (a HERE alternative or a way round), not option 0. Every option is
    compared against THAT pair of lines; an option that crosses a routing zone in force on the day is ruled out (it would
    put lorries back through the closure). A busy-hours road in use (route_choice.busy_alt_at) is the line in use at the
    busy hour it covers, and is used for the Busy hours head only (the plan's own 10:00 figures stay on the zone rows).
  * The lorry (N2): the one the route's Approved loads mostly use (whole loads per forecast line, derived's rule); with no
    Approved load, route_compare.PROFILE where the route holds it, else the first stored lorry type, said in lorry_basis.
  * Limits first (N1): an option is ruled out only by a lorry limit below the lorry that it ADDS over the line in use on
    the same leg (route_choice._below_keys on each, the one matching rule of limits_added). A limit both lines meet is not
    new. "Except for access" is a limit below the lorry like any other (route_choice's rule) and keeps its note. With NO
    limits held at all nothing is suggested (SUGGEST_NEEDS_LIMITS): no option could have been checked.
  * Collisions (4c, 4e): on-the-road counts per option, all and goods-vehicle, measured at read from each stored record's
    position to the option's OWN two lines (its loaded line and the return line it is costed with), within
    collisions.ON_ROUTE_M, on the fetch's own thinned lines and projection (collisions.RouteIndex); a collision near both
    lines counts once. The route in use is counted the same way on its own pair. (16 Nov evening, the mother session's
    first live read: the stored distances are keyed by option NUMBER with both legs pooled, so an option costed with the
    main line's way back counted every collision of the main line too and could never read "fewer"; R003's Alt 1 and
    Alt 2 read 29 against 23 on live. Counting on the lines retires that, and Make primary no longer moves a count.)
    "Clearly fewer" by the app's own exact test (OFFER_MIN, OFFER_P). Never in a percentage, never a rate or a ratio,
    said in plain words with the two counts.
  * What the collision history still guards (finding 4, narrowed): the fetch keeps only the collisions within
    collisions.NEAR_ROUTE_M (250 m) of the lines it searched. A line routed after the fetch can run on a road the fetch
    never searched, so its count could be short. history_state() compares the route's set of lines now with the set the
    fetch searched (fingerprints, kept by the fetch since 16 Nov), whatever option number each sits under (a Make primary
    swap changes no line, so it reads current); for a fetch made before that, a line routed after the fetch. Out of
    date: no collision part is counted, the answer says so, and nothing is suggested (SUGGEST_NEEDS_COLLISIONS).
  * Both legs (N3): left turns, cycle routes met and distance beside a cycle route are a ROUND trip's (the loaded leg plus
    the return leg route_analysis costs).
  * Community places (4d): schools, hospitals and health centres within 250 m decide; the other kinds are returned as
    shown only.
  * Percentages (4f): one for each measure of the cycle part and one for community places, each beside its two counts;
    NO blended exposure figure, and no average of the cycle measures either. A count alone where the base is under
    PCT_BASE_MIN or is 0; a part moves on the DIFFERENCE of counts, so a rise from 0 still shows.
  * The gate (finding 7, step 2): the cycle and community parts move the answer only once the community layer was fetched
    along every option (community.status()["all_options"], added by claude/community-all-options; a missing key = False).
    While closed they are returned, marked counted: False, and move nothing.
  * Time (round trip, trips a day), Busy hours (08:00 and 17:00 where held) and Carbon are heads beside People.
  * N5: an option shorter in km whose driving takes longer is never "Suggested"; "A trade-off" at most.
  * The card's two extra fields (John's yes to the third draft, 16 Nov evening): `trade_short`, the trade in one line
    naming the heads only, at most SHORT_MAX (25) words, the long `trade` kept for "All figures" and the file; and
    `in_use_limits`, the lorry limits below the lorry that the line in use itself meets (site-allowed ones left out),
    reported only: the answer does not change for them.

Every threshold is a named constant below: STARTING VALUES that John has not set (he sets them on the all-50 table, Q9).

WHAT IS NOT VERIFIED: run on stubbed and local lines only; never on live's figures (local worktree databases hold stand-in
lines and no limits). Collisions are counted on the chosen lorry's own lines; the RECORDS a route is measured against are
those the fetch kept near any of the route's searched lines (every lorry type), so a lorry type whose line was never
searched is caught by history_state only through its fingerprint. A count beside a road is not a risk.
"""
import datetime
import math

import collisions
import community
import conversions
import db
import derived
import network
import route_choice
import route_compare
import zones

# --------------------------------------------------------------------------- #
#  Thresholds: STARTING VALUES. John has not set any of them (Q9: he sets      #
#  them on the all-50 table this module's admin read gives).                   #
# --------------------------------------------------------------------------- #
TIME_MIN = 2.0          # minutes a round trip: a gap under max(TIME_MIN, TIME_PCT of the in-use driving) is "the same"
TIME_PCT = 0.03
CARBON_PCT = 0.05       # a carbon gap under 5 % of the in-use trip's kg CO2e is "the same"
LEFT_TURNS = 2          # left turns a round trip: a gap of this many or more counts
CYCLE_MEETS = 2         # cycle routes met a round trip: a gap of this many or more counts
BESIDE_KM = 1.0         # km beside a cycle route a round trip: a gap of this much or more counts
PLACES = 2              # schools, hospitals and health centres passed a round trip: a gap of this many or more counts
SLOWER_MIN = 0.0        # N5: shorter in km AND more than this many minutes' more driving a round trip = never "Suggested"
PCT_BASE_MIN = 5        # 4f: a percentage only where the in-use count is at least this (else the counts alone)
PCT_BASE_KM = 1.0       # ...and for km beside a cycle route, where the in-use distance is at least this
COLLISIONS_MIN = collisions.OFFER_MIN   # "clearly": at least this many on the side with more (the busy-hours offer's test)…
COLLISIONS_P = collisions.OFFER_P       # …and a gap this big comes by chance less than this often (an exact test)
SUGGEST_NEEDS_LIMITS = True             # no "Suggested" while no lorry limit is held at all (nothing could be checked)
SUGGEST_NEEDS_COLLISIONS = True         # no "Suggested" while the route's collision history is missing or out of date

# --------------------------------------------------------------------------- #
#  Fixed by John's decisions, not thresholds                                   #
# --------------------------------------------------------------------------- #
DECIDING_KINDS = ("schools", "hospitals", "health")    # 4d; = route_analysis_doc.NAMED_KINDS (asserted)
SHOWN_KINDS = tuple(k for k in route_compare.KINDS if k not in DECIDING_KINDS)
PLACES_M = 250                                          # = route_compare.NEAR_M for the three (asserted)
BUSY_HOURS = ("08:00", "17:00")
MAX_HERE_ALT = route_compare.MAX_HERE_ALT
SUGGESTED, TRADE_OFF, KEEP = "Suggested", "A trade-off", "Keep the route in use"
ANSWERS = (SUGGESTED, TRADE_OFF, KEEP)
NOT_FETCHED_WORDS = ("Cycle routes and community places are shown, not counted: they have not been fetched along every "
                     "option yet.")
STALE_WORDS = ("Collision history out of date: this route was routed again after the last collision fetch, so a road "
               "on it may not have been searched; collisions are not compared until it is fetched again.")
NO_HISTORY_WORDS = "Collisions are not compared: the collision history has not been fetched."
NO_LIMITS_WORDS = "No road limits are held, so no other option could be checked against them."

#: a head's or a part's value: +1 the option is ahead, -1 behind, 0 the same, MIXED both, None not counted
MIXED = 2
_PART_WORDS = {1: "fewer", 0: "same", -1: "more", MIXED: "mixed"}
_HEAD_WORDS = {"people": _PART_WORDS, "time": {1: "quicker", 0: "same", -1: "slower", MIXED: "mixed"},
               "busy": {1: "quicker", 0: "same", -1: "slower", MIXED: "mixed"},
               "carbon": {1: "less", 0: "same", -1: "more", MIXED: "mixed"}}


def thresholds():
    """Every threshold and fixed value the rule used, for the table's head (so a figure can be read against its rule)."""
    return {"time_min": TIME_MIN, "time_pct": TIME_PCT, "carbon_pct": CARBON_PCT, "left_turns": LEFT_TURNS,
            "cycle_meets": CYCLE_MEETS, "beside_km": BESIDE_KM, "places": PLACES, "slower_min": SLOWER_MIN,
            "pct_base_min": PCT_BASE_MIN, "pct_base_km": PCT_BASE_KM, "collisions_min": COLLISIONS_MIN,
            "collisions_p": COLLISIONS_P, "suggest_needs_limits": SUGGEST_NEEDS_LIMITS,
            "suggest_needs_collisions": SUGGEST_NEEDS_COLLISIONS, "places_m": PLACES_M,
            "on_route_m": collisions.ON_ROUTE_M, "deciding_kinds": list(DECIDING_KINDS), "busy_hours": list(BUSY_HOURS),
            "set_by_john": False}


# --------------------------------------------------------------------------- #
#  Small pure helpers (the rule itself)                                        #
# --------------------------------------------------------------------------- #
def clearly(use_n, opt_n):
    """+1 the option had clearly fewer than the line in use, -1 clearly more, 0 no clear gap (collisions.chance_of_fewer,
    at least COLLISIONS_MIN on the side with more, chance under COLLISIONS_P)."""
    if use_n >= COLLISIONS_MIN and collisions.chance_of_fewer(use_n, opt_n) < COLLISIONS_P:
        return 1
    if opt_n >= COLLISIONS_MIN and collisions.chance_of_fewer(opt_n, use_n) < COLLISIONS_P:
        return -1
    return 0


def step(diff, t):
    """+1 when the option has `t` or more fewer (diff = option - in use), -1 when `t` or more more, else 0."""
    if diff is None:
        return None
    return 1 if diff <= -t else -1 if diff >= t else 0


def mix(vals):
    """Several parts into one: MIXED when one is ahead and another behind (or mixed), else the one way, else 0. Parts not
    counted (None) are left out; None when none is counted."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    ahead, behind = any(v == 1 for v in vals), any(v in (-1, MIXED) for v in vals)
    return MIXED if (ahead and behind) else 1 if ahead else -1 if behind else 0


def pct(opt, use, base_min):
    """The change from the in-use figure as a whole percentage, or None where the base is under base_min or 0 (4f: the
    counts are then given alone)."""
    if opt is None or use is None or use == 0 or use < base_min:
        return None
    return int(round((opt - use) / use * 100))


def label(alt):
    """'The main route' (option 0), 'Alt 2', 'Way round' (a line baked round a closed zone)."""
    a = int(alt or 0)
    if not a:
        return "The main route"
    if a >= route_choice.WAY_ROUND_BASE:
        n = a - route_choice.WAY_ROUND_BASE + 1
        return "Way round" + (f" {n}" if n > 1 else "")
    return f"Alt {a}"


def _join(xs):
    xs = [x for x in xs if x]
    return "" if not xs else xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def date_words(v):
    """'2027-12-17' -> '17 Dec 2027': the app's date words (clp_doc._date_words' rule, asserted equal; that module is not
    imported here, it brings the whole document build). No sentence of the rule carries an ISO date (pinned)."""
    try:
        d = datetime.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return str(v or "")
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def _legs_words(legs):
    """' (both legs)' or ' (loaded leg)': a thing an option meets on both legs is said once."""
    legs = sorted(set(legs))
    return " (both legs)" if len(legs) > 1 else f" ({legs[0]} leg)"


def _n(x, d=1):
    """A figure as words: whole where it is whole."""
    if x is None:
        return "–"
    x = round(float(x), d)
    return str(int(x)) if x == int(x) else f"{x:.{d}f}"


def _parse_ts(v):
    if not v:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- #
#  The context: what every route's answer reads, read once                    #
# --------------------------------------------------------------------------- #
class Context:
    """One read of everything the rule needs that is not per route: the routes and their analysis rows (one `pre`,
    network.prefetch_analysis_geometry), the route-choice rows, the zones in force, the lorry limits, the collision
    records and the fetch's searched lines, the community features and cycle routes, the Approved loads. A route's own
    lines are read when the route is evaluated and dropped after (they are the heavy part)."""

    def __init__(self, day=None, pre=None):
        self.day = day or datetime.date.today()
        # the busy hours are weekday hours (route_choice.BUSY_DAYS): a weekend day reads the next Monday's
        bd = self.day
        while bd.weekday() >= 5:
            bd += datetime.timedelta(days=1)
        self.busy_day = bd
        self.tenant = db.current_tenant()
        self.factors = conversions.load_factors()
        self.pre = pre if pre is not None else {}
        network.prefetch_analysis_geometry(self.pre)
        self.routes = self.pre["routes"]
        self.locs = {l["id"]: l for l in db.query("SELECT id, name, lat, lon FROM locations WHERE tenant_id = ?",
                                                  (self.tenant,))}
        self.choice_rows = route_choice._rows_by_route()
        self.zones_on = [z for z in route_choice.dated_zones() if zones.applies_on(z, self.day.isoformat())]
        self.lims = route_choice._load_limits()
        # collisions
        self.col_status = collisions.status() or {}
        self.col_meta = collisions._detail(collisions._meta_row()) or {}
        self.fetched_at = _parse_ts(self.col_status.get("fetched_at"))
        self.fetched = bool(self.fetched_at) and bool(self.col_status.get("years"))
        self.searched = collisions.searched_keys()
        prints = self.col_meta.get("searched_prints")
        self.searched_prints = ({k: set(v) for k, v in prints.items()} if isinstance(prints, dict) else None)
        self.records = {}
        if self.fetched:
            for c in collisions.records():
                for rid in {route_choice.base_of(k) for k in (c.get("routes") or {})}:
                    self.records.setdefault(rid, []).append(c)
        self.period = self.col_status.get("period") or ""
        # community: the gate, the features (once), the cycle routes on one projection
        self.community_all = bool((community.status() or {}).get("all_options"))
        self.features = []
        for f in community.features(list(route_compare.KINDS)):
            pts = route_compare._points(f.get("geometry"))
            if pts:
                self.features.append((f["properties"]["kind"], pts, (min(p[0] for p in pts), min(p[1] for p in pts),
                                                                      max(p[0] for p in pts), max(p[1] for p in pts))))
        sites = [(lid, l.get("name") or lid, float(l["lon"]), float(l["lat"])) for lid, l in self.locs.items()
                 if l.get("lat") is not None and l.get("lon") is not None]
        self.proj = collisions.RouteIndex([], sites)
        cl = collisions.cycle_lines()
        self.grid = collisions._SegGrid(self.proj, cl) if cl else None
        self.loads = approved_loads(self.factors)

    def searched_lines(self, rid):
        """{fingerprint} of every line of this route the last fetch searched (any option number), or None when the fetch
        kept no fingerprints (a fetch made before 16 Nov)."""
        if self.searched_prints is None:
            return None
        return {p for k, v in self.searched_prints.items() if route_choice.base_of(k) == rid for p in v}

    def route_lines(self, rid):
        """{(profile, leg, alt): coords}, {route_key: {fingerprint}} and the lines' computed_at, for one route."""
        import here_routing
        lines, prints, computed = {}, {}, []
        for g in db.query("SELECT vehicle_profile, leg, alt_index, geometry, computed_at FROM route_geometry "
                          "WHERE tenant_id = ? AND route_id = ? AND geometry IS NOT NULL", (self.tenant, rid)):
            coords = collisions._coords(g["geometry"])
            if len(coords) < 2:
                continue
            alt = int(g.get("alt_index") or 0)
            lines[(g["vehicle_profile"], g["leg"], alt)] = coords
            prints.setdefault(collisions.route_key(rid, alt), set()).add(here_routing._fingerprint(coords))
            computed.append(_parse_ts(g.get("computed_at")))
        return lines, prints, computed


def approved_loads(factors):
    """{route_id: {lorry type: whole loads}} over the Approved forecast lines: a line in vehicles is its count, any other
    unit its tonnes over the lorry's payload, rounded up per line (derived.day_figures' rule)."""
    out = {}
    try:
        rows = db.query("SELECT route_id, quantity, unit, material_type, vehicle_type FROM forecasts WHERE tenant_id = ? "
                        "AND status = 'Approved'", (db.current_tenant(),))
    except Exception:
        return out
    for r in rows:
        veh = r.get("vehicle_type")
        if not veh:
            continue
        q = float(r.get("quantity") or 0)
        if q <= 0:
            continue
        payload = float(derived.payload_for(veh, factors)[0] or 0)
        if r.get("unit") == "vehicles":
            n = derived._ceil(q)
        else:
            try:
                t = derived.tonnes_of(q, {"unit": r.get("unit"), "material_type": r.get("material_type"),
                                          "vehicle_type": veh, "payload_t": payload}, factors)
            except Exception:
                continue
            n = derived._ceil(t / payload) if payload > 0 else 0
        d = out.setdefault(r["route_id"], {})
        d[veh] = d.get(veh, 0) + n
    return out


def pick_lorry(rid, ctx, profiles):
    """(lorry, basis): N2, the lorry type the route's Approved loads mostly use (ties: the lower name), among the types
    with a stored line; else route_compare.PROFILE where stored; else the first stored type."""
    loads = {v: n for v, n in (ctx.loads.get(rid) or {}).items() if v in profiles and n > 0}
    if loads:
        best = sorted(loads, key=lambda v: (-loads[v], v))[0]
        return best, "approved loads"
    if not profiles:
        return None, "no stored line"
    if route_compare.PROFILE in profiles:
        return route_compare.PROFILE, "no approved loads"
    return sorted(profiles)[0], "no approved loads"


def history_state(rid, prints, computed, ctx):
    """'current', 'out_of_date' or 'not_fetched' for this route's collision counts. The counts are measured on the lines
    themselves, so what can go stale is only WHICH collisions the fetch kept: those within 250 m of the lines it searched.
    With the fetch's own fingerprints: out of date when the route now holds a line the fetch did not search, under any
    option number (a Make primary swaps numbers, not lines: current). For a fetch made before 16 Nov (no fingerprints
    kept): out of date when a line of the route was routed after the fetch. A line the fetch searched that has since
    gone does not matter (its collisions are kept, just not read)."""
    if not ctx.fetched:
        return "not_fetched"
    searched = ctx.searched_lines(rid)
    if searched is not None:
        now = {p for v in prints.values() for p in v}
        return "current" if now <= searched else "out_of_date"
    if any(t is not None and t > ctx.fetched_at for t in computed):
        return "out_of_date"
    return "current"


# --------------------------------------------------------------------------- #
#  One option's counts                                                         #
# --------------------------------------------------------------------------- #
def _places(legs, ctx):
    """{kind: how many} of the community features within route_compare.NEAR_M[kind] of a round trip's lines (each place
    once). The rule of route_compare.near_counts, on these lines only."""
    out = {k: 0 for k in route_compare.KINDS}
    pts = [p for l in legs for p in l]
    if not pts:
        return out
    pad = 0.005
    box = (min(p[0] for p in pts) - pad, min(p[1] for p in pts) - pad, max(p[0] for p in pts) + pad,
           max(p[1] for p in pts) + pad)
    idx = collisions.RouteIndex([("o", community._thin(l)) for l in legs], [])
    for kind, fpts, fb in ctx.features:
        if fb[2] < box[0] or fb[0] > box[2] or fb[3] < box[1] or fb[1] > box[3]:
            continue
        best = None
        for p in fpts:
            d = idx.near(p[0], p[1])[0].get("o")
            if d is not None and (best is None or d < best):
                best = d
        if best is not None and best <= route_compare.NEAR_M[kind]:
            out[kind] += 1
    return out


def count_on_lines(recs, legs):
    """{"all", "goods"}: the collisions of `recs` within collisions.ON_ROUTE_M of any of these lines, each collision once.
    Measured from the record's own position to the lines thinned as the fetch thins them (community._thin) on the
    fetch's index (collisions.RouteIndex), so a distance here is the one the fetch would have stored for that line."""
    n = {"all": 0, "goods": 0}
    legs = [community._thin(l) for l in legs if l and len(l) >= 2]
    if not legs:
        return n
    idx = collisions.RouteIndex([(str(i), l) for i, l in enumerate(legs)], [], route_m=collisions.ON_ROUTE_M, site_m=0)
    for c in recs:
        lon, lat = c.get("lon"), c.get("lat")
        if lon is None or lat is None or not idx.in_box(float(lon), float(lat)):
            continue
        if idx.near(float(lon), float(lat))[0]:
            n["all"] += 1
            n["goods"] += 1 if c.get("goods") else 0
    return n


def measures(rid, row, lines, lorry, ctx):
    """The counts of one costed pair (a route_analysis row): both legs' lines, km, minutes, trips, carbon, busy-hour
    cycles, collisions on the road, left turns, cycle routes, places."""
    la, ra = int(row["alt_index"]), row.get("return_alt_used")
    legs = [lines.get((lorry, "loaded", la))]
    if ra is not None:
        legs.append(lines.get((lorry, "return", int(ra))))
    legs = [l for l in legs if l and len(l) >= 2]
    left = sum(len(collisions.left_turns(ctx.proj, l, ctx.grid)) for l in legs)
    meets = beside = None
    if ctx.grid is not None:
        meets, beside_m = 0, 0
        for l in legs:
            cy = collisions.cycle_along(ctx.proj, l, ctx.grid)
            meets += len(cy["meets"])
            beside_m += len(cy["beside_m"]) * 10
        beside = round(beside_m / 1000.0, 2)
    places = _places(legs, ctx)
    # the option numbers the pair is stored under (an older fetch's "searched" list is by number) and its lines' prints
    keys = {collisions.route_key(rid, la)} | ({collisions.route_key(rid, int(ra))} if ra is not None else set())
    import here_routing
    col = count_on_lines(ctx.records.get(rid, ()), legs)
    hrs = row.get("hours") or {}
    return {"loaded_alt": la, "return_alt": (int(ra) if ra is not None else None), "keys": sorted(keys),
            "prints": sorted({here_routing._fingerprint(l) for l in legs}),
            "km": round(float(row.get("total_km") or 0), 2),
            "drive_min": round((float(row.get("loaded_hr") or 0) + float(row.get("return_hr") or 0)) * 60, 1),
            "cycle_min": round(float(row.get("cycle_hr") or 0) * 60, 1),
            "trips": int(row.get("trips_per_day") or 0), "co2_kg": float(row.get("co2_kg_per_trip") or 0),
            "busy_min": {h: (round(hrs[h] * 60, 1) if hrs.get(h) is not None else None) for h in BUSY_HOURS},
            "collisions": col["all"], "goods": col["goods"],
            "left_turns": left, "cycle_meets": meets, "cycle_beside_km": beside,
            "places": sum(places[k] for k in DECIDING_KINDS), "by_kind": places,
            "shown": {k: places[k] for k in SHOWN_KINDS}}


# --------------------------------------------------------------------------- #
#  One route                                                                   #
# --------------------------------------------------------------------------- #
def _limit_words(L):
    try:
        import limits
        w = limits.headline(L)
    except Exception:
        w = f"{L.get('kind')} {L.get('value')}"
    if L.get("exceptions"):
        w += f" ({str(L['exceptions']).lower()}: a lorry may use it to reach premises on it)"
    return w


def _ruled_out(opt_legs, use_legs, lorry, ctx):
    """[reason words] and [added limits] for one option: a routing zone in force it crosses; a lorry limit below the lorry
    it ADDS over the line in use on the same leg (N1)."""
    reasons, added = [], []
    crossed = {}                     # each zone named once, with the legs that cross it (16 Nov: it was said a leg)
    for leg, line in opt_legs.items():
        if not line:
            continue
        for i, z in enumerate(ctx.zones_on):
            try:
                hit = zones.line_hits_geometry(line, z["geometry"])
            except Exception:
                hit = False
            if hit:
                crossed.setdefault(z.get("id") or i, [z, []])[1].append(leg)
    for z, legs in crossed.values():
        until = z.get("ends_on")
        reasons.append(f"it crosses {z.get('name') or 'a closed area'}, closed"
                       + (f" until {date_words(until)}" if until else "") + _legs_words(legs))
    if ctx.lims:
        by_key = {(L.get("source"), L.get("ext_id"), L.get("kind")): L for L in ctx.lims}
        for leg, line in opt_legs.items():
            if not line:
                continue
            new = route_choice._below_keys(line, lorry, leg, ctx.lims) - route_choice._below_keys(
                use_legs.get(leg), lorry, leg, ctx.lims)
            for k in sorted(new, key=lambda x: tuple(str(v) for v in x)):
                L = by_key.get(k) or {"kind": k[2], "value": None}
                added.append({"leg": leg, "source": k[0], "ext_id": k[1], "kind": k[2], "words": _limit_words(L),
                              "except_for_access": bool(L.get("exceptions"))})
        if added:
            # each limit named once, with the legs it is on (a limit on both legs was said twice, 16 Nov evening)
            legs_of = {}
            for a in added:
                legs_of.setdefault((a["source"], a["ext_id"], a["kind"]), [a["words"], []])[1].append(a["leg"])
            n = len(legs_of)
            reasons.append(f"it meets {n} road limit{'s' if n != 1 else ''} below this lorry that the route in use does "
                           f"not: " + "; ".join(w + _legs_words(ls) for w, ls in legs_of.values()))
    return reasons, added


def in_use_limits(use_legs, lorry, ctx):
    """[{"words", "legs"}]: each stored lorry limit BELOW the lorry that the line in use ITSELF meets (16 Nov evening,
    John's yes to the third draft: R027's diversion runs a 7.5 t road), by the one matching rule (route_choice._below_keys,
    so a limit limits.site_allowed allows, the site being on that road, is not listed). "legs": "loaded", "return" or
    "both". Reported only: the rule still compares every option against the line in use and its answer does not change."""
    if not ctx.lims:
        return []
    by_key = {(L.get("source"), L.get("ext_id"), L.get("kind")): L for L in ctx.lims}
    legs_of = {}
    for leg in ("loaded", "return"):
        line = use_legs.get(leg)
        if not line:
            continue
        for k in route_choice._below_keys(line, lorry, leg, ctx.lims):
            legs_of.setdefault(k, []).append(leg)
    out = []
    for k in sorted(legs_of, key=lambda x: tuple(str(v) for v in x)):
        L = by_key.get(k) or {"kind": k[2], "value": None}
        ls = legs_of[k]
        out.append({"words": _limit_words(L), "legs": "both" if len(set(ls)) > 1 else ls[0],
                    "kind": k[2], "except_for_access": bool(L.get("exceptions"))})
    return out


#: trade_short: the trade in one line naming the HEADS only (John's yes to the third draft, 16 Nov evening); the long
#: `trade` (with its counts) stays for "All figures" and the file. Each part or head: (ahead words, behind words). Three
#: levels, the first that keeps the line within SHORT_MAX words: 0 the full words; 1 shorter words, and the busy hours left
#: out where they go the same way as the round trip; 2 as 1, the people parts grouped under one "fewer" / "more", and the
#: "mixed" notes left out (they are in the long line).
SHORT_MAX = 25
_SHORT = {"collisions": ("fewer collisions", "more collisions"),
          "goods": ("fewer goods-vehicle collisions", "more goods-vehicle collisions"),
          "cycle": ("less by cycle routes", "more by cycle routes"),
          "community": ("fewer schools, hospitals and health centres passed",
                        "more schools, hospitals and health centres passed"),
          "time": ("quicker", "slower"),
          "busy": ("quicker at the busy hours", "slower at the busy hours"),
          "carbon": ("less carbon", "more carbon")}
_SHORTER = {"community": ("fewer schools and hospitals passed", "more schools and hospitals passed"),
            "busy": ("quicker at busy hours", "slower at busy hours")}
#: level 2's nouns for the people parts, after one "fewer" or "more"
_PEOPLE_NOUNS = {"collisions": "collisions", "goods": "goods-vehicle collisions", "cycle": "cycle routes met",
                 "community": "places passed"}


def _short_line(o, level):
    words = dict(_SHORT, **(_SHORTER if level else {}))
    gains, losses = [], []
    pt, hd = o["parts"], o["heads"]
    grouped = {1: [], -1: []}
    for key in ("collisions", "goods", "cycle", "community"):
        v = pt.get(key)
        if key == "goods" and v is not None and v == pt.get("collisions"):
            continue            # goods go the same way as all collisions: "fewer collisions" says it
        if v in (1, -1) and level == 2:
            grouped[v].append(_PEOPLE_NOUNS[key])
        elif v == 1:
            gains.append(words[key][0])
        elif v == -1:
            losses.append(words[key][1])
        elif v == MIXED and level < 2:
            losses.append("mixed by cycle routes")       # some cycle measures ahead, some behind
    if grouped[1]:
        gains.append("fewer " + _join(grouped[1]))
    if grouped[-1]:
        losses.append("more " + _join(grouped[-1]))
    det = o.get("detail") or {}
    gap = det.get("time_gap_min", 0)
    beyond = abs(gap) >= det.get("time_tolerance_min", 0)
    for key in ("time", "busy", "carbon"):
        v = hd.get(key)
        if key == "busy" and level and v in (1, -1) and v == hd.get("time"):
            continue            # "quicker" already says it
        if key == "time" and v in (1, -1) and not beyond:
            # the time head moved on trips a day alone (the round trip is about the same)
            (gains if v == 1 else losses).append("more trips a day" if v == 1 else "fewer trips a day")
        elif v == 1:
            gains.append(words[key][0])
        elif v == -1:
            losses.append(words[key][1])
        elif v == MIXED and key == "time":
            # quicker a round trip but a trip a day fewer, or the other way round: both sides, once each
            if gap < 0:
                gains.append("quicker")
                losses.append("fewer trips a day")
            else:
                gains.append("more trips a day")
                losses.append("slower")
        elif v == MIXED and level < 2:
            losses.append("mixed at the busy hours" if key == "busy" else "mixed on carbon")
    if o.get("n5") and hd.get("time") not in (-1, MIXED):
        losses.append(N5_WORDS)
    return f"{o['label']}: " + (_join(gains) or "nothing clearly ahead") + (", but " + _join(losses) if losses else "") + "."


def trade_short(o):
    """'Alt 2: fewer collisions and less carbon, but slower.' Heads only, no counts, one "but", at most SHORT_MAX words:
    the first of the three levels that fits (level 2 is returned whatever its length; the harness pins it under)."""
    for level in (0, 1, 2):
        line = _short_line(o, level)
        if len(line.split()) <= SHORT_MAX:
            return line
    return line


def _heads(use, opt, ctx, hist, searched_ok):
    """The parts of People and the four heads for one option against the line in use."""
    counted = hist == "current" and searched_ok
    parts = {"collisions": clearly(use["collisions"], opt["collisions"]) if counted else None,
             "goods": clearly(use["goods"], opt["goods"]) if counted else None}
    cyc = {"left_turns": step(opt["left_turns"] - use["left_turns"], LEFT_TURNS),
           "cycle_meets": (step(opt["cycle_meets"] - use["cycle_meets"], CYCLE_MEETS)
                           if opt["cycle_meets"] is not None and use["cycle_meets"] is not None else None),
           "cycle_beside_km": (step(round(opt["cycle_beside_km"] - use["cycle_beside_km"], 2), BESIDE_KM)
                               if opt["cycle_beside_km"] is not None and use["cycle_beside_km"] is not None else None)}
    cycle_part = mix(cyc.values())
    place_part = step(opt["places"] - use["places"], PLACES)
    parts["cycle"] = cycle_part if ctx.community_all else None
    parts["community"] = place_part if ctx.community_all else None
    tol = max(TIME_MIN, TIME_PCT * use["drive_min"])
    dt, dtrips = opt["cycle_min"] - use["cycle_min"], opt["trips"] - use["trips"]
    t_ahead, t_behind = (dt <= -tol or dtrips > 0), (dt >= tol or dtrips < 0)
    time = MIXED if (t_ahead and t_behind) else 1 if t_ahead else -1 if t_behind else 0
    busy_steps = {}
    for h in BUSY_HOURS:
        a, u = opt["busy_min"].get(h), use["busy_at"].get(h)
        busy_steps[h] = step(round(a - u, 1), tol) if (a is not None and u is not None) else None
    carbon = None
    if use["co2_kg"] > 0:
        c = (opt["co2_kg"] - use["co2_kg"]) / use["co2_kg"]
        carbon = 1 if c <= -CARBON_PCT else -1 if c >= CARBON_PCT else 0
    heads = {"people": mix(parts.values()), "time": time, "busy": mix(busy_steps.values()), "carbon": carbon}
    return heads, parts, {"cycle_measures": cyc, "cycle_part": cycle_part, "community_part": place_part,
                          "busy_hours": busy_steps, "time_tolerance_min": round(tol, 1), "time_gap_min": round(dt, 1)}


def _pcts(use, opt):
    return {"left_turns": pct(opt["left_turns"], use["left_turns"], PCT_BASE_MIN),
            "cycle_meets": pct(opt["cycle_meets"], use["cycle_meets"], PCT_BASE_MIN),
            "cycle_beside_km": pct(opt["cycle_beside_km"], use["cycle_beside_km"], PCT_BASE_KM),
            "places": pct(opt["places"], use["places"], PCT_BASE_MIN)}


def _pct_words(p, fewer="fewer", more="more"):
    return "" if p is None else f" ({abs(p)} % {fewer if p < 0 else more})" if p else " (the same)"


def sentences(o, use, ctx, hist):
    """The fixed sentences for one option against the line in use (Q2: the rule writes, fixed words)."""
    name, p, out = o["label"], o["pct"], []
    if hist == "current" and o["searched"]:
        for key, tail in (("collisions", ""), ("goods", " involving a goods vehicle over 3.5 t")):
            v = o["parts"].get(key)
            a, u = o["counts"][key], use[key]
            if v == 1:
                out.append(f"{name} had fewer collisions{tail} on it: {a} against {u} on the route in use, {ctx.period}.")
            elif v == -1:
                out.append(f"{name} had more collisions{tail} on it: {a} against {u} on the route in use, {ctx.period}.")
            else:
                out.append(f"{name} had {a} collision{'' if a == 1 else 's'}{tail} on it against {u} on the route in use, "
                           f"{ctx.period}.")
    elif hist == "out_of_date":
        out.append(STALE_WORDS)
    elif hist == "not_fetched":
        out.append(NO_HISTORY_WORDS)
    c = o["counts"]
    cyc = [f"makes {c['left_turns']} left turns against {use['left_turns']}{_pct_words(p['left_turns'])}"]
    if c["cycle_meets"] is not None:
        cyc.append(f"meets a cycle route {c['cycle_meets']} times against {use['cycle_meets']}"
                   f"{_pct_words(p['cycle_meets'])}")
        cyc.append(f"runs {_n(c['cycle_beside_km'], 2)} km beside one against {_n(use['cycle_beside_km'], 2)} km"
                   f"{_pct_words(p['cycle_beside_km'], 'less', 'more')}")
    out.append("A round trip " + _join(cyc) + ".")
    out.append(f"It passes {c['places']} schools, hospitals and health centres within {PLACES_M} m against "
               f"{use['places']}{_pct_words(p['places'])}.")
    if not ctx.community_all:
        out.append(NOT_FETCHED_WORDS)
    out.append(f"A round trip takes {_n(c['cycle_min'])} min against {_n(use['cycle_min'])} min, and a lorry fits "
               f"{c['trips']} trips a day against {use['trips']}.")
    busy = [f"at {h}, {_n(c['busy_min'][h])} min against {_n(use['busy_at'][h])}" for h in BUSY_HOURS
            if c["busy_min"].get(h) is not None and use["busy_at"].get(h) is not None]
    if busy:
        out.append("Setting off " + "; ".join(busy) + ".")
    out.append(f"Carbon is {_n(c['co2_kg'])} kg CO2e a trip against {_n(use['co2_kg'])} kg.")
    if o["n5"]:
        out.append(f"{name} is {N5_WORDS} ({_n(use['km'] - c['km'], 2)} km less, "
                   f"{_n(c['drive_min'] - use['drive_min'])} min more driving a round trip), so it is never suggested.")
    return out


#: N5 in words, once: never "shorter but slower" (a trade line already carries its own "but")
N5_WORDS = "a shorter road that takes longer"


def _gains_losses(o, use, with_time=True):
    """([what the option gains], [what it gives up]) in words, for the why and the trade line. with_time=False leaves the
    round-trip time out (the why says it first, so it is said once)."""
    c, gains, losses = o["counts"], [], []
    pt = o["parts"]
    for key, what in (("collisions", "collisions"), ("goods", "goods-vehicle collisions")):
        if pt.get(key) == 1:
            gains.append(f"fewer {what} on it ({c[key]} against {use[key]})")
        elif pt.get(key) == -1:
            losses.append(f"more {what} on it ({c[key]} against {use[key]})")
    for key, what in (("left_turns", "left turns"), ("cycle_meets", "cycle routes met")):
        v = o["detail"]["cycle_measures"].get(key)
        if pt.get("cycle") is None or v is None:
            continue
        d = c[key] - use[key]
        if v == 1:
            gains.append(f"{-d} fewer {what}")
        elif v == -1:
            losses.append(f"{d} more {what}")
    v = o["detail"]["cycle_measures"].get("cycle_beside_km")
    if pt.get("cycle") is not None and v in (1, -1):
        d = round(c["cycle_beside_km"] - use["cycle_beside_km"], 2)
        (gains if v == 1 else losses).append(f"{_n(abs(d), 2)} km {'less' if v == 1 else 'more'} beside a cycle route")
    if pt.get("community") in (1, -1):
        d = c["places"] - use["places"]
        (gains if d < 0 else losses).append(f"{abs(d)} {'fewer' if d < 0 else 'more'} schools, hospitals and health "
                                            f"centres passed")
    dt = round(c["cycle_min"] - use["cycle_min"])
    time_loss = with_time and o["heads"]["time"] in (-1, MIXED) and dt > 0
    if with_time and o["heads"]["time"] in (1, MIXED) and dt < 0:
        gains.append(f"{-dt} min quicker a round trip")
    if time_loss:
        losses.append(f"{dt} min more a round trip")
    if c["trips"] > use["trips"]:
        gains.append(f"{c['trips']} trips a day, not {use['trips']}")
    elif c["trips"] < use["trips"]:
        losses.append(f"a lorry fits {c['trips']} trips a day, not {use['trips']}")
    busy = {1: [], -1: []}
    for h, v in o["detail"]["busy_hours"].items():
        if v in (1, -1):
            busy[v].append((h, abs(round(c["busy_min"][h] - use["busy_at"][h]))))
    for v, hs in busy.items():
        word = "quicker" if v == 1 else "more"
        if len(hs) == 1:
            (gains if v == 1 else losses).append(f"{hs[0][1]} min {word} setting off at {hs[0][0]}")
        elif hs:
            # both busy hours in ONE phrase, so "min quicker setting off at" is not said twice
            (gains if v == 1 else losses).append(f"{word} setting off at " + _join([f"{h} ({d} min)" for h, d in hs]))
    if o["heads"]["carbon"] in (1, -1):
        d = round(c["co2_kg"] - use["co2_kg"], 1)
        (gains if d < 0 else losses).append(f"{_n(abs(d))} kg CO2e {'less' if d < 0 else 'more'} a trip")
    if o["n5"] and not time_loss:
        # said once: where the longer round trip is already a loss above, the N5 words would say it again
        losses.append(f"it is {N5_WORDS}")
    return gains, losses


def _why_suggested(o, use):
    gains, _ = _gains_losses(o, use, with_time=False)
    dt = o["counts"]["cycle_min"] - use["cycle_min"]
    if round(abs(dt)) == 0:
        first = "About the same time a round trip"
    else:
        first = ("About a minute" if round(abs(dt)) <= 1 else f"{round(abs(dt))} min") + \
                (" longer" if dt > 0 else " quicker") + " a round trip"
    return first + (", with " + _join(gains) if gains else "") + "."


def evaluate(rid, ctx):
    """The answer for one route on ctx.day (see the module's docstring). Read only; no outside call."""
    route = ctx.routes.get(rid)
    if not route:
        return None
    lines, prints, computed = ctx.route_lines(rid)
    profiles = sorted({k[0] for k in lines})
    lorry, basis = pick_lorry(rid, ctx, profiles)
    loc = lambda i: (ctx.locs.get(i) or {}).get("name") or i
    out = {"route": rid, "from": loc(route.get("origin_id")), "to": loc(route.get("dest_id")), "day": ctx.day.isoformat(),
           "lorry": lorry, "lorry_name": (conversions.vehicle_label(ctx.factors, lorry) if lorry else None),
           "lorry_basis": basis, "other_lorries": [p for p in profiles if p != lorry],
           "answer": KEEP, "option": None, "alt": None, "why": None, "trade": None, "trade_short": None,
           "held_back": None, "in_use_limits": [],
           "sentences": [], "options": [], "in_use": None, "busy_roads": [],
           "checks": {"limits_held": bool(ctx.lims), "community_all_options": ctx.community_all}}
    # finding 5: do the lorry types' lines differ on any (leg, option)? Every count here is on the chosen lorry's own
    # lines (16 Nov evening); route_compare's table still pools collisions by option number, so this says where they part
    by_lo = {}
    for (p, leg, alt), l in lines.items():
        by_lo.setdefault((leg, alt), set()).add((len(l), tuple(l[0][:2]), tuple(l[-1][:2]), tuple(l[len(l) // 2][:2])))
    out["lines_differ_by_lorry"] = any(len(v) > 1 for v in by_lo.values())
    hist = history_state(rid, prints, computed, ctx)
    out["checks"]["collision_history"] = hist
    if not lorry:
        out["why"] = "No line of this route is worked out yet."
        return out
    # the route in use on this day, per leg (4, point 4)
    in_use = {}
    for leg in ("loaded", "return"):
        ch = route_choice.choice_on(rid, lorry, leg, ctx.day, rows=ctx.choice_rows)
        alt = int(ch["alt_index"]) if ch and ch.get("status") == "in_use" else 0
        if (lorry, leg, alt) not in lines:
            alt = 0
        in_use[leg] = {"alt": alt, "label": label(alt), "why": ("diversion" if alt else "main route"),
                       "zones": [z for z in ((ch or {}).get("reason_ref") or "").split(",") if z] if ch else [],
                       "status": (ch or {}).get("status"), "until": (ch or {}).get("ends_on")}
    use_pair = (in_use["loaded"]["alt"], in_use["return"]["alt"])
    out["in_use"] = dict(in_use, pair=list(use_pair))
    busy_pair = {}
    for h in BUSY_HOURS:
        m = int(h[:2]) * 60 + int(h[3:])
        busy_pair[h] = (route_choice.busy_alt_at(rid, lorry, "loaded", ctx.busy_day, m, rows=ctx.choice_rows),
                        route_choice.busy_alt_at(rid, lorry, "return", ctx.busy_day, m, rows=ctx.choice_rows))
        if busy_pair[h] != use_pair:
            out["busy_roads"].append({"hour": h, "pair": list(busy_pair[h]), "label": label(busy_pair[h][0] or busy_pair[h][1])})
    here_alts = sorted(a for (p, leg, a) in lines if p == lorry and leg == "loaded" and a <= MAX_HERE_ALT)
    cands = [a for a in here_alts if (a, a) != use_pair]
    pairs = []
    for pr in [use_pair] + [(a, a) for a in cands] + list(busy_pair.values()):
        if pr not in pairs:
            pairs.append(pr)
    ana = network.route_analysis(rid, profiles=[lorry], pre=ctx.pre, pairs=pairs)
    try:
        import hour_times
        ana = hour_times.attach(ana)
    except Exception:
        pass
    rows = {(r["alt_index"], r.get("return_alt_index")): r for r in (ana.get("rows") or []) if r.get("profile") == lorry}
    if use_pair not in rows:
        out["why"] = "The route in use has no costed line for this lorry."
        return out
    memo = {}

    def meas(pr):
        if pr not in memo:
            memo[pr] = measures(rid, rows[pr], lines, lorry, ctx)
        return memo[pr]
    use = dict(meas(use_pair))
    use["busy_at"] = {h: (meas(busy_pair[h])["busy_min"].get(h) if busy_pair[h] in rows else None) for h in BUSY_HOURS}
    out["counts_in_use"] = {k: use[k] for k in ("km", "drive_min", "cycle_min", "trips", "co2_kg", "collisions", "goods",
                                                "left_turns", "cycle_meets", "cycle_beside_km", "places", "shown")}
    out["counts_in_use"]["busy_min"] = use["busy_at"]
    use_legs = {"loaded": lines.get((lorry, "loaded", use_pair[0])), "return": lines.get((lorry, "return", use_pair[1]))}
    out["in_use_limits"] = in_use_limits(use_legs, lorry, ctx)
    searched_lines = ctx.searched_lines(rid)

    def was_searched(m):
        # were this pair's lines searched by the last fetch? By line where it kept fingerprints, else by option number
        if searched_lines is not None:
            return set(m["prints"]) <= searched_lines
        return ctx.searched is None or set(m["keys"]) <= ctx.searched
    use_searched = was_searched(use)
    for a in cands:
        if (a, a) not in rows:
            continue
        m = meas((a, a))
        opt_legs = {"loaded": lines.get((lorry, "loaded", m["loaded_alt"]))}
        if m["return_alt"] is not None:
            opt_legs["return"] = lines.get((lorry, "return", m["return_alt"]))
        reasons, added = _ruled_out(opt_legs, use_legs, lorry, ctx)
        searched = use_searched and was_searched(m)
        out["options"].append(option_entry(a, m, use, ctx, hist, reasons, added, searched))
    _answer(out, use, ctx, hist)
    return out


def option_entry(alt, m, use, ctx, hist, reasons=(), added=(), searched=True):
    """One option against the line in use: its heads, parts, counts, percentages, N5 and fixed sentences. `m` and `use`
    are measures() dicts (use with `busy_at`); pure given those, so a set of typed figures can be run through it too."""
    heads, parts, detail = _heads(use, m, ctx, hist, searched)
    n5 = m["km"] < use["km"] and (m["drive_min"] - use["drive_min"]) > SLOWER_MIN
    o = {"alt": alt, "label": label(alt), "return_alt": m.get("return_alt"), "ruled_out": list(reasons),
         "added_limits": list(added), "searched": searched, "heads": heads, "parts": parts, "detail": detail, "n5": n5,
         "counts": {k: m.get(k) for k in ("km", "drive_min", "cycle_min", "trips", "co2_kg", "busy_min", "collisions",
                                          "goods", "left_turns", "cycle_meets", "cycle_beside_km", "places", "shown")},
         "pct": _pcts(use, m)}
    o["head_words"] = {k: (_HEAD_WORDS[k].get(v) if v is not None else "not counted") for k, v in heads.items()}
    o["part_words"] = {k: (_PART_WORDS.get(v) if v is not None else "not counted") for k, v in parts.items()}
    o["sentences"] = sentences(o, use, ctx, hist)
    return o


def _answer(out, use, ctx, hist):
    """Suggested / A trade-off / Keep the route in use, the option, the why and the trade line (Q3, N5).
      clean   ahead on at least one counted head and behind on none;
      apart   ahead (or mixed) on one head and behind (or mixed) on another: the heads pull apart.
    Suggested: the clean option (most heads ahead, then the least carbon, then the lower number) that is not shorter but
    slower (N5) and whose collisions were searched, while no check the answer needs is missing (`held`). A trade-off: an
    apart option, or a clean one N5 holds to a trade-off; the trade in one line and NO pick (Q3). Otherwise Keep, with
    held_back saying what kept a clean option from being suggested."""
    opts = out["options"]
    live = [o for o in opts if not o["ruled_out"]]
    counted = lambda o: [v for v in o["heads"].values() if v is not None]
    ahead = lambda o: sum(1 for v in counted(o) if v == 1)
    behind = lambda o: sum(1 for v in counted(o) if v in (-1, MIXED))
    clean = [o for o in live if ahead(o) and not behind(o)]
    apart = [o for o in live if any(v in (1, MIXED) for v in counted(o)) and behind(o)]
    held = None
    if SUGGEST_NEEDS_LIMITS and not ctx.lims:
        held = NO_LIMITS_WORDS
    elif SUGGEST_NEEDS_COLLISIONS and hist != "current":
        held = STALE_WORDS if hist == "out_of_date" else NO_HISTORY_WORDS
    out["held_back"] = None
    suggest = [o for o in clean if not o["n5"] and o["searched"]]
    if suggest and not held:
        o = sorted(suggest, key=lambda x: (-ahead(x), x["counts"]["co2_kg"], x["alt"]))[0]
        o["chosen"] = True
        out.update(answer=SUGGESTED, option=o["label"], alt=o["alt"], why=_why_suggested(o, use),
                   sentences=o["sentences"])
        return
    if suggest:
        # an option the rule would suggest, held back by a missing check: said before any trade-off, so the table shows
        # what the check would open
        o = sorted(suggest, key=lambda x: (-ahead(x), x["counts"]["co2_kg"], x["alt"]))[0]
        out.update(answer=KEEP, held_back=held, why=f"Not suggested yet: {held}", sentences=o["sentences"])
        return
    trade = apart + [o for o in clean if o["n5"]]
    if trade:
        o = sorted(trade, key=lambda x: (-ahead(x), behind(x), x["alt"]))[0]
        o["traded"] = True
        gains, losses = _gains_losses(o, use)
        line = f"{o['label']} has " + (_join(gains) or "nothing clearly ahead") + (", but " + _join(losses) if losses else "")
        out.update(answer=TRADE_OFF, why=line + ".", trade=line + ".", trade_short=trade_short(o),
                   sentences=o["sentences"], held_back=held)
        return
    if clean:
        o = sorted(clean, key=lambda x: (-ahead(x), x["alt"]))[0]
        why = held or (f"Collisions on {o['label']} were not searched at the last collision fetch, so it cannot be "
                       f"compared yet.")
        out.update(answer=KEEP, held_back=why, why=f"Not suggested yet: {why}", sentences=o["sentences"])
        return
    # nothing would be suggested: a missing limits check holds nothing back; a missing collision history still might
    missing = bool(live) and SUGGEST_NEEDS_COLLISIONS and hist != "current"
    out["held_back"] = (STALE_WORDS if hist == "out_of_date" else NO_HISTORY_WORDS) if missing else None
    if not opts:
        out["why"] = "No other option is stored for this lorry."
    elif not live:
        out["why"] = "Every other option is ruled out: " + "; ".join(f"{o['label']}: {o['ruled_out'][0]}" for o in opts) + "."
    else:
        out["why"] = "No other option is clearly ahead on any head."


# --------------------------------------------------------------------------- #
#  The all-routes table (the admin read)                                       #
# --------------------------------------------------------------------------- #
def table(day=None, route_ids=None):
    """The rule over every route (or those asked): {"day", "thresholds", "checks", "totals", "rows", "routes"}. One row a
    (route, option) John can set thresholds on: the route's answer, the option, each head, the counts on both sides, the
    percentages, the why, what ruled the option out. Read only; no outside call."""
    ctx = Context(day=day)
    ids = sorted(route_ids or ctx.routes)
    routes, rows = [], []
    totals = {SUGGESTED: 0, TRADE_OFF: 0, KEEP: 0, "no_alternative": 0}
    for rid in ids:
        r = evaluate(rid, ctx)
        if r is None:
            continue
        routes.append(r)
        totals[r["answer"]] += 1
        if not r["options"]:
            totals["no_alternative"] += 1
        base = {"route": rid, "from": r["from"], "to": r["to"], "lorry": r["lorry_name"] or r["lorry"],
                "in_use": ("/".join(sorted({r["in_use"]["loaded"]["label"], r["in_use"]["return"]["label"]}))
                           if r.get("in_use") else None),
                "answer": r["answer"], "why": r["why"], "held_back": r["held_back"],
                "collision_history": r["checks"]["collision_history"], "trade_short": r.get("trade_short"),
                "in_use_limits": r.get("in_use_limits") or []}
        if not r["options"]:
            rows.append(dict(base, option=None, chosen=False))
        for o in r["options"]:
            rows.append(dict(base, option=o["label"], chosen=bool(o.get("chosen")), traded=bool(o.get("traded")),
                             ruled_out="; ".join(o["ruled_out"]) or None, heads=o["head_words"], parts=o["part_words"],
                             counts=o["counts"], counts_in_use=r.get("counts_in_use"), pct=o["pct"],
                             shorter_but_slower=o["n5"], collisions_searched=o["searched"]))
    return {"day": ctx.day.isoformat(), "thresholds": thresholds(),
            "checks": {"limits_held": bool(ctx.lims), "community_all_options": ctx.community_all,
                       "collisions_fetched_at": ctx.col_status.get("fetched_at"), "collisions_period": ctx.period,
                       "collision_fingerprints_kept": ctx.searched_prints is not None,
                       "community_fetched_at": (community.status() or {}).get("fetched_at")},
            "totals": totals, "rows": rows, "routes": routes}
