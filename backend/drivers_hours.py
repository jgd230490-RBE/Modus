"""
drivers_hours.py — a lorry's working day under the UK drivers' hours rules. Wayscope, 17 Oct 2026.

THE ASK (the user, 17 Oct 2026): "regards driving hours please use uk rules" — then "a lorry's day is Shift hours a day
less the breaks the rules require, with driving capped at 9 h". Sources checked on gov.uk and legislation.gov.uk the same
day (notes/drivers-hours-1017.md): a construction tipper, eight-wheeler, flatbed or concrete mixer over 3.5 t on the public
road is under the ASSIMILATED rules (Regulation (EC) 561/2006 as it has effect in the UK) with a tachograph, and its driver
under the Road Transport (Working Time) Regulations 2005. No GB derogation covers construction haulage.

THE RULE, IN ONE PLACE (network.route_analysis, the public map's route figures, the Carbon planner's swapped routes and
its electric day all call lorry_day(); nothing works trips a lorry a day out a second way)
------------------------------------------------------------------------------------------------------------------------
* The DAY is Shift hours a day (Config → Planning), at most SHIFT_MAX_H (13 h: the driver's daily rest is 11 hours in
  every 24, Art 8; the reduced 9 h rest is not assumed). A longer figure is refused on Config and capped here.
* A cycle is DRIVING (both legs as routed — haul roads and gate access roads are inside them — plus gate-to-face travel:
  the tachograph records any movement as driving) and OTHER WORK (loading, unloading, the gate check-in).
* n trips need n × the cycle, plus ONE break: 45 min once driving passes 4.5 h (Art 7) or working time passes 9 h (2005
  Regs reg 5), else 30 min once working time passes 6 h, else none. The 45-minute break satisfies the 30-minute one, so
  they are never added. "Passes" is strictly more than (driving of exactly 4.5 h needs no break before the day ends).
* Driving is at most DRIVING_MAX_MIN (9 h a day, Art 6; the twice-a-week 10 h is not assumed).
* Trips a lorry a day = the largest n that fits both. It can be 0: one round trip that does not fit a driver's day.
NOT MODELLED (said wherever the figure is explained): the weekly limits (56 h driving, 90 h in two weeks; 60 h working
time in a week, 48 h average), night work (10 h working time), GB domestic rules for vehicles exempt from the assimilated
rules. A planning figure, not a check of anyone's tachograph. UK only: before a tenant outside the UK, raise it with the
user (the same numbers may hold under EU law, unverified here).

Pure: no database read, no write.
"""


#: Reg 561/2006 (assimilated) Art 6(1): daily driving time 9 hours
DRIVING_MAX_MIN = 540.0
#: Art 7: after 4.5 hours of driving, a break of at least 45 minutes
DRIVING_BEFORE_BREAK_MIN = 270.0
BREAK_LONG_MIN = 45.0
#: Road Transport (Working Time) Regulations 2005 reg 5: more than 6 h of work, 30 min; more than 9 h, 45 min
WORK_SHORT_BREAK_AFTER_MIN = 360.0
WORK_LONG_BREAK_AFTER_MIN = 540.0
BREAK_SHORT_MIN = 30.0
#: Art 8: a daily rest of 11 hours in every 24 leaves a working day of at most 13 hours
SHIFT_MAX_H = 13.0
SHIFT_DEFAULT_H = 10.0
#: minutes treated as equal (float dust between figures that are equal on paper)
EPS = 1e-6

#: the words every screen and export uses for the rule
RULE_WORDS = ("the shift less the breaks the UK drivers' hours rules require (45 min once driving passes 4½ h or work "
              "passes 9 h; 30 min once work passes 6 h), with driving at most 9 h")
LIMIT_WORDS = {
    "shift": "as many round trips as fit in the shift",
    "breaks": "one fewer than the shift alone would hold: the required break takes the time",
    "driving": "capped by the 9 h a day driving limit",
    "none": "one round trip does not fit in a driver's day",
}


def shift_hours(factors):
    """Shift hours a day as typed (Config → Planning), SHIFT_DEFAULT_H when untyped or not a positive number, at most
    SHIFT_MAX_H. Returns (hours used, capped: bool)."""
    v = ((factors or {}).get("planning") or {}).get("shift_hours_per_day")
    try:
        h = float(v if v is not None else SHIFT_DEFAULT_H)
    except (TypeError, ValueError):
        h = SHIFT_DEFAULT_H
    if not h > 0:
        h = SHIFT_DEFAULT_H
    return (SHIFT_MAX_H, True) if h > SHIFT_MAX_H + EPS else (h, False)


def shift_problem(v):
    """None when `v` is an allowed Shift hours a day, else the problem in words (Config → Planning)."""
    try:
        h = float(v)
    except (TypeError, ValueError):
        return None                     # the positive-number check is config.validate's own
    if h > SHIFT_MAX_H + EPS:
        return (f"Shift hours a day: at most {SHIFT_MAX_H:g} — a driver's daily rest is 11 hours in every 24 under the "
                f"UK drivers' hours rules")
    return None


def break_minutes(driving_min, work_min):
    """The ONE break a day of `driving_min` driving and `work_min` working time needs (minutes): 45 once driving passes
    4.5 h or work passes 9 h, else 30 once work passes 6 h, else 0. Never the two added together."""
    if driving_min > DRIVING_BEFORE_BREAK_MIN + EPS or work_min > WORK_LONG_BREAK_AFTER_MIN + EPS:
        return BREAK_LONG_MIN
    if work_min > WORK_SHORT_BREAK_AFTER_MIN + EPS:
        return BREAK_SHORT_MIN
    return 0.0


def fits(n, drive_min, other_min, shift_min, extra_min=0.0):
    """True when n round trips (each `drive_min` driving + `other_min` other work) fit a driver's day of `shift_min`:
    driving at most 9 h, and the trips, `extra_min` (an electric lorry's charging) and the required break inside it."""
    driving, work = n * drive_min, n * (drive_min + other_min)
    if driving > DRIVING_MAX_MIN + EPS:
        return False
    return work + extra_min + break_minutes(driving, work) <= shift_min + EPS


def lorry_day(shift_h, drive_min, other_min):
    """
    One lorry's day on a route: {trips, limited_by, break_minutes, driving_minutes, work_minutes, shift_hours,
    cycle_minutes, trips_without_rules}. `trips` = the largest n that fits (fits()); `trips_without_rules` = the old
    floor(shift ÷ cycle), kept so a figure that moved can say why. `limited_by`: 'shift' (the rules took nothing off: as
    many as the shift holds), 'driving' (fewer, and one more would pass the 9 h driving cap), 'breaks' (fewer because of
    the required break) or 'none' (not one round trip fits). `shift_h` is used as given (shift_hours() caps it).
    """
    drive_min = max(0.0, float(drive_min or 0.0))
    other_min = max(0.0, float(other_min or 0.0))
    shift_min = float(shift_h) * 60.0
    cycle = drive_min + other_min
    plain = int((shift_min + EPS) // cycle) if cycle > 0 else 0
    n = plain
    while n > 0 and not fits(n, drive_min, other_min, shift_min):
        n -= 1
    # why not one more: nothing taken off ('shift'), else the 9 h driving cap (named first when both would), else the break
    if n <= 0:
        limited = "none"
    elif n == plain:
        limited = "shift"
    elif (n + 1) * drive_min > DRIVING_MAX_MIN + EPS:
        limited = "driving"
    else:
        limited = "breaks"
    driving, work = n * drive_min, n * cycle
    return {"trips": n, "limited_by": limited, "break_minutes": (break_minutes(driving, work) if n else 0.0),
            "driving_minutes": driving, "work_minutes": work, "shift_hours": float(shift_h),
            "cycle_minutes": cycle, "trips_without_rules": plain}


def ev_trips(shift_h, drive_min, other_min, charge_minutes_for):
    """
    An electric lorry's day: the largest n whose trips, charging (`charge_minutes_for(n)`, the battery simulated trip by
    trip in carbon.ev_day) and the required break fit, driving at most 9 h. Charging comes ON TOP of the break (17 Oct
    2026, the cautious reading: a break is uninterrupted free time, and a charging stop's length rarely matches it) —
    the Carbon planner says so. Returns n (0 when not one trip fits).
    """
    shift_min = float(shift_h) * 60.0
    cycle = max(0.0, float(drive_min or 0.0)) + max(0.0, float(other_min or 0.0))
    n = int((shift_min + EPS) // cycle) if cycle > 0 else 0
    while n > 0:
        if fits(n, drive_min, other_min, shift_min, extra_min=charge_minutes_for(n)):
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
    """'5 a day: as many round trips as fit in the shift with the required break (45 min)' — for a title or a footnote."""
    if not day:
        return None
    lim = LIMIT_WORDS.get(day.get("limited_by"), "")
    brk = day.get("break_minutes") or 0
    return (f"{day['trips']} a day: {lim}" + (f" ({brk:g} min break)" if day.get("trips") and brk else "")
            if day.get("trips") else LIMIT_WORDS["none"].capitalize())


if __name__ == "__main__":       # a quick look: python drivers_hours.py
    for d, o in ((60, 0), (69, 24), (45, 24), (138, 24), (104 - 20, 20)):
        r = lorry_day(10, d, o)
        print(d, o, r["trips"], r["limited_by"], r["break_minutes"], r["trips_without_rules"], words(r))
