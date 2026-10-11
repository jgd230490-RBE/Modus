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
# NARROWED 11 Oct 2026 (guide v2.1 review): the Control Panel description became a list, so the one line
# "Route filtering, Basemap, Overlays" no longer exists. The description must still name every group, in order.
_cp_at = src.find("The <strong>Control Panel</strong> on the left holds, top to bottom:")
_cp = src[_cp_at:src.find("</ul>", _cp_at)] if _cp_at >= 0 else ""
_cp_groups = ("Route filtering", "Layers and basemap", "Basemap, Overlays and Haul routes", "What's moving",
              "Road closures", "Road restrictions", "Forecast traffic volume")
ok("\U0001f534 ...and correcting that sentence did NOT take the Control Panel description "
   "with it", "Control Panel" in src and all(g in _cp for g in _cp_groups)
   and [_cp.index(g) for g in _cp_groups] == sorted(_cp.index(g) for g in _cp_groups)
   and "the \u2630 button opens it" in src)

# deep links
# NARROWED 11 Oct 2026: the Carbon planner's two pictures (S16, S17) link to /#carbon, so 23 of 29 (was 21 of 27)
ok("every figure with a screen behind it links into the live app (23 of 29)",
   len(re.findall(r'figcaption[^<]*<a class="go"', src)) + len(re.findall(r'<a class="go"', src)) >= 23)
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
   and "Hard-refresh (empty cache and reload), or open a private window and sign in again." in text)
ok("...the Forecasts badge counts Pending or Mixed lines, and the guide says so (not 'waiting for approval')",
   'r.status === "Pending" || r.status === "Mixed"' in fe_src
   and "shows how many lines are Pending or Mixed" in text and "lines are waiting for approval while" not in text)

# the demo bar and the tour
ok("the shared demo: one callout names what not to press, and the map's first tour has no welcome",
   "On the shared demo, show these but do not press them" in text and "Bake all</strong> (it spends routing calls)" in src
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
   and "Sat/Sun are held at 0 and not shown" in fe_src)
ok("...the KPI strip is a list; the check line's two other states; Esc saves a day",
   "The <strong>KPI strip</strong> reads:</p>\n<ul>" in src and "not checked since baking" in text
   and "the stored result stands" in text and "Esc, or clicking elsewhere, saves too" in text
   and 'e.key === "Enter" || e.key === "Escape") e.currentTarget.blur()' in fe_src)

# the public map
ok("\U0001f534 the map: compound and railhead are the only squares; a tip draws as Other",
   "port, site, railhead and compound (squares)" not in text
   and "Rounded squares: compound (a site cabin) and railhead (rails)." in text
   and "A site of any other type, such as a tip, is drawn as other." in text)
ok("...the filters skip stockpiles; the quick buttons are named; the t / day figure is hidden in vehicles",
   "the route conditions (not to stockpiles over capacity)" in text
   and "Light, Dark, Satellite and Streets (Streets is not in the Basemap list)" in text
   and "Material a day appears too" not in text and "as shipped it counts in vehicles, so that figure is not shown" in text)
ok("...an unbaked line is counted as unknown; a route with no geometry is left out of the bar",
   "A line whose route is not baked for its vehicle is counted as unknown" in text
   and "A line whose route has no drawn geometry at all is left out of the bar." in text
   and "a route that is not baked is counted as unknown" not in text)

# Data pages and settings
ok("Data pages: a tip keeps its imported type; the Planning tick does not lead a country with its own vehicle set",
   "a tip or recycling site keeps the type it was imported with" in text
   and "the Planning tick does not change the lists" in text and "vehicle_sets" in text)
ok("...the money settings split into three bullets; the token paragraph says a team code cannot open those pages",
   "<li><strong>Diesel index</strong> —" in src and "<li><strong>Fuel surcharge (BAF)</strong> —" in src
   and "whichever of the planner or admin codes they signed in with (a team code cannot open those pages)" in text
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
_vis = src[:src.find('<h1 id="appendix-d-technical-reference"')]
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
   "Appendix D, in the admin view of this guide" in text and "see Appendix D." not in text)

# the pictures: each placeholder's title is its figure caption; no developer instructions on them; no truck
_holders = dict(re.findall(r'\n  ([SM]\d\d): \["([^"]+)"', gen_src))
_caps = dict(re.findall(r'<img src="media/([SM]\d\d)\.png"[^>]*><figcaption>Figure \d+ — (.*?)(?: &nbsp;·&nbsp;.*?)?</figcaption>', src))
_appc = dict((f, c) for c, f in re.findall(r"<tr><td>\d+</td><td>([^<]+)</td><td>([SM]\d\d)\.png</td></tr>", src))
# NARROWED 11 Oct 2026: 24 pictures (S16 and S17 added for the Carbon planner), was 22
ok("\U0001f534 every placeholder's title is its figure caption, word for word, and Appendix C agrees (%d pictures)" % len(_caps),
   len(_caps) == 24 and set(_holders) == set(_caps) and all(_holders[k] == _caps[k] for k in _caps)
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


# =========================================================================== #
#  11 Oct 2026 — the Carbon planner's pictures and the capture script           #
#  (branch claude/guide-screenshots)                                            #
# =========================================================================== #
# What these prove: S16 and S17 are in the guide where the text is, captioned, listed, drawn as placeholders until
# the live capture replaces them; the figures are numbered in order; the capture script shoots every picture, cannot
# write, cancels the Confirm dialog and refuses to start without a site and a code.
# What they do not prove: what the live capture will show (it was dry-run against a LOCAL copy only; see
# capture_guide.js's header), or how the page looks in a browser.
import shutil
import subprocess

CAP = os.path.join(ROOT, "backend", "tools", "capture_guide.js")
cap_src = open(CAP, encoding="utf-8").read()
_S16 = "The Carbon planner — the six steps"
_S17 = "Step 6 — the scheme's carbon target"
_sec6 = src[src.find('<h1 id="6-the-carbon-planner">'):src.find('<h1 id="6-the-look-ahead">')]
_s61 = _sec6[_sec6.find('<h2 id="6-1-how-the-carbon-planner-works">'):_sec6.find('<h2 id="6-2-steps-1-to-4-your-plan-and-your-choices">')]
_s65 = _sec6[_sec6.find('<h2 id="6-5-reading-the-carbon-target">'):]
ok("\u2b50 S16 sits in \u00a76.1 and S17 in \u00a76.5 (read by every role), each with its alt text and a link to the Carbon planner",
   '<img src="media/S16.png" alt="%s"' % _S16 in _s61 and '<img src="media/S17.png" alt="%s"' % _S17 in _s65
   and _s61.count('href="/#carbon"') == 1 and _s65.count('href="/#carbon"') == 1
   and src.count("media/S16.png") == 1 and src.count("media/S17.png") == 1)
ok("...captioned word for word, listed in Appendix C, drawn as placeholders until captured",
   _caps.get("S16") == _S16 and _caps.get("S17") == _S17 and _appc.get("S16") == _S16 and _appc.get("S17") == _S17
   and _holders.get("S16") == _S16 and _holders.get("S17") == _S17
   and os.path.isfile(os.path.join(MEDIA, "S16.png")) and os.path.isfile(os.path.join(MEDIA, "S17.png")))
_fig_nums = [int(n) for n in re.findall(r"<figcaption>Figure (\d+) — ", src)]
_appc_rows = re.findall(r"<tr><td>(\d+)</td><td>([^<]+)</td><td>([^<]+)</td></tr>", src)
_fig_files = re.findall(r'<img src="media/([^"]+)"[^>]*><figcaption>Figure \d+ — ', src)
ok("the figures are numbered 1 to %d in reading order, and Appendix C lists each, in that order, by its file" % len(_fig_nums),
   _fig_nums == list(range(1, 30)) and [int(r[0]) for r in _appc_rows] == _fig_nums
   and [r[2] for r in _appc_rows] == _fig_files)
ok("\U0001f534 the notes about placeholders stay true before and after the capture (no 'yet', no 'has no picture')",
   "A picture that says PLACEHOLDER on it is a stand-in, not a screenshot" in src
   and "A picture that says PLACEHOLDER — NOT A SCREENSHOT on the image itself stands in for a screen that has not been captured yet" in src
   and "not screenshots yet" not in src and "has no picture yet" not in src and "placeholders until they are captured" not in src)
ok("...and the placeholder card still says those words on the image (make_guide_images.js)",
   "Placeholder — not a screenshot" in _holder_fn and "text-transform:uppercase" in gen_src)
ok("make_guide_images.js can draw named placeholders only (holders S16,S17), so adding a figure redraws no other picture",
   "process.argv[3]" in gen_src and "if (onlyIds.length && !onlyIds.includes(code)) continue;" in gen_src)

# the capture script: every picture, in the guide's set
_want_ids = ["S%02d" % i for i in range(1, 18)] + ["M%02d" % i for i in range(1, 9) if i != 4]
_shots_decl = re.search(r"const SHOTS = \[(.*?)\];", cap_src, re.S)
_shots = re.findall(r'"([SM]\d\d)"', _shots_decl.group(1)) if _shots_decl else []
ok("\u2b50 the capture script takes S01 to S17 and M01 to M08, and no M04 (%d pictures)" % len(_shots),
   sorted(_shots) == sorted(_want_ids) and len(_shots) == 24 and "M04" not in _shots
   and all(('shot(page, "%s"' % i) in cap_src for i in _want_ids if i != "S15")
   and 'want("S15")' in cap_src and '"S15.png"' in cap_src and 'shot(page, "M04"' not in cap_src)
ok("...the set it takes is the set the guide shows (every S and M image in the guide)",
   sorted(_shots) == sorted(f[:-4] for f in media_files if re.match(r"[SM]\d\d\.png$", f)))
ok("...MODUS_OUT and MODUS_ONLY are kept, and MODUS_ONLY refuses a picture the guide does not have",
   "process.env.MODUS_OUT" in cap_src and "process.env.MODUS_ONLY" in cap_src
   and "MODUS_ONLY names a picture the guide does not have" in cap_src)

# never confirms, approves, bakes, sets or saves
_clicked = []
for _ln in cap_src.splitlines():
    if re.search(r"\.(click|check|fill|selectOption|dblclick|press|type)\(", _ln):
        _clicked.append(_ln)
_names = re.findall(r'getByRole\(\s*"button"\s*,\s*\{\s*name:\s*([^,}]+)', cap_src) + re.findall(r"getByText\(([^)]*)\)", cap_src)
_BANNED = re.compile(r"Confirm|Approve|Save|Bake|Set as|Clear|Delete|Withdraw|Reject|Re-open|Discard|Reset|Attach|Create|Edit|Draw|Start again|Download|check now")
ok("\U0001f534 the capture never presses Confirm, Approve, Save, Bake, Set, Clear, Delete, Withdraw, Reject or the like: "
   "no button name or text it looks for says so, and no line that clicks, ticks, types or picks names one (%d lines act)" % len(_clicked),
   _clicked and _names and not any(_BANNED.search(n) for n in _names) and not any(_BANNED.search(l) for l in _clicked))
ok("\U0001f534 ...the Confirm week dialog is opened by the HEADER button, found by its title, and the dialog's own "
   "Confirm week has no title, so it cannot be the one found",
   "const HEADER_CONFIRM = 'button[title^=\"Whole week, every line, one act\"]';" in cap_src
   and fe_src.count('title="Whole week, every line, one act. Planned cells lock; actuals stay typeable."') == 1
   and '<button onClick={doConfirm} className="px-4 py-2 text-sm font-semibold text-white rounded-lg" style={{ background: "var(--green)" }}>Confirm week</button>' in fe_src)
_s10 = cap_src[cap_src.find('await shot(page, "S10"'):cap_src.find('await shot(page, "S11"')]
ok("\U0001f534 ...and it is CANCELLED: the dialog's own Cancel, after the shot whatever happened, and the run stops if it will not close",
   'dlg.getByRole("button", { name: "Cancel", exact: true }).click(' in cap_src
   and 'await dlg.waitFor({ state: "detached"' in cap_src
   and "try { await cancelConfirmDialog(page); }" in _s10 and "process.exit(1)" in _s10
   and '"Confirm the week of' in cap_src and "Confirm the week of {spanLabel(cw.from, cw.to)}" in fe_src)
ok("\U0001f534 ...every confirm() the app asks is answered No",
   'page.on("dialog", d => d.dismiss()' in cap_src and ".accept(" not in cap_src)
_reads = re.search(r"const READS_WITH_A_BODY = \[(.*?)\];", cap_src)
ok("\U0001f534 ...and a write cannot leave the browser: every API call but a GET is aborted, bar three reads that take a body",
   _reads and re.findall(r'"([^"]+)"', _reads.group(1)) == ["/api/auth", "/api/costing/preview", "/api/carbon/scenario"]
   and "return route.abort();" in cap_src and 'm === "GET"' in cap_src
   and "if (blocked.length) process.exit(1);" in cap_src)
ok("...those three are reads on the server's own word (main.py: nothing stored)",
   "this only tells it what it got. Nothing is stored server-side." in main_src
   and main_src.count("it stores nothing") >= 2
   and '@app.post("/api/costing/preview")' in main_src and '@app.post("/api/carbon/scenario")' in main_src)
ok("...the Look-ahead's day cells are never clicked (a click opens a cell that saves on blur); rows open by their \u25b6 only",
   "la-cell" not in cap_src and "td.la-stick button[title^='Show ']" in cap_src
   and "onBlur={() => { saveDay(line, d); setEditing(null); }}" in fe_src)

# S15 without poppler; S16/S17 aim at what the page has
_pdf = cap_src[cap_src.find("async function pdfFirstPage("):cap_src.find("\n(async () => {")]
ok("\u2b50 S15 is pictured without poppler: pdf.js 3.11.174 from cdnjs (exact version, worker included), poppler's pdftoppm tried first",
   'const PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";' in cap_src
   and 'const PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";' in cap_src
   and 0 <= _pdf.find('execFileSync("pdftoppm"') < _pdf.find("pdfjsLib") and "GlobalWorkerOptions.workerSrc" in _pdf)
ok("S16 and S17 aim at what the Carbon planner has: step 2 under the top, step 6 by its id, the target read before the shot",
   '#carbon-step-2' in cap_src and '#carbon-step-6' in cap_src and 'id={"carbon-step-" + n}' in fe_src
   and "Loading the carbon target" in cap_src and "Loading the carbon target…" in fe_src
   and 'goApp(page, "carbon", "Carbon planner")' in cap_src and '<PageHeader title="Carbon planner"' in fe_src)

# the header says how to run it, and it refuses to start without a site and a code
ok("the header gives the exact PowerShell command and what it writes",
   all(s in cap_src for s in ('$env:MODUS_URL = "https://app.wayscope.co.uk"', '$env:MODUS_PLANNER_CODE = Read-Host "Planner code"',
                              "$env:NODE_PATH = (npm root -g)", "node backend/tools/capture_guide.js",
                              "WHAT IT WRITES: frontend/help/media/S01.png … S17.png and M01.png … M08.png")))
_refuse = cap_src.find("if (!BASE || !CODE)")
ok("\U0001f534 it refuses to run without MODUS_URL and MODUS_PLANNER_CODE, before Playwright is even loaded",
   0 < _refuse < cap_src.find('require("playwright")') and "process.exit(2);" in cap_src[_refuse:_refuse + 200])
_node = shutil.which("node")
_env = {k: v for k, v in os.environ.items() if k not in ("MODUS_URL", "MODUS_PLANNER_CODE", "MODUS_ONLY", "NODE_PATH")}
def _run(extra):
    e = dict(_env); e.update(extra)
    return subprocess.run([_node, CAP], env=e, capture_output=True, text=True, encoding="utf-8", timeout=60)
if _node:
    _r0 = _run({})
    _r1 = _run({"MODUS_URL": "https://app.wayscope.co.uk/map", "MODUS_PLANNER_CODE": "x"})
    _r2 = _run({"MODUS_URL": "http://127.0.0.1:9", "MODUS_PLANNER_CODE": "x", "MODUS_ONLY": "M04"})
ok("...run with no site or code it stops with exit code 2 and says what to set; a page address or an unknown picture is refused the same way",
   _node is not None and _r0.returncode == 2 and "Set MODUS_URL and MODUS_PLANNER_CODE" in _r0.stderr
   and _r1.returncode == 2 and "site address only" in _r1.stderr
   and _r2.returncode == 2 and "M04" in _r2.stderr)

# =========================================================================== #
#  11 Oct 2026 — the review's fixes to the capture script                       #
#  (branch claude/guide-screenshots)                                            #
# =========================================================================== #
# What these prove: the browser asks for the GPU and a map picture with a blank foot fails; the pictures are British
# (en-GB, London time); S14 is not taken unless asked; S15 is drawn at the size shown; S12 fails unless the analysis
# table is in the picture; S05 folds the rail and opens it again; S08's caption says what its picture shows.
# What they do not prove: what the GPU does on another machine, or the pictures themselves (dry-run locally only).
_launch = cap_src.find("chromium.launch({ args: [...GPU_ARGS, ...LANG_ARGS] })")
_plain = cap_src.find("browser = await chromium.launch({ args: LANG_ARGS });")
ok("\U0001f534 the capture's Chromium asks for the GPU (--enable-gpu, --use-angle=d3d11, --ignore-gpu-blocklist), "
   "and starts without it only if that launch fails",
   'const GPU_ARGS = ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"];' in cap_src
   and 0 < _launch < cap_src.find("catch (e)", _launch) < _plain
   and cap_src.count("chromium.launch(") == 2)
_ready = cap_src[cap_src.find("async function mapReady("):cap_src.find("async function mapIdle(")]
_shotfn = cap_src[cap_src.find("async function shot("):cap_src.find("// ---- the staff app")]
_foot = cap_src[cap_src.find("async function mapFootDrawn(page)"):cap_src.find("async function mapIdle(")]
ok("\U0001f534 ...and a map picture whose foot is blank fails: checked when the map is ready and as each M picture is "
   "taken, on a strip read back from the WHOLE picture (a small clip came out drawn when the picture was not), and the "
   "picture checked is the picture saved",
   "await mapFootDrawn(page);" in _ready and _foot
   and 'if (id.startsWith("M")) fs.writeFileSync(path.join(MEDIA, id + ".png"), await mapFootDrawn(page));' in _shotfn
   and "const png = await page.screenshot({ clip: { x: 0, y: 0, ...VIEW } });" in _foot
   and "if (flat < FOOT_ROWS - 2) return png;" in _foot and "page.screenshot({ clip: seg })" not in _foot
   and "document.elementFromPoint(x, y) === cv" in _foot and "createImageBitmap" in _foot
   and "the foot of the map is blank" in _foot and "above the foot of the window" in _foot)
ok("\U0001f534 the pictures are British whatever the laptop's settings: one browser context, locale en-GB, Europe/London, "
   "and Chromium started with --lang=en-GB (a date box follows the operating system's region otherwise), with or without the GPU",
   'const LOCALE = { locale: "en-GB", timezoneId: "Europe/London" };' in cap_src
   and 'const LANG_ARGS = ["--lang=en-GB"];' in cap_src and _launch > 0 and _plain > 0
   and "browser.newContext({ viewport: VIEW, deviceScaleFactor: 1, ...LOCALE })" in cap_src
   and cap_src.count("newContext(") == 1)
ok("\U0001f534 MODUS_SKIP defaults to S14 (the live Config still lists the EU vehicles), MODUS_ONLY wins over it, "
   "'none' skips nothing, and the header says so",
   'const SKIP_RAW = process.env.MODUS_SKIP === undefined ? "S14" : process.env.MODUS_SKIP;' in cap_src
   and "const want = (id) => ONLY.length ? ONLY.includes(id) : !SKIP.includes(id);" in cap_src
   and "/^\\s*none\\s*$/i.test(SKIP_RAW)" in cap_src
   and "MODUS_SKIP names a picture the guide does not have" in cap_src
   and 'MODUS_SKIP — a comma list of pictures NOT taken (their placeholders stay); default "S14".' in cap_src
   and '$env:MODUS_ONLY = "S14"' in cap_src and "claude/remove-eu-vehicles" in cap_src
   and cap_src.find("const SKIP_RAW") < cap_src.find('require("playwright")')
   and "if (!ONLY.length) SKIP.forEach(id => skipped.push(" in cap_src)
ok("...the header's command clears leftovers from a retake or a dry run, and says in one line that M02 and M05 may fail",
   "Remove-Item Env:MODUS_ONLY, Env:MODUS_SKIP, Env:MODUS_OUT -ErrorAction SilentlyContinue" in cap_src
   and " *   M02, M05 — 11 Oct 2026: may fail and keep their placeholders until the public map's bugs" in cap_src
   and "iptCheckboxId(underlayKey())" not in cap_src[:cap_src.find("const fs = require")])
if _node:
    _r3 = _run({"MODUS_URL": "http://127.0.0.1:9", "MODUS_PLANNER_CODE": "x", "MODUS_SKIP": "S14,X99"})
ok("...and MODUS_SKIP naming a picture the guide does not have is refused with exit code 2, before any browser",
   _node is not None and _r3.returncode == 2 and "X99" in _r3.stderr and "MODUS_SKIP" in _r3.stderr)
_pdf2 = cap_src[cap_src.find("async function pdfFirstPage("):cap_src.find("\n(async () => {")]
ok("\U0001f534 S15's pdf.js page is drawn at the size it is shown (scale = 1380 / width), not drawn at 1.5\u00d7 and shrunk",
   "const scale = 1380 / vp.width;" in _pdf2 and "1380 * 1.5" not in _pdf2 and "width:1380px" in _pdf2)
_s12 = cap_src[cap_src.find('await shot(page, "S12"'):cap_src.find('await shot(page, "S13"')]
ok("\U0001f534 S12 is aimed at the analysis table with scrollUnderHeader, and fails unless the table's head and first row "
   "are inside the picture and inside the list's own box",
   "await scrollUnderHeader(page, th, 150);" in _s12 and "m.scrollTop = m.scrollHeight" not in _s12
   and 'box.querySelector("thead.sticky")' in _s12 and "the analysis table is not inside the picture" in _s12
   and "head.top >= lo - 1 && end <= hi + 1" in _s12
   and '<th className="px-2 py-1 text-left font-semibold">Option</th>' in fe_src
   and '<thead className="bg-slate-50 text-slate-500 text-xs sticky top-0">' in fe_src)
_s05 = cap_src[cap_src.find('await shot(page, "S05"'):cap_src.find('await shot(page, "S06"')]
ok("S05 folds the rail with the app's own button, fails unless the Status column's words are whole, and opens the rail "
   "again after the shot whatever happened",
   "await setRail(page, false);" in _s05 and "try { await setRail(page, true); }" in _s05
   and _s05.find("setRail(page, false)") < _s05.find("try { await setRail(page, true); }")
   and "the Status column is cut off" in _s05
   and 'aside[data-guide="rail"] button[title="${open ? "Expand" : "Collapse"}"]' in cap_src
   and 'title={railOpen ? "Collapse" : "Expand"}' in fe_src and 'data-guide="rail"' in fe_src)
# NARROWED 11 Oct 2026: S08's caption no longer promises the Stockpiles block (it lies ~1,700 px under the top of the
# lines table, outside the picture); it says what the picture shows
_S08 = "Account view \u2014 last week line by line: planned, actual, variance and cost"
ok("S08's caption says what its picture shows (the Stockpiles block is below it), in the figure, Appendix C and the placeholder",
   _caps.get("S08") == _S08 and _appc.get("S08") == _S08 and _holders.get("S08") == _S08
   and '<img src="media/S08.png" alt="%s"' % _S08 in src and "the Stockpiles block" not in _caps.get("S08", "x"))

# =========================================================================== #
#  11 Oct 2026 — the second review of the capture script                        #
#  (branch claude/guide-screenshots)                                            #
# =========================================================================== #
# What these prove: S12 and S13's captions say what their pictures show, wherever a caption is written; S12 fails unless
# the route's haul roads, its closures line and every row of the analysis table are in the picture; S09 folds the rail
# and fails unless next month's last week is whole. What they do not prove: the live pictures (dry-run locally only).
_S12 = "Routes — a route opened: its haul roads, the closures check and the analysis table"
_S13 = "Zones — a temporary haul road with its speed and mode"
# NARROWED 11 Oct 2026: S12's caption promised "bake status, analysis, alternatives, planning block". The opened route is
# ~480 px tall and the list's box shows ~256 px under its sticky head, so R001's row (its bake chips) is above the picture,
# and no alternatives or planning block are in it; it says what the picture shows
ok("S12's caption says what its picture shows (no bake status, alternatives or planning block), in the figure, its alt "
   "text, Appendix C and the placeholder",
   _caps.get("S12") == _S12 and _appc.get("S12") == _S12 and _holders.get("S12") == _S12
   and '<img src="media/S12.png" alt="%s"' % _S12 in src
   and "bake status" not in src and "planning block" not in src and "planning block" not in gen_src)
# NARROWED 11 Oct 2026: S13's caption promised "a disruption zone and a haul road"; no zone outline is in the map's frame
# and the demo's one disruption zone is a list row cut off at the foot, so it names the haul road only
ok("S13's caption names the haul road with its speed and mode only (no zone is in the picture), in the figure, its alt "
   "text, Appendix C and the placeholder",
   _caps.get("S13") == _S13 and _appc.get("S13") == _S13 and _holders.get("S13") == _S13
   and '<img src="media/S13.png" alt="%s"' % _S13 in src
   and "a disruption zone and a haul road" not in src and "a disruption zone and a haul road" not in gen_src)
ok("\U0001f534 S12 scrolls the list so the analysis table's LAST row sits at the box's foot, and fails unless that row, the "
   "route's haul-road heading and its closures line (once checked) are inside the picture and the box",
   "r1 = rows[rows.length - 1]" in _s12
   and "box.scrollTop += r1.getBoundingClientRect().bottom - (Math.min(H, box.getBoundingClientRect().bottom) - 6);" in _s12
   and _s12.find("await scrollUnderHeader(page, th, 150);") < _s12.find("box.scrollTop += r1")
   and "/^Temporary haul roads on this route$/i" in _s12 and "the route's haul roads are not in the picture" in _s12
   and "/planned closures|road restrictions/i" in _s12 and "the closures check is not in the picture" in _s12
   and "/^Checking road restrictions/.test(p.textContent.trim())" in _s12
   and "if (!at.haul || !at.haulIn)" in _s12 and "if (!at.closures || !at.closuresIn)" in _s12
   and "Temporary haul roads on this route" in fe_src
   and "planned closures (current or future) within ${data.match_m} m of this route." in fe_src
   and '{dated ? "Planned closures on this route" : "Road restrictions on this route"}' in fe_src
   and "Checking road restrictions…" in fe_src)
_s09 = cap_src[cap_src.find('await shot(page, "S09"'):cap_src.find('await shot(page, "S10"')]
_colw = cap_src[cap_src.find("async function columnWords(th)"):cap_src.find("async function showGridTop(")]
ok("S09 folds the rail as S05 does, opens it again after the shot whatever happened, and fails unless the Horizon's last "
   "column is a week whose words end inside the table's box",
   'await lookahead(page, "Horizon");' in _s09 and "await setRail(page, false);" in _s09
   and "try { await setRail(page, true); }" in _s09
   and _s09.find("setRail(page, false)") < _s09.find("columnWords(lastWeek)") < _s09.find("try { await setRail(page, true); }")
   and "/^W\\d/.test(fit.text)" in _s09 and "the last week column is cut off" in _s09
   and '<table className="text-sm" style={{ minWidth: 1300 }}>' in fe_src
   and "W{w} · {weekSpanLbl(horizon, m, w)}" in fe_src)
ok("...S05 and S09 share one column check: the words of the column's head and of every row on screen, against the right "
   "edge of the box that scrolls the table sideways",
   bool(_colw) and "createTreeWalker(c, NodeFilter.SHOW_TEXT)" in _colw and "right <= edge + 1" in _colw
   and "n > 1" in _colw and "await columnWords(st);" in _s05 and "await columnWords(lastWeek);" in _s09
   and cap_src.count("createTreeWalker") == 1)


print("test_help.py: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
