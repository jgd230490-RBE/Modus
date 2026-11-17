/* ui_fix_route_option_labels.js — 17 Nov 2026, branch claude/route-option-labels (John's "Yes, as recommended" to Q1 to
 * Q8 of the mockup notes\route-option-labels-mockup-1117; Idea 1 of the 17 Nov frontier check, F1 and F2).
 * While a route is open on Data -> Routes, each stored line of the card's lorry carries one short label on the page's own
 * map, written by the best-option rule (route.lines; test_route_option_labels.py is the rule's side). A label is a real
 * button; a click on a label or its line picks that option (the halo, the label's edge, the card's rows and its tab); a
 * click on another route's line opens its panel and leaves the page at the map; the card gains a tab an option; a limit
 * that rules an option out is marked on its line, solid and dark, with the limit sign the map already draws.
 *
 * Source checks, the placing rules as pure functions, then the Routes page mounted in a real DOM (jsdom) over a
 * stand-in map that projects, records and answers clicks.
 * Not covered here: where a label sits on a real map in pixels, the look in either look, a real server's answers, the
 * real limits read, a tablet's touch. Those are the session note's Chrome check (notes\session-1117-route-option-labels.md).
 *
 * Its own file. Every check marked ⭐ fails on the files before this branch. To see that:
 *   node backend/tests/ui_fix_route_option_labels.js <folder holding main's frontend/index.html as frontend/index.html>
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_route_option_labels.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 500) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, "..", "..");
const read = (...p) => { try { return fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n"); } catch (e) { return ""; } };
const html = read("frontend", "index.html");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

// ---------------- source checks ----------------
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };
const between = (a, b) => { const i = html.indexOf(a); const j = i < 0 ? -1 : html.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : html.slice(i, j); };
const bo = fnSrc("BestOption"), ra = fnSrc("RouteAnalysis");
const block = between("// ---- 17 Nov 2026 (route option labels) ----", "// 8 Nov 2026 (task 2.1-5): the five layers.");
const layer = between('<div className="ol-layer"', "</div>)}");
const css = between("/* 17 Nov 2026 (route option labels): the labels on the Routes map.", "\n  .bo-grp");

ok("⭐ SRC: a label is a real button named by its own words, both halves the rule's (route.lines), with its picked state",
   layer.includes('<button key={L.k} type="button" data-ol-label={L.ln.state}') && layer.includes("<b>{L.ln.name}</b> · {L.ln.words}")
   && layer.includes('aria-pressed={olPicked(L.ln) ? "true" : "false"}') && !/aria-label|title=/.test(layer));
ok("⭐ SRC: the page works no label out: the labels' code reads no time, count or head of the rule's answer, only its lines",
   block.length > 500 && !/cycle_min|drive_min|counts|head_words|heads\b|trips|Math\.round\([^)]*min/.test(block) && block.includes("(olBest.lines || []).map((ln, k) =>"));
ok("⭐ SRC: the labels come after the map's own box in the page (Tab reaches them after its buttons), the line in use first as the rule lists it",
   html.indexOf('<div className="ol-layer"') > html.indexOf("<RouteMapBox low=") && html.indexOf('<div className="ol-layer"') < html.indexOf("{full && onRoutes && !drawing && <>"));
ok("⭐ SRC: labels only for the route whose panel is open, once its card has the answer, on the lines of the lorry the card speaks for",
   block.includes('const olRoute = subTab === "routes" && !drawing && selected && (full || openRow === selected) ? selected : null;')
   && block.includes("const olOn = !!(olBest && selGeoms && olProf === olBest.lorry);") && html.includes("{olOn && olLabels.length > 0 && ("));
ok("⭐ SRC: one selection: a label, a line and a tab all move the map's focus, and the card's picked option is read from it",
   block.includes("const olPick = (ln) => { if(olBest) focusGeom(olBest.lorry, ln.alt != null ? ln.alt : ln.return_alt, showLegRef.current, ln.return_alt); };")
   && ra.includes("const pick = active && bestR && active.profile === bestR.lorry && Number(active.alt_index) !== useAlt ? Number(active.alt_index) : null;")
   && ra.includes("pick={pick} onPick={onFocus} />"));
ok("⭐ SRC: the card can show any option: tabs (the app's one tab) where a route has two or more others, the names the rule's",
   bo.includes("const tabs = !allOut && (r.options || []).length > 1 && onPick ? r.options : null;")
   && bo.includes('<div className="ws-tabs bo-tabs" role="tablist" aria-label="Option shown" data-bo-tabs="1" onKeyDown={tabKey}>')
   && bo.includes('role="tab" className="ws-tab" data-bo-tab={x.alt}') && bo.includes("{boLineName(r, x)}</button>))}"));
ok("⭐ SRC: Make primary stays on the SUGGESTED option alone (the card can now show another), never while a diversion is in use",
   bo.includes('const canPromote = r.answer === "Suggested" && o && o.chosen && onPromote && !div;'));
ok("⭐ SRC: the map's click: a limit sign and the open route's own lines first, then a ticked layer's thing, then another route's line, which opens its panel",
   TRY(() => { const a = html.indexOf("if(cbRef.current.olClick && cbRef.current.olClick(e)) return;"), b = html.indexOf("if(cbRef.current.layerPopup && cbRef.current.layerPopup(e)) return;"),
                     c = html.indexOf("(cbRef.current.routeClick || cbRef.current.selectRoute || (()=>{}))(hitRoute[0].properties.route_id);"); return a > 0 && a < b && b < c; })
   && html.includes('const layers = ["route-line", "route-failed", "ol-use-line"].filter(l => m.getLayer(l));'));
ok("⭐ SRC: Q6: a route opened from the map leaves the page at the map (no move, no focus taken); ▶ in the list still moves it",
   html.includes("if(!full && openRow !== id){ roQuiet.current = true; setOpenRow(id); }")
   && html.includes("if(roQuiet.current){ roQuiet.current = false; return; }") && html.includes('el.scrollIntoView({ block: "start"'));
ok("⭐ SRC: the map rules hold: the marked stretch is SOLID and dark (no dash, not the limit layer's red), the labels carry no red",
   TRY(() => { const mk = between('m.addLayer({ id: "ol-mark"', "});"); return mk.includes('"line-color": olMarkInk') && !/dasharray|RL_LIMIT_RED|#DC2626|#C8102E/.test(mk); })
   && html.includes('const OL_MARK = "#334155", OL_MARK_DARK = "#E2E8F0";') && css.length > 200 && !/#DC2626|#C8102E|var\(--red\)|var\(--bad/.test(css));
ok("⭐ SRC: the sign is the one the Lorry limits layer draws (rlSignImage), on its own layer, shown without ticking that box",
   html.includes('m.addLayer({ id: "ol-sign", type: "symbol", source: "olsigns"')
   && (html.match(/"icon-image": \["concat", "rl-sign-", \["get", "sign"\]\]/g) || []).length === 2 && html.includes("rlSignImage(t), { pixelRatio: 2 }")
   && block.includes('rlRead("limits").then('));
ok("⭐ SRC: the open route's line in use is drawn in the leg colours (a dated diversion is not option 0), and the route layers give that route up meanwhile",
   html.includes('m.addLayer({ id: "ol-use-line", type: "line", source: "oluse"') && between('id: "ol-use-line"', "});").includes('"line-color": LEG_COLOR_EXPR, "line-width": 3, "line-offset": LEG_OFFSET')
   && html.includes('const f = hide ? ["all", base, ["!=", ["get", "route_id"], hide]] : base;'));
ok("⭐ SRC: the label's look: 12 px (the app's floor), the app's surface and ink, a 44 px tap area on a tablet or a touch screen, a Dark edge",
   css.includes("font-size:12px") && css.includes("background:var(--surface);color:var(--ink)") && css.includes(".ol-lab.ol-out{color:var(--muted);}")
   && css.includes("@media (max-width:1024px), (pointer:coarse){.ol-lab::after{") && css.includes('html[data-theme="dark"] .ol-lab[aria-pressed="true"]{border-color:#7AA2FF'));
ok("⭐ SRC: rule 1: opening a route fits the map to all its options once; rule 4: the labels are placed again as each move ends",
   block.includes("olFitFor.current = key;") && block.includes("m.fitBounds(boundsOf(pts), { padding: { top: 70, bottom: 50, left: 70, right: 70 }, maxZoom: 13")
   && html.includes('m.on("moveend", () => { if(cbRef.current.olPlace) cbRef.current.olPlace(); });'));
ok("SRC: no new map picture, no new read on a page view: the labels use the card's answer and the lines already read; the limits read is the Layers box's own",
   !/static\/|styles\/v1/.test(block) && (block.match(/fetch\(/g) || []).length === 0);
ok("SRC: the public map is not touched (no label code in map/index.html)", !/ol-lab|olPlace|route\.lines/.test(read("map", "index.html")));

// ---------------- the guides ----------------
const ug = read("frontend", "help", "index.html"), tg = read("frontend", "help", "technical", "index.html");
ok("⭐ GUIDE: the user guide says what a label is, what a click does, the tabs and the marked stretch",
   /label on (its|each) line/i.test(ug) && ug.includes("3.5 min quicker") && /similar/.test(ug) && /ruled out/.test(ug) && /tab/.test(ug.split('id="ug-best-option"')[1] || ""));
ok("⭐ GUIDE: the technical guide names where the words come from (route_best.line_labels) and the placing rules",
   tg.includes("line_labels") && tg.includes("olPlace"));

// ---------------- the app in a DOM, over a stand-in map ----------------
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
const ctlBox = w.document.createElement("div"); w.document.body.appendChild(ctlBox);
// the stand-in map: a 700 x 430 px box; a point's place is (lng, lat) x 1000, then the view's pan and zoom
const MAP = { W: 700, H: 430, ox: 0, oy: 0, z: 1, on: [], hits: () => [], fits: [], filt: {}, src: {}, lay: {}, pops: [], box: null };
const fire = (ev, e) => MAP.on.filter(h => h.ev === ev && !h.layer).forEach(h => h.fn(e));
w.mapboxgl = { accessToken: "", NavigationControl: function(){}, ScaleControl: function(){}, AttributionControl: function(){},
  LngLatBounds: function(){ return { pts: [], extend(c){ this.pts.push(c); return this; } }; },
  Popup: function(){ const p = { html: "", at: null, setLngLat: (c) => { p.at = c; return p; }, setHTML: (h) => { p.html = h; return p; }, setDOMContent: () => p, addTo: () => { MAP.pops.push(p); return p; }, remove(){ p.gone = true; }, on: () => p }; return p; },
  Marker: function(){ const m = { setLngLat: () => m, addTo: () => m, remove(){}, getElement: () => w.document.createElement("div"), on: () => m, setDraggable: () => m }; return m; },
  Map: function(o){
    MAP.box = o && o.container;
    const m = new Proxy({}, { get: (t, k) => {
      if (k === "on") return (ev, a, b) => { const fn = typeof a === "function" ? a : b; MAP.on.push({ ev, layer: typeof a === "string" ? a : null, fn }); if (ev === "load") setTimeout(() => fn(), 0); return m; };
      if (k === "addControl") return (c) => { if (c && c.onAdd){ const n = c.onAdd(m); if (n) ctlBox.appendChild(n); } return m; };
      if (k === "getContainer") return () => MAP.box;
      if (k === "getCanvas" || k === "getCanvasContainer") return () => ({ style: {}, addEventListener(){}, removeEventListener(){} });
      if (k === "project") return (c) => ({ x: (c[0] * 1000 - MAP.ox) * MAP.z, y: (c[1] * 1000 - MAP.oy) * MAP.z });
      if (k === "unproject") return (p) => ({ lng: (p[0] / MAP.z + MAP.ox) / 1000, lat: (p[1] / MAP.z + MAP.oy) / 1000 });
      if (k === "fitBounds") return (b, opt) => { MAP.fits.push({ b, opt }); return m; };
      if (k === "setFilter") return (l, f) => { MAP.filt[l] = f; return m; };
      if (k === "getZoom") return () => 10;
      if (k === "getCenter") return () => ({ lng: 0, lat: 0 });
      if (k === "getBounds") return () => ({ getWest: () => 0, getEast: () => 1, getSouth: () => 0, getNorth: () => 1 });
      if (k === "addLayer") return (l) => { MAP.lay[l.id] = l; return m; };
      if (k === "getLayer") return (id) => MAP.lay[id];
      if (k === "addSource") return (id, s) => { MAP.src[id] = { ...s, setData(d){ this.data = d; } }; return m; };
      if (k === "getSource") return (id) => MAP.src[id];
      if (k === "hasImage") return () => false;
      if (k === "getStyle") return () => ({ layers: [] });
      if (k === "queryRenderedFeatures") return (g, q) => MAP.hits((q && q.layers) || []);
      if (k === "isStyleLoaded" || k === "loaded") return () => true;
      if (k === "then") return undefined;
      return () => m;
    } });
    return m;
  } };
w.eval(CLOCK.shiftSource());
let loaded = true;
try { w.eval(js + "\nwindow.__TENANT = TENANT; window.__ACCESS = ACCESS;"); } catch (e) { loaded = false; console.log("app script failed: " + e.message); }
ok("the app's script runs in the DOM", loaded);

// ---------------- the placing rules, as the pure functions the page calls ----------------
const HAVE = typeof w.olPlace === "function" && typeof w.olMarks === "function";
ok("⭐ PLACE: the placing and the marks are functions of their own (olPlace, olSamples, olMarks, olThin)", HAVE && typeof w.olSamples === "function" && typeof w.olThin === "function");
const USE_PX = [[100, 100], [250, 100], [600, 120], [600, 330]], ALT1_PX = [[100, 100], [250, 100], [400, 250], [600, 330]], ALT2_PX = [[100, 100], [100, 380], [600, 380], [600, 330]];
const item = (k, pts, wd) => ({ k, pts, w: wd || 120, h: 26 });
const boxHit = (a, b, wa, wb) => Math.abs(a.x - b.x) < ((wa || 120) + (wb || 120)) / 2 && Math.abs(a.y - b.y) < 26;
const distTo = (p, pts) => { let d = 1e9; for (let i = 1; i < pts.length; i++){ const a = pts[i - 1], b = pts[i], L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2;
  const t = L2 ? Math.max(0, Math.min(1, ((p.x - a[0]) * (b[0] - a[0]) + (p.y - a[1]) * (b[1] - a[1])) / L2)) : 0; d = Math.min(d, Math.hypot(p.x - (a[0] + (b[0] - a[0]) * t), p.y - (a[1] + (b[1] - a[1]) * t))); } return d; };
if (HAVE) {
  const P1 = w.olPlace([item(0, USE_PX), item(1, ALT1_PX), item(2, ALT2_PX)], 700, 430, []);
  ok("⭐ PLACE rule 2: three lines in view: each label sits ON its own line, on a part no other line shares, none overlapping, none stacked",
     TRY(() => [0, 1, 2].every(k => P1[k] && !P1[k].stacked) && distTo(P1[0], USE_PX) < 2 && distTo(P1[1], ALT1_PX) < 2 && distTo(P1[2], ALT2_PX) < 2
       && distTo(P1[0], ALT1_PX) >= 9 && distTo(P1[0], ALT2_PX) >= 9 && distTo(P1[1], USE_PX) >= 9 && distTo(P1[2], USE_PX) >= 9
       && !boxHit(P1[0], P1[1]) && !boxHit(P1[0], P1[2]) && !boxHit(P1[1], P1[2])), JSON.stringify(P1));
  ok("⭐ PLACE rule 2: every label is whole inside the map and clear of its line's two ends",
     TRY(() => [0, 1, 2].every(k => P1[k].x - 60 >= 4 && P1[k].x + 60 <= 696 && P1[k].y - 13 >= 4 && P1[k].y + 13 <= 426
       && Math.hypot(P1[k].x - 100, P1[k].y - 100) > 40 && Math.hypot(P1[k].x - 600, P1[k].y - 330) > 40)), JSON.stringify(P1));
  ok("PLACE rule 2: among its unshared places a label takes the one nearest the middle of the map",
     TRY(() => { const s = w.olSamples(ALT2_PX, 14).filter(q => q.t >= 0.12 && q.t <= 0.88 && q.x - 60 >= 4 && q.x + 60 <= 696 && q.y + 13 <= 426 && distTo(q, USE_PX) >= 10 && distTo(q, ALT1_PX) >= 10);
                 const best = Math.min(...s.map(q => Math.hypot(q.x - 350, q.y - 215))); return Math.abs(Math.hypot(P1[2].x - 350, P1[2].y - 215) - best) < 1.5; }));
  // only the stretch the two share is in view (zoomed in on it): they stack, the line in use first
  const zoom = (pts) => pts.map(([x, y]) => [(x - 90) * 5, (y - 57) * 5]);
  const P2 = w.olPlace([item(0, zoom(USE_PX)), item(1, zoom(ALT1_PX))], 700, 430, []);
  ok("⭐ PLACE rule 3: only their shared stretch in view: the two labels stack, the line in use first, the second straight under it",
     TRY(() => P2[0] && P2[1] && !P2[0].stacked && P2[1].stacked && P2[1].x === P2[0].x && P2[1].y - P2[0].y === 28), JSON.stringify(P2));
  const P3 = w.olPlace([item(0, USE_PX), item(1, ALT1_PX), item(2, ALT2_PX.map(([x, y]) => [x, y + 600]))], 700, 430, []);
  ok("⭐ PLACE rule 4: a line wholly out of view has no label (nothing is pinned to the map's edge); the others keep theirs",
     TRY(() => P3[0] && P3[1] && P3[2] === undefined), JSON.stringify(P3));
  const KEEP = [{ x0: 0, y0: 0, x1: 700, y1: 215 }];
  const P4 = w.olPlace([item(0, USE_PX)], 700, 430, KEEP);
  ok("⭐ PLACE: no label covers the map's own buttons (a kept-out box): the label moves along its line to clear it",
     TRY(() => P4[0] && P4[0].y - 13 >= 215 && distTo(P4[0], USE_PX) < 2), JSON.stringify(P4));
  ok("PLACE: a line of one point, or of no length, gets no label and breaks nothing",
     TRY(() => Object.keys(w.olPlace([item(0, [[10, 10]]), item(1, [[50, 50], [50, 50]])], 700, 430, [])).length === 0));
}
// the limits feed as the Lorry limits read gives it (ids are source:ext_id:kind), and the rule's added limits
const LIM = (id, sign, name, anchor, pt) => ({ type: "Feature", geometry: pt ? { type: "Point", coordinates: anchor } : { type: "LineString", coordinates: [[anchor[0] - 0.005, anchor[1]], [anchor[0] + 0.005, anchor[1]]] },
  properties: { id, kind: id.split(":")[2], icon_text: sign, headline: name, anchor } });
const LIMITS = { type: "FeatureCollection", features: [
  LIM("osm:1:weight", "7.5t", "Weight limit 7.5 t, Syston Road", [0.30, 0.20]), LIM("osm:2:weight", "7.5t", "Weight limit 7.5 t, Syston Road", [0.32, 0.20]),
  LIM("osm:3:weight", "7.5t", "Weight limit 7.5 t, Syston Road", [0.34, 0.20]), LIM("osm:4:weight", "7.5t", "Weight limit 7.5 t", [0.50, 0.30]),
  LIM("here:9:height", "4.2m", "Height limit 4.2 m, Mill Lane", [0.20, 0.38], true), LIM("osm:77:weight", "18t", "Weight limit 18 t, Far Road", [0.9, 0.9]) ] };
const ADD = (source, ext, kind, short, road) => ({ leg: "loaded", source, ext_id: ext, kind, short, road, except_for_access: false, words: short });
const ADDED = [ADD("osm", "1", "weight", "7.5 t limit", "Syston Road"), ADD("osm", "2", "weight", "7.5 t limit", "Syston Road"), ADD("osm", "3", "weight", "7.5 t limit", "Syston Road"),
               ADD("osm", "4", "weight", "7.5 t limit", null), ADD("here", "9", "height", "4.2 m height limit", "Mill Lane"), ADD("osm", "404", "weight", "7.5 t limit", "Gone Road")];
if (HAVE) {
  const R = { lines: [{ alt: 1, name: "Alt 1", state: "ruled_out" }, { alt: 0, name: "Main route", state: "ruled_out" }] };
  const mk = w.olMarks([{ alt: 1, label: "Alt 1", added_limits: ADDED }, { alt: 0, label: "The main route", added_limits: [ADDED[0]] }], LIMITS, R);
  ok("⭐ MARKS: every stretch the options add is marked once with the limit's own stored line; a point limit has a sign and no stretch; a limit not in the read is left out",
     TRY(() => mk.marks.length === 4 && mk.marks.map(f => f.properties.id).sort().join() === "osm:1:weight,osm:2:weight,osm:3:weight,osm:4:weight"
       && mk.marks.every(f => f.geometry.type === "LineString")), JSON.stringify(mk.marks.map(f => f.properties.id)));
  ok("⭐ MARKS: ONE sign a road (three stretches of Syston Road: one sign, at the middle stretch), a sign for the unnamed stretch and for the point",
     TRY(() => mk.signs.length === 3 && mk.signs.filter(s => s.properties.id === "osm:2:weight").length === 1 && mk.signs.some(s => s.properties.id === "osm:4:weight")
       && mk.signs.some(s => s.properties.id === "here:9:height" && s.properties.sign === "4.2m")
       && mk.signs.every(s => s.geometry.type === "Point")), JSON.stringify(mk.signs.map(s => s.properties)));
  ok("⭐ MARKS R1: the sign's box says the limit's own name and which options meet it, in the rule's names: 'Alt 1 and Main route meet it.' / 'Alt 1 meets it.'",
     TRY(() => { const sy = mk.signs.find(s => s.properties.id === "osm:2:weight").properties, un = mk.signs.find(s => s.properties.id === "osm:4:weight").properties;
                 return sy.headline === "Weight limit 7.5 t, Syston Road" && sy.who === "Alt 1 and Main route meet it." && un.who === "Alt 1 meets it." && sy.sign === "7.5t"; }),
     JSON.stringify(mk.signs.map(s => s.properties.who)));
  ok("⭐ MARKS: signs that would touch at this zoom become one; apart, each shows",
     TRY(() => w.olThin([1, 2, 3], [[100, 100], [110, 104], [300, 100]], 26).join() === "1,3" && w.olThin([1, 2, 3], [[100, 100], [140, 100], [300, 100]], 26).length === 3));
}

// ---------------- the Routes page ----------------
const respond = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 0)); });
const P = "Artic Tipper (44t)", RIG = "Rigid 8-wheeler (32t)";
const META = { routes: [], materials: ["Aggregate"], vehicles: [P, RIG], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } }, mapbox_token: "",
  vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [], ipts: [],
  tenant: { name: "Wolds Link", team_label: "Team", currency: "GBP", currency_symbol: "£", country: "GB", distance_unit: "mi", demo_notice: "Fictional scheme" } };
const LOCS = { type: "FeatureCollection", features: [["L001", "Tilton Viaduct site", 0.1, 0.1], ["L003", "Wolds Link Inert Landfill", 0.6, 0.33]]
  .map(([id, name, lon, lat]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id, name, role: "origin", loc_type: "Quarry", supplies: [], receives: [] } })) };
const leg = (km, hr, alt) => ({ alt_index: alt || 0, baked: true, distance_km: km, duration_hr: hr, error: null, haul_zones: [], haul_recorded: true });
const ST = (id) => ({ id, origin: "Tilton Viaduct site", dest: "Wolds Link Inert Landfill", origin_id: "L001", dest_id: "L003", ipt: null, haul_roads: [], gate_blockers: [],
  profiles: { [P]: { baked: true, distance_km: 40, duration_hr: 0.75, legs: { loaded: [leg(40, 0.75), leg(44, 0.8, 1), leg(46, 0.9, 2)], return: [leg(42, 0.5)] }, return_baked: true, alt_count: 3 } } });
const STATUS = [ST("R001"), ST("R002"), ST("R003")];
const ROW = (alt, prof) => ({ profile: prof || P, alt_index: alt, loaded_km: 40 + alt, return_km: 42, return_estimated: false, loaded_hr: 0.75, return_hr: 0.5,
  load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 1.7, haul_speed_applied: false,
  trips_per_day: 5, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 56, lorry_day: { limited_by: "shift", trips_without_rules: 5, words: "5 a day", break_minutes: 45 } });
const DATA = { rows: [ROW(0), ROW(1), ROW(2), ROW(0, RIG)], planning: { shift_hours_per_day: 10, working_days_per_month: 22, shift_note: "" } };
const ll = (px) => px.map(([x, y]) => [x / 1000, y / 1000]);
const GEO = (rid) => ({ type: "FeatureCollection", features: [[0, USE_PX], [1, ALT1_PX], [2, ALT2_PX]].flatMap(([alt, px]) => ["loaded", "return"].map(lg => (
  { type: "Feature", properties: { route_id: rid, vehicle_profile: P, leg: lg, alt_index: alt }, geometry: { type: "LineString", coordinates: lg === "loaded" ? ll(px) : ll(px).slice().reverse() } })))
  .concat([{ type: "Feature", properties: { route_id: rid, vehicle_profile: RIG, leg: "loaded", alt_index: 0 }, geometry: { type: "LineString", coordinates: ll(USE_PX) } }]) });
const OPT = (alt, label, o) => Object.assign({ alt, label, return_alt: alt, ruled_out: [], added_limits: [], searched: true, heads: {}, parts: {}, n5: false,
  counts: { km: 64.71, drive_min: 66.5, cycle_min: 100.5, trips: 5, co2_kg: 56, busy_min: {}, collisions: 39, goods: 1, left_turns: 9, cycle_meets: 4, cycle_beside_km: 0.17, places: 2 },
  pct: { left_turns: -10, cycle_meets: -33, cycle_beside_km: null, places: -71 }, head_words: { people: "fewer", time: "quicker", busy: "not counted", carbon: "same" },
  part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "fewer" },
  sentences: [`${label} had 39 collisions on it against 39 on the route in use, 2021–2025.`, `${label} had 1 collision involving a goods vehicle over 3.5 t on it against 4 on the route in use, 2021–2025.`] }, o || {});
const USE0 = { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } };
const CU = { km: 66.65, drive_min: 70, cycle_min: 104, trips: 5, co2_kg: 57.7, collisions: 39, goods: 4, left_turns: 10, cycle_meets: 6, cycle_beside_km: 0.24, places: 7, busy_min: {} };
const BEST1 = { day: "2026-11-17", checks: {}, route: { route: "R001", answer: "Suggested", option: "Alt 1", alt: 1, why: "3.5 min quicker a round trip, with 2 fewer cycle routes met.",
  trade: null, held_back: null, lorry: P, lorry_basis: "approved loads", other_lorries: [RIG], in_use: USE0, counts_in_use: CU,
  checks: { limits_held: true, community_all_options: true, collision_history: "current" },
  options: [OPT(1, "Alt 1", { chosen: true }), OPT(2, "Alt 2", { head_words: { people: "mixed", time: "slower", busy: "not counted", carbon: "same" }, counts: Object.assign({}, OPT(2, "x").counts, { cycle_min: 106.8, co2_kg: 58.5 }) })],
  lines: [{ alt: 0, return_alt: 0, name: "In use", words: "104 min", state: "in_use" }, { alt: 1, return_alt: 1, name: "Alt 1", words: "3.5 min quicker", state: "quicker" },
          { alt: 2, return_alt: 2, name: "Alt 2", words: "3 min longer", state: "longer" }] } };
// R002: Alt 2 is in use as a dated diversion; the main route crosses the closed area, Alt 1 adds limits on Syston Road
const DIV = { alt: 2, label: "Alt 2", why: "diversion", status: "in_use", until: "2027-12-17" };
const BEST2 = { day: "2026-11-17", checks: {}, route: { route: "R002", answer: "Keep the route in use", option: null, alt: null, why: "Every other option is ruled out: …",
  trade: null, held_back: null, lorry: P, lorry_basis: "approved loads", other_lorries: [], in_use: { loaded: DIV, return: DIV }, counts_in_use: Object.assign({}, CU, { cycle_min: 147.7 }),
  checks: { limits_held: true, community_all_options: true, collision_history: "current" },
  options: [OPT(0, "The main route", { ruled_out: ["it crosses Tilton junction works, closed until 17 Dec 2027 (both legs)"] }),
            OPT(1, "Alt 1", { ruled_out: ["it adds 7.5 t limits on Syston Road and an unnamed road and a 4.2 m height limit on Mill Lane"], added_limits: ADDED })],
  lines: [{ alt: 2, return_alt: 2, name: "In use", words: "147.7 min", state: "in_use" }, { alt: 0, return_alt: 0, name: "Main route", words: "ruled out", state: "ruled_out" },
          { alt: 1, return_alt: 1, name: "Alt 1", words: "ruled out", state: "ruled_out" }] } };
const seen = [];
w.fetch = (url) => { const u = String(url); seen.push(u);
  if (/\/locations\/geojson$/.test(u)) return respond(LOCS);
  if (/\/routes\/status$/.test(u)) return respond(STATUS);
  if (/\/routes\/summary$/.test(u)) return respond({ here_configured: true, routes: 3, locations: 2 });
  if (/\/zones$/.test(u)) return respond({ zones: [], haul_links: {} });
  if (/\/routes\/geojson\?/.test(u)) return respond({ type: "FeatureCollection", features: [] });
  if (/\/routes\/community-counts$/.test(u)) return respond({ fetched_at: "2026-11-16", near_m: {}, kinds: [], routes: {} });
  if (/\/routes\/diversions$/.test(u)) return respond({ periods: [], busy: [] });
  if (/\/api\/gates$/.test(u)) return respond({ gates: [] });
  if (/\/routes\/R00\d\/analysis$/.test(u)) return respond(DATA);
  if (/\/routes\/R001\/best-option$/.test(u)) return respond(BEST1);
  if (/\/routes\/R002\/best-option$/.test(u)) return respond(BEST2);
  if (/\/public\/limits$/.test(u)) return respond(LIMITS);
  if (/\/routes\/R00\d\/haul-roads$/.test(u)) return respond({ links: [], plan: {} });
  const g = u.match(/\/routes\/(R00\d)\/geometries$/); if (g) return respond(GEO(g[1]));
  return new Promise(() => {}); };          // R003's best option is never answered (still being worked out)

let desk = true; const mqOn = [];
const isDesk = (q) => /min-width: 1024px/.test(q);
w.matchMedia = (q) => ({ get matches(){ return isDesk(q) ? desk : false; }, media: q,
  addEventListener(t, f){ if (isDesk(q)) mqOn.push(f); }, removeEventListener(){}, addListener(f){ if (isDesk(q)) mqOn.push(f); }, removeListener(){} });
const doc = w.document, de = doc.documentElement; let fsEl = null;
Object.defineProperty(doc, "fullscreenElement", { configurable: true, get: () => fsEl });
de.requestFullscreen = () => { fsEl = de; return Promise.resolve(); };
doc.exitFullscreen = () => { fsEl = null; return Promise.resolve(); };
const rect = (o) => Object.assign({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0 }, o);
w.Element.prototype.getBoundingClientRect = function(){
  if (this === MAP.box) return rect({ width: MAP.W, height: MAP.H, right: MAP.W, bottom: MAP.H });
  if (this.hasAttribute && this.hasAttribute("data-route-map-box")) return rect({ left: 8, top: 8, right: 180, bottom: 80, width: 172, height: 72 });
  return rect({});
};
const moved = [];
w.Element.prototype.scrollIntoView = function(o){ moved.push([this, o || {}]); };
w.ResizeObserver = function(){ this.observe = () => {}; this.disconnect = () => {}; };

(async () => {
  if (!loaded || typeof w.DataManagement !== "function") { ok("the Routes page (DataManagement) is defined", false); return finish(); }
  w.__ACCESS.info = { role: "admin", label: "Admin", via: "login", can_approve: true, ipt: null, name: "Ada", email: "ada@example.org" };
  const el = doc.createElement("div"); doc.body.appendChild(el); const root = w.ReactDOM.createRoot(el);
  const settle = async () => { for (let i = 0; i < 12; i++) await tick(); };
  const press = async (b) => { await act(async () => { b.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await settle(); };
  const mapEv = async (ev, e) => { await act(async () => { fire(ev, e); }); await settle(); };
  const q = (s) => el.querySelector(s), qa = (s) => [...el.querySelectorAll(s)];
  const tri = (id) => q(`button[data-route-tri="${id}"]`);
  const labs = () => qa(".ol-layer button.ol-lab");
  const said = () => labs().map(b => b.textContent.replace(/\s+/g, " ").trim());
  const pressed = () => labs().filter(b => b.getAttribute("aria-pressed") === "true").map(b => b.textContent.replace(/\s+/g, " ").trim()).join("|");
  const lab = (t) => labs().find(b => b.textContent.replace(/\s+/g, " ").trim().startsWith(t));
  const at = (b) => ({ x: parseFloat(b.style.left), y: parseFloat(b.style.top) });
  const tabs = () => qa(".bo-card [role=tab]");
  const card = () => (q(".bo-card") || { textContent: "" }).textContent.replace(/\s+/g, " ");
  try {
    await act(async () => { root.render(w.React.createElement(w.DataManagement, { meta: META, who: "t", subTab: "routes", onSubTab(){} })); });
    await settle();
    Object.defineProperty(MAP.box, "clientWidth", { configurable: true, get: () => MAP.W });
    Object.defineProperty(MAP.box, "clientHeight", { configurable: true, get: () => MAP.H });
    ok("DOM: no route is open: no label on the map", labs().length === 0 && !q(".ol-layer"));

    // ---- open R001 with ▶ ----
    await press(tri("R001"));
    ok("⭐ DOM: a route's panel is open and its card has the answer: one label a stored line, the rule's words, the line in use first",
       said().join("|") === "In use · 104 min|Alt 1 · 3.5 min quicker|Alt 2 · 3 min longer", said().join("|"));
    ok("⭐ DOM: each label is a button named by its own words (no other name), carrying its state; the line in use is the picked one at first",
       labs().length === 3 && labs().every(b => b.tagName === "BUTTON" && b.type === "button" && !b.getAttribute("aria-label") && !b.title)
       && labs().map(b => b.getAttribute("data-ol-label")).join() === "in_use,quicker,longer" && pressed() === "In use · 104 min", pressed());
    ok("⭐ DOM: the labels sit in the map's card, after the map's own box of buttons",
       TRY(() => { const L = q(".ol-layer"), B = q("[data-route-map-box]"); return L.parentElement === B.parentElement && L.parentElement.contains(MAP.box) && !!(B.compareDocumentPosition(L) & w.Node.DOCUMENT_POSITION_FOLLOWING); }));
    {
      const p = labs().map(at);
      ok("⭐ DOM: each label is placed on its own line, inside the map, clear of the map's buttons, none overlapping",
         p.length === 3 && distTo(p[0], USE_PX) < 2 && distTo(p[1], ALT1_PX) < 2 && distTo(p[2], ALT2_PX) < 2
         && p.every(c => c.x > 60 && c.x < 640 && c.y > 13 && c.y < 417 && !(c.x - 90 < 184 && c.y - 13 < 84))
         && Math.abs(p[0].y - p[1].y) + Math.abs(p[0].x - p[1].x) > 60 && Math.abs(p[1].y - p[2].y) + Math.abs(p[1].x - p[2].x) > 60, JSON.stringify(p));
    }
    ok("⭐ DOM rule 1: opening the route fits the map to ALL its options (every point of the card's lorry's six lines), once",
       TRY(() => { const f = MAP.fits.filter(x => x.b && x.b.pts && x.b.pts.length === 24); return f.length === 1 && f[0].opt.maxZoom === 13 && f[0].opt.padding.top === 70; }),
       MAP.fits.map(x => x.b && x.b.pts && x.b.pts.length).join());
    ok("⭐ DOM: the line in use is drawn by its own layers (both legs of option 0 here) and the route layers give this route up",
       TRY(() => MAP.src.oluse.data.features.length === 2 && MAP.src.oluse.data.features.every(f => f.properties.alt_index === 0 && f.properties.vehicle_profile === P)
         && JSON.stringify(MAP.filt["route-line"]) === JSON.stringify(["all", ["!=", ["get", "failed"], true], ["!=", ["get", "route_id"], "R001"]])
         && JSON.stringify(MAP.filt["route-arrows"]) === JSON.stringify(MAP.filt["route-line"])), JSON.stringify(MAP.filt["route-line"]));
    ok("⭐ DOM: the card shows the option the rule names (Alt 1) with a tab an option, Alt 1's selected, and Make primary on it",
       tabs().map(t => t.textContent + ":" + t.getAttribute("aria-selected")).join() === "Alt 1:true,Alt 2:false" && /Alt 1 had 39 collisions/.test(card())
       && TRY(() => q("button[data-bo-promote]").textContent === "Make Alt 1 primary") && TRY(() => q("[role=tablist]").getAttribute("aria-label") === "Option shown"));
    ok("⭐ DOM R1: the tabs add the options' names only to the card (2 words an option), nothing else",
       TRY(() => q("[data-bo-tabs]").textContent === "Alt 1Alt 2"));

    // ---- a click on a label ----
    moved.length = 0;
    await press(lab("Alt 2"));
    ok("⭐ DOM: a click on 'Alt 2 · 3 min longer' picks Alt 2: its label is the pressed one, the card's tab and rows are Alt 2's, the headline answer stays",
       pressed() === "Alt 2 · 3 min longer" && tabs().map(t => t.getAttribute("aria-selected")).join() === "false,true" && /Alt 2 had 39 collisions/.test(card())
       && !/Alt 1 had 39 collisions/.test(card()) && TRY(() => q(".bo-ans b").textContent === "Alt 1") && /106\.8 min a round trip/.test(card()), card().slice(0, 300));
    ok("⭐ DOM: on another option's tab there is no Make primary (it is the suggested option's alone), and the map button names the option shown",
       !q("button[data-bo-promote]") && TRY(() => q("button[data-bo-show]").textContent === "Show Alt 2 on map"));
    ok("⭐ DOM: the pick did not move the page (no scroll to the panel or the map)", moved.length === 0, moved.length);
    await press(lab("In use"));
    ok("⭐ DOM: a click on the line in use's label: the card goes back to the option the rule names, Make primary with it",
       pressed() === "In use · 104 min" && tabs().map(t => t.getAttribute("aria-selected")).join() === "true,false" && !!q("button[data-bo-promote]"));

    // ---- a tab, and the arrow keys ----
    moved.length = 0;
    await press(tabs()[1]);
    ok("⭐ DOM: a click on the card's Alt 2 tab is the same pick: the map's label follows, and the page does not move",
       pressed() === "Alt 2 · 3 min longer" && tabs()[1].getAttribute("aria-selected") === "true" && moved.length === 0);
    ok("⭐ DOM: one tab stop in the tabs (the selected one); the arrow keys move between them",
       tabs().map(t => t.tabIndex).join() === "-1,0" && TRY(() => { tabs()[1].focus(); tabs()[1].dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
         const a = doc.activeElement === tabs()[0]; tabs()[0].dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })); return a && doc.activeElement === tabs()[1]; }));

    // ---- a click on an option's LINE ----
    MAP.hits = (layers) => layers.includes("alt-line") ? [{ properties: { route_id: "R001", vehicle_profile: P, leg: "return", alt_index: 1 }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 400, y: 250 }, lngLat: { lng: 0.4, lat: 0.25 } });
    ok("⭐ DOM: a click on Alt 1's line (either leg) picks Alt 1, as its label does", pressed() === "Alt 1 · 3.5 min quicker" && tabs()[0].getAttribute("aria-selected") === "true", pressed());
    MAP.hits = (layers) => layers.includes("ol-use-line") && !layers.includes("route-line") ? [{ properties: { route_id: "R001", vehicle_profile: P, leg: "loaded", alt_index: 0 }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 600, y: 200 }, lngLat: { lng: 0.6, lat: 0.2 } });
    ok("⭐ DOM: a click on the line in use picks it", pressed() === "In use · 104 min", pressed());

    // ---- the map moves ----
    MAP.hits = () => [];
    MAP.ox = 250; MAP.oy = 60; MAP.z = 2;
    await mapEv("moveend", {});
    ok("⭐ DOM rule 4: the map is moved so Alt 2's line is out of view: its label goes, the other two are placed again on their lines",
       said().join("|") === "In use · 104 min|Alt 1 · 3.5 min quicker"
       && TRY(() => { const z = (px) => px.map(([x, y]) => [(x - 250) * 2, (y - 60) * 2]); const p = labs().map(at); return distTo(p[0], z(USE_PX)) < 2 && distTo(p[1], z(ALT1_PX)) < 2; }), said().join("|"));
    {
      const b = lab("In use"), was = at(b);
      MAP.ox = 260;
      await act(async () => { fire("move", {}); });
      ok("⭐ DOM: while the map moves a label rides with its place on the road (20 px here)", Math.abs(at(b).x - (was.x - 20)) < 1.5, [was.x, at(b).x].join());
    }
    MAP.ox = 0; MAP.oy = 0; MAP.z = 1;
    await mapEv("moveend", {});
    ok("DOM: moved back, all three labels return", labs().length === 3);

    // ---- another lorry's lines ----
    await press(q("button[data-bo-all]"));
    const rigRow = qa("table[data-bo-table] tbody tr").find(tr => /8-wheeler/.test(tr.textContent));
    await press(rigRow);
    ok("⭐ DOM: the map is showing another lorry's lines (a row of All figures): no label, and the route layers draw the route again",
       labs().length === 0 && TRY(() => MAP.src.oluse.data.features.length === 0 && JSON.stringify(MAP.filt["route-line"]) === JSON.stringify(["!=", ["get", "failed"], true])), said().join("|"));
    await press(q("button[data-bo-show]"));
    ok("DOM: 'Show Alt 1 on map' brings the card's lorry back: the labels return, Alt 1 picked", labs().length === 3 && pressed() === "Alt 1 · 3.5 min quicker");

    // ---- a click on ANOTHER route's line opens its panel, the page stays at the map ----
    moved.length = 0;
    const focusWas = doc.activeElement;
    MAP.hits = (layers) => layers.includes("route-line") ? [{ properties: { route_id: "R002" }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 300, y: 300 }, lngLat: { lng: 0.3, lat: 0.3 } });
    MAP.hits = () => [];
    await settle();
    ok("⭐ DOM Q6: a click on R002's line opens R002's panel (it only picked the row before)",
       TRY(() => q("section[data-route-panel]").getAttribute("data-route-panel") === "R002" && tri("R002").getAttribute("aria-expanded") === "true"));
    ok("⭐ DOM Q6: the page stays at the map: nothing was scrolled to the panel and focus was not taken to its heading",
       !moved.some(([n]) => n === q("section[data-route-panel]")) && doc.activeElement !== q("#route-panel-h"), moved.length);

    // ---- R002: a diversion in use, options ruled out, the marked stretch ----
    ok("⭐ DOM: a dated diversion in use: 'In use · 147.7 min' first, then 'Main route · ruled out' and 'Alt 1 · ruled out' in grey words",
       said().join("|") === "In use · 147.7 min|Main route · ruled out|Alt 1 · ruled out"
       && labs().map(b => b.classList.contains("ol-out")).join() === "false,true,true" && pressed() === "In use · 147.7 min", said().join("|"));
    ok("⭐ DOM: the strong line is the diversion (option 2, both legs), not option 0",
       TRY(() => MAP.src.oluse.data.features.length === 2 && MAP.src.oluse.data.features.every(f => f.properties.alt_index === 2 && f.properties.route_id === "R002")
         && JSON.stringify(MAP.filt["route-line"]).includes('"R002"')));
    ok("⭐ DOM F2: the limits Alt 1 adds are marked on the map: four stretches, three signs (one for Syston Road's three), read once without ticking Lorry limits",
       TRY(() => MAP.src.olmarks.data.features.length === 4 && MAP.src.olsigns.data.features.length === 3
         && seen.filter(u => /\/public\/limits$/.test(u)).length === 1 && !q('input[data-route-layer="limits"]').checked),
       TRY(() => [MAP.src.olmarks.data.features.length, MAP.src.olsigns.data.features.length].join()));
    ok("DOM: every option ruled out: the card lists each with its reason as before, and has no tabs", tabs().length === 0 && /Every other option is ruled out\./.test(card()) && qa(".bo-card [data-bo-row^='out-']").length === 2);
    MAP.pops.length = 0;
    MAP.hits = (layers) => layers.length === 1 && layers[0] === "ol-sign" ? [MAP.src.olsigns.data.features.find(f => f.properties.id === "osm:2:weight")] : [];
    await mapEv("click", { point: { x: 320, y: 200 }, lngLat: { lng: 0.32, lat: 0.2 } });
    MAP.hits = () => [];
    ok("⭐ DOM F2: a click on the sign opens one small box: the limit's own name and 'Alt 1 meets it.' (4 new words), nothing else",
       TRY(() => MAP.pops.length === 1 && MAP.pops[0].html.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|") === "|Weight limit 7.5 t, Syston Road|Alt 1 meets it.|"), TRY(() => MAP.pops[0].html));
    ok("DOM: the sign's click picked nothing and opened no other route", pressed() === "In use · 147.7 min" && q("section[data-route-panel]").getAttribute("data-route-panel") === "R002");

    // ---- a route whose answer is still being worked out ----
    MAP.hits = (layers) => layers.includes("route-line") ? [{ properties: { route_id: "R003" }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 300, y: 300 }, lngLat: { lng: 0.3, lat: 0.3 } });
    MAP.hits = () => [];
    await settle();
    ok("⭐ DOM: while the card says 'Working out the best option…' there is no label, no marked stretch, and the lines draw as before",
       TRY(() => q("section[data-route-panel]").getAttribute("data-route-panel") === "R003" && !!q(".bo-card [data-bo-wait]")) && labs().length === 0
       && TRY(() => MAP.src.olmarks.data.features.length === 0 && MAP.src.olsigns.data.features.length === 0 && MAP.src.oluse.data.features.length === 0));

    // ---- full screen ("Beside the map") ----
    await press(tri("R001"));
    await press(q("button[data-route-beside]"));
    ok("⭐ DOM: beside the map (full screen) the picked route's labels are on the map, and a click on one picks in the card beside it",
       TRY(() => !!q('[data-full="1"]')) && said().join("|") === "In use · 104 min|Alt 1 · 3.5 min quicker|Alt 2 · 3 min longer");
    await press(lab("Alt 2"));
    ok("⭐ DOM: full screen: the card beside the map follows the label (Alt 2's tab and rows)",
       pressed() === "Alt 2 · 3 min longer" && TRY(() => q('[data-route-full-analysis] [data-bo-tab="2"]').getAttribute("aria-selected") === "true"));
    MAP.hits = (layers) => layers.includes("route-line") ? [{ properties: { route_id: "R002" }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 300, y: 300 }, lngLat: { lng: 0.3, lat: 0.3 } });
    MAP.hits = () => [];
    await settle();
    ok("⭐ DOM: full screen: a click on another route's line shows that route beside the map, with its labels",
       said().join("|") === "In use · 147.7 min|Main route · ruled out|Alt 1 · ruled out" && TRY(() => /R002/.test(q("[data-route-full-details]").textContent)), said().join("|"));
    await act(async () => { root.unmount(); });
  } catch (e) { ok("ROUTE OPTION LABELS DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 700)); }
  el.remove();
  finish();
})();

function finish(){
  console.log(`ui_fix_route_option_labels.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
}
