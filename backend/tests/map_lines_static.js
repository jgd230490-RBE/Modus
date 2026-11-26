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
console.log("C. Card 2: the forecast lines — a white casing, the five blues kept, ONE width (25 Nov: Direction 1 again)");
ok("C1 kept: the five band blues are unchanged (one list with the bulletin's VOLUME_RAMP)",
   html.includes("const CARBON_RAMP = ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'];"));
ok("C2 the map config holds no stock blue: the forecast line Off and the brand are the sign blue, the casing white",
   /brand:\s+"#0B4EA2"/.test(cfg) && /forecast:\s+"#0B4EA2"/.test(cfg) && /forecastCasing:\s+"#FFFFFF"/.test(cfg)
   && !/#2563EB|#3B82F6/i.test(cfg.replace(/\/\/[^\n]*/g, '')));
// 25 Nov 2026 (John: "all lines should be the same thickess"): 24 Nov's width by band (Q4, Direction 2) is taken out again;
// every forecast line and shared section is ONE width in every mode, the amount told by the five blues only (12 Oct's rule)
ok("C3 one width in every mode: 4 px on a 6.6 px casing (John, 25 Nov: 'TRY 4 PX'; was 5 on 7.6)",
   html.includes("const FORECAST_LINE_WIDTH = 4;") && html.includes("const FORECAST_CASING_WIDTH = 6.6;"));
ok("C4 the forecast line and its casing, and the shared sections, are drawn at full opacity",
   /id:'forecast-casing'[^\n]*'line-opacity':1\}\}/.test(html) && /id:'forecast-layer'[^\n]*'line-opacity':1\}\}/.test(html)
   && /id: 'road-load-casing'[\s\S]{0,300}'line-opacity': 1 \}/.test(html) && /id: 'road-load-line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html)
   && /id: 'forecast-casing', type: 'line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html) && /id: 'forecast-layer', type: 'line'[\s\S]{0,300}'line-opacity': 1 \}/.test(html));
// REVERSED 25 Nov 2026 (one width): the band widths and their helper are GONE
ok("C5 gone: LINE_BAND_WIDTHS, LINE_BAND_PAD and bandWidthExpr (no width by band anywhere on the page)",
   !html.includes("LINE_BAND_WIDTHS") && !html.includes("LINE_BAND_PAD") && !html.includes("bandWidthExpr")
   && !/'line-width',?:?\s?\['step', \['to-number', \['get', '(f_avg|f_co2|rl_mv)'\]/.test(html));
const acm = fnSrc("applyCarbonMode");
ok("C8 Volume, Carbon and Off: the routes keep one width (the council view its thin 2 px); the colour carries the band",
   !acm.includes("bandW") && acm.includes("focus ? COUNCIL_ROUTE_WIDTH : FORECAST_LINE_WIDTH")
   && acm.includes("const caseW = FORECAST_CASING_WIDTH;"));
ok("C9 the shared sections: the same one width, at creation and on every repaint",
   /id: 'road-load-line'[\s\S]{0,200}'line-width': FORECAST_LINE_WIDTH,/.test(html)
   && /id: 'road-load-casing'[\s\S]{0,200}'line-width': FORECAST_CASING_WIDTH,/.test(html)
   && acm.includes("map.setPaintProperty('road-load-line', 'line-width', FORECAST_LINE_WIDTH);")
   && acm.includes("map.setPaintProperty('road-load-casing', 'line-width', FORECAST_CASING_WIDTH);"));
ok("C6 the band is still told by colour: Volume paints the routes by f_avg on the route stops",
   acm.includes("vol ? volumeColor('f_avg', ROUTE_VOLUME_STOPS)"));
ok("C7 ...and Carbon by f_co2 on the carbon stops", acm.includes("co2 ? carbonColor('f_co2', stops)"));
ok("C10 the amber diversion edge keeps the casing's place at the casing's width",
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
// (25 Nov 2026: static's one width took the lanes' first band back; moot here, the lanes are gone)
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

// ---------------------------------------------------------------------------------------------------------------
console.log("F. Card 4 (Q6): no words along the lines");
// comment-stripped source, so the dated note that says what went cannot make a gone-check fail or pass
const code = html.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
ok("F1 the forecast line's label layer is gone: no 'forecast-labels' layer, rule, list entry or visibility switch",
   !code.includes("forecast-labels") && !/setForecastLabelsVisible/.test(code));
ok("F2 its text field and unit are gone (forecastLabelField, FORECAST_LABEL_UNIT) and the map config has no label halo",
   !/forecastLabelField|FORECAST_LABEL_UNIT/.test(code) && !/forecastLabelHalo/.test(cfg));
const rules = between("    const LABEL_RULES = {", "    const LABEL_SORT");
ok("F3 the stretches' and the routes' badges are drawn under Labels \"All\" only (Few: null)",
   rules.includes("'road-load-labels':   { few: null, all: 0 },") && rules.includes("'carbon-route-labels':{ few: null, all: 0 },"));
ok("F4 the cap badge (a route over its planning flag) is kept as it was: a flag, not a figure along the line",
   rules.includes("'forecast-cap-badge': { few: 0, all: 0 },") && code.includes("id:'forecast-cap-badge'"));
ok("F5 the key's badge rows follow the switch (badgesOn: Labels \"All\"), and a Labels change re-draws the key",
   code.includes("function badgesOn(){ return typeof LABELS !== 'undefined' && LABELS.mode === 'all'; }")
   && (code.match(/badgesOn\(\) \? '<div class="ml-row ml-key">/g) || []).length === 2
   && /LABELS\.mode = mode;\s*applyLabels\(true\); syncLabelsSwitch\(\);\s*try \{ if \(typeof renderModeLegends === 'function'/.test(code));

// ---------------------------------------------------------------------------------------------------------------
console.log("G. Card 6: the picked route in ink on a sign-blue halo, and easy to hit");
ok("G1 the pick's paint: ink #1F2024 on white, the halo #0B4EA2 at 0.3; no green / amber left on the pick",
   code.includes("const SEL = { core: '#1F2024', coreDark: '#F5F5F4', casing: '#ffffff', casingDark: '#1F2024', glow: '#0B4EA2', glowOpacity: 0.3 };")
   && /id:'sel-core'[^\n]*'line-color':selPaint\(\)\.core,/.test(code) && /id:'sel-glow'[^\n]*'line-color':SEL\.glow,[^\n]*'line-opacity':SEL\.glowOpacity,/.test(code)
   && !/'#059669','Outbound Highway','#f59e0b'/.test(code));
ok("G2 kept: the other routes dim as before (0.42, setRouteDim on a pick, cleared on none)",
   code.includes("const DIM_OPACITY = 0.42;") && /setRouteDim\(routeId\);/.test(code) && /setRouteDim\(null\);/.test(code));
let selOk = false, selDark = null, selLight = null;
try {
  const S = vm.runInContext("({ SEL, applySelLook })", sb);
  ['sel-core', 'sel-casing', 'sel-glow'].forEach(l => { sb.layers[l] = {}; });
  sb.DARK = false; S.applySelLook(); selLight = [P('sel-core', 'line-color'), P('sel-casing', 'line-color'), P('sel-glow', 'line-color'), P('sel-glow', 'line-opacity')];
  sb.DARK = true; sb.applyLegLook(); selDark = [P('sel-core', 'line-color'), P('sel-casing', 'line-color')];
  sb.DARK = false; selOk = true;
} catch (e) { selOk = e.message; }
ok("G3 sandbox: light ground — ink core, white casing, sign-blue halo at 0.3", selOk === true
   && JSON.stringify(selLight) === JSON.stringify(['#1F2024', '#ffffff', '#0B4EA2', 0.3]), [selOk, selLight]);
ok("G4 sandbox: a dark ground (through applyLegLook, as the basemap / light switch calls it) — a pale core on a dark casing",
   selOk === true && JSON.stringify(selDark) === JSON.stringify(['#F5F5F4', '#1F2024']) && contrast('#F5F5F4', '#1F2024') >= 7, selDark);
// the click box: the point first, then ROUTE_HIT_PAD px either side; never a wider line
const hitSrc = between("    const ROUTE_HIT_PAD = ", "    (function initAnalysis(){");
const hb = { calls: [], answer: [] };
hb.map = { getLayer: id => id !== 'nope', queryRenderedFeatures: (q, o) => { hb.calls.push([q, o.layers]); return hb.answer.shift() || []; } };
vm.createContext(hb);
let hErr = "";
try { vm.runInContext(hitSrc + "\nthis.routeHitsAt = routeHitsAt; this.PAD = ROUTE_HIT_PAD;", hb); } catch (e) { hErr = e.message; }
ok("G5 sandbox: routeHitsAt runs", typeof hb.routeHitsAt === "function", hErr);
if (typeof hb.routeHitsAt === "function") {
  hb.answer = [[{ id: 'on' }]]; hb.calls = [];
  const a = hb.routeHitsAt({ x: 100, y: 50 }, ['forecast-layer', 'nope']);
  ok("G6 a hit on the line answers from the point alone (one query, the layers that exist)",
     a.length === 1 && a[0].id === 'on' && hb.calls.length === 1 && JSON.stringify(hb.calls[0][1]) === '["forecast-layer"]');
  hb.answer = [[], [{ id: 'near' }]]; hb.calls = [];
  const b = hb.routeHitsAt({ x: 100, y: 50 }, ['forecast-layer']);
  ok("G7 a miss asks a box 5 px either side of the point", b.length === 1 && b[0].id === 'near' && hb.PAD === 5
     && JSON.stringify(hb.calls[1][0]) === JSON.stringify([[95, 45], [105, 55]]));
  hb.calls = [];
  ok("G8 no layer or no point: nothing, and no query", hb.routeHitsAt({ x: 1, y: 1 }, ['nope']).length === 0 && hb.routeHitsAt(null, ['forecast-layer']).length === 0 && hb.calls.length === 0);
}
const ia = between("    (function initAnalysis(){", "    })();");
ok("G9 a click on a line keeps its own layer's handler; a near miss goes through the same routeClick, unless something with a click of its own is under it; else the pick clears",
   /map\.on\('click', lid, \(e\)=>\{\s*if\(!e\.features\|\|!e\.features\.length\) return;\s*routeClick\(e, e\.features\[0\]\);/.test(ia)
   && /if\(hits\.length\) return;[\s\S]{0,300}const near=routeHitsAt\(e\.point, routeLayers\);\s*if\(near\.length && !\(typeof clickableAt === 'function' && clickableAt\(e\.point\)\)\)\{ routeClick\(e, near\[0\]\); return; \}\s*clearSelection\(\);/.test(ia));
// NARROWED 25 Nov 2026: the widths it kept are now the one width
ok("G10 the hover asks the same box (the hand and the tip within 5 px of a line), and the line widths are not widened for it",
   /map\.on\('mousemove', \(e\) => \{\s*(\/\/[^\n]*\n\s*)?let features = routeHitsAt\(e\.point, interactiveLayers\);/.test(html)
   && html.includes("const FORECAST_LINE_WIDTH = 4;"));

// ---------------------------------------------------------------------------------------------------------------
console.log("H. Q5: a month on screen opens on Volume; a link's own layers and a picked Off still win");
ok("H1 the page ships Volume checked, Off and Carbon unchecked (one checked radio in the group)",
   /<input type="radio" name="heat-mode" id="toggle-road-load" onchange="toggleRoadLoad\(\)" checked>/.test(html)
   && /<input type="radio" name="heat-mode" id="heat-off" onchange="toggleHeatOff\(\)">/.test(html)
   && !/id="toggle-carbon"[^>]*checked/.test(html) && (html.match(/name="heat-mode"[^>]*checked/g) || []).length === 1);
ok("H2 the link's defaults are read from the page as shipped (so Volume is the default and a link with Off writes -road-load)",
   html.includes("VIEW.defaults = layersOn();") && /function layerBoxes\(\)[\s\S]{0,600}toggle-road-load/.test(html));
ok("H3 Off picked stays Off: refreshMapModes only mirrors the radios, it never ticks Volume back",
   /const off = document\.getElementById\('heat-off'\);\s*if \(off && off\.checked !== !mode\) off\.checked = !mode;/.test(html)
   && !/getElementById\('toggle-road-load'\)\.checked\s*=\s*true/.test(html));
ok("H4 the council view still turns the heat map Off (kept)",
   html.includes("if (on) { const off = document.getElementById('heat-off'); if (off && !off.checked) { off.checked = true;"));
ok("H5 the Labels box says the figures on the roads come with All",
   html.includes("Off hides the names on the map. Few shows the sites. All shows every name and the figures on the roads."));
ok("H6 the heat map's radios are built after the link reads its defaults, so Volume is named a default by hand (a link with Off keeps Off)",
   /VIEW\.defaults = layersOn\(\);[^\n]*\n(\s*\/\/[^\n]*\n)*\s*const LATE_DEFAULTS = \['road-load'\];\s*LATE_DEFAULTS\.forEach\(k => \{ if \(!VIEW\.defaults\.includes\(k\)\) VIEW\.defaults\.push\(k\); \}\);\s*VIEW\.defaults\.sort\(\);/.test(html)
   && html.indexOf("const LATE_DEFAULTS") < html.indexOf("function encodeView"));
// ---------------------------------------------------------------------------------------------------------------
console.log("I. The key and the guides");
const legend = fnSrc("renderModeLegends");
// REVERSED 25 Nov 2026 (one width): the key shows colours only, a square swatch a band (no width step, no line sample)
ok("I1 Volume and Carbon: each band's row is its colour only (bandSample draws the square swatch)",
   (legend.match(/bandSample\(i\)/g) || []).length === 2
   && html.includes("return '<span class=\"ml-sw\" style=\"background:' + CARBON_RAMP[i] + '\"></span>';"));
let samples = null;
try {
  const kb = {}; vm.createContext(kb);
  vm.runInContext("const CARBON_RAMP = ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'];\n" + fnSrc("bandSample") + "\nthis.out = [0,1,2,3,4].map(bandSample);", kb);
  samples = kb.out;
} catch (e) { samples = e.message; }
ok("I2 sandbox: the five samples are the five blues, the same size each, no height by band", Array.isArray(samples) && samples.length === 5
   && samples[0] === '<span class="ml-sw" style="background:#72A7FF"></span>' && samples[4] === '<span class="ml-sw" style="background:#00215B"></span>'
   && samples.every(x => !/height/.test(x)), samples);
ok("I3 the line samples' CSS is gone (.ml-ln), the square swatch keeps its light outline on a dark look",
   !html.includes(".ml-ln") && html.includes(".mode-legend .ml-sw{ display:inline-block; width:14px; height:14px;")
   && html.includes('html[data-look="dark"] .mode-legend .ml-steps i, html[data-look="dark"] .mode-legend .ml-sw{ box-shadow:0 0 0 1px rgba(231,229,228,.7); }'));
ok("I4 the leg rows in Haul routes name the new paint (ink #3A3C41, grey #8E9197; alternatives #A9ABB0)",
   html.includes('id="layer-inbound" checked onchange="applyFilters()"> Laden (out)</label><span class="color-dot" style="background:#3A3C41;">')
   && html.includes('id="layer-outbound" checked onchange="applyFilters()"> Empty (return)</label><span class="color-dot" style="background:#8E9197;">')
   && html.includes('Alternative routes <span class="lim-n" id="alts-note"></span></label><span class="color-dot" style="background:#A9ABB0;">'));
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const technical = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");
ok("I5 the user guide: dark and grey legs, no green and amber, the pick drawn dark over a soft blue edge, a click just beside a route counts",
   guide.includes("<tr><td>Dark and grey lines</td>") && !guide.includes("<tr><td>Green and amber lines</td>")
   && guide.includes("Click a route, or just beside it, for its name and distance: it is drawn dark over a soft blue edge and the other routes fade."));
// NARROWED 25 Nov 2026 (one width): darker is more, the width says nothing
ok("I6 the user guide: darker is more (no word on width); one blue with Off; the badges under Labels All; a month opens on Volume",
   guide.includes("the darker the blue, the more lorry movements a day on that stretch") && !guide.includes("darker and wider")
   && !technical.includes("LINE_BAND_WIDTHS") && technical.includes("one width in every mode") && guide.includes("With Heat map Off they are all one blue.")
   && guide.includes("With Labels on All, a small white badge") && guide.includes("(a month opens on Volume; a shared link keeps its own choice)")
   && guide.includes("the work-section marks, the heat map's badges and each gate's own access road") && !guide.includes("<tr><td>Blue lines with a figure</td>")
   && !guide.includes("turn blue and show their lorry movements a day"));

// ---------------------------------------------------------------------------------------------------------------
console.log("J. Card 4b: the badge is a small plate on its line, no blue (John: 'smaller and neater')");
ok("J1 the plate's paint: white, a #C6C8CC edge, the number in ink, a grey arrow; the carbon plate the same with no arrow; no blue or green left",
   html.includes("const BADGE_STYLE = { mv: { edge: '#C6C8CC', ink: '#1F2024', arrow: '#62656B' }, co2: { edge: '#C6C8CC', ink: '#1F2024' } };")
   && !/BADGE_STYLE[^\n]*#2563EB|BADGE_STYLE[^\n]*#059669/.test(html));
ok("J2 the number is 12 px bold, centred ON its line (no offset above it)",
   html.includes("const BADGE_TEXT_SIZE = 12,") && /'text-anchor': 'center', 'text-offset': \[0, 0\],/.test(fnSrc("badgeLayout")));
let plate = null, plErr = "";
try {
  const strokes = [];
  const g = { set strokeStyle(v) { strokes.push(v); }, get strokeStyle() { return strokes[strokes.length - 1]; }, fillStyle: '', lineWidth: 0, lineCap: '', lineJoin: '',
    beginPath() {}, moveTo() {}, lineTo() {}, arcTo() {}, closePath() {}, fill() {}, stroke() {}, getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }) };
  const pb = { document: { createElement: () => ({ getContext: () => g }) } };
  vm.createContext(pb);
  vm.runInContext("const BADGE_STYLE = { mv: { arrow: '#62656B' } };\n" + fnSrc("plateBadgeImage") + "\nthis.a = plateBadgeImage('#C6C8CC', true); this.b = plateBadgeImage('#C6C8CC', false);", pb);
  plate = { a: pb.a, b: pb.b, strokes };
} catch (e) { plErr = e.message; }
ok("J3 sandbox: the plate is 16 px high at pixelRatio 2, the arrow plate wider by the 8 px arrow; the edge #C6C8CC then the arrow #62656B",
   !!plate && plate.a.img.height === 32 && plate.b.img.height === 32 && plate.a.opts.pixelRatio === 2
   && plate.a.img.width - plate.b.img.width === 18 && plate.strokes.join() === "#C6C8CC,#62656B,#C6C8CC", plErr || JSON.stringify(plate && { aw: plate.a.img.width, bw: plate.b.img.width, s: plate.strokes }));
ok("J4 the key's samples are the same plate (16 px, 3 px corner, 1 px #C6C8CC edge, 12 px bold ink, a grey 8 px arrow)",
   html.includes(".mv-pill, .co-pill{ flex:none; display:inline-flex; align-items:center; gap:3px; height:16px; padding:0 4px; border-radius:3px; background:#ffffff;")
   && html.includes("font:700 12px/16px var(--f-text); white-space:nowrap; color:#1F2024; box-shadow:inset 0 0 0 1px #C6C8CC; }")
   && html.includes('<span class="mv-pill"><svg width="8" height="8" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 4h9M7 1l3 3-3 3M11 8H2M5 5L2 8l3 3" fill="none" stroke="#62656B"')
   && !/\.mv-pill\{[^}]*#2563EB|\.co-pill\{[^}]*#059669/.test(html));
ok("J5 still under Labels All only (the key's rows and LABEL_RULES few: null)",
   /'road-load-labels':\s*\{ few: null, all: 0 \}/.test(html) && /'carbon-route-labels':\s*\{ few: null, all: 0 \}/.test(html) && (fnSrc("renderModeLegends").match(/badgesOn\(\) \?/g) || []).length === 2);

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
