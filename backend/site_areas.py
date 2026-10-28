"""
site_areas.py — the places inside a site a lorry goes after the gate (simulation v2, 28 Oct 2026, task 0e).

An AREA belongs to one location and has one activity:
  unload   a laden lorry whose material category (and vehicle, when listed) the area takes is unloaded here
  load     an empty lorry coming to load is loaded here (muck away, a stockpile drawn down)
  wash     the wheel wash: every lorry leaving the site passes it, after its area; at most one a site
`bays` lorries are served at once, each for `service_minutes` (blank = the vehicle's own loading or unloading minutes
from the factors, or WASH_MINUTES for a wash). `materials` and `vehicles` are lists ([] = any). `level` is words for the
drawing. `geometry` is a GeoJSON Point or Polygon; `point_of` is where a lorry stops (a polygon's centroid).

Read by sim_site.py (the station chain) and the Locations page; written by admins through /api/admin/site-areas.
Every SQL literal carries the tenant. Nothing here is routed: the public roads and the gates' access roads are
untouched by an area.
"""
import datetime
import json

import db

ACTIVITIES = ("unload", "load", "wash")
#: a wheel wash with no minutes typed takes this long a lorry
WASH_MINUTES = 2.0
MAX_BAYS = 20
MAX_MINUTES = 240.0
GEOM_TYPES = ("Point", "Polygon")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _truthy(v):
    return bool(v) and str(v).lower() not in ("0", "false", "")


def _list(v):
    """A JSON list of strings (stored text, a list, or None) -> [str]."""
    if v in (None, ""):
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return []
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def _geom(v):
    if v in (None, ""):
        return None
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return None
    return v if isinstance(v, dict) else None


def point_of(geom):
    """[lon, lat] a lorry stops at: the Point itself, or the polygon's outer-ring centroid. None without one."""
    g = _geom(geom)
    if not g:
        return None
    if g.get("type") == "Point":
        c = g.get("coordinates") or []
        return [float(c[0]), float(c[1])] if len(c) >= 2 else None
    if g.get("type") == "Polygon":
        rings = g.get("coordinates") or []
        ring = [p for p in (rings[0] if rings else []) if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(ring) > 1 and ring[0][0] == ring[-1][0] and ring[0][1] == ring[-1][1]:
            ring = ring[:-1]
        if not ring:
            return None
        return [sum(float(p[0]) for p in ring) / len(ring), sum(float(p[1]) for p in ring) / len(ring)]
    return None


def _valid_geometry(geom):
    g = _geom(geom)
    return bool(g) and g.get("type") in GEOM_TYPES and point_of(g) is not None


def _row(a):
    g = _geom(a.get("geometry"))
    return {
        "id": a["id"], "location_id": a["location_id"], "name": a.get("name"),
        "activity": (a.get("activity") or "unload"),
        "materials": _list(a.get("materials")), "vehicles": _list(a.get("vehicles")),
        "service_minutes": (float(a["service_minutes"]) if a.get("service_minutes") not in (None, "") else None),
        "bays": max(1, int(a.get("bays") or 1)),
        "level": a.get("level") or None,
        "geometry": g, "point": point_of(g),
        "seq": int(a.get("seq") or 0), "active": _truthy(a.get("active")),
        "note": a.get("note") or None,
        "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
    }


# --------------------------------------------------------------------------- reads
def list_areas(location_id=None, include_inactive=True):
    if location_id:
        rows = db.query("SELECT * FROM site_areas WHERE tenant_id = ? AND location_id = ? ORDER BY seq, id",
                        (db.current_tenant(), location_id))
    else:
        rows = db.query("SELECT * FROM site_areas WHERE tenant_id = ? ORDER BY location_id, seq, id",
                        (db.current_tenant(),))
    out = [_row(a) for a in rows]
    if not include_inactive:
        out = [a for a in out if a["active"]]
    return out


def by_location(include_inactive=False):
    """{location id: [areas]} — one read for every site."""
    out = {}
    for a in list_areas(include_inactive=include_inactive):
        out.setdefault(a["location_id"], []).append(a)
    return out


def get_area(area_id):
    rows = db.query("SELECT * FROM site_areas WHERE tenant_id = ? AND id = ?", (db.current_tenant(), area_id))
    if not rows:
        return {"error": "area not found", "id": area_id}
    return _row(rows[0])


# --------------------------------------------------------------------------- the lorry's area
def area_for(areas, kind, material=None, vehicle=None):
    """
    The area a lorry goes to: `kind` 'laden' or 'pour' -> an unload area, 'empty' -> a load area. The first active
    area (by seq) whose materials hold the lorry's category (an empty list takes any) and whose vehicles hold its
    vehicle (an empty list takes any); else the first that takes any material. None = no area for it.
    """
    act = "load" if kind == "empty" else "unload"
    cands = [a for a in (areas or []) if a["active"] and a["activity"] == act]
    for a in cands:
        if (not a["materials"] or (material and material in a["materials"])) and (not a["vehicles"] or (vehicle and vehicle in a["vehicles"])):
            return a
    for a in cands:
        if not a["materials"] and not a["vehicles"]:
            return a
    return None


def wash_for(areas):
    return next((a for a in (areas or []) if a["active"] and a["activity"] == "wash"), None)


def service_for(area, vehicle, factors):
    """The area's minutes a lorry: as typed, else the vehicle's own (factors), else the wash's default."""
    if area.get("service_minutes") not in (None, ""):
        return float(area["service_minutes"])
    if area.get("activity") == "wash":
        return WASH_MINUTES
    key = "load_minutes" if area.get("activity") == "load" else "unload_minutes"
    vs = (factors or {}).get("vehicles") or {}
    v = vs.get(vehicle) if vehicle else None
    plan = (factors or {}).get("planning") or {}
    for src in (v or {}, vs.get("_default") or {}, plan):
        if isinstance(src, dict) and src.get(key) not in (None, ""):
            try:
                return float(src[key])
            except (TypeError, ValueError):
                pass
    return 0.0


# --------------------------------------------------------------------------- writes
def _next_id():
    rows = db.query("SELECT id FROM site_areas WHERE tenant_id = ?", (db.current_tenant(),))
    n = 0
    for r in rows:
        try:
            n = max(n, int(str(r["id"]).lstrip("A")))
        except ValueError:
            pass
    return f"A{n + 1:03d}"


def _problem(location_id, name, activity, materials, vehicles, service_minutes, bays, geometry, exclude_id=None):
    if not (location_id or "").strip():
        return "location_id is required"
    if not db.query("SELECT id FROM locations WHERE tenant_id = ? AND id = ?", (db.current_tenant(), location_id)):
        return f"location {location_id} not found"
    if not (name or "").strip():
        return "name is required"
    if activity not in ACTIVITIES:
        return "activity must be unload, load or wash"
    if activity == "wash":
        other = [a for a in list_areas(location_id) if a["activity"] == "wash" and a["active"] and a["id"] != exclude_id]
        if other:
            return "this site already has a wheel wash"
    if service_minutes not in (None, ""):
        try:
            m = float(service_minutes)
        except (TypeError, ValueError):
            return "the minutes a lorry must be a number"
        if not (0 <= m <= MAX_MINUTES):
            return f"the minutes a lorry must be between 0 and {MAX_MINUTES:g}"
    try:
        b = int(bays)
    except (TypeError, ValueError):
        return "bays must be a whole number"
    if not (1 <= b <= MAX_BAYS):
        return f"bays must be between 1 and {MAX_BAYS}"
    if not isinstance(_list(materials), list) or not isinstance(_list(vehicles), list):
        return "materials and vehicles must be lists"
    if geometry not in (None, "") and not _valid_geometry(geometry):
        return "the area must be drawn as a point or a shape"
    return None


def create_area(location_id, name, activity="unload", materials=None, vehicles=None, service_minutes=None, bays=1,
                level=None, geometry=None, seq=0, active=True, note=None, area_id=None):
    activity = (activity or "unload").strip().lower()
    p = _problem(location_id, name, activity, materials, vehicles, service_minutes, bays, geometry)
    if p:
        return {"error": p}
    aid = (area_id or "").strip() or _next_id()
    if db.query("SELECT id FROM site_areas WHERE tenant_id = ? AND id = ?", (db.current_tenant(), aid)):
        return {"error": f"area {aid} already exists"}
    now = _now()
    db.execute(
        "INSERT INTO site_areas (tenant_id, id, location_id, name, activity, materials, vehicles, service_minutes, "
        "bays, level, geometry, seq, active, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.current_tenant(), aid, location_id, name.strip(), activity, json.dumps(_list(materials)),
         json.dumps(_list(vehicles)), (None if service_minutes in (None, "") else float(service_minutes)),
         int(bays), (level or None), (json.dumps(_geom(geometry)) if geometry not in (None, "") else None),
         int(seq or 0), bool(active), (note or None), now, now))
    return get_area(aid)


def update_area(area_id, **fields):
    """Partial update: only the keys present are written (the gates' rule)."""
    cur = db.query("SELECT * FROM site_areas WHERE tenant_id = ? AND id = ?", (db.current_tenant(), area_id))
    if not cur:
        return {"error": "area not found", "id": area_id}
    c = _row(cur[0])
    nxt = dict(c)
    for k in ("name", "activity", "materials", "vehicles", "service_minutes", "bays", "geometry"):
        if k in fields:
            nxt[k] = fields[k]
    act = (nxt.get("activity") or "unload").strip().lower()
    p = _problem(c["location_id"], nxt.get("name"), act, nxt.get("materials"), nxt.get("vehicles"),
                 nxt.get("service_minutes"), nxt.get("bays"), nxt.get("geometry"), exclude_id=area_id)
    if p:
        return {"error": p}
    sets, params = [], []
    if "name" in fields:
        sets.append("name = ?"); params.append(fields["name"].strip())
    if "activity" in fields:
        sets.append("activity = ?"); params.append(act)
    if "materials" in fields:
        sets.append("materials = ?"); params.append(json.dumps(_list(fields["materials"])))
    if "vehicles" in fields:
        sets.append("vehicles = ?"); params.append(json.dumps(_list(fields["vehicles"])))
    if "service_minutes" in fields:
        v = fields["service_minutes"]
        sets.append("service_minutes = ?"); params.append(None if v in (None, "") else float(v))
    if "bays" in fields:
        sets.append("bays = ?"); params.append(int(fields["bays"]))
    if "level" in fields:
        sets.append("level = ?"); params.append(fields["level"] or None)
    if "geometry" in fields:
        g = fields["geometry"]
        sets.append("geometry = ?"); params.append(json.dumps(_geom(g)) if g not in (None, "") else None)
    if "seq" in fields:
        sets.append("seq = ?"); params.append(int(fields["seq"] or 0))
    if "active" in fields:
        sets.append("active = ?"); params.append(bool(fields["active"]))
    if "note" in fields:
        sets.append("note = ?"); params.append(fields["note"] or None)
    if not sets:
        return get_area(area_id)
    sets.append("updated_at = ?"); params.append(_now())
    params.append(db.current_tenant()); params.append(area_id)
    db.execute("UPDATE site_areas SET {} WHERE tenant_id = ? AND id = ?".format(", ".join(sets)), tuple(params))
    return get_area(area_id)


def delete_area(area_id):
    a = get_area(area_id)
    if a.get("error"):
        return a
    db.execute("DELETE FROM site_areas WHERE tenant_id = ? AND id = ?", (db.current_tenant(), area_id))
    return {"ok": True, "deleted": area_id}
