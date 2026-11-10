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
const la = between("function LookAhead({ meta, who, access, initialPage, initialView }){", "\nfunction CommitMap(");
const laGrid = la.slice(la.indexOf('data-rd-table="lookahead"'), la.indexOf("{/* 14 Oct 2026 (bundle G, W17): the committed week at each gate"));
const acct = la.slice(la.indexOf('view === "account" ?'), la.indexOf("{/* 10 Sep: what came OUT of each stockpile"));
const gw = between("function GatesWeek({ gw }){", "\n// the status pill column");

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
ok("...Account's shortfall card is the same tonnes, amber", acct.includes('<LaKpi value={`${grp(laShortT(account))} t`} tone={laShortT(account) > 0 ? "warn" : undefined} caption="short last week, not yet carried" />'));
ok("...a row is washed (amber) only when it is short past the share", acct.includes('const short = r.action === "spread" && !!r.short_flag;')
   && acct.includes('style={short ? { background: "rgba(217,119,6,.06)" } : {}}'));

// the gate charts
ok("⭐ 5: a gate chart's Copy / Download sit in its title row: ChartCanvas takes `head` and draws the buttons in the flow beside it",
   code.includes("function ChartCanvas({ config, height, size, title, scope, notools, head }){")
   && code.includes('return head ? <><div className="gw-head" data-chart-head="1"><div className="min-w-0">{head}</div>{tools}</div>{chart}</> : chart;')
   && /\.gw-head\{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;\}/.test(css));
ok("...the gate's name, closed note and capacity sentence are that head (no sentence left above the chart for the buttons to cover)",
   gw.includes("head={<>") && gw.indexOf("Can check in ${grp(g.capacity_per_day)} a day") > gw.indexOf("head={<>")
   && gw.indexOf("Can check in ${grp(g.capacity_per_day)} a day") < gw.indexOf("</>} />"));
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

console.log(`ui_fix_lookahead_calm.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  ✗ " + f)); process.exit(1); }
