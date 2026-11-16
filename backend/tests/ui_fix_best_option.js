/* ui_fix_best_option.js — 16 Nov 2026, branch claude/route-best-option (step 1b of the best option; John's yes to the third
 * draft, notes\route-best-option-mockup-1116, "Yes, as recommended" to Q1-Q9). The "Best option" card on Data -> Routes,
 * mounted in a real DOM (jsdom) for each answer and each not-counted state, plus source checks: the staff read, the
 * reversal of "Counts only: nothing is scored or ranked", no colour / "Better" / "safer" on a collision count.
 *
 * The answers fed to the card are route_best.evaluate()'s shape with live's figures of 16 Nov (examples.md: R050, R003,
 * R021, R027, R013; a fictional demo scheme). Not covered here: the real server's answer (smoke: http_smoke and
 * smoke_reviewer_wall reach the endpoint), a browser (the session note's local Chrome check), Postgres.
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the code before (no BestOption, no endpoint).
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_best_option.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const guide = read("frontend", "help", "index.html");
const mainPy = read("backend", "main.py");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;

// ---------------- source checks ----------------
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };
const bo = fnSrc("BestOption");
ok("⭐ SRC: the card component exists and reads /api/routes/<id>/best-option (never the admin table)",
   bo.length > 0 && html.includes("/routes/${encodeURIComponent(routeId)}/best-option`") && !html.includes("route-options/best"));
ok("⭐ SRC: 'Counts only: nothing is scored or ranked' is GONE from the app and the user guide's Routes section (John's Q1, 16 Nov)",
   !html.includes("Counts only: nothing is scored or ranked") && !guide.includes("nothing is scored or ranked"));
{
  const col = (bo.match(/const colRow = [\s\S]*?\n  \};/) || [""])[0];
  ok("⭐ SRC: a collision row never carries a status tint: its code names no rs-ok / rs-warn / rs-bad and no tone but none",
     col.length > 0 && !/rs-(ok|warn|bad)|tone="(ok|warn|bad)"/.test(col) && col.includes("bo-dash"));
}
ok("⭐ SRC: the card says no 'Better', 'safer', 'risk', 'rate' or 'ratio', and no '%' next to a collision count",
   bo.length > 0 && !/\b(Better|better|safer|Safer|risk|ratio)\b/.test(bo) && !/collisions?[^"`\n]{0,40}%/.test(bo));
ok("⭐ SRC: no Make primary on a trade-off or a diverted route (Q2, Q4): only on a Suggested answer with no diversion in use",
   bo.includes('const canPromote = r.answer === "Suggested" && o && onPromote && !div;'));
ok("⭐ SRC: the card's Make primary moves the card's lorry on both legs only where the option has its own way back, and the message names the lorries not moved (Q3)",
   bo.includes('legs: ownWayBack ? ["loaded", "return"] : ["loaded"]') && html.includes("for(const lg of (card ? card.legs : [oneLeg(leg || showLeg)])){")
   && html.includes("is now the main route for the ${vehShort(profile)}.${card.others ? ` Not moved: ${card.others}.` : \"\"} Routing again puts the original order back."));
ok("⭐ SRC: the options table folds under 'All figures', closed each time a row opens (Q6); a route with no other option keeps it open",
   html.includes("const [showAll, setShowAll] = useState(false);") && html.includes("setBest(null); setShowAll(false);")
   && html.includes("{(showAll || (best && best.route && !(best.route.options || []).length)) && <>"));
ok("⭐ SRC: the busy-hours offer and its 'in use' lines stay outside the fold (Q5)",
   (() => { const a = html.indexOf("{(showAll || (best && best.route"); const z = html.indexOf("</>}", a); const b = html.indexOf("data-busy-hours={o.alt}", a); return a > 0 && z > a && b > z; })());
ok("⭐ SRC: the 'i' box: at most 30 words and a user-guide link (R1)",
   TRY(() => { const m = html.match(/"routes\.best": \{ title: "Best option", text: "([^"]+)", guide: "ug-best-option" \}/); return m && m[1].split(/\s+/).length <= 30; }));
{
  // every fixed sentence the card writes itself, 25 words or fewer (R1)
  const own = ["Working out the best option…", "Not suggested yet: the collision history is out of date.", "Every other option is ruled out.",
               "Collision history out of date. Fetch it again on Config → Map and bulletin.",
               "Collisions are not compared: the collision history has not been fetched.",
               "Cycle routes and community places are shown, not counted: they have not been fetched along every option yet.",
               "No road limits are held."];
  ok("⭐ SRC: the card's own fixed sentences are in it and each is 25 words or fewer",
     own.every(s => html.includes(s) && s.split(/\s+/).length <= 25), own.filter(s => !html.includes(s)).join(" | "));
}
{
  const ga = mainPy.indexOf("def _gate_arrivals_build("), ep = mainPy.indexOf('@app.get("/api/routes/{route_id}/best-option")');
  const body = ep > 0 ? mainPy.slice(ep, mainPy.indexOf("\n@app.", ep + 10)) : "";
  ok("⭐ SRC: the staff read: after _gate_arrivals_build, any staff login (_require_access), one kept build of the rule over every route (Q8), 404 for an unknown route",
     ga > 0 && ep > ga && body.includes("acc = _require_access()")
     && body.includes('_staff_json("route-options/best", {"day": d.isoformat()}, lambda: route_best.table(d), acc)')
     && body.includes('raise HTTPException(404, "no such route")'));
}
ok("⭐ GUIDE: the user guide's Routes section has the Best option entry, names the three answers, no supplier and no endpoint",
   TRY(() => { const a = guide.indexOf('<li id="ug-best-option">'); const li = guide.slice(a, guide.indexOf("</li>", a));
               return a > 0 && li.includes("<strong>Suggested</strong>") && li.includes("<strong>A trade-off</strong>")
                 && li.includes("<strong>Keep the route in use</strong>") && !/HERE|\/api\/|safer|Better/.test(li); }));

// ---------------- the card in a DOM ----------------
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.mapboxgl = { Map: function(){ return { on(){}, remove(){} }; } };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
let loaded = true;
try { w.eval(js); } catch (e) { loaded = false; console.log("app script failed: " + e.message); }
ok("the app's script runs in the DOM", loaded);
const hasCard = typeof w.BestOption === "function";
ok("⭐ the card component is defined", hasCard);

const E = w.React.createElement;
function mount(best, extra){
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const calls = [];
  const props = Object.assign({ best, routeId: "RX", showAll: false, onAll: () => calls.push(["all"]), onFocus: (p, a) => calls.push(["focus", p, a]),
                                onPromote: (...a) => calls.push(["promote", ...a]), promoting: "", busyUses: null }, extra || {});
  if (hasCard) act(() => { root.render(E(w.BestOption, props)); });
  return { host, calls, text: () => host.textContent.replace(/\s+/g, " "), done: () => { act(() => root.unmount()); host.remove(); } };
}
const btnText = (host, t) => [...host.querySelectorAll("button")].find(b => b.textContent.trim() === t);
const row = (host, k) => host.querySelector(`[data-bo-row="${k}"]`);
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });

// live's R050 (examples.md, 16 Nov 20:27 UTC): Suggested Alt 1, Artic Tipper; collisions 39 / 39, goods 1 / 4
const CU = (o) => Object.assign({ km: 66.65, drive_min: 70, cycle_min: 104, trips: 5, co2_kg: 57.7, collisions: 39, goods: 4,
                                  left_turns: 10, cycle_meets: 6, cycle_beside_km: 0.24, places: 7, busy_min: {} }, o || {});
function opt(alt, o){
  return Object.assign({ alt, label: "Alt " + alt, return_alt: 0, ruled_out: [], added_limits: [], searched: true,
    heads: {}, parts: {}, n5: false,
    counts: { km: 64.71, drive_min: 66.5, cycle_min: 100.5, trips: 5, co2_kg: 56, busy_min: {}, collisions: 39, goods: 1,
              left_turns: 9, cycle_meets: 4, cycle_beside_km: 0.17, places: 2 },
    pct: { left_turns: -10, cycle_meets: -33, cycle_beside_km: null, places: -71 },
    head_words: { people: "fewer", time: "quicker", busy: "not counted", carbon: "same" },
    part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "fewer" },
    sentences: ["Alt " + alt + " had 39 collisions on it against 39 on the route in use, 2021–2025.",
                "Alt " + alt + " had 1 collision involving a goods vehicle over 3.5 t on it against 4 on the route in use, 2021–2025.",
                "A round trip makes 9 left turns against 10 (10 % fewer), meets a cycle route 4 times against 6 (33 % fewer) and runs 0.17 km beside one against 0.24 km.",
                "Carbon is 56 kg CO2e a trip against 57.7 kg."] }, o || {});
}
function route(o){
  return Object.assign({ route: "R050", answer: "Suggested", option: "Alt 1", alt: 1,
    why: "4 min quicker a round trip, with 2 fewer cycle routes met and 5 fewer schools, hospitals and health centres passed.",
    trade: null, held_back: null, lorry: "Artic Tipper (44t)", lorry_basis: "approved loads",
    other_lorries: ["Artic Flatbed (44t)", "Truck mixer 6 m³ (26t)", "Truck mixer 8 m³ (32t)"],
    in_use: { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } },
    counts_in_use: CU(), checks: { limits_held: true, community_all_options: true, collision_history: "current" } }, o || {});
}
const B = (r) => ({ day: "2026-11-16", checks: {}, route: r });
const noTint = (host) => ["collisions", "goods"].every(k => { const el = row(host, k); return el && !el.querySelector(".rs-ok,.rs-warn,.rs-bad") && !/Better|safer/.test(el.textContent); });

if (hasCard) {
  // 1. Suggested (R050)
  {
    const r = route(); const a = opt(1, { chosen: true }); r.options = [a, opt(2, { heads: {}, head_words: {}, part_words: {} })];
    const m = mount(B(r)); const t = m.text();
    ok("⭐ SUGGESTED: the answer, its chip and the rule's why as returned", m.host.querySelector('[data-best-option="Suggested"]')
       && /Alt 1.?Suggested/.test(t) && t.includes(r.why), t);
    ok("⭐ SUGGESTED: the lorry at the top and at the foot, in the app's short names; the others named (no 'Truck')",
       t.includes("Best option · Tipper (44t)") && t.includes("For the Tipper (44t), the lorry most approved loads use.")
       && t.includes("Not for: Flatbed (44t), Concrete mixer 6 m³ (26t), Concrete mixer 8 m³ (32t).") && !/Truck/.test(t), t);
    ok("⭐ PEOPLE (Q1 A): a row for each part; the collision rows are the rule's sentences with a dash and no tint",
       row(m.host, "collisions").textContent.includes("Alt 1 had 39 collisions on it against 39 on the route in use, 2021–2025.")
       && row(m.host, "goods").textContent.includes("Alt 1 had 1 collision involving a goods vehicle over 3.5 t on it against 4")
       && row(m.host, "collisions").querySelector(".bo-dash") && noTint(m.host));
    ok("⭐ PEOPLE: cycle routes and places each a chip with their counts and percentages; no blended figure",
       row(m.host, "cycle").textContent.includes("Left turns 9 against 10 (10 % fewer) · met 4 against 6 (33 % fewer) · beside 0.17 km against 0.24")
       && row(m.host, "cycle").querySelector(".rs-ok") && row(m.host, "places").textContent.includes("2 against 7 (71 % fewer)")
       && !/exposure/i.test(t), row(m.host, "cycle").textContent);
    ok("HEADS: Time quicker with trips; Busy hours not counted said plainly; Carbon same; Limits none added",
       row(m.host, "Time").textContent.includes("100.5 min a round trip · 104 now · 5 trips a day either way")
       && row(m.host, "Busy hours").textContent.includes("No busy-hour times held for Alt 1.")
       && row(m.host, "Carbon").textContent.includes("56 kg CO₂e a trip · 57.7 now") && row(m.host, "Limits").textContent.includes("None added"));
    const mp = btnText(m.host, "Make Alt 1 primary");
    ok("⭐ MAKE PRIMARY: an outline button on a Suggested card (btn-sec, never a filled action)", mp && mp.className === "btn-sec" && !mp.getAttribute("style"));
    click(mp);
    const call = m.calls.find(c => c[0] === "promote");
    ok("⭐ MAKE PRIMARY: it moves the card's lorry, loaded leg only where the option comes back on the main route, naming the others",
       call && call[1] === "Artic Tipper (44t)" && call[2] === 1 && call[3] === "loaded" && JSON.stringify(call[4].legs) === '["loaded"]'
       && call[4].others === "Flatbed (44t), both concrete mixers", JSON.stringify(call));
    click(btnText(m.host, "Show Alt 1 on map"));
    ok("SHOW ON MAP: draws the option for the card's lorry", m.calls.some(c => c[0] === "focus" && c[1] === "Artic Tipper (44t)" && c[2] === 1));
    click(m.host.querySelector("button[data-bo-all]"));
    ok("ALL FIGURES: the fold's button calls its toggle and says it is closed", m.calls.some(c => c[0] === "all")
       && m.host.querySelector("button[data-bo-all]").getAttribute("aria-expanded") === "false");
    m.done();
    const r2 = route(); r2.options = [opt(1, { chosen: true, return_alt: 1 })];
    const m2 = mount(B(r2)); click(btnText(m2.host, "Make Alt 1 primary"));
    const c2 = m2.calls.find(c => c[0] === "promote");
    ok("⭐ MAKE PRIMARY: both legs where the option has its own way back (Q3)", c2 && JSON.stringify(c2[4].legs) === '["loaded","return"]');
    m2.done();
    const m3 = mount(B(route({ options: [opt(1, { chosen: true })] })), { onPromote: null });
    ok("MAKE PRIMARY: none when the caller may not change routes (not an admin login, or the route not picked)", !btnText(m3.host, "Make Alt 1 primary"));
    m3.done();
  }
  // 2. A trade-off (R003): no pick, no Make primary; the long trade line is never shown (Q7), the short one when the rule gives it
  {
    const LONG = "Alt 2 has 2 fewer left turns, 1.32 km less beside a cycle route and 2.1 kg CO2e less a trip, but 3 more schools, hospitals and health centres passed and it is a shorter road that takes longer.";
    const t2 = opt(2, { traded: true, n5: true, counts: { km: 12.84, drive_min: 21.4, cycle_min: 82.4, trips: 6, co2_kg: 7.5, busy_min: {}, collisions: 26, goods: 0,
                        left_turns: 7, cycle_meets: 7, cycle_beside_km: 3.38, places: 9 },
                        pct: { left_turns: -22, cycle_meets: 0, cycle_beside_km: -28, places: 50 },
                        head_words: { people: "mixed", time: "same", busy: "not counted", carbon: "less" },
                        part_words: { collisions: "same", goods: "same", cycle: "fewer", community: "more" },
                        sentences: ["Alt 2 had 26 collisions on it against 23 on the route in use, 2021–2025.", "Alt 2 had 0 collisions involving a goods vehicle over 3.5 t on it against 0 on the route in use, 2021–2025."] });
    const r = route({ route: "R003", answer: "A trade-off", option: null, alt: null, why: LONG, trade: LONG, lorry: "Artic Flatbed (44t)",
                      other_lorries: ["Artic Tipper (44t)"], counts_in_use: CU({ cycle_min: 81.4, trips: 6, co2_kg: 9.6, collisions: 23, goods: 0, left_turns: 9, cycle_meets: 7, cycle_beside_km: 4.7, places: 6 }),
                      options: [opt(1), t2] });
    const m = mount(B(r)); const t = m.text();
    ok("⭐ TRADE-OFF: 'A trade-off · Your call', the traded option's heads, and NO Make primary (Q2)",
       /A trade-off.?Your call/.test(t) && m.host.querySelector('[data-bo-option="Alt 2"]') && ![...m.host.querySelectorAll("button")].some(b => /primary/.test(b.textContent)), t);
    ok("⭐ TRADE-OFF: the rule's long trade line (over 25 words) is not on the card (Q7)", !t.includes(LONG) && !m.host.querySelector("[data-bo-why]"));
    ok("TRADE-OFF: places more is a warn chip with its percentage; Time says 'a shorter road that takes longer'; collisions still untinted",
       row(m.host, "places").querySelector(".rs-warn") && row(m.host, "places").textContent.includes("9 against 6 (50 % more)")
       && row(m.host, "Time").textContent.includes("a shorter road that takes longer") && noTint(m.host)
       && row(m.host, "cycle").textContent.includes("met 7 against 7 ·"), row(m.host, "cycle").textContent);
    m.done();
    const SHORT = "Alt 2 is ahead on cycle routes and carbon, behind on places and time.";
    const m2 = mount(B(Object.assign({}, r, { trade_short: SHORT })));
    const m0 = mount(B(Object.assign({}, r, { trade_short: null })));
    ok("TRADE-OFF: trade_short null (the field's agreed shape) gives no why line, never the long trade", !m0.host.querySelector("[data-bo-why]") && !m0.text().includes(LONG));
    m0.done();
    ok("TRADE-OFF: the rule's short trade line is the why when it gives one", m2.host.querySelector("[data-bo-why]") && m2.host.querySelector("[data-bo-why]").textContent === SHORT);
    m2.done();
  }
  // 3. Keep: every other option ruled out (R021), no other option (R009), nothing clearly ahead
  {
    const REASON = "it meets 1 road limit below this lorry that the route in use does not: Weight limit 7.5 t (both legs)";
    const r = route({ route: "R021", answer: "Keep the route in use", option: null, alt: null,
                      why: "Every other option is ruled out: Alt 1: " + REASON + "; Alt 2: " + REASON + ".",
                      options: [opt(1, { ruled_out: [REASON] }), opt(2, { ruled_out: [REASON] })] });
    const m = mount(B(r)); const t = m.text();
    ok("⭐ KEEP · RULED OUT: 'Every other option is ruled out.' and one row an option with its own reasons, word for word",
       /Keep the route in use.?No change/.test(t) && m.host.querySelector("[data-bo-why]").textContent === "Every other option is ruled out."
       && /^Alt 1.?Ruled out/.test(row(m.host, "out-1").textContent) && row(m.host, "out-1").textContent.endsWith(REASON) && row(m.host, "out-2").textContent.includes(REASON)
       && !m.host.querySelector("[data-bo-option]") && ![...m.host.querySelectorAll("button")].some(b => /primary/.test(b.textContent)), t);
    m.done();
    const z = "it crosses A47 at the new Tilton junction: HGV diversion while the junction is built, closed until 17 Dec 2027 (loaded leg)";
    const m1 = mount(B(route({ answer: "Keep the route in use", options: [opt(1, { ruled_out: [z, z] })] })));
    ok("KEEP · RULED OUT: a reason said twice is shown once; a zone name with a colon is kept whole (built from the list, never by splitting the why)",
       row(m1.host, "out-1").textContent.split(z).length === 2);
    m1.done();
    const m2 = mount(B(route({ route: "R009", answer: "Keep the route in use", option: null, why: "No other option is stored for this lorry.", options: [] })));
    ok("⭐ KEEP · NO OTHER OPTION: the rule's sentence, no heads, no buttons, no fold to open", m2.text().includes("No other option is stored for this lorry.")
       && !m2.host.querySelector(".bo-heads") && !m2.host.querySelector("button[data-bo-all]") && !m2.host.querySelector("button.btn-sec"));
    m2.done();
    const m3 = mount(B(route({ answer: "Keep the route in use", option: null, why: "No other option is clearly ahead on any head.", options: [opt(1)] })));
    ok("KEEP · NOTHING CLEARLY AHEAD: the rule's sentence and the fold", m3.text().includes("No other option is clearly ahead on any head.") && m3.host.querySelector("button[data-bo-all]"));
    m3.done();
  }
  // 4. The not-counted states
  {
    const a = opt(1, { part_words: { collisions: "same", goods: "same", cycle: "not counted", community: "not counted" } });
    const m = mount(B(route({ options: [Object.assign(a, { chosen: true })], checks: { limits_held: true, community_all_options: false, collision_history: "current" } })));
    ok("⭐ NOT COUNTED YET: cycle routes and places read 'Not counted yet', greyed, with the rule's sentence",
       row(m.host, "cycle").textContent.includes("Not counted yet") && row(m.host, "cycle").querySelector(".bo-grey")
       && row(m.host, "places").textContent.includes("Not counted yet")
       && m.host.querySelector('[data-bo-not-counted="community"]').textContent === "Cycle routes and community places are shown, not counted: they have not been fetched along every option yet.");
    m.done();
    const SENT = "A round trip makes 9 left turns against 10.";
    const held = opt(1, { part_words: { collisions: "not counted", goods: "not counted", cycle: "fewer", community: "fewer" }, sentences: [SENT] });
    const r = route({ answer: "Keep the route in use", option: null, held_back: "Collision history out of date: …", sentences: [SENT], options: [held],
                      checks: { limits_held: true, community_all_options: true, collision_history: "out_of_date" } });
    const m2 = mount(B(r)); const t2 = m2.text();
    ok("⭐ OUT OF DATE: 'Not suggested yet: the collision history is out of date.'; both collision rows a grey 'Not counted' chip and the short words (Q7)",
       m2.host.querySelector("[data-bo-why]").textContent === "Not suggested yet: the collision history is out of date."
       && ["collisions", "goods"].every(k => row(m2.host, k).textContent.includes("Not counted") && row(m2.host, k).querySelector(".rs-none")
                                              && row(m2.host, k).textContent.includes("Collision history out of date. Fetch it again on Config → Map and bulletin."))
       && noTint(m2.host) && !t2.includes("Collision history out of date: …"), t2);
    m2.done();
    const m3 = mount(B(route({ options: [Object.assign(opt(1), { chosen: true })], checks: { limits_held: true, community_all_options: true, collision_history: "not_fetched" } })));
    ok("NEVER FETCHED: the collision rows say the history has not been fetched",
       row(m3.host, "collisions").textContent.includes("Collisions are not compared: the collision history has not been fetched."));
    m3.done();
    const m4 = mount(B(route({ answer: "Keep the route in use", option: null, held_back: "No road limits are held, so no other option could be checked against them.",
                              sentences: opt(1).sentences, options: [opt(1)], checks: { limits_held: false, community_all_options: true, collision_history: "current" } })));
    ok("⭐ NO LIMITS HELD: 'Not checked · No road limits are held.' and the rule's held-back words",
       row(m4.host, "Limits").textContent.includes("Not checked") && row(m4.host, "Limits").textContent.includes("No road limits are held.")
       && m4.host.querySelector("[data-bo-why]").textContent === "Not suggested yet: No road limits are held, so no other option could be checked against them.");
    m4.done();
  }
  // 5. The route in use is not the main route: a diversion (R027), a busy-hours road (R013), a limit on the line in use (Q9)
  {
    const r = route({ route: "R027", options: [Object.assign(opt(1), { chosen: true })],
      in_use: { loaded: { alt: 2, label: "Alt 2", why: "diversion", status: "in_use", until: "2027-12-17" }, return: { alt: 2, label: "Alt 2", why: "diversion", status: "in_use", until: "2027-12-17" } } });
    const m = mount(B(r));
    ok("⭐ DIVERSION: 'In use: Alt 2, the diversion, until 17 Dec 2027. Compared with it.' and no Make primary even on a suggestion (Q4)",
       m.host.querySelector('[data-bo-in-use="diversion"]').textContent === "In use: Alt 2, the diversion, until 17 Dec 2027. Compared with it."
       && !btnText(m.host, "Make Alt 1 primary"));
    m.done();
    const m2 = mount(B(route({ options: [Object.assign(opt(1), { chosen: true })] })), { busyUses: [{ alt: 2, from: "16:00", to: "19:00", status: "in_use" }, { alt: 1, from: "07:00", to: "09:00", status: "stopped" }] });
    ok("⭐ BUSY HOURS: 'Busy hours: Alt 2 is in use on weekdays 16:00–19:00.' (a stopped use is not said)",
       m2.host.querySelector('[data-bo-in-use="busy"]').textContent === "Busy hours: Alt 2 is in use on weekdays 16:00–19:00." && m2.host.querySelectorAll('[data-bo-in-use="busy"]').length === 1);
    m2.done();
    const m3 = mount(B(route({ options: [opt(1)], answer: "Keep the route in use", why: "No other option is clearly ahead on any head.",
                               in_use_limits: [{ words: "The diversion in use meets a 7.5 t limit below this lorry.", legs: "both" }] })));
    ok("Q9: a limit on the line in use, as the rule words it, is one grey line on the card",
       m3.host.querySelector("[data-bo-in-use-limit]") && m3.host.querySelector("[data-bo-in-use-limit]").textContent === "The diversion in use meets a 7.5 t limit below this lorry.");
    m3.done();
    const m4 = mount(B(route({ options: [Object.assign(opt(1), { chosen: true })], in_use_limits: [], trade_short: null })));
    ok("Q9: an empty in_use_limits list (the rule's 'none') draws no line; trade_short null on a Suggested answer leaves the rule's why",
       !m4.host.querySelector("[data-bo-in-use-limit]") && m4.host.querySelector("[data-bo-why]") && m4.host.querySelector("[data-bo-why]").textContent === route().why);
    m4.done();
  }
  // 6. Loading, and a failed read
  {
    const m = mount(null);
    ok("⭐ LOADING: 'Working out the best option…' with the fold's button usable (Q8)", m.text().includes("Working out the best option…") && m.host.querySelector("button[data-bo-all]"));
    m.done();
    const m2 = mount(false);
    ok("FAILED READ: no card, only the fold's button (the table stays reachable)", !m2.host.querySelector(".bo-card") && m2.host.querySelector("button[data-bo-all]"));
    m2.done();
  }
}

console.log(`ui_fix_best_option.js: ${pass} passed, ${fail.length} failed`);
for (const f of fail) console.log("  FAIL: " + f);
process.exit(fail.length ? 1 : 0);
