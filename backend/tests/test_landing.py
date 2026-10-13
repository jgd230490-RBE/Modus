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
# REVERSED 13 Oct (landing v3): was overview < standards < readers < problems < not < demo.
ok("sections in the pack's order: problem, how it works, readers, planning layer, standards, demo",
   0 < src.find('id="top"') < src.find('id="problems"') < src.find('id="overview"') < src.find('id="readers"')
   < src.find('id="not"') < src.find('id="standards"') < src.find('id="demo"'))

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

# --- the three films (13 Oct, landing v3; notes/session-1013-landing-v3.md) ---------------------
# REVERSED 13 Oct: the 6 Oct page had two placeholder videos (the hero explainer and the overview
# product tour; both showed pre-UI screens and the word "truck"). Both files are deleted. "How it works"
# now holds three films, each a muted autoplay loop (browsers refuse autoplay with sound) with controls
# as the sound and pause buttons, playsinline for iOS, served from landing/films/.
FILMS = os.path.join(ROOT, "landing", "films")
videos = re.findall(r"<video\b[^>]*>", src)
ok("page has three videos, the three films", len(videos) == 3)
ok("🔴 the old placeholder videos are gone from the page and from landing/media",
   "explainer-overview" not in src and "hero-overview" not in src
   and not os.path.exists(os.path.join(ROOT, "landing", "media", "explainer-overview.mp4"))
   and not os.path.exists(os.path.join(ROOT, "landing", "media", "hero-overview.mp4")))
for n in (1, 2, 3):
    m = re.search(r'<div class="film" id="film-%d">(.*?)</div>\s*</div>' % n, src, re.S)
    block = m.group(1) if m else ""
    v = re.search(r"<video\b[^>]*>", block)
    v = v.group(0) if v else ""
    ok(f"film {n}: its block exists and holds one video", bool(v))
    ok(f"film {n}: plays ./films/film{n}.mp4", f'src="./films/film{n}.mp4"' in v)
    for attr in ("autoplay", "muted", "loop", "playsinline", "controls"):
        ok(f"film {n}: video is {attr}", re.search(r"\b%s\b" % attr, v) is not None)
    ok(f"film {n}: aria-label says the fictional demo scheme", re.search(r'aria-label="[^"]*fictional demo scheme', v) is not None)
    ok(f"film {n}: has a poster that exists", any(os.path.exists(os.path.join(ROOT, "landing", r))
       for r in re.findall(r'poster="\./([^"]+)"', v)))
    ok(f"film {n}: the narration is on the page as a transcript", "<summary>Read the narration</summary>" in block)
    path = os.path.join(FILMS, f"film{n}.mp4")
    head = open(path, "rb").read(65536) if os.path.exists(path) else b""
    ok(f"⭐ film {n}: landing/films/film{n}.mp4 exists (the user supplies the films)", os.path.exists(path))
    # moov before mdat = "faststart": the browser can start playing before the whole file lands.
    ok(f"film {n}: an MP4 with faststart", head[4:8] == b"ftyp" and 0 < head.find(b"moov") < (head.find(b"mdat") if b"mdat" in head else 1 << 30))
    # GitHub warns above 50 MB and refuses above 100 MB; three autoplaying films load on every visit.
    ok(f"film {n}: under 50 MB", os.path.exists(path) and os.path.getsize(path) < 50 * 1024 * 1024)
ok("each film file is used once", len(set(re.findall(r'src="\./films/([^"]+\.mp4)"', src))) == 3)
ok("the films come in page order, inside How it works",
   src.find('id="overview"') < src.find('id="film-1"') < src.find('id="film-2"') < src.find('id="film-3"') < src.find('id="readers"'))
_body = " ".join(p.text)
ok("no media placeholder text left on the page", "[SCREEN RECORDING" not in _body and "[EXPLAINER" not in src
   and "placeholder]" not in _body.lower())
ok("the films note says all three are the fictional demo scheme",
   "All three films are recorded on the fictional demo scheme. Nothing in them is a real project." in _body)
# 11 Oct 2026 (the user): the map is the "public map" everywhere a person reads its name, landing page included.
# NARROWED 13 Oct: the two 11 Oct sentences went with the old copy; the name rule stays.
ok("the landing page says 'public map', never 'corridor map' (copy and the labels)",
   "corridor map" not in src.lower() and "shared public map that opens with one password you hand out" in src)
# REVERSED 13 Oct: five stills, one per problem, became three: the hero (the public map) and the two
# Film 2 screens (forecast submissions, the Look-ahead clash rail). The two unused stills are deleted.
import pathlib
_still_path = lambda n: pathlib.Path(ROOT, "landing", "media", n + ".jpg")
_STILLS = ("still-routes", "still-fairprice", "still-lookahead")
_still_tags = re.findall(r'<figure class="shot"[^>]*>\s*<a href="\./media/([\w-]+)\.jpg"[^>]*><img ([^>]*)></a>', src)
ok("three stills, each linking to its own full-size image, in page order",
   [h for h, _ in _still_tags] == list(_STILLS)
   and all('src="./media/%s.jpg"' % h in t for h, t in _still_tags))
_still_tags = [t for _, t in _still_tags]
ok("⭐ every still's alt text says it is the fictional demo scheme",
   len(_still_tags) == 3 and all(re.search(r'alt="[^"]*fictional demo scheme[^"]*"', t) for t in _still_tags))
ok("...and the map still's alt text calls it the public map, not the route map",
   'alt="The public map on the fictional demo scheme' in src and not re.search(r'alt="[^"]*route map', src, re.I))
ok("every still has width and height (no layout jump); the two below the fold load lazily",
   all('width="' in t and 'height="' in t for t in _still_tags)
   and all('loading="lazy"' in t for t in _still_tags[1:]))
ok("each still exists as a JPEG under 200 KB",
   all(_still_path(n).is_file() and _still_path(n).read_bytes()[:3] == b"\xff\xd8\xff"
       and _still_path(n).stat().st_size < 200 * 1024 for n in _STILLS))
ok("🔴 the two stills the page no longer shows are deleted (still-carbon, still-fleet)",
   not _still_path("still-carbon").exists() and not _still_path("still-fleet").exists())
# REVERSED 13 Oct: the 8 Oct overview had four steps, Plan / Approve / Share / Record.
ok("🔴 the Plan / Approve / Share / Record steps are gone", all(f"<b>{s}</b>" not in src for s in ("Plan", "Approve", "Share", "Record")))
ok("How it works has the four-step bar: Locate & route, Forecast & flag, Confirm week, Share",
   src.count('class="steps"') == 1
   and all(f">{s}</a></li>" in src for s in ("Locate &amp; route", "Forecast &amp; flag", "Confirm week", "Share")))

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
    # 13 Oct (the landing pack's banned list): the first client's names, as test_modus.py spells them.
    (r"Rail\s?Baltic", "the first client's project name"),
    (r"\bNGE\b", "the first client's contractor name"),
    (r"\bAlliance\s?1\b", "the first client's alliance name"),
]
for pat, name in BANNED:
    ok(f"no banned word: {name}", not re.search(pat, body, re.I))
ok("page says the demo is fictional", re.search(r"fictional", body, re.I) is not None)
ok("page carries the sources paragraph", "DESNZ" in body and "RIS3" in body)
ok("page uses British spelling (programme)", "programme" in body and "program " not in body)

# --- standards: named, never claimed (8 Oct; rewritten 13 Oct) -----------------------------
# REVERSED 13 Oct (the landing pack; the user, 13 Oct): the disclaimer no longer says "accredited by,
# endorsed by", and the NH card no longer says "has not reviewed or endorsed". Neither word is on the
# page at all now. The disclaimer says the bodies are independent and none of them has reviewed Wayscope.
DISCLAIMER = "Wayscope is independent of every organisation named here, and none of them has reviewed Wayscope."
flat = re.sub(r"\s+", " ", body)
ok("the standards disclaimer ships, under the standards AND in the footer", flat.count(DISCLAIMER) == 2)
ok("🔴 the 8 Oct disclaimer and the NH small print are gone",
   "not accredited by, endorsed by" not in flat and "has not reviewed or endorsed" not in flat)
ok("the standards disclaimer is in #standards", src.find('id="standards"') < src.find(DISCLAIMER.replace("'", "'")) < src.find('id="demo"'))
ok("#standards names the documents", all(w in flat for w in ("The CLOCS Standard", "FORS Standard v7.2",
   "National Highways Carbon Tool", "PAS 2080", "RIS3 performance specification", "CTMPs and planning conditions")))
# REVERSED 13 Oct: five cards (CLOCS, FORS, NH, officers, CILT/CIOB) became five named documents in a list.
ok("#standards lists five documents, no cards", src.count('<ul class="chips">') == 1
   and len(re.findall(r"<li>", src[src.find('<ul class="chips">'):src.find("</ul>", src.find('<ul class="chips">'))])) == 5
   and '<article class="standard">' not in src)
ok("🔴 CILT and CIOB are no longer named (the pack dropped that block)", "CILT" not in flat and "CIOB" not in flat)
ok("the CLOCS Standard is named with no version number", "CLOCS Standard v" not in flat and not re.search(r"CLOCS[^.]{0,20}\bv\d", flat))
ok("the readers section has four readers: CLOCS, FORS, National Highways, Local authorities",
   len(re.findall(r'<article class="reader">', src)) == 4
   and all(f'<p class="eyebrow">{r}</p>' in src for r in ("CLOCS", "FORS", "National Highways", "Local authorities")))
ok("each reader card says what stays with the reader", src.count("<b>What stays with you:</b>") == 4)
# NARROWED 13 Oct: there is nothing to strip now; no claim word may appear anywhere on the page.
for pat, name in [(r"\bcompliant\b", "compliant"), (r"\bapproved by\b", "approved by"),
                  (r"\baccredit", "accredited / accreditation"), (r"\bcertif", "certified / certification"),
                  (r"\bendorse", "endorsed / endorsement")]:
    ok(f"no standard is claimed: '{name}' never appears on the page", not re.search(pat, flat, re.I))
# 13 Oct: the scan above reads text nodes only; an aria-label once said "approved by". Attributes too.
_attrs = " ".join(re.findall(r'(?:alt|aria-label|placeholder|title|content)="([^"]*)"', src))
for pat, name in BANNED + [(r"compliant", "compliant"), (r"approved by", "approved by"),
                           (r"accredit", "accredited"), (r"certif", "certified"), (r"endorse", "endorsed")]:
    ok(f"no banned word in alt / aria-label / placeholder / title / meta: {name}", not re.search(pat, _attrs, re.I))
ok("no logos of the named bodies (the only images are Wayscope's own)",
   all(s.startswith("./assets/") or s.startswith("./media/") or s.startswith("./films/") for s in p.srcs if s.startswith("./")))

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

# --- 11 Oct review (notes/landing-review-1011.md L2, L6): no claim to a Carbon Tool export ---
# H3, the Carbon Tool export, is not built. The page may say how Wayscope HOLDS a haul (quantity and
# one-way distance per origin and destination); it may not say the figures are a return or ready for one.
_low = body.lower()
ok("🔴 no claim that the figures are already in the Carbon Tool's form or prepared for entry into it",
   "already in the form the carbon tool" not in _low and "prepared for entry into the carbon tool" not in _low
   and "in the form the carbon tool asks for" not in _low)
ok("🔴 no placeholder or caption promising a carbon export", not re.search(r"carbon[^.]{0,40}\bexport", _low))
ok("...and the page says plainly the figures are planning estimates, not a Carbon Tool return",
   "not a Carbon Tool return" in body and "your Carbon Tool return stays your own" in body)
# REVERSED 13 Oct (the landing pack, item 11): the Carbon planner, fair price, fleet sizing and gate arrivals
# are built but sit outside the three films, so the page no longer names them.
ok("🔴 the Carbon planner is no longer on the landing page", "Carbon planner" not in body)
# NARROWED 13 Oct: the look-ahead line now says the commitment is recorded as held or short.
ok("the look-ahead copy no longer promises that declared disruption is what occurs",
   "the disruption that occurs" not in _low and "recorded as held or short" in body)

# --- 13 Oct (the landing pack, notes/session-1013-landing-v3.md): v3 copy rules ---------------
# Taglines (the user, 13 Oct): "Every movement in scope." in the hero eyebrow and the footer;
# "Organisation before movement." above the closing demo request. "Every load in scope." is retired.
ok("⭐ 'Every movement in scope.' is the hero eyebrow", '<p class="eyebrow">Every movement in scope.</p>' in src
   and src.find("Every movement in scope.</p>") < src.find("<h1>"))
ok("...and the footer tagline", '<p class="tagline">Every movement in scope.</p>' in src[src.find("<footer"):])
ok("🔴 'Every load in scope' is gone, og:title included", "every load in scope" not in src.lower())
ok("'Organisation before movement.' sits above the demo heading",
   src.find('id="demo"') < src.find("Organisation before movement.") < src.find("See it on a fictional demo scheme."))
ok("the h1 is the agreed headline", "<h1>Plan every lorry movement. Evidence every plan.</h1>" in src)
# The CLOCS card (live-page fix): never "the plan you approve".
ok("🔴 no 'the plan you approve' anywhere", "the plan you approve" not in _low)
# RIS3: a tool only supports the seven-day horizon; the KPI is National Highways' own.
ok("RIS3: 'supports the seven-day planning horizon', never meets or delivers it",
   "supports the seven-day planning horizon in RIS3" in flat
   and not re.search(r"\b(meets?|deliver(s|ed)?|achieves?)\b[^.]{0,40}seven-day", flat, re.I))
# Ported from claude/landing-overreach (13 Oct, superseded by this page): three overclaims stay out.
ok("🔴 no weight limits claimed (none is ever flagged)", "weight limit" not in _low)
ok("🔴 'they don't need an account' stays gone", "don't need an account" not in _low)
ok("🔴 no 'carbon you can report'", "carbon you can report" not in _low)
ok("the public map always comes with its password: hero, Film 3 and the planning list",
   flat.count("opens with one password you hand out") >= 3)
# Built today vs not (4-rules/platform-truth.md §8): no import, no bulletin, no holding areas, no Carbon Tool export.
ok("🔴 import is not claimed as a feature; the page says there is none today",
   "There is no import today" in flat and "import from your booking system is set up" not in _low)
ok("🔴 no bulletin and no holding areas on the page", "bulletin" not in _low and "holding area" not in _low)
ok("🔴 TROs and Street Manager appear only as what stays with the reader or the reader's systems",
   all(("What stays with you" in flat[max(0, m.start() - 160):m.start()]) or ("Permits, TROs and Street Manager" in flat[max(0, m.start() - 20):m.end() + 5])
       for m in re.finditer(r"Street Manager", flat)))
ok("actuals are typed, never counted or tracked", "Actuals are typed in, as held or short, not counted or tracked." in flat)
ok("the carbon line says 'holds the inputs the Carbon Tool asks for'", "holds the inputs the Carbon Tool asks for" in flat)
ok("closures are National Highways planned closures only, flagged, never blocked",
   "National Highways planned closures" in flat and "flagged, never blocked" in flat)
# The user, 13 Oct: the clash rail sits on the Look-ahead and runs before Confirm week, not before approval.
ok("🔴 Film 2 no longer says the clash is found before approval",
   "find the clash before approval" not in _low and "Find the clash before the week is confirmed." in flat)
ok("...and no screen caption puts the clash rail on the forecast submissions",
   "forecast submissions with clash rail" not in _low and "forecast submissions + clash rail" not in _low)
# No prices (the pack's agreed decisions).
ok("no prices on the page: no £, no 'per month', no 'pricing'",
   "£" not in flat and "per month" not in _low and "pricing" not in _low and "fair price" not in _low)
# The demo CTA: every "Request a demo" button goes to the form; the address is the fallback.
ok("'Request a demo' is in the nav and the hero, and each one goes to #demo",
   len(re.findall(r'href="#demo">Request a demo</a>', src)) >= 2 and 'href="#demo"' in src)
ok("'Watch the films' goes to How it works", 'href="#overview">Watch the films</a>' in src)
ok("the demo band offers the email address beside the form", 'Or write to <a href="mailto:JDavis@wayscope.co.uk">' in src)
ok("one <main> on the page", src.count("<main") == 1)

# --- the placeholders that still need the user's facts ---------------------------
placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z 0-9:,\-]+\]", body)))
print("placeholders still on the page:", ", ".join(placeholders) or "none")

print(f"test_landing.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
