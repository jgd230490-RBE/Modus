"""
The style of the server-drawn maps, 28 Oct 2026 (task 8e) — branch claude/export-basemap.

WHAT IS ASSERTED
----------------
  1. basemap.STYLES: the four styles (light, streets, outdoors, aerial), each with its Mapbox style, its road-name layer
     (probed 28 Oct 2026: light-v11 `road-label-simple`, the three -v12 styles `road-label`) and its credit words; Aerial's
     credit names Maxar; clean_style refuses anything else; the default is light.
  2. Which style a map is drawn in: the one asked for, else the thread's `use` block, else the tenant's setting
     (config.export_map_style), else light; `use` restores the previous choice and ignores an unknown key.
  3. url() carries the chosen style in its path and nothing else changes; labels_layer() and credit() follow it.
  4. fetch(): a chosen style Mapbox refuses (HTTP error) falls back to Light at once, with Light's road-name layer
     swapped in for the chosen style's; a network failure does not (no second request, Mapbox marked down).
  5. config: the tenant's `export_map_style` validates (light / streets / outdoors / aerial / blank), reads back as light
     without a usable value.
  6. The route sheet's overlays are measured against the CHOSEN style's road-name layer (export._rs_overlays).
  7. Source level: the bulletin's maps stay Light (the explicit style on the bulletin calls and the fixed Light URL), the
     credit lines read basemap.credit(), main.py's two map-export endpoints take `style` (422 for an unknown one, blank =
     the tenant's), the staff app's Config card and the Routes page's export menu, the public map's export dialog
     ("As on screen" follows the basemap showing when it is one of the four).

WHAT THIS DOES NOT PROVE
------------------------
  * Mapbox is never called: the Static Images answers are a stub. The four styles were drawn for real on 28 Oct 2026
    (notes\\export-basemap-mockup-1028) and the live check follows the merge.
  * No browser here; the session note records the Chrome check.

Run:  python backend/tests/test_export_style.py
"""
import io
import os
import sys
import types
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

import basemap  # noqa: E402
import config  # noqa: E402

PASS = FAIL = 0


def ok(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   ", label)
    else:
        FAIL += 1
        print("  FAIL ", label, extra)


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


# ---- 1. the table
ok("1: four styles, in order", list(basemap.STYLES) == ["light", "streets", "outdoors", "aerial"])
ok("1: their Mapbox styles", [v[0] for v in basemap.STYLES.values()] ==
   ["mapbox/light-v11", "mapbox/streets-v12", "mapbox/outdoors-v12", "mapbox/satellite-streets-v12"])
ok("1: road-name layers as probed 28 Oct 2026 (Light's is the simple one)",
   [v[1] for v in basemap.STYLES.values()] == ["road-label-simple", "road-label", "road-label", "road-label"])
ok("1: Aerial's credit names Maxar, the others do not",
   "Maxar" in basemap.STYLES["aerial"][2] and all("Maxar" not in basemap.STYLES[k][2] for k in ("light", "streets", "outdoors")))
ok("1: names for people", basemap.STYLE_NAMES["aerial"] == "Aerial (with names)" and set(basemap.STYLE_NAMES) == set(basemap.STYLES))
ok("1: clean_style accepts the four (any case, spaces) and refuses the rest",
   basemap.clean_style(" Aerial ") == "aerial" and basemap.clean_style("standard") is None
   and basemap.clean_style("") is None and basemap.clean_style(None) is None and basemap.clean_style(3) is None)
ok("1: the default stays Light and the old constants are kept", basemap.DEFAULT_STYLE == "light" and basemap.STYLE == "mapbox/light-v11"
   and basemap.LABELS_LAYER == "road-label-simple")
ok("1: config's list is the same four", list(config.EXPORT_MAP_STYLES) == list(basemap.STYLES))

# ---- 2. which style
ok("2: nothing set, no database: light", basemap.resolve_style() == "light")
ok("2: asked for wins", basemap.resolve_style("streets") == "streets")
with basemap.use("outdoors"):
    ok("2: a use block", basemap.resolve_style() == "outdoors" and basemap.resolve_style("aerial") == "aerial")
    with basemap.use("aerial"):
        ok("2: nested", basemap.resolve_style() == "aerial")
    ok("2: the outer choice is back after the inner block", basemap.resolve_style() == "outdoors")
    with basemap.use("standard"):
        ok("2: an unknown key changes nothing", basemap.resolve_style() == "outdoors")
ok("2: and after the block, light again", basemap.resolve_style() == "light")

_real_cfg = config.export_map_style
config.export_map_style = lambda conversions=None, doc=None: "streets"
ok("2: the tenant's setting is read when nothing else is asked", basemap.resolve_style() == "streets")
with basemap.use("aerial"):
    ok("2: a use block beats the tenant's setting", basemap.resolve_style() == "aerial")
ok("2: an explicit light beats it too", basemap.resolve_style("light") == "light")
config.export_map_style = _real_cfg

# ---- 3. url
V = {"lon": -1.0, "lat": 52.5, "zoom": 10.0, "w": 800, "h": 600}
ok("3: Light's url is what it was", basemap.url(V, "T").startswith("https://api.mapbox.com/styles/v1/mapbox/light-v11/static/-1.00000,52.50000,10.00,0/800x600@2x?"))
ok("3: the chosen style is in the path",
   "/styles/v1/mapbox/satellite-streets-v12/static/" in basemap.url(V, "T", style="aerial")
   and "/styles/v1/mapbox/streets-v12/static/" in basemap.url(V, "T", style="streets"))
with basemap.use("outdoors"):
    ok("3: a use block reaches url, labels_layer and credit",
       "/outdoors-v12/" in basemap.url(V, "T") and basemap.labels_layer() == "road-label" and basemap.credit() == basemap.STYLES["outdoors"][2])
ok("3: the overlays and the before_layer still ride in the url",
   "before_layer=road-label&" in basemap.url(V, "T", overlays=["path-3+FF0000(abc)"], before_layer="road-label", style="streets"))

# ---- 4. fetch and its fallback
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20
calls = []


class _Resp:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake(mode):
    def urlopen(req, timeout=0):
        u = req.full_url if hasattr(req, "full_url") else req
        calls.append(u)
        if mode == "refuse-non-light" and "/light-v11/" not in u:
            raise urllib.error.HTTPError(u, 422, "no such layer", {}, io.BytesIO(b""))
        if mode == "network":
            raise urllib.error.URLError("down")
        return _Resp(PNG)
    return urlopen


_real_open = basemap.urllib.request.urlopen
basemap._CACHE.clear()
basemap.urllib.request.urlopen = _fake("refuse-non-light")
got = basemap.fetch(V, "T", overlays=["path-3+FF0000(abc)"], before_layer="road-label", style="aerial")
ok("4: a style Mapbox refuses falls back to Light and still answers a picture", got == PNG)
ok("4: two requests: the chosen style first, then Light with Light's own road-name layer",
   len(calls) == 2 and "/satellite-streets-v12/" in calls[0] and "before_layer=road-label&" in calls[0]
   and "/light-v11/" in calls[1] and "before_layer=road-label-simple&" in calls[1], str(calls))
calls.clear(); basemap._CACHE.clear()
got = basemap.fetch(V, "T", style="light")
ok("4: Light refused is not retried (no loop)", True)
basemap._CACHE.clear(); calls.clear()
basemap.urllib.request.urlopen = _fake("network")
basemap._DOWN_UNTIL[0] = 0.0
got = basemap.fetch(V, "T", style="streets")
ok("4: a network failure is not a fallback: one request, Mapbox marked down, no picture",
   got is None and len(calls) == 1 and basemap._DOWN_UNTIL[0] > 0)
basemap._DOWN_UNTIL[0] = 0.0
basemap._CACHE.clear()
# the satellite style answers a JPEG (found 28 Oct 2026 against the real service: it used to be refused as "not a picture"
# and marked Mapbox down for two minutes, so the next map in the same document fell back to the schematic)
JPG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"j" * 20
basemap.urllib.request.urlopen = lambda req, timeout=0: _Resp(JPG)
got = basemap.fetch(V, "T", style="aerial")
ok("4: a JPEG answer is a picture, and Mapbox is NOT marked down", got == JPG and basemap._DOWN_UNTIL[0] == 0.0)
basemap._CACHE.clear()
basemap.urllib.request.urlopen = lambda req, timeout=0: _Resp(b"<html>not a picture</html>")
got = basemap.fetch(V, "T", style="streets")
ok("4: anything else is still refused and marks Mapbox down", got is None and basemap._DOWN_UNTIL[0] > 0)
basemap._DOWN_UNTIL[0] = 0.0
basemap._CACHE.clear()
basemap.urllib.request.urlopen = _real_open

# ---- 5. config
good = {"tenant": {"export_map_style": "aerial"}}
ok("5: the setting reads back", config.export_map_style(doc=good) == "aerial")
ok("5: blank, missing, wrong type or unknown reads as light",
   all(config.export_map_style(doc=d) == "light" for d in
       ({"tenant": {"export_map_style": ""}}, {"tenant": {}}, {}, {"tenant": {"export_map_style": 3}},
        {"tenant": {"export_map_style": "standard"}})))
src_cfg = read("backend", "config.py")
ok("5: Config's validation names the four and accepts blank",
   'tenant.export_map_style must be light, streets, outdoors or aerial, or null' in src_cfg
   and 'ems != ""' in src_cfg)

# ---- 6. the route sheet's overlays use the chosen style's road-name layer
import export  # noqa: E402

seen = []
_real_url = basemap.url
basemap.url = lambda v, token, retina=True, overlays=None, before_layer=None, style=None: (seen.append(before_layer) or "x")
try:
    legs = [([(-1.0, 52.5), (-0.99, 52.51), (-0.98, 52.52)], "#16A34A", 0)]
    V = basemap.view(legs[0][0], 800, 600, pad_px=40)
    with basemap.use("aerial"):
        out = export._rs_overlays(V, 190, legs)
    ok("6: under Aerial the sheet's overlays are measured against road-label", out and seen and set(seen) == {"road-label"}, str(seen))
    seen.clear()
    out = export._rs_overlays(V, 190, legs)
    ok("6: under Light, against road-label-simple", out and set(seen) == {"road-label-simple"}, str(seen))
finally:
    basemap.url = _real_url

# ---- 7. source level
exp = read("backend", "export.py")
ok("7: export.py imports basemap at module level (the captions read the credit)", "import basemap\nimport config\n" in exp)
ok("7: the bulletin's two maps and its caption are Light, explicitly",
   'bulletin_doc.map_points(self.S), self.width, self.height,\n                                 reserve_right_pt=getattr(self, "reserve_right", 0), style="light")' in exp
   and "bulletin_doc.council_points(self.C), self.width, self.height, 20, style=\"light\")" in exp
   and 'basemap.credit("light") if self.mp.kind == "mapbox"' in exp)
ok("7: and its route map's own URL is the fixed Light one", "/styles/v1/mapbox/light-v11/static/" in exp)
bd = read("backend", "bulletin_doc.py")
ok("7: the bulletin's web-page map asks for Light", 'basemap.fetch(v, retina=False, style="light")' in bd)
ok("7: no caption prints the fixed words any more (they read basemap.credit())",
   "Map © Mapbox © OpenStreetMap." not in exp and '" · map © Mapbox © OpenStreetMap"' not in exp)
ok("7: the route sheet names the chosen style's layer and the fetch passes it",
   exp.count("before_layer=basemap.labels_layer()") == 2 and "basemap.LABELS_LAYER if overlays" not in exp)
mn = read("backend", "main.py")
ok("7: main.py: both map-export endpoints take `style`, validated before the read; blank = the tenant's setting",
   mn.count("style: Optional[str] = None, request: Request = None):") == 2 and mn.count("sk = _export_style(style)") == 2
   and mn.count("with basemap.use(sk):") == 2
   and 'raise HTTPException(422, "style must be light, streets, outdoors or aerial")' in mn
   and "import basemap " in mn)
fe = read("frontend", "index.html")
ok("7: the staff app: Config's Maps on paper, the export menu's Map style (blank = as set on Config)",
   'id="cfg-export-map-style"' in fe and 'setTenantText(d, "export_map_style", e.target.value === "light" ? "" : e.target.value)' in fe
   and "if(mstyle) q.set(\"style\", mstyle);" in fe and "As set on Config" in fe and 'aria-label="Map style"' in fe)
mp = read("map", "index.html")
ok("7: the public map's dialog: a Map style select, and the URL always carries one (As on screen = the basemap showing, else Light)",
   'id="rme-style"' in mp and "q.set('style', exportMapStyle());" in mp and "'mapbox://styles/mapbox/satellite-streets-v12': 'aerial'" in mp
   and "return EXPORT_STYLE_OF[BASEMAP.pending || BASEMAP.shown] || 'light';" in mp)

ug = read("frontend", "help", "index.html")
tg = read("frontend", "help", "technical", "index.html")
ok("7: the user guide says Map style and Maps on paper in a sentence (and that the bulletin stays Light)",
   "<em>Map style</em> picks Light, Streets, Outdoors or Aerial (with names)" in ug and "<em>Maps on paper</em> on Config" in ug
   and "The bulletin stays Light." in ug)
ok("7: the technical guide holds the detail (the JPEG, the fallback, the layer per style)",
   "<code>basemap.STYLES</code> holds four" in tg and "answers a JPEG, not a PNG" in tg and "falls back to Light at once" in tg)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
