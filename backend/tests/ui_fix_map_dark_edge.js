/* ui_fix_map_dark_edge.js — 12 Nov 2026, card A-F2b on dark grounds, option (b), on claude/bulletin-print-fixes
 * (notes\clocs-meeting-1113\left-to-do-mockup-1111\cards-live-a-public.html; BUILD.md rule 13).
 * The new band blues sank into a dark basemap: the darkest two bands read 1.34:1 and 1.07:1 on Dark's #292929, the
 * near-black line edge (#1F2024) vanished, and the key's near-black swatch outline vanished on the app's Dark look.
 * Fix: on a dark ground (labelsDark(): Dark, Navigation night, the aerial styles, Standard at dusk or night) the edge
 * under a heat map's lines turns pale; on the Dark look the key's swatches get a pale outline. One list of blues kept.
 * Source checks and sandboxes of the map's own functions; no browser (the real pictures are on the card).
 * Its own file: nothing appended to parse_map.js. Every check but the "kept" ones fails on the code before it.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
function fnSrc(name) {
  const i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    function ", i + 10);
  return html.slice(i, j > 0 ? j : i + 6000);
}
function lum(hex) {
  const h = hex.replace("#", ""); const c = [0, 2, 4].map(k => parseInt(h.slice(k, k + 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

const rampM = html.match(/const CARBON_RAMP = \[([^\]]+)\];/);
const RAMP = rampM ? rampM[1].match(/#[0-9A-Fa-f]{6}/g) : [];
const edgeM = html.match(/const HEAT_EDGE_DARK = '(#[0-9A-Fa-f]{6})';/);
const EDGE = edgeM ? edgeM[1] : null;
const DARK_GROUND = "#292929";   // Mapbox Dark v11's land, the darkest of the dark grounds measured on the card

console.log("A. One list of blues kept (no separate Dark list: option (c) stays open to John)");
ok("A1 kept: CARBON_RAMP is still the one list of A-F2b's five blues",
   RAMP.join(",") === "#72A7FF,#006AFD,#0051C4,#00388E,#00215B", RAMP);
ok("A2 kept: no second ramp for dark grounds", (html.match(/const [A-Z_]*RAMP[A-Z_]* = \[/g) || []).filter(x => !/AREA_RAMP/.test(x)).length === 1);

console.log("B. A pale edge on a dark ground");
ok("B1 HEAT_EDGE_DARK is a pale colour that parts from the dark ground and from the darkest band (≥ 3:1 each)",
   EDGE && contrast(EDGE, DARK_GROUND) >= 3 && contrast(EDGE, RAMP[4]) >= 3 && contrast(EDGE, RAMP[3]) >= 3,
   EDGE && [contrast(EDGE, DARK_GROUND).toFixed(2), contrast(EDGE, RAMP[4]).toFixed(2)]);
// sandbox: heatEdgeColour / restyleHeatEdge with a stub map (heatEdgeColour's slice carries the `let HEAT_LINES_ON` after it)
const sb = { CONFIG: { COLORS: { forecastCasing: "#1F2024" } }, DARK: false, set: [],
             map: { getLayer: () => true, setPaintProperty: (l, p, v) => sb.set.push([l, p, v]) } };
sb.labelsDark = () => sb.DARK;
vm.createContext(sb);
try {
  vm.runInContext("const HEAT_EDGE_DARK = '" + EDGE + "';\n" + fnSrc("heatEdgeColour") + "\n" + fnSrc("restyleHeatEdge")
                  + "\nthis.heatEdgeColour = heatEdgeColour; this.restyleHeatEdge = restyleHeatEdge; this.setOn = v => { HEAT_LINES_ON = v; };", sb);
} catch (e) { console.log("  sandbox: " + e.message); }
const hec = sb.heatEdgeColour || (() => null);
sb.DARK = true;
ok("B2 a heat map on a dark ground: the edge is pale", !!EDGE && hec(true) === EDGE);
ok("B3 no heat map on a dark ground: the edge stays near-black (the plain routes keep their look)", hec(false) === "#1F2024");
sb.DARK = false;
ok("B4 a heat map on a light ground: the edge stays near-black (paper and the light map unchanged)", hec(true) === "#1F2024");
sb.DARK = true; sb.set = [];
if (sb.setOn) { sb.setOn(true); sb.restyleHeatEdge(); }
ok("B5 restyleHeatEdge paints both casings (the route lines' and the shared roads') pale while a heat map is on",
   sb.set.some(s => s[0] === "forecast-casing" && s[1] === "line-color" && s[2] === EDGE)
   && sb.set.some(s => s[0] === "road-load-casing" && s[1] === "line-color" && s[2] === EDGE), sb.set);
sb.set = [];
if (sb.setOn) { sb.setOn(false); sb.restyleHeatEdge(); }
ok("B6 the heat map off: the route lines' edge goes back to near-black",
   sb.set.some(s => s[0] === "forecast-casing" && s[2] === "#1F2024"), sb.set);

console.log("C. Re-applied wherever the ground or the heat map changes");
ok("C1 applyCarbonMode records whether a heat map colours the lines (not the council view) and restyles the edge",
   fnSrc("applyCarbonMode").includes("HEAT_LINES_ON = heat && !focus; restyleHeatEdge();"));
ok("C2 a Standard light preset change (dusk / night) restyles the edge", fnSrc("setLightPreset").includes("restyleHeatEdge()"));
ok("C3 a layer (re)made after a basemap change restyles the edge (raiseMarks)", fnSrc("raiseMarks").includes("restyleHeatEdge()"));
ok("C4 kept: labelsDark() still names Dark, Navigation night, the aerial styles and Standard at dusk or night",
   fnSrc("labelsDark").includes("/dark|night|satellite|maaamet/.test(bm)") && fnSrc("labelsDark").includes("LIGHT.preset === 'night'"));

console.log("D. The key on the app's Dark look");
const darkKey = html.match(/html\[data-look="dark"\] \.mode-legend \.ml-steps i, html\[data-look="dark"\] \.mode-legend \.ml-sw\{ box-shadow:0 0 0 1px rgba\((\d+),(\d+),(\d+),\.(\d+)\); \}/);
ok("D1 the Dark look gives the key's swatches and steps a pale outline", !!darkKey);
const hex2 = n => ("0" + Number(n).toString(16)).slice(-2);
const outline = darkKey ? "#" + hex2(darkKey[1]) + hex2(darkKey[2]) + hex2(darkKey[3]) : null;
const darkSurface = (html.match(/html\[data-look="dark"\]\{[^}]*--surface:\s*(#[0-9A-Fa-f]{6})/) || [])[1];
ok("D2 the outline (at full strength) parts from the Dark panel by ≥ 3:1 and from the darkest swatch",
   outline && darkSurface && contrast(outline, darkSurface) >= 3 && contrast(outline, RAMP[4]) >= 3, [outline, darkSurface]);
ok("D3 kept: the light look keeps its near-black outline",
   html.includes(".mode-legend .ml-sw{ display:inline-block; width:14px; height:14px; flex:0 0 14px; border-radius:2px; box-shadow:0 0 0 1px rgba(31,32,36,.35); }"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
