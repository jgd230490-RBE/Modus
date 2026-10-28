"""
sim_site.py — what happens INSIDE a site in the haulage simulation (v2, 28 Oct 2026, task 0e).

Until v2 a lorry vanished once its gate had checked it in. Now, at a site with AREAS (site_areas.py) or internal
ROADS (haul-road zones with `location_id`, zones.internal_roads), each checked-in lorry runs a CHAIN OF STATIONS:

    gate in (the gate's own queue, sim.queue) -> drive -> its AREA (bays, service minutes) -> drive -> the WHEEL
    WASH (if the site has one) -> drive -> gate out (counted, never queued)

Every station after the gate is a first-come-first-served queue with `bays` servers: a lorry starts when it has
arrived and a bay is free, and leaves `service` minutes later. The drive between stations is the shortest path by
time over the site's drawn roads (each at its own speed, else the site speed), a gate or area snapping to its
nearest road within SNAP_M; with no roads, straight lines at the site speed. A site with no speed typed drives at
DEFAULT_SITE_KPH and the reply says so.

Per station the figures the gate has (sim.gate_figures' rule): first wait, the bottleneck (the first wait LONGER
THAN the station's service — D85 applied to each), most waiting at once, minutes lost, longest wait, busiest hour,
and three words: "Bays enough" / "Queue likely" / "Over capacity". Per site: lorries in and out, the average and
longest time on site, the lines that found no area for their material (named, never silently dropped: their
lorries leave from the gate as before).

Room for the vehicle holding areas (task 3c): a station BEFORE the gate is one more entry in the chain a
`chain_for()` builds; nothing here assumes the chain starts at the gate.

Pure functions; the reads are in sim.day(). Never spells a team slot id.
"""
import heapq
import math

import gates
import site_areas

#: a site with no speed typed drives at this on its roads (5 mph), and says so
DEFAULT_SITE_KPH = 8.0
#: two road ends within this many metres are one junction
JOIN_M = 5.0
#: a gate or an area within this of a drawn road joins it there; further away, a straight line
SNAP_M = 60.0
#: the exit gate crosses with no service; a lorry waiting less than this has not waited
WAIT_EPS = 0.01
STATION_WORDS = {"ok": "Bays enough", "amber": "Queue likely", "red": "Over capacity"}
R_EARTH = 6371008.8


# --------------------------------------------------------------------------- geometry
def _xy(p, lat0):
    return (p[0] * math.pi / 180 * R_EARTH * math.cos(lat0), p[1] * math.pi / 180 * R_EARTH)


def _ll(x, y, lat0):
    return [round(x / (math.pi / 180 * R_EARTH * math.cos(lat0)), 6), round(y / (math.pi / 180 * R_EARTH), 6)]


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _proj(p, a, b):
    """(the nearest point of segment a-b to p, its distance, the parameter u)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    q = (a[0] + u * dx, a[1] + u * dy)
    return q, _d(p, q), u


class Graph:
    """The site's roads as nodes and edges in local metres; every edge carries its speed (metres a minute)."""

    def __init__(self, lat0, site_kph):
        self.lat0 = lat0
        self.site_mpm = site_kph * 1000.0 / 60.0
        self.nodes = {}        # id -> (x, y)
        self.adj = {}          # id -> [(to, len_m, mpm, zone)]
        self.n = 0

    def node(self, xy, join=0.0):
        if join > 0:
            for k, p in self.nodes.items():
                if _d(p, xy) <= join:
                    return k
        k = f"n{self.n}"
        self.n += 1
        self.nodes[k] = xy
        self.adj[k] = []
        return k

    def edge(self, a, b, mpm, zone=None):
        L = _d(self.nodes[a], self.nodes[b])
        if a == b:
            return
        self.adj[a].append((b, L, mpm, zone))
        self.adj[b].append((a, L, mpm, zone))

    def path(self, a, b):
        """Dijkstra by time. [(node, len_m, mpm, zone)] from a to b (the first with len 0), or None when apart."""
        if a == b:
            return [(a, 0.0, self.site_mpm, None)]
        best = {a: 0.0}
        prev = {}
        heap = [(0.0, a)]
        done = set()
        while heap:
            t, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u == b:
                break
            for v, L, mpm, zone in self.adj[u]:
                nt = t + (L / mpm if mpm > 0 else 0.0)
                if v not in best or nt < best[v]:
                    best[v] = nt
                    prev[v] = (u, L, mpm, zone)
                    heapq.heappush(heap, (nt, v))
        if b not in best:
            return None
        out = []
        cur = b
        while cur != a:
            u, L, mpm, zone = prev[cur]
            out.append((cur, L, mpm, zone))
            cur = u
        out.append((a, 0.0, self.site_mpm, None))
        out.reverse()
        return out


def build_graph(roads, stations, site_kph, lat0):
    """
    `roads` = [{zone_id, line [[lon, lat], ...], speed_kph}], `stations` = {key: [lon, lat]}. Each road's vertices are
    nodes (ends joined within JOIN_M); each station snaps to its nearest road point within SNAP_M (a node on that
    road, joined by a straight run at the site speed), else stands alone and is joined straight to every other
    station. Returns (graph, {station key: node id}).
    """
    g = Graph(lat0, site_kph)
    segs = []   # (a_node, b_node, mpm, zone)
    for r in roads:
        pts = [_xy(p, lat0) for p in (r.get("line") or []) if p and len(p) >= 2]
        if len(pts) < 2:
            continue
        mpm = (float(r["speed_kph"]) if r.get("speed_kph") else site_kph) * 1000.0 / 60.0
        ids = [g.node(pts[0], JOIN_M)] + [g.node(p) for p in pts[1:-1]] + [g.node(pts[-1], JOIN_M)]
        for a, b in zip(ids, ids[1:]):
            g.edge(a, b, mpm, r["zone_id"])
            segs.append((a, b, mpm, r["zone_id"]))
    at = {}
    loose = []
    for key, p in stations.items():
        xy = _xy(p, lat0)
        k = g.node(xy)
        at[key] = k
        best = None
        for a, b, mpm, zone in segs:
            q, dist, u = _proj(xy, g.nodes[a], g.nodes[b])
            if dist <= SNAP_M and (best is None or dist < best[0]):
                best = (dist, q, a, b, mpm, zone)
        if best is None:
            loose.append(k)
            continue
        dist, q, a, b, mpm, zone = best
        qn = g.node(q, JOIN_M)
        if qn not in (a, b):
            g.edge(a, qn, mpm, zone)
            g.edge(qn, b, mpm, zone)
        if dist > 0.5:
            g.edge(k, qn, g.site_mpm, None)
        elif qn != k:
            g.edge(k, qn, g.site_mpm, None)
    # a station off every road: straight to every other station (a site with no roads drawn works this way)
    keys = list(at.values())
    for k in loose:
        for other in keys:
            if other != k:
                g.edge(k, other, g.site_mpm, None)
    return g, at


def leg_from_path(g, nodes_path):
    """The drawing's leg for a path: coords (lon, lat), cum metres, parts [[a, b, mpm, zone, t0, t1]], minutes."""
    coords, cum, parts = [], [0.0], []
    pos, t = 0.0, 0.0
    for i, (n, L, mpm, zone) in enumerate(nodes_path):
        coords.append(_ll(*g.nodes[n], g.lat0))
        if i == 0:
            continue
        cum.append(cum[-1] + L)
        dt = L / mpm if mpm > 0 else 0.0
        if parts and parts[-1][3] == zone and abs(parts[-1][2] - mpm) < 1e-9:
            parts[-1][1] = pos + L
            parts[-1][5] = t + dt
        else:
            parts.append([pos, pos + L, mpm, zone, t, t + dt])
        pos += L
        t += dt
    if not parts:
        parts = [[0.0, 0.0, g.site_mpm, None, 0.0, 0.0]]
    return {"coords": coords, "cum": [round(c, 1) for c in cum], "len_m": round(pos, 1),
            "parts": [[round(p[0], 1), round(p[1], 1), round(p[2], 4), p[3], round(p[4], 3), round(p[5], 3)] for p in parts],
            "minutes": round(t, 3)}


# --------------------------------------------------------------------------- the site model
def site_model(loc, loc_gates, areas, roads, factors, scen, on=None):
    """
    One site ready to simulate: its stations (every active gate, every active area, the wash), the graph and the
    speed. `scen`: {"site_speed": {loc id: kph}, "service": {area id: min}, "bays": {area id: n}, "wash": None|bool}.
    """
    sc = scen or {}
    typed = loc.get("site_speed_kph")
    if loc["id"] in (sc.get("site_speed") or {}):
        kph, basis = float(sc["site_speed"][loc["id"]]), "scenario"
    elif typed not in (None, ""):
        kph, basis = float(typed), "typed"
    else:
        kph, basis = DEFAULT_SITE_KPH, "default"
    active_areas = [a for a in areas if a["active"]]
    wash_area = site_areas.wash_for(active_areas)
    wash = None if sc.get("wash") is False else wash_area
    stations, points = {}, {}
    for g in loc_gates:
        if not g.get("active"):
            continue
        key = f"gate:{g['id']}"
        stations[key] = {"key": key, "kind": "gate", "name": g.get("name"), "gate_id": g["id"], "bays": 1,
                         "service": None, "closed": gates.closed_on(g, on), "closed_words": gates.closed_words(g),
                         "serves_entry": gates.serves(g, "entry"), "serves_exit": gates.serves(g, "exit")}
        if g.get("lat") is not None and g.get("lon") is not None:
            points[key] = [float(g["lon"]), float(g["lat"])]
    for a in active_areas:
        if a is wash_area and sc.get("wash") is False:
            continue
        key = f"area:{a['id']}"
        bays = int((sc.get("bays") or {}).get(a["id"], a["bays"]))
        svc = (sc.get("service") or {}).get(a["id"])
        stations[key] = {"key": key, "kind": a["activity"], "name": a["name"], "area_id": a["id"], "bays": max(1, bays),
                         "service": (float(svc) if svc is not None else None), "area": a,
                         "service_basis": ("scenario" if svc is not None else ("typed" if a.get("service_minutes") is not None else "vehicle"))}
        if a.get("point"):
            points[key] = a["point"]
    lat0 = float(loc["lat"]) * math.pi / 180
    road_lines = [{"zone_id": z["id"], "line": z.get("line"), "speed_kph": z.get("speed_kph")} for z in roads if z.get("line")]
    graph, at = build_graph(road_lines, points, kph, lat0)
    return {"location_id": loc["id"], "name": loc.get("name") or loc["id"], "speed_kph": kph, "speed_basis": basis,
            "areas": active_areas, "wash": wash, "roads": roads, "stations": stations, "graph": graph, "at": at,
            "paths": {}, "on": on, "loc": loc, "loc_gates": loc_gates, "factors": factors}


def path_between(site, a_key, b_key):
    """The leg between two stations (cached), or None when a station has no point."""
    k = f"{a_key}>{b_key}"
    if k in site["paths"]:
        return site["paths"][k]
    at = site["at"]
    if a_key not in at or b_key not in at:
        site["paths"][k] = None
        return None
    p = site["graph"].path(at[a_key], at[b_key])
    site["paths"][k] = leg_from_path(site["graph"], p) if p else None
    return site["paths"][k]


def exit_key(site, in_key):
    """The station key of the gate a lorry LEAVES by: the site's exit gate on the day (gates.resolve, closures)."""
    r = gates.resolve(site["loc"], "exit", None, gates=site["loc_gates"], on=site["on"])
    gid = r.get("gate_id")
    key = f"gate:{gid}" if gid else None
    return key if key in site["stations"] else in_key


def chain_for(site, arrival, line):
    """
    The stations after the gate for one checked-in lorry: [area, wash, gate out] — or [] when no area takes its
    material (it leaves from the gate, as before v2; the reply names the line). `line` carries material / vehicle.
    """
    kind = arrival["kind"]
    material = "Ready-mixed concrete" if kind == "pour" else (line or {}).get("material")
    vehicle = (line or {}).get("vehicle_drawn") or (line or {}).get("vehicle")
    area = site_areas.area_for(site["areas"], kind, material, vehicle)
    if area is None or f"area:{area['id']}" not in site["stations"]:
        return [], area
    out = [f"area:{area['id']}"]
    if site["wash"] is not None and f"area:{site['wash']['id']}" in site["stations"]:
        out.append(f"area:{site['wash']['id']}")
    out.append(exit_key(site, arrival["gate_key"]))
    return out, area


def service_minutes(site, key, vehicle, factors):
    st = site["stations"][key]
    if st["kind"] == "gate":
        return 0.0
    if st["service"] is not None:
        return st["service"]
    return site_areas.service_for(st["area"], vehicle, factors)


# --------------------------------------------------------------------------- the run
def run_site(site, lorries, lines, factors):
    """
    `lorries` = the site's checked-in arrivals (sim.queue's dicts: t, start, done, kind, line, gate) in any order.
    Sets on each: `chain`, `stops` [{st, t, start, done, bay, wait}], `hops` [{path, t0, t1}], `out_at`, `on_site`,
    `no_area`. Returns the site's figures.
    """
    for a in lorries:
        a["gate_key"] = f"gate:{a['gate']}"
    free = {k: [-1e9] * st["bays"] for k, st in site["stations"].items()}
    stops = {k: [] for k in site["stations"]}
    heap = []
    seq = 0
    no_area = {}
    for a in lorries:
        line = lines[a["line"]] if a.get("line") is not None else None
        chain, area = chain_for(site, a, line)
        a["chain"], a["stops"], a["hops"], a["no_area"] = chain, [], [], (not chain)
        a["vehicle"] = (line or {}).get("vehicle_drawn") or (line or {}).get("vehicle")
        if not chain:
            a["out_at"], a["on_site"] = a["done"], 0.0
            if line is not None:
                no_area.setdefault(line["route_id"], {"route": line["route_id"], "material": line.get("material"),
                                                       "vehicle_label": line.get("vehicle_label"), "lorries": 0})["lorries"] += 1
            elif a["kind"] == "pour":
                no_area.setdefault("pour", {"route": None, "material": "Ready-mixed concrete", "vehicle_label": None, "lorries": 0})["lorries"] += 1
            continue
        leg = path_between(site, a["gate_key"], chain[0])
        drive = leg["minutes"] if leg else 0.0
        if leg:
            a["hops"].append({"path": f"{a['gate_key']}>{chain[0]}", "t0": a["done"], "t1": a["done"] + drive})
        heapq.heappush(heap, (a["done"] + drive, seq, id(a), 0))
        seq += 1
    by_id = {id(a): a for a in lorries}
    while heap:
        t, _s, aid, k = heapq.heappop(heap)
        a = by_id[aid]
        key = a["chain"][k]
        st = site["stations"][key]
        svc = service_minutes(site, key, a.get("vehicle"), factors)
        bays = free[key]
        bay = min(range(len(bays)), key=lambda i: bays[i])
        start = max(t, bays[bay]) if svc > 0 else t
        done = start + svc
        if svc > 0:
            bays[bay] = done
        stop = {"st": key, "t": t, "start": start, "done": done, "bay": bay, "wait": start - t, "service": svc}
        a["stops"].append(stop)
        stops[key].append(stop)
        if k + 1 < len(a["chain"]):
            nxt = a["chain"][k + 1]
            leg = path_between(site, key, nxt)
            drive = leg["minutes"] if leg else 0.0
            if leg:
                a["hops"].append({"path": f"{key}>{nxt}", "t0": done, "t1": done + drive})
            heapq.heappush(heap, (done + drive, seq, aid, k + 1))
            seq += 1
        else:
            a["out_at"] = done
            a["on_site"] = done - a["start"]
    figures = []
    for key, st in site["stations"].items():
        S = sorted(stops[key], key=lambda x: x["t"])
        if st["kind"] == "gate" and not S:
            continue
        figures.append(station_figures(st, S))
    chained = [a for a in lorries if a["chain"]]
    on = [a["on_site"] for a in chained]
    return {"stations": figures, "no_area": sorted(no_area.values(), key=lambda x: (x["route"] or "")),
            "lorries_in": len(lorries), "lorries_out": len(chained),
            "avg_on_site": (round(sum(on) / len(on), 2) if on else None),
            "longest_on_site": (round(max(on), 2) if on else None),
            "minutes_lost": round(sum(s["wait"] for a in chained for s in a["stops"]), 2)}


def station_figures(st, S):
    """The gate's figures (sim.gate_figures' rule) for one station's stops, sorted by arrival."""
    svc_ref = max([s["service"] for s in S] or [0.0])
    hours = [0] * 24
    for s in S:
        hours[min(23, max(0, int(s["t"] // 60)))] += 1
    busiest = max([0] + hours)
    bh = [h for h, n in enumerate(hours) if n == busiest and n > 0]
    first = next((s for s in S if s["wait"] > WAIT_EPS), None)
    bott = next((s for s in S if s["service"] > 0 and s["wait"] > s["service"] + WAIT_EPS), None)
    ev = []
    for s in S:
        if s["wait"] > WAIT_EPS:
            ev.append((s["t"], 1))
            ev.append((s["start"], -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = most = 0
    most_at = None
    for t, d in ev:
        cur += d
        if cur > most:
            most, most_at = cur, t
    if st["kind"] == "gate":
        flag, word = None, "Counted, never queued"
    elif not S:
        flag, word = None, "No arrivals"
    elif bott is not None:
        flag, word = "red", STATION_WORDS["red"]
    elif first is not None:
        flag, word = "amber", STATION_WORDS["amber"]
    else:
        flag, word = None, STATION_WORDS["ok"]
    return {"key": st["key"], "kind": st["kind"], "name": st["name"], "area_id": st.get("area_id"),
            "gate_id": st.get("gate_id"), "bays": st["bays"] if st["kind"] != "gate" else None,
            "service": (round(svc_ref, 2) if st["kind"] != "gate" else None), "service_basis": st.get("service_basis"),
            "arrivals": len(S), "hours": hours, "busiest": busiest,
            "busiest_hour": (f"{bh[0]:02d}:00" if bh else None),
            "queue_start": (round(first["t"], 2) if first else None),
            "bottleneck_at": (round(bott["t"], 2) if bott else None),
            "most_waiting": most, "most_at": (round(most_at, 2) if most_at is not None else None),
            "minutes_lost": round(sum(s["wait"] for s in S), 2),
            "longest_wait": round(max([0.0] + [s["wait"] for s in S]), 2),
            "flag": flag, "status_word": word, "closed_words": st.get("closed_words")}


def site_reply(site, fig, send_lines):
    """
    The reply's block for one site. Its lines (the roads, the areas, the paths between stations) are small and
    change with the scenario (a site speed moves every path's minutes), so they travel in EVERY reply; only the
    routes' long lines wait for legs=1.
    """
    gl = {g["id"]: g for g in site["loc_gates"]}
    out = {"location_id": site["location_id"], "name": site["name"],
           "speed_kph": site["speed_kph"], "speed_basis": site["speed_basis"],
           "gates": [{"gate_id": st["gate_id"], "name": st["name"], "entry": st["serves_entry"], "exit": st["serves_exit"],
                      "closed": st["closed"], "closed_words": st["closed_words"],
                      "lat": (gl.get(st["gate_id"]) or {}).get("lat"), "lon": (gl.get(st["gate_id"]) or {}).get("lon")}
                     for st in site["stations"].values() if st["kind"] == "gate"],
           "areas": [{"id": a["id"], "name": a["name"], "activity": a["activity"], "bays": site["stations"][f"area:{a['id']}"]["bays"],
                      # the minutes the station runs at (typed, the scenario's, or the default) — the drawing's label
                      "service": service_minutes(site, f"area:{a['id']}", None, site.get("factors")), "service_typed": a.get("service_minutes"),
                      "level": a.get("level"), "materials": a["materials"], "vehicles": a["vehicles"],
                      "point": a.get("point"), "geometry": a.get("geometry")}
                     for a in site["areas"] if f"area:{a['id']}" in site["stations"]],
           "wash": (site["wash"]["id"] if site["wash"] else None),
           "roads": [{"zone_id": z["id"], "name": z.get("name"), "speed_kph": z.get("speed_kph"), "length_km": z.get("length_km"),
                      "coords": z.get("line")} for z in site["roads"]],
           "paths": {k: v for k, v in site["paths"].items() if v}}
    out.update(fig)
    return out
