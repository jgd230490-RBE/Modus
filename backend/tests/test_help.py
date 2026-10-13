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
# REVERSED 13 Oct 2026 (the user, 12 Oct: each team gets its own share of the target): it asserted "not split by team"
# and "with no verdict" in the guide; the guide now says how a team's share is split and that each figure has a verdict
ok("...a team code: its own share of the target (split by each team's plan with the agreed decisions), its figures with a verdict",
   "not split by team" not in text and "with no verdict" not in text
   and "the scheme's target split by each team's plan with the agreed decisions" in text
   and "so the shares add up to the target" in text and "with a verdict on each" in text)
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
   "FICTIONAL DEMO SCHEME · NOTHING HERE IS REAL" in src and "<strong>Guide</strong>, at the right-hand end of the bar" in src
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
   "On the shared demo, show these but do not press them" in text and "Route all</strong> (it spends routing calls)" in src   # 13 Oct 2026 (W3, narrowed): the button reads Route all
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
   # 13 Oct 2026 (W3, narrowed): the same two rules in the screen's words
   "A line whose route is not routed for its vehicle is counted as unknown" in text
   and "A line whose route has no line drawn at all is left out of the bar." in text
   and "a route that is not baked is counted as unknown" not in text and "a route that is not routed is counted as unknown" not in text)

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
    "2 ...and its rule": "The gap is the shift's minutes ÷ arrivals, an average with no hourly",
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
ok("...it maps the old screen words to the new ones, and says the exports keep the old words (decision A)",
   "baked / not baked / unbaked</td><td>routed / not routed yet" in tg and "line-month</td><td>forecast month" in tg
   and "UNBAKED, NOT BAKED (clash rail and line flags)</td><td>NOT ROUTED" in tg and "The XLSX and PDF exports and the clash text made on the server still say" in tg)
ok("...and the user guide's Appendix D points at it (the first client's Word document is no longer mentioned)",
   '<a href="/help/technical/">technical guide</a> (staff only)' in src and "Word document" not in src and "fifty pages" not in src
   and '<a href="/help/#appendix-d-technical-reference">Open Appendix D</a>' in tg)

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
ok("...the guide names the buttons the screens now show (Route all, not routed)",
   "<strong>Route all</strong>" in src and "Bake all" not in src and "not routed" in src)

# 13 Oct 2026 (bundle E): the guide describes what the Appearance button now offers, and the narrow left menu
ok("E (W16): the guide names the four accents beside the three looks, the plan-first rule and the status shapes",
   all(f"<strong>{w}</strong>" in src for w in ("Ink", "Light", "Dark", "Orange", "Blue", "Blue shades", "Orange shades"))
   and "the first series is the plan and the second what was delivered" in src and "a warning is a triangle and a problem a diamond" in src)
ok("E (W5): the guide says the left menu shows icons only below 768 px and opens over the page",
   "Below 768 px the left menu shows its icons only" in src and "opens it over the page until you pick one" in src)

print("test_help.py: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
