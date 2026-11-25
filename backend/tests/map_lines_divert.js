/* map_lines_divert.js — 24 Nov 2026, the public map's route lines rethink, task B2 (claude/map-lines-diversions).
 * John's "Yes, as recommended" to notes\public-map-lines-mockup-1124 Q1 to Q13 (24 Nov 2026, about 20:27 UTC), card 5:
 * Q8 the usual road and the amber edge, Q9 busy hours with no click; the brief is notes\public-map-lines-build-1124\README.md.
 * Source checks and sandboxes of the map's own functions against a stub map; no browser (the real pictures are on the
 * mockup page under card 5, "Real · built, local copy"). The older pins this bends are narrowed where they stand
 * (parse_map.js, map_lines_static.js C10) with a dated note.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const cfg = fs.readFileSync(path.join(ROOT, "map", "config.js"), "utf8").replace(/\r\n?/g, "\n");
const help = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const tech = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");

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

// the diversion block, run against a stub map that records every source push and every layer added / moved
const a = html.indexOf("const DIV_EDGE = {"), b = html.indexOf("function renderMonthFrame(m){");
const block = html.slice(a, b);
function stubMap(order) {
  const m = { sent: {}, added: [], moved: [], vis: {}, sources: {}, layers: new Set(order || ['forecast-casing', 'forecast-layer']),
    order: (order || ['forecast-casing', 'forecast-layer']).slice() };
  m.getSource = (id) => m.sources[id] || (m.sources[id] = { _data: null, setData: (d) => { m.sent[id] = (m.sent[id] || 0) + 1; m.sources[id]._data = d; } });
  m.getLayer = (id) => m.layers.has(id) ? { id } : undefined;
  m.addSource = (id, o) => { m.sources[id] = { _data: o.data, setData: (d) => { m.sent[id] = (m.sent[id] || 0) + 1; m.sources[id]._data = d; } }; };
  m.addLayer = (l, before) => { m.added.push({ l, before }); m.layers.add(l.id); const i = m.order.indexOf(before); if (i >= 0) m.order.splice(i, 0, l.id); else m.order.push(l.id); };
  m.moveLayer = (id, before) => { m.moved.push([id, before]); m.order.splice(m.order.indexOf(id), 1); const i = before ? m.order.indexOf(before) : -1; if (i >= 0) m.order.splice(i, 0, id); else m.order.push(id); };
  m.getStyle = () => ({ layers: m.order.map(id => ({ id })) });
  m.setLayoutProperty = (id, k, v) => { m.vis[id + ':' + k] = v; };
  m.setPaintProperty = () => {};
  return m;
}
const FILTER = (legs, rids) => ['all', ['==', ['get', 'is_forecast'], true], ['in', ['get', 'type'], ['literal', legs]], ['in', ['get', 'route_id'], ['literal', rids]]];
function load(env) {
  const names = Object.keys(env);
  return new Function(...names, block + "\nreturn { DIV_EDGE, DIV_USUAL, DIV_USUAL_LAYERS, divOffPieces, updateDiversionEdge, divEdgeGap, updateUsualRoad, ensureDiversionEdge, placeDiversionEdge, divOverlayPasses };")(...names.map(k => env[k]));
}
const BASE = (m, over) => Object.assign({
  map: m, DIV: { orig: new Map() }, forecastLayerFilter: () => FILTER(['Inbound Highway', 'Outbound Highway'], ['R1', 'R2']),
  FORECAST_CASING_WIDTH: 6.6, FORECAST_LINE_WIDTH: 4, COUNCIL_ROUTE_WIDTH: 2, CONFIG: { COLORS: { forecast: '#1F5FD6', brand: '#0B4EA2' } },
  renderFlowLegend: () => {}, heatMode: () => null, councilFocus: () => false, mapModeMonth: () => 16, styleReady: () => true,
  LINE_BAND_WIDTHS: [3, 4.5, 6, 8, 10], ROUTE_VOLUME_STOPS: [20, 50, 100, 200], carbonScale: () => ({ stops: [1, 2, 3, 4] }),
  rlStops: () => [20, 50, 100, 200], RL: { month: 16, cache: { 16: true } }, netDark: () => false, labelAnchor: () => undefined,
}, over || {});

// a usual road along lat 52.5 and a diversion that leaves it between lon -0.96 and -0.94 (a 0.01 deg hump, ~1.1 km)
const mainL = []; for (let i = 0; i <= 20; i++) mainL.push([-1.0 + i * 0.005, 52.5]);
const divL = mainL.map(c => [c[0], (c[0] > -0.961 && c[0] < -0.939) ? 52.51 : 52.5]);
const leg = (rid, type, coords, fc) => ({ type: 'Feature', properties: { type, route_id: rid, div_when: '1–31 Dec 2027', is_forecast: fc !== false }, geometry: { type: 'LineString', coordinates: coords } });

// ---------------------------------------------------------------------------------------------------------------
console.log("A. The usual road (card 5, Q8): the stretch a diversion leaves, under the lines, grey with crosses");
ok("A1 the code sits beside the amber edge, before renderMonthFrame", a > 0 && b > a);
ok("A2 grey #B4B6BA 2.6 px on a 5 px white casing, an × in #6B6E74 about every 70 px; a dark ground has its own pale pair",
   /core: '#B4B6BA', casing: '#FFFFFF', x: '#6B6E74', coreDark: '#[0-9A-F]{6}', casingDark: '#[0-9A-F]{6}', xDark: '#[0-9A-F]{6}',/.test(block)
   && /coreW: 2\.6, casingW: 5, xEvery: 70,/.test(block));
{
  const m = stubMap(); const E = load(BASE(m, { DIV: { orig: new Map([['R1|Inbound Highway', { coords: mainL }]]) } }));
  E.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL)] });
  const u = E.DIV_USUAL.fc.features;
  ok("⭐ A3 the usual road is the stretch of the usual line the diversion leaves: one piece, on lat 52.5, between where it leaves and rejoins",
     u.length === 1 && u[0].geometry.coordinates.every(c => c[1] === 52.5)
     && u[0].geometry.coordinates[0][0] < -0.955 && u[0].geometry.coordinates[u[0].geometry.coordinates.length - 1][0] > -0.945, u);
  ok("A4 sent once to its own source; the same month again sends nothing", m.sent['div-usual-source'] === 1
     && (E.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL)] }), m.sent['div-usual-source'] === 1));
  E.updateDiversionEdge({ features: [] });
  ok("A5 a month with no diversion clears it once, and an empty month after an empty one sends nothing",
     m.sent['div-usual-source'] === 2 && E.DIV_USUAL.fc.features.length === 0
     && (E.updateDiversionEdge({ features: [] }), m.sent['div-usual-source'] === 2));
}
{
  const orig = new Map([['R1|Inbound Highway', { coords: mainL }], ['R1|Outbound Highway', { coords: mainL }], ['R3|Inbound Highway', { coords: mainL }]]);
  const m = stubMap(); const E = load(BASE(m, { DIV: { orig } }));
  E.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL), leg('R1', 'Outbound Highway', divL), leg('R3', 'Inbound Highway', divL)] });
  ok("⭐ A6 two legs (and a route the overlay filter leaves out) over one usual road draw it ONCE: no doubled line, no doubled crosses",
     E.DIV_USUAL.pieces.length === 3 && E.DIV_USUAL.fc.features.length === 1, E.DIV_USUAL.fc.features.length);
  const m2 = stubMap(); const E2 = load(BASE(m2, { DIV: { orig }, forecastLayerFilter: () => FILTER(['Inbound Highway', 'Outbound Highway'], ['R2']) }));
  E2.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL)] });
  ok("A7 it obeys the overlay filter: a route filtered out draws no usual road", E2.DIV_USUAL.fc.features.length === 0);
  const m3 = stubMap(); const E3 = load(BASE(m3, { DIV: { orig } }));
  E3.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL, false)] });
  ok("A8 a leg not on the month's forecast draws no usual road", E3.DIV_USUAL.fc.features.length === 0);
}
{
  const m = stubMap(); const E = load(BASE(m));
  E.ensureDiversionEdge();
  const u = m.added.filter(x => E.DIV_USUAL_LAYERS.includes(x.l.id));
  ok("⭐ A9 its three layers (casing, line, crosses) go UNDER the forecast casing, so every line is drawn over it",
     u.length === 3 && u.every(x => x.before === 'forecast-casing') && u.map(x => x.l.id).join() === 'div-usual-casing,div-usual,div-usual-x', u.map(x => [x.l.id, x.before]));
  const x = (u.find(z => z.l.id === 'div-usual-x') || {}).l || {};
  ok("A10 the crosses: '×' along the line every 70 px, size 15, kept upright off, shown even where names collide",
     x.layout && x.layout['text-field'] === '×' && x.layout['symbol-placement'] === 'line' && x.layout['symbol-spacing'] === 70
     && x.layout['text-size'] === 15 && x.layout['text-allow-overlap'] === true && x.layout['text-ignore-placement'] === true, x.layout);
  const m2 = stubMap(); const E2 = load(BASE(m2, { styleReady: () => false }));
  E2.ensureDiversionEdge();
  ok("A11 nothing is added before the style is ready (styleReady(), never map.once('idle'))", m2.added.length === 0
     && fnSrc("ensureUsualRoad").includes("if (typeof styleReady === 'function' && !styleReady()) return;") && !/map\.once\('idle'/.test(block));
}
ok("A12 the crosses are marks, not names: not in LABEL_RULES (they stay under Labels Off), and the code says so",
   !/LABEL_RULES[\s\S]{0,3000}div-usual-x/.test(html.slice(html.indexOf("const LABEL_RULES"), html.indexOf("const LABEL_RULES") + 3000))
   && /marks, not names/.test(block));
ok("A13 a council view hides it; both removal lists drop it; no popup and no tip on it",
   html.includes("const COUNCIL_QUIET_LAYERS = ['forecast-casing', 'forecast-flow', 'forecast-flow-light', 'forecast-cap-badge', 'div-usual-casing', 'div-usual', 'div-usual-x'];")
   && (html.match(/'diversion-edge','div-usual-x','div-usual','div-usual-casing','forecast-layer'/g) || []).length === 2
   && !/map\.on\('(click|mouseenter|mousemove)',\s*'div-usual/.test(html));
ok("A14 the filter or a pick redraws it (applyForecastFilter), and a look change repaints it (raiseMarks)",
   fnSrc("applyForecastFilter").includes("updateUsualRoad()") && fnSrc("raiseMarks").includes("restyleUsualRoad()"));

// ---------------------------------------------------------------------------------------------------------------
console.log("B. The way round: two amber rails outside the one line");
// NARROWED 25 Nov 2026 (John, "Keep 4 px"): the rail is no longer a written 3: it is sized from the line and its casing,
// 1.7 px of amber beyond the casing whatever the one width is (4 on 6.6 now; 5 on 7.6 the day before)
{
  const railAt = (lw, cw) => load(BASE(stubMap(), { FORECAST_LINE_WIDTH: lw, FORECAST_CASING_WIDTH: cw })).DIV_EDGE.rail;
  const beyond = (lw, cw) => railAt(lw, cw) - (cw - lw) / 2;
  ok("B1 amber #F59E0B, round caps, the gap the line's own width; each rail 1.7 px of amber beyond the casing at 4 on 6.6 AND at 5 on 7.6 (at least 2 px of amber each side of the line)",
     /const DIV_EDGE = \{ colour: '#F59E0B', near_m: 25, beyond: 1\.7,\n\s*get rail\(\)\{ return \(FORECAST_CASING_WIDTH - FORECAST_LINE_WIDTH\) \/ 2 \+ this\.beyond; \},/.test(block)
     && Math.abs(beyond(4, 6.6) - 1.7) < 1e-9 && Math.abs(beyond(5, 7.6) - 1.7) < 1e-9 && railAt(4, 6.6) >= 2
     && /'line-cap': 'round'/.test(fnSrc("ensureDiversionEdge")) && fnSrc("ensureDiversionEdge").includes("'line-gap-width': divEdgeGap(),"),
     [railAt(4, 6.6), railAt(5, 7.6)]);
  ok("⭐ B1b no line width written as a number in the diversion code (no 5 / 7.6 / 11 / 10 px figure): widths come from the constants",
     !/(rail|line-gap-width|line-width)['"]?\s*:\s*(5|7\.6|11|10|4|6\.6)\b/.test(block));
  const lw = html.match(/const FORECAST_LINE_WIDTH = ([\d.]+);/), du = block.match(/coreW:\s*([\d.]+)/),
        bz = html.match(/id:'busy-core'[^\n]*'line-width':([\d.]+)/);
  ok("B1c the usual road and the busy-hours road stay thinner than the one forecast line",
     !!(lw && du && bz) && +du[1] < +lw[1] && +bz[1] < +lw[1], [lw && lw[1], du && du[1], bz && bz[1]]);
}
// 25 Nov 2026: John reversed Q4 ("all lines should be the same thickess"): every blue line is ONE width in every mode (4 px on 6.6 since his "Keep 4 px"),
// so the rails' gap is the one width; the band-width gaps built on 24 Nov (pieces cut where the width changed) are GONE
ok("⭐ B2 gone: no band width in the diversion code (no dv_gap, no cut by width, no LINE_BAND_WIDTHS / bandWidthExpr / rlStops)",
   !/dv_gap|divEdgeGaps|divGapLines|divBandW|DIV_GAP_NEAR_M|LINE_BAND_WIDTHS|bandWidthExpr|rlStops/.test(block));
{
  const gap = (over) => { const m = stubMap(); const E = load(BASE(m, over)); E.ensureDiversionEdge(); return (m.added.find(x => x.l.id === 'diversion-edge') || { l: { paint: {} } }).l.paint['line-gap-width']; };
  ok("⭐ B3 the gap is the one line width (4 px, so 10 px across) whatever the heat map; a council view its thin line (2 px)",
     gap({}) === 4 && gap({ heatMode: () => 'volume' }) === 4 && gap({ heatMode: () => 'carbon' }) === 4 && gap({ councilFocus: () => true }) === 2
     && gap({ FORECAST_LINE_WIDTH: 5, FORECAST_CASING_WIDTH: 7.6 }) === 5,
     [gap({}), gap({ heatMode: () => 'volume' }), gap({ councilFocus: () => true })]);
  const orig = new Map([['R1|Inbound Highway', { coords: mainL }]]);
  const m = stubMap(); const E = load(BASE(m, { DIV: { orig } }));
  E.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL)] });
  ok("B4 one piece a stretch off the usual road, sent once; the same month again sends nothing",
     E.DIV_EDGE.fc.features.length === 1 && m.sent['diversion-edge-source'] === 1
     && (E.updateDiversionEdge({ features: [leg('R1', 'Inbound Highway', divL)] }), m.sent['diversion-edge-source'] === 1));
}
{
  const m = stubMap(['forecast-casing', 'forecast-layer', 'diversion-edge', 'road-load-casing', 'road-load-line', 'forecast-flow', 'busy-core']);
  const E = load(BASE(m)); E.placeDiversionEdge();
  const o = m.order;
  ok("⭐ B7 the rails go just over the highest of the forecast line, the shared sections and the lanes (so a shared section never hides them), under a pick",
     o.indexOf('diversion-edge') === o.indexOf('forecast-flow') + 1 && o.indexOf('diversion-edge') < o.indexOf('busy-core'), o);
}
ok("B8 a mode change (a council view) sets the gap again (applyCarbonMode)",
   fnSrc("applyCarbonMode").includes("map.setPaintProperty('diversion-edge', 'line-gap-width', divEdgeGap());"));
ok("B9 amber is the way round's alone: the busy-hours road and its hours carry none",
   !/#F59E0B|#f59e0b|amber/i.test(fnSrc("busyInk") + fnSrc("busySample")) && html.includes("const BUSY_ROAD_COLOR = CONFIG.COLORS.brand;"));

// ---------------------------------------------------------------------------------------------------------------
console.log("C. Busy hours with no click (card 5, Q9)");
ok("C1 the sign blue (#0B4EA2), thin on a white casing; its hours in ink with a halo, a pale ink on a dark ground",
   /brand:\s*"#0B4EA2"/.test(cfg) && fnSrc("busyInk").includes("return { ink: dark ? '#F4F4F5' : '#1F2024', halo: dark ? '#1F2024' : '#ffffff' };")
   && html.includes("'line-color':BUSY_ROAD_COLOR,'line-width':2.6"));
{
  const bs = html.indexOf("    const BUSY_ROAD_COLOR"), be = html.indexOf("    function fillBusyRoads(");
  const busy = (TL, focus, filt, feats) => new Function("TL", "councilFocus", "divOverlayPasses", "a1_data", "CONFIG", "netDark",
    html.slice(bs, be) + "\nreturn busyOnMonth(busyLegProps());")(TL, () => focus, () => filt, { features: feats }, { COLORS: { brand: '#0B4EA2' } }, () => false);
  const passAll = { key: '*', ok: p => !!p.is_forecast };
  const L = (type, extra) => ({ type: 'Feature', properties: Object.assign({ type, route_id: 'R13', is_forecast: true }, extra || {}), geometry: { type: 'LineString', coordinates: mainL } });
  const B = (legName) => ({ type: 'Feature', properties: { type: 'BusyHours', route_id: 'R13', leg: legName, from: '16:00', to: '19:00' }, geometry: { type: 'LineString', coordinates: divL } });
  ok("⭐ C2 a route on the month's forecast draws its busy-hours roads, both legs, with no pick",
     busy({ on: true }, false, passAll, [L('Inbound Highway'), L('Outbound Highway'), B('loaded'), B('return')]).length === 2);
  ok("C3 a route not on the month's forecast, or with the timeline shut, draws none",
     busy({ on: true }, false, passAll, [L('Inbound Highway', { is_forecast: false }), B('loaded')]).length === 0
     && busy({ on: false }, false, passAll, [L('Inbound Highway'), B('loaded')]).length === 0);
  ok("⭐ C4 a dated diversion wins on its days: a diverted leg draws no busy-hours road",
     busy({ on: true }, false, passAll, [L('Inbound Highway', { div_when: '1–31 Dec 2027' }), L('Outbound Highway'), B('loaded'), B('return')]).length === 1);
  ok("C5 the overlay filter and a council view leave it out",
     busy({ on: true }, false, { key: 'x', ok: () => false }, [L('Inbound Highway'), B('loaded')]).length === 0
     && busy({ on: true }, true, passAll, [L('Inbound Highway'), B('loaded')]).length === 0);
}
ok("C6 a pick still draws its own (showBusyRoad), refilled with the month on every frame, filter and closing of the bar",
   fnSrc("showBusyRoad").includes("fillBusyRoads();") && fnSrc("renderMonthFrame").includes("fillBusyRoads()")
   && fnSrc("applyForecastFilter").includes("fillBusyRoads()") && fnSrc("closeTimeline").includes("fillBusyRoads()"));
ok("C7 the hours sit beside the loaded leg's road, read '16:00–19:00' (from–to), one a route and hours",
   fnSrc("fillBusyRoads").includes("properties: { hours: f.properties.from + '–' + f.properties.to }"));

// ---------------------------------------------------------------------------------------------------------------
console.log("D. The key");
{
  const ks = html.indexOf("    function divLegendRows("), ke = html.indexOf("    function divUsualSample(");
  const rows = (edge, usual, busy) => new Function("divOverlayPasses", "DIV_EDGE", "DIV_USUAL", "BUSY", "flowKeySvg", "FORECAST_LINE_WIDTH", "CONFIG", "rlEsc",
    html.slice(ks, ke) + "\nfunction divUsualSample(){return ''} function busySample(){return ''}\nreturn divLegendRows();")(
    () => ({ ok: () => true }), { colour: '#F59E0B', rail: 3, fc: { features: edge ? [{ properties: {} }] : [] } }, { fc: { features: usual ? [{}] : [] } },
    { shown: busy }, () => '', 5, { COLORS: { forecast: '#1F5FD6' } }, s => s);
  const bf = (f, t) => ({ properties: { from: f, to: t } });
  const r1 = rows(true, true, [bf('16:00', '19:00'), bf('16:00', '19:00')]);
  ok("⭐ D1 three rows, each only when its thing is on the map: the way round, the usual road, the busy hours with their hours",
     r1.includes('The way round a closure') && r1.includes('Usual road, not used this month') && r1.includes('Used 16:00 to 19:00 only'), r1);
  ok("D2 busy roads with different hours read 'Used in busy hours only'; nothing on the map, no row",
     rows(false, false, [bf('16:00', '19:00'), bf('07:00', '09:00')]).includes('Used in busy hours only') && rows(false, false, []) === '');
}
ok("D3 the key's samples are hidden from a screen reader (the row's words say it)", fnSrc("flowKeySvg").includes('aria-hidden="true"'));
// 25 Nov 2026: static's 2f1bc34 hid the old white lanes and gave the key an early path with its own single "goes round"
// row, so the usual road's and the busy-hours rows never showed (seen in the merged head's audit picture at 390 px)
{
  const rfl = fnSrc("renderFlowLegend"), early = (rfl.match(/if \(!FLOW_LANES_SHOWN\)[^\n]*/) || [''])[0];
  ok("⭐ D4 with the lanes hidden the key still draws divLegendRows() (all three rows), none in a council view; no old \"goes round\" row is left",
     /const divRows = councilFocus\(\) \? '' : divLegendRows\(\);/.test(rfl) && early.includes("box.innerHTML = divRows")
     && !html.includes("Where a route goes round a closure</div>"), early);
}

// ---------------------------------------------------------------------------------------------------------------
console.log("E. The guides");
ok("E1 the user guide's key row and busy-hours item say what the map now draws",
   help.includes("Where a route goes round a closure") && help.includes("Usual road, not used this month") && /busy hours[\s\S]{0,400}without a click|with no click/i.test(help));
ok("E2 the technical guide says how the rails sit outside the line, and no band width", /line-gap-width/.test(tech) && /div-usual/.test(tech) && !/dv_gap|DIV_GAP_NEAR_M/.test(tech));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
