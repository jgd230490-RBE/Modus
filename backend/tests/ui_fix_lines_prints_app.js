/* ui_fix_lines_prints_app.js — 26 Nov 2026, branch claude/lines-prints-app (the staff and printed maps' route lines, task A;
 * John's "Yes, as recommended" to Q1 to Q9 of notes\map-lines-prints-mockup-1125, cards 1 and 2; the brief
 * notes\map-lines-prints-build-1126\README.md). The app's own small maps follow the public map's ink and grey:
 *   Q1  CommitMap (the Dashboard's "Today on the map" and the Look-ahead's "This week's movements"): out (loaded) ink
 *       #3A3C41, back (empty) grey #8E9197; on a dark ground the Routes page's Dark pair #D4D6DA / #9A9DA3 on its dark casing;
 *   Q2  "later this week" the line grey #C6C8CC at 0.9 (on a dark ground the Routes page's dark quiet grey #7D8087);
 *   Q3  the Simulation's route lines (sim-routes, sim-busy-main) the public map's quiet grey #A9ABB0; the lorry marks and
 *       the dashed route-end line unchanged.
 *   The user guide's two sentences on these maps name the new colours; the export sentence is task B's and is left alone.
 * Source checks and the pair worked out by the page's own cmLegs. Not covered here: pixels on a real map (the session note's
 * Chrome pictures, notes\session-1126-lines-prints-app.md).
 * Every check marked ⭐ fails on the files before this branch. To see that:
 *   node backend/tests/ui_fix_lines_prints_app.js <folder holding main's frontend/index.html and frontend/help/index.html>
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  → " + String(extra).slice(0, 500) : "")); };
const TRY = (f) => { try { return f(); } catch (e) { return false; } };

const ROOT = process.argv[2] || path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n/g, "\n");
const noComments = (s) => s.split("\n").map(l => l.replace(/(^|[^:"'])\/\/.*$/, "$1")).join("\n");
const cmSrc = noComments(html.slice(html.indexOf("function CommitMap({"), html.indexOf("function commitMapFigs(")));
const simSrc = noComments(html.slice(html.indexOf('m.on("style.load", () => {\n      if(m.getSource("sim-routes")) return;'), html.indexOf('m.addLayer({ id: "sim-haul",')));

// ---- Q1, Q2: the week maps' constants and the pair a ground gets ----
ok("⭐ Q1: CM_OUT is ink #3A3C41 and CM_BACK grey #8E9197 (was green #059669 and amber #f59e0b)",
   html.includes('const CM_OUT = "#3A3C41", CM_BACK = "#8E9197"') && !/const CM_OUT = "#059669"/.test(html) && !/CM_BACK = "#f59e0b"/.test(html));
ok("⭐ Q2: \"later this week\" is the line grey #C6C8CC at 0.9 (was #9CA3AF at 0.55)",
   html.includes('CM_FADED = "#C6C8CC", CM_FADED_OPACITY = 0.9;') && cmSrc.includes('"line-color": L.faded, "line-width": 2, "line-opacity": CM_FADED_OPACITY')
   && !cmSrc.includes('"line-opacity": 0.55'));
// the page's own cmLegs, run with the Routes page's Dark constants as the page defines them
const pick = (re) => { const m = html.match(re); return m ? m[0] : ""; };
const legsFn = TRY(() => new Function(
  pick(/const LEG_OUT_DARK = "[^\n]*;/) + "\n" + pick(/const CM_OUT = "[^\n]*;/) + "\n" + pick(/const CM_FADED_DARK = "[^\n]*;/) + "\n"
  + pick(/function cmLegs\(dark\)\{[\s\S]*?\n\}/) + "\nreturn cmLegs;")());
const light = TRY(() => legsFn(false)), dark = TRY(() => legsFn(true));
ok("⭐ Q1, Q2: cmLegs(light) = ink out, grey back, the line grey for the week, a white casing",
   light && light.out === "#3A3C41" && light.back === "#8E9197" && light.faded === "#C6C8CC" && light.edge === "#ffffff", JSON.stringify(light));
ok("⭐ Q1: cmLegs(dark) = the Routes page's Dark pair #D4D6DA / #9A9DA3 on its dark casing #1F2024; the week in the dark quiet grey #7D8087",
   dark && dark.out === "#D4D6DA" && dark.back === "#9A9DA3" && dark.faded === "#7D8087" && dark.edge === "#1F2024", JSON.stringify(dark));
ok("Q1: the Dark pair is the Routes page's own (LEG_OUT_DARK / LEG_BACK_DARK / LEG_CASE_DARK), not a copy",
   /return dark \? \{ out: LEG_OUT_DARK, back: LEG_BACK_DARK, faded: CM_FADED_DARK, edge: LEG_CASE_DARK \}/.test(html)
   && html.includes('const LEG_OUT_DARK = "#D4D6DA", LEG_BACK_DARK = "#9A9DA3", LEG_CASE = "#ffffff", LEG_CASE_DARK = "#1F2024";'));
ok("⭐ Q1: every CommitMap line layer reads its colour from the pair for the ground its one map opens on (no green, amber or #9CA3AF left in it)",
   cmSrc.includes("const [cmDark] = useState(() => mapGroundDark(lookMapStyle()));") && cmSrc.includes("style: lookMapStyle(),") && cmSrc.includes("const L = cmLegs(cmDark);")
   && ['"line-color": L.out', '"line-color": L.back', '"line-color": L.faded', '"line-color": L.edge'].every(w => cmSrc.includes(w))
   && !/#059669|#f59e0b|#9CA3AF/i.test(cmSrc));
ok("Q1: the legs keep their widths and their side of the road (4 / 2.5 px, the white casing 6.5 / 5, OFF to the left)",
   cmSrc.includes('"line-color": L.out, "line-width": 4, "line-offset": OFF') && cmSrc.includes('"line-color": L.back, "line-width": 2.5, "line-offset": OFF')
   && cmSrc.includes('"line-width": ["match", ["get", "kind"], "out", 6.5, 5], "line-opacity": 0.9, "line-offset": OFF'));

// ---- the key ----
ok("⭐ Q1, Q2: the key's swatches: ink out, grey back, the line grey at .9 for later this week",
   html.includes(".cm-k-out{height:4px;background:#3A3C41;} .cm-k-back{height:3px;background:#8E9197;} .cm-k-faded{height:2px;background:#C6C8CC;opacity:.9;}"));
ok("⭐ Q1: on a dark ground the key follows the map (data-cm-dark on the key row; the Dark pair in the CSS)",
   cmSrc.includes('data-cm-dark={cmDark ? "1" : "0"}') && cmSrc.includes("const [cmDark] = useState(() => mapGroundDark(lookMapStyle()));")
   && html.includes('.cm-key[data-cm-dark="1"] .cm-k-out{background:#D4D6DA;} .cm-key[data-cm-dark="1"] .cm-k-back{background:#9A9DA3;} .cm-key[data-cm-dark="1"] .cm-k-faded{background:#7D8087;}'));
ok("Q1: the key's words are unchanged (Today, out (loaded) / Today, back (empty) / Later this week / Out (loaded))",
   ["Today, out (loaded)", "Today, back (empty)", "Later this week", '"Out (loaded)"', "Gate (zoom in)"].every(w => cmSrc.includes(w)));

// ---- Q3: the Simulation ----
ok("⭐ Q3: the Simulation's route lines and the busy-hours road's main road are the quiet grey #A9ABB0 (was the slate #94A3B8)",
   html.includes('const SIM_ROUTE_LINE = "#A9ABB0";')
   && simSrc.includes('m.addLayer({ id: "sim-routes", type: "line", source: "sim-routes", paint: { "line-color": SIM_ROUTE_LINE, "line-width": 1.6, "line-opacity": 0.75 } });')
   && /id: "sim-busy-main"[^\n]*"line-color": SIM_ROUTE_LINE, "line-width": 1\.6, "line-opacity": 0\.75/.test(simSrc));
ok("Q3: the lorry marks and the dashed route-end line are left as they were (not this task's)",
   simSrc.includes('m.addLayer({ id: "sim-ends", type: "line", source: "sim-ends", paint: { "line-color": "#94A3B8", "line-width": 1, "line-dasharray": [2, 2] } });')
   && html.includes(".sim-line-end{border-top:1.5px dashed #94A3B8;}"));

// ---- the user guide ----
ok("⭐ guide: Today on the map says dark grey out, light grey back, the week thinner and paler (not green, amber, faded grey)",
   guide.includes("out (loaded) in dark grey and back (empty) in light grey, each on the left of its own direction, with today's load on a tag; lines later this week thinner and paler.")
   && !guide.includes("out (loaded) in green and back (empty) in amber"));
ok("⭐ guide: the Look-ahead's week map says dark grey (not green)",
   guide.includes("draws this week's lines, out (loaded) in dark grey, with the week's load on a tag") && !guide.includes("draws this week's lines, out (loaded) in green"));
ok("guide: the same words as 9.2's Routes map for the pair (dark grey / light grey)",
   guide.includes("out (laden) in dark grey and back (empty) in light grey"));

console.log(`ui_fix_lines_prints_app.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  FAIL: " + f));
process.exit(fail.length ? 1 : 0);
