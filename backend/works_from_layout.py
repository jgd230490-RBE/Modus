"""
works_from_layout.py — task 2.1-12 (8 Nov 2026, the mockup John approved: notes works-from-layout-mockup-1108, Q1–Q8 as
recommended): a site layout's outline becomes a WORKS AREA zone, so nobody draws the site twice.

The works area stays an ordinary zone (public, dated, can steer routing); the layout stays staff only. This module only
works out shapes and remembers where a zone's outline came from. The zone write itself (and what it re-routes) is
main.py's create_zone / update_zone, so a works area made here behaves exactly like one drawn on Zones.

* Q1 — the outline: "all" = the convex outline of every thing on the phase, MARGIN_M out (every line, area, symbol and
  word); "boundary" = the largest area drawn with the Site boundary style (offered only when the phase has one).
* Q5 — a one-off copy: the zone remembers the phase and the phase's version (zones.from_phase_id / from_phase_version).
  The phase row reads "layout changed since" when the phase was saved again, and "changed on Zones" when the zone's
  outline was edited on Zones (that edit clears from_phase_version). Nothing changes by itself.
* Q7 — admins only (the zone write is an admin write, as on Zones).
"""
import calendar
import json
import math

import db

#: how far outside the drawn things the "all" outline runs, metres (a buffer, not a measured figure)
MARGIN_M = 10.0
#: the circle round each hull corner is drawn with this many points (the buffer's rounded corners)
CORNER_STEPS = 16
BOUNDARY_STYLE = "boundary"


def _coords(c, out):
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        out.append((float(c[0]), float(c[1])))
    elif isinstance(c, (list, tuple)):
        for x in c:
            _coords(x, out)
    return out


def _hull(pts):
    """Convex hull (Andrew's monotone chain), anticlockwise, not closed."""
    P = sorted(set(pts))
    if len(P) < 3:
        return P

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _frame(pts):
    """A local metre frame about the points' middle: (to_m, to_ll)."""
    lat0 = sum(p[1] for p in pts) / len(pts)
    lon0 = sum(p[0] for p in pts) / len(pts)
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0
    return (lambda p: ((p[0] - lon0) * kx, (p[1] - lat0) * ky)), (lambda q: (lon0 + q[0] / kx, lat0 + q[1] / ky))


def ring_area_m2(ring):
    """Area of a [lon, lat] ring in square metres (a local flat frame; fine at a site's size)."""
    if not ring or len(ring) < 3:
        return 0.0
    to_m, _ = _frame(ring)
    r = [to_m(p) for p in ring]
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2.0


def outline_all(things, margin_m=MARGIN_M):
    """The convex outline round every coordinate of every thing, margin_m out (the hull of a circle round each corner:
    the buffer of a convex shape, its corners drawn with CORNER_STEPS points whose edges sit margin_m out). A GeoJSON Polygon, closed, 7 dp; None
    when the phase has nothing drawn."""
    pts = []
    for f in things or []:
        g = (f or {}).get("geometry") or {}
        _coords(g.get("coordinates"), pts)
    if not pts:
        return None
    to_m, to_ll = _frame(pts)
    core = _hull([to_m(p) for p in pts])
    grown = []
    r = margin_m / math.cos(math.pi / CORNER_STEPS)      # the corner polygon's edges, not its points, sit margin_m out
    for (x, y) in core:
        for i in range(CORNER_STEPS):
            a = 2 * math.pi * i / CORNER_STEPS
            grown.append((x + r * math.cos(a), y + r * math.sin(a)))
    ring = [to_ll(q) for q in _hull(grown)]
    ring = [[round(p[0], 7), round(p[1], 7)] for p in ring]
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def outline_boundary(things):
    """The largest Site boundary area's outer ring (its holes dropped: a works area is the whole site). None if none."""
    best, best_a = None, -1.0
    for f in things or []:
        p = (f or {}).get("properties") or {}
        g = (f or {}).get("geometry") or {}
        if p.get("style") != BOUNDARY_STYLE or g.get("type") != "Polygon" or not g.get("coordinates"):
            continue
        ring = [[round(float(c[0]), 7), round(float(c[1]), 7)] for c in g["coordinates"][0]]
        a = ring_area_m2(ring)
        if a > best_a:
            best, best_a = ring, a
    if not best:
        return None
    if best[0] != best[-1]:
        best.append(list(best[0]))
    return {"type": "Polygon", "coordinates": [best]}


def _phase(phase_id):
    rows = db.query("SELECT p.*, l.location_id FROM site_layout_phases p JOIN site_layouts l "
                    "ON l.tenant_id = p.tenant_id AND l.id = p.layout_id WHERE p.tenant_id = ? AND p.id = ?",
                    (db.current_tenant(), phase_id))
    return rows[0] if rows else None


def _things(ph):
    try:
        fc = json.loads(ph.get("features_json") or "{}")
    except Exception:
        fc = {}
    return fc.get("features") if isinstance(fc, dict) and isinstance(fc.get("features"), list) else []


def _bbox(geom):
    pts = _coords((geom or {}).get("coordinates"), [])
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _overlap(a, b):
    return bool(a and b and a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3])


def month_dates(month_from, month_to):
    """Q3: a phase's months as zone dates — the 1st of From, the last day of To; an open end stays open."""
    s = f"{month_from}-01" if month_from else None
    e = None
    if month_to:
        y, m = int(month_to[:4]), int(month_to[5:7])
        e = f"{month_to}-{calendar.monthrange(y, m)[1]:02d}"
    return s, e


def plan(phase_id):
    """What the panel shows: both outlines (boundary None when there is no Site boundary area), their hectares, the
    suggested name and dates, the works areas whose outline overlaps (Q6: offered first, the one already made from this
    phase before any other), and the works area this phase made before. None when the phase does not exist."""
    ph = _phase(phase_id)
    if not ph:
        return None
    things = _things(ph)
    loc = db.query("SELECT name FROM locations WHERE tenant_id = ? AND id = ?",
                   (db.current_tenant(), ph["location_id"]))
    site = (loc[0].get("name") if loc else None) or ph["location_id"]
    a_all, a_bnd = outline_all(things), outline_boundary(things)
    shape = a_bnd or a_all
    bb = _bbox(shape)
    s, e = month_dates(ph.get("month_from"), ph.get("month_to"))
    near = []
    for z in db.query("SELECT id, name, kind, geometry, starts_on, ends_on, affects_routing, active, from_phase_id "
                      "FROM zones WHERE tenant_id = ? AND kind = 'works' ORDER BY id", (db.current_tenant(),)):
        try:
            g = json.loads(z.get("geometry") or "null")
        except Exception:
            g = None
        mine = z.get("from_phase_id") == phase_id
        if mine or _overlap(bb, _bbox(g)):
            near.append({"id": z["id"], "name": z.get("name"), "starts_on": z.get("starts_on"),
                         "ends_on": z.get("ends_on"), "affects_routing": bool(z.get("affects_routing"))
                         and z.get("affects_routing") not in ("0", "false"), "from_this_phase": mine})
    near.sort(key=lambda z: (not z["from_this_phase"], z["id"]))
    return {
        "phase_id": phase_id, "phase_name": ph.get("name"), "location_id": ph["location_id"], "site": site,
        "version": int(ph.get("version") or 1),
        "outlines": {"all": a_all, "boundary": a_bnd},
        "hectares": {"all": round(ring_area_m2(a_all["coordinates"][0]) / 1e4, 1) if a_all else None,
                     "boundary": round(ring_area_m2(a_bnd["coordinates"][0]) / 1e4, 1) if a_bnd else None},
        "default_outline": "boundary" if a_bnd else "all",
        "name": f"{site} works area", "starts_on": s, "ends_on": e,
        "works_areas": near,
    }


def set_source(zone_id, phase_id, version):
    """Remember the phase (and its version) a zone's outline was copied from."""
    db.execute("UPDATE zones SET from_phase_id = ?, from_phase_version = ? WHERE tenant_id = ? AND id = ?",
               (phase_id, int(version), db.current_tenant(), zone_id))


def zone_outline_edited(zone_id):
    """A geometry edit made on Zones: the zone keeps its phase but no longer matches any version of it."""
    db.execute("UPDATE zones SET from_phase_version = NULL WHERE tenant_id = ? AND id = ? AND from_phase_id IS NOT NULL",
               (db.current_tenant(), zone_id))


def by_phase():
    """{phase id: {zone_id, name, state}} for the layout card — state 'same' | 'layout_changed' | 'zone_changed'.
    One zone per phase (the lowest id when more than one was made from it)."""
    tenant = db.current_tenant()
    vers = {r["id"]: int(r.get("version") or 1) for r in
            db.query("SELECT id, version FROM site_layout_phases WHERE tenant_id = ?", (tenant,))}
    out = {}
    for z in db.query("SELECT id, name, from_phase_id, from_phase_version FROM zones WHERE tenant_id = ? "
                      "AND from_phase_id IS NOT NULL ORDER BY id", (tenant,)):
        pid = z["from_phase_id"]
        if pid not in vers or pid in out:
            continue
        v = z.get("from_phase_version")
        state = "zone_changed" if v in (None, "") else ("same" if int(v) == vers[pid] else "layout_changed")
        out[pid] = {"zone_id": z["id"], "name": z.get("name"), "state": state}
    return out


def sources():
    """{zone id: {location_id, site}} for the Zones table's "From the <site> site layout" line (zones whose phase still
    exists)."""
    tenant = db.current_tenant()
    rows = db.query("SELECT z.id AS zone_id, l.location_id, loc.name AS site FROM zones z "
                    "JOIN site_layout_phases p ON p.tenant_id = z.tenant_id AND p.id = z.from_phase_id "
                    "JOIN site_layouts l ON l.tenant_id = p.tenant_id AND l.id = p.layout_id "
                    "LEFT JOIN locations loc ON loc.tenant_id = l.tenant_id AND loc.id = l.location_id "
                    "WHERE z.tenant_id = ?", (tenant,))
    return {r["zone_id"]: {"location_id": r["location_id"], "site": r.get("site") or r["location_id"]} for r in rows}
