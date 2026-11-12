/* ui_fix_map_route_story.js — 12 Nov 2026, branch claude/ui-map-forecast-detail-1111 (John, 12 Nov: "Yes, option A", to the
 * page notes\ux-map-forecast-detail-1111; step A1, "This route"). Source checks on map/index.html and the two guides, plus
 * sandboxes that run the page's OWN functions against stand-ins (R050's real figures from the demo); no browser (the browser
 * half is the Chrome check in the session note).
 *
 *   The route panel's first tab ("Route analysis") opened on four route facts and asked the server for the whole plan again;
 *   its second ("Forecast detail") was a 60-column tonnes table. A1: the tabs are "This route" and "All routes"; "This route"
 *   says what the route carries, how much and between which months, shows the month's three figures (the phone card's) and
 *   the busiest month, and draws a bar per month that moves the map; Table and Route facts are one click away; the phone's
 *   route card gets the same line, the bars as a picture and one button to the busiest month. No read of its own.
 *
 * Its own file (BUILD.md rule 3). Every check marked ⭐ fails on the code before.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("map", "index.html");
const guide = read("frontend", "help", "index.html");
const tech = read("frontend", "help", "technical", "index.html");
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 500) : "")); console.log("  ✗ " + label); }
}
// a check that needs a function the page does not have is a failed check, never a crash
const TRY = (f) => { try { return f(); } catch (e) { return false; } };
// a function's own source: from its first line to the first line that is exactly four spaces and a closing brace
const fnSrc = (head) => { const a = html.indexOf("    " + head); if (a < 0) return ""; const b = html.indexOf("\n    }", a); return b < 0 ? "" : html.slice(a, b + 6); };
const fmtN = (n, d) => (Math.round(n * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toLocaleString("en-GB");
const monthLabel = (i) => ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][(i - 1) % 12] + " " + (2026 + Math.floor((i - 1) / 12));
const escHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const CWm = { label: "Lorry movements a day", lower: "lorry movements a day", short: "movements a day", col: "Movements a day", note: "A lorry coming and going is 2 movements, as councils count them." };
const CWv = { label: "Lorry visits a day", lower: "lorry visits a day", short: "visits a day", col: "Visits a day", note: "A lorry coming and going is 1 visit (2 movements as councils count them)." };

// ---------- the stand-in: R050 as the demo holds it (29 t a load, 22 working days, 6 round trips a lorry a day) ----------
const T = { 5: 800, 6: 1000, 7: 1200, 8: 1400, 9: 1600, 10: 1600, 11: 1600, 12: 900, 13: 1100, 14: 1300, 15: 38000, 16: 42000, 17: 38000, 18: 1200, 19: 1000, 20: 800 };
const months = {};
for (let m = 1; m <= 60; m++) {
  const lines = [{ route_id: "R011", material_type: "Small aggregate", qty_t: 500, vehicle_loads: 25, trips_per_vehicle_day: 4, co2_t: 1 }];
  if (T[m]) lines.push({ route_id: "R050", material_type: "Earthworks / soil", vehicle_name: "Artic Tipper (44t)", qty_t: T[m], vehicle_loads: Math.round(T[m] / 29 * 1000) / 1000,
                         trips_per_vehicle_day: 6, co2_t: m === 20 ? null : T[m] * 0.00095 });
  months[m] = { working_days: 22, lines };
}

(async () => {
  // ---------- the tabs and the tab row ----------
  ok("⭐ the tabs read 'This route' and 'All routes' (were 'Route analysis' and 'Forecast detail'); their ids and what they call are unchanged",
     html.includes('<button class="drawer-tab active" id="tab-analysis" onclick="showDrawerTab(\'analysis\')">This route</button>')
     && html.includes('<button class="drawer-tab" id="tab-detail" onclick="openForecastDetail()">All routes</button>')
     && !/class="drawer-tab[^"]*"[^>]*>(Route analysis|Forecast detail)</.test(html));
  ok("⭐ the view's switches sit in the tab row, between the tabs and the close button, hidden until a story is drawn",
     /id="tab-detail"[^\n]*\n[^\n]*\n\s*<span class="rs-ctl" id="rs-ctl" hidden><\/span>\s*\n\s*<button type="button" class="drawer-close"/.test(html));
  ok("⭐ showDrawerTab clears the tab row's switches when the tab changes (each tab draws its own), closes an open 'i', and draws 'This route' again when its tab is pressed",
     html.includes("{ const rc = document.getElementById('rs-ctl'); if (rc && rc._tab !== tab) { rc._tab = tab; rc._src = null; rc.innerHTML = ''; rc.hidden = true; } if (typeof closeInfos === 'function') closeInfos(); }")
     && html.includes("if (tab === 'analysis' && typeof RS !== 'undefined' && RS.rid && typeof renderRouteStory === 'function') renderRouteStory();")
     && html.includes("if (ctl && drawerTab === 'analysis') {"));
  ok("with no route picked there is no 'This route' tab to press (the panel opened from the Control Panel shows All routes)",
     html.includes("{ const ta = document.getElementById('tab-analysis'); if (ta && typeof RS !== 'undefined') ta.hidden = !RS.rid; }"));

  // ---------- no read of its own ----------
  const a = html.indexOf("async function openRouteAnalysis(routeId){"), b = html.indexOf("async function openForecastDetail(){");
  const block = a > 0 && b > a ? html.slice(a, b) : "";
  ok("⭐ NO READ: the route panel asks the server for nothing of its own (no fetch, no fetchMatrix between openRouteAnalysis and the table's code); it waits on the two reads the page makes when it opens",
     !!block && !/fetchMatrix\(/.test(block) && !/\bfetch\(/.test(block) && block.includes("await ensureTimelineMatrix();") && block.includes("await kpiFetchAll();"));
  ok("NO READ: only if that one read failed are the route's own months read, one at a time, through the page's existing month read",
     /catch \(e\) \{\s*const by = \(TL\.matrix && TL\.matrix\.byRoute\[[^\]]+\]\) \|\| \{ monthly: \{\} \};[\s\S]{0,260}await kpiFetchMonth\(m\)/.test(block));
  ok("⭐ the old cards' words are gone from the page: 'over selected window', 'one-way loaded runs', 'busiest month in window', 'to clear peak month', 'Trips / day / lorry'",
     !/over selected window|one-way loaded runs|busiest month in window|to clear peak month|Trips \/ day \/ lorry|Lorries for peak/.test(html));
  ok("⭐ no source or supplier is named in the panel's code (the 34-word carbon note is gone; its words are in an 'i' and the guides)",
     !!block && !/DESNZ|DEFRA|Carbon Tool|carbon_stamp/.test(block) && !/Carbon: DESNZ 2026 factors/.test(html));

  // ---------- rsStory: the page's own function on R050's figures ----------
  const routeFigures = new Function(fnSrc("function routeFigures(lines, rid, wd) {") + "\nreturn routeFigures;")();
  const storySrc = fnSrc("function rsStory(rid, months, wdDefault, lo, hi) {");
  ok("⭐ rsStory is in the page and takes its month figures from routeFigures (the phone card's rule)", !!storySrc && storySrc.includes("routeFigures(kp.lines, rid, wd)"));
  const rsStory = storySrc ? new Function("routeFigures", storySrc + "\nreturn rsStory;")(routeFigures) : () => null;
  const st = rsStory("R050", months, 22, 1, 60) || { months: [], busiest: {}, materials: [] };
  ok("⭐ rsStory (run): R050 works May 2026 to Aug 2027 (months 5 to 20), 16 months listed, 133,500 t, 4,603 loads",
     st.first === 5 && st.last === 20 && st.months.length === 16 && st.totalT === 133500 && Math.round(st.totalLoads) === 4603, [st.first, st.last, st.months.length, st.totalT, st.totalLoads]);
  ok("⭐ rsStory (run): the busiest month is Apr 2027 (month 16) at 65.8 visits a day = 132 movements; Sep 2026 is 2.5 visits = 5 movements, 1 vehicle, 73 t a day",
     st.busiest.m === 16 && Math.round(st.busiest.aday * 2) === 132
     && (() => { const s = st.months.find(x => x.m === 9); return s && Math.round(s.aday * 2) === 5 && s.vehicles === 1 && Math.round(s.tonnesDay) === 73; })()
     && (() => { const s = st.months.find(x => x.m === 16); return s && s.vehicles === 11 && Math.round(s.tonnesDay) === 1909; })());
  ok("rsStory (run): another route's lines are left out; the material is named; a month with no carbon figure is counted, never a zero (Aug 2027 here)",
     st.materials.join() === "Earthworks / soil" && st.co2MissingMonths === 1 && Math.abs(st.co2BakedT - (133500 - 800)) < 1e-6 && Math.abs(st.co2T - (133500 - 800) * 0.00095) < 1e-6);
  {
    const gap = { 3: { working_days: 22, lines: [{ route_id: "RX", material_type: "A", qty_t: 10, vehicle_loads: 1 }] }, 6: { working_days: 22, lines: [{ route_id: "RX", material_type: "B", qty_t: 30, vehicle_loads: 2 }, { route_id: "RX", material_type: "C", qty_t: 20, vehicle_loads: 1 }] } };
    const g = rsStory("RX", gap, 22, 1, 12);
    ok("rsStory (run): the months between the first and the last are listed with nothing in them; materials come biggest first; no volume = no story",
       !!g && g.months.map(x => x.m).join() === "3,4,5,6" && g.months[1].t === 0 && g.months[1].loads === 0 && g.materials.join() === "B,C,A" && rsStory("NONE", gap, 22, 1, 12) === null);
    ok("⭐ rsWhat (run): 'Earthworks / soil · 133,500 t · May 2026 to Aug 2027'; three materials read '3 materials'; one month reads that month alone",
       TRY(() => { const rsWhat = new Function("monthLabel", "fmtN", fnSrc("function rsWhat(story) {") + "\nreturn rsWhat;")(monthLabel, fmtN);
                 return rsWhat(st) === "Earthworks / soil · 133,500 t · May 2026 to Aug 2027" && rsWhat(g) === "3 materials · 60 t · Mar 2026 to Jun 2026"
                        && rsWhat({ materials: ["Asphalt", "Sand"], totalT: 5, first: 7, last: 7 }) === "Asphalt, Sand · 5 t · Jul 2026"; }));
  }
  const rsN = new Function("fmtN", "const rsN = x => (x > 0 && x < 1 ? 'under 1' : fmtN(x || 0, 0));\nreturn rsN;")(fmtN);
  ok("⭐ a count a day is a whole number, 'under 1' below one (the page's own line)", html.includes("const rsN = x => (x > 0 && x < 1 ? 'under 1' : fmtN(x || 0, 0));") && rsN(0.4) === "under 1" && rsN(131.66) === "132" && rsN(0) === "0" && rsN(1448.3) === "1,448");

  // ---------- the HTML the page's functions draw ----------
  const mk = (PVn, CWo) => {
    const dep = { monthLabel, fmtN, escHtml, rsN, PV: () => PVn, CW: () => CWo, vehiclesText: r => (r.unbaked && !r.vehicles ? "not routed yet" : fmtN(r.vehicles, 0) + (r.unbaked ? "+" : "")),
                  CONFIG: { START_YEAR: 2026, MONTH_COUNT: 60 }, RS_MONTHS: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] };
    const names = Object.keys(dep), vals = names.map(k => dep[k]);
    const f = (head, extra) => new Function(...names, ...(extra ? Object.keys(extra) : []), fnSrc(head) + "\nreturn " + /function (\w+)/.exec(head)[1] + ";")(...vals, ...(extra ? Object.values(extra) : []));
    const rsWhat = f("function rsWhat(story) {"), rsMonthWords = f("function rsMonthWords(x, unit) {"), rsTitleHTML = f("function rsTitleHTML(names) {");
    return { rsWhat, rsMonthWords, rsTitleHTML,
             rsStoryHTML: f("function rsStoryHTML(story, month, names, desc) {", { rsWhat, rsTitleHTML }),
             rsChartHTML: f("function rsChartHTML(story, month, unit, still, names) {", { rsWhat, rsMonthWords }),
             rsTableHTML: f("function rsTableHTML(story, month, unit) {", { rsMonthWords }),
             rsPhoneBusyHTML: f("function rsPhoneBusyHTML(st, month) {"),
             rsCopyParts: f("function rsCopyParts(story, names, link, when) {", { rsWhat, TENANT: { name: "Wolds Link", demo_notice: "Fictional scheme" } }) };
  };
  const NAMES = { rid: "R050", from: "Tilton Viaduct site", to: "Wolds Link Inert Landfill", team: "North Team" };
  let M;
  try { M = mk(2, CWm); } catch (e) { M = null; }
  ok("⭐ the drawing functions are in the page (rsStoryHTML, rsChartHTML, rsTableHTML, rsPhoneBusyHTML, rsCopyParts)", !!M);
  if (M) {
    const s16 = M.rsStoryHTML(st, 16, NAMES, "Piling arisings <b>to tip</b>");
    ok("⭐ the story (run), Apr 2027 on the map: the route in words, 'R050 · North Team', the line, 'In Apr 2027', 132 / 11 / 1,909 t with the phone card's labels, and 'Busiest · 132 a day' under Apr 2027 (not a button on its own month)",
       s16.includes('<h3 class="rs-title"><span>Tilton Viaduct site → Wolds Link Inert Landfill</span><small>R050 · North Team</small></h3>')
       && s16.includes('<div class="rs-what">Earthworks / soil · 133,500 t · May 2026 to Aug 2027</div>') && s16.includes('<div class="rs-inm">In Apr 2027</div>')
       && s16.includes('<b>132</b><span>Lorry movements a day</span>') && s16.includes('<b>11</b><span>Vehicles needed</span>') && s16.includes('<b>1,909 t</b><span>Material a day</span>')
       && s16.includes('<div class="rs-fig"><b>Apr 2027</b><span>Busiest · 132 a day</span></div>') && !s16.includes("rs-go"), s16.slice(0, 300));
    ok("⭐ the story (run): the team's description is one line, and anything typed in it is escaped", s16.includes('<div class="rs-desc" title="Piling arisings &lt;b&gt;to tip&lt;/b&gt;">Piling arisings &lt;b&gt;to tip&lt;/b&gt;</div>') && !M.rsStoryHTML(st, 16, NAMES, "").includes("rs-desc"));
    const s9 = M.rsStoryHTML(st, 9, NAMES, "");
    ok("⭐ the story (run), Sep 2026 on the map: 5 / 1 / 73 t, and the busiest month is a BUTTON that goes to month 16",
       s9.includes('<div class="rs-inm">In Sep 2026</div>') && s9.includes('<b>5</b><span>Lorry movements a day</span>') && s9.includes('<b>1</b><span>Vehicles needed</span>') && s9.includes('<b>73 t</b><span>Material a day</span>')
       && s9.includes('<button type="button" class="rs-fig rs-go" data-k="go" onclick="rsGoMonth(16)" aria-label="Go to the busiest month, Apr 2027"><b>Apr 2027</b><span>Busiest · 132 a day</span></button>'));
    ok("the story (run): a month with nothing on the route, and no month at all, say so in the phone card's words and keep the busiest-month button",
       M.rsStoryHTML(st, 25, NAMES, "").includes('<div class="rs-inm">Nothing approved on this route in Jan 2028.</div>') && M.rsStoryHTML(st, 25, NAMES, "").includes("rsGoMonth(16)")
       && M.rsStoryHTML(st, null, NAMES, "").includes('<div class="rs-inm">Pick a month to see this route’s movements a day.</div>') && !M.rsStoryHTML(st, null, NAMES, "").includes("Vehicles needed"));
    const V = mk(1, CWv);
    ok("⭐ the unit follows the organisation's setting (run): counting visits, Apr 2027 reads 66 under 'Lorry visits a day' and 'Busiest · 66 a day'",
       V.rsStoryHTML(st, 16, NAMES, "").includes('<b>66</b><span>Lorry visits a day</span>') && V.rsStoryHTML(st, 16, NAMES, "").includes("Busiest · 66 a day")
       && V.rsMonthWords(st.months.find(x => x.m === 16), "count") === "Apr 2027: 66 lorry visits a day");

    // the chart
    const cols = h => (h.match(/<div class="rs-col[^"]*">/g) || []);
    const ems = h => (h.match(/<em>[^<]*<\/em>/g) || []).map(x => x.replace(/<\/?em>/g, ""));
    const c16 = M.rsChartHTML(st, 16, "count", false, NAMES), c9 = M.rsChartHTML(st, 9, "count", false, NAMES);
    ok("⭐ the chart (run): one bar a month (16), the map's month marked once, month names under them and the two years under those",
       cols(c16).length === 16 && (c16.match(/<div class="rs-col rs-now">/g) || []).length === 1 && c16.includes('<span class="rs-now">Apr</span>')
       && c16.includes('<span style="flex:8 1 0">2026</span><span style="flex:8 1 0">2027</span>'));
    ok("⭐ the chart (run): figures as drawn: on Apr 2027, over Mar, Apr and May (119, 132, 119); on Sep 2026, over Sep and the busiest month only (5, 132)",
       ems(c16).join() === "119,132,119" && ems(c9).join() === "5,132", [ems(c16), ems(c9)]);
    ok("⭐ the chart is ONE control (run): a slider from the route's first month to its last, on the map's month, that says the month's figure and moves the map; the bars are hidden from a screen reader and take the pointer",
       /<input type="range" id="rs-range" min="5" max="20" step="1" value="16" aria-label="R050, month" aria-valuetext="Apr 2027: 132 lorry movements a day" oninput="rsGoMonth\(this\.value\)">/.test(c16)
       && c16.includes('<div class="rs-plot" onclick="rsPlotClick(event)" aria-hidden="true">') && (c16.match(/<button/g) || []).length === 0);
    ok("the chart (run): with the map on a month outside the route's life the slider rests on the busiest month; in tonnes the figures are tonnes",
       /value="16"/.test(M.rsChartHTML(st, 40, "count", false, NAMES)) && ems(M.rsChartHTML(st, 16, "t", false, NAMES)).join() === "38,000,42,000,38,000"
       && /aria-valuetext="Apr 2027: 42,000 t"/.test(M.rsChartHTML(st, 16, "t", false, NAMES)));
    const still = M.rsChartHTML(st, 9, "count", true);
    ok("⭐ the phone's bars are a picture (run): no slider, no click, one description; initials under the bars",
       !still.includes("<input") && !still.includes("onclick") && still.includes('role="img" aria-label="Earthworks / soil · 133,500 t · May 2026 to Aug 2027. Busiest month Apr 2027, 132 a day"') && still.includes('<span class="rs-now">S</span>'));
    {
      const long = { rid: "R012", first: 1, last: 60, months: Array.from({ length: 60 }, (_, i) => ({ m: i + 1, t: 100, loads: 4, aday: 4 / 22 })), busiest: { m: 1, aday: 4 / 22 }, materials: ["Asphalt"], totalT: 6000 };
      const h = M.rsChartHTML(long, 30, "count", false, { rid: "R012" });
      ok("the chart (run): a 60-month route still draws one bar a month in one control, with years but no month letters", cols(h).length === 60 && h.includes('class="rs-plot rs-many"') && !/<span[^>]*>[JFMASOND]<\/span>/.test(h) && (h.match(/<button/g) || []).length === 0);
    }
    const plotMonth = new Function(fnSrc("function rsPlotMonth(x, left, width, first, n) {") + "\nreturn rsPlotMonth;")();
    ok("⭐ a click on the bars picks the month under the pointer (run): the middle of each of 16 columns gives months 5 to 20; outside the plot, the nearest end",
       Array.from({ length: 16 }, (_, i) => plotMonth(100 + (i + 0.5) * 36, 100, 576, 5, 16)).join() === Array.from({ length: 16 }, (_, i) => 5 + i).join()
       && plotMonth(90, 100, 576, 5, 16) === 5 && plotMonth(9999, 100, 576, 5, 16) === 20 && plotMonth(1, 0, 0, 5, 16) === null);
    ok("⭐ moving the month goes through the page's own pickMonth; the open panel follows a month move and the timeline closing",
       /function rsGoMonth\(m\) \{\s*m = parseInt\(m, 10\);\s*if \(m >= 1 && m <= \(CONFIG\.MONTH_COUNT \|\| 60\) && typeof pickMonth === 'function'\) pickMonth\(m\);/.test(html)
       && (html.match(/if \(typeof rsOnMonth === 'function'\) rsOnMonth\(\);/g) || []).length === 2
       && /function rsOnMonth\(\) \{\s*if \(!document\.body\.classList\.contains\('drawer-open'\)\) return;\s*if \(drawerTab === 'detail'\) \{ if \(typeof renderAllRoutes === 'function'\) renderAllRoutes\(\); return; \}\s*if \(RS\.rid\) renderRouteStory\(\);/.test(html));

    // the table
    const tm = M.rsTableHTML(st, 16, "count"), tt = M.rsTableHTML(st, 9, "t");
    const cells = h => (h.match(/<td[^>]*>(?:<button[^>]*>)?([^<]*)/g) || []).map(x => x.replace(/<[^>]*>/g, ""));
    ok("⭐ the table (run): a year to a line with real headings; movements a day 2026: – – – – 3 3 4 4 5 5 5 3, busiest 5; 2027: 3 4 119 132 119 4 3 3 – – – –, busiest 132",
       tm.includes('<th scope="col">Year</th><th scope="col">Jan</th>') && tm.includes('<th scope="col">Busiest</th>') && tm.includes('<th scope="row">2026</th>') && tm.includes('<th scope="row">2027</th>')
       && cells(tm).join() === "–,–,–,–,3,3,4,4,5,5,5,3,5,3,4,119,132,119,4,3,3,–,–,–,–,132", cells(tm).join());
    ok("⭐ the table (run): a figure is a button that moves the map; the map's month is framed and named current; the busiest is bold",
       tm.includes('<button type="button" class="rs-cell rs-now rs-peak" data-k="c16" onclick="rsGoMonth(16)" aria-current="true" aria-label="Apr 2027: 132 lorry movements a day">132</button>')
       && tm.includes('<button type="button" class="rs-cell" data-k="c9" onclick="rsGoMonth(9)" aria-label="Sep 2026: 5 lorry movements a day">5</button>') && (tm.match(/<button/g) || []).length === 16);
    ok("⭐ the table in tonnes (run): the last column is headed 'Total' (one 'Year' heading, the first): 10,100 and 123,400 (133,500 in all)",
       tt.includes('<th scope="col">Total</th></tr>') && (tt.match(/>Year</g) || []).length === 1 && cells(tt).filter((x, i) => i === 12 || i === 25).join("|") === "10,100|123,400" && tt.includes('aria-label="Apr 2027: 42,000 t">42,000</button>'));

    // the phone, Copy
    ok("⭐ the phone's button (run): 'Busiest month: Apr 2027 · 132 a day' goes to month 16; on that month it rests as 'Busiest month: Apr 2027 (this month)'",
       M.rsPhoneBusyHTML(st, 9) === '<button type="button" class="btn btn-ghost rs-busy" onclick="rsGoMonth(16)">Busiest month: Apr 2027 · 132 a day</button>'
       && M.rsPhoneBusyHTML(st, 16) === '<button type="button" class="btn btn-ghost rs-busy" disabled>Busiest month: Apr 2027 (this month)</button>');
    ok("⭐ the phone's route card draws the line and the bars before the month's figures, the button after them, and asks for the story when it opens (no read of its own)",
       html.includes("if (st) html += '<p class=\"rs-what\">' + escHtml(rsWhat(st)) + '</p>' + rsChartHTML(st, month, 'count', true);")
       && html.indexOf("rsChartHTML(st, month, 'count', true)") < html.indexOf("'<dl><dt>' + CW().label + ', ' + escHtml(monthLabel(month))")
       && html.includes("if (st) html += rsPhoneBusyHTML(st, month);")
       && html.includes("if (typeof rsLoad === 'function') rsLoad(String(rid)).then(() => { if (SHEET.card === String(rid)) renderRouteCard(); }).catch(() => {});"));
    const cp = M.rsCopyParts(st, NAMES, "https://app.example/map/", "12 Nov 2026");
    ok("⭐ Copy (run): the route's months as a table: a title, the line, 16 months with movements a day and tonnes, a total, where it came from",
       cp.tsv.split("\n")[0] === "Wolds Link (demo) · R050 · Tilton Viaduct site → Wolds Link Inert Landfill" && cp.tsv.split("\n")[1] === "Approved plan. Earthworks / soil · 133,500 t · May 2026 to Aug 2027."
       && cp.tsv.split("\n")[2] === "Month\tLorry movements a day\tTonnes" && cp.tsv.includes("Apr 2027\t132\t42,000") && cp.tsv.includes("Total\t\t133,500") && cp.tsv.split("\n").length === 21
       && cp.tsv.endsWith("From the Wayscope public map, 12 Nov 2026. https://app.example/map/") && cp.html.includes("<table") && cp.html.includes("Apr 2027"));
  }

  // ---------- the switches, the facts, the "i" boxes ----------
  const ctl = fnSrc("function rsCtlHTML(unit, view) {");
  ok("⭐ the switches: the unit by the organisation's own word (CW().col) and Tonnes; Chart, Table, Route facts; Copy; an 'i'. Each a real button that says which is on",
     !!ctl && ctl.includes("b('u-count', unit !== 't', 'rsSetUnit', 'count', CW().col) + b('u-t', unit === 't', 'rsSetUnit', 't', 'Tonnes')")
     && ctl.includes("b('v-chart', view === 'chart', 'rsSetView', 'chart', 'Chart') + b('v-table', view === 'table', 'rsSetView', 'table', 'Table') + b('v-facts', view === 'facts', 'rsSetView', 'facts', 'Route facts')")
     && ctl.includes('aria-pressed="\' + on + \'"') && ctl.includes('onclick="rsCopy(this)">Copy</button>') && ctl.includes('aria-controls="info-route-story" onclick="toggleInfo(this)"'));
  const facts = fnSrc("function rsFactsHTML(rid, story) {");
  ok("⭐ Route facts: six cards with the words put right (One way, by road · Round trip with loading · Round trips a lorry a day · Loads in all · CO₂e (est.) · CO₂e a tonne moved)",
     !!facts && ["'One way, by road'", "'Round trip with loading'", "'Round trips a lorry a day'", "'Loads in all'", "'CO₂e (est.)'", "'CO₂e a tonne moved'"].every(w => facts.includes(w))
     && (facts.match(/\+ c\(/g) || []).length === 6 && facts.includes("routeWordsHTML(rid)") && facts.includes("Driving directions ↗"));
  ok("a failed carbon read says so and a month with no figure is 'not routed yet' (two different states); a lorry that cannot make one round trip in a day says why",
     !!facts && facts.includes("story.co2Error ? ', carbon could not be read'") && facts.includes("' not routed yet'") && facts.includes("'one round trip does not fit a driver\\'s day'")
     && rsStory("R050", Object.assign({}, months, { 16: Object.assign({}, months[16], { co2_error: "x" }) }), 22, 1, 60).co2Error === true && st.co2Error === false);
  ok("⭐ the carbon figure is still the server's (summed from each line's co2_t in rsStory), with no factor read and no arithmetic of its own in the panel",
     /if \(l\.co2_t == null \|\| kp\.co2_error\) \{ if \(q > 0\) miss\+\+; \} else \{ co2 \+= Number\(l\.co2_t\); baked \+= q; \}/.test(block) && !/vehicle_emissions_kg_co2e_per_km/.test(block) && !/\*\s*emis/.test(block));
  const words = t => t.replace(/<[^>]+>/g, " ").replace(/’/g, "'").trim().split(/\s+/).filter(Boolean).length;
  const co2Tip = (/id="info-route-co2" hidden><p>([^<]*)<\/p>/.exec(html) || [])[1] || "";
  ok("⭐ the carbon 'i' says what is counted in 30 words or fewer and names no source: exhaust emissions of each loaded journey and the scheme's share of the empty return",
     co2Tip === "A planning estimate: exhaust emissions of each loaded journey and the scheme’s share of the empty return. The same figure as the bar." && words(co2Tip) <= 30 && !/DESNZ|DEFRA/.test(co2Tip));
  const tipLine = "'Approved plan. A month’s loads over its working days. ' + CW().note + ' Click a month to move the map.'";
  ok("⭐ the chart's 'i' is 30 words or fewer in either unit and uses the organisation's own counting sentence",
     html.includes("words.textContent = " + tipLine) && words("Approved plan. A month's loads over its working days. " + CWm.note + " Click a month to move the map.") <= 30
     && words("Approved plan. A month's loads over its working days. " + CWv.note + " Click a month to move the map.") <= 30);
  ok("⭐ the guide link in an 'i' shows to staff only (the guide is behind the staff sign-in): hidden in the markup, shown when the page knows a staff viewer",
     html.includes('<a id="info-route-story-guide" href="/help/#ug-map-route-panel" target="_blank" rel="noopener" hidden>User guide</a>')
     && html.includes("if (guide) guide.hidden = !RME.staff;") && html.includes("'<p><a href=\"/help/#ug-map-route-panel\" target=\"_blank\" rel=\"noopener\"' + (RME.staff ? '' : ' hidden') + '>User guide</a></p>"));

  // ---------- the look: the strip's real room, the keyboard, Dark, the phone ----------
  const css = (sel) => { const i = html.indexOf("\n        " + sel + "{"); return i < 0 ? "" : html.slice(i, html.indexOf("}", i) + 1); };
  ok("⭐ the strip: the story and the months side by side; the panel's own padding is 10 px so the story fits 169 px without scrolling",
     /\.rs-two\{ display:grid; grid-template-columns:minmax\(0, 484px\) minmax\(0, 1fr\); gap:22px; \}/.test(html) && css("#drawer-analysis").includes("padding:10px 16px;")
     && html.includes("@media (max-height:680px){ .rs-plot{ height:80px; }"));
  ok("⭐ a place name is NEVER cut on 'This route': the number and team drop to the line below when the two do not fit, then the name wraps; if the strip is then full the description line gives way",
     css(".rs-title").includes("flex-wrap:wrap;") && !/ellipsis|nowrap|overflow:hidden/.test(css(".rs-title span")) && css(".rs-title small").includes("white-space:nowrap;")
     && html.includes("if (box.scrollHeight > box.clientHeight + 1) { const d = box.querySelector('.rs-desc'); if (d) d.hidden = true; }"));
  ok("⭐ the four figures stay on one line, and the pale bars are 3:1 against the panel (#6690E3 on white)",
     css(".rs-figs").includes("display:flex;") && !css(".rs-figs").includes("wrap") && css(".rs-col i").includes("background:#6690E3;"));
  ok("⭐ after the busiest-month button has done its job (it is no longer a button on that month) the keyboard is on the months, not lost",
     html.includes("|| (held === 'go' ? document.getElementById('rs-range') : null);"));
  ok("⭐ the slider is kept out of sight for the keyboard, as the timeline's is, and the bars show the focus",
     css(".rs-chart input[type=range]").includes("clip:rect(0,0,0,0)") && css(".rs-chart:focus-within .rs-plot").includes("outline:2px solid #1D4ED8;"));
  ok("⭐ nothing in the panel is under 12 px, and every button in it has a visible keyboard focus",
     !(html.slice(html.indexOf("        .rs-ctl{"), html.indexOf("        .route-card .rs-yl{")).match(/font-size:(\d+(\.\d+)?)px/g) || []).some(x => parseFloat(x.split(":")[1]) < 12)
     && html.includes(".rs-seg button:focus-visible, .rs-bt:focus-visible, .rs-go:focus-visible, .rs-cell:focus-visible{ outline:2px solid #1D4ED8; outline-offset:-2px; }"));
  ok("⭐ Dark (the map inside the app): the bars, the marked month, the pressed switch, the links and the focus ring each have a Dark rule",
     ['html[data-look="dark"] .rs-col i{', 'html[data-look="dark"] .rs-col.rs-now i{', 'html[data-look="dark"] .rs-col.rs-now::before{', 'html[data-look="dark"] .rs-seg button[aria-pressed="true"]{',
      'html[data-look="dark"] .rs-cell.rs-now{', 'html[data-look="dark"] .rs-chart:focus-within .rs-plot{'].every(x => html.includes(x)));
  ok("the phone still has no route panel (the card in the sheet carries the story); the bars there take no pointer",
     html.includes("#kpi-hud, #menu-toggle, #timeline-bar, #tl-warnings, #route-drawer, #btn-detail{ display:none !important; }") && css(".route-card .rs-plot").includes("cursor:default;"));
  ok("⭐ the load's description comes from the matrix the page already reads when it opens (the line with the most volume speaks)",
     html.includes("if (rt.material_description && String(rt.material_description).trim() && (Number(rt.total)||0) >= (acc.descOf||0)) { acc.desc = String(rt.material_description).trim(); acc.descOf = Number(rt.total)||0; }"));

  // ---------- the guides ----------
  const sec = (src, id) => { const i = src.indexOf('id="' + id + '"'); return i < 0 ? "" : src.slice(i, i + 3200); };
  const ug = sec(guide, "ug-map-route-panel");
  ok("⭐ user guide: the route panel's paragraph names This route and All routes, the line, the bars that move the map, Table and Route facts, and no back-end word",
     !!ug && /This route/.test(ug) && /All routes/.test(ug) && /click one and the map moves/i.test(ug) && /Table/.test(ug) && /Route facts/.test(ug)
     && !/\/api\/|endpoint|KPI\.cache|rsStory|fetch/.test(ug.slice(0, 1500)));
  ok("⭐ user guide: the old panel's sentence is gone ('The route analysis panel opens over the foot of the map', 'Full route analysis' stays the popup's own button)",
     !guide.includes("The route analysis panel opens over the foot of the map"));
  ok("user guide: the carbon source the screen no longer names is named in its sources (A.1 / A.2)", /DESNZ/.test(guide.slice(guide.indexOf('id="a-1')) || ""));
  const t1 = sec(tech, "t1-route-story");
  ok("⭐ technical guide: where each figure comes from, that the panel reads nothing of its own, and the carbon source and method that left the screen",
     !!t1 && t1.includes("<code>rsStory</code>") && t1.includes("<code>routeFigures</code>") && /no read of its own/i.test(t1) && /DESNZ/.test(t1) && t1.includes("<code>rsOnMonth</code>"));

  for (const f of fail) console.log("  FAIL: " + f);
  console.log(`${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
