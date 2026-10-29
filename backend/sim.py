"""
sim.py — the haulage simulation: an average working day of one month, lorry by lorry, at every gate.
Wayscope, 16 Oct 2026 (S3 = v2 V4a / B3; the engine the Dashboard's Simulation panel, S7, only draws).

THE SPEC is the example the user approved on 16 Oct (notes/sim-example-1016/, not in git): its `simulate()` is one pure
function, and this module is that function in Python, with the review's fixes and the decisions D81–D94 as taken.
A browser that draws this reply cannot disagree with the table, because both read the same arrivals.

WHAT A DAY IS (each step is one function below)
-----------------------------------------------
1. WHOLE LOADS (D88). Each approved line of the month carries trips ÷ working days loads a day (the trips rule is
   gate_arrivals.trips_for, the Dashboard's). A day has whole loads, so each line's average day is rounded DOWN or UP;
   the day's total is the month's average day rounded. Of all such choices the day keeps: the smallest worst gate
   difference from the Dashboard's Gate arrivals figure, then the smallest sum of squares of those differences, then
   the smallest sum of squares of each line's own change, then the choice that rounds up the lowest route numbers.
   A whole-number line is never rounded up. whole_loads() searches every choice in that order (depth first, pruned
   on the worst gate difference); on a very large month it stops after NODE_BUDGET steps and says so (`exact`).
2. ARRIVALS. A laden lorry arrives at the destination's entry gate, an empty one (coming to load) at the origin's:
   gate_arrivals.entry_gate, the Dashboard's ends.
3. RELEASE (D59). Each gate's arrivals are spread evenly over its open minutes, the peak bands and the gate's own
   shut windows taken off (17 Oct 2026), all teams' lines interleaved: arrival i of n at (i + ½) / n of the open
   minutes. A boundary minute belongs to the NEXT interval (a band 07:00–10:00 on 05:00–17:00: open minute 120 is
   10:00, never 07:00). So no lorry is placed before its gate opens: it sets off its drive time earlier (step 7) —
   before 08:00 for a gate opening at 08:00 — and arrives from the opening (the user, 17 Oct 2026).
   29 Oct 2026 (the user: a scenario where lorries bottleneck AT THE GATE): the scenario's ARRIVAL PATTERN — `even`
   (the above, the default) or a MORNING RUSH: the first round(share × n) of the gate's arrivals, in the same order
   (so every line's first trips come first, interleaved), evenly over the first `minutes` OPEN minutes (bands and shut
   times skipped as above), the rest evenly over the remaining open minutes. A window at or past the gate's open
   minutes, or a share of nothing, is the even spread. On screen only (D86); every gate; every scale. The Dashboard's
   capacity words, the Look-ahead's gate flags and the public map keep the even spread.
4. THE POUR (a typed what-if until V5 holds pours): ceil(m³ ÷ m³ a load) mixers, one every (m³ a load ÷ pour rate)
   hours from the start, on top of the gate's day. The default mixer is the app's "Truck mixer 8 m³ (32t)"
   (payload_m3 7.5 in factors.json). A pour whose last mixer would come after 23:59 is refused.
5. THE QUEUE. One lane at each gate, first come first served, each lorry taking the gate's check-in minutes
   (`safety_minutes`). A lorry that comes while the gate is shut (before it opens, in a no-delivery band or in one of
   the gate's shut windows) waits for it to open. One still waiting after the last open minute is checked in late and COUNTED (D89), queue or not.
   A gate with no check-in typed never queues.
6. FIGURES. Per gate: the busiest clock hour, when the first lorry waits (`queue_start`), the BOTTLENECK — the first
   wait LONGER than the gate's check-in (D85; the example marked any wait) —, the most waiting at once, the minutes
   lost, the longest wait, the late check-ins, capacity and the Dashboard's words: gate_arrivals.judge, red "Over
   gate capacity" when the DISPLAYED one-decimal gap is shorter than the check-in, amber "Queue likely" at 85 %.
7. JOURNEYS (drawing only). Each arrival is a lorry that set off its route's drive time earlier. The line's OWN
   vehicle's route (route_geometry, the Look-ahead's rule: that vehicle where it was worked out, else the first that
   was, said). Haul stretches — where the route runs within HAUL_NEAR_M of a haul road it was routed along — run at
   the road's assigned speed, the rest at whatever speed makes up the route's stored time (haul.py's rule).

OPEN HOURS. A gate's typed `open_from`–`open_to`; a gate with none typed takes the DEFAULT GATE HOURS (17 Oct 2026, the
user: 08:00–17:00, or the scheme's own on Config — gate_hours.default_hours; until then the lorry shift placed at 07:00
stood in), and the reply says so. A window that ends at or before it starts — past midnight — is refused (D93): typed on
a gate, that gate is left out and named; asked for in a scenario, the request is refused in words.
SHUT WINDOWS (17 Oct 2026): each gate's own, as typed on it (gate_hours.shut_windows), always on — under a scenario's
hours too, and the bands switch does not touch them (they are the gate's agreements, not a what-if). Taken off like a
band; an overlap with a band counts once.
PEAK BANDS: `planning.peak_bands` as typed, on by default when typed; switched on with none typed, Config's example
bands (gate_hours.PEAK_PLACEHOLDER) stand in and the reply says so.

8. ON SITE (28 Oct 2026, v2; sim_site.py). At a site with areas or internal roads a checked-in lorry drives the drawn
   roads at the site speed to the area that takes its material (bays, service minutes), then the wheel wash, then
   out by the site's exit gate — a gate closed for a period hands both directions to the other gate. Every station
   queues first come first served and is counted like the gate. SCALES: the month's average working day (as
   above), the Look-ahead week's average weekday, or one planned day (lookahead_lines).

D84: an origin's gate (a quarry, the railhead) serves other customers too — only this scheme's lorries are counted.
D86: nothing is saved; a scenario exists only in the request that asks for it. D92: one drive time a route, all day.

Pure functions down to `day()`, which reads (never writes): the month's forecasts, routes, locations, gates, the
routes' stored times and, for the drawing, their lines and the haul roads. Every SQL literal carries the tenant.
Never spells a team slot id (test_modus scans shipped .py); teams reach the reply as the tenant's names.
"""
import functools
import json
import math

import datetime

import access
import conversions
import days
import db
import derived
import gate_arrivals
import gate_hours
import gates
import site_areas
import sim_site
import taxonomy
import zones

#: 17 Oct 2026: the playback window when a day has no lorry at all and no scheme default is passed in (inp's
#: "empty_window", the scheme's default gate hours, wins) — the shipped default gate hours (was the 07:00 stand-in)
EMPTY_DAY_WINDOW = (gate_hours.minutes_of(gate_hours.DEFAULT_GATE_HOURS["from"]),
                    gate_hours.minutes_of(gate_hours.DEFAULT_GATE_HOURS["to"]))
#: the app's own mixer: its legal fill is the pour's default m³ a load (factors.json, itself a stated assumption)
MIXER_NAME = "Truck mixer 8 m³ (32t)"
MIXER_M3_FALLBACK = 7.5
MAX_POUR_MIXERS = 400
MAX_CHECK_IN = 240.0
#: 29 Oct 2026: the morning rush's defaults (the plan's own first trips at the demo's busiest gate: 30 % in 30 min)
RUSH_DEFAULT_SHARE = 30.0
RUSH_DEFAULT_MINUTES = 30.0
RUSH_MIN_MINUTES, RUSH_MAX_MINUTES = 5.0, 240.0
#: a lorry waiting less than this has not waited (float dust between equal minutes)
WAIT_EPS = 0.01
#: drawing: the pour's mixers appear this far out on the shortest road into the gate (2.5 miles)
MIXER_APPROACH_M = 4000.0
#: a route runs ON a haul road where its points lie within this of the drawn road
HAUL_NEAR_M = 4.0
#: the drawing's line is simplified to this (the example's 15 m); stretch ends are always kept
SIMPLIFY_M = 15.0
#: whole_loads() stops searching after this many steps and keeps the best day found (`exact` False)
NODE_BUDGET = 300_000
#: 17 Oct 2026: a concrete pour goes to a WORKING site — the location types the app treats as one (network._role_for's
#: compound and site; the Locations form offers Quarry, Port, Compound, Site, Railhead, Stockpile, Other). Never a quarry,
#: a railhead, a stockpile, a landfill, a soil recycling hub or a batching plant. Matched without regard to case.
POUR_SITE_TYPES = ("compound", "site")

NOTE_ORIGIN = "Serves other customers too: only this scheme's lorries are counted, so a queue here is the least it could be."
LIMITS = ("Planning view, not a record of what happened.",
          "Congestion on the public road is not modelled: each route has one drive time all day, so the only "
          "bottlenecks shown are at the gates and on site.",
          "A lorry held up at a gate is not late for anything afterwards: each arrival is placed by its gate's open "
          "hours, not by the lorry's last trip.")


# --------------------------------------------------------------------------------------------------- small helpers
def js_round(x):
    """Math.round: halves go up (Python's round() goes to even)."""
    return math.floor(x + 0.5)


def hhmm(m):
    """540 -> '09:00'; the example's hhmm (minutes rounded first, halves up)."""
    if m is None:
        return None
    m = js_round(m)
    return f"{m // 60:02d}:{m % 60:02d}"


def _r2(x):
    return None if x is None else round(float(x), 2)


def _num(v, what):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number")
    if not math.isfinite(f):
        raise ValueError(f"{what} must be a number")
    return f


# --------------------------------------------------------------------------------------------------- 1. whole loads
def whole_loads(shares, touch, avg, node_budget=NODE_BUDGET):
    """
    D88. `shares`: each line's loads a day (trips ÷ working days), in route order. `touch`: for each line the gate
    keys its loads arrive at (destination's, origin's; a missing end left out). `avg`: {gate key: the Dashboard's
    arrivals a day}. Returns {per_line, worst, exact}. Memoised: the same month gives the same day for free.
    """
    key = (tuple(float(s) for s in shares), tuple(tuple(t) for t in touch),
           tuple((k, float(v)) for k, v in avg.items()))
    return dict(_whole_loads(key, int(node_budget)))


@functools.lru_cache(maxsize=64)
def _whole_loads(key, node_budget):
    shares, touch, avg_items = key
    n = len(shares)
    gid = [k for k, _ in avg_items]
    gpos = {g: j for j, g in enumerate(gid)}
    av = [v for _, v in avg_items]
    G = len(gid)
    floor = [math.floor(s) for s in shares]
    k = js_round(sum(shares)) - sum(floor)
    tch = [[gpos[g] for g in t if g in gpos] for t in touch]
    base = [0] * G
    for i in range(n):
        for j in tch[i]:
            base[j] += floor[i]
    cand = [i for i in range(n) if shares[i] - floor[i] >= 1e-9]          # a whole-number line is never rounded up
    k = max(0, min(k, len(cand)))
    frac = [shares[i] - floor[i] for i in range(n)]
    lsq0 = sum(f * f for f in frac)                                         # every line down

    def score(ups):
        s = base[:]
        lsq = lsq0
        for i in ups:
            for j in tch[i]:
                s[j] += 1
            lsq += (1 - frac[i]) ** 2 - frac[i] ** 2
        worst, sq = 0.0, 0.0
        for j in range(G):
            d = abs(s[j] - av[j])
            worst = max(worst, d)
            sq += d * d
        return worst, sq, lsq

    def better(a, b):
        """a beats b: (worst, sq, lsq) each within 1e-9, then the lower route numbers (the example's before())."""
        for x, y in zip(a[0], b[0]):
            if x < y - 1e-9:
                return True
            if x > y + 1e-9:
                return False
        return a[1] < b[1]

    # a good first answer, so the search below cuts early: the k largest remainders, then single swaps while they help
    order = sorted(cand, key=lambda i: (-frac[i], i))
    ups = sorted(order[:k])
    best = (score(ups), tuple(ups))
    improved = True
    while improved:
        improved = False
        for a in list(best[1]):
            for b in cand:
                if b in best[1]:
                    continue
                trial = tuple(sorted([x for x in best[1] if x != a] + [b]))
                c = (score(trial), trial)
                if better(c, best):
                    best, improved = c, True
                    break
            if improved:
                break

    # every choice in the order of route numbers (so the first of two equal days is the lower route numbers), cut
    # where no completion can get the worst gate difference down to the best one's
    nc = len(cand)
    suffix = [[0] * G for _ in range(nc + 1)]                               # gate touches still available from c on
    for c in range(nc - 1, -1, -1):
        suffix[c] = suffix[c + 1][:]
        for j in tch[cand[c]]:
            suffix[c][j] += 1
    s = base[:]
    picked = []
    steps = [0]
    exact = [True]

    def bound(c, left):
        lb = 0.0
        for j in range(G):
            over = s[j] - av[j]
            short = av[j] - (s[j] + min(left * 2, suffix[c][j]))
            lb = max(lb, over, short)
        return lb

    def dfs(c):
        nonlocal best
        if not exact[0]:
            return
        steps[0] += 1
        if steps[0] > node_budget:
            exact[0] = False
            return
        left = k - len(picked)
        if left == 0:
            ups_t = tuple(picked)
            cand_s = (score(ups_t), ups_t)
            if better(cand_s, best):
                best = cand_s
            return
        if bound(c, left) > best[0][0] + 1e-9:
            return
        for x in range(c, nc - left + 1):
            i = cand[x]
            picked.append(i)
            for j in tch[i]:
                s[j] += 1
            dfs(x + 1)
            for j in tch[i]:
                s[j] -= 1
            picked.pop()
            if not exact[0]:
                return

    dfs(0)
    up = set(best[1])
    per_line = [floor[i] + (1 if i in up else 0) for i in range(n)]
    return (("per_line", tuple(per_line)), ("worst", best[0][0]), ("exact", exact[0]))


# --------------------------------------------------------------------------------------------------- 3. open time
def band_intervals(bands):
    """[{from, to}] -> [(a, b)] in minutes of the day; a band past midnight splits at midnight (gate_hours' rule)."""
    out = []
    for b in bands or []:
        a, z = gate_hours.minutes_of(b.get("from")), gate_hours.minutes_of(b.get("to"))
        if a is None or z is None or a == z:
            continue
        out.extend(gate_hours._intervals(a, z))
    return out


def open_intervals(window, bands):
    """The gate's window [a, b) with each band taken off, in order (the example's openIntervals)."""
    if window is None:
        return []
    iv = [(window[0], window[1])]
    for p, q in bands or []:
        nx = []
        for x, y in iv:
            if q <= x or p >= y:
                nx.append((x, y))
                continue
            if p > x:
                nx.append((x, p))
            if q < y:
                nx.append((q, y))
        iv = nx
    return iv


def clock_at_open(iv, u):
    """The clock time `u` open minutes into the gate's day. A boundary minute belongs to the NEXT interval."""
    for a, b in iv:
        if u < b - a:
            return a + u
        u -= (b - a)
    return iv[-1][1] if iv else None


def next_service(iv, s):
    """The first minute at or after `s` the gate is open; after its last open minute, `s` itself (checked in late)."""
    for a, b in iv:
        if s < a:
            return a
        if s < b:
            return s
    return s


def place(arrivals, iv, pattern=None):
    """
    D59: the gate's arrivals evenly over its open minutes, the lines interleaved — sorted by each lorry's place in its
    own line's day (phase), then line, then kind; arrival i of n at (i + ½) / n of the open minutes. Sets `t`.
    29 Oct 2026: `pattern` {"kind": "rush", "share": 0–1, "minutes": W} puts the first k = round(share × n) arrivals
    (the same order: every line's first trips first) evenly over the first W open minutes and the rest evenly over
    the remaining O − W; W is capped at O, and W ≥ O or k = 0 is the even spread. Marks the rush's lorries `rush`.
    """
    O = sum(b - a for a, b in iv)
    arrivals.sort(key=lambda a: (a["phase"], a["line"], a["kind"]))
    n = len(arrivals)
    for a in arrivals:
        a["rush"] = False
    rush = pattern if (pattern and pattern.get("kind") == "rush") else None
    W = min(float(rush["minutes"]), O) if rush else 0.0
    k = int(round(float(rush["share"]) * n)) if rush else 0
    if not rush or O <= 0 or n == 0 or W >= O or k <= 0:
        for i, a in enumerate(arrivals):
            a["t"] = clock_at_open(iv, (i + 0.5) / n * O) if O > 0 else None
        return arrivals
    k = min(n, k)
    for i, a in enumerate(arrivals):
        if i < k:
            u = (i + 0.5) / k * W
            a["rush"] = True
        else:
            u = W + (i - k + 0.5) / (n - k) * (O - W)
        a["t"] = clock_at_open(iv, u)
    return arrivals


# --------------------------------------------------------------------------------------------------- 4. the pour
def pour_burst(start, m3, m3_per_load, rate):
    """{loads, gap, end, times}: ceil(m³ ÷ m³ a load) mixers, one every (m³ a load ÷ rate) hours from `start`."""
    loads = math.ceil(m3 / m3_per_load - 1e-9)
    gap = m3_per_load / rate * 60.0
    return {"loads": loads, "gap": gap, "end": start + (loads - 1) * gap,
            "times": [start + j * gap for j in range(loads)]}


def pour_problem(start, m3, m3_per_load, rate):
    """None when the pour can be simulated, else what is wrong, in words."""
    if start is None:
        return "The pour needs a start time such as 10:00."
    if not (m3 > 0 and m3_per_load > 0 and rate > 0):
        return "The pour needs a volume, a mixer load and a pour rate above nothing."
    loads = math.ceil(m3 / m3_per_load - 1e-9)
    if loads > MAX_POUR_MIXERS:
        return f"That pour needs {loads} mixers; the simulation takes at most {MAX_POUR_MIXERS}."
    end = start + (loads - 1) * m3_per_load / rate * 60.0
    if end > 23 * 60 + 59:
        return f"That pour would run past midnight (last mixer at {hhmm(end)}); the simulation shows one day."
    return None


# --------------------------------------------------------------------------------------------------- 5–6. the queue
def queue(arrivals, iv, check_in):
    """One lane, first come first served (see the module docstring). Sets start, wait, done; returns them by `t`."""
    A = sorted((a for a in arrivals if a.get("t") is not None), key=lambda a: a["t"])
    c = check_in
    free = -1e9
    for a in A:
        if c is None or not c > 0:
            a["start"], a["wait"], a["done"] = a["t"], 0.0, a["t"]
            continue
        s = next_service(iv, max(a["t"], free))
        a["start"], a["wait"], a["done"] = s, s - a["t"], s + c
        free = a["done"]
    return A


def waiting_at(A, t):
    """The lorries waiting at minute `t`, in the order they will be checked in (the gate's one lane)."""
    return [a for a in A if a["t"] <= t < a["start"]]


def gate_figures(A, iv, check_in):
    """Step 6 for one gate, from its queued arrivals `A` (sorted by arrival)."""
    c = check_in
    O = sum(b - a for a, b in iv)
    last_open = iv[-1][1] if iv else None
    hours = [0] * 24
    for a in A:
        hours[min(23, max(0, math.floor(a["t"] / 60)))] += 1
    busiest = max([0] + hours)
    busiest_hours = [h for h, n in enumerate(hours) if n == busiest and n > 0]
    first = next((a for a in A if a["wait"] > WAIT_EPS), None)
    bottleneck = (next((a for a in A if a["wait"] > c + WAIT_EPS), None) if (c and c > 0) else None)
    ev = []
    for a in A:
        if a["wait"] > WAIT_EPS:
            ev.append((a["t"], 1))
            ev.append((a["start"], -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = most = 0
    most_at = None
    for t, d in ev:
        cur += d
        if cur > most:
            most, most_at = cur, t
    n = len(A)
    jd = gate_arrivals.judge(float(n) if n else None, O, c if (c and c > 0) else None)
    cap = jd["cap_raw"]
    pct = (n * 100.0 / cap) if cap else None
    late = [a for a in A if c and c > 0 and (last_open is None or a["start"] >= last_open - 1e-9)]
    regular = [a for a in A if a["kind"] != "pour"]
    return {
        "arrivals": n,
        "laden": sum(1 for a in A if a["kind"] == "laden"),
        "empty": sum(1 for a in A if a["kind"] == "empty"),
        "pour": sum(1 for a in A if a["kind"] == "pour"),
        "open_minutes": O, "intervals": [[a, b] for a, b in iv], "last_open": last_open,
        "check_in": c,
        "capacity": (gate_arrivals.r1(cap) if cap else None), "capacity_raw": cap,
        "pct": (js_round(pct) if pct is not None else None), "pct_raw": pct,
        "gap": jd["gap"] if n else None,
        "flag": jd["flag"], "status_word": gate_hours.STATUS_WORDS.get(jd["flag"]),
        "hours": hours, "busiest": busiest, "busiest_hours": busiest_hours,
        "busiest_hour": (f"{busiest_hours[0]:02d}:00" if busiest_hours else None),
        "per_hour": (60.0 / c if (c and c > 0) else None),
        "even_rate": (len(regular) / O * 60.0 if O > 0 else None),
        "queue_start": (first["t"] if first else None),
        "bottleneck_at": (bottleneck["t"] if bottleneck else None),
        "most_waiting": most, "most_at": most_at,
        "minutes_lost": sum(a["wait"] for a in A),
        "longest_wait": max([0.0] + [a["wait"] for a in A]),
        "late": len(late),
        "last_done": (max(a["done"] for a in A) if A else None),
        # 29 Oct 2026: how many of the gate's lorries the morning rush placed in its first minutes (0 under the even spread)
        "rush_n": sum(1 for a in A if a.get("rush")),
    }


# --------------------------------------------------------------------------------------------------- 7. the drawing
def metres(a, b):
    """The example's flat-earth distance between two [lon, lat] points (good to a few cm at a scheme's scale)."""
    la = (a[1] + b[1]) / 2 * math.pi / 180
    R = 6371008.8
    return math.hypot((b[0] - a[0]) * math.pi / 180 * R * math.cos(la), (b[1] - a[1]) * math.pi / 180 * R)


def _xy(p, lat0):
    R = 6371008.8
    return (p[0] * math.pi / 180 * R * math.cos(lat0), p[1] * math.pi / 180 * R)


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def haul_stretches(coords, roads, near=HAUL_NEAR_M):
    """
    [(zone id, i0, i1)]: the runs of the route's points lying within `near` metres of a haul road it was routed
    along (`roads` = {zone id: [[lon, lat], ...]}). A single point touching a road (a crossing) is not a stretch.
    """
    if not coords or not roads:
        return []
    lat0 = coords[0][1] * math.pi / 180
    P = [_xy(c, lat0) for c in coords]
    out = []
    for zid, line in roads.items():
        if not line or len(line) < 2:
            continue
        Z = [_xy(c, lat0) for c in line]
        xs, ys = [z[0] for z in Z], [z[1] for z in Z]
        x0, x1, y0, y1 = min(xs) - near, max(xs) + near, min(ys) - near, max(ys) + near
        on = []
        for p in P:
            if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
                on.append(False)
                continue
            on.append(min(_seg_dist(p, Z[k], Z[k + 1]) for k in range(len(Z) - 1)) <= near)
        i = 0
        while i < len(on):
            if on[i]:
                j = i
                while j + 1 < len(on) and on[j + 1]:
                    j += 1
                if j > i:
                    out.append((zid, i, j))
                i = j + 1
            else:
                i += 1
    out.sort(key=lambda s: s[1])
    return out


def simplify(coords, tol=SIMPLIFY_M, keep=()):
    """Douglas–Peucker to `tol` metres, the points in `keep` (and both ends) always kept. Returns the kept indices."""
    n = len(coords)
    if n <= 2:
        return list(range(n))
    lat0 = coords[0][1] * math.pi / 180
    P = [_xy(c, lat0) for c in coords]
    must = sorted({0, n - 1} | {k for k in keep if 0 <= k < n})
    kept = set(must)
    for a, b in zip(must, must[1:]):
        stack = [(a, b)]
        while stack:
            i, j = stack.pop()
            if j - i < 2:
                continue
            far, at = -1.0, None
            for k in range(i + 1, j):
                d = _seg_dist(P[k], P[i], P[j])
                if d > far:
                    far, at = d, k
            if far > tol:
                kept.add(at)
                stack.append((i, at))
                stack.append((at, j))
    return sorted(kept)


def leg_plan(length, minutes, stretches, speed_kph):
    """
    The example's legPlan: the haul stretches at their assigned speed (metres a minute), the rest at the speed that
    makes up the route's stored time. `stretches` = [(zone, a_m, b_m)]. Returns {parts: [{a, b, mpm, zone, t0, t1}],
    minutes}.
    """
    parts = []
    hs = [(z, a, b) for z, a, b in stretches if speed_kph.get(z)]
    haul_min = sum((b - a) / 1000.0 / speed_kph[z] * 60.0 for z, a, b in hs)
    haul_len = sum(b - a for z, a, b in hs)
    pub_min = max(1.0, minutes - haul_min)
    pub_len = length - haul_len
    pos = 0.0
    for z, a, b in sorted(hs, key=lambda h: h[1]):
        if a > pos:
            parts.append({"a": pos, "b": a, "mpm": pub_len / pub_min, "zone": None})
        parts.append({"a": a, "b": b, "mpm": speed_kph[z] * 1000.0 / 60.0, "zone": z})
        pos = b
    if pos < length:
        parts.append({"a": pos, "b": length, "mpm": pub_len / pub_min, "zone": None})
    t = 0.0
    for p in parts:
        p["t0"] = t
        t += (p["b"] - p["a"]) / p["mpm"] if p["mpm"] > 0 else 0.0
        p["t1"] = t
    return {"parts": parts, "minutes": t}


def time_at_dist(plan, d):
    for p in plan["parts"]:
        if d <= p["b"]:
            return p["t0"] + max(0.0, d - p["a"]) / p["mpm"]
    return plan["minutes"]


def build_leg(coords, minutes, roads, speed_kph):
    """
    One leg ready to draw: the line simplified (stretch ends kept), its cumulative metres, the haul stretches and the
    plan. `roads`: the haul roads this leg was routed along. None when there is no line.
    """
    if not coords or len(coords) < 2:
        return None
    st = haul_stretches(coords, roads)
    idx = simplify(coords, keep=[i for _, a, b in st for i in (a, b)])
    pos = {i: k for k, i in enumerate(idx)}
    pts = [[round(coords[i][0], 6), round(coords[i][1], 6)] for i in idx]
    cum = [0.0]
    for k in range(1, len(pts)):
        cum.append(cum[-1] + metres(pts[k - 1], pts[k]))
    length = cum[-1]
    stretches = [(z, cum[pos[a]], cum[pos[b]]) for z, a, b in st]
    plan = leg_plan(length, minutes, stretches, speed_kph)
    return {"coords": pts, "cum": cum, "len_m": length, "minutes": minutes, "stretches": stretches, "plan": plan}


def reversed_leg(leg, speed_kph):
    """A leg driven the other way (a line whose return was never worked out: the loaded line reversed)."""
    if not leg:
        return None
    L = leg["len_m"]
    pts = list(reversed(leg["coords"]))
    cum = [L - c for c in reversed(leg["cum"])]
    stretches = [(z, L - b, L - a) for z, a, b in leg["stretches"]]
    return {"coords": pts, "cum": cum, "len_m": L, "minutes": leg["minutes"], "stretches": stretches,
            "plan": leg_plan(L, leg["minutes"], stretches, speed_kph)}


# --------------------------------------------------------------------------------------------------- the whole day
def simulate(inp, scen):
    """
    THE ENGINE, pure: `inp` = what day() read (lines, gates, Dashboard averages, legs), `scen` = the scenario (hours,
    check-in, bands, pour), both plain data. Returns the day: per line, per gate, every arrival, the pour, the haul
    roads and the window the clock plays. See the module docstring for each step.
    """
    lines, G = inp["lines"], inp["gates"]
    if inp.get("fixed") is not None:          # 28 Oct 2026 (v2): the day scale — each line's trips are whole already
        rnd = {"per_line": [int(x) for x in inp["fixed"]], "exact": True, "worst": 0.0}
    else:
        rnd = whole_loads([l["share"] for l in lines], [l["touch"] for l in lines], inp["panel"])
    per_line = list(rnd["per_line"])
    bands = band_intervals(scen.get("bands") or [])

    # 2–3. every arrival at every gate, then D59 at each gate
    by_gate = {g: [] for g in G}
    for li, l in enumerate(lines):
        n = per_line[li]
        for k in range(n):
            ph = (k + 0.5) / n
            if l.get("laden_gate") in by_gate:
                by_gate[l["laden_gate"]].append({"gate": l["laden_gate"], "kind": "laden", "line": li,
                                                 "route": l["route_id"], "phase": ph, "leg": l.get("laden_leg")})
            if l.get("empty_gate") in by_gate:
                by_gate[l["empty_gate"]].append({"gate": l["empty_gate"], "kind": "empty", "line": li,
                                                 "route": l["route_id"], "phase": ph, "leg": l.get("empty_leg")})
    ivs = {}
    for g, A in by_gate.items():
        # 17 Oct 2026: the gate's own shut windows come off with the bands (open_intervals: an overlap counts once)
        ivs[g] = open_intervals(G[g]["window"], bands + list(G[g].get("shut") or [])) if G[g]["window"] is not None else []
        place(A, ivs[g], scen.get("arrivals"))

    # 4. the pour, a burst on top
    pour = None
    p = scen.get("pour")
    if p and p.get("gate") in by_gate:
        b = pour_burst(p["start"], p["m3"], p["m3_per_load"], p["rate"])
        into = [inp["legs"][l["laden_leg"]] for l in lines
                if l.get("laden_gate") == p["gate"] and l.get("laden_leg") in inp["legs"] and inp["legs"][l["laden_leg"]]]
        into_keys = [l["laden_leg"] for l in lines
                     if l.get("laden_gate") == p["gate"] and l.get("laden_leg") in inp["legs"] and inp["legs"][l["laden_leg"]]]
        approach = None
        if into:
            order = sorted(range(len(into)), key=lambda i: into[i]["len_m"])
            approach = into_keys[order[0]]
        # 17 Oct 2026 (review; the user: a lorry "should [not] arrive before 0800"): a pour is typed, so its mixers can
        # come while the gate is shut — before it opens, in a band or a shut time. They wait (step 5); the reply says how many.
        shut_n = sum(1 for t in b["times"] if not any(a <= t < z for a, z in ivs[p["gate"]]))
        pour = {"gate": p["gate"], "start": p["start"], "m3": p["m3"], "m3_per_load": p["m3_per_load"],
                "rate": p["rate"], "loads": b["loads"], "gap": b["gap"], "end": b["end"], "approach_leg": approach,
                "while_shut": shut_n}
        for t in b["times"]:
            by_gate[p["gate"]].append({"gate": p["gate"], "kind": "pour", "line": None, "route": None, "phase": None,
                                       "leg": approach, "t": t})

    # 5–6. the queue and each gate's figures
    out_g = {}
    for g, A in by_gate.items():
        Q = queue(A, ivs[g], G[g]["check_in"])
        f = gate_figures(Q, ivs[g], G[g]["check_in"])
        f["queued"] = Q
        f["unplaced"] = sum(1 for a in A if a.get("t") is None)
        out_g[g] = f

    # 8. on site (28 Oct 2026, v2): each site's chain of stations for the lorries checked in at its gates
    sites_out, departures = {}, {}
    gate_loc = inp.get("gate_loc") or {}
    for lid, site in (inp.get("sites") or {}).items():
        lor = [a for g, f in out_g.items() if gate_loc.get(g) == lid for a in f["queued"]]
        sites_out[lid] = sim_site.run_site(site, lor, lines, inp.get("factors"))
        for a in lor:
            if a.get("chain"):
                og = a["chain"][-1].split(":", 1)[1]
                departures[og] = departures.get(og, 0) + 1

    # 7. journeys: each arrival set off its route's drive time earlier; the pour's mixers only for their last stretch
    legs = inp["legs"]
    journeys = []
    for g, f in out_g.items():
        for a in f["queued"]:
            leg = legs.get(a.get("leg")) if a.get("leg") else None
            a["from_m"], a["t_from"] = 0.0, 0.0
            if leg:
                if a["kind"] == "pour":
                    a["from_m"] = max(0.0, leg["len_m"] - MIXER_APPROACH_M)
                    a["t_from"] = time_at_dist(leg["plan"], a["from_m"])
                    a["depart"] = a["t"] - (leg["plan"]["minutes"] - a["t_from"])
                else:
                    a["depart"] = a["t"] - leg["plan"]["minutes"]
            else:
                mins = inp["leg_minutes"].get(a.get("leg")) if a.get("leg") else None
                a["depart"] = (a["t"] - mins) if (mins and a["kind"] != "pour") else None
            journeys.append((a, leg))

    # haul roads: lorries onto each one, both ways, by the hour they reach it (mixers too, where their stretch crosses)
    haul = {z: {"n": 0, "hours": [0] * 24, "routes": set()} for z in inp.get("haul_roads", {})}
    for a, leg in journeys:
        if not leg:
            continue
        for part in leg["plan"]["parts"]:
            z = part["zone"]
            if not z or part["b"] <= a["from_m"] or z not in haul:
                continue
            t = a["depart"] + (max(part["t0"], a["t_from"]) - a["t_from"])
            haul[z]["n"] += 1
            haul[z]["hours"][min(23, max(0, math.floor(t / 60)))] += 1
            if a.get("route"):
                haul[z]["routes"].add(a["route"])

    # the day the clock plays: the first lorry setting off to the last check-in done, in whole half hours
    deps = [a["depart"] for a, _ in journeys if a.get("depart") is not None]
    deps += [a["t"] for a, _ in journeys if a.get("depart") is None]       # no line to drive: the clock starts at its arrival
    dones = [f["last_done"] for f in out_g.values() if f["arrivals"]]
    dones += [a["out_at"] for f in out_g.values() for a in f["queued"] if a.get("out_at") is not None]
    if deps and dones:
        win = (max(0, math.floor((min(deps) - 10) / 30) * 30), min(24 * 60, math.ceil((max(dones) + 10) / 30) * 30))
    else:
        win = tuple(inp.get("empty_window") or EMPTY_DAY_WINDOW)
    return {"per_line": per_line, "rounding_exact": rnd["exact"], "rounding_worst": rnd["worst"],
            "gates": out_g, "pour": pour, "haul": haul, "window": win, "total": sum(per_line),
            "sites": sites_out, "departures": departures}


# --------------------------------------------------------------------------------------------------- the scenario
def _hours_pair(v, who):
    """'06:00-18:00' -> (360, 1080); refuses a window that ends at or before it starts (D93)."""
    s = str(v or "").replace("–", "-").strip()
    if "-" not in s:
        raise ValueError(f"{who}: open hours must be two times such as 07:00-17:00")
    a_s, b_s = [x.strip() for x in s.split("-", 1)]
    a, b = gate_hours.minutes_of(a_s), gate_hours.minutes_of(b_s)
    if a is None or b is None:
        raise ValueError(f"{who}: open hours must be 24-hour times such as 07:00-17:00")
    if b <= a:
        raise ValueError(f"{who}: the gate must close after it opens; a window past midnight is not simulated.")
    return a, b


def scenario_from_query(hours=None, check_in=None, bands=None, pour_gate=None, pour_start=None, pour_m3=None,
                        pour_m3_per_load=None, pour_rate=None, site_speed=None, service=None, bays=None, wash=None,
                        arrivals=None, rush_share=None, rush_minutes=None):
    """
    The query parameters of GET /api/sim/day as one scenario, or ValueError in words. Nothing here is saved (D86).
      hours     repeated 'GATE=HH:MM-HH:MM', or 'all=HH:MM-HH:MM' for every gate (a gate's own wins over 'all')
      check_in  repeated 'GATE=minutes' ('GATE=' or 0 = no check-in: that gate never queues)
      bands     'on' or 'off' (unset: on when the scheme has bands typed)
      pour_*    gate, start HH:MM, m³, m³ a load (default: the app's mixer), pour rate in m³ an hour
      28 Oct 2026 (v2): site_speed repeated 'LOC=kph'; service repeated 'AREA=minutes'; bays 'AREA=n';
      wash 'on' or 'off' (unset: as typed)
      29 Oct 2026: arrivals 'even' (default) or 'rush'; rush_share 1–100 (%), rush_minutes 5–240 — the morning rush
    """
    sc = {"hours": {}, "all": None, "check_in": {}, "bands": None, "pour": None,
          "site_speed": {}, "service": {}, "bays": {}, "wash": None, "arrivals": {"kind": "even"}}
    kind = str(arrivals or "even").strip().lower()
    if kind not in ("even", "rush"):
        raise ValueError("arrivals must be even or rush")
    if kind == "rush":
        share = RUSH_DEFAULT_SHARE if rush_share in (None, "") else _num(rush_share, "The morning rush share")
        if not (1 <= share <= 100):
            raise ValueError("The morning rush share must be between 1 and 100 %.")
        mins = RUSH_DEFAULT_MINUTES if rush_minutes in (None, "") else _num(rush_minutes, "The morning rush minutes")
        if not (RUSH_MIN_MINUTES <= mins <= RUSH_MAX_MINUTES):
            raise ValueError(f"The morning rush must last between {RUSH_MIN_MINUTES:g} and {RUSH_MAX_MINUTES:g} minutes.")
        sc["arrivals"] = {"kind": "rush", "share": share / 100.0, "minutes": float(mins)}
    elif rush_share not in (None, "") or rush_minutes not in (None, ""):
        raise ValueError("rush_share and rush_minutes go with arrivals=rush.")
    for item in site_speed or []:
        if not item:
            continue
        if "=" not in item:
            raise ValueError("site_speed must be given as LOCATION=km/h")
        g, v = [x.strip() for x in item.split("=", 1)]
        k = _num(v, f"{g}: the site speed")
        if not (0 < k <= 60):
            raise ValueError(f"{g}: the site speed must be above 0 and at most 60 km/h")
        sc["site_speed"][g] = k
    for item in service or []:
        if not item:
            continue
        if "=" not in item:
            raise ValueError("service must be given as AREA=minutes")
        g, v = [x.strip() for x in item.split("=", 1)]
        m = _num(v, f"{g}: the minutes a lorry")
        if m < 0 or m > MAX_CHECK_IN:
            raise ValueError(f"{g}: the minutes a lorry must be between 0 and {MAX_CHECK_IN:g}")
        sc["service"][g] = m
    for item in bays or []:
        if not item:
            continue
        if "=" not in item:
            raise ValueError("bays must be given as AREA=n")
        g, v = [x.strip() for x in item.split("=", 1)]
        n = _num(v, f"{g}: the bays")
        if n < 1 or n > site_areas.MAX_BAYS or n != int(n):
            raise ValueError(f"{g}: bays must be a whole number between 1 and {site_areas.MAX_BAYS}")
        sc["bays"][g] = int(n)
    if wash not in (None, ""):
        w = str(wash).strip().lower()
        if w not in ("on", "off"):
            raise ValueError("wash must be on or off")
        sc["wash"] = (w == "on")
    for item in hours or []:
        if not item:
            continue
        if "=" not in item:
            raise ValueError("hours must be given as GATE=07:00-17:00")
        g, v = [x.strip() for x in item.split("=", 1)]
        if g.lower() == "all":
            sc["all"] = _hours_pair(v, "Every gate")
        else:
            sc["hours"][g] = _hours_pair(v, g)
    for item in check_in or []:
        if not item:
            continue
        if "=" not in item:
            raise ValueError("check_in must be given as GATE=minutes")
        g, v = [x.strip() for x in item.split("=", 1)]
        if v == "":
            sc["check_in"][g] = None
            continue
        c = _num(v, f"{g}: the check-in")
        if c < 0 or c > MAX_CHECK_IN:
            raise ValueError(f"{g}: the check-in must be between 0 and {MAX_CHECK_IN:g} minutes")
        sc["check_in"][g] = c if c > 0 else None
    if bands not in (None, ""):
        b = str(bands).strip().lower()
        if b not in ("on", "off"):
            raise ValueError("bands must be on or off")
        sc["bands"] = (b == "on")
    if pour_gate not in (None, ""):
        st = gate_hours.minutes_of(pour_start) if pour_start not in (None, "") else None
        try:
            m3 = _num(pour_m3, "The pour's volume")
            rate = _num(pour_rate, "The pour rate")
            mpl = None if pour_m3_per_load in (None, "") else _num(pour_m3_per_load, "The mixer load")
        except ValueError:
            raise ValueError("The pour needs a volume, a mixer load and a pour rate above nothing.")
        sc["pour"] = {"gate": str(pour_gate).strip(), "start": st, "m3": m3, "m3_per_load": mpl, "rate": rate}
    return sc


def pour_site(loc):
    """True for a location a pour can go to: its type is Compound or Site (POUR_SITE_TYPES)."""
    return str((loc or {}).get("loc_type") or "").strip().lower() in POUR_SITE_TYPES


def pour_gates(gate_rows, locations, laden_by_gate):
    """
    The gates a pour can go to — the active entry gates of the working sites (pour_site) — busiest first: the most
    laden lorries a day in the month (the Dashboard's Gate arrivals figure), then the site's name. The first is the
    default pour gate. [{gate_id, gate_name, location_id, location_name, laden_per_day}]
    """
    out = []
    for gid, g in gate_rows.items():
        loc = locations.get(g.get("location_id")) or {}
        if not g.get("active") or not gates.serves(g, "entry") or not pour_site(loc):
            continue
        out.append({"gate_id": gid, "gate_name": g.get("name"), "location_id": g.get("location_id"),
                    "location_name": loc.get("name") or g.get("location_id") or "",
                    "laden_per_day": float(laden_by_gate.get(gid) or 0.0)})
    out.sort(key=lambda x: (-x["laden_per_day"], x["location_name"], x["gate_id"]))
    return out


def mixer_m3(factors):
    """(m³ a load, vehicle name) — the app's own mixer's legal fill; the first mixer typed; else 7.5 (stated)."""
    vs = (factors or {}).get("vehicles") or {}
    v = (vs.get(MIXER_NAME) or {}).get("payload_m3")
    if v:
        return float(v), MIXER_NAME
    for name, x in vs.items():
        if isinstance(x, dict) and x.get("payload_m3"):
            return float(x["payload_m3"]), name
    return MIXER_M3_FALLBACK, None


# --------------------------------------------------------------------------------------------------- reading the day
def _legs_for(route_ids, want_lines, days=None):
    """
    Each (route, vehicle profile, leg) the day needs: its stored time and, when `want_lines`, the line, the haul
    roads it was routed along and their speeds. Primary option only (alt_index 0).

    29 Oct 2026 (task 0c, PR B): with `days` (the period the day stands for: the month's or the week's working days,
    or the one date), a leg a dated zone diverts on most of those days runs on that diversion
    (route_choice.majority_alt) — its time, its line.
    """
    if not route_ids:
        return {}, {}
    marks = ",".join("?" * len(route_ids))
    cols = "route_id, vehicle_profile, leg, alt_index, duration_hr, distance_km, haul_zones" + (", geometry" if want_lines else "")
    rows = db.query(f"SELECT {cols} FROM route_geometry WHERE tenant_id = ? "
                    f"AND route_id IN ({marks})", (db.current_tenant(), *route_ids))
    per, alts = {}, {}
    for r in rows:
        a = int(r.get("alt_index") or 0)
        if a:
            alts[(r["route_id"], r["vehicle_profile"], r["leg"], a)] = r
        else:
            per.setdefault(r["route_id"], {}).setdefault(r["vehicle_profile"], {})[r["leg"]] = r
    if days and alts:
        import route_choice
        for rid, profs in per.items():
            for prof, legs in profs.items():
                for leg in list(legs):
                    a = route_choice.majority_alt(rid, prof, leg, days)
                    if a and (rid, prof, leg, a) in alts:
                        legs[leg] = alts[(rid, prof, leg, a)]
    zone_rows = {}
    if want_lines:
        for z in zones.list_zones(include_inactive=True):
            if z.get("kind") == zones.HAUL_KIND and z.get("geometry") and not z.get("location_id"):
                zone_rows[z["id"]] = z
    return per, zone_rows


def _weekday_dates(iso_from, iso_to):
    a, b = datetime.date.fromisoformat(iso_from), datetime.date.fromisoformat(iso_to)
    out = []
    while a <= b:
        if a.weekday() < 5:
            out.append(a)
        a += datetime.timedelta(days=1)
    return out


def _day_words(d):
    return d.strftime("%a %d %b %Y").replace(" 0", " ")


def _line_trips(qty, row, factors):
    """One day's trips for a Look-ahead line (the grid's own rule: derived.day_figures on an unbaked context)."""
    payload_t, _fb = derived.payload_for(row.get("vehicle_type"), factors)
    ctx = {"unit": row.get("unit"), "payload_t": payload_t, "material_type": row.get("material_type"),
           "vehicle_type": row.get("vehicle_type"), "baked": False}
    return int(derived.day_figures(qty, ctx, factors)["trips"])


def lookahead_lines(bucket, date, factors, today=None):
    """
    28 Oct 2026 (v2): the WEEK and DAY scales read the Look-ahead's day-by-day plan (forecast_days, the two buckets
    the Look-ahead holds: 'commit' = the week with today in it, 'next'). Each line's trips a weekday
    (days.list_days + derived.day_figures, the grid's own), summed over the week's weekdays; or one dated day's.
    Returns (rows like the month's forecast rows with `trips` and `share`, the week block, working days, on, choices).
    """
    bucket = "next" if bucket == "next" else "commit"
    full = days.list_days(bucket=bucket, today=today)
    cw = full.get("commit_week") or {}
    if not cw:
        raise ValueError("The Look-ahead has no week to simulate.")
    wdays = _weekday_dates(cw["from"], cw["to"])
    chosen = None
    if date is not None:
        try:
            chosen = datetime.date.fromisoformat(str(date)[:10])
        except ValueError:
            raise ValueError("The day must be a date such as 2027-04-14.")
        if chosen not in wdays:
            raise ValueError(f"{_day_words(chosen)} is not a weekday of the week of {_day_words(wdays[0])}: pick a day of "
                             f"the Look-ahead's two weeks.")
    rows, confirmed = [], 0
    for l in full.get("lines") or []:
        w = l.get("week") or {}
        if str(w.get("status") or "") == "confirmed":
            confirmed += 1
        by_date = {d["day_date"]: float(d.get("planned_qty") or 0) for d in (l.get("days") or [])}
        if chosen is not None:
            q = by_date.get(chosen.isoformat(), 0.0)
            trips = _line_trips(q, l, factors)
        else:
            trips = sum(_line_trips(by_date.get(d.isoformat(), 0.0), l, factors) for d in wdays)
        if trips <= 0:
            continue
        rows.append({"route_id": l["route_id"], "discipline": l.get("discipline") or "", "section_id": l.get("section_id") or "",
                     "ipt": l.get("ipt"), "vehicle_type": l.get("vehicle_type"), "material_type": l.get("material_type"),
                     "unit": l.get("unit"), "quantity": None, "trips": trips, "status": w.get("status")})
    week = {"bucket": bucket, "month_index": cw.get("month_index"), "week_index": cw.get("week_index"),
            "from": cw["from"], "to": cw["to"], "weekdays": len(wdays), "lines": len(full.get("lines") or []),
            "confirmed_lines": confirmed, "label": f"Week of {_day_words(wdays[0])}"}
    choices = day_choices_for(today)
    if chosen is not None:
        on, wd = chosen, 1
    else:
        on, wd = wdays[min(2, len(wdays) - 1)], max(1, len(wdays))
    return rows, week, wd, on, choices, chosen


def day_choices_for(today=None):
    """The days a person can pick for the day scale: the weekdays of the Look-ahead's two buckets."""
    choices = []
    for b in ("commit", "next"):
        try:
            mi, wi = days.bucket_of(b, today=today)
            if mi is None:
                continue
            for d in days.bucket_dates(mi, wi):
                if d.weekday() < 5:
                    choices.append({"date": d.isoformat(), "words": _day_words(d), "bucket": b})
        except Exception:
            continue
    return choices


def day(month_index, acc, factors=None, working_days=None, scenario=None, panel=None, with_lines=True,
        send_lines=False, scale="month", bucket="commit", date=None, today=None):
    """
    The contract behind GET /api/sim/day. Reads only. `scenario` from scenario_from_query (or None for the
    month as typed, no pour); `panel` = gate_arrivals.arrivals' reply when the caller already has it (month scale).
    `with_lines` False skips the routes' lines (the Gate arrivals panel needs the gates only: departures then come
    from the stored times, the pour's mixers have none, and the haul roads are not counted). `send_lines` puts each
    route's line, simplified, into the reply for the drawing.
    28 Oct 2026 (v2): `scale` 'month' (the forecast month's average working day, as before), 'week' (the Look-ahead
    week's average weekday, `bucket` commit | next) or 'day' (one dated weekday of those two weeks, `date`); the
    sites' station chains (sim_site) run at every scale.
    Raises ValueError (in words) for a scenario that cannot be simulated.
    """
    factors = factors or conversions.load_factors()
    sc = scenario or scenario_from_query()
    my_team = (acc or {}).get("ipt")
    team_scope = bool(my_team)
    scale = scale if scale in ("month", "week", "day") else "month"
    if scale == "day" and date in (None, ""):
        raise ValueError("The day scale needs a date: pick a weekday of the Look-ahead's two weeks.")

    week_block, day_choices, chosen = None, [], None
    if scale == "month":
        wd = gate_arrivals._positive(working_days, gate_arrivals._working_days(factors))
        panel = panel or gate_arrivals.arrivals(int(month_index), acc, factors=factors, working_days=wd)
        rows = db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND month_index = ? AND status = 'Approved' "
                        "ORDER BY route_id, discipline, section_id", (db.current_tenant(), int(month_index)))
        on_gate = int(month_index)
        label = gate_arrivals.month_label(int(month_index))
        day_choices = day_choices_for(today)
    else:
        rows, week_block, wd, on_gate, day_choices, chosen = lookahead_lines(bucket, date if scale == "day" else None,
                                                                            factors, today=today)
        month_index = week_block["month_index"]
        label = (_day_words(chosen) if scale == "day" else week_block["label"])
        panel = None
    routes = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (db.current_tenant(),))}
    locations = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    gbl = gates.gates_by_location()
    gate_rows = {g["id"]: g for gs in gbl.values() for g in gs}
    labels = taxonomy.team_labels()

    lines, closed_seen = [], {}
    for row in rows:
        route = routes.get(row.get("route_id"))
        if not route:
            continue
        trips = row["trips"] if scale != "month" else gate_arrivals.trips_for(row, factors)
        ends = {}
        for end, loc_key, gate_key in (("laden", "dest_id", "dest_gate_id"), ("empty", "origin_id", "origin_gate_id")):
            loc = locations.get(route.get(loc_key))
            if not loc:
                ends[end] = None
                continue
            r, blocked = gate_arrivals.entry_gate(loc, route.get(gate_key), gbl.get(loc["id"]) or [], on=on_gate)
            if blocked and blocked.get("reason") == "closed":
                closed_seen[blocked["gate_id"]] = (blocked, r.get("gate_name"), loc)
            ends[end] = r.get("gate_id")
        team_key = access.canonical_ipt(row.get("ipt")) or row.get("ipt")
        lines.append({"route_id": route["id"], "discipline": row.get("discipline") or "",
                      "section_id": row.get("section_id") or "", "team_key": team_key,
                      "team": taxonomy.team_name(team_key, labels) if team_key else None,
                      "vehicle": row.get("vehicle_type"), "material": row.get("material_type"),
                      "vehicle_label": conversions.vehicle_label(factors, row.get("vehicle_type")),
                      "quantity": row.get("quantity"), "unit": row.get("unit"),
                      "trips": trips, "share": trips / wd,
                      "laden_gate": ends["laden"], "empty_gate": ends["empty"],
                      "touch": [g for g in (ends["laden"], ends["empty"]) if g]})
    if panel is None:
        # the week's / the day's own reference figures: each gate's arrivals a day from the same lines
        per = {}
        for l in lines:
            for g, k in ((l["laden_gate"], "laden"), (l["empty_gate"], "empty")):
                if g:
                    per.setdefault(g, {"laden": 0.0, "empty": 0.0})[k] += l["share"]
        panel = {"gates": [{"gate_id": g, "arrivals_per_day": round(v["laden"] + v["empty"], 3),
                            "laden_per_day": round(v["laden"], 3)} for g, v in per.items()]}

    # the routes' times (and lines): each line's OWN vehicle where it was worked out, else the first that was (said)
    # 29 Oct 2026 (task 0c, PR B): the days this day stands for, so a leg diverted on most of them runs its diversion
    try:
        import route_choice
        if scale == "month":
            span_days = route_choice.month_days(int(month_index))
        elif scale == "day":
            span_days = [chosen]
        else:
            span_days = route_choice.week_days(int(week_block["month_index"]), int(week_block["week_index"]))
    except Exception:
        span_days = None
    per, zone_rows = _legs_for(sorted({l["route_id"] for l in lines}), with_lines, days=span_days)
    speed = {z: (zone_rows[z].get("speed_kph") or 0) for z in zone_rows}
    legs, leg_minutes, leg_meta, used_zones = {}, {}, {}, set()
    for l in lines:
        prof = per.get(l["route_id"]) or {}
        used = l["vehicle"] if l["vehicle"] in prof else (sorted(prof)[0] if prof else None)
        l["vehicle_drawn"] = used
        l["vehicle_as_planned"] = (used == l["vehicle"]) if used else None
        for kind, leg_name in (("laden", "loaded"), ("empty", "return")):
            key = f"{l['route_id']}|{used}|{leg_name}" if used else None
            l[f"{kind}_leg"] = key
            if not key or key in leg_meta:
                continue
            g = (prof.get(used) or {}).get(leg_name)
            other = (prof.get(used) or {}).get("loaded")
            src = g or (other if leg_name == "return" else None)            # no return worked out: the loaded reversed
            mins = (float(src["duration_hr"]) * 60.0) if (src and src.get("duration_hr")) else None
            leg_minutes[key] = mins
            leg_meta[key] = {"route_id": l["route_id"], "vehicle": used, "leg": leg_name,
                             "reversed": g is None and src is not None, "minutes": mins,
                             "distance_km": (float(src["distance_km"]) if src and src.get("distance_km") is not None else None)}
            if with_lines and src and src.get("geometry") and mins:
                try:
                    coords = [[float(p[0]), float(p[1])] for p in json.loads(src["geometry"])]
                except Exception:
                    coords = None
                hz = [z for z in (src.get("haul_zones") or "").split(",") if z]
                roads = {z: zones.as_line(zone_rows[z]["geometry"]) for z in hz if z in zone_rows}
                used_zones.update(roads)
                built = build_leg(coords, mins, roads, speed) if coords else None
                if built and g is None:
                    built = reversed_leg(built, speed)
                legs[key] = built
            else:
                legs[key] = None

    # the gates of the day: every entry gate a line arrives by, plus the pour's
    gate_ids = []
    for l in lines:
        for g in (l["laden_gate"], l["empty_gate"]):
            if g and g not in gate_ids:
                gate_ids.append(g)
    p = sc.get("pour")
    pgates = pour_gates(gate_rows, locations, {g["gate_id"]: g.get("laden_per_day") for g in panel.get("gates") or []})
    if p:
        pg = gate_rows.get(p["gate"])
        if not pg or not pg.get("active") or not gates.serves(pg, "entry"):
            raise ValueError("The pour's gate is not one of this scheme's entry gates.")
        if p["gate"] not in {x["gate_id"] for x in pgates}:
            ploc = locations.get(pg.get("location_id")) or {}
            raise ValueError(f"A pour goes to a working site (a compound or a site): {ploc.get('name') or p['gate']} "
                             f"is {('a ' + str(ploc.get('loc_type')).strip().lower()) if ploc.get('loc_type') else 'not one'}.")
        if gates.closed_on(pg, on_gate):
            raise ValueError(f"{pg.get('name')} is {gates.closed_words(pg)}: pour by the site's other gate.")
        if p.get("m3_per_load") is None:
            p = dict(p, m3_per_load=mixer_m3(factors)[0])
        prob = pour_problem(p["start"], p["m3"], p["m3_per_load"], p["rate"])
        if prob:
            raise ValueError(prob)
        if p["gate"] not in gate_ids:
            gate_ids.append(p["gate"])
    for g in list(sc["hours"]) + list(sc["check_in"]):
        if g not in gate_rows:
            raise ValueError(f"{g} is not one of this scheme's gates.")

    typed_bands = gate_hours.peak_bands(factors)
    bands_on = sc["bands"] if sc["bands"] is not None else bool(typed_bands)
    bands_src = ("typed" if typed_bands else "example") if bands_on else None
    bands = (typed_bands or gate_hours.PEAK_PLACEHOLDER) if bands_on else []

    # 17 Oct 2026 (the user): a gate with no hours typed is open the default gate hours (never past midnight: Config
    # refuses it), no longer the lorry shift placed at 07:00
    dflt = gate_hours.default_hours(factors)
    dwin = (gate_hours.minutes_of(dflt["from"]), gate_hours.minutes_of(dflt["to"]))
    G, notes, refused = {}, [], []
    for gid in gate_ids:
        grow = gate_rows.get(gid) or {}
        typed = (gate_hours.minutes_of(grow.get("open_from")), gate_hours.minutes_of(grow.get("open_to")))
        if gid in sc["hours"]:
            win, basis = sc["hours"][gid], "scenario"
        elif sc["all"]:
            win, basis = sc["all"], "scenario"
        elif gate_hours.window_of(grow):
            a, b = gate_hours.window_of(grow)
            b = gate_hours._end(a, b)       # 17 Oct 2026: closing at 00:00 = the end of the same day, not past midnight
            if b <= a:
                win, basis = None, "refused"
                refused.append(gid)
            else:
                win, basis = (a, b), "gate"
        else:
            win, basis = dwin, "default"
        ci = sc["check_in"][gid] if gid in sc["check_in"] else grow.get("safety_minutes")
        ci = float(ci) if ci not in (None, "") and float(ci) > 0 else None
        shut = gate_hours.shut_windows(grow)
        G[gid] = {"window": win, "basis": basis, "check_in": ci, "typed": typed,
                  "shut": band_intervals(shut), "shut_typed": shut}

    # 28 Oct 2026 (v2): the sites with areas or internal roads — their station chains (sim_site)
    areas_by = site_areas.by_location(include_inactive=True)
    roads_by = zones.internal_roads()
    for aid in list(sc.get("service") or {}) + list(sc.get("bays") or {}):
        if not any(a["id"] == aid for al in areas_by.values() for a in al):
            raise ValueError(f"{aid} is not one of this scheme's site areas.")
    for lid in list(sc.get("site_speed") or {}):
        if lid not in locations:
            raise ValueError(f"{lid} is not one of this scheme's sites.")
    sites = {}
    for lid, loc in locations.items():
        areas = areas_by.get(lid) or []
        roads = [dict(z, line=zones.as_line(z["geometry"])) for z in (roads_by.get(lid) or [])]
        if not any(a["active"] for a in areas) and not roads:
            continue
        sites[lid] = sim_site.site_model(loc, gbl.get(lid) or [], areas, roads, factors, sc, on=on_gate)
    gate_loc = {gid: g.get("location_id") for gid, g in gate_rows.items()}

    # 17 Oct 2026: a gate's ACCESS ROAD (location_gates.access_zone_id) is a haul-road zone too, and lorries still cross
    # it at its speed (the legs above are untouched), but it is the last few metres to a gate, not a haul road a planner
    # watches: it is not listed or counted with the haul roads. The reply says how many were left out.
    access_ids = {g.get("access_zone_id") for g in gate_rows.values() if g.get("access_zone_id")}
    inp = {"lines": lines, "gates": G, "legs": legs, "leg_minutes": leg_minutes, "empty_window": dwin,
           "panel": {g["gate_id"]: g["arrivals_per_day"] for g in panel.get("gates") or []},
           # the day scale: each line's trips are already whole (no rounding)
           "fixed": ([l["trips"] for l in lines] if scale == "day" else None),
           # the haul roads some leg of the day was routed along (an unused or switched-off road is not listed)
           "haul_roads": {z: zone_rows[z] for z in sorted(used_zones - access_ids)} if with_lines else {},
           "sites": sites, "gate_loc": gate_loc, "factors": factors}
    if p:
        sc = dict(sc, pour=p)
    pattern = sc.get("arrivals") or {"kind": "even"}
    res = simulate(inp, {"bands": bands, "pour": sc.get("pour"), "arrivals": pattern})

    # 29 Oct 2026: the plan's own first trips at each gate — its lorries (each line's loads a day ÷ the trips one lorry
    # makes a day, rounded up: the Dashboard's vehicles rule through derived.cycle_for) over its arrivals; None where a
    # line at the gate has no cycle worked out. A planning aid for the morning-rush share, never a figure of the day.
    first_trips = {}
    try:
        _cc = {}
        _wk = (int(week_block["week_index"]) if (scale != "month" and week_block) else None)
        _mi = (int(week_block["month_index"]) if (scale != "month" and week_block) else int(month_index))
        for li, l in enumerate(lines):
            row = derived.cycle_for(l["route_id"], l.get("vehicle_drawn") or l.get("vehicle"), _cc, month_index=_mi, week_index=_wk)
            tpd = int((row or {}).get("trips_per_day") or 0)
            loads = res["per_line"][li]
            lorries = (math.ceil(loads / tpd) if (tpd > 0 and loads > 0) else (0 if loads == 0 else None))
            for g in (l["laden_gate"], l["empty_gate"]):
                if not g:
                    continue
                ft = first_trips.setdefault(g, {"lorries": 0, "known": True})
                if lorries is None:
                    ft["known"] = False
                else:
                    ft["lorries"] += lorries
    except Exception:
        first_trips = {}

    # ---- the reply
    panel_by = {g["gate_id"]: g for g in panel.get("gates") or []}
    out_gates = []
    for gid in gate_ids:
        f = res["gates"][gid]
        grow = gate_rows.get(gid) or {}
        loc = locations.get(grow.get("location_id")) or {}
        win = G[gid]["window"]
        teams = sorted({lines[a["line"]]["team"] for a in f["queued"]
                        if a["line"] is not None and lines[a["line"]]["team"]})
        words = None
        if G[gid]["basis"] == "default":
            words = f"No open hours typed for this gate: open {hhmm(win[0])}–{hhmm(win[1])}, the default gate hours."
        elif G[gid]["basis"] == "refused":
            words = (f"Open {grow.get('open_from')}–{grow.get('open_to')} runs past midnight: the simulation shows one "
                     f"day, midnight to midnight, so this gate is left out.")
        out_gates.append({
            "gate_id": gid, "gate_name": grow.get("name"), "location_id": grow.get("location_id"),
            "location_name": loc.get("name") or grow.get("location_id") or "",
            "lat": grow.get("lat"), "lon": grow.get("lon"),
            "origin_share_note": NOTE_ORIGIN if loc.get("role") == "origin" else None,
            "teams": teams,
            "panel_per_day": (panel_by.get(gid) or {}).get("arrivals_per_day"),
            "open_from": hhmm(win[0]) if win else None, "open_to": hhmm(win[1]) if win else None,
            "open_basis": G[gid]["basis"], "open_words": words,
            # 17 Oct 2026: the gate's shut windows as typed (always applied) and their words
            "shut_windows": G[gid]["shut_typed"], "shut_words": gate_hours.peak_words(G[gid]["shut_typed"]),
            # 28 Oct 2026 (v2): in and out by this gate while the site's other gate is closed
            "closed_words": gates.closed_words(grow),
            "serves_exit_too": any(k == gid for k, _v in closed_seen_to(closed_seen)),
            "departures": res["departures"].get(gid, 0),
            "arrivals": f["arrivals"], "laden": f["laden"], "empty": f["empty"], "pour": f["pour"],
            "unplaced": f["unplaced"],
            "open_minutes": f["open_minutes"], "intervals": f["intervals"], "last_open": f["last_open"],
            "check_in": f["check_in"], "capacity": f["capacity"], "pct": f["pct"], "gap": f["gap"],
            "flag": f["flag"], "status_word": f["status_word"],
            "hours": f["hours"], "busiest": f["busiest"], "busiest_hours": f["busiest_hours"],
            "busiest_hour": f["busiest_hour"],
            "per_hour": _r2(f["per_hour"]), "even_rate": _r2(f["even_rate"]),
            "queue_start": _r2(f["queue_start"]), "bottleneck_at": _r2(f["bottleneck_at"]),
            "most_waiting": f["most_waiting"], "most_at": _r2(f["most_at"]),
            "minutes_lost": _r2(f["minutes_lost"]), "longest_wait": _r2(f["longest_wait"]),
            "late": f["late"], "last_done": _r2(f["last_done"]),
            # 29 Oct 2026: the morning rush's lorries at this gate, and the plan's first-trip share (None when unknown)
            "rush_n": f.get("rush_n", 0),
            "first_trip_share": (round(min(1.0, first_trips[gid]["lorries"] / (f["laden"] + f["empty"])), 2)
                                 if (gid in first_trips and first_trips[gid]["known"] and (f["laden"] + f["empty"]) > 0) else None),
            "first_trip_lorries": (first_trips[gid]["lorries"] if (gid in first_trips and first_trips[gid]["known"]) else None),
            # the same share as a whole per cent for the screen (the browser works out no figure)
            "first_trip_pct": (int(round(min(1.0, first_trips[gid]["lorries"] / (f["laden"] + f["empty"])) * 100))
                               if (gid in first_trips and first_trips[gid]["known"] and (f["laden"] + f["empty"]) > 0) else None),
        })
    out_gates.sort(key=lambda g: (-g["arrivals"], g["gate_id"]))

    def mine(li):
        return (not team_scope) or (li is not None and access.canonical_ipt(lines[li]["team_key"]) == my_team)

    arrivals = []
    for gid in gate_ids:
        for a in res["gates"][gid]["queued"]:
            arrivals.append({"gate": gid, "kind": a["kind"],
                             "line": a["line"] if (a["line"] is None or mine(a["line"])) else None,
                             "route": a["route"], "leg": a.get("leg"),
                             "at": _r2(a["t"]), "start": _r2(a["start"]), "wait": _r2(a["wait"]),
                             "done": _r2(a["done"]), "depart": _r2(a.get("depart")),
                             "from_m": _r2(a.get("from_m")), "t_from": _r2(a.get("t_from")),
                             # 28 Oct 2026 (v2): on site — the stations after the gate and the drives between them
                             "site": gate_loc.get(gid) if a.get("chain") else None,
                             "stops": [{"st": s["st"], "at": _r2(s["t"]), "start": _r2(s["start"]), "done": _r2(s["done"]),
                                        "bay": s["bay"]} for s in (a.get("stops") or [])],
                             "hops": [{"path": h["path"], "t0": _r2(h["t0"]), "t1": _r2(h["t1"])} for h in (a.get("hops") or [])],
                             "out_at": _r2(a.get("out_at")), "on_site": _r2(a.get("on_site")),
                             "no_area": bool(a.get("no_area"))})
    arrivals.sort(key=lambda a: (a["at"], a["gate"]))

    out_lines = []
    for li, l in enumerate(lines):
        # vehicle keys are ids ("Truck mixer …"); what a person reads is conversions.vehicle_label (the word rule)
        base = {"line": li, "route_id": l["route_id"], "team": l["team"], "vehicle_drawn": l["vehicle_drawn"],
                "vehicle_drawn_label": conversions.vehicle_label(factors, l["vehicle_drawn"]),
                "laden_gate": l["laden_gate"], "empty_gate": l["empty_gate"],
                "laden_leg": l["laden_leg"], "empty_leg": l["empty_leg"]}
        if mine(li):
            base.update({"discipline": l["discipline"], "section_id": l["section_id"], "vehicle": l["vehicle"],
                         "vehicle_label": l["vehicle_label"],
                         "vehicle_as_planned": l["vehicle_as_planned"], "material": l["material"],
                         "trips_month": l["trips"], "per_day": round(l["share"], 3), "loads": res["per_line"][li]})
        out_lines.append(base)

    haul = []
    for z, h in res["haul"].items():
        zr = zone_rows.get(z) or {}
        b = max(h["hours"]) if h["hours"] else 0
        line = zones.as_line(zr.get("geometry")) if (send_lines and zr.get("geometry")) else None
        haul.append({"zone_id": z, "name": zr.get("name"), "speed_kph": zr.get("speed_kph"),
                     "length_km": zr.get("length_km"), "lorries": h["n"], "busiest": b,
                     "busiest_hour": (f"{h['hours'].index(b):02d}:00" if b else None),
                     "routes": sorted(h["routes"]),
                     # 17 Oct 2026 (S7): the drawn road, for the Dashboard's map (legs=1 only)
                     "coords": ([[round(float(p[0]), 6), round(float(p[1]), 6)] for p in line] if line else None)})
    haul.sort(key=lambda h: h["zone_id"])

    out_legs = {}
    for key, m in leg_meta.items():
        lg = legs.get(key)
        out_legs[key] = dict(m, drawn=bool(lg))
        if lg and send_lines:
            out_legs[key].update({"coords": lg["coords"], "len_m": round(lg["len_m"], 1),
                                  "cum": [round(c, 1) for c in lg["cum"]],
                                  "parts": [[round(q["a"], 1), round(q["b"], 1), round(q["mpm"], 4), q["zone"],
                                             round(q["t0"], 3), round(q["t1"], 3)] for q in lg["plan"]["parts"]],
                                  "plan_minutes": round(lg["plan"]["minutes"], 3)})

    pour = res["pour"]
    if pour:
        pour = {"gate": pour["gate"], "start": hhmm(pour["start"]), "m3": pour["m3"],
                "m3_per_load": pour["m3_per_load"], "rate": pour["rate"], "loads": pour["loads"],
                "gap_minutes": _r2(pour["gap"]), "end": hhmm(pour["end"]), "approach_leg": pour["approach_leg"],
                "while_shut": pour.get("while_shut", 0)}

    # 28 Oct 2026 (v2): the sites' blocks and their words
    out_sites = [sim_site.site_reply(sites[lid], res["sites"][lid], send_lines) for lid in sorted(sites, key=lambda k: sites[k]["name"])]
    for s in out_sites:
        if s["speed_basis"] == "default":
            notes.append(f"{s['name']}: no site speed typed, so the simulation's default site speed stands in "
                         f"(Data → Locations).")
        for na in s["no_area"]:
            who = f"route {na['route']}" if na["route"] else "the pour"
            notes.append(f"{s['name']}: no area takes {na['material'] or 'this material'} from {who}, so those "
                         f"{na['lorries']} lorries leave from the gate.")
    for gid, (blocked, to_name, loc) in sorted(closed_seen.items()):
        notes.append(f"{loc.get('name') or loc.get('id')}: {blocked.get('name')} {gates.closed_words(blocked)}: "
                     f"in and out by {to_name}.")

    n_pour = pour["loads"] if pour else 0
    total_arr = sum(g["arrivals"] for g in out_gates)
    expect = sum(res["per_line"][i] * len(l["touch"]) for i, l in enumerate(lines)) + n_pour
    diffs = [abs((g["laden"] + g["empty"]) - g["panel_per_day"]) for g in out_gates if g["panel_per_day"] is not None]
    if refused:
        notes.append("Open hours past midnight are not simulated (one day, midnight to midnight): "
                     + ", ".join(f"{(locations.get((gate_rows.get(g) or {}).get('location_id')) or {}).get('name') or g}" for g in refused)
                     + " left out.")
    if any(G[g]["basis"] == "default" for g in gate_ids):
        notes.append(f"Gates with no open hours typed are open {hhmm(dwin[0])}–{hhmm(dwin[1])}, the default gate hours "
                     f"(Config → Planning). Type a gate's own hours and shut times on its gate, under Data → Locations.")
    if any(G[g]["shut_typed"] for g in gate_ids):
        notes.append("Each gate's shut times are taken off its open hours; a lorry that comes while its gate is shut "
                     "waits for it to open.")
    # 17 Oct 2026 (review): a gate whose bands and shut times leave no open minute places none of its lorries — said
    for g in gate_ids:
        if G[g]["window"] is not None and res["gates"][g]["open_minutes"] <= 0 and res["gates"][g]["unplaced"]:
            _gr = gate_rows.get(g) or {}
            notes.append(f"{(locations.get(_gr.get('location_id')) or {}).get('name') or g}, {_gr.get('name') or g}: the "
                         f"no-delivery bands and its shut times leave no open time, so its {res['gates'][g]['unplaced']} "
                         f"lorries are not placed.")
    if res["pour"] and res["pour"].get("while_shut"):
        _pg = gate_rows.get(res["pour"]["gate"]) or {}
        _pn = (locations.get(_pg.get("location_id")) or {}).get("name") or res["pour"]["gate"]
        notes.append(f"{res['pour']['while_shut']} of the pour's {res['pour']['loads']} mixers come while {_pn} is shut "
                     f"(before it opens, in a no-delivery band or a shut time); they wait for it to open.")
    if bands_src == "example":
        notes.append(f"No peak bands are typed: Config's example bands ({gate_hours.peak_words(bands)}) stand in.")
    if not res["rounding_exact"]:
        notes.append("This month has many lines: the whole loads of the day are the closest found in the search, not "
                     "the closest possible.")
    if team_scope:
        word = (taxonomy._team_word() or "Team").lower()
        notes.append(f"Lines of another {word} are shown by route only: their own figures are theirs.")
    mx, mx_name = mixer_m3(factors)
    return {
        "month": int(month_index), "label": label,
        # 28 Oct 2026 (v2): the scale and what it reads
        "scale": scale, "week": week_block, "date": (chosen.isoformat() if chosen else None),
        "day_choices": day_choices,
        "working_days": wd, "scope": "team" if team_scope else "scheme",
        "loads": res["total"], "loads_month": sum(l["trips"] for l in lines),
        "gate_arrivals": total_arr,
        "lines": out_lines, "gates": out_gates, "arrivals": arrivals, "pour": pour, "haul_roads": haul,
        "sites": out_sites,
        "access_roads_hidden": (len(used_zones & access_ids) if with_lines else 0),
        # 17 Oct 2026: where a pour can go (working sites only), busiest first; the first is the screen's default
        "pour_gates": pgates, "pour_default": (pgates[0]["gate_id"] if pgates else None),
        "legs": out_legs,
        # routes the drawing cannot show: no route worked out for any vehicle (their lorries still count at the gates)
        "not_drawn": (sorted({l["route_id"] for l in lines if not (l["laden_leg"] and legs.get(l["laden_leg"]))})
                      if with_lines else None),
        "window": {"start": res["window"][0], "end": res["window"][1],
                   "from": hhmm(res["window"][0]), "to": hhmm(res["window"][1])},
        "bands": {"on": bands_on, "source": bands_src, "bands": bands, "typed": typed_bands,
                  "words": gate_hours.peak_words(bands)},
        # 29 Oct 2026: the arrival pattern the day was placed by (on screen only, like the rest of the scenario)
        "arrival_pattern": pattern_words(pattern),
        "mixer": {"m3_per_load": mx, "vehicle": mx_name,
                  "vehicle_label": conversions.vehicle_label(factors, mx_name) if mx_name else None},
        # 17 Oct 2026: the default gate hours (was "stand_in", the lorry shift placed at 07:00)
        "default_hours": {"from": hhmm(dwin[0]), "to": hhmm(dwin[1])},
        # COMPATIBILITY, one release (review, 17 Oct 2026): a Dashboard opened before the deploy still reads
        # D.stand_in.from when its Simulation section mounts, and the page would go blank without it. Remove after.
        "stand_in": {"from": hhmm(dwin[0]), "to": hhmm(dwin[1]), "shift_hours": (dwin[1] - dwin[0]) / 60.0},
        "near_pct": gate_hours.NEAR_PCT,
        "site_speed_default_kph": sim_site.DEFAULT_SITE_KPH,
        "checks": {"arrivals_listed": len(arrivals), "arrivals_expected": expect,
                   "table_equals_arrivals": total_arr == len(arrivals) == expect - sum(g["unplaced"] for g in out_gates),
                   "hours_add_up": all(sum(g["hours"]) == g["arrivals"] for g in out_gates),
                   "largest_panel_difference": (round(max(diffs), 2) if diffs else None),
                   # 28 Oct 2026 (v2): every chained lorry left by a gate, and the stations' arrivals add up
                   "sites_add_up": all(s["lorries_out"] + sum(n["lorries"] for n in s["no_area"]) == s["lorries_in"]
                                       for s in out_sites)},
        "rounding": {"exact": res["rounding_exact"], "worst": round(res["rounding_worst"], 3)},
        "notes": notes, "limits": list(LIMITS),
    }


def pattern_words(pattern):
    """The reply's `arrival_pattern`: kind, the share in %, the minutes, and one sentence for the screen."""
    if pattern and pattern.get("kind") == "rush":
        share = int(round(float(pattern["share"]) * 100))
        mins = float(pattern["minutes"])
        return {"kind": "rush", "share": share, "minutes": (int(mins) if mins == int(mins) else mins),
                "words": f"A morning rush: {share} % of each gate's lorries in the first {mins:g} min, the rest spread "
                         f"evenly over its open hours"}
    return {"kind": "even", "share": None, "minutes": None,
            "words": "Each gate's arrivals are spread evenly over its open hours"}


def closed_seen_to(closed_seen):
    """[(the gate id lorries went to instead, the closed gate id)] — for the gate rows' 'serves the exit too' flag."""
    out = []
    for cg, (blocked, to_name, loc) in closed_seen.items():
        for g in gates.list_gates(loc.get("id")):
            if g.get("name") == to_name:
                out.append((g["id"], cg))
    return out


def busiest(month_index, acc, factors, working_days, panel):
    """
    The Dashboard's Gate arrivals panel: per gate, the lorries in the busiest clock hour of the simulation's average
    day (no pour, the gates as typed, the bands as typed), the hour, and what the gate can check in an hour.
    {gate id: {...}} plus the words the panel prints. Never raises: a day that cannot be simulated gives {}.
    """
    try:
        d = day(month_index, acc, factors=factors, working_days=working_days, panel=panel, with_lines=False)
    except Exception:
        return {"gates": {}, "note": None}
    out = {}
    for g in d["gates"]:
        out[g["gate_id"]] = {"lorries": g["busiest"], "hour": g["busiest_hour"],
                             "hours": [f"{h:02d}:00" for h in g["busiest_hours"]],
                             "per_hour": g["per_hour"], "open_basis": g["open_basis"],
                             "open_from": g["open_from"], "open_to": g["open_to"]}
    dflt = any(g["open_basis"] == "default" for g in d["gates"])
    shut = any(g["shut_windows"] for g in d["gates"])
    note = (f"Busiest hour: the lorries arriving in the busiest clock hour of an average working day, {d['loads']} "
            f"whole loads spread evenly over each gate's open hours"
            + (f" ({d['default_hours']['from']}–{d['default_hours']['to']} where none are typed)" if dflt else "")
            + (", its shut times" if shut and d["bands"]["on"] else (", its shut times taken off" if shut else ""))
            + (f"{' and' if shut else ','} the no-delivery bands {d['bands']['words']} taken off" if d["bands"]["on"] else "")
            + ". No pour.")
    return {"gates": out, "note": note, "loads": d["loads"]}
