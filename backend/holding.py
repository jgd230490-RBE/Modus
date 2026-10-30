"""
holding.py — vehicle holding areas (task 3c, 29 Oct 2026; B4 / V1 / CLOCS Standard v5 §4.1b, §5.5a.iv).

A HOLDING AREA is a location of type "Holding area" (role 'holding'): a field or lay-by near the main road where
construction lorries wait and are CALLED FORWARD to a site when there is room for them (TfL / CLOCS CLP Guidance v1.2
p.37: vehicles "wait and/or queue at a suitable location near the site where they can be called to site when
appropriate and at short notice"; the CLP reports "the size of any vehicle holding areas", p.20). It is never where a
route starts or ends. On it:
    holding_spaces   how many lorries it holds (the CLP's size)
    holding_call     how many are called forward at a time for one bay (the Simulation's rule; default DEFAULT_CALL)
    holding_exempt   JSON list of vehicle keys that go straight to the gate; NULL = the concrete mixers (D63, the user:
                     "all vehicles attend the VHA first, except abnormal loads and concrete"). The abnormal loads are not
                     lorry lines and never call off.
A SITE names the holding area its lorries call off through (`locations.holding_id`); one holding area can serve several
sites. A ROUTE can be ticked `routes.skip_holding` (its lorries never call off: the user's Q4, as Sizewell C sends only
its trunk-road lorries through its facility).

WHICH LEG STOPS (stops()): the leg that ARRIVES at a served site — the loaded leg into its destination, the return leg
back to its origin (the empty lorry coming to load) — for a lorry type that is not exempt, on a route not skipped.

THE MARK (mark_leg): nothing is routed again where the holding area already lies on the stored line. After every bake,
and whenever a holding area, a site's choice or a route's tick changes, each stored row of a leg that stops is marked:
    holding_id      the holding area it stops at (NULL = this row does not stop)
    holding_at_km   where along the line, when the holding area's entrance lies within ON_LINE_M of it; NULL = the line
                    does not pass it ("Route again": the next bake with via_holding routes the leg through it)
    holding_tail_hr the stored time from the stop to the gate, shared by distance
The line itself is never changed, so the busy-hour times (hour_times), the collisions, the councils and the diversions
stand. A leg routed THROUGH the holding area (network.leg_request's holding step) costs one more HERE call and one option.

THE CYCLE (cycle_minutes): the holding area's own check minutes (its entrance gate's `safety_minutes`, the FORS / CLOCS /
DVS check many schemes do there; TfL CFB 2021 p.16 "up to 30 minutes extra") are added to the route's cycle like a
gate's, where the lorry calls off. Nothing else moves: the waiting is the Simulation's, never the cycle's (as at gates).

Reads and writes go through db; every SQL literal carries the tenant. Never spells a team slot id.
"""
import json
import math

import conversions
import db
import gates
import network

TYPE = "Holding area"
ROLE = "holding"
#: the holding area's entrance within this of a stored line = the line passes it (a gate access road is 35 m)
ON_LINE_M = 50.0
DEFAULT_CALL = 2
MAX_SPACES = 500
MAX_CALL = 50
R_EARTH = 6371008.8
STEP_PREFIX = "hold:"

#: the screens' states for a route (holding.summary): what its lorries do at the holding area
STATES = ("calls", "route_again", "skip", "exempt", "not_routed")


# --------------------------------------------------------------------------- what is a holding area
def is_holding(loc):
    return network.canonical_loc_type((loc or {}).get("loc_type")) == TYPE


def default_exempt(factors=None):
    """The vehicle keys exempt by default: the concrete mixers (D63) — any key or label with 'mixer' in it."""
    factors = factors or conversions.load_factors()
    out = []
    for key in (factors.get("vehicles") or {}):
        if key == "_default":
            continue
        if "mixer" in key.lower() or "mixer" in conversions.vehicle_label(factors, key).lower():
            out.append(key)
    return out


def exempt_for(loc, factors=None):
    """The vehicle keys that go straight to the gate at this holding area: as typed, else default_exempt()."""
    raw = (loc or {}).get("holding_exempt")
    if raw in (None, ""):
        return default_exempt(factors)
    try:
        v = json.loads(raw) if isinstance(raw, str) else list(raw)
        return [str(x) for x in v]
    except Exception:
        return default_exempt(factors)


def spaces_of(loc):
    v = (loc or {}).get("holding_spaces")
    return None if v in (None, "") else int(v)


def call_of(loc):
    v = (loc or {}).get("holding_call")
    return DEFAULT_CALL if v in (None, "") else int(v)


def _skip(route):
    return gates._truthy((route or {}).get("skip_holding"))


# --------------------------------------------------------------------------- validation
def problem_fields(spaces=None, call=None, exempt=None, factors=None, given=None):
    """None, or the problem in words, for the holding area's own fields (only those in `given` are looked at)."""
    given = set(given or ())
    if "holding_spaces" in given and spaces not in (None, ""):
        try:
            s = int(spaces)
        except (TypeError, ValueError):
            return "the spaces must be a whole number of lorries"
        if s < 1 or s > MAX_SPACES:
            return f"the spaces must be between 1 and {MAX_SPACES} lorries"
    if "holding_call" in given and call not in (None, ""):
        try:
            c = int(call)
        except (TypeError, ValueError):
            return "called forward at a time must be a whole number"
        if c < 1 or c > MAX_CALL:
            return f"called forward at a time must be between 1 and {MAX_CALL}"
    if "holding_exempt" in given and exempt is not None:
        if not isinstance(exempt, (list, tuple)):
            return "the vehicles that go straight to the gate must be a list"
        known = set((factors or conversions.load_factors()).get("vehicles") or {})
        for k in exempt:
            if str(k) not in known:
                return f"{k} is not one of this scheme's vehicles"
    return None


def problem_calls_through(location_id, holding_id, locations=None):
    """None, or why `location_id` cannot call off through `holding_id`."""
    if holding_id in (None, ""):
        return None
    locs = locations or {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?",
                                                       (db.current_tenant(),))}
    me = locs.get(location_id)
    h = locs.get(holding_id)
    if me is not None and is_holding(me):
        return "a holding area does not call off through another"
    if not h:
        return "that holding area is not one of this scheme's locations"
    if not is_holding(h):
        return f"{h.get('name') or holding_id} is not a holding area"
    if holding_id == location_id:
        return "a site cannot call off through itself"
    return None


# --------------------------------------------------------------------------- writes
def set_holding(location_id, given, spaces=None, call=None, exempt=None, factors=None):
    """The holding area's own three fields; only those in `given` are written; a blank clears (spaces, call) or goes
    back to the default (exempt). Refused on a location that is not a holding area."""
    given = set(given or ())
    network._ensure_location_columns()
    cur = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), location_id))
    if not cur:
        return {"error": "not found"}
    cur = cur[0]
    if not is_holding(cur):
        return {"error": f"{cur.get('name') or location_id} is not a holding area"}
    p = problem_fields(spaces, call, exempt, factors, given)
    if p:
        return {"error": p}
    new_spaces = (None if spaces in (None, "") else int(spaces)) if "holding_spaces" in given else cur.get("holding_spaces")
    new_call = (None if call in (None, "") else int(call)) if "holding_call" in given else cur.get("holding_call")
    if "holding_exempt" in given:
        new_exempt = None if exempt is None else json.dumps([str(x) for x in exempt])
    else:
        new_exempt = cur.get("holding_exempt")
    db.execute("UPDATE locations SET holding_spaces = ?, holding_call = ?, holding_exempt = ? "
               "WHERE tenant_id = ? AND id = ?", (new_spaces, new_call, new_exempt, db.current_tenant(), location_id))
    if "holding_exempt" in given:
        mark_all()                      # which lorries stop changed
    return {"ok": True, "id": location_id, "holding_spaces": new_spaces, "holding_call": new_call,
            "holding_exempt": exempt_for({"holding_exempt": new_exempt}, factors)}


def set_calls_through(location_id, holding_id):
    """A site's 'Lorries call off through' (None clears). Marks the site's routes afterwards."""
    network._ensure_location_columns()
    p = problem_calls_through(location_id, holding_id)
    if p:
        return {"error": p}
    if not db.query("SELECT id FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), location_id)):
        return {"error": "not found"}
    v = None if holding_id in (None, "") else str(holding_id)
    db.execute("UPDATE locations SET holding_id = ? WHERE tenant_id = ? AND id = ?",
               (v, db.current_tenant(), location_id))
    for rid in network.routes_touching(location_id):
        mark_route(rid)
    return {"ok": True, "id": location_id, "holding_id": v}


def on_location_deleted(location_id):
    """A deleted holding area: the sites that called off through it no longer do, and no stored row stops there."""
    db.execute("UPDATE locations SET holding_id = NULL WHERE tenant_id = ? AND holding_id = ?",
               (db.current_tenant(), location_id))
    db.execute("UPDATE route_geometry SET holding_id = NULL, holding_at_km = NULL, holding_tail_hr = NULL "
               "WHERE tenant_id = ? AND holding_id = ?", (db.current_tenant(), location_id))


# --------------------------------------------------------------------------- the context one read or one batch uses
def context(factors=None):
    """Everything stops() and mark_leg() need, read once: the locations, the routes, the holding areas with their
    entrance point (gates.resolve: the typed entry gate, else the marker) and their effective exemptions."""
    factors = factors or conversions.load_factors()
    tenant = db.current_tenant()
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (tenant,))}
    routes = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (tenant,))}
    try:
        gbl = gates.gates_by_location()
    except Exception:
        gbl = {}
    hold = {}
    for l in locs.values():
        if not is_holding(l):
            continue
        try:
            g = gates.resolve(l, "entry", None, gates=gbl.get(l["id"]))
        except Exception:
            g = {"lat": l.get("lat"), "lon": l.get("lon"), "gate_id": None, "safety_minutes": 0.0, "source": "node"}
        hold[l["id"]] = dict(l, gate=g, spaces=spaces_of(l), call=call_of(l), exempt=exempt_for(l, factors),
                             served=[s["id"] for s in locs.values() if s.get("holding_id") == l["id"]])
    return {"factors": factors, "locations": locs, "routes": routes, "holding": hold, "gates_by_loc": gbl}


def arrival_end(route, leg):
    """The location id a leg ARRIVES at: the destination on the loaded leg, the origin on the return."""
    return route.get("dest_id") if leg == "loaded" else route.get("origin_id")


def stops(route, leg, ctx, profile=None):
    """The holding area this leg stops at (the context's row, with `gate`), or None."""
    if not route or _skip(route):
        return None
    end = ctx["locations"].get(arrival_end(route, leg))
    if not end or not end.get("holding_id"):
        return None
    h = ctx["holding"].get(end["holding_id"])
    if not h or not h.get("gate") or h["gate"].get("lat") is None:
        return None
    if profile is not None and profile in h["exempt"]:
        return None
    return h


# --------------------------------------------------------------------------- geometry
def _xy(p, lat0):
    return (p[0] * math.pi / 180 * R_EARTH * math.cos(lat0), p[1] * math.pi / 180 * R_EARTH)


def nearest_on_line(coords, lon, lat):
    """(metres from the point to the line, metres along the line at the nearest point, the line's length in metres),
    or None for fewer than two points. Flat-earth maths at the point's latitude (good to centimetres here)."""
    if not coords or len(coords) < 2:
        return None
    lat0 = float(lat) * math.pi / 180
    P = _xy((float(lon), float(lat)), lat0)
    pts = [_xy((float(c[0]), float(c[1])), lat0) for c in coords]
    best, cum = None, 0.0
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        L = math.sqrt(L2)
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((P[0] - a[0]) * dx + (P[1] - a[1]) * dy) / L2))
        q = (a[0] + u * dx, a[1] + u * dy)
        d = math.hypot(P[0] - q[0], P[1] - q[1])
        if best is None or d < best[0]:
            best = (d, cum + u * L)
        cum += L
    return best[0], best[1], cum


def mark_for(row, h):
    """The three columns one stored row gets for holding area `h` (None = the row has no line)."""
    if not row.get("geometry"):
        return (h["id"], None, None)
    try:
        coords = json.loads(row["geometry"])
    except Exception:
        coords = None
    near = nearest_on_line(coords, h["gate"]["lon"], h["gate"]["lat"]) if coords else None
    if near and near[2] > 0 and near[0] <= ON_LINE_M:
        dur = row.get("duration_hr")
        tail = (float(dur) * (1.0 - near[1] / near[2])) if dur not in (None, "") else None
        return (h["id"], round(near[1] / 1000.0, 3), (round(tail, 4) if tail is not None else None))
    return (h["id"], None, None)


# --------------------------------------------------------------------------- the mark
def mark_leg(route_id, profile, leg, ctx=None):
    """Mark every stored row of one (route, lorry type, leg): {marked, off_line, cleared}."""
    ctx = ctx or context()
    tenant = db.current_tenant()
    route = ctx["routes"].get(route_id)
    h = stops(route, leg, ctx, profile) if route else None
    rows = db.query("SELECT alt_index, geometry, duration_hr, holding_id, holding_at_km, holding_tail_hr "
                    "FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? AND leg = ?",
                    (tenant, route_id, profile, leg))
    out = {"marked": 0, "off_line": 0, "cleared": 0}
    for row in rows:
        new = mark_for(row, h) if h is not None else (None, None, None)
        old = (row.get("holding_id"), row.get("holding_at_km"), row.get("holding_tail_hr"))
        if old != new:
            db.execute("UPDATE route_geometry SET holding_id = ?, holding_at_km = ?, holding_tail_hr = ? "
                       "WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? AND leg = ? AND alt_index = ?",
                       (new[0], new[1], new[2], tenant, route_id, profile, leg, row["alt_index"]))
        if new[0] is None:
            out["cleared"] += 1 if old[0] is not None else 0
        elif new[1] is None:
            out["off_line"] += 1
        else:
            out["marked"] += 1
    return out


def mark_route(route_id, ctx=None):
    ctx = ctx or context()
    pairs = db.query("SELECT DISTINCT vehicle_profile, leg FROM route_geometry WHERE tenant_id = ? AND route_id = ?",
                     (db.current_tenant(), route_id))
    out = {"marked": 0, "off_line": 0, "cleared": 0}
    for p in pairs:
        r = mark_leg(route_id, p["vehicle_profile"], p["leg"], ctx)
        for k in out:
            out[k] += r[k]
    return out


def mark_all(ctx=None):
    """Every stored row of every route. Cheap (pure geometry over the stored lines); nothing when the scheme has no
    holding area and no row carries a mark."""
    ctx = ctx or context()
    tenant = db.current_tenant()
    if not ctx["holding"]:
        n = db.query("SELECT COUNT(*) AS n FROM route_geometry WHERE tenant_id = ? AND holding_id IS NOT NULL", (tenant,))
        if not n or not n[0]["n"]:
            return {"marked": 0, "off_line": 0, "cleared": 0, "routes": 0}
    out = {"marked": 0, "off_line": 0, "cleared": 0, "routes": 0}
    for rid in sorted(ctx["routes"]):
        r = mark_route(rid, ctx)
        out["routes"] += 1
        for k in ("marked", "off_line", "cleared"):
            out[k] += r[k]
    return out


def mark_quietly(why=""):
    try:
        return mark_all()
    except Exception as e:                       # a cold database without the columns yet: never a failed bake
        print(f"holding: not marked after {why}: {e}")
        return None


# --------------------------------------------------------------------------- the bake through it
def step_for(h):
    """The holding area's entrance as one leg step for haul.route_with_haul (a stop of no length, spliced): the leg is
    routed to it and from it, one option. `zone_id` carries STEP_PREFIX + the location id, which no zone ever has."""
    g = h["gate"]
    pt = [float(g["lon"]), float(g["lat"])]
    return {"zone_id": STEP_PREFIX + h["id"], "name": h.get("name") or h["id"], "mode": "splice", "speed_kph": None,
            "line": [pt, list(pt)], "length_km": 0.0, "entry": (pt[1], pt[0]), "exit": (pt[1], pt[0]),
            "reversed": False, "holding_id": h["id"]}


def with_step(steps, h):
    """The leg's steps with the holding area's stop before the arrival gate's access road (else last)."""
    s = list(steps or [])
    st = step_for(h)
    if s and s[-1].get("gate_role") == "entry":
        return s[:-1] + [st, s[-1]]
    return s + [st]


# --------------------------------------------------------------------------- the cycle
def cycle_minutes(route, origin, dest, profile, gates_by_loc=None, factors=None):
    """The holding area's check minutes this lorry pays once a cycle at each end where it calls off: 0.0, and no
    read at all, unless an end's row names a holding area (`holding_id` travels on the location rows every caller
    already holds). Called for every row of route_analysis, so it stays this cheap."""
    if not route or _skip(route):
        return 0.0
    hids = {"loaded": (dest or {}).get("holding_id"), "return": (origin or {}).get("holding_id")}
    if not any(hids.values()):
        return 0.0
    out, seen = 0.0, {}
    for leg, hid in hids.items():
        if not hid:
            continue
        if hid not in seen:
            rows = db.query("SELECT * FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), hid))
            h = rows[0] if (rows and is_holding(rows[0])) else None
            if h is not None:
                try:
                    g = gates.resolve(h, "entry", None, gates=(gates_by_loc or {}).get(hid))
                except Exception:
                    g = None
                h = dict(h, gate=g, exempt=exempt_for(h, factors))
            seen[hid] = h
        h = seen[hid]
        if h is None or profile in h["exempt"]:
            continue
        out += float(((h.get("gate") or {}).get("safety_minutes")) or 0.0)
    return out


# --------------------------------------------------------------------------- the read
def route_state(route, ctx, rows_by_profile_leg):
    """One word for a route: 'calls' (a stored line stops), 'route_again' (a leg that should stop does not pass the
    holding area), 'skip', 'exempt' (only exempt lorry types run it), 'not_routed', or None (no holding area at
    either end)."""
    ends = [ctx["locations"].get(arrival_end(route, leg)) for leg in ("loaded", "return")]
    if not any(e and e.get("holding_id") and e["holding_id"] in ctx["holding"] for e in ends):
        return None
    if _skip(route):
        return "skip"
    any_stop, on, off = False, 0, 0
    for (profile, leg), rows in rows_by_profile_leg.items():
        h = stops(route, leg, ctx, profile)
        if h is None:
            continue
        any_stop = True
        for r in rows:
            if r.get("alt_index") != 0:          # an alternative off the line matters only once it is promoted
                continue
            if r.get("holding_at_km") is not None:
                on += 1
            elif r.get("geometry_present"):
                off += 1
    if not any_stop:
        # a lorry type that stops exists in the scheme but none of this route's rows carries it, or all are exempt
        lorry_types = {p for (p, _l) in rows_by_profile_leg}
        if lorry_types and all(all(p in h["exempt"] for h in ctx["holding"].values()) for p in lorry_types):
            return "exempt"
        return "not_routed" if not lorry_types else "exempt"
    if off:
        return "route_again"
    return "calls" if on else "not_routed"


def summary(factors=None):
    """GET /api/holding: every holding area with its sites, and every route's state (the Routes page, the forms)."""
    ctx = context(factors)
    tenant = db.current_tenant()
    rows = db.query("SELECT route_id, vehicle_profile, leg, alt_index, holding_id, holding_at_km, holding_tail_hr, "
                    "(geometry IS NOT NULL) AS geometry_present FROM route_geometry WHERE tenant_id = ?", (tenant,))
    by_route = {}
    for r in rows:
        by_route.setdefault(r["route_id"], {}).setdefault((r["vehicle_profile"], r["leg"]), []).append(
            {"alt_index": r["alt_index"], "holding_id": r["holding_id"], "holding_at_km": r["holding_at_km"],
             "holding_tail_hr": r["holding_tail_hr"], "geometry_present": gates._truthy(r["geometry_present"])})
    areas = []
    for hid in sorted(ctx["holding"]):
        h = ctx["holding"][hid]
        areas.append({"id": hid, "name": h.get("name"), "lat": h.get("lat"), "lon": h.get("lon"),
                      "spaces": h["spaces"], "call": h["call"], "exempt": h["exempt"],
                      "exempt_labels": [conversions.vehicle_label(ctx["factors"], k) for k in h["exempt"]],
                      "exempt_typed": (h.get("holding_exempt") not in (None, "")),
                      "gate": {"gate_id": h["gate"].get("gate_id"), "gate_name": h["gate"].get("gate_name"),
                               "lat": h["gate"].get("lat"), "lon": h["gate"].get("lon"),
                               "check_minutes": h["gate"].get("safety_minutes"), "source": h["gate"].get("source")},
                      "served": [{"id": s, "name": (ctx["locations"].get(s) or {}).get("name")} for s in h["served"]]})
    routes = []
    for rid in sorted(ctx["routes"]):
        route = ctx["routes"][rid]
        state = route_state(route, ctx, by_route.get(rid, {}))
        if state is None:
            continue
        ends = {}
        for leg in ("loaded", "return"):
            e = ctx["locations"].get(arrival_end(route, leg))
            if e and e.get("holding_id") in ctx["holding"]:
                ends[leg] = e["holding_id"]
        primary = [(k, v) for k, v in by_route.get(rid, {}).items()]
        marked = [dict(r, profile=k[0], leg=k[1]) for k, rs in primary for r in rs if r["alt_index"] == 0 and r["holding_id"]]
        routes.append({"route_id": rid, "origin_id": route.get("origin_id"), "dest_id": route.get("dest_id"),
                       "skip": _skip(route), "state": state, "stops": ends,
                       "legs": [{"profile": m["profile"], "profile_label": conversions.vehicle_label(ctx["factors"], m["profile"]),
                                 "leg": m["leg"], "holding_id": m["holding_id"], "at_km": m["holding_at_km"],
                                 "tail_hr": m["holding_tail_hr"], "on_line": m["holding_at_km"] is not None}
                                for m in marked]})
    return {"holding_areas": areas, "routes": routes, "default_exempt": default_exempt(ctx["factors"]),
            "default_call": DEFAULT_CALL, "on_line_m": ON_LINE_M}
