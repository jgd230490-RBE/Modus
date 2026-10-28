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
              "limit": "Signed limit", "notice": "Routing notice", "bridge": "Bridge", "railway": "Railway crossed",
              "level_crossing": "Level crossing", "calming": "Traffic calming", "overhead": "Overhead line",
              "width": "Narrow road", "junction": "Junction", "furniture": "Street furniture", "other": "Other"}
INDICATIVE_WORDS = ("Indicative line, drawn for the load's size. The haulier's ESDAL route and route survey govern; "
                    "structures are checked by their owners through ESDAL.")
#: 28 Oct 2026 (the user: no supplier or back-end words on a screen): the one line under the pinch-point table — the old
#: two (this and STRUCTURES_WORDS, 75 words naming OpenStreetMap, the community layer and Fetch now) made one. What is not
#: worked out (structure ratings, swept paths, clearances) is in the user guide, chapter 14.
CANDIDATE_WORDS = ("Found from the route's turns and bends, the signed limits and the bridges, railways, overhead lines, crossings and "
                   "traffic calming on the map. Each starts Grey; the route survey decides.")
_ORD = {1: "1st", 2: "2nd", 3: "3rd"}

# --------------------------------------------------------------------------- #
#  28 Oct 2026 (the user, 22 Oct: "no info about api or backend stuff" on a     #
#  screen; supplier names only in the technical guide): the sentences the page  #
#  prints when a line is capped or not drawn, and plain_*() — the same words for #
#  what an older version SAVED on a movement (pinch_json, here_notices_json,     #
#  bake_error), applied as the page reads it, so nothing needs drawing again.   #
# --------------------------------------------------------------------------- #
NOT_SET_UP = "The line could not be drawn: route drawing is not set up here."
JUST_NOW = "The line could not be drawn just now. Try again in a minute."
RETURN_JUST_NOW = "The return leg could not be drawn just now."
NO_MAP_DATA = "no map data yet. Fetch it on Config → Map and bulletin, then check again."
#: what no screen of this page may say (the guard in tests/test_abnormal.py and parse_frontend.js uses the same list)
SCREEN_BAN = re.compile(r"\bHERE\b|OpenStreetMap|\bOSM\b|Mapbox|GOV\.UK|gov\.uk|NaPTAN|\bGIAS\b|STATS19|\bDfT\b|Geofabrik|"
                        r"Fetch now|routing key|community layer|severity|router|\bE\d{6}\b")


def cap_note(key, most, typed):
    """A load bigger than the router can take: the line is drawn at the most it takes, and the row says so."""
    return f"Drawn for a {key} of {most:g} m, the most a line can be drawn for; the load is {typed:g} m."


_OLD_CAP = re.compile(r"^HERE takes a (\w+) of at most ([\d.]+) m: the line is drawn for [\d.]+ m, the load is ([\d.]+) m$")
_OLD_SOURCE = re.compile(r"\s*\(OpenStreetMap(?: as fetched [0-9-]+)?\)")


def plain_note(n):
    """A route note as the page prints it (an older version's words reworded)."""
    t = str(n or "")
    m = _OLD_CAP.match(t)
    if m:
        return cap_note(m.group(1), float(m.group(2)), float(m.group(3)))
    if t.startswith("the return leg could not be drawn"):
        return RETURN_JUST_NOW
    return t


def plain_bake_error(e):
    """Why the line is not drawn, as one sentence (never the supplier's raw answer)."""
    if not e:
        return e
    t = str(e)
    if t in (NOT_SET_UP, JUST_NOW) or t.startswith("The line could not be drawn"):
        return t
    if "routing key" in t:
        return NOT_SET_UP
    if t.startswith("the line could not be drawn"):
        return JUST_NOW
    return f"The line could not be drawn: {t.rstrip('.')}."


def plain_candidate(c):
    """A found pinch point as the page prints it: an older version's detail reworded (a copy; the saved row is untouched)."""
    if not isinstance(c, dict):
        return c
    c = dict(c)
    d = c.get("detail")
    if d:
        d = str(d)
        if "turn severity" in d or re.match(r"^code .*, severity ", d):
            d = None
        elif d.startswith("straight over each"):
            d = "straight over each"
        else:
            d = _OLD_SOURCE.sub("", d)
            d = d.replace("tagged in OpenStreetMap on the road; the sign on the road is what counts, and the stored signed limits are checked apart",
                          "marked on the map; the sign on the road is what counts")
            d = d.replace("tagged in OpenStreetMap on a barrier", "marked on the map")
        c["detail"] = d
    w = c.get("words")
    if w and c.get("kind") == "notice":
        c["words"] = re.sub(r"^Routing notice: [A-Z0-9_]+$", "Routing notice: a restriction the route could not keep to", str(w))
    return c


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
            notes.append(cap_note(key, HERE_MAX_CM[key] / 100, v))
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
        if kind == "turn":
            # 28 Oct 2026: the router's severity word stays in actions_json, never on a screen (technical guide T1)
            k, words = "turn", f"Turn {a.get('direction') or ''} onto {road}".replace("  ", " ") if road else f"Turn {a.get('direction') or ''}".strip()
            detail = None
        elif kind == "uTurn":
            k, words, detail = "turn", f"U-turn{(' at ' + road) if road else ''}", None
        elif kind == "roundaboutExit":
            k, words = "roundabout", f"Roundabout: {_ordinal(a.get('exit'))} exit" + (f" onto {road}" if road else "")
            detail = None
        elif kind == "roundaboutPass":
            mm = re.search(r"Pass (\d+) roundabouts?", a.get("instruction") or "")
            n = mm.group(1) if mm else "several"
            k, words, detail = "roundabout", f"Passes {n} roundabouts" + (f" on {road}" if road else ""), "straight over each"
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
                    "words": f"Routing notice: {n.get('title') or 'a restriction the route could not keep to'}",
                    "detail": None, "grade": "grey",
                    "lon": geometry[0][0] if geometry else None, "lat": geometry[0][1] if geometry else None, "offset": 0})
    return out

# --------------------------------------------------------------------------- #
#  22 Oct 2026 (phase 3): the structures and limits along the road, from OpenStreetMap — the community layer's
#  second pass (community_sources.osm_structures_extract, source "osm_structures"), read along the drawn line.
#  A bridge the road is carried on, a railway or an overhead line the line crosses, a level crossing, traffic
#  calming, a signed limit tagged on the road or a height restrictor. Every one is a Grey candidate: OpenStreetMap is
#  as complete as its mappers, and the survey decides.
# --------------------------------------------------------------------------- #
STRUCT_NEAR_M = 20.0      # a crossing, a calming feature or a height restrictor this close to the line is on the road
STRUCT_ALONG_M = 12.0     # a bridge or a tagged limit whose way has a vertex this close is the road the line follows
STRUCT_PAD_M = 60.0       # the stored features are read for the line's bbox plus this
LIMIT_WORDS = {"maxheight": ("height", "m"), "maxwidth": ("width", "m"), "maxweight": ("gross weight", "t"),
               "maxaxleload": ("heaviest axle", "t"), "maxlength": ("length", "m")}
LIMIT_NEAR = {"maxheight": 0.3, "maxwidth": 0.3, "maxweight": 0.10, "maxaxleload": 0.10, "maxlength": 1.0}   # m, m, share, share, m
#: 28 Oct 2026: the staff map's and the feature collection's line about the map rows (was: OpenStreetMap, the community
#: layer's extract, Config → Map and bulletin → Fetch now). The page itself prints CANDIDATE_WORDS only.
STRUCTURES_WORDS = ("Bridges, railways, overhead lines, crossings, traffic calming and limits marked on the map along the line. "
                    "Not every road is fully mapped: the survey decides.")
_FT_IN = re.compile(r"""^\s*(\d+)\s*'\s*(\d+(?:\.\d+)?)?\s*"?\s*$""")


def _parse_detail(detail):
    """community_sources.structure_detail back into a dict."""
    out = {}
    for part in str(detail or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num_tag(v):
    """An OpenStreetMap limit value as a number: '4.2', '4.2 m', '13'6"', '7.5 t', '7,5', '132000'; None for none /
    default / words. Feet and inches, kilograms and pounds come back in metres and tonnes."""
    if v is None:
        return None
    t = str(v).strip().lower()
    if not t or t in ("none", "default", "unsigned", "no", "below_default", "yes"):
        return None
    m = _FT_IN.match(t)
    if m:
        return round(int(m.group(1)) * 0.3048 + float(m.group(2) or 0) * 0.0254, 2)
    m = re.match(r"^(\d+(?:[.,]\d{1,2})?)\s*(m|t|tonnes?|tons?|lbs?|kg|ft|kv)?\b", t)
    if not m:
        return None
    x = float(m.group(1).replace(",", "."))
    unit = m.group(2) or ""
    if unit == "ft":
        return round(x * 0.3048, 2)
    if unit == "kv":
        return x * 1000.0
    if unit == "kg":
        return round(x / 1000.0, 2)
    if unit in ("lb", "lbs"):
        return round(x * 0.000453592, 2)
    return x


def _kv(v):
    """'132000' → '132 kV'; '400000,275000' → '400 kV' (the highest); None when unreadable."""
    best = None
    for part in str(v or "").split(","):
        n = _num_tag(part)
        if n is not None and (best is None or n > best):
            best = n
    if best is None:
        return None
    return f"{best / 1000:g} kV" if best >= 1000 else f"{best:g} V"


def _proj(geometry):
    lat = (sum(c[1] for c in geometry) / len(geometry)) if geometry else 52.0
    return 111320.0 * math.cos(math.radians(lat)), 110574.0


def _xy(c, k):
    return (c[0] * k[0], c[1] * k[1])


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _seg_meet(p1, p2, q1, q2):
    d = (p2[0] - p1[0]) * (q2[1] - q1[1]) - (p2[1] - p1[1]) * (q2[0] - q1[0])
    if abs(d) < 1e-9:
        return None
    t = ((q1[0] - p1[0]) * (q2[1] - q1[1]) - (q1[1] - p1[1]) * (q2[0] - q1[0])) / d
    u = ((q1[0] - p1[0]) * (p2[1] - p1[1]) - (q1[1] - p1[1]) * (p2[0] - p1[0])) / d
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))
    return None


class _Line:
    """The load's line in metres (a local equirectangular projection) with a cell grid of its segments, so a county's
    features are tested quickly."""
    CELL = 300.0

    def __init__(self, geometry):
        self.k = _proj(geometry)
        self.xy = [_xy(c, self.k) for c in geometry]
        self.grid = {}
        for i, (a, b) in enumerate(zip(self.xy, self.xy[1:])):
            for gx in range(int(min(a[0], b[0]) // self.CELL) - 1, int(max(a[0], b[0]) // self.CELL) + 2):
                for gy in range(int(min(a[1], b[1]) // self.CELL) - 1, int(max(a[1], b[1]) // self.CELL) + 2):
                    self.grid.setdefault((gx, gy), []).append(i)

    def near_m(self, c):
        """Metres from a point to the line (None when no segment is within a cell of it)."""
        p = _xy(c, self.k)
        best = None
        for i in self.grid.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            d = _pt_seg(p, self.xy[i], self.xy[i + 1])
            best = d if best is None or d < best else best
        return best

    def cross(self, coords):
        """Where a way first crosses the line, as (lon, lat); None when it does not."""
        for q1, q2 in zip(coords, coords[1:]):
            Q1, Q2 = _xy(q1, self.k), _xy(q2, self.k)
            cells = set()
            for gx in range(int(min(Q1[0], Q2[0]) // self.CELL), int(max(Q1[0], Q2[0]) // self.CELL) + 1):
                for gy in range(int(min(Q1[1], Q2[1]) // self.CELL), int(max(Q1[1], Q2[1]) // self.CELL) + 1):
                    cells.update(self.grid.get((gx, gy), ()))
            for i in sorted(cells):
                pt = _seg_meet(self.xy[i], self.xy[i + 1], Q1, Q2)
                if pt:
                    return (pt[0] / self.k[0], pt[1] / self.k[1])
        return None

    def along(self, coords):
        """The first vertex of a way that lies on the line (within STRUCT_ALONG_M), as (lon, lat); None when the way
        is not the road the line follows."""
        for c in coords:
            d = self.near_m(c)
            if d is not None and d <= STRUCT_ALONG_M:
                return (c[0], c[1])
        return None


def _limit_words(tags, dims):
    """'maxheight 4.2 m: the load's height 4.3 m is over it' for each tagged limit the load is over or close to
    (LIMIT_NEAR); '' when none applies."""
    parts = []
    for tag, (what, unit) in LIMIT_WORDS.items():
        lim, have = _num_tag(tags.get(tag)), dims.get(tag)
        if lim is None or have is None:
            continue
        near = LIMIT_NEAR[tag]
        margin = lim * near if unit == "t" else near
        if have > lim:
            parts.append(f"{tag} {lim:g} {unit}: the load's {what} {have:g} {unit} is over it")
        elif have > lim - margin:
            parts.append(f"{tag} {lim:g} {unit}: the load's {what} {have:g} {unit} is within {margin:g} {unit} of it")
    return "; ".join(parts)


def _bbox(geometry, pad_m=STRUCT_PAD_M):
    kx, ky = _proj(geometry)
    return [min(c[0] for c in geometry) - pad_m / kx, min(c[1] for c in geometry) - pad_m / ky,
            max(c[0] for c in geometry) + pad_m / kx, max(c[1] for c in geometry) + pad_m / ky]


def _stored_structures(geometry):
    try:
        import community
        return community.structures(bbox=_bbox(geometry))
    except Exception:       # noqa: BLE001 — a copy without the table, or no fetch yet: no structure candidates
        return []


def _structures_fetched():
    try:
        import community
        return community.structures_fetched_at()
    except Exception:       # noqa: BLE001
        return None


def structure_candidates(geometry, m, feats, fetched=None):
    """OpenStreetMap's structures and limits (community.structures) along the drawn line as candidates (source 'osm'),
    each Grey: a bridge carrying the road (a vertex on the line), a railway or an overhead line crossed (a segment
    meeting the line), a level crossing / traffic calming / height restrictor within STRUCT_NEAR_M, a tagged limit the
    load is over or close to. `fetched` (ISO) dates the words."""
    if not geometry or len(geometry) < 2 or not feats:
        return []
    L = _Line(geometry)
    dims = {"maxheight": rules._num(m.get("height_m")), "maxwidth": rules._num(m.get("width_m")),
            "maxweight": rules._num(m.get("gross_t")), "maxaxleload": rules._num(m.get("max_axle_t")),
            "maxlength": rules._num(m.get("length_m"))}
    # 28 Oct 2026 (the user: no supplier names on a screen): the details no longer end "(OpenStreetMap as fetched …)";
    # `fetched` stays in the signature (the callers pass it) and the source is named in the technical guide, T1
    when = ""
    out = []
    for f in feats:
        g = f.get("geometry") or {}
        kind, tags, name = f.get("kind"), _parse_detail(f.get("detail")), f.get("name")
        road = tags.get("name") or tags.get("ref")
        if g.get("type") == "Point":
            c = g.get("coordinates") or []
            if len(c) < 2:
                continue
            d = L.near_m(c)
            if d is None or d > STRUCT_NEAR_M:
                continue
            lon, lat = c[0], c[1]
            if kind == "s_level_crossing":
                k, words = "level_crossing", "Level crossing" + (f": {name}" if name else "")
                detail = ("Network Rail's level crossing: a long or low load needs its say (grounding on the crossing, "
                          "the time spent on it)" + when)
            elif kind == "s_calming":
                t = (tags.get("traffic_calming") or "").replace("_", " ")
                k, words = "calming", f"Traffic calming ({t})" + (f" on {road}" if road else "")
                detail = "a low loader can ground on a hump, cushion or table; an island or a chicane narrows the road" + when
            elif kind == "s_limit":
                over = _limit_words(tags, dims)
                if not over:
                    continue
                k = "limit"
                words = ("Height restrictor" if tags.get("barrier") == "height_restrictor" else "Signed limit") + (f" at {name}" if name else "") + ": " + over
                detail = "marked on the map; the sign on the road is what counts" + when
            else:
                continue
        elif g.get("type") == "LineString":
            coords = g.get("coordinates") or []
            if len(coords) < 2:
                continue
            if kind in ("s_rail", "s_power"):
                pt = L.cross(coords)
                if not pt:
                    continue
                lon, lat = pt
                if kind == "s_rail":
                    where = ("the railway is carried over the road on a bridge: a height question for the load"
                             if tags.get("bridge") not in (None, "no") else
                             "the railway passes under the road in a tunnel" if tags.get("tunnel") not in (None, "no") else
                             "whether the railway passes over or under the road is the survey's question")
                    k, words = "railway", "Railway crossed" + (f": {name}" if name else "")
                    detail = "Network Rail: notice where a load goes over or under its structure (the aide memoire); " + where + when
                else:
                    volts = _kv(tags.get("voltage"))
                    k, words = "overhead", "Overhead line crossed" + (f" ({volts})" if volts else "")
                    detail = ("the line's owner (the distribution network operator, or National Grid at 275 / 400 kV) sets "
                              "the clearance under it for the travelling height" + when)
            elif kind in ("s_bridge", "s_limit"):
                pt = L.along(coords)
                if not pt:
                    continue
                lon, lat = pt
                over = _limit_words(tags, dims)
                if kind == "s_bridge":
                    k, words = "bridge", "Bridge carrying the road" + (f": {name}" if name else "") + (f" ({tags['bridge:structure']})" if tags.get("bridge:structure") else "")
                    detail = ("the structure's owner assesses it for the load's weight through ESDAL (the road and bridge "
                              "authority's notice)" + (f"; signed {over}" if over else "") + when)
                else:
                    if not over:
                        continue
                    k, words = "limit", "Signed limit" + (f" on {road}" if road else "") + ": " + over
                    detail = "marked on the map; the sign on the road is what counts" + when
            else:
                continue
        else:
            continue
        out.append({"source": "osm", "kind": k, "place": name or road, "words": words, "detail": detail, "grade": "grey",
                    "lon": round(lon, 6), "lat": round(lat, 6), "offset": None, "ref": f.get("source_ref")})
    return out


def _carry_grades(old, new):
    """A grade (and a note) the planner set on a found candidate survives a re-bake or a structures check when the
    same candidate is found again: the same source, kind and place (the OSM object, else the point and the words)."""
    def key(c):
        return (c.get("source"), c.get("kind"), c.get("ref") or (round(float(c.get("lon") or 0), 5), round(float(c.get("lat") or 0), 5), c.get("words")))
    prev = {key(c): c for c in (old or []) if isinstance(c, dict) and c.get("source") != "typed"}
    for c in new:
        o = prev.get(key(c))
        if o:
            if o.get("grade") in GRADES:
                c["grade"] = o["grade"]
            if o.get("note"):
                c["note"] = o["note"]
    return new


def _stored_candidates(m):
    try:
        cur = json.loads(m.get("pinch_json") or "[]")
    except Exception:
        cur = []
    return [c for c in cur if isinstance(c, dict) and c.get("source") != "typed"]


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


def bake(movement_id, by=None, _routes=None, _limits=None, _structures=None, _fetched=None):
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
        err = NOT_SET_UP
        _store(movement_id, {"bake_error": err, "baked_at": _now()})
        return {"ok": False, "error": err}
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    try:
        gbl = gates.gates_by_location()
    except Exception:
        gbl = {}
    a, b, problem = ends(m, locs, gbl)
    if problem:
        problem = plain_bake_error(problem)
        _store(movement_id, {"bake_error": problem, "baked_at": _now()})
        return {"ok": False, "error": problem}
    params, notes = vehicle_params(m)
    via = via_points(m)
    try:
        opts = call(a["lat"], a["lon"], b["lat"], b["lon"], None, vehicle=params, extras=dict(EXTRAS), via=via or None, alternatives=1)
    except Exception as e:  # noqa: BLE001 — the answer is the error, stored on the movement
        print(f"🚧 abnormal route {movement_id}: the router refused: {str(e)[:400]}", flush=True)   # the raw answer: the log only
        err = JUST_NOW
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
    feats = _structures if _structures is not None else _stored_structures(geometry)
    fetched = _fetched if _structures is not None else _structures_fetched()
    struct_c = structure_candidates(geometry, m, feats, fetched=fetched)
    cands = _carry_grades(_stored_candidates(m), _numbered(notice_candidates(notices, geometry) + here_c + bend_c + struct_c + limit_candidates(hits)))
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
            print(f"🚧 abnormal route {movement_id}: the return leg was refused: {str(e)[:400]}", flush=True)
            ret_notes.append(RETURN_JUST_NOW)
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
            "notices": len(notices), "roads": roads_sentence(roads), "notes": notes + ret_notes, "return_drawn": bool(ret_geom),
            "structures": len(struct_c), "structures_fetched": fetched}


def check_structures(movement_id, by=None, _structures=None, _fetched=None):
    """
    22 Oct 2026 (phase 3): look again along the DRAWN line for OpenStreetMap's structures and limits — no HERE call —
    after a Fetch now on Config → Map and bulletin. The HERE candidates, the bends and the signed-limit hits stay as
    they are; the structure candidates are found afresh, numbered in their place (before the signed limits), and a
    grade or note set on one found again is kept.
    """
    import abnormal
    m = abnormal.get(movement_id)
    if not m:
        return {"ok": False, "error": "no such abnormal load"}
    try:
        geometry = json.loads(m.get("geometry_json") or "null")
    except Exception:
        geometry = None
    if not geometry:
        return {"ok": False, "error": "draw the route first: the structures are looked for along the drawn line"}
    feats = _structures if _structures is not None else _stored_structures(geometry)
    fetched = _fetched if _structures is not None else _structures_fetched()
    found = _stored_candidates(m)
    if not feats and not fetched:
        # nothing has been fetched for the scheme yet: there is nothing to check against, so what was found before (and
        # any grade on it) stays; the note says where Fetch now is
        return {"ok": True, "movement_id": movement_id, "structures": sum(1 for c in found if c.get("source") == "osm"),
                "candidates": len(found), "structures_fetched": None,
                "note": NO_MAP_DATA}
    keep = [c for c in found if c.get("source") != "osm"]
    before = [c for c in keep if c.get("source") != "limits"]
    after = [c for c in keep if c.get("source") == "limits"]
    struct_c = structure_candidates(geometry, m, feats, fetched=fetched)
    cands = _carry_grades(found, _numbered(before + struct_c + after))
    _store(movement_id, {"pinch_json": json.dumps(cands + typed_rows(m)), "updated_by": by, "updated_at": _now()})
    return {"ok": True, "movement_id": movement_id, "structures": len(struct_c), "candidates": len(cands), "structures_fetched": fetched,
            "note": None if fetched else NO_MAP_DATA}


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
def _nw(x):
    """A typed figure in words: 40.0 -> 40, 4.6 -> 4.6, None -> — (the map popup read '40.0 t' on the local copy, 22 Oct)."""
    v = rules._num(x)
    if v is None:
        return "—"
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


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
            base.update({"team_name": m.get("team_name"), "size": f"{_nw(m.get('width_m'))} × {_nw(m.get('height_m'))} × {_nw(m.get('length_m'))} m · {_nw(m.get('gross_t'))} t",
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
                      "structures": None if public else STRUCTURES_WORDS,
                      "counted_apart": "Counted apart from the lorries: not in the movement counts, the heat map or the carbon figures."},
            "grades": [{"key": k, "word": GRADE_WORDS[k]} for k in GRADES] if not public else None,
            "count": len({f["properties"].get("id") for f in feats if f["geometry"]["type"] == "LineString"})}
