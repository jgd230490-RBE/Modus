/* ui_fix_map_phone_lead.js — 12 Nov 2026, branch claude/map-phone-lead-labels (a fault found in passing on the public map's
 * phone sheet, card A1-L3 in notes\clocs-meeting-1113\left-to-do-mockup-1111\cards-a1-road-card-tall.html).
 *
 * The sheet's two lead figures ("308 movements a day", "42 vehicles") sit in a wrapping row with the conditions pill. Each
 * figure was `flex:1 1 0; min-width:0`, so the pill took its width first and the figures shared what was left: at 360 and 390 px
 * that was 54 px each, and the 77 px word "movements" ran into "vehicles". A figure now keeps its longest word
 * (`min-width:min-content`), so when the three do not fit the pill drops to a row of its own.
 *
 * Source checks on map/index.html (no browser: the browser half is the Chrome check in the card and ui_audit.js).
 * Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}

// the phone block's own rule for a lead figure: ".m-fig{ ... }" with nothing before the dot but spaces (not the peek's or the landscape's)
const rules = [...html.matchAll(/^[ \t]+\.m-fig\{([^}]*)\}/gm)].map(m => m[1]);
ok("A1 the phone sheet has exactly one base rule for a lead figure", rules.length === 1, rules);
const base = rules[0] || "";
ok("A2 a lead figure keeps its longest word: min-width:min-content", /min-width:\s*min-content/.test(base), base);
ok("A3 ...and no longer lets a figure shrink to nothing (no min-width:0)", !/min-width:\s*0\b/.test(base), base);
ok("A4 the two figures still share the row (flex:1 1 0) and the label still wraps between words", /flex:\s*1 1 0/.test(base) && !/white-space:\s*nowrap/.test(base), base);
ok("A5 the sheet's row still wraps, so the pill can drop to a row of its own",
   /\.m-peek\{[^}]*flex-wrap:wrap;/.test(html));
ok("A6 the folded sheet's one line is unchanged (nowrap figures, pill hidden)",
   html.includes('#m-sheet[data-state="peek"] .m-fig{ flex:0 0 auto; white-space:nowrap; }')
   && html.includes('#m-sheet[data-state="peek"] .m-cond{ display:none; }')
   && html.includes('#m-sheet[data-state="peek"] .m-peek{ flex-wrap:nowrap;'));
ok("A7 the figures' words are the same: 'movements a day' and 'vehicles'",
   html.includes('<span id="m-trips-word">movements a day</span>') && html.includes('<b id="m-vehicles">&mdash;</b><span>vehicles</span>'));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
