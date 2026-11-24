"""
A fair count of community places and cycle routes for every option (16 Nov 2026, step 2 of the best-option work;
branch claude/community-all-options; notes/session-1116-community-all-options.md).

John, 16 Nov: places and cycle routes count toward a route's best option only once the alternatives' counts are fair.
Until now a Fetch now fetched the community layer (which holds the cycle routes too) along the main routes and the
diversions in use only, so an alternative that leaves the main route by more than 250 m read LOW.

WHAT IS ASSERTED
  1. The strip: a Fetch now's strip covers an alternative that leaves the main route; a way round a closed zone
     (alt_index 10+) stays out unless a diversion uses it; strip_from_db() with no argument is still the narrow strip.
  2. status()["all_options"]: False before any fetch, True after a fetch along every option, False after a narrow
     fetch, after a re-route, after a new option and after a diversion takes up a way round; True again after the
     next wide fetch; Make primary (a swap of numbers) and a dropped option leave it True.
  3. Slices: the OpenStreetMap passes cut into slices keep exactly what one pass keeps, at the same nearest distance
     (an outline crossed by a line of one slice only is in at 0 m); a slice that fails fails its source, which keeps its
     old features and its old record, so "all_options" stays False after a narrow layer.
  4. Source: Fetch now asks for every option by default; the lock with the collision fetch is kept; the route
     comparison's under-count warning and the technical guide say what is now true.

WHAT THIS DOES NOT PROVE
  * Geofabrik, GIAS and NaPTAN are NOT called here (fakes); pyosmium is not run. The memory and time of the real
    passes were measured once on this laptop (the session note), never on live.
  * Postgres: the stamp reads plain columns only; not run on Postgres here.

Run:  python backend/tests/test_community_all_options.py
"""
import json
import os
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

TMP = tempfile.mkdtemp(prefix="wayscope_allopts_")
from portable import remove_scratch_db   # noqa: E402
for _v in ("DATABASE_URL", "ADMIN_TOKEN", "TENANT_ID"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import network  # noqa: E402
import limits  # noqa: E402
import route_choice  # noqa: E402
import community  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# --------------------------------------------------------------------------- #
#  Fixture: one route; the main line along 52.5 N, an alternative bent 1.1 km  #
#  north (52.51), a way round a closed zone (alt 10) bent south (52.49)        #
# --------------------------------------------------------------------------- #
ART = "Artic Tipper (44t)"
T = db.current_tenant()
DLAT = 1 / 110574.0          # one metre north
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L1', 'Quarry', 52.5, -1.0, 'Quarry')", (T,))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L2', 'Compound', 52.5, -0.9, 'Compound')", (T,))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R1', 'L1', 'L2', "
           "'Small aggregate', 'IPT1')", (T,))
LINE0 = [[-1.0 + 0.005 * i, 52.5] for i in range(21)]
LINE1 = [[-1.0, 52.5], [-0.98, 52.51], [-0.92, 52.51], [-0.9, 52.5]]
LINE10 = [[-1.0, 52.5], [-0.98, 52.49], [-0.92, 52.49], [-0.9, 52.5]]


def put(alt, line, km, leg_both=True):
    network._upsert_geom("R1", ART, json.dumps(line), km, 0.2, None, leg="loaded", alt_index=alt)
    if leg_both:
        network._upsert_geom("R1", ART, json.dumps(list(reversed(line))), km, 0.2, None, leg="return", alt_index=alt)


for _a, _l, _k in ((0, LINE0, 7.0), (1, LINE1, 8.0), (10, LINE10, 9.0)):
    put(_a, _l, _k)


def P(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


# what the county file holds: kept or not by the strip handed to the extract (the real extract's contract: keep() decides)
CANDIDATES = [
    ("schools", "n1", "School by the main line", P(-0.95, 52.5 + 50 * DLAT)),
    ("schools", "n2", "School by the alternative", P(-0.95, 52.51 + 110 * DLAT)),
    ("schools", "n3", "School by the way round", P(-0.95, 52.49 - 110 * DLAT)),
    ("schools", "n4", "School far from every line", P(-0.95, 52.53)),
    ("cycle", "w5", "Cycle path by the alternative",
     {"type": "LineString", "coordinates": [[-0.95, 52.51 + 100 * DLAT], [-0.94, 52.51 + 100 * DLAT]]}),
    # a housing area the alternative crosses, every corner of it more than 250 m from any line: in at 0 m
    ("residential", "w6", "Homes the alternative crosses",
     {"type": "Polygon", "coordinates": [[[-0.97, 52.51 - 400 * DLAT], [-0.955, 52.51 - 400 * DLAT],
                                          [-0.955, 52.51 + 400 * DLAT], [-0.97, 52.51 + 400 * DLAT],
                                          [-0.97, 52.51 - 400 * DLAT]]]}),
]
CALLS = {"osm": 0, "structures": 0}
BREAK = {"osm_on_call": None}


def fake_osm(paths, keep):
    CALLS["osm"] += 1
    if BREAK["osm_on_call"] and CALLS["osm"] == BREAK["osm_on_call"]:
        raise RuntimeError("the county file stopped half way (test)")
    out = []
    for kind, ref, name, g in CANDIDATES:
        d = keep(kind, g)
        if d is not None:
            out.append({"kind": kind, "source": "osm", "source_ref": ref, "name": name, "detail": None, "geometry": g,
                        "dist_m": d})
    return out


def fake_structures(paths, keep):
    CALLS["structures"] += 1
    g = P(-0.93, 52.51 + 20 * DLAT)
    d = keep("s_bridge", g)
    return [] if d is None else [{"kind": "s_bridge", "source": "osm_structures", "source_ref": "n9", "name": "Bridge",
                                  "detail": None, "geometry": g, "dist_m": d}]


def _sq(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


INDEX = {"features": [
    {"properties": {"id": "great-britain", "parent": "europe", "urls": {"pbf": "https://x/gb.osm.pbf"}}, "geometry": _sq(-8, 49, 2, 61)},
    {"properties": {"id": "england", "parent": "great-britain", "urls": {"pbf": "https://x/england.osm.pbf"}}, "geometry": _sq(-6, 49, 2, 56)},
    {"properties": {"id": "testshire", "name": "Testshire", "parent": "england",
                    "urls": {"pbf": "https://x/testshire-latest.osm.pbf"}}, "geometry": _sq(-1.2, 52.3, -0.7, 52.7)},
]}
GIAS_CSV = "URN,EstablishmentName,EstablishmentStatus (name),PhaseOfEducation (name),EstablishmentTypeGroup (name),Easting,Northing\n"
NAPTAN_CSV = ("ATCOCode,CommonName,Indicator,LocalityName,StopType,Status,Longitude,Latitude,Easting,Northing\n"
              f"2600X1,Main stop,opp,Here,BCT,active,-0.97,{52.5 + 40 * DLAT},,\n"
              f"2600X2,Alternative stop,adj,There,BCT,active,-0.93,{52.51 + 40 * DLAT},,\n")


def fake_download(url, dest, **k):
    if "index-v1" in url:
        json.dump(INDEX, open(dest, "w", encoding="utf-8"))
    elif url.endswith(".osm.pbf"):
        open(dest, "wb").write(b"not read: the extract is faked")
        url = url.replace("-latest", "-261115")
    elif "edubase" in url:
        open(dest, "w", encoding="cp1252").write(GIAS_CSV)
    elif "naptan" in url:
        open(dest, "w", encoding="utf-8").write(NAPTAN_CSV)
    else:
        raise RuntimeError("unexpected " + url)
    return url, os.path.getsize(dest)


FETCH = {"download": fake_download, "osm_extract": fake_osm, "osm_structures_extract": fake_structures}
import datetime as _dt  # noqa: E402
TODAY = _dt.date(2026, 11, 16)


def refs(kind=None):
    return {f["properties"]["name"] for f in community.features([kind] if kind else None)}


def near(line, lat):
    return any(abs(c[1] - lat) < 1e-6 for ln in line for c in ln)


# =========================================================================== #
#  1. The strip                                                                #
# =========================================================================== #
narrow = community.strip_from_db().lines
wide = community.strip_from_db(all_options=True).lines
ok("1. strip_from_db() with no argument is still the narrow strip (the main line only here)",
   not near(narrow, 52.51) and not near(narrow, 52.49), str(len(narrow)))
ok("⭐ 1. the wide strip covers the alternative that leaves the main route by 1.1 km", near(wide, 52.51))
ok("⭐ 1. ...and a way round a closed zone (alt 10) stays out of both while no diversion uses it",
   not near(wide, 52.49) and not near(narrow, 52.49))
ok("1. Fetch now asks for every option: ALL_OPTIONS is on and refresh() reads it when not told",
   community.ALL_OPTIONS is True and "all_options = ALL_OPTIONS if all_options is None else bool(all_options)" in read("backend/community.py"))
ok("1. the option number at the edge: 9 is the router's, 10 is a way round", community.MAX_ROUTER_ALT == 9
   and community._option_wanted({"route_id": "R", "leg": "loaded", "alt_index": 9}, True, set())
   and not community._option_wanted({"route_id": "R", "leg": "loaded", "alt_index": 10}, True, set())
   and community._option_wanted({"route_id": "R", "leg": "loaded", "alt_index": 10}, True, {("R", "loaded", 10)})
   and not community._option_wanted({"route_id": "R", "leg": "loaded", "alt_index": 1}, False, set())
   and community._option_wanted({"route_id": "R", "leg": "loaded", "alt_index": 0}, False, set()))

# =========================================================================== #
#  2. A fetch along every option, and status()["all_options"]                  #
# =========================================================================== #
st0 = community.status()
ok("⭐ 2. status() carries the key 'all_options' (the best-option rule reads exactly that name): False before any fetch",
   "all_options" in st0 and st0["all_options"] is False)
st = community.refresh(by="Planner", fetchers=FETCH, today=TODAY)
src = {s["key"]: s for s in st["sources"]}
ok("2. the fetch stored every source (no error)", st["state"] == "done" and not st["error"]
   and all(src[s]["fetched_at"] for s in ("osm", "osm_structures", "gias", "naptan")), json.dumps(st)[:300])
ok("⭐ 2. Fetch now (the default) stores the school, the cycle path and the bus stop along the alternative",
   {"School by the main line", "School by the alternative"} <= refs("schools") and refs("cycle") == {"Cycle path by the alternative"}
   and refs("bus_stops") == {"Main stop", "Alternative stop"}, str(refs()))
ok("⭐ 2. ...never the one by the unused way round, nor the far one",
   "School by the way round" not in refs() and "School far from every line" not in refs())
ok("2. ...a housing area the alternative crosses is in at 0 m",
   [f["properties"]["dist_m"] for f in community.features(["residential"])] == [0.0])
ok("⭐ 2. all_options is True after a fetch along every option", st["all_options"] is True and community.covers_all_options())
_det = community._detail(community._meta_row())
ok("2. each source records the options it was fetched along (a stamp, the list kept once, no line text)",
   len({_det["sources"][s].get("options_stamp") for s in community.COUNT_SOURCES}) == 1
   and list(_det["option_sets"]) == [_det["sources"]["osm"]["options_stamp"]]
   and all(r.startswith("R1|") and "[" not in r for r in _det["option_sets"][_det["sources"]["osm"]["options_stamp"]]),
   json.dumps(_det.get("option_sets"))[:300])

st_n = community.refresh(by="Planner", fetchers=FETCH, today=TODAY, all_options=False)
ok("⭐ 2. the narrow fetch (all_options=False) is unchanged: the main line only, and all_options reads False",
   "School by the alternative" not in refs() and "School by the main line" in refs() and refs("cycle") == set()
   and refs("bus_stops") == {"Main stop"} and st_n["all_options"] is False)
ok("2. ...and the option lists no source points at any more are dropped",
   community._detail(community._meta_row()).get("option_sets") == {})

community.refresh(fetchers=FETCH, today=TODAY)
ok("2. a fetch along every option again: True", community.status()["all_options"] is True)
put(1, [[-1.0, 52.5], [-0.98, 52.512], [-0.92, 52.512], [-0.9, 52.5]], 8.1, leg_both=False)
ok("⭐ 2. a re-route (the alternative's laden leg worked out again) makes it False", community.status()["all_options"] is False)
community.refresh(fetchers=FETCH, today=TODAY)
ok("2. ...True again after the next Fetch now", community.status()["all_options"] is True)
_pr = network.promote_alternative("R1", ART, 1, leg="loaded")
ok("2. Make primary (a swap of option numbers) leaves it True: the same lines are covered",
   not (_pr or {}).get("error") and community.status()["all_options"] is True, str(_pr)[:200])
network.promote_alternative("R1", ART, 1, leg="loaded")      # back as it was
put(2, [[-1.0, 52.5], [-0.97, 52.52], [-0.9, 52.5]], 9.5, leg_both=False)
ok("⭐ 2. a new option the router gave makes it False", community.status()["all_options"] is False)
db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R1' AND alt_index = 2", (T,))
ok("2. ...and dropping it again leaves the layer covering every option there is: True", community.status()["all_options"] is True)
db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, reason_kind, status, source) "
           "VALUES (?, 'RC1', 'R1', NULL, NULL, 10, 'zone', 'in_use', 'auto')", (T,))
route_choice._MEMO.clear()
ok("⭐ 1. a way round a diversion uses is in the strip (narrow and wide)",
   near(community.strip_from_db().lines, 52.49) and near(community.strip_from_db(all_options=True).lines, 52.49))
ok("⭐ 2. a diversion taking up a way round no fetch covered makes it False", community.status()["all_options"] is False)
community.refresh(fetchers=FETCH, today=TODAY)
ok("2. ...the next Fetch now stores the school by the way round and reads True",
   "School by the way round" in refs() and community.status()["all_options"] is True)
db.execute("DELETE FROM route_choice WHERE tenant_id = ? AND id = 'RC1'", (T,))
route_choice._MEMO.clear()
community.refresh(fetchers=FETCH, today=TODAY)
ok("2. a strip handed in (a study, a test) records no stamp: False",
   community.refresh(fetchers=FETCH, today=TODAY, strip=community.strip_from_db(all_options=True))["all_options"] is False)
community.refresh(fetchers=FETCH, today=TODAY)

# =========================================================================== #
#  3. Slices                                                                   #
# =========================================================================== #
one = sorted((f["properties"]["kind"], f["properties"]["name"], f["properties"]["dist_m"]) for f in community.features())
one_struct = [(x["name"], x["dist_m"]) for x in community.structures()]
_lines = len(community.strip_from_db(all_options=True).lines)
community.SLICE_LINES = 1
CALLS.update(osm=0, structures=0)
st_s = community.refresh(fetchers=FETCH, today=TODAY)
sliced = sorted((f["properties"]["kind"], f["properties"]["name"], f["properties"]["dist_m"]) for f in community.features())
ok("⭐ 3. in slices of one line each, the passes read the files once per slice",
   _lines >= 2 and CALLS["osm"] == _lines and CALLS["structures"] == _lines, f"{_lines} lines, calls {CALLS}")
ok("⭐ 3. ...and keep exactly what one pass keeps, at the same nearest distance (the crossed housing area at 0 m)",
   sliced == one and [(x["name"], x["dist_m"]) for x in community.structures()] == one_struct
   and st_s["all_options"] is True, f"{sliced} vs {one}")
ok("3. strip_slices: no size or a short strip is one slice; every site goes in each slice",
   len(community.strip_slices(community.Strip([LINE0, LINE1], [(-1.0, 52.5)]), size=None)) in (1, 2)
   and len(community.strip_slices(community.Strip([LINE0, LINE1], [(-1.0, 52.5)]), size=5)) == 1
   and all(s.sites == [(-1.0, 52.5)] for s in community.strip_slices(community.Strip([LINE0, LINE1, LINE10], [(-1.0, 52.5)]), size=1)))

# a failed slice: the layer is narrow first, then a fetch along every option breaks in its second OpenStreetMap slice
community.SLICE_LINES = None
community.refresh(fetchers=FETCH, today=TODAY, all_options=False)
_osm_before = sorted((f["properties"]["kind"], f["properties"]["name"]) for f in community.features()
                     if f["properties"]["source_key"] == "osm")
community.SLICE_LINES = 1
CALLS.update(osm=0, structures=0)
BREAK["osm_on_call"] = 2
st_f = community.refresh(fetchers=FETCH, today=TODAY)
BREAK["osm_on_call"] = None
src_f = {s["key"]: s for s in st_f["sources"]}
_osm_after = sorted((f["properties"]["kind"], f["properties"]["name"]) for f in community.features()
                    if f["properties"]["source_key"] == "osm")
ok("⭐ 3. a slice that fails fails its source: the OpenStreetMap features stay as they were (nothing of the slices that "
   "worked is stored)", _osm_after == _osm_before and src_f["osm"]["error"] and "half way" in src_f["osm"]["error"]
   and "Cycle path by the alternative" not in refs(), f"{_osm_after} vs {_osm_before}")
ok("3. ...the other sources are stored, the page says what failed, and all_options stays False (the kept layer is narrow)",
   not src_f["gias"]["error"] and not src_f["naptan"]["error"] and "OpenStreetMap" in (st_f["error"] or "")
   and "kept" in (st_f["error"] or "") and st_f["all_options"] is False, json.dumps(st_f)[:300])
community.SLICE_LINES = None
community.refresh(fetchers=FETCH, today=TODAY)
ok("3. the next good fetch puts it right", community.status()["all_options"] is True and "Cycle path by the alternative" in refs())

# =========================================================================== #
#  3b. The cell look-ups give the same answers as the old scan of every probe  #
#      and every segment (the old code, copied here as the reference)          #
# =========================================================================== #
import random  # noqa: E402
from community_sources import polygons_of, in_polygons, bbox_of_coords  # noqa: E402


def old_distance(s, geometry):
    t = geometry["type"]
    if t == "Point":
        ok_, d = s.margin(*geometry["coordinates"][:2])
        return round(d, 1) if ok_ else None
    if t == "LineString":
        coords = geometry["coordinates"]
    else:
        polys = polygons_of(geometry)
        coords = [c for poly in polys for ring in poly for c in ring]
        bb = bbox_of_coords(coords)
        for x, y in s.probe:
            if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and in_polygons(x, y, polys):
                return 0.0
        edges = [(r[i - 1], r[i]) for poly in polys for r in poly for i in range(1, len(r))]
        for line in s.lines:
            for a, b in zip(line, line[1:]):
                if max(a[0], b[0]) < bb[0] or min(a[0], b[0]) > bb[2] or max(a[1], b[1]) < bb[1] or min(a[1], b[1]) > bb[3]:
                    continue
                if in_polygons(a[0], a[1], polys) or in_polygons(b[0], b[1], polys):
                    return 0.0
                if any(s._seg_cross(a, b, e1, e2) for e1, e2 in edges):
                    return 0.0
    best = None
    for c in coords:
        ok_, d = s.margin(c[0], c[1])
        if ok_ and (best is None or d < best):
            best = d
    return round(best, 1) if best is not None else None


rng = random.Random(1116)
LONGSEG = [[-1.0, 52.45], [-0.85, 52.55]]          # one long diagonal segment over many cells
S3 = community.Strip([LINE0, LINE1, LINE10, LONGSEG], [(-0.9, 52.5)])
_shapes = []
for _i in range(600):
    cx, cy = rng.uniform(-1.02, -0.83), rng.uniform(52.44, 52.56)
    w, h = rng.uniform(0.0002, 0.03), rng.uniform(0.0002, 0.02)
    kind = _i % 3
    if kind == 0:
        g = {"type": "Polygon", "coordinates": [[[cx, cy], [cx + w, cy], [cx + w, cy + h], [cx, cy + h], [cx, cy]]]}
    elif kind == 1:
        g = {"type": "LineString", "coordinates": [[cx, cy], [cx + w, cy + h]]}
    else:
        g = P(cx, cy)
    _shapes.append(g)
_diff = [(g, S3.distance(g), old_distance(S3, g)) for g in _shapes if S3.distance(g) != old_distance(S3, g)]
_zero = sum(1 for g in _shapes if g["type"] == "Polygon" and S3.distance(g) == 0.0)
_none = sum(1 for g in _shapes if S3.distance(g) is None)
ok("⭐ 3b. 600 random outlines, lines and points: the cell look-ups give exactly the old answers (some in at 0 m, some out)",
   not _diff and _zero >= 10 and _none >= 10, f"{len(_diff)} differ, e.g. {_diff[:2]}; zero {_zero} none {_none}")
_big = {"type": "Polygon", "coordinates": [[[-0.97, 52.4], [-0.96, 52.4], [-0.96, 52.6], [-0.97, 52.6], [-0.97, 52.4]]]}
ok("3b. an outline crossed only between the vertices of a long segment is in at 0 m, as before",
   S3.distance(_big) == old_distance(S3, _big) == 0.0)

# =========================================================================== #
#  3c. A long fetch keeps a sign of life: the stale rule reads the last beat   #
# =========================================================================== #
_beats = []
community.BEAT_S = 0
_k = community._beating(S3.keep, lambda: _beats.append(1))
ok("3c. the keep() wrapper answers as keep() does and calls beat() when BEAT_S has passed",
   _k("schools", P(-0.95, 52.5)) == S3.keep("schools", P(-0.95, 52.5)) and len(_beats) == 1)
community.BEAT_S = 3600
_k = community._beating(S3.keep, lambda: _beats.append(1))
_k("schools", P(-0.95, 52.5))
ok("3c. ...and not before", len(_beats) == 1 and community._beating(S3.keep, None) == S3.keep)
community.BEAT_S = 60
_old_t = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=45)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
community._write_meta("running", dict(community._detail(community._meta_row()), beat=community._now()), started_at=_old_t)
ok("⭐ 3c. a fetch started 45 minutes ago that beat a moment ago still reads running (it was 'failed' at 30 minutes)",
   community.status()["state"] == "running")
r_ = community.start_refresh(by="x", sync=True, fetchers=FETCH, today=TODAY)
# REVERSED 23 Nov 2026 (claude/working-list): refused in the "Working" list's one sentence, not "already running"
ok("3c. ...so a second Fetch now is refused while it runs", r_["started"] is False and "already running" not in r_["message"]
   and r_["message"] == "The community places fetch is running. The community places fetch can start when it finishes.",
   str(r_.get("message")))
community._write_meta("running", dict(community._detail(community._meta_row()), beat=_old_t), started_at=_old_t)
ok("3c. one with no beat for 45 minutes reads failed (a restart killed it)", community.status()["state"] == "failed")
_src_r = read("backend/community.py").split("def refresh(")[1].split("\ndef ")[0]
ok("3c. refresh() hands the beat to both OpenStreetMap passes",
   "_fetch_osm(strip, workdir, fetch, beat)" in _src_r and "_fetch_osm_structures(strip, workdir, fetch, beat)" in _src_r)
community.refresh(fetchers=FETCH, today=TODAY)

# =========================================================================== #
#  4. Source                                                                   #
# =========================================================================== #
_c = read("backend/community.py")
_main = read("backend/main.py").split("def community_refresh(")[1].split("\n@app.")[0]
ok("4. Fetch now (POST /api/community/refresh) calls start_refresh with no strip and no all_options: every option",
   "community.start_refresh(by=" in _main and "all_options" not in _main and "strip=" not in _main)
ok("4. the one lock with the collision fetch is kept, and the fetch is never started by a page view",
   # NARROWED 23 Nov 2026 (claude/working-list): the check under the one lock is working.refusal (any long job, the
   # collision fetch included)
   "with fetch_guard.LOCK, _LOCK:" in _c and 'working.refusal("community")' in _c
   and 'fetch_guard.other_running(' not in _c)
ok("4. the slice size measured on 16 Nov is set in the module (one pass), with its reason beside it",
   "SLICE_LINES = None" in _c and "measured" in _c.split("SLICE_LINES = None")[0][-300:])
_rc = read("backend/route_compare.py")
ok("⭐ 4. route_compare's warning says what is now true: the alternatives' counts are fair only when status() says so",
   'community.status()["all_options"]' in _rc and "too heavy for the deployment" not in _rc
   and "a machine with more memory" not in _rc)
_tech = read("frontend/help/technical/index.html")
ok("4. the technical guide says a Fetch now covers every option and how the record is read",
   "t8-community-all-options" in _tech and "every option the router gave" in _tech
   and "too heavy for the deployment, which fetches the main routes and diversions only" not in _tech)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
