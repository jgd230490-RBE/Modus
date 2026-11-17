/* ui_fix_route_record.js — 17 Nov 2026, branch claude/route-choices-record (best option step 3; John's "Yes, as
 * recommended" to the third draft, notes\route-choices-record-mockup-1117, and its Q1-Q9). The Dashboard's "Route
 * choices: what each saved or added" fold mounted in a real DOM (jsdom): empty, two choices (the draft's R013 and R014
 * figures), an ended row, a phone; plus the words it must never say.
 *
 * The record fed to the fold is route_record.record()'s shape with the draft's figures (a fictional demo scheme, miles
 * and pounds). Not covered here: the real server's answer (test_route_record.py builds it; smoke_reviewer_wall reaches
 * the endpoint), a browser (the session note's local Chrome pictures), Postgres.
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the code before (no RouteChoicesRecord).
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_route_record.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

// ---------------- source checks ----------------
const a = html.indexOf("function RouteChoicesRecord(");
const fold = a > 0 ? html.slice(html.indexOf("const RC_MONTHS"), html.indexOf("\n}\n", a) + 3) : "";
ok("⭐ SRC: the fold exists, reads /api/route-choices/record on first open, and offers the spreadsheet",
   fold.includes("fetch(`${API}/route-choices/record`)") && fold.includes("if(!open || d) return;")
   && fold.includes("href={`${API}/route-choices/record.xlsx`}"));
ok("⭐ SRC: Copy / Download through ChartTools (the Dashboard's picture icons)", fold.includes("<ChartTools inline title=\"Route choices: what each saved or added\""));
ok("⭐ SRC: no 'avoided', 'safer', 'risk' or 'ratio' in the fold, and no '%' beside a collision count",
   fold.length > 0 && !/\b(avoided|avoid|safer|safe|risk|ratio)\b/i.test(fold) && !/[Cc]ollisions?[^\n]{0,80}%/.test(fold));
ok("⭐ SRC: added figures in red through one class (--bad-text), as the Carbon planner does",
   html.includes(".rc-more{color:var(--bad-text);}") && fold.includes('"rc-more"'));

// ---------------- the fold in a DOM ----------------
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
let REPLY = null;
w.fetch = (url) => (String(url).includes("/route-choices/record") && REPLY
  ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(REPLY))) })
  : new Promise(() => {}));
w.mapboxgl = { Map: function(){ return { on(){}, remove(){} }; } };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
let loaded = true;
try { w.eval(js + "\nwindow.__RC_TENANT = TENANT;"); } catch (e) { loaded = false; console.log("app script failed: " + e.message); }
ok("the app's script runs in the DOM", loaded);
// the demo reads miles and pounds (a top-level const is not on window: the script hands it over at its end)
if (w.__RC_TENANT) Object.assign(w.__RC_TENANT, { distance_unit: "mi", symbol: "£" });
const hasFold = typeof w.RouteChoicesRecord === "function";
ok("⭐ the fold component is defined", hasFold);

const E = w.React.createElement;
async function mount(reply, props){
  REPLY = reply;
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  if (hasFold) await act(async () => { root.render(E(w.RouteChoicesRecord, props || {})); });
  const det = host.querySelector("details[data-route-choices]");
  const closed = det ? !det.open : null;
  if (det) await act(async () => { det.open = true; det.dispatchEvent(new w.Event("toggle", { bubbles: false })); });
  await act(async () => { await new Promise(r => setTimeout(r, 0)); });
  await act(async () => { await new Promise(r => setTimeout(r, 0)); });
  return { host, closed, text: () => host.textContent.replace(/\s+/g, " "), done: () => { act(() => root.unmount()); host.remove(); } };
}
const Z = (o) => Object.assign({ trips: 0, of: 0, km: 0, min: 0, kg: 0, eur: 0, left_turns: 0, cycle_meets: 0, places: 0, eur_missing: false, counts_missing: false }, o || {});
const MI = 1.609344;
// the draft's two rows (card 2): R013's busy-hours road, R014's Make primary; distances given in km, as the server sends
const R013 = { id: "B:R013", route_id: "R013", kind: "busy", alt: 2, label: "Alt 2", legs: ["loaded", "return"], hours_from: "16:00", hours_to: "19:00",
  since: "2026-11-06", status: "in_use", ended_on: null, ended_why: null, ended_words: null, from: "Brook Pit", to: "Harborough Compound",
  lorry: "Artic Tipper (44t)", all_lorries: true,
  per_trip: { km: -5.7 * MI, min: -1.7, kg: -6.3, eur: -8.53, left_turns: 5, cycle_meets: -3, places: -2 },
  planned: Z({ trips: 35.3, of: 212, km: -200 * MI, min: -60, kg: -223, eur: -301, left_turns: 177, cycle_meets: -106, places: -71 }),
  so_far: Z(), collisions: { before: 51, after: 25, before_label: "Main route", after_label: "Alt 2" } };
const R014 = { id: "M:R014", route_id: "R014", kind: "primary", alt: 1, label: "Alt 1", legs: ["loaded", "return"], hours_from: null, hours_to: null,
  since: "2026-11-17", status: "in_use", ended_on: null, ended_why: null, ended_words: null, from: "Brook Pit", to: "Langton Compound",
  lorry: "Artic Tipper (44t)", all_lorries: false,
  per_trip: { km: 0.4 * MI, min: 2.4, kg: -8.2, eur: 2.06, left_turns: -5, cycle_meets: 0, places: 0 },
  planned: Z({ trips: 1389, of: 1389, km: 492 * MI, min: 55.6 * 60, kg: -11390, eur: 2861, left_turns: -6945, cycle_meets: 0, places: 0 }),
  so_far: Z(), collisions: { before: 49, after: 53, before_label: "Old main route", after_label: "Alt 1" } };
const TOT = Z({ trips: 1424.3, km: 292 * MI, min: 54.6 * 60, kg: -11613, eur: 2560, left_turns: -6768, cycle_meets: -106, places: -71 });
const FULL = { rows: [R013, R014], totals: { planned: TOT, so_far: Z() }, diversions: 13, collision_period: "2021–2025", day: "2026-11-17" };

(async () => {
  // ---- empty ----
  {
    const m = await mount({ rows: [], totals: { planned: Z(), so_far: Z() }, diversions: 13, collision_period: null, day: "2026-11-17" });
    const t = m.text();
    ok("⭐ closed each visit (Q5): the fold mounts closed", m.closed === true);
    ok("⭐ empty: the agreed words, and the diversions line", t.includes("No route choice yet.")
       && t.includes("A choice made on Routes is kept here: another main route, or a road for the busy hours.")
       && t.includes("13 routes are on a dated diversion: a closure, not a choice, so not counted here."), t.slice(0, 300));
    ok("...no table and no totals while empty", !m.host.querySelector("[data-rc-table]") && !m.host.querySelector("[data-rc-tiles]"));
    m.done();
  }
  // ---- two choices ----
  {
    const m = await mount(FULL);
    const t = m.text();
    const tile = (k) => (m.host.querySelector(`[data-rc-tile="${k}"] b`) || {}).textContent;
    ok("⭐ the four totals in the draft's words (miles and pounds)", tile("kg") === "11.6 t less" && tile("min") === "54.6 h more"
       && tile("km") === "292 mi more" && tile("eur") === "£2,560 more", [tile("kg"), tile("min"), tile("km"), tile("eur")].join(" | "));
    ok("⭐ what a choice adds is in red; what it saves is not", m.host.querySelector('[data-rc-tile="min"] b.rc-more')
       && !m.host.querySelector('[data-rc-tile="kg"] b.rc-more'));
    ok("⭐ the passes line, each part its own figure", t.includes("A lorry passes, planned: 6,768 fewer left turns · 106 fewer cycle routes met · 71 fewer places"), t);
    ok("⭐ R013's row: the choice, its ends, since, all lorry types, '35 of 212'",
       t.includes("R013 · Alt 2, weekdays 16:00–19:00") && t.includes("Brook Pit → Harborough Compound")
       && t.includes("Since 6 Nov 2026 · all lorry types") && t.includes("35 of 212"));
    const r13 = m.host.querySelector('[data-rc-row="B:R013"]');
    const cellsOf = (row, i) => [...row.querySelectorAll("tr")[i].querySelectorAll("td.num")].map(c => c.textContent);
    ok("⭐ R013 a trip: 6.3 kg less, 1.7 min less, 5.7 mi less, £8.53 less, 5 more, 3 fewer, 2 fewer",
       r13 && JSON.stringify(cellsOf(r13, 0).slice(1)) === JSON.stringify(["6.3 kg less", "1.7 min less", "5.7 mi less", "£8.53 less", "5 more", "3 fewer", "2 fewer"]),
       r13 && cellsOf(r13, 0).join(" | "));
    ok("⭐ R013 planned: 223 kg less, 1.0 h less, 200 mi less, £301 less, 177 more, 106 fewer, 71 fewer",
       r13 && JSON.stringify(cellsOf(r13, 1)) === JSON.stringify(["223 kg less", "1.0 h less", "200 mi less", "£301 less", "177 more", "106 fewer", "71 fewer"]),
       r13 && cellsOf(r13, 1).join(" | "));
    ok("...its added left turns in red", r13 && [...r13.querySelectorAll("td.rc-more")].map(c => c.textContent).join("|") === "5 more|177 more");
    const r14 = m.host.querySelector('[data-rc-row="M:R014"]');
    ok("⭐ R014: 'Alt 1 made the main route', its lorry, a trip with 'the same' at nought",
       t.includes("R014 · Alt 1 made the main route") && t.includes("Since 17 Nov 2026 · ")
       && r14 && JSON.stringify(cellsOf(r14, 0).slice(1)) === JSON.stringify(["8.2 kg less", "2.4 min more", "0.4 mi more", "£2.06 more", "5 fewer", "the same", "the same"]),
       r14 && cellsOf(r14, 0).join(" | "));
    ok("⭐ R014 planned: 11.4 t less, 55.6 h more, 492 mi more, £2,861 more, 6,945 fewer",
       r14 && JSON.stringify(cellsOf(r14, 1).slice(0, 5)) === JSON.stringify(["11.4 t less", "55.6 h more", "492 mi more", "£2,861 more", "6,945 fewer"]),
       r14 && cellsOf(r14, 1).join(" | "));
    ok("⭐ so far with no loads: 'No loads recorded yet' on each row", m.host.querySelectorAll("[data-rc-none]").length === 2);
    const cols = [...m.host.querySelectorAll("[data-rc-collisions]")].map(c => c.textContent);
    ok("⭐ collisions: two counts a row, no chip, no colour, no percentage; the years in the head",
       JSON.stringify(cols) === JSON.stringify(["Alt 2: 25Main route: 51", "Alt 1: 53Old main route: 49"])
       && !m.host.querySelector("[data-rc-collisions] .rc-more, [data-rc-collisions] .row-st") && !cols.join("").includes("%")
       && t.includes("Collisions, 2021–2025"), cols.join(" | "));
    // John, 17 Nov 2026 ("Yes, build both", q1q2 mockup Q1): Collisions sits right after Loads, so at a 1150 px window
    // the sideways scroll never hides it (bends the third draft, where it was the last column)
    const heads = [...m.host.querySelectorAll("[data-rc-table] thead th")].map(h => h.textContent.trim());
    ok("⭐ Q1: the head reads Choice, Loads, Collisions, then the figures",
       heads[0] === "Choice" && heads[1] === "Loads" && heads[2].startsWith("Collisions, 2021–2025"), heads.join(" | "));
    ok("⭐ Q1: in every row the collisions cell comes straight after the loads cell",
       [r13, r14].every(r => { const loads = r && r.querySelector("tr td.num"); return loads && loads.nextElementSibling
         && loads.nextElementSibling.hasAttribute("data-rc-collisions"); }));
    ok("⭐ the head: 'Planned, not measured', the picture icons and the Spreadsheet button",
       t.includes("Planned, not measured") && m.host.querySelector("[data-chart-tools]") && m.host.querySelector("[data-rc-sheet]"));
    ok("⭐ the diversions line under the table", t.includes("13 routes are on a dated diversion: a closure, not a choice, so not counted here."));
    ok("⭐ the rendered fold says no 'avoided', 'safer', 'risk' or 'ratio'", !/\b(avoided|avoid|safer|safe|risk|ratio)\b/i.test(t));
    m.done();
  }
  // ---- an ended row ----
  {
    const ended = Object.assign({}, R014, { id: "M:R014e", status: "ended", ended_on: "2027-07-01", ended_why: "routed_again", ended_words: "routed again",
      planned: Z({ trips: 233, of: 233, km: 83 * MI, min: 9.3 * 60, kg: -1900, eur: 480, left_turns: -1165 }),
      so_far: Z({ trips: 200, of: 200, km: 71 * MI, min: 8 * 60, kg: -1600, eur: 412, left_turns: -1000 }) });
    const m = await mount({ rows: [ended], totals: { planned: ended.planned, so_far: ended.so_far }, diversions: 0, collision_period: "2021–2025", day: "2026-11-17" });
    const t = m.text();
    const row = m.host.querySelector('[data-rc-row="M:R014e"]');
    ok("⭐ an ended row: its chip, its dates, greyed; its so far filled in", t.includes("Ended: routed again")
       && t.includes("17 Nov 2026 to 1 Jul 2027") && row && row.classList.contains("rc-ended")
       && [...row.querySelectorAll("tr")[2].querySelectorAll("td.num")].map(c => c.textContent)[0] === "1.6 t less", t.slice(0, 400));
    ok("...no diversions line when none", !m.host.querySelector("[data-rc-diversions]"));
    m.done();
  }
  // ---- a count not held: that figure a dash, the others shown ----
  {
    const r = Object.assign({}, R014, { id: "M:R014n", per_trip: Object.assign({}, R014.per_trip, { cycle_meets: null }),
      planned: Object.assign({}, R014.planned, { cycle_meets: null, counts_missing: true }) });
    const T2 = Object.assign({}, TOT, { cycle_meets: null, counts_missing: true });
    const m = await mount({ rows: [r], totals: { planned: T2, so_far: Z() }, diversions: 0, collision_period: null, day: "2026-11-17" });
    const t = m.text();
    ok("⭐ a count not held reads a dash for that figure only; left turns and places still show",
       t.includes("A lorry passes, planned: 6,768 fewer left turns · — cycle routes met · 71 fewer places")
       && [...m.host.querySelector('[data-rc-row="M:R014n"]').querySelectorAll("tr")[1].querySelectorAll("td.num")].map(c => c.textContent).slice(4).join("|") === "6,945 fewer|—|the same", t);
    m.done();
  }
  // ---- a phone ----
  {
    const m = await mount(FULL, { phone: true });
    const t = m.text();
    ok("⭐ a phone: the four totals and a short card a choice; no table, no download (Q5)",
       m.host.querySelectorAll("[data-rc-tile]").length === 4 && m.host.querySelectorAll("[data-rc-pcard]").length === 2
       && !m.host.querySelector("[data-rc-table]") && !m.host.querySelector("[data-rc-sheet]") && !m.host.querySelector("[data-chart-tools]"));
    ok("⭐ ...the cards in the draft's words", t.includes("R013 · Alt 2, 16:00–19:00") && t.includes("35 loads planned: 223 kg less, 1.0 h less, 177 more left turns")
       && t.includes("R014 · Alt 1 the main route") && t.includes("1,389 loads planned: 11.4 t less, 55.6 h more, 6,945 fewer left turns"), t);
    ok("...the short tile name on a phone", (m.host.querySelector('[data-rc-tile="eur"] .rc-tk') || {}).textContent === "Fair cost");
    m.done();
  }
  // ---- a phone card with a figure that does not change (John, 17 Nov 2026, q1q2 mockup Q2): the card names it ----
  {
    const same = Object.assign({}, R014, { planned: Object.assign({}, R014.planned, { min: 0 }) });
    const sameKg = Object.assign({}, R013, { planned: Object.assign({}, R013.planned, { kg: 0, left_turns: 0 }) });
    const m = await mount({ rows: [sameKg, same], totals: { planned: TOT, so_far: Z() }, diversions: 0, collision_period: null, day: "2026-11-17" }, { phone: true });
    const t = m.text();
    ok("⭐ Q2: a phone card says WHAT is the same: 'lorry time the same', never 'the same' alone",
       t.includes("1,389 loads planned: 11.4 t less, lorry time the same, 6,945 fewer left turns"), t);
    ok("⭐ Q2: ...'carbon the same' and 'left turns the same' too; a changed figure reads as before",
       t.includes("35 loads planned: carbon the same, 1.0 h less, left turns the same"), t);
    m.done();
  }
  console.log(`ui_fix_route_record.js: ${pass} passed, ${fail.length} failed`);
  for (const f of fail) console.log("  ✗ " + f);
  process.exit(fail.length ? 1 : 0);
})();
