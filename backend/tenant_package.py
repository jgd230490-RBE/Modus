"""
tenant_package.py — a tenant as one JSON document. Modus G2, 2026-09-16.

WHY THIS EXISTS
---------------
The product used to ship its first customer's network, taxonomy and alignment as code
(seed_data/, taxonomy.py's IPT and work-section tables, map/data/*.js). A second
customer could not exist without editing the repository, and the first customer's data
could not leave it. Now:

    * the product boots to an EMPTY tenant — no locations, no routes, no teams, no
      sections; only the generic disciplines and the factors file are seeded;
    * everything a tenant owns is written into a PACKAGE — every row of every tenanted
      table, plus the config rows (factors, costing, overlay) — and imported into an
      empty tenant elsewhere. Baked route geometry travels with it, so a network does
      not have to be re-proven through HERE after a move;
    * a synthetic demo tenant is just a package nobody owns (tools/make_demo_tenant.py).

THE DOCUMENT
------------
    {
      "modus_package": 1,                       # format version — refuse anything else
      "exported_at": "2026-09-16T12:00:00Z",
      "tenant_id":   "default",                 # informational; the importer uses the CURRENT tenant
      "app_version": "...",                     # informational
      "tables": { "<table>": [ {row}, ... ] }   # tenanted tables only, tenant_id stripped
    }

`config` rows are in tables.config like any other (key/value/updated_by/updated_at), so
the factors document, the costing settings and the alignment overlay all travel.

IMPORT RULES
------------
    * The tenant must be EMPTY (no locations, routes, forecasts, teams or sections)
      unless replace=True, which deletes every tenanted row of the current tenant
      first. There is no merge: a package is a whole tenant, not a patch.
    * Columns are matched to the LIVE schema by name. A column the package has and the
      schema lacks is dropped and reported; a column the schema has and the package
      lacks is left to its default. So an older package imports into a newer schema.
    * Tables are inserted parents-first (ORDER below) so a foreign-key-shaped
      relationship never dangles mid-import; every statement runs on the same
      connection and the import commits once at the end — a failure leaves the tenant
      as it was.
    * tenant_id is NEVER read from the package. Every row is stamped with the tenant
      the request is running as. A package cannot write into another tenant.
    * Nothing here calls HERE, Mapbox or any external service.

WHAT THIS DOES NOT DO
---------------------
It does not migrate a database (db.init_* do that), it does not validate the physics
of the factors document (config.validate does, and import calls it for the factors
row), and it does not know what a row MEANS — a package that names a discipline no
row defines will import and then show "no discipline" in the picker, exactly as a
hand-typed one would.
"""
import datetime
import json
import re

import db

FORMAT = 1

# Parents before children. Every table in db.TENANTED_TABLES must appear here exactly
# once — test_modus.py asserts it, so a table added to the schema cannot be silently
# left out of the package.
ORDER = [
    "config",
    "disciplines", "discipline_materials",
    "ipts", "design_sections", "work_sections",
    "locations", "location_gates",
    "zones",
    "routes", "route_haul_roads", "route_geometry",
    "forecasts", "forecast_weeks", "forecast_days",
    "stockpile_weeks",
]

# "Empty" for import purposes: the tables a person's work lands in. config is not in
# the list because every booted tenant has the seeded factors row.
EMPTY_CHECK = ("locations", "routes", "forecasts", "ipts", "work_sections", "zones",
               "forecast_weeks", "stockpile_weeks")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _columns(cur, table):
    return db._columns_of(cur, table)


def table_rows(table):
    """Every row of one tenanted table for the current tenant, tenant_id stripped."""
    rows = db.query(f"SELECT * FROM {table} WHERE tenant_id = ?", (db.current_tenant(),))
    out = []
    for r in rows:
        d = dict(r)
        d.pop("tenant_id", None)
        out.append(d)
    return out


def is_empty():
    """True when the current tenant holds no work in any EMPTY_CHECK table."""
    for t in EMPTY_CHECK:
        try:
            n = db.query(f"SELECT COUNT(*) AS n FROM {t} WHERE tenant_id = ?",
                         (db.current_tenant(),))[0]["n"]
        except Exception:
            n = 0            # a table this database has not created yet holds nothing
        if n:
            return False
    return True


def export_tenant(app_version=None):
    """The whole current tenant as a package document."""
    tables = {}
    for t in ORDER:
        try:
            tables[t] = table_rows(t)
        except Exception as e:
            # a table the schema has not created yet (a cold test database) exports as
            # empty rather than aborting the whole export
            tables[t] = []
            print(f"tenant_package: {t} not exported ({e})")
    return {
        "modus_package": FORMAT,
        "exported_at": _now(),
        "tenant_id": db.current_tenant(),
        "app_version": app_version,
        "tables": tables,
    }


def validate(pkg):
    """Problems with a candidate package, as sentences. Empty = importable."""
    p = []
    if not isinstance(pkg, dict):
        return ["the package must be a JSON object"]
    if pkg.get("modus_package") != FORMAT:
        p.append(f"modus_package must be {FORMAT} (got {pkg.get('modus_package')!r})")
    tables = pkg.get("tables")
    if not isinstance(tables, dict):
        p.append("tables must be an object of table name -> list of rows")
        return p
    for t, rows in tables.items():
        if t not in db.TENANTED_TABLES:
            p.append(f"unknown table '{t}'")
            continue
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            p.append(f"tables.{t} must be a list of row objects")
    # the factors document, if present, must pass the same checks the Config page applies
    for row in (tables.get("config") or []):
        if isinstance(row, dict) and row.get("key") == "factors":
            try:
                import config as _config
                doc = json.loads(row.get("value") or "null")
                probs = _config.validate(doc)
                p += [f"config.factors: {x}" for x in probs]
            except Exception as e:
                p.append(f"config.factors is not valid JSON ({e})")
    return p


def counts(pkg):
    return {t: len(rows or []) for t, rows in (pkg.get("tables") or {}).items()}


def _delete_tenant_rows(cur, tenant):
    for t in reversed(ORDER):
        try:
            cur.execute(db._adapt(f"DELETE FROM {t} WHERE tenant_id = ?"), (tenant,))
        except Exception as e:
            print(f"tenant_package: could not clear {t} ({e})")


def import_tenant(pkg, replace=False):
    """
    Import a package into the CURRENT tenant. Returns
    {ok, inserted: {table: n}, dropped_columns: {table: [col]}, replaced: bool}.
    Raises ValueError on a bad package or a non-empty tenant without replace.
    """
    problems = validate(pkg)
    if problems:
        raise ValueError("; ".join(problems))
    if not replace and not is_empty():
        raise ValueError("this tenant already holds data — export it first, then import "
                         "with replace=true to overwrite it")
    tenant = db.current_tenant()
    tables = pkg["tables"]
    inserted, dropped = {}, {}
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        if replace:
            _delete_tenant_rows(cur, tenant)
        for t in ORDER:
            rows = tables.get(t) or []
            if not rows:
                continue
            live = _columns(cur, t)
            if not live:
                raise ValueError(f"table {t} does not exist in this database")
            # A package is the WHOLE tenant: a table it carries replaces that table's
            # rows for this tenant. On an empty tenant that only ever means the boot
            # seeds — the generic disciplines and the factors config row — which the
            # package's own copies supersede. User work is guarded by is_empty() above.
            cur.execute(db._adapt(f"DELETE FROM {t} WHERE tenant_id = ?"), (tenant,))
            live_set = set(live)
            gone = set()
            n = 0
            for r in rows:
                cols = [c for c in r.keys() if c in live_set and c != "tenant_id"]
                gone |= {c for c in r.keys() if c not in live_set and c != "tenant_id"}
                vals = [_to_db(r[c]) for c in cols]
                sql = (f"INSERT INTO {t} (tenant_id, {', '.join(cols)}) "
                       f"VALUES (?, {', '.join('?' for _ in cols)})")
                cur.execute(db._adapt(sql), [tenant] + vals)
                n += 1
            inserted[t] = n
            if gone:
                dropped[t] = sorted(gone)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    try:
        import config as _config
        _config.invalidate()
    except Exception:
        pass
    # An optional national fuel-index price the package suggests (a typed placeholder
    # for a country the bulletin does not cover). fuel_index is GLOBAL, one row per
    # country, so it is applied only where that country has no row yet — never over a
    # live bulletin row or a price somebody typed.
    applied_fuel = []
    for fi in (pkg.get("fuel_index") or []):
        try:
            import fuel as _fuel
            c = str(fi.get("country") or "").upper()
            if c and not _fuel.get_index(c):
                r = _fuel.set_manual(fi.get("eur_per_l"), fi.get("bulletin_date"), by="tenant package", country=c)
                if r.get("ok"):
                    applied_fuel.append(c)
        except Exception as e:
            print("tenant_package: fuel_index not applied:", e)
    return {"ok": True, "inserted": inserted, "dropped_columns": dropped, "replaced": bool(replace),
            "fuel_index_applied": applied_fuel}


def import_rows(table, rows):
    """
    Insert rows into ONE tenanted table for the current tenant, matching columns by name
    like import_tenant. For tests and tools; the product's own path is import_tenant.
    """
    if table not in db.TENANTED_TABLES:
        raise ValueError(f"unknown table '{table}'")
    tenant = db.current_tenant()
    conn = db.get_conn()
    n = 0
    try:
        cur = conn.cursor()
        live = set(_columns(cur, table))
        for r in rows:
            cols = [c for c in r.keys() if c in live and c != "tenant_id"]
            sql = (f"INSERT INTO {table} (tenant_id, {', '.join(cols)}) "
                   f"VALUES (?, {', '.join('?' for _ in cols)})")
            cur.execute(db._adapt(sql), [tenant] + [_to_db(r[c]) for c in cols])
            n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def _to_db(v):
    """JSON values -> what the drivers accept. Dicts and lists are stored as JSON text
    (that is how every JSON-bearing column in this schema is written)."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


# --------------------------------------------------------------------------- #
#  The overlay — the map's alignment package, one config row                   #
# --------------------------------------------------------------------------- #
OVERLAY_KEY = "overlay"


def get_overlay_row():
    rows = db.query("SELECT value, updated_by, updated_at FROM config WHERE tenant_id = ? AND key = ?",
                    (db.current_tenant(), OVERLAY_KEY))
    return rows[0] if rows else None


def set_overlay(doc, by=None):
    """Store the map overlay for the current tenant (see map/overlay.js for the shape)."""
    probs = validate_overlay(doc)
    if probs:
        return {"ok": False, "problems": probs}
    val = json.dumps(doc, ensure_ascii=False)
    if get_overlay_row():
        db.execute("UPDATE config SET value = ?, updated_by = ?, updated_at = ? "
                   "WHERE tenant_id = ? AND key = ?",
                   (val, by, _now(), db.current_tenant(), OVERLAY_KEY))
    else:
        db.execute("INSERT INTO config (tenant_id, key, value, updated_by, updated_at) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (db.current_tenant(), OVERLAY_KEY, val, by, _now()))
    return {"ok": True, "problems": []}


def validate_overlay(doc):
    p = []
    if not isinstance(doc, dict):
        return ["the overlay must be a JSON object"]
    for fc in ("alignment", "chainage", "rail"):
        v = doc.get(fc)
        if v is not None and not (isinstance(v, dict) and v.get("type") == "FeatureCollection"
                                  and isinstance(v.get("features"), list)):
            p.append(f"{fc} must be a GeoJSON FeatureCollection or null")
    bands = doc.get("bands") or []
    if not isinstance(bands, list):
        p.append("bands must be a list")
    else:
        prev = None
        for i, b in enumerate(bands):
            if not isinstance(b, dict) or "chain_from" not in b or "chain_to" not in b:
                p.append(f"bands[{i}] needs chain_from and chain_to")
                continue
            if not all(isinstance(b[k], (int, float)) and not isinstance(b[k], bool)
                       for k in ("chain_from", "chain_to")):
                p.append(f"bands[{i}] chain_from and chain_to must be numbers (metres)")
                continue
            if b["chain_to"] <= b["chain_from"]:
                p.append(f"bands[{i}] runs backwards or is empty ({b['chain_from']} -> {b['chain_to']})")
            if prev is not None and b["chain_from"] != prev:
                p.append(f"bands[{i}] chain_from {b['chain_from']} != previous chain_to {prev} (bands must be contiguous)")
            prev = b["chain_to"]
            if not b.get("colour"):
                p.append(f"bands[{i}] needs a colour")
            elif not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(b["colour"])):
                p.append(f"bands[{i}] colour must be #RRGGBB, got {b['colour']!r}")
        # a boundary tick marks a colour change, so it must sit on a band edge
        edges = set()
        for b in bands:
            if isinstance(b, dict):
                edges.update(x for x in (b.get("chain_from"), b.get("chain_to")) if isinstance(x, (int, float)))
        bnds = doc.get("boundaries") or []
        if not isinstance(bnds, list):
            p.append("boundaries must be a list")
        else:
            for i, b in enumerate(bnds):
                cm = (b or {}).get("chain_m") if isinstance(b, dict) else None
                if not isinstance(cm, (int, float)) or isinstance(cm, bool):
                    p.append(f"boundaries[{i}] needs a numeric chain_m")
                elif bands and cm not in edges:
                    p.append(f"boundaries[{i}] chain_m {cm} is not a band edge — a tick must sit on the colour change it marks")
    view = doc.get("view")
    if view is not None:
        c = (view or {}).get("center")
        if not (isinstance(c, list) and len(c) == 2 and all(isinstance(x, (int, float)) for x in c)):
            p.append("view.center must be [lon, lat]")
    return p
