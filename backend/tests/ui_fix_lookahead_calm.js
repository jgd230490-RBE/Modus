/*
 * ui_fix_lookahead_calm.js — the 9 Nov 2026 UI critique, wave 3, branch claude/ui-fix-lookahead-calm (the Look-ahead, its
 * Account tab and gate charts, and Submit).
 *
 *   Finding 5 / card 5: the Look-ahead opens on the plan, not alarm — a line short last week keeps its status (Confirmed),
 *     the shortfall is a second line under it (grey "1 t to carry", amber "Short 130 t last week" past the organisation's
 *     share, the server's SHORTAGE); every card's number with its noun and unit ("356 t short last week", amber, in tonnes);
 *     Account's Variance in words ("45.0 t short" / "40.0 t over", amber only past the share, never green); the gate
 *     charts' Copy / Download in the gate's title row; Config → Planning "Flag a shortfall over, %".
 *   Finding 6 / card 6: under Tonnes a concrete row reads tonnes (the server's figure) with its m³ as a small second line,
 *     and the total says what it includes ("Tonnes incl. concrete at 2.4 t/m³").
 *
 * Its own file (the wave rule, notes\ui-critique-1109.md §H). Source checks, plus laMixNote and laCarryLine run for real
 * (transpiled out of the page). Needs typescript through NODE_PATH; without it it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts;
try { ts = require("typescript"); } catch (e) { console.log("ui_fix_lookahead_calm.js: SKIPPED — typescript not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const css = html.slice(0, html.indexOf("</style>"));
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const la = between("function LookAhead({ meta, who, access, initialPage, initialView", "\nfunction CommitMap(");   // NARROWED 11 Nov 2026 (CLOCS C-F10 added a prop)
const laGrid = la.slice(la.indexOf('data-rd-table="lookahead"'), la.indexOf("{/* 14 Oct 2026 (bundle G, W17): the committed week at each gate"));
const acct = la.slice(la.indexOf('view === "account" ?'), la.indexOf("{/* 10 Sep: what came OUT of each stockpile"));
const gw = between("function GatesWeek({ gw, initialOpen }){", "\n// the status pill column");

// run a few of the page's own small functions for real (JSX → React.createElement, which we stub to plain objects)
const grab = (start) => { const i = code.indexOf(start); if (i < 0) return ""; let j = code.indexOf("\n}\n", i); return code.slice(i, j + 2); };
const grabLine = (start) => { const i = code.indexOf(start); return i < 0 ? "" : code.slice(i, code.indexOf("\n", i)); };
const grpSrc = (() => { const i = code.indexOf("const grp = (n, d) =>"); return i < 0 ? "" : code.slice(i, code.indexOf(";\n", i) + 1); })();
const src = [grpSrc, grabLine("const laQty = (x) =>"), grabLine("const laShortT = (a) =>"), grabLine("const laCarryKey = (r) =>"),
  grab("function laCarryLine(row, flagged){"), grab("function laMixNote(lines){")].join("\n");
let F = {};
try {
  const js = ts.transpileModule(src + "\nmodule.exports = { grp, laQty, laShortT, laCarryKey, laCarryLine, laMixNote };",
    { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const React = { createElement: (t, p, ...c) => ({ t, p: p || {}, c: c.flat() }) };
  const unitLbl = (u) => (u === "m3" ? "m³" : u);
  const m = { exports: {} };
  new Function("module", "exports", "React", "unitLbl", js)(m, m.exports, React, unitLbl);
  F = m.exports;
} catch (e) { fail.push("the page's small functions transpile and run  " + e.message); }
const text = (n) => n == null ? "" : typeof n === "string" || typeof n === "number" ? String(n) : (n.c || []).map(text).join("");

// ---------------------------------------------------------------- finding 5: the status keeps the week's state
const laStatusSrc = grab("function laStatus(flags, w){");
ok("⭐ 5: a shortage never takes a row's status: laStatus drops SHORTAGE before it ranks (the week's state shows, Confirmed)",
   laStatusSrc.includes('.filter(c => c !== "SHORTAGE")'));
ok("...and the grid's status cell draws last week's shortfall as a second line, by line, flagged only when the server raised SHORTAGE",
   laGrid.includes('{laCarryLine(carryBy[laCarryKey(line)], lf.some(f => f.code === "SHORTAGE"))}</td>')
   && la.includes("const carryBy = useMemo(() => { const g = {}; (account.rows || []).forEach(r => { g[laCarryKey(r)] = r; }); return g; }, [account]);"));
if (F.laCarryLine) {
  const q = F.laCarryLine({ remaining_short: 1, unit: "t" }, false), s = F.laCarryLine({ remaining_short: 130, unit: "t" }, true);
  const m3 = F.laCarryLine({ remaining_short: 8.5, unit: "m3" }, false);
  ok("⭐ 5: a small shortfall reads grey \"1 t to carry\"; one past the share amber \"Short 130 t last week\"; m³ keeps its unit",
     text(q) === "1 t to carry" && q.p.className === "la-carry" && text(s) === "Short 130 t last week" && s.p.className === "la-carry is-short"
     && text(m3) === "8.5 m³ to carry", `${text(q)} | ${text(s)} | ${text(m3)}`);
  ok("...nothing to carry draws nothing (a held line, an added one, no row)", F.laCarryLine({ remaining_short: 0, unit: "t" }, false) === null
     && F.laCarryLine(null, true) === null);
  ok("...the key leaves the month out (last week can be the month before)", F.laCarryKey({ route_id: "R1", discipline: "d", section_id: "WS1", month_index: 3 }) === "R1|d|WS1");
}
ok("🔴 5: no Look-ahead row says SHORT in capitals, and the shortage is amber, not red (laTone)",
   !/word: "SHORT"/.test(code) && code.includes('|| code === "SHORTAGE") ? "warn" : "bad";'));
ok("...the amber is the text-grade warning colour; the grey the muted one", /\.la-carry\{[^}]*color:var\(--muted\)/.test(css)
   && /\.la-carry\.is-short\{color:var\(--warn-text\);font-weight:600;\}/.test(css));

// the cards: every number with its noun and unit
ok("⭐ 5: the shortfall card is in tonnes and amber, \"short last week\" (no \"+296\", no red)",
   la.includes('<LaKpi value={`${grp(laShortT(account))} t`} tone={laShortT(account) > 0 ? "warn" : undefined} caption="short last week" />')
   && !la.includes("last week shortage") && !la.includes("`+${grp(account.shortfall)}`"));
if (F.laShortT) ok("...it reads the server's tonnes (shortfall_t), the old own-unit sum only from an older page",
   F.laShortT({ shortfall: 295.5, shortfall_t: 356.4 }) === 356.4 && F.laShortT({ shortfall: 12 }) === 12 && F.laShortT(null) === 0);
ok("...LaKpi has the amber tone (--warn-text)", code.includes('tone === "warn" ? "var(--warn-text)"'));
ok("⭐ 5 (card 5): the cards say loads, vehicles a day at the peak, t·mi on the routes, lines delivered last week",
   la.includes('caption="loads"') && la.includes('"vehicles a day at the peak"') && la.includes("caption={`${TKM()} on the routes`}")
   && la.includes('caption="lines delivered last week"') && !la.includes('caption="trips"') && !la.includes("· route basis"));

// Account
ok("⭐ 5: Account's Variance in words — \"45.0 t short\" / \"40.0 t over\" / \"on plan\" — amber only past the share, grey otherwise",
   acct.includes('`${grp(Math.abs(r.variance), 1)} ${unitLbl(r.unit)} ${r.variance > 0 ? "short" : "over"}`') && acct.includes('"on plan"')
   && acct.includes('style={{ color: r.short_flag ? "var(--warn-text)" : "var(--muted)" }}'));
ok("🔴 ...no green for over, no red for short, no bare \"+45.0\" left in the Variance cell",
   !acct.includes('r.variance > 0 && !r.held ? "var(--bad-text)" : "var(--ok-text)"') && !acct.includes('(r.variance > 0 ? "+" : "") + grp(r.variance, 1)'));
ok("...Account's shortfall card is the same tonnes, amber", acct.includes('<LaKpi value={`${grp(laShortT(account))} t`} tone={laShortT(account) > 0 ? "warn" : undefined} caption="short last week, not yet added to this week" />'));
ok("...a row is washed (amber) only when it is short past the share", acct.includes('const short = r.action === "spread" && !!r.short_flag;')
   && acct.includes('style={short ? { background: "rgba(217,119,6,.06)" } : {}}'));

// the gate charts
ok("⭐ 5: a gate chart's Copy / Download sit in its title row: ChartCanvas takes `head` and draws the buttons in the flow beside it",
   code.includes("function ChartCanvas({ config, height, size, title, scope, notools, head }){")
   && code.includes('return head ? <><div className="gw-head" data-chart-head="1"><div className="min-w-0">{head}</div>{tools}</div>{chart}</> : chart;')
   && /\.gw-head\{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;\}/.test(css));
ok("...the gate's name, closed note and capacity sentence are that head (no sentence left above the chart for the buttons to cover)",
   gw.includes("head={<>") && gw.indexOf('<div className="clp-note">{capWords(g)}</div>') > gw.indexOf("head={<>")
   && gw.indexOf('<div className="clp-note">{capWords(g)}</div>') < gw.indexOf("</>} />") && gw.includes("`Can check in ${grp(g.capacity_per_day)} a day"));
ok("...every other chart keeps its buttons in its box as before", code.includes("{!head && tools}</div>;"));

// Config
ok("⭐ 5: Config → Planning has \"Flag a shortfall over, %\" (planning.short_flag_pct), showing 10 when unset",
   code.includes('<label htmlFor="cfg-short_flag_pct">Flag a shortfall over, %</label>')
   && code.includes('value={"short_flag_pct" in (doc.planning || {}) ? ((doc.planning || {}).short_flag_pct ?? "") : 10}'));

// ---------------------------------------------------------------- finding 6: Tonnes never mixes units unseen
ok("⭐ 6: under Tonnes a non-tonne row reads tonnes (the server's derived.tonnes) with its own figure as a small second line",
   laGrid.includes('<span className="tabular-nums font-semibold text-slate-700" data-la-tonnes="1">{grp(f.tonnes, 1)} t<span className="la-sub">{grp(d.planned_qty, 1)}{own}</span></span>')
   && laGrid.includes('own && wd.tonnes != null ? <>{grp(wd.tonnes, 1)} <span className="text-slate-400 font-normal text-[13px]">t</span><span className="la-sub">{grp(w.planned_qty, 1)}{own}</span></>'));
ok("...an editable cell shows the same, and while typing the box is in the line's own unit (its label says m³)",
   laGrid.includes("? <>{grp(f.tonnes, 1)} t<span className=\"la-sub\">{grp(d.planned_qty, 1)}{own}</span></> : <>{grp(draft[k] ?? d.planned_qty, 1)}{own}</>}")
   && laGrid.includes("aria-label={`${dayName(d.day_date)}'s plan (${unitLbl(line.unit)})`}"));
ok("...the total row says what the tonnes include (Tonnes only)", laGrid.includes('{unitSel === "tonnes" && laMixNote(lines) && <span className="la-sub" data-la-mix="1">{laMixNote(lines)}</span>}'));
if (F.laMixNote) {
  const day = (q, t) => ({ planned_qty: q, derived: { tonnes: t } });
  const conc = { unit: "m3", material_type: "Ready-mixed concrete", days: [day(17, 40.8), day(0, 0)] };
  const conc2 = { unit: "m3", context: { material_type: "Ready-mixed concrete" }, days: [day(48, 115.2)] };
  const soil = { unit: "m3", material_type: "Earthworks / soil", days: [day(10, 16)] };
  const t = { unit: "t", material_type: "Small aggregate", days: [day(60, 60)] };
  ok("⭐ 6: \"Tonnes incl. concrete at 2.4 t/m³\" — the density from the server's own figures",
     F.laMixNote([t, conc, conc2]) === "Tonnes incl. concrete at 2.4 t/m³", F.laMixNote([t, conc, conc2]));
  ok("...no note when every line is in tonnes", F.laMixNote([t]) === "" && F.laMixNote([]) === "");
  ok("...two materials at two densities say so; a non-concrete m³ line is named as m³",
     F.laMixNote([t, conc, soil]) === "Tonnes incl. 2 lines in m³ at each material's density"
     && F.laMixNote([soil]) === "Tonnes incl. 1 line in m³ at 1.6 t/m³", `${F.laMixNote([t, conc, soil])} | ${F.laMixNote([soil])}`);
}
ok("🔴 6: the old Tonnes cell that printed a concrete row in m³ beside tonne rows is gone (a locked row reads tonnes when it has them)",
   laGrid.includes(") : own && f.tonnes != null ? ("));

// ---------------------------------------------------------------- finding 16 / mockup card 1: Submit opens on the route
const mx = (() => { const i = code.indexOf("function Matrix({ meta, who, editTarget, vehLang, access, initialCost, initialTarget }){");
  const j = code.indexOf("\nfunction ", i + 10); return i >= 0 && j > i ? code.slice(i, j) : ""; })();
const rvSrc = grab("function routeVehicle(route, allowed){");
let routeVehicle = null;
try {
  const js = ts.transpileModule(rvSrc + "\nmodule.exports = routeVehicle;", { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const m = { exports: {} }; new Function("module", "exports", "HIDDEN_VEHICLES", js)(m, m.exports, ["Hidden 3-axle"]); routeVehicle = m.exports;
} catch (e) { fail.push("routeVehicle transpiles and runs  " + e.message); }
if (routeVehicle) {
  const r = { route_id: "R013", distance_profile: "Artic Tipper (44t)" };
  ok("⭐ 16: a route opens on the vehicle it is worked out for when the material may go in it",
     routeVehicle(r, ["Rigid 8-wheeler (32t)", "Artic Tipper (44t)"]) === "Artic Tipper (44t)");
  ok("...not when the material may not (the material's first vehicle then, as before), nor a hidden one, nor an unrouted route",
     routeVehicle(r, ["Truck mixer 8 m³ (32t)"]) === "" && routeVehicle({ distance_profile: "Hidden 3-axle" }, ["Hidden 3-axle"]) === ""
     && routeVehicle({ route_id: "R1" }, ["Artic Tipper (44t)"]) === "" && routeVehicle(null, []) === "");
}
ok("...the Matrix asks for it on a route change and after a material change; a saved line still wins (its load sets the vehicle after)",
   mx.includes("setVehicle(v => suggestedVehicles.includes(v) ? v : (routeVehicle(route, suggestedVehicles) || firstShown(suggestedVehicles) || v));")
   && mx.includes("if(rv) setVehicle(rv);") && mx.includes("if(first.vehicle_type) setVehicle(first.vehicle_type);")
   && mx.indexOf("if(rv) setVehicle(rv);") < mx.indexOf("if(first.vehicle_type) setVehicle(first.vehicle_type);"));
ok("...and says so under the box: \"The vehicle the route is worked out for\"",
   mx.includes('{route && route.distance_profile === vehicle && <span className="block mt-1 text-[13px] text-slate-500" data-veh-hint="1">The vehicle the route is worked out for</span>}'));
ok("⭐ 16: a planner's Team opens on the route's team, follows the route until picked by hand, and says \"The route's team\"; a team login stays locked",
   mx.includes("if(!iptLocked && !iptByHand && route.ipt && ((access && access.ipts) || Object.keys(TEAM_LABELS)).includes(route.ipt)) setIpt(route.ipt);")
   && mx.includes("onChange={e => { setIpt(e.target.value); setIptByHand(true); }}")
   && mx.includes('{route && route.ipt && ipt === route.ipt && <span className="block mt-1 text-[13px] text-slate-500" data-team-hint="1">The route\'s {TEAM().toLowerCase()}</span>}')
   && mx.includes("<option value=\"\">— pick a {TEAM().toLowerCase()} —</option>") && mx.includes("{teamName(access.ipt)} <span className=\"text-slate-400 font-normal\">· your {TEAM().toLowerCase()}</span>"));
ok("🔴 16: the month boxes carry no grey \"0\" (it read as typed)",
   mx.includes('value={vals[mi] ?? ""} onChange={e => setMonth(mi, e.target.value)}\n') && !mx.includes('onChange={e => setMonth(mi, e.target.value)} placeholder="0"'));
ok("⭐ 16: until a month is typed the strip is one line, not six zeros",
   mx.includes('{!typedAny ? <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600" data-strip-empty="1">Type a month\'s quantity: the loads, lorries and price show here.</div> :')
   && mx.includes("const typedAny = inRange.some(([, q]) => +q > 0) || !!initialCost;"));
ok("⭐ 16: \"not routed\" only once the route's read has said so (never while it is on its way or after it failed)",
   mx.includes("const notRouted = tpvKnown && !(tripsPerVehicleDay > 0);") && mx.includes("setTpv(null); setTpvKnown(false);")
   && mx.includes("setTpvKnown(true);") && mx.includes("{!notRouted ? null : <div className=\"px-3 py-1.5 text-[13px] text-slate-500 bg-white\" data-foot=\"1\">")
   && !mx.includes("{tripsPerVehicleDay > 0 ? null : <div"));

// ---------------------------------------------------------------- 16 Oct item 24 / mockup card 2: the Account in words
const fw = between("function FuelWidget({ who, access, mode, initial, onChanged }){", "\nfunction ");
const fwStrip = fw.slice(fw.indexOf('if(mode === "strip"){'), fw.indexOf('if(mode === "compact"){'));
ok("⭐ 24: the Account's fuel line is a titled Fuel card — the price with its date, two labelled boxes, the surcharge in words",
   fwStrip.includes('<h3 className="text-sm font-semibold text-[color:var(--navy-deep)]">Fuel</h3>')
   && fwStrip.includes('{box("yard_eur_per_l", "Yard price per litre", "",') && fwStrip.includes('{box("share_pct", "Fuel share of the cost", "%",')
   && fwStrip.includes('<span className="block text-[13px] text-slate-500 mb-1">Fuel surcharge</span>')
   && fwStrip.includes(': sum.baf_reason === "no base" ? "Starts from the week you confirm"')
   && fwStrip.includes('% of the quote`') && fwStrip.includes('`against ${CUR()}'));
ok("🔴 24: no \"BAF:\", \"no base locked\", \"Yard £/L\" or \"Fuel share %\" on the Account's card (Config's own row is not this page's)",
   !/BAF|no base locked|Yard \$\{CUR\(\)\}\/L|Fuel share %|Index unavailable/.test(fwStrip) && fwStrip.length > 500
   && la.includes('<FuelWidget mode="strip" who={who} access={access} initial={page && page.costing} onChanged={() => setTick(t => t + 1)} />'));
ok("⭐ 24: the Account's cards in words — \"within 2 % of plan\", \"lines reported\", \"not yet added to this week\", \"can add their shortfall\"",
   acct.includes('caption="lines delivered last week, within 2 % of plan"') && acct.includes('caption={`moved · ${account.reported || 0} of ${account.lines || 0} lines reported`}')
   && acct.includes('"line can add its shortfall to this week" : "lines can add their shortfall to this week"')
   && !/98% band|open to calibrate|not auto|not yet carried/.test(acct));
ok("⭐ 24: the column is \"Difference\" (its info box too); one verb: Delivered, Added n t, Add to this week, Waiting",
   acct.includes('>Difference<InfoTip id="la.variance" /></th>') && code.includes('"la.variance": { title: "Difference",')
   && code.includes('"la.spread": { title: "Add to this week",')
   && acct.includes('{r.action === "held" && <RowStatus word="Delivered" tone="ok" />}')
   && acct.includes('{r.action === "applied" && <RowStatus word={`Added ${grp(r.carried, 1)} ${unitLbl(r.unit)}`} tone="none" />}')
   && acct.includes('>Add to this week</button>') && acct.includes('<span className="text-[13px] text-slate-500">Waiting</span>')
   && !/>held<|applied · |spread on this week|>waiting</.test(acct));
const hz = la.slice(la.indexOf("const hl = Object.values(g)"), la.indexOf('data-horizon-stock="1"'));
ok("⭐ 24: Account and Horizon name a line by its route's two ends, the code moving to the second line",
   la.includes("const ends = useMemo(() => laEnds(meta), [meta]);")
   && acct.includes('<div className="font-semibold text-[color:var(--navy-deep)]" data-la-ends={r.route_id}>{ends[r.route_id] || r.route_id}</div>')
   && acct.includes("{ends[r.route_id] && <span>{r.route_id}</span>}<IptPill ipt={r.ipt} />")
   && hz.includes('<div className="font-semibold text-[color:var(--navy-deep)]" data-la-ends={line.route_id}>{ends[line.route_id] || line.route_id}</div>')
   && hz.includes("{ends[line.route_id] && <span>{line.route_id}</span>}<IptPill ipt={line.ipt} />"));
const endsSrc = grab("function laEnds(meta){");
try {
  const js = ts.transpileModule(endsSrc + "\nmodule.exports = laEnds;", { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const m = { exports: {} }; new Function("module", "exports", js)(m, m.exports); const laEnds = m.exports;
  const e = laEnds({ routes: [{ route_id: "R001", origin: "Kilby Ridge Quarry", dest: "Harborough Compound" }, { route_id: "R9", origin: "A" }] });
  ok("...laEnds: \"Kilby Ridge Quarry → Harborough Compound\"; a route missing a name keeps its code; no meta, no names",
     e.R001 === "Kilby Ridge Quarry → Harborough Compound" && !("R9" in e) && Object.keys(laEnds(null)).length === 0, JSON.stringify(e));
} catch (err) { fail.push("laEnds transpiles and runs  " + err.message); }
ok("⭐ 24: on the Horizon a week not set yet reads grey, explained once in the heading (no \"derived ÷5\" in every cell)",
   la.includes('<div className="text-xs font-normal text-slate-500" data-hz-grey="1">Grey: the month spread evenly over its weeks</div>')
   && hz.includes('const grey = status == null;') && hz.includes('className={"tabular-nums " + (grey ? "text-slate-500" : "font-semibold text-slate-800")} data-hz-cell={grey ? "derived" : "set"}')
   && !/derived ÷/.test(la));

// ---------------------------------------------------------------- 16 Oct item 33 / mockup card 3: the gates as one list
const gwAll = between("function gwBusiest(g){", "\n// the status pill column");
ok("⭐ 33: every gate is one row of one list (no six-chart grid, no \"N more gates\" sentence), in the server's order (worst first)",
   gw.includes('<table className="tbl gw-table" data-gw-table="1">')
   && gw.includes('<thead><tr><th scope="col">Gate</th><th scope="col">Busiest day</th><th scope="col">Of what it can check in</th><th scope="col">Status</th></tr></thead>')
   && gw.includes("{gs.map(g => {") && !code.includes("GW_SHOW") && !gw.includes("data-gw-rest") && !gw.includes("more gate"));
ok("...a row: the gate's two names, its busiest day with its lorries, a thin bar against what it can check in, one status chip",
   gw.includes('<span className="gw-name">{g.location_name}<small>{g.gate_name}</small></span>')
   && gw.includes("<b>{grp(b.arrivals)}</b> lorr{+b.arrivals === 1 ? \"y\" : \"ies\"}<small>{b.day}</small>")
   && gw.includes('<div className="ga-pbar" aria-hidden="true"><i style={{ width: Math.max(2, Math.min(100, g.peak_pct)) + "%" }}></i></div>')
   && gw.includes("<span>{g.peak_pct} % of {grp(g.capacity_per_day)}</span>") && gw.includes("<td><RowStatus word={st.word} tone={st.tone} /></td>"));
ok("⭐ 33: the day chart is behind a real button on the row (aria-expanded), closed by default; the holding areas stay below the list",
   gw.includes('<button type="button" className="gw-open" aria-expanded={isOpen ? "true" : "false"} aria-controls={`gw-d-${g.gate_id}`}')
   && gw.includes("{isOpen && (") && gw.includes("useState(() => (initialOpen === true && gw && gw.gates ?")
   && gw.indexOf("data-gw-holding={h.id}") > gw.indexOf("</table>"));
try {
  const js = ts.transpileModule(gwAll.slice(0, gwAll.indexOf("function GatesWeek(")) + "\nmodule.exports = { gwBusiest, gwStatus };",
    { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const m = { exports: {} }; new Function("module", "exports", js)(m, m.exports); const G = m.exports;
  const days = [{ day: "Mon 9 Nov", arrivals: 37, open: true }, { day: "Tue 10 Nov", arrivals: 41, open: true }, { day: "Sat 14 Nov", arrivals: 90, open: false }];
  ok("...gwBusiest: the busiest OPEN day (a closed day's figure is not the gate's busiest)", G.gwBusiest({ days }).day === "Tue 10 Nov" && G.gwBusiest({ days: [] }) === null);
  ok("...gwStatus: Over capacity (bad), Queue likely (warn), No open time, Not compared, Within (ok)",
     G.gwStatus({ flag: "red" }).word === "Over capacity" && G.gwStatus({ flag: "red" }).tone === "bad"
     && G.gwStatus({ flag: "amber" }).word === "Queue likely" && G.gwStatus({ flag: "amber" }).tone === "warn"
     && G.gwStatus({ no_open_time: true, capacity_per_day: 0 }).word === "No open time"
     && G.gwStatus({ capacity_per_day: null }).word === "Not compared" && G.gwStatus({ capacity_per_day: 170 }).tone === "ok");
} catch (err) { fail.push("gwBusiest / gwStatus transpile and run  " + err.message); }

// ---------------------------------------------------------------- UI audit (10 Nov 2026): contrast on the washes this branch added
ok("⭐ audit: a chip on the Account's amber-washed row has a plain surface tint (navy on the tint over amber was 4.35:1)",
   html.includes('html:where(:not([data-theme="dark"])) :where([style*="rgba(217, 119, 6, 0.06)"],[style*="rgba(217,119,6,.06)"]) :where([style*="--navy-soft"],[style*="rgba(37, 99, 235, 0.08)"],[style*="rgba(37,99,235,.08)"]){background:var(--surface) !important}'));
ok("⭐ audit: a quantity's m3 line (.la-sub) steps to slate-600 on every wash (muted on the today column's blue was 4.27:1)",
   html.includes('[style*="rgba(217,119,6,.06)"]) .la-sub{color:#475569}')
   && html.includes('html:where(:not([data-theme="dark"])) :where(.bg-blue-50,[style*="--navy-soft"],'));

console.log(`ui_fix_lookahead_calm.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  ✗ " + f)); process.exit(1); }
