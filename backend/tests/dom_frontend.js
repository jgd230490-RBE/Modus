/*
 * dom_frontend.js — the staff app mounted in a REAL DOM (jsdom), for the behaviour the
 * static harnesses cannot see: clicks, state, what ends up on <html>, what is stored.
 *
 * 5 Oct 2026, written for the Appearance picker. render_frontend.js renders components
 * to static markup; parse_frontend.js reads the source. Neither can open a popover.
 *
 * Needs: typescript, react, react-dom, jsdom — resolved through NODE_PATH (or a
 * node_modules on the path), like the other JS harnesses:
 *     npm install -g typescript@5 react@18 react-dom@18 jsdom@24
 *     export NODE_PATH="$(npm root -g)"; node backend/tests/dom_frontend.js
 * Without jsdom it prints SKIPPED and exits 0, so the suite stays runnable.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("dom_frontend.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");   // 9 Oct 2026: a Windows checkout (core.autocrlf) hands us CRLF; the regexes expect LF
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

const dom = new JSDOM(`<!doctype html><html><head><meta name="theme-color" content="#1F2024"></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.mapboxgl = { Map: function(){ return { on(){}, remove(){}, getCanvas: () => ({ style: {} }), addControl(){}, getSource: () => null, getLayer: () => null, resize(){}, setStyle(){}, fitBounds(){} }; }, accessToken: "", NavigationControl: function(){}, ScaleControl: function(){} };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });

// ---- 1. a remembered choice is applied before anything mounts -------------------------
w.localStorage.setItem("modus_theme", "light");
w.eval(js + "\nwindow.__T = THEME;");   // the store is a const in the script scope; expose it for §3
ok("APPEARANCE: a remembered look (localStorage modus_theme) is on <html> before React mounts",
   w.document.documentElement.getAttribute("data-theme") === "light");
ok("APPEARANCE: theme-color follows the header colour (white for the light look)",
   w.document.querySelector('meta[name="theme-color"]').getAttribute("content") === "#FFFFFF");

// ---- 2. the picker in the header ------------------------------------------------------
act(() => { w.ReactDOM.createRoot(w.document.getElementById("root")).render(
  w.React.createElement(w.Header, { view: "portal", role: { label: "Admin", ipt: null }, setView(){}, signOut(){}, vehLang: "en", setVehLang(){} })); });
const btn = w.document.querySelector(".appearance-btn");
ok("APPEARANCE: one 32 px button in the header, closed, labelled, before Sign out",
   !!btn && btn.closest("header") !== null && btn.getAttribute("aria-expanded") === "false" && btn.getAttribute("aria-label") === "Appearance"
   && [...w.document.querySelectorAll("header button")].findIndex(b => b === btn) < [...w.document.querySelectorAll("header button")].findIndex(b => /Sign out/.test(b.textContent)));
ok("APPEARANCE: nothing is open until it is clicked", !w.document.querySelector(".appearance-menu"));
click(btn);
const items = [...w.document.querySelectorAll(".appearance-item")];
ok("APPEARANCE: the popover lists Ink, Light, Dark as menuitemradio, the current one checked",
   items.map(b => b.textContent.replace("✓", "").trim()).join("|") === "Ink|Light|Dark"
   && items.map(b => b.getAttribute("aria-checked")).join("|") === "false|true|false" && btn.getAttribute("aria-expanded") === "true");
click(items[2]);
ok("APPEARANCE: choosing Dark sets html[data-theme=dark], stores it, closes the popover, ink theme-color",
   w.document.documentElement.getAttribute("data-theme") === "dark" && w.localStorage.getItem("modus_theme") === "dark"
   && !w.document.querySelector(".appearance-menu") && w.document.querySelector('meta[name="theme-color"]').getAttribute("content") === "#1F2024");
click(btn);
act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
ok("APPEARANCE: Escape closes it", !w.document.querySelector(".appearance-menu"));
click(btn);
act(() => { w.document.body.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
ok("APPEARANCE: a click outside closes it", !w.document.querySelector(".appearance-menu"));
click(btn);
act(() => { btn.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
ok("APPEARANCE: a click on the button itself does not count as outside", !!w.document.querySelector(".appearance-menu"));
click(items[0] === undefined ? btn : [...w.document.querySelectorAll(".appearance-item")][0]);
ok("APPEARANCE: back to Ink", w.document.documentElement.getAttribute("data-theme") === "ink" && w.localStorage.getItem("modus_theme") === "ink");
act(() => { w.applyTheme("bogus"); });
ok("APPEARANCE: an unknown value falls back to ink", w.document.documentElement.getAttribute("data-theme") === "ink");

// ---- 3. subscribers ---------------------------------------------------------------------
let seen = [];
w.__T.subs.add((n) => seen.push(n));
act(() => { w.applyTheme("dark"); w.applyTheme("light"); });
ok("APPEARANCE: subscribers (the charts) hear every change in order", seen.join("|") === "dark|light");

// ---- 4. the carbon target in a real DOM (11 Oct 2026) ---------------------------------------
// What the static harnesses cannot see: the reads themselves, a failed read, the buttons' clicks,
// confirm(), and a refused scenario. fetch is a stub that answers like the server (the fixtures the
// backend harnesses write); nothing here reaches a server. Not covered: a browser's layout (the Guide's
// strip lifting above the result strip is source-level only: jsdom measures every box as 0 × 0).
const FIX = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", f), "utf8"));
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const settle = (ms) => act(async () => { await sleep(ms); });
const reply = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status,
  text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  json: () => Promise.resolve(body), blob: () => Promise.resolve(new w.Blob(["x"])) });
const byText = (root, sel, t) => [...root.querySelectorAll(sel)].find(e => e.textContent.trim() === t);
const setVal = (el, v) => act(() => {
  Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(el, v);
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
});
const plannerAcc = { role: "planner", label: "Planner", ipt: null, can_approve: true, ipt_locked: false, ipt_required: true, demo: false, ipts: ["IPT1", "IPT2"] };
const metaMin = { routes: [], materials: ["Small aggregate"], vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 24 }, factors: { material_density_t_per_m3: { "Small aggregate": 1.6 }, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } },
  mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [] };

async function carbonTargetDom(){
  const SC = FIX("carbon_scenario.json"), CTX = FIX("carbon_target.json");
  const calls = [];
  const srv = { target: () => reply(500, "boom") };
  let confirmAnswer = false, confirms = 0;
  w.confirm = () => { confirms++; return confirmAnswer; };
  w.fetch = (url, opt) => {
    const method = (opt && opt.method) || "GET", body = opt && opt.body ? JSON.parse(opt.body) : null;
    calls.push({ url, method, body });
    if (url === "/api/carbon/target") return method === "GET" ? srv.target() : reply(200, CTX);
    if (url === "/api/carbon/scenario") {
      const lv = ((body.alternatives || [])[0] || {}).levers || [];
      if (lv.some(l => l.epd && !String(l.epd.source || "").trim())) return reply(400, { detail: "an EPD override needs its source (the EPD's reference)" });
      return reply(200, lv.length ? SC : { ...SC, alternatives: [] });
    }
    if (url === "/api/carbon/summary.pdf") return reply(503, { detail: "the PDF library is not installed here" });
    return new Promise(() => {});
  };

  // ---- the Carbon page: its read of the target fails --------------------------------------
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  act(() => { root.render(w.React.createElement(w.CarbonPage, { meta: metaMin, access: plannerAcc, who: "Sam" })); });
  await settle(450);
  const step6 = () => host.querySelector("#carbon-step-6");
  const setBtn = () => byText(host, "button", "Set as the scheme's carbon target");
  const puts = () => calls.filter(c => c.url === "/api/carbon/target" && c.method === "PUT");
  ok("CARBON DOM: the page reads the target once on mount (GET), and the read fails (a 500)",
     calls.filter(c => c.url === "/api/carbon/target").length === 1 && calls[0].method === "GET" && !!step6());
  ok("⭐ CARBON DOM: with the read failed, Set is disabled and says why; Try again is offered; the server's error is shown",
     setBtn() && setBtn().disabled && step6().textContent.includes("The scheme's current carbon target did not load, so a new one cannot be set yet.")
     && !!byText(step6(), "button", "Try again") && step6().textContent.includes("The carbon target could not be reached (error 500). Try again."));
  const elec = [...host.querySelectorAll("label")].find(l => /Battery electric lorries/.test(l.textContent)).querySelector("input");
  act(() => { elec.click(); });
  await settle(450);
  ok("CARBON DOM: a choice that lowers carbon gives a result (the strip at the foot reads it)",
     (host.querySelector("[data-sticky-foot]") || { textContent: "" }).textContent.includes("Result: 32.8 tCO2e"));
  act(() => { setBtn().click(); });
  await settle(50);
  ok("🔴 CARBON DOM: ...but Set stays disabled, and a click sends NO PUT (it would have replaced a target it could not see, without asking)",
     setBtn().disabled && puts().length === 0 && confirms === 0);
  srv.target = () => reply(200, CTX);
  act(() => { byText(step6(), "button", "Try again").click(); });
  await settle(100);
  ok("⭐ CARBON DOM: Try again reads it again (a second GET); the target shows and Set is enabled",
     calls.filter(c => c.url === "/api/carbon/target" && c.method === "GET").length === 2
     && step6().textContent.includes("Target: 73.1% below the approved plan = 43.4 tCO2e") && !setBtn().disabled && !byText(step6(), "button", "Try again"));
  act(() => { setBtn().click(); });
  await settle(50);
  ok("🔴 CARBON DOM: with a target there, Set asks first; answering no sends nothing",
     confirms === 1 && puts().length === 0);
  confirmAnswer = true;
  act(() => { setBtn().click(); });
  await settle(100);
  const put = puts()[0] || { body: {} };
  ok("⭐ CARBON DOM: answering yes sends ONE PUT: the decisions, the mode, the page state and the typed name — never a figure",
     puts().length === 1 && put.body.mode === "pct" && put.body.updated_by === "Sam" && put.body.ui_state && put.body.ui_state.electric === true
     && JSON.stringify(put.body.levers) === JSON.stringify([{ driver: "fuel", fuel: "electric" }])
     && !/target_t|cap_t|pct_below|approved_t|with_decisions_t/.test(JSON.stringify(put.body)) && step6().textContent.includes("Target set."));
  act(() => { byText(host, "button", "Start again").click(); });
  await settle(450);
  ok("CARBON DOM: Start again empties the choices and clears step 6's last message",
     !step6().textContent.includes("Target set.") && !elec.checked);
  confirmAnswer = false;
  act(() => { byText(step6(), "button", "Fixed tCO2e cap").click(); });
  await settle(50);
  ok("🔴 CARBON DOM: switching a saved target to a cap asks first; answering no sends nothing",
     confirms === 3 && puts().length === 1);
  confirmAnswer = true;
  act(() => { byText(step6(), "button", "Fixed tCO2e cap").click(); });
  await settle(100);
  ok("CARBON DOM: answering yes sends the mode alone", puts().length === 2 && JSON.stringify(puts()[1].body) === JSON.stringify({ mode: "cap", updated_by: "Sam" }));

  // ---- a refused scenario: an EPD typed before its reference --------------------------------
  act(() => { elec.click(); });
  await settle(450);
  const kg = host.querySelector('input[placeholder="Government factor"]');
  await setVal(kg, "5");
  await settle(450);
  const s5 = host.querySelector("#carbon-step-5").textContent, foot = (host.querySelector("[data-sticky-foot]") || { textContent: "" }).textContent;
  ok("⭐ CARBON DOM: a refused scenario says 'Not updated' with the server's sentence in step 5, and calls the old figures the previous choices",
     s5.includes("Not updated: an EPD override needs its source (the EPD's reference) The figures below are from your previous choices."));
  ok("⭐ CARBON DOM: ...the strip at the foot says it too, in place of the old result",
     foot.includes("Not updated: an EPD override needs its source") && !foot.includes("Result:"));
  ok("🔴 CARBON DOM: ...and Set is disabled, its reason the same sentence",
     setBtn().disabled && step6().textContent.includes("Not updated: an EPD override needs its source (the EPD's reference)"));
  ok("CARBON DOM: ...the EPD fields say what they need, and the material says an EPD is in use",
     host.textContent.includes("Add the EPD reference: the result does not update until it has one.")
     && host.textContent.includes("Supplier EPD in use: 5 kgCO2e per tonne, so recycled content and reuse do not apply"));
  act(() => { byText(host, "button", "Download the summary (PDF)").click(); });
  await settle(100);
  const dl = byText(host, "button", "Download the summary (PDF)");
  ok("⭐ CARBON DOM: a failed summary is said under its own button, in the server's words, and does not touch the scenario's error",
     dl && dl.nextElementSibling && dl.nextElementSibling.textContent === "The summary could not be made: the PDF library is not installed here"
     && host.querySelector("#carbon-step-5").textContent.includes("Not updated: an EPD override needs its source"));
  const ref = host.querySelectorAll('input[placeholder="for example, the EPD number"]')[0];
  await setVal(ref, "EPD-123");
  await settle(450);
  ok("CARBON DOM: with a reference the scenario is answered again and every 'Not updated' clears",
     !host.textContent.includes("Not updated") && (host.querySelector("[data-sticky-foot]") || { textContent: "" }).textContent.includes("Result:"));
  act(() => { root.unmount(); }); host.remove();

  // ---- the Dashboard and Forecasts: a failed read, and the button to the Carbon planner ----------
  const CL = FIX("cost_lines.json");
  const dMeta = { ...metaMin, routes: [], vehicles: ["Rigid 8-wheeler (32t)"],
    factors: { ...metaMin.factors, vehicle_payload_t: { "Rigid 8-wheeler (32t)": 20 } } };
  srv.target = () => reply(500, "boom");
  const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
    act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
  const d1 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  const e1 = d1.el.querySelector('[data-carbon-target="error"]');
  ok("⭐ CARBON DOM: the Dashboard's own read of the target fails: one line says so, the programme figures stay",
     !!e1 && e1.textContent === "The carbon target did not load." && d1.el.textContent.includes("Transport carbon"));
  d1.done();
  const f1 = mount(w.Forecasts, { meta: dMeta, who: "t", access: plannerAcc, onEdit(){}, onChanged(){} });
  await settle(50);
  const e2 = f1.el.querySelector('[data-carbon-target="error"]');
  ok("⭐ CARBON DOM: the Forecasts page's read fails: one line says so", !!e2 && e2.textContent === "The carbon target did not load.");
  f1.done();
  srv.target = () => reply(200, { target: null, status: null });
  const opened = [];
  const d2 = mount(w.Dashboard, { meta: dMeta, initialData: CL, onOpen: (p) => opened.push(p) });
  await settle(50);
  const go = byText(d2.el, "button", "Open the Carbon planner");
  ok("CARBON DOM: no target: the Dashboard says so and offers the Carbon planner",
     !!d2.el.querySelector('[data-carbon-target="none"]') && d2.el.textContent.includes("No carbon target set yet. A planner sets it in the Carbon planner.") && !!go);
  if (go) act(() => { go.click(); });
  ok("⭐ CARBON DOM: ...and its click opens the Carbon planner through the Portal's page switch (onOpen('carbon'))",
     opened.length === 1 && opened[0] === "carbon");
  d2.done();
  srv.target = () => reply(200, CTX);
  const d3 = mount(w.Dashboard, { meta: dMeta, initialData: CL, onOpen: (p) => opened.push(p) });
  await settle(50);
  const go3 = byText(d3.el, "button", "Open the Carbon planner");
  if (go3) act(() => { go3.click(); });
  ok("CARBON DOM: with a target set, the strip reads it and still offers the Carbon planner",
     !!d3.el.querySelector('[data-carbon-target="set"]') && d3.el.textContent.includes("With the agreed decisions: 43.4 tCO2e, on target")
     && opened.length === 2 && opened[1] === "carbon");
  d3.done();
}

(async () => {
  try { await carbonTargetDom(); } catch (e) { ok("CARBON DOM: the section ran to the end", false, e && e.stack); }
  console.log(`\n${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
})();
