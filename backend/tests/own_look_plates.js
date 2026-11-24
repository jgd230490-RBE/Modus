/*
 * own_look_plates.js — 24 Nov 2026, branch claude/own-look-road-plates (Group C of Wayscope's own look; card 3 of the
 * third mockup, John's "Yes, as recommended" to Q3; notes\design-language-1123.md, the row "Road numbers").
 *
 *   1  the helper   roadPlates(name): a road's number in a gate's, zone's or limit's name wrapped in a plate, the words unchanged
 *   2  the plate    CSS from the look's tokens: ink line, the surface, the one 6 px corner; a motorway in the sign blue with white
 *   3  contrast     every text pair on a plate at 4.5:1 or more, Light and Dark
 *   4  the places   the lists and tables that plate a name, and the names that stay plain (the map, pickers, sentences, labels)
 *
 * Source checks on frontend/index.html; the helper is cut out between its START / END comments and run with a stub React.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const css = html.slice(0, html.indexOf("</style>"));

// ---- 1 the helper ----------------------------------------------------------------------------------------------------
const a = html.indexOf("// ROAD PLATES START"), b = html.indexOf("// ROAD PLATES END");
ok("⭐ 1 helper: one roadPlates block on the page, between its START and END comments",
   a > 0 && b > a && html.indexOf("// ROAD PLATES START", a + 1) < 0 && (html.match(/function roadPlates\(/g) || []).length === 1);
const block = html.slice(a, b);
const React = { createElement: (t, p, c) => ({ t, cls: p.className, key: p.key, text: c }) };
const ctx = { React }; vm.createContext(ctx); vm.runInContext(block + "\nthis.roadPlates = roadPlates;", ctx);
const rp = ctx.roadPlates;
// what a person reads (and a screen reader reads): the parts joined; and the plates found
const said = (v) => Array.isArray(v) ? v.map(x => typeof x === "string" ? x : x.text).join("") : v;
const plates = (v) => Array.isArray(v) ? v.filter(x => typeof x !== "string").map(x => (x.cls.includes("rd-plate-m") ? "M:" : "") + x.text) : [];
const CASES = [
  ["A6 entrance (in)", ["A6"]],
  ["B6047", ["B6047"]],
  ["A47 at the new Tilton junction: HGV diversion while the junction is built", ["A47"]],
  ["M1 junction 21", ["M:M1"]],
  ["A1(M) slip road", ["M:A1(M)"]],
  ["Gate on the A1(M)", ["M:A1(M)"]],
  ["A606 / B6047 crossing", ["A606", "B6047"]],
  ["A6 A47 link", ["A6", "A47"]],
  ["Main compound gate", []],
  ["Old Dalby lane", []],
  ["A4 paper store", []],
  ["A3 sheet drawings", []],
  ["a6 entrance", []],
  ["b6047 gate", []],
  ["m1 junction", []],
  ["Gate off the B6047", ["B6047"]],
  ["Gate off the B6047.", ["B6047"]],
  ["Gate (A6)", ["A6"]],
  ["\"A6\" gate", ["A6"]],
  ["Route R014 gate", []],
  ["IPT1 compound", []],
  ["Zone Z004 limit", []],
  ["Gate G001", []],
  ["A0 gate", []],
  ["A06 gate", []],
  ["A12345 gate", []],
  ["B12 gate", []],
  ["M123 gate", []],
  ["MA1 gate", []],
  ["A6a gate", []],
  ["A6-A47 link", []],
  ["CAT-A1 site", []],
  ["Bay A1", ["A1"]],
  ["M25", ["M:M25"]],
  ["A9999 and B100", ["A9999", "B100"]],
  ["Rigid 8-wheeler tipper", []],
  ["A6, south gate", ["A6"]],
];
for (const [name, want] of CASES) {
  const got = rp(name);
  ok(`1 helper: "${name}" → plates [${want.join(", ")}] and the same words`,
     JSON.stringify(plates(got)) === JSON.stringify(want) && said(got) === name, JSON.stringify(plates(got)) + " · " + said(got));
  if (!want.length) ok(`1 helper: "${name}" comes back as the same string (no markup)`, got === name);
}
ok("🔴 1 helper: an empty, missing or non-string name comes back unchanged",
   rp("") === "" && rp(null) === null && rp(undefined) === undefined && rp(5) === 5);
ok("1 helper: plates carry keys unique within the name", (() => { const g = rp("A6 A47 B6047"); const k = g.filter(x => typeof x !== "string").map(x => x.key); return k.length === 3 && new Set(k).size === 3; })());
ok("1 helper: two calls in a row give the same answer (the regex's lastIndex is reset)", said(rp("A6 gate")) === "A6 gate" && plates(rp("A6 gate")).length === 1 && plates(rp("A6 gate")).length === 1);
ok("1 helper: the words are only wrapped: no title, no aria, nothing added to the plate",
   /React\.createElement\("span", \{ key: "rp" \+ at, className: "rd-plate" \+ \(nr\[0\] === "M" \|\| nr\.endsWith\("\(M\)"\) \? " rd-plate-m" : ""\) \}, nr\)/.test(block)
   && !/aria-|title:|role:/.test(block.replace(/^\/\/.*$/gm, "")));
ok("1 helper: no look-behind in the pattern (an older browser would refuse the whole script)", !/\(\?<[=!]/.test(block));

// ---- 2 the plate ---------------------------------------------------------------------------------------------------------
const rule = (sel) => { const m = css.match(new RegExp("\\n  " + sel.replace(/[.()[\]"=:]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : null; };
const base = rule(".rd-plate"), mw = rule(".rd-plate.rd-plate-m"), dk = rule('html[data-theme="dark"] .rd-plate:not(.rd-plate-m)');
ok("⭐ 2 plate: an ink line 2 px, the surface behind, 600 weight, 0 7 px inside and 3 px either side (card 3's .pl1)",
   base === "display:inline-block;font-weight:600;padding:0 7px;border:2px solid var(--ink);border-radius:6px;background:var(--surface);margin:0 3px;", base);
ok("2 plate: the corner is the look's one 6 px (card 3 drew 5 px; 3 px is for bars and key caps)", /border-radius:6px;/.test(base || ""));
ok("2 plate: in Light the plate's words keep the colour of the line they sit in (as drawn: grey in a second line, ink in a name)",
   !/(^|;)color:/.test(base || ""));
ok("⭐ 2 plate: a motorway is the sign blue #0B4EA2 with white words and a white inner line, in every look",
   mw === "background:#0B4EA2;border-color:#0B4EA2;color:#FFFFFF;box-shadow:inset 0 0 0 1.5px #FFFFFF;", mw);
ok("2 plate: Dark draws the words in the ink (#E6E7EA in Dark) on the Dark surface, a motorway left blue", dk === "color:var(--ink);", dk);
ok("🔴 2 plate: no pill, no stock blue, no new grey in the plate's rules",
   ![base, mw, dk].join("").match(/999px|#2563EB|#3B82F6|#[0-9A-F]{6}/gi)?.some(h => !/^#(0B4EA2|FFFFFF)$/i.test(h)));
const tok = (blockStart, name) => { const s = css.indexOf(blockStart); const e = css.indexOf("\n  }", s); const m = css.slice(s, e).match(new RegExp("--" + name + ":\\s*([^;]+);")); return m ? m[1].trim() : null; };
const L = { ink: tok("  :root{", "ink"), surface: tok("  :root{", "surface"), muted: tok("  :root{", "muted") };
const D = { ink: tok('  html[data-theme="dark"]{', "ink"), surface: tok('  html[data-theme="dark"]{', "surface") };
ok("2 plate: the tokens are the drawn colours (Light ink #1F2024 on #FFFFFF; Dark #E6E7EA on #1F2024)",
   L.ink === "#1F2024" && L.surface === "#FFFFFF" && D.ink === "#E6E7EA" && D.surface === "#1F2024", JSON.stringify([L, D]));

// ---- 3 contrast ---------------------------------------------------------------------------------------------------------
const lum = (hex) => { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (x, y) => { const [p, q] = [lum(x), lum(y)].sort((s, t) => t - s); return (p + 0.05) / (q + 0.05); };
const PAIRS = [["Light: ink on the plate", L.ink, L.surface], ["Light: caption grey on the plate (a second line)", L.muted, L.surface],
  ["Dark: ink on the plate", D.ink, D.surface], ["motorway: white on the sign blue", "#FFFFFF", "#0B4EA2"]];
for (const [label, fg, bg] of PAIRS) ok(`⭐ 3 contrast: ${label} at 4.5:1 or more`, ratio(fg, bg) >= 4.5, ratio(fg, bg).toFixed(2));
ok("3 contrast: the plate's own line stands off the page (ink on white, light ink on the Dark surface, 3:1 or more)",
   ratio(L.ink, "#FFFFFF") >= 3 && ratio(D.ink, D.surface) >= 3);

// ---- 4 the places --------------------------------------------------------------------------------------------------------
const PLATED = [
  ["Dashboard Gate arrivals, phone list", '<small>{roadPlates(r.g.gate_name)}</small>'],
  ["Dashboard Gate arrivals table, gate line", '<div className="ga-gate">{roadPlates(g.gate_name)}{'],
  ["Gate arrivals row details, Gate", '<RdItem t="Gate">{roadPlates(g.gate_name)}</RdItem>'],
  ["Dashboard Traffic limits table", '<td>{roadPlates(L.name)}</td>'],
  ["Abnormal loads table, gates", '{roadPlates([m.origin_gate_name, m.dest_gate_name].filter(Boolean).join(" → "))}'],
  ["Plan's moves table, the gate", '{m.dest_gate_name ? <>, {roadPlates(m.dest_gate_name)}</> : ""}'],
  ["Look-ahead Gates this week row", '<span className="gw-name">{g.location_name}<small>{roadPlates(g.gate_name)}</small></span>'],
  ["Gates this week open row's head", '<span className="text-slate-400 font-normal"> · {roadPlates(g.gate_name)}</span>'],
  ["Simulation traffic limits on this day", '{roadPlates(t.name)}: {tlNum(t.value)}'],
  ["Simulation stations now, a gate's line", '{r.gate ? roadPlates(r.sub) : r.sub}'],
  ["Simulation gates table", '<div className="sim-sub">{roadPlates(g.gate_name)}</div>'],
  ["Simulation phone card", '<div className="sim-pline">{roadPlates(g.gate_name)} · '],
  ["Simulation on-site table, a gate station", 'st.kind === "gate" ? roadPlates(st.name) : st.name}</b>'],
  ["Simulation haul roads table", '<td><b>{roadPlates(h.name)}</b></td>'],
  ["Routes diversions table", '{roadPlates((p.zone_names || []).join(", "))}'],
  ["Routes zones table", '{roadPlates(z.name) || l.zone_id}'],
  ["Locations gate list", '<span className="font-medium text-slate-700">{roadPlates(g.name)}</span>'],
  ["Locations gate list, access road", 'access road: {roadPlates(((haulRoadList || []).find(z => z.id === g.access_zone_id) || {}).name) || g.access_zone_id}'],
  ["Data → Zones table", 'openZoneFromKeys(z); }}>{roadPlates(z.name)}</button>'],
];
for (const [label, s] of PLATED) ok(`⭐ 4 places: ${label} plates the name`, html.includes(s));
ok("4 places: roadPlates is called at exactly these places (a new one is added here)",
   (html.match(/roadPlates\(/g) || []).length === PLATED.length + 1, String((html.match(/roadPlates\(/g) || []).length));
const PLAIN = [
  ["an accessible name stays a string (Gate arrivals row)", 'label={`Details for ${g.location_name}, ${g.gate_name}`}'],
  ["the zone button's name stays a string", 'aria-label={canEdit ? `Edit ${z.name}` : `Show ${z.name} on the map`}'],
  ["a picker's option stays plain", '<option key={g.gate_id} value={g.gate_id}>{simGateName(g)}, {g.gate_name}</option>'],
  ["a sentence stays plain (the plan's first trips)", "The plan's first trips: about {g.first_trip_pct} % at {simGateName(g)}, {g.gate_name}."],
  ["the chart's name stays a string (Gates this week)", 'const name = [g.location_name, g.gate_name].filter(Boolean).join(", ");'],
  ["a canvas axis stays plain (Gate arrivals)", 'return r ? [cutLabel(r.g.location_name), cutLabel(r.g.gate_name)] : "";'],
  ["the traffic limits chart title stays plain", '{L.name} <span className="text-slate-500 font-normal">({unitOf(L)} a day'],
  ["a road limit read from the road data stays plain", '{h.road_name || (h.road_nr ? `road ${h.road_nr}` : "")}'],
];
for (const [label, s] of PLAIN) ok(`4 places: ${label}`, html.includes(s));
ok("🔴 4 places: no plate on the map page", !fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").includes("rd-plate"));
const plateAt = [...html.matchAll(/rd-plate/g)].map(m => m.index);
ok("4 places: the class is written only in the plate's CSS and in the helper (no map popup's HTML string carries a plate)",
   plateAt.length === 8 && plateAt.every(i => i < css.length || (i > a && i < b)), String(plateAt.length));

console.log(`own_look_plates.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
