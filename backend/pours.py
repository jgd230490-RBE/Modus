"""
pours.py — concrete pours (task 3a, B1 / V5, 29 Oct 2026).

A POUR is a dated event on a ready-mixed concrete LINE (a forecast line planned in m³): a date, the time the first
mixer starts discharging, the volume, the pour rate (m³ an hour: the pump or skip), and optionally the mixers booked
and the wash-out minutes. From the line it takes the route (batching plant → site), the mixer and its m³ a load; from
the route, the drive there and back; from the site's entry gate, the check-in minutes.

THE FIGURES (figures(), pure; John's answers to the mockup's Q1–Q12, 29 Oct 2026, "as recommended")
  loads           ceil(m³ ÷ m³ a load); the last may be a part load
  gap             m³ a load ÷ pour rate × 60 — a mixer every `gap` minutes, and each mixer's DISCHARGE on a pour (Q3:
                  the pump sets it, not the mixer's usual unload minutes)
  cycle           loading + drive there + check-in + discharge + wash-out (typed, blank = 0, Q4) + drive back
  needed          ceil(cycle ÷ gap) mixers keep the pour flowing
  transit         loading + drive there + check-in + discharge: from loading to the end of discharge, no wait
  booked          optional (Q7). Fewer than needed: the real gap is cycle ÷ booked, the pour runs longer and the
                  FACE WAITS (real gap − discharge) between one mixer's last concrete and the next one's first
FLAGS (codes; the screens' words in WORDS)
  POUR_COLD_JOINT red    the face waits longer than the cold-joint gap (planning.pours.cold_joint_min, 30)
  POUR_TRANSIT    red    transit longer than planning.pours.transit_limit_min (120)
  POUR_SHORT      amber  fewer mixers booked than needed, no cold joint: the pour ends later
  POUR_BAND       amber  mixers arriving at the gate in a no-delivery band or one of the gate's shut times (Q8),
                         or (31 Oct 2026, John: "your recommendation") reaching the PLANT's gate to load in one of
                         its no-delivery times — the Simulation holds them there and they reach the site later
  POUR_OVER_PLAN  amber  the line's pours that month add up to more than the line's month (Q5)
No plant output check (John, 29 Oct: "plant output not needed").

THE LIMITS ARE NOT A STANDARD. BS 8500-2 carried "within 2 h after the time of loading" (cl. 14.2) until BS 8500:2023
dropped it; the Concrete Society (Fingertips, 2 Jun 2025) still calls 2 h "a reasonable rule of thumb for a
conventional concrete". The 30 minutes is the Specification for Highway Works Series 1700 cl. 1710.3 (March 2020): fresh
concrete "shall not be placed against in situ concrete that has been in position for more than 30 minutes unless a
construction joint is formed". Both are tenant settings; the specification or the supplier's ticket wins. Sources in the
technical guide (T1) and notes/session-1029-concrete-pours.md §1.

DRIVE TIMES (drive_times()): the route's row for the mixer in the pour's month (derived.cycle_for: a dated diversion
counts), then the busy-hour times (hour_times, 0f) at the hours the mixers set off — the WORST of those hours (Q11) —
where they are worked out; else the planned 10:00 road. `basis` says which.

THE DAY SPLIT (Q5): a pour's m³ comes OUT of its line's month. split_month(): each week = its pours + an even share
(÷ the month's weeks) of what is left; split_days(): a pour day = its pours, the other weekdays share the rest of the
week. weeks.py and days.py call them for DERIVED rows only — an edited or confirmed week or day holds what was typed.
A pour belongs to the month of its WEEK (weeks.week_of_date: the week's Thursday), the Look-ahead's own calendar.
"""
import datetime
import math

import db

TRANSIT_DEFAULT = 120.0
COLD_JOINT_DEFAULT = 30.0
TRANSIT_RANGE = (15.0, 600.0)
COLD_JOINT_RANGE = (5.0, 240.0)
STATUSES = ("planned", "confirmed", "done", "cancelled")
LIVE = ("planned", "confirmed", "done")
MAX_M3 = 20000.0
MAX_RATE = 500.0
MAX_MIXERS = 200
MAX_WASHOUT = 120.0
#: the screens' words for the codes (the Look-ahead's LINE_FLAG_LABEL carries the same)
WORDS = {"POUR_COLD_JOINT": "COLD JOINT", "POUR_TRANSIT": "TRANSIT", "POUR_SHORT": "MIXERS SHORT",
         "POUR_BAND": "IN A BAND", "POUR_OVER_PLAN": "OVER PLAN"}
RED = ("POUR_COLD_JOINT", "POUR_TRANSIT")
CODES = ("POUR_COLD_JOINT", "POUR_TRANSIT", "POUR_SHORT", "POUR_BAND", "POUR_OVER_PLAN")
EPS = 1e-9

_COLS = ("id, route_id, discipline, section_id, month_index, pour_date, start, m3, rate_m3h, mixers_booked, washout_min, "
         "place, method, status, note, created_by, created_at, updated_by, updated_at")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def minutes_of(hhmm):
    """'07:30' -> 450; None for anything else."""
    try:
        h, m = str(hhmm).strip().split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def clock(m):
    """450 -> '07:30'; past midnight '00:30 next day'."""
    m = int(round(m))
    day, r = divmod(m, 1440)
    s = f"{r // 60:02d}:{r % 60:02d}"
    if day > 0:
        s += " next day"
    elif day < 0:
        s += " the day before"
    return s


def hm(minutes):
    """125 -> '2 h 05'; 45 -> '45 min'."""
    m = int(round(minutes))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d}"


# --------------------------------------------------------------------------------------------- the settings
def limits(factors):
    """{transit_min, cold_joint_min} from planning.pours, else the defaults."""
    p = (((factors or {}).get("planning") or {}).get("pours")) or {}
    out = {"transit_min": TRANSIT_DEFAULT, "cold_joint_min": COLD_JOINT_DEFAULT}
    for key, field, (lo, hi) in (("transit_min", "transit_limit_min", TRANSIT_RANGE),
                                 ("cold_joint_min", "cold_joint_min", COLD_JOINT_RANGE)):
        v = p.get(field)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if lo <= v <= hi:
            out[key] = v
    return out


def limits_problem(v):
    """None when planning.pours is valid (or absent), else what is wrong, in words (config.validate)."""
    if v is None:
        return None
    if not isinstance(v, dict):
        return "planning.pours must be an object."
    for field, words, (lo, hi) in (("transit_limit_min", "Loading to the end of discharge", TRANSIT_RANGE),
                                   ("cold_joint_min", "The cold-joint time", COLD_JOINT_RANGE)):
        if field not in v or v[field] in (None, ""):
            continue
        try:
            x = float(v[field])
        except (TypeError, ValueError):
            return f"{words} must be a number of minutes."
        if not lo <= x <= hi:
            return f"{words} must be between {lo:g} and {hi:g} minutes."
    return None


# --------------------------------------------------------------------------------------------- the arithmetic
def figures(m3, rate, start, m3_per_load, load_min, laden_min, check_in, washout, back_min, booked=None,
            transit_limit=TRANSIT_DEFAULT, cold_joint=COLD_JOINT_DEFAULT, bands=None, plant_bands=None,
            plant_check_in=0):
    """
    One pour's figures (minutes; `start` = minutes after midnight the first mixer starts discharging). Pure.
    `bands` = [(from_min, to_min)] when deliveries are barred at the gate (no-delivery bands, the gate's shut times).
    `plant_bands` the same at the plant's gate, `plant_check_in` its check-in: each mixer reaches it loading +
    drive + the plant's check-in before it reaches the site's gate (31 Oct 2026).
    Returns {loads, last_load_m3, gap, discharge, cycle, needed, needed_exact, transit, booked, real_gap, face_wait,
    first_loads, last_arrives, ends, ends_planned, late_by, in_band, in_band_plant, flags: [{code, text}]}.
    """
    m3, rate, m3_per_load = float(m3), float(rate), float(m3_per_load)
    loads = max(1, math.ceil(m3 / m3_per_load - EPS))
    last_load = round(m3 - (loads - 1) * m3_per_load, 3)
    dis = m3_per_load / rate * 60.0
    last_dis = last_load / rate * 60.0
    load_min, laden_min, back_min = float(load_min or 0), float(laden_min or 0), float(back_min or 0)
    check_in, washout = float(check_in or 0), float(washout or 0)
    cycle = load_min + laden_min + check_in + dis + washout + back_min
    needed_exact = cycle / dis
    needed = max(1, math.ceil(needed_exact - EPS))
    transit = load_min + laden_min + check_in + dis
    b = int(booked) if booked not in (None, "") else None
    short = b is not None and 0 < b < needed
    real_gap = cycle / b if short else dis
    face_wait = max(0.0, real_gap - dis)
    last_arrives = start + (loads - 1) * real_gap
    ends = last_arrives + last_dis
    ends_planned = start + (loads - 1) * dis + last_dis
    first_loads = start - check_in - laden_min - load_min
    # the gate sees each mixer check-in minutes before it starts discharging
    at_gate = [start + i * real_gap - check_in for i in range(loads)]
    in_band = sum(1 for t in at_gate if any(a <= (t % 1440) < z for a, z in (bands or [])))
    at_plant = [t - laden_min - load_min - float(plant_check_in or 0) for t in at_gate]
    in_plant = sum(1 for t in at_plant if any(a <= (t % 1440) < z for a, z in (plant_bands or [])))
    flags = []
    if transit > float(transit_limit) + EPS:
        flags.append({"code": "POUR_TRANSIT",
                      "text": f"Loading to the end of discharge takes {hm(transit)}, over the {hm(transit_limit)} limit."})
    if short and face_wait > float(cold_joint) + EPS:
        flags.append({"code": "POUR_COLD_JOINT",
                      "text": f"{b} of {needed} mixers: the face waits {hm(face_wait)} between mixers, over "
                              f"{hm(cold_joint)}."})
    elif short:
        flags.append({"code": "POUR_SHORT",
                      "text": f"{b} of {needed} mixers: the pour ends {clock(ends)}, {hm(ends - ends_planned)} later."})
    if in_band or in_plant:
        mx = lambda n: f"{n} mixer{'s' if n != 1 else ''}"      # noqa: E731
        where = (f"{mx(in_band)} at the gate and {in_plant} at the plant" if in_band and in_plant
                 else f"{mx(in_band)} at the gate" if in_band else f"{mx(in_plant)} at the plant")
        flags.append({"code": "POUR_BAND", "text": f"{where} in a no-delivery time."})
    r1 = lambda x: round(x, 1)      # noqa: E731
    return {"loads": loads, "last_load_m3": last_load, "m3_per_load": m3_per_load, "gap": r1(dis),
            "discharge": r1(dis), "cycle": r1(cycle), "needed": needed, "needed_exact": round(needed_exact, 2),
            "transit": r1(transit), "booked": b, "real_gap": r1(real_gap), "face_wait": r1(face_wait),
            "first_loads": clock(first_loads), "last_arrives": clock(last_arrives), "ends": clock(ends),
            "ends_planned": clock(ends_planned), "late_by": r1(max(0.0, ends - ends_planned)), "in_band": in_band,
            "in_band_plant": in_plant,
            "parts": {"loading": r1(load_min), "there": r1(laden_min), "check_in": r1(check_in),
                      "discharge": r1(dis), "washout": r1(washout), "back": r1(back_min)},
            "start_min": start, "ends_min": r1(ends), "first_loads_min": r1(first_loads),
            "limits": {"transit_min": float(transit_limit), "cold_joint_min": float(cold_joint)},
            "flags": flags}


def worst_flag(flags):
    """The most serious code of a list of flags, or None."""
    for c in CODES:
        if any(f["code"] == c for f in flags or []):
            return c
    return None


# --------------------------------------------------------------------------------------------- the day split
def split_month(quantity, n_weeks, pours_by_week):
    """
    Q5: {week_index: planned} — each week its pours (`pours_by_week` {week_index: m³}) plus an even share of what the
    month has left (÷ n_weeks; the old rule when there are no pours). Pours over the month leave nothing to share.
    """
    q = float(quantity or 0)
    p = {int(w): float(v) for w, v in (pours_by_week or {}).items() if 1 <= int(w) <= n_weeks and v}
    rest = max(0.0, q - sum(p.values()))
    return {w: p.get(w, 0.0) + rest / n_weeks for w in range(1, n_weeks + 1)}


def split_days(planned_qty, dates, pours_by_date, weekday_max=4):
    """
    Q5: {date: planned} — a pour day carries its pours; the week's remainder is shared evenly by the OTHER weekdays
    (every weekday when each one has a pour); weekends 0 unless a pour is on one. `pours_by_date` {date: m³}.
    Without pours this is days.split_week exactly.
    """
    pd = {d: float(v) for d, v in (pours_by_date or {}).items() if d in dates and v}
    wd = [d for d in dates if d.weekday() <= weekday_max]
    rest = max(0.0, float(planned_qty or 0) - sum(pd.values()))
    share_on = [d for d in wd if d not in pd] or wd
    share = rest / len(share_on) if share_on else 0.0
    return {d: pd.get(d, 0.0) + (share if d in share_on else 0.0) for d in dates}


# --------------------------------------------------------------------------------------------- storage
def _row(r):
    d = dict(r)
    for k in ("m3", "rate_m3h", "washout_min"):
        if d.get(k) is not None:
            d[k] = float(d[k])
    if d.get("mixers_booked") is not None:
        d["mixers_booked"] = int(d["mixers_booked"])
    d["month_index"] = int(d["month_index"])
    return d


def _ipt_of(rows):
    """Add each pour's line `ipt` (one read) — what access.filter_lines reads."""
    if not rows:
        return rows
    ipt = {(f["route_id"], int(f["month_index"]), f["discipline"] or "", f["section_id"] or ""): f.get("ipt")
           for f in db.query("SELECT route_id, month_index, discipline, section_id, ipt FROM forecasts WHERE tenant_id = ?",
                             (db.current_tenant(),))}
    for r in rows:
        r["ipt"] = ipt.get((r["route_id"], r["month_index"], r["discipline"] or "", r["section_id"] or ""))
    return rows


def list_pours(from_date=None, to_date=None, route_id=None, include_cancelled=True):
    sql = f"SELECT {_COLS} FROM pours WHERE tenant_id = ?"
    args = [db.current_tenant()]
    if from_date:
        sql += " AND pour_date >= ?"; args.append(str(from_date))
    if to_date:
        sql += " AND pour_date <= ?"; args.append(str(to_date))
    if route_id:
        sql += " AND route_id = ?"; args.append(route_id)
    sql += " ORDER BY pour_date, start, id"
    rows = [_row(r) for r in db.query(sql, tuple(args))]
    if not include_cancelled:
        rows = [r for r in rows if r["status"] in LIVE]
    return _ipt_of(rows)


def get_pour(pour_id):
    rows = db.query(f"SELECT {_COLS} FROM pours WHERE tenant_id = ? AND id = ?", (db.current_tenant(), pour_id))
    return _ipt_of([_row(rows[0])])[0] if rows else None


def by_line(from_month, to_month):
    """{(route_id, discipline, section_id, month_index): {date: m³}} of the live pours in a month window (one read)."""
    out = {}
    for r in db.query("SELECT route_id, discipline, section_id, month_index, pour_date, m3, status FROM pours "
                      "WHERE tenant_id = ? AND month_index BETWEEN ? AND ?",
                      (db.current_tenant(), int(from_month), int(to_month))):
        if r["status"] not in LIVE:
            continue
        k = (r["route_id"], r["discipline"] or "", r["section_id"] or "", int(r["month_index"]))
        d = datetime.date.fromisoformat(str(r["pour_date"]))
        out.setdefault(k, {})
        out[k][d] = out[k].get(d, 0.0) + float(r["m3"] or 0)
    return out


def _next_id():
    n = 0
    for r in db.query("SELECT id FROM pours WHERE tenant_id = ?", (db.current_tenant(),)):
        try:
            n = max(n, int(str(r["id"]).lstrip("P")))
        except ValueError:
            pass
    return f"P{n + 1:03d}"


def _line(route_id, month_index, discipline, section_id):
    rows = db.query("SELECT route_id, month_index, discipline, section_id, quantity, unit, vehicle_type, material_type, "
                    "ipt, status FROM forecasts WHERE tenant_id = ? AND route_id = ? AND month_index = ? "
                    "AND discipline = ? AND section_id = ?",
                    (db.current_tenant(), route_id, int(month_index), discipline or "", section_id or ""))
    return rows[0] if rows else None


def month_of(pour_date):
    """The month a pour belongs to: its week's (the Thursday rule, weeks.week_of_date)."""
    import weeks
    return weeks.week_of_date(pour_date)[0]


def problem(f, factors):
    """None, or what is wrong with a pour's fields, in words. `f` is the whole pour as it would be stored."""
    try:
        d = datetime.date.fromisoformat(str(f.get("pour_date") or ""))
    except ValueError:
        return "The pour needs a date."
    import weeks
    if month_of(d) < 1:
        return "That date is before the programme starts."
    if minutes_of(f.get("start")) is None:
        return "The pour needs a start time such as 07:30."
    for k, words, hi in (("m3", "The volume", MAX_M3), ("rate_m3h", "The pour rate", MAX_RATE)):
        try:
            v = float(f.get(k))
        except (TypeError, ValueError):
            return f"{words} must be a number."
        if not 0 < v <= hi:
            return f"{words} must be above 0 and at most {hi:g}."
    if f.get("mixers_booked") not in (None, ""):
        try:
            b = float(f["mixers_booked"])
        except (TypeError, ValueError):
            return "Mixers booked must be a whole number."
        if b != int(b) or not 1 <= b <= MAX_MIXERS:
            return f"Mixers booked must be a whole number from 1 to {MAX_MIXERS}."
    if f.get("washout_min") not in (None, ""):
        try:
            w = float(f["washout_min"])
        except (TypeError, ValueError):
            return "Wash-out must be a number of minutes."
        if not 0 <= w <= MAX_WASHOUT:
            return f"Wash-out must be between 0 and {MAX_WASHOUT:g} minutes."
    if (f.get("status") or "planned") not in STATUSES:
        return "Status must be planned, confirmed, done or cancelled."
    line = _line(f.get("route_id"), month_of(d), f.get("discipline"), f.get("section_id"))
    if not line:
        return "There is no line on that route in the month of that date."
    if (line.get("unit") or "").lower() not in ("m3", "m³"):
        return "A pour goes on a ready-mixed concrete line planned in m³."
    v = ((factors or {}).get("vehicles") or {}).get(line.get("vehicle_type")) or {}
    if not v.get("payload_m3"):
        return "The line's vehicle carries no m³ a load: choose a concrete mixer on the line first."
    return None


def create_pour(fields, factors, by=None):
    f = {k: fields.get(k) for k in ("route_id", "discipline", "section_id", "pour_date", "start", "m3", "rate_m3h",
                                    "mixers_booked", "washout_min", "place", "method", "status", "note")}
    f["discipline"], f["section_id"] = f.get("discipline") or "", f.get("section_id") or ""
    f["status"] = (f.get("status") or "planned").strip().lower()
    p = problem(f, factors)
    if p:
        return {"error": p}
    d = datetime.date.fromisoformat(str(f["pour_date"]))
    pid = _next_id()
    now = _now()
    db.execute(
        "INSERT INTO pours (tenant_id, id, route_id, discipline, section_id, month_index, pour_date, start, m3, rate_m3h, "
        "mixers_booked, washout_min, place, method, status, note, created_by, created_at, updated_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), pid, f["route_id"], f["discipline"], f["section_id"], month_of(d), d.isoformat(),
         clock(minutes_of(f["start"])), float(f["m3"]), float(f["rate_m3h"]),
         (None if f.get("mixers_booked") in (None, "") else int(float(f["mixers_booked"]))),
         (None if f.get("washout_min") in (None, "") else float(f["washout_min"])),
         ((f.get("place") or "").strip() or None), ((f.get("method") or "").strip() or None), f["status"],
         ((f.get("note") or "").strip() or None), by, now, by, now))
    return get_pour(pid)


EDITABLE = ("pour_date", "start", "m3", "rate_m3h", "mixers_booked", "washout_min", "place", "method", "status", "note")


def update_pour(pour_id, fields, factors, by=None):
    """Partial update: only the keys present are written. The line (route, discipline, section) does not change."""
    cur = get_pour(pour_id)
    if not cur:
        return {"error": "pour not found"}
    nxt = dict(cur)
    for k in EDITABLE:
        if k in fields:
            nxt[k] = fields[k]
    nxt["status"] = (nxt.get("status") or "planned").strip().lower()
    p = problem(nxt, factors)
    if p:
        return {"error": p}
    d = datetime.date.fromisoformat(str(nxt["pour_date"]))
    db.execute(
        "UPDATE pours SET month_index = ?, pour_date = ?, start = ?, m3 = ?, rate_m3h = ?, mixers_booked = ?, "
        "washout_min = ?, place = ?, method = ?, status = ?, note = ?, updated_by = ?, updated_at = ? "
        "WHERE tenant_id = ? AND id = ?",
        (month_of(d), d.isoformat(), clock(minutes_of(nxt["start"])), float(nxt["m3"]), float(nxt["rate_m3h"]),
         (None if nxt.get("mixers_booked") in (None, "") else int(float(nxt["mixers_booked"]))),
         (None if nxt.get("washout_min") in (None, "") else float(nxt["washout_min"])),
         ((nxt.get("place") or "").strip() or None), ((nxt.get("method") or "").strip() or None), nxt["status"],
         ((nxt.get("note") or "").strip() or None), by, _now(), db.current_tenant(), pour_id))
    return get_pour(pour_id)


def delete_pour(pour_id):
    if not get_pour(pour_id):
        return {"error": "pour not found"}
    db.execute("DELETE FROM pours WHERE tenant_id = ? AND id = ?", (db.current_tenant(), pour_id))
    return {"deleted": pour_id}


# --------------------------------------------------------------------------------------------- the reads
def drive_times(route_id, vehicle, month_index, depart_mins, cache=None):
    """
    (there_min, back_min, basis, hours) for a mixer on the route in the month: the busy-hour times at the hours in
    `depart_mins` (each laden departure, minutes after midnight) — the worst cycle of those hours — where worked out,
    else the planned road. basis 'hours' | 'planned' | None (not routed for the mixer: (None, None, None, [])).
    """
    import derived
    import hour_times
    row = derived.cycle_for(route_id, vehicle, cache=cache, month_index=month_index)
    if not row or row.get("loaded_hr") is None or row.get("return_hr") is None:
        return None, None, None, []
    there, back = float(row["loaded_hr"]) * 60.0, float(row["return_hr"]) * 60.0
    try:
        T = hour_times.times_for(route_id)
    except Exception:                 # an old database without the table
        T = {}
    if not T:
        return round(there, 1), round(back, 1), "planned", []
    hours = sorted({min(hour_times.HOURS, key=lambda h: abs(minutes_of(h) - (t % 1440))) for t in depart_mins})
    alt, ralt = row.get("alt_index") or 0, row.get("return_alt_used")
    ralt = alt if ralt is None else ralt

    def legs(prof):
        tt = T.get(prof) or {}
        return ((tt.get("loaded") or {}).get(alt) or {}), ((tt.get("return") or {}).get(ralt) or {})

    lo, rt = legs(vehicle)
    scale_lo = scale_rt = 1.0
    if not lo or not rt:
        tip = derived.cycle_for(route_id, hour_times.PROFILE, cache=cache, month_index=month_index)
        same = (tip is not None and tip.get("loaded_hr") and tip.get("return_hr")
                and abs(float(tip.get("loaded_km") or 0) - float(row.get("loaded_km") or 0)) <= hour_times.SAME_ROAD_KM
                and abs(float(tip.get("return_km") or 0) - float(row.get("return_km") or 0)) <= hour_times.SAME_ROAD_KM)
        if not same:
            return round(there, 1), round(back, 1), "planned", []
        lo, rt = legs(hour_times.PROFILE)
        scale_lo = float(row["loaded_hr"]) / float(tip["loaded_hr"])
        scale_rt = float(row["return_hr"]) / float(tip["return_hr"])
    got = [(lo[h] * scale_lo * 60.0, rt[h] * scale_rt * 60.0, h) for h in hours if h in lo and h in rt]
    if not got:
        return round(there, 1), round(back, 1), "planned", []
    a, b, _h = max(got, key=lambda x: x[0] + x[1])
    return round(a, 1), round(b, 1), "hours", [h for _a, _b, h in got]


def _gate_for(route, locations, gbl, on, end="dest"):
    """The gate a route's mixers use at the site (`end` dest) or at the plant (`end` origin), as the Simulation picks it."""
    import gate_arrivals
    loc = locations.get(route.get(f"{end}_id"))
    if not loc:
        return None
    r, _blocked = gate_arrivals.entry_gate(loc, route.get(f"{end}_gate_id"), gbl.get(loc["id"]) or [], on=on)
    gid = r.get("gate_id")
    for g in gbl.get(loc["id"]) or []:
        if g.get("id") == gid:
            return g
    return None


def _bands(gate, factors):
    import gate_hours
    out = [(gate_hours.minutes_of(b["from"]), gate_hours.minutes_of(b["to"])) for b in gate_hours.peak_bands(factors)]
    if gate:
        try:
            for w in gate_hours.shut_windows(gate) or []:
                out.append((gate_hours.minutes_of(w["from"]), gate_hours.minutes_of(w["to"])))
        except Exception:
            pass
    return [(a, z) for a, z in out if a is not None and z is not None and z > a]


def decorate(rows, factors=None, cache=None, exclude_ids=()):
    """Each pour + its line's words, its gate, the drive times and figures(); OVER PLAN across a line's month.
    A row marked `_preview` (preview()) counts its own m³ in its line's month; `exclude_ids` (the stored pour it stands
    for) are left out of the sums."""
    import conversions
    import gates as _gates
    factors = factors or conversions.load_factors()
    lim = limits(factors)
    cache = {} if cache is None else cache
    routes = {r["id"]: r for r in db.query(
        "SELECT id, origin_id, dest_id, origin_gate_id, dest_gate_id FROM routes WHERE tenant_id = ?",
        (db.current_tenant(),))}
    # 31 Oct 2026: the position too — a plant with no gate row resolves to its own point (gates.resolve)
    locations = {l["id"]: l for l in db.query("SELECT id, name, loc_type, lat, lon, gate_lat, gate_lon FROM locations "
                                              "WHERE tenant_id = ?", (db.current_tenant(),))}
    gbl = _gates.gates_by_location()
    lines = {(f["route_id"], int(f["month_index"]), f["discipline"] or "", f["section_id"] or ""): f
             for f in db.query("SELECT route_id, month_index, discipline, section_id, quantity, unit, vehicle_type, "
                               "material_type, material_description, ipt, status FROM forecasts WHERE tenant_id = ?",
                               (db.current_tenant(),))}
    month_sum = {}
    for p in list_pours(include_cancelled=False):
        if p["id"] in (exclude_ids or ()):
            continue
        k = (p["route_id"], p["month_index"], p["discipline"] or "", p["section_id"] or "")
        month_sum[k] = month_sum.get(k, 0.0) + float(p["m3"])
    for p in rows:
        if p.get("_preview") and p.get("status") in LIVE:
            k = (p["route_id"], p["month_index"], p["discipline"] or "", p["section_id"] or "")
            month_sum[k] = month_sum.get(k, 0.0) + float(p["m3"])
    out = []
    for p in rows:
        p = dict(p)
        k = (p["route_id"], p["month_index"], p["discipline"] or "", p["section_id"] or "")
        line = lines.get(k) or {}
        route = routes.get(p["route_id"]) or {}
        veh = line.get("vehicle_type")
        vrow = ((factors.get("vehicles") or {}).get(veh)) or {}
        d = datetime.date.fromisoformat(p["pour_date"])
        gate = _gate_for(route, locations, gbl, d) if route else None
        plant_gate = _gate_for(route, locations, gbl, d, end="origin") if route else None
        start = minutes_of(p["start"]) or 0
        m3pl = float(vrow.get("payload_m3") or 0)
        p["origin_name"] = (locations.get(route.get("origin_id")) or {}).get("name")
        p["dest_name"] = (locations.get(route.get("dest_id")) or {}).get("name")
        p["gate_name"] = (gate or {}).get("name")
        p["plant_gate_name"] = (plant_gate or {}).get("name")
        p["vehicle"] = veh
        p["vehicle_name"] = conversions.vehicle_label(factors, veh) if veh else None
        p["line_m3"] = float(line.get("quantity") or 0) if line else None
        p["line_description"] = line.get("material_description")
        p["line_status"] = line.get("status")
        p["figures"], p["basis"], p["flags"] = None, None, []
        if not m3pl:
            p["problem"] = "The line's vehicle carries no m³ a load."
            out.append(p)
            continue
        import network
        load_m, _unload = network._turnaround_minutes(veh, factors)
        gap = m3pl / float(p["rate_m3h"]) * 60.0
        loads = max(1, math.ceil(float(p["m3"]) / m3pl - EPS))
        # the laden departures at the planned road's drive time (enough to pick the busy hours)
        there0, _b0, basis0, _h0 = drive_times(p["route_id"], veh, p["month_index"], [start], cache=cache)
        if there0 is None:
            p["problem"] = "The route is not routed for the line's mixer yet."
            p["basis"] = None
            out.append(p)
            continue
        chk = float((gate or {}).get("safety_minutes") or 0)
        departs = [start + i * gap - chk - there0 for i in range(loads)]
        there, back, basis, hrs = drive_times(p["route_id"], veh, p["month_index"], departs, cache=cache)
        fig = figures(p["m3"], p["rate_m3h"], start, m3pl, load_m, there, chk, p.get("washout_min") or 0, back,
                      booked=p.get("mixers_booked"), transit_limit=lim["transit_min"], cold_joint=lim["cold_joint_min"],
                      bands=_bands(gate, factors), plant_bands=_bands(plant_gate, factors) if plant_gate else None,
                      plant_check_in=float((plant_gate or {}).get("safety_minutes") or 0))
        flags = list(fig.pop("flags"))
        if line and month_sum.get(k, 0.0) > float(line.get("quantity") or 0) + 1e-6 and p["status"] in LIVE:
            flags.append({"code": "POUR_OVER_PLAN",
                          "text": f"The pours this month on this line add up to {month_sum[k]:g} m³, more than the "
                                  f"line's {float(line.get('quantity') or 0):g} m³."})
        if p["status"] not in LIVE:
            flags = []
        p["figures"], p["basis"], p["basis_hours"], p["flags"] = fig, basis, hrs, flags
        p["worst"] = worst_flag(flags)
        out.append(p)
    return out


def preview(fields, factors, exclude_id=None):
    """
    The figures of a pour as typed, nothing saved (the Pours form asks as it is typed): {error} or the decorated pour.
    `exclude_id` = the stored pour being edited, left out of OVER PLAN's sum (the typed one counts instead).
    """
    f = {k: fields.get(k) for k in ("route_id", "discipline", "section_id", "pour_date", "start", "m3", "rate_m3h",
                                    "mixers_booked", "washout_min", "place", "status")}
    f["discipline"], f["section_id"] = f.get("discipline") or "", f.get("section_id") or ""
    f["status"] = (f.get("status") or "planned").strip().lower()
    p = problem(f, factors)
    if p:
        return {"error": p}
    d = datetime.date.fromisoformat(str(f["pour_date"]))
    row = {"id": None, "route_id": f["route_id"], "discipline": f["discipline"], "section_id": f["section_id"],
           "month_index": month_of(d), "pour_date": d.isoformat(), "start": clock(minutes_of(f["start"])),
           "m3": float(f["m3"]), "rate_m3h": float(f["rate_m3h"]),
           "mixers_booked": None if f.get("mixers_booked") in (None, "") else int(float(f["mixers_booked"])),
           "washout_min": None if f.get("washout_min") in (None, "") else float(f["washout_min"]),
           "place": f.get("place"), "status": f["status"], "_preview": True}
    return decorate([row], factors, exclude_ids=(exclude_id,) if exclude_id else ())[0]


def page(acc=None, from_date=None, to_date=None, factors=None):
    """The Pours page: every pour this caller may see, decorated, with the limits. Newest first is the screen's job."""
    import access
    import conversions
    factors = factors or conversions.load_factors()
    rows = access.filter_lines(list_pours(from_date, to_date), acc)
    return {"pours": decorate(rows, factors), "limits": limits(factors), "words": WORDS, "statuses": list(STATUSES)}


def line_choices(acc=None, factors=None):
    """The lines a pour can go on: m³ lines whose vehicle has an m³ load, one row per (route, discipline, section),
    with the months they run (for the Add pour form)."""
    import access
    import conversions
    factors = factors or conversions.load_factors()
    vs = factors.get("vehicles") or {}
    names = {l["id"]: l["name"] for l in db.query("SELECT id, name FROM locations WHERE tenant_id = ?",
                                                   (db.current_tenant(),))}
    routes = {r["id"]: r for r in db.query("SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?",
                                           (db.current_tenant(),))}
    rows = access.filter_lines(db.query(
        "SELECT route_id, month_index, discipline, section_id, unit, vehicle_type, material_description, ipt, status "
        "FROM forecasts WHERE tenant_id = ? ORDER BY route_id, month_index", (db.current_tenant(),)), acc)
    out = {}
    for r in rows:
        if (r.get("unit") or "").lower() not in ("m3", "m³") or not (vs.get(r.get("vehicle_type")) or {}).get("payload_m3"):
            continue
        k = (r["route_id"], r["discipline"] or "", r["section_id"] or "")
        rt = routes.get(r["route_id"]) or {}
        e = out.setdefault(k, {"route_id": r["route_id"], "discipline": r["discipline"] or "",
                               "section_id": r["section_id"] or "", "description": r.get("material_description"),
                               "origin_name": names.get(rt.get("origin_id")), "dest_name": names.get(rt.get("dest_id")),
                               "vehicle_name": conversions.vehicle_label(factors, r.get("vehicle_type")),
                               "months": []})
        e["months"].append(int(r["month_index"]))
    return list(out.values())


def flags_for_lines(lines, from_date, to_date, factors=None, cache=None):
    """
    The Look-ahead rail's pour flags for the decorated lines of a week: one flag per (line, pour) with `day_date`, the
    clashes._flag shape, the pour's own sentence. Cancelled pours raise none.
    """
    import clashes
    keys = {clashes.line_key(l): l for l in lines or []}
    rows = [p for p in list_pours(from_date, to_date, include_cancelled=False)]
    out = []
    for p in decorate(rows, factors, cache=cache):
        l = keys.get((p["route_id"], p["month_index"], p["discipline"] or "", p["section_id"] or ""))
        if l is None:
            continue
        where = p.get("place") or "Pour"
        for f in p["flags"]:
            out.append(clashes._flag(f["code"], l, f"{where}, {p['pour_date']}: {f['text']}", day_date=p["pour_date"],
                                     pour_id=p["id"]))
    return out


def day_pours(lines, from_date, to_date):
    """{line_key: {date: [{id, place, m3, start}]}} — the pours on each line's days, for the grid's POUR mark."""
    import clashes
    keys = {clashes.line_key(l) for l in lines or []}
    out = {}
    for p in list_pours(from_date, to_date, include_cancelled=False):
        k = (p["route_id"], p["month_index"], p["discipline"] or "", p["section_id"] or "")
        if k in keys:
            out.setdefault(k, {}).setdefault(p["pour_date"], []).append(
                {"id": p["id"], "place": p.get("place"), "m3": p["m3"], "start": p["start"], "status": p["status"]})
    return out
