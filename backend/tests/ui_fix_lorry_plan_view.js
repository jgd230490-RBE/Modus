/*
 * ui_fix_lorry_plan_view.js — the Look-ahead rethink, task C1 (25 Nov 2026; card 3 of notes\lookahead-rethink-mockup-1124,
 * John's "Yes, as recommended" to Q1 to Q19): the Lorry plan as the week's second view, "By site · By lorry", and a
 * lorry's driver sheet opening on the screen under its row.
 *
 * Mounts the real LorryPlan and LaViewSwitch (jsdom, the page's own code) with the Lorry plan read stubbed in the server's
 * shape and the driver sheet read (GET /api/forecast-weeks/lorry-plan/sheet) stubbed in the shape of
 * lorry_plan.driver_pages (task B2's committed read; test_lorry_plan.py proves the server's side). What it proves:
 *   - the view switch: "View: By site | By lorry", aria-pressed, remembered for the session (sessionStorage modus_la_by);
 *     the plan mounts OPEN with no fold, and draws nothing while "By site" is chosen (show=false) but still reads;
 *   - the three cells, a label over each: Lorries on the day, Lorry-days saved, Saved this week; As booked's dashes;
 *     no day rate typed: the link "Set a day rate" (planner / admin) or plain words (a team), one typed: the money;
 *   - "load point" for "yard" in every word the screen makes; "Chained by load point";
 *   - the day as underlined tabs with ", today" on today's; a day press closes an open sheet;
 *   - trip blocks named by SITE (the type word dropped), the route in the block's tip; the site colours: no hue between
 *     15 and 45 degrees, never the sign blue or the chart orange, white words at 4.5 : 1 or better, in both looks;
 *   - a lorry's name is a button with aria-expanded; it opens THAT lorry's sheet under its row (one read with the block's
 *     yard, vehicle and lorry), focus to its heading; one sheet at a time; a second press or Escape closes it and gives
 *     focus back; a day or view change closes it;
 *   - the sheet prints the read's words as they come: the trips, the break's sentence, the line, the gate, the team,
 *     the small print's first line, each route's "Take care" block (its head, sentences, legs, limits and places, the
 *     gate, the foot), a road number as a plate; a lorry with three routes shows three blocks and their route lines;
 *   - a read that fails says one plain sentence; "Download this sheet" asks /download with yard, vehicle, lorry;
 *     "Driver sheets ▾" offers the day's sheets and one item a load point · lorry type;
 *   - gone, at source: "Chained by yard", the head sentence, data-lp-toggle, "yard" in the screen's words.
 * What it does NOT prove: a real browser's layout or a block's measured name (jsdom has no layout: the pictures in
 * notes\lookahead-rethink-mockup-1124\built\lorry\ do), the PDF itself, the print dialog.
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_lorry_plan_view.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const src = code.replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "sessionStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.matchMedia = () => ({ matches: false, addEventListener(){}, removeEventListener(){} });
w.print = () => { w.__printed = (w.__printed || 0) + 1; };
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__F = { lpSiteName, lpPalette, lpDeep, lpLum, LP_SITE_HEX, LP_VIEW_WORDS, lpPlates };");
const F = w.__F;

const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
const settle = async () => { for (let i = 0; i < 8; i++) await act(async () => { await new Promise(r => setTimeout(r, 0)); }); };
const click = async (el) => { await act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await settle(); };
const key = async (el, k) => { await act(async () => { el.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true })); }); await settle(); };

// ---------------------------------------------------------------- the made-up plan (the server's shape, as dom_frontend's)
const DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"];
const row = (n, trips, free, words, blocks, places) => ({ n, trips, places: places || ["Melton Compound"], blocks, start: "07:00", end: "15:40",
  driving_minutes: 300, work_minutes: 500, break_minutes: 45, free_minutes: free, room_for: 0, used_pct: 90, free_words: words });
const trip = (start, route, dest, day) => ({ kind: "trip", route_id: route, dest_id: "L1", dest_name: dest || "Melton Compound", line_key: route + "|11||", start, minutes: 91, qty: 29, unit: "t", material: "Small aggregate", day, drive: 64, other: 27 });
const yard = (day) => ({ origin_id: "L002", yard_id: "L002", name: "Northfield Quarry", vehicle: "Artic Tipper (44t)", vehicle_short: "Tipper", gate: "Weighbridge", day,
  loads: 9, booked: 3, kept: 0, count: 2, places: ["Melton Compound", "Tilton Viaduct site", "Stockpile North"],
  lorries: [row(1, 6, 9, "Full day", [trip("07:00", "R011", null, day), trip("08:31", "R011", null, day), trip("10:02", "R011", null, day), trip("11:33", "R011", null, day),
              { kind: "break", start: "13:04", minutes: 45 }, trip("13:49", "R011", null, day), trip("15:20", "R011", null, day)]),
            row(2, 3, 200, "3 h 20 free · room for 2 more trips", [trip("07:00", "R011", null, day), trip("08:31", "R014", "Tilton Viaduct site", day), trip("10:02", "R018", "Stockpile North", day)],
              ["Melton Compound", "Tilton Viaduct site", "Stockpile North"])] });
const byDay = (n) => Object.fromEntries(DAYS.map(d => [d, n]));
const view = (n, saved) => ({ by_day: byDay(n), week: n * 5, saved_week: saved, days: Object.fromEntries(DAYS.map(d => [d, [yard(d)]])) });
const mkPlan = (over = {}) => ({ week: { from: "2026-11-02", to: "2026-11-08", bucket: "commit" }, days: DAYS, today: "2026-11-04", view_default: "chained", views: ["booked", "chained", "compressed"],
  shift_hours: 10, team_only: null, made_by: "Planner", made_at: "8 Nov 2026 20:00", week_confirmed: false, any_confirmed: false,
  booked: { by_day: byDay(27), week: 135 }, chained: view(16, 55), compressed: { ...view(14, 68), moves: [] },
  day_hire: { rates: {}, typed: false, chained: null, compressed: null },
  words: { rule: "A rule.", planning: "A planning figure.", compress: "A suggestion until Apply.", one_yard: "", not_modelled: "", sends_nothing: "" }, ...over });

// the driver sheet read, in lorry_plan.driver_pages' shape (B2's committed read): every word below must reach the screen as it is
const leg = (lg, title, length, limits, places, more) => ({ leg: lg, title, length, km: 9.4, limits, places, more: 0, shared: 0, more_words: more || "", shared_words: "" });
const take = (route, dest) => ({ route_id: route, vehicle: "Artic Tipper (44t)", vehicle_text: "Artic Tipper (44t)", day: "2026-11-04", origin: "Northfield Quarry", dest,
  head: "Take care on this route", foot: "Road signs come first. Distances are along the route from the gate.", unit: "mi", routed: true,
  sentences: [`Planned on ${route}: the main route.`], closures: route === "R011" ? [{ kind: "planned", text: "A planned closure on the B6047 from 3 Dec." }] : [],
  legs: [leg("out", "Out", "9.4 mi", [{ w: "2.1 mi", text: "Melton Road, B6047: 7.5 t weight limit", at_km: 3.4, state: "allowed" }],
               [{ w: "4.0 mi", text: "Tilton Primary School", n: 1 }], "and 2 more places further on"),
         leg("back", "Back", "9.6 mi", [], [])],
  nothing: "", limits: 1, limits_checked: true, places_fetched: true, gate: "At the gate: Weighbridge, open 06:00 to 18:00.", holding: "", vehicle_values: {} });
const sheetPage = (n, routes) => ({ yard_id: "L002", load_point: "Northfield Quarry", vehicle: "Artic Tipper (44t)", vehicle_text: "Artic Tipper (44t)", lorry: n, of: 2,
  head: `Lorry ${n} of 2 · Northfield Quarry · Artic Tipper (44t)`, day_words: "Wednesday 4 November 2026",
  line: `${routes.length} route${routes.length === 1 ? "" : "s"}, 6 trips, about 8 h 31 of the day`, team: "Earthworks team's lines", gate: "Load at Northfield Quarry, Weighbridge.",
  rows: [{ kind: "trip", about: "07:00", route_id: routes[0], from: "Northfield Quarry", to: "Melton Compound", material: "Small aggregate", load: "29 t", round_trip: "1 h 31" },
         { kind: "break", about: "13:04", text: "45 min break, as the UK drivers' hours rules require." },
         { kind: "trip", about: "13:49", route_id: routes[routes.length - 1], from: "Northfield Quarry", to: "Stockpile North", material: "Small aggregate", load: "29 t", round_trip: "1 h 31" }],
  routes, take_care: routes.map((r, i) => take(r, ["Melton Compound", "Tilton Viaduct site", "Stockpile North"][i])),
  small: ["A planning sheet: the times are planned, not booked.", "Made 25 Nov 2026 by Planner · credits"] });

let PLAN = mkPlan(), reads = [], sheetFails = false;
w.fetch = (url) => {
  const u = String(url); reads.push(u);
  const reply = (status, body) => Promise.resolve({ ok: status < 400, status, headers: { get: () => "application/json" },
    json: () => Promise.resolve(JSON.parse(JSON.stringify(body))), text: () => Promise.resolve(JSON.stringify(body)), blob: () => Promise.resolve(new w.Blob(["%PDF"])) });
  if (/lorry-plan\/sheet\?/.test(u)) {
    if (sheetFails) return reply(500, { detail: "boom" });
    const n = +(/[?&]lorry=(\d+)/.exec(u) || [])[1];
    return reply(200, { title: "Driver sheets", day: "2026-11-04", view: "chained", stamp: "", sub: "", pages: [sheetPage(n, n === 2 ? ["R011", "R014", "R018"] : ["R011"])], routes: [] });
  }
  if (/lorry-plan\/download\?/.test(u)) return reply(200, {});
  return reply(200, PLAN);
};
w.URL.createObjectURL = () => "blob:x"; w.URL.revokeObjectURL = () => {};

const mount = async (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  await act(async () => { r.render(w.React.createElement(C, props)); }); await settle();
  return { el, rerender: async (p) => { await act(async () => { r.render(w.React.createElement(C, p)); }); await settle(); }, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };
const LP = (over = {}) => ({ bucket: "commit", tick: 0, access: { role: "planner" }, onData: () => {}, weekConfirmed: false, today: "2026-11-04", show: true, viewSwitch: null, ...over });
const cells = (el) => [...el.querySelectorAll(".lp-kpi")].map(e => ({ l: norm(e.querySelector(".lp-kl").firstChild.textContent), v: norm(e.querySelector("b").textContent), s: norm((e.querySelector(":scope > span") || {}).textContent) }));

(async () => {
  // ---------------------------------------------------------------- 1. the view switch
  {
    let chosen = null;
    const m = await mount(w.LaViewSwitch, { value: "lorry", onChange: (k) => { chosen = k; } });
    const bs = [...m.el.querySelectorAll("[data-la-by-btn]")];
    ok("⭐ C1: the view switch reads 'View  By site | By lorry', a named group, the chosen one pressed",
       norm(m.el.textContent) === "ViewBy siteBy lorry" && !!m.el.querySelector('[role="group"][aria-label="View the week"]')
       && bs.map(b => b.getAttribute("aria-pressed")).join() === "false,true", norm(m.el.textContent));
    await click(bs[0]);
    ok("C1: pressing By site hands 'site' up", chosen === "site");
    m.done();
    const LA = between("function LookAhead({ meta, who, access, initialPage, initialView", "\nfunction CommitMap(");
    ok("⭐ C1: the choice is remembered for the session (sessionStorage modus_la_by), By site to start",
       /sessionStorage\.getItem\("modus_la_by"\)/.test(LA) && /sessionStorage\.setItem\("modus_la_by"/.test(LA) && LA.includes('laBy === "lorry" ? null :'));
    ok("C1: the Lorry plan sits in the list's place, beside the switch, read in both views and drawn only in By lorry",
       LA.includes('show={laBy === "lorry"} viewSwitch={<LaViewSwitch value={laBy} onChange={setLaBy} />}') && LA.includes('<span className="lp-bar-l"><LaViewSwitch value={laBy} onChange={setLaBy} />'));
  }

  // ---------------------------------------------------------------- 2. open, no fold; the three cells
  reads = [];
  const m = await mount(w.LorryPlan, LP());
  const sec = () => m.el.querySelector("[data-lorry-plan]");
  ok("⭐ C1: the plan mounts OPEN: no fold, no head sentence, its rows drawn; one read",
     !!sec() && !m.el.querySelector("[data-lp-toggle]") && !m.el.querySelector("[data-lp-head]") && m.el.querySelectorAll(".lp-row").length === 2
     && reads.filter(u => /lorry-plan\?/.test(u)).length === 1);
  let kc = cells(m.el);
  ok("⭐ C1: three cells, a label over each: 'Lorries, Wed 4' 16 (27 as booked · 80 against 135 this week)",
     kc.length === 3 && kc[0].l === "Lorries, Wed 4" && kc[0].v === "16" && kc[0].s === "27 as booked · 80 against 135 this week", JSON.stringify(kc[0]));
  ok("C1: 'Lorry-days saved' 11 (55 this week)", kc[1].l === "Lorry-days saved" && kc[1].v === "11" && kc[1].s === "55 this week", JSON.stringify(kc[1]));
  ok("⭐ C1: no day rate typed: 'Saved this week' a dash and the link 'Set a day rate' for a planner",
     kc[2].l === "Saved this week" && / —$/.test(kc[2].v) && kc[2].s === "Set a day rate" && !!m.el.querySelector('button[data-lp-rate="1"]'), JSON.stringify(kc[2]));
  await click(m.el.querySelector('[data-lp-rate="1"]'));
  ok("C1: 'Set a day rate' opens Config on Costing · fuel", w.location.hash === "#config" && w.sessionStorage.getItem("modus_cfg_tab") === "costing");
  ok("C1: Config reads that once and forgets it", code.includes('window.sessionStorage.getItem("modus_cfg_tab")') && code.includes('window.sessionStorage.removeItem("modus_cfg_tab")'));
  const sub = norm(m.el.querySelector(".lp-sub").textContent);
  ok("C1: a load point's line in sites: '9 loads to 3 sites · 3 lorries as booked · 2 chained'", sub.startsWith("9 loads to 3 sites · 3 lorries as booked · 2 chained"), sub);

  // ---------------------------------------------------------------- 3. the day tabs
  const tabs = [...m.el.querySelectorAll('.lp-days[role="group"][aria-label="Day"] button')];
  ok("⭐ C1: the day as tabs, today's said: 'Wed 4, today' pressed", tabs.length === 5 && norm(tabs[2].textContent) === "Wed 4, today"
     && tabs[2].getAttribute("aria-pressed") === "true" && tabs.filter(t => t.getAttribute("aria-pressed") === "true").length === 1, tabs.map(t => norm(t.textContent)).join("|"));
  ok("C1: the tabs are underlined (a 2 px sign-blue line), never a filled chip", /\.lp-days button\[aria-pressed="true"\]\{color:var\(--navy\);box-shadow:inset 0 -2px 0 var\(--navy\)\}/.test(html));
  await click(tabs[3]);
  ok("C1: a tab press shows that day", m.el.querySelectorAll('.lp-days button[aria-pressed="true"]')[0].textContent === "Thu 5" && cells(m.el)[0].l === "Lorries, Thu 5");
  await click([...m.el.querySelectorAll(".lp-days button")][2]);

  // ---------------------------------------------------------------- 4. the blocks: named by site, coloured by site
  const blk = [...m.el.querySelectorAll(".lp-row")][1].querySelectorAll(".lp-blk");
  ok("⭐ C1: a trip block carries its SITE's name, the type word dropped; the route in its tip",
     [...blk].map(b => norm(b.textContent)).join("|") === "Melton|Tilton Viaduct|Stockpile North" && /R014 → Tilton Viaduct site/.test(blk[1].getAttribute("title") || ""),
     [...blk].map(b => norm(b.textContent)).join("|"));
  ok("C1: lpSiteName: 'Melton Compound' → 'Melton', 'Harborough Rail Freight Terminal' → 'Harborough RFT', 'Stockpile North' kept",
     F.lpSiteName("Melton Compound") === "Melton" && F.lpSiteName("Harborough Rail Freight Terminal") === "Harborough RFT" && F.lpSiteName("Stockpile North") === "Stockpile North");
  ok("C1: a block too narrow for its name carries none: each name measured against its block (is-cut, hidden)",
     /\.lp-name\.is-cut\{[^}]*visibility:hidden/.test(html) && between("function LorryPlanRow(", "function LorryPlan(").includes('n.classList.add("is-cut")'));
  const colours = new Set([...m.el.querySelectorAll(".lp-blk:not(.is-break)")].map(b => b.style.background));
  ok("C1: one colour a site (three sites, three colours)", colours.size === 3, [...colours].join(" "));
  const hexOf = (s) => { const m2 = /^#([0-9a-f]{6})$/i.exec(s.trim()); return m2 ? s.trim() : null; };
  const hue = (h) => { const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255); const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    if (!d) return null; let x = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; x *= 60; return x < 0 ? x + 360 : x; };
  const contrast = (h) => 1.05 / (F.lpLum(h) + 0.05);
  const rootBlk = (html.match(/:root\{[^}]*--lp-s1:[^}]*\}/) || [""])[0], darkBlk = (html.match(/html\[data-theme="dark"\]\{[^}]*--lp-s1:[^}]*\}/) || [""])[0];
  const tokHex = (blkTxt) => Array.from({ length: 8 }, (_, i) => hexOf((new RegExp(`--lp-s${i + 1}:(#[0-9A-Fa-f]{6})`).exec(blkTxt) || [])[1] || ""));
  const looks = { list: Array.from(F.LP_SITE_HEX), light: tokHex(rootBlk), dark: tokHex(darkBlk) };
  for (const [look, hexes] of Object.entries(looks)) {
    const bad = hexes.filter(h => !h || (hue(h) != null && hue(h) >= 15 && hue(h) <= 45) || contrast(F.lpDeep(h)) < 4.5
      || ["#0B4EA2", "#8AB4F8", "#E8590C"].includes(h.toUpperCase()));
    ok(`⭐ C1: the site colours (${look}): 8, no hue 15–45°, not the sign blue or the chart orange, white words 4.5 : 1 or better`, hexes.length === 8 && !bad.length,
       hexes.map(h => `${h} ${h && hue(h) != null ? hue(h).toFixed(0) : "-"}° ${h ? contrast(F.lpDeep(h)).toFixed(2) : ""}`).join(", "));
  }
  ok("C1: the light tokens are the list the page falls back to", looks.light.join() === looks.list.join());

  // ---------------------------------------------------------------- 5. the words: load point, never yard
  const shown = norm(sec().textContent);
  ok("⭐ C1: 'Chained by load point' on the view button; no 'yard' anywhere the plan shows",
     [...m.el.querySelectorAll('[aria-label="Lorry plan view"] button')].map(b => norm(b.textContent)).join("|") === "As booked|Chained by load point|Week compressed"
     && !/yard/i.test(shown) && F.LP_VIEW_WORDS.chained === "Chained by load point", shown.match(/.{20}yard.{20}/i));
  const panelSrc = between("const LP_VIEW_WORDS", "function GatesWeek({");
  const strings = (panelSrc.match(/"[^"\n]*"|`[^`\n]*`|>[^<>{}\n]+</g) || []).filter(s => /yard/i.test(s) && !/yard_id|yard=|\byard\b\.|yard:|data-lp|lp-yard|\$\{yard|Yard\b.*price/.test(s));
  ok("⭐ C1 gone: no string the panel makes says 'yard'", !strings.length, strings.join(" ¦ "));
  ok("C1 gone: 'Chained by yard', the head sentence and the fold's toggle are out of the page",
     !code.includes("Chained by yard") && !code.includes("data-lp-head") && !code.includes("data-lp-toggle") && !code.includes("lorry-days this week with each yard's lorries chained"));

  // ---------------------------------------------------------------- 6. the sheet: open, focus, one at a time, Escape
  reads = [];
  const openBtn = (n) => m.el.querySelector(`[data-lp-open="${n}"]`);
  ok("⭐ C1: a lorry's name is a button with aria-expanded=false to start", openBtn(1).tagName === "BUTTON" && openBtn(1).getAttribute("aria-expanded") === "false"
     && norm(openBtn(1).textContent) === "Lorry 1");
  await click(openBtn(1));
  let sh = m.el.querySelector("[data-lp-sheet]");
  const sreads = reads.filter(u => /lorry-plan\/sheet\?/.test(u));
  ok("⭐ C1: it opens THAT lorry's sheet under its row: one read with the day, view, yard, vehicle and lorry",
     !!sh && sh.getAttribute("data-lp-sheet") === "1" && sreads.length === 1
     && /sheet\?bucket=commit&view=chained&day=2026-11-04&yard=L002&vehicle=Artic%20Tipper%20\(44t\)&lorry=1$/.test(sreads[0])
     && sh.previousElementSibling && sh.previousElementSibling.getAttribute("data-lp-lorry") === "1", sreads.join(" "));
  ok("C1: aria-expanded true, aria-controls the sheet, the row tinted", openBtn(1).getAttribute("aria-expanded") === "true" && openBtn(1).getAttribute("aria-controls") === sh.id
     && openBtn(1).closest(".lp-row").classList.contains("is-sel"));
  ok("⭐ C1: focus moves to the sheet's heading 'Lorry 1 of 2 · Wed 4 Nov'", w.document.activeElement === sh.querySelector("h5") && norm(sh.querySelector("h5").textContent) === "Lorry 1 of 2 · Wed 4 Nov",
     norm(w.document.activeElement && w.document.activeElement.textContent));
  const st = norm(sh.textContent);
  const P = sheetPage(1, ["R011"]);
  ok("⭐ C1: the sheet prints the read's words as they come: trips, the break's sentence, the line, the gate, the team, the small print's first line",
     st.includes("07:00") && st.includes("Northfield Quarry → Melton Compound") && st.includes("Small aggregate") && st.includes("29 t") && st.includes("1 h 31")
     && st.includes(P.rows[1].text) && st.includes(P.line + ".") && st.includes(P.gate) && st.includes(P.team) && st.includes(P.small[0]) && !st.includes(P.small[1]), st.slice(0, 400));
  const T = P.take_care[0];
  ok("⭐ C1: 'Take care on this route' as the read wrote it: the head, the sentence, the closure, Out and Back with their lengths, the limit and the place with their marks, the gate, the foot",
     st.includes(T.head) && st.includes(T.sentences[0]) && st.includes(T.closures[0].text.replace("B6047", "B6047")) && st.includes("Out, 9.4 mi") && st.includes("Back, 9.6 mi")
     && st.includes("2.1 mi") && st.includes("Melton Road, B6047: 7.5 t weight limit") && st.includes("4.0 mi") && st.includes("Tilton Primary School")
     && st.includes("and 2 more places further on") && st.includes("Nothing held this way.") && st.includes(T.gate) && st.includes(T.foot), st);
  ok("C1: a road number in the read's words is drawn as a plate; the words around it unchanged",
     [...sh.querySelectorAll(".lp-plate")].some(p => p.textContent === "B6047") && norm(sh.querySelector('[data-lp-point="limit"]').textContent) === "2.1 miMelton Road, B6047: 7.5 t weight limit");
  ok("C1: a one-route lorry's block carries no route line", !sh.querySelector(".lp-tk-r") && sh.querySelectorAll("[data-lp-tk]").length === 1);
  ok("C1: collisions are not on the sheet", !/collision/i.test(st));
  // Download this sheet, Print
  reads = [];
  await click(sh.querySelector("[data-lp-sheet-pdf]"));
  ok("⭐ C1: 'Download this sheet' asks for that one page: yard, vehicle, lorry, pdf",
     reads.some(u => /lorry-plan\/download\?bucket=commit&view=chained&day=2026-11-04&yard=L002&vehicle=Artic%20Tipper%20\(44t\)&lorry=1&format=pdf$/.test(u)), reads.join(" "));
  await click(sh.querySelector("[data-lp-sheet-print]"));
  ok("C1: 'Print' prints the panel alone (html.lp-printing while the dialog is up)", w.__printed === 1 && /html\.lp-printing[^{]*\{[^}]*display:none/.test(html.replace(/\n/g, " ")) || (w.__printed === 1 && html.includes("html.lp-printing")));
  // one at a time
  await click(openBtn(2));
  const all = m.el.querySelectorAll("[data-lp-sheet]");
  sh = m.el.querySelector("[data-lp-sheet]");
  ok("⭐ C1: one sheet at a time: opening lorry 2 closes lorry 1's", all.length === 1 && sh.getAttribute("data-lp-sheet") === "2" && openBtn(1).getAttribute("aria-expanded") === "false");
  const s2 = norm(sh.textContent);
  ok("⭐ C1: a lorry with three routes: three 'Take care' blocks, each with its route line",
     sh.querySelectorAll("[data-lp-tk]").length === 3 && [...sh.querySelectorAll(".lp-tk-r")].map(e => norm(e.textContent)).join("|") === "R011 · Northfield Quarry – Melton Compound|R014 · Northfield Quarry – Tilton Viaduct site|R018 · Northfield Quarry – Stockpile North",
     [...sh.querySelectorAll(".lp-tk-r")].map(e => norm(e.textContent)).join("|"));
  await key(sh.querySelector("h5"), "Escape");
  await settle(); await act(async () => { await new Promise(r => setTimeout(r, 5)); });
  ok("⭐ C1: Escape closes it and gives focus back to the lorry's name", !m.el.querySelector("[data-lp-sheet]") && w.document.activeElement === openBtn(2)
     && openBtn(2).getAttribute("aria-expanded") === "false", w.document.activeElement && w.document.activeElement.outerHTML.slice(0, 80));
  await click(openBtn(2)); await click(openBtn(2));
  ok("C1: a second press of the name closes it", !m.el.querySelector("[data-lp-sheet]"));
  await click(openBtn(1));
  await click([...m.el.querySelectorAll(".lp-days button")][3]);
  ok("C1: a day press closes an open sheet", !m.el.querySelector("[data-lp-sheet]"));
  await click([...m.el.querySelectorAll(".lp-days button")][2]);
  await click(openBtn(1));
  await click([...m.el.querySelectorAll('[aria-label="Lorry plan view"] button')][2]);
  ok("C1: a view change closes it too", !m.el.querySelector("[data-lp-sheet]"));
  await click([...m.el.querySelectorAll('[aria-label="Lorry plan view"] button')][1]);

  // a read that fails
  sheetFails = true;
  await click(openBtn(1));
  const er = m.el.querySelector("[data-lp-sheet-err]");
  ok("⭐ C1: a sheet whose read fails says one plain sentence, no status or reply; Download and Print off",
     !!er && /^The driver sheet could not be read\./.test(norm(er.textContent)) && !/500|boom|detail/.test(er.textContent)
     && m.el.querySelector("[data-lp-sheet-pdf]").disabled && m.el.querySelector("[data-lp-sheet-print]").disabled, er && er.textContent);
  sheetFails = false;
  await click(openBtn(1));

  // ---------------------------------------------------------------- 7. Driver sheets ▾, drag after Move trips
  const menu = m.el.querySelector("[data-lp-sheets-menu]");
  ok("⭐ C1: 'Driver sheets ▾' offers the day's sheets and one item a load point · lorry type",
     norm(menu.querySelector("summary").textContent) === "Driver sheets ▾" && norm(menu.querySelector("[data-lp-sheets-day]").textContent) === "This day, 2 sheets"
     && [...menu.querySelectorAll("[data-lp-sheets-yard]")].map(b => norm(b.textContent)).join("|") === "Northfield Quarry · Artic Tipper (44t), 2 sheets",
     norm(menu.textContent));
  reads = [];
  await click(menu.querySelector("[data-lp-sheets-yard]"));
  ok("C1: the load point's item asks /download with its yard and vehicle",
     reads.some(u => /lorry-plan\/download\?bucket=commit&view=chained&day=2026-11-04&format=pdf&yard=L002&vehicle=Artic%20Tipper%20\(44t\)$/.test(u)), reads.join(" "));
  ok("C1: before 'Move trips' no trip drags", [...m.el.querySelectorAll(".lp-trip")].every(t => t.getAttribute("draggable") === "false"));
  await click(m.el.querySelector("[data-lp-move-toggle]"));
  ok("C1: after 'Move trips' every trip drags and the hint says 'load point'", [...m.el.querySelectorAll(".lp-trip")].every(t => t.getAttribute("draggable") === "true")
     && /another lorry of its load point/.test(norm(m.el.querySelector("[data-lp-drag-hint]").textContent)));
  await click(m.el.querySelector("[data-lp-move-toggle]"));

  // ---------------------------------------------------------------- 8. As booked; a day rate typed; drawn only in By lorry
  await click([...m.el.querySelectorAll('[aria-label="Lorry plan view"] button')][0]);
  kc = cells(m.el);
  ok("C1: As booked: 27 lorries (135 this week), saved a dash 'no saving in this view', no sheets", kc[0].v === "27" && kc[0].s === "135 this week" && kc[1].v === "—"
     && kc[1].s === "no saving in this view" && !m.el.querySelector("[data-lp-open]") && /Chained by load point to see them filled/.test(norm(sec().textContent)), JSON.stringify(kc));
  m.done();
  PLAN = mkPlan({ day_hire: { typed: true, rates: { x: 1 }, chained: { eur: 6050, missing: ["Concrete mixer 8 m³ (32t)"] }, compressed: { eur: 7150, missing: [] } } });
  const r2 = await mount(w.LorryPlan, LP());
  kc = cells(r2.el);
  ok("⭐ C1: a day rate typed: the money with 'an estimate' and the lorry type with no rate; no link",
     /6,050$/.test(kc[2].v) && kc[2].s.startsWith("an estimate · no rate for ") && !r2.el.querySelector("[data-lp-rate]"), JSON.stringify(kc[2]));
  r2.done();
  PLAN = mkPlan({ chained: view(27, 0) });
  const r3 = await mount(w.LorryPlan, LP());
  kc = cells(r3.el);
  ok("C1: a week with no saving: 0 lorry-days saved, 0 this week", kc[1].v === "0" && kc[1].s === "0 this week", JSON.stringify(kc[1]));
  r3.done();
  PLAN = mkPlan({ team_only: "IPT1" });
  const r4 = await mount(w.LorryPlan, LP({ access: { role: "team", team: "IPT1" } }));
  kc = cells(r4.el);
  ok("⭐ C1: a team login: plain words 'no day rate typed' (no link), no Move trips, no Apply, the sheets still open",
     kc[2].s === "no day rate typed" && !r4.el.querySelector("[data-lp-rate]") && !r4.el.querySelector("[data-lp-move-toggle]") && !r4.el.querySelector("[data-lp-apply]")
     && !!r4.el.querySelector("[data-lp-open]"), JSON.stringify(kc[2]));
  r4.done();
  PLAN = mkPlan();
  reads = [];
  const r5 = await mount(w.LorryPlan, LP({ show: false }));
  ok("⭐ C1: By site chosen: the plan still reads (the page's 'if chained' figure) but draws nothing",
     !r5.el.querySelector("[data-lorry-plan]") && reads.filter(u => /lorry-plan\?/.test(u)).length === 1);
  await r5.rerender(LP({ show: true }));
  ok("C1: By lorry then draws it with no second read", !!r5.el.querySelector("[data-lorry-plan]") && reads.filter(u => /lorry-plan\?/.test(u)).length === 1);
  r5.done();

  console.log(`ui_fix_lorry_plan_view.js: ${pass} passed, ${fail.length} failed`);
  for (const f of fail) console.log("  FAIL: " + f);
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.log("ui_fix_lorry_plan_view.js: CRASH " + (e && e.stack || e)); console.log(`ui_fix_lorry_plan_view.js: ${pass} passed, ${fail.length + 1} failed`); process.exit(1); });
