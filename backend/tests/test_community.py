"""
The community considerations layer, 14 Oct 2026 (item B; branch claude/community-layer).

WHAT IS ASSERTED
----------------
  1. The nine kinds: the user's words, one colour and one symbol each, none of them a reserved colour (the Volume
     blues, the breach and limit reds, orange, the amber status colour, the team / rail / reserved hexes).
  2. The strip (250 m along every route, 500 m round every site): points, lines and outlines in and out by the
     distance, an outline holding a route is in at 0 m; strip_from_db reads the stored road routes and the sites.
  3. The sources, parsed from small fixtures: Geofabrik's index (the GB leaf regions the strip touches, never a parent
     or a region abroad) and its dated file name; British National Grid → WGS84 (the OS worked example); GIAS (open
     schools only, in the strip); NaPTAN (active stops, bus and rail kinds, the area codes from the bbox + 910);
     OpenStreetMap through pyosmium on a real .osm file (polygons, outlines → points, cycle paths and a National Cycle
     Network road, OSM's own schools and bus stops NOT read, nurseries filed under Schools); the downloader resumes a
     short read and refuses a 404 at once.
  4. Storage: a source's rows replaced in one go, the others kept; status and the credit line in words.
  5. refresh(): every source stored with its date; one source failing keeps its old rows and says so; all failing
     changes nothing; no routes and no sites is said in words; start_refresh refuses a second run.
  6. The endpoints: GET /api/community and /status are staff only (401 for nothing and for the map password's cookie),
     POST /refresh is a planner's or an admin's (403 for a team code); the plan endpoints carry `community`.
  7. The CLP plans: the features in the frame, the kinds among them only, the credit line, drawn into the PDF
     (fills under the routes, symbols over), and nothing when the card leaves the layer out.
  8. Source level: the map's group is hidden unless whoami says staff, off by default, read only on a tick, never
     fetched from a public source by the page; the Config panel and its button; the export cards' leave-out box; the
     tables are tenanted and in the package; the guides say what the layer is, where it comes from and how old it is.

WHAT THIS DOES NOT PROVE
------------------------
  * Geofabrik, GIAS and NaPTAN are NOT called: the live run is in notes/session-1014-community.md (14 Oct 2026).
  * Nothing renders in a browser here; Mapbox is never called (portable.offline).
"""
import io
import json
import os
import re
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


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class _App:
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = patch = _deco

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query
_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None
_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_community_")
from portable import remove_scratch_db, offline, pdf_text   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN", "MAP_PASSWORD"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import community  # noqa: E402
import community_sources as cs  # noqa: E402
import route_map_export  # noqa: E402
import export  # noqa: E402
import tenant_package  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import gate  # noqa: E402
offline(export)

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


def boot():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate()


def raises(fn):
    try:
        fn()
    except Exception as e:      # noqa: BLE001
        return e
    return None


# a small strip: one straight route east-west at 52.60 N from -0.95 to -0.90, one site at its east end
LAT0 = 52.60
ROUTE = [[-0.95, LAT0], [-0.925, LAT0], [-0.90, LAT0]]
SITE = (-0.90, LAT0)
DLAT = 1 / 110574.0          # one metre north
DLON = 1 / (111320.0 * 0.6074)   # one metre east at 52.6 N (cos 52.6 ≈ 0.6074)
strip = community.Strip([ROUTE], [SITE])

# --------------------------------------------------------------------------- #
#  1. The kinds                                                                #
# --------------------------------------------------------------------------- #
K = community.KINDS
ok("1: nine kinds, in the user's order", [k["key"] for k in K] ==
   ["residential", "schools", "hospitals", "health", "community", "sports", "stations", "cycle", "bus_stops"])
ok("1: the user's words (and the cycle label the user chose, 14 Oct)",
   [k["label"] for k in K] == ["Residential areas", "Schools", "Hospitals", "Health centres", "Community centres",
                               "Sports facilities", "Stations and tram stops",
                               "Cycle routes (National Cycle Network and cycle paths)", "Bus stops"])
ok("1: one colour each, all different", len({k["colour"].upper() for k in K}) == 9)
ok("1: one symbol each, all different", len({k["symbol"] for k in K}) == 9)
RESERVED = {"#94BBF9", "#5A96F6", "#2071F3", "#0B55CB", "#073888",          # the Volume blues (map CARBON_RAMP)
            "#DC2626", "#C8102E",                                           # breach / clash red, the limit-sign red
            "#FF8C14", "#E8590C", "#E8681E", "#FF8312",                     # orange (barred on the map) and the accent
            "#D97706", "#F59E0B", "#C2790B",                                # amber status
            "#059669", "#3B82F6", "#2563EB", "#0F766E", "#0D9488",          # on plan, forecast / brand blue, rail, teal slot
            "#4C1D95", "#155E75", "#57534E", "#64748B", "#7C3AED",          # team bands, unassigned, violet slot
            "#89A3DC", "#6A8BD2", "#4A72C9", "#2D4E95"}                     # the council plan-blue ramp
ok("1: no kind takes a reserved colour (Volume blues, breach red, orange, amber, team / rail hexes)",
   not ({k["colour"].upper() for k in K} & RESERVED), str({k["colour"] for k in K} & RESERVED))


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


ok("1: every symbol colour stands out from a white basemap (contrast ≥ 3:1)",
   all((1.05) / (_lum(k["colour"]) + 0.05) >= 3.0 for k in K), str([(k["key"], round(1.05 / (_lum(k["colour"]) + .05), 2)) for k in K]))
ok("1: the sources and their licences", community.SOURCES["osm"]["licence"] == "ODbL 1.0"
   and community.SOURCES["gias"]["licence"] == community.SOURCES["naptan"]["licence"] == "OGL v3.0")
ok("1: the strip is 250 m along the routes and 500 m round the sites (the user, 14 Oct)",
   community.STRIP_ROUTE_M == 250 and community.STRIP_SITE_M == 500)

# --------------------------------------------------------------------------- #
#  2. The strip                                                                #
# --------------------------------------------------------------------------- #
P = lambda lon, lat: {"type": "Point", "coordinates": [lon, lat]}
mid = -0.925
ok("2: a point 200 m off a route is in, at about 200 m", abs((strip.distance(P(mid, LAT0 + 200 * DLAT)) or 0) - 200) < 3)
ok("2: a point 300 m off a route (far from the site) is out", strip.distance(P(-0.94, LAT0 + 300 * DLAT)) is None)
ok("2: a point 450 m past the site is in (500 m round a site)", strip.distance(P(-0.90 + 450 * DLON, LAT0)) is not None)
ok("2: a point 600 m past the site is out", strip.distance(P(-0.90 + 600 * DLON, LAT0)) is None)
ok("2: a line with one vertex in the strip is in; one wholly outside is out",
   strip.distance({"type": "LineString", "coordinates": [[mid, LAT0 + 100 * DLAT], [mid, LAT0 + 900 * DLAT]]}) is not None
   and strip.distance({"type": "LineString", "coordinates": [[mid, LAT0 + 400 * DLAT], [mid, LAT0 + 900 * DLAT]]}) is None)
_big = {"type": "Polygon", "coordinates": [[[-0.94, LAT0 - 900 * DLAT], [-0.91, LAT0 - 900 * DLAT],
                                            [-0.91, LAT0 + 900 * DLAT], [-0.94, LAT0 + 900 * DLAT], [-0.94, LAT0 - 900 * DLAT]]]}
ok("2: an outline the route runs through (no vertex near it, no route vertex inside it) is in at 0 m", strip.distance(_big) == 0.0)
_thin_strip = community.Strip([[[-0.95, LAT0], [-0.90, LAT0]]], [])
ok("2: ...even when the route crosses it on one long straight segment", _thin_strip.distance(_big) == 0.0)
ok("2: the strip's box covers the route and the site with the reach", strip.bbox[0] < -0.95 and strip.bbox[2] > -0.90 + 500 * DLON)
boot()
network._upsert_geom  # noqa: B018 — the helper exists (the harnesses bake through it)
db.execute("INSERT INTO locations (tenant_id, id, name, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
           (db.current_tenant(), "L1", "Site", "destination", SITE[1], SITE[0]))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id) VALUES (?, ?, ?, ?)", (db.current_tenant(), "R1", "L1", "L1"))
network._upsert_geom("R1", "Artic Tipper (44t)", json.dumps(ROUTE), 3.4, 0.1, None, leg="loaded", alt_index=0)
network._upsert_geom("R1", "Artic Tipper (44t)", json.dumps(list(reversed(ROUTE))), 3.4, 0.1, None, leg="return", alt_index=0)
_sd = community.strip_from_db()
ok("2: strip_from_db reads the stored road routes (a reversed leg is the same line, kept once) and the sites",
   len(_sd.lines) >= 1 and len(_sd.sites) == 1 and _sd.distance(P(mid, LAT0 + 100 * DLAT)) is not None,
   f"{len(_sd.lines)} {len(_sd.sites)}")

# --------------------------------------------------------------------------- #
#  3. The sources                                                              #
# --------------------------------------------------------------------------- #
FX = os.path.join(TMP, "fx")
os.makedirs(FX, exist_ok=True)
sq = lambda x0, y0, x1, y1: {"type": "MultiPolygon", "coordinates": [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]]}
INDEX = {"features": [
    {"properties": {"id": "great-britain", "parent": "europe", "urls": {"pbf": "https://x/gb.osm.pbf"}}, "geometry": sq(-8, 49, 2, 61)},
    {"properties": {"id": "england", "parent": "great-britain", "urls": {"pbf": "https://x/england.osm.pbf"}}, "geometry": sq(-6, 49, 2, 56)},
    {"properties": {"id": "leicestershire", "name": "Leicestershire", "parent": "england",
                    "urls": {"pbf": "https://x/leicestershire-latest.osm.pbf"}}, "geometry": sq(-1.6, 52.4, -0.92, 52.98)},
    {"properties": {"id": "rutland", "name": "Rutland", "parent": "england",
                    "urls": {"pbf": "https://x/rutland-latest.osm.pbf"}}, "geometry": sq(-0.92, 52.5, -0.4, 52.8)},
    {"properties": {"id": "devon", "name": "Devon", "parent": "england", "urls": {"pbf": "https://x/devon.osm.pbf"}},
     "geometry": sq(-4.7, 50.2, -2.9, 51.25)},
    {"properties": {"id": "brittany", "name": "Bretagne", "parent": "france", "urls": {"pbf": "https://x/bretagne.osm.pbf"}},
     "geometry": sq(-5.2, 47.2, -1.0, 52.7)},
    {"properties": {"id": "france", "parent": "europe", "urls": {"pbf": "https://x/france.osm.pbf"}}, "geometry": sq(-5.2, 41, 9.6, 52.7)},
]}
_regs = cs.geofabrik_regions(INDEX, strip.bbox, strip.probe)
ok("3: Geofabrik: only the GB LEAF regions the strip touches (never a parent, a far county or one abroad)",
   sorted(r[0] for r in _regs) == ["leicestershire", "rutland"], str(_regs))
ok("3: ...a strip outside Great Britain gets none", cs.geofabrik_regions(INDEX, [2.0, 48.0, 2.1, 48.1], [(2.05, 48.05)]) == [])
ok("3: Geofabrik's dated file name gives the data's date", cs.extract_date("https://d/rutland-261013.osm.pbf") == "2026-10-13"
   and cs.extract_date("https://d/rutland-latest.osm.pbf") is None)
_la, _lo = cs._tm_inverse(651409.903, 313177.270)
import math  # noqa: E402
ok("3: British National Grid: the OS worked example (651409.903 E, 313177.270 N → 52°39′27.2531″ N, 1°43′4.5177″ E on OSGB36)",
   abs(math.degrees(_la) - (52 + 39 / 60 + 27.2531 / 3600)) < 1e-6 and abs(math.degrees(_lo) - (1 + 43 / 60 + 4.5177 / 3600)) < 1e-6,
   f"{math.degrees(_la)} {math.degrees(_lo)}")
_wlon, _wlat = cs.bng_to_wgs84(651409.903, 313177.270)
ok("3: ...and the shift to WGS84 is the expected size there (about 100 m west, 30 m north)",
   -0.0025 < _wlon - (1 + 43 / 60 + 4.5177 / 3600) < -0.0005 and 0 < _wlat - (52 + 39 / 60 + 27.2531 / 3600) < 0.0008,
   f"{_wlon} {_wlat}")
# GIAS: four rows — open in the strip, closed in the strip, open far away, "proposed to close" in the strip
def _en(lon, lat):
    """A WGS84 point back to an easting / northing (search; the fixtures need the inverse once)."""
    e, n = 480000.0, 300000.0
    for _ in range(40):
        x, y = cs.bng_to_wgs84(e, n)
        e += (lon - x) * 111320.0 * math.cos(math.radians(lat))
        n += (lat - y) * 110574.0
    return round(e, 1), round(n, 1)
e1, n1 = _en(mid, LAT0 + 120 * DLAT)
e2, n2 = _en(-0.80, 52.30)
GIAS_HEAD = ["URN", "EstablishmentName", "EstablishmentStatus (name)", "PhaseOfEducation (name)", "EstablishmentTypeGroup (name)",
             "Easting", "Northing"]
rows = [["100001", "Langton Primary School", "Open", "Primary", "Local authority maintained schools", e1, n1],
        ["100002", "Old Board School", "Closed", "Primary", "Local authority maintained schools", e1, n1],
        ["100003", "Far School", "Open", "Secondary", "Academies", e2, n2],
        ["100004", "St Mary’s Academy", "Open, but proposed to close", "Secondary", "Academies", e1 + 30, n1]]
gias_path = os.path.join(FX, "gias.csv")
with open(gias_path, "w", encoding="cp1252", newline="") as f:
    import csv as _csv
    w = _csv.writer(f)
    w.writerow(GIAS_HEAD)
    w.writerows(rows)
_g = cs.gias_extract(gias_path, strip.keep, strip.bbox)
ok("3: GIAS: open schools in the strip only (closed and far ones dropped; 'proposed to close' kept)",
   sorted(x["name"] for x in _g) == ["Langton Primary School", "St Mary’s Academy"], str([x["name"] for x in _g]))
ok("3: ...kind Schools, its URN, phase and type in words, within a few metres of where it was put",
   all(x["kind"] == "schools" and x["source_ref"].startswith("URN ") for x in _g)
   and [x["detail"] for x in _g if x["name"].startswith("Langton")] == ["Primary, Local authority maintained schools"]
   and abs([x["dist_m"] for x in _g if x["name"].startswith("Langton")][0] - 120) < 5)
NAPTAN_CSV = ("ATCOCode,CommonName,Indicator,LocalityName,StopType,Status,Longitude,Latitude,Easting,Northing\n"
              f"2600LE1,Langton Road,opp,Langton,BCT,active,{mid},{LAT0 + 40 * DLAT},,\n"
              f"2600LE2,Langton Road,adj,Langton,BCT,inactive,{mid},{LAT0 + 45 * DLAT},,\n"
              f"9100LANG,Langton Rail Station,,Langton,RLY,active,{mid + 0.003},{LAT0 - 150 * DLAT},,\n"
              f"2600LE3,Taxi rank,,Langton,TXR,active,{mid},{LAT0 + 10 * DLAT},,\n"
              f"2600LE4,Far stop,,Elsewhere,BCT,active,-0.80,52.30,,\n")
_n = cs.naptan_extract(NAPTAN_CSV, strip.keep, strip.bbox)
ok("3: NaPTAN: active bus stops and rail stations in the strip; inactive, other types and far ones dropped",
   sorted((x["kind"], x["name"]) for x in _n) == [("bus_stops", "Langton Road"), ("stations", "Langton Rail Station")], str(_n))
ok("3: ...a bus stop's detail is its indicator and locality", [x["detail"] for x in _n if x["kind"] == "bus_stops"] == ["opp, Langton"])
_areas = [{"atco": "260", "bbox": [-1.6, 52.39, -0.66, 52.98]}, {"atco": "268", "bbox": [-0.88, 52.52, -0.42, 52.76]},
          {"atco": "110", "bbox": [-4.7, 50.2, -2.9, 51.25]}]
ok("3: NaPTAN area codes: the areas whose localities overlap the strip, and always 910 (rail)",
   cs.naptan_area_codes(strip.bbox, _areas) == ["260", "268", "910"], str(cs.naptan_area_codes(strip.bbox, _areas)))
_na = json.load(open(os.path.join(BACKEND, "data", "naptan_areas.json"), encoding="utf-8"))
ok("3: the shipped NaPTAN area table: 144 areas, Leicestershire 260 / Leicester 269 / Rutland 268, its OGL line",
   len(_na["areas"]) == 144 and {"260", "268", "269"} <= {a["atco"] for a in _na["areas"]}
   and "Open Government Licence v3.0" in _na["source"])

try:
    import osmium  # noqa: F401
    HAVE_OSMIUM = True
except ImportError:
    HAVE_OSMIUM = False
ok("3: pyosmium is installed (backend/requirements.txt)", HAVE_OSMIUM and "osmium==" in read("backend/requirements.txt"))


def _osm_xml():
    """A tiny .osm file round the strip: what is read and what is not."""
    nid = [0]
    nodes, out = [], []

    def n(lon, lat, tags=None):
        nid[0] += 1
        nodes.append((nid[0], lon, lat, tags or {}))
        return nid[0]

    def tagxml(t):
        return "".join(f'<tag k="{k}" v="{v}"/>' for k, v in t.items())
    hosp = n(mid, LAT0 + 60 * DLAT, {"amenity": "hospital", "name": "Langton Hospital"})
    n(mid + 0.001, LAT0 + 70 * DLAT, {"amenity": "school", "name": "OSM School (GIAS has it)"})
    n(mid + 0.002, LAT0 + 80 * DLAT, {"highway": "bus_stop", "name": "OSM stop (NaPTAN has it)"})
    n(mid + 0.003, LAT0 + 90 * DLAT, {"amenity": "kindergarten", "name": "Little Acorns"})
    n(-0.80, 52.30, {"amenity": "hospital", "name": "Far Hospital"})
    # a community centre drawn as an outline → a point
    cc = [n(mid - 0.002 + dx, LAT0 + (100 + dy) * DLAT) for dx, dy in ((0, 0), (0.0005, 0), (0.0005, 40), (0, 40))]
    # a residential area round the route (no vertex near it) and a pitch
    rr = [n(x, LAT0 + y * DLAT) for x, y in ((-0.94, -900), (-0.93, -900), (-0.93, 900), (-0.94, 900))]
    pp = [n(mid + dx, LAT0 + (150 + dy) * DLAT) for dx, dy in ((0, 0), (0.001, 0), (0.001, 50), (0, 50))]
    cyc = [n(mid - 0.003, LAT0 + 20 * DLAT), n(mid + 0.003, LAT0 + 20 * DLAT)]
    rd = [n(-0.948, LAT0 + 30 * DLAT), n(-0.946, LAT0 + 30 * DLAT)]
    farw = [n(-0.80, 52.30), n(-0.79, 52.30)]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6" generator="test">']
    for i, lon, lat, t in nodes:
        xml.append(f'<node id="{i}" version="1" lat="{lat:.7f}" lon="{lon:.7f}">{tagxml(t)}</node>')

    def way(wid, refs, tags, close=False):
        r = refs + ([refs[0]] if close else [])
        xml.append(f'<way id="{wid}" version="1">' + "".join(f'<nd ref="{x}"/>' for x in r) + tagxml(tags) + "</way>")
    way(101, cc, {"amenity": "community_centre", "name": "Langton Village Hall"}, close=True)
    way(102, rr, {"landuse": "residential", "name": "Langton"}, close=True)
    way(103, pp, {"leisure": "pitch", "sport": "soccer"}, close=True)
    way(104, cyc, {"highway": "cycleway"})
    way(105, rd, {"highway": "unclassified", "name": "Back Lane"})
    way(106, farw, {"highway": "cycleway"})
    xml.append('<relation id="201" version="1"><member type="way" ref="105" role=""/>'
               '<tag k="type" v="route"/><tag k="route" v="bicycle"/><tag k="network" v="ncn"/><tag k="ref" v="64"/></relation>')
    xml.append("</osm>")
    return "\n".join(xml)


osm_path = os.path.join(FX, "fixture.osm")
open(osm_path, "w", encoding="utf-8").write(_osm_xml())
if HAVE_OSMIUM:
    _o = cs.osm_extract([osm_path], strip.keep)
    by = {}
    for x in _o:
        by.setdefault(x["kind"], []).append(x)
    names = sorted((x["kind"], x["name"]) for x in _o)
    ok("3: OSM: a hospital node, a nursery (filed under Schools), a village hall outline as a point",
       ("hospitals", "Langton Hospital") in names and ("schools", "Little Acorns") in names
       and [x["geometry"]["type"] for x in by.get("community", [])] == ["Point"], str(names))
    ok("3: ...OSM's own schools and bus stops are NOT read (GIAS and NaPTAN have them), nor anything far away",
       not any(n_ in ("OSM School (GIAS has it)", "OSM stop (NaPTAN has it)", "Far Hospital") for _, n_ in names)
       and not any(x["kind"] == "bus_stops" for x in _o))
    ok("3: ...the residential area round the route is a polygon at 0 m; the pitch a Sports polygon",
       [(x["geometry"]["type"], x["dist_m"]) for x in by.get("residential", [])] == [("Polygon", 0.0)]
       and [x["geometry"]["type"] for x in by.get("sports", [])] == ["Polygon"]
       and by["sports"][0]["detail"] == "soccer")
    ok("3: ...a cycle path, and a road on National Cycle Network route 64, named for the route; the far path dropped",
       sorted((x["name"], x["detail"]) for x in by.get("cycle", [])) ==
       [("Cycle path", "Cycle path"), ("National Cycle Network route 64", "Quiet road on the route")], str(by.get("cycle")))


class _FakeResp:
    def __init__(self, body, status=200, headers=None, url="https://x/f"):
        self._b, self.status, self.headers, self._u = io.BytesIO(body), status, headers or {}, url

    def read(self, n=-1):
        return self._b.read(n)

    def geturl(self):
        return self._u

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


BODY = bytes(range(256)) * 40
_calls = []


def _opener_short_then_range(req, timeout=0):
    rng = req.headers.get("Range") or req.get_header("Range")
    _calls.append(rng)
    if not rng:   # the first read stops at 3,000 of 10,240 bytes
        return _FakeResp(BODY[:3000], 200, {"Content-Length": str(len(BODY)), "Accept-Ranges": "bytes"})
    start = int(rng.split("=")[1].rstrip("-"))
    return _FakeResp(BODY[start:], 206, {"Content-Range": f"bytes {start}-{len(BODY) - 1}/{len(BODY)}"})


cs_time = cs.time.sleep
cs.time.sleep = lambda s: None
dst = os.path.join(FX, "dl.bin")
try:
    _r = cs.download("https://x/f", dst, opener=_opener_short_then_range, use_curl=False)
except RuntimeError as _ex:
    _r = (None, -1)
ok("3: the downloader resumes a short read with a Range request and gets every byte",
   _r[1] == len(BODY) and open(dst, "rb").read() == BODY and _calls == [None, "bytes=3000-"], str(_calls))


def _opener_404(req, timeout=0):
    import urllib.error
    _calls.append("404")
    raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)


_calls.clear()
_e = raises(lambda: cs.download("https://x/missing", dst, opener=_opener_404, use_curl=False))
ok("3: ...a 404 is refused at once, in words, without retrying", isinstance(_e, RuntimeError) and "HTTP 404" in str(_e)
   and _calls == ["404"], f"{_e} {_calls}")


def _opener_always_short(req, timeout=0):
    return _FakeResp(BODY[:100], 200, {"Content-Length": str(len(BODY))})


_e = raises(lambda: cs.download("https://x/f", dst, opener=_opener_always_short, use_curl=False))
ok("3: ...a read that stays short (no ranges) fails in words after its tries", isinstance(_e, RuntimeError) and "short read" in str(_e))
cs.time.sleep = cs_time

# --------------------------------------------------------------------------- #
#  4. Storage                                                                  #
# --------------------------------------------------------------------------- #
boot()
F1 = [{"kind": "schools", "source_ref": "URN 1", "name": "A School", "detail": "Primary", "geometry": P(mid, LAT0), "dist_m": 5.0}]
F2 = [{"kind": "bus_stops", "source_ref": "260X", "name": "Stop", "detail": "opp", "geometry": P(mid, LAT0), "dist_m": 1.0}]
community.replace_source("gias", F1, "2026-10-14T20:00:00Z")
community.replace_source("naptan", F2, "2026-10-14T20:00:00Z")
community.replace_source("gias", F1 + [dict(F1[0], source_ref="URN 2", name="B School")], "2026-10-14T21:00:00Z")
_f = community.features()
ok("4: a source's rows are replaced together, another source's are kept",
   sorted(x["properties"]["name"] for x in _f) == ["A School", "B School", "Stop"])
ok("4: features come in the kinds' order with their source's name and key",
   [x["properties"]["kind"] for x in _f] == ["schools", "schools", "bus_stops"]
   and _f[0]["properties"]["source"] == "DfE Get Information about Schools" and _f[0]["properties"]["source_key"] == "gias")
ok("4: the credit line names ODbL for OpenStreetMap and OGL v3.0 for the government sources it used",
   community.credit_line(["osm", "gias"]) == ("Community considerations: © OpenStreetMap contributors (ODbL); contains public sector "
                                              "information licensed under the Open Government Licence v3.0 (DfE Get Information "
                                              "about Schools).") and community.credit_line([]) == "")
_st = community.status()
ok("4: status before any refresh: 'never', the counts from what is stored", _st["state"] == "never" and _st["counts"]["schools"] == 2
   and _st["counts"]["bus_stops"] == 1 and _st["total"] == 3)

# --------------------------------------------------------------------------- #
#  5. refresh()                                                                #
# --------------------------------------------------------------------------- #
boot()
_naptan_file = os.path.join(FX, "naptan.csv")
open(_naptan_file, "w", encoding="utf-8").write(NAPTAN_CSV)
_idx_file = os.path.join(FX, "index.json")
json.dump(INDEX, open(_idx_file, "w"))
FAILS = set()


def fake_download(url, dest, **k):
    for key in FAILS:
        if key in url:
            raise RuntimeError(f"could not download {url}: test")
    if "index-v1" in url:
        shutil.copy(_idx_file, dest); return url, os.path.getsize(dest)
    if url.endswith(".osm.pbf"):
        shutil.copy(osm_path, dest); return url.replace("-latest", "-261013"), os.path.getsize(dest)
    if "edubase" in url:
        if "20261014" in url:
            raise RuntimeError("could not download: HTTP 404")    # today's not published yet → yesterday's
        shutil.copy(gias_path, dest); return url, os.path.getsize(dest)
    if "naptan" in url:
        shutil.copy(_naptan_file, dest); return url, os.path.getsize(dest)
    raise RuntimeError("unexpected " + url)


def fake_osm(paths, keep):
    # the downloads are named .osm.pbf; the fixture is .osm XML, so it is read from where it is (pyosmium goes by the name)
    return cs.osm_extract([osm_path], keep) if HAVE_OSMIUM else [
        {"kind": "hospitals", "source_ref": "n1", "name": "Langton Hospital", "detail": None, "geometry": P(mid, LAT0), "dist_m": 1.0}]


import datetime as _dt  # noqa: E402
TODAY = _dt.date(2026, 10, 14)
FX_FETCH = {"download": fake_download, "osm_extract": fake_osm}
st = community.refresh(by="Planner", fetchers=FX_FETCH, strip=strip, today=TODAY)
src = {s["key"]: s for s in st["sources"]}
ok("5: a refresh stores every source, with its data date (Geofabrik's file name; GIAS yesterday's file)",
   st["state"] == "done" and src["osm"]["data_date"] == "2026-10-13" and src["gias"]["data_date"] == "2026-10-13"
   and src["naptan"]["count"] == 2 and src["gias"]["count"] == 2 and not st["error"], json.dumps(st)[:400])
ok("5: ...the counts per kind, and who fetched it", st["counts"]["schools"] >= 2 and st["counts"]["bus_stops"] == 1
   and st["counts"]["hospitals"] == 1 and st["by"] == "Planner")
ok("5: ...the files read are named (Leicestershire and Rutland extracts)",
   any("Leicestershire" in x for x in src["osm"]["files"] or []) and any("Rutland" in x for x in src["osm"]["files"] or []),
   str(src["osm"]))
_before = {x["properties"]["name"] for x in community.features(["bus_stops", "stations"])}
FAILS.add("naptan")
st2 = community.refresh(by="Planner", fetchers=FX_FETCH, strip=strip, today=TODAY)
src2 = {s["key"]: s for s in st2["sources"]}
ok("5: a source that fails keeps what it had, and the page says so in words",
   {x["properties"]["name"] for x in community.features(["bus_stops", "stations"])} == _before
   and src2["naptan"]["error"] and "DfT NaPTAN" in (st2["error"] or "") and "kept" in st2["error"] and st2["state"] == "done")
FAILS.update({"index-v1", "edubase"})
st3 = community.refresh(by="Planner", fetchers=FX_FETCH, strip=strip, today=TODAY)
ok("5: every source failing changes nothing and says so", st3["state"] == "failed" and "nothing was changed" in st3["error"]
   and st3["total"] == st2["total"])
FAILS.clear()
st4 = community.refresh(fetchers=FX_FETCH, strip=community.Strip([], []), today=TODAY)
ok("5: no route and no site: said in words, nothing fetched", st4["state"] == "failed" and "no route is worked out" in st4["error"])
community._write_meta("running", {}, started_at=community._now())
r = community.start_refresh(by="x", sync=True, fetchers=FX_FETCH, strip=strip, today=TODAY)
ok("5: start_refresh refuses while a refresh is running", r["started"] is False and "already running" in r["message"])
community._write_meta("running", {}, started_at="2026-10-14T00:00:00Z")
ok("5: a 'running' row older than 30 minutes reads as failed (a restart killed it)", community.status()["state"] == "failed")
r = community.start_refresh(by="x", sync=True, fetchers=FX_FETCH, strip=strip, today=TODAY)
ok("5: ...and a new one starts", r["started"] is True and r["state"] == "done")

# --------------------------------------------------------------------------- #
#  6. The endpoints                                                            #
# --------------------------------------------------------------------------- #
access.set_current(None)
_e = raises(lambda: main.community_layer(request=_Request()))
ok("6: GET /api/community with no credential: 401", getattr(_e, "status_code", None) == 401)
os.environ["MAP_PASSWORD"] = "pw"
os.environ["GATE_SECRET"] = "s3cret-for-the-harness"
try:
    _mapc = gate.issue(gate.LEVEL_MAP) if hasattr(gate, "issue") else None
except Exception:
    _mapc = None
if _mapc:
    _e = raises(lambda: main.community_layer(request=_Request(cookies={gate.COOKIE: _mapc})))
    ok("6: ...with the map password's cookie: 401 (the public map's password view never gets it)", getattr(_e, "status_code", None) == 401)
_src_main = read("backend/main.py")
_cl = _src_main.split("def community_layer(")[1].split("\n@app.")[0]
ok("6: the layer endpoint checks _staff_request first (the map cookie is not staff)",
   "if not _staff_request(request):" in _cl and "401" in _cl and _cl.index("_staff_request") < _cl.index("community.payload"))
_cs = _src_main.split("def community_status(")[1].split("\n@app.")[0]
ok("6: /api/community/status is staff only too", "if not _staff_request(request):" in _cs and "401" in _cs)
access.set_current("planner123")
_pl = main.community_layer(request=_Request())
ok("6: a planner gets the layer as a FeatureCollection, with the kinds, sources and credit",
   _pl["type"] == "FeatureCollection" and len(_pl["kinds"]) == 9 and _pl["credit"].startswith("Community considerations:")
   and all(f["properties"]["kind"] in community.KIND_KEYS for f in _pl["features"]))
_pk = main.community_layer(kinds="bus_stops", request=_Request())
ok("6: ...`kinds` narrows it", {f["properties"]["kind"] for f in _pk["features"]} == {"bus_stops"})
_cr = _src_main.split("def community_refresh(")[1].split("\n@app.")[0]
ok("6: POST /api/community/refresh: 401 without a code, 403 for a team code, a planner or an admin starts it",
   'raise HTTPException(401' in _cr and 'acc.get("role") not in ("planner", "admin")' in _cr and "403" in _cr
   and "community.start_refresh(" in _cr)
_team = None
for code in ("ipt1", "north", "team1"):
    pass
_orig_cur = access.current
access.current = lambda: {"role": "ipt", "label": "North Team", "ipt": "IPT1"}
_e = raises(lambda: main.community_refresh(request=_Request()))
ok("6: ...a team code's POST is refused, 403", getattr(_e, "status_code", None) == 403)
access.current = _orig_cur
ok("6: the plan endpoints carry `community` through to route_map_export.plan",
   "community: int = 1, request: Request = None):" in _src_main.split("def route_map_export_pdf(")[1][:600]
   and "community: int = 1, request: Request = None):" in _src_main.split("def route_map_export_png(")[1][:600]
   and "route_map_export.plan(S, plan, scale, at, community=bool(community))" in _src_main)

# --------------------------------------------------------------------------- #
#  7. The CLP plans                                                            #
# --------------------------------------------------------------------------- #
import basemap  # noqa: E402
v = basemap.view_centred(mid, LAT0, basemap.zoom_for_scale(2500, LAT0, route_map_export.FRAME_W_MM, route_map_export.W_PX),
                         route_map_export.W_PX, route_map_export.H_PX)
ok("7: basemap.unproject is project's inverse", all(abs(a - b) < 1e-9 for a, b in zip(basemap.unproject(v, *basemap.project(v, -0.91, 52.61)), (-0.91, 52.61))))
CMf = route_map_export.community_in_frame(v)
kinds_in = [k["key"] for k in CMf["kinds"]]
ok("7: the features in the frame and ONLY the kinds among them, in the legend's order",
   kinds_in and kinds_in == [k for k in community.KIND_KEYS if k in kinds_in]
   and set(kinds_in) == {f["properties"]["kind"] for f in CMf["features"]}, str(kinds_in))
ok("7: ...the credit line names the sources in the frame", CMf["credit"].startswith("Community considerations:"))
far_v = basemap.view_centred(-0.5, 52.0, v["zoom"], v["w"], v["h"])
# 15 Oct 2026 (the user: "leave bus stops off the regional plan")
ok("7: the regional plan leaves the bus stops out; the local and site plans keep them",
   route_map_export.PLAN_OMITS == {"regional": ("bus_stops",)}
   and 'community_in_frame(P["view"], omit=PLAN_OMITS.get(kind, ())) if (community and P["view"])' in read("backend/route_map_export.py"))
_om = route_map_export.community_in_frame(v, omit=("bus_stops",))
ok("7: ...left out, no bus stop is drawn or listed, and the panel is told which kind went (never silently)",
   "bus_stops" in kinds_in and not any(f["properties"]["kind"] == "bus_stops" for f in _om["features"])
   and "bus_stops" not in [k["key"] for k in _om["kinds"]] and _om["left_out"] == ["Bus stops"]
   and CMf["left_out"] == [], str(_om["left_out"]))
ok("7: a frame with none of them in it has no community block", (route_map_export.community_in_frame(far_v) or {}).get("kinds") == [])
# a sheet and its PDF (an empty month: the frame still centres; the panel lists the kinds)
S = {"tenant": "Test scheme", "month_long": "October 2026", "filter_words": "All routes", "map_legend_title": "Two-way movements a day",
     "volume_legend": [], "as_at": "Approved plan as at 14 Oct 2026", "map_routes": [], "places": [], "map_sections": [], "controls": [],
     "map_demo_tag": None}
S["plan"] = {"kind": "local", "name": "Local plan", "view": v, "denom": 2500, "scale_words": "1:2,500", "centre": "Langton",
             "places": [], "fitted": False, "community": CMf, "community_asked": True}
_pdf = export.build_route_map_pdf(S)
_t = " ".join(pdf_text(_pdf, "").split()) if shutil.which("pdftotext") else ""
ok("7: the plan's panel lists 'Community considerations', the kinds in view and the sources' credit",
   not _t or ("Community considerations" in _t and all(community.KIND_BY_KEY[k]["label"].split(" (")[0] in _t for k in kinds_in)
              and "Open Government Licence" in _t), _t[-600:])
S["plan"]["community"] = _om
_tr = " ".join(pdf_text(export.build_route_map_pdf(S), "").split()) if shutil.which("pdftotext") else ""
ok("7: ...the regional plan's panel says 'Bus stops are on the local and site plans.' and lists no Bus stops row",
   not _tr or ("Bus stops are on the local and site plans." in _tr and _tr.count("Bus stops") == 1), _tr[-500:])
S["plan"]["community"] = CMf
_absent = [k["label"] for k in community.KINDS if k["key"] not in kinds_in]
ok("7: ...and not the kinds out of view", not _t or not any(a in _t for a in _absent if a not in ("Schools",)), str(_absent))
S["plan"]["community"] = None
_t0 = " ".join(pdf_text(export.build_route_map_pdf(S), "").split()) if shutil.which("pdftotext") else ""
ok("7: left out (the card's box): no block, no credit", not _t0 or ("Community considerations" not in _t0 and "Open Government" not in _t0))
_ex = read("backend/export.py")
_b = _ex.split("def build_route_map_pdf(")[1].split("\ndef ")[0]
ok("7: outlines and cycle routes are drawn BEFORE the routes, the symbols AFTER",
   _b.index('_draw_community(c, PL, P, "under")') < _b.index("_draw_bulletin_schematic(") < _b.index('_draw_community(c, PL, P, "over")'))
ok("7: outlines are a 22 % tint with the full colour as the edge (the colour system's print rule), one figure for PDF and map",
   community.FILL_ALPHA == 0.22 and "c.setFillAlpha(_comm_alpha())" in _ex.split("def _draw_community(")[1].split("\ndef ")[0]
   and main.community_layer(request=_Request())["fill_alpha"] == 0.22)
_rp = read("backend/route_map_export.py")
ok("7: plan() adds the layer unless asked not to", "def plan(S, kind=\"regional\", scale=None, at=None, community=True):" in _rp
   # NARROWED 15 Oct 2026: the plan's own omissions (bus stops off the regional plan) ride along
   and 'P["community"] = community_in_frame(P["view"], omit=PLAN_OMITS.get(kind, ())) if (community and P["view"]) else None' in _rp)

# --------------------------------------------------------------------------- #
#  8. Source level                                                             #
# --------------------------------------------------------------------------- #
MAP, APP = read("map/index.html"), read("frontend/index.html")
_grp = MAP.split('<div class="control-group" id="community-group" hidden>')
ok("8: map — the group is hidden in the markup", len(_grp) == 2)
# found in the browser check (14 Oct 2026): .control-group is display:flex, which beat the hidden attribute — the group
# showed on the password view (and By council on an organisation without council areas)
ok("8: map — a hidden control group is not displayed (display:flex no longer beats the hidden attribute)",
   ".control-group[hidden] { display:none; }" in MAP
   and MAP.index(".control-group[hidden] { display:none; }") > MAP.index(".control-group { display:flex; flex-direction:column; }"))
ok("8: map — ...and shown only when whoami answers level 'staff'",
   "RME.staff = !!(j && j.level === 'staff');" in MAP and "communityStaff(RME.staff);" in MAP
   and "if (g) g.hidden = !COMM.staff;" in MAP)
_box = _grp[1].split("</div>")[0] if len(_grp) == 2 else ""
ok("8: map — the layer is OFF by default (its box carries no checked attribute)", 'id="layer-community"' in _grp[1][:600]
   and not re.search(r'\schecked(\s|>|=)', re.search(r'<input[^>]*id="layer-community"[^>]*>', _grp[1]).group(0).replace("this.checked", "")))
_tog = MAP.split("function toggleCommunity(")[1].split("\n    }")[0]
ok("8: map — the layer is read only when the box is ticked, and only from /api/community (never a public source)",
   "if (COMM.on && !COMM.data) loadCommunity();" in _tog and "fetch('/api/community'" in MAP
   and not re.search(r"overpass|geofabrik|naptan\.api|edubase", MAP, re.I))
ok("8: map — a non-staff answer hides the layers again", "if (!COMM.staff) { COMM.on = false;" in MAP)
ok("8: map — kinds, colours and symbols come from the data, one image per kind",
   "map.addImage(id, commSymbolImage(k.symbol, k.colour)" in MAP and "'icon-image': ['concat', 'comm-', ['get', 'kind']]" in MAP)
ok("8: map — fills and cycle lines go under our layers, the points over them, the sites on top",
   "paint: { 'fill-color': commColourExpr(), 'fill-opacity': commAlpha() } }, before);" in MAP
   and "const commAlpha = () => (COMM.data && COMM.data.fill_alpha) || 0;" in MAP
   and "'line-dasharray': [2, 1.5] } }, before);" in MAP and "raiseMarks();" in MAP.split("function ensureCommunityLayers(")[1].split("function communityPopup(")[0])
ok("8: map — re-added after a basemap switch", "if (typeof COMM !== 'undefined' && COMM.data) ensureCommunityLayers();" in MAP)
ok("8: map — the export card's leave-out box sends community=0",
   'id="rme-no-community"' in MAP and "if (noc && noc.checked) q.set('community', '0');" in MAP)
ok("8: app — Config → Map and bulletin carries the panel; a planner or admin fetches; the page asks every 5 s while it runs",
   "<CommunityPanel access={access} />" in APP and 'fetch(`${API}/community/refresh`, { method: "POST" })' in APP
   and 'access.role === "planner" || access.role === "admin"' in APP and "setTimeout(read, 5000)" in APP)
ok("8: app — the Routes page menu's leave-out box", 'if(noComm) q.set("community", "0");' in APP and "data-rme-no-community" in APP)
ok("8: app — no page reads the layer on load except the panel's status", APP.count("/community/status") == 1)
ok("8: the tables are tenanted, in the package (after the work tables) and in the audit's registry",
   {"community_features", "community_meta"} <= set(db.TENANTED_TABLES)
   and tenant_package.ORDER[-2:] == ["community_features", "community_meta"]
   and '"community_features", "community_meta",' in read("backend/tests/test_tenant_audit.py"))
_sql = read("backend/community.py")
import ast  # noqa: E402
_stmts = [n.value for n in ast.walk(ast.parse(_sql)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
          and re.match(r"\s*(SELECT|DELETE|INSERT|UPDATE)\b", n.value)]
ok("8: every query in community.py names tenant_id (whole statements, read with ast)", len(_stmts) >= 8
   and all("tenant_id" in q for q in _stmts), str([q[:80] for q in _stmts if "tenant_id" not in q]))
ok("8: nothing is fetched on a page view: only refresh() reaches the downloaders",
   _sql.count("fetch[\"download\"](") == 4 and "default_fetchers()" in _sql.split("def refresh(")[1][:400])
GUIDE, TECH = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
ok("8: the user guide says what the layer is, who sees it, where it comes from and how old it is",
   "Community considerations" in GUIDE and "250 m" in GUIDE and "OpenStreetMap" in GUIDE and "NaPTAN" in GUIDE
   and "Get Information about Schools" in GUIDE and "staff" in GUIDE.split("Community considerations")[1][:3000].lower()
   and "the regional plan leaves the bus stops out" in GUIDE)
ok("8: the technical guide says how it is fetched (Geofabrik, not the public Overpass) and the licences",
   "Geofabrik" in TECH and "Overpass" in TECH and "ODbL" in TECH and "Open Government Licence" in TECH)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
