"""
2.5b, 2026-09-03 — the editable copy of factors.json.

WHAT CHANGED AND WHY IT MATTERS
-------------------------------
Until now `backend/factors.json` was the single source of truth for materials, vehicles
and planning constants, and editing it meant a commit and a redeploy. The Config page
needs those numbers editable in the app, and Render's filesystem does not persist, so
the document now lives in the `config` table (key `factors`) and the file is the SEED.

    conversions.load_factors()  -> the config row if there is one, else the file

⚠️ Consequence: once the row exists, EDITING factors.json DOES NOTHING until somebody
presses "Reset to file" on the Config page (or the row is deleted). The file is where
a fresh database starts, not where the live numbers live. The Config page says so.

VALIDATION
----------
A bad document here would silently change every payload, density and cycle time in the
system, so a write is refused unless it passes validate(). The checks are structural
and physical (a payload must be a positive number; a vehicle the network is baked for
must still exist; the planning vehicles must exist) — they are not a judgement about
whether 18 t is the right payload. That stays with the person editing.
"""
import datetime
import json
import math
import os
import re

import db

# The Mapbox PUBLIC token (pk.…). Public by design — it is in every browser's
# view-source — and read from MAPBOX_TOKEN on Render when set. ONE place for it since
# 10 Sep: the browser map, the Commit week map and the PDF's static map all use
# mapbox_token(); the PDF used to read only the env var and fell back to a schematic
# on Render, where the env var was never set.
# H1 (29 Sep 2026): the value below is the token rotated on 25 Sep — the SAME one
# map/config.js carries (test_h1_uk.py asserts the two are equal). The pre-rotation
# token that sat here until H1 is revoked and gone.
MAPBOX_TOKEN_DEFAULT = ("pk.eyJ1IjoiamdkMjMwNDE5OTAiLCJhIjoiY211aDB1YTJtMHF3YzJ4cnpodTlsb2czOSJ9"
                        ".B1oY8QnGB2YRBz0rV1klfg")


def mapbox_token():
    return (os.getenv("MAPBOX_TOKEN") or "").strip() or MAPBOX_TOKEN_DEFAULT


KEY = "factors"

# --------------------------------------------------------------------------- #
#  Tenant settings — G2, 2026-09-16                                            #
# --------------------------------------------------------------------------- #
# The words and units a tenant sees. Kept INSIDE the factors document (key
# `tenant`) so it travels with the config row, is edited on the Config page, and
# is exported in the tenant package like everything else. Defaults apply when a
# document predates the block — a live row seeded before 16 Sep has none.
#
#   name         the project's own name, shown in the header and on exports
#   team_label   the word for a delivery team ("Team", "IPT", "Package", "JV partner").
#                LABEL ONLY: the `ipt` column, the roles and the env vars keep their
#                names — see claude/gtm-0916.md, decision 2.
#   currency     ISO code; symbol and formatting only, no conversion. Every stored
#                figure stays in the tenant's own currency.
#   distance_unit "km" (default) or "mi" — H1. What the tenant READS; km is what is stored.
#   country      ISO-3166 alpha-2, or null. Chooses the providers that are country-
#                specific: the road-restriction layer (EE: Tark Tee; GB: National
#                Highways planned closures — H1), the diesel index auto-fetch (EU-27:
#                the Weekly Oil Bulletin; GB: DESNZ — H1), the orthophoto basemap (EE).
#                Null = none of them; the diesel index is then typed only.
TENANT_DEFAULTS = {"name": "Wayscope", "team_label": "Team", "currency": "EUR", "country": None,
                   "distance_unit": "km",     # H1: km stored always; "mi" = read in miles
                   # H2 (5 Oct 2026): a short notice every screen and export carries when set —
                   # the demo tenant says "Fictional demo scheme · nothing here is real". A real
                   # tenant leaves it null and nothing is shown. Validated as text or null.
                   "demo_notice": None,
                   # 12 Oct 2026 (map review 2.1 / 2.3): the address the public map's "Report a concern" link
                   # writes to. TYPED by the tenant, never invented: null (the demo) and the map says that no
                   # contact address has been typed. Validated as one plain email address or null.
                   "concern_email": None}

CURRENCIES = {
    "EUR": {"symbol": "€", "name": "euro"},
    "GBP": {"symbol": "£", "name": "pound sterling"},
    "SEK": {"symbol": "kr", "name": "Swedish krona"},
    "NOK": {"symbol": "kr", "name": "Norwegian krone"},
    "DKK": {"symbol": "kr", "name": "Danish krone"},
    "PLN": {"symbol": "zł", "name": "Polish złoty"},
    "CHF": {"symbol": "CHF", "name": "Swiss franc"},
    "USD": {"symbol": "$", "name": "US dollar"},
}


# Which countries have a road-restriction provider wired in restrictions.py (EE: Tark
# Tee; GB: National Highways planned closures — H1). Read from that module so the two
# cannot drift; the literal fallback is for a partial import in a stubbed harness.
try:
    from restrictions import PROVIDERS as _RX_PROVIDERS
    RESTRICTION_PROVIDERS = set(_RX_PROVIDERS)
except Exception:                                   # pragma: no cover
    RESTRICTION_PROVIDERS = {"EE", "GB"}

# H1: which distance unit the tenant READS. Everything is stored in km; "mi" converts on
# display and on the exports only. Per tenant (HU5, decided 29 Sep) until G3 exists.
DISTANCE_UNITS = ("km", "mi")
# 10 Oct 2026, carbon planner: what a vehicle runs on. Absent = diesel (every entry before 10 Oct).
FUELS = ("diesel", "electric")
KM_PER_MILE = 1.609344


def tenant_settings(conversions=None, doc=None):
    """The tenant block with defaults applied, plus the derived currency symbol."""
    if doc is None:
        doc = load(conversions) if conversions is not None else {}
    t = dict(TENANT_DEFAULTS)
    block = doc.get("tenant") if isinstance(doc, dict) else None
    if isinstance(block, dict):
        for k in TENANT_DEFAULTS:
            if block.get(k) not in (None, ""):
                t[k] = block[k]
    cur = str(t.get("currency") or "EUR").upper()
    t["currency"] = cur
    t["currency_symbol"] = CURRENCIES.get(cur, {}).get("symbol", cur)
    c = (t.get("country") or None)
    t["country"] = c.upper() if isinstance(c, str) and c else None
    try:
        import fuel as _fuel
        t["fuel_index_auto"] = _fuel.auto_available(t["country"])
        t["fuel_provider"] = _fuel.provider_public(t["country"])     # H1: which series, or None
    except Exception:
        t["fuel_index_auto"] = False
        t["fuel_provider"] = None
    t["restrictions_provider"] = t["country"] in RESTRICTION_PROVIDERS
    try:
        import restrictions as _rx
        t["restrictions"] = ({k: v for k, v in (_rx.provider_for(t["country"]) or {}).items()}
                             if t["country"] in RESTRICTION_PROVIDERS else None)
    except Exception:
        t["restrictions"] = None
    # H1: the distance unit the tenant reads (km stored; mi shown). Defaults to km; the
    # tenant block may say "mi" (validated in validate()).
    du = str((block or {}).get("distance_unit") or "").strip().lower() if isinstance(block, dict) else ""
    t["distance_unit"] = du if du in DISTANCE_UNITS else "km"
    dn = (block or {}).get("demo_notice") if isinstance(block, dict) else None
    t["demo_notice"] = dn.strip() if isinstance(dn, str) and dn.strip() else None
    ce = (block or {}).get("concern_email") if isinstance(block, dict) else None
    t["concern_email"] = ce.strip() if is_concern_email(ce) else None
    t["council_breaks"] = council_breaks(doc=doc)
    return t


# 13 Oct 2026 (W12, bundle B): the colour bands of the "By council" layer and of the bulletin's council sections, per
# scheme. Three ascending figures per measure: two-way movements a day, and t CO2e in the month. A district below the
# first is the lightest step, at or over the third the darkest. Typed on Config → Map and bulletin (tenant block,
# key `council_breaks`); a tenant that has not typed them reads these defaults — the stops the map has used since
# 12 Oct (map/index.html AREA_STOPS, held equal by parse_map.js and test_bulletin.py). Fixed per scheme, never worked
# out from the data, so a colour means the same figure in every month.
COUNCIL_BREAKS_DEFAULT = {"movements": (50, 100, 200), "carbon": (50, 100, 200)}
COUNCIL_BREAK_MEASURES = ("movements", "carbon")


def council_breaks_problem(v):
    """None when `v` is three ascending figures above zero, else what is wrong (for validate())."""
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return "must be three figures"
    # whole numbers: both legends print a band as "50 – 99 t" (the next band's figure less one)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 1
           or float(x) != int(x) for x in v):
        return "must be whole numbers, 1 or more"
    if not (v[0] < v[1] < v[2]):
        return "must rise from left to right"
    return None


def council_breaks(doc=None, conversions=None):
    """
    {"movements": [a, b, c], "carbon": [a, b, c]}: the tenant's typed bands, each measure falling back to
    COUNCIL_BREAKS_DEFAULT on its own when it is missing or not three ascending figures. The ONE reader: the
    areas payloads (the map) and the bulletin both call it.
    """
    if doc is None:
        if conversions is None:
            import conversions as _c
            conversions = _c
        try:
            doc = load(conversions)
        except Exception:
            doc = {}
    block = (doc or {}).get("tenant") if isinstance(doc, dict) else None
    typed = block.get("council_breaks") if isinstance(block, dict) else None
    out = {}
    for m in COUNCIL_BREAK_MEASURES:
        v = typed.get(m) if isinstance(typed, dict) else None
        out[m] = [int(x) for x in v] if council_breaks_problem(v) is None else list(COUNCIL_BREAKS_DEFAULT[m])
    return out


# one plain address: something@domain.tld, no spaces, no second address, nothing a mailto: could be bent with
_CONCERN_EMAIL_RE = re.compile(r"^[^\s@<>\"',;:?&]+@[^\s@<>\"',;:?&]+\.[^\s@<>\"',;:?&]+$")


def is_concern_email(v):
    return isinstance(v, str) and 0 < len(v.strip()) <= 254 and bool(_CONCERN_EMAIL_RE.match(v.strip()))
# a small in-process cache so the many load_factors() calls inside one request do not
# each hit the database. Invalidated on every write through this module; a write made
# by another process (another Render instance) shows up within TTL seconds.
_CACHE = {"doc": None, "at": 0.0}
CACHE_TTL_S = 5.0


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _file_doc(conversions):
    with open(conversions._FACTORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_row():
    """The stored document plus its stamp, or None when the row does not exist."""
    try:
        rows = db.query("SELECT value, updated_by, updated_at FROM config "
                        "WHERE tenant_id = ? AND key = ?", (db.current_tenant(), KEY))
    except Exception:
        return None          # table not created yet (a cold database, or a test)
    if not rows:
        return None
    try:
        return {"doc": json.loads(rows[0]["value"]), "updated_by": rows[0]["updated_by"],
                "updated_at": rows[0]["updated_at"]}
    except Exception:
        return None          # a corrupt row must not take the app down; fall back


def load(conversions, use_cache=True):
    """The live factors document: the config row, else the file."""
    import time
    if use_cache and _CACHE["doc"] is not None and time.time() - _CACHE["at"] < CACHE_TTL_S:
        return _CACHE["doc"]
    row = get_row()
    doc = row["doc"] if row else _file_doc(conversions)
    _CACHE["doc"], _CACHE["at"] = doc, time.time()
    return doc


def invalidate():
    _CACHE["doc"], _CACHE["at"] = None, 0.0


def seed_from_file(conversions):
    """First boot: copy the file into the table. Does nothing if the row exists."""
    if get_row():
        return {"seeded": False}
    doc = _file_doc(conversions)
    db.execute("INSERT INTO config (tenant_id, key, value, updated_by, updated_at) "
               "VALUES (?, ?, ?, ?, ?)",
               (db.current_tenant(), KEY, json.dumps(doc, ensure_ascii=False),
                "seed:factors.json", _now()))
    invalidate()
    return {"seeded": True}


def validate(doc, network=None):
    """Problems with a candidate document, as a list of sentences. Empty = fine."""
    p = []
    if not isinstance(doc, dict):
        return ["the document must be a JSON object"]
    cats = doc.get("material_categories")
    vs = doc.get("vehicles")
    plan = doc.get("planning")
    if not isinstance(cats, dict) or not any(not k.startswith("_") for k in cats):
        p.append("material_categories must be an object with at least one category")
    if not isinstance(vs, dict) or not any(not k.startswith("_") for k in vs):
        p.append("vehicles must be an object with at least one vehicle")
    if not isinstance(plan, dict):
        p.append("planning must be an object")

    def num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    if isinstance(cats, dict):
        for k, c in cats.items():
            if k.startswith("_") or not isinstance(c, dict):
                continue
            d = c.get("density_t_per_m3")
            if not num(d) or d <= 0:
                p.append(f"material '{k}': density_t_per_m3 must be a positive number")
            if c.get("default_unit") not in (None, "m3", "t", "vehicles"):
                p.append(f"material '{k}': default_unit must be m3, t or vehicles")
            for v in c.get("vehicles") or []:
                if isinstance(vs, dict) and v not in vs:
                    p.append(f"material '{k}' lists vehicle '{v}', which does not exist")
    if isinstance(vs, dict):
        for k, v in vs.items():
            if k.startswith("_") or not isinstance(v, dict):
                continue
            pl = v.get("payload_t")
            if not num(pl) or pl <= 0:
                p.append(f"vehicle '{k}': payload_t must be a positive number")
            em = v.get("emissions_kg_co2e_per_km")
            # 12 Oct 2026 (B2): a BLANK cell saved on the Config page arrives as null (the page
            # writes num("") = null; it deletes the key only for load/unload minutes). Until
            # today that passed, and float(None) then raised inside every costlines read and
            # silently blanked every carbon figure on the map. Refused here, naming the vehicle.
            # An electric entry with no stored figure is the derived case and stays allowed;
            # a key that is absent altogether reads the fallback and is not a Config edit.
            if "emissions_kg_co2e_per_km" in v and (em is None or em == "") and v.get("fuel") != "electric":
                p.append(f"vehicle '{k}': the kg CO2e per km cell is blank — type its figure "
                         f"(0 for a vehicle with no tailpipe carbon) or put the stored one back; "
                         f"a blank would send every carbon figure on this vehicle to the fallback")
            elif em is not None and (not num(em) or em < 0):
                p.append(f"vehicle '{k}': emissions_kg_co2e_per_km must be a number >= 0")
            for f in ("load_minutes", "unload_minutes", "gvw_t"):
                if v.get(f) is not None and (not num(v[f]) or v[f] < 0):
                    p.append(f"vehicle '{k}': {f} must be a number >= 0")
            if v.get("gvw_t") is not None and num(v.get("gvw_t")) and num(pl) and v["gvw_t"] < pl:
                p.append(f"vehicle '{k}': gvw_t is less than payload_t")
            # 10 Oct 2026, carbon planner: the fuel and the electric figures
            fu = v.get("fuel")
            if fu is not None and fu not in FUELS:
                p.append(f"vehicle '{k}': fuel must be one of {', '.join(FUELS)}")
            if fu == "electric":
                kw = v.get("kwh_per_km")
                if not num(kw) or kw <= 0:
                    p.append(f"vehicle '{k}': an electric vehicle needs kwh_per_km, a positive number")
            for f in ("kwh_per_km", "battery_kwh_usable", "charge_kw"):
                if v.get(f) is not None and (not num(v[f]) or v[f] < 0):
                    p.append(f"vehicle '{k}': {f} must be a number >= 0")
            tw = v.get("geometry_twin")
            if tw is not None and (not isinstance(tw, str) or tw not in vs or tw == k):
                p.append(f"vehicle '{k}': geometry_twin must name another vehicle")
        for name in doc.get("planning_vehicles") or []:
            if name not in vs:
                p.append(f"planning_vehicles names '{name}', which does not exist")
        # H1: per-country vehicle sets name real vehicles, and a name is not both led and hidden
        sets = doc.get("vehicle_sets")
        if sets is not None:
            if not isinstance(sets, dict):
                p.append("vehicle_sets must be an object keyed by country code")
            else:
                for cc, cs in sets.items():
                    if not (isinstance(cc, str) and len(cc) == 2 and cc.isalpha()) or not isinstance(cs, dict):
                        p.append(f"vehicle_sets.{cc}: key must be a two-letter country code and the value an object")
                        continue
                    lead, hide = cs.get("lead") or [], cs.get("hide") or []
                    for name in list(lead) + list(hide):
                        if name not in vs:
                            p.append(f"vehicle_sets.{cc} names '{name}', which does not exist")
                    both = sorted(set(lead) & set(hide))
                    if both:
                        p.append(f"vehicle_sets.{cc}: {both} cannot be both lead and hidden")
        # a vehicle the network is baked for cannot be deleted — its geometry rows are
        # keyed on the name and every figure on those routes would fall to _default
        if network is not None:
            try:
                baked = {g["vehicle_profile"] for g in db.query(
                    "SELECT DISTINCT vehicle_profile FROM route_geometry WHERE tenant_id = ?",
                    (db.current_tenant(),))}
                for b in sorted(baked - set(vs)):
                    p.append(f"vehicle '{b}' has baked route geometry and cannot be removed")
            except Exception:
                pass
            if getattr(network, "DEFAULT_PROFILE", None) and network.DEFAULT_PROFILE not in vs:
                p.append(f"the default routing profile '{network.DEFAULT_PROFILE}' must exist")
    if isinstance(plan, dict):
        for f in ("working_days_per_month", "shift_hours_per_day", "avg_haul_speed_kmh",
                  "load_minutes", "unload_minutes"):
            x = plan.get(f)
            if not num(x) or x <= 0:
                p.append(f"planning.{f} must be a positive number")
    # 10 Oct 2026: the carbon block, when present. Every shape the carbon planner reads is
    # checked, so a Config save can never leave a document that makes every scenario fail:
    # the sub-blocks are objects, every factor a number >= 0 (null switches a figure off), a
    # disposal site type maps to a published route, and a category's carbon_material names a
    # class the live block OR the file carries (the planner merges the two key by key).
    cb = doc.get("carbon")
    if cb is not None and not isinstance(cb, dict):
        p.append("carbon must be an object")
        cb = None
    cb = cb or {}
    for blk in ("materials", "transport", "electricity", "electric_hgv", "disposal_loc_types", "benchmarks", "planned", "source"):
        if cb.get(blk) is not None and not isinstance(cb.get(blk), dict):
            p.append(f"carbon.{blk} must be an object")
    mats = cb.get("materials") if isinstance(cb.get("materials"), dict) else {}
    for mk, m in mats.items():
        if str(mk).startswith("_"):
            continue
        if not isinstance(m, dict):
            p.append(f"carbon.materials.{mk} must be an object")
            continue
        for grp in ("kg_co2e_per_t", "disposal_kg_co2e_per_t"):
            g = m.get(grp)
            if g is not None and not isinstance(g, dict):
                p.append(f"carbon.materials.{mk}.{grp} must be an object of figures")
                continue
            for kk, x in (g or {}).items():
                if x is not None and (not num(x) or x < 0):
                    p.append(f"carbon.materials.{mk}.{grp}.{kk} must be a number >= 0 or null")
    tr = cb.get("transport") if isinstance(cb.get("transport"), dict) else {}
    for blk, field in (("tonne_km_2026", "kg_co2e_per_tkm"), ("vehicle_km_2026", "kg_co2e_per_vkm")):
        rows = tr.get(blk)
        if rows is not None and not isinstance(rows, dict):
            p.append(f"carbon.transport.{blk} must be an object")
            continue
        for rk, r in (rows or {}).items():
            if str(rk).startswith("_") or not isinstance(r, dict) or field not in r:
                continue
            if r[field] is not None and (not num(r[field]) or r[field] < 0):
                p.append(f"carbon.transport.{blk}.{rk}.{field} must be a number >= 0")
    nh = tr.get("nh_carbon_tool_v27")
    if nh is not None:
        if not isinstance(nh, dict):
            p.append("carbon.transport.nh_carbon_tool_v27 must be an object")
        else:
            for f in ("laden_t_co2e_per_tkm", "unladen_t_co2e_per_tkm"):
                if nh.get(f) is not None and (not num(nh[f]) or nh[f] < 0):
                    p.append(f"carbon.transport.nh_carbon_tool_v27.{f} must be a number >= 0")
    el = cb.get("electricity") if isinstance(cb.get("electricity"), dict) else {}
    for kk, x in el.items():
        if str(kk).endswith("_per_kwh") and x is not None and (not num(x) or x < 0):
            p.append(f"carbon.electricity.{kk} must be a number >= 0")
    dl = cb.get("disposal_loc_types") if isinstance(cb.get("disposal_loc_types"), dict) else {}
    for kk, x in dl.items():
        if not str(kk).startswith("_") and x not in ("landfill", "closed_loop", "open_loop", "combustion"):
            p.append(f"carbon.disposal_loc_types.{kk} must be landfill, closed_loop, open_loop or combustion")
    if isinstance(cats, dict):
        known = set(k for k in mats if not str(k).startswith("_"))
        try:
            with open(os.path.join(os.path.dirname(__file__), "factors.json"), encoding="utf-8") as fh:
                fm = (json.load(fh).get("carbon") or {}).get("materials") or {}
            known |= set(k for k in fm if not str(k).startswith("_"))
        except Exception:
            pass
        for k, c in cats.items():
            cm = c.get("carbon_material") if isinstance(c, dict) else None
            if cm is not None and not isinstance(cm, str):
                p.append(f"material '{k}': carbon_material must be a class name or null")
            elif cm is not None and known and cm not in known:
                p.append(f"material '{k}': carbon_material '{cm}' is not a carbon material ({', '.join(sorted(known))})")
    # 10 Sep night: the fair-price block, when present — numbers >= 0, months 1-12
    fp = doc.get("fair_price")
    if fp is not None:
        if not isinstance(fp, dict):
            p.append("fair_price must be an object")
        else:
            for f in ("driver_eur_per_h", "vehicle_standing_eur_per_h", "running_eur_per_km",
                      "margin_pct", "vehicle_new_price_eur"):
                x = fp.get(f)
                if x is not None and (not num(x) or x < 0):
                    p.append(f"fair_price.{f} must be a number >= 0")
            cons = fp.get("consumption") or {}
            if isinstance(cons, dict):
                x = cons.get("l_per_100km_per_tonne")
                if x is not None and (not num(x) or x < 0):
                    p.append("fair_price.consumption.l_per_100km_per_tonne must be a number >= 0")
                for cls in ("rigid", "artic"):
                    y = (cons.get(cls) or {}).get("l_per_100km_empty") if isinstance(cons.get(cls), dict) else None
                    if y is not None and (not num(y) or y <= 0):
                        p.append(f"fair_price.consumption.{cls}.l_per_100km_empty must be a positive number")
            se = fp.get("season") or {}
            if isinstance(se, dict):
                for f in ("winter_months", "thaw_months"):
                    ms = se.get(f) or []
                    if not all(isinstance(m, int) and 1 <= m <= 12 for m in ms):
                        p.append(f"fair_price.season.{f} must be integers 1-12")
                u = se.get("winter_consumption_uplift_pct")
                if u is not None and (not num(u) or u < 0):
                    p.append("fair_price.season.winter_consumption_uplift_pct must be a number >= 0")
    # G2: the tenant block, when present
    tb = doc.get("tenant")
    if tb is not None:
        if not isinstance(tb, dict):
            p.append("tenant must be an object")
        else:
            for f in ("name", "team_label"):
                if tb.get(f) is not None and (not isinstance(tb[f], str) or not tb[f].strip()):
                    p.append(f"tenant.{f} must be a non-empty string")
            if tb.get("currency") is not None and str(tb["currency"]).upper() not in CURRENCIES:
                p.append(f"tenant.currency must be one of {', '.join(sorted(CURRENCIES))}")
            c = tb.get("country")
            if c is not None and c != "" and not (isinstance(c, str) and len(c) == 2 and c.isalpha()):
                p.append("tenant.country must be a two-letter ISO code or null")
            du = tb.get("distance_unit")
            if du is not None and du != "" and str(du).strip().lower() not in DISTANCE_UNITS:
                p.append("tenant.distance_unit must be 'km' or 'mi'")
            dn = tb.get("demo_notice")
            if dn is not None and (not isinstance(dn, str) or len(dn) > 120):
                p.append("tenant.demo_notice must be text of at most 120 characters, or null")
            ce = tb.get("concern_email")
            if ce is not None and ce != "" and not is_concern_email(ce):
                p.append("tenant.concern_email must be one email address, or null")
            cb = tb.get("council_breaks")
            if cb is not None:
                if not isinstance(cb, dict):
                    p.append("tenant.council_breaks must be an object with movements and carbon")
                else:
                    for m in COUNCIL_BREAK_MEASURES:
                        if cb.get(m) is not None and council_breaks_problem(cb[m]):
                            p.append(f"tenant.council_breaks.{m} {council_breaks_problem(cb[m])}")
                    for k in cb:
                        if k not in COUNCIL_BREAK_MEASURES:
                            p.append(f"tenant.council_breaks.{k} is not a measure (movements or carbon)")
    for w in doc.get("seasonal_restrictions") or []:
        if not isinstance(w, dict) or not w.get("name"):
            p.append("every seasonal restriction needs a name")
            continue
        ms = w.get("months") or []
        if not all(isinstance(m, int) and 1 <= m <= 12 for m in ms):
            p.append(f"seasonal '{w['name']}': months must be integers 1-12")
        for v in w.get("restricted_vehicles") or []:
            if isinstance(vs, dict) and v not in vs:
                p.append(f"seasonal '{w['name']}' names vehicle '{v}', which does not exist")
    return p


def save(doc, by=None, network=None):
    """Validate and store. Returns {ok, problems}."""
    problems = validate(doc, network=network)
    if problems:
        return {"ok": False, "problems": problems}
    if get_row():
        db.execute("UPDATE config SET value = ?, updated_by = ?, updated_at = ? "
                   "WHERE tenant_id = ? AND key = ?",
                   (json.dumps(doc, ensure_ascii=False), by, _now(), db.current_tenant(), KEY))
    else:
        db.execute("INSERT INTO config (tenant_id, key, value, updated_by, updated_at) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (db.current_tenant(), KEY, json.dumps(doc, ensure_ascii=False), by, _now()))
    invalidate()
    return {"ok": True, "problems": []}


def reset_to_file(conversions, by=None, network=None):
    """Overwrite the stored document with the file. The one way the file wins again.

    11 Oct 2026: `network` is passed through to save(), so a reset is held to the same
    rule as a Save: a vehicle the network is baked for cannot be removed. Until the EU
    vehicles left the seed the file always carried every vehicle a live document did, so
    a reset never removed one; now a live row saved before 11 Oct (the demo's) carries
    four the file lacks, and an unguarded reset would drop them under baked geometry and
    re-base every line on them silently. The endpoint always passes the network."""
    doc = _file_doc(conversions)
    res = save(doc, by=f"reset:factors.json ({by or 'unknown'})", network=network)
    return {"ok": res["ok"], "problems": res["problems"], "doc": doc}


def status(conversions):
    """What the Config page shows at the top: where the live numbers come from."""
    row = get_row()
    file_doc = _file_doc(conversions)
    live = row["doc"] if row else file_doc
    return {
        "source": "database" if row else "file",
        "updated_by": row["updated_by"] if row else None,
        "updated_at": row["updated_at"] if row else None,
        # a cheap "has the file drifted from the live copy" signal
        "differs_from_file": bool(row) and json.dumps(live, sort_keys=True) != json.dumps(file_doc, sort_keys=True),
    }
