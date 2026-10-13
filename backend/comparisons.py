"""
comparisons.py — the arithmetic of the bulletin's "Is it a lot?" panel (13 Oct 2026, W14; decision D40).

WHAT THIS IS
------------
The panel sets the month's haul carbon beside yardsticks a reader knows. The scheme's own
yardsticks (the plan, last month, the carbon target, per tonne and per movement) come from the
bulletin's own figures; the two outside ones come from ONE table, backend/data/comparison_factors.json,
where every factor carries its source, year and the day it was checked:

  * cars — the month's tonnes as "about N–M average cars driven for a month": the DESNZ 2026
    average car (fuel unknown, tailpipe — the same tank-to-wheel basis as the lorry factors) ×
    the DfT NTS0901a average annual mileage (England, 2025) ÷ 12, printed as a range of
    car_range_pct either side (D40: "a rounded range, never one exact figure"), two significant figures;
  * the council's own figures — a district's haul carbon as "about x %" of a month of the
    district's road transport emissions in the government's local statistics (DESNZ 2024,
    Table 1.1; backend/data/desnz_la_road_transport_2024.json, keyed by the ONS code the
    council areas carry). A month is one twelfth of the year (D40).

ROAD CLASS (13 Oct 2026, decision 2a: "HERE road attributes first, all roads printed until it lands")
-----------------------------------------------------------------------------------------------------
The stored road routes carry no road class (HERE is asked for the line and the summary only), so
nothing says whether a route's miles in a district were on a motorway. Until it does, the share is
taken against ALL the district's road transport (A roads + minor roads + motorways) and says so; in a
district the government figures give no motorway, that is A + minor roads exactly, and it says that.
D40's fuller rule (A + minor, plus motorways only where the routes use them) needs the road class:
GET /api/admin/diagnostics/road-class shows what HERE returns, before anything is built on it.

RULES KEPT
----------
* Every figure printed has a source and a year; nothing here is typed by hand outside the table.
* "About" on every outside comparison; never trees, flights or households (the brief's copy rule).
* No figure → words ("no government figure for this council"), never a zero.
"""
import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
FACTORS_PATH = os.path.join(_HERE, "data", "comparison_factors.json")
LA_PATH = os.path.join(_HERE, "data", "desnz_la_road_transport_2024.json")
KM_PER_MILE = 1.609344
_CACHE = {}


def _load(path):
    if path not in _CACHE:
        with open(path, encoding="utf-8") as f:
            _CACHE[path] = json.load(f)
    return _CACHE[path]


def factors():
    """The comparison factors table: {key: {value, unit, what, source, year, url, checked_on, next_edition}}."""
    return _load(FACTORS_PATH)["factors"]


def la_table():
    """The DESNZ 2024 road transport rows and their source block."""
    return _load(LA_PATH)


def sig2(x):
    """Two significant figures, as a whole number from 10 up (2,431 → 2,400; 96.4 → 96; 7.3 → 7)."""
    if x is None or x <= 0:
        return 0
    if x < 10:
        return int(round(x))
    p = 10 ** (int(math.floor(math.log10(x))) - 1)
    return int(round(x / p) * p)


def car_month_kg():
    """kg CO2e of one average car driven for a month: miles a year × km per mile × kg per km ÷ 12."""
    f = factors()
    return f["car_miles_a_year"]["value"] * KM_PER_MILE * f["car_kg_co2e_per_km"]["value"] / 12.0


def car_equivalents(t_co2e):
    """
    The month's tonnes as average cars driven for a month, a range car_range_pct either side, two
    significant figures each end; None for no figure. "less than one" below one car.
    """
    if t_co2e is None or not t_co2e > 0:
        return None
    pct = factors()["car_range_pct"]["value"] / 100.0
    cars = t_co2e * 1000.0 / car_month_kg()
    lo, hi = sig2(cars * (1 - pct)), sig2(cars * (1 + pct))
    if hi < 1:
        words = "less than one average car driven for a month"
    elif lo == hi:
        words = f"about {lo:,} average car{'s' if lo != 1 else ''} driven for a month"
    else:
        words = f"about {max(lo, 1):,}–{hi:,} average cars driven for a month"
    return {"cars": cars, "low": lo, "high": hi, "words": words}


def pct_words(p):
    """A share in words: "under 0.1 %", one decimal below 10 %, whole from 10 %."""
    if p is None:
        return "—"
    if p < 0.1:
        return "under 0.1%"
    return f"{p:.1f}%" if p < 10 else f"{p:.0f}%"


def la_share(area_id, t_co2e):
    """
    A district's haul carbon in the month against a month (one twelfth) of its road transport
    emissions in DESNZ 2024: {pct, pct_words, month_t, roads, has_motorway, name}; None when the
    council is not in the table (or no carbon figure).
    """
    row = (la_table().get("rows") or {}).get(area_id)
    if not row or t_co2e is None:
        return None
    name, a, m, minor = row
    year_t = (a + m + minor) * 1000.0
    if not year_t > 0:
        return None
    month_t = year_t / 12.0
    pct = 100.0 * t_co2e / month_t
    has_mw = m > 0
    roads = ("all roads, motorways included; whether these lorries used one is not yet known" if has_mw
             else "A and minor roads: the government figures give no motorway in the district")
    return {"name": name, "pct": pct, "pct_words": pct_words(pct), "month_t": month_t, "year_t": year_t,
            "has_motorway": has_mw, "roads": roads}


def about(p_words):
    """'about 0.6%' — but a share under 0.1 % reads 'under 0.1%', never 'about under'."""
    return p_words if p_words.startswith("under") or p_words == "—" else "about " + p_words
