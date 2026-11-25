/*
 * ui_fix_la_words.js — the Look-ahead rethink, task B1 (25 Nov 2026; cards 2 and 5 of notes\lookahead-rethink-mockup-1124,
 * John's "Yes, as recommended" to Q1 to Q19, and his "Yes, as recommended" on 25 Nov to the Last week tab's link):
 * the strip's seven figures, Last week's four, the four tabs, the road-closures line, the flag words and the Look-ahead's
 * own words ("lorries", "fuel surcharge").
 *
 * Mounts the real LookAhead (jsdom, the page's own code) on the fixture page with its figures set to card 2's. Proves:
 *   - the strip: seven labelled figures in card 2's order, each value and unit, at most one second line; every state of
 *     a second line (chained, not routed, typed, stale, unavailable, fair price, n of m priced, no rate, short past the
 *     share with the amber edge, short under it, nothing short); the edge only on Delivered last week; the step-down;
 *   - the tabs: Last week · This week · Next week · Weeks ahead, the one aria-current, the week each reads (bucket), the
 *     place line, the subtitle, the remembered tab; the link "This week so far", its button "Add to next week", and
 *     "Delivered this week" on Next week (John's three additions to card 5);
 *   - Last week's four figures; the closures line's four forms and the unavailable words, with no source, no ISO date,
 *     no "UTC", no route code; "Route cap" and "<team word> share"; no "BAF" and no "vehicles" on the Look-ahead's screens;
 *   - gone, at source: the switch, "Commit · this week", "vehicles a day at the peak", "re-check", the old captions.
 * What it does NOT prove: a real browser's layout (the container query's columns, the edge's look, Dark): the Chrome
 * pictures in notes\lookahead-rethink-mockup-1124\built\words\.
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_la_words.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
process.env.HARNESS_TODAY = process.env.HARNESS_TODAY || "2026-11-25";
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const src = code.replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const FIX = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", f), "utf8"));
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const LA = between("function LookAhead({ meta, who, access, initialPage, initialView", "\nfunction PhoneLookAhead(");
const FW = between("function FuelWidget({ who, access, mode, initial, onChanged }){", "\nfunction LookAhead(");

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
// a fetch router: a matching key answers with its JSON; anything else waits for ever (the page keeps initialPage)
let ROUTES = {}; let CALLS = [];
w.fetch = (u) => { CALLS.push(String(u));
  for (const [k, v] of Object.entries(ROUTES)) if (String(u).includes(k)) {
    const d = typeof v === "function" ? v(String(u)) : v;
    return Promise.resolve({ ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(d)) }); }
  return new Promise(() => {}); };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.Element.prototype.scrollIntoView = function(){};
w.matchMedia = () => ({ matches: false, addEventListener(){}, removeEventListener(){} });
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__F = { grp, dist, TENANT, TEAM, RAIL_LABEL, LINE_FLAG_LABEL, INFO, laDay, laWhen };");
const F = w.__F;
F.TENANT.symbol = "£"; F.TENANT.distance_unit = "mi"; F.TENANT.fuel_index_auto = true; F.TENANT.team_label = "Package";

const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
const flush = async () => { for (let i = 0; i < 4; i++) await act(async () => { await new Promise(r => setTimeout(r, 0)); }); };
const mount = async (props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  await act(async () => { r.render(w.React.createElement(w.LookAhead, props)); }); await flush();
  return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const click = async (el) => { await act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await flush(); };

// ---------------------------------------------------------------- the page, at card 2's figures
const BASE = FIX("lookahead_page.json");
const TKM_KM = 315905 * 1.609344;          // 315,905 tonne-miles
const page = (o = {}) => {
  const p = JSON.parse(JSON.stringify(BASE));
  Object.assign(p.commit.totals, { planned_t: 8464, trips: 410, vehicles_peak: 30, tonne_km: TKM_KM, lines: 22, unbaked_lines: 0,
    excludes_unbaked: false, eur: 60764, eur_lines: 22, eur_partial: false, eur_target_lines: 4, eur_adj: 61980, fair_eur: 47276, fair_lines: 22 }, o.totals || {});
  Object.assign(p.account, { delivered: 19, lines: 22, reported: 22, actual_t: 7891, shortfall: 575, shortfall_t: 575, short_flagged: 3,
    open_to_calibrate: 3, short_flag_pct: 10 }, o.account || {});
  p.account.rows = p.account.rows.map((r, i) => i === 0 ? { ...r, planned_qty: 1000, actual_qty: 800, remaining_short: 200, remaining_short_t: 200,
    calibrated_at: null, calibrated_qty: null, action: "spread" } : r);
  Object.assign(p.costing, { index_eur_per_l: 1.933, index_bulletin_date: "2026-11-23", index_source: "desnz" }, o.costing || {});
  p.clashes.sources = Object.assign({}, p.clashes.sources, { restrictions: "ok", restrictions_checked_at: "2026-11-24 14:56:00",
    restrictions_unchecked: [], restrictions_refresh: { running: false, status: "ok" },
    restrictions_ui_label: "Road closures (National Highways)" }, o.sources || {});
  return p;
};
const META = { routes: [], materials: ["Small aggregate"], vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {}, vehicle_emissions_kg_co2e_per_km: {},
  planning: { working_days_per_month: 21 } }, mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] },
  disciplines: [], sections: [], work_sections: [] };
const figs = (el, strip = "lookahead") => [...el.querySelectorAll(`[data-fig-strip="${strip}"] [data-la-fig]`)].map(c => ({
  c, label: c.getAttribute("data-la-fig"), num: norm((c.querySelector(".la-fig-num") || {}).textContent),
  unit: norm((c.querySelector(".la-fig-unit") || {}).textContent),
  sub: norm((c.querySelector(".la-fig-sub") || {}).textContent), warn: !!c.querySelector('[data-la-fig-sub="warn"]'),
  edge: c.classList.contains("la-fig-warn") }));
const fig = (el, label, strip) => figs(el, strip).find(f => f.label === label) || {};

(async () => {
try {
  // ---------------------------------------------------------------- the strip, as card 2 draws it
  w.localStorage.clear(); ROUTES = {}; CALLS = [];
  let m = await mount({ meta: META, who: "t", initialPage: page() });
  let F7 = figs(m.el);
  ok("⭐ STRIP: seven figures, labelled in card 2's order", F7.map(f => f.label).join("|")
     === "Planned|Loads|Lorries, busiest day|Tonne-miles|Diesel, per litre|Planned cost|Delivered last week", F7.map(f => f.label).join("|"));
  ok("⭐ STRIP: the values and units as card 2: 8,464 t · 410 · 30 · 315,905 · £1.933 · £60,764 · 19 of 22 lines",
     fig(m.el, "Planned").num === "8,464t" && fig(m.el, "Planned").unit === "t" && fig(m.el, "Loads").num === "410"
     && fig(m.el, "Lorries, busiest day").num === "30" && fig(m.el, "Tonne-miles").num === "315,905"
     && fig(m.el, "Diesel, per litre").num === "£1.933" && fig(m.el, "Planned cost").num === "£60,764"
     && fig(m.el, "Delivered last week").num === "19 of 22lines" && fig(m.el, "Delivered last week").unit === "lines",
     F7.map(f => f.num).join("|"));
  ok("STRIP: each label sits over its figure (the label first in the cell, its own class)",
     F7.every(f => f.c.firstElementChild && f.c.firstElementChild.classList.contains("la-fig-label")));
  ok("⭐ STRIP: second lines: Diesel \"23 Nov\", Planned cost \"fair price £47,276\", Delivered \"3 short · 575 t\" (amber), the rest none",
     fig(m.el, "Diesel, per litre").sub === "23 Nov" && !fig(m.el, "Diesel, per litre").warn
     && fig(m.el, "Planned cost").sub === "fair price £47,276" && !fig(m.el, "Planned cost").warn
     && fig(m.el, "Delivered last week").sub === "3 short · 575 t" && fig(m.el, "Delivered last week").warn
     && ["Planned", "Loads", "Lorries, busiest day", "Tonne-miles"].every(l => fig(m.el, l).sub === ""), F7.map(f => f.sub).join("|"));
  ok("⭐ STRIP: the 4 px amber edge only on Delivered last week while its status shows; at most ONE second line a cell",
     F7.filter(f => f.edge).map(f => f.label).join("|") === "Delivered last week" && F7.every(f => f.c.querySelectorAll(".la-fig-sub").length <= 1));
  ok("STRIP: Diesel and Planned cost carry an \"i\"; the others none", F7.filter(f => f.c.querySelector(".la-fig-label button, .la-fig-label [aria-label]")).map(f => f.label).join("|")
     === "Diesel, per litre|Planned cost", F7.filter(f => f.c.querySelector(".la-fig-label button, .la-fig-label [aria-label]")).map(f => f.label).join("|"));
  const stripTxt = norm(m.el.querySelector('[data-fig-strip="lookahead"]').textContent);
  ok("⭐ STRIP: no BAF, no \"vehicles\", no \"planned this week\", no \"(model\", no \"t·mi\", no country on the strip",
     !/BAF|vehicles|planned this week|\(model|t·mi|t·km|\bEE\b|GB/.test(stripTxt), stripTxt);
  ok("STRIP: the place line reads \"Track · This week\", the subtitle the week's dates and \"Mon to Fri\"",
     norm(m.el.textContent).includes("Track · This week") && norm(m.el.textContent).includes("· Mon to Fri"));
  m.done();

  // each second-line state, one at a time
  const state = async (o, label) => { w.localStorage.clear(); const mm = await mount({ meta: META, who: "t", access: o.access, initialPage: page(o) });
    const f = fig(mm.el, label); mm.done(); return f; };
  let f;
  f = await state({ totals: { eur_lines: 20 } }, "Planned cost");
  ok("⭐ STATE: not every line priced: \"20 of 22 priced\" in amber, no fair price", f.sub === "20 of 22 priced" && f.warn && !f.edge, f.sub);
  f = await state({ totals: { eur: null, eur_lines: 0, fair_eur: null } }, "Planned cost");
  ok("STATE: no rate: the figure \"—\" and \"no rate set\"", f.num === "—" && f.sub === "no rate set" && !f.warn, f.num + "|" + f.sub);
  f = await state({ account: { short_flagged: 0, shortfall_t: 0, shortfall: 0, delivered: 22 } }, "Delivered last week");
  ok("⭐ STATE: nothing short: no second line, no edge", f.sub === "" && !f.edge && f.num === "22 of 22lines", f.sub);
  f = await state({ account: { short_flagged: 0, shortfall_t: 120, shortfall: 120 } }, "Delivered last week");
  ok("⭐ STATE: short under the share: a grey \"120 t to carry\", no edge", f.sub === "120 t to carry" && !f.warn && !f.edge, f.sub);
  f = await state({ totals: { excludes_unbaked: true, unbaked_lines: 2 } }, "Lorries, busiest day");
  ok("⭐ STATE: a line not routed: \"some lines not routed\" in amber (the diamond), no edge", f.sub === "some lines not routed" && f.warn && !f.edge, f.sub);
  f = await state({ costing: { index_source: "manual" } }, "Diesel, per litre");
  ok("STATE: a typed price: \"typed 23 Nov\"", f.sub === "typed 23 Nov" && !f.warn, f.sub);
  f = await state({ costing: { index_eur_per_l: null, index_bulletin_date: null } }, "Diesel, per litre");
  ok("STATE: no price: \"Index unavailable\", and \"not set\" for a reader", f.num === "Index unavailable" && f.sub === "not set", f.num + "|" + f.sub);
  f = await state({ costing: { index_eur_per_l: null, index_bulletin_date: null }, access: { can_approve: true, role: "admin" } }, "Diesel, per litre");
  ok("STATE: no price, an admin: \"type a price on Config\"", f.sub === "type a price on Config", f.sub);
  ROUTES = { "/fuel-index": { index: { eur_per_l: 1.901, bulletin_date: "2026-11-10", source: "desnz", stale: true, refresh: null }, fuel: {}, summary: {} } };
  f = await state({}, "Diesel, per litre");
  ROUTES = {};
  ok("⭐ STATE: a stale price: \"stale · 10 Nov\" in amber (the diamond), the last good price kept", f.sub === "stale · 10 Nov" && f.warn && f.num === "£1.901", f.num + "|" + f.sub);
  f = await state({ totals: { planned_t: 1234567, eur: 123456 } }, "Planned");
  const fc = fig((await (async () => { w.localStorage.clear(); const mm = await mount({ meta: META, who: "t", initialPage: page({ totals: { eur: 123456 } }) }); const e = mm.el; return { el: e, mm }; })()).el, "Planned cost");
  ok("⭐ STATE: the figure steps down a size from 8 characters: \"1,234,567\" and \"£123,456\" smaller, \"£60,764\" not",
     f.c.querySelector(".la-fig-num").classList.contains("text-xl") && fc.c.querySelector(".la-fig-num").classList.contains("text-xl")
     && !fc.c.querySelector(".la-fig-num").classList.contains("text-2xl"));
  w.document.body.innerHTML = "";

  // the chained peak, through the Lorry plan's own read (mounted without initialPage, as on live); the read's shape as
  // dom_frontend.js's lorryPlanDom gives it, no yard rows (the panel is folded)
  const LPD = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"];
  const byD = (a) => Object.fromEntries(LPD.map((d, i) => [d, a[i]]));
  const vw = (a, saved) => ({ by_day: byD(a), week: a.reduce((x, y) => x + y, 0), saved_week: saved, days: Object.fromEntries(LPD.map(d => [d, []])) });
  const LP = { week: { from: LPD[0], to: "2026-11-29", bucket: "commit" }, days: LPD, today: LPD[2], view_default: "chained", views: ["booked", "chained", "compressed"],
    shift_hours: 10, team_only: null, made_by: "Planner", made_at: "25 Nov 2026 09:00", week_confirmed: false, any_confirmed: false,
    booked: vw([30, 28, 27, 26, 25], 0), chained: vw([19, 17, 18, 16, 15], 51), compressed: { ...vw([18, 17, 17, 16, 15], 54), moves: [], lines: {}, flags: [] },
    day_hire: { rates: {}, typed: false, chained: null, compressed: null },
    words: { rule: "", planning: "", compress: "", one_yard: "", not_modelled: "", sends_nothing: "", estimate: "" } };
  w.localStorage.clear(); CALLS = [];
  ROUTES = { "/lookahead?": page(), "/lorry-plan?": LP };
  m = await mount({ meta: META, who: "t" });
  f = fig(m.el, "Lorries, busiest day");
  ok("⭐ STATE: chaining saves a lorry: \"19 if chained\" (the busiest chained day)", f.sub === "19 if chained", f.sub || norm(m.el.textContent).slice(0, 200));
  m.done(); ROUTES = {};

  // ---------------------------------------------------------------- the tabs
  w.localStorage.clear(); CALLS = [];
  m = await mount({ meta: META, who: "t", initialPage: page() });
  const tabs = () => [...m.el.querySelectorAll("button.ws-tab[data-la-tab-id]")];
  const cur = () => tabs().filter(b => b.getAttribute("aria-current") === "page").map(b => b.textContent).join("|");
  ok("⭐ TABS: Last week · This week · Next week · Weeks ahead, the one tab class; This week current at first",
     tabs().map(b => b.textContent).join("|") === "Last week|This week|Next week|Weeks ahead" && cur() === "This week", tabs().map(b => b.textContent).join("|"));
  ok("TABS: no switch beside them (no \"this week | next week\" buttons)", ![...m.el.querySelectorAll("button")].some(b => /^(this|next) week$/.test(b.textContent)));
  await click(tabs()[2]);
  ok("⭐ TABS: Next week reads the week after (bucket=next), is remembered, and its last figure reads \"Delivered this week\"",
     CALLS.some(u => u.includes("/lookahead?bucket=next")) && cur() === "Next week" && w.localStorage.getItem("modus_la_view") === "next"
     && !!fig(m.el, "Delivered this week").c && !fig(m.el, "Delivered last week").c && norm(m.el.textContent).includes("Track · Next week"));
  CALLS = [];
  await click(tabs()[0]);
  const L4 = figs(m.el, "lookahead-last");
  ok("⭐ LAST WEEK: four figures: Delivered 19 of 22 lines · within 2 % of plan; Moved 7,891 t · 22 of 22 reported; Short 575 t · not yet added; Can be added 3 lines",
     L4.map(x => `${x.label}=${x.num}/${x.sub}`).join("|")
     === "Delivered=19 of 22lines/within 2 % of plan|Moved=7,891t/22 of 22 reported|Short=575t/not yet added|Can be added=3lines/", L4.map(x => `${x.label}=${x.num}/${x.sub}`).join("|"));
  ok("LAST WEEK: reads the week before (bucket=commit), remembered as \"account\", the place line \"Track · Last week\"",
     CALLS.some(u => u.includes("/lookahead?bucket=commit")) && cur() === "Last week" && w.localStorage.getItem("modus_la_view") === "account"
     && norm(m.el.textContent).includes("Track · Last week"));
  const sofar = m.el.querySelector("button[data-la-sofar]");
  const addBtns = () => [...m.el.querySelectorAll("button")].filter(b => /^Add to (this|next) week$/.test(b.textContent)).map(b => b.textContent);
  ok("⭐ JOHN'S ADDITION 1: the quiet link \"This week so far\" in Last week's subtitle", !!sofar && sofar.textContent === "This week so far" && sofar.classList.contains("la-sofar"));
  ok("⭐ JOHN'S ADDITION 2a: on Last week a shortfall's button reads \"Add to this week\"", addBtns().length >= 1 && addBtns().every(t => t === "Add to this week"), addBtns().join("|"));
  CALLS = [];
  await click(sofar);
  ok("⭐ JOHN'S ADDITION 2b: This week so far reads the running week (bucket=next), keeps Last week current, and its button reads \"Add to next week\"",
     CALLS.some(u => u.includes("/lookahead?bucket=next")) && cur() === "Last week" && addBtns().length >= 1 && addBtns().every(t => t === "Add to next week")
     && norm(m.el.textContent).includes("Track · This week so far") && !m.el.querySelector("button[data-la-sofar]"), addBtns().join("|"));
  ok("JOHN'S ADDITION 2c: This week so far is remembered as Last week (never opens by itself)", w.localStorage.getItem("modus_la_view") === "account");
  ok("LAST WEEK: its Fuel row says \"Fuel surcharge\", never \"BAF\"", !/BAF/.test(norm(m.el.querySelector('[data-fuel-widget="strip"]').textContent))
     && /Fuel surcharge/.test(norm(m.el.querySelector('[data-fuel-widget="strip"]').textContent)), norm(m.el.querySelector('[data-fuel-widget="strip"]').textContent));
  await click(tabs()[3]);
  ok("TABS: Weeks ahead is remembered, its roles in the tabs' words (no \"COMMIT\", no \"ACCOUNT\")",
     w.localStorage.getItem("modus_la_view") === "horizon" && cur() === "Weeks ahead" && !/>(COMMIT|ACCOUNT)</.test(m.el.innerHTML));
  m.done();
  m = await mount({ meta: META, who: "t", initialPage: page() });
  ok("TABS: the remembered tab opens next time (Weeks ahead)", [...m.el.querySelectorAll("button.ws-tab[aria-current=page]")].map(b => b.textContent).join() === "Weeks ahead");
  m.done();
  w.localStorage.setItem("modus_la_view", "sofar");
  m = await mount({ meta: META, who: "t", initialPage: page() });
  ok("TABS: a stored \"sofar\" opens This week, never the running week's account", [...m.el.querySelectorAll("button.ws-tab[aria-current=page]")].map(b => b.textContent).join() === "This week");
  m.done();

  // ---------------------------------------------------------------- the road-closures line
  const closures = async (s) => { w.localStorage.clear(); const mm = await mount({ meta: META, who: "t", initialPage: page({ sources: s }) });
    const span = mm.el.querySelector("[data-la-closures]"); const box = span ? span.parentElement : null;
    const r = { text: norm(span && span.textContent), all: norm(box && box.textContent), btn: box ? [...box.querySelectorAll("button")].map(b => norm(b.textContent)).join("|") : "" };
    mm.done(); return r; };
  const clean = (t) => !/UTC|\d{4}-\d\d-\d\d|National Highways|Tark Tee|\bR\d{3}\b|re-check/.test(t);
  let c = await closures({});
  ok("⭐ CLOSURES: \"Road closures checked 24 Nov, 14:56 · Check again\" (UK time, no source, no ISO date, no UTC)",
     c.text === "Road closures checked 24 Nov, 14:56" && c.btn === "Check again" && clean(c.all), c.all);
  c = await closures({ restrictions: "partial", restrictions_unchecked: ["R001", "R002", "R003"] });
  ok("⭐ CLOSURES: a count of routes, never their codes: \"Road closures: 3 routes not checked since they were re-routed · Check now\"",
     c.text === "Road closures: 3 routes not checked since they were re-routed" && c.btn === "Check now" && clean(c.all), c.all);
  c = await closures({ restrictions: "partial", restrictions_unchecked: ["R001"] });
  ok("CLOSURES: one route: \"1 route not checked since it was re-routed\"", c.text === "Road closures: 1 route not checked since it was re-routed", c.text);
  c = await closures({ restrictions: "unchecked", restrictions_checked_at: null });
  ok("⭐ CLOSURES: never checked: \"Road closures not checked for these routes · Check now\"", c.text === "Road closures not checked for these routes" && c.btn === "Check now" && clean(c.all), c.all);
  c = await closures({ restrictions_refresh: { running: true } });
  ok("CLOSURES: while it runs: \"Road closures: checking…\", no button", c.text === "Road closures: checking…" && c.btn === "", c.all);
  c = await closures({ restrictions_refresh: { running: false, status: "unavailable" } });
  ok("⭐ CLOSURES: the check could not be made: \"· the check could not be made: showing the last one\"",
     c.all.includes("· the check could not be made: showing the last one") && clean(c.all), c.all);

  // ---------------------------------------------------------------- flag words, words, infos
  ok("⭐ FLAG WORDS: \"Route cap\" for Cap; \"<team word> share\" for Share, through TEAM()",
     F.LINE_FLAG_LABEL.ROUTE_CAP === "Route cap" && F.RAIL_LABEL.ROUTE_CAP === "Route cap"
     && F.LINE_FLAG_LABEL.IPT_SHARE === "Package share" && F.RAIL_LABEL.IPT_SHARE === "Package share");
  F.TENANT.team_label = "Team";
  ok("FLAG WORDS: the default team word reads \"Team share\"", F.LINE_FLAG_LABEL.IPT_SHARE === "Team share");
  const words = (t) => t.split(/\s+/).filter(Boolean).length;
  ok("⭐ INFO: the two new \"i\" boxes are two sentences, 30 words at most, and name no source",
     ["la.fig_diesel", "la.fig_cost"].every(k => F.INFO[k] && words(F.INFO[k].text) <= 30 && (F.INFO[k].text.match(/\./g) || []).length === 2
       && !/DESNZ|Bulletin|EuroOilWatch|Oil Bulletin|BAF/.test(F.INFO[k].text + (F.INFO[k].how || ""))),
     ["la.fig_diesel", "la.fig_cost"].map(k => words((F.INFO[k] || {}).text || "")).join(","));
  ok("⭐ GONE (source): the switch, \"Commit · this week\", \"vehicles a day at the peak\", \"Cycles a vehicle a day\", \"BAF\" in the Look-ahead",
     LA.length > 1000 && !LA.includes("Commit · this week") && !LA.includes("Commit · next week") && !LA.includes('[["commit", "this week"], ["next", "next week"]]')
     && !LA.includes("vehicles a day at the peak") && !LA.includes("Cycles a vehicle a day") && !/["`>][^"`<]*BAF/.test(LA.replace(/\/\/.*$/gm, "")));
  ok("⭐ GONE (source): the closures line's \"re-check\", \"UTC\" and the stored time's slice; the old captions",
     !LA.includes(">re-check<") && !LA.includes(" UTC") && !LA.includes("restrictions_checked_at).slice") && !LA.includes('caption="loads"')
     && !LA.includes('caption="lines delivered last week"') && !LA.includes('caption="short last week"') && !code.includes("xl:grid-cols-8"));
  ok("GONE (source): \"BAF: set a base\" leaves the strip; the FuelWidget's Look-ahead modes say \"Fuel surcharge\"",
     FW.includes('const SUR = mode === "config" ? "BAF" : "Fuel surcharge";') && !FW.includes('"BAF: set a base on Confirm week"'));
  ok("CSS: seven across from 1,000 px of the strip's own width, four below 1,000, two a row at phone width; the edge is a 4 px gold top",
     html.includes(".la-figs-box{container-type:inline-size;}") && html.includes("@container (min-width:1000px){.fig-strip.la-figs:not(.la-figs-4){grid-template-columns:repeat(7,minmax(0,1fr));}}")
     && html.includes("@container (min-width:560px){.fig-strip.la-figs{grid-template-columns:repeat(4,minmax(0,1fr));}}")
     && html.includes(".fig-strip.la-figs{grid-template-columns:repeat(2,minmax(0,1fr));")
     && html.includes('.fig-strip.la-figs>.la-fig-warn::before{content:"";position:absolute;left:0;right:0;top:0;height:4px;background:var(--gold);}'));
} catch (e) {
  fail.push("CRASH " + (e && e.stack || e));
}
console.log(`ui_fix_la_words.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(x => console.log("  FAIL: " + x));
process.exit(fail.length ? 1 : 0);
})();
