"""
abnormal_route.py — an abnormal load's OWN route, drawn by HERE at the load's typed size (D67), and the potential pinch
points Wayscope can see along it. Wayscope, 22 Oct 2026 (S16 / B5 phase 2; the user: "go ahead with the pinch points").

WHAT HERE WAS SEEN TO RETURN (the probe of 22 Oct 2026, four calls, notes/abnormal-loads-1022-probe — nothing below is
assumed beyond it)
  * HERE's vehicle parameters take the typed figures: grossWeight and weightPerAxle in kg, height / width / length in cm
    (HERE's maxima: 5,000 / 5,000 / 3,000 cm — a 36 m load is drawn for 30 m and the bake SAYS so), axleCount.
  * `return=actions,instructions` adds an `actions` list to each section: depart / turn / roundaboutExit /
    roundaboutPass / ramp / keep / continue / arrive, a `direction` (left / right), a `severity` on turns ("quite" was
    the one value seen), an `exit` number on roundaboutExit, an `offset` = the index of the point in the section's
    polyline, a `length`, a `duration`, and the `instruction` in words ("Take the 3rd exit from roundabout onto
    Harborough Road (B6047)…"; "Pass 3 roundabouts and continue on Leicester Road (A607)" — the COUNT is only in the
    words).
  * `spans=names,routeNumbers,functionalClass,length,notices` adds `spans`: offset, length, names [{value}],
    routeNumbers [{value}], functionalClass 1–5, notices (none seen). No width, height or weight on a span.
  * Asking for them changed nothing: the control call gave the same 12,077 m / 913 s line.
  * No `notices` came back on any of the four routes (the 16 Oct probe saw none either).

THE CANDIDATES (potential pinch points, every one graded Grey "to survey", WSP's scale; the route survey decides —
never a verdict, never a structure rating, never a swept path):
  here    every turn (with HERE's severity word), every roundabout exit (with its number), every "pass N
          roundabouts" stretch; a slip road or a keep-left only for a LONG load (over 25.9 m overall or 18.75 m rigid);
          any HERE notice (a limit HERE could not keep to)
  line    a sharp bend in the line itself: a heading change of BEND_DEG or more within BEND_WINDOW_M, for a long load,
          where no HERE turn already stands
  limits  a stored signed limit (OpenStreetMap / HERE, limits.py) the line runs along, judged against the LOAD's own
          gross, height, width and heaviest axle: "exceeds" and "at the limit" are candidates; "within" is listed in
          the hits only
  typed   phase 3: the planner's own rows (the route survey's findings), kept across re-bakes
Phase 3 adds the OpenStreetMap candidates (bridges carried, railways crossed, level crossings, traffic calming,
overhead lines, tagged widths) from the community layer's extract.

THE RETURN LEG: drawn only when the movement says the return is abnormal too (a crane); an empty trailer within the
normal limits is a lorry route and is not drawn. The haul roads and the gates' access roads are NOT spliced (an
abnormal load's route is HERE's line gate to gate; the planner's via points bend it).

Nothing here is a lorry count (D70) or a carbon figure (D71).
"""
import datetime
import json
import math
import re

import db
import gates
import here_routing
import limits
import abnormal_rules as rules

#: HERE Routing v8 vehicle[] maxima (the API reference, read 16 Oct 2026): height and width 5,000 cm, length 3,000 cm
HERE_MAX_CM = {"height": 5000, "width": 5000, "length": 3000}
#: what the bake asks HERE for beyond the line (the probe of 22 Oct 2026)
EXTRAS = {"return": "polyline,summary,actions,instructions", "spans": "names,routeNumbers,functionalClass,length,notices"}
#: a sharp bend in the line: this much heading change inside this length (a judgement, not a standard); a bend within
#: BEND_NEAR_M of a HERE turn or roundabout is that turn, not a second candidate
BEND_DEG = 60.0
BEND_WINDOW_M = 40.0
BEND_NEAR_M = 30.0
#: WSP's grading of a route survey's obstacles (the research note §4), Grey = not yet surveyed
GRADES = ("grey", "green", "amber", "red", "black")
GRADE_WORDS = {"grey": "Grey — to survey", "green": "Green — passable", "amber": "Amber — passable with care or measures",
               "red": "Red — needs works or a permit", "black": "Black — impassable"}
KIND_WORDS = {"turn": "Turn", "roundabout": "Roundabout", "slip_road": "Slip road", "bend": "Sharp bend",
              "limit": "Signed limit", "notice": "HERE notice", "bridge": "Bridge", "railway": "Railway crossed",
              "level_crossing": "Level crossing", "calming": "Traffic calming", "overhead": "Overhead line",
              "width": "Narrow road", "junction": "Junction", "furniture": "Street furniture", "other": "Other"}
INDICATIVE_WORDS = ("Indicative line drawn by HERE for the load's size. The haulier's ESDAL route and route survey govern; "
                    "structures are checked by their owners through ESDAL.")
CANDIDATE_WORDS = ("Potential pinch points found by Wayscope from HERE's turn-by-turn, the line itself and the stored signed "
                   "limits, each graded Grey (to survey). The route survey decides: no structure rating, no swept path, "
                   "no overhead clearance is worked out here.")
_ORD = {1: "1st", 2: "2nd", 3: "3rd"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ordinal(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "an"
    return _ORD.get(n, f"{n}th")


def is_long(m):
    """A long load: over the STGO combination line overall, or the rigid line (the swept-path candidates apply)."""
    ln, rl = rules._num(m.get("length_m")), rules._num(m.get("rigid_length_m"))
    return (ln is not None and ln > rules.STGO_COMBINATION_M) or (rl is not None and rl > rules.STGO_RIGID_M)


# --------------------------------------------------------------------------- #
#  The HERE call at the typed size                                             #
# --------------------------------------------------------------------------- #
def vehicle_params(m):
    """HERE's vehicle parameters from the typed figures, and the notes for anything HERE cannot take as typed."""
    p = {"transportMode": "truck"}
    notes = []
    g = rules._num(m.get("gross_t"))
    if g:
        p["vehicle[grossWeight]"] = int(round(g * 1000))
    a = rules._num(m.get("max_axle_t"))
    if a:
        p["vehicle[weightPerAxle]"] = int(round(a * 1000))
    for key, col in (("height", "height_m"), ("width", "width_m"), ("length", "length_m")):
        v = rules._num(m.get(col))
        if not v:
            continue
        cm = int(round(v * 100))
        if cm > HERE_MAX_CM[key]:
            notes.append(f"HERE takes a {key} of at most {HERE_MAX_CM[key] / 100:g} m: the line is drawn for {HERE_MAX_CM[key] / 100:g} m, "
                         f"the load is {v:g} m")
            cm = HERE_MAX_CM[key]
        p[f"vehicle[{key}]"] = cm
    n = rules._int(m.get("axle_count"))
    if n and n >= 2:
        p["vehicle[axleCount]"] = n
    return p, notes


def via_points(m):
    """The planner's via points, [[lat, lon], …] in travel order, from via_json; [] when none."""
    raw = m.get("via") if "via" in m else m.get("via_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    out = []
    for p in raw or []:
        try:
            lat, lon = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append([lat, lon])
    return out


def via_problems(points):
    if not isinstance(points, list):
        return ["via points must be a list of [latitude, longitude] pairs"]
    if len(points) > 10:
        return ["at most 10 via points"]
    p = []
    for i, pt in enumerate(points):
        try:
            lat, lon = float(pt[0]), float(pt[1])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except Exception:
            p.append(f"via point {i + 1} is not a [latitude, longitude] pair")
    return p


def ends(m, locs, gbl):
    """Where the loaded leg leaves and arrives: the gate the movement names at each end (gates.resolve's rule), else the
    location's default for that direction. Returns (a, b, problem)."""
    o, d = locs.get(m.get("origin_id")), locs.get(m.get("dest_id"))
    if not o or not d:
        return None, None, "the movement's from or to location no longer exists"
    a = gates.resolve(o, "exit", m.get("origin_gate_id"), gates=gbl.get(o["id"]))
    b = gates.resolve(d, "entry", m.get("dest_gate_id"), gates=gbl.get(d["id"]))
    for r, loc in ((a, o), (b, d)):
        if r.get("blocked"):
            return None, None, f"gate {r['blocked'].get('name') or r['blocked'].get('id')} at {loc['name']} is not in use"
        if r.get("lat") is None or r.get("lon") is None:
            return None, None, f"{loc['name']} has no coordinates"
    return a, b, None


# --------------------------------------------------------------------------- #
#  What HERE's actions and spans say                                            #
# --------------------------------------------------------------------------- #
def _road_of(instruction):
    """'Turn right onto Leicester Road (B6047). Go for 675 m.' -> 'Leicester Road (B6047)'; None when no road is named."""
    mm = re.search(r"\b(?:onto|on) (.+?)(?: toward .+?)?(?:\. Go for|\.$|$)", instruction or "")
    return mm.group(1).strip() if mm else None


def _join_sections(parts):
    """One geometry, one actions list and one spans list across HERE's sections, the offsets made global (each
    section's polyline starts on the point the one before ended on, so a later section's offsets shift by the points
    before it less one)."""
    coords, actions, spans = [], [], []
    shift = 0
    for i, part in enumerate(parts or []):
        pts = part.get("geometry") or []
        start = shift if i == 0 else shift - 1
        for a in part.get("actions") or []:
            a2 = dict(a)
            a2["offset"] = int(a.get("offset") or 0) + max(start, 0)
            actions.append(a2)
        for s in part.get("spans") or []:
            s2 = dict(s)
            s2["offset"] = int(s.get("offset") or 0) + max(start, 0)
            spans.append(s2)
        coords.extend(pts[1:] if coords else pts)
        shift = len(coords)
    return coords, actions, spans


def roads_in_words(spans):
    """The roads the line runs along, in order, each once: [{name, ref, class, length_m}] — the public card's 'roads
    in words' and the ESDAL sheet's route description."""
    out = []
    for s in spans or []:
        name = next((n.get("value") for n in (s.get("names") or []) if isinstance(n, dict) and n.get("value")), None)
        ref = next((r.get("value") for r in (s.get("routeNumbers") or []) if isinstance(r, dict) and r.get("value")), None)
        if not name and not ref:
            continue
        if out and out[-1]["name"] == name and out[-1]["ref"] == ref:
            out[-1]["length_m"] += int(s.get("length") or 0)
            continue
        out.append({"name": name, "ref": ref, "class": s.get("functionalClass"), "length_m": int(s.get("length") or 0)})
    return out


def roads_sentence(roads, cap=14):
    words = []
    for r in roads or []:
        w = (f"{r['ref']} {r['name']}" if r.get("ref") and r.get("name") else (r.get("ref") or r.get("name") or ""))
        if w and (not words or words[-1] != w):
            words.append(w)
    if len(words) > cap:
        words = words[:cap] + [f"and {len(words) - cap} more"]
    return ", ".join(words)


def has_motorway(roads):
    return any(str(r.get("ref") or "").upper().startswith("M") for r in roads or [])


def _road_at(spans, offset):
    best = None
    for s in spans or []:
        if int(s.get("offset") or 0) <= offset:
            best = s
        else:
            break
    if not best:
        return None
    name = next((n.get("value") for n in (best.get("names") or []) if isinstance(n, dict)), None)
    ref = next((r.get("value") for r in (best.get("routeNumbers") or []) if isinstance(r, dict)), None)
    return f"{name} ({ref})" if name and ref else (name or ref)


def candidates_from_actions(actions, geometry, m, spans=None):
    """HERE's turn-by-turn as candidates: turns, roundabouts, and — for a long load — slip roads and keeps."""
    out = []
    long_load = is_long(m)
    for a in actions or []:
        kind = a.get("action")
        off = int(a.get("offset") or 0)
        pt = geometry[off] if geometry and 0 <= off < len(geometry) else None
        road = _road_of(a.get("instruction")) or _road_at(spans, off)
        sev = a.get("severity")
        if kind == "turn":
            k, words = "turn", f"Turn {a.get('direction') or ''} onto {road}".replace("  ", " ") if road else f"Turn {a.get('direction') or ''}".strip()
            detail = f"HERE's turn severity: {sev}" if sev else None
        elif kind == "uTurn":
            k, words, detail = "turn", f"U-turn{(' at ' + road) if road else ''}", None
        elif kind == "roundaboutExit":
            k, words = "roundabout", f"Roundabout: {_ordinal(a.get('exit'))} exit" + (f" onto {road}" if road else "")
            detail = None
        elif kind == "roundaboutPass":
            mm = re.search(r"Pass (\d+) roundabouts?", a.get("instruction") or "")
            n = mm.group(1) if mm else "several"
            k, words, detail = "roundabout", f"Passes {n} roundabouts" + (f" on {road}" if road else ""), "straight over each; HERE counts them in its words"
        elif kind in ("ramp", "keep") and long_load:
            k, words = "slip_road", (a.get("instruction") or "Slip road").split(". Go for")[0]
            detail = "a long load on a slip road or a lane change: the swept path is the survey's question"
        else:
            continue
        out.append({"source": "here", "kind": k, "place": road, "words": words, "detail": detail, "grade": "grey",
                    "lon": pt[0] if pt else None, "lat": pt[1] if pt else None, "offset": off})
    return out


def _heading(a, b):
    lat = math.radians((a[1] + b[1]) / 2.0)
    dx, dy = (b[0] - a[0]) * math.cos(lat), (b[1] - a[1])
    return math.degrees(math.atan2(dx, dy)) % 360.0


def bends(geometry, m, spans=None, taken_points=()):
    """Sharp bends in the line for a long load: a heading change of BEND_DEG or more within BEND_WINDOW_M, where HERE
    has no turn or roundabout within BEND_NEAR_M already."""
    if not is_long(m) or not geometry or len(geometry) < 3:
        return []
    out = []
    taken = [p for p in taken_points if p]
    for i in range(1, len(geometry) - 1):
        a, b, c = geometry[i - 1], geometry[i], geometry[i + 1]
        d1, d2 = limits._hav_m(a, b), limits._hav_m(b, c)
        if d1 + d2 > BEND_WINDOW_M or d1 <= 0 or d2 <= 0:
            continue
        turn = abs((_heading(b, c) - _heading(a, b) + 180.0) % 360.0 - 180.0)
        if turn < BEND_DEG:
            continue
        if any(limits._hav_m(b, t) <= BEND_NEAR_M for t in taken):
            continue
        road = _road_at(spans, i)
        out.append({"source": "line", "kind": "bend", "place": road, "words": f"Sharp bend ({turn:.0f}°)" + (f" on {road}" if road else ""),
                    "detail": f"a heading change of {turn:.0f}° within {d1 + d2:.0f} m of line: a swept-path question for a load this long",
                    "grade": "grey", "lon": b[0], "lat": b[1], "offset": i})
        taken.append(b)
    return out


def load_dims(m):
    return {"mass_t": rules._num(m.get("gross_t")), "height_m": rules._num(m.get("height_m")),
            "width_m": rules._num(m.get("width_m")), "axle_t": rules._num(m.get("max_axle_t"))}


def limit_candidates(hits):
    out = []
    for h in hits or []:
        if h.get("verdict") not in ("exceeds", "at_limit"):
            continue
        over = "is over" if h["verdict"] == "exceeds" else "is exactly at"
        out.append({"source": "limits", "kind": "limit", "place": h.get("name") or h.get("ref"),
                    "words": f"{h.get('headline')}: the load's {h.get('vehicle_value'):g} {h.get('unit')} {over} it",
                    "detail": h.get("note"), "grade": "grey",
                    "lon": (h.get("anchor") or [None, None])[0], "lat": (h.get("anchor") or [None, None])[1], "offset": None})
    return out


def notice_candidates(notices, geometry):
    out = []
    for n in notices or []:
        out.append({"source": "here", "kind": "notice", "place": None,
                    "words": f"HERE notice: {n.get('title') or n.get('code') or 'a restriction HERE could not keep to'}",
                    "detail": f"code {n.get('code')}, severity {n.get('severity')}", "grade": "grey",
                    "lon": geometry[0][0] if geometry else None, "lat": geometry[0][1] if geometry else None, "offset": 0})
    return out


def _numbered(cands):
    for i, c in enumerate(cands):
        c["id"] = f"P{i + 1}"
    return cands


# --------------------------------------------------------------------------- #
#  The bake                                                                    #
# --------------------------------------------------------------------------- #
#: the route's columns, written whole in ONE literal statement (the tenant audit reads statements as text; a SET list
#: built at run time would hide the WHERE from it). _ROUTE_COLS is asserted to be exactly what the literal names.
_ROUTE_COLS = ("via_json", "geometry_json", "return_geometry_json", "distance_km", "duration_hr", "baked_at", "bake_error",
               "here_notices_json", "actions_json", "roads_json", "limits_hits_json", "limits_checked_at", "pinch_json",
               "updated_by", "updated_at")
_ROUTE_UPDATE = (
    "UPDATE abnormal_loads SET via_json = ?, geometry_json = ?, return_geometry_json = ?, distance_km = ?, "
    "duration_hr = ?, baked_at = ?, bake_error = ?, here_notices_json = ?, actions_json = ?, roads_json = ?, "
    "limits_hits_json = ?, limits_checked_at = ?, pinch_json = ?, updated_by = ?, updated_at = ? "
    "WHERE tenant_id = ? AND id = ?"
)
assert re.findall(r"(\w+) = \?", _ROUTE_UPDATE) == list(_ROUTE_COLS) + ["tenant_id", "id"]


def _store(movement_id, vals):
    """Write the route columns whole: the row's current values with `vals` laid over them."""
    rows = db.query("SELECT * FROM abnormal_loads WHERE tenant_id = ? AND id = ?", (db.current_tenant(), movement_id))
    cur = dict(rows[0]) if rows else {}
    merged = {k: cur.get(k) for k in _ROUTE_COLS}
    merged.update({k: v for k, v in vals.items() if k in _ROUTE_COLS})
    db.execute(_ROUTE_UPDATE, [merged[k] for k in _ROUTE_COLS] + [db.current_tenant(), movement_id])


def typed_rows(m):
    """The planner's own pinch-point rows (phase 3), kept across re-bakes."""
    raw = m.get("pinch") if "pinch" in m else m.get("pinch_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    rows = [c for c in (raw or []) if isinstance(c, dict) and c.get("source") == "typed"]
    for i, t in enumerate(rows):
        t["id"] = t.get("id") or f"T{i + 1}"
    return rows


def bake(movement_id, by=None, _routes=None, _limits=None):
    """
    Route one movement at its typed size and store the line, HERE's words and the candidates. `_routes` (tests)
    replaces here_routing.routes. Returns {ok, movement_id, distance_km, duration_hr, candidates, notes} or
    {ok: False, error}. A failure is stored on the movement (bake_error) and returned, never raised.
    """
    import abnormal
    m = abnormal.get(movement_id)
    if not m:
        return {"ok": False, "error": "no such abnormal load"}
    call = _routes or here_routing.routes
    if _routes is None and not here_routing.configured():
        err = "HERE_API_KEY is not set on this deployment, so no line can be drawn"
        _store(movement_id, {"bake_error": err, "baked_at": _now()})
        return {"ok": False, "error": err}
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    try:
        gbl = gates.gates_by_location()
    except Exception:
        gbl = {}
    a, b, problem = ends(m, locs, gbl)
    if problem:
        _store(movement_id, {"bake_error": problem, "baked_at": _now()})
        return {"ok": False, "error": problem}
    params, notes = vehicle_params(m)
    via = via_points(m)
    try:
        opts = call(a["lat"], a["lon"], b["lat"], b["lon"], None, vehicle=params, extras=dict(EXTRAS), via=via or None, alternatives=1)
    except Exception as e:  # noqa: BLE001 — the answer is the error, stored on the movement
        err = f"HERE could not draw the line: {str(e)[:240]}"
        _store(movement_id, {"bake_error": err, "baked_at": _now()})
        return {"ok": False, "error": err}
    best = opts[0]
    geometry, actions, spans = _join_sections(best.get("sections") or [{"geometry": best.get("geometry")}])
    if not geometry:
        geometry = best.get("geometry") or []
    notices = [n for part in (best.get("sections") or []) for n in (part.get("notices") or [])]
    notices += [n for s in spans for n in (s.get("notices") or [])]
    roads = roads_in_words(spans)
    here_c = candidates_from_actions(actions, geometry, m, spans)
    bend_c = bends(geometry, m, spans, taken_points=[[c["lon"], c["lat"]] for c in here_c if c.get("lon") is not None])
    hits = limits.check_line(geometry, load_dims(m), label="the load", _limits=_limits)
    cands = _numbered(notice_candidates(notices, geometry) + here_c + bend_c + limit_candidates(hits))
    typed = typed_rows(m)
    for i, t in enumerate(typed):
        t["id"] = t.get("id") or f"T{i + 1}"
    ret_geom, ret_notes = None, []
    if m.get("return_abnormal"):
        try:
            back = call(b["lat"], b["lon"], a["lat"], a["lon"], None, vehicle=params, extras=dict(EXTRAS),
                        via=list(reversed(via)) or None, alternatives=1)
            rg, _, _ = _join_sections(back[0].get("sections") or [{"geometry": back[0].get("geometry")}])
            ret_geom = rg or back[0].get("geometry")
        except Exception as e:  # noqa: BLE001
            ret_notes.append(f"the return leg could not be drawn: {str(e)[:160]}")
    compact_actions = [{k: a2.get(k) for k in ("action", "direction", "severity", "exit", "offset", "length", "duration", "instruction") if k in a2}
                       for a2 in actions]
    _store(movement_id, {
        "geometry_json": json.dumps(geometry), "return_geometry_json": json.dumps(ret_geom) if ret_geom else None,
        "distance_km": best.get("distance_km"), "duration_hr": best.get("duration_hr"),
        "baked_at": _now(), "bake_error": None,
        "here_notices_json": json.dumps({"notices": notices, "notes": notes + ret_notes, "via": via, "has_motorway": has_motorway(roads)}),
        "actions_json": json.dumps(compact_actions), "roads_json": json.dumps(roads),
        "limits_hits_json": json.dumps(hits), "limits_checked_at": _now(),
        "pinch_json": json.dumps(cands + typed), "updated_by": by, "updated_at": _now(),
    })
    return {"ok": True, "movement_id": movement_id, "distance_km": best.get("distance_km"), "duration_hr": best.get("duration_hr"),
            "points": len(geometry), "candidates": len(cands), "limit_hits": len(hits), "exceeds": len([h for h in hits if h["verdict"] == "exceeds"]),
            "notices": len(notices), "roads": roads_sentence(roads), "notes": notes + ret_notes, "return_drawn": bool(ret_geom)}


def set_via(movement_id, points, by=None):
    probs = via_problems(points)
    if probs:
        return {"ok": False, "problems": probs}
    clean = [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in points]
    _store(movement_id, {"via_json": json.dumps(clean) if clean else None, "updated_by": by, "updated_at": _now()})
    return {"ok": True, "via": clean}


def clear_route(movement_id, by=None):
    """A changed end or size makes the stored line stale: drop it (the typed pinch rows stay)."""
    import abnormal
    m = abnormal.get(movement_id)
    typed = typed_rows(m) if m else []
    _store(movement_id, {"geometry_json": None, "return_geometry_json": None, "distance_km": None, "duration_hr": None,
                         "baked_at": None, "bake_error": None, "here_notices_json": None, "actions_json": None, "roads_json": None,
                         "limits_hits_json": None, "limits_checked_at": None, "pinch_json": json.dumps(typed) if typed else None,
                         "updated_by": by, "updated_at": _now()})


PINCH_TEXT_MAX = 400


def pinch_problems(rows, found_ids=()):
    """Why a pinch-point list cannot be saved. A row naming a found candidate (its P… id) changes only the grade and a note;
    a typed row (the planner's own) carries kind, place, words, grade, note, owner, measure, permit, works, link."""
    if not isinstance(rows, list):
        return ["the pinch points must be a list"]
    if len(rows) > 200:
        return ["at most 200 pinch points"]
    p = []
    found = set(found_ids or ())
    for i, r in enumerate(rows):
        n = i + 1
        if not isinstance(r, dict):
            p.append(f"row {n}: not an object")
            continue
        if r.get("grade") not in (None, "") and r.get("grade") not in GRADES:
            p.append(f"row {n}: the grade must be one of " + ", ".join(GRADES))
        src = "found" if r.get("id") in found else (r.get("source") or "typed")
        if src == "typed":
            if r.get("kind") not in (None, "") and r.get("kind") not in KIND_WORDS:
                p.append(f"row {n}: the kind must be one of " + ", ".join(KIND_WORDS))
            if not str(r.get("words") or r.get("place") or "").strip():
                p.append(f"row {n}: say where or what the pinch point is")
        for k in ("place", "words", "note", "owner", "measure", "permit", "works", "link"):
            if r.get(k) is not None and len(str(r.get(k))) > PINCH_TEXT_MAX:
                p.append(f"row {n}: {k} is too long (at most {PINCH_TEXT_MAX} characters)")
    return p


def set_pinch(movement_id, rows, by=None):
    """Write the grades (and notes) the planner set on the found candidates, and the planner's own rows whole."""
    import abnormal
    m = abnormal.get(movement_id)
    if not m:
        return {"ok": False, "error": "no such abnormal load"}
    try:
        cur = json.loads(m.get("pinch_json") or "[]")
    except Exception:
        cur = []
    found = {c.get("id"): c for c in cur if isinstance(c, dict) and c.get("source") != "typed"}
    probs = pinch_problems(rows, found_ids=found.keys())
    if probs:
        return {"ok": False, "problems": probs}
    sent = {r.get("id"): r for r in rows if isinstance(r, dict) and r.get("id") in found}
    out = []
    for cid, c in found.items():
        r = sent.get(cid)
        if r:
            c = dict(c, grade=(r.get("grade") or c.get("grade") or "grey"), note=(str(r.get("note")).strip() or None) if r.get("note") is not None else c.get("note"))
        out.append(c)
    typed = []
    for r in rows:
        if not isinstance(r, dict) or r.get("id") in found or (r.get("source") or "typed") != "typed":
            continue
        typed.append({"id": r.get("id") or "", "source": "typed", "kind": r.get("kind") or "other", "place": (str(r.get("place")).strip() or None) if r.get("place") else None,
                      "words": (str(r.get("words")).strip() or None) if r.get("words") else None, "grade": r.get("grade") or "grey",
                      "note": (str(r.get("note")).strip() or None) if r.get("note") else None,
                      "owner": (str(r.get("owner")).strip() or None) if r.get("owner") else None,
                      "measure": (str(r.get("measure")).strip() or None) if r.get("measure") else None,
                      "permit": (str(r.get("permit")).strip() or None) if r.get("permit") else None,
                      "works": (str(r.get("works")).strip() or None) if r.get("works") else None,
                      "link": (str(r.get("link")).strip() or None) if r.get("link") else None,
                      "lon": r.get("lon") if isinstance(r.get("lon"), (int, float)) else None,
                      "lat": r.get("lat") if isinstance(r.get("lat"), (int, float)) else None})
    for i, t in enumerate(typed):
        t["id"] = f"T{i + 1}"
    _store(movement_id, {"pinch_json": json.dumps(out + typed), "updated_by": by, "updated_at": _now()})
    return {"ok": True, "pinch": out + typed}


#: the typed fields whose change makes a stored line stale
ROUTE_FIELDS = ("origin_id", "origin_gate_id", "dest_id", "dest_gate_id", "width_m", "height_m", "length_m", "gross_t",
                "max_axle_t", "axle_count", "return_abnormal")


# --------------------------------------------------------------------------- #
#  The map's collections                                                        #
# --------------------------------------------------------------------------- #
def feature_collection(movements, public=False):
    """
    The abnormal loads as GeoJSON: one LineString per drawn leg, and (staff only) one Point per candidate. `movements`
    are decorated rows (abnormal.decorate). Public (D68): approved-or-later only, the words a visitor may read — no
    haulier, no value, no references, no pinch points; the band never the hour.
    """
    feats = []
    for m in movements:
        if public and not m.get("public"):
            continue
        geom = m.get("geometry")
        if not geom:
            continue
        adv = m.get("advice") or {}
        base = {"id": m["id"], "name": m.get("name"), "status": m.get("status"), "status_word": m.get("status_word"),
                "date_from": m.get("date_from"), "date_to": m.get("date_to"), "time_band": m.get("time_band"),
                "movements": m.get("movements"), "escorted": (m.get("escort_planned") or "none") != "none",
                "class_word": adv.get("summary"), "roads": roads_sentence(m.get("roads") or []),
                "indicative": INDICATIVE_WORDS, "distance_km": m.get("distance_km")}
        if public:
            base = {k: base[k] for k in ("id", "name", "date_from", "date_to", "time_band", "movements", "escorted", "roads", "indicative")}
            base["kind"] = "Abnormal load"
            base["public_words"] = "Indicative route; the agreed route may differ."
        else:
            base.update({"team_name": m.get("team_name"), "size": f"{m.get('width_m')} × {m.get('height_m')} × {m.get('length_m')} m · {m.get('gross_t')} t",
                         "candidates": len([c for c in (m.get("pinch") or []) if c.get("source") != "typed"]),
                         "typed_points": len([c for c in (m.get("pinch") or []) if c.get("source") == "typed"]),
                         "flags": [f.get("code") for f in (m.get("flags") or [])], "baked_at": m.get("baked_at")})
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": geom}, "properties": dict(base, leg="loaded")})
        if m.get("return_geometry"):
            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": m["return_geometry"]}, "properties": dict(base, leg="return")})
        if not public:
            for c in m.get("pinch") or []:
                if c.get("lon") is None or c.get("lat") is None:
                    continue
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                              "properties": {"movement_id": m["id"], "movement": m.get("name"), "pinch_id": c.get("id"), "source": c.get("source"),
                                             "kind": c.get("kind"), "kind_word": KIND_WORDS.get(c.get("kind"), c.get("kind")), "place": c.get("place"),
                                             "words": c.get("words"), "detail": c.get("detail"), "grade": c.get("grade") or "grey",
                                             "grade_word": GRADE_WORDS.get(c.get("grade") or "grey")}})
    return {"type": "FeatureCollection", "features": feats,
            "words": {"indicative": INDICATIVE_WORDS, "candidates": None if public else CANDIDATE_WORDS,
                      "counted_apart": "Counted apart from the lorries: not in the movement counts, the heat map or the carbon figures."},
            "grades": [{"key": k, "word": GRADE_WORDS[k]} for k in GRADES] if not public else None,
            "count": len({f["properties"].get("id") for f in feats if f["geometry"]["type"] == "LineString"})}
