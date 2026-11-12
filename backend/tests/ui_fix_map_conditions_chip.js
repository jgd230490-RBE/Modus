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
   /@media \(min-width:1024px\)\{\n(?:.*\n)*?\s+body\.cond-chip-below #kpi-conditions\{ position:absolute; top:calc\(100% \+ 7px\); right:64px;/.test(html));
ok("C2 the Conditions panel starts under the chip (with and without the demo notice) and its height gives the room back",
   html.includes("body.cond-chip-below #tl-warnings{ top:calc(84px + var(--cond-chip-h, 0px)); }")
   && html.includes("body.has-demo-notice.cond-chip-below #tl-warnings{ top:calc(110px + var(--cond-chip-h, 0px)); }")
   && html.includes("calc(100vh - 130px - var(--cond-chip-h, 0px) - var(--tl-foot, 0px))"));
// REVERSED 12 Nov 2026 (the second build): the first build measured every card from the chip's bottom edge (its C3); on live that cut the
// B6047 card's table from 189 px to 71 px at 1150 x 677 (the card with the traffic-limit line is taller). Now NO card measures from
// the chip: secselTopEdge is the figures bar's own edge, as on main before the chip fix; the chip gives way to an open card instead.
const teM = /    function secselTopEdge\(\) \{[\s\S]*?\n    \}/.exec(html), te = teM ? teM[0] : "";
ok("C3 (reversed) every card measures from the figures bar's bottom edge only: secselTopEdge knows nothing of the chip, and has no span",
   te.length > 100 && !/cond-chip|kpi-conditions/.test(te) && /return Math\.max\(0, Math\.round\(r\.bottom - m\.top\)\);/.test(te));
ok("C3b nothing that places a card (the road card, the popups' fit, the room helpers) mentions the chip",
   !/cond-chip|kpi-conditions/.test((/    function showRoadPopup\(\) \{[\s\S]*?\n    \}/.exec(html) || [""])[0] + (/    function fitRoadPopup\(\) \{[\s\S]*?\n    \}/.exec(html) || [""])[0]
     + (/    function popupFit\(pop\) \{[\s\S]*?\n    \}/.exec(html) || [""])[0] + (/    function secselRoom\([\s\S]*?\n    \}/.exec(html) || [""])[0]) && te.length > 100);
ok("C4 the rule that keeps the chip in a 300 px pill beside the figures is unchanged (1024 px and wider)",
   html.includes("@media (min-width:1024px){ #kpi-conditions{ flex-wrap:wrap; max-width:300px; flex-shrink:0; column-gap:12px; row-gap:2px;"));


// ---- E: the road card's room is main's to the pixel with the chip present (a traffic-limit line forced in), and the chip gives way
const r0 = html.indexOf("    const SECSEL_HALF = 200;"), r1 = html.indexOf("    // 11 Nov 2026 (map popup top;"), q0 = html.indexOf("    const SECSEL_MINROW = 90"), q1 = html.indexOf("    function redrawRoadCard()");
const helpers = r0 >= 0 && r1 > r0 ? html.slice(r0, r1) : "", fitPart = q0 >= 0 && q1 > q0 ? html.slice(q0, q1) : "";
function roadWorld(W, H, below, fixedPart, x, y) {
  const cls = new Set(below ? ["cond-chip-below"] : []);
  const rect = (l, t, r, b) => ({ left: l, top: t, right: r, bottom: b });
  const els = { "kpi-hud": { getBoundingClientRect: () => rect(0, 26, W, 98) }, "kpi-conditions": { getBoundingClientRect: () => rect(W - 364, 105, W - 64, 145) }, "tl-warnings": null };
  const sc = { offsetHeight: 86, scrollHeight: 300, style: {} }, box = { offsetHeight: fixedPart + 86, offsetWidth: 360 };
  const pop = { options: { anchor: "bottom" }, setLngLat() {}, getLngLat: () => ({ lng: 0, lat: 0 }), setMaxWidth() { box.offsetHeight = fixedPart + 86; },
                getElement: () => ({ querySelector: q => (q === ".secsel-scroll" ? sc : q === ".mapboxgl-popup-content" ? box : null) }) };
  const SEC = { roadPopup: pop, roadAt: { lngLat: {}, point: { x, y } }, narrowed: 0 };
  const run = new Function("map", "document", "getComputedStyle", "window", "SECSEL", "hoverGiveWay", "chipGiveWay",
    helpers + "\n" + fitPart + "\nreturn fitRoadPopup;")(
    { getContainer: () => ({ getBoundingClientRect: () => rect(0, 0, W, H), clientWidth: W, clientHeight: H }), project: () => ({ x, y }) },
    { body: { classList: { contains: c => cls.has(c) } }, documentElement: {}, getElementById: id => els[id] || null }, () => ({ display: "flex", getPropertyValue: () => "94px" }),
    { innerWidth: W }, SEC, () => {}, () => {});
  run();
  return { anchor: pop.options.anchor, max: sc.style.maxHeight };
}
if (helpers && fitPart) {
  let cases = 0, differ = [];
  for (const [W, H] of [[1150, 677], [1150, 710], [1024, 700]]) for (const fixed of [184, 210, 236, 270]) for (let x = 100; x <= W - 100; x += 50) for (let y = 110; y <= H - 100; y += 25) {
    const withChip = roadWorld(W, H, true, fixed, x, y), main = roadWorld(W, H, false, fixed, x, y); cases++;
    if (withChip.anchor !== main.anchor || withChip.max !== main.max) differ.push([W, H, fixed, x, y, withChip, main]);
  }
  ok("E1 the road card's placing and its table's room are main's to the pixel with the chip below the bar: fixed parts 184 (ordinary), 210 (the 'no loads' line), 236 and 270 (a traffic limit's line), at 1150 x 677, 1150 x 710 and 1024 x 700 (" + cases + " clicks)",
     cases > 1000 && differ.length === 0, differ.slice(0, 2));
  // the live case as numbers: the B6047 card with its limit line (fixed 210+), click beside (x 711 y 300 at 1150 x 677): the table keeps main's room
  const live = roadWorld(1150, 677, true, 236, 711, 300), liveMain = roadWorld(1150, 677, false, 236, 711, 300);
  ok("E2 the live case (click 711, 300; the card with a traffic limit's line, fixed 236): the table's room with the chip equals main's: " + liveMain.max,
     live.max === liveMain.max && live.anchor === liveMain.anchor && parseInt(liveMain.max, 10) >= 90, [live, liveMain]);
} else { ok("E the road card's placing code could not be read", false); }

const gM = /    function chipGiveWay\(\) \{[\s\S]*?\n    \}/.exec(html), gSrc = gM ? gM[0] : "";
function giveWorld(below, chipRect, cards) {
  const cls = new Set(below ? ["cond-chip-below"] : []);
  const chip = { getBoundingClientRect: () => chipRect };
  const g = new Function("document", gSrc + "\nreturn chipGiveWay;")({ body: { classList: { contains: c => cls.has(c), toggle: (c, on) => { if (on) cls.add(c); else cls.delete(c); } } },
    getElementById: id => (id === "kpi-conditions" ? chip : null), querySelectorAll: () => cards.map(r => ({ getBoundingClientRect: () => r })) });
  return { g, away: () => cls.has("cond-chip-away"), cards };
}
if (gSrc) {
  const chipR = { left: 786, right: 1086, top: 105, bottom: 145 };
  let w = giveWorld(true, chipR, [{ left: 700, right: 1000, top: 108, bottom: 400, width: 300, height: 292 }]); w.g();
  ok("F1 an open card that lies over the chip (the chip below the bar): the chip gives way", w.away());
  w.cards.length = 0; w.g();
  ok("F2 the card closes: the chip comes back", !w.away());
  w = giveWorld(true, chipR, [{ left: 331, right: 701, top: 108, bottom: 510, width: 370, height: 402 }]); w.g();
  ok("F3 the live case: a card beside its click on the far side (x 331-701 against the chip's 786-1086): the chip stays", !w.away());
  w = giveWorld(true, chipR, [{ left: 700, right: 1000, top: 200, bottom: 400, width: 300, height: 200 }]); w.g();
  ok("F4 a card wholly below the chip does not move it", !w.away());
  w = giveWorld(false, chipR, [{ left: 700, right: 1000, top: 108, bottom: 400, width: 300, height: 292 }]); w.g();
  ok("F5 the chip in the bar (the figures fit, or a phone / tablet): it never gives way", !w.away());
  w = giveWorld(true, chipR, [{ left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 }]); w.g();
  ok("F6 a card that is not shown (no size) does not move it", !w.away());
  ok("F7 the page: the chip is hidden by a class only while it is below the bar, the page asks again when a card opens, closes or moves",
     /body\.cond-chip-below\.cond-chip-away #kpi-conditions\{ visibility:hidden; \}/.test(html) && /new MutationObserver\(chipAsk\)\.observe\(document\.body, \{ childList: true, subtree: true, attributes: true, attributeFilter: \['style', 'hidden'\] \}\)/.test(html)
     && /if \(typeof chipGiveWay === 'function'\) chipGiveWay\(\);\n\s+\} catch \(e\) \{\}\n\s+\}\n\s+window\.addEventListener\('resize', fitCondChip\)/.test(html));
} else { ok("F the chip's give-way could not be read", false); }

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
