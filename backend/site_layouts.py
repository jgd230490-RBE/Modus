"""
site_layouts.py — a site's logistics layout (task 4c PR 1, 31 Oct 2026; plan notes site-layouts-plan-1030.md §2, §6).

ONE layout a site (a location). A layout has PHASES, each with the months it applies to ('YYYY-MM', either end open)
and its map things: a GeoJSON FeatureCollection in WGS 84 to 7 decimals, each thing naming a style in
site_layout_styles (refused when unknown; any property not in KEYS is dropped). A phase holds at most MAX_PHASE things.

A save carries the phase's `version`; a save behind someone else's is refused with STALE (two planners on one site).
Drawings are brought in by site_layout_import.read() into a short-lived in-memory hold (HOLD_S, per process) and placed
here by place(): the "in the file -> becomes" table chooses each row's style, the organisation's choices are saved in
its Config as `site_layouts.import_map`, and the import is logged in site_layout_imports (the file is not kept).

Every SQL literal carries the tenant. Written by planners and admins (Q6); read by staff (the Route map's layer).
"""
import datetime
import json
import math
import re
import threading
import time
import uuid

import db
import site_layout_import as imp
import site_layout_styles as styles

MAX_PHASE = 2000
MAX_PHASES = 24
MAX_NAME = 80
STALE = "Someone else saved this layout. Reload to see their changes."
#: an import's read things are held this long for the place step, a few at a time
HOLD_S = 30 * 60
HOLD_MAX = 4
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: the properties a thing may carry (anything else is dropped on save)
KEYS = ("style", "layer", "color", "w", "opacity", "fill", "outline", "sym", "size", "rot", "text", "bold", "halo",
        "halo_color", "label", "z", "source", "src_layer", "mode")


class Problem(Exception):
    """A refusal in plain words (shown as it is)."""


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _next_id(table, prefix):
    rows = db.query(f"SELECT id FROM {table} WHERE tenant_id = ?", (db.current_tenant(),))
    n = 0
    for r in rows:
        m = re.fullmatch(prefix + r"(\d+)", r["id"] or "")
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:03d}"


def _truthy(v):
    return bool(v) and str(v).lower() not in ("0", "false", "f", "")


# --------------------------------------------------------------------------------------------------------- things
def _num(v, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return min(hi, max(lo, x))


def _hexc(v):
    return v.upper() if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None


def _pt(c):
    if not isinstance(c, (list, tuple)) or len(c) < 2:
        return None
    try:
        x, y = float(c[0]), float(c[1])
    except (TypeError, ValueError):
        return None
    if not (-180 <= x <= 180 and -90 <= y <= 90):
        return None
    return [round(x, 7), round(y, 7)]


def clean_geometry(g):
    """A Point, LineString (2+ points) or Polygon (one closed ring of 4+ points), rounded to 7 dp; None if not."""
    if not isinstance(g, dict):
        return None
    t, c = g.get("type"), g.get("coordinates")
    if t == "Point":
        p = _pt(c)
        return {"type": "Point", "coordinates": p} if p else None
    if t == "LineString":
        ps = [_pt(x) for x in (c or [])] if isinstance(c, list) else []
        if len(ps) < 2 or None in ps or len(ps) > 5000:
            return None
        return {"type": "LineString", "coordinates": ps}
    if t == "Polygon":
        if not isinstance(c, list) or not c or not isinstance(c[0], list):
            return None
        ring = [_pt(x) for x in c[0]]
        if None in ring or len(ring) < 3 or len(ring) > 5000:
            return None
        if ring[0] != ring[-1]:
            ring.append(list(ring[0]))
        if len(ring) < 4:
            return None
        return {"type": "Polygon", "coordinates": [ring]}
    return None


def kind_of(style):
    if style == "sym":
        return "sym"
    if style == "text":
        return "text"
    if style in styles.AREA_STYLES:
        return "area"
    if style in styles.LINE_STYLES:
        return "line"
    return None


GEOM_FOR = {"line": "LineString", "area": "Polygon", "sym": "Point", "text": "Point"}


def clean_thing(f):
    """One thing checked against the style table: (thing, None) or (None, why). Unknown properties are dropped."""
    if not isinstance(f, dict):
        return None, "not a thing"
    p = f.get("properties") if isinstance(f.get("properties"), dict) else {}
    g = clean_geometry(f.get("geometry"))
    if g is None:
        return None, "its shape is not a point, line or area"
    st = p.get("style")
    k = kind_of(st)
    if k is None:
        return None, f"its style “{str(st)[:40]}” is not one Wayscope draws"
    if g["type"] != GEOM_FOR[k]:
        return None, f"a {k} must be a {GEOM_FOR[k].lower().replace('linestring', 'line').replace('polygon', 'area')}"
    if k == "sym" and p.get("sym") not in styles.SYMBOL_KEYS:
        return None, f"its symbol “{str(p.get('sym'))[:40]}” is not one Wayscope draws"
    out = {"style": st}
    lay = p.get("layer")
    if lay in styles.LAYERS:
        out["layer"] = lay
    elif k == "line":
        out["layer"] = styles.LINE_STYLES[st]["layer"]
    elif k == "area":
        out["layer"] = "Areas"
    elif k == "sym":
        out["layer"] = styles.SYMBOL_LAYER.get(styles.SYMBOL_KEYS[p["sym"]]["group"], "Welfare and safety")
    else:
        out["layer"] = "Text and notes"
    for key in ("color", "halo_color"):
        c = _hexc(p.get(key))
        if c:
            out[key] = c
    for key, lo, hi in (("w", 0.02, 60.0), ("opacity", 0.0, 1.0), ("size", 0.2, 120.0), ("rot", -720.0, 720.0)):
        if p.get(key) is not None:
            x = _num(p.get(key), lo, hi)
            if x is not None:
                out[key] = round(x, 3)
    if p.get("fill") in styles.FILLS:
        out["fill"] = p["fill"]
    if p.get("outline") in styles.OUTLINES:
        out["outline"] = p["outline"]
    if k == "sym":
        out["sym"] = p["sym"]
    for key, mx in (("text", 200), ("label", 80), ("source", 200), ("src_layer", 120)):
        v = p.get(key)
        if isinstance(v, str) and v.strip():
            out[key] = re.sub(r"[\x00-\x1f]+", " ", v.strip())[:mx]
        elif key == "text" and v == "" and k == "area":
            out[key] = ""
    if k == "text" and not out.get("text"):
        return None, "a text thing needs words"
    for key in ("bold", "halo"):
        if key in p:
            out[key] = bool(p[key]) and p[key] not in ("0", "false")
    if p.get("z") is not None:
        z = _num(p.get("z"), -99, 99)
        if z is not None:
            out["z"] = int(z)
    out["mode"] = {"Point": "point", "LineString": "linestring", "Polygon": "polygon"}[g["type"]]
    return {"type": "Feature", "geometry": g, "properties": out}, None


def clean_features(fc):
    """A FeatureCollection (or list) -> (things, [why left out])."""
    feats = fc.get("features") if isinstance(fc, dict) else fc
    if not isinstance(feats, list):
        raise Problem("The layout's things must be a list.")
    if len(feats) > MAX_PHASE:
        raise Problem(f"A phase holds at most {MAX_PHASE:,} things.")
    out, why = [], []
    for f in feats:
        t, w = clean_thing(f)
        if t:
            out.append(t)
        else:
            why.append(w)
    return out, why


def _fc(things):
    return {"type": "FeatureCollection", "features": things}


# --------------------------------------------------------------------------------------------------------- reads
def _layout_row(location_id):
    rows = db.query("SELECT * FROM site_layouts WHERE tenant_id = ? AND location_id = ?",
                    (db.current_tenant(), location_id))
    return rows[0] if rows else None


def _phase_out(r, with_things=True):
    try:
        fc = json.loads(r.get("features_json") or "{}")
    except Exception:
        fc = {}
    feats = fc.get("features") if isinstance(fc, dict) and isinstance(fc.get("features"), list) else []
    out = {"id": r["id"], "layout_id": r["layout_id"], "name": r["name"], "month_from": r.get("month_from") or None,
           "month_to": r.get("month_to") or None, "clp_stage": r.get("clp_stage") or None, "sort": int(r.get("sort") or 0),
           "things": len(feats), "updated_by": r.get("updated_by"), "updated_at": r.get("updated_at"),
           "version": int(r.get("version") or 1)}
    if with_things:
        out["features"] = _fc(feats)
    return out


def get(location_id, with_things=True):
    """A site's layout with its phases (in order) and its import log; None when the site has none."""
    lay = _layout_row(location_id)
    if not lay:
        return None
    tenant = db.current_tenant()
    phases = db.query("SELECT * FROM site_layout_phases WHERE tenant_id = ? AND layout_id = ? ORDER BY sort, id",
                      (tenant, lay["id"]))
    log = db.query("SELECT id, phase_id, file_name, format, report_json, things, created_by, created_at "
                   "FROM site_layout_imports WHERE tenant_id = ? AND layout_id = ? ORDER BY created_at DESC, id DESC",
                   (tenant, lay["id"]))
    imports = []
    for r in log[:20]:
        try:
            rep = json.loads(r.get("report_json") or "{}")
        except Exception:
            rep = {}
        imports.append({"id": r["id"], "phase_id": r.get("phase_id"), "file_name": r.get("file_name"),
                        "format": r.get("format"), "things": int(r.get("things") or 0), "by": r.get("created_by"),
                        "at": r.get("created_at"), "fit": rep.get("fit_words"), "transform": rep.get("transform")})
    return {"id": lay["id"], "location_id": lay["location_id"], "name": lay.get("name"),
            "public": _truthy(lay.get("public")), "version": int(lay.get("version") or 1),
            "updated_at": lay.get("updated_at"),
            "phases": [_phase_out(p, with_things) for p in phases], "imports": imports}


def summary():
    """{location id: {phases, things}} for every site with a layout (the Locations list's mark)."""
    tenant = db.current_tenant()
    lays = db.query("SELECT id, location_id FROM site_layouts WHERE tenant_id = ?", (tenant,))
    if not lays:
        return {}
    ph = db.query("SELECT layout_id, features_json FROM site_layout_phases WHERE tenant_id = ?", (tenant,))
    by = {}
    for p in ph:
        try:
            n = len((json.loads(p.get("features_json") or "{}") or {}).get("features") or [])
        except Exception:
            n = 0
        b = by.setdefault(p["layout_id"], [0, 0])
        b[0] += 1
        b[1] += n
    return {l["location_id"]: {"phases": by.get(l["id"], [0, 0])[0], "things": by.get(l["id"], [0, 0])[1]} for l in lays}


def in_month(ph, month):
    """True when a phase applies in 'YYYY-MM' (an open end applies)."""
    if not month:
        return True
    return (not ph.get("month_from") or ph["month_from"] <= month) and (not ph.get("month_to") or month <= ph["month_to"])


def for_map(month=None):
    """The staff Route map's layer: every site's phases that apply in `month` ('YYYY-MM'; None = this month), as ONE
    FeatureCollection, each thing tagged with its site and phase. Read only."""
    if month is None:
        month = datetime.date.today().strftime("%Y-%m")
    tenant = db.current_tenant()
    lays = {l["id"]: l for l in db.query("SELECT id, location_id FROM site_layouts WHERE tenant_id = ?", (tenant,))}
    if not lays:
        return {"month": month, "sites": [], "features": _fc([])}
    names = {r["id"]: r.get("name") for r in db.query("SELECT id, name FROM locations WHERE tenant_id = ?", (tenant,))}
    feats, sites = [], {}
    for p in db.query("SELECT * FROM site_layout_phases WHERE tenant_id = ? ORDER BY sort, id", (tenant,)):
        lay = lays.get(p["layout_id"])
        if not lay or not in_month(p, month):
            continue
        ph = _phase_out(p)
        for f in ph["features"]["features"]:
            q = dict(f["properties"])
            q.update(site=lay["location_id"], phase=ph["id"])
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": q})
        s = sites.setdefault(lay["location_id"], {"location_id": lay["location_id"],
                                                  "name": names.get(lay["location_id"]) or lay["location_id"], "phases": []})
        s["phases"].append({"id": ph["id"], "name": ph["name"], "things": ph["things"]})
    return {"month": month, "sites": sorted(sites.values(), key=lambda s: s["name"] or ""), "features": _fc(feats)}


# --------------------------------------------------------------------------------------------------------- writes
def _location(location_id):
    rows = db.query("SELECT id, name, lat, lon FROM locations WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), location_id))
    if not rows:
        raise Problem("That location is not set up here.")
    return rows[0]


def _ensure_layout(location_id, by):
    lay = _layout_row(location_id)
    if lay:
        return lay
    loc = _location(location_id)
    lid = _next_id("site_layouts", "SL")
    now = _now()
    db.execute("INSERT INTO site_layouts (tenant_id, id, location_id, name, public, created_by, created_at, updated_at, "
               "version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
               (db.current_tenant(), lid, location_id, loc.get("name"), False, by, now, now))
    return _layout_row(location_id)


def _month(v, what):
    if v in (None, ""):
        return None
    v = str(v).strip()
    if not MONTH_RE.match(v):
        raise Problem(f"The {what} month must be a month, like 2027-04.")
    return v


def _phase_fields(body, current=None):
    cur = current or {}
    name = body.get("name", cur.get("name"))
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]
    if not name:
        raise Problem("Give the phase a name.")
    mf = _month(body.get("month_from", cur.get("month_from")), "From")
    mt = _month(body.get("month_to", cur.get("month_to")), "To")
    if mf and mt and mt < mf:
        raise Problem("The To month is before the From month.")
    return name, mf, mt


def _phase_row(phase_id):
    rows = db.query("SELECT * FROM site_layout_phases WHERE tenant_id = ? AND id = ?", (db.current_tenant(), phase_id))
    if not rows:
        raise Problem("That phase is not there any more. Reload to see the layout.")
    return rows[0]


def add_phase(location_id, body, by):
    lay = _ensure_layout(location_id, by)
    tenant = db.current_tenant()
    n = db.query("SELECT COUNT(*) AS n, MAX(sort) AS s FROM site_layout_phases WHERE tenant_id = ? AND layout_id = ?",
                 (tenant, lay["id"]))[0]
    if int(n["n"] or 0) >= MAX_PHASES:
        raise Problem(f"A layout holds at most {MAX_PHASES} phases.")
    name, mf, mt = _phase_fields(body)
    things, _why = clean_features(body.get("features") or [])
    pid = _next_id("site_layout_phases", "PH")
    db.execute("INSERT INTO site_layout_phases (tenant_id, id, layout_id, name, month_from, month_to, sort, "
               "features_json, updated_by, updated_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
               (tenant, pid, lay["id"], name, mf, mt, int(n["s"] or 0) + 1, json.dumps(_fc(things)), by, _now()))
    return pid


def _bump(phase_id, version, sets, params, by):
    """UPDATE the phase only if its version is still `version`; refuse with STALE when someone saved first."""
    try:
        v = int(version)
    except (TypeError, ValueError):
        raise Problem(STALE)
    tenant = db.current_tenant()
    # the stamp to the microsecond tells this save from another that also moved the version on
    stamp = datetime.datetime.utcnow().isoformat(timespec="microseconds") + "Z"
    db.execute("UPDATE site_layout_phases SET {}, updated_by = ?, updated_at = ?, version = version + 1 WHERE tenant_id = ? "
               "AND id = ? AND version = ?".format(sets), tuple(params) + (by, stamp, tenant, phase_id, v))
    r = _phase_row(phase_id)
    if int(r.get("version") or 0) != v + 1 or r.get("updated_at") != stamp:
        raise Problem(STALE)
    return r


def edit_phase(phase_id, body, by):
    """Rename / set the months of a phase (a save with the version check)."""
    cur = _phase_row(phase_id)
    if int(body.get("version") or 0) != int(cur.get("version") or 1):
        raise Problem(STALE)
    name, mf, mt = _phase_fields(body, cur)
    return _phase_out(_bump(phase_id, body.get("version"), "name = ?, month_from = ?, month_to = ?", (name, mf, mt), by))


def save_things(phase_id, body, by):
    """Replace a phase's things (PR 2's tools save through here)."""
    cur = _phase_row(phase_id)
    if int(body.get("version") or 0) != int(cur.get("version") or 1):
        raise Problem(STALE)
    things, why = clean_features(body.get("features") or {})
    r = _bump(phase_id, body.get("version"), "features_json = ?", (json.dumps(_fc(things)),), by)
    out = _phase_out(r)
    out["left_out"] = why
    return out


def delete_phase(phase_id, version):
    cur = _phase_row(phase_id)
    if str(version) != str(cur.get("version") or 1):
        raise Problem(STALE)
    db.execute("DELETE FROM site_layout_phases WHERE tenant_id = ? AND id = ? AND version = ?",
               (db.current_tenant(), phase_id, int(cur.get("version") or 1)))
    return {"ok": True, "deleted": phase_id}


# --------------------------------------------------------------------------------------------------------- imports
_HOLD = {}
_HOLD_LOCK = threading.Lock()


def _hold_put(entry):
    with _HOLD_LOCK:
        now = time.time()
        for k in [k for k, v in _HOLD.items() if now - v["at"] > HOLD_S]:
            _HOLD.pop(k, None)
        while len(_HOLD) >= HOLD_MAX:
            _HOLD.pop(min(_HOLD, key=lambda k: _HOLD[k]["at"]), None)
        key = uuid.uuid4().hex
        entry["at"] = now
        _HOLD[key] = entry
        return key


def _hold_get(key, location_id):
    with _HOLD_LOCK:
        e = _HOLD.get(str(key or ""))
    if not e or time.time() - e["at"] > HOLD_S or e["tenant"] != db.current_tenant() or e["location_id"] != location_id:
        raise Problem("This drawing is no longer held. Bring the file in again.")
    return e


def import_map():
    """The organisation's saved "in the file -> becomes" choices."""
    import config
    import conversions
    doc = config.load(conversions)
    blk = doc.get("site_layouts") if isinstance(doc, dict) else None
    m = blk.get("import_map") if isinstance(blk, dict) else None
    return {k: v for k, v in (m or {}).items() if isinstance(k, str) and styles.choice_ok(v)}


def import_map_problem(m):
    """config.validate's check of `site_layouts.import_map`."""
    if m is None:
        return None
    if not isinstance(m, dict):
        return "site_layouts.import_map must be an object"
    if len(m) > 1000:
        return "site_layouts.import_map holds at most 1,000 rows"
    for k, v in m.items():
        if not isinstance(k, str) or not k or len(k) > 160:
            return "site_layouts.import_map: each row must be named by at most 160 characters"
        if not styles.choice_ok(v):
            return f"site_layouts.import_map: “{k[:40]}” must become a style Wayscope draws, text, or leave out"
    return None


def _save_map(choices, by):
    """Merge this import's choices into the organisation's table (newest wins)."""
    import config
    import conversions
    doc = json.loads(json.dumps(config.load(conversions, use_cache=False)))
    blk = doc.get("site_layouts") if isinstance(doc.get("site_layouts"), dict) else {}
    m = dict(blk.get("import_map") or {})
    m.update({k: v for k, v in choices.items() if styles.choice_ok(v)})
    if len(m) > 1000:
        m = dict(list(m.items())[-1000:])
    blk["import_map"] = m
    doc["site_layouts"] = blk
    res = config.save(doc, by=by)
    return bool(res.get("ok"))


def _site_gates(location_id):
    rows = db.query("SELECT name, lat, lon, active FROM location_gates WHERE tenant_id = ? AND location_id = ?",
                    (db.current_tenant(), location_id))
    return [{"name": r.get("name") or "gate", "lon": float(r["lon"]), "lat": float(r["lat"])}
            for r in rows if r.get("lat") is not None and r.get("lon") is not None
            and r.get("active") not in (False, 0, "0", "f", "false")]


def _near_points():
    rows = db.query("SELECT lat, lon FROM locations WHERE tenant_id = ?", (db.current_tenant(),))
    return [[float(r["lon"]), float(r["lat"])] for r in rows if r.get("lat") is not None and r.get("lon") is not None]


def read_file(location_id, data, file_name, grid="auto", by=None):
    """Read an uploaded drawing and HOLD it for place(): {import_id, report, rows, control, gate_check, bounds}.
    Raises site_layout_import.Refused / AskGrid / Problem."""
    _location(location_id)
    if grid not in ("auto", "bng", "site"):
        grid = "auto"
    res = imp.read(data, file_name, grid=grid, near=_near_points())
    things, rep = res["things"], res["report"]
    rows = imp.rows(things, import_map())
    gates = []
    if rep.get("grid") != "site":
        gates = imp.gate_checks(things, _site_gates(location_id))
        rep["gate_check"] = gates
    key = _hold_put({"tenant": db.current_tenant(), "location_id": location_id, "things": things, "report": rep,
                     "file": file_name})
    return {"import_id": key, "report": rep, "rows": rows, "control": rep.get("control") or [],
            "gate_check": gates, "bounds": _bounds(things) if rep.get("grid") != "site" else None,
            "site_gates": _site_gates(location_id)}


def _bounds(things):
    xs, ys = [], []
    for t in things:
        g = t["geometry"]
        cs = [g["coordinates"]] if g["type"] == "Point" else g["coordinates"] if g["type"] == "LineString" else g["coordinates"][0]
        for c in cs:
            xs.append(c[0])
            ys.append(c[1])
    return [[min(xs), min(ys)], [max(xs), max(ys)]] if xs else None


def _pairs(e, points):
    """The planner's survey points [{name, lon, lat}] joined to the drawing's control points by name."""
    ctl = {c["name"]: c for c in (e["report"].get("control") or [])}
    out = []
    for p in points or []:
        c = ctl.get(str((p or {}).get("name") or ""))
        ll = _pt([(p or {}).get("lon"), (p or {}).get("lat")])
        if c and ll:
            out.append({"name": c["name"], "x": c["x"], "y": c["y"], "lon": ll[0], "lat": ll[1]})
    return out


def fit_preview(location_id, import_id, points):
    """The fit from the points placed so far: turn, scale, each point's miss, the sentence; plus the gate check."""
    e = _hold_get(import_id, location_id)
    if e["report"].get("grid") != "site":
        raise Problem("This drawing is not on a site grid.")
    pairs = _pairs(e, points)
    ft = imp.fit(pairs)
    moved = imp.fitted(e["things"], ft)
    return {"turn": ft["turn"], "scale": ft["scale"], "worst": ft["worst"], "misses": ft["misses"], "over": ft["over"],
            "scale_flag": ft["scale_flag"], "words": imp.fit_words(ft),
            "gate_check": imp.gate_checks(moved, _site_gates(location_id)), "bounds": _bounds(moved)}


def _default_props(kind, val):
    if kind == "line":
        s = styles.LINE_STYLES[val]
        return {"style": val, "layer": s["layer"], "color": s["color"], "w": s["w"], "opacity": 1}
    if kind == "area":
        s = styles.AREA_STYLES[val]
        return {"style": val, "layer": "Areas", "color": s["color"], "opacity": s["opacity"], "fill": s["fill"],
                "outline": s["outline"], "text": s["text"]}
    if kind == "sym":
        s = styles.SYMBOL_KEYS[val]
        return {"style": "sym", "sym": val, "layer": styles.SYMBOL_LAYER.get(s["group"], "Welfare and safety"),
                "size": s["size"], "rot": 0, "label": ""}
    return {"style": "text", "layer": "Text and notes", "text": "Text", "size": 2.2, "color": "#111827", "bold": True,
            "halo": True, "halo_color": "#FFFFFF", "rot": 0}


def placed_things(things, choice, keep_colours, source, turn=0.0):
    """The file's things turned into layout things by the table (the mockup's placeImport, on the server)."""
    out = []
    for t in things:
        p, g = t["properties"], t["geometry"]
        ch = choice.get(imp.row_key(p)) or "skip"
        kind, _, val = ch.partition(":")
        if kind == "skip" or not styles.choice_ok(ch):
            continue
        extra = {"source": source, "src_layer": p.get("src_layer")}
        if keep_colours and p.get("color"):
            extra["color"] = p["color"]
        rot = round(float(p.get("rot") or 0) - (turn or 0), 2)
        new = None
        if kind == "line" and g["type"] == "LineString":
            new = (g, dict(extra, **({"w": p["width_m"]} if p.get("width_m") else {})))
        elif kind == "line" and g["type"] == "Polygon":
            new = ({"type": "LineString", "coordinates": g["coordinates"][0]}, extra)
        elif kind == "area" and g["type"] == "Polygon":
            new = (g, dict(extra, text=""))
        elif kind == "area" and g["type"] == "LineString" and len(g["coordinates"]) > 3:
            new = ({"type": "Polygon", "coordinates": [g["coordinates"] + [g["coordinates"][0]]]}, extra)
        elif kind == "text" and g["type"] == "Point" and (p.get("text") or p.get("name")):
            new = (g, dict(extra, text=p.get("text") or p.get("name"),
                           size=round(p["height_m"] * 1.35, 2) if p.get("height_m") else 3, rot=rot, bold=False))
        elif kind == "sym" and g["type"] == "Point":
            new = (g, dict(extra, rot=rot, label=p["name"] if p.get("name") and re.search("gate", p["name"], re.I) else ""))
        if new is None:
            continue
        props = _default_props(kind, val if kind != "text" else None)
        props.update({k: v for k, v in new[1].items() if v is not None})
        th, _w = clean_thing({"type": "Feature", "geometry": new[0], "properties": props})
        if th:
            out.append(th)
    return out


def place(location_id, body, by):
    """Place a held drawing on a phase. body: {import_id, choices {row: choice}, points [{name, lon, lat}] (site grid),
    place_anyway, keep_colours, where 'new' | <phase id>, phase {name, month_from, month_to}, version (an existing
    phase's)}. Returns {phase, placed, left_out, report}."""
    e = _hold_get(body.get("import_id"), location_id)
    rep = dict(e["report"])
    choice = {k: v for k, v in (body.get("choices") or {}).items() if isinstance(k, str) and styles.choice_ok(v)}
    rows = {r["key"]: r["becomes"] for r in imp.rows(e["things"], import_map())}
    for k in rows:
        choice.setdefault(k, rows[k])
    things, turn = e["things"], 0.0
    if rep.get("grid") == "site":
        ft = imp.fit(_pairs(e, body.get("points")))
        if ft["over"] and not body.get("place_anyway"):
            raise Problem(f"A survey point misses by {ft['worst']:.2f} m (more than 1 m). Check the points, or tick "
                          "Place anyway.")
        # 31 Oct 2026 (seen in Chrome): two points always fit exactly, so a wrong scale is the only sign of a wrong pick
        if ft["scale_flag"] and not body.get("place_anyway"):
            raise Problem(f"The drawing would be stretched {ft['scale']:.4f} times to fit. Check the points and the "
                          "drawing's units, or tick Place anyway.")
        things, turn = imp.fitted(things, ft), ft["turn"]
        rep.update(fit={"turn": ft["turn"], "scale": ft["scale"], "worst": ft["worst"], "misses": ft["misses"]},
                   fit_words=imp.fit_words(ft))
    source = f"{e['file']} ({rep.get('format')})"
    out = placed_things(things, choice, bool(body.get("keep_colours")), source[:200], turn)
    if not out:
        raise Problem("Nothing to place: every row is set to Leave out.")
    where = body.get("where") or "new"
    if where == "new":
        ph = body.get("phase") or {}
        if len(out) > MAX_PHASE:
            raise Problem(f"A phase holds at most {MAX_PHASE:,} things; this drawing has {len(out):,}. Leave some rows out.")
        pid = add_phase(location_id, {"name": ph.get("name") or ("Imported · " + str(e["file"]))[:MAX_NAME],
                                      "month_from": ph.get("month_from"), "month_to": ph.get("month_to"),
                                      "features": out}, by)
        phase = _phase_out(_phase_row(pid), with_things=False)
    else:
        cur = _phase_row(where)
        lay = _layout_row(location_id)
        if not lay or cur["layout_id"] != lay["id"]:
            raise Problem("That phase is not on this site's layout.")
        have = json.loads(cur.get("features_json") or "{}").get("features") or []
        if len(have) + len(out) > MAX_PHASE:
            raise Problem(f"A phase holds at most {MAX_PHASE:,} things; this would make {len(have) + len(out):,}.")
        phase = save_things(where, {"version": body.get("version"), "features": have + out}, by)
        phase.pop("features", None)
        phase.pop("left_out", None)
    lay = _layout_row(location_id)
    rep_keep = {k: v for k, v in rep.items() if k not in ("control",)}
    db.execute("INSERT INTO site_layout_imports (tenant_id, id, layout_id, phase_id, file_name, format, report_json, "
               "things, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), _next_id("site_layout_imports", "IM"), lay["id"], phase["id"], str(e["file"])[:200],
                rep.get("format"), json.dumps(rep_keep), len(out), by, _now()))
    _save_map(choice, by)
    with _HOLD_LOCK:
        _HOLD.pop(str(body.get("import_id")), None)
    return {"phase": phase, "placed": len(out), "left_out": len(things) - len(out), "report": rep_keep}
