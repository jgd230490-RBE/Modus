"""
Carbon planner — 10 Oct 2026. The engine behind /api/carbon/scenario and the Carbon page.

WHAT IT IS FOR
--------------
Strategic planning to REDUCE carbon on a programme's haulage and bulk materials: which
decisions move the most tCO2e (material choice, recycled content, source distance, haul
route, vehicle, diesel vs electric, disposal route), tested as alternatives beside a
baseline. It is a planning estimate. It is NOT a National Highways Carbon Tool return and
nothing here says it is.

THE RULES — mirrored from the NH Carbon Tool v2.7 so the figures are comparable
------------------------------------------------------------------------------
  material tCO2e   = quantity × conversion × carbon factor (kg/t ÷ 1000)     'Bulk Materials' M9
  tool transport   = one-way km × tonnes × conversion × (laden + unladen)/2 × 2  'Bulk Materials' Y9, Z9
                     — the tool doubles the one-way distance for the return leg (the ×2 rule)
  allocation       = % of a row to Fencing / Drainage / Road Pavements / Civils Structures / Waste,
                     the remainder 'Not Allocated'; a sum over 100 % is an error (the sheet's "err")
  double count     = earthworks EXCLUDES bulk materials: every line sits on ONE sheet, chosen by its
                     material class (soils → Earthworks; every other class → Bulk Materials) — and a
                     line to a tip or recycling site sits on Waste, as the tool's 'exported off-site' rows do
Wayscope's HEADLINE transport figure is the vehicle-km method the Dashboard and the map
already use (trips × routed km × the vehicle's kg CO2e per vehicle-km, costlines.co2_t).
The tool's tonne-km figure and the DESNZ 2026 class tonne-km figure are returned beside it,
each labelled, and never added into it.

ONE DISTANCE, ONE TRIP COUNT — and nothing that reads as a saving by accident
----------------------------------------------------------------------------
The baseline reads costlines.lines() — the Dashboard's own read — for tonnes, trips, the
one-way and return km and the cycle. A line whose route is not baked has no distance: its
transport carbon is None and it is EXCLUDED from every transport total, which says so.
Never estimated. An ALTERNATIVE is compared like with like:
  * it keeps every line on the baseline's baked set — where the alternative VEHICLE has no
    baked geometry on the same route, the forecast vehicle's distance is used (flagged
    KM_FROM_BASELINE_VEHICLE); where a swapped-to ROUTE is not baked at all, the swap is left
    out for that line (ROUTE_SWAP_NOT_BAKED) — a dropped or borrowed-elsewhere line would read
    as a saving;
  * it counts the legs the baseline counts: when the baseline line has both legs and the
    alternative route's return is not baked, the loaded leg stands in for it, as
    route_analysis() does for the cycle (RETURN_STAND_IN); when the baseline counts the loaded
    leg only, so does the alternative;
  * a disposal route with no published factor for the material is never counted as zero:
    the line is flagged NO_DISPOSAL_FACTOR, its tonnes reported, and a lever asking for it
    is skipped with a note;
  * an electric trip that needs more than one battery is not sized and not credited: that
    line stays diesel, flagged EV_TRIP_EXCEEDS_BATTERY.

FACTORS
-------
backend/factors.json `carbon` — UK Government GHG conversion factors 2026, flat file v1.2,
OGL v3.0, each with its row ID, year, scope, GWP basis and a status (VERIFIED / DERIVED /
ASSUMPTION). A tenant whose live document predates the block reads the FILE's block key by
key (params(): a key PRESENT in the live document wins, even when it is null, so a tenant
can switch a figure off), the file's scenario-only electric profiles (vehicles()) and the
file's carbon_material for a category of the same name when the live category has none —
so the page works on a tenant seeded before 10 Oct without a re-import. The file is read
once and cached until it changes. No ICE factor is used (ICE commercial use ended 30 Sep
2026). Concrete has ONE generic figure: a supplier EPD (value + reference) replaces it per
material category or route, never an invented grade, and is shown as an ASSUMPTION (typed,
not checked). Soils have no primary factor, so earthworks carbon is haulage + disposal.

ELECTRIC
--------
The 2026 Government set has no electric HGV factor. An electric profile's kg CO2e/km is
kWh/km × UK electricity (generation + T&D), derived in conversions._emissions() — the one
place. Fleet size for an electric profile adds charging time to the shift (ev_day()): the
battery starts the shift full, a trip's energy must fit the usable battery, the lorry stops
to charge before a trip that does not fit, topping up only what the rest of the shift
needs, at the profile's charger power.

Nothing here writes. A scenario is computed on request and stored nowhere.
"""
import copy
import math
import os

import access
import conversions
import costlines
import db
import derived
import fairprice
import network

KM_PER_MILE = 1.609344
SHEET_BULK, SHEET_EARTHWORKS, SHEET_WASTE = "Bulk Materials", "Earthworks", "Waste"
ALLOCATION = ("Fencing", "Drainage", "Road Pavements", "Civils Structures", "Waste")
NOT_ALLOCATED = "Not Allocated"
DRIVERS = ("material", "recycled", "source", "route", "vehicle", "fuel", "disposal")
# 11 Oct 2026: the words National Highways, CLOCS and the Environment Agency use (notes/carbon-ui-1011):
# "custom carbon factor" and "disposal method" are NH Carbon Tool v2.7 terms, "vehicle choice" a CLOCS
# planned measure, "receiving site" the EA's
DRIVER_LABELS = {
    "material": "Custom carbon factor (supplier EPD) or reused material",
    "recycled": "Recycled content",
    "source": "Supplier and haul distance",
    "route": "Haul route",
    "vehicle": "Vehicle choice",
    "fuel": "Battery electric lorries",
    "disposal": "Receiving site and disposal method",
}
DISPOSAL_ROUTES = ("landfill", "closed_loop", "open_loop", "combustion")
FLAG_UNBAKED = derived.FLAG_UNBAKED
FLAG_KM_BORROWED = "KM_FROM_BASELINE_VEHICLE"
FLAG_KM_SCALED = "KM_SCALED"
FLAG_ALT_UNBAKED = "ALT_ROUTE_NOT_BAKED"
FLAG_SWAP_UNBAKED = "ROUTE_SWAP_NOT_BAKED"
FLAG_EV_INFEASIBLE = "EV_TRIP_EXCEEDS_BATTERY"
FLAG_RETURN_ESTIMATED = "RETURN_NOT_BAKED"
FLAG_RETURN_STAND_IN = "RETURN_STAND_IN"
FLAG_NO_DISPOSAL_FACTOR = "NO_DISPOSAL_FACTOR"
LEVER_KEYS = {"driver", "scope", "epd", "reused", "pct", "to_route", "distance_pct", "alt_index", "vehicle", "fuel", "to"}
LIMITS = (
    "Government material factors are coarser than ICE; ICE is not used (its commercial use ended 30 Sep 2026).",
    "Concrete has one generic Government figure (no grades, no cement replacement): enter a supplier EPD instead.",
    "Electric kWh per km is derived from a mixed-fleet programme (ZEHID 2026), not measured for these lorries.",
    "The +2 t weight allowance for zero-emission HGVs is a draft rule and is not applied.",
    "The Government 2026 set has no electric HGV factor: electric carbon is kWh × UK electricity.",
    "Material Use factors are AR4 GWP; transport and fuel factors are AR5 — the Government publishes them so.",
    "Planning estimates on the approved forecast, not a National Highways Carbon Tool return.",
    "Access is a shared code per role: there is no per-person sign-in yet.",
)


class CarbonError(ValueError):
    """A request the rules refuse — allocation over 100 %, an EPD with no reference, an unknown vehicle."""


def _num(x):
    try:
        v = float(x) if x is not None and x != "" and not isinstance(x, bool) else None
    except (TypeError, ValueError):
        return None
    return v if v is not None and math.isfinite(v) else None


# =========================================================================== #
#  Factors: the live document, falling back to the file                        #
# =========================================================================== #
def _merge(seed, live):
    """Recursive: dicts merge key by key. A key PRESENT in the live document wins, even when
    it is null (a tenant switching a figure off); an ABSENT key falls back to the file's."""
    if isinstance(seed, dict) and isinstance(live, dict):
        out = {}
        for k in list(seed) + [k for k in live if k not in seed]:
            if k in live:
                out[k] = _merge(seed.get(k), live[k]) if isinstance(live[k], dict) else copy.deepcopy(live[k])
            else:
                out[k] = copy.deepcopy(seed.get(k))
        return out
    return copy.deepcopy(live)


def _file():
    """factors.json, parsed once and cached until the file changes (conversions' cache)."""
    try:
        return conversions.load_factors_file_cached()
    except Exception:
        return {}


def params(factors=None):
    """The `carbon` block of the live document, falling back to factors.json's key by key."""
    factors = factors if factors is not None else conversions.load_factors()
    live = factors.get("carbon") if isinstance(factors.get("carbon"), dict) else {}
    return _merge(_file().get("carbon") or {}, live)


def vehicles(factors=None):
    """The live vehicles, plus the file's scenario-only profiles (the electric variants) that the
    live document does not carry yet. A live entry always wins over the file's."""
    factors = factors if factors is not None else conversions.load_factors()
    out = {k: v for k, v in (factors.get("vehicles") or {}).items() if isinstance(v, dict)}
    for k, v in (_file().get("vehicles") or {}).items():
        if not k.startswith("_") and k not in out and isinstance(v, dict) and v.get("scenario_only"):
            out[k] = copy.deepcopy(v)
    return out


def _doc(factors, vs, cp):
    """The document conversions._emissions() should read: live, with the merged vehicles and carbon."""
    d = dict(factors)
    d["vehicles"] = vs
    d["carbon"] = cp
    return d


def carbon_material_of(category, factors=None):
    """The Government material class a category is priced with, or None (excluded, labelled).
    The live category's own value wins when the key is present (null = excluded on purpose);
    only an ABSENT key falls back to the file's category of the same name."""
    factors = factors if factors is not None else conversions.load_factors()
    c = (factors.get("material_categories") or {}).get(category)
    if isinstance(c, dict) and "carbon_material" in c:
        cm = c.get("carbon_material")
        return cm if isinstance(cm, str) else None
    fc = (_file().get("material_categories") or {}).get(category)
    cm = fc.get("carbon_material") if isinstance(fc, dict) else None
    return cm if isinstance(cm, str) else None


def sheet_of(carbon_material, disposal=False):
    """The NH Carbon Tool sheet a line belongs on — ONE sheet per line (earthworks excludes bulk;
    material leaving site to a tip or a recycling site is Waste, as in the tool)."""
    if disposal:
        return SHEET_WASTE
    if carbon_material is None:
        return None
    return SHEET_EARTHWORKS if carbon_material == "soils" else SHEET_BULK


def electric_variant(vs, vehicle):
    """The electric profile whose geometry_twin is `vehicle`, or None."""
    for k, v in vs.items():
        if not k.startswith("_") and isinstance(v, dict) and v.get("fuel") == "electric" and v.get("geometry_twin") == vehicle:
            return k
    return None


# =========================================================================== #
#  Units                                                                       #
# =========================================================================== #
def km_from(value, unit="km"):
    """A distance typed in the tenant's unit, in km (km is what is stored)."""
    v = _num(value)
    if v is None:
        return None
    return v * KM_PER_MILE if unit == "mi" else v


def km_to(km, unit="km"):
    v = _num(km)
    if v is None:
        return None
    return v / KM_PER_MILE if unit == "mi" else v


# =========================================================================== #
#  The factor functions (pure; hand-checked in test_carbon.py)                 #
# =========================================================================== #
def _material_row(cp, material):
    m = (cp.get("materials") or {}).get(material) if material else None
    return m if isinstance(m, dict) else None


def material_factor(cp, material, recycled_pct=0.0, epd=None, reused=False):
    """
    kg CO2e per tonne of one Government material class.

    recycled_pct blends primary and closed-loop linearly by the recycled share — only where the
    file publishes BOTH; otherwise recycled content is refused with the reason. `epd` =
    {"kg_per_t", "source"} replaces the Government figure (a supplier EPD; the reference is
    required; shown as an ASSUMPTION — typed, not checked). `reused` takes the published
    Re-used row where one exists.
    """
    m = _material_row(cp, material)
    kg = (m or {}).get("kg_co2e_per_t") if isinstance((m or {}).get("kg_co2e_per_t"), dict) else {}
    primary, closed, reuse = _num(kg.get("primary")), _num(kg.get("closed_loop")), _num(kg.get("reused"))
    label = (m or {}).get("label") or material or "this material"
    enabled = primary is not None and closed is not None
    if m is None:
        reason = "no Government material class is set for this category"
    elif primary is None:
        reason = f"no primary-production factor is published for {label}"
    elif closed is None:
        reason = f"no closed-loop (recycled) factor is published for {label}"
    else:
        reason = None
    base = {"material": material, "label": label, "primary": primary, "closed_loop": closed, "reused": reuse,
            "recycled_enabled": enabled, "recycled_reason": reason, "ids": (m or {}).get("ids"),
            "source": (m or {}).get("source"), "year": (m or {}).get("year"), "gwp": (m or {}).get("gwp"),
            "scope": (m or {}).get("scope"), "epd_source": None}
    if epd:
        v = _num(epd.get("kg_per_t")) if isinstance(epd, dict) else None
        src = str((epd or {}).get("source") or "").strip() if isinstance(epd, dict) else ""
        if v is None or v < 0:
            raise CarbonError("an EPD override needs a value in kg CO2e per tonne, 0 or more")
        if not src:
            raise CarbonError("an EPD override needs its source (the EPD's reference)")
        return dict(base, kg_per_t=v, method="epd", recycled_pct=None, epd_source=src, status="ASSUMPTION",
                    source=f"supplier EPD {src} (typed; not checked by Wayscope)", year=None, ids=None)
    if reused:
        if reuse is None:
            raise CarbonError(f"no re-used factor is published for {label}")
        return dict(base, kg_per_t=reuse, method="reused", recycled_pct=None, status="VERIFIED")
    r = _num(recycled_pct) or 0.0
    if r < 0 or r > 100:
        raise CarbonError("recycled content must be between 0 and 100 %")
    if r > 0 and not enabled:
        raise CarbonError(f"recycled content cannot be set for {label}: {reason}")
    if primary is None:
        return dict(base, kg_per_t=None, method="none", recycled_pct=0.0, status=None)
    if r > 0:
        return dict(base, kg_per_t=primary * (1.0 - r / 100.0) + closed * (r / 100.0), method="blend",
                    recycled_pct=r, status="DERIVED")
    return dict(base, kg_per_t=primary, method="primary", recycled_pct=0.0, status="VERIFIED")


def material_t(quantity, kg_per_t, conversion=1.0):
    """The tool's material row: quantity × conversion × carbon factor, in tonnes CO2e."""
    if quantity is None or kg_per_t is None:
        return None
    return float(quantity) * float(conversion) * float(kg_per_t) / 1000.0


def disposal_factor(cp, material, route):
    """kg CO2e per tonne for a Waste disposal row, or None when the file publishes none."""
    if route not in DISPOSAL_ROUTES:
        raise CarbonError(f"disposal route must be one of {', '.join(DISPOSAL_ROUTES)}")
    d = (_material_row(cp, material) or {}).get("disposal_kg_co2e_per_t")
    return _num(d.get(route)) if isinstance(d, dict) else None


def disposal_routes_published(cp, material):
    """The disposal routes the Government file publishes a factor for, for this class."""
    return [r for r in DISPOSAL_ROUTES if material and disposal_factor(cp, material, r) is not None]


def disposal_t(tonnes, kg_per_t):
    if tonnes is None or kg_per_t is None:
        return None
    return float(tonnes) * float(kg_per_t) / 1000.0


def transport_vehicle_km_t(trips, km_per_trip, kg_per_vkm):
    """Wayscope's method: trips × km per trip × kg CO2e per vehicle-km ÷ 1000 (costlines.co2_t)."""
    if km_per_trip is None or kg_per_vkm is None or trips is None:
        return None
    return float(trips) * float(km_per_trip) * float(kg_per_vkm) / 1000.0


def nh_tool_t_per_t_km(cp):
    """The tool's tCO2e per tonne per ONE-WAY km: (laden + unladen)/2 × 2."""
    nh = ((cp.get("transport") or {}).get("nh_carbon_tool_v27")) or {}
    return (((_num(nh.get("laden_t_co2e_per_tkm")) or 0.0) + (_num(nh.get("unladen_t_co2e_per_tkm")) or 0.0)) / 2.0) * 2.0


def transport_nh_t(one_way_km, tonnes, cp, conversion=1.0):
    """The NH Carbon Tool's transport row: one-way km × tonnes × conversion × (laden + unladen)/2 × 2."""
    if one_way_km is None or tonnes is None:
        return None
    return float(one_way_km) * float(tonnes) * float(conversion) * nh_tool_t_per_t_km(cp)


def tkm_class(vehicle_class, gvw_t=None):
    """The DESNZ 2026 size class a vehicle's tonne-km benchmark is read from."""
    g = _num(gvw_t)
    if vehicle_class == "artic":
        return "artic" if (g is None or g > 33) else "artic_3_5_33"
    if g is not None and g <= 7.5:
        return "rigid_3_5_7_5"
    if g is not None and g <= 17:
        return "rigid_7_5_17"
    return "rigid"


def tkm_factor(cp, cls):
    """kg CO2e per tonne-km, DESNZ 2026 average laden, for a size class key (the benchmark)."""
    t = ((cp.get("transport") or {}).get("tonne_km_2026")) or {}
    row = t.get(cls) if isinstance(t.get(cls), dict) else (t.get("rigid") if cls not in t else None)
    return _num((row or {}).get("kg_co2e_per_tkm"))


def transport_tkm_t(one_way_km, tonnes, cp, cls):
    """The same haul on the DESNZ 2026 class tonne-km factor (what a tonne-km calculator says)."""
    f = tkm_factor(cp, cls)
    if one_way_km is None or tonnes is None or f is None:
        return None
    return float(tonnes) * float(one_way_km) * f / 1000.0


def allocate(t_co2e, pcts):
    """
    Split a row's tCO2e over the tool's five categories by percentage; the remainder is 'Not
    Allocated'. A sum over 100 % is refused, as the tool's sheet flags "err".
    """
    if pcts is not None and not isinstance(pcts, dict):
        raise CarbonError("an allocation is a set of category percentages, e.g. {\"Fencing\": 10}")
    pcts = pcts or {}
    total = 0.0
    for k, v in pcts.items():
        if k not in ALLOCATION:
            raise CarbonError(f"'{k}' is not an allocation category ({', '.join(ALLOCATION)})")
        x = _num(v)
        if x is None or x < 0:
            raise CarbonError(f"allocation to {k} must be a percentage, 0 or more")
        total += x
    if total > 100.0 + 1e-9:
        raise CarbonError(f"allocation sums to {round(total, 2)} % — it cannot exceed 100 %")
    t = float(t_co2e or 0.0)
    out = {k: t * (_num(pcts.get(k)) or 0.0) / 100.0 for k in ALLOCATION}
    out[NOT_ALLOCATED] = t * (100.0 - total) / 100.0
    return out


def split_sheets(rows):
    """
    The double-count rule: each row lands on exactly ONE sheet — by its material class, or Waste
    when it leaves site for disposal; the Earthworks total therefore excludes every bulk-material
    row. `rows` = [{id, carbon_material, t, disposal}]. Refuses a row id that appears twice.
    """
    seen, out = set(), {SHEET_BULK: 0.0, SHEET_EARTHWORKS: 0.0, SHEET_WASTE: 0.0, None: 0.0}
    for r in rows:
        rid = r.get("id")
        if rid in seen:
            raise CarbonError(f"row {rid} is counted twice")
        seen.add(rid)
        out[sheet_of(r.get("carbon_material"), bool(r.get("disposal")))] += float(r.get("t") or 0.0)
    return {SHEET_BULK: out[SHEET_BULK], SHEET_EARTHWORKS: out[SHEET_EARTHWORKS], SHEET_WASTE: out[SHEET_WASTE],
            "unclassed": out[None]}


def electric_kg_per_km(factors, v, basis="ttw"):
    """kWh/km × UK electricity — conversions' function, the one place it is computed."""
    return conversions.electric_kg_per_km(factors, v, basis)


def ev_day(cycle_min, km_trip, shift_hours, kwh_per_km, battery_kwh, charge_kw):
    """
    Cycles one electric lorry can run in a shift once charging is counted, simulated trip by
    trip: the battery starts the shift full; a trip's energy must fit the usable battery; before
    a trip that does not fit, the lorry charges — only what the rest of the shift needs, up to a
    full battery — at charge_kw (minutes = kWh ÷ kW × 60). Returns {cycles, charges,
    charge_minutes, minutes_per_charge, kwh_per_trip, kwh_day, range_per_charge_km, feasible}.
    """
    cyc, km, kwh, bat, kw = (_num(cycle_min), _num(km_trip), _num(kwh_per_km), _num(battery_kwh), _num(charge_kw))
    shift_min = float(shift_hours or 10) * 60.0
    out = {"cycles": 0, "charges": 0, "charge_minutes": 0.0, "minutes_per_charge": None,
           "kwh_per_trip": None, "kwh_day": 0.0, "range_per_charge_km": None, "feasible": True}
    if not cyc or cyc <= 0 or km is None or not kwh:
        return dict(out, feasible=False)
    e_trip = km * kwh
    out["kwh_per_trip"] = e_trip
    if not bat or bat <= 0 or not kw or kw <= 0:
        n = int(shift_min // cyc)                       # no battery figures: the diesel cycle, stated
        return dict(out, cycles=n, kwh_day=n * e_trip)
    out["range_per_charge_km"] = bat / kwh
    if e_trip > bat + 1e-9:
        return dict(out, feasible=False)

    def charging(n):
        soc, stops, kwh_in = bat, 0, 0.0
        for i in range(n):
            if soc + 1e-9 < e_trip:
                need = min(bat, (n - i) * e_trip) - soc
                soc += need
                kwh_in += need
                stops += 1
            soc -= e_trip
        return stops, kwh_in / kw * 60.0

    n = int(shift_min // cyc)
    while n > 0:
        stops, minutes = charging(n)
        if n * cyc + minutes <= shift_min + 1e-9:
            return dict(out, cycles=n, charges=stops, charge_minutes=minutes,
                        minutes_per_charge=(minutes / stops if stops else None), kwh_day=n * e_trip)
        n -= 1
    return dict(out, cycles=0, feasible=False)


def lorries_for(trips, cycles_per_day, working_days):
    """costlines' fleet rule: ceil(trips ÷ (cycles a day × working days)); None with no cycle."""
    if not trips:
        return 0
    if not cycles_per_day:
        return None
    return int(math.ceil(round(float(trips) / (float(cycles_per_day) * float(working_days)), 9)))


# =========================================================================== #
#  Provenance                                                                   #
# =========================================================================== #
def vehicle_factor(doc, cp, vehicle):
    """The vehicle's kg CO2e/km with its provenance: VERIFIED (equals a published 2026 row),
    DERIVED (electric, on the ZEHID-derived default kWh/km) or ASSUMPTION (an electric profile's
    own kWh/km, any other typed figure, or the _default fallback)."""
    vs = doc.get("vehicles") or {}
    v = vs.get(vehicle)
    kg = conversions._emissions(doc, vehicle)
    if not isinstance(v, dict):
        return {"vehicle": vehicle, "kg_per_km": kg, "fuel": "diesel", "status": "ASSUMPTION",
                "source": "the fallback figure for a vehicle not on Config", "year": None, "id": None, "basis": "fallback"}
    fuel = v.get("fuel") or "diesel"
    if fuel == "electric" and v.get("emissions_kg_co2e_per_km") is None:
        e = conversions.electricity_factors(doc)
        kwh = _num(v.get("kwh_per_km"))
        dflt = _num(((cp.get("electric_hgv") or {}).get("kwh_per_km_default")))
        derived_default = kwh is not None and dflt is not None and abs(kwh - dflt) < 1e-9
        basis = ("DERIVED from ZEHID 2026 (mixed fleet)" if derived_default
                 else "ASSUMPTION typed on the profile")
        return {"vehicle": vehicle, "kg_per_km": kg, "fuel": "electric",
                "status": "DERIVED" if derived_default else "ASSUMPTION",
                "kg_per_km_wtw": conversions.electric_kg_per_km(doc, v, "wtw"),
                "kwh_per_km": kwh,
                "source": (f"{kwh} kWh/km ({basis}) × UK electricity 2026 "
                           f"(generation {e.get('generation_kg_co2e_per_kwh')} + T&D {e.get('td_kg_co2e_per_kwh')} kg CO2e/kWh)"),
                "year": 2026, "id": f"{e.get('generation_id')} + {e.get('td_id')}", "basis": "tank-to-wheel equivalent"}
    rows = {k: r for k, r in (((cp.get("transport") or {}).get("vehicle_km_2026")) or {}).items()
            if isinstance(r, dict) and not k.startswith("_")}
    hit = next((r for r in rows.values() if _num(r.get("kg_co2e_per_vkm")) is not None
                and abs(float(r["kg_co2e_per_vkm"]) - kg) < 1e-9), None)
    if hit:
        return {"vehicle": vehicle, "kg_per_km": kg, "fuel": fuel, "status": "VERIFIED",
                "source": f"DESNZ 2026, {hit.get('row')}, Scope 1, tank-to-wheel", "year": 2026,
                "id": hit.get("id"), "basis": "average laden, per vehicle-km"}
    return {"vehicle": vehicle, "kg_per_km": kg, "fuel": fuel, "status": "ASSUMPTION",
            "source": "typed on Config → Vehicles; not a published 2026 row", "year": None, "id": None,
            "basis": "per vehicle-km"}


def _prov_material(cp, name):
    m = _material_row(cp, name) or {}
    return {"key": f"material:{name}", "label": m.get("label") or name, "kg_co2e_per_t": m.get("kg_co2e_per_t"),
            "disposal_kg_co2e_per_t": m.get("disposal_kg_co2e_per_t"), "ids": m.get("ids"),
            "disposal_ids": m.get("disposal_ids"), "source": m.get("source"), "year": m.get("year"),
            "scope": m.get("scope"), "gwp": m.get("gwp"), "status": m.get("status"), "note": m.get("_note"),
            "unit": "kg CO2e per tonne"}


# =========================================================================== #
#  Reads                                                                        #
# =========================================================================== #
def _locations():
    return {r["id"]: r for r in db.query("SELECT id, name, loc_type FROM locations WHERE tenant_id = ?",
                                         (db.current_tenant(),))}


def _routes():
    return {r["id"]: r for r in db.query("SELECT id, origin_id, dest_id, material_category FROM routes "
                                         "WHERE tenant_id = ?", (db.current_tenant(),))}


class _Geo:
    """route_analysis() rows per (route, profile, alt), one call per route per request."""

    def __init__(self):
        self.cache = {}

    def rows(self, route_id):
        if route_id not in self.cache:
            try:
                res = network.route_analysis(route_id)
                self.cache[route_id] = [r for r in (res.get("rows", []) or [])]
            except Exception:
                self.cache[route_id] = []
        return self.cache[route_id]

    def row(self, route_id, profile, alt=0):
        if not profile:
            return None
        for r in self.rows(route_id):
            if r.get("profile") == profile and int(r.get("alt_index") or 0) == int(alt or 0):
                return r
        return None

    def alts(self, route_id, profile):
        return sorted({int(r.get("alt_index") or 0) for r in self.rows(route_id) if r.get("profile") == profile})

    def baked_any(self, route_id, profiles):
        return any(self.row(route_id, p, 0) is not None for p in profiles if p)


def disposal_route_of(cp, loc):
    """'landfill' / 'closed_loop' … when the location's type marks a disposal site, else None."""
    t = str((loc or {}).get("loc_type") or "").strip().lower()
    dl = cp.get("disposal_loc_types") if isinstance(cp.get("disposal_loc_types"), dict) else {}
    m = {str(k).strip().lower(): v for k, v in dl.items() if not str(k).startswith("_")}
    v = m.get(t)
    return v if v in DISPOSAL_ROUTES else None


# =========================================================================== #
#  Levers                                                                       #
# =========================================================================== #
def _matches(scope, line):
    scope = scope or {}
    if scope.get("category") and line["material_type"] != scope["category"]:
        return False
    if scope.get("route_id") and line["route_id"] != scope["route_id"]:
        return False
    return True


def _check_levers(levers, vs, routes):
    if levers is None:
        return
    if not isinstance(levers, list):
        raise CarbonError("levers must be a list")
    for lv in levers:
        if not isinstance(lv, dict):
            raise CarbonError("each lever is an object with a driver")
        d = lv.get("driver")
        if d not in DRIVERS:
            raise CarbonError(f"unknown driver '{d}' (one of {', '.join(DRIVERS)})")
        sc = lv.get("scope")
        if sc is not None and (not isinstance(sc, dict) or any(k not in ("category", "route_id") for k in sc)
                               or any(v is not None and not isinstance(v, str) for v in sc.values())):
            raise CarbonError("a lever's scope is {\"category\": …} or {\"route_id\": …}, or empty for every line")
        for k in ("pct", "distance_pct", "alt_index"):
            if k in lv and lv[k] is not None and _num(lv[k]) is None:
                raise CarbonError(f"'{k}' must be a finite number")
        if d == "vehicle" and lv.get("vehicle") not in vs:
            raise CarbonError(f"vehicle '{lv.get('vehicle')}' is not on Config")
        if d == "fuel" and lv.get("fuel") not in ("electric", "diesel"):
            raise CarbonError("fuel must be electric or diesel")
        if d == "recycled":
            p = _num(lv.get("pct"))
            if p is None or p < 0 or p > 100:
                raise CarbonError("recycled content must be between 0 and 100 %")
        if d == "source" and lv.get("distance_pct") is not None:
            p = _num(lv.get("distance_pct"))
            if p is None or p <= 0 or p > 500:
                raise CarbonError("source distance must be a percentage of the baked distance, above 0 and at most 500")
        if d in ("source", "disposal") and lv.get("to_route") is not None and lv.get("to_route") not in routes:
            raise CarbonError(f"route '{lv.get('to_route')}' does not exist")
        if d == "disposal" and lv.get("to") is not None and lv.get("to") not in DISPOSAL_ROUTES:
            raise CarbonError(f"disposal route must be one of {', '.join(DISPOSAL_ROUTES)}")
        if d == "route":
            a = _num(lv.get("alt_index"))
            if a is None or a < 0 or a != int(a):
                raise CarbonError("haul route alternative must be a whole number, 0 or more")
        if d == "material" and lv.get("epd") is not None:
            if not ((sc or {}).get("category") or (sc or {}).get("route_id")):
                raise CarbonError("a supplier EPD is one product's figure: scope it to a material category or a route")
            material_factor({"materials": {"x": {"kg_co2e_per_t": {"primary": 1}}}}, "x", epd=lv.get("epd"))


def _dest_of(ctx, route_id):
    return (ctx["routes"].get(route_id) or {}).get("dest_id")


def _apply(state, line, levers, ctx, notes):
    """Apply levers (in order) to one line's state. Returns the new state; notes what it skipped."""
    vs, routes, locs, cp = ctx["vs"], ctx["routes"], ctx["locs"], ctx["cp"]
    cm = ctx["cm"](line["material_type"])
    s = dict(state)
    for lv in levers or []:
        if not _matches(lv.get("scope"), line):
            continue
        d = lv["driver"]
        if d == "material":
            if lv.get("epd"):
                s["epd"], s["reused"] = lv["epd"], False
            elif lv.get("reused"):
                if (((_material_row(cp, cm) or {}).get("kg_co2e_per_t") or {}).get("reused")) is None:
                    notes.add(f"no re-used factor is published for {line['material_type']}: those lines are unchanged")
                else:
                    s["reused"], s["epd"] = True, None
        elif d == "recycled":
            if material_factor(cp, cm).get("recycled_enabled"):
                s["recycled_pct"] = _num(lv.get("pct")) or 0.0
            elif _num(lv.get("pct")):
                notes.add(f"recycled content cannot be set for {line['material_type']}: those lines are unchanged")
        elif d == "source":
            if lv.get("to_route"):
                to = routes.get(lv["to_route"]) or {}
                cur = routes.get(s["route_id"]) or {}
                if to.get("dest_id") != cur.get("dest_id"):
                    raise CarbonError(f"a supplier swap must keep the destination: {lv['to_route']} goes elsewhere")
                s["route_id"] = lv["to_route"]
            if lv.get("distance_pct") is not None:
                s["km_scale"] = (_num(lv.get("distance_pct")) or 100.0) / 100.0
        elif d == "route":
            s["alt_index"] = int(_num(lv.get("alt_index")) or 0)
        elif d == "vehicle":
            s["vehicle"] = lv["vehicle"]
        elif d == "fuel":
            if lv["fuel"] == "electric":
                ev = electric_variant(vs, s["vehicle"])
                if ev:
                    s["vehicle"] = ev
                elif (vs.get(s["vehicle"]) or {}).get("fuel") != "electric":
                    notes.add(f"no electric variant of {s['vehicle']} on Config: those lines stay diesel")
            else:
                tw = (vs.get(s["vehicle"]) or {}).get("geometry_twin")
                if (vs.get(s["vehicle"]) or {}).get("fuel") == "electric" and tw:
                    s["vehicle"] = tw
        elif d == "disposal":
            is_disposal = bool(s.get("disposal_to") or disposal_route_of(cp, locs.get(_dest_of(ctx, s["route_id"]))))
            if lv.get("to_route"):
                to = routes.get(lv["to_route"]) or {}
                cur = routes.get(s["route_id"]) or {}
                if to.get("origin_id") != cur.get("origin_id"):
                    raise CarbonError(f"a disposal swap must keep the origin: {lv['to_route']} starts elsewhere")
                if is_disposal or disposal_route_of(cp, locs.get(to.get("dest_id"))):
                    s["route_id"] = lv["to_route"]
                    s["disposal_to"] = None
                    is_disposal = bool(disposal_route_of(cp, locs.get(to.get("dest_id"))))
                else:
                    notes.add("a disposal lever applies only to lines going to a tip or recycling site: delivery lines are unchanged")
            if lv.get("to"):
                if not is_disposal:
                    notes.add("a disposal lever applies only to lines going to a tip or recycling site: delivery lines are unchanged")
                elif disposal_factor(cp, cm, lv["to"]) is None:
                    notes.add(f"no {lv['to'].replace('_', '-')} disposal factor is published for {line['material_type']}: "
                              f"those lines are unchanged")
                else:
                    s["disposal_to"] = lv["to"]
    return s


# =========================================================================== #
#  One line under one state                                                     #
# =========================================================================== #
def _eval(line, s, ctx):
    """Every figure for one line-month under a state. `line` is a costlines line."""
    cp, doc, vs, geo, locs, routes, plan = (ctx["cp"], ctx["doc"], ctx["vs"], ctx["geo"], ctx["locs"],
                                            ctx["routes"], ctx["plan"])
    flags = []
    tonnes = float(line.get("tonnes") or 0.0)
    veh = s["vehicle"]
    v = vs.get(veh) or {}
    twin = v.get("geometry_twin")
    base_baked = bool(line.get("baked"))
    both_legs = base_baked and line.get("return_km") is not None     # what the baseline counts
    # a swapped-to route with no geometry at all cannot be compared: leave the swap out here
    if base_baked and s["route_id"] != line["route_id"] and not geo.baked_any(s["route_id"], (veh, twin, line["vehicle_type"])):
        s = dict(s, route_id=line["route_id"])
        flags.append(FLAG_SWAP_UNBAKED)
    payload, _fb = derived.payload_for(veh, doc)
    trips = derived._ceil(tonnes / payload) if payload > 0 and tonnes > 0 else 0
    unchanged_geo = (veh == line["vehicle_type"] and s["route_id"] == line["route_id"]
                     and int(s.get("alt_index") or 0) == 0 and float(s.get("km_scale") or 1.0) == 1.0)

    # ---- distance and cycle ---------------------------------------------------------
    one_way = ret = km_trip = cycle_min = None
    cycles = None
    if base_baked and unchanged_geo:
        one_way = _num(line.get("distance_km"))
        ret = _num(line.get("return_km"))                     # None when the return is not baked
        km_trip = _num(line.get("km_trip"))
        cycle_min = _num(line.get("cycle_min"))
        cycles = line.get("cycles_per_vehicle_day")
        if ret is None:
            flags.append(FLAG_RETURN_ESTIMATED)
    elif base_baked:
        alt = int(s.get("alt_index") or 0)
        row = geo.row(s["route_id"], veh, alt) or geo.row(s["route_id"], twin, alt)
        if row is None and alt != 0:
            flags.append(FLAG_ALT_UNBAKED)
            row = geo.row(s["route_id"], veh, 0) or geo.row(s["route_id"], twin, 0)
        if row is None:
            flags.append(FLAG_KM_BORROWED)
            row = geo.row(s["route_id"], line["vehicle_type"], 0)
        if row is not None:
            scale = float(s.get("km_scale") or 1.0)
            if scale != 1.0:
                flags.append(FLAG_KM_SCALED)
            one_way = float(row.get("loaded_km") or 0.0) * scale
            ret_real = None if row.get("return_estimated") else float(row.get("return_km") or 0.0) * scale
            if both_legs:
                ret = ret_real if ret_real is not None else one_way
                if ret_real is None:
                    flags.append(FLAG_RETURN_STAND_IN)
            else:
                ret = None
                flags.append(FLAG_RETURN_ESTIMATED)
            km_trip = one_way + (ret or 0.0)
            travel_hr = (float(row.get("loaded_hr") or 0) + float(row.get("return_hr") or 0)) * scale
            cycle_min = round((travel_hr + float(row.get("turnaround_hr") or 0)) * 60.0, 1)
            cycles = int((plan["shift_h"] * 60.0) // cycle_min) if cycle_min and cycle_min > 0 else 0
        else:
            base_baked = False
    if not base_baked:
        flags.append(FLAG_UNBAKED)

    # ---- an electric trip that cannot fit the battery stays diesel ------------------------
    electric = (v.get("fuel") == "electric")
    ev = None
    if electric and base_baked and cycle_min:
        ev_km = (one_way or 0.0) + (ret if ret is not None else (one_way or 0.0))   # the lorry drives home either way
        ev = ev_day(cycle_min, ev_km, plan["shift_h"], v.get("kwh_per_km"), v.get("battery_kwh_usable"), v.get("charge_kw"))
        if not ev["feasible"] and twin:
            r = _eval(line, dict(s, vehicle=twin), ctx)
            r["flags"] = r["flags"] + [FLAG_EV_INFEASIBLE]
            return r

    # ---- transport ------------------------------------------------------------------
    vf = vehicle_factor(doc, cp, veh)
    vclass = fairprice.vehicle_class(veh, doc)
    tcls = tkm_class(vclass, v.get("gvw_t"))
    tr_t = transport_vehicle_km_t(trips, km_trip, vf["kg_per_km"]) if base_baked else None
    nh_t = transport_nh_t(one_way, tonnes, cp) if base_baked else None
    tkm_t = transport_tkm_t(one_way, tonnes, cp, tcls) if base_baked else None
    vkm = trips * km_trip if (base_baked and km_trip is not None) else None
    laden_km = trips * one_way if (base_baked and one_way is not None) else None
    kwh = (vkm * float(v.get("kwh_per_km") or 0)) if (electric and vkm is not None) else 0.0

    # ---- fleet ----------------------------------------------------------------------
    if base_baked and cycle_min:
        if electric and ev is not None:
            cycles = ev["cycles"]
        lorries = lorries_for(trips, cycles, plan["work_days"])
    else:
        lorries = None

    # ---- material or disposal ---------------------------------------------------------
    cm = ctx["cm"](line["material_type"])
    dest = _dest_of(ctx, s["route_id"]) or line.get("dest_id")
    disp = s.get("disposal_to") or disposal_route_of(cp, locs.get(dest))
    mat = {"kg_per_t": None, "method": "none", "status": None}
    mat_t = dis_t = dis_kg = None
    if disp:
        dis_kg = disposal_factor(cp, cm, disp) if cm else None
        dis_t = disposal_t(tonnes, dis_kg)
        if dis_kg is None:
            flags.append(FLAG_NO_DISPOSAL_FACTOR)
    else:
        mf = material_factor(cp, cm, epd=s.get("epd"), reused=bool(s.get("reused")) and not s.get("epd"))
        rp = s.get("recycled_pct") or 0.0
        if rp and mf.get("recycled_enabled") and not s.get("epd") and not s.get("reused"):
            mf = material_factor(cp, cm, recycled_pct=rp)
        mat = mf
        mat_t = material_t(tonnes, mf.get("kg_per_t"))

    total = (mat_t or 0.0) + (tr_t or 0.0) + (dis_t or 0.0)
    return {
        "route_id": s["route_id"], "base_route_id": line["route_id"], "month_index": line["month_index"],
        "material_type": line["material_type"], "carbon_material": cm, "sheet": sheet_of(cm, bool(disp)),
        "vehicle": veh, "fuel": "electric" if electric else "diesel", "vehicle_class": vclass, "tkm_class": tcls,
        "tonnes": tonnes, "trips": trips, "payload_t": payload, "baked": base_baked,
        "one_way_km": one_way, "return_km": ret, "km_trip": km_trip, "vkm": vkm, "laden_km": laden_km,
        "cycle_min": cycle_min, "cycles_per_day": cycles, "lorries": lorries, "kwh": kwh,
        "ev": ev, "kg_per_km": vf["kg_per_km"], "factor_status": vf["status"],
        "material_kg_per_t": mat.get("kg_per_t"), "material_method": mat.get("method"),
        "material_status": mat.get("status"), "material_source": mat.get("source"),
        "recycled_pct": mat.get("recycled_pct"), "material_t": mat_t,
        "disposal_route": disp, "disposal_kg_per_t": dis_kg, "disposal_t": dis_t,
        "transport_t": tr_t, "transport_nh_t": nh_t, "transport_tkm_t": tkm_t,
        "total_t": total, "flags": flags, "ipt": line.get("ipt"),
    }


def _state0(line):
    return {"vehicle": line["vehicle_type"], "route_id": line["route_id"], "alt_index": 0, "km_scale": 1.0,
            "recycled_pct": 0.0, "epd": None, "reused": False, "disposal_to": None}


# =========================================================================== #
#  Totals                                                                       #
# =========================================================================== #
def _r(v):
    return round(v, 3) if isinstance(v, float) else v


def _totals(evals, cp, spend_m=None, allocation=None):
    t = {"lines": len(evals), "baked_lines": 0, "tonnes": 0.0, "baked_tonnes": 0.0, "trips": 0, "electric_trips": 0,
         "vkm": 0.0, "laden_km": 0.0, "tkm": 0.0, "kwh": 0.0, "material_t": 0.0, "transport_t": 0.0,
         "transport_nh_t": 0.0, "transport_tkm_t": 0.0, "disposal_t": 0.0, "total_t": 0.0,
         "material_excluded_tonnes": 0.0, "disposal_excluded_tonnes": 0.0, "flags": {}}
    by_cat, by_route, by_month, sheets = {}, {}, {}, []
    alloc = {k: 0.0 for k in ALLOCATION + (NOT_ALLOCATED,)} if allocation else None
    for i, e in enumerate(evals):
        t["tonnes"] += e["tonnes"]
        t["trips"] += e["trips"]
        if e["fuel"] == "electric":
            t["electric_trips"] += e["trips"]
        if e["baked"]:
            t["baked_lines"] += 1
            t["baked_tonnes"] += e["tonnes"]
            t["vkm"] += e["vkm"] or 0.0
            t["laden_km"] += e["laden_km"] or 0.0
            t["tkm"] += (e["tonnes"] * (e["one_way_km"] or 0.0))
            t["transport_t"] += e["transport_t"] or 0.0
            t["transport_nh_t"] += e["transport_nh_t"] or 0.0
            t["transport_tkm_t"] += e["transport_tkm_t"] or 0.0
            t["kwh"] += e["kwh"] or 0.0
        t["material_t"] += e["material_t"] or 0.0
        if e["material_t"] is None and not e["disposal_route"]:
            t["material_excluded_tonnes"] += e["tonnes"]
        if e["disposal_route"] and e["disposal_t"] is None:
            t["disposal_excluded_tonnes"] += e["tonnes"]
        t["disposal_t"] += e["disposal_t"] or 0.0
        t["total_t"] += e["total_t"]
        for f in e["flags"]:
            t["flags"][f] = t["flags"].get(f, 0) + 1
        c = by_cat.setdefault(e["material_type"], {"category": e["material_type"], "carbon_material": e["carbon_material"],
                                                   "sheet": e["sheet"], "tonnes": 0.0, "material_t": 0.0,
                                                   "transport_t": 0.0, "disposal_t": 0.0, "total_t": 0.0})
        r = by_route.setdefault(e["route_id"], {"route_id": e["route_id"], "tonnes": 0.0, "transport_t": 0.0,
                                                "total_t": 0.0, "vehicles": set()})
        m = by_month.setdefault(e["month_index"], {"month_index": e["month_index"], "total_t": 0.0, "transport_t": 0.0,
                                                   "lorries": 0, "trips": 0})
        for k in ("tonnes", "material_t", "transport_t", "disposal_t", "total_t"):
            c[k] += e[k] or 0.0
        for k in ("tonnes", "transport_t", "total_t"):
            r[k] += e[k] or 0.0
        r["vehicles"].add(e["vehicle"])
        m["total_t"] += e["total_t"]
        m["transport_t"] += e["transport_t"] or 0.0
        m["trips"] += e["trips"]
        m["lorries"] += e["lorries"] or 0
        sheets.append({"id": i, "carbon_material": e["carbon_material"], "t": e["total_t"], "disposal": bool(e["disposal_route"])})
        if alloc is not None:
            pcts = allocation.get(e["base_route_id"]) or allocation.get(e["material_type"]) or {}
            for k, x in allocate(e["total_t"], pcts).items():
                alloc[k] += x
    t["excludes_unbaked"] = t["baked_lines"] < t["lines"]
    peak = max(by_month.values(), key=lambda x: x["lorries"], default=None)
    t["lorries_peak"] = peak["lorries"] if peak else 0
    t["lorries_peak_month"] = peak["month_index"] if peak else None
    for r in by_route.values():
        r["vehicles"] = sorted(r["vehicles"])
    out = {
        "totals": {k: _r(v) for k, v in t.items()},
        "by_category": sorted([{k: _r(v) for k, v in c.items()} for c in by_cat.values()], key=lambda x: -x["total_t"]),
        "by_route": sorted([{k: _r(v) for k, v in r.items()} for r in by_route.values()], key=lambda x: -x["total_t"]),
        "by_month": [{k: _r(v) for k, v in by_month[k2].items()} for k2 in sorted(by_month)],
        "sheets": {k: round(v, 3) for k, v in split_sheets(sheets).items()},
        "benchmarks": benchmarks(t, evals, cp, spend_m),
    }
    if alloc is not None:
        out["allocation"] = {k: round(v, 3) for k, v in alloc.items()}
    return out


def benchmarks(t, evals, cp, spend_m=None):
    """
    The figures the brief names, each against a published reference — never against an invented
    limit (no 'per delivery' limit exists in any rule): kg CO2e per tonne delivered; kg CO2e per
    tonne-km against the DESNZ 2026 average-laden tonne-km figure for each line's size class;
    the laden share; the share of zero-emission deliveries (NH: all HGVs delivering to its sites
    electric or hydrogen by 2040); tCO2e per £m where spend is typed (NH's own intensity 159 → 181
    t/£m). A line that counts its loaded leg only (return not baked) would read as an empty-free
    haul, so it is left out of the per-tonne, per-tonne-km and laden-share figures, and counted.
    """
    use = [e for e in evals if e["baked"] and FLAG_RETURN_ESTIMATED not in e["flags"]]
    bt = sum(e["tonnes"] for e in use)
    tkm = sum(e["tonnes"] * (e["one_way_km"] or 0.0) for e in use)
    tr = sum(e["transport_t"] or 0.0 for e in use)
    vkm = sum(e["vkm"] or 0.0 for e in use)
    lkm = sum(e["laden_km"] or 0.0 for e in use)
    ref_num = sum((e["tonnes"] * (e["one_way_km"] or 0.0)) * (tkm_factor(cp, e.get("tkm_class") or e["vehicle_class"]) or 0.0)
                  for e in use)
    ref = (ref_num / tkm) if tkm > 0 else None
    kg_tkm = (tr * 1000.0 / tkm) if tkm > 0 else None
    # 11 Oct 2026: NH restated its intensity at 2023 prices (annual progress report 2025-26): 159 → 181,
    # a rise. Read from its OWN key only, so a document still carrying the superseded 210 → 148 key
    # (the 2025 update) can never feed it
    kpi = ((cp.get("benchmarks") or {}).get("nh_kpi_2023_prices")) or None
    spend = _num(spend_m)
    return {
        "kg_co2e_per_t_delivered": round(tr * 1000.0 / bt, 3) if bt > 0 else None,
        "kg_co2e_per_t_all_in": round(t["total_t"] * 1000.0 / t["tonnes"], 3) if t["tonnes"] > 0 else None,
        "kg_co2e_per_tkm": round(kg_tkm, 5) if kg_tkm is not None else None,
        "desnz_kg_co2e_per_tkm": round(ref, 5) if ref is not None else None,
        "vs_national_average_pct": (round((kg_tkm / ref - 1.0) * 100.0, 1) if (kg_tkm is not None and ref) else None),
        "laden_share_pct": round(lkm * 100.0 / vkm, 1) if vkm > 0 else None,
        "excluded_lines": sum(1 for e in evals if e["baked"]) - len(use),
        "zero_emission_share_pct": round(t["electric_trips"] * 100.0 / t["trips"], 1) if t["trips"] > 0 else None,
        "t_co2e_per_gbp_m": round(t["total_t"] / spend, 2) if spend and spend > 0 else None,
        "nh_kpi": ({"series": {k: v for k, v in kpi.items() if k[:2] == "20"}, "price_base": kpi.get("base_prices"),
                    "source": kpi.get("source"), "url": kpi.get("url"), "status": kpi.get("status"),
                    "checked": kpi.get("checked")} if isinstance(kpi, dict) else None),
        "nh_target": (cp.get("benchmarks") or {}).get("nh_target"),
    }


# =========================================================================== #
#  The scenario                                                                 #
# =========================================================================== #
def _check_allocation(allocation):
    if allocation is None:
        return
    if not isinstance(allocation, dict):
        raise CarbonError("allocation is {category or route id: {Fencing: %, …}}")
    for k, pcts in allocation.items():
        allocate(1.0, pcts)                                      # refuses over 100 % up front


def scenario(acc=None, alternatives=None, baseline_levers=None, from_month=None, to_month=None,
             status="Approved", spend_m=None, allocation=None, factors=None):
    """
    The baseline (the caller's visible forecast lines, as approved, with Government primary
    material factors and the forecast vehicles — adjusted by `baseline_levers`) and each
    alternative (`[{name, levers: [...]}]`). Per alternative: its totals, the delta, and the
    per-driver deltas RANKED by tCO2e moved — each driver's levers applied alone to the
    baseline — plus the interaction (combined minus the sum of the singles), every delta taken
    on unrounded sums. Raises CarbonError.
    """
    acc = acc if acc is not None else access.current()
    factors = factors if factors is not None else conversions.load_factors()
    cp = params(factors)
    vs = vehicles(factors)
    doc = _doc(factors, vs, cp)
    routes = _routes()
    locs = _locations()
    plan = factors.get("planning", {}) or {}
    cm_cache = {}

    def cm_of(cat):
        if cat not in cm_cache:
            cm_cache[cat] = carbon_material_of(cat, factors)
        return cm_cache[cat]

    ctx = {"cp": cp, "doc": doc, "vs": vs, "geo": _Geo(), "locs": locs, "routes": routes, "cm": cm_of,
           "plan": {"shift_h": float(plan.get("shift_hours_per_day") or 10),
                    "work_days": float(plan.get("working_days_per_month") or 22)}}
    _check_allocation(allocation)
    _check_levers(baseline_levers, vs, routes)
    alts = list(alternatives or [])
    for a in alts:
        _check_levers(a.get("levers"), vs, routes)

    cl = costlines.lines(acc, from_month=from_month, to_month=to_month, status=status, factors=factors)
    lines = cl["lines"]
    notes = set()
    states0 = [_apply(_state0(l), l, baseline_levers, ctx, notes) for l in lines]
    base_eval = [_eval(l, s, ctx) for l, s in zip(lines, states0)]
    base = _totals(base_eval, cp, spend_m, allocation)
    bt = sum(e["total_t"] for e in base_eval)

    out_alts, alt_evals = [], []
    for a in alts:
        lv = a.get("levers") or []
        a_notes = set()
        ev = [_eval(l, _apply(s, l, lv, ctx, a_notes), ctx) for l, s in zip(lines, states0)]
        alt_evals.append(ev)
        tot = _totals(ev, cp, spend_m, allocation)
        drivers, singles = [], 0.0
        for d in DRIVERS:
            dl = [x for x in lv if x.get("driver") == d]
            if not dl:
                continue
            de = [_eval(l, _apply(s, l, dl, ctx, set()), ctx) for l, s in zip(lines, states0)]
            dt = sum(e["total_t"] for e in de) - bt
            changed = sum(1 for e0, e1 in zip(base_eval, de) if abs(e1["total_t"] - e0["total_t"]) > 1e-9)
            singles += dt
            drivers.append({"driver": d, "label": DRIVER_LABELS[d], "delta_t": round(dt, 3),
                            "delta_pct": round(dt * 100.0 / bt, 1) if bt else None, "lines_changed": changed})
        drivers.sort(key=lambda x: -abs(x["delta_t"]))
        delta = sum(e["total_t"] for e in ev) - bt
        interaction = delta - singles
        out_alts.append(dict(tot, name=str(a.get("name") or "Alternative"), levers=lv,
                             delta_t=round(delta, 3), delta_pct=(round(delta * 100.0 / bt, 1) if bt else None),
                             # 11 Oct 2026: the change in lorry loads, so the page never subtracts
                             delta_trips=sum(e["trips"] for e in ev) - sum(e["trips"] for e in base_eval),
                             drivers=drivers, interaction_t=(0.0 if abs(interaction) < 5e-4 else round(interaction, 3)),
                             notes=sorted(a_notes), fleet=_fleet_summary(ev)))

    return {
        "baseline": dict(base, fleet=_fleet_summary(base_eval), notes=sorted(notes)),
        "alternatives": out_alts,
        "fleet_compare": fleet_compare(lines, states0, ctx),
        "options": options(lines, ctx, factors),
        "factors": provenance(base_eval, ctx, alt_evals, [baseline_levers or []] + [a.get("levers") or [] for a in alts]),
        "lines": [_line_out(e) for e in base_eval],
        "working_days_per_month": ctx["plan"]["work_days"],
        "shift_hours_per_day": ctx["plan"]["shift_h"],
        "status": status, "from": from_month, "to": to_month,
        "unit": "km",
        "limits": list(LIMITS),
        "planned": list(((cp.get("planned") or {}).get("items")) or []),
        "methods": {
            "headline": "vehicle-km: trips × routed km of both legs × the vehicle's kg CO2e per vehicle-km (DESNZ 2026, tank-to-wheel)",
            "nh_tool": "NH Carbon Tool v2.7 basis: tonnes × one-way km × (laden + unladen) ÷ 2 × 2, 2024 factors with well-to-tank",
            "tonne_km": "DESNZ 2026 tonne-km for each vehicle's size class, average laden — what a tonne-km calculator gives for the same haul",
        },
    }


def _line_out(e):
    keep = ("route_id", "month_index", "material_type", "carbon_material", "sheet", "vehicle", "fuel", "tonnes",
            "trips", "baked", "one_way_km", "km_trip", "kg_per_km", "factor_status", "material_kg_per_t",
            "material_method", "material_status", "material_t", "transport_t", "transport_nh_t",
            "disposal_route", "disposal_kg_per_t", "disposal_t", "total_t", "flags", "ipt")
    return {k: _r(e[k]) for k in keep}


def _fleet_summary(evals):
    months = {}
    for e in evals:
        m = months.setdefault(e["month_index"], {"lorries": 0, "trips": 0, "unsized": 0})
        m["trips"] += e["trips"]
        if e["lorries"] is None:
            m["unsized"] += 1
        else:
            m["lorries"] += e["lorries"]
    peak = max(months.items(), key=lambda kv: kv[1]["lorries"], default=(None, {"lorries": 0}))
    return {"lorries_peak": peak[1]["lorries"], "peak_month": peak[0],
            "trips": sum(m["trips"] for m in months.values()),
            "kwh": round(sum(e["kwh"] or 0.0 for e in evals), 1),
            "transport_t": round(sum(e["transport_t"] or 0.0 for e in evals), 3),
            "unsized_lines": sum(m["unsized"] for m in months.values())}


def fleet_compare(lines, states0, ctx):
    """
    Diesel vs electric for the SAME tonnage: every baked baseline line whose vehicle has an
    electric variant, run once as forecast and once on the variant. Lorries (peak month),
    trips, kWh, tCO2e, and the electric day: payload, range per charge, charges, minutes per
    charge. A line whose electric trip needs more than one battery is left out of BOTH sides
    and counted, so the two lorry figures always size the same lines.
    """
    vs = ctx["vs"]
    sel = [(l, s) for l, s in zip(lines, states0) if l.get("baked") and electric_variant(vs, s["vehicle"])]
    if not sel:
        return {"lines": 0, "diesel": None, "electric": None, "infeasible_lines": 0,
                "note": "no forecast vehicle on a baked route has an electric variant"}
    pairs = []
    infeasible = 0
    for l, s in sel:
        e = _eval(l, dict(s, vehicle=electric_variant(vs, s["vehicle"])), ctx)
        if FLAG_EV_INFEASIBLE in e["flags"]:
            infeasible += 1
            continue
        pairs.append((_eval(l, s, ctx), e))
    d_ev, e_ev = [p[0] for p in pairs], [p[1] for p in pairs]
    d, e = _fleet_summary(d_ev), _fleet_summary(e_ev)
    days = [x["ev"] for x in e_ev if x.get("ev")]
    evs = sorted({x["vehicle"] for x in e_ev})
    return {
        "lines": len(pairs), "infeasible_lines": infeasible, "tonnes": round(sum(x["tonnes"] for x in d_ev), 3),
        "diesel": d, "electric": e,
        "electric_profiles": [{"vehicle": k, "payload_t": _num(vs[k].get("payload_t")), "kwh_per_km": _num(vs[k].get("kwh_per_km")),
                               "battery_kwh_usable": _num(vs[k].get("battery_kwh_usable")), "charge_kw": _num(vs[k].get("charge_kw")),
                               "twin": vs[k].get("geometry_twin"),
                               "twin_payload_t": _num((vs.get(vs[k].get("geometry_twin")) or {}).get("payload_t")),
                               "status": "ASSUMPTION",
                               "source": "payload, battery and charger typed on the profile (ZEHID 2026 ranges); see Config → Vehicles"}
                              for k in evs],
        "charges_per_lorry_day_max": max((x["charges"] for x in days), default=0),
        "minutes_per_charge_max": (round(max((x["minutes_per_charge"] or 0) for x in days), 1) if days else None),
        "range_per_charge_km_min": (round(min(x["range_per_charge_km"] for x in days if x["range_per_charge_km"]), 1)
                                    if any(x["range_per_charge_km"] for x in days) else None),
        "delta_t": round(sum(x["transport_t"] or 0.0 for x in e_ev) - sum(x["transport_t"] or 0.0 for x in d_ev), 3),
    }


def options(lines, ctx, factors):
    """What the page's controls may offer: the categories in view with their material options, the
    vehicles per category (and their electric variants), and per route the baked alternatives,
    the other suppliers to the same destination and the other destinations from the same origin
    (each with its place name and whether it is baked), and the disposal routes the Government
    file publishes for the route's material."""
    cp, vs, geo, routes, locs = ctx["cp"], ctx["vs"], ctx["geo"], ctx["routes"], ctx["locs"]
    hidden = set(conversions.hidden_vehicle_names(factors))
    cats = {}
    for l in lines:
        c = cats.setdefault(l["material_type"], {"category": l["material_type"], "tonnes": 0.0})
        c["tonnes"] += float(l.get("tonnes") or 0)
    mats = []
    for name, c in cats.items():
        cm = ctx["cm"](name)
        mf = material_factor(cp, cm)
        listed = [v for v in (((factors.get("material_categories") or {}).get(name) or {}).get("vehicles") or [])
                  if v in vs and v not in hidden]
        listed += [electric_variant(vs, v) for v in listed if electric_variant(vs, v)]
        mats.append(dict(c, tonnes=round(c["tonnes"], 3), carbon_material=cm, sheet=sheet_of(cm),
                         label=mf.get("label"), primary=mf.get("primary"), closed_loop=mf.get("closed_loop"),
                         reused=mf.get("reused"), recycled_enabled=mf.get("recycled_enabled"),
                         recycled_reason=mf.get("recycled_reason"), vehicles=listed,
                         disposal_routes=disposal_routes_published(cp, cm)))
    veh = []
    for k in sorted({l["vehicle_type"] for l in lines} | {x for m in mats for x in m["vehicles"]}):
        v = vs.get(k) or {}
        vf = vehicle_factor(ctx["doc"], cp, k)
        veh.append({"vehicle": k, "label": ((v.get("labels") or {}).get("en")) or k, "fuel": v.get("fuel") or "diesel",
                    "payload_t": _num(v.get("payload_t")), "kg_per_km": vf["kg_per_km"], "status": vf["status"],
                    "source": vf["source"], "id": vf.get("id"), "electric_variant": electric_variant(vs, k),
                    "geometry_twin": v.get("geometry_twin"), "vehicle_class": fairprice.vehicle_class(k, ctx["doc"]),
                    "scenario_only": bool(v.get("scenario_only"))})
    rts = []
    for rid in sorted({l["route_id"] for l in lines}):
        r = routes.get(rid) or {}
        vehs = sorted({l["vehicle_type"] for l in lines if l["route_id"] == rid})
        profs = tuple(vehs) + tuple(filter(None, (electric_variant(vs, x) for x in vehs)))
        cm = ctx["cm"]((r.get("material_category") or "")) or ctx["cm"](next((l["material_type"] for l in lines if l["route_id"] == rid), ""))
        rts.append({
            "route_id": rid, "origin_id": r.get("origin_id"), "dest_id": r.get("dest_id"),
            "origin_name": (locs.get(r.get("origin_id")) or {}).get("name"),
            "dest_name": (locs.get(r.get("dest_id")) or {}).get("name"),
            "material_category": r.get("material_category"),
            "disposal_route": disposal_route_of(cp, locs.get(r.get("dest_id"))),
            "disposal_routes": disposal_routes_published(cp, cm),
            "alts": {v: geo.alts(rid, v) for v in vehs},
            # other suppliers of the same material to the same destination, and other destinations
            # for the same material from the same origin (a tip vs a recycling site), each with
            # the place it names (never a bare id) and whether it is baked for the line's vehicle
            "suppliers": [{"route_id": k, "origin_name": (locs.get(x.get("origin_id")) or {}).get("name"),
                           "baked": geo.baked_any(k, profs)}
                          for k, x in sorted(routes.items()) if k != rid and x.get("dest_id") == r.get("dest_id")
                          and (x.get("material_category") or "") == (r.get("material_category") or "")],
            "destinations": [{"route_id": k, "dest_name": (locs.get(x.get("dest_id")) or {}).get("name"),
                              "disposal_route": disposal_route_of(cp, locs.get(x.get("dest_id"))),
                              "baked": geo.baked_any(k, profs)}
                             for k, x in sorted(routes.items()) if k != rid and x.get("origin_id") == r.get("origin_id")
                             and (x.get("material_category") or "") == (r.get("material_category") or "")],
        })
    return {"materials": mats, "vehicles": veh, "routes": rts, "drivers": DRIVER_LABELS,
            "allocation": list(ALLOCATION), "disposal_routes": list(DISPOSAL_ROUTES)}


def provenance(evals, ctx, alt_evals=(), lever_sets=()):
    """Every factor a figure on the page used — in the baseline AND in every alternative: value,
    unit, source, year, status (VERIFIED / DERIVED / ASSUMPTION), the gov.uk row ID and the GWP
    basis — for the page's hover text. A supplier EPD is listed as typed (ASSUMPTION), a recycled
    blend as DERIVED from its two published rows."""
    cp, doc, vs = ctx["cp"], ctx["doc"], ctx["vs"]
    every = list(evals) + [e for ev in alt_evals for e in ev]
    out = []
    for name in sorted({e["carbon_material"] for e in every if e["carbon_material"]}):
        out.append(_prov_material(cp, name))
    for vname in sorted({e["vehicle"] for e in every}
                        | {electric_variant(vs, e["vehicle"]) for e in evals if electric_variant(vs, e["vehicle"])}):
        out.append(dict(vehicle_factor(doc, cp, vname), key=f"vehicle:{vname}", label=vname, unit="kg CO2e per vehicle-km"))
    seen = set()
    for e in every:
        if e["material_method"] == "blend":
            k = f"blend:{e['carbon_material']}:{e['recycled_pct']}"
            if k not in seen:
                seen.add(k)
                mf = material_factor(cp, e["carbon_material"])
                out.append({"key": k, "label": f"{mf.get('label')} at {e['recycled_pct']:g} % recycled", "value": round(e["material_kg_per_t"], 5),
                            "unit": "kg CO2e per tonne", "status": "DERIVED", "year": 2026,
                            "source": f"linear blend of the published primary {mf.get('primary')} and closed-loop {mf.get('closed_loop')} kg CO2e/t",
                            "ids": mf.get("ids")})
        if e["material_method"] == "epd":
            k = f"epd:{e['material_type']}:{e['material_kg_per_t']}"
            if k not in seen:
                seen.add(k)
                out.append({"key": k, "label": f"Supplier EPD — {e['material_type']}", "value": e["material_kg_per_t"],
                            "unit": "kg CO2e per tonne", "status": "ASSUMPTION", "year": None, "source": e["material_source"]})
    el = conversions.electricity_factors(doc)
    out.append({"key": "electricity", "label": "UK electricity, generation + T&D", "unit": "kg CO2e per kWh",
                "value": round((_num(el.get("generation_kg_co2e_per_kwh")) or 0) + (_num(el.get("td_kg_co2e_per_kwh")) or 0), 5),
                "value_wtw": round(sum((_num(el.get(k)) or 0) for k in ("generation_kg_co2e_per_kwh", "td_kg_co2e_per_kwh",
                                                                          "wtt_generation_kg_co2e_per_kwh", "wtt_td_kg_co2e_per_kwh")), 5),
                "ids": [el.get("generation_id"), el.get("td_id"), el.get("wtt_generation_id"), el.get("wtt_td_id")],
                "source": el.get("source"), "year": el.get("year"), "status": el.get("status"), "gwp": el.get("gwp")})
    eh = cp.get("electric_hgv") or {}
    out.append({"key": "kwh_per_km", "label": "Electric lorry energy use (default)", "unit": "kWh per km",
                "value": eh.get("kwh_per_km_default"), "source": eh.get("kwh_per_km_source"), "year": 2026,
                "status": eh.get("kwh_per_km_status") or "DERIVED"})
    out.append({"key": "ev_payload", "label": "Electric payload penalty", "unit": "t",
                "value": eh.get("payload_penalty_range_t"), "source": "ZEHID annual report 2026", "year": 2026,
                "status": "ASSUMPTION"})
    out.append({"key": "zev_allowance", "label": "Zero-emission HGV weight allowance", "unit": "t",
                "value": eh.get("zev_gvw_allowance_t"), "source": eh.get("zev_allowance_status"), "year": 2026,
                "status": "ASSUMPTION"})
    tk = ((cp.get("transport") or {}).get("tonne_km_2026")) or {}
    for cls in sorted({e.get("tkm_class") for e in every if e.get("tkm_class")} | {"rigid", "artic"}):
        r = tk.get(cls) or {}
        out.append({"key": f"tkm:{cls}", "label": f"DESNZ 2026 tonne-km, {r.get('row') or cls}", "unit": "kg CO2e per tonne-km",
                    "value": r.get("kg_co2e_per_tkm"), "ids": [r.get("id")], "source": tk.get("source"),
                    "year": tk.get("year"), "status": tk.get("status"), "gwp": tk.get("gwp"), "note": r.get("row")})
    nh = ((cp.get("transport") or {}).get("nh_carbon_tool_v27")) or {}
    out.append({"key": "nh_tool", "label": "NH Carbon Tool v2.7 transport basis", "unit": "t CO2e per tonne per one-way km",
                "value": nh_tool_t_per_t_km(cp), "source": nh.get("source"), "year": nh.get("year"),
                "status": nh.get("status"), "note": nh.get("basis"), "formula": nh.get("formula")})
    return out
