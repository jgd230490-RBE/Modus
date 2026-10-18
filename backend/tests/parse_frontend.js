/*
 * Frontend assertions for the Phase 2 changes.
 *
 * There is no build step -- index.html is React via CDN with in-browser Babel -- so this
 * pulls the <script type="text/babel"> block out of the file, parses it as TSX with the
 * global TypeScript compiler, and then asserts at SOURCE level.
 *
 * Source-level assertions are the point, not a shortcut. useEffect does not run under
 * renderToStaticMarkup, so the only way to prove that a fetch was rewired or a retired
 * control is really gone is to assert against the source. That has caught dangling UI
 * text more than once.
 *
 * NOT covered: anything requiring a browser. Mapbox, Chart.js rendering, actual fetch
 * behaviour, and whether the new pickers look right are unverified here.
 *
 * Run:  node backend/tests/parse_frontend.js
 */
const fs = require("fs");
const path = require("path");
// 29 Sep 2026: resolve the global packages through NODE_PATH or a node_modules on the
// path first (CI, Codespace, any sandbox); the old sandbox's fixed folder is the fallback.
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");

const ROOT = path.resolve(__dirname, "..", "..");
const FILE = path.join(ROOT, "frontend", "index.html");
// 13 Oct 2026 (W4): the technical guide, where the passages the screens no longer carry now live
const TECH = path.join(ROOT, "frontend", "help", "technical", "index.html");
const _tg = fs.existsSync(TECH) ? fs.readFileSync(TECH, "utf8").replace(/\r\n?/g, "\n") : "";
const html = fs.readFileSync(FILE, "utf8").replace(/\r\n?/g, "\n");   // 9 Oct 2026: a Windows checkout (core.autocrlf) hands us CRLF; the regexes expect LF

let pass = 0;
const fail = [];
function ok(label, cond, extra) {
  if (cond) pass++;
  else fail.push(label + (extra ? "  " + extra : ""));
}

// ---- extract the babel block -------------------------------------------------
const m = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/);
ok("the babel script block is present", !!m);
const src = m ? m[1] : "";

// ---- 1. it must still parse --------------------------------------------------
const sf = ts.createSourceFile("index.tsx", src, ts.ScriptTarget.Latest, true,
  ts.ScriptKind.TSX);
const diags = sf.parseDiagnostics || [];
ok("JSX parses with no syntax errors", diags.length === 0,
  diags.slice(0, 3).map(d => {
    const p = sf.getLineAndCharacterOfPosition(d.start);
    return `line ${p.line + 1}: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`;
  }).join(" | "));

// and it must survive a real transpile, which catches things parse alone does not
let emitted = "";
try {
  emitted = ts.transpileModule(src, {
    compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  ok("JSX transpiles to runnable JS", emitted.length > 1000);
} catch (e) {
  ok("JSX transpiles to runnable JS", false, e.message);
}
// 🔴 09 Sep night: the page shipped with TWO `function Kpi` declarations. TypeScript's
// transpile and `new Function()` (sloppy mode) both accept a redeclared function; the
// browser's Babel does not, and the app rendered a blank white page. Every top-level
// name must be declared exactly once.
const _decls = [...src.matchAll(/^(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)/gm)].map(m => m[1]);
const _dups = _decls.filter((n, i) => _decls.indexOf(n) !== i);
ok("🔴 no top-level name is declared twice (Babel refuses it; the harness alone did not)",
  _dups.length === 0, "duplicates: " + [...new Set(_dups)].join(", "));
// and, when @babel/standalone is on this machine, compile exactly as the browser does
const _babelPaths = ["/tmp/babelcheck/node_modules/@babel/standalone/babel.min.js",
                     "/tmp/shot/node_modules/@babel/standalone/babel.min.js"];
const _babel = _babelPaths.find(p => fs.existsSync(p));
if (_babel) {
  try {
    const Babel = require(_babel);
    const out = Babel.transform(src, { presets: ["react"], filename: "index.html" });
    ok("⭐ @babel/standalone compiles the page the way the browser does", out.code.length > 1000);
  } catch (e) {
    ok("⭐ @babel/standalone compiles the page the way the browser does", false, e.message.split("\n")[0]);
  }
} else {
  ok("(@babel/standalone not installed here — the browser-compile check did not run; `npm i @babel/standalone@7.24.7` in /tmp/babelcheck to enable it)", true);
}
try {
  new Function(emitted.replace(/^import .*$/gm, ""));
  ok("transpiled output is syntactically valid JS", true);
} catch (e) {
  ok("transpiled output is syntactically valid JS", false, e.message);
}

// ---- 2. the dashboard no longer computes its own cycle time ------------------
// 11 Sep: the Dashboard reads /api/costing/lines — the Look-ahead's functions — and
// derives NOTHING. The analysis-batch read and the client arithmetic are gone with it.
const _dbBody = src.slice(src.indexOf("function Dashboard("), src.indexOf("function DashboardToday("));
ok("🔴 the dashboard reads /costing/lines and no longer the analysis batch or the raw forecasts",
  _dbBody.includes("fetch(`${API}/costing/lines?status=All`)") && !_dbBody.includes("/routes/analysis-batch") && !_dbBody.includes("`${API}/forecasts`"));
ok("the flat-speed cycle formula is gone",
  !src.includes("round/P.avg_haul_speed_kmh") &&
  !src.includes("round / P.avg_haul_speed_kmh"));
ok("no local cycleH is computed from avg_haul_speed_kmh",
  !/cycleH\s*=\s*[^;]*avg_haul_speed_kmh/.test(src));
ok("cycle time is read from the server row (cycle_min), never computed here",
  _dbBody.includes("cycleH: (r.cycle_min != null ? r.cycle_min / 60 : null)") && !_dbBody.includes("avg_haul_speed") && !_dbBody.includes("load_minutes"));
ok("an unbaked route renders 'not baked' rather than a number",
  src.includes("not baked"));
ok("distance falls back to null, not 0",
  !src.includes("route.distance_km || 0"));
// 13 Oct 2026 (W3, narrowed): the same count in plain words ("forecast months have a route", "leave out … not routed yet");
// the routing detail is in the coverage info box and the technical guide (T2)
ok("the dashboard says how many forecast months the km / CO₂e / fair totals exclude, in the header",
  _dbBody.includes("forecast months have a route") && _dbBody.includes("leave out the {D.lines - D.baked} not routed yet") && _dbBody.includes("Not routed yet for this lorry")
  && _dbBody.includes('<InfoTip id="dash.coverage" />'));
ok("🔴 fleet size is the SERVER's `vehicles` (a monthly peak of it), never demand ÷ capacity here",
  _dbBody.includes("a.peakVeh = Math.max(a.peakVeh || 0, r.vehicles)") && !_dbBody.includes("peakPerDay / a.capacityPerDay")
  && !_dbBody.includes("/ payload(") && !_dbBody.includes("emisFactor(") && !_dbBody.includes("toTonnes("));
// 13 Oct 2026 (W3, narrowed): the method paragraph left the screen (inventory §1 rows 1-3): the read and the formulas are in the
// technical guide, each figure's method in its info box, and the footer links there
ok("the footnote's read and formulas live in the technical guide; the footer keeps one line and links to it",
  !_dbBody.includes("<code>/api/costing/lines</code>") && _dbBody.includes('TECH_URL("t1-figures")') && _tg.includes("<code>GET /api/costing/lines</code>")
  && _tg.includes("rounded up per line-month") && _dbBody.includes("Planning estimates and typed actuals — no live tracking."));

// ---- 3. per-line model -------------------------------------------------------
ok("dashboard rows are keyed per line, not per route",
  _dbBody.includes("`${r.route_id}|${r.discipline || \"\"}|${r.section_id || \"\"}`"));
// 13 Oct 2026 (W6, narrowed): the discipline is a chip on the route row and a "Sort by" choice, no longer its own column
ok("dashboard shows a discipline column", src.includes('["discipline", "Discipline"]') && src.includes("r.discipline || null]}"));
ok("matrix posts a discipline", /discipline\s*:/.test(src));
ok("matrix posts a section_id", /section_id\s*:/.test(src));

// ---- 4. the two-vehicle split UI is really gone ------------------------------
// Comments are stripped first. The file now EXPLAINS why the split was removed, and a
// raw substring check would match the explanation and report the code as still present.
const code = src
  .split("\n")
  .map(l => l.replace(/\/\/.*$/, ""))
  .join("\n")
  .replace(/\/\*[\s\S]*?\*\//g, "");

for (const gone of [
  ["vehicle_type_2", "vehicle_type_2 no longer read or sent"],
  ["split_pct", "split_pct no longer read or sent"],
  ["setUseTwo", "the 'split across a second vehicle' state is gone"],
  ["useTwo", "no useTwo branching survives"],
  ["setVehicle2", "the second-vehicle state is gone"],
  ["Split the load across a second vehicle", "its checkbox label is gone"],
  ["1 / (s / p1", "the blended-payload maths is gone"],
  ["Vehicle 2", "the Vehicle 2 picker is gone"],
  ["blended ${effPayload", "the 'blended t/load' readout is gone"],
]) {
  ok(gone[1], !code.includes(gone[0]));
}
ok("effective payload is now simply the vehicle's own payload",
  /const effPayload\s*=\s*payload\(factors,\s*vehicle\)/.test(code));

// the delete/withdraw paths must be line-scoped too, or one discipline's withdrawal
// takes another's forecast with it
ok("withdraw sends the line keys",
  code.includes("discipline: g.discipline") && code.includes("section_id: g.sectionId"));
// ⚠️ CHANGED 2026-09-01. This asserted `[r.route_id, year, disc, sect]` — per line AND
// year. The multi-year save lets one line span several years, and that key splits it
// into a 2026 row and a 2027 row that read as two separate forecasts. The year came OUT
// of the key; discipline and section stay in it, which is the half this assertion has
// always really been protecting.
ok("my-submissions groups per line, across every year the line covers",
  code.includes('[r.route_id, disc, sect].join("|")')
  && !/\[r\.route_id,\s*year,/.test(code));
ok("edit carries the line keys back into the matrix",
  code.includes("editTarget.discipline") && code.includes("editTarget.sectionId"));

// ---- 4b. Task A — the planning vehicles lead the picker --------------------------
// (the four EU-named ones until 11 Oct 2026; the tenant's own lead list since — UK trade names in the seed)
ok("the matrix reads planning_vehicles off /api/meta",
  code.includes("planning_vehicles"));
ok("...and defaults it to [] so an older meta payload still renders one flat list",
  /planning_vehicles\s*=\s*\[\]/.test(code));
ok("the picker groups planning vehicles above the rest",
  code.includes('<optgroup label="Planning vehicles">')
  && code.includes('<optgroup label="Other vehicles">'));
ok("the legacy group is the complement, not a second hard-coded list",
  /legacyVehicles\s*=\s*useMemo\(\s*\(\)\s*=>\s*vehicles\.filter/.test(code));
// one <option> renderer, shared: two copies of the disabled rule would drift
ok("both groups render through one shared option builder",
  /function vehOption\(/.test(code)
  && (code.match(/vehOption\(v, suggestedVehicles, vehicle\)/g) || []).length >= 3);
ok("a vehicle outside the material's list is still visible, just disabled",
  code.includes("not used for this material"));
ok("...and the currently-selected vehicle is never disabled",
  /disabled=\{!fits && v !== current\}/.test(code));

// ---- 4b2. 2026-09-02 — one vehicle, three labels -------------------------------
// NARROWED 11 Oct 2026 (EU vehicles removed): VEH_LANGS still NAMES the three label slots (a document saved
// before then carries labels.eu and keeps that option), but which are OFFERED is the server's list, VEH.langs.
ok("there is a label language toggle with exactly EN / EU / EE",
  /const VEH_LANGS = \[\["en", "English"\], \["eu", "European"\], \["ee", "Estonian"\]\]/.test(code));
// REVERSED 11 Oct 2026 (EU vehicles removed): the default is English (it was European), and the offered list
// starts as English alone until /api/meta answers.
ok("the default is English, offering English alone until /api/meta answers",
  /const VEH = \{ lang: "en", langs: \["en"\], labels: \{\}, fallbacks: \{\} \};/.test(code) && !/const VEH = \{ lang: "eu"/.test(code));
ok("11 Oct 2026: the offered languages come off /api/meta (vehicle_labels.langs), English if it sends none",
  code.includes('VEH.langs = (Array.isArray(vl.langs) && vl.langs.length) ? vl.langs : ["en"];'));
ok("labels come off /api/meta, not a second list in the client",
  code.includes("m.vehicle_labels") && code.includes("VEH.labels = vl.labels"));
// 12 Oct 2026 (map review D31): /api/meta answers two shapes — routes, teams and sections only to a code or a staff
// cookie. The mount fetch runs before a fresh sign-in, so the app fetches again once `role` is set, unless the mount
// fetch already carried a code (a resume).
// NARROWED 12 Oct 2026 (the review and fix pass): the "already staff" flag is set from the ANSWER's shape (m.scope),
// never from whether a code was stored — a stale stored code got the public shape, and the re-fetch after a fresh
// sign-in was then skipped (no routes, no teams in the portal). Only the latest fetch's answer is applied.
ok("D31: /api/meta is loaded through one function, on mount and again after a sign-in, unless the answer already was the staff shape",
  /const loadMeta = \(\) => \{\s*\n\s*const seq = \+\+metaSeq\.current;\s*\n\s*return fetch\(`\$\{API\}\/meta`\)\.then\(r => r\.json\(\)\)\.then\(m => \{\s*\n\s*if\(seq !== metaSeq\.current\) return;\s*\n\s*metaHadCode\.current = !!\(m && m\.scope === "staff"\);/.test(code)
  && !/metaHadCode\.current = !!ACCESS\.code/.test(code)
  && /\.catch\(\(\) => \{ if\(seq === metaSeq\.current\) setMetaErr\(true\); \}\);/.test(code)
  && /useEffect\(\(\) => \{ loadMeta\(\); \}, \[\]\);/.test(code)
  && /useEffect\(\(\) => \{ if\(role && !metaHadCode\.current\) loadMeta\(\); \}, \[role\]\);/.test(code)
  && (code.match(/fetch\(`\$\{API\}\/meta`\)/g) || []).length === 1);
// 12 Oct 2026 (the review and fix pass): Sign out asks the server to swap the 12-hour staff cookie for a map-only one
// (gate.downgrade_kwargs) — clearing the tab's code alone left the staff surface open to the next person at the machine
// NARROWED 14 Oct 2026 (G3): Sign out posts /api/auth/signout, which does what gate-signout?keep=map did (the staff
// cookie becomes a map cookie) AND ends a login's session on the server; gate-signout still answers (test_gate)
ok("Sign out POSTs /api/auth/signout and forgets the staff shape, so the next sign-in fetches /api/meta again",
  /const signOut = \(\) => \{[\s\S]{0,900}fetch\(`\$\{API\}\/auth\/signout`, \{ method: "POST" \}\)\.catch\(\(\) => \{\}\);\s*\n\s*metaHadCode\.current = false;/.test(code)
  && /const signOut = \(\) => \{[\s\S]{0,300}authHint\(false\);/.test(code));
// ⭐ THE INVARIANT. The <option value> is the canonical id; only the text changes.
ok("⭐ the picker's option VALUE is the canonical id, the text is the label",
  /<option key=\{v\} value=\{v\} disabled=[\s\S]{0,160}\{vehLabel\(v\)\}/.test(code));
// NARROWED 11 Oct 2026 (EU vehicles removed): English is the default, and an id IS a name in English (and in the
// European slot, as before), so only another language's fallback is starred — no star under English now.
ok("a fallback slot is marked, not passed off as a translation",
  /vehIsFallback\(v\) && !\["en", "eu"\]\.includes\(VEH\.lang\) \? " \*"/.test(code)
  && !/vehIsFallback\(v\) && VEH\.lang !== "eu" \? " \*"/.test(code));
// NARROWED 14 Oct 2026 (civils materials): the fallback is the id through the word rule ("Truck mixer …" reads
// "Concrete mixer …"; every other id unchanged), and a label equal to its id passes the rule too
ok("vehLabel falls back to the id itself, through the word rule",
  code.includes('const vehLabel = (v, lang) => { const l = (VEH.labels[v] || {})[lang || VEH.lang]; return (l && l !== v) ? l : vehWord(v || ""); };')
  && /const vehWord = \(v\) => String\(v == null \? "" : v\)\.replace\(\/\^\\s\*truck\\s\+mixer\\b\/i, "Concrete mixer"\);/.test(code));
ok("the save still posts the stored id", code.includes("vehicle_type: vehicle,"));
// 13 Oct 2026 (W6, narrowed): the Forecasts vehicle is in the row's details: the label, and the stored name beside it when they differ
// REVERSED 14 Oct 2026 (civils materials): the stored id never reaches a screen; "full name" is the full NAME, shown when
// the short form (the name without Artic/Rigid) differs from it
ok("tables show the label, and the full NAME (never the stored id) beside a short one",
  code.includes('<RdItem t="Vehicle">{vehLabel(g.vehicle)}</RdItem>') && code.includes('<RdItem t="Vehicle, full name">{g.vehicle && vehShort(g.vehicle) !== vehLabel(g.vehicle) ? vehLabel(g.vehicle) : null}</RdItem>')
  && !code.includes('g.vehicle !== vehLabel(g.vehicle) ? g.vehicle : null'));
// NARROWED (G2): the header still carries the control, but offers the local-language
// option only to a tenant whose country it is local to.
ok("the header carries the control", /VEH_LANGS\.filter\(\(\[k\]\) => vehLangShown\(k\)\)\.map\(\(\[k, l\]\) =>/.test(code));
// 11 Oct 2026: ...but only when there is a CHOICE — one offered language draws no buttons (the GB demo showed a
// lone "English" button until then)
ok("11 Oct 2026: the header draws the vehicle-name buttons only when more than one language is shown",
  /\{VEH_LANGS\.filter\(\(\[k\]\) => vehLangShown\(k\)\)\.length > 1 && \(\s*<span className="hidden md:inline-flex rounded-md overflow-hidden hdr-seg/.test(code));
// NARROWED (H1, 29 Sep): EN always; EE only for an Estonian tenant; EU for everyone EXCEPT a
// British tenant, whose EU-named vehicles are hidden, so the option would label nothing.
// NARROWED 11 Oct 2026 (EU vehicles removed): both country rules stand, AND a language is shown only when the
// server offers it (a vehicle the tenant is offered carries it). REVERSED in its second half: a stored or default
// language that is not shown falls back to ENGLISH (it fell back to "eu", which GB is not shown either).
ok("G2/H1: the Estonian label option is shown to an Estonian tenant only, the EU option not to a British one, each only when offered, and a stored language not shown falls back to English",
  /const vehLangShown = \(k\) => k === "en" \|\| \(\(VEH\.langs \|\| \[\]\)\.includes\(k\) && \(\s*\(k === "ee" && String\(TENANT\.country \|\| ""\)\.toUpperCase\(\) === "EE"\)\s*\|\| \(k === "eu" && String\(TENANT\.country \|\| ""\)\.toUpperCase\(\) !== "GB"\)\)\);/.test(code)
  && /if\(!vehLangShown\(VEH\.lang\)\)\{ VEH\.lang = "en"; setVehLangState\("en"\); \}/.test(code)
  && !/VEH\.lang = "eu"; setVehLangState\("eu"\)/.test(code));
// 11 Oct 2026: the fallback runs whether or not /api/meta sent a tenant block (it sat inside `if(tn)` until then)
ok("11 Oct 2026: the English fallback sits after the tenant block, not inside it",
  /catch\(e\)\{\} \}\n\s*\/\/ 11 Oct 2026: a stored or default label language[^\n]*\n[^\n]*\n\s*if\(!vehLangShown\(VEH\.lang\)\)\{ VEH\.lang = "en"/.test(src));
// 11 Oct 2026 (EU vehicles removed): the Config page's Planning tick keeps the list's ORDER (its first name is
// the payload fallback) and appends a newly ticked vehicle; it rebuilt the list in file order until then
ok("11 Oct 2026: Config → Vehicles' Planning tick keeps the planning list's order and appends a new tick",
  code.includes("const kept = (d.planning_vehicles || []).filter(x => d.vehicles[x] && d.vehicles[x].planning_vehicle); d.planning_vehicles = [...kept, ...Object.keys(d.vehicles).filter(x => !x.startsWith(\"_\") && d.vehicles[x].planning_vehicle && !kept.includes(x))];")
  && !code.includes("d.planning_vehicles = Object.keys(d.vehicles).filter("));
// NARROWED 11 Oct 2026 (review): the label said "(shown only when offered)"; the column now follows the country alone
// NARROWED 14 Oct 2026 (civils materials): the placeholder is the id through the word rule (vehWord), never "Truck mixer"
ok("11 Oct 2026: Config → Vehicles' Estonian column (an Estonian tenant's) shows the id (word rule applied) as its placeholder, not 'falls back to EU'",
  !src.includes('placeholder="falls back to EU"') && code.includes('value={lab.ee || ""} placeholder={vehWord(k)}'));
// 11 Oct 2026 (review): gated on what the server OFFERS, the column needed an Estonian name to exist before one could
// be typed — on the new seed (English names only) an Estonian organisation never saw it. The column follows the
// country rule alone; the header's buttons still need a choice (vehLangShown, above).
ok("11 Oct 2026 (review): ⭐ the Config Estonian column is gated on the COUNTRY alone (vehLangEditable), not on the offered languages",
  code.includes('const vehLangEditable = (k) => k === "en" || (k === "ee" && String(TENANT.country || "").toUpperCase() === "EE");')
  && !/const vehLangEditable = [^\n]*VEH\.langs/.test(code)
  && code.includes('.filter(h => h !== "Estonian" || vehLangEditable("ee"))') && code.includes('{vehLangEditable("ee") && <td className="min-w-[190px]"><input className={inp} value={lab.ee || ""}')
  && !code.includes('vehLangShown("ee")'));
// 11 Oct 2026: ⭐ the four EU type-approval vehicles are gone from the app's source — no name, no code, no 'aliases'
// note (only those entries carried aliases), and no comment that describes them as present
ok("11 Oct 2026: ⭐ the staff app names none of the four EU type-approval vehicles or their codes",
  !["N3 lorry", "N3 tractor", "TPMLM", "O4 semi", "O4 tipping", "V07", "V10", "V11", "V12", "EU-named", "EU N-category", "four EU"].some(t => src.includes(t))
  && !src.includes("Routing dimensions and aliases"), ["N3 lorry", "V07", "V12", "EU-named", "EU N-category", "four EU"].filter(t => src.includes(t)).join(", "));
ok("H1: the pickers hide the tenant's hidden vehicles (its country's set) but keep a current value visible",
  /const HIDDEN_VEHICLES = \[\];/.test(code) && /const vehShown = \(v, keep\) => !HIDDEN_VEHICLES\.includes\(v\) \|\| v === keep;/.test(code)
  && /HIDDEN_VEHICLES\.length = 0; \(m && m\.hidden_vehicles \|\| \[\]\)\.forEach\(v => HIDDEN_VEHICLES\.push\(v\)\);/.test(code)
  && (code.match(/\.filter\(v => vehShown\(v/g) || []).length >= 5);
ok("H1: the basemap list is by country — the Estonian orthophoto for EE only, 'Aerial' wording for GB",
  /function basemapsFor\(country\)/.test(code) && /val !== "maaamet-ortho" \|\| c === "EE"/.test(code)
  && /"Aerial \(Mapbox Satellite\)"/.test(code) && /basemapsFor\(TENANT\.country\)\.map/.test(code)
  && !/\{BASEMAPS\.map\(/.test(code));
ok("G2/29 Sep: the page title is the tenant's name · Wayscope, and plain 'Wayscope' for the default tenant",
  /document\.title = \(TENANT\.name && TENANT\.name !== "Wayscope"\) \? TENANT\.name \+ " · Wayscope" : "Wayscope"/.test(code));
// ---- 29 Sep 2026: the rebrand. The header is the lockup + a rule + the tenant's name;
// the gold bar and the "Modus · Forecasting & Route Map" caption are GONE (asserted at
// source level, the "references are gone" rule), and the default tenant is Wayscope.
ok("REBRAND: the header renders the Wayscope lockup image with alt text",
  /<img src="\/brand\/logo-header-on-dark\.svg" alt="Wayscope" className="brand-lockup" draggable="false" \/>/.test(code));
ok("REBRAND: the tenant's name sits after a rule, only when it is not the default, hidden below sm",
  /TENANT\.name && TENANT\.name !== "Wayscope" && \(/.test(code)
  && /className="brand-rule hidden sm:block"/.test(code)
  // NARROWED 5 Oct 2026: the name's colour is the header token (.hdr-muted), not text-white/70
  // NARROWED 9 Oct 2026: on a demo tenant the slot shows the placeholder, not the scheme's name
  && /className="hidden sm:block text-\[14px\] font-medium hdr-muted truncate max-w-\[36vw\]">\{TENANT\.demo_notice \? HEADER_DEMO_NAME : TENANT\.name\}/.test(code));
ok("9 Oct: a DEMO tenant's header shows where a client's name goes, in plain words, and ONLY the header changes",
  /const HEADER_DEMO_NAME = "Your organisation's name appears here";/.test(code)
  && (code.match(/HEADER_DEMO_NAME/g) || []).length === 2          // the constant and its one use
  && /document\.title = \(TENANT\.name && TENANT\.name !== "Wayscope"\) \? TENANT\.name \+ " · Wayscope" : "Wayscope"/.test(code));
ok("REBRAND: the old header is gone — no gold bar, no caption, no bold tenant-name block",
  !/Forecasting &amp; Route Map/.test(html) && !/style=\{\{background:"var\(--gold\)"\}\}/.test(code)
  && !/font-extrabold tracking-tight leading-none text-\[17px\]/.test(code));
ok("REBRAND: the default tenant is Wayscope in both the module constant and the meta fallback",
  /const TENANT = \{ name: "Wayscope",/.test(code) && /name: tn\.name \|\| "Wayscope",/.test(code));
ok("REBRAND: the word Modus appears nowhere in the staff app", !/\bModus\b/.test(html));
ok("REBRAND: the ink token is #1F2024, the brand orange tokens exist, amber stays the warning colour",
  /--navy-deep:#1F2024;/.test(html) && /--brand-orange:#FF8C14;/.test(html) && /--gold:#D97706;/.test(html)
  && !/#0F172A/i.test(html));
// 5 Oct 2026, from the live site: a hook placed after a component's early `return`
// (useTheme() in Dashboard, after "if(!data || !D) return …") raised React #310 ("rendered
// more hooks than during the previous render") once the data arrived, and the WHOLE app
// unmounted to a blank page. Neither SSR nor jsdom-with-no-data renders twice, so no
// harness saw it. This reads the rule statically, for every top-level component:
// no hook call at the component's top level after its first top-level early return.
(function hooksBeforeReturns() {
  const lines = code.split("\n");
  const bad = [];
  let fn = null, sawReturn = false;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const m = l.match(/^function ([A-Z]\w*)\(/);
    if (m) { fn = m[1]; sawReturn = false; continue; }
    if (!fn) continue;
    if (/^}/.test(l)) { fn = null; continue; }
    if (/^  if\s*\(.*\breturn\b/.test(l) || /^  if\s*\(.*\)\s*{\s*$/.test(l) && /^\s+return\b/.test(lines[i + 1] || "")) sawReturn = true;
    if (sawReturn && /^  (?:const|let|var)?\s*(?:\[[^\]]*\]|\w+)?\s*=?\s*use[A-Z]\w*\(/.test(l)) bad.push(`${fn} line ${i + 1}: ${l.trim().slice(0, 70)}`);
  }
  ok("🔴 no component calls a hook after its first top-level early return (React #310 — the 5 Oct blank page)", bad.length === 0, bad.join(" · "));
})();
// NARROWED 5 Oct 2026 (Appearance): the bar's background is a header token now, and the
// picker's tick is the second brand-orange use. Orange as a CONTROL colour exists only
// inside html[data-theme="dark"] — the user's decision for the dark look.
ok("REBRAND: the header bar carries the 2 px orange rule; brand orange is used twice at most (the rule, the picker's tick)",
  /\.brand-bar\{background:var\(--hdr-bg\);color:var\(--hdr-fg\);border-bottom:2px solid var\(--brand-orange\);\}/.test(html)
  && (html.match(/var\(--brand-orange\)/g) || []).length <= 2);
ok("REBRAND: the head carries the favicon links, the manifest and the ink theme-color",
  /<link rel="icon" href="\/favicon\.ico" sizes="32x32">/.test(html) && /<link rel="icon" href="\/favicon\.svg" type="image\/svg\+xml">/.test(html)
  && /<link rel="apple-touch-icon" href="\/apple-touch-icon\.png">/.test(html) && /<link rel="manifest" href="\/site\.webmanifest">/.test(html)
  && /<meta name="theme-color" content="#1F2024">/.test(html));

// ---- 4c. Task B — the multi-year matrix ---------------------------------------
// The single-year state has to be GONE, not shadowed. A surviving setYear would be a
// second source of truth for the same window.
for (const gone of [
  ["setYear(", "the single-year setter is gone"],
  ["const [year,", "the single-year state is gone"],
  ["clearYear", "'Clear year' no longer refers to a single year's state"],
]) {
  ok(gone[1], !code.includes(gone[0]));
}
ok("the matrix carries a From year and a To year",
  /const \[fromYear, setFromYear\]/.test(code) && /const \[toYear, setToYear\]/.test(code));
ok("both come from months.years", code.includes("yearsAvail.map(y =>"));
ok("⭐ the To list only offers years at or after From",
  code.includes("yearsAvail.filter(y => y >= fromYear)"));
ok("...and to >= from is enforced in state as well as in the dropdown",
  /setToYear\(t => \(t < fromYear \? fromYear : t\)\)/.test(code));
ok("the default range is the CURRENT calendar year",
  code.includes("new Date().getFullYear()"));
ok("...falling back to the first year the backend offers",
  /yearsAvail\.includes\(now\) \? now : \(yearsAvail\[0\]/.test(code));
ok("one labelled twelve-cell row is rendered per year in the range",
  code.includes("yearsInRange.map(y =>") && code.includes("MONTHS.map((mn, i) =>"));
// ⭐ absolute month_index keys. A relative 1..12 key collides across years — Jan 2026
// and Jan 2027 would both be "1" and overwrite each other in `vals`.
ok("⭐ cells are keyed by absolute month_index, not 1..12",
  code.includes("const mi = base + i + 1") && code.includes("vals[mi]")
  && !/vals\[i \+ 1\]/.test(code));
ok("the edit window is a month_index range computed from the two years",
  /const mLo = \(fromYear - months\.start_year\) \* 12 \+ 1/.test(code)
  && /const mHi = \(Math\.max\(fromYear, toYear\) - months\.start_year\) \* 12 \+ 12/.test(code));
ok("the load filters on that window", code.includes("x.month_index >= mLo && x.month_index <= mHi"));
ok("...and re-runs when either year moves",
  code.includes("[routeId, fromYear, toYear, discipline, sectionId]"));
ok("⭐ ONE bulk POST covers the whole range",
  /for\(let mi = mLo; mi <= mHi; mi\+\+\) cells\.push/.test(code)
  && (code.match(/\/forecasts\/bulk/g) || []).length === 1);
ok("totals, per-day and the seasonal check all read the same in-range list",
  (code.match(/inRange/g) || []).length >= 4);
// seasonal_restrictions.months are CALENDAR months; month_index is absolute
ok("⭐ the seasonal check folds an absolute index back to a calendar month",
  code.includes("((mi - 1) % 12) + 1"));
ok("clearing is scoped to the range, not the whole of vals",
  /for\(let mi = mLo; mi <= mHi; mi\+\+\) delete next\[mi\]/.test(code));
ok("the save message names the range", code.includes("Saved ${rangeLabel} forecast"));
// my submissions
ok("⭐ my submissions shows a year SPAN when a line covers more than one",
  code.includes("fromYear === toYear ? String(fromYear) : `${fromYear}–${toYear}`"));
ok("withdraw is scoped to the months the row actually shows, not 1..60",
  code.includes("from: String(g.minMonth), to: String(g.maxMonth)"));
ok("...and the confirmation says how many months go",
  code.includes("will be removed"));
ok("edit reopens the line on its full span",
  code.includes("year: g.fromYear, toYear: g.toYear"));
ok("...and the matrix accepts that span", code.includes("setToYear(editTarget.toYear || editTarget.year)"));

// ---- 4c2. 2026-09-02 §3 — the six per-day cards ---------------------------------
// ⭐ 2026-09-03, the human's correction: MOVEMENTS and VEHICLES are different numbers.
// A movement is one load carried one way; how many a single vehicle can make per day is
// a property of the ROUTE (the baked HERE cycle), so vehicles needed = movements/day ÷
// that figure, rounded UP. The earlier "trips == vehicles" cards are gone.
for (const card of ["Avg movements / day", "Peak movements / day", "Vehicles needed (avg)", "Vehicles needed (peak)"]) {
  ok(`the range strip carries '${card}'`, code.includes(`"${card}"`));
}
ok("⭐ no card claims trips equal vehicles any more",
  !code.includes("Avg vehicles / day") && !code.includes("Trips equal vehicle loads"));
ok("⭐ trips-per-vehicle-per-day comes from the route's baked cycle, the same source the dashboard uses",
  code.includes("/analysis?profile=") && /setTpv\(row && row\.trips_per_day > 0 \? row\.trips_per_day : null\)/.test(code));
ok("⭐ vehicles needed = movements ÷ trips-per-vehicle, rounded UP",
  /Math\.ceil\(movesPerDay \/ tripsPerVehicleDay\)/.test(code));
// 13 Oct 2026 (W3, narrowed): "not baked" reads "not routed"
ok("⭐ an unbaked route reads 'not routed', never a fleet size",
  code.includes('"not routed" : String(fleetOf(') && code.includes("not routed yet for") && !code.includes('"not baked" : String(fleetOf('));
ok("the dashboard's fleet column is the server's model (costlines.vehicles), read not recomputed", _dbBody.includes("r.vehicles") && !code.includes("Math.ceil(peakPerDay / a.capacityPerDay)"));
ok("...and avg / peak material in the CHOSEN unit",
  code.includes('`Avg ${unit === "m3" ? "m³"') && code.includes('`Peak ${unit === "m3" ? "m³"'));
ok("working days come from factors.planning, defaulting to 22",
  /working_days_per_month\) \|\| 22/.test(code));
ok("averages are over months WITH a figure, not the whole range",
  code.includes("inRange.filter(([, q]) => +q > 0)") && code.includes("/ months.length) / wd"));
ok("peak is the busiest single month per working day",
  code.includes("Math.max(...monthlyT) / wd") && code.includes("Math.max(...monthlyQ) / wd"));
ok("vehicle loads convert through the payload", code.includes("avgT / p, peakVeh = peakT / p"));
ok("trips are stated to equal vehicle loads on one line", code.includes("avgTrips: avgVeh, peakTrips: peakVeh"));
ok("the cards sit in the navy strip with tabular numerals, no new fonts",
  code.includes('style={{ background: "var(--navy)" }}') && code.includes("tabular-nums")
  && !/fontFamily/.test(code.slice(code.indexOf("Avg vehicles / day") - 2000, code.indexOf("Avg vehicles / day") + 2000)));

// ---- 4d. Tasks C + D — the Look-ahead page ------------------------------------
// 2.5b: a rail entry now, not a tab. The nav entry and the render are checked
// separately because a page that is listed but not rendered is a blank screen.
ok("there is a Look-ahead nav entry",
  /\{ id: "lookahead", label: "Look-ahead"/.test(code));
ok("...in the Track group, on its own",
  /group: "Track", items: \[\s*\{ id: "lookahead"/.test(code));
// NARROWED 14 Oct 2026 (D9, the mobile shell): on a desktop; below 768 px the page is PhoneLookAhead
ok("...and it renders the LookAhead component",
  /page === "lookahead" && !narrow && <LookAhead/.test(code) && /page === "lookahead" && narrow && <PhoneLookAhead meta=\{meta\} \/>/.test(code));
// ⚠️ Visible to submitters too. /api/forecast-weeks is filtered per IPT on the server
// since Task F, so the boundary is there, not in the nav. Asserted so nobody "fixes"
// this into a second, inconsistent permission.
ok("⭐ the Track group is NOT admin-gated",
  !/group: "Track", admin/.test(code));
// Look-ahead v2 (09 Sep evening): the page reads ONE endpoint and the server decides
// every window. Reversed from "current month + next" — the browser no longer does
// month arithmetic for the look-ahead at all.
const _laBody = (() => {
  const i = code.indexOf("function LookAhead(");
  const j = code.indexOf("function RoutePlanning(", i);
  return i >= 0 && j > i ? code.slice(i, j) : "";
})();
ok("LookAhead is findable in the source", _laBody.length > 1000);
ok("⭐ the window comes from the server's horizon block, not the browser clock",
  _laBody.includes("horizon.from_month") && !/new Date\(\)\.getMonth/.test(_laBody)
  && !/months\.count, from \+ 1/.test(_laBody));
// ⭐ which week is the commit week comes from the SERVER; the browser only picks the bucket
ok("⭐ the commit week comes from the server's commit_week, through /lookahead?bucket=",
  _laBody.includes("fetch(`${API}/lookahead?bucket=${bucket}`)") && _laBody.includes("page.commit_week")
  && !_laBody.includes("payload.next_week"));
ok("...and the bucket switch offers exactly this week and next week — the Thursday process",
  /\[\["commit", "this week"\], \["next", "next week"\]\]/.test(_laBody));
// 10 Oct 2026 NARROWED: the day cell reads as a figure and is an input only once clicked (mockup 3) —
// still editable exactly while the week is not confirmed, in this bucket or next
// 13 Oct 2026 (W6, narrowed): the input sits behind the unit switch (typing is in Tonnes only: decision 2)
ok("a planned day is editable while its week is not confirmed, this bucket or next",
  /const locked = w\.status === "confirmed"/.test(_laBody) && /: !locked && editing === k \? \(/.test(_laBody) && /\) : !locked \? \(/.test(_laBody)
  && _laBody.includes('onClick={() => setEditing(k)}'));
// 13 Oct 2026 (W6, narrowed): the old cell title is the week's words in the row's details
ok("a confirmed week's plan is read-only", code.includes('"Confirmed: reopen it to change the plan"'));
ok("⭐ Confirm week is ONE button for the whole week, separate from editing (L6)",
  _laBody.includes(">Confirm week<") && _laBody.includes("/forecast-weeks/confirm")
  && /const doConfirm = async \(\) => \{[\s\S]*?for\(const l of lines\)/.test(_laBody));
// scoped to doConfirm's own body: a `break` after the first line would confirm ONE line
// and still contain the loop, so the loop alone proved nothing (regression F2 was green)
const _doConfirmBody = (() => { const i = _laBody.indexOf("const doConfirm ="); const j = _laBody.indexOf("const doReopen =", i); return i >= 0 && j > i ? _laBody.slice(i, j) : ""; })();
ok("⭐ ...and doConfirm walks EVERY unconfirmed line — the only break is the failed-request one",
  _doConfirmBody.length > 0 && (_doConfirmBody.match(/break;/g) || []).length === 1 && _doConfirmBody.includes("if(!j) break;"));
ok("...and a confirmed week can be re-opened, through its own endpoint, deleting nothing",
  _laBody.includes("/forecast-weeks/reopen") && _laBody.includes("Nothing is deleted"));
ok("confirm offers exactly the four flag fields, all optional",
  /\["weather", "wetness", "traffic", "other"\]/.test(code)
  && code.includes("optional and may be left blank"));
// ⭐ THE ONE THAT MATTERS. Saving an actual must not calibrate.
ok("⭐ the actual is saved through /forecast-weeks/actual",
  code.includes("/forecast-weeks/actual"));
// Scoped to saveActual's OWN body, sliced out between its declaration and the next
// one. A window-sized regex matched doCalibrate() further down the file and passed on
// a clean tree AND on a deliberately broken one — vacuously true in both directions.
const _saveActualBody = (() => {
  const i = code.indexOf("const saveActual =");
  if (i < 0) return null;
  const j = code.indexOf("const doConfirm =", i);
  return j > i ? code.slice(i, j) : code.slice(i);
})();
ok("saveActual is findable in the source", !!_saveActualBody);
ok("⭐ and saveActual's own body never touches the calibrate endpoint",
  !!_saveActualBody && !_saveActualBody.includes("forecast-weeks/calibrate"));
// C18, decided: the per-line "spread on this week" button (the Account mock), not a
// dialog checkbox. Still the ONLY thing that reaches calibrate.
ok("⭐ calibrate is reached only from the per-line 'spread on this week' button",
  (code.match(/\/forecast-weeks\/calibrate/g) || []).length === 1
  && code.includes("spread on this week") && /const doSpread = \(row\) => send\("\/forecast-weeks\/calibrate", \{ \.\.\.wkBody\(row\), spread: true/.test(_laBody));
ok("...and the button says the server refuses it when that week is confirmed",
  _laBody.includes("Refused if that week is confirmed"));
// reversed: the calibrate DIALOG is gone with C18 — there is no typed override in the UI
// (the endpoint keeps it; nothing in the page sends override_qty)
ok("the calibrate dialog and its typed override are gone from the page (C18: per-line button)",
  !_laBody.includes("override_qty") && !_laBody.includes("leave blank to use the formula")
  && !_laBody.includes("setCalibrating"));
ok("the four action states of the Account mock are all rendered: held · spread · applied · waiting",
  ['r.action === "held"', 'r.action === "spread"', 'r.action === "applied"', 'r.action === "waiting"'].every(t => _laBody.includes(t)));
ok("variance is blank rather than 0 until an actual is typed",
  /r\.variance == null \? "—"/.test(code));
ok("an emptied actual box clears it back to null, not to zero",
  /actual_qty: \(v === "" \|\| v == null \? null/.test(code));
// 13 Oct 2026 (W6, narrowed): the words moved from StatusChip to the row's status (MONTH CHANGED) and its details line
ok("a week whose parent month changed says so",
  code.includes('<RdItem t="Parent month changed" wide bad>{w.parent_changed ?') && code.includes('return { word: "MONTH CHANGED", tone: "bad", more: 0 };') && code.includes("parent_changed"));
ok("reopening a month is shown as a note, not by hiding its weeks",
  code.includes("month is now"));

// ---- 4d2. Look-ahead v2 slices 3-6 — the page (09 Sep evening) ------------------
ok("three pills, in the mock's order, and the page lands on Commit",
  /pill\("account", "Account"\)/.test(_laBody) && /pill\("commit", /.test(_laBody) && /pill\("horizon", "Horizon"\)/.test(_laBody)
  && /localStorage\.getItem\("modus_la_view"\) \|\| "commit"/.test(_laBody));
ok("the pills sit under PageHeader — the left rail stays (C18's unsettled point, decided)",
  /<PageHeader title="Look-ahead"/.test(_laBody) && !_laBody.includes("Dashboard · Submit Forecast"));
// NARROWED (H1, 29 Sep): the t·km card reads TKM() — "t·km", or "t·mi" for a tenant that
// reads miles (HU5: per tenant). The card and its position are unchanged.
ok("the Commit KPI strip carries the mock's cards: planned, trips, vehicles peak, t·km (TKM()), last-week shortage, last-week delivered — and planned €",
  ["planned this week", "trips", "vehicles / day peak", "caption={`${TKM()} · route basis`}", "last week shortage", "last week delivered", "planned ${CUR()}"]
    .every(t => _laBody.includes(t)));
ok("H1 (HU5): distances are shown in the tenant's unit — helpers convert at the display boundary only, km stays stored",
  /const DU = \(\) => \(TENANT\.distance_unit === "mi" \? "mi" : "km"\);/.test(code)
  && /const dist = \(km\) =>/.test(code) && /const distRate = \(perKm\) =>/.test(code) && /const distInRate = \(perUnit\) =>/.test(code)
  && /const KM_PER_MI = 1\.609344;/.test(code) && (code.match(/\bdist\(/g) || []).length >= 12
  && (code.match(/\bDU\(\)/g) || []).length >= 25);
ok("H1 (HU5): a per-distance RATE is typed and shown in the tenant's unit and stored per km (route form + target rate)",
  _laBody.length > 0 && code.includes('body[k] = (v[k] === "" || v[k] == null) ? null : (k === "rate_eur_per_km" ? +(+distInRate(+v[k])).toFixed(6) : +v[k]);')
  && code.includes('else body[k] = (k === "rate_eur_per_km" ? +(+distInRate(n)).toFixed(6) : n);')
  && code.includes('rate_eur_per_km: route.rate_eur_per_km == null ? "" : +(+distRate(route.rate_eur_per_km)).toFixed(4),'));
ok("🔴 the word PPC is printed nowhere (L5)", !/\bPPC\b/.test(code));
ok("⭐ the clash rail is ONE row with '+N more', not a stack",
  _laBody.includes("rail.flags.slice(0, 3)") && _laBody.includes("more`") && !_laBody.includes("dismiss"));
// 🔴 09 Sep night: the LIVE Tark Tee check froze the page on the critical path, and off
// it still took 30 s+. 10 Sep: the page reads the STORED per-route check (the rail carries
// it), and the live check runs on demand in the background — a "check now / re-check"
// button that polls until it finishes. A route never checked is named, never shown clean.
// NARROWED (H1, 29 Sep): the paths are /forecast-weeks/restrictions[/refresh] and the
// words come from the page (`restrictions_ui_label`), so the same line reads "Road
// restrictions (Tark Tee)" for EE and "Road closures (National Highways)" for GB.
ok("🔴 the page never fetches the live provider — the refresh is a POST the person triggers, then a poll",
  !/lookahead\?bucket=\$\{bucket\}&(tark_tee|restrictions_on)=0/.test(_laBody)
  && _laBody.includes('fetch(`${API}/forecast-weeks/restrictions/refresh`, { method: "POST" })')
  && /fetch\(`\$\{API\}\/forecast-weeks\/restrictions\?bucket=\$\{bucket\}`\)/.test(_laBody)
  && _laBody.includes("setTimeout(tickPoll, 4000)") && !_laBody.includes("forecast-weeks/tark-tee"));
ok("...the status line says checked-when, partial-with-names, or NOT checked — never a silent clean — in the provider's words",
  _laBody.includes("${ttName}: checked") && _laBody.includes("not checked since the route was worked out")   // 13 Oct 2026 (W3, narrowed): was "since baking" 
  && _laBody.includes("NOT checked for these routes") && _laBody.includes("check now")
  && _laBody.includes('const ttName = ttSrc.restrictions_ui_label || "Road restrictions";')
  && !_laBody.includes("Tark Tee)") && _laBody.includes("could not reach {ttShort}"));
ok("H1: the status line names the week the flags are filtered to, and shows only when the tenant has a provider",
  _laBody.includes("flags shown for the week ${ttSrc.restrictions_week[0]}") && _laBody.includes("&& ttSrc.restrictions_provider && ("));
ok("...and the rail's flags come from the page read alone (no second rail, no client-side merge)",
  /const rail = \(page && page\.clashes\) \|\| \{ flags: \[\], count: 0, sources: \{\} \};/.test(_laBody)
  && !_laBody.includes("...(tt.flags || [])"));
// Mon–Fri only (10 Sep, the human)
ok("⭐ the Commit grid shows Mon–Fri only — weekend days are filtered out of the columns and the cells",
  /\.filter\(iso => !isWeekend\(iso\)\)/.test(_laBody) && _laBody.includes("const weekdaysOf = (line) =>")
  && _laBody.includes("{weekdaysOf(line).map(d => {") && !_laBody.includes("{line.days.map(d => {"));
// 13 Oct 2026 (W3, narrowed): the footer's rule moved to the commit caption's info box
ok("...and the commit grid's info box says so", src.includes("Monday to Friday only: Saturday and Sunday are held at 0 and not shown") && _laBody.includes('<InfoTip id="la.commit" />'));
// calendar weeks (10 Sep): nothing in the browser assumes four weeks a month
ok("🔴 the four-week constant and the 1–7 / 8–14 labels are gone; the Horizon asks the server",
  !/const WEEK_NOS = \[1, 2, 3, 4\]/.test(code) && !code.includes('"8–14"')
  && /const weekNosOf = \(horizon, m\) =>/.test(code) && /weekNosOf\(horizon, m\)\.forEach\(w => cols\.push/.test(_laBody)
  && /W\{w\} · \{weekSpanLbl\(horizon, m, w\)\}/.test(_laBody) && !_laBody.includes("derived ÷4<"));
// the Commit week map (10 Sep): its own small read, one map instance, never the public map in a frame
const _cmBody = code.slice(code.indexOf("function CommitMap("), code.indexOf("function RoutePlanning("));
ok("the Commit map reads /lookahead/geometry with the page's route ids — never the page again, never /public/map-data",
  _cmBody.includes("/lookahead/geometry?ids=") && !_cmBody.includes("/lookahead?") && !_cmBody.includes("map-data") && !_cmBody.includes("<iframe"));
ok("...creates ONE map and keeps it (the guard), and never draws an unbaked route as a line",
  _cmBody.includes("if(mapObj.current || !mapDiv.current || !window.mapboxgl) return;")
  && /if\(r\.geometry && r\.geometry\.length > 1\)\{/.test(_cmBody) && _cmBody.includes("Not drawn (no route worked out)"));   // 13 Oct 2026 (W3, narrowed): plain words
ok("...colours lines by IPT from palette C, and is not rendered under the render harness",
  _cmBody.includes("IPT_PALETTE_C[iptKey(") && _laBody.includes("!initialPage && <CommitMap"));
// 13 Oct 2026 (W6, narrowed): ", today" (one " · " a cell at most)
// NARROWED 17 Oct 2026 (UI fix 2, claude/ui-fix-dark, finding 2): the wash is var(--navy-soft) INLINE — the .tbl th rule
// out-ranks a bg-blue-50 class — so the dark look paints today's column in its own tint (the figures were 1.14:1 on #eff6ff)
ok("today's column carries the wash and the '· today' suffix",
  _laBody.includes('", today"') && _laBody.includes('style={t ? { background: "var(--navy-soft)" } : {}}'));
ok("UI fix 2 (#2): no #eff6ff / #64748b / #B45309 literal is left in the Look-ahead; seven inline var(--navy-soft) washes (today's th and td, the summary row, the Horizon's commit th and two td); the week pill reads var(--muted) when off",
  !/#eff6ff|#64748b|#B45309/i.test(_laBody)
  && (_laBody.match(/\{ background: "var\(--navy-soft\)"/g) || []).length === 7
  && _laBody.includes('style={bucket === b ? { background: "var(--navy-soft)", color: "var(--navy)" } : { color: "var(--muted)" }}'));
ok("...the road-closures line is 13 px in slate-500 (checked) or amber-700 (not checked) — classes the dark look remaps — with no inline colour (was 11 px #64748b / #B45309, 3.64:1 in Dark)",
  _laBody.includes('<div className={"text-[13px] mb-3 flex flex-wrap items-center gap-2 " + (ttSrc.restrictions === "ok" ? "text-slate-500" : "text-amber-700")}>')
  && !_laBody.includes("text-[11px] mb-3 flex flex-wrap") && _laBody.includes('{ttSrc.restrictions === "ok" ? "re-check" : "check now"}'));
// 17 Oct 2026 (UI fix 2, findings 1 and 6): the pressed view pill and the two Confirm week buttons read tokens
ok("UI fix 2 (#1): the pressed view pill (Commit / Account / Horizon) reads var(--control-fg), not an inline white",
  _laBody.includes('style={view === id ? { background: "var(--navy)", color: "var(--control-fg)", borderColor: "var(--navy)" }') && !/color: "white"/.test(_laBody));
ok("UI fix 2 (#6): both Confirm week buttons read the --ok-btn pair (5.48:1 ink, 8.47:1 dark) and carry no text-white; nothing else in the app uses the pair; no text-white sits on var(--green) anywhere",
  (_laBody.match(/style=\{\{ background: "var\(--ok-btn\)", color: "var\(--ok-btn-fg\)" \}\}/g) || []).length === 2
  && (code.match(/var\(--ok-btn\)/g) || []).length === 2 && (code.match(/var\(--ok-btn-fg\)/g) || []).length === 2
  && _laBody.includes('font-semibold rounded-lg" style={{ background: "var(--ok-btn)", color: "var(--ok-btn-fg)" }}>Confirm week</button>')
  && !/text-white[^<]{0,400}var\(--green\)/.test(code));
// NARROWED (H1): the unit word is DU() — km, or mi for a tenant that reads miles
// 13 Oct 2026 (W6, narrowed): the ▶ row's string became the details row, one fact a line, labels in the tenant's unit
ok("the expanded row prints km/trip, km/week, t·km, cycle and € or 'rate not set' — in the tenant's unit",
  _laBody.includes("<RdItem t={`${DU()} a trip`}>{`${grp(dist(c.km_trip))}") && _laBody.includes("<RdItem t={`${DU()} this week`}>{grp(dist(wd.km))}")
  && _laBody.includes("<RdItem t={TKM()}>{`${grp(dist(wd.tonne_km))}") && _laBody.includes('<RdItem t="Cycle">{`${grp(c.cycle_min)} min')
  && _laBody.includes('"Rate not set"'));
// 13 Oct 2026 (W6, narrowed): the sentence is in the details, with a full stop for the " · "
ok("⭐ the honest-gap sentence for an unbaked line ships as written",
  _laBody.includes("<RdItem t={DU()} wide>{`— until the route is worked out. Trips still come from the ${grp(c.payload_t, 1)} t planning payload"));   // 13 Oct 2026 (W3, narrowed): "baked" reads "worked out" 
// 13 Oct 2026 (W6, narrowed): the Lorries cell reads "—" and the details say why
ok("an unbaked line shows trips and NO vehicle count (the human's rule), never a 1",
  _laBody.includes('(c.baked ? <span className="tabular-nums">{grp(f.vehicles)}</span> : <span className="text-amber-700">—</span>)')
  && _laBody.includes('"Needs this line\'s route worked out for its vehicle"') && _laBody.includes('<td>{c.baked ? grp(f.vehicles) : "—"}</td>'));   // 13 Oct 2026 (W3, narrowed): plain words
// 13 Oct 2026 (W6, narrowed): the trigger is RowDetails' chevron, a button with aria-expanded, open per row for the session
ok("the expand trigger is the Routes table's ▶ toggle, reused",
  _laBody.includes('isOpen={laOpen(lk)} onToggle={() => laToggle(lk)}') && _laBody.includes('const [laOpen, laToggle] = useRowOpen("lookahead");'));
ok("the empty state uses EmptyState", _laBody.includes("<EmptyState title={`No approved forecast line in the commit week"));
ok("planned days are saved through PUT /forecast-days with the day's key",
  /send\("\/forecast-days", \{ route_id: line\.route_id, month_index: line\.month_index,[\s\S]*?day_date: d\.day_date, planned_qty:/.test(_laBody)
  && _laBody.includes('"PUT"'));
// slice 4 — export
ok("⭐ export downloads through fetch + blob, never a bare <a href> (the access code is a header)",
  /fetch\(`\$\{API\}\/forecast-weeks\/export\?format=\$\{format\}&bucket=\$\{bucket\}`\)/.test(_laBody)
  && _laBody.includes("URL.createObjectURL(blob)") && !/href=\{`\$\{API\}\/forecast-weeks\/export/.test(code));
ok("...the mock's bar: Export XLSX beside the green Confirm week, PDF as a smaller second button",
  // NARROWED 17 Oct 2026 (UI fix 2, finding 6): the button reads its own pair, --ok-btn / --ok-btn-fg
  _laBody.includes(">Export XLSX<") && _laBody.includes('download("pdf")') && _laBody.includes('background: "var(--ok-btn)", color: "var(--ok-btn-fg)" }}>{anyConfirmed'));
ok("no email and no upload in the page", !/mailto:|sendEmail|<input type="file"/.test(_laBody));
// slice 5 — rates and the confirmed cost
ok("⭐ the confirmed cost is sent ONLY when its box was touched — an absent field leaves it alone",
  /if\(draft\[kc\] !== undefined\) body\.actual_cost_eur =/.test(_laBody)
  && !/actual_cost_eur: draft\[kc\] \?\?/.test(_laBody));
ok("the Account table has Planned €, Actual € and € var columns",
  _laBody.includes(">Planned {CUR()}<") && _laBody.includes(">Actual {CUR()}<") && _laBody.includes(">{CUR()} var<"));
ok("the route form gained a RoutePlanning block with the three rates, the cap and the km basis",
  /function RoutePlanning\(/.test(code) && /<RoutePlanning route=/.test(code)
  && code.includes("/planning${qs}") && ["rate_eur_per_load", "rate_eur_per_t", "rate_eur_per_km", "max_vehicles_per_day", "km_basis"].every(k => code.includes(k))
  && code.includes('<option value="round_trip">') && code.includes('<option value="loaded">'));
ok("🔴 no default rate anywhere in the page — blank means 'rate not set'",
  !/rate_eur_per_\w+: \d/.test(code) && code.includes('Blank = no rate'));
// G2 (16 Sep): the map's band colours are TENANT DATA now (the overlay package), so the
// old "pills equal the band table" check has nothing static to compare against. What
// still holds: the six pill hexes are a product palette and must never reuse a colour the
// map spends on a route, a forecast or a selection — overlay.js's reserved list.
const _ovl = fs.readFileSync(path.join(ROOT, "map", "overlay.js"), "utf8").replace(/\r\n?/g, "\n");
const _reserved = (() => { const m = _ovl.match(/IPT_RESERVED_COLOURS = \[([^\]]*)\]/); return m ? [...m[1].matchAll(/'(#[0-9A-Fa-f]{6})'/g)].map(x => x[1].toUpperCase()) : []; })();
const _pageHex = (() => { const m = code.match(/const IPT_PALETTE_C = \{([^}]*)\}/); const o = {};
  if (m) for (const x of m[1].matchAll(/(IPT\d): "(#[0-9A-Fa-f]{6})"/g)) o[x[1]] = x[2]; return o; })();
ok("⭐ the team pills carry six distinct hexes, none of them a colour the map reserves for routes",
  Object.keys(_pageHex).length === 6 && new Set(Object.values(_pageHex).map(h => h.toUpperCase())).size === 6
  && _reserved.length >= 5 && Object.values(_pageHex).every(h => !_reserved.includes(h.toUpperCase())));
ok("the demo package's band colours are the same hexes as the pills, so map and tables agree",
  (() => { try { const d = JSON.parse(fs.readFileSync(path.join(ROOT, "demo", "uk-corridor.package.json"), "utf8"));
    const ov = JSON.parse(d.tables.config.find(r => r.key === "overlay").value);
    const labels = Object.fromEntries(d.tables.ipts.map(i => [i.label, i.id]));
    return ov.bands.every(b => (_pageHex[labels[b.ipt]] || "").toUpperCase() === b.colour.toUpperCase()); } catch (e) { return false; } })());
// the Horizon view
ok("the Horizon columns carry a ROLE label — account · commit · make-ready · early warning",
  ["ACCOUNT", "COMMIT", "MAKE-READY", "EARLY WARNING"].every(t => _laBody.includes(`"${t}"`)) && _laBody.includes("horizon.roles"));
ok("...and no Confirm button lives on the Horizon view",
  (() => { const i = _laBody.indexOf("{horizon.rows.length === 0"); const j = _laBody.indexOf("{confirming && (", i);
           // 13 Oct 2026 (W3, narrowed): the "No day columns here" note moved to the Line header's info box (la.horizon)
           const h = i > 0 && j > i ? _laBody.slice(i, j) : ""; return h.length > 0 && !h.includes("Confirm week") && h.includes('<InfoTip id="la.horizon" />'); })());
ok("the Horizon footer states the weeks-not-days rule and the blue-column rule",
  // 13 Oct 2026 (W3, narrowed): the footer's two rules are the Horizon info box's text and how
  src.includes("Week totals for the weeks after the commit week, so hauliers are not sent a four-week daily spreadsheet") && src.includes("It is the only week with daily rows."));

let _dsBody;
// ---- 4e. Task D2 — stock held (moved on 10 Sep) --------------------------------------
// The W1–W4 consumption grid is GONE from the Look-ahead. Consumption is typed on the
// Account view for the account week; the read-only balances are on the Dashboard.
ok("🔴 the old Stockpiles grid component no longer exists",
  !/function Stockpiles\(/.test(code) && !/<Stockpiles /.test(code));
// 11 Sep pm: the stock TABLE is gone from the Dashboard — a capacity bar chart in its place
ok("🔴 the Dashboard's stock table is gone: no DashboardStock component, no 'Stock held' heading, no per-week <table> in the stock component",
  !/function DashboardStock\(/.test(code) && !/<DashboardStock /.test(code)
  && /function DashboardStockChart\(/.test(code) && /<DashboardStockChart meta=\{meta\}/.test(code)
  && !(_dsBody = code.slice(code.indexOf("function DashboardStockChart("), code.indexOf("function App("))).includes("<table")
  && !_dsBody.includes("Stock held") && _dsBody.includes('type: "bar"') && _dsBody.includes('indexAxis: "y"'));
ok("...it is read-only: no consume call, no input, in that component",
  !_dsBody.includes("/stockpiles/consume") && !_dsBody.includes("<input"));
ok("...a bar is the balance as a % of the RECORDED capacity, red past 100 %, a dashed line at capacity; no-capacity stockpiles are listed, never drawn as 0 %",
  _dsBody.includes("pct: bal * 100 / sp.capacity_qty") && _dsBody.includes('b.over ? "#DC2626"')
  && _dsBody.includes("sp.capacity_qty != null && sp.capacity_qty > 0") && _dsBody.includes("No capacity recorded")
  && _dsBody.includes("getPixelForValue(100)"));
ok("...the week is picked with chips, defaulting to the week that holds today", _dsBody.includes("setWk(x.k)") && _dsBody.includes("nowKey"));
ok("consumption is typed on the ACCOUNT view through /stockpiles/consume, for the account week",
  _laBody.includes("/stockpiles/consume") && /month_index: account\.week\.month_index,\s*week_index: account\.week\.week_index/.test(_laBody));
ok("...one box per stockpile, and an emptied box is null (not typed), not zero",
  /consumed_qty: \(v === "" \? null : numOr\(v, null\)\)/.test(_laBody) && _laBody.includes("account.stock.map("));
ok("...and the balance is read from /stockpiles", code.includes("/stockpiles?from_month="));
// ⭐ no capacity recorded is NOT zero capacity
ok("⭐ an unset capacity renders '—' / 'not recorded', never 0",
  _dsBody.includes("· max —") && !_dsBody.includes("capacity_qty || 0")
  && /s\.capacity_qty == null \? <span className="text-slate-500">not recorded<\/span>/.test(_laBody));   // 17 Oct 2026 (UI fix 4): slate-500, readable
ok("over capacity uses the existing red, not a reserved route colour",
  _dsBody.includes('b.over ? "#DC2626"') && !_dsBody.includes('over ? "#059669"'));
ok("the panel says inbound comes from typed actuals only",
  code.includes("a week nobody") && code.includes("reported counts as nothing"));
ok("🔴 the Commit view's stock card is gone — the week map stands in its place",
  !_laBody.includes("Stock held") && _laBody.includes("<CommitMap ") && /function CommitMap\(/.test(code));
ok("🔴 the word 'pile' never appears on its own — always 'stockpile' (the human, 10 Sep)",
  !/(?<![Ss]tock)\b[Pp]iles?\b/.test(code));
ok("the capacity fields appear for the four storage types",
  /const STORAGE_TYPES = \["Stockpile", "Site", "Compound", "Railhead"\]/.test(code)
  && /STORAGE_TYPES\.includes\(form\.loc_type\)/.test(code));
ok("...and on other types only when the location receives material",
  /form\.role === "destination" \|\| form\.role === "both"/.test(code));
ok("capacity has ONE write path, its own endpoint",
  (code.match(/\/capacity\$\{qs\}/g) || []).length === 1);

// ---- 4f. Task E — the two new location types -----------------------------------
ok("Railhead and Stockpile are offered as location types",
  /const LOC_TYPES = \["Quarry", "Port", "Compound", "Site", "Railhead", "Stockpile", "Other"\]/.test(code));
ok("Railhead is drawn in the reserved rail colour",
  /"Railhead": "#0F766E"/.test(code));

// ---- 4h. 2026-09-02 Task F — access codes resolved by the server ----------------
ok("⭐ the client-side LOGINS dict with plaintext codes is GONE",
  !/const LOGINS\s*=/.test(code) && !/CAN_APPROVE\s*=/.test(code));
ok("sign-in POSTs the code to /api/auth", code.includes("`${API}/auth`"));
ok("⭐ every /api request carries the code in X-Access-Code, from ONE wrapper",
  code.includes('"X-Access-Code": ACCESS.code') && /window\.fetch = \(url, opts\) =>/.test(code)
  && (code.match(/X-Access-Code/g) || []).length === 1);
ok("the code lives in sessionStorage, not localStorage",
  code.includes('sessionStorage.setItem("modus_access_code"') && !code.includes('localStorage.setItem("modus_access_code"'));
ok("sign-out clears it", code.includes('sessionStorage.removeItem("modus_access_code")'));
ok("canApprove comes from the server payload", /const canApprove = !!\(role && role\.can_approve\)/.test(code));
ok("the form has a team field, labelled with the tenant's word", code.includes('label={iptRequired ? `${TEAM()} (required)` : TEAM()}'));
ok("⭐ a team code's field is locked to its team", code.includes("Your access code is for this ${TEAM().toLowerCase()}"));
ok("⭐ a planner's default is EMPTY, never IPT 1",
  code.includes('useState((access && access.ipt) || "")') && code.includes("— pick a {TEAM().toLowerCase()} —")
  && !/useState\("IPT1"\)/.test(code));
ok("...and the save refuses without one when required",
  code.includes("Pick which ${TEAM().toLowerCase()} this line belongs to before saving."));
ok("the save posts ipt on the line", /ipt: \(iptLocked \? access\.ipt : ipt\) \|\| null/.test(code));
ok("a line with no IPT is flagged on the Forecasts page as planner-only",
  code.includes('"no " + TEAM().toLowerCase()') && code.includes("only planners can see it until one is set"));

// ---- 4g. NOTHING may upload ----------------------------------------------------
// "Never build: file upload, OCR..." — asserted at source level so a later edit that
// adds one trips here rather than shipping.
for (const banned of ['type="file"', "FormData(", ".files[", "multipart/form-data"]) {
  ok(`no upload path: ${banned} is absent`, !code.includes(banned));
}

// ---- 5. the double-counting caution --------------------------------------------
ok("the save surfaces the backend caution", src.includes("caution"));

// ---- 6. things that must NOT have been broken ---------------------------------
for (const keep of [
  ["mapboxgl", "the Mapbox instance is untouched"],
  ["applyEmphasis", "basemap-switch paint restoration survives"],
  ["promote-alt", "promote-to-primary survives"],
  ["RouteAnalysis", "the route analysis panel survives"],
  ["Diagnostics", "the diagnostics panel survives"],
  ["gate_lat", "gate points survive"],
]) {
  ok(keep[1], src.includes(keep[0]));
}

// ---- 7. Phase 3: zones ---------------------------------------------------------
// Source-level again, and here that is not a compromise but the only option: the whole
// feature is map interaction, and there is no browser in this harness. What CAN be
// proved is that the wiring exists and that nothing sends HERE calls by accident.
ok("a Zones page exists", /\{ id: "zones", label: "Zones"/.test(code));
ok("the sub-tab switch is three-way, not 'not locations'",
  code.includes("const onRoutes = subTab === \"routes\"") &&
  code.includes("const onZones = subTab === \"zones\""));
ok("no `!onLoc` branch survives — it would render the routes panel on the Zones tab",
  !code.includes("{!onLoc &&"));
ok("zones are fetched from /api/zones", code.includes("`${API}/zones`"));
ok("zone writes go to the admin endpoint", code.includes("`${API}/admin/zones"));
ok("zone deletion checks the impact first", code.includes("/impact"));
ok("the admin token rides along on zone writes",
  code.includes("tokenRef.current ? `?token=${encodeURIComponent(tokenRef.current)}` : \"\""));

ok("drawing collects vertices from map clicks", code.includes("cbRef.current.addVertex"));
ok("zone drawing is checked BEFORE add-location mode, so the two cannot both fire",
  code.indexOf("zoneDrawRef.current") < code.indexOf('modeRef.current === "add"'));
ok("the drawn ring is explicitly closed before it is sent", code.includes("const ringOf"));
// Phase 4 replaced the literal 3 with minPts(), which is 3 for a zone and 2 for a haul
// road. The rule for zones is unchanged; the assertion follows it to its new home rather
// than being deleted.
ok("a minimum vertex count is enforced before save",
  code.includes("drawPts.length < minPts(zoneForm)"));
ok("a zone still needs three corners and a haul road two",
  /minPts\s*=\s*\(f\)\s*=>\s*isHaul\(f\)\s*\?\s*2\s*:\s*3/.test(code));

ok("saving re-bakes what it invalidated", code.includes("rebakeAfterZone"));
ok("the re-bake drives the existing batch endpoint rather than a new one",
  code.includes("`${API}/admin/bake-routes?${q}`"));
// NARROWED 17 Oct 2026 (Route all 502s): the guard is no longer a cap of 200 calls (short, time-boxed batches could
// reach it on a big network) but "stop when `remaining` stops falling"; test_route_all.py asserts both loops
ok("the re-bake loop has a guard against spinning forever",
  /const rebakeAfterZone = async[\s\S]*?if\(left >= last\) throw new Error\(`\$\{left\} leg\(s\) left and not falling`\);/.test(code));
ok("only the affected vehicle profiles are re-baked",
  code.includes("legs.map(l => l.vehicle_profile)"));
ok("the invalidated leg count is surfaced to the user", code.includes("inv.leg_count"));
ok("approximate matches are declared, not hidden", code.includes("inv.approximate"));

ok("routing zones and advisory zones are drawn differently",
  code.includes("ZONE_ROUTING") && code.includes("ZONE_ADVISORY"));
ok("the panel states that HERE takes boxes, not polygons",
  src.includes("bounding boxes, not polygons"));
ok("the panel shows the box that will actually be sent", src.includes("Sent to HERE as bbox:"));
ok("deactivating is offered as the alternative to deleting",
  src.includes("without deleting it"));
ok("leaving the Zones tab abandons a half-drawn shape",
  code.includes('if(subTab !== "zones"'));

// ---- Phase 4: temporary haul roads -------------------------------------------
// The user requirement was that a haul road is editable ON THE ROUTE, not in a separate
// drawing tool. These assertions are what keeps that true: a HaulRoads panel that lives
// inside the per-route expansion, and no second map or second tab.
ok("there is a haul-road panel", code.includes("function HaulRoads("));
ok("it is rendered inside the per-route expansion, not as its own tab",
  code.includes("<HaulRoads routeId={routeId}"));
ok("RouteAnalysis is given the haul roads to offer", code.includes("haulRoads={haulRoadList}"));
ok("attaching posts to the route's own endpoint",
  code.includes("/haul-roads${qs()}`"));
ok("detaching is a DELETE on the route + zone pair",
  code.includes('method: "DELETE"') && code.includes("haul-roads/${encodeURIComponent(zid)}"));
ok("the traversal order can be changed", code.includes("haul-roads/order${qs()}"));
ok("a haul change drives the SAME re-bake loop as a zone write, not a second one",
  code.includes("onHaulChanged={rebakeAfterZone}"));

ok("a haul road is drawn as an open LineString, not a closed ring",
  code.includes('{ type: "LineString", coordinates: drawPts.map'));
ok("and a zone is still a Polygon", code.includes('{ type: "Polygon", coordinates: [ringOf(drawPts)] }'));
ok("the in-progress preview does not close a haul road",
  code.includes("const line = (!haulNow && drawPts.length >= 3) ? ringOf(drawPts) : drawPts"));
// the pop() that strips a polygon's repeated closing vertex must not run on a haul road,
// or reopening one would shorten it by a point every time
ok("editing a haul road does not pop its last point as if it closed a ring",
  code.includes('if(z.geometry && z.geometry.type === "Polygon"'));

ok("a blank speed is sent as null, not zero", code.includes("? Number(zoneForm.speed_kph) : null"));
ok("the speed field explains that HERE will not take a custom speed",
  src.includes("will not accept a custom speed"));
ok("the mode field says which failure mode is invisible",
  src.includes("wrong without warning"));
ok("splice is named as the default", src.includes("Default (splice)"));

ok("the panel says a haul road does nothing until it is attached",
  src.includes("does nothing until it is"));
ok("an unattached haul road is called out in the zones table", src.includes("no routes"));
ok("the single-option regression is stated where the roads are attached",
  src.includes("single option"));
ok("an assigned haul speed is marked in the cycle column", src.includes("haul_speed_applied"));
ok("and the HERE-timed cycle is offered alongside it", code.includes("r.cycle_hr_here"));

ok("haul roads have their own colour — red would read as 'closed'",
  code.includes("const ZONE_HAUL"));
ok("the map draws them by kind, not by affects_routing",
  code.includes('is_haul: z.kind === HAUL_KIND'));
ok("the haul kind is a constant, not a string literal scattered about",
  code.includes('const HAUL_KIND = "haul_road"'));
ok("the Phase 4 placeholder label is gone from the kind list",
  !src.includes("Haul road (Phase 4)"));

// ---- Phase 2.5a: road restrictions on a route --------------------------------
ok("there is a per-route restriction panel", code.includes("function RouteRestrictions("));
ok("it is rendered inside the route expansion, beside the haul roads",
  code.includes("<RouteRestrictions routeId={routeId} />"));
ok("it reads the per-route endpoint", code.includes("/restrictions`"));
// ⚠️ These four were REVERSED, not deleted, once the real Tark Tee schema was read.
// restriction_limit is a genuine number in tonnes or metres, so mass/height/width DO get
// a verdict now. The original point — no invented verdict on a bridge LOAD CLASS — is
// narrowed to exactly that case rather than dropped.
ok("the restriction's actual value is shown, not just its existence",
  code.includes("{h.limit}") && code.includes("h.unit"));
ok("a real EXCEEDS verdict is given where two numbers share a unit",
  code.includes('h.verdict === "exceeds"') && src.includes("EXCEEDS by"));
ok("and the margin either way is quantified", code.includes("h.margin"));
ok("but a bridge load class is still NOT converted to tonnes",
  src.includes("load class is not a tonnage") || src.includes("a weak bridge's load class is not a tonnage"));
ok("an uncomparable restriction says 'not comparable' rather than guessing",
  src.includes("not comparable"));
ok("and carries the reason it could not be compared", code.includes("h.note"));
ok("the vehicle's own figure is shown beside the limit",
  code.includes("h.vehicle_value"));
ok("the panel says it is advisory and not fed to the router",
  src.includes("The router is never given this data"));
ok("a partial fetch is declared rather than passing as a clean check",
  code.includes("fetch_errors") && src.includes("not a complete check"));
// NARROWED (H1): the provider's short name comes from TENANT.restrictions, never a literal.
ok("an unreachable service degrades to a note, not an error banner",
  src.includes("Road restrictions unavailable — {prov} could not be reached") && !src.includes("Tark Tee could not be reached"));
ok("a route with no hits says so explicitly rather than rendering nothing — closures or restrictions by provider",
  src.includes("`No ${prov} restrictions in force within ${data.match_m} m of this route.`")
  && src.includes("`No ${prov} planned closures (current or future) within ${data.match_m} m of this route.`")
  && !src.includes("No Tark Tee restrictions"));
ok("H1: the panel's source line is the API's attribution, and the panel is absent for a tenant with no provider",
  src.includes("Source: {data.attribution || (TENANT.restrictions && TENANT.restrictions.attribution) || prov}.")
  && src.includes("if(!TENANT.restrictions) return null;") && !src.includes("Estonian Transport Administration"));
ok("expired records are declared as excluded, not silently dropped",
  code.includes("expired_or_future_excluded"));

// ---- Phase 5a: gates, and the turnaround split -------------------------------
ok("the gate editor is present on the Locations panel",
  code.includes("saveGate") && code.includes("gateForm"));
ok("gates are only offered once a location exists — a gate needs a location_id",
  src.includes("Gates can be added once the location has been created"));
ok("a gate can be placed by clicking the map, like every other point in this app",
  code.includes("placeGateAt") && code.includes("gatePlaceRef"));
ok("gate placement is a separate click mode from node placement",
  code.includes("gatePlaceRef.current") && code.includes('modeRef.current === "add"'));
ok("leaving the Locations tab abandons a half-placed gate",
  src.includes('if(subTab !== "locations") setGatePlace(false)'));
ok("the three directions are offered by their meaning, not by their column value",
  src.includes("Entry only") && src.includes("Exit only") && src.includes("In and out"));
ok("induction time is editable per gate (B3)", code.includes("safety_minutes"));
ok("the flat gate-to-face allowance is editable per gate (B5)",
  code.includes("internal_travel_minutes"));
// copy replaced 2026-09-02 with the human's wording; the B5(c) statement survives
ok("the UI says the flat allowance is IGNORED where a haul road is drawn — B5(c)",
  src.includes("ignored if the") && src.includes("not counted twice"));
ok("the two gate fields carry the 2026-09-02 label copy",
  src.includes("Safety / briefing at this gate. Once per arrival.")
  && src.includes("Drive from this gate to the face. Ignored if the route uses a drawn haul road."));
// §2 — old spelling accepted on read, never written
ok("the old 'Rail head' spelling is read as 'Railhead'",
  /const locTypeOf = \(t\) => \(t === "Rail head" \? "Railhead" : t\)/.test(code)
  && (code.match(/locTypeOf\(p\.loc_type\)/g) || []).length >= 2);
ok("...and appears nowhere else in the app", (code.match(/"Rail head"/g) || []).length === 1);
ok("a deactivated gate is shown as deactivated rather than just missing",
  src.includes("deactivated"));

ok("routes can select a gate at each end", code.includes("RouteGates")
  && code.includes("origin_gate_id") && code.includes("dest_gate_id"));
ok("'no explicit choice' is an offered option, not an empty select",
  src.includes("Default for this site"));
ok("B2: a blocked route says so on the collapsed row, not only when expanded",
  src.includes("gate blocked") && code.includes("r.gate_blockers"));
// 13 Oct 2026 (W3, narrowed): plain words for the same two warnings
ok("and the blocker text names what is wrong",
  src.includes("This route cannot be routed"));
ok("changing a gate warns that the stored route is now stale",
  src.includes("this route still goes to the old gate until it is routed again"));

ok("the turnaround cell reads the backend's total, never its own sum",
  code.includes("r.turnaround_hr") && !code.includes("load_minutes + r.unload_minutes"));
ok("the turnaround breakdown comes from the backend's parts",
  code.includes("r.turnaround_parts"));
ok("the tooltip explains a drawn-road cycle rather than hiding the missing allowance",
  src.includes("not a flat allowance"));
ok("the 125% lesson is recorded where the total is displayed",
  src.includes("125%"));
ok("the factors panel no longer calls its load+unload figure 'turnaround'",
  !code.includes("v.turnaround_hr") && code.includes("v.unloading_hr"));

// ---- 8. 2.5b: the page architecture -------------------------------------------
// The left rail replaced the tab row, My submissions and Approvals became one page,
// routes became editable and factors.json became editable. Everything here is
// source-level: there is no browser in this harness, so what can be proved is that the
// wiring exists and that the two things that would break silently — the shared Mapbox
// instance and the scope of a withdraw — are still right.

// 8a. the rail
ok("the nav is four groups in order: Plan, Track, Data, Map",
  (code.match(/group: "(Plan|Track|Data|Map)"/g) || []).join(",") === 'group: "Plan",group: "Track",group: "Data",group: "Map"');
ok("⭐ only the Data group is admin-gated", /group: "Data", admin: true/.test(code)
  && (code.match(/admin: true/g) || []).length === 1);
ok("an admin-only page falls back to the dashboard rather than a blank screen",
  code.includes("if(!allowed.has(page)) setPage(\"dashboard\")"));
ok("the rail collapses and the page survives a refresh",
  code.includes('localStorage.getItem("modus_page")') && code.includes('localStorage.setItem("modus_rail"'));
ok("the pending count badges Forecasts for approvers only",
  code.includes('it.id === "forecasts" && canApprove && pending > 0'));

// 8b. ⭐ ONE Mapbox instance across Locations / Routes / Zones
// Three nav entries, one component. Rendering DataManagement in three separate
// branches would unmount and remount it on every switch — the map would reload its
// style, lose its sources and jump back to the default viewport. This is the
// assertion that catches that.
ok("⭐ Locations/Routes/Zones render exactly ONE <DataManagement>",
  (code.match(/<DataManagement/g) || []).length === 1);
ok("...selected by DATA_PAGES, not by three separate branches",
  code.includes("DATA_PAGES.includes(page) && canApprove") &&
  /const DATA_PAGES = \["locations", "routes", "zones"\]/.test(code));
ok("...and the page reaches it as a prop", /<DataManagement meta=\{meta\} who=\{who\} subTab=\{page\}/.test(code));
ok("the old in-component sub-tab bar is gone",
  !code.includes('["zones", "Zones", zoneList.length]'));
// A map click that opens a node, or "create a route from here", still switches page
// from inside the component. Each of those must tell the rail too, or the rail and the
// panel disagree about which page you are looking at.
ok("⭐ an internal page switch tells the rail as well",
  code.includes("const setSubTab = (t) => { setSubTabState(t); if(onSubTab) onSubTab(t); }"));
ok("...and a page change from the rail is mirrored inward",
  /if\(propSubTab && propSubTab !== subTab\) setSubTabState\(propSubTab\)/.test(code));

// 8c. Forecasts — My submissions and Approvals, merged
// NARROWED 11 Oct 2026 (the carbon target line: the render harness hands it in as initialTarget)
ok("there is one Forecasts page, not two lists",
  code.includes("function Forecasts({ meta, who, access, onEdit, onChanged, initialCost, initialRows, initialTarget })")
  && !code.includes("function MySubmissions") && !code.includes("function Approvals("));
ok("lines group per route + discipline + section, not per month",
  code.includes('const key = [r.route_id, disc, sect].join("|")'));
ok("a group spanning several statuses reads Mixed rather than picking one",
  code.includes('e.statuses.size === 1 ? [...e.statuses][0] : "Mixed"'));
ok("⭐ withdraw is scoped to the months the row shows, never 1..count",
  code.includes('from: String(g.minMonth), to: String(g.maxMonth)'));
ok("⭐ a submitter withdraws only its own lines; an approver is not narrowed",
  code.includes('if(!canApprove) p.set("submitted_by", who)'));
// 11 Oct 2026: the demo stores submitters as "IPT3 planner", and the Submit page printed it raw
// ("…earthworks / WS1 (IPT3 planner)") — a team id on screen. Every place that SHOWS a submitter goes
// through teamText(); the comparisons with `who` and the withdraw filter keep the stored value.
ok("🔴 the route's other lines on Submit show the submitter through teamText (no IPTn on screen)",
  code.includes('${s.submitted_by ? " (" + teamText(s.submitted_by) + ")" : ""}')
  && !code.includes('" (" + s.submitted_by + ")"'));
ok("🔴 the save caution, withdraw prompt, row title, row menu and CSV show teamText(submitter)",
  code.includes(', submitted by ${teamText(l.submitted_by)}') && !code.includes(', submitted by ${l.submitted_by}')
  && code.includes('(submitted by ${teamText(g.submittedBy)})') && !code.includes('(submitted by ${g.submittedBy})')
  // 13 Oct 2026 (W6, narrowed): the row title is the details' "Submitted by" line
  && code.includes('<RdItem t="Submitted by">{`${teamText(g.submittedBy) || "—"}') && code.includes('Submitted by {teamText(g.submittedBy) || "—"}')
  && !/Submitted by \$?\{g\.submittedBy/.test(code)
  && code.includes('g.months, g.status, teamText(g.submittedBy),'));
ok("...the Forecasts search finds a line by its team NAME as well as the stored value",
  code.includes('${g.submittedBy} ${teamText(g.submittedBy)}`.toLowerCase()'));
ok("...the signed-in name under the rail goes through teamText too",
  code.includes('{teamText(who) || "—"}</span>'));
ok("...and ownership still compares the STORED submitter (teamText is display only)",
  code.includes('const own = g.submittedBy === who;') && code.includes('(!f.mine || g.submittedBy === who)'));
ok("⭐ a rejection without a reason is refused, not stored blank",
  code.includes('A rejection needs a reason — nothing was changed.'));
ok("edit hands back the whole year span, not one year",
  /onEdit\(\{ routeId: g\.routeId, year: g\.fromYear, toYear: g\.toYear/.test(code));
ok("approve/reject are shown only to approvers",
  (code.match(/canApprove && g\.status !== "(Approved|Rejected)"/g) || []).length === 2);

// 8d. Config — the editable copy of factors.json
ok("the Config page saves the whole document to the admin endpoint",
  code.includes("`${API}/admin/config/factors${qs}`") && code.includes('method: "PUT"'));
ok("...and can put the file back", code.includes("admin/config/factors/reset"));
ok("⭐ it says the file is only the seed once the row exists",
  src.includes("Reset to file") && src.includes("differs from the file in the repo"));
ok("a raw JSON tab exists for what the forms do not cover",
  code.includes('["raw", "Everything (JSON)"]'));
ok("bad JSON in the raw tab is refused before it is sent",
  code.includes('setRawErr("Not valid JSON: "'));
ok("the vehicle id is not editable — baked geometry is keyed on it",
  src.includes("it cannot be renamed here"));

// 8e. route editing in place
ok("a route row can be edited", code.includes("startEditRoute") && code.includes("saveRouteEdit"));
ok("⭐ the impact is fetched and confirmed BEFORE the write",
  code.indexOf("/impact") < code.indexOf('method: "PATCH"') && code.includes("Continue?"));
ok("the write is a PATCH of the changed fields, not a delete and re-create",
  code.includes('method: "PATCH"') && !code.includes("recreateRoute"));
ok("the route id itself is not editable while editing",
  code.includes("disabled={!!editingRoute}"));

// 8e-ter. 2026-09-09: changing which VEHICLES a route is baked for.
//
// The reported bug was "edit route cannot change vehicle", and the guard that caused it
// was deliberate -- the panel hid the tick-boxes whenever editingRoute was set. Removing
// a guard is exactly the kind of change that leaves no textual trace if it regresses, so
// the retired guard is asserted ABSENT rather than the new behaviour merely asserted
// present. Reversed from what it said before this shipped; never delete an assertion.
ok("🔴 the vehicle tick-boxes are no longer hidden while editing a route",
  !code.includes("{!editingRoute && ("));
ok("...and the panel says what ticking and unticking now MEAN while editing",
  src.includes("tick to route, untick to remove"));   // 13 Oct 2026 (W3, narrowed): plain words

// The edit set is separate state. Sharing rVehicles would have been one line shorter and
// would have silently re-pointed the network-wide Bake all button at whatever the route
// under edit happens to carry -- while its own tooltip still said the list came from the
// Create panel.
ok("⭐ the edited vehicle set is its OWN state, not rVehicles",
  code.includes("const [eVehicles, setEVehicles]") && code.includes("const toggleEVehicle"));
{
  const i = code.indexOf("const bulkBake = async");
  const j = code.indexOf("const clearRoutes", i);
  const body = i >= 0 && j > i ? code.slice(i, j) : "";
  ok("🔴 bulk bake still reads rVehicles and never the edit set",
    body.includes("rVehicles.length ? rVehicles") && !body.includes("eVehicles"));
}

{
  const i = code.indexOf("const saveRouteEdit = async");
  const j = code.indexOf("const deleteRoute = async", i);
  const body = i >= 0 && j > i ? code.slice(i, j) : "";
  ok("the save computes BOTH directions of the vehicle diff against what is cached",
    body.includes("Object.keys(cur.profiles || {})")
    && /const add = eVehicles\.filter/.test(body)
    && /const drop = had\.filter/.test(body));
  // A move clears every profile server-side. Restoring affected.profiles afterwards --
  // which is what this did before the diff existed -- would bring back a profile the
  // user had just unticked, and the route list would show it as though nothing happened.
  ok("🔴 a moved route re-bakes the NEWLY TICKED set, not the profiles it used to have",
    body.includes("const toBake = moved ? eVehicles : add") && !body.includes("rebakeAffected"));
  // Without route_id this call clears the profile from EVERY route in the network. The
  // parameter is the whole point of the backend half of this change.
  ok("🔴 dropping a vehicle clears geometry for THIS ROUTE only",
    /clear-geometry/.test(body)
    && /route_id: editingRoute, profile: prof/.test(body));
  // 13 Oct 2026 (W3, narrowed): plain words
  ok("the confirm names the forecast lines a dropped vehicle leaves reading 'not routed'",
    body.includes("forecast_vehicles") && body.includes("not routed"));
  ok("...and warns when the last vehicle is being removed",
    body.includes("NO routed vehicle at all"));
}
ok("each tick-box says whether it will be baked, removed, or is already baked",
  code.includes('"will be routed"') && code.includes('"will be removed"'));   // 13 Oct 2026 (W3, narrowed): plain words
ok("the Save button shows the vehicle change before the confirm dialog does",
  code.includes("Save changes · "));

// 8e-bis. the names the UI calls things
// Renaming a page and leaving its old name in a hint is exactly the dangling-text
// failure that source-level assertions exist to catch; it has bitten twice already.
ok("⭐ no visible text still points at the retired 'Data Management tab'",
  !src.includes("Data Management tab") && !/in Data\s+Management/.test(src));
ok("...and nothing calls the data pages 'sub-tabs' to the user",
  !/sub-tab/i.test(src.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, "")));

// 8f. the shared page furniture
ok("one PageHeader component, and every portal page uses it",
  (code.match(/function PageHeader\(/g) || []).length === 1
  && (code.match(/<PageHeader/g) || []).length >= 6);
// The layout pass is only worth anything if it is the ONLY way a page titles itself.
// A page that hand-rolls its own heading drifts on font size, spacing and colour, which
// is exactly what 2.5b was asked to stop.
ok("⭐ no portal page hand-rolls its own heading any more",
  !/<h1 className="text-lg font-bold/.test(code) && !/<h2 className="text-lg font-bold/.test(code));
ok("there is a shared empty state", code.includes("function EmptyState("));

// ---- 4f. 10 Sep evening — the fuel widget, target rate and Quote + BAF ---------------
const _fwBody = code.slice(code.indexOf("function FuelWidget("), code.indexOf("function LookAhead("));
// 17 Oct 2026 (UI fix 2, finding 2): the BAF figure's "no share" grey is the token (identical in Ink; 3.42:1 -> 6.25:1 in Dark)
ok("UI fix 2 (#2): the fuel card's BAF figure reads var(--navy) or var(--muted), never the light-look grey literal",
  _fwBody.includes('style={{ color: sum.baf_pct != null ? "var(--navy)" : "var(--muted)" }} title={baseTxt}>{bafTxt}</span>') && !/#64748b/i.test(_fwBody));
const _ctBody = code.slice(code.indexOf("function CostingTab("), code.indexOf("function ConfigPage("));
ok("⭐ ONE FuelWidget component, mounted THREE times: Commit (compact), Account (strip), Config (config)",
  (code.match(/function FuelWidget\(/g) || []).length === 1 && (code.match(/<FuelWidget\b/g) || []).length === 3
  && /<FuelWidget mode="compact"/.test(_laBody) && /<FuelWidget mode="strip"/.test(_laBody) && /<FuelWidget mode="config"/.test(_ctBody));
// NARROWED (H1): the attribution is the provider the API names (idx.provider.label) — the
// bulletin for EU-27, DESNZ for GB — and the widget carries no country fallback of its own.
ok("...the widget reads /fuel-index and never the feed host; it names the provider the API gives it",
  _fwBody.includes("fetch(`${API}/fuel-index?lazy=") && !/eurooilwatch\.com/i.test(code)
  && _fwBody.includes("const prov = idx.provider || (idx.auto_available ? TENANT.fuel_provider : null);")
  && _fwBody.includes("(prov ? prov.label : \"automatic index\")") && !_fwBody.includes("EU Weekly Oil Bulletin via EuroOilWatch"));
ok("H1: no fallback to Estonia in the widget — a tenant with no country reads 'no country'",
  !_fwBody.includes('fuelS.country || "EE"') && _fwBody.includes('const country = noCountry ? "no country" : rawCountry;')
  && _fwBody.includes("no country set"));
ok("H1: the widget shows the ex-VAT figure when the API derives one (DESNZ pump prices include VAT)",
  _fwBody.includes("idx.ex_vat_per_l") && _fwBody.includes("ex-VAT"));
ok("...settings go to PUT /fuel-index/settings; manual index, refresh and reset-base are ADMIN calls with the token",
  _fwBody.includes('put("/fuel-index/settings"') && _fwBody.includes('"/admin/fuel-index/manual"')
  && _fwBody.includes('"/admin/fuel-index/refresh?sync=1"') && _fwBody.includes("/admin/fuel-index/reset-base?")
  && /token=\$\{encodeURIComponent\(token\)\}/.test(_fwBody));
ok("...the yard and share boxes are typeable by approvers only, and an emptied box sends null (not 0)",
  _fwBody.includes("access.can_approve") && /const v = draft\[k\] === "" \? null : numOr\(draft\[k\], null\)/.test(_fwBody));
ok("...it says 'Index unavailable' with no price, 'stale' after 8 days, and why there is no BAF",
  _fwBody.includes("Index unavailable") && _fwBody.includes(">stale<") && _fwBody.includes("set a base on Confirm week")
  && _fwBody.includes("type a fuel share"));
ok("...and it polls `refresh` while the server's background fetch runs — never blocks on it",
  _fwBody.includes("rf.running") && _fwBody.includes("setTimeout(() => load(false).then(poll), 3000)"));
ok("🔴 nothing is seeded in the page: no 25 % share and no €1.9x price as a default",
  !/share_pct[^\n]{0,40}25\b/.test(_fwBody) && !/1\.9\d/.test(_fwBody) && !/1\.9\d/.test(_ctBody));
ok("the Commit KPI strip is eight cards with the widget right of t·km, and the planned € caption counts target lines and shows + BAF",
  _laBody.includes("xl:grid-cols-8") && _laBody.indexOf('caption={`${TKM()} · route basis`}') < _laBody.indexOf('<FuelWidget mode="compact"')
  && _laBody.indexOf('<FuelWidget mode="compact"') < _laBody.indexOf("planned ${CUR()} · no rate typed")
  && _laBody.includes("at target") && _laBody.includes("+ BAF ${CUR()} ${grp(totals.eur_adj)}"));
ok("...the expanded Commit row and the Account cell print '+ BAF' as a SECOND figure and mark a target-priced line",
  // 13 Oct 2026 (W6, narrowed): the Commit row's BAF is its own line in the details
  _laBody.includes('<RdItem t="Plus the fuel surcharge (BAF)">{wd.eur_adj != null ? `${CUR()} ${grp(wd.eur_adj)}` : null}</RdItem>') && _laBody.includes("+ BAF {CUR()} {grp(r.planned_eur_adj)}")
  && _laBody.includes('r.rate_source === "target"') && _laBody.includes('c.rate_source === "target"'));
ok("...and the Account footer says the quote is never replaced and € var is against the quote",
  // 13 Oct 2026 (W3, narrowed): the Account footer moved to the Planned cost header's info box (la.cost_quote)
  src.includes("the quote is never replaced") && src.includes("The cost variance compares the actual against the quote") && _laBody.includes('<InfoTip id="la.cost_quote"'));
ok("the Account strip is mounted above the KPI grid; the widget is passed the page's own costing block",
  _laBody.indexOf('<FuelWidget mode="strip"') < _laBody.indexOf('caption="last week delivered · 98% band"')
  && (_laBody.match(/initial=\{page && page\.costing\}/g) || []).length === 2);
ok("Config has a 'Costing · fuel' tab whose target rate saves to PUT /admin/costing/target with the admin token — not inside the factors document",
  code.includes('["costing", "Costing · fuel"]') && _ctBody.includes("/admin/costing/target${qs}")
  && !_ctBody.includes("admin/config/factors") && _ctBody.includes("Save target rate"));
ok("...three target inputs; a blank sends null (clears), and the copy says target is used ONLY where the route has no rate",
  (_ctBody.match(/rate_eur_per_(load|t|km)/g) || []).length >= 6 && _ctBody.includes('if(draft[k] === ""){ body[k] = null; return; }')
  && _ctBody.includes("Used ONLY for routes with no rate typed on the route form"));
ok("the route form says a typed rate is used alone and never mixed with the target",
  code.includes("A typed rate here is used ALONE; it is never mixed with the target."));
ok("LookAhead now receives the role (for the widget's typeable boxes)", /<LookAhead meta=\{meta\} who=\{who\} access=\{role\} \/>/.test(code));
ok("🔴 no fuel on the public map: map/index.html has no widget, no fuel-index, no BAF",
  !/FuelWidget|fuel-index|\bBAF\b/.test(fs.readFileSync(path.join(__dirname, "..", "..", "map", "index.html"), "utf8").replace(/\r\n?/g, "\n")));

// ---- 4g. 10 Sep night — the fair-price model on the page -------------------------------
// NARROWED (H1): the field list is FAIR_FIELDS_FOR(), a function — CUR() and DU() are the
// tenant's and land with /api/meta, so a module constant would print the defaults.
const _fpBody = code.slice(code.indexOf("const FAIR_FIELDS_FOR = "), code.indexOf("function ConfigPage("));   // the field list sits just above the component
ok("⭐ ONE FairPriceSection, mounted once inside the Costing tab, editing doc.fair_price through the page's upd()",
  (code.match(/function FairPriceSection\(/g) || []).length === 1 && (code.match(/<FairPriceSection\b/g) || []).length === 1
  && _ctBody.includes("<FairPriceSection doc={doc} upd={upd} fileDoc={fileDoc}") && _fpBody.includes("d.fair_price = JSON.parse(JSON.stringify(fileFp))"));
ok("...it saves through the factors document (the page's Save + admin token), never its own endpoint",
  !_fpBody.includes("fetch(") && _fpBody.includes("Saved with the page's Save button (admin token)"));
ok("...the four money coefficients, the three consumption figures, the uplift and both month pickers are editable",
  ["driver_eur_per_h", "vehicle_standing_eur_per_h", "running_eur_per_km", "margin_pct"].every(k => _fpBody.includes(`"${k}"`))
  && _fpBody.includes("l_per_100km_per_tonne") && _fpBody.includes("f.consumption.rigid.l_per_100km_empty") && _fpBody.includes("f.consumption.artic.l_per_100km_empty")
  && _fpBody.includes("winter_consumption_uplift_pct") && _fpBody.includes('monthsBox("winter_months"') && _fpBody.includes('monthsBox("thaw_months"'));
ok("...and says which three are assumptions", (_fpBody.match(/ASSUMPTION/g) || []).length === 3);
ok("...a live document without the block shows the file's values and says so",
  _fpBody.includes("const fp = (doc && doc.fair_price) || fileFp") && _fpBody.includes("the live document has no fair_price block yet"));
ok("the Look-ahead prints the fair figure as a THIRD figure, marked 'model': KPI caption, expanded row, Account column",
  // 13 Oct 2026 (W6, narrowed): the Commit row's fair figure is the details' "Fair cost (model)" line
  _laBody.includes("fair ${CUR()} ${grp(totals.fair_eur)} (model") && _laBody.includes('<RdItem t="Fair cost (model)">{wd.fair_eur != null && c.fair ? `${CUR()} ${grp(wd.fair_eur)}') && _laBody.includes("Fair {CUR()} <span")
  && _laBody.includes("{CUR()} {grp(r.planned_fair_eur)}"));
ok("...with the winter and thaw flags on the Account cell and the expanded row",
  _laBody.includes('(r.fair_flags || []).includes("WINTER")') && _laBody.includes('(r.fair_flags || []).includes("THAW")')
  // 13 Oct 2026 (W6, narrowed): the expanded row's flags are words through fairWords (winter, thaw)
  && _laBody.includes("fairWords(c.fair.flags)") && src.includes('(flags || []).includes("THAW") ? "thaw restrictions may apply"'));
// 13 Oct 2026 (W3, narrowed): plain words
ok("...an unbaked line prints — with the reason, never a number", _laBody.includes("No fair price: the route is not routed yet for this vehicle, or the diesel index is missing"));
// 13 Oct 2026 (W3, narrowed): the footer moved to the Fair column's info box (la.cost_fair)
ok("...and the Fair column's info box calls it a floor for negotiation, never a quote", src.includes("A floor for negotiation, never a quote.") && _laBody.includes('<InfoTip id="la.cost_fair" />'));
ok("the Config page hands the file document to the tab (for the fallback values)", code.includes("setFileDoc(j.file || null)"));

// ---- 11 Sep pm: the big-screen Dashboard ---------------------------------------------
const _tdBody = src.slice(src.indexOf("function DashboardToday("), src.indexOf("function DashboardStockChart("));
// 13 Oct 2026 (W3, narrowed): the hover title became an info box; none is bare still
ok("🔴 every KPI figure carries an info box (was: a hover title) — none is bare",
  _dbBody.split("<Fig ").slice(1).length >= 16 && _dbBody.split("<Fig ").slice(1).every(chunk => chunk.slice(0, chunk.indexOf("/>")).includes("info={{ id: \"")));
ok("🔴 no KPI figure is truncated: no `truncate` on a Fig, the value is nowrap with a clamp() size, two per row",
  // 14 Oct 2026 (narrowed): the clamp() size moved from the inline style to CSS (.fig-val), so the big screen can scale it
  !/kpi-num[^"]*truncate/.test(_dbBody) && _dbBody.includes('kpi-num font-bold whitespace-nowrap fig-val') && /\.fig-val\{font-size:clamp\(1\.1rem,1\.45vw,1\.7rem\);\}/.test(html)
  && _dbBody.includes('<div className="grid grid-cols-2 gap-x-4 gap-y-3">{children}</div>'));
// 13 Oct 2026 (W3, narrowed): the exact figure rides in the info box's value line
ok("millions print compact (bigNum) with the exact figure in the info box",
  /const bigNum = /.test(src) && _dbBody.includes("bigNum(K.totT)") && _dbBody.includes("value: `Exactly ${grp(K.totT)} t`"));
ok("the four KPI groups: Delivered to date · Volume · Cost · Carbon",
  ['title="Delivered to date"', 'title="Volume"', 'title="Cost"', 'title="Carbon"'].every(t => _dbBody.includes(t)));
ok("🔴 delivered to date is the SERVER's actual_tonnes summed — never a share of the forecast, None until reported",
  _dbBody.includes("if(r.actual_tonnes != null){ T.actualT = (T.actualT || 0) + r.actual_tonnes;") && _dbBody.includes('K.actualT == null ? "—"')
  && !_dbBody.includes("actual_qty *") );
ok("the Today strip reads /api/lookahead (commit bucket, restrictions OFF) in its own fetch, and a failure never hides the programme figures",
  _dbBody.includes("fetch(`${API}/lookahead?bucket=commit&restrictions_on=0`)") && _dbBody.includes("setWeekErr(") && _dbBody.includes("<DashboardToday meta={meta} week={week} err={weekErr}"));
ok("...today's rows are the day rows whose date is the server's `today` — the server's tonnes, trips, vehicles per day, nothing derived",
  _tdBody.includes("d.day_date !== today") && _tdBody.includes("tonnes: dv.tonnes, trips: dv.trips, vehicles: dv.vehicles")
  && !_tdBody.includes("/ payload") && !_tdBody.includes("payload_t *"));
ok("...with this week to date and last week's account (the server's actual_t, reported, delivered, hold band)",
  _tdBody.includes("This week to date") && _tdBody.includes("acct.actual_t") && _tdBody.includes("acct.hold_band"));
ok("...and the small map is the Look-ahead's CommitMap, title and height as props, defaults unchanged for the Look-ahead",
  // 14 Oct 2026 (narrowed): + `fill`, the big screen's map takes its whole card (the default is unchanged)
  _tdBody.includes('<CommitMap meta={meta} bucket="commit"') && src.includes("function CommitMap({ meta, bucket, tick, lines, title, height, flush, fill })")
  && src.includes('{title || "This week\'s movements"}') && src.includes("height: height || 380"));
ok("🔴 cost never reaches the map: no €, eur, fair or rate anywhere in CommitMap (its hover carries quantity and trips only)",
  !/€|\beur\b|_eur|fair|rate_|\brates?\b|planned_units|eur_units/i.test(_cmBody) && _cmBody.includes("trips`).join"));
ok("big-screen mode: fullscreen requested (never required), filters and the table hidden, both reads refreshed every 5 minutes, Esc leaves",
  _dbBody.includes("requestFullscreen") && _dbBody.includes("REFRESH_MS") && src.includes("const REFRESH_MS = 5 * 60 * 1000")
  // 10 Oct 2026 NARROWED: the filters sit in the header (three that matter) with the rest behind "More filters",
  // and the route table is a collapsed section of the working view — both are still gated on !wall
  && _dbBody.includes("{!wall && <>") && _dbBody.includes("More filters ▾") && _dbBody.includes("{!wall && <AppliedChips")
  && _dbBody.includes('data-dash-table="1"') && _dbBody.indexOf('data-dash-table="1"') < _dbBody.indexOf("      ) : (\n        <>\n")
  && _dbBody.includes('e.key === "Escape"') && _dbBody.includes("fullscreenchange"));
ok("interactive: a route row (or a Top-routes bar) narrows the charts and figures to that line; the table stays whole; a chip clears it",
  _dbBody.includes("const narrowed = lineKey ? filtered.filter(r => keyOf(r) === lineKey) : filtered;")
  // 13 Oct 2026 (W6, narrowed): the click rides on RowDetails' rowProps; the chevron stops it (stopPropagation)
  && _dbBody.includes("rowProps={{ onClick: () => pick(r.key),") && _dbBody.includes("pick(topN[els[0].index].key)") && src.includes("onClick={(e) => { e.stopPropagation(); onToggle(); }}")
  && _dbBody.includes("✕ show all") && _dbBody.includes("filtered.forEach(r => {") && _dbBody.includes("narrowed.forEach(r => {"));
ok("a Delivered-against-plan chart (planned t as bars, reported t over them) and a Delivered column in the table",
  _dbBody.includes("Delivered against plan") && _dbBody.includes("actualM") && _dbBody.includes('setSort("deliveredPct")'));
ok("nothing on the Dashboard writes", !/fetch\(`\$\{API\}[^`]*`,\s*\{\s*method/.test(_dbBody + _tdBody + _dsBody));

// ---- 2026-09-14: the user guide is reachable from the app --------------------
// It has been served at /help/ since 10 Sep and NOTHING linked to it: the only way in
// was to type the URL. That is why the human could not find it.
// NARROWED 14 Oct 2026 (D9): the rail and, on a phone, the More sheet (the rail is not drawn there) — once each
ok("\u2b50 the rail links to the user guide at /help/, exactly once (and the phone's More sheet once)",
   (src.match(/href=\{"\/help\/\?role="/g) || []).length === 2
   && (src.slice(src.indexOf("function PhoneMore("), src.indexOf("function DeskOnly(")).match(/href=\{"\/help\/\?role="/g) || []).length === 1);
ok("...carrying the signed-in role, so the guide opens on the right view",
   /href=\{"\/help\/\?role=" \+ encodeURIComponent\(\(role && role\.role\) \|\| ""\)\}/.test(src)
   && (src.match(/href=\{"\/help\/\?role=" \+ encodeURIComponent\(\(role && role\.role\) \|\| ""\)\}/g) || []).length === 2);
ok("...as an ANCHOR, not a NAV entry \u2014 /help/ is a separate document, not a React view, "
   + "so a 'help' id would fail the allowed-page check and bounce to the dashboard",
   !/\{\s*id:\s*"help"/.test(src) && /<a href=\{"\/help\//.test(src));
ok("...opening in a new tab, with rel=noopener, so the app's state is not lost",
   /\/help\/\?role=[\s\S]{0,120}target="_blank"/.test(src) && /\/help\/\?role=[\s\S]{0,140}rel="noopener/.test(src));

// ---- 2026-09-14: deep links. The guide links at a screen, so the URL names the page. ----
ok("\u2b50 the hash names the page, and the id list is DERIVED from NAV so the two cannot drift",
   /const PAGE_IDS = new Set\(NAV\.flatMap/.test(src) && /function pageFromHash\(\)/.test(src));
// ⚠️ 2026-09-15 — NARROWED, NOT DELETED (lesson 1). The hash gained an optional "/n"
// screen suffix, so the id check moved into hashParts(); it is still a PAGE_IDS check and
// an unknown id still yields null.
ok("...an unknown hash is ignored rather than blanking the app",
   /PAGE_IDS\.has\(id\) \? \{ page: id, rest \} : \{ page: null, rest: "" \}/.test(src)
   && /function pageFromHash\(\)\{ return hashParts\(\)\.page; \}/.test(src));
ok("...the hash wins over the remembered page on first load, and the remembered page is "
   + "still the fallback",
   /const h = pageFromHash\(\);\s*\n\s*if\(h\) return h;[\s\S]{0,160}localStorage\.getItem\("modus_page"\)/.test(src));
ok("\U0001f534 ...and it REPLACES rather than pushes \u2014 the rail is not browser history",
   /history\.replaceState/.test(src) && !/history\.pushState/.test(src));
ok("...a hashchange (a second link from the guide into the same tab) moves the page",
   /addEventListener\("hashchange"/.test(src) && /removeEventListener\("hashchange"/.test(src));

// ---- 2026-09-15: the big screen is four sections, three ways ------------------------
ok("0915: four sections, named, in the page's own order",
   /const DASH_SECTIONS = \[/.test(src)
   && ["today", "kpis", "charts", "stock"].every(k => new RegExp(`key: "${k}"`).test(src))
   && (src.match(/\{ key: "(?:today|kpis|charts|stock)",/g) || []).length === 4
   // 14 Oct 2026 (narrowed): a FIFTH, More charts, added LAST so #dashboard/1 … /4 keep their screens
   // 17 Oct 2026 (narrowed): a SIXTH, Simulation, added LAST after it, so #dashboard/1 … /5 keep their screens
   && /\{ key: "stock",  title: "Stockpiles" \},\n  \{ key: "more",   title: "More charts" \},\n  \/\/ 17 Oct 2026 \(the user\): the Simulation, added LAST[^\n]*\n  \{ key: "sim",    title: "Simulation" \},\n\];/.test(src));
ok("0915: every one of the six (14 Oct: five; 17 Oct: six) is wrapped, and each wraps a DIFFERENT index",
   (src.match(/<WallSection show=\{sectionShown\(/g) || []).length === 6
   && [0, 1, 2, 3, 4, 5].every(i => new RegExp(`sectionShown\\(${i}\\)`).test(src)));
ok("0915: 🔴 a hidden section is HIDDEN, not unmounted — the Mapbox instance survives",
   // the wrapper renders its children unconditionally and toggles `hidden`
   // (13 Oct 2026, W5: narrowed — the wrapper no longer needs a ref, it fires nothing)
   /<div hidden=\{!show\} data-wall-section/.test(src)
   && !/\{show && <DashboardToday/.test(src) && !/sectionShown\(0\) && </.test(src)
   // and [hidden] is forced in the STYLESHEET (not the script block), because a Tailwind
   // utility on the same element would otherwise win
   && /\[hidden\]\{display:none !important;\}/.test(html));
// 13 Oct 2026 (W5, bundle E): narrowed. The section is still re-measured when it comes back into view, but by the
// boxes themselves: every chart box and the Today map watch their own size (ResizeObserver), so nothing fires a window
// resize any more, and a chart that was never on screen is built then, at its real size.
ok("0915: ...and a section coming back into view is re-measured (13 Oct: each box watches its own size)",
   !/window\.dispatchEvent\(new Event\("resize"\)\)/.test(src)
   && /function ChartCanvas[\s\S]{0,2600}new ResizeObserver\(/.test(src)
   && /function CommitMap[\s\S]{0,9000}new ResizeObserver\(\(\) => \{ try \{ if\(mapDiv\.current && mapDiv\.current\.clientWidth > 0\) m\.resize\(\);/.test(src));
ok("0915: the WORKING view always shows all four, whatever the big screen remembered",
   /const sectionShown = \(i\) => !wall \|\| wallLayout === "all" \|\| wallSection === i;/.test(src));
// NARROWED 17 Oct 2026: a timeout per section instead of one interval, so each section has its own time on screen — the
// Simulation its whole day (SIM_WALL_SECONDS), the others the rotate setting
ok("0915: the rotate timer runs only on the big screen, and is cleared",
   /if\(!wall \|\| wallLayout !== "rotate"\) return;/.test(src)
   && /setTimeout\(\(\) => setWallSection\(s => \(s \+ 1\) % DASH_SECTIONS\.length\), dwellNow \* 1000\)/.test(src)
   && /return \(\) => clearTimeout\(id\);\n  \}, \[wall, wallLayout, rotateSecs, wallSection\]\);/.test(src)
   && src.includes('const dwellNow = (DASH_SECTIONS[wallSection] || {}).key === "sim" ? SIM_WALL_SECONDS : rotateSecs;'));
ok("0915: a screen can be pinned by URL, 1-based, and a bad number is ignored not clamped",
   /function screenFromHash\(max\)/.test(src)
   && /return \(n >= 1 && n <= max\) \? n : null;/.test(src)
   && /const pinned = screenFromHash\(DASH_SECTIONS\.length\);/.test(src));
ok("0915: ...and a pinned URL wins over what this browser remembered",
   /if\(pinned\) return "single";\s*\/\/ a pinned URL wins on first load/.test(src)
   && /if\(pinned\) return pinned - 1;/.test(src));
ok("0915: the three layouts are all offered, and every localStorage read is guarded",
   ['"all"', '"rotate"', '"single"'].every(v => src.includes(`pickLayout(${v.replace(/"/g, '"')})`) || src.includes(v))
   && (src.match(/localStorage\.(get|set)Item\("modus_dash_/g) || []).length === 6
   // every one of the six sits inside a try — a private window must not blank the page
   && !/[^ ]localStorage\.getItem\("modus_dash_[^)]*\)[^;]*;\s*\n(?![\s\S]{0,40}catch)/.test(src));
// 13 Oct 2026 (W5): narrowed — the rail's labels follow railShown (railOpen, or below 768 px the overlay)
ok("...and it collapses with the rail like every other item (label behind railShown)",
   /\/help\/\?role=[\s\S]{0,460}?\{railShown && <span className="truncate">User guide<\/span>\}/.test(src));

// ---- H10 (8 Oct 2026): the in-app guide ----------------------------------------
// Demo tenant only; steps per page anchored to data-guide elements; Back/Next/Done and
// "Don't show again"; the header replays it; localStorage in try/catch; no new library;
// the Mapbox iframe untouched. Copy from notes/landing-copy-v2-1008.md §5.
{
  const gs = src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/);
  ok("GUIDE_STEPS is declared", !!gs);
  const steps = gs ? gs[1] : "";
  for (const k of ["welcome", "dashboard", "submit", "forecasts", "lookahead", "data"])
    ok(`GUIDE_STEPS has steps for '${k}'`, new RegExp(`\\n  ${k}: `).test(steps));
  ok("the three data pages share one 'data' set (guidePageKey)",
     /const guidePageKey = \(page\) => DATA_PAGES\.includes\(page\) \? "data" : page;/.test(src));
  ok("Submit forecast and Forecasts share the forecast steps", /submit: GUIDE_FORECAST_STEPS,\n  forecasts: GUIDE_FORECAST_STEPS,/.test(steps));
  const anchors = [...new Set([...(gs ? gs[0] : "").matchAll(/anchor: "([a-z-]+)"/g), ...(src.match(/const GUIDE_FORECAST_STEPS = \[[\s\S]*?\];/) || [""])[0].matchAll(/anchor: "([a-z-]+)"/g)].map(m => m[1]))];
  ok("the steps name anchors", anchors.length >= 6, anchors.join(","));
  for (const a of anchors)
    ok(`⭐ every anchor a step names exists in the markup: data-guide="${a}"`, src.includes(`data-guide="${a}"`));
  ok("the page header is the universal anchor (every page renders one)", /<div className="flex flex-wrap items-start justify-between gap-3 mb-5" data-guide="page-header">/.test(src));
  ok("a missing or hidden anchor falls back to the page header, never to nothing",
     /if\(!el \|\| !\(el\.offsetWidth \|\| el\.offsetHeight\)\) el = document\.querySelector\('\[data-guide="page-header"\]'\);/.test(src));
  // NARROWED 14 Oct 2026 (D9): the signature gained `phone` (the phone's own steps and the tab bar as the "rail")
  const guideFn = (src.match(/function Guide\(\{ page, groups, phone \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
  ok("Guide is a component", guideFn.length > 500);
  ok("🔴 the guide shows ONLY on a demo tenant (TENANT.demo_notice), so a real client never sees it",
     /useEffect\(\(\) => \{\n    if\(!TENANT\.demo_notice\) return;/.test(guideFn));
  // 11 Oct 2026 NARROWED: with no tour running it renders only the hints (the strip and the dots), never a card
  ok("...and renders only the hints when there is no step (no card)", guideFn.includes("if(!step) return hintsEl;")
     && guideFn.includes("const hintsEl = (hints && !step) ? ("));
  ok("the welcome's menu line is built from the groups the ROLE can see (not from NAV)",
     guideFn.includes("(groups || []).map(g => `${g.group} (${g.items.map(it => it.label.toLowerCase()).join(\", \")})`)")
     // NARROWED 14 Oct 2026 (D9): + phone={narrow}; on a phone the welcome's second step names the tab bar instead
     && /<Guide page=\{page\} groups=\{visible\} phone=\{narrow\} \/>/.test(src)
     && guideFn.includes(': phone ? { ...s, title: "The tabs", body: "The tabs at the foot of the screen open the Dashboard, the Look-ahead and the Route map. More lists the pages made for a desktop." }'));
  ok("...and the welcome names the tenant, never a project", guideFn.includes("This is ${TENANT.name || \"the demo scheme\"}. Everything you see is invented") && !/Wolds Link/.test(src));
  ok("remembered per visitor under wayscope_guide_<page>", /const GUIDE_KEY = "wayscope_guide_";/.test(src));
  ok("every storage read and write is in try/catch (no storage → shows once per load)",
     /function guideRead\(k\)\{ try \{ return localStorage\.getItem\(GUIDE_KEY \+ k\); \} catch\(e\)\{ return null; \} \}/.test(src)
     && /function guideWrite\(k, v\)\{ try \{ localStorage\.setItem\(GUIDE_KEY \+ k, v\); \} catch\(e\)\{\} \}/.test(src)
     && !/localStorage\.(get|set)Item\(GUIDE_KEY/.test(guideFn));
  // 11 Oct 2026 NARROWED: the last button says "Got it" (Google's wording)
  ok("Back / Next / Got it and 'Don't show again'", />Back<\/button>/.test(guideFn) && />Next<\/button>/.test(guideFn)
     && />Got it<\/button>/.test(guideFn) && />Don't show again<\/button>/.test(guideFn));
  ok("Done marks the page (and the welcome) seen; 'Don't show again' switches every page off",
     guideFn.includes('guideWrite(key, "done"); guideWrite("welcome", "done");') && guideFn.includes('guideWrite("all", "off");'));
  // NARROWED 11 Oct 2026 (the demo bar): the Guide button left the header for the demo bar under it, which shows
  // exactly when the header's did (a demo tenant); on a Portal page it still replays through the one event name
  ok("the demo bar has the Guide button, demo tenant only, that replays the app's guide through one event name",
     /function replayAppGuide\(\)\{ window\.dispatchEvent\(new Event\(GUIDE_EVENT\)\); \}/.test(src)
     && /: onMap \? \(mapTour \? startMapTour : null\) : replayAppGuide;/.test(src)
     && /function DemoBar\(\{ onGuide \}\)\{\n  if\(!TENANT\.demo_notice\) return null;/.test(src)
     && guideFn.includes("window.addEventListener(GUIDE_EVENT, on)") && /const GUIDE_EVENT = "wayscope-guide";/.test(src));
  ok("🔴 the guide never renders a team id: no IPT in its copy", !/IPT/.test(gs ? gs[0] : "x"));
  ok("🔴 no 'truck' in its copy (UK: lorry / HGV)", !/truck/i.test(gs ? gs[0] : "x"));
  ok("🔴 no new script tag: the guide is in-page (six script src tags, as before)", (html.match(/<script src=/g) || []).length === 6);
  ok("🔴 the route map stays an iframe of /map/ — the staff app never mounts Mapbox for it",
     /<iframe src=\{MAP_URL\} title="Public Route Map" className="w-full h-full border-0" \/>/.test(src)
     && !/new mapboxgl\.Map\(/.test(guideFn));
  ok("the anchor is scrolled into view before measuring, and the card is clamped into the window",
     guideFn.includes('el.scrollIntoView({ block: "nearest" })') && guideFn.includes("top = Math.min(Math.max(12, top), Math.max(12, vh - 232));"));
  ok("a tall anchor (the rail) gets the card BESIDE it, never on top of it",
     guideFn.includes("if(box.height > vh * 0.5 && box.left + box.width + W + 24 <= vw){") && guideFn.includes("left = box.left + box.width + 12; top = Math.max(12, box.top + 12);"));
  ok("the card and ring are fixed overlays with their own z-index (nothing in the page is re-laid-out)",
     /\.guide-ring\{position:fixed;z-index:9000;pointer-events:none;/.test(html) && /\.guide-card\{position:fixed;z-index:9001;/.test(html));
}

// ---- 9 Oct 2026: UK wording in the staff app's own copy ------------------------------
// The Dashboard figure said 'truck-mi', the Routes table 'Truck-mi', the bake table 'Truck
// params', and two tooltips 'truck'. Vehicle NAMES ('Truck mixer 8 m³') come from the tenant's
// factors and are not this file's copy; identifiers (truck_params_present) and comments are not copy.
{
  const strings = (src.match(/'[^'\r\n]*'|"[^"\r\n]*"|`[^`\r\n]*`/g) || []);   // single-line literals only: a span across lines would swallow JSX comments
  const jsxText = (src.match(/>[^<>{}]*truck[^<>{}]*</gi) || []);
  const trucks = strings.filter(s => /\btrucks?\b/i.test(s) && !/Truck mixer/.test(s)).concat(jsxText);
  ok("🔴 no 'truck' in any string or JSX text the staff app prints (lorry / HGV)", trucks.length === 0, trucks.slice(0, 3).join(" | "));
  // 13 Oct 2026 (W3, narrowed): the carbon sentence moved from the tooltip to the info box (source line) and the technical guide
  ok("the carbon info box and the Config sub-line say DESNZ 2026, not DEFRA (checked against gov.uk 9 Oct 2026)",
     !/DEFRA/.test(src) && src.includes('source: "DESNZ greenhouse gas conversion factors, 2026"')
     && /DESNZ 2026 kg CO₂e per vehicle-km \(average laden, both legs, from Config\)/.test(_tg));
  ok("the Dashboard figure and the Routes table say lorry-<unit>, the bake table says HGV params",
     // 13 Oct 2026 (W6, narrowed): the route table's lorry-distance is a details line and a "Sort by" choice
     /label=\{`lorry-\$\{DU\(\)\}`\}/.test(src) && src.includes('<RdItem t={`Lorry-${DU()}`}>{r.baked ? grp(dist(r.km))') && src.includes('["km", `Lorry-${DU()}`]') && />HGV params<\/th>/.test(src));
}

// ---- 10 Oct 2026: the Carbon planner page (phase 3) ------------------------------
// One read (POST /api/carbon/scenario), no carbon arithmetic in the browser, distances in the
// tenant's unit, every factor's source / year / status on hover, the Planned panel and the
// known limits on screen, and none of the words a public stand must not use.
{
  const s0 = src.indexOf("// ================================================================= Carbon planner (10 Oct 2026)");
  const s1 = src.indexOf("// ================================================================= Look-ahead v2 (2026-09-09)");
  const cbSrc = s0 > 0 && s1 > s0 ? src.slice(s0, s1) : "";
  const cb = cbSrc.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  ok("⭐ the Carbon planner is a Plan-group page after Forecasts (not admin-gated: a team code sees its own lines)",
     /\{ id: "forecasts", label: "Forecasts", glyph: "☰" \},\n    \{ id: "carbon", label: "Carbon planner", glyph: "◐" \},\n  \]\},/.test(code)
     && !/group: "Plan", admin/.test(code));
  // NARROWED 11 Oct 2026 (the process layout: the page switch also hands the Carbon page the typed sign-in name, the "set by" of a target)
  // NARROWED 14 Oct 2026 (D9): on a desktop only (on a phone the Carbon planner is the desk-only card)
  ok("...and the page switch renders CarbonPage", /page === "carbon" && !narrow && <CarbonPage meta=\{meta\} access=\{role\} who=\{who\} \/>/.test(code));
  // NARROWED 11 Oct 2026 (after the show, item 11): + the one summary download, which the server draws from the same read
  // NARROWED 11 Oct 2026 (the process layout, step 6): + ONE call to /api/carbon/target, whose three verbs (GET, PUT, DELETE)
  // go through one helper; the scenario is still the page's only read of carbon figures
  ok("🔴 ONE read: POST /api/carbon/scenario, and no other fetch on the page but the summary PDF download and the target's one call",
     cb.length > 5000 && (cb.match(/fetch\(/g) || []).length === 3 && cb.includes('fetch(`${API}/carbon/scenario`, { method: "POST"')
     && cb.includes('fetch(`${API}/carbon/summary.pdf`, { method: "POST"')
     && cb.includes('fetch(`${API}/carbon/target`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })'));
  ok("🔴 no carbon arithmetic in the browser: no emission key, no factor literal, no km/mile constant",
     !/emissions_kg_co2e_per_km|kwh_per_km \*|0\.93939|0\.99773|7\.80307|0\.14395|0\.13096|1\.609344|19\.55376/.test(cb));
  ok("distances and per-distance figures go through the tenant's unit (fmtDist, distRate, DU, TKM)",
     cb.includes("fmtDist(") && cb.includes("distRate(") && cb.includes("DU()") && cb.includes("TKM()"));
  ok("⭐ it says what it is not: a National Highways Carbon Tool return", cb.includes("not a National Highways Carbon Tool return"));
  // NARROWED 11 Oct 2026 (plain-English pass, notes/carbon-ui-1011): the same five sections, in the new words
  ok("⭐ the ranked list, the three methods side by side, the fleet comparison, the not-built panel and the limits",
     ["Which decisions change carbon most", "Three ways to count the same haul", "Diesel or battery electric, same tonnage",
      "Not built yet", "Known limits", "No figures are shown for these until each exists."].every(t => cb.includes(t)));
  ok("⭐ every factor's source, year and status on hover (title={prov(…)}) and as a status chip",
     (cb.match(/title=\{prov\(/g) || []).length >= 5 && cb.includes("<Chip s={f.status} />") && cb.includes("Factors used: source, year and status")
     && /const CARBON_TONE = \{ VERIFIED: [^}]*DERIVED: [^}]*ASSUMPTION: /.test(code));
  ok("the alternative's levers cover all seven drivers the brief names",
     ["recycled", "material", "vehicle", "fuel", "source", "route", "disposal"].every(d => cb.includes(`driver: "${d}"`)));
  ok("the recycled slider is disabled with the server's reason where the Government file has no closed-loop or primary row",
     cb.includes("disabled={!m.recycled_enabled || !!e.kg}") && cb.includes("Not available: {m.recycled_reason}."));
  ok("an EPD needs its reference (the field says so; the server refuses it otherwise)", cb.includes("EPD reference (required)"));
  // NARROWED 11 Oct 2026: "route distance", the Routes page's Bake named as the action
  // NARROWED 11 Oct 2026 (the process layout: the header's line moved into step 1, as the first of the server-counted
  // left-out lines, in the words of the "Left out here" list)
  ok("the unbaked lines are named, never estimated",
     // 13 Oct 2026 (W3, narrowed): plain words
     cb.includes('unrouted > 0 ? `${unrouted} plan line${unrouted === 1 ? " has" : "s have"} no route distance yet: transport not counted (route it on Data → Routes)` : ""')
     && cb.includes("const unrouted = (B.totals.lines || 0) - (B.totals.baked_lines || 0);")
     && cb.includes('{leftOut.length > 0 && <p className="text-sm text-amber-700 mt-2">{leftOut[0]}'));
  ok("🔴 the electric figures carry their basis: no Government electric HGV factor; the +2 t allowance is draft, not applied",
     cb.includes("no Government electric HGV factor exists") && cb.includes("is a draft rule and is not applied")
     && cb.includes("kWh per km × UK electricity") && !cb.includes("kWh per {DU()}") && cb.includes("Where Config has an electric profile for that lorry"));
  const cbStrings = (cb.match(/'[^'\n]*'|"[^"\n]*"|`[^`\n]*`/g) || []).concat(cb.match(/>[^<>{}]+</g) || []);
  const banned = (x) => /\b(compliant|secure|NH-approved|real-time|predict\w*|optimi[sz]\w*|trucks?)\b/i.test(x) || /\bAI\b/.test(x);
  ok("🔴 none of the banned words on the page: compliant, secure, NH-approved, real-time, AI, predict, optimise, truck",
     cbStrings.length > 50 && !cbStrings.some(banned), cbStrings.filter(banned).join(" | "));
  ok("🔴 no team id reaches the page (it never reads .ipt)", !cb.includes(".ipt"));
  ok("the scenario-only profiles (electric variants) never reach a forecast picker",
     code.includes("Object.entries((m && m.vehicle_details) || {}).forEach(([k, v]) => { if(v && v.scenario_only && !HIDDEN_VEHICLES.includes(k)) HIDDEN_VEHICLES.push(k); });"));
  ok("Config → Vehicles says an electric profile's kg CO₂e/km is derived", code.includes('placeholder={v.fuel === "electric" ? "derived: kWh × UK grid" : ""}'));
  ok("review (11 Oct): every flag the engine can raise reads in words — including the stand-in return, the unbaked swap and the missing disposal factor",
     ["UNBAKED", "KM_FROM_BASELINE_VEHICLE", "KM_SCALED", "ALT_ROUTE_NOT_BAKED", "EV_TRIP_EXCEEDS_BATTERY", "RETURN_NOT_BAKED",
      "RETURN_STAND_IN", "ROUTE_SWAP_NOT_BAKED", "NO_DISPOSAL_FACTOR"].every(k => new RegExp(`\\b${k}: "`).test(code))
     && code.includes("left out, not counted as zero"));
  ok("review: a supplier or destination that is not baked is offered but cannot be picked", (cb.match(/disabled=\{!(s|x)\.baked\}/g) || []).length === 2
     && (cb.match(/" — no route distance yet"/g) || []).length === 2);
  ok("review: the disposal choice lists only the routes the Government file publishes for the material", cb.includes("(r.disposal_routes || []).map(k =>")
     && !cb.includes('<option value="open_loop">'));
  ok("review: the electric range is the range on ONE charge, and an impossible trip is left out of both columns",
     cb.includes("Range on one charge") && cb.includes("fc.range_per_charge_km_min") && !cb.includes("daily_range") && cb.includes("left out of both columns"));
  ok("review: the benchmarks say how many line-months they leave out", cb.includes("bm(B).excluded_lines"));
  ok("after the UI pass (11 Oct): the Carbon page keeps the 14 px floor (13 px allowance; no 9, 10 or 11 px text) and no dashed border",
     !/text-\[(9|10|11)px\]/.test(cb) && !cb.includes("border-dashed"));
  ok("after the UI pass (11 Oct): the Carbon planner has its own rail icon, the Plan kicker, and the error kind of the empty state",
     /\n  carbon: "M/.test(code) && (cb.match(/<PageHeader title="Carbon planner" kicker="Plan"/g) || []).length === 2
     && cb.includes('<EmptyState kind="error" title="Couldn\'t compute the carbon scenario"'));
  // 11 Oct 2026 — the plain-English pass (notes/carbon-ui-1011, every item checked against its source)
  // NARROWED 11 Oct 2026 (the process layout: the "Approved plan" card is now step 1, "Your approved plan", from the step titles)
  ok("plain English: 'Approved plan', never 'Baseline' (National Highways uses baseline for its 2019/20 year)",
     cb.includes('const CARBON_STEP_TITLES = ["Your approved plan", ') && cb.includes('<CarbonStep n={1} data-guide="carbon-compare">') && !/\bBaseline\b/.test(cb)
     && cb.includes("than the approved plan (${pct(A.delta_pct)})") && !src.includes("What moves carbon most"));
  ok("plain English: a change is said in words ('tCO2e lower' / 'higher' / 'no change'), never by colour alone",
     cb.includes("tCO2e lower`") && cb.includes("tCO2e higher`") && cb.includes('"no change"') && cb.includes('<b style={{ color: tone(d.delta_t) }}>{moved(d.delta_t)}</b>'));
  ok("plain English: tCO2e and CO2e with a normal 2, % with no space, empty cells say what they mean",
     !cb.includes("CO₂e") && !/\} %/.test(cb) && cb.includes('"no data"') && cb.includes('>not applicable<') && cb.includes('"no alternative yet"'));
  ok("plain English: sentence-case headings, no 12 px text and no capitals for emphasis on the page",
     !cb.includes("uppercase") && !cb.includes("text-xs") && !/text-\[(9|10|11|12)px\]/.test(cb) && cb.includes('const h3 = "text-base font-semibold text-slate-800";'));
  ok("the warning line says what the page is not, before anything else", cb.includes('role="note"')
     && cb.includes("<strong className=\"text-base text-slate-800\">Planning estimates. Not a National Highways Carbon Tool return.</strong>"));
  // REVERSED 11 Oct 2026 (the user: "make it like a process, with a final target at the end": the six steps run top to
  // bottom on every screen, so the answer no longer jumps above the controls on a phone; a strip at the foot keeps it in view)
  // NARROWED 11 Oct 2026 (the review: the Guide's strip covered it): the strip at the foot carries data-sticky-foot, which the
  // Guide measures to lift its own strip above it
  ok("on a phone the steps run in order (the answer is not moved above the controls) and a strip at the foot keeps the result in view",
     !/\border-[12]\b|\blg:order-/.test(cb) && cb.includes('<div className="sticky bottom-0 z-10 mt-4" data-sticky-foot="">')
     && cb.includes('<button type="button" className="link-btn" onClick={toResult}>See step 5</button>')
     && cb.includes('document.getElementById("carbon-step-5")'));
  ok("lorry loads beside the carbon on both cards, the change in loads from the server (no subtraction in the browser)",
     cb.includes("Lorry loads (deliveries):") && cb.includes("lorries needed in the busiest month:") && cb.includes("A.delta_trips")
     && !/fleet\.trips\s*-/.test(cb) && cb.includes("more lorry loads, because each lorry carries less") && !/two-way/i.test(cb));
  ok("the total visibly adds up, and says it is rounded", cb.includes("Material {t1(sc.totals.material_t)} + Transport {t1(sc.totals.transport_t)} + Waste disposal {t1(sc.totals.disposal_t)}")
     && cb.includes("Figures are rounded, so the parts may not add exactly to the total"));
  ok("the controls speak NH, CLOCS and EA words, each with one hint",
     ["Vehicle choice", "Haul distance: ", "Below 100% is a nearer supplier, above is farther", "Custom carbon factor (supplier EPD), kgCO2e per tonne",
      "Receiving site", "Disposal method", "Battery electric lorries", "Reused material", "Programme spend, in {CUR()} million (optional)"].every(t => cb.includes(t))
     && !cb.includes("Source distance") && !cb.includes("Send instead to"));
  ok("🔴 the NH intensity is the restated 159 → 181 (2023 prices), read from its own key, and called context only",
     cb.includes("const nhKpi = bm(B).nh_kpi || null;") && cb.includes("Context only: this page counts materials, haulage and waste disposal, not the same scope.")
     && !cb.includes("nh_kpi_t_co2e_per_gbp_m") && !cb.includes("2023_24"));
  ok("the methods are named in full: 'National Highways Carbon Tool method (for comparison)'; laden share says how it is counted",
     cb.includes("National Highways Carbon Tool method (for comparison)") && cb.includes("Wayscope: per vehicle-km, both legs")
     && cb.includes("Every return leg is counted empty: back-loads are not modelled") && !cb.includes("Laden share of km"));
  // NARROWED 11 Oct 2026 (the process layout: the "By material" table became step 2's one row per category, with the NH
  // category on the name's hover; three tables remain, each inside a closed details)
  // NARROWED 17 Oct 2026 (UI audit #15, claude/ui-fix-keyboard): the two step-5 reference tables wrap their cells (tbl-wrap)
  ok("the tables use the app's .tbl style with a caption, and the NH category takes NH's own name for waste",
     (cb.match(/<table className="tbl(?: tbl-wrap)?">/g) || []).length === 3 && (cb.match(/<table className="tbl tbl-wrap">/g) || []).length === 2
     && (cb.match(/<table\b/g) || []).length === 3 && (cb.match(/<caption><b>/g) || []).length === 3
     && cb.includes('"Waste": "Waste + Waste Transport"')
     && cb.includes('title={`National Highways Carbon Tool category: ${bc ? (CARBON_NH_CATEGORY[bc.sheet] || bc.sheet || "no category") : "no category"}`}'));
  // after the show (11 Oct 2026, notes/carbon-ui-1011 items 8, 9, 11–15): every figure from the server
  // NARROWED 11 Oct 2026 (the process layout: "What this page counts" is now "What this counts", a closed details in step 1,
  // still above the result in step 5)
  ok("item 8 'What this page counts' sits above the answer, in the server's words, with what is left out from the server's counts",
     cb.includes('<details className="dash-more mt-3" data-guide="carbon-counts">') && cb.includes("<summary>What this counts</summary>") && cb.includes("const sw = data.scope_words || {};")
     && ["{sw.counts", "{sw.not_counted", "{sw.factors"].every(t => cb.includes(t)) && cb.includes("Nothing: every plan line is counted in full.")
     && cb.indexOf('data-guide="carbon-counts"') > cb.indexOf("<CarbonStep n={1}") && cb.indexOf('data-guide="carbon-counts"') < cb.indexOf("<CarbonStep n={2}")
     && cb.indexOf('data-guide="carbon-counts"') < cb.indexOf("<CarbonStep n={5}")
     && ["B.totals.material_excluded_tonnes", "fl0.RETURN_NOT_BAKED", "fl0.NO_DISPOSAL_FACTOR", "B.totals.wtw_lines_out"].every(t => cb.includes(t)));
  ok("item 9 each decision's lorry effect from the server (delta_trips, delta_vkm_km), the distance in the tenant's unit",
     cb.includes("const lorryEffect = (d) => [loadsWord(d.delta_trips), kmWord(d.delta_vkm_km)]") && cb.includes("dist(km)") && cb.includes("lorry-${DU()}")
     && cb.includes("<div className={hint + \" tabular-nums\"}>{lorryEffect(d)}</div>") && cb.includes("kmWord(A.delta_vkm_km)") && !/vkm\s*-/.test(cb));
  ok("item 11 the summary: one POST with the page's own body and the commentary, typed but never saved, stamped",
     cb.includes('data-guide="carbon-summary"') && cb.includes("commentary: note || null") && cb.includes("maxLength={1500}")
     && cb.includes("Printed on the summary as typed; not saved") && cb.includes("Download the summary (PDF)")
     && cb.includes("Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures") && !/localStorage/.test(cb));
  {
    const _mn = fs.readFileSync(path.join(ROOT, "backend", "main.py"), "utf8");
    ok("...the page's 1,500-character limit is the server's", /CARBON_COMMENTARY_MAX = 1500\b/.test(_mn));
  }
  ok("item 12 well-to-wheel beside the total on both cards and in the methods table, FORS's rule said as FORS says it",
     cb.includes("Transport well-to-wheel: {t1(sc.totals.transport_wtw_t)} tCO2e") && cb.includes("beside the total, not in it")
     && cb.includes("Wayscope, well-to-wheel (adds producing the fuel or electricity)")
     && cb.includes("FORS Silver and Gold require operators to report well-to-wheel; Bronze recommends it")
     && !cb.includes("this page does not show that figure yet") && cb.includes("{altCell(a => t1(a.totals.transport_wtw_t))}"));
  ok("item 13 the waste hierarchy step from the server on every disposal option, and the transfer-note line",
     cb.includes("const step = (k) => ((data.waste_hierarchy || {})[k] || \"\");") && cb.includes("{dispWord(k)}")
     && cb.includes("dispWord(x.disposal_route)") && cb.includes("waste transfer note (or a season ticket covering a series of transfers)")
     && cb.includes("Wayscope does not replace these or the duty of care") && cb.includes("title={data.waste_hierarchy_source"));
  ok("item 14 the life-cycle modules as a secondary line (hint size), named for BS EN 15804, from the server's stages",
     cb.includes("By life-cycle module: A1–A3 {t1((sc.stages || {})[\"A1-A3\"])} · A4 {t1((sc.stages || {}).A4)} · A5 {t1((sc.stages || {}).A5)}")
     && cb.includes("Life-cycle modules as BS EN 15804 names them"));
  // REVERSED 11 Oct 2026 (the review: "Buyer" is not one of CLOCS's roles — client, principal contractor, site operator, fleet
  // operator, notes/carbon-ui-research-1011.md — so the page no longer says "Roles as CLOCS names them"; and the client
  // agrees the target while a planner records it, as step 6 and the Dashboard say)
  ok("item 15 'Using these results': three steps, each saying who acts, never attributed to CLOCS; not a record of delivery",
     cb.includes('data-guide="carbon-using"') && ["{ who: \"Client\"", "{ who: \"Buyer\"", "{ who: \"Principal contractor\""].every(t => cb.includes(t))
     && !cb.includes("as CLOCS names them") && cb.includes("Agrees the carbon target for the scheme (a planner records it in step 6)")
     && !cb.includes("Sets the carbon target for the scheme") && cb.includes("they are not a record of what was delivered")
     && !/meets? CLOCS|CLOCS[- ]compliant|complies/i.test(cb));
  const gs2 = (src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1];
  ok("the guide has steps for the Carbon page, on its own anchors", /\n  carbon: \[/.test(gs2)
     && ["carbon-compare", "carbon-levers", "carbon-drivers"].every(a => gs2.includes(`anchor: "${a}"`) && src.includes(`data-guide="${a}"`)));

  // ---- 11 Oct 2026: the Carbon page as a process ending in the target (six steps; step 6 reads and sets it) --------
  // Source-level. What they prove: the six steps in order, top to bottom; the guide on the same six anchors; the
  // explanations in closed <details>; the target read and written only through /api/carbon/target with no figure in
  // the body (the server works every number out); planner or admin only; the hooks before the early returns; and
  // the merge's one way of saying a gap and a team across the four pages. Not covered here: the rendered states
  // (render_frontend.js). Not covered anywhere: the PUT / DELETE round trip from a browser, confirm(),
  // scrollIntoView and the sticky strip's look.
  const _cp = cb.slice(cb.indexOf("function CarbonPage("));
  ok("⭐ PROCESS: six numbered steps, in order, top to bottom: approved plan, materials, lorries and routes, surplus material, result, carbon target",
     cb.includes('const CARBON_STEP_TITLES = ["Your approved plan", "Materials", "Lorries and routes", "Surplus material", "Result", "Carbon target"];')
     && [1, 2, 3, 4, 5, 6].every(n => _cp.indexOf(`<CarbonStep n={${n}}`) > 0 && (n === 1 || _cp.indexOf(`<CarbonStep n={${n - 1}}`) < _cp.indexOf(`<CarbonStep n={${n}}`)))
     && (_cp.match(/<CarbonStep n=\{/g) || []).length === 6 && _cp.includes('<ol className="space-y-4" aria-label="The six steps">'));
  ok("...the step card is top level, never defined inside CarbonPage (inputs keep their focus, a details keeps its open state)",
     cb.indexOf("function CarbonStep(") > 0 && cb.indexOf("function CarbonStep(") < cb.indexOf("function CarbonPage(")
     && !/function CarbonStep\(|const CarbonStep =/.test(_cp));
  ok("...each step is a section named by its number and heading",
     cb.includes('aria-labelledby={"carbon-step-" + n + "-h"}') && cb.includes("<span>{CARBON_STEP_TITLES[n - 1]}</span>"));
  const gsC = (gs2.match(/\n  carbon: \[([\s\S]*?)\n  \],/) || ["", ""])[1];
  ok("⭐ the guide walks the same six steps, each on an anchor the page carries",
     (gsC.match(/anchor: "/g) || []).length === 6
     && ["carbon-compare", "carbon-levers", "carbon-lorries", "carbon-surplus", "carbon-drivers", "carbon-target"].every((a, i) =>
        gsC.includes(`anchor: "${a}", title: "${i + 1}. `) && _cp.includes(`<CarbonStep n={${i + 1}} data-guide="${a}">`)));
  ok("every explanation, table and list sits in a native details, closed (it stays in the markup the render harness reads)",
     (_cp.match(/<details className="dash-more/g) || []).length >= 10 && !/<details[^>]*\bopen\b/.test(_cp)
     && ["What this counts", "Use a supplier EPD", "Supplier and route, route by route", "Diesel or battery electric, same tonnage", "Transfer notes",
         "The result in full", "How the plan compares", "Three ways to count the same haul", "Add a commentary (optional)", "About these figures"].every(t => _cp.includes(`<summary>${t}`)));
  ok("🔴 step 6: the target goes only through /api/carbon/target; Set sends the decisions, the mode, the page state and the typed name, never a figure",
     cb.includes('targetCall("PUT", { mode, levers, ui_state: st, updated_by: who || null }, "Target set.")')
     && cb.includes('targetCall("PUT", { mode: k, updated_by: who || null }')
     && cb.includes('targetCall("DELETE", null, "Target cleared.")') && cb.includes('targetCall("GET", null, null)')
     // NARROWED 11 Oct 2026 (the review: a failed read left no way back but a reload): 4 → 5, the fifth is "Try again", a GET
     && (cb.match(/targetCall\("/g) || []).length === 5 && cb.includes('onClick={() => targetCall("GET", null, null)}>Try again</button>')
     && !/\b(target_t|cap_t|pct_below|approved_t|with_decisions_t)\s*:/.test(cb));
  ok("...a planner or admin code sets, switches or clears it; any other code reads it and is told who sets it",
     cb.includes("const canSet = !!(access && access.can_approve);") && cb.includes("{canSet ? (")
     // NARROWED 11 Oct 2026 (the review: one click rewrote the saved target): switching a saved target asks first
     && cb.includes("Your planner sets the scheme's carbon target.") && cb.includes("if(canSet && T.mode !== k && confirm(k === \"cap\"")
     && cb.includes("Every page shows the change.") && cb.includes("Switching it changes the saved target; you are asked first."));
  ok("...the two ways a target is held are the server's own words (carbon_target.MODE_WORDS), the picked one ticked as well as filled",
     cb.includes('const CARBON_TARGET_MODES = [["pct", "% below the approved plan"], ["cap", "Fixed tCO2e cap"]];')
     && /MODE_WORDS = \{"pct": "% below the approved plan", "cap": "Fixed tCO2e cap"\}/.test(fs.readFileSync(path.join(ROOT, "backend", "carbon_target.py"), "utf8"))
     && cb.includes("aria-pressed={mode === k}") && cb.includes('{mode === k ? "✓ " : ""}{w}'));
  ok("...Set waits for a choice that lowers carbon and says why when it cannot; replacing or clearing asks first",
     cb.includes('"Make a choice in steps 2 to 4 first."') && cb.includes('"These decisions do not lower carbon, so they cannot be the target."')
     && cb.includes("disabled={!!setWhy || tBusy}") && cb.includes(`confirm("Replace the scheme's carbon target with these decisions?")`)
     && cb.includes(`confirm("Clear the scheme's carbon target?")`));
  ok("...a refusal reads as a sentence: the server's own words for a 400, plain words for 401, 403 and anything else",
     cb.includes('if(status === 401) return "Sign in again to see the carbon target.";') && cb.includes('if(status === 403) return "Only a planner or admin code can change the carbon target.";')
     && cb.includes('typeof j.detail === "string"') && cb.includes('role="alert"'));
  ok("...the stored page state comes back into the controls only key by key (an object stays an object, electric a yes or no)",
     cb.includes("function carbonStateFrom(u){") && cb.includes('if(k === "electric") o[k] = !!v;') && cb.includes("setSt(carbonStateFrom(T.ui_state))"));
  ok("🔴 the new hooks sit before the page's early returns (React #310 blanked the app on 5 Oct)",
     _cp.indexOf("const [tg, setTg]") > 0 && _cp.indexOf("const alive = useRef(true);") > 0 && _cp.indexOf('targetCall("GET", null, null)') > 0
     && Math.max(_cp.indexOf("const [tg, setTg]"), _cp.indexOf("const alive = useRef(true);"), _cp.indexOf('targetCall("GET", null, null)')) < _cp.indexOf("if(!data && err) return"));
  // REVERSED 11 Oct 2026 (R2, one "on target" rule decided on the server): step 6 no longer works out a tolerance of its own
  // (it gave a cap no band while the Dashboard gave it 0.05% of the plan, so a 2.0 t gap read "on target" on one page and
  // "over" on the other). It now says the server's verdict in the shared words.
  ok("...step 6 compares nothing: no tolerance, no gap word of its own; the server's verdicts in the shared words (ctTargetLine, ctProgress)",
     !cb.includes("const tol =") && !cb.includes("gapWord") && !cb.includes("targetWords") && !/\* ?0\.0005/.test(cb)
     && cb.includes("const p6 = ctHere ? ctProgress(tg) : [];") && cb.includes("{ctTargetLine(tg)}") && cb.includes("{p6[0]}") && cb.includes("{p6[1]}")
     && !/S\.\w+_t\s*[-+*/]\s*S\./.test(cb));
  // 11 Oct 2026 (the review, low): the old guard only caught S-to-S arithmetic; this is the surfaces' guard, both ways round
  ok("🔴 ...and no carbon arithmetic anywhere on the page: no _t field added, taken, multiplied or divided, either way round",
     !/_t\s*[-+*/]\s*[\w(+]/.test(cb) && !/[-+*/]\s*(?:A|B|S|T|a|d|sc|e|s|c|t)\.[\w.]*_t\b/.test(cb));
  // NARROWED 11 Oct 2026 (the review: "one way of saying the target" was not one way): the page no longer builds its own target
  // sentence or gap words (it said "which is X today", "a fixed cap of", "N tCO2e over"; the Dashboard "= X", "X cap", "N over");
  // every page uses the same helpers, and a team code is told the target is the whole scheme's, not split by team
  ok("🔴 the merge: the Carbon page says the target and a gap with the other three pages' own helpers, and a team in the tenant's word",
     code.includes("tCO2e ${gap > 0 ? \"over\" : \"under\"} the target`") && !cb.includes("below the target") && !/your team's lines|per team\)/.test(cb)
     && !cb.includes("; on ${ctYour()} that is ") && !cb.includes("(a cap has no share per") && cb.includes("{ctScopeNote(tg)}")
     && code.includes('${gap > 0 ? "over" : "under"} the target'));
  ok("⭐ R3: 'Open the agreed decisions' is an approver's control only, and does nothing without a stored page state",
     cb.indexOf(">Open the agreed decisions</button>") > cb.indexOf("{canSet ? (") && cb.indexOf(">Open the agreed decisions</button>") < cb.indexOf("Your planner sets the scheme's carbon target.")
     && cb.includes("const openAgreed = () => { if(!canSet || !T || !T.ui_state) return; setSt(carbonStateFrom(T.ui_state));"));
  ok("...the agreed decisions are listed in step 6 to a scheme code only, as on the Dashboard",
     cb.includes("{!team && (T.lever_words || []).length > 0 && ("));
  ok("⭐ a failed read of the target: Set waits (it cannot know there is a target to replace), says why, and offers Try again",
     cb.includes("const setWhy = !tLoaded ? (tErr ? \"The scheme's current carbon target did not load, so a new one cannot be set yet.\" : \"Reading the current carbon target…\")")
     && cb.includes("const setTarget = () => {\n    if(!tLoaded) return;") && cb.includes("{!tLoaded && tErr && <button"));
  ok("⭐ a refused scenario: step 5, the strip at the foot and Set's reason all say 'Not updated' with the server's sentence; the old figures are called the previous choices",
     cb.includes(": err ? `Not updated: ${err}`") && cb.includes("Not updated: {err}{A ? \" The figures below are from your previous choices.\" : \"\"}")
     && cb.includes("{(A || err) && (") && cb.includes('<span role="alert" style={{ color: "var(--red)" }}>Not updated: {err}</span>')
     && cb.includes("err ? null : <p className=\"text-sm text-slate-600 mt-2\">Make a choice in steps 2 to 4 to see the result."));
  ok("...the summary's failure sits under its own button (pdfErr), never in the scenario's error; its hook is with the others",
     cb.includes("} catch(e){ setPdfErr(\"The summary could not be made: \" + (e.message || e)); }") && !cb.includes("setErr(\"The summary could not be made")
     && cb.includes("{pdfErr && <p") && _cp.indexOf("const [pdfErr, setPdfErr] = useState(null);") > 0
     && _cp.indexOf("const [pdfErr, setPdfErr] = useState(null);") < _cp.indexOf("if(!data && err) return"));
  ok("...an EPD says what it needs beside its fields, and an EPD in use is said beside the controls it switches off",
     cb.includes("Add the EPD reference: the result does not update until it has one.") && cb.includes("Type a number, with a point for decimals (for example 12.5).")
     && cb.includes("so recycled content and reuse do not apply (change it under Use a supplier EPD)."));
  ok("...Start again also clears step 6's last message; the route details count the choices made inside them; Set wraps on a phone",
     cb.includes('setSt(CARBON_EMPTY); setSpend(""); setTMsg(null);') && cb.includes("{chosenN ? ` · ${chosenN} chosen` : \"\"}")
     && cb.includes('<button type="button" className="btn-pri" style={{ whiteSpace: "normal" }} disabled={!!setWhy || tBusy} onClick={setTarget}>'));
  ok("...the date of a target is the reader's own day on every page (one helper, ctWhen), never toLocaleDateString's month words",
     cb.includes("ctWhen(T.updated_at)") && !cb.includes("toLocaleDateString") && code.includes("function ctWhen(at){"));
}

// ---- 10 Oct 2026: the UI pass (notes/ui-review-1009, mockups 1-6, 8 and 8b; colour-system-1010.md) ----
// Source-level, like everything above. What they prove: the tokens exist in both looks, the charts read
// the palette in fixed order and carry no raw hex, the shell is neutral (ink active rail item), the shared
// components exist and are used, the tables are 14 px in 40 / 32 px rows with a caption, and the four
// rebuilt pages carry no 9-11 px product text. Not covered: anything visual (no browser here).
{
  // (code has its comments stripped, so the slices end on the next function, never on a comment marker)
  const _fcBody = code.slice(code.indexOf("function Forecasts("), code.indexOf("function CostingTab("));
  const _cfBody = code.slice(code.indexOf("function ConfigPage("), code.indexOf("const dayName = (iso) => [", code.indexOf("function ConfigPage(")));
  const _dbWork = _dbBody.slice(_dbBody.indexOf("{!wall ? ("), _dbBody.indexOf("      ) : (\n        <>\n"));
  const _dbWall = _dbBody.slice(_dbBody.indexOf("      ) : (\n        <>\n"));
  // 13 Oct 2026 (W6, narrowed): the grid now holds a small by-day table in each details row, so the slice ends at the
  // </table> after the totals row, not the first one
  const _laGrid = _laBody.slice(_laBody.indexOf('<table className="tbl compact'), _laBody.indexOf("</table>", _laBody.indexOf('<tr className="la-total')));
  // 8b. the data palette: six tokens, light and dark, read in fixed order, never a raw hex on a dataset
  // 11 Oct 2026 NARROWED: the user chose the orange-led palette (plan = brand orange, delivered = blue, model = violet)
  ok("the data palette is six tokens in the light look (plan orange, delivered blue, teal, model violet, gold, not-yet grey)",
    /--chart-1:#E8590C; --chart-1-soft:rgba\(232,89,12,\.18\); --chart-2:#2563EB; --chart-3:#0D9488; --chart-4:#7C3AED; --chart-5:#A07D34; --chart-none:#A8A29E;/.test(html));
  ok("...and six dark steps on the dark surface (validated 10 Oct, colour-system-1010.md)",
    /--chart-1:#E8681E; --chart-1-soft:rgba\(232,104,30,\.22\); --chart-2:#5B8FF0; --chart-3:#13A193; --chart-4:#9572EE; --chart-5:#B48E3E; --chart-none:#6B6965;/.test(html));
  ok("⭐ the charts read the slots in FIXED order and a sixth series is grey, never a new hue (no cycled PALETTE)",
    code.includes('const CHART_SLOTS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"];')
    && code.includes('const colorOf = (i) => tok(CHART_SLOTS[i] || "--chart-none", "#A8A29E");') && !/const PALETTE = \[/.test(code));
  ok("🔴 no Dashboard dataset carries a raw hex: planned is slot 1, delivered slot 2, the model slot 4 (status colours stay on the stockpile chart only)",
    !/backgroundColor: "#[0-9A-Fa-f]{6}"/.test(_dbBody) && !/borderColor: "#[0-9A-Fa-f]{6}"/.test(_dbBody)
    && _dbBody.includes('C2 = tok("--chart-2", "#2563EB"), C4 = tok("--chart-4", "#7C3AED")')
    && _dbBody.includes("data: D.actualM, backgroundColor: C2") && _dbBody.includes("data: D.fairM, backgroundColor: C4")
    && _dbBody.includes("data: D.co2M, borderColor: C1, backgroundColor: C1S"));
  // 8. the shell: warm neutrals, a dimmed rail whose active item is ink
  ok("the shell tokens are the warm neutrals and the rail has its own two tokens, light and dark",
    /--line:#E7E5E4; --bg:#FFFFFF;/.test(html) && /--rail-bg:#FAFAF9; --rail-on:#1F2024;/.test(html) && /--rail-bg:#1B1D21; --rail-on:#F3F4F6;/.test(html));
  ok("⭐ the rail's active item is INK, not the action colour (one accent on a neutral shell)",
    /\.rail-item\.is-on\{background:var\(--surface\);color:var\(--rail-on\);font-weight:600;box-shadow:0 0 0 1px var\(--line\);\}/.test(html)
    && code.includes('className={"rail shrink-0 flex flex-col transition-[width] duration-150 "')
    && code.includes('className={"rail-item w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition " + (active ? "is-on" : "")}')
    && !code.includes('border-[color:var(--navy)] bg-slate-50 text-[color:var(--navy)] font-semibold'));
  ok("...and the pending count is a muted number, not a gold badge", code.includes('<span className="rail-count" title={`${badge} line(s) waiting for approval`}>{badge}</span>'));
  // 11 Oct 2026 — the fresher shell (fresh-directions.html: A with B's orange button and kicker)
  ok("the action colour is its own token: deep orange with white text in the light looks (5.2:1), brand orange with ink text in dark (7.0:1)",
    /--action:#C2410C; --action-fg:#FFFFFF;/.test(html) && /--action:#FF8C14; --action-fg:#1F2024;/.test(html)
    && /\.btn-pri\{display:inline-block;padding:7px 14px;border-radius:6px;background:var\(--action\);color:var\(--action-fg\);/.test(html)
    && (html.match(/var\(--brand-orange\)/g) || []).length <= 2);
  ok("the rail has line icons (inline SVG, no library) in place of the glyphs, one per nav entry",
    code.includes("function NavIcon({ id })") && code.includes("<NavIcon id={it.id} />") && !code.includes("{it.glyph}</span>")
    && ["dashboard", "submit", "forecasts", "lookahead", "locations", "routes", "zones", "config", "map"].every(k => new RegExp("\\n  " + k + ": \"M").test(code)));
  ok("the rail search filters the pages in place, Enter opens the first match, Ctrl K focuses it",
    code.includes('placeholder="Find a page…"') && code.includes("g.items.filter(navMatch)") && code.includes("if(e.key === \"Enter\" && navFirst){ setPage(navFirst.id); setNavQ(\"\"); }")
    && code.includes('(e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")'));
  ok("PageHeader takes a monospace kicker; the four rebuilt pages pass one",
    code.includes("function PageHeader({ title, subtitle, actions, children, kicker })") && code.includes('{kicker && <div className="kicker">{kicker}</div>}')
    && /\.kicker\{font:600 12px ui-monospace,/.test(html)
    && ['<PageHeader title="Dashboard" kicker=', '<PageHeader title="Forecasts" kicker="Plan"', '<PageHeader title="Configuration" kicker="Data"', '<PageHeader title="Look-ahead" kicker='].every(t => code.includes(t)));
  ok("the Dashboard's six figures sit in one strip card, and Big screen is the orange action button",
    /\.dash-cards\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\);gap:0;border:1px solid var\(--line\);/.test(html) && _dbBody.includes('className={wall ? "btn-sec" : "btn-pri"}'));
  ok("orange-led means the largest material over the whole programme takes slot 1; ranked on every row, so a filter never repaints",
    _dbBody.includes("const matRank = {}; rows.forEach(r => { matRank[r.material_type] = (matRank[r.material_type] || 0) + (r.tonnes || 0); });")
    && _dbBody.includes(".sort((a, b) => (matRank[b] || 0) - (matRank[a] || 0)"));
  // 11 Oct 2026 REVERSED (the user chose the Google style, options 4 + 1 + 2)
  ok("11 Oct: the tour bubble is Google-style — dark, slightly transparent, an arrow on the side it points from, text buttons",
    /\.guide-card\{position:fixed;z-index:9001;width:min\(300px,calc\(100vw - 24px\)\);background:rgba\(32,33,36,\.88\);[^}]*backdrop-filter:blur\(8px\)/.test(html)
    && /\.guide-card\[data-place="above"\]::before/.test(html) && code.includes("data-place={place}"));
  {
    // NARROWED 14 Oct 2026 (D9): the signature gained `phone`
    const gf = (src.match(/function Guide\(\{ page, groups, phone \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    ok("11 Oct: nothing pops up uninvited — the first visit shows the strip and the dots, not the tour",
      gf.includes('setHints(true); setStrip(guideRead(key) !== "done");') && !/if\(s\.length\)\{ setSteps\(s\); setI\(0\); \}/.test(gf));
    ok("11 Oct: the strip offers the tour and × switches every tip off; dots one per distinct anchor, re-placed every second, none during the tour",
      // NARROWED 11 Oct 2026 (the review: on the Carbon page it covered the result strip): the strip's foot is 16 px, or just above a [data-sticky-foot]
      gf.includes(">Take the tour</button>") && gf.includes("style={{ left: railRight + 16, bottom: stripBottom }}") && gf.includes('aria-label="Hide the tips"') && gf.includes("onClick={off}")
      && gf.includes("const [stripBottom, setStripBottom] = useState(16);") && gf.includes("document.querySelector('[data-sticky-foot]')")
      && gf.includes("Math.round(window.innerHeight - fr.top) + 8 : 16;") && gf.indexOf("useState(16)") < gf.indexOf("if(!step) return hintsEl;")
      && gf.includes("if(seen.has(s.anchor) || !s.body) return; seen.add(s.anchor);") && gf.includes("const id = setInterval(place, 1000);")
      && gf.includes("if(!hints || steps.length){ setDots([]); return; }"));
  }
  // REVERSED 11 Oct 2026 (the demo bar, the user: the map's strip "on every page"): the header badge and PR #20's
  // logic that hid it under the embedded map are gone — the bar under the header carries the notice on every view,
  // and the embedded map no longer draws its own. Nothing else read body[data-view] or body[data-map-open].
  ok("11 Oct (demo bar): the header's demo badge and PR #20's hide logic are gone — no .demo-badge, no body[data-view] / body[data-map-open] CSS, neither effect",
    // the CSS and the code with their comments removed (the comments say what went and why)
    ((css) => !/demo-badge/.test(css) && !/data-view|data-map-open/.test(css))
      ((html.match(/<style>([\s\S]*?)<\/style>/) || ["", ""])[1].replace(/\/\*[\s\S]*?\*\//g, ""))
    && !/demo-badge|data-view|data-map-open/.test(code)
    && !code.includes("document.body.dataset.view") && !code.includes("dataset.mapOpen") && !/\bmapOpen\b/.test(code));
  // ---- 11 Oct 2026: the demo bar on every page ---------------------------------------------------------------
  // The user: "There is a bar with FICTIONAL DEMO SCHEME · NOTHING HERE IS REAL and a guide button on the public
  // map. Lets have that on every page." One bar in App between the header and <main>, keyed on TENANT.demo_notice.
  {
    const appFn = (src.match(/function App\(\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    const appCode = (code.match(/function App\(\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    const hdrFn = (code.match(/function Header\(\{ view, role, setView, signOut, vehLang, setVehLang \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    const barFn = (src.match(/function DemoBar\(\{ onGuide \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    const portalFn = (src.match(/function Portal\(\{ role, who, meta, metaErr, vehLang, onPage \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    ok("⭐ the bar sits in App between <Header/> and <main> (main is flex-1 min-h-0, so it gives up the 26 px and nothing overflows)",
      /<Header view=\{view\} role=\{role\} setView=\{setView\} signOut=\{signOut\} vehLang=\{vehLang\} setVehLang=\{setVehLang\} \/>\s*(?:\{\}\s*)?<DemoBar onGuide=\{barGuide\} \/>\s*<main className="flex-1 min-h-0 flex flex-col">/.test(appCode)
      && (code.match(/<DemoBar /g) || []).length === 1);
    // NARROWED 11 Oct 2026 (review): the bar must be there at all (with no <DemoBar> indexOf is -1 and every "<" held,
    // so this passed with the bar deleted), and the label claimed Loading and the service error, which it cannot
    // cover: the notice is unknown until /api/meta answers. The embedded map keeps its own strip when the bar is absent.
    ok("⭐ ...so it is on every view once /api/meta has answered: the public map (and its password page), sign-in, and every Portal page (not over Loading or the service error; the embedded map keeps its own strip when the bar is absent)",
      appCode.indexOf("<DemoBar ") > 0
      && appCode.indexOf("<DemoBar ") < appCode.indexOf('{view === "public" && <PublicMap')
      && appCode.indexOf("<DemoBar ") < appCode.indexOf('{view === "login" && <Login') && appCode.indexOf("<DemoBar ") < appCode.indexOf('{view === "portal" && ('));
    ok("🔴 keyed on TENANT.demo_notice: a real tenant (no notice) gets no bar at all",
      barFn.startsWith("\n  if(!TENANT.demo_notice) return null;") && !/use[A-Z]\w*\(/.test(barFn));
    ok("the bar shows the tenant's own words (uppercased by CSS, the full text on hover) and the Guide only when there is a tour to replay",
      barFn.includes('<span className="demo-bar-text" title={TENANT.demo_notice}>{TENANT.demo_notice}</span>')
      && barFn.includes('{onGuide && (') && barFn.includes('<button type="button" className="demo-bar-guide" onClick={onGuide} title="Replay the guide for this page">Guide</button>')
      && barFn.includes('className={"demo-bar" + (onGuide ? " has-guide" : "")}') && !/HEADER_DEMO_NAME|IPT/.test(barFn));
    ok("🔴 nothing in the bar touches the document while rendering (render_frontend's stub has no querySelector), and App reads no body dataset",
      !/document\./.test(barFn) && !/document\.body|querySelector/.test(appCode));
    // NARROWED 11 Oct 2026 (review): the notice is 14 px (the floor), not 13 px (the hint allowance): a required
    // notice is not a hint
    // NARROWED 13 Oct 2026 (D45, Option A chosen by the user): light grey with red text and a 3 px red rule, was ink
    // with amber text and a 1 px amber rule; the token values are pinned in the 13 Oct block at the end of this file
    ok("the bar is CSS classes in <style>: 26 px, light grey with red text from tokens, centred, uppercase, letter-spaced, an ellipsis, the Guide at the right end, 14 px text",
      /\.demo-bar\{position:relative;flex:none;height:26px;display:flex;align-items:center;justify-content:center;padding:0 12px;background:var\(--demo-bg\);color:var\(--demo-fg\);border-bottom:3px solid var\(--demo-rule\);font:700 14px\/1 Inter,system-ui,sans-serif;letter-spacing:\.06em;/.test(html)
      && !/\.demo-bar[^{]*\{[^}]*font:[^;]*\b1[0-3](?:\.\d+)?px/.test(html)
      && /\.demo-bar-text\{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-transform:uppercase;\}/.test(html)
      && /\.demo-bar-guide\{position:absolute;right:8px;top:2px;height:21px;[^}]*font:600 14px\/21px /.test(html) && /\.demo-bar\.has-guide\{padding:0 84px;\}/.test(html)
      && /--demo-bg:#F1F5F9; --demo-fg:#B91C1C; --demo-rule:#DC2626;/.test(html));
    // REVERSED 11 Oct 2026 (review): on a phone the text no longer truncates. With the Guide beside it, 375 px cut the
    // notice to "FICTIONAL DEMO SCHEME · NOTHING H…" on every Portal page; below 640 px it now wraps whole (the map's
    // own phone strip wrapped too), the bar grows from its 26 px, and the Guide keeps its slot, vertically centred.
    ok("...the Guide keeps its slot at every width, phones included (below 640 px the text WRAPS whole, the bar grows, the button is centred)",
      /@media \(max-width:639px\)\{ \.demo-bar\{letter-spacing:\.03em;height:auto;min-height:26px;padding:4px 12px;line-height:1\.3;\} \.demo-bar\.has-guide\{padding:4px 76px 4px 12px;\} \.demo-bar-text\{white-space:normal;text-overflow:clip;text-align:center;\} \.demo-bar-guide\{top:50%;transform:translateY\(-50%\);\} \}/.test(html)
      && !/@media \(max-width:639px\)\{[^\n]*\.demo-bar-text\{[^}]*white-space:nowrap/.test(html)
      && !/hidden sm:|sm:inline|md:/.test(barFn));
    ok("...no Tailwind colour utility in the bar (no DARK-REMAP needed) and no brand orange",
      !/\b(?:bg|text|border)-(?:slate|amber|gray|white|black|blue|red|\[)/.test(barFn) && !/brand-orange/.test(barFn));
    ok("🔴 the header has no badge and no Guide button of its own any more (the bar has them)",
      !/demo-badge/.test(hdrFn) && !/GUIDE_EVENT|>\s*Guide\s*</.test(hdrFn) && !/TENANT\.demo_notice &&/.test(hdrFn)
      && /<AppearancePicker \/>/.test(hdrFn) && /Sign out/.test(hdrFn) && /Staff sign in/.test(hdrFn));
    ok("the bar's Guide: none on sign-in; the embedded map's tour on a map view once the map says it is ready; the app's guide on other Portal pages",
      appFn.includes('const onMap = view === "public" || (view === "portal" && page === "map");')
      // 11 Oct: "resume" (signing back in after a reload) has no guide either, like the sign-in view
      // NARROWED 14 Oct 2026 (G3): the set-password and dead-link views have no tour either
      && appFn.includes('const barGuide = (view === "login" || view === "resume" || view === "setpw" || view === "linkerr") ? null : onMap ? (mapTour ? startMapTour : null) : replayAppGuide;'));
    ok("🔴 a reload with a stored code starts on resume and re-checks it with /api/auth, never trusting it unchecked",
      // NARROWED 14 Oct 2026 (G3): a set-password link opens "setpw"; a lead's link, a stored code or a browser that
      // signed in with a login before (the hint) starts on "resume"; anything else the public map, as before
      appFn.includes('const [view, setView] = useState(() => (START_LINK && START_LINK.purpose !== "demo") ? "setpw"\n    : (START_LINK || ACCESS.code || hasAuthHint()) ? "resume" : "public");')
      && appFn.includes('body: JSON.stringify({ code: ACCESS.code }) })')
      && appFn.includes('.then(info => { ACCESS.info = info; setRole(info); setView("portal"); })')
      && (appFn.match(/setView\("portal"\)/g) || []).length === 3);   // signIn(), the checked code resume and (G3) the checked session resume
    ok("...a 401 / 403 forgets the stored code; the public map is the fallback either way",
      appFn.includes('if(e === 401 || e === 403){ ACCESS.code = ""; try { sessionStorage.removeItem("modus_access_code"); } catch(x){} }')
      && /\.catch\(e => \{[\s\S]{0,400}setView\("public"\);\s*\}\);/.test(appFn));
    ok("...the map's readiness comes from a same-origin message of one type, and resets on every new screen (a new iframe announces itself again)",
      appFn.includes("if(e.origin === window.location.origin && e.data && e.data.type === MAP_TOUR_MSG) setMapTour(true);")
      && appFn.includes('window.addEventListener("message", on);') && appFn.includes('return () => window.removeEventListener("message", on);')
      && appFn.includes("useEffect(() => { setMapTour(false); }, [view, page]);") && /const MAP_TOUR_MSG = "wayscope-map-tour";/.test(src));
    ok("(review) tellMapBarOn: outside App, posts BAR_ON_MSG into each map iframe, same origin only, guarded",
      /function tellMapBarOn\(\)\{\n  try \{\n    document\.querySelectorAll\('iframe\[title="Public Route Map"\]'\)\.forEach\(f => \{\n      if\(f\.contentWindow\) f\.contentWindow\.postMessage\(\{ type: BAR_ON_MSG \}, window\.location\.origin\);\n    \}\);\n  \} catch\(e\)\{\}\n\}/.test(src)
      && !/postMessage\([^)]*["']\*["']/.test(src) && !appFn.includes("function tellMapBarOn"));
    ok("(review) App tells the map in an EFFECT on meta (after the bar is committed), demo tenant only; a hook, App has no early return",
      appFn.includes("useEffect(() => { if(meta && TENANT.demo_notice) tellMapBarOn(); }, [meta]);")
      && !/\n  if\([^\n]*\) return /.test(appFn));
    ok("...Portal reports its page up (a hook before its early returns), App passes setPage",
      portalFn.includes("useEffect(() => { if(onPage) onPage(page); }, [page]);")
      && portalFn.indexOf("useEffect(() => { if(onPage) onPage(page); }, [page]);") < portalFn.indexOf("if(metaErr){")
      && /<Portal role=\{role\} who=\{who\} meta=\{meta\} metaErr=\{metaErr\} vehLang=\{vehLang\} onPage=\{setPage\} \/>/.test(src));
    ok("🔴 the map's tour is started through the same-origin iframe, guarded: no iframe, the map password page (no guideStart) or a throw does nothing",
      /function startMapTour\(\)\{\n  try \{\n    const f = document\.querySelector\('iframe\[title="Public Route Map"\]'\);\n    const w = f && f\.contentWindow;\n    if\(w && typeof w\.guideStart === "function"\) w\.guideStart\(\);\n  \} catch\(e\)\{\}\n\}/.test(src));
    ok("⭐ both iframes are the map EMBEDDED: MAP_URL carries embed=1 and both iframes use MAP_URL",
      /const MAP_URL = "\/map\/\?embed=1&v=" \+ Date\.now\(\);/.test(src)
      && /<iframe src=\{MAP_URL\} title="Public Route Map" className="flex-1 w-full border-0" \/>/.test(src)
      && /<iframe src=\{MAP_URL\} title="Public Route Map" className="w-full h-full border-0" \/>/.test(src)
      && (src.match(/<iframe /g) || []).length === 2 && !/<iframe src="\/map/.test(src));
    {
      const mapHtml = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
      // 11 Oct 2026 (review): the map hides its own notice only under a real .demo-bar, and the app tells it when the
      // bar arrives after the map has loaded
      ok("⭐ (review) the late-bar contract: the app posts 'wayscope-bar-on' that the map listens for, and the map looks for the .demo-bar the app renders",
        /const BAR_ON_MSG = "wayscope-bar-on";/.test(src) && mapHtml.includes("e.data.type !== 'wayscope-bar-on'")
        && mapHtml.includes("window.parent.document.querySelector('.demo-bar')") && /className=\{"demo-bar" \+ \(onGuide \? " has-guide" : ""\)\}/.test(src));
      ok("⭐ the contract with /map/: it posts the same message type, defines a global guideStart, and reads the same embed flag",
        mapHtml.includes("window.parent.postMessage({ type: 'wayscope-map-tour' }, location.origin);")
        && /\n    function guideStart\(\)\{/.test(mapHtml) && mapHtml.includes("new URLSearchParams(location.search).get('embed') === '1'"));
    }
    ok("the app's own guide is not mounted on the Route map (the embedded map runs its own): one 'New here?' strip there, and the app never touches wayscope_guide_map",
      // 14 Oct 2026 (narrowed): nor over the Dashboard's big screen
      // 14 Oct 2026 (narrowed, D9): nor over a desk page's card on a phone; the guide is told it is on a phone
      portalFn.includes('{page !== "map" && !phoneDesk && !(page === "dashboard" && wallOn) && <Guide page={page} groups={visible} phone={narrow} />}') && (src.match(/<Guide /g) || []).length === 1
      && !/\n  map: \[/.test((src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1]));
    ok("a page with no steps of its own (Config) replays the welcome, so the bar's Guide never does nothing",
      // NARROWED 14 Oct 2026 (D9): the page's steps come from stepsOf() (on a phone, its own set or the desk steps left out)
      /const startTour = \(\) => \{ setTip\(null\); setSteps\(build\(guideRead\("welcome"\) !== "done" \|\| !stepsOf\(\)\.length\)\); setI\(0\); \};/.test(src)
      && src.includes('const stepsOf = () => (phone && GUIDE_STEPS[key + "_phone"]) ? GUIDE_STEPS[key + "_phone"] : (GUIDE_STEPS[key] || []).filter(s => !(phone && s.desk));'));
  }
  {
    // NOTE 11 Oct 2026 (the demo bar): the bar above the map lives in App, not in PublicMap; this pin is about
    // PublicMap's own strip (the old title line and the Submit link), which stays gone
    const pm = (src.match(/function PublicMap\(\{ onLogin \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    ok("11 Oct: the public map page is only the map — no strip above it, no 'Submit a forecast' link; the header keeps Staff sign in",
      pm.includes('<iframe src={MAP_URL} title="Public Route Map" className="flex-1 w-full border-0" />')
      && !/Toggle <span|Approved haul-route forecasts|Submit a forecast/.test(pm.replace(/\/\/.*$/gm, ""))
      && code.includes('onClick={() => setView("login")}'));
  }
  {
    // NARROWED 14 Oct 2026 (G3): Login also takes the "you have been signed out" notice
    const lg = (src.match(/function Login\(\{ onSignIn, onBack, savedName, notice \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
    ok("11 Oct: the staff sign-in uses the finalised theme — tokens, labels above, orange focus and button; no blue focus ring, no navy button",
      lg.includes('<div className="auth-card">') && lg.includes('className="btn-pri auth-go"') && lg.includes('<label htmlFor="auth-code">Access code</label>')
      && !/focus:ring-\[color:var\(--blue\)\]/.test(lg) && !/background:"var\(--navy\)"/.test(lg)
      && /\.auth-input:focus\{outline:2px solid var\(--action\);/.test(html));
    ok("11 Oct: the access code has a show / hide eye that flips the input type and its label",
      lg.includes('type={show ? "text" : "password"}') && lg.includes("onClick={() => setShow(s => !s)}")
      && lg.includes('aria-label={show ? "Hide access code" : "Show access code"}') && lg.includes("aria-pressed={show}")
      && lg.includes('placeholder="Access code"'));
  }
  // 5. the shared components
  ok("the empty-state family: one EmptyState with a kind, marked data-empty, no dashed border; a SkeletonTable; StatusWord; AppliedChips",
    code.includes("function EmptyState({ title, body, action, kind })") && code.includes('data-empty={k}') && !code.includes("border-dashed")
    && code.includes("function SkeletonTable({ cols, rows, caption })") && code.includes("function StatusWord({ status, label })") && code.includes("function AppliedChips({ chips, onClear, onClearAll, count })"));
  ok("...the three kinds are used: none (Forecasts), nomatch (Forecasts + Dashboard), error (Forecasts), and a skeleton while Forecasts and Config load",
    _fcBody.includes('<EmptyState kind="error" title="Forecasts did not load"') && _fcBody.includes('<EmptyState kind="nomatch" title="No lines match these filters"')
    && _fcBody.includes('<EmptyState title="No forecast lines yet"') && _dbBody.includes('<EmptyState kind="nomatch" title="No forecast lines match these filters"')
    && _fcBody.includes("<SkeletonTable cols=") && _cfBody.includes("<SkeletonTable cols="));
  // the table style: 14 px, 40 px rows (32 compact), a sticky header, numbers right-aligned, the sort shown once
  ok("the shared table style: 14 px, 40 px rows, 32 px compact, a sticky header, .num right-aligned, one sorted header",
    /\.tbl\{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;font-variant-numeric:tabular-nums;/.test(html)
    && /\.tbl th\{position:sticky;top:0;z-index:1;/.test(html) && /\.tbl td\{padding:0 12px;height:40px;/.test(html)
    && /\.tbl\.compact th,\.tbl\.compact td\{height:32px;\}/.test(html) && /\.tbl \.num\{text-align:right;\}/.test(html) && /\.tbl th\.sorted::after\{content:" ▾";\}/.test(html));
  // 2 + 4. Forecasts
  ok("Forecasts: one .tbl with a caption, the unit in the header, numbers in .num cells, the one visible sort",
    // 13 Oct 2026 (W6, narrowed): one unit for every line through the switch (the header names it); what was typed,
    // in its own unit, is in the details
    _fcBody.includes('<table className="tbl rd-table" data-rd-table="forecasts">') && _fcBody.includes("<caption><b>Forecast lines</b> · {sortCaption}")
    && _fcBody.includes('{th(qtyHead, "quantity", true)}') && _fcBody.includes('<td className="num" data-label={qtyHead}>')
    && _fcBody.includes('<RdItem t="Typed">{`${fmt(g.quantity, g.unit)} ${unitLabel(g.unit)}`}</RdItem>') && _fcBody.includes('const [sort, setSort] = useState({ key: "quantity", dir: "desc" });'));
  ok("...a filter row with applied-filter chips and Clear all above the table; the status chips left the page header",
    _fcBody.includes('<div className="filter-row" data-guide="forecast-status">') && _fcBody.includes("<AppliedChips chips={applied} onClear={clearOne} onClearAll={clearAll}")
    && _fcBody.includes("const clearAll = () => setF({ status: \"ALL\", ipt: \"ALL\", discipline: \"ALL\", mine: false, q: \"\" });")
    && !_fcBody.includes("badge(s)"));
  ok("...Approve is the one visible action; Reject, Edit and Withdraw sit behind the row menu; status is a word with a dot",
    _fcBody.includes('<details className="row-menu">') && _fcBody.includes(">Reject…</button>") && _fcBody.includes(">Edit in Submit forecast</button>") && _fcBody.includes(">Withdraw…</button>")
    // 13 Oct 2026 (W6, narrowed): the status is RowStatus, a word and an icon (Rejected, ROAD LIMIT, Pending, Mixed, Approved)
    && _fcBody.includes("<RowStatus word={st.word} tone={st.tone} more={st.more} />") && _fcBody.includes('className="btn-pri btn-sm mr-1">Approve</button>'));
  ok("🔴 no 9, 10 or 11 px product text on the Forecasts page (the 13 px allowance only)",
    !/text-\[(9|10|11)px\]/.test(_fcBody));
  // 6. Configuration as a form
  ok("Config: a section list, a two-thirds form, labels above inputs, one Save bar, the token and Reset behind More",
    _cfBody.includes('<div className="cfg-grid">') && _cfBody.includes('<nav className="cfg-nav" aria-label="Configuration sections">')
    && _cfBody.includes('<div className="savebar" data-cfg-savebar="1">') && _cfBody.includes('<details className="row-menu" data-cfg-more="1">')
    && _cfBody.includes(">Reset to file…</button>") && _cfBody.includes('<label htmlFor={"cfg-" + k}>{l}</label>') && _cfBody.includes('<div className="hint">{help}</div>')
    && /\.cfg-grid\{display:grid;grid-template-columns:200px minmax\(0,800px\);/.test(html) && /\.savebar\{position:sticky;bottom:0;/.test(html));
  ok("...every form label in the file is 14 px above its input; the 11 px uppercase label is gone",
    (code.match(/<span className="block text-sm font-medium text-slate-700 mb-1">/g) || []).length >= 40
    && !code.includes('text-[11px] uppercase tracking-wide text-slate-400') && !/text-\[(9|10|11)px\]/.test(_cfBody));
  ok("...one Discard beside Save, both in the bar; Reset keeps its confirm", _cfBody.includes(">Discard</button>") && _cfBody.includes('if(!confirm("Replace the live configuration with backend/factors.json?'));
  // 13 Oct 2026 (W12, bundle B): Config → Map and bulletin — the scheme's council colour bands
  ok("⭐ W12: Config has a 'Map and bulletin' section, before Everything (JSON), with three band fields per measure",
    _cfBody.includes('["seasonal", "Seasonal restrictions"], ["mapbulletin", "Map and bulletin"], ["raw", "Everything (JSON)"]')
    && _cfBody.includes('{tab === "mapbulletin" && (') && _cfBody.includes('data-cfg="council-breaks"')
    && _cfBody.includes('{[0, 1, 2].map(i => (') && _cfBody.includes('aria-label={`${l}, band ${i + 1} of 3`}')
    && _cfBody.includes('placeholder={String(COUNCIL_BREAKS_DEFAULT[m][i])}')
    && _cfBody.includes('"Movements by council: two-way movements a day"') && _cfBody.includes('"Carbon by council: t CO₂e in the month"'));
  const _sbSrc = (_cfBody.match(/const setBreak = \(d, m, i, v\) => \{[\s\S]*?\n  \};/) || [""])[0];
  const setBreak = _sbSrc ? new Function(_sbSrc + "; return setBreak;")() : null;
  const _d1 = { tenant: { name: "X" } };
  if (setBreak) { setBreak(_d1, "carbon", 0, 20); setBreak(_d1, "carbon", 1, 50); setBreak(_d1, "carbon", 2, 100); }
  const _d2 = JSON.parse(JSON.stringify(_d1));
  if (setBreak) { setBreak(_d2, "carbon", 0, null); setBreak(_d2, "carbon", 1, null); setBreak(_d2, "carbon", 2, null); }
  const _d3 = {};
  if (setBreak) setBreak(_d3, "movements", 1, 80);
  ok("⭐ W12: the fields write tenant.council_breaks (three per measure); clearing all three removes the row, so the default applies",
    !!setBreak && JSON.stringify(_d1.tenant.council_breaks) === '{"carbon":[20,50,100]}' && _d1.tenant.name === "X"
    && _d2.tenant.council_breaks === undefined && JSON.stringify(_d3.tenant.council_breaks) === '{"movements":[null,80,null]}',
    JSON.stringify([_d1, _d2, _d3]));
  ok("🔴 W12: the section's words follow the word rule (no bake, server, endpoint, token or cached on this screen)",
    !/\b(bake|baked|server|endpoint|token|cached|geometry)\b/i.test(_cfBody.slice(_cfBody.indexOf('{tab === "mapbulletin"'), _cfBody.indexOf('{tab === "costing"'))));
  // 1. the one-screen Dashboard
  ok("Dashboard: the working view is six cards, four charts, and five collapsed sections; the big screen keeps its four WallSections",
    (_dbWork.match(/<Card label=/g) || []).length === 6 && _dbWork.includes('<div className="dash-cards" data-guide="dash-figures">')
    && (_dbWork.match(/<details className="dash-more"/g) || []).length === 5 && (_dbWork.match(/<ChartCanvas config=/g) || []).length === 8
    // 14 Oct 2026 (narrowed): five WallSections; the same eight charts, four in Charts and four in More charts
    // 17 Oct 2026 (narrowed): six WallSections — the sixth is the Simulation (SimWall), no chart in it
    && (_dbWall.match(/<WallSection show=\{sectionShown\(/g) || []).length === 6 && (_dbWall.match(/<ChartCanvas config=/g) || []).length === 8
    && (_dbWall.match(/<div className="wall-charts">/g) || []).length === 2);
  ok("...the six cards: material, deliveries a day (11 Oct: one delivery = one two-way movement; working days from Config), vehicles needed, planned this week, delivered against plan, transport carbon",
    ['label="Material in view"', 'label="Deliveries a day"', 'label="Vehicles needed"', 'label="Planned this week"', 'label="Delivered against plan"', 'label="Transport carbon"'].every(t => _dbWork.includes(t))
    && _dbBody.includes("const wdPerMonth = +(((factors || {}).planning || {}).working_days_per_month || 22);") && _dbBody.includes("const loadsPerDay = K.totTrips / (nMonths * wdPerMonth);"));
  // 13 Oct 2026 (W5): narrowed — no onToggle handler any more; a chart in a collapsed section is built when its box
  // first has a size (ChartCanvas's ResizeObserver), so it is measured right on the first open
  ok("...a collapsed section re-measures what it holds when opened (13 Oct: each chart box watches itself; no onMore)",
    !_dbBody.includes("const onMore") && (_dbWork.match(/onToggle=\{onMore\}/g) || []).length === 0
    && (_dbWork.match(/<details className="dash-more"/g) || []).length === 5
    && /function ChartCanvas[\s\S]{0,2600}if\(!\(el\.clientWidth > 0 && el\.clientHeight > 0\)\) return;/.test(src));
  ok("...three filters in the header, the rest behind More filters, applied chips with Clear all",
    _dbBody.includes(">More filters ▾</summary>") && _dbBody.includes('<div className="row-menu-list dash-filters">') && _dbBody.includes("{!wall && <AppliedChips chips={applied} onClear={clearOne} onClearAll={clearAll}"));
  // 3. the Look-ahead grid
  ok("Look-ahead: the commit grid is a compact .tbl with a caption, the row named in words, a Week column, a Status column and a totals row",
    // 13 Oct 2026 (W6, narrowed): the caption follows the unit switch; the row is named by its two ends (team, section
    // and the rest in the details); ONE status column, after the route (the flags win over the week's state: decision 1)
    _laGrid.includes('"Planned quantity by day"}</b>') && _laGrid.includes('<th className="la-stick" style={{ minWidth: 280 }}>Route</th>')
    && _laGrid.includes('<th className="num">Week</th>') && _laGrid.includes("<th>Status</th>") && _laGrid.includes('<tr className="la-total rd-card">')
    && _laGrid.includes('<td className="rd-status" data-label="Status"><RowStatus word={st.word} tone={st.tone} more={st.more} /></td>'));
  ok("...the day cell is a figure until clicked, then an input that saves on blur, Enter or Escape",
    // 13 Oct 2026 (W6, narrowed): the weekend greying went with the weekend days (the grid shows Mon–Fri only)
    _laGrid.includes('<button type="button" className="la-cell"') && _laGrid.includes('onBlur={() => { saveDay(line, d); setEditing(null); }}')
    && _laGrid.includes('onKeyDown={e => { if(e.key === "Enter" || e.key === "Escape") e.currentTarget.blur(); }}'));
  ok("🔴 no 9, 10 or 11 px text in the commit grid; status and flags are words with dots",
    // 13 Oct 2026 (W6, narrowed): LineFlags and StatusChip gave way to ONE RowStatus a row; the flags are words in the
    // status and in the details (flagWord with the grid's own word table)
    !/text-\[(9|10|11)px\]/.test(_laGrid) && /function laStatus\(flags, w\)\{[\s\S]*?word: flagWord\(f, LINE_FLAG_LABEL\)/.test(code)
    && _laGrid.includes("{laFlagGroups(lf).map(g => <RdItem key={g.code} t={g.word} wide bad={g.tone === \"bad\"}>")
    && /function laFlagGroups\(flags\)\{[\s\S]*?word: flagWord\(f, LINE_FLAG_LABEL\)[\s\S]*?const t = teamText\(f\.text \|\| ""\)/.test(code));
  ok("...the clash rail is a card that says how many flags, each a word with a dot; +N more kept",
    _laBody.includes('<span className="font-semibold shrink-0">{rail.count} flag{rail.count === 1 ? "" : "s"} this week</span>')
    && _laBody.includes("rail.flags.slice(0, 3)") && _laBody.includes("more`"));
}

// ---- 11 Oct 2026: the carbon target on the Dashboard, Forecasts and Submit forecast -------------
// Source-level. What they prove: each surface reads GET /api/carbon/target in its OWN read (or, on
// Submit forecast, the preview's carbon block), nothing works carbon out in the browser, the
// six-card pin still holds, and the words are the contract's. Not covered here: the loaded
// states and the big-screen figure (render_frontend.js, from fixtures/carbon_target.json; ctFig is
// called directly, the Dashboard is not rendered in wall mode), and the read itself, the button's
// click and the error state (dom_frontend.js, against a stubbed fetch — NARROWED 11 Oct 2026: this
// comment claimed dom_frontend.js covered them before it did). Not covered anywhere: a browser, the live server.
{
  const c0 = src.indexOf("// ---- 11 Oct 2026: the carbon target on the Dashboard, Forecasts and Submit forecast");
  const c1 = src.indexOf("function Dashboard(");
  const ctSrc = c0 > 0 && c1 > c0 ? src.slice(c0, c1) : "";
  const ctc = ctSrc.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  const _dbc = code.slice(code.indexOf("function Dashboard("), code.indexOf("function DashboardToday("));
  const _dbW = _dbc.slice(_dbc.indexOf("{!wall ? ("), _dbc.indexOf("      ) : (\n        <>\n"));
  const _dbWl = _dbc.slice(_dbc.indexOf("      ) : (\n        <>\n"));
  const _fcc = code.slice(code.indexOf("function Forecasts("), code.indexOf("function CostingTab("));
  const _mxc = code.slice(code.indexOf("function Matrix("), code.indexOf("function Forecasts("));
  const mxCt = _mxc.slice(_mxc.indexOf("{cost && cost.carbon && (() => {"), _mxc.indexOf("{ctCellsTarget(ct)}</div>}") + 26);
  const GETS = /fetch\(`\$\{API\}\/carbon\/target`\)/g;
  ok("⭐ CARBON TARGET: one block of helpers before the Dashboard — the strip, the Forecasts line and the word helpers",
    ctSrc.length > 3000 && ctc.includes("function CarbonTargetStrip({ ct, err, onOpen })") && ctc.includes("function CarbonTargetLine({ ct, err, pendingN })")
    && ["ctGap", "ctTargetLine", "ctProgress", "ctScopeNote", "ctSetBy", "ctCellsTarget", "ctFig"].every(f => ctc.includes(`function ${f}(`)));
  ok("🔴 ...each of the three surfaces reads it in its OWN read, a GET with no method: nothing on them writes the target",
    [_dbc, _fcc, _mxc].every(b => (b.match(GETS) || []).length === 1 && !/carbon\/target`,/.test(b))
    && (ctc.match(GETS) || []).length === 0 && !/fetch\(/.test(ctc));
  ok("...guarded by initialTarget (the render harness); Dashboard and Forecasts read it again on tick (big-screen refresh; Refresh, Approve, Reject, Withdraw), Submit forecast once",
    [_dbc, _fcc, _mxc].every(b => b.includes("const [ct, setCt] = useState(initialTarget || null);") && b.includes("if(initialTarget) return;"))
    && /fetch\(`\$\{API\}\/carbon\/target`\)[\s\S]{0,220}\}, \[tick\]\);/.test(_dbc) && /fetch\(`\$\{API\}\/carbon\/target`\)[\s\S]{0,220}\}, \[tick\]\);/.test(_fcc)
    && /fetch\(`\$\{API\}\/carbon\/target`\)[\s\S]{0,160}\}, \[\]\);/.test(_mxc)
    && _dbc.includes("{ if(live) setCtErr(true); }") && _fcc.includes("{ if(live) setCtErr(true); }"));
  ok("🔴 ...the Dashboard's new hooks sit before its early returns (React #310 blanked the app on 5 Oct)",
    _dbc.indexOf("const [ct, setCt]") > 0 && _dbc.indexOf("const [ct, setCt]") < _dbc.indexOf("if(err) return")
    && _dbc.indexOf("fetch(`${API}/carbon/target`)") < _dbc.indexOf("if(err) return"));
  ok("⭐ Dashboard: a strip under the six cards, NOT a seventh card; with no target, a button opens the Carbon planner through the Portal's page switch",
    _dbW.includes("<CarbonTargetStrip ct={ct} err={ctErr} onOpen={onOpen} />") && (_dbW.match(/<Card label=/g) || []).length === 6
    && _dbW.indexOf("<CarbonTargetStrip") > _dbW.indexOf('<div className="dash-cards" data-guide="dash-figures">')
    && _dbW.indexOf("<CarbonTargetStrip") < _dbW.indexOf('<details className="dash-more"')
    // 14 Oct 2026 (narrowed): onWall also tells the Portal the big screen is on (no tour over it)
    // 14 Oct 2026 (narrowed, D9): the Portal tells the Dashboard it is on a phone (no big screen there)
    && code.includes("<Dashboard meta={meta} phone={narrow} onWall={(on) => { setRailOpen(!on); setWallOn(!!on); }} onOpen={setPage} />")
    // NARROWED 11 Oct 2026 (gate arrivals: the render harness's prop initialGates joins the signature); 14 Oct 2026: + phone
    // NARROWED 14 Oct 2026 (bundle G, W7: the render harness's prop initialClp joins the signature too; merged with D9's phone)
    // NARROWED 16 Oct 2026 (S7: the render harness's prop initialSim joins the signature)
    && code.includes("function Dashboard({ meta, initialData, initialWeek, initialTarget, initialGates, initialClp, initialSim, onWall, onOpen, phone })")
    && ctc.includes('{onOpen && <button type="button" className="btn-sec" onClick={() => onOpen("carbon")}>Open the Carbon planner</button>}'));
  ok("...the big screen's Carbon group gains ONE target figure in the group's own pattern (a Fig with a title); the working view's group is unchanged",
    // 13 Oct 2026 (W3, narrowed): the Fig's words ride in its info box (value) instead of a title
    (_dbWl.match(/<Fig value=\{ctW\.value\} label="tCO2e target, all-in" sub=\{ctW\.sub\} info=\{\{ id: "dash\.target", value: ctW\.title \}\} \/>/g) || []).length === 1
    && !_dbW.includes("ctW.") && _dbc.includes("const ctW = ctFig(ct, ctErr);"));
  ok("⭐ Forecasts: the line sits under the PageHeader, before the list in every state; the pending count is the page's own (lines with a Pending month)",
    _fcc.includes("<CarbonTargetLine ct={ct} err={ctErr} pendingN={rows ? pendingN : null} />")
    && _fcc.indexOf('<PageHeader title="Forecasts"') < _fcc.indexOf("<CarbonTargetLine") && _fcc.indexOf("<CarbonTargetLine") < _fcc.indexOf("{err ? <EmptyState")
    && _fcc.includes('const pendingN = useMemo(() => groups.filter(g => g.statuses.has("Pending")).length, [groups]);')
    && ctc.includes("`The ${pendingN} pending line${pendingN === 1 ? \"\" : \"s\"} would add ${ctT(s.pending_t)} tCO2e.`"));
  ok("⭐ Submit forecast: the cells' carbon is the preview's own block (total and parts as sent, the unrouted words), inside the price strip, with the target beside it",
    mxCt.length > 300 && _mxc.indexOf('data-cost-strip="1"') < _mxc.indexOf("{cost && cost.carbon && (() => {")
    && _mxc.indexOf("{ctCellsTarget(ct)}</div>}") < _mxc.indexOf("Movements = loads per working day")
    && mxCt.includes("Carbon of these cells: <b>{ctT(c.total_t)} tCO2e</b>")
    && mxCt.includes('[["material", c.material_t], ["transport", c.transport_t], ["waste disposal", c.disposal_t]]')
    && mxCt.includes('{c.unrouted ? " · no route distance yet, so transport is not counted" : ""}') && mxCt.includes("title={c.basis || undefined}")
    && code.includes("function Matrix({ meta, who, editTarget, vehLang, access, initialCost, initialTarget })"));
  ok("🔴 no carbon arithmetic in the browser: no factor, no × or ÷ 1000, no sum or difference of the server's tCO2e fields; the gaps are the server's",
    !/emissions_kg_co2e_per_km|kg_per_km|_factor|\* ?1000|\/ ?1000|0\.93939|7\.80307|19\.55376|1\.01398/.test(ctc + mxCt)
    && !/_t\s*[-+*/]\s*[\w(+]/.test(ctc + mxCt) && !/[-+*/]\s*(?:s|c|t|ct\.status|ct\.target)\.\w+_t\b/.test(ctc + mxCt)
    // NARROWED 11 Oct 2026 (R2): the words come from the server's verdict (on_target_*), not a comparison with the approved plan
    && ctc.includes("ctGap(s.on_target_as_forecast, s.gap_as_forecast_t)") && ctc.includes("ctGap(s.on_target_with_decisions, s.gap_with_decisions_t)"));
  // REVERSED 11 Oct 2026 (R2, one "on target" rule decided on the server; the % is held to 6 dp, so there is no rounding to absorb).
  // It asserted CT_ROUND and the Dashboard's own band (|gap| ≤ 0.05% of the plan, whatever the mode).
  ok("...the pages compare nothing: no band, no CT_ROUND anywhere; 'on target' is the server's on_target_* and the side is the gap's sign",
    !code.includes("CT_ROUND") && !/Math\.abs\(gap\)\s*<=/.test(code) && ctc.includes("function ctGap(on, gap){")
    && ctc.includes("if(on == null || gap == null) return null;") && ctc.includes('if(on) return "on target";')
    && fs.readFileSync(path.join(ROOT, "backend", "carbon_target.py"), "utf8").includes("ON_TARGET_TOL_T = 0.05"));
  // NARROWED 11 Oct 2026 (one way of saying the target on all four pages): a cap reads "a fixed cap of" everywhere (the toggle
  // shows on every page), a gap carries its unit, a team code's figures say whose lines they are and its target is the scheme's
  ok("⭐ the contract's words: the two modes, as forecast and with the agreed decisions, on / over / under the target",
    ctc.includes("`Target: ${pct} below the approved plan = ${ctT(s.target_t)} tCO2e`")
    && ctc.includes("`Target: a fixed cap of ${ctT(t.cap_t)} tCO2e (${pct} below the approved plan when it was set)`")
    // REVERSED 13 Oct 2026 (each team its share of the target, the user's 12 Oct decision): a team code's line said
    // "for the whole scheme, not split by team"; it now names its own share (the server's target_t and share_pct)
    && ctc.includes("return `Target for ${ctYour()}: ${ctT(s.target_t)} tCO2e, ${(+s.share_pct).toFixed(1)}% of ${of}`;")
    && ctc.includes("const of = t.mode === \"cap\" ? `the scheme's fixed cap of ${ctT(t.cap_t)} tCO2e` : `the scheme's target (${pct} below the approved plan)`;")
    && ctc.includes("have no share of it while the agreed decisions do not fit the plan`;") && !ctc.includes("ctSplit")
    && ctc.includes("`As forecast${on}: ${ctT(s.approved_t)} tCO2e${g1 ? \", \" + g1 : \"\"}`")
    && ctc.includes("`With the agreed decisions${on}: ${ctT(s.with_decisions_t)} tCO2e${g2 ? \", \" + g2 : \"\"}`")
    && ctc.includes("s.invalid ? (dash ? `With the agreed decisions${on}: —` : s.invalid)")
    && ctc.includes('${gap > 0 ? "over" : "under"} the target') && ctc.includes("pct = `${(+t.pct_below).toFixed(1)}%`"));
  ok("⭐ the same three things on the Dashboard, Forecasts, Submit forecast and the big screen: the target line and both figures, from one pair of helpers",
    (ctc.match(/ctTargetLine\(ct\)/g) || []).length >= 4 && (ctc.match(/ctProgress\(ct(, true)?\)/g) || []).length >= 4
    && ctc.includes("return `${ctTargetLine(ct)} · ${p1} · ${p2}`;") && ctc.includes("<div className=\"ct-line\">{p1} · {p2}</div>")
    && !ctc.includes("approved plan now") && !ctc.includes("the scheme's cut") && ctc.includes("with the agreed decisions: \" + g2"));
  ok("...Submit forecast prints the server's sentence under its line when the decisions no longer apply",
    _mxc.includes("{ct && ctOk(ct) && ct.status.invalid && <div className=\"w-full ct-note\">{ct.status.invalid}</div>}"));
  ok("...the Dashboard's strip offers the Carbon planner whether a target is set or not",
    (ctc.match(/\{onOpen && <button type="button" className="btn-sec" onClick=\{\(\) => onOpen\("carbon"\)\}>Open the Carbon planner<\/button>\}/g) || []).length === 2);
  ok("🔴 the Dashboard's subtitle names a team, never its id (it printed the raw id; on main too)",
    code.includes('(ipt === "none" ? "no " + TEAM().toLowerCase() : teamText(ipt))') && !code.includes('(ipt === "none" ? "no " + TEAM().toLowerCase() : ipt)'));
  ok("...all-in said once where transport-only figures sit: the strip names the Transport carbon card, the big-screen figure the group it joins",
    ctc.includes('const CT_ALLIN = "All-in: making the material, transport and waste disposal";')
    // NARROWED 11 Oct 2026 (the review: a team code read "your team's lines only" and "on the whole approved plan" about the same figures)
    && ctc.includes("{CT_ALLIN}, on {ctTeam(ct) ? `the approved plan on ${ctYour()}` : \"the whole approved plan\"}. The Transport carbon card above counts transport only.")
    && ctc.includes('CT_ALLIN + ". The other carbon figures here are transport only"') && ctc.includes("s.approved_transport_t"));
  ok("...no target says who sets it; a team code reads its own lines in the tenant's word (a cap is not compared), never a team id",
    // NARROWED 11 Oct 2026 (one "no target" sentence, CT_NONE + CT_WHO, on all four pages; a team code's figures are never compared
    // with the scheme's target in either mode, so "with the scheme's cut applied to them" is REVERSED)
    ctc.includes('const CT_NONE = "No carbon target set yet.";') && ctc.includes('const CT_WHO = "A planner sets it in the Carbon planner.";')
    && (ctc.match(/\{CT_NONE\} \{CT_WHO\}/g) || []).length === 2 && (ctc.match(/`\$\{CT_NONE\} \$\{CT_WHO\}`/g) || []).length === 2
    && !/No carbon target set yet\. A planner|No scheme carbon target|No carbon target is set yet/.test(code)
    && ctc.includes("const ctYour = () => `your ${TEAM().toLowerCase()}'s lines`;") && ctc.includes('ct.status.scope === "team"')
    // REVERSED 13 Oct 2026 (each team its share): "The target is for the whole scheme, so they are not compared with it." and
    // ctSplit ("not split by team") are gone; the note says whose lines and how the share is split
    && ctc.includes("against their share of the scheme's target: the target split by each ${TEAM().toLowerCase()}'s plan with the agreed decisions. The shares add up to the target.")
    && !ctc.includes("so they are not compared with it") && !ctc.includes("with the scheme's cut applied to them.")
    && !ctc.includes("not split by") && !/\.ipt\b|IPT ?[1-6]|teamName\(|teamText\(/.test(ctc + mxCt));
  ok("...the agreed decisions are listed for a scheme code only, collapsed (a team code's GET still carries them: this is wording, not a lock)",
    ctc.includes("{!ctTeam(ct) && words.length > 0 && (") && ctc.includes('<details className="ct-more">') && ctc.includes("const words = t.lever_words || [];"));
  ok("🔴 the target's words: tCO2e with a plain 2, none of the banned words, no small, uppercase or colour-only text",
    !/CO₂/.test(ctc + mxCt) && /tCO2e/.test(ctc) && /tCO2e/.test(mxCt)
    && !/\b(secure|trusted by|testimonials?|real-time|optimi[sz]\w*|predict\w*|telematics|live tracking|compliant|NH-approved|trucks?)\b/i.test(ctc + mxCt)
    && !/\bAI\b/.test(ctc + mxCt) && !/text-xs|text-\[(9|10|11|12)(\.\d)?px\]|uppercase/.test(ctc + mxCt) && !/style=\{\{ ?color/.test(ctc + mxCt));
  ok("...its colours and sizes are tokens in <style>: 14 px lines, 13 px notes, no new Tailwind colour utility to remap for the dark look",
    /\.ct-strip\{background:var\(--surface\);border:1px solid var\(--line\);/.test(html) && /\.ct-line\{font-size:14px;[^}]*color:var\(--ink\)/.test(html)
    && /\.ct-note\{font-size:13px;[^}]*color:var\(--muted\)/.test(html)
    && !/\b(?:bg|text|border)-(?:white|black|slate|gray|red|amber|green|emerald|blue)\b/.test(ctc + mxCt) && !/\b(?:bg|text|border)-\[/.test(ctc + mxCt));
}

// ---- 11 Oct 2026: Gate arrivals on the Dashboard ----------------------------------------------
// Source-level. What they prove: the panel is one block before the carbon target's (so the carbon
// slice's pins keep their shape), the Dashboard reads GET /api/gates/arrivals?month=N in its OWN read
// keyed on the panel's month, the browser derives nothing (no ceil, no ÷ 60, no payload), the words are
// the contract's ("if arrivals are spread evenly", red only and always with a word), teams reach the
// screen through teamText, and the six cards / five sections / eight charts / four big-screen sections
// are untouched. Not covered here: the loaded states (render_frontend.js, from fixtures/gate_arrivals.json),
// the read, a failed read and the month change (dom_frontend.js). Not covered anywhere: a browser, the live server.
{
  const g0 = src.indexOf("// ---- 11 Oct 2026: Gate arrivals on the Dashboard");
  const g1 = src.indexOf("// ---- 11 Oct 2026: the carbon target on the Dashboard, Forecasts and Submit forecast");
  const gaSrc = g0 > 0 && g1 > g0 ? src.slice(g0, g1) : "";
  const gac = gaSrc.split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  const _dbc = code.slice(code.indexOf("function Dashboard("), code.indexOf("function DashboardToday("));
  const _dbW = _dbc.slice(_dbc.indexOf("{!wall ? ("), _dbc.indexOf("      ) : (\n        <>\n"));
  const _dbWl = _dbc.slice(_dbc.indexOf("      ) : (\n        <>\n"));
  const ctSrc = src.slice(g1, src.indexOf("function Dashboard("));
  const gaIdsStripped = gac.replace(/key=\{g\.gate_id\}|data-ga-gate=\{g\.gate_id\}/g, "");
  ok("⭐ GATE ARRIVALS: one block before the carbon target's, holding the panel and its word helpers",
    gaSrc.length > 1500 && gac.includes("function GateArrivalsPanel({ ga, err, month, months, onMonth })")
    && gac.includes("const gaMonthToday = (months) => {") && gac.includes("const gaFlagWord = (g) =>")
    && ctSrc.startsWith("// ---- 11 Oct 2026: the carbon target") && !ctSrc.includes("GateArrivalsPanel"));
  // NARROWED 11 Oct 2026 (review): the read is also skipped on the big screen, where the panel is not rendered
  ok("🔴 the Dashboard reads it in its OWN GET, guarded by initialGates and by wall, keyed on tick, the month and wall; nothing in the block fetches",
    /fetch\(`\$\{API\}\/gates\/arrivals\?month=\$\{gaMonth\}`\)[\s\S]{0,260}\}, \[tick, gaMonth, wall\]\);/.test(_dbc)
    && /if\(initialGates\) return;\n\s*if\(wall\) return;\n\s*let live = true;\n\s*setGaErr\(false\);/.test(_dbc)
    && _dbc.includes("const [ga, setGa] = useState(initialGates || null);") && _dbc.includes("if(initialGates) return;")
    && _dbc.includes("{ if(live) setGaErr(true); }") && !/fetch\(/.test(gac) && !/gates\/arrivals[^`]*`,/.test(_dbc)
    && (_dbc.match(/fetch\(`\$\{API\}\/gates\/arrivals/g) || []).length === 1);
  // NARROWED 14 Oct 2026 (the user took the recommendation): the panel moved from under the carbon strip to under the
  // four charts, so the charts are on the first screen at 1920 x 1080; still before the first collapsed section
  ok("⭐ the panel sits under the four key charts and before the first collapsed section; the six cards, five sections, eight charts are untouched",
    _dbW.includes("<GateArrivalsPanel ga={ga} err={gaErr} month={gaMonth} months={months} onMonth={setGaMonth} />")
    && _dbW.indexOf("<GateArrivalsPanel") > _dbW.indexOf("<CarbonTargetStrip") && _dbW.indexOf("<GateArrivalsPanel") < _dbW.indexOf('<details className="dash-more"')
    && _dbW.indexOf("<GateArrivalsPanel") > _dbW.indexOf("<ChartCanvas config={costCfg} />")
    && _dbW.indexOf("<GateArrivalsPanel") > _dbW.indexOf('<div className="dash-charts" data-dash-charts="1">')
    && (_dbW.match(/<Card label=/g) || []).length === 6 && (_dbW.match(/<details className="dash-more"/g) || []).length === 5
    // 13 Oct 2026 (W5): narrowed — the five sections no longer carry onToggle={onMore} (see the W5 block)
    && (_dbW.match(/<ChartCanvas config=/g) || []).length === 8 && (_dbW.match(/onToggle=\{onMore\}/g) || []).length === 0);
  ok("the hooks sit before the early returns (React #310)",
    _dbc.indexOf("const [ga, setGa]") > 0 && _dbc.indexOf("const [ga, setGa]") < _dbc.indexOf("if(err) return")
    && _dbc.indexOf("const [gaMonth, setGaMonth] = useState(() => (initialGates && initialGates.month) || gaMonthToday(months));") < _dbc.indexOf("if(err) return")
    && _dbc.indexOf("fetch(`${API}/gates/arrivals") < _dbc.indexOf("if(err) return"));
  ok("🔴 the words: 'if arrivals are spread evenly', 'Queue likely', 'Spacing holds', 'No check-in time typed', 'coming to load', lorries not trucks; none of the banned words; no small, uppercase or colour-only text",
    gac.includes('const GA_SPREAD = "if arrivals are spread evenly";') && gac.includes('"Queue likely"') && gac.includes('"Spacing holds"')
    && gac.includes('"No check-in time typed"') && gac.includes("Coming to load") && gac.includes('"not typed"') && gac.includes("min a lorry")   // 13 Oct 2026 (W6, narrowed): "Coming to load a day" is a details label
    // 11 Oct 2026 (review): a pending-only gate (gap null) says so, before the check-in test, and never "one every —"
    && gac.includes('g.gap_minutes == null ? "No approved arrivals" : (g.gate_minutes == null ? "No check-in time typed" : "Spacing holds")')
    // 13 Oct 2026 (W6, narrowed): the cell reads "2.6 min"; the full sentence is in the details
    && gac.includes('{g.gap_minutes == null ? "No approved arrivals." : `One every ${gaMin(g.gap_minutes)} ${GA_SPREAD}.`}') && gac.includes('{g.gap_minutes == null ? "none" : gaMin(g.gap_minutes)}')
    && gac.includes("all {TEAMS().toLowerCase()} together") && !/every \{TEAMS\(\)/.test(code)
    && gac.includes("Pending lines appear as a note until they are approved, then in the figures.")
    && gac.includes("lorries a day at each gate") && gac.includes("The gate arrivals did not load.")
    && !/\b(secure|trusted by|testimonials?|real-time|optimi[sz]\w*|predict\w*|telematics|live tracking|compliant|NH-approved|trucks?|booking|peak hour)\b/i.test(gac)
    && !/\bAI\b/.test(gac) && !/text-xs|text-\[(9|10|11|12)(\.\d)?px\]|uppercase/.test(gac) && !/style=\{\{ ?color/.test(gac));
  // REVERSED 14 Oct 2026 (bundle G, W17, the user's D42 follow-up): two steps, each always with a word — red "Over gate
  // capacity" (the 11 Oct red rule, renamed) and amber "Queue likely" at 85 % (the gold token, RowStatus "warn"); no green tick
  ok("🔴 always with a word: red 'Over gate capacity' ('bad'), amber 'Queue likely' ('warn', the gold token) and grey otherwise; no tick",
    gac.includes('<RowStatus word={gaFlagWord(g)} tone={gaTone(g)} />') && !/"ok"/.test(gac)
    && code.includes('const gaTone = (g) => g.flag === "red" ? "bad" : g.flag === "amber" ? "warn" : "none";')
    && gac.includes('<RdItem t="Status" wide bad={g.flag === "red"}>{g.reason}</RdItem>') && !gac.includes("title={g.reason}")
    && code.includes('g.flag === "red" ? "Over gate capacity" : g.flag === "amber" ? "Queue likely"') && gac.includes('"data-ga-flag": g.flag || "none"'));
  ok("the browser derives nothing: no division, ceil or payload arithmetic in the block; it formats the server's fields",
    !/Math\.ceil|\/ *60|payload|\* *60|working_days *[*\/]|[*\/] *working_days/.test(gac)
    // NARROWED 11 Oct 2026 (review): `unbaked_note` was a field the server never sends; the block renders only the contract's
    && ["arrivals_per_day", "laden_per_day", "empty_per_day", "gap_minutes", "gate_minutes", "per_team", "origin_share_note", "pending_per_day", "pending_lines"].every(f => gac.includes(f))
    && !gac.includes("unbaked"));
  ok("teams reach the screen through teamText only; no id is rendered",
    gac.includes("teamText(t)") && gac.includes("teamText(t.team)") && !/g\.gate_id\}|location_id\}|scope\}|fallthrough_routes/.test(gaIdsStripped)
    && !/IPT ?[1-6]/.test(gac) && gac.includes("{TEAMS().toLowerCase()}"));
  ok("the month select uses the Dashboard's month words (monthLabelAbs) and defaults to today's month clamped to the horizon",
    gac.includes("monthLabelAbs(i, startYear)") && gac.includes("Math.max(1, Math.min(n,") && gac.includes('aria-label="Month"')
    && gac.includes("onChange={e => onMonth(+e.target.value)}"));
  ok("the states are data attributes the DOM and render harnesses read: error / none / set, each root a guide anchor",
    gac.includes('data-gate-arrivals="error"') && gac.includes('data-gate-arrivals={state}') && gac.includes('const state = gates.length === 0 ? "none" : "set";')
    && (gac.match(/data-guide="dash-gates"/g) || []).length === 2 && gac.includes('if(!ga) return err'));
  ok("the empty state is the EmptyState family (kind none) and the error line copies the carbon strip's shape",
    gac.includes('<EmptyState kind="none" title={`No approved lines in ${ga.label}`}')
    && gac.includes('<div className="ct-strip ga-strip" data-gate-arrivals="error" data-guide="dash-gates"><span className="ct-line">The gate arrivals did not load.</span></div>'));
  ok("the CSS is tokens: 14 px table text, --ink / --line, no Tailwind colour in the block",
    /\.ga-table\{[^}]*font-size:14px;[^}]*color:var\(--ink\)/.test(html) && /\.ga-table th\{font-size:14px/.test(html) && /\.ga-table td\{font-size:14px/.test(html)
    && /\.ga-sel\{font-size:14px/.test(html) && !/\b(?:bg|text|border)-(?:white|black|slate|gray|red|amber|green|emerald|blue)\b/.test(gac) && !/\b(?:bg|text|border)-\[/.test(gac));
  // 11 Oct 2026 (review): under 720 px the header row is hidden, so each cell carries its column's label (the phone test)
  ok("on a phone every figure cell carries its column's label: data-label on the four figure cells and the ::before rule in the media query",
    // 13 Oct 2026 (W6, narrowed): the 720 px rule became the shared .rd-table cards below 768 px
    ["Arrivals a day", "Average gap", "Check-in a lorry", "Status"].every(l => gac.includes(`data-label="${l}"`))
    && /@media \(max-width:767px\)\{[\s\S]*?\.rd-table>thead\{display:none;\}[\s\S]*?\.rd-table tr\.rd-row>td\[data-label\]::before,\.rd-table tr\.rd-card>td\[data-label\]::before\{content:attr\(data-label\);/.test(html)
    && gac.includes('<table className="ga-table rd-table" data-rd-table="gates">'));
  const gsGa = (src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1];
  ok("the guide names the panel and the anchor exists",
    gsGa.includes('{ anchor: "dash-gates", title: "Gate arrivals.", body: "Lorries a day at each gate, every team together, and the average gap if arrivals are spread evenly." },')
    && src.includes('data-guide="dash-gates"'));
  // 13 Oct 2026 (W3, narrowed): the footnote's gate sentence moved: the read and the rule to the technical guide (T1, T3),
  // the rule in plain words to the panel's info box
  ok("the gate arrivals read and how the figure is made: the technical guide and the panel's info box",
    _tg.includes("<code>GET /api/gates/arrivals?month=N</code>") && _tg.includes("The gap is the shift's minutes ÷ arrivals, an average with no hourly")
    // NARROWED 14 Oct 2026 (bundle G, W17): the info box's how-to now names the gate's open minutes and the peak bands
    && _tg.includes("all teams summed at the gate a lorry arrives by")
    && src.includes("Capacity = the gate's open minutes (its hours less any no-delivery peak bands, else the shift) ÷ its check-in minutes a lorry. Averages, no peak hour.")
    && _tg.includes("<code>backend/gate_hours.py</code>") && _tg.includes("<strong>Queue likely</strong> (amber)")
    && src.includes('<h3 className="ct-h">Gate arrivals<InfoTip id="dash.gates" /></h3>') && !_dbBody.includes("every {TEAMS()"));
  ok("the big screen is unchanged: still four sections, and the panel is not on it",
    // 14 Oct 2026 (narrowed): five sections now (More charts); the panel is still not on it
    // 17 Oct 2026 (narrowed): six sections (the Simulation); the Gate arrivals panel is still not on it
    !_dbWl.includes("<GateArrivalsPanel") && (_dbWl.match(/<WallSection show=\{sectionShown\(/g) || []).length === 6
    && (src.match(/\{ key: "(?:today|kpis|charts|stock)",/g) || []).length === 4);
}

// ---- 16 Oct 2026 (S3): the busiest hour on the Gate arrivals panel ----------------------------------------------------
// Source-level. What they prove: the "Gate by gate" table carries a sixth column, "Busiest hour", read from the server's
// `busiest_hour` (sim.py's average working day) and formatted only; the details line says the hour and what the gate can
// check in an hour; the server's note is printed under the table. Not covered here: the loaded rows (render_frontend.js).
{
  const b0 = src.indexOf("// ---- 11 Oct 2026: Gate arrivals on the Dashboard");
  const b1 = src.indexOf("// ---- 11 Oct 2026: the carbon target on the Dashboard, Forecasts and Submit forecast");
  const gb = src.slice(b0, b1).split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  const gbW = gb.slice(gb.indexOf("const gaBusyCell"), gb.indexOf("function GateArrivalsPanel"));
  ok("⭐ S3: the gate table has a sixth column, Busiest hour, with its phone label, and the details row spans six",
    gb.includes('<th scope="col" className="num">Busiest hour</th><th scope="col">Status</th>')
    && gb.includes("colSpan={6}") && !gb.includes("colSpan={5}")
    && ["Arrivals a day", "Average gap", "Check-in a lorry", "Busiest hour", "Status"].every(l => gb.includes(`data-label="${l}"`)));
  ok("S3: the cell and the details line format the server's busiest_hour (lorries, hour, hours, per_hour); nothing is worked out",
    gbW.includes('const gaBusyCell = (b) => b && b.lorries ? `${b.lorries} at ${b.hour}` : "—";')
    && gb.includes("{gaBusyCell(g.busiest_hour)}") && gb.includes('<RdItem t="Busiest hour" wide>{gaBusyWords(g.busiest_hour)}</RdItem>')
    && gbW.includes("`The gate can check in ${gaN1(b.per_hour)} an hour.`") && gbW.includes("No check-in time typed, so nothing is compared.")
    && gbW.length > 200 && !/Math\.(ceil|floor|round|max)\(|\/ *60|\* *60/.test(gbW));
  ok("S3: the server's note on where the busiest hour comes from is printed under the notes",
    gb.includes('{ga.busiest_note && <div className="ct-note" data-ga-busy-note="1">{ga.busiest_note}</div>}')
    && gb.indexOf("data-ga-busy-note") > gb.indexOf("(ga.notes || []).map("));
  ok("S3: no banned word and no 'peak hour' in the new words",
    !/\b(secure|real-time|optimi[sz]\w*|predict\w*|telematics|live tracking|trucks?|peak hour)\b/i.test(gbW));
}

// ---- 16 Oct 2026 (S7): the Simulation on the staff Dashboard ----------------------------------------------------------
// Source-level. What they prove: the section sits under Gate arrivals on the desk Dashboard only (not the big screen),
// folded and read on first open with one GET; it writes nothing and keeps nothing (no storage, no address: D86); the
// figures are the server's (the browser draws positions and counts what it draws, nothing else); dots not icons (D81);
// its own Mapbox instance, never removed; no new script; no hourly HERE switch (D92); the holding area greyed; the words.
// Not covered here: the rendered section (render_frontend.js), the reads and the clock (dom_frontend.js), a browser.
{
  const s0 = src.indexOf("// ---- 16 Oct 2026 (S7): the Simulation on the staff Dashboard ----");
  const s1 = src.indexOf("function CommitMap({ meta, bucket, tick, lines, title, height, flush, fill }){");
  const simSrc = s0 > 0 && s1 > s0 ? src.slice(s0, s1) : "";
  const simc = simSrc.split("\n").map(l => l.replace(/^\s*\/\/.*$/, "")).join("\n");
  const fn = (name, next) => simSrc.slice(simSrc.indexOf(`function ${name}(`), next ? simSrc.indexOf(next) : undefined);
  // 17 Oct 2026: the panel ends where the big screen's SimWall begins (same block)
  const mapSrc = fn("SimMap", "const SIM_TL_LEFT"), panelSrc = fn("SimulationPanel", "// ---- 17 Oct 2026: the Simulation on the BIG SCREEN");
  const _dbS = code.slice(code.indexOf("function Dashboard("), code.indexOf("function DashboardToday("));
  const _dbSW = _dbS.slice(_dbS.indexOf("{!wall ? ("), _dbS.indexOf("      ) : (\n        <>\n")), _dbSWl = _dbS.slice(_dbS.indexOf("      ) : (\n        <>\n"));
  ok("⭐ S7: one block before CommitMap holding the panel, its player, map, timeline, scenario, table and phone list",
    simSrc.length > 20000 && ["function SimulationPanel({ meta, months, phone, initial })", "function SimPlayer({ meta, D, store, scenario, open })", "useEffect(() => { if(!open) setPlaying(false); }, [open]);",
      "function SimMap({ meta, D, store, frame })", "function SimTimeline({ D, t, onSeek })", "const SimScenario = React.memo(function SimScenario(",
      "const SimTable = React.memo(function SimTable(", "function SimPhoneList({ D })", "function simFrame(D, legs, t)", "function simQS(month, sc, legs)"].every(f => simSrc.includes(f)));
  ok("⭐ S7: under Gate arrivals on the desk Dashboard, before the folded sections; never on the big screen",
    _dbSW.includes("<SimulationPanel meta={meta} months={months} phone={phone} initial={initialSim} />")
    && _dbSW.indexOf("<SimulationPanel") > _dbSW.indexOf("<GateArrivalsPanel") && _dbSW.indexOf("<SimulationPanel") < _dbSW.indexOf('<details className="dash-more"')
    && !_dbSWl.includes("<SimulationPanel") && (code.match(/<SimulationPanel /g) || []).length === 1);
  ok("⭐ S7: folded, read on FIRST OPEN with one GET of /api/sim/day (the lines once a month), keyed on open, the month and the scenario",
    panelSrc.includes('<details className="dash-more" data-sim="1" open={open || undefined} onToggle={e => setOpen(e.currentTarget.open)}>')
    && panelSrc.includes("if(!open) return;") && panelSrc.includes("fetch(`${API}/sim/day?${simQS(month, sc, wantLines)}`)") && panelSrc.includes("}, [open, month, scKey]);")
    && panelSrc.includes("const wantLines = !phone && !(store && store.month === month);") && (panelSrc.match(/fetch\(/g) || []).length === 1
    // NARROWED 17 Oct 2026: the block holds the big screen's SimWall too, with its own one read (the plain month, with the lines)
    && (simc.match(/fetch\(/g) || []).length === 2 && fn("SimWall", "function CommitMap(").includes("fetch(`${API}/sim/day?month=${month}&legs=1`)"));
  ok("🔴 S7 (D86): nothing written, nothing kept, nothing in the address — no method, no storage, no history, no location in the block",
    !/method:|localStorage|sessionStorage|history\.|location\.|postJSON|navigator\.clipboard/.test(simc));
  ok("⭐ S7: the scenario reaches the server only as the query its parser reads (hours, check_in, bands, pour_*, legs=1)",
    ["`hours=${encodeURIComponent(\"all=\" + sc.all[0] + \"-\" + sc.all[1])}`", "`check_in=${encodeURIComponent(g + \"=\" + sc.check_in[g])}`",
     "`bands=${sc.bands ? \"on\" : \"off\"}`", "`pour_gate=${encodeURIComponent(p.gate)}`", "`pour_m3_per_load=${encodeURIComponent(p.mpl)}`", 'q.push("legs=1")'].every(t => simSrc.includes(t)));
  ok("🔴 S7: the browser works out no figure: the table and the cards print the server's fields; no capacity, share, wait or rounding of a day here",
    ["g.busiest", "g.pct", "g.capacity", "g.minutes_lost", "g.bottleneck_at", "g.most_waiting", "g.longest_wait", "g.late", "g.per_hour", "g.panel_per_day", "D.checks.table_equals_arrivals", "D.checks.largest_panel_difference"].every(f => simSrc.includes(f))
    // NARROWED 17 Oct 2026: "* 100" no longer matches "* 1000" (the big screen's hold in milliseconds); a percentage still does
    && !/60 \/ |\* 100(?!0)|\/ g\.check_in|open_minutes \//.test(simc)
    // the one ceil is the timeline's first hour tick (drawing)
    && (simc.match(/Math\.ceil/g) || []).length === 1 && simc.includes("for(let h = Math.ceil(s0 / 60); h <= Math.floor(s1 / 60); h++)"));
  ok("⭐ S7 (D85): the timeline's red mark is the server's bottleneck (the first wait longer than the check-in), said in words",
    simSrc.includes("{g.bottleneck_at != null") && simSrc.includes("bottleneck from {simHM(g.bottleneck_at)} · up to {g.most_waiting} waiting")
    && simSrc.includes("none longer than the {+g.check_in} min check-in"));
  ok("⭐ S7 (D81): lorries are dots (one circle layer, laden filled, empty hollow, mixers orange, waiting red); no icons",
    mapSrc.includes('m.addLayer({ id: "sim-lorries", type: "circle", source: "sim-lorries"') && !/icon-image|loadImage|addImage/.test(mapSrc)
    && mapSrc.includes('"laden", tok("--sim-lorry", "#2563EB"), "pour", tok("--sim-mixer", "#E8590C"), "#FFFFFF"')
    && /:root\{--sim-lorry:#2563EB;--sim-mixer:#E8590C;\}/.test(html) && /html\[data-theme="dark"\]\{--sim-lorry:#5B8FF0;--sim-mixer:#E8681E;\}/.test(html));
  ok("🔴 S7: its own Mapbox instance (CommitMap's pattern), never removed; the only .remove() is a waiting badge's marker; no new script",
    (mapSrc.match(/new window\.mapboxgl\.Map\(/g) || []).length === 1 && (mapSrc.match(/\.remove\(\)/g) || []).length === 1 && mapSrc.includes("try { x.m.remove(); } catch(e){}")
    // no new third-party script: the page loads the same six scripts it loaded on main ba295a4
    && !/<script|createElement\("script"\)/.test(simSrc) && (html.match(/<script[^>]*src=/g) || []).length === 6);
  ok("⭐ S7: the drawing reads the server's plan: each lorry along its own leg at the parts' speeds, waiting lorries 25 m apart in the gate's one lane",
    simSrc.includes("for(const p of parts){ if(el <= p[5]) return p[0] + (el - p[4]) * p[2]; }") && simSrc.includes("const SIM_QUEUE_M = 25;")
    && simSrc.includes("Object.keys(lanes).forEach(g => lanes[g].sort((x, y) => x.start - y.start));") && simSrc.includes("leg.len_m - Math.max(0, q) * SIM_QUEUE_M"));
  ok("⭐ S7 (D83): about 60 s a day at 1×, ½× to 4×, Play / Pause / Restart, a jump slider; the timeline click jumps too",
    simSrc.includes("const SIM_PLAY_SECONDS = 60;") && simSrc.includes('const SIM_SPEEDS = [["0.5", "½×"], ["1", "1×"], ["2", "2×"], ["4", "4×"]];')
    && simSrc.includes('playing ? "Pause" : (t >= s1 ? "Play again" : "Play")') && simSrc.includes(">Restart</button>")
    && simSrc.includes('aria-label="Jump to a time of day"') && simSrc.includes("onClick={click}"));
  ok("⭐ S7: the words — staff only, a planning view, congestion not modelled; the holding area greyed for V1; no hourly HERE switch (D92)",
    simSrc.includes(">Staff only · never on the public map<") && simSrc.includes(">Planning view, not a record of what happened<")
    && simSrc.includes(">Congestion on the public road is not modelled<") && simSrc.includes('<input type="checkbox" disabled /><span>Holding area: lorries wait off the highway</span>')
    && simSrc.includes("Comes with holding areas (V1).") && !/\bHERE\b/.test(simc) && !/hour of day|hourly drive/i.test(simc));
  ok("🔴 S7: no banned word and no word-rule word on screen; lorries never trucks; teams through teamText; the tenant's distance unit and speed",
    // GeoJSON's own key (geometry) and Mapbox's token setting are code, not words on a screen
    !/\b(bake[ds]?|cached|geometry|server|endpoint|token|real-time|live tracking|telematics|optimi[sz]\w*|predict\w*|trucks?|secure|booking)\b/i.test(simc.replace(/accessToken|mapbox_token|geometry: \{|\.geometry\b/g, ""))
    && simSrc.includes("teamText(x)") && simSrc.includes("${Math.round(speed(h.speed_kph))} ${SPD()}") && simSrc.includes("${fmtDist(h.length_km, 1)} ${DU()}")
    && simSrc.includes("D.mixer.vehicle_label") && !/IPT ?[1-6]/.test(simSrc));
  ok("S7: below 768 px one card a gate, read-only, and the desktop note; the scenario controls are not there",
    panelSrc.includes("? <><div className=\"ct-note\" data-sim-phone=\"1\">The map, the playback and the what-if controls open on a desktop.</div><SimPhoneList D={D} /></>")
    && !fn("SimPhoneList", "function SimulationPanel(").includes("<input"));
  // 17 Oct 2026 (found on live): the pour's gates and default are the server's (working sites only); the gate access roads
  // are not listed with the haul roads, and the screen says so in one line
  const scnSrc = fn("SimScenario", "const gateBandWords");
  ok("⭐ S7 fix: the pour's gate list and default are the server's (D.pour_gates, D.pour_default); no site to pour at says so; no list worked out here",
    scnSrc.includes("const sites = D.pour_gates || [];") && scnSrc.includes("gate: p.gate || D.pour_default || \"\"")
    && !scnSrc.includes("origin_share_note") && !scnSrc.includes("(sites[0] || {}).gate_id")
    && scnSrc.includes('data-sim-no-pour-site="1">No site to pour at: a pour goes to a location of type Compound or Site (Data → Locations).<'));
  ok("S7 fix: one quiet line under the haul roads when gate access roads were left out (the server's count)",
    panelSrc.includes('{D.access_roads_hidden > 0 && <p className="ct-note" data-sim-access-hidden="1">Gate access roads are not listed ({D.access_roads_hidden}): lorries still cross them at their typed speed.</p>}'));
  // 17 Oct 2026: the big screen's sixth section (SimWall) and the one-screen layout of this section
  const wallSrc = fn("SimWall", "function CommitMap(");
  const wallTop = simSrc.slice(simSrc.indexOf("// ---- 17 Oct 2026: the Simulation on the BIG SCREEN"), simSrc.indexOf("function SimWall("));
  ok("⭐ SIM BIG SCREEN: the sixth section is last (key sim), wrapped like the others, and plays SimWall with this display's month, the pass, the loop and the refresh",
    _dbS.includes('<WallSection show={sectionShown(5)} divider={wall && wallLayout === "all"} title={DASH_SECTIONS[5].title}>')
    && _dbS.includes('<SimWall meta={meta} month={simMonth} show={wall && sectionShown(5)} pass={simPass} loop={wallLayout !== "rotate"} fill={fill} tick={tick} />')
    && _dbSWl.indexOf("<SimWall ") > _dbSWl.indexOf("<ChartCanvas config={splitCfg} />") && !_dbSW.includes("<SimWall "));
  ok("⭐ SIM BIG SCREEN: in Rotate the Simulation stays its whole day (a day at 1× + a 5 s hold), whatever the rotate setting; the others keep theirs",
    wallTop.includes("const SIM_WALL_HOLD_S = 5;") && wallTop.includes("const SIM_WALL_SECONDS = SIM_PLAY_SECONDS + SIM_WALL_HOLD_S;")
    && _dbS.includes('const dwellNow = (DASH_SECTIONS[wallSection] || {}).key === "sim" ? SIM_WALL_SECONDS : rotateSecs;'));
  ok("⭐ SIM BIG SCREEN: each pass starts the day again (simPass counts the section coming round); the play loop restarts on it",
    _dbS.includes("useEffect(() => { if(wall && sectionShown(simIdx)) setSimPass(p => p + 1); }, [wall, wallLayout, wallSection]);")
    && wallSrc.includes("useEffect(() => { if(dRef.current){ tRef.current = dRef.current.window.start; setT(dRef.current.window.start); } }, [pass]);")
    && wallSrc.includes("}, [show, D, loop, pass]);") && wallSrc.includes("if(!loop){ tRef.current = n; setT(n); raf = null; return; }"));
  ok("🔴 SIM BIG SCREEN (D86): the month is a per-display setting in localStorage, said in a comment to be NOT a saved or shared scenario; nothing goes in the address",
    wallTop.includes('const SIM_WALL_MONTH_KEY = "modus_dash_sim_month";') && /NOT a saved or shared scenario: D86 stands/.test(wallTop)
    && _dbS.includes("localStorage.setItem(SIM_WALL_MONTH_KEY, v)")
    && /A display setting in this browser's localStorage, like the rotate time — NOT a saved or shared\n\s*\/\/ scenario \(D86 stands/.test(src)
    && _dbS.includes('aria-label="Simulation month on this display"') && _dbS.includes('<option value="">this month</option>')
    && !/localStorage|sessionStorage|history\.|location\./.test(wallSrc));
  ok("SIM BIG SCREEN: the bar keeps one line — the month choice only while the Simulation is on screen (or in All sections), and no costing range beside it",
    (_dbS.match(/\(wallLayout === "all" \|\| wallSection === simIdx\) && </g) || []).length === 2
    && _dbS.includes("{fill && wallSection !== simIdx && <span className=\"dash-wallbar-note\" title="));
  // 17 Oct 2026 (the user: "entry gate and empty lorry icons look too similar")
  ok("⭐ SIM: an entry gate never reads as a lorry — a bullseye (radius 7, thick ink rim, ink centre) against the empty lorry's small blue ring (radius 4); the key draws the same",
    mapSrc.includes('m.addLayer({ id: "sim-gates", type: "circle", source: "sim-gates", paint: { "circle-radius": 7, "circle-color": "#FFFFFF", "circle-stroke-color": "#1E293B", "circle-stroke-width": 2.5 } });')
    && mapSrc.includes('m.addLayer({ id: "sim-gates-dot", type: "circle", source: "sim-gates", paint: { "circle-radius": 2.5, "circle-color": "#1E293B" } });')
    && mapSrc.includes('"circle-radius": ["match", ["get", "k"], "wait", 4.5, 4]') && mapSrc.includes('"circle-stroke-color": ["match", ["get", "k"], "wait", tok("--red", "#DC2626"), "pour", "#FFFFFF", tok("--sim-lorry", "#2563EB")]')
    && /\.sim-dot-gate\{background:radial-gradient\(circle,#1E293B 0 2\.5px,#FFFFFF 3px\);border:2\.5px solid #1E293B;width:15px;height:15px;\}/.test(html)
    && /\.sim-dot-empty\{background:#FFFFFF;border:2px solid var\(--sim-lorry\);\}/.test(html));
  ok("SIM: the map's key is a named group (an aria-label on a plain div is not allowed: the UI audit's aria-prohibited-attr)",
    mapSrc.includes('<div className="sim-legend" role="group" aria-label="Map key">') && !mapSrc.includes('<div className="sim-legend" aria-label='));
  ok("SIM: the map's key names the concrete mixer only on a day with a pour",
    mapSrc.includes('{D.pour && <div><i className="sim-dot sim-dot-pour" aria-hidden="true"></i>'));
  ok("🔴 SIM BIG SCREEN: no scenario controls and no table on the TV; it reads the plain month (no pour) only while shown",
    !/<input|<select|<button|SimScenario|SimTable|pour_gate|onHours|onCheckIn/.test(wallSrc)
    && wallSrc.includes("if(!show) return;") && wallSrc.includes("fetch(`${API}/sim/day?month=${month}&legs=1`)") && wallSrc.includes("no pour"));
  ok("SIM BIG SCREEN: it fills the TV in Rotate / One section (.dash-fill) with the map large, the clock and Gates now beside it, the timeline under the map",
    /\.sim-wall\{display:grid;[^}]*grid-template-areas:"map side" "tl side";\}/.test(html) && /\.dash-wall\.dash-fill \.sim-wall-fill\{height:100%;grid-template-rows:minmax\(0,1fr\) auto;\}/.test(html)
    && /\.sim-wall-fill \.sim-map\{height:100%;\}/.test(html) && /\.sim-wall-clock\{font-size:clamp\(/.test(html)
    && wallSrc.includes('<div className={"sim-wall" + (fill ? " sim-wall-fill" : "")} data-sim-wall="1">'));
  ok("⭐ SIM ONE SCREEN: from 1024 px the map and its timeline sit left, the clock / Gates now / scenario beside them; the table and the haul roads fold away (closed)",
    fn("SimPlayer", "const SimScenario").includes('<div className="sim-main">\n          <SimMap meta={meta} D={D} store={store} frame={f} />')
    && /<div className="sim-main">[\s\S]{0,700}<SimTimeline D=\{D\} t=\{t\}/.test(fn("SimPlayer", "const SimScenario"))
    && /@media \(min-width:1024px\)\{\.sim-grid\{grid-template-columns:minmax\(0,1fr\) 300px;align-items:start;\}\n\s*\.sim-main \.sim-map\{height:clamp\(260px,calc\(100vh - 420px\),680px\);\}\}/.test(html)
    // found in Chrome: in the flex column the map's box shrank to nothing (align-self:start); it stretches across its column
    && /\.sim-main>\.sim-map-wrap\{align-self:stretch;\}/.test(html)
    && panelSrc.includes('<details className="sim-fold" data-sim-fold="table"><summary>Busiest hour at each gate</summary>')
    && panelSrc.includes('<details className="sim-fold" data-sim-fold="haul"><summary>Haul roads</summary>') && !/data-sim-fold="[a-z]+" open/.test(panelSrc));
  ok("S7: the info box entry (≤ 40 words) and the controls are named for a screen reader",
    /"dash\.sim": \{ title: "Simulation", text: "[^"]+", *\n? *how: "[^"]+", tech: "t1-gates" \}/.test(src)
    && ["Simulation month", "Playback speed", "Every gate opens at", "Every gate closes at", "Pour gate", "Pour starts at", "Busiest hour at each gate"].every(a => simSrc.includes(`aria-label="${a}"`)));
}

// ---- 11 Oct 2026 — the guide update: the tour text that was wrong or stale ------------------------
// Source-level. What they prove: the dashboard, look-ahead, data and forecast steps say what the pages show
// today, on the same anchors; the old promises are gone. Not covered: how a card reads on screen (dom_frontend.js
// walks the welcome and the dashboard tour in a DOM).
{
  const gsU = (src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1];
  const gfU = (src.match(/const GUIDE_FORECAST_STEPS = \[[\s\S]*?\];/) || [""])[0];
  const stepsOf = (k) => (gsU.match(new RegExp(`\\n  ${k}: \\[([\\s\\S]*?)\\n  \\],`)) || ["", ""])[1];
  const dashU = stepsOf("dashboard"), laU = stepsOf("lookahead"), dataU = stepsOf("data");
  // NARROWED 11 Oct 2026 (guide v2.1 review): "everything below follows" was not true (this week's plan and the
  // carbon target read their own, unfiltered data), so step 1 now names the two exceptions
  ok("guide update: the dashboard tour starts on the filters and points to today's folded section, on the same anchors plus the gate step",
     dashU.includes('{ anchor: "page-header", title: "The plan at a glance.", body: "Pick the months, team and status here; the cards and charts follow, except this week\'s plan and the carbon target. Today\'s figures are under This week and today, further down." }')
     // NARROWED 11 Oct 2026 (gate arrivals): a fifth step, anchor dash-gates, sits before Big screen
     && (dashU.match(/anchor: "/g) || []).length === 5 && dashU.includes('anchor: "dash-gates"') && dashU.includes('anchor: "dash-wall"'));
  // NARROWED 11 Oct 2026 (guide v2.1 review): the step titled "Six cards." named five; it names all six now, and says
  // which one is the Look-ahead's rather than "for the lines in view"
  ok("...the cards step names the six cards; the carbon step says transport only and points to the target strip; cost is in its chart",
     dashU.includes('title: "Six cards."') && dashU.includes("Material in view, deliveries a day, vehicles needed, delivered against plan and transport carbon for the lines in view, and this week's plan from the Look-ahead.")
     && dashU.includes('title: "Carbon."') && dashU.includes("Transport carbon counts transport only.") && dashU.includes("Cost is in the Cost over time chart."));
  ok("🔴 ...and the old dashboard promises are gone (today in the header, the seven-day number, cost on the cards)",
     !/title: "Today\."|seven-day|Cost and carbon\.|Planned cost, the modelled fair price/.test(dashU));
  ok("the look-ahead tour: this week by day with the next week switch; flags without seasonal windows; actuals on Account",
     laU.includes('title: "This week, by day."') && laU.includes("Use the next week switch to plan ahead")
     && laU.includes("Flags never block anything.") && laU.includes("On Account, type what really moved last week.")
     && (laU.match(/anchor: "lookahead-(tabs|flags)"/g) || []).length === 3);
  ok("🔴 ...and the old look-ahead claims are gone (next week by default, seasonal windows and mass limits as flags, the seven-day accuracy)",
     !/Next week, by day|seasonal windows|mass limits|seven-day/.test(laU));
  ok("the data tour: routes are routed for the lorry, not 'HGV-legal'; zones are areas, caps and windows live elsewhere",
     dataU.includes('title: "Routes", body: "are routed for a lorry of the vehicle\'s weight and size, out laden and back empty, and drawn on the map."')
     && dataU.includes("Lorry caps are set on each route, seasonal windows in Config.") && !/HGV-legal|carry the rules/.test(dataU));
  ok("the forecast steps: a quantity in m³, tonnes or vehicles; Pending until approved; the public map",
     gfU.includes("with a quantity for each month in m³, tonnes or vehicles.") && gfU.includes("A new line is Pending until a planner approves it.")
     && gfU.includes("the Look-ahead and the public map.") && !/the tonnes by month|from submitted to approved/.test(gfU));
  ok("🔴 the changed tour copy keeps the house words: lorry, never truck; no team id",
     !/\btrucks?\b/i.test(gsU + gfU) && !/IPT/.test(gsU + gfU));
  // 11 Oct 2026 (late, guide v2.1 review) — the corrected statements
  ok("🔴 guide v2.1 review: the dashboard tour no longer says everything follows the filters",
     !/everything below follows/.test(dashU) && /except this week's plan and the carbon target/.test(dashU));
  ok("🔴 ...the actuals step says a line that REACHES 98% of its plan is delivered (clashes.HOLD_BAND: actual >= 0.98 x plan), not 'within'",
     laU.includes("A line that reaches 98% of its plan counts as delivered.") && !/within 98%/.test(laU));
}

// ---- 11 Oct 2026 (late) — guide v2.1 review: the on-screen text that contradicted the guide -------------
{
  ok("🔴 the Locations subtitle says deleting a site deletes its routes (network.delete_location), as the confirm does",
     src.includes("drag a marker to move it; deleting a site also deletes every route that uses it.")
     && !src.includes("a site that a route uses cannot be deleted")
     && src.includes("This also removes any routes that use it."));
  ok("🔴 ...the planner's Forecasts subtitle and the Data legend call the map the public map, and the Dashboard by its name",
     src.includes("approved lines feed the public map, the Look-ahead and the Dashboard.")
     && src.includes("Material colouring lives on the Dashboard and the public map.")
     && !/approved lines feed the route map|the KPI cards\."|forecasting dashboard and the public route map/.test(src));
}

// ---- 12 Oct 2026 (C4, map review §2.6, mockup 9) — the Monthly bulletin on the Dashboard -----------------
// Source-level. What it proves: the menu sits on the Dashboard's working view (not the big screen), the PDF is
// fetched from /api/bulletin/month.pdf with the month (the access code rides on the wrapped fetch), the page
// link is /bulletin/?month=N in a new tab, the default month is the calendar month inside the programme, the
// words meet the 14 px floor, and nothing is computed in the browser. Not covered here: the click and the
// error line (dom_frontend.js), the server (test_bulletin.py, http_smoke.py), a real browser download.
{
  const bm = code.slice(code.indexOf("function BulletinMenu({ months })"), code.indexOf("function BulletinMenu({ months })") + 3200);
  const bmc = bm.slice(0, bm.indexOf("\n}\n") + 3);
  ok("⭐ BULLETIN: one BulletinMenu component, outside the Dashboard's own body (the carbon-target pins slice it), used ONCE, in the working view's actions",
    bmc.length > 500 && (code.match(/<BulletinMenu months=\{months\} \/>/g) || []).length === 1
    // NARROWED 14 Oct 2026 (D9): the big-screen button after it is not drawn on a phone
    && _dbBody.includes("            <BulletinMenu months={months} />\n          </>}\n          {/* 14 Oct 2026 (D9): no big screen from a phone (a site-office TV is not a phone) */}\n          {!phone && <button type=\"button\" data-guide=\"dash-wall\"")
    && !_dbBody.includes("function BulletinMenu(") && code.indexOf("function BulletinMenu(") > code.indexOf("function DashboardStockChart("));
  ok("⭐ BULLETIN: the PDF is fetched from /api/bulletin/month.pdf for the chosen month and saved as bulletin-YYYY-MM.pdf",
    bmc.includes("const r = await fetch(`${API}/bulletin/month.pdf?month=${m}`);") && bmc.includes("const blob = await r.blob();")
    && bmc.includes('a.download = `bulletin-${months.start_year + Math.floor((m - 1) / 12)}-${String((m - 1) % 12 + 1).padStart(2, "0")}.pdf`;')
    && bmc.includes("URL.revokeObjectURL(a.href)"));
  ok("⭐ BULLETIN: the HTML page opens in a new tab at /bulletin/?month=N (the staff cookie opens it; no code in the address)",
    bmc.includes('<a href={`/bulletin/?month=${m}`} target="_blank" rel="noopener">Open the page</a>') && !/access_code|X-Access-Code|code=/.test(bmc));
  ok("BULLETIN: the month defaults to this calendar month, clamped to the programme; every month is offered by its label",
    bmc.includes("const cur = Math.min(months.count, Math.max(1, (now.getFullYear() - months.start_year) * 12 + now.getMonth() + 1));")
    && bmc.includes("const [m, setM] = useState(cur);") && bmc.includes("monthLabelAbs(i, months.start_year)"));
  ok("BULLETIN: a failed PDF says so under the button in the server's words, never silently",
    bmc.includes('setErr("The bulletin could not be made: " + (e.message || e));') && bmc.includes('<div className="bm-err" role="alert">{err}</div>')
    && bmc.includes('{busy ? "Making the bulletin…" : "Download the PDF"}'));
  ok("🔴 BULLETIN: nothing is computed in the browser — no working-day divisor, no movements arithmetic, no team id",
    !/working_days|\/ 22|vehicle_loads|two_way|IPT/.test(bmc));
  ok("🔴 BULLETIN: the 14 px floor for the menu's words (its label, its link, its error line)",
    /\.bulletin-menu label span\{font-size:14px;\}/.test(html) && /\.bulletin-menu \.row-menu-list a\{[^}]*font-size:14px;/.test(html)
    && /\.bulletin-menu \.bm-err\{[^}]*font-size:14px;/.test(html));
  ok("BULLETIN: the house words — lorry movements, never truck; none of the banned words in the menu",
    // NARROWED 12 Oct 2026 (browser check): the demo's October bulletin is THREE pages (19 routes), so the menu no
    // longer promises two; the PDF is two pages or more (test_bulletin: "at least two A4 pages")
    bmc.includes("The month's lorry movements as a PDF and a web page, from the approved plan") && !bmc.includes("two-page PDF")
    && !/\btrucks?\b|real-time|live tracking|telematics|optimi[sz]e|predict|\bsecure\b/i.test(bmc) && !/\bAI\b/.test(bmc));
}

// ---- 13 Oct 2026: D45 — the demo bar, Option A (the user's pick from the dev brief) and W1, no map over Estonia ----
{

  const _lum = (hex) => { const v = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const _cr = (a, b) => { const x = _lum(a), y = _lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const root = (html.match(/:root\{([\s\S]*?)\n  \}/) || ["", ""])[1];
  const tok = (n) => ((root.match(new RegExp("--" + n + ":(#[0-9A-Fa-f]{6})")) || [])[1] || "");
  const darkBlock = (html.match(/html\[data-theme="dark"\]\{([\s\S]*?)\n  \}/) || ["", ""])[1];
  ok("⭐ D45: the demo bar's tokens are Option A — light grey #F1F5F9, red #B91C1C text, a #DC2626 rule, a red tag with white text",
     tok("demo-bg") === "#F1F5F9" && tok("demo-fg") === "#B91C1C" && tok("demo-rule") === "#DC2626"
     && tok("demo-tag-bg") === "#B91C1C" && tok("demo-tag-fg") === "#FFFFFF" && tok("demo-btn-ring") === "#94A3B8",
     [tok("demo-bg"), tok("demo-fg"), tok("demo-rule"), tok("demo-tag-bg")].join(" "));
  ok("🔴 D45 (REVERSED from 11 Oct): no ink-and-amber demo bar is left (no #FBBF24 / #FEF3C7 on a --demo token)",
     !/--demo-[a-z-]+:#(?:FBBF24|FEF3C7)/i.test(html));
  ok("🔴 D45: contrast — the red text on the grey and the white tag text pass 4.5:1, the rule 3:1, the Guide text 4.5:1",
     _cr(tok("demo-fg"), tok("demo-bg")) >= 4.5 && _cr(tok("demo-tag-fg"), tok("demo-tag-bg")) >= 4.5
     && _cr(tok("demo-rule"), tok("demo-bg")) >= 3 && _cr(tok("demo-btn-fg"), tok("demo-btn-bg")) >= 4.5,
     [_cr(tok("demo-fg"), tok("demo-bg")).toFixed(2), _cr(tok("demo-tag-fg"), tok("demo-tag-bg")).toFixed(2)].join(" "));
  ok("D45: the same bar in every look — the dark block redefines no --demo token, so the light bar stands out on the dark page",
     darkBlock.length > 100 && !/--demo-/.test(darkBlock));
  ok("D45: a red DEMO tag before the words, CSS only (the markup the other harnesses pin is unchanged), hidden from screen readers (alt text \"\")",
     /\.demo-bar::before\{content:"DEMO";content:"DEMO" \/ "";flex:none;margin-right:8px;padding:0 6px;border-radius:3px;background:var\(--demo-tag-bg\);color:var\(--demo-tag-fg\);/.test(html));
  ok("D45: the white Guide pill keeps an edge on the light bar (an inset grey ring, no layout change)",
     /\.demo-bar-guide\{[^}]*background:var\(--demo-btn-bg\);box-shadow:inset 0 0 0 1px var\(--demo-btn-ring\);/.test(html));
  // W1
  const ukm = html.match(/\nconst UK_VIEW = \{ center: \[(-?[\d.]+), (-?[\d.]+)\], zoom: (\d+(?:\.\d+)?) \};\n/);
  ok("⭐ W1: one UK_VIEW, inside Great Britain (lon -8..2, lat 50..59), declared at the top level",
     !!ukm && +ukm[1] > -8 && +ukm[1] < 2 && +ukm[2] > 50 && +ukm[2] < 59);
  ok("🔴 W1: no map opens on the old [24.7, 58.5] default, and the location form's placeholders are not 58.5 / 24.7",
     !/24\.7,\s*58\.5/.test(html) && !/placeholder="(?:58\.5|24\.7)"/.test(html)
     && /placeholder="52\.6"/.test(html) && /placeholder="-1\.5"/.test(html));
  // NARROWED 16 Oct 2026 (S7): a third map, the Dashboard's Simulation (SimMap, its own instance like CommitMap), opens
  // on UK_VIEW too, then frames the day's routes
  ok("W1: every map the app creates opens on UK_VIEW (the Look-ahead map, the Routes / Zones map, the Simulation map)",
     (html.match(/center: UK_VIEW\.center, zoom: UK_VIEW\.zoom/g) || []).length === 3
     && (html.match(/new window\.mapboxgl\.Map\(/g) || []).length === 3
     && /function SimMap\(\{ meta, D, store, frame \}\)\{[\s\S]{0,700}new window\.mapboxgl\.Map\(\{ container: div\.current, style: "mapbox:\/\/styles\/mapbox\/light-v11", center: UK_VIEW\.center, zoom: UK_VIEW\.zoom/.test(html));
  const locFetch = (html.match(/fetch\(`\$\{API\}\/locations\/geojson`\)\.then\(r => r\.json\(\)\)\.then\(gj => \{([\s\S]*?)\n    \}\)\.catch/) || ["", ""])[1];
  ok("⭐ W1: the Routes / Zones map frames the scheme's locations the FIRST time they load, once (a ref), finite points only, inside a try",
     /const framedRef = useRef\(false\);/.test(html) && /if\(!framedRef\.current\)\{/.test(locFetch)
     && /\.filter\(c => Array\.isArray\(c\) && isFinite\(c\[0\]\) && isFinite\(c\[1\]\)\)/.test(locFetch)
     && /if\(pts\.length\)\{ framedRef\.current = true; try \{ m\.fitBounds\(boundsOf\(pts\), \{ padding: 60, maxZoom: 12, duration: 0 \}\); \} catch\(e\)\{\} \}/.test(locFetch)
     && (html.match(/framedRef\.current = true/g) || []).length === 1);
}

// ---- 13 Oct 2026 (W6, bundle F): row details on the four busy tables --------------------------------------
// RowDetails, RowStatus, the unit switch, the cards below 768 px; the UI they replaced is gone. The behaviour (clicks,
// the session, the switch, nothing lost, one " · " a cell) is in dom_frontend.js; the layout in the browser matrix.
{
  const rdc = (src.match(/\nfunction RowDetails\([\s\S]*?\n\}\n/) || [""])[0];
  ok("⭐ W6: RowDetails — a native chevron button with aria-expanded and aria-controls, a stopped click, at most two chips, a details row always rendered and hidden while shut",
     rdc.includes('<button type="button" className="rd-chev" aria-expanded={isOpen ? "true" : "false"} aria-controls={did} aria-label={label}')
     && rdc.includes("onClick={(e) => { e.stopPropagation(); onToggle(); }}") && rdc.includes(".filter(Boolean).slice(0, 2)")
     && rdc.includes('<tr className="rd-details" id={did} hidden={!isOpen} data-rd-details={rowKey}>') && rdc.includes('<dl className="rd-dl">{children}</dl>'));
  ok("W6: the open rows are kept per table for the session (sessionStorage modus_rows_<table>); the unit per page for good (localStorage modus_units_<page>), Tonnes by default",
     src.includes('const rdKey = (table) => "modus_rows_" + table;') && /window\.sessionStorage\.setItem\(rdKey\(table\)/.test(src)
     && src.includes('window.localStorage.getItem("modus_units_" + page)') && src.includes('return UNIT_CHOICES.some(c => c[0] === v) ? v : "tonnes";')
     && src.includes('const UNIT_CHOICES = [["loads", "Loads"], ["tonnes", "Tonnes"], ["lorries", "Lorries"]];'));
  // 17 Oct 2026 (UI fix 2, finding 1): the pressed word reads the control's text colour (white on the dark look's orange was 2.33:1)
  ok("UI fix 2 (#1): the pressed Loads / Tonnes / Lorries word is var(--control-fg) on var(--navy), no #fff literal",
     html.includes('.unit-sw-seg button[aria-pressed="true"]{background:var(--navy);color:var(--control-fg);}') && !/\.unit-sw-seg[^\n]*#fff/.test(html));
  ok("W6: the switch is a labelled group of three aria-pressed buttons with its info box, on the Look-ahead, the Dashboard and Forecasts (not Gate arrivals: all lorries)",
     src.includes('<span className="unit-sw-seg" role="group" aria-label="Show the figures as">') && src.includes('aria-pressed={value === k ? "true" : "false"}')
     && src.includes('<InfoTip id="units" />') && ["lookahead", "dashboard", "forecasts"].every(p => src.includes(`useUnits("${p}")`))
     && !/useUnits\("gates"\)/.test(src));
  ok("W6: the status is a word and an icon whose shape says the tone (✓ circle, ! square, ! circle, – circle), never colour alone",
     src.includes('const RS_ICON = { ok: "✓", warn: "!", bad: "!", none: "–" };') && /\.row-st\.rs-warn i\{[^}]*border-radius:3px;/.test(html)
     && src.includes('<span className={"row-st rs-" + t} data-row-status={t}><i aria-hidden="true">{RS_ICON[t]}</i>{word}'));
  ok("⭐ W6: all five tables are row-details tables (Look-ahead, gates, Today, the route table, Forecasts)",
     ["lookahead", "gates", "today", "dashboard", "forecasts"].every(n => src.includes(`data-rd-table="${n}"`))
     && (src.match(/<RowDetails key=/g) || []).length === 5);
  ok("⭐ W6: below 768 px the tables are cards in the brief's order (primary, status, then the figures) and every figure cell carries its label",
     /@media \(max-width:767px\)\{[\s\S]*?\.rd-table tr\.rd-row>td\.rd-primary\{order:0;[\s\S]*?\.rd-table tr\.rd-row>td\.rd-status\{order:1;[\s\S]*?content:attr\(data-label\);/.test(html)
     && /\.rd-table\{min-width:0 !important;/.test(html));
  ok("W6: ROAD LIMIT ranks first among the Look-ahead flags, and the Dashboard and Forecasts read it from the cost lines (`limit`)",
     src.includes("const LA_FLAG_RANK = { LIMIT: 0, RESTRICTION: 1,") && src.includes('const st = r.limit ? { word: "ROAD LIMIT", tone: "bad" }')
     && src.includes('if(lim) return { word: "ROAD LIMIT", tone: "bad", more: 0 };') && src.includes("if(r.limit && !a.limit) a.limit = r.limit;") && src.includes("if(r.limit && !e.limit) e.limit = r.limit;"));
  // removed UI: asserted gone at source level
  ok("🔴 W6 removed: the Look-ahead's ▶/▼ toggle, its open-state object, the Flags column (LineFlags) and the week StatusChip",
     !src.includes('{isOpen ? "▼" : "▶"}') && !src.includes("const [open, setOpen] = useState({});") && !/function LineFlags\(/.test(src)
     && !/function StatusChip\(/.test(src) && !src.includes("<LineFlags") && !src.includes("<StatusChip") && !src.includes("Route · {TEAM().toLowerCase()} · section</th>"));
  ok("🔴 W6 removed: the hover titles D left on the four tables and Today (grid cells, Today rows, the £/t · £/trip split, the gate's reason, the vehicle name)",
     !src.includes("title={`Click to type ${dayName(d.day_date)}'s plan") && !src.includes('title="Confirmed — reopen it to change the plan"')
     && !src.includes("planned today${r.actual != null") && !src.includes('title={c.plannedU ? unitTriple(c.plannedU)') && !src.includes('title={r.plannedU ? unitTriple(r.plannedU)')
     && !src.includes("title={g.reason}") && !src.includes("title={g.vehicle}") && !src.includes("title={`Submitted by ${teamText(g.submittedBy)")
     && !src.includes('title="An actual has been typed for today"') && !src.includes("trips/day per vehicle` : undefined}"));
  ok("🔴 W6 removed: the route table's 'on hover' line and its four moved columns (distance a trip, cycle, lorry-distance, fair per tonne headers)",
     !src.includes("/{DU()} on hover") && !src.includes('onClick={() => setSort("dist")}') && !src.includes('onClick={() => setSort("cycleH")}')
     && !src.includes('onClick={() => setSort("km")}') && !src.includes('onClick={() => setSort("fairPerT")}'));
  ok("🔴 W6 removed: the gate table's laden · coming-to-load line, its notes row and the 720 px rule; the Forecasts cost cell's two stacked figures",
     !src.includes("{gaN1(g.laden_per_day)} laden · {gaN1(g.empty_per_day)} coming to load") && !src.includes('<tr className="ga-notes">')
     && !/@media \(max-width:720px\)\{\.ga-table/.test(html) && !src.includes('<span className="text-slate-400"> · {(+c.fairU.per_t).toFixed(2)}/t</span>'));
  // found by the browser matrix (13 Oct): at 768 px an opened details row was as wide as its table, so on a table that
  // scrolls sideways half of it sat off screen; the gate table had no scroll box and spilled out of its card; at 360 px
  // the Look-ahead's first cell kept its inline 280 px and a long status word did not wrap
  ok("W6: every row-details table sits in a scroll box that is a size container, and a details grid is never wider than that box",
     (src.match(/className="[^"]*overflow-auto[^"]*rd-scroll[^"]*"/g) || []).length === 5 && /\.rd-scroll\{container-type:inline-size;\}/.test(html)
     && /\.rd-dl\{position:sticky;left:0;max-width:min\(100cqw, 1100px\);/.test(html)
     && src.includes('<div className="overflow-auto rd-scroll"><table className="ga-table rd-table" data-rd-table="gates">'));
  ok("W6: the big screen hides the row chevrons as it hides the info boxes (a wall display is not clicked)",
     /\.dash-wall \.ibtn\{display:none;\}\n  \.dash-wall \.rd-chev\{display:none;\}/.test(html));
  ok("W6: in the cards, the first cell drops its inline minimum width, the totals cells too, and a status word wraps",
     /\.rd-table tr\.rd-row>td\.rd-primary\{order:0;text-align:left;display:block;min-width:0 !important;/.test(html)
     && /\.rd-table tr\.rd-card>td\{min-width:0 !important;\}/.test(html) && /\.rd-table \.row-st\{white-space:normal;/.test(html));
  ok("W6: the info box words follow the move: the cost split is 'in the row's details', the commit grid's unit 'chosen above'",
     src.includes("Each figure's per tonne, per trip and per mile or km is in the row's details.") && !src.includes("is in its tooltip")
     && src.includes("in the unit chosen above. In Tonnes, click a day to type its plan"));
}

// ---- 13 Oct 2026 (W3): the word rule, the info box and its dictionary -----------------------
// The rule (notes/w3-w4-inventory-1013.md): no screen says these words; they live in the technical guide.
// Every piece of literal text in the Babel block is walked with the TypeScript parser (comments are not
// text, so they are never read): JSX text, every string and template piece, every attribute. A piece is
// skipped only when it is code, not words: a fetch / storage / JSON call's argument, an object key, a
// comparison or index, an identifier-like token (`route_geometry`, `/admin/...`, `POST`, `geometry-type`).
// Exempt by decision B (13 Oct): the Diagnostics panel, the Config "Everything (JSON)" tab's own words,
// and the phrase "admin token" wherever its field is named.
{
  const BANNED = /(\/api\b|\bendpoints?\b|\bservers?\b|\bJSON\b|\bcached?\b|\bgeometry\b|\bbak(?:e|ed|es|ing)\b|\bunbaked\b|\bre-?bak\w*|\bPOST\b|\bGET\b|\bHTTP\b|localStorage|\bschema\b|\btokens?\b|line-months?)/i;
  const CASED = /\b(POST|GET|JSON|HTTP)\b/;
  const EXEMPT_TEXT = ["Not valid JSON: ", "Everything (JSON)", "Saving from the JSON section sends the text as typed"];
  const sfW = ts.createSourceFile("w.tsx", src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const K = ts.SyntaxKind;
  const compOf = (n) => { for (let p = n.parent; p; p = p.parent) {
    if (ts.isFunctionDeclaration(p) && p.name && /^[A-Z]/.test(p.name.text)) return p.name.text;
    if (ts.isVariableDeclaration(p) && ts.isIdentifier(p.name) && /^[A-Z]/.test(p.name.text) && p.initializer && (ts.isArrowFunction(p.initializer) || ts.isFunctionExpression(p.initializer))) return p.name.text; }
    return "(top)"; };
  const ctxOf = (n) => {
    let e = n; if (n.kind === K.TemplateHead || n.kind === K.TemplateMiddle || n.kind === K.TemplateTail) { e = n.parent; if (e && e.kind === K.TemplateSpan) e = e.parent; }
    const p = e.parent;
    if (ts.isJsxText(n)) return "jsx-text";
    if (p && ts.isJsxAttribute(p)) return "attr:" + p.name.getText();
    if (p && ts.isJsxExpression(p) && p.parent && ts.isJsxAttribute(p.parent)) return "attr:" + p.parent.name.getText();
    if (p && ts.isCallExpression(p)) return "call:" + p.expression.getText().slice(0, 40);
    if (p && ts.isPropertyAssignment(p)) return p.name === e ? "key" : "prop:" + p.name.getText();
    if (p && ts.isElementAccessExpression(p)) return "index";
    if (p && ts.isBinaryExpression(p) && /^(===|!==|==|!=)$/.test(p.operatorToken.getText())) return "compare";
    if (p && ts.isCaseClause(p)) return "compare";
    return K[p.kind]; };
  const pieces = [];
  (function walk(n) {
    const a = n.getStart(sfW), b = n.getEnd();
    let t = null;
    if (n.kind === K.StringLiteral || n.kind === K.NoSubstitutionTemplateLiteral) t = src.slice(a + 1, b - 1);
    else if (n.kind === K.TemplateHead || n.kind === K.TemplateMiddle) t = src.slice(a + 1, b - 2);
    else if (n.kind === K.TemplateTail) t = src.slice(a + 1, b - 1);
    else if (n.kind === K.JsxText && n.getText().trim()) t = n.getText();
    if (t != null) pieces.push({ t, ctx: ctxOf(n), comp: compOf(n), line: src.slice(0, a).split("\n").length });
    ts.forEachChild(n, walk);
  })(sfW);
  const isCode = (p) => {
    const w = p.t.trim();
    if (p.t.includes("?token=") || w.startsWith("/api/")) return true;
    if (["key", "index", "compare"].includes(p.ctx) || /^call:(fetch|api|JSON\.|localStorage|sessionStorage)/.test(p.ctx) || p.ctx.includes("localStorage")) return true;
    if (/^[a-z]+(-[a-z]+)+$/.test(w)) return true;                 // a Mapbox expression name, a CSS word
    if (!/\s/.test(w) && ((p.ctx.startsWith("call:") && /^[a-z_]+$/.test(w)) || /[/_=?&]/.test(w) || ["POST", "GET", "PUT", "DELETE", "PATCH"].includes(w))) return true;
    return false; };
  const banOf = (t) => { const t2 = t.replace(/admin token/gi, ""); const m = t2.match(BANNED); if (!m) return null;
    if (/^(POST|GET|JSON|HTTP)$/i.test(m[0]) && !CASED.test(t2)) return null; return m[0]; };
  const hits = pieces.filter(p => banOf(p.t) && !isCode(p) && p.comp !== "Diagnostics" && !EXEMPT_TEXT.includes(p.t));
  ok(`⭐ W3 word rule: no text a person reads on a staff screen says API / endpoint / server / JSON / cache / geometry / bake / POST / GET / HTTP / localStorage / schema / token / line-month (${pieces.length} pieces read)`,
     pieces.length > 2000 && hits.length === 0,
     hits.slice(0, 8).map(p => `line ${p.line} ${p.comp} [${banOf(p.t)}] ${JSON.stringify(p.t.trim().slice(0, 80))}`).join(" | "));
  ok("...the scan is real: it reads JSX text, titles, aria-labels, placeholders, confirm() and message strings",
     ["jsx-text", "attr:title", "attr:aria-label", "attr:placeholder"].every(c => pieces.some(p => p.ctx === c))
     && pieces.some(p => p.ctx.startsWith("call:confirm")) && pieces.some(p => p.ctx.startsWith("call:setRouteMsg")));
  ok("...and it would catch the old words: the exempt rows are the decided ones only (Diagnostics, the JSON tab's three strings, the admin token)",
     banOf("line-months on a baked route") && banOf("No cached geometry") && banOf("The server did not answer") && !banOf("Admin token")
     && pieces.filter(p => banOf(p.t) && p.comp === "Diagnostics" && !isCode(p)).length >= 1
     && EXEMPT_TEXT.every(x => pieces.some(p => p.t === x)));
  ok("...the internal codes and field names stay (only the words a person reads changed)",
     src.includes('UNBAKED: "NOT ROUTED"') && src.includes("r.baked") && src.includes("excludes_unbaked") && src.includes("D.baked"));

  // the INFO dictionary
  const infoDecl = (() => { let d = null; (function f(n) { if (ts.isVariableDeclaration(n) && n.name.getText() === "INFO") d = n; ts.forEachChild(n, f); })(sfW); return d; })();
  const INFOS = {};
  if (infoDecl && infoDecl.initializer && ts.isObjectLiteralExpression(infoDecl.initializer)) {
    for (const prop of infoDecl.initializer.properties) {
      const key = prop.name.text, e = {};
      for (const q of prop.initializer.properties) e[q.name.getText()] = q.initializer.text;
      INFOS[key] = e;
    }
  }
  const ids = Object.keys(INFOS);
  const used = new Set([...src.matchAll(/<InfoTip id="([^"]+)"/g), ...src.matchAll(/info=\{\{ id: "([^"]+)"/g)].map(m => m[1]));
  const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;
  const guideIds = new Set([...fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").matchAll(/ id="([^"]+)"/g)].map(m => m[1]));
  const techIds = new Set([..._tg.matchAll(/ id="([^"]+)"/g)].map(m => m[1]));
  ok(`⭐ W3 INFO: one dictionary, every entry has a title and a text (${ids.length} entries)`,
     ids.length >= 50 && ids.every(k => INFOS[k].title && INFOS[k].text));
  ok("...every info box on a screen has its entry, and every entry is used (no orphan copy)",
     [...used].every(k => INFOS[k]) && ids.every(k => used.has(k)), [...used].filter(k => !INFOS[k]).concat(ids.filter(k => !used.has(k))).join(", "));
  ok("...each entry's plain text is at most 40 words (the brief's limit; the rest goes in 'how')",
     ids.every(k => words(INFOS[k].text) <= 40), ids.filter(k => words(INFOS[k].text) > 40).join(", "));
  ok("...and no entry breaks the word rule",
     ids.every(k => ["title", "text", "how", "source"].every(f => !banOf(INFOS[k][f] || ""))), ids.filter(k => ["title", "text", "how", "source"].some(f => banOf(INFOS[k][f] || ""))).join(", "));
  ok("...every 'Read more' anchor exists in the user guide, every 'Technical detail' anchor in the technical guide",
     ids.every(k => !INFOS[k].guide || guideIds.has(INFOS[k].guide)) && ids.every(k => !INFOS[k].tech || techIds.has(INFOS[k].tech)) && techIds.has("t1-figures")
     && ids.some(k => INFOS[k].guide) && ids.some(k => INFOS[k].tech),
     ids.filter(k => (INFOS[k].guide && !guideIds.has(INFOS[k].guide)) || (INFOS[k].tech && !techIds.has(INFOS[k].tech))).join(", "));

  // the component (the behaviour is exercised in dom_frontend.js and in a real browser)
  const it = src.slice(src.indexOf("function InfoTip("), src.indexOf("// Chart.js wrapper"));
  ok("⭐ W3 InfoTip: a native button (Enter and Space click it), named 'About: …', with aria-expanded and aria-controls",
     it.includes('<button ref={btn} type="button" className="ibtn" aria-label={`About: ${name}`} aria-expanded={open ? "true" : "false"}')
     && it.includes("aria-controls={panelId}") && !it.includes("onMouseEnter") && !it.includes("onMouseOver") && !it.includes("onKeyDown"));
  ok("...the panel is a non-modal dialog labelled by its title, in title → text → value → how → source → links order",
     it.includes('role="dialog" aria-modal="false" aria-labelledby={panelId + "-t"}')
     && ["<h6 id=", "<p>{e.text}</p>", "info-val", "How it is worked out", "Source: {e.source}", "Read more in the user guide →", "Technical detail →"].every((x, i, a) => it.indexOf(x) > 0 && (i === 0 || it.indexOf(x) > it.indexOf(a[i - 1]))));
  ok("...Esc closes it and gives focus back to the 'i'; an outside click or a touch closes it; one open at a time",
     it.includes('if(ev.key === "Escape") { ev.stopPropagation(); close(true); }') && it.includes("if(refocus && btn.current)")
     && it.includes('document.addEventListener("mousedown", onDown)') && it.includes('document.addEventListener("touchstart", onDown)')
     && it.includes("if(INFO_OPEN && INFO_OPEN.close) INFO_OPEN.close(false);") && /^let INFO_OPEN = null;$/m.test(src));
  ok("...below 640 px it opens as a sheet from the bottom; otherwise it flips above the 'i' when there is no room below",
     it.includes('window.matchMedia("(max-width: 639px)")') && it.includes("is-sheet") && /\.info-pop\.is-sheet\{left:0 !important;right:0 !important;bottom:0 !important;top:auto !important;/.test(html)
     && it.includes("r.bottom + 6 + ph > vh"));
  ok("...it is drawn in a portal (a card's overflow:hidden would clip it) and its click never sorts a column or toggles a <details>",
     it.includes("ReactDOM.createPortal(panel, document.body)") && it.includes("ev.stopPropagation(); ev.preventDefault();"));
  ok("...24 px hit area, 44 px on a touch screen, a focus ring, and hidden on the big screen (a wall display has no pointer)",
     /\.ibtn::after\{content:"";position:absolute;inset:-3px;\}/.test(html) && /@media \(pointer:coarse\)\{\.ibtn::after\{inset:-13px;\}\}/.test(html)
     && /\.ibtn:focus-visible\{outline:2px solid var\(--navy\);/.test(html) && /\.dash-wall \.ibtn\{display:none;\}/.test(html));

  // what W3 removed from the screens (source-level, so a revert is caught)
  ok("🔴 W3 removed: no cursor:help and no hover title on a Dashboard card, figure or Today figure",
     !/cursor-help/.test(src) && !/cursor:help/.test(html)
     && ["const Card = ({ label, value, sub, info, tone })", "const Fig = ({ value, label, sub, info, tone })", "const Big = ({ value, label, sub, info, tone })"].every(x => src.includes(x))
     && !/<Card [^>]*\btitle=/.test(src) && !/<Fig [^>]*\btitle=/.test(src) && !/<Big [^>]*\btitle=/.test(src));
  ok("🔴 ...the Dashboard shows the date range once (the kicker): the subtitle that repeated it and the scope is gone",
     !_dbBody.includes("Strategic planning view") && !_dbBody.includes("subtitle={`") && _dbBody.includes('<PageHeader title="Dashboard" kicker={`${rangeLabel} ·'));
  ok("🔴 ...the dot-separated hints are gone from the screens: the stockpile chart's formula line, the commit caption's, the Account and Horizon footers",
     !src.includes("balance at the week's end = opening + typed week actuals") && !src.includes("· loads and vehicles in grey · Monday to Friday")
     && !src.includes("Calibrate never fires on save") && !src.includes("No day columns here.") && !src.includes("Type what came out of each stockpile this week. Opening ="));
  ok("🔴 ...and the Forecasts cost column and the carbon target line carry an info box, not a title",
     // 13 Oct 2026 (W6, narrowed): the cost cell became two columns; the info box rides on the Planned header
     src.includes('<th scope="col" className="num">Planned ({CUR()})<InfoTip id="fc.cost" /></th>') && !src.includes("Hover a figure for")
     && !src.includes('data-carbon-target="set" title='));
  ok("W3 §1: the passages that left the screen read in plain words (each one's old text is in the technical guide)",
     src.includes("Needed to change routes, locations and zones. Remembered in this browser.") && !src.includes("ADMIN_TOKEN")
     && src.includes("Routing is not set up on this deployment yet") && !src.includes("HERE_API_KEY")
     && src.includes("The admin token is taken from the field at the top of this page.") && !src.includes("taken from the bake panel")
     && src.includes("Saved on its own: the page's Save button does not save the target rate") && src.includes("from Config → Vehicles, plus")
     && src.includes("Codes are checked by Wayscope") && src.includes('confirm("Clear ALL routes? Locations are kept. This cannot be undone.")'));
}

// ---- 13 Oct 2026 (W5, bundle E): charts fill every screen ------------------------------------------------------
{
  const _cc = (src.match(/function ChartCanvas\([\s\S]*?\n\}\n/) || [""])[0];
  const _db = (src.match(/function Dashboard\(\{[\s\S]*?\n\}\n/) || [""])[0];
  ok("W5: every chart box is position:relative and sized by CSS clamp(), two sizes; the canvas is the box's only child",
     /\.chart-box\{position:relative;width:100%;min-width:0;height:clamp\(200px,28vh,420px\);\}/.test(html)
     && /\.chart-box\.is-lg\{height:clamp\(220px,32vh,480px\);\}/.test(html)
     // (14 Oct: a third size, "fill", for a chart that takes its card on the big screen)
     && _cc.includes('<div ref={box} className={"chart-box" + (size === "lg" ? " is-lg" : size === "fill" ? " is-fill" : "")} data-chart-box="" style={height ? { height } : undefined}><canvas ref={ref}></canvas></div>'));
  // 14 Oct 2026 (narrowed): the gate chart joins the stockpile chart — its height follows its rows too (one a gate)
  // NARROWED 14 Oct 2026 (bundle G, W7): + the CLP section's three row charts (routes, sites, councils), one row each too
  ok("W5: 🔴 no Dashboard chart has a fixed px height any more (only the stockpile, gate and CLP row charts, whose height follows their rows)",
     (src.match(/<ChartCanvas [^>]*height=/g) || []).length === 5
     && src.includes('height={Math.max(150, 46 * capped(C.route_caps.rows).length + 50)} />') && src.includes('height={Math.max(150, 46 * capped(C.site_caps.rows).length + 50)} />')
     && src.includes('height={Math.max(170, 40 * (C.councils.rows || []).length + 80)} />') && src.includes("<ChartCanvas config={gaCfg} height={Math.max(180, 46 * rowsC.length + 60)} />") && /<ChartCanvas config=\{cfg\} height=\{Math\.max\(wall \? 220 : 160, 36 \* bars\.length \+ 40\)\} \/>/.test(src)
     && !/height=\{wall \? \d+ : \d+\} \/>/.test(_db.replace(/<CommitMap[^>]*>/g, "")));
  ok("W5: a chart is built only once its box has a size; a ResizeObserver resizes it and moves the legend across 768 / 1024 px",
     _cc.includes("const ro = new ResizeObserver(") && _cc.includes("if(!sized || !ref.current || !window.Chart) return;")
     && _cc.includes('if(want && lg.position !== want){ lg.position = want; c.update("none"); } else c.resize();')
     && _cc.includes("ro.disconnect(); cancelAnimationFrame(raf);") && _cc.includes("}, [JSON.stringify(config), theme, accent, sized]);"));   // (W16 the same evening: + accent)
  ok("W5: the rules by width: legend under the plot below 768 px, a doughnut's on the right only from 1024 px; labels 18 characters, no rotation; DPR at most 2",
     /const CHART_LABEL_MAX = 18;/.test(src) && /if\(vw < 768\) return "bottom";/.test(src)
     && /if\(type === "doughnut" \|\| type === "pie"\) return vw >= 1024 \? \(asked \|\| "right"\) : "bottom";/.test(src)
     && /const ticks = \{ \.\.\.\(ax\.ticks \|\| \{\}\), maxRotation: 0, autoSkip: true \};/.test(src)
     && /o\.devicePixelRatio = Math\.min\(\(typeof window !== "undefined" && window\.devicePixelRatio\) \|\| 1, 2\);/.test(src));
  ok("W5: the working view is up to 1680 px wide (not max-w-7xl); the big screen's Charts section fills the height when shown alone",
     _db.includes('"max-w-[1680px]")}>') && !_db.includes('"max-w-7xl"')
     // 14 Oct 2026 (narrowed): EVERY section fills in Rotate / One section, not only Charts
     && _db.includes('const fill = wall && wallLayout !== "all";') && _db.includes('(fill ? " dash-fill" : "")')
     && /\.dash-wall\.dash-fill\{height:100%;display:flex;flex-direction:column;\}/.test(html)
     && /\.dash-wall\.dash-fill \.wall-charts\{height:100%;grid-auto-rows:minmax\(0,1fr\);\}/.test(html));
  ok("W5: the four charts: one column, 3 + 2 from 1024 px, three columns from 1600 px (top routes down the right); More charts 1 / 2 / 4",
     /@media \(min-width:1600px\)\{\n\s*\.dash-charts\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\);grid-template-areas:"demand progress top" "cost cost top";\}/.test(html)
     && ["c-demand", "c-top", "c-progress", "c-cost"].every(c => _db.includes(`<div className="card p-4 chart-card ${c}">`))
     && _db.includes('<div className="dash-charts" data-dash-charts="1">') && _db.includes('<div className="pt-3 dash-more-charts">')
     && _db.includes('<div className="wall-charts">') && (_db.match(/className="card p-4 chart-card/g) || []).length === 16);
  // NARROWED 16 Oct 2026 (S7): two more observers, the Simulation's map (it opens folded at 0 × 0, like the Today map)
  // and its timeline (it redraws to its own width)
  ok("W5: the Today map and the Routes map watch their own container (the dispatch they relied on is gone); so do the Simulation's map and timeline",
     (src.match(/new ResizeObserver\(/g) || []).length === 5 && /const ro = typeof ResizeObserver !== "undefined" \? new ResizeObserver\(doResize\) : null;/.test(src)
     && (src.slice(src.indexOf("function SimMap("), src.indexOf("function SimPlayer(")).match(/new ResizeObserver\(/g) || []).length === 2);
  // REVERSED 14 Oct 2026 (D9, the mobile shell): below 768 px there is NO rail (not even icons); the bottom tab bar
  // (PhoneTabs) takes its place. The same one breakpoint; the over-the-page "peek" and its CSS are gone.
  ok("W5 → D9 (14 Oct): below 768 px the rail is not drawn at all; the peek state, its class and its CSS are gone",
     /const NARROW_Q = "\(max-width: 767px\)";/.test(src) && /const railShown = railOpen;/.test(src)
     && /\{!narrow && <aside data-guide="rail" className=\{"rail shrink-0/.test(src)
     && !/railPeek|setRailPeek|rail-peek/.test(src) && !/\.rail\.rail-peek\{/.test(html)
     && /onClick=\{\(\) => setPage\(it\.id\)\}/.test(src));
}

// ---- 13 Oct 2026 (W16, bundle E; D39): the four accents ----------------------------------------------------------
// The series colours of every accent × look are worked out from the <style> exactly as the browser cascades them
// (:root, then the dark block, then the accent's block), and checked with the method the 10 and 11 Oct palettes were
// chosen by (notes/colour-system-1010.md, notes/bundle-e-plan-1013.md): neighbouring series must stay apart for a
// colour-blind reader (Machado 2009 protan/deutan simulation, OKLab distance × 100, at least 8) and for everyone
// (at least 15), and every series must stand 3:1 against the chart's surface. Formulas: OKLab (Ottosson 2020), WCAG 2.
{
  const css = html.match(/<style>([\s\S]*?)<\/style>/)[1];
  const blockOf = (sel) => { const i = css.indexOf(sel + "{"); if (i < 0) return null; const j = css.indexOf("}", i); return css.slice(i + sel.length + 1, j); };
  const toks = (b) => { const o = {}; (b || "").replace(/--([a-z0-9-]+):([^;]+);/g, (_, k, v) => { o[k] = v.trim(); }); return o; };
  const ROOT = toks(blockOf(":root")), DARK = toks(blockOf('html[data-theme="dark"]'));
  const acc = (k) => toks(blockOf(`:root:not([data-theme="dark"])[data-accent="${k}"]`));
  // (Blue and Blue shades share one dark block: `html[data-theme="dark"][data-accent="blue"],html[…="blue-shades"]`)
  const DARK_BLUE = 'html[data-theme="dark"][data-accent="blue"],html[data-theme="dark"][data-accent="blue-shades"]';
  const accD = (k) => (k === "blue" || k === "blue-shades") ? toks(blockOf(DARK_BLUE)) : toks(blockOf(`html[data-theme="dark"][data-accent="${k}"]`));
  const eff = (k, dark) => dark ? { ...ROOT, ...DARK, ...(k === "orange" ? {} : accD(k)) } : { ...ROOT, ...(k === "orange" ? {} : acc(k)) };
  const KEYS = ["orange", "blue", "blue-shades", "orange-shades"];
  const series = (t) => ["chart-1", "chart-2", "chart-3", "chart-4", "chart-5"].map(n => t[n].toUpperCase()).filter(c => c !== t["chart-none"].toUpperCase());
  // colour maths
  const lin = (h) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const lum = (h) => { const [r, g, b] = lin(h); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const M = { protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
              deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]] };
  const sim = (h, k) => { const v = lin(h); if (!k) return v; return M[k].map(r => Math.max(0, Math.min(1, r[0] * v[0] + r[1] * v[1] + r[2] * v[2]))); };
  const oklab = (v) => { const l = Math.cbrt(0.4122214708 * v[0] + 0.5363325363 * v[1] + 0.0514459929 * v[2]), m = Math.cbrt(0.2119034982 * v[0] + 0.6806995451 * v[1] + 0.1073969566 * v[2]),
                            s = Math.cbrt(0.0883024619 * v[0] + 0.2817188376 * v[1] + 0.6299787005 * v[2]);
                      return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]; };
  const dE = (a, b, k) => { const p = oklab(sim(a, k)), q = oklab(sim(b, k)); return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };
  // the pairs a reader compares: neighbours in a stack, and 1 against 4 (the cost chart: planned beside the model)
  const worst = (pal) => { let cvd = 1e9, nv = 1e9; const P = []; for (let i = 1; i < pal.length; i++) P.push([i - 1, i]); if (pal.length >= 4) P.push([0, 3]);
    for (const [i, j] of P) { cvd = Math.min(cvd, dE(pal[i], pal[j], "protan"), dE(pal[i], pal[j], "deutan")); nv = Math.min(nv, dE(pal[i], pal[j])); } return { cvd, nv }; };
  ok("W16: the ACCENTS block exists with a light and a dark block for each of the three alternatives, and touches no status colour",
     ["blue", "blue-shades", "orange-shades"].every(k => blockOf(`:root:not([data-theme="dark"])[data-accent="${k}"]`)) && !!blockOf(DARK_BLUE)
     && !blockOf('html[data-theme="dark"][data-accent="orange-shades"]') && !blockOf(':root:not([data-theme="dark"])[data-accent="orange"]')
     && !/--(green|gold|red):/.test(css.slice(css.indexOf("ACCENTS-START"), css.indexOf("ACCENTS-END"))));
  ok("W16: 🔴 Orange (the default, the user's pick) IS the look before 13 Oct: the same buttons, links and series in both looks",
     series(eff("orange", false)).join(" ") === "#E8590C #2563EB #0D9488 #7C3AED #A07D34" && series(eff("orange", true)).join(" ") === "#E8681E #5B8FF0 #13A193 #9572EE #B48E3E"
     && eff("orange", false).action === "#C2410C" && eff("orange", false).navy === "#2563EB" && eff("orange", true).action === "#FF8C14");
  ok("W16: Blue primary swaps slots 1 and 2 (the plan blue, delivered orange) and 4 and 5 (the model gold: blue beside violet fails 1–4)",
     series(eff("blue", false)).join(" ") === "#2563EB #E8590C #0D9488 #A07D34 #7C3AED" && series(eff("blue", true)).join(" ") === "#5B8FF0 #E8681E #13A193 #B48E3E #9572EE");
  ok("W16: the shade accents carry FOUR hues and the fifth series is the 'not yet' grey; in Dark each draws its primary's series",
     series(eff("blue-shades", false)).join(" ") === "#1D4ED8 #0891B2 #4F46E5 #0D9488" && series(eff("blue-shades", true)).join(" ") === series(eff("blue", true)).join(" ")
     && series(eff("orange-shades", false)).join(" ") === "#E8590C #9A3412 #A07D34 #BE185D"
     && series(eff("orange-shades", true)).join(" ") === series(eff("orange", true)).join(" "));
  for (const k of KEYS) for (const dark of [false, true]) {
    const t = eff(k, dark), pal = series(t), w = worst(pal), surf = dark ? "#1F2024" : "#FFFFFF";
    ok(`W16 palette ${k} · ${dark ? "dark" : "light"}: neighbours and the plan–model pair apart for a colour-blind reader (≥ 8) and for everyone (≥ 15); every series ≥ 3:1 on the surface`,
       w.cvd >= 8 && w.nv >= 15 && pal.every(c => cr(c, surf) >= 3), `cvd ${w.cvd.toFixed(1)} nv ${w.nv.toFixed(1)} min contrast ${Math.min(...pal.map(c => cr(c, surf))).toFixed(2)}`);
  }
  ok("W16: the brief's own shade ramps would FAIL the same check (kept here so a later copy of them is caught)",
     worst(["#1E3A8A", "#2563EB", "#60A5FA", "#93C5FD", "#BFDBFE"]).nv < 15 && cr("#BFDBFE", "#FFFFFF") < 3
     && worst(["#7C2D12", "#C2410C", "#FF8C14", "#FFB55C", "#FFE0B8"]).nv < 15 && cr("#FFE0B8", "#FFFFFF") < 3);
  // the state, the early script, the picker, the charts
  ok("W16: ACCENTS + applyAccent + useAccent mirror the look; stored as modus_accent (the B6 decision: keys keep the old prefix); unknown → orange",
     /const ACCENTS = \[\n  \["orange",/.test(src) && /const ACCENT = \{ key: "modus_accent", current: "orange", subs: new Set\(\) \};/.test(src)
     && /if\(!ACCENTS\.some\(\(\[k\]\) => k === name\)\) name = "orange";/.test(src) && /try \{ applyAccent\(localStorage\.getItem\(ACCENT\.key\) \|\| "orange", false\); \} catch\(e\)\{ applyAccent\("orange", false\); \}/.test(src)
     && /function useAccent\(\)\{/.test(src));
  ok("W16: 🔴 the remembered look and accent go on <html> in a plain <head> script, BEFORE the CDN scripts and Babel (no flash of the default)",
     html.indexOf('d.setAttribute("data-accent",') > 0 && html.indexOf('d.setAttribute("data-accent",') < html.indexOf("react.production.min.js")
     && /\/\^\(orange\|blue\|blue-shades\|orange-shades\)\$\/\.test\(a\|\|""\)\?a:"orange"/.test(html) && /\/\^\(ink\|light\|dark\)\$\/\.test\(t\|\|""\)\?t:"ink"/.test(html));
  ok("W16: the picker has a second group, Accent, four menuitemradio items in their own class (the three looks stay three)",
     /<h6>Accent<\/h6>\n\s*\{ACCENTS\.map\(\(\[k, label, sw\]\) => \(/.test(src) && src.includes('className={"accent-item" + (accent === k ? " is-on" : "")} data-accent-choice={k}')
     && src.includes("onClick={() => { setAccent(k); setOpen(false); }}"));
  ok("W16: charts rebuild on an accent change without a reload (ChartCanvas and the Dashboard subscribe)",
     (src.match(/const \[accent\] = useAccent\(\);/g) || []).length === 2);
  ok("W16 (D39): every multi-series Dashboard chart names its series on the chart from 768 px; stacked segments have a 2 px surface gap",
     /const SERIES_LABELS = \{ id: "seriesLabels", afterDatasetsDraw\(chart, _args, opts\)\{/.test(src)
     && /if\(plugins\.seriesLabels && plugins\.seriesLabels\.on && vw >= 768\)\{/.test(src)
     && (src.match(/\.\.\.named \}/g) || []).length === 3 && /borderWidth: \{ top: 2 \}, borderColor: SURF, borderSkipped: "start"/.test(src)
     && /ctx\.fillStyle = tok\("--ink", "#1E293B"\);/.test(src));
  ok("W16 (D39): an amber status is a triangle and a red one a diamond beside its word — every .chip-st dot, by the token it is painted with",
     /\.chip-st i\[style\*="--gold"\]\{width:10px;height:9px;border-radius:0;clip-path:polygon\(50% 0,100% 100%,0 100%\);\}/.test(html)
     && /\.chip-st i\[style\*="--red"\]\{width:10px;height:10px;border-radius:0;clip-path:polygon\(50% 0,100% 50%,50% 100%,0 50%\);\}/.test(html));
  ok("W16: 🔴 no hard-coded control blue left in the app's markup — only the map's route and place colours (map data, 29 Sep) and the token blocks",
     !/rgba\(37,99,235,\.(1|08)\)", color: "var\(--navy\)"/.test(src) && !/accentColor: "#2563EB" \}\} \/>\n/.test(src.replace('toggleCat("supplies", cat)} style={{ accentColor: "#2563EB" }} />', ""))
     // NARROWED 16 Oct 2026 (S7): the Simulation's lorry dots read their token --sim-lorry, with #2563EB as the fallback
     // (map data: a lorry, in every accent; the token block holds the value)
     && (src.match(/#2563EB/g) || []).length === (src.match(/const ROUTE_COLOR = "#2563EB";|"Port": "#2563EB"|"circle-stroke-color": "#2563EB"|toggleCat\("supplies", cat\)\} style=\{\{ accentColor: "#2563EB" \}\}|dot: "#2563EB"|s1: "#2563EB"|s2: "#2563EB"|btn: "#2563EB"|C2 = tok\("--chart-2", "#2563EB"\)|tok\("--sim-lorry", "#2563EB"\)/g) || []).length);
}

// ---- 14 Oct 2026: the big screen fills the screen in EVERY section (the user: "the screen still don't fill up on
// rotate"; measured on the branch at 1920 × 1080: Today 67 %, Figures 38 %, Stockpiles 37 %, Charts 98 %). TV-dashboard
// practice (Datadog TV mode, Grafana kiosk, Geckoboard, Microsoft's TV guidance): fit without scrolling, hide the
// chrome, split a crowded screen, nothing that needs a hover, a clock. Browser-measured afterwards: 96–99 % at
// 1366 × 768, 1920 × 1080 and 3840 × 2160, nothing cut off (notes/session-1014-big-screen.md).
{
  const _db = (src.match(/function Dashboard\(\{[\s\S]*?\n\}\n/) || [""])[0];
  const _td = (src.match(/function DashboardToday\([\s\S]*?\n\}\n/) || [""])[0];
  const _sc = (src.match(/function DashboardStockChart\([\s\S]*?\n\}\n/) || [""])[0];
  const _pf = (src.match(/function Portal\([\s\S]*?\n\}\n/) || [""])[0];
  ok("BIG SCREEN: Rotate and One section fill (dash-fill) whatever the section; the shown section takes the height left",
     _db.includes('const fill = wall && wallLayout !== "all";') && _db.includes('(fill ? " dash-fill" : "")')
     && /\.dash-wall\.dash-fill>\[data-wall-section\]:not\(\[hidden\]\)\{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;\}/.test(html)
     && /\.dash-wall\.dash-fill>\[data-wall-section\]>\*\{flex:1 1 auto;min-height:0;\}/.test(html));
  ok("BIG SCREEN: the TV type scale is from the screen height (figures ~6 % and width-capped, labels ~1.8 %, never under 13 px); chart text = height ÷ 74",
     /\.dash-wall\.dash-fill \.fig-val\{font-size:clamp\(2rem,min\(6\.4vh,3\.3vw\),8rem\);/.test(html)
     && /\.dash-wall\.dash-fill \.fig-label\{font-size:clamp\(13px,1\.8vh,30px\);/.test(html)
     && _db.includes("const tf = { size: wall ? Math.max(13, Math.min(30, Math.round(winH / 74))) : 11 };")
     && _db.includes("const named = { seriesLabels: { on: true, size: tf.size } };"));
  ok("BIG SCREEN: Figures is a 2 × 2 grid of tiles; a tile with five figures takes three columns so none is cut off",
     _db.includes('<div className={fill ? "wall-figs" : "grid md:grid-cols-2 xl:grid-cols-4 gap-3"} data-wall-figures="1">')
     && /\.dash-wall\.dash-fill \.wall-figs\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\);grid-auto-rows:minmax\(0,1fr\);/.test(html)
     && /\.wall-figs>\.card>\.grid:has\(>:nth-child\(5\)\)\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\);\}/.test(html));
  ok("BIG SCREEN: Today's figures go 2 × 2, its lines take the rest of the card (never a scrollbar on a TV), the map the whole right column",
     _td.includes('(fill ? " today-figs" : " xl:grid-cols-4")') && _td.includes("today-lines") && _td.includes('lg:col-span-3 today-map')
     && _td.includes("flush fill={fill} />") && /\.dash-wall\.dash-fill \.today-lines\{max-height:none !important;overflow:hidden;\}/.test(html)
     && src.includes('<div ref={mapDiv} style={fill ? { flex: "1 1 auto", minHeight: 0 } : { height: height || 380 }} />'));
  ok("BIG SCREEN: the stockpile chart takes its card, and each bar names its fill in words (no hover on a TV)",
     _sc.includes('(fill ? <ChartCanvas config={cfg} size="fill" /> : <ChartCanvas config={cfg} height={Math.max(wall ? 220 : 160, 36 * bars.length + 40)} />)')
     && _sc.includes('(b.over ? " · over capacity" : b.pct >= 90 ? " · nearly full" : "")') && _sc.includes("plugins: [capLine, barLabels] };")
     && /\.chart-box\.is-fill\{height:100%;min-height:0;\}/.test(html));
  ok("BIG SCREEN: eight charts no longer share one screen — Charts has the four a planner reads first, More charts (5th, added last) the other four, each 2 × 2",
     (_db.match(/<div className="wall-charts">/g) || []).length === 2 && /\{ key: "more",   title: "More charts" \}/.test(src)
     && /@media \(min-width:1024px\)\{\.wall-charts\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\);\}\}/.test(html)
     && _db.includes('[["all", "All sections"], ["rotate", "Rotate"], ["single", "One section"]]') && !_db.includes('"All four"'));
  ok("BIG SCREEN: the rotation shows a line that fills over the section's time and names the next one; no motion when reduced motion is asked for",
     // NARROWED 17 Oct 2026: the line fills over THIS section's time (dwellNow: the Simulation's whole day, else the setting)
     _db.includes('<i key={wallSection + "-" + dwellNow} style={{ animationDuration: dwellNow + "s" }}></i>')
     && _db.includes("next: {DASH_SECTIONS[(wallSection + 1) % DASH_SECTIONS.length].title}")
     && /@media \(prefers-reduced-motion:reduce\)\{\.dash-rot>i\{animation:none;/.test(html));
  ok("BIG SCREEN: the page header folds into the bar (range, updated, a clock, Exit); no tour and no menu over the TV",
     _db.includes("{!fill && <PageHeader") && _db.includes('<span className="dash-clock" data-wall-clock="1">{hhmm(clock)}</span>')
     && _db.includes('{fill && <button type="button" className="dash-wallbar-btn" onClick={toggleWall} title="Back to the working view (Esc)">Exit</button>}')
     && _pf.includes('(wallOn && page === "dashboard" ? " hidden" : "")') && _pf.includes('!(page === "dashboard" && wallOn) && <Guide'));
  ok("BIG SCREEN: on a TV nothing asks for a click — Top routes drops 'click a bar to focus' there",
     _db.includes('{!wall && <span className="text-slate-400 font-normal">· click a bar to focus</span>}'));
}

// ---- 14 Oct 2026 (the user: "rather than having huge charts, size charts and KPIs appropriately; do a design UI and UX
// quality check"). Found: charts stretched to fill with no message; four months as 180 px slabs; the carbon line's axis at
// 370 (a 10 % dip looked like a cliff); "1,000,000" ticks. Now: a headline over each big-screen chart, bars capped,
// axes from zero, compact ticks. Measured: fattest bar 68 px at 1080p (was ~180), every value axis min 0.
{
  const _db = (src.match(/function Dashboard\(\{[\s\S]*?\n\}\n/) || [""])[0];
  const _sc = (src.match(/function DashboardStockChart\([\s\S]*?\n\}\n/) || [""])[0];
  const _wall = _db.slice(_db.indexOf('<div className="wall-charts">'));
  ok("DESIGN: every big-screen chart opens with its message (a ChartHead), only on a filled screen — eight charts, eight headlines",
     (_wall.match(/\{fill && <ChartHead /g) || []).length === 8 && /const ChartHead = \(\{ value, label, note, tone \}\) => \(/.test(_db)
     && ["demandCfg", "progressCfg", "costCfg", "topCfg", "tripsCfg", "fleetCfg", "co2Cfg", "splitCfg"].every(k => new RegExp("<ChartHead [^\\n]*\\n\\s*<ChartCanvas config=\\{" + k + "\\}").test(_wall))
     && !_db.slice(0, _db.indexOf('<div className="wall-charts">')).includes("<ChartHead "));
  ok("DESIGN: the headlines say what the number is measured against (delivered of plan, planned vs the model, share of tonnes, per tonne)",
     _wall.includes('label="of the plan delivered"') && _wall.includes('`${bigNum(K.actualT)} t reported of ${bigNum(K.totT)} t planned`')
     && _wall.includes('"the fair-price model"') && _wall.includes("% of the tonnes in view`") && _wall.includes("kg for each tonne moved`"));
  ok("DESIGN: the stockpile screen opens with how many are over capacity (red), nearly full, with room, and with no capacity recorded",
     _sc.includes('{nOver ? `${nOver} over capacity` : "None over capacity"}') && _sc.includes("`${noCap.length} with no capacity recorded`")
     && _sc.includes("maxBarThickness: fill ? Math.round(sf * 4.5) : 40"));
  ok("DESIGN: every chart's value axis starts at zero, with compact ticks, and a bar is capped at 4.5 × its text (fitChartConfig)",
     /if\(vax\.beginAtZero == null && vax\.min == null\) vax\.beginAtZero = true;/.test(src) && /if\(!vt\.callback\) vt\.callback = compactTick;/.test(src)
     && /o\.datasets = \{ \.\.\.\(o\.datasets \|\| \{\}\), bar: \{ maxBarThickness: Math\.round\(fsz \* 4\.5\)/.test(src)
     && /const compactTick = \(v\) => \{/.test(src));
  ok("DESIGN: the headline type is from the screen height (number ~5 %, label 2 %, note 1.6 %), the label spaced from the number",
     /\.chart-head \.ch-val\{font-weight:700;color:var\(--navy-deep\);font-size:clamp\(1\.6rem,min\(5\.2vh,2\.7vw\),6\.5rem\);/.test(html)
     && /\.chart-head \.ch-lbl\{[^}]*margin-left:\.45em;\}/.test(html));
  ok("DESIGN: series names at a chart's end keep 20 characters (were cut at 15: 'Large aggregat…'), with room for them",
     src.includes('const t = m.label.length > 20 ? m.label.slice(0, 19) + "…" : m.label;') && /const SERIES_LABEL_PAD = 136;/.test(src));
}

// ---- 14 Oct 2026 (the user: "gate arrivals should be a chart, measuring arrivals against capacity"): a bullet chart,
// one row a gate, the fullest first. Capacity = the shift's minutes ÷ the check-in minutes a lorry, SENT BY THE SERVER
// (capacity_per_day, capacity_pct; test_gate_arrivals pins the arithmetic and that it agrees with the red flag).
{
  const _ga = (src.match(/function GateArrivalsPanel\([\s\S]*?\n\}\n/) || [""])[0];
  ok("GATE CHART: the panel opens with a chart, one row a gate (fullest first), above the table, which folds under 'Gate by gate'",
     _ga.includes('<div className="ga-chart" data-ga-chart="1">') && _ga.includes("<ChartCanvas config={gaCfg} height={Math.max(180, 46 * rowsC.length + 60)} />")
     && _ga.indexOf('data-ga-chart="1"') < _ga.indexOf('data-rd-table="gates"') && _ga.includes('<details className="ga-more" data-ga-table="1"><summary>Gate by gate:')
     && _ga.includes("((b.pct == null ? -1 : b.pct) - (a.pct == null ? -1 : a.pct)) || (b.g.arrivals_per_day - a.g.arrivals_per_day)"));
  ok("GATE CHART: a bullet chart — a pale track to the gate's capacity, the planned arrivals inside it, a marker with an arrow at capacity",
     _ga.includes('{ label: "Capacity a day", data: rowsC.map(r => r.cap == null ? null : r.cap)') && _ga.includes('{ label: "Planned arrivals a day", data: rowsC.map(r => r.g.arrivals_per_day)')
     && _ga.includes('const capMarks = { id: "gaCapMarks", afterDatasetsDraw: (chart) => {') && _ga.includes("plugins: [capMarks] };")
     && (_ga.match(/grouped: false/g) || []).length === 2);
  ok("GATE CHART: 🔴 the browser draws the server's capacity and flag — it divides nothing; red only where the server's flag is red",
     // NARROWED 14 Oct 2026 (W17): + near (the server's amber flag) in gold; the 85 % tick is the server's near_per_day
     _ga.includes(".map(g => ({ g, cap: g.capacity_per_day, pct: g.capacity_pct, over: g.flag === \"red\", near: g.flag === \"amber\" }))")
     && !/gaCapacity|shift_hours \* 60|\* *60|\/ *60|GA_NEAR *\/|\/ *100/.test(_ga) && _ga.includes("r.over ? REDg : r.near ? GOLDg : (r.cap == null ? NONEg : C1g)")
     && _ga.includes("x.getPixelForValue(r.g.near_per_day)"));
  ok("GATE CHART: every row says its figure in words (no hover on a TV or a print): 'N a day · P % of C', 'over capacity', 'no check-in time typed'",
     // NARROWED 14 Oct 2026 (W17): + "queue likely" on an amber row, and a headline for gates near capacity
     _ga.includes('const words = r.cap == null ? " · no check-in time typed" : ` · ${r.pct} % of ${grp(r.cap)}` + (r.over ? " · over capacity" : r.near ? " · queue likely" : "");')
     && _ga.includes('{nOverG ? `${nOverG} gate${nOverG === 1 ? "" : "s"} over capacity` : nNearG ? `${nNearG} gate${nNearG === 1 ? "" : "s"} near capacity: queue likely` : "Every gate within its capacity"}'));
  ok("GATE CHART: a key names the bar, the track, the marker, red and grey; the tooltip names the gate and how capacity is worked out",
     // NARROWED 14 Oct 2026 (W17): capacity is the gate's open hours (the shift where none are typed), and the key names the 85 % step
     _ga.includes('<i className="ga-key-bar"></i>planned arrivals a day') && _ga.includes("capacity: the open hours ÷ the check-in time a lorry")
     && _ga.includes('<i className="ga-key-gold"></i>{GA_NEAR} % or more: queue likely')
     && _ga.includes("more than it can check in") && _ga.includes("no check-in time typed</span>")
     && _ga.includes("`the ${ga.shift_hours} h shift`} ÷ ${+r.g.gate_minutes} min a lorry)`") && _ga.includes("`open ${r.g.open_hours}"));
}

// ---- 14 Oct 2026 (bundle G, W7 + W8): CLP monitoring and the CLP data fields, source level ---------------
{
  const _cs = src.indexOf("// ---- 14 Oct 2026 (bundle G, W7): CLP monitoring ----"), _ce = src.indexOf("function BulletinMenu({ months }){");
  const clpc = _cs > 0 && _ce > _cs ? src.slice(_cs, _ce) : "";
  ok("CLP: one block before BulletinMenu holds the section, its cards and its five chart builders",
     clpc.length > 4000 && ["function ClpCard(", "function clpBulletCfg(", "function clpShareCfg(", "function clpCouncilCfg(", "function clpCarbonCfg(",
       "function clpTripsCfg(", "function ClpUncapped(", "function ClpMonitoring({ months, initial })"].every(f => clpc.includes(f)));
  ok("⭐ CLP: read on FIRST OPEN only: the effect waits for open, GETs /api/clp/monitoring?month=N, keyed on open and the month",
     clpc.includes("if(!open) return;") && clpc.includes("fetch(`${API}/clp/monitoring?month=${month}`)") && clpc.includes("}, [open, month]);")
     // NARROWED 14 Oct 2026 (W10, the same session): a second fetch, the CLP pack, on a button press only
     && clpc.includes('onToggle={e => setOpen(e.currentTarget.open)}') && (clpc.match(/fetch\(/g) || []).length === 2
     && clpc.includes("const r = await fetch(`${API}/clp/pack.${ext}?month=${month}`);"));
  ok("⭐ W10: the section offers the CLP pack for its month, PDF and XLSX; the file name is the reply's own; a failure is said in words",
     clpc.includes('onClick={() => pack("pdf")}') && clpc.includes('onClick={() => pack("xlsx")}')
     && clpc.includes('const m = cd.match(/filename="([^"]+)"/);') && clpc.includes('setPackErr("The CLP pack could not be made: " + (e.message || e));')
     && clpc.includes('{packErr && <div className="ct-line" role="alert" data-clp-pack-error="1">{packErr}</div>}'));
  ok("⭐ CLP: the Dashboard mounts it once, folded, after More charts and before Stockpile capacity",
     (src.match(/<ClpMonitoring months=\{months\} initial=\{initialClp\} \/>/g) || []).length === 1
     && src.indexOf("<ClpMonitoring") > src.indexOf("<summary>More charts: trips") && src.indexOf("<ClpMonitoring") < src.indexOf("<summary>Stockpile capacity</summary>"));
  ok("🔴 CLP: the browser divides nothing — no division, ceil or rounding of a figure; it draws the server's fields",
     // (the one division left is drawing, not a figure: half a bar's height in pixels for the cap marker)
     clpc.includes("const half = (el.height || 16) / 2 + 5")
     && !/[\w)\]]\s*\/\s*[\w(]/.test(clpc.replace("(el.height || 16) / 2", "").replace(/<\/?[A-Za-z][^>]*>/g, "").replace(/\/\/[^\n]*/g, "").replace(/"[^"\n]*"|`[^`\n]*`/g, '""'))
     && !/Math\.(ceil|round|floor)/.test(clpc));
  ok("CLP: an empty chart is an EmptyState carrying the server's missing sentence; a set one its headline, how it is worked out and its source",
     clpc.includes('{c.state !== "set" ? <EmptyState kind="none" title="Not enough to draw this yet" body={c.missing} /> : <>')
     && clpc.includes('<details className="clp-how"><summary>How it is worked out</summary><p>{c.basis}</p></details>') && clpc.includes("Source: {c.source}"));
  ok("CLP: each card carries its own literal info box (seven) and the section one",
     ["clp.route_caps", "clp.site_caps", "clp.vehicle_types", "clp.euro_class", "clp.councils", "clp.carbon_rate", "clp.trips_avoided", "dash.clp"]
       .every(id => clpc.includes(`<InfoTip id="${id}" />`)));
  ok("🔴 CLP colours are tokens only: the chart slots, the status red, the none grey, ink for a cap or target; Not typed is grey",
     !/#[0-9A-Fa-f]{6}\b(?!")/.test(clpc.replace(/tok\("[^"]+", "#[0-9A-Fa-f]{6}"\)/g, "")) && clpc.includes('s.group === CLP_NOT_TYPED ? tok("--chart-none", "#A8A29E") : colorOf(slot++)')
     && clpc.includes('const CLP_NOT_TYPED = "Not typed";'));
  ok("CLP: per load is drawn without a target line; the target shared out per tonne is a dashed ink line",
     clpc.includes('if(per === "tonne" && c.target_kg_per_tonne != null) ds.push({ label: "The target, shared out", data: m.map(() => c.target_kg_per_tonne), borderColor: INK, borderDash: [6, 4]')
     && !clpc.includes("target_kg_per_load"));
  ok("CLP: every bullet row says its figure in words (no hover on a print or a TV): 'N word · P % of C' and 'over the cap'",
     // NARROWED 14 Oct 2026 (seen at 1366 px: one long line ran off the card): two short lines in a column right of the plot
     clpc.includes('ctx.fillText(`${clpN1(r[valKey])} ${word}`, A.right + 12, el.y - 7);')
     && clpc.includes('ctx.fillText(`${r.pct} % of ${grp(r.cap)}` + (r.over ? " · over the cap" : ""), A.right + 12, el.y + 8);'));
  // W17: the Look-ahead's gates this week, and the rail's two codes
  ok("⭐ W17: GatesWeek draws the page's gates_week (no read of its own), after the grid and before the map",
     src.includes("function GatesWeek({ gw }){") && src.includes("{lines.length > 0 && <GatesWeek gw={page && page.gates_week} />}")
     && src.indexOf("<GatesWeek gw=") < src.indexOf("<CommitMap meta={meta} bucket={bucket} tick={tick} lines={lines} />")
     && !src.slice(src.indexOf("function GatesWeek({ gw }){"), src.indexOf("// the status pill column between the line and the days")).includes("fetch("));
  ok("W17: each day is the server's: red past capacity, gold from 85 %, a capacity step line and a dashed 85 % line; words via RowStatus",
     src.includes('backgroundColor: g.days.map(d => d.flag === "red" ? RED : d.flag === "amber" ? GOLD : (g.capacity_per_day == null ? NONE : C1)) }];')
     && src.includes('stepped: "middle", order: 1 });') && src.includes("data: g.days.map(d => d.open ? g.near_per_day : 0), borderColor: GOLD, borderWidth: 1.5, borderDash: [4, 3]")
     && src.includes('<RowStatus word={`${d.day}: ${d.status_word}${d.pct != null ? ` (${d.pct} %)` : d.open ? "" : " (closed)"}`} tone={d.flag === "red" ? "bad" : "warn"} />'));
  ok("⭐ W17: the rail names GATE OVER CAPACITY / GATE NEAR CAPACITY (as the exports do); near is a gold warning, over red",
     src.includes('GATE_OVER: "GATE OVER CAPACITY", GATE_NEAR: "GATE NEAR CAPACITY" };') && src.includes('GATE_OVER: "GATE OVER", GATE_NEAR: "GATE NEAR" };')
     && src.includes('const laTone = (code) => (code === "UNBAKED" || code === "RESTRICTION" || code === "GATE_NEAR") ? "warn" : "bad";')
     && src.includes('<i style={{ background: laTone(f.code) === "warn" ? "var(--gold)" : "var(--red)" }} aria-hidden="true"></i>')
     && /"GATE_OVER": "GATE OVER CAPACITY", "GATE_NEAR": "GATE NEAR CAPACITY"/.test(fs.readFileSync(path.join(ROOT, "backend", "export.py"), "utf8")));
  // W8: the data fields
  ok("⭐ W8: the location form carries the CLP cap (lorry visits a day), sends null for blank, never 0",
     src.includes('data-clp-cap-field="1"') && src.includes('aria-label="CLP cap: lorry visits a day"')
     && src.includes('clp_cap_per_day: (f.clp_cap_per_day === "" || f.clp_cap_per_day == null) ? null : +f.clp_cap_per_day,')
     && src.includes('clp_cap_per_day: p.clp_cap_per_day == null ? "" : p.clp_cap_per_day'));
  ok("⭐ W17: the gate form carries open hours (two time boxes) and seven day boxes; every day ticked is sent as blank (the shift, every day)",
     src.includes('data-gate-hours-form="1"') && src.includes('aria-label="Open from"') && src.includes('aria-label="Open to"')
     && src.includes('return { ...g, open_days: v === "1111111" ? "" : v };') && src.includes('open_from: gateForm.open_from || "", open_to: gateForm.open_to || "", open_days: gateForm.open_days || "",')
     && src.includes('const GATE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];'));
  const _cfgPy = fs.readFileSync(path.join(ROOT, "backend", "config.py"), "utf8"), _ghPy = fs.readFileSync(path.join(ROOT, "backend", "gate_hours.py"), "utf8");
  ok("🔴 W8: the Euro classes, the peak-band cap and placeholder and the 85 % step are held equal to the backend",
     /EURO_CLASSES = \("Euro IV", "Euro V", "Euro VI", "Zero emission"\)/.test(_cfgPy) && src.includes('const EURO_CLASSES = ["Euro IV", "Euro V", "Euro VI", "Zero emission"];')
     && /MAX_PEAK_BANDS = 4\b/.test(_ghPy) && src.includes("const PEAK_BANDS_MAX = 4;")
     && /PEAK_PLACEHOLDER = \[\{"from": "07:00", "to": "10:00"\}, \{"from": "16:00", "to": "19:00"\}\]/.test(_ghPy)
     && src.includes('const PEAK_BANDS_PLACEHOLDER = [{ from: "07:00", to: "10:00" }, { from: "16:00", to: "19:00" }];')
     && /NEAR_PCT = 85\b/.test(_ghPy) && src.includes("const GA_NEAR = 85;"));
  ok("W8: Config → Vehicles has a Euro class column ('not typed' deletes the key); Config → Planning the no-delivery peak bands, at most four",
     src.includes('"Unload min", "Euro class", "Planning"]') && src.includes('data-cfg-euro={k}') && src.includes("else delete d.vehicles[k].euro_class;")
     && src.includes('data-cfg="peak-bands"') && src.includes("No-delivery peak bands (from the CLP)") && src.includes("((doc.planning || {}).peak_bands || []).length < PEAK_BANDS_MAX")
     && src.includes("Wayscope holds no arrival times, so it cannot check that lorries keep out of them."));
}

// ---- 14 Oct 2026 (D9 + D14, the mobile shell; notes/session-1014-mobile-shell.md) ----------------------------------------
// Below 768 px (one breakpoint, D9) the rail gives way to a bottom tab bar of four in the tenant's words; on a phone the
// Dashboard, the Look-ahead and the Route map show (D9), everything else is the "Open on a desktop to edit this" card;
// nothing on a phone writes (D9: read-only first) — the write controls are NOT RENDERED there, never disabled. The phone
// Look-ahead is a date strip and one day card with a Day sheet (mockup 10, D9 "Day sheet yes"). dom_frontend clicks it.
{
  const _pt = (src.match(/function PhoneTabs\([\s\S]*?\n\}\n/) || [""])[0];
  const _pm = (src.match(/function PhoneMore\([\s\S]*?\n\}\n/) || [""])[0];
  const _do = (src.match(/function DeskOnly\([\s\S]*?\n\}\n/) || [""])[0];
  const _pl = (src.match(/function PhoneLookAhead\([\s\S]*?\n\}\n/) || [""])[0];
  const _po = (src.match(/function Portal\([\s\S]*?\n\}\n/) || [""])[0];
  const _css = (html.match(/\/\* PHONE-SHELL-START[\s\S]*?PHONE-SHELL-END \*\//) || [""])[0];
  ok("⭐ D9: one breakpoint, 768 px, the same as the cards; the phone pages are the Dashboard, the Look-ahead and the Route map",
     /const NARROW_Q = "\(max-width: 767px\)";/.test(src) && src.includes('const PHONE_PAGES = ["dashboard", "lookahead", "map"];')
     && /@media \(max-width:767px\)\{\n    \.rd-table\{min-width:0 !important;width:100%;\}/.test(html));
  ok("PHONE TABS: the three phone pages from NAV (their labels: the tenant's words, never an id) and More; one nav named 'Pages'",
     _pt.includes("(groups || []).flatMap(g => g.items).filter(it => PHONE_PAGES.includes(it.id))") && _pt.includes("<NavIcon id={it.id} /><span>{it.label}</span>")
     && _pt.includes('<span>More</span>') && _pt.includes('aria-label="Pages"') && !/\{it\.id\}<\/span>/.test(_pt)
     && _pt.includes('aria-current={page === it.id ? "page" : undefined}') && _pt.includes('aria-expanded={moreOpen ? "true" : "false"} aria-controls="phone-more"'));
  ok("PHONE TABS: the tab bar is the guide's 'rail' anchor and the foot the guide's strip stays above",
     _pt.includes('data-guide="rail" data-sticky-foot="1"'));
  ok("⭐ PHONE: the Portal draws the rail only at 768 px and up, and the tab bar and More only below",
     _po.includes('{!narrow && <aside data-guide="rail"') && _po.includes("{narrow && <PhoneTabs groups={visible} page={page} onPick={pickPage} moreOpen={moreOpen}")
     && _po.includes("{narrow && moreOpen && <PhoneMore groups={visible} page={page} onPick={pickPage}"));
  ok("⭐ PHONE WATCHER (hide, do not disable): every desk page is not RENDERED on a phone — Submit, Forecasts, Carbon, the desk Look-ahead, Data, Config",
     _po.includes('{page === "submit" && !narrow && <Matrix ') && _po.includes('{page === "forecasts" && !narrow && <Forecasts ')
     && _po.includes('{page === "carbon" && !narrow && <CarbonPage ') && _po.includes('{page === "lookahead" && !narrow && <LookAhead ')
     && _po.includes("{DATA_PAGES.includes(page) && canApprove && !narrow && (") && _po.includes('{page === "config" && canApprove && !narrow && <ConfigPage ')
     && _po.includes("const phoneDesk = narrow && !PHONE_PAGES.includes(page);") && _po.includes("{phoneDesk && <DeskOnly label={current.label} onHome={() => pickPage(\"dashboard\")} />}")
     && !/disabled=\{[^}]*\b(narrow|phone)\b/.test(src));
  // the same rule for ANY page added later (G3's Users page, say): every page the Portal mounts, other than the Dashboard
  // and the Route map, carries `!narrow`, or is a Phone… page mounted only when narrow
  {
    const _main = _po.slice(_po.indexOf('<main className="flex-1 min-h-0 overflow-auto">'), _po.indexOf("</main>"));
    const mounts = [..._main.matchAll(/\{(?:page === "(\w+)"|DATA_PAGES\.includes\(page\))([^\n]*)/g)].map(m => ({ id: m[1] || "data", rest: m[2] }));
    const loose = mounts.filter(m => !["dashboard", "map"].includes(m.id) && !/ && !narrow && /.test(m.rest) && !/ && narrow && <Phone[A-Z]/.test(m.rest));
    ok("⭐ PHONE WATCHER, for every page: each page the Portal mounts (but the Dashboard and the Route map) is desk-only on a phone or a Phone… page",
       mounts.length >= 9 && loose.length === 0, loose.map(m => m.id).join(", ") || String(mounts.length));
  }
  ok("PHONE: the desk-only card says 'Open on a desktop to edit this.' under the page's own name, and offers the Dashboard",
     _do.includes("<h2>{label}</h2>") && _do.includes('<p className="do-lead">Open on a desktop to edit this.</p>')
     && _do.includes("On a phone, Wayscope shows the Dashboard, the Look-ahead and the Route map, to read.") && _do.includes("Go to the Dashboard"));
  ok("PHONE: More lists the role's desk pages (from the visible groups, so a team code never sees Data or Config) and the user guide in a new tab",
     _pm.includes("const desk = (groups || []).flatMap(g => g.items).filter(it => !PHONE_PAGES.includes(it.id));")
     && _pm.includes('role="dialog" aria-modal="true" aria-label="More pages"') && _pm.includes('target="_blank" rel="noopener noreferrer"')
     && _pm.includes("{teamText(who) || \"—\"} · {role.ipt ? teamName(role.ipt) : role.label}"));
  ok("PHONE: Escape and the shade shut More; Ctrl K opens it on a phone (the rail's search is not drawn there)",
     _po.includes('const k = (e) => { if(e.key === "Escape") setMoreOpen(false); };') && _pm.includes('className="phone-more-back" aria-label="Close More" tabIndex={-1} onClick={onClose}')
     && _po.includes("if(window.matchMedia && window.matchMedia(NARROW_Q).matches){ setMoreOpen(true); return; }"));
  ok("⭐ PHONE WATCHER: the Dashboard's big-screen switch is not drawn on a phone", src.includes('{!phone && <button type="button" data-guide="dash-wall" onClick={toggleWall}'));
  ok("⭐ PHONE WATCHER: the phone Look-ahead only READS — one GET of /lookahead and the Day sheet's GET; no method, no send(), no input, no Confirm",
     _pl.length > 3000 && (_pl.match(/fetch\(/g) || []).length === 2 && _pl.includes("fetch(`${API}/lookahead?bucket=${bucket}`)")
     && _pl.includes("fetch(`${API}/forecast-weeks/day-sheet?bucket=${bucket}&day=${shown}`)")
     && !/method|send\(|<input|<select|<textarea|Confirm week|Re-open|saveDay|saveActual|doConfirm|doSpread|refreshTarkTee/.test(_pl));
  ok("PHONE LOOK-AHEAD: a date strip of the week's weekdays (today first, today marked), one card for the chosen day",
     _pl.includes("const shown = (day && dates.includes(day)) ? day : (dates.includes(today) ? today : dates[0]);")
     && _pl.includes('aria-pressed={iso === shown ? "true" : "false"}') && _pl.includes('className={"ph-day" + (iso === today ? " is-today" : "")}')
     && _pl.includes('data-guide="ph-days"') && _pl.includes('data-guide="ph-sheet"'));
  ok("PHONE LOOK-AHEAD: the card's figures are the server's for that day (derived tonnes, trips, vehicles of routed lines), lines heaviest first",
     _pl.includes("const tonnes = rows.reduce((x, r) => x + (r.f.tonnes || 0), 0);") && _pl.includes("const loads = rows.reduce((x, r) => x + (r.f.trips || 0), 0);")
     && _pl.includes("const lorries = routed.reduce((x, r) => x + (r.f.vehicles || 0), 0);")
     && _pl.includes(".sort((a, b) => ((b.f.tonnes || 0) - (a.f.tonnes || 0)) || String(a.line.route_id).localeCompare(String(b.line.route_id)));"));
  ok("PHONE LOOK-AHEAD: each line shows its places, the team's NAME and the material as chips, one status (the desk grid's laStatus), facts behind a native button",
     _pl.includes("const teamWord = iptKey(r.c.ipt) ? teamName(iptKey(r.c.ipt)) : `No ${TEAM().toLowerCase()}`;")
     && _pl.includes("<RowStatus word={r.st.word} tone={r.st.tone} more={r.st.more} />") && _pl.includes("st: laStatus(lf, line.week || {})")
     && _pl.includes('aria-expanded={isOpen ? "true" : "false"} aria-controls={did}') && _pl.includes('<dl className="rd-dl" id={did} hidden={!isOpen}>')
     && _pl.includes("laFlagGroups(r.lf).map(g =>"));
  ok("PHONE LOOK-AHEAD: the Day sheet downloads as day-sheet-<day>.pdf, and the page says where typing happens",
     _pl.includes("a.download = `day-sheet-${shown}.pdf`;") && _pl.includes("To type a day's plan, confirm the week or record what moved, open the Look-ahead on a desktop."));
  ok("PHONE GUIDE: the Look-ahead has its own phone steps, the Dashboard's big-screen step is marked desk-only, and the welcome names the tabs",
     /\n  lookahead_phone: \[\n    \{ anchor: "ph-days", title: "One day at a time\."/.test(src) && src.includes('{ anchor: "dash-wall", title: "Big screen.", body: "Opens a version made for a site-office TV.", desk: true },')
     && src.includes("setRailRight(rr.height > rr.width ? Math.round(rr.right) : 0);"));
  ok("PHONE CSS: every phone control is a 48 px box or more (tabs 56, sheet rows 48, week switch 48, days 56, lines 48, Show more 48, the card's buttons 48)",
     /\.phone-tab\{[^}]*min-height:56px;/.test(_css) && /\.phone-more-item\{[^}]*min-height:48px;/.test(_css) && /\.ph-seg button\{min-height:48px;/.test(_css)
     && /\.ph-day\{[^}]*min-height:56px;/.test(_css) && /\.ph-line>button\{[^}]*min-height:48px;/.test(_css) && /\.ph-more\{[^}]*min-height:48px;/.test(_css)
     && /\.ph-actions>\*\{flex:1;min-height:48px;/.test(_css) && /\.tap48\{min-height:48px;\}/.test(_css));
  ok("PHONE CSS: tokens only (every look and accent follows), the active tab in the accent's control colour, the 14 px floor kept (13 px only for the tab words and notes)",
     _css.length > 3000 && !/#[0-9A-Fa-f]{3,6}\b/.test(_css) && /\.phone-tab\.is-on\{color:var\(--action\);/.test(_css)
     && /\.phone-tab\.is-on::before\{[^}]*background:var\(--action\);\}/.test(_css) && !/font(-size)?:[^;]*\b(9|10|11|12)px/.test(_css));
  ok("PHONE CSS: the page header's actions wrap under the title (a phone, and 768–1023 px beside the open rail), the Look-ahead's flags wrap in their chips",
     /\n  \.ph-actions-box\{flex-shrink:1;min-width:0;max-width:100%;flex-wrap:wrap;\}/.test(_css)
     && /\[data-guide="lookahead-flags"\] \.chip-st\{white-space:normal;/.test(_css)
     && /\.chart-box>canvas\{max-width:100%;\}/.test(_css)
     && src.includes('{actions && <div className="flex items-center gap-2 shrink-0 ph-actions-box">{actions}</div>}'));
  ok("PHONE: the sheet stops at the tab bar, so More still shuts it; the bar keeps clear of a phone's home indicator",
     /\.phone-more\{position:absolute;left:0;right:0;bottom:calc\(57px \+ env\(safe-area-inset-bottom,0px\)\);/.test(_css)
     && /\.phone-tabs\{[^}]*padding-bottom:env\(safe-area-inset-bottom,0px\);/.test(_css));
}

// ---- 14 Oct 2026 (G3): per-person logins, at source ---------------------------------------------------------
{
  const fnBody = (name) => { const i = code.indexOf(`function ${name}(`); if (i < 0) return ""; const j = code.indexOf("\nfunction ", i + 10); return code.slice(i, j < 0 ? undefined : j); };
  const wrap = code.slice(code.indexOf("window.fetch = (url, opts) =>"), code.indexOf("const SESSION_ENDED"));
  ok("⭐ G3: the ONE fetch wrapper adds X-Wayscope to every API call (the server refuses a cookie write without it)",
     wrap.includes('o.headers = { ...(o.headers || {}), "X-Wayscope": "1", ...(ACCESS.code ? { "X-Access-Code": ACCESS.code } : {}) };')
     && (code.match(/"X-Wayscope"/g) || []).length === 1);
  ok("G3: a 401 to a login (not on a sign-in call) ends the session in the app, once, by one event",
     wrap.includes('if(r.status === 401 && ACCESS.info && ACCESS.info.via === "login" && !u.startsWith(API + "/auth/"))')
     && code.includes('const SESSION_ENDED = "wayscope-session-ended";'));
  ok("⭐ G3: an emailed link is read from the FRAGMENT once, only its own characters, and taken off the address at once",
     /const START_LINK = \(function\(\)\{[\s\S]{0,400}\/\^#\(invite\|reset\|demo\)=\(\[A-Za-z0-9_-\]\{20,200\}\)\$\/[\s\S]{0,200}history\.replaceState\(null, "", window\.location\.pathname \+ window\.location\.search\);/.test(code));
  ok("🔴 G3: the session never touches page storage — only a '1' hint is kept, and no password or email is stored",
     code.includes('localStorage.setItem(AUTH_HINT, "1")') && !/(local|session)Storage\.setItem\([^)]*(pass|email|session)/i.test(code)
     && !/document\.cookie/.test(code));
  const lg = fnBody("Login");
  ok("G3: the sign-in screen opens on email and password; the code form only while the server says codes are on",
     lg.includes('const [mode, setMode] = useState("email");') && lg.includes('postJSON("/auth/signin", { email: email.trim(), password: pass, remember })')
     && lg.includes('{codesOn && !forgot && <button type="button" onClick={() => go("code")}>Sign in with a team code instead</button>}')
     && lg.includes("setCodesOn(!!(j && j.codes))") && lg.includes('autoComplete="username"') && lg.includes('autoComplete="current-password"'));
  ok("G3: 'Forgot your password?' posts the email only, and shows the server's one answer",
     lg.includes('postJSON("/auth/forgot", { email: email.trim() })') && lg.includes("setMsg(j.message"));
  const sp = fnBody("SetPassword");
  ok("G3: the set-password screen checks the link first (no use), refuses short and unmatched passwords on the page, then posts",
     sp.includes('postJSON("/auth/check", { token: link.token })') && sp.includes("if(pw.length < 10)") && sp.includes("if(pw !== pw2)")
     && sp.includes('postJSON("/auth/reset", { token: link.token, password: pw, remember })') && sp.includes('autoComplete="new-password"'));
  const up = fnBody("UsersPage");
  ok("⭐ G3 USERS: never renders a team id — teams come from the server's NAMES; the slot is only an option value",
     up.length > 3000 && !/\{u\.team\}|\{l\.team\}|\{t\.id\}<|>\{.*\.team\}/.test(up) && up.includes('teams.map(t => ["team:" + t.id, t.label])')
     && up.includes("{choices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}"));
  ok("G3 USERS: the admin token is asked for only when NOT signed in as an admin login (D47 bootstrap), never sent by a login",
     up.includes("{!viaLogin && (") && up.includes('if(!viaLogin && token) q.set("token", token);'));
  ok("G3 USERS: the person cannot disable themself; a link that could not be emailed is shown to pass on",
     up.includes("{u.id !== data.me && <button") && up.includes("Pass this link on yourself") && up.includes("navigator.clipboard.writeText(note.link)"));
  ok("G3: Users is an admin-only item, shown to an admin and (for the first-admin step) a planner on a shared CODE, never a planner login",
     code.includes('const isAdmin = !!(role && (role.role === "admin" || (role.can_approve && role.via !== "login")));'));
  // NARROWED 14 Oct 2026 (merged with the mobile shell, D9): and only at 768 px and up; on a phone it is the desk card
  ok("G3: Users is an admin-only item, rendered only for an admin",
     code.includes('{ id: "users", label: "Users", glyph: "☺", adminOnly: true }') && code.includes('{page === "users" && isAdmin && !narrow && <UsersPage access={role} />}')
     && code.includes(".map(g => ({ ...g, items: g.items.filter(i => !i.adminOnly || isAdmin) }))"));
  ok("G3 (D51): only a DEMO login reports page opens", /if\(!role \|\| role\.kind !== "demo"\) return;\s*\n\s*fetch\(`\$\{API\}\/activity`/.test(code));
  const am = fnBody("AccountMenu");
  ok("G3: the account menu shows the team by NAME and offers a password change to staff logins only",
     am.includes("const team = role.ipt ? teamName(role.ipt) : role.label;") && am.includes("{!demo && (")
     && am.includes('postJSON("/auth/password", { current: cur, new: nw })'));
  ok("G3: the header shows the account menu for a login and the old team/role line for a code",
     code.includes('{role.via === "login" ? <AccountMenu role={role} onSignOut={signOut} />'));
  ok("G3 (phone): below 640 px a login's name becomes its initials, its Sign out moves into the menu, and the menu is pinned on screen",
     html.includes(".hdr-signout-login{display:none;} .acct-signout{display:block;} }") && html.includes(".acct-btn .acct-name{display:none;} .acct-btn .acct-ini{display:inline;}")
     && html.includes(".acct-menu{position:fixed;left:8px;right:8px;top:60px;min-width:0;}")
     && code.includes('(role.via === "login" ? " hdr-signout-login" : "")') && code.includes('aria-label={`Your account: ${role.name}`}'));
}

// ---- 14 Oct 2026 (backlog item 2): the route map export from the Routes page --------------------------------------------
{
  const _rm = (src.match(/function RouteMapExportMenu\([\s\S]*?\n\}\n/) || [""])[0];
  // NARROWED 14 Oct 2026, evening (the user: "just the map … certain scales as in the CLP template"): the two options gave
  // way to the CLP template's three plans
  ok("⭐ ROUTE MAP EXPORT (Routes page): one menu on the Routes list's bar, the month, every route or the one picked, a team, the plan",
     _rm.length > 1500 && (code.match(/<RouteMapExportMenu /g) || []).length === 1
     && code.includes("<RouteMapExportMenu months={meta.months} ipts={meta.ipts} picked={selected} />")
     && _rm.includes('aria-label="Route map month"') && _rm.includes('<option value="all">Every route</option>')
     && _rm.includes('{picked && <option value="picked">Only the route picked in the list</option>}')
     && _rm.includes('<option value="regional">Regional plan: the whole routes</option>')
     && _rm.includes('<option value="local">Local plan: around a site, 1:2,000 to 1:3,000</option>')
     && _rm.includes('<option value="site">Site plan: around a site, 1:500 to 1:1,000</option>'));
  // REVERSED 14 Oct 2026, evening: no map-only switch and no Carbon Tool rows — the export is only ever the map
  ok("🔴 ...no 'map only' switch, no Carbon Tool rows, no tick-box style left behind",
     !/map_only|carbon_tool|mapOnly|carbonTool|Carbon Tool rows/.test(_rm) && !src.includes(".bulletin-menu .rme-tick"));
  ok("...it asks the one staff-only endpoint with the same parameters as the public map (routes, team, plan, scale, at), PDF or PNG",
     _rm.includes("fetch(`${API}/routes/map-export.${kind}?${q.toString()}`)") && _rm.includes('if(scope === "picked" && picked) q.set("routes", picked);')
     && _rm.includes('q.set("plan", plan);') && _rm.includes('if(scale) q.set("scale", scale);')
     && _rm.includes('if(spec && spec.centred && at) q.set("at", at);')
     && _rm.includes('onClick={() => download("pdf")}') && _rm.includes('onClick={() => download("png")}'));
  ok("...the scales and the places to centre on come from the server for the month, routes and team chosen (read again when they change)",
     _rm.includes("fetch(`${API}/routes/map-export/places?${query().toString()}`)")
     && _rm.includes("useEffect(() => { if(open) load(); }, [open, m, scope, team, picked]);")
     && _rm.includes("{(spec ? spec.scales : []).map(n =>") && _rm.includes("{spec && spec.centred && <label><span>Centred on</span>"));
  ok("...team NAMES in its list (teamText), never an id",
     _rm.includes("{(ipts || []).map(i => <option key={i.id} value={i.id}>{teamText(i.id)}</option>)}"));
  ok("...it says what it is (approved lines, not an approved CLP), and a refusal in words",
     _rm.includes("Approved lines only. A planning document, not an approved CLP.") && _rm.includes('setErr("The route map could not be made: " + (e.message || e));'));
  ok("...placed after App, outside the Dashboard's read-only stock slice (that pin scans DashboardStockChart → App)",
     code.indexOf("function RouteMapExportMenu(") > code.indexOf("function App(") && code.indexOf("function RouteMapExportMenu(") < code.indexOf("function Header("));
}

// ---- 16 Oct 2026 (the UI audit, finding #14): names for the staff map's header selects and the Config JSON textarea ----
// axe-core select-name and label (WCAG 4.1.2, Level A): on Locations, Routes and Zones the header announced "Light,
// combo box" and "Artic Tipper (44t), combo box" with no word for what changes, and two selects were named only by a
// title. The visible word beside a select is in its name (WCAG 2.5.3): "Basemap" → Basemap, "Show" → Show vehicle.
{
  const _h0 = src.indexOf('<span className="text-xs text-slate-400">Basemap</span>');
  const _hd = _h0 < 0 ? "" : src.slice(_h0, src.indexOf('placeholder="Admin token"', _h0));
  ok("names #14: the header of Locations / Routes / Zones is one block with four selects (Basemap, Show, direction, route option)",
     _h0 > 0 && _hd.length > 200 && _hd.length < 2500 && (_hd.match(/<select\b/g) || []).length === 4, String(_hd.length));
  ok("🔴 names #14: the Basemap select is named Basemap, the word shown beside it",
     _hd.includes('<span className="text-xs text-slate-400">Basemap</span>\n          <select value={basemap} onChange={e => changeStyle(e.target.value)} className={sel} aria-label="Basemap">'));
  ok("🔴 names #14: the vehicle select is named 'Show vehicle' — the visible word 'Show' first in the name (2.5.3)",
     _hd.includes('<span className="text-xs text-slate-400 ml-1">Show</span>\n          <select value={showProfile} onChange={e => setShowProfile(e.target.value)} className={sel} aria-label="Show vehicle">'));
  ok("🔴 names #14: the two selects that had only a title carry names — Direction drawn, Route option drawn — and keep their titles",
     _hd.includes('<select value={showLeg} onChange={e => setShowLeg(e.target.value)} className={sel} title="Which direction to draw" aria-label="Direction drawn">')
     && _hd.includes('<select value={showAlt} onChange={e => setShowAlt(+e.target.value)} className={sel} title="Which HERE option to draw" aria-label="Route option drawn">'));
  const _names = [..._hd.matchAll(/<select [^\n]*aria-label="([^"]*)"/g)].map(m => m[1]);
  ok("names #14: all four are named, in words that pass the word rule (no bake, server, endpoint, token, cached, geometry) and say lorry never truck",
     _names.length === 4 && _names.every(n => n.length > 3 && !/\b(bake|baked|server|endpoint|token|cached|geometry|trucks?)\b/i.test(n)), JSON.stringify(_names));
  const _rw = src.slice(src.indexOf('{tab === "raw" && ('), src.indexOf('<div className="savebar" data-cfg-savebar="1">'));
  ok('🔴 names #14: the Config "Everything (JSON)" textarea is named exactly "Everything (JSON)" — the tab\'s own words, the one JSON wording the word rule exempts',
     (_rw.match(/<textarea\b/g) || []).length === 1
     && _rw.includes('<textarea className="w-full h-[60vh] font-mono text-[13px] border border-slate-300 rounded-lg p-3" value={raw} aria-label="Everything (JSON)"'));
  ok("names #14: no other aria-label on a staff screen says JSON (the exemption covers the tab's own words only)",
     [...src.matchAll(/aria-label="([^"]*)"/g)].map(m => m[1]).filter(n => /\bJSON\b/.test(n)).every(n => n === "Everything (JSON)"));
}

// ---- 17 Oct 2026 (the UI audit's keyboard findings #15 and #16, claude/ui-fix-keyboard) -----------------------------
// #16: the rail's "Find a page" box was the one control with no focus ring (its input has outline:0); the ring now goes on
// the label that frames it, via :focus-within, the same ring as .auth-input:focus. #15: the Locations table scrolls in a
// 40 vh box whose rows are mouse-only, so a keyboard user could reach none of it: the box is a named region with tabindex 0
// and a ring. The Carbon planner's two step-5 reference tables wrap their cells instead of scrolling the Reference column
// 1,200 px off a 772 px box. The big screen's Today list (open question 6) and the rows themselves (open question 16) wait.
{
  ok("🔴 #16: the Find a page box shows a ring when its input has the focus — the same ring as the sign-in fields",
     html.includes(".rail-search:focus-within{outline:2px solid var(--action);outline-offset:1px;border-color:var(--action);}")
     && html.includes(".auth-input:focus{outline:2px solid var(--action);outline-offset:1px;border-color:var(--action);}")
     && html.includes('<label className="rail-search" title="Find a page (Ctrl K)">')
     && /\.rail-search input\{[^}]*outline:0;/.test(html));
  ok("🔴 #15: the Locations table's scroll box is a named region a keyboard user can Tab to (tabindex 0, role region, 'Locations table'), with a ring",
     src.includes('<div className="overflow-auto kb-scroll" style={{ maxHeight: "40vh" }} tabIndex={0} role="region" aria-label="Locations table">')
     && html.includes(".kb-scroll:focus-visible{outline:2px solid var(--navy);outline-offset:2px;}"));
  const _regions = [...src.matchAll(/<div className="([^"]*)"[^\n]*tabIndex=\{0\} role="region" aria-label="([^"]*)"/g)];
  ok("#15: every scroll region with tabindex 0 carries a focus-ring class (kb-scroll or sim-scroll) and a name that passes the word rule",
     _regions.length === 3 && _regions.every(m => /\b(kb-scroll|sim-scroll)\b/.test(m[1]) && m[2].length > 3
       && !/\b(bake|baked|server|endpoint|token|cached|geometry|trucks?)\b/i.test(m[2])), String(_regions.length));
  ok("#15: the Locations rows are still mouse-only (open question 16 — pinned as found, not fixed here)",
     src.includes('<tr key={l.id} onClick={() => locateNode(l.id)}\n') && !/<tr key=\{l\.id\} onClick=\{\(\) => locateNode\(l\.id\)\}[^\n]*tabIndex/.test(src));
  ok("🔴 #15: the Carbon planner's two step-5 reference tables wrap their cells (tbl-wrap; the figures stay on one line), so the Reference column no longer scrolls off",
     html.includes(".tbl.tbl-wrap td{white-space:normal;} .tbl.tbl-wrap td.num{white-space:nowrap;}")
     && src.includes('<table className="tbl tbl-wrap">\n                  <caption><b>How the plan compares</b>')
     && src.includes('<table className="tbl tbl-wrap">\n                  <caption><b>Transport only</b>')
     && (src.match(/className="tbl tbl-wrap"/g) || []).length === 2);
}

// ---- 17 Oct 2026 (D114): the Dashboard's default range is this month ± 6 -----------------------------------------------
{
  ok("⭐ D114: the Dashboard's From / To start from dashRangeDefault (this month ± DASH_RANGE_EITHER_SIDE), not month 1 and the last month",
     src.includes("const [fromM, setFromM] = useState(() => dashRangeDefault(months)[0]);")
     && src.includes("const [toM, setToM] = useState(() => dashRangeDefault(months)[1]);")
     && !src.includes("const [fromM, setFromM] = useState(1);") && !src.includes("const [toM, setToM] = useState(months.count);"));
  ok("D114: six months either side, clamped to the horizon, from the same 'this month' the Gate arrivals panel uses",
     src.includes("const DASH_RANGE_EITHER_SIDE = 6;")
     && src.includes("return [Math.max(1, c - DASH_RANGE_EITHER_SIDE), Math.min(n, c + DASH_RANGE_EITHER_SIDE)];")
     && /const dashRangeDefault = \(months\) => \{\s*const n = \(months && months\.count\) \|\| 60, c = gaMonthToday\(months\);/.test(src));
  ok("D114: one button between the default and the whole programme ('Whole programme' / 'This month ± 6'), not shown on the big screen",
     src.includes(">Whole programme</button>") && src.includes(">This month ± 6</button>")
     && src.indexOf(">Whole programme</button>") > src.indexOf('aria-label="To month"')
     && src.lastIndexOf("{!wall && <>", src.indexOf(">Whole programme</button>")) > src.lastIndexOf("</>}", src.indexOf(">Whole programme</button>")));
  ok("🔴 D114: only the Dashboard's range changed — the Gate arrivals and Simulation months still start at today's month",
     src.includes("const [gaMonth, setGaMonth] = useState(() => (initialGates && initialGates.month) || gaMonthToday(months));"));
  // 17 Oct 2026 (D114 fix): seen on live — the Dashboard opened on Jan 26 – Dec 30 because its first read of the lines
  // widened From / To to every month with lines, after the ± 6 default had been set
  ok("🔴 D114 fix: the Dashboard's first read no longer widens From / To to every month with lines; it keeps this month ± 6 "
     + "and falls back to the lines' own months only when none falls inside it",
     src.includes("if(idx.length && !idx.some(m => m >= lo && m <= hi)){ setFromM(Math.min(...idx)); setToM(Math.max(...idx)); }")
     && src.includes("const [lo, hi] = dashRangeDefault(months);")
     && src.includes('const all = j.lines || [], ap = all.filter(x => x.status === "Approved");')
     && src.includes("const idx = (ap.length ? ap : all).map(x => x.month_index);")
     && !src.includes("if(idx.length){ setFromM(Math.min(...idx)); setToM(Math.max(...idx)); }"));
}

// ---- 17 Oct 2026 (UI fix 4, claude/ui-fix-captions): captions, status words, chips and small captions (findings 3, 19, 20; decisions 1–3) ----
{
  const _fw = code.slice(code.indexOf("function FuelWidget("), code.indexOf("\n}\n", code.indexOf("function FuelWidget(")));
  const _ipt = code.slice(code.indexOf("function IptPill("), code.indexOf("function LaKpi("));
  const _cat = code.slice(code.indexOf("function CatChips("), code.indexOf("\n}\n", code.indexOf("function CatChips(")));
  ok("🔴 captions #3 (decision 1): ONE rule maps text-slate-400 to --muted outside the dark look, weighed with :where() so hover:text-slate-700 still wins; the dark remap keeps its line; a second rule steps the greys on a selected row (.bg-blue-50) to slate-600",
     html.includes('html:where(:not([data-theme="dark"])) .text-slate-400{color:var(--muted)}')
     && html.includes('html:where(:not([data-theme="dark"])) :where(.bg-blue-50,[style*="--navy-soft"],[style*="rgba(191, 46, 85"],[style*="rgba(191,46,85"]) .text-slate-400,html:where(:not([data-theme="dark"])) :where(.bg-blue-50,[style*="--navy-soft"],[style*="rgba(191, 46, 85"],[style*="rgba(191,46,85"]) .text-slate-500{color:#475569}')
     && (html.match(/\.text-slate-400\{/g) || []).length === 2 && html.includes('html[data-theme="dark"] .text-slate-400{color:#9AA1AB}')
     && code.includes("text-slate-400 hover:text-slate-700") && (code.match(/\btext-slate-400\b/g) || []).length >= 120);
  ok("captions #3: the rail's group headings have no opacity, the big screen's labels read --muted (no #9aa1ac), the Dashboard group title defaults to --muted (no #94a3b8), and no text-slate-300 is left in the markup — every placeholder reads slate-500 (the dark remap line went with it)",
     /\.rail-group\{[^}]*color:var\(--muted\);\}/.test(html) && !/\.rail-group\{[^}]*opacity/.test(html)
     && !/9aa1ac/i.test(html) && /\.dash-wallbar-lbl\{[^}]*color:var\(--muted\);\}/.test(html) && /\.dash-divider\{[^}]*color:var\(--muted\);/.test(html)
     && !code.includes('"#94a3b8"') && code.includes('style={{ color: tone || "var(--muted)" }}>{title}</div>')
     && !/\btext-slate-300\b/.test(code) && !html.includes(".text-slate-300{") && !html.includes(".text-emerald-600{")
     && (code.match(/<span className="text-slate-500">rate not set<\/span>/g) || []).length === 3);
  ok("decision 3: the Submit strip's peak values carry no colour of their own (the label says Peak)",
     !code.includes("text-[color:var(--gold)]") && code.includes('<div className="text-lg font-bold tabular-nums">{value}</div>') && code.includes(".map(([label, value]) => (") && !code.includes('"peak"]'));
  ok("decision 2: the green status WORDS read --ok-text, never --green — In force, Delivered %, the CatChips 'in' chip, the Routes vehicle chips, the set / held / routed tags, the simulation's checks; the red chip words read --bad-text; the stale chip --warn-text",
     code.includes('<span className="font-semibold" style={{ color: "var(--ok-text)" }}>In force</span>') && !code.includes("text-emerald-600")
     && code.includes('<span style={{ color: "var(--ok-text)" }}>{r.deliveredPct.toFixed(0)} %</span>')
     && _cat.includes('const fg = dir === "in" ? "var(--ok-text)" : "var(--navy)";')
     && code.includes('["rgba(3,158,134,.12)", "var(--ok-text)"]') && code.includes('["rgba(191,46,85,.12)", "var(--bad-text)"]') && code.includes('["#f1f5f9", "#475569"]')
     && code.includes(': has ? ["routed", "var(--ok-text)"] : null;') && code.includes('color: "var(--ok-text)" }}>set</span>') && code.includes('style={{ color: "var(--ok-text)", background: "rgba(3,158,134,.12)" }}>held</span>')
     && /\.sim-ok\{color:var\(--ok-text\);/.test(html) && /\.sim-tl-ok\{[^}]*fill:var\(--ok-text\);\}/.test(html) && html.includes(".sim-warn{color:var(--warn-text);}")
     && !/color: "var\(--green\)"/.test(code) && !/color:var\(--green\)/.test(html) && !/fill:var\(--green\)/.test(html)
     && code.includes('style={{ background: "rgba(197,48,48,.12)", color: "var(--bad-text)" }}>') && _fw.includes('color: "var(--warn-text)", background: "rgba(217,119,6,.10)"'));
  ok("🔴 chips #19: the 9–10 px chips take the house 12 px (text-xs) — target / quote, stale, winter / thaw, the team and workstream pills, the Routes vehicle chips, the material categories, the gate direction (now the house navy-on-tint pair), set, gate blocked and haul — no 'text-[10px] … rounded-full' chip is left; the one text-[9px] left is the horizon's role word (finding 11, its own branch)",
     code.includes('const srcChip = (s) => s === "target" ? <span className="ml-1 text-xs font-semibold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">target</span>')
     && code.includes('<span className="ml-1 text-xs font-semibold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">quote</span>')
     && _fw.includes('<span className="ml-1 text-xs font-semibold px-1.5 py-0.5 rounded-full" style={{ color: "var(--warn-text)"')
     && code.includes('className="ml-1 text-xs font-semibold px-1.5 py-0.5 rounded-full text-slate-600 bg-slate-100" title="No rate on this route')
     && code.includes('<span className="ml-1 text-xs text-slate-500" title="winter consumption uplift applied">winter</span>')
     && code.includes('<span className="ml-1 text-xs text-amber-700" title="Spring load restrictions')
     && _ipt.includes('<span className="text-xs text-slate-500">no {TEAM().toLowerCase()}</span>') && _ipt.includes('<span className="text-xs font-semibold px-1.5 py-0.5 rounded-full text-white"')
     && _ipt.includes('<span className="text-xs font-semibold px-1.5 py-0.5 rounded-full"\n    style={{ background: "var(--navy-soft)", color: "var(--navy)" }}>{ws}</span>')
     && !/text-\[(9|10|11)px\]/.test(_ipt) && !/text-\[(9|10|11)px\]/.test(_cat)
     && _cat.includes('<span key={c} className="text-xs px-1.5 py-0.5 rounded-full whitespace-nowrap"')
     && code.includes('className="text-xs font-semibold px-1.5 py-0.5 rounded-full whitespace-nowrap"\n            style={{ background: bg, color: fg }}>')
     && code.includes('<span className="rd-chip">\n                            {g.direction === "access" ? "in only"') && !code.includes("rgba(31,86,168,.1)")
     && code.includes('className="text-xs font-semibold px-1.5 py-0.5 rounded-full whitespace-nowrap"\n                          style={{ background: "rgba(3,158,134,.12)", color: "var(--ok-text)" }}>set</span>')
     && (code.match(/className="ml-1\.5 text-xs font-semibold px-1\.5 py-0\.5 rounded-full whitespace-nowrap"/g) || []).length === 2
     && !code.includes("text-[10px] font-semibold px-1.5 py-0.5 rounded-full") && !code.includes("text-[9px] font-semibold")
     && (code.match(/text-\[9px\]/g) || []).length === 1 && /text-\[9px\] uppercase tracking-wide text-slate-400">\{roleLbl\[role\]/.test(code));
  ok("after the first compare: the two slate-100 chips on Zones (Advisory, Not open) read slate-600 (slate-500 on slate-100 is 4.34:1), and the compact fuel card's two captions no longer truncate at 12 px (the BAF line carries its own hover title) — finding 11's clipped captions, brought forward because the 12 px made the clipping worse",
     !/bg-slate-100 text-slate-500|text-slate-500 bg-slate-100/.test(code)
     && code.includes('<span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600">Advisory</span>')
     && _fw.includes('<div className="text-xs uppercase tracking-wide text-slate-500 mt-0.5">') && _fw.includes('<div className="text-xs text-slate-500 mt-0.5" title={bafTxt}>{bafTxt}</div>')
     && !_fw.includes("text-slate-500 mt-0.5 truncate") && !_fw.includes('mt-0.5 truncate" title={bafTxt}'));
  ok("🔴 captions #20: the Config fuel widget has no 9, 10 or 11 px text (text-xs text-slate-500 captions, the DESNZ attribution among them) and its three admin buttons are btn-sec btn-sm; the Dashboard's figure labels and sub-lines, the Today card's captions and the group titles are 12 px; the never-rendered Kpi component is gone",
     !/text-\[(9|10|11)px\]/.test(_fw) && _fw.includes('const attribution = <span className="text-xs text-slate-500"') && (_fw.match(/className="btn-sec btn-sm disabled:opacity-40"/g) || []).length === 3
     && !_fw.includes("hover:bg-slate-50 disabled:opacity-40") && _fw.includes('<span className="text-xs uppercase tracking-wide text-slate-500">Diesel {country}</span>') && _fw.includes('<span className="w-full text-xs text-slate-500">The base is locked')
     && (code.match(/className="text-xs font-semibold uppercase tracking-wide text-slate-500 mt-0\.5 fig-label"/g) || []).length === 2 && !code.includes("text-[11px] font-semibold uppercase tracking-wide text-slate-400")
     && (code.match(/className="text-xs text-slate-500 fig-sub"/g) || []).length === 2 && !code.includes("text-slate-400 fig-sub")
     && (code.match(/className="text-xs font-semibold uppercase tracking-wide(?: mb-2)? fig-group"/g) || []).length === 2 && !/text-\[10px\] font-semibold uppercase tracking-wide(?: mb-2)? fig-group/.test(code)
     && code.includes('<div className="text-xs text-slate-500">{cw.from ? `week ') && code.includes('<div className="text-xs text-slate-500 mt-1">{bigNum(T.wkPlanT)}') && code.includes('<div className="text-xs text-slate-500 mt-1">{acct && acct.week ? `${acct.reported}')
     && !code.includes("function Kpi(") && !/\bKpi\b/.test(code));
}

// ---- 17 Oct 2026 (the user: UK drivers' hours): the words that state how trips a lorry a day are worked out ----------
// NARROWED 17 Oct 2026 (the review): a lorry's day, worked on one driver's 13 h (a longer shift is accepted, not
// refused); one break with the second 15 past 12 h; the planning-figure caveat
ok("⭐ Config → Planning: 'Shift hours a day' is a driver's working day, at most 13 h, the trips what fit after the "
   + "required breaks with driving at most 9 h; the old 'shift ÷ cycle time' is gone",
   src.includes("A lorry's working day. The trips it makes on a route are what fit in one driver's day of it, at most 13 hours (the 11-hour daily rest), after the break the UK drivers' hours rules require (45 min once driving passes 4½ hours or work passes 9, otherwise 30 min once work passes 6; 15 min more once work passes 12), with driving at most 9 hours. A longer shift is fine for a double-shifted lorry. A planning figure: weekly limits, night work and the day's other duties are not modelled.")
   && !src.includes("Caps the trips one vehicle can make on a route in a day: shift ÷ cycle time.")
   && !src.includes("A driver's working day, at most 13 hours (the 11-hour daily rest)."));
ok("⭐ the Routes table: Trips/day is what fits in a driver's day (driving = out, back and gate to face), § marks a route the "
   + "rules hold below the shift alone, the cell's title gives the server's words",
   src.includes("Trips/day is what fits in a driver's day: the {data.planning.shift_hours_per_day} h")
   && src.includes("9 h; loading, unloading and check-in are other work. § = fewer than the shift alone would hold (hover for why);")
   && src.includes('title={(r.lorry_day && r.lorry_day.words) || undefined} data-trips-limit={(r.lorry_day && r.lorry_day.limited_by) || undefined}')
   && !src.includes("Trips/day assumes a {data.planning.shift_hours_per_day} h"));
// 17 Oct 2026 (the review): § only where the rules took trips off (not on a 0 the shift alone would also give), the 0
// explained, the caveat and the 13 h note on the footnote
ok("⭐ the review: the Routes table's § marks only a route with fewer trips than the shift alone; the footnote explains a 0 "
   + "(one lorry a trip), says it is a planning figure and shows the 13 h note",
   src.includes('{r.lorry_day && r.trips_per_day < r.lorry_day.trips_without_rules ? <span className="text-slate-500">§</span> : null}')
   && !src.includes('r.lorry_day.limited_by !== "shift" ? <span className="text-slate-500">§</span>')
   && src.includes("a 0 is a round trip that does not fit a driver's day, counted as one lorry a trip. A planning figure: weekly")
   && src.includes('{data.planning.shift_note ? " " + data.planning.shift_note : ""}'));
ok("the info boxes and the Look-ahead's details say a driver's day; the Carbon page puts charging on top of the break",
   src.includes("the trips one vehicle can do in a driver's day on its route") && src.includes("what one vehicle does in a driver's day on that route")
   && !src.includes("the trips one vehicle can do in a shift on its route") && !src.includes("what one vehicle does in a shift on that route")
   && src.includes('c.lorry_day.limited_by === "driving" ? "the 9 h driving limit"')
   && src.includes('c.lorry_day.limited_by === "driver_day" ? "one driver\'s 13 h day"')
   // NARROWED 17 Oct 2026 (the review): charging is attended, so working time — on top of the break AND counted toward it
   && src.includes("charging time comes out of the shift. The driver attends it, so it counts as working time: it comes on top of the required break and counts toward it")
   && !src.includes("the required breaks, at most 9 hours"));
ok("🔴 no compliance claim on a screen: the drivers' hours words never say 'compliant' or 'legal'",
   !/drivers'? hours[^"`]{0,200}\b(compliant|compliance|legal)\b/i.test(src));

// ---- report ------------------------------------------------------------------
console.log();
for (const f of fail) console.log("  FAIL:", f);
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
