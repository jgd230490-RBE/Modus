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
w.eval(js + "\nwindow.__T = THEME; window.__TENANT = TENANT; window.__ACCESS = ACCESS; window.__VEH = VEH;");   // VEH: the vehicle-name languages (§3b, 11 Oct)   // ACCESS: the stored code (11 Oct, reload resume)   // consts in the script scope; THEME for §3, TENANT for §4
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

// ---- 3b. the vehicle-name buttons (11 Oct 2026, the EU type-approval vehicles removed) ------------------
// /api/meta's vehicle_labels.langs is what the server OFFERS: English, plus any label language a vehicle the
// tenant is offered still carries. The seed and the GB demo carry English alone; a document saved before
// 11 Oct with the EU entries still carries 'eu'. The header draws buttons only when there is a choice, and
// the country rules (G2/H1) still apply on top. NOT covered: the md: breakpoint that hides them on a phone.
function headerWith(langs, country, lang){
  w.__VEH.langs = langs; w.__TENANT.country = country; w.__VEH.lang = lang || "en";
  const box = w.document.createElement("div"); w.document.body.appendChild(box);
  const root = w.ReactDOM.createRoot(box);
  act(() => { root.render(w.React.createElement(w.Header, { view: "portal", role: { label: "Planner", ipt: null }, setView(){}, signOut(){}, vehLang: lang || "en", setVehLang(){} })); });
  const names = [...box.querySelectorAll("header .hdr-seg button")].map(b => b.textContent.trim());
  const on = [...box.querySelectorAll("header .hdr-seg button.is-on")].map(b => b.textContent.trim());
  const seg = !!box.querySelector("header .hdr-seg");
  act(() => { root.unmount(); }); box.remove();
  return { names, on, seg };
}
const vh1 = headerWith(["en"], "GB");
ok("VEHICLE NAMES: English alone offered (the seed, the GB demo) → no buttons at all in the header (it showed a lone English)",
   vh1.names.length === 0 && !vh1.seg, JSON.stringify(vh1));
const vh2 = headerWith(["en", "eu"], null);
ok("VEHICLE NAMES: a document still carrying the EU entries, no country set → English and European, English lit (the new default)",
   vh2.names.join("|") === "English|European" && vh2.on.join("|") === "English", JSON.stringify(vh2));
const vh3 = headerWith(["en", "eu"], "GB");
ok("VEHICLE NAMES: ...the same offer to a GB tenant still shows no European button (H1), so no buttons at all",
   vh3.names.length === 0 && !vh3.seg, JSON.stringify(vh3));
const vh4 = headerWith(["en", "eu", "ee"], "EE", "ee");
ok("VEHICLE NAMES: an Estonian tenant whose vehicles carry Estonian names gets all three, its stored choice lit (G2)",
   vh4.names.join("|") === "English|European|Estonian" && vh4.on.join("|") === "Estonian", JSON.stringify(vh4));
const vh5 = headerWith(["en", "ee"], "GB");
ok("VEHICLE NAMES: an Estonian label offered to a non-Estonian tenant is still not shown (G2)", vh5.names.length === 0, JSON.stringify(vh5));
w.__VEH.langs = ["en"]; w.__TENANT.country = null; w.__VEH.lang = "en";

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
  const srv = { target: () => reply(500, "boom"), gates: () => new Promise(() => {}) };   // 11 Oct 2026: gate arrivals never answer here, so the Dashboard mounts below keep the panel silent
  let confirmAnswer = false, confirms = 0;
  w.confirm = () => { confirms++; return confirmAnswer; };
  w.fetch = (url, opt) => {
    const method = (opt && opt.method) || "GET", body = opt && opt.body ? JSON.parse(opt.body) : null;
    calls.push({ url, method, body });
    if (url === "/api/carbon/target") return method === "GET" ? srv.target() : reply(200, CTX);
    if (String(url).startsWith("/api/gates/arrivals")) return srv.gates();
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

  // ---- 12 Oct 2026 (C4): the Monthly bulletin on the Dashboard — the click, the request, the error, the save ----
  // fetch answers like the server: first a 503 (the PDF library missing), then a PDF. NOT covered: a browser's
  // real download, the HTML page itself (test_bulletin.py, http_smoke.py).
  const bulletinCalls = [];
  const realFetch = w.fetch;
  let pdfReply = () => reply(503, { detail: "reportlab is not installed: test" });
  w.fetch = (url, opt) => {
    if (String(url).startsWith("/api/bulletin/")) { bulletinCalls.push(url); return pdfReply(); }
    return realFetch(url, opt);
  };
  const saved = [];
  w.URL.createObjectURL = () => "blob:bulletin"; w.URL.revokeObjectURL = () => {};
  const realClick = w.HTMLAnchorElement.prototype.click;
  w.HTMLAnchorElement.prototype.click = function(){ saved.push(this.download); };
  const d4 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  const bmSel = d4.el.querySelector('select[aria-label="Bulletin month"]');
  const bmLink = () => [...d4.el.querySelectorAll(".bulletin-menu a")].find(x => x.textContent === "Open the page");
  ok("BULLETIN DOM: the menu is on the Dashboard with every programme month, and its link follows the month",
     !!bmSel && bmSel.options.length === dMeta.months.count && !!bmLink());
  act(() => { bmSel.value = "10"; bmSel.dispatchEvent(new w.Event("change", { bubbles: true })); });
  ok("BULLETIN DOM: choosing October 2026 points the page link at /bulletin/?month=10, in a new tab",
     bmLink().getAttribute("href") === "/bulletin/?month=10" && bmLink().getAttribute("target") === "_blank");
  act(() => { byText(d4.el, "button", "Download the PDF").click(); });
  await settle(50);
  const bmErr = d4.el.querySelector(".bm-err");
  ok("⭐ BULLETIN DOM: Download asks the server for that month's PDF; a refusal is said under it, in the server's words",
     bulletinCalls.length === 1 && bulletinCalls[0] === "/api/bulletin/month.pdf?month=10" && !!bmErr
     && bmErr.textContent === "The bulletin could not be made: reportlab is not installed: test" && saved.length === 0);
  pdfReply = () => reply(200, "%PDF-");
  act(() => { byText(d4.el, "button", "Download the PDF").click(); });
  await settle(50);
  ok("⭐ BULLETIN DOM: ...and a PDF is saved as bulletin-2026-10.pdf, the error line cleared",
     bulletinCalls.length === 2 && saved.length === 1 && saved[0] === "bulletin-2026-10.pdf" && !d4.el.querySelector(".bm-err"));
  d4.done();
  w.HTMLAnchorElement.prototype.click = realClick;
  w.fetch = realFetch;
}

// ---- 4b. gate arrivals in a real DOM (11 Oct 2026) ----------------------------------------
// The Dashboard's own read of GET /api/gates/arrivals?month=N: a failed read says so in one line and
// leaves the programme figures and the carbon strip alone; a landed read is three rows with the red
// row's chip saying "Queue likely"; picking another month re-reads with that month and nothing else
// (every call a GET: the panel writes nothing); an empty month shows the empty state. The fixture is
// the one test_gate_arrivals.py writes (the planner's month 9). Not covered: a browser, the live server.
async function gateArrivalsDom(){
  const GA = FIX("gate_arrivals.json"), CTX = FIX("carbon_target.json"), CL = FIX("cost_lines.json");
  const calls = [];
  const srv = { gates: () => reply(500, "boom") };
  w.fetch = (url, opt) => {
    const method = (opt && opt.method) || "GET";
    calls.push({ url: String(url), method });
    if (url === "/api/carbon/target") return reply(200, CTX);
    if (String(url).startsWith("/api/gates/arrivals")) return srv.gates();
    return new Promise(() => {});
  };
  const dMeta = { ...metaMin, routes: [], vehicles: ["Rigid 8-wheeler (32t)"],
    factors: { ...metaMin.factors, vehicle_payload_t: { "Rigid 8-wheeler (32t)": 20 } } };
  const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
    act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
  const gaCalls = () => calls.filter(c => c.url.startsWith("/api/gates/arrivals"));
  // today's month, the panel's default, worked out the same way (clamped to the 24-month horizon of metaMin)
  const _d = new Date(), thisMonth = Math.max(1, Math.min(dMeta.months.count, (_d.getFullYear() - dMeta.months.start_year) * 12 + _d.getMonth() + 1));

  // (1) the read fails
  const d1 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  const e1 = d1.el.querySelector('[data-gate-arrivals="error"]');
  ok("⭐ GATE DOM: the panel's own read fails: one line says so, the carbon strip and the programme figures stay",
     !!e1 && e1.textContent === "The gate arrivals did not load." && d1.el.textContent.includes("Transport carbon")
     && !!d1.el.querySelector('[data-carbon-target="set"]') && !d1.el.querySelector("[data-ga-gate]"));
  ok("GATE DOM: ...it asked for this month, once, as a GET",
     gaCalls().length === 1 && gaCalls()[0].url === `/api/gates/arrivals?month=${thisMonth}` && gaCalls()[0].method === "GET");
  d1.done();

  // (2) the read lands
  srv.gates = () => reply(200, GA);
  calls.length = 0;
  const d2 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  const redRow = d2.el.querySelector('[data-ga-flag="red"]');
  ok("⭐ GATE DOM: the read lands: three rows, the red row's chip says Queue likely, the others Spacing holds / No check-in time typed",
     d2.el.querySelectorAll("[data-ga-gate]").length === 3 && !!d2.el.querySelector('[data-gate-arrivals="set"]')
     && !!redRow && redRow.textContent.includes("Queue likely") && redRow.textContent.includes("East compound")
     && d2.el.querySelectorAll('[data-ga-flag="none"]').length === 2
     && d2.el.textContent.includes("Spacing holds") && d2.el.textContent.includes("No check-in time typed")
     && d2.el.textContent.includes("one every 2.6 min if arrivals are spread evenly"));
  // the select is the REQUEST's month (this month, the panel's default), the header line the server's label — here the stub
  // answered a month-9 fixture to whatever month was asked, so the two differ on purpose
  ok("GATE DOM: ...the month select holds the month that was asked for, and the header line carries the server's label",
     d2.el.querySelector("select.ga-sel") && d2.el.querySelector("select.ga-sel").value === String(thisMonth)
     && d2.el.textContent.includes("Sep 2026: lorries a day at each gate"));

  // (3) picking another month re-reads with that month and nothing else
  const other = thisMonth === 3 ? 4 : 3;
  const sel = d2.el.querySelector("select.ga-sel");
  const before = calls.length;
  await act(async () => {
    Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(sel, String(other));
    sel.dispatchEvent(new w.Event("change", { bubbles: true }));
  });
  await settle(50);
  ok("⭐ GATE DOM: picking another month re-reads with that month and nothing else; every call is a GET (the panel writes nothing)",
     gaCalls().length === 2 && gaCalls()[1].url === `/api/gates/arrivals?month=${other}` && calls.length === before + 1
     && calls.every(c => c.method === "GET") && sel.value === String(other));
  d2.done();

  // (4) an empty month
  srv.gates = () => reply(200, { ...GA, month: 11, label: "Nov 2026", gates: [], notes: ["No approved lines in Nov 2026.", GA.notes[GA.notes.length - 1]] });
  const d4 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  ok("GATE DOM: an empty month shows the empty state with the month's name and the averages note; no rows",
     !!d4.el.querySelector('[data-gate-arrivals="none"]') && d4.el.textContent.includes("No approved lines in Nov 2026")
     && d4.el.textContent.includes("No hourly peak is typed") && !d4.el.querySelector("[data-ga-gate]"));
  d4.done();
}

// ---- 5. the demo bar (11 Oct 2026) ------------------------------------------------------
// The whole App, mounted: /api/meta answers with the demo tenant, /api/auth with a planner, every other fetch
// never settles. The map iframe is jsdom's (nothing is loaded into it), so the embedded map's side — the message
// it posts and its guideStart — is played by this harness: parse_map.js runs the map's own code for that.
// NOT covered: how it looks, and the real iframe in a browser.
const N = "Fictional demo scheme · nothing here is real";
const META = { routes: [], materials: ["Aggregate"], vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } }, mapbox_token: "",
  // NARROWED 11 Oct 2026 (EU vehicles removed): the server now sends the languages it OFFERS — English alone for the
  // GB demo (it sent every slot, ["en", "eu", "ee"], and the client gated them by country)
  vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [], ipts: [],
  tenant: { name: "Wolds Link", team_label: "Team", currency: "GBP", currency_symbol: "£", country: "GB", distance_unit: "mi", demo_notice: N } };
const PLANNER = { role: "planner", label: "Planner", ipt: null, can_approve: true, ipt_locked: false, ipt_required: true, demo: true, ipts: [] };
const respond = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 0)); });
async function demoBar(){
  let meta = META;
  w.fetch = (url) => /\/api\/meta$/.test(String(url)) ? respond(meta) : /\/api\/auth$/.test(String(url)) ? respond(PLANNER) : new Promise(() => {});
  w.localStorage.setItem("modus_page", "dashboard");
  const mount = async () => {
    const box = w.document.createElement("div"); w.document.body.appendChild(box);
    const root = w.ReactDOM.createRoot(box);
    await act(async () => { root.render(w.React.createElement(w.App)); });
    await tick(); await tick();
    return { box, root };
  };
  w.__VEH.lang = "eu";      // 11 Oct 2026: a visitor whose browser stored "eu" before the EU vehicles left
  const { box, root } = await mount();
  ok("VEHICLE NAMES: a stored 'eu' the GB demo is not offered falls back to English once /api/meta answers (it was set back to 'eu')",
     w.__VEH.lang === "en" && w.__VEH.langs.join("|") === "en");
  const bar = () => box.querySelector(".demo-bar");
  const guideBtn = () => box.querySelector(".demo-bar-guide");
  const order = () => { const kids = [...box.firstElementChild.children].map(e => e.tagName.toLowerCase() + (e.classList.contains("demo-bar") ? ".demo-bar" : "")); return kids.join(">"); };
  const post = (data, origin) => act(() => { w.dispatchEvent(new w.MessageEvent("message", { data, origin: origin || w.location.origin })); });
  ok("DEMO BAR: once /api/meta answers with a demo tenant, the bar is on the public map, straight under the header and before <main>",
     w.__TENANT.demo_notice === N && !!bar() && order() === "header>div.demo-bar>main");
  ok("DEMO BAR: it carries the tenant's own words (the CSS uppercases them) as text, with the full text on hover",
     bar().querySelector(".demo-bar-text").textContent === N && bar().querySelector(".demo-bar-text").getAttribute("title") === N && bar().getAttribute("role") === "note");
  ok("DEMO BAR: no header badge, and no Guide in the header", !box.querySelector(".demo-badge") && ![...box.querySelectorAll("header button")].some(b => /Guide/.test(b.textContent)));
  ok("DEMO BAR: on the public map there is no Guide until the embedded map says its tour is ready (the password page never does)", !guideBtn() && !bar().classList.contains("has-guide"));
  await post({ type: "wayscope-map-tour" }, "https://elsewhere.example");
  await post({ type: "something-else" });
  ok("🔴 DEMO BAR: a message from another origin, or of another type, shows no Guide", !guideBtn());
  await post({ type: "wayscope-map-tour" });
  ok("⭐ DEMO BAR: the map's own message shows the Guide at the bar's right end", !!guideBtn() && bar().classList.contains("has-guide") && guideBtn().textContent === "Guide");
  const frame = box.querySelector('iframe[title="Public Route Map"]');
  ok("DEMO BAR: the public map's iframe is the embedded map (?embed=1)", !!frame && /^\/map\/\?embed=1&v=\d+$/.test(frame.getAttribute("src")));
  let mapTours = 0, appGuides = 0;
  w.addEventListener("wayscope-guide", () => appGuides++);
  frame.contentWindow.guideStart = () => mapTours++;
  click(guideBtn());
  ok("⭐ DEMO BAR: on the public map the Guide starts the EMBEDDED map's own tour (its guideStart), not the app's", mapTours === 1 && appGuides === 0);
  delete frame.contentWindow.guideStart;
  let threw = false; try { click(guideBtn()); } catch (e) { threw = true; }
  ok("🔴 DEMO BAR: with no guideStart in the frame (the map password page) the Guide throws nothing and starts nothing", !threw && mapTours === 1 && appGuides === 0);
  // sign-in: the bar stays, with no Guide (there is no tour)
  click([...box.querySelectorAll("header button")].find(b => /Staff sign in/.test(b.textContent)));
  ok("DEMO BAR: on the sign-in view the bar stays, under the header, with no Guide", order() === "header>div.demo-bar>main" && !guideBtn() && !!box.querySelector('input[placeholder="Access code"]'));
  const setVal = (el, v) => act(() => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(el, v); el.dispatchEvent(new w.Event("input", { bubbles: true })); });
  await setVal(box.querySelector('input[placeholder="Your name"]'), "Tester");
  await setVal(box.querySelector('input[placeholder="Access code"]'), "planner-code");
  await act(async () => { [...box.querySelectorAll("button")].find(b => b.textContent === "Sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick(); await tick();
  ok("DEMO BAR: signed in, on a Portal page (Dashboard), the bar is still under the header, with the Guide", order() === "header>div.demo-bar>main" && !!box.querySelector('[data-guide="rail"]') && !!guideBtn());
  ok("DEMO BAR: the header still has no Guide of its own, and Appearance still comes before Sign out",
     ![...box.querySelectorAll("header button")].some(b => /^Guide$/.test(b.textContent.trim())) && !!box.querySelector("header .appearance-btn"));
  await act(async () => { guideBtn().dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  ok("⭐ DEMO BAR: on a Portal page the Guide replays the app's guide (the one event name) and the tour opens, welcome first",
     appGuides === 1 && mapTours === 1 && !!w.document.querySelector(".guide-card") && /Welcome to the demo\./.test(w.document.querySelector(".guide-card").textContent));
  // walk the tour to its end ("Got it"): the Dashboard and the welcome are marked seen, the tips stay switched on
  for (let n = 0; n < 12 && w.document.querySelector(".guide-card .guide-next"); n++) click(w.document.querySelector(".guide-card .guide-next"));
  ok("DEMO BAR: the tour closes with Got it and the tips stay on (so the next check means something)",
     !w.document.querySelector(".guide-card") && w.localStorage.getItem("wayscope_guide_all") !== "off" && w.localStorage.getItem("wayscope_guide_dashboard") === "done");
  // the staff Route map: the app's guide steps aside, the bar's Guide goes to the embedded map once it is ready
  await act(async () => { [...box.querySelectorAll(".rail-item")].find(b => /Route map/.test(b.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  const sframe = box.querySelector('iframe[title="Public Route Map"]');
  ok("DEMO BAR: on the staff Route map the iframe is the embedded map, and there is no Guide until it says its tour is ready",
     !!sframe && /^\/map\/\?embed=1&v=\d+$/.test(sframe.getAttribute("src")) && !guideBtn());
  ok("DEMO BAR: ...and the app's own guide is not mounted there (no second 'New here?' strip, no tour card, nothing under wayscope_guide_map)",
     !w.document.querySelector(".guide-strip") && !w.document.querySelector(".guide-card") && w.localStorage.getItem("wayscope_guide_map") === null);
  await post({ type: "wayscope-map-tour" });
  sframe.contentWindow.guideStart = () => mapTours++;
  click(guideBtn());
  ok("⭐ DEMO BAR: on the staff Route map the Guide starts the embedded map's tour, not the app's", mapTours === 2 && appGuides === 1);
  await act(async () => { [...box.querySelectorAll(".rail-item")].find(b => /Dashboard/.test(b.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  click(guideBtn());
  ok("DEMO BAR: back on a Portal page the Guide is the app's again", appGuides === 2 && mapTours === 2);
  await act(async () => { [...box.querySelectorAll(".rail-item")].find(b => /Route map/.test(b.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  ok("🔴 DEMO BAR: back on the Route map, a NEW iframe: no Guide until it announces its tour again (the readiness was reset with the screen)", !guideBtn());
  await act(async () => { root.unmount(); }); box.remove();
  // a real tenant: no notice, so no bar and no Guide anywhere
  meta = { ...META, tenant: { ...META.tenant, name: "Real Client", demo_notice: null } };
  w.localStorage.setItem("modus_page", "dashboard");
  const real = await mount();
  ok("🔴 DEMO BAR: a real tenant (no notice) gets no bar and no Guide button anywhere",
     w.__TENANT.demo_notice === null && !real.box.querySelector(".demo-bar") && ![...real.box.querySelectorAll("button")].some(b => b.textContent.trim() === "Guide")
     && [...real.box.firstElementChild.children].map(e => e.tagName.toLowerCase()).join(">") === "header>main");
  await act(async () => { real.root.unmount(); });
}

// ---- 6. the embedded map with and without the bar above it (11 Oct 2026, review) -------------------------------
// The map hides its own notice only when the app's bar is really drawn above it: barAbove() looks for .demo-bar in
// the parent page. Here the map's REAL guide block (applyTenantVocabulary … the resize hook, sliced out of
// map/index.html as parse_map.js does) runs in a second jsdom document, and its parent is THIS app window with App
// mounted in it. So the class the map looks for is checked against what App really renders. The browser's
// postMessage between the two windows is played by the harness (each side's message is handed to the other's
// listener). NOT covered: a real iframe in a browser, and how either looks.
const mapAll = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const mapMain = (mapAll.match(/\n<script>\n([\s\S]*?)\n<\/script>/) || ["", ""])[1];
const gA = mapMain.indexOf("    function applyTenantVocabulary() {");
const gEnd = "window.addEventListener('resize', () => { if (guideIndex >= 0) guideRender(); });";
const gB = mapMain.indexOf(gEnd);
function mapUnder(notice){
  const md = new JSDOM(`<!doctype html><html><body><div id="kpi-hud"></div><button id="tl-play"></button><div id="kpi-conditions"></div><div id="kpi-moving"></div></body></html>`,
                       { url: "https://wayscope.test/map/?embed=1&v=1" });
  const mdoc = md.window.document, listeners = {}, toApp = [];
  const parent = { document: w.document, postMessage: (m, o) => toApp.push([m, o]) };   // this app window, as the map sees it
  const mwin = { innerWidth: 1280, innerHeight: 800, evr_rail_data: null, OVERLAY_VERSION: null, parent,
                 addEventListener(t, fn){ (listeners[t] = listeners[t] || []).push(fn); } };
  const location = { origin: "https://wayscope.test", search: "?embed=1&v=1" };
  const TENANT = { name: "Wolds Link", team_label: "Team", demo_notice: notice };
  const f = new Function("document", "window", "localStorage", "location", "setInterval", "TENANT", "TEAM", "EMBED",
    mapMain.slice(gA, gB + gEnd.length) + "\nreturn { applyTenantVocabulary };");
  const api = f(mdoc, mwin, md.window.localStorage, location, () => 0, TENANT, "Team", true);
  api.applyTenantVocabulary();
  return {
    toApp,
    strip: () => mdoc.getElementById("demo-notice"),
    cls: () => mdoc.body.classList.contains("has-demo-notice"),
    btn: () => mdoc.getElementById("guide-btn"),
    // the browser delivering the app's message into the frame: from the parent, this origin
    receive: (data) => (listeners.message || []).forEach(fn => fn({ data, origin: location.origin, source: parent })),
  };
}
async function lateBar(){
  ok("MAP UNDER THE BAR: the map's guide block is found in map/index.html", gA > 0 && gB > gA);
  const post = (data) => act(() => { w.dispatchEvent(new w.MessageEvent("message", { data, origin: w.location.origin })); });
  const mountApp = async () => {
    const box = w.document.createElement("div"); w.document.body.appendChild(box);
    const root = w.ReactDOM.createRoot(box);
    await act(async () => { root.render(w.React.createElement(w.App)); });
    return { box, root };
  };
  // a fresh load is a SIGNED-OUT visitor: the DEMO BAR section signed in, and since 11 Oct a stored code resumes
  // the staff app on load, so forget it here (the public map is what these cases are about)
  w.__ACCESS.code = ""; w.__ACCESS.info = null; w.sessionStorage.removeItem("modus_access_code");
  // (a) /api/meta fails (FastAPI's plain-text 500: json() throws) on a fresh load: no bar, so the map keeps its own
  w.__TENANT.demo_notice = null; w.__TENANT.name = "Wayscope";
  w.fetch = (url) => /\/api\/meta$/.test(String(url))
    ? Promise.resolve({ ok: false, status: 500, json: () => Promise.reject(new SyntaxError("Unexpected token 'I'")) })
    : new Promise(() => {});
  const a = await mountApp(); await tick(); await tick();
  const aFrame = a.box.querySelector('iframe[title="Public Route Map"]');
  ok("MAP UNDER THE BAR: /api/meta fails → the app draws no bar, and the public map's iframe is still the embedded map",
     !a.box.querySelector(".demo-bar") && !!aFrame && /^\/map\/\?embed=1&v=\d+$/.test(aFrame.getAttribute("src")));
  const m1 = mapUnder("Fictional demo scheme · nothing here is real");
  ok("⭐ MAP UNDER THE BAR: ...so the embedded map (its real code, its parent this app) keeps its own strip, the class and its own Guide button",
     !!m1.strip() && m1.strip().textContent === "Fictional demo scheme · nothing here is real" && m1.cls() && !!m1.btn()
     && m1.toApp.length === 0);
  await act(async () => { a.root.unmount(); }); a.box.remove();

  // (b) the bar arrives AFTER the map has loaded: /api/meta answers late
  let release;
  w.__TENANT.demo_notice = null;
  w.fetch = (url) => /\/api\/meta$/.test(String(url)) ? new Promise(r => { release = () => r({ ok: true, status: 200, json: () => Promise.resolve(META) }); }) : new Promise(() => {});
  const b = await mountApp();
  const bFrame = b.box.querySelector('iframe[title="Public Route Map"]');
  const sent = [];
  bFrame.contentWindow.postMessage = (m, o) => sent.push([m, o, !!w.document.querySelector(".demo-bar")]);
  const m2 = mapUnder(N);                 // the map loaded first: no bar above yet
  ok("MAP UNDER THE BAR: before /api/meta answers there is no bar, and a map that loads now draws its own strip",
     !b.box.querySelector(".demo-bar") && !!m2.strip() && m2.cls() && !!m2.btn());
  await act(async () => { release(); }); await tick(); await tick();
  ok("⭐ MAP UNDER THE BAR: /api/meta answers → the bar appears, and the app tells the map in the frame, once, same origin, with the bar already on screen",
     !!b.box.querySelector(".demo-bar") && sent.length === 1 && sent[0][0].type === "wayscope-bar-on"
     && sent[0][1] === w.location.origin && sent[0][2] === true);
  m2.receive(sent[0][0]);
  ok("⭐ MAP UNDER THE BAR: ...the map drops its strip, its class and its own Guide button, and tells the app its tour is ready",
     !m2.strip() && !m2.cls() && !m2.btn() && m2.toApp.length === 1 && m2.toApp[0][0].type === "wayscope-map-tour" && m2.toApp[0][1] === "https://wayscope.test");
  await post(m2.toApp[0][0]);
  ok("MAP UNDER THE BAR: ...and the bar's Guide appears for the map's tour (one notice on screen, the bar's)",
     !!b.box.querySelector(".demo-bar-guide"));
  const m3 = mapUnder(N);                 // a map that loads after the bar finds it itself
  ok("⭐ MAP UNDER THE BAR: a map that loads after the bar finds it in the app page: no strip, no class, no button; it says its tour is ready",
     !m3.strip() && !m3.cls() && !m3.btn() && m3.toApp.length === 1 && m3.toApp[0][0].type === "wayscope-map-tour");
  await act(async () => { b.root.unmount(); }); b.box.remove();

  // (c) a real tenant: no bar, and nothing is posted into the frame
  let releaseReal;
  w.__TENANT.demo_notice = null;
  w.fetch = (url) => /\/api\/meta$/.test(String(url)) ? new Promise(r => { releaseReal = () => r({ ok: true, status: 200, json: () => Promise.resolve({ ...META, tenant: { ...META.tenant, name: "Real Client", demo_notice: null } }) }); }) : new Promise(() => {});
  const c = await mountApp();
  const sentReal = [];
  c.box.querySelector('iframe[title="Public Route Map"]').contentWindow.postMessage = (m, o) => sentReal.push([m, o]);
  await act(async () => { releaseReal(); }); await tick(); await tick();
  ok("🔴 MAP UNDER THE BAR: a real tenant: no bar, and nothing is posted into the map", !c.box.querySelector(".demo-bar") && sentReal.length === 0);
  await act(async () => { c.root.unmount(); }); c.box.remove();
}

// 11 Oct 2026: a reload no longer signs you out. A stored code is checked with /api/auth on load and the app
// returns to the staff view; a refused code is forgotten; a network failure keeps it for the next reload.
async function reloadResume(){
  const mountApp = async () => {
    const box = w.document.createElement("div"); w.document.body.appendChild(box);
    const root = w.ReactDOM.createRoot(box);
    await act(async () => { root.render(w.React.createElement(w.App)); });
    return { box, root };
  };
  const btn = (box, t) => [...box.querySelectorAll("button")].some(b => b.textContent.trim() === t);
  const store = (c) => { w.__ACCESS.code = c; w.__ACCESS.info = null; w.sessionStorage.setItem("modus_access_code", c); };
  const isMeta = (u) => /\/api\/meta$/.test(String(u)), isAuth = (u) => /\/api\/auth$/.test(String(u));
  w.__TENANT.demo_notice = N;
  // (a) the server accepts the stored code
  let authBody = null, release;
  store("demo-planner");
  w.fetch = (url, o) => isMeta(url) ? respond(META)
    : isAuth(url) ? (authBody = o && o.body, new Promise(r => { release = () => r({ ok: true, status: 200, json: () => Promise.resolve(PLANNER) }); }))
    : new Promise(() => {});
  const a = await mountApp(); await tick();
  ok("RELOAD: with a stored code the app says it is signing you back in, not the public map or Staff sign in",
     /Signing you back in/.test(a.box.textContent) && !btn(a.box, "Staff sign in") && !a.box.querySelector('iframe[title="Public Route Map"]'));
  ok("...and asks /api/auth what that code grants (the same call the sign-in form makes)",
     authBody === JSON.stringify({ code: "demo-planner" }));
  await act(async () => { release(); }); await tick(); await tick();
  ok("⭐ RELOAD: an accepted code returns to the staff app (Sign out on screen, no Staff sign in, code kept)",
     btn(a.box, "Sign out") && !btn(a.box, "Staff sign in") && !/Signing you back in/.test(a.box.textContent)
     && w.sessionStorage.getItem("modus_access_code") === "demo-planner" && w.__ACCESS.info === PLANNER);
  await act(async () => { a.root.unmount(); }); a.box.remove();
  // (b) the server refuses it (the code was changed): public map, and the code is forgotten
  store("old-code");
  w.fetch = (url) => isMeta(url) ? respond(META)
    : isAuth(url) ? Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }) : new Promise(() => {});
  const b = await mountApp(); await tick(); await tick();
  ok("🔴 RELOAD: a refused code lands on the public map with Staff sign in, and is removed from the tab",
     btn(b.box, "Staff sign in") && !btn(b.box, "Sign out") && w.sessionStorage.getItem("modus_access_code") === null && w.__ACCESS.code === "");
  await act(async () => { b.root.unmount(); }); b.box.remove();
  // (c) the network fails: public map now, but the code is kept so the next reload tries again
  store("demo-planner");
  w.fetch = (url) => isMeta(url) ? respond(META) : isAuth(url) ? Promise.reject(new TypeError("Failed to fetch")) : new Promise(() => {});
  const c = await mountApp(); await tick(); await tick();
  ok("RELOAD: a network failure shows the public map but keeps the code for the next reload",
     btn(c.box, "Staff sign in") && w.sessionStorage.getItem("modus_access_code") === "demo-planner");
  await act(async () => { c.root.unmount(); }); c.box.remove();
  // (d) no stored code: the public map at once, and /api/auth is never called
  w.__ACCESS.code = ""; w.sessionStorage.removeItem("modus_access_code");
  let authCalls = 0;
  w.fetch = (url) => { if(isAuth(url)) authCalls++; return isMeta(url) ? respond(META) : new Promise(() => {}); };
  const d = await mountApp(); await tick();
  ok("RELOAD: with no stored code the public map shows at once and /api/auth is not called",
     btn(d.box, "Staff sign in") && authCalls === 0 && !/Signing you back in/.test(d.box.textContent));
  await act(async () => { d.root.unmount(); }); d.box.remove();
}

// ---- 11 Oct 2026 (review): Config → Vehicles' Estonian column follows the COUNTRY, not the offered languages ----
// On the new seed every vehicle carries English alone, so the server offers ["en"]. Gated on what is offered, an
// Estonian organisation never saw the column it needs to type its first Estonian name. Mounted for real, the doc
// served by a stubbed GET /api/config/factors.
async function configEstonianColumn(){
  const DOC = { vehicles: { _default: { payload_t: 20 }, "Rigid 8-wheeler (32t)": { payload_t: 20, gvw_t: 32, labels: { en: "Rigid 8-wheeler (32t)" } } },
                material_categories: {}, planning: { load_minutes: 12, unload_minutes: 8, working_days_per_month: 22 } };
  w.fetch = (url) => /\/api\/config\/factors$/.test(String(url)) ? respond({ doc: DOC, status: { source: "file" }, file: DOC }) : new Promise(() => {});
  const mount = async (country) => {
    w.__TENANT.country = country; w.__VEH.langs = ["en"];
    const box = w.document.createElement("div"); w.document.body.appendChild(box);
    const root = w.ReactDOM.createRoot(box);
    await act(async () => { root.render(w.React.createElement(w.ConfigPage, { meta: {}, who: "tester", access: plannerAcc })); });
    await tick(); await tick();
    const th = [...box.querySelectorAll("table.tbl thead th")].map(x => x.textContent.trim());
    const inputs = box.querySelectorAll("table.tbl tbody tr")[0] ? box.querySelectorAll("table.tbl tbody tr")[0].querySelectorAll('input[placeholder="Rigid 8-wheeler (32t)"]').length : -1;
    await act(async () => { root.unmount(); }); box.remove();
    return { th, inputs };
  };
  const ee = await mount("EE");
  ok("CONFIG (11 Oct 2026 review): ⭐ an Estonian tenant offered English alone still sees the Estonian column, to type its first Estonian name",
     ee.th.includes("Vehicle (id)") && ee.th.includes("Estonian") && ee.inputs === 2, JSON.stringify(ee));
  const gb = await mount("GB");
  ok("CONFIG (11 Oct 2026 review): ...a GB tenant does not (the country rule stands), English column only",
     gb.th.includes("English") && !gb.th.includes("Estonian") && gb.inputs === 1, JSON.stringify(gb));
  const hdr = headerWith(["en"], "EE");
  ok("CONFIG (11 Oct 2026 review): ...while the header still draws no buttons for that Estonian tenant until a vehicle carries an Estonian name",
     hdr.names.length === 0 && !hdr.seg, JSON.stringify(hdr));
  w.__VEH.langs = ["en"]; w.__TENANT.country = null; w.__VEH.lang = "en"; w.fetch = () => new Promise(() => {});
}

// one runner for the async sections (merged 11 Oct 2026: claude/carbon-process + claude/demo-bar): the bar's first,
// on a fresh window, then the carbon target's (it mounts its pages directly, without the App shell)
(async () => {
  try { await demoBar(); ok("DEMO BAR: the section ran to the end", true); }
  catch (e) { ok("DEMO BAR: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await lateBar(); ok("MAP UNDER THE BAR: the section ran to the end", true); }
  catch (e) { ok("MAP UNDER THE BAR: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await reloadResume(); ok("RELOAD: the section ran to the end", true); }
  catch (e) { ok("RELOAD: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await configEstonianColumn(); ok("CONFIG (11 Oct 2026 review): the section ran to the end", true); }
  catch (e) { ok("CONFIG (11 Oct 2026 review): the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await carbonTargetDom(); } catch (e) { ok("CARBON DOM: the section ran to the end", false, e && e.stack); }
  try { await gateArrivalsDom(); ok("GATE DOM: the section ran to the end", true); }
  catch (e) { ok("GATE DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  console.log(`\n${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
})();
