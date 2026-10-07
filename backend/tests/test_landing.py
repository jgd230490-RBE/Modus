"""Landing page (landing/) — source-level assertions.

Run from the repo root:  python3 backend/tests/test_landing.py

What this proves: landing/index.html exists, parses as HTML, has a title, an h1 and the
section anchors the nav links to; every local asset it references is present in
landing/assets/; it carries the banned-words rules from claude/messaging-0929.md §7 (no
"secure", no "Modus", no "trusted by", no testimonials, no "real-time", no "AI", no
"optimise", no "predict", no telematics); it says "fictional" and links to the demo host;
it loads no script; and main.py mounts /landing before the catch-all "/".

What it does not prove: that Starlette serves the mount, that the Render static site is
configured, or how the page looks in a browser (the sandbox cannot render the fonts).
"""
import os
import re
import sys
from html.parser import HTMLParser

# Where the demo scheme runs (7 Oct): the app on app.wayscope.co.uk. wayscope.co.uk itself
# is this landing page; demo.wayscope.co.uk has no DNS record. Change page and test together.
DEMO_URL = "https://app.wayscope.co.uk/"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "backend", "main.py")
PAGE = os.path.join(ROOT, "landing", "index.html")
ASSETS = os.path.join(ROOT, "landing", "assets")

passed = failed = 0


def ok(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL:", label)


# --- the mount -----------------------------------------------------------------
main_src = open(MAIN, encoding="utf-8").read()
landing_mount = main_src.find('app.mount("/landing"')
root_route = main_src.find('@app.get("/")')
ok("main.py mounts /landing", landing_mount > 0)
ok("/landing is mounted before the catch-all /", 0 < landing_mount < root_route)
ok("/landing mount tolerates a missing folder (check_dir=False)",
   "check_dir=False" in main_src[landing_mount:landing_mount + 200])

# --- the page parses -----------------------------------------------------------
ok("landing/index.html exists", os.path.exists(PAGE))
src = open(PAGE, encoding="utf-8").read() if os.path.exists(PAGE) else ""


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.tags = []
        self.ids = set()
        self.hrefs = []
        self.srcs = []
        self.text = []
        self.scripts = 0
        self.imgs_without_alt = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if tag == "title":
            self.in_title = True
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        if tag in ("img", "video", "source") and "src" in a:
            self.srcs.append(a["src"])
        if tag == "link" and "href" in a:
            self.srcs.append(a["href"])
        if tag == "meta" and a.get("property") == "og:image":
            self.srcs.append(a.get("content", ""))
        if tag == "script":
            self.scripts += 1
        if tag == "img" and not a.get("alt"):
            self.imgs_without_alt += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        self.text.append(data)


p = P()
try:
    p.feed(src)
    parsed = True
except Exception as e:  # pragma: no cover
    parsed = False
    print("parse error:", e)
ok("page parses as HTML", parsed)
ok("page has a title naming Wayscope", "Wayscope" in p.title)
ok("page has one h1", p.tags.count("h1") == 1)
ok("page has h2 sections", p.tags.count("h2") >= 4)
ok("every img has alt text", p.imgs_without_alt == 0)
ok("page loads no script", p.scripts == 0)
ok("page declares a viewport", 'name="viewport"' in src)
ok("page has og:image and og:title", 'property="og:image"' in src and 'property="og:title"' in src)

# --- anchors resolve -----------------------------------------------------------
for h in p.hrefs:
    if h.startswith("#"):
        ok(f"anchor {h} exists on the page", h[1:] in p.ids)
for needed in ("overview", "readers", "problems", "demo"):
    ok(f"section #{needed} exists", needed in p.ids)

# --- local assets exist ----------------------------------------------------------
local = [s for s in p.srcs if s.startswith("./")]
ok("page references local assets", len(local) >= 4)
for s in local:
    ok(f"asset present: {s}", os.path.exists(os.path.join(ROOT, "landing", s[2:])))
ok("no absolute /brand/ paths (the page must work as a standalone static site)",
   "/brand/" not in src)
ok("only Google Fonts is loaded from the network",
   all(u.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com"))
       for u in re.findall(r'href="(https://[^"]+)"', src)
       if "wayscope.co.uk" not in u and u != DEMO_URL))

# --- the two placeholder videos (6 Oct) -------------------------------------------
# Hero: the silent animated explainer, muted autoplay loop (browsers refuse autoplay with
# sound), playsinline for iOS, controls as the pause button. Overview: the product tour,
# which has a sound track, click to play. Neither is repeated elsewhere on the page.
MEDIA = os.path.join(ROOT, "landing", "media")
videos = re.findall(r"<video\b[^>]*>", src)
ok("page has two videos", len(videos) == 2)
def video_in(frame_id):
    m = re.search(r'id="%s"[^>]*>\s*(<video\b[^>]*>)' % frame_id, src)
    return m.group(1) if m else ""
hv = video_in("hero-media")
ok("hero frame holds the explainer", "./media/explainer-overview.mp4" in hv)
for attr in ("autoplay", "muted", "loop", "playsinline", "controls"):
    ok(f"hero video is {attr}", re.search(r"\b%s\b" % attr, hv) is not None)
ov = video_in("overview-media")
ok("overview frame holds the product tour", "./media/hero-overview.mp4" in ov)
ok("overview video does not autoplay (it has sound)", "autoplay" not in ov)
ok("overview video has controls", "controls" in ov)
ok("overview comes before the readers and problems sections",
   0 < src.find('id="overview"') < src.find('id="readers"') < src.find('id="problems"'))
ok("'See how it works' goes to the overview", 'href="#overview">See how it works' in src)
ok("each video file is used once", len(set(re.findall(r'src="\./media/([^"]+\.mp4)"', src))) == 2)
for v in videos:
    ok("every video has an aria-label", 'aria-label="' in v)
    ok("every video has a poster", 'poster="./media/' in v)
    ok("every video says fictional in its label", "fictional" in v)
    for ref in re.findall(r'(?:src|poster)="\./([^"]+)"', v):
        ok(f"media file present: {ref}", os.path.exists(os.path.join(ROOT, "landing", ref)))
for name in ("hero-overview.mp4", "explainer-overview.mp4"):
    path = os.path.join(MEDIA, name)
    head = open(path, "rb").read(65536) if os.path.exists(path) else b""
    # moov before mdat = "faststart": the browser can start playing before the whole file lands.
    ok(f"{name} is an MP4 with faststart", head[4:8] == b"ftyp" and 0 < head.find(b"moov") < (head.find(b"mdat") if b"mdat" in head else 1 << 30))
    ok(f"{name} is under 10 MB", os.path.exists(path) and os.path.getsize(path) < 10 * 1024 * 1024)
_body = " ".join(p.text)
ok("no media placeholder text left in the hero", "[SCREEN RECORDING" not in _body)
ok("explainers 1-5 still marked as placeholders",
   all(f"[EXPLAINER {n}" in _body for n in (1, 2, 3, 4, 5)))

# --- wording rules (claude/messaging-0929.md §7) -----------------------------------
body = " ".join(p.text)
BANNED = [
    (r"\bsecur(e|ed|ity|ely)\b", "secure / security (not until G3)"),
    (r"\bModus\b", "Modus"),
    (r"\btrusted by\b", "trusted by"),
    (r"\btestimonial", "testimonials"),
    (r"\breal[- ]time\b", "real-time"),
    (r"\bAI\b", "AI"),
    (r"\boptimi[sz]", "optimise"),
    (r"\bpredict", "predict"),
    (r"\btelematics\b", "telematics"),
    (r"\blive tracking\b", "live tracking"),
    (r"\btruck", "truck (UK copy says lorry / HGV)"),
]
for pat, name in BANNED:
    ok(f"no banned word: {name}", not re.search(pat, body, re.I))
ok("page says the demo is fictional", re.search(r"fictional", body, re.I) is not None)
ok("page links to the demo host", DEMO_URL in p.hrefs)
ok("page does not link to a raw onrender.com host", not any("onrender.com" in h for h in p.hrefs))
ok("page does not link to demo.wayscope.co.uk (no DNS record)",
   not any("demo.wayscope.co.uk" in h for h in p.hrefs))
ok("page carries the sources paragraph", "DESNZ" in body and "RIS3" in body)
ok("page uses British spelling (programme)", "programme" in body and "program " not in body)

# --- the placeholders that still need the user's facts ---------------------------
placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z 0-9:,\-]+\]", body)))
print("placeholders still on the page:", ", ".join(placeholders) or "none")

print(f"test_landing.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
