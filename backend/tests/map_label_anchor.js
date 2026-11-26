/* map_label_anchor.js — 26 Nov 2026, claude/map-label-anchor (a fault found in passing by the route-lines plan session).
 * On the public map, labelAnchor() is the layer every route line is inserted before, so road and place names print over
 * the lines. It took the first TEXT layer whose id was not on a short list of the page's own prefixes. Four text layers of
 * ours were not on it: the usual road's crosses (div-usual-x, PR #330, inserted under forecast-casing), the traffic
 * limit's badge, the holding chevrons and the busy-hours times. So with a month on screen the anchor was one of OURS,
 * under the month's forecast lines, and every line added or moved there afterwards went UNDER the forecast lines: the
 * shared road sections (a shared road showed one route's band, not the road's total), a picked route, the busy-hours
 * road and the abnormal loads. The fix: the page's own map.addLayer wrapper stamps every layer it adds
 * (metadata 'wayscope:own'), and labelAnchor() never answers a stamped layer, whatever its id.
 * Seen in Chrome after that fix: a basemap switch makes the pick, the abnormal loads and the traffic limits again BEFORE
 * the forecast lines, which then come in over them. So the layers over the lines have ONE order (OVER_LINES,
 * restackOverLines(), run by raiseMarks() on every forecast re-add and by selectRoute()): part C.
 * The real labelAnchor(), restackOverLines() and addLayer wrapper are run against a stand-in map; no browser (the real
 * pictures are in notes\route-lines-plan-1126\check\fix\). On main 3a3e592, 17 of the 22 checks fail (A4, A5, B3, B4 and
 * B5 hold there too).
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const sly = fs.readFileSync(path.join(ROOT, "map", "site-layouts.js"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
function fnSrc(name) {
  const i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    }\n", i);
  return html.slice(i, j + 6);
}
// the wrapper block: from its comment to the end of map.addLayer = function … };
const wStart = html.indexOf("    // every addLayer of the page goes through here");
const wEnd = html.indexOf("\n    };\n", html.indexOf("map.addLayer = function (layer, before) {", wStart));
const wrapperSrc = wStart >= 0 && wEnd > wStart ? html.slice(wStart, wEnd + 7) : "";

// a stand-in map: an ordered layer list with Mapbox's add / move semantics; getStyle() lists a copy of each layer as
// Mapbox does (metadata kept), so nothing can key on the object handed in
function stubMap(base) {
  const layers = base.map(l => JSON.parse(JSON.stringify(l)));
  const m = {
    layers,
    getStyle: () => ({ layers: layers.map(l => JSON.parse(JSON.stringify(l))) }),
    getLayer: id => { const l = layers.find(x => x.id === id); return l ? JSON.parse(JSON.stringify(l)) : undefined; },
    addLayer: (l, before) => { const c = JSON.parse(JSON.stringify(l)); const i = before ? layers.findIndex(x => x.id === before) : -1;
      if (i >= 0) layers.splice(i, 0, c); else layers.push(c); },
    moveLayer: (id, before) => { const i = layers.findIndex(x => x.id === id); const [c] = layers.splice(i, 1);
      const j = before ? layers.findIndex(x => x.id === before) : -1; if (j >= 0) layers.splice(j, 0, c); else layers.push(c); },
  };
  return m;
}
// the page's own wrapper and labelAnchor, run on the stand-in (styleHasSlots false: a classic basemap)
function sandbox(base) {
  const map = stubMap(base);
  const api = new Function("map", "styleHasSlots", "SLOT_TYPES", "EMISSIVE",
    wrapperSrc + "\n" + fnSrc("labelAnchor") + "\nreturn { labelAnchor };")(map, () => false, new Set(["line", "fill"]), { line: "line-emissive-strength" });
  const ids = () => map.layers.map(l => l.id);
  return { map, anchor: api.labelAnchor, ids, at: id => ids().indexOf(id) };
}
const T = (id, source) => ({ id, type: "symbol", source, layout: { "text-field": ["get", "name"] } });
const LN = (id, source) => ({ id, type: "line", source });
// a Light basemap, cut down: its lines, then its names
const BASEMAP = [{ id: "land", type: "background" }, LN("road-primary", "composite"), LN("road-secondary", "composite"),
  T("road-label-simple", "composite"), T("settlement-minor-label", "composite"), T("settlement-major-label", "composite")];
const names = new Set(BASEMAP.filter(l => l.type === "symbol").map(l => l.id));

// ---------------------------------------------------------------------------------------------------------------
console.log("A. The rule: the anchor is always the basemap's own first name layer");
{
  // the page's add order with a month on and a diversion on, as main 3a3e592 runs it (ensureForecastLayers, then
  // ensureUsualRoad's crosses under forecast-casing, the traffic limits, the chevrons, the busy-hours times), every
  // one through the page's map.addLayer and before labelAnchor() where the page does so
  let s = null, err = null;
  try {
    s = sandbox(BASEMAP);
    const add = (l, before) => s.map.addLayer(l, before);
    add(LN("outbound-lines", "routes-source"), s.anchor()); add(LN("inbound-lines", "routes-source"), s.anchor());
    add(LN("forecast-casing", "routes-source"), s.anchor()); add(LN("forecast-layer", "routes-source"), s.anchor());
    add(T("div-usual-x", "div-usual-source"), "forecast-casing");
    add(T("traffic-limit-badge", "traffic-limit-source"), s.anchor());
    add(T("holding-chevrons", "holding-source"), s.anchor());
    add(T("busy-hours-at", "busy-hours-at"));                    // added on top, then moved under the names (placeBusyRoads)
    s.map.moveLayer("busy-hours-at", s.anchor());
  } catch (e) { err = String(e); }
  ok("⭐ A1 with div-usual-x, traffic-limit-badge, holding-chevrons and busy-hours-at under the forecast lines, the anchor is the basemap's road-label-simple",
     !err && !!s && s.anchor() === "road-label-simple", err || (s && { anchor: s.anchor(), order: s.ids() }));
  ok("⭐ A2 none of the four is ever the anchor, and the anchor is above the forecast lines",
     !err && !!s && !["div-usual-x", "traffic-limit-badge", "holding-chevrons", "busy-hours-at"].includes(s.anchor())
     && s.at(s.anchor()) > s.at("forecast-layer"), err || (s && s.anchor()));
  // what is added next goes OVER the forecast lines and under the names
  let order = null;
  try {
    const add = (l) => s.map.addLayer(l, s.anchor());
    add(LN("road-load-casing", "road-load-source")); add(LN("road-load-line", "road-load-source"));
    add(LN("abnormal-public-casing", "abnormal-public")); add(LN("abnormal-public-lines", "abnormal-public"));
    add(LN("busy-casing", "busy-route")); add(LN("busy-core", "busy-route"));
    add(LN("sel-glow", "selected-route")); add(LN("sel-casing", "selected-route")); add(LN("sel-core", "selected-route"));
    ["busy-casing", "busy-core", "sel-glow", "sel-casing", "sel-core", "busy-hours-at"].forEach(l => s.map.moveLayer(l, s.anchor()));   // selectRoute
    order = s.ids();
  } catch (e) { err = String(e); }
  const over = ["road-load-casing", "road-load-line", "busy-casing", "busy-core", "sel-glow", "sel-casing", "sel-core", "abnormal-public-lines"];
  ok("⭐ A3 the shared sections, the busy road, the pick and the abnormal loads added (or moved) at the anchor land OVER forecast-layer",
     !err && !!order && over.every(l => s.at(l) > s.at("forecast-layer")), err || order);
  ok("⭐ A4 and all of them stay UNDER the basemap's names",
     !err && !!order && over.every(l => s.at(l) < s.at("road-label-simple")), order);
  ok("A5 selectRoute's moves keep the pick over the busy road (sel-core is the highest of them)",
     !err && !!order && s.at("sel-core") > s.at("busy-core") && s.at("sel-core") > s.at("road-load-line"), order);
}
{
  // a FUTURE text layer of ours, with an id no list could know (even one that looks like a basemap name), is never the anchor
  let s = null, a = null;
  try {
    s = sandbox(BASEMAP);
    s.map.addLayer(LN("forecast-layer", "routes-source"), s.anchor());
    s.map.addLayer(T("road-label-our-new-words", "our-source"), "forecast-layer");
    s.map.addLayer(T("zz-anything", "our-source"), "forecast-layer");
    a = s.anchor();
  } catch (e) { a = "threw " + e; }
  ok("⭐ A6 a new text layer of ours under the lines, whatever its id, is never the anchor (the stamp, not a name list)",
     a === "road-label-simple", { a, order: s && s.ids() });
  ok("A7 every layer added through the page's map.addLayer carries the stamp; the basemap's own layers carry none",
     !!s && s.map.layers.filter(l => !names.has(l.id) && !["land", "road-primary", "road-secondary"].includes(l.id)).every(l => l.metadata && l.metadata["wayscope:own"] === true)
     && s.map.layers.filter(l => names.has(l.id)).every(l => !l.metadata), s && s.map.layers.map(l => [l.id, l.metadata]));
  let kept = null;
  try { const s2 = sandbox(BASEMAP); s2.map.addLayer({ id: "x", type: "line", source: "s", metadata: { note: "mine" } }); kept = s2.map.layers.find(l => l.id === "x").metadata; } catch (e) { kept = String(e); }
  ok("A8 the stamp keeps any metadata a layer already has", !!kept && kept.note === "mine" && kept["wayscope:own"] === true, kept);
}
{
  // Standard: the basemap's layers sit in an import and getStyle().layers lists only ours: no anchor (the 'middle' slot does it)
  let a = "unset";
  try { const s = sandbox([]); s.map.addLayer(LN("forecast-layer", "routes-source")); s.map.addLayer(T("div-usual-x", "div-usual-source"), "forecast-layer"); a = s.anchor(); } catch (e) { a = "threw " + e; }
  ok("⭐ A9 on a style that lists only our layers (Standard) there is no anchor, never one of ours", a === undefined, a);
  // a council view: the town names go UNDER the council fill (placeTownNames); the anchor is the first basemap name above it
  let c = null;
  try {
    const s = sandbox([{ id: "land", type: "background" }, T("settlement-minor-label", "composite"), T("settlement-major-label", "composite"), T("road-label-simple", "composite")]);
    s.map.addLayer({ id: "area-fill", type: "fill", source: "areas-source" }, "settlement-minor-label");
    s.map.moveLayer("area-fill", "road-label-simple");          // the towns are under the fill now
    s.map.addLayer(T("div-usual-x", "div-usual-source"), "road-label-simple");
    c = s.anchor();
  } catch (e) { c = "threw " + e; }
  ok("A10 in a council view the anchor is still the first basemap name above the fill, never a text layer of ours there", c === "road-label-simple", c);
}

// ---------------------------------------------------------------------------------------------------------------
console.log("B. Source checks");
ok("⭐ B1 the page's map.addLayer stamps every layer it adds as ours, keeping its metadata",
   /const OWN_LAYER_MARK = 'wayscope:own';/.test(wrapperSrc)
   && /map\.addLayer = function \(layer, before\) \{\n\s+if \(layer && typeof layer === 'object'\) \{\n\s+layer\.metadata = Object\.assign\(\{\}, layer\.metadata \|\| \{\}, \{ \[OWN_LAYER_MARK\]: true \}\);/.test(wrapperSrc));
const la = fnSrc("labelAnchor");
ok("⭐ B2 labelAnchor() never answers a stamped layer, read by the stamp's own name, and still skips the old prefixes",
   la.includes("!(x.metadata && x.metadata['wayscope:own'])") && /x\.type === 'symbol' && x\.layout && x\.layout\['text-field'\]/.test(la)
   && la.includes("(forecast|road-load|temp-haul|site|restriction|limit|area|community|abnormal|collision|evr)"));
ok("B3 nothing on the page adds a layer around the wrapper: _addLayerRaw is called only inside it",
   (html.match(/_addLayerRaw\(/g) || []).length === 1 && wrapperSrc.includes("return _addLayerRaw(layer, before);"));
ok("B4 the site layouts add their layers through the map they are given (map.addLayer, so the page's wrapper)",
   (sly.match(/map\.addLayer\(/g) || []).length >= 2 && !/_addLayerRaw|addLayer\.call|Map\.prototype\.addLayer/.test(sly));
const textLayer = id => new RegExp("id: ?'" + id + "'[\\s\\S]{0,600}'text-field'").test(html);
ok("B5 the four layers that were taken for the anchor are text layers of the page (the premise of A1)",
   ["div-usual-x", "traffic-limit-badge", "holding-chevrons", "busy-hours-at"].every(textLayer));
ok("B6 the anchor's comment names why: our text layers under the lines, found by the stamp",
   html.includes("a text layer of OURS is never the anchor, whatever its id"));

// ---------------------------------------------------------------------------------------------------------------
console.log("C. The one order over the lines (restackOverLines), after a basemap switch and on a pick");
const olm = html.match(/    const OVER_LINES = \[[^\]]*\];/);
const restackSrc = (olm ? olm[0] : "") + "\n" + fnSrc("restackOverLines");
function sandbox2(base) {
  const map = stubMap(base);
  let moves = 0; const mv = map.moveLayer; map.moveLayer = (a, b) => { moves++; mv(a, b); };
  const api = new Function("map", "styleHasSlots", "SLOT_TYPES", "EMISSIVE",
    wrapperSrc + "\n" + fnSrc("labelAnchor") + "\n" + restackSrc + "\nreturn { labelAnchor, restackOverLines, OVER_LINES };")(
      map, () => false, new Set(["line", "fill"]), { line: "line-emissive-strength" });
  const ids = () => map.layers.map(l => l.id);
  return { map, api, ids, at: id => ids().indexOf(id), moves: () => moves };
}
// the order the stack must read, bottom to top, between the forecast lines and the basemap's names
const WANT = ["forecast-casing", "forecast-layer", "road-load-casing", "road-load-line", "diversion-edge", "busy-casing", "busy-core",
  "sel-glow", "sel-casing", "sel-core", "abnormal-public-casing", "abnormal-public-lines",
  "traffic-limit-fill", "traffic-limit-band", "traffic-limit-edge", "traffic-limit-badge"];
const inOrder = (s, list, top) => list.every((id, i) => s.at(id) >= 0 && (i === 0 || s.at(id) > s.at(list[i - 1]))) && s.at(list[list.length - 1]) < s.at(top);
{
  // after a switch to Streets, as read in Chrome on 26 Nov 2026 (main 3a3e592): the pick, the abnormal loads and the
  // traffic limits made again BEFORE the forecast lines, which then came in over them
  let s = null, r = null;
  try {
    s = sandbox2(BASEMAP);
    const add = (l) => s.map.addLayer(l, s.api.labelAnchor());
    ["busy-casing", "busy-core", "sel-glow", "sel-casing", "sel-core"].forEach(id => add(LN(id, "selected-route")));
    s.map.addLayer(T("busy-hours-at", "busy-hours-at"));               // no before: on top, then a pick moves it under the names
    s.map.moveLayer("busy-hours-at", s.api.labelAnchor());
    ["abnormal-public-casing", "abnormal-public-lines"].forEach(id => add(LN(id, "abnormal-public-source")));
    add({ id: "traffic-limit-fill", type: "fill", source: "traffic-limit-source" });
    ["traffic-limit-band", "traffic-limit-edge"].forEach(id => add(LN(id, "traffic-limit-source")));
    add(T("traffic-limit-badge", "traffic-limit-badges"));
    ["forecast-casing", "forecast-layer", "road-load-casing", "road-load-line", "diversion-edge"].forEach(id => add(LN(id, "routes-source")));
    r = { before: inOrder(s, WANT, "road-label-simple") };
    s.api.restackOverLines();
    r.after = inOrder(s, WANT.concat(["busy-hours-at"]), "road-label-simple");
  } catch (e) { r = "threw " + e; }
  ok("⭐ C1 after a basemap switch the stack is put back: forecast lines, shared sections, rails, busy road, pick, abnormal, traffic limits, the pick's hours, then the basemap's names",
     r && r.before === false && r.after === true, { r, ids: s && s.ids() });
  let m2 = null;
  try { const n = s.moves(); s.api.restackOverLines(); m2 = s.moves() - n; } catch (e) { m2 = "threw " + e; }
  ok("C2 once the order holds it moves nothing (it runs on every forecast re-add)", m2 === 0, m2);
}
{
  // a busy-hours pill nobody has put under the names (no pick) stays where it is, over them
  let s = null, r = null;
  try {
    s = sandbox2(BASEMAP);
    const add = (l) => s.map.addLayer(l, s.api.labelAnchor());
    ["forecast-casing", "forecast-layer"].forEach(id => add(LN(id, "routes-source")));
    ["busy-casing", "busy-core"].forEach(id => add(LN(id, "busy-route")));
    s.map.addLayer(T("busy-hours-at", "busy-hours-at"));
    ["road-load-casing", "road-load-line"].forEach(id => add(LN(id, "road-load-source")));
    s.api.restackOverLines();
    r = { pillOverNames: s.at("busy-hours-at") > s.at("road-label-simple"), order: inOrder(s, ["forecast-layer", "road-load-casing", "road-load-line", "busy-casing", "busy-core"], "road-label-simple") };
  } catch (e) { r = "threw " + e; }
  ok("C3 with no pick the busy-hours pill keeps its place over the names, and the shared sections still go under the busy road",
     r && r.pillOverNames === true && r.order === true, { r, ids: s && s.ids() });
}
{
  // Standard lists only our layers: no basemap name, so the order is kept just under the first text layer of ours above them
  let s = null, r = null;
  try {
    s = sandbox2([{ id: "land", type: "background" }]);
    const add = (l) => s.map.addLayer(l, s.api.labelAnchor());
    ["sel-glow", "sel-casing", "sel-core"].forEach(id => add(LN(id, "selected-route")));
    ["forecast-casing", "forecast-layer"].forEach(id => add(LN(id, "routes-source")));
    s.map.addLayer(T("road-load-labels", "road-load-labels"));
    s.map.addLayer({ id: "locations", type: "circle", source: "locations" });
    s.api.restackOverLines();
    r = { anchor: s.api.labelAnchor() === undefined, order: inOrder(s, ["forecast-layer", "sel-glow", "sel-casing", "sel-core"], "road-load-labels") };
  } catch (e) { r = "threw " + e; }
  ok("C4 on a style with no basemap names (Standard) the pick goes over the lines and under our own labels", r && r.anchor && r.order, { r, ids: s && s.ids() });
}
ok("⭐ C5 raiseMarks() (every forecast re-add) and selectRoute() both put the stack in the one order; selectRoute no longer moves the pick on its own",
   fnSrc("raiseMarks").includes("restackOverLines();") && fnSrc("selectRoute").includes("restackOverLines();")
   && !fnSrc("selectRoute").includes("['busy-casing', 'busy-core', 'sel-glow', 'sel-casing', 'sel-core', 'busy-hours-at'].forEach"));
ok("C6 OVER_LINES lists the shared sections first and the traffic limits last, as the comment says",
   !!olm && /'road-load-casing', 'road-load-line', 'diversion-edge', 'busy-casing', 'busy-core',\s+'sel-glow', 'sel-casing', 'sel-core', 'abnormal-public-casing', 'abnormal-public-lines',\s+'traffic-limit-fill', 'traffic-limit-band', 'traffic-limit-edge', 'traffic-limit-badge'\]/.test(olm[0])
   && html.includes("A NEW layer that must draw over the\n    // month's lines joins OVER_LINES here"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
