"""
section_select.py — the public map's road card and "Select an area". Wayscope, 10 Nov 2026 (v2.1 task 2.1-4).

THE ASK (John, 9 Nov 2026, mockup notes/map-section-select-mockup-1109, Q1-Q10 "as recommended"): click any road a
route uses and see every route on it, in every heat map mode; drag a box and get one summed table of every route that
enters it, for the month on screen, ready to copy into a council email.

THE COUNT is 2.1-1's: traffic_limits.through(geometry, month) — each PASS of a leg is a movement, the loaded leg "in"
on the roads it runs, the empty way back "out" on the roads it runs (counting.py, 2.1-11b's question A), the month's
approved loads ÷ its working days, a dated diversion's share of the days on the option it uses. Nothing here counts
differently; this module only says WHICH geometry is asked about.

  a ROAD (Q1-Q4)  — the clicked point is matched to the nearest stored leg the map draws (within `r` metres, the
                    click's tolerance in metres at the map's zoom, PICK_M_MIN..PICK_M_MAX), and a PIECE_M piece of
                    that leg round the point is the "line" through() tests (a leg within 25 m for half of it passes:
                    the routes that share that road there, whichever leg was clicked);
  an AREA (Q5-Q6) — a box west, south, east, north; a leg counts if it ENTERS the box at all (BOX_ENTER_KM, not the
                    200 m an area limit asks for: Q5, "for a box a person draws, 'it enters' is plainer"). A route is
                    counted once whatever it does inside: in = its loads if the loaded leg enters, out = its loads if
                    the way back does.

No month (Q4): the routes by reference, no figures. The organisation's count (counting.per_visit) decides "a day":
in + out under 2, the route's lorries once under 1.

WHAT IT READS ONCE: traffic_limits.context() (the drawn legs, the approved lines by month, the working days) is kept
per tenant until the next write (db.data_version, noted BEFORE the read, so a write mid-build is never kept). The
public reads in main.py run in one of heavy_reads' slots; a click or a box after the first is a few hundred ms.
Team names never leave here (the map has them; the Copy leaves them out, Q8).
"""
import math
import threading

import counting
import db
import traffic_limits

#: the piece of road a click asks about, metres (a short stretch: the routes on THAT road, not the next junction's)
PIECE_M = 150.0
#: the click's reach, metres (the map sends ~10 px at its zoom, clamped to this)
PICK_M_MIN, PICK_M_MAX, PICK_M_DEFAULT = 5.0, 120.0, 30.0
#: a box: a leg counts if this much of it is inside (1 m = "enters at all")
BOX_ENTER_KM = 0.001
#: the largest box, km across its diagonal (the whole of a big scheme; refuses only a slip that drew the country)
BOX_MAX_KM = 200.0

_CTX = {}
_LOCK = threading.Lock()


def _ctx():
    """traffic_limits.context() with its lines read once and each leg's bounding box, kept until the next write."""
    tenant, version = db.current_tenant(), db.data_version()        # noted BEFORE any read
    with _LOCK:
        hit = _CTX.get(tenant)
        if hit and hit[0] == version:
            return hit[1]
    c = traffic_limits.context()
    by_month = c["lines_by_month"]()
    c["lines_by_month"] = lambda v=by_month: v
    c["boxes"] = [(rid, leg, alt, pts, (min(p[0] for p in pts), min(p[1] for p in pts),
                                        max(p[0] for p in pts), max(p[1] for p in pts)))
                  for rid, leg, alt, pts in c["legs"]]
    with _LOCK:
        _CTX[tenant] = (version, c)
    return c


def warm():
    """True when what a click reads is already in memory for this tenant and data version (a click then needs no
    heavy-read slot: it only walks the kept legs)."""
    with _LOCK:
        hit = _CTX.get(db.current_tenant())
        return bool(hit and hit[0] == db.data_version())


def forget():
    """Drop what is kept (tests)."""
    with _LOCK:
        _CTX.clear()


# --------------------------------------------------------------------------- #
#  A road: the piece of the nearest leg round the click                        #
# --------------------------------------------------------------------------- #
def _nearest(boxes, lon, lat, r_m):
    """(distance m, coords, segment index, t along it) of the stored leg nearest the point, within r_m; else None."""
    f = traffic_limits._proj(lat)
    p = f((lon, lat))
    pad_x = r_m / (111320.0 * max(0.01, math.cos(math.radians(lat))))
    pad_y = r_m / 110540.0
    best = None
    for _rid, _leg, _alt, pts, bb in boxes:
        if lon < bb[0] - pad_x or lon > bb[2] + pad_x or lat < bb[1] - pad_y or lat > bb[3] + pad_y:
            continue
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            if (max(a[0], b[0]) < lon - pad_x or min(a[0], b[0]) > lon + pad_x
                    or max(a[1], b[1]) < lat - pad_y or min(a[1], b[1]) > lat + pad_y):
                continue
            am, bm = f(a), f(b)
            dx, dy = bm[0] - am[0], bm[1] - am[1]
            L = dx * dx + dy * dy
            t = 0.0 if L <= 0 else max(0.0, min(1.0, ((p[0] - am[0]) * dx + (p[1] - am[1]) * dy) / L))
            d = math.hypot(p[0] - (am[0] + t * dx), p[1] - (am[1] + t * dy))
            if d <= r_m and (best is None or d < best[0]):
                best = (d, pts, i, t)
    return best


def _piece(pts, i, t, length_m=PIECE_M):
    """The [lon, lat] polyline of `length_m` along `pts`, centred on segment i at t (shorter at a leg's end)."""
    lat0 = sum(p[1] for p in pts) / len(pts)
    f = traffic_limits._proj(lat0)
    kx, ky = f((1.0, 1.0))
    m = [f(p) for p in pts]
    cum = [0.0]
    for a, b in zip(m, m[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cum[-1]
    s0 = cum[i] + t * (cum[i + 1] - cum[i])
    lo, hi = max(0.0, s0 - length_m / 2), min(total, s0 + length_m / 2)
    # a piece cut short at one end is lengthened at the other, so a click near a leg's end still asks about PIECE_M
    if hi - lo < length_m:
        lo, hi = max(0.0, hi - length_m), min(total, lo + length_m)

    def at(s):
        for k in range(len(cum) - 1):
            if cum[k + 1] >= s:
                seg = cum[k + 1] - cum[k]
                u = 0.0 if seg <= 0 else (s - cum[k]) / seg
                x, y = m[k][0] + u * (m[k + 1][0] - m[k][0]), m[k][1] + u * (m[k + 1][1] - m[k][1])
                return k, [round(x / kx, 6), round(y / ky, 6)]
        return len(m) - 2, [round(m[-1][0] / kx, 6), round(m[-1][1] / ky, 6)]
    k0, a = at(lo)
    k1, b = at(hi)
    out = [a] + [[round(p[0], 6), round(p[1], 6)] for p in pts[k0 + 1:k1 + 1]] + [b]
    dedup = [out[0]]
    for q in out[1:]:
        if q != dedup[-1]:
            dedup.append(q)
    return dedup


# --------------------------------------------------------------------------- #
#  The answer                                                                  #
# --------------------------------------------------------------------------- #
def _whole(x):
    """The whole number a screen shows for x (half up, as the map's Math.round and a traffic limit's figure)."""
    return int(math.floor(float(x) + 0.5))


def share_tenths(cells, total):
    """
    10 Nov 2026 (road card polish, John's Q1 = A: "one decimal in the table, whole headline"). `cells` (movements a
    day, any precision) as whole TENTHS that ADD UP: their sum is `total` to one decimal, and that sum to the nearest
    whole number is `total` to the nearest whole number — the figure the card's headline, the figures bar and a
    traffic limit on the same ground show.

    Each cell is rounded to its nearest tenth (so a route that is 59.56 each way reads 59.6 and 59.6, and its day
    119.2). Only when the cells then add to a different WHOLE number than `total` does one cell at a time move a
    tenth the other way — the one whose rounding moved it furthest — until they agree (171.46 as cells adding to
    171.5 would read 172 under a headline of 171). No cell ends more than a tenth from its value.

    Why the card cannot round three figures apart: 59.56 + 59.56 = 119.12 read "60 · 60 · 119" (seen on live,
    10 Nov), and fourteen rows rounded apart read 86 in, 85 out under a total of 172.
    """
    cells = [max(0.0, float(v or 0.0)) for v in cells]
    want = _whole(max(0.0, float(total or 0.0)))
    t = [int(math.floor(v * 10 + 0.5 + 1e-9)) for v in cells]
    for _ in range(10 * len(cells) + 10):
        got = _whole(sum(t) / 10.0)
        if got == want or not cells:
            break
        if got > want:      # too high: the cell rounded UP the most comes down a tenth
            cand = [i for i in range(len(t)) if t[i] > 0]
            if not cand:
                break
            i = max(cand, key=lambda j: (t[j] - cells[j] * 10, cells[j], -j))
            t[i] -= 1
        else:               # too low: the cell rounded DOWN the most goes up a tenth
            i = max(range(len(t)), key=lambda j: (cells[j] * 10 - t[j], cells[j], -j))
            t[i] += 1
    return t


def _rows(fig, pv):
    """Each route's In / Out / A day in the organisation's count, to ONE decimal and adding up (share_tenths): a
    row's A day is its In + Out, the totals are the rows added. Busiest first. `small` names a figure that is more
    than nothing but under a tenth (the card says "under 0.1", never a bare 0 for a route that runs).
    -> (rows, in, out, a_day)"""
    rs = fig["routes"]
    if pv == 2:
        cells = [v for r in rs for v in (r["in_per_day"], r["out_per_day"])]
        t = share_tenths(cells, fig["movements_per_day"])
        trip = [(t[2 * i], t[2 * i + 1], t[2 * i] + t[2 * i + 1]) for i in range(len(rs))]
    else:
        a = share_tenths([r["visits_per_day"] for r in rs], fig["visits_per_day"])
        trip = [(int(math.floor(r["in_per_day"] * 10 + 0.5)), int(math.floor(r["out_per_day"] * 10 + 0.5)), a[i])
                for i, r in enumerate(rs)]
    rows = []
    for r, (ti, to, ta) in zip(rs, trip):
        true = {"in": r["in_per_day"], "out": r["out_per_day"],
                "a_day": r["in_per_day"] + r["out_per_day"] if pv == 2 else r["visits_per_day"]}
        shown = {"in": ti, "out": to, "a_day": ta}
        row = {"route_id": r["route_id"], "in": ti / 10.0, "out": to / 10.0, "a_day": ta / 10.0}
        small = [k for k in ("in", "out", "a_day") if not shown[k] and true[k] > 0]
        if small:
            row["small"] = small
        rows.append((ta, true["a_day"], row))
    rows.sort(key=lambda x: (-x[0], -x[1], str(x[2]["route_id"])))
    rows = [x[2] for x in rows]
    tin, tout, tday = (sum(int(round(r[k] * 10)) for r in rows) for k in ("in", "out", "a_day"))
    return rows, tin / 10.0, tout / 10.0, tday / 10.0


def _answer(kind, geometry, month, c, enter_km=None):
    pv = counting.per_visit()
    out = {"kind": kind, "month": int(month) if month else None, "counting": counting.words_for(pv)}
    pas = traffic_limits.passing(geometry, drawn=c["drawn"], legs=c["legs"], enter_km=enter_km)
    if not month:
        out.update({"routes": [{"route_id": rid} for rid in sorted(pas)], "in": None, "out": None, "a_day": None})
        return out
    fig = traffic_limits.through(geometry, int(month), ctx=c, enter_km=enter_km, pas=pas)
    rows, t_in, t_out, t_day = _rows(fig, pv)
    # 10 Nov 2026 (road card polish, Q2 / Q3): the routes on this ground with nothing approved that month, by
    # reference — the card reads "1 of 12 routes" and can say the clicked route has no loads
    busy = {r["route_id"] for r in rows}
    out.update({"routes": rows, "in": t_in, "out": t_out, "a_day": t_day,
                "idle": sorted(str(rid) for rid in pas if rid not in busy)})
    return out


def road_at(lon, lat, month=None, r_m=PICK_M_DEFAULT, route=None):
    """The road card's figures: the routes on the road under (lon, lat) and each one's In / Out / A day. `route` = the
    route line the person clicked: where several roads meet under a click, the piece is taken from THAT route's legs
    (any leg's nearest when it has none within reach)."""
    r_m = max(PICK_M_MIN, min(PICK_M_MAX, float(r_m or PICK_M_DEFAULT)))
    c = _ctx()
    hit = None
    if route:
        hit = _nearest([b for b in c["boxes"] if str(b[0]) == str(route)], float(lon), float(lat), r_m)
    if hit is None:
        hit = _nearest(c["boxes"], float(lon), float(lat), r_m)
    if hit is None:
        return {"kind": "road", "month": int(month) if month else None, "piece": None, "routes": [],
                "in": None, "out": None, "a_day": None, "counting": counting.words()}
    _d, pts, i, t = hit
    piece = _piece(pts, i, t)
    out = _answer("road", {"type": "LineString", "coordinates": piece}, month, c)
    out["piece"] = piece
    return out


class BadBox(ValueError):
    pass


def parse_box(text):
    """'w,s,e,n' -> (w, s, e, n) or BadBox with one plain sentence."""
    try:
        w, s, e, n = (float(x) for x in str(text or "").split(","))
    except (TypeError, ValueError):
        raise BadBox("A box is four numbers: west, south, east, north.")
    if not all(math.isfinite(v) for v in (w, s, e, n)) or not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise BadBox("A box is four numbers: west, south, east, north.")
    diag = math.hypot((e - w) * 111.32 * math.cos(math.radians((s + n) / 2)), (n - s) * 110.54)
    if diag > BOX_MAX_KM:
        raise BadBox("Draw a smaller box.")
    return w, s, e, n


def in_box(w, s, e, n, month=None):
    """The area card's figures: every route with a leg that enters the box, counted once."""
    poly = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    out = _answer("area", poly, month, _ctx(), enter_km=BOX_ENTER_KM)
    out["box"] = [w, s, e, n]
    return out
