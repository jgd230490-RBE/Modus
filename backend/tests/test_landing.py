"""Landing page (landing/) — source-level assertions.

Run from the repo root:  python3 backend/tests/test_landing.py

What this proves: landing/index.html exists, parses as HTML, has a title, an h1 and the
section anchors the nav links to; every local asset it references is present in
landing/assets/; it carries the banned-words rules from claude/messaging-0929.md §7 (no
"secure", no "Modus", no "trusted by", no testimonials, no "real-time", no "AI", no
"optimise", no "predict", no telematics) plus the 8 Oct rules (no "Highways Agency" /
"Highways England", standards named but never claimed); it says "fictional"; it loads no
script; the demo-request form posts to the app with the fields the copy specifies and no
code printed on the page; privacy.html, thanks.html and error.html exist and parse; and
main.py mounts /landing before the catch-all "/".

What it does not prove: that Starlette serves the mount, that the Render static site is
configured, that the demo-request endpoint exists (H9), or how the page looks in a browser.
"""
import os
import re
import sys
from html.parser import HTMLParser

# Where the demo scheme runs (7 Oct): the app on app.wayscope.co.uk. wayscope.co.uk itself
# is this landing page; demo.wayscope.co.uk has no DNS record. Change page and test together.
DEMO_URL = "https://app.wayscope.co.uk/"
# 8 Oct (H5c/H9): the form posts here; the codes travel only in the email the app sends.
DEMO_REQUEST_ACTION = DEMO_URL + "api/public/demo-request"
LANDING_URL = "https://wayscope.co.uk/"
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
        self.forms = []          # dicts of attrs
        self.fields = []         # (tag, attrs) for input / select / textarea / button
        self.options = []        # option text, in order
        self.in_option = False
        self.og_image = ""

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
            self.og_image = a.get("content", "")
        if tag == "script":
            self.scripts += 1
        if tag == "img" and not a.get("alt"):
            self.imgs_without_alt += 1
        if tag == "form":
            self.forms.append(a)
        if tag in ("input", "select", "textarea", "button"):
            self.fields.append((tag, a))
        if tag == "option":
            self.in_option = True
            self.options.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "option":
            self.in_option = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_option and self.options:
            self.options[-1] += data
        self.text.append(data)


def parse(path):
    q = P()
    q.feed(open(path, encoding="utf-8").read())
    return q


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
ok("page has h2 sections", p.tags.count("h2") >= 6)
ok("every img has alt text", p.imgs_without_alt == 0)
ok("page loads no script (a plain HTML form POST and a redirect need none)", p.scripts == 0)
ok("page declares a viewport", 'name="viewport"' in src)
ok("page has og:image and og:title", 'property="og:image"' in src and 'property="og:title"' in src)
# 8 Oct: absolute, so a link preview on LinkedIn / Teams / WhatsApp finds the image wherever the
# page is shared; and the file it names is the one in landing/assets.
ok("og:image is an absolute URL on wayscope.co.uk", p.og_image.startswith(LANDING_URL + "assets/"))
ok("og:image names a file that exists in landing/assets",
   os.path.exists(os.path.join(ROOT, "landing", p.og_image[len(LANDING_URL):])) if p.og_image.startswith(LANDING_URL) else False)

# --- anchors resolve -----------------------------------------------------------
for h in p.hrefs:
    if h.startswith("#"):
        ok(f"anchor {h} exists on the page", h[1:] in p.ids)
for needed in ("overview", "standards", "readers", "problems", "not", "demo"):
    ok(f"section #{needed} exists", needed in p.ids)
for nav in ("#overview", "#standards", "#readers", "#demo"):
    ok(f"nav links to {nav}", nav in p.hrefs)

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
ok("overview comes before standards, readers and problems",
   0 < src.find('id="overview"') < src.find('id="standards"') < src.find('id="readers"') < src.find('id="problems"'))
ok("the 'what it is not' band sits between the problems and the demo request",
   src.find('id="problems"') < src.find('id="not"') < src.find('id="demo"'))
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
ok("the overview has four steps, Plan / Approve / Share / Record (8 Oct)",
   all(f"<b>{s}</b>" in src for s in ("Plan", "Approve", "Share", "Record")) and src.count('class="steps"') == 1)

# --- wording rules (claude/messaging-0929.md §7 + landing-copy-v2-1008.md §6) -----------
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
    # 8 Oct: the body was the Highways Agency until 2015 and Highways England until 2021.
    (r"\bHighways Agency\b", "Highways Agency (it is National Highways)"),
    (r"\bHighways England\b", "Highways England (it is National Highways)"),
]
for pat, name in BANNED:
    ok(f"no banned word: {name}", not re.search(pat, body, re.I))
ok("page says the demo is fictional", re.search(r"fictional", body, re.I) is not None)
ok("page carries the sources paragraph", "DESNZ" in body and "RIS3" in body)
ok("page uses British spelling (programme)", "programme" in body and "program " not in body)

# --- standards: named, never claimed (8 Oct) ------------------------------------------
DISCLAIMER = ("CLOCS, FORS, National Highways, CILT and CIOB are named to describe requirements and "
              "practice that Wayscope helps you meet. Wayscope is not accredited by, endorsed by or "
              "affiliated with any of them.")
NH_SMALL_PRINT = "National Highways has not reviewed or endorsed Wayscope."
flat = re.sub(r"\s+", " ", body)
ok("the standards disclaimer ships, under the cards AND in the footer", flat.count(DISCLAIMER) == 2)
ok("the National Highways card says NH has not reviewed or endorsed Wayscope", NH_SMALL_PRINT in flat)
ok("#standards names the five bodies", all(w in flat for w in ("CLOCS", "FORS", "National Highways", "CILT", "CIOB")))
ok("#standards has five cards", len(re.findall(r'<article class="standard">', src)) == 5)
ok("the readers section has four readers (was three)", len(re.findall(r'<article class="reader">', src)) == 4)
# Strip the two negated sentences, then no claim word may remain anywhere on the page.
_claims = flat.replace(DISCLAIMER, "").replace(NH_SMALL_PRINT, "")
for pat, name in [(r"\bcompliant\b", "compliant"), (r"\bapproved by\b", "approved by"),
                  (r"\baccredit", "accredited / accreditation"), (r"\bcertif", "certified / certification"),
                  (r"\bendorsed\b", "endorsed")]:
    # "accreditation" is allowed only in the CLOCS card's honest-scope line about what Wayscope does NOT hold.
    hits = [m.start() for m in re.finditer(pat, _claims, re.I)]
    if name.startswith("accredit"):
        hits = [h for h in hits if "vehicle and driver accreditation" not in _claims[max(0, h - 30):h + 30]]
    ok(f"no standard is claimed: '{name}' never appears except in the disclaimer", not hits)
ok("no logos of the named bodies (the only images are Wayscope's own)",
   all(s.startswith("./assets/") or s.startswith("./media/") for s in p.srcs if s.startswith("./")))

# --- the event is not on the page (8 Oct: the page is for everyone) ---------------------
# REVERSED 8 Oct: the 6 Oct page carried the Highways UK pill and an "At the stand" tile.
ok("page does not name Highways UK, the NEC or a stand",
   not re.search(r"Highways UK|\bNEC\b|\bstand\b|STAND NUMBER", body))

# --- no code on the page; the request form instead (8 Oct) ------------------------------
# REVERSED 8 Oct: the 7 Oct page printed [MAP CODE] / [TEAM CODE] tiles and a planner line.
ok("no code tile and no code placeholder on the page",
   'class="tile"' not in src and not re.search(r"MAP CODE|TEAM CODE|PLANNER CODE|PLANNER_CODE|MAP_PASSWORD|IPT[1-6]_CODE", src))
ok("the page does not print the words 'password' or 'code' next to a value",
   not re.search(r"(password|code)\s*[:=]\s*\S", body, re.I))
# REVERSED 8 Oct: the page no longer links straight to the app; the link travels in the email.
ok("page does not link straight to the demo host (access travels by email)", DEMO_URL not in p.hrefs)
ok("page does not link to a raw onrender.com host", not any("onrender.com" in h for h in p.hrefs))
ok("page does not link to demo.wayscope.co.uk (no DNS record)",
   not any("demo.wayscope.co.uk" in h for h in p.hrefs))

ok("exactly one form on the page", len(p.forms) == 1)
form = p.forms[0] if p.forms else {}
ok("the form POSTs to the app's demo-request endpoint",
   form.get("method", "").lower() == "post" and form.get("action") == DEMO_REQUEST_ACTION)
ok("the form is inside #demo", src.find('id="demo"') < src.find("<form") < src.find("</form>"))
names = {a.get("name"): (t, a) for t, a in p.fields if a.get("name")}
for n in ("name", "email", "organisation", "role"):
    ok(f"required field '{n}'", n in names and "required" in names[n][1])
ok("the email field is type=email", names.get("email", ("", {}))[1].get("type") == "email")
ok("the role field is a select with the seven roles from the copy",
   names.get("role", ("", {}))[0] == "select"
   and [o.strip() for o in p.options if o.strip() and o.strip() != "Choose one"] ==
   ["Client or highway authority", "Principal contractor", "Logistics or site management",
    "Haulier or fleet operator", "Local authority officer", "Consultant", "Other"])
ok("'what would you like to see' is optional", "wants" in names and "required" not in names["wants"][1])
ok("the updates tick box exists, is a checkbox and is UNTICKED by default",
   names.get("updates", ("", {}))[1].get("type") == "checkbox" and "checked" not in names["updates"][1])
ok("every text field has a length cap", all("maxlength" in a for t, a in p.fields if t == "input" and a.get("type") in (None, "text", "email")))
ok("a honeypot field exists for the server to reject bots on (H9)",
   "website" in names and 'class="hp"' in src and "tabindex" in names["website"][1])
ok("the submit button says what happens", any(t == "button" and a.get("type") == "submit" for t, a in p.fields)
   and "Email me the demo access" in body)
ok("the form links the privacy notice and warns that the access details are shared",
   "./privacy.html" in p.hrefs and "shared between everyone viewing the demo" in flat)

# --- the three support pages (8 Oct) ----------------------------------------------------
for fn, must in (("privacy.html", ("ico.org.uk", "24 months", "JDavis@wayscope.co.uk", "no tracking cookies")),
                 ("thanks.html", ("Check your inbox", "junk", "JDavis@wayscope.co.uk")),
                 ("error.html", ("didn't go through", "JDavis@wayscope.co.uk"))):
    path = os.path.join(ROOT, "landing", fn)
    ok(f"{fn} exists", os.path.exists(path))
    if os.path.exists(path):
        q = parse(path)
        txt = re.sub(r"\s+", " ", " ".join(q.text))
        ok(f"{fn} parses, names Wayscope and loads no script", "Wayscope" in q.title and q.scripts == 0)
        for m in must:
            ok(f"{fn} says '{m}'", m in txt)
        ok(f"{fn} links back to the landing page", any(h in ("./", "./#demo") for h in q.hrefs))
        for s in [s for s in q.srcs if s.startswith("./")]:
            ok(f"{fn} asset present: {s}", os.path.exists(os.path.join(ROOT, "landing", s[2:])))
        ok(f"{fn} is not indexed", 'name="robots" content="noindex"' in open(path, encoding="utf-8").read())
ok("the footer links the privacy notice", src.rfind('href="./privacy.html"') > src.find("<footer"))

# --- footer (7 Oct decisions) ------------------------------------------------------------
ok("contact email is JDavis@wayscope.co.uk, as a mailto link and as visible text",
   "mailto:JDavis@wayscope.co.uk" in p.hrefs and "JDavis@wayscope.co.uk" in body)
ok("no [EMAIL] or [COMPANY NAME AND NUMBER] placeholder left", "[EMAIL]" not in body and "[COMPANY NAME" not in body)
ok("company line is plain Wayscope: no company number, no Ltd / Limited",
   re.search(r"[Cc]ompany (No|no|number)", body) is None and " Ltd" not in body and "Limited" not in body)
# NARROWED 8 Oct: the planner code is not on the page at all (the 7 Oct "Not published" tile went
# with the rest of the code tiles); the code names are asserted absent above.
ok("the planner code is NOT published", "[PLANNER CODE]" not in body and "PLANNER_CODE" not in body)

# --- the placeholders that still need the user's facts ---------------------------
placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z 0-9:,\-]+\]", body)))
print("placeholders still on the page:", ", ".join(placeholders) or "none")

print(f"test_landing.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
