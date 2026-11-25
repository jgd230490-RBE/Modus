/* ui_fix_routes_card_room.js — 17 Nov 2026, branch claude/routes-card-room (John's "Yes, as recommended" to the mockup
 * notes\routes-card-room-mockup-1117: Option B and Q1 to Q4). Room for the Best option card on Data -> Routes: an open
 * route is a panel of its own under the Routes list (it was rows inside the list's 40vh box), the card first, the
 * route's settings beside it on a wide panel and after it on a narrow one, all figures and diversions under both;
 * "Beside the map" (full screen for that route), a named close; the card's "Show Alt N on map" moves the page up to the
 * map; the haul road picker keeps to its box's width.
 *
 * Source checks, then the Routes page mounted in a real DOM (jsdom): open, order, focus, close, wide, full screen.
 * Not covered here: any layout in pixels (jsdom has none: the panel's width and the map's box are stubbed), the look,
 * a real server's answers (the reads are stubbed in the server's shapes), Chrome's own full screen. Those are the
 * session note's Chrome check (notes\session-1117-routes-card-room.md).
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the files before this branch. To see that:
 *   node backend/tests/ui_fix_routes_card_room.js <folder holding main's frontend/index.html as frontend/index.html>
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_routes_card_room.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

// ---------------- source checks ----------------
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };
const between = (a, b) => { const i = html.indexOf(a); const j = i < 0 ? -1 : html.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : html.slice(i, j); };
const table = between('<table className="w-full text-sm tab-cards" data-tab-cards="routes">', '{!status && <tr><td colSpan="11"');
const ra = fnSrc("RouteAnalysis"), det = fnSrc("RouteFullDetails"), haul = fnSrc("HaulRoads"), bo = fnSrc("BestOption");
const panel = between('<section className="card" id="route-panel"', "</section>");

ok("⭐ SRC: the Routes list's table holds rows only: no analysis, Near box, vehicle chips or diversions inside it",
   table.length > 0 && !/<RouteAnalysis|<NearDetails|<VehChips|data-route-vehicles|data-route-diversions|\{open && </.test(table));
ok("SRC: the list is still a 40vh box, the open row's ▶ turned (▼) and the picked row tinted",
   html.includes('<div className="overflow-auto" style={{ maxHeight: "40vh" }}>\n          <table className="w-full text-sm tab-cards" data-tab-cards="routes">')
   && table.includes('transform: open ? "rotate(90deg)" : "none"') && table.includes('(selected === r.id ? "bg-blue-50" : "hover:bg-slate-50")'));
ok("⭐ SRC: opening a route's panel picks the route in the list (so a Suggested card shows Make primary at once)",
   table.includes("if(open) setOpenRow(null); else { setOpenRow(r.id); if(selected !== r.id) selectRoute(r.id); }"));
ok("⭐ SRC: the open route is a panel of its own after the list's card: a section named by its heading '<id> · <origin> → <dest>'",
   panel.length > 0 && html.indexOf('id="route-panel"') > html.indexOf('data-tab-cards="routes"')
   && panel.includes('aria-labelledby="route-panel-h"')
   && panel.includes('<h3 id="route-panel-h" className="ro-head" tabIndex={-1} ref={roHead}>{r.id} · {r.origin} → {r.dest}</h3>'));
ok("⭐ SRC: the panel's two buttons: 'Beside the map' (only where full screen is offered) and a named close ×, its glyph drawn by CSS (.row-x)",
   panel.includes('{fullOk && <button type="button" className="btn-sec" data-route-beside={r.id} onClick={() => besideMap(r.id)}>Beside the map</button>}')
   && /<button type="button" className="row-x" data-route-close=\{r\.id\} aria-label=\{`Close \$\{r\.id\}`\} title=\{`Close \$\{r\.id\}`\}\s+onClick=\{\(\) => setOpenRow\(null\)\}><\/button>/.test(panel)
   && html.includes('.row-x::before{content:"×";}'));
ok("⭐ SRC: 'Beside the map' picks the route and enters the page's own full-screen layout (Q3)",
   html.includes("const besideMap = (id) => { if(selected !== id) selectRoute(id); roBeside.current = true; enterFull(); };"));
ok("⭐ SRC: the parts are written in the order they are read: the card, the figures, the settings in one column; the card, the settings, the figures when wide",
   ra.includes("{wide ? [partMain, partSide, partUnder] : [partMain, partUnder, partSide]}")
   && TRY(() => { const m = ra.indexOf("const partMain"), s = ra.indexOf("const partSide"), u = ra.indexOf("const partUnder");
                  const main = ra.slice(m, s), side = ra.slice(s, u), under = ra.slice(u);
                  return m > 0 && s > m && u > s && main.includes("<BestOption ") && !/RouteGates|HaulRoads|RouteRestrictions/.test(main)
                    && side.indexOf("{side}") > 0 && side.indexOf("{side}") < side.indexOf("<RouteGates") && side.indexOf("<RouteGates") < side.indexOf("<HaulRoads")
                    && side.indexOf("<HaulRoads") < side.indexOf("<RouteRestrictions")
                    && under.indexOf('data-bo-table="1"') > 0 && under.indexOf('data-bo-table="1"') < under.indexOf("data-busy-hours={o.alt}")
                    && under.indexOf("data-busy-hours={o.alt}") < under.indexOf("{diversions}"); }));
ok("⭐ SRC: the open route's detail is no longer a table row (no <tr>, no colSpan in RouteAnalysis or Near the route's box)",
   ra.length > 0 && !/<tr className="bg-slate-50\/70">|colSpan=\{colSpan\}/.test(ra) && html.includes("function NearDetails({ data, id }){")
   && !fnSrc("NearDetails").includes("<tr"));
ok("⭐ SRC: two columns from 1,100 px of the PANEL's own width (the card's 820 px cap, then the settings); the figures span both",
   html.includes("const [roBox, roWide, roEl] = useBoxWide(1100);") && panel.includes("<RouteAnalysis routeId={r.id} wide={roWide}")
   && html.includes(".ro-body{display:grid;grid-template-columns:minmax(0,1fr);column-gap:16px;}")
   && html.includes(".ro-body.ro-wide{grid-template-columns:minmax(0,820px) minmax(0,1fr);}")
   && html.includes(".ro-body.ro-wide>.ro-under{grid-column:1 / -1;}") && html.includes(".bo-card{container-type:inline-size;")
   && /\.bo-card\{[^}]*max-width:820px;\}/.test(html));
ok("⭐ SRC: on the page the settings column is Vehicles, then Near the route, then the analysis's own Gates, Haul roads and closures line",
   TRY(() => { const s = panel.slice(panel.indexOf("side={<>")); return s.indexOf("data-route-vehicles={r.id}") > 0
     && s.indexOf("data-route-vehicles={r.id}") < s.indexOf("<NearDetails data={nearData} id={r.id} />"); }));
ok("⭐ SRC: opening moves the page to the panel's top and focus to its heading; closing brings focus back to the row's ▶ button",
   html.includes("if(h){ try { h.focus({ preventScroll: true }); } catch(e){} }")
   && html.includes('el.scrollIntoView({ block: "start", behavior: calmMotion() ? "auto" : "smooth" })')
   && html.includes('const b = [...document.querySelectorAll("[data-route-tri]")].find(x => x.getAttribute("data-route-tri") === was);')
   && table.includes('<button type="button" data-route-tri={r.id}'));
ok("⭐ SRC: Q4: the card's 'Show Alt N on map' (and only it) also moves the page up to the map, never in full screen",
   ra.includes("onFocus={onShow || onFocus} onPromote={onPromote}") && panel.includes("onShow={(p, a) => { focusR(p, a); mapIntoView(); }}")
   && html.includes("if(full || !box || !box.scrollIntoView) return;") && html.includes("if(seen < 0.5){")
   && !between("<RouteFullDetails route=", "</>}").includes("onShow"));
ok("SRC: the card itself still calls the handler it is given, with its lorry and option (BestOption is not this branch's)",
   bo.includes("onClick={(e) => { e.stopPropagation(); onFocus(r.lorry, o.alt); }}>Show {o.label} on map</button>")
   // NARROWED 17 Nov 2026 (route option labels, Q5): the card can show another option, so Make primary names the
   // suggested one (`o.chosen`); the handler's call is as it was.
   && bo.includes('const canPromote = r.answer === "Suggested" && o && o.chosen && onPromote && !div;'));
ok("SRC: when Make primary shows is unchanged: the route picked in the list, an admin login (the page hands the card no handler otherwise)",
   panel.includes("onPromote={selected === r.id && canEdit ? promoteAlt : null}"));
ok("⭐ SRC: card 4: the haul road picker may shrink to its box and cuts a long name with '…'; the Attach button never shrinks",
   haul.includes('className="ro-pick border border-slate-200 rounded-lg px-2 py-1 text-[13px] bg-white disabled:opacity-40"')
   && html.includes(".ro-pick{min-width:0;flex:0 1 auto;max-width:100%;text-overflow:ellipsis;}")
   && haul.includes('<div className="flex items-center gap-2" style={{ minWidth: 0 }} data-haul-pick="1">')
   && haul.includes('style={{ background: "var(--haul-text)", flex: "none" }}>Attach</button>'));
ok("⭐ SRC: the settings' own tables scroll inside their boxes (a haul road attached, the closures list), never the column",
   haul.includes('<div className="overflow-x-auto mb-2" data-haul-table="1">')
   && /\{open && \(\s*\/\/[^\n]*\n\s*<div className="overflow-x-auto">\s*<table className="text-\[13px\] w-full mt-2">/.test(fnSrc("RouteRestrictions"))
   && html.includes(".ro-main,.ro-side,.ro-under{min-width:0;}"));
ok("⭐ SRC: full screen (cards 2 and 3): the chosen route's detail is the same analysis in one column, its diversions inside it, no table round it",
   det.includes('{analysis && <div data-route-full-analysis="1" style={{ minWidth: 0 }}>{analysis}</div>}') && !det.includes("<table")
   && !det.includes("{diversions") && !det.includes("diversions }") && /analysis=\{selected \? <RouteAnalysis routeId=\{selected\}\n[\s\S]{0,700}diversions=\{routeDiversions\(selected\)\} \/> : null\} \/>/.test(html)
   && !/analysis=\{selected \? <RouteAnalysis routeId=\{selected\}[^\n]*wide=/.test(html));
// ---------------- the Routes page in a DOM ----------------
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
w.mapboxgl = { accessToken: "", NavigationControl: function(){}, ScaleControl: function(){}, AttributionControl: function(){}, LngLatBounds: function(){ return { extend(){ return this; } }; },
  Popup: function(){ const p = { setLngLat: () => p, setHTML: () => p, setDOMContent: () => p, addTo: () => p, remove(){}, on: () => p }; return p; },
  Marker: function(){ const m = { setLngLat: () => m, addTo: () => m, remove(){}, getElement: () => w.document.createElement("div"), on: () => m, setDraggable: () => m }; return m; },
  Map: function(){
    const L = {}, S = {};
    const m = new Proxy({}, { get: (t, k) => {
      if (k === "on") return (ev, a, b) => { const fn = typeof a === "function" ? a : b; if (ev === "load") setTimeout(() => fn(), 0); return m; };
      if (k === "addControl") return (c) => { if (c && c.onAdd){ const n = c.onAdd(m); if (n) ctlBox.appendChild(n); } return m; };
      if (k === "getCanvas" || k === "getCanvasContainer" || k === "getContainer") return () => ({ style: {}, addEventListener(){}, removeEventListener(){} });
      if (k === "getZoom") return () => 10;
      if (k === "getCenter") return () => ({ lng: 0, lat: 0 });
      if (k === "getBounds") return () => ({ getWest: () => 0, getEast: () => 1, getSouth: () => 0, getNorth: () => 1 });
      if (k === "addLayer") return (l) => { L[l.id] = l; return m; };
      if (k === "getLayer") return (id) => L[id];
      if (k === "addSource") return (id, s) => { S[id] = { ...s, setData(d){ this.data = d; } }; return m; };
      if (k === "getSource") return (id) => S[id];
      if (k === "hasImage") return () => false;
      if (k === "getStyle") return () => ({ layers: [] });
      if (k === "queryRenderedFeatures") return () => [];
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

const respond = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 0)); });
const N = "Fictional scheme";
const P = "Artic Tipper (44t)";
const META = { routes: [], materials: ["Aggregate"], vehicles: [P], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } }, mapbox_token: "",
  vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [], ipts: [],
  tenant: { name: "Wolds Link", team_label: "Team", currency: "GBP", currency_symbol: "£", country: "GB", distance_unit: "mi", demo_notice: N } };
const LOCS = { type: "FeatureCollection", features: [["L001", "Kilby Ridge Quarry", -1.238, 52.561], ["L003", "Brook Pit", -0.752, 52.694]]
  .map(([id, name, lon, lat]) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { id, name, role: "origin", loc_type: "Quarry", supplies: ["Small aggregate"], receives: [] } })) };
const leg = (km, hr, alt) => ({ alt_index: alt || 0, baked: true, distance_km: km, duration_hr: hr, error: null, haul_zones: [], haul_recorded: true });
const STATUS = [
  { id: "R001", origin: "Kilby Ridge Quarry", dest: "Brook Pit", origin_id: "L001", dest_id: "L003", ipt: null, haul_roads: [], gate_blockers: [],
    profiles: { [P]: { baked: true, distance_km: 40, duration_hr: 0.75, legs: { loaded: [leg(40, 0.75), leg(44, 0.8, 1)], return: [leg(42, 0.5)] }, return_baked: true, alt_count: 2 } } },
  { id: "R002", origin: "Brook Pit", dest: "Kilby Ridge Quarry", origin_id: "L003", dest_id: "L001", ipt: null, haul_roads: [], gate_blockers: [],
    profiles: { [P]: { baked: true, distance_km: 12, duration_hr: 0.25, legs: { loaded: [leg(12, 0.25)] }, return_baked: false, alt_count: 1 } } },
];
const ROW = (alt) => ({ profile: P, alt_index: alt, loaded_km: 40 + alt, return_km: 42, return_estimated: false, loaded_hr: 0.75, return_hr: 0.5,
  load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 1.7, haul_speed_applied: false,
  trips_per_day: 5, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 56,
  lorry_day: { limited_by: "shift", trips_without_rules: 5, words: "5 a day", break_minutes: 45 } });
const DATA = { rows: [ROW(0), ROW(1)], planning: { shift_hours_per_day: 10, working_days_per_month: 22, shift_note: "" } };
// the rule's answer in route_best.evaluate()'s shape (live's R050 figures, 16 Nov; a fictional demo scheme)
const OPT = { alt: 1, label: "Alt 1", return_alt: 0, ruled_out: [], added_limits: [], searched: true, heads: {}, parts: {}, n5: false, chosen: true,
  counts: { km: 64.71, drive_min: 66.5, cycle_min: 100.5, trips: 5, co2_kg: 56, busy_min: {}, collisions: 39, goods: 1, left_turns: 9, cycle_meets: 4, cycle_beside_km: 0.17, places: 2 },
  pct: { left_turns: -10, cycle_meets: -33, cycle_beside_km: null, places: -71 },
  head_words: { people: "fewer", time: "quicker", busy: "not counted", carbon: "same" },
  part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "fewer" },
  sentences: ["Alt 1 had 39 collisions on it against 39 on the route in use, 2021–2025.",
              "Alt 1 had 1 collision involving a goods vehicle over 3.5 t on it against 4 on the route in use, 2021–2025."] };
const BEST = { day: "2026-11-17", checks: {}, route: { route: "R001", answer: "Suggested", option: "Alt 1", alt: 1,
  why: "4 min quicker a round trip, with 2 fewer cycle routes met.", trade: null, held_back: null, lorry: P, lorry_basis: "approved loads", other_lorries: [],
  in_use: { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } },
  counts_in_use: { km: 66.65, drive_min: 70, cycle_min: 104, trips: 5, co2_kg: 57.7, collisions: 39, goods: 4, left_turns: 10, cycle_meets: 6, cycle_beside_km: 0.24, places: 7, busy_min: {} },
  checks: { limits_held: true, community_all_options: true, collision_history: "current" }, options: [OPT] } };
const NEAR = { fetched_at: "2026-11-16", near_m: { schools: 250, bus_stops: 100 }, kinds: [{ key: "schools", label: "Schools" }, { key: "bus_stops", label: "Bus stops" }],
  routes: { R001: { schools: 6, bus_stops: 34 }, R002: { schools: 0, bus_stops: 2 } } };
const DIVS = { periods: [{ route_id: "R001", starts_on: "2027-12-01", ends_on: "2027-12-17", zones: ["Z9"], zone_names: ["Bridge works"], status: "no_way_round" }], busy: [] };
const GATES = [{ id: "G1", location_id: "L001", name: "South lane gate", direction: "egress", active: true },
               { id: "G2", location_id: "L003", name: "Weighbridge", direction: "both", active: true }];
const ZONES = [{ id: "Z7", kind: "haul_road", name: "A very long name for the temporary haul road across the north field", length_km: 1.9, speed_kph: 30 }];
const seen = [];
w.fetch = (url) => { const u = String(url); seen.push(u);
  if (/\/locations\/geojson$/.test(u)) return respond(LOCS);
  if (/\/routes\/status$/.test(u)) return respond(STATUS);
  if (/\/routes\/summary$/.test(u)) return respond({ here_configured: true, routes: 2, locations: 2 });
  if (/\/zones$/.test(u)) return respond({ zones: ZONES, haul_links: {} });
  if (/\/routes\/geojson\?/.test(u)) return respond({ type: "FeatureCollection", features: [] });
  if (/\/routes\/community-counts$/.test(u)) return respond(NEAR);
  if (/\/routes\/diversions$/.test(u)) return respond(DIVS);
  if (/\/api\/gates$/.test(u)) return respond({ gates: GATES });
  if (/\/routes\/R001\/analysis$/.test(u)) return respond(DATA);
  if (/\/routes\/R001\/best-option$/.test(u)) return respond(BEST);
  if (/\/routes\/R00\d\/haul-roads$/.test(u)) return respond({ links: [], plan: {} });
  if (/\/routes\/R00\d\/geometries$/.test(u)) return respond({ type: "FeatureCollection", features: [] });
  return new Promise(() => {}); };

// a desk window that can be narrowed, Chrome's full screen, the two boxes this branch measures, and a record of what moved
let desk = true; const mqOn = [];
const isDesk = (q) => /min-width: 1024px/.test(q);
w.matchMedia = (q) => ({ get matches(){ return isDesk(q) ? desk : false; }, media: q,
  addEventListener(t, f){ if (isDesk(q)) mqOn.push(f); }, removeEventListener(){}, addListener(f){ if (isDesk(q)) mqOn.push(f); }, removeListener(){} });
const doc = w.document, de = doc.documentElement; let fsEl = null;
Object.defineProperty(doc, "fullscreenElement", { configurable: true, get: () => fsEl });
de.requestFullscreen = () => { fsEl = de; return Promise.resolve(); };
doc.exitFullscreen = () => { fsEl = null; return Promise.resolve(); };
let PANEL_W = 0, MAP_BOX = { top: 100, bottom: 500, height: 400 };
const rect = (o) => Object.assign({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0 }, o);
w.Element.prototype.getBoundingClientRect = function(){
  if (this.hasAttribute && this.hasAttribute("data-route-panel")) return rect({ width: PANEL_W, right: PANEL_W });
  if (this.classList && this.classList.contains("dm-map")) return rect(MAP_BOX);
  return rect({});
};
const moved = [];
w.Element.prototype.scrollIntoView = function(o){ moved.push([this, o || {}]); };
// jsdom has no ResizeObserver: a stub that remembers what each one watches, so a growing panel can be played
const ROS = [];
w.ResizeObserver = function(cb){ this.cb = cb; this.els = []; this.observe = (el) => { this.els.push(el); if (!ROS.includes(this)) ROS.push(this); }; this.disconnect = () => { this.els = []; }; };
const grow = (el) => act(() => { ROS.filter(r => r.els.includes(el)).forEach(r => r.cb([])); });

(async () => {
  if (!loaded || typeof w.DataManagement !== "function") { ok("the Routes page (DataManagement) is defined", false); return finish(); }
  w.__ACCESS.info = { role: "admin", label: "Admin", via: "login", can_approve: true, ipt: null, name: "Ada", email: "ada@example.org" };
  const el = doc.createElement("div"); doc.body.appendChild(el); const root = w.ReactDOM.createRoot(el);
  const settle = async () => { for (let i = 0; i < 10; i++) await tick(); };
  const press = async (b) => { await act(async () => { b.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await settle(); };
  const q = (s) => el.querySelector(s), qa = (s) => [...el.querySelectorAll(s)];
  const tri = (id) => q(`button[data-route-tri="${id}"]`) || qa('button[aria-label="Show analysis"], button[aria-label="Hide analysis"]')[id === "R001" ? 0 : 1];
  const panelEl = () => q("section[data-route-panel]");
  const listRows = () => qa('table[data-tab-cards="routes"] > tbody > tr');
  const order = () => [...(q("[data-route-analysis-body]") || { children: [] }).children].map(c => c.getAttribute("data-ro")).join(">");
  try {
    await act(async () => { root.render(w.React.createElement(w.DataManagement, { meta: META, who: "t", subTab: "routes", onSubTab(){} })); });
    await settle();
    ok("DOM: the Routes list shows its two routes and no route is open", listRows().length === 2 && !panelEl() && !q(".bo-card"));

    // ---- open R001: one column (the panel reads 0 px wide here) ----
    moved.length = 0;
    await press(tri("R001"));
    const p = panelEl();
    ok("⭐ DOM: ▶ opens the route in a panel of its own: outside the list's table, after the list's card, named by its heading",
       !!p && p.getAttribute("data-route-panel") === "R001" && !p.closest("table")
       && !!(q('table[data-tab-cards="routes"]').compareDocumentPosition(p) & w.Node.DOCUMENT_POSITION_FOLLOWING)
       && p.getAttribute("aria-labelledby") === "route-panel-h" && TRY(() => q("#route-panel-h").textContent === "R001 · Kilby Ridge Quarry → Brook Pit"));
    ok("⭐ DOM R1: the panel's head adds three words to the screen ('Beside the map') beside a heading made of the route's own names",
       TRY(() => p.firstElementChild.textContent === "R001 · Kilby Ridge Quarry → Brook PitBeside the map"), TRY(() => p.firstElementChild.textContent));
    ok("⭐ DOM: the list stays rows only (still two rows), the open row's button says so and points at the panel",
       listRows().length === 2 && tri("R001").getAttribute("aria-expanded") === "true" && tri("R001").getAttribute("aria-controls") === "route-panel"
       && tri("R002").getAttribute("aria-expanded") === "false");
    ok("⭐ DOM: opening picks the route in the list (its row tinted, its lines read for the map)",
       TRY(() => q('[data-route-open="R001"]').getAttribute("aria-current") === "true" && /bg-blue-50/.test(q('[data-route-open="R001"]').closest("tr").className))
       && seen.some(u => /\/routes\/R001\/geometries$/.test(u)));
    ok("⭐ DOM: the page moves to the panel's top (block start) and focus goes to the panel's heading",
       !!p && moved.some(([n, o]) => n === p && o.block === "start") && doc.activeElement === q("#route-panel-h"));
    {
      // the panel grows as its reads arrive: the page is kept at its top, until the person does something
      const n0 = moved.filter(([n]) => n === p).length;
      await grow(p);
      const n1 = moved.filter(([n]) => n === p).length;
      await act(async () => { w.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
      await grow(p);
      const n2 = moved.filter(([n]) => n === p).length;
      ok("⭐ DOM: while the panel grows (its reads arriving) the page is kept at the panel's top; after a click, a key or a scroll it is left alone",
         n1 === n0 + 1 && n2 === n1, [n0, n1, n2].join(","));
    }
    ok("⭐ DOM: one column reads the card, then the figures, then the settings (Q2: the card first)", order() === "card>figures>settings"
       && TRY(() => p.getAttribute("data-route-panel-wide") === "0" && !q(".ro-body").classList.contains("ro-wide")), order());
    ok("⭐ DOM: the Best option card is the first thing in the panel's body, with its answer",
       TRY(() => { const first = q('[data-ro="card"]').firstElementChild; return first.classList.contains("bo-card") && first.getAttribute("data-best-option") === "Suggested"
                     && /Alt 1.?Suggested/.test(first.textContent.replace(/\s+/g, " ")); }));
    // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "Use Alt 1 as the main route" (it read "Make Alt 1 primary")
    ok("⭐ DOM: a Suggested card shows 'Use Alt 1 as the main route' at once (the route was picked by opening it; an admin login)",
       TRY(() => q("button[data-bo-promote]").textContent === "Use Alt 1 as the main route"));
    ok("⭐ DOM: the settings in order: Vehicles, Near the route, Gates, Temporary haul roads",
       TRY(() => { const t = q('[data-ro="settings"]'); const at = (s) => t.textContent.indexOf(s);
                   return !!t.querySelector('[data-route-vehicles="R001"]') && !!t.querySelector('[data-route-near="R001"]') && !!t.querySelector("[data-route-gates]")
                     && at("Vehicles") >= 0 && at("Vehicles") < at("Near R001") && at("Near R001") < at("Gates") && at("Gates") < at("Temporary haul roads on this route"); }),
       TRY(() => q('[data-ro="settings"]').textContent.slice(0, 300)));
    ok("⭐ DOM: the diversions sit with the figures, before the settings", TRY(() => !!q('[data-ro="figures"] [data-route-diversions="R001"]')
       && /Diversions/.test(q('[data-ro="figures"]').textContent) && !q('[data-ro="settings"] [data-route-diversions]')));
    ok("DOM: the haul road picker is named, carries the class that lets it shrink, and lists the long-named road",
       TRY(() => { const s = q("[data-haul-pick] select"); return s.classList.contains("ro-pick") && s.getAttribute("aria-label") === "Add a haul road" && s.options.length === 2 && s.options[0].textContent === "Add a haul road…"; }));
    await press(q("button[data-bo-all]"));
    ok("⭐ DOM: the figures table sits in a sideways-scrolling box the keyboard can reach, named 'All figures' (a narrow panel, full screen)",
       TRY(() => { const b = q('[data-ro="figures"] [data-bo-figures]'); return b.getAttribute("tabindex") === "0" && b.getAttribute("role") === "region"
                     && b.getAttribute("aria-label") === "All figures" && b.classList.contains("kb-scroll") && b.firstElementChild.matches("table[data-bo-table]"); }));
    ok("⭐ DOM: 'All figures' opens the options table with the figures (under both columns), not inside the card",
       TRY(() => !!q('[data-ro="figures"] table[data-bo-table]') && !q('.bo-card table') && q("button[data-bo-all]").getAttribute("aria-expanded") === "true"));

    // ---- Q4: Show Alt 1 on map ----
    MAP_BOX = { top: -620, bottom: -220, height: 400 }; moved.length = 0;
    await press(q("button[data-bo-show]"));
    const mapCard = q(".dm-map");
    ok("⭐ DOM Q4: with the map out of sight, the card's 'Show Alt 1 on map' moves the page up to the map",
       !!mapCard && moved.length === 1 && moved[0][0] === mapCard && moved[0][1].block === "start", String(moved.length));
    MAP_BOX = { top: 100, bottom: 500, height: 400 }; moved.length = 0;
    await press(q("button[data-bo-show]"));
    ok("DOM Q4: with the map in sight nothing moves", moved.length === 0);
    MAP_BOX = { top: -620, bottom: -220, height: 400 }; moved.length = 0;
    await press(q('[data-ro="figures"] table[data-bo-table] tbody tr:nth-child(2)'));
    ok("DOM Q4: a click on a row of the figures table shows that option and leaves the page where it is", moved.length === 0);
    MAP_BOX = { top: 100, bottom: 500, height: 400 };

    // ---- Make primary's rule is unchanged: another route picked in the list hides it ----
    await press(q('[data-route-open="R002"]'));
    ok("DOM: with another route picked in the list the open panel stays and 'Make primary' goes (the rule is unchanged)",
       !!panelEl() && panelEl().getAttribute("data-route-panel") === "R001" && !q("button[data-bo-promote]") && !!q("button[data-bo-show]"));
    await press(q('[data-route-open="R001"]'));

    // ---- close ----
    const x = q("button[data-route-close]");
    ok("⭐ DOM: the close button is named 'Close R001' and holds no text of its own (its × is CSS)",
       !!x && x.getAttribute("aria-label") === "Close R001" && x.textContent === "" && x.classList.contains("row-x"));
    if (x) await press(x);
    ok("⭐ DOM: closing removes the panel and brings focus back to the row's ▶ button", !panelEl() && doc.activeElement === q('button[data-route-tri="R001"]')
       && tri("R001").getAttribute("aria-expanded") === "false" && listRows().length === 2);
    await press(tri("R001")); await press(tri("R001"));
    ok("DOM: ▶ pressed again on the open row closes it too", !panelEl());

    // ---- wide: two columns from 1,100 px of panel ----
    PANEL_W = 1149; await press(tri("R001"));
    ok("⭐ DOM: at 1,149 px of panel (John's window) the settings come beside the card and the figures last, under both",
       TRY(() => panelEl().getAttribute("data-route-panel-wide") === "1" && q(".ro-body").classList.contains("ro-wide")) && order() === "card>settings>figures", order());
    await press(q("button[data-route-close]"));
    PANEL_W = 1099; await press(tri("R001"));
    ok("⭐ DOM: at 1,099 px one column, the card first", TRY(() => panelEl().getAttribute("data-route-panel-wide") === "0") && order() === "card>figures>settings", order());
    await press(q("button[data-route-close]"));

    // ---- Beside the map (Q3) ----
    PANEL_W = 1149; await press(tri("R002"));
    const beside = q("button[data-route-beside]");
    ok("⭐ DOM Q3: the panel carries 'Beside the map' at a desk", !!beside && beside.textContent === "Beside the map" && beside.getAttribute("data-route-beside") === "R002");
    if (beside) await press(beside);
    const g = q("[data-full]"), fd = q("[data-route-full-details]");
    ok("⭐ DOM Q3: it lays the page over the window (the list | the map | the chosen route) with THAT route chosen, focus on the chosen route",
       !!g && / sl-full$/.test(g.className) && fsEl === de && !!fd && /R002 · Brook Pit → Kilby Ridge Quarry/.test(fd.textContent)
       && TRY(() => q('[data-route-full-pick="R002"]').getAttribute("aria-current") === "true") && doc.activeElement === fd);
    await press(q('[data-route-full-pick="R001"]'));
    const fa = q("[data-route-full-analysis]");
    ok("⭐ DOM full screen: the chosen route's detail is one column, the card first, then figures and diversions, then Gates and Haul roads",
       !!fa && !fa.querySelector(":scope > table") && TRY(() => fa.firstElementChild.classList.contains("ro-body") && !fa.firstElementChild.classList.contains("ro-wide"))
       && order() === "card>figures>settings" && TRY(() => !!fa.querySelector('[data-ro="figures"] [data-route-diversions="R001"]')
       && !!fa.querySelector('[data-ro="settings"] [data-route-gates]') && !!fa.querySelector('[data-ro="settings"] select.ro-pick')), order());
    ok("DOM full screen: the page's Vehicles and Near boxes are not repeated there (the panel's head carries the lorry and Near the route)",
       !!fa && !fa.querySelector("[data-route-vehicles]") && !fa.querySelector("[data-route-near]") && /Near the route/.test(fd.textContent));
    MAP_BOX = { top: -620, bottom: -220, height: 400 }; moved.length = 0;
    if (fa && fa.querySelector("button[data-bo-show]")) await press(fa.querySelector("button[data-bo-show]"));
    ok("DOM Q4: in full screen 'Show Alt 1 on map' moves nothing (the map is beside the route)", !!fa && !!fa.querySelector("button[data-bo-show]") && moved.length === 0);
    MAP_BOX = { top: 100, bottom: 500, height: 400 };
    await press(ctlBox.querySelector("[data-full-ctl] button"));
    ok("DOM: leaving full screen brings the page back with the open route's panel still there", !q("[data-full]") && !!panelEl() && panelEl().getAttribute("data-route-panel") === "R002");

    // ---- under 1,024 px: no full screen, so no button; one column ----
    await act(async () => { desk = false; mqOn.forEach(f => f()); }); await settle();
    ok("⭐ DOM: under 1,024 px of window the panel has no 'Beside the map' (full screen is not offered there); the close stays",
       !!panelEl() && !q("button[data-route-beside]") && !!q("button[data-route-close]"));
    await act(async () => { desk = true; mqOn.forEach(f => f()); }); await settle();

    // ---- a planner's code: reads, no Make primary, no haul road picker ----
    await press(q("button[data-route-close]"));
    w.__ACCESS.info = { role: "planner", label: "Planner", via: "code", can_approve: true, ipt: null };
    await act(async () => { root.render(w.React.createElement(w.DataManagement, { meta: META, who: "p", subTab: "routes", onSubTab(){} })); }); await settle();
    await press(tri("R001"));
    ok("DOM: not an admin login: the panel opens and reads the same, with no 'Make primary' and no haul road picker",
       !!panelEl() && !!q('.bo-card[data-best-option="Suggested"]') && !q("button[data-bo-promote]") && !q("[data-haul-pick]"));
    await act(async () => { root.unmount(); });
  } catch (e) { ok("ROUTES CARD ROOM DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  el.remove();
  finish();
})();

function finish(){
  console.log(`ui_fix_routes_card_room.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
}
