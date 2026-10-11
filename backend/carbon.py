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
                     material class (soils → Earthworks; every other class → Bulk Materials)
Wayscope's HEADLINE transport figure is the vehicle-km method the Dashboard and the map
already use (trips × routed km × the vehicle's kg CO2e per vehicle-km, costlines.co2_t).
The tool's tonne-km figure and the DESNZ 2026 class tonne-km figure are returned beside it,
each labelled, and never added into it.

ONE DISTANCE, ONE TRIP COUNT
----------------------------
The baseline reads costlines.lines() — the Dashboard's own read — for tonnes, trips, the
one-way and return km and the cycle. A line whose route is not baked has no distance: its
transport carbon is None and it is EXCLUDED from every transport total, which says so.
Never estimated. An ALTERNATIVE keeps every line it changes on the baseline's baked set:
when the alternative's vehicle or route has no baked geometry of its own, the baseline
vehicle's distance on that route is used and the line is flagged (KM_FROM_BASELINE_VEHICLE)
rather than silently dropped — a dropped line would read as a saving.

FACTORS
-------
backend/factors.json `carbon` — UK Government GHG conversion factors 2026, flat file v1.2,
OGL v3.0, each with its row ID, year, scope, GWP basis and a status (VERIFIED / DERIVED /
ASSUMPTION). A tenant whose live document predates the block reads the FILE's block key by
key (params()), the file's scenario-only electric profiles (vehicles()) and the file's
carbon_material mapping for a category of the same name — so the page works on a tenant
seeded before 10 Oct without a re-import. No ICE factor is used (ICE commercial use ended
30 Sep 2026). Concrete has ONE generic figure: a supplier EPD (value + source) replaces it
per material category, never an invented grade. Soils have no primary factor, so earthworks
carbon is haulage + disposal.

ELECTRIC
--------
The 2026 Government set has no electric HGV factor. An electric profile's kg CO2e/km is
kWh/km × UK electricity (generation + T&D), derived in conversions._emissions() — the one
place. Fleet size for an electric profile adds charging time to the shift: the battery
starts the shift full, a trip's energy must fit the usable battery, and the energy beyond
one battery is topped up at the profile's charger power (ev_day()).

Nothing here writes. A scenario is computed on request and stored nowhere.
"""
import copy
import math

import access
import conversions
import costlines
import db
import derived
import fairprice
import network

KM_PER_MILE = 1.609344
SHEET_BULK, SHEET_EARTHWORKS = "Bulk Materials", "Earthworks"
ALLOCATION = ("Fencing", "Drainage", "Road Pavements", "Civils Structures", "Waste")
NOT_ALLOCATED = "Not Allocated"
DRIVERS = ("material", "recycled", "source", "route", "vehicle", "fuel", "disposal")
DRIVER_LABELS = {
    "material": "Material choice (supplier EPD or re-used)",
    "recycled": "Recycled content",
    "source": "Source distance / supplier",
    "route": "Haul route",
    "vehicle": "Vehicle",
    "fuel": "Diesel vs electric",
    "disposal": "Disposal route",
}
DISPOSAL_ROUTES = ("landfill", "closed_loop", "open_loop", "combustion")
FLAG_UNBAKED = derived.FLAG_UNBAKED
FLAG_KM_BORROWED = "KM_FROM_BASELINE_VEHICLE"
FLAG_KM_SCALED = "KM_SCALED"
FLAG_ALT_UNBAKED = "ALT_ROUTE_NOT_BAKED"
FLAG_EV_INFEASIBLE = "EV_TRIP_EXCEEDS_BATTERY"
FLAG_RETURN_ESTIMATED = "RETURN_NOT_BAKED"
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
    """A request the rules refuse — allocation over 100 %, an EPD with no source, an unknown vehicle."""


def _num(x):
    try:
        return float(x) if x is not None and x != "" else None
    except (TypeError, ValueError):
        return None


# =========================================================================== #
#  Factors: the live document, falling back to the file                        #
# =========================================================================== #
def _merge(seed, live):
    """Recursive: dicts merge key by key, the live value wins where it is not None."""
    if isinstance(seed, dict) and isinstance(live, dict):
        out = {}
        for k in list(seed) + [k for k in live if k not in seed]:
            if k in live and live[k] is not None:
                out[k] = _merge(seed.get(k), live[k]) if k in seed else copy.deepcopy(live[k])
            else:
                out[k] = copy.deepcopy(seed.get(k))
        return out
    return copy.deepcopy(live if live is not None else seed)


def _file():
    try:
        return conversions.load_factors_file()
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
    """The Government material class a category is priced with, or None (excluded, labelled)."""
    factors = factors if factors is not None else conversions.load_factors()
    c = (factors.get("material_categories") or {}).get(category)
    cm = c.get("carbon_material") if isinstance(c, dict) else None
    if cm is None:
        fc = (_file().get("material_categories") or {}).get(category)
        cm = fc.get("carbon_material") if isinstance(fc, dict) else None
    return cm


def sheet_of(carbon_material):
    """The NH Carbon Tool sheet a line belongs on — ONE sheet per line (earthworks excludes bulk)."""
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
def material_factor(cp, material, recycled_pct=0.0, epd=None, reused=False):
    """
    kg CO2e per tonne of one Government material class.

    recycled_pct blends primary and closed-loop linearly by the recycled share — only where the
    file publishes BOTH; otherwise recycled content is refused with the reason. `epd` =
    {"kg_per_t", "source"} replaces the Government figure (a supplier EPD; the source is
    required). `reused` takes the published Re-used row where one exists.
    """
    m = (cp.get("materials") or {}).get(material) if material else None
    kg = (m or {}).get("kg_co2e_per_t") or {}
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
        return dict(base, kg_per_t=v, method="epd", recycled_pct=None, epd_source=src, status="EPD (supplier)")
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
    m = (cp.get("materials") or {}).get(material) or {}
    return _num((m.get("disposal_kg_co2e_per_t") or {}).get(route))


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
    return ((float(nh.get("laden_t_co2e_per_tkm") or 0) + float(nh.get("unladen_t_co2e_per_tkm") or 0)) / 2.0) * 2.0


def transport_nh_t(one_way_km, tonnes, cp, conversion=1.0):
    """The NH Carbon Tool's transport row: one-way km × tonnes × conversion × (laden + unladen)/2 × 2."""
    if one_way_km is None or tonnes is None:
        return None
    return float(one_way_km) * float(tonnes) * float(conversion) * nh_tool_t_per_t_km(cp)


def tkm_factor(cp, vehicle_class):
    """kg CO2e per tonne-km, DESNZ 2026 average laden, for the class (the benchmark)."""
    t = ((cp.get("transport") or {}).get("tonne_km_2026")) or {}
    return _num((t.get("artic" if vehicle_class == "artic" else "rigid") or {}).get("kg_co2e_per_tkm"))


def transport_tkm_t(one_way_km, tonnes, cp, vehicle_class):
    """The same haul on the DESNZ 2026 class tonne-km factor (what a tonne-km calculator says)."""
    f = tkm_factor(cp, vehicle_class)
    if one_way_km is None or tonnes is None or f is None:
        return None
    return float(tonnes) * float(one_way_km) * f / 1000.0


def allocate(t_co2e, pcts):
    """
    Split a row's tCO2e over the tool's five categories by percentage; the remainder is 'Not
    Allocated'. A sum over 100 % is refused, as the tool's sheet flags "err".
    """
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
    The double-count rule: each row lands on exactly ONE sheet by its material class; the
    Earthworks total therefore excludes every bulk-material row. `rows` = [{id, carbon_material,
    t}]. Refuses a row id that appears twice.
    """
    seen, out = set(), {SHEET_BULK: 0.0, SHEET_EARTHWORKS: 0.0, None: 0.0}
    for r in rows:
        rid = r.get("id")
        if rid in seen:
            raise CarbonError(f"row {rid} is counted twice")
        seen.add(rid)
        out[sheet_of(r.get("carbon_material"))] += float(r.get("t") or 0.0)
    return {SHEET_BULK: out[SHEET_BULK], SHEET_EARTHWORKS: out[SHEET_EARTHWORKS], "unclassed": out[None]}


def electric_kg_per_km(factors, v, basis="ttw"):
    """kWh/km × UK electricity — conversions' function, the one place it is computed."""
    return conversions.electric_kg_per_km(factors, v, basis)


def ev_day(cycle_min, km_trip, shift_hours, kwh_per_km, battery_kwh, charge_kw):
    """
    Cycles one electric lorry can run in a shift once charging is counted. The battery starts the
    shift full; a trip's energy must fit the usable battery; energy beyond one battery is topped
    up at charge_kw (minutes = kWh ÷ kW × 60), in as many stops as whole batteries it needs.
    Returns {cycles, charges, charge_minutes, minutes_per_charge, kwh_per_trip, kwh_day,
    daily_range_km, feasible}.
    """
    cyc, km, kwh, bat, kw = (_num(cycle_min), _num(km_trip), _num(kwh_per_km), _num(battery_kwh), _num(charge_kw))
    shift_min = float(shift_hours or 10) * 60.0
    out = {"cycles": 0, "charges": 0, "charge_minutes": 0.0, "minutes_per_charge": None,
           "kwh_per_trip": None, "kwh_day": 0.0, "daily_range_km": None, "feasible": True}
    if not cyc or cyc <= 0 or km is None or not kwh:
        return dict(out, feasible=False)
    e_trip = km * kwh
    out["kwh_per_trip"] = e_trip
    if not bat or bat <= 0 or not kw or kw <= 0:
        n = int(shift_min // cyc)                       # no battery figures: the diesel cycle, stated
        return dict(out, cycles=n, kwh_day=n * e_trip)
    out["daily_range_km"] = bat / kwh
    if e_trip > bat + 1e-9:
        return dict(out, feasible=False)
    n = int(shift_min // cyc)
    while n > 0:
        deficit = max(0.0, n * e_trip - bat)
        charges = int(math.ceil(round(deficit / bat, 9))) if deficit > 0 else 0
        minutes = deficit / kw * 60.0
        if n * cyc + minutes <= shift_min + 1e-9:
            return dict(out, cycles=n, charges=charges, charge_minutes=minutes,
                        minutes_per_charge=(minutes / charges if charges else None), kwh_day=n * e_trip)
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
    DERIVED (electric) or ASSUMPTION (any other typed figure, or the _default fallback)."""
    vs = doc.get("vehicles") or {}
    v = vs.get(vehicle)
    kg = conversions._emissions(doc, vehicle)
    if not isinstance(v, dict):
        return {"vehicle": vehicle, "kg_per_km": kg, "fuel": "diesel", "status": "ASSUMPTION",
                "source": "the fallback figure for a vehicle not on Config", "year": None, "id": None, "basis": "fallback"}
    fuel = v.get("fuel") or "diesel"
    if fuel == "electric" and v.get("emissions_kg_co2e_per_km") is None:
        e = conversions.electricity_factors(doc)
        return {"vehicle": vehicle, "kg_per_km": kg, "fuel": "electric", "status": "DERIVED",
                "kg_per_km_wtw": conversions.electric_kg_per_km(doc, v, "wtw"),
                "kwh_per_km": _num(v.get("kwh_per_km")),
                "source": (f"{_num(v.get('kwh_per_km'))} kWh/km (ZEHID 2026, mixed fleet) × UK electricity 2026 "
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
    m = (cp.get("materials") or {}).get(name) or {}
    return {"key": f"material:{name}", "label": m.get("label") or name, "kg_co2e_per_t": m.get("kg_co2e_per_t"),
            "disposal_kg_co2e_per_t": m.get("disposal_kg_co2e_per_t"), "ids": m.get("ids"),
            "disposal_ids": m.get("disposal_ids"), "source": m.get("source"), "year": m.get("year"),
            "scope": m.get("scope"), "gwp": m.get("gwp"), "status": m.get("status"), "note": m.get("_note")}


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
        for r in self.rows(route_id):
            if r.get("profile") == profile and int(r.get("alt_index") or 0) == int(alt or 0):
                return r
        return None

    def alts(self, route_id, profile):
        return sorted({int(r.get("alt_index") or 0) for r in self.rows(route_id) if r.get("profile") == profile})


def disposal_route_of(cp, loc):
    """'landfill' / 'closed_loop' … when the location's type marks a disposal site, else None."""
    t = str((loc or {}).get("loc_type") or "").strip().lower()
    m = {str(k).strip().lower(): v for k, v in (cp.get("disposal_loc_types") or {}).items() if not str(k).startswith("_")}
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
    for lv in levers or []:
        d = lv.get("driver")
        if d not in DRIVERS:
            raise CarbonError(f"unknown driver '{d}' (one of {', '.join(DRIVERS)})")
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
            material_factor({"materials": {"x": {"kg_co2e_per_t": {"primary": 1}}}}, "x", epd=lv.get("epd"))


def _apply(state, line, levers, vs, routes, notes):
    """Apply levers (in order) to one line's state. Returns the new state."""
    s = dict(state)
    for lv in levers or []:
        if not _matches(lv.get("scope"), line):
            continue
        d = lv["driver"]
        if d == "material":
            s["epd"] = lv.get("epd") or None
            s["reused"] = bool(lv.get("reused")) and not lv.get("epd")
        elif d == "recycled":
            s["recycled_pct"] = _num(lv.get("pct")) or 0.0
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
                    notes.add(f"no electric variant of {s['vehicle']} on Config")
            else:
                tw = (vs.get(s["vehicle"]) or {}).get("geometry_twin")
                if (vs.get(s["vehicle"]) or {}).get("fuel") == "electric" and tw:
                    s["vehicle"] = tw
        elif d == "disposal":
            if lv.get("to_route"):
                to = routes.get(lv["to_route"]) or {}
                cur = routes.get(s["route_id"]) or {}
                if to.get("origin_id") != cur.get("origin_id"):
                    raise CarbonError(f"a disposal swap must keep the origin: {lv['to_route']} starts elsewhere")
                s["route_id"] = lv["to_route"]
            if lv.get("to"):
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
    payload, _fb = derived.payload_for(veh, doc)
    trips = derived._ceil(tonnes / payload) if payload > 0 and tonnes > 0 else 0
    base_baked = bool(line.get("baked"))
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
        prof = veh
        row = geo.row(s["route_id"], prof, s.get("alt_index") or 0)
        if row is None and v.get("geometry_twin"):
            prof = v["geometry_twin"]
            row = geo.row(s["route_id"], prof, s.get("alt_index") or 0)
        if row is None and int(s.get("alt_index") or 0) != 0:
            flags.append(FLAG_ALT_UNBAKED)
            row = geo.row(s["route_id"], prof, 0) or (geo.row(s["route_id"], v.get("geometry_twin"), 0)
                                                     if v.get("geometry_twin") else None)
        if row is None:
            flags.append(FLAG_KM_BORROWED)
            row = (geo.row(s["route_id"], line["vehicle_type"], 0)
                   or geo.row(line["route_id"], line["vehicle_type"], 0))
        if row is not None:
            scale = float(s.get("km_scale") or 1.0)
            if scale != 1.0:
                flags.append(FLAG_KM_SCALED)
            est = bool(row.get("return_estimated"))
            one_way = float(row.get("loaded_km") or 0.0) * scale
            ret = None if est else float(row.get("return_km") or 0.0) * scale
            if est:
                flags.append(FLAG_RETURN_ESTIMATED)
            km_trip = one_way + (ret or 0.0)
            travel_hr = (float(row.get("loaded_hr") or 0) + float(row.get("return_hr") or 0)) * scale
            cycle_hr = travel_hr + float(row.get("turnaround_hr") or 0)
            # a profile's own turnaround (an electric variant copies its twin's minutes)
            cycle_min = round(cycle_hr * 60.0, 1)
            cycles = int((plan["shift_h"] * 60.0) // cycle_min) if cycle_min and cycle_min > 0 else 0
        else:
            base_baked = False
    if not base_baked:
        flags.append(FLAG_UNBAKED)

    # ---- transport ------------------------------------------------------------------
    vf = vehicle_factor(doc, cp, veh)
    vclass = fairprice.vehicle_class(veh, doc)
    tr_t = transport_vehicle_km_t(trips, km_trip, vf["kg_per_km"]) if base_baked else None
    nh_t = transport_nh_t(one_way, tonnes, cp) if base_baked else None
    tkm_t = transport_tkm_t(one_way, tonnes, cp, vclass) if base_baked else None
    vkm = trips * km_trip if (base_baked and km_trip is not None) else None
    laden_km = trips * one_way if (base_baked and one_way is not None) else None
    electric = (v.get("fuel") == "electric")
    kwh = (vkm * float(v.get("kwh_per_km") or 0)) if (electric and vkm is not None) else 0.0

    # ---- fleet ----------------------------------------------------------------------
    ev = None
    if base_baked and cycle_min:
        if electric:
            ev = ev_day(cycle_min, km_trip, plan["shift_h"], v.get("kwh_per_km"), v.get("battery_kwh_usable"), v.get("charge_kw"))
            if not ev["feasible"]:
                flags.append(FLAG_EV_INFEASIBLE)
            cycles = ev["cycles"]
        lorries = lorries_for(trips, cycles, plan["work_days"])
    else:
        lorries = None

    # ---- material or disposal ---------------------------------------------------------
    cm = carbon_material_of(line["material_type"], doc)
    dest = (routes.get(s["route_id"]) or {}).get("dest_id") or line.get("dest_id")
    disp = s.get("disposal_to") or disposal_route_of(cp, locs.get(dest))
    mat = {"kg_per_t": None, "method": "none", "status": None}
    mat_t = dis_t = None
    dis_kg = None
    if disp:
        dis_kg = disposal_factor(cp, cm, disp) if cm else None
        dis_t = disposal_t(tonnes, dis_kg)
    else:
        rp = s.get("recycled_pct") or 0.0
        mf = material_factor(cp, cm, recycled_pct=0.0, epd=s.get("epd"), reused=s.get("reused"))
        if rp and mf.get("recycled_enabled") and not s.get("epd") and not s.get("reused"):
            mf = material_factor(cp, cm, recycled_pct=rp)
        mat = mf
        mat_t = material_t(tonnes, mf.get("kg_per_t"))

    total = (mat_t or 0.0) + (tr_t or 0.0) + (dis_t or 0.0)
    return {
        "route_id": s["route_id"], "base_route_id": line["route_id"], "month_index": line["month_index"],
        "material_type": line["material_type"], "carbon_material": cm, "sheet": sheet_of(cm),
        "vehicle": veh, "fuel": "electric" if electric else "diesel", "vehicle_class": vclass,
        "tonnes": tonnes, "trips": trips, "payload_t": payload, "baked": base_baked,
        "one_way_km": one_way, "return_km": ret, "km_trip": km_trip, "vkm": vkm, "laden_km": laden_km,
        "cycle_min": cycle_min, "cycles_per_day": cycles, "lorries": lorries, "kwh": kwh,
        "ev": ev, "kg_per_km": vf["kg_per_km"], "factor_status": vf["status"],
        "material_kg_per_t": mat.get("kg_per_t"), "material_method": mat.get("method"),
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
def _totals(evals, cp, spend_m=None, allocation=None):
    t = {"lines": len(evals), "baked_lines": 0, "tonnes": 0.0, "baked_tonnes": 0.0, "trips": 0, "electric_trips": 0,
         "vkm": 0.0, "laden_km": 0.0, "tkm": 0.0, "kwh": 0.0, "material_t": 0.0, "transport_t": 0.0,
         "transport_nh_t": 0.0, "transport_tkm_t": 0.0, "disposal_t": 0.0, "total_t": 0.0,
         "material_excluded_tonnes": 0.0, "flags": {}}
    by_cat, by_route, by_month, sheets = {}, {}, {}, []
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
        sheets.append({"id": i, "carbon_material": e["carbon_material"], "t": e["total_t"]})
    t["excludes_unbaked"] = t["baked_lines"] < t["lines"]
    peak = max(by_month.values(), key=lambda x: x["lorries"], default=None)
    t["lorries_peak"] = peak["lorries"] if peak else 0
    t["lorries_peak_month"] = peak["month_index"] if peak else None
    for r in by_route.values():
        r["vehicles"] = sorted(r["vehicles"])
    out = {
        "totals": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in t.items()},
        "by_category": sorted([{k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items()} for c in by_cat.values()],
                              key=lambda x: -x["total_t"]),
        "by_route": sorted([{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in by_route.values()],
                           key=lambda x: -x["total_t"]),
        "by_month": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in by_month[k2].items()} for k2 in sorted(by_month)],
        "sheets": {k: round(v, 3) for k, v in split_sheets(sheets).items()},
        "benchmarks": benchmarks(t, evals, cp, spend_m),
    }
    if allocation:
        alloc = {k: 0.0 for k in ALLOCATION + (NOT_ALLOCATED,)}
        for c in by_cat.values():
            for k, x in allocate(c["total_t"], allocation.get(c["category"]) or {}).items():
                alloc[k] += x
        out["allocation"] = {k: round(v, 3) for k, v in alloc.items()}
    return out


def benchmarks(t, evals, cp, spend_m=None):
    """
    The figures the brief names, each against a published reference — never against an invented
    limit (no 'per delivery' limit exists in any rule): kg CO2e per tonne delivered; kg CO2e per
    tonne-km against the DESNZ 2026 average-laden tonne-km figure for the same classes; the laden
    share; the share of zero-emission deliveries (NH: all HGVs delivering to its sites electric or
    hydrogen by 2040); tCO2e per £m where spend is typed (NH's own KPI 210 → 148 t/£m).
    """
    bt = t["baked_tonnes"]
    tkm = t["tkm"]
    ref_num = sum((e["tonnes"] * (e["one_way_km"] or 0.0)) * (tkm_factor(cp, e["vehicle_class"]) or 0.0)
                  for e in evals if e["baked"])
    ref = (ref_num / tkm) if tkm > 0 else None
    kg_tkm = (t["transport_t"] * 1000.0 / tkm) if tkm > 0 else None
    kpi = ((cp.get("benchmarks") or {}).get("nh_kpi_t_co2e_per_gbp_m")) or {}
    spend = _num(spend_m)
    return {
        "kg_co2e_per_t_delivered": round(t["transport_t"] * 1000.0 / bt, 3) if bt > 0 else None,
        "kg_co2e_per_t_all_in": round(t["total_t"] * 1000.0 / t["tonnes"], 3) if t["tonnes"] > 0 else None,
        "kg_co2e_per_tkm": round(kg_tkm, 5) if kg_tkm is not None else None,
        "desnz_kg_co2e_per_tkm": round(ref, 5) if ref is not None else None,
        "vs_national_average_pct": (round((kg_tkm / ref - 1.0) * 100.0, 1) if (kg_tkm is not None and ref) else None),
        "laden_share_pct": round(t["laden_km"] * 100.0 / t["vkm"], 1) if t["vkm"] > 0 else None,
        "zero_emission_share_pct": round(t["electric_trips"] * 100.0 / t["trips"], 1) if t["trips"] > 0 else None,
        "t_co2e_per_gbp_m": round(t["total_t"] / spend, 2) if spend and spend > 0 else None,
        "nh_kpi_t_co2e_per_gbp_m": kpi,
        "nh_target": (cp.get("benchmarks") or {}).get("nh_target"),
    }


# =========================================================================== #
#  The scenario                                                                 #
# =========================================================================== #
def scenario(acc=None, alternatives=None, baseline_levers=None, from_month=None, to_month=None,
             status="Approved", spend_m=None, allocation=None, factors=None):
    """
    The baseline (the caller's visible forecast lines, as approved, with Government primary
    material factors and the forecast vehicles — adjusted by `baseline_levers`) and each
    alternative (`[{name, levers: [...]}]`). Per alternative: its totals, the delta, and the
    per-driver deltas RANKED by tCO2e moved — each driver's levers applied alone to the
    baseline — plus the interaction (combined minus the sum of the singles). Raises CarbonError.
    """
    acc = acc if acc is not None else access.current()
    factors = factors if factors is not None else conversions.load_factors()
    cp = params(factors)
    vs = vehicles(factors)
    doc = _doc(factors, vs, cp)
    routes = _routes()
    locs = _locations()
    plan = factors.get("planning", {}) or {}
    ctx = {"cp": cp, "doc": doc, "vs": vs, "geo": _Geo(), "locs": locs, "routes": routes,
           "plan": {"shift_h": float(plan.get("shift_hours_per_day") or 10),
                    "work_days": float(plan.get("working_days_per_month") or 22)}}
    if allocation:
        for cat, pcts in allocation.items():
            allocate(1.0, pcts)                                  # refuses over 100 % up front
    _check_levers(baseline_levers, vs, routes)
    alts = list(alternatives or [])
    for a in alts:
        _check_levers(a.get("levers"), vs, routes)

    cl = costlines.lines(acc, from_month=from_month, to_month=to_month, status=status, factors=factors)
    lines = cl["lines"]
    notes = set()
    states0 = [_apply(_state0(l), l, baseline_levers, vs, routes, notes) for l in lines]
    base_eval = [_eval(l, s, ctx) for l, s in zip(lines, states0)]
    base = _totals(base_eval, cp, spend_m, allocation)
    bt = base["totals"]["total_t"]

    out_alts = []
    for a in alts:
        lv = a.get("levers") or []
        a_notes = set()
        ev = [_eval(l, _apply(s, l, lv, vs, routes, a_notes), ctx) for l, s in zip(lines, states0)]
        tot = _totals(ev, cp, spend_m, allocation)
        drivers, singles = [], 0.0
        for d in DRIVERS:
            dl = [x for x in lv if x.get("driver") == d]
            if not dl:
                continue
            de = [_eval(l, _apply(s, l, dl, vs, routes, set()), ctx) for l, s in zip(lines, states0)]
            dt = sum(e["total_t"] for e in de) - sum(e["total_t"] for e in base_eval)
            changed = sum(1 for e0, e1 in zip(base_eval, de) if abs(e1["total_t"] - e0["total_t"]) > 1e-9)
            singles += dt
            drivers.append({"driver": d, "label": DRIVER_LABELS[d], "delta_t": round(dt, 3),
                            "delta_pct": round(dt * 100.0 / bt, 1) if bt else None, "lines_changed": changed})
        drivers.sort(key=lambda x: -abs(x["delta_t"]))
        delta = tot["totals"]["total_t"] - bt
        out_alts.append(dict(tot, name=str(a.get("name") or "Alternative"), levers=lv,
                             delta_t=round(delta, 3), delta_pct=(round(delta * 100.0 / bt, 1) if bt else None),
                             drivers=drivers, interaction_t=round(delta - singles, 3), notes=sorted(a_notes),
                             fleet=_fleet_summary(ev)))

    return {
        "baseline": dict(base, fleet=_fleet_summary(base_eval), notes=sorted(notes)),
        "alternatives": out_alts,
        "fleet_compare": fleet_compare(lines, states0, ctx),
        "options": options(lines, ctx, factors),
        "factors": provenance(base_eval, ctx),
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
            "tonne_km": "DESNZ 2026 class tonne-km, average laden — what a tonne-km calculator gives for the same haul",
        },
    }


def _line_out(e):
    keep = ("route_id", "month_index", "material_type", "carbon_material", "sheet", "vehicle", "fuel", "tonnes",
            "trips", "baked", "one_way_km", "km_trip", "material_t", "transport_t", "transport_nh_t",
            "disposal_route", "disposal_t", "total_t", "flags", "ipt")
    return {k: (round(e[k], 3) if isinstance(e[k], float) else e[k]) for k in keep}


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
    trips, kWh, tCO2e, and the electric day: payload, range, charges, minutes per charge.
    """
    vs = ctx["vs"]
    sel = [(l, s) for l, s in zip(lines, states0) if l.get("baked") and electric_variant(vs, s["vehicle"])]
    if not sel:
        return {"lines": 0, "diesel": None, "electric": None, "note": "no forecast vehicle on a baked route has an electric variant"}
    d_ev = [_eval(l, s, ctx) for l, s in sel]
    e_ev = [_eval(l, dict(s, vehicle=electric_variant(vs, s["vehicle"])), ctx) for l, s in sel]
    d, e = _fleet_summary(d_ev), _fleet_summary(e_ev)
    days = [x["ev"] for x in e_ev if x.get("ev")]
    evs = sorted({x["vehicle"] for x in e_ev})
    return {
        "lines": len(sel), "tonnes": round(sum(x["tonnes"] for x in d_ev), 3),
        "diesel": d, "electric": e,
        "electric_profiles": [{"vehicle": k, "payload_t": _num(vs[k].get("payload_t")), "kwh_per_km": _num(vs[k].get("kwh_per_km")),
                               "battery_kwh_usable": _num(vs[k].get("battery_kwh_usable")), "charge_kw": _num(vs[k].get("charge_kw")),
                               "twin": vs[k].get("geometry_twin"),
                               "twin_payload_t": _num((vs.get(vs[k].get("geometry_twin")) or {}).get("payload_t"))} for k in evs],
        "charges_per_lorry_day_max": max((x["charges"] for x in days), default=0),
        "minutes_per_charge_max": (round(max((x["minutes_per_charge"] or 0) for x in days), 1) if days else None),
        "daily_range_km_min": (round(min(x["daily_range_km"] for x in days if x["daily_range_km"]), 1)
                               if any(x["daily_range_km"] for x in days) else None),
        "infeasible_lines": sum(1 for x in days if not x["feasible"]),
        "delta_t": round(e["transport_t"] - d["transport_t"], 3),
    }


def options(lines, ctx, factors):
    """What the page's controls may offer: the categories in view with their material options, the
    vehicles per category (and their electric variants), and per route the baked alternatives,
    the other suppliers to the same destination, and the other destinations from the same origin."""
    cp, vs, geo, routes, locs = ctx["cp"], ctx["vs"], ctx["geo"], ctx["routes"], ctx["locs"]
    hidden = set(conversions.hidden_vehicle_names(factors))
    cats = {}
    for l in lines:
        c = cats.setdefault(l["material_type"], {"category": l["material_type"], "tonnes": 0.0})
        c["tonnes"] += float(l.get("tonnes") or 0)
    mats = []
    for name, c in cats.items():
        cm = carbon_material_of(name, factors)
        mf = material_factor(cp, cm) if cm else material_factor(cp, None)
        listed = [v for v in (((factors.get("material_categories") or {}).get(name) or {}).get("vehicles") or [])
                  if v in vs and v not in hidden]
        listed += [electric_variant(vs, v) for v in listed if electric_variant(vs, v)]
        mats.append(dict(c, tonnes=round(c["tonnes"], 3), carbon_material=cm, sheet=sheet_of(cm),
                         label=mf.get("label"), primary=mf.get("primary"), closed_loop=mf.get("closed_loop"),
                         reused=mf.get("reused"), recycled_enabled=mf.get("recycled_enabled"),
                         recycled_reason=mf.get("recycled_reason"), vehicles=listed))
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
        rts.append({
            "route_id": rid, "origin_id": r.get("origin_id"), "dest_id": r.get("dest_id"),
            "origin_name": (locs.get(r.get("origin_id")) or {}).get("name"),
            "dest_name": (locs.get(r.get("dest_id")) or {}).get("name"),
            "material_category": r.get("material_category"),
            "disposal_route": disposal_route_of(cp, locs.get(r.get("dest_id"))),
            "alts": {v: geo.alts(rid, v) for v in vehs},
            "suppliers": sorted(k for k, x in routes.items() if k != rid and x.get("dest_id") == r.get("dest_id")
                                and (x.get("material_category") or "") == (r.get("material_category") or "")),
            "destinations": sorted(k for k, x in routes.items() if k != rid and x.get("origin_id") == r.get("origin_id")
                                   and (x.get("material_category") or "") == (r.get("material_category") or "")),
        })
    return {"materials": mats, "vehicles": veh, "routes": rts, "drivers": DRIVER_LABELS,
            "allocation": list(ALLOCATION), "disposal_routes": list(DISPOSAL_ROUTES)}


def provenance(evals, ctx):
    """Every factor a figure on the page used: value, unit, source, year, status (VERIFIED /
    DERIVED / ASSUMPTION), the gov.uk row ID and the GWP basis — for the page's hover text."""
    cp, doc = ctx["cp"], ctx["doc"]
    out = []
    for name in sorted({e["carbon_material"] for e in evals if e["carbon_material"]}):
        out.append(_prov_material(cp, name))
    for vname in sorted({e["vehicle"] for e in evals}
                        | {electric_variant(ctx["vs"], e["vehicle"]) for e in evals if electric_variant(ctx["vs"], e["vehicle"])}):
        out.append(dict(vehicle_factor(doc, cp, vname), key=f"vehicle:{vname}", label=vname, unit="kg CO2e per vehicle-km"))
    el = cp.get("electricity") or {}
    out.append({"key": "electricity", "label": "UK electricity, generation + T&D", "unit": "kg CO2e per kWh",
                "value": round(float(el.get("generation_kg_co2e_per_kwh") or 0) + float(el.get("td_kg_co2e_per_kwh") or 0), 5),
                "value_wtw": round(sum(float(el.get(k) or 0) for k in ("generation_kg_co2e_per_kwh", "td_kg_co2e_per_kwh",
                                                                         "wtt_generation_kg_co2e_per_kwh", "wtt_td_kg_co2e_per_kwh")), 5),
                "ids": [el.get("generation_id"), el.get("td_id"), el.get("wtt_generation_id"), el.get("wtt_td_id")],
                "source": el.get("source"), "year": el.get("year"), "status": el.get("status"), "gwp": el.get("gwp")})
    eh = cp.get("electric_hgv") or {}
    out.append({"key": "kwh_per_km", "label": "Electric lorry energy use", "unit": "kWh per km",
                "value": eh.get("kwh_per_km_default"), "source": eh.get("kwh_per_km_source"), "year": 2026,
                "status": eh.get("kwh_per_km_status") or "DERIVED"})
    out.append({"key": "ev_payload", "label": "Electric payload penalty", "unit": "t",
                "value": eh.get("payload_penalty_range_t"), "source": "ZEHID annual report 2026", "year": 2026,
                "status": "ASSUMPTION"})
    out.append({"key": "zev_allowance", "label": "Zero-emission HGV weight allowance", "unit": "t",
                "value": eh.get("zev_gvw_allowance_t"), "source": eh.get("zev_allowance_status"), "year": 2026,
                "status": "ASSUMPTION"})
    tk = ((cp.get("transport") or {}).get("tonne_km_2026")) or {}
    for cls in ("rigid", "artic"):
        r = tk.get(cls) or {}
        out.append({"key": f"tkm:{cls}", "label": f"DESNZ 2026 tonne-km, {cls}", "unit": "kg CO2e per tonne-km",
                    "value": r.get("kg_co2e_per_tkm"), "ids": [r.get("id")], "source": tk.get("source"),
                    "year": tk.get("year"), "status": tk.get("status"), "gwp": tk.get("gwp"), "note": r.get("row")})
    nh = ((cp.get("transport") or {}).get("nh_carbon_tool_v27")) or {}
    out.append({"key": "nh_tool", "label": "NH Carbon Tool v2.7 transport basis", "unit": "t CO2e per tonne per one-way km",
                "value": nh_tool_t_per_t_km(cp), "source": nh.get("source"), "year": nh.get("year"),
                "status": nh.get("status"), "note": nh.get("basis"), "formula": nh.get("formula")})
    return out
