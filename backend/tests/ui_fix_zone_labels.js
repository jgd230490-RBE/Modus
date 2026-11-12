/*
 * ui_fix_zone_labels.js — 11 Nov 2026, card B-X1 (rule 13: a fault found along the way), branch claude/clocs-b-zone-labels.
 *
 *   The data pages' map (Locations, Routes and Zones share it) drew each zone's name in slate (#334155) on a 2 px WHITE halo
 *   at 11 px, whatever the basemap. On the Dark look (the Dark basemap since card 14) every name read as a white block with
 *   grey text. The names now follow the public map's name rule (labelPaint in map/index.html): ink on a soft white halo, or
 *   near-white on a near-black halo on a dark ground (Dark, Navigation night, the aerial styles); 12 px, the app's floor.
 *
 * Its own file (BUILD.md rule 3). Source checks, plus the two helpers run on their own.
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const mapPage = read("map", "index.html");

// the zone-label layer of the data pages' map
const at = html.indexOf('if(!m.getLayer("zone-label")) m.addLayer({ id: "zone-label"');
const layer = at < 0 ? "" : html.slice(at, html.indexOf("});", at) + 3);
const before = at < 0 ? "" : html.slice(Math.max(0, at - 700), at);
const after = at < 0 ? "" : html.slice(at, at + 600);

ok("🔴 B-X1: the zone names are no longer slate on a fixed white halo", at > 0 && !layer.includes('"text-color": "#334155"') && !layer.includes('"text-halo-color": "#ffffff"'));
ok("🔴 B-X1: the paint comes from zoneLabelPaint(mapGroundDark(...)) of the basemap last set",
   /const zonePaint = zoneLabelPaint\(mapGroundDark\(basemapShown\.current \|\| basemap\)\);/.test(before) && layer.includes("paint: zonePaint"));
ok("🔴 B-X1: 12 px, the app's floor (was 11)", layer.includes('"text-size": 12') && !layer.includes('"text-size": 11'));
ok("B-X1: the paint is set again after the add (a layer kept across a style change keeps its old paint)",
   /Object\.keys\(zonePaint\)\.forEach\(k => \{ try \{ m\.setPaintProperty\("zone-label", k, zonePaint\[k\]\); \} catch\(e\)\{\} \}\);/.test(after));
ok("B-X1: changeStyle records the style it sets", /basemapShown\.current = val;\n\s+setBasemap\(val\);/.test(html));
ok("B-X1: one basemapShown ref", (html.match(/const basemapShown = useRef\(null\);/g) || []).length === 1);

// the helpers, run on their own
const grab = (name) => { const m = html.match(new RegExp("const " + name + " = [\\s\\S]*?;\\n")); return m ? m[0] : ""; };
const src = grab("mapGroundDark") + grab("zoneLabelPaint");
let mapGroundDark = null, zoneLabelPaint = null;
try { ({ mapGroundDark, zoneLabelPaint } = new Function(src + "; return { mapGroundDark, zoneLabelPaint };")()); } catch (e) {}
ok("B-X1: both helpers parse", typeof mapGroundDark === "function" && typeof zoneLabelPaint === "function", src.slice(0, 120));
if (mapGroundDark && zoneLabelPaint) {
  const DARK = ["mapbox://styles/mapbox/dark-v11", "mapbox://styles/mapbox/navigation-night-v1", "mapbox://styles/mapbox/satellite-streets-v12",
                "mapbox://styles/mapbox/satellite-v9", "maaamet-ortho"];
  const LIGHT = ["mapbox://styles/mapbox/light-v11", "mapbox://styles/mapbox/streets-v12", "mapbox://styles/mapbox/outdoors-v12",
                 "mapbox://styles/mapbox/navigation-day-v1", "", null, undefined];
  ok("B-X1: a dark ground = Dark, Navigation night, both aerial styles, the Estonian photo", DARK.every(s => mapGroundDark(s) === true));
  ok("B-X1: a light ground = Light, Streets, Outdoors, Navigation day, nothing set", LIGHT.every(s => mapGroundDark(s) === false));
  // every basemap the picker offers is classed one way or the other
  const offered = [...html.matchAll(/^\s+\["[^"]+", "((?:mapbox:\/\/styles\/mapbox\/[a-z0-9-]+)|maaamet-ortho)"\],$/gm)].map(m => m[1]);
  ok("B-X1: the picker's nine basemaps are all in the two lists above", offered.length === 9 && offered.every(s => DARK.includes(s) || LIGHT.includes(s)), JSON.stringify(offered));
  const d = zoneLabelPaint(true), l = zoneLabelPaint(false);
  ok("🔴 B-X1: on a dark ground, near-white on a near-black halo", d["text-color"] === "#F5F5F4" && d["text-halo-color"] === "rgba(18,19,22,0.92)");
  ok("B-X1: on a light ground, ink on white", l["text-color"] === "#1F2024" && l["text-halo-color"] === "#FFFFFF");
  ok("B-X1: halo 1.75 px with 0.5 blur both ways (no more 2 px block)", [d, l].every(p => p["text-halo-width"] === 1.75 && p["text-halo-blur"] === 0.5));
  // the same values as the public map's name rule, so the two maps' zone names read alike
  ok("B-X1: the public map's labelPaint carries the same inks and halos",
     mapPage.includes("(dark ? '#F5F5F4' : '#1F2024')") && mapPage.includes("'text-halo-color': dark ? 'rgba(18,19,22,0.92)' : '#FFFFFF', 'text-halo-width': 1.75, 'text-halo-blur': 0.5"));
  ok("B-X1: and the same dark-ground test", mapPage.includes("/dark|night|satellite|maaamet/.test(bm)"));
}

console.log(`ui_fix_zone_labels.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
