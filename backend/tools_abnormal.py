"""
tools_abnormal.py — the abnormal load adviser's free check, the public tool at /tools/abnormal-load (claude/tools-abnormal-
adviser, 17 Nov 2026; John's order of 16 Nov, "start the first opening"; the look is the mockup's card 3,
notes/tools-first-opening-mockup-1116).

THE RULES ARE THE PLATFORM'S OWN. The answer is abnormal_rules.advice(...) on the typed figures, with:
  nation         what the person picked (England and Wales, or Scotland), never an organisation's setting;
  holidays_feed  the SHIPPED gov.uk copy (backend/data/bank_holidays.json), never an organisation's fetched copy;
  time_bans      None: police time bans are typed per scheme, and a public check has no scheme;
  today          the date in London.
Nothing of any organisation is read (no Config, no database, no access.current()), and nothing is written or kept.
This module changes no rule and adds none: it only turns the rules' STRUCTURED answer (category, notices, attendant
reasons, markers, speeds, escort, height, reasons, notes) into the page's short sentences. The rules' own `lines` name
statute paragraphs and a code of practice; the public page leaves those references out, as the agreed drawing does. Every
place a public sentence is shorter than the rules' line is listed side by side in notes/session-1117-tools-abnormal-
adviser.md. The staff-only note "No escort is planned for this movement…" is never shown (a public check plans nothing).

The form has no rigid-length box and no overhang boxes: "Length" is the overall length (`length_m`) and overhangs are 0.
Two ticks (John's yes, 17 Nov, Q6 and Q7 of notes/tools-abnormal-adviser-mockup-1116): "The lorry itself is within the
normal size and weight limits" sends `cu_vehicle` (the rules then answer C&U where the figures allow it), and "The heaviest
axle is a driving axle" sends `axle_driving` (11.5 t, not 10 t). How a C&U answer reads is Q8: the head "Moves under C&U,
not STGO", no Speeds row and no STGO category note, a line that a Saturday counts; ticked but over the C&U ceilings, the
rules answer STGO and the page says why first.

Pure: no database, no network, no clock of its own beyond `today` (passed in, or London's date).
"""
import datetime
import json
import os

import abnormal_rules as R

HOLIDAYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bank_holidays.json")

#: the two choices the "Where" box offers, as the rules name them
NATIONS = {"england-and-wales": "England and Wales", "scotland": "Scotland"}
#: the move's time band, as the rules name it
BANDS = {"day": "by day", "night": "by night"}

#: the open call's limit: checks from one address in an hour. The page asks again a moment after each change, so a
#: person trying a few loads makes a few dozen; a script is stopped well before it matters (tools_public.Limit)
CHECKS_PER_HOUR = 120

#: the bounds of a figure a person can type (outside them the figure cannot be right: a sentence, never a guess)
BOUNDS = {
    "width_m": (0.5, 12.0), "length_m": (2.0, 120.0), "height_m": (0.5, 12.0),
    "gross_t": (1.0, 3000.0), "max_axle_t": (0.5, 100.0),
}
AXLES_MIN, AXLES_MAX = 2, 400
SPACING_MIN_M, SPACING_MAX_M = 0.3, 30.0

#: the refusal sentences, one per missing or impossible figure (tests pin each word for word)
SAY = {
    "width_m": "Type the width in metres.",
    "length_m": "Type the length in metres.",
    "height_m": "Type the height in metres.",
    "gross_t": "Type the gross weight in tonnes.",
    "max_axle_t": "Type the heaviest axle in tonnes.",
    "axle_count": "Type the number of axles: 2 or more.",
    "date": "Pick the day it moves.",
    "past": "Pick a moving day from today on.",
    "where": "Pick England and Wales, or Scotland.",
    "band": "Pick by day or by night.",
    "axle_over_gross": "The heaviest axle cannot weigh more than the whole load. Check the figures.",
    "axles_short": "The heaviest axle times the number of axles is less than the gross weight. Check the figures.",
    "spacings": "Type the axle spacings in metres, with commas between them.",
}
BOUND_SAY = {
    "width_m": "A width of {lo:g} to {hi:g} m, please.",
    "length_m": "A length of {lo:g} to {hi:g} m, please.",
    "height_m": "A height of {lo:g} to {hi:g} m, please.",
    "gross_t": "A gross weight of {lo:g} to {hi:g} t, please.",
    "max_axle_t": "A heaviest axle of {lo:g} to {hi:g} t, please.",
}

#: Q8 (17 Nov): a C&U answer's head, its calendar line, and the plain words for the rules' "over the C&U ceiling" reasons
CU_HEAD = "Moves under C&U, not STGO"
NOT_ABNORMAL = "Not an abnormal load"
NOT_ABNORMAL_NOTICE = "Not abnormal, but a notice is needed"
CU_SATURDAY = "For an ordinary lorry a Saturday counts as a working day; Sundays and bank holidays do not."
CEILING_WORDS = (("width over the C&U ceiling", f"over {R.CU_WIDTH_MAX_M:g} m wide"),
                 ("length over the C&U ceiling", f"over {R.CU_LENGTH_MAX_M:g} m long"),
                 ("weights over the normal limits", "over the normal weights"))

#: the fixed lines of the answer
LAST_LINE = ("Advice from the typed figures, not permission. The haulier, ESDAL, the police and the road and bridge "
             "authorities decide. Bridges, structures and overhangs are not checked here.")
SPACINGS_NOT_TYPED = "Axle spacings not typed: the limits for closely spaced axles are not tested."
NEXT_WORDS = ("More than one load?", "Keep each load and its notices in one plan.")


class Bad(ValueError):
    """A typed figure that is missing or cannot be right; `say` is the one sentence the page shows."""

    def __init__(self, say):
        super().__init__(say)
        self.say = say


# --------------------------------------------------------------------------- the shipped bank holidays

_FEED = None


def holidays_feed():
    """The shipped gov.uk copy (never an organisation's fetched one), read once."""
    global _FEED
    if _FEED is None:
        with open(HOLIDAYS_FILE, encoding="utf-8") as fh:
            _FEED = json.load(fh)
    return _FEED


def last_moving_day():
    """The last moving day the shipped holidays cover: 31 December of the year of their last date (Dec 2028)."""
    dates = R.holiday_dates(holidays_feed(), ("england-and-wales", "scotland"))
    return datetime.date(max(dates).year, 12, 31)


def london_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/London")).date()
    except Exception:
        return datetime.date.today()


# --------------------------------------------------------------------------- reading the form

def _figure(body, key, required=True):
    v = (body or {}).get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise Bad(SAY[key])
        return None
    if isinstance(v, bool):
        raise Bad(SAY[key])
    try:
        x = float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        raise Bad(SAY[key])
    if x != x or x in (float("inf"), float("-inf")):
        raise Bad(SAY[key])
    lo, hi = BOUNDS[key]
    if x < lo or x > hi:
        raise Bad(BOUND_SAY[key].format(lo=lo, hi=hi))
    return round(x, 3)


def _spacings(v, axles):
    if v is None or (isinstance(v, str) and not v.strip()) or v == []:
        return []
    items = v if isinstance(v, (list, tuple)) else str(v).replace(";", ",").split(",")
    out = []
    for it in items:
        s = str(it).strip().lower().replace("m", "").strip()
        if not s:
            continue
        try:
            x = float(s)
        except ValueError:
            raise Bad(SAY["spacings"])
        if x != x or x < SPACING_MIN_M or x > SPACING_MAX_M:
            raise Bad(f"Each axle spacing from {SPACING_MIN_M:g} to {SPACING_MAX_M:g} m, please.")
        out.append(round(x, 3))
    if out and len(out) != axles - 1:
        raise Bad(f"Type one spacing between each pair of axles: {axles - 1} for {axles} axles.")
    return out


def read_form(body, today=None):
    """The typed form as the rules' figures plus the move: (figures, date, band, nation). Raises Bad with one sentence."""
    body = body if isinstance(body, dict) else {}
    today = today or london_today()
    width = _figure(body, "width_m")
    length = _figure(body, "length_m")
    height = _figure(body, "height_m")
    gross = _figure(body, "gross_t")
    axle = _figure(body, "max_axle_t")
    n = body.get("axle_count")
    try:
        n = int(float(str(n).strip())) if n not in (None, "") and not isinstance(n, bool) else None
    except (TypeError, ValueError, OverflowError):     # OverflowError: "1e999" or "inf" typed as the axles
        n = None
    if n is None or n < AXLES_MIN or n > AXLES_MAX or float(str(body.get("axle_count")).strip()) != n:
        raise Bad(SAY["axle_count"])
    if axle > gross:
        raise Bad(SAY["axle_over_gross"])
    if axle * n < gross - 1e-9:
        raise Bad(SAY["axles_short"])
    spacings = _spacings(body.get("axle_spacings_m"), n)
    d = R._date(body.get("date"))
    if not d or not isinstance(body.get("date"), str) or len(body.get("date").strip()) != 10:
        raise Bad(SAY["date"])
    if d < today:
        raise Bad(SAY["past"])
    last = last_moving_day()
    if d > last:
        raise Bad(f"Pick a moving day up to {_long(last)}: the bank holidays held here end then.")
    # Q1 (17 Nov, the session's recommendation as revised; John's yes OUTSTANDING): the page sends no time band (it never
    # changes an answer with no police time bans); "Where" is kept (it moves the C&U calendar); a caller may still send
    # either, read as before
    nation = body.get("where") or "england-and-wales"
    if not isinstance(nation, str) or nation not in NATIONS:      # a list or a dict sent by a script is a sentence too
        raise Bad(SAY["where"])
    band = body.get("band") or "day"
    if not isinstance(band, str) or band not in BANDS:
        raise Bad(SAY["band"])
    figures = {"width_m": width, "length_m": length, "height_m": height, "gross_t": gross, "max_axle_t": axle,
               "axle_count": n, "axle_spacings_m": spacings, "indivisible": body.get("indivisible") is True,
               "axle_driving": body.get("axle_driving") is True, "cu_vehicle": body.get("cu_vehicle") is True}
    return figures, d, band, nation


# --------------------------------------------------------------------------- the words

def _g(x):
    return f"{x:g}"


def _short(iso):
    """7 Dec (a row's date)."""
    d = R._date(iso)
    return f"{d.day} {d:%b}"


def _day(iso):
    """Mon 7 Dec 2026 (a chip's date)."""
    d = R._date(iso)
    return f"{d:%a} {d.day} {d:%b} {d.year}"


def _long(d):
    """31 December 2028."""
    return f"{d.day} {d:%B} {d.year}"


def _and(parts):
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


#: the class line, from the rules' category
CLASS_WORDS = {"cat1": "STGO Category 1", "cat2": "STGO Category 2", "cat3": "STGO Category 3",
               "special_order": "Special Order"}


def _over_normal(g):
    """The load's figures over the normal limits, each with its limit: '76 t gross (44 t)'. Same tests as the rules'
    abnormal_reasons (no rigid length is typed on this form)."""
    out = []
    if g["gross_t"] is not None and g["gross_t"] > R.ABNORMAL_GROSS_T:
        out.append(f"{_g(g['gross_t'])} t gross ({_g(R.ABNORMAL_GROSS_T)} t)")
    lim = R.axle_limit_t(g["axle_driving"])
    if g["max_axle_t"] is not None and g["max_axle_t"] > lim:
        out.append(f"{_g(g['max_axle_t'])} t on an axle ({_g(lim)} t)")
    if g["width_m"] is not None and g["width_m"] > R.ABNORMAL_WIDTH_M:
        out.append(f"{_g(g['width_m'])} m wide ({_g(R.ABNORMAL_WIDTH_M)} m)")
    if g.get("rigid_length_m") is not None and g["rigid_length_m"] > R.ABNORMAL_RIGID_LENGTH_M:
        out.append(f"{_g(g['rigid_length_m'])} m rigid ({_g(R.ABNORMAL_RIGID_LENGTH_M)} m)")
    return out


def _attendant(g, reg):
    """Why an attendant is needed, in the page's words; the rules' attendant reasons, in the same order."""
    out = []
    w, ln, rl = g["width_m"], g["length_m"], g.get("rigid_length_m")
    if w is not None and w > R.ATTENDANT_WIDTH_M:
        out.append(f"over {_g(R.ATTENDANT_WIDTH_M)} m wide")
    rigid_limit = R.ABNORMAL_RIGID_LENGTH_M if reg == "cu" else R.STGO_RIGID_M
    if rl is not None and rl > rigid_limit:
        out.append(f"over {_g(rigid_limit)} m rigid")
    if ln is not None and ln > R.STGO_COMBINATION_M:
        out.append(f"over {_g(R.STGO_COMBINATION_M)} m long")
    if g["proj_front_m"] > R.PROJECTION_FRONT_ATTENDANT_M:
        out.append(f"a front overhang over {_g(R.PROJECTION_FRONT_ATTENDANT_M)} m")
    if g["proj_rear_m"] > R.PROJECTION_REAR_ATTENDANT_M:
        out.append(f"a rear overhang over {_g(R.PROJECTION_REAR_ATTENDANT_M)} m")
    return out


def _escort(g, which):
    out = []
    w, ln, gross = g["width_m"], g["length_m"], g["gross_t"]
    if which == "motorway":
        if w is not None and w > R.ESCORT_MOTORWAY_WIDTH_M:
            out.append(f"over {_g(R.ESCORT_MOTORWAY_WIDTH_M)} m wide")
        if gross is not None and gross > R.ESCORT_MOTORWAY_GROSS_T:
            out.append(f"over {_g(R.ESCORT_MOTORWAY_GROSS_T)} t gross")
    else:
        if w is not None and w > R.ESCORT_OTHER_WIDTH_M:
            out.append(f"over {_g(R.ESCORT_OTHER_WIDTH_M)} m wide")
        if ln is not None and ln > R.ESCORT_OTHER_LENGTH_M:
            out.append(f"over {_g(R.ESCORT_OTHER_LENGTH_M)} m long")
        if gross is not None and gross > R.ESCORT_OTHER_GROSS_T:
            out.append(f"over {_g(R.ESCORT_OTHER_GROSS_T)} t gross")
    return out


def _height(g, permission):
    h = g["height_m"]
    out = []
    if h is not None and h > R.HEIGHT_CAB_NOTICE_M:
        out.append(f"Over {_g(R.HEIGHT_CAB_NOTICE_M)} m: the travelling height is shown in the cab.")
    if h is not None and h > R.HEIGHT_CHECK_M:
        out.append(f"Over {_g(R.HEIGHT_CHECK_M)} m: check every bridge and overhead structure with the highway "
                   f"authorities. Bridges are signed only below {_g(R.HEIGHT_CHECK_M)} m, so an unsigned one can still "
                   "be too low." + (f" A Special Order or VR1 load stays within {_g(R.HEIGHT_CHECK_M)} m where possible."
                                    if permission != "none" else ""))
    if h is not None and h > R.HIGH_LOAD_GRID_M[1]:
        out.append(f"Over {_g(R.HIGH_LOAD_GRID_M[1])} m (20 ft): beyond the High Load Grid.")
    elif h is not None and h > R.HIGH_LOAD_GRID_M[0]:
        out.append(f"Over {_g(R.HIGH_LOAD_GRID_M[0])} m (18 ft): a High Load Grid route (20 ft routes take it).")
    return " ".join(out)


def _markers(g):
    """The rules' markers in the page's words. On this form only the long-load plates can arise (no overhangs typed)."""
    out = []
    pf, pr, ln = g["proj_front_m"], g["proj_rear_m"], g["length_m"]
    if pr > R.MARKER_REAR_VISIBLE_M and pr <= R.MARKER_END_M:
        out.append(f"Make the end clearly visible (a rear overhang over {_g(R.MARKER_REAR_VISIBLE_M)} m).")
    if pf > R.MARKER_END_M or pr > R.MARKER_END_M:
        out.append("End marker boards (an overhang over 2 m).")
    if pf > R.MARKER_SIDE_FRONT_M or pr > R.MARKER_SIDE_REAR_M:
        out.append("Side marker boards (front over 2 m or rear over 3 m).")
    if pf > R.MARKER_EXTRA_FRONT_M or pr > R.MARKER_EXTRA_REAR_M:
        out.append("Extra side markers every 2.5 m (front) or 3.5 m (rear).")
    if g["proj_side_m"] > R.SIDE_PROJECTION_M:
        out.append(f"Side markers at the widest point (a side overhang over {_g(R.SIDE_PROJECTION_M)} m).")
    if pf > R.CODE_LAMPS_PROJECTION_M or pr > R.CODE_LAMPS_PROJECTION_M:
        out.append("Amber side marker lamps every 3 m. Voluntary.")
    if ln is not None and ln > R.CODE_PLATES_LENGTH_M:
        out.append(f"Lit marker plates front and back (over {_g(R.CODE_PLATES_LENGTH_M)} m long). Voluntary.")
    return out


def answer(body, today=None):
    """The public answer for one typed load: {"advice": the rules' own dict, "page": the words the page shows}.
    Raises Bad with one sentence for a missing or impossible figure."""
    today = today or london_today()
    figs, d, band, nation = read_form(body, today=today)
    a = R.advice(figs, date_from=d.isoformat(), date_to=None, time_band=band, nation=nation,
                 holidays_feed=holidays_feed(), time_bans=None, today=today)
    g = R.figures(figs)
    page = words(a, g, today)
    return {"advice": a, "page": page}


def words(a, g, today):
    """The page's words from the rules' structured answer `a` and the cleaned figures `g`."""
    nt = a["notices"]
    perm = a["permission"]
    chips, notes, fine, rows = [], [], [], []
    late = any(f["code"] == "NOTICE_LATE" for f in a["flags"])
    so_late = any(f["code"] == "SO_LEAD_TIME" for f in a["flags"])
    cu = a["regime"] == "cu"
    # Q8: ticked as an ordinary lorry but over what C&U allows: the rules answer STGO and say why; the page says it first
    reg_note = next((n for n in a["notes"] if n.startswith("The C&U tick is set")), None)
    if reg_note:
        notes.append("Ticked as an ordinary lorry, but " + " and ".join(w for k, w in CEILING_WORDS if k in reg_note)
                     + ": it moves under STGO. Check with the haulier.")
    if cu and a["notify_by"]:
        fine.append(CU_SATURDAY)

    # the short answer only when the rules give no permission and no road-authority notice either: a 31 m long load
    # within the weights and width is "not abnormal" to the rules yet a Special Order case (17 Nov)
    if not a["abnormal"] and perm == "none" and not nt["rba_days"]:
        over = []
        # 17 Nov 2026 (John's yes, the review's B3): with a police notice still due the head says so; it read
        # "Not an abnormal load" beside a "Notify by" chip
        head = NOT_ABNORMAL_NOTICE if nt["police_days"] else NOT_ABNORMAL
        axle_words = f"{_g(R.ABNORMAL_AXLE_T)} t an axle" + (
            f" ({_g(R.ABNORMAL_DRIVING_AXLE_T)} t a driving axle)" if g["axle_driving"] else "")
        notes.append(f"Within the normal limits on these figures: {_g(R.ABNORMAL_GROSS_T)} t gross, "
                     f"{axle_words}, {_g(R.ABNORMAL_WIDTH_M)} m wide. A rigid vehicle over "
                     f"{_g(R.ABNORMAL_RIGID_LENGTH_M)} m long is abnormal too. Check with the haulier.")
        # 17 Nov: the rules' "abnormal" reads gross, axle, width and RIGID length only, so a long combination within them
        # (2.5 m, 28 m, 40 t) is "not abnormal" yet needs a police notice, an attendant and marker plates: the page shows
        # every one of those the rules give, in the same rows as an abnormal load (it hid them before; nothing is invented)
        if nt["police_days"]:
            chips.append(["warn", f"Notify by {_day(a['notify_by'])}" + (": passed" if late else "")])
            rows.append(["Police", f"{nt['police_days']} clear working days' notice to every force on the route."
                         + (f" Receive by {_short(nt['police_by'])}." if nt["police_by"] else "")])
            if late:
                notes.append(f"The last day to notify for this moving day was {_day(a['notify_by'])}. Notices given now "
                             "are too late for it.")
        att = _attendant(g, a["regime"])
        if att:
            rows.append(["Attendant", "Required: " + _and(att) + "."])
        mk = _markers(g)
        if mk:
            rows.append(["Markers", " ".join(mk)])
        esc = a["escort_expected"]
        if esc != "none":
            where = {"all_roads": "on every road", "other_roads": "on roads other than motorways",
                     "motorways": "on motorways"}[esc]
            why = _escort(g, "other") or _escort(g, "motorway")
            rows.append(["Escort", f"Expected {where} ({_and(why)}). The police decide."])
        h = _height(g, perm)
        if h:
            rows.append(["Height", h])
        return {"head": head, "chips": chips, "over": over, "notes": notes, "rows": rows, "fine": fine,
                "next": list(NEXT_WORDS), "last": LAST_LINE}

    # ---- the class
    cat = a["category"]
    head = CU_HEAD if cu else (CLASS_WORDS.get(cat) or "No STGO category fits")
    over = _over_normal(g)

    # ---- the chips: apply by (a Special Order or VR1), notify by
    if perm in ("special_order", "vr1") and a["apply_by"]:
        what = "Special Order" if perm == "special_order" else "VR1"
        if so_late:
            chips.append(["warn", f"Apply for the {what} by {_day(a['apply_by'])}: passed"])
        else:
            chips.append(["warn", f"Apply for the {what} by {_day(a['apply_by'])}"])
    if a["notify_by"]:
        if late:
            chips.append(["warn", f"Notify by {_day(a['notify_by'])}: passed"])
        else:
            chips.append(["warn", f"Notify by {_day(a['notify_by'])}"])

    # ---- the notes above the rows
    if not g["indivisible"]:
        notes.append("Not ticked as a load that cannot be divided. A load that can be divided without undue expense or "
                     "risk cannot move under STGO: tick it once the haulier confirms it.")
    if late:
        notes.append(f"The last day to notify for this moving day was {_day(a['notify_by'])}. Notices given now are "
                     "too late for it.")
    if cat is None and not cu:          # an STGO category note means nothing for a C&U move (Q8)
        why = []
        n = g["axle_count"]
        sp = g["axle_spacings_m"]
        dd = sum(sp) if sp else None
        if n is not None and n < R.CAT2_MIN_AXLES:
            why.append(f"{n} axles: Categories 2 and 3 need at least {R.CAT2_MIN_AXLES}.")
        if dd is not None and g["gross_t"] > dd * R.CAT3_T_PER_METRE:
            why.append(f"{_g(g['gross_t'])} t over {_g(dd)} m between the outer axles is more than "
                       f"{_g(R.CAT3_T_PER_METRE)} t a metre.")
        elif dd is not None and g["gross_t"] > dd * R.CAT2_T_PER_METRE and g["gross_t"] <= R.CAT2_GROSS_T:
            why.append(f"{_g(g['gross_t'])} t over {_g(dd)} m between the outer axles is more than "
                       f"{_g(R.CAT2_T_PER_METRE)} t a metre.")
        notes.append(" ".join(why + ["A vehicle with more axles, a longer axle spread or a Special Order: check with "
                                     "the haulier."]))

    # ---- the rows
    if perm == "special_order":
        so = a["special_order_reasons"]
        rows.append(["Special Order", "Needed: " + _and([_so_words(x) for x in so]) + ". Apply "
                     f"{R.SO_LEAD_WEEKS} weeks ahead (the form itself says {R.SO_LEAD_WEEKS_BE16}: plan on "
                     f"{R.SO_LEAD_WEEKS})" + (f", by {_short(a['apply_by'])}" if a["apply_by"] else "") + ". "
                     "The National Highways Abnormal Loads Team decides; approval is not automatic, and the road may "
                     "be refused where the load can go by water."])
    elif perm == "vr1":
        rows.append(["VR1", f"Needed: over {_g(R.VR1_WIDTH_M)} m wide. Apply {R.VR1_LEAD_WEEKS} weeks ahead"
                     + (f", by {_short(a['apply_by'])}" if a["apply_by"] else "") + ". "
                     "The National Highways Abnormal Loads Team decides; approval is not automatic, and the road may "
                     "be refused where the load can go by water."])
    if nt["police_days"]:
        rows.append(["Police", f"{nt['police_days']} clear working days' notice to every force on the route."
                     + (f" Receive by {_short(nt['police_by'])}." if nt["police_by"] else "")])
    else:
        rows.append(["Police", "No notice from these figures."])
    if nt["rba_days"]:
        rows.append(["Road and bridge authorities", f"{nt['rba_days']} clear days' notice with an indemnity, to every "
                     "authority on the route." + (f" Receive by {_short(nt['rba_by'])}." if nt["rba_by"] else "")])
        nr = R.NR_DAYS_OVER_80 if (g["gross_t"] is not None and g["gross_t"] > R.RBA_WEIGHT_STEP_T) else R.NR_DAYS_UP_TO_80
        rows.append(["Network Rail", f"If the route crosses one of its bridges: {nr} clear working days' notice with "
                     "an indemnity."])
    else:
        rows.append(["Road and bridge authorities", "No notice from these figures."])
        rows.append(["Network Rail", "No notice from these figures."])
    att = _attendant(g, a["regime"])
    rows.append(["Attendant", ("Required: " + _and(att) + ".") if att else "Not needed on these figures."])
    mk = _markers(g)
    rows.append(["Markers", " ".join(mk) if mk else "None from these figures."])
    sp = a["speeds_mph"]
    if cu:
        pass                            # Q8: no Speeds row for a C&U move (the rules give STGO Category 1 speeds even so)
    elif sp:
        rows.append(["Speeds", f"{sp[0]} mph motorway, {sp[1]} dual carriageway, {sp[2]} other roads."])
    elif cat == "special_order":
        rows.append(["Speeds", "Set by the Special Order."])
    else:
        rows.append(["Speeds", "No category fits, so no speeds are given."])
    esc = a["escort_expected"]
    if esc != "none":
        where = {"all_roads": "on every road", "other_roads": "on roads other than motorways",
                 "motorways": "on motorways"}[esc]
        why = _escort(g, "other") or _escort(g, "motorway")
        rows.append(["Escort", f"Expected {where} ({_and(why)}). The police decide."])
    else:
        rows.append(["Escort", "Not expected on these figures. The police decide."])
    h = _height(g, perm)
    rows.append(["Height", h or f"{_g(R.HEIGHT_CAB_NOTICE_M)} m or under: nothing for the height."])

    # ---- the fine lines under the rows
    sp_typed = bool(g["axle_spacings_m"])
    if sp_typed and min(g["axle_spacings_m"]) < R.AXLE_SPACING_MIN_M and not cu:
        fine.append(f"An axle spacing under {_g(R.AXLE_SPACING_MIN_M)} m: Categories 2 and 3 need axles at least "
                    f"{_g(R.AXLE_SPACING_MIN_M)} m apart.")
    if cat in ("cat2", "cat3") and not sp_typed:
        fine.append(SPACINGS_NOT_TYPED)
    return {"head": head, "chips": chips, "over": over, "notes": notes, "rows": rows, "fine": fine,
            "next": list(NEXT_WORDS), "last": LAST_LINE}


def _so_words(reason):
    """'width 6.5 m is over 6.1 m' -> 'over 6.1 m wide' (the rules' Special Order reasons, in the page's words)."""
    if reason.startswith("width"):
        return f"over {_g(R.SO_WIDTH_M)} m wide"
    if reason.startswith("length"):
        return f"over {_g(R.SO_LENGTH_M)} m long"
    if reason.startswith("gross"):
        return f"over {_g(R.SO_GROSS_T)} t gross"
    if reason.startswith("heaviest axle"):
        return f"over {_g(R.SO_AXLE_T)} t on an axle"
    return reason
