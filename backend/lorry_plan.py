"""
8 Nov 2026 (v2.1 task 2.1-9, mockup notes/drivers-day-fill-mockup-1108 v2 + addendum; John: "YES, AS RECOMMENDED",
Q1–Q14, drag and drop as a later PR).

THE LORRY PLAN: each day-hired lorry's day used to the full. Today every line books its own whole lorries
(derived.day_figures: ceil(loads ÷ trips a lorry a day)), so a line with 7 loads on a route where one lorry makes 6
trips books 2 lorries and the second does 1 trip. This module takes all of ONE day's loads leaving ONE yard (a route's
origin) in ONE kind of lorry and chains them into as few lorry-days as the UK drivers' hours rule allows
(drivers_hours: the shift less the required break, driving at most 9 h), each lorry's round trips listed in the order
the driver does them (runs to the same place kept together, the break placed). Three views:

  booked      each line's own whole lorries, as the grid, the CLP, the gate figures and the cost lines count them;
  chained     each day's loads chained by yard — the same loads on the same days, fewer lorries (Q1–Q3; the default);
  compressed  the week's loads of a yard pooled and chained, then laid over the weekdays round-robin, so a yard's
              part-used last lorry each day becomes one full lorry on fewer days. A SUGGESTION until Apply (Q12):
              apply() writes the moved day quantities into an unconfirmed week's cells through days.set_day (audited),
              a load only ever within its own line and week (Q13; never another line, week or month).

Rules (README "The chaining rule"): one yard and one lorry type per lorry-day (no empty run between yards, no washout
question: the cross-yard case is Pairings, v3/v4); first fit, longest cycle first; the break by drivers_hours; a mixer
line with a planned pour that day is left out of the chaining and its booked lorries kept (Q6: the pour plans them);
a route where not one round trip fits a driver's day is one lorry a trip, never chained; a line typed in vehicles
chains like any other. Flags a compressed move would raise: CAP (a line's own most-a-day) and GATE (a gate's check-in
capacity, from the page's gates_week) are said beside the move; road limits are not re-checked (the words say so).

Money (Q4): lorry-days saved × a DAY-HIRE rate per lorry type typed on Config → Costing · fuel (`day_hire`, blank by
default, never seeded — no public UK rate exists; labelled an estimate). Blank = lorry-days only.

Words (Q8): "Lorry plan", "chained", "free", "room for N more trips", "lorry-days saved", "an estimate". Never
"utilisation", "fill rate", "compliant" (NOT_MODELLED_WORDS say what the figure leaves out) or "movements".
Scope (Q10): the page this is built from is already the caller's (a team its lines only); the sheet says whose it is.
Pure over the page it is given, plus the tenant's locations, routes and gates for the sheets. Wayscope sends nothing.

PR 2 (9 Nov 2026, v2.1 task 2.1-9b, mockup card 9 + Q14; John: "Yes, build it"): A PLANNER'S OWN ARRANGEMENT. A trip
block can be dragged to another lorry of the same yard (chained and compressed) or, in the compressed view, to another
day. move() checks the drop against the same rule (_fits) and refuses in words ("Would pass the 10 h shift by 13 min");
a move that fits is saved per yard and week in the tenanted table `lorry_plan_moves` as the yard's whole arrangement
(each lorry a list of trip references {lk, d}) with a fingerprint of the trips it was made from, and plan() uses it in
place of pack() while that fingerprint still matches (chained: a day at a time; compressed: the yard's week). Once the
loads change the arrangement is simply not used (the words say so); reset() deletes it. Planners and admins only: a
team sees Wayscope's plan of its own lines.
"""
import datetime
import hashlib
import io
import json
import math
import re

import drivers_hours as dh

VIEWS = ("booked", "chained", "compressed")
DEFAULT_VIEW = "chained"
#: the panel's and the sheet's one-sentence rule
RULE_WORDS = ("Each lorry's day: its trips as routed, the break the UK drivers' hours rules require, driving at most "
              "9 h, inside the shift. Chained only for lorries of one type leaving one yard.")
PLANNING_WORDS = ("A planning figure: the loads, their routes and the week's plan do not change; a haulier may fill "
                  "the spare with other work.")
COMPRESS_WORDS = ("A suggestion until Apply: a load moves only within its own line and this week; a pour's mixers stay "
                  "on the pour's day; road limits are not checked again.")
SENDS_NOTHING = "Wayscope sends nothing: download the sheets and hand them to the haulier."
#: Q2: never chained across yards or lorry types
ONE_YARD_WORDS = "One yard and one kind of lorry a lorry-day."
#: PR 2 (card 9): the panel's words when a saved arrangement is in use, and the refusals
ARRANGED_WORDS = ("Your arrangement, kept for this week until its loads change; Reset puts Wayscope's plan back. "
                  "A dropped trip is checked against the same rule first.")
CHANGED_WORDS = "The plan has changed since the page was read: reload and try again."
SAME_DAY_WORDS = "In Chained by yard a trip stays on its day: use Week compressed to move it to another day."
EPS = 1e-6
TABLE = "lorry_plan_moves"


class PlanError(Exception):
    pass


# ----------------------------------------------------------------------------------------------- small helpers
def _f(v, default=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if x == x else default


def _trips(d):
    return int(_f((d.get("derived") or {}).get("trips")))


def _booked(d):
    return int(_f((d.get("derived") or {}).get("vehicles")))


def line_key(l):
    return f"{l.get('route_id')}|{l.get('month_index')}|{l.get('discipline') or ''}|{l.get('section_id') or ''}"


def _weekdays(cw):
    try:
        a = datetime.date.fromisoformat(cw["from"])
    except (KeyError, TypeError, ValueError):
        return []
    return [(a + datetime.timedelta(days=i)).isoformat() for i in range(5)]


def _hm(m):
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


def _minutes_of(hhmm):
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(hhmm or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if 0 <= h < 24 and 0 <= mi < 60 else None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "yard"


def short_name(n):
    return str(n or "").replace(" (fictional)", "")


# ----------------------------------------------------------------------------------------------- day-hire rate
def day_hire_rates(factors):
    """{vehicle type: rate} from Config's `day_hire` block (typed, never seeded). Only positive numbers count."""
    out = {}
    for k, v in (((factors or {}).get("day_hire") or {}).items()):
        if str(k).startswith("_"):
            continue
        x = _f(v, None)
        if x is not None and x > 0:
            out[k] = x
    return out


def day_hire_problem(v, vehicles):
    """None, or the sentence for Config → Costing when `day_hire` is not an object of vehicle type → positive number."""
    if v is None:
        return None
    if not isinstance(v, dict):
        return "Day hire must be an object of vehicle type → a rate a day"
    for k, x in v.items():
        if str(k).startswith("_"):
            continue
        if isinstance(vehicles, dict) and k not in vehicles:
            return f"Day hire names vehicle '{k}', which does not exist"
        if x is None or x == "":
            continue
        if isinstance(x, bool) or not isinstance(x, (int, float)) or x <= 0:
            return f"Day hire for '{k}' must be a positive number (a rate a day), or left blank"
    return None


# ----------------------------------------------------------------------------------------------- the chaining
def _fits(drive, work, add_drive, add_other, shift_min):
    dr, wk = drive + add_drive, work + add_drive + add_other
    if dr > dh.DRIVING_MAX_MIN + EPS:
        return False
    return wk + dh.break_minutes(dr, wk) <= shift_min + EPS


def pack(trips, shift_min):
    """First fit, longest cycle first: trips ({drive, other, cyc, …}) into lorries [{trips, drive, work}]."""
    lorries = []
    for t in sorted(trips, key=lambda x: (-_f(x["cyc"]), str(x.get("route_id")))):
        for L in lorries:
            if _fits(L["drive"], L["work"], _f(t["drive"]), _f(t["other"]), shift_min):
                L["trips"].append(t)
                L["drive"] += _f(t["drive"])
                L["work"] += _f(t["drive"]) + _f(t["other"])
                break
        else:
            lorries.append({"trips": [t], "drive": _f(t["drive"]), "work": _f(t["drive"]) + _f(t["other"])})
    return lorries


def _lorry_rows(lorries, shift_min, start_min):
    """Each packed lorry as the panel's row: trips in the driver's order (same destination together), the break
    placed after the trip that passes 4½ h driving or 6 h work, times from `start_min`, free minutes and the room."""
    rows = []
    for i, L in enumerate(lorries, 1):
        trips = sorted(L["trips"], key=lambda t: (str(t.get("dest_name")), str(t.get("route_id"))))
        br = dh.break_minutes(L["drive"], L["work"])
        t0, dr, wk, placed, blocks = start_min, 0.0, 0.0, False, []
        for t in trips:
            if not placed and br and (dr > dh.DRIVING_BEFORE_BREAK_MIN + EPS or wk > dh.WORK_SHORT_BREAK_AFTER_MIN + EPS):
                blocks.append({"kind": "break", "start": _hm(t0), "minutes": br})
                t0 += br
                placed = True
            blocks.append({"kind": "trip", "route_id": t["route_id"], "dest_id": t.get("dest_id"),
                           "dest_name": t.get("dest_name"), "line_key": t["line_key"], "start": _hm(t0),
                           "minutes": round(_f(t["cyc"]), 1), "qty": t.get("qty"), "unit": t.get("unit"),
                           "material": t.get("material"),
                           # PR 2: the day the trip is booked on and its own driving / other minutes, so a drop can
                           # be checked on the page before the server's answer (the same rule, drivers_hours)
                           "day": t.get("day"), "drive": round(_f(t["drive"]), 1), "other": round(_f(t["other"]), 1)})
            t0 += _f(t["cyc"])
            dr += _f(t["drive"])
            wk += _f(t["drive"]) + _f(t["other"])
        if br and not placed:
            blocks.append({"kind": "break", "start": _hm(t0), "minutes": br})
            t0 += br
        free = max(0.0, shift_min - L["work"] - br)
        shortest = min([_f(t["cyc"]) for t in trips] or [0.0])
        room = int(free // shortest) if shortest > 0 else 0
        places = []
        for t in trips:
            if t.get("dest_name") not in places:
                places.append(t.get("dest_name"))
        rows.append({"n": i, "trips": len(trips), "places": places, "blocks": blocks, "start": _hm(start_min),
                     "end": _hm(t0), "driving_minutes": round(L["drive"], 1), "work_minutes": round(L["work"], 1),
                     "break_minutes": br, "free_minutes": int(round(free)), "room_for": room,
                     "used_pct": int(round(100.0 * (L["work"] + br) / shift_min)) if shift_min > 0 else 0,
                     "free_words": free_words(free, room)})
    return rows


def free_words(free_min, room):
    free_min = int(round(free_min))
    if free_min < 15:
        return "Full day"
    w = f"{free_min // 60} h {free_min % 60:02d} free" if free_min >= 60 else f"{free_min} min free"
    if room > 0:
        w += f" · room for {room} more trip{'' if room == 1 else 's'}"
    return w


# ----------------------------------------------------------------------------------------------- the plan
def _yard_start(oid, origin_gate_id, locs, gbl, factors):
    """Minutes after midnight the yard's lorries leave: its exit gate's opening time, else the default gate hours."""
    try:
        import route_sheet
        import gate_hours
        g = route_sheet._gate_words(locs.get(oid) or {}, "exit", origin_gate_id, gbl.get(oid), factors)
        hrs = g.get("hours")
        if hrs and "–" in hrs:
            m = _minutes_of(hrs.split("–")[0])
            if m is not None:
                return m, g.get("name")
        return _minutes_of(gate_hours.default_hours(factors)["from"]) or 8 * 60, g.get("name")
    except Exception:                                            # noqa: BLE001 — no network tables (a bare page)
        return 8 * 60, None


def _pour_line_days(page):
    """{(line_key, day)} of a planned pour: those mixers are the pour's, not chained (Q6)."""
    out = set()
    for p in page.get("pours") or []:
        if p.get("pour_date"):
            out.add((line_key(p), p["pour_date"]))
    return out


def _collect(page, factors):
    """The week's trips by yard: {(origin_id, vehicle_type): {"name", "vehicle", "days": {d: [trip…]}, "booked": {d: n},
    "kept": {d: n (a pour's mixers, booked as is)}, lines: {line_key: {...}}}} and the lines' own figures."""
    lines = (page.get("commit") or {}).get("lines") or []
    pours = _pour_line_days(page)
    yards, line_info = {}, {}
    for l in lines:
        c = l.get("context") or {}
        if not c.get("baked"):
            continue                                             # no route: one lorry a trip stays the grid's "—"
        cyc_day = int(_f(c.get("cycles_per_vehicle_day")))
        lk = line_key(l)
        oid, vt = c.get("origin_id") or c.get("origin_name") or "?", c.get("vehicle_type") or "?"
        y = yards.setdefault((oid, vt), {"origin_id": c.get("origin_id"), "name": c.get("origin_name") or oid,
                                         "vehicle": vt, "vehicle_short": c.get("vehicle_short") or vt,
                                         "origin_gate_id": None, "days": {}, "booked": {}, "kept": {}, "lines": {}})
        li = line_info.setdefault(lk, {"line_key": lk, "route_id": l.get("route_id"), "month_index": l.get("month_index"),
                                       "discipline": l.get("discipline") or "", "section_id": l.get("section_id") or "",
                                       "unit": l.get("unit") or c.get("unit") or "t", "dest_id": c.get("dest_id"),
                                       "dest_name": c.get("dest_name"), "material": c.get("material_type"),
                                       "yard": (oid, vt), "status": (l.get("week") or {}).get("status"),
                                       "max_per_day": c.get("max_vehicles_per_day"), "cyc_day": cyc_day,
                                       "days": {}, "week_qty": 0.0, "week_trips": 0})
        y["lines"][lk] = li
        for d in l.get("days") or []:
            dd = d.get("day_date")
            if not dd:
                continue
            n, bk, q = _trips(d), _booked(d), _f(d.get("planned_qty"))
            li["days"][dd] = {"trips": n, "booked": bk, "qty": q}
            li["week_qty"] += q
            li["week_trips"] += n
            if n <= 0:
                continue
            y["booked"][dd] = y["booked"].get(dd, 0) + bk
            if (lk, dd) in pours or cyc_day <= 0:
                # a pour's mixers (Q6) and a route whose round trip does not fit a driver's day: kept as booked
                y["kept"][dd] = y["kept"].get(dd, 0) + bk
                continue
            per = q / n if n else 0.0
            trip = {"route_id": l.get("route_id"), "line_key": lk, "dest_id": c.get("dest_id"), "dest_name": c.get("dest_name"),
                    "drive": _f(c.get("drive_min")), "other": _f(c.get("other_work_min")), "cyc": _f(c.get("cycle_min")),
                    "qty": round(per, 2), "unit": li["unit"], "material": c.get("material_type"), "day": dd}
            if trip["cyc"] <= 0:
                trip["cyc"] = trip["drive"] + trip["other"]
            y["days"].setdefault(dd, []).extend([dict(trip) for _ in range(n)])
    return yards, line_info


def _yard_block(y, lorries, shift_min, start_min, gate_name, day, key=None, arranged=None):
    rows = _lorry_rows(lorries, shift_min, start_min)
    loads = sum(r["trips"] for r in rows)
    return {"origin_id": y["origin_id"], "yard_id": (key or (y["origin_id"], y["vehicle"]))[0],
            "name": y["name"], "vehicle": y["vehicle"], "vehicle_short": y["vehicle_short"],
            "gate": gate_name, "day": day, "loads": loads, "booked": y["booked"].get(day, 0),
            "kept": y["kept"].get(day, 0), "lorries": rows, "count": len(rows) + y["kept"].get(day, 0),
            "places": sorted({p for r in rows for p in r["places"] if p}),
            # PR 2: True when this day's lorries are a planner's saved arrangement, not pack()'s
            "arranged": bool(arranged), "moved_by": (arranged or {}).get("moved_by"),
            "moved_at": (arranged or {}).get("moved_at")}


# ----------------------------------------------------------------------------------------------- the arrangement (PR 2)
def pool_fp(trips):
    """A fingerprint of a set of trips: how many of each (line, booked day). The saved arrangement is used only while
    the trips it was made from are exactly these — a typed cell, an Apply or a re-route changes it and the arrangement
    quietly gives way to Wayscope's plan (the words on the panel say so)."""
    counts = {}
    for t in trips:
        k = f"{t['line_key']}|{t.get('day')}"
        counts[k] = counts.get(k, 0) + 1
    raw = "\n".join(f"{k}={counts[k]}" for k in sorted(counts))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _row_id(week_from, view, key):
    return f"{week_from}|{view}|{key[0]}|{key[1]}"


def _saved_rows(week_from):
    """{(view, yard_id, vehicle): {pool_fp, days: {d: {fp, lorries: [[{lk, d}…]…]}}, moved_by, moved_at}} for the week."""
    if not week_from:
        return {}
    try:
        import db
        rows = db.query(f"SELECT view, origin_id, vehicle, pool_fp, lorries_json, moved_by, moved_at FROM {TABLE} "
                        "WHERE tenant_id = ? AND week_from = ?", (db.current_tenant(), week_from))
    except Exception:                                            # noqa: BLE001 — a bare page with no tables
        return {}
    out = {}
    for r in rows:
        try:
            days = json.loads(r.get("lorries_json") or "{}")
        except ValueError:
            continue
        out[(r["view"], r["origin_id"], r["vehicle"])] = {"pool_fp": r.get("pool_fp"), "days": days,
                                                            "moved_by": r.get("moved_by"), "moved_at": r.get("moved_at")}
    return out


def _rebuild(trips, refs_by_lorry):
    """The lorries [[{lk, d}…]…] rebuilt from `trips`: None unless every reference finds a trip and every trip is placed."""
    buckets = {}
    for t in trips:
        buckets.setdefault((t["line_key"], t.get("day")), []).append(t)
    lorries = []
    for refs in refs_by_lorry or []:
        L = {"trips": [], "drive": 0.0, "work": 0.0}
        for ref in refs or []:
            b = buckets.get((ref.get("lk"), ref.get("d")))
            if not b:
                return None
            t = b.pop()
            L["trips"].append(t)
            L["drive"] += _f(t["drive"])
            L["work"] += _f(t["drive"]) + _f(t["other"])
        if L["trips"]:
            lorries.append(L)
    if any(buckets.values()):
        return None
    return lorries


def _yard_lorries(y, view, shift_min, days_, saved=None):
    """
    {day: [lorry…]} for one yard in one view, and which days are the saved arrangement's.
    Chained packs each day on its own; a saved day is used in place of pack() while its own fingerprint matches.
    Compressed packs the week's pool and lays the lorries over the weekdays round-robin, busiest first; the saved
    arrangement is used while the week's fingerprint matches. Returns (per_day, {day: True} of the days arranged).
    """
    per_day, arranged = {d: [] for d in days_}, {}
    if view == "compressed":
        pool = [t for d in days_ for t in (y["days"].get(d) or [])]
        if saved and saved.get("pool_fp") == pool_fp(pool) and set((saved.get("days") or {}).keys()) <= set(days_):
            refs = {d: (saved["days"].get(d) or {}).get("lorries") or [] for d in days_}
            flat = [L for d in days_ for L in refs[d]]
            built = _rebuild(pool, flat)
            if built is not None:
                # _rebuild leaves an empty lorry out, so walk the two lists together by the non-empty ones
                j = 0
                for d in days_:
                    for lorry_refs in refs[d]:
                        if lorry_refs:
                            per_day[d].append(built[j])
                            j += 1
                for d in days_:
                    if per_day[d]:
                        arranged[d] = True
                return per_day, arranged
        packed = sorted(pack(pool, shift_min), key=lambda L: -L["work"]) if pool else []
        for i, L in enumerate(packed):
            per_day[days_[i % len(days_)]].append(L)
        return per_day, arranged
    for d in days_:
        trips = y["days"].get(d) or []
        sd = ((saved or {}).get("days") or {}).get(d)
        if trips and sd and sd.get("fp") == pool_fp(trips):
            built = _rebuild(trips, sd.get("lorries") or [])
            if built is not None:
                per_day[d] = built
                arranged[d] = True
                continue
        per_day[d] = pack(trips, shift_min) if trips else []
    return per_day, arranged


def _refs(per_day, days_, view, y, only=None):
    """The arrangement as saved: {day: {fp (chained), lorries: [[{lk, d}…]…]}}. In the chained view only the days a
    planner has touched are saved (`only`), so the other days stay Wayscope's plan and carry no badge; the compressed
    view is the yard's whole week."""
    out = {}
    for d in days_:
        if only is not None and d not in only:
            continue
        entry = {"lorries": [[{"lk": t["line_key"], "d": t.get("day")} for t in L["trips"]] for L in per_day.get(d) or []]}
        if view == "chained":
            entry["fp"] = pool_fp(y["days"].get(d) or [])
        out[d] = entry
    return out


def _refusal(L, t, shift_min):
    dr = L["drive"] + _f(t["drive"])
    wk = L["work"] + _f(t["drive"]) + _f(t["other"])
    if dr > dh.DRIVING_MAX_MIN + EPS:
        return f"Would pass 9 h of driving by {int(round(dr - dh.DRIVING_MAX_MIN))} min."
    over = wk + dh.break_minutes(dr, wk) - shift_min
    return f"Would pass the {shift_min / 60.0:g} h shift by {int(round(over))} min."


def move(page, body, by=None, now=None, factors=None):
    """
    PR 2 (card 9): one trip of one lorry to another lorry of the same yard (`to_lorry` 1-based), or to another day in
    the compressed view (`to_lorry` 0 = the first lorry of that day that takes it, else a new one). Checked against the
    rule first; a drop that does not fit raises PlanError with the reason. A move that fits saves the yard's whole
    arrangement for the week (replacing the last) and returns where the trip landed.
    body: {view, yard_id, vehicle, line_key, from_day, from_lorry, to_day, to_lorry}.
    """
    import conversions
    factors = factors or conversions.load_factors()
    view = (body or {}).get("view")
    if view not in ("chained", "compressed"):
        raise PlanError("Moves are for the chained or compressed view.")
    cw = page.get("commit_week") or {}
    days_ = _weekdays(cw)
    week_from = cw.get("from")
    shift_h, _capped = dh.shift_hours(factors)
    shift_min = shift_h * 60.0
    yards, _line_info = _collect(page, factors)
    key = (body.get("yard_id"), body.get("vehicle"))
    y = yards.get(key)
    if y is None:
        raise PlanError("That yard is not in this week's plan.")
    fd, td = body.get("from_day"), body.get("to_day")
    if fd not in days_ or td not in days_:
        raise PlanError("That day is not in this week.")
    if view == "chained" and td != fd:
        raise PlanError(SAME_DAY_WORDS)
    saved = _saved_rows(week_from)
    per_day, _arr = _yard_lorries(y, view, shift_min, days_, saved.get((view,) + key))
    try:
        src = per_day[fd][int(body.get("from_lorry")) - 1] if int(body.get("from_lorry")) >= 1 else None
    except (TypeError, ValueError, IndexError):
        src = None
    if src is None:
        raise PlanError(CHANGED_WORDS)
    lk = body.get("line_key")
    t = next((x for x in src["trips"] if x["line_key"] == lk), None)
    if t is None:
        raise PlanError(CHANGED_WORDS)
    try:
        to_l = int(body.get("to_lorry") or 0)
    except (TypeError, ValueError):
        to_l = 0
    if to_l > 0:
        if to_l > len(per_day[td]):
            raise PlanError(CHANGED_WORDS)
        tgt = per_day[td][to_l - 1]
        if tgt is src:
            raise PlanError("The trip is already on that lorry.")
        if not _fits(tgt["drive"], tgt["work"], _f(t["drive"]), _f(t["other"]), shift_min):
            raise PlanError(_refusal(tgt, t, shift_min))
    else:
        tgt = next((L for L in per_day[td] if L is not src and _fits(L["drive"], L["work"], _f(t["drive"]), _f(t["other"]), shift_min)), None)
        if tgt is None:
            if not _fits(0.0, 0.0, _f(t["drive"]), _f(t["other"]), shift_min):
                raise PlanError(_refusal({"drive": 0.0, "work": 0.0}, t, shift_min))
            tgt = {"trips": [], "drive": 0.0, "work": 0.0}
            per_day[td].append(tgt)
    src["trips"].remove(t)
    src["drive"] -= _f(t["drive"])
    src["work"] -= _f(t["drive"]) + _f(t["other"])
    if not src["trips"]:
        per_day[fd].remove(src)
    tgt["trips"].append(t)
    tgt["drive"] += _f(t["drive"])
    tgt["work"] += _f(t["drive"]) + _f(t["other"])
    _save(week_from, view, key, y, per_day, days_, by, now, only=(set(_arr) | {fd, td}) if view == "chained" else None)
    return {"ok": True, "view": view, "day": td, "lorry": per_day[td].index(tgt) + 1,
            "lorries": {d: len(per_day[d]) for d in days_}}


def _save(week_from, view, key, y, per_day, days_, by, now, only=None):
    import db
    import supplier_orders
    tenant = db.current_tenant()
    pool = [t for d in days_ for t in (y["days"].get(d) or [])]
    rid = _row_id(week_from, view, key)
    db.execute_atomic([
        (f"DELETE FROM {TABLE} WHERE tenant_id = ? AND id = ?", (tenant, rid)),
        (f"INSERT INTO {TABLE} (tenant_id, id, week_from, view, origin_id, vehicle, pool_fp, lorries_json, moved_by, moved_at) "
         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
         (tenant, rid, week_from, view, key[0], key[1], pool_fp(pool), json.dumps(_refs(per_day, days_, view, y, only), separators=(",", ":")),
          by, (now or supplier_orders._now()).strftime("%Y-%m-%dT%H:%M"))),
    ])


def reset(week_from, view=None):
    """Delete the week's saved arrangements (one view, or both). Returns {"deleted": n}."""
    import db
    tenant = db.current_tenant()
    if not week_from:
        return {"deleted": 0}
    where, params = f"tenant_id = ? AND week_from = ?", [tenant, week_from]
    if view in ("chained", "compressed"):
        where += " AND view = ?"
        params.append(view)
    n = len(db.query(f"SELECT id FROM {TABLE} WHERE {where}", tuple(params)))
    if n:
        db.execute(f"DELETE FROM {TABLE} WHERE {where}", tuple(params))
    return {"deleted": n}


def plan(page, factors=None, acc=None, now=None):
    """
    The three views for the page's commit week:
      {"week": {from, to, bucket}, "days": [Mon..Fri], "view_default", "shift_hours", "team_only", "made_by",
       "booked": {"by_day": {d: n}, "week": n},
       "chained": {"by_day": {d: n}, "week": n, "days": {d: [yard block…]}, "saved_week": n},
       "compressed": {"by_day": {d: n}, "week": n, "days": {d: [yard block…]}, "saved_week": n, "moves": [...],
                      "lines": {line_key: {route_id, days: {d: {qty_from, qty_to, trips_from, trips_to}}}}, "flags": [...]},
       "day_hire": {"rates": {vehicle: £}, "typed": bool, "chained_eur_week", "compressed_eur_week"},
       "words": {...}}
    Figures are read from the page (derived's trips, vehicles and each line's drive / other-work minutes).
    """
    import conversions
    factors = factors or conversions.load_factors()
    cw = page.get("commit_week") or {}
    days_ = _weekdays(cw)
    shift_h, _capped = dh.shift_hours(factors)
    shift_min = shift_h * 60.0
    yards, line_info = _collect(page, factors)
    try:
        import db
        import gates
        tenant = db.current_tenant()
        locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (tenant,))}
        routes = {r["id"]: r for r in db.query("SELECT id, origin_gate_id FROM routes WHERE tenant_id = ?", (tenant,))}
        gbl = gates.gates_by_location(include_inactive=True)
    except Exception:                                            # noqa: BLE001 — a bare page with no tables
        locs, routes, gbl = {}, {}, {}

    booked_by_day = {d: 0 for d in days_}
    chained = {"by_day": {d: 0 for d in days_}, "days": {d: [] for d in days_}}
    compressed = {"by_day": {d: 0 for d in days_}, "days": {d: [] for d in days_}, "moves": [], "lines": {}, "flags": []}
    saved_by_vehicle = {"chained": {}, "compressed": {}}
    saved = _saved_rows(cw.get("from"))                          # PR 2: the planners' own arrangements for the week
    arranged_yards = {"chained": [], "compressed": []}
    for key, y in sorted(yards.items(), key=lambda kv: (-sum(len(v) for v in kv[1]["days"].values()), kv[1]["name"])):
        og = None
        for li in y["lines"].values():
            og = og or (routes.get(li["route_id"]) or {}).get("origin_gate_id")
        start_min, gate_name = _yard_start(y["origin_id"], og, locs, gbl, factors)
        week_booked = 0
        week_chained = 0
        # chained: day by day (a saved day in place of pack() while its trips are unchanged)
        per_c, arr_c = _yard_lorries(y, "chained", shift_min, days_, saved.get(("chained",) + key))
        if arr_c:
            arranged_yards["chained"].append(y["name"])
        for d in days_:
            booked_by_day[d] += y["booked"].get(d, 0)
            week_booked += y["booked"].get(d, 0)
            if not per_c[d] and not y["kept"].get(d):
                continue
            blk = _yard_block(y, per_c[d], shift_min, start_min, gate_name, d, key,
                              saved.get(("chained",) + key) if arr_c.get(d) else None)
            chained["days"][d].append(blk)
            chained["by_day"][d] += blk["count"]
            week_chained += blk["count"]
        saved_by_vehicle["chained"][y["vehicle"]] = saved_by_vehicle["chained"].get(y["vehicle"], 0) + week_booked - week_chained
        # compressed: the week's trips pooled, packed, then laid over the weekdays round-robin (busiest lorries first);
        # or the saved arrangement of the week while its trips are unchanged
        per_day, arr_x = _yard_lorries(y, "compressed", shift_min, days_, saved.get(("compressed",) + key))
        if arr_x:
            arranged_yards["compressed"].append(y["name"])
        week_comp = 0
        for d in days_:
            if not per_day[d] and not y["kept"].get(d):
                continue
            blk = _yard_block(y, per_day[d], shift_min, start_min, gate_name, d, key,
                              saved.get(("compressed",) + key) if arr_x.get(d) else None)
            compressed["days"][d].append(blk)
            compressed["by_day"][d] += blk["count"]
            week_comp += blk["count"]
        saved_by_vehicle["compressed"][y["vehicle"]] = saved_by_vehicle["compressed"].get(y["vehicle"], 0) + week_booked - week_comp
        # the moves each line would need, with the quantity each day (the week's total kept exactly)
        for lk, li in y["lines"].items():
            new_trips = {d: 0 for d in days_}
            for d in days_:
                for L in per_day[d]:
                    new_trips[d] += sum(1 for t in L["trips"] if t["line_key"] == lk)
            kept_days = {d for d in days_ if (lk, d) in _pour_line_days(page) or li["cyc_day"] <= 0}
            old_trips = {d: li["days"].get(d, {}).get("trips", 0) for d in days_}
            if all(new_trips[d] == old_trips[d] for d in days_ if d not in kept_days):
                continue
            per = (li["week_qty"] / li["week_trips"]) if li["week_trips"] else 0.0
            new_qty, run = {}, 0.0
            movable = [d for d in days_ if d not in kept_days]
            week_movable = sum(li["days"].get(d, {}).get("qty", 0.0) for d in movable)
            last = None
            for d in movable:
                if new_trips[d] > 0:
                    last = d
            for d in movable:
                q = round(new_trips[d] * per, 1) if new_trips[d] else 0.0
                new_qty[d] = q
                run += q
            if last is not None:
                new_qty[last] = round(new_qty[last] + (week_movable - run), 1)
            entry = {"route_id": li["route_id"], "month_index": li["month_index"], "discipline": li["discipline"],
                     "section_id": li["section_id"], "unit": li["unit"], "dest_name": li["dest_name"],
                     "origin_name": y["name"], "status": li["status"], "days": {}}
            for d in movable:
                entry["days"][d] = {"trips_from": old_trips[d], "trips_to": new_trips[d],
                                    "qty_from": round(li["days"].get(d, {}).get("qty", 0.0), 1), "qty_to": new_qty[d]}
                if new_trips[d] != old_trips[d]:
                    flags = []
                    mx = li.get("max_per_day")
                    if mx is not None and new_trips[d] > int(_f(mx)):
                        flags.append(f"CAP: {new_trips[d]} loads, the route's most a day is {int(_f(mx))}")
                    compressed["moves"].append({"line_key": lk, "route_id": li["route_id"], "origin_name": y["name"],
                                                "dest_name": li["dest_name"], "day": d, "trips_from": old_trips[d],
                                                "trips_to": new_trips[d], "qty_from": entry["days"][d]["qty_from"],
                                                "qty_to": new_qty[d], "unit": li["unit"], "flags": flags})
            compressed["lines"][lk] = entry
    # the gate check on the compressed days (the page's gates_week: capacity a day per gate, by destination)
    compressed["flags"] = _gate_flags(page, compressed, line_info, days_)
    for m in compressed["moves"]:
        for f in compressed["flags"]:
            if f["day"] == m["day"] and m["dest_name"] == f.get("location_name"):
                m["flags"].append(f["words"])

    booked_week = sum(booked_by_day.values())
    chained["week"] = sum(chained["by_day"].values())
    compressed["week"] = sum(compressed["by_day"].values())
    chained["saved_week"] = booked_week - chained["week"]
    compressed["saved_week"] = booked_week - compressed["week"]
    rates = day_hire_rates(factors)

    def money(kind):
        if not rates:
            return None
        tot, missing = 0.0, []
        for v, n in saved_by_vehicle[kind].items():
            if v in rates:
                tot += n * rates[v]
            elif n:
                missing.append(v)
        return {"eur": round(tot, 2), "missing": missing}

    team = None
    if acc and acc.get("ipt"):
        try:
            import export
            team = export._team_namer()(acc["ipt"]) or None
        except Exception:                                        # noqa: BLE001
            team = None
    confirmed = [li for li in line_info.values() if li.get("status") == "confirmed"]
    import supplier_orders
    return {
        "week": {"from": cw.get("from"), "to": cw.get("to"), "bucket": page.get("bucket")},
        "days": days_, "view_default": DEFAULT_VIEW, "views": list(VIEWS), "shift_hours": shift_h,
        "shift_minutes": shift_min,                               # PR 2: the page checks a drop against the rule first
        "arranged": arranged_yards,                              # PR 2: the yards shown as a planner arranged them
        "team_only": team, "made_by": supplier_orders.made_by(acc),
        "made_at": (now or supplier_orders._now()).strftime("%d %b %Y %H:%M").lstrip("0"),
        "week_confirmed": bool(line_info) and len(confirmed) == len(line_info),
        "any_confirmed": bool(confirmed),
        "booked": {"by_day": booked_by_day, "week": booked_week},
        "chained": chained, "compressed": compressed,
        "day_hire": {"rates": rates, "typed": bool(rates), "chained": money("chained"), "compressed": money("compressed")},
        "words": {"rule": RULE_WORDS, "planning": PLANNING_WORDS, "compress": COMPRESS_WORDS, "one_yard": ONE_YARD_WORDS,
                  "not_modelled": dh.NOT_MODELLED_WORDS, "sends_nothing": SENDS_NOTHING, "arranged": ARRANGED_WORDS,
                  "estimate": "An estimate at the day-hire rate typed on Config → Costing · fuel."},
    }


def _gate_flags(page, compressed, line_info, days_):
    """GATE: a compressed day's loads into one place would pass a gate's check-in capacity (the page's gates_week)."""
    gw = (page.get("gates_week") or {})
    caps = {}
    for g in gw.get("gates") or []:
        cap = g.get("capacity_per_day")
        if cap is None or not g.get("location_name"):
            continue
        caps[g["location_name"]] = caps.get(g["location_name"], 0.0) + _f(cap)
    if not caps:
        return []
    out = []
    for d in days_:
        into = {}
        for blk in compressed["days"].get(d) or []:
            for r in blk["lorries"]:
                for b in r["blocks"]:
                    if b["kind"] == "trip" and b.get("dest_name"):
                        into[b["dest_name"]] = into.get(b["dest_name"], 0) + 1
        for place, n in into.items():
            if place in caps and n > caps[place] + EPS:
                out.append({"day": d, "location_name": place, "loads": n, "capacity": caps[place],
                            "words": f"GATE: {n} loads into {place}, its gates can check in {int(caps[place])} a day"})
    return out


# ----------------------------------------------------------------------------------------------- apply (Q12)
def apply(page, data, by=None):
    """Write the compressed view's day quantities into the week's cells (days.set_day, one write a changed day).
    Refuses a confirmed week and a week with nothing to move. Returns {"written": n, "lines": n}."""
    import days as _days
    comp = (data or {}).get("compressed") or {}
    lines = comp.get("lines") or {}
    if not lines:
        raise PlanError("Nothing to move: the week is already as full as the chaining allows.")
    for e in lines.values():
        if e.get("status") == "confirmed":
            raise PlanError("This week is confirmed: re-open it to move its loads.")
    written = 0
    for e in lines.values():
        for d, x in sorted(e["days"].items()):
            if abs(_f(x["qty_to"]) - _f(x["qty_from"])) < 0.05:
                continue
            res = _days.set_day(e["route_id"], e["month_index"], e["discipline"], e["section_id"], d, x["qty_to"], by=by)
            if res.get("error"):
                raise PlanError(res["error"])
            written += 1
    return {"written": written, "lines": len(lines)}


# ----------------------------------------------------------------------------------------------- the sheets
def day_view(data, view, day):
    if view not in ("chained", "compressed"):
        raise PlanError("The sheets are for the chained or compressed view.")
    if day not in (data.get("days") or []):
        raise PlanError(f"{day} is not a weekday of the week {data['week'].get('from')} to {data['week'].get('to')}.")
    blocks = (data.get(view) or {}).get("days", {}).get(day) or []
    if not any(b["lorries"] for b in blocks):
        raise PlanError("No lorry to print on that day.")
    return blocks


def _day_words(day):
    d = datetime.date.fromisoformat(day)
    return d.strftime("%A %d %B %Y").replace(" 0", " ")


def build_pdf(data, view, day):
    """Driver sheets: one A4 page a lorry for the day, in the driver's order (export.page_frame)."""
    import export
    from export import (rl_canvas, A4, mm, colors, ParagraphStyle, Paragraph, Spacer, LongTable, TableStyle,
                        NAVY_RGB, GREY, DEMO_FG_RGB, MISSING)
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + MISSING.get("pdf", ""))
    from reportlab.platypus import PageBreak
    blocks = day_view(data, view, day)
    safe = export._pdf_safe
    buf = io.BytesIO()
    W, H = A4
    lm = rm = 12 * mm
    tenant = export._tenant_name() or "Wayscope"
    notice = export._demo_notice() or None
    top, bottom = (27 if notice else 22) * mm, 14 * mm
    title = f"Driver sheets · {_day_words(day)}"
    stamp = "CONFIRMED" if data.get("week_confirmed") else "DRAFT · not confirmed"
    on_page = export.page_frame(
        W, H, lm, rm, safe(title), rule_y=H - 9 * mm, title_font=("Helvetica-Bold", 13), title_y=H - 15 * mm,
        right=(stamp, "Helvetica-Bold", 9, NAVY_RGB),
        sub=("A planning sheet for the haulier · not a delivery note · planning payloads, not plated weights",
             "Helvetica", 8, GREY, H - 19.5 * mm),
        notice=((safe(notice), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 24.5 * mm) if notice else None),
        foot=("Wayscope · " + safe(tenant), "Helvetica", 7, GREY))
    doc = export.frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page)
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=10.5)
    st_h = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.Color(*NAVY_RGB))
    st_g = ParagraphStyle("g", parent=st, fontSize=7.5, leading=9.5, textColor=colors.Color(*GREY))
    st_big = ParagraphStyle("d", parent=st, fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.Color(*NAVY_RGB))
    st_f = ParagraphStyle("f", parent=st, fontSize=10, leading=13)

    def E(v):
        return safe(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def P(t, style=st):
        return Paragraph(str(t), style)

    story = []
    first = True
    for blk in blocks:
        for r in blk["lorries"]:
            if not first:
                story.append(PageBreak())
            first = False
            story.append(P(E(f"{short_name(blk['name'])} · {blk['vehicle']} · lorry {r['n']} of {len(blk['lorries'])}"), st_big))
            story.append(P(f"<b>{E(_day_words(day))}</b> · {r['trips']} round trip{'' if r['trips'] == 1 else 's'} · "
                           f"leave the yard about {r['start']} · back about {r['end']} · {E(r['free_words'].lower())}", st_f))
            if data.get("team_only"):
                story.append(P(E(f"{data['team_only']}'s lines only"), st_g))
            if blk.get("gate"):
                story.append(P(E(f"Load at {short_name(blk['name'])}, leave by {blk['gate']}."), st))
            story.append(Spacer(1, 2 * mm))
            rows = [[P("About", st_h), P("Trip", st_h), P("Load, average", st_h), P("Round trip", st_h)]]
            routes_named = []
            for b in r["blocks"]:
                if b["kind"] == "break":
                    rows.append([P(b["start"]), P(f"<i>Break, {int(b['minutes'])} min, about here: the rules require it after "
                                                 f"4½ h of driving or 6 h of work; it may be taken as 15 + 30.</i>", st_g), P(""), P("")])
                else:
                    rows.append([P(b["start"]),
                                 P(f"<b>{E(b['route_id'])}</b> {E(short_name(blk['name']))} → {E(short_name(b.get('dest_name')))}"
                                   + (f"<br/><font size=7 color='#64748B'>{E(b.get('material') or '')}</font>" if b.get("material") else "")),
                                 P(f"{round(b['qty'], 1):g} {E(supplier_orders_unit(b.get('unit')))}" if b.get("qty") is not None else "—"),
                                 P(f"{int(round(b['minutes']))} min")])
                    if b["route_id"] not in routes_named:
                        routes_named.append(b["route_id"])
            usable = W - lm - rm
            t = LongTable(rows, colWidths=[14 * mm, usable - 14 * mm - 26 * mm - 20 * mm, 26 * mm, 20 * mm], repeatRows=1)
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.Color(*NAVY_RGB)),
                                   ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.Color(0.89, 0.91, 0.94)),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.945, 0.961, 0.976)),
                                   ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            story.append(t)
            story.append(Spacer(1, 3 * mm))
            story.append(P(E(f"Route sheet{'s' if len(routes_named) != 1 else ''} {', '.join(routes_named)} give the roads, the turns "
                             "and the gate hours: follow them, not a sat-nav. Times are planning times; a queue at a gate moves "
                             f"them. Driving at most 9 h today. {dh.NOT_MODELLED_WORDS}"), st_g))
            story.append(P(E(f"Made {data['made_at']} by {data['made_by']}. {SENDS_NOTHING}"), st_g))
    doc.build(story)
    return buf.getvalue()


def supplier_orders_unit(u):
    return {"m3": "m³", "t": "t", "vehicles": "loads"}.get(u or "", u or "")


def build_xlsx(data, view, day):
    """The day's lorries as one sheet: one row a trip (lorry, order, time, route, from, to, load, minutes)."""
    from export import openpyxl, Font, PatternFill, Alignment, get_column_letter, NAVY, MISSING
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + MISSING.get("xlsx", ""))
    import export
    blocks = day_view(data, view, day)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lorry plan"
    head, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=NAVY)
    tenant = export._tenant_name() or "Wayscope"
    ws.cell(row=1, column=1, value=f"{tenant} · lorry plan · {_day_words(day)} · {view} · "
                                   f"{'CONFIRMED' if data.get('week_confirmed') else 'DRAFT, not confirmed'}").font = Font(bold=True, size=13)
    ws.cell(row=2, column=1, value=(f"DEMO · {export._demo_notice()}. " if export._demo_notice() else "") + RULE_WORDS + " " + PLANNING_WORDS)
    ws.cell(row=3, column=1, value=f"Made {data['made_at']} by {data['made_by']}" + (f" · {data['team_only']}'s lines only" if data.get("team_only") else ""))
    cols = ["Yard", "Lorry type", "Lorry", "Order", "About", "Route", "To", "Load", "Unit", "Round trip (min)", "Free (min)"]
    r0 = 5
    for j, c in enumerate(cols, 1):
        x = ws.cell(row=r0, column=j, value=c)
        x.font, x.fill = head, fill
        x.alignment = Alignment(horizontal="center", wrap_text=True)
    i = r0
    for blk in blocks:
        for r in blk["lorries"]:
            k = 0
            for b in r["blocks"]:
                i += 1
                if b["kind"] == "break":
                    vals = [short_name(blk["name"]), blk["vehicle"], r["n"], None, b["start"], "Break", None, None, None, int(b["minutes"]), None]
                else:
                    k += 1
                    vals = [short_name(blk["name"]), blk["vehicle"], r["n"], k, b["start"], b["route_id"], short_name(b.get("dest_name")),
                            b.get("qty"), supplier_orders_unit(b.get("unit")), round(b["minutes"], 1), r["free_minutes"] if k == 1 else None]
                for j, v in enumerate(vals, 1):
                    ws.cell(row=i, column=j, value=v)
    for j, w in enumerate([26, 22, 7, 7, 8, 9, 28, 9, 7, 14, 10], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def file_stem(data, view, day):
    return f"lorry-plan-{day}-{view}"
