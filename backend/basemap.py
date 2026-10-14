"""
basemap.py — a map behind the bulletin's maps (14 Oct 2026, the user: "no map behind the route").

WHY THIS EXISTS
---------------
Until 13 Oct the bulletin's PDF asked Mapbox for one static image with every route drawn into the URL. Bundle B added a
casing under each route and the shared road sections on top: 132 paths for the demo month, which never fits Mapbox's
8,192-character URL limit, so export.bulletin_map_png gave up and every PDF (live included) fell back to the blank
schematic. The HTML page and the council maps never had a basemap at all.

WHAT IT DOES
------------
Asks Mapbox for the BASEMAP ONLY — the light style, centred and zoomed to frame the points, no overlays — so the URL is
short and always fits, and hands back the view so the caller draws its own routes, sections, pins and district fills on
top in vector, in the same Web Mercator projection Mapbox renders with (512-px tiles):

    v = view(points, w_px, h_px, pad_px)       the centre and the fractional zoom that frame every point
    project(v, lon, lat) -> (x, y)             image pixels, y DOWN, exactly where Mapbox drew that place
    png = fetch(v)                             the PNG (@2x), cached in-process for a day; None when it cannot be had

One HTTP request per distinct view and day; nothing is stored. After a failure no request is made for DOWN_S seconds,
so a document never waits on Mapbox twice. The harnesses never reach Mapbox: portable.offline()
refuses urllib.request.urlopen for the whole process, so fetch() returns None and every caller draws its schematic.
The image carries Mapbox's own logo and attribution; the captions say "Map © Mapbox © OpenStreetMap" as well.
"""
import math
import time
import urllib.error
import urllib.parse
import urllib.request

TILE = 512                       # Mapbox style tiles are 512 px at zoom 0
STYLE = "mapbox/light-v11"       # the public map's light basemap
MAX_PX = 1280                    # the Static Images API's largest side (before @2x)
CACHE_S = 24 * 3600
_CACHE = {}                      # url without the token -> (fetched_at, png bytes)
DOWN_S = 120                     # after a failed fetch, no further attempt for this long: a PDF never waits twice
_DOWN_UNTIL = [0.0]


def _merc(lon, lat):
    """Normalised Web Mercator (0..1 across the world, y down)."""
    lat = max(-85.05112878, min(85.05112878, lat))
    s = math.sin(math.radians(lat))
    return (lon + 180.0) / 360.0, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def _unmerc(x, y):
    lon = x * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))
    return lon, lat


def view(points, w_px, h_px, pad_px=24, max_zoom=15.0, reserve_right_px=0):
    """The centre (lon, lat) and fractional zoom that frame every (lon, lat) point in w_px × h_px with pad_px round it.
    14 Oct 2026 (the route map export's map-only page): `reserve_right_px` keeps a strip at the right free for a legend
    drawn inside the map — the points are framed in the rest, and the centre moves right by half the strip."""
    pts = [p for p in points if p]
    if not pts:
        return None
    w_px, h_px = int(min(MAX_PX, w_px)), int(min(MAX_PX, h_px))
    ms = [_merc(*p) for p in pts]
    x0, x1 = min(m[0] for m in ms), max(m[0] for m in ms)
    y0, y1 = min(m[1] for m in ms), max(m[1] for m in ms)
    dx, dy = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    r = max(0, min(int(reserve_right_px), w_px // 2))
    z = min(math.log2((w_px - r - 2 * pad_px) / (dx * TILE)), math.log2((h_px - 2 * pad_px) / (dy * TILE)), max_zoom)
    z = math.floor(max(0.0, z) * 100) / 100.0           # two decimals: the URL and the drawing use the SAME zoom
    cx, cy = (x0 + x1) / 2 + (r / 2) / (TILE * 2 ** z), (y0 + y1) / 2
    lon, lat = _unmerc(cx, cy)
    lon, lat = round(lon, 5), round(lat, 5)              # what the URL says, so project() uses exactly that centre
    cx, cy = _merc(lon, lat)
    return {"lon": lon, "lat": lat, "zoom": z, "w": w_px, "h": h_px, "cx": cx, "cy": cy}


def project(v, lon, lat):
    """(x, y) in image pixels (y down) of a (lon, lat) on the basemap of view v."""
    k = TILE * (2 ** v["zoom"])
    mx, my = _merc(lon, lat)
    return v["w"] / 2 + (mx - v["cx"]) * k, v["h"] / 2 + (my - v["cy"]) * k


def url(v, token, retina=True):
    return (f"https://api.mapbox.com/styles/v1/{STYLE}/static/{v['lon']:.5f},{v['lat']:.5f},{v['zoom']:.2f},0/"
            f"{v['w']}x{v['h']}{'@2x' if retina else ''}?access_token=" + urllib.parse.quote(token))


def scale(v, target_px):
    """(km, px): a round scale-bar length (0.5, 1, 2, 5 ... km) near target_px image pixels at the view's centre."""
    m_per_px = 40075016.686 * math.cos(math.radians(v["lat"])) / (TILE * 2 ** v["zoom"])
    want = target_px * m_per_px / 1000
    km = 0.5
    for x in (0.5, 1, 2, 5, 10, 20, 50, 100, 200):
        if x <= want * 1.6:
            km = x
    return km, km * 1000 / m_per_px


# ---------------------------------------------------------------------------------------------------------------------
# 14 Oct 2026 (the CLP plans, the user's CLOCS outline CLP template §2.2 / §4): a view at a STATED SCALE, 1:N when the
# map is printed `frame_w_mm` wide. Mapbox's zoom is fractional (two decimals in the URL), so the zoom is worked out from
# the scale and the latitude: ground metres per image pixel = N / 1000 × frame_w_mm / w_px. Rounding the zoom to two
# decimals moves the scale by at most ±0.35 %; Web Mercator's scale also changes with latitude, so 1:N holds at the
# map's centre (a 1:125,000 plan of 25 km north-south is about 0.4 % off at its top and bottom edges).
M_EQUATOR = 40075016.686         # metres round the equator, the sphere Web Mercator uses
MAX_ZOOM = 22.0                  # the Static Images API's deepest zoom


def m_per_px(lat, zoom):
    """Ground metres per image pixel (before @2x) at latitude `lat` and zoom `zoom`."""
    return M_EQUATOR * math.cos(math.radians(lat)) / (TILE * 2 ** zoom)


def zoom_for_scale(denom, lat, frame_w_mm, w_px):
    """The zoom (two decimals) at which an image w_px wide, printed frame_w_mm wide, is at 1:denom at latitude `lat`."""
    want = float(denom) / 1000.0 * float(frame_w_mm) / float(w_px)
    z = math.log2(M_EQUATOR * math.cos(math.radians(lat)) / (TILE * want))
    return round(max(0.0, min(MAX_ZOOM, z)), 2)


def scale_denominator(v, frame_w_mm):
    """The N of 1:N that view v really is at its centre, printed frame_w_mm wide."""
    return m_per_px(v["lat"], v["zoom"]) * v["w"] / float(frame_w_mm) * 1000.0


def view_centred(lon, lat, zoom, w_px, h_px, reserve_right_px=0):
    """The view at `zoom` with (lon, lat) in the middle of the image — or, with `reserve_right_px`, in the middle of what
    is left of it once a strip at the right is kept for a legend."""
    w_px, h_px = int(min(MAX_PX, w_px)), int(min(MAX_PX, h_px))
    r = max(0, min(int(reserve_right_px), w_px // 2))
    mx, my = _merc(lon, lat)
    lon_c, lat_c = _unmerc(mx + (r / 2) / (TILE * 2 ** zoom), my)
    lon_c, lat_c = round(lon_c, 5), round(lat_c, 5)     # what the URL says, so project() uses exactly that centre
    cx, cy = _merc(lon_c, lat_c)
    return {"lon": lon_c, "lat": lat_c, "zoom": zoom, "w": w_px, "h": h_px, "cx": cx, "cy": cy}


def view_to_scale(points, series, frame_w_mm, w_px, h_px, pad_px=24, reserve_right_px=0):
    """(N, view): the first scale 1:N of `series` (largest scale first) at which every point fits the image with pad_px
    round it and the right strip kept free; the last of the series when none fits. (None, None) with no points."""
    pts = [p for p in points if p]
    if not pts or not series:
        return None, None
    w_px, h_px = int(min(MAX_PX, w_px)), int(min(MAX_PX, h_px))
    r = max(0, min(int(reserve_right_px), w_px // 2))
    ms = [_merc(*p) for p in pts]
    x0, x1 = min(m[0] for m in ms), max(m[0] for m in ms)
    y0, y1 = min(m[1] for m in ms), max(m[1] for m in ms)
    clon, clat = _unmerc((x0 + x1) / 2, (y0 + y1) / 2)
    for n in series:
        z = zoom_for_scale(n, clat, frame_w_mm, w_px)
        k = TILE * 2 ** z
        if (x1 - x0) * k <= w_px - r - 2 * pad_px and (y1 - y0) * k <= h_px - 2 * pad_px:
            return n, view_centred(clon, clat, z, w_px, h_px, r)
    n = series[-1]
    return n, view_centred(clon, clat, zoom_for_scale(n, clat, frame_w_mm, w_px), w_px, h_px, r)


def bar_metres(v, target_px):
    """(metres, px): a scale-bar length of 1, 2 or 5 × 10^k metres, the longest not over target_px image pixels."""
    mpp = m_per_px(v["lat"], v["zoom"])
    want, best = target_px * mpp, 1
    for e in range(0, 7):
        for f in (1, 2, 5):
            if f * 10 ** e <= want:
                best = f * 10 ** e
    return best, best / mpp


def length_words(metres):
    return f"{metres / 1000:g} km" if metres >= 1000 else f"{metres:g} m"


def fetch(v, token=None, timeout=12, retina=True):
    """The basemap PNG for view v, or None (no view, no token, Mapbox refused or unreachable). Cached for a day."""
    if not v:
        return None
    if token is None:
        import config
        token = config.mapbox_token()
    if not token:
        return None
    u = url(v, token, retina)
    key = u.split("?", 1)[0]
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    if time.time() < _DOWN_UNTIL[0]:
        return None                  # Mapbox failed a moment ago: the schematic, at once, not another 12 s wait
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Wayscope/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception:
        _DOWN_UNTIL[0] = time.time() + DOWN_S
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        _DOWN_UNTIL[0] = time.time() + DOWN_S
        return None
    if len(_CACHE) > 64:
        _CACHE.clear()
    _CACHE[key] = (time.time(), data)
    return data
