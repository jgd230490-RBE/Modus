/* ui_fix_best_option_1117.js — 17 Nov 2026, branch claude/ui-best-option-1117 (the live check and UI / UX review of the best
 * option, notes\ux-best-option-1117; John: "Yes, as recommended" to Q1 to Q7). The card's side, mounted in a real DOM
 * (jsdom): the frame at once (Q3), a ruled-out reason as a sentence (Q1), "trades too" (Q6), the press's own word and
 * answer in the open route's panel with no second read (Q2), and source checks for the one-request press, the busy-hours
 * line taken off (Q6) and the record's Loads cell (finding 8). The rule's side is test_best_option_1117.py.
 *
 * Not covered: the real server's answer, a browser (the session note's local Chrome pictures), live's timing.
 * Every check marked ⭐ fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_best_option_1117.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };

// ---------------- source checks ----------------
const ra = fnSrc("RouteAnalysis");
ok("⭐ SRC Q3: the open route's panel shows the card's frame while it reads (it said 'Loading analysis…' over an empty half panel)",
   ra.includes("{!data && !err && <BestOption best={null} frame routeId={routeId} />}") && !ra.includes(">Loading analysis…</p>"));
// REVERSED 17 Nov 2026 (claude/best-option-wait-line; John: "Yes, drop it"): the line no longer says how long. Since the
// card answers its own route first (PR #317) the wait after a change is a few seconds on live, so "about half a minute
// after a change" was no longer true. It read: the wait says how long.
// REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "Working out the route options…" (it read "Working out the best option…")
ok("⭐ SRC Q3: the wait line is 'Working out the route options…' and no longer says 'half a minute' (the screen and the guide)",
   html.includes('const BO_WAIT = "Working out the route options…";') && !html.includes("Working out the best option") && !/BO_WAIT = "[^"]*half a minute/.test(html)
   && !read("frontend", "help", "index.html").includes("half a minute")
   && read("frontend", "help", "index.html").includes("After a change the card takes a few seconds to work out again."));
ok("⭐ SRC Q2: the press is ONE request with every leg it moves, and its reply's answer goes to the open panel",
   html.includes('legs: legs.join(",") });') && !html.includes("for(const lg of (card ? card.legs")
   && html.includes("setPromoted({ route: rid, text: said, best: j.best || null });")
   && /promoted=\{promoted\}/.test(html) && (html.match(/promoted=\{promoted\}/g) || []).length === 2);
ok("⭐ SRC Q6: the busy-hours line no longer says 'Make primary may suit better' (on R013 it advised Alt 2 under a card naming Alt 1)",
   !html.includes("Make primary may suit better.</span>") && !html.includes("{o.better_all_day && <span"));
ok("⭐ SRC finding 8: the record's Loads cell reads 'N planned', one form for a busy-hours road ('35 of 212 planned')",
   html.includes('data-rc-loads="1">{r.kind === "busy" ? `${grp(Math.round(p.trips))} of ${grp(Math.round(p.of))}` : grp(Math.round(p.trips))} planned</td>'));
ok("⭐ SRC Q7: the record's trip minutes are the rule's halves (min_half), its own rounding to the nearest half",
   html.includes('k === "min" && f.min_half != null ? f.min_half : f[k]'));

{
  const guide = read("frontend", "help", "index.html"), tech = read("frontend", "help", "technical", "index.html");
  const a = guide.indexOf('<li id="ug-best-option">'), li = a > 0 ? guide.slice(a, guide.indexOf("</li>", a)) : "";
  ok("⭐ GUIDE: the user guide's Best option entry says 'measure' (no 'head'), names the roads a ruled-out option adds, 'trades too', and the message under the card",
     // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "clearly better on one measure", "another option is mixed too" (they read "clearly
     // ahead on one measure", "another option trades too"); NARROWED: no "ahead", "behind" or "trade"
     li.includes("clearly better on one measure") && !/\bheads?\b/.test(li) && li.includes("section A lists every stretch")
     && li.includes("another option is mixed too") && !/\b(ahead|behind|trades?|trade-off)\b/.test(li) && li.includes("says so under the card") && !/\/api\/|HERE/.test(li));
  const t = tech.indexOf('id="t2-best-option"'), tl = t > 0 ? tech.slice(t, tech.indexOf("</li>", t)) : "";
  ok("⭐ GUIDE: the technical guide's t2-best-option names added_words, the four-line cut, half_min, _whole, trade_also and promote-alt's legs",
     ["route_best.added_words", "cut_lines", "_sum_lower_h", "route_best.half_min", "route_record._whole", "trade_also",
      "promote-alt?legs=loaded,return", "route_best.card_answer"].every(k => tl.includes(k)));
}

// ---------------- the card in a DOM ----------------
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
const seen = [];
const respond = (j) => Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" },
                                         json: () => Promise.resolve(j), text: () => Promise.resolve(JSON.stringify(j)) });
let ROUTES = {};
w.fetch = (url) => { const u = String(url); seen.push(u);
  for (const [re, j] of Object.entries(ROUTES)) if (new RegExp(re).test(u)) return j === null ? new Promise(() => {}) : respond(j);
  return new Promise(() => {}); };
w.mapboxgl = { Map: function(){ return { on(){}, remove(){} }; } };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
w.ResizeObserver = function(){ this.observe = () => {}; this.disconnect = () => {}; this.unobserve = () => {}; };
w.Element.prototype.scrollIntoView = function(){};
w.matchMedia = (q) => ({ matches: /min-width: 1024px/.test(q), media: q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){} });
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
let loaded = true;
try { w.eval(js); } catch (e) { loaded = false; console.log("app script failed: " + e.message); }
ok("the app's script runs in the DOM", loaded);
const E = w.React.createElement;
const flush = async () => { for (let i = 0; i < 4; i++) await act(async () => { await new Promise(r => setTimeout(r, 0)); }); };
const txt = (el) => (el ? el.textContent : "").replace(/\s+/g, " ").trim();

function mountCard(best, extra){
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const props = Object.assign({ best, routeId: "RX", showAll: false, onAll: () => {}, onFocus: () => {}, onPromote: () => {},
                                promoting: "", busyUses: null }, extra || {});
  if (typeof w.BestOption === "function") act(() => { root.render(E(w.BestOption, props)); });
  return { host, done: () => { act(() => root.unmount()); host.remove(); } };
}

const P = "Artic Tipper (44t)";
const CU = { km: 66.65, drive_min: 70, cycle_min: 104, trips: 5, co2_kg: 57.7, collisions: 39, goods: 4, left_turns: 10,
             cycle_meets: 6, cycle_beside_km: 0.24, places: 7, busy_min: {} };
function opt(alt, o){
  return Object.assign({ alt, label: "Alt " + alt, return_alt: 0, ruled_out: [], added_limits: [], searched: true, heads: {}, parts: {}, n5: false,
    counts: { km: 64.71, drive_min: 66.5, cycle_min: 100.5, trips: 5, co2_kg: 56, busy_min: {}, collisions: 39, goods: 1,
              left_turns: 9, cycle_meets: 4, cycle_beside_km: 0.17, places: 2 },
    pct: { left_turns: -10, cycle_meets: -33, cycle_beside_km: null, places: -71 },
    head_words: { people: "fewer", time: "quicker", busy: "not counted", carbon: "same" },
    part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "fewer" },
    sentences: ["Alt " + alt + " had 39 collisions on it against 39 on the route in use, 2021–2025."] }, o || {});
}
function answer(o){
  return { day: "2026-11-17", checks: {}, route: Object.assign({ route: "R011", answer: "Keep the route in use", option: null, alt: null,
    why: "No other option is clearly better.", trade: null, trade_short: null, trade_also: [], held_back: null, lorry: P,
    lorry_basis: "approved loads", other_lorries: [],
    in_use: { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } },
    counts_in_use: CU, checks: { limits_held: true, community_all_options: true, collision_history: "current" },
    options: [opt(1)], in_use_limits: [] }, o || {}) };
}

// Q3: the frame
{
  const m = mountCard(null, { frame: true });
  const wait = m.host.querySelector("[data-bo-wait]");
  // REVERSED 17 Nov 2026 (claude/best-option-wait-line): the wait words alone, no time
  // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "Route options" and its wait words (they read "Best option", "Working out the best option…")
  ok("⭐ Q3: the frame names the card and shows the wait words ('Route options', 'Working out the route options…')",
     txt(m.host).startsWith("Route options") && txt(wait) === "Working out the route options…", txt(m.host));
  ok("⭐ Q3: the frame has no 'All figures' button (nothing to fold yet)", !m.host.querySelector("button[data-bo-all]"));
  m.done();
  const m2 = mountCard(null);
  ok("Q3: a card re-reading after a change keeps its 'All figures' button with the same wait words",
     !!m2.host.querySelector("button[data-bo-all]") && txt(m2.host.querySelector("[data-bo-wait]")).startsWith("Working out the route options"));
  m2.done();
}

// Q1: a ruled-out reason as a sentence; the rule's words as they are
{
  const R1 = "it adds 7.5 t limits, except for access, on Syston Road, Cossington Lane, Valley Road and unnamed roads";
  const R2 = "it adds 7.5 t limits, except for access, on unnamed roads (both legs)";
  const B = answer({ why: `Every other option is ruled out: Alt 1: ${R2}; Alt 2: ${R1}.`,
                     options: [opt(1, { ruled_out: [R2] }), opt(2, { ruled_out: [R1] })] });
  const m = mountCard(B, { showAll: true });
  const rows = [...m.host.querySelectorAll("[data-bo-row]")].map(txt).join(" | ");
  ok("⭐ Q1: a ruled-out row reads the rule's reason as a sentence (a capital, a full stop)",
     rows.includes("It adds 7.5 t limits, except for access, on Syston Road, Cossington Lane, Valley Road and unnamed roads."), rows);
  ok("Q1: no row on the card is over 40 words (R011's ran to 361)",
     [...m.host.querySelectorAll("[data-bo-row]")].every(r => txt(r).split(" ").length <= 40),
     [...m.host.querySelectorAll("[data-bo-row]")].map(r => txt(r).split(" ").length).join(","));
  m.done();
}

// Q6: trades too
{
  // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the rule's answer "Planner to decide" (it read "A trade-off"), its lines in the new words
  const B = answer({ answer: "Planner to decide", why: "Alt 1: 5 fewer left-hand turns; 8 kg CO₂e more a trip.",
                     trade: "Alt 1: 5 fewer left-hand turns; 8 kg CO₂e more a trip.", trade_short: "Alt 1: fewer cycle routes; more carbon.",
                     trade_also: ["Alt 2"], options: [opt(1, { traded: true }), opt(2)] });
  const m = mountCard(B);
  const also = m.host.querySelector("[data-bo-also]");
  // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): 'Alt 2 is mixed too.' (it read 'Alt 2 trades too: All figures.'); the mark reads 'Mixed'
  ok("⭐ Q6: the card says when another option is mixed too: 'Alt 2 is mixed too.' (six words or fewer)",
     txt(also) === "Alt 2 is mixed too." && txt(also).split(" ").length <= 6 && /Planner to decide.?Mixed/.test(txt(m.host))
     && !/trade|Your call/.test(txt(m.host)), txt(m.host));
  m.done();
  const m2 = mountCard(answer({ answer: "Planner to decide", why: "Alt 1: 5 fewer left-hand turns; 8 kg CO₂e more a trip.",
                                trade_short: "Alt 1: fewer cycle routes; more carbon.", trade_also: ["Alt 2", "Alt 3"], options: [opt(1, { traded: true }), opt(2), opt(3)] }));
  // REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): '2 others are mixed too.' (it read '2 others trade too: All figures.')
  ok("⭐ Q6: two more: '2 others are mixed too.'", txt(m2.host.querySelector("[data-bo-also]")) === "2 others are mixed too.", txt(m2.host));
  m2.done();
  const m3 = mountCard(answer({ answer: "Planner to decide", why: "Alt 1: 5 fewer left-hand turns; 8 kg CO₂e more a trip.",
                                options: [opt(1, { traded: true })] }));
  ok("Q6: no other trade-off, no 'trades too'", !m3.host.querySelector("[data-bo-also]"));
  m3.done();
}

// Q2: the press's word and answer in the open route's panel, with no second read
(async () => {
  const ROW = (alt) => ({ profile: P, alt_index: alt, loaded_km: 40 + alt, return_km: 42, return_estimated: false, loaded_hr: 0.75, return_hr: 0.5,
    load_minutes: 15, unload_minutes: 9, turnaround_hr: 0.4, turnaround_parts: {}, cycle_hr: 1.7, haul_speed_applied: false,
    trips_per_day: 5, tonnes_per_day: 100, tonnes_per_month: 2200, co2_kg_per_trip: 56,
    lorry_day: { limited_by: "shift", trips_without_rules: 5, words: "5 a day", break_minutes: 45 } });
  const SUG = answer({ route: "R050", answer: "Suggested", option: "Alt 1", alt: 1, why: "3.5 min quicker a round trip, with 5 fewer left turns.",
                       options: [opt(1, { chosen: true })] });
  const AFTER = answer({ route: "R050", why: "No other option is clearly better.", options: [opt(1)] });
  ROUTES = { "/routes/R050/analysis$": null, "/routes/R050/best-option$": SUG, "/routes/R050/collision-hours$": { uses: [] } };
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const base = { routeId: "R050", active: true, onFocus: () => {}, onPromote: () => {}, promoting: "", leg: "loaded", wide: true,
                 haulRoads: [], diversions: null, token: "", onHaulChanged: () => {}, originId: "L001", destId: "L003", gateBlockers: [] };
  const render = (p) => act(() => { root.render(E(w.RouteAnalysis, Object.assign({}, base, p))); });
  let okMount = typeof w.RouteAnalysis === "function";
  try { if (okMount) render({ promoted: null }); } catch (e) { okMount = false; }
  await flush();
  ok("⭐ Q3: the panel shows the card's frame while the route's figures are still being read",
     okMount && txt(host.querySelector('[data-best-option="loading"] [data-bo-wait]')).startsWith("Working out the route options")
     && !txt(host).includes("Loading analysis"), txt(host).slice(0, 200));
  // the figures arrive; then a press: promoting, then its reply
  ROUTES["/routes/R050/analysis$"] = { rows: [ROW(0), ROW(1)], planning: { shift_hours_per_day: 10, working_days_per_month: 22, shift_note: "" } };
  if (okMount) { act(() => root.unmount()); }
  const root2 = w.ReactDOM.createRoot(host);
  const render2 = (p) => act(() => { root2.render(E(w.RouteAnalysis, Object.assign({}, base, p))); });
  if (okMount) { render2({ promoted: null }); await flush(); }
  const before = seen.filter(u => /R050\/best-option$/.test(u)).length;
  if (okMount) { render2({ promoted: null, promoting: `${P}|1` }); await flush(); }
  const said = "Alt 1 is now the main route for the Artic Tipper. Not moved: Flatbed.";
  if (okMount) { render2({ promoted: { route: "R050", text: said, best: AFTER }, promoting: `${P}|1` }); await flush();
                 render2({ promoted: { route: "R050", text: said, best: AFTER }, promoting: "" }); await flush(); }
  const doneEl = host.querySelector("[data-bo-done]");
  ok("⭐ Q2: the press's own sentence shows in the open route's panel, under the card, as a status",
     txt(doneEl) === said && doneEl && doneEl.getAttribute("role") === "status"
     && !!host.querySelector('[data-ro="card"] [data-bo-done]'), txt(host).slice(0, 300));
  ok("⭐ Q2: the card shows the press's answer at once (Keep, 'No other option is clearly better.')",
     txt(host.querySelector("[data-bo-why]")).startsWith("No other option is clearly better."), txt(host.querySelector("[data-bo-why]")));
  ok("⭐ Q2: no second read of the answer after the press (the reply carried it)",
     seen.filter(u => /R050\/best-option$/.test(u)).length === before, seen.filter(u => /best-option/.test(u)).length);
  // a press on another route says nothing here; a failed press says why
  if (okMount) { render2({ promoted: { route: "R001", text: "Alt 1 is now the main route for the Artic Tipper.", best: null }, promoting: "" }); await flush(); }
  ok("Q2: a press on another route leaves this panel's sentence as it was", txt(host.querySelector("[data-bo-done]")) === said);
  if (okMount) { render2({ promoted: { route: "R050", text: "Couldn't use this alternative.", best: null, failed: true }, promoting: "" }); await flush(); }
  ok("⭐ Q2: a failed press says so in the panel", host.querySelector('[data-bo-done="failed"]')
     && txt(host.querySelector("[data-bo-done]")) === "Couldn't use this alternative.");
  if (okMount) act(() => root2.unmount());
  host.remove();

  console.log(`\nui_fix_best_option_1117.js: ${pass} passed, ${fail.length} failed`);
  for (const f of fail) console.log("  FAIL " + f);
  console.log(`\n${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.log("crashed: " + (e && e.stack || e)); console.log(`\n${pass} passed, ${fail.length + 1} failed`); process.exit(1); });
