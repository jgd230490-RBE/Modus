WAYSCOPE — REBRAND DELIVERY · 29 September 2026
================================================

The product is Wayscope on every screen, export and page: "Modus" no longer appears in
any shipped file (asserted), the theme is the Wayscope one (ink #1F2024, orange as the
brand accent only, blue for controls, amber still means WARNING), the header is the
lockup + a thin rule + the tenant's name, the three gate pages carry the stacked logo,
the favicon set is served at the root, and the user guide's synthetic figures are
regenerated with the new header. Branch `claude/wayscope-rebrand` in the sandbox; a push
was refused (repo not a source for the session), so this is the zip + Codespace routine.

README.txt (this file) is the delivery note. Commit it with the rest. It starts
"WAYSCOPE — " and the harness (test_modus.py) now requires that prefix.


ACTIONS — IN THIS ORDER
-----------------------
1. APPLY THE BRAND ASSETS FIRST. This delivery REFERENCES `frontend/brand/` (18 files:
   the header and stacked logos, the favicon set, site.webmanifest, theme-tokens.css)
   but does NOT contain them — they were delivered separately this morning as
   `wayscope-brand-assets-0929.zip` and were not at HEAD (830c153) when this was cut.
   Upload that zip to the Codespace and unzip it first (its own README has the commands).
   Without the folder the app still boots and works (that was made safe on purpose —
   a missing folder is a 404, not a crash), but every logo and favicon is a broken image
   and three assertions in test_modus.py and eight in http_smoke.py stay red.

2. Upload THIS zip as ONE file to the Codespace, then the commands at the end.

3. Delete the stray root file `download` (it is the G2 `.gitignore`, renamed by the web
   uploader): this delivery ships a real `.gitignore` with the same content. A zip never
   deletes, so:  git rm download
   (Do it before the commit in step 2's commands, or as a second commit.)

4. Push. If GitHub's push protection flags the Mapbox `pk.` token in map/config.js again,
   allow it through the unblock link — the token line itself is unchanged in this zip.

5. Render deploys main. FIRST LOOK, in this order:
   a. The browser tab: the Wayscope favicon (hard-refresh; icons are cached aggressively).
   b. The staff app header: the orange-and-white lockup on ink, a thin rule, then the
      tenant's name (hidden below 640 px). The default tenant shows the lockup alone.
   c. Sign out → /map/ in a private window: the password page, ink background, the
      stacked logo above the white box.
   d. Sign in → User guide: the nav says "Wayscope · User guide" (text — see item 5 under
      NOT TESTED), the intro says "Wayscope is…", the figures say Wayscope in their header.
   e. Look-ahead → Export PDF: the heading ink is #1F2024; the route map's pins are ink
      and the theme red.


WHAT CHANGED
------------
* Name: every "Modus" in shipped files → Wayscope (titles, the default tenant name in
  factors.json / config.py / index.html / map, FastAPI title, exports' default name and
  User-Agent, the guide, the tools, comments and docstrings). test_modus.py now scans
  every shipped file for \bModus\b and fails on a hit. Deliberately NOT renamed: the
  Render service names `modus-web` / `modus-db` (a rename changes the URL), the `modus_*`
  localStorage / cookie keys (invisible; renaming the cookie would sign everyone out once),
  env var names, the GitHub repo, the demo tenant "Wolds Link — demo corridor".
* Theme: `--navy-deep` #0F172A → #1F2024 everywhere (app tokens, map brandDark and
  forecast casing, overlay.js's reserved hexes, the canvas marks, the PDF ink, the guide,
  the guide-image tool). #0F172A is on the retired list now. Orange tokens added to :root
  (`--brand-orange` #FF8C14 and friends) and used ONLY for the 2 px rule under the header;
  the guide's nav has the same rule on its right edge. `--gold` #D97706 (amber) is untouched:
  unbaked routes, missing index, capacity from 90 %, edited/thaw marks keep it. Forecast
  routes on the map stay blue (your decision: orange would blur with amber warnings).
* Header: the old gold bar + bold name + "Modus · Forecasting & Route Map" caption is gone;
  `/brand/logo-header-on-dark.svg` at 38 px + rule + tenant name in white/70, click-to-home
  kept (your decision: logo + rule + name).
* Gate pages (map password, guide sign-in, map closed): Wayscope titles, the stacked logo,
  the Wayscope palette (they still carried the pre-G2 navy/blue/red), and "Alliance staff" /
  "outside the alliance" wording replaced with "Staff" / "without a staff sign-in".
* Static: `app.mount("/brand", …)` (no-cache, not gated) and root routes for favicon.ico,
  favicon.svg, apple-touch-icon.png, site.webmanifest, icon-192.png, icon-512.png,
  icon-512-maskable.png (browsers and iOS ask at the root). A name outside that set is a
  404 — `../factors.json` cannot escape. NoCacheStatic now tolerates a missing directory
  (Starlette otherwise refuses to boot, or 500s on the first request).
* <head>: favicon links + theme-color on the app, the map, the guide and the gate pages.
* document.title: "<tenant> · Wayscope", plain "Wayscope" for the default tenant.
* Guide: nav brand text "Wayscope", intro sentence, and all 27 synthetic figures
  regenerated (backend/tools/make_guide_images.js, headless Chromium) — they now read
  "Wayscope" in the header and use the new ink. They are still placeholders and say so.
* Also in this zip, found at plain HEAD: test_lookahead.py was 240/2 — two assertions
  that only fail in the FIRST WEEK OF A MONTH (the commit week is Oct W1 today: `(MI, 2)`
  is the next-week day bucket, and the account week Sep W4 is off the two-month horizon
  grid). Narrowed with the reason written in; the code behaviour was correct.
* `.gitignore` (the G2 one, see action 3).


TESTS (sandbox, stubbed suite; counts are before → after)
---------------------------------------------------------
Plain HEAD 830c153: 3,256 passed / 2 failed (the two date bombs above).
This zip over a clean HEAD, WITHOUT frontend/brand/: 3,294 passed / 1 failed — the one is
"frontend/brand/ ships every file the pages reference" (action 1).
With the brand assets applied: expected 3,295 / 0.
  test_modus 148 → 171 (+31 rebrand assertions, incl. the \bModus\b scan, the manifest's
  icon paths, the gate pages, the header, the tokens, the map ink, the exports)
  parse_frontend 378 → 386 · parse_map 514 → 518 · test_lookahead 240/2 → 244/0
  http_smoke (real FastAPI in a venv): 65 → 78 with the brand files present (favicon/brand
  200s without a cookie, content types, no-cache, the manifest's icons, the branded
  password page, the mount cannot be walked out of); WITHOUT the folder the 8 brand checks
  fail as designed and the app still serves everything else.


NOT TESTED
----------
1. The live favicon on Render and the iOS home-screen icon (only headless Chromium here).
2. The lockup's real rendering in the header (Mapbox/CDNs are blocked in the sandbox;
   the SVG files themselves were not in the sandbox — see action 1).
3. The guide's nav still names the product as TEXT. The plan was the on-dark lockup
   inlined as SVG (the guide fetches nothing by design; test_help pins that). It needs the
   SVG file in hand; it lands in the next delivery once frontend/brand/ is at HEAD.
4. The PDF header mark (rebrand brief §2, "optional"): not done — the PNG mark is in the
   full kit, not in the assets zip. Left for later; the PDF is otherwise rebranded.
5. Push protection behaviour on this push (item 4 above).


AFTER IT LANDS — PROJECT INSTRUCTIONS TO CHANGE (only you can edit them)
-------------------------------------------------------------------------
* "**Modus** is a haulage forecasting…" → Wayscope (the service names stay modus-*).
* The delivery-note rule: README.txt starts "WAYSCOPE — " (was "MODUS — ").
* "CI: .github/workflows/suite.yml runs every harness on push; keep it green" — that file
  is NOT in the repo any more (commit 2c9e9a5 "Delete .github directory"). There is no CI
  on push today. Say whether you want it back (it was a one-file workflow).
* "Public-facing wording: the product name needs a qualifier" — resolved: Wayscope.


CODESPACE COMMANDS
------------------
Upload wayscope-brand-assets-0929.zip first (if not already applied), then this zip, as
single files. Then, in the Codespace terminal (check the names with `ls *.zip` first):

  unzip -o wayscope-brand-assets-0929.zip && rm wayscope-brand-assets-0929.zip
  unzip -o wayscope-rebrand-0929.zip && rm wayscope-rebrand-0929.zip
  git rm -q download
  git add -A && git commit -m "Wayscope rebrand: name, theme, header, gate pages, brand files, favicon" && git push

If the push is rejected as non-fast-forward:
  git pull origin main --no-rebase --no-edit
  git push
