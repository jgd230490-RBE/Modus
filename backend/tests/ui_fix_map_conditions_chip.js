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
const te = html.slice(html.indexOf("    function secselTopEdge(span) {"), html.indexOf("    function secselTopEdge(span) {") + 1800);
ok("C3 the map's cards measure from the chip's bottom edge when it hangs under the bar (secselTopEdge)",
   te.includes("classList.contains('cond-chip-below')") && te.includes("getElementById('kpi-conditions')") && te.includes("Math.max(bottom, cr.bottom + 6)"));

// ---- 12 Nov 2026, the fix of A1-X2 (seen on live by the routes check, Apr 2027, 1150 x 677): the B6047 card beside its click
// (x 331-701, the chip at x 786-1086 on the other side of the map) was cut to top 167 / foot 451 and its table to 71 px, because
// secselTopEdge gave the chip's bottom for every card. The chip is now in the card's way only where the card's own column meets it.
const s0 = html.indexOf("    const SECSEL_HALF = 200;"), s1 = html.indexOf("    // 11 Nov 2026 (map popup top;");
const place = s0 >= 0 && s1 > s0 ? html.slice(s0, s1) : "";
ok("D0 the placing helpers are in the page (secselTopEdge takes the card's span; secselSpan and secselRoadWant exist)",
   /function secselTopEdge\(span\) \{/.test(place) && /function secselSpan\(x, anchor, w\) \{/.test(place) && /function secselRoadWant\(x, y, W, H, foot, right, need, w\) \{/.test(place));
function mapWorld(below) {
  const cls = new Set(below ? ["cond-chip-below"] : []);
  const rect = (l, t, r, b) => ({ left: l, top: t, right: r, bottom: b });
  const els = { "kpi-hud": { getBoundingClientRect: () => rect(0, 26, 1150, 98) }, "kpi-conditions": { getBoundingClientRect: () => rect(786, 105, 1086, 145) } };
  return new Function("map", "document", "getComputedStyle", "window", place + "\nreturn { secselTopEdge, secselSpan, secselRoadWant };")(
    { getContainer: () => ({ getBoundingClientRect: () => rect(0, 0, 1150, 677), clientWidth: 1150, clientHeight: 677 }) },
    { body: { classList: { contains: c => cls.has(c) } }, getElementById: id => els[id] || null }, () => ({ display: "flex" }), { innerWidth: 1150 });
}
if (place) {
  const w = mapWorld(true), off = mapWorld(false);
  ok("D1 no span (the old call): the chip's bottom counts, 145 + 6 = 151; the chip not below: the bar's 98", w.secselTopEdge() === 151 && off.secselTopEdge() === 98, [w.secselTopEdge(), off.secselTopEdge()]);
  ok("D2 a column that does not meet the chip (x 331-701 against 786-1086) measures from the bar: 98; one that meets it measures from the chip: 151",
     w.secselTopEdge([331, 701]) === 98 && w.secselTopEdge([700, 900]) === 151 && w.secselTopEdge([1000, 1100]) === 151 && w.secselTopEdge([1086, 1200]) === 98, [w.secselTopEdge([331, 701]), w.secselTopEdge([700, 900])]);
  ok("D3 a card's column from its anchor: beside the click to the left / right, above or below with a corner, centred",
     JSON.stringify(w.secselSpan(711, "right", 370)) === "[341,711]" && JSON.stringify(w.secselSpan(711, "left", 370)) === "[711,1081]"
     && JSON.stringify(w.secselSpan(711, "top-left", 380)) === "[711,1091]" && JSON.stringify(w.secselSpan(711, "bottom-right", 380)) === "[331,711]"
     && JSON.stringify(w.secselSpan(711, "", 380)) === "[521,901]" && JSON.stringify(w.secselSpan(711, "top", 0)) === "[509,913]");
  // the live case: click at map (711, 300), the free map ends at 1094, the timeline bar 94, a card 370 wide
  const L = w.secselRoadWant(711, 300, 1150, 677, 94, 1094, 290, 370);
  ok("D4 THE LIVE CASE: a click at (711, 300) opens the card beside the click, to its left, and measures from the bar (98), not the chip (151): its table keeps its room",
     L.want === "right" && L.beside === "right" && L.top === 98, L);
  const L0 = off.secselRoadWant(711, 300, 1150, 677, 94, 1094, 290, 370);
  ok("D5 with the chip in the bar the answer is the same as with it below for that click", L0.want === L.want && L0.top === L.top, [L0, L]);
  const M = w.secselRoadWant(950, 300, 1150, 677, 94, 1094, 290, 370);
  ok("D6 a click whose card lies UNDER the chip (x 950, the card to its left, x 580-950 meets 786-1086) still measures from the chip: 151", M.beside === "right" && M.top === 151, M);
  const N = w.secselRoadWant(300, 120, 1150, 677, 94, 1094, 290, 370);
  ok("D7 a click far from the chip (x 300, y 120): the card opens below it from the bar's edge (98)", N.top === 98 && /^top/.test(N.want), N);
  const O = w.secselRoadWant(900, 120, 1150, 677, 94, 1094, 290, 370);
  ok("D8 a click under the chip's column (x 900, y 120): the card still clears the chip (top 151)", O.top === 151, O);
  ok("D9 the page asks the new helper in both places that place the card, and the popups' fit gives its own span",
     /const rw = secselRoadWant\(/.test(html) && /secselRoadWant\(at\.point\.x, at\.point\.y, W, H, foot, secselRightEdge\(\), secselNeed\(fixed, sc\.scrollHeight\), cw\)/.test(html)
     && /secselTopEdge\(secselSpan\(pt\.x, /.test(html));
} else { ok("D the placing helpers could not be read", false); }
ok("C4 the rule that keeps the chip in a 300 px pill beside the figures is unchanged (1024 px and wider)",
   html.includes("@media (min-width:1024px){ #kpi-conditions{ flex-wrap:wrap; max-width:300px; flex-shrink:0; column-gap:12px; row-gap:2px;"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
