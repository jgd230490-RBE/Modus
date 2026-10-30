"""
sim_holding.py — a vehicle holding area in the haulage simulation (task 3c, 29 Oct 2026; the user's Q3).

With a holding area, the lorries for the sites it serves no longer drive straight to the gate: each one that calls
off (holding.stops: the leg arrives at a served site, the lorry type is not exempt, the route is not ticked; a pour's
mixer never) reaches the HOLDING AREA first — at the moment it would have reached the gate, less the run from the
holding area to the gate — and waits there to be CALLED FORWARD. The rule, for the first held lorry in order of
arrival whose turn it is:
    (a) fewer than `call` lorries are on their way to, or waiting at, its first station on site (its bay; the gate
        itself for a lorry no area takes) — "called forward at a time", typed on the holding area;
    (b) fewer than GATE_LANE lorries are waiting at the gate;
    (c) it would reach the gate while the gate is open — else it is called so that it arrives as the gate opens.
Once called it drives to the gate and runs the gate's one lane and the site's chain of stations exactly as every other
lorry (sim.queue's rule for the lane, sim_site's for the stations), in ONE event loop, because a call depends on a bay
starting and a lane clearing. Lorries that do not call off (exempt, or a line whose route is ticked) take the same lane
and stations in the same loop, so the gate's order is first come first served across both.

Per holding area: the lorries held, the most held at once and when (against its spaces), when call-off begins, the
minutes held and the longest hold, arrivals by hour. Per gate and per station the figures are the ones sim.gate_figures
and sim_site.station_figures give, from the same stops. With the holding area off (the scenario) nothing here runs and
every figure is the plain day's.

What is not modelled, said on the screen: bookings and slots, a lorry turned away when the holding area is full (it is
counted as "over its spaces"), a lorry looping instead of holding, the drive to and from a holding area off the line
(that lorry is drawn straight from the holding area to the gate, and the reply says so).

Pure: no SQL, no db. Never spells a team slot id.
"""
import heapq

import sim_site

#: a lorry is called forward only while fewer than this many wait in the gate's lane
GATE_LANE = 2
WAIT_EPS = 0.01


def _next_service(iv, s):
    """sim.next_service without the import cycle: the first minute at or after `s` the gate is open."""
    for a, b in iv:
        if s < a:
            return a
        if s < b:
            return s
    return s


def run(H, gates_in, sites, lines, factors):
    """
    One holding area's day.
      H         {"id", "name", "spaces" (int|None), "call" (int), ...}
      gates_in  {gate id: {"arrivals": [sim.simulate's arrival dicts, `t` placed], "iv": [(a, b)...], "check_in": c|None,
                           "site": location id|None}} — every arrival at the served sites' gates; an arrival that calls
                 off carries `hold` = {"tail": minutes from the holding area to the gate, "straight": bool}
      sites     {location id: sim_site.site_model(...)} for the served sites that have a model
    Sets on each arrival: t (the gate arrival), start, wait, done (the lane), held {at, called, wait, straight} or None,
    chain, stops, hops, out_at, on_site, no_area (as sim_site.run_site). Returns
      {"gates": {gate id: arrivals sorted by t}, "sites": {location id: run_site's figures}, "figures": {...}}.
    """
    N = max(1, int(H.get("call") or 1))
    heap, seq = [], [0]

    def push(t, kind, aid=None, k=0):
        heapq.heappush(heap, (t, seq[0], kind, aid, k))
        seq[0] += 1

    lorries, by_id = [], {}
    gate_free = {g: -1e9 for g in gates_in}
    gate_waiting = {g: 0 for g in gates_in}
    called_for = {}                 # first station key -> lorries called for it and not yet started there
    free = {}                       # (site id, station key) -> [bay free times]
    stops_at = {}                   # (site id, station key) -> stops
    no_area = {lid: {} for lid in sites}
    held = []                       # at the holding area, in order of arrival
    H_fig = {"held": 0, "hours": [0] * 24, "now": 0, "most": 0, "most_at": None, "first": None,
             "minutes": 0.0, "longest": 0.0, "straight": 0, "events": []}
    recall_at = [None]

    for gid, gi in gates_in.items():
        site = sites.get(gi.get("site"))
        for a in gi["arrivals"]:
            if a.get("t") is None:
                continue                    # not placed (no open minute): left as sim.queue leaves it
            a["gate_key"] = f"gate:{gid}"
            line = lines[a["line"]] if a.get("line") is not None else None
            if site is not None:
                chain, area = sim_site.chain_for(site, a, line)
            else:
                chain, area = [], None
            a["chain"], a["stops"], a["hops"], a["no_area"] = chain, [], [], (not chain)
            a["vehicle"] = (line or {}).get("vehicle_drawn") or (line or {}).get("vehicle")
            x = {"a": a, "gid": gid, "site": site, "lid": gi.get("site"), "line": line, "chain": chain,
                 "target": (chain[0] if chain else a["gate_key"]), "held": None, "id": id(a)}
            by_id[x["id"]] = x
            lorries.append(x)
            h = a.get("hold") if a["kind"] != "pour" else None
            if h:
                tv = a["t"] - float(h.get("tail") or 0.0)
                x["held"] = {"at": tv, "called": None, "wait": None, "straight": bool(h.get("straight")), "tail": float(h.get("tail") or 0.0)}
                a["t_placed"] = a["t"]
                a["t"] = None
                push(tv, "hold", x["id"])
            else:
                push(a["t"], "gate", x["id"])
            if site is not None and not chain:
                if line is not None:
                    no_area[x["lid"]].setdefault(line["route_id"], {"route": line["route_id"], "material": line.get("material"),
                                                                       "vehicle_label": line.get("vehicle_label"), "lorries": 0})["lorries"] += 1
                elif a["kind"] == "pour":
                    no_area[x["lid"]].setdefault("pour", {"route": None, "material": "Ready-mixed concrete", "vehicle_label": None, "lorries": 0})["lorries"] += 1

    def can_call(x, now):
        if called_for.get(x["target"], 0) >= N:
            return None
        if gate_waiting[x["gid"]] >= GATE_LANE:
            return None
        iv = gates_in[x["gid"]]["iv"]
        at = now + x["held"]["tail"]
        s = _next_service(iv, at) if iv else at
        if s > at + WAIT_EPS:
            return ("later", s - x["held"]["tail"])          # the gate is shut then: call it so that it arrives as it opens
        return ("now", now)

    def try_call(now):
        moved = True
        while moved and held:
            moved = False
            for j, x in enumerate(held):
                r = can_call(x, now)
                if r is None:
                    continue
                if r[0] == "later":
                    if recall_at[0] is None or r[1] < recall_at[0] - WAIT_EPS:
                        recall_at[0] = r[1]
                        push(r[1], "recall")
                    continue
                held.pop(j)
                H_fig["now"] -= 1
                w = now - x["held"]["at"]
                x["held"]["called"], x["held"]["wait"] = now, w
                H_fig["minutes"] += w
                H_fig["longest"] = max(H_fig["longest"], w)
                if w > WAIT_EPS and H_fig["first"] is None:
                    H_fig["first"] = x["held"]["at"]
                H_fig["events"].append((x["held"]["at"], 1))
                H_fig["events"].append((now, -1))
                called_for[x["target"]] = called_for.get(x["target"], 0) + 1
                push(now + x["held"]["tail"], "gate", x["id"])
                moved = True
                break

    while heap:
        t, _s, kind, aid, k = heapq.heappop(heap)
        if kind == "recall":
            recall_at[0] = None
            try_call(t)
            continue
        x = by_id[aid]
        a = x["a"]
        if kind == "hold":
            H_fig["held"] += 1
            H_fig["hours"][min(23, max(0, int(t // 60)))] += 1
            if x["held"]["straight"]:
                H_fig["straight"] += 1
            held.append(x)
            H_fig["now"] += 1
            if H_fig["now"] > H_fig["most"]:
                H_fig["most"], H_fig["most_at"] = H_fig["now"], t
            try_call(t)
        elif kind == "gate":
            gid, c = x["gid"], gates_in[x["gid"]]["check_in"]
            a["t"] = t
            if c is None or not c > 0:
                a["start"], a["wait"], a["done"] = t, 0.0, t
            else:
                s = _next_service(gates_in[gid]["iv"], max(t, gate_free[gid]))
                a["start"], a["wait"], a["done"] = s, s - t, s + c
                gate_free[gid] = a["done"]
            if a["wait"] > WAIT_EPS:
                gate_waiting[gid] += 1
                push(a["start"], "gate_start", aid)
            elif x["held"] and x["target"] == a["gate_key"]:
                called_for[x["target"]] -= 1
                try_call(t)
            if x["chain"]:
                leg = sim_site.path_between(x["site"], a["gate_key"], x["chain"][0])
                drive = leg["minutes"] if leg else 0.0
                if leg:
                    a["hops"].append({"path": f"{a['gate_key']}>{x['chain'][0]}", "t0": a["done"], "t1": a["done"] + drive})
                push(a["done"] + drive, "station", aid, 0)
            else:
                a["out_at"], a["on_site"] = a["done"], 0.0
        elif kind == "gate_start":
            gate_waiting[x["gid"]] -= 1
            if x["held"] and x["target"] == a["gate_key"]:
                called_for[x["target"]] -= 1
            try_call(t)
        elif kind == "station":
            key = x["chain"][k]
            site = x["site"]
            st = site["stations"][key]
            svc = sim_site.service_minutes(site, key, a.get("vehicle"), factors)
            fk = (x["lid"], key)
            bays = free.setdefault(fk, [-1e9] * st["bays"])
            bay = min(range(len(bays)), key=lambda i: bays[i])
            start = max(t, bays[bay]) if svc > 0 else t
            done = start + svc
            if svc > 0:
                bays[bay] = done
            stop = {"st": key, "t": t, "start": start, "done": done, "bay": bay, "wait": start - t, "service": svc}
            a["stops"].append(stop)
            stops_at.setdefault(fk, []).append(stop)
            if k == 0 and x["held"]:
                push(start, "bay_start", aid, k)
            if k + 1 < len(x["chain"]):
                nxt = x["chain"][k + 1]
                leg = sim_site.path_between(site, key, nxt)
                drive = leg["minutes"] if leg else 0.0
                if leg:
                    a["hops"].append({"path": f"{key}>{nxt}", "t0": done, "t1": done + drive})
                push(done + drive, "station", aid, k + 1)
            else:
                a["out_at"] = done
                a["on_site"] = done - a["start"]
        elif kind == "bay_start":
            called_for[x["target"]] -= 1
            try_call(t)

    # the gates: every arrival by its gate arrival time (sim.queue's order)
    out_gates = {gid: sorted((x["a"] for x in lorries if x["gid"] == gid and x["a"].get("t") is not None), key=lambda a: a["t"])
                 for gid in gates_in}
    # the sites: run_site's figures from the same stops
    out_sites = {}
    for lid, site in sites.items():
        figures = []
        for key, st in site["stations"].items():
            S = sorted(stops_at.get((lid, key), []), key=lambda s: s["t"])
            if st["kind"] == "gate" and not S:
                continue
            figures.append(sim_site.station_figures(st, S))
        mine = [x["a"] for x in lorries if x["lid"] == lid]
        chained = [a for a in mine if a.get("chain")]
        on = [a["on_site"] for a in chained if a.get("on_site") is not None]
        out_sites[lid] = {"stations": figures, "no_area": sorted(no_area[lid].values(), key=lambda v: (v["route"] or "")),
                          "lorries_in": len(mine), "lorries_out": len(chained),
                          "avg_on_site": (round(sum(on) / len(on), 2) if on else None),
                          "longest_on_site": (round(max(on), 2) if on else None),
                          "minutes_lost": round(sum(s["wait"] for a in chained for s in a["stops"]), 2)}
    # the holding area: the most held at once from the arrive / called events (a lorry called at once never counts)
    ev = sorted(H_fig["events"], key=lambda e: (e[0], e[1]))
    cur, most, most_at = 0, 0, None
    for tt, d in ev:
        cur += d
        if cur > most:
            most, most_at = cur, tt
    for x in lorries:
        x["a"]["held"] = (dict(x["held"]) if x["held"] else None)
        if x["held"]:
            x["a"]["held"]["at"] = round(x["held"]["at"], 2)
            x["a"]["held"]["called"] = (round(x["held"]["called"], 2) if x["held"]["called"] is not None else None)
            x["a"]["held"]["wait"] = (round(x["held"]["wait"], 2) if x["held"]["wait"] is not None else None)
    spaces = H.get("spaces")
    return {"gates": out_gates, "sites": out_sites,
            "figures": {"held": H_fig["held"], "hours": H_fig["hours"], "most": most,
                        "most_at": (round(most_at, 2) if most_at is not None else None),
                        "over_spaces": (max(0, most - int(spaces)) if spaces else 0),
                        "first": (round(H_fig["first"], 2) if H_fig["first"] is not None else None),
                        "minutes_held": round(H_fig["minutes"], 2), "longest": round(H_fig["longest"], 2),
                        "straight": H_fig["straight"], "call": N, "gate_lane": GATE_LANE,
                        "all_called": all(x["held"]["called"] is not None for x in lorries if x["held"])}}
