/* ui_fix_routes_open_map.js — 24 Nov 2026, branch claude/routes-open-map (the Routes page rethink, task A1; John's "Yes, as
 * recommended" to Q1 to Q14 of notes\routes-rethink-mockup-1124, cards 1 and 2; the brief notes\routes-rethink-build-1124).
 * The staff app's Data -> Routes map:
 *   Q3  the two legs in the public map's pair, out ink #3A3C41 and back grey #8E9197 (a pale pair on a dark casing on a dark
 *       basemap), the keys following;
 *   Q2  with a route OPEN (its panel, or Beside the map) the other approved routes are not drawn, only its two ends and the
 *       zones its drawn lines meet; a tick "Other routes" in Layers brings the routes back (off each time a route opens);
 *   Q4  the picked option a SOLID sign-blue line on white with its arrows, over the rest; no see-through band; the line in
 *       use drawn once, no halo; alternatives thin neutral grey on white, under the line in use;
 *       a route picked but NOT open: a soft sign-blue halo, the rest dimmed (the mother session's reading).
 * Source checks, the zone test as a pure function, then the Routes page mounted in a real DOM (jsdom) over a stand-in map
 * that records sources, filters and paint. Not covered here: pixels on a real map, a real basemap's dark ground, the real
 * server's lines (the session note's Chrome check, notes\session-1124-routes-open-map.md).
 * Every check marked ⭐ fails on the files before this branch. To see that:
 *   node backend/tests/ui_fix_routes_open_map.js <folder holding main's frontend/index.html as frontend/index.html>
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_routes_open_map.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 500) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };
const J = JSON.stringify;
const RR = require("./lib/route_line_styles").load("frontend").routes_map;   // 27 Nov 2026: the route-line table's copy

const ROOT = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, "..", "..");
const read = (...p) => { try { return fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n"); } catch (e) { return ""; } };
const html = read("frontend", "index.html");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const between = (a, b) => { const i = html.indexOf(a); const j = i < 0 ? -1 : html.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : html.slice(i, j); };
const layerSrc = (id) => between(`m.addLayer({ id: "${id}"`, "});");

// ---------------- source checks ----------------
// NARROWED 27 Nov 2026 (claude/route-line-spec): the Routes map's values are the route-line table's (RLS_R, the page's copy
// of backend/route_line_styles.py); each check below holds today's value as a literal and that the page reads it from the copy
ok("⭐ SRC Q3: the legs are the public map's pair: out ink #3A3C41, back grey #8E9197; green #059669 and amber #F59E0B are gone from this map",
   html.includes('const LEG_OUT = RLS_R.loaded_leg.color, LEG_BACK = RLS_R.empty_leg.color, SEL_HALO = RLS_R.pick.color;')
   && RR.loaded_leg.color === "#3A3C41" && RR.empty_leg.color === "#8E9197" && RR.pick.color === "#0B4EA2" && !html.includes('const LEG_OUT = "#059669"')
   && !/LEG_OUT = "#059669"|LEG_BACK = "#F59E0B"|SEL_HALO = "#1D4ED8"/.test(html));
ok("⭐ SRC Q3: a dark basemap takes the public map's pale pair on a dark casing (the values the public map's build set)",
   html.includes('const LEG_OUT_DARK = RLS_R.loaded_leg.color_dark, LEG_BACK_DARK = RLS_R.empty_leg.color_dark, LEG_CASE = RLS_R.loaded_leg.casing, LEG_CASE_DARK = RLS_R.loaded_leg.casing_dark;')
   && RR.loaded_leg.color_dark === "#D4D6DA" && RR.empty_leg.color_dark === "#9A9DA3" && RR.loaded_leg.casing === "#ffffff" && RR.loaded_leg.casing_dark === "#1F2024"
   && html.includes('const SEL_SIGN_DARK = RLS_R.pick.color_dark;') && RR.pick.color_dark === "#8AB4F8" && between("const legLook = (m) => {", "\n  };").includes("mapGroundDark(basemapShown.current || basemap)"));
ok("⭐ SRC: the dark look is applied after EVERY add of the layers (a basemap switch re-adds them on style.load)",
   between("const addNetworkLayers = (m) => {", "\n  };").includes("legLook(m);") && html.includes('m.on("style.load", () => { addNetworkLayers(m);'));
ok("⭐ SRC: no slate grey and no stock blue left on this map's lines: the alternatives #8E9197 (was #94A3B8), the marked stretch #1F2024 (was #334155)",
   html.includes('const ALT_COLOR = RLS_R.alternative.color, ALT_COLOR_DARK = RLS_R.alternative.color_dark;') && RR.alternative.color === "#8E9197" && RR.alternative.color_dark === "#7D8087"
   && html.includes('const OL_MARK = RLS_R.ruled_out_stretch.color, OL_MARK_DARK = RLS_R.ruled_out_stretch.color_dark;') && RR.ruled_out_stretch.color === "#1F2024" && RR.ruled_out_stretch.color_dark === "#E6E7EA"
   && !html.includes('const ALT_COLOR = "#94A3B8"') && !html.includes('"rgba(29,78,216,.32)"'));
ok("⭐ SRC Q4: the see-through band is gone: sel-line is a solid 3.4 px sign-blue line, opacity 1, on its own white casing, with arrows, over the line in use",
   TRY(() => { const s = layerSrc("sel-line"); return s.includes('"line-color": SEL_HALO, "line-opacity": 1, "line-width": RLS_R.pick.width, "line-offset": LEG_OFFSET') && !s.includes("0.32") && !/\}, "route-casing"\)/.test(s + "})"); })
   && layerSrc("sel-casing").includes('"line-color": RLS_R.pick.casing, "line-width": RLS_R.pick.casing_width, "line-offset": LEG_OFFSET')
   && RR.pick.width === 3.4 && RR.pick.casing === "#ffffff" && RR.pick.casing_width === 6.4
   && layerSrc("sel-arrows").includes('"icon-halo-color": SEL_HALO')
   && TRY(() => { const i = (id) => html.indexOf(`m.addLayer({ id: "${id}"`); return i("ol-use-arrows") < i("sel-casing") && i("sel-casing") < i("sel-line") && i("sel-line") < i("sel-arrows") && i("alt-line") < i("ol-use-casing"); }));
ok("⭐ SRC Q4: a route picked but not open: a soft sign-blue halo (0.3) under its legs, from its own source",
   layerSrc("sel-halo").includes('source: "selhalo"') && layerSrc("sel-halo").includes('"line-color": RLS_R.pick.halo, "line-opacity": RLS_R.pick.halo_opacity')
   && html.includes('paint: { "line-color": RLS_R.pick.halo, "line-opacity": RLS_R.pick.halo_opacity, "line-width": RLS_R.pick.halo_width,\n               "line-offset": LEG_OFFSET } }, "route-casing");')
   && RR.pick.halo === "#0B4EA2" && RR.pick.halo_opacity === 0.3 && J(RR.pick.halo_width) === J(["interpolate", ["linear"], ["zoom"], 9, 11, 14, 16]));
ok("⭐ SRC card 1: the line in use 3.2 px on a 6 px white casing, opacity 1; alternatives 2.4 px on a 5.4 px white casing, no offset",
   layerSrc("ol-use-line").includes('"line-width": RLS_R.in_use.width') && layerSrc("ol-use-casing").includes('"line-color": RLS_R.in_use.casing, "line-width": RLS_R.in_use.casing_width, "line-opacity": RLS_R.in_use.casing_opacity')
   && RR.in_use.width === 3.2 && RR.in_use.casing === "#ffffff" && RR.in_use.casing_width === 6 && RR.in_use.casing_opacity === 1
   && layerSrc("alt-line").includes('"line-color": ALT_COLOR, "line-width": RLS_R.alternative.width, "line-opacity": RLS_R.alternative.opacity') && !layerSrc("alt-line").includes("line-offset")
   && layerSrc("alt-casing").includes('"line-color": RLS_R.alternative.casing, "line-width": RLS_R.alternative.casing_width')
   && RR.alternative.width === 2.4 && RR.alternative.opacity === 1 && RR.alternative.casing === "#ffffff" && RR.alternative.casing_width === 5.4);
ok("⭐ SRC: a click on an open route's line is looked for in a wider box (8 px a side), the lines are not widened for it",
   html.includes("const OL_HIT_PX = 8;") && between("cbRef.current.olClick = (e) => {", "\n  };").includes("[[e.point.x - OL_HIT_PX, e.point.y - OL_HIT_PX], [e.point.x + OL_HIT_PX, e.point.y + OL_HIT_PX]]"));
ok("⭐ SRC Q2: the 30 % fade only while a route is picked and NOT open (applyEmphasis reads the open route)",
   between("const applyEmphasis = (m) => {", "\n  };").includes("const sel = olOpenRef.current ? null : selectedRef.current;"));
// found in Chrome on 24 Nov: a route opened before its drawn lines came in kept every location (the ends were read from
// the lines only, and the lines' arrival does not run the scope again): the ends come from the route's own row first
ok("⭐ SRC Q2: an open route's two ends come from its own row (status), the drawn lines only as a fallback",
   html.includes("const st = (status || []).find(r => r.id === olRoute) || {};")
   && html.includes("const ends = [st.origin_id || p0.origin_id, st.dest_id || p0.dest_id].filter(Boolean);"));
// NARROWED 26 Nov 2026 (lines-prints Q1): the week maps took the same pair in their own branch (CM_OUT / CM_BACK = LEG_OUT /
// LEG_BACK's values); this branch's own constants are still the only ones on the Routes map
ok("⭐ SRC: the Routes map's pair is its own (LEG_OUT / LEG_BACK); the week maps keep their own constants, now the same ink and grey (lines-prints Q1)",
   // NARROWED 27 Nov 2026: each map reads its own surface of the table (commit_map, routes_map), the same ink and grey
   html.includes('const CM_OUT = RLS_C.loaded_leg.color, CM_BACK = RLS_C.empty_leg.color') && html.includes('const LEG_OUT = RLS_R.loaded_leg.color, LEG_BACK = RLS_R.empty_leg.color')
   && TRY(() => { const C = require("./lib/route_line_styles").load("frontend").commit_map; return C.loaded_leg.color === RR.loaded_leg.color && C.empty_leg.color === RR.empty_leg.color; }));

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
const MAP = { W: 700, H: 430, on: [], hits: () => [], filt: {}, src: {}, lay: {}, paint: {}, lyo: {}, box: null, styles: [] };
const fire = (ev, e) => MAP.on.filter(h => h.ev === ev && !h.layer).forEach(h => h.fn(e));
w.mapboxgl = { accessToken: "", NavigationControl: function(){}, ScaleControl: function(){}, AttributionControl: function(){},
  LngLatBounds: function(){ return { pts: [], extend(c){ this.pts.push(c); return this; } }; },
  Popup: function(){ const p = { setLngLat: () => p, setHTML: () => p, setDOMContent: () => p, addTo: () => p, remove(){}, on: () => p }; return p; },
  Marker: function(){ const m = { setLngLat: () => m, addTo: () => m, remove(){}, getElement: () => w.document.createElement("div"), on: () => m, setDraggable: () => m }; return m; },
  Map: function(o){
    MAP.box = o && o.container;
    const m = new Proxy({}, { get: (t, k) => {
      if (k === "on") return (ev, a, b) => { const fn = typeof a === "function" ? a : b; MAP.on.push({ ev, layer: typeof a === "string" ? a : null, fn }); if (ev === "load") setTimeout(() => fn(), 0); return m; };
      if (k === "addControl") return (c) => { if (c && c.onAdd){ const n = c.onAdd(m); if (n) ctlBox.appendChild(n); } return m; };
      if (k === "getContainer") return () => MAP.box;
      if (k === "getCanvas" || k === "getCanvasContainer") return () => ({ style: {}, addEventListener(){}, removeEventListener(){} });
      if (k === "project") return (c) => ({ x: c[0] * 1000, y: c[1] * 1000 });
      if (k === "unproject") return (p) => ({ lng: p[0] / 1000, lat: p[1] / 1000 });
      if (k === "setFilter") return (l, f) => { MAP.filt[l] = f; return m; };
      if (k === "getZoom") return () => 10;
      if (k === "addLayer") return (l, before) => { MAP.lay[l.id] = Object.assign({ before }, l); MAP.paint[l.id] = Object.assign({}, l.paint); if (l.filter !== undefined) MAP.filt[l.id] = l.filter; return m; };
      if (k === "getLayer") return (id) => MAP.lay[id];
      if (k === "setPaintProperty") return (l, p, v) => { (MAP.paint[l] = MAP.paint[l] || {})[p] = v; return m; };
      if (k === "setLayoutProperty") return (l, p, v) => { (MAP.lyo[l] = MAP.lyo[l] || {})[p] = v; return m; };
      if (k === "getLayoutProperty") return (l, p) => (MAP.lyo[l] || {})[p];
      if (k === "addSource") return (id, s) => { MAP.src[id] = { ...s, setData(d){ this.data = d; } }; return m; };
      if (k === "getSource") return (id) => MAP.src[id];
      if (k === "setStyle") return (s) => { MAP.styles.push(s); MAP.lay = {}; MAP.src = {}; setTimeout(() => fire("style.load", {}), 0); return m; };
      if (k === "hasImage") return () => false;
      if (k === "getStyle") return () => ({ layers: [] });
      if (k === "queryRenderedFeatures") return (g, q) => MAP.hits((q && q.layers) || [], g);
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

// ---------------- the zone test, as the pure function the page calls ----------------
// a point's place: lng / lat in degrees near (0, 0); 0.001 degree is about 111 m
const USE_PX = [[100, 100], [250, 100], [600, 120], [600, 330]], ALT1_PX = [[100, 100], [250, 100], [400, 250], [600, 330]], ALT2_PX = [[100, 100], [100, 380], [600, 380], [600, 330]];
const ll = (px) => px.map(([x, y]) => [x / 1000, y / 1000]);
const box = (x0, y0, x1, y1) => ({ type: "Polygon", coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]] });
const ZF = (id, geometry) => ({ type: "Feature", properties: { id }, geometry });
const Z_ALT2 = ZF("Z001", box(0.30, 0.37, 0.40, 0.39));                                  // Alt 2 crosses it
const Z_FAR = ZF("Z002", box(0.80, 0.80, 0.90, 0.90));                                   // nothing near
const H_ALONG = ZF("Z003", { type: "LineString", coordinates: [[0.12, 0.1], [0.2, 0.1]] }); // a haul road the main route runs along
const H_ACROSS = ZF("Z004", { type: "LineString", coordinates: [[0.22, 0.05], [0.22, 0.15]] }); // a road the route only crosses
const Z_HOLE = ZF("Z005", { type: "Polygon", coordinates: [[[0.05, 0.05], [0.65, 0.05], [0.65, 0.45], [0.05, 0.45], [0.05, 0.05]], [[0.06, 0.06], [0.64, 0.06], [0.64, 0.44], [0.06, 0.44], [0.06, 0.06]]] });
const HAVE = typeof w.olZonesOver === "function";
ok("⭐ ZONES: the test is a function of its own (olZonesOver)", HAVE);
if (HAVE) {
  const all = [Z_ALT2, Z_FAR, H_ALONG, H_ACROSS, Z_HOLE];
  ok("⭐ ZONES: with the line in use and both alternatives: the area Alt 2 crosses and the haul road the route runs along; not the far area, not a road it only crosses, not an area whose hole holds every line",
     J(w.olZonesOver([ll(USE_PX), ll(ALT1_PX), ll(ALT2_PX)], all)) === J(["Z001", "Z003"]), J(w.olZonesOver([ll(USE_PX), ll(ALT1_PX), ll(ALT2_PX)], all)));
  ok("⭐ ZONES: with the line in use alone (Out only, no Alt 2): the area Alt 2 crosses is not kept",
     J(w.olZonesOver([ll(USE_PX)], all)) === J(["Z003"]));
  ok("ZONES: a MultiPolygon counts as its parts; no line, no zone; a zone with no shape breaks nothing",
     J(w.olZonesOver([ll(ALT2_PX)], [ZF("Z9", { type: "MultiPolygon", coordinates: [box(0.8, 0.8, 0.9, 0.9).coordinates, box(0.3, 0.37, 0.4, 0.39).coordinates] }), ZF("Z8", null)])) === J(["Z9"])
     && J(w.olZonesOver([], all)) === "[]");
}

// ---------------- the Routes page ----------------
const respond = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 0)); });
const P = "Artic Tipper (44t)";
const META = { routes: [], materials: ["Aggregate"], vehicles: [P], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } }, mapbox_token: "",
  vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [], ipts: [],
  tenant: { name: "Wolds Link", team_label: "Team", currency: "GBP", currency_symbol: "£", country: "GB", distance_unit: "mi", demo_notice: "Fictional scheme" } };
const LOCS = { type: "FeatureCollection", features: [["L001", "Tilton Viaduct site", 0.1, 0.1], ["L003", "Wolds Link Inert Landfill", 0.6, 0.33], ["L009", "Far quarry", 0.9, 0.9]]
  .map(([id, name, lon, lat]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id, name, role: "origin", loc_type: "Quarry", supplies: [], receives: [] } })) };
const leg = (km, hr, alt) => ({ alt_index: alt || 0, baked: true, distance_km: km, duration_hr: hr, error: null, haul_zones: [], haul_recorded: true });
const ST = (id, o, d) => ({ id, origin: "Tilton Viaduct site", dest: "Wolds Link Inert Landfill", origin_id: o, dest_id: d, ipt: null, haul_roads: [], gate_blockers: [],
  profiles: { [P]: { baked: true, distance_km: 40, duration_hr: 0.75, legs: { loaded: [leg(40, 0.75), leg(44, 0.8, 1), leg(46, 0.9, 2)], return: [leg(42, 0.5)] }, return_baked: true, alt_count: 3 } } });
const STATUS = [ST("R001", "L001", "L003"), ST("R002", "L009", "L003")];
const ROUTES_GJ = (lg) => ({ type: "FeatureCollection", features: [
  { type: "Feature", properties: { route_id: "R001", origin_id: "L001", dest_id: "L003", vehicle_profile: P, alt_index: 0 }, geometry: { type: "LineString", coordinates: lg === "loaded" ? ll(USE_PX) : ll(USE_PX).reverse() } },
  { type: "Feature", properties: { route_id: "R002", origin_id: "L009", dest_id: "L003", vehicle_profile: P, alt_index: 0 }, geometry: { type: "LineString", coordinates: [[0.9, 0.9], [0.6, 0.33]] } }] });
const ROW = (alt) => ({ profile: P, alt_index: alt, loaded_km: 40 + alt, return_km: 42, return_estimated: false, loaded_hr: 0.75, return_hr: 0.5,
  load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 1.7, haul_speed_applied: false,
  trips_per_day: 5, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 56, lorry_day: { limited_by: "shift", trips_without_rules: 5, words: "5 a day", break_minutes: 45 } });
const DATA = { rows: [ROW(0), ROW(1), ROW(2)], planning: { shift_hours_per_day: 10, working_days_per_month: 22, shift_note: "" } };
const GEO = (rid) => ({ type: "FeatureCollection", features: [[0, USE_PX], [1, ALT1_PX], [2, ALT2_PX]].flatMap(([alt, px]) => ["loaded", "return"].map(lg => (
  { type: "Feature", properties: { route_id: rid, vehicle_profile: P, leg: lg, alt_index: alt }, geometry: { type: "LineString", coordinates: lg === "loaded" ? ll(px) : ll(px).slice().reverse() } }))) });
const OPT = (alt, label, o) => Object.assign({ alt, label, return_alt: alt, ruled_out: [], added_limits: [], searched: true, heads: {}, parts: {}, n5: false,
  counts: { km: 64.71, drive_min: 66.5, cycle_min: 100.5, trips: 5, co2_kg: 56, busy_min: {}, collisions: 39, goods: 1, left_turns: 9, cycle_meets: 4, cycle_beside_km: 0.17, places: 2 },
  pct: { left_turns: -10, cycle_meets: -33, cycle_beside_km: null, places: -71 }, head_words: { people: "fewer", time: "quicker", busy: "not counted", carbon: "same" },
  part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "fewer" }, sentences: [`${label} had 39 collisions on it against 39 on the route in use, 2021–2025.`] }, o || {});
const USE = (a) => ({ loaded: { alt: a, label: "x", why: "main route", status: null }, return: { alt: a, label: "x", why: "main route", status: null } });
const CU = { km: 66.65, drive_min: 70, cycle_min: 104, trips: 5, co2_kg: 57.7, collisions: 39, goods: 4, left_turns: 10, cycle_meets: 6, cycle_beside_km: 0.24, places: 7, busy_min: {} };
const BEST = (rid, inUse) => ({ day: "2026-11-24", checks: {}, route: { route: rid, answer: "Suggested", option: "Alt 1", alt: 1, why: "3.5 min quicker a round trip.",
  trade: null, held_back: null, lorry: P, lorry_basis: "approved loads", other_lorries: [], in_use: USE(inUse), counts_in_use: CU,
  checks: { limits_held: true, community_all_options: true, collision_history: "current" },
  options: [OPT(1, "Alt 1", { chosen: true }), OPT(inUse === 2 ? 0 : 2, inUse === 2 ? "The main route" : "Alt 2")],
  lines: inUse === 2
    ? [{ alt: 2, return_alt: 2, name: "In use", words: "104 min", state: "in_use" }, { alt: 1, return_alt: 1, name: "Alt 1", words: "3.5 min quicker", state: "quicker" }, { alt: 0, return_alt: 0, name: "Main route", words: "3 min longer", state: "longer" }]
    : [{ alt: 0, return_alt: 0, name: "In use", words: "104 min", state: "in_use" }, { alt: 1, return_alt: 1, name: "Alt 1", words: "3.5 min quicker", state: "quicker" }, { alt: 2, return_alt: 2, name: "Alt 2", words: "3 min longer", state: "longer" }] } });
const ZONES = [Z_ALT2, Z_FAR, H_ALONG, H_ACROSS].map(z => ({ id: z.properties.id, name: "Zone " + z.properties.id, kind: z.geometry.type === "Polygon" ? "closure" : "haul_road",
  affects_routing: true, date_from: null, date_to: null, geometry: z.geometry }));
w.fetch = (url) => { const u = String(url);
  if (/\/locations\/geojson$/.test(u)) return respond(LOCS);
  if (/\/routes\/status$/.test(u)) return respond(STATUS);
  if (/\/routes\/summary$/.test(u)) return respond({ here_configured: true, routes: 2, locations: 3 });
  if (/\/zones$/.test(u)) return respond({ zones: ZONES, haul_links: {} });
  const rg = u.match(/\/routes\/geojson\?.*leg=(\w+)/); if (rg) return respond(ROUTES_GJ(rg[1]));
  if (/\/routes\/community-counts$/.test(u)) return respond({ fetched_at: "2026-11-16", near_m: {}, kinds: [], routes: {} });
  if (/\/routes\/diversions$/.test(u)) return respond({ periods: [], busy: [] });
  if (/\/api\/gates$/.test(u)) return respond({ gates: [] });
  if (/\/routes\/R00\d\/analysis$/.test(u)) return respond(DATA);
  if (/\/routes\/R001\/best-option$/.test(u)) return respond(BEST("R001", 0));
  if (/\/routes\/R002\/best-option$/.test(u)) return respond(BEST("R002", 2));
  if (/\/public\/limits$/.test(u)) return respond({ type: "FeatureCollection", features: [] });
  if (/\/routes\/R00\d\/haul-roads$/.test(u)) return respond({ links: [], plan: {} });
  const g = u.match(/\/routes\/(R00\d)\/geometries$/); if (g) return respond(GEO(g[1]));
  return new Promise(() => {}); };
w.matchMedia = (q) => ({ get matches(){ return /min-width: 1024px/.test(q); }, media: q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){} });
const doc = w.document, de = doc.documentElement; let fsEl = null;
Object.defineProperty(doc, "fullscreenElement", { configurable: true, get: () => fsEl });
de.requestFullscreen = () => { fsEl = de; return Promise.resolve(); };
doc.exitFullscreen = () => { fsEl = null; return Promise.resolve(); };
const rect = (o) => Object.assign({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0 }, o);
w.Element.prototype.getBoundingClientRect = function(){ return this === MAP.box ? rect({ width: MAP.W, height: MAP.H, right: MAP.W, bottom: MAP.H }) : rect({}); };
w.Element.prototype.scrollIntoView = function(){};
w.ResizeObserver = function(){ this.observe = () => {}; this.disconnect = () => {}; };

(async () => {
  if (!loaded || typeof w.DataManagement !== "function") { ok("the Routes page (DataManagement) is defined", false); return finish(); }
  w.__ACCESS.info = { role: "admin", label: "Admin", via: "login", can_approve: true, ipt: null, name: "Ada", email: "ada@example.org" };
  const el = doc.createElement("div"); doc.body.appendChild(el); const root = w.ReactDOM.createRoot(el);
  const settle = async () => { for (let i = 0; i < 14; i++) await tick(); };
  const press = async (b) => { await act(async () => { b.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await settle(); };
  const mapEv = async (ev, e) => { await act(async () => { fire(ev, e); }); await settle(); };
  const q = (s) => el.querySelector(s), qa = (s) => [...el.querySelectorAll(s)];
  const ids = (s) => ((MAP.src[s] && MAP.src[s].data && MAP.src[s].data.features) || []).map(f => `${f.properties.leg}:${f.properties.alt_index}`).sort().join();
  const BASE = ["!=", ["get", "failed"], true];
  const ROUTE_ONLY = (r) => J(["all", BASE, ["==", ["get", "route_id"], r]]);
  const ROUTE_OFF = (r) => J(["all", BASE, ["!=", ["get", "route_id"], r], ["==", ["get", "route_id"], r]]);
  const others = () => q('input[data-route-others]');
  const lab = (t) => qa(".ol-layer button.ol-lab").find(b => b.textContent.replace(/\s+/g, " ").trim().startsWith(t));
  try {
    await act(async () => { root.render(w.React.createElement(w.DataManagement, { meta: META, who: "t", subTab: "routes", onSubTab(){} })); });
    await settle();
    Object.defineProperty(MAP.box, "clientWidth", { configurable: true, get: () => MAP.W });
    Object.defineProperty(MAP.box, "clientHeight", { configurable: true, get: () => MAP.H });

    // ---- nothing picked: the whole network ----
    ok("DOM: nothing picked: every route drawn, every location and zone, no halo, no pick, no alternatives",
       J(MAP.filt["route-line"]) === J(BASE) && MAP.filt["node-dots"] == null && J(MAP.filt["zone-fill"]) === J(["==", ["geometry-type"], "Polygon"]) && MAP.filt["zone-label"] == null
       && ids("sel") === "" && ids("alts") === "" && ids("selhalo") === "", J([MAP.filt["route-line"], MAP.filt["node-dots"]]));
    ok("⭐ DOM Q3: the drawn legs are ink out and grey back on white (light ground); the line in use's layers the same pair",
       J(MAP.paint["route-line"]["line-color"]) === J(["match", ["get", "leg"], "return", "#8E9197", "#3A3C41"])
       && J(MAP.paint["ol-use-line"]["line-color"]) === J(MAP.paint["route-line"]["line-color"]) && MAP.paint["route-casing"]["line-color"] === "#ffffff"
       && J(MAP.paint["route-arrows"]["icon-halo-color"]) === J(MAP.paint["route-line"]["line-color"]));
    ok("⭐ DOM: no 'Other routes' tick while no route is open", !others());
    ok("⭐ DOM keys: Out ink, Back grey, Picked the solid sign blue, Alternative the neutral grey (no green, amber or see-through blue)",
       TRY(() => { const c = (k) => w.getComputedStyle(q(`[data-legend-leg="${k}"] span`)).backgroundColor;
         return c("out") === "rgb(58, 60, 65)" && c("back") === "rgb(142, 145, 151)" && c("picked") === "rgb(11, 78, 162)" && c("alt") === "rgb(142, 145, 151)"; }),
       TRY(() => ["out", "back", "picked", "alt"].map(k => w.getComputedStyle(q(`[data-legend-leg="${k}"] span`)).backgroundColor).join("|")));

    // ---- R001 picked, NOT open (its name in the list) ----
    await press(q('button[data-route-open="R001"]'));
    ok("⭐ DOM Q4 (picked, not open): R001 sits in the soft halo (its own drawn line, both legs), its other options thin grey, nothing in the solid pick",
       ids("selhalo") === "loaded:0,return:0" && ids("alts") === "loaded:1,loaded:2,return:1,return:2" && ids("sel") === "", [ids("selhalo"), ids("alts"), ids("sel")].join(" / "));
    ok("DOM (picked, not open): the other routes stay drawn, faded to 30 %; every location and zone stays",
       J(MAP.filt["route-line"]) === J(BASE) && J(MAP.paint["route-line"]["line-opacity"]) === J(["case", ["==", ["get", "route_id"], "R001"], 1, 0.3])
       && MAP.filt["node-dots"] == null && MAP.filt["zone-label"] == null);

    // ---- R001 OPEN with ▶ ----
    await press(q('button[data-route-tri="R001"]'));
    ok("⭐ DOM Q2: R001 open: no other route is drawn (nor its failed line); the line in use by its own layers, no fade",
       MAP.filt["route-line"] && J(MAP.filt["route-line"]) === ROUTE_OFF("R001") && J(MAP.filt["route-arrows"]) === ROUTE_OFF("R001") && J(MAP.filt["route-casing"]) === ROUTE_OFF("R001")
       && J(MAP.filt["route-failed"]) === J(["all", ["==", ["get", "failed"], true], ["==", ["get", "route_id"], "R001"]])
       && ids("oluse") === "loaded:0,return:0" && MAP.paint["route-line"]["line-opacity"] === 1, J(MAP.filt["route-line"]));
    ok("⭐ DOM Q2: R001 open: only its two ends among the locations", J(MAP.filt["node-dots"]) === J(["in", ["get", "id"], ["literal", ["L001", "L003"]]]), J(MAP.filt["node-dots"]));
    ok("⭐ DOM Q2: R001 open: only the zones its drawn lines meet (the area Alt 2 crosses, the haul road it runs along), fill, edge and name alike",
       J(MAP.filt["zone-label"]) === J(["in", ["get", "id"], ["literal", ["Z001", "Z003"]]]) && J(MAP.filt["zone-outline"]) === J(MAP.filt["zone-label"])
       && J(MAP.filt["zone-fill"]) === J(["all", ["==", ["geometry-type"], "Polygon"], ["in", ["get", "id"], ["literal", ["Z001", "Z003"]]]]), J(MAP.filt["zone-label"]));
    ok("⭐ DOM Q4: the pick is the line in use: nothing in the solid pick (no halo, nothing drawn twice); the two alternatives thin grey; no halo source",
       ids("sel") === "" && ids("alts") === "loaded:1,loaded:2,return:1,return:2" && ids("selhalo") === "", [ids("sel"), ids("alts")].join(" / "));
    ok("⭐ DOM Q2: an 'Other routes' tick in Layers, off", !!others() && others().checked === false && TRY(() => others().closest("[data-route-layers]") !== null));

    // ---- a picked alternative ----
    await press(lab("Alt 1"));
    ok("⭐ DOM Q4: Alt 1 picked: Alt 1's two legs in the solid sign-blue pick; Alt 2 thin grey; the line in use NOT in the alternatives (drawn once, by its own layers)",
       ids("sel") === "loaded:1,return:1" && ids("alts") === "loaded:2,return:2" && ids("oluse") === "loaded:0,return:0", [ids("sel"), ids("alts"), ids("oluse")].join(" / "));
    ok("⭐ DOM Q4: the pick's paint: sign blue, opacity 1, 3.4 px, on a 6.4 px white casing, arrows with a sign-blue edge",
       MAP.paint["sel-line"]["line-color"] === "#0B4EA2" && MAP.paint["sel-line"]["line-opacity"] === 1 && MAP.paint["sel-line"]["line-width"] === 3.4
       && MAP.paint["sel-casing"]["line-color"] === "#ffffff" && MAP.paint["sel-casing"]["line-width"] === 6.4 && MAP.paint["sel-arrows"]["icon-halo-color"] === "#0B4EA2");
    MAP.hits = (layers, g) => layers.includes("alt-line") && J(g) === J([[400 - 8, 380 - 8], [400 + 8, 380 + 8]])
      ? [{ properties: { route_id: "R001", vehicle_profile: P, leg: "loaded", alt_index: 2 }, geometry: {} }] : [];
    await mapEv("click", { point: { x: 400, y: 380 }, lngLat: { lng: 0.4, lat: 0.38 } });
    MAP.hits = () => [];
    ok("⭐ DOM: a click within 8 px of the thin Alt 2 line picks it (the box is wider, the line is not)", ids("sel") === "loaded:2,return:2" && ids("alts") === "loaded:1,return:1", ids("sel"));
    await press(lab("In use"));
    ok("DOM: back to the line in use: nothing in the pick again", ids("sel") === "" && ids("alts") === "loaded:1,loaded:2,return:1,return:2");

    // ---- Out only ----
    await press(q('[data-leg-pick="loaded"]'));
    ok("DOM: Out only: the open route's own zones follow the lines drawn (Alt 2's out leg still crosses Z001)",
       J(MAP.filt["zone-label"]) === J(["in", ["get", "id"], ["literal", ["Z001", "Z003"]]]) && ids("alts") === "loaded:1,loaded:2");
    await press(q('[data-leg-pick="both"]'));

    // ---- Other routes ----
    await act(async () => { others().click(); }); await settle();
    ok("⭐ DOM Q2: 'Other routes' ticked: every other route drawn again at full strength (no 30 % fade); this route's line in use still drawn once",
       others().checked && J(MAP.filt["route-line"]) === J(["all", BASE, ["!=", ["get", "route_id"], "R001"]]) && MAP.paint["route-line"]["line-opacity"] === 1
       && J(MAP.paint["route-casing"]["line-opacity"]) === J(0.85), J(MAP.filt["route-line"]));
    ok("DOM: the tick brings the routes back only: the ends and the zones stay this route's", J(MAP.filt["node-dots"]) === J(["in", ["get", "id"], ["literal", ["L001", "L003"]]]));

    // ---- a basemap switch re-adds the layers: the scope and the paint come back ----
    await act(async () => { fire("style.load", {}); }); await settle();
    ok("⭐ DOM: after a basemap switch (layers re-added) the open route's scope and the pair hold",
       J(MAP.filt["node-dots"]) === J(["in", ["get", "id"], ["literal", ["L001", "L003"]]]) && J(MAP.filt["zone-label"]) === J(["in", ["get", "id"], ["literal", ["Z001", "Z003"]]])
       && J(MAP.paint["route-line"]["line-color"]) === J(["match", ["get", "leg"], "return", "#8E9197", "#3A3C41"]));

    // ---- closing the panel ----
    await press(q('button[data-route-tri="R001"]'));
    ok("⭐ DOM: closing the panel puts the network back (every route, location and zone); R001 still picked: the halo and the 30 % fade",
       J(MAP.filt["route-line"]) === J(BASE) && MAP.filt["node-dots"] == null && MAP.filt["zone-label"] == null
       && J(MAP.filt["zone-fill"]) === J(["==", ["geometry-type"], "Polygon"]) && ids("selhalo") === "loaded:0,return:0" && ids("sel") === ""
       && J(MAP.paint["route-line"]["line-opacity"]) === J(["case", ["==", ["get", "route_id"], "R001"], 1, 0.3]) && !others(), J([MAP.filt["route-line"], MAP.filt["node-dots"]]));

    // ---- R002 open: a diversion in use (option 2); 'Other routes' is off again ----
    await press(q('button[data-route-tri="R002"]'));
    ok("⭐ DOM: another route opened: 'Other routes' off again; R002 alone, its ends",
       !!others() && others().checked === false && J(MAP.filt["route-line"]) === ROUTE_OFF("R002")
       && J(MAP.filt["node-dots"]) === J(["in", ["get", "id"], ["literal", ["L009", "L003"]]]), J(MAP.filt["route-line"]));
    ok("⭐ DOM: a diversion in use (option 2): the legs' pair on option 2 (ol-use), options 0 and 1 the thin grey, none twice",
       ids("oluse") === "loaded:2,return:2" && ids("alts") === "loaded:0,loaded:1,return:0,return:1" && ids("sel") === "", [ids("oluse"), ids("alts"), ids("sel")].join(" / "));
    await press(lab("Main route"));
    ok("⭐ DOM: the usual road (option 0) picked: it is the solid pick, the diversion in use stays drawn once in ink and grey",
       ids("sel") === "loaded:0,return:0" && ids("alts") === "loaded:1,return:1" && ids("oluse") === "loaded:2,return:2");

    // ---- Beside the map (full screen) ----
    await press(q("button[data-route-beside]"));
    ok("⭐ DOM: beside the map, the route shown is open the same way: others off, its ends, the tick",
       TRY(() => !!q('[data-full="1"]')) && J(MAP.filt["route-line"]) === ROUTE_OFF("R002") && J(MAP.filt["node-dots"]) === J(["in", ["get", "id"], ["literal", ["L009", "L003"]]]) && !!others(),
       J(MAP.filt["route-line"]));

    // ---- a dark ground ----
    await act(async () => { w.document.documentElement.setAttribute("data-theme", "dark"); });
    const bm = qa("select").find(s => [...s.options].some(o => /dark/.test(o.value)));
    if (bm) {
      const dark = [...bm.options].find(o => /dark/.test(o.value)).value;
      await act(async () => { const d = Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value"); d.set.call(bm, dark); bm.dispatchEvent(new w.Event("change", { bubbles: true })); });
      await settle();
      ok("⭐ DOM Q3 dark ground: the pale pair on a dark casing, the alternatives' dark grey, the pick the light sign blue, the halo too",
         J(MAP.paint["route-line"]["line-color"]) === J(["match", ["get", "leg"], "return", "#9A9DA3", "#D4D6DA"]) && J(MAP.paint["ol-use-line"]["line-color"]) === J(MAP.paint["route-line"]["line-color"])
         && MAP.paint["route-casing"]["line-color"] === "#1F2024" && MAP.paint["ol-use-casing"]["line-color"] === "#1F2024" && MAP.paint["alt-line"]["line-color"] === "#7D8087"
         && MAP.paint["alt-casing"]["line-color"] === "#1F2024" && MAP.paint["sel-line"]["line-color"] === "#8AB4F8" && MAP.paint["sel-halo"]["line-color"] === "#8AB4F8"
         && MAP.paint["ol-mark"]["line-color"] === "#E6E7EA", J([MAP.paint["route-line"]["line-color"], MAP.paint["sel-line"]["line-color"]]));
      ok("⭐ DOM Q2: and the dark basemap's re-add keeps the open route alone", J(MAP.filt["route-line"]) === ROUTE_OFF("R002"));
    } else ok("DOM: a basemap picker with a dark style is on the Routes page", false, qa("select").map(s => s.getAttribute("aria-label")).join());

    // ---- Locations and Zones: the same map, nothing of an open route applies there ----
    for (const page of ["locations", "zones"]) {
      await act(async () => { root.render(w.React.createElement(w.DataManagement, { meta: META, who: "t", subTab: page, onSubTab(){} })); });
      await settle();
      ok(`DOM (a guard: main passes it too): on ${page[0].toUpperCase() + page.slice(1)} (the shared map) every route, location and zone is drawn: no open route's scope, no 'Other routes'`,
         J(MAP.filt["route-line"]) === J(BASE) && MAP.filt["node-dots"] == null && MAP.filt["zone-label"] == null && MAP.filt["zone-outline"] == null
         && J(MAP.filt["zone-fill"]) === J(["==", ["geometry-type"], "Polygon"]) && !others(), J([MAP.filt["route-line"], MAP.filt["node-dots"], MAP.filt["zone-label"]]));
    }
    await act(async () => { root.unmount(); });
  } catch (e) { ok("ROUTES OPEN MAP DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 700)); }
  el.remove();
  finish();
})();

function finish(){
  console.log(`ui_fix_routes_open_map.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
}
