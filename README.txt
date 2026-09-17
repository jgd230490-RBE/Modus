MODUS — G2 DELIVERY · 16 September 2026
========================================

This zip IS the whole new repository. Unpack it into an EMPTY folder and upload
everything to a new PRIVATE GitHub repository called "modus". It starts a fresh
history: nothing from RBE_Alliance1 comes across except the product code, with every
piece of alliance data taken out.

README.txt (this file) is the delivery note. Commit it with the rest: it is how a later
session checks which delivery is at HEAD. README.md is the product's own readme.

A second zip, rbe-tenant-offline.zip, holds the first tenant's data that left the code.
It is NOT part of the repository. Keep it offline, with your database backup.


ACTIONS — IN THIS ORDER
-----------------------
1. BACK UP THE OLD DATABASE FIRST. Render → the database rbe-a1-db → Backups (or
   Export) → download it. That database is the ONLY full copy of the first tenant's forecasts,
   weeks, actuals and baked routes. Nothing in either zip replaces it.

2. MAKE THE OLD REPOSITORY PRIVATE NOW. Your old repository, RBE_Alliance1, is
   public and still contains the alliance's network, alignment, screenshots and the
   claude/ project notes. Settings → Danger Zone → Change visibility → Private.
   Delete it later, only once you are happy with step 1 and the offline zip.

3. CREATE THE NEW REPOSITORY. github.com → New → name "modus" → PRIVATE → Create.
   Upload the unpacked files, keeping the folders. ⚠️ Check that the two files whose
   names start with a dot went up: .gitignore and .github/workflows/suite.yml
   (Windows Explorer shows them; macOS Finder hides them until Cmd+Shift+.). If the
   uploader skipped one, create it on github.com with "Add file → Create new file" and
   paste its contents. Without suite.yml there are no automatic test runs.

4. DEPLOY. Render → New → Blueprint → the modus repository. render.yaml creates a NEW
   web service (modus-web) and a NEW database (modus-db); it does not touch
   rbe-a1-logistics or rbe-a1-db. Check the two plan lines first (starter,
   basic-256mb — paid plans), then Apply.

5. SET THE SECRETS on modus-web → Environment (see env.example for each):
     ADMIN_TOKEN     a NEW value — paste what this PRINTS, never the command itself:
                       Git Bash:    openssl rand -hex 24
                       PowerShell:  $b = New-Object byte[] 24
                                    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
                                    ($b | ForEach-Object { $_.ToString('x2') }) -join ''
     PLANNER_CODE, ADMIN_CODE, and IPT1_CODE… for the teams you create
     MAP_PASSWORD    only if outsiders should open the map
     HERE_API_KEY    use a key from a NEW HERE App ID for Modus — HERE's terms want one
                     App ID per application, not the one the old service uses
     MAPBOX_TOKEN    your public pk. token (see "Mapbox" below)
   Do NOT set ALLOW_DEMO_CODES.

6. LOAD THE DEMO (the service boots EMPTY — that is correct). From the unpacked
   folder, in PowerShell (curl.exe ships with Windows 10 and 11 — type the .exe):
     curl.exe -X POST "https://<modus-web>/api/admin/tenant/import?token=<ADMIN_TOKEN>" -H "Content-Type: application/json" --data-binary "@demo/uk-corridor.package.json"
   It answers {"ok":true,...} with the rows it inserted.
   Then sign in with PLANNER_CODE → Routes → Bake all. Eighteen routes × the vehicles
   each carries × two legs is a few hundred HERE calls. Until baked, the demo reads
   "not baked" everywhere — by design.

7. TYPE A CURRENT UK DIESEL PRICE. The demo carries a typed placeholder of £1.43/L
   dated 14 Sep 2026. Config → the diesel widget → type the latest weekly UK figure
   (the government's weekly road fuel prices). There is no automatic feed outside
   the EU, deliberately.

8. REPLACE THE GUIDE'S PLACEHOLDER SCREENSHOTS. The 22 screenshots in the user guide
   are clearly marked placeholders. Once step 6 is baked, on your laptop (Node.js
   installed), from the unpacked folder, in PowerShell:
     npm i -g playwright
     npx playwright install chromium
     $env:MODUS_URL = "https://<modus-web>"
     $env:MODUS_PLANNER_CODE = "<code>"
     $env:NODE_PATH = (npm root -g)
     node backend/tools/capture_guide.js
   then upload frontend/help/media/*.png. It never confirms or saves anything.
   M05 (road restrictions) stays a placeholder on the UK demo: no provider there.
   S15 (the PDF) needs poppler's pdftoppm on the PATH; without it that one shot is
   skipped with a message and its placeholder stays.

9. RETIRE THE OLD RENDER SERVICE AND DATABASE when you are ready — they bill monthly.
   Only after step 1.

10. BEFORE SHOWING A PAYING CLIENT: write to HERE about the Base Plan's excluded use
    cases ("Asset Management") — the open question from earlier today.


MAPBOX
------
The public token in map/config.js and backend/config.py belongs to your personal
Mapbox account. It is safe to expose (pk. tokens are public by design) but restrict it
to your Modus domain(s) in the Mapbox account, or create a Modus-specific token and set
it as MAPBOX_TOKEN and in map/config.js.


WHAT CHANGED
------------
No alliance data ships.
  * No seed network, no seed taxonomy, no static alignment/chainage/rail files, no
    project screenshots. A fresh deployment boots EMPTY (only the generic disciplines
    and the default configuration).
  * A source-level sweep (backend/tests/test_modus.py) fails the suite if a shipped
    file names the alliance, its partners or its places.
  * Names and figures from that project were also taken out of code comments.

A tenant is one file.
  * backend/tenant_package.py: export/import a whole tenant (every table, the
    configuration, the map overlay, baked geometry) — GET /api/admin/tenant/export,
    POST /api/admin/tenant/import (empty tenant, or replace=1), GET .../status.
  * The map alignment is tenant data: PUT /api/admin/overlay, served to the map by
    GET /api/public/alignment (gated like the map, with an ETag). map/overlay.js is
    product code with empty defaults. Uploads are refused when a band runs backwards,
    a boundary is off a band edge, or a colour is not #RRGGBB.

The tenant's own words.
  * Settings (Config → Everything): name, team_label, currency (symbol only — no
    exchange rates), country. Country switches the Estonian road restrictions,
    orthophoto and vehicle labels on for EE only, and the automatic EU diesel price
    for EU-27 only.
  * Team ids stay IPT1…IPT6 (your decision). Every place a person reads a team — the
    app, the map, the XLSX and PDF, sign-in labels, the clash rail — now shows the
    tenant's name for it ("North Team"), never the id. Flag codes are shown by name.
  * The route-timing diagnostic probes in the tenant's own time zone (from its
    country); a country it does not know runs on UTC and says so.

The Modus look.
  * Name and theme (ink #0F172A, accent #2563EB, clash #DC2626, warning #D97706,
    confirmed #059669). "Public route map" is now "Route map" (it is gated). Long KPI
    values shrink instead of being cut off. A typed diesel price is dated "typed".

The demo.
  * demo/uk-corridor.package.json — the Wolds Link, a FICTIONAL 31.8 km corridor in the
    East Midlands; rebuilt by backend/tools/make_demo_tenant.py. Fixed today: its work
    sections now fit the line (the last one used to start past the end of it), its
    chainage markers sit on exact 100 m values (the map's 10 km / 5 km / 1 km ticks
    had nothing to draw), and one boundary is marked provisional to show the feature.

The guide.
  * frontend/help rewritten in product terms; the stale "Stock held" description now
    matches the Stockpile capacity panel; the five diagrams redrawn in the Modus theme
    (backend/tools/make_guide_images.js); 22 honest placeholders; the capture tool.

Repository.
  * README.md, env.example, render.yaml (new blueprint), .gitignore,
    .github/workflows/suite.yml (every harness on every push).


TESTS — COUNTS
--------------
  Stubbed suite (15 Python + 4 JS harnesses)    3,258 passed, 0 failed
      baseline at RBE_Alliance1 1c5ac11:         3,063 passed, 1 failed
  backend/tests/http_smoke.py (NEW, real FastAPI, TestClient, pinned requirements)
                                                    65 passed, 0 failed
      gate and cookie, sign-in, empty boot, import/export/replace over HTTP, the
      overlay and its ETag/304, team scoping, real XLSX (openpyxl) and PDF (reportlab)
      read back: team names, £, the tenant's name, no team ids.
  The same Python harnesses in a CI-like venv without FastAPI: all green.
  Off-repo equivalence check: the ORIGINAL 140 overlay assertions, run against the
      new map/overlay.js with the first tenant's overlay from the offline zip: 140 passed.
  The staff app, rendered in headless Chromium against a local server (libraries
      served from disk): all 15 staff screens load and capture; no page crash.

Assertions were narrowed or reversed, never deleted: every project-specific fact the
map harness used to pin is now a REVERSED assertion that the fact is NOT in product code.


NOT VERIFIED
------------
  * PostgreSQL — every run here is SQLite.
  * HERE — no key in the sandbox; nothing was baked.
  * Mapbox — no map ever drew here (tiles unreachable), so no map rendering, and the
    map half of capture_guide.js has never run.
  * The GitHub Actions workflow — written and its steps reproduced locally, but not
    run on GitHub.
  * The Render blueprint — not applied. A 9.8 MB overlay upload works locally in about
    a second; Render's own request limits were not tested.
  * Street View.


KNOWN GAPS
----------
  * A tenant with NO country set still falls back to the Estonian diesel index. Set
    the country. (Queued as a G3 fix — it touches four harnesses.)
  * Test fixtures still carry alliance place names (your decision: leave them). If
    this repository is ever shared outside, strip backend/tests/fixtures and the
    browser-check scripts first.
  * The fair-price model's default coefficients come from Estonian public sources
    (driver wages, the spring-thaw limit). The demo reads them as £ and says so in its
    configuration. Replace them with UK figures before quoting a fair price to anyone.
  * The demo's two granite quarries sit near real quarry sites in Leicestershire under
    invented names.
  * Six team slots per tenant; one tenant per deployment (TENANT_ID).
  * Access is still shared codes per role — do not describe a deployment as secure.
