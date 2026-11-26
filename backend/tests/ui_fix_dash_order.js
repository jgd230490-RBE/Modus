/*
 * ui_fix_dash_order.js — the Dashboard rethink, task B (25 Nov 2026; John's "Yes, as recommended" to Q8 to Q10 and Q14 of
 * notes\dashboard-rethink-mockup-1124): the page's order, the three key charts on one line with this month marked, the
 * carbon target as four figures, and the header's count line only with a filter chip. Its own file (parallel branches
 * never meet at the end of parse_frontend.js).
 *
 * Covers: the working view's order (six figures, the three key charts, Gate arrivals, the carbon target, Cost over time
 * and Top routes, the folds), the charts' rows by their own width, Vehicles needed out of "More charts" and the fold's
 * name, this month's mark (the plugin, its wiring through fitChartConfig, the copied picture's light ink, the three key
 * charts only and never the big screen), the series names kept on the big screen only, the count line, and the carbon
 * section in every state (set over / under / on, a fixed cap, a team's share, a team with no share, decisions that no
 * longer fit, none set, a failed read, loading with and without the transport figure, scheme-wide), with its two "i"
 * boxes opened in a real DOM, and what went ("card above", the old sentences, a source name, CO₂ in the block).
 * Not covered here: a real browser's layout (the pictures in notes\dashboard-rethink-mockup-1124\built\order\ and the UI
 * audit do that), the live server.
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_dash_order.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const code = src.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const CTX = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "carbon_target.json"), "utf8"));

// ---------------------------------------------------------------------------------------------- 1. the source
const dash = (() => { const i = code.indexOf("\nfunction Dashboard("); return code.slice(i, code.indexOf("\n}\n", i) + 3); })();
const at = (s) => dash.indexOf(s);
const P = {
  figures: at('<div className="dash-cards-box"><div className="dash-cards" data-guide="dash-figures">'),
  charts1: at('<div className="dash-charts-box"><div className="dash-charts" data-dash-charts="1">'),
  gates: at("<GateArrivalsPanel"),
  carbon: at("<CarbonTargetStrip ct={ct}"),
  charts2: at('<div className="dash-charts-box"><div className="dash-charts2" data-dash-charts="2">'),
  more: at('<details className="dash-more"'),
};
ok("⭐ ORDER (Q8): the six figures, the three key charts, Gate arrivals, the carbon target, Cost over time and Top routes, then the folds",
   Object.values(P).every(v => v > 0) && P.figures < P.charts1 && P.charts1 < P.gates && P.gates < P.carbon && P.carbon < P.charts2 && P.charts2 < P.more,
   JSON.stringify(P));
const row1 = dash.slice(P.charts1, dash.indexOf("</div></div>}", P.charts1));
const row2 = dash.slice(P.charts2, dash.indexOf("</div></div>}", P.charts2));
const ci = (s, c) => s.indexOf(`<div className="card p-4 chart-card ${c}">`);
ok("⭐ ...the first row is Material demand, Delivered against plan and Vehicles needed, in that order, and nothing else",
   ci(row1, "c-demand") > 0 && ci(row1, "c-demand") < ci(row1, "c-progress") && ci(row1, "c-progress") < ci(row1, "c-fleet")
   && (row1.match(/chart-card c-/g) || []).length === 3 && row1.includes("<ChartCanvas config={fleetCfg}"));
ok("...the second row is Cost over time and Top routes, after the carbon target",
   ci(row2, "c-cost") > 0 && ci(row2, "c-cost") < ci(row2, "c-top") && (row2.match(/chart-card c-/g) || []).length === 2);
ok("...both rows are drawn only with lines in view (the empty message says one thing instead)",
   dash.includes('{!D.empty && <div className="dash-charts-box"><div className="dash-charts" data-dash-charts="1">')
   && dash.includes('{!D.empty && <div className="dash-charts-box"><div className="dash-charts2" data-dash-charts="2">'));
const moreAt = dash.lastIndexOf('<details className="dash-more"', at("More charts:"));
const moreFold = dash.slice(moreAt, dash.indexOf("</details>", moreAt));
ok("⭐ GONE from 'More charts': Vehicles needed over time (it is a key chart now); the fold's name loses 'vehicles'",
   !moreFold.includes("fleetCfg") && !moreFold.includes("Vehicles needed") && moreFold.includes("More charts: trips, carbon over time, material split")
   // NARROWED 25 Nov 2026 (level plots): the moved chart is size "key" now, not "lg"
   && !/More charts:[^<]*vehicles/.test(dash) && (dash.match(/<ChartCanvas config=\{fleetCfg\} size="key" htmlKey/g) || []).length === 1);
ok("...the moved chart is a key chart in its row (size key, its key out of the canvas), its tools in its title row",
   // NARROWED 25 Nov 2026 (the mother session's "level the three plots"): size "lg" became size "key" + htmlKey
   /c-fleet">[\s\S]{0,400}<ChartCanvas config=\{fleetCfg\} size="key" htmlKey title=\{"Vehicles needed"\} scope=\{dashScope\} \/>/.test(row1));
ok("⭐ LEVEL PLOTS: the three key charts are size 'key' with their key as an HTML line; nothing else on the page is",
   /c-demand">[\s\S]{0,400}<ChartCanvas config=\{demandCfg\} size="key" htmlKey /.test(row1)
   && /c-progress">[\s\S]{0,400}<ChartCanvas config=\{progressCfg\} size="key" htmlKey /.test(row1)
   && (code.match(/size="key" htmlKey /g) || []).length === 3 && (code.match(/size="key"/g) || []).length === 3 && !/<ChartCanvas [^>]*htmlKey/.test(code.replace(/<ChartCanvas config=\{(demandCfg|progressCfg|fleetCfg)\} size="key" htmlKey /g, "")));
ok("⭐ ...CSS: one fixed height (the old default's), never stretched by the row; the key line 12 px under the box",
   /\.chart-box\.is-key\{height:clamp\(200px,28vh,420px\);\}/.test(html) && /\.chart-card>\.chart-box\.is-key\{flex:none;\}/.test(html)
   && /\.ch-key\{display:flex;flex-wrap:wrap;gap:3px 12px;margin-top:4px;font-size:12px;line-height:16px;color:var\(--muted\);\}/.test(html));
const _cc = (code.match(/function ChartCanvas\([\s\S]*?\n\}\n/) || [""])[0];
ok("⭐ ...ChartCanvas: the canvas is drawn with no key when htmlKey; the copied picture is the config AS GIVEN (key and all) at the box's height plus the key line's",
   _cc.includes("const drawn = htmlKey ? chartNoLegend(config) : config;") && _cc.includes("fitChartConfig(drawn, vwNow())")
   && _cc.includes("drawChartLight(cfgRef.current, el ? el.clientWidth : 0, h)") && _cc.includes("keyRef.current.offsetHeight + 4")
   && _cc.includes("cfgRef.current = config;"));
ok("⭐ CSS (Q9): the rows follow their OWN width: three across from 1,000 px, two from 640 (Vehicles a whole row), one under another below; Cost and Top routes 3 : 2 from 640",
   /\.dash-charts-box\{container-type:inline-size;\}/.test(html)
   && /\.dash-charts,\.dash-charts2\{display:grid;gap:16px 22px;grid-template-columns:minmax\(0,1fr\);\}/.test(html)
   && /@container \(min-width:640px\)\{\s*\.dash-charts\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\);\} \.dash-charts>\.c-fleet\{grid-column:1 \/ -1;\}\s*\.dash-charts2\{grid-template-columns:3fr 2fr;\}\s*\}/.test(html)
   && /@container \(min-width:1000px\)\{\.dash-charts\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\);\} \.dash-charts>\.c-fleet\{grid-column:auto;\}\}/.test(html));
ok("🔴 the old layout's named areas are gone (no 'demand progress top')", !/grid-template-areas:"demand progress top"/.test(html) && !/grid-area:\s*(demand|progress|top|cost)\b/.test(html));

// this month's mark
ok("⭐ THIS MONTH: a plugin draws a dashed hairline through this month's column; fitChartConfig adds it and inks the month's label",
   /\nconst NOW_MARK = \{ id: "nowMark", afterDatasetsDraw\(chart, _args, opts\)\{/.test(code) && code.includes("function fitChartConfig(config, vw, light){")
   && code.includes("config = { ...config, plugins: [...(config.plugins || []), NOW_MARK] };"));
ok("⭐ ...on the three key charts of the working view only: never on the big screen, never on Cost over time",
   code.includes("const keyMark = wall ? {} : { nowMark: { i: dcCur } };")
   && (dash.match(/\.\.\.keyMark \}/g) || []).length === 3 && at("const costCfg") > 0
   && !dash.slice(at("const costCfg"), dash.indexOf("\n  const ", at("const costCfg") + 10)).includes("keyMark") && !/function WallSection[\s\S]{0,4000}keyMark/.test(code));
ok("...this month is worked out ONCE for the charts and the figures (dcNow, dcCur), before the charts",
   (dash.match(/const dcNow = /g) || []).length === 1 && (dash.match(/const dcCur = /g) || []).length === 1 && at("const dcCur = ") < at("const demandCfg"));
ok("...the copied / downloaded picture draws the mark in its own light ink (drawChartLight asks fitChartConfig for light)",
   /function drawChartLight\(config, w, h\)\{[\s\S]{0,800}fitChartConfig\(config, [\s\S]{0,120}?, true\);/.test(code));
ok("⭐ SERIES NAMES: the three key charts name their series at the right on the big screen only (a third of the line is too narrow); Cost keeps its names",
   code.includes("const keyNamed = wall ? named : {};") && (dash.match(/\.\.\.keyNamed, \.\.\.keyMark \}/g) || []).length === 2
   && (dash.match(/\.\.\.named \}/g) || []).length === 1);
ok("THE BIG SCREEN is not this task's: DASH_SECTIONS, WallSection and the wall's figures are still there",
   /\nconst DASH_SECTIONS = /.test(code) && /\nfunction WallSection\(/.test(code) && /\nfunction CarbonTargetLine\(/.test(code) && code.includes("function ctCellsTarget("));

// the header (Q14)
ok("⭐ HEADER (Q14): no 'N plan lines in view' line while no filter chip shows (nor on the first steps)",
   dash.includes("count={firstRun || !applied.length ? null : `${D.lines} plan line${D.lines === 1 ? \"\" : \"s\"} in view`}"));

// ---------------------------------------------------------------------------------------------- 2. a real DOM
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = function(){ return new Proxy({ measureText: (s) => ({ width: String(s).length * 6 }) }, { get(t, k){ return k in t ? t[k] : () => {}; }, set(){ return true; } }); };
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
// (guarded, so the harness reports failures on the code before task B instead of throwing)
w.eval(js + "\nwindow.__O = { NOW_MARK: typeof NOW_MARK === 'undefined' ? {} : NOW_MARK, fitChartConfig, CHART_INK, CHART_MUTED, chartKeyItems: typeof chartKeyItems === 'undefined' ? null : chartKeyItems, ChartCanvas };");
// every config the page hands Chart.js, for the key checks
const BUILT = []; { const C0 = w.Chart; w.Chart = function(_cv, cfg){ BUILT.push(cfg); return C0(); }; w.Chart.defaults = {}; }
const X = w.__O;
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 30)); });
const T = (el) => (el ? el.textContent : "").replace(/\s+/g, " ").trim();
// a figure's words without its "i" button's own glyph
const TF = (el) => { if (!el) return ""; const c = el.cloneNode(true); c.querySelectorAll("button").forEach(b => b.remove()); return T(c); };
const mount = (props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(w.CarbonTargetStrip, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const fig = (el, k) => el.querySelector(`[data-ct-fig="${k}"]`);
const st = (el, k) => { const s = fig(el, k) && fig(el, k).querySelector("[data-row-status]"); return s ? `${s.getAttribute("data-row-status")}:${T(s)}` : null; };
const pop = async (btn) => { if (!btn) return ""; click(btn); await tick(); const p = w.document.querySelector(".info-pop"); const t = T(p);
  act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); }); return t; };
const TR = { t: 864.04, intensity: 1.8, loaded: 595.2, empty: 268.8 };
const S = (over) => ({ ...CTX, status: { ...CTX.status, ...over } });

(async () => {
  try {
    // ---- this month's mark, behaviour ------------------------------------------------------------------------
    const base = { type: "line", data: { labels: ["Jan", "Feb", "Mar"], datasets: [] }, options: { plugins: { nowMark: { i: 1 } } } };
    const fc = X.fitChartConfig(base, 1200);
    const xt = fc.options.scales && fc.options.scales.x && fc.options.scales.x.ticks;
    ok("⭐ THIS MONTH (fitChartConfig): the plugin is added, this month's label is the ink at weight 600 and the others stay grey",
       (fc.plugins || []).includes(X.NOW_MARK) && !!xt && typeof xt.color === "function"
       && xt.color({ tick: { value: 1 } }) !== xt.color({ tick: { value: 0 } }) && xt.font({ tick: { value: 1 } }).weight === "600" && !xt.font({ tick: { value: 2 } }).weight);
    const fl = X.fitChartConfig(base, 1200, true);
    ok("...in the copied picture the label and the line take the picture's own light ink (CHART_INK, CHART_MUTED)",
       typeof fl.options.scales.x.ticks.color === "function" && fl.options.scales.x.ticks.color({ tick: { value: 1 } }) === X.CHART_INK && fl.options.scales.x.ticks.color({ tick: { value: 0 } }) === X.CHART_MUTED
       && fl.options.plugins.nowMark.color === X.CHART_MUTED);
    const fn = X.fitChartConfig({ ...base, options: { plugins: { nowMark: { i: null } } } }, 1200);
    const fd = X.fitChartConfig({ type: "doughnut", data: { labels: ["a"], datasets: [] }, options: { plugins: { nowMark: { i: 0 } } } }, 1200);
    ok("...nothing when this month is outside the range in view (i null), nor on a doughnut, nor without the option",
       !(fn.plugins || []).includes(X.NOW_MARK) && !(fd.plugins || []).includes(X.NOW_MARK)
       && !(X.fitChartConfig({ type: "bar", data: { labels: ["a"], datasets: [] }, options: {} }, 1200).plugins || []).includes(X.NOW_MARK));
    const calls = [];
    const ctx = new Proxy({}, { get: (t, k) => (...a) => calls.push([k, ...a]), set: (t, k, v) => { calls.push(["set", k, v]); return true; } });
    const chart = (px) => ({ chartArea: { left: 40, right: 340, top: 10, bottom: 210 }, scales: { x: { getPixelForValue: () => px } }, ctx });
    if (typeof X.NOW_MARK.afterDatasetsDraw !== "function") X.NOW_MARK.afterDatasetsDraw = () => {};   // the code before task B has no plugin
    X.NOW_MARK.afterDatasetsDraw(chart(120.3), {}, { i: 1, color: "#62656B" });
    ok("⭐ ...the plugin draws ONE dashed 1 px hairline from the top of the plot to its foot through the month's column",
       calls.some(c => c[0] === "setLineDash" && JSON.stringify(c[1]) === "[2,3]") && calls.some(c => c[0] === "set" && c[1] === "lineWidth" && c[2] === 1)
       && calls.some(c => c[0] === "moveTo" && c[1] === 120.5 && c[2] === 10) && calls.some(c => c[0] === "lineTo" && c[1] === 120.5 && c[2] === 210)
       && calls.filter(c => c[0] === "stroke").length === 1);
    calls.length = 0; X.NOW_MARK.afterDatasetsDraw(chart(400), {}, { i: 9 }); X.NOW_MARK.afterDatasetsDraw(chart(120), {}, { i: null });
    ok("...and nothing when the month's column is off the plot or there is no month", calls.length === 0);

    // ---- the carbon section, every state ------------------------------------------------------------------
    const set = mount({ ct: CTX, err: false, onOpen(){}, transport: TR });
    const s0 = set.el.querySelector('[data-carbon-target="set"]');
    ok("⭐ CARBON (Q10): a target set: FOUR figures in one ruled strip, in this order: Target, As forecast, With the agreed decisions, Transport carbon in view",
       !!s0 && !!s0.querySelector(".ct-figs.fig-strip") && [...s0.querySelectorAll("[data-ct-fig]")].map(e => e.getAttribute("data-ct-fig")).join() === "target,forecast,decisions,transport");
    ok("...Target 41.4 t, '74.0 % below the approved plan' under it, no status (it is the yardstick)",
       /^Target41\.4 t74\.0 % below the approved plan$/.test(T(fig(s0, "target"))) && st(s0, "target") === null);
    ok("⭐ ...As forecast 159.1 t with its status a diamond '117.7 t over'; With the agreed decisions 41.4 t with a dot 'On target'",
       /As forecast\s*159\.1 t/.test(T(fig(s0, "forecast"))) && st(s0, "forecast") === "warn:117.7 t over"
       && /With the agreed decisions\s*41\.4 t/.test(T(fig(s0, "decisions"))) && st(s0, "decisions") === "ok:On target");
    ok("⭐ ...Transport carbon, in view: 864.0 t, '1.8 kg/t · loaded 595.2 t · empty 268.8 t', no status",
       /Transport carbon, in view\s*864\.0 t\s*1\.8 kg\/t · loaded 595\.2 t · empty 268\.8 t/.test(TF(fig(s0, "transport"))) && st(s0, "transport") === null, T(fig(s0, "transport")));
    ok("...the title 'Carbon target · all-in' with its 'i', who set it, the Carbon planner button, and the fold of the agreed decisions",
       /^Carbon target · all-in/.test(T(s0.querySelector(".ct-h"))) && !!s0.querySelector(".ct-h button") && !!s0.querySelector(".ct-row .ct-note")
       && [...s0.querySelectorAll("button")].some(b => T(b) === "Open the Carbon planner") && (!CTX.target.lever_words || !CTX.target.lever_words.length || !!s0.querySelector("details.ct-more")));
    const tInfo = await pop(s0.querySelector(".ct-h button"));
    ok("⭐ ...the all-in sentence and the target line are in the title's 'i', not on the page",
       /All-in: making the material, transport and waste disposal, on the whole approved plan\. Target: 74\.0% below the approved plan = 41\.4 tCO2e\./.test(tInfo)
       && !/All-in:/.test(T(s0)), tInfo.slice(0, 220));
    const trInfo = await pop(fig(s0, "transport").querySelector("button"));
    ok("...the transport figure's 'i' gives the exact figure and the approved plan's transport part",
       /Exactly 864\.0 tCO2e on the routed lines in view, transport only\. Transport is 11\.7 tCO2e of the approved plan as forecast\./.test(trInfo), trInfo.slice(0, 220));
    ok("🔴 GONE: 'The Transport carbon card above counts transport only.', the three sentences ('As forecast: …'), CO₂ and any source name on the section (an info box keeps its own source line)",
       !/card above/.test(T(s0) + tInfo + trInfo) && !/As forecast: |With the agreed decisions: |Target: 74/.test(T(s0))
       && !/CO₂/.test(T(s0)) && !/CO₂/.test(tInfo.slice(tInfo.indexOf("All-in:"))) && !/CO₂/.test(trInfo.slice(trInfo.indexOf("Exactly"))) && !/DESNZ|DfT|UK Government/.test(T(s0)));
    set.done();

    const scheme = mount({ ct: CTX, err: false, onOpen(){}, scheme: true, transport: TR });
    ok("...with Sites picked the title says scheme-wide", /^Carbon target · all-in · scheme-wide/.test(T(scheme.el.querySelector(".ct-h")))); scheme.done();

    const under = mount({ ct: S({ with_decisions_t: 29.1, gap_with_decisions_t: -12.3, on_target_with_decisions: false, gap_as_forecast_t: 0, on_target_as_forecast: true }), transport: TR });
    ok("...under the target: a dot '12.3 t under'; on target as forecast: a dot 'On target'",
       st(under.el, "decisions") === "ok:12.3 t under" && st(under.el, "forecast") === "ok:On target"); under.done();

    const cap = mount({ ct: { ...CTX, target: { ...CTX.target, mode: "cap", cap_t: 41.387 } }, transport: TR });
    const capInfo = await pop(cap.el.querySelector(".ct-h button"));
    ok("...a fixed cap: the target figure says 'a fixed cap', the 'i' gives the cap's sentence",
       /^Target41\.4 ta fixed cap$/.test(T(fig(cap.el, "target"))) && /Target: a fixed cap of 41\.4 tCO2e \(74\.0% below the approved plan when it was set\)/.test(capInfo)); cap.done();

    const team = mount({ ct: S({ scope: "team", share_pct: 79.1, target_t: 32.7 }), transport: TR });
    const teamInfo = await pop(team.el.querySelector(".ct-h button"));
    ok("⭐ ...a team login: 'Target, your <team>'s share' 32.7 t, '79.1 % of the scheme's target'; the 'i' says the approved plan on the team's lines; no fold",
       /^Target, your [a-z ]+'s share32\.7 t79\.1 % of the scheme's target$/.test(T(fig(team.el, "target")))
       && /All-in: making the material, transport and waste disposal, on the approved plan on your [a-z ]+'s lines\. Target for your [a-z ]+'s lines: 32\.7 tCO2e, 79\.1% of the scheme's target/.test(teamInfo)
       && !team.el.querySelector("details.ct-more"), T(fig(team.el, "target")) + " | " + teamInfo.slice(0, 200)); team.done();

    const noShare = mount({ ct: S({ scope: "team", share_pct: null, target_t: null, invalid: "The agreed decisions no longer fit the plan.", with_decisions_t: null }), transport: TR });
    ok("...a team with no share while the decisions do not fit: '—' and 'no share while the agreed decisions do not fit'; the decisions figure a ring 'No longer fit the plan'",
       /^Target, your [a-z ]+'s share—no share while the agreed decisions do not fit$/.test(T(fig(noShare.el, "target")))
       && st(noShare.el, "decisions") === "none:No longer fit the plan" && /^With the agreed decisions—/.test(T(fig(noShare.el, "decisions")))); noShare.done();

    // ---- the key out of the canvas (level plots) ------------------------------------------------------------------
    const mountC = (props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
      act(() => { r.render(w.React.createElement(X.ChartCanvas, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
    const two = { type: "bar", data: { labels: ["Jan", "Feb"], datasets: [
      { label: "Planned t", data: [1, 2], backgroundColor: "rgba(232,89,12,.18)", borderColor: "#E8590C", borderWidth: 1, order: 2 },
      { label: "Delivered t (reported)", data: [1, 1], backgroundColor: "#0B4EA2", borderWidth: 0, order: 1 }] },
      options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } } };
    const one = { type: "bar", data: { labels: ["Jan", "Feb"], datasets: [{ label: "Vehicles", data: [1, 2], backgroundColor: "#E8590C" }] }, options: { plugins: { legend: { display: false } } } };
    BUILT.length = 0;
    const kc = mountC({ config: two, size: "key", htmlKey: true, title: "Delivered against plan (tonnes)" });
    const keyEl = kc.el.querySelector('[data-chart-key="1"]');
    const sw = keyEl ? [...keyEl.querySelectorAll("i")] : [];
    ok("⭐ KEY LINE: under the box, one entry a series in Chart.js's own key order (by `order`) and colour; a bordered series keeps its edge; the swatch is hidden from a reader",
       !!keyEl && [...keyEl.children].map(T).join("|") === "Delivered t (reported)|Planned t"
       && kc.el.querySelector(".chart-box.is-key") && kc.el.querySelector(".chart-box.is-key").nextElementSibling && kc.el.querySelector(".chart-box.is-key").nextElementSibling.contains(keyEl)
       && sw.length === 2 && /inset 0(px)? 0(px)? 0(px)? 1px/.test(sw[1].style.boxShadow) && !sw[0].style.boxShadow && sw.every(i => i.getAttribute("aria-hidden") === "true"));
    ok("⭐ ...the canvas is drawn WITHOUT its key (legend display false), the config it was given left as it was (the picture draws the key)",
       BUILT.length >= 1 && BUILT[BUILT.length - 1].options.plugins.legend.display === false && two.options.plugins.legend.display === undefined);
    kc.done();
    const nk = mountC({ config: one, size: "key", htmlKey: true, title: "Vehicles needed" });
    ok("⭐ ...a chart with no key (Vehicles needed) gets no line and no room for one",
       !nk.el.querySelector('[data-chart-key="1"]') && !!nk.el.querySelector(".chart-box.is-key") && !nk.el.querySelector(".chart-box.is-key").nextElementSibling); nk.done();
    BUILT.length = 0;
    const plain = mountC({ config: two, title: "Cost over time" });
    ok("🔴 ...a chart without htmlKey (Cost over time, the big screen, More charts) keeps its key inside the canvas, as before",
       !plain.el.querySelector('[data-chart-key="1"]') && BUILT.length >= 1 && BUILT[BUILT.length - 1].options.plugins.legend.display !== false); plain.done();
    ok("...chartKeyItems: no entries when the key is switched off; unnamed series skipped",
       !!X.chartKeyItems && X.chartKeyItems(one).length === 0
       && X.chartKeyItems({ ...two, data: { labels: [], datasets: [...two.data.datasets, { data: [] }] } }).length === 2);

    const bad = mount({ ct: S({ invalid: "The agreed decisions no longer fit the plan (route 'R4' does not exist).", with_decisions_t: null }), transport: TR });
    ok("⭐ ...decisions that no longer fit: the figure is '—' with a ring 'No longer fit the plan'; the server's sentence under the figures",
       st(bad.el, "decisions") === "none:No longer fit the plan" && [...bad.el.querySelectorAll(".ct-note")].some(n => /no longer fit the plan \(route 'R4'/.test(T(n)))
       && st(bad.el, "forecast") === "warn:117.7 t over"); bad.done();

    const none = mount({ ct: { status: null, target: null }, err: false, onOpen(){}, transport: TR });
    const nOut = none.el.querySelector('[data-carbon-target="none"]');
    ok("⭐ ...none set: the title row and its button, ONE line 'No carbon target set yet. A planner sets it in the Carbon planner.' and the transport figure beside it",
       !!nOut && T(fig(nOut, "state")) === "No carbon target set yet. A planner sets it in the Carbon planner." && !!fig(nOut, "transport")
       && [...nOut.querySelectorAll("button")].some(b => T(b) === "Open the Carbon planner") && !fig(nOut, "target")); none.done();

    const err = mount({ ct: null, err: true, transport: TR });
    ok("...a failed read: 'The carbon target did not load.' and the transport figure, no button without onOpen",
       T(fig(err.el, "state")) === "The carbon target did not load." && !!fig(err.el, "transport") && !err.el.querySelector("button.btn-sec")); err.done();

    const load = mount({ ct: null, err: false, transport: TR });
    const load0 = mount({ ct: null, err: false });
    ok("...loading: 'Loading the carbon target.' beside the transport figure; with no transport figure either, nothing at all",
       T(fig(load.el, "state")) === "Loading the carbon target." && !!fig(load.el, "transport") && load0.el.innerHTML === ""); load.done(); load0.done();

    const zero = mount({ ct: CTX, transport: { t: 0, intensity: null, loaded: 0, empty: 0 } });
    ok("...no routed lines in view: the transport figure reads 0.0 t and 'needs routes worked out', no source named",
       /Transport carbon, in view\s*0\.0 t\s*needs routes worked out/.test(TF(fig(zero.el, "transport"))) && !/DESNZ/.test(T(zero.el))); zero.done();
  } catch (e) {
    ok("the harness ran without throwing", false, String(e && e.stack || e).slice(0, 400));
  }
  for (const f of fail) console.log("  FAIL: " + f);
  console.log(`ui_fix_dash_order.js: ${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
