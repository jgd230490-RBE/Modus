/* ui_fix_map_strip.js — 12 Nov 2026, branch claude/map-strip-gives-way (the left-to-do card A1-F3, John's yes of 11 Nov).
 * Source checks on map/index.html; no browser (the browser half is the Chrome check in the session note).
 *
 * The "New here? Press Play to watch a month of haul." strip sits at the map's top left, over any popup that opens there:
 * it hid the start of a road card's title. While a popup is open the strip is hidden (one CSS rule: no script, so it is at once
 * and never out of step), and it comes back when the popup closes. A phone is unchanged.
 *
 * Its own file (BUILD.md rule 3). Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
const rule = "@media (min-width:768px){body:has(.mapboxgl-popup) .guide-strip{display:none}}";
const i = html.indexOf(rule);
ok("⭐ the strip is hidden while a map popup is open, by one CSS rule (a popup is in the page only while it is open)", i > 0 && html.split(rule).length === 2);
ok("⭐ the rule is for a desk and a tablet only (768 px and up): the phone's strip, under Layers, is unchanged",
   i > 0 && !html.slice(0, i).slice(-400).includes("max-width") && html.indexOf(".guide-strip{position:fixed;") < i);
ok("the rule beats the strip's own display:flex by specificity ((0,2,1) against (0,1,0)), so it needs no !important and the wall mode's and the sidebar's own display rules still stand",
   !/body:has\(\.mapboxgl-popup\) \.guide-strip\{display:none ?!important/.test(html) && html.includes("body.wall-mode .guide-strip, body.wall-mode .guide-dot")
   && (html.match(/body:not\(\.sidebar-closed\) \.guide-strip/g) || []).length === 1);
ok("the strip's words, buttons and its placing script are untouched (it is still placed every second; nothing sets its display from script)",
   html.includes("'<span>New here? Press <b>Play</b> to watch a month of haul.</span>'") && html.includes('onclick="guideStart()">Take the tour</button>')
   && !/strip\.style\.display/.test(html) && html.includes("strip.style.top = (Math.round(below) + 10) + 'px'; strip.style.left = (Math.round(k.left) + 12) + 'px';"));
ok("⭐ technical T1 says the strip gives way to an open popup, on a desk and a tablet only",
   guide.includes('id="t1-strip-gives-way"') && guide.includes("<code>.guide-strip</code>") && guide.includes("while a map popup is open") && guide.includes("768 px"));
for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
