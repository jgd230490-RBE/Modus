// CLOCS card C-X2 (11 Nov 2026, rule 13 of the build, John's "start the fix at once"): the Look-ahead's Gates this week
// note was a 50-word block (gate_hours.LIMIT_WORDS + the week-split sentence), pinned in the audit's long-prose list. It is
// five words now, "Averages only: no hourly peak."; both sentences live in the la.gates "i" box's how. The pin leaves the
// list and PINNED_MAX comes down with it (CLAUDE.md: remove a pin and lower its MAX when the text is cut).
// Run: node backend/tests/ui_fix_clocs_c_gates_words.js
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n/g, "\n");
const rules = require("./lib/ui_rules.js");
const auditRules = fs.readFileSync(path.join(__dirname, "ui_audit_rules.js"), "utf8");
let pass = 0, fail = 0;
const ok = (label, cond, detail) => { if (cond) { pass++; console.log("  ✅ " + label); } else { fail++; console.log("  ❌ " + label + (detail ? "\n       " + detail : "")); } };
const words = (s) => String(s).trim().split(/\s+/).filter(Boolean).length;

const gw = html.slice(html.indexOf("function GatesWeek({"), html.indexOf("\nfunction ", html.indexOf("function GatesWeek({") + 10));
const note = (gw.match(/<div className="ct-note" data-gw-note="1">([^<]*)<\/div>/) || [])[1];
ok("⭐ C-X2: Gates this week's note is a few words: 'Averages only: no hourly peak.'", note === "Averages only: no hourly peak." && words(note) <= 8, note);
ok("⭐ C-X2: the note no longer prints the limit sentence or the week-split sentence on the screen",
   !gw.includes("{gw.limit}") && !gw.includes("The days are this page's own"));
const tip = html.slice(html.indexOf('"la.gates": {'), html.indexOf("\n", html.indexOf("how:", html.indexOf('"la.gates": {'))));
ok("⭐ C-X2: both sentences are in the la.gates 'i' box's how (the limit with its shut times and bands; the week split)",
   tip.includes("less shut times and the no-delivery bands; no hourly peak is known.")
   && tip.includes("The days are this page's own: the month spread over its calendar weeks, rounded up a day, so a day can be busier than the Dashboard's month average."), tip.slice(0, 300));
const text = (tip.match(/text: "([^"]*)"/) || [])[1] || "";
ok("C-X2: the 'i' box's text (what the CI counts) is unchanged at 34 words, within its pin", words(text) === 34, String(words(text)));
ok("⭐ C-X2: the long-prose pin 'Planned arrivals spread evenly over the gate's open hours' has left the list",
   !rules.LONG_PROSE_PINNED.some(p => /^Planned arrivals spread evenly/.test(p.starts)));
ok("⭐ C-X2: PINNED_MAX came down with it (25), and the list fits", /const PINNED_MAX = 25;/.test(auditRules) && rules.LONG_PROSE_PINNED.length <= 25,
   String(rules.LONG_PROSE_PINNED.length));
ok("C-X2: the gates heading keeps its 'i' box", gw.includes('<h3 className="ct-h">Gates this week<InfoTip id="la.gates" /></h3>'));
console.log(`\nui_fix_clocs_c_gates_words.js: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
