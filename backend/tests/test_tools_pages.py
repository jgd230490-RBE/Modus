"""
test_tools_pages.py — the public tool pages' frame (claude/tools-shell, 16 Nov 2026). No FastAPI needed: the pages, the
shared files, the wording, tools_public's rules and its limit, and the pins in main.py, the headers, the gate, the guide
and the UI audit. The real app's side (the gate ON, no cookie, the headers on the answers, no cookie set, the 404s, a
sample open call's limit) is smoke_tools_pages.py.

    python backend/tests/test_tools_pages.py

Every page under frontend/tools/ is checked, and so is the sample page backend/tests/tools_sample/calculators.html (the
mockup's card 2 laid out in the frame, never shipped), so the frame's checks run on real content before any tool exists.
A tool branch that adds a page gets every check below for free, and must add its page to ui_audit.js TOOL_PAGES.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import gate  # noqa: E402
import tools_public  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:600])


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


TOOLS = ROOT / "frontend" / "tools"
SAMPLE = HERE / "tools_sample" / "calculators.html"
SHIPPED_PAGES = sorted(TOOLS.glob("*.html"))
PAGES = SHIPPED_PAGES + [SAMPLE]

# =========================================================================== #
#  1. the folder and the shared files                                          #
# =========================================================================== #
ok("the frame's folder holds the shared stylesheet and script", (TOOLS / "tools.css").is_file() and (TOOLS / "tools.js").is_file())
_kinds = sorted({p.suffix for p in TOOLS.iterdir() if p.is_file()})
ok("the folder holds pages, the stylesheet, the script and nothing else", set(_kinds) <= {".html", ".css", ".js", ".md"}, str(_kinds))
ok("🔴 the sample page is NOT shipped (it lives under backend/tests/)", not (TOOLS / "calculators.html").exists()
   or "TEST ONLY" not in (TOOLS / "calculators.html").read_text(encoding="utf-8"))
ok("🔴 no index page in the folder (the Tools index is the landing site's)", not (TOOLS / "index.html").exists())
ok("every page's name is its address: lower case, digits and dashes",
   all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", p.stem) for p in SHIPPED_PAGES), str([p.name for p in SHIPPED_PAGES]))
ok("tools_public.pages() lists exactly the shipped pages", tools_public.pages() == [p.stem for p in SHIPPED_PAGES],
   str(tools_public.pages()))

CSS = (TOOLS / "tools.css").read_text(encoding="utf-8")
JS = (TOOLS / "tools.js").read_text(encoding="utf-8")
_css_nc = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
ok("tools.css: the braces balance", _css_nc.count("{") == _css_nc.count("}") and _css_nc.count("{") > 50)
ok("🔴 tools.css: no @import, and every url() is a data: URI (nothing fetched from anywhere)",
   "@import" not in _css_nc and all(u.strip("'\" ").startswith("data:") for u in re.findall(r"url\(([^)]*)\)", _css_nc)))
ok("🔴 tools.css: no outside address at all", not re.search(r"https?://(?!www\.w3\.org/2000/svg)", _css_nc.replace("%3A", ":")))


def tokens(css):
    m = re.search(r":root\s*\{(.*?)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S), re.S)
    return dict((k.strip(), re.sub(r"\s+", " ", v.strip())) for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1))) if m else {}


LANDING_TOKENS = tokens(read("landing/index.html"))
TOOL_TOKENS = tokens(CSS)
ok("⭐ tools.css carries the landing page's own tokens, every one with the same value",
   len(LANDING_TOKENS) >= 20 and all(TOOL_TOKENS.get(k) == v for k, v in LANDING_TOKENS.items()),
   str({k: (v, TOOL_TOKENS.get(k)) for k, v in LANDING_TOKENS.items() if TOOL_TOKENS.get(k) != v}))
ok("tools.css: the mockup's classes for a tool page are all there",
   all(re.search(r"\." + c + r"\b", _css_nc) for c in (
       "toolbar", "tp", "pitch", "work", "topline", "form", "f", "inp", "tick", "trap", "runrow", "res", "big", "adv", "fine2",
       "thanks", "say", "calchead", "calcs", "calc", "ans", "pdfbox", "pdfrow", "next", "cr", "chip", "btn-orange", "btn-line",
       "btn-ink", "eyebrow", "note")))
ok("tools.css: the pills read Free (green) and By request (grey), as the mockup draws them",
   ".cr.free{background:var(--ok-bg);color:var(--ok)}" in _css_nc and ".cr.ask{background:var(--none-bg);color:var(--ink-2)}" in _css_nc)
ok("tools.css: a small button keeps its drawn size and gets a 44 px tap area", re.search(r"\.btn\.sm::after\{[^}]*height:44px", _css_nc))
ok("tools.css: the mockup's two narrow breakpoints (860 px, 520 px)", "@media (max-width:860px)" in _css_nc and "@media (max-width:520px)" in _css_nc)
ok("🔴 tools.css draws no demo bar and no sign-in", not re.search(r"demo-?bar|demo-notice|signin|sign-in|balance", _css_nc, re.I))

# the shared script
_node = shutil.which("node")
if _node:
    r = subprocess.run([_node, "--check", str(TOOLS / "tools.js")], capture_output=True, text=True)
    ok("tools.js parses (node --check)", r.returncode == 0, r.stderr[:300])
else:
    ok("node is on the PATH to check tools.js", False)
_js_nc = re.sub(r"/\*.*?\*/", "", JS, flags=re.S)
ok("⭐ tools.js never sends a cookie with a tool call", 'credentials: "omit"' in _js_nc and "include" not in _js_nc)
ok("🔴 tools.js calls only /api/tools/ (anything else is refused before a request)",
   'path.indexOf("/api/tools/") !== 0' in _js_nc and _js_nc.count("fetch(") == 1)
ok("🔴 tools.js names no outside address and writes no HTML", not re.search(r"https?://", _js_nc) and "innerHTML" not in _js_nc
   and "document.write" not in _js_nc and "eval(" not in _js_nc)
ok("⭐ a failure shows one plain sentence: the server's own say, else a general one; the raw reply to the console only",
   "data.detail.say" in _js_nc and "say(sayEl, words)" in _js_nc and 'console.warn("Wayscope:"' in _js_nc
   and "textContent" in _js_nc and "r.status" not in re.sub(r'console\.warn\([^)]*\)', "", _js_nc))
_js_words = re.findall(r'var (?:GENERAL|OFFLINE) = "([^"]+)"', _js_nc)
ok("tools.js: two plain sentences, no number in either", len(_js_words) == 2 and not any(re.search(r"\d", w) for w in _js_words), str(_js_words))
ok("tools.js exposes WaysTools.call and WaysTools.say", "window.WaysTools = { call: call, say: say" in _js_nc)

# =========================================================================== #
#  2. every page: it parses, it loads nothing from outside, the frame is there  #
# =========================================================================== #
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
READ_ATTRS = ("alt", "aria-label", "placeholder", "title", "content", "value")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.text, self.attrs_text, self.tags = [], [], [], [], []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        for k in READ_ATTRS:
            if a.get(k) and not (tag == "meta" and a.get("name") == "viewport") and not (tag == "meta" and "charset" in a):
                self.attrs_text.append(a[k])
        if tag in VOID:
            return
        if tag in ("script", "style"):
            self.skip += 1
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes {self.stack[-1] if self.stack else 'nothing'}")
            if tag in self.stack:
                while self.stack and self.stack[-1] != tag:
                    self.stack.pop()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(re.sub(r"\s+", " ", data.strip()))


def parse(path):
    src = path.read_text(encoding="utf-8")
    p = Page()
    p.feed(src)
    p.close()
    return src, p


PARSED = {}
for path in PAGES:
    src, p = parse(path)
    PARSED[path] = (src, p)
    name = path.name if path != SAMPLE else "the sample page"
    ok(f"{name}: every tag closes in order", not p.errors and not p.stack, str(p.errors[:5] + p.stack[:5]))
    ok(f"{name}: an HTML5 page in British English with a viewport and a title naming Wayscope tools",
       src.lstrip().lower().startswith("<!doctype html>") and '<html lang="en-GB">' in src
       and '<meta name="viewport" content="width=device-width, initial-scale=1">' in src
       and re.search(r"<title>[^<]+ · Wayscope tools</title>", src))
    scripts = [a for t, a in p.tags if t == "script"]
    ok(f"🔴 {name}: no inline script, and every script is the app's own (/tools/…)",
       all((a.get("src") or "").startswith("/tools/") for a in scripts), str(scripts))
    ok(f"🔴 {name}: no inline event handler", not re.search(r"\son[a-z]+\s*=", src, re.I))
    sheets = [a.get("href") or "" for t, a in p.tags if t == "link" and a.get("rel") == "stylesheet"]
    ok(f"🔴 {name}: stylesheets only from the app or the Google Fonts CSS the landing page uses",
       all(h.startswith("/tools/") or h.startswith("https://fonts.googleapis.com/css2?") for h in sheets)
       and "/tools/tools.css" in sheets, str(sheets))
    srcs = [a.get("src") or "" for t, a in p.tags if t in ("img", "source", "video", "audio", "embed", "iframe")]
    ok(f"🔴 {name}: every picture is the app's own (no supplier's map, no Street View), and no frame",
       all(s.startswith(("/brand/", "/tools/")) for s in srcs) and not any(t in ("iframe", "object", "embed") for t, _ in p.tags), str(srcs))
    ok(f"{name}: the bar: the logo, \"Tools\" to the landing site's Tools page, \"Request a demo\" to its demo form",
       re.search(r'<header class="toolbar">', src)
       and '<img src="/brand/logo-header-on-dark.svg" alt="Wayscope"' in src
       and '<a class="on" href="https://wayscope.co.uk/tools">Tools</a>' in src
       and '<a class="btn btn-orange sm" href="https://wayscope.co.uk/#demo">Request a demo</a>' in src)
    ok(f"{name}: the shared script loads last", src.rstrip().endswith('<script src="/tools/tools.js"></script>\n</body>\n</html>'.strip()))
    ok(f"{name}: one h1", sum(1 for t, _ in p.tags if t == "h1") == 1)
    forms = src.count("<form")
    ok(f"{name}: a form a person types into carries the hidden trap box", forms == 0 or src.count(f'name="{tools_public.TRAP}"') >= forms)
    ok(f"{name}: no link to the app's staff side or the map", not re.search(r'href="/(?:#|map|help|bulletin|api/)', src))

ok("the logo the bar names is the landing page's own file", (ROOT / "frontend/brand/logo-header-on-dark.svg").read_bytes()
   == (ROOT / "landing/assets/logo-header-on-dark.svg").read_bytes())

# =========================================================================== #
#  3. the words a person reads there                                           #
# =========================================================================== #
_tl = read("backend/tests/test_landing.py")
_m = re.search(r"\nBANNED = (\[.*?\n\])\n", _tl, re.S)
LANDING_BANNED = ast.literal_eval(_m.group(1)) if _m else []
ok("the landing page's banned list read from test_landing.py", len(LANDING_BANNED) >= 15, str(len(LANDING_BANNED)))
_ar = read("backend/abnormal_route.py")
_m = re.search(r"SCREEN_BAN = re\.compile\((.*?)\)\n", _ar, re.S)
SCREEN_BAN = re.compile("".join(ast.literal_eval("(" + _m.group(1) + ",)"))) if _m else None
ok("the supplier names read from abnormal_route.SCREEN_BAN", SCREEN_BAN is not None and SCREEN_BAN.search("Mapbox"))
ok("...and the adviser's own ESDAL is not among them", SCREEN_BAN is not None and not SCREEN_BAN.search("ESDAL"))
EXTRA_BANNED = [
    (r"\btruck", "truck"), (r"\bsafer\b", "safer"), (r"\bcomplian", "compliant"), (r"\bbest\b", "best"),
    (r"(?-i:\bDEMO\b)", "the demo bar's DEMO"), (r"fictional scheme", "the demo notice"), (r"\bsign[- ]?in\b", "sign in"),
    (r"\bcredits?\b", "credits"), (r"\bbalance\b", "a balance"), (r"\bVAT\b", "VAT"), (r"street ?view", "Street View"),
    (r"\bguarantee", "a guarantee"), (r"\bapproved by\b", "approved by"), (r"\bcertif", "certified"), (r"\bendorse", "endorsed"),
]
WORDS = {}
for path, (src, p) in PARSED.items():
    WORDS[path.name if path != SAMPLE else "the sample page"] = " ".join(p.text + p.attrs_text)
WORDS["tools.js"] = " ".join(_js_words)
ok("the words were read (the sample page alone has the mockup's card 2 words)",
   "Three quick answers from a few figures." in WORDS.get("the sample page", "") and "a planning estimate" in WORDS.get("the sample page", ""))
for where, text in WORDS.items():
    hits = [n for pat, n in LANDING_BANNED + EXTRA_BANNED if re.search(pat, text, re.I)]
    ok(f"🔴 {where}: no banned word (landing list, truck, safer, compliant, best, demo bar, sign-in, credits, VAT)", not hits, str(hits))
    ok(f"🔴 {where}: no supplier or back-end name", not (SCREEN_BAN and SCREEN_BAN.search(text)),
       str(SCREEN_BAN.findall(text)[:5]) if SCREEN_BAN else "")
    ok(f"🔴 {where}: no back-end word (server, endpoint, API, token, cached, JSON, status)",
       not re.search(r"\b(server|endpoint|API|token|cached|JSON|status code|HTTP)\b", text), text[:200])
# the checks catch what they should (each list run on a line made to fail)
_bad = "Our AI makes trucks safer and compliant. Sign in. 5 credits + VAT. Routed by HERE on OpenStreetMap."
ok("the lists catch a made-up bad line (truck, AI, safer, compliant, sign in, credits, VAT, HERE, OpenStreetMap)",
   len([n for pat, n in LANDING_BANNED + EXTRA_BANNED if re.search(pat, _bad, re.I)]) >= 7 and len(SCREEN_BAN.findall(_bad)) >= 2)

# =========================================================================== #
#  4. tools_public: what a name serves, the landing address, the limit          #
# =========================================================================== #
_tmp = Path(tempfile.mkdtemp(prefix="tools_pages_"))
for f in ("tools.css", "tools.js"):
    shutil.copy(TOOLS / f, _tmp / f)
shutil.copy(SAMPLE, _tmp / "calculators.html")
(_tmp / "index.html").write_text("<!doctype html>", encoding="utf-8")
(_tmp / "notes.md").write_text("x", encoding="utf-8")
(_tmp / "Upper.html").write_text("x", encoding="utf-8")
_real = tools_public.TOOLS_DIR
tools_public.TOOLS_DIR = _tmp
try:
    f = tools_public.page_file("calculators")
    ok("⭐ /tools/calculators serves calculators.html as a page", f and f[0].name == "calculators.html" and f[1].startswith("text/html"))
    ok("/tools/tools.css and /tools/tools.js serve the shared files with their types",
       tools_public.page_file("tools.css")[1].startswith("text/css") and tools_public.page_file("tools.js")[1].startswith("text/javascript"))
    _no = ["", "index", "calculators.html", "notes.md", "notes", "Upper", "../main", "..", ".", "calculators/",
           "%2e%2e", "route-check", "-calc", "calc-", "a--b", "x" * 61, None, 5, "tools.css.map", "TOOLS.CSS"]
    ok("🔴 everything else is nothing (index, .html in the address, a note, capitals, dots, a page not there, odd names)",
       all(tools_public.page_file(n) is None for n in _no), str([n for n in _no if tools_public.page_file(n) is not None]))
    ok("pages() lists calculators only (not index, not Upper)", tools_public.pages() == ["calculators"], str(tools_public.pages()))
    body = tools_public.page_bytes(_tmp / "calculators.html")
    ok("with LANDING_URL unset a page names https://wayscope.co.uk", b'href="https://wayscope.co.uk/tools"' in body)
    os.environ["LANDING_URL"] = "https://landing.example.test/"
    body = tools_public.page_bytes(_tmp / "calculators.html")
    ok("⭐ with LANDING_URL set the bar's links follow it", b'href="https://landing.example.test/tools"' in body
       and b'href="https://landing.example.test/#demo"' in body and b'href="https://wayscope.co.uk' not in body)
    ok("...and the stylesheet is served as it is", tools_public.page_bytes(_tmp / "tools.css") == (TOOLS / "tools.css").read_bytes())
    os.environ.pop("LANDING_URL", None)
finally:
    tools_public.TOOLS_DIR = _real
    shutil.rmtree(_tmp, ignore_errors=True)
ok("on this branch no tool page is reachable yet (the folder holds the shared files only)", tools_public.pages() == []
   and tools_public.page_file("calculators") is None)

# the limit
L = tools_public.Limit("sample", 3, 3600)
t0 = 1_800_000_000.0
ok("⭐ the limit allows its count from one address", all(L.hit("203.0.113.5", now=t0 + i) for i in range(3)))
ok("⭐🔴 ...and refuses the next", L.hit("203.0.113.5", now=t0 + 10) is False)
ok("...a refused call is not counted (the window is not pushed on)", L.hit("203.0.113.5", now=t0 + 3600) is True)
ok("another address is not held up by the first", L.hit("198.51.100.7", now=t0 + 11) is True)
L2 = tools_public.Limit("sample2", 2, 60)
L2.hit("a", now=t0); L2.hit("a", now=t0 + 1)
ok("⭐ it recovers after its window", L2.hit("a", now=t0 + 30) is False and L2.hit("a", now=t0 + 60) is True
   and L2.hit("a", now=t0 + 61) is True and L2.hit("a", now=t0 + 62) is False)
ok("the address is kept only as a salted hash", all(len(k) == 32 and "a" != k for k in L2._hits)
   and tools_public.address_hash("203.0.113.5") != tools_public.address_hash("203.0.113.6"))
L3 = tools_public.Limit("flood", 1, 3600)
L3.MAX_KEYS = 50
for i in range(500):
    L3.hit(f"10.0.{i // 250}.{i % 250}", now=t0)
ok("🔴 a flood of addresses cannot grow memory past MAX_KEYS", len(L3._hits) <= 50, str(len(L3._hits)))
L.reset()
ok("reset() empties it", L.hit("203.0.113.5", now=t0) is True)
ok("the refusal is one plain sentence with no number", tools_public.Limit("x", 5, 3600).say
   == "Too many checks from this connection. Please try again in an hour."
   and tools_public.Limit("x", 5, 600).say.endswith("in 10 minutes.") and tools_public.Limit("x", 5, 60).say.endswith("in a minute."))
for args in (("", 1, 1), ("x", 0, 1), ("x", 1, 0)):
    try:
        tools_public.Limit(*args)
        ok(f"a limit with {args} is refused", False)
    except ValueError:
        ok(f"a limit with {args} is refused", True)
try:
    tools_public.refuse(429, "Too many checks.")
    ok("refuse() raises", False)
except Exception as e:
    ok("⭐ refuse() raises the status and {\"say\": sentence} (the shape the shared script reads)",
       getattr(e, "status_code", None) == 429 and getattr(e, "detail", None) == {"say": "Too many checks."})


class _Req:
    def __init__(self, fwd, peer):
        self.headers = {"x-forwarded-for": fwd} if fwd else {}
        self.client = type("C", (), {"host": peer})()


L4 = tools_public.Limit("guard", 1, 3600)
tools_public.guard(_Req("203.0.113.9, 10.0.0.1", "10.0.0.1"), L4)
try:
    tools_public.guard(_Req("203.0.113.9", "10.0.0.2"), L4)
    ok("guard() refuses the second call from the same visitor behind the proxy", False)
except Exception as e:
    ok("guard() refuses the second call from the same visitor behind the proxy (the first X-Forwarded-For entry)",
       getattr(e, "status_code", None) == 429 and e.detail["say"] == L4.say)
tools_public.guard(_Req("198.51.100.1", "10.0.0.1"), L4)
ok("...and lets another visitor through the same proxy", True)
ok("trapped(): the hidden box filled is a machine; empty or missing is a person",
   tools_public.trapped({"website": "x"}) and not tools_public.trapped({"website": " "}) and not tools_public.trapped({})
   and not tools_public.trapped(None) and tools_public.TRAP == "website")
ok("OPEN_ROUTES is a tuple, every entry under /api/tools/ (empty on this branch: no tool call yet)",
   isinstance(tools_public.OPEN_ROUTES, tuple) and all(r.startswith("/api/tools/") for r in tools_public.OPEN_ROUTES)
   and tools_public.OPEN_ROUTES == ())

# =========================================================================== #
#  5. the pins: the gate, the app, the headers, the guide, the audit           #
# =========================================================================== #
ok("⭐ the gate does not police /tools or /api/tools (open without a gate change)",
   all(gate.scope_for(p) is None for p in ("/tools", "/tools/", "/tools/calculators", "/tools/tools.css", "/api/tools/x")))
ok("🔴 ...while it still polices the map, the guides, the bulletin and the map's data",
   gate.scope_for("/map/") == "map" and gate.scope_for("/help/") == "help" and gate.scope_for("/bulletin/") == "bulletin"
   and gate.scope_for("/api/zones") == "map")
os.environ.pop("MAP_GATE", None)
ok("gate.decide lets an outsider with no cookie reach a tool page, and still refuses the map",
   gate.decide("/tools/calculators", has_valid_code=False, cookie=None) == gate.ALLOW
   and gate.decide("/map/", has_valid_code=False, cookie=None) != gate.ALLOW)
MAIN = read("backend/main.py")
ok("main.py serves /tools/{name} through tools_public, answers 404 for /tools and /tools/, none in the API schema",
   '@app.get("/tools", include_in_schema=False)\n@app.get("/tools/", include_in_schema=False)\ndef tools_index():' in MAIN
   and '@app.get("/tools/{name}", include_in_schema=False)' in MAIN and "tools_public.page_file(name)" in MAIN
   and 'headers={"Cache-Control": "no-cache"}' in MAIN[MAIN.find("def tools_page"):MAIN.find("def tools_page") + 600])
ok("🔴 /tools is not a static mount (a mount would list or redirect; the handler answers only what tools_public allows)",
   'app.mount("/tools"' not in MAIN)
ok("⭐ the open calls write no audit row and empty no kept read (/api/tools/ in AUDIT_SKIP_PREFIXES)",
   '"/api/tools/")' in MAIN[MAIN.find("AUDIT_SKIP_PREFIXES = ("):MAIN.find("\n\n", MAIN.find("AUDIT_SKIP_PREFIXES = ("))])
ok("the /tools routes come before the catch-all page", MAIN.find('@app.get("/tools/{name}"') < MAIN.find('@app.get("/")\ndef frontend_index'))
import security_headers  # noqa: E402
ok("⭐ no browser or proxy keeps a tool's answer (/api/tools/ in NO_STORE_PREFIXES)", "/api/tools/" in security_headers.NO_STORE_PREFIXES)
_h = security_headers.apply("/api/tools/x", {})
ok("...and apply() gives a tool call no-store and every security header", _h.get("Cache-Control") == "no-store"
   and all(k in _h for k in security_headers.HEADERS))
ok("the policy already allows the Google Fonts stylesheet and fonts the pages load (no new host)",
   "https://fonts.googleapis.com" in security_headers.CSP_SOURCES["style-src"]
   and "https://fonts.gstatic.com" in security_headers.CSP_SOURCES["font-src"])
TG = read("frontend/help/technical/index.html")
_sec = TG[TG.find('<h2 id="t4-tools">'):TG.find('<h1 id="t5-errors"')]
ok("the technical guide: where tool pages live and the open-call rule, linked from its contents",
   '<a href="#t4-tools">Public tool pages</a>' in TG and "frontend/tools/&lt;page&gt;.html" in _sec
   and "/api/tools/" in _sec and "tools_public.guard(request, limit)" in _sec and "OPEN_ROUTES" in _sec and "429" in _sec)
UA = read("backend/tests/ui_audit.js")
_m = re.search(r"const TOOL_PAGES = \[([^\]]*)\];", UA)
_listed = re.findall(r'"([a-z0-9-]+)"', _m.group(1)) if _m else None
ok("⭐ the UI audit walks every tool page: its TOOL_PAGES is exactly the shipped pages", _listed == tools_public.pages(),
   f"{_listed} vs {tools_public.pages()}")
ok("...as signed-out stops named tools-<page>, beside the landing pages",
   '...TOOL_PAGES.map(n => ["tools-" + n, "/tools/" + n])' in UA and "|tools-[a-z0-9-]+)$/" in UA)
WALL = read("backend/tests/smoke_reviewer_wall.py")
ok("the reviewer-wall sweep checks that every /api/tools route is named open on purpose",
   "tools_public.OPEN_ROUTES" in WALL and '_tools_routes == sorted(set(tools_public.OPEN_ROUTES))' in WALL)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"test_tools_pages.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
