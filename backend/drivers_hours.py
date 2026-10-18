"""
drivers_hours.py — a lorry's working day under the UK drivers' hours rules. Wayscope, 17 Oct 2026.

THE ASK (the user, 17 Oct 2026): "regards driving hours please use uk rules" — then "a lorry's day is Shift hours a day
less the breaks the rules require, with driving capped at 9 h". Sources checked on gov.uk and legislation.gov.uk the same
day (notes/drivers-hours-1017.md, and the review the same night): a construction tipper, eight-wheeler, flatbed or
concrete mixer over 3.5 t on the public road is under the ASSIMILATED rules (Regulation (EC) 561/2006 as it has effect in
the UK) with a tachograph, and its driver under the Road Transport (Working Time) Regulations 2005 (SI 2005/639). The one
GB derogation near this work — road maintenance and control, which moves a vehicle to the GB domestic rules — is about
maintaining existing roads and is not modelled.

THE RULE, IN ONE PLACE (network.route_analysis, the public map's route figures, the Carbon planner's swapped routes and
its electric day all call it; nothing works trips a lorry a day out a second way)
------------------------------------------------------------------------------------------------------------------------
* ONE DRIVER A LORRY A DAY. The day is Shift hours a day (Config → Planning, 10 h untyped), read as at most SHIFT_MAX_H
  (13 h: a driver's daily rest is 11 hours in every 24, Art 8; the reduced 9 h rest is not assumed). A longer shift is
  allowed on Config (a lorry can be double-shifted, and the field is also a gate's stand-in open window); the trips a
  lorry makes are worked out on one driver's 13 h, and the Routes page says so.
* A cycle is DRIVING (both legs as routed — haul roads and gate access roads are inside them — plus gate-to-face travel)
  and OTHER WORK (loading, unloading, the gate check-in). gov.uk: off-road driving between rest periods counts toward
  the daily driving limit (it is recorded as other work); counting it toward the 4.5 h break trigger too is cautious.
* n trips need n × the cycle plus the breaks: 45 min once driving passes 4.5 h (Art 7) or working time passes 9 h (2005
  Regs reg 7(3)), else 30 min once working time passes 6 h (reg 7(2)), else none — ONE break, the 45 covering the 30;
  and since no more than 6 h of work may run without a break (reg 7(1)), working time over 12 h needs a second break of
  at least 15 min (reg 7(4)): 60 min in all. "Passes" is strictly more than ("exceeds", reg 7; Art 7's break is due
  after a driving period of 4.5 h, and a day of exactly 4.5 h driving that then stops needs none).
* Driving is at most DRIVING_MAX_MIN (9 h a day, Art 6(1); the twice-a-week 10 h is not assumed).
* An electric lorry's charging is attended, so it is WORKING TIME (reg 2): it comes on top of the break and counts when
  the break is chosen.
* Trips a lorry a day = the largest n that fits. It can be 0: one round trip that does not fit a driver's day — every
  reader then counts one lorry a trip (a planning floor) and says so.
NOT MODELLED (NOT_MODELLED_WORDS, said wherever the figure is explained): the weekly limits (56 h driving, 90 h in two
weeks; 60 h working time in a week, 48 h average), night work, the 10 h driving day, the reduced daily rest, where the
break falls in the day, a second driver on the lorry, and the day's other duties (the vehicle check, the run from the
yard to the first load and back, refuelling, queues). A planning figure, not a check of anyone's hours. UK only: before
a tenant outside the UK, raise it with the user.

Pure: no database read, no write.
"""

#: Reg 561/2006 (assimilated) Art 6(1): daily driving time 9 hours
DRIVING_MAX_MIN = 540.0
#: Art 7: after a driving period of 4.5 hours, a break of at least 45 minutes
DRIVING_BEFORE_BREAK_MIN = 270.0
BREAK_LONG_MIN = 45.0
#: Road Transport (Working Time) Regulations 2005 (SI 2005/639) reg 7: work over 6 h, 30 min; over 9 h, 45 min; no more
#: than 6 h of work without a break, so work over 12 h needs a second break (each at least 15 min, reg 7(4))
WORK_SHORT_BREAK_AFTER_MIN = 360.0
WORK_LONG_BREAK_AFTER_MIN = 540.0
WORK_SECOND_BREAK_AFTER_MIN = 720.0
BREAK_SHORT_MIN = 30.0
BREAK_SECOND_MIN = 15.0
#: Art 8: a daily rest of 11 hours in every 24 leaves one driver a working day of at most 13 hours
SHIFT_MAX_H = 13.0
SHIFT_DEFAULT_H = 10.0
#: minutes treated as equal (float dust between figures that are equal on paper)
EPS = 1e-6

#: the words every screen and export uses for the rule (one break: the 45 covers the 30)
RULE_WORDS = ("the shift less the break the UK drivers' hours rules require (45 min once driving passes 4½ h or work "
              "passes 9 h, otherwise 30 min once work passes 6 h), with driving at most 9 h")
#: one sentence for what the figure leaves out — the same on every surface
NOT_MODELLED_WORDS = ("A planning figure, not a check of anyone's hours: weekly limits, night work, the 10-hour driving "
                      "day, the reduced daily rest, where the break falls in the day, a second driver on the lorry and "
                      "the day's other duties (vehicle check, the run from the yard, refuelling, queues) are not modelled.")
LIMIT_WORDS = {
    "shift": "as many round trips as fit in the shift",
    "driving": "capped by the 9 h a day driving limit",
    "driver_day": "as many as fit in one driver's 13 h day (the typed shift is longer)",
    "none": "one round trip does not fit in a driver's day: counted as one lorry a trip",
}


def shift_hours(factors):
    """Shift hours a day as typed (Config → Planning), SHIFT_DEFAULT_H when untyped or not a positive number, read as at
    most SHIFT_MAX_H for one driver. Returns (hours used, capped: bool)."""
    h = typed_shift_hours(factors)
    return (SHIFT_MAX_H, True) if h > SHIFT_MAX_H + EPS else (h, False)


def typed_shift_hours(factors):
    """Shift hours a day as typed, SHIFT_DEFAULT_H when untyped or not a positive number (no cap)."""
    v = ((factors or {}).get("planning") or {}).get("shift_hours_per_day")
    try:
        h = float(v if v is not None else SHIFT_DEFAULT_H)
    except (TypeError, ValueError):
        h = SHIFT_DEFAULT_H
    return h if h > 0 else SHIFT_DEFAULT_H


def shift_note(factors):
    """Words when the typed shift is longer than one driver's day (None otherwise) — for the Routes page and Config."""
    h, capped = shift_hours(factors)
    if not capped:
        return None
    return (f"The {typed_shift_hours(factors):g} h shift is read as {SHIFT_MAX_H:g} h for a lorry's trips: one driver's "
            f"day (the 11-hour daily rest).")


def break_minutes(driving_min, work_min):
    """The breaks a day of `driving_min` driving and `work_min` working time needs (minutes): 45 once driving passes 4.5 h
    or work passes 9 h, else 30 once work passes 6 h, else 0 — never the 45 and the 30 added — plus a second break of 15
    once work passes 12 h (no more than 6 h of work without a break)."""
    if driving_min > DRIVING_BEFORE_BREAK_MIN + EPS or work_min > WORK_LONG_BREAK_AFTER_MIN + EPS:
        b = BREAK_LONG_MIN
    elif work_min > WORK_SHORT_BREAK_AFTER_MIN + EPS:
        b = BREAK_SHORT_MIN
    else:
        b = 0.0
    if work_min > WORK_SECOND_BREAK_AFTER_MIN + EPS:
        b += BREAK_SECOND_MIN
    return b


def fits(n, drive_min, other_min, shift_min, extra_min=0.0):
    """True when n round trips (each `drive_min` driving + `other_min` other work) fit a driver's day of `shift_min`:
    driving at most 9 h, and the trips, `extra_min` (an electric lorry's charging — attended, so working time) and the
    breaks inside it."""
    driving, work = n * drive_min, n * (drive_min + other_min) + extra_min
    if driving > DRIVING_MAX_MIN + EPS:
        return False
    return work + break_minutes(driving, work) <= shift_min + EPS


def _clean(v):
    try:
        f = float(v or 0.0)
    except (TypeError, ValueError):
        f = 0.0
    return f if f > 0 else 0.0


def _start(shift_min, drive_min, cycle):
    """The largest n worth trying: what the shift alone holds, and no more than the 9 h driving cap allows."""
    plain = int((shift_min + EPS) // cycle) if cycle > 0 else 0
    if drive_min > 0:
        plain = min(plain, int((DRIVING_MAX_MIN + EPS) // drive_min))
    return plain


def lorry_day(shift_h, drive_min, other_min, typed_shift_h=None):
    """
    One lorry's day on a route: {trips, limited_by, break_minutes, driving_minutes, work_minutes, shift_hours,
    cycle_minutes, trips_without_rules}. `trips` = the largest n that fits (fits()). `trips_without_rules` = the old
    floor(shift ÷ cycle) on the shift as TYPED (`typed_shift_h`, default `shift_h`), kept so a figure that moved can say
    why. `limited_by`: 'shift' (the rules took nothing off), 'driving' (fewer, and one more would pass the 9 h driving
    cap), 'driver_day' (fewer only because the typed shift is longer than one driver's 13 h), 'breaks' (fewer because of
    the required breaks) or 'none' (not one round trip fits). `shift_h` is used as given (shift_hours() caps it).
    """
    drive_min, other_min = _clean(drive_min), _clean(other_min)
    shift_min = float(shift_h) * 60.0
    cycle = drive_min + other_min
    plain = (int((float(typed_shift_h if typed_shift_h is not None else shift_h) * 60.0 + EPS) // cycle)
             if cycle > 0 else 0)
    n = _start(shift_min, drive_min, cycle)
    while n > 0 and not fits(n, drive_min, other_min, shift_min):
        n -= 1
    plain_here = int((shift_min + EPS) // cycle) if cycle > 0 else 0
    if n <= 0:
        limited = "none"
    elif n >= plain:
        limited = "shift"
    elif (n + 1) * drive_min > DRIVING_MAX_MIN + EPS:
        limited = "driving"
    elif n >= plain_here:
        limited = "driver_day"          # the typed shift is longer than one driver's 13 h: the cap took them, not a break
    else:
        limited = "breaks"
    driving, work = n * drive_min, n * cycle
    return {"trips": n, "limited_by": limited, "break_minutes": (break_minutes(driving, work) if n else 0.0),
            "driving_minutes": driving, "work_minutes": work, "shift_hours": float(shift_h),
            "cycle_minutes": cycle, "trips_without_rules": plain}


def ev_trips(shift_h, drive_min, other_min, charge_minutes_for):
    """
    An electric lorry's day: the largest n whose trips, charging (`charge_minutes_for(n)`, the battery simulated trip by
    trip in carbon.ev_day) and breaks fit, driving at most 9 h. Charging is attended, so it is working time: it comes ON
    TOP of the break and counts when the break is chosen (the cautious reading) — the Carbon planner says so. The cheap
    tests run before the battery is simulated. Returns n (0 when not one trip fits).
    """
    drive_min, other_min = _clean(drive_min), _clean(other_min)
    shift_min = float(shift_h) * 60.0
    n = _start(shift_min, drive_min, drive_min + other_min)
    while n > 0:
        if fits(n, drive_min, other_min, shift_min) and fits(n, drive_min, other_min, shift_min,
                                                              extra_min=charge_minutes_for(n)):
            return n
        n -= 1
    return 0


def split_cycle(loaded_hr, return_hr, turnaround_parts):
    """(driving minutes, other-work minutes) of one cycle from route_analysis's figures: both legs as routed plus the
    gate-to-face travel are driving; loading, unloading and the gate check-in are other work."""
    p = turnaround_parts or {}
    internal = float(p.get("internal_travel_minutes") or 0.0)
    other = float(p.get("unloading_minutes") or 0.0) + float(p.get("safety_minutes") or 0.0)
    drive = (float(loaded_hr or 0.0) + float(return_hr or 0.0)) * 60.0 + internal
    return drive, other


def words(day):
    """'5 a day: 1 fewer than the shift alone would hold: the required break takes the time (45 min break)' — for a title
    or a footnote."""
    if not day:
        return None
    if not day.get("trips"):
        return LIMIT_WORDS["none"][0].upper() + LIMIT_WORDS["none"][1:]
    lim = day.get("limited_by")
    if lim == "breaks":
        k = int(day.get("trips_without_rules") or 0) - int(day["trips"])
        what = f"{k} fewer than the shift alone would hold: the required break" + (" takes the time" if k else "")
    else:
        what = LIMIT_WORDS.get(lim, "")
    brk = day.get("break_minutes") or 0
    return f"{day['trips']} a day: {what}" + (f" ({brk:g} min break)" if brk else "")


if __name__ == "__main__":       # a quick look: python drivers_hours.py
    for d, o in ((60, 0), (69, 24), (45, 24), (138, 24), (84, 20), (15, 5)):
        r = lorry_day(10, d, o)
        print(d, o, r["trips"], r["limited_by"], r["break_minutes"], r["trips_without_rules"], words(r))
