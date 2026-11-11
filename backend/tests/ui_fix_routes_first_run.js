/*
 * ui_fix_routes_first_run.js — the 9 Nov 2026 UI critique, wave 3, branch claude/ui-fix-routes-first-run.
 *
 *   Finding 23 / card 23: the Routes table's code column is only as wide as the code, From → to takes the room (the status chips under
 *     it), the vehicles are a count with the chips in the row's details. Locations: a planner's selected row says what the place is
 *     and which routes use it. Zones lead with the name, never an ID; no screen prints a place's or a zone's code.
 *   Finding 17 / card 17: a deployment with no forecast line opens its Dashboard on its first steps (each a control that opens the
 *     page), draws no empty chart, and every empty message names a real control; the Routes / Locations / Zones empty rows say who
 *     adds the first one; no key for an empty map; the Gate arrivals panel points at Forecasts.
 *
 * Its own file (the wave rule, notes\ui-critique-1109.md §H): nothing appended to dom_frontend.js / parse_frontend.js / parse_map.js.
 * Source checks, plus DashFirstSteps and VehCount rendered for real (transpiled out of the page). Needs typescript, react and
 * react-dom through NODE_PATH; without them it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts, React, RDS;
try { ts = require("typescript"); React = require("react"); RDS = require("react-dom/server"); }
catch (e) { console.log("ui_fix_routes_first_run.js: SKIPPED — typescript / react / react-dom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];

// a top-level function's source, by its first line and the matching closing brace at column 0
const fnSrc = (name) => {
  const i = code.indexOf("function " + name + "(");
  if (i < 0) return "";
  const j = code.indexOf("\n}\n", i);
  return code.slice(i, j + 2);
};
const slice = (a, b) => { const i = code.indexOf(a); const j = code.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : code.slice(i, j); };
const compile = (names, prelude) => {
  const src = names.map(fnSrc).join("\n");
  const js = ts.transpileModule(prelude + "\n" + src + "\nreturn { " + names.join(", ") + " };", { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None } }).outputText;
  return new Function("React", "ACCESS", js.replace(/^"use strict";?/, ""));
};

// ---------------------------------------------------------------- the Routes table (finding 23)
const routesTable = slice('<th className="px-2 py-2 w-6"></th>', "{!status && <tr><td colSpan=\"11\"");
const rowStart = routesTable.indexOf("{(status || []).map(r => {");
const head = routesTable.slice(0, rowStart);
ok("⭐ 23: the Routes header keeps its columns: Route, From → to, team, Near the route, the four legs, Vehicles, Actions",
   /<th className=\{th\}>Route<\/th>\s*<th className=\{th\}>From → to<\/th>\s*<th className=\{th\}>\{TEAM\(\)\}<\/th>\s*<th className=\{th\}>Near the route<\/th>/.test(head)
   && head.includes('<th className={th}>Vehicles</th>') && head.includes('data-leg-col="out-dist"') && head.includes('data-leg-col="back-min"'));
const codeCell = routesTable.slice(routesTable.indexOf("data-route-open={r.id}") - 260, routesTable.indexOf("data-route-notes={r.id}"));
ok("⭐ 23: the code cell is only as wide as the code (width 1%, never wrapping, set inline: the Tailwind class is not defined here) and holds the code button alone",
   /<td className="px-3 py-2 font-medium text-slate-800" style=\{\{ width: "1%", whiteSpace: "nowrap" \}\}>/.test(codeCell)
   && !/gate blocked|Part return|Busy hours|Diverted|haul ×/.test(codeCell.slice(codeCell.indexOf("data-route-open"))));
const fromTo = routesTable.slice(routesTable.indexOf("data-route-notes={r.id}") - 330, routesTable.indexOf("data-route-near-cell={r.id}"));
ok("⭐ 23: From → to takes the room on one line, and the five status chips (gate blocked, holding area, busy hours, return, diverted, haul) sit UNDER it",
   /style=\{\{ minWidth: 220 \}\}/.test(fromTo) && fromTo.includes("{r.origin} → {r.dest}")
   && fromTo.indexOf("{r.origin} → {r.dest}") < fromTo.indexOf("data-route-notes={r.id}")
   && ["gate blocked", "data-route-holding", "data-route-busy", "data-route-return", "data-route-diverted", "haul ×"].every(k => fromTo.includes(k)));
ok("...the team and Near-the-route cells do not wrap (inline white-space), so the width goes to From → to",
   /<td className="px-3 py-2 text-slate-500" style=\{\{ whiteSpace: "nowrap" \}\}>\{teamText\(r\.ipt\)/.test(routesTable)
   && /style=\{\{ whiteSpace: "nowrap" \}\} data-route-near-cell=\{r\.id\}/.test(routesTable));
ok("⭐ 23: the Vehicles cell is a count (VehCount); each vehicle's chip moves to the row's details (data-route-vehicles) beside the analysis",
   routesTable.includes("<VehCount profiles={r.profiles} />") && !routesTable.includes("<td className=\"px-3 py-2\"><VehChips")
   && /\{open && <tr data-route-vehicles=\{r\.id\}><td colSpan=\{11\}[^>]*>[\s\S]{0,200}<VehChips profiles=\{r\.profiles\} \/>/.test(routesTable)
   && routesTable.indexOf("data-route-vehicles") < routesTable.indexOf("<NearDetails"));
if (!fnSrc("VehCount")) ok("...VehCount exists (the Vehicles cell's count)", false);
else {
  const mk = compile(["VehCount"], "const vehLabel = (k) => ({ tipper: 'Tipper (44t)', flat: 'Flatbed (44t)', mix: 'Mixer' }[k] || k);");
  const { VehCount } = mk(React, {});
  const r = (profiles) => RDS.renderToStaticMarkup(React.createElement(VehCount, { profiles }));
  const four = r({ a: { baked: true, return_baked: true }, b: { baked: true, return_baked: true }, c: { baked: true, return_baked: true }, d: { baked: true, return_baked: true } });
  ok("...VehCount: four routed vehicles read '4 vehicles', the list in the title, no chips", /4 vehicles/.test(four) && /title="[^"]*"/.test(four) && !/rounded-full/.test(four));
  ok("...VehCount: one vehicle is '1 vehicle'; none is 'not routed'; an outbound-only vehicle is named in words ('1 out only'), a failed one too",
     /1 vehicle</.test(r({ a: { baked: true, return_baked: true } })) && /not routed/.test(r({})) && /1 out only/.test(r({ a: { baked: true, return_baked: false }, b: { baked: true, return_baked: true } }))
     && /1 failed/.test(r({ a: { error: "x" } })));
}
ok("🔴 23: the Routes page has no empty claim of a button that does not exist ('author one with “Create route”' is gone)", !code.includes("author one with"));
ok("⭐ 17: an empty Routes table says who adds the first route: a reader 'An admin adds the first one', an admin with fewer than two places goes to Locations, otherwise Create route",
   code.includes('"No routes yet. An admin adds the first one."') && code.includes("Add two locations first.")
   && code.includes('data-routes-empty-go="locations" onClick={() => setSubTab("locations")}>Open Locations') && code.includes('"No routes yet. Pick an origin and a destination in Create route."')
   && /\{!canEdit \? "No routes yet\. An admin adds the first one\."\s*: locs\.length < 2/.test(code));

// ---------------------------------------------------------------- Locations and Zones: no id as the lead, nor anywhere
const locTable = slice('<th className={th}>Location</th>', "{!locs.length && <tr");
ok("⭐ 23: Locations print no place code beside the name (no `{l.id}` in the row's cells)", !/\{l\.id\}<\/span>/.test(locTable) && locTable.includes("{l.name}</button>"));
const zoneTable = slice("<th className={th}>Name</th><th className={th}>Kind</th>", "{!zoneList.length && <tr");
ok("⭐ 23: Zones open on the Name column: no ID header, no `{z.id}` cell, the first cell is the name button",
   !code.includes("<th className={th}>ID</th>") && !/<td className="px-3 py-2 font-mono text-xs text-slate-500">\{z\.id\}<\/td>/.test(zoneTable)
   && /<tr key=\{z\.id\} onClick=\{\(\) => editZone\(z\)\}[\s\S]{0,260}<td className="px-3 py-2 font-medium">\s*<button type="button" className="row-open" data-zone-open=\{z\.id\}/.test(zoneTable));
// NARROWED 11 Nov 2026 (CLOCS B-F4): the dates read through dayWords ("5 Oct 2026") and the cells carry data-zone-from / -to
ok("...Zones' dates and 'Used by' stay on one line, and 'route(s)' is a plural",
   (zoneTable.match(/style=\{\{ whiteSpace: "nowrap" \}\}(?: data-zone-(?:from|to)=\{z\.id\})?>\{(?:dayWords\()?z\.(starts|ends)_on/g) || []).length === 2 && !/route\(s\)/.test(zoneTable)
   && zoneTable.includes('route{haulUse[z.id] === 1 ? "" : "s"}'));
ok("⭐ 23: an editor's heading and the route pickers name the place or zone, never its code ('Editing Northfield Quarry'; no '(L001)' in an option)",
   code.includes('`Editing ${(locs.find(l => l.id === form.id) || {}).name || "location"}`') && code.includes('`Editing ${(zoneList.find(z => z.id === zoneForm.id) || {}).name || "zone"}`')
   && !/`Editing \$\{form\.id\}`|`Editing \$\{zoneForm\.id\}`/.test(code) && !code.includes("{l.name} ({l.id})"));
ok("17: the empty Locations and Zones rows say who adds the first one (a reader) or the real button (an admin)",
   code.includes('{canEdit ? "No locations yet. Add the first with “+ Add location”." : "No locations yet. An admin adds them."}')
   && code.includes('{canEdit ? "No zones yet. Draw a closure for routes to avoid, a works area, or a temporary haul road." : "No zones yet. An admin draws them."}')
   && code.includes('data-zones-empty="1"><td colSpan="8"'));
ok("17: nothing is drawn on a new deployment, so the key (Legend) is not either: it waits for a location, a route or a zone",
   /\{\(locs\.length > 0 \|\| \(status \|\| \[\]\)\.length > 0 \|\| zoneList\.length > 0\) && \(\s*<div className="card p-4">\s*<div className="text-sm font-semibold text-slate-700 mb-2">Legend<\/div>/.test(code));

// ---------------------------------------------------------------- the Locations card for a reader (mockup of 10 Nov)
const readCard = slice("{!form && readLoc && (", "{form && (");
ok("⭐ 23: a planner who selects a location gets what it is (type · role), what it supplies and receives, how routes reach it, and the routes that use it",
   readCard.includes("data-read-loc-facts={L.id}") && readCard.includes("ROLE_LABEL[L.role]") && readCard.includes("<CatChips list={L.supplies} />") && readCard.includes('<CatChips list={L.receives} dir="in" />')
   && readCard.includes("Routes go to its gate") && readCard.includes("Routes go to the marker itself") && readCard.includes("No route uses it yet."));
ok("...each route listed is a button that selects it and opens the Routes page; five at most, then '+ n more · Open Routes'; the card still ends with the Site layout",
   readCard.includes("onClick={() => { selectRoute(r.id); setSubTab(\"routes\"); }}") && readCard.includes("rs.slice(0, 5)") && readCard.includes("Open Routes")
   && readCard.indexOf("data-read-loc-facts") < readCard.indexOf("<SiteLayoutCard") && !/L\.id\}<\/|\{L\.id\}/.test(readCard.replace("data-read-loc-facts={L.id}", "")));

// ---------------------------------------------------------------- the Dashboard of a new deployment (finding 17)
ok("⭐ 17: a deployment with no forecast line at all (the unfiltered read is empty) opens on its first steps: firstRun, not a filter message",
   code.includes("const firstRun = !wall && !!data && rows.length === 0;")
   && code.includes("{firstRun && <DashFirstSteps locCount={locList ? locList.length : null} routeCount={(meta.routes || []).length} onOpen={onOpen} />}")
   && code.includes("{!firstRun && <>\n          <div className=\"dash-cards\" data-guide=\"dash-figures\">"));
ok("...on its first steps the header drops the date kicker, the filters, the coverage line and the 'plan lines in view' count",
   code.includes("kicker={firstRun ? undefined : `${rangeLabel} ·") && code.includes("actions={firstRun ? null : <div className=\"flex flex-wrap gap-2 items-center\">")
   && code.includes("{!firstRun && <div className=\"text-xs text-slate-500 mt-2 flex flex-wrap gap-x-3 gap-y-1\">") && code.includes("count={firstRun ? null :"));
if (!fnSrc("DashFirstSteps")) ok("17: DashFirstSteps exists (the Dashboard's first steps)", false);
else {
  const mk = compile(["DashFirstSteps"], "const TEAM = () => 'Team'; const isAdminLogin = (a) => !!(a && a.via === 'login' && a.role === 'admin');");
  const draw = (access, props) => { const { DashFirstSteps } = mk(React, { info: access }); const opened = []; const html = RDS.renderToStaticMarkup(React.createElement(DashFirstSteps, Object.assign({ onOpen: (p) => opened.push(p) }, props))); return html; };
  const reader = draw({ via: "code", role: "planner" }, { locCount: 0, routeCount: 0 });
  ok("⭐ 17: the steps: organisation set up (ticked), places, routes, ask each team to submit; 'The charts appear once a forecast is approved.'",
     /data-first-step="1" data-done="1"/.test(reader) && /Add the places lorries go between/.test(reader) && /Add the routes between them/.test(reader)
     && /Ask each team to submit its forecast/.test(reader) && /The charts appear once a forecast is approved\./.test(reader));
  ok("...a reader (not an admin login) is told who adds places and routes, and gets only Submit forecast as a control",
     (reader.match(/An admin adds these/g) || []).length === 2 && /data-first-step-go="submit"/.test(reader) && !/data-first-step-go="locations"/.test(reader) && !/data-first-step-go="routes"/.test(reader));
  const admin0 = draw({ via: "login", role: "admin" }, { locCount: 0, routeCount: 0 });
  ok("...an admin login gets a control for each step: Locations is the primary (the first to do), Routes and Submit forecast secondary; none says 'An admin adds'",
     /<button[^>]*data-first-step-go="locations"[^>]*class="btn-pri btn-sm"/.test(admin0) && /<button[^>]*data-first-step-go="routes"[^>]*class="btn-sec btn-sm"/.test(admin0)
     && /<button[^>]*data-first-step-go="submit"[^>]*class="btn-sec btn-sm"/.test(admin0) && !/An admin adds these/.test(admin0));
  const admin1 = draw({ via: "login", role: "admin" }, { locCount: 5, routeCount: 0 });
  ok("...a step is ticked and loses its control as it is done (five places: step 2 done, Routes becomes the primary)",
     /data-first-step="2" data-done="1"/.test(admin1) && !/data-first-step-go="locations"/.test(admin1) && /<button[^>]*data-first-step-go="routes"[^>]*class="btn-pri btn-sm"/.test(admin1));
  const loading = draw({ via: "login", role: "admin" }, { locCount: null, routeCount: 0 });
  ok("...while the places are still being read nothing is ticked on a guess", /data-first-step="2" data-done="0"/.test(loading));
  ok("🔴 17: no currency sign, no id and no back-end word on the first steps", !/[€£$]/.test(admin0) && !/\bL\d{3}\b|\bR\d{3}\b/.test(admin0) && !/(endpoint|server|API|token|geometry)/i.test(admin0));
}
ok("⭐ 17: with lines but a filter that shows none, the Dashboard draws NO empty chart and says one thing with a working control: 'Clear the filters'; with lines but none approved it opens Forecasts",
   code.includes("{!D.empty && <div className=\"dash-charts\" data-dash-charts=\"1\">") && code.includes("const pendingOnly = !firstRun && rows.length > 0 && !rows.some(r => r.status === \"Approved\");")
   && code.includes('title="No approved lines yet" body="The plan is drawn from approved forecast lines."') && code.includes('data-dash-empty-go="forecasts" onClick={() => onOpen && onOpen("forecasts")}>Open Forecasts')
   && code.includes('title="No forecast lines match these filters" body="Clear the filters to see the plan."') && code.includes('data-dash-empty-go="clear" onClick={() => { clearAll(); setFromM(1); setToM(months.count); }}>Clear the filters')
   && !code.includes("Widen the month range or clear a filter"));
ok("⭐ 17: the Gate arrivals panel names the way on: 'Pick another month, or approve a line.' with an Open Forecasts button (a planner), not 'Pick another month. Pending lines appear as a note…'",
   code.includes('"Pick another month, or approve a line."') && code.includes('data-ga-empty-go="forecasts" onClick={() => onOpen("forecasts")}>Open Forecasts')
   && code.includes("onOpen={canApprove ? onOpen : null} />") && !code.includes("Pending lines appear as a note until they are approved"));
ok("...the Dashboard's first steps are not placed among the carbon-target strip or the Gate arrivals blocks (their word checks read those slices)",
   code.indexOf("function DashFirstSteps(") > code.indexOf("function AppliedChips") - 5000 && code.indexOf("function DashFirstSteps(") > code.indexOf("function GateArrivalsPanel(")
   && !slice("function CarbonTargetStrip(", "function Dashboard(").includes("DashFirstSteps"));

// ---------------------------------------------------------------- the old claims are gone from the guide too
const guide = ["help/user-guide/index.html", "help/technical/index.html"].map(f => { try { return read("frontend", f); } catch (e) { return ""; } }).join("\n");
ok("...the guides do not tell a reader to 'author' a route with Create route or to widen a month range on an empty Dashboard", !/author one with/i.test(guide) && !/Widen the month range/i.test(guide));

console.log(`ui_fix_routes_first_run.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
