# Carbon planner — build note (10–11 Oct 2026, branch `claude/carbon-planner`)

Built from `carbon-build-brief-1010.md`. Copy this file into the Claude project's notes.
**Status: phase 1 (engine) on the branch. Phases 2–4 follow on the same branch; phase 5 is after the show.**

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

## Known limits (also on screen)
Government material factors are coarser than ICE; concrete is one generic figure (enter a
supplier EPD); electric kWh/km is derived from a mixed-fleet programme; the 2 t ZEV allowance is
draft; no electric HGV factor exists in the Government set; Material Use is AR4 GWP while
transport and fuel are AR5. Access is still shared codes (no per-person identity until G3) — do
not call any deployment secure.

## Only tested against stubs
Everything in phase 1 runs on a scratch SQLite with hand-seeded route geometry: no HERE bake,
no browser. The factor values were read from the downloaded gov.uk file and NH workbook kept in
`notes\evidence\carbon-1009\`, not fetched live during the tests.
