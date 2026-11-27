/*
 * ui_fix_la_site_papers.js — the Look-ahead rethink, task C2 (25 Nov 2026, `claude/la-site-papers`; cards 5 and 6 of
 * notes\lookahead-rethink-mockup-1124, John's "Yes, as recommended"): Last week's account and the weeks ahead grouped by
 * SITE, with task A's rule only (the server's `row.site`, the order `page.site_order` = Data → Locations).
 *
 * Mounts the real LookAhead (jsdom, the page's own code) on a made-up page. What it proves:
 *   - Last week: a ruled heading a site in the server's order, "n of m delivered" and, when something is still short,
 *     "n t short", amber only when a row of the site is past the share (short_flag); a one-row site is ONE row; rows
 *     named "From <origin>", an out row last "Out, to <destination>"; folds and "Open all · Fold all"; open at a desk;
 *     the Tonnes | Cost switch, the cost columns, an unreported actual's box, "Add to this week" and the pinned Action
 *     column still there; a team login's sites carry its team;
 *   - the weeks ahead: the same headings with each week's total in tonnes (the lines' own planned_t added), "n t out";
 *     the headings add up to the lines; open at a desk up to 40 lines, folded on every width past 40;
 *   - the tablet: both folded to start; a page with no `site` keeps the old one-row-a-line table.
 * What it does NOT prove: a real browser's layout (the Chrome pictures in notes\lookahead-rethink-mockup-1124\built\papers\).
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_la_site_papers.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const src = code.replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const FIX = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", f), "utf8"));

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.Element.prototype.scrollIntoView = function(){};
let TABLET = false;
w.matchMedia = (q) => ({ matches: TABLET && q === "(min-width: 768px) and (max-width: 1024px)", addEventListener(){}, removeEventListener(){} });
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__F = { grp, laRowSites, LA_HZ_FOLD_OVER };");
const F = w.__F;

const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
const tnum = (t) => { const m = norm(t).replace(/,/g, "").match(/-?\d+(\.\d+)?/); return m ? +m[0] : 0; };

// ---------------------------------------------------------------- the made-up page
const BASE = FIX("lookahead_page.json");
const A0 = BASE.account.rows[0];
const SITE = (id, name, type, dir = "in") => ({ id, name, type, dir });
const HA = SITE("L001", "Harborough Compound", "Compound"), TC = SITE("L002", "Tilton Compound", "Compound");
const TV = SITE("L003", "Tilton Viaduct site", "Site"), TVout = SITE("L003", "Tilton Viaduct site", "Site", "out");
const ORDER = ["L001", "L002", "L003"];
const ROUTES = [
  ["R10", "Kilby Ridge Quarry", "Harborough Compound"], ["R11", "Harborough Rail Freight Terminal", "Harborough Compound"],
  ["R12", "Wolds Link Batching Plant", "Tilton Compound"], ["R13", "Northfield Quarry", "Tilton Viaduct site"],
  ["R14", "Tilton Viaduct site", "Wolds Link Inert Landfill"], ["R15", "Brook Pit", "Tilton Viaduct site"]];
// Last week: R10 short past the share (amber), R11 delivered, R12 its site's one row (not reported yet), R13 short under
// the share (grey), R14 the out row, R15 delivered; the server's order of rows is NOT the site order (R14 comes first)
const acctRow = (route, sec, site, o = {}) => ({ ...A0, route_id: route, section_id: sec, discipline: "earthworks", ipt: o.ipt || "IPT1", site,
  planned_qty: o.planned ?? 500, planned_t: o.planned ?? 500, actual_qty: o.actual === undefined ? 500 : o.actual, actual_at: o.actual === null ? null : "<ts>",
  held: !!o.held, action: o.action || (o.held ? "held" : "spread"), short_flag: !!o.flag, remaining_short_t: o.short || 0, remaining_short: o.short || 0,
  variance: o.short || 0, carried: 0 });
const ACCT = (ipt) => [
  acctRow("R14", "WS4", TVout, { held: true, ipt }),
  acctRow("R10", "WS1", HA, { short: 120, flag: true, actual: 380, ipt }),
  acctRow("R11", "WS1", HA, { held: true, ipt: ipt || "IPT2" }),
  acctRow("R12", "WS4", TC, { actual: null, action: "waiting", ipt }),
  acctRow("R13", "WS4", TV, { short: 20, actual: 480, ipt }),
  acctRow("R15", "WS4", TV, { held: true, ipt }),
];
// the weeks ahead: the fixture's weeks, one row a line a week, each with its planned_t
const WEEKS = BASE.horizon.rows.filter(r => r.route_id === "R1" && r.section_id === "WS1").map(r => [r.month_index, r.week_index, r.role || null]);
const hzLine = (route, sec, site, t, ipt = "IPT1") => WEEKS.map(([m, wk, role], i) => ({ ...BASE.horizon.rows[0], route_id: route, section_id: sec,
  discipline: "earthworks", month_index: m, week_index: wk, role, ipt, site, planned_qty: t + i, planned_t: t + i }));
const HZ = (extra = 0) => [
  ...hzLine("R14", "WS4", TVout, 80), ...hzLine("R10", "WS1", HA, 200), ...hzLine("R11", "WS1", HA, 10, "IPT2"),
  ...hzLine("R12", "WS4", TC, 40), ...hzLine("R13", "WS4", TV, 60), ...hzLine("R15", "WS4", TV, 30),
  ...Array.from({ length: extra }, (_, i) => hzLine("R" + (100 + i), "WS4", TV, 5)).flat(),
];
const pageOf = ({ ipt = null, extra = 0, sites = true } = {}) => {
  const strip = (rs) => sites ? rs : rs.map(r => { const x = { ...r }; delete x.site; return x; });
  return { ...BASE, site_order: sites ? ORDER : undefined,
    account: { ...BASE.account, rows: strip(ACCT(ipt)) },
    horizon: { ...BASE.horizon, rows: strip(HZ(extra)) } };
};
const META = { routes: ROUTES.map(([route_id, origin, dest]) => ({ route_id, origin, dest })), materials: ["Small aggregate"],
  vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: { "Small aggregate": 1.6 }, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } },
  mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [],
  work_sections: [{ section_id: "WS1", name: "Harborough approach" }, { section_id: "WS4", name: "Tilton viaduct" }] };
const view = (page, v, more = {}) => mount(w.LookAhead, { meta: META, who: "t", initialPage: page, initialView: v, ...more });
const heads = (el) => [...el.querySelectorAll("tr.la-xsite")];
const under = (h) => { const out = []; let x = h.nextElementSibling; while (x && !x.classList.contains("la-xsite")) { if (x.classList.contains("la-xln")) out.push(x); x = x.nextElementSibling; } return out; };
const ends = (tr) => norm(tr.querySelector("[data-la-ends]").textContent);

try {
  // ---------------------------------------------------------------- the helper
  const g = F.laRowSites(ACCT(), ORDER);
  ok("⭐ laRowSites: the sites in the server's order (Data → Locations), whatever the rows' order; an out row last under its site",
     g.map(x => x.id).join("|") === "L001|L002|L003" && g[2].rows.map(r => r.route_id).join("|") === "R13|R15|R14", g.map(x => x.id).join("|"));
  const g2 = F.laRowSites([...ACCT(), { ...ACCT()[0], route_id: "R99", site: undefined }], ORDER);
  ok("laRowSites: a row with no site goes last, under \"Other lines\"", g2[g2.length - 1].name === "Other lines" && g2[g2.length - 1].rows[0].route_id === "R99");
  ok("laRowSites: with no site order the sites keep the order their rows come in", F.laRowSites(ACCT(), null).map(x => x.id).join("|") === "L003|L001|L002");

  // ---------------------------------------------------------------- Last week, at a desk
  w.sessionStorage.clear();
  let d = view(pageOf(), "account");
  let el = d.el;
  let H = heads(el);
  ok("⭐ LAST WEEK: one ruled heading a site, in the server's order", H.map(h => h.getAttribute("data-la-site")).join("|") === "L001|L002|L003",
     H.map(h => h.getAttribute("data-la-site")).join("|"));
  const [hA, hB, hC] = H;
  ok("⭐ LAST WEEK: a heading reads its name, type · n lines, and \"n of m delivered\"",
     norm(hA.querySelector(".la-sn").textContent) === "Harborough Compound" && norm(hA.textContent).includes("Compound · 2 lines")
     && norm(hC.querySelector("[data-la-acct-site]").textContent).startsWith("2 of 3 delivered"), norm(hC.textContent));
  ok("⭐ LAST WEEK: \"n t short\" AMBER only where a row is past the share (short_flag); grey under it",
     hA.querySelector("[data-la-acct-site]").getAttribute("data-la-acct-site") === "short" && !!hA.querySelector(".la-acct-short")
     && norm(hA.querySelector(".la-acct-short").textContent) === "120 t short"
     && hC.querySelector("[data-la-acct-site]").getAttribute("data-la-acct-site") === "quiet" && !hC.querySelector(".la-acct-short")
     && norm(hC.querySelector("[data-la-acct-site]").textContent).includes("20 t short"));
  ok("LAST WEEK: a site with nothing short says only \"n of m delivered\"",
     hB.querySelector("[data-la-acct-site]").getAttribute("data-la-acct-site") === "ok" && norm(hB.querySelector("[data-la-acct-site]").textContent) === "0 of 1 delivered");
  ok("⭐ LAST WEEK: a site with ONE row is that one row (no fold button), named by where it comes from",
     !hB.querySelector(".la-fold") && !!hB.querySelector("[data-la-ends]") && ends(hB) === "From Wolds Link Batching Plant");
  const cRows = under(hC);
  ok("⭐ LAST WEEK: under a site its rows read \"From <origin>\", the out row LAST \"Out, to <destination>\"",
     cRows.map(ends).join(" | ") === "From Northfield Quarry | From Brook Pit | Out, to Wolds Link Inert Landfill", cRows.map(ends).join(" | "));
  ok("LAST WEEK: the route code stays on the row's second line", norm(cRows[0].textContent).includes("R13"));
  ok("LAST WEEK: a site of two rows has a fold button, open at a desk, named by what it does",
     hA.querySelector(".la-fold").getAttribute("aria-expanded") === "true" && hA.querySelector(".la-fold").getAttribute("aria-label") === "Fold Harborough Compound");
  ok("LAST WEEK: a heading of several rows keeps the pinned Action column (an empty .la-pin cell, so the pin stays opaque)",
     !!hA.querySelector("td.la-pin") && norm(hA.querySelector("td.la-pin").textContent) === "");
  ok("KEPT: the short row's amber wash; the Tonnes | Cost switch beside \"Open all · Fold all\"",
     under(hA)[0].getAttribute("style").includes("rgba(217, 119, 6, 0.06)") || under(hA)[0].getAttribute("style").includes("rgba(217,119,6,.06)"));
  ok("KEPT: the Show switch and the folds on one bar", !!el.querySelector(".la-xbar [data-acct-show]") && !!el.querySelector('.la-xbar [data-la-folds="account"]'));
  ok("KEPT: an unreported actual's box is still there for the one-row site", !!hB.querySelector("input"));
  // fold one, then Fold all / Open all
  click(hA.querySelector(".la-fold"));
  ok("LAST WEEK: a fold hides that site's rows only", under(heads(el)[0]).length === 0 && under(heads(el)[2]).length === 3);
  const btn = (t) => [...el.querySelectorAll('[data-la-folds="account"] button')].find(b => b.textContent === t);
  click(btn("Fold all"));
  ok("LAST WEEK: Fold all folds every site of several rows (a one-row site stays its one row)",
     el.querySelectorAll("tr.la-xln").length === 0 && heads(el).length === 3 && !!heads(el)[1].querySelector("input"));
  click(btn("Open all"));
  ok("LAST WEEK: Open all opens them again", el.querySelectorAll("tr.la-xln").length === 5);
  d.done();

  // cost columns
  w.sessionStorage.clear();
  d = view(pageOf(), "account", { initialAcctShow: "cost" }); el = d.el;
  const ncol = (tr) => [...tr.children].reduce((a, td) => a + (+td.getAttribute("colspan") || 1), 0);
  ok("⭐ LAST WEEK (Cost): the heading spans the same columns as a row with the cost columns shown",
     ncol(heads(el)[0]) === ncol(under(heads(el)[0])[0]), `${ncol(heads(el)[0])} vs ${ncol(under(heads(el)[0])[0])}`);
  d.done();
  w.sessionStorage.clear();
  d = view(pageOf(), "account"); el = d.el;
  ok("LAST WEEK (Tonnes): the heading spans the same columns as a row", ncol(heads(el)[0]) === ncol(under(heads(el)[0])[0]),
     `${ncol(heads(el)[0])} vs ${ncol(under(heads(el)[0])[0])}`);
  d.done();

  // a team login: every row one team's, so each heading names the team
  w.sessionStorage.clear();
  d = view(pageOf({ ipt: "IPT1" }), "account"); el = d.el;
  ok("LAST WEEK (a team login): each site's heading names its one team, never an id",
     heads(el).every(h => /Team 1/.test(norm(h.textContent))) && !/\bIPT ?\d\b/.test(norm(el.querySelector("table").textContent)));
  d.done();

  // ---------------------------------------------------------------- the weeks ahead
  w.sessionStorage.clear();
  d = view(pageOf(), "horizon"); el = d.el;
  H = heads(el);
  ok("⭐ WEEKS AHEAD: one ruled heading a site, in the server's order", H.map(h => h.getAttribute("data-la-site")).join("|") === "L001|L002|L003");
  ok("WEEKS AHEAD: the one-line site is one row, its line named \"From …\"", !H[1].querySelector(".la-fold") && ends(H[1]) === "From Wolds Link Batching Plant");
  const hzC = under(H[2]);
  ok("⭐ WEEKS AHEAD: under a site its lines \"From …\", the out line last \"Out, to …\"",
     hzC.map(ends).join(" | ") === "From Northfield Quarry | From Brook Pit | Out, to Wolds Link Inert Landfill", hzC.map(ends).join(" | "));
  const cells = (h) => [...h.querySelectorAll("[data-hz-site-week]")];
  ok("⭐ WEEKS AHEAD: a heading carries one total a week, in tonnes", cells(H[0]).length === WEEKS.length
     && cells(H[0]).every(c => /\bt\b/.test(norm(c.textContent))), cells(H[0]).map(c => norm(c.textContent)).join("|"));
  const k0 = cells(H[2])[0].getAttribute("data-hz-site-week");
  ok("⭐ WEEKS AHEAD: each week's heading is its lines' planned tonnes added (60 + 30 + 80 in the first week)",
     cells(H[2]).every((c, i) => tnum(c.firstChild ? c.childNodes[0].textContent : c.textContent) === (60 + i) + (30 + i) + (80 + i)),
     cells(H[2]).map(c => norm(c.textContent)).join("|"));
  ok("WEEKS AHEAD: the part going out is said under the sending site's week (\"80 t out\")",
     norm(cells(H[2])[0].querySelector(".la-sub").textContent) === "80 t out" && !cells(H[0])[0].querySelector(".la-sub"));
  ok("WEEKS AHEAD: under 40 lines the sites are open at a desk, with \"Open all · Fold all\"",
     under(H[0]).length === 2 && !!el.querySelector('[data-la-folds="horizon"]') && k0.includes("|"));
  ok("WEEKS AHEAD: the commit week's heading cell keeps the column's shade",
     cells(H[0]).some(c => (c.getAttribute("style") || "").includes("--navy-soft-col")));
  d.done();
  // past 40 lines: folded on every width
  w.sessionStorage.clear();
  d = view(pageOf({ extra: F.LA_HZ_FOLD_OVER }), "horizon"); el = d.el;
  ok("⭐ WEEKS AHEAD: past 40 lines every site starts folded, at a desk too", el.querySelectorAll("tr.la-xln").length === 0
     && heads(el)[2].querySelector(".la-fold").getAttribute("aria-expanded") === "false", String(el.querySelectorAll("tr.la-xln").length));
  click([...el.querySelectorAll('[data-la-folds="horizon"] button')].find(b => b.textContent === "Open all"));
  ok("WEEKS AHEAD: Open all opens them", el.querySelectorAll("tr.la-xln").length === 5 + F.LA_HZ_FOLD_OVER);
  d.done();

  // ---------------------------------------------------------------- the tablet
  TABLET = true; w.sessionStorage.clear();
  d = view(pageOf(), "account"); el = d.el;
  ok("TABLET: Last week's sites start folded", el.querySelectorAll("tr.la-xln").length === 0 && heads(el).length === 3);
  d.done();
  d = view(pageOf(), "horizon"); el = d.el;
  ok("TABLET: the weeks ahead's sites start folded", el.querySelectorAll("tr.la-xln").length === 0 && heads(el).length === 3);
  d.done();
  TABLET = false;

  // ---------------------------------------------------------------- an older page with no sites
  w.sessionStorage.clear();
  d = view(pageOf({ sites: false }), "account"); el = d.el;
  ok("NO SITES: Last week groups everything under \"Other lines\"", heads(el).length === 1 && norm(heads(el)[0].textContent).includes("Other lines"));
  d.done();
} catch (e) {
  fail.push("CRASH: " + (e && e.stack || e));
}

// ---------------------------------------------------------------- the source
ok("the screens take the site from the server (row.site, page.site_order): nothing works a site out a second way",
   /function laRowSites\(rows, order\)\{[\s\S]*?const s = r\.site \|\| null/.test(code) && code.includes("const siteOrder = (page && page.site_order) || null;"));
ok("folds: Last week open at a desk and folded on a tablet; the weeks ahead folded past LA_HZ_FOLD_OVER lines on every width",
   code.includes('const acctFolds = useLaFolds("lookahead-acct-sites", !laTab);')
   && code.includes('const hzFolds = useLaFolds("lookahead-hz-sites", !laTab && hzLineN <= LA_HZ_FOLD_OVER);') && code.includes("const LA_HZ_FOLD_OVER = 40;"));
ok("CSS: a site heading is a 1 px ink rule; the amber shortfall is --warn-text",
   html.includes("tr.la-xsite>td{border-top:1px solid var(--ink) !important;") && html.includes(".la-acct-short{color:var(--warn-text);"));

console.log(`ui_fix_la_site_papers.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  ✗ " + f));
process.exit(fail.length ? 1 : 0);
