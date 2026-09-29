WAYSCOPE — H1 · UK LOCALISATION · 29 September 2026
====================================================

Apply AFTER the rebrand zip (wayscope-rebrand-0929.zip) and the brand assets zip. This
delivery builds on both: its files are the cumulative versions (a file in both zips is
complete here). Branch `claude/h1-uk` in the sandbox; a push was refused, so the zip +
Codespace routine.

README.txt (this file) is the delivery note; commit it with the rest.

A GB tenant now sees nothing Estonian: the diesel index comes from DESNZ, road
restrictions from National Highways' planned closures, the vehicle pickers lead with UK
trade names and hide the EU N-category ones, the aerial basemap is Mapbox Satellite
labelled "Aerial", and every distance reads in the tenant's unit — miles for the demo.
A tenant with NO country no longer falls back to Estonia's diesel index (the G3-prep gap).


ACTIONS — IN THIS ORDER
-----------------------
1. Upload this zip as ONE file to the Codespace; the commands are at the end.

2. `backend/factors.json` IS INCLUDED (DESNZ 2026 CO2 factors, two UK truck mixers, the
   per-country `vehicle_sets` block, notes). If you have edited factors.json yourself,
   MERGE rather than overwrite. The seed only matters for a NEW tenant or "Reset to
   file"; an existing tenant's live config row is untouched by the deploy.

3. `demo/uk-corridor.package.json` IS REGENERATED (tenant.distance_unit "mi", a GB
   fair-price coefficient set with sources in £, the new vehicles, a typed DESNZ
   placeholder of £1.955/L dated 21 Sep). A demo tenant imported from the OLD package
   keeps the old copy until you re-import it with replace=1 — from the repo folder, in
   PowerShell (curl.exe ships with Windows 10 and 11 — type the .exe):
     curl.exe -X POST "https://<the service>/api/admin/tenant/import?replace=1&token=<ADMIN_TOKEN>" -H "Content-Type: application/json" --data-binary "@demo/uk-corridor.package.json"
   replace=1 DELETES that tenant's rows first (forecasts, weeks, baked geometry too), so
   do this on the demo tenant only, and bake again afterwards.

4. Deploy (Render, main). At boot the guard adds four columns to `fuel_index`
   (provider, native_price, native_unit, vat_pct) — ADD COLUMN IF NOT EXISTS, no data
   rewritten. Watch the deploy log for an ALTER error; there should be none.

5. THE TWO PROBES — the first real calls to gov.uk and National Highways ever made by
   this product. Neither host is reachable from the build sandbox, so both paths have
   only run against fixtures shaped from the published schemas. Open, with the admin
   token, on a deployment whose tenant is GB (the demo):
     /api/admin/diagnostics/fuel-index?probe=1&token=<ADMIN_TOKEN>
       → probe.ok true and probe.parsed.eur_per_l ≈ 1.9x means the content API resolved
         this week's CSV and the column names matched. If probe.ok is false, read
         probe.error, probe.detail.csv_head (the header row) and tell me what it says —
         the columns are matched by header TEXT ("Date", "ULSD … pence/litre", "VAT")
         and may need one line changed.
     /api/admin/diagnostics/restrictions?probe=true&token=<ADMIN_TOKEN>
       → probe.records_returned 3, probe.sample_dates.from/to filled, probe.reading
         "field map found start and end dates". If reading says "no start/end date
         found", send me probe.sample_property_names — the field map in
         restrictions.NH_FIELDS is one dict.
   Nothing is written by a probe.

6. Then the real thing: Config → Costing · fuel → "Fetch this week's DESNZ price now"
   (admin token). The widget should read the DESNZ price with "£… / L ex-VAT" beside it
   and "DESNZ weekly road fuel prices (gov.uk)" under it. Then Look-ahead → "check now":
   the status line reads "Road closures (National Highways): checked …" and names the
   week the flags are filtered to. A ROADWORKS flag appears only where a planned closure
   runs within 100 m of a BAKED route and its dates overlap the week — with the demo's
   routes unbaked, expect none until you bake.

7. FIRST LOOK, GB tenant: Dashboard truck-mi and t·mi cards; Routes table "mi (…)";
   Look-ahead expanded row "mi/trip · mi/week · t·mi"; route form "£ per mi"; the target
   rate "£ per mi"; Config → Costing "Running £ / mi"; XLSX headers mi/trip, mi/day, t·mi;
   PDF "MI/TRIP". Basemap select: "Aerial (Mapbox Satellite)", no Estonian orthophoto.
   Submit forecast → vehicle picker: UK names first, no "N3 lorry (BA)…" entries; the
   EN / EU label toggle shows EN only.


WHAT CHANGED, BY H1 ITEM
------------------------
* Diesel index (fuel.py) — a PROVIDER PER COUNTRY behind one interface: EU-27 → the EU
  Weekly Oil Bulletin (unchanged); GB → DESNZ "Weekly road fuel prices": the CSV's URL
  changes weekly, so it is resolved through the gov.uk content API
  (/api/content/government/statistics/weekly-road-fuel-prices → details.attachments[]),
  and the LAST row's ULSD pump price (pence/litre, INCLUDES duty and VAT) is stored as
  £/L; the ex-VAT figure is derived from the row's VAT % (20 if absent) and shown beside
  it. Same background refresh, same last-good-row-on-failure. NO COUNTRY → NO AUTOMATIC
  INDEX: the row is keyed NO_COUNTRY ("--"), typed only; `DEFAULT_COUNTRY = "EE"` is gone
  from fuel.py, costing.py, derived.py, main.py and the widget. The stored column is
  still called `eur_per_l` — it holds the price in the provider's currency (the row says
  which); nothing converts. Widget: provider label from the API, "no country set" wording,
  the fetch button says which series it fetches.
* Road restrictions (restrictions.py) — PROVIDERS = {EE: Tark Tee, GB: National
  Highways}. GB reads the keyless FeatureServer "PublicScheduledRoadClosures" (OGL v3,
  daily, strategic road network only), paged 1000 at a time; a closure that has ENDED is
  dropped, current and FUTURE ones are kept (the look-ahead needs the future). Field
  names from the published schema, matched case-insensitively (scheduledplannedstartdate
  / enddate → the module's date_from / date_to, description, road_number, eventtype,
  natureofworks, formattedeventnumber). Match distance 100 m for NH (30 m for Tark Tee):
  a closure's polyline is the authority's road geometry, not HERE's. A closure is never
  judged as a dimension limit (verdict "unknown", note says why).
  HU4 (your decision): the clash rail raises the flag only when the closure's dates
  OVERLAP THE BUCKET'S WEEK (Mon–Sun); an undated Tark Tee limit always counts; an
  unreadable date never hides a hit. The flag code is now RESTRICTION (was TARK_TEE),
  shown with the provider's word: "TARK TEE" / "ROADWORKS". Endpoints:
  /api/forecast-weeks/restrictions and …/restrictions/refresh (the tark-tee paths stay
  as hidden aliases); /api/lookahead?restrictions_on=0 (tark_tee=0 still accepted);
  `sources.restrictions*` on the page (were `tark_tee*`), plus the provider, its words
  and the week window. Exports print the provider's word. The map's panel heading reads
  the provider's ("Road closures" for NH). The guide documents both providers.
* Vehicles (factors.json) — CO2: every >17 t rigid and >33 t artic entry now carries the
  DESNZ/DEFRA 2026 average-laden factor (0.99773 / 0.93939 kg CO2e/km) with the 0 % and
  100 % laden pair stored beside it (not read by code yet) and its source. ⚠️ Read from a
  SECONDARY copy of the 2026 set on 26 Sep (gov.uk is blocked from the sandbox) — the
  file says "VERIFY against the gov.uk flat file" on every entry; a carbon figure on a
  stand should wait for that check. Two UK truck mixers added ("Truck mixer 8 m³ (32t)"
  18 t / 7.5 m³, "Truck mixer 6 m³ (26t)" 14.4 t / 6 m³ — payloads labelled ASSUMPTION
  with the derivation). New `vehicle_sets` block: per country, `lead` (the pickers'
  first group) and `hide` (never offered to that tenant); GB leads with the UK trade
  names and hides the four EU N-category entries and the 7.5 t. NOTHING is renamed or
  removed — a hidden vehicle still resolves on an existing line or baked route, and the
  pickers keep a hidden value visible when it is the current one. /api/meta carries
  `hidden_vehicles`; the EU label toggle is hidden for GB.
* Aerial: the staff app offered "Estonia ortho (Maa-amet)" to EVERY tenant (the 26 Sep
  audit note said it was already gated — it was on the map only). Now per country:
  Maa-amet for EE only; for GB the Mapbox satellite styles are labelled "Aerial (Mapbox
  Satellite)" / "Aerial with roads", on the app and the map.
* km / miles (HU5, your decision: per tenant) — `tenant.distance_unit` "km" | "mi" on
  the tenant block (validated, defaults km, exported in the package). Everything is
  STORED and COMPUTED in km; the app, the map and the XLSX/PDF convert at the display
  boundary (distances ÷ 1.609344, t·km → t·mi, km/h → mph; a per-km RATE × 1.609344 →
  per mile). A per-distance rate TYPED in miles (route form, target rate, the running
  coefficient) is converted back to per km before it is saved. Not converted, on purpose:
  the CO2 factor (kg CO2e per km — it is defined per km), L/100 km (a model coefficient),
  the config's avg haul speed km/h and the zone speed inputs (config values; their
  displays do convert), and the diagnostics' "Live km".
* Mapbox: `config.MAPBOX_TOKEN_DEFAULT` now equals the token in map/config.js (the
  rotated one); the revoked token is gone from the code. Asserted equal.
* Time zone: GB → Europe/London was already in here_routing.COUNTRY_TZ; asserted.
* Demo tenant v1.1 (tools/make_demo_tenant.py): GB, GBP, MILES; a GB fair-price
  coefficient set in £ WITH SOURCES — driver £24/h derived from ONS ASHE 2025 median
  HGV pay £16.25 (via DfT Road Freight Statistics 2025; RHA Pay Report 2026 medians
  quoted beside it) with an ASSUMED on-cost multiplier; vehicle standing £13/h from an
  ASSUMED £150k vehicle; running £0.12/km ASSUMPTION (the RHA 78.21 p/mile figure
  includes fuel and is not used); margin 8 % ASSUMPTION; rigid consumption derived from
  the 2026 CO2 factors (31 L/100 km empty); no thaw season. The factors.json SEED keeps
  the Estonian set (with the derivation note updated), so an EE tenant's model does not
  move; only the demo carries the GB set.
* Probes: /api/admin/diagnostics/fuel-index (new) and a provider-aware
  /api/admin/diagnostics/restrictions (the NH branch shows the raw property names, the
  mapped dates, the paging flag and a coordinate before/after normalisation).


TESTS (sandbox; counts are after the rebrand zip → after this zip)
-------------------------------------------------------------------
Stubbed suite (16 py + 4 js): 3,295 expected → 3,402 passed / 1 failed here — the one
is the brand-folder check (frontend/brand/ was not in the sandbox; green once the assets
zip is applied). NEW: backend/tests/test_h1_uk.py, 56 assertions — the acceptance
criterion: the demo tenant imported into an empty tenant, every JSON value of 12 GB
pages and both exports (XLSX read back with openpyxl, PDF with pdftotext) checked for
any Estonian term, any EU-bulletin term, "€" and an "EE" country value; the providers;
the units; the vehicle set and CO2 factors; the token; the probes.
  test_costing 106 → 122 · test_lookahead 244 → 249 · test_modus 171 → 180
  parse_frontend 386 → 394 · parse_map 518 → 519 · test_week1 318 → 319
  test_costlines 48 · test_fairprice 47 (both narrowed to explicit EE, unchanged counts)
http_smoke.py (real FastAPI + TestClient in a venv): 78 → 81 / 0 (GB provider on the
layers endpoint, DESNZ named on /api/fuel-index with the typed placeholder as the index,
the restriction status names ROADWORKS, the pre-H1 alias path answers, hidden_vehicles
and miles on /api/meta).
Narrowed, never deleted: test_costing / test_fairprice / test_costlines / test_lookahead
now model an ESTONIAN tenant explicitly (they relied on the silent EE fallback);
test_modus §6 GB assertions are REVERSED (GB has both providers now); the "Modus scan"
skips the delivery note (it has to say what was renamed).

WHAT THIS DID NOT TEST — say it out loud
----------------------------------------
1. gov.uk and the National Highways FeatureServer: never called. The DESNZ CSV column
   names and the content-API attachment shape, and NH's field names and paging flag,
   come from published schemas / the 26 Sep research. Action 5's probes are the check.
   If the CSV's headers differ, parse_desnz_csv() matches by text and fails loudly with
   the header row in the error — it never returns 0.
2. Postgres: the four-column guard on fuel_index is standard ADD COLUMN IF NOT EXISTS
   and was run on SQLite only.
3. Miles in a real browser: the app's conversions are asserted at source and rendered
   by the render harness with a km fixture only; nothing was viewed. First-look item 7.
4. The DESNZ 2026 CO2 figures against gov.uk (see Vehicles above).
5. A real NH closure geometry against a real HERE polyline at 100 m — the matching maths
   is the Tark Tee one, exercised with fixtures.
6. The regenerated demo package on Render (the import command in action 3).

DELIBERATELY LEFT OUT (after 15 Oct, or a decision)
---------------------------------------------------
* Street Manager (local roads: SNS push receiver), TfL, D-TRO, OS layers — as planned.
* CO2 per leg from the laden/empty pair (stored, not read).
* GB fair-price coefficients in the factors.json SEED (only the demo carries them). A
  new GB tenant created from the seed would start on the Estonian benchmarks; say if the
  seed should carry a per-country set too.
* mpg for the consumption coefficients; per-USER units (needs G3).
* The `modus_*` storage keys and Render service names (unchanged, on purpose).


CODESPACE COMMANDS
------------------
Upload this zip as one file, after the rebrand zip is committed. Then (check the name
with `ls *.zip` first):

  unzip -o wayscope-h1-uk-0929.zip && rm wayscope-h1-uk-0929.zip
  git add -A && git commit -m "H1 UK localisation: DESNZ diesel, National Highways closures, UK vehicles + DESNZ 2026 CO2, aerial, miles per tenant, probes" && git push

If the push is rejected as non-fast-forward:
  git pull origin main --no-rebase --no-edit
  git push
