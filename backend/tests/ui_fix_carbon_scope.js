/* ui_fix_carbon_scope.js — 12 Nov 2026, branch claude/carbon-line-scope (the left-to-do card A1-F2, John's yes of 11 Nov).
 * The page's OWN ctProgress / ctGap run against stand-in figures; no browser.
 *
 * A team login's carbon line on Forecasts read "As forecast on your team's lines: 71,909.6 tCO2e, 351.1 tCO2e over the target ·
 * With the agreed decisions on your team's lines: ..." = 29 words, over the 25 the audit allows (rule R1). The line above it already
 * says "Target for your team's lines", so the scope was said twice more. It is said once now; the Dashboard, Forecasts, Submit
 * forecast and the Carbon planner all print the target line first, so none loses it.
 *
 * Its own file (BUILD.md rule 3). Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
const fn = (name) => { const i = html.indexOf("function " + name + "("); const j = html.indexOf("\n}\n", i); return i < 0 ? "" : html.slice(i, j + 3); };
const make = (team) => new Function("ctTeam", "ctYour", "ctT", fn("ctGap") + "\n" + fn("ctProgress") + "\nreturn ctProgress;")(() => team, () => "your team's lines", n => n.toFixed(1));
const words = s => s.split(/\s+/).filter(Boolean).length;
const st = (o) => ({ status: Object.assign({ approved_t: 2310.4, with_decisions_t: 2198.4, on_target_as_forecast: false, gap_as_forecast_t: 112, on_target_with_decisions: false, gap_with_decisions_t: -12, invalid: "" }, o || {}) });
ok("⭐ the function is in the page and no longer builds any scope words of its own", !!fn("ctProgress") && !/\bon = ctTeam|\$\{on\}|ctYour\(\)/.test(fn("ctProgress")));
{
  const team = make(true)(st()), scheme = make(false)(st());
  ok("⭐ a team login's two figures lines carry no 'on your team's lines'; they are the same words a scheme login reads",
     team.join("|") === scheme.join("|") && !/your team/.test(team.join(" ")));
  ok("⭐ the words: 'As forecast: 2,310.4 tCO2e, 112.0 tCO2e over the target' and 'With the agreed decisions: 2,198.4 tCO2e, 12.0 tCO2e under the target' (sentence figures from the server's verdicts, nothing worked out here)",
     team[0] === "As forecast: 2310.4 tCO2e, 112.0 tCO2e over the target" && team[1] === "With the agreed decisions: 2198.4 tCO2e, 12.0 tCO2e under the target");
  const line = team[0] + " · " + team[1];
  ok("⭐ the worst case the audit met (both verdicts a gap, shown joined by ' · ' as Forecasts prints them) is 21 words, not 29: under the 25-word limit",
     words(line) === 21 && words("As forecast on your team's lines: 2310.4 tCO2e, 112.0 tCO2e over the target · With the agreed decisions on your team's lines: 2198.4 tCO2e, 12.0 tCO2e under the target") === 29);
  ok("on target: the verdict words stand ('on target'); a missing verdict adds nothing",
     make(true)(st({ on_target_as_forecast: true, on_target_with_decisions: true }))[0] === "As forecast: 2310.4 tCO2e, on target"
     && make(true)(st({ on_target_as_forecast: null, gap_as_forecast_t: null }))[0] === "As forecast: 2310.4 tCO2e");
  ok("decisions that no longer apply: the dash form is a dash, the long form is the server's own sentence",
     make(true)(st({ invalid: "x" }), true)[1] === "With the agreed decisions: —" && make(true)(st({ invalid: "Decisions do not fit the plan." }))[1] === "Decisions do not fit the plan.");
}
ok("⭐ every place that prints the two lines still prints the target line first (the scope is said there, once): Forecasts' strip, the Dashboard's words, Submit forecast's one line, the Carbon planner",
   html.includes("<b>Carbon (all-in):</b> {ctTargetLine(ct)}") && html.includes("const words = [ctTargetLine(ct), ...ctProgress(ct), ctScopeNote(ct),")
   && html.includes("return `${ctTargetLine(ct)} · ${p1} · ${p2}`;") && html.includes("<p className=\"text-base font-semibold text-slate-800 tabular-nums\">{ctTargetLine(tg)}</p>"));
ok("the scope words themselves are unchanged where they are said once: 'Target for your team's lines' (target line) and the scope note",
   html.includes("return `Target for ${ctYour()}: ${ctT(s.target_t)} tCO2e,") && html.includes("These figures are for ${ctYour()} only, against their share of the scheme's target"));
for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
