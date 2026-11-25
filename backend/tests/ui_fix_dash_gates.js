/*
 * ui_fix_dash_gates.js — the Dashboard rethink, task A2 (24 Nov 2026; John: "G2 a gauge for each gate … the actual gauge
 * bar in the conditional colour rather than the notification at the bottom", version c of "Round 3" on
 * notes\dashboard-rethink-mockup-1124): Gate arrivals as a dial a gate. Its own file (parallel branches never meet at the
 * end of parse_frontend.js).
 *
 * Covers: every state the panel can be in (over, near, fine, no check-in time, no open time, set with no arrivals, no
 * gates, a failed read), the fullest six plus every flagged gate, two dials of one place, the phone's two across, the key
 * line, the verdict, the fold's name, Copy / Download kept, the dial's geometry, the saved picture, the CSS (tokens only)
 * and what went (the bullet chart, its marks plugin, the five-part key, the 21-word sentence, the phone list).
 * Not covered here: a real browser's layout (the pictures in notes\dashboard-rethink-mockup-1124\built\gates\ and the UI
 * audit do that), the live server.
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_dash_gates.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const code = src.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const GAF = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "gate_arrivals.json"), "utf8"));

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
// a 2-d context that records what is drawn (the saved picture's test)
const DRAWN = [];
w.HTMLCanvasElement.prototype.getContext = function(){
  const rec = (name) => (...a) => { DRAWN.push([name, ...a]); };
  return new Proxy({ measureText: (s) => ({ width: String(s).length * 6 }) }, {
    get(t, k){ if (k in t) return t[k]; return rec(k); },
    set(t, k, v){ DRAWN.push(["set", k, v]); return true; },
  });
};
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__G = { GA_DIALS, GA_DIAL_TOP, GA_DIAL, GA_NEAR, gaDialPt, gaDialArc, gaDialTick, gaDialTone, gaDialWord, gaDialsPicture };");
const X = w.__G;

const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const T = (el) => (el ? el.textContent : "").replace(/\s+/g, " ").trim();

// one gate as the server sends it
const g0 = GAF.gates[0];
const gate = (id, loc, name, perDay, pct, flag, extra) => ({ ...g0, gate_id: id, location_name: loc, gate_name: name, arrivals_per_day: perDay,
  capacity_pct: pct, capacity_per_day: pct == null ? null : Math.round(perDay * 100 / pct), flag, no_open_time: false, ...(extra || {}) });
const panel = (gates, extra) => ({ ga: { ...GAF, gates }, err: false, month: GAF.month, months: { start_year: 2026, count: 60 }, onMonth(){}, ...(extra || {}) });

(async () => {
  try {
    // ---- every state --------------------------------------------------------------------------------------------
    const mixed = [
      gate("A1", "Kilby Ridge Quarry", "Weighbridge (in)", 164, 109, "red"),
      gate("A2", "Harborough Compound", "A6 entrance (in)", 31.5, 95, "amber"),
      gate("A3", "Melton Compound", "North weighbridge (in)", 27.9, 62, null),
      gate("A4", "North stockpile", "Stockpile gate", 9, null, null, { gate_minutes: null }),
      gate("A5", "Shut yard", "Yard gate", 4, null, null, { no_open_time: true }),
      gate("A6", "Quiet gate", "Nothing", 0, 0, null),
    ];
    const m = mount(w.GateArrivalsPanel, panel(mixed));
    const dial = (id) => m.el.querySelector(`[data-ga-li="${id}"]`);
    ok("STATES: one dial a gate with arrivals (the gate with none left out), fullest first, no-capacity gates last (busiest first)",
       [...m.el.querySelectorAll("[data-ga-li]")].map(e => e.getAttribute("data-ga-li")).join("|") === "A1|A2|A3|A4|A5",
       [...m.el.querySelectorAll("[data-ga-li]")].map(e => e.getAttribute("data-ga-li")).join("|"));
    ok("STATES: over capacity — the bad tone, the arc, both marks, '109 %', '164.0 a day of 150', 'Over capacity' with the status square",
       dial("A1").getAttribute("data-ga-tone") === "bad" && !!dial("A1").querySelector(".ga-d-arc") && !!dial("A1").querySelector(".ga-d-near") && !!dial("A1").querySelector(".ga-d-cap")
       && T(dial("A1").querySelector(".ga-d-pct")) === "109 %" && T(dial("A1").querySelector(".ga-d-fig")) === "164.0 a day of 150"
       && dial("A1").querySelector('[data-row-status="bad"]') && T(dial("A1")).includes("Over capacity"), T(dial("A1")));
    ok("STATES: 85 to 100 % — the warn tone and 'Queue likely' with the diamond",
       dial("A2").getAttribute("data-ga-tone") === "warn" && !!dial("A2").querySelector('[data-row-status="warn"]') && T(dial("A2")).includes("Queue likely") && T(dial("A2")).includes("95 %"));
    ok("STATES: a fine gate — the ok tone on the arc and NO word, no status shape (John's version c: a word only where a gate is not fine)",
       dial("A3").getAttribute("data-ga-tone") === "ok" && !dial("A3").querySelector("[data-row-status]") && T(dial("A3").querySelector(".ga-d-pct")) === "62 %" && T(dial("A3").querySelector(".ga-d-name")) === "Melton Compound"
       && T(dial("A3").querySelector(".ga-d-fig")) === "27.9 a day of 45" && dial("A3").children.length === 3, T(dial("A3")));
    ok("STATES: no check-in time typed — the empty track only (no arc, no marks), '—' in the middle, the ring and 'No check-in time typed', no 'of'",
       dial("A4").getAttribute("data-ga-tone") === "none" && !dial("A4").querySelector(".ga-d-arc") && !dial("A4").querySelector(".ga-d-near") && !dial("A4").querySelector(".ga-d-cap")
       && !!dial("A4").querySelector(".ga-d-track") && T(dial("A4").querySelector(".ga-d-pct")) === "—" && !!dial("A4").querySelector('[data-row-status="none"]')
       && T(dial("A4")).includes("No check-in time typed") && T(dial("A4").querySelector(".ga-d-fig")) === "9.0 a day", T(dial("A4")));
    ok("STATES: no open time (the bands and shut times cover its hours) — the same empty dial, the word 'No open time'",
       dial("A5").getAttribute("data-ga-tone") === "none" && T(dial("A5")).includes("No open time") && !T(dial("A5")).includes("check-in"));
    ok("STATES: the verdict line counts the red gates first, with the bad shape; the key line names the two marks; no capacity words anywhere else",
       T(m.el.querySelector(".ga-head-v")) === "1 gate over capacity" && m.el.querySelector("[data-ga-verdict]").getAttribute("data-ga-verdict") === "bad"
       && [...m.el.querySelectorAll(".ga-key > span")].map(T).join("|") === "85 %: queue likely|capacity" && !!m.el.querySelector(".ga-key-near") && !!m.el.querySelector(".ga-key-cap"));
    ok("STATES: the fold keeps every gate (the gate with none too), so it is 'All 6 gates' when a gate has no dial",
       m.el.querySelectorAll("[data-ga-gate]").length === 6 && T(m.el.querySelector("[data-ga-table] summary")).startsWith("All 6 gates: the gap, the check-in time, each "));
    ok("STATES: each dial is one picture with a name a reader hears (the gate and its share)",
       dial("A1").querySelector("svg").getAttribute("role") === "img" && dial("A1").querySelector("svg").getAttribute("aria-label") === "Kilby Ridge Quarry, Weighbridge (in): 109 % of capacity"
       && dial("A4").querySelector("svg").getAttribute("aria-label") === "North stockpile, Stockpile gate: no capacity");
    m.done();

    const near = mount(w.GateArrivalsPanel, panel([gate("N1", "One", "g", 30, 90, "amber"), gate("N2", "Two", "g", 20, 88, "amber"), gate("N3", "Three", "g", 10, 40, null)]));
    ok("STATES: no red gate — the verdict names the near ones with the warn shape",
       T(near.el.querySelector(".ga-head-v")) === "2 gates near capacity: queue likely" && near.el.querySelector("[data-ga-verdict]").getAttribute("data-ga-verdict") === "warn");
    near.done();
    const calm = mount(w.GateArrivalsPanel, panel([gate("C1", "One", "g", 30, 60, null), gate("C2", "Two", "g", 20, 30, null)]));
    ok("STATES: a quiet month — 'Every gate within its capacity' with the ok dot; no dial carries a word",
       T(calm.el.querySelector(".ga-head-v")) === "Every gate within its capacity" && calm.el.querySelector("[data-ga-verdict]").getAttribute("data-ga-verdict") === "ok"
       && !calm.el.querySelector(".ga-dial [data-row-status]"));
    ok("STATES: every gate has a dial — the fold is 'Gate by gate'", T(calm.el.querySelector("[data-ga-table] summary")).startsWith("Gate by gate: the gap, the check-in time, each "));
    calm.done();
    const quiet = mount(w.GateArrivalsPanel, panel([gate("Q1", "One", "g", 0, 0, null), gate("Q2", "Two", "g", 0, 0, null)]));
    ok("STATES: gates but no arrivals this month — no dials, no picture buttons; the ring and 'No arrivals at a gate in <month>'; the fold still lists the gates",
       !quiet.el.querySelector("[data-ga-dials]") && !quiet.el.querySelector(".ct-tools, [data-chart-tools]") && T(quiet.el.querySelector("[data-ga-verdict]")) === `No arrivals at a gate in ${GAF.label}`
       && quiet.el.querySelector("[data-ga-verdict]").getAttribute("data-ga-verdict") === "none" && quiet.el.querySelectorAll("[data-ga-gate]").length === 2, T(quiet.el));
    quiet.done();
    const none = mount(w.GateArrivalsPanel, panel([], { sited: "Kilby Ridge Quarry" }));
    ok("STATES: no gates at the sites picked — the empty state says so and points to the month or more sites; no dials, no fold",
       none.el.querySelector('[data-gate-arrivals="none"]') && T(none.el).includes(`No gates at these sites in ${GAF.label}`) && T(none.el).includes("Pick another month or more sites.")
       && !none.el.querySelector("[data-ga-dials]") && !none.el.querySelector("[data-ga-table]"));
    none.done();
    const bad = mount(w.GateArrivalsPanel, { ga: null, err: true, month: 1, months: { start_year: 2026, count: 60 }, onMonth(){} });
    ok("STATES: the read failing — one plain sentence, nothing else", T(bad.el) === "The gate arrivals did not load." && !!bad.el.querySelector('[data-gate-arrivals="error"]'));
    bad.done();

    // ---- how many dials: the fullest six, and every flagged gate besides --------------------------------------------
    const nine = [120, 110, 100, 98, 95, 92, 90, 88, 30].map((p, i) => gate("S" + i, "Site " + i, "g", 10 + i, p, p > 100 ? "red" : p >= 85 ? "amber" : null));
    const n9 = mount(w.GateArrivalsPanel, panel(nine));
    ok("SIX: the fullest six on one line, and every other gate the server flags (85 % or more) too; a fine seventh is in the fold, which is then 'All 9 gates'",
       n9.el.querySelectorAll("[data-ga-li]").length === 8 && !n9.el.querySelector('[data-ga-li="S8"]')
       && T(n9.el.querySelector("[data-ga-table] summary")).startsWith("All 9 gates: the gap, the check-in time, each "));
    n9.done();
    const ten = [80, 70, 60, 50, 40, 30, 20, 10, 5, 2].map((p, i) => gate("T" + i, "Site " + i, "g", 10 + i, p, null));
    const n10 = mount(w.GateArrivalsPanel, panel(ten));
    ok("SIX: ten fine gates — exactly six dials, the fullest; the fold 'All 10 gates'",
       [...n10.el.querySelectorAll("[data-ga-li]")].map(e => e.getAttribute("data-ga-li")).join("|") === "T0|T1|T2|T3|T4|T5" && T(n10.el.querySelector("[data-ga-table] summary")).startsWith("All 10 gates"));
    n10.done();
    ok("SIX: GA_DIALS is 6 and the ring ends at 125 % of the gate's own capacity", X.GA_DIALS === 6 && X.GA_DIAL_TOP === 125 && X.GA_NEAR === 85);

    // ---- two dials at one place print the gate's name ------------------------------------------------------------
    const two = mount(w.GateArrivalsPanel, panel([gate("D1", "Melton Compound", "North (in)", 30, 70, null), gate("D2", "Melton Compound", "South (in)", 20, 50, null), gate("D3", "Kilby", "Weighbridge", 10, 40, null)]));
    ok("NAMES: two dials of one place print each gate's name; a place with one dial prints the place; the whole name is the title",
       T(two.el.querySelector('[data-ga-li="D1"] .ga-d-name')) === "North (in)" && T(two.el.querySelector('[data-ga-li="D2"] .ga-d-name')) === "South (in)"
       && T(two.el.querySelector('[data-ga-li="D3"] .ga-d-name')) === "Kilby" && two.el.querySelector('[data-ga-li="D1"] .ga-d-name').getAttribute("title") === "Melton Compound, North (in)");
    two.done();

    // ---- the phone two across; the desk six ------------------------------------------------------------------------
    const ph = mount(w.GateArrivalsPanel, panel(mixed, { phone: true }));
    ok("PHONE: the same dials, the phone class (two across); the verdict and the key line too",
       ph.el.querySelector("ul.ga-dials").classList.contains("ga-dials-phone") && ph.el.querySelectorAll("[data-ga-li]").length === 5 && !!ph.el.querySelector(".ga-key") && !!ph.el.querySelector("[data-ga-verdict]"));
    ph.done();

    // ---- Copy and Download kept: the picture is drawn from the dials ------------------------------------------------
    ok("PICTURE: the dials keep Copy and Download in their title row (ChartTools inline), titled and scoped by the month and the sites; only when there are dials",
       code.includes('{dialsOn && <ChartTools inline title={picTitle} scope={[ga.label, sited || null]} getPlot={async () => gaDialsPicture(shown, dialName)} />}')
       && code.includes('const picTitle = "Gate arrivals: each gate against its capacity";') && code.includes("const dialsOn = state === \"set\" && rowsC.length > 0;"));
    DRAWN.length = 0;
    const rows = [{ g: mixed[0], cap: 150, pct: 109, over: true, near: false }, { g: mixed[1], cap: 33, pct: 95, over: false, near: true },
                  { g: mixed[2], cap: 45, pct: 62, over: false, near: false }, { g: mixed[3], cap: null, pct: null, over: false, near: false }];
    const pic = X.gaDialsPicture(rows, r => r.g.location_name);
    const texts = DRAWN.filter(d => d[0] === "fillText").map(d => d[1]);
    ok("PICTURE: the saved picture is a dial a gate, four across for four gates, one row; each prints its share, its name, 'N a day of C' and the same word as the screen",
       pic && pic.w === 4 * 172 && pic.h === Math.round(66 * 1.25) + 66 && texts.includes("109 %") && texts.includes("—") && texts.includes("Kilby Ridge Quarry")
       && texts.includes("164.0 a day of 150") && texts.includes("9.0 a day") && texts.includes("Over capacity") && texts.includes("Queue likely") && texts.includes("No check-in time typed")
       && !texts.some(t => /undefined|NaN/.test(t)), JSON.stringify(texts));
    const p7 = X.gaDialsPicture(nine.slice(0, 7).map(g => ({ g, cap: 10, pct: g.capacity_pct, over: g.flag === "red", near: g.flag === "amber" })), r => r.g.location_name);
    ok("PICTURE: seven dials wrap to two rows of six across", p7.w === 6 * 172 && p7.h === 2 * (Math.round(66 * 1.25) + 66));

    // ---- geometry ----------------------------------------------------------------------------------------------------
    const near1 = (a, b) => Math.abs(a - b) < 0.11;
    const [x0, y0] = X.gaDialPt(0, X.GA_DIAL.r), [xt, yt] = X.gaDialPt(62.5, X.GA_DIAL.r), [x1, y1] = X.gaDialPt(125, X.GA_DIAL.r), [xo, yo] = X.gaDialPt(400, X.GA_DIAL.r);
    ok("GEOMETRY: a half ring left to right — 0 % at the left end, half of 125 % at the top, 125 % at the right end; a share past 125 % stops at the end",
       near1(x0, 15) && near1(y0, 58) && near1(xt, 60) && near1(yt, 13) && near1(x1, 105) && near1(y1, 58) && xo === x1 && yo === y1, [x0, y0, xt, yt, x1, y1].join(","));
    const cap = X.gaDialTick(100), nr = X.gaDialTick(85);
    ok("GEOMETRY: the capacity mark crosses the ring at 100/125 of the way round (inside to outside), the 85 % mark before it",
       near1(Math.hypot(cap.x1 - 60, cap.y1 - 58), 38) && near1(Math.hypot(cap.x2 - 60, cap.y2 - 58), 52) && cap.x1 > 60 && nr.x1 < cap.x1 && nr.y1 < cap.y1);
    ok("GEOMETRY: an arc is one SVG arc from the left end; a share of 0 still draws a sliver, so the track shows where it starts",
       /^M15 58 A45 45 0 0 1 [\d.]+ [\d.]+$/.test(X.gaDialArc(50)) && X.gaDialArc(0) !== "M15 58 A45 45 0 0 1 15 58");
    ok("GEOMETRY: the tone is the server's flag, never a share worked out here; the word too",
       X.gaDialTone({ cap: 10, over: true }) === "bad" && X.gaDialTone({ cap: 10, near: true }) === "warn" && X.gaDialTone({ cap: 10 }) === "ok" && X.gaDialTone({ cap: null, over: true }) === "none"
       && X.gaDialWord({ cap: 10, over: false, near: false, g: {} }) === null && X.gaDialWord({ cap: null, g: { no_open_time: true } }) === "No open time");

    // ---- the CSS: tokens only, sizes ---------------------------------------------------------------------------------
    const css = (sel) => { const mm = html.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\{([^}]*)\\}")); return mm ? mm[1] : ""; };
    const gaCss = (html.match(/\.ga-(d|dial|dials|key)[\w-]*[^{]*\{[^}]*\}/g) || []).join("\n");
    ok("CSS: the arc's colours are the status tokens (green / gold / red), the track --line-2, the marks --muted dashed and --ink solid; no colour written out",
       css(".ga-d-ok .ga-d-arc") === "stroke:var(--green);" && css(".ga-d-warn .ga-d-arc") === "stroke:var(--gold);" && css(".ga-d-bad .ga-d-arc") === "stroke:var(--red);"
       && /stroke:var\(--line-2\)/.test(css(".ga-d-track")) && /stroke:var\(--muted\)/.test(css(".ga-d-near")) && /stroke-dasharray/.test(css(".ga-d-near")) && /stroke:var\(--ink\)/.test(css(".ga-d-cap"))
       && gaCss.length > 200 && !/#[0-9A-Fa-f]{3,8}\b|rgba?\(/.test(gaCss), gaCss.slice(0, 200));
    ok("CSS: six across on a desk, three on a tablet, two on a phone; type 12 px or more; the name cut with an ellipsis (whole in its title)",
       /grid-template-columns:repeat\(6,/.test(css(".ga-dials")) && /repeat\(3,/.test(html.match(/@media \(max-width:1024px\)[^@]*\.ga-dials\{[^}]*\}/) ? html.match(/@media \(max-width:1024px\)[^@]*\.ga-dials\{[^}]*\}/)[0] : "")
       && /repeat\(2,/.test(css(".ga-dials-phone")) && /font-size:12px/.test(css(".ga-d-name")) && /font-size:12px/.test(css(".ga-d-fig")) && /text-overflow:ellipsis/.test(css(".ga-d-name"))
       && !/font-size:(9|10|11)px/.test(gaCss));

    // ---- what went ---------------------------------------------------------------------------------------------------
    ok("GONE: the bullet chart, its capacity-marks plugin, its tooltip and its config",
       !code.includes("const gaCfg") && !code.includes("gaCapMarks") && !code.includes("capMarks") && !html.includes('data-ga-chart="1"') && !code.includes("No open time: the bands and shut times cover its hours"));
    ok("GONE: the five-part colour key and the 21-word sentence under the title (its sense is in the \"i\", 30 words)",
       !/\.ga-key-(bar|track|red|gold|none)\{/.test(html) && !html.includes('className="ga-key-bar"') && !code.includes("lorries a day at each gate, all {TEAMS()")
       && !code.includes("{ga.label}: lorries a day at each gate")
       && code.includes('"dash.gates": { title: "Gate arrivals", text: "Each gate\'s lorries a day, every team together, spread evenly over its open hours, against what it can check in. Queue likely from 85 %; over capacity past 100 %."'));
    const infoWords = "Each gate's lorries a day, every team together, spread evenly over its open hours, against what it can check in. Queue likely from 85 %; over capacity past 100 %.".split(/\s+/).length;
    ok("GONE: the \"i\" is 30 words at most", infoWords <= 30, String(infoWords));
    ok("GONE: the phone's plain list and its CSS (the Look-ahead's peak bar .ga-pbar stays: GatesWeek draws it)",
       !code.includes("data-ga-list") && !/\.ga-list\{|\.ga-li-(name|fig)\{/.test(html) && html.includes(".ga-pbar{") && code.includes('<div className="ga-pbar" aria-hidden="true">'));
    ok("KEPT: the month picker, 'Next queue likely … Show', the closed gate's and busiest hour's lines, the fold's table unchanged",
       code.includes('<select className="ga-sel" value={month} onChange={e => onMonth(+e.target.value)} aria-label="Month">') && code.includes("Next queue likely: {nextQ.label}")
       && code.includes('<table className="ga-table rd-table" data-rd-table="gates">') && code.includes("const gaBusyWords = (b) =>"));
  } catch (e) {
    fail.push("harness crashed: " + (e && e.stack || e));
  }
  if (fail.length) for (const f of fail) console.log("  FAIL: " + f);
  console.log(`ui_fix_dash_gates.js: ${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
