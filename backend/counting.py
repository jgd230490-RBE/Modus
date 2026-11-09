"""
counting.py — how a lorry visit is counted. Wayscope, 9 Nov 2026 (v2.1 task 2.1-11b).

THE RULE
--------
A lorry coming to a site and leaving again is ONE visit (= one load = one delivery). Councils, DCO caps and
transport assessments count it as TWO movements, one each way ("182 HGV movements per day (91 in / 91 out)").
CLPs and the CLOCS tool count visits. The research: notes movement-counting-1108.md (32 sources, John's Q1–Q7
of 8 Nov 2026).

The organisation picks which one its ROAD figures are in: Config -> Planning -> "Count a lorry coming and going
as", stored as `planning.count_visit_as` = 2 (movements, in and out — the default for a new organisation and
the demo) or 1 (visits). Absent = 2.

What follows the setting (Q3): the public map's figures bar, the shared road sections (Volume heat map, the
stretch card), the council view, the bulletin, the Dashboard's headline card. What never does: CLP §6 and the
CLP pack's vehicles / trips, Gate arrivals, the Look-ahead, the Simulation — they schedule lorries — and a
route's typed cap (`routes.max_vehicles_per_day`), which is ALWAYS lorry visits a day (Q4) and is compared
with the route's visits whichever way the organisation counts.

On a road (2.1-1's Q2, and this branch's question A): each PASS of a leg is a movement — the loaded leg is
"in" where it runs, the empty way back "out" where it runs. Under 1, a route's lorries count once on a road if
either leg passes. For a whole route or the whole scheme both legs always run, so movements = visits × 2.

`convert()` is the one place a figure changes unit (2.1-1's road limits call it: a limit is typed in its own
unit, as the condition was written).
"""
import math

MOVEMENTS = "movements"
VISITS = "visits"
UNITS = (MOVEMENTS, VISITS)
DEFAULT_PER_VISIT = 2


def per_visit(factors=None):
    """2 (a visit = 2 movements, the default) or 1, from planning.count_visit_as."""
    if factors is None:
        try:
            import conversions
            factors = conversions.load_factors()
        except Exception:
            factors = {}
    plan = (factors or {}).get("planning") if isinstance(factors, dict) else None
    v = (plan or {}).get("count_visit_as") if isinstance(plan, dict) else None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return DEFAULT_PER_VISIT
    return v if v in (1, 2) else DEFAULT_PER_VISIT


def unit(factors=None):
    return MOVEMENTS if per_visit(factors) == 2 else VISITS


def setting_problem(value):
    """One sentence for config.validate, or None. Absent = 2."""
    if value is None:
        return None
    if value in (1, 2) and not isinstance(value, bool):
        return None
    return "planning.count_visit_as must be 1 or 2 (or left out)"


def convert(n, from_unit, to_unit):
    """A count in one unit in the other: movements = visits × 2. None stays None; a limit is never rounded."""
    if from_unit not in UNITS or to_unit not in UNITS:
        raise ValueError("unit must be 'movements' or 'visits'")
    if n is None:
        return None
    n = float(n)
    if from_unit == to_unit:
        return n
    return n * 2.0 if to_unit == MOVEMENTS else n / 2.0


def from_visits(visits, factors=None, pv=None):
    """Visits (loads) in the organisation's unit."""
    pv = per_visit(factors) if pv is None else pv
    return None if visits is None else float(visits) * pv


def on_road(loads, passes_in, passes_out, pv):
    """A route's count on a road: its loads × (in + out) as movements, or × (in or out) as visits."""
    if pv == 2:
        return float(loads) * ((1 if passes_in else 0) + (1 if passes_out else 0))
    return float(loads) if (passes_in or passes_out) else 0.0


#: the words, one set per unit (few words on a screen: the explanation is in the guides)
WORDS = {
    MOVEMENTS: {
        "label": "Lorry movements a day",
        "lower": "lorry movements a day",
        "short": "movements a day",
        "col": "Movements a day",
        "month": "movements in the month",
        "one": "movement", "many": "movements",
        "note": "A lorry coming and going is 2 movements, as councils count them.",
        "sources": ("Movements: this bulletin counts an HGV arriving and leaving as 2 movements, as council conditions "
                    "do; a CLP counts the same lorries once, as visits."),
    },
    VISITS: {
        "label": "Lorry visits a day",
        "lower": "lorry visits a day",
        "short": "visits a day",
        "col": "Visits a day",
        "month": "visits in the month",
        "one": "visit", "many": "visits",
        "note": "A lorry coming and going is 1 visit (2 movements as councils count them).",
        "sources": ("Visits: this bulletin counts an HGV arriving and leaving once, as a visit (2 movements as "
                    "councils count them)."),
    },
}

#: the route cap's words, whatever the setting (Q4)
CAP_UNIT_WORDS = "lorry visits a day"


def words(factors=None):
    """The organisation's count words + its unit and factor, for a page or an export."""
    u = unit(factors)
    out = dict(WORDS[u])
    out.update({"unit": u, "per_visit": 2 if u == MOVEMENTS else 1})
    return out


def split_words(movements, inn, out):
    """'(61 in, 61 out)' for a movements figure; '' for visits or no figure."""
    if movements is None or inn is None or out is None:
        return ""
    return f"({_n(inn)} in, {_n(out)} out)"


def _n(x):
    x = float(x or 0)
    if 0 < x < 1:
        return "under 1"
    return f"{int(math.floor(x + 0.5)):,}"


def words_for(pv):
    """words() for a known factor (a payload built once per read)."""
    u = MOVEMENTS if pv == 2 else VISITS
    out = dict(WORDS[u])
    out.update({"unit": u, "per_visit": pv})
    return out


def area_basis(pv):
    if pv == 2:
        return ("Lorry movements a day: each leg of a route that enters an area is one movement a load (the loaded "
                "leg in, the empty way back out), the month's approved loads divided by the working days.")
    return ("Lorry visits a day: the month's approved loads of every route with a leg that enters an area, divided "
            "by the working days, each lorry once.")


def road_basis(pv):
    if pv == 2:
        return ("lorry movements a day: each pass of a leg is one movement a load (the loaded leg in, the empty way "
                "back out, each where it runs); the month's approved loads (tonnes ÷ payload, as typed, not rounded "
                "per line) / working days, summed over the routes on the section.")
    return ("lorry visits a day: a route's loads count once on a section when either of its legs runs there; the "
            "month's approved loads (tonnes ÷ payload, as typed, not rounded per line) / working days, summed over "
            "the routes on the section.")
