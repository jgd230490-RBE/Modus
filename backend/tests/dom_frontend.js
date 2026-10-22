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

// 18 Oct 2026 (D104 for the JS harnesses): today is a fixed day, shifted not frozen (lib/harness_clock.js) — the
// Dashboard's this month ± 6 follows the clock, and the fixture lines sit in Sep–Nov 2026. Both realms: here, and the
// jsdom window the app runs in (below, before the app's script). HARNESS_TODAY=YYYY-MM-DD runs on another day.
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

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
w.eval(CLOCK.shiftSource());      // 18 Oct 2026: the app's realm reads the same shifted clock as the checks
w.eval(js +"\nwindow.__T = THEME; window.__ACC = ACCENT; window.__CHARTFIT = { chartLegendPos }; window.__TENANT = TENANT; window.__ACCESS = ACCESS; window.__VEH = VEH;"
  // 13 Oct 2026 (W6): the app's own formatters, so the nothing-lost check formats each fact exactly as the old cell did
  + "\nwindow.__F = { grp, dist, distRate, DU, CUR, TKM, teamText, teamName, iptKey, vehLabel, unitLbl, gaN1, gaMin, gaFlagWord, fmt, flagWord, LINE_FLAG_LABEL, dayName, dayNum, isWeekend };");   // VEH: the vehicle-name languages (§3b, 11 Oct)   // ACCESS: the stored code (11 Oct, reload resume)   // consts in the script scope; THEME for §3, TENANT for §4
ok("APPEARANCE: a remembered look (localStorage modus_theme) is on <html> before React mounts",
   w.document.documentElement.getAttribute("data-theme") === "light");
ok("APPEARANCE: theme-color follows the header colour (white for the light look)",
   w.document.querySelector('meta[name="theme-color"]').getAttribute("content") === "#FFFFFF");
// 18 Oct 2026: the shifted clock holds in both realms, and still ticks (a frozen clock would stall anything that waits on it)
{
  const appDay = w.eval("new Date().toISOString().slice(0, 10)"), hereDay = new Date().toISOString().slice(0, 10);
  const skew = Math.abs(w.eval("Date.now()") - Date.now()), t0 = Date.now(); let spin = 0; while (Date.now() === t0 && spin < 5e7) spin++;
  ok(`CLOCK: today is ${CLOCK.TODAY} in the checks AND in the app's realm (lib/harness_clock.js), and the clock still moves`,
     appDay === CLOCK.TODAY && hereDay === CLOCK.TODAY && skew < 5000 && Date.now() > t0 && w.eval("Date.__harnessShifted") === true,
     `app ${appDay}, here ${hereDay}, skew ${skew} ms`);
}

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

// ---- 2b. 13 Oct 2026 (W16): the Accent group in the same popover ------------------------------------------------
ok("ACCENT: with nothing stored the accent is orange (today's look) on <html> before React mounts",
   w.document.documentElement.getAttribute("data-accent") === "orange");
click(btn);
const accItems = [...w.document.querySelectorAll(".accent-item")];
ok("ACCENT: the popover's second group lists Orange, Blue, Blue shades, Orange shades as menuitemradio, Orange checked; the looks stay three",
   accItems.map(b => b.textContent.replace("✓", "").trim()).join("|") === "Orange|Blue|Blue shades|Orange shades"
   && accItems.every(b => b.getAttribute("role") === "menuitemradio") && accItems.map(b => b.getAttribute("aria-checked")).join("|") === "true|false|false|false"
   && w.document.querySelectorAll(".appearance-item").length === 3);
let seenA = []; const subA = (n) => seenA.push(n);
w.__ACC.subs.add(subA);
click(accItems[2]);
ok("ACCENT: choosing Blue shades sets html[data-accent], stores it, tells the charts, closes the popover, leaves the look alone",
   w.document.documentElement.getAttribute("data-accent") === "blue-shades" && w.localStorage.getItem("modus_accent") === "blue-shades"
   && seenA.join("|") === "blue-shades" && !w.document.querySelector(".appearance-menu") && w.document.documentElement.getAttribute("data-theme") === "ink");
act(() => { w.applyAccent("bogus"); });
ok("ACCENT: an unknown value falls back to orange", w.document.documentElement.getAttribute("data-accent") === "orange" && seenA.join("|") === "blue-shades|orange");
w.__ACC.subs.delete(subA); w.localStorage.removeItem("modus_accent");

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
// ---- 13 Oct 2026 (W3): the info box in a real DOM ------------------------------------------------------
// Click opens it, a second click or Esc closes it and focus returns to the "i"; one open at a time; a
// mousedown outside closes it; its click never reaches a clickable parent (a sortable <th>); the value line
// carries the exact figure the old hover tooltip showed; below 640 px it is a bottom sheet. jsdom has no
// layout, so the flip-above rule and the 44 px touch area are pinned at source level (parse_frontend) and
// checked in a browser. react-dom/client has no createPortal here, so the panel renders in place.
// ---- 13 Oct 2026 (W5, bundle E): a chart is built only once its box has a size ---------------------------------
// jsdom has no layout and no ResizeObserver, so both are stubbed here: the box reports 0 × 0 (a collapsed section)
// and then a real size (the section opened). Chart.js is the stub above, wrapped to record each construction.
async function chartBoxDom(){
  const h = w.React.createElement;
  const tick = () => act(async () => { await new Promise(r => setTimeout(r, 30)); });
  const made = []; const RealChart = w.Chart;
  w.Chart = function(el, cfg){ made.push(cfg); return { destroy(){}, update(){}, resize(){}, options: cfg.options, config: cfg }; }; w.Chart.defaults = {};
  const obs = [];
  w.ResizeObserver = function(cb){ this.cb = cb; this.observe = (el) => { this.el = el; obs.push(this); }; this.disconnect = () => {}; };
  const vw0 = w.innerWidth; const dpr0 = w.devicePixelRatio;
  Object.defineProperty(w, "innerWidth", { value: 600, configurable: true, writable: true });
  Object.defineProperty(w, "devicePixelRatio", { value: 3, configurable: true, writable: true });
  const box = w.document.createElement("div"); w.document.body.appendChild(box);
  const root = w.ReactDOM.createRoot(box);
  const cfg = { type: "doughnut", data: { labels: ["A very long material name indeed", "B"], datasets: [{ data: [1, 2] }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "right" } } } };
  const bar = { type: "bar", data: { labels: ["Route R-001 · Earthworks and more"], datasets: [{ data: [3] }] }, options: { plugins: { legend: { display: false } } } };
  act(() => { root.render(h("div", null, h(w.ChartCanvas, { config: cfg }), h(w.ChartCanvas, { config: bar, size: "lg" }))); });
  await tick();
  const boxes = [...box.querySelectorAll("[data-chart-box]")];
  ok("CHART BOX: each chart sits in its own .chart-box (the lg one marked), observed by a ResizeObserver",
     boxes.length === 2 && boxes.every(b => b.classList.contains("chart-box") && b.querySelector("canvas")) && boxes[1].classList.contains("is-lg")
     && obs.length === 2 && obs.every(o => boxes.includes(o.el)));
  ok("CHART BOX: 🔴 while the box is 0 × 0 (a collapsed section) no chart is built", made.length === 0);
  boxes.forEach(b => { Object.defineProperty(b, "clientWidth", { value: 400, configurable: true }); Object.defineProperty(b, "clientHeight", { value: 240, configurable: true }); });
  act(() => { obs.forEach(o => o.cb([])); }); await tick();
  ok("CHART BOX: once the box has a size (the section opened) each chart is built, once", made.length === 2, `built ${made.length}`);
  const d = made.find(c => c.type === "doughnut") || { options: {} }, b = made.find(c => c.type === "bar") || { options: {} };
  ok("CHART BOX: at most two device pixels per CSS pixel (a 3× screen gets 2)", d.options.devicePixelRatio === 2 && b.options.devicePixelRatio === 2);
  ok("CHART BOX: below 768 px the doughnut's legend moves under the plot (it asked for the right)", d.options.plugins.legend.position === "bottom");
  const tk = ((b.options.scales || {}).x || {}).ticks || {};
  ok("CHART BOX: category labels never rotate, skip when crowded, and are cut at 18 characters",
     tk.maxRotation === 0 && tk.autoSkip === true && typeof tk.callback === "function"
     && tk.callback.call({ getLabelForValue: () => "Route R-001 · Earthworks and more" }, 0) === "Route R-001 · Ear…"
     && tk.callback.call({ getLabelForValue: () => "Short" }, 0) === "Short");
  // 14 Oct 2026 (the design check): every value axis from zero, short tick labels, and no bar fatter than 4.5 × the text
  const yv = ((b.options.scales || {}).y) || {}, bt = ((b.options.datasets || {}).bar) || {};
  ok("CHART BOX: the value axis starts at zero and reads 1.5 M / 250 k / 85 (the tooltip keeps the exact figure)",
     yv.beginAtZero === true && typeof (yv.ticks || {}).callback === "function"
     && yv.ticks.callback(1500000) === "1.5 M" && yv.ticks.callback(250000) === "250 k" && yv.ticks.callback(85) === "85" && yv.ticks.callback(25000000) === "25 M");
  ok("CHART BOX: a bar is never fatter than 4.5 × the chart's text (11 px text → 50 px)", bt.maxBarThickness === 50);
  ok("CHART BOX: the rule by width — a doughnut keeps its legend on the right only from 1024 px",
     w.__CHARTFIT.chartLegendPos("doughnut", 1100, "right") === "right" && w.__CHARTFIT.chartLegendPos("doughnut", 900, "right") === "bottom"
     && w.__CHARTFIT.chartLegendPos("bar", 700, "bottom") === "bottom" && w.__CHARTFIT.chartLegendPos("bar", 1400, "top") === "top");
  act(() => { root.unmount(); }); box.remove();
  w.Chart = RealChart; delete w.ResizeObserver;
  Object.defineProperty(w, "innerWidth", { value: vw0, configurable: true, writable: true });
  Object.defineProperty(w, "devicePixelRatio", { value: dpr0, configurable: true, writable: true });
}

async function infoTipDom(){
  const h = w.React.createElement;
  const tick = () => act(async () => { await new Promise(r => setTimeout(r, 30)); });
  const box = w.document.createElement("div"); w.document.body.appendChild(box);
  const outside = w.document.createElement("button"); outside.textContent = "elsewhere"; w.document.body.appendChild(outside);
  let sorted = 0;
  const root = w.ReactDOM.createRoot(box);
  act(() => { root.render(h("table", null, h("thead", null, h("tr", null,
    h("th", { onClick: () => { sorted++; } }, "Tonnes", h(w.InfoTip, { id: "dash.material", value: "Exactly 796 000 t" })),
    h("th", null, "Carbon", h(w.InfoTip, { id: "dash.carbon", value: ["Exactly 1 544.1 t CO₂e", ""] })))))); });
  const [bA, bB] = [...box.querySelectorAll("button.ibtn")];
  ok("INFO BOX: two closed 'i' buttons, named 'About: …', nothing open yet",
     !!bA && !!bB && bA.getAttribute("type") === "button" && bA.getAttribute("aria-label") === "About: Material in view"
     && bA.getAttribute("aria-expanded") === "false" && !w.document.querySelector(".info-pop"));
  click(bA); await tick();
  const pop = w.document.querySelector(".info-pop");
  ok("INFO BOX: a click opens it: a non-modal dialog labelled by its title, aria-expanded true, aria-controls pointing at it",
     !!pop && pop.getAttribute("role") === "dialog" && pop.getAttribute("aria-modal") === "false"
     && w.document.getElementById(pop.getAttribute("aria-labelledby")).textContent === "Material in view"
     && bA.getAttribute("aria-expanded") === "true" && bA.getAttribute("aria-controls") === pop.id);
  ok("INFO BOX: ...it carries the plain text, the exact figure (the old tooltip's), and both guide links",
     pop.textContent.includes("The planned quantity of every forecast month in view") && pop.querySelector(".info-val").textContent === "Exactly 796 000 t"
     && pop.querySelector('a[href="/help/#3-1-filters-and-the-six-cards"]') && pop.querySelector('a[href="/help/technical/#t1-volume"]'));
  ok("INFO BOX: ...focus moves into it, and the click did not sort the column under it", w.document.activeElement === pop && sorted === 0, `sorted ${sorted}`);
  act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  ok("INFO BOX: Esc closes it and gives focus back to the 'i'",
     !w.document.querySelector(".info-pop") && bA.getAttribute("aria-expanded") === "false" && w.document.activeElement === bA);
  click(bA); await tick(); click(bB); await tick();
  const pops = [...w.document.querySelectorAll(".info-pop")];
  ok("INFO BOX: one open at a time: opening the second closes the first",
     pops.length === 1 && pops[0].textContent.includes("Transport carbon") && bA.getAttribute("aria-expanded") === "false" && bB.getAttribute("aria-expanded") === "true"
     && pops[0].querySelectorAll(".info-val").length === 1 && pops[0].textContent.includes("Source: DESNZ greenhouse gas conversion factors, 2026")
     && pops[0].textContent.includes("How it is worked out"));
  act(() => { outside.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
  ok("INFO BOX: a mousedown anywhere else closes it", !w.document.querySelector(".info-pop") && bB.getAttribute("aria-expanded") === "false");
  click(bB); await tick(); click(bB); await tick();
  ok("INFO BOX: a second click on the same 'i' closes it", !w.document.querySelector(".info-pop"));
  const mm = w.matchMedia;
  w.matchMedia = (q) => ({ matches: q === "(max-width: 639px)", media: q, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
  click(bA); await tick();
  ok("INFO BOX: below 640 px it opens as a bottom sheet (is-sheet, no coordinates of its own)",
     !!w.document.querySelector(".info-pop.is-sheet") && !w.document.querySelector(".info-pop").style.top);
  w.matchMedia = mm;
  act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  act(() => { root.unmount(); }); box.remove(); outside.remove();

  // the carbon target strip: the transport part that used to be a hover title is in the info box
  const CTX = FIX("carbon_target.json");
  const box2 = w.document.createElement("div"); w.document.body.appendChild(box2);
  const root2 = w.ReactDOM.createRoot(box2);
  act(() => { root2.render(h(w.CarbonTargetStrip, { ct: CTX, err: false, onOpen(){} })); });
  const bt = box2.querySelector('button[aria-label="About: Transport in this target"]');
  if (bt) { click(bt); await tick(); }
  const p2 = w.document.querySelector(".info-pop");
  ok("INFO BOX: the carbon target's transport part (once a hover title) opens in its info box with the figure",
     !!bt && !!p2 && /Transport is \d[\d ]*\.\d tCO2e of the approved plan as forecast/.test(p2.textContent)
     && !box2.querySelector(".ct-note[title]"), p2 ? p2.textContent.slice(0, 160) : "no panel");
  act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  act(() => { root2.unmount(); }); box2.remove();
}

// ---- 14 Oct 2026 (bundle G, W7): CLP monitoring in a real DOM — read on FIRST OPEN only, the month select re-reads, a
// failed read says so, an empty chart names its field. fetch is a stub answering with test_clp.py's fixture.
async function clpDom(){
  const CLPF = FIX("clp_monitoring.json");
  const calls = [];
  // the stub answers for the month that was asked (the server's month rides on the reply)
  const srv = { clp: (m) => reply(200, { ...CLPF, month: m }) };
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || "GET" });
    if (String(url).startsWith("/api/clp/monitoring")) return srv.clp(+String(url).split("month=")[1]);
    return new Promise(() => {});
  };
  const el = w.document.createElement("div"); w.document.body.appendChild(el);
  const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(w.ClpMonitoring, { months: metaMin.months })); });
  await settle(30);
  const _d = new Date(), thisMonth = Math.max(1, Math.min(metaMin.months.count, (_d.getFullYear() - metaMin.months.start_year) * 12 + _d.getMonth() + 1));
  ok("⭐ CLP DOM: a folded section reads NOTHING (a closed section costs nothing)", calls.length === 0 && !el.querySelector("details[data-clp]").open);
  const det = el.querySelector("details[data-clp]");
  await act(async () => { det.open = true; det.dispatchEvent(new w.Event("toggle")); await sleep(30); });
  ok("⭐ CLP DOM: opening it reads this month once, as a GET, and draws the seven cards",
     calls.length === 1 && calls[0].url === `/api/clp/monitoring?month=${thisMonth}` && calls[0].method === "GET"
     && el.querySelectorAll('[data-clp-state="set"]').length === 7, JSON.stringify(calls));
  ok("CLP DOM: the headlines are the server's words",
     CLPF.order.every(k => (el.querySelector(`[data-clp-head="${k}"]`) || {}).textContent === CLPF.charts[k].headline));
  await act(async () => { det.open = false; det.dispatchEvent(new w.Event("toggle")); await sleep(10); });
  await act(async () => { det.open = true; det.dispatchEvent(new w.Event("toggle")); await sleep(10); });
  ok("CLP DOM: folding and opening it again does not read again for the same month", calls.length === 1, JSON.stringify(calls));
  const other = thisMonth === 3 ? 4 : 3;
  const sel = el.querySelector('select[aria-label="CLP month"]');
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(sel, String(other));
    sel.dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(30); });
  ok("⭐ CLP DOM: picking another month reads that month, and nothing else", calls.length === 2 && calls[1].url === `/api/clp/monitoring?month=${other}`, JSON.stringify(calls));
  srv.clp = () => reply(500, "boom");
  const third = other === 5 ? 6 : 5;
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(sel, String(third));
    sel.dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(30); });
  ok("CLP DOM: a failed read says so in one line", !!el.querySelector('[data-clp-error="1"]') && el.querySelector('[data-clp-error="1"]').textContent === "The CLP figures did not load.");
  const E = JSON.parse(JSON.stringify(CLPF));
  E.charts.trips_avoided = { ...E.charts.trips_avoided, state: "empty", missing: "No decisions agreed yet: a planner sets them with the carbon target in the Carbon planner." };
  srv.clp = (m) => reply(200, { ...E, month: m });
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(sel, String(thisMonth));
    sel.dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(30); });
  const tc = el.querySelector('[data-clp-chart="trips_avoided"]');
  ok("⭐ CLP DOM: an empty chart names what is missing and where, with no figure",
     !!tc && tc.getAttribute("data-clp-state") === "empty" && tc.textContent.includes("No decisions agreed yet: a planner sets them with the carbon target in the Carbon planner.")
     && !tc.querySelector("canvas") && !tc.querySelector("[data-clp-head]"));
  // W10: the pack buttons ask for this month's pack and name the file from the reply
  const made = [];
  const realCreate = w.URL.createObjectURL;
  w.URL.createObjectURL = () => "blob:x"; w.URL.revokeObjectURL = () => {};
  const realClick = w.HTMLAnchorElement.prototype.click;
  w.HTMLAnchorElement.prototype.click = function(){ made.push(this.download); };
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || "GET" });
    if (String(url).startsWith("/api/clp/pack.pdf")) return Promise.resolve({ ok: true, status: 200, blob: () => Promise.resolve(new w.Blob(["%PDF"])),
      headers: { get: (h) => h === "Content-Disposition" ? 'attachment; filename="wayscope-clp-pack-2026-10.pdf"' : null } });
    if (String(url).startsWith("/api/clp/pack.xlsx")) return reply(503, { detail: "openpyxl is not installed" });
    return new Promise(() => {});
  };
  const pdfBtn = [...el.querySelectorAll("[data-clp-pack] button")].find(b => b.textContent === "CLP pack (PDF)");
  calls.length = 0;
  await act(async () => { pdfBtn.click(); await sleep(30); });
  ok("⭐ CLP DOM (W10): the PDF button GETs this month's pack and saves it under the reply's file name",
     calls.length === 1 && calls[0].url === `/api/clp/pack.pdf?month=${thisMonth}` && made[0] === "wayscope-clp-pack-2026-10.pdf", JSON.stringify(calls) + " " + JSON.stringify(made));
  const xBtn = [...el.querySelectorAll("[data-clp-pack] button")].find(b => b.textContent === "CLP pack (XLSX)");
  await act(async () => { xBtn.click(); await sleep(30); });
  ok("CLP DOM (W10): a refused pack says why, in words",
     !!el.querySelector('[data-clp-pack-error="1"]') && el.querySelector('[data-clp-pack-error="1"]').textContent === "The CLP pack could not be made: openpyxl is not installed");
  w.HTMLAnchorElement.prototype.click = realClick; w.URL.createObjectURL = realCreate;
  act(() => { r.unmount(); }); el.remove();
}

// ---- 16 Oct 2026 (S7): the Simulation section in a real DOM ----------------------------------------------------------
// What the static harnesses cannot see: the read on FIRST OPEN (with the routes' lines once), folding and opening again,
// Play / Pause / Restart / Jump moving the clock, a scenario change reading the day again (no lines, the scenario as
// query parameters, a GET), a scenario the server refuses (its words shown, the inputs put back), one the screen
// refuses itself, Back to the scheme's figures, and the phone (the table only). fetch is a stub answering the fixture
// test_sim.py writes (the example's day with the pour). jsdom draws no map (no Mapbox here); two points a leg stand in
// for each route's line so the drawing's counts can run.
async function simDom(){
  const SIM = FIX("sim_day.json");
  const withLines = (d) => ({ ...d, legs: Object.fromEntries(Object.entries(d.legs).map(([k, v]) => [k, { ...v, coords: [[-1, 52], [-0.9, 52.1]],
    cum: [0, 13000], len_m: 13000, parts: [[0, 13000, 13000 / (v.minutes || 30), null, 0, v.minutes || 30]], plan_minutes: v.minutes || 30 }])) });
  const calls = [];
  const srv = { day: (url) => reply(200, url.includes("legs=1") ? withLines(SIM) : SIM) };
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || "GET" });
    if (String(url).startsWith("/api/sim/day")) return srv.day(String(url));
    return new Promise(() => {});
  };
  const simCalls = () => calls.filter(c => c.url.startsWith("/api/sim/day"));
  const _d = new Date(), thisMonth = Math.max(1, Math.min(metaMin.months.count, (_d.getFullYear() - metaMin.months.start_year) * 12 + _d.getMonth() + 1));
  const mount = (props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
    act(() => { r.render(w.React.createElement(w.SimulationPanel, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
  const toggle = (det, on) => act(async () => { det.open = on; det.dispatchEvent(new w.Event("toggle")); await sleep(40); });

  const m = mount({ meta: metaMin, months: metaMin.months });
  await settle(30);
  const det = m.el.querySelector("details[data-sim]");
  ok("⭐ SIM DOM: a folded Simulation reads NOTHING", simCalls().length === 0 && !!det && !det.open);
  await toggle(det, true);
  await settle(40);
  ok("⭐ SIM DOM: opening it reads this month's day once, as a GET, with the routes' lines (legs=1)",
     simCalls().length === 1 && simCalls()[0].url === `/api/sim/day?month=${thisMonth}&legs=1` && simCalls()[0].method === "GET", JSON.stringify(calls));
  const lead = (m.el.querySelector("[data-sim-lead]") || {}).textContent || "";
  ok("⭐ SIM DOM: the day is drawn from the reply: the lead line, eleven gate rows, the three checks all ticked",
     m.el.querySelector('[data-sim-state="set"]') && lead.startsWith("Sep 2026: an average working day, 312 loads (646 lorry arrivals at the gates, 22 of them mixers)")
     && m.el.querySelectorAll("[data-sim-table] tr[data-sim-gate]").length === 11
     && [...m.el.querySelectorAll("[data-sim-checks] .sim-ok")].length === 3 && !m.el.querySelector("[data-sim-checks] .sim-bad"), lead);
  const hb = m.el.querySelector('[data-sim-table] tr[data-sim-gate="G007"]');
  ok("SIM DOM: Harborough's row carries the server's figures: 101 arrivals, 84 % used, 12 waiting at 12:38, 1776 minutes lost, longest wait 56",
     !!hb && hb.textContent.includes("101") && hb.textContent.includes("84 % used") && hb.textContent.includes("at 12:38")
     && hb.textContent.includes("1776") && hb.textContent.includes("longest wait 56 min") && hb.textContent.includes("first wait 10:00"), hb && hb.textContent);
  ok("SIM DOM: the timeline marks Harborough's bottleneck in words", (m.el.querySelector('[data-sim-tl-gate="G007"]') || {}).textContent && m.el.querySelector('[data-sim-tl-gate="G007"]').textContent.includes("bottleneck from"));
  await toggle(det, false); await toggle(det, true);
  ok("SIM DOM: folding and opening again reads nothing more", simCalls().length === 1, JSON.stringify(simCalls()));

  // the clock. The test drives the animation frames itself (jsdom's own frames race React's act and made this flaky):
  // a frame every 100 ms of page time; 05:30–17:30 plays in 60 s at 1×, so one second of frames is 12 minutes of the day
  const clock = () => m.el.querySelector("[data-sim-clock]").textContent;
  const play = () => m.el.querySelector("[data-sim-play]");
  const realRaf = w.requestAnimationFrame, realCaf = w.cancelAnimationFrame, queued = new Map();
  let rafId = 0, pageMs = 1000;
  w.requestAnimationFrame = (cb) => { queued.set(++rafId, cb); return rafId; };
  w.cancelAnimationFrame = (id) => { queued.delete(id); };
  const frames = (n) => act(() => { for (let i = 0; i < n; i++){ const due = [...queued.values()]; queued.clear(); pageMs += 100; due.forEach(cb => cb(pageMs)); } });
  ok("SIM DOM: the clock starts at the first lorry setting off (05:30) and the button says Play", clock() === "05:30" && play().textContent === "Play");
  await act(async () => { play().click(); });
  frames(11);
  const ran = clock();
  ok("⭐ SIM DOM: Play moves the clock — one second of frames is 12 minutes of the day (05:30 → 05:42) — and the button says Pause",
     ran === "05:42" && play().textContent === "Pause", ran);
  await act(async () => { play().click(); });
  const held = clock();
  frames(10);
  ok("SIM DOM: Pause holds the clock (no frame is asked for while paused)", clock() === held && held === "05:42" && play().textContent === "Play" && queued.size === 0, held + " " + clock());
  const twoX = m.el.querySelector('select[aria-label="Playback speed"]');
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(twoX, "2"); twoX.dispatchEvent(new w.Event("change", { bubbles: true })); });
  await act(async () => { play().click(); });
  frames(11);
  ok("SIM DOM: at 2× one second of frames is 24 minutes (05:42 → 06:06)", clock() === "06:06", clock());
  await toggle(det, false);
  frames(10);
  ok("SIM DOM: folding the section while it plays pauses it (nothing plays unseen)", play().textContent === "Play" && clock() === "06:06" && queued.size === 0, clock());
  await toggle(det, true);
  w.requestAnimationFrame = realRaf; w.cancelAnimationFrame = realCaf;
  const restart = byText(m.el, "button", "Restart");
  await act(async () => { restart.click(); await sleep(20); });
  ok("SIM DOM: Restart puts the clock back to 05:30", clock() === "05:30");
  const jump = m.el.querySelector('input[type=range][aria-label="Jump to a time of day"]');
  await setVal(jump, String(12 * 60 + 40));
  await settle(20);
  const g7now = m.el.querySelector('[data-sim-now-gate="G007"]');
  ok("⭐ SIM DOM: Jump to 12:40 — the clock reads 12:40 and Harborough has lorries waiting in Gates now",
     clock() === "12:40" && !!g7now && g7now.className.includes("sim-q") && /\d+ waiting/.test(g7now.textContent), g7now && g7now.textContent);

  // a scenario: the pour switched on reads the day again, without the lines, with the pour as query parameters
  const pourBox = [...m.el.querySelectorAll("[data-sim-scenario] label.sim-check")].find(l => /Concrete pour/.test(l.textContent)).querySelector("input");
  await act(async () => { pourBox.click(); await sleep(450); });
  const c2 = simCalls()[simCalls().length - 1];
  ok("⭐ SIM DOM: switching the pour on reads the day again after a pause: no lines, the pour's gate, start, m³ and rate, a GET",
     simCalls().length === 2 && !c2.url.includes("legs=1") && c2.url.includes("pour_gate=G007") && c2.url.includes("pour_start=10%3A00")
     && c2.url.includes("pour_m3=160") && c2.url.includes("pour_rate=60") && c2.method === "GET", JSON.stringify(simCalls()));
  ok("SIM DOM fix: the pour's gate list is the server's working sites (four compounds) and the tick took the server's default",
     [...m.el.querySelectorAll('select[aria-label="Pour gate"] option')].map(o => o.value).join(",") === SIM.pour_gates.map(x => x.gate_id).join(",")
     && SIM.pour_default === "G007" && m.el.querySelector('select[aria-label="Pour gate"]').value === "G007");
  // the server refuses a pour past midnight: its words, the start put back, the last good day kept
  srv.day = () => reply(400, { detail: "That pour would run past midnight (last mixer at 25:38); the simulation shows one day." });
  const start = m.el.querySelector('input[aria-label="Pour starts at"]');
  await setVal(start, "23:00");
  await settle(450);
  const msg = m.el.querySelector(".sim-msg");
  ok("⭐ SIM DOM: a refused scenario shows the server's words and puts the input back; the day on screen stays",
     !!msg && msg.textContent === "That pour would run past midnight (last mixer at 25:38); the simulation shows one day."
     && m.el.querySelector('input[aria-label="Pour starts at"]').value === "10:00" && m.el.querySelectorAll("[data-sim-table] tr[data-sim-gate]").length === 11,
     msg && msg.textContent);
  srv.day = (url) => reply(200, url.includes("legs=1") ? withLines(SIM) : SIM);
  const nBefore = simCalls().length;
  await settle(400);
  ok("SIM DOM: the scenario put back is the one on screen: nothing read again", simCalls().length === nBefore, JSON.stringify(simCalls().slice(nBefore)));
  // a window past midnight typed in the table: refused on the screen, nothing read
  const closes = m.el.querySelector('[data-sim-table] tr[data-sim-gate="G001"] input[aria-label$="closes at"]');
  await setVal(closes, "06:00");
  await settle(400);
  ok("⭐ SIM DOM: a gate closing before it opens is refused on the screen in words (D93), and nothing is read",
     simCalls().length === nBefore && (m.el.querySelector(".sim-msg") || {}).textContent === "Kilby Ridge Quarry: the gate must close after it opens; a window past midnight is not simulated.",
     (m.el.querySelector(".sim-msg") || {}).textContent);
  const ci = m.el.querySelector('[data-sim-table] tr[data-sim-gate="G012"] input[type=number]');
  await setVal(ci, "20");
  await settle(450);
  const c3 = simCalls()[simCalls().length - 1];
  ok("SIM DOM: a check-in typed in the table reads the day again with it (check_in=G012=20), the pour still on",
     simCalls().length === nBefore + 1 && c3.url.includes("check_in=G012%3D20") && c3.url.includes("pour_gate=G007"), JSON.stringify(c3));
  const back = byText(m.el, "button", "Back to the scheme's figures");
  await act(async () => { back.click(); });
  await settle(450);
  const c4 = simCalls()[simCalls().length - 1];
  ok("⭐ SIM DOM: Back to the scheme's figures reads the plain month again (no scenario, no lines); every call was a GET",
     c4.url === `/api/sim/day?month=${thisMonth}` && calls.every(c => c.method === "GET"), JSON.stringify(c4));
  m.done();

  // the phone: the table only, no lines asked for, no player, nothing to type
  calls.length = 0;
  const p = mount({ meta: metaMin, months: metaMin.months, phone: true });
  await settle(20);
  await toggle(p.el.querySelector("details[data-sim]"), true);
  await settle(40);
  ok("⭐ SIM DOM: on a phone the day is read without the lines; one card a gate, read-only, with the desktop note",
     simCalls().length === 1 && simCalls()[0].url === `/api/sim/day?month=${thisMonth}` && !!p.el.querySelector('[data-sim-phone="1"]')
     && !p.el.querySelector("[data-sim-player]") && p.el.querySelectorAll("[data-sim-table] li[data-sim-gate]").length === 11
     && (p.el.querySelector('li[data-sim-gate="G007"] [data-sim-busy]') || {}).textContent === "16 at 10:00"
     && !p.el.querySelector("[data-sim-table] input") && !p.el.querySelector("[data-sim-scenario]"));
  p.done();
}

// ---- 17 Oct 2026: the Simulation on the BIG SCREEN (SimWall, the sixth section) in a real DOM --------------------------
// What the static harnesses cannot see: no read while the section is hidden; the plain month (no pour) read once with the
// lines; the day played ONCE a pass in Rotate (then its last picture held), started again at the first lorry each pass,
// looped in One section after the hold; paused while hidden; read again on the 5-minute refresh without restarting; a new
// month read and started at its first lorry; no scenario control and no table on the TV. The month rule (simWallMonth):
// the display's choice, else this month, else the next month with approved lines, else the last one before. Frames are
// driven by the test (a frame every 100 ms of page time; a day = 60 s at 1×, so one second of frames is 12 minutes).
async function simWallDom(){
  const SIM = FIX("sim_day.json");
  const withLines = (d) => ({ ...d, legs: Object.fromEntries(Object.entries(d.legs).map(([k, v]) => [k, { ...v, coords: [[-1, 52], [-0.9, 52.1]],
    cum: [0, 13000], len_m: 13000, parts: [[0, 13000, 13000 / (v.minutes || 30), null, 0, v.minutes || 30]], plan_minutes: v.minutes || 30 }])) });
  const calls = [];
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || "GET" });
    if (String(url).startsWith("/api/sim/day")) { const m = +((/month=(\d+)/.exec(String(url)) || [])[1]); return reply(200, { ...withLines(SIM), month: m, label: m === 9 ? "Sep 2026" : "Oct 2026" }); }
    return new Promise(() => {});
  };
  const swm = w.eval("simWallMonth"), months = metaMin.months;
  const _d = new Date(), thisMonth = Math.max(1, Math.min(months.count, (_d.getFullYear() - months.start_year) * 12 + _d.getMonth() + 1));
  ok("⭐ SIM WALL DOM: the month rule — the display's choice; else this month; else the next month with approved lines; else the last before",
     swm("9", months, []) === 9 && swm("", months, [thisMonth, thisMonth + 2]) === thisMonth && swm("", months, [thisMonth - 3, thisMonth + 2, thisMonth + 5]) === thisMonth + 2
     && swm("", months, [thisMonth - 3, thisMonth - 1]) === thisMonth - 1 && swm("", months, []) === thisMonth && swm("99", months, [thisMonth]) === thisMonth);
  const realRaf = w.requestAnimationFrame, realCaf = w.cancelAnimationFrame, queued = new Map();
  let rafId = 0, pageMs = 1000;
  w.requestAnimationFrame = (cb) => { queued.set(++rafId, cb); return rafId; };
  w.cancelAnimationFrame = (id) => { queued.delete(id); };
  const frames = (n) => act(() => { for (let i = 0; i < n; i++){ const due = [...queued.values()]; queued.clear(); pageMs += 100; due.forEach(cb => cb(pageMs)); } });
  const el = w.document.createElement("div"); w.document.body.appendChild(el);
  const root = w.ReactDOM.createRoot(el);
  const draw = (props) => act(() => { root.render(w.React.createElement(w.SimWall, { meta: metaMin, month: 9, show: false, pass: 0, loop: false, fill: true, tick: 0, ...props })); });
  const clock = () => (el.querySelector("[data-sim-wall-clock]") || {}).textContent;
  draw({});
  await settle(30);
  ok("⭐ SIM WALL DOM: a hidden section reads nothing", calls.length === 0 && !el.querySelector('[data-sim-wall="1"]'));
  draw({ show: true });
  await settle(40);
  ok("⭐ SIM WALL DOM: shown, it reads the plain month once with the lines — no pour, no scenario — as a GET",
     calls.length === 1 && calls[0].url === "/api/sim/day?month=9&legs=1" && calls[0].method === "GET", JSON.stringify(calls));
  const sub = (el.querySelector("[data-sim-wall-sub]") || {}).textContent || "";
  // RELABELLED 17 Oct 2026 (the review): it says the default gate hours now, never 'stood in'
  ok("⭐ SIM WALL DOM: the TV shows the map, the clock at the first lorry, Gates now and the timeline; it says no pour and the default gate hours",
     !!el.querySelector('[data-sim-wall="1"] .sim-map') && clock() === "05:30" && !!el.querySelector("[data-sim-timeline]") && el.querySelectorAll("[data-sim-now-gate]").length === 8
     // NARROWED 17 Oct 2026: the example's 07:00–17:00 is the scheme's default gate hours in test_sim's fixture, said so
     && sub.includes("Sep 2026, an average working day: 312 loads · no pour · gates open 07:00–17:00 (the default: no open hours typed)")
     && !sub.includes("stood in")
     && el.textContent.includes("Staff only · never on the public map") && el.textContent.includes("Planning view, not a record of what happened"), sub);
  ok("🔴 SIM WALL DOM: no scenario control and no table on the TV (nobody touches it): no input, select, scenario card or busiest-hour table",
     el.querySelectorAll("input,select,textarea,button").length === 0 && !el.querySelector("[data-sim-scenario]") && !el.querySelector("[data-sim-table]"));
  frames(11);
  ok("SIM WALL DOM: it plays at 1×: one second of frames is 12 minutes (05:30 → 05:42)", clock() === "05:42", clock());
  frames(700);
  ok("⭐ SIM WALL DOM: in Rotate the day plays ONCE and holds its last picture: 17:30, and no frame asked for after it",
     clock() === "17:30" && queued.size === 0, clock() + " " + queued.size);
  draw({ show: true, pass: 1 });
  await settle(10);
  ok("⭐ SIM WALL DOM: the next pass starts the day again at the first lorry (05:30) and plays", clock() === "05:30" && queued.size === 1, clock());
  frames(11);
  draw({ show: false, pass: 1 });
  frames(20);
  const hiddenAt = clock();
  ok("SIM WALL DOM: hidden, it stops playing (no frame asked for) and reads nothing", queued.size === 0 && hiddenAt === "05:42" && calls.length === 1, hiddenAt);
  draw({ show: true, pass: 1, loop: true });
  await settle(10);
  frames(11);
  ok("SIM WALL DOM: shown again on the same month and refresh it reads nothing more and carries on", calls.length === 1 && clock() === "05:54", clock());
  // from 05:54 the day's end (17:30) is 696 minutes = 58 s = 580 frames away; then the last picture holds 5 s (50 frames)
  frames(600);
  const atEnd = clock();
  frames(40);
  ok("⭐ SIM WALL DOM: in One section it loops: the day's last picture is held 5 s, then the day starts again at the first lorry",
     atEnd === "17:30" && /^05:[34]\d$/.test(clock()), atEnd + " → " + clock());
  const beforeRefresh = clock();
  draw({ show: true, pass: 1, loop: true, tick: 1 });
  await settle(30);
  ok("SIM WALL DOM: the 5-minute refresh reads the day again without restarting the clock",
     calls.length === 2 && calls[1].url === "/api/sim/day?month=9&legs=1" && clock() === beforeRefresh, JSON.stringify(calls.slice(1)) + " " + beforeRefresh + " " + clock());
  frames(30);
  draw({ show: true, pass: 1, loop: true, tick: 1, month: 10 });
  await settle(30);
  ok("SIM WALL DOM: a new month on this display is read and starts at its first lorry",
     calls.length === 3 && calls[2].url === "/api/sim/day?month=10&legs=1" && clock() === "05:30" && (el.querySelector("[data-sim-wall-sub]") || {}).textContent.startsWith("Oct 2026"));
  act(() => { root.unmount(); }); el.remove();
  w.requestAnimationFrame = realRaf; w.cancelAnimationFrame = realCaf;
}

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
  // 17 Oct 2026 (D114): the Dashboard opens on THIS month ± 6, clamped to the horizon — not on every month
  {
    const fromSel = d1.el.querySelector('select[aria-label="From month"]'), toSel = d1.el.querySelector('select[aria-label="To month"]');
    const lo = Math.max(1, thisMonth - 6), hi = Math.min(dMeta.months.count, thisMonth + 6);
    const rbtn = () => d1.el.querySelector("button.dash-range-btn");
    ok("⭐ D114 DOM: the Dashboard opens on this month ± 6 (From and To), clamped to the horizon — was every month",
       !!fromSel && !!toSel && +fromSel.value === lo && +toSel.value === hi && !(lo === 1 && hi === dMeta.months.count),
       `${fromSel && fromSel.value}–${toSel && toSel.value} for ${lo}–${hi}`);
    ok("D114 DOM: ...a 'Whole programme' button beside the range", !!rbtn() && rbtn().textContent === "Whole programme");
    click(rbtn());
    ok("⭐ D114 DOM: 'Whole programme' sets every month of the horizon, and the button turns into 'This month ± 6'",
       +d1.el.querySelector('select[aria-label="From month"]').value === 1
       && +d1.el.querySelector('select[aria-label="To month"]').value === dMeta.months.count && rbtn().textContent === "This month ± 6");
    click(rbtn());
    ok("D114 DOM: ...and 'This month ± 6' brings the default back",
       +d1.el.querySelector('select[aria-label="From month"]').value === lo && +d1.el.querySelector('select[aria-label="To month"]').value === hi
       && rbtn().textContent === "Whole programme");
  }
  d1.done();

  // 17 Oct 2026 (D114 fix): the LIVE path. Mounted with initialData (above) the Dashboard never reads its own lines, so the
  // D114 checks passed while live opened on every month: its first read of /api/costing/lines widened From / To to the
  // lines' own months. Here nothing is handed in, the page reads its lines itself, and the lines' months are built from
  // today's month so the check cannot age.
  {
    const N = dMeta.months.count, lo = Math.max(1, thisMonth - 6), hi = Math.min(N, thisMonth + 6);
    const shift = (ms, status) => ({ ...CL, lines: CL.lines.map((l, i) => ({ ...l, month_index: ms[i % ms.length], ...(status ? { status } : {}) })) });
    // live's shape: approved lines in EVERY month of the horizon (the four-year demo has lines in all 60)
    const everyMonth = { ...CL, lines: Array.from({ length: N }, (_, k) => ({ ...CL.lines[k % CL.lines.length], status: "Approved", month_index: k + 1 })) };
    const inside = [Math.max(lo, thisMonth - 1), thisMonth, Math.min(hi, thisMonth + 1)];   // inside the window, narrower than it
    const baseFetch = w.fetch;
    const openLive = async (lines) => {
      const reads = [];
      w.fetch = (url, opt) => {
        if (String(url).startsWith("/api/costing/lines")) { reads.push(String(url)); return reply(200, lines); }
        return baseFetch(url, opt);
      };
      const m = mount(w.Dashboard, { meta: dMeta });
      await settle(80);
      const fs_ = m.el.querySelector('select[aria-label="From month"]'), ts_ = m.el.querySelector('select[aria-label="To month"]');
      const out = { f: fs_ ? +fs_.value : null, t: ts_ ? +ts_.value : null, reads };
      m.done(); w.fetch = baseFetch;
      return out;
    };
    const e = await openLive(everyMonth);
    ok("⭐ D114 LIVE PATH: mounted WITHOUT initialData, with approved lines in EVERY month (live's shape), the Dashboard reads "
       + "its own lines and STILL opens on this month ± 6 — the old first read widened it to every month, what live showed",
       e.reads.length === 1 && e.reads[0] === "/api/costing/lines?status=All" && e.f === lo && e.t === hi,
       `${e.f}–${e.t} for ${lo}–${hi}; reads ${e.reads}`);
    const a = await openLive(shift(inside));
    ok("D114 LIVE PATH: ...and with every line inside the window it keeps the whole window (it does not narrow to the lines)",
       a.reads.length === 1 && a.f === lo && a.t === hi, `${a.f}–${a.t} for ${lo}–${hi}`);
    // the fallback, on whichever side(s) of the window the horizon leaves room for today (at least one always)
    const sides = [];
    if (lo > 2) sides.push({ name: "finished", ms: [1, 2] });
    if (hi + 2 <= N) sides.push({ name: "not started yet", ms: [hi + 1, hi + 2] });
    const fell = [];
    for (const s of sides) { const r = await openLive(shift(s.ms, "Approved")); fell.push({ s, r }); }
    ok("D114 LIVE PATH: ...and when not one approved line falls inside the window it opens on the months that have lines, "
       + "never on a window with none (a programme finished / not started yet, each side the horizon allows today)",
       sides.length >= 1 && fell.every(({ s, r }) => r.f === s.ms[0] && r.t === s.ms[1]),
       fell.map(({ s, r }) => `${s.name}: ${r.f}–${r.t} for ${s.ms}`).join("; "));
    // the page opens on Approved: Pending lines inside the window do not hold it there when every approved line is outside
    const apOut = sides[0].ms;
    const mixed = { ...CL, lines: CL.lines.map((l, i) => l.status === "Approved" ? { ...l, month_index: apOut[i % 2] } : { ...l, month_index: thisMonth }) };
    const p = await openLive(mixed);
    ok("D114 LIVE PATH: ...the lines counted are the Approved ones (the status the page opens on): Pending lines this month "
       + "do not keep a window whose approved lines are all outside it",
       CL.lines.some(l => l.status === "Pending") && p.f === apOut[0] && p.t === apOut[1], `${p.f}–${p.t} for ${apOut}`);
  }

  // (2) the read lands
  srv.gates = () => reply(200, GA);
  calls.length = 0;
  const d2 = mount(w.Dashboard, { meta: dMeta, initialData: CL });
  await settle(50);
  const redRow = d2.el.querySelector('[data-ga-flag="red"]');
  // NARROWED 14 Oct 2026 (bundle G, W17): the red word is "Over gate capacity" now ("Queue likely" is the 85 % step)
  ok("⭐ GATE DOM: the read lands: three rows, the red row's chip says Over gate capacity, the others Spacing holds / No check-in time typed",
     d2.el.querySelectorAll("[data-ga-gate]").length === 3 && !!d2.el.querySelector('[data-gate-arrivals="set"]')
     && !!redRow && redRow.textContent.includes("Over gate capacity") && redRow.textContent.includes("East compound")
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
  // 14 Oct 2026 (G3): /api/auth/me says the shared codes are still on, so the sign-in screen offers the code form
  w.fetch = (url) => /\/api\/meta$/.test(String(url)) ? respond(meta) : /\/api\/auth$/.test(String(url)) ? respond(PLANNER)
    : /\/api\/auth\/me$/.test(String(url)) ? respond({ signed_in: false, access: null, codes: true }) : new Promise(() => {});
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
  await tick();
  // NARROWED 14 Oct 2026 (G3): the sign-in view opens on email and password; the code form is one click away while
  // the server still has codes (it said so above)
  ok("G3: the sign-in view opens on email and password, with Forgot your password? and, while codes are on, the code link",
     !!box.querySelector('input#auth-email') && !!box.querySelector('input#auth-pass') && !box.querySelector('input[placeholder="Access code"]')
     && [...box.querySelectorAll("button")].some(b => b.textContent === "Forgot your password?")
     && [...box.querySelectorAll("button")].some(b => b.textContent === "Sign in with a team code instead"));
  click([...box.querySelectorAll("button")].find(b => b.textContent === "Sign in with a team code instead"));
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
     // NARROWED 14 Oct 2026: the first column is "Vehicle" (the name), no longer "Vehicle (id)"
     ee.th.includes("Vehicle") && !ee.th.includes("Vehicle (id)") && ee.th.includes("Estonian") && ee.inputs === 2, JSON.stringify(ee));
  const gb = await mount("GB");
  ok("CONFIG (11 Oct 2026 review): ...a GB tenant does not (the country rule stands), English column only",
     gb.th.includes("English") && !gb.th.includes("Estonian") && gb.inputs === 1, JSON.stringify(gb));
  const hdr = headerWith(["en"], "EE");
  ok("CONFIG (11 Oct 2026 review): ...while the header still draws no buttons for that Estonian tenant until a vehicle carries an Estonian name",
     hdr.names.length === 0 && !hdr.seg, JSON.stringify(hdr));
  w.__VEH.langs = ["en"]; w.__TENANT.country = null; w.__VEH.lang = "en"; w.fetch = () => new Promise(() => {});
}

// ---- 13 Oct 2026 (W6, bundle F): row details in a real DOM ---------------------------------------------
// The four busy tables (Look-ahead Commit, Gate arrivals, the Dashboard's route table, Forecasts) and the Dashboard's
// Today rows, mounted from the backend harnesses' own fixtures. Checked here:
//   1. "≤ one ' · ' per rendered cell": every row cell, every details line (<dd>), every cell of the by-day table and
//      of the totals row, in each of the three units (Loads | Tonnes | Lorries) where the table has the switch;
//   2. NOTHING LOST, field by field: every fact the old cells showed (each one formatted as the old cell did, with the
//      app's own helpers) is in the row or in its details row, for every row of every fixture;
//   3. the chevron: a native button with aria-expanded / aria-controls, the details row hidden until it is clicked,
//      the open rows kept for the session (sessionStorage) across an unmount; on the Dashboard it never picks the line;
//   4. the switch: remembered per page (localStorage), one figure a cell, typing a day's plan in Tonnes only;
//   5. the status column: ROAD LIMIT first (Look-ahead, Dashboard, Forecasts), a count of the other flags.
// NOT covered here (jsdom has no layout): the cards below 768 px, the details grid, a real key press reaching a
// native button (jsdom does not turn Enter into a click; the browser matrix and a real keyboard did).
async function rowDetailsDom(){
  const F = w.__F;
  const CL = FIX("cost_lines.json"), GA = FIX("gate_arrivals.json"), LA = FIX("lookahead_page.json"), WK = FIX("lookahead_page_fuel.json"), CTX = FIX("carbon_target.json");
  w.fetch = (url) => (url === "/api/carbon/target" ? reply(200, CTX) : new Promise(() => {}));
  ["dashboard", "forecasts", "lookahead"].forEach(k => w.localStorage.removeItem("modus_units_" + k));
  w.sessionStorage.clear();
  const routes = [];
  CL.lines.forEach(l => { if (!routes.some(r => r.route_id === l.route_id)) routes.push({ route_id: l.route_id, origin: l.origin_name, dest: l.dest_name }); });
  const dMeta = { ...metaMin, routes, vehicles: ["Rigid 8-wheeler (32t)"], factors: { ...metaMin.factors, vehicle_payload_t: { "Rigid 8-wheeler (32t)": 20 } } };
  const laMeta = { ...metaMin, months: { start_year: 2026, count: 60 } };
  const rowsFix = CL.lines.map(l => ({ route_id: l.route_id, discipline: l.discipline, section_id: l.section_id, month_index: l.month_index,
    quantity: l.quantity, unit: l.unit, status: l.status, ipt: l.ipt, material_type: l.material_type, material_description: "Type 1 sub-base",
    vehicle_type: l.vehicle_type, submitted_by: "tester", reject_reason: l.route_id === "R3" ? "Wrong month: move it to November" : null }));
  rowsFix.filter(r => r.route_id === "R3").forEach(r => { r.status = "Rejected"; });
  const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
    act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
  const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
  const dots = (t) => (t.match(/ · /g) || []).length;
  const tableOf = (el, name) => el.querySelector(`table[data-rd-table="${name}"]`);
  // every "cell" a person reads in a row-details table: the row cells, each details line, the by-day and totals cells
  const cellsOf = (table) => {
    const out = [];
    [...table.tBodies[0].rows].forEach(tr => {
      if (tr.classList.contains("rd-details")) {
        tr.querySelectorAll("dd").forEach(dd => { if (!dd.querySelector("table")) out.push(dd); });
        tr.querySelectorAll("table.rd-days td").forEach(td => out.push(td));
      } else [...tr.cells].forEach(td => out.push(td));
    });
    return out;
  };
  const dotCheck = (label, table) => {
    const cells = table ? cellsOf(table) : [];
    const bad = cells.filter(c => dots(norm(c.textContent)) > 1).map(c => norm(c.textContent).slice(0, 90));
    ok(`ROW DETAILS · ≤ one ' · ' per rendered cell: ${label} (${cells.length} cells)`, !!table && cells.length > 0 && bad.length === 0, bad.slice(0, 3).join(" | "));
  };
  const pressUnit = (el, which) => {
    const b = [...el.querySelectorAll("[data-unit-switch] button")].find(x => x.textContent === which);
    if (b) act(() => { b.click(); });
    return !!b;
  };
  // a row and its details row, as one text (the details row is always rendered, hidden while shut)
  // text nodes joined with a space, as a person reads them (textContent runs adjacent cells together: "Mon 28160.0")
  const words = (el) => { const out = []; const it = w.document.createTreeWalker(el, 4); let x; while ((x = it.nextNode())) out.push(x.textContent); return out.join(" "); };
  const rowText = (tr) => tr ? norm(words(tr) + " " + ((tr.nextElementSibling && tr.nextElementSibling.classList.contains("rd-details")) ? words(tr.nextElementSibling) : "")) : "";
  // field by field: one assertion per fact, across every row of the fixture
  const lost = (table, rows) => {          // rows: [{ name, text, facts: [[field, expected], ...] }]
    const byField = {};
    rows.forEach(r => r.facts.forEach(([field, want]) => {
      if (want == null || want === "") return;
      (byField[field] || (byField[field] = { n: 0, miss: [] })).n += 1;
      if (!r.text.includes(norm(want))) byField[field].miss.push(`${r.name}: "${norm(want)}"`);
    }));
    Object.entries(byField).forEach(([field, v]) =>
      ok(`ROW DETAILS · NOTHING LOST · ${table} · ${field} (${v.n} row${v.n === 1 ? "" : "s"})`, v.miss.length === 0, v.miss.slice(0, 2).join(" | ")));
    return Object.keys(byField).length;
  };
  const cur = F.CUR();
  const triple = (u) => !u || u.eur == null ? [] : [u.per_t != null ? `${cur} ${(+u.per_t).toFixed(2)}/t` : null,
    u.per_trip != null ? `${cur} ${F.grp(u.per_trip, 0)}/trip` : null, u.per_km != null ? `${cur} ${(+F.distRate(u.per_km)).toFixed(2)}/${F.DU()}` : null].filter(Boolean);

  // ============================== 1. Look-ahead → Commit ==============================
  const la = mount(w.LookAhead, { meta: laMeta, who: "t", initialPage: LA, initialView: "commit" });
  const laT = tableOf(la.el, "lookahead");
  ok("ROW DETAILS · Look-ahead: the grid is a row-details table with one chevron a line and the switch above it, Tonnes by default",
     !!laT && laT.querySelectorAll("button.rd-chev").length === LA.commit.lines.length
     && la.el.querySelector('[data-unit-switch="tonnes"]') && la.el.querySelector('[data-unit-switch] button[aria-pressed="true"]').textContent === "Tonnes");
  ["Tonnes", "Loads", "Lorries"].forEach(u => { pressUnit(la.el, u); dotCheck(`Look-ahead Commit in ${u}`, tableOf(la.el, "lookahead")); });
  pressUnit(la.el, "Loads");
  const laL = tableOf(la.el, "lookahead");
  ok("ROW DETAILS · Look-ahead in Loads: no day cell can be typed, the bar says to switch, the caption and a cell follow the unit",
     laL.querySelectorAll("button.la-cell").length === 0 && la.el.textContent.includes("Switch to Tonnes to type a day's plan.")
     && laL.querySelector("caption").textContent.startsWith("Loads by day")
     && norm(laL.querySelector(`tr[data-la-line] td[data-label]:not(.rd-status)`).textContent) === F.grp((LA.commit.lines[0].days.find(d => !F.isWeekend(d.day_date)).derived || {}).trips));
  pressUnit(la.el, "Tonnes");
  const unlocked = LA.commit.lines.filter(l => (l.week || {}).status !== "confirmed").length;
  ok("ROW DETAILS · Look-ahead in Tonnes: every unconfirmed line's five days are click-to-type again (decision 2), and the choice is stored for this page",
     tableOf(la.el, "lookahead").querySelectorAll("button.la-cell").length === unlocked * 5 && w.localStorage.getItem("modus_units_lookahead") === "tonnes");
  // nothing lost
  const laRows = LA.commit.lines.map(l => {
    const c = l.context || {}, wd = l.week_derived || {}, wk = l.week || {};
    const lk = `${l.route_id}|${l.discipline || ""}|${l.section_id || ""}|${l.month_index}`;
    const tr = laT.querySelector(`tr[data-la-line="${lk}"]`);
    const fl = (LA.clashes.flags || []).filter(f => `${f.route_id}|${f.discipline || ""}|${f.section_id || ""}|${f.month_index}` === lk);
    const days = (l.days || []).filter(d => !F.isWeekend(d.day_date));
    const facts = [
      ["origin", c.origin_name], ["destination", c.dest_name], ["route id", l.route_id],
      ["team", c.ipt ? F.teamName(F.iptKey(c.ipt)) : null], ["section", c.section_id], ["material", c.material_type],
      ["vehicle (short)", c.vehicle_short || F.vehLabel(c.vehicle_type)], ["vehicle (full name)", c.vehicle_type],
      ["week state", { derived: "Derived", edited: "Edited", confirmed: "Confirmed" }[wk.status]],
      ["parent month changed", wk.parent_changed ? "The parent month's quantity changed after this week was set" : null],
      ["days ≠ week", l.days_ne_week ? F.grp(l.days_sum, 1) : null],
      ["week quantity", `${F.grp(wk.planned_qty, 1)} ${F.unitLbl(l.unit)}`],
    ];
    fl.forEach(f => { facts.push(["flag word", F.flagWord(f, F.LINE_FLAG_LABEL)]); facts.push(["flag sentence (team names, not ids)", F.teamText(f.text)]); });
    days.forEach(d => { const f = d.derived || {};
      facts.push(["day plan", `${F.dayName(d.day_date)} ${F.dayNum(d.day_date)} ${F.grp(d.planned_qty, 1)}`]);
      facts.push(["day trips", F.grp(f.trips)]);
      if (c.baked) facts.push(["day vehicles", F.grp(f.vehicles)]);
      if (d.status === "edited") facts.push(["day typed by hand", "typed by hand"]); });
    if (c.baked) {
      facts.push(["distance a trip", F.grp(F.dist(c.km_trip))], ["outbound only", c.return_baked ? null : "outbound only"],
        ["distance this week", F.grp(F.dist(wd.km))], ["peak vehicles", F.grp(wd.vehicles_peak)], ["tonne-distance", F.grp(F.dist(wd.tonne_km))],
        ["tonne-distance basis", c.km_basis === "loaded" ? "loaded leg" : "round trip"], ["cycle", `${F.grp(c.cycle_min)} min`],
        ["cycle source", c.cycle_source === "here" ? "HERE" : "HERE‡ (return estimated)"], ["cycles a vehicle a day", String(c.cycles_per_vehicle_day)]);
    } else facts.push(["unrouted: payload", `${F.grp(c.payload_t, 1)} t planning payload`]);
    facts.push(["planned cost", wd.eur == null ? "Rate not set" : `${cur} ${F.grp(wd.eur)}`], ["target rate", c.rate_source === "target" && wd.eur != null ? "target rate" : null],
      ["+ BAF", wd.eur_adj != null ? `${cur} ${F.grp(wd.eur_adj)}` : null]);
    if (wd.eur != null && wd.eur_units && wd.eur_units.per_t != null) triple(wd.eur_units).forEach(x => facts.push(["quote per unit", x]));
    if (wd.fair_eur != null && c.fair) {
      facts.push(["fair cost", `${cur} ${F.grp(wd.fair_eur)}`], ["litres a trip", `${F.grp(c.fair.litres_trip, 1)} L`],
        ["diesel price", `${cur}${c.fair.index_eur_per_l}`], ["fuel share", `${F.grp(c.fair.fuel_share_pct)} %`],
        ["winter", (c.fair.flags || []).includes("WINTER") ? "winter" : null], ["thaw", (c.fair.flags || []).includes("THAW") ? "thaw restrictions may apply" : null]);
      if (wd.fair_units && wd.fair_units.per_t != null) triple(wd.fair_units).forEach(x => facts.push(["fair per unit", x]));
    }
    return { name: lk, text: rowText(tr), facts };
  });
  ok("ROW DETAILS · NOTHING LOST · Look-ahead: every fixture line has its row", laRows.every(r => r.text.length > 0));
  const nLa = lost("Look-ahead", laRows);
  // the chevron and the session
  const lk0 = `${LA.commit.lines[0].route_id}|${LA.commit.lines[0].discipline || ""}|${LA.commit.lines[0].section_id || ""}|${LA.commit.lines[0].month_index}`;
  const chev = () => la.el.querySelector(`tr[data-la-line="${lk0}"] button.rd-chev`);
  const det = () => la.el.querySelector(`[data-rd-details="la-${lk0}"]`);
  ok("ROW DETAILS · the chevron is a native button (Enter and Space click it), named, shut, pointing at a hidden details row",
     chev().tagName === "BUTTON" && chev().getAttribute("type") === "button" && chev().getAttribute("aria-expanded") === "false"
     && /^Details for R\d/.test(chev().getAttribute("aria-label")) && chev().getAttribute("aria-controls") === det().id && det().hidden === true);
  act(() => { chev().click(); });
  ok("ROW DETAILS · ...a click opens it: aria-expanded true, the details row shown, the row remembered for the session",
     chev().getAttribute("aria-expanded") === "true" && det().hidden === false && JSON.parse(w.sessionStorage.getItem("modus_rows_lookahead") || "{}")[lk0] === 1);
  la.done();
  const la2 = mount(w.LookAhead, { meta: laMeta, who: "t", initialPage: LA, initialView: "commit" });
  const chev2 = la2.el.querySelector(`tr[data-la-line="${lk0}"] button.rd-chev`);
  ok("ROW DETAILS · ...and it is still open when the page is mounted again (leaving the page and coming back)",
     chev2.getAttribute("aria-expanded") === "true" && la2.el.querySelector(`[data-rd-details="la-${lk0}"]`).hidden === false);
  act(() => { chev2.click(); });
  ok("ROW DETAILS · ...a second click shuts it and forgets it", chev2.getAttribute("aria-expanded") === "false" && !JSON.parse(w.sessionStorage.getItem("modus_rows_lookahead") || "{}")[lk0]);
  la2.done();
  // ROAD LIMIT wins the status, with a count of the other kinds of flag
  const limText = "Artic Tipper (44t) (44 t, loaded) is over the Weight limit 5 t · Back Lane (OpenStreetMap) (+1 more)";
  const l0 = LA.commit.lines[0];
  const LA2 = JSON.parse(JSON.stringify(LA));
  LA2.clashes.flags.push({ code: "LIMIT", label: "ROAD LIMIT", route_id: l0.route_id, month_index: l0.month_index, discipline: l0.discipline || "", section_id: l0.section_id || "",
    ipt: l0.ipt, text: "Pit → Site: " + limText });
  const la3 = mount(w.LookAhead, { meta: laMeta, who: "t", initialPage: LA2, initialView: "commit" });
  const r0 = la3.el.querySelector(`tr[data-la-line="${lk0}"]`);
  const kinds0 = new Set(LA.clashes.flags.filter(f => `${f.route_id}|${f.discipline || ""}|${f.section_id || ""}|${f.month_index}` === lk0).map(f => f.code)).size;
  const st0 = r0.querySelector("td.rd-status .row-st");
  ok("⭐ ROW DETAILS · Look-ahead: a lorry over a road limit is the row's ONE status, ahead of the line's other flags, with their count (decision 1)",
     norm(st0.textContent) === `!ROAD LIMIT+${kinds0}` && st0.getAttribute("data-row-status") === "bad" && r0.querySelectorAll(".row-st").length === 1, norm(st0.textContent));
  const d0 = la3.el.querySelector(`[data-rd-details="la-${lk0}"]`);
  ok("ROW DETAILS · ...and the details spell it out first, the limit sentence in full, then each other flag",
     d0.querySelector(".rd-i.rd-wide dt").textContent === "ROAD LIMIT" && d0.textContent.includes(limText) && d0.querySelectorAll(".rd-i.rd-wide.rd-bad").length >= kinds0 + 1);
  la3.done();

  // ============================== 2. the Dashboard: gates, Today, the route table ==============================
  const GA2 = JSON.parse(JSON.stringify(GA));
  const d = mount(w.Dashboard, { meta: dMeta, initialData: CL, initialGates: GA2, initialWeek: WK, initialTarget: CTX });
  await settle(30);
  dotCheck("Gate arrivals", tableOf(d.el, "gates"));
  dotCheck("Dashboard Today", tableOf(d.el, "today"));
  ["Tonnes", "Loads", "Lorries"].forEach(u => { pressUnit(d.el.querySelector('[data-rd-card="dashboard"]'), u); dotCheck(`Dashboard route table in ${u}`, tableOf(d.el, "dashboard")); });
  // gates, nothing lost
  const gT = tableOf(d.el, "gates");
  const gRows = GA2.gates.map(g => ({ name: g.gate_id, text: rowText(gT.querySelector(`tr[data-ga-gate="${g.gate_id}"]`)), facts: [
    ["location", g.location_name], ["gate", g.gate_name], ...(g.teams || []).map(t => ["team at the gate", F.teamText(t)]),
    ["arrivals a day", F.gaN1(g.arrivals_per_day)], ["laden a day", `Laden a day ${F.gaN1(g.laden_per_day)}`], ["coming to load a day", `Coming to load a day ${F.gaN1(g.empty_per_day)}`],
    ...(g.per_team || []).map(t => ["each team's figure", `${F.teamText(t.team)}, a day ${F.gaN1(t.arrivals_per_day)}`]),
    ["average gap", g.gap_minutes == null ? "No approved arrivals" : `One every ${F.gaMin(g.gap_minutes)} if arrivals are spread evenly`],
    ["check-in", g.gate_minutes == null ? "not typed" : `${+g.gate_minutes} min a lorry`], ["status word", F.gaFlagWord(g)], ["the server's reason", g.reason],
    ["origin share note", g.origin_share_note], ["pending lines", g.pending_lines > 0 ? `${g.pending_lines} pending line${g.pending_lines === 1 ? "" : "s"} would add ${F.gaN1(g.pending_per_day)} a day here once approved.` : null],
  ] }));
  const nGa = lost("Gate arrivals", gRows);
  ok("ROW DETAILS · Gate arrivals: three gates or more get a '+N more' chip, never a third chip",
     [...gT.querySelectorAll("tr.rd-row")].every(tr => tr.querySelectorAll(".rd-chip").length <= 2));
  // Today, nothing lost
  const tT = tableOf(d.el, "today");
  const todayRows = [];
  WK.commit.lines.forEach(l => (l.days || []).forEach(dd => { if (dd.day_date === WK.today && ((dd.planned_qty || 0) > 0 || dd.actual_qty != null)) todayRows.push({ l, dd }); }));
  const tdRows = todayRows.map(({ l, dd }) => { const ctx = l.context || {}, dv = dd.derived || {};
    const key = `${l.route_id}|${l.discipline || ""}|${l.section_id || ""}`;
    return { name: key, text: rowText(tT.querySelector(`tr[data-rd="today-${key}"]`)), facts: [
      ["route id", l.route_id], ["origin", ctx.origin_name], ["destination", ctx.dest_name], ["material", l.material_type], ["discipline", l.discipline],
      ["vehicle", ctx.vehicle_short || l.vehicle_type], ["tonnes", F.grp(dv.tonnes)], ["trips", dv.trips == null ? null : F.grp(dv.trips)],
      ["vehicles", dv.vehicles == null ? null : String(dv.vehicles)], ["planned today (old title)", `${F.grp(dd.planned_qty)} ${F.unitLbl(l.unit)}`],
      ["reported (old title)", dd.actual_qty != null ? `${F.grp(dd.actual_qty)} ${F.unitLbl(l.unit)}` : "Not reported yet"],
      ["not routed (old title)", ctx.baked ? null : "not worked out yet, so no distance or vehicles"],
      ["status word", dd.actual_qty != null ? "reported" : dd.status === "confirmed" ? "confirmed" : dd.status === "edited" ? "edited" : "planned"],
    ] }; });
  const nTd = lost("Dashboard Today", tdRows);
  // the route table, nothing lost: the Dashboard's own sums over the fixture's Approved lines (its default filter)
  const rT = tableOf(d.el, "dashboard");
  const agg = {};
  CL.lines.filter(l => l.status === "Approved").forEach(l => {
    const k = `${l.route_id}|${l.discipline || ""}|${l.section_id || ""}`;
    const a = agg[k] || (agg[k] = { l, t: 0, trips: 0, km: 0, co2: 0, peak: null, planned: null, fair: null, source: null, flags: new Set(), actualT: null, bkm: 0 });
    a.t += l.tonnes; a.trips += l.trips; a.km += l.km || 0; a.co2 += l.co2_t || 0; a.bkm += (l.basis_km || 0) * l.trips;
    if (l.vehicles != null) a.peak = Math.max(a.peak || 0, l.vehicles);
    if (l.planned && l.planned.eur != null) { a.planned = (a.planned || 0) + l.planned.eur; a.source = l.planned.source; }
    if (l.fair && l.fair.eur != null) { a.fair = (a.fair || 0) + l.fair.eur; (l.fair.flags || []).forEach(x => a.flags.add(x)); }
    if (l.actual_tonnes != null) a.actualT = (a.actualT || 0) + l.actual_tonnes;
  });
  const per = (eur, a) => eur == null ? null : { eur, per_t: a.t > 0 ? eur / a.t : null, per_trip: a.trips > 0 ? eur / a.trips : null, per_km: a.bkm > 0 ? eur / a.bkm : null };
  const dRows = Object.entries(agg).map(([k, a]) => { const l = a.l;
    const facts = [["route id", l.route_id], ["origin", l.origin_name], ["destination", l.dest_name], ["vehicle (short)", l.vehicle_short || F.vehLabel(l.vehicle_type)],
      ["vehicle (full name)", l.vehicle_type], ["discipline", l.discipline], ["section (old title)", l.section_id], ["team", l.ipt ? F.teamText(l.ipt) : null],
      ["distance a trip", l.km_trip == null ? "Not routed yet for this lorry" : (+F.dist(l.km_trip)).toFixed(1)],
      ["cycle", l.cycle_min == null ? "Needs this line's route worked out" : (l.cycle_min / 60).toFixed(2)], ["tonnes", F.grp(a.t)], ["trips", F.grp(a.trips)],
      ["delivered %", a.actualT != null && a.t > 0 ? `${(a.actualT * 100 / a.t).toFixed(0)} %` : null],
      ["delivered (old title)", a.actualT == null ? "No week actual reported on this line in the months in view" : `${F.grp(a.actualT)} t reported of ${F.grp(a.t)} t planned`],
      ["lorry-distance", l.baked ? F.grp(F.dist(a.km)) : null], ["tCO₂e", l.baked ? a.co2.toFixed(1) : null], ["peak vehicles", a.peak == null ? null : String(a.peak)],
      ["trips a day per vehicle (old title)", l.cycles_per_vehicle_day ? String(l.cycles_per_vehicle_day) : null],
      ["planned", a.planned == null ? "rate not set" : `${cur} ${F.grp(a.planned)}`], ["quote / target tag", a.source === "target" ? "target" : a.source === "route" ? "quote" : null],
      ["fair", a.fair == null ? (l.baked ? "No diesel index" : "Not routed yet, so no distance") : `${cur} ${F.grp(a.fair)}`],
      ["fair per tonne", a.fair != null && a.t > 0 ? (a.fair / a.t).toFixed(2) : null], ["winter", a.flags.has("WINTER") ? "winter" : null], ["thaw", a.flags.has("THAW") ? "thaw" : null]];
    triple(per(a.planned, a)).forEach(x => facts.push(["planned per unit (old title)", x]));
    triple(per(a.fair, a)).forEach(x => facts.push(["fair per unit (old title)", x]));
    return { name: k, text: rowText(rT.querySelector(`tr[data-rd="dash-${k}"]`)), facts }; });
  const nDash = lost("Dashboard route table", dRows);
  // the switch on the Dashboard
  const rCard = () => d.el.querySelector('[data-rd-card="dashboard"]');
  pressUnit(rCard(), "Loads");
  const firstKey = Object.keys(agg)[0];
  const qCell = () => d.el.querySelector(`tr[data-rd="dash-${firstKey}"] td.num`);
  ok("ROW DETAILS · Dashboard: Loads makes the quantity column loads (its header says so) and is stored for this page only",
     norm(qCell().textContent) === F.grp(agg[firstKey].trips) && w.localStorage.getItem("modus_units_dashboard") === "loads"
     && [...tableOf(d.el, "dashboard").querySelectorAll("thead th")][1].textContent.startsWith("Loads") && w.localStorage.getItem("modus_units_forecasts") === null);
  // the chevron never picks the line; the row still does
  const rowEl = () => d.el.querySelector(`tr[data-rd="dash-${firstKey}"]`);
  act(() => { rowEl().querySelector("button.rd-chev").click(); });
  ok("ROW DETAILS · Dashboard: the chevron opens the details and does NOT focus the charts on the line",
     !rowEl().classList.contains("is-picked") && rowEl().querySelector("button.rd-chev").getAttribute("aria-expanded") === "true");
  act(() => { rowEl().querySelector("td.num").click(); });
  ok("ROW DETAILS · ...a click on the row itself still does", rowEl().classList.contains("is-picked"));
  const sortSel = d.el.querySelector('select[aria-label="Sort the route table by"]');
  ok("ROW DETAILS · Dashboard: the 'Sort by' list keeps all 13 of the old headers' sorts (decision 4)",
     !!sortSel && [...sortSel.options].map(o => o.value).join(",") === "route_id,discipline,t,trips,peakVeh,deliveredPct,dist,cycleH,km,co2,planned,fair,fairPerT");
  d.done();
  const d2 = mount(w.Dashboard, { meta: dMeta, initialData: CL, initialGates: GA2, initialWeek: WK, initialTarget: CTX });
  await settle(30);
  ok("ROW DETAILS · ...the Dashboard comes back in Loads, with that row's details still open",
     d2.el.querySelector('[data-rd-card="dashboard"] button[aria-pressed="true"]').textContent === "Loads"
     && d2.el.querySelector(`tr[data-rd="dash-${firstKey}"] button.rd-chev`).getAttribute("aria-expanded") === "true");
  d2.done();
  // ROAD LIMIT on the Dashboard's route table
  const CLL = JSON.parse(JSON.stringify(CL));
  const limLine = CLL.lines.find(l => l.baked && l.status === "Approved");
  CLL.lines.filter(l => l.route_id === limLine.route_id && l.vehicle_type === limLine.vehicle_type).forEach(l => { l.limit = { count: 2, text: limText, kind: "weight", checked_at: "2026-10-13T09:00:00Z" }; });
  const d3 = mount(w.Dashboard, { meta: dMeta, initialData: CLL, initialTarget: CTX });
  await settle(30);
  const limKey = `${limLine.route_id}|${limLine.discipline || ""}|${limLine.section_id || ""}`;
  const limRow = d3.el.querySelector(`tr[data-rd="dash-${limKey}"]`);
  ok("⭐ ROW DETAILS · Dashboard: a line whose lorry is over a road limit reads ROAD LIMIT in its status, the sentence in its details (decision 3)",
     limRow.querySelector(".row-st").getAttribute("data-row-status") === "bad" && norm(limRow.querySelector(".row-st").textContent) === "!ROAD LIMIT"
     && rowText(limRow).includes(limText) && rowText(limRow).includes("Checked 13 Oct 2026"));
  const others = [...d3.el.querySelectorAll('table[data-rd-table="dashboard"] tr.rd-row')].filter(tr => tr !== limRow).map(tr => norm(tr.querySelector(".row-st").textContent));
  ok("ROW DETAILS · ...the other lines read Clear or Not routed, nothing else", others.length > 0 && others.every(x => x === "✓Clear" || x === "!Not routed"), others.join("|"));
  d3.done();

  // ============================== 3. Forecasts ==============================
  const f = mount(w.Forecasts, { meta: dMeta, who: "tester", access: plannerAcc, onEdit(){}, onChanged(){}, initialRows: rowsFix, initialCost: CL, initialTarget: CTX });
  ["Tonnes", "Loads", "Lorries"].forEach(u => { pressUnit(f.el, u); dotCheck(`Forecasts in ${u}`, tableOf(f.el, "forecasts")); });
  pressUnit(f.el, "Tonnes");
  const fT = tableOf(f.el, "forecasts");
  const fg = {};
  rowsFix.forEach(r => { const k = [r.route_id, r.discipline || "", r.section_id || ""].join("|");
    const g = fg[k] || (fg[k] = { r, n: 0, q: 0, min: r.month_index, max: r.month_index, st: new Set() });
    g.n += 1; g.q += +r.quantity || 0; g.min = Math.min(g.min, r.month_index); g.max = Math.max(g.max, r.month_index); g.st.add(r.status); });
  const fc = {};
  CL.lines.forEach(l => { const k = [l.route_id, l.discipline || "", l.section_id || ""].join("|");
    const e = fc[k] || (fc[k] = { t: 0, trips: 0, bkm: 0, planned: null, fair: null, source: null, baked: 0, n: 0, flags: new Set() });
    e.n += 1; e.t += l.tonnes || 0; e.trips += l.trips || 0; e.bkm += (l.basis_km || 0) * (l.trips || 0); if (l.baked) e.baked += 1;
    if (l.planned && l.planned.eur != null) { e.planned = (e.planned || 0) + l.planned.eur; e.source = l.planned.source; }
    if (l.fair && l.fair.eur != null) { e.fair = (e.fair || 0) + l.fair.eur; (l.fair.flags || []).forEach(x => e.flags.add(x)); } });
  const fRows = Object.entries(fg).map(([k, g]) => { const r = g.r, c = fc[k] || {}, rt = routes.find(x => x.route_id === r.route_id) || {};
    const yr = (mi) => 2026 + Math.floor((mi - 1) / 12), years = yr(g.min) === yr(g.max) ? String(yr(g.min)) : `${yr(g.min)}–${yr(g.max)}`;
    const status = g.st.size === 1 ? [...g.st][0] : "Mixed";
    const pu = c.planned != null ? { eur: c.planned, per_t: c.t > 0 ? c.planned / c.t : null, per_trip: c.trips > 0 ? c.planned / c.trips : null, per_km: c.bkm > 0 ? c.planned / c.bkm : null } : null;
    const fu = c.fair != null ? { eur: c.fair, per_t: c.t > 0 ? c.fair / c.t : null, per_trip: c.trips > 0 ? c.fair / c.trips : null, per_km: c.bkm > 0 ? c.fair / c.bkm : null } : null;
    const facts = [["route id", r.route_id], ["discipline", r.discipline], ["section", r.section_id], ["origin", rt.origin], ["destination", rt.dest],
      ["team", r.ipt ? F.teamText(r.ipt) : "No team"], ["material", r.material_type], ["description (old title)", r.material_description],
      ["vehicle", F.vehLabel(r.vehicle_type)], ["vehicle (full name, old title)", r.vehicle_type], ["months", `${g.n}, ${years}`],
      ["total as typed", `${F.fmt(g.q, r.unit)} ${r.unit === "m3" ? "m³" : r.unit}`],
      ["planned", c.planned == null ? "rate not set" : `${cur} ${F.grp(c.planned)}`], ["target tag", c.source === "target" ? "target" : null],
      ["fair", c.fair == null ? (c.baked < c.n ? "Not routed yet for this vehicle, so no distance and no fair price" : "No diesel index") : `${cur} ${F.grp(c.fair)}`],
      ["status", status], ["reject reason (old title, full)", r.reject_reason], ["submitted by (old row title)", "tester (you)"]];
    triple(pu).forEach(x => facts.push(["planned per unit (old title)", x]));
    triple(fu).forEach(x => facts.push(["fair per unit (old title)", x]));
    return { name: k, text: rowText(fT.querySelector(`tr[data-fc-line="${k}"]`)), facts }; });
  const nFc = lost("Forecasts", fRows);
  const stOf = (k) => norm(fT.querySelector(`tr[data-fc-line="${k}"] .row-st`).textContent);
  const rej = Object.keys(fg).find(k => k.startsWith("R3|"));
  ok("ROW DETAILS · Forecasts: a rejected line's status reads Rejected (red), its reason in full in the details",
     stOf(rej) === "!Rejected" && rowText(fT.querySelector(`tr[data-fc-line="${rej}"]`)).includes("Wrong month: move it to November"));
  f.done();
  const f2 = mount(w.Forecasts, { meta: dMeta, who: "tester", access: plannerAcc, onEdit(){}, onChanged(){}, initialRows: rowsFix, initialCost: CLL, initialTarget: CTX });
  const fT2 = tableOf(f2.el, "forecasts");
  const limFk = [limLine.route_id, limLine.discipline || "", limLine.section_id || ""].join("|");
  const limFr = fT2.querySelector(`tr[data-fc-line="${limFk}"]`);
  ok("⭐ ROW DETAILS · Forecasts: the same line reads ROAD LIMIT before Pending or Approved, so an approver sees it first; the sentence in the details",
     norm(limFr.querySelector(".row-st").textContent) === "!ROAD LIMIT" && rowText(limFr).includes(limText) && rowText(limFr).includes("Approval"));
  f2.done();
  ok("ROW DETAILS · the nothing-lost checks covered every table: Look-ahead, gates, Today, the route table and Forecasts each with ten fields or more",
     [nLa, nGa, nTd, nDash, nFc].every(n => n >= 10), [nLa, nGa, nTd, nDash, nFc].join(" / "));
  w.fetch = () => new Promise(() => {});
}

// ---- 13 Oct 2026 (speed): the compiled app kept in the browser ----------------------------------------------
// The small plain script after the app compiles the app once and keeps it in localStorage (modus_app_js), keyed by
// a hash of the app's text and Babel's version. Run here in a fresh jsdom per "page load", with a stand-in Babel
// that counts its compiles: the first load compiles and keeps; the next one runs the kept code and compiles
// nothing; a changed app compiles again and REPLACES the one entry; with storage refusing writes it still runs;
// a compile that throws falls back to Babel's own pass. Not covered: the real Babel's output (the browser check,
// 13 Oct: first load 1.4 s, later loads 0.14 s to the first read, every page working).
function keptAppLoader(){
  const loader = (html.match(/<\/script>\n<script>\n(\/\* 13 Oct 2026 \(speed\)[\s\S]*?)<\/script>\n<\/body>/) || [])[1];
  ok("SPEED: the loader is the plain script right after the app, before </body>", !!loader && html.includes('<script type="text/babel" data-presets="react">'));
  if (!loader) return;
  const page = (appSrc, store, babelOpts) => {
    const d = new JSDOM(`<!doctype html><html><body><div id="root"></div><script type="text/babel" data-presets="react">${appSrc}</script></body></html>`,
                        { runScripts: "dangerously", url: "https://wayscope.test/" });   // the loader appends a <script>: it must run, as in a browser
    const win = d.window;
    const calls = { transform: 0, disabled: 0, fallback: 0, presets: null };
    const realLs = win.localStorage;
    Object.entries(store).forEach(([k, v]) => realLs.setItem(k, v));
    if (babelOpts && babelOpts.refuseWrites) {
      Object.defineProperty(win, "localStorage", { value: { getItem: (k) => realLs.getItem(k), setItem: () => { throw new Error("QuotaExceededError"); }, removeItem: (k) => realLs.removeItem(k) } });
    }
    win.Babel = { version: (babelOpts && babelOpts.version) || "7.23.10",
      disableScriptTags(){ calls.disabled += 1; },
      transformScriptTags(){ calls.fallback += 1; },
      transform(src, opts){ calls.transform += 1; calls.presets = opts.presets;
        if (babelOpts && babelOpts.throws) throw new Error("boom");
        return { code: `window.RAN = (window.RAN || 0) + 1; window.SRC = ${JSON.stringify(src)};` }; } };
    win.eval(loader);
    const out = {}; for (let i = 0; i < realLs.length; i++) out[realLs.key(i)] = realLs.getItem(i === -1 ? "" : realLs.key(i));
    return { win, calls, store: out };
  };
  const p1 = page("APP v1", {});
  ok("SPEED: the first load compiles once with the script's presets, keeps the result, and runs it once (Babel's own pass is switched off)",
     p1.calls.disabled === 1 && p1.calls.transform === 1 && JSON.stringify(p1.calls.presets) === '["react"]' && p1.win.RAN === 1
     && p1.win.SRC === "APP v1" && p1.win.MODUS_APP_FROM === "compiled" && JSON.parse(p1.store.modus_app_js).code.includes("window.RAN"));
  const p2 = page("APP v1", p1.store);
  ok("⭐ SPEED: the next load runs the kept code and compiles nothing", p2.calls.transform === 0 && p2.win.RAN === 1 && p2.win.MODUS_APP_FROM === "kept");
  const p3 = page("APP v2", p2.store);
  ok("SPEED: a changed app (a deploy) compiles again and replaces the one entry: storage never grows",
     p3.calls.transform === 1 && p3.win.SRC === "APP v2" && Object.keys(p3.store).filter(k => k.startsWith("modus_app")).length === 1
     && JSON.parse(p3.store.modus_app_js).k !== JSON.parse(p2.store.modus_app_js).k);
  const p4 = page("APP v2", p3.store, { version: "7.99.0" });
  ok("SPEED: a different Babel version never reuses code compiled by another", p4.calls.transform === 1 && p4.win.MODUS_APP_FROM === "compiled");
  const p5 = page("APP v3", {}, { refuseWrites: true });
  ok("SPEED: with storage refusing the write (a full quota, a private window) the app still runs, compiled", p5.win.RAN === 1 && p5.calls.fallback === 0);
  const p6 = page("APP v4", {}, { throws: true });
  ok("SPEED: a compile that throws falls back to Babel's own pass, so the page behaves exactly as before",
     p6.calls.fallback === 1 && !p6.win.RAN && p6.win.MODUS_APP_FROM === "babel");
  const p7 = page("APP v1", { modus_app_js: "{not json" });
  ok("SPEED: a damaged kept entry is ignored and replaced", p7.calls.transform === 1 && p7.win.RAN === 1 && JSON.parse(p7.store.modus_app_js).k);
}

// ---- 14 Oct 2026 (D9, the mobile shell): the Portal on a phone, in a real DOM ---------------------------------------
// The Portal mounted with matchMedia answering "(max-width: 767px)", once as a team code (the stand's "demo" visitor:
// role ipt, cannot approve) and once as the planner, then turned to a desktop width through the same media query's
// change event. The Look-ahead reads the backend harness's own fixture (lookahead_page.json); every other read never
// settles. Checked: no rail on a phone, the four tabs in the tenant's words, the desk pages as the "open on a desktop"
// card (the page itself never mounted), the phone Look-ahead's day strip, figures, order, team names and details, the
// Day sheet's request, and that NOTHING on a phone can write: no input, select or textarea, no write button, no fetch
// with a method. NOT covered (jsdom has no layout): the 48 px boxes, no sideways scroll, the looks and accents — the
// browser matrix measured those (notes/session-1014-mobile-shell.md).
async function phoneShellDom(){
  const LA = FIX("lookahead_page.json"), CL = FIX("cost_lines.json");
  const calls = [];
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || "GET" });
    if (/\/api\/lookahead\?bucket=commit$/.test(String(url))) return reply(200, LA);
    if (/\/api\/costing\/lines\?status=All$/.test(String(url))) return reply(200, CL);
    if (/\/api\/forecast-weeks\/day-sheet\?/.test(String(url))) return reply(200, "pdf");
    return new Promise(() => {});
  };
  w.URL.createObjectURL = () => "blob:day-sheet"; w.URL.revokeObjectURL = () => {};
  let mqHandler = null, narrowNow = true;
  const mm = w.matchMedia;
  w.matchMedia = (q) => ({ get matches(){ return q === "(max-width: 767px)" && narrowNow; }, media: q,
    addListener(f){ if(q === "(max-width: 767px)") mqHandler = f; }, removeListener(){},
    addEventListener(t, f){ if(q === "(max-width: 767px)") mqHandler = f; }, removeEventListener(){} });
  const TEAM_ACC = { role: "ipt", label: "North Team", ipt: "IPT1", can_approve: false, ipt_locked: true, ipt_required: false, demo: false, ipts: ["IPT1", "IPT2"] };
  const meta = { ...metaMin, months: { start_year: 2026, count: 60 } };
  const mountPortal = async (role, pageId) => {
    w.localStorage.setItem("modus_page", pageId || "dashboard");
    try { w.history.replaceState(null, "", "#" + (pageId || "dashboard")); } catch(e){}
    const el = w.document.createElement("div"); w.document.body.appendChild(el);
    const r = w.ReactDOM.createRoot(el);
    await act(async () => { r.render(w.React.createElement(w.Portal, { role, who: "Tester", meta, metaErr: false, vehLang: "en", onPage(){} })); });
    await settle(5);
    return { el, done: async () => { await act(async () => { r.unmount(); }); el.remove(); } };
  };
  const tabs = (el) => [...el.querySelectorAll("nav.phone-tabs > button")];
  const tabText = (b) => b.querySelector("span").textContent.trim();
  const WRITE_WORDS = /^(Confirm|Re-open|Export|Save|Submit|Approve|Reject|Delete|Add|check now|re-check|Spread)/i;

  // -- a team code on a phone
  const t = await mountPortal(TEAM_ACC, "dashboard");
  ok("⭐ PHONE: below 768 px the rail is not drawn; a bottom tab bar of four is (Dashboard, Look-ahead, Route map, More), the NAV's own words",
     !t.el.querySelector("aside.rail") && tabs(t.el).map(tabText).join("|") === "Dashboard|Look-ahead|Route map|More"
     && t.el.querySelector("nav.phone-tabs").getAttribute("aria-label") === "Pages");
  ok("PHONE: the open page's tab is marked (aria-current=page and is-on); More says whether its sheet is open",
     tabs(t.el)[0].getAttribute("aria-current") === "page" && tabs(t.el)[0].classList.contains("is-on")
     && tabs(t.el)[3].getAttribute("aria-expanded") === "false" && tabs(t.el)[3].getAttribute("aria-controls") === "phone-more");
  ok("PHONE: the Dashboard has no big-screen switch on a phone (the Dashboard itself is drawn: its six cards)", !!t.el.querySelector('[data-guide="dash-figures"]') && !t.el.querySelector('[data-guide="dash-wall"]')
     && ![...t.el.querySelectorAll("button")].some(b => /Big screen/.test(b.textContent)));
  await act(async () => { tabs(t.el)[1].dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await settle(5);
  const ph = () => t.el.querySelector('[data-phone-page="lookahead"]');
  ok("⭐ PHONE: the Look-ahead tab opens the phone Look-ahead (one read of /lookahead), not the desk grid",
     !!ph() && !t.el.querySelector('[data-rd-table="lookahead"]') && !t.el.querySelector('[data-guide="lookahead-tabs"]')
     && calls.some(c => c.url === "/api/lookahead?bucket=commit" && c.method === "GET"));
  const dayBtns = () => [...ph().querySelectorAll(".ph-days > button")];
  const shown = () => (dayBtns().find(b => b.getAttribute("aria-pressed") === "true") || {}).textContent;
  const weekdays = LA.commit.lines[0].days.map(d => d.day_date).filter(iso => !w.__F.isWeekend(iso));
  ok("PHONE: the date strip is the week's five weekdays, today pressed first (the fixture's today)",
     dayBtns().length === 5 && dayBtns().map(b => b.textContent).join("|") === weekdays.map(iso => w.__F.dayName(iso) + w.__F.dayNum(iso)).join("|")
     && shown() === w.__F.dayName(LA.today) + w.__F.dayNum(LA.today) && ph().querySelector("[data-ph-day]").getAttribute("data-ph-day") === LA.today);
  // the day's figures are the server's own, summed over the lines with something planned that day
  const dayRows = (iso) => LA.commit.lines.map(l => ({ l, d: l.days.find(x => x.day_date === iso) }))
    .filter(x => x.d && ((+x.d.planned_qty || 0) > 0 || ((x.d.derived || {}).trips || 0) > 0));
  const figs = () => [...ph().querySelectorAll(".ph-figs > span")].map(s => s.textContent.replace(/\s+/g, " ").trim());
  const sumOf = (rows, k) => rows.reduce((a, x) => a + ((x.d.derived || {})[k] || 0), 0);
  const rT = dayRows(LA.today);
  ok("⭐ PHONE: the day card's figures are the server's for that day: tonnes, loads, lorries (routed lines), lines",
     figs().join("|") === [`${w.__F.grp(sumOf(rT, "tonnes"))}t`, `${w.__F.grp(sumOf(rT, "trips"))}loads`,
                           `${rT.some(x => x.l.context.baked) ? w.__F.grp(rT.filter(x => x.l.context.baked).reduce((a, x) => a + (x.d.derived.vehicles || 0), 0)) : "—"}${rT.some(x => !x.l.context.baked) && rT.some(x => x.l.context.baked) ? "lorries, routed lines" : "lorries"}`,
                           `${rT.length}line${rT.length === 1 ? "" : "s"}`].join("|"), figs().join("|"));
  const lineEls = () => [...ph().querySelectorAll(".ph-line")];
  const tonnesOf = (el) => { const k = el.getAttribute("data-ph-line"); const x = rT.find(y => `${y.l.route_id}|${y.l.discipline || ""}|${y.l.section_id || ""}|${y.l.month_index}` === k); return x ? (x.d.derived.tonnes || 0) : -1; };
  ok("PHONE: one row per line planned that day, heaviest first",
     lineEls().length === Math.min(rT.length, 6) && lineEls().every((e, i, a) => i === 0 || tonnesOf(a[i - 1]) >= tonnesOf(e)));
  ok("🔴 PHONE: team NAMES on the phone Look-ahead, never an id", !/\bIPT ?\d\b/i.test(ph().textContent) && /Team \d|North Team|No team/i.test(ph().textContent));
  const first = lineEls()[0], fb = first.querySelector("button"), fdl = first.querySelector("dl");
  ok("PHONE: a line's facts are shut until it is tapped (a native button, aria-expanded / aria-controls)",
     fb.getAttribute("aria-expanded") === "false" && fdl.hidden === true && fb.getAttribute("aria-controls") === fdl.id);
  click(fb);
  ok("PHONE: ...and a tap shows them (route, vehicle, plan, lorries, the week's state)",
     fb.getAttribute("aria-expanded") === "true" && fdl.hidden === false && /Route/.test(fdl.textContent) && /Plan/.test(fdl.textContent) && /This week/.test(fdl.textContent));
  const other = weekdays.find(iso => iso !== LA.today);
  click(dayBtns().find(b => b.textContent === w.__F.dayName(other) + w.__F.dayNum(other)));
  ok("PHONE: another day in the strip shows that day's card (and shuts the open facts)",
     ph().querySelector("[data-ph-day]").getAttribute("data-ph-day") === other && shown() === w.__F.dayName(other) + w.__F.dayNum(other)
     && [...ph().querySelectorAll(".ph-line > button")].every(b => b.getAttribute("aria-expanded") === "false"));
  // nothing on a phone writes: no input, no select, no textarea, no write button, no request with a method
  const writeBtns = (el) => [...el.querySelectorAll("button")].filter(b => WRITE_WORDS.test(b.textContent.trim()));
  ok("⭐ PHONE WATCHER: the phone Look-ahead has no input, select or textarea and no write button (Confirm, Re-open, Save…)",
     !ph().querySelector("input, select, textarea") && writeBtns(ph()).length === 0, writeBtns(ph()).map(b => b.textContent).join(","));
  await act(async () => { [...ph().querySelectorAll("button")].find(b => /Day sheet/.test(b.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await settle(5);
  ok("⭐ PHONE: the Day sheet asks for the shown day of the open week (a GET; the file is named after the day)",
     calls.some(c => c.url === `/api/forecast-weeks/day-sheet?bucket=commit&day=${other}` && c.method === "GET"));
  ok("🔴 PHONE WATCHER: not one request from the phone pages carries a method other than GET", calls.every(c => c.method === "GET"),
     calls.filter(c => c.method !== "GET").map(c => c.method + " " + c.url).join(", "));
  // More: the desk pages, each the card on a phone
  click(tabs(t.el)[3]);
  const sheet = () => t.el.querySelector("#phone-more");
  ok("PHONE: More opens a sheet (a dialog) with the pages made for a desk this role can see, and the user guide",
     !!sheet() && sheet().getAttribute("role") === "dialog" && tabs(t.el)[3].getAttribute("aria-expanded") === "true"
     && [...sheet().querySelectorAll("button.phone-more-item span:not(.pm-note)")].map(s => s.textContent).join("|") === "Submit forecast|Forecasts|Carbon planner"
     && !!sheet().querySelector('a[href^="/help/?role="][target="_blank"]'));
  ok("PHONE: ...a team code's sheet holds no Data or Config page (the role's own pages only)", !/Locations|Routes|Zones|Config/.test(sheet().textContent));
  await act(async () => { w.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  ok("PHONE: Escape shuts the sheet", !sheet() && tabs(t.el)[3].getAttribute("aria-expanded") === "false");
  click(tabs(t.el)[3]);
  click([...sheet().querySelectorAll("button.phone-more-item")].find(b => /Forecasts/.test(b.textContent)));
  const desk = () => t.el.querySelector("[data-desk-only]");
  ok("⭐ PHONE: a desk page on a phone is the card \"Open on a desktop to edit this.\" with its own name, never the page",
     !!desk() && desk().querySelector("h2").textContent === "Forecasts" && /Open on a desktop to edit this\./.test(desk().textContent)
     && !t.el.querySelector('[data-rd-table="forecasts"], table') && !sheet() && w.location.hash === "#forecasts" && tabs(t.el)[3].classList.contains("is-on"));
  ok("🔴 PHONE WATCHER: the desk card has no input and no write button (hidden, not disabled)",
     !t.el.querySelector("main input, main select, main textarea") && writeBtns(t.el.querySelector("main")).length === 0
     && ![...t.el.querySelectorAll("main button")].some(b => b.disabled));
  click([...desk().querySelectorAll("button")].find(b => /Go to the Dashboard/.test(b.textContent)));
  ok("PHONE: its button goes back to the Dashboard", !desk() && tabs(t.el)[0].classList.contains("is-on") && w.location.hash === "#dashboard");
  // a desk page opened by its address (#submit) on a phone is the card too
  await t.done();
  const s2 = await mountPortal(TEAM_ACC, "submit");
  ok("PHONE: a desk page opened by its address (#submit) is the card as well, the matrix never mounted",
     !!s2.el.querySelector("[data-desk-only]") && s2.el.querySelector("[data-desk-only] h2").textContent === "Submit forecast" && !s2.el.querySelector("main input, main select"));
  await s2.done();

  // -- the planner on a phone: the Data pages and Config are desk pages too
  const p = await mountPortal(plannerAcc, "dashboard");
  click(tabs(p.el)[3]);
  // NARROWED 14 Oct 2026 (merged with G3): a planner on a shared CODE also sees Users (G3's first-admin step), a desk page too
  ok("PHONE: the planner's sheet adds the Data pages, Config and Users (each a desk page)",
     [...p.el.querySelectorAll("#phone-more button.phone-more-item span:not(.pm-note)")].map(s => s.textContent).join("|") === "Submit forecast|Forecasts|Carbon planner|Locations|Routes|Zones|Config|Users");
  click([...p.el.querySelectorAll("#phone-more button.phone-more-item")].find(b => /Users/.test(b.textContent)));
  ok("PHONE (with G3): Users on a phone is the card, the Users page never mounted",
     !!p.el.querySelector("[data-desk-only]") && p.el.querySelector("[data-desk-only] h2").textContent === "Users" && !p.el.querySelector("main table, main input"));
  click(tabs(p.el)[3]);
  click([...p.el.querySelectorAll("#phone-more button.phone-more-item")].find(b => /Config/.test(b.textContent)));
  ok("PHONE: Config on a phone is the card (the Config page, its Save and its JSON never mount)",
     !!p.el.querySelector("[data-desk-only]") && !/Everything \(JSON\)/.test(p.el.textContent) && !p.el.querySelector("main textarea"));
  // turned sideways past 768 px (the media query changes): the desk shell, the rail and the page itself
  narrowNow = false;
  await act(async () => { if (mqHandler) mqHandler({ matches: false }); });
  await settle(5);
  ok("⭐ PHONE → DESK: past 768 px the rail is back, the tab bar gone, and the desk page itself mounts (no card)",
     !!p.el.querySelector("aside.rail") && !p.el.querySelector("nav.phone-tabs") && !p.el.querySelector("[data-desk-only]") && !p.el.querySelector("#phone-more"));
  await p.done();
  w.matchMedia = mm;
}

// ---- 17 Oct 2026: the phone day card shows that DAY's flags --------------------------------------------------------
// PhoneLookAhead mounted with `initialPage` (no fetch): three lines of the backend fixture planned on every weekday, the
// clash rail swapped for four flags — a gate over capacity dated the next weekday on line A, a gate near capacity dated
// today on line B, a route cap dated the next weekday on line B, a road restriction with no date on line C. A dated flag
// belongs on its own day's card only, an undated one on every day (the Day sheet PDF's rule, export.day_sheet_rows; the
// fixture's own dated flags fall on every weekday, so they cannot show the difference). Checked on three days: each
// line's status, its details and the "N lines flagged" count; then the desk grid with the same page, whose row is the
// whole week and so keeps every flag.
async function phoneDayFlagsDom(){
  const LA = FIX("lookahead_page.json");
  w.fetch = () => new Promise(() => {});
  const meta = { ...metaMin, months: { start_year: 2026, count: 60 } };
  const lk = (r) => `${r.route_id}|${r.discipline || ""}|${r.section_id || ""}|${r.month_index}`;
  const planned = (l, iso) => { const d = (l.days || []).find(x => x.day_date === iso); return !!d && ((+d.planned_qty || 0) > 0 || ((d.derived || {}).trips || 0) > 0); };
  const today = LA.today;
  const weekdays = LA.commit.lines[0].days.map(d => d.day_date).filter(iso => !w.__F.isWeekend(iso));
  const [next, third] = weekdays.filter(iso => iso > today);
  const lines = LA.commit.lines.filter(l => weekdays.every(iso => planned(l, iso))).slice(0, 3);
  ok("PHONE DAY FLAGS: the test page — three fixture lines planned on every weekday, today and two later weekdays",
     lines.length === 3 && new Set(lines.map(lk)).size === 3 && weekdays.includes(today) && !!next && !!third, `${lines.length} ${today} ${next} ${third}`);
  const [A, B, C] = lines;
  const fl = (l, code, text, day) => ({ code, route_id: l.route_id, month_index: l.month_index, discipline: l.discipline || "",
    section_id: l.section_id || "", ipt: l.ipt, text, ...(day ? { day_date: day } : {}) });
  const page = { ...LA, commit: { ...LA.commit, lines }, clashes: { ...LA.clashes, flags: [
    fl(A, "GATE_OVER", `Gate A on ${next}: 9 lorries against the 6 it can check in (150 %)`, next),
    fl(B, "GATE_NEAR", `Gate B on ${today}: 5 lorries against the 6 it can check in (83 %), near capacity`, today),
    fl(B, "ROUTE_CAP", `${B.route_id} ${next}: 12 veh against a cap of 10`, next),
    fl(C, "RESTRICTION", "Road closed all week"),
  ] } };
  const el = w.document.createElement("div"); w.document.body.appendChild(el);
  const r = w.ReactDOM.createRoot(el);
  await act(async () => { r.render(w.React.createElement(w.PhoneLookAhead, { meta, initialPage: page })); });
  const card = () => el.querySelector("[data-ph-day]");
  const line = (l) => el.querySelector(`[data-ph-line="${lk(l)}"]`);
  // the status word alone (the row-st span holds an icon <i>, the word, and +N for more kinds of flag)
  const word = (l) => { const s = line(l).querySelector(".row-st"); return [...s.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim(); };
  const more = (l) => (line(l).querySelector(".row-st .rs-more") || {}).textContent || "";
  const facts = (l) => line(l).querySelector("dl").textContent;
  const note = () => card().querySelector(".ph-note").textContent;
  const pick = async (iso) => { await act(async () => { [...el.querySelectorAll(".ph-days > button")].find(b => b.textContent === w.__F.dayName(iso) + w.__F.dayNum(iso)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); };

  ok("PHONE DAY FLAGS: the card opens on today with all three lines", card().getAttribute("data-ph-day") === today && !!line(A) && !!line(B) && !!line(C));
  ok("⭐ PHONE DAY FLAGS (today): a gate over capacity dated another day is NOT on the card — not in the line's status, not in its details",
     word(A) !== "GATE OVER" && !/GATE OVER/.test(facts(A)) && !facts(A).includes(`Gate A on ${next}`), `${word(A)} | ${facts(A).slice(0, 200)}`);
  ok("⭐ PHONE DAY FLAGS (today): a flag dated today IS on the card; the same line's route cap dated another day is not",
     word(B) === "GATE NEAR" && more(B) === "" && facts(B).includes(`Gate B on ${today}`) && !/\bCAP\b/.test(facts(B)), `${word(B)} ${more(B)} | ${facts(B).slice(0, 200)}`);
  ok("⭐ PHONE DAY FLAGS (today): a flag with no date (a road restriction) is on the card", word(C) === "RESTRICTION" && facts(C).includes("Road closed all week"), word(C));
  ok("PHONE DAY FLAGS (today): the count names the two lines flagged today, not three", /· 2 lines flagged/.test(note()), note());

  await pick(next);
  ok("⭐ PHONE DAY FLAGS (next weekday): its own gate over capacity shows on that day's card, status and details",
     card().getAttribute("data-ph-day") === next && word(A) === "GATE OVER" && facts(A).includes(`Gate A on ${next}`), `${word(A)} | ${facts(A).slice(0, 200)}`);
  ok("PHONE DAY FLAGS (next weekday): line B carries its route cap, and today's gate near capacity has left the card",
     word(B) === "CAP" && more(B) === "" && !/GATE NEAR/.test(facts(B)) && !facts(B).includes(`Gate B on ${today}`), `${word(B)} ${more(B)} | ${facts(B).slice(0, 200)}`);
  ok("⭐ PHONE DAY FLAGS (next weekday): the undated restriction is still on the card (every day)", word(C) === "RESTRICTION");
  ok("PHONE DAY FLAGS (next weekday): three lines flagged", /· 3 lines flagged/.test(note()), note());

  await pick(third);
  ok("⭐ PHONE DAY FLAGS (a day no dated flag names): only the undated restriction — one line flagged, A and B in the week's own state",
     card().getAttribute("data-ph-day") === third && word(C) === "RESTRICTION" && !/GATE|CAP/.test(word(A) + word(B))
     && !/GATE|\bCAP\b/.test(facts(A) + facts(B)) && /· 1 line flagged/.test(note()), `${word(A)} | ${word(B)} | ${note()}`);
  await act(async () => { r.unmount(); }); el.remove();

  // the desk grid: its row is the whole week, so every flag of the week stays on it (unchanged by the phone's rule)
  const del = w.document.createElement("div"); w.document.body.appendChild(del);
  const dr = w.ReactDOM.createRoot(del);
  await act(async () => { dr.render(w.React.createElement(w.LookAhead, { meta, who: "t", initialPage: page, initialView: "commit" })); });
  const deskWord = (l) => { const s = del.querySelector(`tr[data-la-line="${lk(l)}"] .row-st`); return s ? [...s.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim() : "(no row)"; };
  const deskMore = (l) => (del.querySelector(`tr[data-la-line="${lk(l)}"] .row-st .rs-more`) || {}).textContent || "";
  ok("⭐ DESK GRID (unchanged): the week's row keeps every flag of the week — A's gate over capacity, B's route cap ahead of its gate near capacity (+1), C's restriction",
     deskWord(A) === "GATE OVER" && deskWord(B) === "CAP" && deskMore(B) === "+1" && deskWord(C) === "RESTRICTION",
     `${deskWord(A)} | ${deskWord(B)} ${deskMore(B)} | ${deskWord(C)}`);
  await act(async () => { dr.unmount(); }); del.remove();
}

// ---- 14 Oct 2026 (G3): per-person logins, mounted -------------------------------------------------------------
// The whole App with a stubbed fetch that records every call: email sign-in, the account menu, the Users page (teams by
// NAME, never an id), the hint that resumes a session on reload, a session ending while the app is open, a demo login
// sending its page opens, and the set-password screen (mounted on its own: the link is read once as the page loads).
// NOT covered: the real cookie (http_smoke.py), how it looks (the browser check).
async function g3LoginsDom(){
  const answer = (status, data) => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(data) });
  const ADMIN = { role: "admin", label: "Admin", ipt: null, can_approve: true, ipt_locked: false, ipt_required: true, demo: false,
                  ipts: [], via: "login", codes: false, name: "Ada Lovelace", email: "ada@example.org", kind: "staff", user_id: "u1" };
  const TEAMLOGIN = { ...ADMIN, role: "ipt", label: "North Team", ipt: "IPT1", can_approve: false, ipt_locked: true, ipt_required: false,
                      name: "Bob North", email: "bob@example.org", user_id: "u2" };
  const USERS = { users: [
      { id: "u1", email: "ada@example.org", name: "Ada Lovelace", role: "admin", team: null, team_label: null, role_label: "Admin",
        status: "active", kind: "staff", disabled: false, has_password: true, last_sign_in_at: "2026-10-14T09:00:00Z" },
      { id: "u2", email: "bob@example.org", name: "Bob North", role: "team", team: "IPT1", team_label: "North Team", role_label: "North Team",
        status: "invited", kind: "staff", disabled: false, has_password: false, last_sign_in_at: null },
      { id: "u3", email: "lea@example.org", name: "Lea Lead", role: "team", team: "IPT1", team_label: "North Team", role_label: "North Team",
        status: "active", kind: "demo", disabled: false, has_password: false, expires_at: "2026-10-28T09:00:00Z", last_sign_in_at: null }],
    teams: [{ id: "IPT1", label: "North Team" }, { id: "IPT2", label: "Central Team" }], codes: true, mail: false, me: "u1" };
  const calls = [];
  let signinAnswer = () => answer(200, ADMIN), meAnswer = () => answer(200, { signed_in: false, access: null, codes: false });
  w.fetch = (url, o) => {
    const u = String(url); calls.push({ u, o });
    if (/\/api\/meta$/.test(u)) return respond(META);
    if (/\/api\/auth\/me$/.test(u)) return meAnswer();
    if (/\/api\/auth\/signin$/.test(u)) return signinAnswer();
    if (/\/api\/auth\/signout$/.test(u)) return answer(200, { ok: true });
    if (/\/api\/admin\/users(\?|$)/.test(u) && !(o && o.method === "POST")) return answer(200, USERS);
    if (/\/api\/admin\/users(\?|$)/.test(u)) return answer(200, { user: { ...USERS.users[1], id: "u9", name: "Cy New" }, email: "unsent", purpose: "invite",
                                                                    link: "https://app.wayscope.co.uk/#invite=abcdefghijklmnopqrstuvwxyz" });
    if (/\/api\/admin\/audit/.test(u)) return answer(200, { rows: [
      { id: "a1", at: "2026-10-14T10:00:00Z", kind: "write", actor_label: "Ada Lovelace <ada@example.org>", method: "POST", path: "/api/forecasts/bulk", detail: "{\"rows\":1}" },
      { id: "a2", at: "2026-10-14T09:00:00Z", kind: "page", actor_label: "Lea Lead <lea@example.org>", target: "dashboard" }] });
    if (/\/api\/admin\/leads/.test(u)) return answer(200, { leads: [
      { id: "r1", created_at: "2026-10-09T12:00:00Z", name: "Old Lead", email: "old@example.org", organisation: "O", role: "Other", login: "none",
        login_expires_at: "", sign_ins: "", first_seen: "", last_seen: "", pages: "" }] });
    if (/\/api\/activity$/.test(u)) return answer(200, { ok: true, recorded: true });
    return new Promise(() => {});
  };
  const mountApp = async () => {
    const box = w.document.createElement("div"); w.document.body.appendChild(box);
    const root = w.ReactDOM.createRoot(box);
    await act(async () => { root.render(w.React.createElement(w.App)); });
    await tick(); await tick();
    return { box, root };
  };
  const btnT = (box, t) => [...box.querySelectorAll("button")].find(b => b.textContent.trim() === t);
  const setVal = (el, v) => act(() => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set.call(el, v); el.dispatchEvent(new w.Event("input", { bubbles: true })); });
  w.__ACCESS.code = ""; w.__ACCESS.info = null; w.sessionStorage.removeItem("modus_access_code"); w.localStorage.removeItem("wayscope_signed_in");
  w.localStorage.setItem("modus_page", "dashboard");

  // (a) email sign-in as an admin
  const a = await mountApp();
  click(btnT(a.box, "Staff sign in")); await tick();
  ok("G3 SIGN-IN: with the codes OFF on the server, the code link is not offered",
     !!a.box.querySelector("input#auth-email") && !btnT(a.box, "Sign in with a team code instead") && !!btnT(a.box, "Forgot your password?"));
  await setVal(a.box.querySelector("input#auth-email"), "  ada@example.org ");
  await setVal(a.box.querySelector("input#auth-pass"), "correct horse battery");
  click(a.box.querySelector(".auth-check input"));
  await act(async () => { btnT(a.box, "Sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick(); await tick();
  const sc = calls.find(c => /\/api\/auth\/signin$/.test(c.u));
  ok("⭐ G3 SIGN-IN: posts the trimmed email, the password and the keep-me-signed-in tick to /api/auth/signin",
     sc && sc.o.method === "POST" && JSON.parse(sc.o.body).email === "ada@example.org" && JSON.parse(sc.o.body).password === "correct horse battery"
     && JSON.parse(sc.o.body).remember === true);
  ok("⭐ G3 SIGN-IN: the staff app opens; the header shows the person's NAME (the account menu), and no code is kept in the tab",
     !!btnT(a.box, "Sign out") && !!a.box.querySelector(".acct-btn") && /Ada Lovelace/.test(a.box.querySelector(".acct-btn").textContent)
     && w.sessionStorage.getItem("modus_access_code") === null && w.__ACCESS.code === "" && w.__ACCESS.info === ADMIN);
  ok("...and the browser keeps only the harmless note that someone signed in here", w.localStorage.getItem("wayscope_signed_in") === "1");
  ok("G3: an ADMIN sees Users in the rail", [...a.box.querySelectorAll(".rail-item")].some(b => /Users/.test(b.textContent)));
  click(a.box.querySelector(".acct-btn"));
  const menu = a.box.querySelector(".acct-menu");
  ok("G3 ACCOUNT: the menu names the person, their email, and offers a password change",
     !!menu && /ada@example\.org/.test(menu.textContent) && /Change your password/.test(menu.textContent)
     && !!menu.querySelector('input[aria-label="Current password"]'));
  click(a.box.querySelector(".acct-btn"));
  // the Users page
  await act(async () => { [...a.box.querySelectorAll(".rail-item")].find(b => /Users/.test(b.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick(); await tick();
  const usersText = a.box.querySelector("main main") ? a.box.querySelector("main main").textContent : a.box.textContent;
  ok("⭐ G3 USERS: the list shows each person, a team by its NAME, and NEVER a team id",
     /Bob North/.test(usersText) && /North Team/.test(usersText) && !/IPT1|IPT2/.test(usersText));
  ok("G3 USERS: the shared codes are still on, and the page says so", /The shared codes still work on this site/.test(usersText));
  ok("G3 USERS: an admin LOGIN is not asked for the admin token", !a.box.querySelector('input[aria-label="Admin token"]'));
  ok("G3 USERS: the add form offers each team by NAME, Planner and Admin",
     [...a.box.querySelectorAll('select[aria-label="Team or role"] option')].map(x => x.textContent).join("|") === "Choose…|North Team|Central Team|Planner|Admin");
  ok("G3 USERS: the person signed in cannot disable themself (no Disable on their own row); others can be",
     [...a.box.querySelectorAll("tbody tr")].filter(r => /Ada Lovelace/.test(r.textContent)).every(r => !/Disable/.test(r.textContent))
     && [...a.box.querySelectorAll("tbody tr")].some(r => /Bob North/.test(r.textContent) && /Disable/.test(r.textContent)));
  ok("G3 USERS: a demo login sits in its own table with its end date and '7 more days'",
     /Demo logins/.test(usersText) && [...a.box.querySelectorAll("tbody tr")].some(r => /Lea Lead/.test(r.textContent) && /7 more days/.test(r.textContent)));
  await setVal(a.box.querySelector('input[aria-label="Name"]'), "Cy New");
  await setVal(a.box.querySelector('input[aria-label="Email"]'), "cy@example.org");
  const sel = a.box.querySelector('select[aria-label="Team or role"]');
  await act(async () => { sel.value = "team:IPT2"; sel.dispatchEvent(new w.Event("change", { bubbles: true })); });
  await act(async () => { btnT(a.box, "Add and send the link").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick(); await tick();
  const add = calls.find(c => /\/api\/admin\/users(\?|$)/.test(c.u) && c.o && c.o.method === "POST");
  ok("⭐ G3 USERS: Add posts the name, the email and the team SLOT behind the name, with no token in the address",
     add && JSON.stringify(JSON.parse(add.o.body)) === JSON.stringify({ name: "Cy New", email: "cy@example.org", role: "team", team: "IPT2" })
     && !/token=/.test(add.u));
  ok("G3 USERS: with no email set up, the page shows the invite link to pass on, with Copy",
     /pass this link/.test(a.box.textContent) && /#invite=abcdefghijklmnopqrstuvwxyz/.test(a.box.textContent) && !!btnT(a.box, "Copy"));
  click(btnT(a.box, "Demo leads")); await tick(); await tick();
  ok("G3 USERS → Demo leads: a lead who had the shared code gets 'Send a personal login'",
     /Old Lead/.test(a.box.textContent) && /had the shared code/.test(a.box.textContent) && !!btnT(a.box, "Send a personal login"));
  click(btnT(a.box, "Activity")); await tick(); await tick();
  ok("G3 USERS → Activity: rows read in words — who, and what they did — not paths",
     /Ada Lovelace/.test(a.box.textContent) && /Saved forecast lines/.test(a.box.textContent) && /Opened dashboard/.test(a.box.textContent)
     && !/\/api\/forecasts/.test([...a.box.querySelectorAll("tbody td")].map(t => t.textContent).join(" ").replace(/Details[\s\S]*$/, "")));
  // sign out
  await act(async () => { btnT(a.box, "Sign out").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  ok("⭐ G3 SIGN OUT: posts /api/auth/signout, drops the note, lands on the public map",
     calls.some(c => /\/api\/auth\/signout$/.test(c.u) && c.o && c.o.method === "POST") && w.localStorage.getItem("wayscope_signed_in") === null
     && !!btnT(a.box, "Staff sign in"));
  await act(async () => { a.root.unmount(); }); a.box.remove();

  // (b) a refused sign-in shows the server's one sentence
  signinAnswer = () => answer(401, { detail: "That email and password don't match." });
  const b = await mountApp();
  click(btnT(b.box, "Staff sign in")); await tick();
  await setVal(b.box.querySelector("input#auth-email"), "x@example.org");
  await setVal(b.box.querySelector("input#auth-pass"), "wrong wrong wrong");
  await act(async () => { btnT(b.box, "Sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick(); await tick();
  ok("G3 SIGN-IN: a refusal shows the server's one sentence and stays on the sign-in screen",
     /That email and password don't match\./.test(b.box.textContent) && !!b.box.querySelector("input#auth-email"));
  click(btnT(b.box, "Forgot your password?")); await tick();
  ok("G3 FORGOT: the same card asks for the email and offers 'Send me a link' and 'Back to sign in'",
     /Forgotten your password\?/.test(b.box.textContent) && !!btnT(b.box, "Send me a link") && !!btnT(b.box, "Back to sign in") && !b.box.querySelector("input#auth-pass"));
  await act(async () => { b.root.unmount(); }); b.box.remove();
  const staffActivity = calls.filter(x => /\/api\/activity$/.test(x.u)).length;   // (a) opened Dashboard and Users as an admin login

  // (c) a reload with the note: the server is asked who this is
  w.localStorage.setItem("wayscope_signed_in", "1");
  meAnswer = () => answer(200, { signed_in: true, access: TEAMLOGIN, codes: false });
  calls.length = 0;
  const c = await mountApp(); await tick();
  ok("⭐ G3 RELOAD: with the note, the app asks /api/auth/me and returns to the staff app as that login",
     calls.some(x => /\/api\/auth\/me$/.test(x.u)) && !!btnT(c.box, "Sign out") && /Bob North/.test(c.box.querySelector(".acct-btn").textContent));
  ok("G3: a TEAM login sees no Users page", ![...c.box.querySelectorAll(".rail-item")].some(x => /Users/.test(x.textContent)));
  await act(async () => { w.dispatchEvent(new w.Event("wayscope-session-ended")); }); await tick();
  ok("⭐ G3 SESSION ENDED: a session that ends while the app is open lands on sign-in with a sentence saying so, and the note goes",
     !!c.box.querySelector("input#auth-email") && /You have been signed out/.test(c.box.textContent) && w.localStorage.getItem("wayscope_signed_in") === null);
  await act(async () => { c.root.unmount(); }); c.box.remove();
  // the note, but the session is gone
  w.localStorage.setItem("wayscope_signed_in", "1");
  meAnswer = () => answer(200, { signed_in: false, access: null, codes: false });
  const d = await mountApp(); await tick();
  ok("🔴 G3 RELOAD: the note with no live session → the public map, and the note is dropped",
     !!btnT(d.box, "Staff sign in") && w.localStorage.getItem("wayscope_signed_in") === null);
  await act(async () => { d.root.unmount(); }); d.box.remove();
  // no note: /api/auth/me is not asked on load
  calls.length = 0;
  const e = await mountApp(); await tick();
  ok("G3 RELOAD: without the note a visitor gets the public map at once and /api/auth/me is not asked before sign-in",
     !!btnT(e.box, "Staff sign in") && !calls.some(x => /\/api\/auth\/me$/.test(x.u)));
  await act(async () => { e.root.unmount(); }); e.box.remove();

  // (d) a demo login sends its page opens (D51); a staff login does not
  w.localStorage.setItem("wayscope_signed_in", "1");
  meAnswer = () => answer(200, { signed_in: true, access: { ...TEAMLOGIN, kind: "demo", name: "Lea Lead", expires_at: "2026-10-28T09:00:00Z" }, codes: false });
  calls.length = 0;
  const f = await mountApp(); await tick(); await tick();
  await act(async () => { [...f.box.querySelectorAll(".rail-item")].find(x => /Look-ahead/.test(x.textContent)).dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  const acts = calls.filter(x => /\/api\/activity$/.test(x.u)).map(x => JSON.parse(x.o.body).page);
  ok("⭐ G3 DEMO: a demo login reports each page it opens (Dashboard, then Look-ahead)", acts.join("|") === "dashboard|lookahead");
  click(f.box.querySelector(".acct-btn"));
  ok("G3 DEMO: its account menu says when the demo access ends and offers no password change",
     /Your demo access ends/.test(f.box.querySelector(".acct-menu").textContent) && !/Change your password/.test(f.box.querySelector(".acct-menu").textContent));
  await act(async () => { f.root.unmount(); }); f.box.remove();
  ok("🔴 G3: the STAFF login in (a) opened two pages and sent no page open", staffActivity === 0);
  w.localStorage.removeItem("wayscope_signed_in");

  // (e) the set-password screen
  let resetBody = null, checkAnswer = () => answer(200, { purpose: "invite", name: "Cy New", email: "cy@example.org" });
  w.fetch = (url, o) => { const u = String(url);
    if (/\/api\/auth\/check$/.test(u)) return checkAnswer();
    if (/\/api\/auth\/reset$/.test(u)) { resetBody = JSON.parse(o.body); return answer(200, { ...TEAMLOGIN, name: "Cy New" }); }
    return new Promise(() => {}); };
  let signedIn = null;
  const g = w.document.createElement("div"); w.document.body.appendChild(g);
  const gr = w.ReactDOM.createRoot(g);
  await act(async () => { gr.render(w.React.createElement(w.SetPassword, { link: { purpose: "invite", token: "t".repeat(40) }, onSignIn: (i) => { signedIn = i; }, onBack: () => {} })); });
  await tick(); await tick();
  ok("⭐ G3 SET PASSWORD: an invite greets the person by first name and names the login's email", /Welcome, Cy/.test(g.textContent) && /cy@example\.org/.test(g.textContent));
  await setVal(g.querySelector("#set-pw"), "short");
  await act(async () => { btnT(g, "Save and sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  ok("G3 SET PASSWORD: under 10 characters is refused on the page, nothing posted", /at least 10 characters/.test(g.textContent) && resetBody === null);
  await setVal(g.querySelector("#set-pw"), "purple tractor river");
  await setVal(g.querySelector("#set-pw2"), "purple tractor rivers");
  await act(async () => { btnT(g, "Save and sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  ok("G3 SET PASSWORD: two different passwords are refused on the page", /not the same/.test(g.textContent) && resetBody === null);
  await setVal(g.querySelector("#set-pw2"), "purple tractor river");
  await act(async () => { btnT(g, "Save and sign in").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
  await tick();
  ok("⭐ G3 SET PASSWORD: posts the link and the password to /api/auth/reset and signs in with the answer",
     resetBody && resetBody.token === "t".repeat(40) && resetBody.password === "purple tractor river" && signedIn && signedIn.name === "Cy New");
  await act(async () => { gr.unmount(); }); g.remove();
  checkAnswer = () => answer(410, { detail: "This link has expired or has already been used. Ask for a new one." });
  const h = w.document.createElement("div"); w.document.body.appendChild(h);
  const hr = w.ReactDOM.createRoot(h);
  await act(async () => { hr.render(w.React.createElement(w.SetPassword, { link: { purpose: "reset", token: "u".repeat(40) }, onSignIn: () => {}, onBack: () => {} })); });
  await tick(); await tick();
  ok("🔴 G3 SET PASSWORD: a used or expired link says so, says how to get a new one, and shows no password field",
     /This link no longer works/.test(h.textContent) && /Forgot your password/.test(h.textContent) && !h.querySelector("#set-pw"));
  await act(async () => { hr.unmount(); }); h.remove();
}

// one runner for the async sections (merged 11 Oct 2026: claude/carbon-process + claude/demo-bar): the bar's first,
// on a fresh window, then the carbon target's (it mounts its pages directly, without the App shell)
// ---- 17 Oct 2026 (the user: UK drivers' hours; the review): the Routes page's Trips/day cell, mounted ---------------
// The § marks only a route the rules hold below the shift alone (trips < trips_without_rules), the cell's title is the
// server's words, a 0 shows as a 0 with its words, and the footnote carries the 13 h note. fetch answers the analysis
// read only; the gates / haul roads / restrictions reads never answer. Not covered: the real server's rows (http_smoke).
async function routesDriversDom(){
  const ROW = (profile, trips, lim, plain, words) => ({ profile, alt_index: 0, loaded_km: 12, return_km: 12, return_estimated: false,
    load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 1.5, haul_speed_applied: false,
    trips_per_day: trips, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 30,
    lorry_day: { limited_by: lim, trips_without_rules: plain, words, break_minutes: 45 } });
  const NOTE = "The 15 h shift is read as 13 h for a lorry's trips: one driver's day (the 11-hour daily rest).";
  const DATA = { rows: [
      ROW("Tipper", 5, "breaks", 6, "5 a day: 1 fewer than the shift alone would hold: the required break takes the time (45 min break)"),
      ROW("Flatbed", 8, "shift", 8, "8 a day: as many round trips as fit in the shift (45 min break)"),
      ROW("Mixer", 0, "none", 0, "One round trip does not fit in a driver's day: counted as one lorry a trip")],
    planning: { shift_hours_per_day: 15, working_days_per_month: 22, shift_note: NOTE } };
  w.fetch = (url) => /\/api\/routes\/R1\/analysis$/.test(String(url)) ? reply(200, DATA) : new Promise(() => {});
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const E = w.React.createElement;
  act(() => { root.render(E("table", null, E("tbody", null, E(w.RouteAnalysis, { routeId: "R1", colSpan: 9, token: "t" })))); });
  await settle(150);
  const cells = [...host.querySelectorAll("td[data-trips-limit]")];
  ok("⭐ ROUTES DOM: one Trips/day cell a row, each carrying its limit", cells.length === 3
     && cells.map(c => c.getAttribute("data-trips-limit")).join() === "breaks,shift,none", String(cells.length));
  ok("⭐ ROUTES DOM: § only where the rules took trips off (5 of 6), not on a shift-limited 8 nor on a 0 the shift alone also gives",
     cells.length === 3 && cells[0].textContent === "5§" && cells[1].textContent === "8" && cells[2].textContent === "0",
     cells.map(c => c.textContent).join("|"));
  ok("ROUTES DOM: the cell's title is the server's words (why, and the 0 counted as one lorry a trip)",
     cells.length === 3 && cells[0].title === DATA.rows[0].lorry_day.words && cells[2].title === DATA.rows[2].lorry_day.words);
  const foot = host.textContent.replace(/\s+/g, " ");
  ok("⭐ ROUTES DOM: the footnote says a planning figure, explains the 0, and carries the 13 h note for a 15 h shift",
     // NARROWED 22 Oct 2026 (UI fix 7, the user: fewer words): the footnote is one short paragraph, the rule the same.
     // The build's own first run found "fit a15 h" here (JSX drops the space at a line break before {…}): asserted below.
     foot.includes("0 = one lorry a trip)") && foot.includes("A planning figure.") && foot.includes(NOTE)
     // found in the Chrome check (18 Oct): JSX dropped the space at the line break — "modelled.t/month"
     && foot.includes(NOTE + " t/month at 22 working days") && !/\.t\/month/.test(foot)
     && foot.includes("round trips that fit a 15 h shift with the legal break and at most 9 h driving") && !/fit a15/.test(foot), foot.slice(-700));
  act(() => { root.unmount(); }); host.remove();
}

// ---- 22 Oct 2026 (UI fix 6, card 5; decision 6): the big screen's Today list in Rotate / One section, mounted -------------
// The list shows only the rows that fit WHOLE (busiest first), every row closed whatever the desk opened, and under it
// "+ N more lines today · X t"; since card 4 (22 Oct) "All sections" does the same; the desk is unchanged. jsdom has no layout and
// no ResizeObserver, so the list box's height and the rows' boxes are stubbed (a 30 px header, 40 px rows) and the observer
// is fired by hand. The counting rule itself, todayFit, is tested on its own first. Not covered here: real row heights,
// fonts and the TV widths (the browser and the UI audit), and the count line's own height taking space from the list
// (the observer re-measures when the box shrinks; with a stubbed box that size never changes).
async function todayFitDom(){
  const tf = w.todayFit;
  ok("UI FIX 6 card 5: todayFit is a global helper", typeof tf === "function");
  ok("⭐ UI FIX 6 card 5: todayFit counts the rows that fit WHOLE, in order — 3 × 40 px in 120 → 3, in 119 → 2; half a pixel is forgiven (119.6 → 3)",
     tf([40, 40, 40], 120) === 3 && tf([40, 40, 40], 119) === 2 && tf([40, 40, 40], 119.6) === 3 && tf([40, 40, 40], 1000) === 3);
  ok("⭐ UI FIX 6 card 5: todayFit never skips a row to pull a shorter one up (busiest first stays busiest first), and a first row taller than the box gives 0",
     tf([40, 80, 10], 100) === 1 && tf([130, 10], 100) === 0);
  ok("UI FIX 6 card 5: todayFit with no rows, no list, or a row with no height stops there",
     tf([], 100) === 0 && tf(null, 100) === 0 && tf(undefined, 100) === 0 && tf([40, NaN, 40], 500) === 1 && tf([40, 40], 0) === 0);

  const TODAY = CLOCK.TODAY;
  const TONNES = [2400, 1800, 1200, 700, 650, 120.6];       // already busiest first; the last three sum to 1 470.6
  const lines = TONNES.map((t, i) => ({ route_id: "R" + (i + 1), discipline: "D" + i, section_id: "", unit: "t", material_type: "Small aggregate",
    context: { origin_name: "Quarry " + (i + 1), dest_name: "Compound " + (i + 1), vehicle_short: "Tipper", baked: true },
    week_derived: { tonnes: t * 5, trips: 10 },
    days: [{ day_date: TODAY, planned_qty: t, status: "planned", actual_qty: null, derived: { tonnes: t, trips: 2, vehicles: 1, km_day: 40 } }] }));
  const week = { today: TODAY, commit: { lines }, commit_week: { week_index: 3, from: "2026-10-12", to: "2026-10-18" }, account: null };
  const OPEN = { "R1|D0|": 1 };                             // the busiest row, opened at the desk earlier in this tab
  w.sessionStorage.setItem("modus_rows_today", JSON.stringify(OPEN));
  w.fetch = () => new Promise(() => {});
  // the stubs: the list box (.today-lines) is AVAIL px high, its rows sit under a 30 px header, 40 px each
  let AVAIL = 0; const HEAD = 30, ROWH = 40, TOP = 100;
  const hadOwn = Object.getOwnPropertyDescriptor(w.HTMLElement.prototype, "clientHeight");
  const realRect = w.Element.prototype.getBoundingClientRect;
  Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { configurable: true,
    get(){ return this.classList && this.classList.contains("today-lines") ? AVAIL : 0; } });
  w.Element.prototype.getBoundingClientRect = function(){
    if (this.classList && this.classList.contains("today-lines")) return { top: TOP, bottom: TOP + AVAIL, height: AVAIL, left: 0, right: 500, width: 500, x: 0, y: TOP };
    if (this.classList && this.classList.contains("rd-row") && this.parentNode) {
      const i = [...this.parentNode.children].filter(x => x.classList.contains("rd-row")).indexOf(this);
      // 22 Oct 2026 (UI fix 6, card 5, review): a scrolled list box lifts its rows, as a browser does
      const lb = this.closest && this.closest(".today-lines");
      const top = TOP + HEAD + i * ROWH - ((lb && lb.scrollTop) || 0);
      return { top, bottom: top + ROWH, height: ROWH, left: 0, right: 500, width: 500, x: 0, y: top };
    }
    return realRect.call(this);
  };
  const ROs = [];
  w.ResizeObserver = function(cb){ this.cb = cb; this.els = []; this.observe = (el) => { this.els.push(el); if (!ROs.includes(this)) ROs.push(this); }; this.disconnect = () => { this.els = []; }; };
  const fire = () => act(() => { ROs.forEach(o => { if (o.els.length) o.cb([]); }); });
  const mount = (props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
    act(() => { r.render(w.React.createElement(w.DashboardToday, { meta: metaMin, week, ...props })); });
    return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
  const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
  try {
    // 1. Rotate: the section is hidden (0 px) when the card mounts — nothing is measured, every row drawn, no count line
    const tv = mount({ wall: true, fill: true });
    const list = () => tv.el.querySelector(".today-lines");
    const rows = () => [...tv.el.querySelectorAll("tr.rd-row")];
    const cut = () => rows().filter(r => r.classList.contains("today-cut")).map(r => r.getAttribute("data-rd"));
    const more = () => tv.el.querySelector("[data-today-more]");
    ok("UI FIX 6 card 5: on the big screen in Rotate / One section the list is marked to fit, its box observed (the box and its table)",
       !!list() && list().getAttribute("data-today-fit") === "1" && ROs.some(o => o.els.includes(list()) && o.els.includes(list().querySelector("table"))));
    ok("UI FIX 6 card 5: while its section is hidden (0 px high) nothing is measured — all six rows drawn, no count line",
       rows().length === 6 && cut().length === 0 && !more());
    // 2. the section is shown: a 155 px box = the header + three whole rows + 5 px
    AVAIL = HEAD + 3 * ROWH + 5; fire();
    ok("⭐ UI FIX 6 card 5: the section shown (155 px): three whole rows, busiest first; the other three are not drawn (today-cut), none cut in half",
       cut().join() === "today-R4|D3|,today-R5|D4|,today-R6|D5|" && rows().slice(0, 3).every(r => !r.classList.contains("today-cut")), cut().join());
    ok("⭐ UI FIX 6 card 5: under the list, inside the card, '+ 3 more lines today · 1 471 t' (the hidden rows' tonnes, rounded and grouped like the card's figures), 12 px, flex:none (.today-more)",
       !!more() && norm(more().textContent) === "+ 3 more lines today · 1 471 t" && more().getAttribute("data-today-more") === "3"
       && more().className === "text-xs today-more" && list().nextElementSibling === more() && !!more().closest(".card") && !list().contains(more()),
       more() ? norm(more().textContent) : "no count line");
    ok("UI FIX 6 card 5: the rows shown plus the count add up to the card's tonnes figure (5 400 + 1 470.6 = 6 870.6, printed 6 871)",
       norm(tv.el.textContent).includes("6 871") && TONNES.slice(0, 3).reduce((a, b) => a + b, 0) + 1470.6 === TONNES.reduce((a, b) => a + b, 0));
    ok("⭐ UI FIX 6 card 5: every row is drawn CLOSED on the big screen although the desk opened the busiest one in this tab — and the desk's choice is kept for the desk",
       [...tv.el.querySelectorAll("tr.rd-details")].every(d => d.hidden) && tv.el.querySelector('tr[data-rd="today-R1|D0|"] .rd-chev').getAttribute("aria-expanded") === "false"
       && w.sessionStorage.getItem("modus_rows_today") === JSON.stringify(OPEN));
    ok("UI FIX 6 card 5 (the user: keep the progress bars): the two bars and their headings are still there, above the list",
       tv.el.querySelectorAll(".h-2.rounded-full.bg-slate-100").length === 2 && norm(tv.el.textContent).includes("This week to date") && norm(tv.el.textContent).includes("Last week")
       && (tv.el.querySelector(".h-2.rounded-full.bg-slate-100").compareDocumentPosition(list()) & 4) === 4);
    // 2b. 22 Oct 2026 (UI fix 6, card 5, review): a scroll left over from "All sections" (40 px down) is reset before
    // measuring, so the count is the unscrolled one (without the reset the rows sit 40 px higher and four would "fit")
    { let st = 40; const lbx = list();
      Object.defineProperty(lbx, "scrollTop", { configurable: true, get(){ return st; }, set(v){ st = v; } });
      fire();
      ok("⭐ UI FIX 6 card 5 (review): a list box left scrolled (40 px) by All sections is put back to the top before measuring — the same three whole rows and '+ 3 more lines today · 1 471 t'",
         st === 0 && cut().join() === "today-R4|D3|,today-R5|D4|,today-R6|D5|" && !!more() && norm(more().textContent) === "+ 3 more lines today · 1 471 t",
         `scrollTop ${st}; cut ${cut().join()}`);
      delete lbx.scrollTop; }
    // 3. a bigger screen: everything fits — no cut, no count line
    AVAIL = 1000; fire();
    ok("⭐ UI FIX 6 card 5: when every row fits there is no count line and no row is left off",
       cut().length === 0 && !more() && rows().length === 6);
    // 4. room for five: one more line, singular
    AVAIL = HEAD + 5 * ROWH + 2; fire();
    ok("UI FIX 6 card 5: room for five whole rows: '+ 1 more line today · 121 t' (one line, singular; 120.6 t rounded)",
       cut().join() === "today-R6|D5|" && !!more() && norm(more().textContent) === "+ 1 more line today · 121 t", more() ? norm(more().textContent) : cut().join());
    // 5. Rotate moves to another section (0 px): the last count is kept, not reset to 'everything hidden'
    AVAIL = 0; fire();
    ok("UI FIX 6 card 5: while another section is on the screen (0 px) the last count is kept",
       cut().join() === "today-R6|D5|" && !!more() && norm(more().textContent) === "+ 1 more line today · 121 t");
    tv.done();
    // 6. REVERSED 22 Oct 2026 (UI fix 6, card 4; the user: "yes, build card 4 ... keeping the progress bars"): All sections
    //    (wall, not fill) now fits whole rows like Rotate / One section, in its 260 px box; the working Dashboard is unchanged.
    AVAIL = HEAD + 3 * ROWH + 5;
    {
      const m = mount({ wall: true, fill: false });
      fire();
      const lb = m.el.querySelector(".today-lines");
      const mm = m.el.querySelector("[data-today-more]");
      ok("⭐ UI FIX 6 card 4: All sections fits too — the 260 px box is marked to fit, three whole rows shown, three not drawn, '+ 3 more lines today · 1 471 t' under it",
         !!lb && lb.getAttribute("data-today-fit") === "1" && lb.style.maxHeight === "260px"
         && m.el.querySelectorAll("tr.today-cut").length === 3 && !!mm && norm(mm.textContent) === "+ 3 more lines today · 1 471 t",
         mm ? norm(mm.textContent) : "no count line");
      ok("UI FIX 6 card 4: in All sections every row is drawn closed (the desk opened the busiest), and both progress bars stay above the list",
         [...m.el.querySelectorAll("tr.rd-details")].every(d => d.hidden)
         && m.el.querySelector('tr[data-rd="today-R1|D0|"] .rd-chev').getAttribute("aria-expanded") === "false"
         && m.el.querySelectorAll(".h-2.rounded-full.bg-slate-100").length === 2 && norm(m.el.textContent).includes("This week to date"));
      m.done();
    }
    {
      const m = mount({ wall: false, fill: false });
      fire();
      const lb = m.el.querySelector(".today-lines");
      ok("UI FIX 6 card 4: the working Dashboard is unchanged — no fit marker, no row left off, no count line, its 190px box, and the row opened at the desk is open",
         !!lb && !lb.hasAttribute("data-today-fit") && lb.style.maxHeight === "190px" && m.el.querySelectorAll("tr.rd-row").length === 6
         && !m.el.querySelector(".today-cut") && !m.el.querySelector("[data-today-more]")
         && m.el.querySelector('tr[data-rd="today-R1|D0|"] .rd-chev').getAttribute("aria-expanded") === "true"
         && !m.el.querySelector('tr[data-rd-details="today-R1|D0|"]').hidden);
      m.done();
    }
  } finally {
    w.Element.prototype.getBoundingClientRect = realRect;
    if (hadOwn) Object.defineProperty(w.HTMLElement.prototype, "clientHeight", hadOwn); else delete w.HTMLElement.prototype.clientHeight;
    delete w.ResizeObserver;
    w.sessionStorage.removeItem("modus_rows_today");
  }
}

(async () => {
  try { await routesDriversDom(); ok("ROUTES DOM: the section ran to the end", true); }
  catch (e) { ok("ROUTES DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await demoBar(); ok("DEMO BAR: the section ran to the end", true); }
  catch (e) { ok("DEMO BAR: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await lateBar(); ok("MAP UNDER THE BAR: the section ran to the end", true); }
  catch (e) { ok("MAP UNDER THE BAR: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await reloadResume(); ok("RELOAD: the section ran to the end", true); }
  catch (e) { ok("RELOAD: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await g3LoginsDom(); ok("G3 LOGINS: the section ran to the end", true); }
  catch (e) { ok("G3 LOGINS: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await configEstonianColumn(); ok("CONFIG (11 Oct 2026 review): the section ran to the end", true); }
  catch (e) { ok("CONFIG (11 Oct 2026 review): the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await carbonTargetDom(); } catch (e) { ok("CARBON DOM: the section ran to the end", false, e && e.stack); }
  try { await gateArrivalsDom(); ok("GATE DOM: the section ran to the end", true); }
  catch (e) { ok("GATE DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await simDom(); ok("SIM DOM: the section ran to the end", true); }
  catch (e) { ok("SIM DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await simWallDom(); ok("SIM WALL DOM: the section ran to the end", true); }
  catch (e) { ok("SIM WALL DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await clpDom(); ok("CLP DOM: the section ran to the end", true); }
  catch (e) { ok("CLP DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await infoTipDom(); ok("INFO BOX: the section ran to the end", true); }
  catch (e) { ok("INFO BOX: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { await chartBoxDom(); ok("CHART BOX: the section ran to the end", true); }
  catch (e) { ok("CHART BOX: the section ran to the end", false, String(e && e.stack || e).slice(0, 400)); }
  try { keptAppLoader(); ok("SPEED: the loader section ran to the end", true); }
  catch (e) { ok("SPEED: the loader section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await rowDetailsDom(); ok("ROW DETAILS: the section ran to the end", true); }
  catch (e) { ok("ROW DETAILS: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await phoneShellDom(); ok("PHONE: the section ran to the end", true); }
  catch (e) { ok("PHONE: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  try { await phoneDayFlagsDom(); ok("PHONE DAY FLAGS: the section ran to the end", true); }
  catch (e) { ok("PHONE DAY FLAGS: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  // 22 Oct 2026 (UI fix 6, card 5): the big screen's Today list fitted to its box
  try { await todayFitDom(); ok("TODAY FIT: the section ran to the end", true); }
  catch (e) { ok("TODAY FIT: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  console.log(`\n${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
})();
