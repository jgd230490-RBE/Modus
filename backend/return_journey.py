"""
The return journey: how much of a lorry's EMPTY way back is charged to this scheme's carbon.

8 Nov 2026 (v2.1; John, 8 Nov: "if a lorry is on turnaround … two way, but if it's just on delivery maybe … one
way as the vehicle could be on a completely other job afterwards"). Researched in notes/carbon-return-leg-1108.md:

* No published method counts a delivery one way only. The National Highways Carbon Tool (v2.7, §5.3.2) adds the
  whole return journey to every haul. RICS Whole life carbon assessment (2nd ed., 2023, §5.1.3, module A4) says the
  return MUST be included: 43 % of the loaded distance as the UK default where the lorry may find other work, 100 %
  where no return load is possible (concrete mixers, a haul from a site). GLEC v3: a vehicle working for one
  customer carries its whole round trip; one way only when it is chartered for a one-way journey.
* The government's per-vehicle-km factors (DESNZ 2026) are published for 0 %, 100 % and average loading. Wayscope
  used "average laden" for both legs; now the LOADED leg takes the 100 % laden figure and the EMPTY leg the 0 %
  figure, so the two legs can be charged apart (the RICS / GLEC method). A vehicle with no pair (an electric lorry,
  or one typed on Config without one) uses its single figure for both.

ONE rule. Every carbon figure reads trip_kg() here: the Routes table's rows (network.route_analysis), the cost lines
the Dashboard, the Look-ahead, the public map and the bulletin sum (derived.line_context → costlines), the Carbon
planner (carbon._eval) and the carbon target built from them. The NH Carbon Tool figure printed beside them and the
tonne-km benchmark are NOT touched: they are comparisons with other methods, not Wayscope's figure.

Per route (Data → Routes, the planning figures): `routes.return_mode`
    'empty'   Comes back empty         the whole return is charged (RICS 100 %; the NH tool's reading)
    'part'    May take other work      planning.return_journeys.part_share_pct of it (RICS 43 % UK default)
    'oneway'  One way only             none of it (GLEC: a one-way charter) — offered, never a default
    NULL      guessed from the route: a supplier's yard / quarry / plant as its start → the 'supplier' default
              ('part'); anything else (a haul from a site, muck-away, between compounds) → the 'scheme' default
              ('empty'); a concrete mixer → the 'mixers' default ('empty') whatever the route says.
Pairings (v3, notes/carbon-return-leg-1108.md last section) will later REPLACE the charged return km for the paired
loads in a week: keep the charged share one number (`share`) that the figures multiply the return km by.
"""

MODES = ("empty", "part", "oneway")
WORDS = {"empty": "Comes back empty", "part": "May take other work", "oneway": "One way only"}
#: the seed (factors.json planning.return_journeys carries the same; a tenant saved before 8 Nov 2026 has none)
DEFAULTS = {"supplier": "part", "part_share_pct": 43, "scheme": "empty", "mixers": "empty"}
#: a location kind that is a SUPPLIER's end: a lorry from there may well find other work after unloading
SUPPLIER_WORDS = ("quarry", "plant", "works", "depot", "railhead", "rail head", "port", "supplier", "recycling", "yard")


def settings(factors):
    """planning.return_journeys with the seed's defaults under it (every key present, the pct a number)."""
    plan = (factors or {}).get("planning") if isinstance(factors, dict) else None
    rj = (plan or {}).get("return_journeys") if isinstance(plan, dict) else None
    out = dict(DEFAULTS)
    if isinstance(rj, dict):
        for k in ("supplier", "scheme", "mixers"):
            if rj.get(k) in MODES:
                out[k] = rj[k]
        try:
            pct = float(rj.get("part_share_pct"))
            if 0 <= pct <= 100:
                out["part_share_pct"] = pct
        except (TypeError, ValueError):
            pass
    return out


def settings_problem(block):
    """One sentence for config.validate, or None. Absent = the defaults."""
    if block is None:
        return None
    if not isinstance(block, dict):
        return "Return journeys on Config → Planning must be a set of choices"
    for k in ("supplier", "scheme", "mixers"):
        if k in block and block[k] is not None and block[k] not in MODES:
            return f"Return journeys: {k} must be one of {', '.join(WORDS[m] for m in MODES)}"
    if "part_share_pct" in block and block["part_share_pct"] is not None:
        try:
            pct = float(block["part_share_pct"])
        except (TypeError, ValueError):
            return "Return journeys: the share must be a number from 0 to 100"
        if not (0 <= pct <= 100):
            return "Return journeys: the share must be a number from 0 to 100"
    return None


def is_mixer(vehicle):
    return "mixer" in str(vehicle or "").lower()


def is_supplier_type(loc_type):
    t = str(loc_type or "").strip().lower()
    return any(w in t for w in SUPPLIER_WORDS)


def default_mode(origin_type, vehicle, factors):
    s = settings(factors)
    if is_mixer(vehicle):
        return s["mixers"]
    return s["supplier"] if is_supplier_type(origin_type) else s["scheme"]


def mode_for(route_row, origin_type, vehicle, factors):
    """(mode, source): the route's own choice ('route') or the guess ('default')."""
    m = (route_row or {}).get("return_mode") if isinstance(route_row, dict) else None
    if m in MODES:
        return m, "route"
    return default_mode(origin_type, vehicle, factors), "default"


def share(mode, factors):
    """The charged share of the empty return: 1.0, the part share, or 0.0."""
    if mode == "oneway":
        return 0.0
    if mode == "part":
        return float(settings(factors)["part_share_pct"]) / 100.0
    return 1.0


def _num(x):
    if x is None or isinstance(x, bool) or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def leg_factors(factors, vehicle):
    """
    (laden kg CO2e per km, empty kg CO2e per km, basis). The vehicle's stored 100 % / 0 % laden pair where both
    exist and its average figure is stored above 0 ('pair'); else its single figure for both legs ('single': an
    electric lorry, a vehicle typed without the pair, a stored 0, or one this document does not carry) —
    conversions._emissions, the one fallback rule.
    """
    import conversions
    vs = (factors or {}).get("vehicles", {}) or {}
    v = vs.get(vehicle) if isinstance(vs.get(vehicle), dict) else {}
    laden, empty = _num(v.get("emissions_kg_co2e_per_km_laden")), _num(v.get("emissions_kg_co2e_per_km_empty"))
    single_stored = _num(v.get("emissions_kg_co2e_per_km"))
    # the pair applies to a vehicle on the government basis (its average figure stored, above 0); a stored 0 is a FIGURE
    # — no tailpipe carbon, on both legs (B2, 12 Oct 2026) — and a blank average falls to the one fallback rule below
    if laden is not None and empty is not None and single_stored is not None and single_stored > 0 \
            and v.get("fuel") != "electric":
        return laden, empty, "pair"
    single = conversions._emissions(factors, vehicle)
    return single, single, "single"


def trip_kg(factors, vehicle, loaded_km, return_km, share_):
    """
    One round trip's kg CO2e: loaded km × the laden figure + return km × share × the empty figure.
    {"kg", "loaded_kg", "empty_kg", "charged_km", "basis"}; return_km None or 0 = no return charged.
    """
    laden, empty, basis = leg_factors(factors, vehicle)
    lk = float(loaded_km or 0.0)
    rk = float(return_km or 0.0) * float(share_ if share_ is not None else 1.0)
    loaded_kg = lk * laden
    empty_kg = rk * empty
    return {"kg": loaded_kg + empty_kg, "loaded_kg": loaded_kg, "empty_kg": empty_kg,
            "charged_km": lk + rk, "basis": basis}
