"""
Distance along a line: ONE set of functions for the whole server (27 Nov 2026, claude/route-pieces).

Until this branch the functions lived in collisions.py as private names (`_project`, `_chainage`) and the Route analysis
(route_analysis_doc: its limits table and its community places), the collision evidence (its places, collisions and
stretches), the traffic counts and the busy-hours offer all called them there. They moved here word for word, so every
caller measures the same way; collisions.py keeps its old names as aliases of these, so nothing that called them moves.
A new reader that needs "metres from A" or "metres off the line" calls these and never writes its own walk.

Every function takes a projection `index`: anything with `_xy((lon, lat)) -> (x, y)` in metres on a local
equirectangular plane (collisions.RouteIndex, or Proj below). Metres along a line are measured on that projection, from
the line's FIRST vertex.
"""
import math


class Proj:
    """The smallest projection the functions here need: metres a degree at one latitude (collisions.RouteIndex's own
    constants, so a distance read through either is the same at the same latitude)."""

    def __init__(self, lat0=52.0):
        self.lat0 = float(lat0)
        self.kx, self.ky = 111320.0 * math.cos(math.radians(self.lat0)), 110574.0

    @classmethod
    def around(cls, lines):
        """A projection centred on the mean latitude of every vertex of `lines` (as RouteIndex centres its own)."""
        pts = [c for l in (lines or []) for c in (l or [])]
        return cls((sum(p[1] for p in pts) / len(pts)) if pts else 52.0)

    def _xy(self, c):
        return (c[0] * self.kx, c[1] * self.ky)

    def metres(self, a, b):
        return math.hypot((a[0] - b[0]) * self.kx, (a[1] - b[1]) * self.ky)


def project(index, line, p):
    """(metres from `line`, metres along it from its first vertex) for the point on `line` nearest `p`."""
    best, at, run = None, 0.0, 0.0
    P = index._xy(p)
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        dx, dy = B[0] - A[0], B[1] - A[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((P[0] - A[0]) * dx + (P[1] - A[1]) * dy) / L2))
        d = math.hypot(P[0] - (A[0] + t * dx), P[1] - (A[1] + t * dy))
        if best is None or d < best:
            best, at = d, run + t * math.sqrt(L2)
        run += math.sqrt(L2)
    return (best if best is not None else float("inf")), at


def chainage(index, line, p):
    """Metres along `line` (from its first vertex) to the point on it nearest `p`."""
    return project(index, line, p)[1]


def line_length_m(index, line):
    """The length of `line` in metres on the index's projection (the one project() measures along)."""
    return sum(math.hypot(*(B - A for A, B in zip(index._xy(a), index._xy(b)))) for a, b in zip(line, line[1:]))


def vertex_chainage(index, line):
    """[metres along `line` at each of its vertices] (the first is 0): the walk project() makes, kept per vertex, so a
    reader that needs the chainage of the line's OWN points does not project each one back onto the line."""
    out, run = [], 0.0
    for i, c in enumerate(line or []):
        if i:
            A, B = index._xy(line[i - 1]), index._xy(c)
            run += math.hypot(B[0] - A[0], B[1] - A[1])
        out.append(run)
    return out


class Grid:
    """A line's segments filed in a grid on one projection, each with its metres along the line, for the questions
    project() answers when only points NEAR the line matter: "how far is this point from the line" up to `reach`
    (beyond it: infinity) and "where along the line is it". Within `reach` nearest() gives what project() gives (the
    same nearest segment, the first in line order on a tie, the same metres): test_route_pieces asserts it. `p` is a
    point already on the projection (index._xy)."""
    CELL = 200.0

    def __init__(self, index, line, reach):
        self.reach = float(reach)
        self.g = {}
        P = [index._xy(c) for c in line]
        run, c = 0.0, self.CELL
        for a, b in zip(P, P[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            item = (a, b, run, L)
            run += L
            for gx in range(int((min(a[0], b[0]) - reach) // c), int((max(a[0], b[0]) + reach) // c) + 1):
                for gy in range(int((min(a[1], b[1]) - reach) // c), int((max(a[1], b[1]) + reach) // c) + 1):
                    self.g.setdefault((gx, gy), []).append(item)
        self.length = run

    def _each(self, p):
        for a, b, m0, L in self.g.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            yield math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)), m0 + t * L, m0

    def dist(self, p):
        best = min((d for d, _m, _s in self._each(p)), default=float("inf"))
        return best if best <= self.reach else float("inf")

    def nearest(self, p):
        """(metres from the line, metres along it) of the nearest point on the line when it is within `reach`, else
        (infinity, None)."""
        best = None
        for d, m, s in self._each(p):
            if best is None or d < best[0] or (d == best[0] and s < best[2]):
                best = (d, m, s)
        if best is None or best[0] > self.reach:
            return float("inf"), None
        return best[0], best[1]

    def along_near(self, p, near):
        """[metres along the line] of every place on it within `near` of p (one a segment)."""
        return [m for d, m, _s in self._each(p) if d <= near]


def point_at(index, line, metres):
    """The (lon, lat) `metres` along `line` from its first vertex (on the index's projection)."""
    run = 0.0
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        L = math.hypot(B[0] - A[0], B[1] - A[1])
        if run + L >= metres and L > 0:
            t = (metres - run) / L
            return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
        run += L
    return list(line[-1]) if line else None


def line_between(index, line, a_m, b_m):
    """The vertices of `line` between a_m and b_m metres from its start, with the two end points."""
    out, run = [point_at(index, line, a_m)], 0.0
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        run += math.hypot(B[0] - A[0], B[1] - A[1])
        if a_m < run < b_m:
            out.append(list(b))
    out.append(point_at(index, line, b_m))
    return [p for p in out if p]
