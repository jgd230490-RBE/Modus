/* ui_fix_map_words.js — 11 Nov 2026, branch claude/map-words: the Public map's group A cards on John's "Yes, as
 * recommended" (notes\clocs-meeting-1113\left-to-do-mockup-1111\cards-live-a-public.html). Source checks on
 * map/index.html and the user guide, plus small sandboxes of the map's own functions; no browser (ui_audit.js is that).
 *
 *   A-F5  a route's line label says what its number is: "R050 · 132 a day" (movements, the organisation's count), not a
 *         bare "R050 · 66" of visits beside a road card that says 132; a route under 1 a day gets no label.
 *   A-X1  the road card: "The line you clicked, R045, has no loads this month."; no "R045's card" button for it; the team
 *         is on the route's name (a tip + screen-reader words), not a second line in every row.
 *   A-X2  small words: no "The other 0 are shown"; "under 1 lorry movement a day" (singular); the figures bar's label
 *         "Movements a day"; an unnamed limit's Conditions row "Road near R008 · …" with its routes in the tip.
 *   A-I3  "Report a lorry here" on the road card: the scheme's own address, the road and month filled in, the body asks
 *         when / where / which way / registration or company; the general concern email has the same body.
 *   A-F7  every Play is greyed and cannot be pressed while the months load; a settled load (or a failed one) hands it back.
 *
 * Its own file (the wave rule): the pins it narrows / reverses in parse_map.js are marked there. Every check of a change fails on
 * the code before this branch, but for the 10 that guard what stays (on 07c8b49: 10 passed, 23 failed).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
// a function's source, from "function name(" to the next sibling at the same indent
function fnSrc(name) {
  let i = html.indexOf("    function " + name + "(");
  if (i < 0) i = html.indexOf("    async function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    function ", i + 10);
  return html.slice(i, j > 0 ? j : i + 6000);
}
// a one-statement const at the page's indent ("    const name = …" up to the line that ends it)
function constSrc(name, endMark) {
  const i = html.indexOf("    const " + name + " = ");
  if (i < 0) return "";
  const j = html.indexOf(endMark || "\n", i);
  return html.slice(i, j + (endMark ? endMark.length : 0));
}
const WORDS2 = { label: "Lorry movements a day", lower: "lorry movements a day", short: "movements a day", col: "Movements a day" };
const WORDS1 = { label: "Lorry visits a day", lower: "lorry visits a day", short: "visits a day", col: "Visits a day" };
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------------------------------------- A-F5
console.log("A-F5 the route label");
// a small evaluator of the Mapbox expressions the label uses
function evalExpr(e, props) {
  if (!Array.isArray(e)) return e;
  const [op, ...a] = e, v = x => evalExpr(x, props);
  switch (op) {
    case "get": return props[a[0]];
    case "concat": return a.map(v).map(x => (x == null ? "" : String(x))).join("");
    case "case": { for (let i = 0; i + 1 < a.length; i += 2) if (v(a[i])) return v(a[i + 1]); return v(a[a.length - 1]); }
    case "<": return v(a[0]) < v(a[1]);
    case "*": return v(a[0]) * v(a[1]);
    case "round": return Math.round(v(a[0]));
    case "to-number": { const n = Number(v(a[0])); return Number.isFinite(n) ? n : v(a[1]); }
    case "to-string": return String(v(a[0]));
    default: throw new Error("expression op not in the harness: " + op);
  }
}
{
  const src = fnSrc("forecastLabelField");
  const run = (unit, pv) => {
    const ctx = { CONFIG: { FORECAST_UNIT: unit }, PV: () => pv, out: null };
    vm.createContext(ctx); vm.runInContext(src + "\nout = forecastLabelField();", ctx);
    return ctx.out;
  };
  let e2 = null, e1 = null, em = null, err = "";
  try { e2 = run("vehicles", 2); e1 = run("vehicles", 1); em = run("m3", 2); } catch (x) { err = String(x); }
  ok("A-F5 the label runs in a sandbox", !!e2 && !!e1 && !!em, err);
  if (e2) {
    ok("⭐ A-F5 a route of 66 visits a day reads 'R050 · 132 a day' (movements: the road card's figure), not 'R050 · 66'",
       evalExpr(e2, { route_id: "R050", f_avg: 66 }) === "R050 · 132 a day", evalExpr(e2, { route_id: "R050", f_avg: 66 }));
    ok("A-F5 an organisation counting visits reads its visits: 'R050 · 66 a day'", evalExpr(e1, { route_id: "R050", f_avg: 66 }) === "R050 · 66 a day");
    ok("A-F5 rounded to a whole number: 10.4 visits = '21 a day'", evalExpr(e2, { route_id: "R7", f_avg: 10.4 }) === "R7 · 21 a day");
    ok("A-F5 a route under 1 a day gets no label (never 'R9 · 0 a day')", evalExpr(e2, { route_id: "R9", f_avg: 0.2 }) === ""
       && evalExpr(e2, { route_id: "R9", f_avg: null }) === "");
    ok("A-F5 a scheme counting another unit keeps its unit and figure: 'R1 · 12 m³ / day'", evalExpr(em, { route_id: "R1", f_avg: 12 }) === "R1 · 12 m³ / day");
  }
  ok("A-F5 the user guide says what the label's number is", guide.includes("&quot;R050 · 132 a day&quot;") && /a road’s card adds up every route on that road|a road's card adds up every route on that road/.test(guide));
}

// ---------------------------------------------------------------------------------------------- the road card sandbox
const card = (() => {
  const a = html.indexOf("    function secselView("), b = html.indexOf("    function secselPickMonth(");
  return a > 0 && b > a ? html.slice(a, b) : "";
})();
const cwNSrc = constSrc("cwN", "CW().lower);");
function cardRun(pv, extra) {
  const ctx = Object.assign({ escHtml: esc, PV: () => pv, CW: () => (pv === 2 ? WORDS2 : WORDS1), monthLabel: m => (m === 17 ? "Apr 2027" : "M" + m),
    teamText: v => (v === "IPT1" ? "North Team" : v), TENANT: { name: "Wolds Link", demo_notice: "Fictional scheme" }, out: null }, extra || {});
  vm.createContext(ctx);
  vm.runInContext(cwNSrc + "\n" + card + "\nthis.secselCardHTML = secselCardHTML;", ctx);
  return ctx;
}
const RES = { kind: "road", month: 17, a_day: 61, in: 30.5, out: 30.5,
              routes: [{ route_id: "R011", in: 15.5, out: 15.5, a_day: 31 }, { route_id: "R012", in: 15, out: 15, a_day: 30 }], idle: ["R045", "R046"] };
const RP = { R011: { origin: "Northfield Quarry", dest: "Melton Compound", ipt: "IPT1" }, R012: { origin: "Plant C", dest: "Site B", ipt: "IPT1" } };

console.log("A-X1 the road card");
{
  let c = null, err = "";
  try { c = cardRun(2); } catch (x) { err = String(x); }
  ok("A-X1 the road card runs in a sandbox", !!c && typeof c.secselCardHTML === "function", err);
  if (c) {
    const h = c.secselCardHTML(RES, { rp: RP, clicked: "R045" });
    ok("⭐ A-X1 the clicked line with no loads says it is the clicked one: 'The line you clicked, R045, has no loads this month.'",
       h.includes('<p class="secsel-note">The line you clicked, R045, has no loads this month.</p>') && !h.includes("R045: no loads in"), h);
    ok("⭐ A-X1 ...and no 'R045’s card' button (that card has no loads to show)", !h.includes("R045’s card"));
    const hb = c.secselCardHTML(RES, { rp: RP, clicked: "R011" });
    ok("A-X1 a clicked route WITH loads keeps its card button", hb.includes("R011’s card</button>") && !hb.includes("has no loads this month"));
    const hn = c.secselCardHTML(Object.assign({}, RES, { a_day: null, routes: [{ route_id: "R011" }] }), { rp: RP, clicked: "R045" });
    ok("A-X1 no month on screen: the button stays (nothing says the route is idle)", hn.includes("R045’s card</button>"));
    // NARROWED 11 Nov 2026 (merged with PR #270, the route number a button "Show R011 on the map"): the team is that button's
    // DESCRIPTION (aria-describedby to a hidden span) and the mouse's tip; never in its name, never a second line in the row
    ok("⭐ A-X1 the team is on the route's button as its description and tip, not in its name, not a second line in the row",
       h.includes('aria-label="Show R011 on the map"') && h.includes('aria-describedby="secsel-team-road-R011" title="North Team"')
       && h.includes('>R011</button><span id="secsel-team-road-R011" hidden>North Team</span></td><td>Northfield Quarry → Melton Compound</td>')
       && !h.includes('class="secsel-team"') && !/aria-label="[^"]*North Team/.test(h)
       && h.includes("<th>From → to</th>") && !h.includes("· team</th>"), h);
    const ha = c.secselCardHTML(Object.assign({}, RES, { kind: "area" }), { rp: RP });
    ok("A-X1 the area card names no team, in a tip or otherwise", !ha.includes("North Team") && !ha.includes(' title="'));
    ok("A-X1 'under 1' in the card's headline is singular: 'under 1 lorry movement a day'",
       c.secselCardHTML(Object.assign({}, RES, { a_day: 0.4, routes: [{ route_id: "R011", in: 0.2, out: 0.2, a_day: 0.4 }], idle: [] }), { rp: RP })
        .includes("<b>under 1 lorry movement a day</b>"));
  }
  ok("A-X1 the old 'secsel-team' row line is gone from the source", !/class="secsel-team"/.test(html));
}

console.log("A-X2 small words");
{
  const loop = fnSrc("renderTlLoop");
  ok("⭐ A-X2 the timeline never says 'The other 0 are shown, not played.' (only when some are)",
     loop.includes("(N - n > 0 ? ' The other ' + (N - n) + ' are shown, not played.' : '')"));
  let cw = null; try { cw = new Function("CW", cwNSrc + "\nreturn cwN;")(() => WORDS2); } catch (x) { /* fails below */ }
  ok("⭐ A-X2 'under 1' and '1' take the singular: 'under 1 lorry movement a day', '1 lorry movement a day'; '2 lorry movements a day'",
     !!cw && cw("under 1") === "under 1 lorry movement a day" && cw("1") === "1 lorry movement a day" && cw("2") === "2 lorry movements a day");
  let cv = null; try { cv = new Function("CW", cwNSrc + "\nreturn cwN;")(() => WORDS1); } catch (x) {}
  ok("A-X2 ...and for visits: 'under 1 lorry visit a day'", !!cv && cv("under 1") === "under 1 lorry visit a day");
  ok("A-X2 every place that joined a count to its words goes through cwN (the shared road popup, its hover tip, the card, the timeline line)",
     html.includes("cwN(f ? f.properties.rl_mv_text : '0')") && html.includes("fig: cwN(p.rl_mv_text != null ? p.rl_mv_text : '0')")
     && html.includes("escHtml(cwN(secN(v.aday)))") && html.includes("const parts = [cwN(trips), routes")
     && !/rl_mv_text : '0'\) \+ ' ' \+ CW\(\)\.lower/.test(html) && !html.includes("secN(v.aday) + ' ' + escHtml(CW().lower)"));
  ok("⭐ A-X2 the figures bar's label is 'Movements a day' (two lines at 1422 px, not three); the lorry stays in its tip",
     html.includes('title="A lorry coming and going is 2 movements, as councils count them.">Movements a day</div>')
     && html.includes("tl.textContent = CW().col; tl.title = CW().note;") && !html.includes(">Lorry movements a day</div>"));
  // the Conditions row of a limit with no road name
  const rowsSrc = fnSrc("limitConditionRows");
  const ctx = { limitPropsOf: p => p, limitBreachLines: bs => bs, limitKindWord: k => (k === "weight" ? "weight" : k),
                limitValueText: (k, v, u) => v + " " + u, out: null };
  vm.createContext(ctx);
  let rows = null, err = "";
  try {
    vm.runInContext(rowsSrc + "\nthis.limitConditionRows = limitConditionRows;", ctx);
    const F = p => ({ properties: p });
    rows = ctx.limitConditionRows([
      F({ id: "a", kind: "weight", value: 7.5, unit: "t", breach_count: 4, name: "", ref: "",
          breaches: ["R008", "R016", "R018", "R020"].map(r => ({ route_id: r })) }),
      F({ id: "b", kind: "weight", value: 7.5, unit: "t", breach_count: 1, name: "Back Lane", ref: "", exceptions: "Except for access",
          breaches: [{ route_id: "R004" }] })], ["R008", "R016", "R018", "R020", "R004"], 17);
  } catch (x) { err = String(x); }
  ok("A-X2 the Conditions rows run in a sandbox", Array.isArray(rows) && rows.length === 2, err || rows);
  if (Array.isArray(rows) && rows.length === 2) {
    ok("⭐ A-X2 an unnamed limit's row reads 'Road near R008 · 7.5 t · no exception recorded: check the sign'; its routes in the tip",
       rows[0].what === "Road near R008 · 7.5 t · no exception recorded: check the sign" && rows[0].tip === "Routes over it: R008, R016, R018, R020", rows[0]);
    ok("A-X2 a named road's row is as before (routes, figure, exception, road) with no tip",
       rows[1].what === "R004 · 7.5 t, except for access · Back Lane" && !rows[1].tip, rows[1]);
  }
  ok("A-X2 both Conditions renderers put the tip on the row's sentence",
     html.includes('<span class="what"${i.tip ? ` title="${esc(i.tip)}"` : \'\'}>${esc(i.what)}</span>')
     && html.includes("'</b><span class=\"what\"' + (i.tip ? ' title=\"' + escHtml(i.tip) + '\"' : '') + '>' + escHtml(i.what) + '</span><br>'"));
}

console.log("A-I3 Report a lorry here");
{
  const helpers = fnSrc("lorryBody") + fnSrc("mailtoOf") + fnSrc("concernMailto") + fnSrc("lorryMailto");
  const ctx = {};
  vm.createContext(ctx);
  let err = "";
  try { vm.runInContext(helpers + "\nthis.lorryMailto = lorryMailto; this.concernMailto = concernMailto;", ctx); } catch (x) { err = String(x); }
  ok("A-I3 the email helpers run in a sandbox", typeof ctx.lorryMailto === "function", err);
  if (typeof ctx.lorryMailto === "function") {
    const mt = ctx.lorryMailto("contact@scheme.example", "B6047", "Apr 2027", "https://x.example/map/?month=2027-04");
    const q = new URLSearchParams(mt.slice(mt.indexOf("?") + 1));
    ok("⭐ A-I3 the email names the road and month: subject 'A lorry on B6047, Apr 2027'",
       mt.startsWith("mailto:contact@scheme.example?subject=") && q.get("subject") === "A lorry on B6047, Apr 2027", mt);
    const body = q.get("body") || "";
    ok("⭐ A-I3 the body asks for the four things: when, where (the road filled in), which way, registration or company",
       body.startsWith("When (date and time):\nWhere: B6047, \nWhich way it was going:\nRegistration or company name, if seen:\n\n"), body);
    ok("A-I3 ...says a lorry on another road may not be the scheme's, and carries the month and the map view",
       body.includes("A lorry on another road may be a local delivery, not this scheme’s.") && body.includes("Month on the map: Apr 2027")
       && body.includes("The map view: https://x.example/map/?month=2027-04"));
    const nm = new URLSearchParams(ctx.lorryMailto("contact@scheme.example", "", null, null).split("?")[1]);
    ok("A-I3 no road name from the basemap and no month: 'A lorry on a road on the map', Where left blank",
       nm.get("subject") === "A lorry on a road on the map" && nm.get("body").startsWith("When (date and time):\nWhere: \n"));
    const cm = new URLSearchParams(ctx.concernMailto("contact@scheme.example", "Wolds Link", "Apr 2027", null).split("?")[1]);
    ok("A-I3 the general concern email asks the same four things after 'What happened:'",
       cm.get("subject") === "Report a concern: Wolds Link" && cm.get("body").startsWith("What happened:\n\nWhen (date and time):\nWhere: \nWhich way it was going:"));
  }
  // the card's foot
  let c = null; try {
    c = cardRun(2, { concernAddress: t => (t && t.concern_email) || null,
                     lorryMailto: (a, road, m, link) => "mailto:" + a + "|" + road + "|" + m + "|" + link });
  } catch (x) {}
  if (c) {
    c.TENANT.concern_email = "contact@scheme.example";
    const h = c.secselCardHTML(RES, { rp: RP, clicked: "R011", road: "B6047", link: "L" });
    ok("⭐ A-I3 the road card's foot carries 'Report a lorry here' with the road, the month and the view",
       h.includes('<a class="secsel-btn secsel-report" href="mailto:contact@scheme.example|B6047|Apr 2027|L">Report a lorry here</a>'), h.slice(-500));
    ok("A-I3 not on the area card, nor while the card loads", !c.secselCardHTML(Object.assign({}, RES, { kind: "area" }), { rp: RP }).includes("Report a lorry here")
       && !c.secselCardHTML({ kind: "road", month: 17, loading: true }, {}).includes("Report a lorry here"));
    c.TENANT.concern_email = null;
    ok("⭐ A-I3 no typed address (the demo's seed): no link, no invented address", !c.secselCardHTML(RES, { rp: RP, road: "B6047" }).includes("Report a lorry here"));
  } else ok("A-I3 the road card with an address runs in a sandbox", false);
  ok("A-I3 the road's name is read from the basemap under the click, never sent anywhere but the email",
     fnSrc("secselRoadName").includes("x.sourceLayer === 'road'") && html.includes("limits: secselLimitLines(e.point), road: secselRoadName(e.point) };")
     && html.includes("road: at.road, link:"));
  ok("A-I3 the link is styled as the card's other buttons (no underline)", /a\.secsel-btn\{ display:inline-flex; align-items:center; text-decoration:none; \}/.test(html));
  ok("A-I3 the user guide says where it is", guide.includes("Report a lorry here"));
  ok("A-I3 no supplier or back-end words in the new strings", !/HERE|Mapbox|OpenStreetMap|server|endpoint/.test(fnSrc("lorryBody") + fnSrc("lorryMailto")));
}

console.log("A-F7 Play while the months load");
{
  const ens = fnSrc("ensureTimelineMatrix"), pw = fnSrc("playWait");
  ok("⭐ A-F7 the months' fetch greys Play when it starts and hands it back when it settles (loaded or failed)",
     /playWait\(true\);\s*TL\.matrixPending = loadTimelineMatrix\(\)\.finally\(\(\)=>\{ TL\.matrixPending = null; playWait\(false\); \}\);/.test(ens), ens);
  ok("A-F7 every Play is covered: the panel's, the bar's and the phone's two",
     html.includes("const PLAY_IDS = ['tl-open', 'tl-play', 'm-play', 'm-full-play'];")
     && ["tl-open", "tl-play", "m-play", "m-full-play"].every(id => html.includes('id="' + id + '"')));
  const els = {}; ["tl-open", "tl-play", "m-play", "m-full-play"].forEach(id => { const cl = new Set();
    els[id] = { disabled: false, classList: { toggle: (k, on) => (on ? cl.add(k) : cl.delete(k)), has: k => cl.has(k) } }; });
  const ctx = { document: { getElementById: id => els[id] || null } };
  vm.createContext(ctx);
  let err = "";
  try { vm.runInContext(constSrc("PLAY_IDS") + "\n" + pw + "\nthis.playWait = playWait;", ctx); } catch (x) { err = String(x); }
  if (typeof ctx.playWait === "function") {
    ctx.playWait(true);
    const grey = Object.values(els).every(b => b.disabled && b.classList.has("play-wait"));
    ctx.playWait(false);
    ok("⭐ A-F7 playWait(true) disables every Play and greys it; playWait(false) gives it back",
       grey && Object.values(els).every(b => !b.disabled && !b.classList.has("play-wait")));
  } else ok("A-F7 playWait runs in a sandbox", false, err);
  ok("A-F7 the grey look: faded, a waiting cursor, no colour", /\.play-wait, \.play-wait:hover\{ opacity:\.45; cursor:progress; filter:grayscale\(1\); \}/.test(html));
  ok("A-F7 no new words for it (the Month line already says 'Loading the months…')", !/play-wait[^\n]*aria-label/.test(html) && !pw.includes("textContent"));
}

console.log();
fail.forEach(f => console.log("  FAIL: " + f));
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
