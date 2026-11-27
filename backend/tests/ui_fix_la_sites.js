/*
 * ui_fix_la_sites.js — the Look-ahead rethink, task A (25 Nov 2026; card 1 of notes\lookahead-rethink-mockup-1124, John's
 * "Yes, as recommended" to Q1 to Q7, and "Cards as drawn" for the tablet): the commit week's list grouped by SITE.
 *
 * Mounts the real LookAhead and PhoneLookAhead (jsdom, the page's own code) on a made-up page: three sites in the
 * server's order (two lines; one line; three lines with one going OUT and one not routed), the sites' figures added up
 * here the way backend/la_sites.py adds them (test_la_sites.py proves the server's own sums). What it proves:
 *   - the desk: a ruled heading a site with ONE status, its figures a day and for the week, "n t out" under them; its
 *     lines under it ("From …", the out line last, "Out, to …"); a one-line site is ONE row with no fold arrow; folds,
 *     "Open all · Fold all"; the headings ADD UP to the total row in Loads, Tonnes and Lorries, column by column; the
 *     total row's "3 sites · 6 lines" and "… t of the week goes out"; "pour" in plain words;
 *   - the flags line: the rail's count, a kind of flag once with its site(s) as links (a dated one with its day), the
 *     lines short last week apart; a link opens its site; no flag = no line; every site flagged;
 *   - an unconfirmed and a confirmed week; a team login's one line "<team>'s lines only"; an unrouted line's lorries
 *     left out of its site's and the total's;
 *   - the tablet: cards (.tab-cards), sites folded to start; the phone: the day's sites, folded, "sites" as the 4th
 *     figure, "n sites flagged · n lines short last week", "1 load";
 *   - gone, at source: the rail's "+N more" / "show fewer" / railOpen, the phone's PH_FIRST / "Show N more lines", the
 *     old tablet table's status under the name.
 * What it does NOT prove: a real browser's layout (the Chrome pictures in notes\lookahead-rethink-mockup-1124\built\sites\).
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_la_sites.js: SKIPPED — jsdom not installed"); process.exit(0); }

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
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const LA = between("function LookAhead({ meta, who, access, initialPage, initialView", "\nfunction CommitMap(");
const PH = between("function PhoneLookAhead({ meta, initialPage }){", "\n}\n");

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.Element.prototype.scrollIntoView = function(){ w.__scrolled = (w.__scrolled || []).concat(this.getAttribute("data-la-site")); };
let TABLET = false;
w.matchMedia = (q) => ({ matches: TABLET && q === "(min-width: 768px) and (max-width: 1024px)", addEventListener(){}, removeEventListener(){} });
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__F = { grp, laSiteList, lineKeyOf, dayName };");
const F = w.__F;

const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
const num = (el) => { const k = el.cloneNode(true); k.querySelectorAll(".la-sub, .pour-mark, [role=img]").forEach(x => x.remove());
  const m = norm(k.textContent).replace(/,/g, "").match(/-?\d+(\.\d+)?/); return m ? +m[0] : 0; };

// ---------------------------------------------------------------- the made-up page
const BASE = FIX("lookahead_page.json");
const T0 = BASE.commit.lines[0];
const DAYS = T0.days.map(d => d.day_date);                 // Mon … Sun of the fixture's week
const WD = DAYS.slice(0, 5);
const TODAY = WD[2];
const mkLine = (route, section, ipt, from, to, perDay, opts = {}) => {
  const o = opts;
  const days = DAYS.map((iso, i) => {
    const on = i < 5;
    const t = on ? (o.byDay ? o.byDay[i] : perDay) : 0;
    const n = on ? (o.loads ? o.loads[i] : Math.round(t / 20)) : 0;
    const v = on ? (o.lorries != null ? o.lorries : Math.max(1, Math.ceil(n / 5))) : 0;
    return { day_date: iso, planned_qty: t, status: "derived", derived: { tonnes: t, trips: n, vehicles: n ? v : 0 } };
  });
  const wt = days.reduce((a, d) => a + d.derived.tonnes, 0), wn = days.reduce((a, d) => a + d.derived.trips, 0);
  return { ...T0, route_id: route, discipline: "earthworks", section_id: section, month_index: T0.month_index, ipt, unit: "t",
    site: o.site, days,
    week: { ...(T0.week || {}), status: o.status || "derived", planned_qty: wt, parent_changed: false },
    week_derived: { tonnes: wt, trips: wn, vehicles_peak: Math.max(...days.map(d => d.derived.vehicles)) },
    context: { ...(T0.context || {}), ipt, origin_name: from, dest_name: to, material_type: o.mat || "Small aggregate", section_id: section,
               baked: o.baked !== false, diversion: null, busy_hours: null } };
};
const SITE = (id, name, type, dir = "in") => ({ id, name, type, dir });
const A = SITE("L001", "Harborough Compound", "Compound"), B = SITE("L002", "Tilton Compound", "Compound");
const C = SITE("L003", "Tilton Viaduct site", "Site"), Cout = SITE("L003", "Tilton Viaduct site", "Site", "out");
const linesOf = (status) => [
  mkLine("R10", "WS1", "IPT1", "Kilby Ridge Quarry", "Harborough Compound", 170, { site: A, status }),
  mkLine("R11", "WS1", "IPT2", "Harborough Rail Freight Terminal", "Harborough Compound", 5, { site: A, status, loads: [1, 1, 1, 1, 1] }),
  mkLine("R12", "WS4", "IPT1", "Wolds Link Batching Plant", "Tilton Compound", 40, { site: B, status }),
  mkLine("R13", "WS4", "IPT1", "Northfield Quarry", "Tilton Viaduct site", 60, { site: C, status, byDay: [60, 60, 60, 60, 60] }),
  mkLine("R14", "WS4", "IPT1", "Brook Pit", "Tilton Viaduct site", 30, { site: C, status, baked: false, lorries: 3 }),
  mkLine("R15", "WS4", "IPT1", "Tilton Viaduct site", "Wolds Link Inert Landfill", 80, { site: Cout, status, mat: "Earthworks / soil" }),
];
const key = (l) => F.lineKeyOf(l);
// the server's roll-up (backend/la_sites.roll_up), worked here the same way
const rollUp = (lines) => {
  const out = [];
  lines.forEach(l => {
    let g = out.find(x => x.id === l.site.id);
    if (!g) { g = { id: l.site.id, name: l.site.name, type: l.site.type, lines: [], out_lines: 0, ipts: new Set(), days: {},
                    week: { t: 0, loads: 0, lorries: 0 }, out_week: { t: 0, loads: 0, lorries: 0 } }; out.push(g); }
    const isOut = l.site.dir === "out";
    g.lines.push(key(l)); g.out_lines += isOut ? 1 : 0; g.ipts.add(l.context.ipt);
    l.days.forEach(d => { const x = g.days[d.day_date] || (g.days[d.day_date] = { t: 0, loads: 0, lorries: 0, out_t: 0, out_loads: 0, out_lorries: 0 });
      const v = l.context.baked ? d.derived.vehicles : 0;
      x.t += d.derived.tonnes; x.loads += d.derived.trips; x.lorries += v;
      if (isOut) { x.out_t += d.derived.tonnes; x.out_loads += d.derived.trips; x.out_lorries += v; } });
    g.week.t += l.week_derived.tonnes; g.week.loads += l.week_derived.trips;
    if (isOut) { g.out_week.t += l.week_derived.tonnes; g.out_week.loads += l.week_derived.trips; }
  });
  out.forEach(g => { g.week.lorries = Math.max(0, ...Object.values(g.days).map(d => d.lorries)); g.out_week.lorries = Math.max(0, ...Object.values(g.days).map(d => d.out_lorries));
    g.ipt = g.ipts.size === 1 ? [...g.ipts][0] : null; delete g.ipts; });
  return out;
};
const flag = (l, code, text, day) => ({ code, route_id: l.route_id, discipline: l.discipline, section_id: l.section_id, month_index: l.month_index,
  ipt: l.ipt, text, ...(day ? { day_date: day } : {}) });
const pageOf = ({ status = "derived", flags, teamOnly = null, pours = [] } = {}) => {
  const lines = linesOf(status);
  const fl = flags ? flags(lines) : [
    flag(lines[0], "DAYS_NE_WEEK", "The days do not add up to the week"),
    flag(lines[0], "SHORTAGE", "Short 100 t last week"),
    flag(lines[3], "POUR_BAND", "Mixers in a no-delivery time", WD[3]),
    flag(lines[4], "UNBAKED", "Not routed yet"),
  ];
  const planned = lines.reduce((a, l) => a + l.week_derived.tonnes, 0), trips = lines.reduce((a, l) => a + l.week_derived.trips, 0);
  return { ...BASE, today: TODAY, pours,
    commit: { ...BASE.commit, lines, sites: rollUp(lines), team_only: teamOnly, totals: { ...BASE.commit.totals, planned_t: planned, trips } },
    // last week's row for R10, 100 t short and not carried yet (the site's "Short 100 t last week" line)
    account: { ...(BASE.account || {}), rows: [{ ...((BASE.account || {}).rows || [{}])[0], route_id: "R10", discipline: "earthworks", section_id: "WS1",
               ipt: "IPT1", unit: "t", planned_qty: 1000, actual_qty: 900, remaining_short: 100, remaining_short_t: 100, carried: 0 }] },
    clashes: { ...BASE.clashes, flags: fl, count: fl.length } };
};
const META = { routes: [], materials: ["Small aggregate"], vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: { "Small aggregate": 1.6 }, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } },
  mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] }, disciplines: [], sections: [],
  work_sections: [{ section_id: "WS1", name: "Harborough approach" }, { section_id: "WS4", name: "Tilton viaduct" }] };
const desk = (page) => mount(w.LookAhead, { meta: META, who: "t", initialPage: page, initialView: "commit" });
const pressUnit = (el, which) => { const b = [...el.querySelectorAll("[data-unit-switch] button")].find(x => x.textContent === which); if (b) click(b); return !!b; };

try {
  // ---------------------------------------------------------------- the desk
  w.sessionStorage.clear();
  const P = pageOf();
  const d = desk(P);
  const el = d.el;
  const heads = () => [...el.querySelectorAll("tr[data-la-site]")];
  ok("⭐ DESK: one ruled heading a site, in the server's order (Data → Locations)", heads().map(h => h.getAttribute("data-la-site")).join("|") === "L001|L002|L003",
     heads().map(h => h.getAttribute("data-la-site")).join("|"));
  const hA = heads()[0], hB = heads()[1], hC = heads()[2];
  ok("DESK: a heading names the site (Sora, .la-sn), then its type · n lines · team (a team only when one team's)",
     norm(hA.querySelector(".la-sn").textContent) === "Harborough Compound" && norm(hA.querySelector(".la-sm").textContent) === "Compound · 2 lines"
     && norm(hC.querySelector(".la-sm").textContent) === "Site · 3 lines · Team 1", norm(hC.querySelector(".la-sm").textContent));
  ok("⭐ DESK: a site with ONE line is ONE row with no fold arrow: the site's heading, then where its line comes from",
     hB.classList.contains("la-one") && !hB.querySelector(".la-fold") && !!hB.getAttribute("data-la-line")
     && norm(hB.textContent).includes("Tilton Compound") && norm(hB.textContent).includes("From Wolds Link Batching Plant · Small aggregate · WS4 · Tilton viaduct"));
  ok("DESK: a site with lines has a fold button (open at a desk), named by what it does and the site",
     hA.querySelector(".la-fold").getAttribute("aria-expanded") === "true" && hA.querySelector(".la-fold").getAttribute("aria-label") === "Fold Harborough Compound");
  const linesUnder = (h) => { const out = []; let x = h.nextElementSibling; while (x && !x.hasAttribute("data-la-site") && !x.classList.contains("la-total")) { if (x.classList.contains("la-ln")) out.push(x); x = x.nextElementSibling; } return out; };
  const cLines = linesUnder(hC);
  ok("⭐ DESK: a line under its site reads where it comes from, then material · work section; the OUT line goes last, \"Out, to …\"",
     cLines.length === 3 && norm(cLines[0].querySelector(".la-lf").textContent) === "From Northfield Quarry"
     && norm(cLines[0].querySelector(".la-lm").textContent) === "Small aggregate · WS4 · Tilton viaduct"
     && norm(cLines[2].querySelector(".la-lf").textContent) === "Out, to Wolds Link Inert Landfill" && cLines[2].classList.contains("la-out"),
     cLines.map(x => norm(x.querySelector(".la-lf").textContent)).join(" | "));
  ok("DESK: under a site of two teams, each line names its team (never an id)",
     linesUnder(hA).map(x => norm(x.querySelector(".la-lm").textContent)).join(" | ") === "Small aggregate · WS1 · Harborough approach · Team 1 | Small aggregate · WS1 · Harborough approach · Team 2"
     && !/\bIPT ?\d\b/.test(el.textContent) && !/\bL00\d\b/.test(norm(el.querySelector('[data-rd-table="lookahead"]').textContent)));
  ok("⭐ DESK: ONE status a heading: the site's worst flag (laStatus over its lines' flags); a shortage never takes it, it is the second line",
     norm(hA.querySelector("td.rd-status .row-st").textContent).startsWith("Days ≠ week") && norm(hA.querySelector("td.rd-status").textContent).includes("Short 100 t last week")
     && norm(hC.querySelector("td.rd-status .row-st").textContent).startsWith("Not routed"), norm(hC.querySelector("td.rd-status").textContent));
  ok("DESK: \"n t out\" under a site's figures when it sends some out (a day and the week)",
     [...hC.querySelectorAll("td.la-site-n .la-sub")].map(x => norm(x.textContent)).join("|") === "80 t out|80 t out|80 t out|80 t out|80 t out|400 t out");
  // the headings add up to the total row, in every unit
  const total = () => el.querySelector("tr.la-total");
  const sumCheck = (unit) => {
    pressUnit(el, unit);
    const tot = [...total().querySelectorAll("td.num")].map(num);
    const cols = tot.map((_, i) => heads().reduce((a, h) => a + num([...h.querySelectorAll("td.num")][i]), 0));
    return { tot, cols, same: tot.length === WD.length + 1 && tot.every((x, i) => Math.abs(x - cols[i]) < 0.6) };
  };
  for (const u of ["Loads", "Tonnes", "Lorries"]) {
    const r = sumCheck(u);
    ok(`⭐ DESK SUMS (${u}): the site headings add up to the total row, column by column (each day and the week)`, r.same, `${r.cols.join(",")} vs ${r.tot.join(",")}`);
  }
  pressUnit(el, "Lorries");
  ok("DESK (Lorries): an unrouted line's lorries are not in its site's or the total's (its own cell reads —)",
     num([...hC.querySelectorAll("td.num")][0]) === 1 + 1 && norm([...cLines[1].querySelectorAll("td.num")][0].textContent) === "—");
  pressUnit(el, "Tonnes");
  ok("⭐ DESK: the total row reads \"3 sites · 6 lines\" and what of the week goes out",
     norm(total().querySelector("td").textContent).startsWith("3 sites · 6 lines") && norm(total().textContent).includes("400 t of the week goes out"), norm(total().querySelector("td").textContent));
  ok("DESK: the first column is the Site", [...el.querySelectorAll('[data-rd-table="lookahead"] thead th')][0].textContent === "Site");
  // folding
  const folds = el.querySelector("[data-la-folds]");
  ok("DESK: \"Open all · Fold all\" beside the unit switch", !!folds && norm(folds.textContent).replace(/\s*·\s*/, " · ") === "Open all · Fold all");
  click(hC.querySelector(".la-fold"));
  ok("DESK: a fold button folds its site's lines away (the heading stays, its figures too)",
     linesUnder(heads()[2]).length === 0 && heads()[2].querySelector(".la-fold").getAttribute("aria-expanded") === "false" && heads().length === 3);
  click([...folds.querySelectorAll("button")].find(b => b.textContent === "Open all"));
  ok("DESK: Open all opens every site", linesUnder(heads()[0]).length === 2 && linesUnder(heads()[2]).length === 3);
  click([...el.querySelector("[data-la-folds]").querySelectorAll("button")].find(b => b.textContent === "Fold all"));
  ok("DESK: Fold all folds every site; a one-line site is still its one row", linesUnder(heads()[0]).length === 0 && linesUnder(heads()[2]).length === 0 && !!el.querySelector("tr.la-one"));
  // the flags line
  const fl = el.querySelector("[data-la-flagline]");
  ok("⭐ FLAGS LINE: the rail's own count, then each KIND of flag once with its site(s) as links",
     !!fl && fl.getAttribute("data-la-flagline") === "4" && norm(fl.querySelector("b").textContent) === "4 flags"
     && [...fl.querySelectorAll("[data-la-flag]")].map(x => x.getAttribute("data-la-flag")).join("|") === [...fl.querySelectorAll("[data-la-flag]")].map(x => x.getAttribute("data-la-flag")).filter((x, i, a) => a.indexOf(x) === i).join("|"),
     norm(fl && fl.textContent));
  const kindTxt = (code) => norm(String((fl.querySelector(`[data-la-flag="${code}"]`) || {}).textContent || "").replace(/·/g, " · "));
  ok("FLAGS LINE: a dated flag says its day; an undated one does not",
     kindTxt("POUR_BAND").startsWith("Mixers in a no-delivery time, " + F.dayName(WD[3])) && kindTxt("POUR_BAND").includes("Tilton Viaduct site")
     && kindTxt("DAYS_NE_WEEK") === "Days ≠ week · Harborough Compound", kindTxt("POUR_BAND") + " || " + kindTxt("DAYS_NE_WEEK"));
  ok("⭐ FLAGS LINE: the lines short last week come last and apart (\"Short last week · 1 line\"), never as a site's status",
     kindTxt("SHORTAGE") === "Short last week · 1 line" && [...fl.querySelectorAll("[data-la-flag]")].pop().getAttribute("data-la-flag") === "SHORTAGE", kindTxt("SHORTAGE"));
  w.__scrolled = [];
  click([...fl.querySelectorAll("button.la-fl-site")].find(b => b.textContent === "Tilton Viaduct site"));
  await_(() => {});
  ok("FLAGS LINE: a site's link opens that site (folded before) and goes to it", linesUnder(heads()[2]).length === 3);
  d.done();

  // ---------------------------------------------------------------- states
  w.sessionStorage.clear();
  const none = desk(pageOf({ flags: () => [] }));
  ok("STATE no flag: no flags line at all, every heading the week's own state", !none.el.querySelector("[data-la-flagline]")
     && [...none.el.querySelectorAll("tr[data-la-site] td.rd-status .row-st")].every(s => /Derived/.test(s.textContent)));
  none.done();
  const all = desk(pageOf({ flags: (ls) => [flag(ls[0], "LIMIT", "Road limit"), flag(ls[2], "ROUTE_CAP", "Over the cap", WD[1]), flag(ls[5], "PARENT_CHANGED", "Month changed")] }));
  ok("STATE every site flagged: each heading carries its flag's word, the shape red or amber",
     [...all.el.querySelectorAll("tr[data-la-site]")].map(h => norm(h.querySelector(".row-st").textContent)).join("|") === "Road limit|Route cap|Month changed",   // NARROWED 25 Nov 2026 (the Look-ahead rethink, B1, Q18): the flag word "Cap" is spelt out, "Route cap"
     [...all.el.querySelectorAll("tr[data-la-site]")].map(h => norm(h.querySelector(".row-st").textContent)).join("|"));
  ok("STATE every site flagged: the flags line names all three sites", norm(all.el.querySelector("[data-la-flagline]").textContent).includes("Harborough Compound")
     && norm(all.el.querySelector("[data-la-flagline]").textContent).includes("Tilton Compound") && norm(all.el.querySelector("[data-la-flagline]").textContent).includes("Tilton Viaduct site"));
  all.done();
  const conf = desk(pageOf({ status: "confirmed", flags: () => [] }));
  ok("STATE confirmed week: every heading reads Confirmed; the day cells are figures, not buttons to type",
     [...conf.el.querySelectorAll("tr[data-la-site] td.rd-status .row-st")].every(s => /Confirmed/.test(s.textContent)) && !conf.el.querySelector(".la-cell"));
  conf.done();
  const unconf = desk(pageOf({ status: "derived", flags: () => [] }));
  ok("STATE unconfirmed week: a day is still typed in Tonnes (a figure that becomes a box)", !!unconf.el.querySelector("tr.la-ln .la-cell, tr.la-one .la-cell"));
  unconf.done();
  const team = desk(pageOf({ teamOnly: "North Team" }));
  ok("⭐ STATE team login: said once, \"North Team's lines only\", on the total row",
     (norm(team.el.textContent).match(/North Team's lines only/g) || []).length === 1 && !!team.el.querySelector("tr.la-total [data-la-team-only]"));
  team.done();
  const pour = desk(pageOf({ flags: () => [], pours: [{ route_id: "R13", discipline: "earthworks", section_id: "WS4", month_index: T0.month_index, pour_date: WD[3], m3: 25, start: "07:00", place: "Pier 2" }] }));
  const pm = pour.el.querySelector("[data-pour-mark]");
  ok("DESK: a pour's day reads \"pour\" in plain words (no capitals, no box)", !!pm && pm.textContent === "pour" && pm.classList.contains("la-pour"), pm && pm.outerHTML.slice(0, 120));
  pour.done();

  // ---------------------------------------------------------------- the tablet: cards
  w.sessionStorage.clear(); TABLET = true;
  const tab = desk(pageOf());
  const tbl = tab.el.querySelector('[data-rd-table="lookahead"]');
  ok("⭐ TABLET: the list is cards (.tab-cards .la-cards; John, 25 Nov: \"Cards as drawn\")", tbl.classList.contains("tab-cards") && tbl.classList.contains("la-cards")
     && tbl.style.getPropertyValue("--tc-n") === String(WD.length + 1));
  ok("TABLET: the sites are folded to start (a heading's fold reads Open), no line card drawn; a one-line site is its one card",
     [...tab.el.querySelectorAll("tr[data-la-site] .la-fold")].every(b => b.getAttribute("aria-expanded") === "false") && !tab.el.querySelector("tr.la-ln") && !!tab.el.querySelector("tr.la-one"));
  click(tab.el.querySelector("tr[data-la-site] .la-fold"));
  ok("TABLET: a site opened shows its lines as cards, each with its status cell and its days", tab.el.querySelectorAll("tr.la-ln").length === 2
     && [...tab.el.querySelectorAll("tr.la-ln")].every(r => !!r.querySelector("td.rd-status") && r.querySelectorAll("td.num").length === WD.length + 1));
  tab.done(); TABLET = false;

  // ---------------------------------------------------------------- the phone
  w.sessionStorage.clear();
  const ph = mount(w.PhoneLookAhead, { meta: META, initialPage: pageOf() });
  const pel = ph.el;
  const figs = [...pel.querySelectorAll(".ph-figs > span")].map(s => norm(s.textContent));
  ok("⭐ PHONE: the day's figures, the fourth the day's SITES", figs.length === 4 && figs[3] === "3sites"
     && norm(pel.querySelector('[data-ph-fig="sites"] b').textContent) === "3", figs.join("|"));
  const pss = [...pel.querySelectorAll("[data-ph-site]")];
  ok("⭐ PHONE: the day is its sites in the server's order, each folded to start (no line drawn)",
     pss.map(x => x.getAttribute("data-ph-site")).join("|") === "L001|L002|L003" && !pel.querySelector(".ph-line")
     && pss.every(x => x.querySelector(".ph-site-b").getAttribute("aria-expanded") === "false"));
  ok("PHONE: a site row: its name and the day's tonnes; its status; loads · lines · \"t out\"",
     norm(pss[2].querySelector(".ph-sn").textContent) === "Tilton Viaduct site" && norm(pss[2].querySelector(".ph-sf").textContent) === "170 t"
     && norm(pss[2].querySelector(".ph-sm").textContent) === "9 loads · 3 lines · 80 t out", norm(pss[2].querySelector(".ph-sm").textContent));
  ok("PHONE: \"1 load\", never \"1 loads\"", !/\b1 loads\b/.test(pel.textContent));
  // NARROWED 26 Nov 2026 (John, "As recommended" to the Look-ahead batch page, Q3): ONE line as card c1 drew it: the week's state, then the SITES flagged; no short-lines count
  ok("⭐ PHONE: the note is the week's state, then the SITES flagged that day (no lines-short count)",
     /^(\d+ of \d+ lines confirmed|Derived from the month · not confirmed yet|The week is confirmed) · 2 sites flagged · 1 not routed yet$/.test(norm(pel.querySelector("[data-ph-note]").textContent)),
     norm(pel.querySelector("[data-ph-note]").textContent));
  ok("🔴 PHONE: one note line only: no chained-lorries line, nothing 'short last week' (Q3, 26 Nov)",
     pel.querySelectorAll(".ph-card > .ph-note").length === 1 && !pel.querySelector("[data-ph-lorry-plan]") && !/short last week/.test(pel.textContent));
  click(pss[0].querySelector(".ph-site-b"));
  ok("PHONE: a tapped site shows its lines (\"From …\", material · section), each opening its details",
     pel.querySelectorAll(".ph-line").length === 2 && norm(pel.querySelector(".ph-line .ph-l > span").textContent) === "From Kilby Ridge Quarry"
     && !!pel.querySelector(".ph-line dl.rd-dl"));
  ok("PHONE: one load on a line reads \"1 load\"", [...pel.querySelectorAll(".ph-line .ph-r small")].some(s => s.textContent === "1 load"));
  ph.done();
  const ph2 = mount(w.PhoneLookAhead, { meta: META, initialPage: pageOf({ flags: () => [], teamOnly: "North Team" }) });
  ok("PHONE: a team's page says \"North Team's lines only\" in the note", norm(ph2.el.querySelector("[data-ph-note]").textContent).startsWith("North Team's lines only"));
  ph2.done();
  const ph3 = mount(w.PhoneLookAhead, { meta: META, initialPage: pageOf({ flags: () => [], status: "confirmed" }) });
  ok("PHONE: with no flag and nothing short, the note is the week's state", norm(ph3.el.querySelector("[data-ph-note]").textContent).startsWith("The week is confirmed")
     || norm(ph3.el.querySelector("[data-ph-note]").textContent).includes("not routed yet"), norm(ph3.el.querySelector("[data-ph-note]").textContent));
  ph3.done();

  // ---------------------------------------------------------------- 26 Nov 2026: card c1's figures (the batch's second look)
  // R10's days add to 840 (170 × 4 + 160) against a week of 850: the line says "days add to 840" under its week, so the site's
  // 865 t (its lines' days) reads right against 850 + 25; every line figure is whole tonnes, as the card draws them.
  w.sessionStorage.clear();
  const PD = pageOf();
  { const r10 = PD.commit.lines[0];
    r10.days[4] = { ...r10.days[4], planned_qty: 160, derived: { ...r10.days[4].derived, tonnes: 160 } };
    r10.week = { ...r10.week, planned_qty: 850 }; r10.week_derived = { ...r10.week_derived, tonnes: 840 };
    r10.days_sum = 840; r10.days_ne_week = true;
    PD.commit.sites = rollUp(PD.commit.lines); }
  const dd = desk(PD);
  const dA = dd.el.querySelector('tr[data-la-site="L001"]');
  const dLines = []; { let x = dA.nextElementSibling; while (x && !x.hasAttribute("data-la-site") && !x.classList.contains("la-total")) { if (x.classList.contains("la-ln")) dLines.push(x); x = x.nextElementSibling; } }
  const wkCell = (tr) => [...tr.querySelectorAll("td.num")].pop();
  ok("⭐ CARD c1: a line whose days do not add to its week says so under the week figure (\"850 t\", then \"days add to 840\")",
     dLines.length === 2 && norm(wkCell(dLines[0]).textContent).startsWith("850 t") && !!wkCell(dLines[0]).querySelector("[data-la-daysum]")
     && norm(wkCell(dLines[0]).querySelector("[data-la-daysum]").textContent) === "days add to 840", dLines[0] && norm(wkCell(dLines[0]).textContent));
  ok("CARD c1: ...only where they differ (R11's week has no such line), and the site's week is the days' 865 t",
     !wkCell(dLines[1]).querySelector("[data-la-daysum]") && norm([...dA.querySelectorAll("td.la-site-n")].pop().textContent) === "865 t"
     && dd.el.querySelectorAll("[data-la-daysum]").length === 1, norm([...dA.querySelectorAll("td.la-site-n")].pop().textContent));
  // the figure cells only: a line's details (the "By day" table, the "Days and week disagree" sentence) keep one decimal
  ok("⭐ CARD c1: a line's figures are WHOLE tonnes (170 … 160, 850 t; 5 … 25 t), never \"170.0\"",
     [...dLines[0].querySelectorAll("td.num")].map(x => norm(x.childNodes[0] && x.textContent).replace(/days add to.*/, "").replace(/✎/g, "").trim()).join("|") === "170|170|170|170|160|850 t"
     && [...dLines[1].querySelectorAll("td.num")].map(x => norm(x.textContent)).join("|") === "5|5|5|5|5|25 t"
     && !/\d\.0\b/.test([...dd.el.querySelectorAll('[data-rd-table="lookahead"] tbody td.num')].map(x => norm(x.textContent)).join(" | ").replace(/days add to [\d,.]+/g, "")),
     [...dLines[0].querySelectorAll("td.num")].map(x => norm(x.textContent)).join("|") );
  pressUnit(dd.el, "Loads");
  ok("CARD c1: under Loads the line's figures stay whole and the \"days add to\" line goes (it speaks of tonnes)",
     !dd.el.querySelector("[data-la-daysum]") && !/\d\.\d\b/.test([...dd.el.querySelectorAll('[data-rd-table="lookahead"] tbody td.num')].map(x => norm(x.textContent)).join(" | ")));
  pressUnit(dd.el, "Lorries");
  ok("CARD c1: under Lorries too", !dd.el.querySelector("[data-la-daysum]") && !/\d\.\d\b/.test([...dd.el.querySelectorAll('[data-rd-table="lookahead"] tbody td.num')].map(x => norm(x.textContent)).join(" | ")));
  dd.done();

  // ---------------------------------------------------------------- one list for desk and phone
  const L2 = linesOf("derived");
  const S0 = F.laSiteList({ sites: rollUp(L2) }, L2);
  ok("laSiteList: the server's sites with their lines, the in lines first and the out lines last", S0.map(s => s.sl.map(l => l.route_id).join(",")).join("|") === "R10,R11|R12|R13,R14,R15");
  const S1 = F.laSiteList({}, L2.slice(0, 2));
  ok("laSiteList: an older page with no sites gives one site a line (named by where it delivers)", S1.length === 2 && S1[0].name === "Harborough Compound" && S1[0].sl.length === 1);
  ok("laSiteList: a site with no place is named \"Other lines\", never blank", F.laSiteList({ sites: [{ id: null, name: "", lines: [key(L2[0])] }] }, L2)[0].name === "Other lines");
} catch (e) {
  ok("the harness ran to the end", false, String(e && e.stack || e).slice(0, 800));
}
function await_(f){ f(); }

// ---------------------------------------------------------------- source: gone, and the rules kept
ok("🔴 GONE: the rail's \"+N more\" / \"show fewer\" / railOpen and its three-flag slice, in the Look-ahead",
   LA.length > 5000 && !LA.includes("rail.flags.slice(0, 3)") && !LA.includes("more`") && !LA.includes("show fewer") && !LA.includes("railOpen")
   && !LA.includes("flags this week</span>"));
ok("🔴 GONE: the phone's PH_FIRST and \"Show N more lines\" / \"Show fewer lines\"", !code.includes("const PH_FIRST") && !PH.includes("PH_FIRST")
   && !code.includes("Show fewer lines") && !PH.includes("more line"));
ok("🔴 GONE: the tablet table's status under the route's name (REVERSED 10 Nov card 6 at John's word)", !code.includes("la-st-under") && !html.includes('[data-la-tab="1"]'));
ok("🔴 GONE: the grid's and the phone's capital POUR", !code.includes(">POUR</span>") && code.includes('<span className="pour-mark la-pour">pour</span>'));
ok("KEPT: one Confirm for the whole week; laStatus / LA_FLAG_RANK / LINE_FLAG_LABEL the only source of a status word; phFlagsByLine",
   /function laSiteStatus\(siteLines, flagsByLine\)\{[\s\S]*?return laStatus\(fl, wk \|\| \{\}\);/.test(code) && code.includes("const phFlagsByLine = (flags, day) => {")
   && PH.includes("const flagsByLine = useMemo(() => phFlagsByLine(rail.flags, shown), [rail, shown]);") && /function laStatus\(flags, w\)\{/.test(code));
ok("KEPT: a site's status never takes a shortage (laStatus drops SHORTAGE) and its carry line is the lines' own tonnes",
   /function laSiteCarry\(siteLines, carryBy, flagsByLine\)\{[\s\S]*?f\.code === "SHORTAGE"/.test(code));
ok("the sites are remembered per look: a desk, a tablet and a phone each their own (useRowOpen)",
   LA.includes('useRowOpen("lookahead-sites")') && LA.includes('useRowOpen("lookahead-sites-tablet")') && PH.includes('useRowOpen("lookahead-sites-phone")')
   && /function useRowOpen\(table\)\{[\s\S]*?const setMany = [\s\S]*?return \[\(k\) => !!open\[k\], toggle, setMany\];/.test(code));
ok("CSS: the site heading is a 1 px ink rule, the name Sora 600 15 px; the tablet cards' site heading is ruled, not boxed",
   /\.tbl tr\.la-site>td\{[^}]*border-top:1px solid var\(--ink\)/.test(html) && /\.la-sn\{[^}]*font:600 15px/.test(html)
   && /\.la-cards>tbody>tr\.la-site\{border:0 !important;border-top:1px solid var\(--ink\) !important;/.test(html));
ok("CSS: a status chip in any tablet card keeps its shape (inline-flex), found by this task", html.includes(".tab-cards>tbody>tr>td>span.row-st{display:inline-flex;}"));
ok("CSS: the total row's second line wraps (its one long line held the Site column at 339 px; 280 px again, as before the sites)",
   html.includes(".tbl tr.la-total td.la-stick .la-sub{white-space:normal;}"));

console.log(`ui_fix_la_sites.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  ✗ " + f));
process.exit(fail.length ? 1 : 0);
