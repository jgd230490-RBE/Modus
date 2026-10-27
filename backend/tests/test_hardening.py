"""
Pilot readiness phase 2 (27 Oct 2026, F3 e) — the security headers, the pinned outside scripts, the vendored Tailwind
file, the weekly dependency audit and the key-rotation table. Source-level and offline: no network, no FastAPI.
http_smoke.py checks the same headers on the real app's answers.

Run from the repo root:  python backend/tests/test_hardening.py

What this proves: every header is set (and a header an endpoint set itself is kept), the sign-in answers are never
cached, the Content Security Policy refuses plugins and outside framing and pins <base> and form targets; every https
host a page loads code, styles, fonts or data from is one the policy allows; every outside script and stylesheet but
Google Fonts' CSS is an exact version with an integrity hash and crossorigin="anonymous"; the vendored Tailwind file is
byte-identical to its recorded hash and git will not rewrite it; Pillow is past the 63 advisories found on 27 Oct; the
weekly audit workflow exists; the technical guide carries the headers and the key table.

What it does not prove: that a browser accepts every hash (the Chrome check and the UI audit do), that the live CDNs
still serve those bytes (a change shows as a refused script in the browser), the audit's network run (GitHub does).
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import security_headers as sh  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


# =========================================================================== #
#  1. the headers                                                              #
# =========================================================================== #
H = sh.HEADERS
ok("⭐ every header is in the set: HSTS, nosniff, frame options, referrer policy, permissions policy, CSP",
   set(H) == {"Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
              "Permissions-Policy", "Content-Security-Policy"})
ok("HSTS one year, no includeSubDomains (decided per subdomain)", H["Strict-Transport-Security"] == "max-age=31536000")
ok("nosniff; framed by this site only; the origin only to other sites",
   H["X-Content-Type-Options"] == "nosniff" and H["X-Frame-Options"] == "SAMEORIGIN"
   and H["Referrer-Policy"] == "strict-origin-when-cross-origin")
ok("the permissions policy turns off camera, microphone, location, payment and USB",
   all(f"{k}=()" in H["Permissions-Policy"] for k in ("camera", "microphone", "geolocation", "payment", "usb")))
CSP = H["Content-Security-Policy"]
d = {p.split(" ")[0]: p.split(" ")[1:] for p in CSP.split("; ")}
ok("🔴 the CSP refuses plugins, refuses another site's frame, pins <base> and form targets to the site",
   d["object-src"] == ["'none'"] and d["frame-ancestors"] == ["'self'"] and d["base-uri"] == ["'self'"]
   and d["form-action"] == ["'self'"] and d["default-src"] == ["'self'"])
ok("...frames: only this site (the staff app frames the public map)", d["frame-src"] == ["'self'"])
ok("...the honest limit is written down: inline script and eval stay (in-browser Babel, no build step)",
   "'unsafe-inline'" in d["script-src"] and "'unsafe-eval'" in d["script-src"]
   and "does not stop injected inline script" in open(os.path.join(BACKEND, "security_headers.py"), encoding="utf-8").read())
ok("...Mapbox's workers from blob:, its tiles and events in connect-src",
   "blob:" in d["worker-src"] and all(h in d["connect-src"] for h in
                                      ("https://api.mapbox.com", "https://*.tiles.mapbox.com", "https://events.mapbox.com")))
ok("🔴 the Tailwind CDN is NOT allowed any more (the file is served from the app)", "https://cdn.tailwindcss.com" not in CSP)
h1 = sh.apply("/", {})
ok("apply() sets every header on a page", all(h1.get(k) == v for k, v in H.items()) and "Cache-Control" not in h1)
h2 = sh.apply("/x", {"X-Frame-Options": "DENY", "Cache-Control": "no-cache"})
ok("...keeps a header the endpoint set itself (and its Cache-Control)", h2["X-Frame-Options"] == "DENY" and h2["Cache-Control"] == "no-cache")
ok("⭐ the sign-in calls and the Users list are never cached (a set-up answer holds a key and recovery codes)",
   sh.apply("/api/auth/setup", {"Cache-Control": "max-age=60"})["Cache-Control"] == "no-store"
   and sh.apply("/api/auth/code", {})["Cache-Control"] == "no-store"
   and sh.apply("/api/admin/users", {})["Cache-Control"] == "no-store"
   and "Cache-Control" not in sh.apply("/api/forecasts", {}))

MAIN = read("backend/main.py")
ok("⭐ main.py adds the headers in a middleware declared AFTER the access middleware (so it wraps the gate's refusals)",
   "security_headers.apply(request.url.path, response.headers)" in MAIN
   and MAIN.find("async def _access_middleware") < MAIN.find("async def _security_headers_middleware"))
ok("...and imports the module", "\nimport security_headers" in MAIN)

# =========================================================================== #
#  2. every outside host a page uses is allowed, and pinned                     #
# =========================================================================== #
PAGES = ["frontend/index.html", "map/index.html", "frontend/help/index.html", "frontend/help/technical/index.html"]
TAG_RX = re.compile(r"<(script|link)\b[^>]*>", re.I)


def attr(tag, name):
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else None


def allowed(host_url, directive):
    """Does the CSP directive allow this https URL's origin?"""
    m = re.match(r"https://([^/]+)", host_url)
    if not m:
        return True
    host = m.group(1)
    for src in d.get(directive, []):
        if src == "https:":
            return True
        if src.startswith("https://*."):
            if host.endswith(src[len("https://*"):]):
                return True
        elif src == "https://" + host:
            return True
    return False


bad_hosts, unpinned, outside = [], [], 0
for page in PAGES:
    src = read(page)
    for t in [m.group(0) for m in TAG_RX.finditer(src)]:
        if t.lower().startswith("<script"):
            u = attr(t, "src")
            if u and u.startswith("http"):
                outside += 1
                if not allowed(u, "script-src"):
                    bad_hosts.append((page, u))
                if not (attr(t, "integrity") or "").startswith("sha384-") or attr(t, "crossorigin") != "anonymous":
                    unpinned.append((page, u))
        else:
            u = attr(t, "href")
            rel = attr(t, "rel") or ""
            if u and u.startswith("http") and rel == "stylesheet":
                outside += 1
                if not allowed(u, "style-src"):
                    bad_hosts.append((page, u))
                if "fonts.googleapis.com" not in u and (not (attr(t, "integrity") or "").startswith("sha384-")
                                                        or attr(t, "crossorigin") != "anonymous"):
                    unpinned.append((page, u))
ok("⭐ every outside script and stylesheet the pages load comes from a host the CSP allows", not bad_hosts and outside >= 8,
   str(bad_hosts))
ok("⭐ every outside script and stylesheet (but Google Fonts' CSS) carries a sha384 integrity hash and crossorigin=anonymous",
   not unpinned, str(unpinned))
FE = read("frontend/index.html")
ok("🔴 no floating version left: React and ReactDOM are 18.3.1, never @18/",
   "unpkg.com/react@18.3.1/umd/react.production.min.js" in FE and "unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" in FE
   and "@18/" not in FE)
ok("🔴 no script from cdn.tailwindcss.com; the app serves Tailwind 3.4.17 itself",
   'src="https://cdn.tailwindcss.com' not in FE and '<script src="/vendor/tailwind-play-3.4.17.js"></script>' in FE)
for page in ("frontend/index.html", "map/index.html"):
    js_hosts = sorted(set(re.findall(r"https://([a-z0-9.-]+\.[a-z]{2,})/[^\"'\s`]*\{[zxy]\}", read(page))))
    ok(f"the tile hosts {page} draws from are in connect-src ({', '.join(js_hosts) or 'none'})",
       all(allowed("https://" + h, "connect-src") for h in js_hosts))
ok("Google Fonts: the CSS in style-src, the font files in font-src",
   allowed("https://fonts.googleapis.com/css2", "style-src") and allowed("https://fonts.gstatic.com/x", "font-src"))

# =========================================================================== #
#  3. the vendored file                                                         #
# =========================================================================== #
TW = os.path.join(ROOT, "frontend", "vendor", "tailwind-play-3.4.17.js")
TW_SHA384 = "igm5BeiBt36UU4gqwWS7imYmelpTsZlQ45FZf+XBn9MuJbn4nQr7yx1yFydocC/K"
import base64  # noqa: E402
ok("⭐ the vendored Tailwind file is byte-identical to what cdn.tailwindcss.com/3.4.17 served (sha384)",
   os.path.isfile(TW) and base64.b64encode(hashlib.sha384(open(TW, "rb").read()).digest()).decode() == TW_SHA384)
ok("...git keeps it byte-identical (no line-ending rewrite), and the README records source, version, hash, licence",
   "frontend/vendor/*.js -text" in read(".gitattributes")
   and all(x in read("frontend/vendor/README.md") for x in ("https://cdn.tailwindcss.com/3.4.17", TW_SHA384, "MIT")))
ok("main.py serves /vendor/ before the catch-all", 'app.mount("/vendor", NoCacheStatic(directory=str(ROOT / "frontend" / "vendor")' in MAIN
   and MAIN.find('app.mount("/vendor"') < MAIN.find('@app.get("/")'))

# =========================================================================== #
#  4. the libraries and the weekly audit                                        #
# =========================================================================== #
REQ = read("backend/requirements.txt")
ok("⭐ Pillow is 13.0.0: the 63 advisories pip-audit found in 12.2.0 on 27 Oct 2026 are all fixed there",
   "pillow==13.0.0" in REQ and "pillow==12.2.0" not in REQ)
ok("every requirement is pinned to an exact version", all("==" in l for l in REQ.splitlines() if l.strip() and not l.startswith("#")))
WF = read(".github/workflows/dependency-audit.yml")
ok("⭐ the weekly audit: Mondays, on demand, and on a PR that changes requirements.txt; pip-audit pinned; read-only",
   'cron: "17 6 * * 1"' in WF and "workflow_dispatch:" in WF and '- "backend/requirements.txt"' in WF
   and "pip-audit==2.10.1" in WF and "pip-audit -r backend/requirements.txt" in WF and "contents: read" in WF)
ok("...the suite itself stays offline (its harness step runs in a network namespace)",
   "network namespace" in read(".github/workflows/suite.yml"))

# =========================================================================== #
#  5. the guide                                                                 #
# =========================================================================== #
TG = read("frontend/help/technical/index.html")
ok("⭐ the technical guide: the headers and their limit, the pinned scripts, the weekly audit, the key table",
   '<h2 id="t7-hardening">' in TG and '<a href="#t7-hardening">' in TG and "does not stop injected inline script" in TG
   and "/vendor/tailwind-play-3.4.17.js" in TG and "dependency-audit.yml" in TG
   and all(f"<code>{k}</code>" in TG for k in ("GATE_SECRET", "MAP_PASSWORD", "ADMIN_TOKEN", "SMTP_PASSWORD", "HERE_API_KEY")))
ok("🔴 ...and nowhere calls the deployment secure", " secure " not in re.sub(r"<[^>]+>", " ", TG[TG.find('id="t7-hardening"'):TG.find('id="t8-community"')]).lower())

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
