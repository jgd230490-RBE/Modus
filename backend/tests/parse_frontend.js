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
ok("the dashboard says how many line-months the km / CO₂e / fair totals exclude, in the header",
  _dbBody.includes("line-months on a baked route") && _dbBody.includes("exclude the {D.lines - D.baked} unbaked") && _dbBody.includes("No cached geometry for this vehicle"));
ok("🔴 fleet size is the SERVER's `vehicles` (a monthly peak of it), never demand ÷ capacity here",
  _dbBody.includes("a.peakVeh = Math.max(a.peakVeh || 0, r.vehicles)") && !_dbBody.includes("peakPerDay / a.capacityPerDay")
  && !_dbBody.includes("/ payload(") && !_dbBody.includes("emisFactor(") && !_dbBody.includes("toTonnes("));
ok("the footnote says every figure comes from /api/costing/lines and how each is made",
  _dbBody.includes("Every planning figure on this page comes from <code>/api/costing/lines</code>") && _dbBody.includes("rounded up per line-month"));

// ---- 3. per-line model -------------------------------------------------------
ok("dashboard rows are keyed per line, not per route",
  _dbBody.includes("`${r.route_id}|${r.discipline || \"\"}|${r.section_id || \"\"}`"));
ok("dashboard shows a discipline column", src.includes('setSort("discipline")'));
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
ok("Sign out POSTs /api/gate-signout?keep=map and forgets the staff shape, so the next sign-in fetches /api/meta again",
  /const signOut = \(\) => \{[\s\S]{0,500}fetch\(`\$\{API\}\/gate-signout\?keep=map`, \{ method: "POST" \}\)\.catch\(\(\) => \{\}\);\s*\n\s*metaHadCode\.current = false;/.test(code));
// ⭐ THE INVARIANT. The <option value> is the canonical id; only the text changes.
ok("⭐ the picker's option VALUE is the canonical id, the text is the label",
  /<option key=\{v\} value=\{v\} disabled=[\s\S]{0,160}\{vehLabel\(v\)\}/.test(code));
// NARROWED 11 Oct 2026 (EU vehicles removed): English is the default, and an id IS a name in English (and in the
// European slot, as before), so only another language's fallback is starred — no star under English now.
ok("a fallback slot is marked, not passed off as a translation",
  /vehIsFallback\(v\) && !\["en", "eu"\]\.includes\(VEH\.lang\) \? " \*"/.test(code)
  && !/vehIsFallback\(v\) && VEH\.lang !== "eu" \? " \*"/.test(code));
ok("vehLabel falls back to the id itself", /\|\| v \|\| ""/.test(code));
ok("the save still posts the stored id", code.includes("vehicle_type: vehicle,"));
ok("tables show the label with the stored id in the title",
  code.includes('title={g.vehicle}>{vehLabel(g.vehicle)}'));
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
ok("11 Oct 2026: Config → Vehicles' Estonian column (an Estonian tenant's) shows the id as its placeholder, not 'falls back to EU'",
  !src.includes('placeholder="falls back to EU"') && code.includes('value={lab.ee || ""} placeholder={k}'));
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
ok("⭐ an unbaked route reads 'not baked', never a fleet size",
  code.includes('"not baked" : String(fleetOf(') && code.includes("not baked yet for"));
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
ok("...and it renders the LookAhead component",
  /page === "lookahead" && <LookAhead/.test(code));
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
ok("a planned day is editable while its week is not confirmed, this bucket or next",
  /const locked = w\.status === "confirmed"/.test(_laBody) && /\{!locked && editing === k \? \(/.test(_laBody) && /\) : !locked \? \(/.test(_laBody)
  && _laBody.includes('onClick={() => setEditing(k)}'));
ok("a confirmed week's plan is read-only", code.includes("Confirmed — reopen it to change the plan"));
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
ok("a week whose parent month changed says so",
  code.includes("parent month changed") && code.includes("parent_changed"));
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
  _laBody.includes("${ttName}: checked") && _laBody.includes("not checked since baking")
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
ok("...and the footer says so", _laBody.includes("Mon–Fri only — Sat/Sun are held at 0 and not shown"));
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
  && /if\(r\.geometry && r\.geometry\.length > 1\)\{/.test(_cmBody) && _cmBody.includes("Not drawn (no baked route)"));
ok("...colours lines by IPT from palette C, and is not rendered under the render harness",
  _cmBody.includes("IPT_PALETTE_C[iptKey(") && _laBody.includes("!initialPage && <CommitMap"));
ok("today's column carries the wash and the '· today' suffix",
  _laBody.includes('" · today"') && _laBody.includes('#eff6ff'));
// NARROWED (H1): the unit word is DU() — km, or mi for a tenant that reads miles
ok("the expanded row prints km/trip, km/week, t·km, cycle and € or 'rate not set' — in the tenant's unit",
  _laBody.includes("{grp(dist(c.km_trip))} {DU()}/trip") && _laBody.includes("{grp(dist(wd.tonne_km))} {TKM()} (") && _laBody.includes("cycle {grp(c.cycle_min)} min")
  && _laBody.includes('"rate not set"'));
ok("⭐ the honest-gap sentence for an unbaked line ships as written",
  _laBody.includes("{DU()} — until the route is baked · trips still from"));
ok("an unbaked line shows trips and NO vehicle count (the human's rule), never a 1",
  _laBody.includes("veh —") && _laBody.includes("Vehicles need a baked route"));
ok("the expand trigger is the Routes table's ▶ toggle, reused",
  _laBody.includes('{isOpen ? "▼" : "▶"}'));
ok("the empty state uses EmptyState", _laBody.includes("<EmptyState title={`No approved forecast line in the commit week"));
ok("planned days are saved through PUT /forecast-days with the day's key",
  /send\("\/forecast-days", \{ route_id: line\.route_id, month_index: line\.month_index,[\s\S]*?day_date: d\.day_date, planned_qty:/.test(_laBody)
  && _laBody.includes('"PUT"'));
// slice 4 — export
ok("⭐ export downloads through fetch + blob, never a bare <a href> (the access code is a header)",
  /fetch\(`\$\{API\}\/forecast-weeks\/export\?format=\$\{format\}&bucket=\$\{bucket\}`\)/.test(_laBody)
  && _laBody.includes("URL.createObjectURL(blob)") && !/href=\{`\$\{API\}\/forecast-weeks\/export/.test(code));
ok("...the mock's bar: Export XLSX beside the green Confirm week, PDF as a smaller second button",
  _laBody.includes(">Export XLSX<") && _laBody.includes('download("pdf")') && _laBody.includes('background: "var(--green)" }}>{anyConfirmed'));
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
           const h = i > 0 && j > i ? _laBody.slice(i, j) : ""; return h.length > 0 && !h.includes("Confirm week") && h.includes("No day columns here"); })());
ok("the Horizon footer states the weeks-not-days rule and the blue-column rule",
  _laBody.includes("stay week totals so hauliers are not sent a four-week daily spreadsheet") && _laBody.includes("That is the only week that materialises daily rows"));

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
  && /s\.capacity_qty == null \? <span className="text-slate-300">not recorded<\/span>/.test(_laBody));
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
ok("the re-bake loop has a guard against spinning forever", code.includes("guard++ < 200"));
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
ok("and the blocker text names what is wrong",
  src.includes("This route will not bake"));
ok("changing a gate warns that the cached geometry is now stale",
  src.includes("cached geometry now points at the old gate"));

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
  && code.includes('Submitted by ${teamText(g.submittedBy) || "—"}') && code.includes('Submitted by {teamText(g.submittedBy) || "—"}')
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
  src.includes("tick to bake, untick to remove"));

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
  ok("the confirm names the forecast lines a dropped vehicle leaves reading 'not baked'",
    body.includes("forecast_vehicles") && body.includes("not baked"));
  ok("...and warns when the last vehicle is being removed",
    body.includes("NO baked vehicle at all"));
}
ok("each tick-box says whether it will be baked, removed, or is already baked",
  code.includes('"will be baked"') && code.includes('"will be removed"'));
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
  _laBody.includes("+ BAF ${CUR()} ${grp(wd.eur_adj)}") && _laBody.includes("+ BAF {CUR()} {grp(r.planned_eur_adj)}")
  && _laBody.includes('r.rate_source === "target"') && _laBody.includes('c.rate_source === "target"'));
ok("...and the Account footer says the quote is never replaced and € var is against the quote",
  _laBody.includes("the quote is never replaced") && _laBody.includes("{CUR()} var compares the actual against the quote"));
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
  _laBody.includes("fair ${CUR()} ${grp(totals.fair_eur)} (model") && _laBody.includes("fair {CUR()} {grp(wd.fair_eur)}") && _laBody.includes("Fair {CUR()} <span")
  && _laBody.includes("{CUR()} {grp(r.planned_fair_eur)}"));
ok("...with the winter and thaw flags on the Account cell and the expanded row",
  _laBody.includes('(r.fair_flags || []).includes("WINTER")') && _laBody.includes('(r.fair_flags || []).includes("THAW")')
  && _laBody.includes('c.fair.flags.includes("THAW") ? ", thaw restrictions may apply"'));
ok("...an unbaked line prints — with the reason, never a number", _laBody.includes("No fair price: the route is not baked for this vehicle, or the diesel index is missing"));
ok("...and the footer calls it a floor for negotiation, never a quote", _laBody.includes("a floor for negotiation, never a quote"));
ok("the Config page hands the file document to the tab (for the fallback values)", code.includes("setFileDoc(j.file || null)"));

// ---- 11 Sep pm: the big-screen Dashboard ---------------------------------------------
const _tdBody = src.slice(src.indexOf("function DashboardToday("), src.indexOf("function DashboardStockChart("));
ok("🔴 every KPI figure carries a title (hover) — none is bare",
  _dbBody.split("<Fig ").slice(1).length >= 16 && _dbBody.split("<Fig ").slice(1).every(chunk => chunk.slice(0, chunk.indexOf("/>")).includes("title=")));
ok("🔴 no KPI figure is truncated: no `truncate` on a Fig, the value is nowrap with a clamp() size, two per row",
  !/kpi-num[^"]*truncate/.test(_dbBody) && _dbBody.includes('kpi-num font-bold whitespace-nowrap') && _dbBody.includes('fontSize: "clamp(')
  && _dbBody.includes('<div className="grid grid-cols-2 gap-x-4 gap-y-3">{children}</div>'));
ok("millions print compact (bigNum) with the exact figure in the title",
  /const bigNum = /.test(src) && _dbBody.includes("bigNum(K.totT)") && _dbBody.includes("`${grp(K.totT)} t —"));
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
  _tdBody.includes('<CommitMap meta={meta} bucket="commit"') && src.includes("function CommitMap({ meta, bucket, tick, lines, title, height, flush })")
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
  && _dbBody.includes("onClick={() => pick(r.key)}") && _dbBody.includes("pick(topN[els[0].index].key)")
  && _dbBody.includes("✕ show all") && _dbBody.includes("filtered.forEach(r => {") && _dbBody.includes("narrowed.forEach(r => {"));
ok("a Delivered-against-plan chart (planned t as bars, reported t over them) and a Delivered column in the table",
  _dbBody.includes("Delivered against plan") && _dbBody.includes("actualM") && _dbBody.includes('setSort("deliveredPct")'));
ok("nothing on the Dashboard writes", !/fetch\(`\$\{API\}[^`]*`,\s*\{\s*method/.test(_dbBody + _tdBody + _dsBody));

// ---- 2026-09-14: the user guide is reachable from the app --------------------
// It has been served at /help/ since 10 Sep and NOTHING linked to it: the only way in
// was to type the URL. That is why the human could not find it.
ok("\u2b50 the rail links to the user guide at /help/, exactly once",
   (src.match(/href=\{"\/help\/\?role="/g) || []).length === 1);
ok("...carrying the signed-in role, so the guide opens on the right view",
   /href=\{"\/help\/\?role=" \+ encodeURIComponent\(\(role && role\.role\) \|\| ""\)\}/.test(src));
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
   && (src.match(/\{ key: "(?:today|kpis|charts|stock)",/g) || []).length === 4);
ok("0915: every one of the four is wrapped, and each wraps a DIFFERENT index",
   (src.match(/<WallSection show=\{sectionShown\(/g) || []).length === 4
   && [0, 1, 2, 3].every(i => new RegExp(`sectionShown\\(${i}\\)`).test(src)));
ok("0915: 🔴 a hidden section is HIDDEN, not unmounted — the Mapbox instance survives",
   // the wrapper renders its children unconditionally and toggles `hidden`
   /<div ref=\{ref\} hidden=\{!show\} data-wall-section/.test(src)
   && !/\{show && <DashboardToday/.test(src) && !/sectionShown\(0\) && </.test(src)
   // and [hidden] is forced in the STYLESHEET (not the script block), because a Tailwind
   // utility on the same element would otherwise win
   && /\[hidden\]\{display:none !important;\}/.test(html));
ok("0915: ...and a section coming back into view is told to re-measure",
   /requestAnimationFrame\(\(\) => \{ try \{ window\.dispatchEvent\(new Event\("resize"\)\)/.test(src)
   && /cancelAnimationFrame\(id\)/.test(src));
ok("0915: the WORKING view always shows all four, whatever the big screen remembered",
   /const sectionShown = \(i\) => !wall \|\| wallLayout === "all" \|\| wallSection === i;/.test(src));
ok("0915: the rotate timer runs only on the big screen, and is cleared",
   /if\(!wall \|\| wallLayout !== "rotate"\) return;/.test(src)
   && /setInterval\(\(\) => setWallSection\(s => \(s \+ 1\) % DASH_SECTIONS\.length\), rotateSecs \* 1000\)/.test(src)
   && /return \(\) => clearInterval\(id\);/.test(src));
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
ok("...and it collapses with the rail like every other item (label behind railOpen)",
   /\/help\/\?role=[\s\S]{0,460}?\{railOpen && <span className="truncate">User guide<\/span>\}/.test(src));

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
  const guideFn = (src.match(/function Guide\(\{ page, groups \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
  ok("Guide is a component", guideFn.length > 500);
  ok("🔴 the guide shows ONLY on a demo tenant (TENANT.demo_notice), so a real client never sees it",
     /useEffect\(\(\) => \{\n    if\(!TENANT\.demo_notice\) return;/.test(guideFn));
  // 11 Oct 2026 NARROWED: with no tour running it renders only the hints (the strip and the dots), never a card
  ok("...and renders only the hints when there is no step (no card)", guideFn.includes("if(!step) return hintsEl;")
     && guideFn.includes("const hintsEl = (hints && !step) ? ("));
  ok("the welcome's menu line is built from the groups the ROLE can see (not from NAV)",
     guideFn.includes("(groups || []).map(g => `${g.group} (${g.items.map(it => it.label.toLowerCase()).join(\", \")})`)")
     && /<Guide page=\{page\} groups=\{visible\} \/>/.test(src));
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
  ok("the carbon tooltip and the Config sub-line say DESNZ 2026, not DEFRA (checked against gov.uk 9 Oct 2026)",
     !/DEFRA/.test(src) && /DESNZ 2026 kg CO₂e per vehicle-km \(average laden, both legs, from Config\)/.test(src));
  ok("the Dashboard figure and the Routes table say lorry-<unit>, the bake table says HGV params",
     /label=\{`lorry-\$\{DU\(\)\}`\}/.test(src) && />Lorry-\{DU\(\)\}\{arrow\("km"\)\}<\/th>/.test(src) && />HGV params<\/th>/.test(src));
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
  ok("...and the page switch renders CarbonPage", /page === "carbon" && <CarbonPage meta=\{meta\} access=\{role\} who=\{who\} \/>/.test(code));
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
     cb.includes('unrouted > 0 ? `${unrouted} plan line${unrouted === 1 ? " has" : "s have"} no route distance yet: transport not counted (Bake on the Routes page)` : ""')
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
  ok("the tables use the app's .tbl style with a caption, and the NH category takes NH's own name for waste",
     (cb.match(/<table className="tbl">/g) || []).length === 3 && (cb.match(/<table\b/g) || []).length === 3 && (cb.match(/<caption><b>/g) || []).length === 3
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
  const _laGrid = _laBody.slice(_laBody.indexOf('<table className="tbl compact"'), _laBody.indexOf("</table>", _laBody.indexOf('<table className="tbl compact"')));
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
    const gf = (src.match(/function Guide\(\{ page, groups \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
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
      && appFn.includes('const barGuide = (view === "login" || view === "resume") ? null : onMap ? (mapTour ? startMapTour : null) : replayAppGuide;'));
    ok("🔴 a reload with a stored code starts on resume and re-checks it with /api/auth, never trusting it unchecked",
      appFn.includes('const [view, setView] = useState(() => ACCESS.code ? "resume" : "public");')
      && appFn.includes('body: JSON.stringify({ code: ACCESS.code }) })')
      && appFn.includes('.then(info => { ACCESS.info = info; setRole(info); setView("portal"); })')
      && (appFn.match(/setView\("portal"\)/g) || []).length === 2);   // signIn() and the checked resume, nowhere else
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
      portalFn.includes('{page !== "map" && <Guide page={page} groups={visible} />}') && (src.match(/<Guide /g) || []).length === 1
      && !/\n  map: \[/.test((src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1]));
    ok("a page with no steps of its own (Config) replays the welcome, so the bar's Guide never does nothing",
      /const startTour = \(\) => \{ setTip\(null\); setSteps\(build\(guideRead\("welcome"\) !== "done" \|\| !\(GUIDE_STEPS\[key\] \|\| \[\]\)\.length\)\); setI\(0\); \};/.test(src));
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
    const lg = (src.match(/function Login\(\{ onSignIn, onBack, savedName \}\)\{([\s\S]*?)\n\}\n/) || ["", ""])[1];
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
    _fcBody.includes('<table className="tbl">') && _fcBody.includes("<caption><b>Forecast lines</b> · {sortCaption}")
    && _fcBody.includes('th(units.size === 1 ? `Total (${unitLabel([...units][0])})` : "Total", "quantity", true)')
    && _fcBody.includes('<td className="num">{fmt(g.quantity, g.unit)}') && _fcBody.includes('const [sort, setSort] = useState({ key: "quantity", dir: "desc" });'));
  ok("...a filter row with applied-filter chips and Clear all above the table; the status chips left the page header",
    _fcBody.includes('<div className="filter-row" data-guide="forecast-status">') && _fcBody.includes("<AppliedChips chips={applied} onClear={clearOne} onClearAll={clearAll}")
    && _fcBody.includes("const clearAll = () => setF({ status: \"ALL\", ipt: \"ALL\", discipline: \"ALL\", mine: false, q: \"\" });")
    && !_fcBody.includes("badge(s)"));
  ok("...Approve is the one visible action; Reject, Edit and Withdraw sit behind the row menu; status is a word with a dot",
    _fcBody.includes('<details className="row-menu">') && _fcBody.includes(">Reject…</button>") && _fcBody.includes(">Edit in Submit forecast</button>") && _fcBody.includes(">Withdraw…</button>")
    && _fcBody.includes("<StatusWord status={g.status} />") && _fcBody.includes('className="btn-pri btn-sm mr-1">Approve</button>'));
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
  // 1. the one-screen Dashboard
  ok("Dashboard: the working view is six cards, four charts, and five collapsed sections; the big screen keeps its four WallSections",
    (_dbWork.match(/<Card label=/g) || []).length === 6 && _dbWork.includes('<div className="dash-cards" data-guide="dash-figures">')
    && (_dbWork.match(/<details className="dash-more"/g) || []).length === 5 && (_dbWork.match(/<ChartCanvas config=/g) || []).length === 8
    && (_dbWall.match(/<WallSection show=\{sectionShown\(/g) || []).length === 4 && (_dbWall.match(/<ChartCanvas config=/g) || []).length === 8);
  ok("...the six cards: material, deliveries a day (11 Oct: one delivery = one two-way movement; working days from Config), vehicles needed, planned this week, delivered against plan, transport carbon",
    ['label="Material in view"', 'label="Deliveries a day"', 'label="Vehicles needed"', 'label="Planned this week"', 'label="Delivered against plan"', 'label="Transport carbon"'].every(t => _dbWork.includes(t))
    && _dbBody.includes("const wdPerMonth = +(((factors || {}).planning || {}).working_days_per_month || 22);") && _dbBody.includes("const loadsPerDay = K.totTrips / (nMonths * wdPerMonth);"));
  ok("...a collapsed section re-measures what it holds when opened (Mapbox and Chart.js measure zero while hidden)",
    _dbBody.includes('const onMore = (e) => { if(e.target.open) requestAnimationFrame(() => { try { window.dispatchEvent(new Event("resize")); } catch(err){} }); };')
    && (_dbWork.match(/onToggle=\{onMore\}/g) || []).length === 5);
  ok("...three filters in the header, the rest behind More filters, applied chips with Clear all",
    _dbBody.includes(">More filters ▾</summary>") && _dbBody.includes('<div className="row-menu-list dash-filters">') && _dbBody.includes("{!wall && <AppliedChips chips={applied} onClear={clearOne} onClearAll={clearAll}"));
  // 3. the Look-ahead grid
  ok("Look-ahead: the commit grid is a compact .tbl with a caption, the row named in words, a Week column, a Status column and a totals row",
    _laGrid.includes("<caption><b>Planned quantity by day</b>") && _laGrid.includes("Route · {TEAM().toLowerCase()} · section</th>")
    && _laGrid.includes('<th className="num">Week</th>') && _laGrid.includes("<th>Status</th>") && _laGrid.includes('<tr className="la-total">')
    && _laGrid.includes("<td><StatusChip s={w.status} parentChanged={w.parent_changed} /></td>"));
  ok("...the day cell is a figure until clicked, then an input that saves on blur, Enter or Escape",
    _laGrid.includes('<button type="button" className={"la-cell"') && _laGrid.includes('onBlur={() => { saveDay(line, d); setEditing(null); }}')
    && _laGrid.includes('onKeyDown={e => { if(e.key === "Enter" || e.key === "Escape") e.currentTarget.blur(); }}'));
  ok("🔴 no 9, 10 or 11 px text in the commit grid; status and flags are words with dots",
    !/text-\[(9|10|11)px\]/.test(_laGrid) && code.includes('<StatusWord status={s} label={s === "derived" ? "Derived"')
    && /function LineFlags\(\{ flags \}\)\{[\s\S]*?className="chip-st whitespace-nowrap"/.test(code));
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
    && code.includes("<Dashboard meta={meta} onWall={(on) => setRailOpen(!on)} onOpen={setPage} />")
    // NARROWED 11 Oct 2026 (gate arrivals: the render harness's prop initialGates joins the signature)
    && code.includes("function Dashboard({ meta, initialData, initialWeek, initialTarget, initialGates, onWall, onOpen })")
    && ctc.includes('{onOpen && <button type="button" className="btn-sec" onClick={() => onOpen("carbon")}>Open the Carbon planner</button>}'));
  ok("...the big screen's Carbon group gains ONE target figure in the group's own pattern (a Fig with a title); the working view's group is unchanged",
    (_dbWl.match(/<Fig value=\{ctW\.value\} label="tCO2e target, all-in" sub=\{ctW\.sub\} title=\{ctW\.title\} \/>/g) || []).length === 1
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
    && ctc.includes("`Target: a fixed cap of ${ctT(t.cap_t)} tCO2e for the whole scheme, ${ctSplit()}`")
    && ctc.includes("`Target: ${pct} below the approved plan, for the whole scheme, ${ctSplit()}`")
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
    && ctc.includes("The target is for the whole scheme, so they are not compared with it.") && !ctc.includes("with the scheme's cut applied to them.")
    && ctc.includes("const ctSplit = () => `not split by ${TEAM().toLowerCase()}`;") && !/\.ipt\b|IPT ?[1-6]|teamName\(|teamText\(/.test(ctc + mxCt));
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
  ok("⭐ the panel sits under the carbon strip and before the first collapsed section; the six cards, five sections, eight charts are untouched",
    _dbW.includes("<GateArrivalsPanel ga={ga} err={gaErr} month={gaMonth} months={months} onMonth={setGaMonth} />")
    && _dbW.indexOf("<GateArrivalsPanel") > _dbW.indexOf("<CarbonTargetStrip") && _dbW.indexOf("<GateArrivalsPanel") < _dbW.indexOf('<details className="dash-more"')
    && (_dbW.match(/<Card label=/g) || []).length === 6 && (_dbW.match(/<details className="dash-more"/g) || []).length === 5
    && (_dbW.match(/<ChartCanvas config=/g) || []).length === 8 && (_dbW.match(/onToggle=\{onMore\}/g) || []).length === 5);
  ok("the hooks sit before the early returns (React #310)",
    _dbc.indexOf("const [ga, setGa]") > 0 && _dbc.indexOf("const [ga, setGa]") < _dbc.indexOf("if(err) return")
    && _dbc.indexOf("const [gaMonth, setGaMonth] = useState(() => (initialGates && initialGates.month) || gaMonthToday(months));") < _dbc.indexOf("if(err) return")
    && _dbc.indexOf("fetch(`${API}/gates/arrivals") < _dbc.indexOf("if(err) return"));
  ok("🔴 the words: 'if arrivals are spread evenly', 'Queue likely', 'Spacing holds', 'No check-in time typed', 'coming to load', lorries not trucks; none of the banned words; no small, uppercase or colour-only text",
    gac.includes('const GA_SPREAD = "if arrivals are spread evenly";') && gac.includes('"Queue likely"') && gac.includes('"Spacing holds"')
    && gac.includes('"No check-in time typed"') && gac.includes("coming to load") && gac.includes('"not typed"') && gac.includes("min a lorry")
    // 11 Oct 2026 (review): a pending-only gate (gap null) says so, before the check-in test, and never "one every —"
    && gac.includes('g.gap_minutes == null ? "No approved arrivals" : (g.gate_minutes == null ? "No check-in time typed" : "Spacing holds")')
    && gac.includes('{g.gap_minutes == null ? "no approved arrivals" : `one every ${gaMin(g.gap_minutes)} ${GA_SPREAD}`}')
    && gac.includes("all {TEAMS().toLowerCase()} together") && !/every \{TEAMS\(\)/.test(code)
    && gac.includes("Pending lines appear as a note until they are approved, then in the figures.")
    && gac.includes("lorries a day at each gate") && gac.includes("The gate arrivals did not load.")
    && !/\b(secure|trusted by|testimonials?|real-time|optimi[sz]\w*|predict\w*|telematics|live tracking|compliant|NH-approved|trucks?|booking|peak hour)\b/i.test(gac)
    && !/\bAI\b/.test(gac) && !/text-xs|text-\[(9|10|11|12)(\.\d)?px\]|uppercase/.test(gac) && !/style=\{\{ ?color/.test(gac));
  ok("🔴 red only, and always with a word: the chip's dot is var(--red) for flag 'red' and var(--chart-none) otherwise; no amber or gold token in the block",
    gac.includes('g.flag === "red" ? "var(--red)" : "var(--chart-none)"') && !/--gold|--amber|amber/.test(gac)
    && gac.includes('<span className="font-semibold">{gaFlagWord(g)}</span>') && gac.includes("title={g.reason}")
    && gac.includes('g.flag === "red" ? "Queue likely"') && gac.includes('data-ga-flag={g.flag || "none"}'));
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
    ["Arrivals a day", "Average gap", "Check-in", "Status"].every(l => gac.includes(`<td data-label="${l}"`))
    && /@media \(max-width:720px\)\{\.ga-table thead\{display:none;\}[^\n]*\.ga-table td\[data-label\]::before\{content:attr\(data-label\) ": ";/.test(html));
  const gsGa = (src.match(/const GUIDE_STEPS = \{([\s\S]*?)\n\};/) || ["", ""])[1];
  ok("the guide names the panel and the anchor exists",
    gsGa.includes('{ anchor: "dash-gates", title: "Gate arrivals.", body: "Lorries a day at each gate, every team together, and the average gap if arrivals are spread evenly." },')
    && src.includes('data-guide="dash-gates"'));
  ok("the footnote names the read and how the figure is made",
    _dbBody.includes("Gate arrivals come from <code>/api/gates/arrivals</code>") && _dbBody.includes("the gap is the shift's minutes ÷ arrivals, an average with no hourly peak")
    && _dbBody.includes("all {TEAMS().toLowerCase()} summed at the gate a lorry arrives by") && !_dbBody.includes("every {TEAMS()"));
  ok("the big screen is unchanged: still four sections, and the panel is not on it",
    !_dbWl.includes("<GateArrivalsPanel") && (_dbWl.match(/<WallSection show=\{sectionShown\(/g) || []).length === 4
    && (src.match(/\{ key: "(?:today|kpis|charts|stock)",/g) || []).length === 4);
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
    && _dbBody.includes("            <BulletinMenu months={months} />\n          </>}\n          <button type=\"button\" data-guide=\"dash-wall\"")
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
  ok("W1: both maps the app creates open on UK_VIEW (the Look-ahead map and the Routes / Zones map)",
     (html.match(/center: UK_VIEW\.center, zoom: UK_VIEW\.zoom/g) || []).length === 2
     && (html.match(/new window\.mapboxgl\.Map\(/g) || []).length === 2);
  const locFetch = (html.match(/fetch\(`\$\{API\}\/locations\/geojson`\)\.then\(r => r\.json\(\)\)\.then\(gj => \{([\s\S]*?)\n    \}\)\.catch/) || ["", ""])[1];
  ok("⭐ W1: the Routes / Zones map frames the scheme's locations the FIRST time they load, once (a ref), finite points only, inside a try",
     /const framedRef = useRef\(false\);/.test(html) && /if\(!framedRef\.current\)\{/.test(locFetch)
     && /\.filter\(c => Array\.isArray\(c\) && isFinite\(c\[0\]\) && isFinite\(c\[1\]\)\)/.test(locFetch)
     && /if\(pts\.length\)\{ framedRef\.current = true; try \{ m\.fitBounds\(boundsOf\(pts\), \{ padding: 60, maxZoom: 12, duration: 0 \}\); \} catch\(e\)\{\} \}/.test(locFetch)
     && (html.match(/framedRef\.current = true/g) || []).length === 1);
}

// ---- report ------------------------------------------------------------------
console.log();
for (const f of fail) console.log("  FAIL:", f);
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
