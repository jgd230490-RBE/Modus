"""
Unit conversion engine for logistics forecasting.

Everything pivots through TONNES:
    m3       -> tonnes  via material density
    tonnes   -> tonnes  (identity)
    vehicles -> tonnes  via vehicle payload

...and back out to whichever unit the caller wants. All the tunable numbers
live in factors.json so an engineer can adjust them without touching code.
"""
import json
import os
import sys

UNITS = ["m3", "t", "vehicles"]
_FACTORS_PATH = os.path.join(os.path.dirname(__file__), "factors.json")


def load_factors():
    """
    The live factors document.

    2.5b: the `config` table's `factors` row when it exists, else backend/factors.json.
    The file is the SEED a fresh database starts from; once the row exists, editing the
    file changes nothing until "Reset to file" is pressed on the Config page. See
    config.py. A missing table, a missing row or a corrupt row all fall back to the
    file, so nothing that reads factors can be taken down by the config layer.
    """
    try:
        import config
        return config.load(sys.modules[__name__])
    except Exception:
        with open(_FACTORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def load_factors_file():
    """The file, always. For seeding, resetting, and the diff on the Config page."""
    with open(_FACTORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_FILE_CACHE = {"mtime": None, "doc": None}


def load_factors_file_cached():
    """The file, parsed once and kept until it changes on disk. READ ONLY — the carbon planner's
    fallbacks read it per request; a caller that wants to edit takes load_factors_file()."""
    mt = os.path.getmtime(_FACTORS_PATH)
    if _FILE_CACHE["doc"] is None or _FILE_CACHE["mtime"] != mt:
        _FILE_CACHE["doc"], _FILE_CACHE["mtime"] = load_factors_file(), mt
    return _FILE_CACHE["doc"]


def _density(factors, material):
    cats = factors.get("material_categories", {})
    c = cats.get(material) or cats.get("_default", {})
    return float(c.get("density_t_per_m3", 1.6))


def _payload(factors, vehicle):
    vs = factors.get("vehicles", {})
    v = vs.get(vehicle) or vs.get("_default", {})
    return float(v.get("payload_t", 20))


#: 12 Oct 2026 (B2, the carbon fallbacks): the ONE figure a per-km factor falls to when the
#: document gives none — a vehicle name it does not carry and no `_default` entry to catch it,
#: or a stored figure that is null or blank. The UK Government (DESNZ) 2026 GHG conversion
#: factors' published AVERAGE for non-refrigerated diesel HGVs, average laden, kg CO2e per
#: vehicle-km, flat file v1.2 (notes/carbon-check-1009.md §2, §6). It replaced the 0.90
#: literals here and on the map that no published row ever said; the seed's `_default` entry
#: carries the same figure, so a document with or without that entry resolves alike.
#: conversions._emissions() is the only reader: network.route_analysis, costlines and the
#: flat factors /api/meta serves all go through it, so no two screens can disagree.
FALLBACK_KG_CO2E_PER_KM = 0.89743


def _stored_factor(v):
    """The per-km figure an entry carries as a number, else None: null, a blank string, a
    word or a bool all read as 'no figure' (a blank cell saved on Config is None here)."""
    x = (v or {}).get("emissions_kg_co2e_per_km") if isinstance(v, dict) else None
    if x is None or isinstance(x, bool) or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _emissions(factors, vehicle):
    """
    kg CO2e per vehicle-km for a vehicle: its stored figure (the DESNZ 2026 diesel factors,
    tank-to-wheel). 10 Oct 2026 (carbon planner): an entry with fuel "electric" and no stored
    figure is DERIVED here, once — kwh_per_km × the UK electricity factor (generation + T&D)
    from the `carbon` block — because the Government 2026 set publishes no electric HGV factor.
    A stored figure on an electric entry (a fleet's measured one) wins.

    12 Oct 2026 (B2): ONE fallback rule, the same for every caller — the vehicle's own figure;
    an electric entry's derived figure; else the document's `_default` figure; else
    FALLBACK_KG_CO2E_PER_KM. A stored 0 is a figure (a vehicle with no tailpipe carbon), not a
    gap — route_analysis used to send 0 to `_default` while this returned 0, so the Routes
    table and the Dashboard disagreed. A null or blank stored figure (the blank Config cell
    that used to make float(None) raise here and blank every carbon figure on the map) now
    falls through like a missing one; config.validate refuses it at save time.
    """
    vs = (factors or {}).get("vehicles", {}) or {}
    v = vs.get(vehicle)
    if not isinstance(v, dict):
        v = vs.get("_default") if isinstance(vs.get("_default"), dict) else {}
    stored = _stored_factor(v)
    if stored is not None:
        return stored
    if v.get("fuel") == "electric":
        return electric_kg_per_km(factors, v)
    dflt = _stored_factor(vs.get("_default"))
    return dflt if dflt is not None else FALLBACK_KG_CO2E_PER_KM


def electricity_factors(factors=None):
    """The `carbon.electricity` block: the file's, with every key the live document carries laid
    over it (a tenant seeded before 10 Oct 2026 has no carbon block until Reset to file or a
    re-import). Key by key — the same rule carbon.params() uses — so the map, the Dashboard and
    the Carbon page always read one electric figure."""
    try:
        seed = (load_factors_file_cached().get("carbon") or {}).get("electricity") or {}
    except Exception:
        seed = {}
    live = ((factors or {}).get("carbon") or {}).get("electricity") if isinstance(factors, dict) else None
    out = dict(seed) if isinstance(seed, dict) else {}
    if isinstance(live, dict):
        out.update(live)
    return out


def electric_kg_per_km(factors, v, basis="ttw"):
    """kg CO2e per km for an electric entry: kWh/km × (generation + T&D) — the tank-to-wheel
    equivalent beside the diesel figures; basis "wtw" adds the two well-to-tank rows."""
    e = electricity_factors(factors)
    kwh = float((v or {}).get("kwh_per_km") or ((factors or {}).get("carbon") or {}).get("electric_hgv", {}).get("kwh_per_km_default") or 1.25)
    per_kwh = float(e.get("generation_kg_co2e_per_kwh") or 0) + float(e.get("td_kg_co2e_per_kwh") or 0)
    if basis == "wtw":
        per_kwh += float(e.get("wtt_generation_kg_co2e_per_kwh") or 0) + float(e.get("wtt_td_kg_co2e_per_kwh") or 0)
    return kwh * per_kwh


def material_names(factors):
    return [k for k in factors.get("material_categories", {}) if not k.startswith("_")]


def vehicle_names(factors):
    return [k for k in factors.get("vehicles", {}) if not k.startswith("_")]


def planning_vehicle_names(factors, country=None):
    """
    The vehicles that LEAD every picker, in order: the country's `vehicle_sets[..].lead`
    when the tenant's country has one (H1: GB's UK trade names), else the document's own
    planning vehicles in the order its top-level `planning_vehicles` lists them (the seed:
    the six UK haulage trade names, Rigid 8-wheeler first, since 11 Oct 2026). The FIRST
    name is also the payload fallback (derived.payload_for).

    Two sources on purpose, and they have to agree: the top-level `planning_vehicles`
    array carries the ORDER, and `planning_vehicle: true` on the entry itself is the
    FLAG. A name in the array that is not a real vehicle key is DROPPED rather than
    returned — it would otherwise reach a picker as an option that silently resolves to
    _default (20 t, 0.89743 kg/km — FALLBACK_KG_CO2E_PER_KM), which is the failure
    factors_diagnostics() exists to catch. An entry that is flagged but missing from the array is appended, so flagging
    another vehicle is one edit and forgetting the array is visible, not silent.

    11 Oct 2026 (the EU type-approval vehicles removed): NEVER an empty list while the
    document has a vehicle a tenant can pick. Until then the seed's array named the four
    EU entries, so the empty case never came from the seed; emptied, it would have left
    every tenant without a vehicle set with no lead group and no named payload fallback.
    Now, when the array and the flags give nothing (a document without them, or every
    Planning tick taken off on Config), the lead list is the vehicles the material
    categories list, in the
    order they first appear (category by category, as factors.json orders them) — the
    vehicles a tenant actually uses, and for the seed that puts Rigid 8-wheeler (32t)
    first, the same first name the array gives. Not the file's vehicle order: that starts
    with Rigid 7.5t (3.5 t), which would then become the payload every unknown vehicle
    converts on. Hidden (the country's `hide`) and scenario-only (electric) profiles are
    never in it — a picker does not offer them. Only when no category lists a usable
    vehicle does it fall back to every usable vehicle in file order.
    """
    vs = factors.get("vehicles", {}) or {}
    known = [k for k in vs if not k.startswith("_")]
    # H1 (29 Sep 2026): a country with its own `vehicle_sets` entry leads with THAT list
    # (GB: the UK trade names) and never with the names it hides.
    cs = _country_set(factors, country)
    if cs and cs.get("lead"):
        return [n for n in cs["lead"] if n in known]
    out = [n for n in (factors.get("planning_vehicles") or []) if n in known]
    for k in known:
        if k not in out and (vs.get(k) or {}).get("planning_vehicle"):
            out.append(k)
    if out:
        return out
    # 11 Oct 2026: the never-empty fallback described above
    hidden = set(hidden_vehicle_names(factors, country))
    usable = [k for k in known if k not in hidden and not (vs.get(k) or {}).get("scenario_only")]
    for cat, c in (factors.get("material_categories") or {}).items():
        if cat.startswith("_") or not isinstance(c, dict):
            continue
        for n in c.get("vehicles") or []:
            if n in usable and n not in out:
                out.append(n)
    return out or usable


def _tenant_country_of(factors):
    """The tenant's country from the factors document's own tenant block (no DB read)."""
    t = factors.get("tenant") if isinstance(factors, dict) else None
    c = (t or {}).get("country") if isinstance(t, dict) else None
    return str(c).strip().upper() if isinstance(c, str) and c.strip() else None


def _country_set(factors, country=None):
    """The `vehicle_sets` entry for a country (default: the document's own tenant country)."""
    c = (str(country).strip().upper() if country else None) or _tenant_country_of(factors)
    sets = factors.get("vehicle_sets") if isinstance(factors, dict) else None
    if not c or not isinstance(sets, dict):
        return None
    cs = sets.get(c)
    return cs if isinstance(cs, dict) else None


def hidden_vehicle_names(factors, country=None):
    """
    H1: the vehicle names the PICKERS do not offer this tenant (its country's `hide`
    list). They stay in `vehicles` and resolve everywhere else — an existing line or a
    baked route on one of them keeps its payload, CO2 and geometry. Never renamed,
    never removed (the validator refuses deleting a baked profile).
    """
    vs = factors.get("vehicles", {}) or {}
    cs = _country_set(factors, country)
    if not cs:
        return []
    return [n for n in (cs.get("hide") or []) if n in vs]


# The label slots a factors document can carry, in the order the header lists them. "en" is
# the one every vehicle in the seed carries. 11 Oct 2026 (the EU type-approval vehicles
# removed from the seed): "eu" and "ee" stay READABLE here because a document saved before
# then (the live demo's Config row, an older tenant package) still carries labels.eu on
# those four entries, and its strings must keep resolving. Whether a slot is OFFERED is
# decided per document — `langs` in vehicle_labels() — not by this tuple.
VEHICLE_LANGS = ("en", "eu", "ee")


def offered_vehicle_langs(factors, country=None):
    """
    The label languages the app OFFERS this tenant (the header's vehicle-name buttons):
    "en" always, then every other slot of VEHICLE_LANGS that at least one vehicle the
    tenant is offered — not in its country's `hide` list — carries a non-blank label in.

    11 Oct 2026. Until then all three were always sent and the client gated them by
    country. A language nobody's vehicle uses is now not offered at all: the seed's
    vehicles carry English only, so a new organisation gets English alone and no buttons.
    A document that still carries the EU entries keeps "eu" for a tenant that is offered
    them (no country set, say); GB hides them, so GB gets English alone, as before.
    """
    vs = factors.get("vehicles", {}) or {}
    hidden = set(hidden_vehicle_names(factors, country))
    used = set()
    for k, v in vs.items():
        if k.startswith("_") or k in hidden:
            continue
        lab = (v or {}).get("labels") or {}
        for lang in VEHICLE_LANGS:
            if isinstance(lab.get(lang), str) and lab[lang].strip():
                used.add(lang)
    return ["en"] + [l for l in VEHICLE_LANGS if l != "en" and l in used]


def vehicle_labels(factors, country=None):
    """
    {"labels": {vehicle_key: {lang: text}}, "fallbacks": {vehicle_key: [lang]}, "langs": [...]}.

    `langs` is offered_vehicle_langs() — the languages the app offers this tenant, English
    always (11 Oct 2026: no longer every slot the code can read). Every vehicle carries
    every OFFERED slot, filled; a missing label falls back to the KEY — never to another
    language and never to an invented trade name (the 2026-09-02 feedback is explicit:
    rather than invent, show the id). The key is the canonical id a forecast line stores;
    a label only changes what a picker shows. `fallbacks` says which slots were filled
    that way, so a UI can mark them rather than pass a fallback off as a translation.
    """
    langs = offered_vehicle_langs(factors, country)
    out, fallbacks = {}, {}
    for k, v in (factors.get("vehicles", {}) or {}).items():
        if k.startswith("_"):
            continue
        lab = (v or {}).get("labels") or {}
        out[k] = {}
        for lang in langs:
            val = (lab.get(lang) or "").strip() if isinstance(lab.get(lang), str) else ""
            if val:
                out[k][lang] = val
            else:
                out[k][lang] = k
                fallbacks.setdefault(k, []).append(lang)
    return {"labels": out, "fallbacks": fallbacks, "langs": langs}


def flat_factors(factors):
    """
    Backward-compatible flat maps for clients that read the old shape
    (the map and the dashboard read factors.vehicle_payload_t etc.).
    Derived from the rich taxonomy so there is still one source of truth.
    """
    cats = factors.get("material_categories", {})
    vs = factors.get("vehicles", {})
    density = {k: v.get("density_t_per_m3", 1.6) for k, v in cats.items()}
    density.setdefault("_default", 1.6)
    payload = {k: v.get("payload_t", 20) for k, v in vs.items()}
    payload.setdefault("_default", 20)
    # 10 Oct 2026: through _emissions(), so an electric entry carries its derived figure here
    # too (the map and the Dashboard read this map). 12 Oct 2026 (B2): EVERY entry through it,
    # so a null or blank stored figure reaches the map as the resolved fallback, never as null,
    # and `_default` is the document's figure or FALLBACK_KG_CO2E_PER_KM — the one rule.
    emis = {k: _emissions(factors, k) for k, v in vs.items() if isinstance(v, dict)}
    emis.setdefault("_default", FALLBACK_KG_CO2E_PER_KM)
    return {
        "material_density_t_per_m3": density,
        "vehicle_payload_t": payload,
        "vehicle_emissions_kg_co2e_per_km": emis,
        "planning": factors.get("planning", {}),
    }


def to_tonnes(quantity, unit, material, vehicle, factors=None):
    factors = factors or load_factors()
    q = float(quantity)
    if unit == "t":
        return q
    if unit == "m3":
        return q * _density(factors, material)
    if unit == "vehicles":
        return q * _payload(factors, vehicle)
    raise ValueError(f"Unknown unit: {unit}")


def from_tonnes(tonnes, unit, material, vehicle, factors=None):
    factors = factors or load_factors()
    t = float(tonnes)
    if unit == "t":
        return t
    if unit == "m3":
        return t / _density(factors, material)
    if unit == "vehicles":
        return t / _payload(factors, vehicle)
    raise ValueError(f"Unknown unit: {unit}")


def convert(quantity, from_unit, to_unit, material, vehicle, factors=None):
    """Convert a quantity from one unit to another for a given material/vehicle."""
    factors = factors or load_factors()
    tonnes = to_tonnes(quantity, from_unit, material, vehicle, factors)
    return from_tonnes(tonnes, to_unit, material, vehicle, factors)


def effective_payload(factors, v1, v2=None, split_pct=100):
    """
    DEPRECATED in Phase 2 — kept only so an older caller does not crash.

    A load split across two vehicle types is now TWO forecast lines, one vehicle each,
    which the widened forecasts key makes storable. Blending two payloads into one number
    also blended their haul cycles, and those are not close: an Artic Flatbed turns round
    in 45 minutes against an Artic Tipper's 24. Two lines keep each cycle honest.

    With v2 omitted this is just v1's payload, which is all any current caller passes.
    """
    p1 = _payload(factors, v1)
    if not v2 or split_pct is None or split_pct >= 100:
        return p1
    p2 = _payload(factors, v2)
    s = max(0, min(100, int(split_pct))) / 100.0
    inv = s / p1 + (1 - s) / p2
    return (1.0 / inv) if inv > 0 else p1


def convert_row(row, to_unit, factors=None):
    """
    Convert one stored forecast row to the requested unit.

    One vehicle per row since Phase 2 — a split is two rows, so there is no blend here
    any more. Falls back through effective_payload() only if a legacy row still carries
    vehicle_type_2, which the rebuilt table cannot produce.
    """
    factors = factors or load_factors()
    material = row.get("material_type")
    tonnes = to_tonnes(row["quantity"], row["unit"], material, row.get("vehicle_type"), factors)
    if to_unit == "t":
        return tonnes
    if to_unit == "m3":
        return tonnes / _density(factors, material)
    if to_unit == "vehicles":
        ep = effective_payload(factors, row.get("vehicle_type"),
                               row.get("vehicle_type_2"), row.get("split_pct", 100))
        return tonnes / ep
    raise ValueError(f"Unknown unit: {to_unit}")


def round_for_unit(value, unit):
    """Vehicles are whole; volumes/weights get one decimal."""
    if unit == "vehicles":
        return int(round(value))
    return round(float(value), 1)
