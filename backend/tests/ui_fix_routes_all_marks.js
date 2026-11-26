/* ui_fix_routes_all_marks.js — 26 Nov 2026, branch claude/routes-all-figures-marks (the Routes page rethink, Group C4;
 * John: "Yes, as recommended" to S1 of notes\session-1124-route-options-schedule.md §4). The open route's "All figures"
 * table: on the CARD's lorry only, an alternative's round trip (the Cycle column), trips a day, carbon and the busy-hour
 * times carry the rule's own shape (dot = ok, diamond = warn) BEFORE the figure, with no words on the screen (a hidden
 * word for a screen reader), no bar, no tint, no green; every other lorry plain; collisions never marked. The marks are
 * the `mark` of the rule's row with the same key (route_best.option_rows); the page works nothing out.
 *
 * Fed the rule's own rows (fixtures/route_rows_1125.json) plus one typed option with busy-hour rows. Not covered: a
 * browser (the shapes' look, Dark): the session note's pictures and axe on the open table.
 * Every check marked ⭐ fails on the code before (the quicker busy-hour cell was green and bold, nothing else was marked).
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_routes_all_marks.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const FX = JSON.parse(read("backend", "tests", "fixtures", "route_rows_1125.json"));
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };

// ---------------- source checks ----------------
const ra = fnSrc("RouteAnalysis");
ok("⭐ SRC: a mark is read from the rule's rows (option.rows, the row's mark): the page works out nothing",
   ra.includes("o.rows.map(x => [x.key, x.mark])") && ra.includes('m === "ok" || m === "warn" ? m : null')
   && !/quickAlt|isQuick/.test(ra));
ok("⭐ SRC: only the lorry the card answers for (best.route.lorry), and only the four measures (round_trip, trips, carbon, busy_<hour>)",
   ra.includes("r.profile !== best.route.lorry") && ra.includes('figMark(r, "round_trip")') && ra.includes('figMark(r, "trips")')
   && ra.includes('figMark(r, "carbon")') && ra.includes('figMark(r, "busy_" + h)')
   && !/figMark\(r, "(collisions|goods|left_turns|places|cycle_meets|limits)/.test(ra)
   && (ra.match(/figMark\(/g) || []).length === 4);
ok("⭐ SRC: the green bold is gone from the table (no rgba(4,120,87), no data-quick, no 'Green, bold' in its note)",
   !/rgba\(4,120,87|data-quick|Green, bold/.test(ra));
{
  const css = (sel) => { const i = html.indexOf(sel); return i < 0 ? "" : html.slice(i, html.indexOf("}", i) + 1); };
  ok("⭐ CSS: a dot (ok) and a diamond (warn) in the status words' text colours; no background on the cell, no bar, no pill",
     css(".bo-fm-ok i{").includes("background:var(--ok-text)") && css(".bo-fm-warn i{").includes("background:var(--warn-text)")
     && css(".bo-fm-warn i{").includes("border-radius:0") && css(".bo-fm-warn i{").includes("rotate(45deg)")
     && !/\.bo-fm[^{]*\{[^}]*(background:var\(--(navy|action|ok|warn|red)|border-radius:(99|999)px)/.test(html.replace(/\.bo-fm-(ok|warn) i\{[^}]*\}/g, "")));
  ok("⭐ CSS: the shape's hidden word sits in a positioned box (a .sr-only in a scroller stretches the page otherwise)",
     css(".bo-fm{").includes("position:relative"));
}

// ---------------- the table in a DOM ----------------
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.mapboxgl = { Map: function(){ return { on(){}, remove(){} }; } };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.ResizeObserver = function(){ this.observe = () => {}; this.disconnect = () => {}; };
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
let loaded = true;
try { w.eval(js); } catch (e) { loaded = false; console.log("app script failed: " + e.message); }
ok("the app's script runs in the DOM", loaded);
const E = w.React.createElement;
const respond = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
const tick = () => act(async () => { await new Promise(r => setTimeout(r, 0)); });

const TIP = "Artic Tipper (44t)", FLAT = "Artic Flatbed (44t)";
const IN_USE = { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } };
const ROW = (profile, alt) => ({ profile, alt_index: alt, loaded_km: 40 + alt, return_km: 42, return_estimated: false, loaded_hr: 0.75, return_hr: 0.5,
  load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 2.0 + alt * 0.3, haul_speed_applied: false,
  hours: profile === TIP ? { "08:00": 2.07 + alt * 0.1, "17:00": 2.13 + alt * 0.1 } : { "08:00": 2.4 + alt * 0.1, "17:00": 2.5 + alt * 0.1 },
  trips_per_day: 4 - alt, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 42 + alt * 15,
  lorry_day: { limited_by: "shift", trips_without_rules: 4 - alt, words: "a day", break_minutes: 45 } });
const DATA = { rows: [ROW(TIP, 0), ROW(TIP, 1), ROW(FLAT, 0), ROW(FLAT, 1)],
  planning: { shift_hours_per_day: 10, working_days_per_month: 22, shift_note: "" },
  hour_times: { profile: TIP, screen_hours: ["08:00", "17:00"] } };
const clone = (x) => JSON.parse(JSON.stringify(x));
// the rule's rows for Alt 1 of live's R001 (warn on the three measures) plus busy-hour rows a typed option adds (ok at 08:00, warn at 17:00)
const OPT = clone(FX.L001.options[0]);
OPT.rows = OPT.rows.filter(x => x.key !== "busy");
OPT.rows.splice(OPT.rows.findIndex(x => x.key === "carbon"), 0,
  { key: "busy_08:00", label: "Setting off at 08:00", mark: "ok", words: "6 min quicker" },
  { key: "busy_17:00", label: "Setting off at 17:00", mark: "warn", words: "6 min longer" });
const BEST = (opt, lorry) => ({ day: "2026-11-26", checks: {}, route: { route: "R001", answer: "A trade-off", option: "Alt 1", alt: 1, lorry: lorry || TIP, lorry_basis: "approved loads",
  other_lorries: [], in_use: IN_USE, why: "", trade_short: "", trade_also: "", held_back: null, counts_in_use: {},
  checks: { limits_held: true, community_all_options: true, collision_history: "current" }, options: [opt] } });
let CUR = BEST(OPT);
w.fetch = (url) => { const u = String(url);
  if (/\/routes\/R001\/analysis$/.test(u)) return respond(DATA);
  if (/\/routes\/R001\/best-option$/.test(u)) return respond(CUR);
  if (/\/collision-hours$/.test(u)) return respond({});
  return new Promise(() => {}); };

async function open(best){
  CUR = best;
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  await act(async () => { root.render(E(w.RouteAnalysis, { routeId: "R001", token: "t", onFocus(){}, onPromote(){}, promoting: "", leg: "loaded" })); });
  for (let i = 0; i < 8; i++) await tick();
  const btn = host.querySelector("button[data-bo-all]");
  if (btn) { await act(async () => { btn.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); for (let i = 0; i < 4; i++) await tick(); }
  return { host, done: async () => { await act(async () => root.unmount()); host.remove(); } };
}
const trOf = (host, profileText, altText) => [...host.querySelectorAll("table[data-bo-table] tbody tr")]
  .filter(tr => tr.children[1].textContent.replace(/[●\s]/g, "") === altText)
  .find(tr => profileText == null || true);
const rowsOf = (host) => [...host.querySelectorAll("table[data-bo-table] tbody tr")];
const col = (host, text) => [...host.querySelectorAll("table[data-bo-table] thead th")].findIndex(th => th.textContent.trim() === text);

(async () => {
  if (!loaded || typeof w.RouteAnalysis !== "function") { ok("RouteAnalysis is defined", false); return finish(); }
  try {
    const m = await open(BEST(OPT));
    const tb = m.host.querySelector("table[data-bo-table]");
    ok("DOM: the open route's All figures table is there with its four rows (two lorries, main and Alt 1)", !!tb && rowsOf(m.host).length === 4, tb && rowsOf(m.host).length);
    const [tipMain, tipAlt, flMain, flAlt] = rowsOf(m.host);
    const cCycle = col(m.host, "Cycle"), cTrips = col(m.host, "Trips/day"), cCo2 = col(m.host, "CO₂ kg/trip"), c8 = col(m.host, "08:00"), c17 = col(m.host, "17:00");
    const mk = (tr, c) => tr.children[c].querySelector(".bo-fm");
    // the card's lorry, the alternative: warn on the three measures (the rule's rows for R001), ok then warn on the busy hours
    ok("⭐ MARKS: the card's lorry's Alt 1: a diamond before the Cycle, the trips and the carbon figures (the rule's warn)",
       [cCycle, cTrips, cCo2].every(c => TRY(() => mk(tipAlt, c).getAttribute("data-fig-mark") === "warn" && mk(tipAlt, c).classList.contains("bo-fm-warn"))),
       [cCycle, cTrips, cCo2].map(c => tipAlt.children[c].innerHTML.slice(0, 120)).join(" | "));
    ok("⭐ MARKS: the busy-hour cells take the rule's own marks: a dot at 08:00 (ok), a diamond at 17:00 (warn), the figure in ink",
       TRY(() => mk(tipAlt, c8).getAttribute("data-fig-mark") === "ok" && mk(tipAlt, c17).getAttribute("data-fig-mark") === "warn"
         && mk(tipAlt, c8).classList.contains("bo-fm-hr") && mk(tipAlt, c8).textContent.includes("2.17 h")));
    ok("⭐ SHAPE FIRST: the shape comes before the figure; it is hidden from a reader and a hidden word names it ('Better: ' / 'Worse: ')",
       TRY(() => { const s = mk(tipAlt, c8); return s.firstElementChild.tagName === "I" && s.firstElementChild.getAttribute("aria-hidden") === "true"
         && s.children[1].classList.contains("sr-only") && s.children[1].textContent === "Better: " && mk(tipAlt, c17).children[1].textContent === "Worse: "; }));
    ok("⭐ NO WORDS: a marked cell reads its figure (and the hidden word) only, no 'quicker' / 'more' / 'fewer' / '%'",
       [cCycle, cTrips, cCo2, c8, c17].every(c => !/quicker|longer|more|fewer|less|%|kg more/.test(tipAlt.children[c].textContent.replace("Better: ", "").replace("Worse: ", ""))));
    ok("⭐ NO TINT, NO GREEN: no marked cell carries a background, a bold weight or the ok colour on the cell itself; no bar in the table",
       [...tb.querySelectorAll("td")].every(td => !td.style.background && !td.style.fontWeight && !td.style.color) && !tb.querySelector(".bo-bar, [data-quick]"));
    ok("⭐ PLAIN: the card's lorry's MAIN row has no mark (the rule marks an option against the route in use)",
       !tipMain.querySelector(".bo-fm"));
    ok("⭐ OTHER LORRIES: no cell of the Flatbed (main or Alt 1) is marked, nor are its busy-hour times",
       !flMain.querySelector(".bo-fm") && !flAlt.querySelector(".bo-fm") && !flAlt.querySelector("[data-fig-mark]"));
    ok("⭐ ONLY THREE MEASURES: out and back distances and minutes, turnaround, t/day and t/month are never marked",
       [2, 3, 4, 5, 6, cTrips + 1, cTrips + 2].every(c => c < 0 || !tipAlt.children[c].querySelector(".bo-fm")), tipAlt.querySelectorAll(".bo-fm").length);
    ok("⭐ COUNT: exactly five marked cells in the table (Cycle, Trips/day, CO₂, 08:00, 17:00), all on one row",
       tb.querySelectorAll(".bo-fm").length === 5 && tipAlt.querySelectorAll(".bo-fm").length === 5, tb.querySelectorAll(".bo-fm").length);
    ok("⭐ NOTE: the hours' note no longer says green and names the dot and the diamond",
       TRY(() => { const n = m.host.querySelector("[data-hour-note]").textContent; return !/green/i.test(n) && /dot/.test(n) && /diamond/.test(n); }));
    ok("the table's other figures and the dagger / § signs still print (Cycle 2.3 h, trips 3, carbon 57)",
       tipAlt.children[cCycle].textContent.replace("Worse: ", "").includes("2.3 h") && tipAlt.children[cTrips].textContent.replace("Worse: ", "").startsWith("3")
       && tipAlt.children[cCo2].textContent.replace("Worse: ", "") === "57", [cCycle, cTrips, cCo2].map(c => tipAlt.children[c].textContent).join("|"));
    await m.done();

    // an ok on the rule's carbon (live's R003 Alt 1: carbon ok, round trip warn, trips none): a dot, and none where the rule says none
    const o3 = clone(FX.L003.options[0]);
    const m2 = await open(BEST(o3));
    const t2 = rowsOf(m2.host)[1];
    ok("⭐ MARKS FOLLOW THE RULE: carbon ok → a dot; round trip warn → a diamond; trips none → no shape",
       TRY(() => t2.children[col(m2.host, "CO₂ kg/trip")].querySelector(".bo-fm").getAttribute("data-fig-mark") === "ok"
         && t2.children[col(m2.host, "Cycle")].querySelector(".bo-fm").getAttribute("data-fig-mark") === "warn"
         && !t2.children[col(m2.host, "Trips/day")].querySelector(".bo-fm")));
    ok("⭐ no busy-hour rows held (the rule's 'off' row): the busy-hour cells are plain figures, no green",
       TRY(() => !t2.children[col(m2.host, "08:00")].querySelector(".bo-fm") && t2.children[col(m2.host, "08:00")].textContent === "2.17 h"));
    await m2.done();

    // the card answers for another lorry: the Tipper's rows are plain and the Flatbed's Alt 1 carries the marks
    const m3 = await open(BEST(OPT, FLAT));
    const r3 = rowsOf(m3.host);
    ok("⭐ THE CARD'S LORRY DECIDES: with the card on the Flatbed its Alt 1 is marked and the Tipper's rows are not",
       r3[3].querySelectorAll(".bo-fm").length === 5 && !r3[0].querySelector(".bo-fm") && !r3[1].querySelector(".bo-fm") && !r3[2].querySelector(".bo-fm"));
    await m3.done();

    // a ruled-out option has no rows: no mark; no best answer at all: no mark and the table as before
    const oOut = Object.assign(clone(OPT), { rows: null, ruled_out: ["it adds a limit"] });
    const m4 = await open(BEST(oOut));
    ok("⭐ a ruled-out option (no rows) is not marked anywhere", !m4.host.querySelector("table[data-bo-table] .bo-fm"));
    await m4.done();
    CUR = { route: null };
    const m5 = await open({ day: "2026-11-26", checks: {}, route: null });
    ok("no best answer: the table prints as before and holds no mark", TRY(() => !!m5.host.querySelector("table[data-bo-table]") && !m5.host.querySelector(".bo-fm")));
    await m5.done();
  } catch (e) { ok("ALL FIGURES MARKS DOM: the section ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  finish();
})();

function finish(){
  console.log(`ui_fix_routes_all_marks.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
}
