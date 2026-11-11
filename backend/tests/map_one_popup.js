/* map_one_popup.js — 12 Nov 2026, branch claude/map-one-popup (the left-to-do cards A1-L2 and A1-F1, John's yes of 11 Nov).
 * Source checks on map/index.html plus sandboxes that run the page's OWN lines against stand-in maps; no browser (the browser
 * half is the Chrome check in the session note).
 *
 *   L2. A click on a road opened the road card AND an advisory zone's popup over its left part (live, the B6047, Apr 2027):
 *       an advisory (kind 'other') laid along a road now gives way to the road's card. A works area, a closure, a limit keep theirs.
 *   F1. A gate on its site's marker opened the gate's popup AND the holding area's (live, Lane entrance on Billesdon Lane
 *       holding area), and a place under a traffic limit's sign opened both (the case CLAUDE.md left for John): of a place's
 *       marker, a gate's marker and a limit's sign under one click, the one drawn on top answers alone.
 *
 * Its own file (BUILD.md rule 3): nothing appended to parse_map.js. Every check fails on the code before this branch.
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
// the source of one click handler, from its map.on('click', ...) line to the next map.on / forEach at the same level
function between(a, b) { const i = html.indexOf(a); if (i < 0) return ""; const j = html.indexOf(b, i + a.length); return html.slice(i, j > 0 ? j : i + 2500); }

// ---------- F1: topMarkerLayerAt, run against stand-in maps ----------
const topSrc = (/function topMarkerLayerAt\(point\) \{[\s\S]*?\n    \}/.exec(html) || [""])[0];
const makeTop = (map) => new Function("map", "TOP_MARKER_LAYERS", topSrc + "\nreturn topMarkerLayerAt;")(map, ["locations", "site-gates", "limit-signs"]);
const stub = (present, answer, throwIt) => {
  const seen = { layers: null };
  return { seen, map: { getLayer: l => present.indexOf(l) >= 0 ? {} : undefined,
    queryRenderedFeatures: (pt, o) => { seen.layers = o.layers; if (throwIt) throw new Error("x"); return answer.filter(a => o.layers.indexOf(a) >= 0).map(id => ({ layer: { id } })); } } };
};
ok("⭐ F1: the function is in the page and asks the map only for the marker layers that exist",
   !!topSrc && html.includes("const TOP_MARKER_LAYERS = ['locations', 'site-gates', 'limit-signs'];"));
{
  const all = ["locations", "site-gates", "limit-signs"];
  const a = stub(all, ["site-gates", "locations"]);
  ok("⭐ F1: a gate over its site's place: the GATE is on top (the map lists what lies under the point top-most first)",
     makeTop(a.map)({ x: 1, y: 1 }) === "site-gates" && a.seen.layers.join() === "locations,site-gates,limit-signs");
  ok("F1: a place over a gate: the place; a limit's sign over a place: the sign; one marker alone: that marker",
     makeTop(stub(all, ["locations", "site-gates"]).map)({ x: 1, y: 1 }) === "locations"
     && makeTop(stub(all, ["limit-signs", "locations"]).map)({ x: 1, y: 1 }) === "limit-signs"
     && makeTop(stub(all, ["locations"]).map)({ x: 1, y: 1 }) === "locations");
  ok("F1: nothing under the point, a layer that is not drawn yet, no point, or the map failing: '' (the handler answers as it always did)",
     makeTop(stub(all, []).map)({ x: 1, y: 1 }) === "" && makeTop(stub([], ["locations"]).map)({ x: 1, y: 1 }) === ""
     && makeTop(stub(all, ["locations"]).map)(null) === "" && makeTop(stub(all, ["locations"], true).map)({ x: 1, y: 1 }) === ""
     && stub(["locations"], ["locations"]).seen.layers === null);
  const b = stub(["locations", "site-gates"], ["site-gates"]); makeTop(b.map)({ x: 1, y: 1 });
  ok("F1: a layer that does not exist is left out of the question (no limit signs drawn: only the two others are asked)", b.seen.layers.join() === "locations,site-gates");
}

// ---------- F1: the three handlers each give way when another marker is on top (their own lines, run) ----------
const gateH = between("map.on('click', 'site-gates', (e) => {", "map.on('mouseenter', 'locations'");
const placeH = between("map.on('click', 'locations', (e) => {", "['restriction-points', 'restriction-lines']");
const signH = between("['limit-signs', 'limit-dots', 'limit-lines'].forEach(l => map.on('click', l, (e) => {", "    // \"Show on map\" from a Conditions row");
const guardOf = (src, layer) => { const m = new RegExp("\\{ const top = typeof topMarkerLayerAt === 'function' \\? topMarkerLayerAt\\(e\\.point\\) : ''; if \\(top && top !== '" + layer + "'\\) return; \\}").exec(src); return m ? m[0] : ""; };
const answers = (guard, top) => new Function("topMarkerLayerAt", "e", "typeof topMarkerLayerAt; " + guard + " return 'answers';")(() => top, { point: { x: 1, y: 1 } }) === "answers";
const gG = guardOf(gateH, "site-gates"), pG = guardOf(placeH, "locations");
ok("⭐ F1: the gate's handler has the guard (its own layer id), and runs it before it opens anything",
   !!gG && gateH.indexOf(gG) < gateH.indexOf("new mapboxgl.Popup"));
ok("⭐ F1: the place's handler has the guard, and runs it before it opens anything or asks for a street picture",
   !!pG && placeH.indexOf(pG) < placeH.indexOf("new mapboxgl.Popup") && placeH.indexOf(pG) < placeH.indexOf("svIntoPopup("));
if (gG && pG) {
  ok("⭐ F1 (run): a click with a gate over its site's place: the gate answers, the place gives way",
     answers(gG, "site-gates") === true && answers(pG, "site-gates") === false);
  ok("⭐ F1 (run): a place over a gate: the place answers, the gate gives way",
     answers(pG, "locations") === true && answers(gG, "locations") === false);
  ok("F1 (run): where the map cannot say which is on top ('') every handler answers as before: a marker is never silenced by a failed question",
     answers(gG, "") === true && answers(pG, "") === true);
  ok("F1 (run): a limit's sign on top gives way to nobody: a place or a gate under it gives way, as the sign answers",
     answers(gG, "limit-signs") === false && answers(pG, "limit-signs") === false);
} else ok("⭐ F1 (run): the guards could not be read", false);
ok("⭐ F1: the limit sign's handler gives way to a place or a gate on top (only for the SIGN layer; a ring or a stretch is unchanged), before it records the click",
   signH.includes("if (l === 'limit-signs') { const top = topMarkerLayerAt(e.point); if (top && top !== 'limit-signs') return; }")
   && signH.indexOf("if (l === 'limit-signs')") < signH.indexOf("LIM.lastClick = e.originalEvent"));

// ---------- L2: the zone popup gives way to the road card, for an advisory along a road only ----------
const zoneH = between("map.on('click', 'zone-fill', (e) => {", "map.on('click', 'temp-haul-lines'");
const zoneGuard = (/if \(e\.features\[0\]\.properties && e\.features\[0\]\.properties\.kind === 'other' && typeof roadCardHitAt === 'function' && roadCardHitAt\(e\.point\)\) return;/.exec(zoneH) || [""])[0];
ok("⭐ L2: the zone's handler has the guard, after the marker's guard and before it opens the popup",
   !!zoneGuard && zoneH.indexOf("markerHitAt(e.point)) return;") < zoneH.indexOf(zoneGuard) && zoneH.indexOf(zoneGuard) < zoneH.indexOf("new mapboxgl.Popup"));
if (zoneGuard) {
  const run = (kind, road, props) => new Function("roadCardHitAt", "e", "return (function(){ " + zoneGuard.replace(/\) return;$/, ") return 'gave way';") + " return 'popup'; })();")(() => road, { features: [{ properties: props === undefined ? { kind } : props }], point: {} });
  ok("⭐ L2 (run): an advisory with a road under the click gives way to the road's card",
     run("other", true) === "gave way");
  ok("⭐ L2 (run): an advisory with no road under the click keeps its popup; a works area, a closure and a weight limit keep theirs even over a road",
     run("other", false) === "popup" && run("works", true) === "popup" && run("closure", true) === "popup" && run("weight_limit", true) === "popup");
  ok("L2 (run): a zone with no properties is not mistaken for an advisory", run("other", true, null) === "popup");
} else ok("⭐ L2 (run): the guard could not be read", false);
ok("L2: the other popups' own guards are untouched (the temporary haul road and the zone keep the marker's guard first)",
   zoneH.includes("if (typeof markerHitAt === 'function' && markerHitAt(e.point)) return;      // 11 Nov: a place's or a gate's marker answers")
   && between("map.on('click', 'temp-haul-lines'", "// Phase 5a: the gate popup").includes("markerHitAt(e.point)) return;"));
ok("⭐ F1/L2: technical T1 says the marker on top answers alone and that an advisory gives way to the road's card",
   guide.includes('id="t1-one-popup-top"') && guide.includes("<code>topMarkerLayerAt</code>") && guide.includes("the marker on top answers alone")
   && guide.includes("advisory zone") && guide.includes("<code>roadCardHitAt</code>"));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
