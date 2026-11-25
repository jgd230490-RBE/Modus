/* map_lines_flow.js — 24 Nov 2026, the public map's route lines rethink, task B1 (claude/map-lines-flow).
 * John's "Yes, as recommended" to notes\public-map-lines-mockup-1124 Q1 to Q13 (24 Nov 2026, about 20:27 UTC), then his
 * "Arrowheads drifting" to card 3b's Q14 (22:46 UTC), which reopened Q6 (the dots): the white lanes go; each lane with
 * movements carries small SOLID ARROWHEADS, turned to its travel, on the LEFT of it, ONE gap on screen for every road at
 * every zoom; they show whenever the lanes are on the map, stand still unless Play runs, drift the way the lorries go
 * while it runs at one slow speed on screen, never under reduced motion; the key is ONE row, "Direction of travel". The
 * brief: notes\public-map-lines-build-1124\README.md ("John's choice on Q14"). The older pins it bends are narrowed where
 * they stand (parse_map.js, map_lines_static.js, ui_fix_map_card.js, test_help.py) with a dated note. Source checks and a
 * sandbox of the flow block against a stub map; no browser (the real pictures and the recording are on the mockup page
 * under card 3b, "Real · built, local copy"; the frame rates are in notes\session-1124-map-lines-flow.md). Every check
 * but the "kept" ones fails on b3bafdc.
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const tech = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
function fnSrc(name) {
  const i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    }\n", i);
  return html.slice(i, j > 0 ? j + 7 : i + 6000);
}
const code = html.split("\n").map(l => l.replace(/^\s*\/\/.*$/, "")).join("\n");
const fA = html.indexOf("    // ===== 16 Oct 2026 (D115, S17) — THE FLOW");
const fB = html.indexOf("    // ===== end of the flow =====");
const fblk = fA > 0 && fB > fA ? html.slice(fA, fB) : "";

// ---------------------------------------------------------------------------------------------------------------
console.log("A. The white lanes and the dots are gone; the lanes as data stay; one arrowhead layer");
ok("A1 no lane layer, no lanes' source, no lane widths, offset, still opacity or three lights a lane",
   !/'forecast-flow'/.test(code) && !html.includes("const FLOW_SOURCE") && !html.includes("'flow-source'")
   && !/const FLOW_(WIDTHS|OFFSET|STILL_OPACITY|PULSES|PULSE_LEN|PULSE_SPEED)\b/.test(html)
   && !/flowWidthExpr|placeFlowLayer|setFlowPulse/.test(code));
ok("A2 no dots and no bands in the flow (Q14 reopened Q6): no dot gaps, dot speed, dot size, circle layer or band step",
   !/FLOW_DOT_|flowDotPoints|setFlowDots|flowBand|FLOW_STOPS|flowSample\(/.test(code) && !/type: 'circle'/.test(fblk));
ok("A3 kept: the lanes are still worked out from the legs (buildFlowLanes) with each lane's movements (fl_mv)",
   /function buildFlowLanes\(/.test(fblk) && /fl_mv/.test(fblk));
ok("A4 the marks' one layer: a symbol of one picture on its own point source, turned on the map to each mark's travel, never pushing a name away",
   /id: 'forecast-flow-light', type: 'symbol', source: FLOW_LIGHT_SOURCE,/.test(fblk)
   && /'icon-image': FLOW_MARK_IMG, 'icon-rotate': \['get', 'rot'\],\s*'icon-rotation-alignment': 'map', 'icon-pitch-alignment': 'map',\s*'icon-allow-overlap': true, 'icon-ignore-placement': true/.test(fblk)
   && (fblk.match(/map\.addLayer\(/g) || []).length === 1 && (fblk.match(/map\.addImage\(/g) || []).length === 1);
ok("A5 the brief's values: 5.2 px long and across, a 0.8 px #00215B outline (the darkest band blue), 2.7 px left, 90 px apart, 13 px a second",
   html.includes("const FLOW_MARK_LEN = 5.2;") && html.includes("const FLOW_MARK_W = 5.2;") && html.includes("const FLOW_MARK_RING = '#00215B';")
   && html.includes("const FLOW_MARK_RING_W = 0.8;") && html.includes("const FLOW_MARK_SIDE = 2.7;") && html.includes("const FLOW_MARK_GAP = 90;")
   && html.includes("const FLOW_MARK_SPEED = 13;") && /CARBON_RAMP\s*=\s*\[[^\]]*'#00215B'\]/.test(html));
ok("A6 kept: the 'called forward' chevrons are untouched (their own layer, not the flow's)",
   /chevron/i.test(html.slice(0, fA)) || /chevron/i.test(html.slice(fB)));

// ---------------------------------------------------------------------------------------------------------------
console.log("B. The sandbox: the flow block against a stub map");
const mk = () => {
  const layers = {}, sources = {}, order = [], images = {}, handlers = {};
  return { layers, sources, order, images, handlers, zoom: 10, view: [-1, 51, 4, 53],
    getLayer: id => layers[id], getSource: id => sources[id],
    getZoom() { return this.zoom; },
    getBounds() { const v = this.view; return { getWest: () => v[0], getSouth: () => v[1], getEast: () => v[2], getNorth: () => v[3] }; },
    addSource(id, spec) { sources[id] = { spec, _data: spec.data, n: 0, setData(d) { this._data = d; this.n++; } }; },
    addLayer(spec) { layers[spec.id] = { spec, paint: Object.assign({}, spec.paint), layout: Object.assign({}, spec.layout) }; order.push(spec.id); },
    removeLayer(id) { delete layers[id]; order.splice(order.indexOf(id), 1); },
    setPaintProperty(id, k, v) { layers[id].paint[k] = v; },
    setLayoutProperty(id, k, v) { layers[id].layout[k] = v; },
    getLayoutProperty: (id, k) => layers[id].layout[k],
    hasImage: id => !!images[id], addImage(id, data, opts) { images[id] = { data, opts }; },
    on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); },
    getStyle: () => ({ layers: order.map(id => ({ id })) }),
    moveLayer() {} };
};
const fmap = mk();
const els = {}, drawn = [];
const ctx = { scale(a, b) { drawn.push(["scale", a, b]); }, beginPath() { drawn.push(["begin"]); }, moveTo(x, y) { drawn.push(["M", x, y]); },
  lineTo(x, y) { drawn.push(["L", x, y]); }, closePath() { drawn.push(["Z"]); }, fill() { drawn.push(["fill", this.fillStyle]); },
  stroke() { drawn.push(["stroke", this.strokeStyle, this.lineWidth, this.lineJoin]); }, getImageData: (x, y, w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }) };
const document = { getElementById: id => els[id] || (els[id] = { id, checked: true, hidden: true, innerHTML: "" }),
                   createElement: t => ({ tag: t, width: 0, height: 0, getContext: () => ctx }) };
const RAMP = ['#72A7FF', '#006AFD', '#0051C4', '#00388E', '#00215B'];
const a1_data = { features: [] };
let focus = false, raf = [];
let F = null, err = "";
try {
  F = new Function("map", "document", "a1_data", "modeRoutesPassing", "councilFocus", "mapModeMonth", "forecastWindow", "rlEsc", "monthLabel",
    "stepRanges", "VOLUME_STOPS", "ROUTE_VOLUME_STOPS", "CONFIG", "FORECAST_LINE_WIDTH", "FORECAST_CASING_WIDTH", "raiseMarks",
    "heatMode", "CARBON_RAMP", "LINE_BAND_WIDTHS", "LINE_BAND_PAD", "requestAnimationFrame",
    fblk + "\nreturn { FLOW, FLOW_MARK_GAP, FLOW_MARK_SPEED, FLOW_MARK_SIDE, FLOW_MARK_MARGIN, FLOW_MARK_MAX, FLOW_MARK_IMG, flowMarkPoints, mercX, mercY, setFlowMarks, flowMarksOnMove, ensureFlowLayer, renderFlowLegend, flowMarkSample, flowMarkImage, drawFlow, get clock(){ return _flowClock; } };")(
    fmap, document, a1_data, () => ({}), () => focus, () => 16, () => [9, 12], t => String(t), i => "Apr 2027",
    s => [], [10, 25, 50, 100], [10, 25, 50, 100], { FORECAST_UNIT: "vehicles", COLORS: { forecast: "#0B4EA2", forecastCasing: "#FFFFFF" } }, 5, 7.6, () => {},
    () => "volume", RAMP, [3, 4.5, 6, 8, 10], 2.4, fn => { raf.push(fn); return raf.length; });
} catch (e) { err = e.message; }
ok("B0 the flow block runs against a stub map", !!F, err);

if (F) {
  const px = (c, z) => { const W = 512 * Math.pow(2, z); return [F.mercX(c[0]) * W, F.mercY(c[1]) * W]; };
  const bounds = v => ({ getWest: () => v[0], getSouth: () => v[1], getEast: () => v[2], getNorth: () => v[3] });
  const eastLane = () => ({ coords: [[-1.4, 52.6], [-0.85, 52.6], [-0.3, 52.6]] });   // two pieces, west to east, 1.1°
  const westLane = () => ({ coords: [[-0.3, 52.6], [-1.4, 52.6]] });                  // the same road, east to west
  const marks = (ts, zoom, view) => F.flowMarkPoints(ts, { zoom, bounds: bounds(view || [-2, 51, 1, 54]) }).features;
  const xy = (ts, zoom, view) => marks(ts, zoom, view).map(f => f.geometry.coordinates);

  console.log("B. ONE gap on screen for every road, at every zoom");
  let gapsOk = true; const seen = [];
  for (const z of [9.6, 11, 12.6, 14]) {
    F.FLOW.lit = [{ lane: eastLane() }];
    const p = xy(1234, z).map(c => px(c, z));
    const d = p.slice(1).map((q, i) => Math.hypot(q[0] - p[i][0], q[1] - p[i][1]));
    seen.push([z, d.length, d.length ? Math.round(d.reduce((a, x) => a + x, 0) / d.length * 100) / 100 : null]);
    if (d.length < 2 || d.some(x => Math.abs(x - 90) > 0.05)) gapsOk = false;
  }
  ok("B1 the arrowheads are 90 px apart on screen at zooms 9.6, 11, 12.6 and 14, across a lane's bend", gapsOk, seen);
  F.FLOW.lit = [{ lane: eastLane() }, { lane: { coords: [[-1.4, 52.7], [-0.3, 52.7]] } }];
  const rowA = xy(500, 12.6).filter(c => c[1] < 52.65).length, rowB = xy(500, 12.6).filter(c => c[1] > 52.65).length;
  ok("B2 a busy lane and a quiet one of the same length carry as many marks: the gap says nothing of the amount",
     rowA > 5 && Math.abs(rowA - rowB) <= 1 && !/fl_mv/.test(fnSrc("flowMarkPoints")), [rowA, rowB]);

  console.log("C. Left of travel, turned to it");
  const z = 12.6, roadY = px([-0.85, 52.6], z)[1], roadX = px([-0.85, 52.6], z)[0];
  F.FLOW.lit = [{ lane: eastLane() }];
  const eM = marks(500, z), eY = eM.map(f => px(f.geometry.coordinates, z)[1] - roadY);
  F.FLOW.lit = [{ lane: westLane() }];
  const wM = marks(500, z), wY = wM.map(f => px(f.geometry.coordinates, z)[1] - roadY);
  ok("C1 going east they sit 2.7 px NORTH of the line and point east (rot 90); going west 2.7 px SOUTH, pointing west (rot -90)",
     eM.length > 0 && wM.length > 0 && eY.every(y => Math.abs(y + 2.7) < 0.01) && wY.every(y => Math.abs(y - 2.7) < 0.01)
     && eM.every(f => f.properties.rot === 90) && wM.every(f => f.properties.rot === -90), [eY.slice(0, 2), wY.slice(0, 2), eM[0] && eM[0].properties, wM[0] && wM[0].properties]);
  F.FLOW.lit = [{ lane: { coords: [[-0.85, 52.55], [-0.85, 52.65]] } }];
  const nM = marks(500, z), nX = nM.map(f => px(f.geometry.coordinates, z)[0] - roadX);
  ok("C2 going north they sit 2.7 px WEST of the line and point north (rot 0)", nM.length > 0 && nX.every(x => Math.abs(x + 2.7) < 0.01) && nM.every(f => f.properties.rot === 0), nX.slice(0, 2));
  F.FLOW.lit = [{ lane: { coords: [[-0.9, 52.65], [-0.8, 52.55]] } }];
  const seM = marks(500, z);
  const seRot = Math.atan2(px([-0.8, 52.55], z)[0] - px([-0.9, 52.65], z)[0], -(px([-0.8, 52.55], z)[1] - px([-0.9, 52.65], z)[1])) * 180 / Math.PI;
  ok("C3 going south-east they point the way the line runs on screen (rot = its bearing, to a tenth of a degree)",
     seM.length > 0 && seM.every(f => Math.abs(f.properties.rot - seRot) <= 0.05), [seRot, seM[0] && seM[0].properties.rot]);
  ok("C4 a road's two rows (5.4 px apart) never touch: an arrowhead is 5.2 px across", 2 * F.FLOW_MARK_SIDE > 5.2);

  console.log("D. Standing still, or drifting at one slow speed");
  let speedOk = true; const sp = [];
  for (const zz of [9.6, 12.6]) {
    F.FLOW.lit = [{ lane: eastLane() }];
    const x0 = xy(10000, zz).map(c => px(c, zz)[0]), x1 = xy(10100, zz).map(c => px(c, zz)[0]);
    const shift = x1.map((x, i) => x - x0[i]).filter((s, i) => i < Math.min(x0.length, x1.length) - 1);
    sp.push([zz, shift.slice(0, 2)]);
    if (!shift.length || shift.some(s => Math.abs(s - 1.3) > 0.02)) speedOk = false;
  }
  ok("D1 0.1 s of Play on, every arrowhead is 1.3 px further along its travel (13 px a second on screen), the same at zoom 9.6 and 12.6", speedOk, sp);
  F.FLOW.lit = [{ lane: eastLane() }];
  const loopA = xy(0, 12.6).map(c => c[0].toFixed(9)).join(), loopB = xy(90 / 13 * 1000, 12.6).map(c => c[0].toFixed(9)).join();
  ok("D2 after one gap's drift (90 px at 13 px a second) they stand where they started: the drift loops, never jumps", loopA.length > 0 && loopA.slice(20, 200) === loopB.slice(20, 200));
  ok("D3 the drift has its own clock, run only while Play runs (a pause leaves them standing; Play carries on without a jump), moved about 15 times a second",
     /if\(_flowLast!=null\) _flowClock\+=Math\.min\(ts-_flowLast, 250\);\s*_flowLast=ts;/.test(html)
     && /ts-_flowT>=FLOW_MARK_STEP_MS\)\{ _flowT=ts; setFlowMarks\(_flowClock\); \}/.test(html) && html.includes("const FLOW_MARK_STEP_MS = 66;")
     && /if\(!TL\.playing\)\{ _flowRAF=null; _flowLast=null; setFlowMarks\(_flowClock\); return; \}/.test(html)
     && /function stopFlowAnimation\(\)\{\s*if\(_flowRAF!=null\)\{ cancelAnimationFrame\(_flowRAF\); _flowRAF=null; \}\s*_flowLast=null; setFlowMarks\(_flowClock\);/.test(html));
  ok("D4 reduced motion: Play starts no drift and the arrowheads stand still",
     /function startFlowAnimation\(\)\{\s*if\(reducedMotion\(\)\)\{ setFlowMarks\(_flowClock\); return; \}/.test(html));

  console.log("E. Only the part in view");
  F.FLOW.lit = [{ lane: { coords: [[-3, 52.6], [3, 52.6]] } }];
  const zv = 12.6, vw = [-0.95, 52.55, -0.80, 52.65];
  const inView = xy(777, zv, vw);
  const W = 512 * Math.pow(2, zv), mx0 = F.mercX(vw[0]) * W - 48, mx1 = F.mercX(vw[2]) * W + 48;
  ok("E1 a lane 6° long in ONE piece, a view 0.15° wide: marks are made only within the view and its 48 px margin",
     inView.length > 0 && inView.every(c => { const x = F.mercX(c[0]) * W; return x >= mx0 - 0.01 && x <= mx1 + 0.01; })
     && inView.length <= Math.ceil((mx1 - mx0) / 90) + 1, inView.length);
  ok("E2 a lane wholly outside the view makes none", xy(777, zv, [10, 50, 10.1, 50.1]).length === 0);
  F.FLOW.lit = Array.from({ length: 200 }, (_, i) => ({ lane: { coords: [[-3, 52 + i * 0.001], [3, 52 + i * 0.001]] } }));
  ok("E3 at most FLOW_MARK_MAX (5,000) at once, however much is in view", F.FLOW_MARK_MAX === 5000 && xy(1, 12, [-3, 51, 3, 53]).length === 5000);
  ok("E4 a pan or a zoom places them again, once a frame at most (wired once on the map's move)",
     /if \(!FLOW\.moveWired && map\.on\) \{ FLOW\.moveWired = true; map\.on\('move', flowMarksOnMove\); \}/.test(html)
     && /function flowMarksOnMove\(\)\{\s*if \(FLOW\.movePending/.test(html));

  console.log("F. Shown whenever the lanes are on the map");
  fmap.addSource("routes-source", { type: "geojson", data: a1_data });
  ["forecast-casing", "forecast-layer", "forecast-cap-badge"].forEach(id => fmap.addLayer({ id, paint: {}, layout: {} }));
  try { F.ensureFlowLayer(); } catch (e) { err = e.message; }
  const img = fmap.images[F.FLOW_MARK_IMG];
  ok("F1 the picture: a white triangle pointing UP, its base 5.2 px across and 5.2 px from base to tip, a 0.8 px #00215B outline, at twice the screen's px",
     !!img && img.opts && img.opts.pixelRatio === 2
     // a 9 px square (5.2 + 2 x 0.8, rounded up, + 2), its middle at 4.5: tip (4.5, 1.9), base (7.1, 7.1) to (1.9, 7.1)
     && drawn.filter(d => d[0] === "M" || d[0] === "L").map(d => d.slice(1)).every((q, i) => [[4.5, 1.9], [7.1, 7.1], [1.9, 7.1]][i].every((v, k) => Math.abs(v - q[k]) < 1e-9))
     && drawn.filter(d => d[0] === "M" || d[0] === "L").length === 3
     && drawn.some(d => d[0] === "fill" && d[1] === "#ffffff") && drawn.some(d => d[0] === "stroke" && d[1] === "#00215B" && d[2] === 0.8 && d[3] === "round"),
     drawn);
  const nImg = drawn.length; F.ensureFlowLayer();
  ok("F2 the picture is made once a style (a basemap switch drops it; ensureFlowLayer makes it again only when it is missing)", drawn.length === nImg);
  delete fmap.images[F.FLOW_MARK_IMG]; F.flowMarkImage();
  ok("F3 ...and made again when the style lost it", !!fmap.images[F.FLOW_MARK_IMG]);
  ok("F4 the map's move is listened to once", (fmap.handlers.move || []).length === 1);
  const src = fmap.getSource("flow-light-source");
  const n = () => (src && src._data && src._data.features || []).length;
  fmap.zoom = 12.6; fmap.view = [-1, 52.5, -0.7, 52.7];
  F.FLOW.lit = [{ lane: eastLane() }]; F.FLOW.drawn = "x";
  F.setFlowMarks(F.clock);
  ok("F5 standing still (no Play), a lane on screen carries its arrowheads", n() > 0 && n() === F.FLOW.marksShown, n());
  F.setFlowMarks(null);
  const none = n();
  focus = true; F.setFlowMarks(1000); const council = n(); focus = false;
  ok("F6 none when asked for none, none in a council view", none === 0 && council === 0);
  raf = []; F.setFlowMarks(F.clock); fmap.view = [-0.9, 52.55, -0.8, 52.65]; F.flowMarksOnMove(); F.flowMarksOnMove();
  const before = n(); raf.forEach(fn => fn()); const after = n();
  ok("F7 a move asks for one placing a frame, and the next frame places them for the new view", raf.length === 1 && after > 0 && after < before, [raf.length, before, after]);
  ok("F8 the council views still hide the flow (COUNCIL_QUIET_LAYERS holds the marks' layer) and set them again on the way out",
     html.includes("const COUNCIL_QUIET_LAYERS = ['forecast-casing', 'forecast-flow-light', 'forecast-cap-badge'];")
     && /COUNCIL_QUIET_LAYERS\.forEach\([^\n]*\n\s*if \(typeof setFlowMarks === 'function'\) setFlowMarks\(_flowClock\);/.test(html));
  ok("F9 a month step, a filter or a basemap switch sets them at once (drawFlow sets them), and a diversion change rebuilds the lanes (DIV.rev)",
     /FLOW\.count = feats\.length;\s*setFlowMarks\(_flowClock\);\s*renderFlowLegend\(\);/.test(fnSrc("drawFlow")) && /DIV\.rev/.test(fnSrc("flowLanes")));

  console.log("G. The key: one row, Direction of travel");
  F.FLOW.count = 3;
  F.renderFlowLegend();
  const box = document.getElementById("flow-legend").innerHTML;
  const rows = box.match(/<div class="ml-row"[^>]*>/g) || [];
  ok("G1 ONE row (no closure on the map here): an arrowhead sample, 'Direction of travel' and an 'i'; the title and the five band rows are gone",
     rows.length === 1 && box.includes("<span>Direction of travel</span>") && box.includes('aria-label="About the arrowheads"')
     && !/Movements a day|under 10|100 and over|In Apr 2027/.test(box), box.slice(0, 400));
  const poly = (box.match(/<polygon points="([^"]+)"/g) || []).map(s => s.match(/points="([^"]+)"/)[1].split(" ").map(p => p.split(",").map(Number)));
  ok("G2 the sample: the Off line on its white casing, an arrowhead each way on its own side (the upper one points right, the lower left), at the closure sample's scale",
     poly.length === 2 && poly[0][1][0] > poly[0][0][0] && poly[0][1][1] < 6 && poly[1][1][0] < poly[1][0][0] && poly[1][1][1] > 6
     && box.includes('<svg class="fl-sw"') && box.includes('stroke="#0B4EA2" stroke-width="5"') && box.includes('stroke="#FFFFFF" stroke-width="7.6"')
     && box.includes('fill="#ffffff" stroke="#00215B" stroke-width="0.8"'), poly);
  const info = (box.match(/<div class="info-pop" id="info-flow"[^>]*><p>([\s\S]*?)<\/p>/) || [, ""])[1];
  const words = info.split(/\s+/).filter(Boolean).length, sentences = (info.match(/[.!?](\s|$)/g) || []).length;
  ok("G3 the 'i' says the arrowheads show the way lorries travel, each direction on its own side, and are not vehicles, in at most 2 sentences and 30 words",
     /arrowheads show the way lorries travel/.test(info) && /own side/.test(info) && /not vehicles/.test(info) && words <= 30 && sentences <= 2, [words, sentences, info]);
  const txt = box.replace(/<[^>]+>/g, " ");
  ok("G4 nothing a person reads in the key says truck, real-time, live tracking, telematics, AI, optimise, predict, secure, dot, lane or width",
     !/truck|real-time|live tracking|telematics|optimi[sz]e|predict|\bsecure\b|\bdots?\b|\blane|\bwidth|\bwider/i.test(txt) && !/\bAI\b/.test(txt));
  focus = true; F.renderFlowLegend(); const hiddenInCouncil = document.getElementById("flow-legend").hidden; focus = false;
  F.FLOW.count = 0; F.renderFlowLegend(); const hiddenEmpty = document.getElementById("flow-legend").hidden;
  ok("G5 the key hides in a council view and with no lane on the map", hiddenInCouncil === true && hiddenEmpty === true);
  ok("G6 the 'i' stays open across a rebuild", fnSrc("renderFlowLegend").includes("const was = document.getElementById('info-flow'), open = !!(was && !was.hidden);"));
}

console.log("H. Kept: the diversion's row (the diversions session's)");
const divSrc = fnSrc("divEdgeSample");
ok("H1 kept: divEdgeSample is byte for byte as on b3bafdc", crypto.createHash("sha1").update(divSrc).digest("hex") === "c7807aa92b1b38f9520638892609b794da55ee14", divSrc.length);
ok("H2 kept: the '#div-legend' row's markup and words as on b3bafdc, inside the same box",
   html.includes(`? '<div class="ml-row" id="div-legend">' + divEdgeSample() + 'Where a route goes round a closure</div>' : '');`)
   && html.includes('<div class="mode-legend" id="flow-legend" hidden></div>'));

console.log("I. The guides");
ok("I1 the user guide §8.3 says the arrowheads: the way, each on its own side, not how many, not vehicles, standing still unless playing",
   guide.includes("Small white arrowheads on the lines show the way the lorries go, each direction on its own side, on the left as driven")
   && guide.includes("<strong>They show the way, not how many</strong>") && guide.includes("They are not vehicles.")
   && guide.includes("<em>Direction of travel</em>") && guide.includes("they stand still.")
   && !guide.includes("The closer the dots") && !guide.includes("A wider lane means more movements a day") && !guide.includes("<em>Movements a day, each way</em>"));
ok("I2 the technical guide names the arrowheads' gap, speed, side, clock and the part in view; no dots, no lane drawn",
   tech.includes("<strong>Flow arrowheads.</strong>") && tech.includes("<code>FLOW_MARK_GAP</code>, 90 px on screen at every zoom")
   && tech.includes("<code>FLOW_MARK_SPEED</code>, 13 px a second") && tech.includes("They say the direction, never the amount.")
   && !tech.includes("<strong>Flow dots.</strong>") && !tech.includes("<strong>Flow lanes.</strong>") && !tech.includes("FLOW_DOT_"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
