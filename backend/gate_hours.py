"""
gate_hours.py — when a gate is open, how many lorries it can check in, and how full a day is.
Wayscope, 14 Oct 2026 (bundle G: W8 cut down + W17). Design note: notes/clp-design.md (not in git).

THE RULES, IN ONE PLACE (the Dashboard's Gate arrivals panel, the Look-ahead's week chart, the clash
rail, the CLP section and both exports all read these; nothing is worked out a second time)
------------------------------------------------------------------------------------------------
* OPEN MINUTES of a gate on a day = its typed `open_from`–`open_to` (HH:MM; a window that ends
  before it starts runs past midnight), else THE DEFAULT GATE HOURS: the scheme's own
  (`planning.default_gate_hours`, typed on Config → Planning) or 08:00–17:00 (DEFAULT_GATE_HOURS; the
  user, 17 Oct 2026: the hours councils' noise conditions usually allow). Every gate therefore has
  clock times. From its window come off, COUNTED ONCE where they overlap: the scheme's PEAK BANDS
  (`planning.peak_bands`, no-delivery windows agreed in the CLP, the user's decision 14 Oct) and the
  gate's own SHUT WINDOWS (`shut_windows`, at most MAX_SHUT_WINDOWS, e.g. a school run or a lunch;
  17 Oct 2026). A shut window outside the window takes nothing off. The lorry shift
  (`planning.shift_hours_per_day`) is NOT a gate's day: it sets the trips one lorry makes (derived.py).
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
LIMIT_WORDS = ("Planned arrivals spread evenly over the gate's open hours, less its shut times and the no-delivery "
               "bands; no hourly peak is known.")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MAX_PEAK_BANDS = 4
PEAK_PLACEHOLDER = [{"from": "07:00", "to": "10:00"}, {"from": "16:00", "to": "19:00"}]
#: 17 Oct 2026 (the user: "default time for gates should be 0800-1700 as this is generally environmental and local
#: authority agreements due to noise pollution"): a gate with no hours typed is open these hours, unless the scheme types
#: its own default on Config (planning.default_gate_hours). Applied when read, never written onto a gate, so typed and
#: default hours stay apart. Councils publish other hours too (08:00–18:00 weekdays is the most common pattern found).
DEFAULT_GATE_HOURS = {"from": "08:00", "to": "17:00"}
#: 17 Oct 2026: the most shut windows one gate can have in a day (a school run each way, a lunch, one more)
MAX_SHUT_WINDOWS = 4
SHUT_PLACEHOLDER = [{"from": "08:30", "to": "09:15"}, {"from": "15:00", "to": "15:45"}]

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


def _shut_list(v):
    """[(from, to)] as strings from a list of {from, to}, a list of 'HH:MM-HH:MM' or the stored text; [] for nothing;
    None for a shape that is none of these."""
    if v is None or v == "" or v == []:
        return []
    if isinstance(v, str):
        v = [p for p in v.split(",") if p.strip()]
    if not isinstance(v, (list, tuple)):
        return None
    out = []
    for w in v:
        if isinstance(w, dict):
            f, t = w.get("from"), w.get("to")
            if not isinstance(f, str) or not isinstance(t, str):
                return None
            out.append((f.strip(), t.strip()))
        elif isinstance(w, str) and "-" in w.replace("–", "-"):
            f, t = w.replace("–", "-").split("-", 1)
            out.append((f.strip(), t.strip()))
        else:
            return None
    return out


def shut_problem(v):
    """
    17 Oct 2026: None when `v` is a gate's shut windows as typed — at most MAX_SHUT_WINDOWS {from, to} windows, each
    ending after it starts on the same day, none overlapping another — else the problem in words. Nothing (None, '',
    []) is fine. Also takes the stored text ('08:30-09:15,12:00-12:30') and 'HH:MM-HH:MM' strings.
    """
    ws = _shut_list(v)
    if ws is None:
        return "shut times must be a list of from–to times"
    if len(ws) > MAX_SHUT_WINDOWS:
        return f"at most {MAX_SHUT_WINDOWS} shut times a gate"
    seen = []
    for i, (f, t) in enumerate(ws):
        a, z = minutes_of(f), minutes_of(t)
        if a is None or z is None:
            return f"shut time {i + 1}: from and to must be 24-hour times such as 12:00"
        if a == z:
            return f"shut time {i + 1}: from and to are the same time"
        if z < a:
            return f"shut time {i + 1} must end after it starts (a shut time stays within one day)"
        if _overlap([(a, z)], seen):
            return f"shut time {i + 1} overlaps another shut time"
        seen.append((a, z))
    return None


def clean_shut(v):
    """The text stored on the gate: start-sorted 'HH:MM-HH:MM,HH:MM-HH:MM', or None for no shut times. Call only after
    shut_problem(v) is None (the caller refuses anything else)."""
    ws = sorted(_shut_list(v) or [], key=lambda w: minutes_of(w[0]) or 0)
    return ",".join(f"{f}-{t}" for f, t in ws) or None


def shut_windows(gate):
    """
    The gate's shut windows as [{from, to}], start-sorted; [] when none — or when the stored text is not valid (a
    package imports rows with no gate check, so the read never trusts it).
    """
    v = (gate or {}).get("shut_windows")
    if not v or shut_problem(v) is not None:
        return []
    ws = sorted(_shut_list(v), key=lambda w: minutes_of(w[0]))
    return [{"from": f, "to": t} for f, t in ws]


def default_hours_problem(v):
    """17 Oct 2026: None when `v` (planning.default_gate_hours) is absent or {from, to} on one day, else the problem."""
    if v is None:
        return None
    if not isinstance(v, dict):
        return "default_gate_hours must be an object with from and to"
    a, z = minutes_of(v.get("from")), minutes_of(v.get("to"))
    if a is None or z is None:
        return "default_gate_hours: from and to must be 24-hour times such as 08:00"
    if z <= a:
        return "default_gate_hours: the gate must close after it opens (the default stays within one day)"
    return None


def default_hours(factors):
    """{from, to}: the scheme's default gate hours as typed on Config, else DEFAULT_GATE_HOURS."""
    v = ((factors or {}).get("planning") or {}).get("default_gate_hours")
    if v is None or default_hours_problem(v) is not None:
        return dict(DEFAULT_GATE_HOURS)
    return {"from": v["from"].strip(), "to": v["to"].strip()}


def default_words(factors):
    """'08:00–17:00': the default gate hours, as every screen prints them."""
    d = default_hours(factors)
    return f"{d['from']}–{d['to']}"


def subtract(iv, cuts):
    """The intervals `iv` with every interval in `cuts` taken off (a set difference: an overlap among the cuts counts
    once). Both are [(a, b)] in minutes of the day; the result keeps `iv`'s order."""
    out = list(iv)
    for p, q in cuts or []:
        nx = []
        for x, y in out:
            if q <= x or p >= y:
                nx.append((x, y))
                continue
            if p > x:
                nx.append((x, p))
            if q < y:
                nx.append((q, y))
        out = nx
    return out


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
    """The LORRY shift (derived.py's rule), 10 h when untyped or not a positive number. Not a gate's day since 17 Oct
    2026: a gate with no hours typed takes the default gate hours (default_hours)."""
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


def effective_window(gate, factors):
    """((from, to) in minutes, basis): the gate's typed hours ('gate'), else the default gate hours ('default')."""
    w = window_of(gate)
    if w is not None:
        return w, "gate"
    d = default_hours(factors)
    return (minutes_of(d["from"]), minutes_of(d["to"])), "default"


def _hhmm(m):
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def open_minutes(gate, factors):
    """
    {minutes, basis, hours, peak_minutes, shut, shut_minutes, shut_words, intervals} for one gate on an open day.
    basis 'gate' (its typed hours) or 'default' (the default gate hours; 17 Oct 2026, was 'shift' = the lorry shift
    with no clock times). From the window come off the peak bands (`peak_minutes`), then the gate's shut windows not
    already inside a band (`shut_minutes`): an overlap counts once. `intervals` = what is left, [(a, b)] in minutes of
    the day (a window past midnight splits at midnight).
    """
    bands = peak_bands(factors)
    w, basis = effective_window(gate, factors)
    iv = _intervals(*w)
    total = sum(b - a for a, b in iv)
    band_iv = [x for b in bands for x in _intervals(minutes_of(b["from"]), minutes_of(b["to"]))]
    after_bands = subtract(iv, band_iv)
    shut = shut_windows(gate)
    left = subtract(after_bands, [(minutes_of(s["from"]), minutes_of(s["to"])) for s in shut])
    m_bands, m_left = sum(b - a for a, b in after_bands), sum(b - a for a, b in left)
    hours = (f"{gate['open_from'].strip()}–{gate['open_to'].strip()}" if basis == "gate"
             else f"{_hhmm(w[0])}–{_hhmm(w[1])}")
    return {"minutes": float(m_left), "basis": basis, "hours": hours,
            "peak_minutes": float(total - m_bands), "shut": shut, "shut_minutes": float(m_bands - m_left),
            "shut_words": peak_words(shut), "intervals": left}


def shut_fit_problem(gate, factors):
    """
    17 Oct 2026, on a write: None when the gate's shut windows fit its hours (typed, or the default), else the problem
    in words — a shut time wholly outside the hours (a typing slip: it would take nothing off), or shut times that
    leave the gate no open time at all. The peak bands are the scheme's and are not counted here.
    """
    shut = shut_windows(gate)
    if not shut:
        return None
    w, basis = effective_window(gate, factors)
    iv = _intervals(*w)
    hours = (f"{gate['open_from'].strip()}–{gate['open_to'].strip()}" if basis == "gate"
             else f"{_hhmm(w[0])}–{_hhmm(w[1])} (the default)")
    for s in shut:
        if not _overlap(iv, [(minutes_of(s["from"]), minutes_of(s["to"]))]):
            return f"shut time {s['from']}–{s['to']} is outside the open hours {hours}"
    if not subtract(iv, [(minutes_of(s["from"]), minutes_of(s["to"])) for s in shut]):
        return f"the shut times leave the gate no open time within {hours}"
    return None


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
