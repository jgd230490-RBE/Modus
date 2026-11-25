/*
 * sim_full_screen.js — the Simulation's full screen (24 Nov 2026, branch claude/simulation-full-screen; John's "Yes, as
 * recommended" to Q1 to Q8 of notes\simulation-fullscreen-mockup-1124, then "Build it here").
 *
 *   1  source: the full screen is a CLASS on the one `.sim-play` (fixed over the window, z 70), never a second player or
 *      map; its rules use tokens only (no 999px, no slate grey, no stock blue); the type by the screen's height (the Big
 *      screen's clamp values); the Scenario band, the key rows and the small clock hidden in it; one filled primary (Play);
 *      the Big screen's SimWall untouched but for F2's comma; the guide's §17.1 says it in two sentences
 *   2  the page in a real DOM (jsdom): "Full screen" only on a desk from 1,024 px, never on the phone page, never on a
 *      month with no lines; entering puts the class on the same player, the SAME map element and ONE map, a bar with the
 *      DEMO tag, the headline's words, the figures line's start, "Planning view, not a record" and "Leave full screen";
 *      the page behind inert; focus on Play; Chrome's own full screen asked (stubbed here: jsdom has none)
 *   3  leaving by the button, by Esc, by Chrome leaving its own full screen, by the window narrowing under 1,024 px and by
 *      a month with no lines; each undoes the class and the inert, gives focus back to "Full screen" and lets Chrome's own
 *      go only if it was asked; Esc on a drop-down does not leave
 *   4  the clock's time and the playing state are the same before and after; the bar's words for a day that queues and
 *      one that does not
 *   5  the Key: a button at the map's corner, closed at first, opening the page's own key list; Esc closes the list first,
 *      then a second Esc leaves
 *   6  the map keeps its area: the bounds read before the size changes are fitted after with no animation, both ways
 *   7  F1: the map's five name layers by the look (Light ink on white; Dark near-white or a light shade on a near-black
 *      halo), again after a look change; F2: "Min lost" through grp ("1,776")
 *
 * NOT covered here: a real browser's layout (jsdom lays nothing out: the sizes, the map's real area and the pictures are
 * from local Chrome, notes\simulation-fullscreen-mockup-1124\built\); Chrome's own full screen (no session's click has a
 * user's activation, PR #219: requestFullscreen is a stub here, John's one click on live checks it); a touch screen; a
 * screen reader. Needs typescript, react, react-dom and jsdom through NODE_PATH; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts, JSDOM;
try { ts = require("typescript"); ({ JSDOM } = require("jsdom")); }
catch (e) { console.log("sim_full_screen.js: SKIPPED — typescript / jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();
const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const guide = read("frontend", "help", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const mapSrc = between("function SimMap({", "\nconst SIM_TL_LEFT");
const playerSrc = between("function SimPlayer({", "\nconst SimScenario");
const pageSrc = between("function SimulationPage({", "\n// the phone's Simulation:");
const wallSrc = between("function SimWall({", "\nfunction ");
const FIX = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", f), "utf8"));

// ---------------------------------------------------------------- 1. source
const cssA = html.indexOf(".sim-play.sim-full{"), cssB = html.indexOf(".sim-key-box li{", cssA);
const fullCss = cssA > 0 && cssB > cssA ? html.slice(cssA, html.indexOf("\n", cssB)) : "";
ok("⭐ FULL 1: one class on the one player: `.sim-play.sim-full` fixed over the whole window (inset 0, z 70) on the surface, a grid of bar, controls, map | side column, timeline",
   fullCss.startsWith(".sim-play.sim-full{position:fixed;inset:0;z-index:70;") && fullCss.includes("background:var(--surface)")
   && fullCss.includes('grid-template-areas:"bar bar" "ctl ctl" "map side" "tlh side" "tl side"') && fullCss.includes("clamp(280px,24vw,640px)")
   && fullCss.includes(".sim-full>.sim-grid{display:contents;}"), fullCss.slice(0, 200));
ok("FULL 1: in it the Scenario band, the key rows and the small clock are hidden; the map and the side column fill their cells",
   fullCss.includes(".sim-full>.sim-band,.sim-full .sim-key,.sim-full .sim-clock-small{display:none;}")
   && fullCss.includes(".sim-full .sim-main .sim-map{height:100%;min-height:0;max-height:none;}") && fullCss.includes(".sim-full .sim-side{grid-area:side;max-height:none;min-height:0;overflow:auto;}"));
ok("FULL 1 (Q4): the type by the screen's height, the Big screen's values: sentence 18 to 40 in the heading face, month line 13 to 24, clock 34 to 96, Now and the cards' heads 14 to 28, their th 13 to 22, notes 13 to 26, the timeline's head 13 to 22",
   fullCss.includes(".sim-full-head{font-family:var(--f-head);font-weight:600;font-size:clamp(18px,2.9vh,40px)") && fullCss.includes(".sim-full-sub{font-size:clamp(13px,1.9vh,24px)")
   && fullCss.includes(".sim-full .sim-clock{font-size:clamp(34px,7vh,96px);}") && fullCss.includes(".sim-full .sim-now,.sim-full .sim-card-h{font-size:clamp(14px,1.7vh,28px);}")
   && fullCss.includes(".sim-full .sim-now th{font-size:clamp(13px,1.35vh,22px);}") && fullCss.includes(".sim-full .sim-side .ct-note,.sim-full .sim-side .sim-lbl{font-size:clamp(13px,1.55vh,26px);}")
   && fullCss.includes(".sim-full .sim-tl-head{font-size:clamp(13px,1.4vh,22px);}"));
ok("FULL 1: the bar's two lines are cut with … before they wrap; the bar is a 1 px ink rule, no box (the own look's sections)",
   /\.sim-full-head\{[^}]*white-space:nowrap;overflow:hidden;text-overflow:ellipsis;/.test(fullCss) && /\.sim-full-sub\{[^}]*white-space:nowrap;overflow:hidden;text-overflow:ellipsis;/.test(fullCss)
   && fullCss.includes("border-bottom:1px solid var(--ink)") && !/\.sim-full>\.sim-full-bar\{[^}]*(box-shadow|background)/.test(fullCss));
ok("FULL 1: the Key button and its box sit at the map's TOP LEFT (10 / 10, the box at 46), clear of the logo and credit; the busy-hours note moves right of the button",
   /\.sim-key-btn\{position:absolute;left:10px;top:10px;/.test(fullCss) && /\.sim-key-box\{position:absolute;left:10px;top:46px;/.test(fullCss)
   && fullCss.includes(".sim-full .sim-busy-note{left:76px;"));
const SLATE = ["#64748B", "#475569", "#94A3B8", "#CBD5E1", "#E2E8F0", "#F1F5F9", "#334155", "#1E293B", "#0F172A"];
ok("⭐ FULL 1 (the own look): the new rules use tokens only — no 999px pill, no slate grey, no stock blue #2563EB, one 6 px corner",
   fullCss.length > 1500 && !fullCss.includes("999px") && !SLATE.some(c => fullCss.toUpperCase().includes(c)) && !/#2563EB/i.test(fullCss)
   && (fullCss.match(/border-radius:(\d+)px/g) || []).every(r => r === "border-radius:6px"), (fullCss.match(/#[0-9A-Fa-f]{3,6}\b/g) || []).join(","));
ok("⭐ FULL 1: the one player and the one map: the class goes on `.sim-play` (data-sim-full), ONE <SimMap> in the player taking `full`, no second player anywhere",
   playerSrc.includes('className={"sim-play" + (full ? " sim-full" : "")} data-sim-player="1" data-sim-full={full ? "1" : "0"}')
   && (playerSrc.match(/<SimMap /g) || []).length === 1 && playerSrc.includes("full={!!full} />") && (code.match(/<SimPlayer /g) || []).length === 1);
ok("FULL 1: one filled primary on the player (Play); the bar's Leave and the page's Full screen are outline buttons",
   (playerSrc.match(/className="btn-pri"/g) || []).length === 1 && playerSrc.includes('className="btn-sec" onClick={() => onLeave && onLeave()} data-sim-full-leave="1">Leave full screen</button>')
   && pageSrc.includes('className="btn-sec" onClick={enterFull} data-sim-full-btn="1">Full screen</button>') && !playerSrc.includes("var(--action)"));
ok("FULL 1: the bar's words are worked out ONCE on the page (headWords / dayWords) and the page's headline and figures line print the same",
   pageSrc.includes('<b>{headWords}</b> — the busiest point') && pageSrc.includes('<div className="sim-figs" data-sim-lead="1">{dayWords}{pourN')
   && pageSrc.includes("bar={{ head: headWords, sub: dayWords }}"));
ok("FULL 1: Chrome's own full screen is asked as a courtesy (fsAsked) and let go only if asked; Chrome leaving its own leaves this too",
   pageSrc.includes("fsAsked.current = true; document.documentElement.requestFullscreen().catch(() => { fsAsked.current = false; })")
   && pageSrc.includes("if(fsAsked.current && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen()")
   && pageSrc.includes('const onFs = () => { if(!document.fullscreenElement && fsAsked.current){ fsAsked.current = false; setFull(false); } };'));
ok("FULL 1: the Big screen (SimWall) is left as it was: no full-screen class in it, its map still `wall`, its Minutes lost now through grp (F2)",
   wallSrc.length > 500 && !wallSrc.includes("sim-full") && !wallSrc.includes("full={") && wallSrc.includes("<td className=\"num\">{grp(n.lost)}</td>") && !wallSrc.includes("Math.round(n.lost)"));
ok("FULL 1 (F2): no \"Min lost\" in the side column prints Math.round raw any more (Gates now, Stations now, the holding rows, the fold's minutes)",
   !playerSrc.includes("Math.round(n.lost)") && !playerSrc.includes("Math.round((f.heldLost") && playerSrc.includes("{grp((f.heldLost || {})[h.id] || 0)}")
   && playerSrc.includes("{grp(w.minutes_held || 0)}"));
const nameLayers = ["sim-haul-label", "sim-areas-label", "sim-areas-pt-label", "sim-wash-label", "sim-gate-labels"];
ok("⭐ FULL 1 (F1): the map's five name layers take their paint from simLabelPaint by the ground (mapGroundDark), the fixed #1E293B / white pairs gone",
   nameLayers.every(id => new RegExp(`id: "${id}"[^\\n]*\\n\\s*paint: (nm|simLabelPaint\\(dk, )`).test(mapSrc))
   && mapSrc.includes("const dk = mapGroundDark(styleNow), nm = simLabelPaint(dk);") && !mapSrc.includes('"text-color": "#1E293B"') && !mapSrc.includes('"text-color": "#5B21B6"'));
const p17 = (guide.match(/<p id="ug-sim-full">([\s\S]*?)<\/p>/) || ["", ""])[1];
ok("FULL 1: the guide's §17.1 says it: Full screen on a desk, the Key, Leave full screen or Esc, the clock kept",
   p17.includes("<strong>Full screen</strong>") && p17.includes("<strong>Key</strong>") && p17.includes("<strong>Leave full screen</strong> or Esc")
   && p17.includes("the clock where it was") && guide.indexOf('id="ug-sim-full"') > guide.indexOf('id="17-1-the-day-and-the-controls"')
   && guide.indexOf('id="ug-sim-full"') < guide.indexOf('id="17-2-the-scenario"'));

// ---------------------------------------------------------------- the app in jsdom
const src = code.replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const dom = new JSDOM(`<!doctype html><html data-theme="light"><head></head><body><div id="before">a page part</div><div id="root"></div><div id="after">another</div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require("react"); w.ReactDOM = require("react-dom/client");

// the window's width, stood in for: useMQ's matchMedia answers min-width / max-width against W and hears a change
let W = 1422; const mqs = [];
w.matchMedia = (q) => {
  const mn = /min-width:\s*([\d.]+)px/.exec(q), mx = /max-width:\s*([\d.]+)px/.exec(q);
  const mq = { media: q, ls: [], get matches(){ return (!mn || W >= +mn[1]) && (!mx || W <= +mx[1]); },
    addEventListener(t, f){ this.ls.push(f); }, removeEventListener(t, f){ this.ls = this.ls.filter(x => x !== f); }, addListener(f){ this.ls.push(f); }, removeListener(f){ this.ls = this.ls.filter(x => x !== f); } };
  mqs.push(mq); return mq;
};
// Chrome's own full screen, stood in for (jsdom has none)
let fsEl = null; const fsCalls = { ask: 0, exit: 0 };
Object.defineProperty(w.document, "fullscreenElement", { get: () => fsEl, configurable: true });
w.document.documentElement.requestFullscreen = () => { fsCalls.ask++; fsEl = w.document.documentElement; return Promise.resolve(); };
w.document.exitFullscreen = () => { fsCalls.exit++; fsEl = null; return Promise.resolve(); };

// the map, stood in for: what SimMap asks of Mapbox, recorded
const maps = [];
function FakeMap(opts){
  this.opts = opts; this.style = opts.style; this.layers = []; this.sources = {}; this.h = {}; this.fits = []; this.resizes = 0; this.styles = [];
  this.zoom = 9; this.center = { lng: -1, lat: 52, distanceTo: (o) => Math.hypot(o.lng + 1, o.lat - 52) * 111000 };
  this.bounds = { tag: "B0" }; maps.push(this);
}
FakeMap.prototype = {
  on(ev, cb){ (this.h[ev] = this.h[ev] || []).push(cb); return this; }, fire(ev){ (this.h[ev] || []).forEach(cb => cb({})); },
  addControl(){}, remove(){}, getCanvas(){ return { style: {} }; },
  addSource(id){ this.sources[id] = { data: null, setData(d){ this.data = d; } }; }, getSource(id){ return this.sources[id] || null; },
  addLayer(l){ this.layers.push(l); }, getLayer(id){ return this.layers.find(l => l.id === id) || null; }, setPaintProperty(){}, setFilter(){},
  setStyle(s){ this.styles.push(s); this.style = s; this.sources = {}; this.layers = []; },
  resize(){ this.resizes++; }, fitBounds(b, o){ this.fits.push({ b, o }); }, getBounds(){ return this.bounds; },
  getZoom(){ return this.zoom; }, getCenter(){ return this.center; },
};
function Bounds(){ this.n = 0; }
Bounds.prototype = { extend(){ this.n++; return this; }, isEmpty(){ return this.n === 0; } };
function Marker(){ this.el = null; }
Marker.prototype = { setLngLat(){ return this; }, addTo(){ return this; }, remove(){}, getElement(){ return this.el; } };
w.mapboxgl = { Map: FakeMap, LngLatBounds: Bounds, Marker, NavigationControl: function(){}, accessToken: "" };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const realRaf = w.requestAnimationFrame;
const act = w.React.act || require("react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const settle = (ms) => act(async () => { await sleep(ms || 0); });
const reply = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status, url: "", json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
const key = (target, k) => act(() => { target.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });

const SIM = FIX("sim_day.json");
const withLines = (d) => ({ ...d, legs: Object.fromEntries(Object.entries(d.legs).map(([k, v]) => [k, { ...v, coords: [[-1, 52], [-0.9, 52.1]],
  cum: [0, 13000], len_m: 13000, parts: [[0, 13000, 13000 / (v.minutes || 30), null, 0, v.minutes || 30]], plan_minutes: v.minutes || 30 }])) });
const DAY = withLines(SIM);
let dayReply = () => reply(200, SIM);
w.fetch = (url) => {
  const u = String(url);
  if (u.startsWith("/api/sim/day")) return dayReply(u);
  if (u.startsWith("/api/sim/busiest-month")) return reply(200, { busiest: null });
  return new Promise(() => {});
};
const metaMin = { routes: [], materials: [], vehicles: [], units: [], months: { start_year: 2026, count: 24 }, factors: { planning: { working_days_per_month: 21 } },
  mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [] };

let booted = true;
try { w.eval(CLOCK.shiftSource()); w.eval(js + "\nwindow.__TENANT = TENANT; window.__F = { grp, simLabelPaint, mapGroundDark };"); }
catch (e) { booted = false; fail.push("the page's script runs in jsdom  " + String(e && e.message).slice(0, 200)); }
const HAS = booted && typeof w.SimulationPage === "function";
ok("⭐ the page's SimulationPage runs in jsdom", HAS);

// F1's pairs, measured (WCAG ratio) on the dark basemap's land (#1F2024 or darker under a 0.92 near-black halo)
const lum = (hex) => { const c = hex.replace("#", "").match(/../g).map(x => parseInt(x, 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
if (HAS) {
  const P = w.__F.simLabelPaint;
  const dk = P(true), lt = P(false), dkHaul = P(true, "#5B21B6", "#C4B5FD"), dkWash = P(true, "#0E7490", "#67E8F9");
  ok("FULL 7 (F1): simLabelPaint — Light ink #1F2024 on white (a coloured name keeps its hue), Dark #F5F5F4 (or the light shade) on rgba(18,19,22,0.92), halo 1.5 both",
     lt["text-color"] === "#1F2024" && lt["text-halo-color"] === "#FFFFFF" && dk["text-color"] === "#F5F5F4" && dk["text-halo-color"] === "rgba(18,19,22,0.92)"
     && P(false, "#5B21B6", "#C4B5FD")["text-color"] === "#5B21B6" && dkHaul["text-color"] === "#C4B5FD" && dkWash["text-color"] === "#67E8F9"
     && [dk, lt, dkHaul, dkWash].every(p => p["text-halo-width"] === 1.5));
  const rs = { name: cr("#F5F5F4", "#121316"), haul: cr("#C4B5FD", "#121316"), wash: cr("#67E8F9", "#121316") };
  ok(`FULL 7 (F1): the Dark pairs read at 7:1 or better on the near-black halo — names ${rs.name.toFixed(2)}, haul road ${rs.haul.toFixed(2)}, wheel wash ${rs.wash.toFixed(2)}`,
     rs.name >= 7 && rs.haul >= 7 && rs.wash >= 7);
  ok("FULL 7 (F2): grp gives the comma: 4527 → \"4,527\", 1776.4 → \"1,776\"", w.__F.grp(4527) === "4,527" && w.__F.grp(1776.4) === "1,776");
}

(async () => {
  if (HAS) {
    w.__TENANT.demo_notice = "Fictional scheme";
    const root = w.ReactDOM.createRoot(w.document.getElementById("root"));
    const mount = async (props) => { await act(async () => { root.render(w.React.createElement(w.SimulationPage, { meta: metaMin, months: metaMin.months, ...props })); }); await settle(20); };
    const $ = (s) => w.document.querySelector(s);
    const player = () => $('[data-sim-player="1"]');
    const fullBtn = () => $('[data-sim-full-btn="1"]');
    const isFull = () => !!player() && player().classList.contains("sim-full") && player().getAttribute("data-sim-full") === "1";
    const inertOf = (el) => !!(el && el.closest("[inert]"));

    // ---- 2. where it is offered
    W = 1422;
    await mount({ initial: DAY });
    const m0 = maps[maps.length - 1];
    ok("⭐ FULL 2: on a desk (1,422 px) the page header carries \"Full screen\", an outline button BEFORE the tag, and the player is not full",
       !!fullBtn() && fullBtn().className === "btn-sec" && fullBtn().textContent === "Full screen" && !isFull()
       && !!fullBtn().closest('[data-guide="page-header"]') && (fullBtn().compareDocumentPosition($("[data-sim-tag]")) & w.Node.DOCUMENT_POSITION_FOLLOWING) > 0);
    ok("FULL 2: closed, nothing is inert, no bar, no Key button, the key rows under the map", !w.document.querySelector("[inert]") && !$("[data-sim-full-bar]") && !$("[data-sim-key-btn]") && !!$('[data-sim-key="1"]'));
    // the map ready (its style loaded), so the size change is measured
    await act(async () => { m0.fire("style.load"); }); await settle(10);
    const mapEl = $(".sim-map"), headTxt = ($('[data-sim-head="queue"] b') || {}).textContent || "", leadTxt = ($("[data-sim-lead]") || {}).textContent || "";
    // the clock moved off its start and playing, to see both kept
    const clock = () => ($("[data-sim-clock]") || {}).textContent;
    const jump = $('input[type=range][aria-label="Jump to a time of day"]');
    await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(jump, String(13 * 60 + 5)); jump.dispatchEvent(new w.Event("input", { bubbles: true })); });
    const queued = new Map(); let rafId = 0;
    w.requestAnimationFrame = (cb) => { queued.set(++rafId, cb); return rafId; }; w.cancelAnimationFrame = (id) => { queued.delete(id); };
    await click($("[data-sim-play]"));
    const before = { clock: clock(), word: $("[data-sim-play]").textContent };
    const fitsBefore = m0.fits.length, nMaps = maps.length;
    m0.bounds = { tag: "page-area" };

    // ---- enter
    await click(fullBtn()); await settle(10);
    ok("⭐ FULL 2: \"Full screen\" puts the class on the SAME player; the SAME map element and still ONE map; named \"Simulation, full screen\"",
       isFull() && $(".sim-map") === mapEl && maps.length === nMaps && player().getAttribute("role") === "region" && player().getAttribute("aria-label") === "Simulation, full screen");
    const bar = $('[data-sim-full-bar="1"]');
    ok("⭐ FULL 2: the bar, first in the player: DEMO · Fictional scheme, the headline's words, the figures line's start, the tag, Leave full screen",
       !!bar && player().firstElementChild === bar && ($("[data-sim-full-demo]") || {}).textContent === "DEMOFictional scheme"
       && ($("[data-sim-full-head]") || {}).textContent === headTxt && headTxt.length > 10
       && ($("[data-sim-full-sub]") || {}).textContent === "Sep 2026 · an average working day · 312 loads · 646 arrivals" && leadTxt.startsWith($("[data-sim-full-sub]").textContent)
       && bar.querySelector(".sim-tag").textContent === "Planning view, not a record" && ($("[data-sim-full-leave]") || {}).textContent === "Leave full screen", headTxt + " | " + leadTxt);
    ok("⭐ FULL 2: the page behind is inert (the header and the parts around the page), the player itself is not; focus is on Play",
       inertOf(fullBtn()) && inertOf($("#before")) && inertOf($("#after")) && !inertOf(player()) && w.document.activeElement === $("[data-sim-play]"));
    ok("FULL 2: Chrome's own full screen asked once (a stub here)", fsCalls.ask === 1 && fsEl === w.document.documentElement);
    ok("FULL 4: the clock's time and the playing state are the same in full screen", clock() === before.clock && $("[data-sim-play]").textContent === before.word && before.word === "Pause", JSON.stringify(before) + " " + clock());
    const fitIn = m0.fits.slice(fitsBefore);
    ok("⭐ FULL 6: going in the map keeps its area: the bounds read before the size changed fitted after, no animation, no padding",
       m0.resizes > 0 && fitIn.length === 1 && fitIn[0].b.tag === "page-area" && fitIn[0].o.duration === 0 && fitIn[0].o.padding === 0, JSON.stringify(fitIn));

    // ---- 5. the Key
    const kb = () => $("[data-sim-key-btn]");
    ok("⭐ FULL 5: a \"Key\" button on the map, closed at first (aria-expanded false), no box", !!kb() && kb().textContent === "Key" && kb().getAttribute("aria-expanded") === "false" && !$("[data-sim-key-box]") && !!kb().closest(".sim-map-wrap"));
    await click(kb());
    const rows = [...w.document.querySelectorAll('[data-sim-key="1"] li')].map(li => li.textContent), boxRows = [...w.document.querySelectorAll("[data-sim-key-box] li")].map(li => li.textContent);
    ok("FULL 5: open, the box lists the page's own key, row for row, and the button says so", kb().getAttribute("aria-expanded") === "true" && boxRows.length >= 6 && boxRows.join("|") === rows.join("|"), boxRows.join("|"));
    await key($("[data-sim-key-box]"), "Escape");
    ok("⭐ FULL 5: Esc closes the key box FIRST and full screen stays; focus back on Key", !$("[data-sim-key-box]") && isFull() && w.document.activeElement === kb());

    // Esc on a drop-down is the drop-down's
    const speed = $('select[aria-label="Playback speed"]');
    await key(speed, "Escape");
    ok("FULL 3: Esc on a drop-down (the speed) does not leave", isFull());

    // ---- 3. leave by Esc
    m0.bounds = { tag: "full-area" };
    const fitsMid = m0.fits.length;
    await key(w.document.body, "Escape"); await settle(10);
    ok("⭐ FULL 3: a second Esc leaves: no class, no bar, nothing inert, focus back on Full screen; Chrome's own let go (it was asked)",
       !isFull() && !$("[data-sim-full-bar]") && !w.document.querySelector("[inert]") && w.document.activeElement === fullBtn() && fsCalls.exit === 1 && fsEl === null);
    ok("FULL 4: out again, the clock's time and playing are as they were; the same map element", clock() === before.clock && $("[data-sim-play]").textContent === "Pause" && $(".sim-map") === mapEl);
    const fitOut = m0.fits.slice(fitsMid);
    ok("⭐ FULL 6: coming out, the area it showed BEFORE going in (nobody moved the map), no animation; the key box gone",
       fitOut.length === 1 && fitOut[0].b.tag === "page-area" && fitOut[0].o.duration === 0 && !$("[data-sim-key-btn]"), JSON.stringify(fitOut));
    await click($("[data-sim-play]"));   // pause
    w.requestAnimationFrame = realRaf;

    // leave by the button, after the map was moved in full screen: the full-screen area is kept
    await click(fullBtn()); await settle(10);
    m0.zoom = 11; m0.bounds = { tag: "moved-area" };
    const fitsB = m0.fits.length;
    await click($("[data-sim-full-leave]")); await settle(10);
    ok("⭐ FULL 3: \"Leave full screen\" leaves the same way (class, inert, focus) and lets Chrome's own go",
       !isFull() && !w.document.querySelector("[inert]") && w.document.activeElement === fullBtn() && fsCalls.exit === 2);
    ok("FULL 6: moved in full screen, coming out keeps the area on screen then (not the old one)", m0.fits.slice(fitsB).length === 1 && m0.fits.slice(fitsB)[0].b.tag === "moved-area");
    m0.zoom = 9;

    // leave by Chrome leaving its own full screen
    await click(fullBtn()); await settle(10);
    fsEl = null; await act(async () => { w.document.dispatchEvent(new w.Event("fullscreenchange")); }); await settle(10);
    ok("⭐ FULL 3: Chrome leaving its own full screen (Esc / F11 there) leaves this too, nothing more let go", !isFull() && !w.document.querySelector("[inert]") && fsCalls.exit === 2);
    // Chrome refused its own: the app's own still opens and leaves; nothing let go
    w.document.documentElement.requestFullscreen = () => { fsCalls.ask++; return Promise.reject(new Error("no")); };
    await click(fullBtn()); await settle(10);
    const askedNow = fsCalls.ask;
    await click($("[data-sim-full-leave]")); await settle(10);
    ok("FULL 3: when Chrome refuses its own full screen the app's still opens and leaves, and nothing is let go", askedNow === 5 - 1 && !isFull() && fsCalls.exit === 2, String(askedNow));
    w.document.documentElement.requestFullscreen = () => { fsCalls.ask++; fsEl = w.document.documentElement; return Promise.resolve(); };

    // leave by the window narrowing under 1,024 px; no button there
    await click(fullBtn()); await settle(10);
    W = 1000; await act(async () => { mqs.forEach(q => q.ls.forEach(f => f())); }); await settle(10);
    ok("⭐ FULL 3: the window narrowing under 1,024 px ends it, and the button is not offered there", !isFull() && !fullBtn() && !w.document.querySelector("[inert]"));
    W = 1422; await act(async () => { mqs.forEach(q => q.ls.forEach(f => f())); }); await settle(10);
    ok("FULL 2: back at 1,422 px the button is offered again", !!fullBtn());

    // a month with no lines ends it (the player leaves the screen)
    await click(fullBtn()); await settle(10);
    dayReply = () => reply(200, { ...SIM, loads: 0, gate_arrivals: 0, arrivals: [], gates: [], label: "Jan 2027", month: 5 });
    const msel = $('select[aria-label="Simulation month"]');
    await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(msel, "5"); msel.dispatchEvent(new w.Event("change", { bubbles: true })); });
    await settle(450);
    ok("⭐ FULL 3: a month with no lines ends it: no player, no button, nothing inert, the empty words on the page",
       !player() && !fullBtn() && !w.document.querySelector("[inert]") && $('[data-sim-state="none"]') !== null && fsEl === null);

    // ---- 4. the bar's words for a day where nothing queues
    const calm = { ...DAY, gates: DAY.gates.map(g => ({ ...g, most_waiting: 0, most_at: null })), sites: (DAY.sites || []).map(x => ({ ...x, stations: (x.stations || []).map(st => ({ ...st, most_waiting: 0, most_at: null })) })) };
    await act(async () => { root.unmount(); });
    const root2 = w.ReactDOM.createRoot(w.document.getElementById("root"));
    await act(async () => { root2.render(w.React.createElement(w.SimulationPage, { meta: metaMin, months: metaMin.months, initial: calm })); }); await settle(20);
    await click(fullBtn()); await settle(10);
    ok("⭐ FULL 4: a day where nothing queues: the bar says \"Nothing queues on this day (Sep 2026).\", as the page does",
       isFull() && ($("[data-sim-full-head]") || {}).textContent === "Nothing queues on this day (Sep 2026)." && !!$('[data-sim-head="none"]')
       && $('[data-sim-head="none"]').textContent.startsWith("Nothing queues on this day (Sep 2026)."));
    await click($("[data-sim-full-leave]")); await settle(10);

    // ---- 7. F2 in the side column: Harborough's minutes at the end of the day
    const jump2 = $('input[type=range][aria-label="Jump to a time of day"]');
    await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(jump2, String(DAY.window.end)); jump2.dispatchEvent(new w.Event("input", { bubbles: true })); });
    const g7 = $('[data-sim-now-gate="G007"]'), g7min = g7 ? g7.querySelectorAll("td")[2].textContent : "";
    ok("⭐ FULL 7 (F2): Gates now's Min lost has its comma at the end of the day (Harborough \"1,7xx\", never \"17xx\")", /^\d{1,3}(,\d{3})+$/.test(g7min), g7min);
    await act(async () => { root2.unmount(); });

    // ---- 2. the phone page: never
    const root3 = w.ReactDOM.createRoot(w.document.getElementById("root"));
    await act(async () => { root3.render(w.React.createElement(w.SimulationPage, { meta: metaMin, months: metaMin.months, initial: DAY, phone: true })); }); await settle(20);
    ok("⭐ FULL 2: the phone page never offers it (no button, no player)", !fullBtn() && !player());
    await act(async () => { root3.unmount(); });

    // ---- 7. F1 on the map, by the look, and again after a look change
    const paintOf = (mp, id) => (mp.layers.find(l => l.id === id) || {}).paint || {};
    const lightMap = m0;
    ok("FULL 7 (F1): on Light the map's names are ink on white", nameLayers.filter(id => id !== "sim-haul-label" && id !== "sim-wash-label").every(id => paintOf(lightMap, id)["text-color"] === "#1F2024" && paintOf(lightMap, id)["text-halo-color"] === "#FFFFFF")
       && paintOf(lightMap, "sim-haul-label")["text-color"] === "#5B21B6" && paintOf(lightMap, "sim-wash-label")["text-color"] === "#0E7490");
    w.document.documentElement.setAttribute("data-theme", "dark");
    const root4 = w.ReactDOM.createRoot(w.document.getElementById("root"));
    await act(async () => { root4.render(w.React.createElement(w.SimulationPage, { meta: metaMin, months: metaMin.months, initial: DAY })); }); await settle(20);
    const dm = maps[maps.length - 1];
    await act(async () => { dm.fire("style.load"); }); await settle(10);
    ok("⭐ FULL 7 (F1): opened on Dark, the gate, area and point names are near-white on a near-black halo; the haul road and the wheel wash their light shades",
       dm.style === "mapbox://styles/mapbox/dark-v11" && ["sim-gate-labels", "sim-areas-label", "sim-areas-pt-label"].every(id => paintOf(dm, id)["text-color"] === "#F5F5F4" && paintOf(dm, id)["text-halo-color"] === "rgba(18,19,22,0.92)")
       && paintOf(dm, "sim-haul-label")["text-color"] === "#C4B5FD" && paintOf(dm, "sim-wash-label")["text-color"] === "#67E8F9");
    await act(async () => { w.applyTheme("light", false); }); await settle(10);
    await act(async () => { dm.fire("style.load"); }); await settle(10);
    ok("FULL 7 (F1): a look change to Light gives the same map the light style and its names ink on white again",
       dm.styles[dm.styles.length - 1] === "mapbox://styles/mapbox/light-v11" && paintOf(dm, "sim-gate-labels")["text-color"] === "#1F2024" && paintOf(dm, "sim-gate-labels")["text-halo-color"] === "#FFFFFF");
    await act(async () => { root4.unmount(); });
  }
  console.log(fail.length ? fail.map(f => "  FAIL: " + f).join("\n") : "");
  console.log(`sim_full_screen.js: ${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.log("  FAIL: the run threw  " + (e && e.stack || e)); console.log(`sim_full_screen.js: ${pass} passed, ${fail.length + 1} failed`); process.exit(1); });
