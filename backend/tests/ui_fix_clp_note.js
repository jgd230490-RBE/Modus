/*
 * ui_fix_clp_note.js — 11 Nov 2026, card D-F8 (John: "do it now"), branch claude/clp-note-two-lines.
 *
 *   CLP monitoring's note under its title ran the scope, the "planned, not observed" limit and the recorded line together:
 *   26 words, over the audit's long-prose rule (25) on a staff screen. The recorded words are now their own note line
 *   under the first, on the screen and in the pack. The words themselves do not change.
 *
 * Its own file (BUILD.md rule 3). Source checks only; the pack's lines are checked in test_clp.py.
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const pack = read("backend", "clp_pack.py");
const rules = read("backend", "tests", "lib", "ui_rules.js");

const at = html.indexOf("function ClpMonitoring(");
const body = at < 0 ? "" : html.slice(at, html.indexOf("\nfunction ", at + 10));

ok("🔴 D-F8: no note line runs the limit and the recorded line together on the screen",
   at > 0 && !/\{data\.limit\}\{data\.recorded_line \?/.test(body) && !/data\.limit\}[^<]*data\.recorded_line/.test(body));
ok("🔴 D-F8: the recorded line is its own ct-note line, only when the reply carries one, right under the scope + limit line",
   body.includes('<div className="ct-note">{data.scope_line} {data.limit}</div>\n          {data.recorded_line && <div className="ct-note" data-clp-recorded="1">{data.recorded_line}</div>}'));
ok("D-F8: the peak-hours line still follows as its own line",
   body.indexOf('data-clp-recorded="1"') < body.indexOf('data-clp-peak="1"'));
ok("🔴 D-F8: the pack prints the recorded line as its own paragraph under the scope + limit",
   pack.includes('story = [P_(E(" ".join(x for x in (M.get("scope_line"), M.get("limit")) if x)), st_g)]')
   && /if M\.get\("recorded_line"\):\n\s+story\.append\(P_\(E\(M\["recorded_line"\]\), st_g\)\)/.test(pack)
   && !pack.includes('(M.get("scope_line"), M.get("limit"), M.get("recorded_line"))'));
ok("D-F8: no new long-prose pin for CLP monitoring's note (the split is the fix, not a pin)",
   !/Every team's approved lines|Recorded tonnes as typed on Account/.test(rules));

console.log(`ui_fix_clp_note.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
