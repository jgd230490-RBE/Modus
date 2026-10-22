"""
community_sources.py — the three public sources of the community considerations layer, read on the
server once per refresh (14 Oct 2026). community.py decides what to keep and stores it; this module
only downloads and parses.

THE SOURCES (decided by the user on 14 Oct 2026 after the live diagnostic, notes/community-sources-1014.md)
  OpenStreetMap   residential areas, hospitals, health centres, community centres, sports facilities,
                  cycle routes and paths, and nurseries (filed under Schools). From a GEOFABRIK county
                  extract (.osm.pbf), never the public Overpass servers: their policy asks a commercial
                  app not to use them as a backend, and on 14 Oct they failed 7 of 11 queries. ODbL 1.0.
  DfE GIAS        schools (open ones only) — the daily all-establishments CSV. OGL v3.0.
  DfT NaPTAN      bus stops and rail / tram stations — the access-nodes CSV for the scheme's transport
                  areas (backend/data/naptan_areas.json picks them). OGL v3.0.

Every download streams to a file (a 65 MB CSV must not sit in memory), follows redirects (Geofabrik's
"-latest" names redirect to the dated file, whose date is the data's date) and is tried three times.
Nothing here is called on a page view: only community.refresh() calls it.
"""
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

USER_AGENT = "Wayscope/1.0 (community considerations; one fetch per scheme refresh)"
GEOFABRIK_INDEX = "https://download.geofabrik.de/index-v1.json"
GIAS_URL = "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{ymd}.csv"
NAPTAN_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv&atcoAreaCodes={codes}"
NAPTAN_AREAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "naptan_areas.json")
NAPTAN_NATIONAL = ("910",)          # rail stations sit in a national area with no localities: always asked


# --------------------------------------------------------------------------- #
#  Downloading                                                                 #
# --------------------------------------------------------------------------- #
def _urllib_once(url, dest, timeout, opener, resume_from=0):
    """One urllib attempt. (final_url, bytes_on_disk, expected_total or 0, ranges_ok). Appends from
    `resume_from` when the server answers a Range request with 206."""
    headers = {"User-Agent": USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    req = urllib.request.Request(url, headers=headers)
    with opener(req, timeout=timeout) as r:
        final = r.geturl() if hasattr(r, "geturl") else url
        h = getattr(r, "headers", None) or {}
        partial = resume_from and getattr(r, "status", 200) == 206
        total = 0
        cr = h.get("Content-Range") if hasattr(h, "get") else None
        if partial and cr and "/" in cr:
            total = int(cr.rsplit("/", 1)[1]) if cr.rsplit("/", 1)[1].isdigit() else 0
        elif not partial:
            total = int(h.get("Content-Length") or 0) if hasattr(h, "get") else 0
        ranges_ok = bool(partial) or ((h.get("Accept-Ranges") or "").lower() == "bytes" if hasattr(h, "get") else False)
        n = resume_from if partial else 0
        with open(dest, "ab" if partial else "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                n += len(chunk)
        return final, n, total, ranges_ok


def _curl(url, dest, timeout):
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("curl is not available")
    r = subprocess.run([exe, "-sSfL", "--retry", "3", "--max-time", str(int(timeout)), "-A", USER_AGENT, "-o", dest,
                        "-w", "%{url_effective} %{size_download}", url], capture_output=True, text=True, timeout=timeout + 60)
    if r.returncode != 0:
        raise RuntimeError(f"curl: {(r.stderr or '').strip()[:160]}")
    final, _, size = (r.stdout or "").strip().rpartition(" ")
    return final or url, int(size) if size.isdigit() else os.path.getsize(dest)


def download(url, dest, timeout=300, tries=3, opener=None, use_curl=True):
    """Stream `url` to the file `dest` and make sure all of it arrived. Returns (final_url, bytes); raises
    RuntimeError with words when it cannot.

    14 Oct 2026: on the build laptop Python's own HTTPS reads were cut off part-way with no error — Geofabrik's
    20 MB file stopped at 15–17 MB every time, NaPTAN's 9.4 MB at 6.3 MB, the GIAS file at 0.2 MB — while curl
    fetched the same files whole, and outside the sandbox too. So: a read short of Content-Length (or one that
    raises) is RESUMED with a Range request where the server allows it (Geofabrik does; GIAS and NaPTAN do not),
    tried again otherwise, and after `tries` attempts handed to curl when the system has it. Whether Render's
    Python is affected is not known; the check and the fallback cover both."""
    opener = opener or urllib.request.urlopen
    last, have, final = None, 0, url
    for k in range(tries):
        try:
            final, n, total, ranges_ok = _urllib_once(url, dest, timeout, opener, resume_from=have)
            if total and n < total:
                have = n if ranges_ok else 0
                raise IOError(f"short read: {n} of {total} bytes")
            return final, n
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:       # not there (a GIAS file for a day not yet published): no retry
                raise RuntimeError(f"could not download {url.split('?')[0]}: HTTP {e.code}")
            last = e
            time.sleep(min(10, 2 * (k + 1)))
        except Exception as e:          # noqa: BLE001 — every failure is retried, then reported in words
            last = e
            if not isinstance(e, IOError) or not have:
                time.sleep(min(10, 2 * (k + 1)))
    if use_curl and shutil.which("curl"):
        try:
            return _curl(url, dest, timeout)
        except Exception as e:          # noqa: BLE001
            last = e
    raise RuntimeError(f"could not download {url.split('?')[0]}: {str(last)[:160]}")


def fetch_text(url, timeout=120, opener=None, encoding="utf-8-sig"):
    fd, path = tempfile.mkstemp(prefix="wayscope_")
    os.close(fd)
    try:
        final, n = download(url, path, timeout=timeout, opener=opener)
        with open(path, "rb") as f:
            return final, f.read().decode(encoding, errors="replace")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
#  Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def point_in_ring(lon, lat, ring):
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i - 1][0], ring[i - 1][1]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-15) + x1:
            c = not c
    return c


def polygons_of(geometry):
    """A GeoJSON Polygon / MultiPolygon as a list of polygons, each a list of rings."""
    t = (geometry or {}).get("type")
    if t == "Polygon":
        return [geometry["coordinates"]]
    if t == "MultiPolygon":
        return list(geometry["coordinates"])
    return []


def in_polygons(lon, lat, polys):
    for rings in polys:
        if rings and point_in_ring(lon, lat, rings[0]) and not any(point_in_ring(lon, lat, h) for h in rings[1:]):
            return True
    return False


def bbox_of_coords(coords):
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


# --------------------------------------------------------------------------- #
#  British National Grid → WGS84 (GIAS gives easting / northing)               #
# --------------------------------------------------------------------------- #
# The OS transverse-Mercator inverse on Airy 1830 (OSGB36), then the 7-parameter Helmert OSGB36 → WGS84 (the
# OS "A guide to coordinate systems in Great Britain" figures, negated). About 3–5 m: checked on 14 Oct 2026
# against postcodes.io at 2.9 and 3.1 m. No pyproj on the server.
_A_AIRY, _B_AIRY = 6377563.396, 6356256.909
_A_WGS, _B_WGS = 6378137.000, 6356752.3142
_F0 = 0.9996012717
_LAT0, _LON0 = math.radians(49.0), math.radians(-2.0)
_N0, _E0 = -100000.0, 400000.0
_TX, _TY, _TZ = 446.448, -125.157, 542.060
_S = 20.4894e-6
_RX, _RY, _RZ = [math.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421)]


def _tm_inverse(E, N):
    a, b = _A_AIRY, _B_AIRY
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)
    lat, M = _LAT0, 0.0
    for _ in range(100):
        lat = (N - _N0 - M) / (a * _F0) + lat
        Ma = (1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * (lat - _LAT0)
        Mb = (3 * n + 3 * n ** 2 + 21 / 8 * n ** 3) * math.sin(lat - _LAT0) * math.cos(lat + _LAT0)
        Mc = (15 / 8 * n ** 2 + 15 / 8 * n ** 3) * math.sin(2 * (lat - _LAT0)) * math.cos(2 * (lat + _LAT0))
        Md = 35 / 24 * n ** 3 * math.sin(3 * (lat - _LAT0)) * math.cos(3 * (lat + _LAT0))
        M = b * _F0 * (Ma - Mb + Mc - Md)
        if abs(N - _N0 - M) < 0.00001:
            break
    s, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * _F0 / math.sqrt(1 - e2 * s * s)
    rho = a * _F0 * (1 - e2) / (1 - e2 * s * s) ** 1.5
    eta2 = nu / rho - 1
    VII = t / (2 * rho * nu)
    VIII = t / (24 * rho * nu ** 3) * (5 + 3 * t * t + eta2 - 9 * t * t * eta2)
    IX = t / (720 * rho * nu ** 5) * (61 + 90 * t * t + 45 * t ** 4)
    X = 1 / (c * nu)
    XI = 1 / (c * 6 * nu ** 3) * (nu / rho + 2 * t * t)
    XII = 1 / (c * 120 * nu ** 5) * (5 + 28 * t * t + 24 * t ** 4)
    XIIA = 1 / (c * 5040 * nu ** 7) * (61 + 662 * t * t + 1320 * t ** 4 + 720 * t ** 6)
    dE = E - _E0
    return (lat - VII * dE ** 2 + VIII * dE ** 4 - IX * dE ** 6,
            _LON0 + X * dE - XI * dE ** 3 + XII * dE ** 5 - XIIA * dE ** 7)


def _to_cart(lat, lon, a, b):
    e2 = 1 - (b * b) / (a * a)
    nu = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return nu * math.cos(lat) * math.cos(lon), nu * math.cos(lat) * math.sin(lon), (1 - e2) * nu * math.sin(lat)


def _from_cart(x, y, z, a, b):
    e2 = 1 - (b * b) / (a * a)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * nu * math.sin(lat), p)
    return lat, math.atan2(y, x)


def bng_to_wgs84(E, N):
    """(lon, lat) in WGS84 for a British National Grid easting / northing (metres)."""
    lat, lon = _tm_inverse(float(E), float(N))
    x, y, z = _to_cart(lat, lon, _A_AIRY, _B_AIRY)
    x2 = _TX + (1 + _S) * x - _RZ * y + _RY * z
    y2 = _TY + _RZ * x + (1 + _S) * y - _RX * z
    z2 = _TZ - _RY * x + _RX * y + (1 + _S) * z
    la, lo = _from_cart(x2, y2, z2, _A_WGS, _B_WGS)
    return math.degrees(lo), math.degrees(la)


# --------------------------------------------------------------------------- #
#  OpenStreetMap: which Geofabrik extracts, and what is in them                #
# --------------------------------------------------------------------------- #
def geofabrik_regions(index, bbox, probe_points=()):
    """The Geofabrik LEAF regions (no sub-region of their own) inside Great Britain that the strip touches:
    the region's outline holds a probe point (a strip vertex or site), or a corner of the strip's bbox.
    [(id, name, pbf_url)], smallest first. Empty = the strip is outside Great Britain's extracts."""
    feats = (index or {}).get("features") or []
    props = {f["properties"]["id"]: f["properties"] for f in feats if f.get("properties", {}).get("id")}
    parents = {p.get("parent") for p in props.values() if p.get("parent")}

    def in_gb(pid):
        seen = 0
        while pid and seen < 10:
            if pid in ("great-britain", "united-kingdom"):
                return True
            pid = (props.get(pid) or {}).get("parent")
            seen += 1
        return False

    corners = [(bbox[0], bbox[1]), (bbox[0], bbox[3]), (bbox[2], bbox[1]), (bbox[2], bbox[3])]
    probes = list(probe_points) + corners
    out = []
    for f in feats:
        p = f.get("properties") or {}
        rid = p.get("id")
        if not rid or rid in parents or not in_gb(p.get("parent")) or not (p.get("urls") or {}).get("pbf"):
            continue
        polys = polygons_of(f.get("geometry"))
        if not polys:
            continue
        rb = bbox_of_coords([c for poly in polys for c in poly[0]])
        if not bbox_overlap(rb, bbox):
            continue
        if any(in_polygons(x, y, polys) for x, y in probes if rb[0] <= x <= rb[2] and rb[1] <= y <= rb[3]):
            out.append((rid, p.get("name") or rid, p["urls"]["pbf"], (rb[2] - rb[0]) * (rb[3] - rb[1])))
    out.sort(key=lambda r: r[3])
    return [(r[0], r[1], r[2]) for r in out]


def extract_date(final_url):
    """Geofabrik's dated file name ('rutland-261013.osm.pbf') → '2026-10-13'; None when it has no date."""
    m = re.search(r"-(\d{2})(\d{2})(\d{2})\.osm\.pbf$", final_url or "")
    return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# OSM tags → kind. Schools come from GIAS (the user, 14 Oct): only nurseries and pre-schools come from OSM, filed
# under Schools. Bus stops and stations come from NaPTAN, so OSM's are not read.
OSM_POINT_KINDS = (
    (("amenity", "hospital"), "hospitals"), (("healthcare", "hospital"), "hospitals"),
    (("amenity", "clinic"), "health"), (("amenity", "doctors"), "health"),
    (("healthcare", "clinic"), "health"), (("healthcare", "centre"), "health"), (("healthcare", "doctor"), "health"),
    (("amenity", "community_centre"), "community"), (("amenity", "social_centre"), "community"),
    (("amenity", "kindergarten"), "schools"),
    (("leisure", "sports_centre"), "sports"), (("leisure", "stadium"), "sports"), (("leisure", "sports_hall"), "sports"),
    (("leisure", "swimming_pool"), "sports"), (("leisure", "track"), "sports"), (("leisure", "pitch"), "sports"),
)
OSM_POLYGON_KINDS = {("landuse", "residential"): "residential", ("leisure", "pitch"): "sports",
                     ("leisure", "sports_centre"): "sports", ("leisure", "stadium"): "sports",
                     ("leisure", "track"): "sports"}
CYCLE_NETWORKS = {"ncn": "National Cycle Network", "rcn": "Regional cycle route"}


def osm_kind(tags):
    for (k, v), kind in OSM_POINT_KINDS:
        if tags.get(k) == v:
            return kind
    return None


def osm_polygon_kind(tags):
    for (k, v), kind in OSM_POLYGON_KINDS.items():
        if tags.get(k) == v:
            return kind
    return None


def is_cycle_way(tags):
    if tags.get("highway") == "cycleway":
        return True
    for k in ("cycleway", "cycleway:both", "cycleway:left", "cycleway:right"):
        if tags.get(k) in ("lane", "track"):
            return True
    return False


def _osm_detail(tags, kind):
    if kind == "schools":
        return "Nursery or pre-school"
    if kind == "sports":
        return (tags.get("sport") or tags.get("leisure") or "").replace("_", " ").replace(";", ", ")
    if kind == "health":
        return {"doctors": "GP surgery", "clinic": "Clinic"}.get(tags.get("amenity"), "Health centre")
    return None


def osm_extract(paths, keep):
    """Read Geofabrik .osm.pbf files and return the features `keep` accepts.

    keep(kind, geometry) -> distance in metres (kept) or None (outside the strip). Two passes per file: the
    cycle route relations first (their member ways are read in the second), then everything else, with
    pyosmium dropping untagged and unwanted objects in C++ (a whole county in about a second). Polygons
    (residential areas, sports grounds) are assembled into Polygon / MultiPolygon; a hospital, surgery,
    community centre or nursery drawn as an outline becomes the point at its outline's centre. The same
    OSM object read from two overlapping extracts is kept once."""
    import osmium            # imported here: the app starts without it; refresh says so in words
    feats, seen = [], set()
    for path in paths:
        members = {}
        for o in osmium.FileProcessor(path, osmium.osm.RELATION).with_filter(
                osmium.filter.TagFilter(("route", "bicycle"))):
            net = o.tags.get("network")
            if net not in CYCLE_NETWORKS:
                continue
            label = CYCLE_NETWORKS[net] + (f" route {o.tags.get('ref')}" if o.tags.get("ref") else "")
            if o.tags.get("name"):
                label += f" ({o.tags.get('name')})" if o.tags.get("ref") else f": {o.tags.get('name')}"
            for m in o.members:
                if m.type == "w":
                    members.setdefault(m.ref, label)
        area_filter = osmium.filter.TagFilter(*(list(OSM_POLYGON_KINDS) + [kv for kv, _ in OSM_POINT_KINDS]))
        fp = (osmium.FileProcessor(path).with_locations().with_areas(area_filter)
              .with_filter(osmium.filter.EmptyTagFilter()))
        for o in fp:
            tags = {t.k: t.v for t in o.tags}
            if o.is_area():
                key = ("a", o.orig_id(), o.from_way())
                if key in seen:
                    continue
                pk, kind = osm_polygon_kind(tags), osm_kind(tags)
                try:
                    polys = []
                    for outer in o.outer_rings():
                        ring = [[round(n.lon, 5), round(n.lat, 5)] for n in outer]
                        holes = [[[round(n.lon, 5), round(n.lat, 5)] for n in inner] for inner in o.inner_rings(outer)]
                        polys.append([ring] + holes)
                except Exception:
                    continue
                if not polys:
                    continue
                if pk:
                    geom = ({"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1
                            else {"type": "MultiPolygon", "coordinates": polys})
                    use_kind = pk
                elif kind:
                    ring = polys[0][0]
                    geom = {"type": "Point", "coordinates": [round(sum(c[0] for c in ring) / len(ring), 5),
                                                             round(sum(c[1] for c in ring) / len(ring), 5)]}
                    use_kind = kind
                else:
                    continue
                d = keep(use_kind, geom)
                if d is None:
                    continue
                seen.add(key)
                ref = ("w" if o.from_way() else "r") + str(o.orig_id())
                feats.append({"kind": use_kind, "source": "osm", "source_ref": ref, "name": tags.get("name"),
                              "detail": _osm_detail(tags, use_kind), "geometry": geom, "dist_m": d})
            elif o.is_node():
                kind = osm_kind(tags)
                if not kind or ("n", o.id) in seen:
                    continue
                geom = {"type": "Point", "coordinates": [round(o.location.lon, 5), round(o.location.lat, 5)]}
                d = keep(kind, geom)
                if d is None:
                    continue
                seen.add(("n", o.id))
                feats.append({"kind": kind, "source": "osm", "source_ref": "n" + str(o.id), "name": tags.get("name"),
                              "detail": _osm_detail(tags, kind), "geometry": geom, "dist_m": d})
            elif o.is_way():
                route = members.get(o.id)
                if not (route or is_cycle_way(tags)) or ("w", o.id) in seen:
                    continue
                try:
                    coords = [[round(n.lon, 5), round(n.lat, 5)] for n in o.nodes]
                except Exception:
                    continue
                if len(coords) < 2:
                    continue
                geom = {"type": "LineString", "coordinates": coords}
                d = keep("cycle", geom)
                if d is None:
                    continue
                seen.add(("w", o.id))
                name = route or tags.get("name") or ("Cycle path" if tags.get("highway") == "cycleway" else "Cycle lane")
                feats.append({"kind": "cycle", "source": "osm", "source_ref": "w" + str(o.id), "name": name,
                              "detail": ("Cycle path" if tags.get("highway") == "cycleway" else
                                         "On the road" if is_cycle_way(tags) else "Quiet road on the route"),
                              "geometry": geom, "dist_m": d})
    return feats


# --------------------------------------------------------------------------- #
#  DfE Get Information about Schools                                           #
# --------------------------------------------------------------------------- #
GIAS_OPEN = ("Open", "Open, but proposed to close")


def gias_url(day):
    return GIAS_URL.format(ymd=day.strftime("%Y%m%d"))


def gias_extract(path, keep, bbox=None):
    """Open establishments from a GIAS all-data CSV (cp1252) that `keep` accepts, kind 'schools'."""
    out = []
    with open(path, "r", encoding="cp1252", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("EstablishmentStatus (name)") or "").strip() not in GIAS_OPEN:
                continue
            try:
                lon, lat = bng_to_wgs84(float(r["Easting"]), float(r["Northing"]))
            except (KeyError, TypeError, ValueError):
                continue
            if bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                continue
            geom = {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}
            d = keep("schools", geom)
            if d is None:
                continue
            phase = (r.get("PhaseOfEducation (name)") or "").strip()
            group = (r.get("EstablishmentTypeGroup (name)") or "").strip()
            detail = ", ".join(x for x in (phase if phase and phase != "Not applicable" else "", group) if x)
            out.append({"kind": "schools", "source": "gias", "source_ref": "URN " + (r.get("URN") or "").strip(),
                        "name": (r.get("EstablishmentName") or "").strip() or None, "detail": detail or None,
                        "geometry": geom, "dist_m": d})
    return out


# --------------------------------------------------------------------------- #
#  DfT NaPTAN                                                                  #
# --------------------------------------------------------------------------- #
NAPTAN_KINDS = {"BCT": "bus_stops", "BCS": "bus_stops", "RLY": "stations", "TMU": "stations"}


def naptan_area_codes(bbox, areas=None):
    """The ATCO area codes whose NPTG localities overlap the strip's bbox (padded by ~2 km), plus the
    national rail area. From backend/data/naptan_areas.json (built 14 Oct 2026 from the NPTG)."""
    if areas is None:
        with open(NAPTAN_AREAS, encoding="utf-8") as f:
            areas = json.load(f)["areas"]
    pad = 0.03
    b = [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad]
    codes = sorted({a["atco"] for a in areas if a.get("bbox") and bbox_overlap(a["bbox"], b)})
    return codes + [c for c in NAPTAN_NATIONAL if c not in codes]


def naptan_extract(text, keep, bbox=None):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if (r.get("Status") or "").strip().lower() != "active":
            continue
        kind = NAPTAN_KINDS.get((r.get("StopType") or "").strip())
        if not kind:
            continue
        try:
            lon, lat = float(r["Longitude"]), float(r["Latitude"])
        except (KeyError, TypeError, ValueError):
            try:
                lon, lat = bng_to_wgs84(float(r["Easting"]), float(r["Northing"]))
            except (KeyError, TypeError, ValueError):
                continue
        if bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        geom = {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}
        d = keep(kind, geom)
        if d is None:
            continue
        name = (r.get("CommonName") or "").strip()
        ind = (r.get("Indicator") or "").strip()
        loc = (r.get("LocalityName") or "").strip()
        detail = ", ".join(x for x in (ind, loc) if x) if kind == "bus_stops" else (
            "Rail station" if r.get("StopType") == "RLY" else "Tram or metro")
        out.append({"kind": kind, "source": "naptan", "source_ref": (r.get("ATCOCode") or "").strip(),
                    "name": name or None, "detail": detail or None, "geometry": geom, "dist_m": d})
    return out


# --------------------------------------------------------------------------- #
#  22 Oct 2026 (abnormal loads, phase 3): the structures and limits along the roads, read from the SAME county
#  extract in a second pass, kept in community_features under the source "osm_structures". Not a community
#  layer kind (nothing of this is drawn on the community group): abnormal_route reads them to find a load's
#  potential pinch points — a bridge the road is carried on, a railway or an overhead line the line crosses, a level
#  crossing, traffic calming, a signed limit tagged on the road (maxheight, maxwidth, maxweight, maxaxleload,
#  maxlength, a height restrictor). The strip is the community strip, which strip_from_db() now widens to the
#  abnormal loads' own lines. OpenStreetMap is as complete as its mappers: a road may carry no tag at all.
# --------------------------------------------------------------------------- #
STRUCTURE_SOURCE = "osm_structures"
STRUCTURE_KINDS = ("s_bridge", "s_rail", "s_level_crossing", "s_calming", "s_power", "s_limit")
STRUCTURE_WORDS = {"s_bridge": "a bridge or viaduct carrying the road", "s_rail": "a railway",
                   "s_level_crossing": "a level crossing", "s_calming": "traffic calming",
                   "s_power": "an overhead power line", "s_limit": "a signed limit tagged on the road"}
RAIL_TYPES = ("rail", "light_rail", "narrow_gauge", "tram", "monorail", "funicular")
ROAD_TYPES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
              "living_street", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
LIMIT_TAGS = ("maxheight", "maxwidth", "maxweight", "maxaxleload", "maxlength")
STRUCTURE_KEYS = ("bridge", "railway", "traffic_calming", "power", "barrier") + LIMIT_TAGS
KEPT_TAGS = ("name", "ref", "highway", "bridge", "bridge:name", "bridge:structure", "layer", "railway", "electrified",
             "tunnel", "service", "traffic_calming", "power", "voltage", "cables", "barrier", "operator") + LIMIT_TAGS
STRUCTURE_DENSE_M = 120.0      # a long straight way is tested against the strip every 120 m, not only at its vertices


def structure_way_kind(tags):
    """The kind a tagged WAY is for the abnormal loads, or None: an overhead power line, a railway (never a disused or
    abandoned one: those carry railway=disused / abandoned), a road on a bridge, a road with a signed limit tag."""
    if tags.get("power") in ("line", "minor_line"):
        return "s_power"
    if tags.get("railway") in RAIL_TYPES:
        return "s_rail"
    if tags.get("highway") in ROAD_TYPES:
        if tags.get("bridge") not in (None, "no"):
            return "s_bridge"
        if any(tags.get(k) for k in LIMIT_TAGS):
            return "s_limit"
    return None


def structure_node_kind(tags):
    """The kind a tagged NODE is: a level crossing, a traffic-calming feature, a height restrictor (a barrier with a
    limit tag)."""
    if tags.get("railway") in ("level_crossing", "crossing"):
        return "s_level_crossing"
    if tags.get("traffic_calming") not in (None, "no"):
        return "s_calming"
    if tags.get("barrier") == "height_restrictor" or (tags.get("barrier") and any(tags.get(k) for k in LIMIT_TAGS)):
        return "s_limit"
    return None


def structure_name(tags):
    return tags.get("name") or tags.get("bridge:name") or tags.get("ref") or None


def structure_detail(tags):
    """The tags that matter, as 'key=value;key=value' (a ';' in a value becomes ',') — read back by
    abnormal_route._parse_detail."""
    parts = []
    for k in KEPT_TAGS:
        v = tags.get(k)
        if v:
            parts.append(f"{k}={str(v).replace(';', ',').strip()}")
    return ";".join(parts) or None


def _dense(coords, step_m=STRUCTURE_DENSE_M):
    """The way's vertices plus a point every step_m along a long straight (for the strip test only; the stored
    geometry keeps the vertices as mapped)."""
    out = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        lat = math.radians((a[1] + b[1]) / 2.0)
        dx, dy = (b[0] - a[0]) * 111320.0 * math.cos(lat), (b[1] - a[1]) * 110574.0
        n = int(math.hypot(dx, dy) // step_m)
        for i in range(1, n + 1):
            t = i / (n + 1)
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
        out.append(b)
    return out


def osm_structures_extract(paths, keep):
    """Read the same Geofabrik .osm.pbf files for the structures and limits along the roads (one pass over nodes and
    ways, the tag filter in C++: any of STRUCTURE_KEYS). keep(kind, geometry) -> distance (kept) or None (outside the
    strip). The same object read from two overlapping extracts is kept once. Returns features shaped like
    osm_extract's, source 'osm_structures'."""
    import osmium            # imported here: the app starts without it; refresh says so in words
    feats, seen = [], set()
    for path in paths:
        fp = (osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY).with_locations()
              .with_filter(osmium.filter.KeyFilter(*STRUCTURE_KEYS)))
        for o in fp:
            tags = {t.k: t.v for t in o.tags}
            if o.is_node():
                kind = structure_node_kind(tags)
                if not kind:
                    continue
                try:
                    geom = {"type": "Point", "coordinates": [round(o.lon, 6), round(o.lat, 6)]}
                except Exception:
                    continue
                ref, test_geom = "n" + str(o.id), geom
            elif o.is_way():
                kind = structure_way_kind(tags)
                if not kind:
                    continue
                try:
                    coords = [[round(n.lon, 6), round(n.lat, 6)] for n in o.nodes if n.location.valid()]
                except Exception:
                    continue
                if len(coords) < 2:
                    continue
                geom = {"type": "LineString", "coordinates": coords}
                ref, test_geom = "w" + str(o.id), {"type": "LineString", "coordinates": _dense(coords)}
            else:
                continue
            if ref in seen:
                continue
            d = keep(kind, test_geom)
            if d is None:
                continue
            seen.add(ref)
            feats.append({"kind": kind, "source": STRUCTURE_SOURCE, "source_ref": ref, "name": structure_name(tags),
                          "detail": structure_detail(tags), "geometry": geom, "dist_m": d})
    return feats
