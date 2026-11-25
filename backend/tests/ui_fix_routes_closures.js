/* ui_fix_routes_closures.js — 25 Nov 2026, branch claude/route-closures-line (the Routes page rethink, card 3; John's
 * "Yes, as recommended" to Q5 and Q6 of notes\routes-rethink-mockup-1124). The rule's closure lines (route_best.closures,
 * test_route_closures.py) on the Route options card and on the Routes map:
 *  - the card: margin lines at the top, above the answer (a 2 px ink rule, the status shape and the head, then the rule's
 *    name · dates · what the diversion does); a diamond in force, a ring planned; at most two, then "and N more"; they
 *    REPLACE "In use: …, the diversion, until …. Compared with it."; the busy-hours and in-use limit lines in the same
 *    margin style; the page joins the rule's halves and makes no words of its own;
 *  - the map: an open route's zone names read the rule's name and dates (any other zone's name cut at its first colon);
 *    while a diversion is in use the way round carries an amber edge under the line's casing and the usual road it leaves
 *    is thin grey with "×" marks (the public map's values, DIV_USUAL in map/index.html), re-added on a style change.
 *
 * The card is mounted in a real DOM (jsdom) with live's three cases of 25 Nov (R027, R012, R001; a fictional demo
 * scheme). Not covered here: a browser (the session note's local Chrome pictures), the real map (jsdom has no WebGL:
 * the layers are source checks; the pieces' rule is run as a function), live.
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the code before (no closure lines, no pieces).
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_routes_closures.js: SKIPPED — jsdom not installed"); process.exit(0); }
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 400) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const guide = read("frontend", "help", "index.html");
const tech = read("frontend", "help", "technical", "index.html");
const rule = read("backend", "route_best.py");
const pubMap = read("map", "index.html");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const live = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020,
                                                          module: ts.ModuleKind.None, removeComments: true } }).outputText;
const fnSrc = (name) => { const a = html.indexOf("function " + name + "("); if (a < 0) return ""; const b = html.indexOf("\n}\n", a); return html.slice(a, b + 3); };

// =========================== source checks: the card ===========================
const bo = fnSrc("BestOption");
ok("⭐ SRC: the card prints the rule's closures (r.closures), at most BO_CL_SHOWN, then the rule's closures_more",
   bo.includes("const closures = r.closures || [];") && bo.includes("closures.slice(0, BO_CL_SHOWN).map(")
   && bo.includes("{r.closures_more && <p className=\"bo-cl bo-grey\" data-bo-closure-more=\"1\">{r.closures_more}</p>}"));
ok("⭐ SRC: BO_CL_SHOWN is the rule's CLOSURES_SHOWN (2)",
   /const BO_CL_SHOWN = 2;/.test(html) && /^CLOSURES_SHOWN = 2$/m.test(rule));
ok("⭐ GONE (25 Nov, Q5): the card no longer writes 'In use: …, the diversion' or 'Compared with it.'",
   !live.includes("Compared with it.") && !/data-bo-in-use="diversion"|"data-bo-in-use": "diversion"/.test(live) && !html.includes("function boDate("));
ok("⭐ SRC: the busy-hours and in-use limit lines are margin lines (bo-cl), no box (bo-state) any more",
   bo.includes('<p className="bo-cl" data-bo-in-use="busy">') && bo.includes('className="bo-cl bo-grey" data-bo-in-use-limit="1"')
   && !/bo-state[^"]*" data-bo-in-use/.test(bo));
{
  const one = fnSrc("BoClosure");
  ok("⭐ SRC: a closure line joins the rule's halves (name, dates, does) and adds no word of its own",
     one.includes('[cl.name, cl.dates].filter(Boolean).join(" · ")') && one.includes("{cl.head}") && one.includes("{cl.does}")
     && !/>[A-Za-z][^<{]*</.test(one.replace(/aria-hidden="true"><\/i>/g, "")), one);
}
{
  const css = (html.match(/\.bo-cl\{[^}]*\}/) || [""])[0];
  ok("⭐ CSS: a margin line: a 2 px ink rule at the left, no box, no corner, no tint",
     css.includes("border-left:2px solid var(--ink)") && !/background|border-radius|border:1px/.test(css), css);
  ok("⭐ CSS: a diamond (the warning colour, turned 45°) for a closure in force, a grey ring for one planned",
     /\.bo-sh\.bo-cl-warn\{background:var\(--gold\);transform:rotate\(45deg\) scale\(\.82\);\}/.test(html)
     && /\.bo-sh\.bo-cl-none\{border-radius:50%;border:2px solid #8E9197;\}/.test(html)
     && /\.bo-cl-st\.bo-cl-warn\{color:var\(--warn-text\);\}/.test(html));
}

// =========================== source checks: the map ===========================
{
  const ol = (html.match(/const OL_DIV = \{[\s\S]*?\};/) || [""])[0];
  const du = (pubMap.match(/const DIV_USUAL = \{[\s\S]*?\};/) || [""])[0];
  const v = (s, k) => (s.match(new RegExp("\\b" + k + ": ?['\"]?([^,'\"\\s}]+)")) || [])[1];
  ok("⭐ MAP: the amber edge (#F59E0B, 10.5 px) and the usual road's values (#B4B6BA 2.6 px on a 5 px casing, × #6B6E74)",
     v(ol, "edge") === "#F59E0B" && v(ol, "edgeW") === "10.5" && v(ol, "core") === "#B4B6BA" && v(ol, "coreW") === "2.6"
     && v(ol, "casingW") === "5" && v(ol, "x") === "#6B6E74" && +v(ol, "xEvery") >= 64 && +v(ol, "xEvery") <= 70, ol);
  ok("MAP: where the public map carries DIV_USUAL its colours are the same as these (kept in step)",
     !du || ["core", "x", "coreDark", "casingDark", "xDark", "coreW", "casingW"].every(k => v(du, k) === v(ol, k)), du);
}
{
  const anl = (() => { const a = html.indexOf("const addNetworkLayers = (m) => {"); return html.slice(a, html.indexOf("\n  };\n", a)); })();
  const at = (id) => anl.indexOf(`id: "${id}"`);
  ok("⭐ MAP: the layers are added on every style load (addNetworkLayers) with their own sources",
     anl.includes('m.addSource("oldivway"') && anl.includes('m.addSource("olusual"')
     && ["ol-usual-casing", "ol-usual-line", "ol-div-edge", "ol-usual-x"].every(id => at(id) > 0));
  ok("⭐ MAP: order: the alternatives' grey, the usual road over it, the amber edge, then the line in use's casing over the edge; "
     + "the crosses over the picked option and under the limit marks",
     at("alt-line") < at("ol-usual-casing") && at("ol-usual-casing") < at("ol-usual-line") && at("ol-usual-line") < at("ol-div-edge")
     && at("ol-div-edge") < at("ol-use-casing") && at("sel-arrows") < at("ol-usual-x") && at("ol-usual-x") < at("ol-mark"));
  const edge = anl.slice(at("ol-div-edge"), anl.indexOf("});", at("ol-div-edge")));
  const xs = anl.slice(at("ol-usual-x"), anl.indexOf("});", at("ol-usual-x")));
  ok("⭐ MAP: the edge sits on the line's own side (LEG_OFFSET); the crosses are '×', upright (viewport), overlap allowed",
     edge.includes('"line-offset": LEG_OFFSET') && edge.includes("OL_DIV.edge")
     && xs.includes('"text-field": "\\u00d7"') && xs.includes('"text-rotation-alignment": "viewport"')
     && xs.includes('"text-allow-overlap": true') && xs.includes('"symbol-placement": "line"'), xs);
  const look = (() => { const a = html.indexOf("const legLook = (m) => {"); return html.slice(a, html.indexOf("\n  };\n", a)); })();
  ok("MAP: on a dark ground the usual road takes the public map's dark pair (legLook)",
     look.includes('set("ol-usual-line", "line-color", dark ? OL_DIV.coreDark : OL_DIV.core);')
     && look.includes('set("ol-usual-x", "text-color", dark ? OL_DIV.xDark : OL_DIV.x);'));
  const eff = (() => { const a = html.indexOf("// 25 Nov 2026 (the Routes page rethink, card 3, Q5): a leg on a dated diversion"); return a < 0 ? "" : html.slice(a, html.indexOf("}, [olOn,", a)); })();
  ok("⭐ MAP: the pieces come only from a leg the RULE says is on a diversion in use (why 'diversion', status 'in_use'), its in-use line against option 0",
     eff.includes('x.why !== "diversion" || x.status !== "in_use"') && eff.includes("olOffPieces(use, [main])")
     && eff.includes("olOffPieces(main, [use])") && eff.includes("drawn.length ? olOffPieces(c, drawn) : [c]"), eff.slice(0, 200));
  const sc = (() => { const a = html.indexOf("const olScope = (m) => {"); return html.slice(a, html.indexOf("\n  };\n", a)); })();
  ok("⭐ MAP: an open route's zone names are the rule's (olZoneText of the open answer's closures); closed: the name as before",
     sc.includes('m.setLayoutProperty("zone-label", "text-field", sc ? olZoneText(olClosRef.current) : ["get", "name"])')
     && html.includes("olClosRef.current = (olBest && olBest.closures) || [];"));
}

// =========================== the functions, in a DOM ===========================
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

// ---- the pieces' rule ----
{
  const has = typeof w.olOffPieces === "function";
  ok("⭐ PIECES: olOffPieces is defined", has);
  if (has) {
    // a straight usual road 3 km east, and a way round that leaves it for 1.6 km to the north and comes back
    const lat = 52.6, X = (m) => -1.0 + m / (111320 * Math.cos(lat * Math.PI / 180)), Y = (m) => lat + m / 110540;
    const main = [[X(0), Y(0)], [X(3000), Y(0)]];
    const way = [[X(0), Y(0)], [X(700), Y(0)], [X(900), Y(400)], [X(2100), Y(400)], [X(2300), Y(0)], [X(3000), Y(0)]];
    const off = w.olOffPieces(way, [main]), usual = w.olOffPieces(main, [way]);
    const len = (r) => r.reduce((t, p, i) => i ? t + w.olMetres(r[i - 1], p) : 0, 0);
    ok("⭐ PIECES: the way round's own stretch is ONE piece, starting and ending on the usual road",
       off.length === 1 && w.olMetres(off[0][0], main[0]) < 800
       && Math.abs(off[0][0][1] - Y(0)) * 110540 <= 30 && Math.abs(off[0][off[0].length - 1][1] - Y(0)) * 110540 <= 30
       && len(off[0]) > 1500 && len(off[0]) < 2200, JSON.stringify(off.map(len)) + " " + JSON.stringify([off[0][0], off[0][off[0].length - 1]]));
    ok("⭐ PIECES: the usual road it leaves is ONE piece, about the 1.6 km between the two junctions",
       usual.length === 1 && len(usual[0]) > 1400 && len(usual[0]) < 1800, JSON.stringify(usual.map(len)));
    ok("PIECES: the same line twice gives nothing; a short wobble (under 150 m) gives nothing",
       w.olOffPieces(main, [main]).length === 0
       && w.olOffPieces([[X(0), Y(0)], [X(1000), Y(0)], [X(1050), Y(60)], [X(1100), Y(0)], [X(3000), Y(0)]], [main]).length === 0);
    ok("PIECES: a usual stretch already drawn (the other leg's) is not drawn again", w.olOffPieces(usual[0], usual).length === 0);
  }
}
// ---- the zone names ----
{
  const has = typeof w.olZoneText === "function";
  ok("⭐ NAMES: olZoneText is defined", has);
  if (has) {
    const e = w.olZoneText([{ zone: "Z003", name: "A47 at the new Tilton junction", dates: "until 17 Dec 2027" },
                            { zone: "Z038", name: "Market Harborough town centre", dates: "1–31 Dec 2027" },
                            { zone: "Z038", name: "Market Harborough town centre", dates: "1–31 Dec 2027" }]);
    ok("⭐ NAMES: a closure the rule reports reads its name, then its dates on a second line; each zone once; others cut at the colon",
       e[0] === "match" && JSON.stringify(e[1]) === '["get","id"]' && e[2] === "Z003" && e[3] === "A47 at the new Tilton junction\nuntil 17 Dec 2027"
       && e[4] === "Z038" && e[5] === "Market Harborough town centre\n1–31 Dec 2027" && e.length === 7
       && JSON.stringify(e[6]).includes('"index-of",":"'), JSON.stringify(e));
    ok("NAMES: no closures: every name cut at its first colon", JSON.stringify(w.olZoneText([])).startsWith('["let","n"'));
  }
}

// ---- the card ----
const hasCard = typeof w.BestOption === "function";
ok("the card component is defined", hasCard);
const E = w.React.createElement;
function mount(best, extra){
  const host = w.document.createElement("div"); w.document.body.appendChild(host);
  const root = w.ReactDOM.createRoot(host);
  const props = Object.assign({ best, routeId: "RX", showAll: false, onAll: () => {}, onFocus: () => {}, onPromote: () => {}, promoting: "", busyUses: null }, extra || {});
  if (hasCard) act(() => { root.render(E(w.BestOption, props)); });
  return { host, text: () => host.textContent.replace(/\s+/g, " "), done: () => { act(() => root.unmount()); host.remove(); } };
}
const MAIN = { loaded: { alt: 0, label: "The main route", why: "main route", status: null }, return: { alt: 0, label: "The main route", why: "main route", status: null } };
function route(o){
  return Object.assign({ route: "R050", answer: "Keep the route in use", option: null, why: "No other option is clearly better.",
    trade: null, held_back: null, lorry: "Artic Tipper (44t)", options: [], in_use: MAIN, counts_in_use: {},
    checks: { limits_held: true, community_all_options: true, collision_history: "current" }, closures: [], closures_more: null }, o || {});
}
const B = (r) => ({ day: "2026-11-25", checks: {}, route: r });
// live's three cases (a local copy of live, 25 Nov: route_best.table over all 50 routes)
const CL_R027 = { zone: "Z003", name: "A47 at the new Tilton junction", state: "in_force", whose: "in_use", alts: [], labels: [],
  legs: "both", starts_on: "2026-10-05", ends_on: "2027-12-17", dates: "until 17 Dec 2027", does: "the diversion is in use",
  head: "Closure in force", line: "A47 at the new Tilton junction · until 17 Dec 2027 · the diversion is in use" };
const CL_R012 = { zone: "Z038", name: "Market Harborough town centre", state: "planned", whose: "in_use", alts: [], labels: [],
  legs: "both", starts_on: "2027-12-01", ends_on: "2027-12-31", dates: "1–31 Dec 2027", does: "diverts, +2.7 mi · −3 min",
  head: "Closure planned", line: "Market Harborough town centre · 1–31 Dec 2027 · diverts, +2.7 mi · −3 min" };
const CL_R001 = { zone: "Z038", name: "Market Harborough town centre", state: "planned", whose: "option", alts: [1], labels: ["Alt 1"],
  legs: "both", starts_on: "2027-12-01", ends_on: "2027-12-31", dates: "1–31 Dec 2027", does: null,
  head: "Closure planned on Alt 1", line: "Market Harborough town centre · 1–31 Dec 2027" };

if (hasCard) {
  const DIV = { loaded: { alt: 2, label: "Diversion", why: "diversion", status: "in_use", until: "2027-12-17", zones: ["Z003"] },
                return: { alt: 2, label: "Diversion", why: "diversion", status: "in_use", until: "2027-12-17", zones: ["Z003"] } };
  {
    const m = mount(B(route({ route: "R027", in_use: DIV, closures: [CL_R027] })));
    const lines = [...m.host.querySelectorAll("[data-bo-closure]")];
    const first = m.host.querySelector(".bo-card").children[1];
    ok("⭐ R027: ONE closure line, in force, at the top above the answer: the diamond, 'Closure in force', then the rule's line",
       lines.length === 1 && lines[0].getAttribute("data-bo-closure") === "in_force" && first === lines[0]
       && lines[0].querySelector(".bo-sh.bo-cl-warn[aria-hidden='true']") && lines[0].querySelector(".bo-cl-st").textContent === "Closure in force"
       && lines[0].children[1].textContent === "A47 at the new Tilton junction · until 17 Dec 2027 · the diversion is in use"
       && lines[0].querySelector(".bo-g").textContent === "the diversion is in use"
       && lines[0].compareDocumentPosition(m.host.querySelector(".bo-ans")) === w.Node.DOCUMENT_POSITION_FOLLOWING, m.host.innerHTML.slice(0, 600));
    ok("⭐ R027: no 'In use: … the diversion' and no 'Compared with it.' (replaced)",
       !m.host.querySelector('[data-bo-in-use="diversion"]') && !m.text().includes("Compared with it.") && !/In use: /.test(m.text()));
    m.done();
  }
  {
    const m = mount(B(route({ route: "R012", closures: [CL_R012] })));
    const l = m.host.querySelector("[data-bo-closure]");
    ok("⭐ R012: 'Closure planned' with the ring and the Diversions table's figures, muted",
       l && l.getAttribute("data-bo-closure") === "planned" && l.querySelector(".bo-sh.bo-cl-none") && l.querySelector(".bo-cl-st.bo-cl-none")
       && l.textContent === "Closure plannedMarket Harborough town centre · 1–31 Dec 2027 · diverts, +2.7 mi · −3 min"
       && l.querySelector(".bo-g").textContent === "diverts, +2.7 mi · −3 min", l && l.textContent);
    m.done();
  }
  {
    const m = mount(B(route({ route: "R001", closures: [CL_R001] })));
    const l = m.host.querySelector("[data-bo-closure]");
    ok("⭐ R001: 'Closure planned on Alt 1', name and dates, nothing after them",
       l && l.textContent === "Closure planned on Alt 1Market Harborough town centre · 1–31 Dec 2027" && !l.querySelector(".bo-g"), l && l.textContent);
    m.done();
  }
  {
    const three = [CL_R027, CL_R012, Object.assign({}, CL_R001, { zone: "Z099", name: "Mill Street", dates: "1–31 Oct 2027", head: "Closure planned on Alt 1" })];
    const m = mount(B(route({ closures: three, closures_more: "and 1 more closure" })));
    ok("⭐ MORE: three closures: two lines, soonest first as the rule sent them, then the rule's 'and 1 more closure'",
       m.host.querySelectorAll("[data-bo-closure]").length === 2
       && m.host.querySelectorAll("[data-bo-closure]")[0].getAttribute("data-bo-closure-zone") === "Z003"
       && m.host.querySelector("[data-bo-closure-more]").textContent === "and 1 more closure"
       && !m.text().includes("Mill Street"), m.text().slice(0, 300));
    m.done();
  }
  {
    const m = mount(B(route()), { busyUses: [{ alt: 2, from: "16:00", to: "19:00", status: "in_use" }] });
    ok("NONE: no closure: no closure line and no more line; the busy-hours line is a margin line with its words",
       !m.host.querySelector("[data-bo-closure]") && !m.host.querySelector("[data-bo-closure-more]")
       && m.host.querySelector('[data-bo-in-use="busy"]').className === "bo-cl"
       && m.host.querySelector('[data-bo-in-use="busy"]').textContent === "Busy hours: Alt 2 is in use on weekdays 16:00–19:00.");
    m.done();
  }
  {
    const m = mount(B(route({ in_use: DIV, closures: [CL_R027],
      in_use_limits: [{ legs: "both", short: "7.5 t limit", words: "Weight limit 7.5 t" }] })));
    const lim = m.host.querySelector("[data-bo-in-use-limit]");
    ok("LIMIT: the in-use limit line stays, a grey margin line under the closure line, its words unchanged",
       lim && lim.className === "bo-cl bo-grey" && lim.textContent === "The diversion in use meets a 7.5 t limit below this lorry."
       && m.host.querySelector("[data-bo-closure]").compareDocumentPosition(lim) === w.Node.DOCUMENT_POSITION_FOLLOWING);
    m.done();
  }
  {
    const m = mount(B(route({ closures: undefined, closures_more: undefined })));
    ok("OLDER ANSWER: a route answer with no closures field shows the card with no closure line", m.host.querySelector(".bo-card") && !m.host.querySelector("[data-bo-closure]"));
    m.done();
  }
}

// =========================== the guides ===========================
{
  const ug = (() => { const a = guide.indexOf('<li id="ug-best-option">'); return a < 0 ? "" : guide.slice(a, guide.indexOf("</li>", a)); })();
  const map = (() => { const a = guide.indexOf('id="ug-routes-map"'); return a < 0 ? "" : guide.slice(a, guide.indexOf("</li>", a)); })();
  ok("⭐ GUIDE: the Route options entry says what a closure line is (in force, planned, planned on an option) and that a closure planned later changes no answer",
     ug.includes("<em>Closure in force</em>") && ug.includes("<em>Closure planned</em>") && ug.includes("<em>Closure planned on Alt 1</em>")
     && /changes no answer|does not change the answer/.test(ug) && !/\bHERE\b/.test(ug) && !/\/api\/|\bzones?\b/i.test(ug.replace(/id="[^"]*"/g, "")), ug.slice(0, 400));
  ok("⭐ GUIDE: the Routes map entry says the way round has an amber edge and the usual road is grey with crosses",
     /amber edge/.test(map) && /usual road/.test(map) && /×/.test(map), map.slice(0, 300));
  const t2 = (() => { const a = tech.indexOf('id="t2-best-option"'); return a < 0 ? "" : tech.slice(a, tech.indexOf("</li>", a)); })();
  ok("⭐ TECH: the technical guide names the field (closures, closures_more), that it is reported only, and the Diversions table's figures",
     t2.includes("<code>closures</code>") && t2.includes("<code>closures_more</code>") && /reported only|REPORTED/i.test(t2)
     && t2.includes("route_choice.periods"), t2.length);
}

console.log(`\nui_fix_routes_closures.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  FAIL: " + f));
process.exit(fail.length ? 1 : 0);
