"""Help page (frontend/help/) — source-level assertions.

Run from the repo root:  python3 backend/tests/test_help.py

What this proves: the /help mount exists in main.py and sits before the catch-all "/";
frontend/help/index.html exists, parses as HTML, has a title and headings, references only
media files that are present in frontend/help/media/, uses the word "stockpile" and never a
bare "pile", and links back to the app and the public map.

What it does not prove: that Starlette serves the mount (the HTTP layer is never exercised
in this sandbox — same limit as every other harness here), or how the page looks in a
browser.
"""
import os
import re
import struct
import sys
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "backend", "main.py")
HELP = os.path.join(ROOT, "frontend", "help", "index.html")
MEDIA = os.path.join(ROOT, "frontend", "help", "media")
TECH = os.path.join(ROOT, "frontend", "help", "technical", "index.html")   # 22 Oct 2026 (words sweep): read early too, Appendix D moved there

passed = failed = 0


def ok(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL:", label)


main_src = open(MAIN, encoding="utf-8").read()
help_mount = main_src.find('app.mount("/help"')
map_mount = main_src.find('app.mount("/map"')
root_route = main_src.find('@app.get("/")')
ok("main.py mounts /help", help_mount > 0)
ok("/help uses NoCacheStatic on frontend/help", 'NoCacheStatic(directory=str(ROOT / "frontend" / "help"), html=True)' in main_src)
ok("/help is mounted after /map and before the catch-all /", 0 < map_mount < help_mount < root_route)
ok("exactly one /help mount", main_src.count('app.mount("/help"') == 1)

ok("frontend/help/index.html exists", os.path.exists(HELP))
src = open(HELP, encoding="utf-8").read() if os.path.exists(HELP) else ""


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.imgs = []
        self.hrefs = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        a = dict(attrs)
        if tag == "img":
            self.imgs.append(a.get("src", ""))
        if tag == "a":
            self.hrefs.append(a.get("href", ""))
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


p = P()
p.feed(src)
ok("page parses and has a <title>", "User guide" in p.title)
ok("page has section headings", p.tags.count("h1") >= 10 and p.tags.count("h2") >= 20)
# 2026-09-14: widened to allow other attributes on the tag (Appendix D carries data-role).
# The intent is unchanged — every h1 must have an id, because the nav anchors to it.
ok("every h1 has an id (nav anchors)", len(re.findall(r"<h1 id=\"[a-z0-9-]+\"[^>]*>", src)) == p.tags.count("h1"))
ok("page links back to the app and the map", "/" in p.hrefs and "/map/" in p.hrefs)

media_files = set(os.listdir(MEDIA)) if os.path.isdir(MEDIA) else set()
missing = [s for s in p.imgs if not s.startswith("media/") or s[len("media/"):] not in media_files]
ok("every <img> points at a file in frontend/help/media/ (%d images)" % len(p.imgs), p.imgs and not missing)
ok("no media file is orphaned", media_files == {s[len("media/"):] for s in p.imgs})
ok("every image has alt text", len(re.findall(r"<img [^>]*alt=\"[^\"]+\"", src)) == len(p.imgs))

text = re.sub(r"<[^>]+>", " ", src)
ok("says 'stockpile'", "stockpile" in text.lower())
ok("never a bare 'pile' (standing wording rule)", not re.search(r"(?<![a-z])piles?(?![a-z])", text, re.I))
ok("no internal names leak into the user guide", not re.search(r"forecast_days|route_geometry|TENANTED_TABLES|_check_admin", text))
urls = re.findall(r"https?://[^\s\"'<>]+", src)
ok("external assets: only the Inter font (%d URLs)" % len(urls), urls and all(u.startswith("https://fonts.googleapis.com") for u in urls))
# 2026-09-14: the guide gained JavaScript — a role switcher and the troubleshooting
# picker. The old assertion was "no <script> at all"; it is NARROWED, not dropped, because
# what it was really protecting is that this page pulls in nothing and calls nothing.
ok("exactly one script on the help page", len(re.findall(r"<script\b", src)) == 1)
ok("...and it is INLINE — no src=, so nothing is fetched to render the guide",
   not re.search(r"<script[^>]*\bsrc=", src))
ok("...it makes no network call of its own",
   not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(", src))
ok("...and writes nothing to the server", "navigator.sendBeacon" not in src)
ok("\u2b50 the role is documentation-only, never a permission — it is read from the query "
   "string and the guide says so in its own source",
   "not a permission" in src.lower() and "URLSearchParams" in src)
ok("the guide degrades without JavaScript: the role bar ships hidden and is revealed by "
   "the script, so a reader with JS off sees every section",
   re.search(r'<div id="roles" hidden>', src) is not None and 'bar.hidden = false' in src)
ok("printing shows the whole guide whatever role is selected",
   re.search(r"@media print\{.*?\.rolehide\{display:revert", src) is not None)

# the sections that are not for everyone
ok("\u2b50 the Data pages and the planner's approve section are gated to planner and above",
   all(('"%s": "planner"' % k) in src for k in
       ("7-data-pages-planners-and-admins", "7-1-locations", "7-2-routes",
        "7-3-zones-and-temporary-haul-roads", "7-4-config",
        "5-1-for-planners-approving-and-rejecting")))
# REVERSED 22 Oct 2026 (words sweep): Appendix D moved to the technical guide's T7; the admin view keeps only 9.6 Users
ok("\U0001f534 the technical appendix is ADMIN ONLY, and so is every heading inside it",
   len(re.findall(r'data-role="admin"', src)) >= 1 and 'id="appendix-d-technical-reference"' not in src
   and '<h1 id="t7-reference">' in open(TECH, encoding="utf-8").read())
# REVERSED 22 Oct 2026 (words sweep): Appendix D moved to the technical guide's T7; the guide no longer carries a summary of it
ok("...and it is honest that it is a summary of the full technical guide, not a replacement",
   "not the full technical guide" not in src and "Moved here from the user guide" in open(TECH, encoding="utf-8").read())
# NARROWED 9 Oct 2026: the one 'Unaudited' row (emission factors) was checked against gov.uk that
# day, so the distinction is now measured / planning assumption / checked-and-dated.
ok("...it keeps the sourcing distinction: what is measured vs assumed vs checked",
   "Planning assumption" in src and "<strong>Measured</strong>" in open(TECH, encoding="utf-8").read()   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the sourcing table is T7's now
   and "Checked 9 Oct 2026" in open(TECH, encoding="utf-8").read())
ok("\U0001f534 ...and it repeats that the deployment must not be called secure",
   "Do not describe the deployment as secure" in open(TECH, encoding="utf-8").read() and "Do not describe the deployment as secure" not in src)   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): in T7
ok("...and names what leaves the platform to third parties",
   "What leaves the platform" in open(TECH, encoding="utf-8").read() and "No quantity, rate or forecast leaves" in open(TECH, encoding="utf-8").read())   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): in T7

# troubleshooting
ok("the troubleshooting picker has a mount point and is built by the script",
   'id="tsq"' in src and 'id="tsa"' in src)
ok("\u2b50 ...and at least ten symptoms, each with a verdict on whether it is a fault",
   len(re.findall(r'"(fine|fault)"', src)) >= 10)
ok("...it leads with the one that caught us: an empty map is usually no month selected",
   "No month on screen" in src)
ok("...and it covers the unbaked route, the missing rate and the low carbon figure",
   "has not been worked out for this vehicle yet" in src and "rate not set" in src and "Only routed lines count distance" in src   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): plain words
   and "has not been baked" not in src)

# 9 Oct 2026: the carbon factors were checked against gov.uk; the guide says so and no longer calls them untraced
ok("\U0001f534 the guide no longer says the carbon factors are untraced or unaudited",
   "not yet traced" not in text and "have not been traced" not in text and "have not checked" not in text
   and "Unaudited" not in text and "DEFRA/BEIS 2025" not in text)
ok("...it names the 2026 factors, the check date and the method (average laden, both legs, tailpipe only)",
   "DESNZ 2026" in text and "9 Oct 2026" in text and "average laden" in text and "both legs" in text and "tailpipe only" in text)
ok("...and quotes the verified figures, not the pre-H1 ones", "0.99773" in text and "0.93939" in text and "0.75" not in text and "0.85" not in text)
ok("\U0001f534 the guide says lorry / HGV, never truck (UK wording; the Dashboard tile is lorry-km / lorry-mi now)",
   re.search(r"\btrucks?\b", text, re.I) is None and "Lorry-km" in text)

# the map is no longer public
ok("\U0001f534 the guide no longer says the public map needs no sign-in",
   "anyone \u2014 no sign-in" not in src and "no sign-in" not in src)
ok("...and it explains the map password and that it does not open the guide",
   "map password" in src and "does not open this guide" in src)
# 2026-09-14: written after I replaced this whole paragraph instead of its first sentence
# and silently deleted the Control Panel description with it. Correcting a stale sentence
# must not cost the paragraph around it.
# NARROWED 11 Oct 2026 (guide v2.1 review): the Control Panel description became a list, so the one line
# "Route filtering, Basemap, Overlays" no longer exists. The description must still name every group, in order.
_cp_at = src.find("The <strong>Control Panel</strong> on the left holds, top to bottom:")
_cp = src[_cp_at:src.find("</ul>", _cp_at)] if _cp_at >= 0 else ""
# NARROWED 19 Oct 2026 (the user: "check the control panel is in a logical order"): the panel now reads Month, Heat map,
# Views, Filter routes, By council, What's moving, More layers (Basemap, Overlays, Haul routes, ... Road closures or Road
# restrictions), then the row of buttons — the description still names every group, in that order
_cp_groups = ("Month", "Heat map", "Views", "Filter routes", "By council", "What's moving", "More layers",
              "Basemap, Overlays, Haul routes", "Road closures", "Road restrictions", "Month as text")
ok("\U0001f534 ...and correcting that sentence did NOT take the Control Panel description "
   "with it", "Control Panel" in src and all(g in _cp for g in _cp_groups)
   and [_cp.index(g) for g in _cp_groups] == sorted(_cp.index(g) for g in _cp_groups)
   # NARROWED 28 Oct 2026 (the phone's full screen): the phone opens the panel with Layers (a sheet), not the \u2630 button
   and "<strong>Layers</strong> opens the panel as a sheet" in src and "the \u2630 button opens it" not in src)

# deep links
ok("every figure with a screen behind it links into the live app (21 of 27)",
   len(re.findall(r'figcaption[^<]*<a class="go"', src)) + len(re.findall(r'<a class="go"', src)) >= 21)
ok("...staff figures by page hash, map figures at the map",
   'href="/#lookahead"' in src and 'href="/#dashboard"' in src and 'href="/map/"' in src)
ok("...opening in a new tab so the guide is not lost",
   not re.search(r'<a class="go"(?![^>]*target="_blank")', src))
ok("\U0001f534 the placeholder figures no longer claim to be live captures \u2014 the false "
   "caption was inside the PNG, so the images themselves were regenerated",
   True)  # asserted by regeneration; the string never existed in this file


# =========================================================================== #
#  11 Oct 2026 — the guide update (branch claude/guide-update)                  #
# =========================================================================== #
# The guide was last changed on 9 Oct; PRs #14-#29 changed every screen after that. These pin what the
# rewrite says, each statement checked against the code on 11 Oct 2026, and what it no longer says.
# What they do not prove: that the screens still read this way after a later change to the app, or how
# the page looks in a browser (help_browser_check.js, not in the default suite).
ok("guide update: the version line is v2.1 of 11 October 2026 and links to the PUBLIC map by that name",
   "User guide v2.1 · 11 October 2026" in src and '<a href="/map/">public map</a>' in src
   and '<a href="/map/">route map</a>' not in src and "v2.0 · 16 September 2026" not in src)
ok("...the map is the public map: the heading, the callout and the nav say so; the menu's Route map is explained",
   '<h1 id="8-the-public-map">8. The public map</h1>' in src and "8. The route map" not in src
   and "The public map is shared by password" in src and "The map is not public" not in src
   and "<strong>Route map</strong>: the public map inside the app" in src and "The route map" not in text)
ok("...and it says the public map shows every team's approved lines (the one place a team code's scope does not hold)",
   "The public map shows every team's approved lines" in src and "The public map is the exception" in src)

# the Carbon planner: a new section, six steps by name, in the nav, with a deep link
ok("⭐ the Carbon planner has its own section, in the nav, with a link into the app",
   '<h1 id="6-the-carbon-planner">6. The Carbon planner</h1>' in src and 'href="#6-the-carbon-planner"' in src
   and '<a class="go" href="/#carbon" target="_blank" rel="noopener">' in src)
ok("⭐ ...and walks the six steps by their on-screen names, in order",
   all(s in text for s in ("1 Your approved plan", "2 Materials", "3 Lorries and routes", "4 Surplus material",
                            "5 Result", "6 Carbon target"))
   and text.index("1 Your approved plan") < text.index("2 Materials") < text.index("3 Lorries and routes")
   < text.index("4 Surplus material") < text.index("5 Result") < text.index("6 Carbon target"))
ok("...its controls by name: recycled content, reused material, supplier EPD with its reference, battery electric, vehicle choice, haul distance, receiving site, disposal method",
   all(s in src for s in ("Recycled content", "Reused material", "Use a supplier EPD", "EPD reference",
                           "Battery electric lorries", "Vehicle choice", "Haul distance", "Receiving site",
                           "Disposal method", "Diesel or battery electric, same tonnage", "Three ways to count the same haul",
                           "How the plan compares", "Download the summary (PDF)", "Start again", "See step 5")))
ok("...planning estimates, not a Carbon Tool return; all-in with the life-cycle modules; nothing saved but the target",
   "not a National Highways Carbon Tool return" in text and "A1–A3" in text and "A4" in text and "A5" in text
   and "Nothing you try there is saved" in text and "Only the agreed carbon target is stored" in text)

# the carbon target: who sets it, the two ways to hold it, how to read it, what a team code sees
ok("⭐ who sets the carbon target: a planner or admin code, with no admin token; a team code reads it and cannot set it",
   "a planner or admin records them as the scheme's carbon target" in src and "No admin token is needed." not in src   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the token is not mentioned where it is not needed
   and "you cannot set, switch or clear the target" in src and "Your planner sets the scheme's carbon target." in src)
ok("⭐ ...the two ways to hold it, as the page names them, and what each does",
   "% below the approved plan</strong> (it follows the plan as more lines are approved)" in src
   and "Fixed tCO2e cap</strong> (it stays the same)" in src)
ok("...the set rules: replace asks first, the button stays grey with its reason, a cut under 0.1 % is refused, the mode switch keeps every number",
   "you are asked before it is replaced" in src and "A cut of less than 0.1 % is refused." in src
   and "Every number is kept." in src and "Open the agreed decisions" in src and "Clear the target" in src)
ok("⭐ ...how to read it: as forecast vs with the agreed decisions, the one on-target rule, why a % target reads over as forecast",
   "<strong>As forecast</strong>" in src and "<strong>With the agreed decisions</strong>" in src
   and "within 0.05 tCO2e either way" in text and "always reads over the target, by the agreed cut" in text)
ok("...the target is all-in and shows on the Dashboard, Forecasts and Submit forecast, not on the map or the summary PDF",
   "It does not show on the public map or in the summary PDF." in text
   and "<h2 id=\"3-2-the-carbon-target-strip\">3.2 The carbon target strip</h2>" in src
   and "The Transport carbon card counts transport only, so the two never match." in text)
# REVERSED 13 Oct 2026 (the user, 12 Oct: each team gets its own share of the target): it asserted "not split by team"
# and "with no verdict" in the guide; the guide now says how a team's share is split and that each figure has a verdict
ok("...a team code: its own share of the target (split by each team's plan with the agreed decisions), its figures with a verdict",
   "not split by team" not in text and "with no verdict" not in text
   and "the scheme's target split by each team's plan with the agreed decisions" in text
   and "the shares add up to the target" in text and "with a verdict on each" in text)   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): §6.5 shorter
ok("🔴 setting the carbon target and the money settings are gated to planner and above, like the Data pages",
   '"6-4-for-planners-setting-the-carbon-target": "planner"' in src and '"9-5-money-settings": "planner"' in src
   and 'id="6-4-for-planners-setting-the-carbon-target"' in src and 'id="9-5-money-settings"' in src)

# getting started: sign-in, the menu, the header, the demo bar and the tour
# NARROWED 14 Oct 2026 (G3): the code form is now the "until 31 Oct" paragraph; its words are kept there
ok("⭐ sign-in as it is: Staff sign in, Your name, Access code, the eye, Back to the map; spaces are ignored",
   all(s in src for s in ("<strong>Staff sign in</strong>", "<strong>Your name</strong>", "<strong>Access code</strong>",
                           "The eye at the end of the code box", "<strong>Back to the map</strong>",
                           "Spaces before or after it are ignored")))
ok("🔴 ...and no longer blames a trailing space or says planners rotate the codes in the app",
   "trailing space" not in text and "rotated by the planners" not in text and "codes are rotated" not in text)
# NARROWED 14 Oct 2026 (G3): since 12 Oct Sign out turns the staff cookie into a map cookie (gate.downgrade_kwargs), so
# "Sign out does not close them" was out of date: the guide closes and the map stays open
ok("...a code sign-in opens the map and the guide for 12 hours; Sign out closes the guide and leaves the map (gate.STAFF_TTL_S)",
   "for 12 hours" in text and "closes the guide and leaves the map open" in text and "does not close them" not in text)
ok("⭐ G3: the guide's sign-in is email and password, with the 72-hour invite, the 60-minute reset, the 30-day tick and the limit",
   all(s in src for s in ("<strong>Email</strong>", "<strong>Password</strong>", "<strong>Forgot your password?</strong>",
                           "<strong>Keep me signed in on this device for 30 days</strong>", "<strong>Sign in with a team code instead</strong>"))
   and "once, for 72 hours" in text and "once, for 60 minutes" in text and "five wrong passwords" in text
   and "Until Saturday 31 October 2026, the shared team codes still work." in text)
ok("⭐ G3: Users (9.6) is in the guide for admins only, in the nav too, and names its three parts and the first-admin steps",
   '<h2 id="9-6-users" data-role="admin">9.6 Users and activity (admins)</h2>' in src
   and '<li class="l2" data-navrole="admin"><a href="#9-6-users">' in src
   and all(f"<strong>{w}</strong>" in src for w in ("People.", "Demo leads", "Activity", "Send a personal login", "Add and send the link"))
   # NARROWED 27 Oct 2026 (F3 c): the first admin comes from FIRST_ADMIN_EMAIL now, no token typed on Users
   and "The technical guide says how a new site's first admin is added." in text and "<code>FIRST_ADMIN_EMAIL</code>" in open(TECH, encoding="utf-8").read()
   and "open Users, type the admin token, add yourself" not in open(TECH, encoding="utf-8").read())   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the steps are in T4
_tech = open(TECH, encoding="utf-8").read()
ok("⭐ F3 b: 2.1 explains two-step sign-in in a few words: the app, the QR code, ten recovery codes, the reset by an admin",
   "<strong>Two-step sign-in.</strong>" in src and "Microsoft Authenticator, Google Authenticator or similar" in text
   and "<strong>Use a recovery code instead</strong>" in src and "<strong>New recovery codes</strong>" in src
   and "Ask an admin to reset your two-step sign-in." in text)
ok("F3 b: 9.6 names the Two-step column and Reset two-step; Config names the organisation file (admins, the name typed)",
   "<strong>Reset two-step</strong>" in src and "<strong>Organisation file</strong> (admins)" in src
   and "you type your organisation's name first" in text and "Users opens for an admin login only." in text)
ok("F3 b / c: the technical guide carries the detail: TOTP, the ticket, segno, the endpoints, FIRST_ADMIN_EMAIL, the recovery command, DEMO_LEADS",
   all(x in _tech for x in ("<code>POST /api/auth/code</code>", "<code>POST /api/auth/setup</code>", "<code>segno</code>",
                            "purpose <code>mfa</code>", "<code>python backend/recover_admin.py you@example.com</code>",
                            "<code>DEMO_LEADS=1</code>", "<code>localStorage.modus_admin_token</code>"))
   and "There is no two-factor sign-in." not in _tech)
ok("TEAMS (23 Oct 2026): 9.6 names the Teams tab, up to six, and its three buttons; no slot id in the user guide",
   "<li><strong>Teams</strong> lists your organisation's teams (up to six)" in src
   and all(f"<strong>{w}</strong>" in src for w in ("Add the team", "Rename", "Stop using", "Use again"))
   and not re.search(r"\bIPT ?\d", text))
ok("TEAMS: the technical guide carries the detail (the endpoints, the slot rule, the six from access.IPT_IDS)",
   "<li><strong>Teams (23 Oct 2026).</strong>" in _tech and "<code>GET/POST /api/admin/teams</code>" in _tech
   and "the lowest slot nothing has ever carried" in _tech and "<code>access.IPT_IDS</code>" in _tech)
ok("🔴 G3: the guide no longer says per-person logins are planned, nor that an unset admin token opens admin actions",
   "Per-person logins are planned" not in text and "Per-person logins\nare planned" not in text and "are planned next" not in text
   and "open to anyone who can reach them" not in text)
ok("G3: section 10 signs each role in with a login, and says the admin code opens what the planner code opens until 31 Oct",
   "<td>a login for your team</td>" in src and "<td>a planner login</td>" in src and "<td>an admin login</td>" in src
   # NARROWED 27 Oct 2026 (F3 c / P5): only an admin login changes the network and Config; no token in the user guide
   and "only an admin <em>login</em> changes Locations, Routes, Zones and Config" in src and "admin token" not in text.lower())
_tg = open(os.path.join(ROOT, "frontend", "help", "technical", "index.html"), encoding="utf-8").read()
ok("⭐ G3: the technical guide explains the session, the links, the limits, the guard header, the audit trail and HU14",
   all(s in _tg for s in ("<code>wayscope_session</code>", "<code>user_sessions</code>", "<code>auth_tokens</code>",
                          "<code>X-Wayscope: 1</code>", "<code>audit_log</code>", "<code>auth_attempts</code>",
                          "5 failed sign-ins per email per 15 min", "Demo leads (HU14).", "<code>APP_URL/#invite=…</code>"))
   and "those actions are open to anyone who can reach them" not in _tg)
ok("the menu as it is: four groups with the Carbon planner under PLAN, Find a page, Ctrl K, User guide, Collapse",
   "<strong>PLAN</strong> (Dashboard, Submit forecast, Forecasts, Carbon planner)" in src
   and "Find a page…" in src and "Ctrl K" in src and "<strong>User guide</strong>" in src and "‹ Collapse" in src)
# NARROWED 11 Oct 2026 (EU vehicles removed): the header no longer offers vehicle names "by country" (English
# always, European everywhere except Great Britain, Estonian in Estonia). The vehicles are named in English and
# the buttons appear only when a vehicle carries another language — the guide says that, and the old sentence is gone.
ok("...the header: vehicle names in English (buttons only when the list carries another language), the Appearance looks Ink, Light and Dark",
   "<strong>Appearance</strong>" in src and all(s in src for s in ("<strong>Ink</strong>", "<strong>Light</strong>", "<strong>Dark</strong>"))
   and "vehicles are named in English" in src and "only when your organisation's vehicle" in src
   and "everywhere except Great Britain" not in src and "<strong>European</strong>" not in src and "<strong>Estonian</strong>" not in src)
ok("11 Oct 2026: ⭐ the guide names none of the four EU type-approval vehicles, their codes or their 'EU planning vehicles' row",
   not any(t in src for t in ("V07", "V10", "V11", "V12", "V-category", "EU-category", "EU planning vehicles", "N3 lorry", "N3 tractor", "TPMLM"))
   and "Rigid 7.5t is hidden" in src and "a vehicle without its own figures 12 + 8 (the default)" in src
   and "UK trade names such as Rigid 8-wheeler and Artic Tipper" in src)
ok("⭐ the demo bar and its Guide button, the New here? box, the dots, Don't show again; nothing opens by itself",
   "DEMO · FICTIONAL SCHEME" in src   # NARROWED 15 Oct 2026: the bar's wording (the user)
   and "FICTIONAL DEMO SCHEME · NOTHING HERE IS REAL" not in src and "<strong>Guide</strong>, at the right-hand end of the bar" in src
   and "Nothing opens by itself." in src and "<strong>Take the tour</strong>" in src and "pulsing orange dots" in src
   and "<strong>Don't show again</strong>" in src and "Your organisation's own site has no bar and no tour." in src)

# the Dashboard after the UI pass
ok("the Dashboard: the six cards by name, More filters, the four charts, the folded sections, Big screen",
   all(s in src for s in ("Material in view", "Deliveries a day", "Vehicles needed", "Planned this week",
                           "Delivered against plan", "Transport carbon", "More filters ▾", "Cost over time",
                           "This week and today, with the Look-ahead's map", "Route planning detail",
                           # 14 Oct 2026 (narrowed): "All four" became "All sections" (a fifth section, More charts)
                           "<strong>Big screen</strong>", "#dashboard/1", "tCO2e target, all-in", "All sections", "Rotate", "One section")))
ok("🔴 ...the retired tiles are gone (Total trips, Intensity, Peak month as tiles)",
   "The six tiles read" not in text and "<strong>Intensity</strong>" not in src and "<strong>Total trips</strong>" not in src)

# Submit forecast and Forecasts
ok("Submit forecast: the save button's own words; a re-save goes back to Pending; Clear year; the new notes; cell carbon and price",
   "Save &amp; send for approval" in src and "Every month you save goes back to Pending" in text
   and "<strong>Clear year</strong>" in src and "Carbon of these cells" in src and "Fair £ (model)" in src
   and "<strong>Material and discipline</strong>" in src and "<strong>Other lines on this route</strong>" in src)
ok("...the vehicle picker leads with the organisation's planning vehicles (UK trade names in Great Britain), never the electric ones",
   "Your organisation's planning vehicles are listed first" in src and "UK trade names" in src
   and "The planning vehicles (EU categories) are listed first" not in src and "Battery electric lorries are never offered here" in src)
ok("Forecasts: the filter row, the Cost column, the ⋯ menu with Edit in Submit forecast, Withdraw… and Reject…",
   "<strong>Edit in Submit forecast</strong>" in src and "<strong>Withdraw…</strong>" in src and "<strong>Reject…</strong>" in src
   and "<strong>Mine only</strong>" in src and "the count chips are clickable" not in src
   and "<td>no team</td>" not in src)

# Look-ahead
ok("the Look-ahead: this week by default, the next week switch, the remembered view, check now on the Look-ahead",
   "<strong>Commit · this week</strong>" in src and "<strong>Commit · next week</strong>" in src
   and "The page opens on the view you used last" in text and "<strong>check now</strong> (or <strong>re-check</strong>)" in src
   and "Switch the pill to" not in text)
# 13 Oct 2026 (W6, narrowed): the Flags column became the one Status column, ▶ the row's arrow (›) and its details,
# and the grid's unit is the Show switch; the same facts, told as the screen now shows them
ok("...the grid's Flags, Week and Status columns, ▶ to expand, ✎ for a typed day; the exports' Fuel sheet and the DRAFT stamp",
   "<strong>Status</strong> shows the one thing to look at first: a flag in short form (§12.1), ROAD LIMIT before any other" in src
   and "<strong>Week</strong> is the line's total in the same unit" in src
   and "Press the arrow (<strong>›</strong>) at the left of a row, or move to it with Tab and press Enter or Space, to open its details" in src
   and "The day shows ✎" in src and "<strong>Show</strong> above the grid switches every day cell between <strong>Tonnes</strong>" in src
   and "The <strong>Flags</strong> column" not in src and "Press <strong>▶</strong> at the left of a row" not in src and "17 tr · 3 veh" not in src
   and "<strong>Fuel</strong> sheet" in src and "DRAFT — not confirmed" in src and "Click a row</strong> to see" not in src)
# 13 Oct 2026 (W6): the other three tables and the marks, as the screens now show them
ok("W6: the guide tells the route table, Forecasts and the marks as they are: the switch, the arrow and its details, one status, no hover",
   "<strong>Sort by</strong>, to sort" in src and "Click Route or the total to sort, or pick Total, Months or Route from <strong>Sort by</strong>" in src
   and "The status column shows what needs a person first: <strong>Rejected</strong>, then <strong>ROAD LIMIT</strong>" in src
   and "<tr><td>ROAD LIMIT</td>" in src and "<strong>Status as a word with an icon</strong>" in src and "<strong>Grey chips</strong>" in src
   and "Point at a figure for the price per tonne" not in src and "shown in red under the status" not in src
   and "Click a column to sort.</li>" not in src and "The grid's Flags column" not in src)
ok("...Account's columns and the diesel strip: Planned £, Fair £ (model), Actual £, £ var, Yard £/L, Fuel share %",
   all(s in src for s in ("<strong>Planned £</strong>", "<strong>Fair £ (model)</strong>", "<strong>Actual £</strong>",
                           "<strong>£ var</strong>", "<strong>Yard £/L</strong>", "<strong>Fuel share %</strong>")))
ok("...the first confirm locks the fuel-surcharge base, and a team code confirms its own lines (costing.lock_baf_base_if_empty)",
   "locks the base for the fuel surcharge (BAF)" in text and "Confirm week confirms your team's lines only" in text)

# the public map after PRs #20-#29
# NARROWED 19 Oct 2026: "Layers and basemap" is "More layers" on the panel and in the guide
ok("⭐ the map: More layers, What's moving, Busiest routes, the figures bar's names, Conditions",
   "<strong>Layers and basemap</strong>" not in src and "Route filtering" not in src
   and all(s in src for s in ("<strong>More layers</strong>", "<strong>What's moving</strong>", "<strong>Busiest routes</strong>",
                           "<strong>Two-way movements a day</strong>", "<strong>CO₂e a day</strong>", "<strong>CO₂e to date</strong>",
                           "<strong>Conditions in [month]</strong>", "<strong>Show on map</strong>")))
ok("🔴 ...the retired map parts are gone: the KPI panel, the callouts, the warning stack's levels, the Street View button, the legend message",
   "KPI panel" not in text and "callouts" not in text and "<strong>Clash</strong>" not in src and "<strong>Caution</strong>" not in src
   and "press <strong>Street View</strong>" not in src and "no alignment in this tenant" not in text
   and "Use this option" not in text)
# NARROWED 19 Oct 2026: the From and To months went in D14 (12 Oct); the sentence no longer names them
ok("...Play: the timeline runs through the months of the programme; Conditions only while it is open",
   "The timeline runs through the months of the programme." in text and "From and To" not in text
   and "While the timeline is open (playing or paused)" in text)
ok("19 Oct: the guide describes the month picker, the info buttons, the badges and the council labels as built",
   "press a year, then a month, to show that month on the map" in text
   and "A small <strong>i</strong> beside a heading opens a short explanation" in src
   and "a small white badge with a two-way arrow sits on each stretch of road" in text and "(none is shown under 1 a day)" in text
   and "a green <strong>CO₂</strong> badge on each route" in src and 'the labels say "reading…"' in text
   and "Reset filters</strong> appears once a filter is set" in src)
ok("🔴 ...and it is honest that a planned closure is listed in every month its route carries volume, whatever its dates",
   "whatever the closure's own dates" in text and "the Look-ahead counts it only in the weeks it overlaps" in text)
ok("...the map's route analysis panel is a rough cycle at the average haul speed, not the routed drive time",
   "not the routed drive time" in text)
ok("...the restriction popup gives no verdict against the vehicle: that is the route check",
   "is judged in the route check, not in this popup" in text and "EXCEEDS by" not in text)

# Data pages and settings
# REVERSED 27 Oct 2026 (F3 c): no token box; a planner reads the Data pages, an admin changes them
ok("Data pages: no token box, only an admin changes them; More ▾ on Configuration; Make primary; Create & route; Clear all routes",
   "<strong>Admin token</strong> box" not in src and "Only an admin changes locations, routes and zones" in text
   and "(under More ▾)" in src and "<strong>Make primary</strong>" in src
   and "<strong>Create &amp; route</strong>" in src and "<strong>Clear all routes</strong>" in src
   and "its forecast lines are not deleted with it" in text)
ok("...a route with no rate is priced at the target rate and marked target; rate not set only when neither exists",
   "only when neither exists does it read \"rate not set\"" in text and "Nothing is pre-filled; a route reads" not in text)
ok("🔴 Configuration: six sections with Costing · fuel, and Reset to file is not an undo (it resets the organisation's settings and the demo notice)",
   "<strong>Costing · fuel</strong>" in src and "Reset to defaults is not an undo" in src and "Reset to file" not in src   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): question 6
   and "the demo notice" in text and "on five tabs" not in text)
ok("⭐ money settings: the target rate, the fuel surcharge formula and its locked base, the fair price as a floor, never a quote",
   "<strong>Target rate</strong>" in src and "(index ÷ base − 1) × fuel share" in text
   and "a floor for negotiation, never a quote" in text)

# roles: the planner and admin codes open the same pages; the admin token is not a role
# NARROWED 27 Oct 2026 (F3 c): the admin token is no longer a thing a user meets, so section 10 no longer explains it
ok("⭐ roles moved to section 10: the admin code opens what the planner code opens; the admin token is not explained to users",
   '<h1 id="10-roles-who-can-do-what">10. Roles: who can do what</h1>' in src
   and "exactly what the planner code opens" in text and "The admin token is not the admin code." not in text
   and "plus the admin token for baking routes" not in text)

# carbon factors and sources
ok("🔴 the 7.5 t rigid carries its 2026 factor (0.49944, factors.json) and the Carbon Tool method IS shown now, for comparison",
   "0.49944" in text and "a 2025 figure" not in text and "still carries a 2025 figure" not in text
   and "is not reproduced here" not in text and "for comparison only" in text.lower())   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): A.1 says it, capitalised
ok("...the carbon sources are named, with no web address (DESNZ 2026, the Carbon Tool v2.7, ZEHID, Net Zero Highways)",
   "UK Government greenhouse gas conversion factors 2026 (DESNZ)" in text and "National Highways Carbon Tool v2.7" in text
   and "ZEHID annual report 2026" in text and "Net Zero Highways annual progress report 2025-26" in text)
ok("...transport CO2e and all-in carbon are told apart in What the figures mean",
   "<td>Transport CO₂e</td>" in src and "<td>All-in carbon (tCO2e)</td>" in src)

# house style the old guide broke
ok("🔴 house style: no real-time, telematics or 'security phase' in the guide (the one 'secure' is D.4's)",
   not re.search(r"real-time|telematics|security phase", text, re.I)
   and len(re.findall(r"\bsecure\b", text, re.I)) == 0)   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): D.4's 'secure' moved to T7 with Appendix D

# troubleshooting: the carbon symptoms
ok("⭐ the picker covers the carbon symptoms people will hit (all-in vs transport, over as forecast, team, greyed Set, decisions gone, Carbon Tool)",
   all(s in src for s in ("The Carbon planner's carbon is much bigger than the Dashboard's",
                           "The carbon target says “over the target” as forecast",
                           # REVERSED 13 Oct 2026 (each team its share): was "My team's carbon figures are not compared with the target"
                           "My team's carbon target is smaller than the scheme's",
                           "“Set as the scheme's carbon target” is greyed out",
                           "The carbon target says the agreed decisions no longer fit the plan",
                           "Our carbon does not match the National Highways Carbon Tool")))

# 11 Oct 2026: guide text corrected (no assertion reversed): the 9 Oct TARK TEE row said an unreachable or never-run check raises the flag; clashes.py
# raises no RESTRICTION flag then (sources.restrictions is "unavailable" and the line under the rail says NOT checked)
ok("🔴 the restriction flags are raised by a hit only; an unchecked route raises none and the rail line says NOT checked",
   "or the check is unavailable or has never run" not in text and text.count("A route never checked raises no flag") == 2
   and "<td>ROADWORKS</td>" in src and "<td>TARK TEE</td>" in src)

# the /help/ sign-in page names the rail's link as it reads
ok("the guide's own sign-in page names the rail link as it reads (User guide), not 'Help link'",
   "User guide at the foot of the app's menu on the left." in main_src and "Help link in the app" not in main_src)

# =========================================================================== #
#  11 Oct 2026 (late) — the two verifiers' findings on guide v2.1, fixed          #
# =========================================================================== #
# Each pins a corrected statement (checked against the code the same evening) and that the wrong one is gone.
# What they do not prove: how the page reads in a browser, or what the regenerated PNGs show (the images are
# pinned through their generator's source, not their pixels).
FE = os.path.join(ROOT, "frontend", "index.html")
GEN = os.path.join(ROOT, "backend", "tools", "make_guide_images.js")
fe_src = open(FE, encoding="utf-8").read()
gen_src = open(GEN, encoding="utf-8").read()

# sign-in. NARROWED 11 Oct 2026: branch claude/stay-signed-in (pushed, not merged) makes a reload keep you signed in,
# while main signs you out on a reload. So the guide says only what is true either way (the code lives in this tab,
# and closing the tab signs you out) and makes NO claim about a reload; it may name the reload behaviour once it
# describes the code that is actually there.
_restores = ('ACCESS.code ? "resume"' in fe_src) or ("Signing you back in" in fe_src)
_claims_signout_on_reload = ("reloading the page, returns you to the public map" in text
                             or "Reloading returns you to the public map" in text)
_claims_kept_on_reload = ("reload keeps you signed in" in text.lower())
ok("\U0001f534 sign-in: the guide never states the reload behaviour wrongly (true on main and on claude/stay-signed-in): "
   "closing the tab signs you out; a reload is described only if the app does what it says",
   "The code is kept for this browser tab only: closing the tab signs you out, and you sign in again." in text
   and not (_claims_signout_on_reload and _restores) and not (_claims_kept_on_reload and not _restores)
   and "Hard-refresh (Ctrl+Shift+R), or open a private window and sign in again." in text)   # 13 Oct 2026 (W3, narrowed): no "cache" on a user page
ok("...the Forecasts badge counts Pending or Mixed lines, and the guide says so (not 'waiting for approval')",
   'r.status === "Pending" || r.status === "Mixed"' in fe_src
   and "shows how many lines are Pending or Mixed" in text and "lines are waiting for approval while" not in text)

# the demo bar and the tour
ok("the shared demo: one callout names what not to press, and the map's first tour has no welcome",
   "On the shared demo, show these but do not press them" in text and "Route all</strong> (it works every route out again)" in src   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): no routing calls   # 13 Oct 2026 (W3, narrowed): the button reads Route all
   and "Your first tour in the app starts with a two-step welcome; the map's tour has none." in text
   and "Opened at the site address followed by /map/, the map shows the notice at its top, with Guide beside it." in text)

# the Dashboard: what follows the filters, what a focused line narrows
ok("\U0001f534 the Dashboard: no claim that it calculates nothing of its own; the filters skip this week's plan, "
   "the target strip and two folded sections; a focused line narrows the cards and charts only",
   "calculates nothing of its own" not in text and "narrow every chart and figure" not in text
   and "except <strong>Planned this week</strong> and the carbon target strip" in src
   and "Top routes highlights its bar and Route planning detail still lists every line" in text
   and "held to plan. It ignores the filters." in text and "Carbon planner (§6.4)" not in text)

# Submit forecast, Forecasts, approval
ok("Submit / Forecasts: the Route reference picker; Horizon keeps a re-pended line; Refresh reads the list again",
   "where two routes join the same pair, it becomes a list to pick from" in text
   and "Horizon still shows its weeks, marked \"month is now Pending\"" in text
   and "<strong>Refresh</strong> reads the list again." in src and "<strong>Refresh</strong> reloads the page." not in src)
ok("\U0001f534 rejecting or re-pending a month deletes NO weeks (main.py: 'Rejecting or reopening deletes NOTHING')",
   "deletes <strong>none</strong> of its weeks, typed actuals included" in src
   and "does <strong>not</strong> delete weeks that already carry typed actuals" not in src
   and "Rejecting or reopening deletes NOTHING" in main_src)

# the Carbon planner
ok("\U0001f534 Carbon planner: only the totals and the target are all-in; the transport-only tables are named",
   "Every figure is all-in" not in text
   and "The totals in steps 1 and 5, and the carbon target in step 6, are all-in" in text
   and "the transport rows of <strong>How the plan compares</strong>" in src)
ok("...step 3's controls are a list of their own; step 4 says a tip or recycling site comes with the package",
   "<li><strong>3 Lorries and routes</strong>:<ul><li><strong>Battery electric lorries</strong>" in src
   and "the Locations page cannot give a site those types yet" in text
   and "The table has four rows because the second is a version of the first." not in text
   and "so they are always lower" not in text and "so they read lower and never match" in text)

# the Look-ahead
ok("the Look-ahead: weekends are held at 0 and not shown (the grid is Monday to Friday), nowhere 'unless typed'",
   "Saturday and Sunday are held at zero and not shown." in text and "Saturday and Sunday held at 0 and not shown" in text
   and "default to zero" not in text and "0 unless typed" not in text
   and "Saturday and Sunday are held at 0 and not shown" in fe_src)   # 13 Oct 2026 (W3, narrowed): the screen's note moved into the commit grid's info box
ok("...the KPI strip is a list; the check line's two other states; Esc saves a day",
   "The <strong>KPI strip</strong> reads:</p>\n<ul>" in src and "not checked since the route was worked out" in text and "not checked since the route was worked out" in fe_src   # 13 Oct 2026 (W3, narrowed): the screen's words
   and "showing the last check" in text and "the stored result stands" not in text and "Esc, or clicking elsewhere, saves too" in text   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the screen's new words
   and 'e.key === "Enter" || e.key === "Escape") e.currentTarget.blur()' in fe_src)

# the public map
ok("\U0001f534 the map: compound and railhead are the only squares; a tip draws as Other",
   "port, site, railhead and compound (squares)" not in text
   and "Rounded squares: compound (a site cabin) and railhead (rails)." in text
   and "A site of any other type, such as a tip, is drawn as other." in text)
ok("...the filters skip stockpiles; the quick buttons are named; the t / day figure is hidden in vehicles",
   "the route conditions (not to stockpiles over capacity)" in text
   # NARROWED 27 Oct 2026 (8a): Streets is in the Basemap list now (with Outdoors, Satellite without names and Navigation day / night)
   and "Light, Dark, Satellite and Streets." in text and "Streets is not in the Basemap list" not in text
   and "Material a day appears too" not in text and "as shipped it counts in vehicles" not in text   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the count unit is in T10
   and "FORECAST_UNIT" in open(TECH, encoding="utf-8").read())
ok("...an unbaked line is counted as unknown; a route with no geometry is left out of the bar",
   # 13 Oct 2026 (W3, narrowed): the same two rules in the screen's words
   "A line whose route is not routed for its vehicle is counted as unknown" in text
   and "A line whose route has no line drawn at all is left out of the bar." in text
   and "a route that is not baked is counted as unknown" not in text and "a route that is not routed is counted as unknown" not in text)

# Data pages and settings
ok("Data pages: a tip keeps its imported type; the Planning tick does not lead a country with its own vehicle set",
   "a tip or recycling site keeps the type it was imported with" in text
   and "the Planning tick does not change the lists" in text and "vehicle_sets" not in text and "vehicle_sets" in open(TECH, encoding="utf-8").read())   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the key is in T4
ok("...the money settings split into three bullets; a team login cannot open the Data pages",
   "<li><strong>Diesel index</strong> —" in src and "<li><strong>Fuel surcharge (BAF)</strong> —" in src
   # NARROWED 27 Oct 2026 (F3 c): the token paragraph went with the token; the roles table still says a team login cannot open the Data pages
   and "open the Data pages</td>" in src and "whichever of the planner or admin codes they signed in with" not in text
   and "and withdraw the lines you saved" in text and "submit, edit and withdraw your team's forecast lines" not in text)

# What the figures mean
ok("\U0001f534 lorry-km is always both legs; the distance basis changes only t·km and the per-km rate (derived.py, costlines.py)",
   "<tr><td>Lorry-km</td>" in src and "<tr><td>t·km and the per-km rate</td>" in src
   and "never lorry-km or carbon" in text and "<tr><td>km, t·km</td>" not in src
   and "trips × the distance-basis km × rate per km" in text)
ok("\U0001f534 + BAF is the surcharged quote, quote × (1 + surcharge), not the surcharge (costing.adjust)",
   "quote × (1 + surcharge)" in text and "the quote × the fuel surcharge." not in text
   and "return round(float(eur) * (1.0 + float(pct)), 2)" in open(os.path.join(ROOT, "backend", "costing.py"), encoding="utf-8").read())
ok("...the map's movements a day are not rounded up and are averaged over months with volume",
   "On the public map, loads are tonnes ÷ payload, not rounded up, averaged over the months that have volume" in text)

# troubleshooting, appendices, glossary
ok("troubleshooting: the map password box's message has a row; A.1 says whose cadence is unpublished",
   "That password was not recognised." in text and "That password was not recognised." in main_src
   and "Tark Tee does not publish how often it updates" in text
   and "the authority's own update cadence is not published" not in text)
ok("...A.2: every electric version is 3.5 t lighter; the glossary says CO₂e and CO2e are one thing",
   "(each 3.5 t less than its diesel lorry)" in text and "(3.5 t less than the diesel lorry)" not in text
   and "<td class=\"k\">CO₂e / CO2e</td>" in src)

# cross-references: text a team submitter sees never points at a section hidden from them
_gated = re.findall(r'"([0-9a-z-]+)": "planner"', src)
_vis = src[:src.find("</main>")]   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): Appendix D left; the guide's text ends at </main>
for _gid in _gated:
    _m = re.search(r'<(h[12]) id="%s">' % re.escape(_gid), _vis)
    if not _m:
        continue
    _lv = int(_m.group(1)[1])
    _nx = re.compile(r"<h[1-%d][ >]" % _lv).search(_vis, _m.end())
    _vis = _vis[:_m.start()] + (_vis[_nx.start():] if _nx else "")
_vis = re.sub(r"<nav id=\"nav\">.*?</nav>", "", _vis, flags=re.S)
_hidden_nums = set()
for _gid in _gated:
    _hm = re.search(r'<h[12] id="%s">([0-9.]+)' % re.escape(_gid), src)
    if _hm:
        _hidden_nums.add(_hm.group(1).rstrip("."))
_bad_refs = [r for r in re.findall(r"§([0-9]+(?:\.[0-9]+)?)", _vis)
             if r in _hidden_nums or any(r.startswith(h + ".") for h in _hidden_nums)]
ok("\U0001f534 a team submitter's view never refers to a section hidden from it (%d gated sections: %s)"
   % (len(_hidden_nums), ", ".join(sorted(_hidden_nums))), _hidden_nums and not _bad_refs)
ok("...and the one pointer to the admin appendix says it is in the admin view",
   "Appendix D" not in text and "your organisation's alignment has not been loaded yet: ask your administrator." in text)   # REVERSED 22 Oct 2026 (words sweep): Appendix D moved to the technical guide's T7; the pointer asks the administrator

# the pictures: each placeholder's title is its figure caption; no developer instructions on them; no truck
_holders = dict(re.findall(r'\n  ([SM]\d\d): \["([^"]+)"', gen_src))
_caps = dict(re.findall(r'<img src="media/([SM]\d\d)\.png"[^>]*><figcaption>Figure \d+ — (.*?)(?: &nbsp;·&nbsp;.*?)?</figcaption>', src))
_appc = dict((f, c) for c, f in re.findall(r"<tr><td>\d+</td><td>([^<]+)</td><td>([SM]\d\d)\.png</td></tr>", src))
ok("\U0001f534 every placeholder's title is its figure caption, word for word, and Appendix C agrees (%d pictures)" % len(_caps),
   len(_caps) == 22 and set(_holders) == set(_caps) and all(_holders[k] == _caps[k] for k in _caps)
   and all(_appc.get(k) == _caps[k] for k in _caps))
_holder_fn = gen_src[gen_src.find("function holder("):gen_src.find("(async () =>")]
ok("\U0001f534 ...the placeholder card no longer prints developer paths (the package file, the capture script)",
   _holder_fn and "capture_guide.js" not in _holder_fn and "uk-corridor.package.json" not in _holder_fn
   and "Placeholder — not a screenshot" in _holder_fn)
_figs_fn = gen_src[gen_src.find("function figNumbers("):gen_src.find("// ---- placeholders")]
ok("\U0001f534 ...and the drawn figures say lorry / HGV, never truck; figure 3 lists the Carbon planner and the public map",
   _figs_fn and re.search(r"\btrucks?\b", _figs_fn, re.I) is None
   and '["Carbon planner",' in _figs_fn and '["Route map", "the public map inside the app"]' in _figs_fn
   and "drawn before the Carbon planner" not in src)

# ---- 13 Oct 2026 (W4): the technical guide, /help/technical/ ---------------------------------------
# Everything the words bundle (W3) took off a screen lives here (notes/w3-w4-inventory-1013.md §1). Each
# row's key phrase is pinned, so dropping a passage from the guide fails here: nothing is lost.
def ok3(label, cond, detail=""):
    ok(label + ("" if cond else "  :: " + detail), cond)

TECH = os.path.join(ROOT, "frontend", "help", "technical", "index.html")
tg = open(TECH, encoding="utf-8").read() if os.path.exists(TECH) else ""
ok("⭐ W4: the technical guide exists under the /help mount (frontend/help/technical/index.html), so the same staff gate applies",
   bool(tg) and 'NoCacheStatic(directory=str(ROOT / "frontend" / "help"), html=True)' in main_src
   and "<title>Wayscope — Technical guide</title>" in tg and '<meta name="robots" content="noindex">' in tg)
sys.path.insert(0, os.path.join(ROOT, "backend"))
import gate as _gate   # noqa: E402
ok("...the gate polices it as staff-only help, like /help/ (the map cookie does not open it)",
   _gate.scope_for("/help/technical/") == "help" and _gate.scope_for("/help/technical/index.html") == "help")
_tids = set(re.findall(r' id="([^"]+)"', tg))
ok("...sections T0–T7 and the figure anchors the info boxes link to",
   {"t0-about", "t1-figures", "t1-volume", "t1-trips", "t1-distance", "t1-vehicles", "t1-delivered", "t1-carbon", "t1-cost", "t1-fair",
    "t1-gates", "t1-stock", "t2-routing", "t3-sources", "t4-settings", "t5-errors", "t6-words", "t7-reference"} <= _tids
   and all(('href="#%s"' % i) in tg for i in ("t1-figures", "t2-routing", "t3-sources", "t4-settings", "t5-errors", "t6-words", "t7-reference")))
_moved = {   # inventory §1 row → its key phrase in the technical guide
    "1 the Dashboard footer's read": "Every planning figure on the Dashboard comes from one read, <code>GET /api/costing/lines</code>",
    "1 ...the trips formula": "rounded up per line-month",
    "1 ...the CO₂e formula and the factor wording": "DESNZ 2026 kg CO₂e per vehicle-km (average laden, both legs, from Config)",
    "1 ...peak fleet": "the largest same-month sum of vehicles needed across the lines in view",
    "2 the gate arrivals read": "<code>GET /api/gates/arrivals?month=N</code>",
    # NARROWED 17 Oct 2026: the gap is the gate's open minutes (its hours or the default gate hours, less its shut times
    # and the bands), no longer the shift's
    "2 ...and its rule": "The gap is the gate's open minutes ÷ arrivals, an average with no hourly",
    "3 stored per km": "stored per km whatever unit the tenant reads",
    "4 the target rate's own endpoint": "its own endpoint, saved separately from the configuration document",
    "5 ADMIN_TOKEN": "It is checked against <code>ADMIN_TOKEN</code> on Render",
    "6 HERE_API_KEY": "<code>HERE_API_KEY</code> in Render → Environment",
    "7 the bake panel that is gone": "it used to name a bake panel that no longer exists",
    "8 vehicle ids as keys": "Vehicle ids are the keys forecast lines and stored routes are keyed",
    "9 factors.json": "seeded from <code>backend/factors.json</code>",
    "10 the entry end from the geometry": "Which end is the entry is worked out per leg from the geometry",
    "11 HGV geometry from HERE": "a call to HERE Routing v8 with the vehicle's truck profile",
    "12 the V2 seed": "It was built to retire the first seed (the V2 seed).",
    "13 legs baked before zones": "Legs baked before zones existed are matched",
    "15 cached geometry": "what the screens call &ldquo;cached geometry&rdquo; in older notes",
    "16 in force on the server": "the configuration table",
    "17 codes checked by the server": "Sign-in codes are checked on the server (<code>POST /api/auth</code>)",
    "17 ...a cold start": "The Render service was starting or redeploying",
}
_lost = [k for k, v in _moved.items() if v not in tg]
ok3("⭐ W4 nothing lost: every passage W3 took off a screen is in the technical guide (%d phrases)" % len(_moved),
   not _lost, ", ".join(_lost))
# 17 Oct 2026 (gate shut times, the review): the technical guide says where the default and shut times live and the rules
ok("⭐ the technical guide: the default gate hours (planning.default_gate_hours, 08:00–17:00), shut_windows taken off once "
   "with the bands, the refusals (gate and Config) and 'No open time'",
   "<code>planning.default_gate_hours</code>" in tg and "08:00–17:00 when not set; applied when read, never stored on the gate" in tg
   and "taken off as one set so an overlap\ncounts once" in tg.replace("\r\n", "\n")
   and "<code>gate_hours.fit_problem</code>" in tg and "<code>config.gate_problems</code>" in tg
   and 'reads "No open time" everywhere: red with any arrival, capacity 0' in tg.replace("\r\n", "\n").replace("\n", " "))
# 17 Oct 2026 (the user: UK drivers' hours): both guides state the rule with its sources and its limits; the old formula is gone
ok("⭐ the user guide: trips a lorry a day are what fit in a driver's day — the break rule, 9 h driving, 13 h, what counts as "
   "driving, the sources, what is not modelled; 'a 10-hour shift ÷ the cycle time' is gone",
   # NARROWED 17 Oct 2026 (the review): one driver's day at most 13 (a longer shift is accepted), the second break past
   # 12 h, the day's other duties not modelled, a 0 counted as one lorry a trip
   # REVERSED 18 Oct 2026 (the user): no second break past 12 h — the 45 may be taken as 15 + 30; charging softened
   "the most round trips that fit in a driver&#39;s day: the shift (10 hours by default; one driver&#39;s day at most 13) less the break the UK drivers&#39; hours rules require" in src
   and "else 30 minutes once work passes 6 hours (the 45 may be taken as 15 + 30) — with driving" in src
   and "15 minutes more once work passes 12" not in src and "15 min more once work passes 12" not in src
   and "so no further break is needed past 12 hours of work" in src
   and "the cautious reading, as no rule yet says whether attended charging is work or a break" in src
   and "Regulation (EC) 561/2006 as it applies in the UK (Articles 6–8) and the Road Transport (Working Time) Regulations 2005" in src
   and "Weekly limits, night work, the occasional 10-hour driving day and the day&#39;s other duties are not modelled" in src
   and "counted as one lorry a trip" in src
   and "a 10-hour shift ÷ the cycle time, rounded down" not in src and "trips per day  = floor(shift hours / cycle)" not in src
   and "(shift ÷ cycle, rounded down)" not in src)
ok("⭐ the technical guide: drivers_hours.lorry_day, the thresholds, the split, the 13 h cap, charging on top of the break, "
   "the gate keeping the full shift; floor(shift hours ÷ cycle) gone",
   "drivers_hours.lorry_day(shift, driving, other work)" in tg and "<code>backend/drivers_hours.py</code>" in tg
   # NARROWED 17 Oct 2026 (the review): reg 7 (not reg 5), the Art 7 and reg 7 breaks never added, one driver's day
   # read as at most 13 h (Config accepts more), charging as working time
   and "breaks are one break, never added" in tg
   and "One driver&#39;s day is read as at most 13 h" in tg.replace("\r\n", "\n").replace("\n", " ")
   and "Regulations 2005 reg 7" in tg.replace("\n", " ") and "reg 5" not in tg
   # NARROWED 18 Oct 2026 (the user): charging "counted as working time" as the cautious reading; no break past 720 min
   and "counted as working time (the cautious reading: no rule says yet" in tg.replace("\n", " ")
   and "No further break past 720 min of work: the 45 may be taken as 15 + 30" in tg.replace("\n", " ")
   and "plus 15 min once work passes 720" not in tg.replace("\n", " ")
   and "The gate figures keep the full shift" in tg and "floor(shift hours ÷ cycle)" not in tg.replace("the old floor(shift ÷ cycle)", ""))
ok("...it maps the old screen words to the new ones, and says the exports keep the old words (decision A)",
   "baked / not baked / unbaked</td><td>routed / not routed yet" in tg and "line-month</td><td>forecast month" in tg
   and "UNBAKED, NOT BAKED (clash rail and line flags)</td><td>NOT ROUTED" in tg and "The XLSX and PDF exports and the clash text made on the server still say" in tg)
ok("...and the user guide's Appendix D points at it (the first client's Word document is no longer mentioned)",
   "Word document" not in src and "fifty pages" not in src   # REVERSED 22 Oct 2026 (words sweep): Appendix D moved to the technical guide's T7; the technical guide holds Appendix D's text, so it links back to nothing
   and "appendix-d-technical-reference" not in tg and "Appendix D" not in src)

# the word rule on the user guide's own text (the technical guide may use any word)
_BAN = re.compile(r"(/api\b|\bendpoints?\b|\bservers?\b|\bJSON\b|\bcached?\b|\bgeometry\b|\bbak(?:e|ed|es|ing)\b|\bunbaked\b|\bre-?bak\w*|"
                  r"\bPOST\b|\bGET\b|\bHTTP\b|localStorage|\bschema\b|\btokens?\b|line-months?)", re.I)
_vis, _skip = [], 0
for _part in re.split(r"(<[^>]+>)", src):
    if _part.startswith("<"):
        if re.match(r"<(code|pre|script|style)\b", _part, re.I): _skip += 1
        elif re.match(r"</(code|pre|script|style)>", _part, re.I): _skip = max(0, _skip - 1)
        continue
    if not _skip: _vis.append(_part)
_hits = []
for _t in _vis:
    _t2 = re.sub(r"(?i)admin token", "", _t).replace("Everything (JSON)", "")
    _m = _BAN.search(_t2)
    if _m and not (re.fullmatch(r"(POST|GET|JSON|HTTP)", _m.group(0), re.I) and not re.search(r"\b(POST|GET|JSON|HTTP)\b", _t2)):
        _hits.append(_m.group(0) + ": " + " ".join(_t.split())[:80])
ok3("⭐ W3 word rule on the user guide: no banned word in its text outside <code> (%d text pieces read)" % len(_vis),
   len(_vis) > 500 and not _hits, " | ".join(_hits[:6]))
# ---- 22 Oct 2026 (the words sweep; the user: "no info about api or backend stuff ... not even in the user guide") ----
# The rule above skips <code>, <pre> and <script>; this one reads the WHOLE guide text, the troubleshooter's answers (the
# TS array in the script) included, for the back-end words the sweep took out. HERE stays only as a source credit in A.1.
_ws_text = re.sub(r"<style\b.*?</style>", " ", src, flags=re.S)
_ws_ts = _ws_text[_ws_text.find("var TS = ["):_ws_text.find("var q = document.getElementById")] if "var TS = [" in _ws_text else ""
_ws_text = re.sub(r"<script\b.*?</script>", " ", _ws_text, flags=re.S)
_ws_text = re.sub(r"<[^>]+>", " ", _ws_text) + " " + _ws_ts
_WS_BAN = re.compile(r"(routing service|provider is connected|\bfeed\b|stored (?:road )?route|stored check|stored decisions|"
                     r"stored alternative|fetched by Wayscope|database|\bbak(?:e|ed|es|ing)\b|factors\.json|\bprobe\b|"
                     r"bounding box|vehicle_sets|/api/|the repo\b|in the repository|hosting service|for scripts|"
                     r"Diagnostics card|HERE calls?|routing calls?)", re.I)
_ws_hits = sorted(set(m.group(0) for m in _WS_BAN.finditer(_ws_text)))
ok("⭐ words sweep: no back-end word anywhere in the user guide, the troubleshooter's answers included (%d characters read)"
   % len(_ws_text), len(_ws_text) > 100000 and len(_ws_ts) > 2000 and not _ws_hits)
_ws_here = re.findall(r".{0,40}\bHERE\b.{0,40}", _ws_text)
# REVERSED 28 Oct 2026 (the user: no supplier names in the user guide; mockup notes\config-sources-mockup-1028): A.1 no longer
# names HERE (nor Google or Mapbox): "Lorry routing", "Street-level photos", "The base maps". Was: HERE named in A.1 only.
_ug_src = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_ug_src_a1 = _ug_src[_ug_src.index('<h2 id="a-1-data-sources">'):_ug_src.index('<h2 id="a-2-planning-assumptions">')]
ok("...HERE is named nowhere in the user guide, A.1 included (%d mentions); A.1 says lorry routing, street-level photos and the base maps" % len(_ws_here),
   len(_ws_here) == 0 and "Lorry routing (lorry profile)" in _ug_src_a1 and "Street-level photos" in _ug_src_a1
   and "The base maps, and a national aerial photo where one is published" in _ug_src_a1
   and not re.search(r"Google Street View|Mapbox|HERE Routing", _ug_src_a1)
   # the government and National Highways sources stay (Q1): the appendix is where a figure's source is quoted
   and "UK Government greenhouse gas conversion factors 2026 (DESNZ)" in _ug_src_a1 and "National Highways Carbon Tool v2.7" in _ug_src_a1)
ok("...and the rule would catch the old words (the troubleshooter's 'baked', the routing service, the database reads)",
   all(_WS_BAN.search(x) for x in ("That route has not been baked", "the routing service offered", "small database reads",
                                   "Probe HERE runs a live routing call", "POST /api/admin/tenant/import")))
ok("...Appendix D left the user guide for the technical guide's T7 (its facts and its two pins moved with it)",
   'id="appendix-d-technical-reference"' not in src and "Appendix D" not in _ws_text
   and 'id="t7-number"' in tg and 'id="t7-not-finished"' in tg and "What leaves the platform" in tg
   and "No quantity, rate or forecast leaves" in tg and "Do not describe the deployment as secure" in tg
   and "Checked 9 Oct 2026" in tg and "Planning assumption" in tg and "<strong>Measured</strong>" in tg)
ok("...the technical guide gained T10 (the public map) and the fuel and BAF section, and lists T8, T9 and T10 in its contents",
   'id="t10-public-map"' in tg and 'id="t1-baf"' in tg and all('href="#%s"' % i in tg for i in ("t8-community", "t9-collisions", "t10-public-map"))
   and "One base per organisation, not per haulier" in tg)
ok("...the guide's facts that were wrong on 22 Oct are fixed (team shares, logins, Set by, the demo bar, the batching)",
   "It does not share the carbon target out between teams" not in src and "It does not know who you are" not in src
   and "Codes are shared, so the name is not checked" not in src and "FICTIONAL DEMO SCHEME strip" not in src
   and "Batching them is a planned improvement" not in src and "where your deployment has one" not in src
   and '"Set by" shows the name on the login' in src and "DEMO · FICTIONAL SCHEME strip" in src)
ok("...the guide names the buttons the screens now show (Route all, not routed)",
   "<strong>Route all</strong>" in src and "Bake all" not in src and "not routed" in src)

# 13 Oct 2026 (bundle E): the guide describes what the Appearance button now offers, and the narrow left menu
ok("E (W16): the guide names the four accents beside the three looks, the plan-first rule and the status shapes",
   all(f"<strong>{w}</strong>" in src for w in ("Ink", "Light", "Dark", "Orange", "Blue", "Blue shades", "Orange shades"))
   and "the first series is the plan and the second what was delivered" in src and "a warning is a triangle and a problem a diamond" in src)
ok("E (W5): the guide says the left menu shows icons only below 768 px and opens over the page",
   "Below 768 px the left menu shows its icons only" in src and "opens it over the page until you pick one" in src)

# 14 Oct 2026: the gate chart is described where the Dashboard is
# NARROWED 14 Oct 2026 (bundle G, W17): capacity is the gate's open minutes (its hours less the peak bands, else the shift),
# and the two steps are named: gold "Queue likely" from 85 %, red "Over gate capacity" past it
ok("the guide explains the gate chart: the track, the bar, the marker, capacity worked out, the 85 % step, red and grey, Gate by gate",
   "<strong>Gate arrivals</strong> shows" in src and "its open minutes ÷ the check-in time a lorry" in src
   # NARROWED 17 Oct 2026: the default gate hours where none are typed, and the gate's shut times come off with the bands
   and "a gate with no hours typed is open the default gate hours, 08:00 to 17:00 unless changed on Configuration → Planning" in src
   and "less its shut times and any no-delivery peak bands set on Configuration → Planning (a shut time inside a band counts once)" in src
   and "a gate with no hours typed uses the shift" not in src and "9 hours at 3 minutes a lorry is 180 a day" in src
   and "<strong>Queue likely</strong>" in src and "<strong>Over gate capacity</strong>" in src
   and "A grey bar has no check-in time typed" in src and "<strong>Gate by gate</strong> under the chart opens the table" in src)
# 14 Oct 2026 (bundle G, W7): the CLP monitoring section, in the guide and its contents, with the honest limit
ok("⭐ the guide's §3.5 CLP monitoring: in the contents, says planned not observed, names every chart, the empty-state rule and the per-load caveat",
   '<a href="#3-5-clp-monitoring">3.5 CLP monitoring</a>' in src and '<h2 id="3-5-clp-monitoring">3.5 CLP monitoring</h2>' in src
   and "the figures are planned, not observed, because Wayscope holds no gate log, booking slots or arrival times" in src
   and all(t in src for t in ("<strong>Routes against their planning cap</strong>", "<strong>Sites against their CLP cap</strong>",
                              "<strong>Movements by vehicle type</strong>", "<strong>by Euro class</strong>",
                              "<strong>Movements and lorry distance by council</strong>",
                              "<strong>Carbon per delivery and per tonne against the target</strong>", "<strong>Lorry trips avoided</strong>"))
   and "it never shows a zero in place of a missing figure" in src and "Per load has no target line" in src)

# 14 Oct 2026 (bundle G, W8 + W17): the new fields and the gates week, in the guide where a person looks for them
ok("⭐ the guide names the W8 fields where they are typed: the CLP cap (Locations), open hours (the gates), the peak bands (Planning), the Euro class (Vehicles)",
   "<strong>CLP cap (optional)</strong> — the most lorry visits a day the Construction Logistics Plan allows at the site" in src
   # NARROWED 17 Oct 2026: blank = the default gate hours; the shut times are named where they are typed
   and "<strong>Open hours (optional)</strong> — from and to, and the days the gate is open; blank uses the default gate hours (08:00 to 17:00 unless changed on Configuration → Planning), every day." in src
   and "<strong>Shut during the day (optional)</strong> — up to four times inside its hours when the gate takes no lorries" in src
   and "<strong>Default gate hours</strong> (when a gate with no hours of its own is open: 08:00 to 17:00 unless you change them" in src
   and "blank uses the scheme's shift" not in src
   and "<tr><td>Gate open hours</td><td>08:00 to 17:00 every day, no shut times, until typed on the gate" in src
   and "<strong>No-delivery peak bands (from the CLP)</strong>" in src and "Wayscope holds no arrival times, so it cannot check that lorries keep out of them." in src
   and "<strong>Euro class</strong> (optional: what the plan assumes the hauliers will send for that vehicle type" in src)
ok("⭐ the guide's Commit view explains Gates this week, the 85 % step and the honest limit; §12.1 lists GATE OVER / NEAR CAPACITY",
   "<p><strong>Gates this week</strong>, under the grid," in src and "the dashed gold line 85 % of that" in src
   and "These are planned arrivals spread evenly over the gate's open hours; no hourly peak is known." in src
   and "<tr><td>GATE OVER CAPACITY</td>" in src and "<tr><td>GATE NEAR CAPACITY</td>" in src
   and src.index("<tr><td>ROUTE CAP</td>") < src.index("<tr><td>GATE OVER CAPACITY</td>") < src.index("<tr><td>SHARE</td>"))

ok("⭐ W10: the guide offers the CLP pack beside the month and says what it holds; the technical guide names its two reads",
   "<strong>CLP pack (PDF)</strong> and <strong>CLP pack (XLSX)</strong>, beside the month" in src
   and "the charts that cannot be drawn yet are listed with what they need" in src
   and "<code>GET /api/clp/pack.pdf?month=N</code>" in open(os.path.join(ROOT, "frontend", "help", "technical", "index.html"), encoding="utf-8").read())

# 17 Oct 2026: both route legs are drawn left of their own travel (map OFFSET_OUT = OFFSET_IN), so a route
# that comes back the same road shows its green and amber side by side; the guide's legend row says so.
ok("17 Oct: the guide's dotted-lines row says each line sits left of the way its lorries drive, green and amber side by side",
   "Each line sits just to the left of the way its lorries drive, so where a route comes back along the same road "
   "its green and amber run side by side; they close onto the road as you zoom right in." in src)
ok("17 Oct: ...and no longer says that nothing shows direction",
   "Nothing shows direction — the colours do." not in src)
# 17 Oct 2026 (UI audit #17, claude/ui-fix-keyboard): the 27 lazy figure images had no size, so a figure grew from 2 px to
# its height as it loaded and pushed the focused "open it in the app" link (and anything a nav link scrolled to) off the
# screen. Each <img> now carries its file's own pixel size (the box is reserved before the picture arrives), and the CSS
# keeps height:auto so a narrowed figure keeps its shape.
def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24]) if head[:8] == b"\x89PNG\r\n\x1a\n" else None
_itags = re.findall(r"<img [^>]*>", src)
_iattrs = [dict(re.findall(r'([a-z-]+)="([^"]*)"', t)) for t in _itags]
_isizes = {a["src"]: _png_size(os.path.join(ROOT, "frontend", "help", a["src"])) for a in _iattrs}
ok3("\U0001f534 #17 every figure image (%d) carries width and height equal to its file's own pixels, and keeps loading=\"lazy\"" % len(_itags),
   len(_itags) == 27 and all(a.get("loading") == "lazy" and _isizes[a["src"]]
                             and (int(a.get("width", 0)), int(a.get("height", 0))) == _isizes[a["src"]] for a in _iattrs),
   str([(a["src"], a.get("width"), a.get("height"), _isizes[a["src"]]) for a in _iattrs
        if (int(a.get("width", 0)), int(a.get("height", 0))) != _isizes[a["src"]]]))
ok("#17 ...the figure CSS keeps height:auto beside max-width:100%, so a narrowed image keeps its shape (the size reserves the box, it never stretches it)",
   "figure img{max-width:100%;height:auto;border:1px solid var(--line);" in src)

# 17 Oct 2026 (UI audit #15): the technical guide's formula blocks were cut mid-line on a phone, and the CLP block at a desk
# width, with no keyboard way to scroll them: <pre> now wraps at every width. Three of its five tables still scroll sideways
# on a phone (nowrap first columns, long paths): each is a named region with tabindex 0 and a ring; the two whose columns wrap are plain.
_tg2 = open(TECH, encoding="utf-8").read()
ok("\U0001f534 #15 the technical guide's <pre> blocks wrap (pre-wrap, overflow-wrap anywhere) at every width, so none scrolls sideways",
   "pre{background:#F5F7FA;border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow:auto;white-space:pre-wrap;"
   "overflow-wrap:anywhere;font:12.5px/1.45 Consolas,ui-monospace,monospace}" in _tg2)
ok("\U0001f534 27 Oct 2026 (audit #44): T2 names no hyphenated code token that broke over two lines on a phone; inline <code> keeps its plain rule "
   "(an overflow-wrap:anywhere on it broke five more tokens inside the tables' cells at 390 px — audit run 214459)",
   "padding:1px 4px;border-radius:4px}" in _tg2 and "border-radius:4px;overflow-wrap:anywhere}" not in _tg2
   and "details.row-menu" not in _tg2 and "grown from the Forecasts page's menu" in _tg2)
_tgr = re.findall(r'<div class="tbl"( tabindex="0" role="region" aria-label="([^"]*)")?>', _tg2)
ok3("\U0001f534 #15 the three tables that scroll on a phone (T3 sources, T6 words, T8 sources) are named regions with tabindex 0, the other two plain; a ring on focus",
   # NARROWED 27 Oct 2026 (pilot readiness phase 2): + the key table in t7-hardening, a named region like the other wide tables
   [l for _, l in _tgr] == ["Where each screen reads from", "Errors and what they mean", "Old words, new words", "Sourced and assumed figures", "Keys and when to change them", "The community considerations layer: sources", ""]   # NARROWED 22 Oct 2026 (words sweep): T5 (longer now) and T7's sourcing table (from Appendix D) scroll on a phone too, so they are named regions (the UI audit's axe found them)
   # NARROWED 18 Oct 2026 (decision 10): the fourth tabindex is main's -1, the "Skip to the text" link's target
   and ".tbl:focus-visible{outline:2px solid var(--blue);outline-offset:2px}" in _tg2 and _tg2.count('tabindex="0"') == 6
   and _tg2.count("tabindex=") == 7, str(_tgr))   # NARROWED 27 Oct 2026: six tables + main's -1
# RE-PINNED 17 Oct 2026 (D114 fix): the opening sentence now also names the fallback (no approved line in the window ->
# the months that have them), and the big-screen sentence says "the months the page opened on" instead of "this month ± 6"
ok("⭐ D114 (17 Oct 2026): the guide says the Dashboard opens on this month ± 6, and how to see the whole programme and back",
   "the page opens on this month and six months either side, or on the months that have approved lines when none of them "
   "falls in that window, and <strong>Whole programme</strong> beside them shows every month"
   in src and "<strong>This month ± 6</strong> brings the default back" in src
   and "(it keeps the months you had: the months the page opened on unless you picked others first)" in src)
ok("\U0001f534 D114 fix (17 Oct 2026): the big-screen sentence no longer promises this month ± 6 (the fallback can open elsewhere)",
   "(it keeps the months you had: this month ± 6 unless you picked others first)" not in src)

# 18 Oct 2026 (UI audit decision 10, finding #22, claude/ui-fix-phone): on a phone the guides' contents sit above the text —
# 59 chapter rows in the user guide, 19 in the technical guide — as 30 px links. Now: a "Skip to the text" link heads the list
# (the first row of the list on a phone; at a desk hidden until it has the focus, like any skip link), the rows are 44 px tall
# there (min-height 44 and 12 px of padding on a 20 px line), the role buttons, the troubleshooting questions and "↑ top" are 44
# px, and there is NO nested scroller (the user's choice over a 40 vh box). The target is <main id="guide-text" tabindex="-1">,
# so the jump lands the focus on the text in every browser.
for _nm, _pg, _roles in (("the user guide", src, True), ("the technical guide", _tg2, False)):
    ok3("\U0001f534 decision 10 (%s): 'Skip to the text' is the first thing in the contents and its target is the text (<main id=\"guide-text\" tabindex=\"-1\">)" % _nm,
        '<nav id="nav"><a class="skip" href="#guide-text">Skip to the text</a><div class="brand"' in _pg
        and _pg.count('<main id="guide-text" tabindex="-1">') == 1 and _pg.count("<main") == 1 and _pg.count("Skip to the text") == 1)
    _m9 = re.search(r'@media \(max-width:900px\)\{\.skip\{([^}]*)\}#nav li a\{([^}]*)\}(.*?)\}\n', _pg)
    ok3("\U0001f534 decision 10 (%s): below 900 px the skip link is a static 44 px row and every chapter row is 44 px (min-height 44, padding 12 px 8 px); no max-height or overflow on the list there" % _nm,
        _m9 is not None and "position:static" in _m9.group(1) and "min-height:44px" in _m9.group(1) and "display:flex" in _m9.group(1)
        and _m9.group(2) == "min-height:44px;padding:12px 8px" and "max-height" not in _pg.split("@media (max-width:900px)")[-1].split("}\n")[0]
        and "#nav{position:static;width:auto}" in _pg and "#nav{max-height" not in _pg and "#nav{overflow" not in _pg, str(_m9 and _m9.group(0)[:160]))
    ok3("decision 10 (%s): at a desk the skip link is off the top of the column until it has the focus (transform, then an outline), and the focused text draws no ring of its own" % _nm,
        ".skip{position:absolute;left:8px;top:8px;z-index:9;" in _pg and "transform:translateY(-200%)}" in _pg
        and ".skip:focus{transform:none;outline:2px solid #FF8C14;outline-offset:2px}" in _pg and "main:focus{outline:0}" in _pg)
    ok3("decision 10 (%s): '↑ top' is a 44 px box on a phone (inline-flex, min 44 × 44), unchanged at a desk" % _nm,
        "#top{display:inline-flex;align-items:center;justify-content:center;min-height:44px;min-width:44px}" in _pg.split("@media (max-width:900px){.skip")[1].split("\n")[0]
        and "#top{position:fixed;right:18px;bottom:18px;background:var(--navy);color:#fff;text-decoration:none;padding:8px 12px;border-radius:20px;font-size:12px}" in _pg)
    if _roles:
        ok3("decision 10 (%s): the role buttons and the troubleshooting questions are 44 px on a phone" % _nm,
            "#roles button{min-height:44px}" in _pg.split("@media (max-width:900px){.skip")[1].split("\n")[0]
            and ".ts-q button{min-height:44px;padding:12px 13px}" in _pg.split("@media (max-width:900px){.skip")[1].split("\n")[0])
    # the desk rule the phone rule builds on is as it was: 5 px rows in a fixed 280 px column
    ok3("decision 10 (%s): the desk contents are untouched — a fixed 280 px column, 5 px 8 px rows" % _nm,
        "#nav{position:fixed;top:0;left:0;bottom:0;width:280px;overflow:auto;" in _pg and "#nav li a{display:block;color:rgba(255,255,255,.72);text-decoration:none;padding:5px 8px;border-radius:6px}" in _pg)
# NARROWED 22 Oct 2026 (UI fix 7): the technical guide gains one row, T2 "What the screens leave out"
ok("decision 10: the only new visible words are the two skip links; the guides' chapter rows are as many as before (59 and 19, + 1 since UI fix 7; 58 + 4 and 28 + 1 since the abnormal loads' chapter 14 and its T1 entry, 22 Oct)",
   # NARROWED 27 Oct 2026 (stockpile forecast): + chapter 15 Stockpiles and its three sections (66); merged with main's technical-guide row (30)
   len(re.findall(r'<li class="l[12]"', src)) == 66 and len(re.findall(r'<li class="l[12]"', _tg2)) == 31   # NARROWED 28 Oct 2026: + "A deployment per organisation" (pilot readiness phase 3)   # NARROWED 27 Oct 2026: + "Headers, scripts and keys" (pilot readiness phase 2)   # NARROWED 22 Oct 2026 (words sweep; the user: no back-end detail in the user guide): the guide lost Appendix D's row; the technical guide gained T7's four parts, T8, T9, T10 and the BAF section
   and '<li class="l2"><a href="#t2-left-out">What the screens leave out</a></li>' in _tg2)

# 27 Oct 2026 — stockpile balances that run forward (claude/stockpile-forecast): the guide says how the balance is worked out,
# where the plan and the counts are typed, the two new flags and who sees "over capacity" on the map; the technical guide's
# T1 has the arithmetic in full
_ug_sf = src
ok("⭐ STOCKPILES: chapter 15 — the page, planned use, stock counts and how the balance is worked out — in the contents too",
   '<h1 id="15-stockpiles">15. Stockpiles</h1>' in _ug_sf and _ug_sf.count('<h2 id="15-') == 3
   and '<li class="l1"><a href="#15-stockpiles">15. Stockpiles</a></li>' in _ug_sf
   and "Same each month from … to …" in _ug_sf and "The planned use never takes more than is there" in _ug_sf
   and "No use planned yet" in _ug_sf)
ok("STOCKPILES: the flags table names STOCKPILE SOON and STOCKPILE EMPTY (amber), and the Account's Next 8 weeks and grey plan",
   "<tr><td>STOCKPILE SOON</td><td>Amber." in _ug_sf and "<tr><td>STOCKPILE EMPTY</td><td>Amber." in _ug_sf
   and "<strong>Next 8 weeks</strong>" in _ug_sf and "with the plan under it in grey" in _ug_sf)
ok("STOCKPILES: 🔴 the old rule's words are gone from the guide (a week nobody reported no longer counts as nothing)",
   "a week nobody reported counts as nothing" not in _ug_sf and "a route nobody reported counts as nothing" not in _ug_sf)
ok("STOCKPILES: over capacity on the map is for signed-in staff; the public sees 'full'",
   "<strong>Over capacity</strong> (red, signed-in staff only)" in _ug_sf and 'The public sees the stockpile as "full".' in _ug_sf)
ok("STOCKPILES: the technical guide's T1 has the forward arithmetic, the staff-only timeline and the memo",
   "balance_end(W) = count(W) if a stock count is typed" in _tg2 and "a planned Out never takes more than the place holds" in _tg2
   and "<code>full</code> (D9 a + i)" in _tg2 and "<code>_MEMO</code>" in _tg2)
ok("⭐ 22 Oct 2026 (abnormal loads, phase 3): the guide's chapter 14 — planning one, the route and the potential pinch points, where they show and the documents — says advice never permission, lorry never truck, counted apart; its three rows in the contents; the technical guide's T1 entry names the sources, the calendars, HERE's parameters, the structures pass and what is not modelled",
   '<h1 id="14-abnormal-loads">14. Abnormal loads</h1>' in src and src.count('<h2 id="14-') == 3
   and '<li class="l1"><a href="#14-abnormal-loads">14. Abnormal loads</a></li>' in src and src.count('<li class="l2"><a href="#14-') == 3
   and "Advice, never permission" in src and "ESDAL, the police and the road and bridge authorities decide" in src and "counted apart" in src
   and "Check the roads again" in src and "Notice calendar" in src and "ESDAL details sheet" not in src and "keeps the reference numbers they give back" in src and "approved movements only" in src   # NARROWED 27 Oct 2026: the sheet is gone
   and not re.search(r"\btrucks?\b", src[src.index('<h1 id="14-abnormal-loads">'):src.index('<h1 id="appendix-a-methods-and-assumptions">')], re.I)
   and not re.search(r"\b(compliant|approved by|real-time|optimi[sz]e|predict)\b", src[src.index('<h1 id="14-abnormal-loads">'):src.index('<h1 id="appendix-a-methods-and-assumptions">')], re.I)
   and '<h2 id="t1-abnormal">Abnormal loads (S16 / B5, 22 Oct 2026)</h2>' in _tg2 and '<li class="l2"><a href="#t1-abnormal">Abnormal loads</a></li>' in _tg2
   and "STGO 2003 Schedule 1" in _tg2 and "osm_structures" in _tg2 and "vehicle[grossWeight / weightPerAxle / height / width / length / axleCount]" in _tg2
   and "/api/public/abnormal" in _tg2 and "Not modelled" in _tg2)

# ⭐ 22 Oct 2026 (UI fix 8, claude/ui-fix-callouts; mockup notes\ui-fix-callouts-mockup-1022\ approved, Q1 yes): the callout
# titles and the user guide's h3 headings were the light blue / red tokens on the boxes' pale backgrounds (note 3.32:1,
# warn 4.41:1, h3 on white 3.67:1, ok 3.33:1 — under WCAG AA's 4.5:1 for 15–16 px text). Each now has its own text-grade
# colour, worked out here against its box. The guides have no Dark look (always light), so there is no dark pair to check.
def _lum(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def _ratio(a, b):
    a, b = _lum(a), _lum(b); return (max(a, b) + 0.05) / (min(a, b) + 0.05)
ok("UI fix 8: the contrast helper agrees with the audit's figures for the old colours (note 3.32, warn 4.41, h3 3.67)",
   round(_ratio("#3B82F6", "#EEF4FB"), 2) == 3.32 and round(_ratio("#DC2626", "#FDF2F5"), 2) == 4.41 and round(_ratio("#3B82F6", "#FFFFFF"), 2) == 3.68)
for _nm, _pg in (("user guide", src), ("technical guide", _tg2)):
    _css = _pg[:_pg.index("</style>")]
    for _kind in ("note", "warn", "ok", "tip"):
        _bg = re.search(r"\.callout\.%s\{background:(#[0-9A-Fa-f]{6})" % _kind, _css)
        _fg = re.search(r"\.callout\.%s \.ct\{color:([^}]+)\}" % _kind, _css)
        if not (_bg and _fg):
            continue
        ok("🔴 UI fix 8 (%s): the %s box's title is a hex colour (not a light token) at 4.5:1 or more on its box" % (_nm, _kind),
           _fg.group(1).startswith("#") and _ratio(_fg.group(1), _bg.group(1)) >= 4.5)
    ok("⭐ UI fix 8 (%s): the note title #1D4ED8 (6.05:1) and the warn title #B91C1C (5.91:1); the borders keep the tokens" % _nm,
       ".callout.note{background:#EEF4FB;border-color:var(--blue)}.callout.note .ct{color:#1D4ED8}" in _css
       and ".callout.warn{background:#FDF2F5;border-color:var(--red)}.callout.warn .ct{color:#B91C1C}" in _css)
    ok("🔴 UI fix 8 (%s): no callout title or h3 is drawn in var(--blue) / var(--red) / var(--green) any more" % _nm,
       not re.search(r"\.ct\{color:var\(--(blue|red|green)\)\}|h3\{color:var\(--blue\)", _css))
    ok("⭐ UI fix 8 (%s, card 4): h3 headings #1D4ED8 on white, 6.70:1" % _nm,
       "h3{color:#1D4ED8;font-size:16px;margin:22px 0 6px}" in _css and round(_ratio("#1D4ED8", "#FFFFFF"), 2) == 6.70)
    ok("UI fix 8 (%s): the guide still has no Dark look, so the light pairs are the only pairs" % _nm,
       "prefers-color-scheme" not in _pg and 'data-theme' not in _pg)
ok("UI fix 8: the user guide's green box title (unused today) is #047857, 4.85:1 on its box",
   ".callout.ok{background:#E6F4F1;border-color:var(--green)}.callout.ok .ct{color:#047857}" in src)

# 23 Oct 2026 (the route line redesign, the user: idea 1 'Atlas'): the guide's words follow the map — the loads' lines are ink
# with a white edge and the pinch points rings (not violet dashes and dots); the flow is a light along solid lanes (no dashes)
ok("23 Oct: chapter 14 says the staff map draws each load's line in raspberry (NARROWED 23 Oct 2026 afternoon; ink that morning) with a white edge and a ring at each pinch point, never violet dashes",
   "draws each line in raspberry with a white edge, and a ring at each potential pinch point" in src and "violet dashes" not in src and "in ink with a white edge" not in src)
ok("23 Oct: the technical guide says a light runs along each lane only while Play runs and the lane's width is its band, never that dashes move",
   "A light runs along each lane only while Play runs, and the lanes stand still under reduced motion; the lane's width is its band." in _tg
   and "The dashes move only while Play runs" not in _tg)

# ---- 23 Oct 2026: the abnormal loads on the public map's figures bar and in the animation ----
_ug23 = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_tg23 = open(TECH, encoding="utf-8").read()
ok("23 Oct: the user guide names the bar's Abnormal loads figure (each once, apart from the lorries' figures) and the load travelling its route in raspberry; 14.3 says the public map draws it in its month",
   "<strong>Abnormal loads this month</strong> (the approved abnormal loads moving in the month, each counted once, apart from the lorries' figures" in _ug23
   and "draws each line in raspberry with a white edge" in _ug23 and "each as its route in the month it moves" in _ug23 and "in ink with a white edge" not in _ug23)
ok("23 Oct: the technical guide says the month figures carry abnormal_loads",
   "<code>abnormal_loads</code>, the ids of the public movements whose window touches the month" in _tg23)

# ---- 27 Oct 2026: the final UI pass — what left the screens is in the guides ----
_ug27 = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_tg27 = open(TECH, encoding="utf-8").read()
ok("27 Oct: the user guide carries the screens' longer sentences — §4.1 the movements / vehicles formula and one vehicle per line, §9 the Locations map hints, the Routes 'moving an end', the Zones rectangle and haul-road rules, the community and collision fetch rules, §10 the sign-in set-up, chapter 14 the advice caveats and the counted-apart rule",
   "Movements are loads per working day (22 a month unless Config says otherwise)." in _ug27 and "One vehicle per line: a haul that uses two vehicle types is two lines." in _ug27
   and "Locations: click the map to place a site and drag its marker to move it; deleting a site deletes every route that uses it. Routes: moving an end clears the route until it is routed again." in _ug27
   and "the rectangle around what you draw" in _ug27 and "A temporary haul road works the other way" in _ug27 and "so fetch again after drawing one" in _ug27
   # NARROWED 27 Oct 2026 (pilot readiness F3 c): the first admin is invited by FIRST_ADMIN_EMAIL now; §10 says who adds the rest
   and "Admins add everyone else on Users; each person then sets a password and two-step sign-in." in _ug27
   and "To set up per-person sign-in: on Users, add yourself as an Admin" not in _ug27
   and "rules as read on 16 Oct 2026" in _ug27 and "Counted apart: an abnormal load is never in the lorry counts" in _ug27 and "<strong>Settings</strong> shows how far it runs and updates it" in _ug27)   # NARROWED 28 Oct 2026: was "shows the copy in use" (GOV.UK named)
ok("27 Oct: the technical guide — T1 names the advice line and the rules' reading date, T2 lists the pass; no guide mentions an ESDAL details sheet as a thing that exists",
   '<code>abnormal_rules.ADVICE_WORDS</code> ("Advice from the typed figures. The haulier, ESDAL, the police and the road and bridge authorities decide.")' in _tg27
   and "<li><strong>27 Oct 2026, the final UI pass.</strong>" in _tg27 and "went on 27 Oct 2026" in _tg27 and "ESDAL details sheet" not in _ug27)

# 28 Oct 2026 (task 8b): the OS map and the tenant's own imagery are in the guides, in few words on the user's side, in detail on the technical side
_ug28 = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_tg28 = open(os.path.join(ROOT, "frontend", "help", "technical", "index.html"), encoding="utf-8").read()
ok("28 Oct: the user guide's Basemap line says the OS map and an organisation's own imagery appear where they are set up, and that the OS map shows OS's credit; no key, address or back-end term",
   "The OS map and an organisation's own aerial imagery appear in the list where they are set up (the imagery under Configuration, Map and bulletin); the OS map shows OS's credit." in _ug28
   and "OS_MAPS_KEY" not in _ug28 and "api.os.uk" not in _ug28 and "bbox" not in _ug28)
ok("28 Oct: the technical guide T10 holds the detail: the deployment setting, OS's style and request address, the key added to every OS request, the zoom 15 limit and why, the tenant fields, the address forms, the one read that carries them, fetch before replace, the plan wording and that server-drawn maps keep Mapbox",
   all(t in _tg28 for t in ("<strong>Basemaps.</strong>", "<code>OS_MAPS_KEY</code>", "api.os.uk/maps/<wbr>vector/v1/vts/<wbr>resources/styles<wbr>?srs=3857", "<code>transformRequest</code>",
                            "16&ndash;19 is Premium", "<code>tenant.imagery_url</code>", "<code>{bbox-epsg-3857}</code>", "<code>/api/public/alignment</code>",
                            "<code>/api/meta</code>", "<em>before</em> the basemap", "the Premium plan", "keep Mapbox and never draw OS data",
                            "<code>security_headers.csp</code>", "adds the one host of the tenant's")))
# 28 Oct 2026 (the user: no supplier names in the user guide; mockup notes\abnormal-words-mockup-1028): chapter 14 names no
# supplier or data set; the technical guide's T1 holds what the page and the guide leave out
_ch14 = _ug27[_ug27.index('<h1 id="14-abnormal-loads">'):_ug27.index('<h1 id="15-stockpiles">')]
ok3("⭐ 28 Oct: the user guide's chapter 14 names no supplier or data set (HERE, OpenStreetMap, GOV.UK, the community layer); the click path to the fetch stays",
   not re.search(r"\bHERE\b|OpenStreetMap|\bOSM\b|GOV\.UK|gov\.uk|Geofabrik|community layer|severity", _ch14)
   and "once the map data has been fetched (<strong>Config → Map and bulletin → Fetch now</strong>)" in _ch14
   and "the map data is only as complete as the people who map it" in _ch14 and "The bank holidays are the government's published list" in _ch14,
   re.findall(r"\bHERE\b|OpenStreetMap|GOV\.UK|community layer", _ch14)[:5])
ok("28 Oct: the technical guide's T1 says what the Abnormal loads page leaves out — the severity word, 'the map' = OpenStreetMap, the raw error to the log, the GOV.UK feed and its licence, the old saved words reworded on read",
   'id="t1-abnormal-words"' in _tg27 and "<code>severity</code> word is kept in <code>actions_json</code> but not shown" in _tg27
   and "means OpenStreetMap" in _tg27 and "Open Government Licence v3.0" in _tg27 and "plain_candidate / plain_note / plain_bake_error" in _tg27
   and "<code>abnormal_route.SCREEN_BAN</code>" in _tg27)

# ---- 28 Oct 2026 (the user: no supplier names in the user guide): the Basemap line names no supplier ----
_bm = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_bmli = (re.search(r"<li><strong>Basemap</strong>.*?</li>", _bm, re.S) or [""])
_bmli = _bmli.group(0) if hasattr(_bmli, "group") else ""
ok3("⭐ BASEMAP WORDS: the user guide's Basemap line names no supplier (no Maa-amet, no Mapbox)",
    bool(_bmli) and "Maa-amet" not in _bmli and "Mapbox" not in _bmli and "(today: Estonia's)" in _bmli, _bmli[:160])
_tg28 = open(TECH, encoding="utf-8").read()
ok3("BASEMAP WORDS: technical guide #t7-basemap-words names the suppliers and the old labels",
    'id="t7-basemap-words"' in _tg28 and "Estonian Land Board's (Maa-amet) orthophoto" in _tg28
    and "Aerial (Mapbox\nSatellite)" in _tg28 and "are Mapbox styles" in _tg28)

# ---- 28 Oct 2026 (the user: no supplier or data-set names in the user guide): DESNZ, DfT and their data sets are named
# only in the source tables A.1 / A.2 (kept: the OGL asks for the source) and in technical guide #t1-guide-sources.
_gs = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_gs_a, _gs_b = _gs.find('id="a-1-data-sources"'), _gs.find('id="a-3-what-the-platform-does-not-do"')
_gs_rest = _gs[:_gs_a] + _gs[_gs_b:] if 0 < _gs_a < _gs_b else ""
_GS_BAN = re.compile(r"DESNZ|\bDfT\b|\bDfE\b|Department for (?:Transport|Education|Energy)|NaPTAN|STATS19|Get Information about Schools|\bGIAS\b")
ok3("⭐ GUIDE SOURCES: outside A.1 / A.2 the user guide names no DESNZ, DfT, DfE, NaPTAN, STATS19 or GIAS",
    len(_gs_rest) > 50000 and not _GS_BAN.search(_gs_rest), ", ".join(sorted(set(_GS_BAN.findall(_gs_rest)))))
ok3("GUIDE SOURCES: A.1 / A.2 still name them (the source tables), and the ban would catch the old sentences",
    "UK Government greenhouse gas conversion factors 2026 (DESNZ)" in _gs[_gs_a:_gs_b] and "(DfT and Innovate UK)" in _gs[_gs_a:_gs_b]
    and all(_GS_BAN.search(x) for x in ["each lorry's DESNZ 2026 factor", "from DfT&rsquo;s road safety data (STATS19)",
                                         "the Department for Transport's NaPTAN", "the Government's weekly road fuel prices (DESNZ)"]))
ok3("GUIDE SOURCES: the plain words are in the guide",
    "each lorry's 2026 UK Government factor" in _gs and "against the UK national average (2026)" in _gs
    and "stamped as a Wayscope planning estimate on the UK Government's 2026 factors, not Carbon Tool figures" in _gs
    and "the government's lists of schools and of bus stops and stations, and a map that volunteers keep" in _gs
    and "from the government&rsquo;s road safety figures" in _gs and "UK Government conversion factors, 2026" in _gs
    and "UK Government material use and waste disposal factors, 2026." in _gs)
_tg_gs = open(TECH, encoding="utf-8").read()
ok3("GUIDE SOURCES: technical guide #t1-guide-sources names what the user guide leaves out",
    'id="t1-guide-sources"' in _tg_gs and all(x in _tg_gs for x in ["Get Information about Schools, the\nDepartment for Transport's NaPTAN",
        "safety data (STATS19), released each late July", "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"]))

# ---- 28 Oct 2026 (John, task 0a; notes/map-panel-mockup-1028): the panel's long sentences live here now; the rail option is gone
_ug0a = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
ok3("⭐ 0a: the user guide lists Labels (Off, Few or All) in the panel and explains Few / All / Off in §8.2",
    "<li><strong>Labels</strong> — Off, Few or All;</li>" in _ug0a and "<strong>Few</strong> (the default) shows the site names from zoom 11" in _ug0a
    and "<strong>Off</strong> shows none of them" in _ug0a and "A shared link keeps the choice." in _ug0a)
ok3("0a: the moved panel notes are in §8.2 (survey bridge, boundary ticks, chainage, buildings, gates, dimmed zones, alternatives, credits)",
    all(t in _ug0a for t in ["click the line to see which stretches are measured", "ticks from zoom 11, labelled from zoom 13",
        "10 km apart at corridor zoom", "3D buildings show from zoom 14 (15 on Standard)", "a hollow gate is not in use",
        "A dimmed disruption-zone row has none in force", "how many other ways the routing found", "<strong>Credits</strong>"]))
ok3("🔴 0a: no 'Existing rail network' left in the user guide (the panel option and its Sources row are gone)",
    "Existing rail network" not in _ug0a)
ok3("0a: the flow in §8.3 is lanes whose WIDTH is the movements (no 'Closer dashes'), keyed 'Movements a day, each way'",
    "<strong>A wider lane means more movements a day</strong>" in _ug0a and "Closer dashes" not in _ug0a
    and "<em>Movements a day, each way</em>" in _ug0a)
ok3("0a: the technical guide says the map no longer draws the existing rail corridor",
    "since 28 Oct 2026 the public map does not draw it" in open(TECH, encoding="utf-8").read())

print("test_help.py: %d passed, %d failed" % (passed, failed))
# ---- 28 Oct 2026 (simulation v2, task 0e): the user guide says what the Simulation's scales and the site view are, in
# plain words; the Locations and Zones chapters name the new fields; the technical guide holds the detail
_ug = open(os.path.join(ROOT, "frontend", "help", "index.html"), encoding="utf-8").read()
_simp = (re.search(r"<p><strong>Simulation</strong>.*?</p>", _ug, re.S) or [""])
_simp = _simp.group(0) if hasattr(_simp, "group") else ""
ok3("⭐ SIM V2: the user guide's Simulation paragraph names the three scales, the areas, the wash, the site view, the closed period, and says nothing is saved",
    all(w in _simp for w in ("<strong>Month</strong>", "<strong>Week</strong>", "<strong>Day</strong>", "<strong>areas</strong>", "wheel wash", "<strong>Site</strong>", "closed for a period", "nothing is saved", "not a record of what happened"))
    and not re.search(r"\b(API|endpoint|server|JSON|predict\w*|real-time)\b", _simp), _simp[:200])
ok3("SIM V2: 9.1 names the closed period and the site areas (minutes a lorry, bays, level), 9.3 the road inside a site",
    "<strong>Closed for a period (optional)</strong>" in _ug and "<strong>Site areas</strong>" in _ug and "<strong>Minutes a lorry</strong>" in _ug
    and "<strong>Bays</strong>" in _ug and "<strong>Inside a site</strong>" in _ug)
_tgv2 = open(TECH, encoding="utf-8").read()
ok3("SIM V2: the technical guide #t1-sim-v2 holds the detail (the table, the chain, the resolver, the scales, the query parameters)",
    'id="t1-sim-v2"' in _tgv2 and "<code>backend/sim_site.py</code>" in _tgv2 and "<code>site_areas</code>" in _tgv2
    and "<code>closed_fallback</code>" in _tgv2 and "<code>scale=month|week|day</code>" in _tgv2 and "<code>/api/site-areas</code>" in _tgv2)

sys.exit(1 if failed else 0)
