/* ui_fix_map_conditions_chip.js — 12 Nov 2026, branch claude/map-conditions-chip-fits (card A1-X2).
 *
 * Seen on live at 1150 px (John's window): the conditions chip in the figures bar lay over the figures ("375 t CO2e to date" hidden
 * with two entries, "CO2e a day" too with three; at 1024 px even one entry). The old build did the same (the chip never depended
 * on the panel). Now fitCondChip() puts body.cond-chip-below on when the figures do not fit beside the chip: the chip hangs on its
 * own line under the bar, right-aligned, and what measured from the bar's bottom edge measures from the chip's (secselTopEdge,
 * the Conditions panel's top through --cond-chip-h). Under 1024 px (the phone and the tablet) nothing changes.
 *
 * Source checks on map/index.html plus a sandbox that runs the page's own fitCondChip against stand-ins. No browser (the browser
 * half is the Chrome run in card A1-X2: 1024 to 1400 px, one to four entries). Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}

const a = html.indexOf("    function fitCondChip() {");
const b = html.indexOf("    window.addEventListener('resize', fitCondChip);", a);
const src = a >= 0 && b > a ? html.slice(a, b) : "";
ok("A1 the page has fitCondChip, run on resize and on the bar's size change, and renderConditionsPill calls it",
   !!src && html.includes("window.addEventListener('resize', fitCondChip);") && /new ResizeObserver\(\(\) => fitCondChip\(\)\)\.observe\(document\.getElementById\('kpi-hud'\)\)/.test(html)
   && /pill\.classList\.add\('on'\);\n\s+fitCondChip\(\);/.test(html));

function world(width, o) {
  const cls = new Set(), vars = {};
  const chip = { classList: { contains: c => c === "on" && o.chipOn !== false }, getBoundingClientRect: () => ({ height: o.chipH || 47 }) };
  const cards = { scrollWidth: o.scrollWidth, clientWidth: o.clientWidth };
  const hud = {};
  const body = { classList: { add: c => cls.add(c), remove: c => cls.delete(c), contains: c => cls.has(c) },
                 style: { getPropertyValue: k => vars[k] || "", setProperty: (k, v) => { vars[k] = v; } } };
  const ctx = { window: { innerWidth: width }, getComputedStyle: () => ({ display: o.hudDisplay || "flex" }), document: { body,
                getElementById: id => ({ "kpi-conditions": chip, "kpi-cards": cards, "kpi-hud": hud })[id] || null } };
  vm.createContext(ctx);
  vm.runInContext(src + "\n;this.fit = fitCondChip;", ctx);
  return { ctx, cls, vars, cards };
}
if (src) {
  let w = world(1150, { scrollWidth: 560, clientWidth: 470 }); w.ctx.fit();
  ok("B1 figures that do not fit beside the chip (scrollWidth 560 over 470): the chip goes below, room = its height + 15 px", w.cls.has("cond-chip-below") && w.vars["--cond-chip-h"] === "62px", [...w.cls, w.vars]);
  w = world(1150, { scrollWidth: 470, clientWidth: 470 }); w.ctx.fit();
  ok("B2 figures that fit: the chip stays in the bar and takes no room", !w.cls.has("cond-chip-below") && w.vars["--cond-chip-h"] === "0px", [...w.cls, w.vars]);
  w = world(1150, { scrollWidth: 471, clientWidth: 470 }); w.ctx.fit();
  ok("B3 a one-pixel difference (rounding) does not move it", !w.cls.has("cond-chip-below"));
  w = world(1150, { scrollWidth: 560, clientWidth: 470 }); w.ctx.fit(); w.cards.scrollWidth = 470; w.ctx.fit();
  ok("B4 a window that grows (the figures fit again) puts the chip back in the bar", !w.cls.has("cond-chip-below") && w.vars["--cond-chip-h"] === "0px", [...w.cls, w.vars]);
  w = world(1023, { scrollWidth: 900, clientWidth: 400 }); w.ctx.fit();
  ok("B5 under 1024 px (the tablet and the phone) it never moves the chip", !w.cls.has("cond-chip-below") && w.vars["--cond-chip-h"] === "0px");
  w = world(1150, { scrollWidth: 900, clientWidth: 400, chipOn: false }); w.ctx.fit();
  ok("B6 no entries (the chip is not shown): nothing moves", !w.cls.has("cond-chip-below") && w.vars["--cond-chip-h"] === "0px");
  w = world(1150, { scrollWidth: 900, clientWidth: 400, hudDisplay: "none" }); w.ctx.fit();
  ok("B7 the bar hidden (wall mode): nothing moves", !w.cls.has("cond-chip-below"));
  w = world(1150, { scrollWidth: 900, clientWidth: 400, chipH: 30 }); w.ctx.fit();
  ok("B8 the room follows the chip's height (one line: 45 px)", w.vars["--cond-chip-h"] === "45px", w.vars);
} else { ok("B the sandbox could not run: fitCondChip is missing", false); }

ok("C1 the chip below is its own line under the bar, right-aligned, clear of the zoom buttons (a desk-only rule)",
   /@media \(min-width:1024px\)\{\n\s+body\.cond-chip-below #kpi-conditions\{ position:absolute; top:calc\(100% \+ 7px\); right:64px;/.test(html));
ok("C2 the Conditions panel starts under the chip (with and without the demo notice) and its height gives the room back",
   html.includes("body.cond-chip-below #tl-warnings{ top:calc(84px + var(--cond-chip-h, 0px)); }")
   && html.includes("body.has-demo-notice.cond-chip-below #tl-warnings{ top:calc(110px + var(--cond-chip-h, 0px)); }")
   && html.includes("calc(100vh - 130px - var(--cond-chip-h, 0px) - var(--tl-foot, 0px))"));
const te = html.slice(html.indexOf("    function secselTopEdge() {"), html.indexOf("    function secselTopEdge() {") + 1200);
ok("C3 the map's cards measure from the chip's bottom edge when it hangs under the bar (secselTopEdge)",
   te.includes("classList.contains('cond-chip-below')") && te.includes("getElementById('kpi-conditions')") && te.includes("Math.max(bottom, c.getBoundingClientRect().bottom + 6)"));
ok("C4 the rule that keeps the chip in a 300 px pill beside the figures is unchanged (1024 px and wider)",
   html.includes("@media (min-width:1024px){ #kpi-conditions{ flex-wrap:wrap; max-width:300px; flex-shrink:0; column-gap:12px; row-gap:2px;"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
