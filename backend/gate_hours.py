"""
gate_hours.py — when a gate is open, how many lorries it can check in, and how full a day is.
Wayscope, 14 Oct 2026 (bundle G: W8 cut down + W17). Design note: notes/clp-design.md (not in git).

THE RULES, IN ONE PLACE (the Dashboard's Gate arrivals panel, the Look-ahead's week chart, the clash
rail, the CLP section and both exports all read these; nothing is worked out a second time)
------------------------------------------------------------------------------------------------
* OPEN MINUTES of a gate on a day = its typed `open_from`–`open_to` (HH:MM; a window that ends
  before it starts runs past midnight), else the scheme's shift (`planning.shift_hours_per_day`,
  10 h untyped — derived.py's rule). With the gate's hours typed, the scheme's PEAK BANDS
  (`planning.peak_bands`, no-delivery windows agreed in the CLP, the user's decision 14 Oct) are
  taken off the minutes inside the window. The scheme's shift has no clock times, so a gate with
  no hours typed keeps its shift minutes and `peak_note` says the bands could not be taken off.
* OPEN DAYS: `open_days` is seven '1'/'0' flags, Monday first. Untyped = open every day. Only the
  Look-ahead's dated days test it; a month figure is a working-day average and does not.
* CAPACITY a day = open minutes ÷ the gate's check-in minutes a lorry (`safety_minutes`): the most
  lorries it can check in if they arrive evenly. No check-in typed = no capacity, never compared.
* STATUS (one rule): planned arrivals ≥ NEAR_PCT (85 %) of capacity = "Queue likely" (amber);
  over 100 % = "Over gate capacity" (red); arrivals on a closed day = "Over gate capacity". Words
  always travel with the colour (word + icon on every screen).
* THE HONEST LIMIT, printed wherever a figure is: LIMIT_WORDS. No arrival times are held (D42).

Pure functions: no database read, no write.
"""
import re

NEAR_PCT = 85
STATUS_WORDS = {"red": "Over gate capacity", "amber": "Queue likely"}
LIMIT_WORDS = "Planned arrivals spread evenly over the gate's open hours; no hourly peak is known."
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MAX_PEAK_BANDS = 4
PEAK_PLACEHOLDER = [{"from": "07:00", "to": "10:00"}, {"from": "16:00", "to": "19:00"}]

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def minutes_of(hhmm):
    """'07:30' -> 450; None for anything else (24:00 is not a time; type 00:00)."""
    if not isinstance(hhmm, str):
        return None
    m = _HHMM.match(hhmm.strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def hhmm_problem(v):
    """None when `v` is a 24-hour HH:MM time, else what is wrong, in words."""
    return None if minutes_of(v) is not None else "must be a 24-hour time such as 07:00"


def clean_days(v):
    """Seven '1'/'0' flags Monday first, from a string of seven flags or a list of seven booleans;
    None for nothing or for a shape that is neither (the caller refuses it)."""
    if v is None or v == "":
        return None
    if isinstance(v, (list, tuple)) and len(v) == 7:
        return "".join("1" if bool(x) else "0" for x in v)
    if isinstance(v, str) and re.fullmatch(r"[01]{7}", v.strip()):
        return v.strip()
    return None


def days_problem(v):
    if v is None or v == "":
        return None
    d = clean_days(v)
    if d is None:
        return "open days must be seven on/off flags, Monday first"
    if "1" not in d:
        return "a gate must be open on at least one day (clear the days to mean every day)"
    return None


def _intervals(a, b):
    """The window [a, b) in minutes of the day; one that ends at or before it starts runs past midnight."""
    if b > a:
        return [(a, b)]
    return [(a, 1440), (0, b)]


def _overlap(xs, ys):
    return sum(max(0, min(b, d) - max(a, c)) for a, b in xs for c, d in ys)


def peak_bands_problem(v):
    """None when `v` is a list of at most four {from, to} windows that do not overlap, else the problem."""
    if v is None:
        return None
    if not isinstance(v, list):
        return "peak_bands must be a list of {from, to} windows"
    if len(v) > MAX_PEAK_BANDS:
        return f"at most {MAX_PEAK_BANDS} peak bands"
    seen = []
    for i, b in enumerate(v):
        if not isinstance(b, dict):
            return f"peak band {i + 1} must be an object with from and to"
        a, z = minutes_of(b.get("from")), minutes_of(b.get("to"))
        if a is None or z is None:
            return f"peak band {i + 1}: from and to must be 24-hour times such as 07:00"
        if a == z:
            return f"peak band {i + 1}: from and to are the same time"
        iv = _intervals(a, z)
        if _overlap(iv, [x for s in seen for x in s]):
            return f"peak band {i + 1} overlaps another band"
        seen.append(iv)
    return None


def peak_bands(factors):
    """The scheme's peak bands as typed ([] when none, or when the block is not valid)."""
    v = ((factors or {}).get("planning") or {}).get("peak_bands")
    if not v or peak_bands_problem(v) is not None:
        return []
    return [{"from": b["from"].strip(), "to": b["to"].strip()} for b in v]


def peak_words(bands):
    """'07:00–10:00 and 16:00–19:00' (or None)."""
    if not bands:
        return None
    parts = [f"{b['from']}–{b['to']}" for b in bands]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def shift_minutes(factors):
    """The derived.py rule: the planning block's shift, 10 h when untyped or not a positive number."""
    v = ((factors or {}).get("planning") or {}).get("shift_hours_per_day")
    try:
        h = float(v if v is not None else 10)
    except (TypeError, ValueError):
        h = 10.0
    return (h if h > 0 else 10.0) * 60.0


def window_of(gate):
    """(from, to) as typed on the gate, or None when either is missing or not a time."""
    a, b = minutes_of((gate or {}).get("open_from")), minutes_of((gate or {}).get("open_to"))
    if a is None or b is None or a == b:
        return None
    return a, b


def open_minutes(gate, factors):
    """
    {minutes, basis, hours, peak_minutes, peak_note} for one gate on an open day.
    basis 'gate' (its hours, less the peak bands inside them) or 'shift' (the scheme's).
    """
    bands = peak_bands(factors)
    w = window_of(gate)
    if w is None:
        return {"minutes": shift_minutes(factors), "basis": "shift", "hours": None, "peak_minutes": 0.0,
                "peak_note": ("The peak bands are not taken off this gate: the scheme's shift has no clock times, "
                              "so type the gate's open hours." if bands else None)}
    iv = _intervals(*w)
    total = sum(b - a for a, b in iv)
    banned = 0.0
    for b in bands:
        banned += _overlap(iv, _intervals(minutes_of(b["from"]), minutes_of(b["to"])))
    return {"minutes": float(max(0.0, total - banned)), "basis": "gate",
            "hours": f"{gate['open_from'].strip()}–{gate['open_to'].strip()}",
            "peak_minutes": float(banned), "peak_note": None}


def is_open_on(gate, date):
    """False only when the gate's open days are typed and exclude the date's weekday."""
    d = clean_days((gate or {}).get("open_days"))
    return True if d is None else d[date.weekday()] == "1"


def closed_days_words(gate):
    """'closed on Saturdays and Sundays' for a gate with open days typed (None otherwise)."""
    d = clean_days((gate or {}).get("open_days"))
    if d is None or "0" not in d:
        return None
    shut = [DAY_NAMES[i] + "s" for i, f in enumerate(d) if f == "0"]
    return "closed on " + (shut[0] if len(shut) == 1 else ", ".join(shut[:-1]) + " and " + shut[-1])


def capacity(open_m, check_in):
    """Open minutes ÷ check-in minutes; None with no check-in (or a zero one) or no open minutes."""
    try:
        c = float(check_in) if check_in is not None else None
    except (TypeError, ValueError):
        c = None
    if not c or c <= 0 or not open_m or open_m <= 0:
        return None
    return float(open_m) / c


def status(arrivals, cap, open_today=True):
    """'red' over 100 % (or any arrival on a closed day), 'amber' at NEAR_PCT % or more, else None."""
    if arrivals is None or arrivals <= 0:
        return None
    if not open_today:
        return "red"
    if not cap:
        return None
    pct = arrivals * 100.0 / cap
    if pct > 100.0 + 1e-9:
        return "red"
    if pct >= NEAR_PCT - 1e-9:
        return "amber"
    return None
