# Carbon planner — build note (10–11 Oct 2026, branch `claude/carbon-planner`)

Built from `carbon-build-brief-1010.md`. Copy this file into the Claude project's notes.
**Status: phases 1–4 (engine, scenario API, Carbon page, demo data) and the review fixes on the branch. Phase 5 is after the show.**

## What it is for
Carbon forecasting for strategic planning, to REDUCE carbon: which planning decisions move the
most tCO2e on haulage and bulk materials, tested as an alternative beside the approved plan.
It is a planning estimate, not a National Highways Carbon Tool return, and every screen says so.

## Phase 1 — the engine (`backend/carbon.py`, `backend/tests/test_carbon.py`)

### Calculation rules (mirrored from the NH Carbon Tool v2.7 workbook)
| Rule | Formula | Where in the tool |
|---|---|---|
| Material | quantity × conversion × factor (kg/t ÷ 1000) | Bulk Materials M9 |
| Tool transport | one-way km × tonnes × conversion × (laden + unladen) ÷ 2 × **2** | Bulk Materials Y9, Z9 |
| Allocation | % to Fencing / Drainage / Road Pavements / Civils Structures / Waste, rest Not Allocated; **over 100 % is an error** | cells P–U, S2 "err" |
| Double count | earthworks excludes bulk materials: each line on ONE sheet by its material class (soils → Earthworks, the rest → Bulk Materials) | Earthworks sheet heading |
| Units | miles × 1.609344 = km; km stored; shown in the tenant's unit | the tool's converter cell |

**Wayscope's headline transport figure stays the vehicle-km method** the Dashboard and the map
already use (trips × routed km of both legs × the vehicle's kg CO2e per vehicle-km). The tool's
basis and the DESNZ 2026 class tonne-km figure are returned beside it, labelled, never added in.
The baseline reads `costlines.lines()` (the Dashboard's own read), so the Carbon page and the
Dashboard show one transport number per line (asserted, and over HTTP on the note's R001 example).

### Factors (`backend/factors.json` → new `carbon` block) — **factors.json changed: merge, do not overwrite**
- Material use and waste disposal, Construction, from the gov.uk 2026 flat file v1.2 (revised
  31 Jul 2026), each with its row ID, year, scope, GWP basis (AR4) and status VERIFIED.
- UK electricity 2026: generation 0.13096 + T&D 0.01299 (+ WTT 0.03682 + 0.00359).
- DESNZ 2026 tonne-km benchmarks (rigid >17 t 0.17256, artic >33 t 0.07835) and the published
  per-vehicle-km rows, so a vehicle factor equal to one is labelled VERIFIED with its ID.
- The NH Carbon Tool v2.7 basis read from the workbook's own cells (G7, G11; Y9/Z9 formulas).
- The diesel `_emissions_basis` notes now say **verified 10 Oct 2026 against the flat file v1.2**
  with the row IDs. **Rigid 7.5t: 0.55 → 0.49944** (2026 class figure; pair 0.46656 / 0.54675).
- `fuel` on every vehicle: `diesel` on the twelve existing, `electric` on two NEW keys:
  "Artic Tipper (44t) — electric" and "Rigid 8-wheeler (32t) — electric" (nothing renamed).
- `carbon_material` on every material category (soils, aggregates, concrete, metals, average).
- No ICE factor anywhere (ICE commercial use ended 30 Sep 2026).

### Electric lorries
- The Government 2026 set has **no electric HGV factor**. Electric kg CO2e/km = kWh/km × UK
  electricity (generation + T&D) = 1.25 × 0.14395 = 0.17994, derived in ONE place
  (`conversions._emissions`), which the costlines, the route analysis and the map's flat factors
  all call. Well-to-wheel (0.23045) is shown separately; the diesel figures are tank-to-wheel.
- kWh/km 1.25 is DERIVED from ZEHID 2026 (4,500 MWh over 3.60 million km, mixed fleet).
- Payload = the diesel twin's less 3.5 t (ASSUMPTION, ZEHID's range 1.5–3.5 t). The draft +2 t
  zero-emission allowance is NOT applied (in-force status unconfirmed; never above 44 t).
- Battery 500 / 400 kWh usable and 350 kW charging are ASSUMPTIONS, editable per profile.
- Fleet: the battery starts the shift full; a trip must fit the battery; energy beyond one
  battery is topped up at the charger's power, and those minutes come out of the shift.
- The electric profiles are **scenario-only**: hidden from the forecast pickers, and they read
  the diesel twin's baked distances (`geometry_twin`).

### Decisions taken (mine, under the brief)
- **No re-import needed for the live demo.** The engine reads the live `carbon` block, electric
  profiles and material mapping, falling back to `factors.json` key by key (the fair-price
  pattern). So the page works on today's live demo row, which predates the block.
- **An alternative never drops a line.** Where the alternative's vehicle or route has no baked
  geometry, the baseline vehicle's km is used and the line is flagged; a dropped line would read
  as a saving. A line unbaked in the baseline stays excluded from transport in both.
- **Disposal lines** are recognised by the destination location's type (Landfill, Tip,
  Soil recycling …; list in `carbon.disposal_loc_types`): they carry the waste factor, not a
  material-production factor.
- Per-driver deltas: each driver's levers applied ALONE to the baseline, ranked by tCO2e moved;
  the interaction (combined minus the singles) is reported, not hidden.

### Tests
`test_carbon.py` 126 / 0, every figure hand-worked in its comment (the note's worked example:
19.20 t vehicle-km, 261.82 t tool basis, 90.10 t tonne-km). Narrowed: `test_week1` vehicle count
12 → 14 (plus a check that the two additions are the electric twins).

## Phase 2 — the scenario API (`POST /api/carbon/scenario`, in `backend/main.py`)
Body (all optional): `status` (Approved by default; Pending / Rejected / All), `from_month`,
`to_month`, `baseline` (levers describing today's plan), `alternatives` (up to six, each
`{name, levers}`), `spend_gbp_m` (typed programme spend, for tCO2e per £m) and `allocation`
(`{category: {Fencing: %, …}}`). A lever is `{driver, scope, …}`, where `scope` is `{category}`
or `{route_id}` or empty (every line):

| driver | values | what it changes |
|---|---|---|
| material | `epd: {kg_per_t, source}` or `reused: true` | the material factor (EPD needs its source) |
| recycled | `pct` 0–100 | primary/closed-loop blend, only where both are published |
| source | `to_route` (same destination) or `distance_pct` | supplier, or a typed % of the baked distance (flagged) |
| route | `alt_index` | a baked HERE alternative (unbaked → flagged, unchanged) |
| vehicle | `vehicle` | payload → trips, factor, cycle |
| fuel | `electric` / `diesel` | swaps to the profile's electric variant and back |
| disposal | `to_route` (same origin) and/or `to` (landfill, closed_loop …) | tip vs recycling site |

Answer: the baseline and each alternative (totals, by category / route / month, the two NH
sheets, allocation, benchmarks, fleet), each alternative's delta and **drivers ranked by tCO2e
moved** with the interaction, the diesel-vs-electric fleet comparison, the options the page can
offer (with place names, never bare ids), every factor's provenance, the methods, the known
limits and the Planned items. A rule the engine refuses is a 400 with the reason.

**Gating:** any signed-in code, filtered like `/api/costing/lines` (a team code sees only its own
lines). This is how the staff reads (Dashboard, Forecasts, Look-ahead) are gated; the nav's group
structure is frozen by assertion, so the page sits in the Plan group beside them.

**Tests:** `test_carbon.py` 136 / 0 (adds the endpoint called as a function: 401 without a code,
the four 400s, the answer unchanged, and a source check that `_require_access()` comes first).
`http_smoke.py` 92 → 103: 401 without a code; the demo's 72 approved line-months with the unbaked
network excluded from transport; the North Team code sees only its lines; the 400s; then R001
baked BY HAND with the note's illustrative 18.4 + 19.1 km gives **75.99 t** (the note's worked
example) and the same figure as `/api/costing/lines`, with the tool basis 261.82 t beside it.

## Phase 3 — the Carbon page (`frontend/index.html`, Plan → **Carbon planner**)
- **Left: the alternative's controls.** Per material category: recycled content (slider; disabled with
  the Government file's reason where no closed-loop or primary row exists), a supplier EPD (value +
  reference, both required), the published re-used row where one exists, the vehicle, and a typed
  source distance (50–150 % of the baked distance, flagged as typed). Electric lorries where a variant
  exists. Programme spend in £m (for tCO2e per £m). Per route, folded away: another supplier to the
  same destination, a baked HERE alternative route, another destination (tip vs recycling site) and
  the disposal route.
- **Right: the answer.** Baseline (the approved plan) beside the alternative, split into material,
  transport and disposal, with the delta and the %. **What moves carbon most**: each decision ranked
  by the tonnes it moves on its own, with the interaction and any flag in words. Benchmarks (kg per
  tonne delivered; kg per t·km against the DESNZ 2026 class average, "X % below the national
  average"; laden share; zero-emission deliveries with NH's 2040 target; t per £m with NH's 210 → 148).
  **Three ways to count the same haul**: Wayscope's per-vehicle-km headline, the NH Carbon Tool basis
  "shown for comparison", and DESNZ tonne-km, with the stand line under it. **Diesel or electric — the
  same tonnage**: lorries at the peak month, trips, kWh, tCO2e, payload, battery, charger, range,
  charges. By material with the NH sheet. **Factors used**: each with its status chip, value, source,
  year and gov.uk row ID; every figure carries the same text on hover.
- **Bottom:** the **Planned — not built yet** panel (electricity price index, charging-site map, charger
  sizing, battery degradation, plant fuel, the .rct export) with no figures, and the known limits.
- One read only (`POST /api/carbon/scenario`), debounced; the page does no carbon arithmetic.
  Distances and per-distance figures go through the tenant's unit (the demo reads miles).
- Guide: three steps for the page (demo tenant only). Config → Vehicles shows "derived: kWh × UK grid"
  in an electric profile's kg CO2e/km cell. Electric profiles never reach the forecast pickers.
- **Side effect:** `frontend/index.html` grows from 492 KB to 525 KB, past in-browser Babel's 500 KB
  mark, so the browser console prints "[BABEL] Note: The code generator has deoptimised the styling…".
  It is a notice, not an error: Babel only switches to compact output. The page works. (The
  single-file rule and the six-script-tag assertion rule out moving the page into its own file.)

**Tests:** `parse_frontend.js` 435 → 456 (nav and switch, one POST read, no carbon arithmetic or
factor literal, the tenant's unit, the Planned panel and limits, provenance on hover, all seven
drivers, the banned words, no team id, the electric wording, the guide anchors). `render_frontend.js`
104 → 114 (the page in the rail, and POPULATED from `fixtures/carbon_scenario.json`: 157.0 t vs 32.8 t,
the drivers in order, the three methods, 300 → 342 trips, no undefined/NaN).

**Checked in a real browser (local, 11 Oct):** the app on this branch with the demo package imported
(its config row has no carbon block, like the live demo) and route distances seeded by hand (straight
line × 1.3; HERE was not called). Signed in as a planner: the page loads, electric + 30 % recycled small
aggregate moves the plan −1,294.5 t (−17.6 %), ranked electric first; miles shown correctly.

## Phase 4 — demo data (`backend/tools/make_demo_tenant.py` → `demo/uk-corridor.package.json`)
- **A landfill-vs-reuse choice.** Two fictional sites near Langton Compound: "Wolds Link Inert Landfill
  (fictional)" (type Landfill) and "Wolds Link Soil Recycling Hub (fictional)" (type Soil recycling), a gate
  each; R019 Langton Compound → landfill with four approved months of surplus cut (27,800 t, Central Team,
  typed actuals in Sep/Oct weeks 1–2, September week 3 confirmed, like every other line); R020 to the hub
  with a route and no forecast — the alternative. On the page: Per route → R019 → "Send instead to" the hub
  moves **−515.4 t** (27,800 t × (1.01398 − 19.55376) kg/t), ranked as the disposal decision.
- **Materials and recycled options** come from the factor block (aggregates, concrete and metals take a
  recycled share; soils and the average class say why not). **Electric:** the package carries the three
  scenario-only electric profiles; Electric lorries switches every demo line (tippers and flatbeds).
- **Deterministic and additive.** The new rows come from their own seeded generator placed after every
  existing draw. Regenerated and diffed: every row that was in the package before is identical apart from
  regeneration timestamps (`created_at`, `updated_at` …); the factors row gains the carbon block, the
  electric profiles and `carbon_material`, with the tenant settings and the fair-price block unchanged.
- **Pins narrowed (not deleted):** `test_modus` 11 → 13 locations, 18 → 20 routes, 74 → 78 forecasts
  (72 → 76 approved), 14 → 16 gates, `/api/meta` 18 → 20 routes; `test_h1_uk` 14 → 16 gates, the show week
  18 → 19 lines and 36 → 38 typed actuals, and the "VERIFY" note pin **reversed** (it now asserts the
  verified wording and the row IDs); `http_smoke` the same counts and 324 → 342 weeks. Added: two
  `test_modus` checks (the landfill/hub choice; the carbon block and electric profiles in the package) and
  two `http_smoke` checks (the landfill line on the Waste sheet at 543.595 t; the hub moves −515.406 t).

### Re-importing the demo — your decision, with its cost
**The Carbon page does NOT need a re-import.** On today's live demo it reads the carbon block, the electric
profiles and the material mapping from `factors.json` (checked locally on a database holding the old
package). What a re-import adds is the landfill/hub example and the electric profiles in Config.
**The cost:** `replace=1` deletes every baked route (the package carries no geometry), so every route reads
UNBAKED and every CO2e figure, the map's carbon and the Look-ahead's cycles disappear until Routes → Bake all
is run for Artic Tipper (44t) and Artic Flatbed (44t) (HERE calls; 20 routes × 2 vehicles × 2 legs, plus the
alternatives). The standing rule in the notes (todo A12) says do not re-import before the show.
**Recommendation: do not re-import before 15 Oct.** Show the disposal lever on any soil line instead, or
re-import after the show.

## Review fixes (11 Oct) — an independent adversarial review of the engine
Three reviewers (formulas, edge cases, brief compliance) raised 30 findings; each was re-checked by a
separate verifier that tried to refute it: **26 confirmed**, 4 judged design choices (fixed anyway).
Every fix has an assertion in `test_carbon.py` (175 / 0). The ones that changed figures or behaviour:
- **A disposal route with no published factor counted as zero** and topped the ranking (soil "open-loop"
  read −113 t). Now: a lever asking for it is skipped with a note; a site whose factor is unpublished is
  flagged NO_DISPOSAL_FACTOR and its tonnes reported; the page lists only the published routes.
- **A disposal lever hit delivery lines** (quarry aggregates lost their production carbon). It now applies
  only to lines going to a tip or recycling site. An unscoped EPD is refused (one product's figure).
- **Like with like:** a swap to a route whose return leg is not baked used to halve transport; the loaded
  leg now stands in (RETURN_STAND_IN). A swap to an unbaked route used R1's own km under R5's name; it is
  now left out and flagged (ROUTE_SWAP_NOT_BAKED); the page marks such routes "not baked".
- **Electric:** a trip needing more than one battery was credited at electric rates and dropped from the
  lorry count; it now stays diesel (flagged) and is left out of BOTH columns of the comparison. Charging is
  simulated trip by trip (stops were undercounted); "daily range" is renamed range per charge.
- **Benchmarks:** lines counting their loaded leg only are left out (and counted); tonne-km references are
  read per size class (a 7.5 t rigid against 0.54001, not the > 17 t 0.17256) — three more published rows.
- **Provenance:** the factors list now includes what the alternatives used (a recycled blend DERIVED, a typed
  EPD as ASSUMPTION — the brief allows only the three statuses); a profile's own kWh/km is an ASSUMPTION.
- **Robustness:** malformed levers and allocations are a 400, never a 500 or a NaN; `config.validate` refuses
  every carbon-block shape that would break a scenario; a partial live block is accepted (merged); an explicit
  null in the live document switches a figure or category off. Allocation may name a route (a row) as well as
  a category. Deltas are taken on unrounded sums (a lone lever no longer shows a ±0.001 "interaction").
- **Speed on the live demo:** the live row has no carbon block, so the engine re-read `factors.json` for every
  line — about 2,000 parses and 4.5 s per scenario. The file is now parsed once and cached until it changes.
- **Electric variants:** a third, "Artic Flatbed (44t) — electric", so the demo's flatbed lines can switch too
  (the mixers and the smaller rigids still have none). `test_week1` count narrowed 14 → 15.

## Known limits (also on screen)
Government material factors are coarser than ICE; concrete is one generic figure (enter a
supplier EPD); electric kWh/km is derived from a mixed-fleet programme; the 2 t ZEV allowance is
draft; no electric HGV factor exists in the Government set; Material Use is AR4 GWP while
transport and fuel are AR5. Access is still shared codes (no per-person identity until G3) — do
not call any deployment secure.

## Only tested against stubs
Everything in phases 1–2 runs on a scratch SQLite with hand-seeded route geometry: no HERE bake,
no browser. The HTTP checks run FastAPI's TestClient, not Render. The factor values were read from the downloaded gov.uk file and NH workbook kept in
`notes\evidence\carbon-1009\`, not fetched live during the tests.
