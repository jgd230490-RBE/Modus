/* ui_fix_dash_figures.js — 24 Nov 2026, branch claude/dash-top-figures (the Dashboard rethink, task A1; John's three answers
 * of 24 Nov: "Direction A with small bar + with the condition accent at the top of the box as in directionn B, but not the
 * full box highlighted", the carbon target as the sixth figure, "Keep both" for the warning colour).
 *
 * The six top figures of the staff Dashboard: ONE ruled strip (six across from about 1,000 px of its own width, three on a
 * tablet, two on a phone), small ink bars under three figures, one bar to a plan mark under Delivered, a status (a shape and a
 * word) on four figures only, and a 4 px top edge in the status's colour on a figure that has one (no wash, no coloured
 * figure). The page's OWN helpers run against stand-in reads; no browser, no calendar.
 *
 * Its own file (the brief's rule 3). Every ⭐ check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
let ts, React, RDS;
try { ts = require("typescript"); React = require("react"); RDS = require("react-dom/server"); }
catch (e) { console.log("ui_fix_dash_figures.js: SKIPPED — typescript / react / react-dom not installed"); process.exit(0); }

const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); }
}
const fn = (name) => { const i = code.indexOf("\nfunction " + name + "("); const j = code.indexOf("\n}\n", i); return i < 0 ? "" : code.slice(i + 1, j + 3); };
const constLine = (name) => { const m = code.match(new RegExp("\\nconst " + name + " = [^\\n]*\\n")); return m ? m[0] : ""; };
const NAMES = ["dashCutWords", "DashBars", "DashPlanBar", "dashRoadShort", "dashLimitStatus", "dashWeekStatus", "dashShortPct", "dashDeliveredStatus", "dashTargetCell"];
const missing = NAMES.filter(n => !fn(n));
ok("⭐ the strip's helpers are top-level functions in the page: " + NAMES.join(", "), !missing.length, missing);
if (missing.length) { report(); }

// the page's own grp / monthAxis / ctT / ctOk / ctTeam, a stand-in TEAM
const prelude = [
  "const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];",
  "const TENANT = { team_label: 'Package' }; const TEAM = () => TENANT.team_label || 'Team';",
  (code.match(/\nconst grp = [\s\S]*?;\n/) || [""])[0],
  constLine("monthAxis"), constLine("ctT"), constLine("ctOk"), constLine("ctTeam"),
].join("\n");
const js = ts.transpileModule(prelude + "\n" + NAMES.map(fn).join("\n") + "\nreturn { " + NAMES.join(", ") + ", grp };",
  { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None } }).outputText;
const P = new Function("React", js.replace(/^"use strict";?/, ""))(React);
const draw = (el) => el ? RDS.renderToStaticMarkup(el) : "";
const words = (s) => String(s || "").split(/\s+/).filter(Boolean).length;

// ------------------------------------------------------------------ the grp the page uses (a guard on the prelude)
ok("the page's own grp is the one under test (12,345 with a comma)", P.grp(12345) === "12,345" && P.grp(3291.66, 1) === "3,291.7");

// ------------------------------------------------------------------ 1. a road limit's short name
ok("⭐ a limit's short name: its road number where the name has one, else up to its first comma, dash or bracket, at most 24 characters",
   P.dashRoadShort("B6047 Melton Road, Tilton on the Hill") === "B6047" && P.dashRoadShort("Uppingham Road (A47)") === "A47"
   && P.dashRoadShort("A606 Oakham Road") === "A606" && P.dashRoadShort("A1(M) junction 1") === "A1(M)"
   && P.dashRoadShort("Glenhills Boulevard, Leicester") === "Glenhills Boulevard"
   && P.dashRoadShort("Station Lane – the level crossing") === "Station Lane"
   && P.dashRoadShort("A very long road name with no road number at all") === "A very long road name w…"
   && P.dashRoadShort("") === "" && P.dashRoadShort(null) === "");
ok("...a word that only starts like a road number is not one (Bakery Lane, M1nor)", P.dashRoadShort("Bakery Lane") === "Bakery Lane" && P.dashRoadShort("Mill Lane") === "Mill Lane");

// ------------------------------------------------------------------ 2. Lorry movements a day against the traffic limits
const lim = (name, value, months) => ({ name, limit: { value, counts: "movements", basis: "day" }, months });
const over = { limits: [
  lim("B6047 Melton Road, Tilton", 150, { 16: { value: 159.4, state: "over" }, 17: { value: 152, state: "over" }, 15: { value: 140, state: "near" } }),
  lim("A606 Oakham Road", 400, { 16: { value: 405, state: "over" }, 14: { value: 390, state: "near" } }),
] };
const sOver = P.dashLimitStatus(over, 2026);
ok("⭐ any month over a limit → the square, 'Over a road limit'; the WORST month (highest share of its limit) is named: road · movements/limit · month",
   sOver && sOver.tone === "bad" && sOver.word === "Over a road limit" && sOver.line === "B6047 · 159/150 · Apr '27" && sOver.m === 16, sOver);
const sNear = P.dashLimitStatus({ limits: [lim("B6047 Melton Road", 150, { 12: { value: 140, state: "near" }, 13: { value: 146, state: "near" } }), lim("A606", 400, { 3: { value: 100, state: "ok" } })] }, 2026);
ok("⭐ only near a limit → the diamond, 'Near a road limit', the nearest month named", sNear && sNear.tone === "warn" && sNear.word === "Near a road limit" && sNear.line === "B6047 · 146/150 · Jan '27" && sNear.m === 13, sNear);
const sOk = P.dashLimitStatus({ limits: [lim("B6047", 150, { 3: { value: 90, state: "ok" } })] }, 2026);
ok("⭐ limits drawn, none near → the dot, 'Within road limits', no line", sOk && sOk.tone === "ok" && sOk.word === "Within road limits" && sOk.line === null && sOk.m === null, sOk);
ok("⭐ no limit drawn, no read yet, or a refused read (a team login) → no status at all",
   P.dashLimitStatus({ limits: [] }, 2026) === null && P.dashLimitStatus(null, 2026) === null && P.dashLimitStatus(undefined, 2026) === null && P.dashLimitStatus({}, 2026) === null);
ok("...a limit with no value counts for nothing (no divide by zero)", P.dashLimitStatus({ limits: [lim("B1", 0, { 2: { value: 5, state: "over" } })] }, 2026).tone === "ok");
ok("...whole movements with commas in the line (1,203/1,200)", P.dashLimitStatus({ limits: [lim("M1", 1200, { 1: { value: 1203.4, state: "over" } })] }, 2026).line === "M1 · 1,203/1,200 · Jan '26");

// ------------------------------------------------------------------ 3. Planned this week against last week's lines
ok("⭐ last week's lines short past the share (the server's short_flagged) → the diamond, 'N short last week'",
   JSON.stringify(P.dashWeekStatus({ lines: 22, delivered: 19, reported: 22, short_flagged: 3 })) === JSON.stringify({ tone: "warn", word: "3 short last week" }));
ok("⭐ NOT lines − delivered: two lines nobody reported and one short inside the share are not 'short' (ring, 'not reported')",
   JSON.stringify(P.dashWeekStatus({ lines: 22, delivered: 19, reported: 20, short_flagged: 0 })) === JSON.stringify({ tone: "none", word: "2 not reported last week" }));
ok("every line held → the dot, 'Every line held last week'", P.dashWeekStatus({ lines: 10, delivered: 10, reported: 10, short_flagged: 0 }).word === "Every line held last week");
ok("all reported, some short inside the share → the dot, 'None short last week'", JSON.stringify(P.dashWeekStatus({ lines: 10, delivered: 8, reported: 10, short_flagged: 0 })) === JSON.stringify({ tone: "ok", word: "None short last week" }));
ok("no lines last week, or no read → no status", P.dashWeekStatus({ lines: 0 }) === null && P.dashWeekStatus(null) === null);

// ------------------------------------------------------------------ 4. Delivered against plan
ok("⭐ the share comes from Config → Planning (planning.short_flag_pct); absent, blank or nonsense = 10",
   P.dashShortPct({ planning: { short_flag_pct: 15 } }) === 15 && P.dashShortPct({}) === 10 && P.dashShortPct(null) === 10
   && P.dashShortPct({ planning: { short_flag_pct: "" } }) === 10 && P.dashShortPct({ planning: { short_flag_pct: "x" } }) === 10 && P.dashShortPct({ planning: { short_flag_pct: -1 } }) === 10);
const dl = (pct, f) => JSON.stringify(P.dashDeliveredStatus(pct, f));
ok("⭐ within the share under plan → the dot, 'Within 10 % of plan' (95 %, and exactly 90 %)",
   dl(94.66) === JSON.stringify({ tone: "ok", word: "Within 10 % of plan" }) && dl(90) === JSON.stringify({ tone: "ok", word: "Within 10 % of plan" }));
ok("⭐ further under → the DIAMOND, 'More than 10 % under plan', never a square", dl(89.9) === JSON.stringify({ tone: "warn", word: "More than 10 % under plan" }) && dl(10) === dl(89.9));
ok("ahead of plan → the dot, 'Ahead of plan'; at plan → within", P.dashDeliveredStatus(104).word === "Ahead of plan" && P.dashDeliveredStatus(104).tone === "ok" && P.dashDeliveredStatus(100).word === "Within 10 % of plan");
ok("the organisation's own share is used and named (15 %, 7.5 %)", P.dashDeliveredStatus(86, { planning: { short_flag_pct: 15 } }).word === "Within 15 % of plan"
   && P.dashDeliveredStatus(92, { planning: { short_flag_pct: 7.5 } }).word === "More than 7.5 % under plan");
ok("nothing reported → no status", P.dashDeliveredStatus(null) === null && P.dashDeliveredStatus(undefined) === null);

// ------------------------------------------------------------------ 5. the carbon target's answer
const ct = (o, scope) => ({ target: { t: 1 }, status: Object.assign({ target_t: 14000, on_target_with_decisions: false, gap_with_decisions_t: -0.1,
  on_target_as_forecast: false, gap_as_forecast_t: 3291.66, invalid: "", scope: scope || "scheme" }, o || {}) });
const flat = (c) => ({ value: draw(React.createElement("span", null, c.value)).replace(/<\/?span>/g, ""), lines: c.lines, st: c.st, st2: c.st2, edge: c.edge });
const live = flat(P.dashTargetCell(ct(), false, false));
ok("⭐ the drawing's state: '0.1 t CO₂e under', dot 'With agreed decisions', diamond 'Over as forecast', 'by 3,291.7 t CO₂e'; the edge follows the FIGURE (green)",
   live.value === '0.1 t <small class="dc-unit">CO₂e under</small>' && JSON.stringify(live.st) === JSON.stringify({ tone: "ok", word: "With agreed decisions" })
   && JSON.stringify(live.st2) === JSON.stringify({ tone: "warn", word: "Over as forecast" }) && live.lines[0] === "by 3,291.7 t CO₂e" && live.edge === "ok", live);
const overC = flat(P.dashTargetCell(ct({ gap_with_decisions_t: 0.2, gap_as_forecast_t: 0.2 }), false, false));
ok("⭐ over with the decisions → '0.2 t CO₂e over', a DIAMOND 'With agreed decisions' (never a square), the edge amber",
   overC.value.includes("0.2 t") && overC.value.includes("CO₂e over") && overC.st.tone === "warn" && overC.edge === "warn" && overC.st2.word === "Over as forecast");
const onC = flat(P.dashTargetCell(ct({ on_target_with_decisions: true, on_target_as_forecast: true, gap_with_decisions_t: 0, gap_as_forecast_t: 0 }), false, false));
ok("on target both ways → 'On target', two dots, no 'by …' line", onC.value === "On target" && onC.st.tone === "ok" && onC.st2.word === "On target as forecast" && onC.lines[0] === null && onC.edge === "ok");
const underBoth = flat(P.dashTargetCell(ct({ gap_as_forecast_t: -40 }), false, false));
ok("under as forecast too → dot 'Under as forecast', 'by 40.0 t CO₂e'", underBoth.st2.tone === "ok" && underBoth.st2.word === "Under as forecast" && underBoth.lines[0] === "by 40.0 t CO₂e");
const noneSet = P.dashTargetCell({ target: null, status: null }, false, false);
ok("⭐ no target set → '—', 'none set yet', no status, the ink edge", noneSet.value === "—" && noneSet.lines[0] === "none set yet" && noneSet.st === null && noneSet.st2 === null && noneSet.edge === undefined);
const bad = P.dashTargetCell(ct({ invalid: "The decisions no longer fit the plan." }), false, false);
ok("⭐ the decisions no longer fit → '—', the ring 'Decisions no longer fit', the as-forecast answer kept, the ink edge",
   bad.value === "—" && JSON.stringify(bad.st) === JSON.stringify({ tone: "none", word: "Decisions no longer fit" }) && bad.st2.word === "Over as forecast" && bad.edge === null);
const team = P.dashTargetCell(ct({}, "team"), false, false);
ok("⭐ a team login → the line names 'your package's share' (the tenant's team word, never an id)", team.lines[0] === "by 3,291.7 t CO₂e · your package's share");
const scoped = P.dashTargetCell(ct(), false, true);
ok("⭐ a filter or Sites in view → 'whole scheme' (the target is never cut to a filter)", scoped.lines[0] === "by 3,291.7 t CO₂e · whole scheme");
ok("loading → '—' 'loading'; a failed read → '—' 'did not load'; neither has a status",
   P.dashTargetCell(null, false, false).lines[0] === "loading" && P.dashTargetCell(null, true, false).lines[0] === "did not load" && P.dashTargetCell(null, true, false).st === null);
ok("the cell decides nothing itself: it reads the server's verdicts (on_target_*, gap_*), never compares a figure with the target",
   /on_target_with_decisions/.test(fn("dashTargetCell")) && !/target_t\s*[-<>]/.test(fn("dashTargetCell")) && !/approved_t|(^|[^_a-z])with_decisions_t/.test(fn("dashTargetCell")));

// ------------------------------------------------------------------ 5b. Delivered against plan: to the last COMPLETE week
// (25 Nov 2026, John: "Yes, complete week"). The read gives the cut; the page names its Sunday and sums both sides to it.
ok("⭐ the cut's Sunday in words: '22 Nov'; no cut → null (no date invented)",
   P.dashCutWords({ month_index: 11, week_index: 3, ends: "2026-11-22" }) === "22 Nov" && P.dashCutWords({ ends: "2027-01-03" }) === "3 Jan"
   && P.dashCutWords(null) === null && P.dashCutWords({}) === null);
{
  const D = code.slice(code.indexOf("const D = useMemo(() => {"), code.indexOf("}, [data, status, material, vehicle, ipt, discipline, fromM, toM, unit, factors, months, lineKey"));
  ok("⭐ ONE base for the share wherever the Dashboard shows it: the figure, the route table's column and the chart all read planned_to_cut_t / actual_to_cut_t",
     D.includes("T.tCut += r.planned_to_cut_t || 0") && D.includes("if(r.actual_to_cut_t != null) T.actualCut = (T.actualCut || 0) + r.actual_to_cut_t;")
     && D.includes("deliveredPct: pctOf(T.actualCut, T.tCut)") && D.includes("a.actualCut * 100 / a.tCut")
     && D.includes("cutWords: dashCutWords(data.totals && data.totals.delivered_to)") && !/nowIdx|tNow/.test(D));
  ok("⭐ the page works no date out of the clock for this share (the cut comes from the read)", !/new Date\(\)/.test(D));
}
const cl = fs.readFileSync(path.join(ROOT, "backend", "costlines.py"), "utf8").replace(/\r\n?/g, "\n");
ok("⭐ the read: a complete week is one whose Sunday is before today, with an actual typed on a visible line; totals name it",
   cl.includes("if sun < today and (best is None or sun > best[2]):") && cl.includes('"delivered_to": ({"month_index": cut[0], "week_index": cut[1], "ends": cut[2].isoformat()} if cut else None),')
   && cl.includes('"planned_to_cut_t": round(p_cut, 3), "actual_to_cut_t":'));
ok("CLP monitoring keeps its own rule (D-I4): clp.py still shares the plan to its own latest typed week", fs.readFileSync(path.join(ROOT, "backend", "clp.py"), "utf8").includes("lw = _recorded_to(cl, shown, as_week=True)"));

// ------------------------------------------------------------------ 6. the small bars
const bars = draw(React.createElement(P.DashBars, { values: [10, 20, 40, 30], cur: 2 }));
ok("⭐ one bar a month, this month in ink (dc-cur), the rest grey (dc-oth), hidden from readers",
   (bars.match(/<rect /g) || []).length === 4 && (bars.match(/class="dc-cur"/g) || []).length === 1 && (bars.match(/class="dc-oth"/g) || []).length === 3
   && /aria-hidden="true"/.test(bars) && /data-dc-bars="4"/.test(bars) && !/dc-mark/.test(bars));
const marked = draw(React.createElement(P.DashBars, { values: [10, 20, 40, 30], cur: 1, mark: 2 }));
ok("⭐ a month over a road limit gets a small red square over its bar (Lorry movements a day)", /class="dc-mark" data-dc-mark="2"/.test(marked) && (marked.match(/<rect /g) || []).length === 5);
ok("no months or all zero → no bars at all", draw(React.createElement(P.DashBars, { values: [] })) === "" && draw(React.createElement(P.DashBars, { values: [0, 0] })) === "");
const plan = draw(React.createElement(P.DashPlanBar, { pct: 94.66 })), plan2 = draw(React.createElement(P.DashPlanBar, { pct: 160 }));
ok("⭐ Delivered: one ink bar to a 'plan' mark, the bar stopping at 110 % past it; none when nothing is reported",
   /data-dc-plan="95"/.test(plan) && />plan<\/text>/.test(plan) && /aria-hidden="true"/.test(plan) && /width="118\.0" height="10"/.test(plan2)
   && draw(React.createElement(P.DashPlanBar, { pct: null })) === "");

// ------------------------------------------------------------------ 7. the strip in the Dashboard
const dash = (() => { const i = code.indexOf("\nfunction Dashboard("); return code.slice(i, code.indexOf("\n}\n", i) + 3); })();
// NARROWED 25 Nov 2026 (the Dashboard rethink, B): the carbon target moved down the page (after the charts and Gate
// arrivals), so the strip is read up to the empty message that follows it
const strip = dash.slice(dash.indexOf('<div className="dash-cards-box">'), dash.indexOf("{D.empty && (pendingOnly"));
const keys = (strip.match(/<Card k="([a-z]+)"/g) || []).map(s => s.slice(9, -1));
ok("⭐ six figures in this order: Material in view, Lorry movements a day, Vehicles needed, Planned this week, Delivered against plan, Carbon target",
   JSON.stringify(keys) === JSON.stringify(["material", "movements", "vehicles", "week", "delivered", "target"]) && strip.includes('label="Carbon target"'), keys);
ok("⭐ GONE from the strip: the Transport carbon card, 'each in and out', the old 'of … lines held last week' line, the card's hover title",
   !strip.includes("Transport carbon") && !dash.includes('label="Transport carbon"') && !dash.includes("deliveries, each in and out")
   && !/lines held last week/.test(strip) && !/title=\{/.test(strip) && !dash.includes("const Card = ({ label, value, sub, info, tone })"));
const card = dash.slice(dash.indexOf("const Card = ("), dash.indexOf("const applied = ["));
ok("⭐ a status on FOUR figures only (Lorry movements, Planned this week, Delivered, Carbon target); Material and Vehicles have none",
   /<Card k="movements"[^]*?st=\{dcLim\}/.test(strip) && /<Card k="week"[^]*?st=\{wkTot \? dcWeek : null\}/.test(strip) && /<Card k="delivered"[^]*?st=\{dcDel\}/.test(strip)
   && /<Card k="target"[^]*?st=\{dcCt\.st\} st2=\{dcCt\.st2\}/.test(strip)
   && !/<Card k="material"[^>]*\bst=/.test(strip) && !/<Card k="vehicles"[^>]*\bst=/.test(strip));
ok("⭐ the status is the one chip (RowStatus: a shape and a word); the cell's edge follows the status, ink otherwise; no wash, no coloured figure",
   card.includes("<RowStatus tone={st.tone} word={st.word} />") && card.includes('" dc-" + ed') && card.includes('data-dash-edge={ed || "ink"}')
   && !/style=\{\{[^}]*color/.test(card) && !/background/.test(card));
ok("⭐ the bars: Material, Lorry movements (with the over month's mark), Vehicles; the plan bar under Delivered; none on a phone",
   /<Card k="material"[^]*?bar=\{<DashBars values=\{D\.tonnesM\} cur=\{dcCur\} \/>\}/.test(strip) && /<Card k="movements"[^]*?bar=\{<DashBars values=\{D\.tripsM\} cur=\{dcCur\} mark=/.test(strip)
   && /<Card k="vehicles"[^]*?<DashBars values=\{D\.vehM\}/.test(strip) && /<Card k="delivered"[^]*?<DashPlanBar pct=\{K\.deliveredPct\} \/>/.test(strip)
   && card.includes("{bar && !phone && <div className=\"dc-bar\">{bar}</div>}"));
ok("⭐ the label's last word is tied to its 'i' (it never wraps alone)", card.includes('<span className="dc-nw">{last}{info && <InfoTip'));
ok("⭐ the drawing's words: 'deliveries in and out', 'N loads · N of N held', 'X t of Y t', '% to <the cut's Sunday>' (25 Nov: John's complete week)",
   strip.includes("`${grp(Math.round(loadsPerDay))} deliveries in and out`") && strip.includes("loads${acct && acct.lines ? ` · ${grp(acct.delivered)} of ${grp(acct.lines)} held` : \"\"}")
   && strip.includes("`${bigNum(K.actualToCut)} t of ${bigNum(K.plannedToDate)} t`") && strip.includes('% <small className="dc-unit">to {K.cutWords}</small>'));
ok("⭐ the whole plan's share moved into Delivered's 'i' (no second line)", /dash\.fig\.delivered[^]*?% of the whole plan in view/.test(strip));

// ------------------------------------------------------------------ 8. the traffic limits read ONCE at load, shared with the fold
const tlEff = (() => { const a = dash.indexOf("const tlQ = "); return dash.slice(a, dash.indexOf("useEffect(() => {\n    if(!wall) return;", a)); })();
ok("⭐ the Dashboard reads the traffic limits once at load (planners and admins, never the big screen), keyed on the range and Sites",
   tlEff.includes("if(initialLimits || wall || !canApprove) return;") && tlEff.includes("fetch(`${API}/traffic-limits?${tlQ}`)")
   && tlEff.includes("}, [tick, tlQ, wall, canApprove]);") && /const tlQ = `from=\$\{Math\.min\(fromM, toM\)\}&to=\$\{Math\.max\(fromM, toM\)\}`/.test(tlEff));
ok("⭐ a read for another range never colours the figure (it waits for its own)", dash.includes('tl._q === "initial" || tl._q === tlQ'));
const td = fn("TrafficDash");
ok("⭐ the Traffic limits fold takes the Dashboard's read (`shared`) and makes no second one; alone it still reads on first open",
   td.includes("if(!open || shared) return;") && td.includes("const data = shared ? shared.data : own, err = shared ? shared.err : ownErr;")
   && dash.includes("shared={{ data: tl, err: tlErr }} />") && (dash.match(/traffic-limits\?/g) || []).length === 1);
ok("a test can hand the Dashboard its read (initialLimits), as it does the week and the target", dash.startsWith("\nfunction Dashboard({ meta, initialData, initialWeek, initialTarget, initialGates, initialClp, initialLocations, initialQueue, initialLimits,"));

// ------------------------------------------------------------------ 9. the look
ok("⭐ ONE ruled strip: no box, a hairline under it; each cell a 2 px ink top edge, 4 px in --green / --gold / --red with a status",
   /\.dash-cards\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\);gap:0;border:0;border-bottom:1px solid var\(--line\);border-radius:0;background:none;/.test(html)
   && /\.dash-cards \.dash-card\{border:0;border-radius:0;box-shadow:inset 1px 0 0 var\(--line\),inset 0 2px 0 var\(--ink\);/.test(html)
   && /\.dash-card\.dc-ok\{box-shadow:inset 1px 0 0 var\(--line\),inset 0 4px 0 var\(--green\);\}/.test(html)
   && /\.dash-card\.dc-warn\{box-shadow:inset 1px 0 0 var\(--line\),inset 0 4px 0 var\(--gold\);\}/.test(html)
   && /\.dash-card\.dc-bad\{box-shadow:inset 1px 0 0 var\(--line\),inset 0 4px 0 var\(--red\);\}/.test(html));
ok("⭐ the columns follow the strip's OWN width: two, three from 560 px, six from 1,000 px (his 1150 px window, rail folded: 1,045 px)",
   html.includes(".dash-cards-box{container-type:inline-size;}") && /@container \(min-width:560px\)\{\.dash-cards\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\);\}/.test(html)
   && /@container \(min-width:1000px\)\{\.dash-cards\{grid-template-columns:repeat\(6,minmax\(0,1fr\)\);\}/.test(html));
ok("⭐ six across: one label line (no wrap); otherwise two lines reserved so the figures line up", /@container \(min-width:1000px\)\{[^@]*\.dash-cards \.dash-card-l\{min-height:1\.3em;white-space:nowrap;\}/.test(html)
   && /\.dash-card-l\{[^}]*min-height:2\.6em/.test(html));
const hex = (s) => { const m = s.match(/#([0-9A-Fa-f]{6})/); return m ? m[1] : null; };
const lum = (h) => { const c = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const sparkL = hex((html.match(/\n    --spark:#[0-9A-Fa-f]{6};/) || [""])[0]);
const darkBlock = html.slice(html.indexOf('[data-theme="dark"]'));
const sparkD = hex((darkBlock.match(/--spark:#[0-9A-Fa-f]{6};/) || [""])[0]);
ok("⭐ the other months' grey (--spark) reads 3:1 or better in BOTH looks (on white; on the dark surface and page)",
   sparkL && sparkD && cr(sparkL, "FFFFFF") >= 3 && cr(sparkD, "1F2024") >= 3 && cr(sparkD, "141518") >= 3, [sparkL, sparkD]);
ok("the bars draw only from the look's tokens (ink, --spark, --red, --line-2, --muted)",
   /\.dash-cards \.dc-cur\{fill:var\(--ink\);\} \.dash-cards \.dc-oth\{fill:var\(--spark\);\} \.dash-cards \.dc-mark\{fill:var\(--red\);\} \.dash-cards \.dc-track\{fill:var\(--line-2\);\}/.test(html));

// ------------------------------------------------------------------ 10. the "i" boxes: two sentences and 30 words at most, no source
const info = code.split("const INFO = {")[1].split("\n};")[0];
const entry = (id) => { const m = info.match(new RegExp('"' + id.replace(/\./g, "\\.") + '": \\{ title: "[^"]*", text: "([^"]*)"')); return m ? m[1] : null; };
const ids = ["dash.material", "dash.deliveries", "dash.fig.vehicles", "dash.week", "dash.fig.delivered", "dash.fig.target"];
const long = ids.filter(id => { const t = entry(id); return !t || words(t) > 30 || (t.match(/[.!?](\s|$)/g) || []).length > 2; });
ok("⭐ each figure's 'i' is two sentences and 30 words at most", !long.length, long.map(id => [id, words(entry(id))]));
ok("...and names no supplier or source", !ids.some(id => /HERE|Mapbox|DESNZ|DfT|OpenStreetMap|STATS19|API|endpoint/.test(entry(id) || "")));
ok("the big screen keeps its own entries (dash.vehicles, dash.delivered, dash.carbon)", ['"dash.vehicles": {', '"dash.delivered": {', '"dash.carbon": {'].every(k => info.includes(k)));

// ------------------------------------------------------------------ 11. what this task does not touch
ok("the big screen, the carbon target strip and Gate arrivals are not this task's: still there as they were",
   // NARROWED 25 Nov 2026 (the Dashboard rethink, B): task B moved the carbon target and gave it its transport figure
   code.includes("<CarbonTargetStrip ct={ct} err={ctErr} onOpen={onOpen} scheme={sites.length > 0} transport={") && /\nfunction WallSection\(/.test(code) && /\nfunction GateArrivalsPanel\(/.test(code)
   && code.includes("const Fig = ({ value, label, sub, info, tone })"));

report();
function report() {
  console.log(`ui_fix_dash_figures.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
}
