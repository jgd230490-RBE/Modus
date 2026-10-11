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
import sys
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "backend", "main.py")
HELP = os.path.join(ROOT, "frontend", "help", "index.html")
MEDIA = os.path.join(ROOT, "frontend", "help", "media")

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
ok("\U0001f534 the technical appendix is ADMIN ONLY, and so is every heading inside it",
   len(re.findall(r'data-role="admin"', src)) >= 5
   and 'id="appendix-d-technical-reference" data-role="admin"' in src)
ok("...and it is honest that it is a summary of the full technical guide, not a replacement",
   "not the full technical guide" in src)
# NARROWED 9 Oct 2026: the one 'Unaudited' row (emission factors) was checked against gov.uk that
# day, so the distinction is now measured / planning assumption / checked-and-dated.
ok("...it keeps the sourcing distinction: what is measured vs assumed vs checked",
   "Planning assumption" in src and "Measured" in src and "Checked 9 Oct 2026" in src)
ok("\U0001f534 ...and it repeats that the deployment must not be called secure",
   "Do not describe the deployment as secure" in src)
ok("...and names what leaves the platform to third parties",
   "What leaves the platform" in src and "No quantity, rate or forecast leaves" in src)

# troubleshooting
ok("the troubleshooting picker has a mount point and is built by the script",
   'id="tsq"' in src and 'id="tsa"' in src)
ok("\u2b50 ...and at least ten symptoms, each with a verdict on whether it is a fault",
   len(re.findall(r'"(fine|fault)"', src)) >= 10)
ok("...it leads with the one that caught us: an empty map is usually no month selected",
   "No month on screen" in src)
ok("...and it covers the unbaked route, the missing rate and the low carbon figure",
   "has not been baked" in src and "rate not set" in src and "Only baked routes contribute" in src)

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
ok("\U0001f534 ...and correcting that sentence did NOT take the Control Panel description "
   "with it", "Control Panel" in src and "Route filtering, Basemap, Overlays" in src
   and "the \u2630 button opens it" in src)

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
   "a planner or admin records them as the scheme's carbon target" in src and "No admin token is needed." in src
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
ok("...a team code: the scheme's target, not split by team, its own figures with no verdict",
   "not split by team" in text and "with no verdict" in text)
ok("🔴 setting the carbon target and the money settings are gated to planner and above, like the Data pages",
   '"6-4-for-planners-setting-the-carbon-target": "planner"' in src and '"9-5-money-settings": "planner"' in src
   and 'id="6-4-for-planners-setting-the-carbon-target"' in src and 'id="9-5-money-settings"' in src)

# getting started: sign-in, the menu, the header, the demo bar and the tour
ok("⭐ sign-in as it is: Staff sign in, Your name, Access code, the eye, Back to the map; spaces are ignored",
   all(s in src for s in ("<strong>Staff sign in</strong>", "<strong>Your name</strong>", "<strong>Access code</strong>",
                           "The eye at the end of the code box", "<strong>Back to the map</strong>",
                           "Spaces before or after it are ignored")))
ok("🔴 ...and no longer blames a trailing space or says planners rotate the codes in the app",
   "trailing space" not in text and "rotated by the planners" not in text and "codes are rotated" not in text)
ok("...the staff sign-in keeps the map and the guide open for 12 hours, past Sign out (gate.STAFF_TTL_S)",
   "for 12 hours" in text and "does not close them" in text)
ok("the menu as it is: four groups with the Carbon planner under PLAN, Find a page, Ctrl K, User guide, Collapse",
   "<strong>PLAN</strong> (Dashboard, Submit forecast, Forecasts, Carbon planner)" in src
   and "Find a page…" in src and "Ctrl K" in src and "<strong>User guide</strong>" in src and "‹ Collapse" in src)
ok("...the header: vehicle names by country, the Appearance looks Ink, Light and Dark",
   "<strong>Appearance</strong>" in src and all(s in src for s in ("<strong>Ink</strong>", "<strong>Light</strong>", "<strong>Dark</strong>"))
   and "everywhere except Great Britain" in src)
ok("⭐ the demo bar and its Guide button, the New here? box, the dots, Don't show again; nothing opens by itself",
   "FICTIONAL DEMO SCHEME · NOTHING HERE IS REAL" in src and "<strong>Guide</strong>, at the right-hand end of the bar" in src
   and "Nothing opens by itself." in src and "<strong>Take the tour</strong>" in src and "pulsing orange dots" in src
   and "<strong>Don't show again</strong>" in src and "Your organisation's own site has no bar and no tour." in src)

# the Dashboard after the UI pass
ok("the Dashboard: the six cards by name, More filters, the four charts, the folded sections, Big screen",
   all(s in src for s in ("Material in view", "Deliveries a day", "Vehicles needed", "Planned this week",
                           "Delivered against plan", "Transport carbon", "More filters ▾", "Cost over time",
                           "This week and today, with the Look-ahead's map", "Route planning detail",
                           "<strong>Big screen</strong>", "#dashboard/1", "tCO2e target, all-in", "All four", "Rotate", "One section")))
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
ok("...the grid's Flags, Week and Status columns, ▶ to expand, ✎ for a typed day; the exports' Fuel sheet and the DRAFT stamp",
   "The <strong>Flags</strong> column" in src and "<strong>Week</strong> is the line's total" in src
   and "Press <strong>▶</strong> at the left of a row" in src and "The day shows ✎" in src
   and "<strong>Fuel</strong> sheet" in src and "DRAFT — not confirmed" in src and "Click a row</strong> to see" not in src)
ok("...Account's columns and the diesel strip: Planned £, Fair £ (model), Actual £, £ var, Yard £/L, Fuel share %",
   all(s in src for s in ("<strong>Planned £</strong>", "<strong>Fair £ (model)</strong>", "<strong>Actual £</strong>",
                           "<strong>£ var</strong>", "<strong>Yard £/L</strong>", "<strong>Fuel share %</strong>")))
ok("...the first confirm locks the fuel-surcharge base, and a team code confirms its own lines (costing.lock_baf_base_if_empty)",
   "locks the base for the fuel surcharge (BAF)" in text and "Confirm week confirms your team's lines only" in text)

# the public map after PRs #20-#29
ok("⭐ the map: Layers and basemap, What's moving, Busiest routes, the figures bar's names, Conditions",
   all(s in src for s in ("<strong>Layers and basemap</strong>", "<strong>What's moving</strong>", "<strong>Busiest routes</strong>",
                           "<strong>Two-way movements a day</strong>", "<strong>CO₂e a day</strong>", "<strong>CO₂e to date</strong>",
                           "<strong>Conditions in [month]</strong>", "<strong>Show on map</strong>")))
ok("🔴 ...the retired map parts are gone: the KPI panel, the callouts, the warning stack's levels, the Street View button, the legend message",
   "KPI panel" not in text and "callouts" not in text and "<strong>Clash</strong>" not in src and "<strong>Caution</strong>" not in src
   and "press <strong>Street View</strong>" not in src and "no alignment in this tenant" not in text
   and "Use this option" not in text)
ok("...Play: the timeline runs every month whatever the From and To months; Conditions only while it is open",
   "whatever the From and To months say" in text and "While the timeline is open (playing or paused)" in text)
ok("🔴 ...and it is honest that a planned closure is listed in every month its route carries volume, whatever its dates",
   "whatever the closure's own dates" in text and "the Look-ahead counts it only in the weeks it overlaps" in text)
ok("...the map's route analysis panel is a rough cycle at the average haul speed, not the routed drive time",
   "not the routed drive time" in text)
ok("...the restriction popup gives no verdict against the vehicle: that is the route check",
   "is judged in the route check, not in this popup" in text and "EXCEEDS by" not in text)

# Data pages and settings
ok("Data pages: the token box at the top right, More ▾ on Configuration; Make primary; Create & route; Clear all routes",
   "<strong>Admin token</strong> box" in src and "under <strong>More ▾</strong>" in src and "<strong>Make primary</strong>" in src
   and "<strong>Create &amp; route</strong>" in src and "<strong>Clear all routes</strong>" in src
   and "its forecast lines are not deleted with it" in text)
ok("...a route with no rate is priced at the target rate and marked target; rate not set only when neither exists",
   "only when neither exists does it read \"rate not set\"" in text and "Nothing is pre-filled; a route reads" not in text)
ok("🔴 Configuration: six sections with Costing · fuel, and Reset to file is not an undo (it resets the organisation's settings and the demo notice)",
   "<strong>Costing · fuel</strong>" in src and "Reset to file is not an undo" in src
   and "the demo notice" in text and "on five tabs" not in text)
ok("⭐ money settings: the target rate, the fuel surcharge formula and its locked base, the fair price as a floor, never a quote",
   "<strong>Target rate</strong>" in src and "(index ÷ base − 1) × fuel share" in text
   and "a floor for negotiation, never a quote" in text)

# roles: the planner and admin codes open the same pages; the admin token is not a role
ok("⭐ roles moved to section 10: the admin code opens what the planner code opens; the admin token is a separate key",
   '<h1 id="10-roles-who-can-do-what">10. Roles: who can do what</h1>' in src
   and "exactly what the planner code opens" in text and "The admin token is not the admin code." in text
   and "plus the admin token for baking routes" not in text)

# carbon factors and sources
ok("🔴 the 7.5 t rigid carries its 2026 factor (0.49944, factors.json) and the Carbon Tool method IS shown now, for comparison",
   "0.49944" in text and "a 2025 figure" not in text and "still carries a 2025 figure" not in text
   and "is not reproduced here" not in text and "for comparison only" in text)
ok("...the carbon sources are named, with no web address (DESNZ 2026, the Carbon Tool v2.7, ZEHID, Net Zero Highways)",
   "UK Government greenhouse gas conversion factors 2026 (DESNZ)" in text and "National Highways Carbon Tool v2.7" in text
   and "ZEHID annual report 2026" in text and "Net Zero Highways annual progress report 2025-26" in text)
ok("...transport CO2e and all-in carbon are told apart in What the figures mean",
   "<td>Transport CO₂e</td>" in src and "<td>All-in carbon (tCO2e)</td>" in src)

# house style the old guide broke
ok("🔴 house style: no real-time, telematics or 'security phase' in the guide (the one 'secure' is D.4's)",
   not re.search(r"real-time|telematics|security phase", text, re.I)
   and len(re.findall(r"\bsecure\b", text, re.I)) == 1)

# troubleshooting: the carbon symptoms
ok("⭐ the picker covers the carbon symptoms people will hit (all-in vs transport, over as forecast, team, greyed Set, decisions gone, Carbon Tool)",
   all(s in src for s in ("The Carbon planner's carbon is much bigger than the Dashboard's",
                           "The carbon target says “over the target” as forecast",
                           "My team's carbon figures are not compared with the target",
                           "“Set as the scheme's carbon target” is greyed out",
                           "The carbon target says the agreed decisions no longer fit the plan",
                           "Our carbon does not match the National Highways Carbon Tool")))

# REVERSED 11 Oct 2026: the 9 Oct TARK TEE row said an unreachable or never-run check raises the flag; clashes.py
# raises no RESTRICTION flag then (sources.restrictions is "unavailable" and the line under the rail says NOT checked)
ok("🔴 the restriction flags are raised by a hit only; an unchecked route raises none and the rail line says NOT checked",
   "or the check is unavailable or has never run" not in text and text.count("A route never checked raises no flag") == 2
   and "<td>ROADWORKS</td>" in src and "<td>TARK TEE</td>" in src)

# the /help/ sign-in page names the rail's link as it reads
ok("the guide's own sign-in page names the rail link as it reads (User guide), not 'Help link'",
   "User guide at the foot of the app's menu on the left." in main_src and "Help link in the app" not in main_src)

print("test_help.py: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
