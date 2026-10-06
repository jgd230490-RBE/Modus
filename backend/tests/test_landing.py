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
for needed in ("readers", "problems", "demo"):
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
       if "wayscope.co.uk" not in u))

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
ok("page links to the demo host", any("demo.wayscope.co.uk" in h for h in p.hrefs))
ok("page carries the sources paragraph", "DESNZ" in body and "RIS3" in body)
ok("page uses British spelling (programme)", "programme" in body and "program " not in body)

# --- the placeholders that still need the user's facts ---------------------------
placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z 0-9:,\-]+\]", body)))
print("placeholders still on the page:", ", ".join(placeholders) or "none")

print(f"test_landing.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
