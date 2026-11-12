/* ui_fix_map_all_routes.js — 12 Nov 2026, branch claude/ui-map-forecast-detail-1111 (John, 12 Nov: "Yes, option A", to the
 * page notes\ux-map-forecast-detail-1111; step A2, "All routes"). Source checks on map/index.html, the server and the two
 * guides, plus sandboxes that run the page's OWN functions against stand-ins; no browser (the browser half is the Chrome
 * check in the session note). The server's half of the file (staff only) is test_forecast_plan.py and smoke_forecast_plan.py.
 *
 *   The route panel's second tab was 91 rows by 62 columns of tonnes: one or two rows in view, the material a colour square
 *   (three colours shared by two materials each), "91 route(s)" for 49 routes, no totals, no tie to the map's month, and its
 *   own read of the whole plan. A2: a year at a time, a row a route, the route and its material in words, the map's month
 *   tinted, a totals row that stays in view, sort by any heading, a material filter, Copy, a staff Download, "Taller"; the
 *   Control Panel's button is always there and reads "All routes by month". No read of its own.
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
const main = read("backend", "main.py");
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 500) : "")); console.log("  ✗ " + label); }
}
const TRY = (f) => { try { return f(); } catch (e) { return false; } };
const fnSrc = (head) => { const a = html.indexOf("    " + head); if (a < 0) return ""; const b = html.indexOf("\n    }", a); return b < 0 ? "" : html.slice(a, b + 6); };
const fmtN = (n, d) => (Math.round(n * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toLocaleString("en-GB");
const escHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const rsN = x => (x > 0 && x < 1 ? "under 1" : fmtN(x || 0, 0));
const RS_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CWm = { label: "Lorry movements a day", lower: "lorry movements a day", col: "Movements a day", note: "A lorry coming and going is 2 movements, as councils count them." };
const CWv = { label: "Lorry visits a day", lower: "lorry visits a day", col: "Visits a day", note: "A lorry coming and going is 1 visit (2 movements as councils count them)." };

// ---------- the stand-in: 2027 (months 13 to 24) as the demo holds four of its routes; 22 working days ----------
const T50 = { 13: 1100, 14: 1300, 15: 38000, 16: 42000, 17: 38000, 18: 1200, 19: 1000, 20: 800 };
const months = {};
for (let m = 1; m <= 60; m++) {
  const lines = [];
  if (T50[m]) lines.push({ route_id: "R050", material_type: "Earthworks / soil", qty_t: T50[m], vehicle_loads: Math.round(T50[m] / 29 * 1000) / 1000 });
  if (m >= 13 && m <= 20) {      // R011: two work lines a month, two materials: one row
    lines.push({ route_id: "R011", material_type: "Small aggregate", qty_t: 6000, vehicle_loads: 220 });
    lines.push({ route_id: "R011", material_type: "Asphalt", qty_t: 900, vehicle_loads: 110 });
  }
  if (m >= 16 && m <= 24) lines.push({ route_id: "R019", material_type: "Earthworks / soil", qty_t: 5400, vehicle_loads: 187 });
  if (m === 24) lines.push({ route_id: "R006", material_type: "General / imported", qty_t: 9, vehicle_loads: 1 });
  if (m === 30) lines.push({ route_id: "R099", material_type: "Asphalt", qty_t: 50, vehicle_loads: 2 });
  months[m] = { working_days: 22, lines };
}
const namesOf = (rid) => ({ rid, from: rid === "R050" ? "Tilton Viaduct site" : "Quarry <b>", to: rid === "R050" ? "Wolds Link Inert Landfill" : "Compound", team: "" });

(async () => {
  // ---------- no read of its own; the old table and its read are gone ----------
  const ofd = fnSrc("async function openForecastDetail(){");
  ok("⭐ NO READ: 'All routes' asks the server for nothing (the page's own read of the plan, fetchMatrix, is gone from the page with its cache); it waits on the month figures the page loads when it opens",
     !!ofd && !html.includes("fetchMatrix") && !html.includes("FCACHE") && !/\bfetch\(/.test(ofd) && ofd.includes("await ensureTimelineMatrix();") && ofd.includes("await kpiFetchAll();")
     && ofd.includes("if (TL.matrix && KPI.allDone) { renderAllRoutes(); return; }"));
  ok("NO READ: only if that one read failed are the months of the year on screen read, one at a time, through the page's existing month read",
     ofd.includes("catch (e) { await arFetchYear(); }") && /async function arFetchYear\(\) \{[\s\S]{0,520}try \{ await kpiFetchMonth\(m\); \} catch \(e\) \{\}/.test(html));
  ok("⭐ the 60-column table is gone: no colour key (a square was the only sign of the material, and ten materials shared seven colours), no 'route(s)', no 'Window', no 11.5 px type",
     !/MAT_PALETTE|materialColorMap|mat-chip|fc-matrix|route\(s\) · sorted by total|tonnes of material by month/.test(html) && !/'<div class="an-route">Window '/.test(html));

  // ---------- the rows: the page's own functions ----------
  const yrSrc = fnSrc("function arYearRows(months, y, wdDefault) {"), vwSrc = fnSrc("function arView(rows, opt) {");
  ok("⭐ arYearRows and arView are in the page", !!yrSrc && !!vwSrc);
  const arYearRows = TRY(() => new Function(yrSrc + "\nreturn arYearRows;")()) || (() => []);
  const arView = TRY(() => new Function(vwSrc + "\nreturn arView;")()) || (() => ({ rows: [], tot: { t: [], aday: [] }, mats: [] }));
  const rows = arYearRows(months, 1, 22);
  const by = {}; rows.forEach(r => { by[r.rid] = r; });
  ok("⭐ arYearRows (run), 2027: one row a ROUTE (R011's two work lines are one row); a route with nothing that year is left out",
     rows.map(r => r.rid).sort().join() === "R006,R011,R019,R050" && !!by.R011 && by.R011.t[0] === 6900 && Math.abs(by.R011.aday[0] - 330 / 22) < 1e-9, rows.map(r => r.rid));
  ok("⭐ arYearRows (run): R050 in 2027 is 1,100 1,300 38,000 42,000 38,000 1,200 1,000 800 t = 123,400 t; Apr is 65.8 visits a day = 132 movements, its busiest",
     !!by.R050 && by.R050.t.slice(0, 8).join() === "1100,1300,38000,42000,38000,1200,1000,800" && by.R050.yearT === 123400
     && Math.round(by.R050.aday[3] * 2) === 132 && Math.round(by.R050.peak * 2) === 132 && by.R050.t[8] === 0);
  ok("arYearRows (run): a route's materials are named, biggest first", !!by.R011 && by.R011.materials.join() === "Small aggregate,Asphalt" && by.R050.materials.join() === "Earthworks / soil");
  const v = arView(rows.slice(), { mat: "", sort: "month", k: 3, unit: "count" });
  ok("⭐ arView (run): sorted by the map's month (Apr 2027), busiest first: R050 (132), R011 (30), R019 (17); a route with nothing that month last",
     v.rows.map(r => r.rid).join() === "R050,R011,R019,R006", v.rows.map(r => r.rid));
  ok("⭐ arView (run): the totals add the rows shown: Apr 2027 = 131.66 + 30 + 17 = 179 movements a day; the year 123,400 + 55,200 + 48,600 + 9 t; the busiest month of the total",
     Math.round(v.tot.aday[3] * 2) === 179 && v.tot.t[3] === 42000 + 6900 + 5400 && v.tot.yearT === 123400 + 8 * 6900 + 9 * 5400 + 9 && Math.abs(v.tot.peak - Math.max.apply(null, v.tot.aday)) < 1e-9);
  ok("⭐ arView (run): one material shows only the routes that carry it, and the totals are theirs; the materials offered are the year's, A to Z",
     arView(rows.slice(), { mat: "Asphalt", sort: "month", k: 3, unit: "count" }).rows.map(r => r.rid).join() === "R011"
     && arView(rows.slice(), { mat: "Earthworks / soil", sort: "month", k: 3, unit: "count" }).tot.t[3] === 47400
     && v.mats.join() === "Asphalt,Earthworks / soil,General / imported,Small aggregate");
  ok("⭐ arView (run): any heading sorts: Route A to Z (by number), Material A to Z, the last column biggest first; with the map on another year the month sort falls back to the last column",
     arView(rows.slice(), { mat: "", sort: "route", k: 3, unit: "count" }).rows.map(r => r.rid).join() === "R006,R011,R019,R050"
     && arView(rows.slice(), { mat: "", sort: "material", k: 3, unit: "count" }).rows.map(r => r.rid).join() === "R019,R050,R006,R011"
     && arView(rows.slice(), { mat: "", sort: "last", k: 3, unit: "t" }).rows.map(r => r.rid).join() === "R050,R011,R019,R006"
     && arView(rows.slice(), { mat: "", sort: "month", k: null, unit: "count" }).rows[0].rid === "R050");

  // ---------- the table as drawn ----------
  const mk = (PVn) => TRY(() => new Function("CONFIG", "PV", "fmtN", "rsN", "escHtml", "RS_MONTHS", fnSrc("function arTableHTML(view, y, k, unit, sort, picked, namesOf) {") + "\nreturn arTableHTML;")(
    { START_YEAR: 2026 }, () => PVn, fmtN, rsN, escHtml, RS_MONTHS));
  const arTableHTML = mk(2);
  ok("⭐ arTableHTML is in the page", !!arTableHTML);
  if (arTableHTML) {
    const h = arTableHTML(v, 1, 3, "count", "month", "r011", namesOf);
    const cells = (tr) => (tr.match(/<td[^>]*>([^<]*)<\/td>/g) || []).map(x => x.replace(/<[^>]*>/g, ""));
    const trs = h.slice(h.indexOf("<tbody>"), h.indexOf("</tbody>")).split("</tr>").filter(x => x.includes("<tr"));
    ok("⭐ the table (run): a row a route with its number, 'from → to' and its material in words; R050: 3 4 119 132 119 4 3 3 – – – –, Busiest 132",
       trs.length === 4 && trs[0].includes('data-rid="R050"') && trs[0].includes("Tilton Viaduct site → Wolds Link Inert Landfill")
       && cells(trs[0]).join("|") === "Earthworks / soil|3|4|119|132|119|4|3|3|–|–|–|–|132", cells(trs[0]).join("|"));
    ok("⭐ the table (run): real headings: twelve months and 'Busiest'; the map's month is tinted in every row and marked as the sort; a month's heading is a button that moves the map",
       h.includes('<th scope="col" class="ar-now" aria-sort="descending"><button type="button" class="ar-h" data-k="h-m16" onclick="arMonth(16)" aria-label="Apr 2027: move the map to this month">Apr</button></th>')
       && (h.match(/<th scope="col"/g) || []).length === 15 && (h.match(/class="ar-now"/g) || []).length === 1 + 4 + 1 && h.includes('onclick="arSort(\'last\')">Busiest</button>')
       && (h.match(/<th scope="row">/g) || []).length === 5);
    ok("⭐ the table (run): a totals row that says how many routes it adds: 'All 4 routes', Apr 2027 = 179, Busiest = the total's busiest month",
       /<tfoot><tr><th scope="row">All 4 routes<\/th><td class="ar-l"><\/td>/.test(h) && cells(h.slice(h.indexOf("<tfoot>")))[4] === "179");
    ok("⭐ the table (run): a route's number is a button, as on the road card: it says what it does, and the picked route's row is tinted and its button says the next click opens the route",
       h.includes('data-rid="R050" onclick="arPick(this.dataset.rid)" aria-pressed="false" aria-label="Show R050 on the map">R050</button>')
       && /<tr class="ar-picked"><th scope="row"><button type="button" class="ar-rid" data-k="r-R011" data-rid="R011" onclick="arPick\(this\.dataset\.rid\)" aria-pressed="true" aria-label="Open R011, this route">/.test(h)
       && (h.match(/<tr class="ar-picked">/g) || []).length === 1);
    ok("⭐ the table (run): a typed name is escaped; a route with two materials names both; under one a day reads '<1' in a month's narrow cell",
       h.includes("Quarry &lt;b&gt; → Compound") && !h.includes("Quarry <b>") && trs[1].includes('<td class="ar-l">Small aggregate, Asphalt</td>') && cells(trs[3]).slice(-2).join("|") === "<1|<1".replace(/</g, "&lt;"));
    const t = arTableHTML(arView(rows.slice(), { mat: "", sort: "month", k: 3, unit: "t" }), 1, 3, "t", "month", "", namesOf);
    ok("⭐ the table in tonnes (run): R050's Apr is 42,000 and its last column, 'Year', 123,400", t.includes('onclick="arSort(\'last\')">Year</button>') && cells(t.slice(t.indexOf("<tbody>")).split("</tr>")[0]).slice(-1)[0] === "123,400" && t.includes(">42,000</td>"));
    ok("⭐ the unit follows the organisation's setting (run): counting visits, R050's Apr reads 66", cells(mk(1)(v, 1, 3, "count", "month", "", namesOf).slice(h.indexOf("<tbody>") - 400).split("</tr>").find(x => x.includes('data-rid="R050"')))[4] === "66");
    ok("the table (run): a year with nothing says so in one line", arTableHTML({ rows: [], tot: { t: [], aday: [] }, mats: [] }, 3, null, "count", "month", "", namesOf).includes('<td class="ar-none" colspan="15">Nothing approved in 2029.</td>'));
  }

  // ---------- the switches ----------
  const ctlSrc = fnSrc("function arCtlHTML(y, y0, y1, mats, mat, unit, tall, staff) {");
  const arCtlHTML = TRY(() => new Function("CONFIG", "CW", "escHtml", ctlSrc + "\nreturn arCtlHTML;")({ START_YEAR: 2026 }, () => CWm, escHtml));
  ok("⭐ arCtlHTML is in the page", !!arCtlHTML);
  if (arCtlHTML) {
    const c = arCtlHTML(1, 0, 4, ["Asphalt", "Earthworks / soil"], "Asphalt", "count", false, false);
    ok("⭐ the switches (run): the year between a 'Previous year' and a 'Next year' button (their arrows drawn by CSS, each named), a material list that opens on 'All materials', the unit, Copy, Taller and an 'i'",
       c.includes('<button type="button" class="ar-prev" data-k="y-prev" onclick="arYear(-1)" aria-label="Previous year"></button><span class="ar-yr" aria-live="polite">2027</span><button type="button" class="ar-next" data-k="y-next" onclick="arYear(1)" aria-label="Next year"></button>')
       && c.includes('<select id="ar-mat" class="ar-mat" aria-label="Material" onchange="arSetMat(this.value)"><option value="">All materials</option><option value="Asphalt" selected>Asphalt</option>')
       && c.includes('aria-pressed="true" onclick="rsSetUnit(\'count\')">Movements a day</button>') && c.includes('onclick="arCopy(this)">Copy</button>')
       && c.includes('data-k="tall" aria-pressed="false" onclick="arTall()">Taller</button>') && c.includes('aria-controls="info-all-routes"'));
    ok("⭐ the year buttons stop at the first and the last year with anything approved", arCtlHTML(0, 0, 4, [], "", "count", false, false).includes('aria-label="Previous year" disabled') && arCtlHTML(4, 0, 4, [], "", "count", false, false).includes('aria-label="Next year" disabled'));
    ok("⭐ DOWNLOAD IS FOR STAFF (run): a visitor's switches carry no link to the file at all; a staff viewer's carry one, in the unit on screen",
       !/forecast-plan|Download/.test(c) && arCtlHTML(1, 0, 4, [], "", "t", true, true).includes('<a class="rs-bt ar-dl" data-k="dl" href="/api/routes/forecast-plan.csv?unit=t" download>Download</a>')
       && arCtlHTML(1, 0, 4, [], "", "count", true, true).includes('href="/api/routes/forecast-plan.csv?unit=count"') && arCtlHTML(1, 0, 4, [], "", "t", true, true).includes('data-k="tall" aria-pressed="true"'));
  }
  ok("⭐ ...and the page draws the link only when it knows a staff viewer (RME.staff, from the server's own answer)", html.includes("const h = arCtlHTML(st.y, st.y0, st.y1, st.view.mats, AR.mat, RS.unit, AR.tall, RME.staff);"));
  ok("⭐ ...and the SERVER refuses the file to anyone else, whatever the page shows: the endpoint checks for staff before it builds anything",
     /@app\.get\("\/api\/routes\/forecast-plan\.csv"\)\ndef routes_forecast_plan_csv\([\s\S]{0,1600}?if not _staff_request\(request\):\s*\n\s*raise HTTPException\(401, [^\n]*\n\s*if unit not in forecast_plan\.UNITS:[\s\S]{0,200}?data = _staff_bytes\(/.test(main)
     && main.indexOf("if not _staff_request(request):\n        raise HTTPException(401, \"sign in — the plan as a file is for staff\")") < main.indexOf('data = _staff_bytes("routes/forecast-plan"'));

  // ---------- the month, the year, the pick, Taller ----------
  const stSrc = fnSrc("function arState() {");
  ok("⭐ the year follows the map's month when the month MOVES, and the year buttons hold until it does; the map's month is tinted only in its own year",
     /if \(month !== AR\.month\) \{ AR\.month = month; if \(month\) AR\.year = Math\.floor\(\(month - 1\) \/ 12\); \}/.test(stSrc)
     && stSrc.includes("const y = AR.year, k = month && Math.floor((month - 1) / 12) === y ? (month - 1) % 12 : null;") && stSrc.includes("AR.year = Math.min(y1, Math.max(y0, AR.year));"));
  TRY(() => {
    const TL = { on: true, month: 16 }, AR = { year: null, month: undefined, mat: "", sort: "month" }, RS = { unit: "count" }, KPI = { cache: months };
    const arState = new Function("forecastWindow", "TL", "AR", "RS", "KPI", "FORECAST_WORKING_DAYS", "arYearRows", "arView", stSrc + "\nreturn arState;")(() => [1, 60], TL, AR, RS, KPI, 22, arYearRows, arView);
    const a = arState(); const y1 = a.y, k1 = a.k;
    AR.year = 2; const b = arState();          // the year button: 2028, the month has not moved
    TL.month = 30; const c = arState();        // the month moves to Jun 2028
    TL.month = 9; const d = arState();         // ... and to Sep 2026
    ok("⭐ arState (run): opens on the map's year with its month marked (2027, Apr); a year button moves the year and unmarks the month; a month move brings the year back with it",
       y1 === 1 && k1 === 3 && b.y === 2 && b.k === null && c.y === 2 && c.k === 5 && d.y === 0 && d.k === 8, [y1, k1, b.y, b.k, c.y, c.k, d.y, d.k]);
    AR.mat = "Asphalt"; TL.month = 16; const e = arState(); TL.month = 9; const f = arState();
    ok("arState (run): a material that the year on screen does not carry is dropped (the list would show 'All materials' over a filtered table)", e.view.rows.length === 1 && AR.mat === "" && f.view.rows.length === 0);
    return true;
  }) || ok("⭐ arState (run): opens on the map's year with its month marked; a year button moves the year; a month move brings the year back", false);
  ok("⭐ a month's heading moves the map through the page's own pickMonth and the rows follow it; the open table follows any month move (rsOnMonth)",
     html.includes("function arMonth(m) { AR.sort = 'month'; rsGoMonth(m); renderAllRoutes(); }")
     && /function rsOnMonth\(\) \{\s*if \(!document\.body\.classList\.contains\('drawer-open'\)\) return;\s*if \(drawerTab === 'detail'\) \{ if \(typeof renderAllRoutes === 'function'\) renderAllRoutes\(\); return; \}/.test(html));
  const pickSrc = fnSrc("function arPick(rid) {");
  TRY(() => {
    const calls = { sel: [], open: [], draw: 0 }; let selectedRouteId = null;
    const mkPick = (cur) => new Function("selectedRouteId", "selectRoute", "openRouteAnalysis", "renderAllRoutes", pickSrc + "\nreturn arPick;")(cur, id => calls.sel.push(id), id => calls.open.push(id), () => calls.draw++);
    mkPick(null)("R011"); const first = calls.sel.join() === "R011" && calls.open.length === 0 && calls.draw === 1;
    mkPick("r011 ")("R011"); const second = calls.open.join() === "R011" && calls.sel.length === 1;
    mkPick("R050")(""); const empty = calls.sel.length === 1 && calls.open.length === 1;
    ok("⭐ arPick (run): the first click lights the route on the map (selectRoute, as a picked route is) and tints its row; a click on the lit route opens 'This route'; an empty id does nothing", first && second && empty);
    return true;
  }) || ok("⭐ arPick (run): the first click lights the route; a click on the lit route opens 'This route'", false);
  ok("⭐ the picked route comes first (11 Nov's rule, kept) and a newly picked one is shown; the table keeps its scroll and the keyboard its place when it is drawn again; a year button that has reached the end hands the keyboard to its neighbour",
     html.includes("st.view.rows = arPickedFirst(st.view.rows, picked);") && html.includes("if (picked !== AR.picked) { AR.picked = picked; if (picked) box.scrollTop = 0; }")
     && TRY(() => { const f = new Function(fnSrc("function arPickedFirst(rows, picked) {") + "\nreturn arPickedFirst;")(); const r = [{ rid: "R1" }, { rid: " R2" }, { rid: "R3" }];
                    return f(r, "r2").map(x => x.rid.trim()).join() === "R2,R1,R3" && f(r, "").map(x => x.rid.trim()).join() === "R1,R2,R3" && f(r, "r9").length === 3; })
     && html.includes("box.scrollTop = top; box.scrollLeft = left;")
     && html.includes("if (again && again.disabled && ctl) again = ctl.querySelector('[data-k=\"' + (held === 'y-prev' ? 'y-next' : 'y-prev') + '\"]');"));
  ok("⭐ Taller: the table takes most of the window (80 % of its height) while its tab is on screen, the Conditions panel steps aside, and the drawer still opens and closes by its class only",
     html.includes("body.drawer-open.drawer-tall #route-drawer{ height:80vh; max-height:80vh; }") && html.includes("body.drawer-open.drawer-tall #tl-warnings{ display:none; }")
     && html.includes("document.body.classList.toggle('drawer-tall', AR.tall && drawerTab === 'detail');")
     && html.includes("document.body.classList.toggle('drawer-tall', tab === 'detail' && typeof AR !== 'undefined' && AR.tall);")
     && (html.match(/getElementById\('route-drawer'\)\.(style|classList)\b/g) || []).length === 2);

  // ---------- Copy ----------
  TRY(() => {
    const arCopyParts = new Function("CONFIG", "TENANT", "CW", "PV", "fmtN", "rsN", "escHtml", "RS_MONTHS", fnSrc("function arCopyParts(st, unit, mat, namesOf, link, when) {") + "\nreturn arCopyParts;")(
      { START_YEAR: 2026 }, { name: "Wolds Link", demo_notice: "Fictional scheme" }, () => CWm, () => 2, fmtN, rsN, escHtml, RS_MONTHS);
    const cp = arCopyParts({ y: 1, view: v }, "count", "", namesOf, "https://app.example/map/", "12 Nov 2026"), L = cp.tsv.split("\n");
    ok("⭐ Copy (run): the year's table as shown: a title, what it counts, the headings with the year, a row a route (from, to and material as words), the totals, where it came from",
       L[0] === "Wolds Link (demo) · All routes · 2027" && L[1] === "Approved plan, lorry movements a day." && L[2].startsWith("Route\tFrom\tTo\tMaterial\tJan 2027\t") && L[2].endsWith("\tDec 2027\tBusiest")
       && L[3].startsWith("R050\tTilton Viaduct site\tWolds Link Inert Landfill\tEarthworks / soil\t3\t4\t119\t132\t") && L[L.length - 2].startsWith("All 4 routes\t\t\t\t") && L.length === 3 + 4 + 2
       && L[L.length - 1] === "From the Wayscope public map, 12 Nov 2026. https://app.example/map/" && cp.html.includes("<table") && cp.html.includes("Quarry &lt;b&gt;"), L.slice(0, 4));
    return true;
  }) || ok("⭐ Copy (run): the year's table as shown", false);
  ok("⭐ both tabs' Copy write the clipboard through one function", (html.match(/rsClip\(/g) || []).length === 3 && html.includes("function rsClip(parts, btn) {"));

  // ---------- the Control Panel's button, the look ----------
  ok("⭐ the Control Panel's button is always there and names what it opens: 'All routes by month' (it was 'Forecast detail table', hidden unless 'Show forecast routes' was ticked)",
     html.includes('<button type="button" class="btn btn-ghost" id="btn-detail" onclick="openForecastDetail()">All routes by month</button>')
     && html.includes("#btn-detail{ margin-top:8px; }") && !/#btn-detail\{[^}]*display:none; \}/.test(html.replace(/#btn-detail\{ display:none !important; \}/g, "")) && !/bd\.style\.display/.test(html)
     && !html.includes("if (typeof closeDrawer === 'function' && drawerTab === 'detail') closeDrawer();"));
  ok("it stays off a phone and off wall mode, with the panel", html.includes("#kpi-hud, #menu-toggle, #timeline-bar, #tl-warnings, #route-drawer, #btn-detail{ display:none !important; }") && /body\.wall-mode #btn-detail/.test(html));
  const css = (sel) => { const i = html.indexOf("\n        " + sel + "{"); return i < 0 ? "" : html.slice(i, html.indexOf("}", i) + 1); };
  ok("⭐ the headings and the totals stay put while the rows scroll, in the tab's own scroller (one scroller: the old table's headings scrolled away with it); the cells that stay put are solid",
     css("table.ar-table thead th").includes("position:sticky; top:0;") && css("table.ar-table tfoot th, table.ar-table tfoot td").includes("position:sticky; bottom:0;")
     && css("table.ar-table tbody th, table.ar-table tfoot th").includes("position:sticky; left:0;") && css("table.ar-table th, table.ar-table td").includes("background:var(--surface);")
     && css("#drawer-detail").includes("padding:0 16px;") && !html.includes('<div style="overflow:auto;"><table'));
  ok("⭐ nothing in the table is under 12 px; every button in it shows the keyboard's focus; the arrows are drawn by CSS on named buttons",
     !(html.slice(html.indexOf("        #route-drawer .drawer-head{"), html.indexOf("        /* a laptop-height window")).match(/font-size:(\d+(\.\d+)?)px/g) || []).some(x => parseFloat(x.split(":")[1]) < 12)
     && html.includes(".ar-h:focus-visible, .ar-rid:focus-visible, .ar-mat:focus-visible, a.ar-dl:focus-visible{ outline:2px solid #1D4ED8; outline-offset:-2px; }")
     && html.includes('.ar-prev::before{ content:"\\25C0"; } .ar-next::before{ content:"\\25B6"; }'));
  ok("⭐ Dark (the map inside the app): the tinted month, the picked row, the totals' month, the route numbers and the year each have a Dark rule, solid like the light ones",
     ['html[data-look="dark"] table.ar-table .ar-now, html[data-look="dark"] table.ar-table tr.ar-picked th, html[data-look="dark"] table.ar-table tr.ar-picked td{ background:#202F50; }',
      'html[data-look="dark"] table.ar-table tfoot .ar-now{', 'html[data-look="dark"] th.ar-now .ar-h, html[data-look="dark"] .ar-rid{ color:#8FB3F5; }', 'html[data-look="dark"] .ar-yr,'].every(x => html.includes(x)));
  const words = t => t.replace(/’/g, "'").trim().split(/\s+/).filter(Boolean).length;
  ok("⭐ the table's 'i' is 30 words or fewer in either unit, uses the organisation's own counting sentence, and its guide link shows to staff only",
     html.includes("words.textContent = 'Approved plan, a year at a time. ' + CW().note + ' A route’s number shows it on the map.';")
     && words("Approved plan, a year at a time. " + CWm.note + " A route's number shows it on the map.") <= 30 && words("Approved plan, a year at a time. " + CWv.note + " A route's number shows it on the map.") <= 30
     && html.includes('<a id="info-all-routes-guide" href="/help/#ug-map-route-panel" target="_blank" rel="noopener" hidden>User guide</a>') && html.includes("if (guide) guide.hidden = !RME.staff;"));
  ok("with no route picked the panel has no 'This route' tab; its switches are the tab's own", html.includes("{ const ta = document.getElementById('tab-analysis'); if (ta && typeof RS !== 'undefined') ta.hidden = !RS.rid; }") && html.includes("if (!box || drawerTab !== 'detail') return;"));

  // ---------- the guides ----------
  const sec = (src, id) => { const i = src.indexOf('id="' + id + '"'); return i < 0 ? "" : src.slice(i, i + 4200); };
  const ug = sec(guide, "ug-map-route-panel");
  ok("⭐ user guide: All routes is a year at a time with the totals, the sort, the material list, Copy, Taller and (for staff) Download; the Control Panel's button is named as it reads",
     /a year at a time/.test(ug) && /totals/.test(ug) && /Taller/.test(ug) && /Download/.test(ug) && /staff/.test(ug) && guide.includes("<strong>All routes by month</strong>") && !guide.includes("<strong>Forecast detail table</strong>"));
  const t1 = sec(tech, "t1-all-routes");
  ok("⭐ technical guide: where the rows come from, that the tab reads nothing of its own, and the staff-only file with its address and its refusal",
     !!t1 && t1.includes("<code>arYearRows</code>") && t1.includes("<code>arView</code>") && /no read of its own/i.test(t1) && t1.includes("<code>GET /api/routes/forecast-plan.csv</code>") && /401/.test(t1)
     && t1.includes("<code>forecast_plan.py</code>"));

  for (const f of fail) console.log("  FAIL: " + f);
  console.log(`${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
