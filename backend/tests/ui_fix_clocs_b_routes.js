/*
 * ui_fix_clocs_b_routes.js — branch claude/clocs-b-routes-words, 11 Nov 2026: the CLOCS meeting's "Everything left" cards
 * for routes (notes\clocs-meeting-1113\left-to-do-mockup-1111\cards-live-b-routes.html), John's yes "as recommended".
 *
 *   B-F2  the Route sheet leaves an untyped part out; the Routes bar says which of the route's words are missing beside the
 *         Route sheet button ("No reason or diversions typed · Add"; "Add" for an admin opens the form at the field)
 *   B-F4  the Zones table's From and To in words ("5 Oct 2026"), as the diversion list beside it
 *   B-F5  the Route analysis menu ticks "The page for the assessor" again every time it opens; A-F stay remembered
 *   B-F6  the row's Route is in its "⋯" and asks first; the bar's network jobs are in one "Routing ▾" menu
 *   (B-F7, the file's header length and "Made", is server side: test_route_analysis.py; B-F2's sheet: test_route_sheet.py)
 *
 * Its own file: nothing appended to dom_frontend.js / parse_frontend.js (one pin there REVERSED: #29). Source checks, plus
 * SheetWordsNote and the date / tick helpers run for real (transpiled out of the page). Needs typescript, react and react-dom
 * through NODE_PATH; without them it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts, React, RDS;
try { ts = require("typescript"); React = require("react"); RDS = require("react-dom/server"); }
catch (e) { console.log("ui_fix_clocs_b_routes.js: SKIPPED — typescript / react / react-dom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];

const fnSrc = (name) => {
  const i = code.indexOf("function " + name + "(");
  if (i < 0) return "";
  const j = code.indexOf("\n}\n", i);
  return code.slice(i, j + 2);
};
const lineOf = (start) => { const i = code.indexOf(start); if (i < 0) return ""; return code.slice(i, code.indexOf("\n", i)); };
const slice = (a, b) => { const i = code.indexOf(a); const j = code.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : code.slice(i, j); };
const compile = (src, names) => {
  const js = ts.transpileModule(src + "\nreturn { " + names.join(", ") + " };", { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None } }).outputText;
  return new Function("React", js.replace(/^"use strict";?/, ""))(React);
};

// ---------------------------------------------------------------- B-F2: the missing words, beside the Route sheet button
{
  const m = compile(fnSrc("sheetWordsMissing") + "\n" + fnSrc("SheetWordsNote"), ["sheetWordsMissing", "SheetWordsNote"]);
  const r = (route, canEdit) => RDS.renderToStaticMarkup(React.createElement(m.SheetWordsNote, { route, canEdit, onAdd: () => {} }));
  const none = r({ id: "R001", route_reason: "", permitted_deviations: null }, true);
  ok("⭐ B-F2: a route with neither typed: 'No reason or diversions typed · Add' (Add for an admin, named for the route)",
     />No reason or diversions typed · <button/.test(none) && />Add<\/button>/.test(none)
     && none.includes('aria-label="Add the route sheet words for R001"') && none.includes('data-sheet-words-missing="R001"'), none);
  ok("...only the reason missing: 'No reason typed'; only the diversions: 'No diversions typed'",
     /No reason typed/.test(r({ id: "R2", route_reason: " ", permitted_deviations: "Signed diversion only." }, true))
     && /No diversions typed/.test(r({ id: "R3", route_reason: "Agreed in the CLP.", permitted_deviations: "" }, true)));
  ok("...both typed (R030 on the demo): nothing at all", r({ id: "R030", route_reason: "Hot load.", permitted_deviations: "The signed diversion." }, true) === "");
  ok("...a reader (not an admin) is told, with no Add", /No reason or diversions typed/.test(r({ id: "R1" }, false)) && !/<button/.test(r({ id: "R1" }, false)));
  ok("...no route picked: nothing", r(undefined, true) === "" && r({}, true) === "");
  ok("...amber words (the text-grade warn token), 12 px, on one line", fnSrc("SheetWordsNote").includes('className="text-xs"')
     && fnSrc("SheetWordsNote").includes('color: "var(--warn-text)", whiteSpace: "nowrap"'));
  ok("⭐ B-F2: the note sits in the Routes bar right after the Route sheet button, for the route picked in the list",
     code.includes('<RouteSheetButton routeId={selected} />\n            <SheetWordsNote route={(status || []).find(x => x.id === selected)} canEdit={canEdit} onAdd={addSheetWords} />'));
  const add = slice("const addSheetWords = (r) => {", "const cancelEditRoute = () => {");
  ok("...Add opens the route's form (startEditRoute) and focuses the first missing field: Why this route, else Permitted diversions",
     add.includes("startEditRoute(r);") && add.includes('String(r.route_reason || "").trim() ? "Permitted diversions" : "Why this route"')
     && add.includes('[data-route-sheet-text] textarea[aria-label="${k}"]') && add.includes("t.focus();")
     && fnSrc("RouteSheetText").includes('label: "Why this route"') && fnSrc("RouteSheetText").includes('label: "Permitted diversions"')
     && fnSrc("RouteSheetText").includes("aria-label={label}"));
}

// ---------------------------------------------------------------- B-F4: the Zones table's dates in words
{
  const src = lineOf("const MONTHS = [") + "\n" + lineOf("const _dvD = (iso) =>") + "\n" + lineOf("const dayWords = (iso) =>");
  const m = compile(src, ["dayWords"]);
  ok("⭐ B-F4: dayWords('2026-10-05') is '5 Oct 2026', '2027-12-17' is '17 Dec 2027', none is null",
     m.dayWords("2026-10-05") === "5 Oct 2026" && m.dayWords("2027-12-17") === "17 Dec 2027" && m.dayWords(null) === null && m.dayWords("") === null,
     [m.dayWords("2026-10-05"), m.dayWords("2027-12-17")].join(" / "));
  ok("⭐ B-F4: the Zones table's From and To cells go through dayWords (no ISO date printed), a dash when open-ended",
     code.includes('data-zone-from={z.id}>{dayWords(z.starts_on) || "—"}</td>') && code.includes('data-zone-to={z.id}>{dayWords(z.ends_on) || "—"}</td>')
     && !code.includes('{z.starts_on || "—"}</td>') && !code.includes('{z.ends_on || "—"}</td>'));
}

// ---------------------------------------------------------------- B-F5: the page for the assessor, ticked on opening
{
  const store = {};
  const prelude = 'const RA_SECTIONS = [["limits"], ["community"], ["collisions"], ["cycle"], ["hours"], ["diversions"], ["assessor"]];\n'
    + 'const RA_KEY = "k";\nconst localStorage = { getItem: (k) => STORE[k] === undefined ? null : STORE[k] };\n';
  const js = ts.transpileModule(prelude + lineOf("const raWithAssessor = (v) =>") + "\n" + fnSrc("raSaved") + "\nreturn { raWithAssessor, raSaved };",
    { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None } }).outputText;
  const m = new Function("STORE", js.replace(/^"use strict";?/, ""))(store);
  store.k = JSON.stringify(["collisions", "cycle", "hours", "diversions", "community", "limits"]);   // John's saved ticks, 11 Nov
  ok("⭐ B-F5: John's saved ticks (A-F, no assessor) open with the page for the assessor ticked, A-F as saved",
     JSON.stringify(m.raSaved()) === JSON.stringify(["collisions", "cycle", "hours", "diversions", "community", "limits", "assessor"]), JSON.stringify(m.raSaved()));
  store.k = JSON.stringify(["limits"]);
  ok("...a saved 'limits only' opens as limits + assessor; nothing saved = every section",
     JSON.stringify(m.raSaved()) === '["limits","assessor"]' && (delete store.k, m.raSaved().length === 7));
  ok("...raWithAssessor leaves a list that has it alone", JSON.stringify(m.raWithAssessor(["a", "assessor"])) === '["a","assessor"]');
  const menu = fnSrc("RouteAnalysisMenu");
  ok("⭐ B-F5: every opening of the menu ticks it again (onToggle), and an untick is still saved for A-F only by tickSec as before",
     menu.includes("onToggle={e => { const o = e.currentTarget.open; setOpen(o); if(o) setSecs(raWithAssessor); }}")
     && menu.includes("const [secs, setSecs] = useState(raSaved);") && menu.includes("localStorage.setItem(RA_KEY, JSON.stringify(n))"));
}

// ---------------------------------------------------------------- B-F6: the network jobs in one menu; the row's Route asks
{
  const bar = slice("<RouteSheetButton routeId={selected} />\n            <SheetWordsNote", "</RoutingMenu>}");
  ok("⭐ B-F6: Both legs, Route all, Busy-hour times and Clear all routes are inside one RoutingMenu, an admin's only",
     bar.includes("{canEdit && <RoutingMenu busy={routeBusy}>") && bar.includes("<select value={bakeLegs}") && bar.includes("onClick={bulkBake}")
     && bar.includes("onClick={hourBake}") && bar.includes("onClick={clearRoutes}")
     && bar.indexOf("<RoutingMenu") < bar.indexOf("onClick={bulkBake}"));
  ok("...each job still asks first (Route all, Busy-hour times, Clear all routes keep their own confirm)",
     /const bulkBake = async[\s\S]{0,4000}?confirm\(/.test(code) && /const hourBake = async[\s\S]{0,3000}?confirm\(/.test(code)
     && /const clearRoutes = async[\s\S]{0,2000}?confirm\(/.test(code));
  ok("...nothing outside the menu routes the network: one bulkBake / hourBake / clearRoutes button in the page",
     (code.match(/onClick=\{bulkBake\}/g) || []).length === 1 && (code.match(/onClick=\{clearRoutes\}/g) || []).length === 1
     && (code.match(/onClick=\{hourBake\}/g) || []).length === 1);
  const rm = fnSrc("RoutingMenu");
  ok("...the menu: a named secondary button 'Routing ▾' that says 'Routing…' while one runs; placed on screen as the row menus; a pick closes it",
     rm.includes('{busy ? "Routing…" : "Routing ▾"}') && rm.includes('className="btn-sec"') && rm.includes("useRowMenuPlace(ref);")
     && rm.includes('className="row-menu bulletin-menu"') && rm.includes("ref.current.open = false"));
  ok("...the legs choice has a label in the menu ('Legs to route')", bar.includes('<label><span>Legs to route</span><select value={bakeLegs}')
     && bar.includes('aria-label="Legs to route"'));
  const ask = slice("const routeAgainAsk = (r) => {", "const addSheetWords");
  ok("⭐ B-F6: the row's Route is in its '⋯' as 'Route again' (or 'Route' when not yet routed) and asks: 'Route R001 again? Its lines are replaced.'",
     code.includes("onClick={() => routeAgainAsk(r)}>{Object.keys(r.profiles || {}).length ? \"Route again\" : \"Route\"}</button>")
     && ask.includes("if(!confirm(had ? `Route ${r.id} again? Its lines are replaced.` : `Route ${r.id}?`)) return;")
     && ask.indexOf("confirm(") < ask.indexOf("rebakeRoute(r.id"));
  ok("...no visible Route button left in a row; while it routes the row says 'Routing…'",
     !code.includes('className="btn-sec btn-sm mr-1">') && code.includes('data-route-busy={r.id}>Routing…</span>'));
  ok("...'Keep the main route' on Zones is left as it is (it is undone in the same place)", code.includes("onKeep={keepMain}"));
}

console.log(`ui_fix_clocs_b_routes.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
