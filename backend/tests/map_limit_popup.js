/* map_limit_popup.js — 12 Nov 2026, branch claude/map-limit-popup-marker (card A1-L4, a fault found on live in passing).
 *
 * Live, Jan 2028: a click on the Billesdon Lane holding area's marker opened the holding area's popup AND the B6047 traffic limit's
 * zone popup ("Traffic limit · B6047 Melton Road ... 38 lorry movements a day ...") over it. A place's or a gate's marker answers
 * its click alone (the standing rule of 11 Nov: a click handler on a line or an area under markers starts with markerHitAt); the
 * limit zone's handler (trafficLimitPopup) did not ask. Source check plus the page's own function run against stand-ins.
 * No browser (the browser half is the Chrome run in the session note). Every check fails on the code before this branch.
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

const src = (/    function trafficLimitPopup\(e\) \{[\s\S]*?\n    \}\n    function loadTrafficLimits/.exec(html) || [""])[0].replace(/\n    function loadTrafficLimits$/, "\n");
ok("A1 the zone popup's handler is in the page", !!src);
ok("A2 it asks markerHitAt(e.point) first, before the road card's check", /const f = e\.features && e\.features\[0\]; if \(!f\) return;\n(?:.*\n)*?\s+if \(typeof markerHitAt === 'function' && markerHitAt\(e\.point\)\) return;(?:.*\n)*?\s+if \(typeof roadCardHitAt/.test(src), src.slice(0, 500));

function run(opts) {
  const popups = [];
  class Popup { constructor(o) { popups.push({ opts: o }); } setLngLat() { return this; } setHTML(h) { popups[popups.length - 1].html = h; return this; } addTo() { return this; } }
  const L = { id: "Z041", name: "B6047 Melton Road", limit: { value: 150, basis: "daily" }, months: { "25": { state: "over", value: 162, routes: [] } } };
  const g = { markerHitAt: opts.noFn ? undefined : (pt => { g.seen = pt; return !!opts.marker; }), roadCardHitAt: () => false, seen: null };
  const f = new Function("markerHitAt", "roadCardHitAt", "TLIM", "routePropsById", "escHtml", "tlimUnit", "tlimN", "tlimV", "monthLabel", "TLIM_COL", "mapboxgl", "map",
    src + "\nreturn trafficLimitPopup;")(g.markerHitAt, g.roadCardHitAt, { data: { limits: [L] }, month: 25 }, () => ({}), x => String(x), () => "movements", x => String(x), x => String(x), () => "Jan 2028", { over: "#b91c1c", none: "#64748b" }, { Popup }, {});
  const point = { x: 804, y: 424 };
  f({ features: [{ properties: { id: "Z041" } }], point, lngLat: { lng: 0, lat: 0 } });
  return { popups, seen: g.seen, point };
}
if (src) {
  let r = run({ marker: true });
  ok("B1 a click on a place's or a gate's marker: the zone popup does not open", r.popups.length === 0, r.popups.length);
  ok("B2 it asks about the event's own point", !!r.seen && r.seen.x === 804 && r.seen.y === 424, r.seen);
  r = run({ marker: false });
  ok("B3 a click on the zone with no marker under it: the popup opens as before, once", r.popups.length === 1 && /Traffic limit · B6047 Melton Road/.test(r.popups[0].html || ""), r.popups.length);
  r = run({ noFn: true });
  ok("B4 where markerHitAt does not exist (an older page) the popup still opens", r.popups.length === 1);
} else { ok("B the sandbox could not run: trafficLimitPopup is missing", false); }

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
