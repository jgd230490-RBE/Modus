/* map_switch_leftovers.js — 26 Nov 2026, claude/map-switch-leftovers (two faults found in passing by the label-anchor fix,
 * claude/map-label-anchor, and confirmed in Google Chrome on a local copy).
 * (a) After a basemap switch with a route picked, the other routes were no longer dimmed: setRouteDim() ran (from the
 *     style.load re-pick) before the legs were made again, and applySolidColors() set the legs back to full strength
 *     500 ms later. reapplyRouteDim() now runs after the legs are re-added and at the end of applySolidColors().
 * (b) Click / mouseenter / mouseleave handlers on map layers piled up at every style.load (24 / 23 / 23 at load, 35 / 37 /
 *     37 after one switch, 79 / 93 / 93 after five; one click on an abnormal load opened its popup six times):
 *     setupHoverEvents(), the abnormal loads, the traffic limits and others register again from code that style.load
 *     runs again. The page's map.on now keeps ONE handler for a layer, an event and a piece of code: the same code
 *     registered again replaces the first.
 * The real wrapper and reapplyRouteDim() are run against stand-ins; no browser (the real readings and pictures are in
 * notes\route-lines-plan-1126\check\leftovers\). On 245ed4a (the tip of claude/map-label-anchor) 10 of the 12 fail; A5 and
 * A6 hold there too (they guard what must NOT change: other handlers pass through, map.on still returns the map).
 */
const fs = require("fs");
const path = require("path");
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
  const j = html.indexOf("\n    }\n", i);
  return html.slice(i, j + 6);
}
const W0 = html.indexOf("    // 26 Nov 2026 (claude/map-switch-leftovers): ONE handler a layer");
const W1 = html.indexOf("    // (end of the layer-handler rule)", W0);
const wrapperSrc = W0 >= 0 && W1 > W0 ? html.slice(W0, W1) : "";

// a stand-in map with Mapbox's on / off: a layer handler is { type, layers, fn }; a map-level one has no layers
function stubMap() {
  const ls = [];
  const m = {
    ls,
    on(type, a, b) { if (typeof a === "function") ls.push({ type, layers: null, fn: a }); else ls.push({ type, layers: [].concat(a).join("+"), fn: b }); return m; },
    off(type, a, b) { const layers = typeof a === "function" ? null : [].concat(a).join("+"), fn = typeof a === "function" ? a : b;
      const i = ls.findIndex(x => x.type === type && x.layers === layers && x.fn === fn); if (i >= 0) ls.splice(i, 1); return m; },
    fire(type, layer) { ls.filter(x => x.type === type && (x.layers === null || x.layers.split("+").includes(layer))).forEach(x => x.fn({ layer })); },
  };
  return m;
}
function sandbox() {
  const map = stubMap();
  new Function("map", wrapperSrc)(map);
  const n = (type, layers) => map.ls.filter(x => x.type === type && (layers === undefined || x.layers === layers)).length;
  return { map, n };
}

console.log("A. One handler a layer, an event and a piece of code (the page's map.on)");
{
  let r = null;
  try {
    const s = sandbox();
    // a setup that style.load runs again: three layers, three events, as setupHoverEvents() does
    const setup = () => {
      ["inbound-lines", "outbound-lines", "zone-fill"].forEach(l => {
        s.map.on("mouseenter", l, () => { /* cursor */ });
        s.map.on("mouseleave", l, () => { /* cursor */ });
        s.map.on("click", l, (e) => { /* popup */ });
      });
    };
    setup(); const atLoad = s.map.ls.length;
    setup(); const after1 = s.map.ls.length;
    for (let i = 0; i < 4; i++) setup(); const after5 = s.map.ls.length;
    r = { atLoad, after1, after5 };
  } catch (e) { r = "threw " + e; }
  ok("⭐ A1 a setup run again at every style.load keeps its count: at load, after 1 and after 5 switches the same (9)",
     r && r.atLoad === 9 && r.after1 === 9 && r.after5 === 9, r);
}
{
  let r = null;
  try {
    const s = sandbox(); let opened = 0;
    const wire = () => s.map.on("click", "abnormal-public-lines", e => { opened++; });
    wire(); wire(); wire(); wire(); wire(); wire();
    s.map.fire("click", "abnormal-public-lines");
    r = { opened, n: s.n("click", "abnormal-public-lines") };
  } catch (e) { r = "threw " + e; }
  ok("⭐ A2 an abnormal load's click wired six times opens its popup ONCE", r && r.opened === 1 && r.n === 1, r);
}
{
  let r = null;
  try {
    const s = sandbox(); const seen = [];
    [1, 2, 3].forEach(month => s.map.on("click", "traffic-limit-band", e => { seen.push(month); }));
    s.map.fire("click", "traffic-limit-band");
    r = seen;
  } catch (e) { r = "threw " + e; }
  ok("A3 the NEWEST registration is the one kept (it holds the state of the last style.load)", Array.isArray(r) && r.length === 1 && r[0] === 3, r);
}
{
  let r = null;
  try {
    const s = sandbox();
    s.map.on("click", "locations", e => { /* one */ });
    s.map.on("click", "locations", e => { /* two: other code */ });
    s.map.on("click", "site-gates", e => { /* one */ });
    s.map.on("mouseenter", "locations", e => { /* one */ });
    s.map.on("click", ["limit-signs", "limit-dots"], e => { /* one */ });
    s.map.on("click", ["limit-signs", "limit-dots"], e => { /* one */ });
    r = { locClick: s.n("click", "locations"), gates: s.n("click", "site-gates"), enter: s.n("mouseenter", "locations"), arr: s.n("click", "limit-signs+limit-dots") };
  } catch (e) { r = "threw " + e; }
  ok("A4 other code on the same layer, another layer, another event: each kept; a list of layers counts as one key",
     r && r.locClick === 2 && r.gates === 1 && r.enter === 1 && r.arr === 1, r);
}
{
  let r = null;
  try {
    const s = sandbox();
    const f = function (e) {}; const b1 = f.bind({ a: 1 }), b2 = f.bind({ a: 2 });
    s.map.on("click", "locations", b1); s.map.on("click", "locations", b2);
    const g = e => {}; s.map.on("click", g); s.map.on("click", g); s.map.on("mousemove", e => {}); s.map.on("mousemove", e => {});
    r = { bound: s.n("click", "locations"), mapClick: s.map.ls.filter(x => x.type === "click" && x.layers === null).length, move: s.n("mousemove") };
  } catch (e) { r = "threw " + e; }
  ok("A5 a bound or native function (no code to compare) and every handler for the whole map (no layer) pass through untouched",
     r && r.bound === 2 && r.mapClick === 2 && r.move === 2, r);
}
{
  let r = null;
  try { const s = sandbox(); r = s.map.on("click", "x", e => {}) === s.map && s.map.on("load", () => {}) === s.map; } catch (e) { r = "threw " + e; }
  ok("A6 map.on still returns the map (chained calls keep working)", r === true, r);
}

console.log("B. The dim on the other routes after a switch");
{
  let r = null;
  try {
    const calls = [];
    const f = new Function("selectedRouteId", "setRouteDim", fnSrc("reapplyRouteDim") + "\nreturn reapplyRouteDim;");
    f("R050", id => calls.push(id))(); f(null, id => calls.push("none:" + id))();
    r = calls;
  } catch (e) { r = "threw " + e; }
  ok("⭐ B1 reapplyRouteDim() dims the others again while a route is picked, and does nothing with none picked",
     Array.isArray(r) && r.length === 1 && r[0] === "R050", r);
}
{
  const sc = (html.match(/const applySolidColors = \(\) => \{[\s\S]*?\n                \};/) || [""])[0];
  ok("⭐ B2 applySolidColors() (500 ms after every style.load, the last to write the legs' strength) puts the dim back after its reset",
     /map\.setPaintProperty\('outbound-lines', 'line-opacity', 1\.0\);\n\s+reapplyRouteDim\(\);/.test(sc), sc.slice(0, 200));
  ok("⭐ B3 the style.load handler puts the dim back once the legs are made again (right after applyFilters, before the hover set-up)",
     html.includes("        applyFilters();\n        reapplyRouteDim();") && /reapplyRouteDim\(\);[^\n]*\n        setupHoverEvents\(\);/.test(html));
}

console.log("C. Source checks");
ok("C1 the wrapper sits after the style gate (styleReady) and keeps the raw on / off it wraps",
   wrapperSrc.includes("const _onRaw = map.on.bind(map), _offRaw = map.off.bind(map);")
   && html.indexOf("function styleReady() { return STYLE_READY.now; }") < W0 && W0 > 0);
ok("C2 nothing else on the page replaces map.on", (html.match(/map\.on = function/g) || []).length === 1);
ok("C3 the rule is written for the next place that registers on a layer",
   wrapperSrc.includes("A new place that\n    // registers on a layer needs nothing extra."));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
