"""
abnormal_rules.py — what an ABNORMAL LOAD needs on a GB road, worked out from the typed figures. Wayscope, 22 Oct 2026
(S16 / B5 / P11; the research is notes/abnormal-loads-research-1016.md, not in git — every figure below names its source).

ADVICE, NEVER A VERDICT. Everything here is what the typed width, height, length, projections, gross weight, heaviest
axle and axle count say under the rules as read on 16 Oct 2026. The haulier's own assessment, ESDAL's structure check,
the police and every road and bridge authority decide; this module says "check with the haulier" on every line and never
says a movement meets the rules, is permitted or is approved by anyone (the user's rule: every flag reads as advice).

THE SOURCES (the research note §1, read on gov.uk / legislation.gov.uk / National Highways, 16 Oct 2026)
  STGO        The Road Vehicles (Authorisation of Special Types) (General) Order 2003, SI 2003/1998: Sch 1 (categories,
              width and length ceilings, speeds), Part 2 arts 12–15 (width, length and projection duties), art 17
              (weight notices), art 3(3) (what a working day is), Sch 5 (police notice), Sch 6 (attendants), Sch 7
              (VR1), Sch 9 (road and bridge authorities).
  C&U         The Road Vehicles (Construction and Use) Regulations 1986, SI 1986/1078: reg 7 (lengths), reg 8 (width),
              reg 10 (height notice in the cab), reg 82 (loads over the normal limits), Sch 12 (notices, attendants,
              markers).
  NH page     National Highways, "Abnormal loads and the ESDAL system": what makes a load abnormal.
  Aide memoire National Highways, "Aide Memoire for notification requirements … Abnormal Indivisible Loads", Jan 2022:
              the notice table, the Special Order and VR1 lead times, Note 1 (calendars), Note 2 (4.95 m).
  BE16 / VR1  the forms themselves (Jan 2022 / 01/22): BE16 says 8 weeks where the aide memoire says 10.
  NPCC 2025   NPCC Abnormal Load Guidance 2025 v1.0: §3.12 the 30-day window; §8 escorts are not required by law.
  NH code     National Highways, lighting and marking code of practice for self-escorting vehicles (2021), para 4.4:
              when an escort vehicle is generally expected.
  DfT / NR    Prevention of bridge strikes good practice guides (2012): bridges are signed only below 4.95 m.
  Markers     C&U Sch 12 paras 3–5 (DfT "overhanging loads" sheet); NH lighting and marking code (2021) for the
              voluntary extras.

NOT MODELLED (said on the screen, NOT_MODELLED_WORDS): structures and their ratings (ESDAL and their owners), police
time bans other than the ones a planner types (D72), which forces and authorities the route crosses, level crossings,
overhead lines, swept paths, the light-load Special Order case (a rigid length over 27.4 m on a vehicle of 12 t or
less), mobile-crane categories (STGO Sch 2), the 10 mph engineering-plant speeds, and whether the load really is
indivisible (the planner's declaration).

Pure: no database read, no write, no clock of its own (today is passed in).
"""
import datetime

# --------------------------------------------------------------------------- #
#  The thresholds, each with its source                                        #
# --------------------------------------------------------------------------- #
#: NH page / AWR 1998: gross weight over 44,000 kg is abnormal
ABNORMAL_GROSS_T = 44.0
#: NH page: a single non-driving axle over 10,000 kg, a driving axle over 11,500 kg
ABNORMAL_AXLE_T = 10.0
ABNORMAL_DRIVING_AXLE_T = 11.5
#: NH page / C&U reg 82(1): width over 2.9 m is abnormal (the normal limit is 2.55 m, reg 8)
ABNORMAL_WIDTH_M = 2.9
#: NH page / C&U reg 82(3): rigid length over 18.65 m is abnormal
ABNORMAL_RIGID_LENGTH_M = 18.65

#: C&U reg 82(1): an indivisible load may be up to 4.3 m wide under C&U (police notice, side markers)
CU_WIDTH_MAX_M = 4.3
#: C&U reg 82(3): a load resting on vehicles may be up to 27.4 m long under C&U
CU_LENGTH_MAX_M = 27.4
#: C&U reg 82(3): over 25.9 m for a trailer combination, Sch 12 paras 1 and 2 apply
CU_COMBINATION_M = 25.9

#: STGO Part 2 art 12: width over 3.0 m needs a police notice; art 12(2) a rigid unit over 18.75 m; art 12(3) a
#: combination over 25.9 m (both police notice and attendant)
STGO_POLICE_WIDTH_M = 3.0
STGO_RIGID_M = 18.75
STGO_COMBINATION_M = 25.9
#: STGO Sch 6 / C&U Sch 12 para 2: width over 3.5 m needs an attendant
ATTENDANT_WIDTH_M = 3.5
#: STGO art 13 / C&U Sch 12: a front or rear projection over 3.05 m needs a police notice; art 14: an attendant when the
#: front projection is over 2 m or the rear over 3.05 m
PROJECTION_POLICE_M = 3.05
PROJECTION_FRONT_ATTENDANT_M = 2.0
PROJECTION_REAR_ATTENDANT_M = 3.05
#: C&U Sch 12 para 5 / STGO art 12: a lateral projection over 305 mm needs a police notice and side markers
SIDE_PROJECTION_M = 0.305

#: STGO art 15(5)(a), Sch 7 and the VR1 form: width over 5.0 m needs the Secretary of State's consent (VR1) …
VR1_WIDTH_M = 5.0
#: … and STGO Sch 1 para 24 caps width at 6.1 m: over it is a Special Order
SO_WIDTH_M = 6.1
#: STGO Sch 1 para 25: length at most 30 m; the aide memoire and BE16: over 30 m is a Special Order
SO_LENGTH_M = 30.0
#: STGO Sch 1 para 32 / aide memoire / BE16: gross over 150,000 kg is a Special Order
SO_GROSS_T = 150.0
#: STGO Sch 1 para 33 / aide memoire: any axle over 16,500 kg is a Special Order
SO_AXLE_T = 16.5

#: STGO Sch 1 para 28: Category 1 up to 46,000 kg (5 axles) or 50,000 kg (6 or more); para 29: at least 5 axles
CAT1_GROSS_5_AXLES_T = 46.0
CAT1_GROSS_6_AXLES_T = 50.0
CAT1_MIN_AXLES = 5
#: STGO Sch 1 para 30: Category 2 up to 80,000 kg (or D × 7,500 kg if lower); para 31: at least 6 axles, an axle at most
#: 12,500 kg (12,000 kg where the axle spacing is under 1.35 m)
CAT2_GROSS_T = 80.0
CAT2_T_PER_METRE = 7.5
CAT2_MIN_AXLES = 6
CAT2_AXLE_T = 12.5
CAT2_AXLE_CLOSE_T = 12.0
#: STGO Sch 1 para 32: Category 3 up to 150,000 kg (or D × 12,500 kg if lower); para 33: at least 6 axles, an axle at
#: most 16,500 kg (15,000 kg where the spacing is under 1.35 m)
CAT3_GROSS_T = 150.0
CAT3_T_PER_METRE = 12.5
CAT3_MIN_AXLES = 6
CAT3_AXLE_T = 16.5
CAT3_AXLE_CLOSE_T = 15.0
#: STGO Sch 1 paras 31 and 33: the closer-spacing axle limits apply under 1.35 m; adjacent axles at least 1 m apart
AXLE_SPACING_CLOSE_M = 1.35
AXLE_SPACING_MIN_M = 1.0

#: STGO Sch 1 para 34, Table 3: Category 1 60 / 50 / 40 mph (motorway / dual carriageway / other), Categories 2 and 3
#: 40 / 35 / 30
SPEEDS_MPH = {"cat1": (60, 50, 40), "cat2": (40, 35, 30), "cat3": (40, 35, 30)}

#: Aide memoire (and STGO Sch 9): road and bridge authorities 2 clear working days up to and including 80 t, 5 days over
#: 80 t, with an indemnity; art 17: the duty starts over 44 t (or axles outside the normal limits)
RBA_DAYS_UP_TO_80 = 2
RBA_DAYS_OVER_80 = 5
RBA_WEIGHT_STEP_T = 80.0
#: Aide memoire (and STGO Sch 5): police 2 clear working days — for weight only over 80 t up to 150 t; 5 clear working
#: days for the Special Order cases
POLICE_DAYS = 2
POLICE_DAYS_SO = 5
POLICE_WEIGHT_T = 80.0
#: Network Rail (a bridge authority): 2 clear working days up to 80 t, 5 over, plus an indemnity — only where the route
#: crosses one of its bridges, which this module does not know (said as a conditional line)
NR_DAYS_UP_TO_80 = 2
NR_DAYS_OVER_80 = 5
#: Aide memoire: a Special Order is applied for 10 weeks ahead; the BE16 form itself says 8 (a conflict: plan on 10)
SO_LEAD_WEEKS = 10
SO_LEAD_WEEKS_BE16 = 8
#: Aide memoire / the VR1 form: a VR1 is applied for 2 weeks ahead
VR1_LEAD_WEEKS = 2
#: NPCC 2025 §3.12: forces should normally accept a 30-day window for the move date
POLICE_WINDOW_DAYS = 30

#: NH code of practice (2021) para 4.4: an escort vehicle is generally expected over these (forces differ; the police decide)
ESCORT_MOTORWAY_WIDTH_M = 4.6
ESCORT_MOTORWAY_GROSS_T = 130.0
ESCORT_OTHER_WIDTH_M = 4.1
ESCORT_OTHER_LENGTH_M = 30.5
ESCORT_OTHER_GROSS_T = 100.0

#: C&U reg 10: a vehicle over 3 m travelling height shows its height in the cab
HEIGHT_CAB_NOTICE_M = 3.0
#: Aide memoire Note 2 / the bridge-strike guides: bridges are signed only below 4.95 m (16 ft 3 in); a load over it is
#: checked with the highway authorities and a Special Order or VR1 load stays within it where possible
HEIGHT_CHECK_M = 4.95
#: NH advice for hauliers: the High Load Grid takes loads of 18 ft (5.486 m) and 20 ft (6.096 m)
HIGH_LOAD_GRID_M = (5.486, 6.096)

#: C&U Sch 12 paras 3–4 (the DfT overhanging-loads sheet): a rear projection over 1 m is made clearly visible; over 2 m
#: (front or rear) an end marker; front over 2 m or rear over 3 m side markers too; front over 4.5 m or rear over 5 m
#: extra side markers every 2.5 m (front) or 3.5 m (rear)
MARKER_REAR_VISIBLE_M = 1.0
MARKER_END_M = 2.0
MARKER_SIDE_FRONT_M = 2.0
MARKER_SIDE_REAR_M = 3.0
MARKER_EXTRA_FRONT_M = 4.5
MARKER_EXTRA_REAR_M = 5.0
#: NH lighting and marking code (2021), voluntary: projections over 6 m carry amber side marker lamps every 3 m; loads
#: over 18.3 m carry lit marker plates front and back
CODE_LAMPS_PROJECTION_M = 6.0
CODE_PLATES_LENGTH_M = 18.3

#: the move's time band, as hours of the day, for the typed police time bans (D72) — a planning convention, not a rule
TIME_BANDS = {"day": ("06:00", "20:00"), "night": ("20:00", "06:00")}

STATUSES = ("pending", "approved", "notified", "moved", "withdrawn")
STATUS_WORDS = {"pending": "Pending", "approved": "Approved", "notified": "Notified", "moved": "Moved",
                "withdrawn": "Withdrawn"}
ESCORTS = ("none", "attendant", "private", "police")
VEHICLE_TYPES = ("low_loader", "modular_trailer", "spmt", "mobile_crane", "other")
VEHICLE_WORDS = {"low_loader": "Low-loader", "modular_trailer": "Modular trailer",
                 "spmt": "Self-propelled modular transporter", "mobile_crane": "Mobile crane (self-drive)",
                 "other": "Other"}
CALENDAR_WORDS = {
    "stgo": "STGO clear working days: Saturdays, Sundays and public holidays in any part of Great Britain do not count "
            "(STGO 2003 art 3(3))",
    "cu": "C&U working days: Sundays, bank holidays, Christmas Day and Good Friday do not count — a Saturday does "
          "(C&U Sch 12 para 1)",
    "calendar": "calendar days: a Special Order counts every day unless the order says otherwise (aide memoire Note 1)",
}
ADVICE_WORDS = ("Advice worked out from the typed figures under the rules as read on 16 Oct 2026. Check with the "
                "haulier: ESDAL, the police and the road and bridge authorities decide.")
NOT_MODELLED_WORDS = ("Not worked out here: bridges and structures and their ratings (checked by their owners through "
                      "ESDAL), which police forces and authorities the route crosses, police time bans other than the "
                      "ones typed for this scheme, level crossings, overhead lines, swept paths and whether the load is "
                      "indivisible.")
NOT_ABNORMAL_WORDS = ("Within the normal limits on the typed figures (44 t gross, 10 t an axle or 11.5 t driving, "
                      "2.9 m wide, 18.65 m rigid): not an abnormal load. Check with the haulier.")

#: the 5 working days the NOTICE_DUE flag looks ahead (the Look-ahead's rail; the research note §5.5)
NOTICE_DUE_WORKING_DAYS = 5


# --------------------------------------------------------------------------- #
#  Small helpers                                                               #
# --------------------------------------------------------------------------- #
def _num(v):
    """A typed figure as a float, or None for blank / not a number / negative."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x >= 0 else None


def _int(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _date(v):
    if isinstance(v, datetime.date):
        return v
    if not v:
        return None
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _iso(d):
    return d.isoformat() if isinstance(d, datetime.date) else None


def spacings_of(v):
    """A typed list of axle spacings in metres ('1.36, 1.36, 1.8' or a list) as floats; [] when none typed."""
    if v in (None, ""):
        return []
    items = v if isinstance(v, (list, tuple)) else str(v).replace(";", ",").split(",")
    out = []
    for x in items:
        n = _num(x)
        if n is not None and n > 0:
            out.append(n)
    return out


def figures(f):
    """The typed figures, cleaned: a dict of floats (None where blank), ints, bools and the spacing list."""
    f = f or {}
    return {
        "width_m": _num(f.get("width_m")), "height_m": _num(f.get("height_m")), "length_m": _num(f.get("length_m")),
        "rigid_length_m": _num(f.get("rigid_length_m")),
        "proj_front_m": _num(f.get("proj_front_m")) or 0.0, "proj_rear_m": _num(f.get("proj_rear_m")) or 0.0,
        "proj_side_m": _num(f.get("proj_side_m")) or 0.0,
        "gross_t": _num(f.get("gross_t")), "max_axle_t": _num(f.get("max_axle_t")),
        "axle_driving": bool(f.get("axle_driving")), "axle_count": _int(f.get("axle_count")),
        "axle_spacings_m": spacings_of(f.get("axle_spacings_m")),
        "cu_vehicle": bool(f.get("cu_vehicle")), "indivisible": bool(f.get("indivisible")),
    }


# --------------------------------------------------------------------------- #
#  Is it abnormal, and what regime                                             #
# --------------------------------------------------------------------------- #
def axle_limit_t(driving):
    return ABNORMAL_DRIVING_AXLE_T if driving else ABNORMAL_AXLE_T


def abnormal_reasons(g):
    """Why the typed figures make the load abnormal (NH page): [] when it is within the normal limits."""
    out = []
    if g["gross_t"] is not None and g["gross_t"] > ABNORMAL_GROSS_T:
        out.append(f"gross weight {g['gross_t']:g} t is over {ABNORMAL_GROSS_T:g} t")
    lim = axle_limit_t(g["axle_driving"])
    if g["max_axle_t"] is not None and g["max_axle_t"] > lim:
        out.append(f"heaviest axle {g['max_axle_t']:g} t is over {lim:g} t ({'driving' if g['axle_driving'] else 'non-driving'})")
    if g["width_m"] is not None and g["width_m"] > ABNORMAL_WIDTH_M:
        out.append(f"width {g['width_m']:g} m is over {ABNORMAL_WIDTH_M:g} m")
    if g["rigid_length_m"] is not None and g["rigid_length_m"] > ABNORMAL_RIGID_LENGTH_M:
        out.append(f"rigid length {g['rigid_length_m']:g} m is over {ABNORMAL_RIGID_LENGTH_M:g} m")
    return out


def special_order_reasons(g):
    """The Special Order cases (aide memoire; STGO Sch 1 paras 24, 25, 32, 33)."""
    out = []
    if g["width_m"] is not None and g["width_m"] > SO_WIDTH_M:
        out.append(f"width {g['width_m']:g} m is over {SO_WIDTH_M:g} m")
    if g["length_m"] is not None and g["length_m"] > SO_LENGTH_M:
        out.append(f"length {g['length_m']:g} m is over {SO_LENGTH_M:g} m")
    if g["gross_t"] is not None and g["gross_t"] > SO_GROSS_T:
        out.append(f"gross weight {g['gross_t']:g} t is over {SO_GROSS_T:g} t")
    if g["max_axle_t"] is not None and g["max_axle_t"] > SO_AXLE_T:
        out.append(f"heaviest axle {g['max_axle_t']:g} t is over {SO_AXLE_T:g} t")
    return out


def weights_within_normal(g):
    """Gross at or under 44 t and the heaviest axle within the normal axle limits (or not typed)."""
    if g["gross_t"] is not None and g["gross_t"] > ABNORMAL_GROSS_T:
        return False
    if g["max_axle_t"] is not None and g["max_axle_t"] > axle_limit_t(g["axle_driving"]):
        return False
    return True


def regime(g, so):
    """
    'cu' when the planner ticks a vehicle within the C&U limits AND the figures sit within what C&U reg 82 allows a load
    to exceed (4.3 m wide, 27.4 m long, 25.9 m for a trailer combination, the normal weights); 'stgo' otherwise;
    'special_order' for the Special Order cases. Returns (regime, note or None).
    """
    if so:
        return "special_order", None
    if not g["cu_vehicle"]:
        return "stgo", None
    over = []
    if g["width_m"] is not None and g["width_m"] > CU_WIDTH_MAX_M:
        over.append(f"width over the C&U ceiling of {CU_WIDTH_MAX_M:g} m")
    ln = g["rigid_length_m"] if g["rigid_length_m"] is not None else g["length_m"]
    if ln is not None and ln > CU_LENGTH_MAX_M:
        over.append(f"length over the C&U ceiling of {CU_LENGTH_MAX_M:g} m")
    if not weights_within_normal(g):
        over.append("weights over the normal limits (C&U vehicles carry at most 44 t)")
    if over:
        return "stgo", "The C&U tick is set, but " + "; ".join(over) + ": STGO applies (C&U reg 82). Check with the haulier."
    return "cu", None


# --------------------------------------------------------------------------- #
#  The STGO weight category                                                    #
# --------------------------------------------------------------------------- #
def category(g, so):
    """
    {"category": 'cat1'|'cat2'|'cat3'|'special_order'|None, "words", "needs": [what is missing], "notes": []}
    The category is by weight (STGO Sch 1). It needs the axle count; the per-metre caps and the closer-spacing axle
    limits need the spacings, and without them the category says what it did not test rather than guess (the research
    note §5.2: "needs axle details").
    """
    out = {"category": None, "words": None, "needs": [], "notes": []}
    gross, axle, n, sp = g["gross_t"], g["max_axle_t"], g["axle_count"], g["axle_spacings_m"]
    if gross is None:
        out["needs"].append("gross weight")
        out["words"] = "needs the gross weight"
        return out
    if so:
        out["category"] = "special_order"
        out["words"] = "Special Order (outside the STGO categories)"
        return out
    if n is None:
        out["needs"].append("axle count")
    close = bool(sp) and min(sp) < AXLE_SPACING_CLOSE_M
    if sp and min(sp) < AXLE_SPACING_MIN_M:
        out["notes"].append(f"an axle spacing under {AXLE_SPACING_MIN_M:g} m: STGO Categories 2 and 3 need adjacent axles at "
                            f"least {AXLE_SPACING_MIN_M:g} m apart (Sch 1 paras 31, 33)")
    d = sum(sp) if sp else None          # the distance between the foremost and rearmost axles, when the spacings are typed
    cat2_axle = CAT2_AXLE_CLOSE_T if close else CAT2_AXLE_T
    cat3_axle = CAT3_AXLE_CLOSE_T if close else CAT3_AXLE_T
    # Category 1: 46 t on 5 axles, 50 t on 6 or more; axles within the normal limits
    cat1_gross = CAT1_GROSS_6_AXLES_T if (n is not None and n >= 6) else CAT1_GROSS_5_AXLES_T
    axle_ok = axle is None or axle <= axle_limit_t(g["axle_driving"])
    if gross <= cat1_gross and axle_ok and (n is None or n >= CAT1_MIN_AXLES):
        out["category"] = "cat1"
        out["words"] = f"STGO Category 1 (up to {cat1_gross:g} t on {'6 or more' if cat1_gross == CAT1_GROSS_6_AXLES_T else 'at least 5'} axles)"
        if n is None:
            out["notes"].append(f"on 5 axles Category 1 ends at {CAT1_GROSS_5_AXLES_T:g} t, on 6 or more at {CAT1_GROSS_6_AXLES_T:g} t: type the axle count")
        return out
    if gross <= CAT2_GROSS_T and (axle is None or axle <= cat2_axle) and (n is None or n >= CAT2_MIN_AXLES) \
            and (d is None or gross <= d * CAT2_T_PER_METRE):
        out["category"] = "cat2"
        out["words"] = f"STGO Category 2 (up to {CAT2_GROSS_T:g} t, {cat2_axle:g} t an axle, at least {CAT2_MIN_AXLES} axles)"
    elif gross <= CAT3_GROSS_T and (axle is None or axle <= cat3_axle) and (n is None or n >= CAT3_MIN_AXLES) \
            and (d is None or gross <= d * CAT3_T_PER_METRE):
        out["category"] = "cat3"
        out["words"] = f"STGO Category 3 (up to {CAT3_GROSS_T:g} t, {cat3_axle:g} t an axle, at least {CAT3_MIN_AXLES} axles)"
    else:
        # within 150 t and 16.5 t an axle, yet no category fits: too few axles, or the per-metre cap
        out["category"] = None
        why = []
        if n is not None and n < CAT2_MIN_AXLES:
            why.append(f"{n} axles: Categories 2 and 3 need at least {CAT2_MIN_AXLES}")
        if d is not None and gross > d * CAT3_T_PER_METRE:
            why.append(f"{gross:g} t over {d:g} m between the outer axles is more than {CAT3_T_PER_METRE:g} t a metre (Sch 1 para 32)")
        elif d is not None and gross > d * CAT2_T_PER_METRE and gross <= CAT2_GROSS_T:
            why.append(f"{gross:g} t over {d:g} m between the outer axles is more than {CAT2_T_PER_METRE:g} t a metre (Sch 1 para 30)")
        out["words"] = "no STGO category fits the typed figures" + (": " + "; ".join(why) if why else "")
        out["notes"].append("a vehicle with more axles, a longer axle spread or a Special Order: check with the haulier")
        return out
    if not sp:
        out["notes"].append(f"the per-metre caps ({CAT2_T_PER_METRE:g} t a metre for Category 2, {CAT3_T_PER_METRE:g} for Category 3, "
                            f"Sch 1 paras 30 and 32) and the {AXLE_SPACING_CLOSE_M:g} m closer-spacing axle limits are not tested: type the axle spacings")
    if axle is None:
        out["needs"].append("heaviest axle")
        out["notes"].append(f"the heaviest axle is not typed: Category 2 allows {CAT2_AXLE_T:g} t, Category 3 {CAT3_AXLE_T:g} t, a Special Order over that")
    return out


# --------------------------------------------------------------------------- #
#  Working days and the "notify by" date                                       #
# --------------------------------------------------------------------------- #
def holiday_dates(feed, divisions):
    """The dates (datetime.date) of the gov.uk feed's events in the given divisions."""
    out = set()
    for div in divisions:
        for ev in ((feed or {}).get(div) or {}).get("events") or []:
            d = _date((ev or {}).get("date"))
            if d:
                out.add(d)
    return out


def calendar_divisions(calendar, nation="england-and-wales"):
    """
    Which of the feed's divisions a calendar reads. STGO: a public holiday in ANY part of Great Britain, so England and
    Wales AND Scotland; C&U: the bank holidays where the movement is (NPCC 2025 §3.6), the tenant's nation.
    """
    if calendar == "stgo":
        return ("england-and-wales", "scotland")
    if calendar == "cu":
        return (nation or "england-and-wales",)
    return ()


def is_working_day(d, calendar, holidays):
    """STGO: not Saturday, Sunday or a GB public holiday. C&U: not Sunday or a bank holiday (Saturday counts). Calendar
    days: every day."""
    if calendar == "calendar":
        return True
    if d.weekday() == 6:
        return False
    if calendar == "stgo" and d.weekday() == 5:
        return False
    return d not in holidays


def notify_by(move_date, clear_days, calendar, holidays):
    """
    The latest day a notice can be received: N CLEAR working days must lie between it and the move. The clear days are
    the N working days immediately before the move (STGO Sch 5: received before the start of the period ending before
    the date of use); the notice day is the calendar day before the earliest of them, whatever day that is.
    """
    move_date = _date(move_date)
    if not move_date or not clear_days:
        return None
    d = move_date - datetime.timedelta(days=1)
    earliest, n = None, 0
    while n < clear_days:
        if is_working_day(d, calendar, holidays):
            n += 1
            earliest = d
        d -= datetime.timedelta(days=1)
        if (move_date - d).days > 400:            # a feed with no working days at all: never loop for ever
            return None
    return earliest - datetime.timedelta(days=1)


def working_days_before(d, n, calendar, holidays):
    """The date n working days before d (the NOTICE_DUE window's start)."""
    d = _date(d)
    k = 0
    while k < n:
        d -= datetime.timedelta(days=1)
        if is_working_day(d, calendar, holidays):
            k += 1
    return d


# --------------------------------------------------------------------------- #
#  Everything, for one movement                                                #
# --------------------------------------------------------------------------- #
def advice(f, date_from=None, date_to=None, time_band="day", escort_planned=None, applied_on=None, notified_on=None,
           status="pending", today=None, holidays_feed=None, nation="england-and-wales", time_bans=None):
    """
    The advice for one movement: {abnormal, reasons, regime, permission, category, notices, notify_by, apply_by,
    attendant, markers, speeds, escort_expected, height, lines, flags, words}. Dates in and out are ISO strings.
    """
    g = figures(f)
    today = _date(today) or datetime.date.today()
    d_from, d_to = _date(date_from), _date(date_to)
    reasons = abnormal_reasons(g)
    so = special_order_reasons(g)
    reg, reg_note = regime(g, so)
    cat = category(g, so)
    lines = []                       # the advice lines a person reads, in order
    notes = []                       # softer notes (what is missing, what is not tested)
    if reg_note:
        notes.append(reg_note)
    notes += cat["notes"]

    # ---- the permission needed, and its lead time
    permission, apply_by, apply_by_be16, lead_words = "none", None, None, None
    if so:
        permission = "special_order"
        lead_words = (f"Special Order (BE16): apply {SO_LEAD_WEEKS} weeks ahead (the aide memoire; the BE16 form itself says "
                      f"{SO_LEAD_WEEKS_BE16}: plan on {SO_LEAD_WEEKS})")
        if d_from:
            apply_by = d_from - datetime.timedelta(weeks=SO_LEAD_WEEKS)
            apply_by_be16 = d_from - datetime.timedelta(weeks=SO_LEAD_WEEKS_BE16)
        lines.append("Special Order needed: " + "; ".join(so) + ". The National Highways Abnormal Loads Team decides; "
                     "approval is not automatic, and road may be refused where water is feasible.")
    elif g["width_m"] is not None and g["width_m"] > VR1_WIDTH_M:
        permission = "vr1"
        lead_words = f"VR1 (width over {VR1_WIDTH_M:g} m up to {SO_WIDTH_M:g} m): apply {VR1_LEAD_WEEKS} weeks ahead"
        if d_from:
            apply_by = d_from - datetime.timedelta(weeks=VR1_LEAD_WEEKS)
        lines.append(f"VR1 consent needed: width {g['width_m']:g} m is over {VR1_WIDTH_M:g} m (STGO art 15(5), Sch 7). "
                     "The National Highways Abnormal Loads Team decides; approval is not automatic, and road may be refused "
                     "where water is feasible.")

    # ---- the notices (the aide memoire table)
    gross = g["gross_t"]
    # art 17: over 44 t or axles outside the normal limits; the aide memoire: every Special Order case too (5 days)
    rba_needed = (gross is not None and gross > ABNORMAL_GROSS_T) or not weights_within_normal(g) or bool(so)
    rba_days = None
    if rba_needed:
        rba_days = RBA_DAYS_OVER_80 if (so or (gross is not None and gross > RBA_WEIGHT_STEP_T)) else RBA_DAYS_UP_TO_80
    police_triggers = []
    if so:
        police_triggers.append("a Special Order case")
    if gross is not None and POLICE_WEIGHT_T < gross:
        police_triggers.append(f"gross weight over {POLICE_WEIGHT_T:g} t")
    w = g["width_m"]
    if w is not None:
        if reg == "cu" and w > ABNORMAL_WIDTH_M:
            police_triggers.append(f"width over {ABNORMAL_WIDTH_M:g} m (C&U)")
        elif reg != "cu" and w > STGO_POLICE_WIDTH_M:
            police_triggers.append(f"width over {STGO_POLICE_WIDTH_M:g} m (STGO)")
    if g["proj_side_m"] > SIDE_PROJECTION_M:
        police_triggers.append(f"a lateral projection over {SIDE_PROJECTION_M:g} m")
    rl, ln = g["rigid_length_m"], g["length_m"]
    if reg == "cu":
        if (rl if rl is not None else ln) is not None and (rl if rl is not None else ln) > ABNORMAL_RIGID_LENGTH_M:
            police_triggers.append(f"length over {ABNORMAL_RIGID_LENGTH_M:g} m (C&U)")
    else:
        if rl is not None and rl > STGO_RIGID_M:
            police_triggers.append(f"rigid length over {STGO_RIGID_M:g} m (STGO)")
        if ln is not None and ln > STGO_COMBINATION_M:
            police_triggers.append(f"overall length over {STGO_COMBINATION_M:g} m (STGO)")
    if g["proj_front_m"] > PROJECTION_POLICE_M or g["proj_rear_m"] > PROJECTION_POLICE_M:
        police_triggers.append(f"a front or rear projection over {PROJECTION_POLICE_M:g} m")
    police_days = (POLICE_DAYS_SO if so else POLICE_DAYS) if police_triggers else None
    calendar = "calendar" if so else ("cu" if reg == "cu" else "stgo")
    hol = holiday_dates(holidays_feed, calendar_divisions(calendar, nation))
    police_by = notify_by(d_from, police_days, calendar, hol) if police_days else None
    rba_by = notify_by(d_from, rba_days, calendar, hol) if rba_days else None
    nb = min([x for x in (police_by, rba_by) if x], default=None)
    if police_days:
        lines.append(f"Police notice: {police_days} clear working days to every force on the route ({'; '.join(police_triggers)})"
                     + (f"; receive by {police_by.isoformat()}" if police_by else "") + ".")
    if rba_days:
        why_rba = "a Special Order case" if so else f"gross over {ABNORMAL_GROSS_T:g} t or an axle over the normal limit, STGO art 17"
        lines.append(f"Road and bridge authorities: {rba_days} clear days' notice with an indemnity to every authority on the "
                     f"route ({why_rba})" + (f"; receive by {rba_by.isoformat()}" if rba_by else "") + ".")
        nr_days = NR_DAYS_OVER_80 if (gross is not None and gross > RBA_WEIGHT_STEP_T) else NR_DAYS_UP_TO_80
        lines.append(f"Network Rail, if the route crosses one of its bridges: {nr_days} clear working days with an indemnity.")
    if not police_days and not rba_days and reasons:
        lines.append("No police or road-authority notice from the typed figures alone (weight at or under 80 t needs none "
                     "for weight; width and length below the notice bands). Check with the haulier.")
    if nb:
        lines.append(f"Notify by {nb.isoformat()} ({CALENDAR_WORDS[calendar]}).")

    # ---- attendant, markers, speeds, escort, height
    att = []
    if w is not None and w > ATTENDANT_WIDTH_M:
        att.append(f"width over {ATTENDANT_WIDTH_M:g} m")
    rigid_limit = ABNORMAL_RIGID_LENGTH_M if reg == "cu" else STGO_RIGID_M
    if rl is not None and rl > rigid_limit:
        att.append(f"rigid length over {rigid_limit:g} m")
    if ln is not None and ln > STGO_COMBINATION_M:
        att.append(f"length over {STGO_COMBINATION_M:g} m")
    if g["proj_front_m"] > PROJECTION_FRONT_ATTENDANT_M:
        att.append(f"front projection over {PROJECTION_FRONT_ATTENDANT_M:g} m")
    if g["proj_rear_m"] > PROJECTION_REAR_ATTENDANT_M:
        att.append(f"rear projection over {PROJECTION_REAR_ATTENDANT_M:g} m")
    attendant = bool(att)
    if attendant:
        lines.append("Attendant required (STGO Sch 6 / C&U Sch 12): " + "; ".join(att) + ".")
    markers = []
    pf, pr = g["proj_front_m"], g["proj_rear_m"]
    if pr > MARKER_REAR_VISIBLE_M and pr <= MARKER_END_M:
        markers.append(f"rear projection over {MARKER_REAR_VISIBLE_M:g} m: make the end clearly visible")
    if pf > MARKER_END_M or pr > MARKER_END_M:
        markers.append("end marker board(s) (projection over 2 m)")
    if pf > MARKER_SIDE_FRONT_M or pr > MARKER_SIDE_REAR_M:
        markers.append("side marker boards (front over 2 m or rear over 3 m)")
    if pf > MARKER_EXTRA_FRONT_M or pr > MARKER_EXTRA_REAR_M:
        markers.append("extra side markers every 2.5 m (front) or 3.5 m (rear)")
    if g["proj_side_m"] > SIDE_PROJECTION_M:
        markers.append(f"side markers at the widest point (lateral projection over {SIDE_PROJECTION_M:g} m)")
    if pf > CODE_LAMPS_PROJECTION_M or pr > CODE_LAMPS_PROJECTION_M:
        markers.append("amber side marker lamps every 3 m (NH code of practice, voluntary)")
    if ln is not None and ln > CODE_PLATES_LENGTH_M:
        markers.append(f"lit marker plates front and back (over {CODE_PLATES_LENGTH_M:g} m, NH code of practice, voluntary)")
    if markers:
        lines.append("Marking: " + "; ".join(markers) + ".")
    speeds = SPEEDS_MPH.get(cat["category"])
    if speeds:
        lines.append(f"Speed limits (STGO Sch 1 para 34): {speeds[0]} mph motorway, {speeds[1]} dual carriageway, {speeds[2]} other roads.")
    esc = {"motorway": [], "other": []}
    if w is not None and w > ESCORT_MOTORWAY_WIDTH_M:
        esc["motorway"].append(f"width over {ESCORT_MOTORWAY_WIDTH_M:g} m")
    if gross is not None and gross > ESCORT_MOTORWAY_GROSS_T:
        esc["motorway"].append(f"gross over {ESCORT_MOTORWAY_GROSS_T:g} t")
    if w is not None and w > ESCORT_OTHER_WIDTH_M:
        esc["other"].append(f"width over {ESCORT_OTHER_WIDTH_M:g} m")
    if ln is not None and ln > ESCORT_OTHER_LENGTH_M:
        esc["other"].append(f"length over {ESCORT_OTHER_LENGTH_M:g} m")
    if gross is not None and gross > ESCORT_OTHER_GROSS_T:
        esc["other"].append(f"gross over {ESCORT_OTHER_GROSS_T:g} t")
    escort_expected = "none"
    if esc["motorway"] and esc["other"]:
        escort_expected = "all_roads"
    elif esc["other"]:
        escort_expected = "other_roads"
    elif esc["motorway"]:
        escort_expected = "motorways"
    if escort_expected != "none":
        where = {"all_roads": "on every road", "other_roads": "on roads other than motorways", "motorways": "on motorways"}[escort_expected]
        lines.append(f"Escort vehicle expected {where} (National Highways code of practice para 4.4: "
                     + "; ".join(esc["other"] or esc["motorway"]) + "). No law requires an escort; the police decide.")
        if escort_planned in (None, "", "none"):
            notes.append("no escort is planned for this movement: say what the haulier will provide")
    h = g["height_m"]
    height = []
    if h is not None and h > HEIGHT_CAB_NOTICE_M:
        height.append(f"over {HEIGHT_CAB_NOTICE_M:g} m: the travelling height is shown in the cab (C&U reg 10)")
    if h is not None and h > HEIGHT_CHECK_M:
        height.append(f"over {HEIGHT_CHECK_M:g} m: check every bridge and overhead structure with the highway authorities — "
                      f"bridges are signed only below {HEIGHT_CHECK_M:g} m, so an unsigned one can still be too low"
                      + (f"; a Special Order or VR1 load stays within {HEIGHT_CHECK_M:g} m where possible" if permission != "none" else ""))
    if h is not None and h > HIGH_LOAD_GRID_M[1]:
        height.append(f"over {HIGH_LOAD_GRID_M[1]:g} m (20 ft): beyond the High Load Grid")
    elif h is not None and h > HIGH_LOAD_GRID_M[0]:
        height.append(f"over {HIGH_LOAD_GRID_M[0]:g} m (18 ft): a High Load Grid route (20 ft routes take it)")
    if height:
        lines.append("Height: " + "; ".join(height) + ".")

    # ---- the window, the declaration, the typed time bans
    if d_from and d_to and (d_to - d_from).days > POLICE_WINDOW_DAYS:
        notes.append(f"the move window is longer than the {POLICE_WINDOW_DAYS} days the police normally accept (NPCC 2025 §3.12)")
    if d_from and d_to and d_to < d_from:
        notes.append("the window ends before it starts")
    if reasons and not g["indivisible"]:
        notes.append("not declared indivisible: a load that can be divided without undue expense or risk cannot move under STGO "
                     "(Sch 1 para 2) — tick the declaration once the haulier confirms it")
    bans = []
    band = TIME_BANDS.get(time_band or "day", TIME_BANDS["day"])
    for b in time_bans or []:
        if _bands_overlap(band, ((b or {}).get("from") or "", (b or {}).get("to") or "")):
            days = (b or {}).get("days") or "1111100"
            bans.append(f"{b.get('force') or 'a force'}: no abnormal loads {b.get('from')}–{b.get('to')} on {_days_words(days)}"
                        + (f" ({b['note']})" if b.get("note") else ""))
    if bans:
        lines.append(f"Police time bans typed for this scheme that touch a {time_band} move: " + "; ".join(bans)
                     + ". Which forces the route crosses is not worked out here.")

    # ---- the flags (the Look-ahead's rail reads these)
    flags = []
    live = status in ("pending", "approved")
    if nb and live:
        if today > nb:
            flags.append({"code": "NOTICE_LATE", "text": f"notify by {nb.isoformat()} has passed and the movement is not marked notified"})
        elif today >= working_days_before(nb, NOTICE_DUE_WORKING_DAYS, "stgo", holiday_dates(holidays_feed, calendar_divisions("stgo"))):
            flags.append({"code": "NOTICE_DUE", "text": f"notify by {nb.isoformat()}"})
    if apply_by and live and not _date(applied_on) and today > apply_by:
        flags.append({"code": "SO_LEAD_TIME", "text": (f"{'Special Order' if permission == 'special_order' else 'VR1'} not applied for and "
                                                        f"the lead time has started (apply by {apply_by.isoformat()})")})

    # ---- the summary words
    if not reasons:
        summary = "Not abnormal on the typed figures"
    else:
        bits = []
        if permission == "special_order":
            bits.append("Special Order")
        elif permission == "vr1":
            bits.append("VR1")
        if cat["category"] in ("cat1", "cat2", "cat3"):
            bits.append({"cat1": "STGO Cat 1", "cat2": "STGO Cat 2", "cat3": "STGO Cat 3"}[cat["category"]])
        elif reg == "cu":
            bits.append("C&U")
        if police_days:
            bits.append(f"police {police_days} days")
        if rba_days:
            bits.append(f"authorities {rba_days} days")
        if attendant:
            bits.append("attendant")
        if escort_expected != "none":
            bits.append("escort expected")
        summary = " · ".join(bits) if bits else "Abnormal"
    return {
        "abnormal": bool(reasons), "reasons": reasons,
        "regime": reg, "calendar": calendar, "calendar_words": CALENDAR_WORDS[calendar],
        "permission": permission, "lead_words": lead_words,
        "apply_by": _iso(apply_by), "apply_by_be16": _iso(apply_by_be16),
        "category": cat["category"], "category_words": cat["words"], "needs": cat["needs"],
        "special_order_reasons": so,
        "notices": {"police_days": police_days, "police_triggers": police_triggers, "police_by": _iso(police_by),
                    "rba_days": rba_days, "rba_indemnity": bool(rba_days), "rba_by": _iso(rba_by)},
        "notify_by": _iso(nb),
        "attendant": attendant, "attendant_reasons": att,
        "markers": markers, "speeds_mph": list(speeds) if speeds else None,
        "escort_expected": escort_expected, "escort_reasons": esc,
        "height": height,
        "lines": lines, "notes": notes, "flags": flags,
        "summary": summary, "not_abnormal_words": None if reasons else NOT_ABNORMAL_WORDS,
        "advice_words": ADVICE_WORDS, "not_modelled_words": NOT_MODELLED_WORDS,
    }


def _mins(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _bands_overlap(a, b):
    """Two 'HH:MM' windows overlap (either may run past midnight)."""
    def ivs(x):
        s, e = _mins(x[0]), _mins(x[1])
        if s is None or e is None:
            return []
        return [(s, e)] if s < e else [(s, 1440), (0, e)]
    return any(x0 < y1 and y0 < x1 for x0, x1 in ivs(a) for y0, y1 in ivs(b))


def _days_words(flags):
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    on = [names[i] for i, c in enumerate(str(flags)[:7]) if c == "1"]
    if on == list(names[:5]):
        return "weekdays"
    if on == list(names):
        return "every day"
    return ", ".join(on) if on else "no day"
