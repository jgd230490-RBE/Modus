/*
 * Assertions for the public route map after its migration off map/data/a1_data.js.
 *
 * Extracts every inline <script> block from map/index.html, checks each is valid
 * JavaScript, then asserts at source level that the migration actually happened and that
 * nothing which had to survive was lost.
 *
 * NOT covered: anything needing a browser. Mapbox layer rendering, whether the fetch
 * succeeds, and how the map looks are unverified here.
 *
 * Run:  node backend/tests/parse_map.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const FILE = path.join(ROOT, "map", "index.html");
const html = fs.readFileSync(FILE, "utf8").replace(/\r\n?/g, "\n");   // 9 Oct 2026: a Windows checkout (core.autocrlf) hands us CRLF; the regexes expect LF

let pass = 0;
const fail = [];
function ok(label, cond, extra) {
  if (cond) pass++;
  else fail.push(label + (extra ? "  " + extra : ""));
}
// 12 Oct 2026 (fix pass): the sandboxes at the end resolve promises; the summary waits for these
const ASYNC_PINS = [];

// ---- every inline script must be valid JS ------------------------------------
const blocks = [];
const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
let m;
while ((m = re.exec(html)) !== null) blocks.push(m[1]);
ok("found the inline script block(s)", blocks.length >= 1, `got ${blocks.length}`);

blocks.forEach((b, i) => {
  if (!b.trim()) return;
  try {
    new Function(b);
    pass++;
  } catch (e) {
    fail.push(`inline script #${i + 1} is not valid JS  ${e.message}`);
  }
});

const src = blocks.join("\n");
// comment-stripped, so an assertion cannot pass by matching the prose that explains
// why something was removed
const code = src
  .split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n")
  .replace(/\/\*[\s\S]*?\*\//g, "");

// ---- the static file is gone -------------------------------------------------
ok("the a1_data.js script tag is removed", !/src=["']data\/a1_data\.js["']/.test(html));
// G2 (16 Sep): the alignment and chainage are TENANT DATA from GET /api/public/alignment
ok("G2: no static alignment file is loaded", !/src=["']data\/alignment\.js["']/.test(html));
ok("G2: no static chainage file is loaded", !/src=["']data\/chainage\.js["']/.test(html));
ok("G2: the overlay is fetched once from the API and awaited in style.load",
  /const OVERLAY_READY = \(async \(\) =>/.test(code) && /await OVERLAY_READY;/.test(code)
  && /\/public\/alignment/.test(code) && /window\.applyOverlayPackage\(o\)/.test(code));
ok("nothing reads window.a1_data any more", !code.includes("window.a1_data"));
ok("the file itself has been deleted",
  !fs.existsSync(path.join(ROOT, "map", "data", "a1_data.js")));
ok("G2: no map/data directory ships at all",
  !fs.existsSync(path.join(ROOT, "map", "data")));

// ---- data now comes from the network -----------------------------------------
ok("routes and nodes are fetched from the API", code.includes("/public/map-data"));
ok("the fetch result is pushed into the map source", /getSource\(['"]routes-source['"]\)/.test(code));
ok("init waits for the map to load", code.includes("map.once('load', initNetwork)"));
ok("a failed fetch is surfaced, not swallowed", /Could not load the route network/.test(src));
ok("an empty network tells the user to bake", /Bake the network/.test(src));

// ---- temp haul layer is BACK (Phase 4) ---------------------------------------
// Phase 2 asserted this layer was gone and its toggle disabled, because the network held
// no geometry for it. Phase 4 gives it real drawn polylines, so those assertions are
// reversed rather than deleted — the point they were making (never draw a line the data
// does not support) is now enforced from the other side.
ok("the old placeholder layer id is still gone", !code.includes("temp-lines'"));
ok("a temp-haul layer is drawn from the API's own features",
  code.includes("'temp-haul-lines'") && code.includes("'Temp Haul Track'"));
ok("it reads from routes-source, not a static file",
  /id: 'temp-haul-lines', type: 'line', source: 'routes-source'/.test(code));
ok("its toggle is enabled again", !/id="layer-temp"[^>]*disabled/.test(html));
ok("and wired to a handler", /id="layer-temp"[^>]*onchange="toggleTempHaul/.test(html));
ok("the '(Phase 4)' placeholder label is gone from the toggle",
  !/Temporary haul <span[^>]*>\(Phase 4\)/.test(html));
ok("temporary haul is dashed — it is not the surveyed network",
  /'line-dasharray': \[2, 1\.4\]/.test(code));
ok("haul roads are excluded from the zone overlay so they are not drawn twice",
  code.includes("['!=', ['get', 'kind'], 'haul_road']"));
ok("clicking one opens its own popup", code.includes("map.on('click', 'temp-haul-lines'"));
ok("the popup says the speed is assigned, not measured",
  /Assigned, not measured/.test(src));
ok("and calls out a haul road with no speed set",
  /No speed assigned/.test(src));
ok("visibility survives a basemap switch by reading the checkbox, not a variable",
  code.includes("function tempHaulVisible()") && code.includes("tempHaulVisible() ? 'visible' : 'none'"));

// ---- leg filter replaced by discipline ---------------------------------------
ok("the legacy leg filter is gone", !/id="filter-leg"/.test(html));
ok("a discipline filter replaces it", /id="filter-discipline"/.test(html));
ok("discipline filtering is a membership test, not an equality",
  code.includes("['in', disc, ['get', 'disciplines']]"));
ok("the filter disables itself when no forecasts exist",
  code.includes("No approved forecasts yet"));

// ---- capacity KPI ------------------------------------------------------------
ok("max_loads is no longer summed", !code.includes("max_loads"));
// 2026-09-02 (§9): the Trips/day CARD no longer reads the baked cycle's trips_per_day —
// it is the forecast's vehicle-loads per working day, from /api/public/month-kpis.
// trips_per_day survives on the route popup / drawer, which is where a cycle figure
// belongs.
ok("the old 'capacity' card is gone", !/id="kpi-capacity"/.test(html));
ok("the baked cycle's trips_per_day no longer feeds any KPI card",
  !/function calculateKPIs[\s\S]{0,6000}trips_per_day/.test(code));

// ---- layer filters were repaired ---------------------------------------------
// the casing layers filtered on `route_leg`, a property that never existed in the data,
// so they matched nothing until applyFilters() overwrote the core layers
ok("no layer filters on the non-existent route_leg property", !code.includes("route_leg"));
ok("layers filter on the type property instead",
  code.includes("['==', ['get', 'type'], 'Inbound Highway']"));

// ---- Phase 3: the zone overlay -------------------------------------------------
ok("zones are fetched from their own endpoint", code.includes("'/zones'"));
ok("the overlay does NOT ride on /public/map-data",
  !code.includes("zones-source', { type: 'geojson', data: a1_data"));
ok("a zones source and fill layer exist",
  code.includes("zones-source") && code.includes("'zone-fill'"));
// 12 Oct 2026 (D24) — REVERSED: the zones toggle is no longer ONE switch. The group master
// keeps its id (layer-zones) and under it sits one checkbox per kind.
ok("D24: the sidebar's zones toggle is the group master, with one checkbox per kind under it",
  html.includes('id="layer-zones"')
  && ["closure", "works", "weight_limit", "haul_road", "other"].every(k => html.includes(`id="layer-zone-${k}"`))
  && (html.match(/onchange="toggleZoneKind\('/g) || []).length === 5);
ok("the toggle is wired to a handler", code.includes("function toggleZones") && code.includes("function toggleZoneKind(kind, on)"));
// 12 Oct 2026 (D24) — REVERSED: the colour says what KIND of zone it is, not whether the
// router avoids it (that is still said in the popup). Amber #D97706 for a closure per
// colour-system-1010.md line 24; red is kept for a cap breach or a clash.
ok("D24: zones are coloured per KIND, not by affects_routing",
  !code.includes("['case', ['get', 'affects_routing']")
  && /const ZONE_FILL_COLOUR = \['match', \['get', 'kind'\], 'closure', ZONE_AMBER, 'works', ZONE_AMBER_LIGHT, 'weight_limit', ZONE_INK, ZONE_GREY\];/.test(code)
  && code.includes("const ZONE_AMBER = '#D97706'"));
ok("zones re-add after a basemap switch, like every other layer",
  code.includes("if (ZONES.loaded) ensureZoneLayers(); else loadZones();"));
ok("the overlay follows the forecast timeline", code.includes("applyZoneMonth"));
ok("closing the timeline restores every zone", code.includes("applyZoneMonth(null)"));
ok("date filtering compares YYYYMMDD integers, not strings",
  code.includes("function dnum") && code.includes("function monthSpan"));
ok("an open-ended end date sorts last rather than being special-cased",
  code.includes("99999999"));
ok("only active zones are drawn", code.includes("z.active && z.geometry"));
ok("clicking a zone explains whether routing is affected",
  code.includes("Routing avoids this area") && code.includes("Advisory only"));
ok("a missing zones endpoint is not surfaced as a page error",
  code.includes("console.warn('zones unavailable'"));

// ---- things that must NOT have been broken -----------------------------------
for (const keep of [
  ["rail-alignment", "the rail alignment layer survives"],
  ["chainage-global", "the chainage layer survives"],
  ["maaametOrthoStyle", "the Maa-amet orthophoto basemap survives"],
  ["route-forecasts", "the forecast overlay still reads the public feed"],
  ["openRouteAnalysis", "the route analysis drawer survives"],
  ["toggleTimeline", "the playable timeline survives"],
  ["filterByNode", "click-a-node-to-filter survives"],
]) {
  ok(keep[1], code.includes(keep[0]));
}

// ---- Phase 2.5a: restrictions, Street View, KPI cards, animation, zoom ------
ok("Tark Tee layers are fetched through OUR backend, never straight from tarktee.ee",
  code.includes("CONFIG.API_BASE + '/restrictions'") && !code.includes("tarktee.ee/tarktee/rest"));
ok("the layer catalogue comes from the server, not a copy in this file",
  code.includes("'/restrictions/layers'"));
ok("restriction toggles are built from that catalogue",
  code.includes("function buildRestrictionToggles"));
ok("restrictions survive a basemap switch from cached data, without re-requesting",
  code.includes("if (RESTR.data) ensureRestrictionLayers(); else loadRestrictions();"));
ok("a weak bridge's load class is shown verbatim and NOT converted to tonnes",
  src.includes("A load class, not tonnes"));
ok("the popup LEADS with the restriction value, not just its existence",
  code.includes("p._headline || p._label"));
ok("colours come from the server catalogue, not constants in this file",
  code.includes("RESTR.colour[l.key] = l.colour") && !code.includes("RESTR_NOTE_COLOR"));
ok("legend dots use the same colour the layer paints with",
  code.includes("background:' + l.colour"));
ok("features carry their own colour so map and legend cannot drift",
  code.includes("['coalesce', ['get', '_colour']"));
ok("the value is labelled ON the map from zoom 11, not only in a popup",
  code.includes("'restriction-labels'") && code.includes("['get','_limit']"));
ok("closures and causes are shown in words", code.includes("p.effect") && code.includes("p.cause"));
ok("the source's own free text is passed through", code.includes("p.extra_info"));
ok("the date window is shown so a stale record is visible as stale",
  code.includes("p._from") && code.includes("p._to"));
ok("the overlay is declared advisory - the router is not given it",
  /router is not given this data|Advisory/i.test(src));
ok("restrictions are off by default so they do not bury the haul routes",
  !/id="restr-[a-z_]+" checked/.test(html));

ok("street view goes through our proxy so the Google key stays server-side",
  code.includes("CONFIG.API_BASE + '/streetview") && !code.includes("maps.googleapis.com"));
ok("the FREE metadata call is made before any billable image request",
  code.indexOf("/streetview/meta") > -1 &&
  code.indexOf("/streetview/meta") < code.indexOf("/streetview?lat="));
ok("no imagery means no <img> at all, not a grey placeholder",
  code.includes("if(!meta || !meta.available) return;"));
// 2026-09-08 (§A): the marker's pop.on('open') is gone with the marker. The lookup is
// still lazy — it happens in the layer's click handler, i.e. only when a popup is
// actually opened — so the assertion is narrowed to the property that mattered: the
// lookup is NOT on the load path.
ok("imagery is only looked up when a popup is actually opened",
  /map\.on\('click', 'locations'[\s\S]{0,700}svIntoPopup\(svId/.test(code)
  && !/features\.forEach[\s\S]{0,400}svIntoPopup/.test(code));
ok("a large offset between the gate and the nearest panorama is disclosed",
  src.includes("nearest imagery is"));

ok("the KPI cards actually exist in the page now",
  /id="kpi-routes"/.test(html) && /id="kpi-vehicles"/.test(html)
  && /id="kpi-trips"/.test(html) && /id="kpi-material"/.test(html));
ok("⭐ the KPIs are ON THE MAP, not in the sidebar", /id="kpi-hud"/.test(html));
ok("and are positioned over the map canvas", /#kpi-hud\{[^}]*position:absolute/.test(html));
// 2026-09-07: moved to the TOP-LEFT of the map pane. The old assertion pinned
// top:112px right:10px, which was exactly the "tucked under the zoom stack" position the
// move exists to leave, so it is REVERSED rather than deleted — it now pins the new
// corner and refuses the old one.
// ⚠️ 2026-10-06 — REVERSED again, not deleted (map redesign, claude/map-redesign-1006.md).
// The 07 Sep floating card (top:14px left:312px, 272px wide, blur + shadow) became a flat
// BAR docked to the top of the map pane, full pane width, 72px tall. The assertion now
// pins the bar and refuses the card.
ok("the KPI bar is docked to the top of the map pane, full width, beside the sidebar",
  /#kpi-hud\{[^}]*top:0;[^}]*left:300px;[^}]*right:0;/.test(html)
  && /#kpi-hud\{[^}]*height:72px/.test(html)
  && !/#kpi-hud\{[^}]*width:272px/.test(html)
  && !/#kpi-hud\{[^}]*backdrop-filter/.test(html)
  && !/#kpi-hud\{[^}]*box-shadow/.test(html));
ok("...and reaches the edge when the sidebar is closed, clearing #menu-toggle",
  /body\.sidebar-closed #kpi-hud\{[^}]*left:0;[^}]*padding-left:176px/.test(html));
ok("the Mapbox zoom stack is pushed below the bar", /\.mapboxgl-ctrl-top-right\{ top:72px; \}/.test(html));
ok("⭐ 2026-10-06: six numbers, the last two CO2e a day and to date",
  /id="kpi-co2-day"/.test(html) && /id="kpi-co2-total"/.test(html)
  && /set\('kpi-co2-day', /.test(code) && /set\('kpi-co2-total', fmtN\(co2ToDate, 0\) \+ ' t'\)/.test(code));
// NARROWED 12 Oct 2026 (the base merge of Track A and Track B): the caption names them as lines "with no stored road
// route", not "unbaked" (the team's word); the behaviour is pinned in the F1 sandbox below
ok("⭐ CO2e sums per line AFTER the same filters, and lines with no stored road route are named, not zeroed",
  /if \(l\.co2_t != null\) co2 \+= l\.co2_t; else co2Unbaked\+\+;/.test(code)
  && /excl\. \$\{noRoute\(co2Unbaked\)\}/.test(code)
  && code.includes("const noRoute = k => `${k} line${k === 1 ? '' : 's'} with no stored road route`;")
  && !/excl\. \$\{co2Unbaked\} unbaked/.test(code) && !/\$\{last\.co2_to_date_unbaked_lines\} unbaked/.test(code));
// 12 Oct 2026 (the base merge; Track B's merge-time item): month-kpis' co2_error reaches the bar
ok("⭐ the figures bar reads month-kpis' co2_error and prints 'carbon could not be read', with a dash, in both carbon cards",
  code.includes("const co2Err = payloads.some(p => p && p.co2_error);")
  && /if \(co2Err\) \{\s*set\('kpi-co2-day', '—'\); set\('kpi-co2-total', '—'\);\s*set\('kpi-co2-day-label', 'CO\\u2082e a day \(carbon could not be read\)'\);\s*set\('kpi-co2-total-label', 'CO\\u2082e to date \(carbon could not be read\)'\);/.test(code));
ok("⭐ CO2e to date follows the sidebar filters through the route's props",
  /\(last\.co2_to_date \|\| \[\]\)\.forEach\(c => \{[\s\S]{0,400}discFilter !== 'ALL' && c\.discipline !== discFilter/.test(code));
// 12 Oct 2026 (B2): ONE carbon fallback (conversions.FALLBACK_KG_CO2E_PER_KM, the published 0.89743) and the
// route drawer reads the SERVER's co2_t from forecast-matrix instead of multiplying its own trips × km × factor
ok("⭐ B2: the map's only emissions fallback literal is the published 0.89743 — no 0.90 / 0.9 remains",
  /vehicle_emissions_kg_co2e_per_km: \{ "_default": 0\.89743 \}/.test(code)
  && !/vehicle_emissions_kg_co2e_per_km: \{ "_default": 0\.9\b/.test(code)
  && !/pick\(F\.vehicle_emissions_kg_co2e_per_km,\s*veh\)\s*\|\|\s*0\.9/.test(code));
// NARROWED 12 Oct 2026 (the review and fix pass): the drawer sums EVERY forecast-matrix row of the route (one row per
// discipline and section) — it read the first row only, under a caption that called it the bar's figure
ok("⭐ B2: the drawer reads co2_t per month from forecast-matrix for EVERY line of the route and sums the baked line-months",
  /const rows=\(mtx\.routes\|\|\[\]\)\.filter\(r=>\(r\.route_id\|\|''\)\.toString\(\)\.trim\(\)\.toLowerCase\(\)===rl\);/.test(code)
  && /rows\.forEach\(rw=>\{[\s\S]{0,400}const co2m=rw\.co2_t\|\|\{\};[\s\S]{0,400}if\(c==null\)\{ unbakedMonths\[k\]=true; \} else \{ co2t\+=c; bakedT\+=mt; co2LineMonths\+\+; \}/.test(code)
  && !/const row=\(mtx\.routes\|\|\[\]\)\.find\(/.test(code)
  && !/trips\*round\*emis\/1000/.test(code) && !/const emis=/.test(code));
// NARROWED 12 Oct 2026 (the review and fix pass): "(est.)" is back on the label, the server's planning-estimate stamp is
// printed under the cards, a failed carbon read says so (it used to blame a missing route), and the wording says
// "no stored road route" instead of the team's word "baked"
ok("B2: no stored route shows a dash and says so, never an estimate; a partly stored window names the months it excludes",
  /card\('—','CO₂e \(est\.\)','no road route stored for this vehicle yet'\)/.test(code)
  && /' · excl\. '\+unbakedM\+' month'\+\(unbakedM>1\?'s':''\)\+' with no stored road route'/.test(code)
  && /Read from the server: the costlines figure the bar above and the Dashboard use, summed over every line on this route\./.test(code)
  && !/The same figure as the bar above and the Dashboard, read from the server\./.test(code)
  && !/route not baked for this vehicle/.test(code));
ok("⭐ the drawer's CO2e card is labelled an estimate and carries the server's planning-estimate stamp (forecast-matrix carbon_stamp)",
  /card\(co2t\.toFixed\(1\)\+' t','CO₂e \(est\.\)'/.test(code)
  && /\(mtx\.carbon_stamp\?' '\+mtx\.carbon_stamp\+'\.':''\)/.test(code));
ok("⭐ a failed carbon read (forecast-matrix co2_error) reads 'carbon could not be read', never 'not stored'",
  /const co2Card=mtx\.co2_error\s*\n\s*\? card\('—','CO₂e \(est\.\)','carbon could not be read'\)/.test(code)
  && /const anyBaked=co2LineMonths>0 && !mtx\.co2_error;/.test(code));
ok("no label in the bar is uppercase microtext", !/\.kpi-label\{[^}]*text-transform:uppercase/.test(html)
  && !/\.kpi-label\{[^}]*font-size:9/.test(html));
ok("the KPI block is outside the sidebar element",
  html.indexOf('id="kpi-hud"') > html.indexOf('id="timeline-bar"') ||
  html.indexOf('id="kpi-hud"') > html.lastIndexOf('class="control-group"'));
ok("and calculateKPIs writes to ids that are really there",
  /id="kpi-routes-label"/.test(html) && code.includes("kpi-routes-label"));
ok("KPIs follow the timeline, not just the filters",
  /if \(typeof TL !== 'undefined' && TL\.on\) return \[TL\.month\]/.test(code));
// §9 — the four cards
// 12 Oct 2026 — REVERSED (D14, review 2.3): the From / To selects are gone; the Show-forecast window is the span of
// months with volume (forecastWindow(), from the timeline matrix), and a month chip shows one month
ok("§9: the month comes from the playhead, else the Show-forecast window (the span with volume, no From / To), else nothing",
  /function kpiMonthsOnScreen\(\)/.test(code) && !code.includes("forecast-from") && !code.includes("forecast-to")
  // NARROWED 12 Oct 2026 (Track C review): forecastWindow() may be null (no matrix), so the line reads `|| []` and an
  // empty window returns no month
  && /const \[f, t\] = forecastWindow\(\)( \|\| \[\])?;/.test(code.slice(code.indexOf("function kpiMonthsOnScreen"), code.indexOf("async function kpiFetchMonth")))
  && /return \[\];\s*\}/.test(code));
ok("§9: figures come from /api/public/month-kpis, cached per month",
  code.includes("/public/month-kpis?month=") && /KPI\.cache\[m\] = j/.test(code));
ok("§9: working days come from the server payload", /const wd = payloads\[0\]\.working_days \|\| 22/.test(code));
ok("§9: vehicles/day = vehicle-loads over months with volume, per working day",
  /const vehDay = avg\(mVeh\) \/ wd/.test(code));
// ⭐ 2026-09-03: movements and vehicles are different. Movements/day = loads per working
// day; vehicles needed = Σ per line ceil(movements/day ÷ trips one vehicle can make on
// that route), busiest month, with unbaked lines counted as unknown rather than zero.
// 2026-10-06: the label reads "Movements a day" (sentence case, no slash) — NARROWED
// 11 Oct 2026 NARROWED (the user): one load = one delivery = one TWO-WAY movement; the figure is loads per
// working day, NEVER doubled, and the label says "Two-way movements a day"
ok("§9: two-way movements/day is the loads-per-working-day figure, not doubled", /set\('kpi-trips', fmtN\(vehDay, 0\)\)/.test(code)
  && />Two-way movements a day</.test(html) && !/MOVES_PER_LOAD/.test(code) && !/vehDay \* 2/.test(code));
ok("§9: ⭐ vehicles needed is ceil(movements ÷ trips-per-vehicle-day) per line, from the route's cycle",
  /fleet \+= Math\.ceil\(\(l\.vehicle_loads \/ wd\) \/ l\.trips_per_vehicle_day\)/.test(code));
// NARROWED 12 Oct 2026 (the base merge): the words a person reads are "no stored route" / "with no stored road route"
ok("§9: ⭐ a line with no stored road route is counted as unknown, never as zero vehicles",
  /else unbakedLines\+\+;/.test(code) && code.includes("'no stored route'")
  && code.includes("line${unbakedLines === 1 ? '' : 's'} with no stored road route)")
  && !code.includes("'not baked'") && !code.includes("'s'} unbaked)"));
ok("the bar's method note and the alternatives note say 'stored road route', not 'baked'",
  code.includes("Active routes = every route with a stored road route that matches the filters.")
  && code.includes("(the cycle time of its stored road route)") && code.includes("'none stored — a route through a haul road has no alternatives'")
  && !code.includes("every baked route matching") && !code.includes("(baked cycle)") && !code.includes("'none baked"));
ok("§9: the fleet figure is the busiest month's, not the average", /const fleet = Math\.max\(\.\.\.mFleet\)/.test(code));
ok("§9: no card says trips equal vehicles", !code.includes("Trips = vehicle loads on every line"));
ok("§9: material/day is in the map unit", /qtyDay = avg\(mQty\) \/ wd/.test(code) && code.includes("kpi-material-label"));
ok("§9: filters apply - origin/dest/IPT on the route, discipline on the LINE",
  /discFilter !== 'ALL' && l\.discipline !== discFilter/.test(code));
ok("§9: an empty month says so and hides the breakdown, no zeros",
  code.includes("No approved forecast in this month.")
  && /if \(!mVeh\.length\) \{[\s\S]{0,600}setHTML\('kpi-breakdown', ''\)/.test(code));
// §D: and the SWITCHER goes with them — a switcher over nothing invites a click that
// changes nothing
ok("§D: an empty month hides the switcher too",
  /if \(!mVeh\.length\) \{[\s\S]{0,600}setHTML\('kpi-switch', ''\)/.test(code));
// 2026-10-06: the breakdown is in the SIDEBAR (#kpi-moving), shown only while a month
// is on screen; the rows keep the .kpi-chip name the browser check reads
ok("⭐ 2026-10-06: the breakdown lives in the sidebar, hidden when no month is on screen",
  html.indexOf('id="kpi-moving"') < html.indexOf('id="restrictions-group"')
  && html.indexOf('id="kpi-breakdown"') < html.indexOf('id="kpi-hud"')
  && (code.match(/showMoving\(false\)/g) || []).length >= 2 && /showMoving\(true\)/.test(code));
// 🔴 REPLACED 2026-09-08 (§D). Two stacked chip rows (discipline, then material when
// the month mixed materials) became ONE row with a three-way switcher. Stacking every
// answer made the card a column; the human asked for one card.
ok("§D: ONE chip row, with a Discipline | IPT | Work section switcher",
  /id="kpi-switch"/.test(html) && /id="kpi-breakdown"/.test(html)
  && !/id="kpi-by-discipline"/.test(html) && !/id="kpi-by-material"/.test(html)
  && /const KPI_BY = \[\['discipline', 'Discipline'\], \['ipt', 'Team'\], \['section', 'Work section'\]\]/.test(code)
  && /KPI_BY\[1\]\[1\] = TEAM/.test(code));   // relabelled with the tenant's word once the overlay lands
ok("§D: discipline is the default", /by: 'discipline'/.test(code));
ok("§D: the switch recomputes rather than re-rendering a cached grouping",
  /function setKpiBy\(k\) \{[\s\S]{0,320}applyFilters\(\);/.test(code));
// 12 Oct 2026 (review §3 row 3) — NARROWED: the section chip prints the work section's NAME
// from WS_NAMES, and falls back to the code only when the package has not named it
ok("§D: IPT comes from the route, discipline and section from the line (named via WS_NAMES, code as the fallback)",
  /KPI\.by === 'ipt' \? \(teamText\(rp\.ipt\) \|\| 'no ' \+ TEAM\.toLowerCase\(\)\)/.test(code)
  && /KPI\.by === 'section' \? \(l\.section_id \? \(\(\(\(window\.WS_NAMES \|\| \{\}\)\[l\.section_id\]\) \|\| \{\}\)\.name \|\| l\.section_id\) : 'no work section'\)/.test(code)
  && !/KPI\.by === 'section' \? \(l\.section_id \|\| 'no work section'\)/.test(code));
// 12 Oct 2026 (fix pass, F1) — NARROWED: the guard is the months AND filters on screen, no longer a call counter (the
// counter dropped every fetch that took longer than one tick, so the bar never rendered during Play)
ok("§9: a stale fetch cannot overwrite a newer month (guarded by the months and filters on screen, not a call counter)",
  /if \(KPI\.onScreen !== onScreen\) return;/.test(code) && /KPI\.onScreen = onScreen;/.test(code)
  && !/if \(seq !== KPI\.seq\) return;/.test(code));
ok("§9: the forecast toggle recomputes the cards",
  /src\.setData\(currentData\);\s*applyRailHighlight\(\);\s*applyFilters\(\);/.test(code)
  || /applyRailHighlight\(\);[\s\S]{0,120}applyFilters\(\);[\s\S]{0,60}\/\/ §9/.test(src));
ok("§9: never actuals", !/actual/.test(code.slice(code.indexOf("function calculateKPIs"), code.indexOf("function calculateKPIs") + 5000)));
ok("scrubbing the timeline recalculates them",
  /applyZoneMonth\(m\);[\s\S]{0,500}applyFilters\(\);/.test(code));
ok("the card label says which question it is answering", code.includes("'Routes in '"));

ok("the ant-march animation runs only while the timeline is playing",
  code.includes("if(!TL.playing)"));
ok("and the line goes solid when it stops", code.includes("DASH_SOLID"));
ok("stopping playback cancels the rAF loop rather than letting it spin for ever",
  code.includes("cancelAnimationFrame(_flowRAF)"));
ok("starting playback starts it", code.includes("startFlowAnimation();"));

// z-order is add order: outbound must be added FIRST so inbound draws on top of it
ok("⭐ inbound (laden) is added AFTER outbound, so it renders on top",
  code.indexOf("'id': 'outbound-lines'") < code.indexOf("'id': 'inbound-lines'"));
ok("and each casing still sits under its own core line",
  code.indexOf("'id': 'outbound-lines-casing'") < code.indexOf("'id': 'outbound-lines'") &&
  code.indexOf("'id': 'inbound-lines-casing'") < code.indexOf("'id': 'inbound-lines'"));
ok("the reason is written down where the order is easy to reverse by accident",
  /LAYER ADD ORDER IS Z-ORDER/.test(src));

ok("the direction offset collapses at high zoom instead of holding 4px",
  /OFFSET_IN\s*=[^;]*17,\s*0\]/.test(code) && /OFFSET_OUT\s*=[^;]*17,\s*0\]/.test(code));
ok("line width keeps scaling with zoom", /WIDTH_CORE\s*=[^;]*16,\s*6\.8\]/.test(code));
ok("no hard-coded offset ramp survives inside a layer definition",
  !/'line-offset': \['interpolate'/.test(code));

// =============================================================================
// IPT / Work Section alignment overlay
// =============================================================================
// Source-level only. The behaviour of the band splitter is asserted against the
// real 8.8 MB alignment file in backend/tests/test_ipt_overlay.js.

// G2 (16 Sep): the module is map/overlay.js — product code only. The band table, the
// section names, the boundaries and the geometry are the tenant's, and the harness
// reads them from the DEMO package so the data-shaped assertions still have data.
const IPTF = path.join(ROOT, "map", "overlay.js");
ok("map/overlay.js exists", fs.existsSync(IPTF));
const iptSrc = fs.existsSync(IPTF) ? fs.readFileSync(IPTF, "utf8").replace(/\r\n?/g, "\n") : "";
// 29 Sep: the theme lives in map/config.js; read it for the rebrand assertions below.
const cfgSrc = fs.readFileSync(path.join(ROOT, "map", "config.js"), "utf8").replace(/\r\n?/g, "\n");
ok("map/ipt_segments.js is gone", !fs.existsSync(path.join(ROOT, "map", "ipt_segments.js")));
const demoPkg = JSON.parse(fs.readFileSync(path.join(ROOT, "demo", "uk-corridor.package.json"), "utf8"));
const demoOv = JSON.parse(demoPkg.tables.config.find(r => r.key === "overlay").value);

ok("index.html loads it", /src=["']overlay\.js(\?v=\d+)?["']/.test(html));
// ⭐ The cache-buster is not cosmetic. A browser revalidates the .html far more
// eagerly than the scripts it loads, so both files can be uploaded correctly and
// the OLD script still run — indistinguishable from forgetting to upload it.
ok("...with a ?v= cache-buster", /src=["']overlay\.js\?v=\d+["']/.test(html));
ok("and it ships EMPTY defaults, filled by applyOverlayPackage() from the API",
  /window\.IPT_SEGMENTS = window\.IPT_SEGMENTS \|\| \[\];/.test(iptSrc)
  && /window\.applyOverlayPackage = function/.test(iptSrc));
ok("it is a plain script tag, not a new CDN dependency",
  !/https?:\/\/[^"']*overlay\.js/.test(html));

ok("the alignment layer is coloured from ipt_colour",
  /'line-color':\s*\['coalesce',\s*\['get',\s*'ipt_colour'\]/.test(code));
ok("with a fallback colour if the package carries no band colour",
  /\['get',\s*'ipt_colour'\],\s*'#64748B'\]/.test(code));
ok("the fixed black alignment colour is gone",
  !/'id': 'rail-alignment'[\s\S]{0,400}'line-color':\s*'#000000'/.test(code));
// --- the 2026-08-28 polish pass ------------------------------------------------
// The first cut used one layer at two widths (Main Track 2.5, everything else 1.2).
// The polish spec replaced that: ONE width, Main Track only, side tracks moved off
// the package view entirely. Both halves are asserted, because dropping the filter
// and keeping the width would look right in a diff and wrong on the map.
ok("⭐ the IPT layer is Main Track only",
  /'id': 'rail-alignment',[\s\S]{0,700}'filter':[\s\S]{0,200}\['==',\s*\['get',\s*'align_type'\],\s*'Main Track'\]/.test(code));
// 🔴 REVERSED 2026-09-01. The user asked for a continuous corridor and chose full
// continuity over the 30%-opacity version, so the civil layer now DRAWS bridges
// rather than excluding them. The assertion is reversed, not removed — it is the
// record of a decision that has now flipped three times (phantom lines -> cut ->
// faint bridges -> gone -> solid), and each flip has to be deliberate.
ok("🔴 the gap bridges are drawn SOLID on the civil layer, by request",
  !/'id': 'rail-alignment',[\s\S]{0,900}'filter':[\s\S]{0,200}\['!=',\s*\['get',\s*'is_bridge'\],\s*true\]/.test(code));
ok("it draws at ONE width, not two",
  /'id': 'rail-alignment',[\s\S]{0,900}'line-width':\s*2\.5,/.test(code));
ok("the old two-width case expression is gone",
  !/\['case',\s*\['==',\s*\['get',\s*'align_type'\],\s*'Main Track'\],\s*2\.5,\s*1\.2\]/.test(code));

// Gap bridges — REMOVED 2026-08-30 at the user's request
// ⚠️ These assertions are reversed rather than deleted. The point they were making
// — that a gap must not be silently invented, and must not be silently hidden
// either — still holds; it is now enforced from the other side. The geometry cut
// itself is untouched.
ok("⭐ the bridge layer is gone", !code.includes("'id': 'rail-alignment-bridge'"));
ok("and nothing still tries to toggle or filter it",
  !/toggleLayer\('rail-alignment-bridge'/.test(code) &&
  !/setFilter\('rail-alignment-bridge'/.test(code));
ok("⭐ but the GEOMETRY CUT survives — the 239.5 km of phantom straights stay out",
  /var GAP_SPLIT = true/.test(iptSrc));
ok("and the builder still emits the is_bridge flag, so nothing downstream breaks",
  /p\.is_bridge = /.test(iptSrc));
// 🔴 The consequence of drawing them solid, and it is the whole risk of the change:
// nothing in the PICTURE now separates measured geometry from an interpolation
// across ~60 km of missing survey, on a client-visible map. Two things carry the
// caveat instead, and both are asserted so neither can quietly go.
ok("🔴 the click popup declares an interpolated stretch",
  /No surveyed alignment on this stretch/.test(code) && /p\.is_bridge/.test(code));
ok("...and says plainly that it is not measured geometry",
  /not measured geometry/.test(code));
ok("the sidebar legend no longer claims there are breaks in the line",
  !/Breaks in the line/.test(html) && /interpolated/.test(html));
ok("⭐ the reason it was made solid is written next to the layer",
  /drawn SOLID, at full opacity/.test(src) && /honest-presentation alternative is one number/.test(src)
  && !/open-questions\.md/.test(src));   // G2: the product does not cite one project's notes
ok("the boundary labels still flag a tick with no surveyed track under it",
  /no surveyed alignment here/.test(code));

// Survey layer
ok("the original continuous alignment survives as its own layer",
  code.includes("'id': 'rail-alignment-survey'"));
ok("⭐ fed from the RAW alignment data, so the IPT cuts cannot reach it",
  /addSource\('alignment-survey-source',\s*\{\s*type:\s*'geojson',\s*data:\s*alignment_data\s*\}/.test(code));
ok("styled as it was before the overlay — black, 1.5 px",
  /'id': 'rail-alignment-survey'[\s\S]{0,400}'line-color':\s*'#000000'[\s\S]{0,120}'line-width':\s*1\.5/.test(code));
ok("with its own independent checkbox", /id="layer-alignment-survey"/.test(html) &&
  /onchange="toggleLayer\('rail-alignment-survey', this\.checked\)"/.test(html));
// ⚠️ inline handlers have to come out first: `onchange="...this.checked)"` contains
// the literal word `checked`, so a naive test for the ATTRIBUTE matches every
// wired checkbox and this assertion would fail on a correctly-unchecked box.
const htmlNoHandlers = html.replace(/\son\w+="[^"]*"/g, "");
ok("and it is OFF by default, so the IPT view is what opens",
  !/id="layer-alignment-survey"[^>]*\schecked[\s>]/.test(htmlNoHandlers));
ok("while the IPT layer IS on by default",
  /id="layer-alignment"[^>]*\schecked[\s>]/.test(htmlNoHandlers));

// ⭐ add order is z-order in this file: survey under bridges under solid track
ok("⭐ the survey layer is added first, so it sits under the IPT layers",
  code.indexOf("'id': 'rail-alignment-survey'") < code.indexOf("'id': 'rail-alignment-underlay'"));
ok("⭐ and the underlay before the solid track, so the package colour reads on top",
  code.indexOf("'id': 'rail-alignment-underlay'") < code.indexOf("'id': 'rail-alignment',"));
ok("the reason for that order is written down next to it",
  /ADD ORDER IS THE Z-ORDER/.test(src));

// the three parts of the IPT view move together
ok("toggling the IPT view hides both legend blocks",
  /function toggleAlignment[\s\S]{0,500}'ipt-legend-note'/.test(code));
// NARROWED 29 Sep 2026: the note used to quote the first tenant's figure ("~60 km has no
// surveyed Main Track"); a tenant-neutral map explains the rule, not one alignment's number.
ok("the legend explains what a fainter segment means",
  /id="ipt-legend-note"/.test(html) && /no surveyed main track/i.test(html) && /interpolated/.test(html));
ok("🔴 …and carries no first-tenant figure (no '~60 km', no '7 package edges')",
  !/~60/.test(html) && !/7 package edges/.test(html));

// clicking a bridge must explain itself
ok("⭐ the boundary ticks answer a click too — a mark with no line under it is "
   + "where an explanation is needed most",
  /\['ws-boundary-ticks', 'ws-boundary-labels'\]\.forEach/.test(code));
ok("and that popper is wired ONCE, like the alignment one",
  /WS_POPUP_WIRED/.test(code) &&
  /function setupWsBoundaryPopup\(\)\s*\{\s*if\s*\(WS_POPUP_WIRED\)\s*return;/.test(code));
ok("⭐ it says when there is no surveyed alignment, and how far the nearest is",
  code.includes("No surveyed alignment here.") && /track_gap_m/.test(code));
ok("and it names the two sections in full, not just their codes",
  /window\.WS_NAMES\[c\]/.test(code));

// --- 2026-08-28: the mandated palette ------------------------------------------
// The rule is that no IPT colour may reuse a hex the map spends on a route, a
// forecast, a selection or temporary haul — otherwise "this stretch is IPT 6"
// and "this route is laden" become the same colour, and the route layers are
// the ones carrying money. Checked against the real source both ways.
// G2: the product theme's route / forecast / selection hexes, as overlay.js reserves them.
// 29 Sep 2026: the ink is #1F2024 (Wayscope); #0F172A is retired and must not come back.
const RESERVED = ["#059669", "#f59e0b", "#C2790B", "#3B82F6", "#DC2626", "#2563EB", "#1F2024"];
ok("the reserved list in overlay.js is exactly the theme's route colours",
  RESERVED.every(r => iptSrc.toLowerCase().includes(r.toLowerCase())));
ok("REBRAND (29 Sep): the retired G2 ink #0F172A is gone from the map, its config and overlay.js",
  !/#0F172A/i.test(code) && !/#0F172A/i.test(iptSrc) && !/#0F172A/i.test(cfgSrc));
ok("REBRAND: the map's brand ink is #1F2024 and its forecast routes stay blue (no orange on the map)",
  /brandDark:\s+"#1F2024"/.test(cfgSrc) && /forecastCasing:\s+"#1F2024"/.test(cfgSrc)
  && /brand:\s+"#2563EB"/.test(cfgSrc) && /forecast:\s+"#3B82F6"/.test(cfgSrc) && !/#FF8C14/i.test(cfgSrc));
// 11 Oct 2026 NARROWED (the user): "corridor map" is now "public map" wherever a person reads the name
ok("REBRAND: the map is titled Wayscope, defaults its tenant to Wayscope, and never says Modus",
  /<title>Wayscope — public map<\/title>/.test(html) && !/<title>[^<]*corridor map/i.test(html) && /let TENANT = \{ name: 'Wayscope',/.test(code)
  && !/\bModus\b/.test(html) && !/\bModus\b/.test(iptSrc) && !/\bModus\b/.test(cfgSrc));
ok("REBRAND: the map's head carries the favicon links and the ink theme-color",
  /<link rel="icon" href="\/favicon\.ico" sizes="32x32">/.test(html) && /<link rel="manifest" href="\/site\.webmanifest">/.test(html)
  && /<meta name="theme-color" content="#1F2024">/.test(html));
// the band colours come from the DEMO package now
const bandHexes = demoOv.bands.map(b => String(b.colour || "").toLowerCase());
ok("the demo band table declares a colour for every band", bandHexes.length === 6 && bandHexes.every(h => /^#[0-9a-f]{6}$/.test(h)),
  `got ${bandHexes.length}`);
ok("⭐ NO IPT colour reuses a reserved route / forecast / selection hex",
  RESERVED.every(r => !bandHexes.includes(r.toLowerCase())),
  `clash: ${RESERVED.filter(r => bandHexes.includes(r.toLowerCase())).join(", ")}`);
ok("and the demo's underlay (none) or its colour is clear of them too",
  !demoOv.underlay || !RESERVED.map(r => r.toLowerCase()).includes(String(demoOv.underlay.colour || "").toLowerCase()));
ok("the reserved list is in the source, with the rule it protects, so a future "
   + "palette edit has something to check against",
  /IPT_RESERVED_COLOURS/.test(iptSrc) && /route layers are the ones that carry money/.test(iptSrc));
// ⭐ The property being guarded: one distinct colour per TEAM, none of them a route
// colour. The demo has three teams across six bands; the palette-measurement prose
// that used to sit beside one project's band table (ΔE2000, deuteranopia) went with
// that table — it described those six hexes, not the product.
const demoTeams = [...new Set(demoOv.bands.map(b => b.ipt))];
const hexByTeam = Object.fromEntries(demoOv.bands.map(b => [b.ipt, String(b.colour).toLowerCase()]));
ok("the demo's three teams each have ONE colour, used on every band they own",
  demoTeams.length === 3 && demoOv.bands.every(b => hexByTeam[b.ipt] === String(b.colour).toLowerCase()));
ok("⭐ the three team colours are distinct — no two share a hex",
  new Set(Object.values(hexByTeam)).size === 3);
ok("the first-cut greens and ambers are gone from every band",
  !bandHexes.includes("#c6841d") && !bandHexes.includes("#039e86"));
ok("and so is the whole indigo/violet run that made three bands unreadable",
  !["#4338ca", "#6d28d9", "#5b21b6"].some(h => bandHexes.includes(h)));
ok("⭐ the #6D28D9 collision is GONE, not just documented — from product code and the demo",
  !/colour: '#6D28D9'/.test(iptSrc) && !bandHexes.includes("#6d28d9"));
ok("the underlay falls back to a LIGHT wash, not a deep colour competing for hue",
  /'line-color': \(window\.IPT_UNDERLAY \|\| \{\}\)\.colour \|\| '#C4B5FD'/.test(code)
  && !/\.colour \|\| '#5B21B6'/.test(code));

// ---- G2: team ids never reach the screen ------------------------------------------
ok("G2: the overlay response's team names fill TEAM_LABELS",
  /\(o\.teams \|\| \[\]\)\.forEach\(t => \{/.test(code) && /TEAM_LABELS\[String\(t\.id\)/.test(code));
ok("G2: teamText() maps every team id in a value to the tenant's name, leaving other text alone",
  /function teamText\(v\)/.test(code) && /\\bipt\\s\*\[-_ \]\?\\s\*\(\[1-6\]\)\\b\/gi/.test(code));
ok("G2: an unnamed slot reads '<team word> <n>', never the id",
  /TEAM_LABELS\[k\] \|\| \(TEAM \+ ' ' \+ k\.replace\(\/\^IPT\[-_\]\?\/, ''\)\)/.test(code));
ok("G2: the team filter keeps the raw value but shows the name",
  /fill\('filter-ipt', ipts, teamText\)/.test(code) && /value="\$\{v\}">\$\{text \? text\(v\) : v\}/.test(code));
ok("G2: the compound popup shows the team's name",
  /<b>\$\{TEAM\}:<\/b> \$\{teamText\(props\.ipt\)\}/.test(code));
ok("G2: no team value is interpolated raw into the page",
  !/\$\{props\.ipt\}/.test(code) && !/\$\{rp\.ipt\}/.test(code));
// behaviour, not just text: run the two helpers as the page defines them
{
  const grab = (name) => { const m = code.match(new RegExp("function " + name + "\\(([^)]*)\\) \\{[\\s\\S]*?\\n    \\}")); return m && m[0]; };
  const fnSrc = [grab("teamName"), grab("teamText")].join("\n");
  const mk = new Function("TEAM_LABELS", "TEAM", fnSrc + "; return { teamName, teamText };");
  const T = mk({ IPT1: "North Team", IPT3: "South Team" }, "Team");
  ok("G2: teamText('IPT1') is the tenant's name", T.teamText("IPT1") === "North Team", T.teamText("IPT1"));
  ok("G2: teamText('IPT 3 / IPT6') names both, an unnamed slot reads 'Team 6'",
    T.teamText("IPT 3 / IPT6") === "South Team / Team 6", T.teamText("IPT 3 / IPT6"));
  ok("G2: free text is left alone", T.teamText("Contractor A") === "Contractor A" && T.teamText("") === "" && T.teamText(null) === null);
  ok("G2: a word that merely contains 'ipt' is not touched", T.teamText("receipt 3") === "receipt 3", T.teamText("receipt 3"));
}

// ---- G2, REVERSED: one project's band facts no longer ship ------------------------
// These assertions used to pin the Alliance 1 band table, its palette measurements
// and its disputed work-section ownership. That table is tenant data now (it travels
// in that tenant's package, held offline). Each is REVERSED rather than deleted: the
// product code must not carry those facts again, so a paste-back of the old
// ipt_segments.js is caught here.
const productMap = iptSrc + "\n" + html;
ok("REVERSED: no ΔE2000 palette record for one project's hexes in product code", !/ΔE2000/.test(iptSrc));
ok("REVERSED: no deuteranopia table for one project's bands", !/deuteranopia/.test(iptSrc));
ok("REVERSED: the 'deliberately the WEAKEST' palette note left with its table", !/deliberately the WEAKEST/.test(iptSrc));
ok("REVERSED: ...and so did the dotted-route dependency note", !/dependency of this palette/.test(iptSrc));
ok("REVERSED: the six hue-family list left with its table", !/jade, violet, teal blue/.test(iptSrc));
for (const [ipt, hex] of [["IPT 6", "#0F766E"], ["IPT 1", "#4C1D95"], ["IPT 2", "#155E75"],
                          ["IPT 3", "#57534E"], ["IPT 4", "#92400E"], ["IPT 5", "#831843"]]) {
  ok(`REVERSED: ${ipt}'s ${hex} is not hard-coded as a band colour in product code`,
    !iptSrc.includes(`colour: '${hex}'`) && !new RegExp(`ipt: '${ipt}'`).test(productMap));
}
ok("REVERSED: no measured colour-blind figures for one project's pairs", !/IPT 1 \/ IPT 2\s+19\.5/.test(iptSrc));
ok("REVERSED: no brief-figure warning for one project's palette", !/Do not restore 13\.5/.test(iptSrc));
ok("REVERSED: no one-hex palette fix on record in product code", !/#7C3AED/.test(iptSrc));
ok("REVERSED: the A1/A2 ~141+930 discrepancy is not in product code", !/141\+930/.test(productMap));
ok("REVERSED: no WS13 ownership ruling in product code", !/WS13/.test(productMap));
ok("REVERSED: ...and no band row moving it", !/ws: \['WS2', 'WS13'\]/.test(iptSrc));
ok("REVERSED: no WS14/WS15 open question in product code", !/WS1[45]\b/.test(productMap));
ok("REVERSED: no WS 7.1–7.4 subdivision note in product code", !/WS 7\.1/.test(productMap));
ok("REVERSED: no IPT_SEGMENTS_VERSION stamp — the package carries its own version", !/IPT_SEGMENTS_VERSION/.test(iptSrc));
ok("REVERSED: no ?v=9 file pairing to keep in step", !/ipt_segments\.js\?v=9/.test(html));
ok("REVERSED: no 'Outside A1' band name anywhere in product map code", !/Outside A1/.test(productMap));
ok("REVERSED: no project scope-diagram citations in product map code", !/scope diagram v1\.0|IPT Matrix/.test(productMap));
ok("G2: no alignment.js on disk", !fs.existsSync(path.join(ROOT, "map", "data", "alignment.js")));
ok("G2: no chainage.js on disk", !fs.existsSync(path.join(ROOT, "map", "data", "chainage.js")));
ok("G2: no evr_rail.js on disk", !fs.existsSync(path.join(ROOT, "map", "data", "evr_rail.js")));

// --- IPT 6 superstructure underlay --------------------------------------------
ok("there is an underlay layer", code.includes("'id': 'rail-alignment-underlay'"));
ok("⭐ it is added AFTER survey and BEFORE the civil track, so the package "
   + "colour stays the primary read",
  code.indexOf("'id': 'rail-alignment-survey'") < code.indexOf("'id': 'rail-alignment-underlay'") &&
  code.indexOf("'id': 'rail-alignment-underlay'") < code.indexOf("'id': 'rail-alignment',"));
ok("it is wider than the civil track",
  /'id': 'rail-alignment-underlay'[\s\S]{0,900}'line-width': \(window\.IPT_UNDERLAY/.test(code));
ok("its colour, width and opacity come from the package's underlay object, not three literals",
  /window\.IPT_UNDERLAY = o\.underlay \|\| null;/.test(iptSrc)
  && /'line-color': \(window\.IPT_UNDERLAY \|\| \{\}\)\.colour/.test(code));
ok("⭐ it runs the whole mainline, not just one team's civil band — "
   + "so it is filtered by align_type and the muted flag, never by chainage",
  /'id': 'rail-alignment-underlay'[\s\S]{0,700}\['!=', \['get', 'muted'\], true\]/.test(code));
// reversed with the civil layer above: an underlay with holes under a continuous
// civil line reads as a rendering fault rather than as missing data
ok("⭐ and it includes bridges, matching the civil layer",
  !/'id': 'rail-alignment-underlay'[\s\S]{0,700}\['!=', \['get', 'is_bridge'\], true\]/.test(code));

// --- per-IPT selection ---------------------------------------------------------
ok("the legend rows are checkboxes now",
  /input type="checkbox" id="\$\{iptCheckboxId/.test(code));
ok("still generated from IPT_SEGMENTS, not hand-typed",
  code.includes("window.iptLegendRows()"));
ok("ticking one re-filters rather than rebuilding the GeoJSON",
  code.includes("function applyIptFilter") && !/applyIptFilter[\s\S]{0,600}buildIptAlignment/.test(code));
ok("the filter is a membership test on ipt",
  /\['in', \['get', 'ipt'\], on\]/.test(code));
ok("the civil filter is applied in exactly one place now the bridges are gone",
  (code.match(/\['in', \['get', 'ipt'\], on\]/g) || []).length === 1);
ok("⭐ the IPT 6 checkbox drives the UNDERLAY, not the civil filter",
  /toggleUnderlay\(this\.checked\)/.test(code) &&
  /function toggleUnderlay[\s\S]{0,140}rail-alignment-underlay/.test(code));
ok("⭐ and unchecking it leaves every civil colour where it was — the underlay's team is "
   + "always in the civil set",
  /const on = \[underlayKey\(\)\]/.test(code));
ok("the reason that asymmetry exists is written down",
  /The underlay band is NOT in the civil filter/.test(src));
ok("all boxes start ticked",
  /type="checkbox" id="\$\{iptCheckboxId\(r\.ipt\)\}" checked/.test(code));
ok("a missing checkbox is treated as ticked, so the filter cannot blank the map "
   + "if the legend failed to render",
  /!el \|\| el\.checked/.test(code));
ok("the checkbox id is derived, not hand-listed per IPT",
  /function iptCheckboxId/.test(code));
ok("hiding the whole alignment hides the underlay too",
  /function toggleAlignment[\s\S]{0,500}rail-alignment-underlay/.test(code));
ok("the underlay legend row says what it is — the package's label, else 'corridor underlay'",
  /\(window\.IPT_UNDERLAY \|\| \{\}\)\.label \|\| 'corridor underlay'/.test(code));

// --- 2026-08-30: work-section boundary ticks -----------------------------------
ok("there is a boundary source", code.includes("addSource('ws-boundary-source'"));
ok("memoised like the other two builds",
  /WS_BOUNDS\s*=\s*null/.test(code) && /if\s*\(WS_BOUNDS\)\s*return WS_BOUNDS/.test(code));
ok("a tick layer and a label layer", code.includes("'id': 'ws-boundary-ticks'") &&
  code.includes("'id': 'ws-boundary-labels'"));
ok("⭐ ticks are a SYMBOL layer, not a line — a fixed ground length would be one "
   + "pixel at corridor zoom and half the viewport at zoom 16",
  /'id': 'ws-boundary-ticks', 'type': 'symbol'/.test(code));
ok("⭐ rotated to lie ACROSS the alignment, not along it",
  /'text-rotate': \['get', 'tick_rotate'\]/.test(code) &&
  /'text-rotation-alignment': 'map'/.test(code));
ok("and tick_rotate is the local bearing plus 90",
  /brg \+ 90/.test(iptSrc));
// Phase 5b: ticks 11 -> 8, labels 13 -> 11. At 11 the ticks were effectively
// absent — you had to already be looking at a boundary to find one.
ok("ticks from zoom 8, so they are visible at corridor zoom",
  /'id': 'ws-boundary-ticks'[\s\S]{0,400}'minzoom': 8/.test(code));
ok("⭐ labels from zoom 11, three levels after the ticks appear",
  /'id': 'ws-boundary-labels'[\s\S]{0,400}'minzoom': 11/.test(code));
ok("⭐ only every OTHER boundary is labelled below zoom 13 — boundaries a few km "
   + "apart collide",
  /\['%', \['get', 'idx'\], 2\]/.test(code));
ok("...stepped on zoom in the TEXT-FIELD, because ['zoom'] does not work in a filter",
  /'text-field': \['step', \['zoom'\]/.test(code));
ok("...and the unlabelled ones are hidden with an EMPTY text-field, never opacity 0",
  !/'text-opacity': 0/.test(code));
ok("the boundary index is stamped on the data, not guessed in the expression",
  /properties\.idx = ix/.test(iptSrc));
ok("the label names both sections meeting at the tick, and the chainage",
  /\['get', 'label'\]/.test(code) && /\['get', 'chain_txt'\]/.test(code));
ok("labels declutter; ticks do not, because there are only seven",
  /'id': 'ws-boundary-ticks'[\s\S]{0,900}'text-allow-overlap': true/.test(code) &&
  /'id': 'ws-boundary-labels'[\s\S]{0,1400}'text-allow-overlap': false/.test(code));
ok("⭐ the tick colour is neutral slate — not a route colour and not a package "
   + "colour, because a tick is neither",
  /'text-color': '#334155'/.test(code) &&
  /WS_TICK_COLOUR = '#334155'/.test(iptSrc));
ok("and slate is not one of the reserved route hexes",
  !RESERVED.map(r => r.toLowerCase()).includes("#334155"));
ok("nor one of the band colours", !bandHexes.includes("#334155"));
ok("one toggle moves ticks and labels together",
  /function toggleWsBounds[\s\S]{0,220}ws-boundary-ticks[\s\S]{0,120}ws-boundary-labels/.test(code));
ok("the sidebar has the checkbox", /id="layer-ws-bounds"/.test(html));
ok("on by default", /id="layer-ws-bounds"[^>]*\schecked[\s>]/.test(htmlNoHandlers));
ok("⭐ ticks are added AFTER the alignment layers, so one is never buried under "
   + "the line it marks",
  code.indexOf("'id': 'rail-alignment',") < code.indexOf("'id': 'ws-boundary-ticks'"));
ok("and BEFORE chainage, so a 100 m dot never sits on top of a package edge",
  code.indexOf("'id': 'ws-boundary-ticks'") < code.indexOf("'id': 'chainage-global'"));
ok("the boundary table is package data, filled beside the band table it mirrors",
  /window\.WS_BOUNDARIES = Array\.isArray\(o\.boundaries\)/.test(iptSrc));
ok("⭐ the reason point assets get no tick is written down, not just implied",
  /[Pp]oint assets/.test(iptSrc) && /get no tick/.test(iptSrc));
ok("⭐ and so is the single-datum rule",
  /single global datum/.test(iptSrc) && /local datum must not/.test(iptSrc));
ok("⭐ a boundary must equal the band edge it marks — asserted on the demo package",
  demoOv.boundaries.length >= 3 && demoOv.boundaries.every(b =>
    demoOv.bands.some(x => x.chain_from === b.chain_m || x.chain_to === b.chain_m)));

// --- the WS name table and its disputes ---------------------------------------
ok("section names are package data, filled once from section_names",
  /window\.WS_NAMES = o\.section_names \|\| \{\};/.test(iptSrc));
ok("the demo names every section it declares (six bands, two point assets)",
  Object.keys(demoOv.section_names).length === 8
  && demoPkg.tables.work_sections.every(w => demoOv.section_names[w.section_id]));
ok("⭐ every section name carries the team that owns it, and it agrees with the band table",
  demoOv.bands.every(b => (demoOv.section_names[b.ws_primary] || {}).ipt === b.ipt));
ok("every band names the ONE section that owns its chainage",
  demoOv.bands.every(b => b.ws_primary && b.ws.includes(b.ws_primary)));
ok("and a muted band, if any, owns none", demoOv.bands.every(b => !b.muted || !b.ws_primary));
ok("segments carry the owning section and its name",
  /p\.ws_primary = /.test(iptSrc) && /p\.ws_name = /.test(iptSrc));

// --- chainage, zoom-synced -----------------------------------------------------
ok("the chainage source carries the step tiers",
  /addSource\('chainage-source',\s*\{\s*type:\s*'geojson',\s*data:\s*chainageStepData\(\)/.test(code));
ok("which is memoised like the alignment build",
  /CHAINAGE_STEPPED\s*=\s*null/.test(code) && /if\s*\(CHAINAGE_STEPPED\)\s*return CHAINAGE_STEPPED/.test(code));
ok("⭐ marker density is driven by zoom", /'circle-radius':\s*\['step',\s*\['zoom'\]/.test(code));
ok("⭐ starting with the 10 km ticks alone at corridor zoom",
  /CH_TIER\(10000\)/.test(code));
ok("then 5 km at zoom 9, 1 km at 11, 500 m at 13, everything at 15",
  /9,\s*CH_TIER\(5000\)[\s\S]{0,120}11,\s*CH_TIER\(1000\)[\s\S]{0,120}13,\s*CH_TIER\(500\)[\s\S]{0,120}15,\s*3/.test(code));
ok("⭐ labels stop at the 500 m tier even at maximum zoom — a number every ~100 m "
   + "is the same smear made of text",
  /15,\s*CH_LBL\(500\)/.test(code) && !/15,\s*\['get', 'chaintxt'\]/.test(code));
ok("the label ladder starts one zoom level behind the circles",
  /9,\s*CH_LBL\(10000\)/.test(code));
ok("the 500 m tier exists in the step table",
  /CHAINAGE_STEPS = \[10000, 5000, 1000, 500, 100\]/.test(iptSrc));
ok("⭐ the on-tick test handles NEGATIVE chainage — a corridor can start below "
   + "zero and the spec's formula could never match a negative tick",
  /\(\(m % step\) \+ step\) % step/.test(iptSrc));
ok("and why the spec's version was not used is recorded",
  /WRONG for negative chainage/.test(iptSrc));
ok("the chainage toggle is off by default",
  !/id="layer-chainage"[^>]*\schecked[\s>]/.test(htmlNoHandlers));
ok("the old flat radius of 3 is gone",
  !/'id': 'chainage-global'[\s\S]{0,400}'circle-radius':\s*3,/.test(code));
ok("⭐ labels are off entirely at corridor zoom",
  /'text-field':\s*\['step',\s*\['zoom'\],\s*''/.test(code));
ok("⭐ and hidden with an EMPTY text-field, not opacity — opacity 0 still takes up "
   + "collision space and would push real labels off the map",
  !/'id': 'chainage-labels'[\s\S]{0,900}'text-opacity'/.test(code));
ok("labels declutter rather than overlap",
  /'id': 'chainage-labels'[\s\S]{0,900}'text-allow-overlap':\s*false/.test(code));
ok("and keep their halo so they stay readable over the basemap",
  /'id': 'chainage-labels'[\s\S]{0,1100}'text-halo-width':\s*2/.test(code));
ok("the reason ['zoom'] is not used in a filter is recorded, since it is the "
   + "obvious thing to reach for",
  /cannot use \['zoom'\] inside a layer `filter`/.test(src));
ok("the sidebar says what the marker behaviour is",
  /10 km ticks at corridor zoom/.test(html));

// what must NOT have changed
// G2 narrowing: the rationale stays; the one project's feature counts left with its data
ok("the band splitter is untouched — midpoint stamping stays rejected",
  /WHY THIS FILE SPLITS LINES INSTEAD OF STAMPING THEM/.test(iptSrc) && /midpoint/i.test(iptSrc)
  && /function splitAtGaps\(coords, bridges\)/.test(iptSrc));
ok("GAP_SPLIT still cuts the geometry; bridges are paint, not a reinstated straight",
  /var GAP_SPLIT = true/.test(iptSrc));
ok("a muted band is still shown, muted rather than hidden",
  /muted: !!s\.muted/.test(iptSrc) && /p\.muted = !!seg\.muted/.test(iptSrc));

ok("the layer id is unchanged, so the toggle still targets it",
  code.includes("'id': 'rail-alignment'"));
ok("the alignment checkbox still exists", /id="layer-alignment"/.test(html));
ok("and still shows/hides the same layer",
  /function toggleAlignment[\s\S]{0,200}toggleLayer\('rail-alignment',\s*visible\)/.test(code));
ok("the checkbox is wired to it", /onchange="toggleAlignment\(this\.checked\)"/.test(html));

ok("there is a legend container in the sidebar", /id="ipt-legend"/.test(html));
ok("the legend is generated from IPT_SEGMENTS, not hand-typed",
  code.includes("window.iptLegendRows()") && !/North Team[\s\S]{0,80}Central Team/.test(html));
ok("and it is rendered on load", code.includes("renderIptLegend()"));
ok("hiding the alignment hides its legend too",
  /function toggleAlignment[\s\S]{0,700}ipt-legend[\s\S]{0,160}display/.test(code));

ok("⭐ the built collection is memoised, so a basemap switch does not rebuild it",
  /IPT_ALIGNMENT\s*=\s*null/.test(code) && /if\s*\(IPT_ALIGNMENT\)\s*return IPT_ALIGNMENT/.test(code));
ok("and the source is fed the built collection, not the raw file",
  /addSource\('alignment-source',\s*\{\s*type:\s*'geojson',\s*data:\s*iptAlignmentData\(\)/.test(code));
ok("the raw alignment_data is no longer handed to the source directly",
  !/addSource\('alignment-source'[\s\S]{0,80}data:\s*alignment_data\s*\}/.test(code));

ok("⭐ the alignment popup is wired exactly once, not once per basemap switch",
  code.includes("ALIGNMENT_POPUP_WIRED") &&
  /function setupAlignmentPopup\(\)\s*\{\s*if\s*\(ALIGNMENT_POPUP_WIRED\)\s*return;/.test(code));
// --- 2026-08-30: the popup now names the WORK SECTION that owns the band -------
ok("the popup names the IPT and the owning work section",
  code.includes("Work section:") && code.includes("p.ipt_label"));
ok("⭐ it shows the OWNING section, not every code on that ground",
  code.includes("p.ws_primary") && /also on this ground/.test(code));
ok("with its official name, not just the code",
  /wsName/.test(code) && /window\.wsLabel/.test(iptSrc));
ok("⭐ chainage reads as an engineer writes it — 105+480, not 105.48 km",
  /window\.chainText/.test(code) && !/toFixed\(3\)\.replace/.test(code));
ok("the underlay note appears ONLY when the underlay is actually on, and reads the package's note",
  /\(window\.IPT_UNDERLAY \|\| \{\}\)\.note/.test(code) &&
  /undOn\s*\?/.test(code) && /undBox/.test(code));
ok("and never on a muted stretch the underlay does not cover",
  /!\(p\.muted === true \|\| p\.muted === 'true'\)/.test(code));
ok("a provisional band says so in the popup, from the package's provisional_bounds",
  /Provisional boundary/.test(code) && /IPT_BOUNDS_PROVISIONAL \|\| \[\]\)\.some/.test(code));
ok("and a disputed WS name carries its dispute",
  /wsMeta\.note/.test(code));
ok("and says the WS2/WS3 bound is provisional rather than implying it is surveyed",
  /provisional/i.test(code));

// The band table itself
ok("IPT_SEGMENTS is defined (empty until the package lands)", /window\.IPT_SEGMENTS = window\.IPT_SEGMENTS \|\| \[\];/.test(iptSrc));
ok("iptForChainage is defined", /window\.iptForChainage\s*=/.test(iptSrc));
ok("buildIptAlignment is defined", /window\.buildIptAlignment\s*=/.test(iptSrc));
ok("the gap split is documented as a switchable change, with the off-state named",
  /GAP_SPLIT\s*=\s*false/.test(iptSrc) && /var GAP_SPLIT = true/.test(iptSrc));
ok("the ipt/routes naming collision is written down where it will be read",
  /NAMING COLLISION/.test(iptSrc) && /filter-ipt/.test(iptSrc));
ok("the reason midpoint stamping was rejected is recorded — in product terms, not one project's numbers",
  /One midpoint stamp paints a long feature a single colour/.test(iptSrc)
  && /tens of kilometres/.test(iptSrc) && !/45\.2 km/.test(iptSrc) && !/143700/.test(iptSrc));

// The route filter must not be pointed at the alignment layer
ok("⭐ the sector-IPT route filter still applies to route layers only",
  /filterArr\.push\(\['==',\s*\['get',\s*'ipt'\],\s*i\]\)/.test(code));
// ⚠️ This assertion used to read "rail-alignment is never given a filter". The
// 2026-08-28 per-IPT selection filters it deliberately, so the guard is restated
// rather than deleted: what it was ever protecting is that the ROUTE filter
// (#filter-ipt, which means "the IPT that owns the delivery") must never drive
// the ALIGNMENT layer (whose ipt means "the works package this ground is in").
ok("⭐ the alignment filter is driven by the IPT checkboxes, not by #filter-ipt",
  /setFilter\('rail-alignment',[\s\S]{0,300}checkedIpts\(\)|applyIptFilter[\s\S]{0,900}setFilter\('rail-alignment'/.test(code));
ok("⭐ and #filter-ipt is never read by the alignment code",
  !/function applyIptFilter[\s\S]{0,900}filter-ipt/.test(code));
ok("the two meanings are still written down where they can be confused",
  /NAMING COLLISION/.test(iptSrc));

// ---- Phase 5a: the gate layer ------------------------------------------------
// `code` is comment-stripped, so these cannot pass by matching the prose that
// explains them; the two prose checks below use `src` deliberately.
ok("gates are drawn as their own circle layer, not as site markers",
  code.includes("id: 'site-gates'") && code.includes("type: 'circle'"));
ok("the gate layer filters on the Gate feature type",
  code.includes("['==', ['get', 'type'], 'Gate']"));
ok("gates do not appear until zoom 10 — below that a gate and its site are one pixel",
  /id: 'site-gates',[\s\S]{0,200}minzoom: 10/.test(code));
ok("gate labels come in later than the dots",
  /id: 'site-gates-label',[\s\S]{0,200}minzoom: 13/.test(code));
ok("a deactivated gate is drawn hollow rather than hidden",
  code.includes("['case', ['get', 'active'], '#64748B', '#FFFFFF']"));
ok("the gate layer's visibility is read from the checkbox, not a module variable",
  code.includes("function gatesVisible()")
  && code.includes("document.getElementById('layer-gates')")
  && code.includes("visibility: gatesVisible()"));
ok("there is a control for it", /id="layer-gates"/.test(html)
  && /toggleGates\(this\.checked\)/.test(html));
ok("the toggle moves both the dots and the labels",
  code.includes("['site-gates', 'site-gates-label'].forEach"));
ok("clicking a gate explains that it is an access point, not the site",
  code.includes("access point, not the site itself"));
ok("a deactivated gate's popup says why it matters", code.includes("will not bake"));
ok("the gate popup is wired once, not on every style.load",
  !/style\.load[\s\S]{0,4000}map\.on\('click', 'site-gates'/.test(code));

// 🔴 the regression this pass exists for: gates are Points, and a Point that is a gate
// must NOT become a site marker
// 🔴 the regression this pass exists for: gates are Points, and a Point that is a gate
// must NOT become a site marker. §A moved the test from the marker loop into the layer
// filter, so the assertion moved with it — same guarantee, different mechanism.
ok("the locations layer excludes gate features",
  /id: 'locations', type: 'symbol'[\s\S]{0,400}\['==', \['get', 'type'\], 'Node'\]/.test(code));
ok("...and the layer is the only thing that draws one",
  (code.match(/id: 'locations', type: 'symbol'/g) || []).length === 1);

// 🔴 applyIptFilter() rebuilds the SAME expression and must agree with the layer
// definition, or ticking a checkbox silently reinstates the gaps.
ok("the per-IPT filter agrees with the layer's own filter about bridges",
  !/setFilter\('rail-alignment',[\s\S]{0,300}is_bridge/.test(code));

// ---- Phase 5b map change 3: routes as a dotted line --------------------------
// ⚠️ STEPPED since the 2026-09-01 thinning: the array is in width multiples, so a
// thinner line means a smaller gap, and at zoom 7 the design value would give
// 0.57 px — where a dashed line starts aliasing to solid, at exactly the zoom the
// change exists for. Wider gap below 10, design value above.
ok("the route core is dashed", /const DASH_CORE\s*=\s*\[1, 0\.55\]/.test(code));
// 🔴 Dashing only the core leaves the white casing showing through every gap and
// the route reads as a pale continuous line with coloured beads on it.
ok("🔴 the CASING is dashed too, or the dots sit on a solid white line",
  /const DASH_CASING\s*=\s*\[0\.96, 0\.28\]/.test(code));

// 🔴 2026-09-01. A step expression whose outputs were BARE ARRAYS made every route
// vanish: an array literal used as an expression output must be wrapped in
// ['literal', …], and Style.addLayer validates BEFORE adding — on failure it fires
// an error and returns without adding the layer, so all four route layers were
// silently skipped while every later layer added fine.
//
// This guard is deliberately broader than the bug: NO expression anywhere in this
// file may use a bare array as a step/case/match output. It is the shape of the
// mistake, not the one instance of it, that has to stay caught.
{
  const bareArrayOutput = /\['(step|case|match)',[^\]]*?\]\s*,\s*\[\s*[\d.]+\s*,/;
  ok("🔴 no expression uses a bare array as an output — it must be ['literal', …]",
    !bareArrayOutput.test(code.replace(/\s+/g, ' ')));
}
ok("line-dasharray is a plain constant, not an expression — cross-faded properties "
   + "have patchy expression support and two map deploys went out broken",
  !/'line-dasharray':\s*\['(step|interpolate|case|match)'/.test(code)
  && !/DASH_(CORE|CASING)\s*=\s*\['/.test(code));
ok("...and the reason is written where someone would 'improve' it back",
  /must be wrapped in \['literal'/.test(src) && /RETURNS WITHOUT ADDING THE LAYER/.test(src));
ok("all four route layers carry a dasharray",
  (code.match(/'line-dasharray': DASH_(CORE|CASING)/g) || []).length === 4);
// 🔴 A round cap extends each dash by half the line width at EACH end, so a 1.0w
// dot renders 2.0w long, the 0.333w gap is swallowed twice over, and the route
// draws SOLID — indistinguishable from the change never having been applied.
// 2026-09-02: a fifth butt-capped dashed layer, the EVR rail core, joined the four
ok("🔴 line-cap is butt on all four route layers, or the dots render solid",
  (code.match(/'line-cap': 'butt'/g) || []).length === 5
  && /id: 'evr-rail-line'[\s\S]{0,300}'line-cap': 'butt'/.test(code));
ok("the casing is a FIXED 1.25x the core at every zoom stop, or the two dash "
   + "arrays cannot draw the same period on screen",
  /WIDTH_CORE\s*=\s*\['interpolate', \['linear'\], \['zoom'\], 7, 1\.36, 12, 4,\s+16, 6\.8\]/.test(code)
  && /WIDTH_CASING\s*=\s*\['interpolate', \['linear'\], \['zoom'\], 7, 1\.7,\s+12, 5,\s+16, 8\.5\]/.test(code));
ok("⭐ at corridor zoom the route is THINNER than the alignment's fixed 2.5 px",
  /WIDTH_CORE\s*=\s*\['interpolate', \['linear'\], \['zoom'\], 7, 1\.36,/.test(code));
// ⚠️ the gap ratio is coupled to the width: a 20% thinner line is a 20% smaller gap,
// and 0.45 at the new width gives 0.61 px at zoom 7 — back into aliasing
ok("the gap ratio moved WITH the thinning, or the dots alias to solid at zoom 7",
  /gap ratio moved 0\.45 -> 0\.55 WITH the thinning/.test(src));
ok("the dasharray is NOT interpolated across zoom — it silently does nothing",
  !/'line-dasharray': \['interpolate'/.test(code));
// 🔴 REMOVED 2026-09-01 at the user's request. Asserted GONE rather than deleted
// from the suite — this layer has now been added (nine quick fixes), moved
// (12 -> 11) and removed, and a future edit must not reintroduce it by accident.
ok("🔴 the directional arrow layers are gone",
  !/'inbound-arrows'/.test(code) && !/'outbound-arrows'/.test(code));
ok("...and nothing still tries to filter them",
  !/setFilter\('inbound-arrows'/.test(code) && !/setFilter\('outbound-arrows'/.test(code));
ok("...and no ▶ glyph survives on a route layer",
  !/'text-field': '▶'/.test(code));
ok("⚠️ what went with them is written down — nothing now shows direction of travel",
  /Nothing on this map now indicates which way a/.test(src));
// 🔴 Found while removing the arrows: applyFilters() filtered the cores and never
// the casings, so filtering to one origin left every other route's white casing
// drawn. Pre-existing since Phase 2.5a; a trail of white dots now that they dash.
ok("🔴 the route CASINGS are filtered too, not just the cores",
  /setFilter\('inbound-lines-casing'/.test(code) &&
  /setFilter\('outbound-lines-casing'/.test(code));

// ---- the sidebar swatch is generated, not hard-coded -------------------------
// ⭐ It was a hard-coded gradient of the FIRST palette and survived two palette
// changes untouched, so the control panel advertised inbound-teal, brand navy and
// selection-crimson as IPT colours while the map drew palette C beside it. The
// roadmap already carried "a colour written in two places WILL drift" because this
// same element caused it once before — writing it down was not enough.
ok("🔴 the alignment swatch is generated from the band table",
  /function paintAlignmentSwatch\(\)/.test(code)
  && /window\.iptLegendRows\(\)/.test(code));
ok("...and no stale palette gradient survives in the markup",
  !/linear-gradient\(90deg,#039E86/.test(html));
ok("...and it is repainted whenever the legend is",
  /paintAlignmentSwatch\(\);/.test(code));
ok("the swatch shows the civil bands only, not the underlay wash or a muted band",
  /r\.ipt !== underlayKey\(\) && !r\.muted/.test(code));

// ---- the version handshake — GONE with the static pair (G2) ------------------
// The overlay is data from the API now; it carries its own version string, which
// the module records and the sidebar can show. There is no second file to be out
// of step with.
ok("G2: no file-pair version handshake remains", !/IPT_INDEX_VERSION/.test(code) && !/checkOverlayVersion/.test(code));
ok("G2: the package version is recorded on load", /window\.OVERLAY_VERSION = o\.version \|\| null;/.test(iptSrc));

// ---- Route alternatives -------------------------------------------------------
// 🔴 THE POINT OF THE DESIGN: its own source. Five things walk routes-source per
// feature matching "LineString with a route_id" — the KPI count, the leg filters,
// buildRouteInfo(), the forecast timeline's is_forecast stamping and the
// route-highlight lookup. An alternative in that collection would make a route's
// distance jump to whichever option is longest and would be painted as a forecast.
ok("🔴 alternatives live in their OWN source, not routes-source",
  code.includes("map.addSource('route-alts-source'"));
ok("...fed from their own endpoint",
  /\/public\/route-alternatives/.test(code));
ok("...and nothing points the alt layer at routes-source",
  !/'id': 'route-alt-lines'[\s\S]{0,300}'source': 'routes-source'/.test(code));
// (the feature TYPE is a backend fact and is asserted in test_phase5a.py, where
// route_alternatives_geojson() can actually be run — a `true` here would have been
// an assertion that passes for the wrong reason)
ok("the alt layer is added BEFORE both carriageways, so it draws underneath",
  code.indexOf("'id': 'route-alt-lines'") < code.indexOf("'id': 'outbound-lines-casing'"));
ok("thin, grey and translucent — context, not content",
  /'id': 'route-alt-lines'[\s\S]{0,500}'line-color': '#94a3b8'/.test(code) &&
  /'id': 'route-alt-lines'[\s\S]{0,600}'line-opacity': 0\.45/.test(code));
ok("solid, not dotted — the dots are what say 'this is a haul route'",
  !/'id': 'route-alt-lines'[\s\S]{0,600}'line-dasharray'/.test(code));
ok("and no casing, because a halo is what lifts a line off the basemap",
  !code.includes("'route-alt-lines-casing'"));
ok("its visibility is read from the checkbox, not a module variable",
  /function altsVisible\(\)/.test(code) &&
  /document\.getElementById\('layer-alts'\)/.test(code) &&
  /visibility: altsVisible\(\)/.test(code));
ok("there is a control for it, OFF by default",
  /id="layer-alts"/.test(html) && !/id="layer-alts" checked/.test(html));
ok("the fetch is off the critical path — a failure must not cost the map",
  /async function loadAlternatives/.test(code) && /catch\(e\)\{[\s\S]{0,200}alternatives unavailable/.test(code));
ok("...and it says how many there are, or why there are none",
  /no alternatives/.test(code));


// =============================================================================
//  Week 1, Task E — the EVR rail layer and the railhead highlight
// =============================================================================
// G2 (16 Sep): the existing-railway geometry is the package's `rail`, not a file
ok("G2: no static rail file is loaded", !/src=["']data\/evr_rail\.js/.test(html));
ok("G2: the overlay module fills window.evr_rail_data from the package", /window\.evr_rail_data = \(o\.rail/.test(iptSrc));
ok("it is NOT the alignment layer — separate sources", /addSource\('evr-rail'/.test(code) && /addSource\('alignment-source'/.test(code));

ok("there is an evr-rail source", /addSource\('evr-rail'/.test(code));
ok("...that tolerates the file being absent",
  /window\.evr_rail_data \|\| \{ type: 'FeatureCollection', features: \[\] \}/.test(code));
ok("and an evr-rail-line layer on it",
  /id: 'evr-rail-line', type: 'line', source: 'evr-rail'/.test(code));

// the build list's numbers, exactly
ok("the rail colour is the reserved #0F766E", /const RAIL_COLOR = '#0F766E'/.test(code));
// 2026-09-02 §6a restyle: a quiet grey casing + short-tick dash by default; the
// reserved rail colour only when highlighted. The old 2px/25% single line is gone.
ok("§6a: default = casing 5 px #334155 at 35%",
  /RAIL_DIM\s*=\s*\{ casingW: 5, casingC: '#334155', casingO: 0\.35/.test(code));
ok("§6a: ...under a 2 px #64748B dash with [2, 18]",
  /dashW: 2,\s*dashC: '#64748B',\s*dashO: 1\.0, dash: \[2, 18\]/.test(code));
// 🔴 REVERSED 2026-09-08 (§B). These asserted a BOLD state painted in RAIL_COLOR.
// That made provisional Natural Earth geometry — ~6.4 km out at Lelle — the loudest
// thing on the map whenever a railhead was in play. The brief: never green, never bold,
// never teal. So the assertions now refuse the state they used to require.
ok("⭐ §B: there is no bold rail state at all", !/RAIL_BOLD/.test(code));
ok("⭐ §B: the rail colour never reaches the corridor's paint",
  !/(line-color'?,\s*RAIL_COLOR)/.test(code)
  && !/casingC: RAIL_COLOR/.test(code) && !/dashC: RAIL_COLOR/.test(code));
ok("§6a: two rail layers, casing under core", /id: 'evr-rail-casing'[\s\S]{0,900}id: 'evr-rail-line'/.test(code));
ok("§6a: no IPT or reserved route colour in either rail style",
  !/(RAIL_DIM|RAIL_BOLD)\s*=[^}]*(#039E86|#f59e0b|#C2790B|#3398DB|#BF2E55|#003787|#0A1446|#4338CA|#6D28D9|#57534E|#9A3412|#9F1239|#5B21B6)/i.test(code));
ok("the old single 2px/25% style is gone", !/RAIL_DIM_WIDTH/.test(code));
// §6b's question survives, with a new job: it used to decide whether the corridor went
// BOLD, and now decides whether it TICKS. One home — railInUseOnScreen(), beside
// railFlowOn(). Two copies of "is a railhead in use this month" would have drifted the
// first time one of them learned about a filter.
ok("§B: 'a railhead is in use' has exactly one implementation",
  /function railInUseOnScreen\(\)/.test(code) && !/function railheadMovementOnScreen\(\)/.test(code));
ok("§B: it needs forecast on or the timeline open",
  /const forecastOn = \(typeof TL !== 'undefined' && TL\.on\)[\s\S]{0,180}toggle-forecast/.test(code));
ok("§B: ...and a route carrying volume NOW, inside the current filter, touching a railhead",
  /f\.properties\.is_forecast && routePassesFilters\(f\.properties\)/.test(code)
  && /locTypeById\(f\.properties\.origin_id\) === 'Railhead'[\s\S]{0,80}locTypeById\(f\.properties\.dest_id\) === 'Railhead'/.test(code));
ok("§6b: the forecast toggle recomputes it, both on and off",
  (src.match(/applyRailHighlight\(\);\s*\/\/ §6b/g) || []).length === 2);
ok("§6b: turning forecast off clears is_forecast so the rule sees no movement",
  /if \(f\.properties\) f\.properties\.is_forecast = false; \}\); sd\.setData\(d\); \}\s*applyRailHighlight/.test(code));
ok("§6b: closing the timeline re-runs the filters", /applyZoneMonth\(null\);[^\n]*\n\s*applyFilters\(\);/.test(code));
// ⭐ #0F766E must not collide with anything already meaning something on this map.
for (const reserved of ["#039E86", "#f59e0b", "#C2790B", "#3398DB", "#BF2E55",
                        "#003787", "#0A1446", "#4338CA", "#6D28D9", "#57534E",
                        "#9A3412", "#9F1239", "#5B21B6"]) {
  ok(`the rail colour is not the reserved ${reserved}`, "#0F766E" !== reserved);
}

// visibility from the checkbox, never a module variable — style.load re-adds every
// layer on a basemap switch and a drifted variable restores one the user turned off
ok("rail visibility is read from the checkbox",
  /function railVisible\(\)/.test(code)
  && /document\.getElementById\('layer-rail'\)/.test(code)
  && /visibility: railVisible\(\)/.test(code));
ok("there is a Rail network control, ON by default",
  /id="layer-rail" checked/.test(html));
// 🔴 REVERSED 2026-09-08. This used to assert the OPPOSITE — that toggleRail() moved
// the railhead marks with the corridor. That was the bug: a railhead is a LOCATION, and
// unchecking "Rail network" was hiding sites. The assertion now refuses the old wiring.
ok("⭐ the rail toggle moves the corridor and NOTHING else",
  /function toggleRail\(visible\) \{[\s\S]{0,700}\['evr-rail-casing', 'evr-rail-line'\]\.forEach/.test(code)
  && !/'evr-rail-line', 'railheads'/.test(code));

// the highlight
ok("the highlight follows the origin filter", /function applyRailHighlight\(\)/.test(code)
  && /applyRailHighlight\(\);/.test(code));
ok("...and applyFilters is what calls it",
  /function applyFilters\(\)[\s\S]{0,2600}applyRailHighlight\(\);/.test(code));
ok("it bolds only when the selected origin is a Railhead",
  /locTypeByName\(sel\) === 'Railhead'/.test(code));
ok("the loc_type comes from the Node features, not a hard-coded list",
  /function locTypeByName\(name\)/.test(code)
  && /x\.properties\.type === 'Node'/.test(code));
// ⭐ an array literal used as an expression OUTPUT must be wrapped in ['literal', ...]
// or setFilter validates, errors and silently applies nothing
ok("⭐ the id filter wraps its array in ['literal', ...]",
  /\['in', \['get', 'id'\], \['literal', ids\]\]/.test(code));
ok("heads are matched case-insensitively and by substring, both ways",
  /function railFeaturesFor\(name\)/.test(code)
  && /toLowerCase\(\)\.trim\(\)/.test(code)
  && /n\.indexOf\(hh\) >= 0 \|\| hh\.indexOf\(n\) >= 0/.test(code));
ok("⭐ §B: one style, applied unconditionally — there is nothing to return FROM",
  /const st = RAIL_DIM;/.test(code) && !/bold \? RAIL_BOLD/.test(code));
// ⭐ the road filter must be untouched: a railhead origin still isolates its hauls
ok("⭐ the existing road-route filter is not disturbed",
  /setFilter\('inbound-lines',/.test(code) && /setFilter\('outbound-lines',/.test(code)
  && /setFilter\('inbound-lines-casing',/.test(code));

// filterByNode must treat a railhead as an origin, like a quarry or a port
ok("filterByNode treats a Railhead as an origin",
  /nodeType === 'Railhead'/.test(code)
  && /nodeType === 'Quarry' \|\| nodeType === 'Hub' \|\| nodeType === 'Port'[\s\S]{0,120}filter-origin/.test(code));

// railheads drawn as a LAYER, not only a DOM marker
// §5 — its own mark, a symbol layer, generated glyph
// 2026-09-08 (§A): §5's railhead-only layer became the seven-mark location layer.
// Every guarantee it made survives; it now makes them for all seven types.
ok("§A: locations are a real SYMBOL layer, not a circle and not a DOM marker",
  /id: 'locations', type: 'symbol'/.test(code)
  && !/id: 'railheads'/.test(code) && !/new mapboxgl\.Marker/.test(code));
// 2026-09-08 (pm): locGlyph gained a fourth argument. A stockpile's image depends on
// its STOCK LEVEL, not only on its type, so the level has to reach the painter.
ok("§A: the marks are generated on a canvas, one image per type",
  /function locGlyph\(kind, fill, active, stock\)/.test(code)
  && /function addLocationImages\(m\)/.test(code));
ok("§A: ...and the stock bucket is passed through to BOTH variants of the image",
  /m\.addImage\(key, locGlyph\(spec\.kind, spec\.fill, false, spec\.stock\)/.test(code)
  && /m\.addImage\(key \+ '-on', locGlyph\(spec\.kind, spec\.fill, true, spec\.stock\)/.test(code));
ok("§A: a railhead still carries a rail over two sleepers",
  /kind === 'Railhead'/.test(code) && (code.match(/g\.fillRect\(/g) || []).length >= 3);
ok("§A: the images are re-added on style.load, guarded by hasImage",
  /if \(!m\.hasImage\(key\)\) m\.addImage\(key/.test(code)
  && /if \(!m\.hasImage\(key \+ '-on'\)\) m\.addImage/.test(code)
  // ⚠️ inside the style.load handler, not at load: a basemap switch drops every image
  // with the style. Asserted by position rather than by a size window — a window is not
  // a scope, and this file has been bitten by that before.
  && code.indexOf("addLocationImages(map);") > code.indexOf("map.on('style.load'")
  && code.indexOf("addLocationImages(map);") < code.indexOf("id: 'locations', type: 'symbol'"));
ok("§A: the legend lists all seven types", /id="loc-legend"/.test(html)
  && /const LOC_KINDS = \['Quarry', 'Port', 'Compound', 'Site', 'Railhead', 'Stockpile', 'Other'\]/.test(code));
ok("§A: the layer is filtered to Node features, by canonical kind",
  /\['in', \['get', 'loc_kind'\], \['literal', visibleLocKinds\(\)\]\]/.test(code));

// ===== 2026-09-08 (pm) — THE HUMAN'S REVIEW OF THE MORNING SLICE =================
//
// ---- 1. THE MARKS SIT ON TOP OF THE ALIGNMENT AND THE ROUTES -------------------
// ⚠️ A REGRESSION THE MORNING SLICE INTRODUCED. DOM markers are siblings of the canvas
// and are unconditionally above every layer; a symbol layer is not. Measured in
// Chromium before the fix: NINE layers drew over the marks — all three forecast layers,
// the whole rail-alignment stack, the chainage labels and the selection glow. A railhead
// with two routes converging on it was about 70% covered by the 6 px forecast casing.
ok("⭐ the location and gate layers are re-raised to the top of the stack",
  /const MARK_LAYERS = \['site-gates', 'locations', 'site-gates-label'\];/.test(code)
  && /function raiseMarks\(\)/.test(code)
  && /present\.forEach\(id => \{ try \{ map\.moveLayer\(id\); \} catch \(e\) \{\} \}\);/.test(code));
// moveLayer forces a style recalculation and applyFilters() runs on every keystroke in
// the filter row, so the no-op case has to be free.
ok("⭐ ...and does nothing when they are already last, in order",
  /const tail = ids\.slice\(ids\.length - present\.length\);/.test(code)
  && /if \(tail\.join\('\|'\) === present\.join\('\|'\)\) return;/.test(code));
// Layer order in Mapbox is ADD order and several of the layers above are added lazily,
// so there is no single add site to insert before. Every lazy adder has to re-raise, and
// applyFilters() is the belt to that braces.
ok("⭐ every lazy layer adder re-raises the marks afterwards",
  /raiseMarks\(\);\n    \}/.test(code)
  && (code.match(/raiseMarks\(\);/g) || []).length >= 8);
ok("⭐ ...including the three forecast layers, which are the ones that actually covered them",
  /'text-halo-width':2\}\}\);\s*\n\s*raiseMarks\(\);/.test(code)
  && /'line-dasharray':\[0,4,3\]\}\}\);\s*\n\s*raiseMarks\(\);/.test(code));
ok("⭐ ...and applyFilters, which runs after every user action",
  /markRouteEnds\(\);\s*\n\s*raiseMarks\(\);/.test(code));

// ---- 2. QUARRY IS A CIRCLE AGAIN ------------------------------------------------
// ⚠️ REVERSES the morning's "shape discriminates, not colour" for five of the seven
// types. The human's call: the pre-08 Sep map was circles-with-symbols and they preferred
// it. Railhead and Compound stay squares.
// ⚠️ the first version of this assertion tested !/\/\/ diamond/ against `code`, which
// strips // comments — it could never have failed. Assert the PATH, not the label.
ok("⭐ the quarry is a circle with a pick, not a diamond",
  !/g\.moveTo\(cx, cy - r\); g\.lineTo\(cx \+ r, cy\)/.test(code)
  && !/\/\/ diamond/.test(src)
  && /kind === 'Quarry'/.test(code)
  // locShapePath now branches on ONE thing: square for the two corridor types, circle
  // for everything else. No hexagon, no diamond.
  && /\} else \{ {14}\/\/ Quarry, Stockpile, Port, Site, Other: circle/.test(src));
ok("⭐ ...and the pick's head is built FROM the handle vector, so the two cannot drift",
  /const dx = bx - ax, dy = by - ay, dl = Math\.hypot\(dx, dy\) \|\| 1;/.test(code)
  && /const a0 = Math\.atan2\(uy, ux\), sw = Math\.PI \* 0\.29;/.test(code));
ok("the three material fills survive the reshape",
  /if \(m\.indexOf\('sand'\) >= 0\) return '#ffd700';/.test(code)
  && /if \(m\.indexOf\('limestone'\) >= 0\) return '#ffffff';/.test(code)
  && /const QUARRY_DEFAULT_FILL = '#a0522d';/.test(code));

// ---- 3. THE STOCKPILE IS A GAUGE ------------------------------------------------
ok("⭐ a stockpile fills to its recorded stock level",
  /const STOCK_STEPS = \[0, 20, 40, 60, 80, 100\];/.test(code)
  && /function stockBucket\(props\)/.test(code)
  && /function stockPilePath\(g, cx, cy, r\)/.test(code));
// the mark and the popup read the same fact, so they cannot disagree about one pile
ok("⭐ ...taking `over` from the backend, and only falling back to the ratio if it is absent",
  /props\.stock_over == null \? \(bal > cap\)/.test(code)
  && /!\(props\.stock_over === false \|\| props\.stock_over === 'false'\)/.test(code));
ok("⭐ ...and a pile with NO recorded capacity is dashed, never drawn as a measured one",
  /return 'na';/.test(code)
  && /if \(stock === 'na'\) g\.setLineDash\(\[5, 4\]\);/.test(code));
// cream on cream is a few percent of luminance apart; the boundary has to be a LINE
ok("⭐ ...with an ink rule at the fill height, which is the readable part",
  /if \(stock !== 'over' && pct < 1 && pct > 0\)/.test(code)
  && /g\.strokeStyle = '#1F2024'; g\.lineWidth = 2\.2;/.test(code));
ok("the level reaches the image key, so one bucket is one image",
  /else if \(kind === 'Stockpile'\) suffix = '-' \+ stockBucket\(props\);/.test(code));
ok("over capacity uses the same red as the Clash level",
  /const STOCK_OVER = '#DC2626';/.test(code));

// ---- 4. THE COMPOUND IS A SOLID MARK --------------------------------------------
// ⚠️ REVERSED, not deleted: the morning's compound was a thin white outline square with
// a gap for the gate, and below about 22 CSS px it was an empty amber square.
ok("⭐ the compound is a solid site cabin, not an outline",
  !/g\.strokeRect\(cx - s \/ 2, cy - s \/ 2, s, s\);/.test(code)
  // ⚠️ `code` has // comments stripped — a comment marker has to be grepped in `src`
  && /\/\/ the door/.test(src)
  && /g\.fillRect\(cx - w \/ 2, top, w, h \* 1\.18\);/.test(code));


// ⭐ the honesty channel. The picture reads as authoritative; the popup is where the
// caveat lives, exactly as the alignment's gap bridges do.
ok("⭐ clicking the rail line opens a popup", /map\.on\('click', 'evr-rail-line'/.test(code));
ok("⭐ ...built by railPopupHTML", /function railPopupHTML\(p\)/.test(code));
// ⚠️ RUN IT, do not grep it. A source-level check for "Provisional geometry" passed
// on a deliberately broken tree where the caveat had been branched out with
// `if (false)` — the string was still in the file and unreachable. Executing the
// function is the only assertion that proves the caveat actually renders.
const _railFn = (() => {
  const i = code.indexOf("function railPopupHTML(p) {");
  if (i < 0) return null;
  const j = code.indexOf("\n    function gatePopupHTML", i);
  const body = j > i ? code.slice(i, j) : null;
  if (!body) return null;
  try {
    // H1: the popup prints the length in the tenant's unit through fmtDist()/DU(); the
    // isolated function is given km versions of them (what a km tenant sees)
    return new Function("RAIL_COLOR", "fmtDist", "DU", body + "\nreturn railPopupHTML;")(
      "#0F766E", (km, dp) => (km == null ? "—" : Number(km).toFixed(dp == null ? 1 : dp)), () => "km");
  } catch (e) { return null; }
})();
ok("railPopupHTML can be isolated and run", typeof _railFn === "function");
const _railHtml = _railFn ? _railFn({
  name: "Rapla - Lelle", operator: "Eesti Raudtee (EVR)",
  heads: '["Rapla","Lelle"]', length_km: 16.6, provisional: "true",
  accuracy_note: "wrong at the Lelle end by ~6.4 km",
  source: "Natural Earth 10m railroads",
}) : "";
ok("⭐ the rendered popup SAYS the geometry is provisional",
  _railHtml.includes("Provisional geometry"));
ok("⭐ ...and renders the feature's own accuracy note",
  _railHtml.includes("6.4 km"));
ok("H1 (HU5): the rail popup prints the length in the tenant's unit (16.60 km here)",
  _railHtml.includes("16.60 km") && /const DU = \(\) => \(TENANT\.distance_unit === 'mi' \? 'mi' : 'km'\);/.test(code)
  && (code.match(/fmtDist\(/g) || []).length >= 5 && /distance_unit: 'km'/.test(code));
ok("⭐ ...and names the source", _railHtml.includes("Natural Earth"));
ok("⭐ ...and parses the stringified heads array rather than printing JSON",
  _railHtml.includes("Rapla · Lelle") && !_railHtml.includes('["Rapla"'));
// a real (non-provisional) file must NOT carry the caveat, or it becomes wallpaper
const _railOk = _railFn ? _railFn({ name: "x", provisional: false, source: "OSM" }) : "x";
ok("⭐ a file marked provisional:false shows NO caveat",
  !_railOk.includes("Provisional geometry"));
// properties cross Mapbox's boundary as strings — 'false' is truthy
ok("stringified properties are parsed, not trusted",
  /typeof heads === 'string'/.test(code)
  && /p\.provisional === false \|\| p\.provisional === 'false'/.test(code));

// Task D2's popup line
ok("the node popup shows stock only when BOTH numbers exist",
  /props\.stock_balance != null && props\.capacity_qty != null/.test(code));
ok("...and there is no chart", !/new Chart\(/.test(code));

// Never build: no week scrubber on the public map, no actuals painted here
ok("the timeline is still monthly — no week scrubber",
  !/week_index/.test(code) && !/scrubber/i.test(code));
ok("actuals are not painted on the public map", !/actual_qty/.test(code));

// =============================================================================
//  2026-09-02 §8 — timeline warnings
// =============================================================================
// ⚠️ 2026-10-06 — REVERSED, not deleted. The stack above the timeline became a PANEL
// docked under the bar, top-right. The timeline bar itself stays where it was.
ok("§8: the conditions panel is docked under the bar, top-right, not above the timeline", /id="tl-warnings"/.test(html)
  && /#tl-warnings\{[^}]*top:84px;[^}]*right:12px/.test(html) && !/#tl-warnings\{[^}]*bottom:74px/.test(html)
  && /#timeline-bar\{[^}]*bottom:18px/.test(html));
ok("§8 (2026-10-06): the panel is opened from a pill in the bar that counts the levels",
  /id="kpi-conditions"/.test(html) && /function toggleConditions\(\)/.test(code)
  && /function renderConditionsPill\(live\)/.test(code) && /over capacity/.test(code) && /route limit/.test(code));
ok("§8 (2026-10-06): a month with a red condition opens the panel once by itself",
  /live\.some\(i => i\.lvl === 'clash'\) && !WARN\.autoOpened/.test(code));
ok("§8 (2026-10-06): an over-capacity pile is ringed on the map so map and number agree",
  /id: 'cond-ring', type: 'circle'/.test(code) && /setCondRing\(live\.filter\(i => i\.kind === 's'\)\.map\(i => i\.id\)\)/.test(code));
// 🔴 a Node's id property is `id` (network.py), not `location_id`; the first cut filtered
// on the wrong key and would have ringed nothing. Pinned.
ok("§8 (2026-10-06): the ring and the fly-to key on the Node's `id` property",
  /\['in', \['get', 'id'\], \['literal', ids\]\]/.test(code) && /x\.properties\.id === id\)/.test(code)
  && !/\['get', 'location_id'\]/.test(code));
ok("§8 (2026-10-06): every row has Show on map", /class="show" onclick="showCondition\(/.test(code)
  && /function showCondition\(kind, id\)/.test(code));
ok("§8: rebuilt on every tick and cleared when the timeline closes",
  /applyFilters\(\);\s*renderTimelineWarnings\(m\);/.test(code) && /TL\.on=false;\s*renderTimelineWarnings\(null\)/.test(code));
// 12 Oct 2026 (D21/D33) — RENAMED: a fourth source, the route's planning flag, joined the three.
// Still no weather API. (This pin asserts the endpoint strings, not a count — the count is
// pinned by the cap-source block near the end of this file.)
ok("§8: four sources and no others — Tark Tee / NH, stockpile over, seasonal, planning flag; no weather API",
  code.includes("/routes/restrictions") && code.includes("/public/stockpile-timeline")
  && code.includes("META.seasonal") && code.includes("Number(p.max_vehicles_per_day)")
  && !/weather|openweather|forecast\.io/i.test(code.slice(code.indexOf("const WARN"), code.indexOf("(function initAnalysis"))));
ok("§8: only routes carrying volume THIS month, inside the filter",
  /if \(!f\.properties\.is_forecast \|\| !routePassesFilters\(f\.properties\)\) return;/.test(code));
ok("§8: a stale month cannot paint over the current one", /if \(TL\.month !== month \|\| !TL\.on\) return;/.test(code));
// 2026-10-06 — REVERSED: the panel scrolls (max-height) instead of truncating to three
ok("§8: no +N more truncation; the panel scrolls", !/live\.slice\(0, 3\)/.test(code) && !code.includes("more</div>")
  && /#tl-warnings\{[^}]*max-height:[^}]*overflow:auto/.test(html));
ok("§8: dismissible, per month", /function dismissWarning\(key\)/.test(code) && /\|\$\{month\}`/.test(code));
ok("§8: seasonal windows fold the absolute month to a calendar month", /const cal = \(\(month - 1\) % 12\) \+ 1;/.test(code));
ok("§8: the seasonal check honours restricted_vehicles", /rv\.length === 0 \|\| \[\.\.\.vs\]\.some\(v => rv\.includes\(v\)\)/.test(code));
// 2026-10-06 — REVERSED: a row is a dot, a plain NOUN and one sentence; the month is in
// the panel's title, once, not on every row
ok("§8: each row reads noun + sentence, with the month in the panel title",
  /<b>\$\{esc\(i\.noun\)\}<\/b><span class="what">\$\{esc\(i\.what\)\}<\/span>/.test(code)
  && /<b>Conditions in \$\{esc\(monthLabel\(month\)\)\}<\/b>/.test(code));
ok("§8: fetch failures degrade to no warnings, not a broken map",
  /\.catch\(\(\) => \{ WARN\.restr = \{\}; return WARN\.restr; \}\)/.test(code));

// §4 — Street View empty state, no extra request
ok("§4: ZERO_RESULTS shows 'No Street View here' and returns before any image request",
  /meta\.status === 'ZERO_RESULTS'\)\{[\s\S]{0,200}No Street View here[\s\S]{0,80}return;/.test(code)
  && code.indexOf("No Street View here") < code.indexOf("'/streetview?lat='"));
ok("§4: no key and a fetch failure still show nothing", /if\(!meta \|\| !meta\.available\) return;/.test(code));
ok("§4: no second imagery provider", !/mapillary|bing.*streetside|kartaview/i.test(code));

// ---- 2.5b: the admin pages were renamed -----------------------------------------
// The map's empty-network hint tells the user where to go and bake. It named the
// "Data Management tab", which 2.5b split into Locations / Routes / Zones in the rail.
ok("the empty-network hint names a page that still exists",
  !src.includes("Data Management tab") && src.includes("Routes page"));


// =============================================================================
//  2026-09-07 — the forecast-timeline pass: EVR marches with the hauls, the KPI
//  panel moved and says what the month is doing, and the two ends of every live
//  route are named on the map
// =============================================================================

// ---- 1. the EVR corridor marches while the timeline plays --------------------
ok("there is a marching overlay on the EVR source, not an animation of the corridor",
  /id: 'evr-rail-flow', type: 'line', source: 'evr-rail'/.test(code)
  && /id: 'evr-rail-flow'[\s\S]{0,300}'line-color': '#ffffff'/.test(code));
ok("...starting hidden, so a paused map is not marching before Play is pressed",
  /id: 'evr-rail-flow'[\s\S]{0,200}visibility: 'none'/.test(code));
// ⭐ THE RULE. Play AND the checkbox — not one or the other. A corridor that marched
// with its own layer switched off would be drawing something the user turned off.
// ⭐ NARROWED 2026-09-08 (§B). Play AND the checkbox was not enough: the corridor
// ticked in every month, which said "rail" about months with no rail movement in them.
// A third condition, and the brief's own test — "animation only when the playhead month
// has a Railhead movement".
ok("⭐ the overlay ticks only on Play, with the checkbox on, in a month that USES the rail",
  /function railFlowOn\(\) \{\s*return !!\(typeof TL !== 'undefined' && TL\.playing\) && railVisible\(\) && railInUseOnScreen\(\);/.test(code));
ok("...pause / scrub / close hides it again",
  /function stopFlowAnimation\(\)\{[\s\S]{0,320}applyRailFlow\(\);/.test(code)
  && /if\(!TL\.playing\)\{[\s\S]{0,160}applyRailFlow\(\); return; \}/.test(code));
ok("⭐ the rail steps on the SAME dash index as the hauls, not a second cycle",
  /_dashIx=\(_dashIx\+1\)%DASH_SEQ\.length;[\s\S]{0,400}setRailFlowDash\(DASH_SEQ\[_dashIx\]\)/.test(code));
// the pinned trio is the CHECKBOX toggle. The flow layer must not join it, or the
// checkbox alone would switch it to 'visible' and it would march on a paused map.
ok("⭐ the flow layer is toggled separately from the corridor pair",
  /\['evr-rail-casing', 'evr-rail-line'\]/.test(code)
  && !/'evr-rail-line', 'evr-rail-flow'\]/.test(code)
  && /forEach\(l => toggleLayer\(l, visible\)\);\s*applyRailFlow\(\);/.test(code));
ok("the overlay carries the same railhead narrowing as the corridor under it",
  /if \(map\.getLayer\('evr-rail-flow'\)\) map\.setFilter\('evr-rail-flow', idFilter\);/.test(code));
// ⚠️ EVR is reference geometry. It is not a haul and must never be counted as one.
ok("⭐ EVR is still not in routes-source and still not a counted route",
  !/source: 'routes-source'[\s\S]{0,120}evr-rail/.test(code)
  && !/evr[\s\S]{0,60}mRoutes\.add/.test(code));
ok("the EVR note carries the provisional caveat permanently, not only when dimmed",
  src.includes("Provisional corridor — reference only, not survey. Click the line for detail.")
  && /note\.innerHTML =[\s\S]{0,40}'Provisional corridor/.test(src));
ok("...and the click popup is still railPopupHTML",
  /function railPopupHTML\(p\)/.test(code) && /map\.on\('click', 'evr-rail-line'/.test(code));

// ---- 2. the KPI panel ---------------------------------------------------------
ok("the panel has a month title", /id="kpi-title"/.test(html) && code.includes("set('kpi-title'"));
ok("...naming the month on the playhead",
  /set\('kpi-title', label \+ ' \\u00b7 what is moving'\)/.test(code));
ok("the breakdown is chips, not a faint run-on line",
  /class="kpi-chips" id="kpi-breakdown"/.test(html)
  && /<span class="kpi-chip/.test(code) && !/const line = \(obj, suffix\)/.test(code));
// ⭐ THREE numbers per chip, and the third is TONNES on purpose. The map unit is
// 'vehicles' by default, and in that unit "material/day" and "movements/day" are the
// same number — printing both would put the 04 Sep correction back on screen.
// 11 Oct 2026 NARROWED: the middle figure is called two-way movements (the user), still three quantities
ok("⭐ §D: every chip carries vehicles, two-way movements AND tonnes",
  /veh\/d/.test(code) && /two-way\/d/.test(code) && /t\/d<\/span>/.test(code)
  && /g\.t \+= \(l\.qty_t \|\| 0\)/.test(code));
// vehicles ceil() PER LINE, exactly as the headline does — a vehicle on one route
// cannot also be on another, and the groups must add up to the card above them
ok("⭐ §D: a group's vehicles are summed per line, not ceilinged once",
  /g\.fleet \+= Math\.ceil\(\(l\.vehicle_loads \/ wdv\) \/ l\.trips_per_vehicle_day\)/.test(code));
ok("§D: a group is divided by the months it appeared in, not the window length",
  /const gm = Math\.max\(1, g\.months\.size\);/.test(code));
ok("⭐ names written with innerHTML are escaped",
  /const esc = t => String\(t\)\.replace\(\/\[&<>"\]\/g/.test(code));
// "no zeros" — an empty month printing 0 routes read as a measured zero rather than as
// nothing approved. Both are dashes now.
ok("⭐ an empty month shows dashes, not a zero route count",
  /if \(!mVeh\.length\) \{[\s\S]{0,260}set\('kpi-routes', '—'\)/.test(code)
  && !/set\('kpi-routes', 0\)/.test(code));
ok("...and it says which month is empty",
  /set\('kpi-title', label \+ ' \\u00b7 nothing approved'\)/.test(code));
// 🔴 the vehicles label carries "(N lines unbaked)" for the month it was computed for.
// Neither the no-month branch nor the empty-month branch reset it, so closing the
// timeline left that caveat sitting under a dash, about a month no longer on screen.
ok("⭐ both empty branches reset the vehicles LABEL, not just the value",
  (code.match(/set\('kpi-vehicles-label', 'Vehicles needed'\)/g) || []).length >= 2);
// ⚠️ 2026-10-06 — REVERSED: on a phone the bar stays at the TOP as a 3x2 grid, the note
// hidden (it is a tooltip everywhere now)
ok("on a phone the bar stays at the top as a 3x2 grid with the note hidden",
  /@media \(max-width:1023px\)\{[\s\S]{0,1200}#kpi-hud[\s\S]{0,300}top:0;/.test(html)
  && /#kpi-cards\{ display:grid; grid-template-columns:repeat\(3, minmax\(0, 1fr\)\)/.test(html)
  && /#kpi-hud \.kpi-note\{ display:none; \}/.test(html));
// 🔴 both used to sit at bottom:74px. 07 Sep moved the stack to a FIXED bottom:190px,
// which is not enough — the stack is as tall as its contents, and a month with three
// warnings landed back on the bar. Found by giving the browser check a month that has
// warnings. It is measured now; 190px is only the floor.
// ⚠️ 2026-10-06 — REVERSED: the panel sits UNDER the bar, so it is the TOP that is
// measured; 190px is the CSS floor
ok("⭐ the phone conditions panel clears the KPI bar, by measuring it",
  /@media \(max-width:1023px\)\{[\s\S]{0,3400}#tl-warnings\{ top:190px;/.test(html)   // 9 Oct: the block grew (notice strip, tablet)
  && /function positionWarnStack\(\)/.test(code)
  && /window\.innerWidth > 1023 \|\| !kpi/.test(code)   // 9 Oct: measured below 1024, the stacked-bar range
  && /box\.style\.top = \(Math\.round\(h\) \+ 8\) \+ 'px'/.test(code));
ok("...and it re-measures when the card changes height or the window resizes",
  /setHTML\('kpi-breakdown', chips\);\s*positionWarnStack\(\);/.test(code)
  && /window\.addEventListener\('resize', positionWarnStack\)/.test(code));
ok("the four cards are one row on a phone, two on the desktop",
  /id="kpi-cards"/.test(html) && /#kpi-cards\{ display:flex/.test(html));

// ---- 3. the ends of the live routes, as ICONS (2026-09-08, §C) ------------------
// 🔴 THE 07 SEP CALLOUT PLATES ARE GONE and these assertions are REVERSED, not deleted.
// They pinned a white name plate per end, a cap of six, a rectangle collision skip and a
// moveend re-placement. Every one of those existed because six name plates cover each
// other — which is the human's point: it was a list lying on top of a map. The emphasis
// is the location icon itself now.
ok("⭐ no callout component survives anywhere",
  !/od-callout/.test(html) && !/renderOdCallouts/.test(code)
  && !/OD_MAX/.test(code) && !/OD_BOX_W/.test(code));
ok("the ends are marked by stamping is_end on the Node feature",
  /function markRouteEnds\(\)/.test(code) && /f\.properties\.is_end = on/.test(code));
ok("⭐ ...which the ONE locations layer reads as a bigger image, not a second layer",
  /'icon-image': \['case', \['coalesce', \['get', 'is_end'\], false\],/.test(code)
  && /\['concat', \['get', 'loc_icon'\], '-on'\]/.test(code)
  // exactly one symbol layer draws a location, in either state
  && (code.match(/id: 'locations', type: 'symbol'/g) || []).length === 1);
// ⚠️ REVERSED 2026-09-08 (pm), not deleted. This pinned "+2 px with a 1 px halo", which
// is what §C asked for in the morning and what shipped. It is the wrong treatment: it was
// measured in Chromium at 26 -> 34 CSS px, which is only legible next to an UNUSED mark,
// and in a busy month almost every mark is in use. The human could not see it at all and
// asked for the feature as though it had never been built. So the assertion now pins the
// ring AND the dimming, and REFUSES the size-only treatment coming back.
ok("§C: the in-use mark is a WHITE RING, not a size change",
  /locShapePath\(g, kind, cx, cy, r \+ 6\);/.test(code)
  && /g\.lineWidth = 5; g\.strokeStyle = '#ffffff'; g\.stroke\(\);/.test(code)
  && /g\.lineWidth = 2; g\.strokeStyle = 'rgba\(10,20,70,0\.75\)'/.test(code));
ok("⭐ §C: ...and the mark itself is the SAME SIZE in both states",
  !/if \(active\) r \+= 4;/.test(code)
  && !/g\.strokeStyle = 'rgba\(10,20,70,0\.55\)'/.test(code));
// the half that cannot live in an image: what is NOT in use goes translucent
ok("⭐ §C: everything not in use is dimmed with icon-opacity while a month is on screen",
  /const LOC_DIM_OPACITY = 0\.34;/.test(code)
  && /function applyLocationDim\(dimming\)/.test(code)
  && /setPaintProperty\('locations', 'icon-opacity', dimming/.test(code)
  && /\['case', \['coalesce', \['get', 'is_end'\], false\], 1, LOC_DIM_OPACITY\]/.test(code));
ok("⭐ §C: ...driven by the SAME `live` flag the ends themselves use",
  /if \(changed\) src\.setData\(a1_data\);\s*\n[^\n]*\n[^\n]*\n[^\n]*\n\s*applyLocationDim\(live\);/.test(code));
ok("only the lines carrying volume this month, inside the filter",
  /if \(!p\.is_forecast \|\| !routePassesFilters\(p\)\) return;/.test(code));
ok("...one carriageway only", /if \(p\.type !== 'Inbound Highway'\) return;/.test(code));
ok("⭐ nothing is emphasised with the timeline shut and forecast off",
  /const live = \(typeof TL !== 'undefined' && TL\.on\)/.test(code));
ok("it follows the playhead and every filter change",
  /applyRailHighlight\(\);\s*markRouteEnds\(\);/.test(code));
// ⚠️ setData on this source runs on every timeline tick; only when something flipped.
ok("⭐ the source is only re-set when a mark actually changed",
  /if \(changed\) src\.setData\(a1_data\);/.test(code));
ok("the existing click popup is the only name surface, and it still works",
  /map\.on\('click', 'locations'/.test(code) && /function locationPopupHTML\(props, svId\)/.test(code));

// ---- the two orderings the brief pins -----------------------------------------
ok("⭐ applyZoneMonth(null) is still followed immediately by applyFilters()",
  /applyZoneMonth\(null\);\s*applyFilters\(\);/.test(code));
ok("⭐ applyFilters() is still followed immediately by renderTimelineWarnings(m)",
  /applyFilters\(\);\s*renderTimelineWarnings\(m\);/.test(code));

// ---- §B, 2026-09-08: the corridor is grey and ticks only when the rail is used -----
ok("⭐ §B: the sidebar note says what the ticking means, in both states",
  src.includes("ticking: a movement this month starts or ends at a railhead")
  && src.includes("static grey unless a movement this month uses a railhead"));
// G2 narrowing: the geometry is no longer a file — it is the package's `rail`
ok("§B: the geometry is the package's, and the popup is untouched",
  !src.includes("data/evr_rail.js") && /window\.evr_rail_data \|\| \{ type: 'FeatureCollection', features: \[\] \}/.test(code)
  && /function railPopupHTML\(p\)/.test(code));
ok("§B: applyRailHighlight re-applies the flow rule, so a filter change lands on it too",
  /if \(note\) note\.innerHTML =[\s\S]{0,260}applyRailFlow\(\);/.test(code));

// ---- §E, 2026-09-08: the warning stack has three NAMED levels ---------------------
// ⚠️ 2026-10-06 — REVERSED: the level WORD is gone. The dot's colour plus a plain noun
// ("Over capacity", "Exceeds a mass limit", "Seasonal window") carry the level; the
// three level CLASSES stay so the dots and the sort agree.
ok("§E: the levels are a coloured dot plus a plain noun, never an uppercase level word",
  !/LVL_NAME/.test(code) && !/class="lvl"/.test(code)
  && /\.tl-warn\.clash \.cond-dot\{ background:#C2321C; \}/.test(html)
  && /noun: 'Over capacity'/.test(code) && /noun: 'Seasonal window'/.test(code));
ok("§E: a stockpile past capacity is a CLASH",
  /lvl: 'clash', who: sp\.name/.test(code));
// ⚠️ a Tark Tee 'breach' is a vehicle-versus-limit verdict on a drivable road, not an
// impossibility — and it cannot judge a weak bridge at all (§A2), so it must never be
// the loudest thing on screen.
ok("§E: a Tark Tee exceed is a WARNING, even when its own severity says breach",
  /lvl: 'warn', who: p\.route_id/.test(code) && !/sev: 'breach'/.test(code));
ok("§E: a seasonal window is a CAUTION", /lvl: 'caution', who: p\.route_id/.test(code));
ok("§E: clash sorts above warning sorts above caution",
  /lvl: 'clash'[\s\S]{0,400}sort: 0 \}/.test(code)
  && /lvl: 'warn', who: p\.route_id[\s\S]{0,900}sort: worst\.severity === 'breach' \? 1 : 2/.test(code)
  && /lvl: 'caution'[\s\S]{0,300}sort: 3 \}/.test(code));
// 🔴 the second Clash source the brief names has NO PRODUCER anywhere in the product.
// Inventing what "two conflicting movements" means is the human's call, not mine.
ok("⭐ §E: the missing Clash source is written down, not invented",
  src.includes("THE SECOND CLASH SOURCE THE BRIEF NAMES DOES NOT EXIST")
  && /TIME model, which is Phase 7/.test(src)
  && /gate_blockers` is a deactivated gate refusing/.test(src));
// 12 Oct 2026 — RENAMED (see the §8 twin above): the planning-flag source is the fourth and last
ok("§E: four sources, the planning flag the fourth, and no weather API",
  code.includes("/routes/restrictions") && code.includes("/public/stockpile-timeline")
  && code.includes("META.seasonal") && code.includes("noun: 'Over a planning flag'") && !code.includes("planning cap")   // 12 Oct fix pass: one noun
  && !/weather|openweather|forecast\.io/i.test(code.slice(code.indexOf("const WARN"), code.indexOf("(function initAnalysis"))));
// the brief's own test: the stack is NOT in the KPI card
ok("⭐ §E: the stack is its own element, outside #kpi-hud",
  /id="tl-warnings"/.test(html)
  && html.indexOf('id="tl-warnings"') > html.indexOf("</div>", html.indexOf('id="kpi-hud"')));
ok("⭐ §E: no level word appears anywhere inside the KPI card markup",
  !/(Clash|Caution)/.test(html.slice(html.indexOf('id="kpi-hud"'), html.indexOf('id="tl-warnings"'))));
ok("§E: dismissals are keyed per month, so changing month brings them back",
  /key: `s\|\$\{sp\.location_id\}\|\$\{month\}`/.test(code)
  && /key: `r\|\$\{p\.route_id\}\|\$\{month\}`/.test(code));

// ---- §F ride-alongs, 2026-09-08 ---------------------------------------------------
// F1: "412 vehicles" on a route was the same confusion the 04 Sep correction was about —
// 412 is not 412 lorries, it is 412 loads out and back.
// ⚠️ 2026-09-15 — NARROWED, NOT DELETED (lesson 1). The label is still not "vehicles";
// it now also carries the rate, because the figure beside it became a daily one.
ok("§F1: the forecast route label says Two-way, not vehicles",
  /const FORECAST_LABEL_UNIT = 'Two-way \/ day';/.test(code)
  && !/const FORECAST_LABEL_UNIT = '[^']*vehicles/i.test(code)
  && (code.match(/\['concat', \['get', 'f_avg'\], ' ', FORECAST_LABEL_UNIT\]/g) || []).length === 2
  && !/\['get', 'f_unit'\]\]/.test(code));
ok("§F1: ...and the FIGURE is untouched — f_unit still rides on the feature",
  /f\.properties\.f_unit = m\.unit/.test(code) && /f\.properties\.f_unit=unit/.test(code));

// ---- 2026-09-15 · the route label is a DAILY rate, and the divisor is the server's ----
ok("§0915-1: the label's figure is per working day, never the month's total",
  // timeline path: the month's volume goes through perWorkingDay(), not Math.round()
  /f\.properties\.f_avg=perWorkingDay\(vol\)/.test(code)
  && !/f\.properties\.f_avg=Math\.round\(vol\)/.test(code)
  // window path: the server's per_day, with avg only as a fallback
  // 12 Oct second fix pass — NARROWED: the fallback is the monthly avg put through perWorkingDay(), never the bare
  // monthly figure (it printed under "Two-way / day" and drew the line at full width by volume)
  && /f\.properties\.f_avg = \(m\.per_day != null\) \? m\.per_day : perWorkingDay\(m\.avg\);/.test(code)
  && !/f\.properties\.f_avg = \(m\.per_day != null\) \? m\.per_day : m\.avg;/.test(code));
ok("§0915-2: the month figure is KEPT on the feature, not thrown away",
  /f\.properties\.f_month_total=Math\.round\(vol\)/.test(code)
  && /f\.properties\.f_month_avg = m\.avg/.test(code));
ok("§0915-3: the divisor comes from the feed, and there is exactly one of it",
  /let FORECAST_WORKING_DAYS = 22;/.test(code)
  && (code.match(/FORECAST_WORKING_DAYS = (?:m|j)\.working_days/g) || []).length === 2
  // the only place a month figure is divided by a day count
  && (code.match(/monthTotal \/ wd/g) || []).length === 1
  && !/\/\s*22\b/.test(code.replace(/FORECAST_WORKING_DAYS > 0 \? FORECAST_WORKING_DAYS : 22/g, "")));
ok("§0915-4: the timeline bar says trips, not vehicles — and only for the loads unit",
  /TL_UNIT_WORD = \{ vehicles: 'trips'/.test(code)
  && /\(count===1\?' route · ':' routes · '\)\+Math\.round\(sum\)\+' '\+unitWord\(unit\)/.test(code)   // 12 Oct fix pass: "1 route"
  && !/' routes · '\+Math\.round\(sum\)\+' '\+unit;/.test(code)
  // a tonnage must NOT be called trips
  && /t: 't', m3: 'm³'/.test(code));
ok("§0915-5: the timeline label can no longer be overlapped by the speed select",
  /#tl-label\{[^}]*flex:0 0 auto;[^}]*\}/.test(html)
  && /#tl-speed\{[^}]*flex:0 0 auto;[^}]*width:50px;[^}]*\}/.test(html)
  // the range is the one item that may shrink
  && /#timeline-bar input\[type=range\]\{[^}]*flex:1 1 250px;[^}]*\}/.test(html));
// F4: extruded buildings, default OFF
ok("§F4: there is a 3D buildings control and it is NOT checked",
  /id="layer-buildings"/.test(html) && !/id="layer-buildings" checked/.test(html));
ok("§F4: it is fill-extrusion off Mapbox's own building layer, not an ortho mesh",
  /type: 'fill-extrusion', source: 'composite'/.test(code)
  && /'source-layer': 'building'/.test(code) && !/mesh|photogrammetr/i.test(code));
// ⚠️ the Maa-amet orthophoto basemap is RASTER and has no composite source. addLayer
// would fire an error and return having added nothing — the 2026-09-01 silent failure.
ok("⭐ §F4: guarded on the composite source, with the sidebar told when it is absent",
  /if \(!map\.getSource\('composite'\)\) \{/.test(code)
  && src.includes("not available on this basemap"));
ok("§F4: only re-added on style.load when the checkbox is on",
  /if \(buildingsVisible\(\)\) ensureBuildingLayer\(\);/.test(code));

// ---- 2026-09-11 pm — the timeline's play speed ---------------------------------------
ok("a play-speed select sits in the timeline bar (¼× to 4×, 1× selected by default)",
  // NARROWED 12 Oct 2026 evening (M3 bar): each option also says the seconds a month ("1× · 0.75 s a month")
  /<select id="tl-speed" onchange="setTimelineSpeed\(this\.value\)"/.test(html) && html.includes('<option value="1" selected>1× · 0.75 s a month</option>')
  && html.includes('<option value="0.25">') && html.includes('<option value="4">'));
ok("one step length at 1×, divided by the speed — the ONLY interval the timeline uses",
  code.includes("const TL_STEP_MS = 750;") && (code.match(/setInterval\(tickTimeline, TL_STEP_MS \/ TL\.speed\)/g) || []).length === 2
  && !/setInterval\([^)]*,\s*750\)/.test(code));
ok("changing the speed while playing restarts the interval at the new pace without moving the month",
  /if\(TL\.playing\)\{ clearInterval\(TL\.timer\); TL\.timer = setInterval\(tickTimeline/.test(code) && !/function setTimelineSpeed[\s\S]*?TL\.month\s*=/.test(code.slice(code.indexOf("function setTimelineSpeed"), code.indexOf("function tickTimeline"))));
ok("the speed is remembered per browser and shown when the bar opens; a bad value is ignored",
  code.includes("localStorage.getItem('modus_tl_speed')") && code.includes("localStorage.setItem('modus_tl_speed'") && code.includes("if(!(sp > 0)) return;")
  && code.includes("sel.value=String(TL.speed)"));

// ---- H10 (8 Oct 2026): the map's guide -------------------------------------------
// Four coach-mark cards for the demo tenant only, anchored by id; localStorage in
// try/catch; a Guide button beside the demo notice; in-page; the Mapbox instance untouched.
{
  const gs = code.match(/const MAP_GUIDE_STEPS = \[([\s\S]*?)\n\s*\];/);
  ok("MAP_GUIDE_STEPS is declared with four steps", !!gs && (gs[1].match(/\{ anchor:/g) || []).length === 4);
  const ids = [...new Set([...(gs ? gs[1] : "").matchAll(/(?:anchor|alt): "([a-z-]+)"/g)].map(m => m[1]))];
  for (const id of ids)
    ok(`⭐ every anchor the map's guide names exists as an id: ${id}`, html.includes(`id="${id}"`));
  // ⚠️ 12 Oct 2026 — REVERSED (live A4): the sidebar button said Play and only OPENED the bar at an empty
  // January. It now calls startTimeline(), which opens the bar and plays; openTimeline() stays for the bar.
  ok("the Play step has a fallback: the timeline's button when the bar is open, else the sidebar's Play forecast timeline — and that button PLAYS",
     /anchor: "tl-play", alt: "tl-open"/.test(code) && /id="tl-open" onclick="startTimeline\(\)"/.test(code)
     && !/id="tl-open" onclick="openTimeline\(\)"/.test(code)
     && /for \(const id of \[step\.anchor, step\.alt\]\)/.test(code));
  ok("the copy is §5's: the bar, Press Play, Conditions with Show on map, the side panel",
     /title: "The bar along the top"/.test(code) && /title: "Press Play"/.test(code)
     && /title: "Conditions"[^\n]*Show on map/.test(code) && /title: "The side panel"/.test(code));
  ok("🔴 the guide is set up ONLY when the tenant carries a demo notice",
     /function setupGuide\(\)\{\n\s+if \(!TENANT\.demo_notice\) return;/.test(code)
     && /\} else if \(dn\) \{ dn\.remove\(\); \}\n\s+setupGuide\(\);/.test(code));
  // 11 Oct 2026 REVERSED (the user: the notice and the Guide button sat on the figures bar): no measured
  // placement beside a centred pill any more — the notice is a strip at every width and the button is placed by
  // CSS at the right end of it; the resize hook only clears any inline left
  ok("...and placed by CSS at the right end of the notice strip, never measured beside a centred pill",
     !/getBoundingClientRect\(\)\.right \+ 8/.test(code) && /const placeBtn = \(\) => \{ btn\.style\.left = ''; \};/.test(code)
     && /window\.addEventListener\('resize', placeBtn\);/.test(code));
  ok("9 Oct: tablets get one row of six KPI cards under the month (701-1023px), the phone keeps its 3x2 grid",
     /@media \(min-width:701px\) and \(max-width:1023px\)\{\s*#kpi-cards\{ grid-template-columns:repeat\(6, minmax\(0, 1fr\)\); \}/.test(html));
  ok("9 Oct: below 1024px (phone AND tablet) the notice is a full-width strip at the top and the menu, the bar and the Guide button move down under it",
     /@media \(max-width:1023px\)\{[\s\S]*?body\.has-demo-notice #demo-notice\{ left:0; right:0; top:0; transform:none; border-radius:0;[\s\S]*?body\.has-demo-notice #menu-toggle\{ top:40px; \}[\s\S]*?body\.has-demo-notice #kpi-hud, body\.has-demo-notice\.sidebar-closed #kpi-hud\{ padding-top:84px; \}[\s\S]*?#guide-btn\{ left:auto !important; right:12px; top:9px; \}[\s\S]*?body\.has-demo-notice #guide-btn\{ top:36px; \}/.test(html)
     // NARROWED 11 Oct 2026 (the demo bar): the class is set for a demo tenant on /map/ opened directly, not when
     // the map is embedded in the app (EMBED), whose bar above the iframe carries the notice
     // NARROWED again 11 Oct 2026 (review): not when the app's bar is really drawn above (barAbove(), which needs
     // EMBED too) — embedded with no bar (the app's /api/meta failed) the map keeps its strip and the class
     && /const barOn = barAbove\(\);\n\s+document\.body\.classList\.toggle\('has-demo-notice', !!TENANT\.demo_notice && !barOn\);/.test(code)
     && /const placeBtn = \(\) => \{ btn\.style\.left = ''; \};/.test(code));
  // 11 Oct 2026: and from 1024 px up too — the strip, the bar / panel / controls 26 px lower, the button in the strip
  ok("11 Oct: on the desktop the notice is a 26 px strip too, the bar, panel and map controls sit under it, the Guide button is in the strip",
     /@media \(min-width:1024px\)\{\s*body\.has-demo-notice #demo-notice\{ left:0; right:0; top:0; transform:none; border-radius:0;[^}]*height:26px; \}\s*body\.has-demo-notice #kpi-hud\{ top:26px; \}\s*body\.has-demo-notice \.sidebar\{ top:26px; \}/.test(html)
     && /body\.has-demo-notice \.mapboxgl-ctrl-top-right\{ top:98px; \}/.test(html) && /body\.has-demo-notice #guide-btn\{ left:auto !important; right:10px; top:2px;/.test(html));
  ok("...the Guide button is created inside setupGuide and nowhere else",
     (code.match(/guideEl\('guide-btn', 'button'\)/g) || []).length === 1 && !html.includes('id="guide-btn"'));
  ok("remembered per visitor under wayscope_guide_map, every read and write in try/catch",
     /const MAP_GUIDE_KEY = "wayscope_guide_map";/.test(code)
     && /function guideRead\(\)\{ try \{ return localStorage\.getItem\(MAP_GUIDE_KEY\); \} catch \(e\) \{ return null; \} \}/.test(code)
     && /function guideWrite\(v\)\{ try \{ localStorage\.setItem\(MAP_GUIDE_KEY, v\); \} catch \(e\) \{\} \}/.test(code)
     && (code.match(/localStorage\.(get|set)Item\(MAP_GUIDE_KEY/g) || []).length === 2);
  // 11 Oct 2026 REVERSED (the user, options 4 + 1 + 2): nothing starts by itself any more
  ok("11 Oct: no tour starts by itself; the strip offers it, the dots mark the features, re-placed every second; the button replays",
     !/setTimeout\(guideStart, 900\)/.test(code) && /btn\.onclick = guideStart;/.test(code)
     && code.includes("placeGuideHints();\n        window.addEventListener('resize', placeGuideHints);\n        setInterval(placeGuideHints, 1000);"));
  // 11 Oct 2026 NARROWED: the last button says "Got it" (Google's wording); it still remembers
  ok("Back / Next / Got it and 'Don't show again'; Got it remembers, 'Don't show again' switches off",
     /onclick="guideStep\(-1\)">Back</.test(code) && /onclick="guideStep\(1\)">Next</.test(code)
     && /onclick="guideEnd\(\)">Got it</.test(code) && /onclick="guideOff\(\)">Don\\'t show again</.test(code)
     && /function guideEnd\(keep\)\{ if \(!keep\) guideWrite\('done'\);/.test(code)
     // 11 Oct 2026 NARROWED: 'off' must survive the card closing (it used to be overwritten with 'done')
     && /function guideOff\(\)\{ guideWrite\('off'\); guideEnd\(true\); \}/.test(code));
  ok("🔴 ONE Mapbox instance, never removed: the guide adds no map and no map.remove()",
     (code.match(/new mapboxgl\.Map\(/g) || []).length === 1 && !/map\.remove\(\)/.test(code));
  ok("🔴 no new script tag: the guide is in-page (three script src tags, as before)", (html.match(/<script src=/g) || []).length === 3);
  ok("the card and ring are fixed overlays over the map, not inside it",
     /#guide-ring\{position:fixed;z-index:9000;pointer-events:none;/.test(html) && /#guide-card\{position:fixed;z-index:9001;/.test(html));
  ok("the anchor is scrolled into view before measuring, and the card is clamped into the window (seen live: an off-screen card)",
     /el\.scrollIntoView\(\{ block: 'nearest' \}\)/.test(code) && /top = Math\.min\(Math\.max\(12, top\), Math\.max\(12, vh - 232\)\);/.test(code));
  // 12 Oct 2026 — NARROWED (review 2.8 row 2): the words go through guideTitle() / guideBody(), which pick a step's phone
  // words on a phone; still textContent, and the helpers return the step's own strings and nothing else
  ok("the step text is set as textContent, never as HTML", /card\.querySelector\('h4'\)\.textContent = guideTitle\(step\);/.test(code)
     && /card\.querySelector\('p'\)\.textContent = guideBody\(step\);/.test(code)
     && code.includes("function guideTitle(step){ return (guideOnPhone() && step.phoneTitle) || step.title; }")
     && code.includes("function guideBody(step){ return (guideOnPhone() && step.phoneBody) || step.body; }")
     && !/card\.innerHTML[^;]*step\./.test(code));
  ok("🔴 no team id in the map guide's copy", !/IPT/.test(gs ? gs[0] : "x"));
}
// ---- 11 Oct 2026: the demo bar (the user: the map's strip and Guide "on every page") -------------------------
// The staff app now carries the notice and the Guide in a bar under its header on every view, and iframes this
// page as /map/?embed=1. Embedded, the map draws no #demo-notice, no #guide-btn and sets no has-demo-notice (no
// 26 px gap), keeps its tour, hint strip and dots, and tells the app its tour is ready. /map/ opened directly is
// unchanged. Source first, then the real functions run against a small fake DOM (no browser, no jsdom here).
{
  const embedDecl = (code.match(/const EMBED = (\(\(\) => \{ try \{ return [^\n]*\}\)\(\));/) || [])[1];
  ok("11 Oct (demo bar): EMBED is the embed=1 flag AND a frame, read once, in try/catch",
     !!embedDecl && embedDecl.includes("new URLSearchParams(location.search).get('embed') === '1' && window.self !== window.top")
     && embedDecl.includes("catch (e) { return false; }"));
  if (embedDecl) {
    const ev = (search, framed, throws) => {
      const self = {};
      const win = throws ? { self, get top() { throw new Error("cross-origin"); } } : { self, top: framed ? {} : self };
      return new Function("location", "window", "URLSearchParams", "return " + embedDecl)({ search }, win, URLSearchParams);
    };
    ok("...true only inside a frame with ?embed=1: framed with the flag → embedded; the flag on its own, a frame on its own, neither → standalone",
       ev("?embed=1&v=1", true) === true && ev("?embed=1&v=1", false) === false && ev("?v=1", true) === false
       && ev("", false) === false && ev("?embed=0", true) === false && ev("?embed=1", true, true) === false);
  }
  // NARROWED 11 Oct 2026 (review): skipped when the app's bar is drawn above (barAbove()), not merely when embedded
  ok("...the strip and the class are skipped when the app's bar is drawn above; the notice is still set as text, never as HTML",
     /if \(TENANT\.demo_notice && !barOn\) \{\n\s+if \(!dn\) \{ dn = document\.createElement\('div'\); dn\.id = 'demo-notice'; document\.body\.appendChild\(dn\); \}\n\s+dn\.textContent = TENANT\.demo_notice;/.test(code));
  ok("🔴 (review) barAbove(): false unless EMBED; then asks the parent page for a .demo-bar, in try/catch (any error → draw our own)",
     /function barAbove\(\)\{\n\s+if \(!EMBED\) return false;\n\s+try \{ return !!window\.parent\.document\.querySelector\('\.demo-bar'\); \} catch \(e\) \{ return false; \}\n\s+\}/.test(code)
     && !/!EMBED\)/.test(code.replace(/if \(!EMBED\) return false;/, "")));
  {
    const fh = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
    ok("⭐ (review) the class the map looks for is the class the app's bar carries (.demo-bar, on DemoBar's root div)",
       fh.includes('<div className={"demo-bar" + (onGuide ? " has-guide" : "")} role="note">'));
  }
  const sg = (code.match(/function setupGuide\(\)\{([\s\S]*?)\n    \}\n/) || ["", ""])[1];
  // NARROWED 11 Oct 2026 (review): keyed on barAbove() (the app's bar is really there), not on EMBED alone
  ok("...setupGuide: under the app's bar, no Guide button — it posts 'wayscope-map-tour' to the app (same origin only); otherwise the button as before",
     /if \(barAbove\(\)\) \{\s*try \{ window\.parent\.postMessage\(\{ type: 'wayscope-map-tour' \}, location\.origin\); \} catch \(e\) \{\}\s*\} else \{\s*const btn = guideEl\('guide-btn', 'button'\);/.test(sg)
     && (sg.match(/postMessage\(/g) || []).length === 1 && !/postMessage\([^)]*'\*'/.test(code));
  ok("...the tour, the hint strip and the dots are set up either way (after the if / else)",
     sg.indexOf("placeGuideHints();\n        window.addEventListener('resize', placeGuideHints);") > sg.indexOf("window.addEventListener('resize', placeBtn);\n        }")
     && sg.indexOf("window.addEventListener('resize', placeBtn);\n        }") > 0);
  {
    const lb = (code.match(/window\.addEventListener\('message', \(e\) => \{([\s\S]*?)\n    \}\);/) || ["", ""])[1];
    ok("(review) a late bar: one 'message' listener, from the parent, same origin, type 'wayscope-bar-on', acted on only once the bar is really there",
       lb.includes("if (e.origin !== location.origin || e.source !== window.parent || !e.data || e.data.type !== 'wayscope-bar-on') return;")
       && lb.includes("if (!barAbove()) return;") && (code.match(/addEventListener\('message'/g) || []).length === 1);
    ok("...it drops the strip, the class and the map's own Guide button, and tells the app the tour is ready only if it is set up (same origin)",
       lb.includes("document.body.classList.toggle('has-demo-notice', false);") && lb.includes("const btn = document.getElementById('guide-btn');")
       && lb.includes("if (GUIDE_READY) { try { window.parent.postMessage({ type: 'wayscope-map-tour' }, location.origin); } catch (err) {} }")
       && /let GUIDE_READY = false;/.test(code) && /if \(!TENANT\.demo_notice\) return;\n\s+GUIDE_READY = true;/.test(code));
  }
  ok("...the frontend's MAP_URL carries the flag, so both of the app's iframes are embedded",
     /const MAP_URL = "\/map\/\?embed=1&v=" \+ Date\.now\(\);/.test(fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8")));

  // ---- the real functions, run: applyTenantVocabulary → setupGuide → placeGuideHints, then guideStart ----------
  const a = src.indexOf("    function applyTenantVocabulary() {");
  const bEnd = "window.addEventListener('resize', () => { if (guideIndex >= 0) guideRender(); });";
  const b = src.indexOf(bEnd);
  ok("the guide's functions are one contiguous block (applyTenantVocabulary … the resize hook)", a > 0 && b > a);
  // 11 Oct 2026 (review): `bar` is whether the parent page has the app's .demo-bar (default: embedded ⇒ yes, the
  // normal case); the window records its listeners so a 'message' can be delivered (deliver)
  const run = (embed, notice, bar) => {
    if (bar === undefined) bar = embed;
    const byId = {}, posted = [], intervals = [], listeners = {};
    const parentDoc = { bar, querySelector(sel) { if (this.bar === "throw") throw new Error("cross-origin"); return sel === ".demo-bar" && this.bar ? {} : null; } };
    const mk = (tag) => {
      const el = { tagName: String(tag || "div").toUpperCase(), id: "", style: {}, dataset: {}, attrs: {}, hidden: false, className: "",
        textContent: "", innerHTML: "", offsetWidth: 600, offsetHeight: 72, onclick: null,
        setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; },
        remove() { if (byId[this.id] === this) delete byId[this.id]; },
        getBoundingClientRect() { return { top: 0, left: 300, right: 1280, bottom: 72, width: 980, height: 72 }; },
        scrollIntoView() {}, closest() { return null; }, querySelector() { return mk("span"); } };
      return el;
    };
    for (const id of ["kpi-hud", "tl-play", "kpi-conditions", "kpi-moving"]) { const e = mk(); e.id = id; byId[id] = e; }
    const cls = new Set();
    const document = {
      body: { classList: { toggle(c, on) { if (on) cls.add(c); else cls.delete(c); }, contains: (c) => cls.has(c) },
              appendChild(el) { byId[el.id] = el; return el; } },
      getElementById: (id) => byId[id] || null, createElement: (t) => mk(t), querySelector: () => null,
    };
    const store = {};
    const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
    const parent = { document: parentDoc, postMessage: (msg, origin) => posted.push([msg, origin]) };
    const window = { innerWidth: 1280, innerHeight: 800, addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); },
                     evr_rail_data: null, OVERLAY_VERSION: null, parent };
    const location = { origin: "https://app.wayscope.test", search: embed ? "?embed=1&v=1" : "" };
    const TENANT = { name: "Wolds Link", team_label: "Team", demo_notice: notice };
    const f = new Function("document", "window", "localStorage", "location", "setInterval", "TENANT", "TEAM", "EMBED",
      src.slice(a, b + bEnd.length) + "\nreturn { applyTenantVocabulary, guideStart, setupGuide };");
    const api = f(document, window, localStorage, location, (fn, ms) => intervals.push(ms), TENANT, "Team", embed);
    api.applyTenantVocabulary();
    const before = { cls: cls.has("has-demo-notice"), notice: byId["demo-notice"] ? byId["demo-notice"].textContent : null,
                     btn: byId["guide-btn"] || null, strip: !!byId["guide-strip"], dots: Object.keys(byId).filter(k => /^guide-dot-/.test(k)).length,
                     posted: posted.slice(), intervals: intervals.slice() };
    if (notice) api.guideStart();
    const deliver = (data, origin, source) => (listeners.message || []).forEach(fn => fn({ data, origin: origin || location.origin, source: source === undefined ? parent : source }));
    const now = () => ({ cls: cls.has("has-demo-notice"), notice: byId["demo-notice"] ? byId["demo-notice"].textContent : null,
                         btn: byId["guide-btn"] || null, posted: posted.slice() });
    return { ...before, card: !!byId["guide-card"], api, parentDoc, deliver, now, listeners };
  };
  if (a > 0 && b > a) {
    const N = "Fictional demo scheme · nothing here is real";
    let emb = null, alone = null, real = null, err = "";
    try { emb = run(true, N); alone = run(false, N); real = run(true, null); } catch (e) { err = e.message; }
    ok("⭐ the guide block runs against a fake DOM, embedded and standalone", !!emb && !!alone && !!real, err);
    if (emb && alone && real) {
      ok("⭐ embedded (demo tenant): no strip, no has-demo-notice class (no 26 px gap), no Guide button of its own",
         emb.cls === false && emb.notice === null && emb.btn === null);
      ok("⭐ ...and it tells the app, once, that its tour is ready — to this origin only",
         emb.posted.length === 1 && emb.posted[0][0].type === "wayscope-map-tour" && emb.posted[0][1] === "https://app.wayscope.test");
      ok("⭐ ...its hint strip and dots are still there, and guideStart() (what the app's Guide calls) opens the tour",
         emb.strip === true && emb.dots >= 3 && emb.intervals.includes(1000) && emb.card === true);
      ok("⭐ standalone /map/ is unchanged: the strip with the tenant's words, the class, the Guide button running guideStart, no message",
         alone.cls === true && alone.notice === N && !!alone.btn && alone.btn.textContent === "Guide" && alone.btn.onclick === alone.api.guideStart
         && alone.posted.length === 0 && alone.strip === true && alone.card === true);
      ok("🔴 a real tenant (no notice), embedded: no strip, no class, no button, no message, no hint strip",
         real.cls === false && real.notice === null && real.btn === null && real.posted.length === 0 && real.strip === false && real.dots === 0);
    }
    // ---- 11 Oct 2026 (review): embedded, but the app drew no bar (its /api/meta failed) -------------------------
    let nobar = null, late = null, spoof = null, err2 = "";
    try { nobar = run(true, N, false); late = run(true, N, false); spoof = run(true, N, false); } catch (e) { err2 = e.message; }
    ok("the no-bar cases run", !!nobar && !!late && !!spoof, err2);
    if (nobar && late && spoof) {
      ok("⭐ (review) embedded with NO bar above (the app's /api/meta failed): the map keeps its own strip with the tenant's words, the class and its Guide button",
         nobar.cls === true && nobar.notice === N && !!nobar.btn && nobar.btn.onclick === nobar.api.guideStart && nobar.posted.length === 0);
      // a message that is not the app's bar-on, or arrives before the bar is in the parent page, changes nothing
      spoof.deliver({ type: "wayscope-bar-on" }, "https://elsewhere.example");
      spoof.deliver({ type: "wayscope-bar-on" }, undefined, {});
      spoof.deliver({ type: "something-else" });
      spoof.deliver({ type: "wayscope-bar-on" });           // from the parent, right type, but no .demo-bar there yet
      const sp = spoof.now();
      ok("🔴 (review) bar-on from another origin, from a window that is not the parent, of another type, or with no bar in the parent page: the strip stays",
         sp.cls === true && sp.notice === N && !!sp.btn && sp.posted.length === 0);
      // the bar arrives late: the parent now has .demo-bar and says so
      late.parentDoc.bar = true;
      late.deliver({ type: "wayscope-bar-on" });
      const lt = late.now();
      ok("⭐ (review) the bar arrives late (the app's /api/meta answered after the map's overlay): the map drops its strip, its class and its Guide button",
         lt.cls === false && lt.notice === null && lt.btn === null);
      ok("⭐ ...and tells the app, once, that its tour is ready — to this origin only — so the bar's Guide runs it",
         lt.posted.length === 1 && lt.posted[0][0].type === "wayscope-map-tour" && lt.posted[0][1] === "https://app.wayscope.test");
      late.deliver({ type: "wayscope-bar-on" });
      ok("...a second bar-on changes nothing more (the tour message again, which the app treats the same)",
         late.now().cls === false && late.now().notice === null && late.now().posted.length === 2);
      // the bar-on before the overlay has answered (no notice known yet): nothing to drop, and no tour message
      const early = run(true, null, true);
      early.deliver({ type: "wayscope-bar-on" });
      ok("🔴 (review) bar-on for a map with no tour set up (a real tenant, or the overlay not yet in): no tour message",
         early.now().posted.length === 0 && early.now().cls === false);
      let throwing = null; try { throwing = run(true, N, "throw"); } catch (e) { throwing = null; }
      ok("🔴 (review) a parent page that cannot be read (the lookup throws) counts as no bar: no throw, and the strip is drawn",
         !!throwing && throwing.cls === true && throwing.notice === N && !!throwing.btn);
    }
  }
}
// ---- 9 Oct 2026: UK wording on the public map's visible copy -------------------------
// The route drawer said 'Trips / day / truck', 'Trucks for peak' and 'DEFRA-2025-based'. UK copy says
// lorry / HGV (CLAUDE.md), and the factors are DESNZ 2026. Asserted on every string literal the map
// prints; identifiers and comments are not copy. Vehicle NAMES come from the tenant's factors, not here.
{
  const strings = (code.match(/'[^'\r\n]*'|"[^"\r\n]*"|`[^`]*`/g) || []).filter(s => !/^['"`]\s*$/.test(s));
  const trucks = strings.filter(s => /trucks?/i.test(s) && !/Truck mixer/.test(s));
  ok("🔴 no 'truck' in any string the public map prints (lorry / HGV)", trucks.length === 0, trucks.slice(0, 3).join(" | "));
  ok("the drawer's figures say lorry", /'Trips \/ day \/ lorry'/.test(code) && /'Lorries for peak'/.test(code));
  ok("the drawer's carbon note names DESNZ 2026, not DEFRA 2025, and says what the figure is (average laden, both legs, tailpipe only, set on Config)",
     /Carbon: DESNZ 2026 kg CO₂e per vehicle-km, average laden, applied to both legs, tailpipe only; set per vehicle on the Config page\./.test(code) && !/DEFRA/.test(code));
}


// ---- 11 Oct 2026: the map panel (mockup 7, the user's decisions: no search, two-way movements and vehicles
// needed a day as the headline, the 300 px panel kept) ----
ok("the two headline cards lead: two-way movements and vehicles needed",
  /<div class="kpi-card lead">\s*<div class="kpi-value" id="kpi-trips">/.test(html) && /<div class="kpi-card lead">\s*<div class="kpi-value" id="kpi-vehicles">/.test(html)
  && /\.kpi-card\.lead \.kpi-value\{ font-size:28px;/.test(html)
  // NARROWED 11 Oct 2026: the map's CSS scopes the wrapping label rule to the cards (#kpi-cards .kpi-label),
  // so the bar's own labels are not touched; the assertion was written before that edit landed on main
  && /@media \(min-width:1024px\)\{ #kpi-cards, \.kpi-row\{ gap:18px; \} #kpi-cards \.kpi-label\{ white-space:normal; max-width:104px; \} \}/.test(html));
ok("the side-panel rows say two-way, not trips", code.includes("two-way/d \\u00b7 ") && !code.includes("} trips/d \\u00b7"));
ok("basemap, overlays and haul routes sit in one closed 'Layers and basemap' fold; the panel stays 300 px",
  html.indexOf('<details class="layers-box" id="layers-box">') < html.indexOf('<h3>Basemap</h3>')
  && html.indexOf('<h3>Haul routes</h3>') < html.indexOf('</details>', html.indexOf('id="layers-box"'))
  && !/<details class="layers-box" id="layers-box" open/.test(html) && /\.sidebar \{ position:absolute; top:0; bottom:0; left:0; width:300px;/.test(html));
ok("busiest routes: the five largest by two-way movements a day (not doubled), each a button that selects the route, cleared with the month",
  html.includes('<div id="kpi-busiest"></div>') && code.includes(".sort((a, b) => b[2] - a[2]).slice(0, 5)")
  // 12 Oct second fix pass — NARROWED: cleared in THREE places now (no forecast, an empty month, and a month still loading)
  && code.includes("onclick=\"selectRoute(") && (code.match(/setHTML\('kpi-busiest', ''\)/g) || []).length === 3);
ok("11 Oct: below 1024 px the zoom buttons sit under the measured bar (a fixed 180 px overlapped it at 950 px), set on resize and whenever the bar changes height",
  code.includes("if (ctrl) ctrl.style.top = (window.innerWidth > 1023 || !kpi) ? '' : (Math.round(kpi.getBoundingClientRect().bottom) + 8) + 'px';")
  && code.includes("new ResizeObserver(() => positionWarnStack()).observe(document.getElementById('kpi-hud'))"));
// 11 Oct 2026 REVERSED (the user chose the Google style): the bubble is dark and slightly transparent, with an arrow
ok("11 Oct: the tour bubble is Google-style — dark, slightly transparent (88 %, blurred), 13 px, an arrow, text buttons",
  /#guide-card\{position:fixed;z-index:9001;width:min\(300px,calc\(100vw - 24px\)\);background:rgba\(32,33,36,\.88\);[^}]*backdrop-filter:blur\(8px\)/.test(html)
  && /#guide-card\[data-place="below"\]::before/.test(html) && /#guide-card \.guide-foot button\.guide-next\{color:#8AB4F8\}/.test(html)
  && code.includes("card.dataset.place = place;"));
ok("11 Oct: the strip sits just under the bar, offers the tour and hides everything with ×; shown until the tour is done",
  code.includes("if (on && guideRead() !== 'done' && kpi) {") && code.includes("onclick=\"guideStart()\">Take the tour</button>")
  && code.includes("onclick=\"guideOff()\">\\u00d7</button>") && code.includes("strip.style.top = (Math.round(k.bottom) + 10) + 'px';"));
ok("11 Oct: one pulsing dot per visible feature, hover / focus / tap shows its line, none during the tour or once switched off",
  code.includes("function guideHintsOn(){ return !!TENANT.demo_notice && guideRead() !== 'off'; }") && code.includes("const on = guideHintsOn() && guideIndex < 0;")
  && code.includes("dot.onmouseenter = show; dot.onfocus = show; dot.onmouseleave = hide; dot.onblur = hide;")
  && /\.guide-dot\{position:fixed;z-index:9002;[^}]*animation:guide-pulse 2s infinite\}/.test(html) && /prefers-reduced-motion:reduce\)\{\.guide-dot\{animation:none/.test(html));
ok("11 Oct: the map takes the app's shell — warm neutrals, sentence-case 13 px headings, 14 px controls, orange primary buttons, routes still blue",
  /--line:#E7E5E4; --bg:#FFFFFF;/.test(html) && /--action:#C2410C; --action-fg:#FFFFFF;/.test(html) && /--navy:#2563EB;/.test(html)
  && /\.sidebar h3 \{ margin:0 0 8px; font-size:13px; font-weight:600; letter-spacing:0; color:var\(--navy-deep\); text-transform:none; \}/.test(html)
  && /select \{ width:100%;[^}]*font-size:14px;/.test(html) && /\.btn \{[^}]*background:var\(--action\); color:var\(--action-fg\); \}/.test(html)
  && !/font-size:1(0|0\.5|1)px;\s*color:#8a9099/.test(html) && html.includes('<div style="height:44px;flex:none"></div>')
  && /\.fc-row label\{ font-size:12\.5px;/.test(html) && /\.an-lbl\{ font-size:12px; font-weight:500; letter-spacing:0; text-transform:none;/.test(html));
ok("11 Oct: the Loads / day card is hidden in a vehicles unit (it repeated two-way movements); kept for tonnes / m3",
  /<div class="kpi-card" id="kpi-material-card">/.test(html) && code.includes("if (mc) mc.hidden = (unitLbl === 'vehicles');"));
ok("11 Oct: a bar card never shrinks below its figure; the What's moving figures wrap instead of being cut off",
  /#kpi-cards \.kpi-card\{ min-width:min-content; \}/.test(html) && /\.kpi-chip\{ flex-wrap:wrap; \}/.test(html)
  && /\.kpi-chip \.chip-n\{[^}]*white-space:normal;/.test(html) && !/\.kpi-chip \.chip-n\{[^}]*white-space:nowrap/.test(html));
ok("no place search was added (the user's decision 11 Oct: no geocoder)", !/geocod/i.test(code) && !/Find a place/.test(html));

// ---- 11 Oct 2026 — the guide update: the map tour's stale text -------------------------------------
// The bar's Material a day card is hidden in the vehicles unit the map paints in (CONFIG.FORECAST_UNIT), and on a
// British tenant a route condition is a planned closure, not a mass limit. Source-level only.
{
  const gsM = (code.match(/const MAP_GUIDE_STEPS = \[([\s\S]*?)\n\s*\];/) || ["", ""])[1];
  ok("guide update: the bar step names what the bar shows (no material card in a vehicles unit)",
     gsM.includes('body: "shows the month in view: two-way movements a day, vehicles needed, routes in use and CO₂e." }')
     && !/movements, vehicles, material, routes/.test(gsM));
  ok("...the Conditions step says it appears with the timeline and names a closure, not only a mass limit",
     gsM.includes("appears while the timeline is open") && gsM.includes("a road closure or limit on a route")
     && !/a route over a mass limit/.test(gsM));
}

// ---- 11 Oct 2026 — three public-map bugs found by the guide's dry run (claude/map-popup-layers) ------
// (1) a package with no underlay (the demo) has no underlay key, and iptCheckboxId(null) threw: the
// alignment click opened no popup, and ticking the alignment back on left its band legend hidden.
// (2)/(3) the zone and closure layers deferred to map.once('style.load') while tiles were loading,
// i.e. to an event that had already fired, so they were never added. Checked in a real browser on
// 11 Oct (Playwright, 3 loads, demo tenant); these assertions are source-level only.
{
  ok("map bugs: iptCheckboxId is never handed underlayKey() directly (it is null with no underlay)",
     !/iptCheckboxId\(\s*underlayKey\(\)\s*\)/.test(code));
  const args = [...code.matchAll(/iptCheckboxId\(([^)]*)\)/g)].map(x => x[1].trim());
  ok("...every argument it is handed is a legend row's band, or the underlay key behind a null guard",
     args.length >= 4 && args.every(a => a === "ipt" || a === "r.ipt" || a === "uk"),
     JSON.stringify(args));
  const ukCalls = code.split("\n").filter(l => l.includes("iptCheckboxId(uk)"));
  ok("...and every underlay-key call is guarded on the same line (uk ? ... : null)",
     ukCalls.length === 2 && ukCalls.every(l => /\buk \? document\.getElementById\(iptCheckboxId\(uk\)\) : null;/.test(l)),
     JSON.stringify(ukCalls));
  ok("...the alignment popup's underlay note needs an underlay to exist, not just a missing checkbox",
     code.includes("const undOn = !!uk && (!undBox || undBox.checked) &&"));
  ok("map bugs: nothing defers to map.once('style.load') (it has usually already fired)",
     !/\.once\(\s*['"]style\.load['"]/.test(code));
  ok("...the zone layers wait for idle", code.includes("if (!map.isStyleLoaded()) { map.once('idle', ensureZoneLayers); return; }")
     && !code.includes("map.once('style.load', ensureZoneLayers)"));
  ok("...the restriction (closure) layers wait for idle",
     code.includes("if(!map.isStyleLoaded()){ map.once('idle', ensureRestrictionLayers); return; }")
     && !code.includes("map.once('style.load', ensureRestrictionLayers)"));
  const defers = [...code.matchAll(/if\s*\(\s*!map\.isStyleLoaded\(\)\s*\)\s*\{\s*map\.once\(\s*'([^']+)'/g)].map(x => x[1]);
  ok("...and every isStyleLoaded() deferral in the file waits for 'idle'",
     defers.length >= 2 && defers.every(e => e === "idle"), JSON.stringify(defers));
  ok("...the style.load handler still re-adds both on a basemap switch",
     code.includes("if (ZONES.loaded) ensureZoneLayers(); else loadZones();")
     && code.includes("if (RESTR.data) ensureRestrictionLayers(); else loadRestrictions();"));
}

// ---- 12 Oct 2026 — Play and the timeline (review §2.4 / D22, live A4 A5 A8; branch claude/mr1-play) ----------
// Source-level pins for each of the seven items, then the timeline block run against a fake DOM and a
// hand-built matrix so the loop, the pause flag, the setData guard and the keys are exercised, not just grepped.
{
  // (1) A4 — the sidebar button plays (the reversed guide pin above carries the id/onclick); openTimeline stays
  ok("A4: startTimeline() still opens the bar when it is shut, and openTimeline() is still its own function",
     /function startTimeline\(\)\{[\s\S]{0,400}if\(!TL\.on\) openTimeline\(\);/.test(code) && /function openTimeline\(\)\{/.test(code));
  ok("A4: a second press while playing is a no-op (no second interval)",
     /if\(!TL\.on\) openTimeline\(\);\s*if\(TL\.playing\) return;/.test(code));
  // (2) A5 / D22 — start month, loop within the span, full-horizon switch, once-per-loop pause, empty label
  ok("D22: the matrix carries the months with volume and their span, built from EVERY line the API returned",
     /const volMonths = new Set\(\);/.test(code) && /\(j\.routes\|\|\[\]\)\.forEach\(rt=>\{ Object\.keys\(rt\.monthly\|\|\{\}\)\.forEach\(k=>\{[^\n]*volMonths\.add\(mm\)/.test(code)
     && /const span = volMonths\.size \? \[Math\.min\(\.\.\.volMonths\), Math\.max\(\.\.\.volMonths\)\] : null;/.test(code)
     // NARROWED 12 Oct 2026 (C1, review §2.2a): the matrix also carries the programme's carbon maximum and the feed's
     // co2_error, after the span - the carbon ramp's fixed stops come from it
     // NARROWED 12 Oct 2026 (wording review): and, last, the feed's carbon stamp (carbonStamp), which the carbon legend prints
     // NARROWED 12 Oct 2026 (Track C review): and the largest section-month (sectionCo2Max), the section ramp's stops
     && /TL\.matrix = \{ byRoute:byR, unit:j\.unit, working_days:j\.working_days, volMonths, span, co2Max, (sectionCo2Max, )?co2Error: j\.co2_error \|\| null, carbonStamp: j\.carbon_stamp \|\| null \};/.test(code));
  ok("D22: the bar opens on the current calendar month if it carries volume, else the first month that does — never an empty January",
     /function tlStartMonth\(\)\{\s*const cur = currentMonthIndex\(\);\s*if\(monthHasVolume\(cur\)\) return cur;/.test(code)
     && /return span \? span\[0\] : 1;/.test(code)
     && /ensureTimelineMatrix\(\)\.then\(\(\)=>\{\s*if\(!monthHasVolume\(TL\.month\)\) TL\.month = tlStartMonth\(\);\s*setTimelineMonth\(TL\.month\);/.test(code)
     && /return \(d\.getFullYear\(\) - CONFIG\.START_YEAR\) \* 12 \+ d\.getMonth\(\) \+ 1;/.test(code));
  ok("D22: the loop runs within the span with volume; the old 1..MONTH_COUNT wrap is gone from tickTimeline",
     /function tickTimeline\(\)\{\s*const \[lo, hi\] = tlLoopBounds\(\);\s*const wrap = TL\.month >= hi \|\| TL\.month < lo;/.test(code)
     && !/TL\.month = TL\.month>=CONFIG\.MONTH_COUNT \? 1 : TL\.month\+1;/.test(code));
  // REVERSED 12 Oct 2026 evening (M3 bar, the user: "the full horizon tick box does nothing"): the checkbox is the
  // "Plan months / Full horizon" radio pair of mockup 3; setTimelineFull sets aria-checked on both, and the bar's
  // opening shows the state (setTimelineFull(TL.full)); no checkbox is left
  ok("D22 / M3: the Full horizon switch restores 1..MONTH_COUNT, and it is the 'Plan months / Full horizon' pair in the bar",
     /function tlLoopBounds\(\)\{[\s\S]{0,200}if\(TL\.full \|\| !span\) return \[1, CONFIG\.MONTH_COUNT \|\| 60\];/.test(code)
     && /<div class="tl-seg" role="radiogroup" aria-label="Months Play loops over">/.test(html)
     && /<button type="button" id="tl-seg-plan" role="radio" aria-checked="true" onclick="setTimelineFull\(false\)"[^>]*>Plan months<\/button>/.test(html)
     && /<button type="button" id="tl-seg-full" role="radio" aria-checked="false" onclick="setTimelineFull\(true\)"[^>]*>Full horizon<\/button>/.test(html)
     && /function setTimelineFull\(on\)\{\s*TL\.full = !!on;/.test(code)
     && /if\(sp\) sp\.setAttribute\('aria-checked', String\(!TL\.full\)\);\s*if\(sf\) sf\.setAttribute\('aria-checked', String\(TL\.full\)\);/.test(code)
     && /setTimelineFull\(TL\.full\); setPauseOnClash\(TL\.pauseOnClash\);/.test(code)
     && !html.includes('id="tl-full"') && !code.includes("getElementById('tl-full')"));
  ok("D22: playback stops once per loop on the first red month it TICKS into, panel open; the wrap re-arms it",
     // NARROWED 12 Oct 2026 evening (M3 bar): only while the "Pause on clash" switch is on (absent = on)
     /if \(TL\.playing && TL\.pauseOnClash !== false && TL\.ticked === month && !TL\.clashPaused && live\.some\(i => i\.lvl === 'clash'\)\) \{\s*TL\.clashPaused = true; WARN\.open = true;\s*stopTimeline\(monthLabel\(month\) \+ ' · playback paused: '/.test(code)
     && /if\(wrap && lo !== hi\) TL\.clashPaused = false;/.test(code) && /TL\.ticked = TL\.month;\s*setTimelineMonth\(TL\.month\);/.test(code)
     // resuming on a red month counts as this loop's pause; the month Play was pressed on can never stop it
     && /if\(WARN\.countsMonth === TL\.month && WARN\.counts\.clash > 0\) TL\.clashPaused = true;\s*TL\.ticked = null;/.test(code)
     && /WARN\.countsMonth = month;/.test(code));
  ok("D22: the auto-open-once rule and the pill are untouched by the pause",
     /live\.some\(i => i\.lvl === 'clash'\) && !WARN\.autoOpened/.test(code) && /function renderConditionsPill\(live\)/.test(code));
  // NARROWED 12 Oct 2026 evening (M3 bar): the heading is the month in full; "nothing approved" and the routes and trips
  // moved to the line under it (TL.figsFallback, until the figures bar's own numbers land: syncTlFigs)
  ok("D22: an empty month reads 'nothing approved this month', never '0 routes · 0 trips'",
     /if\(lbl\) lbl\.textContent = monthLong\(m\);/.test(code)
     && /TL\.figsFallback = count===0 \? 'nothing approved this month' : count\+\(count===1\?' route · ':' routes · '\)\+Math\.round\(sum\)\+' '\+unitWord\(unit\)\+' this month';/.test(code)
     && !/' · '\+count\+' routes · '\+Math\.round\(sum\)\+' '\+unitWord\(unit\);\s*\}/.test(code.replace(/count===0 \?[^\n]*/, "")));
  // (3) A8 — the loaded leg only
  ok("⭐ A8: the timeline label counts the LOADED leg only (one load = one two-way movement, never doubled)",
     /if\(f\.properties\.type==='Inbound Highway'\)\{ count\+\+; sum\+=vol; \}/.test(code)
     && !/f_time=monthLabel\(m\); count\+\+; sum\+=vol;/.test(code));
  ok("⭐ A8: 'Showing N route(s)' counts the loaded leg only",
     /if \(f\.properties\.type === 'Inbound Highway'\) matchCount\+\+;/.test(code)
     && (code.match(/matchCount\+\+/g) || []).length === 1
     && /status\.innerHTML = `Showing \$\{matchCount\} route\(s\) with approved forecasts\.`;/.test(code));
  // (4) the changed-guard on the per-month setData; markRouteEnds' own guard untouched
  ok("⭐ renderMonthFrame re-sends the source only when a feature's is_forecast / f_avg / f_month_total changed",
     /const wasForecast=f\.properties\.is_forecast, wasAvg=f\.properties\.f_avg, wasTotal=f\.properties\.f_month_total;/.test(code)
     && /if\(f\.properties\.is_forecast!==wasForecast \|\| f\.properties\.f_avg!==wasAvg \|\| f\.properties\.f_month_total!==wasTotal\) changed=true;/.test(code)
     && /if\(changed\) src\.setData\(data\);\s*ensureForecastLayers\(\); ensureFlowLayer\(\);/.test(code)
     && !/src\.setData\(data\); ensureForecastLayers\(\);/.test(code));
  ok("...and markRouteEnds' second setData keeps its own guard, exactly once",
     (code.match(/if \(changed\) src\.setData\(a1_data\);/g) || []).length === 1);
  // (5) prefers-reduced-motion
  ok("reduced motion: one helper reads the media query, in a try/catch",
     /function reducedMotion\(\)\{\s*try \{ return !!\(window\.matchMedia && window\.matchMedia\('\(prefers-reduced-motion: reduce\)'\)\.matches\); \} catch\(e\)\{ return false; \}/.test(code));
  ok("reduced motion: the dash march stays DASH_SOLID while playing when it matches",
     /function startFlowAnimation\(\)\{\s*applyRailFlow\(\);\s*if\(reducedMotion\(\)\)\{ setFlowDash\(DASH_SOLID\); setRailFlowDash\(DASH_SOLID\); return; \}\s*if\(_flowRAF==null\) _flowRAF=requestAnimationFrame\(animateFlow\);/.test(code));
  ok("reduced motion: Show on map jumps instead of flying when it matches",
     /if \(reducedMotion\(\)\) map\.jumpTo\(cam\); else map\.flyTo\(\{ \.\.\.cam, duration: 700 \}\);/.test(code)
     && !/map\.flyTo\(\{ center: f\.geometry\.coordinates/.test(code));
  // (6) KPI prefetch
  ok("KPI prefetch: kicked off when the matrix lands, never awaited, through the existing cache, one month at a time",
     /TL\.matrix = \{ byRoute:byR[^\n]*\};\s*prefetchSpanKpis\(\);\s*return TL\.matrix;/.test(code)
     && /function prefetchSpanKpis\(\)\{\s*setTimeout\(async \(\)=>\{\s*for\(const m of tlPrefetchOrder\(\)\)\{\s*if\(KPI\.cache\[m\]\) continue;\s*try \{ await kpiFetchMonth\(m\); \} catch\(e\)\{\}/.test(code)   // 12 Oct fix pass (F1)
     && /function tlPrefetchOrder\(\)\{\s*const span = TL\.matrix && TL\.matrix\.span;\s*if\(!span\) return \[\];/.test(code)
     && !/Promise\.all\([^)]*kpiFetchMonth/.test(code.slice(code.indexOf("function prefetchSpanKpis"), code.indexOf("function renderMonthFrame"))));
  // (7) keyboard and ARIA
  // 12 Oct fix pass — NARROWED: on the map canvas the arrows are Mapbox's pan keys; they step the month on the bar only
  ok("keyboard: Space toggles Play on the bar or the map; the arrows step a month on the bar only; never inside an input or select",
     /document\.addEventListener\('keydown', function\(e\)\{\s*if\(!TL\.on \|\| e\.altKey \|\| e\.ctrlKey \|\| e\.metaKey\) return;/.test(code)
     && /if\(tag === 'INPUT' \|\| tag === 'SELECT' \|\| tag === 'TEXTAREA'\) return;/.test(code)
     && /if\(!inBar && !inMap\) return;/.test(code)
     && /if\(e\.key === ' ' \|\| e\.key === 'Spacebar'\)\{ if\(tag === 'BUTTON' && inBar\) return; e\.preventDefault\(\); toggleTimeline\(\); \}/.test(code)
     && /else if\(e\.key === 'ArrowLeft' && inBar\)\{ e\.preventDefault\(\); stepTimeline\(-1\); \}/.test(code)
     && /else if\(e\.key === 'ArrowRight' && inBar\)\{ e\.preventDefault\(\); stepTimeline\(1\); \}/.test(code)
     && !/else if\(e\.key === 'Arrow(Left|Right)'\)\{/.test(code));
  ok("ARIA: the bar is a focusable named group; Play carries aria-pressed; the slider is named Month and speaks the month",
     // NARROWED 12 Oct 2026 (night): the bar ships minimal (class="tl-compact")
     /<div id="timeline-bar" class="tl-compact" role="group" aria-label="Forecast timeline" tabindex="0">/.test(html)
     && /<button type="button" class="tl-btn" id="tl-play" onclick="toggleTimeline\(\)" title="Play \/ pause" aria-label="Play" aria-pressed="false">/.test(html)   // 12 Oct fix pass: was "Play or pause"
     && /<input type="range" id="tl-range" min="1" max="60" value="1" oninput="onTimelineScrub\(this\.value\)" aria-label="Month" aria-valuetext="Jan 2026">/.test(html)
     && /b\.setAttribute\('aria-pressed', 'true'\)/.test(code) && /b\.setAttribute\('aria-pressed', 'false'\)/.test(code)
     && /r\.setAttribute\('aria-valuetext', monthLabel\(m\)\)/.test(code));
  ok("ARIA: a polite live region announces the month when playback stops (and the reason when it is a clash)",
     /<div id="tl-live" class="sr-only" aria-live="polite" aria-atomic="true"><\/div>/.test(html)
     && /\.sr-only\{ position:absolute; width:1px; height:1px;/.test(html)
     && /function announceTimeline\(text\)\{\s*const el=document\.getElementById\('tl-live'\); if\(el\) el\.textContent = text;/.test(code)
     && /const was = TL\.playing;[\s\S]{0,400}if\(was\) announceTimeline\(typeof reason === 'string' \? reason : 'Paused at ' \+ monthLabel\(TL\.month\)\);/.test(code)
     && /stopTimeline\(monthLabel\(month\) \+ ' · playback paused: '/.test(code)
     && !/announceTimeline\(monthLabel\(month\) \+ ' · playback paused: '/.test(code));   // 12 Oct fix pass: one write, not two
  {
    // 12 Oct 2026 (fix pass; both reviewers) — NARROWED: it read the bar's markup plus a string typed into the test, so
    // it passed on the old file. It now reads the STRING LITERALS of every block the review touched, and the legend
    // markup, and must find the new strings in them.
    const lits = t => (t.match(/'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`|"(?:[^"\\\n]|\\.)*"/g) || []).join(" ");
    const cut = (t, a, b) => { const i = t.indexOf(a), j = t.indexOf(b, i + 1); return i >= 0 && j > i ? t.slice(i, j) : ""; };
    const readable = [
      lits(cut(code, "function tlLoopBounds", "const WARN")), lits(cut(code, "const WARN", "(function initAnalysis")),
      lits(cut(code, "function calculateKPIs", "function applyFilters")), lits(cut(code, "const kindLabels", "</script>")),
      cut(html, '<div id="timeline-bar"', '<div id="tl-live"'), cut(html, '<div id="zone-kinds"', "Existing rail network"),
    ].join(" ");
    const must = ["nothing approved", "loading figures", "Paused at ", "playback paused: ", "Over a planning flag",
                  "two-way movements a day against a planning flag of", "routes over planning flags", "nothing recorded since",
                  "Full horizon", "Advisory", "Weight / height limit"];
    const missing = must.filter(w => !readable.includes(w));
    ok("wording: nothing a person reads in the new strings says truck, real-time, live tracking, AI, optimise, predict or secure",
       readable.length > 2000 && missing.length === 0
       && !/truck|real-time|live tracking|telematics|optimi[sz]e|predict|\bsecure\b/i.test(readable) && !/\bAI\b/.test(readable),
       "missing: " + JSON.stringify(missing) + " length " + readable.length);
  }

  // ---- run the timeline block against a fake DOM ------------------------------------------------------------
  const tStart = src.indexOf("const TL_UNIT_WORD = { vehicles: 'trips'");
  const tEnd = src.indexOf("// ===== 2026-09-02 (§8)");
  ok("the timeline block is one contiguous slice (TL_UNIT_WORD … the keydown listener)", tStart > 0 && tEnd > tStart);
  if (tStart > 0 && tEnd > tStart) {
    const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const CONFIG = { MONTH_COUNT: 60, START_YEAR: 2026, FORECAST_UNIT: 'vehicles', API_BASE: '' };
    const monthLabel = i => names[(i - 1) % 12] + ' ' + (CONFIG.START_YEAR + Math.floor((i - 1) / 12));
    const mkEl = (tag) => ({ tagName: tag, attrs: {}, style: {}, textContent: "", value: "", checked: false, children: [],
      setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; },
      contains(x) { return x === this || this.children.includes(x); } });
    const byId = {};
    for (const [id, tag] of [["timeline-bar", "DIV"], ["tl-play", "BUTTON"], ["tl-range", "INPUT"], ["tl-label", "SPAN"], ["tl-speed", "SELECT"],
                             ["tl-seg-plan", "BUTTON"], ["tl-seg-full", "BUTTON"], ["tl-live", "DIV"], ["map", "DIV"], ["toggle-forecast", "INPUT"]]) { byId[id] = mkEl(tag); byId[id].id = id; }
    for (const id of ["tl-play", "tl-range", "tl-speed", "tl-seg-plan", "tl-seg-full"]) byId["timeline-bar"].children.push(byId[id]);
    const canvas = mkEl("CANVAS"); byId["map"].children.push(canvas);
    const listeners = {};
    const document = { getElementById: id => byId[id] || null, addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); } };
    const calls = { setInterval: 0, clearInterval: 0, setData: 0, months: [], warnings: [] };
    const features = [];
    for (const [rid, type] of [["R1", "Inbound Highway"], ["R1", "Outbound Highway"], ["R2", "Inbound Highway"], ["R2", "Outbound Highway"], ["R3", "Inbound Highway"], ["R3", "Outbound Highway"]])
      features.push({ geometry: { type: "LineString" }, properties: { route_id: rid, type } });
    features.push({ geometry: { type: "Point" }, properties: { type: "Node", id: "N1" } });
    const map = { getSource: () => ({ _data: { features }, setData() { calls.setData++; } }) };
    const WARN = { counts: { clash: 0, warn: 0, caution: 0 }, countsMonth: null, open: false };
    const KPI = { cache: {} };
    const f = new Function("document", "window", "localStorage", "setInterval", "clearInterval", "setTimeout", "CONFIG", "map",
      "perWorkingDay", "monthLabel", "ensureForecastLayers", "ensureFlowLayer", "applyZoneMonth", "applyFilters", "renderTimelineWarnings",
      "startFlowAnimation", "stopFlowAnimation", "WARN", "KPI", "kpiFetchMonth", "fetch", "FORECAST_WORKING_DAYS",
      src.slice(tStart, tEnd) + "\nreturn { TL, tickTimeline, tlLoopBounds, setTimelineFull, tlStartMonth, monthHasVolume, renderMonthFrame, startTimeline, stopTimeline, setTimelineMonth, toggleTimeline, stepTimeline, tlPrefetchOrder, ensureTimelineMatrix };");
    // 12 Oct fix pass: the fetch is a delegate (it still throws unless a pin installs one) so the matrix dedupe can be run
    let fakeFetch = () => { throw new Error("fetch must not be called"); };
    let api = null, err = "";
    try {
      api = f(document, { matchMedia: null }, { getItem: () => null, setItem() {} }, () => { calls.setInterval++; return 7; }, () => { calls.clearInterval++; }, () => {},
              CONFIG, map, v => Math.round(v / 22), monthLabel, () => {}, () => {}, () => {}, () => {}, m => { calls.warnings.push(m); },
              () => {}, () => {}, WARN, KPI, () => Promise.resolve({}), (...a) => fakeFetch(...a), 22);
    } catch (e) { err = e.message; }
    ok("⭐ the timeline block runs against a fake DOM", !!api, err);
    if (api) {
      const TL = api.TL;
      const cur = (new Date().getFullYear() - 2026) * 12 + new Date().getMonth() + 1;
      const matrix = (months) => {
        const monthly = {}; months.forEach(([m, v]) => { monthly[String(m)] = v; });
        return { byRoute: { r1: { monthly }, r2: { monthly: { "10": 30 } } }, unit: "vehicles", working_days: 22,
                 volMonths: new Set(months.map(x => x[0]).concat([10])), span: [Math.min(...months.map(x => x[0]), 10), Math.max(...months.map(x => x[0]), 10)] };
      };
      ok("TL starts on the full-horizon switch OFF, unpaused, month 1", TL.full === false && TL.clashPaused === false && TL.month === 1 && TL.ticked === null);
      TL.matrix = matrix([[9, 100], [10, 200], [12, 50]]);
      ok("the loop bounds are the span with volume [9, 12]; Full horizon makes them [1, 60]; off again restores the span",
         JSON.stringify(api.tlLoopBounds()) === "[9,12]"
         // NARROWED 12 Oct 2026 evening (M3 bar): the pair says which is on (was the checkbox's `checked`)
         && (api.setTimelineFull(true), JSON.stringify(api.tlLoopBounds()) === "[1,60]"
             && byId["tl-seg-full"].attrs["aria-checked"] === "true" && byId["tl-seg-plan"].attrs["aria-checked"] === "false")
         && (api.setTimelineFull(false), JSON.stringify(api.tlLoopBounds()) === "[9,12]"
             && byId["tl-seg-full"].attrs["aria-checked"] === "false" && byId["tl-seg-plan"].attrs["aria-checked"] === "true"));
      // 12 Oct 2026 evening (M3 bar): wall mode's hold - a tick inside TL.holdUntil leaves the month where it is
      { const keepM = TL.month; TL.month = 10; TL.holdUntil = Date.now() + 60000; api.tickTimeline(); const held = TL.month;
        TL.holdUntil = 0; api.tickTimeline(); const moved = TL.month; TL.month = keepM;
        ok("⭐ M3 wall mode: a tick inside the hold leaves the month (10 stays 10); after it the loop moves on (10 to 11)", held === 10 && moved === 11, held + " " + moved); }
      // ...and moving the month by hand starts a new loop: the once-per-loop pause is re-armed (seen live: Play from September
      // ran through a red October because the last loop's pause was still spent)
      { TL.clashPaused = true; api.stepTimeline(1); const a = TL.clashPaused === false; api.stopTimeline();
        ok("⭐ M3: a step by hand re-arms the once-per-loop clash pause (it stayed spent from the last loop)", a); }
      // 12 Oct fix pass — NARROWED: it returned true without calling tlStartMonth() whenever today's month carried volume
      // (October 2026 does, in this fixture); the matrix here has no volume in today's month, whatever today is
      { const keep = TL.matrix; TL.matrix = { byRoute: {}, volMonths: new Set([cur + 3, cur + 5]), span: [cur + 3, cur + 5] };
        ok("the start month is the first month with volume when today's month has none", api.tlStartMonth() === cur + 3);
        TL.matrix = keep; }
      { const m2 = matrix([[cur, 5], [9, 100], [12, 50]]); const keep = TL.matrix; TL.matrix = m2;
        ok("...and today's calendar month when it carries volume", api.tlStartMonth() === cur && api.monthHasVolume(cur));
        TL.matrix = keep; }
      // the loop: 10 -> 11 (empty month inside the span keeps its dwell) -> 12 -> wraps to 9 and re-arms the pause
      TL.month = 10; TL.clashPaused = true; calls.warnings.length = 0;
      api.tickTimeline(); const a = TL.month; api.tickTimeline(); const b = TL.month; api.tickTimeline(); const c = TL.month;
      ok("⭐ ticks run 10 → 11 → 12 → 9: within the span, the empty November is shown, the wrap re-arms the clash pause and marks the month as ticked",
         a === 11 && b === 12 && c === 9 && TL.clashPaused === false && TL.ticked === 9 && calls.warnings.join(",") === "11,12,9");
      TL.month = 3; api.tickTimeline();
      ok("a month outside the span (scrubbed there) goes back to the first month with volume", TL.month === 9);
      TL.month = 59; api.setTimelineFull(true); api.tickTimeline(); const d = TL.month; api.tickTimeline(); const e2 = TL.month; api.setTimelineFull(false);
      ok("with Full horizon on the loop is 1..60 again", d === 60 && e2 === 1);
      // 12 Oct fix pass (F2, seen in Chrome as 10, 11, 12, 10 …): the loop from the month Play was pressed on wraps to the
      // span's FIRST month. A guard — tickTimeline already did this; the Chrome sequence came from figures and conditions
      // landing a tick late (F1), not from the wrap.
      TL.month = 10; api.tickTimeline(); const f1 = TL.month; api.tickTimeline(); const f2 = TL.month; api.tickTimeline(); const f3 = TL.month; api.tickTimeline(); const f4 = TL.month;
      ok("F2: from the start month (Oct) the loop runs 11, 12, then the span's first month (Sep), then Oct", [f1, f2, f3, f4].join(",") === "11,12,9,10");
      // one-month span: every tick is a wrap; it must not re-arm the pause on every tick
      { const keep = TL.matrix; TL.matrix = { byRoute: {}, volMonths: new Set([10]), span: [10, 10] };
        TL.month = 10; TL.clashPaused = true; api.tickTimeline(); const once = TL.month; api.tickTimeline();
        ok("⭐ a one-month span keeps its pause spent across ticks (it used to stop 750 ms after every press of Play)",
           once === 10 && TL.month === 10 && TL.clashPaused === true);
        TL.matrix = keep; TL.clashPaused = false; }
      // F3: the wrap ends the "month Play was pressed on"
      TL.month = 12; TL.startedOn = 10; api.tickTimeline();
      ok("F3: the wrap clears the month Play was pressed on", TL.month === 9 && TL.startedOn === null);
      // 12 Oct second fix pass: a one-month span "wraps" onto the same month every tick; that must not forget the
      // month Play was pressed on, or late conditions for it stop playback one tick in
      { const keep = TL.matrix; TL.matrix = { byRoute: {}, volMonths: new Set([10]), span: [10, 10] };
        TL.month = 10; TL.startedOn = 10; api.tickTimeline(); api.tickTimeline();
        ok("⭐ F3: a one-month span keeps the month Play was pressed on across its every-tick wraps", TL.month === 10 && TL.startedOn === 10);
        TL.matrix = keep; TL.startedOn = null; }
      // the prefetch order: the month on screen first, then the span in the order Play reaches it; the span only
      TL.month = 11;
      const po = typeof api.tlPrefetchOrder === "function" ? api.tlPrefetchOrder() : null;
      ok("⭐ F1: the KPI prefetch warms the month on screen first, then the rest of the span in play order (11, 12, 9, 10)",
         JSON.stringify(po) === "[11,12,9,10]");
      api.setTimelineFull(true);
      ok("...and with Full horizon on it still warms the span with volume only (it fired 60 GETs)", JSON.stringify(api.tlPrefetchOrder()) === "[11,12,9,10]");
      api.setTimelineFull(false);
      { const keep = TL.matrix; TL.matrix = { byRoute: {}, volMonths: new Set(), span: null };
        ok("...and nothing at all for a tenant with nothing approved (it fired 60 GETs)", JSON.stringify(api.tlPrefetchOrder()) === "[]");
        TL.matrix = keep; }
      // a double press fetches the matrix once
      { const keep = TL.matrix; let n = 0; TL.matrix = null;
        fakeFetch = () => { n++; return new Promise(() => {}); };
        api.ensureTimelineMatrix(); api.ensureTimelineMatrix();
        ok("⭐ a double press on Play fetches the forecast matrix once (the second waits on the first)", n === 1 && !!TL.matrixPending);
        fakeFetch = () => { throw new Error("fetch must not be called"); }; TL.matrixPending = null; TL.matrix = keep; }
      // renderMonthFrame: loaded leg only, the empty label, and the setData guard
      calls.setData = 0; TL.full = false;
      api.renderMonthFrame(10);
      // NARROWED 12 Oct 2026 evening (M3 bar): the heading is "October 2026"; the routes and trips are the line under it
      ok("⭐ A8: Oct 2026 labels 2 routes · 230 trips — the two return legs are not counted — and the source is sent once",
         byId["tl-label"].textContent === "October 2026" && TL.figsFallback === "2 routes · 230 trips this month" && calls.setData === 1
         && features.filter(x => x.properties.is_forecast).length === 4);
      api.renderMonthFrame(10);
      ok("⭐ the same month again does not re-send the source", calls.setData === 1);
      api.renderMonthFrame(11);
      ok("⭐ an empty month reads 'November 2026' / 'nothing approved this month' and sends the source once (the lines flipped off)",
         byId["tl-label"].textContent === "November 2026" && TL.figsFallback === "nothing approved this month" && calls.setData === 2);
      api.renderMonthFrame(1);
      ok("⭐ a second empty month in a row does NOT re-send the source", calls.setData === 2 && byId["tl-label"].textContent === "January 2026" && TL.figsFallback === "nothing approved this month");
      api.renderMonthFrame(12);
      // 12 Oct fix pass — REVERSED: it asserted "1 routes"
      ok("...and a month with volume after it does (R1 only: 1 route · 50 trips)", calls.setData === 3 && byId["tl-label"].textContent === "December 2026" && TL.figsFallback === "1 route · 50 trips this month");
      // play / stop: aria-pressed, the announcer, the resume-on-a-red-month rule, the slider's valuetext
      TL.on = true; TL.month = 10; api.setTimelineMonth(10);
      ok("the slider speaks the month", byId["tl-range"].attrs["aria-valuetext"] === "Oct 2026" && byId["tl-range"].value === 10);
      WARN.countsMonth = 10; WARN.counts.clash = 1; calls.setInterval = 0;
      api.startTimeline();
      ok("⭐ Play on a red month: aria-pressed true, one interval, the clash pause already spent for this loop, nothing ticked yet",
         TL.playing === true && byId["tl-play"].attrs["aria-pressed"] === "true" && calls.setInterval === 1 && TL.clashPaused === true && TL.ticked === null);
      ok("F3: Play remembers the month it was pressed on", TL.startedOn === 10);
      api.startTimeline();
      ok("a second Play while playing starts no second interval", calls.setInterval === 1);
      byId["tl-live"].textContent = "";
      api.stopTimeline();
      // 12 Oct fix pass — NARROWED: the announcement says what happened, not a bare month
      ok("⭐ stopping announces the month and drops aria-pressed", TL.playing === false && byId["tl-play"].attrs["aria-pressed"] === "false" && byId["tl-live"].textContent === "Paused at Oct 2026");
      byId["tl-live"].textContent = ""; api.stopTimeline();
      ok("stopping an already-stopped timeline announces nothing (scrubbing does not chatter)", byId["tl-live"].textContent === "");
      WARN.counts.clash = 0; TL.clashPaused = false; api.startTimeline();
      ok("Play on a month with no red condition leaves the pause armed", TL.clashPaused === false && TL.playing === true);
      api.stopTimeline();
      // keyboard
      const kd = (listeners.keydown || [])[0];
      ok("one keydown listener is registered on the document", (listeners.keydown || []).length === 1);
      if (kd) {
        const ev = (key, target, mods) => { const e = Object.assign({ key, target, altKey: false, ctrlKey: false, metaKey: false, prevented: false, preventDefault() { this.prevented = true; } }, mods || {}); kd(e); return e; };
        TL.on = true; TL.month = 10; TL.playing = false;
        const e1 = ev(" ", byId["timeline-bar"]);
        ok("⭐ Space on the bar starts playback and is swallowed", TL.playing === true && e1.prevented === true);
        const e2b = ev(" ", byId["timeline-bar"]);
        ok("...Space again pauses it", TL.playing === false && e2b.prevented === true);
        const e3 = ev(" ", byId["tl-play"]);
        ok("Space on the Play BUTTON is left to the button's own click (no double toggle)", TL.playing === false && e3.prevented === false);
        const e4 = ev("ArrowRight", canvas);
        // 12 Oct fix pass — REVERSED: on the map the arrows are Mapbox's pan keys; a press panned AND stepped the month
        ok("⭐ ArrowRight with the map focused is left to the map (it pans; the month does not step)", TL.month === 10 && e4.prevented === false);
        const e4b = ev("ArrowRight", byId["timeline-bar"]);
        ok("ArrowRight on the bar steps to the next month", TL.month === 11 && e4b.prevented === true);
        const e4c = ev(" ", canvas);
        ok("Space with the map focused still plays", TL.playing === true && e4c.prevented === true);
        ev(" ", canvas);
        const e5 = ev("ArrowLeft", byId["timeline-bar"]);
        ok("ArrowLeft on the bar steps back", TL.month === 10 && e5.prevented === true);
        const e6 = ev("ArrowRight", byId["tl-range"]);
        ok("the slider keeps its own arrow keys", TL.month === 10 && e6.prevented === false);
        const e7 = ev("ArrowRight", byId["tl-speed"]);
        ok("...and so does the speed select", TL.month === 10 && e7.prevented === false);
        const e8 = ev("ArrowRight", byId["timeline-bar"], { ctrlKey: true });
        ok("a modified key is ignored", TL.month === 10 && e8.prevented === false);
        TL.on = false; const e9 = ev(" ", byId["timeline-bar"]);
        ok("with the bar shut the keys do nothing", TL.playing === false && e9.prevented === false);
        const e10 = ev("ArrowRight", mkEl("DIV"));
        ok("a key elsewhere on the page is ignored", TL.month === 10 && e10.prevented === false);
      }
    }
  }
}

// ---- 12 Oct 2026 — public map review (notes/map-review-1011): conditions, closures, zones,
// the forecast overlay. Each pin would fail on main 1cea4e3.
{
  const warnBlock = code.slice(code.indexOf("const WARN"), code.indexOf("(function initAnalysis"));
  // 1. live A1 — the restriction condition is month-aware, deduped, highlighted, flown to
  // 12 Oct fix pass — RENAMED (the tests reviewer): the query string is what is asserted; this branch's server ignores it,
  // claude/public-map-backend's /api/routes/restrictions honours it
  ok("A1: the restriction check sends include_expired=1 (honoured by the Track B server, ignored before it); the client filters by month",
     code.includes("fetch(CONFIG.API_BASE + '/routes/restrictions?include_expired=1')"));
  ok("A1: a hit is in the month when its from/to window overlaps monthSpan (dnum; no dates = always)",
     /function hitInMonth\(h, month\)/.test(code) && /const \[lo, hi\] = monthSpan\(month\);/.test(code)
     && code.includes("return dnum(day(h.from), 0) <= hi && dnum(day(h.to), 99999999) >= lo;"));
  ok("A1: the panel only lists hits in force this month, one row per closure per route",
     code.includes("const inMonth = dedupeHits(hit.hits.filter(h => hitInMonth(h, month)));")
     && /function dedupeHits\(hits\)/.test(code) && code.includes("const k = h.event_number ? 'e|' + h.event_number : 'd|' + [h.kind, h.what, h.from, h.to].join('|');")
     && !code.includes("const worst = hit.hits[0];"));
  ok("A1: the matched NH closure is drawn on its own amber layer, keyed by event_number",
     /id:'restriction-hit', type:'line', source:'restrictions-source'/.test(code)
     && /function restrictionHitFilter\(evs\)/.test(code)
     && code.includes("['in', ['to-string', ['get','event_number']], ['literal', evs]]")
     && /id:'restriction-hit'[\s\S]{0,400}'line-color':'#D97706'/.test(code));
  ok("A1: ...shown whether or not the closures toggle is on (the toggle filter never touches it)",
     /id:'restriction-hit'[\s\S]{0,300}visibility:'visible'/.test(code)
     && !/\['restriction-hit', \[/.test(code)
     && code.includes("applyRestrictionFilter();\n        applyRestrictionHits();"));
  ok("A1: a row's Show on map flies to the closure's bounds (and selects its route), not the whole route",
     code.includes("if (kind === 'h') { showRestrictionHit(id); return; }")
     && /function showRestrictionHit\(id\) \{\s*const \{ ev, rid: own \} = splitHitRowId\(id\);/.test(code)   // 12 Oct fix pass: takes the row id (event|route)
     && /String\(x\.properties\.event_number\) === String\(ev\)/.test(code)
     && /map\.fitBounds\(\[\[b\[0\], b\[1\]\], \[b\[2\], b\[3\]\]\], \{ padding: 90, maxZoom: 14, duration: reducedMotion\(\) \? 0 : 700 \}\)/.test(code)
     // 12 Oct fix pass — NARROWED: the row's id is event|route, so each row selects its OWN route (six routes share one A46 closure)
     && code.includes("kind: worst.event_number ? 'h' : 'r', id: worst.event_number ? hitRowId(worst.event_number, p.route_id) : p.route_id")
     && !code.includes("WARN.hitRoute[String(h.event_number)] = p.route_id"));
  ok("A1: the highlight follows the live rows and is cleared with the timeline",
     // 12 Oct fix pass — NARROWED: an event maps to EVERY route it was found on; the highlight stays while any of their rows is live
     code.includes("setRestrictionHits(liveHitEvents(hitEvents, WARN.hitRoute, live));")
     && code.includes("return hitEvents.filter(ev => live.some(i => i.kind === 'h' && (hitRoute[ev] || []).includes(i.who)));")
     && !code.includes("WARN.hitRoute[ev] === i.who")
     && /renderConditionsPill\(\[\]\); setCondRing\(\[\]\); setRestrictionHits\(\[\]\); setCapBadges\(\[\]\);/.test(code));

  // 2. live A2 — a basemap switch brings the forecast overlay, the ring and the hit layer back
  const styleLoad = code.slice(code.indexOf("map.on('style.load', async () => {"), code.indexOf("let ALIGNMENT_POPUP_WIRED"));
  ok("A2: the style.load handler re-renders the open month and its conditions after the sources are back",
     styleLoad.includes("if (typeof TL !== 'undefined' && TL.on && TL.matrix) { renderMonthFrame(TL.month); renderTimelineWarnings(TL.month); }")
     && styleLoad.indexOf("renderMonthFrame(TL.month)") > styleLoad.indexOf("if (RESTR.data) ensureRestrictionLayers(); else loadRestrictions();"));
  ok("A2: the hit layer and the cap badge are re-added from their builders with the filter they had",
     code.includes("const evs = (typeof WARN !== 'undefined' && WARN.hitEvents) || [];")
     && code.includes("const ids = (typeof WARN !== 'undefined' && WARN.capRoutes) || [];")
     && /function ensureCapBadgeLayer\(\)/.test(code) && code.includes("raiseMarks();\n        ensureCapBadgeLayer();"));

  // 3. live A7 — the closures feed is asked for the tenant's bbox, clipped client-side as the fallback, not deferred
  ok("A7: /api/restrictions is asked with ?bbox=w,s,e,n from the network's bounds plus 20 km",
     code.includes("const RESTR_MARGIN_KM = 20;") && /async function restrictionBbox\(\)/.test(code)
     && code.includes("const q = bb ? '?bbox=' + bb.map(v => v.toFixed(4)).join(',') : '';")
     && code.includes("fetch(CONFIG.API_BASE + '/restrictions' + q)"));
  ok("A7: the same box is applied client-side when the server returns the national set",
     /function clipToBbox\(fc, bb\)/.test(code) && code.includes("RESTR.data = bb ? clipToBbox(fc, bb) : fc;")
     && code.includes("return g && g[0] <= bb[2] && g[2] >= bb[0] && g[1] <= bb[3] && g[3] >= bb[1];"));
  ok("A7: the network's bounds are settled once, on success AND failure, and waited on for at most 20 s",
     (code.match(/settleNetworkBounds\(/g) || []).length >= 3
     && code.includes("settleNetworkBounds(null);") && code.includes("fitToNetworkOnce(fc) {\n        settleNetworkBounds(fc);")
     && /Promise\.race\(\[NETWORK_BOUNDS, new Promise\(res => setTimeout\(\(\) => res\(NET_BBOX\), 20000\)\)\]\)/.test(code));
  ok("A7: the download is still NOT deferred to the first toggle (style.load loads it when there is no data)",
     styleLoad.includes("if (RESTR.data) ensureRestrictionLayers(); else loadRestrictions();")
     && code.includes("if(!RESTR.data){ loadRestrictions(); return; }"));

  // 4. D24 — zones per kind
  ok("D24: the five kinds are a list, unknown kinds fold into 'other', haul roads stay excluded from the overlay",
     code.includes("const ZONE_KINDS = ['closure', 'works', 'weight_limit', 'haul_road', 'other'];")
     && code.includes("kind: ZONE_KINDS.includes(z.kind) ? z.kind : 'other'")
     && code.includes("const kindsOn = ZONE_KINDS.filter(k => k !== 'haul_road' && zoneKindVisible(k));")
     && code.includes("['in', ['get', 'kind'], ['literal', kindsOn]]"));
  ok("D24: closure = amber 25% fill with a solid 2 px amber edge; works = lighter amber, dashed edge",
     code.includes("const ZONE_FILL_OPACITY = ['match', ['get', 'kind'], 'closure', 0.25, 'works', 0.18, 'weight_limit', 0.06, 0.15];")
     && code.includes("'line-width': ['match', ['get', 'kind'], 'closure', 2, 1.5]")
     && /id: 'zone-outline-works', type: 'line', source: 'zones-source'[\s\S]{0,200}'line-color': ZONE_AMBER, 'line-width': 2, 'line-dasharray': \[2, 1\.5\]/.test(code)
     && code.includes("['zone-outline-works', ['==', ['get', 'kind'], 'works']]"));
  ok("D24: a weight/height limit is a boxed label carrying the limit text read from the name or note",
     /function zoneLimitText\(z\)/.test(code) && code.includes("limit_text: zoneLimitText(z)")
     && /id: 'zone-limit', type: 'symbol', source: 'zones-source'[\s\S]{0,300}'icon-image': 'zone-limit-badge', 'icon-text-fit': 'both'/.test(code)
     // 12 Oct fix pass — NARROWED: no limit text, no box (the name used to fill it and print again under it); m³ is not a height
     && code.includes("['zone-limit', ['all', ['==', ['get', 'kind'], 'weight_limit'], ['!=', ['get', 'limit_text'], '']]]")
     && !code.includes("return z.name || '';") && code.includes("(t|tonnes?|m)(?![\\w\\u00b2\\u00b3])")
     && code.includes("if (!map.hasImage('zone-limit-badge')) map.addImage('zone-limit-badge', zoneBadgeImage()"));
  ok("D24: advisory is grey, and the red that meant 'avoided by routing' is gone from the zone rows and the note",
     code.includes("ZONE_GREY = '#64748B'") && !/id="layer-zones"[^\n]*#DC2626/.test(html)
     && !html.includes("red = avoided by routing"));
  ok("D24: the legend is month-aware — a kind's row dims when none of it is in force in the month on screen",
     code.includes("row.classList.toggle('dim', !inForce[k]);")
     && /\.zone-kind\.dim label, \.zone-kind\.dim \.color-dot \{ opacity:\.4; \}/.test(html)
     && code.includes("if (!span || (p.start_n <= span[1] && p.end_n >= span[0])) inForce[p.kind] = (inForce[p.kind] || 0) + 1;")
     // 12 Oct fix pass: the haul-road row drives a layer drawn from the network with no month filter, so it never dims
     && code.includes("if (k === 'haul_road') { row.classList.remove('dim'); row.title = 'drawn from the network; not filtered by month'; return; }"));
  ok("D24: the Haul road row is the Temporary haul switch, kept in step both ways (never a second layer)",
     code.includes("if (kind === 'haul_road') {\n            const t = document.getElementById('layer-temp');")
     && code.includes("const z = document.getElementById('layer-zone-haul_road');"));
  ok("D24: the group master still hides every zone layer, including the new ones",
     code.includes("const ZONE_LAYERS = ['zone-fill', 'zone-outline', 'zone-outline-works', 'zone-label', 'zone-limit'];")
     && code.includes("ZONE_LAYERS.forEach(l => toggleLayer(l, visible));"));

  // 5. D21 / D33 — the planning-flag condition
  // 12 Oct fix pass — NARROWED: the sentence names its unit and is built by capSentence()
  const capWhat = (code.match(/return `\$\{rid\}: \$\{shown\} two-way movements a day against a planning flag of \$\{cap\}`;/) || [""])[0];
  ok("D21: a fourth source compares the month's loaded-leg movements a day with max_vehicles_per_day",
     code.includes("const cap = Number(p.max_vehicles_per_day);")
     && code.includes("loadsByRoute[l.route_id] = (loadsByRoute[l.route_id] || 0) + (Number(l.vehicle_loads) || 0);")
     && code.includes("const perDay = loadsByRoute[p.route_id] / wdm;") && code.includes("if (perDay <= cap) return;"));
  ok("D21: working days come from the API (kp.working_days), never a literal 22, and the loaded leg only (linesOnScreen)",
     code.includes("const wdm = (kp && kp.working_days > 0) ? kp.working_days : FORECAST_WORKING_DAYS;")
     && !/\/\s*22\b/.test(warnBlock)
     && /f\.properties\.type === 'Inbound Highway'\)\) return;/.test(code));
  ok("D33: the row is warn level, says 'planning flag', and never 'limit'",
     code.includes("noun: 'Over a planning flag'") && code.includes("what: capSentence(p.route_id, perDay, cap)") && capWhat.length > 0 && !/limit/i.test(capWhat)
     && /key: `c\|\$\{p\.route_id\}\|\$\{month\}`, lvl: 'warn', src: 'cap'/.test(code));
  ok("D33: the pill counts it under its own noun, not as a route limit",
     code.includes("const k = i.src === 'cap' ? 'cap' : i.lvl;")
     // 12 Oct fix pass — NARROWED: a correct plural ("2 over a planning flag" read as a count of flags)
     && code.includes("c.cap === 1 ? '1 route over a planning flag' : c.cap + ' routes over planning flags'")
     && !code.includes(".replace(/flags/, 'flag')"));
  ok("D33: a small badge sits on the route label of every route over its flag — loaded leg, amber, cleared on close",
     /id:'forecast-cap-badge',type:'symbol',source:'routes-source'/.test(code)
     && code.includes("['concat', 'over planning flag ', ['to-string', ['get', 'max_vehicles_per_day']]]")
     && code.includes("return ['all', ['==', ['get', 'type'], 'Inbound Highway'], ['in', ['get', 'route_id'], ['literal', ids]]];")
     && (code.match(/'forecast-flow','forecast-cap-badge'\]\.forEach\(l\s?=>\s?\{ if\(map\.getLayer\(l\)\) map\.removeLayer\(l\); \}\);/g) || []).length === 2
     && code.includes("setCapBadges(overCap.filter(rid => live.some(i => i.src === 'cap' && i.id === rid)));"));

  // 6. review §3 row 3 — the overlay honours the filters; per-route roll-up; WS names; the stockpile sentence
  ok("row 3: the four forecast overlay layers are filtered by the leg toggles and the routes passing routePassesFilters",
     /function forecastLayerFilter\(\)/.test(code)
     && code.includes("&& f.properties.route_id && routePassesFilters(f.properties)) rids.push(f.properties.route_id);")
     && code.includes("['in', ['get', 'type'], ['literal', legs]],")
     && code.includes("['in', ['get', 'route_id'], ['literal', rids]]];")
     && code.includes("const FORECAST_OVERLAY_LAYERS = ['forecast-casing','forecast-layer','forecast-labels','forecast-flow'];")
     && !/filter:\['==','is_forecast',true\]/.test(code));
  ok("row 3: applyFilters() re-applies it, and so do both overlay adders",
     code.includes("if (typeof applyForecastFilter === 'function') applyForecastFilter();")
     && (code.match(/applyForecastFilter\(\);/g) || []).length >= 2
     && code.includes("ensureFlowLayer();\n                applyForecastFilter();"));
  ok("row 3: the timeline matrix sums the monthly figures per route across its per-line entries",
     code.includes("acc.monthly[k] = (acc.monthly[k]||0) + (Number(rt.monthly[k])||0);")
     && !code.includes("byR[(rt.route_id||'').toString().trim().toLowerCase()]=rt;"));
  // 12 Oct 2026 (the base merge): the capacity is "has a capacity of", as the bulletin's stockpile_wording says it
  ok("the map's stockpile sentence says 'has a capacity of N; M recorded', the bulletin's words, never 'holds'",
     code.includes("const head = `${sp.name} has a capacity of ${Math.round(sp.capacity_qty).toLocaleString()} ${u}; ${Math.round(mm.balance_end).toLocaleString()} ${u}`;")
     && !code.includes("${sp.name} holds "));
  ok("row 3 / D23: the stockpile sentence says what is recorded at month end, not what 'the plan puts'",
     code.includes("recorded in it at the end of ${monthLabel(month)}.") && !code.includes("The plan puts")
     // 12 Oct fix pass: a month after the last recorded movement carries the balance forward and says so
     && code.includes("recorded at the end of ${monthLabel(last)}; nothing recorded since.") && code.includes("what: pileSentence(sp, month, u), sort: 0"));
}

// ---- 12 Oct 2026 — the mobile hotfix (review 2.8, live A6), names and the small bugs (claude/mr1-mobile) -------
// Source-level pins on the phone overrides. Every phone rule is an override INSIDE a media block, so the base
// `.sidebar … width:300px`, the base #tl-label / #tl-speed rules and the base @media (max-width:1023px) pins above
// keep passing untouched. No browser here: what the rules do at 385 / 768 / 667x375 px was checked by hand.
{
  const phone = (html.match(/@media \(max-width:1023px\)\{([\s\S]*?)\n        \}\n        @media \(min-width:701px\)/) || ["", ""])[1];
  const narrow = (html.match(/@media \(max-width:700px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  const landscape = (html.match(/@media \(max-width:1023px\) and \(max-height:480px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  // the timeline bar's phone blocks come AFTER its base rules (same specificity: order decides — the first build put them
  // before and the base `body.sidebar-closed #timeline-bar{ left:50%; }` won, measured live as a half-width bar at 385 px)
  const tlBase = html.indexOf("#tl-speed{ border:1px solid var(--line);");
  const tlPhone = (html.slice(tlBase).match(/@media \(max-width:1023px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  const tlNarrow = (html.slice(tlBase).match(/@media \(max-width:700px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  ok("mobile: the phone media blocks exist — stacked (≤1023), phone (≤700), landscape (≤1023 and ≤480 high), and the timeline bar's two after its base rules",
     phone.length > 0 && narrow.length > 0 && landscape.length > 0 && tlBase > 0 && tlPhone.length > 0 && tlNarrow.length > 0,
     `${phone.length}/${narrow.length}/${landscape.length}/${tlPhone.length}/${tlNarrow.length}`);
  ok("...and no timeline-bar rule sits in the early (pre-base) phone blocks, where the base would override it",
     !/#timeline-bar|#tl-label|#tl-speed/.test(phone) && !/#timeline-bar|#tl-label|#tl-speed/.test(narrow));
  // 2. viewport and touch
  ok("mobile: the viewport meta no longer forbids pinch-zoom (no maximum-scale, no user-scalable=no)",
     html.includes('<meta name="viewport" content="width=device-width, initial-scale=1">')
     && (html.match(/<meta name="viewport"/g) || []).length === 1
     && !/<meta[^>]*(maximum-scale|user-scalable)/.test(html));
  ok("mobile: touch-action:manipulation on the panel, the menu button, the bar, the conditions panel, the timeline bar and the drawer",
     /\.sidebar, #menu-toggle, #kpi-hud, #tl-warnings, #timeline-bar, #route-drawer\{ touch-action:manipulation; \}/.test(html));
  // 1a / 1f. the JS threshold matches the CSS; the toggle never re-opens
  ok("mobile: the sidebar auto-closes below 1024 (the CSS breakpoint), not 768, and nothing else tests 768",
     code.includes("if (window.innerWidth <= 1023) closeSidebar();") && !/innerWidth <= 768/.test(code));
  ok("mobile: closeSidebar() closes only an OPEN panel, and filterByNode uses it (the old toggle re-opened a closed panel on a phone)",
     code.includes("function sidebarIsOpen() { return !document.getElementById('main-sidebar').classList.contains('closed'); }")
     && code.includes("function closeSidebar() { if (sidebarIsOpen()) toggleSidebar(); }")
     && code.includes("applyFilters(); if(window.innerWidth <= 1023) closeSidebar();")
     && !/if\(window\.innerWidth <= \d+\) toggleSidebar\(\)/.test(code));
  // 1b. the panel is a drawer over the map below 1024, above the bar, with its own close control; full width on a phone
  ok("mobile: below 1024 the panel sits above the bar (15), the conditions panel (24) and the timeline (25), under the demo strip (30)",
     /\.sidebar\{ z-index:28; \}/.test(phone) && /\.sidebar \{[^}]*z-index:10;/.test(html) && /#demo-notice\{[^}]*z-index:30;/.test(html));
  ok("mobile: below 1024 the map is not pushed 300 px right, nor is the route drawer",
     /#map, \.sidebar ~ #map\{ left:0; \}/.test(phone) && /#route-drawer, body\.sidebar-closed #route-drawer\{ left:0; \}/.test(tlPhone)
     && !/#route-drawer/.test(phone)   // its base rule comes after the early block, so the override lives after the base
     && /#map \{ position:absolute; top:0; bottom:0; right:0; left:300px;/.test(html));   // the desktop base is untouched
  ok("mobile: the panel carries its own 44 px close control, first in the panel, shown below 1024 only, where the menu button hides while the panel is open",
     /<div class="sidebar" id="main-sidebar">\n\s+<button type="button" class="sidebar-close" id="sidebar-close" onclick="toggleSidebar\(\)" aria-label="Close the control panel"/.test(html)
     && /\.sidebar-close\{ display:none; position:absolute; top:10px; left:10px; width:44px; height:44px;/.test(html)
     && /\.sidebar-close\{ display:flex; \}/.test(phone) && /body:not\(\.sidebar-closed\) #menu-toggle\{ display:none; \}/.test(phone)
     && /body\.has-demo-notice \.sidebar\{ top:var\(--notice-h, 26px\); \}/.test(phone));
  ok("mobile: on a phone (≤700) the panel is the full width; the base stays 300 px",
     /\.sidebar\{ width:100%; border-right:none; \}/.test(narrow) && /\.sidebar \{ position:absolute; top:0; bottom:0; left:0; width:300px;/.test(html));
  // 1c. the timeline bar and the bar's lead labels
  ok("mobile: below 1024 the timeline bar is full width with 44 px buttons, the label wraps (no 190 px min-width), the speed select and close stay on screen",
     /#timeline-bar, body\.sidebar-closed #timeline-bar\{ left:12px; right:12px; transform:none; max-width:none; flex-wrap:wrap;/.test(tlPhone)
     && /#timeline-bar \.tl-btn\{ width:44px; height:44px;/.test(tlPhone) && /#timeline-bar \.tl-close\{ width:44px; height:44px;[^}]*margin-left:auto; \}/.test(tlPhone)
     && /#tl-label\{ min-width:0; white-space:normal; flex:1 1 120px;/.test(tlPhone)
     && /#tl-label\{ font-size:12px;[^}]*min-width:190px; white-space:nowrap; flex:0 0 auto; \}/.test(html));   // the base rule is untouched
  ok("mobile: on a phone the bar runs on two rows — label, speed, close above; the three buttons and the slider below (a ::after line break)",
     /#tl-label\{ order:1; \}/.test(tlNarrow) && /#tl-speed\{ order:2; \}/.test(tlNarrow) && /#timeline-bar \.tl-close\{ order:3; \}/.test(tlNarrow)
     && /#timeline-bar::after\{ content:""; flex:0 0 100%; height:0; order:4; \}/.test(tlNarrow)
     && /#timeline-bar \.tl-btn\{ order:5; \}/.test(tlNarrow) && /#timeline-bar input\[type=range\]\{ order:6; flex:1 1 60px; width:auto; \}/.test(tlNarrow));
  ok("mobile: the two lead labels cannot collide — below 1024 a label wraps inside its card and a card can shrink (the base keeps nowrap)",
     /#kpi-cards \.kpi-card\{ min-width:0; \}/.test(phone) && /#kpi-cards \.kpi-label\{ white-space:normal; \}/.test(phone)
     && /\.kpi-label\{[^}]*white-space:nowrap; \}/.test(html));
  // 1d. the conditions panel is capped by the viewport
  ok("mobile: the conditions panel's max-height is measured from the bar's bottom to the timeline bar's top (or the viewport's bottom edge), and cleared on the desktop",
     code.includes("const floor = (tb && tb.style.display !== 'none') ? Math.round(tb.getBoundingClientRect().top) - 8 : window.innerHeight - 12;")
     && code.includes("box.style.maxHeight = Math.max(120, floor - (Math.round(kpi.getBoundingClientRect().bottom) + 8)) + 'px';")
     && code.includes("{ box.style.top = ''; box.style.maxHeight = ''; return; }"));
  // 1e. landscape
  ok("mobile: landscape (≤480 px high) collapses the bar to one row of the two lead figures, and the block comes after the tablet row so it wins",
     /#kpi-cards\{ grid-template-columns:repeat\(2, minmax\(0, 1fr\)\); \}/.test(landscape) && /#kpi-cards \.kpi-card:not\(\.lead\)\{ display:none; \}/.test(landscape)
     && html.indexOf("@media (max-width:1023px) and (max-height:480px)") > html.indexOf("@media (min-width:701px) and (max-width:1023px)"));
  // 3. names
  ok("names: #menu-toggle is a button that names and reports its panel (was a div); toggleSidebar keeps aria-expanded true",
     html.includes('<button type="button" id="menu-toggle" onclick="toggleSidebar()" aria-controls="main-sidebar" aria-expanded="true">☰ Control Panel</button>')
     && !/<div id="menu-toggle"/.test(html)
     && code.includes("if (mt) mt.setAttribute('aria-expanded', String(sidebarIsOpen()));"));
  ok("names: the month slider is named 'Month' (aria-label) and the timeline's aria-valuetext sits beside it",
     /<input type="range" id="tl-range" min="1" max="60" value="1" oninput="onTimelineScrub\(this\.value\)" aria-label="Month" aria-valuetext="Jan 2026">/.test(html));
  {
    // every icon-only button (no letters in its text) carries an aria-label — static markup and the buttons built in JS
    const re = /<button\b([^>]*)>([^<]*)<\/button>/g;
    const bare = [];
    // (a button empty at source, #kpi-conditions, is filled with words at run time)
    for (const s of [html, code]) { let b; while ((b = re.exec(s)) !== null) { if (b[2].trim() && !/[A-Za-z]/.test(b[2]) && !/aria-label="/.test(b[1])) bare.push(b[0].slice(0, 80)); } }
    ok("names: every icon-only button has an aria-label (timeline ◀ ▶ ▶▶ ×, drawer ×, panel ×, basemap widget, conditions × ×)",
       bare.length === 0 && (html.match(/aria-label="/g) || []).length >= 8, JSON.stringify(bare));
    ok("...and the speed select is named", /<select id="tl-speed" onchange="setTimelineSpeed\(this\.value\)" title="[^"]*" aria-label="Play speed, months per second">/.test(html));
  }
  // 4. one hover handler
  ok("hover: ONE mousemove handler queries the three route layers (the forEach registered it three times and never used its argument)",
     (code.match(/map\.on\('mousemove'/g) || []).length === 1 && !code.includes("interactiveLayers.forEach")
     && code.includes("map.on('mousemove', (e) => {\n                    let features = map.queryRenderedFeatures(e.point, { layers: interactiveLayers.filter(l => map.getLayer(l)) });"));
  // 5. the demo strip on a phone
  ok("mobile: the demo strip is 14 px below 1024 (was 9.5), wrapping, and the offsets under it follow its MEASURED height (--notice-h, 26 px floor)",
     // NARROWED 13 Oct 2026 (D45, Option A): the strip's rule is 3 px (was 1 px)
     /body\.has-demo-notice #demo-notice\{ left:0; right:0; top:0; transform:none; border-radius:0; border-width:0 0 3px; white-space:normal; text-align:center; font-size:14px;/.test(phone)
     && !/#demo-notice\{[^}]*font-size:9\.5px/.test(html)
     && /body\.has-demo-notice #menu-toggle\{ top:calc\(var\(--notice-h, 26px\) \+ 14px\); \}/.test(phone)
     && /body\.has-demo-notice #kpi-hud, body\.has-demo-notice\.sidebar-closed #kpi-hud\{ padding-top:calc\(var\(--notice-h, 26px\) \+ 58px\); \}/.test(phone)
     && /body\.has-demo-notice #guide-btn\{ top:calc\(var\(--notice-h, 26px\) \+ 10px\); \}/.test(phone)
     // the calc rules follow the 40 / 84 / 36 floors inside the same block, so they win
     && phone.indexOf("#menu-toggle{ top:calc(") > phone.indexOf("#menu-toggle{ top:40px; }"));
  ok("mobile: measureNotice() reads the strip's height into --notice-h below 1024, removes it otherwise, watches the strip, and runs with every bar measurement",
     /function measureNotice\(\) \{/.test(code) && code.includes("document.body.style.setProperty('--notice-h', nh + 'px');")
     && code.includes("if (!on) { document.body.style.removeProperty('--notice-h'); return; }")
     && code.includes("dn._ro = new ResizeObserver(() => positionWarnStack()); dn._ro.observe(dn);")
     && /function positionWarnStack\(\) \{\n\s+measureNotice\(\);/.test(code)
     // and after the strip is created at tenant load, and when the app's bar takes it away
     && /setupGuide\(\);[^\n]*\n\s+if \(typeof positionWarnStack === 'function'\) positionWarnStack\(\);/.test(code)
     && /document\.body\.classList\.toggle\('has-demo-notice', false\);\n\s+if \(typeof positionWarnStack === 'function'\) positionWarnStack\(\);/.test(code));
}

// ---- 12 Oct 2026 — the Track A fix pass (three reviews of 07a522b + four defects seen in Chrome, F1-F4) ----------------
// Source pins for the CSS and the layers, then two sandboxes that RUN the code: the figures bar (calculateKPIs, F1) and
// the conditions (the whole warn block: closures on several routes, the planning flag, the stockpile sentence, F3).
// Both resolve promises, so they are collected in ASYNC_PINS and the summary waits for them.
{
  const phone = (html.match(/@media \(max-width:1023px\)\{([\s\S]*?)\n        \}\n        @media \(min-width:701px\)/) || ["", ""])[1];
  // F4 + the Guide pill (spec review): nothing of the guide floats over the open drawer on a phone or tablet
  ok("⭐ F4: below 1024, while the drawer is open, the guide strip, its dots and tips and the Guide pill are hidden",
     /body:not\(\.sidebar-closed\) \.guide-strip, body:not\(\.sidebar-closed\) \.guide-dot, body:not\(\.sidebar-closed\) \.guide-tip,\s*body:not\(\.sidebar-closed\) #guide-btn\{ display:none; \}/.test(phone)
     // the desktop is untouched: the rule lives only in the stacked block
     && (html.match(/body:not\(\.sidebar-closed\) \.guide-strip/g) || []).length === 1);
  // the 14 px floor on the new text
  // NARROWED 12 Oct 2026 evening (M3 bar): the Full horizon switch is the pair's buttons (.tl-seg button), 14 px
  ok("14 px: the zone-kind rows, the zone legend note and the Full horizon switch are 14 px (were 12.5, 12 and 11)",
     /#zone-kinds \.control-item \{ padding:4px 2px; font-size:14px; \}/.test(html)
     && /\.tl-seg button\{[^}]*font:500 14px/.test(html) && !/#timeline-bar \.tl-full\{/.test(html)
     && /<span style="font-size:14px;color:var\(--note\);">amber = closure or works/.test(html)
     && !/#zone-kinds \.control-item \{[^}]*font-size:12\.5px/.test(html));
  ok("14 px: the map's new badges (over planning flag, the boxed weight/height limit) are 14 px (were 10.5 and 11.5)",
     /id:'forecast-cap-badge'[\s\S]{0,400}'text-size':14,/.test(code)
     && /'text-field': \['get', 'limit_text'\], 'text-size': 14,/.test(code)
     && !/'text-size':10\.5/.test(code));
  // width by volume
  // REVERSED 12 Oct 2026 (the user, evening: "line width by volume leave out and change to heat map like the carbon"):
  // the forecast line is ONE width again; volume is a colour (the Volume heat map), never a width
  ok("⭐ width by volume is GONE: the forecast line and its casing are one width (3.5 / 6 px), no f_avg width stops",
     code.includes("const FORECAST_LINE_WIDTH = 3.5;") && code.includes("const FORECAST_CASING_WIDTH = 6;")
     && !code.includes("FORECAST_VOL_STOPS") && !code.includes("forecastWidth(")
     && !/\['interpolate', \['linear'\], \['to-number', \['get', '(f_avg|rl_mv)'\]/.test(code)
     && (code.match(/'line-width':\s?FORECAST_LINE_WIDTH/g) || []).length === 2 && (code.match(/'line-width':\s?FORECAST_CASING_WIDTH/g) || []).length === 2
     && !/'line-color':\s?CONFIG\.COLORS\.forecast,\s?'line-width':\s?3\.5/.test(code));
  ok("...and the routes stay blue: the forecast colour is untouched", (code.match(/'line-color':\s?CONFIG\.COLORS\.forecast,/g) || []).length === 2);
  // the drawer's half of review bug (d)
  ok("⭐ row 3 (d), the drawer: a route's analysis counts EVERY approved line of the route, not the first one find() met",
     code.includes("const rows=(mtx.routes||[]).filter(r=>(r.route_id||'').toString().trim().toLowerCase()===rl);")
     && code.includes("const totalT=rows.reduce((a,r)=>a+(r.total||0),0);")
     // NARROWED 12 Oct 2026 (the base merge of Track A and Track B): the per-line carbon is no longer worked out in the
     // page (trips × round trip × factor); every line's trips use its own payload and its CO2e is the server's co2_t
     && code.includes("trips+=pl>0?Math.ceil((rw.total||0)/pl):0;") && code.includes("const co2m=rw.co2_t||{};")
     && !code.includes("co2t+=t*round*em/1000")
     && code.includes("rows.length+' approved lines: '")
     && !code.includes("const row=(mtx.routes||[]).find(r=>(r.route_id||'').toString().trim().toLowerCase()===rl);"));
  // the zone popup speaks the legend's words, and its routing line is not red
  {
    const kl = (code.match(/const kindLabels = \{([^}]*)\}/) || ["", ""])[1];
    const popup = {}; kl.replace(/(\w+): '([^']*)'/g, (_, k, v) => { popup[k] = v; return ""; });
    const legend = {}; html.replace(/data-kind="(\w+)"><label><input[^>]*>\s*([^<]+)<\/label>/g, (_, k, v) => { legend[k] = v.trim(); return ""; });
    const keys = ["closure", "works", "weight_limit", "haul_road", "other"];
    ok("⭐ the zone popup's kind names are the legend's (the popup said 'Zone' where the legend says 'Advisory')",
       keys.every(k => popup[k] && popup[k] === legend[k]), JSON.stringify({ popup, legend }));
    ok("...and 'Routing avoids this area' is ink, not the selection red (red is kept for a clash or a cap breach)",
       code.includes("(p.affects_routing === true || p.affects_routing === 'true' ? '#1F2024' : '#6b7280')")
       && !code.includes("p.affects_routing === 'true' ? CONFIG.COLORS.selection"));
  }
  // the matrix fetch in flight is shared
  ok("ensureTimelineMatrix shares the fetch in flight (TL.matrixPending), cleared when it settles",
     /if\(TL\.matrixPending\) return TL\.matrixPending;\s*TL\.matrixPending = loadTimelineMatrix\(\)\.finally\(\(\)=>\{ TL\.matrixPending = null; \}\);/.test(code));
  ok("F3: openTimeline records the month Play started on once it has moved off an empty month",
     /setTimelineMonth\(TL\.month\);\s*if\(TL\.playing && TL\.ticked === null\) TL\.startedOn = TL\.month;/.test(code));

  const flush = () => new Promise(r => setTimeout(r, 0));
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const monthLabel = i => names[(i - 1) % 12] + ' ' + (2026 + Math.floor((i - 1) / 12));
  const mkEl = id => ({ id, innerText: "", innerHTML: "", textContent: "", hidden: false, title: "", style: {},
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); }, toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); } },
    getBoundingClientRect() { return { top: 0, bottom: 72, left: 0, right: 1000, width: 1000, height: 72 }; },
    setAttribute() {}, querySelector() { return null; } });
  const mkDoc = () => { const els = {}; return { els, getElementById: id => els[id] || (els[id] = mkEl(id)), querySelector: () => null,
    body: { classList: { contains: () => false, toggle() {} }, style: { setProperty() {}, removeProperty() {} } }, addEventListener() {} }; };

  // ---- (1) F1: the figures bar during Play ----------------------------------------------------------------------------
  {
    const a = src.indexOf("    function kpiMonthsOnScreen() {"), b = src.indexOf("    function applyFilters() {");
    ok("F1 sandbox: the figures-bar slice (kpiMonthsOnScreen … calculateKPIs) is found", a > 0 && b > a);
    if (a > 0 && b > a) {
      const document = mkDoc();
      const TL = { on: true, month: 10 };
      const KPI = { cache: {}, pending: {}, onScreen: null, seq: 0, by: 'discipline' };
      const deferred = {};
      const fetch = url => { const m = Number(/month=(\d+)/.exec(url)[1]);
        return new Promise(res => { deferred[m] = p => res({ ok: true, json: () => p }); }); };
      const a1_data = { features: [{ geometry: { type: "LineString" }, properties: { route_id: "R1", type: "Inbound Highway", origin: "Q", dest: "C", ipt: "IPT1" } }] };
      const pay = (m, loads) => ({ month: m, working_days: 20, payload_fallback_vehicle: "x", co2_to_date: [],
        lines: [{ route_id: "R1", vehicle_loads: loads, qty_unit: loads, qty_t: loads * 20, trips_per_vehicle_day: 4, discipline: "Earthworks", co2_t: 2 }] });
      let api = null, err = "", moving = null;
      try {
        api = new Function("document", "window", "TL", "KPI", "CONFIG", "fetch", "a1_data", "routePassesFilters", "monthLabel", "teamText", "TEAM",
          "renderKpiSwitch", "showMoving", "positionWarnStack", "selectRoute",
          src.slice(a, b) + "\nreturn { calculateKPIs, kpiFetchMonth };")(
          document, { WS_NAMES: {} }, TL, KPI, { FORECAST_UNIT: "vehicles", API_BASE: "" }, fetch, a1_data, () => true, monthLabel, x => x, "Team",
          () => {}, on => { moving = !!on; }, () => {}, () => {});
      } catch (e) { err = e.message; }
      ok("F1 sandbox: the figures bar runs against a fake DOM", !!api, err);
      if (api) {
        const el = id => document.getElementById(id);
        KPI.cache[10] = pay(10, 400);
        api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
        ok("⭐ F1: a month already in the cache renders in the same tick (title and figures), not a promise later",
           el("kpi-title").innerHTML.includes("Oct 2026") && el("kpi-trips").innerText === "20", el("kpi-title").innerHTML + " / " + el("kpi-trips").innerText);
        TL.month = 11; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
        ok("⭐ F1: a month still loading says so at once — '<Month> · loading figures' — and the previous month's figures are cleared",
           el("kpi-title").innerText === "Nov 2026 · loading figures" && el("kpi-trips").innerText === "—", el("kpi-title").innerText);
        // 12 Oct second fix pass (the sceptic): the rest of the bar named October under "Nov 2026 · loading figures"
        { const oct = (TL.month = 10, api.calculateKPIs("ALL", "ALL", "ALL", "ALL"),
                       { chips: el("kpi-breakdown").innerHTML, busy: el("kpi-busiest").innerHTML, moving, tip: el("kpi-title").title });
          ok("F1 sandbox: October renders its chips, its busiest routes, 'What's moving' and the method tooltip (so the next pin means something)",
             oct.chips.includes("Earthworks") && oct.busy.includes("busy-row") && oct.moving === true && oct.tip.includes("Approved forecast, Oct 2026")
             && el("kpi-moving-title").innerText === "What’s moving in Oct 2026");
          TL.month = 11; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
          ok("⭐ F1: while Nov loads nothing of October is left in the bar — no chips, no busiest routes, 'What's moving' hidden, labels and note say Nov or loading, no Oct tooltip",
             el("kpi-breakdown").innerHTML === "" && el("kpi-busiest").innerHTML === "" && el("kpi-switch").innerHTML === "" && moving === false
             && el("kpi-routes-label").innerText === "Routes in Nov 2026" && el("kpi-vehicles-label").innerText === "Vehicles needed"
             && el("kpi-note").innerText === "Loading the figures for Nov 2026." && el("kpi-title").title === "",
             JSON.stringify({ b: el("kpi-breakdown").innerHTML.slice(0, 60), moving, note: el("kpi-note").innerText, tip: el("kpi-title").title.slice(0, 40) })); }
        // 12 Oct 2026 (the base merge, Track B's merge-time items): a failed carbon read and a line with no stored road route
        { const p20 = Object.assign(pay(20, 400), { co2_error: "The carbon figures could not be read (OperationalError)." });
          p20.lines[0].co2_t = null; KPI.cache[20] = p20;
          TL.month = 20; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
          ok("⭐ base merge: month-kpis' co2_error puts a dash in both carbon cards and 'carbon could not be read' in their labels, never '0.0 t' or '(excl. N …)'",
             el("kpi-co2-day").innerText === "—" && el("kpi-co2-total").innerText === "—"
             && el("kpi-co2-day-label").innerText === "CO\u2082e a day (carbon could not be read)"
             && el("kpi-co2-total-label").innerText === "CO\u2082e to date (carbon could not be read)" && el("kpi-trips").innerText === "20",
             JSON.stringify([el("kpi-co2-day").innerText, el("kpi-co2-day-label").innerText, el("kpi-co2-total-label").innerText]));
          const p21 = pay(21, 400);
          p21.lines.push({ route_id: "R1", vehicle_loads: 40, qty_unit: 40, qty_t: 800, trips_per_vehicle_day: 0, discipline: "Drainage", co2_t: null });
          p21.co2_to_date_unbaked_lines = 3; KPI.cache[21] = p21;
          TL.month = 21; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
          ok("⭐ base merge: a line with no stored road route is named in those words on the bar (vehicles, CO2e a day, CO2e to date), never 'unbaked'",
             el("kpi-vehicles-label").innerText === "Vehicles needed (1 line with no stored road route)"
             && el("kpi-co2-day-label").innerText === "CO\u2082e a day (excl. 1 line with no stored road route)"
             && el("kpi-co2-total-label").innerText === "CO\u2082e to date (excl. 3 lines with no stored road route)"
             && el("kpi-co2-day").innerText !== "—" && !/baked/.test(el("kpi-note").innerText + el("kpi-vehicles-label").innerText),
             JSON.stringify([el("kpi-vehicles-label").innerText, el("kpi-co2-day-label").innerText, el("kpi-co2-total-label").innerText]));
          const p22 = pay(22, 400); p22.lines[0].trips_per_vehicle_day = 0; KPI.cache[22] = p22;
          TL.month = 22; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
          ok("...and a month whose every line lacks a stored road route reads 'no stored route' for vehicles, never 'not baked' or 0",
             el("kpi-vehicles").innerText === "no stored route", el("kpi-vehicles").innerText); }
        TL.month = 12; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
        ASYNC_PINS.push((async () => {
          deferred[11](pay(11, 200)); await flush(); await flush();
          ok("F1: a fetch that lands after the playhead moved on does not overwrite the month on screen",
             el("kpi-title").innerText === "Dec 2026 · loading figures" && KPI.cache[11] && el("kpi-trips").innerText === "—");
          deferred[12](pay(12, 600)); await flush(); await flush();
          ok("⭐ F1: the fetch for the month on screen renders it when it lands", el("kpi-title").innerHTML.includes("Dec 2026") && el("kpi-trips").innerText === "30",
             el("kpi-title").innerHTML + " / " + el("kpi-trips").innerText);
          // the second loop: every month is cached now, so every tick renders in the same tick
          TL.month = 11; api.calculateKPIs("ALL", "ALL", "ALL", "ALL");
          ok("F1: on the next loop a month fetched earlier renders at once", el("kpi-title").innerHTML.includes("Nov 2026") && el("kpi-trips").innerText === "10");
          // a filter change on the same month: the older call's late fetch cannot paint the old filter over the new one
          TL.month = 13; api.calculateKPIs("ALL", "ALL", "ALL", "ALL"); api.calculateKPIs("Q", "ALL", "ALL", "ALL");
          const keyNow = KPI.onScreen; deferred[13](pay(13, 400)); await flush(); await flush();
          ok("F1: two calls for one month and different filters: only the one on screen renders", keyNow.endsWith("|Q|ALL|ALL|ALL") && el("kpi-title").innerHTML.includes("Jan 2027"));
        })());
      }
    }
  }

  // ---- (2) the conditions: the whole warn block against plain data --------------------------------------------------
  {
    const a = src.indexOf("    const WARN = { restr: null"), b = src.indexOf("    (function initAnalysis(){");
    ok("warn sandbox: the warn block (const WARN … initAnalysis) is found", a > 0 && b > a);
    if (a > 0 && b > a) {
      const document = mkDoc();
      const TL = { on: true, month: 10, playing: false, ticked: null, clashPaused: false, startedOn: null, matrix: {} };
      const rec = { hits: [], caps: [], select: [], fit: 0, stops: [], announced: [] };
      const feat = (rid, extra) => ({ geometry: { type: "LineString" }, properties: Object.assign({ route_id: rid, type: "Inbound Highway", is_forecast: true }, extra || {}) });
      const a1_data = { features: [feat("R2", { max_vehicles_per_day: 20 }), feat("R5")] };
      const kp = { working_days: 20, lines: [{ route_id: "R2", vehicle_loads: 640, vehicle_type: "Artic Tipper (44t)" }, { route_id: "R5", vehicle_loads: 100, vehicle_type: "Artic Tipper (44t)" }] };
      const monthSpan = i => { const y = 2026 + Math.floor((i - 1) / 12), m = ((i - 1) % 12) + 1, last = new Date(Date.UTC(y, m, 0)).getUTCDate(); return [y * 10000 + m * 100 + 1, y * 10000 + m * 100 + last]; };
      const dnum = (s, f) => (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) ? f : parseInt(s.replace(/-/g, ""), 10);
      const RESTR = { data: { features: [{ properties: { event_number: "E1" }, geometry: { coordinates: [[0, 0], [1, 1]] } }] } };
      const map = { getSource: () => ({}), getLayer: () => true, addLayer() {}, setFilter() {}, fitBounds() { rec.fit++; }, jumpTo() {}, flyTo() {}, getZoom: () => 10 };
      let api = null, err = "";
      // 12 Oct second fix pass: the month's KPI fetch is a delegate (a pin can hold it pending, as a cold Play does) and the
      // page's KPI cache is passed in (the conditions read it so a cached month builds every row at once)
      const KPI = { cache: {} }; let kpiCalls = 0, kpiFetch = () => Promise.resolve(kp);
      try {
        api = new Function("document", "window", "ResizeObserver", "setTimeout", "CONFIG", "fetch", "a1_data", "routePassesFilters", "TL", "map", "RESTR",
          "coordsBounds", "selectRoute", "reducedMotion", "monthSpan", "dnum", "stopTimeline", "announceTimeline", "monthLabel", "kpiFetchMonth",
          "FORECAST_WORKING_DAYS", "META", "setRestrictionHits", "setCapBadges", "KPI",
          src.slice(a, b) + "\nreturn { WARN, renderTimelineWarnings, dismissWarning, showRestrictionHit, renderConditionsPill, capSentence, pileSentence, pileLastRecorded, splitHitRowId };")(
          document, { innerWidth: 1280, innerHeight: 800, addEventListener() {} }, function () { this.observe = () => {}; }, () => {},
          { API_BASE: "", MONTH_COUNT: 60, START_YEAR: 2026 }, () => { throw new Error("fetch must not be called"); }, a1_data, () => true, TL, map, RESTR,
          () => [0, 0, 1, 1], rid => rec.select.push(rid), () => false, monthSpan, dnum,
          reason => { rec.stops.push(reason); TL.playing = false; }, t => rec.announced.push(t), monthLabel, m => { kpiCalls++; return kpiFetch(m); },
          22, { seasonal: [] }, evs => rec.hits.push(evs.slice()), ids => rec.caps.push(ids.slice()), KPI);
      } catch (e) { err = e.message; }
      ok("warn sandbox: the warn block runs against plain data", !!api, err);
      if (api) {
        const W = api.WARN, box = () => document.getElementById("tl-warnings").innerHTML, pill = () => document.getElementById("kpi-conditions").innerHTML;
        const hit = { event_number: "E1", from: "2026-10-16T00:00:00", to: "2026-10-17T23:59:00", label: "Planned road closures", what: "A46 closure", severity: "hit" };
        W.restr = { R2: { hits: [hit] }, R5: { hits: [hit] } };
        W.piles = [{ location_id: "L1", name: "Langton stockpile", capacity_qty: 40000, unit: "t",
                     months: { "9": { balance_end: 30000, over: false }, "10": { balance_end: 40510, over: true }, "11": { balance_end: 40510, over: true }, "12": { balance_end: 40510, over: true } } }];
        // the pure helpers
        ok("⭐ the cap sentence names its unit and the flag: 'R016: 32 two-way movements a day against a planning flag of 20'",
           api.capSentence("R016", 32.2, 20) === "R016: 32 two-way movements a day against a planning flag of 20");
        ok("...and keeps a decimal when the round would land on the flag (20.3 over 20 never reads '20 … of 20')",
           api.capSentence("R1", 20.3, 20) === "R1: 20.3 two-way movements a day against a planning flag of 20");
        // 12 Oct second fix pass (the sceptic): 441 loads / 22 days = 20.045 printed "20.0 … against a planning flag of 20"
        ok("⭐ ...nor '20.0 … of 20': a figure just over the flag takes the decimals it needs (20.045 → 20.05, 20.04 → 20.04)",
           api.capSentence("R1", 441 / 22, 20) === "R1: 20.05 two-way movements a day against a planning flag of 20"
           && api.capSentence("R1", 20.04, 20) === "R1: 20.04 two-way movements a day against a planning flag of 20",
           api.capSentence("R1", 441 / 22, 20));
        ok("...and a figure too close to show reads 'just over 20', never '20.000'",
           api.capSentence("R1", 20.0001, 20) === "R1: just over 20 two-way movements a day against a planning flag of 20");
        ok("the last month anything was recorded against a pile is the last month its balance moved (Oct here)", api.pileLastRecorded(W.piles[0]) === 10);
        ok("a row id splits into its event and its route; an old bare event id still works",
           JSON.stringify(api.splitHitRowId("00525419-001|R002")) === '{"ev":"00525419-001","rid":"R002"}' && api.splitHitRowId("E9").rid === null);
        api.renderConditionsPill([{ src: "cap", lvl: "warn" }, { src: "cap", lvl: "warn" }]);
        ok("⭐ the pill's plural: '2 routes over planning flags' (it printed '2 over a planning flag')", pill().includes("2 routes over planning flags"), pill());
        ok("browser check 12 Oct: each pill item is one unit, dot and words together, so the wrapping desktop pill never parts them",
           (pill().match(/<span class="cond-part"><span class="cond-dot /g) || []).length === 1, pill());
        ASYNC_PINS.push((async () => {
          api.renderTimelineWarnings(10); await flush(); await flush();
          ok("⭐ one closure on two routes: two rows, each carrying its OWN route (E1|R2, E1|R5)",
             box().includes("showCondition('h','E1|R2')") && box().includes("showCondition('h','E1|R5')"), box().slice(0, 300));
          ok("...the event maps to both routes and is highlighted once", JSON.stringify(W.hitRoute.E1) === '["R2","R5"]' && JSON.stringify(rec.hits[rec.hits.length - 1]) === '["E1"]');
          ok("⭐ the planning-flag row: one noun, the unit in the sentence", box().includes("<b>Over a planning flag</b>")
             && box().includes("R2: 32 two-way movements a day against a planning flag of 20") && !box().includes("planning cap"));
          ok("...and the pill counts it as '1 route over a planning flag'", pill().includes("1 route over a planning flag"), pill());
          // NARROWED 12 Oct 2026 (the base merge; Track B's bulletin wording): "has a capacity of N t;", not "holds N t."
          ok("the stockpile sentence in a month with a record: '… has a capacity of 40,000 t; 40,510 t recorded in it at the end of Oct 2026.'",
             box().includes(`Langton stockpile has a capacity of ${(40000).toLocaleString()} t; ${(40510).toLocaleString()} t recorded in it at the end of Oct 2026.`)   // the page formats with the reader's locale
             && !box().includes("stockpile holds"), box());
          api.showRestrictionHit("E1|R5"); api.showRestrictionHit("E1|R2"); api.showRestrictionHit("E1");
          ok("⭐ Show on map on each row selects THAT row's route (R5, then R2); a bare event id falls back to its first route",
             rec.select.join(",") === "R5,R2,R2" && rec.fit === 3, rec.select.join(","));
          api.dismissWarning("r|R5|10"); await flush(); await flush();
          ok("⭐ dismissing one route's row keeps the closure highlighted while another route's row is live",
             JSON.stringify(rec.hits[rec.hits.length - 1]) === '["E1"]');
          api.dismissWarning("r|R2|10"); await flush(); await flush();
          ok("...and dismissing the last one clears it", JSON.stringify(rec.hits[rec.hits.length - 1]) === "[]");
          TL.month = 11; api.renderTimelineWarnings(11); await flush(); await flush();
          ok("⭐ D23: a month after the last record carries the balance forward and says so",
             box().includes(`Langton stockpile has a capacity of ${(40000).toLocaleString()} t; ${(40510).toLocaleString()} t recorded at the end of Oct 2026; nothing recorded since.`)   // NARROWED 12 Oct (base merge): "has a capacity of"
             && !box().includes("stockpile holds"), box());
          ok("...and the October closure is not listed in November", !box().includes("E1|"));
          // F3: Play pressed on a red month counts as the loop's pause even when its conditions land after the first tick
          TL.playing = true; TL.startedOn = 10; TL.month = 11; TL.clashPaused = false; TL.ticked = 11;
          api.renderTimelineWarnings(10); await flush(); await flush();
          ok("⭐ F3: Play pressed on a red month (Oct) counts as this loop's pause even when Oct's conditions land after the tick",
             TL.clashPaused === true && rec.stops.length === 0);
          TL.startedOn = null; TL.clashPaused = false; api.renderTimelineWarnings(10); await flush(); await flush();
          ok("...and only for the month it was pressed on, before the wrap", TL.clashPaused === false);
          // the clash pause writes the live region once, with the reason
          TL.month = 10; TL.ticked = 10; TL.playing = true; TL.clashPaused = false; rec.announced.length = 0;
          api.renderTimelineWarnings(10); await flush(); await flush();
          ok("⭐ a clash pause stops ONCE and passes its reason to the one announcement (no second write)",
             rec.stops.length === 1 && rec.stops[0] === "Oct 2026 · playback paused: 1 over capacity" && rec.announced.length === 0 && TL.clashPaused === true,
             JSON.stringify(rec));
          // 12 Oct second fix pass (the sceptic): a cold tick — the month's KPI fetch still in flight — must not hold up
          // the over-capacity row, the pause or the pill; the planning-flag row joins when the figures land
          { const pend = {}; kpiFetch = m => new Promise(res => { pend[m] = res; });
            rec.stops.length = 0; TL.month = 11; TL.ticked = 11; TL.playing = true; TL.clashPaused = false; TL.startedOn = 10;
            api.renderTimelineWarnings(11); await flush(); await flush();
            ok("⭐ a red month whose KPI figures are still loading pauses Play on the tick that reaches it (it waited on the fetch and missed the first loop)",
               rec.stops.length === 1 && rec.stops[0] === "Nov 2026 · playback paused: 1 over capacity" && TL.clashPaused === true, JSON.stringify(rec.stops));
            ok("...the pill already describes Nov (1 over capacity) and carries no planning-flag count before the figures land",
               pill().includes("1 over capacity") && !pill().includes("planning flag") && W.countsMonth === 11, pill());
            ok("...and the panel says Nov with the stockpile row", box().includes("Conditions in Nov 2026") && box().includes("Over capacity") && !box().includes("Over a planning flag"));
            pend[11] && pend[11](kp); await flush(); await flush();
            ok("⭐ when Nov's figures land the planning-flag row and its pill count join, without a second stop",
               box().includes("Over a planning flag") && pill().includes("1 route over a planning flag") && rec.stops.length === 1, pill());
            // a late fetch for a month the playhead has left paints nothing
            TL.month = 11; TL.ticked = 11; TL.playing = false; api.renderTimelineWarnings(11); await flush(); await flush();
            const before = box(); TL.month = 12; pend[11] && pend[11](kp); await flush(); await flush();
            ok("...a month the playhead has left is not painted when its figures land", box() === before);
            // a month already in the page's KPI cache builds every row at once and fetches nothing
            KPI.cache[12] = kp; kpiCalls = 0; api.renderTimelineWarnings(12); await flush(); await flush();
            ok("⭐ a month already in the KPI cache builds its planning-flag row at once and does not fetch",
               kpiCalls === 0 && box().includes("Conditions in Dec 2026") && box().includes("Over a planning flag"), String(kpiCalls));
            kpiFetch = () => Promise.resolve(kp); }
        })());
      }
    }
  }
}

// 12 Oct 2026 (§2.2b, D27): movements and carbon per council — the "By council" group, its ramp, its card
{
  const start = code.indexOf("    const AREAS = { cache: {}");
  // `code` is comment-stripped, so the block ends at its last statement, not at the next banner comment
  const end = code.indexOf("\n    }\n", code.indexOf("map.on('mouseleave', 'area-fill'", start)) + 7;
  const blk = start >= 0 && end > start ? code.slice(start, end) : "";
  ok("§2.2b: the council block is in the page (AREAS, the ramp, the layers, the card)", blk.length > 2000
     && /function areaFillExpr\(mode\)/.test(blk) && /function areaCardHTML\(a, payload, when\)/.test(blk)
     && /function ensureAreaLayers\(\)/.test(blk) && /function setupAreaCard\(\)/.test(blk));
  // its OWN group and boxes, outside "Disruption zones", off by default
  const gStart = html.indexOf('<div class="control-group" id="council-group" hidden>');
  const layersEnd = html.indexOf("</details>", html.indexOf('<details class="layers-box" id="layers-box">'));
  const zonesBox = html.indexOf('id="layer-zones"'), zoneKinds = html.indexOf('<div id="zone-kinds"');
  const group = gStart >= 0 ? html.slice(gStart, html.indexOf("</div>\n\n", gStart)) : "";
  ok("⭐ §2.2b: a 'By council' group of its own, AFTER the layers box closes — not inside 'Disruption zones' or its kinds",
     gStart > layersEnd && layersEnd > zonesBox && zonesBox > 0 && zoneKinds > 0 && gStart > zoneKinds
     && /<h3>By council<\/h3>/.test(group), String(gStart) + " " + String(layersEnd));
  ok("⭐ §2.2b: its own checkboxes, districts and county, each with its own handler — and both OFF by default",
     /<input type="checkbox" id="layer-areas-district" onchange="toggleAreaTier\('district', this\.checked\)">/.test(group)
     && /<input type="checkbox" id="layer-areas-county" onchange="toggleAreaTier\('county', this\.checked\)">/.test(group)
     && !/id="layer-areas-(district|county)"[^>]*\schecked[\s>]/.test(group));
  ok("§2.2b: the group is hidden until the tenant has areas (a map with none is correct, not broken)",
     /if \(group\) group\.hidden = !has;/.test(blk));
  ok("§2.2b: the zone toggle does not drive the council layers, nor the council toggle the zones",
     !/AREA_LAYERS|area-fill/.test(code.slice(code.indexOf("    function toggleZones(visible) {"), code.indexOf("    function toggleZoneKind(")))
     && !/ZONE_LAYERS|zone-fill/.test(code.slice(code.indexOf("    function toggleAreaTier("), code.indexOf("    function toggleArea(id, on)"))));
  ok("§2.2b: one box per district (each its own layer: the fill, outline and label go, the routes stay)",
     /onchange="toggleArea\(\\'' \+ esc\(a\.area_id\)/.test(blk) && /\['!', \['get', 'off'\]\]/.test(blk)
     && /if \(on\) AREAS\.off\.delete\(id\); else AREAS\.off\.add\(id\);/.test(blk));
  // the ramp: ONE hue, the plan blue (D26), fixed stops, ascending
  const rampM = blk.match(/const AREA_RAMP = \[([^\]]+)\]/);
  const ramp = rampM ? rampM[1].match(/#[0-9A-Fa-f]{6}/g) : [];
  const hsl = h => { const r = parseInt(h.slice(1, 3), 16) / 255, g = parseInt(h.slice(3, 5), 16) / 255, b = parseInt(h.slice(5, 7), 16) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
    let hh = 0; if (d) { hh = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; hh *= 60; if (hh < 0) hh += 360; }
    return [hh, l]; };
  const H = ramp.map(hsl);
  ok("⭐ §2.2b (D26): the fill ramp is ONE hue — four steps of the plan blue (#4A72C9 among them), light to dark",
     ramp.length === 4 && ramp.map(x => x.toUpperCase()).includes("#4A72C9")
     && H.every(([h]) => Math.abs(h - 221) < 3) && H.every(([, l], i) => i === 0 || l < H[i - 1][1]), JSON.stringify(ramp));
  // REVERSED 12 Oct 2026 (night, the user: "movements in blue hue and carbon in orange hue"): the council carbon ramp is
  // orange, knowingly, for this layer only; the movements stay blue; the brand orange and the amber of the return leg
  // and of closures are still not used as a council colour
  const rampC = ((blk.match(/const AREA_RAMP_CARBON = \[([^\]]+)\]/) || [])[1] || "").match(/#[0-9A-Fa-f]{6}/g) || [];
  const HC = rampC.map(hsl);
  ok("⭐ council carbon: ONE orange hue (hue 18-30), four steps light to dark, the light end at least 2:1 on white; movements keep the blue",
     rampC.length === 4 && HC.every(([h]) => h >= 18 && h <= 30) && HC.every(([, l], i) => i === 0 || l < HC[i - 1][1])
     && (() => { const lum = h => { const c = [1, 3, 5].map(i => { const v = parseInt(h.slice(i, i + 2), 16) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
                 return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }; return 1.05 / (lum(rampC[0]) + 0.05) >= 2; })()
     && !/#FF8C14|#C97A2E|#E0770C|#D97706|#F59E0B/i.test(blk), JSON.stringify(rampC));
  const AREA_NONE = "#E7E5E4";
  const fillExpr = new Function("AREA_STOPS", "AREA_RAMP", "AREA_NONE", "AREA_RAMP_CARBON",
    (blk.match(/function areaFillExpr\(mode\) \{[\s\S]*?\n    \}/) || [""])[0] + "; return areaFillExpr;")(
    { movements: [50, 100, 200], carbon: [50, 100, 200] }, ramp, AREA_NONE, rampC);
  const fm = fillExpr("movements"), fc = fillExpr("carbon");
  ok("⭐ council carbon: the carbon fill steps through the orange ramp, the movements fill through the blue",
     JSON.stringify(fc.slice(4).filter((x, i) => i % 2 === 0)) === JSON.stringify(rampC)
     && JSON.stringify(fm.slice(4).filter((x, i) => i % 2 === 0)) === JSON.stringify(ramp));
  const stops = e => e.slice(3).filter((x, i) => i % 2 === 0);
  ok("⭐ §2.2b: a Mapbox step on FIXED literal stops in ascending order, the neutral below the first",
     fm[0] === "step" && JSON.stringify(fm[1]) === '["get","v"]' && fm[2] === AREA_NONE
     && JSON.stringify(stops(fm)) === "[0.01,50,100,200]" && JSON.stringify(stops(fc)) === "[0.01,50,100,200]"
     && JSON.stringify(fm.slice(4).filter((x, i) => i % 2 === 0)) === JSON.stringify(ramp), JSON.stringify(fm));
  ok("§2.2b: the stops are literals in the source, not worked out from the data (no max, no quantiles)",
     /const AREA_STOPS = \{ movements: \[50, 100, 200\], carbon: \[50, 100, 200\] \};/.test(blk)
     && !/Math\.max\(|quantile|percentile/.test(blk.slice(blk.indexOf("function areaFillExpr"), blk.indexOf("function areaFigureText"))));
  ok("§2.2b: the fill is drawn UNDER every layer of ours (routes, sites, zones), so the routes stay on top",
     /map\.addLayer\(\{ id: 'area-fill', type: 'fill'[\s\S]*?\}, before\);/.test(blk) && /const before = areaBeforeId\(\);/.test(blk)
     && /'routes-source'/.test(blk.slice(blk.indexOf("function areaBeforeId"), blk.indexOf("function ensureAreaLayers"))));
  ok("§2.2b: a fill, an outline and a label per district; the county a dashed outline of its own",
     /id: 'area-fill', type: 'fill'/.test(blk) && /id: 'area-outline', type: 'line'/.test(blk)
     && /id: 'area-label', type: 'symbol'/.test(blk) && /id: 'area-county-outline', type: 'line'/.test(blk)
     && /filter: \['==', \['get', 'tier'\], 'county'\]/.test(blk) && /'line-dasharray': \[3, 2\]/.test(blk));
  ok("§2.2b: the label is 14 px (the floor) with a white halo", /'text-field': \['get', 'label'\], 'text-size': 14,/.test(blk));
  ok("§2.2b: the colour-by switch has two modes, movements first (D27: movements first, carbon second)",
     /mode: 'movements'/.test(blk) && /\[\['movements', 'Two-way movements a day'\], \['carbon', 't CO(?:₂|\\u2082)e this month'\]\]/.test(blk)
     && /function setAreaMode\(mode\)/.test(blk));
  // the legend, as the page builds it
  const legend = new Function("AREA_STOPS", "AREA_RAMP", "AREA_NONE", "AREA_RAMP_CARBON",
    (blk.match(/function areaLegendHTML\(mode, when\) \{[\s\S]*?\n    \}/) || [""])[0] + "; return areaLegendHTML;")(
    { movements: [50, 100, 200], carbon: [50, 100, 200] }, ramp, AREA_NONE, rampC);
  const lgM = legend("movements", "Oct 2026"), lgC = legend("carbon", "Oct 2026");
  ok("⭐ §2.2b: the legend row per mode — movements titled for laden legs, five rows (four blues and the neutral)",
     lgM.includes("Two-way movements a day on roads a laden leg uses") && (lgM.match(/class="area-lg"/g) || []).length === 5
     && lgM.includes("under 50") && lgM.includes("200 and over") && lgM.includes("no approved laden route")
     && ramp.every(c => lgM.includes(c)), lgM);
  ok("⭐ §2.2b: ...and carbon titled with the month and the split, in t (never kg per tonne)",
     lgC.includes("t CO₂e in Oct 2026, split by the km inside each district") && lgC.includes("200 t and over")
     && lgC.includes("under 50 t") && !/\bkg\b|per tonne/.test(lgC) && rampC.every(c => lgC.includes(c)) && !ramp.some(c => lgC.includes(c)), lgC);
  // the attribution: the source carries the dataset's licence lines; the group prints them
  const seedTxt = fs.readFileSync(path.join(ROOT, "backend", "data", "areas_demo.geojson"), "utf8");
  const seed = JSON.parse(seedTxt);
  ok("⭐ §2.2b: the seed's two licence lines, word for word (ONS licence page)",
     JSON.stringify(seed.attribution) === JSON.stringify([
       "Source: Office for National Statistics licensed under the Open Government Licence v.3.0",
       "Contains OS data © Crown copyright and database right 2026"]), JSON.stringify(seed.attribution));
  ok("⭐ §2.2b: the map prints the lines the server sends: on the source's attribution (beside Mapbox's) and in the group",
     /attribution: \(AREAS\.data\.attribution \|\| \[\]\)\.join\(' (?:·|\\u00b7) '\)/.test(blk)
     && /if \(at\) at\.textContent = \(j\.attribution \|\| \[\]\)\.join\(' (?:·|\\u00b7) '\);/.test(blk)
     && /<div class="area-note" id="area-attribution"><\/div>/.test(html));
  ok("🔴 §2.2b: ...and never a hard-coded dataset's lines (another tenant's boundaries must not be credited to ONS)",
     !/Office for National Statistics|Crown copyright/.test(code));
  // the card, as the page builds it
  const card = new Function((blk.match(/function areaCardHTML\(a, payload, when\) \{[\s\S]*?\n    \}/) || [""])[0] + "; return areaCardHTML;")();
  const A = { area_id: "E07000131", name: "Harborough", tier: "district", tier_words: "local authority district",
              source: "ONS Local Authority Districts (May 2026) Boundaries UK BSC", highway_authority: "Leicestershire County Council",
              movements_per_day: 12.34, routes: ["R001", "R002"], return_only_routes: ["R009"], co2_t: 30.5, co2_t_per_day: 1.39,
              lorry_km: 12345.6, sites: ["Harborough Compound", "<b>x</b>"], sites_count: 2 };
  const P = { totals: { routes_with_volume: 18, co2_t: 482 }, carbon: { stamp: "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" } };
  const ch = card(A, P, "Oct 2026");
  ok("⭐ §2.2b: the per-council card: the name, the tier and the highway authority, movements with the rule, CO2e of the month's total",
     ch.includes("Harborough") && ch.includes("Local authority district") && ch.includes("highway authority: Leicestershire County Council")
     && ch.includes("Two-way movements a day") && ch.includes("<b>12.3</b>") && ch.includes("2 of the 18 routes with approved volume in Oct 2026 enter it laden")
     && ch.includes("1 more run back through it empty") && ch.includes("one load = one two-way movement")
     && ch.includes("30.5 t of 482 t") && ch.includes("split by the km inside") && ch.includes("Lorry-km in Oct 2026"), ch);
  ok("§2.2b: ...the planning-estimate stamp from the server, and every name escaped",
     ch.includes(P.carbon.stamp) && ch.includes("&lt;b>x&lt;/b>") && !ch.includes("<b>x</b>"));
  ok("§2.2b: ...a carbon the server could not give reads 'no figure', never 0 t",
     card(Object.assign({}, A, { co2_t: null }), P, "Oct 2026").includes("<b>no figure</b>")
     && !card(Object.assign({}, A, { co2_t: null }), P, "Oct 2026").includes("<b>0 t"));
  ok("🔴 §2.2b: no team id in the card or the block (no team is named here at all)",
     !/\bIPT ?[1-6]\b|\bipt\b/i.test(blk) && !/IPT/.test(ch));
  ok("§2.2b: the card's click yields to a route, site or zone on top (queryRenderedFeatures over our GeoJSON layers)",
     /if \(above\.length\) return;/.test(blk) && /map\.on\('click', 'area-fill'/.test(blk) && /let AREA_CARD_WIRED = false;/.test(blk));
  ok("§2.2b: every figure is the server's — no working-day count, no division by days in the page",
     !/working_days|\b22\b|\/ ?wd\b/.test(blk));
  // REVERSED 12 Oct 2026 (Track C review): the areas show the month Road load and Carbon show (mapModeMonth) — never the
  // first month of an averaged Show-forecast span, nor the calendar month beside a bar that shows something else
  ok("§2.2b: the areas follow the ONE month on screen (mapModeMonth, the rule Road load and Carbon use), else no figure",
     /function areasMonth\(\) \{\s*return \(typeof mapModeMonth === 'function'\) \? mapModeMonth\(\) : null;\s*\}/.test(blk)
     && !/forecastWindow\(\)\[0\]|currentMonthIndex\(\)/.test(blk)
     && /if\(typeof refreshAreas==='function'\) refreshAreas\(\);/.test(code) && /if \(typeof refreshAreas === 'function'\) refreshAreas\(\);/.test(code)
     && /if \(m !== areasMonth\(\)\) return;/.test(blk));
  ok("§2.2b: off means off — no fetch while both boxes are clear (after the one probe that shows the group)",
     /if \(AREAS\.probed && !areaTierOn\('district'\) && !areaTierOn\('county'\)\) return;/.test(blk));
  ok("§2.2b: a basemap switch re-adds the layers from the cached month (style.load)",
     /if \(AREAS\.data\) \{ AREAS\.drawn = ''; ensureAreaLayers\(\); renderAreas\(\); \} else refreshAreas\(\);/.test(code));
  // the county tier (the highway authority's figure, D27's county/UA toggle): its own figure, its card, its label
  ok("⭐ §2.2b: the group carries the mockup's two sub-heads and the county's own figure on a line under its box",
     /<div class="area-legend-title area-sub" id="area-mode-title">Colour the districts by<\/div>\s*<div class="kpi-switch area-mode" id="area-mode"><\/div>/.test(group)
     && /<div class="area-legend-title area-sub">Highway authority<\/div>\s*<div class="control-item"><label><input type="checkbox" id="layer-areas-county"[^\n]*<\/div>\s*<div class="area-county-fig" id="area-county-fig"><\/div>/.test(group)
     && /if \(cf\) cf\.textContent = counties\.length === 1 \? areaRowFigure\(counties\[0\]\.name \+ ' (?:·|\\u00b7) ' \+ areaFigureText\(counties\[0\], AREAS\.mode, ''\)\)/.test(blk));
  ok("§2.2b: the colour-by switch belongs to the districts — hidden with their box, and the hidden attribute beats .kpi-switch's flex",
     /if \(sw\) sw\.hidden = !areaTierOn\('district'\);/.test(blk) && /if \(swT\) swT\.hidden = !areaTierOn\('district'\);/.test(blk)
     && /#council-group \[hidden\]\{ display:none; \}/.test(html));
  ok("🔴 §2.2b: a figure beside a district wraps inside the panel (Chrome, 12 Oct: '16 routes' ran off its edge)",
     /\.area-fig\{[^}]*text-align:right;[^}]*\}/.test(html) && !/\.area-fig\{[^}]*white-space:nowrap/.test(html)
     && /#area-district-rows \.control-item label\{ width:auto; flex:1 1 auto; min-width:0; \}/.test(html));
  {
    const rf = new Function((blk.match(/function areaRowFigure\(t\) \{[^\n]*\}/) || ["function areaRowFigure(){}"])[0] + "; return areaRowFigure;")();
    ok("§2.2b: ...and breaks only at its ' · ', never inside a figure ('130 t CO2e' stays whole)",
       rf("257 a day · 16 routes") === "257 a day · 16 routes" && rf("130 t CO₂e") === "130 t CO₂e"
       && /esc\(areaRowFigure\(areaFigureText\(a, AREAS\.mode, ''\)\)\)/.test(blk));
  }
  ok("⭐ §2.2b: ONE label per area, on the server's label point (a polygon label repeats on every tile: Harborough twice in Chrome)",
     /if \(Array\.isArray\(a\.label_point\)\) feats\.push\(\{ type: 'Feature', geometry: \{ type: 'Point', coordinates: a\.label_point \}, properties: props \}\);/.test(blk)
     && /const labelPt = \['==', \['geometry-type'\], 'Point'\];/.test(blk)
     && /id: 'area-label', type: 'symbol', source: 'areas-source', filter: district\.concat\(\[labelPt\]\),/.test(blk)
     && /filter: \['all', \['==', \['get', 'tier'\], 'county'\], labelPt\],/.test(blk));
  {
    const af = new Function("areaFigureText", (blk.match(/function areaFeatures\(payload, mode, off, when\) \{[\s\S]*?\n    \}/) || [""])[0] + "; return areaFeatures;")(() => "x");
    const fc = af({ areas: [{ area_id: "A", name: "Alpha", tier: "district", movements_per_day: 3, geometry: { type: "Polygon", coordinates: [] }, label_point: [-0.9, 52.5] },
                            { area_id: "B", name: "Beta", tier: "district", movements_per_day: 0, geometry: { type: "Polygon", coordinates: [] } }] }, "movements", new Set(), "");
    ok("§2.2b: ...a polygon per area plus one point where the server gave one (none invented where it did not)",
       fc.features.length === 3 && fc.features.filter(f => f.geometry.type === "Point").length === 1
       && fc.features[1].geometry.coordinates[0] === -0.9 && fc.features[1].properties.label === "ALPHA\nx");
  }
  ok("§2.2b: the card leads with the figure the map is coloured by (carbon mode: CO2e first, as mockup 4's frame B)",
     /const carbonFirst = typeof AREAS !== 'undefined' && AREAS\.mode === 'carbon';/.test(blk) && /h \+= carbonFirst \? co \+ mv : mv \+ co;/.test(blk));
  ok("⭐ §2.2b: the county answers a click with its own card — a fill with no paint under it, on while its box is",
     /const AREA_COUNTY_LAYERS = \['area-county-outline', 'area-county-fill', 'area-county-label'\];/.test(blk)
     && /id: 'area-county-fill', type: 'fill', source: 'areas-source',\s*filter: \['==', \['get', 'tier'\], 'county'\],\s*layout: \{ visibility: cVis \}, paint: \{ 'fill-color': AREA_INK, 'fill-opacity': 0 \} \}, before\);/.test(blk)
     && /map\.on\('click', 'area-county-fill', \(e\) => \{[\s\S]*?setHTML\(areaCardHTML\(a, AREAS\.data, when\)\)/.test(blk));
  ok("🔴 §2.2b: ...but never over a district: a district (or a route, site or zone) under the click answers instead",
     /f\.layer\.id === 'area-fill' \|\| \(!String\(f\.layer\.id\)\.startsWith\('area-'\)[\s\S]*?if \(above\.length\) return;/.test(
       blk.slice(blk.indexOf("map.on('click', 'area-county-fill'"))));
  {
    const visFn = new Function("areaTierOn", "AREA_LAYERS", "AREA_COUNTY_LAYERS",
      (blk.match(/function areaVisibility\(\) \{[\s\S]*?\n    \}/) || [""])[0] + "; return areaVisibility;");
    const AL = ["area-fill", "area-outline", "area-label"], CL = ["area-county-outline", "area-county-fill", "area-county-label"];
    const vis = (d, c) => visFn(t => (t === "district" ? d : c), AL, CL)();
    const both = vis(true, true), cOnly = vis(false, true), dOnly = vis(true, false), none = vis(false, false);
    ok("⭐ §2.2b: which layer shows, from the two boxes: the county's label only while the districts are off",
       both["area-fill"] === "visible" && both["area-county-outline"] === "visible" && both["area-county-label"] === "none"
       && cOnly["area-fill"] === "none" && cOnly["area-county-fill"] === "visible" && cOnly["area-county-label"] === "visible"
       && dOnly["area-county-fill"] === "none" && dOnly["area-label"] === "visible"
       && Object.values(none).every(v => v === "none") && Object.keys(none).length === 6, JSON.stringify([both, cOnly]));
    ok("§2.2b: both boxes go through the one rule (toggleAreaTier and ensureAreaLayers read areaVisibility)",
       /const vis = areaVisibility\(\);\s*AREA_LAYERS\.concat\(AREA_COUNTY_LAYERS\)\.forEach\(l => toggleLayer\(l, vis\[l\] === 'visible'\)\);/.test(blk)
       && /const vis = areaVisibility\(\), dVis = vis\['area-fill'\], cVis = vis\['area-county-outline'\];/.test(blk)
       && /visibility: vis\['area-county-label'\]/.test(blk));
  }
  ok("⭐ §2.2b: the card counts the sites as the mockup does — '8 of 13' from the server's total",
     card(Object.assign({}, A, { sites_count: 8 }), { totals: { routes_with_volume: 18, co2_t: 482, sites: 13 } }, "Oct 2026").includes("<b>8 of 13</b>")
     && card(Object.assign({}, A, { sites_count: 8 }), { totals: { routes_with_volume: 18 } }, "Oct 2026").includes("<b>8</b>"));
  ok("§2.2b: an unticked district gets a legend row of its own ('layer off'), only while one is off",
     /\+ \(AREAS\.off\.size\s*\? '<div class="area-lg"><span class="area-sw" style="background:transparent; border:1px dashed ' \+ AREA_INK \+ '"><\/span>layer off \(unticked above\)<\/div>' : ''\)/.test(blk));
  // US spellings as words a person reads: Mapbox's own paint keys ('fill-color') and the page's class names
  // ('color-dot') are hyphenated identifiers, not wording, so a hyphen on either side is not a match
  ok("§2.2b: UK wording and none of the banned words in the block or the group",
     !/\b(truck|real[- ]time|live tracking|telematics|optimi[sz]e|predict|secure)\b/i.test(blk + group)
     && !/(?<!-)\b(color|center)\b(?!-)/i.test(blk + group));
  // the 14 px floor on every new rule
  const css = html.slice(html.indexOf("/* §2.2b / D27 (12 Oct 2026)"), html.indexOf(String.fromCharCode(10), html.indexOf(".area-cf{")));
  const sizes = (css.match(/font-size:(\d+(?:\.\d+)?)px/g) || []).map(s => parseFloat(s.replace(/[^\d.]/g, "")));
  ok("⭐ §2.2b: the 14 px floor on the new text (every font-size in the group's and the card's rules is 14 px or more)",
     sizes.length >= 8 && sizes.every(v => v >= 14), JSON.stringify(sizes));
  ok("🔴 §2.2b: ...including the group's heading and its two boxes, which the shared h3 (13 px) and .control-item (13.5 px) rules set below it (Chrome, 12 Oct)",
     /#council-group h3, #council-group \.control-item\{ font-size:14px; \}/.test(css));
}

// 12 Oct second fix pass: source pins for the conditions' timing and the 14 px floor on the row sentence
{
  const rtw = code.slice(code.indexOf("    function renderTimelineWarnings(m) {"), code.indexOf("    function buildConditions("));
  ok("⭐ the conditions wait on the closures and stockpiles only, never on the month's KPI fetch (a cold tick missed the pause)",
     rtw.length > 0 && /Promise\.all\(\[warnRestrictions\(\), warnPiles\(\)\]\)\.then/.test(rtw)
     && !/Promise\.all\(\[warnRestrictions\(\), warnPiles\(\), kpiFetchMonth/.test(code)
     && /kpiFetchMonth\(month\)\.catch\(\(\) => null\)\.then\(kp => \{\s*if \(!kp \|\| TL\.month !== month \|\| !TL\.on\) return;/.test(rtw));
  ok("the condition row's sentence is 14 px (new text; the row is 13 px)", /\.tl-warn \.what\{ color:var\(--muted\); font-size:14px; \}/.test(html));
  ok("F3: only a wrap over more than one month forgets the month Play was pressed on",
     /if\(wrap && lo !== hi\) TL\.startedOn = null;/.test(code) && !/if\(wrap\) TL\.startedOn = null;/.test(code));
}

// ===== 12 Oct 2026 (C1) — ROAD LOAD AND CARBON on the public map (review §2.2d map half, mockup 1; §2.2a, mockup 5) =====
// Every pin below fails on the base (d9e5cb1): none of these names, ids, layers or words existed there.
{
  const blkA = src.indexOf("    // ===== 12 Oct 2026 — ROAD LOAD AND CARBON");
  const blkB = src.indexOf("    // ===== end of road load and carbon =====");
  ok("C1: the road-load and carbon block is one contiguous slice", blkA > 0 && blkB > blkA);
  const blk = blkA > 0 && blkB > blkA ? src.slice(blkA, blkB) : "";
  // the block without its comments, for the source pins
  const blkCode = blk.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n");

  // ---- the controls: two checkboxes, off by default, under Forecast traffic volume ----
  // NARROWED 12 Oct 2026 (the user, evening: "toggle between carbon and volume"): the two checkboxes are ONE radio group,
  // Heat map: Off · Volume · Carbon; "Off" ships checked; the ids are kept so a shared link still opens on the same mode
  ok("⭐ C1: a 'Heat map' radio group — Off (checked), Volume, Carbon — sits in the forecast box; Volume and Carbon OFF by default",
     code.includes('<div class="heat-group" role="radiogroup" aria-labelledby="heat-label">')
     && code.includes('<label class="fc-toggle fc-mode"><input type="radio" name="heat-mode" id="heat-off" onchange="toggleHeatOff()" checked> Off</label>')
     && code.includes('<label class="fc-toggle fc-mode"><input type="radio" name="heat-mode" id="toggle-road-load" onchange="toggleRoadLoad()"> Volume <span class="mode-sub">two-way movements a day</span></label>')
     && code.includes('<label class="fc-toggle fc-mode"><input type="radio" name="heat-mode" id="toggle-carbon" onchange="toggleCarbon()"> Carbon <span class="mode-sub">t CO₂e in the month, per route</span></label>')
     && !/type="checkbox" id="toggle-(road-load|carbon)"/.test(code) && !code.includes("> Road load</label>")
     && !/id="toggle-road-load"[^>]*checked/.test(code) && !/id="toggle-carbon"[^>]*checked/.test(code)
     && code.indexOf('id="toggle-road-load"') > code.indexOf('id="toggle-forecast"') && code.indexOf('id="toggle-carbon"') > code.indexOf('id="toggle-road-load"'));
  ok("heat map (12 Oct, evening): 'Off' re-draws without either mode and re-writes the shared link; the width legend's CSS is gone",
     code.includes("function toggleHeatOff(){\n        refreshMapModes();\n        if (typeof scheduleViewWrite === 'function') scheduleViewWrite();")
     && code.includes("if (off && off.checked !== !mode) off.checked = !mode;")
     && !html.includes(".ml-w{") && !code.includes("ml-w\"")
     && code.includes("const LINK_MODE_BOXES = ['toggle-road-load', 'toggle-carbon', 'toggle-forecast'];"));
  ok("C1: each mode has a legend box, hidden until its checkbox is ticked",
     code.includes('<div class="mode-legend" id="road-load-legend" hidden></div>') && code.includes('<div class="mode-legend" id="carbon-legend" hidden></div>'));
  ok("C1: the new notes and legends are 14 px (the floor for new text)",
     /\.mode-note\{ margin:6px 0 0; font-size:14px;/.test(html) && /\.mode-legend\{ margin:8px 0 2px; font-size:14px;/.test(html));

  // ---- road load: the fetch, per month, cached; the loaded leg (the endpoint's default) ----
  ok("⭐ C1: Road load reads /api/public/road-load for the month on screen, cached per month, one fetch in flight per month",
     blkCode.includes("RL.pending[m] = fetch(CONFIG.API_BASE + '/public/road-load?month=' + m)")
     && blkCode.includes("if (RL.cache[m]) return Promise.resolve(RL.cache[m]);")
     && blkCode.includes(".then(j => { RL.cache[m] = j; delete RL.error[m]; return j; })"));
  ok("C1: the loaded leg only — the page never asks for leg=return, so empties are never added to the figure",
     !/road-load\?[^'"]*leg=/.test(code) && !/leg=return/.test(code));
  ok("C1: the month is the playhead's (once the matrix is read), or the sidebar window when From = To; else none",
     blkCode.includes("if (typeof TL !== 'undefined' && TL.on) return TL.matrix ? TL.month : null;")
     && blkCode.includes("if (f > 0 && f === t) return f;"));

  // ---- road load: the source, the line, the label, the card ----
  ok("⭐ C1: a road-load SOURCE and a line layer of ONE width, coloured by two-way movements a day on FIXED, ascending stops",
     blkCode.includes("map.addSource('road-load-source', { type: 'geojson'")
     // REVERSED 12 Oct 2026 (evening): one width (5 / 7.5 px), never by volume; volume is the colour on FIXED stops
     && !blkCode.includes("ROAD_LOAD_STOPS") && !blkCode.includes("roadLoadWidth")
     && blkCode.includes("const VOLUME_STOPS = [10, 25, 50, 100];")
     && blkCode.includes("const ROAD_LOAD_LINE_WIDTH = 5;") && blkCode.includes("const ROAD_LOAD_CASING_WIDTH = 7.5;")
     && /id: 'road-load-line', type: 'line', source: 'road-load-source',[\s\S]{0,200}'line-width': ROAD_LOAD_LINE_WIDTH/.test(blkCode)
     && /id: 'road-load-casing', type: 'line', source: 'road-load-source',[\s\S]{0,200}'line-width': ROAD_LOAD_CASING_WIDTH/.test(blkCode));
  ok("⭐ C1: routes stay blue — the road-load line is the plan blue (CONFIG.COLORS.brand) under an ink casing",
     /id: 'road-load-line'[\s\S]{0,200}'line-color': CONFIG\.COLORS\.brand,/.test(blkCode)
     && /id: 'road-load-casing'[\s\S]{0,200}'line-color': CONFIG\.COLORS\.forecastCasing,/.test(blkCode));
  ok("⭐ C1: ONE label per run with its OWN text expression ('N two-way / day · R routes'), never the per-route f_avg concat",
     blkCode.includes("const ROAD_LOAD_LABEL = ['concat', ['get', 'rl_mv_text'], ' two-way / day · ', ['get', 'rl_routes_text']];")
     // NARROWED 12 Oct 2026 (browser check): the label sits on its own point source, placed as a level point label;
     // the line-placed version ('line-center' on road-load-source) never rendered on bent roads
     && /id: 'road-load-labels', type: 'symbol', source: ROAD_LOAD_LABEL_SOURCE,[\s\S]{0,120}'symbol-placement': 'point', 'text-field': ROAD_LOAD_LABEL, 'text-size': 14,/.test(blkCode)
     && !/\['get', 'f_avg'\]/.test(blkCode));
  ok("⭐ browser check 12 Oct: the run label is NOT placed along the line (Mapbox drops a line-placed label wherever the road bends past the text's angle)",
     !/id: 'road-load-labels'[\s\S]{0,200}'symbol-placement': 'line/.test(blkCode)
     && blkCode.includes("const ROAD_LOAD_LABEL_SOURCE = 'road-load-label-source';")
     && blkCode.includes("if (!map.getSource(ROAD_LOAD_LABEL_SOURCE)) map.addSource(ROAD_LOAD_LABEL_SOURCE, { type: 'geojson'")
     && blkCode.includes("if (map.getSource(ROAD_LOAD_LABEL_SOURCE)) map.removeSource(ROAD_LOAD_LABEL_SOURCE);")
     && blkCode.includes("if (lsrc) lsrc.setData({ type: 'FeatureCollection', features: roadLoadLabelPoints(feats) });"));
  // 12 Oct 2026 (night, live in the user's Chrome: 1 of 18 carbon labels drawn on real HERE routes)
  ok("⭐ live check 12 Oct: the carbon route label is a LEVEL point label at the route's middle, on its own source — never placed along the line",
     blkCode.includes("const CARBON_LABEL_SOURCE = 'carbon-label-source';")
     && /id: CARBON_LABEL_LAYER, type: 'symbol', source: CARBON_LABEL_SOURCE, filter: carbonLabelFilter\(\),\s*layout: \{ 'symbol-placement': 'point', 'text-field': CARBON_ROUTE_LABEL, 'text-size': 14,/.test(blkCode)
     && !/id: CARBON_LABEL_LAYER[\s\S]{0,300}'symbol-placement': 'line/.test(blkCode)
     && blkCode.includes("const pt = runMidpoint(coords);")
     && blkCode.includes("if (co2) { ensureCarbonLabelLayer(); syncCarbonLabels(); }")
     && blkCode.includes("if (map.getSource(CARBON_LABEL_SOURCE)) map.removeSource(CARBON_LABEL_SOURCE);"));
  ok("browser check 12 Oct: the run label keeps to one line (text-max-width 30 ems) and is never forced over other labels",
     /id: 'road-load-labels'[\s\S]{0,300}'text-max-width': 30,/.test(blkCode)
     && !/id: 'road-load-labels'[\s\S]{0,400}'text-allow-overlap': true/.test(blkCode));
  // the four count pins of review §2.2d, honoured (asserted above unchanged; these say WHY they still hold)
  ok("⭐ C1 (§2.2d's four count pins): the road-load layers use ROUND caps and joins and carry no dasharray at all",
     (blkCode.match(/layout: \{ 'line-cap': 'round', 'line-join': 'round' \}/g) || []).length === 2
     && !/'line-cap': 'butt'/.test(blkCode) && !/line-dasharray/.test(blkCode)
     && (code.match(/'line-cap': 'butt'/g) || []).length === 5
     && (code.match(/'line-dasharray': DASH_(CORE|CASING)/g) || []).length === 4);
  ok("C1: both lazy adders re-raise the marks (raiseMarks count is additive)",
     /map\.addLayer\(\{ id: 'road-load-labels'[\s\S]{0,400}wireRoadLoadPopup\(\);\s*raiseMarks\(\);/.test(blkCode)
     // NARROWED 12 Oct 2026 (night): the carbon label layer's definition is longer (point placement), so a wider window
     && /map\.addLayer\(\{ id: CARBON_LABEL_LAYER[\s\S]{0,700}raiseMarks\(\);/.test(blkCode)
     && (code.match(/raiseMarks\(\);/g) || []).length >= 11);   // 9 on the base, + the two new adders
  ok("⭐ C1: the road-load and carbon-label ids are in BOTH removal lists (Show forecast off, and closeTimeline)",
     (code.match(/\['road-load-labels','road-load-line','road-load-casing','carbon-route-labels','forecast-labels','forecast-layer','forecast-casing','forecast-flow','forecast-cap-badge'\]\.forEach\(l\s?=>\s?\{ if\(map\.getLayer\(l\)\) map\.removeLayer\(l\); \}\);/g) || []).length === 2);
  ok("⭐ C1: re-added on style.load (setStyle drops every source and layer): the handler calls refreshMapModes() after the month re-render",
     (() => { const a = code.indexOf("map.on('style.load', async () => {"); const b = code.indexOf("let ALIGNMENT_POPUP_WIRED");
              const sl = a > 0 && b > a ? code.slice(a, b) : "";
              return sl.indexOf("if (typeof refreshMapModes === 'function') refreshMapModes();") > sl.indexOf("renderMonthFrame(TL.month); renderTimelineWarnings(TL.month);"); })()
     // NARROWED 12 Oct 2026 (night): setTimelineExpanded now sits between the month frame and openTimeline
     && /if\(typeof refreshMapModes === 'function'\) refreshMapModes\(\);\n    \}\n[^\n]*\n?    function setTimelineExpanded\(on\)\{/.test(code));
  ok("C1: every month on the playhead, the overlay switching off and closing the bar refresh the modes",
     /applyFilters\(\);\s*if\(typeof refreshMapModes === 'function'\) refreshMapModes\(\);[^\n]*\n    \}\n    function toggleTimeline/.test(code)
     && src.includes("if (typeof refreshMapModes === 'function') refreshMapModes();   // 12 Oct: Road load / Carbon follow\n                return;"));
  ok("⭐ C1: in either mode the per-route forecast labels HIDE, so two figures never show for one road",
     blkCode.includes("map.setLayoutProperty('forecast-labels', 'visibility', on ? 'visible' : 'none');")
     // NARROWED 12 Oct 2026 (night): and while By council is on (the council view quiets the routes)
     && blkCode.includes("setForecastLabelsVisible(!(m && (rl || co2)) && !councilFocus());"));
  // 12 Oct 2026 (night, the user: By council "would be good to see by itself")
  ok("⭐ council view: while a By council box is ticked the routes are thin pale grey with no casing, flow dashes or cap badges, and the route labels hide",
     blkCode.includes("const COUNCIL_ROUTE_COLOR = '#A8A29E', COUNCIL_ROUTE_WIDTH = 2;")
     && blkCode.includes("const COUNCIL_QUIET_LAYERS = ['forecast-casing', 'forecast-flow', 'forecast-cap-badge'];")
     && blkCode.includes("COUNCIL_QUIET_LAYERS.forEach(l => { if (map.getLayer(l)) map.setLayoutProperty(l, 'visibility', focus ? 'none' : 'visible'); });")
     && blkCode.includes("function councilFocus(){ return typeof areaTierOn === 'function' && (areaTierOn('district') || areaTierOn('county')); }"));
  ok("⭐ council view: ticking a council box turns the heat map Off; picking Volume or Carbon unticks the council boxes (one picture at a time); both write the link",
     code.includes("if (on) { const off = document.getElementById('heat-off'); if (off && !off.checked) { off.checked = true; if (typeof scheduleViewWrite === 'function') scheduleViewWrite(); } }")
     && src.includes("if (typeof refreshMapModes === 'function') refreshMapModes();\n    }\n    // one district at a time")
     && blkCode.includes("if (modeOn('toggle-road-load')) leaveCouncilView();") && blkCode.includes("if (modeOn('toggle-carbon')) leaveCouncilView();")
     && blkCode.includes("['district', 'county'].forEach(t => { const cb = document.getElementById('layer-areas-' + t); if (cb) cb.checked = false; });"));
  // REVERSED 12 Oct 2026 (night, the user: every other layer OFF, with the ability to tick layers back by hand): the
  // opacity fade is gone (a faded layer could not be brought back by its box); the boxes are unticked and remembered
  ok("⭐ council view: no opacity fade of the network any more; the first council box UNTICKS every other layer box (zone kinds left) and remembers them; the last unticked ticks them back",
     !code.includes("COUNCIL_FADE_LAYERS") && !code.includes("fadeNetworkForCouncil")
     && code.includes(`return [...document.querySelectorAll('input[type=checkbox][id^="layer-"], input[type=checkbox][id^="restr-"]')]`)
     && code.includes(".filter(cb => cb.id.indexOf('layer-areas-') !== 0 && cb.id.indexOf('layer-zone-') !== 0);")
     && code.includes("COUNCIL_SOLO.saved = boxes.filter(cb => cb.checked).map(cb => cb.id);")
     && code.includes("ids.forEach(id => { const cb = document.getElementById(id); if (cb) flip(cb, true); });")
     && code.includes("councilSolo(areaTierOn('district') || areaTierOn('county'));")
     && code.includes("cb.dispatchEvent(new Event('change', { bubbles: true }));"));
  ok("⭐ districts as blocks (mockup 4): fill 0.8 with a month, white 2.5 px borders between districts, the county's dashed ink line kept",
     code.includes("const AREA_FILL_OPACITY = 0.8;")
     && code.includes("paint: { 'line-color': '#FFFFFF', 'line-width': 2.5, 'line-opacity': 1 } }, before);")
     && /id: 'area-county-outline'[\s\S]{0,200}'line-color': AREA_INK, 'line-width': 2, 'line-dasharray': \[3, 2\]/.test(code));
  ok("council view: the By council group says what happens to the routes and the heat map while it is on",
     html.includes('<div class="area-note" id="area-focus-note" hidden>While By council is on, every other layer is switched off and the heat map is off, so the councils read by themselves. Tick any layer to add it back (routes show thin and grey); unticking By council brings back the layers you had on.</div>')
     && code.includes("if (fn) fn.hidden = !(areaTierOn('district') || areaTierOn('county'));"));
  ok("⭐ C1: the section card lists the routes, their teams through teamText (never the raw id) and their shares; registered ONCE",
     blkCode.includes("rlEsc(teamText((sh.teams || []).join(', ')) || '—')")
     && !/\.ipt\b/.test(blkCode) && !/\bipt\b/.test(blkCode)
     && blkCode.includes("if (RL.wired) return;") && blkCode.includes("map.on('click', 'road-load-line', (e) => {")
     && blkCode.includes("Loaded leg counted once (one load = one two-way movement)."));
  ok("C1: a click on a shared section answers with the section card, not the route card underneath",
     code.includes("if(typeof roadLoadHitAt === 'function' && roadLoadHitAt(e.point)) return;"));
  ok("C1: the sidebar filters re-cut the cached month (no fetch) through applyForecastFilter",
     code.includes("if (typeof refreshMapModeFilters === 'function') refreshMapModeFilters();"));

  // ---- carbon ----
  ok("⭐ C1 (D26): the carbon ramp is ONE hue, the plan blue, five steps light to dark — no orange, no rainbow",
     (() => {
       const m = /const CARBON_RAMP = \[([^\]]*)\];/.exec(blkCode);
       if (!m) return false;
       const hex = m[1].match(/#[0-9A-Fa-f]{6}/g) || [];
       const hsl = hex.map(h => { const r = parseInt(h.slice(1, 3), 16) / 255, g = parseInt(h.slice(3, 5), 16) / 255, b = parseInt(h.slice(5, 7), 16) / 255;
         const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn; let hu = 0;
         if (d) hu = mx === r ? 60 * (((g - b) / d) % 6) : mx === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4);
         return { h: (hu + 360) % 360, l: (mx + mn) / 2 }; });
       return hex.length === 5 && hsl.every(x => x.h >= 214 && x.h <= 220) && hsl.every((x, i) => i === 0 || x.l < hsl[i - 1].l);
     })()
     && !/#FF8C14/i.test(blk) && !/#F97316/i.test(blk));
  ok("⭐ C1: the stops are FIXED from the programme maximum (forecast-matrix co2_t), ascending, and the step takes them as literals",
     blkCode.includes("const CARBON_STEP_FRACTIONS = [0.2, 0.4, 0.6, 0.8];")
     // NARROWED 12 Oct 2026 (Track C review): the stops come through carbonScale — the route-month maximum for the routes,
     // the section-month maximum for the shared sections
     // NARROWED 12 Oct 2026 (evening): carbon paints the routes only, so always the route-month stops
     && blkCode.includes("const stops = carbonScale(false).stops;")
     && blkCode.includes("const max = mtx ? (sec ? mtx.sectionCo2Max : (mtx.co2Max || 0)) : 0;")
     && blkCode.includes("['step', ['to-number', ['get', prop], 0], c[0], s[0], c[1], s[1], c[2], s[2], c[3], s[3], c[4]],")
     && code.includes("const c = (rt.co2_t||{})[k];")
     && code.includes("Object.keys(byR).forEach(rid=>{ Object.keys(byR[rid].co2||{}).forEach(k=>{ if(byR[rid].co2[k] > co2Max) co2Max = byR[rid].co2[k]; }); });"));
  ok("C1: a route-month with no figure paints grey and is COUNTED, never a zero dressed as a figure",
     blkCode.includes("const CARBON_NONE = '#A8A29E';")
     && code.includes("if(c == null || j.co2_error) acc.co2Missing[k] = (acc.co2Missing[k]||0) + 1;")
     // REVERSED 12 Oct 2026 (wording review): the label on a DRAWN route with no figure says 'no carbon figure' - the
     // route is on the map, so 'no stored road route' contradicted it (and a failed carbon read is not that either)
     && blkCode.includes("'no carbon figure'") && !blkCode.includes("'no stored road route'"));
  // REVERSED 12 Oct 2026 (evening): one heat map at a time. Carbon paints the ROUTES only (a section's carbon is a length
  // share of a route, a different quantity on the same ramp); Volume paints the routes by f_avg AND the shared sections
  // by rl_mv on the same fixed stops. Colour only, one width (rule 1).
  ok("⭐ heat map: Volume paints routes (f_avg) and shared sections (rl_mv) on the volume stops; Carbon paints the routes only; one width",
     // NARROWED 12 Oct 2026 (night): the council view (By council on) paints the routes thin and grey before either mode
     blkCode.includes("const paint = focus ? COUNCIL_ROUTE_COLOR : vol ? volumeColor('f_avg', ROUTE_VOLUME_STOPS) : co2 ? carbonColor('f_co2', stops) : CONFIG.COLORS.forecast;")
     && blkCode.includes("map.setPaintProperty('forecast-layer', 'line-width', focus ? COUNCIL_ROUTE_WIDTH : heat ? CARBON_LINE_WIDTH : FORECAST_LINE_WIDTH);")
     && blkCode.includes("map.setPaintProperty('road-load-line', 'line-color', volumeColor('rl_mv', VOLUME_STOPS));")
     && !blkCode.includes("carbonColor('rl_co2'") && !blkCode.includes("paintRuns")
     // the two forecast addLayer sites keep the plan blue; carbon is a paint change, not a third forecast layer
     && (code.match(/'line-color':\s?CONFIG\.COLORS\.forecast,/g) || []).length === 2);
  ok("⭐ C1: the route label switches to 't CO₂e' in carbon mode (its own layer, on the loaded leg: one label per route)",
     // REVERSED 12 Oct 2026 (wording review): the fallback reads 'no carbon figure' (was 'no stored road route')
     blkCode.includes("['concat', ['to-string', ['get', 'f_co2']], ' t CO₂e'], 'no carbon figure'];")
     && blkCode.includes("return ['all', forecastLayerFilter(), ['==', ['get', 'type'], 'Inbound Highway']];")
     // NARROWED 12 Oct 2026 (evening): the sections are drawn in Volume only, so their label is always the volume one
     && blkCode.includes("map.setLayoutProperty('road-load-labels', 'text-field', ROAD_LOAD_LABEL);") && !code.includes("ROAD_LOAD_CARBON_LABEL"));
  ok("⭐ C1: the carbon legend is a stepped gradient with the note 'Approved plan only, average-laden factor on both legs, excludes N …'",
     blkCode.includes("'<div class=\"ml-steps\">' + CARBON_RAMP.map(c => '<i style=\"background:' + c + '\"></i>').join('') + '</div>'")
     // NARROWED 12 Oct 2026 (browser check): the excluded-line clause is written only when a line is excluded; the demo
     // read "excludes 0 lines with no stored road route"
     && blkCode.includes("'<div class=\"ml-foot\">Approved plan only, average-laden factor on both legs' +")
     && blkCode.includes("(miss ? ', excludes ' + miss + ' line' + (miss === 1 ? '' : 's') + ' with no stored road route' : '') +")
     && !blkCode.includes("on both legs, excludes ' + miss")
     // NARROWED 12 Oct 2026 (Track C review): the legend names the maximum used, route-month or section-month
     && blkCode.includes("'. Stops are fixed from the programme\\'s largest ' + sc.what + ' ('"));
  ok("browser check 12 Oct: on the desktop bar the conditions pill wraps inside 300 px (at 1280 px it covered the last figure card by 91 px)",
     /@media \(min-width:1024px\)\{ #kpi-conditions\{ flex-wrap:wrap; max-width:300px; flex-shrink:0;/.test(html)
     && html.includes(".cond-part{ display:inline-flex; align-items:center; gap:8px; white-space:nowrap; }")
     && code.includes("const part = (lvl, n, noun) => (n ? `<span class=\"cond-part\"><span class=\"cond-dot ${lvl}\"></span>")
     && code.includes("+ (c.cap ? `<span class=\"cond-part\"><span class=\"cond-dot warn\"></span>"));
  ok("browser check 12 Oct: while the timeline bar is open the map's attribution (with the ONS / OS licence lines) rides above it on the desktop",
     /@media \(min-width:768px\)\{\s*body\.timeline-on \.mapboxgl-ctrl-bottom-left, body\.timeline-on \.mapboxgl-ctrl-bottom-right\{ bottom:var\(--tl-foot, 0px\); \}/.test(html)
     && code.includes("document.body.classList.toggle('timeline-on', open);")
     && code.includes("const h = open ? Math.round((bar.offsetHeight || 0) + 18 + 8) : 0;")
     && code.includes("window.addEventListener('resize', syncTimelineFoot);")
     && (code.match(/bar\.style\.display='(flex|none)';\n        syncTimelineFoot\(\);/g) || []).length === 2);
  ok("⭐ browser check 12 Oct (phone): the section click opens the sheet card on the phone shell and the map popup only above it",
     code.includes("if (typeof isPhoneShell === 'function' && isPhoneShell() && typeof openRunCard === 'function') { openRunCard(run.id); return; }\n            new mapboxgl.Popup({ offset: 10, maxWidth: '360px' })")
     // NARROWED 13 Oct 2026 (lorry limits): the sheet's card dispatch gained a third kind ('limit:'); a section ('run:')
     // still opens its run card and anything else the route card
     && /const sc = String\(SHEET\.card\);\s*box\.innerHTML = sc\.indexOf\('run:'\) === 0 \? runCardHTML\(sc\.slice\(4\)\)\s*: sc\.indexOf\('limit:'\) === 0 \? limitSheetHTML\(sc\.slice\(6\)\)\s*: routeCardHTML\(SHEET\.card\);/.test(code));
  ok("⭐ browser check 12 Oct (phone): a near-miss tap is answered — exact hits and other clickable layers keep their own click, then a section, then a route",
     code.includes("if ((runL.length || routeL.length) && map.queryRenderedFeatures(e.point, { layers: runL.concat(routeL) }).length) return;")
     && code.includes("if (typeof clickableAt === 'function' && clickableAt(e.point)) return;")
     && /const runs = runL\.length \? map\.queryRenderedFeatures\(box, \{ layers: runL \}\) : \[\];\s*if \(runs\.length\) \{ openRunCard\(runs\[0\]\.properties\.id\); return; \}/.test(code)
     && code.includes("if (map && typeof map.on === 'function') map.on('click', phoneTapNear);")
     && /function phoneTapNear\(e\) \{\s*if \(!isPhoneShell\(\) \|\| !e \|\| !e\.point\) return;/.test(code));
  {
    const a = html.indexOf("#month-text{ width:100%; border-left:none; z-index:29; }");
    const mq = a > 0 ? html.lastIndexOf("@media", a) : -1;
    const blockCss = a > 0 ? html.slice(a, html.indexOf("\n        }", a)) : "";
    ok("browser check 12 Oct (phone): the text view fits 390 px (number headings wrap, 4 px cell padding) and the Guide button gives way to its close button",
       mq > 0 && /@media \(max-width:767px\)/.test(html.slice(mq, mq + 40))
       && blockCss.includes("table.mt-table th, table.mt-table td{ padding:7px 4px; }")
       && blockCss.includes("table.mt-table th.num{ white-space:normal; }")
       && blockCss.includes(".mt-body{ padding:12px 14px 18px; }")
       && blockCss.includes("body.month-text-open #guide-btn{ display:none; }"), html.slice(mq, mq + 40));
  }
  ok("browser check 12 Oct: a junction stub is drawn but not labelled (12 of 47 demo runs were 19 to 181 m)",
     blkCode.includes("const ROAD_LOAD_LABEL_MIN_KM = 0.2;")
     && blkCode.includes("properties: { id: r.id, rl_km: (r.length_km == null ? null : Number(r.length_km)),")
     && blkCode.includes("return feats.filter(f => f.properties.rl_km == null || f.properties.rl_km >= ROAD_LOAD_LABEL_MIN_KM)"));
  ok("C1: f_co2 is stamped on BOTH legs (both colour) and the excluded-line count sums the routes the filters pass, once each",
     /src\._data\.features\.forEach\(f => \{[\s\S]{0,500}if \(f\.properties\.f_co2 !== c\) \{ f\.properties\.f_co2 = c; changed = true; \}/.test(blkCode)
     && !/f\.properties\.type === 'Inbound Highway'/.test(blkCode.slice(blkCode.indexOf("function stampCarbon"), blkCode.indexOf("function carbonMissingLines"))));
  // ---- the drawer: one carbon number, the server's ----
  ok("⭐ C1: the drawer reads the server's co2_t for the sidebar window and works out no carbon of its own (no factor read)",
     (() => { const a = code.indexOf("async function openRouteAnalysis(routeId){"), b = code.indexOf("const MAT_PALETTE=");
              const d = a > 0 && b > a ? code.slice(a, b) : "";
              return d.includes("const mtx=await fetchMatrix('t');") && d.includes("const co2m=rw.co2_t||{};")
                     && !/vehicle_emissions_kg_co2e_per_km/.test(d) && !/round\s*\*\s*em/.test(d) && !/\*\s*emis/.test(d); })());
  // ---- the product rules ----
  ok("C1: no literal working-day divisor in the block (the server's movements_per_day; never 22)", !/\b22\b/.test(blkCode));
  {
    const strings = (blkCode.match(/'[^'\n]*'/g) || []).join(" ");
    ok("C1: nothing a person reads in the block says truck, real-time, live tracking, telematics, AI, optimise, predict or secure",
       !/truck|real-time|live tracking|telematics|optimi[sz]e|predict|\bsecure\b/i.test(strings) && !/\bAI\b/.test(strings));
  }
  ok("C1: every new symbol layer is 14 px", (blkCode.match(/'text-size': (\d+)/g) || []).length === 2 && !/'text-size': (1[0-3]|[0-9])\b/.test(blkCode));

  // ---- the block, run against a fake map and DOM ----
  const tA = src.indexOf("    const TEAM_LABELS = {};"), tB = src.indexOf("    // ===== The overlay package");
  ok("C1 sandbox: the teamText slice is found", tA > 0 && tB > tA);
  if (blk && tA > 0 && tB > tA) {
    let teamApi = null;
    try { teamApi = new Function("TEAM", src.slice(tA, tB) + "\nreturn { teamText, TEAM_LABELS };")("Team"); } catch (e) {}
    teamApi && (teamApi.TEAM_LABELS.IPT3 = "North Team", teamApi.TEAM_LABELS.IPT1 = "South Team");
    const mkMap = () => {
      const layers = {}, sources = {}, log = [];
      return { layers, sources, log,
        getLayer: id => layers[id], getSource: id => sources[id],
        addSource(id, spec) { sources[id] = { spec, _data: spec.data, setData(d) { this._data = d; log.push("setData:" + id); } }; },
        removeSource(id) { delete sources[id]; log.push("removeSource:" + id); },
        addLayer(spec) { if (layers[spec.id]) throw new Error("layer exists " + spec.id); layers[spec.id] = { spec, paint: Object.assign({}, spec.paint), layout: Object.assign({}, spec.layout), filter: spec.filter }; log.push("add:" + spec.id); },
        removeLayer(id) { delete layers[id]; log.push("remove:" + id); },
        setPaintProperty(id, k, v) { layers[id].paint[k] = v; }, setLayoutProperty(id, k, v) { layers[id].layout[k] = v; },
        setFilter(id, f) { layers[id].filter = f; },
        on(type, layer) { log.push("on:" + type + ":" + layer); }, queryRenderedFeatures: () => [], getCanvas: () => ({ style: {} }) };
    };
    const els = {};
    const el = id => els[id] || (els[id] = { id, checked: false, value: "", hidden: true, innerHTML: "" });
    const document = { getElementById: el };
    const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const monthLabel = i => names[(i - 1) % 12] + ' ' + (2026 + Math.floor((i - 1) / 12));
    const CONFIG = { API_BASE: "/api", COLORS: { brand: "#2563EB", forecast: "#3B82F6", forecastCasing: "#1F2024", brandDark: "#1F2024" } };
    const L = [[0, 0], [1, 1]];
    const a1_data = { features: [["R1", "Inbound Highway"], ["R1", "Outbound Highway"], ["R2", "Inbound Highway"], ["R2", "Outbound Highway"], ["R3", "Inbound Highway"]]
      .map(([rid, type]) => ({ geometry: { type: "LineString", coordinates: L }, properties: { route_id: rid, type, origin: "Q", dest: "C" } })) };
    let passFilter = () => true;
    const TL = { on: true, playing: false, month: 10, matrix: null };
    const fetches = [];
    let fetchImpl = url => { fetches.push(url); return Promise.resolve({ ok: true, json: () => Promise.resolve(RUNS[Number(/month=(\d+)/.exec(url)[1])] || { runs: [], notes: [] }) }); };
    let opened = 0;
    const RUNS = {
      10: { month: 10, notes: [], runs: [{ id: "S1", routes: ["R1", "R2"], movements_per_day: 46.27, co2_t: 3.21, length_km: 3.1, geometry: [[0, 0], [1, 1], [2, 2]],
              route_shares: [{ route_id: "R1", teams: ["IPT3"], movements_per_day: 22.1, co2_t: 2.0 }, { route_id: "R2", teams: ["South Team"], movements_per_day: 24.17, co2_t: 1.21 }] },
            { id: "S2", routes: ["R2", "R3"], movements_per_day: 0.4, co2_t: null, length_km: 1, geometry: [[0, 0], [1, 1]],
              route_shares: [{ route_id: "R2", teams: [], movements_per_day: 0.2, co2_t: null }, { route_id: "R3", teams: [], movements_per_day: 0.2, co2_t: null }] },
            { id: "S3", routes: ["R1", "R3"], movements_per_day: 5, co2_t: 1, length_km: 1, geometry: [[0, 0]], route_shares: [] }] },
      11: { month: 11, notes: ["Approved volume this month runs on no shared road section."], runs: [] } };
    let blkApi = null, blkErr = "";
    const fmap = mkMap();
    try {
      blkApi = new Function("document", "map", "TL", "CONFIG", "a1_data", "routePassesFilters", "monthLabel", "teamText", "fmtDist", "DU", "raiseMarks",
        "forecastLayerFilter", "FORECAST_LINE_WIDTH", "FORECAST_CASING_WIDTH", "fetch", "ensureTimelineMatrix", "openTimeline", "tlLoopBounds", "ROUTEINFO", "mapboxgl", "forecastWindow",
        blk + "\nreturn { RL, carbonStops, carbonColor, roadLoadFeatures, mapModeMonth, refreshMapModes, refreshMapModeFilters, toggleRoadLoad, toggleCarbon, stampCarbon, carbonMissingLines, roadLoadPopupHTML, renderModeLegends, CARBON_RAMP, CARBON_NONE, ROAD_LOAD_LABEL, runMidpoint, roadLoadLabelPoints, fmtTonnes, volumeColor, VOLUME_STOPS, heatMode, toggleHeatOff, carbonLabelPoints };")(
        document, fmap, TL, CONFIG, a1_data, p => passFilter(p), monthLabel, teamApi ? teamApi.teamText : (x => x), (k, d) => Number(k).toFixed(d), () => "km", () => {},
        () => ["all"], "FLW", "FCW", url => fetchImpl(url), () => Promise.resolve(TL.matrix), () => { opened++; }, () => [9, 12],
        { r1: { origin: "Kilby Ridge Quarry", dest: "Harborough Compound" }, r2: { origin: "Northfield Quarry", dest: "Harborough Compound" } }, {},
        // merge with C3 (D14): the page's own forecastWindow — the matrix's span with volume; NARROWED 12 Oct 2026 (Track C
        // review): else no window (null), as the page now says
        () => (TL.matrix && TL.matrix.span) ? [TL.matrix.span[0], TL.matrix.span[1]] : null);
    } catch (e) { blkErr = e.message; }
    ok("⭐ C1 sandbox: the road-load / carbon block runs against a fake map and DOM", !!blkApi && !!teamApi, blkErr);
    if (blkApi) {
      const mp = blkApi.runMidpoint;
      const near = (a, b) => !!a && Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
      ok("browser check 12 Oct: runMidpoint is half way by LENGTH, not the middle vertex (a 3 + 1 run's middle sits on the long leg)",
         near(mp([[0, 0], [0, 3], [0, 4]]), [0, 2]) && near(mp([[0, 0], [0, 1]]), [0, 0.5]) && near(mp([[5, 5]]), [5, 5])
         && mp([]) === null && near(mp([[1, 1], [1, 1]]), [1, 1]));
      ok("browser check 12 Oct: a figure above zero that rounds to nothing reads 'under 0.1 t', never '0 t'; a true zero stays '0 t'",
         blkApi.fmtTonnes(0.018) === "under 0.1 t" && blkApi.fmtTonnes(0.049) === "under 0.1 t" && blkApi.fmtTonnes(0.05) === "0.1 t"
         && blkApi.fmtTonnes(0) === "0 t" && blkApi.fmtTonnes(12.66) === "12.7 t" && blkApi.fmtTonnes(1234) === (1234).toLocaleString() + " t",
         [0.018, 0.05, 0, 1234].map(blkApi.fmtTonnes).join(" | "));
      const stub = km => ({ type: "Feature", geometry: { type: "LineString", coordinates: [[0, 0], [0, 1]] }, properties: { id: "x" + km, rl_km: km } });
      ok("browser check 12 Oct: runs under 0.2 km get no label point; 0.2 km and over, and a run with no length from the server, do",
         blkApi.roadLoadLabelPoints([stub(0.019), stub(0.199), stub(0.2), stub(3.1), stub(null)]).map(f => f.properties.id).join(",") === "x0.2,x3.1,xnull");
    }
    if (blkApi) {
      const B = blkApi;
      // the stops
      const asc = a => a.length === 4 && a.every((x, i) => i === 0 || x > a[i - 1]);
      ok("⭐ C1: carbonStops(55.5) is [11, 22, 33, 44] (two significant figures of 20/40/60/80 % of the programme maximum)",
         JSON.stringify(B.carbonStops(55.5)) === "[11,22,33,44]", JSON.stringify(B.carbonStops(55.5)));
      ok("⭐ C1: the stops are strictly ascending for any maximum, including none and tiny ones (Mapbox refuses others)",
         [0, null, 0.0004, 0.37, 1, 7.77, 99.9, 482, 12345.6].every(x => asc(B.carbonStops(x))),
         JSON.stringify([0, 0.0004, 0.37, 7.77].map(x => B.carbonStops(x))));
      const cc = B.carbonColor("f_co2", [11, 22, 33, 44]);
      ok("C1: the colour expression: a number steps through the five blues at the fixed stops, anything else is the grey 'no figure'",
         cc[0] === "case" && JSON.stringify(cc[1]) === JSON.stringify(["==", ["typeof", ["get", "f_co2"]], "number"])
         && JSON.stringify(cc[2]) === JSON.stringify(["step", ["to-number", ["get", "f_co2"], 0], "#94BBF9", 11, "#5A96F6", 22, "#2071F3", 33, "#0B55CB", 44, "#073888"])
         && cc[3] === B.CARBON_NONE);
      // the features: two overlapping routes, summed once
      const all = B.roadLoadFeatures(RUNS[10], null);
      const s1 = all.find(f => f.properties.id === "S1");
      ok("⭐ C1: two overlapping routes (22.1 + 24.17 a day) give ONE run of 46 two-way a day — their sum, never doubled — and '2 routes'",
         !!s1 && s1.properties.rl_mv === 46.27 && Math.abs(s1.properties.rl_mv - (22.1 + 24.17)) < 0.01
         && s1.properties.rl_mv_text === "46" && s1.properties.rl_routes_text === "2 routes" && s1.properties.rl_co2 === 3.2,
         JSON.stringify(s1 && s1.properties));
      ok("C1: a run under one a day reads 'under 1', a run with no carbon reads 'no carbon figure', a one-point run is not drawn",
         all.length === 2 && all[1].properties.rl_mv_text === "under 1" && all[1].properties.rl_co2 === null
         && all[1].properties.rl_co2_text === "no carbon figure");
      const one = B.roadLoadFeatures(RUNS[10], { R1: true });
      ok("C1: with the filters passing R1 only, the run carries R1's own share ('22 … 1 route') and the run R1 is not on disappears",
         one.length === 1 && one[0].properties.rl_mv_text === "22" && one[0].properties.rl_routes_text === "1 route" && one[0].properties.rl_co2 === 2);
      // the card: names, never ids
      const pop = B.roadLoadPopupHTML(RUNS[10].runs[0], 10, null);
      ok("⭐ C1: the section card lists both routes with origin → destination and team NAMES; no team id reaches it",
         pop.includes("R1") && pop.includes("R2") && pop.includes("Kilby Ridge Quarry → Harborough Compound") && pop.includes("North Team")
         && pop.includes("South Team") && !/IPT\s*\d/i.test(pop) && pop.includes("46 two-way movements a day · 2 routes")
         && pop.indexOf("R2") < pop.indexOf("R1"), pop.slice(0, 300));
      ok("C1: ...and names the routes on the section that the filters leave out", B.roadLoadPopupHTML(RUNS[10].runs[0], 10, { R1: true }).includes("outside the filters: R2"));
      // the month
      TL.on = true; TL.matrix = null;
      ok("C1: the bar open before its matrix is read is NO month (not the default January)", B.mapModeMonth() === null);
      // merged with C3 (D14), narrowed: From / To are gone, so the window is forecastWindow() (the span with volume)
      TL.on = false; el("toggle-forecast").checked = true; TL.matrix = { span: [10, 12] };
      ok("C1: Show forecast over three months is no month; a window of one month is that month (the span with volume, no From / To)",
         B.mapModeMonth() === null && (TL.matrix = { span: [10, 10] }, B.mapModeMonth() === 10));
      TL.matrix = null;
      ok("C1 (merge with C3): with no matrix there is no window, so no month", B.mapModeMonth() === null);
      el("toggle-forecast").checked = false;
      // a tick with no month opens the timeline
      el("toggle-road-load").checked = true; B.toggleRoadLoad();
      ok("C1: ticking Road load with no month on screen opens the timeline (it has the month)", opened === 1 && fetches.length === 0);
      // the timeline open on October
      TL.on = true; TL.month = 10;
      TL.matrix = { co2Max: 55.5, co2Error: null, byRoute: { r1: { route_id: "R1", co2: { "10": 47.34 }, co2Missing: {} }, r2: { route_id: "R2", co2: {}, co2Missing: { "10": 1 } }, r3: { route_id: "R3", co2: { "10": 5 }, co2Missing: { "10": 2 } } } };
      fmap.addSource("routes-source", { type: "geojson", data: a1_data });
      fmap.addLayer({ id: "forecast-casing", paint: { "line-color": "#1F2024", "line-width": "FCW" } });
      fmap.addLayer({ id: "forecast-layer", paint: { "line-color": "#3B82F6", "line-width": "FLW" } });
      fmap.addLayer({ id: "forecast-labels", layout: { "text-field": "f_avg concat" } });
      ASYNC_PINS.push((async () => {
        const flush = () => new Promise(r => setTimeout(r, 0));
        B.refreshMapModes(); await flush(); await flush();
        ok("⭐ C1: Road load on, October: one fetch of road-load?month=10, the source and three layers added, the per-route labels hidden",
           JSON.stringify(fetches) === JSON.stringify(["/api/public/road-load?month=10"]) && !!fmap.layers["road-load-line"] && !!fmap.layers["road-load-casing"]
           && !!fmap.layers["road-load-labels"] && fmap.layers["forecast-labels"].layout.visibility === "none"
           && fmap.sources["road-load-source"]._data.features.length === 2, JSON.stringify(fetches));
        {
          const lp = fmap.sources["road-load-label-source"] ? fmap.sources["road-load-label-source"]._data.features : [];
          ok("⭐ browser check 12 Oct: one label POINT per drawn run, at the run's middle by length, carrying the run's own figures",
             lp.length === 2 && lp.every(f => f.geometry.type === "Point")
             && Math.abs(lp[0].geometry.coordinates[0] - 1) < 1e-9 && Math.abs(lp[0].geometry.coordinates[1] - 1) < 1e-9
             && Math.abs(lp[1].geometry.coordinates[0] - 0.5) < 1e-9 && Math.abs(lp[1].geometry.coordinates[1] - 0.5) < 1e-9
             && lp[0].properties.rl_mv_text === "46" && lp[1].properties.rl_mv_text === "under 1"
             && fmap.layers["road-load-labels"].spec.source === "road-load-label-source", JSON.stringify(lp.map(f => f.geometry.coordinates)));
        }
        ok("C1: the card is wired once (click, enter, leave on road-load-line)",
           fmap.log.filter(x => x.startsWith("on:")).join(",") === "on:mouseenter:road-load-line,on:mouseleave:road-load-line,on:click:road-load-line");
        // NARROWED 12 Oct 2026 (evening): the legend is the five-step ramp on the fixed volume stops, not three widths
        ok("C1: the legend says the month, the five colour steps of the volume stops and the counting rule",
           el("road-load-legend").hidden === false && el("road-load-legend").innerHTML.includes("Volume · two-way movements a day in Oct 2026")
           && el("road-load-legend").innerHTML.includes("under 10") && el("road-load-legend").innerHTML.includes("100 and over")
           && el("road-load-legend").innerHTML.includes("ml-steps") && !el("road-load-legend").innerHTML.includes("ml-w")
           && el("road-load-legend").innerHTML.includes("the loaded leg is counted once"));
        {
          const fl0 = fmap.layers["forecast-layer"].paint, rl0 = fmap.layers["road-load-line"].paint;
          ok("⭐ heat map (Volume): the routes are painted by f_avg and the sections by rl_mv on the SAME five blues and stops [10, 25, 50, 100], one width",
             JSON.stringify(fl0["line-color"]) === JSON.stringify(["step", ["to-number", ["get", "f_avg"], 0], "#94BBF9", 10, "#5A96F6", 25, "#2071F3", 50, "#0B55CB", 100, "#073888"])
             && JSON.stringify(rl0["line-color"]) === JSON.stringify(B.volumeColor("rl_mv", [10, 25, 50, 100]))
             && fl0["line-width"] === 5 && rl0["line-width"] === 5 && fmap.layers["forecast-casing"].paint["line-width"] === 7.5
             && !fmap.layers["carbon-route-labels"] && B.heatMode() === "volume", JSON.stringify(fl0));
        }
        B.refreshMapModes(); await flush(); B.refreshMapModes(); await flush();
        ok("⭐ C1: the same month again is read from the cache — no second fetch, no second set of layers", fetches.length === 1);
        TL.month = 11; B.refreshMapModes(); await flush(); await flush();
        ok("⭐ C1: the next month on the playhead re-fetches (road-load?month=11) and the server's note reaches the legend",
           fetches[1] === "/api/public/road-load?month=11" && fmap.sources["road-load-source"]._data.features.length === 0
           && el("road-load-legend").innerHTML.includes("Approved volume this month runs on no shared road section."));
        TL.month = 10; B.refreshMapModes(); await flush();
        ok("C1: back to October: from the cache, the runs drawn again", fetches.length === 2 && fmap.sources["road-load-source"]._data.features.length === 2);
        // filters
        passFilter = p => p.route_id === "R1"; B.refreshMapModeFilters();
        ok("C1: a filter change re-cuts the cached month with no fetch", fetches.length === 2 && fmap.sources["road-load-source"]._data.features.length === 1
           && fmap.sources["road-load-source"]._data.features[0].properties.rl_mv_text === "22");
        ok("browser check 12 Oct: ...and the label points follow the same cut (one point, the filtered figure)",
           fmap.sources["road-load-label-source"]._data.features.length === 1
           && fmap.sources["road-load-label-source"]._data.features[0].properties.rl_mv_text === "22");
        passFilter = () => true; B.refreshMapModeFilters();
        // REVERSED 12 Oct 2026 (evening): Volume and Carbon are radio buttons — picking Carbon un-picks Volume (the browser
        // does it; the fake DOM is told). An old link with BOTH ticked is guarded: Volume wins.
        el("toggle-carbon").checked = true;
        ok("heat map: with both ids ticked (an old road-load.carbon link) the mode is Volume, never both", B.heatMode() === "volume");
        el("toggle-road-load").checked = false; B.toggleCarbon(); await flush(); await flush();
        ok("⭐ C1: picking Carbon takes the shared sections away and paints the ROUTES by f_co2 on the blue ramp, one width",
           !fmap.layers["road-load-line"] && !fmap.sources["road-load-source"]
           && fmap.layers["forecast-layer"].paint["line-color"][0] === "case" && fmap.layers["forecast-layer"].paint["line-color"][2][1][1][1] === "f_co2"
           && fmap.layers["forecast-layer"].paint["line-width"] === 5 && !!fmap.layers["carbon-route-labels"]
           && el("road-load-legend").hidden === true);
        // NARROWED 12 Oct 2026 (evening): per route (carbon never paints the shared sections now)
        ok("⭐ C1: the carbon legend: per route, the five ranges from the fixed stops, 'excludes 3 lines with no stored road route'",
           el("carbon-legend").hidden === false && el("carbon-legend").innerHTML.includes("Carbon · t CO₂e in Oct 2026, per route")
           && el("carbon-legend").innerHTML.includes("under 11 t") && el("carbon-legend").innerHTML.includes("44 t and over")
           && el("carbon-legend").innerHTML.includes("Approved plan only, average-laden factor on both legs, excludes 3 lines with no stored road route.")
           && el("carbon-legend").innerHTML.includes("(55.5 t)"), el("carbon-legend").innerHTML.slice(0, 400));
        // REVERSED 12 Oct 2026 (evening): carbon paints the routes only, so a section-month figure from the server never
        // sets the stops; the route-month maximum always does
        TL.matrix.sectionCo2Max = 9.1; B.refreshMapModes(); await flush();
        const rlc = fmap.layers["forecast-layer"].paint["line-color"][2];
        ok("⭐ heat map: Carbon's stops come from the largest ROUTE-month (55.5 t) even when the server sends a section-month (9.1 t)",
           JSON.stringify([rlc[3], rlc[5], rlc[7], rlc[9]]) === JSON.stringify(B.carbonStops(55.5))
           && el("carbon-legend").innerHTML.includes("largest route-month (55.5 t)") && !el("carbon-legend").innerHTML.includes("section-month"),
           JSON.stringify(rlc) + " " + el("carbon-legend").innerHTML.slice(0, 200));
        delete TL.matrix.sectionCo2Max; B.refreshMapModes(); await flush();
        ok("Track C review: ...and with no section figure from the server, the route-month maximum, named as such",
           el("carbon-legend").innerHTML.includes("largest route-month (55.5 t)")
           && JSON.stringify(fmap.layers["forecast-layer"].paint["line-color"][2].filter((x, i) => i >= 3 && i % 2 === 1)) === JSON.stringify(B.carbonStops(55.5)));
        // road load off: the forecast routes carry the carbon
        el("toggle-road-load").checked = false; B.toggleRoadLoad(); await flush();
        const fl = fmap.layers["forecast-layer"].paint;
        ok("⭐ C1: Road load off, Carbon on: the road-load source and layers go, the FORECAST routes are painted by f_co2 at a fixed width",
           !fmap.layers["road-load-line"] && !fmap.sources["road-load-source"] && fl["line-color"][2][1][1][1] === "f_co2" && fl["line-width"] === 5
           && fmap.layers["forecast-casing"].paint["line-width"] === 7.5);
        ok("browser check 12 Oct: Road load off removes the label-point source too", !fmap.sources["road-load-label-source"] && !fmap.layers["road-load-labels"]);
        ok("⭐ C1: ...the route label switches to t CO₂e (its own layer on the loaded leg) and the per-route figure label stays hidden",
           !!fmap.layers["carbon-route-labels"] && JSON.stringify(fmap.layers["carbon-route-labels"].filter) === JSON.stringify(["all", ["all"], ["==", ["get", "type"], "Inbound Highway"]])
           && fmap.layers["forecast-labels"].layout.visibility === "none");
        const fco2 = a1_data.features.map(f => f.properties.route_id + "/" + f.properties.type.split(" ")[0] + "=" + f.properties.f_co2).join(",");
        ok("⭐ C1: f_co2 is the route's month figure on BOTH legs (rounded to 0.1 t); a route with no figure is null, never 0",
           fco2 === "R1/Inbound=47.3,R1/Outbound=47.3,R2/Inbound=null,R2/Outbound=null,R3/Inbound=5", fco2);
        ok("C1: the legend says per route now", el("carbon-legend").innerHTML.includes("per route</b>"));
        {
          // 12 Oct 2026 (night): the label points — one per route on the overlay, loaded leg only, at the middle by length
          const saved = a1_data.features.map(f => f.properties.is_forecast);
          a1_data.features.forEach(f => { f.properties.is_forecast = f.properties.route_id !== "R2"; });
          const pts = B.carbonLabelPoints();
          ok("⭐ live check 12 Oct: one carbon label point per route on the overlay (loaded leg only, none for a route off the overlay), at its middle, carrying f_co2",
             pts.length === 2 && pts.map(p => p.properties.route_id).join(",") === "R1,R3" && pts.every(p => p.geometry.type === "Point" && p.properties.type === "Inbound Highway")
             && Math.abs(pts[0].geometry.coordinates[0] - 0.5) < 1e-9 && Math.abs(pts[0].geometry.coordinates[1] - 0.5) < 1e-9
             && pts[0].properties.f_co2 === 47.3 && pts[1].properties.f_co2 === 5, JSON.stringify(pts.map(p => p.properties)));
          a1_data.features.forEach((f, i) => { f.properties.is_forecast = saved[i]; });
        }
        // 12 Oct 2026 (wording review): a CO2e figure a person reads carries the Carbon page's stamp, from the feed
        ok("⭐ wording: with no stamp in the feed the carbon legend prints none (never retyped on the page)",
           !el("carbon-legend").innerHTML.includes("Carbon Tool"));
        TL.matrix.carbonStamp = "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"; B.refreshMapModes(); await flush();
        ok("⭐ wording: the carbon legend ends with the Carbon page's stamp from forecast-matrix (carbon_stamp), word for word",
           el("carbon-legend").innerHTML.includes(" Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures.</div>"),
           el("carbon-legend").innerHTML.slice(-200));
        B.RL.cache[10].carbon = { stamp: "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" };
        ok("⭐ wording: the shared-section card prints the road-load feed's carbon stamp while Carbon is on",
           B.roadLoadPopupHTML(RUNS[10].runs[0], 10, null).includes("Approved plan only. Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures.</div>"));
        el("toggle-carbon").checked = false;
        ok("wording: ...and not while Carbon is off (the card then shows no CO2e figure)",
           !B.roadLoadPopupHTML(RUNS[10].runs[0], 10, null).includes("Carbon Tool"));
        el("toggle-carbon").checked = true; B.refreshMapModes(); await flush();
        {
          // 12 Oct 2026 (night): the council view, then back
          fmap.addLayer({ id: "forecast-flow", paint: {}, layout: {} });
          globalThis.areaTierOn = t => t === "district";
          B.refreshMapModes(); await flush();
          const fq = fmap.layers["forecast-layer"].paint;
          ok("⭐ council view (sandbox): with Local authority districts ticked the routes are #A8A29E at 2 px, the casing and flow hidden, the labels hidden",
             fq["line-color"] === "#A8A29E" && fq["line-width"] === 2 && fmap.layers["forecast-casing"].layout.visibility === "none"
             && fmap.layers["forecast-flow"].layout.visibility === "none" && fmap.layers["forecast-labels"].layout.visibility === "none", JSON.stringify(fq));
          // REVERSED 12 Oct 2026 (night): no network fade in the mode block; the boxes are unticked (pinned above)
          ok("council view (sandbox): the mode block leaves the network's paint alone (no inbound-lines layer touched)", !fmap.layers["inbound-lines"]);
          delete globalThis.areaTierOn;
          B.refreshMapModes(); await flush();
          ok("council view (sandbox): unticked, the casing and flow are back and the routes take the mode's paint again",
             fmap.layers["forecast-casing"].layout.visibility === "visible" && fmap.layers["forecast-flow"].layout.visibility === "visible"
             && fmap.layers["forecast-layer"].paint["line-color"] !== "#A8A29E");
        }
        // a failed carbon read
        TL.matrix.co2Error = "The carbon figures could not be read (OperationalError)."; B.refreshMapModes(); await flush();
        ok("C1: a failed carbon read paints every route grey (no figure) and says so in the legend",
           a1_data.features.every(f => f.properties.f_co2 === null) && el("carbon-legend").innerHTML.includes("could not be read"));
        TL.matrix.co2Error = null;
        // everything off
        el("toggle-carbon").checked = false; B.toggleCarbon(); await flush();
        // NARROWED 12 Oct 2026 (evening): one width now, not "volume widths"; and the "Off" button shows picked
        ok("heat map: with neither mode picked, refreshMapModes shows the 'Off' radio picked", el("heat-off").checked === true);
        ok("⭐ C1: both off: the forecast routes are plan blue at their one width again, the carbon labels gone, the route labels back",
           fmap.layers["forecast-layer"].paint["line-color"] === "#3B82F6" && fmap.layers["forecast-layer"].paint["line-width"] === "FLW"
           && fmap.layers["forecast-casing"].paint["line-width"] === "FCW" && !fmap.layers["carbon-route-labels"]
           && fmap.layers["forecast-labels"].layout.visibility === "visible" && el("carbon-legend").hidden === true && el("road-load-legend").hidden === true);
        // closing the bar with Road load ticked: no month, nothing drawn, the legend says why
        el("toggle-road-load").checked = true; B.refreshMapModes(); await flush();
        TL.on = false; B.refreshMapModes(); await flush();
        ok("C1: the bar closed with Road load ticked: no layers, no source, and the legend says it shows one month",
           !fmap.layers["road-load-line"] && !fmap.sources["road-load-source"] && el("road-load-legend").innerHTML.includes("Shows one month")
           && fmap.layers["forecast-labels"].layout.visibility === "visible");
        // 12 Oct 2026 (wording review): it said "set From and To to the same month" - controls D14 removed
        ok("⭐ wording: the 'one month' note tells a person to press Play or pick a month, never to set the removed From / To",
           el("road-load-legend").innerHTML.includes("Shows one month: press Play or pick a month.")
           && !/From and To/.test(el("road-load-legend").innerHTML), el("road-load-legend").innerHTML);
        el("toggle-road-load").checked = false;
      })());
    }
  }

  // ---- the matrix sums each route's lines' co2_t per month (loadTimelineMatrix, run) ----
  {
    const a = src.indexOf("    async function loadTimelineMatrix(){"), b = src.indexOf("    // 12 Oct 2026 (review §2.4): Play used to fire one month-kpis GET");
    ok("C1 sandbox: loadTimelineMatrix is found", a > 0 && b > a);
    if (a > 0 && b > a) {
      const TLm = {};
      let body = null;
      const run = new Function("TL", "CONFIG", "fetch", "prefetchSpanKpis", "FORECAST_WORKING_DAYS",
        src.slice(a, b) + "\nreturn loadTimelineMatrix;")(TLm, { MONTH_COUNT: 60, FORECAST_UNIT: "vehicles", API_BASE: "" },
        () => Promise.resolve({ ok: true, json: () => Promise.resolve(body) }), () => {}, 22);
      ASYNC_PINS.push((async () => {
        body = { unit: "vehicles", working_days: 21, routes: [
          { route_id: "R1", monthly: { "10": 100, "11": 50 }, total: 150, co2_t: { "10": 2.5, "11": 1.0 } },
          { route_id: "R1", monthly: { "10": 40 }, total: 40, co2_t: { "10": 3.0 } },
          { route_id: "R2", monthly: { "10": 30, "12": 0 }, total: 30, co2_t: { "10": null, "12": null } } ] };
        await run();
        const r1 = TLm.matrix.byRoute.r1, r2 = TLm.matrix.byRoute.r2;
        ok("⭐ C1: the matrix sums a route's lines' server co2_t per month (2.5 + 3.0 = 5.5) and keeps the programme maximum",
           Math.abs(r1.co2["10"] - 5.5) < 1e-9 && r1.co2["11"] === 1 && TLm.matrix.co2Max === 5.5 && TLm.matrix.co2Error === null, JSON.stringify(r1.co2));
        ok("C1: a line-month with volume and no figure is counted missing, never summed as zero; a month with no volume is not counted",
           r2.co2["10"] === undefined && r2.co2Missing["10"] === 1 && r2.co2Missing["12"] === undefined);
        body = Object.assign({}, body, { co2_error: "The carbon figures could not be read (OperationalError)." });
        await run();
        ok("C1: forecast-matrix's co2_error: every line-month counted missing, no maximum, the error kept for the legend",
           TLm.matrix.co2Max === 0 && TLm.matrix.byRoute.r1.co2Missing["10"] === 2 && /could not be read/.test(TLm.matrix.co2Error));
      })());
    }
  }
}
// ==== 12 Oct 2026 — C3: the phone shell (review 2.8 row 2, mockup 7, D30) and the interactivity pass (review 2.3, D14, D29) ====
// Source pins on the CSS and the markup, then the new script block run against a fake DOM: the month chips, the hover
// card's words, the deep link, the QR code (decoded back by an independent reader below), "Report a concern", the text
// view's table and the sheet's state. What this does NOT prove: anything a browser draws (checked by hand in Chrome at
// 390 x 844, 800 and 1280 x 800 against a local server with synthetic route lines — not a real phone, not touch).
{
  // ---- (1) the phone shell's CSS: one block at 767 px and below, after the timeline bar's rules -----------------------
  const secA = html.indexOf("===== 12 Oct 2026 — the interactivity pass (review 2.3, D14, D29) and the phone shell");
  const secB = html.indexOf("/* H10 (8 Oct 2026): the map's guide");
  const sec = secA > 0 && secB > secA ? html.slice(secA, secB) : "";
  const shell = (sec.match(/@media \(max-width:767px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  const tlNarrowAt = html.indexOf("#timeline-bar input[type=range]{ order:6; flex:1 1 60px; width:auto; }");
  ok("C3 phone: the new CSS section exists, after the timeline bar's phone rules (so its overrides win), with ONE block at max-width:767px",
     sec.length > 0 && shell.length > 0 && secA > tlNarrowAt && tlNarrowAt > 0 && (html.match(/@media \(max-width:767px\)/g) || []).length === 1);
  ok("C3 phone (D30): the JS breakpoint is the CSS one — PHONE_SHELL_MQ is '(max-width:767px)' and isPhoneShell() reads it with matchMedia",
     code.includes("const PHONE_SHELL_MQ = '(max-width:767px)';") && /function isPhoneShell\(\) \{\s*try \{ return !!\(window\.matchMedia && window\.matchMedia\(PHONE_SHELL_MQ\)\.matches\); \}/.test(code));
  ok("C3 phone: below 768 the map is full-screen — the figures bar, the menu button, the timeline bar, the conditions panel, the drawer and the detail-table button are hidden",
     shell.includes("#kpi-hud, #menu-toggle, #timeline-bar, #tl-warnings, #route-drawer, #btn-detail{ display:none !important; }"));
  ok("C3 phone: the basemap widget is off on phones (the Layers sheet carries the basemap)",
     shell.includes(".custom-map-widget{ display:none !important; }") && code.includes("this._container.className = 'mapboxgl-ctrl custom-map-widget';"));
  ok("C3 phone: the shell's pieces are hidden at every other width (one rule before the block)",
     sec.indexOf("#m-layers-btn, #m-sheet, .m-done{ display:none; }") >= 0 && sec.indexOf("#m-layers-btn, #m-sheet, .m-done{ display:none; }") < sec.indexOf("@media (max-width:767px)"));
  ok("C3 phone: 44-48 px targets — the Layers button 48, the handle 48, Play 48, a month chip 48, the panel's selects / buttons / rows 48, the zoom buttons 44",
     /#m-layers-btn\{ display:flex;[^}]*height:48px;/.test(shell) && /\.m-handle\{[^}]*flex:0 0 48px; height:48px;/.test(shell)
     && /\.m-play\{ flex:0 0 48px; width:48px; height:48px;/.test(shell) && /\.month-chip\{ min-height:48px; min-width:56px;/.test(shell)
     && /\.m-chips-row \.month-chip\{ min-width:48px;/.test(shell)
     && shell.includes(".sidebar select, .sidebar .btn, .sidebar .fc-toggle{ min-height:48px; }") && shell.includes(".sidebar .control-item{ min-height:48px; }")
     && shell.includes(".mapboxgl-ctrl-group button{ width:44px; height:44px; }") && /\.m-body \.tl-warn \.show, \.m-body \.tl-warn \.x\{ min-height:44px; min-width:44px;/.test(shell));
  ok("C3 phone: the panel IS the full-screen layers sheet below 768 (full width, rises from the bottom, hidden from focus when shut), above the bottom sheet (28 over 26), under the demo strip (30)",
     /\.sidebar\{ width:100%; border-right:none; z-index:28; transform:none; visibility:visible;/.test(shell)
     && /\.sidebar\.closed\{ transform:translateY\(105%\); visibility:hidden;/.test(shell) && /#m-sheet\{ display:flex;[^}]*z-index:26;/.test(shell)
     && /#demo-notice\{[^}]*z-index:30;/.test(html) && /\.m-done\{ display:flex; order:99; position:sticky;/.test(shell));
  ok("C3 phone: the sheet's states — the body is hidden at peek and scrolls at half (about 62 % of the screen)",
     shell.includes('#m-sheet[data-state="peek"] .m-body{ display:none; }') && /#m-sheet\[data-state="half"\]\{ height:min\(62vh,/.test(shell)
     && /\.m-body\{ overflow:auto;/.test(shell));
  // above 767 nothing changes: the base pins above still pass, and the section's desktop rules touch only the text view
  const wide = (sec.match(/@media \(min-width:1024px\)\{([\s\S]*?)\n        \}/) || ["", ""])[1];
  const wideSel = wide.split("\n").map(l => l.trim()).filter(Boolean).map(l => l.slice(0, l.indexOf("{")).trim());
  ok("C3: above 767 the only new layout rules are the text view's (each desktop selector names #month-text or body.month-text-open)",
     wideSel.length >= 5 && wideSel.every(s => /#month-text|body\.month-text-open/.test(s)), JSON.stringify(wideSel));
  // the 14 px floor on everything new
  const sizes = [...sec.matchAll(/font(?:-size)?:\s*(?:[0-9]{3}\s+)?([0-9.]+)px/g)].map(m => Number(m[1]));
  ok("C3: the 14 px floor — every font size in the new CSS section is 14 px or more", sizes.length >= 20 && sizes.every(n => n >= 14), JSON.stringify(sizes));
  // ---- (2) the markup ---------------------------------------------------------------------------------------------
  ok("C3 phone: ONE Layers button, a real button that names and reports its sheet",
     html.includes('<button type="button" id="m-layers-btn" onclick="openLayersSheet()" aria-controls="main-sidebar" aria-expanded="false">&#8779; Layers</button>')
     && (html.match(/id="m-layers-btn"/g) || []).length === 1);
  const sheetHtml = cut0(html, '<section id="m-sheet"', "</section>");
  ok("C3 phone: ONE bottom sheet with a 48 px handle that toggles on a tap and carries aria-expanded (and aria-controls its body)",
     (html.match(/<section id="m-sheet"/g) || []).length === 1 && /<section id="m-sheet" data-state="peek" aria-label="This month on the map">/.test(html)
     && sheetHtml.includes('<button type="button" class="m-handle" id="m-handle" onclick="toggleSheet()" aria-controls="m-body" aria-expanded="false"')
     && sheetHtml.includes('<div class="m-body" id="m-body">'));
  ok("C3 phone: the peek is the month, the two lead figures and the conditions count; the half is the busiest routes and the conditions",
     sheetHtml.indexOf('id="m-month"') > 0 && sheetHtml.indexOf('id="m-trips"') > sheetHtml.indexOf('id="m-month"')
     && sheetHtml.indexOf('id="m-vehicles"') > sheetHtml.indexOf('id="m-trips"') && sheetHtml.indexOf('id="m-cond"') > sheetHtml.indexOf('id="m-vehicles"')
     && sheetHtml.indexOf('id="m-busiest"') > sheetHtml.indexOf('id="m-body"') && sheetHtml.indexOf('id="m-conditions"') > sheetHtml.indexOf('id="m-busiest"')
     && sheetHtml.includes(">two-way movements a day<") && sheetHtml.includes(">vehicles needed<"));
  ok("C3 phone: the full detent is the filters and layers (sheetTo('full') opens the panel as the layers sheet)",
     sheetHtml.includes(`onclick="sheetTo('full')">Filters and layers</button>`) && /if \(state === 'full'\) \{ openLayersSheet\(\); return; \}/.test(code));
  ok("C3 phone: the month chips and Play sit at the BOTTOM of the sheet (the last row), Play named and pressed-state",
     sheetHtml.lastIndexOf('class="m-chips-row"') > sheetHtml.indexOf('id="m-body"')
     && sheetHtml.includes('<button type="button" class="m-play" id="m-play" onclick="toggleTimeline()" aria-label="Play" aria-pressed="false">&#9654;</button>')
     && sheetHtml.includes('<div class="month-chips" id="m-chips" role="group" aria-label="Month"></div>'));
  ok("C3 phone: touchPitch and dragRotate are off on a phone only — at construction, and switched with the breakpoint",
     code.includes("touchPitch: !isPhoneShell(), dragRotate: !isPhoneShell() });")
     && code.includes("try { if (on) { map.touchPitch.disable(); map.dragRotate.disable(); } else { map.touchPitch.enable(); map.dragRotate.enable(); } } catch (e) {}"));
  ok("C3 phone (D14): a tap on a route opens the route card in the sheet INSTEAD of the popup and the drawer",
     /selectRoute\(rid\);\s*if\(typeof isPhoneShell==='function' && isPhoneShell\(\) && typeof openRouteCard==='function'\)\{ openRouteCard\(rid\); return; \}\s*const info=ROUTEINFO/.test(code));
  ok("C3 phone: the guide works on the sheet — every step's phone anchor exists as an id, and guideAnchor tries it first on a phone",
     ["m-peek", "m-play", "m-handle", "m-layers-btn"].every(id => html.includes(`id="${id}"`))
     && (code.match(/phone: "(m-peek|m-play|m-handle|m-layers-btn)"/g) || []).length === 4
     && /function guideAnchor\(step\)\{\s*if \(guideOnPhone\(\) && step\.phone\) \{/.test(code)
     && code.includes("function guideOnPhone(){ return typeof isPhoneShell === 'function' && isPhoneShell(); }"));
  // ---- (3) D14: the month chips replace From / To at every width ---------------------------------------------------
  ok("C3 (D14): the From / To selects and the function that filled them are gone from the page — markup and code",
     !/forecast-from|forecast-to|populateForecastMonths/.test(html));
  ok("C3 (D14): the forecast box carries the month chips (desktop) and the sheet the same chips (phone); both are .month-chips groups",
     html.includes('<div><label id="fc-chips-label">Month</label><div class="month-chips" id="fc-chips" role="group" aria-labelledby="fc-chips-label"></div></div>')
     && /document\.querySelectorAll\('\.month-chips'\)\.forEach\(box =>/.test(code));
  ok("C3 (D14): Show forecast routes, the route analysis and the detail table read the span with volume (forecastWindow), after the matrix",
     // NARROWED 12 Oct 2026 (Track C review): `|| []` (the window may be null); REVERSED: no matrix is NO window, never
     // the whole horizon (which made the bar ask for up to 60 months)
     /try \{ await ensureTimelineMatrix\(\); \} catch \(e\) \{\}\s*\n\s*let \[fromM, toM\] = forecastWindow\(\)( \|\| \[\])?;/.test(code)
     && /try \{ await ensureTimelineMatrix\(\); \} catch \(e\) \{\}\s*\n\s*const \[f, t\] = forecastWindow\(\)( \|\| \[\])?;/.test(code)
     && code.includes("return span ? [span[0], span[1]] : null;") && !code.includes("return span ? [span[0], span[1]] : [1, CONFIG.MONTH_COUNT || 60];"));
  // ---- (4) the hover card's plumbing --------------------------------------------------------------------------------
  ok("C3 hover: routes-source carries generated feature ids (generateId), so a hover can set a feature-state",
     code.includes("map.addSource('routes-source', { type: 'geojson', data: a1_data, generateId: true });")
     && (code.match(/addSource\('routes-source'/g) || []).length === 1);
  ok("C3 hover: the ONE mousemove handler drives the card (setRouteHover) from its own query, and the glow brightens the hovered leg by feature-state",
     (code.match(/map\.on\('mousemove'/g) || []).length === 1
     && code.includes("if (typeof setRouteHover === 'function') setRouteHover(features.length ? features[0] : null, e);")
     && code.includes("'line-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.85, 0.6],")
     && code.includes("map.setFeatureState({ source: 'routes-source', id: id }, { hover: true });"));
  ok("C3 hover: the card is a tooltip outside the canvas, never on a phone or a touch-only screen, and goes when the pointer leaves the map",
     html.includes('<div id="route-hover-card" role="tooltip" hidden></div>') && /#route-hover-card\{ display:none !important; \}/.test(shell)
     // NARROWED 13 Oct 2026: the same hide condition, which now also gives way over a lorry limit (pinned in the limits block)
     && code.includes("if (!f || !e || !e.point || isPhoneShell() || !canHover()\n            || (typeof limitHitAt === 'function' && limitHitAt(e.point))) { card.hidden = true; HOVER.key = ''; return; }")
     && code.includes("if (mapEl) mapEl.addEventListener('mouseleave', () => setRouteHover(null, null));"));
  // ---- (5) the deep link, the share card and the hooks ---------------------------------------------------------------
  ok("C3 link: written on change — applyFilters ends with the write; a layer box or Show forecast schedules it; a stop of playback writes it",
     /markRouteEnds\(\);\s*raiseMarks\(\);\s*if \(typeof scheduleViewWrite === 'function'\) scheduleViewWrite\(\);\s*\}/.test(code)
     // narrowed at the merge with C1: the change hook may also name the Road load / Carbon boxes (LINK_MODE_BOXES)
     && /if \(\/\^\(layer-\|restr-\)\/\.test\(id\) \|\| id === 'toggle-forecast'( \|\| LINK_MODE_BOXES\.includes\(id\))?\) scheduleViewWrite\(\);/.test(code)
     && code.includes("observeEl('tl-play', { attributes: true, attributeFilter: ['aria-pressed'] }, () => { syncPlayButtons(); if (!TL.playing) scheduleViewWrite(); });"));
  ok("C3 link: never written during Play (Safari caps replaceState); written with history.replaceState; the app's embed / v kept in the frame, stripped from the shared link",
     code.includes("if (!VIEW.ready || TL.playing) return;") && code.includes("try { history.replaceState(history.state, '', url); } catch (e) {}")
     && code.includes("['embed', 'v'].forEach(k => { if (keep.has(k)) out.set(k, keep.get(k)); });")
     && code.includes("return location.origin + location.pathname + (qs ? '?' + qs : '');"));
  ok("C3 link: read on load — initNetwork calls onNetworkReady once the network and the filters are in, which applies the link",
     /populateFilters\(\);\s*buildNodeMarkers\(\);\s*buildRouteInfo\(\);\s*applyFilters\(\);\s*if \(typeof onNetworkReady === 'function'\) onNetworkReady\(\);/.test(code)
     && /function onNetworkReady\(\) \{[\s\S]{0,300}applyViewFromUrl\(\);/.test(code));
  ok("C3 share: 'Copy link' and the share card (a dialog with the QR, the link and a polite status); the card says the link still asks for the map password",
     /onclick="openSharePanel\(\)">Link and QR code<\/button>/.test(code) && /onclick="copyViewLink\(\)">Copy link to this view<\/button>/.test(html)
     && html.includes('<div id="share-panel" role="dialog" aria-labelledby="share-title" hidden>') && html.includes('<div id="share-status" role="status" aria-live="polite"></div>')
     && html.includes("It still asks for the map password."));
  ok("C3 (D29): no PNG export — no preserveDrawingBuffer, no map canvas toDataURL, no toBlob, no download (the legend's swatch canvas is not the map)",
     !/preserveDrawingBuffer|getCanvas\(\)\.toDataURL|toBlob|\bdownload=/.test(code + html) && (code.match(/toDataURL\(/g) || []).length === 1 && code.includes("return c.toDataURL();"));
  ok("C3 QR: drawn in the page — no QR library, no new <script src>",
     (html.match(/<script src=/g) || []).length === 3 && !/qrcode|qrious|kjua/i.test(html.replace(/qrSvg|qrMatrix|share-qr|QR code|QR_M_/g, "")));
  // ---- (6) the text view and "Report a concern" ---------------------------------------------------------------------
  ok("C3 text view: an aside beside the map, named by its heading; on the desktop the map gives it its width (the map is BESIDE it, not under it)",
     html.includes('<aside id="month-text" aria-labelledby="mt-title" hidden>') && wide.includes("body.month-text-open #map{ right:420px; }")
     && /<h2 id="mt-title" tabindex="-1">This month as text<\/h2>/.test(html) && code.includes("setTimeout(() => { try { map.resize(); } catch (e) {} }, 0);"));
  ok("C3 text view: the figures are COPIED from the bar's own elements (one source), and the table's four columns are route, two-way a day, vehicles, conditions",
     /const pairs = \[\['Two-way movements a day', txt\('kpi-trips'\)\], \[txt\('kpi-vehicles-label'\), txt\('kpi-vehicles'\)\]\];/.test(code)
     && code.includes("pairs.push([txt('kpi-routes-label'), txt('kpi-routes')], [txt('kpi-co2-day-label'), txt('kpi-co2-day')], [txt('kpi-co2-total-label'), txt('kpi-co2-total')]);")
     && code.includes('<th scope="col">Route</th><th scope="col" class="num">Two-way a day</th><th scope="col" class="num">Vehicles</th><th scope="col">Conditions</th>'));
  ok("C3 text view: working days from the month's API figure, never a literal 22 in the new block",
     code.includes("const wd = kp.working_days > 0 ? kp.working_days : FORECAST_WORKING_DAYS;") && !/\b22\b/.test(newBlockCode().replace(/const QR_M_ECC = \[[^\]]*\];/, "")));   // (the QR code's EC table is not a day count)
  ok("C3 concern: no address is typed into the page — no mailto: with an address in the source, the address comes from TENANT.concern_email only",
     !/mailto:[^'"?\s]*@/.test(html) && code.includes("const a = t && typeof t.concern_email === 'string' ? t.concern_email.trim() : '';")
     && code.includes("const addr = concernAddress(TENANT);"));
  // ---- (7) the wording of everything new ---------------------------------------------------------------------------
  {
    const lits = t => (t.match(/'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`|"(?:[^"\\\n]|\\.)*"/g) || []).join(" ");
    const readable = lits(newBlockCode()) + " " + sec + " " + sheetHtml + " " + cut0(html, '<aside id="month-text"', '<div id="map"></div>')
      + " " + cut0(code, "<h3>Forecast traffic volume</h3>", "sidebar.insertAdjacentHTML");
    ok("C3 wording: nothing new a person reads says truck, real-time, live tracking, telematics, AI, optimise, predict or secure; it says lorry and two-way movements",
       readable.length > 5000 && !/truck|real-time|live tracking|telematics|optimi[sz]e|predict|\bsecure\b/i.test(readable) && !/\bAI\b/.test(readable)
       && /Lorry registration/.test(readable) && /two-way movements a day/.test(readable));
    ok("C3 wording: a team is shown by its name (teamText), never its slot id — no 'IPT' in the new block's words",
       !/IPT[1-6]/.test(lits(newBlockCode())) && (newBlockCode().match(/teamText\(/g) || []).length >= 3);
  }
}
// the new script block, and a cut helper that does not need a second index
function cut0(t, a, b) { const i = t.indexOf(a), j = t.indexOf(b, i + 1); return i >= 0 && j > i ? t.slice(i, j) : ""; }
function newBlockSrc() { return blocks.find(b => b.includes("THE INTERACTIVITY PASS (review 2.3, D14, D29) AND THE PHONE SHELL")) || ""; }
function newBlockCode() { return newBlockSrc().split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, ""); }

// ---- C3: the new block, run against a fake DOM -------------------------------------------------------------------------
{
  const nb = newBlockSrc();
  ok("C3: the new block is ONE inline script, the last on the page, after initAnalysis (outside every sandbox slice above)",
     nb.length > 20000 && blocks[blocks.length - 1] === nb && src.indexOf(nb) > src.indexOf("(function initAnalysis(){"));
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const CONFIG = { MONTH_COUNT: 60, START_YEAR: 2026, FORECAST_UNIT: 'vehicles', API_BASE: '' };
  const monthLabel = i => names[(i - 1) % 12] + ' ' + (CONFIG.START_YEAR + Math.floor((i - 1) / 12));
  const byId = {};
  const mkEl = (id, tag) => {
    const el = { id, tagName: tag || 'DIV', hidden: false, dataset: {}, style: {}, attrs: {}, innerHTML: '', textContent: '', value: '', checked: false,
      options: [], selectedIndex: 0, pressed: {}, open: false,
      setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; }, focus() {}, addEventListener() {},
      getBoundingClientRect() { return { left: 0, top: 0, width: 300, height: 100, right: 300, bottom: 100 }; },
      querySelector() { return null; },
      // chips: the buttons are read back from the markup this element was given
      querySelectorAll(sel) { const box = this; return sel === '.month-chip' ? [...box.innerHTML.matchAll(/data-month="(\d+)"/g)].map(m => ({ dataset: { month: m[1] }, setAttribute(k, v) { box.pressed[m[1]] = v; } })) : []; },
      dispatchEvent() { return true; } };
    if (id) byId[id] = el;
    return el;
  };
  for (const id of ['m-sheet', 'm-handle', 'm-layers-btn', 'm-month', 'm-trips', 'm-vehicles', 'm-cond', 'm-busiest', 'm-conditions', 'm-card', 'm-main',
                    'm-play', 'kpi-title', 'kpi-trips', 'kpi-vehicles', 'kpi-busiest', 'month-text', 'toggle-forecast', 'layers-box', 'sidebar-close']) mkEl(id);
  const chipBoxes = [mkEl('fc-chips'), mkEl('m-chips')];
  const concernSlots = [mkEl(null), mkEl(null)];
  const layerEls = [['layer-alignment', true], ['layer-chainage', false], ['layer-gates', true], ['layer-zones', true]].map(([id, on]) => { const e = mkEl(id, 'INPUT'); e.checked = on; return e; });
  const sel = (id, opts) => { const e = mkEl(id, 'SELECT'); e.options = opts.map(([value, textContent]) => ({ value, textContent })); e.value = 'ALL'; return e; };
  sel('filter-origin', [['ALL', 'All origins'], ['Brook Pit', 'Brook Pit']]); sel('filter-dest', [['ALL', 'All destinations']]);
  sel('filter-discipline', [['ALL', 'All disciplines'], ['earthworks', 'earthworks']]); sel('filter-ipt', [['ALL', 'All teams'], ['IPT2', 'Central Team']]);
  let sidebarOpen = false;
  const document = {
    getElementById: id => byId[id] || null,
    querySelectorAll: s => s === '.month-chips' ? chipBoxes : s === '.concern-slot' ? concernSlots
      : /layer-/.test(s) ? layerEls : [],
    addEventListener() {}, createElement: t => mkEl(null, t), body: { appendChild() {}, classList: { add() {}, remove() {} } }, activeElement: null,
  };
  const TL = { on: false, playing: false, month: 1, matrix: null };
  const WARN = { counts: { clash: 0, warn: 0, caution: 0, cap: 0 }, live: [], liveMonth: null };
  const KPI = { cache: {} };
  const calls = { open: 0, set: [], stop: 0, sel: [], clear: 0 };
  const TENANT = { name: 'Wolds Link (fictional)', demo_notice: 'Fictional demo scheme · nothing here is real', concern_email: null };
  const teamText = v => String(v).replace(/\bipt\s*[-_ ]?\s*([1-6])\b/gi, (m, n) => ({ 1: 'North Team', 2: 'Central Team', 3: 'South Team' }[n] || 'Team ' + n));
  const fmtN = (n, d) => (Math.round(n * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toLocaleString();
  const map = { touchPitch: { disable() {}, enable() {} }, dragRotate: { disable() {}, enable() {} }, setFeatureState() {}, getContainer: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0 }) }), resize() {} };
  const location = { origin: 'https://app.wayscope.test', pathname: '/map/', search: '', hash: '' };
  const history = { replaceState(s, t, u) { const q = u.indexOf('?'); location.search = q >= 0 ? u.slice(q) : ''; } };
  const window = { matchMedia: () => ({ matches: false, addEventListener() {} }), innerWidth: 1280, innerHeight: 800 };
  let api = null, err = '';
  try {
    api = new Function("document", "window", "TL", "KPI", "WARN", "CONFIG", "monthLabel", "map", "teamText", "TENANT", "fmtN", "fmtDist", "DU", "ROUTEINFO",
      "routePropsById", "FORECAST_WORKING_DAYS", "forecastWindow", "ensureTimelineMatrix", "openTimeline", "setTimelineMonth", "stopTimeline", "tlStartMonth",
      "applyFilters", "selectRoute", "clearSelection", "kpiFetchMonth", "sidebarIsOpen", "toggleSidebar", "closeSidebar", "isPhoneShell", "PHONE_SHELL_MQ",
      "location", "history", "navigator", "requestAnimationFrame", "MutationObserver", "setTimeout", "clearTimeout",
      nb + "\nreturn { renderMonthChips, pickMonth, chipLabel, routeHoverView, runHoverView, encodeView, decodeView, monthParam, monthFromParam, layersFromChanges, shareUrl, writeView, currentView, VIEW, "
         + "qrGfMul, qrRsDivisor, qrRsRemainder, qrFormatBits, qrVersionBits, qrMatrix, qrSvg, qrDataCodewords, qrAlignPositions, concernAddress, concernMailto, renderConcernLinks, "
         + "monthTableRows, routeFigures, condSummary, sheetTo, toggleSheet, SHEET, CHIPS, openRunCard, runCardHTML, TAP_SLOP };")(
      document, window, TL, KPI, WARN, CONFIG, monthLabel, map, teamText, TENANT, fmtN, (km) => String(km), () => 'km', {},
      () => ({}), 21, () => [9, 12], () => Promise.resolve(TL.matrix), () => { calls.open++; TL.on = true; }, m => { calls.set.push(m); TL.month = m; },
      () => { calls.stop++; TL.playing = false; }, () => 9, () => {}, r => calls.sel.push(r), () => { calls.clear++; }, () => Promise.resolve(null),
      () => sidebarOpen, () => { sidebarOpen = !sidebarOpen; }, () => { sidebarOpen = false; }, () => false, '(max-width:767px)',
      location, history, {}, () => 0, undefined, () => 0, () => {});
  } catch (e) { err = String(e && e.stack || e); }
  ok("C3: the new block runs against a fake DOM (every global it reads is one the page defines)", !!api, err.slice(0, 400));
  if (api) {
    // ---- month chips (D14) ----
    api.renderMonthChips();
    ok("C3 chips: before the matrix the chips say they are loading (both groups), never an empty row", chipBoxes.every(b => /Loading the months/.test(b.innerHTML)));
    TL.matrix = { volMonths: new Set([12, 9, 10, 11]), span: [9, 12] };
    api.renderMonthChips();
    const chipTexts = b => [...b.innerHTML.matchAll(/>([^<]+)<\/button>/g)].map(m => m[1]);
    ok("⭐ C3 chips: ONE chip per month with volume, in order, short names in one year, each named by its full month, in BOTH groups",
       chipBoxes.every(b => JSON.stringify(chipTexts(b)) === '["Sep","Oct","Nov","Dec"]') && /aria-label="Oct 2026" onclick="pickMonth\(10\)"/.test(chipBoxes[0].innerHTML)
       && (chipBoxes[1].innerHTML.match(/class="month-chip"/g) || []).length === 4, chipBoxes[0].innerHTML.slice(0, 200));
    ok("C3 chips: with no month on screen no chip is pressed", chipBoxes.every(b => Object.values(b.pressed).every(v => v === 'false')));
    api.pickMonth(10);
    ok("⭐ C3 chips: a chip with the timeline shut opens it ON that month (openTimeline with TL.month already set)", calls.open === 1 && TL.month === 10 && calls.set.length === 0);
    api.renderMonthChips();
    ok("...and that chip, and only that chip, is pressed", chipBoxes.every(b => b.pressed['10'] === 'true' && b.pressed['9'] === 'false' && b.pressed['12'] === 'false'));
    TL.playing = true; api.pickMonth(12);
    ok("C3 chips: a chip during Play stops playback and shows its month", calls.stop === 1 && calls.set.join() === '12' && TL.month === 12);
    api.pickMonth(0); api.pickMonth(61); api.pickMonth('x');
    ok("C3 chips: a month outside the horizon is ignored", calls.set.join() === '12' && calls.open === 1);
    ok("C3 chips: across a year end the chips carry the year", api.chipLabel(12, [12, 13]) === 'Dec 2026' && api.chipLabel(13, [12, 13]) === 'Jan 2027' && api.chipLabel(9, [9, 10]) === 'Sep');
    TL.matrix = { volMonths: new Set(), span: null }; chipBoxes.forEach(b => { b.dataset.sig = ''; }); api.renderMonthChips();
    ok("C3 chips: a tenant with nothing approved says so", chipBoxes.every(b => /No approved month yet/.test(b.innerHTML)));
    TL.matrix = { volMonths: new Set([9, 10, 11, 12]), span: [9, 12] };
    // ---- the hover card's words ----
    const hv = api.routeHoverView({ route_id: 'R014', origin: 'Brook Pit', dest: 'Langton Compound', ipt: 'IPT2', type: 'Inbound Highway', is_forecast: true, f_avg: 35 }, 'Oct 2026', 'vehicles');
    ok("⭐ C3 hover: the card names the route, its team by NAME and the leg, and prints the route's movements a day ONCE (one load = one two-way movement)",
       hv.title === 'Brook Pit → Langton Compound' && hv.sub === 'R014 · Central Team · laden' && hv.fig === '35 two-way movements a day · Oct 2026'
       && !/IPT/.test(JSON.stringify(hv)) && hv.hint === 'Click for the route analysis', JSON.stringify(hv));
    const hvR = api.routeHoverView({ route_id: 'R014', origin: 'A', dest: 'B', ipt: 'IPT2', type: 'Outbound Highway', is_forecast: true, f_avg: 35 }, 'Oct 2026', 'vehicles');
    ok("C3 hover: the return leg shows the SAME figure (never doubled, never 70) and says it is the empty return", hvR.fig === hv.fig && /empty return/.test(hvR.sub));
    ok("C3 hover: no month on screen asks for one; a route with nothing approved says so; tonnes say t a day",
       api.routeHoverView({ route_id: 'R1' }, null, 'vehicles').fig === 'Pick a month to see its movements a day'
       && api.routeHoverView({ route_id: 'R1', is_forecast: false }, 'Oct 2026', 'vehicles').fig === 'Nothing approved on this route · Oct 2026'
       && api.routeHoverView({ route_id: 'R1', is_forecast: true, f_avg: 120 }, 'Oct 2026', 't').fig === '120 t a day · Oct 2026'
       && api.routeHoverView({ route_id: 'R1', ipt: 'Unknown_IPT' }, null).sub === 'R1');
    // Track C review: a shared section under the pointer gets the SECTION's card, never one route's
    const rv = api.runHoverView({ id: 'S1', rl_mv: 46.27, rl_mv_text: '46', rl_routes_text: '2 routes', rl_co2_text: '3.2 t CO₂e' }, 'Oct 2026', true);
    ok("⭐ Track C review: the hover over a shared section is the section's: its two-way figure, its routes, the month, 'Click for the routes on this section'",
       rv.title === 'Shared road section' && rv.sub === '2 routes · Oct 2026' && rv.fig === '46 two-way movements a day · 3.2 t CO₂e'
       && rv.hint === 'Click for the routes on this section' && rv.hint !== 'Click for the route analysis', JSON.stringify(rv));
    ok("Track C review: ...without carbon on, no tonnes", api.runHoverView({ rl_mv_text: 'under 1', rl_routes_text: '3 routes' }, 'Oct 2026', false).fig === 'under 1 two-way movements a day');
    // ---- the deep link ----
    // Track C review: "Show forecast routes" travels as layers=forecast (a link from the forecast view opened bare)
    {
      const defsF = ['alignment', 'gates', 'zones'];
      const encF = api.encodeView({ month: null, layers: ['alignment', 'forecast', 'gates', 'zones'], filters: {} }, defsF);
      ok("⭐ Track C review link: Show forecast round-trips — encoded as layers=forecast, decoded back into the ticked set",
         encF === 'layers=forecast' && JSON.stringify(api.layersFromChanges(defsF, api.decodeView('?' + encF).layers)) === '["alignment","forecast","gates","zones"]', encF);
    }
    ok("C3 link: the month reads as YYYY-MM both ways, and a month outside the horizon or malformed is dropped",
       api.monthParam(10) === '2026-10' && api.monthParam(13) === '2027-01' && api.monthFromParam('2026-10') === 10 && api.monthFromParam('2027-1') === 13
       && api.monthFromParam('2025-12') === null && api.monthFromParam('2031-01') === null && api.monthFromParam('2026-13') === null && api.monthFromParam('oct') === null);
    const defs = ['alignment', 'gates', 'zones'];
    const enc = api.encodeView({ month: 10, layers: ['alignment', 'chainage', 'zones'], filters: { origin: 'Brook Pit', team: 'Central Team', dest: null } }, defs);
    ok("⭐ C3 link: encode — the month, the layer CHANGES against the defaults (dots, no escaping), the filters with the team's NAME",
       enc === 'month=2026-10&layers=chainage.-gates&filters=origin%3ABrook+Pit%7Cteam%3ACentral+Team', enc);
    const dec = api.decodeView('?' + enc);
    ok("⭐ C3 link: decode gives the same view back (round trip), and the layers come back as the defaults plus the changes",
       dec.month === 10 && JSON.stringify(dec.layers) === '["chainage","-gates"]' && dec.filters.origin === 'Brook Pit' && dec.filters.team === 'Central Team'
       && JSON.stringify(api.layersFromChanges(defs, dec.layers)) === '["alignment","chainage","zones"]', JSON.stringify(dec));
    ok("C3 link: the default view writes no parameters at all; a closed timeline writes no month",
       api.encodeView({ month: null, layers: defs.slice(), filters: {} }, defs) === '' && !/month=/.test(api.encodeView({ month: null, layers: ['alignment'], filters: {} }, defs)));
    const junk = api.decodeView('?month=2026-10&layers=chainage.%3Cscript%3E.-gates&filters=origin:X|evil:Y|team:|dest');
    ok("C3 link: unknown filter keys, empty values and a layer name that is not a plain key are dropped",
       JSON.stringify(junk.filters) === '{"origin":"X"}' && JSON.stringify(junk.layers) === '["chainage","-gates"]', JSON.stringify(junk));
    // the page's own state, written and shared
    api.VIEW.defaults = ['alignment', 'gates', 'zones'];
    TL.on = true; TL.month = 11; TL.playing = false;
    byId['filter-ipt'].value = 'IPT2'; byId['filter-ipt'].selectedIndex = 1;
    const cv = api.currentView();
    ok("⭐ C3 link: the current view carries the team as the option's NAME, never the slot id", cv.filters.team === 'Central Team' && cv.month === 11 && !/IPT/.test(JSON.stringify(cv.filters)));
    location.search = '?embed=1&v=123';
    api.VIEW.ready = true; api.writeView();
    ok("C3 link: written into the address with the app's embed / v kept; the shared link has neither",
       /month=2026-11/.test(location.search) && /embed=1/.test(location.search) && /v=123/.test(location.search)
       && api.shareUrl() === 'https://app.wayscope.test/map/?month=2026-11&filters=team%3ACentral+Team' && api.shareUrl(true) === 'https://app.wayscope.test/map/?month=2026-11');
    const before = location.search; TL.playing = true; TL.month = 12; api.writeView();
    ok("⭐ C3 link: nothing is written while Play runs (it would be one write a tick)", location.search === before);
    TL.playing = false;
    // ---- the QR code, decoded back by an independent reader ----
    ok("C3 QR: Reed-Solomon against two published vectors (HELLO WORLD 1-M, 01234567 1-M)",
       JSON.stringify(api.qrRsRemainder([32,91,11,120,209,114,220,77,67,64,236,17,236,17,236,17], api.qrRsDivisor(10))) === '[196,35,39,119,235,215,231,226,93,23]'
       && JSON.stringify(api.qrRsRemainder([16,32,12,86,97,128,236,17,236,17,236,17,236,17,236,17], api.qrRsDivisor(10))) === '[165,36,212,193,237,54,199,135,44,85]');
    ok("C3 QR: the format bits (M, mask 0 = 101010000010010), the version 7 bits (000111110010010100), the alignment centres and the data capacity of versions 1-10 (level M)",
       api.qrFormatBits(0).toString(2).padStart(15, '0') === '101010000010010' && api.qrVersionBits(7).toString(2).padStart(18, '0') === '000111110010010100'
       && JSON.stringify([2, 7, 10].map(api.qrAlignPositions)) === '[[6,18],[6,22,38],[6,28,50]]'
       && [1,2,3,4,5,6,7,8,9,10].map(api.qrDataCodewords).join() === '16,28,44,64,86,108,124,154,182,216');
    const texts = ['https://app.wayscope.co.uk/map/',
                   'https://app.wayscope.co.uk/map/?month=2026-10&layers=chainage.-gates&filters=origin%3AKilby+Ridge+Quarry%7Cteam%3ACentral+Team',
                   'https://app.wayscope.co.uk/map/?month=2026-10&filters=' + 'x'.repeat(150), 'Wolds Link · £ ₂'];
    const results = texts.map(t => { const q = api.qrMatrix(t); return { t, q, back: q ? qrRead(q.modules) : { err: 'null' } }; });
    ok("⭐ C3 QR: what is drawn decodes back to the text — finders, timing, format and version bits, every block's RS syndromes zero, byte mode",
       results.every(r => r.back.text === r.t && r.back.version === r.q.version), JSON.stringify(results.map(r => [r.q && r.q.version, r.back.err || r.back.text.slice(0, 40)])));
    ok("C3 QR: the versions used span 1 to 10 (a version 7+ code carries the version blocks; 10 carries a 16-bit count)",
       results[0].q.version <= 3 && results[1].q.version >= 7 && results[2].q.version === 10, results.map(r => r.q.version).join());
    ok("C3 QR: a link too long for version 10 returns null (the card then draws the month-only link)", api.qrMatrix('x'.repeat(214)) === null && api.qrSvg('x'.repeat(214)) === null);
    const svg = api.qrSvg(texts[0], 220);
    ok("C3 QR: the SVG is inline and self-contained — the quiet zone of four, crisp edges, named, no external reference",
       /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 (\d+) \1" width="220" height="220" shape-rendering="crispEdges" role="img" aria-label="QR code for the link to this view">/.test(svg)
       && Number(svg.match(/viewBox="0 0 (\d+)/)[1]) === results[0].q.size + 8 && !/href|<image|url\(/.test(svg));
    // ---- Report a concern ----
    ok("⭐ C3 concern: only a typed, plain address is used — none, a bare word, a list, a query or a header injection is refused",
       api.concernAddress({}) === null && api.concernAddress({ concern_email: null }) === null && api.concernAddress({ concern_email: 'nope' }) === null
       && api.concernAddress({ concern_email: 'a@b.example, c@d.example' }) === null && api.concernAddress({ concern_email: 'a@b.example?cc=x@y.example' }) === null
       && api.concernAddress({ concern_email: ' contact@scheme.example ' }) === 'contact@scheme.example');
    const mt = api.concernMailto('contact@scheme.example', 'Wolds Link (fictional)', 'Oct 2026', 'https://x.example/map/?month=2026-10');
    ok("C3 concern: the mailto keeps the address, and its subject and body (date, time, place, registration, the month and the link) are encoded",
       mt.startsWith('mailto:contact@scheme.example?subject=Report%20a%20concern%3A%20Wolds%20Link%20(fictional)&body=What%20happened%3A')
       && /Date%3A%0ATime%3A%0APlace/.test(mt) && /Lorry%20registration/.test(mt) && /Month%20on%20the%20map%3A%20Oct%202026/.test(mt) && /month%3D2026-10/.test(mt));
    api.renderConcernLinks();
    ok("⭐ C3 concern: the demo (no typed address) says so in every slot, as a placeholder — no link, no invented address",
       concernSlots.every(s => s.innerHTML === '<span class="concern-unset">Report a concern: no contact address has been typed for this scheme (a placeholder on the fictional demo scheme).</span>'));
    TENANT.concern_email = 'contact@scheme.example'; api.renderConcernLinks();
    ok("C3 concern: a typed address becomes a 'Report a concern by email' link", concernSlots.every(s => /^<a class="concern-link" href="mailto:contact@scheme\.example\?subject=/.test(s.innerHTML) && />Report a concern by email<\/a>$/.test(s.innerHTML)));
    TENANT.concern_email = null;
    // ---- the text view's table: the bar's rules ----
    const routes = { R1: { origin: 'Pit', dest: 'Site A', ipt: 'IPT2' }, R2: { origin: 'Pit', dest: 'Site B', ipt: 'IPT1' }, R3: { origin: 'Quarry', dest: 'Site A', ipt: 'IPT3' } };
    const lines = [
      { route_id: 'R1', vehicle_loads: 10.5, trips_per_vehicle_day: 4, discipline: 'earthworks' },
      { route_id: 'R1', vehicle_loads: 10.5, trips_per_vehicle_day: 4, discipline: 'structures' },
      { route_id: 'R2', vehicle_loads: 42, trips_per_vehicle_day: 0, discipline: 'earthworks' },
      { route_id: 'R3', vehicle_loads: 21, trips_per_vehicle_day: 3, discipline: 'earthworks' },
      { route_id: 'R9', vehicle_loads: 99, trips_per_vehicle_day: 3, discipline: 'earthworks' } ];
    const all = { o: 'ALL', d: 'ALL', disc: 'ALL', i: 'ALL' };
    const live = [{ who: 'R1', noun: 'Over a planning flag' }, { who: 'R1', noun: 'Over a planning flag' }, { who: 'Stockpile X', noun: 'Over capacity' }];
    const tb = api.monthTableRows(lines, routes, all, 21, live);
    const r1 = tb.rows.find(r => r.rid === 'R1'), r2 = tb.rows.find(r => r.rid === 'R2'), r3 = tb.rows.find(r => r.rid === 'R3');
    ok("⭐ C3 text view: two-way a day = the route's loads (fractional, summed) ÷ the month's working days from the API (21 here, never 22)",
       r1 && Math.abs(r1.twoWay - 1) < 1e-9 && Math.abs(r3.twoWay - 1) < 1e-9 && Math.abs(r2.twoWay - 2) < 1e-9, JSON.stringify(tb.rows));
    ok("⭐ C3 text view: vehicles are ceil PER LINE (R1: two lines of 0.5 a day at 4 trips = 1 + 1 = 2, not ceil(1 / 4) = 1)", r1.vehicles === 2 && r3.vehicles === 1);
    ok("C3 text view: a line with no stored road route is counted in the movements and named, never zeroed; a route the map does not draw is named, not counted",
       r2.unbaked === 1 && r2.vehicles === 0 && r2.loads === 42 && JSON.stringify(tb.undrawn) === '["R9"]' && !tb.rows.some(r => r.rid === 'R9'));
    ok("C3 text view: busiest first; each route's own conditions, once each; a site's condition is not a route's", tb.rows[0].rid === 'R2'
       && JSON.stringify(r1.conditions) === '["Over a planning flag"]' && r2.conditions.length === 0);
    const tbF = api.monthTableRows(lines, routes, { o: 'ALL', d: 'Site A', disc: 'earthworks', i: 'ALL' }, 21, []);
    ok("C3 text view: the panel's filters apply as they do to the bar (destination on the route, discipline on the LINE)",
       JSON.stringify(tbF.rows.map(r => [r.rid, r.loads])) === '[["R3",21],["R1",10.5]]', JSON.stringify(tbF.rows.map(r => [r.rid, r.loads])));
    const fig = api.routeFigures(lines, 'R1', 21);
    ok("C3 route card: the route's figures by the same rules (two lines, 1 two-way a day, 2 vehicles)", fig.lines === 2 && Math.abs(fig.twoWay - 1) < 1e-9 && fig.vehicles === 2 && fig.unbaked === 0);
    // ---- the sheet ----
    ok("C3 sheet: the conditions count is in the pill's words — a planning flag is never called a limit",
       api.condSummary({ clash: 1, warn: 6, cap: 1, caution: 0 }) === '1 over capacity · 6 route limits · 1 route over a planning flag'
       && api.condSummary({ cap: 2 }) === '2 routes over planning flags' && api.condSummary({}) === '');
    api.sheetTo('peek');
    ok("C3 sheet: at peek the handle says collapsed (aria-expanded false) and offers more", byId['m-handle'].attrs['aria-expanded'] === 'false' && byId['m-sheet'].dataset.state === 'peek'
       && byId['m-handle'].attrs['aria-label'] === 'Show the busiest routes and conditions');
    api.toggleSheet();
    ok("⭐ C3 sheet: a tap on the handle raises it to half and says so (aria-expanded true)", byId['m-sheet'].dataset.state === 'half' && byId['m-handle'].attrs['aria-expanded'] === 'true'
       && byId['m-handle'].attrs['aria-label'] === 'Show less');
    api.toggleSheet();
    ok("...and a second tap lowers it to peek again", byId['m-sheet'].dataset.state === 'peek' && byId['m-handle'].attrs['aria-expanded'] === 'false');
    api.openRunCard('S9');
    ok("⭐ browser check 12 Oct (phone): a shared section's card opens IN THE SHEET at half, with a close button, never a map popup",
       api.SHEET.card === 'run:S9' && byId['m-sheet'].dataset.state === 'half' && byId['m-card'].hidden === false && byId['m-main'].hidden === true
       && byId['m-card'].innerHTML.includes('onclick="closeRouteCard()">Close the card</button>'), byId['m-card'].innerHTML.slice(0, 300));
    ok("browser check 12 Oct (phone): ...and with no road-load month on screen it says so instead of an empty card",
       byId['m-card'].innerHTML.includes('This shared road section is not on the map for the month on screen.'));
    api.sheetTo('peek');
    ok("browser check 12 Oct (phone): lowering the sheet to peek closes the section card like a route card", api.SHEET.card === null && byId['m-card'].hidden === true && byId['m-main'].hidden === false);
    ok("browser check 12 Oct (phone): a tap looks 10 px round itself for a line", api.TAP_SLOP === 10);
    api.sheetTo('full');
    ok("C3 sheet: full opens the panel as the layers sheet; the Layers button reports it", sidebarOpen === true && api.SHEET.state === 'full'
       && byId['m-layers-btn'].attrs['aria-expanded'] === 'true' && byId['m-handle'].attrs['aria-expanded'] === 'true');
  }
}
// An independent QR reader for the pins above (ISO/IEC 18004, byte mode, level M only): it finds the function modules
// itself, reads and checks the format and version bits, unmasks, reads the codewords in the zigzag, de-interleaves the
// blocks, requires every block's syndromes S0..S(n-1) to be zero (polynomial evaluation at alpha^i, not the encoder's
// division) and parses the byte segment.
function qrRead(mod) {
  const n = mod.length, ver = (n - 17) / 4;
  if (!Number.isInteger(ver) || ver < 1 || ver > 10) return { err: 'size ' + n };
  const EXP = [], LOG = new Array(256).fill(0);
  for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11D; }
  const mul = (a, b) => (a && b) ? EXP[(LOG[a] + LOG[b]) % 255] : 0;
  // finders and timing, read off the matrix
  const finderOk = (cx, cy) => { for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) { const d = Math.max(Math.abs(dx), Math.abs(dy)); if (mod[cy + dy][cx + dx] !== (d !== 2)) return false; } return true; };
  if (!finderOk(3, 3) || !finderOk(n - 4, 3) || !finderOk(3, n - 4)) return { err: 'finder' };
  for (let i = 8; i < n - 8; i++) if (mod[6][i] !== (i % 2 === 0) || mod[i][6] !== (i % 2 === 0)) return { err: 'timing' };
  // format: both copies, the BCH code checked by brute force over the 32 valid words
  const bits1 = []; for (let i = 0; i <= 5; i++) bits1.push(mod[i][8]); bits1.push(mod[7][8], mod[8][8], mod[8][7]); for (let i = 9; i < 15; i++) bits1.push(mod[8][14 - i]);
  const bits2 = []; for (let i = 0; i < 8; i++) bits2.push(mod[8][n - 1 - i]); for (let i = 8; i < 15; i++) bits2.push(mod[n - 15 + i][8]);
  const word = b => b.reduce((a, bit, i) => a | ((bit ? 1 : 0) << i), 0);
  const w1 = word(bits1), w2 = word(bits2);
  if (w1 !== w2) return { err: 'format copies differ' };
  let fmt = null;
  for (let d = 0; d < 32; d++) { let r = d; for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >> 9) * 0x537); if ((((d << 10) | r) ^ 0x5412) === w1) fmt = d; }
  if (fmt === null) return { err: 'format bch' };
  if ((fmt >> 3) !== 0) return { err: 'level is not M' };
  const mask = fmt & 7;
  if (!mod[n - 8][8]) return { err: 'dark module' };
  // version blocks (7+), both copies, BCH(18,6)
  if (ver >= 7) {
    let vb = 0, vb2 = 0; for (let i = 0; i < 18; i++) { const a = n - 11 + i % 3, c = Math.floor(i / 3); if (mod[c][a]) vb |= 1 << i; if (mod[a][c]) vb2 |= 1 << i; }
    let r = ver; for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >> 11) * 0x1F25);
    if (vb !== vb2 || vb !== ((ver << 12) | r)) return { err: 'version bits' };
  }
  // the function modules, worked out again here
  const fn = Array.from({ length: n }, () => new Array(n).fill(false));
  const box = (x0, y0, x1, y1) => { for (let y = Math.max(0, y0); y <= Math.min(n - 1, y1); y++) for (let x = Math.max(0, x0); x <= Math.min(n - 1, x1); x++) fn[y][x] = true; };
  box(0, 0, 8, 8); box(n - 8, 0, n - 1, 8); box(0, n - 8, 8, n - 1);           // finders, separators, format
  for (let i = 0; i < n; i++) { fn[6][i] = true; fn[i][6] = true; }            // timing
  if (ver >= 2) {
    const k = Math.floor(ver / 7) + 2, last = n - 7, pos = [6];
    const step = Math.ceil((last - 6) / (k - 1) / 2) * 2;                         // the spec's table, by its rule: even steps, packed to the far end
    for (let p = last; pos.length < k; p -= step) pos.splice(1, 0, p);
    for (const ay of pos) for (const ax of pos) { if ((ax === 6 && ay === 6) || (ax === 6 && ay === last) || (ax === last && ay === 6)) continue; box(ax - 2, ay - 2, ax + 2, ay + 2); }
  }
  if (ver >= 7) { box(n - 11, 0, n - 9, 5); box(0, n - 11, 5, n - 9); }
  const M = [(x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, (x, y) => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
             (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, (x, y) => x * y % 2 + x * y % 3 === 0,
             (x, y) => (x * y % 2 + x * y % 3) % 2 === 0, (x, y) => ((x + y) % 2 + x * y % 3) % 2 === 0][mask];
  const stream = [];
  for (let right = n - 1, upward = true; right >= 1; right -= 2, upward = !upward) {
    if (right === 6) right = 5;
    for (let k = 0; k < n; k++) { const y = upward ? n - 1 - k : k; for (const x of [right, right - 1]) if (!fn[y][x]) stream.push(mod[y][x] !== M(x, y) ? 1 : 0); }
  }
  // de-interleave (level M: EC per block and block count for versions 1-10)
  const ECC = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26][ver], NB = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5][ver];
  const total = Math.floor(stream.length / 8), cw = [];
  for (let i = 0; i < total; i++) { let b = 0; for (let j = 0; j < 8; j++) b = (b << 1) | stream[i * 8 + j]; cw.push(b); }
  const nLong = total % NB, shortData = Math.floor(total / NB) - ECC;
  const blocks = Array.from({ length: NB }, (_, i) => ({ data: [], ecc: [], len: shortData + (i >= NB - nLong ? 1 : 0) }));
  let p = 0;
  for (let i = 0; i < shortData + 1; i++) for (const b of blocks) if (i < b.len) b.data.push(cw[p++]);
  for (let i = 0; i < ECC; i++) for (const b of blocks) b.ecc.push(cw[p++]);
  for (const b of blocks) {
    const c = b.data.concat(b.ecc);
    for (let i = 0; i < ECC; i++) { let s = 0; const a = EXP[i]; for (const v of c) s = mul(s, a) ^ v; if (s !== 0) return { err: 'syndrome' }; }
  }
  const data = [].concat(...blocks.map(b => b.data));
  let bit = 0; const rd = k => { let v = 0; for (let i = 0; i < k; i++) { v = (v << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1); bit++; } return v; };
  if (rd(4) !== 4) return { err: 'not byte mode' };
  const len = rd(ver < 10 ? 8 : 16), bytes = [];
  for (let i = 0; i < len; i++) bytes.push(rd(8));
  return { version: ver, mask, text: Buffer.from(bytes).toString('utf8') };
}

// ===== 12 Oct 2026 — Track C integration (claude/map-review-2): the seams between C1, C2 and C3 =====
// Each pin fails on the four builder branches taken alone: they were built side by side and never saw each other.
{
  const mm = code.slice(code.indexOf("function mapModeMonth(){"), code.indexOf("function niceStop(v){"));
  const am = code.slice(code.indexOf("function areasMonth() {"), code.indexOf("function areaTierOn(tier) {"));
  // NARROWED / REVERSED 12 Oct 2026 (Track C review): mapModeMonth reads `forecastWindow() || []`; the council areas no
  // longer take the window's first month — they read mapModeMonth itself (one rule for the three month layers)
  ok("⭐ Track C: Road load / Carbon read the Show-forecast window from forecastWindow(), and the council areas read mapModeMonth; never the removed From / To selects",
     mm.length > 0 && am.length > 0 && /const \[f, t\] = forecastWindow\(\)( \|\| \[\])?;/.test(mm) && /mapModeMonth\(\)/.test(am)
     && !/forecastWindow\(\)\[0\]/.test(am) && !/forecast-from|forecast-to/.test(mm + am));
  const af = code.slice(code.indexOf("function applyFilters()"), code.indexOf("function resetFilters()"));
  ok("Track C: applyFilters refreshes the council areas AND ends with the address-bar write (both sides kept, the write last)",
     /if \(typeof refreshAreas === 'function'\) refreshAreas\(\);[\s\S]*markRouteEnds\(\);\s*raiseMarks\(\);\s*if \(typeof scheduleViewWrite === 'function'\) scheduleViewWrite\(\);\s*\}\s*$/.test(af));
  const rmf = code.slice(code.indexOf("ensureForecastLayers(); ensureFlowLayer();"), code.indexOf("function openTimeline(){"));
  ok("Track C: each month on the playhead refreshes the council areas and then Road load / Carbon (one call each)",
     (rmf.match(/refreshAreas\(\);/g) || []).length === 1 && (rmf.match(/refreshMapModes\(\);/g) || []).length === 1
     && rmf.indexOf("refreshAreas();") < rmf.indexOf("refreshMapModes();"));
  ok("Track C: still ONE mousemove handler and ONE generateId on routes-source after the merge (no second hover path)",
     (code.match(/map\.on\('mousemove'/g) || []).length === 1 && (code.match(/generateId: true/g) || []).length === 1
     && !/promoteId/.test(code));
  ok("Track C: the two removal lists are the one list, unchanged by the merge (Road load, Carbon and the forecast layers; the council areas are their own group and stay)",
     (code.match(/\['road-load-labels','road-load-line','road-load-casing','carbon-route-labels','forecast-labels','forecast-layer','forecast-casing','forecast-flow','forecast-cap-badge'\]\.forEach/g) || []).length === 2
     && !/'area-fill','forecast/.test(code));
  // the deep link carries Road load and Carbon
  ok("⭐ Track C link: the Road load and Carbon boxes travel in &layers= (the box list names them; a change to either writes the link)",
     // NARROWED 12 Oct 2026 (Track C review): the list and the selector may also name "Show forecast routes"
     /const LINK_MODE_BOXES = \['toggle-road-load', 'toggle-carbon'(, 'toggle-forecast')?\];/.test(code)
     && /input\[type=checkbox\]\[id\^="restr-"\], #toggle-road-load, #toggle-carbon(, #toggle-forecast)?'\)\]/.test(code)
     && code.includes("|| LINK_MODE_BOXES.includes(id)) scheduleViewWrite();"));
  let lk = null;
  try { lk = new Function(/function layerKey\(id\) \{[^\n]*\}/.exec(code)[0] + "\nreturn layerKey;")(); } catch (e) {}
  ok("Track C link: their keys are short and collide with no layer box ('road-load', 'carbon'); layer- and restr- keys unchanged",
     !!lk && lk('toggle-road-load') === 'road-load' && lk('toggle-carbon') === 'carbon' && lk('layer-chainage') === 'chainage'
     && lk('restr-closures') === 'restr-closures' && !/id="layer-(road-load|carbon)"/.test(html));
  ok("Track C: the council group's tier boxes are layer- ids, so the link carries them without a change (areas-district, areas-county)",
     html.includes('id="layer-areas-district"') && html.includes('id="layer-areas-county"'));
}

// ===== 12 Oct 2026 — the wording / rules / licences review of Track C =====
// Each pin fails on f50731b (the Track C integration before the review).
{
  ok("⭐ wording: no text on the page names the removed From / To selects as something to set",
     !/From and To/.test(code) && !/set From/.test(code));
  ok("⭐ the 14 px floor: the Road load and Carbon checkbox labels (.fc-toggle is 13.5 px) and the chips' Month label (.fc-row label is 12.5 px) are 14 px",
     /\.fc-toggle\.fc-mode\{ font-size:14px; \}/.test(html) && /#fc-chips-label\{ font-size:14px; \}/.test(html)
     && html.includes('<label id="fc-chips-label">Month</label>'));
  // the phone sheet and the map's foot: Mapbox's logo and attribution carry the ONS / OS lines of a council layer
  const phoneCss = (() => { const i = html.indexOf("@media (max-width:767px){\n            #kpi-hud, #menu-toggle"); return i > 0 ? html.slice(i, html.indexOf("\n        }\n", i)) : ""; })();
  ok("⭐ licences (phone): the bottom controls (Mapbox logo, attribution with the ONS / OS lines) ride above the sheet, never under it",
     phoneCss.length > 0 && phoneCss.includes(".mapboxgl-ctrl-bottom-left, .mapboxgl-ctrl-bottom-right{ bottom:var(--m-sheet-h, 0px); }")
     && !/\.mapboxgl-ctrl-attrib[^{]*\{[^}]*display:\s*none/.test(html) && !/attributionControl:\s*false/.test(code));
  ok("licences (phone): the sheet's height is measured on every state change, at the breakpoint and on every resize of the sheet",
     /function sheetAria\(\) \{[\s\S]*?syncSheetHeight\(\);\s*\}/.test(code)
     && code.includes("syncSheetWithPanel(); renderSheet(); syncSheetHeight();")
     && code.includes("new ResizeObserver(syncSheetHeight).observe(document.getElementById('m-sheet'))"));
  const fsrc = /function syncSheetHeight\(\) \{[\s\S]*?\n    \}/.exec(code);
  const props = {};
  let phone = true;
  const sheet = { offsetHeight: 212.4 };
  const doc = { getElementById: id => id === 'm-sheet' ? sheet : null, documentElement: { style: { setProperty(k, v) { props[k] = v; } } } };
  let sync = null;
  try { sync = new Function("document", "isPhoneShell", fsrc[0] + "\nreturn syncSheetHeight;")(doc, () => phone); } catch (e) {}
  ok("⭐ licences (phone): syncSheetHeight sets --m-sheet-h to the sheet's height on a phone, and 0 above 767 px",
     !!sync && (sync(), props['--m-sheet-h'] === '212px') && (phone = false, sync(), props['--m-sheet-h'] === '0px'), JSON.stringify(props));
  // the council layer's licence lines: the area card is not where they live, the attribution and the group are (pinned at §2.2b)
  ok("licences: the council areas' source is the only place besides the group that prints the ONS / OS lines, and it is never emptied",
     (code.match(/attribution: \(AREAS\.data\.attribution \|\| \[\]\)\.join/g) || []).length === 1);
}

// ===== 12 Oct 2026 — the Track C review fixes (reviews of claude/map-review-2) =====
// Each pin fails on 25bb1b3 (Track C after its wording review).
{
  ok("⭐ Track C review: no comment or text names the removed From / To as a way to get one month ('From = To')",
     !/From = To/.test(src) && !/From and To/.test(src));
  // the deep link carries Show forecast
  let lkF = null;
  try { lkF = new Function(/function layerKey\(id\) \{[^\n]*\}/.exec(code)[0] + "\nreturn layerKey;")(); } catch (e) {}
  ok("⭐ Track C review link: 'Show forecast routes' is in the link's box list and its selector, keyed 'forecast' (no layer box has that key)",
     code.includes("const LINK_MODE_BOXES = ['toggle-road-load', 'toggle-carbon', 'toggle-forecast'];")
     && code.includes(`input[type=checkbox][id^="restr-"], #toggle-road-load, #toggle-carbon, #toggle-forecast')]`)
     && !!lkF && lkF('toggle-forecast') === 'forecast' && !/id="layer-forecast"/.test(html));
  // the hover over a shared section, and the cursor
  ok("⭐ Track C review hover: the ONE mousemove handler lets a shared section answer (features = [run]) before it drives the card, and glows no route under it",
     /const run = \(typeof roadLoadFeatureAt === 'function'\) \? roadLoadFeatureAt\(e\.point\) : null;\s*if \(run\) features = \[run\];[\s\S]{0,200}setRouteHover\(features\.length \? features\[0\] : null, e\);/.test(code)
     && code.includes("let idMatch = run ? null : (p.Route_ID || p.route_id || p.name || p.ID || p.id);")
     && /const isRun = f\.source === 'road-load-source' \|\| !!\(f\.layer && f\.layer\.id === 'road-load-line'\);\s*const v = isRun\s*\? runHoverView\(/.test(code));
  ok("⭐ Track C review cursor: a move with no route under it keeps the hand over a council area, a site, a zone or a closure (clickableAt), never a blind reset",
     code.includes("map.getCanvas().style.cursor = (typeof clickableAt === 'function' && clickableAt(e.point)) ? 'pointer' : '';")
     && /const CLICKABLE_LAYERS = \[[^\]]*'area-fill', 'area-county-fill'\];/.test(code) && /'locations'/.test((/const CLICKABLE_LAYERS = \[[^\]]*\]/.exec(code) || [""])[0])
     && !/\} else \{\s*map\.getCanvas\(\)\.style\.cursor = '';\s*if \(map\.getLayer\('global-route-hover'\)\)/.test(code));
  {
    const fa = /function roadLoadFeatureAt\(point\)\{[\s\S]*?\n    \}/.exec(code), fc = /function clickableAt\(point\)\{[\s\S]*?\n    \}/.exec(code);
    const layers = { 'road-load-line': 1, 'area-fill': 1, 'locations': 1 };
    let under = [];
    const fm = { getLayer: id => layers[id], queryRenderedFeatures: (pt, o) => under.filter(f => o.layers.includes(f.layer.id)) };
    let RF = null, CA = null;
    try { RF = new Function("map", fa[0] + "\nreturn roadLoadFeatureAt;")(fm); CA = new Function("map", "CLICKABLE_LAYERS", fc[0] + "\nreturn clickableAt;")(fm, ['area-fill', 'locations', 'zone-fill']); } catch (e) {}
    under = [{ layer: { id: 'road-load-line' }, properties: { id: 'S1' } }, { layer: { id: 'forecast-layer' }, properties: { route_id: 'R1' } }];
    const r1 = RF && RF({});
    under = [{ layer: { id: 'area-fill' } }];
    const c1 = CA && CA({});
    under = [];
    ok("Track C review: a point on road-load-line yields the RUN (not the route under it); a council area under the pointer is clickable; nothing is not",
       !!r1 && r1.properties.id === 'S1' && c1 === true && CA({}) === false && RF({}) === null);
  }
  // the carbon ramps: the comment is true, the council legend names the difference
  ok("Track C review: the carbon ramp's comment no longer calls #2071F3's family 'the plan blue'; the council legend says its stops differ from the Carbon legend's",
     !/the plan blue at five lightness steps/.test(src) && /NOT the plan blue #4A72C9/.test(src)
     && code.includes("These stops are fixed for districts (t in the month) and differ from the Carbon legend\\'s for routes and sections."));
  // forecastWindow: no matrix, no window, no burst of month reads
  {
    const fw = /function forecastWindow\(\) \{[\s\S]*?\n    \}/.exec(code), km = /function kpiMonthsOnScreen\(\) \{[\s\S]*?\n    \}/.exec(code);
    const TLx = { on: false, matrix: null };
    const box = { checked: true };
    let FW = null, KM = null;
    try {
      FW = new Function("TL", "CONFIG", fw[0] + "\nreturn forecastWindow;")(TLx, { MONTH_COUNT: 60 });
      KM = new Function("TL", "document", "forecastWindow", km[0] + "\nreturn kpiMonthsOnScreen;")(TLx, { getElementById: () => box }, () => FW());
    } catch (e) {}
    ok("⭐ Track C review: with no timeline matrix (its read failed) there is no window and Show forecast asks for NO month (was all 60)",
       !!FW && FW() === null && JSON.stringify(KM()) === "[]" && (TLx.matrix = { span: [9, 11] }, JSON.stringify(KM()) === "[9,10,11]"));
    ok("Track C review: ...and Show forecast routes says the months could not be loaded instead of reading the whole horizon",
       code.includes('"The months could not be loaded, so no forecast is shown."') && code.includes("if (!f) throw new Error('The months could not be loaded');"));
  }
  // the section ramp's maximum comes from the server
  ok("⭐ Track C review: the timeline asks forecast-matrix for sections=1 and keeps section_co2_max as sectionCo2Max",
     code.includes("'/public/forecast-matrix?from=1&to='+CONFIG.MONTH_COUNT+'&unit='+unit+'&sections=1'")
     && code.includes("const sectionCo2Max = (Number(j.section_co2_max) > 0 && !j.co2_error) ? Number(j.section_co2_max) : null;"));
  // the council layer: shapes once, figures per month, gaps named, the shared month rule
  const ab = (() => { const i = code.indexOf("    const AREAS = { cache: {}"); return i > 0 ? code.slice(i, code.indexOf("// ===== Phase 2.5a", i) > 0 ? code.indexOf("// ===== Phase 2.5a", i) : i + 40000) : ""; })();
  ok("⭐ Track C review areas: the polygons are read ONCE (/public/areas/shapes, no month roll-up); each month's figures without them (&geometry=0)",
     ab.includes("fetch(CONFIG.API_BASE + '/public/areas/shapes')") && ab.includes("'/public/areas?month=' + m + '&geometry=0'")
     && /if \(!AREAS\.shapes\) \{[\s\S]{0,200}fetchAreaShapes\(\)/.test(ab));
  {
    const fj = /function areaJoin\(shapes, figs\) \{[\s\S]*?\n    \}/.exec(ab), ft = /function areaFigureText\(a, mode, when\) \{[\s\S]*?\n    \}/.exec(ab);
    const ff = /function areaFeatures\(payload, mode, off, when\) \{[\s\S]*?\n    \}/.exec(ab), fcard = /function areaCardHTML\(a, payload, when\) \{[\s\S]*?\n    \}/.exec(ab);
    let J = null, T = null, F = null, C = null;
    try {
      J = new Function(fj[0] + "\nreturn areaJoin;")();
      T = new Function(ft[0] + "\nreturn areaFigureText;")();
      F = new Function("areaFigureText", ff[0] + "\nreturn areaFeatures;")(T);
      C = new Function("AREAS", fcard[0] + "\nreturn areaCardHTML;")({ mode: 'movements' });
    } catch (e) {}
    const shapes = { areas: [{ area_id: "A", name: "Alpha", tier: "district", geometry: { type: "Polygon", coordinates: [] }, label_point: [0, 0] },
                             { area_id: "B", name: "Beta", tier: "district", geometry: { type: "Polygon", coordinates: [] } }], attribution: ["L1"] };
    const figs = { areas: [{ area_id: "A", movements_per_day: 12, co2_t: 3, routes: ["R1"], co2_routes_unbaked: ["R2"], edge_routes: ["R3"], return_only_routes: [] },
                           { area_id: "B", movements_per_day: 0, co2_t: 0, routes: [], return_only_routes: [] }],
                   routes_not_clipped: ["R4", "R5"], notes: ["2 route(s) with volume have no clipped road route yet"], totals: { routes_with_volume: 5 } };
    const jd = J && J(shapes, figs), jn = J && J(shapes, null);
    ok("⭐ Track C review areas: the join keeps the polygons and adds the month's figures by area_id; with no month every area is 'no figure'",
       !!jd && jd.areas[0].geometry && jd.areas[0].movements_per_day === 12 && jd.areas[0].unclipped === 2 && jd.attribution[0] === "L1"
       && jd.notes[0].startsWith("2 route(s)") && jn.areas.every(a => a.nofig) && jn.areas[0].geometry);
    const fcD = F && F(jd, "movements", new Set(), "Oct 2026"), fcN = F && F(jn, "movements", new Set(), "");
    ok("⭐ Track C review areas: a district with routes not clipped yet is 'no figure yet' and hatched (v = -1), never 'no approved route'; a figure stays a figure",
       !!fcD && fcD.features.find(f => f.properties.area_id === "B").properties.v === -1
       && /BETA\nno figure yet/.test(fcD.features.find(f => f.properties.area_id === "B").properties.label)
       && fcD.features.find(f => f.properties.area_id === "A").properties.v === 12 && !/no approved route/.test(JSON.stringify(fcD)));
    ok("Track C review areas: with no month on screen no figure is drawn (v = -2, the name alone) — not the first month of a span",
       !!fcN && fcN.features.every(f => f.properties.v === -2) && fcN.features[0].properties.label === "ALPHA" && T(jn.areas[0], "movements", "") === "—");
    const cd = C && C(jd.areas[0], jd, "Oct 2026");
    ok("⭐ Track C review areas: the card names what a partial figure leaves out — 'excludes 1 route with no carbon figure', the edge route, the routes not clipped",
       !!cd && cd.includes("excludes 1 route with no carbon figure") && cd.includes("1 more only cross its edge (under 200 m inside)")
       && cd.includes("2 routes with volume not clipped yet"), (cd || "").slice(0, 300));
    ok("Track C review areas: ...and with no month the card says to pick one, with no zero", C && /Shows one month: press Play or pick a month\./.test(C(jn.areas[0], jn, "")) && !/<b>0<\/b>/.test(C(jn.areas[0], jn, "")));
  }
  ok("⭐ Track C review areas: the server's notes are printed in the group (a gap reads as a gap); a failed read says so",
     /<div class="area-note" id="area-notes"><\/div>/.test(html) && ab.includes("if (nt) nt.textContent = AREAS.error || (noMonth ? '' : (j.notes || []).join(' '));"));
  ok("Track C review areas: the hatch is a layer of its own over the neutral (v = -1), its image re-added after a basemap switch, and it toggles with the districts",
     /id: 'area-nofig', type: 'fill', source: 'areas-source',\s*filter: \['all', \['==', \['get', 'tier'\], 'district'\], \['!', \['get', 'off'\]\], \['==', \['get', 'v'\], -1\]\],/.test(ab)
     && ab.includes("'fill-pattern': 'area-hatch'") && ab.includes("if (map.hasImage && !map.hasImage('area-hatch')) map.addImage('area-hatch', areaHatchImage());")
     && ab.includes("const AREA_LAYERS = ['area-fill', 'area-nofig', 'area-outline', 'area-label'];"));
  ok("Track C review areas: with no month the fill is off (outlines only) and the legend says to pick a month; a tick with no month opens the timeline",
     // NARROWED 12 Oct 2026 (night): the fill's opacity is AREA_FILL_OPACITY (0.8, districts as blocks), still 0 with no month
     ab.includes("map.setPaintProperty('area-fill', 'fill-opacity', noMonth ? 0 : AREA_FILL_OPACITY);") && ab.includes("'fill-opacity': AREAS.month ? AREA_FILL_OPACITY : 0")
     && ab.includes("lg.innerHTML = noMonth ? '<div class=\"area-note\">Shows one month: press Play or pick a month.</div>'")
     && /if \(on && !areasMonth\(\) && typeof TL !== 'undefined' && !TL\.on && typeof openTimeline === 'function'\) openTimeline\(\);/.test(ab));
  // a phone on its side
  ok("Track C review phone: a short landscape phone (767 px or less wide, 480 px or less tall) folds the chips row into the half state and puts the figures inline",
     (() => { const i = html.indexOf("@media (max-height:480px) and (max-width:767px){"); const b = i > 0 ? html.slice(i, html.indexOf("\n        }\n", i)) : "";
              return b.includes('#m-sheet[data-state="peek"] .m-chips-row{ display:none; }') && b.includes(".m-fig b{ display:inline; font-size:20px;"); })());
}

// ===== 12 Oct 2026 (evening) — the M3 timeline bar (review §2.4, mockup 3; the user: "build full m3 bar") ==============
// Seen live on 12 Oct before this: the "Full horizon" tick box changed nothing on screen and Play stopped on October after
// ~6 s with nothing visible saying why. The bar is now mockup 3: row 1, the loop sentence over a bracket, the rail of every
// month (shaded volume, closure triangle, over-capacity dot; click / drag), the years, the keys and the legend; the pause
// message; "Pause on clash"; the "Plan months / Full horizon" pair; the seconds a month on the speed; wall mode.
{
  const barHtml = (() => { const i = html.indexOf('<div id="timeline-bar"'); return i > 0 ? html.slice(i, html.indexOf('<div id="route-drawer">', i)) : ""; })();
  // REVERSED 12 Oct 2026 (night, the user: remove "290 two-way movements a day · 18 routes · 21.1 t CO₂e a day" from the bar):
  // no tl-figs in row 1; the Horizon button (tl-more) sits between the speed and Wall mode
  const order = ['class="tl-row1"', 'id="tl-label"', 'id="tl-pause-clash"', 'id="tl-seg-plan"', 'id="tl-speed"', 'id="tl-more"', 'id="tl-wall"',
                 'class="tl-close"', 'id="tl-looplbl"', 'id="tl-loop"', 'id="tl-rail"', 'id="tl-playhead"', 'id="tl-range"', 'id="tl-years"', 'class="tl-hints"', 'id="tl-live"'];
  const pos = order.map(k => barHtml.indexOf(k));
  ok("⭐ M3: the bar holds, in order, row 1 (month, Pause on clash, Plan months / Full horizon, speed, Horizon, Wall mode, close), the loop sentence, the bracket, the rail, the playhead, the month slider, the years, the keys, the announcer",
     pos.every(p => p > 0) && pos.every((p, i) => i === 0 || p > pos[i - 1]), JSON.stringify(pos));
  // 12 Oct 2026 (night, the user: "horizon opens automatically - minimal should show first"; "the bar takes up too much space")
  ok("⭐ minimal first: the bar ships with class tl-compact, every openTimeline starts minimal, and 'Horizon' toggles the full view (aria-expanded)",
     barHtml.includes('<div id="timeline-bar" class="tl-compact" role="group"')
     && barHtml.includes('<button type="button" class="tl-ghost" id="tl-more" aria-expanded="false" onclick="setTimelineExpanded(!TL.expanded)"')
     && code.includes("function openTimeline(){\n        TL.on=true;\n        setTimelineExpanded(false);")
     && code.includes("if(bar) bar.classList.toggle('tl-compact', !TL.expanded);")
     && code.includes("b.setAttribute('aria-expanded', String(TL.expanded)); b.textContent = TL.expanded ? 'Minimal ▾' : 'Horizon ▴';")
     && code.includes("expanded:false };"));
  ok("⭐ minimal first: the compact bar hides the switch, the pair, Wall mode, the loop sentence and bracket, the years and the keys, keeps a 12 px month strip — never in wall mode",
     /body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-sw, body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-seg,\s*body:not\(\.wall-mode\) #timeline-bar\.tl-compact #tl-wall, body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-looplbl,\s*body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-loop, body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-years,\s*body:not\(\.wall-mode\) #timeline-bar\.tl-compact \.tl-hints\{ display:none; \}/.test(html)
     && html.includes("body:not(.wall-mode) #timeline-bar.tl-compact .tl-rail{ height:12px; }")
     && !/#timeline-bar\.tl-compact \.tl-rail\{ display:none/.test(html)
     && !/#timeline-bar\.tl-compact[^{]*(#tl-play|#tl-speed|\.tl-close|#tl-more)[^{]*\{ display:none/.test(html));
  ok("⭐ the figures line is gone from the bar (markup, CSS); wall mode keeps its own figures (syncTlFigs tolerates no tl-figs)",
     !barHtml.includes('id="tl-figs"') && !/#tl-figs\{/.test(html)
     && code.includes("if (figs && figs.textContent !== line) figs.textContent = line;")
     && code.includes("if (wf && wf.textContent !== line) wf.textContent = line;"));
  ok("M3: the rail's legend names its three marks; the keys are Space, the two arrows and Esc",
     barHtml.includes('<i class="sq"></i>Approved volume') && barHtml.includes('<i class="tri"></i>Closure affecting a route') && barHtml.includes('<i class="dot"></i>Over capacity')
     && barHtml.includes('<kbd>Space</kbd> play / pause') && barHtml.includes('<kbd>←</kbd><kbd>→</kbd> one month') && barHtml.includes('<kbd>Esc</kbd> close'));
  ok("M3: Pause on clash is a named switch (role=switch, on by default) wired to setPauseOnClash; the speed options say the seconds a month",
     /<input type="checkbox" id="tl-pause-clash" role="switch" checked onchange="setPauseOnClash\(this\.checked\)">/.test(barHtml) && barHtml.includes(">Pause on clash</label>")
     && barHtml.includes('<option value="0.25">¼× · 3 s a month</option>') && barHtml.includes('<option value="4">4× · 0.2 s a month</option>'));
  ok("M3: the rail and its marks are hidden from a screen reader; the month slider stays as the keyboard's and the reader's control",
     /<div class="tl-rail" id="tl-rail" aria-hidden="true"/.test(barHtml) && /<div class="tl-years" id="tl-years" aria-hidden="true">/.test(barHtml)
     && /#timeline-bar \.tl-railwrap input\[type=range\]\{ position:absolute; width:1px; height:1px;[^}]*clip:rect\(0,0,0,0\);/.test(html));
  // the switch, stored per browser, and read by the pause
  ok("⭐ M3: the switch is remembered in this browser (modus_tl_pause) and the clash pause happens only while it is on; wall mode dwells instead",
     code.includes("try { if(localStorage.getItem('modus_tl_pause') === '0') TL.pauseOnClash = false; } catch(e){}")
     && code.includes("try { localStorage.setItem('modus_tl_pause', TL.pauseOnClash ? '1' : '0'); } catch(e){}")
     && /if \(TL\.playing && TL\.wall && TL\.ticked === month && live\.some\(i => i\.lvl === 'clash'\)\) \{ if \(typeof wallDwell === 'function'\) wallDwell\(month\); \}\s*else if \(TL\.playing && TL\.pauseOnClash !== false/.test(code));
  ok("⭐ M3: the pause says why — the message is shown by the pause and hidden by Play, by closing the bar and by any other month",
     /if \(typeof showClashToast === 'function'\) showClashToast\(month, live\.filter\(i => i\.lvl === 'clash'\)\);/.test(code)
     && /TL\.ticked = null; TL\.startedOn = TL\.month;\s*if\(typeof hideClashToast === 'function'\) hideClashToast\(\);/.test(code)
     && /renderTimelineWarnings\(null\);[^\n]*\n\s*if\(typeof hideClashToast === 'function'\) hideClashToast\(\);/.test(code)
     && code.includes("if(typeof TOAST !== 'undefined' && TOAST.month !== m) hideClashToast();")
     && /<div id="tl-toast" role="status" hidden>/.test(html) && html.includes('<button type="button" class="tl-act" onclick="startTimeline()">▶ Resume</button>')
     && html.includes('onclick="stopPausingOnClash()">Stop pausing on clashes</button>')
     && /function stopPausingOnClash\(\)\{ setPauseOnClash\(false\); startTimeline\(\); \}/.test(code));
  ok("⭐ M3: moving the month by hand (the slider, the step buttons, a month chip, the rail) re-arms the once-per-loop pause",
     /function onTimelineScrub\(v\)\{ stopTimeline\(\); TL\.clashPaused = false; setTimelineMonth/.test(code) && /function stepTimeline\(delta\)\{\s*stopTimeline\(\); TL\.clashPaused = false;/.test(code)
     && /TL\.month = m; TL\.clashPaused = false;\s*if \(!TL\.on\) openTimeline\(\); else setTimelineMonth\(m\);/.test(code)
     && code.includes("RAIL.drag = true; stopTimeline(); TL.clashPaused = false;"));
  ok("M3: Esc on the bar closes it (the keys row says so); wall mode has its own Esc",
     code.includes("else if(e.key === 'Escape' && inBar && !TL.wall){ e.preventDefault(); closeTimeline(); }")
     && code.includes("if (TL.wall && e.key === 'Escape') { e.preventDefault(); exitWallMode(); }"));
  // wall mode
  ok("⭐ M3 wall mode: the bar's button and ?wall=1 open it; the address keeps wall=1 while it is on; leaving drops it",
     html.includes('<button type="button" class="tl-ghost" id="tl-wall" onclick="enterWallMode()"')
     && code.includes("if (new URLSearchParams(location.search).get('wall') === '1' && typeof enterWallMode === 'function') enterWallMode();")
     && code.includes("if (TL.wall) out.set('wall', '1');") && /if \(q\.has\('wall'\)\) \{ q\.delete\('wall'\);/.test(code));
  ok("⭐ M3 wall mode: chrome off — the panel, the figures bar, the conditions, the pause message, the guide, row 1 and the keys are hidden; the map takes the width",
     ["#main-sidebar", "#menu-toggle", "#kpi-hud", "#tl-warnings", "#tl-toast", "#guide-btn", "#route-drawer", ".custom-map-widget", "#timeline-bar .tl-row1", "#timeline-bar .tl-hints", ".guide-strip"]
       .every(sel => html.includes("body.wall-mode " + sel))
     && html.includes("body.wall-mode #map{ left:0 !important; right:0 !important; transition:none !important; }")
     && /body\.wall-mode #wall-hud \.m\{ font-size:64px;/.test(html));
  ok("M3 wall mode: it dwells WALL_DWELL_MS = 3 s on a red month through a hold in tickTimeline (no third setInterval); the phone shell is left alone",
     code.includes("const WALL_DWELL_MS = 3000;") && code.includes("if(TL.holdUntil && Date.now() < TL.holdUntil) return;")
     && (code.match(/setInterval\(tickTimeline/g) || []).length === 2
     && /function enterWallMode\(\)\{\s*if \(typeof isPhoneShell === 'function' && isPhoneShell\(\)\) return;/.test(code));
  // layout
  ok("⭐ M3: from 1024 px the bar spans the map (324 px with the panel, 24 px without, 24 px from the right; beside the text view too)",
     html.includes('#timeline-bar[role="group"]{ left:324px; right:24px; transform:none; max-width:none; }')
     && html.includes('body.sidebar-closed #timeline-bar[role="group"]{ left:24px; }')
     && html.includes('body.month-text-open #timeline-bar[role="group"]{ left:324px; right:444px; }'));
  ok("M3: the conditions panel stops above the taller bar and its rows never squash; the pause message sits above the bar at its left",
     html.includes("body.timeline-on #tl-warnings{ max-height:min(60vh, 520px, calc(100vh - 130px - var(--tl-foot, 0px))); }")
     && html.includes("body.timeline-on #tl-warnings > *{ flex:0 0 auto; }")
     && /#tl-toast\{ position:absolute; z-index:26; left:324px; bottom:var\(--tl-foot, 200px\);/.test(html));
  ok("⭐ M3: the playhead is .tl-playhead — the conditions panel's .tl-head is its own (a shared name squashed the panel's heading, seen in the browser)",
     (html.match(/\.tl-head\{/g) || []).length === 1 && html.includes('<div class="tl-playhead" id="tl-playhead" aria-hidden="true"></div>')
     && !/body\.wall-mode \.tl-head/.test(html));
  ok("M3: the phone shell hides the pause message and wall mode inside its ONE 767 px block (the sheet carries the month and Play)",
     html.includes("            #tl-toast, #wall-hud, #wall-hint{ display:none !important; }   /* M3 (12 Oct evening): the sheet carries the month and Play */"));
  {
    const a = html.indexOf("the M3 bar (review §2.4, mockup 3"), b = html.indexOf("===== 12 Oct 2026 — the interactivity pass");
    const css = a > 0 && b > a ? html.slice(a, b) : "";
    const sizes = [...css.matchAll(/font-size:(\d+(?:\.\d+)?)px/g), ...css.matchAll(/font:(?:\d+ )?(\d+(?:\.\d+)?)px/g)].map(m => Number(m[1]));
    ok("M3: every font size in the M3 CSS is 14 px or more (the 14 px floor; the mockup used 11-13)", css.length > 2000 && sizes.length > 10 && sizes.every(n => n >= 14), JSON.stringify(sizes));
  }

  // ---- the M3 functions against a fake page --------------------------------------------------------------------
  const mA = src.indexOf("// ===== 12 Oct 2026 (evening) — the M3 bar: the rail, the figures line");
  const mB = src.indexOf("(function initAnalysis", mA);
  ok("M3: the bar's functions are one block, after the conditions code and before initAnalysis", mA > 0 && mB > mA);
  if (mA > 0 && mB > mA) {
    const els = {};
    const mk = id => (els[id] = { id, style: {}, innerHTML: "", textContent: "", hidden: true, children: [], scrollHeight: 18, attrs: {},
      setAttribute(k, v) { this.attrs[k] = String(v); }, querySelector() { return null; },
      classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); }, toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); } } });
    ["tl-rail", "tl-years", "tl-loop", "tl-looplbl", "tl-playhead", "tl-figs", "wall-month", "wall-figs", "wall-hint-text", "wall-hud", "wall-hint",
     "tl-toast", "tl-toast-body", "tl-toast-show", "kpi-trips", "kpi-routes", "kpi-co2-day", "kpi-title", "kpi-hud", "timeline-bar"].forEach(mk);
    const body = { classList: mk("body").classList };
    const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const CONFIG = { MONTH_COUNT: 60, START_YEAR: 2026 };
    const monthLabel = i => names[(i - 1) % 12] + ' ' + (CONFIG.START_YEAR + Math.floor((i - 1) / 12));
    const TL = { on: true, month: 10, full: false, wall: false, playing: false, matrix: null, figsFallback: "" };
    const WARN = { piles: null, restr: null };
    const calls = { start: 0, stop: 0, replace: [], shown: [] };
    const document = { getElementById: id => els[id] || null, body, addEventListener() {} };
    const window = { addEventListener() {} };
    const location = { search: "?month=2026-10&wall=1", pathname: "/map/", hash: "" };
    const history = { state: null, replaceState(s, t, u) { calls.replace.push(u); } };
    let phone = false;
    const f = new Function("document", "window", "location", "history", "CONFIG", "TL", "WARN", "monthLabel", "tlLoopBounds", "monthHasVolume", "hitInMonth",
      "warnRestrictions", "warnPiles", "showCondition", "startTimeline", "stopTimeline", "setTimelineMonth", "syncTimelineFoot", "positionWarnStack",
      "map", "scheduleViewWrite", "isPhoneShell", "getComputedStyle", "setTimeout", "monthLong",
      src.slice(mA, mB) + "\nreturn { monthRangeText, countWord, tlRailMarks, renderTlRail, renderTlLoop, syncTlRail, syncTlFigs, showClashToast, hideClashToast, wallDwell, enterWallMode, exitWallMode, TOAST, WALL_DWELL_MS };");
    let M = null, err = "";
    try {
      M = f(document, window, location, history, CONFIG, TL, WARN, monthLabel,
            () => (TL.full || !(TL.matrix && TL.matrix.span)) ? [1, 60] : TL.matrix.span,
            m => !!(TL.matrix && TL.matrix.volMonths.has(m)),
            (h, m) => m === 10,
            () => new Promise(() => {}), () => new Promise(() => {}),
            (k, id) => calls.shown.push(k + ":" + id), () => { calls.start++; TL.playing = true; }, () => { calls.stop++; TL.playing = false; },
            () => {}, () => {}, () => {}, { resize() {} }, () => {}, () => phone, () => ({ lineHeight: "18px" }), () => 0,
            i => ['January','February','March','April','May','June','July','August','September','October','November','December'][(i - 1) % 12] + ' ' + (2026 + Math.floor((i - 1) / 12)));
    } catch (e) { err = e.stack || e.message; }
    ok("⭐ M3: the bar's block runs against a fake page", !!M, err);
    if (M) {
      ok("M3: month ranges read 'Sep to Dec 2026', 'Nov 2026 to Feb 2027' across a year, 'Sep – Dec 2026' for wall mode",
         M.monthRangeText(9, 12) === "Sep to Dec 2026" && M.monthRangeText(11, 14) === "Nov 2026 to Feb 2027" && M.monthRangeText(9, 12, ' – ') === "Sep – Dec 2026"
         && M.monthRangeText(10, 10) === "Oct 2026" && M.countWord(4) === "four" && M.countWord(24) === "24");
      // the matrix: R1 carries Sep-Dec, R2 only Sep; a closure in force only in October (the fake hitInMonth) on BOTH
      TL.matrix = { byRoute: { r1: { route_id: "R1", monthly: { "9": 5, "10": 5, "11": 5, "12": 5 } }, r2: { route_id: "R2", monthly: { "9": 3, "10": 0 } } },
                    volMonths: new Set([9, 10, 11, 12]), span: [9, 12] };
      WARN.restr = { R1: { hits: [{ from: "2026-10-16" }] }, R2: { hits: [{ from: "2026-10-16" }] } };
      WARN.piles = [{ months: { "10": { over: true }, "11": { over: true }, "12": { over: false } } }, { months: { "9": { over: false } } }];
      const mk1 = M.tlRailMarks();
      ok("⭐ M3 rail marks: a closure triangle only where the closure is in force on a route carrying volume that month; a red dot where a stockpile is recorded over",
         JSON.stringify([...mk1.cl]) === "[10]" && JSON.stringify([...mk1.oc].sort()) === "[10,11]", JSON.stringify([[...mk1.cl], [...mk1.oc]]));
      WARN.restr = { R2: { hits: [{ from: "2026-10-16" }] } };
      ok("M3 rail marks: ...and none for a closure on a route with nothing in that month (R2 carries 0 in October)", M.tlRailMarks().cl.size === 0);
      WARN.restr = { R1: { hits: [{ from: "2026-10-16" }] } };
      M.renderTlRail();
      const cells = (els["tl-rail"].innerHTML.match(/<i /g) || []).length;
      ok("⭐ M3 rail: one cell per month (60), a year mark each January, Sep-Dec shaded, October with all three marks",
         cells === 60 && els["tl-rail"].innerHTML.startsWith('<i data-m="1" class="yr"></i>') && els["tl-rail"].innerHTML.includes('<i data-m="13" class="yr"></i>')
         && els["tl-rail"].innerHTML.includes('<i data-m="9" class="vol"></i>') && els["tl-rail"].innerHTML.includes('<i data-m="10" class="vol cl oc"></i>')
         && els["tl-rail"].innerHTML.includes('<i data-m="11" class="vol oc"></i>') && els["tl-rail"].innerHTML.includes('<i data-m="12" class="vol"></i>')
         && els["tl-years"].innerHTML === "<span>2026</span><span>2027</span><span>2028</span><span>2029</span><span>2030</span>", cells);
      ok("⭐ M3 loop: the bracket covers Sep-Dec (from 13.3 % for 6.7 %) and the sentence names them, the 56 others shown, not played",
         Math.abs(parseFloat(els["tl-loop"].style.left) - 13.333) < 0.01 && Math.abs(parseFloat(els["tl-loop"].style.width) - 6.667) < 0.01
         && els["tl-looplbl"].innerHTML === "<b>Play loops over these four months</b> — Sep to Dec 2026, the ones with approved volume. The other 56 are shown, not played.",
         els["tl-looplbl"].innerHTML);
      TL.full = true; M.renderTlLoop();
      ok("⭐ M3 loop: Full horizon brackets all 60 and says how many of them have nothing approved",
         els["tl-loop"].style.width === "100%" && els["tl-looplbl"].innerHTML === "<b>Play loops over all 60 months</b> — Jan 2026 to Dec 2030, including the 56 with nothing approved.");
      TL.full = false; TL.wall = true; M.renderTlLoop();
      ok("M3 loop: wall mode prints just the range, and its hint says it dwells instead of pausing",
         els["tl-looplbl"].innerHTML === "<b>Sep – Dec 2026</b>" && els["wall-hint-text"].innerHTML === "Wall mode · loops Sep – Dec 2026<br>dwells 3 s on a clash month instead of pausing");
      TL.wall = false;
      const keepM = TL.matrix; TL.matrix = { byRoute: {}, volMonths: new Set(), span: null }; M.renderTlLoop();
      ok("M3 loop: a tenant with nothing approved is told so (no bracket over nothing)", els["tl-looplbl"].innerHTML.startsWith("<b>Nothing approved yet</b>"));
      TL.matrix = keepM; M.renderTlLoop();
      // the figures line
      els["kpi-trips"].textContent = "303"; els["kpi-routes"].textContent = "18"; els["kpi-co2-day"].textContent = "21.9 t"; els["kpi-title"].textContent = "Oct 2026Approved plan · forecast";
      TL.month = 10; TL.figsFallback = "18 routes · 6664 trips this month"; M.syncTlFigs();
      ok("⭐ M3 figures: the line under the month copies the figures bar — '303 two-way movements a day · 18 routes · 21.9 t CO₂e a day'",
         els["tl-figs"].textContent === "303 two-way movements a day · 18 routes · 21.9 t CO₂e a day", els["tl-figs"].textContent);
      els["kpi-title"].textContent = "Sep 2026 · loading figures"; M.syncTlFigs();
      ok("M3 figures: ...never another month's figures: until the bar reaches this month the line is the month's routes and trips",
         els["tl-figs"].textContent === "18 routes · 6664 trips this month");
      TL.month = 20; M.syncTlFigs();
      ok("M3 figures: a month with nothing approved says so", els["tl-figs"].textContent === "Nothing approved this month");
      TL.month = 10; els["kpi-title"].textContent = "Oct 2026 · nothing approved"; M.syncTlFigs();
      ok("M3 figures: the figures bar finding nothing in a month with volume (the filters, no stored route) reads 'Nothing approved in this view'",
         els["tl-figs"].textContent === "Nothing approved in this view");
      els["kpi-title"].textContent = "Oct 2026Approved plan"; els["kpi-routes"].textContent = "1"; els["kpi-co2-day"].textContent = "—"; M.syncTlFigs();
      ok("M3 figures: one route is '1 route'; a carbon dash is left out, never printed as a figure",
         els["tl-figs"].textContent === "303 two-way movements a day · 1 route" && els["wall-figs"].textContent === els["tl-figs"].textContent && els["wall-month"].textContent === "October 2026");
      // the pause message
      M.showClashToast(10, [{ noun: "Over capacity", what: "Stockpile <Tilton> 40,510 t", kind: "s", id: "N7" }]);
      ok("⭐ M3 pause message: names the condition (escaped), shows itself, and its Show on map goes to that condition",
         els["tl-toast"].hidden === false && els["tl-toast-body"].innerHTML === "<b>Over capacity</b> — Stockpile &lt;Tilton> 40,510 t" && M.TOAST.month === 10
         && (els["tl-toast-show"].onclick(), calls.shown[0] === "s:N7"));
      M.hideClashToast();
      ok("M3 pause message: hidden again, and it belongs to no month", els["tl-toast"].hidden === true && M.TOAST.month === null);
      TL.wall = true; M.showClashToast(10, [{ noun: "Over capacity", what: "x", kind: "s", id: "N7" }]);
      ok("M3 pause message: never in wall mode", els["tl-toast"].hidden === true);
      TL.wall = false;
      // wall mode
      const t0 = Date.now(); M.wallDwell(10); const h1 = TL.holdUntil; M.wallDwell(10); const h2 = TL.holdUntil;
      ok("⭐ M3 wall mode: a red month holds Play for 3 s; the second build of the same month does not stretch the hold",
         h1 >= t0 + M.WALL_DWELL_MS && h1 <= Date.now() + M.WALL_DWELL_MS && h2 === h1);
      phone = true; M.enterWallMode();
      ok("M3 wall mode: not on the phone shell (the sheet stays)", TL.wall === false && calls.start === 0);
      phone = false; M.enterWallMode();
      ok("⭐ M3 wall mode: entering sets the body class, starts Play and shows the big month", TL.wall === true && body.classList.contains("wall-mode") && calls.start === 1 && els["wall-hud"].hidden === false);
      M.exitWallMode();
      ok("⭐ M3 wall mode: leaving stops Play, drops the class and takes wall=1 out of the address (the month stays)",
         TL.wall === false && !body.classList.contains("wall-mode") && calls.stop === 1 && calls.replace[0] === "/map/?month=2026-10" && els["wall-hud"].hidden === true);
    }
  }
}

// ---- 13 Oct 2026: LORRY LIMITS (weight, height, width, axle) from OpenStreetMap and HERE (/api/public/limits) --------
{
  const SEC_A = "// ===== 13 Oct 2026: LORRY LIMITS", SEC_B = "// ===== end of lorry limits =====";
  const sec = cut0(src, SEC_A, SEC_B);
  const secCode = sec.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  const grpHtml = cut0(html, '<div class="control-group" id="limits-group" hidden>', '<!-- 12 Oct 2026 (mockup 7): on a phone the sheet ends');
  ok("limits: the section is in the page, in the FIRST script block (with style.load and the restrictions)",
     sec.length > 2000 && blocks[0].includes(SEC_A) && blocks[0].includes(SEC_B));
  ok("⭐ limits panel: a 'Lorry limits' group, hidden until the endpoint answers, right after the closures group",
     grpHtml.includes("<h3>Lorry limits</h3>")
     && html.indexOf('id="restrictions-group"') < html.indexOf('id="limits-group"')
     && html.indexOf('id="limits-group"') < html.indexOf('<div class="m-done">'));
  ok("⭐ limits panel: three boxes Weight · Height · Width, layer-limit-*, OFF by default, each with its count",
     ['weight', 'height', 'width'].every(k => new RegExp('<input type="checkbox" id="layer-limit-' + k + '" onchange="toggleLimits\\(\\)">').test(grpHtml)
                                          && grpHtml.includes('id="limit-count-' + k + '"'))
     && !/id="layer-limit-[a-z]+"[^>]*checked/.test(grpHtml)
     && /> Weight </.test(grpHtml) && /> Height </.test(grpHtml) && /> Width </.test(grpHtml)
     && !grpHtml.includes('layer-limit-axle'));
  ok("limits panel: the source note and the 'none loaded' line are in the group",
     grpHtml.includes("OpenStreetMap contributors and HERE · coverage is incomplete")
     && grpHtml.includes('<div class="control-item" id="limit-empty" hidden>') && grpHtml.includes("No lorry limits loaded for this area yet"));
  ok("⭐ limits: /api/public/limits is fetched (through CONFIG.API_BASE, like the other gated reads)",
     secCode.includes("fetch(CONFIG.API_BASE + '/public/limits')"));
  ok("⭐ limits: drawLimitSign (ONE pure drawing function) and limitCardHTML exist; the card's SVG is the same drawing",
     /function drawLimitSign\(ctx, kind, iconText, imperial, size, breach\) \{/.test(secCode)
     && /function limitCardHTML\(props\) \{/.test(secCode)
     && secCode.includes("drawLimitSign(ctx, kind, iconText, imperial, 100, breach);")
     && secCode.includes("drawLimitSign(ctx, p.kind, p.icon_text, p.imperial, LIMIT_SIGN_PX, Number(p.breach_count) > 0);"));
  ok("⭐ limits: each sign is a canvas image registered with addImage at a pixelRatio of 2 or more",
     secCode.includes("const dpr = Math.max(2, Math.ceil(window.devicePixelRatio || 1));")
     && secCode.includes("map.addImage(name, ctx.getImageData(0, 0, px, px), { pixelRatio: dpr });"));
  ok("⭐ limits zoom rule: clustered up to zoom 10 (radius 40), a plain ring below 13, the sign from 13, the label from 14, the stretch dashed red from 13",
     secCode.includes("const LIMIT_CLUSTER_MAX_ZOOM = 10;") && secCode.includes("clusterMaxZoom: LIMIT_CLUSTER_MAX_ZOOM, clusterRadius: 40")
     && secCode.includes("const LIMIT_SIGN_ZOOM = 13;") && secCode.includes("const LIMIT_LABEL_ZOOM = 14;")
     && /id: 'limit-dots', type: 'circle', source: 'limits-points', maxzoom: LIMIT_SIGN_ZOOM/.test(secCode)
     && /id: 'limit-signs', type: 'symbol', source: 'limits-points', minzoom: LIMIT_SIGN_ZOOM/.test(secCode)
     && secCode.includes("'text-field': ['step', ['zoom'], '', LIMIT_LABEL_ZOOM, ['get', '_label']]")
     && /id: 'limit-lines', type: 'line', source: 'limits-lines', minzoom: LIMIT_SIGN_ZOOM[\s\S]{0,120}'line-color': LIMIT_RED, 'line-width': 3\.5, 'line-dasharray': \[2, 1\.5\]/.test(secCode)
     && secCode.includes("const LIMIT_RED = '#C8102E';"));
  ok("limits: a clash wins a collision (symbol-sort-key, overlap off) and the label is the first thing dropped",
     secCode.includes("'icon-allow-overlap': false") && secCode.includes("'symbol-sort-key': ['get', '_sort']")
     && secCode.includes("_sort: p.breach_count > 0 ? 0 : 1") && secCode.includes("'text-optional': true"));
  ok("⭐ limits attribution: the sources carry the attribution of every source in the loaded limits (Mapbox prints it while a limit layer shows)",
     secCode.includes("const attribution = limitAttribution(fs);") && secCode.includes("attribution ? Object.assign(o, { attribution: attribution }) : o"));
  ok("⭐ limits survive a basemap switch: style.load re-adds them from the cached collection (no second fetch)",
     code.includes("if (LIM.data) ensureLimitLayers(); else loadLimits();"));
  ok("limits: the layers ride over the routes and under the sites (raiseMarks raises them first)",
     code.includes("if (typeof raiseLimits === 'function' && raiseLimits(ids)) {") && /function raiseLimits\(ids\) \{/.test(secCode));
  ok("⭐ limits click: the sign, ring, stretch and cluster are clickable (hand cursor, phone tap) and the route click gives way",
     /const CLICKABLE_LAYERS = \[[^\]]*'limit-signs', 'limit-dots', 'limit-lines', 'limit-clusters', 'area-fill', 'area-county-fill'\];/.test(code)
     && code.includes("if(typeof limitHitAt === 'function' && limitHitAt(e.point)) return;"));
  ok("⭐ limits phone: the card opens in the sheet (SHEET.card 'limit:<id>'), the desktop gets a popup",
     code.includes("if (typeof isPhoneShell === 'function' && isPhoneShell() && typeof openLimitCard === 'function') { openLimitCard(p.id); return; }")
     && /function openLimitCard\(id\) \{\s*if \(id == null \|\| id === ''\) return;\s*SHEET\.card = 'limit:' \+ id;/.test(code)
     && code.includes("limitCardHTML(f.properties)") && code.includes("setHTML(limitCardHTML(p))"));
  ok("⭐ limits conditions: buildConditions adds the limit rows for the routes on screen; 'Show on map' goes to showLimit",
     code.includes("limitConditionRows(LIM.data.features, routes.map(p => p.route_id), month).forEach(i => items.push(i));")
     && code.includes("if (kind === 'l') { if (typeof showLimit === 'function') showLimit(id); return; }")
     && code.includes("if (LIM.data && typeof TL !== 'undefined' && TL.on && typeof renderTimelineWarnings === 'function') renderTimelineWarnings(TL.month);"));
  ok("⭐ limits link / council view: the boxes are layer-* boxes, so layerBoxes() (the link) and councilOtherBoxes() (remember / restore) take them",
     code.includes("return [...document.querySelectorAll('input[type=checkbox][id^=\"layer-\"], input[type=checkbox][id^=\"restr-\"], #toggle-road-load, #toggle-carbon, #toggle-forecast')];")
     && code.includes(".filter(cb => cb.id.indexOf('layer-areas-') !== 0 && cb.id.indexOf('layer-zone-') !== 0);")
     && code.includes("if (/^(layer-|restr-)/.test(id) || id === 'toggle-forecast' || LINK_MODE_BOXES.includes(id)) scheduleViewWrite();"));
  ok("⭐ limits presets: 'Closures and restrictions' ticks the limit boxes while the group offers them; presetMatches reads the same presetLayers",
     code.includes("if (k.indexOf('limit-') === 0 && presetLimitsAvailable()) on.add(k);")
     && /function presetLimitsAvailable\(\) \{/.test(code) && code.includes("const want = presetLayers(p);\n        return layerBoxes()"));
  ok("🔴 limits wording: no 'truck', no banned public words, no team id in the new code or the group",
     !/truck/i.test(sec + grpHtml) && !/\b(optimi[sz]e|predict|real-time|AI|secure|live tracking|telematics)\b/.test(sec + grpHtml)
     && !/IPT\d|'IPT|"IPT/.test(sec + grpHtml));

  // ---- the sandbox: the section run against plain data, a recording 2D context and a fake map ----
  const escSrc = (/const escHtml = (s => [^\n]+);/.exec(html) || [])[1];
  let escHtml = null; try { escHtml = new Function("return " + escSrc)(); } catch (e) {}
  ok("limits (sandbox): the page's own escHtml is read for the sandbox", typeof escHtml === 'function' && escHtml("<b>'") === '&lt;b&gt;&#39;');
  let unit = 'km';
  const KM_PER_MI = 1.609344;
  const DU = () => unit, fmtDist = (km, dp) => (unit === 'mi' ? km / KM_PER_MI : km).toFixed(dp == null ? 1 : dp);
  const byId = {};
  const el = id => {
    const o = { id, hidden: false, checked: false, textContent: '', classes: new Set(), dispatchEvent() { return true; } };
    o.classList = { toggle: (c, on) => { if (on) o.classes.add(c); else o.classes.delete(c); } };
    byId[id] = o;
    return o;
  };
  ['limits-group', 'limit-boxes', 'limit-empty', 'limit-source', 'limit-count-weight', 'limit-count-height', 'limit-count-width',
   'limit-row-weight', 'limit-row-height', 'limit-row-width', 'layer-limit-weight', 'layer-limit-height', 'layer-limit-width'].forEach(id => el(id));
  byId['limits-group'].hidden = true;
  function fakeCtx(noMeasure) {
    const calls = [];
    const c = { calls, fillStyle: '', strokeStyle: '', lineWidth: 1, font: '', textAlign: '', textBaseline: '',
      beginPath() { calls.push(['beginPath']); }, arc(...a) { calls.push(['arc', ...a]); }, moveTo(...a) { calls.push(['moveTo', ...a]); },
      lineTo(...a) { calls.push(['lineTo', ...a]); }, closePath() { calls.push(['closePath']); },
      fill() { calls.push(['fill', this.fillStyle]); }, stroke() { calls.push(['stroke', this.strokeStyle, this.lineWidth]); },
      fillText(t, x, y) { calls.push(['fillText', t, x, y, this.font, this.fillStyle]); },
      scale(x, y) { calls.push(['scale', x, y]); }, getImageData(x, y, w, h) { return { width: w, height: h, data: new Uint8Array(4) }; } };
    if (!noMeasure) c.measureText = function (t) { const m = /([\d.]+)px/.exec(this.font); return { width: String(t).length * (m ? +m[1] : 10) * 0.6 }; };
    return c;
  }
  const canvases = [];
  const document = { getElementById: id => byId[id] || null,
                     createElement: t => { const cv = { tag: t, width: 0, height: 0, ctx: fakeCtx(), getContext() { return this.ctx; } }; canvases.push(cv); return cv; } };
  const window = { devicePixelRatio: 1, innerHeight: 800 };
  // the fake map: sources, layers, images, handlers
  const M = { sources: {}, layers: {}, order: [], images: {}, handlers: [], vis: {}, moved: [] };
  const map = {
    isStyleLoaded: () => true, once() {}, hasImage: n => !!M.images[n], addImage: (n, img, o) => { M.images[n] = { img, o }; },
    getSource: id => M.sources[id] ? { setData: d => { M.sources[id].data = d; }, getClusterExpansionZoom() {} } : undefined,
    addSource: (id, o) => { M.sources[id] = Object.assign({}, o); },
    getLayer: id => M.layers[id], addLayer: l => { M.layers[l.id] = l; M.order.push(l.id); M.vis[l.id] = l.layout && l.layout.visibility; },
    setLayoutProperty: (id, k, v) => { if (k === 'visibility') M.vis[id] = v; },
    on: (...a) => { M.handlers.push(a); }, getStyle: () => ({ layers: M.order.map(id => ({ id })) }), moveLayer: id => { M.moved.push(id); },
    queryRenderedFeatures: () => [], getCanvas: () => ({ style: {} }), getZoom: () => 9,
  };
  let fetchAnswer = null;
  const fetch = () => fetchAnswer;
  const quiet = { warn() {}, log() {}, info() {} };
  let L = null, lerr = '';
  try {
    L = new Function("escHtml", "DU", "fmtDist", "document", "window", "map", "mapboxgl", "CONFIG", "MARK_LAYERS", "raiseMarks", "fetch", "console",
      sec + "\nreturn { drawLimitSign, limitSignSVG, limitCardHTML, limitConditionRows, limitChipText, limitAppliesText, limitValueText, limitLengthText, limitDate,"
          + " limitPointFeatures, limitLineFeatures, limitAttribution, limitImageName, loadLimits, renderLimitGroup, ensureLimitLayers, toggleLimits, raiseLimits, LIM };")(
      escHtml, DU, fmtDist, document, window, map, { Popup: function () { return { setLngLat() { return this; }, setHTML() { return this; }, addTo() { return this; } }; } },
      { API_BASE: '/api' }, ['site-gates', 'locations', 'site-gates-label'], () => {}, fetch, quiet);
  } catch (e) { lerr = String(e && e.stack || e); }
  ok("limits (sandbox): the section runs against plain data, a recording context and a fake map", !!L, lerr.slice(0, 400));
  if (L) {
    // -- the sign --
    const drawn = (kind, t, imp, breach, noMeasure) => { const c = fakeCtx(noMeasure); L.drawLimitSign(c, kind, t, imp, 34, breach); return c.calls; };
    const texts = cs => cs.filter(c => c[0] === 'fillText').map(c => c[1]);
    const w = drawn('weight', '7.5T', null, false);
    ok("⭐ drawLimitSign (sandbox): the ring is stroked in the sign red #C8102E, over a white face",
       w.some(c => c[0] === 'stroke' && c[1] === '#C8102E') && w.find(c => c[0] === 'fill')[1] === '#FFFFFF'
       && w.filter(c => c[0] === 'arc').length === 1);
    ok("⭐ drawLimitSign (sandbox): the weight legend '7.5T' is drawn in black, and nothing else (no triangles, no '!')",
       JSON.stringify(texts(w)) === '["7.5T"]' && w.find(c => c[0] === 'fillText')[5] === '#111111' && !w.some(c => c[0] === 'lineTo'));
    const h = drawn('height', '4.4m', "14'6\"", false);
    const hTxt = h.filter(c => c[0] === 'fillText');
    ok("⭐ drawLimitSign (sandbox): height draws two triangle PATHS (down at the top, up at the bottom) and imperial OVER metric",
       h.filter(c => c[0] === 'moveTo').length === 2 && h.filter(c => c[0] === 'lineTo').length === 4 && h.filter(c => c[0] === 'closePath').length === 2
       && (() => { const mv = h.filter(c => c[0] === 'moveTo'), ln = h.filter(c => c[0] === 'lineTo');
                   return mv[0][2] < 17 && ln[1][2] > mv[0][2] && mv[1][2] > 17 && ln[3][2] < mv[1][2]; })()
       && hTxt.length === 2 && hTxt[0][1] === "14'6\"" && hTxt[1][1] === '4.4m' && hTxt[0][3] < hTxt[1][3], JSON.stringify(h.slice(0, 12)));
    const wd = drawn('width', '2.0m', "6'6\"", false);
    ok("drawLimitSign (sandbox): width draws the triangles at the left and right pointing IN, imperial over metric",
       (() => { const mv = wd.filter(c => c[0] === 'moveTo'), ln = wd.filter(c => c[0] === 'lineTo');
                return mv.length === 2 && mv[0][1] < 17 && ln[1][1] > mv[0][1] && mv[1][1] > 17 && ln[3][1] < mv[1][1]; })()
       && JSON.stringify(texts(wd)) === JSON.stringify(["6'6\"", '2.0m']));
    ok("drawLimitSign (sandbox): height with no imperial figure draws the metric alone",
       JSON.stringify(texts(drawn('height', '4.4m', null, false))) === '["4.4m"]');
    ok("drawLimitSign (sandbox): axle draws its legend over 'per axle'", JSON.stringify(texts(drawn('axle', '10T', null, false))) === '["10T","per axle"]');
    const b = drawn('weight', '7.5T', null, true);
    ok("⭐ drawLimitSign (sandbox): a clash adds a solid red disc with a white '!' at the top right — and only a clash",
       texts(b).includes('!') && !texts(w).includes('!') && !texts(h).includes('!')
       && b.filter(c => c[0] === 'arc').length === 2 && b.filter(c => c[0] === 'arc')[1][1] > 17 && b.filter(c => c[0] === 'arc')[1][2] < 17
       && b.some(c => c[0] === 'fill' && c[1] === '#C8102E') && b.find(c => c[0] === 'fillText' && c[1] === '!')[5] === '#FFFFFF');
    ok("drawLimitSign (sandbox): a context with no measureText still draws", JSON.stringify(texts(drawn('weight', '7.5T', null, false, true))) === '["7.5T"]');
    const svg = L.limitSignSVG('height', '4.4m', "14'6\"", true, 44);
    ok("limits (sandbox): the card's SVG is the same drawing (ring in #C8102E, the legends escaped, the '!' for a clash)",
       /^<svg [^>]*viewBox="0 0 100 100" width="44"/.test(svg) && svg.includes('stroke="#C8102E"') && svg.includes('>14&#39;6&quot;</text>')
       && svg.includes('>4.4m</text>') && svg.includes('>!</text>') && (svg.match(/<path /g) || []).length === 2);
    // -- the card --
    const W = { id: 'osm:w1:weight', kind: 'weight', value: 7.5, unit: 't', label: 'Weight limit 7.5 t', headline: 'Weight limit 7.5 t · Back Lane',
                icon_text: '7.5T', imperial: null, signed: null, name: 'Back Lane', ref: null, exceptions: 'Except for access', source: 'osm',
                source_label: 'OpenStreetMap', attribution: '© OpenStreetMap contributors (ODbL)', fetched_at: '2026-10-13T10:00:00+00:00',
                length_m: 240.5, geom_type: 'LineString', anchor: [-0.92, 52.47],
                breaches: [{ route_id: 'R004', vehicle: 'Artic Tipper (44t)', vehicle_value: 44.0, leg: 'loaded' }], breach_count: 1 };
    const H = { id: 'osm:n7:height', kind: 'height', value: 4.4, unit: 'm', label: 'Height limit 4.4 m', icon_text: '4.4m', imperial: "14'6\"",
                name: 'Kettering Road', ref: 'A6', exceptions: null, source: 'here', source_label: 'HERE', attribution: '© HERE',
                fetched_at: '2026-10-12T08:00:00+00:00', length_m: null, geom_type: 'Point', anchor: [-0.9, 52.48], breaches: [], breach_count: 0 };
    const cw = L.limitCardHTML(W);
    ok("⭐ limitCardHTML (sandbox): a weight limit with 'Except for access' and one breach",
       cw.includes('7.5 t') && cw.includes('Except for access') && cw.includes('R004 · Artic Tipper (44t) · loaded')
       && cw.includes('Advisory: check the signed limit on site') && cw.includes('© OpenStreetMap contributors')
       && cw.includes('<div class="lim-title">Weight limit 7.5 t</div>') && cw.includes('Vehicles over 7.5 t')
       && cw.includes('OpenStreetMap · fetched 13 Oct 2026') && cw.includes('Back Lane · 241 m of road') && cw.includes('lim-v over') && cw.includes('<svg '), cw);
    ok("limitCardHTML (sandbox): Mapbox's stringified properties give the same card", L.limitCardHTML(Object.assign({}, W,
       { breaches: JSON.stringify(W.breaches), anchor: JSON.stringify(W.anchor), breach_count: '1' })) === cw);
    const ch = L.limitCardHTML(H);
    ok("⭐ limitCardHTML (sandbox): a height limit says its imperial figure (14'6\", escaped) and who it applies to; no breach: 'None of the planned routes'",
       ch.includes(escHtml("14'6\"")) && ch.includes('Vehicles taller than 4.4 m (' + escHtml("14'6\"") + ')') && ch.includes('None of the planned routes')
       && ch.includes('None recorded') && ch.includes('Kettering Road (A6)') && ch.includes('HERE · fetched 12 Oct 2026') && ch.includes('© HERE')
       && !ch.includes('lim-v over') && !ch.includes('of road'), ch);
    const evil = L.limitCardHTML(Object.assign({}, W, { name: '<b>Evil</b> Lane', exceptions: '<img src=x onerror=alert(1)>',
                                                        breaches: [{ route_id: '<i>R9</i>', vehicle: '"V"', leg: 'return' }] }));
    ok("⭐ limitCardHTML (sandbox): every interpolated string is escaped (a road named '<b>Evil</b> Lane')",
       !evil.includes('<b>Evil') && evil.includes('&lt;b&gt;Evil&lt;/b&gt; Lane') && !evil.includes('<img') && !evil.includes('<i>R9')
       && evil.includes('&lt;i&gt;R9&lt;/i&gt; · &quot;V&quot; · going back empty'));
    ok("limitCardHTML (sandbox): both legs of one route and vehicle read as one line ('loaded and going back empty')",
       L.limitCardHTML(Object.assign({}, W, { breaches: [{ route_id: 'R004', vehicle: 'Artic Tipper (44t)', leg: 'return' }, W.breaches[0]], breach_count: 2 }))
        .includes('R004 · Artic Tipper (44t) · loaded and going back empty'));
    ok("limitCardHTML (sandbox): an axle limit applies 'per axle'; a width limit 'wider than' with its imperial figure",
       L.limitAppliesText({ kind: 'axle', value: 10, unit: 't' }) === 'Vehicles over 10 t per axle'
       && L.limitAppliesText({ kind: 'width', value: 2, unit: 'm', imperial: "6'6\"" }) === "Vehicles wider than 2.0 m (6'6\")");
    unit = 'mi';
    ok("limits (sandbox): the length is in the tenant's unit (DU): miles on a mi tenant", L.limitCardHTML(W).includes('Back Lane · 0.15 mi of road')
       && L.limitLengthText(5000) === '3.1 mi');
    unit = 'km';
    ok("limits (sandbox): metres under a km, km above; nothing for no length", L.limitLengthText(240.5) === '241 m' && L.limitLengthText(2500) === '2.5 km'
       && L.limitLengthText(null) === '' && L.limitLengthText(0) === '');
    ok("limits (sandbox): the values read as the signs print them", L.limitValueText('weight', 7.5, 't') === '7.5 t' && L.limitValueText('weight', 18, 't') === '18 t'
       && L.limitValueText('height', 4, 'm') === '4.0 m' && L.limitValueText('height', 4.27, 'm') === '4.27 m' && L.limitDate('2026-10-13T10:00:00+00:00') === '13 Oct 2026');
    // -- the label chip --
    ok("⭐ limits (sandbox): the label beside the sign — weight with its exception and road, height as low headroom with imperial, width",
       L.limitChipText(W) === '7.5 t · except for access · Back Lane'
       && L.limitChipText(H) === "Low headroom 4.4 m (14'6\") · Kettering Road"
       && L.limitChipText({ kind: 'width', value: 2, unit: 'm', imperial: "6'6\"" }) === "Width 2.0 m (6'6\")"
       && L.limitChipText({ kind: 'axle', value: 10, unit: 't' }) === '10 t per axle');
    // -- the Conditions rows --
    const F = p => ({ type: 'Feature', geometry: { type: 'Point', coordinates: p.anchor }, properties: p });
    const R9 = Object.assign({}, W, { id: 'osm:w9:weight', breaches: [{ route_id: 'R009', vehicle: 'Rigid 8-wheel (32t)', leg: 'loaded' }] });
    const AX = Object.assign({}, W, { id: 'osm:w5:axle', kind: 'axle', value: 10, icon_text: '10T', name: null, ref: 'B6047',
                                      breaches: [{ route_id: 'R004', vehicle: 'Artic Tipper (44t)', leg: 'loaded' }, { route_id: 'R004', vehicle: 'Artic Tipper (44t)', leg: 'return' },
                                                 { route_id: 'R001', vehicle: 'Rigid 8-wheel (32t)', leg: 'loaded' }], breach_count: 3 });
    const rows = L.limitConditionRows([F(W), F(H), F(R9), F(AX)], ['R004', 'R001'], 10);
    ok("⭐ limits conditions (sandbox): one WARNING row per limit a route in use is over; a route not in use this month gives none",
       rows.length === 2 && rows[0].key === 'l|osm:w1:weight|10' && rows[0].lvl === 'warn' && rows[0].kind === 'l' && rows[0].id === 'osm:w1:weight'
       && rows[0].who === 'R004' && rows[0].noun === 'Over a weight limit'
       && rows[0].what === 'R004 · Artic Tipper (44t) is over the 7.5 t weight limit on Back Lane (OpenStreetMap)', JSON.stringify(rows));
    ok("limits conditions (sandbox): an axle limit is 'an axle weight limit', on its ref when unnamed; two legs of one route count once, another route is '+1 more'",
       rows[1].noun === 'Over an axle weight limit' && rows[1].what === 'R004 · Artic Tipper (44t) is over the 10 t axle weight limit on B6047 (OpenStreetMap) (+1 more)');
    ok("limits conditions (sandbox): no route in use, no rows; a standing limit has no dates, so every month gets its row",
       L.limitConditionRows([F(W)], [], 10).length === 0 && L.limitConditionRows([F(W)], ['R004'], 37)[0].key === 'l|osm:w1:weight|37');
    // -- the map sources --
    const LN = Object.assign({}, W, { id: 'osm:w2:height', kind: 'height', value: 4, icon_text: '4.0m', imperial: "13'1\"", breaches: [], breach_count: 0 });
    const FC = { type: 'FeatureCollection', features: [
      { type: 'Feature', geometry: { type: 'LineString', coordinates: [[-0.93, 52.47], [-0.91, 52.47]] }, properties: W },
      F(H), { type: 'Feature', geometry: { type: 'LineString', coordinates: [[-0.8, 52.4], [-0.79, 52.41]] }, properties: LN }, F(AX)] };
    const pw = L.limitPointFeatures(FC, { weight: true, height: false, width: false });
    ok("⭐ limits (sandbox): the clustered source holds the ticked kinds only (axle rides with Weight), at each limit's anchor, a clash sorted first",
       pw.features.length === 2 && pw.features.every(f => f.geometry.type === 'Point') && JSON.stringify(pw.features[0].geometry.coordinates) === '[-0.92,52.47]'
       && pw.features.map(f => f.properties.kind).join(',') === 'weight,axle' && pw.features[0].properties._sort === 0
       && pw.features[0].properties._img === L.limitImageName('weight', '7.5T', null, true) && pw.features[0].properties._label === '7.5 t · except for access · Back Lane');
    ok("limits (sandbox): the dashed stretches are the LINE limits of the ticked kinds", L.limitLineFeatures(FC, { weight: false, height: true }).features.length === 1
       && L.limitLineFeatures(FC, { weight: true, height: true }).features.length === 2 && L.limitLineFeatures(FC, {}).features.length === 0);
    ok("⭐ limits attribution (sandbox): every source present, once each", L.limitAttribution(FC.features) === '© OpenStreetMap contributors (ODbL) · © HERE'
       && L.limitAttribution([F(W)]) === '© OpenStreetMap contributors (ODbL)' && L.limitAttribution([]) === '');
    ok("limits (sandbox): raiseLimits puts the limits under the marks, and does nothing when they already are",
       L.raiseLimits(['a', 'limit-signs', 'b', 'locations']) === true && M.moved.join(',') === 'limit-signs'
       && L.raiseLimits(['a', 'limit-lines', 'limit-signs', 'site-gates', 'locations']) === false && L.raiseLimits(['a', 'b']) === false);
    M.moved.length = 0;
    // -- the load: the group, the counts, the layers, the images, the attribution --
    fetchAnswer = Promise.resolve({ ok: true, json: () => Promise.resolve(FC) });
    ASYNC_PINS.push(L.loadLimits().then(() => {
      ok("⭐ limits load (sandbox): the group shows with the counts (axle counted with Weight), the empty note hidden",
         !byId['limits-group'].hidden && byId['limit-count-weight'].textContent === '2' && byId['limit-count-height'].textContent === '2'
         && byId['limit-count-width'].textContent === '0' && byId['limit-row-width'].classes.has('dim') && !byId['limit-row-weight'].classes.has('dim')
         && !byId['limit-boxes'].hidden && byId['limit-empty'].hidden
         && byId['limit-source'].textContent === 'OpenStreetMap contributors and HERE · coverage is incomplete. Advisory: check the signed limit on site.');
      const ps = M.sources['limits-points'], ls = M.sources['limits-lines'];
      ok("⭐ limits load (sandbox): a clustered point source (max zoom 10, radius 40) and a line source, both carrying the attribution",
         ps && ps.cluster === true && ps.clusterMaxZoom === 10 && ps.clusterRadius === 40 && ls
         && ps.attribution === '© OpenStreetMap contributors (ODbL) · © HERE' && ls.attribution === ps.attribution);
      ok("⭐ limits load (sandbox): OFF by default — five layers added, all hidden, nothing in the sources",
         ['limit-lines', 'limit-clusters', 'limit-cluster-count', 'limit-dots', 'limit-signs'].every(id => M.layers[id] && M.vis[id] === 'none')
         && ps.data.features.length === 0 && ls.data.features.length === 0);
      const imgs = Object.keys(M.images);
      ok("⭐ limits load (sandbox): one image per distinct sign, at pixelRatio 2 (a 1x screen), 68 px for a 34 px sign",
         imgs.length === 4 && imgs.includes(L.limitImageName('weight', '7.5T', null, true)) && imgs.includes(L.limitImageName('height', '4.4m', "14'6\"", false))
         && Object.values(M.images).every(i => i.o.pixelRatio === 2 && i.img.width === 68) && canvases.length === 4
         && canvases.every(cv => cv.ctx.calls.some(c => c[0] === 'stroke' && c[1] === '#C8102E')));
      byId['layer-limit-height'].checked = true; L.toggleLimits();
      ok("⭐ limits toggle (sandbox): ticking Height shows the layers with the height limits only (point and stretch); no image drawn twice",
         ['limit-lines', 'limit-signs', 'limit-dots', 'limit-clusters'].every(id => M.vis[id] === 'visible')
         && M.sources['limits-points'].data.features.map(f => f.properties.kind).join(',') === 'height,height'
         && M.sources['limits-lines'].data.features.length === 1 && canvases.length === 4);
      byId['layer-limit-height'].checked = false; L.toggleLimits();
      ok("limits toggle (sandbox): unticking the last box hides every limit layer (so its attribution goes too)",
         ['limit-lines', 'limit-clusters', 'limit-cluster-count', 'limit-dots', 'limit-signs'].every(id => M.vis[id] === 'none'));
      ok("limits (sandbox): the clicks are wired once (four layers, hand cursor and click)",
         M.handlers.filter(h => h[0] === 'click' && /^limit-/.test(h[1])).length === 4 && M.handlers.filter(h => h[0] === 'mouseenter').length === 4);
      // 13 Oct 2026, seen in Chrome: the map never went 'idle' again after the limits arrived, so they were never drawn.
      // With the style "not loaded" and an idle that never comes, the layers must still be added straight away.
      const savedIsLoaded = map.isStyleLoaded; let idleArmed = 0;
      const savedOnce = map.once; map.isStyleLoaded = () => false; map.once = (ev) => { if (ev === 'idle') idleArmed++; };
      ['limit-lines', 'limit-clusters', 'limit-cluster-count', 'limit-dots', 'limit-signs'].forEach(id => { delete M.layers[id]; });
      delete M.sources['limits-points']; delete M.sources['limits-lines'];
      L.ensureLimitLayers(); L.ensureLimitLayers();
      ok("⭐ limits (sandbox): the style 'not loaded' and no idle coming — the five layers and two sources are still added at once",
         ['limit-lines', 'limit-clusters', 'limit-cluster-count', 'limit-dots', 'limit-signs'].every(id => M.layers[id])
         && M.sources['limits-points'] && M.sources['limits-lines']);
      ok("...and ONE idle wait is armed, not one per call", idleArmed === 1, String(idleArmed));
      map.isStyleLoaded = savedIsLoaded; map.once = savedOnce;
      ok("limits (source): a route's hover card gives way over a lorry limit (seen in Chrome 13 Oct)",
         code.includes("|| (typeof limitHitAt === 'function' && limitHitAt(e.point))) { card.hidden = true; HOVER.key = ''; return; }"));
      ok("limits (source): the card scrolls inside the popup instead of running off the map",
         html.includes(".lim-card{ font-size:14px; line-height:1.4; color:var(--ink); min-width:230px; max-height:min(52vh, 380px); overflow-y:auto; }"));
      ok("limits (source): the deferral tries the add at once and retries on a refusal",
         code.includes("try { addLimitLayers(); } catch (e) { setTimeout(ensureLimitLayers, 500); }"));
      // an empty collection: the note, no boxes; a failed read: no group
      L.LIM.data = { type: 'FeatureCollection', features: [] }; L.renderLimitGroup();
      ok("⭐ limits (sandbox): nothing loaded yet: the group shows 'No lorry limits loaded for this area yet' instead of the boxes",
         !byId['limits-group'].hidden && byId['limit-boxes'].hidden && !byId['limit-empty'].hidden);
      L.LIM.data = null; fetchAnswer = Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      return L.loadLimits().then(() => {
        ok("⭐ limits (sandbox): the endpoint failing hides the group and nothing throws", byId['limits-group'].hidden === true && L.LIM.failed === true);
      });
    }));
  }
}

// ---- 13 Oct 2026 (the user): PRESET VIEWS at the top of the panel ------------------------------------------------------
{
  const nb = newBlockSrc(), nbc = newBlockCode();
  ok("⭐ presets: a 'Views' group is the FIRST group of the panel (above Route filtering), its buttons built by renderPresets()",
     html.includes('<div class="control-group" id="preset-group">\n        <h3>Views</h3>\n        <div class="preset-views" id="preset-views" role="group" aria-label="Preset views"></div>')
     && html.indexOf('id="preset-group"') < html.indexOf('<h3>Route filtering</h3>') && html.indexOf('id="preset-group"') > html.indexOf('id="main-sidebar"'));
  ok("⭐ presets: the six views, in the user's order and words",
     nbc.includes("{ key: 'councils-movements', label: 'Councils: movements', council: 'movements' },\n        { key: 'councils-carbon', label: 'Councils: carbon', council: 'carbon' },\n        { key: 'busiest-roads', label: 'Busiest roads', heat: 'volume' },\n        { key: 'route-carbon', label: 'Route carbon', heat: 'carbon' },\n        { key: 'closures', label: 'Closures and restrictions', closures: true },\n        { key: 'everything', label: 'Everything' },"));
  ok("⭐ presets: a view outside the council view LEAVES it first (its restore would fight the boxes), sets the boxes, then the heat map",
     /if \(typeof leaveCouncilView === 'function'\) leaveCouncilView\(\);\s*const want = presetLayers\(p\);\s*layerBoxes\(\)\.filter\(cb => !HEAT_RADIO_IDS\.includes\(cb\.id\)\)\.forEach\(cb => flip\(cb, want\.has\(layerKey\(cb\.id\)\)\)\);\s*const radio = /.test(nbc));
  ok("presets: every box a view changes dispatches 'change' (its own handler and the link listener run as for a click)",
     nbc.includes("const flip = (cb, v) => { if (cb && !!cb.checked !== v) { cb.checked = v; cb.dispatchEvent(new Event('change', { bubbles: true })); } };")
     && nbc.includes("radio.checked = true; radio.dispatchEvent(new Event('change', { bubbles: true }));"));
  ok("presets: a council view sets the colouring BEFORE ticking the boxes; council views are left out when the tenant has no council areas",
     /setAreaMode\(p\.council\);\s*flip\(document\.getElementById\('layer-areas-district'\), true\);\s*flip\(document\.getElementById\('layer-areas-county'\), true\);/.test(nbc)
     && nbc.includes("const list = PRESETS.filter(p => !p.council || presetCouncilAvailable());"));
  ok("⭐ presets: the phone gets them in the Layers sheet (the panel is the sheet) at 48 px, and picking one lowers the sheet",
     html.includes(".preset-chip{ min-height:48px; padding:0 14px; }")
     && nbc.includes("if (typeof isPhoneShell === 'function' && isPhoneShell() && typeof closeLayersSheet === 'function') closeLayersSheet();"));
  ok("⭐ presets link: the council colouring travels as &council=carbon (only while By council is on), and is read back before the boxes are ticked",
     nbc.includes("if (v.council === 'carbon') q.set('council', 'carbon');")
     && nbc.includes("council: q.get('council') === 'carbon' ? 'carbon' : null };")
     && nbc.includes("council: (typeof councilFocus === 'function' && councilFocus() && typeof AREAS !== 'undefined' && AREAS.mode === 'carbon') ? 'carbon' : null };")
     && /if \(v\.council === 'carbon' && typeof AREAS !== 'undefined'\) AREAS\.mode = 'carbon';\s*if \(v\.layers\) \{/.test(nbc)
     && code.includes("if (typeof scheduleViewWrite === 'function') scheduleViewWrite();\n        if (typeof schedulePresetRender === 'function') schedulePresetRender();\n    }"));
  ok("presets: the banned public words are not in the preset labels or note",
     !/\b(optimi[sz]e|predict|real-time|AI|secure|live tracking)\b/i.test(cut0(html, 'id="preset-group"', '</div>\n\n') + cut0(nb, 'const PRESETS = [', '];')));

  // the sandbox: the last block against a fake DOM whose boxes behave as the page's (radio group, the council view's
  // contract: the first council box unticks the others and remembers them, leaving ticks them back, the heat map goes Off)
  const byId = {}, order = [];
  const evs = [];
  const mk = (id, checked, type) => { const el = { id, type: type || 'checkbox', checked: !!checked, hidden: false, innerHTML: '', textContent: '', value: '', style: {}, dataset: {}, attrs: {},
      options: [], selectedIndex: 0, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; }, focus() {}, addEventListener() {},
      querySelector() { return null; }, querySelectorAll() { return []; }, getBoundingClientRect() { return { left: 0, top: 0, width: 300, height: 100, right: 300, bottom: 100 }; },
      dispatchEvent(e) { evs.push(id); onChange(el); return true; } };
    byId[id] = el; return el; };
  // the page's boxes (defaults as shipped: the closures' box off, the council boxes off)
  [['layer-alignment', 1], ['layer-ws-bounds', 1], ['layer-chainage', 0], ['layer-nodes', 1], ['layer-gates', 1], ['layer-zones', 1], ['layer-zone-closure', 1],
   ['layer-zone-works', 1], ['layer-rail', 1], ['layer-inbound', 1], ['layer-outbound', 1], ['layer-temp', 1], ['layer-alts', 0],
   ['layer-areas-district', 0], ['layer-areas-county', 0], ['restr-nh_closures', 0],
   // 13 Oct 2026: the lorry-limit boxes (off as shipped; their group shown, limits loaded)
   ['layer-limit-weight', 0], ['layer-limit-height', 0], ['layer-limit-width', 0]].forEach(([id, on]) => order.push(mk(id, on)));
  const heatOff = mk('heat-off', 1, 'radio'), rl = mk('toggle-road-load', 0, 'radio'), co = mk('toggle-carbon', 0, 'radio'), fc = mk('toggle-forecast', 0);
  ['preset-views', 'council-group', 'limits-group', 'limit-boxes', 'm-sheet', 'filter-origin', 'filter-dest', 'filter-discipline', 'filter-ipt', 'layers-box', 'sidebar-close', 'toggle-x'].forEach(id => mk(id, 0, 'div'));
  ['filter-origin', 'filter-dest', 'filter-discipline', 'filter-ipt'].forEach(id => { byId[id].value = 'ALL'; byId[id].options = [{ value: 'ALL', textContent: 'All' }]; });
  const COUNCIL = { saved: null }, calls = { leave: 0, timeline: 0, sheet: 0 };
  const AREAS = { mode: 'movements' };
  const councilOn = () => byId['layer-areas-district'].checked || byId['layer-areas-county'].checked;
  const others = () => order.filter(b => /^(layer-|restr-)/.test(b.id) && !/^layer-(areas|zone)-/.test(b.id));
  function onChange(el) {
    if (el.type === 'radio' && el.checked) [heatOff, rl, co].forEach(r => { if (r !== el) r.checked = false; });
    if (/^layer-areas-/.test(el.id)) {           // the council view's contract (toggleAreaTier + councilSolo)
      if (councilOn() && COUNCIL.saved === null) { COUNCIL.saved = others().filter(b => b.checked).map(b => b.id); others().forEach(b => { if (b.checked) { b.checked = false; b.dispatchEvent({}); } }); }
      else if (!councilOn() && COUNCIL.saved !== null) { const ids = COUNCIL.saved; COUNCIL.saved = null; ids.forEach(i => { if (!byId[i].checked) { byId[i].checked = true; byId[i].dispatchEvent({}); } }); }
      if (el.checked) { heatOff.checked = true; rl.checked = false; co.checked = false; }
    }
    if ((el === rl || el === co) && el.checked) calls.timeline++;
  }
  const fakeGlobals = {
    AREAS, councilFocus: councilOn, heatMode: () => rl.checked ? 'volume' : co.checked ? 'carbon' : null,
    leaveCouncilView: () => { calls.leave++; if (!councilOn()) return; byId['layer-areas-district'].checked = false; byId['layer-areas-county'].checked = false; onChange(byId['layer-areas-district']); },
    setAreaMode: m => { AREAS.mode = m === 'carbon' ? 'carbon' : 'movements'; }, closeLayersSheet: () => { calls.sheet++; }, Event: function (t) { this.type = t; },
  };
  const savedGlobals = {}; Object.keys(fakeGlobals).forEach(k => { savedGlobals[k] = globalThis[k]; });
  Object.assign(globalThis, fakeGlobals);
  const document = {
    getElementById: id => byId[id] || null,
    querySelectorAll: s => /layer-|restr-|toggle-/.test(s) ? order.concat([rl, co, fc]).filter(b => /layer-|restr-/.test(s) && /^(layer-|restr-)/.test(b.id) || ['toggle-road-load', 'toggle-carbon', 'toggle-forecast'].includes(b.id)) : [],
    addEventListener() {}, createElement: () => mk('x' + Math.random(), 0, 'div'), body: { appendChild() {}, classList: { add() {}, remove() {}, toggle() {} } }, activeElement: null,
  };
  const TL = { on: false, playing: false, month: 10, matrix: null };
  const location = { origin: 'https://app.wayscope.test', pathname: '/map/', search: '', hash: '' };
  const history = { replaceState(s, t, u) { const q = u.indexOf('?'); location.search = q >= 0 ? u.slice(q) : ''; } };
  let phone = false, sheetOpen = false;
  const window = { matchMedia: () => ({ matches: phone, addEventListener() {} }), innerWidth: 1280, innerHeight: 800 };
  const map = { touchPitch: { disable() {}, enable() {} }, dragRotate: { disable() {}, enable() {} }, setFeatureState() {}, getContainer: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0 }) }), resize() {}, on() {} };
  let P = null, err = '';
  try {
    P = new Function("document", "window", "TL", "KPI", "WARN", "CONFIG", "monthLabel", "map", "teamText", "TENANT", "fmtN", "fmtDist", "DU", "ROUTEINFO",
      "routePropsById", "FORECAST_WORKING_DAYS", "forecastWindow", "ensureTimelineMatrix", "openTimeline", "setTimelineMonth", "stopTimeline", "tlStartMonth",
      "applyFilters", "selectRoute", "clearSelection", "kpiFetchMonth", "sidebarIsOpen", "toggleSidebar", "closeSidebar", "isPhoneShell", "PHONE_SHELL_MQ",
      "location", "history", "navigator", "requestAnimationFrame", "MutationObserver", "setTimeout", "clearTimeout",
      nb + "\nreturn { PRESETS, PRESET, applyPreset, renderPresets, presetMatches, presetLayers, VIEW, layersOn, currentView, encodeView, decodeView, writeView, applyViewFromUrl };")(
      document, window, TL, { cache: {} }, { counts: {}, live: [] }, { MONTH_COUNT: 60, START_YEAR: 2026, API_BASE: '' }, m => 'Oct 2026', map, v => v, { name: 'Wolds Link (fictional)' },
      n => String(n), km => String(km), () => 'km', {}, () => ({}), 21, () => [9, 12], () => Promise.resolve(null), () => {}, () => {}, () => {}, () => 9,
      () => {}, () => {}, () => {}, () => Promise.resolve(null), () => sheetOpen, () => { calls.sheet++; sheetOpen = !sheetOpen; }, () => {}, () => phone, '(max-width:767px)',
      location, history, {}, () => 0, undefined, () => 0, () => {});
  } catch (e) { err = String(e && e.stack || e); }
  ok("presets (sandbox): the last block runs against a fake DOM with the page's boxes", !!P, err.slice(0, 400));
  if (P) {
    const on = () => order.concat([fc]).filter(b => b.checked).map(b => b.id.replace(/^layer-/, '').replace(/^toggle-/, '')).sort().join(',');
    const pressed = () => [...byId['preset-views'].innerHTML.matchAll(/data-preset="([^"]+)" aria-pressed="true"/g)].map(m => m[1]).join(',');
    const DEF = on();
    P.VIEW.ready = true;
    ok("presets (sandbox): the defaults are read from the boxes as shipped (no council box, no closures, no forecast)", P.VIEW.defaults.join(',') === DEF && !/areas|restr|forecast/.test(DEF), P.VIEW.defaults.join(','));
    // no council areas loaded: the group is hidden, so the two council views are not offered
    byId['council-group'].hidden = true; P.renderPresets();
    ok("⭐ presets (sandbox): with no council areas the council views are not offered; the four others are",
       [...byId['preset-views'].innerHTML.matchAll(/data-preset="([^"]+)"/g)].map(m => m[1]).join(',') === 'busiest-roads,route-carbon,closures,everything'
       && byId['preset-views'].innerHTML.includes('>Closures and restrictions</button>'), byId['preset-views'].innerHTML.slice(0, 300));
    P.applyPreset('councils-carbon');
    ok("presets (sandbox): ...and a council view asked for anyway does nothing", !byId['layer-areas-district'].checked && on() === DEF);
    byId['council-group'].hidden = false;
    // 1. Busiest roads
    P.applyPreset('busiest-roads');
    ok("⭐ presets (sandbox) Busiest roads: Volume picked (Off and Carbon not), the forecast routes on, the page's layers as shipped, the timeline asked for",
       rl.checked && !co.checked && !heatOff.checked && fc.checked && on() === [DEF, 'forecast'].join(',').split(',').sort().join(',') && calls.timeline === 1, on());
    P.writeView();
    ok("⭐ presets (sandbox) Busiest roads: the link carries it (layers=forecast.road-load), and the button shows pressed",
       /layers=forecast\.road-load(&|$)/.test(location.search) && pressed() === 'busiest-roads', location.search + ' / ' + pressed());
    // 2. Route carbon
    P.applyPreset('route-carbon');
    P.writeView();
    ok("⭐ presets (sandbox) Route carbon: Carbon picked, Volume let go, link layers=carbon.forecast, only it pressed",
       co.checked && !rl.checked && !heatOff.checked && /layers=carbon\.forecast(&|$)/.test(location.search) && pressed() === 'route-carbon', location.search + ' / ' + pressed());
    // 3. Councils: carbon (from a heat map)
    byId['layer-chainage'].checked = true;         // a box ticked by hand before: the council view remembers it
    P.applyPreset('councils-carbon');
    ok("⭐ presets (sandbox) Councils: carbon: the colouring is carbon, both council boxes ticked, every other layer off, the heat map Off",
       AREAS.mode === 'carbon' && byId['layer-areas-district'].checked && byId['layer-areas-county'].checked && others().every(b => !b.checked)
       && heatOff.checked && !co.checked && !rl.checked, on());
    P.writeView();
    ok("⭐ presets (sandbox) Councils: carbon: the link carries &council=carbon and the council boxes; only it pressed",
       /council=carbon/.test(location.search) && /areas-county\.areas-district/.test(location.search) && pressed() === 'councils-carbon', location.search + ' / ' + pressed());
    // 4. Councils: movements (council to council: only the colouring changes)
    const evBefore = evs.length;
    P.applyPreset('councils-movements'); P.writeView();
    ok("presets (sandbox) Councils: movements from Councils: carbon: only the colouring changes (no box flipped), the link drops council=carbon",
       AREAS.mode === 'movements' && evs.length === evBefore && !/council=/.test(location.search) && pressed() === 'councils-movements', location.search);
    // REVERSED-in-build 13 Oct (browser check): a council view picked after a forecast view left the forecast routes on
    fc.checked = true; P.applyPreset('busiest-roads'); P.applyPreset('councils-carbon');
    ok("⭐ presets (sandbox): a council view picked after a forecast view switches the forecast routes off too (the same picture whatever came before)",
       !fc.checked && AREAS.mode === 'carbon' && councilOn() && others().every(b => !b.checked));
    // 5. Closures, leaving the council view: the remembered boxes come back first, then the view's own set
    const leaves = calls.leave;
    P.applyPreset('closures');
    ok("⭐ presets (sandbox) Closures and restrictions: leaves the council view, the National Highways closures box and every zone kind on, the heat map Off, chainage (ticked by hand earlier) off again",
       calls.leave === leaves + 1 && !councilOn() && byId['restr-nh_closures'].checked && byId['layer-zones'].checked && byId['layer-zone-closure'].checked
       && heatOff.checked && !rl.checked && !co.checked && !byId['layer-chainage'].checked && fc.checked && COUNCIL.saved === null, on());
    P.writeView();
    ok("presets (sandbox) Closures: the link carries the closures box; only it pressed", /restr-nh_closures/.test(location.search) && pressed() === 'closures', location.search + ' / ' + pressed());
    const limBoxes = ['layer-limit-weight', 'layer-limit-height', 'layer-limit-width'];
    ok("⭐ presets (sandbox) Closures and restrictions: the three lorry-limit boxes are ticked too, and the link carries them",
       limBoxes.every(id => byId[id].checked) && /limit-height\.limit-weight\.limit-width/.test(location.search) && P.presetMatches(P.PRESETS.find(x => x.key === 'closures')),
       location.search);
    // 6. Everything
    P.applyPreset('everything'); P.writeView();
    ok("⭐ presets (sandbox) Everything: the page's layers as shipped with the forecast routes; closures off, heat map Off, no council",
       on() === [DEF, 'forecast'].join(',').split(',').sort().join(',') && heatOff.checked && !councilOn() && location.search === '?layers=forecast' && pressed() === 'everything', location.search + ' ' + on());
    ok("⭐ presets (sandbox) Everything: the lorry-limit boxes are left OFF, as the closures are", limBoxes.every(id => !byId[id].checked));
    // the limits not offered (none loaded, or the endpoint failed): Closures leaves the hidden boxes alone and still matches
    byId['limit-boxes'].hidden = true;
    P.applyPreset('closures');
    ok("presets (sandbox): with no lorry limits offered, Closures and restrictions does not tick the hidden boxes, and still shows pressed",
       limBoxes.every(id => !byId[id].checked) && byId['restr-nh_closures'].checked && pressed() === 'closures');
    byId['limit-boxes'].hidden = false; P.renderPresets();
    ok("presets (sandbox): ...and once the limits are offered, the same map no longer matches Closures (presetMatches reads presetLayers)", pressed() === '');
    P.applyPreset('everything');
    // the link: a shared view with two lorry-limit boxes opens with exactly those ticked, and encodes back the same
    location.search = '?layers=forecast.limit-weight.limit-width';
    P.applyViewFromUrl(); P.writeView();
    ok("⭐ limits link (sandbox): ?layers=limit-weight.limit-width ticks Weight and Width (not Height) and writes back the same link",
       byId['layer-limit-weight'].checked && byId['layer-limit-width'].checked && !byId['layer-limit-height'].checked
       && location.search === '?layers=forecast.limit-weight.limit-width', location.search);
    ok("limits link: encodeView / decodeView round-trip the limit boxes",
       JSON.stringify(P.decodeView('?' + P.encodeView({ month: null, layers: ['alignment', 'limit-height'], filters: {} }, ['alignment'])).layers) === '["limit-height"]');
    byId['layer-limit-weight'].checked = false; byId['layer-limit-width'].checked = false;
    // a box changed by hand: the map no longer matches any view, no button pressed
    byId['layer-gates'].checked = false; P.renderPresets();
    ok("presets (sandbox): a box changed by hand afterwards: no view shows pressed", pressed() === '');
    // the link read back: a shared Councils: carbon view opens coloured by carbon
    AREAS.mode = 'movements';
    location.search = '?layers=areas-county.areas-district&council=carbon';
    P.applyViewFromUrl();
    ok("⭐ presets link (sandbox): a shared Councils: carbon link opens with the districts coloured by carbon and the council boxes ticked",
       AREAS.mode === 'carbon' && byId['layer-areas-district'].checked && byId['layer-areas-county'].checked);
    ok("presets link: decode keeps only council=carbon (anything else is the default colouring)",
       P.decodeView('?council=carbon').council === 'carbon' && P.decodeView('?council=x').council === null && P.decodeView('').council === null
       && P.encodeView({ month: null, layers: [], filters: {}, council: 'movements' }, []) === '');
    // a phone: the sheet goes down after a pick
    sheetOpen = true; P.applyPreset('everything');
    ok("presets (sandbox): on the desktop a pick leaves the panel open", sheetOpen === true && calls.sheet === 0);
    phone = true; P.applyPreset('busiest-roads'); phone = false;
    ok("⭐ presets (sandbox): on the phone shell a pick lowers the Layers sheet (the panel closes, the map shows)", sheetOpen === false && calls.sheet === 1);
  }
  Object.keys(fakeGlobals).forEach(k => { if (savedGlobals[k] === undefined) delete globalThis[k]; else globalThis[k] = savedGlobals[k]; });
}

// ---- 13 Oct 2026: D45 — the map's own demo strip (on /map/ opened by itself) takes Option A, as the app's bar ----
{
  const dn = (html.match(/\n\s*#demo-notice\{([^}]*)\}/) || ["", ""])[1];
  ok("⭐ D45: the map's demo strip is light grey #F1F5F9 with red #B91C1C text and a #DC2626 edge (was ink, amber, amber)",
     /background:#F1F5F9;color:#B91C1C;border:1px solid #DC2626;/.test(dn) && !/FBBF24|#1F2024/.test(dn), dn.slice(0, 160));
  ok("D45: the strip has the red DEMO tag (CSS only, so dn.textContent still sets the words; hidden from screen readers)",
     /#demo-notice::before\{content:"DEMO";content:"DEMO" \/ "";display:inline-block;[^}]*background:#B91C1C;color:#FFFFFF;/.test(html)
     && /dn\.textContent = TENANT\.demo_notice;/.test(code));
  ok("D45: from 1024 px up the strip keeps 26 px with a 3 px red rule inside it (border-box, so nothing under it moves)",
     /body\.has-demo-notice #demo-notice\{ left:0; right:0; top:0; transform:none; border-radius:0; border-width:0 0 3px; text-align:center; padding:4px 10px 3px; height:26px; \}/.test(html)
     && /\*\{ box-sizing:border-box; \}/.test(html) && !/#demo-notice\{[^}]*border-width:0 0 1px/.test(html));
}

// 12 Oct 2026 (fix pass): wait for the sandboxes' promises, then print the summary as before
Promise.all(ASYNC_PINS).catch(e => { fail.push("an async pin block threw  " + (e && e.stack || e)); }).then(() => {
  console.log();
  for (const f of fail) console.log("  FAIL:", f);
  console.log(`\n${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
});
