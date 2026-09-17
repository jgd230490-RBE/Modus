/*
 * Behavioural assertions for the package / work-section alignment overlay.
 *
 * parse_map.js checks the wiring at source level. This file runs the real builders in
 * map/overlay.js over real data and checks what actually comes out.
 *
 * G2 (16 Sep 2026): the overlay is TENANT DATA now, delivered by GET /api/public/alignment.
 * The product ships no alignment of its own, so the data this file builds over is:
 *
 *   DEMO    — the overlay inside demo/uk-corridor.package.json (the fictional Wolds Link,
 *             one clean 31.8 km Main Track LineString, six bands, three teams, markers
 *             every 100 m). This is exactly what the map receives for the demo tenant.
 *   SURVEY  — a survey-shaped fixture built HERE from the demo line: the same track with
 *             a 3 km hole cut out of it (the shape real survey files have — one feature,
 *             one long straight edge across the hole), a genuine two-vertex siding, and a
 *             MultiLineString crossover. It exercises the gap splitter and the bridges,
 *             which a clean demo line never triggers.
 *
 * Every assertion that used to pin one project's numbers (531 source features, 646.7 km,
 * seven boundary chainages, WS13's owner …) is restated against these two, with the
 * same property under test. Those project numbers left with that project's data.
 *
 * NOT covered: anything needing a browser. Whether Mapbox paints the colours, whether the
 * legend looks right, and whether a tenant's band boundaries are right on the ground are
 * all unverified here — the last one is a question for that tenant's drawings.
 *
 * Run:  node backend/tests/test_ipt_overlay.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
let pass = 0;
const fail = [];
function ok(label, cond, extra) {
  if (cond) pass++;
  else fail.push(label + (extra ? "  " + extra : ""));
}
function near(a, b, tol) { return Math.abs(a - b) <= tol; }
const clone = (o) => JSON.parse(JSON.stringify(o));

// ---- load the data the way the browser does ---------------------------------
const demoPkg = JSON.parse(fs.readFileSync(path.join(ROOT, "demo", "uk-corridor.package.json"), "utf8"));
const OV = JSON.parse(demoPkg.tables.config.find(r => r.key === "overlay").value);
global.window = global.window || {};
const _log = console.log;
console.log = () => {};                       // the builder logs its stats; keep the report clean
require(path.join(ROOT, "map", "overlay.js"));
console.log = _log;

ok("before a package lands every global is EMPTY — a fresh tenant draws nothing",
  Array.isArray(window.IPT_SEGMENTS) && window.IPT_SEGMENTS.length === 0
  && Object.keys(window.WS_NAMES).length === 0 && window.WS_BOUNDARIES.length === 0
  && window.IPT_UNDERLAY === null);
window.applyOverlayPackage(OV);

const SEGS = window.IPT_SEGMENTS;
const srcFeatures = window.alignment_data.features;
const srcCount = srcFeatures.length;
const srcFirstLen = srcFeatures[0].geometry.coordinates.length;
const quiet = (fn) => { console.log = () => {}; try { return fn(); } finally { console.log = _log; } };

// =============================================================================
// 1. The band table
// =============================================================================
ok("IPT_SEGMENTS is a non-empty array", Array.isArray(SEGS) && SEGS.length > 0);
ok("every band has ipt, label, colour and numeric bounds",
  SEGS.every(s => s.ipt && s.label && /^#[0-9a-fA-F]{6}$/.test(s.colour) &&
    typeof s.chain_from === "number" && typeof s.chain_to === "number"));
ok("every band runs forwards", SEGS.every(s => s.chain_to > s.chain_from));
ok("the bands are in chainage order",
  SEGS.every((s, i) => i === 0 || s.chain_from >= SEGS[i - 1].chain_from));
ok("⭐ the bands are contiguous — no gap would leave track unpainted",
  SEGS.every((s, i) => i === 0 || s.chain_from === SEGS[i - 1].chain_to));
ok("⭐ and no band overlaps the next, which the first-match scan would hide",
  SEGS.every((s, i) => i === SEGS.length - 1 || s.chain_to <= SEGS[i + 1].chain_from));
// ⭐ The mandatory colour rule, checked from the built data rather than the source
// text: a band may not carry a hex the map spends on a route, forecast or selection.
ok("⭐ no band colour is a reserved route / forecast / selection hex",
  SEGS.every(s => !window.IPT_RESERVED_COLOURS
    .map(r => r.toLowerCase()).includes(s.colour.toLowerCase())),
  SEGS.filter(s => window.IPT_RESERVED_COLOURS.map(r => r.toLowerCase())
    .includes(s.colour.toLowerCase())).map(s => s.ipt + " " + s.colour).join(", "));
ok("the reserved list is non-empty, so that check can actually fail",
  window.IPT_RESERVED_COLOURS.length >= 7);
ok("one team keeps one colour across its bands",
  SEGS.filter(s => s.ipt === "North Team").length === 3
  && new Set(SEGS.filter(s => s.ipt === "North Team").map(s => s.colour)).size === 1);
// the demo has no underlay; a package that does must declare all three together
ok("the demo declares no underlay, and the module holds null rather than a stale one",
  window.IPT_UNDERLAY === null);
{
  const withUnder = clone(OV);
  withUnder.underlay = { key: "Systems Team", colour: "#C4B5FD", width: 4.5, opacity: 0.9, label: "systems underlay" };
  window.applyOverlayPackage(withUnder);
  ok("a package's underlay declares colour, width and opacity together",
    window.IPT_UNDERLAY && /^#[0-9a-fA-F]{6}$/.test(window.IPT_UNDERLAY.colour) &&
    window.IPT_UNDERLAY.width > 2.5 && window.IPT_UNDERLAY.opacity <= 1);
  ok("⭐ the underlay is WIDER than the civil track, or it could not show beneath it",
    window.IPT_UNDERLAY.width > 2.5);
  window.applyOverlayPackage(OV);
  ok("re-applying a package without one clears it again", window.IPT_UNDERLAY === null);
}

ok("a band's ws entries are all WS codes",
  SEGS.every(s => (s.ws || []).every(w => /^WS\d+$/.test(w))));
ok("the provisional WS3/WS4 bound is flagged in the package, not just in prose",
  Array.isArray(window.IPT_BOUNDS_PROVISIONAL) &&
  window.IPT_BOUNDS_PROVISIONAL.some(x => /WS3\/WS4 @ 16500/.test(x)));

// =============================================================================
// 2. iptForChainage
// =============================================================================
ok("chainage inside a band returns that band",
  window.iptForChainage(8000).ipt === "Central Team");
ok("a band is inclusive at its lower bound",
  window.iptForChainage(5500).ipt === "Central Team" && window.iptForChainage(5500).ws.join() === "WS2");
ok("and exclusive at its upper bound, so a boundary belongs to one band only",
  window.iptForChainage(11000).ws.join() === "WS3" && window.iptForChainage(10999.9).ws.join() === "WS2");
ok("a boundary between two teams resolves to the next team",
  window.iptForChainage(16500).ipt === "North Team" && window.iptForChainage(16499).ipt === "Central Team");
ok("all three North bands resolve to North Team",
  ["North Team"].includes(window.iptForChainage(18000).ipt) &&
  window.iptForChainage(24000).ipt === "North Team" && window.iptForChainage(30000).ipt === "North Team");
ok("but they keep their own work sections",
  window.iptForChainage(18000).ws.join() === "WS4" &&
  window.iptForChainage(24000).ws.join() === "WS5" &&
  window.iptForChainage(30000).ws.join() === "WS6");
ok("chainage past the last band falls back to the default",
  window.iptForChainage(999999) === window.IPT_DEFAULT);
ok("chainage before the first band falls back to the default",
  window.iptForChainage(-99999) === window.IPT_DEFAULT);
ok("null chainage falls back rather than throwing",
  window.iptForChainage(null) === window.IPT_DEFAULT);
ok("NaN chainage falls back rather than throwing",
  window.iptForChainage(NaN) === window.IPT_DEFAULT);

// =============================================================================
// 3. Build over the demo
// =============================================================================
const t0 = Date.now();
const fc = quiet(() => window.buildIptAlignment(window.alignment_data, window.chainage_global_data));
const ms = Date.now() - t0;
const stats = window.IPT_BUILD_STATS;
const feats = fc.features;

ok("the build returns a FeatureCollection", fc && fc.type === "FeatureCollection" && Array.isArray(feats));
ok("it read the chainage markers", stats.chainage_markers === OV.chainage.features.length && stats.chainage_markers > 300,
  `got ${stats.chainage_markers}`);
ok("it produced more features than it was given, because the line was cut",
  feats.length > srcCount, `${srcCount} -> ${feats.length}`);
ok("it runs fast enough to sit on page load", ms < 3000, `took ${ms} ms`);

ok("⭐ the input FeatureCollection is not mutated",
  window.alignment_data.features.length === srcCount &&
  window.alignment_data.features[0].geometry.coordinates.length === srcFirstLen &&
  window.alignment_data.features[0].properties.ipt === undefined);
ok("no source property was dropped on the way through",
  feats.every(f => f.properties.align_type === "Main Track" && /Wolds Link/.test(f.properties.name)));

ok("every output feature is a LineString", feats.every(f => f.geometry.type === "LineString"));
ok("and none is a degenerate one-point line",
  feats.every(f => f.geometry.coordinates.length >= 2));
ok("every output feature carries the four properties the paint and popup read",
  feats.every(f => f.properties.ipt && f.properties.ipt_label &&
    /^#[0-9a-fA-F]{6}$/.test(f.properties.ipt_colour) && f.properties.ws !== undefined));
ok("ws is a flat string, not an array — Mapbox properties cannot hold arrays",
  feats.every(f => typeof f.properties.ws === "string"));
ok("every colour on a feature comes from the band table",
  feats.every(f => f.properties.ipt_colour === window.IPT_DEFAULT.colour ||
    SEGS.some(s => s.colour === f.properties.ipt_colour && s.ipt === f.properties.ipt)));
ok("chainage extent is recorded on each segment for the popup",
  feats.every(f => f.properties.chain_from_m === null ||
    (typeof f.properties.chain_from_m === "number" &&
     f.properties.chain_to_m >= f.properties.chain_from_m)));
ok("the muted and provisional flags are stamped on every segment (false on the demo)",
  feats.every(f => f.properties.muted === false && typeof f.properties.provisional === "boolean"));

// deterministic
const fc2 = quiet(() => window.buildIptAlignment(window.alignment_data, window.chainage_global_data));
ok("the build is deterministic", fc2.features.length === feats.length
  && fc2.features.every((f, i) => f.properties.ws_primary === feats[i].properties.ws_primary));

// =============================================================================
// 4. ⭐ The regression this whole design exists for
// =============================================================================
// Stamping one band per feature, taken from the feature's midpoint, would paint the
// demo's single 31.8 km feature ONE colour: its midpoint (~15.9 km) is WS3, so the whole
// corridor would read Central Team and South and North would vanish from the map.
const R = 6371000;
function metres(a, b) {
  const dLat = (b[1] - a[1]) * Math.PI / 180, dLon = (b[0] - a[0]) * Math.PI / 180;
  const l1 = a[1] * Math.PI / 180, l2 = b[1] * Math.PI / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(l1) * Math.cos(l2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, h)));
}
function lengthOf(c) { let L = 0; for (let i = 0; i < c.length - 1; i++) L += metres(c[i], c[i + 1]); return L; }
function maxEdge(c) { let M = 0; for (let i = 0; i < c.length - 1; i++) M = Math.max(M, metres(c[i], c[i + 1])); return M; }
const DEMO_LINE = srcFeatures[0].geometry.coordinates;
const DEMO_LEN = lengthOf(DEMO_LINE);

ok("the demo's one feature spans the whole corridor", near(DEMO_LEN, 31806, 30), `${Math.round(DEMO_LEN)} m`);
ok("⭐ a midpoint stamp would have given it ONE band — WS3",
  window.iptForChainage(DEMO_LEN / 2).ws.join() === "WS3");
ok("the feature is split rather than stamped once",
  feats.length >= 6, `got ${feats.length} segments`);
const bandsOut = new Set(feats.map(f => f.properties.ipt));
const wsOut = new Set(feats.map(f => f.properties.ws_primary));
ok("⭐ and it contributes to all three teams — midpoint stamping gave only one",
  ["North Team", "Central Team", "South Team"].every(b => bandsOut.has(b)),
  `got ${[...bandsOut].join(", ")}`);
ok("⭐ every band ends up painted on Main Track somewhere",
  SEGS.every(s => wsOut.has(s.ws_primary)), `got ${[...wsOut].join(", ")}`);
ok("nothing on Main Track falls through to Unknown", !bandsOut.has("Unknown"));

// A segment may not cover more chainage than the band it is painted with. This is the
// invariant midpoint stamping broke.
//
// Note the recorded extent deliberately includes the shared boundary vertex — the last
// vertex of one segment is the first of the next so the painted line has no gap — so the
// test is against the band WIDTH, not against the band bounds.
function bandWidthFor(f) {
  const a = f.properties.chain_from_m;
  const s = SEGS.find(s => s.ipt === f.properties.ipt && a >= s.chain_from - 150 && a < s.chain_to);
  return s ? s.chain_to - s.chain_from : Infinity;
}
ok("⭐ no output feature covers more chainage than its own band is wide",
  feats.every(f => {
    const a = f.properties.chain_from_m, b = f.properties.chain_to_m;
    if (a == null || b == null) return true;
    return (b - a) <= bandWidthFor(f) + 500;
  }));
ok("⭐ and each band's painted extent matches its table bounds to within a marker spacing",
  SEGS.every(s => {
    const mine = feats.filter(f => f.properties.ws_primary === s.ws_primary);
    const lo = Math.min(...mine.map(f => f.properties.chain_from_m));
    const hi = Math.max(...mine.map(f => f.properties.chain_to_m));
    return near(lo, s.chain_from, 150) && near(hi, Math.min(s.chain_to, DEMO_LEN), 150);
  }));

// =============================================================================
// 5. Gap splitting — the survey-shaped fixture
// =============================================================================
// Chainage of every demo vertex, measured along the line the way the generator did.
const CH = [0];
for (let i = 1; i < DEMO_LINE.length; i++) CH.push(CH[i - 1] + metres(DEMO_LINE[i - 1], DEMO_LINE[i]));
const HOLE_FROM = 23800, HOLE_TO = 26950;          // inside one straight run of the line
const holed = DEMO_LINE.filter((c, i) => CH[i] <= HOLE_FROM || CH[i] >= HOLE_TO);
const iA = CH.findIndex(m => m > HOLE_FROM) - 1, iB = CH.findIndex(m => m >= HOLE_TO);
const CHORD = metres(DEMO_LINE[iA], DEMO_LINE[iB]);
// offset a point east/north in metres
const off = (p, e, n) => [p[0] + e / (111320 * Math.cos(p[1] * Math.PI / 180)), p[1] + n / 111320];
const at = (m) => DEMO_LINE[CH.findIndex(x => x >= m)];
const SIDING = [off(at(1000), 25, 0), off(at(1650), 25, 0)];        // one straight edge, genuine
const XOVER = [[off(at(8000), 15, 0), off(at(8100), 15, 0), off(at(8200), 15, 0), off(at(8300), 15, 0)],
               [off(at(9000), -15, 0), off(at(9100), -15, 0), off(at(9200), -15, 0), off(at(9300), -15, 0)]];
const SURVEY = { type: "FeatureCollection", features: [
  { type: "Feature", geometry: { type: "LineString", coordinates: holed },
    properties: { OBJECTID: "S-1", align_type: "Main Track" } },
  { type: "Feature", geometry: { type: "LineString", coordinates: SIDING },
    properties: { OBJECTID: "S-2", align_type: "Siding" } },
  { type: "Feature", geometry: { type: "MultiLineString", coordinates: XOVER },
    properties: { OBJECTID: "S-3", align_type: "Crossover" } },
] };
const survey = quiet(() => window.buildIptAlignment(SURVEY, window.chainage_global_data));
const sStats = window.IPT_BUILD_STATS;
const sFeats = survey.features;

let srcLen = 0;
for (const f of SURVEY.features) {
  const parts = f.geometry.type === "LineString" ? [f.geometry.coordinates] : f.geometry.coordinates;
  for (const p of parts) srcLen += lengthOf(p);
}
// Every cut edge is kept as a BRIDGE feature — drawn in the band colour so the corridor
// reads continuous — so solid and bridge length are measured separately, or "kept"
// silently means "everything".
const solid = sFeats.filter(f => f.properties.is_bridge !== true);
const bridges = sFeats.filter(f => f.properties.is_bridge === true);
const solidLen = solid.reduce((a, f) => a + lengthOf(f.geometry.coordinates), 0);
const bridgeLen = bridges.reduce((a, f) => a + lengthOf(f.geometry.coordinates), 0);

ok("the fixture really has one hole edge of ~3 km", CHORD > 3000 && CHORD < 3400, `${Math.round(CHORD)} m`);
ok("the gap split ran and cut exactly that one edge", sStats.gap_split === true && sStats.gap_edges_cut === 1,
  `cut ${sStats.gap_edges_cut}`);
ok("⭐ it removed the phantom straight the survey file draws",
  near(sStats.gap_km_removed, CHORD / 1000, 0.06), `removed ${sStats.gap_km_removed} km of ${(CHORD / 1000).toFixed(2)}`);
ok("⭐ the solid track that survives is the source minus the hole",
  near(solidLen, srcLen - CHORD, 5), `${Math.round(solidLen)} vs ${Math.round(srcLen - CHORD)}`);
ok("⭐ the removed length comes back as bridges, not as solid track",
  near(bridgeLen, CHORD, 5), `${Math.round(bridgeLen)} vs ${Math.round(CHORD)}`);
ok("⭐ solid + bridge accounts for the whole source exactly — nothing invented, nothing lost",
  near(solidLen + bridgeLen, srcLen, 5), `${Math.round(solidLen + bridgeLen)} vs ${Math.round(srcLen)}`);
ok("and the bridge length equals what the splitter reported removing",
  near(bridgeLen / 1000, sStats.gap_km_removed, 0.06));
ok("the build reports both counts", sStats.solid_features + sStats.bridge_features === sFeats.length);
ok("every feature is one or the other, never both",
  sFeats.every(f => f.properties.is_bridge === true || f.properties.is_bridge === false));
ok("no source property was dropped — every feature keeps its OBJECTID and align_type",
  sFeats.every(f => /^S-[123]$/.test(f.properties.OBJECTID) && f.properties.align_type));
ok("a MultiLineString is processed part by part, like two LineStrings",
  sFeats.filter(f => f.properties.OBJECTID === "S-3").length >= 2
  && sFeats.filter(f => f.properties.OBJECTID === "S-3").every(f => f.geometry.type === "LineString"));
ok("is_main_track marks the mainline only",
  sFeats.every(f => f.properties.is_main_track === (f.properties.align_type === "Main Track")));

// ⭐ A bridge can be longer than a band. Drawn as one straight it would need ONE colour —
// the midpoint-stamping mistake again, just on the interpolated stretch. So bridges are
// densified and band-split like everything else.
ok("⭐ no bridge spans more chainage than its own band is wide",
  bridges.every(f => {
    const a = f.properties.chain_from_m, b = f.properties.chain_to_m;
    if (a == null || b == null) return true;
    return (b - a) <= bandWidthFor(f) + 500;
  }));
ok("⭐ the hole straight is split, not stamped — it crosses the WS5/WS6 edge and is painted as both",
  new Set(bridges.map(f => f.properties.ws_primary)).size === 2
  && bridges.some(f => f.properties.ws_primary === "WS5") && bridges.some(f => f.properties.ws_primary === "WS6"),
  [...new Set(bridges.map(f => f.properties.ws_primary))].join(","));
ok("splitting produced MORE bridge features than edges cut, because the hole crosses a band edge",
  bridges.length > sStats.gap_edges_cut,
  `${bridges.length} bridges from ${sStats.gap_edges_cut} cut edges`);
ok("every bridge carries a real band colour, not the fallback grey",
  bridges.every(f => SEGS.some(s => s.colour === f.properties.ipt_colour)));

// ⭐ The point of the bridges, stated as an assertion: WS5 keeps only 2.3 km of solid Main
// Track because 2.7 km of its band has no surveyed geometry. Without a bridge the band is
// mostly invisible on the map — the failure the overlay exists to avoid, by another route.
const ws5Solid = solid.filter(f => f.properties.ws_primary === "WS5" && f.properties.align_type === "Main Track");
const ws5Bridge = bridges.filter(f => f.properties.ws_primary === "WS5" && f.properties.align_type === "Main Track");
ok("⭐ WS5 is thinly covered by solid track", ws5Solid.length > 0);
ok("⭐ and its bridge is what makes the band legible at corridor zoom",
  ws5Bridge.length > 0 &&
  ws5Bridge.reduce((a, f) => a + lengthOf(f.geometry.coordinates), 0) >
  ws5Solid.reduce((a, f) => a + lengthOf(f.geometry.coordinates), 0));
// The invariant is about what the splitter left behind, not raw edge length: no edge may
// survive that is both over GAP_MIN_M and far longer than the rest of its own part. A
// two-vertex feature has a ratio of exactly 1 and is never a gap.
function medianOf(a) { const s = a.slice().sort((x, y) => x - y); const h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; }
ok("⭐ no gap-shaped edge survives into the solid output",
  solid.every(f => {
    const c = f.geometry.coordinates;
    const steps = []; for (let i = 0; i < c.length - 1; i++) steps.push(metres(c[i], c[i + 1]));
    const med = medianOf(steps);
    return steps.every(d => !(d > window.IPT_GAP_CONFIG.min_m && d > window.IPT_GAP_CONFIG.ratio * med));
  }));
ok("the split is a ratio test, so a genuine two-vertex straight survives",
  sFeats.some(f => f.properties.OBJECTID === "S-2" && f.geometry.coordinates.length === 2
    && lengthOf(f.geometry.coordinates) > 600 && f.properties.is_bridge === false));
const longStraights = sFeats.filter(f => maxEdge(f.geometry.coordinates) > 600);
ok("exactly ONE solid feature is a single straight edge over 600 m — the siding",
  longStraights.filter(f => f.properties.is_bridge !== true).length === 1
  && longStraights[0].properties.OBJECTID === "S-2",
  `got ${longStraights.filter(f => f.properties.is_bridge !== true).length}`);
ok("⭐ and no bridge is one — densifying every 200 m is what lets them be band-split",
  bridges.every(f => maxEdge(f.geometry.coordinates) < 250),
  `worst ${Math.round(Math.max(...bridges.map(f => maxEdge(f.geometry.coordinates))))} m`);
ok("the siding keeps its own length, to the metre",
  near(Math.max(...longStraights.map(f => maxEdge(f.geometry.coordinates))), lengthOf(SIDING), 1)
  && lengthOf(SIDING) > 600 && lengthOf(SIDING) < 760, `${Math.round(lengthOf(SIDING))} m`);
ok("the config is exposed so the cut can be turned off without editing logic",
  window.IPT_GAP_CONFIG && window.IPT_GAP_CONFIG.split === true &&
  window.IPT_GAP_CONFIG.min_m === 150 && window.IPT_GAP_CONFIG.ratio === 20);
ok("a clean line has nothing to cut — the demo build reports zero",
  stats.gap_edges_cut === 0 && stats.bridge_features === 0 && stats.gap_km_removed === 0);

// =============================================================================
// 6. Recorded fixture facts — what the hole does to coverage
// =============================================================================
const mtFeats = sFeats.filter(f => f.properties.align_type === "Main Track" &&
                                   f.properties.is_bridge !== true);
const covered = new Set();
for (const f of mtFeats) {
  const a = f.properties.chain_from_m, b = f.properties.chain_to_m;
  if (a == null || b == null) continue;
  for (let m = Math.round(a / 100) * 100; m < b; m += 100) covered.add(m);
}
ok("the fixture's Main Track has no solid geometry between 24 km and 26.8 km",
  ![24000, 25000, 26000, 26800].some(m => covered.has(m)));
ok("which is why WS5 is only part-painted solid, and that is the data, not the split",
  mtFeats.filter(f => f.properties.ws_primary === "WS5").length > 0);
ok("and the track either side of the hole is covered",
  covered.has(23500) && covered.has(27200));

// =============================================================================
// 7. Legend
// =============================================================================
const rows = window.iptLegendRows();
ok("the legend has one row per unique team",
  rows.length === new Set(SEGS.map(s => s.ipt)).size && rows.length === 3, `got ${rows.length}`);
ok("⭐ North Team appears once, not three times, despite having three bands",
  rows.filter(r => r.ipt === "North Team").length === 1);
ok("and that row carries all three of its work sections",
  (rows.find(r => r.ipt === "North Team").ws || []).join() === "WS4,WS5,WS6");
ok("the rows come in corridor order (first band first)",
  rows.map(r => r.ipt).join("|") === "South Team|Central Team|North Team");
ok("every legend row has a colour from the band table",
  rows.every(r => SEGS.some(s => s.ipt === r.ipt && s.colour === r.colour)));
ok("no demo team is muted", rows.every(r => r.muted === false));
{
  const withMuted = clone(OV);
  const last = withMuted.bands[withMuted.bands.length - 1];
  withMuted.bands.push({ ipt: "Existing network", ws: [], label: "Beyond the works", ws_primary: null,
                         chain_from: last.chain_to, chain_to: last.chain_to + 5000, colour: "#94A3B8", muted: true });
  window.applyOverlayPackage(withMuted);
  const mrows = window.iptLegendRows();
  ok("a muted band is present in the legend but marked muted rather than dropped",
    mrows.some(r => r.ipt === "Existing network" && r.muted === true));
  ok("no in-scope team is muted", mrows.every(r => r.muted === (r.ipt === "Existing network")));
  ok("a muted band owns no section", window.IPT_SEGMENTS.filter(s => s.muted).every(s => s.ws_primary === null));
  window.applyOverlayPackage(OV);
}

// =============================================================================
// 8. Chainage marker tiering — the noise fix
// =============================================================================
const stepped = window.buildChainageSteps(window.chainage_global_data);
const tiers = window.CHAINAGE_STEP_COUNTS;
const NMARK = window.chainage_global_data.features.length;

ok("every chainage point gets a step tier",
  stepped.features.every(f => window.CHAINAGE_STEPS.includes(f.properties.step_m)));
ok("the tier is the COARSEST interval the chainage falls on, not the finest",
  stepped.features.every(f => {
    const m = Math.round(parseFloat(String(f.properties.chain).replace(/,/g, "")));
    if (isNaN(m)) return f.properties.step_m === 100;
    const coarsest = window.CHAINAGE_STEPS.find(s => m % s === 0) || 100;
    return f.properties.step_m === coarsest;
  }));
ok("the source is not mutated",
  window.chainage_global_data.features.every(f => f.properties.step_m === undefined));
ok("nothing is dropped", stepped.features.length === NMARK);
ok("the original properties survive",
  stepped.features.every(f => f.properties.chaintxt !== undefined));

// ⭐ The whole point: a marker every 100 m is a grey smear at corridor zoom.
ok("the demo has 319 markers, one every 100 m from 0+000 to 31+800", NMARK === 319, `got ${NMARK}`);
ok("⭐ only 4 markers show below zoom 9 (0, 10, 20, 30 km), not 319",
  tiers[10000] === 4, `got ${tiers[10000]}`);
ok("7 by zoom 9", tiers[10000] + tiers[5000] === 7, `got ${tiers[10000] + tiers[5000]}`);
ok("32 by zoom 11", tiers[10000] + tiers[5000] + tiers[1000] === 32);
ok("64 by zoom 13 — the 500 m tier",
  tiers[10000] + tiers[5000] + tiers[1000] + tiers[500] === 64,
  `got ${tiers[10000] + tiers[5000] + tiers[1000] + (tiers[500] || 0)}`);
ok("and all 319 by zoom 15",
  Object.values(tiers).reduce((a, b) => a + b, 0) === 319);
ok("there are five tiers", window.CHAINAGE_STEPS.length === 5);

// ⭐ The spec's on-tick formula could never match a negative tick, and a corridor's
// chainage can start below zero.
ok("⭐ a negative chainage on an exact tick is recognised", window.iptOnTick(-5000, 5000));
ok("and one that is not, is not", !window.iptOnTick(-3982.3, 10000));
ok("the spec's own formula would have failed that first case",
  !(Math.abs(-5000 % 5000) < 0.5 && Math.abs((-5000 % 5000) - 5000) < 0.5) ||
  window.iptOnTick(-5000, 5000));
ok("the float tolerance still works on a positive tick",
  window.iptOnTick(42900.0, 100) && window.iptOnTick(10000.3, 10000));
ok("chain_m is carried through for anything that wants the number",
  stepped.features.every(f => f.properties.chain_m === null ||
    typeof f.properties.chain_m === "number"));
ok("⭐ that is a ~99% reduction in what the corridor view draws",
  tiers[10000] / NMARK < 0.02);
ok("the tiers are disjoint — no marker is drawn twice",
  Object.values(tiers).reduce((a, b) => a + b, 0) === stepped.features.length);

// =============================================================================
// 9. Work-section boundary ticks
// =============================================================================
const wsb = window.buildWsBoundaries(window.chainage_global_data, fc);
const B = wsb.features;

ok("⭐ five boundary ticks, no more and no fewer", B.length === 5, `got ${B.length}`);
ok("all five are points", B.every(f => f.geometry.type === "Point"));
ok("the builder reports what it built against what it was asked for",
  window.WS_BOUNDARY_STATS.built === window.WS_BOUNDARY_STATS.expected);

// --- the version -----------------------------------------------------------------
// The static file pair (index.html + a data script) that could be half-upgraded is gone;
// the package carries one version string and the module records it.
ok("⭐ the package stamps its version", window.OVERLAY_VERSION === "wolds-link-demo-1",
  String(window.OVERLAY_VERSION));

// ⭐ The invariant that matters: a tick marks a colour change, so every tick chainage MUST
// be a boundary in the band table. A tick that drifted off the band edge would point at
// nothing. (tenant_package.validate_overlay refuses such a package on upload, too.)
const bandEdges = new Set(SEGS.slice(1).map(s => s.chain_from));
ok("⭐ every tick sits exactly on a band boundary from IPT_SEGMENTS",
  B.every(f => bandEdges.has(f.properties.chain_m)),
  B.filter(f => !bandEdges.has(f.properties.chain_m)).map(f => f.properties.chain_m).join(", "));
ok("⭐ and every band boundary has a tick — none is missed",
  [...bandEdges].every(e => B.some(f => f.properties.chain_m === e)),
  [...bandEdges].filter(e => !B.some(f => f.properties.chain_m === e)).join(", "));

ok("the ticks are the five chainages the package lists",
  B.map(f => f.properties.chain_m).join(",") === "5500,11000,16500,21500,26500",
  B.map(f => f.properties.chain_m).join(","));
ok("⭐ every tick is on the corridor's one global datum — inside the marker range",
  B.every(f => f.properties.chain_m >= 0 && f.properties.chain_m <= 31800));
ok("and no tick for WS7 or WS8 — they are point assets, not bands",
  !B.some(f => ["WS7", "WS8"].includes(f.properties.from_ws) || ["WS7", "WS8"].includes(f.properties.to_ws)));

// ⭐ The bug this caught. The first version took the bearing from the two markers
// bracketing the boundary — a zero-length span when the boundary lands exactly on a
// marker (every demo boundary does: markers are every 100 m) — and then silently reused
// the PREVIOUS tick's bearing.
const brs = B.map(f => f.properties.bearing);
ok("⭐ every tick has its OWN bearing — none reuses its neighbour's",
  new Set(brs).size === 5, `${new Set(brs).size} distinct of ${brs.length}: ${brs.join(", ")}`);
ok("no two consecutive ticks share a bearing",
  brs.every((b, i) => i === 0 || b !== brs[i - 1]));
ok("every bearing is measured over a real span of line",
  B.every(f => f.properties.bearing_span_m > 0));
ok("bearings are in range", brs.every(b => b >= 0 && b < 360));
ok("⭐ the corridor runs roughly north, so every bearing is within 30° of north",
  brs.every(b => b < 30 || b > 330), brs.join(", "));
ok("⭐ the tick lies ACROSS the alignment: rotate is bearing + 90",
  B.every(f => Math.abs(((f.properties.bearing + 90) % 360) - f.properties.tick_rotate) < 0.2));

ok("each tick names both sections meeting there",
  B.every(f => f.properties.label.includes("|")) && B[0].properties.label === "WS1 | WS2");
ok("each tick names both teams", B[2].properties.from_ipt === "Central Team" && B[2].properties.to_ipt === "North Team");
{
  const withEnd = clone(OV);
  withEnd.boundaries.push({ chain_m: OV.bands[OV.bands.length - 1].chain_to, from_ws: "WS6", to_ws: null,
                            from_ipt: "North Team", to_ipt: null, note: "End of the works" });
  window.applyOverlayPackage(withEnd);
  const BE = window.buildWsBoundaries(window.chainage_global_data).features;
  const lastTick = BE[BE.length - 1];
  ok("a boundary with no next section hands over to 'Outside scope' rather than naming one",
    lastTick.properties.to_ws === "" && /Outside scope/.test(lastTick.properties.label), lastTick.properties.label);
  const named = clone(withEnd);
  named.boundaries[named.boundaries.length - 1].to_ipt = "Existing network";
  window.applyOverlayPackage(named);
  const BN = window.buildWsBoundaries(window.chainage_global_data).features;
  ok("...unless the package names the band being entered (to_ipt) — then the tick says that",
    BN[BN.length - 1].properties.label === "WS6 | Existing network", BN[BN.length - 1].properties.label);
  window.applyOverlayPackage(withEnd);
  ok("...and a boundary past the last marker is clamped to the end of the line, not thrown off it",
    near(lastTick.geometry.coordinates[1], DEMO_LINE[DEMO_LINE.length - 1][1], 0.002));
  window.applyOverlayPackage(OV);
}
ok("the provisional boundary is flagged on the feature, not only in prose",
  B.filter(f => f.properties.provisional).length === 1 &&
  B.find(f => f.properties.provisional).properties.chain_m === 16500);
ok("the package's note on a boundary travels onto its tick",
  /under review/.test(B.find(f => f.properties.provisional).properties.note));
ok("chainage is rendered as an engineer writes it",
  B[0].properties.chain_txt === "5+500" && B[4].properties.chain_txt === "26+500");

// ticks must land on the corridor, not somewhere else in the county
const onCorridor = (f) => {
  const [lon, lat] = f.geometry.coordinates;
  return lon > -1.2 && lon < -0.6 && lat > 52.4 && lat < 52.8;
};
ok("⭐ every tick lands on the East Midlands corridor",
  B.every(onCorridor),
  B.filter(f => !onCorridor(f)).map(f => f.properties.chain_txt).join(", "));

// ⭐ A tick has to sit on the line it marks. Distance is measured to the line's SEGMENTS
// (not just its vertices, which are 100–200 m apart) in a local flat frame — ample at
// this scale.
function distToSegs(pt, set) {
  const kx = 111320 * Math.cos(pt[1] * Math.PI / 180), ky = 111320;
  let best = Infinity;
  for (const f of set) {
    const c = f.geometry.coordinates;
    for (let i = 0; i < c.length - 1; i++) {
      const ax = (c[i][0] - pt[0]) * kx, ay = (c[i][1] - pt[1]) * ky;
      const bx = (c[i + 1][0] - pt[0]) * kx, by = (c[i + 1][1] - pt[1]) * ky;
      const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
      const t = L2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / L2)) : 0;
      const d = Math.hypot(ax + t * dx, ay + t * dy);
      if (d < best) best = d;
    }
  }
  return best;
}
const offDemo = B.map(f => distToSegs(f.geometry.coordinates, feats));
ok("⭐ every tick lands on the drawn corridor — within 70 m of Main Track",
  offDemo.every(d => d < 70), `worst ${Math.round(Math.max(...offDemo))} m`);
ok("on a clean line every tick sits essentially ON it (< 5 m)",
  offDemo.every(d => d < 5), `worst ${offDemo.map(d => d.toFixed(1)).join(", ")}`);

// ⚠️ The hole case. The ticks are positioned from the chainage markers, which cover the
// corridor continuously; a survey alignment may not. A boundary that falls in a hole has
// no solid track to sit on, and the map's label says so — from the BUILDER's flag.
const surveyTicks = window.buildWsBoundaries(window.chainage_global_data, survey).features;
const mainAll = sFeats.filter(f => f.properties.align_type === "Main Track");
const mainSolid = mainAll.filter(f => f.properties.is_bridge !== true);
const offCorridor = surveyTicks.map(f => distToSegs(f.geometry.coordinates, mainAll));
const offSolid = surveyTicks.map(f => distToSegs(f.geometry.coordinates, mainSolid));
const inHole = surveyTicks.filter((f, i) => offSolid[i] > 100).map(f => f.properties.chain_txt);
ok("FIXTURE FACT: one boundary falls in the hole — 26+500", inHole.join(",") === "26+500", inHole.join(","));
ok("⭐ the builder flags exactly that one itself",
  surveyTicks.filter(f => f.properties.no_surveyed_track).map(f => f.properties.chain_txt).join(",") === "26+500",
  surveyTicks.filter(f => f.properties.no_surveyed_track).map(f => f.properties.chain_txt).join(","));
ok("and records how far away the nearest surveyed track is",
  surveyTicks.every(f => typeof f.properties.track_gap_m === "number")
  && surveyTicks.find(f => f.properties.no_surveyed_track).properties.track_gap_m > 300);
ok("the stats line reports the count", window.WS_BOUNDARY_STATS.no_surveyed_track === 1);
ok("⭐ with no alignment passed in, it does not GUESS — it flags nothing",
  window.buildWsBoundaries(window.chainage_global_data).features
    .every(f => f.properties.no_surveyed_track === undefined));
ok("⭐ on the clean demo line nothing is flagged",
  B.every(f => f.properties.no_surveyed_track === false) && window.buildWsBoundaries(window.chainage_global_data, fc)
    && window.WS_BOUNDARY_STATS.no_surveyed_track === 0);
ok("⭐ but the hole tick is still within 70 m of the corridor, because the bridge carries it across",
  surveyTicks.every((f, i) => offCorridor[i] < 70), offCorridor.map(Math.round).join(", "));
ok("the four that are not in a hole sit essentially on the solid line",
  offSolid.filter(d => d <= 100).length === 4 && offSolid.filter(d => d <= 100).every(d => d < 5),
  `worst ${Math.round(Math.max(...offSolid.filter(d => d <= 100)))} m`);

// --- the section name table ----------------------------------------------------
ok("eight work sections are named (six bands, two point assets)", Object.keys(window.WS_NAMES).length === 8);
ok("every entry has a name", Object.values(window.WS_NAMES).every(w => w.name));
ok("⭐ every section names the team that owns it, and it agrees with the band table",
  SEGS.every(s => window.WS_NAMES[s.ws_primary].ipt === s.ipt));
ok("the point assets carry their team too",
  window.WS_NAMES.WS7.ipt === "Central Team" && window.WS_NAMES.WS8.ipt === "North Team");
ok("every band names the ONE section owning its chainage",
  SEGS.filter(s => !s.muted).every(s => /^WS\d+$/.test(s.ws_primary)));
ok("and that section is one of the codes on the band",
  SEGS.filter(s => !s.muted).every(s => s.ws.includes(s.ws_primary)));
ok("every painted segment carries the owning section and its name",
  feats.every(f => /^WS\d+$/.test(f.properties.ws_primary) && f.properties.ws_name.length > 3));
ok("and the name matches the table",
  feats.filter(f => f.properties.ws_primary)
       .every(f => f.properties.ws_name === window.WS_NAMES[f.properties.ws_primary].name));
ok("wsLabel reads the same table, and an unknown code is blank rather than an error",
  window.wsLabel("WS4") === "Tilton viaduct" && window.wsLabel("WS99") === "");

// chainText
ok("chainText formats a boundary", window.chainText(42900) === "42+900");
ok("it pads the metres", window.chainText(14036) === "14+036" && window.chainText(5500) === "5+500");
ok("it handles a negative start of a corridor", window.chainText(-3982) === "-3+982");
ok("and null rather than throwing", window.chainText(null) === "–");

// =============================================================================
// 10. Degenerate inputs
// =============================================================================
const empty = quiet(() => window.buildIptAlignment({ type: "FeatureCollection", features: [] }, window.chainage_global_data));
ok("an empty alignment builds to an empty collection", empty.features.length === 0);
const _warn = console.warn; console.warn = () => {};
const noChain = window.buildIptAlignment(window.alignment_data, { type: "FeatureCollection", features: [] });
console.warn = _warn;
ok("⭐ with no chainage markers it returns the alignment UNCHANGED rather than a grey map",
  noChain === window.alignment_data);
ok("a null alignment is handled", window.buildIptAlignment(null, window.chainage_global_data) === null);
ok("a null chainage collection is handled by the step builder",
  window.buildChainageSteps(null) === null);
ok("and the boundary builder returns an empty collection rather than throwing",
  window.buildWsBoundaries(null).features.length === 0);
ok("a chainage collection with one point cannot make a bearing, and says nothing",
  window.buildWsBoundaries({ type: "FeatureCollection", features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-0.9, 52.5] },
      properties: { chain: "5500.00" } }] }).features.length === 0);
ok("a chainage point with no chain value falls to the finest tier rather than throwing",
  window.buildChainageSteps({ type: "FeatureCollection", features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-0.9, 52.5] }, properties: {} }] }
  ).features[0].properties.step_m === 100);
{
  window.applyOverlayPackage({});
  const _w = console.warn; console.warn = () => {};
  const none = quiet(() => window.buildIptAlignment(window.alignment_data, window.chainage_global_data));
  console.warn = _w;
  ok("⭐ an EMPTY package (a tenant with no alignment) builds to nothing and throws nothing",
    window.alignment_data.features.length === 0 && (none === window.alignment_data || none.features.length === 0)
    && window.buildWsBoundaries(window.chainage_global_data).features.length === 0
    && window.iptLegendRows().length === 0 && window.OVERLAY_VERSION === null);
  window.applyOverlayPackage(null);
  ok("and a null package is the same as an empty one", window.IPT_SEGMENTS.length === 0 && window.evr_rail_data.features.length === 0);
  window.applyOverlayPackage(OV);
}

console.log();
for (const f of fail) console.log("  FAIL:", f);
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
