/*
 * ui_fix_carbon_tap.js — 26 Nov 2026, branch claude/carbon-planner-tap (John: "fix the carbon planner button size").
 *
 *   The UI audit of `main` 6a2e27f (25 Nov) failed its 44 px rule at 390 px on "Open the Carbon planner", the outline
 *   button on the Dashboard's carbon target strip: 187 × 34 px. On a phone (under 768 px) a button inside any carbon
 *   target strip is now at least 44 px tall, the same way the Dashboard's month boxes and the Simulation's controls are.
 *   Nothing changes at a desk. Its own file (BUILD.md rule 3); source checks (jsdom has no layout).
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");

const rule = /@media \(max-width:767px\)\{\[data-carbon-target\] \.btn-sec\{min-height:44px;\}\}/;
ok("🔴 on a phone a button in the carbon target strip is at least 44 px tall", rule.test(html));
ok("...in one phone-only rule (never at a desk)",
   (html.match(/\[data-carbon-target\] \.btn-sec\{/g) || []).length === 1);
const strip = html.slice(html.indexOf("function CarbonTargetStrip("), html.indexOf("function CarbonTargetStrip(") + 3000);
const btns = strip.match(/<button type="button" className="btn-sec" onClick=\{\(\) => onOpen\("carbon"\)\}>Open the Carbon planner<\/button>/g) || [];
ok("both 'Open the Carbon planner' buttons are outline buttons inside a data-carbon-target strip",
   btns.length === 2 && /data-carbon-target="none"/.test(strip) && /data-carbon-target="set"/.test(strip), String(btns.length));
const base = (html.match(/\.btn-sec\{[^}]*background:var\(--surface\);color:var\(--ink\);[^}]*\}/) || [""])[0];
ok("the outline class itself is unchanged (no new height for every btn-sec)", base.length > 0 && !/min-height/.test(base), base);

console.log(`ui_fix_carbon_tap.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
