/* map_lines_static.js — 24 Nov 2026, the public map's route lines rethink, task A1 (claude/map-lines-static).
 * John's "Yes, as recommended" to notes\public-map-lines-mockup-1124 Q1 to Q13 (24 Nov 2026, about 20:27 UTC); the brief
 * is notes\public-map-lines-build-1124\README.md ("The paint"). This file holds the build's own checks, stage by stage;
 * the older pins it bends are narrowed where they stand (parse_map.js, ui_fix_map_dark_edge.js) with a dated note.
 * Source checks and sandboxes of the map's own functions against a stub map; no browser (the real pictures are on the
 * mockup page under each card, "Real · built, local copy"). Every check but the "kept" ones fails on main 87c52b7.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const cfg = fs.readFileSync(path.join(ROOT, "map", "config.js"), "utf8").replace(/\r\n?/g, "\n");

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
function between(a, b) { const i = html.indexOf(a); const j = html.indexOf(b, i + 1); return (i < 0 || j < 0) ? "" : html.slice(i, j); }
function lum(hex) {
  const h = hex.replace("#", ""); const c = [0, 2, 4].map(k => parseInt(h.slice(k, k + 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

// ---------------------------------------------------------------------------------------------------------------
console.log("A. Card 1: the approved network in ink and grey, left of travel");
const netBlk = between("    const NET = {", "    // a month on screen = the forecast overlay is drawn");
ok("A1 the loaded leg is ink #3A3C41, the empty leg grey #8E9197, on a white casing",
   /loaded: '#3A3C41', empty: '#8E9197', casing: '#ffffff',/.test(netBlk), netBlk.slice(0, 200));
ok("A2 the legs are created in the look on screen (netLegPaint), never green #059669 or amber #f59e0b",
   /'id': 'outbound-lines',[\s\S]{0,300}'line-color': netLegPaint\(false\)\.color,/.test(html)
   && /'id': 'inbound-lines',[\s\S]{0,300}'line-color': netLegPaint\(true\)\.color,/.test(html)
   && !/'id': '(in|out)bound-lines',[\s\S]{0,300}'line-color': '#(059669|f59e0b)'/i.test(html));
ok("A3 the haul-road dots follow the legs (netHaulColour), and the legacy applySolidColors no longer paints green / amber",
   /'id': 'haul-dots',[\s\S]{0,300}'line-color': netHaulColour\(\),/.test(html)
   && !/setPaintProperty\('(in|out)bound-lines', 'line-color', '#(059669|f59e0b)'\)/i.test(html)
   && /const applySolidColors = \(\) => \{[\s\S]{0,900}applyLegLook\(\);/.test(html));
ok("A4 the core and casing ramps are the card's (7: 1.1 / 2.9, 12: 2.6 / 4.8, 16: 4.6 / 7)",
   html.includes("const WIDTH_CORE   = ['interpolate', ['linear'], ['zoom'], 7, 1.1, 12, 2.6, 16, 4.6];")
   && html.includes("const WIDTH_CASING = ['interpolate', ['linear'], ['zoom'], 7, 2.9, 12, 4.8, 16, 7];"));
ok("A5 kept: both legs left of their own travel (OFFSET_OUT = OFFSET_IN, the 17 Oct ramp), handed to applyLegLook",
   html.includes("const OFFSET_IN  = ['interpolate', ['linear'], ['zoom'], 7, -1, 12, -4, 14, -3, 17, 0];")
   && html.includes("const OFFSET_OUT = OFFSET_IN;")
   && html.includes("NET.offset = OFFSET_IN; NET.core = WIDTH_CORE; NET.casing_w = WIDTH_CASING;"));
ok("A6 the Control Panel's two leg swatches are ink and grey; the alternatives' swatch the neutral grey",
   /id="layer-inbound"[^\n]*background:#3A3C41;/.test(html) && /id="layer-outbound"[^\n]*background:#8E9197;/.test(html)
   && /id="layer-alts"[^\n]*background:#A9ABB0;/.test(html));
ok("A7 two tones (Q3): the loaded and the empty leg part by tone (≥ 1.8:1) and each reads on white (≥ 3:1)",
   contrast("#3A3C41", "#8E9197") >= 1.8 && contrast("#3A3C41", "#FFFFFF") >= 3 && contrast("#8E9197", "#FFFFFF") >= 3,
   [contrast("#3A3C41", "#8E9197").toFixed(2), contrast("#8E9197", "#FFFFFF").toFixed(2)]);

// sandbox: NET, netLegPaint, applyLegLook against a stub map
const sb = { DARK: false, layers: {}, set: [] };
sb.map = {
  getLayer: id => !!sb.layers[id],
  setPaintProperty: (l, p, v) => { sb.set.push([l, p, v]); (sb.layers[l] = sb.layers[l] || {})[p] = v; }
};
sb.labelsDark = () => sb.DARK;
vm.createContext(sb);
let sbErr = "";
try {
  vm.runInContext(netBlk + between("    // a month on screen = the forecast overlay is drawn", "    const DIM_LAYERS = [")
    + "\nNET.offset = 'OFFSET_IN'; NET.core = 'WIDTH_CORE'; NET.casing_w = 'WIDTH_CASING';"
    + "\nthis.NET = NET; this.netLegPaint = netLegPaint; this.applyLegLook = applyLegLook; this.NET_IDLE = NET_IDLE;", sb);
} catch (e) { sbErr = e.message; }
ok("A8 sandbox: the network block runs against a stub map", !!sb.applyLegLook, sbErr);
const P = (l, k) => (sb.layers[l] || {})[k];
const layersOn = ids => { sb.layers = {}; ids.forEach(i => { sb.layers[i] = {}; }); };
const LEGS = ['inbound-lines', 'outbound-lines', 'inbound-lines-casing', 'outbound-lines-casing', 'haul-dots', 'haul-eraser', 'route-alt-lines'];
if (sb.applyLegLook) {
  layersOn(LEGS); sb.DARK = false; sb.applyLegLook();
  ok("A9 no month on screen, light ground: loaded ink, empty grey, white casings, the legs' own widths, left of travel",
     P('inbound-lines', 'line-color') === '#3A3C41' && P('outbound-lines', 'line-color') === '#8E9197'
     && P('inbound-lines-casing', 'line-color') === '#ffffff' && P('outbound-lines-casing', 'line-color') === '#ffffff'
     && P('inbound-lines', 'line-width') === 'WIDTH_CORE' && P('outbound-lines-casing', 'line-width') === 'WIDTH_CASING'
     && P('inbound-lines', 'line-offset') === 'OFFSET_IN' && P('outbound-lines', 'line-offset') === 'OFFSET_IN'
     && P('haul-dots', 'line-offset') === 'OFFSET_IN', sb.layers);
  ok("A10 the haul dots are ink for a loaded piece and grey for an empty one",
     JSON.stringify(P('haul-dots', 'line-color')) === JSON.stringify(['match', ['get', 'type'], 'Inbound Haul', '#3A3C41', '#8E9197']));
  layersOn(LEGS); sb.DARK = true; sb.applyLegLook();
  ok("A11 a dark ground (card 8): a pale pair on a dark casing, the loaded leg the paler (set in the build)",
     P('inbound-lines', 'line-color') === sb.NET.loadedDark && P('outbound-lines', 'line-color') === sb.NET.emptyDark
     && P('inbound-lines-casing', 'line-color') === '#1F2024'
     && lum(sb.NET.loadedDark) > lum(sb.NET.emptyDark) && contrast(sb.NET.emptyDark, '#292929') >= 3, sb.layers);
}

// ---------------------------------------------------------------------------------------------------------------
console.log("B. Card 2: a month on screen — the forecast line replaces the leg; a route not on the forecast is one quiet line");
const af = fnSrc("applyFilters");
ok("B1 every leg, casing and haul piece filter lets through only what is NOT on the month's forecast (NET_IDLE)",
   html.includes("const NET_IDLE = ['!=', ['get', 'is_forecast'], true];")
   && (af.match(/\['==', \['get', 'type'\], '(In|Out)bound Highway'\], NET_IDLE, \.\.\.filterArr\.slice\(1\)\]/g) || []).length === 4
   && af.includes("['all', haulBase, NET_IDLE, ...filterArr.slice(1)]"));
ok("B2 applyFilters, raiseMarks and a change of light all re-apply the legs' look",
   af.includes("applyLegLook();") && fnSrc("raiseMarks").includes("applyLegLook();") && fnSrc("setLightPreset").includes("applyLegLook()"));
ok("B3 a month on screen is the forecast overlay drawn (the timeline's month or Show forecast's window)",
   /function netMonthOn\(\)\{ try \{ return !!\(map && map\.getLayer && map\.getLayer\('forecast-layer'\)\); \}/.test(html));
if (sb.applyLegLook) {
  layersOn(LEGS.concat(['forecast-layer'])); sb.DARK = false; sb.applyLegLook();
  ok("B4 with a month on screen a route not on the forecast is ONE quiet line: both legs #A9ABB0, no offset, 7: 1 / 12: 2 / 16: 3.4 on 2.6 / 4 / 5.6",
     P('inbound-lines', 'line-color') === '#A9ABB0' && P('outbound-lines', 'line-color') === '#A9ABB0'
     && P('inbound-lines', 'line-offset') === 0 && P('outbound-lines-casing', 'line-offset') === 0
     && JSON.stringify(P('inbound-lines', 'line-width')) === JSON.stringify(['interpolate', ['linear'], ['zoom'], 7, 1, 12, 2, 16, 3.4])
     && JSON.stringify(P('outbound-lines-casing', 'line-width')) === JSON.stringify(['interpolate', ['linear'], ['zoom'], 7, 2.6, 12, 4, 16, 5.6])
     && P('haul-dots', 'line-color') === '#A9ABB0' && P('haul-dots', 'line-offset') === 0 && P('haul-eraser', 'line-offset') === 0, sb.layers);
  layersOn(LEGS); sb.applyLegLook();
  ok("B5 the month off again: the legs go back to ink and grey, left of travel", P('inbound-lines', 'line-color') === '#3A3C41' && P('inbound-lines', 'line-offset') === 'OFFSET_IN');
}
ok("B6 the quiet grey parts from a white casing and from the forecast's lightest blue",
   contrast("#A9ABB0", "#FFFFFF") >= 2 && contrast("#A9ABB0", "#72A7FF") > 1, contrast("#A9ABB0", "#FFFFFF").toFixed(2));

// ---------------------------------------------------------------------------------------------------------------
console.log("C. Card 2: the forecast lines — a white casing, the five blues kept, the width by band (Direction 2)");
ok("C1 kept: the five band blues are unchanged (one list with the bulletin's VOLUME_RAMP)",
   html.includes("const CARBON_RAMP = ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'];"));
ok("C2 the map config holds no stock blue: the forecast line Off and the brand are the sign blue, the casing white",
   /brand:\s+"#0B4EA2"/.test(cfg) && /forecast:\s+"#0B4EA2"/.test(cfg) && /forecastCasing:\s+"#FFFFFF"/.test(cfg)
   && !/#2563EB|#3B82F6/i.test(cfg.replace(/\/\/[^\n]*/g, '')));
ok("C3 heat map Off: one sign blue, 5 px on a 7.6 px casing",
   html.includes("const FORECAST_LINE_WIDTH = 5;") && html.includes("const FORECAST_CASING_WIDTH = 7.6;"));
ok("C4 the forecast line and its casing, and the shared sections, are drawn at full opacity",
   /id:'forecast-casing'[^\n]*'line-opacity':1\}\}/.test(html) && /id:'forecast-layer'[^\n]*'line-opacity':1\}\}/.test(html)
   && /id: 'road-load-casing'[\s\S]{0,300}'line-opacity': 1 \}/.test(html) && /id: 'road-load-line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html)
   && /id: 'forecast-casing', type: 'line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html) && /id: 'forecast-layer', type: 'line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html));
// the band widths, run
let band = null, bandErr = "";
try { band = new Function(between("    const LINE_BAND_WIDTHS = ", "    //: working days in a planning month") + "\nreturn { bandWidthExpr, LINE_BAND_WIDTHS, LINE_BAND_PAD };")(); } catch (e) { bandErr = e.message; }
ok("C5 the width bands are 3 / 4.5 / 6 / 8 / 10 px and the casing 2.4 px wider", !!band
   && band.LINE_BAND_WIDTHS.join() === "3,4.5,6,8,10" && band.LINE_BAND_PAD === 2.4, bandErr);
if (band) {
  ok("C6 bandWidthExpr is a STEP on the same property and stops as the colour (never an interpolation)",
     JSON.stringify(band.bandWidthExpr('f_avg', [10, 25, 50, 100], 0)) === JSON.stringify(['step', ['to-number', ['get', 'f_avg'], 0], 3, 10, 4.5, 25, 6, 50, 8, 100, 10]));
  ok("C7 ...and its casing", JSON.stringify(band.bandWidthExpr('rl_mv', [20, 50, 100, 200], 2.4)) === JSON.stringify(['step', ['to-number', ['get', 'rl_mv'], 0], 5.4, 20, 6.9, 50, 8.4, 100, 10.4, 200, 12.4]));
}
const acm = fnSrc("applyCarbonMode");
ok("C8 Volume widens the routes by f_avg and Carbon by f_co2, each on its own colour's stops; Off and the council view keep one width",
   acm.includes("const bandW = pad => vol ? bandWidthExpr('f_avg', ROUTE_VOLUME_STOPS, pad) : bandWidthExpr('f_co2', stops, pad);")
   && acm.includes("focus ? COUNCIL_ROUTE_WIDTH : heat ? bandW(0) : FORECAST_LINE_WIDTH")
   && acm.includes("const caseW = heat ? bandW(LINE_BAND_PAD) : FORECAST_CASING_WIDTH;"));
ok("C9 the shared sections are widened by rl_mv on their own stops (rlStops), at creation and on every repaint",
   /id: 'road-load-line'[\s\S]{0,200}'line-width': bandWidthExpr\('rl_mv', rlStops\(\), 0\)/.test(html)
   && acm.includes("map.setPaintProperty('road-load-line', 'line-width', bandWidthExpr('rl_mv', rlStops(), 0));")
   && acm.includes("map.setPaintProperty('road-load-casing', 'line-width', bandWidthExpr('rl_mv', rlStops(), LINE_BAND_PAD));"));
ok("C10 the amber diversion edge keeps the casing's place at the casing's width, so a wide band does not bury it",
   acm.includes("if (map.getLayer('diversion-edge')) map.setPaintProperty('diversion-edge', 'line-width', caseW);"));
ok("C11 the edge under every forecast line: white on a light ground, the 12 Nov pale edge on a dark one, heat map on or Off",
   fnSrc("heatEdgeColour").includes("return typeof labelsDark === 'function' && labelsDark() ? HEAT_EDGE_DARK : CONFIG.COLORS.forecastCasing;")
   && html.includes("const HEAT_EDGE_DARK = '#E7E5E4';"));
// the lightest, thinnest line against the Light basemap's ground and its own white casing (the brief: under 2:1 gets a
// hairline edge). The Light basemap's land taken as #F5F5F5 (a near-white grey; to be read off the style in the browser at the pictures stage)
const LIGHT_GROUND = "#F5F5F5";
ok("C12 measured: the lightest blue on its white casing and on the Light basemap's ground clears 2:1, so no hairline edge",
   contrast("#72A7FF", "#FFFFFF") >= 2 && contrast("#72A7FF", LIGHT_GROUND) >= 2,
   [contrast("#72A7FF", "#FFFFFF").toFixed(2), contrast("#72A7FF", LIGHT_GROUND).toFixed(2)]);
ok("C13 the sign blue (heat map Off) parts from its white casing at ≥ 4.5:1", contrast("#0B4EA2", "#FFFFFF") >= 4.5);

// ---------------------------------------------------------------------------------------------------------------
// REVERSED 24 Nov 2026 (claude/map-lines-flow, card 3): Group B replaced the lanes with dots; the lanes' pins here are
// reversed to "gone", the dots' own checks are in map_lines_flow.js
console.log("D. The flow's lanes: replaced by the dots (Group B, map_lines_flow.js)");
ok("D1 REVERSED 24 Nov 2026 (card 3): the lanes, their widths, their offset, their still opacity and their three lights are gone",
   !html.includes("const FLOW_WIDTHS") && !html.includes("const FLOW_OFFSET")
   && !html.includes("const FLOW_STILL_OPACITY") && !html.includes("const FLOW_PULSES") && html.includes("const FLOW_MARK_GAP = 90;"));   // NARROWED 24 Nov 2026 (Q14, card 3b): arrowheads, not dots
ok("D2 REVERSED 24 Nov 2026 (card 3): no lane width to fit to a line, so the heat map sets none (flowWidthExpr and hideFirst gone)",
   !/function flowWidthExpr/.test(html) && !/hideFirst/.test(html)
   && !acm.includes("'forecast-flow'") && !acm.includes("flowWidthExpr"));

// ---------------------------------------------------------------------------------------------------------------
console.log("E. Card 9: the alternatives, a thinner neutral grey");
ok("E1 #A9ABB0 at 0.9, 7: 0.6 / 12: 1.2 / 16: 2 px, no casing; a dark ground gets its own grey",
   /alt: '#A9ABB0', altDark: '#[0-9A-F]{6}', altOpacity: 0\.9,/.test(netBlk)
   && netBlk.includes("altWidth: ['interpolate', ['linear'], ['zoom'], 7, 0.6, 12, 1.2, 16, 2]")
   && !html.includes("'route-alt-lines-casing'"));
if (sb.applyLegLook) {
  layersOn(LEGS); sb.DARK = false; sb.applyLegLook();
  const lightAlt = P('route-alt-lines', 'line-color');
  layersOn(LEGS); sb.DARK = true; sb.applyLegLook();
  ok("E2 applyLegLook repaints the alternatives for the ground", lightAlt === '#A9ABB0' && P('route-alt-lines', 'line-color') === sb.NET.altDark
     && P('route-alt-lines', 'line-opacity') === 0.9);
}

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
