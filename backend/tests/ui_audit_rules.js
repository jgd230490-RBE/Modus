/* ui_audit_rules.js — 10 Nov 2026, branch claude/audit-measures-rules (FR1, notes\ux-programme-1109.md §3, A1a–A1c and A3).
 * The UX rules the browser audit measures, checked WITHOUT a browser, so CI runs it with the suite (ui_audit.js itself is
 * BROWSER_ONLY). What it proves:
 *   A. the in-page measures (lib/ui_rules.js ruleMeasures, pageReadyNow) fire on a made-up bad page and stay quiet on a good
 *      one, under jsdom with a small layout stub (jsdom draws nothing: boxes, the fold and the accent colour are stubbed —
 *      the same pages are measured in Google Chrome at the start of every audit run, which is the real test);
 *   B. the grading: long prose FAILS on a staff screen, warns elsewhere, is skipped on the guides and the landing pages, and a
 *      pinned block is a warning; more than one filled primary warns, one does not;
 *   C. the compare: an earlier run made before the measures pairs but gets no word / speed rows, and its rule findings read
 *      as FIRST MEASURED, not new; the 10 % / 25-word and 25 % / 1 s limits fire on the right side of each edge;
 *   D. the pinned list of long blocks may only shrink; the PR lines; the wiring in ui_audit.js (measured before the shot
 *      grows the viewport, the self-test at the start of every run, the measures kept out of the run's shape).
 * What it does not prove: what a real page measures (the audit's own runs do: notes\session-1110-audit-measures-rules.md).
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const R = require("./lib/ui_rules");
const ROOT = path.join(__dirname, "..", "..");
const audit = fs.readFileSync(path.join(__dirname, "ui_audit.js"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}

// ---------------------------------------------------------------- A. the measures on the made-up pages (jsdom) --------
// The layout stub: a box is 100 × 20 px at the top of the page unless its style sets a size; hidden (the attribute or
// display:none up the tree) is 0 × 0; data-fixture-top moves it down (a button below the fold). The accent: jsdom does not
// resolve var(--action), so a background of var(--action) (inline, or .btn-pri's rule) reads as the fixtures' #C2410C.
const ACTION = "rgb(194, 65, 12)";
function load(html) {
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true });
  const w = dom.window;
  const gcs = w.getComputedStyle.bind(w);
  w.getComputedStyle = (el, ps) => {
    const cs = gcs(el, ps);
    // ...only where the page defines the token, as a browser resolves it (a page without it leaves the probe transparent)
    const defines = [...w.document.querySelectorAll("style")].some(st => st.textContent.includes("--action:"));
    const usesAction = defines && !ps && el && el.matches && (el.matches(".btn-pri") || /var\(--action\)/.test(el.getAttribute("style") || ""));
    return new Proxy(cs, { get: (t, p) => p === "backgroundColor" && usesAction ? ACTION : (typeof t[p] === "function" ? t[p].bind(t) : t[p]) });
  };
  w.Element.prototype.getBoundingClientRect = function () {
    const zero = { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0 };
    for (let e = this; e && e.nodeType === 1; e = e.parentElement) { if (e.hidden || gcs(e).display === "none") return zero; }
    const at = this.closest("[data-fixture-top]"); const top = at ? +at.getAttribute("data-fixture-top") : 10;
    const cs = gcs(this); const W = parseFloat(cs.width), H = parseFloat(cs.height);
    const width = isNaN(W) ? 100 : W, height = isNaN(H) ? 20 : H;
    return { left: 0, top, right: width, bottom: top + height, width, height, x: 0, y: top };
  };
  w.scrollTo = () => {};
  return w;
}
const run = (w, fn, arg) => w.eval("(" + fn.toString() + ")")(arg);

for (const k of ["bad", "good"]) {
  const w = load(R.FIXTURES[k].html);
  const m = run(w, R.ruleMeasures, { blockWords: R.LIMITS.blockWords, proseShare: R.LIMITS.proseShare });
  const e = R.FIXTURES[k].expect;
  ok(`A1a: the ${k} page counts ${e.words} screen words (no table, chart, key, "i" box, field, fold, hidden or screen-reader-only text; figures left out)`,
     m.words === e.words, { words: m.words, skipped: m.skipped });
  ok(`A1b: the ${k} page has ${e.blocks} block(s) over ${R.LIMITS.blockWords} words${e.blockWords ? " (" + e.blockWords + " words)" : ""}`,
     m.blocks.length === e.blocks && (!e.blockWords || m.blocks[0].words === e.blockWords), m.blocks);
  ok(`A1c: the ${k} page has ${e.primaries} filled primar${e.primaries === 1 ? "y" : "ies"} on first view (a selected segment and a button below the fold not counted)`,
     m.primaries.length === e.primaries, m.primaries);
}
{
  const w = load(R.FIXTURES.bad.html);
  const m = run(w, R.ruleMeasures, {});
  ok("A1a: what is left out is counted apart (a table, chart text and a key, the open \"i\" box), so a run can say where the words went",
     m.skipped.table >= 33 && m.skipped.chart >= 66 && m.skipped.info >= 33 && m.skipped.figures >= 2, m.skipped);
  ok("A1c: a primary is recorded with its words and how it was found (the inline var(--action) and .btn-pri's computed colour)",
     m.primaries.map(p => p.text).join("|") === "Save plan|Send now" && m.primaries.every(p => p.how === "action"), m.primaries);
  const g = load(R.FIXTURES.good.html);
  ok("A1a: React's \"line\" + \"s\" (two text nodes of one element) read as one word, as drawn",
     /other forecast lines\b/.test(g.document.getElementById("split").textContent) && run(g, R.ruleMeasures, {}).words === 18);
  // run 1 (10 Nov 2026) read "planner).Different" as one word: text either side of a <br> in ONE element was joined with nothing
  const br = load(`<!doctype html><html><body><p id="b">Ask the planner.<br>Different words for each team, one after another, until the block runs well past the twenty five word limit set by the programme for this check.</p></body></html>`);
  const mb = run(br, R.ruleMeasures, {});
  ok("A1a / A1b: text either side of a <br> reads as two words, never merged (\"planner.\" and \"Different\")",
     mb.blocks.length === 1 && /planner\. Different/.test(mb.blocks[0].text) && mb.blocks[0].words === 29, mb.blocks);
  // a page without the accent (a guide, the landing page): a control filled with a strong colour and light text
  const plain = load(`<!doctype html><html><body><p>Two</p><button style="background:rgb(15,118,110);color:rgb(255,255,255);width:120px;height:32px">Request a demo</button>
    <button style="background:rgb(255,255,255);color:rgb(30,41,59);width:120px;height:32px">Plain</button>
    <button style="background:rgb(15,118,110);color:rgb(255,255,255);width:120px;height:32px">Second</button></body></html>`);
  const pm = run(plain, R.ruleMeasures, {});
  ok("A1c: on a page with no accent token, two strong-filled controls with light text count, a white one does not",
     pm.primaries.length === 2 && pm.primaries.every(p => p.how === "filled"), pm.primaries);
}
{
  const w = load(R.FIXTURES.slow.html);
  const before = run(w, R.pageReadyNow, { title: "Slow page" });
  const wrongTitle = run(w, R.pageReadyNow, { title: "Another page" });
  setTimeout(() => {
    const after = run(w, R.pageReadyNow, { title: "Slow page" });
    ok("A3: page ready is false while the page says Loading… and true once its first figure shows", before === false && after === true, { before, after });
    ok("A3: ...and never true on another page's header (the hash changed, the page has not)", wrongTitle === false);
    const e = load(`<!doctype html><html><body><main class="overflow-auto"><div data-guide="page-header"><h2>Empty</h2></div><div data-empty="none">Nothing yet</div></main></body></html>`);
    ok("A3: a page's own empty state counts as ready (an empty tenant shows no figure by design)", run(e, R.pageReadyNow, { title: "Empty" }) === true);
    const h = load(`<!doctype html><html><body><main class="overflow-auto"><div data-guide="page-header"><h2>Head</h2><p>Week 46</p></div><p>Nothing here</p></main></body></html>`);
    ok("A3: a figure in the page header does not count (the header draws before the data)", run(h, R.pageReadyNow, { title: "Head" }) === false);
    finish();
  }, 600);
}

// ---------------------------------------------------------------- B. grading one stop --------------------------------
const longBlock = { words: 33, sel: "p", text: "This sentence explains far too much on a staff screen because it walks through every step of the working" };
const M = (blocks, primaries) => ({ words: 50, blocks, primaries: primaries || [] });
{
  const staff = R.gradeRules({ name: "dashboard", signedIn: true }, M([longBlock]), []);
  ok("A1b: a long block on a staff screen FAILS the check long-prose", staff.checks.length === 1 && staff.checks[0].id === "long-prose" && !staff.checks[0].ok);
  const clean = R.gradeRules({ name: "dashboard", signedIn: true }, M([]), []);
  ok("A1b: ...and a staff screen with none passes it (the check is on every staff stop, so a pass is counted)", clean.checks.length === 1 && clean.checks[0].ok && !clean.warnings.length);
  const pub = R.gradeRules({ name: "login", signedIn: false }, M([longBlock]), []);
  ok("A1b: elsewhere (signed out, the map, the bulletin) it is a warning, not a check", !pub.checks.length && pub.warnings.some(w => w.id === "long-prose"));
  const rev = R.gradeRules({ name: "review-clp", signedIn: true }, M([longBlock]), []);
  ok("A1b: the client reviewer's page is not a staff screen (a warning)", !rev.checks.length && rev.warnings.some(w => w.id === "long-prose"));
  ok("A1b: the two guides and the landing pages are skipped (explanation and marketing prose belong there)",
     ["help", "help-technical", "landing", "privacy", "thanks", "landing-error"].every(n => { const g = R.gradeRules({ name: n, signedIn: false }, M([longBlock]), []); return !g.checks.length && !g.warnings.length; })
     && !R.PROSE_SKIPPED.test("bulletin") && !R.PROSE_SKIPPED.test("map-page"));
  const pins = [{ starts: "This sentence explains far too much", where: "fixture" }];
  const pinned = R.gradeRules({ name: "dashboard", signedIn: true }, M([longBlock]), pins);
  ok("A1b: a pinned block is a warning (long-prose-pinned) and the check passes; the pin is reported as seen",
     pinned.checks[0].ok && pinned.warnings.some(w => w.id === "long-prose-pinned") && pinned.pinsSeen[0] === pins[0].starts);
  ok("A1b: a pin matches whatever the figures in the block (pinKey: lower case, figures as #)",
     R.pinKey("Busiest hour: 63 whole loads, 08:00–09:00") === R.pinKey("busiest hour: 71 whole loads, 07:30–09:00") && !!R.pinOf("Busiest hour: 12 loads", [{ starts: "Busiest hour: 63" }]));
  const two = R.gradeRules({ name: "zones", signedIn: true }, M([], [{ text: "+ Draw zone" }, { text: "+ Haul road" }]), []);
  const one = R.gradeRules({ name: "forecasts", signedIn: true }, M([], [{ text: "Approve" }]), []);
  ok("A1c: two filled primaries on first view warn (filled-primaries, the list in the detail); one does not",
     two.warnings.some(w => w.id === "filled-primaries" && w.detail.length === 2) && !one.warnings.some(w => w.id === "filled-primaries") && R.LIMITS.primaries === 1);
}

// ---------------------------------------------------------------- C. the compare ---------------------------------------
{
  const S = (name, words, readyMs, extra) => ({ name, width: 1366, look: "ink", accent: "orange", words, readyMs, ...(extra || {}) });
  const old = { stops: [{ name: "dashboard", width: 1366, look: "ink", accent: "orange" }] };   // a run before FR1: no ruleVersion, no words
  const now = { ruleVersion: 1, stops: [S("dashboard", 320, 600)] };
  const c0 = R.compareRules(old, now);
  ok("C: an earlier run made before the measures pairs, but gives no word or speed rows and says so (earlierMeasured false)",
     !c0.earlierMeasured && !c0.words.length && !c0.ready.length);
  const key = (id, x) => `dashboard|1366|ink|orange|${id}|${x}`;
  const sp0 = R.splitFindings([key("long-prose", "p.ct-note Busiest"), key("filled-primaries", "button Big screen"), key("axe-wcag", "color-contrast"), key("words-grew", "")], false);
  ok("C: ...so this run's rule findings read as FIRST MEASURED, an older check's finding stays new, and a compare-made warning is never a finding",
     sp0.first.length === 2 && sp0.fresh.length === 1 && /axe-wcag/.test(sp0.fresh[0]));
  const sp1 = R.splitFindings([key("long-prose", "p")], true);
  ok("C: against a run that HAD the measures, a long block is a new finding", sp1.fresh.length === 1 && !sp1.first.length);
  const prev = { ruleVersion: 1, stops: [S("dashboard", 300, 600), S("submit", 100, 800), S("routes", 200, 900), S("forecasts", 40, 700), S("help", 20000, null), S("config", 60, 2000), S("zones", 100, 900)] };
  const cur = { ruleVersion: 1, stops: [S("dashboard", 326, 700), S("submit", 111, 1100), S("routes", 210, 1300), S("forecasts", 45, 950), S("help", 20500, null), S("config", 60, 2400), S("zones", 110, 1124)] };
  const c1 = R.compareRules(prev, cur);
  const w = Object.fromEntries(c1.words.map(r => [r.name, r])), rd = Object.fromEntries(c1.ready.map(r => [r.name, r]));
  ok("A1a: +26 words warns (more than 25) though it is under 10 %", w.dashboard.warn && w.dashboard.delta === 26 && w.dashboard.pct < 10);
  ok("A1a: +11 % warns (more than 10 %) though it is under 25 words", w.submit.warn && w.submit.pct === 11);
  ok("A1a: +10 words on 200 (5 %) does not warn, nor +10 % exactly (the limit is MORE than 10 %)", !w.routes.warn && !w.zones.warn && w.zones.pct === 10);
  ok("A1a: +12.5 % on a 40-word page warns (a small page is held to the same share)", w.forecasts.warn);
  ok("A1a: a guide growing by 500 words never warns (its words are tracked, not graded)", w.help && !w.help.warn);
  ok("A1a: a stop whose words did not change has no row", !w.config);
  ok("A3: 25 % slower and over 1 s warns (800 → 1100 ms is 37.5 %; 900 → 1300 is 44 %)", rd.submit.warn && rd.routes.warn);
  ok("A3: 35 % slower but under 1 s does not (700 → 950 ms): the floor keeps the laptop's noise out", !rd.forecasts.warn);
  ok("A3: over 1 s but only 20 % slower does not (2000 → 2400 ms); 24.9 % does not either (900 → 1124)", !rd.config.warn && !rd.zones.warn);
  ok("A3: a stop with no time on either side has no row", !rd.help);
  const report = { stops: cur.stops.map(s => ({ ...s, checks: s.name === "submit" ? [{ id: "long-prose", ok: false }] : [] })),
                   compare: { newFindings: ["submit|1366|ink|orange|long-prose|p A long one"], firstMeasured: [], rules: c1 } };
  const L = R.prLines(report).join("\n");
  ok("D: the PR lines name the new failing checks, the screen words +/− per stop changed and the slowest page ready",
     /New failing checks:\*\* 1 — submit 1366 ink orange long-prose/.test(L) && /Screen words \+\/−\*\* \(6 stop\(s\) changed, 3 over the limit\)/.test(L)
     && /dashboard 1366 ink orange: 300 → 326 \(\+26, \+8\.7 %\) ⚠/.test(L) && /Slowest page ready:\*\* 2400 ms, config at 1366 px/.test(L) && /not live's speed/.test(L), L);
  const L0 = R.prLines({ stops: now.stops.map(s => ({ ...s, checks: [] })), compare: { newFindings: [], firstMeasured: ["x"], rules: c0 } }).join("\n");
  ok("D: ...and against an older run they say it has no word counts, and how many findings are first measured",
     /has no word counts/.test(L0) && /1 finding\(s\) of the rule checks are FIRST MEASURED/.test(L0), L0);
  // run 2 (10 Nov 2026): a stop that had not finished loading in one run is the machine's load, not the page
  const NS = { warnings: [{ id: "not-settled", detail: "x" }] }, RN = { warnings: [{ id: "ready-none", detail: "x" }] };
  const pU = { ruleVersion: 1, stops: [S("lookahead", 238, 2090), S("team-lookahead", 23, null, RN), S("dashboard", 375, 483)] };
  const nU = { ruleVersion: 1, stops: [S("lookahead", 12, null, { warnings: [NS.warnings[0], RN.warnings[0]] }), S("team-lookahead", 222, 2354), S("dashboard", 317, 231)] };
  const cU = R.compareRules(pU, nU);
  ok("C: a stop that had not settled (not-settled / ready-none) in EITHER run gets no word or speed row, only its key in unsettled",
     cU.unsettled.length === 2 && !cU.words.some(r => /lookahead/.test(r.name)) && !cU.ready.some(r => /lookahead/.test(r.name)) && cU.words.length === 1 && cU.words[0].name === "dashboard", cU);
  const LU = R.prLines({ stops: nU.stops.map(s => ({ ...s, checks: [] })), compare: { newFindings: [], firstMeasured: [], rules: cU } }).join("\n");
  ok("D: ...and the PR lines say how many stops were not compared and why", /2 stop\(s\) not compared: the page had not finished loading/.test(LU), LU);
}

// ---------------------------------------------------------------- D. the pins, the limits, the wiring ------------------
// The pinned long blocks: exactly those the first runs found on staff screens (10 Nov 2026). May only SHRINK: lower this
// number when claude/ui-fix-long-sentences (or any fix) takes a block away; never raise it.
const PINNED_MAX = 25;   // LOWERED 11 Nov 2026 (C-X2): the Look-ahead's gates note left the list
ok(`A1b: the pinned long blocks may only shrink (${R.LONG_PROSE_PINNED.length} pinned, at most ${PINNED_MAX})`,
   R.LONG_PROSE_PINNED.length <= PINNED_MAX && R.LONG_PROSE_PINNED.every(p => p.starts && p.starts.split(" ").length >= 4 && p.where));
ok("the limits are John's (decision U5, 10 Nov 2026): 25 words, 10 % or 25 words, 1 filled primary, 25 % and 1 s",
   R.LIMITS.blockWords === 25 && R.LIMITS.wordsGrowPct === 10 && R.LIMITS.wordsGrowAbs === 25 && R.LIMITS.primaries === 1 && R.LIMITS.readySlowerPct === 25 && R.LIMITS.readyFloorMs === 1000);
const fnSrc = (name) => { const i = audit.indexOf("function " + name + "("); const j = audit.indexOf("\nfunction ", i + 10), k = audit.indexOf("\nasync function ", i + 10);
  return i < 0 ? "" : audit.slice(i, Math.min(...[j, k].filter(x => x > 0), audit.length)); };
const au = fnSrc("audit");
ok("wiring: every stop measures the rules BEFORE the shot grows the viewport (first view is the real fold), and grades them",
   au.includes("RULES.ruleMeasures") && au.indexOf("RULES.ruleMeasures") < au.indexOf("await shoot(") && au.includes("RULES.gradeRules("));
// run 2 (10 Nov 2026): the Dashboard at 1366 read 375 words on one stop and 317 on the next — a section drew after the settle
ok("wiring: the words and long blocks are counted AGAIN after the shot (late sections in), the filled primaries kept from the first view, and a moved count is on the record",
   au.indexOf("const rmLate = ") > au.indexOf("await shoot(") && au.includes("{ ...rmLate, primaries: rm.primaries }")
   && au.includes("RULES.gradeRules({ name: meta.name, page: meta.page, signedIn: dom.signedIn }, rmUse)") && au.includes("stop.words = rmUse.words")
   && au.includes("stop.wordsLate = { atFold: rm.words, afterShot: rmLate.words }"));
ok("wiring: page ready is timed from the hash set on every portal page (not the framed Route map) and the team's, and from the goto on the map page",
   /const ts = Date\.now\(\);\n\s+await gotoPage\(page, id\);[\s\S]{0,700}timeReady\(page, ts, \{ title: PAGE_TITLE\[id\] \}\)/.test(fnSrc("walkPortal"))
   && fnSrc("walkPortal").includes('id === "map" ? Promise.resolve(undefined)') && fnSrc("walkPortal").includes("timeReady(page, tMap, { map: true })") && fnSrc("walkTeam").includes("timeReady(page, ts,"));
// 10 Nov 2026, run 1: a phone's desk-only page has no header, so the header wait ran its full 20 s and the clock read ~20,200 ms;
// the clock now polls ALONGSIDE the header wait (started before it, awaited after), and the header wait ends on the desk-only card
for (const fn of ["walkPortal", "walkTeam"]) {
  const s = fnSrc(fn), p = s.indexOf("const readyP = "), h = s.indexOf('[data-guide="page-header"] h2'), a = s.indexOf("await readyP");
  ok(`wiring: ${fn} starts the page-ready clock BEFORE the header wait and reads it after (never inside the 20 s wait)`, p > 0 && h > p && a > h);
}
// reversed the same evening: ending the header wait on the desk-only card sped the phone walk up enough that the Look-ahead
// and the Simulation at 390 no longer loaded behind the Dashboard's reads (runs 2 and 3); the walk keeps its old pacing
ok("wiring: the portal's header wait does NOT end on a phone's desk-only card (the walk's pacing is unchanged by FR1)",
   fnSrc("walkPortal").includes("return h && h.textContent.trim() === t; }, PAGE_TITLE[id], { timeout: 20000 })") && !/querySelector\("\[data-desk-only\]"\)/.test(fnSrc("walkPortal")));
ok("wiring: every run starts with the rules' self-test in its own browser, and --self-test runs only that",
   audit.includes("await selfTestRules(browser);   // FR1") && audit.includes('else if (a === "--self-test") o.selfTest = true;') && fnSrc("selfTestRules").includes("RULES.FIXTURES"));
ok("wiring: the measures are NOT part of the run's shape (a run before them pairs); the report carries ruleVersion",
   /function sameShape\(a, b\) \{ const k = \(o\) => \[o\.widths, o\.looks, o\.extraAccents, o\.extraPasses \|\| \[\], o\.browser \|\| "chromium"\];/.test(audit)
   && audit.includes("ruleVersion: RULES.RULES_VERSION") && !/options: \{[^}]*ruleVersion/.test(audit));
ok("wiring: the compare splits first-measured findings out, adds words-grew / ready-slower, and never keys those two as findings",
   fnSrc("compareRuns").includes("RULES.splitFindings(diff.newFindings, diff.rules.earlierMeasured)") && fnSrc("compareRuns").includes('id: "words-grew"')
   && fnSrc("compareRuns").includes('id: "ready-slower"') && fnSrc("findingKeys").includes("RULES.COMPARE_IDS.includes(w.id)"));
ok("wiring: summary.md opens with the PR lines and carries the per-stop measures and the long blocks",
   fnSrc("writeSummaryMd").includes('"## For the PR", "", ...RULES.prLines(REPORT)') && fnSrc("writeSummaryMd").includes("## Rule measures (FR1") && fnSrc("writeSummaryMd").includes("## Long blocks (A1b"));
ok("wiring: a pin no stop showed is named in the run's notes for removal", audit.includes("long-prose pin not seen in this run"));
const PW = "play" + "wright" + '")';   // test_modus.py's sign of a browser harness, spelt so this file does not carry it
ok("the helper is in backend/tests/lib (not run as a harness) and needs no browser; this harness needs no Playwright",
   fs.existsSync(path.join(__dirname, "lib", "ui_rules.js")) && !fs.readFileSync(path.join(__dirname, "lib", "ui_rules.js"), "utf8").includes(PW)
   && !fs.readFileSync(__filename, "utf8").includes(PW));

function finish() {
  console.log();
  for (const f of fail) console.log("  FAIL:", f);
  console.log(`\n${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
}
