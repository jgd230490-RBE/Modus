"""
Busy-hour drive times (29 Oct 2026, task 0f-2).

John (28 Oct): "could a route take an alternative in the hours of congestion for quicker cycle times?" The live probe
of 28 Oct (notes/busy-hours-0f-mockup-1028/probe-20261028.txt) showed HERE's drive times move 4-38 % with the hour, that
its options change with the hour, and that on some routes an option HERE does not rank first is quicker in the busy
hours. This module works out each route's drive times for a lorry setting off at HOURS on the bake's weekday
(here_routing.bake_departure_time, the same Tuesday), and the screens show the cycle at SCREEN_HOURS beside the plan's
figure. NEVER in it: the plan's cycle, trips, lorries and carbon stay the pinned 10:00 bake (D94; Q4 of the mockup).

The run (an admin's "Busy-hour times" button, never Route all): one HERE call per (route, leg, hour) for PROFILE only
(Q3, the Artic Tipper; the other lorry types are scaled from it where they run the same road), asked exactly as the bake
asks (network.leg_request, network.active_avoid, haul.route_with_haul, ALTERNATIVES options). Each option HERE gives is
stored with its line's fingerprint and named by the STORED option with the same line (alt_index; None = a road not
stored), with that stored line's computed_at. A reader (times_for) trusts a row only while the stored line is still the
one it matched, so a re-route quietly retires the times instead of showing them against another road. Options change
with the hour, which is why the key is the road, not the option number (README Q8).

WHAT IS NOT VERIFIED: HERE answers for a future weekday from what it knows of that hour; it does not say whether that is
typical traffic or a forecast. The probe found Tuesday and Thursday within 2.3 %.
"""
import datetime
import json
import time

import db
import haul
import here_routing

PROFILE = "Artic Tipper (44t)"
HOURS = ("06:00", "08:00", "09:00", "12:00", "15:00", "17:00", "18:00")
SCREEN_HOURS = ("08:00", "12:00", "17:00")
SAME_ROAD_KM = 0.05        # another lorry type's option counts as the tipper's road when both legs are within 50 m


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _stored(profile):
    """{(route_id, leg): {fingerprint: (alt_index, computed_at)}} for the profile's stored lines, and the legs."""
    out = {}
    for g in db.query("SELECT route_id, leg, alt_index, geometry, computed_at FROM route_geometry "
                      "WHERE tenant_id = ? AND vehicle_profile = ? AND geometry IS NOT NULL ORDER BY route_id, leg, alt_index",
                      (db.current_tenant(), profile)):
        try:
            fp = here_routing._fingerprint(json.loads(g["geometry"]))
        except Exception:
            fp = None
        d = out.setdefault((g["route_id"], g["leg"]), {})
        if fp and fp not in d:
            d[fp] = (g["alt_index"], g["computed_at"])
    return out


def _legs(profile):
    return sorted({(g["route_id"], g["leg"]) for g in db.query(
        "SELECT route_id, leg FROM route_geometry WHERE tenant_id = ? AND vehicle_profile = ? AND alt_index = 0 "
        "AND geometry IS NOT NULL", (db.current_tenant(), profile))})


def _second(s):
    """An ISO time cut to the whole second (UTC), or None. Rows here are stamped to the second, stored lines finer."""
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(datetime.timezone.utc).replace(microsecond=0)


class _Lines:
    """
    16 Nov 2026 (claude/busy-hours-redo-stale): the stored lines a row may have matched, read without their polyline text.

    A row names the stored line it matched by that line's computed_at (geom_computed_at). A re-route writes a new
    computed_at, so the row is no longer trusted. Make primary (network.promote_alternative) swaps an option's NUMBER with
    0 and leaves computed_at alone: the line is the same, so the row stays trusted and is read under the line's number
    NOW. Where several stored options carry the same computed_at, the row's own fingerprint picks its line (the only
    case that reads polyline text, one line at a time).
    """

    def __init__(self, route_id=None, profile=None):
        sql = ("SELECT route_id, vehicle_profile, leg, alt_index, computed_at FROM route_geometry "
               "WHERE tenant_id = ? AND geometry IS NOT NULL")
        args = [db.current_tenant()]
        if route_id is not None:
            sql += " AND route_id = ?"
            args.append(route_id)
        if profile is not None:
            sql += " AND vehicle_profile = ?"
            args.append(profile)
        self.by_at, self.newest, self._fps = {}, {}, {}
        for g in db.query(sql, tuple(args)):
            k = (g["route_id"], g["vehicle_profile"], g["leg"])
            self.by_at.setdefault(k, {}).setdefault(str(g["computed_at"]), []).append(int(g["alt_index"]))
            t = _second(g["computed_at"])
            if t is not None and (self.newest.get(k) is None or t > self.newest[k]):
                self.newest[k] = t

    def _fp(self, k, alt):
        if (k, alt) not in self._fps:
            g = db.query("SELECT geometry FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? "
                         "AND leg = ? AND alt_index = ?", (db.current_tenant(), k[0], k[1], k[2], alt))
            try:
                self._fps[(k, alt)] = here_routing._fingerprint(json.loads(g[0]["geometry"])) if g else None
            except Exception:
                self._fps[(k, alt)] = None
        return self._fps[(k, alt)]

    def alt_now(self, route_id, profile, leg, row):
        """The number the row's line has NOW, or None when that line is no longer stored (the row is not trusted)."""
        if row.get("alt_index") is None or row.get("geom_computed_at") is None:
            return None
        k = (route_id, profile, leg)
        alts = (self.by_at.get(k) or {}).get(str(row["geom_computed_at"])) or []
        if len(alts) <= 1:
            return alts[0] if alts else None
        if row.get("fingerprint"):
            hit = [a for a in alts if self._fp(k, a) == row["fingerprint"]]
            return hit[0] if hit else None
        return int(row["alt_index"]) if int(row["alt_index"]) in alts else None


def _to_do(profile):
    """
    The (route, leg, hour) a run works out, as [((route_id, leg, hour), why)], why = "absent" (no row) or "stale" (16 Nov
    2026: rows the reader no longer trusts). A key is stale when a row that named a stored line no longer finds it, or
    when it was worked out before the leg's newest stored line (a re-route; a key whose options matched no stored line
    has nothing else to tell). A failed call's row (rank -1) is done until the leg is routed again, as before.
    """
    lines = _Lines(profile=profile)
    keys = {}
    for x in db.query("SELECT route_id, leg, hour, rank, alt_index, geom_computed_at, fingerprint, computed_at "
                      "FROM route_hour_times WHERE tenant_id = ? AND vehicle_profile = ?", (db.current_tenant(), profile)):
        keys.setdefault((x["route_id"], x["leg"], x["hour"]), []).append(x)
    out = []
    for r, l in _legs(profile):
        newest = lines.newest.get((r, profile, l))
        for h in HOURS:
            rows = keys.get((r, l, h))
            if not rows:
                out.append(((r, l, h), "absent"))
                continue
            gone = any(x["rank"] >= 0 and x["alt_index"] is not None and lines.alt_now(r, profile, l, x) is None
                       for x in rows)
            at = [_second(x["computed_at"]) for x in rows]
            older = newest is not None and all(t is not None for t in at) and max(at) < newest
            if gone or older:
                out.append(((r, l, h), "stale"))
    return out


def plan(profile=PROFILE):
    """
    What a run would cost, before it is pressed: routes, legs, hours and HERE calls (haul._here_calls_for x hours) for
    the whole run (`here_calls`, what a clear and a run costs), and since 16 Nov 2026 `to_do`: what a run WITHOUT a clear
    works out (the rows absent or no longer trusted, e.g. after a re-route) and the calls that costs. No HERE call.
    """
    legs = _legs(profile)
    per = {(r, l): haul._here_calls_for([(r, profile, l)]) for r, l in legs}
    todo = _to_do(profile)
    tl = {(r, l) for (r, l, _h), _w in todo}
    return {"profile": profile, "routes": len({r for r, _ in legs}), "legs": len(legs), "hours": list(HOURS),
            "here_calls": sum(per.values()) * len(HOURS), "worked_out": status(profile),
            "to_do": {"routes": len({r for r, _ in tl}), "legs": len(tl), "leg_hours": len(todo),
                      "absent": sum(1 for _k, w in todo if w == "absent"), "stale": sum(1 for _k, w in todo if w == "stale"),
                      "here_calls": sum(per.get((r, l), 1) for (r, l, _h), _w in todo)}}


def status(profile=PROFILE):
    """When the times were last worked out, and for which day: None when there are none."""
    r = db.query("SELECT MAX(computed_at) AS at, MAX(depart_at) AS dep, COUNT(*) AS n FROM route_hour_times "
                 "WHERE tenant_id = ? AND vehicle_profile = ? AND rank >= 0", (db.current_tenant(), profile))
    if not r or not r[0]["n"]:
        return None
    return {"computed_at": r[0]["at"], "day": (r[0]["dep"] or "")[:10], "rows": r[0]["n"]}


def clear(profile=PROFILE):
    db.execute("DELETE FROM route_hour_times WHERE tenant_id = ? AND vehicle_profile = ?", (db.current_tenant(), profile))
    return {"cleared": True, "profile": profile}


def bake_batch(profile=PROFILE, limit=30, budget_s=None, now=None):
    """
    Work out up to `limit` (route, leg, hour) times not yet worked out for the profile. Call until `remaining` is 0
    (the page loops, as Route all). A failed call is stored as rank -1 with the reason, so the run moves on; `errors`
    counts them. Stops starting calls after `budget_s` seconds (network.BAKE_BUDGET_S from the endpoint).
    16 Nov 2026: "not yet worked out" includes a key whose rows the reader no longer trusts (_to_do: a re-route); its
    rows are replaced. Before, any row counted as done and a re-routed line kept no times until a clear and a full run.
    """
    import network
    if not here_routing.configured():
        return {"error": "HERE_API_KEY not set on the server", "baked": 0, "remaining": None}
    tenant = db.current_tenant()
    todo = [k for k, _why in _to_do(profile)]
    routes = {x["id"]: x for x in db.query("SELECT * FROM routes WHERE tenant_id = ?", (tenant,))}
    locs = {x["id"]: x for x in db.query("SELECT * FROM locations WHERE tenant_id = ?", (tenant,))}
    try:
        import gates
        gbl = gates.gates_by_location()
    except Exception:
        gbl = {}
    avoid, _tag = network.active_avoid()
    stored = _stored(profile)
    factors = __import__("conversions").load_factors()
    t0 = time.monotonic()
    baked = errors = calls = attempted = 0
    reqs = {}
    for rid, leg, hour in todo[:limit]:
        if budget_s is not None and attempted and time.monotonic() - t0 >= budget_s:
            break
        attempted += 1
        r = routes.get(rid)
        o, d = locs.get((r or {}).get("origin_id")), locs.get((r or {}).get("dest_id"))
        dep = here_routing.bake_departure_time(now=now, hour=hour)
        db.execute("DELETE FROM route_hour_times WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ? AND leg = ? "
                   "AND hour = ?", (tenant, rid, profile, leg, hour))
        try:
            if not r or not o or not d:
                raise RuntimeError("route or its ends missing")
            if (rid, leg) not in reqs:
                reqs[(rid, leg)] = network.leg_request(r, o, d, leg, gbl)
            q = reqs[(rid, leg)]
            opts = haul.route_with_haul(q["a"]["lat"], q["a"]["lon"], q["b"]["lat"], q["b"]["lon"], profile, q["steps"],
                                        factors=factors, avoid_areas=(avoid or None), laden=(leg == "loaded"),
                                        alternatives=network.ALTERNATIVES, departure_time=dep)
            calls += (opts[0].get("haul_calls") or 1) if opts else 1
            match = stored.get((rid, leg), {})
            for rank, opt in enumerate(opts):
                fp = here_routing._fingerprint(opt.get("geometry"))
                alt, gc = match.get(fp, (None, None))
                db.execute(
                    "INSERT INTO route_hour_times (tenant_id, route_id, vehicle_profile, leg, hour, rank, depart_at, "
                    "fingerprint, alt_index, geom_computed_at, distance_km, duration_hr, duration_hr_here, error, computed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                    (tenant, rid, profile, leg, hour, rank, dep, fp, alt, gc, opt.get("distance_km"), opt.get("duration_hr"),
                     opt.get("duration_hr_here"), _now()))
            baked += 1
        except Exception as e:
            errors += 1
            calls += 1
            db.execute(
                "INSERT INTO route_hour_times (tenant_id, route_id, vehicle_profile, leg, hour, rank, depart_at, error, "
                "computed_at) VALUES (?, ?, ?, ?, ?, -1, ?, ?, ?)", (tenant, rid, profile, leg, hour, dep, str(e)[:300], _now()))
    return {"profile": profile, "baked": baked, "errors": errors, "attempted": attempted,
            "remaining": max(0, len(todo) - attempted), "here_calls": calls,
            "day": here_routing.bake_departure_time(now=now)[:10], "seconds": round(time.monotonic() - t0, 1)}


def times_for(route_id):
    """
    {profile: {leg: {alt_index: {hour: duration_hr}}}} — the rows whose stored line is still the one they matched, each
    under the number that line has NOW (16 Nov 2026: Make primary renumbers the lines and keeps their computed_at; the
    old join on the number read a swapped option's times against the other line, or dropped both).
    """
    rows = db.query(
        "SELECT vehicle_profile, leg, hour, alt_index, duration_hr, geom_computed_at, fingerprint FROM route_hour_times "
        "WHERE tenant_id = ? AND route_id = ? AND rank >= 0 AND alt_index IS NOT NULL", (db.current_tenant(), route_id))
    if not rows:
        return {}
    lines = _Lines(route_id=route_id)
    out = {}
    for h in rows:
        if h["duration_hr"] is None:
            continue
        alt = lines.alt_now(route_id, h["vehicle_profile"], h["leg"], h)
        if alt is None:
            continue
        out.setdefault(h["vehicle_profile"], {}).setdefault(h["leg"], {}).setdefault(alt, {})[h["hour"]] = \
            float(h["duration_hr"])
    return out


def attach(analysis):
    """
    Add to a network.route_analysis answer, per row, `hours` = {hour: cycle_hr or None} (both legs at that hour plus the
    row's own turnaround) and `hours_scaled` (True where the row is another lorry type on the tipper's road, its legs
    scaled by the tipper's hour-to-pinned ratio). Adds `hour_times` = {hours, screen_hours, profile, worked_out} when
    there are any. Never changes a figure the plan uses.
    """
    if not analysis or analysis.get("error") or not analysis.get("rows"):
        return analysis
    T = times_for(analysis["route_id"])
    if not T:
        analysis["hour_times"] = None
        return analysis
    tip = {(x["alt_index"], x.get("return_alt_used")): x for x in analysis["rows"] if x["profile"] == PROFILE}

    def legs_at(prof, alt, ralt):
        tt = T.get(prof) or {}
        lo = (tt.get("loaded") or {}).get(alt) or {}
        rt = (tt.get("return") or {}).get(ralt if ralt is not None else alt) or {}
        return lo, rt

    for row in analysis["rows"]:
        alt, ralt = row["alt_index"], row.get("return_alt_used")
        hrs, scaled = {}, False
        if row["profile"] in T:
            lo, rt = legs_at(row["profile"], alt, ralt)
            for h in HOURS:
                hrs[h] = (round(lo[h] + rt[h] + (row.get("turnaround_hr") or 0), 3) if h in lo and h in rt else None)
        else:
            t_row = tip.get((alt, ralt))
            same = (t_row is not None and abs((t_row["loaded_km"] or 0) - (row["loaded_km"] or 0)) <= SAME_ROAD_KM
                    and abs((t_row["return_km"] or 0) - (row["return_km"] or 0)) <= SAME_ROAD_KM)
            if same:
                lo, rt = legs_at(PROFILE, alt, ralt)
                for h in HOURS:
                    if h in lo and h in rt and t_row["loaded_hr"] and t_row["return_hr"]:
                        hrs[h] = round(row["loaded_hr"] * lo[h] / t_row["loaded_hr"]
                                       + row["return_hr"] * rt[h] / t_row["return_hr"] + (row.get("turnaround_hr") or 0), 3)
                        scaled = True
                    else:
                        hrs[h] = None
            else:
                hrs = {h: None for h in HOURS}
        row["hours"] = hrs
        row["hours_scaled"] = scaled
    analysis["hour_times"] = {"hours": list(HOURS), "screen_hours": list(SCREEN_HOURS), "profile": PROFILE,
                              "worked_out": status(PROFILE)}
    return analysis


def evidence_block(route_id):
    """
    The collision evidence's "Cycle by hour" (card 4): the tipper's cycle in minutes at every hour, this route and each
    stored alternative HERE ranked (alt 0-2), and the quicker option at each hour (None where fewer than two options
    have a time there, as on the screen).
    None when nothing is worked out for the route.
    """
    import network
    a = attach(network.route_analysis(route_id, profiles=[PROFILE]))
    if not a or a.get("error") or not a.get("hour_times"):
        return None
    series = []
    for row in sorted((x for x in a["rows"] if x["alt_index"] < 10), key=lambda x: x["alt_index"]):
        mins = [(round(row["hours"][h] * 60) if row["hours"].get(h) is not None else None) for h in HOURS]
        if any(v is not None for v in mins):
            series.append({"alt": row["alt_index"],
                           "label": "This route" if row["alt_index"] == 0 else f"Alternative {row['alt_index']}",
                           "minutes": mins})
    if not series:
        return None
    quicker = []
    for k in range(len(HOURS)):
        have = [(s["minutes"][k], i) for i, s in enumerate(series) if s["minutes"][k] is not None]
        quicker.append(min(have)[1] if len(have) > 1 else None)   # "quicker" needs another option to beat (as the screen)
    return {"hours": list(HOURS), "busy": ["08:00", "09:00", "17:00", "18:00"], "series": series, "quicker": quicker,
            "profile": PROFILE, "worked_out": a["hour_times"]["worked_out"]}
