/*
 * ui_fix_demo_path.js — 10 Nov 2026, branch claude/ui-fix-demo-path (mockup notes\ui-fix-demo-path-mockup-1110\,
 * John: "Yes, Q1–Q9"): the public map's Conditions rows for lorry limits.
 *
 *   F10: a weight-limit row says the sign's exception ("7.5 t, except for access") or "no exception recorded: check the
 *        sign"; no supplier on the row (the sign's card keeps its Source row; screens name no supplier).
 *   C3:  ONE row per road (kind, value, exception and road name), listing the routes over it ("R002, R005, R008 +7");
 *        an unnamed stretch is its own row; "Show on map" frames every stretch of the road and opens the first's card.
 *
 * Its own file (the wave rule): parse_map.js keeps its three pins, REVERSED there with the date. The functions run for
 * real, cut out of the page by name. The Python side (F10b, F7, C2, C1, F8) is test_ui_fix_demo_path.py.
 *
 * NOT covered: the map drawn in a browser (checked by hand on a local copy and on live after the merge).
 * Run:  node backend/tests/ui_fix_demo_path.js
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const map = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

// a function's whole source, by name, matched brace for brace (strings and comments are simple enough here)
function fnSrc(name) {
  const i = map.indexOf("function " + name + "(");
  if (i < 0) return "";
  let j = map.indexOf("{", i), depth = 0;
  for (let k = j; k < map.length; k++) {
    const ch = map[k];
    if (ch === "{") depth++;
    else if (ch === "}") { depth--; if (depth === 0) return map.slice(i, k + 1); }
  }
  return "";
}
const NAMES = ["limitPropsOf", "limitValueText", "limitKindWord", "limitBreachLines", "limitConditionRows", "showLimit"];
const srcs = NAMES.map(fnSrc);
ok("the six functions are cut out of the page", srcs.every(s => s.length > 40), NAMES.filter((n, i) => srcs[i].length <= 40).join(","));

const calls = { fit: [], fly: [], card: [], boxes: [] };
const LIM = { byId: {} };
const fakeMap = { getZoom: () => 9, fitBounds: (b, o) => calls.fit.push([b, o]), flyTo: o => calls.fly.push(o), jumpTo: o => calls.fly.push(o) };
const document = { getElementById: id => ({ id, checked: false, dispatchEvent() { calls.boxes.push(id); return true; } }) };
let L = null, err = "";
try {
  L = new Function("map", "document", "LIM", "LIMIT_BOX_OF", "LIMIT_LABEL_ZOOM", "openLimitCardAt", "reducedMotion", "isPhoneShell", "setTimeout",
    srcs.join("\n") + "\nfunction limitById(id) { return (LIM.byId && LIM.byId[id]) || null; }\n"
    + "return { limitConditionRows, showLimit, limitBreachLines };")(
    fakeMap, document, LIM, { weight: "weight", axle: "weight", height: "height", width: "width" }, 14,
    (p, c) => calls.card.push([p.id, c]), () => false, () => false, f => f());
} catch (e) { err = String(e && e.stack || e); }
ok("the functions run against plain data and a fake map", !!L, err.slice(0, 300));

if (L) {
  const W = (id, name, routes, extra) => Object.assign({ id, kind: "weight", value: 7.5, unit: "t", name, ref: null,
    exceptions: "Except for access", source: "osm", source_label: "OpenStreetMap", anchor: [-0.9, 52.6],
    breaches: routes.map(r => ({ route_id: r, vehicle: "Artic Tipper (44t)", leg: "loaded" })), breach_count: routes.length }, extra || {});
  const F = (p, coords) => ({ type: "Feature", geometry: coords ? { type: "LineString", coordinates: coords } : { type: "Point", coordinates: p.anchor }, properties: p });
  // Loughborough Road in five stretches (live, Apr 2027), Rearsby Road in one, an unnamed stretch with no exception
  const feats = [
    F(W("osm:w1:weight", "Loughborough Road", ["R005", "R002"]), [[-0.91, 52.60], [-0.909, 52.60]]),
    F(W("osm:w2:weight", "Loughborough Road", ["R008", "R002", "R011"]), [[-0.90, 52.61], [-0.899, 52.61]]),
    F(W("osm:w3:weight", "Loughborough Road", ["R010"])),
    F(W("osm:w4:weight", "Rearsby Road", ["R008"])),
    F(W("osm:w5:weight", null, ["R008"], { exceptions: null })),
    F(W("osm:w6:weight", null, ["R009"], { exceptions: null })),
    F(W("osm:w7:weight", "Loughborough Road", ["R099"])),                                   // a route not in use
    F(W("osm:w8:weight", "Loughborough Road", ["R003"], { value: 18 })),                    // another limit on the same road
  ];
  const inUse = ["R002", "R005", "R008", "R010", "R011", "R003", "R009"];
  const rows = L.limitConditionRows(feats, inUse, 16);
  const lough = rows.find(r => /Loughborough Road$/.test(r.what) && r.what.includes("7.5 t"));
  ok("C3: ⭐ one row per road: Loughborough Road's three stretches in use give ONE 7.5 t row, listing every route over them",
     lough && lough.what === "R002, R005, R008 +2 · 7.5 t, except for access · Loughborough Road" && lough.id === "osm:w1:weight,osm:w2:weight,osm:w3:weight",
     JSON.stringify(rows.map(r => r.what)));
  ok("C3: a stretch whose routes are not in use this month adds nothing; another limit value on the same road is its own row",
     !rows.some(r => r.id.includes("osm:w7")) && rows.some(r => r.what === "R003 · Artic Tipper (44t) · 18 t, except for access · Loughborough Road"));
  ok("F10: ⭐ a road with one route over it names the route and its lorry: 'R008 · Artic Tipper (44t) · 7.5 t, except for access · Rearsby Road'",
     rows.some(r => r.what === "R008 · Artic Tipper (44t) · 7.5 t, except for access · Rearsby Road"));
  ok("F10: ⭐ no exception recorded says so: 'R008 · Artic Tipper (44t) · 7.5 t · no exception recorded: check the sign'",
     rows.some(r => r.what === "R008 · Artic Tipper (44t) · 7.5 t · no exception recorded: check the sign"));
  ok("C3: two unnamed stretches are two rows (never merged by a missing name)",
     rows.filter(r => r.what.includes("no exception recorded")).length === 2);
  ok("F10: ⭐ no row names the supplier (screens name no supplier; the sign's card keeps it)",
     rows.every(r => !/OpenStreetMap|HERE|\(osm\)/.test(r.what)), JSON.stringify(rows.map(r => r.what)));
  ok("C3: rows keep the Conditions shape (warn, src 'limit', kind 'l', 'Over a weight limit', sort 1.2) and a key per road and month",
     rows.every(r => r.lvl === "warn" && r.src === "limit" && r.kind === "l" && r.noun === "Over a weight limit" && r.sort === 1.2)
     && new Set(rows.map(r => r.key)).size === rows.length && lough.key === "l|weight|7.5|except for access|Loughborough Road|16");
  ok("C3: the pill counts the same rows: 5 roads, not 7 stretches", rows.length === 5, String(rows.length));
  // Show on map
  feats.forEach(f => { LIM.byId[f.properties.id] = f; });
  L.showLimit(lough.id);
  ok("C3: ⭐ 'Show on map' on a road's row frames every stretch (one fitBounds over them all) and opens the first stretch's card",
     calls.fit.length === 1 && calls.fit[0][0][0][0] <= -0.91 && calls.fit[0][0][1][0] >= -0.899 && calls.card.length === 1 && calls.card[0][0] === "osm:w1:weight"
     && calls.boxes.includes("layer-limit-weight"), JSON.stringify(calls));
  calls.fit.length = 0; calls.card.length = 0;
  L.showLimit("osm:w4:weight");
  ok("C3: a one-stretch row still flies to its sign as before (no fitBounds)", calls.fit.length === 0 && calls.fly.length === 1 && calls.card.length === 1);
}
ok("F10: the old row words are gone from the page ('is over the … limit on …', the supplier in brackets)",
   !map.includes("' is over the ' + limitValueText") && !map.includes("'source not named'"));

console.log(`ui_fix_demo_path.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  ✗ " + f)); process.exit(1); }
