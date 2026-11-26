/* ui_fix_routes_schedule.js — 25 Nov 2026, branch claude/route-options-schedule (the Routes page rethink, cards 4 and 7;
 * John: "Yes, as recommended" to Q12 and Q13 of notes\routes-rethink-mockup-1124). The card's option rows are ONE
 * schedule: the measure, the route in use, the tab's option in the selection tint, the difference with the status shape
 * and the rule's words; a small bar a figure on the row's own scale, the collision bars both grey.
 *
 * The card is fed the RULE's own rows (backend/tests/fixtures/route_rows_1125.json, written by test_route_best §17 from
 * route_best.evaluate() on live's R001 and R003 figures and on stand-in cases: a fictional demo scheme), so the page is
 * checked against what the rule says, not a typed copy. Not covered: a browser (the bars' widths on screen, the 600 px
 * container rule, Dark's colours: the session note's local Chrome pictures), the real server.
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the code before (no schedule: the rows were chips and
 * sentences).
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_routes_schedule.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const rule = read("backend", "route_best.py");
const FX = JSON.parse(read("backend", "tests", "fixtures", "route_rows_1125.json"));
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };

// ---------------- source checks ----------------
const card = fnSrc("BestOption"), sch = fnSrc("BoSchedule"), mk = fnSrc("boMark"), bar = fnSrc("boBar");
ok("⭐ SRC: the card prints the rule's rows through ONE schedule (BoSchedule rows={o.rows})",
   sch.length > 0 && card.includes("<BoSchedule rows={o.rows}"), card.length);
{
  const GONE = ["colRow", "limitsRow", "goodsSent", "busySent", "tripsWords", "boChip", "BO_TONE", "boPct", "BO_STALE", "BO_NO_HISTORY", "BO_HGV", "boNum", ".bo-dash", "bo-dash"];
  ok("⭐ GONE: the card's own row code (colRow, limitsRow, chips, percentages, its stale words, bo-dash) is out of the page",
     GONE.every(g => !html.includes(g)), GONE.filter(g => html.includes(g)).join(", "));
}
ok("⭐ SRC: the schedule decides nothing: no sum, comparison or word of a difference; its mark is the rule's x.mark",
   !/fewer|more|less|longer|quicker|Better|safer|%|the same/.test((sch + mk).replace(/\/\/.*$/gm, ""))
   && mk.includes('x.mark === "ok" || x.mark === "warn"') && sch.includes("{boMark(x)}") && !/RowStatus|rs-ok|rs-warn/.test(sch + mk));
ok("⭐ SRC: a bar is hidden from a screen reader and 86 px at most, on the row's own scale (the larger of the two figures)",
   bar.includes('aria-hidden="true"') && html.includes("const BO_BAR_W = 86;") && bar.includes("Math.round(v / max * BO_BAR_W)")
   && sch.includes("const max = Math.max(Number(x.in_use) || 0, Number(x.option) || 0);"));
ok("⭐ SRC: the route in use's bar is always the light grey; the option's is the dark ink except where the rule says both grey (collisions)",
   sch.includes("boBar(Number(x.in_use), max, true)") && sch.includes('boBar(Number(x.option), max, x.bars === "grey")'));
{
  const css = (sel) => { const i = html.indexOf(sel); return i < 0 ? "" : html.slice(i, html.indexOf("}", i) + 1); };
  ok("⭐ CSS: bars 7 px high with a 3 px corner; option #62656B, in use #A9ABB0; Dark #C9CACE and #6B6E74",
     css(".bo-bar{").includes("height:7px") && css(".bo-bar{").includes("border-radius:3px")
     && css(".bo-sch{").includes("--bo-bar:#62656B") && css(".bo-sch{").includes("--bo-bar-use:#A9ABB0")
     && html.includes('html[data-theme="dark"] .bo-sch{--bo-bar:#C9CACE;--bo-bar-use:#6B6E74;}'));
  ok("⭐ CSS: the option's column is the selection tint (--navy-soft-col), its head the sign blue; no filled cell",
     html.includes(".bo-sch .bo-pick{background:var(--navy-soft-col);}") && html.includes(".bo-sch thead th.bo-pick{color:var(--navy);")
     && !/\.bo-sch[^{]*\{[^}]*background:var\(--(navy|action|ok|warn|red)\)/.test(html));
  ok("⭐ CSS: the marks are shapes in the status words' text colours (a dot for ok, a diamond for a warning), no pill",
     html.includes(".bo-mk-ok{color:var(--ok-text);} .bo-mk-ok i{background:var(--ok-text);}")
     && html.includes(".bo-mk-warn{color:var(--warn-text);} .bo-mk-warn i{background:var(--warn-text);border-radius:0;transform:rotate(45deg)")
     && !/\.bo-mk[^{]*\{[^}]*border-radius:(99|999|9999)px/.test(html));
  ok("⭐ CSS: under 600 px of the card's own width the bars go (a container rule; the card is the container)",
     /@container \(max-width:600px\)\{\.bo-sch \.bo-bar\{display:none;\}/.test(html) && /\.bo-card\{[^}]*container-type:inline-size/.test(html));
}
ok("SRC: the rule names the five marks and its row words (the page has none of them)",
   rule.includes('ROW_MARKS = ("ok", "warn", "none", "plain", "off")') && rule.includes('ROW_NOT_COUNTED = "Not counted yet"')
   && !html.includes('"Not counted yet"') && !html.includes("Not compared: no busy-hour times held"));

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
const E = w.React.createElement;
const hasCard = typeof w.BestOption === "function" && typeof w.BoSchedule === "function";
ok("⭐ the card and the schedule are defined", hasCard);

// the fixture is the rule's route answer; the card also reads the lorry and the line in use, which the fixture leaves out
const IN_USE = { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } };
const route = (k, o) => Object.assign({ lorry: "Artic Tipper (44t)", lorry_basis: "approved loads", other_lorries: [], in_use: IN_USE,
                                        why: "", trade_short: "", trade_also: "", held_back: null }, FX[k],
                                      { route: FX[k].route || k, checks: FX[k].checks || { limits_held: true, community_all_options: true, collision_history: "current" } }, o || {});
function mount(r, extra){
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const props = Object.assign({ best: { day: "2026-11-25", checks: {}, route: r }, routeId: r.route, showAll: false, onAll: () => {}, onFocus: () => {},
                                onPromote: () => {}, promoting: "", busyUses: null }, extra || {});
  if (hasCard) act(() => { root.render(E(w.BestOption, props)); });
  return { host, done: () => { act(() => root.unmount()); host.remove(); } };
}
const row = (host, k) => host.querySelector(`tr[data-bo-row="${k}"]`);
const cells = (tr) => tr ? [...tr.children].map(c => c.textContent) : [];
const click = (el) => act(() => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
const optOf = (k, alt) => FX[k].options.find(o => o.alt === alt);

if (hasCard) {
  // live's R001 (L001): Planner to decide, Alt 1 — the rows as drawn on card 4
  const m = mount(route("L001"));
  const t = m.host.querySelector("table.bo-sch");
  ok("⭐ TABLE: one real table with a caption, four column heads (scope=col) and a row head (scope=row) a measure",
     t && t.querySelector("caption.sr-only") && t.querySelector("caption").textContent.endsWith("against the route in use")
     && [...t.querySelectorAll("thead th[scope=col]")].map(th => th.textContent).join("|").match(/^A round trip\|In use\|.+\|Against the route in use$/)
     && t.querySelectorAll("tbody th[scope=row]").length === optOf("L001", 1).rows.length, t && t.outerHTML.slice(0, 300));
  ok("⭐ ROWS: the rule's rows, in its order, one table row each",
     t && [...t.querySelectorAll("tbody tr")].map(tr => tr.getAttribute("data-bo-row")).join(",") === optOf("L001", 1).rows.map(x => x.key).join(","));
  ok("⭐ R001: the words as drawn: 13 more, 31 % fewer, 10 % less, 28 % more, 23.5 min longer, 1 fewer, 15.6 kg more",
     [["left_turns", "13 more"], ["cycle_meets", "31 % fewer"], ["cycle_beside_km", "10 % less"], ["places", "28 % more"], ["round_trip", "23.5 min longer"],
      ["trips", "1 fewer"], ["carbon", "15.6 kg more"]].every(([k, wd]) => cells(row(m.host, k))[3] === wd),
     ["left_turns", "cycle_meets", "places", "round_trip", "carbon"].map(k => cells(row(m.host, k)).join("/")).join(" | "));
  ok("⭐ R001: both figures printed as the rule writes them (165 / 97 collisions, 120.3 / 143.8 min, 15.81 / 14.26 km)",
     cells(row(m.host, "collisions")).slice(1, 3).join("/") === "165/97" && cells(row(m.host, "round_trip")).slice(1, 3).join("/") === "120.3/143.8"
     && cells(row(m.host, "cycle_beside_km")).slice(1, 3).join("/") === "15.81/14.26");
  ok("⭐ MARKS: an ok row is a dot AND its words in the ok colour class; a warning a diamond AND its words; the shape hidden from a reader",
     row(m.host, "cycle_meets").querySelector(".bo-mk.bo-mk-ok[data-bo-mark=ok] > i[aria-hidden=true]")
     && row(m.host, "left_turns").querySelector(".bo-mk.bo-mk-warn[data-bo-mark=warn] > i[aria-hidden=true]")
     && row(m.host, "left_turns").querySelector(".bo-mk").textContent === "13 more");
  {
    const col = row(m.host, "collisions"), hgv = row(m.host, "goods");
    ok("⭐ COLLISIONS: counts only: both bars grey, no shape, no tint word, the rule's plain 'fewer'; the HGV row a sub-row",
       col.querySelectorAll(".bo-bar.bo-bar-use").length === 2 && !col.querySelector(".bo-mk,i") && col.querySelector(".bo-mk-plain").textContent === "fewer"
       && !/%|Better|safer/.test(col.textContent) && hgv.querySelector("th.bo-sub") && hgv.querySelectorAll(".bo-bar.bo-bar-use").length === 2
       && hgv.querySelector("th").textContent === "involving an HGV", cells(col).join("/"));
  }
  {
    const bars = [...m.host.querySelectorAll(".bo-bar")];
    const wpx = (tr, i) => parseInt(tr.querySelectorAll(".bo-bar")[i].style.width, 10);
    const rt = row(m.host, "round_trip"), lt = row(m.host, "left_turns");
    ok("⭐ BARS: every bar aria-hidden; the larger figure of a row is 86 px, the other to scale (143.8 → 86, 120.3 → 72; 17 → 86, 4 → 20)",
       bars.length > 0 && bars.every(b => b.getAttribute("aria-hidden") === "true")
       && wpx(rt, 1) === 86 && wpx(rt, 0) === 72 && wpx(lt, 1) === 86 && wpx(lt, 0) === 20,
       [wpx(rt, 0), wpx(rt, 1), wpx(lt, 0), wpx(lt, 1)].join(","));
    ok("⭐ BARS: the route in use's bar grey, the option's ink on a measure that is not a collision count",
       rt.querySelectorAll(".bo-bar")[0].classList.contains("bo-bar-use") && !rt.querySelectorAll(".bo-bar")[1].classList.contains("bo-bar-use"));
  }
  ok("⭐ TINT: the option's column (head and cells) carries bo-pick; no other cell does",
     m.host.querySelector("thead th.bo-pick") && [...m.host.querySelectorAll("tbody tr")].every(tr => tr.querySelectorAll(".bo-pick").length === (tr.querySelector("td.bo-none") ? 0 : 1)));
  ok("⭐ NOT COMPARED: the busy row and the limits row are one cell across, in the rule's words, with no bar",
     row(m.host, "busy").querySelector("td.bo-none[colspan='3']").textContent === "Not compared: no busy-hour times held for Alt 1."
     && row(m.host, "limits").querySelector("td.bo-none").textContent === "None" && !row(m.host, "busy").querySelector(".bo-bar"));
  ok("NO OLD PARTS: no 'People' heading, no chip, no pill, no sentence row in the schedule",
     !/People/.test(t.textContent) && !t.querySelector(".row-st,.rs-ok,.rs-warn,.rs-none,.al-chip") && !t.querySelector("p")
     && [...t.querySelectorAll("td")].every(td => td.textContent.split(/\s+/).length <= 15));
  m.done();

  // R003 (L003): two options; a tab picks the other, its rows follow
  // the tabs are the Routes page's: its own pick (pick / onPick), so the harness holds the pick as the page does
  let picked = [];
  const m1 = mount(route("L003"), { pick: 1, onPick: (l, a) => picked.push(a) });
  const tab2 = m1.host.querySelector("button[data-bo-tab='2']");
  ok("TABS: R003's card on Alt 1 shows Alt 1's rows (carbon 1.6 kg less)", cells(row(m1.host, "carbon"))[3] === "1.6 kg less" && !!tab2);
  if (tab2) click(tab2);
  ok("TABS: the tab asks the page for Alt 2", picked.join(",") === "2");
  m1.done();
  const m2 = mount(route("L003"), { pick: 2, onPick: () => {} });
  ok("⭐ TABS: Alt 2's tab gives Alt 2's own rows (left-hand turns 22 % fewer, carbon 2.1 kg less) and its name heads the tinted column",
     cells(row(m2.host, "left_turns"))[3] === "22 % fewer" && cells(row(m2.host, "carbon"))[3] === "2.1 kg less"
     && /Alt 2/.test(m2.host.querySelector("thead th.bo-pick").textContent), cells(row(m2.host, "carbon")).join("/"));
  m2.done();

  // R1n: not counted yet, no limits held
  const m3 = mount(route("R1n"));
  ok("⭐ NOT COUNTED YET: the cycle and community rows read the rule's 'Not counted yet' in grey words, no shape",
     ["left_turns", "places"].every(k => cells(row(m3.host, k))[3] === "Not counted yet" && row(m3.host, k).querySelector(".bo-mk-plain.bo-mk-off") && !row(m3.host, k).querySelector("i"))
     && m3.host.querySelector("[data-bo-not-counted=community]"));
  ok("⭐ NO LIMITS HELD: the limits row says 'Not checked: no road limits are held.' across the row",
     row(m3.host, "limits").querySelector("td.bo-none").textContent === "Not checked: no road limits are held.");
  m3.done();

  // R1rr: collision history out of date; Alt 1 ruled out
  const m4 = mount(route("R1rr"), { pick: 2, onPick: () => {} });
  ok("⭐ OUT OF DATE: one collision row in the rule's words across it, no counts, no HGV row",
     row(m4.host, "collisions") && row(m4.host, "collisions").querySelector("td.bo-none").textContent === "Collision history out of date. Fetch it again on Config → Map and bulletin."
     && !row(m4.host, "goods") && !row(m4.host, "collisions").querySelector(".bo-bar"), m4.host.textContent.slice(0, 300));
  m4.done();
  const m5 = mount(route("R1rr"), { pick: 1, onPick: () => {} });
  ok("⭐ RULED OUT: a ruled-out option keeps its 'Ruled out' row and shows no schedule",
     /Ruled out/.test(m5.host.textContent) && !m5.host.querySelector("table.bo-sch"), m5.host.textContent.slice(0, 300));
  m5.done();
}

console.log(`ui_fix_routes_schedule.js: ${pass} passed, ${fail.length} failed`);
for (const f of fail) console.log("  FAIL: " + f);
process.exit(fail.length ? 1 : 0);
