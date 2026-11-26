/*
 * ui_fix_warn_chips.js — 26 Nov 2026, branch claude/routes-diverted-chip.
 *
 *   The UI audit of `main` 6a2e27f (the Simulation session's run, 25 Nov) failed axe colour-contrast (serious) on
 *   Data → Routes at 1,366 px in the ink look: the "Diverted …" chip on R002, #B45309 on a 12 % amber tint = #F6EAE1,
 *   4.25:1 against 4.5:1. The same audit of 26a0f53 (before the Routes rethink's batch) shows it too: the chip dates
 *   from 28 Oct. The same see-through amber sat under four more amber words (busy hours paused, "Route again: does not
 *   pass the holding area", the Zones "Busy hours" line and the "no way round yet" box at 10 %, 4.39:1). Every one now
 *   sits on the status chip's own solid token var(--st-warn-bg) (#FFFBEB in ink, 4.84:1; #3A2E1C in Dark, 7.92:1), as
 *   the haul-road chip moved to a solid var(--haul-soft) on 22 Oct. The navy (6.83:1) and red (5.38:1) tints pass and
 *   are left. Its own file (BUILD.md rule 3); source checks plus the ratios worked out here (jsdom has no layout).
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");

// WCAG 2 contrast, the same sums axe uses
const lum = h => { const c = [0, 2, 4].map(i => parseInt(h.replace("#", "").slice(i, i + 2), 16) / 255)
  .map(x => x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const tok = (name, dark) => {
  const blocks = html.match(new RegExp("--" + name + ":(#[0-9A-Fa-f]{6})", "g")) || [];
  const v = blocks.map(m => m.split(":")[1]);
  return dark ? v[1] : v[0];
};

ok("🔴 no amber word sits on a see-through amber tint any more",
   !/background: "rgba\(180,83,9,\.1[02]\)", color: "var\(--warn-text\)"/.test(html));
// REVERSED 26 Nov 2026 (the own look's shape branch taken in with main): the five amber words are no longer chips on a
// solid tint. Each is a status, a shape and a word with no background (RowStatus, or the .st-line sentence), so the
// pair that must pass is --warn-text on the surface itself, in ink and in Dark.
const solid = (html.match(/background: "var\(--st-warn-bg\)", color: "var\(--warn-text\)"/g) || []).length;
ok("🔴 REVERSED: no amber word sits on a tint at all (the five are a shape and a word)", solid === 0, String(solid));
const chip = html.slice(html.indexOf("<span data-route-diverted={r.id}"), html.indexOf("<span data-route-diverted={r.id}") + 500);
ok("the Routes list's 'Diverted …' word is a RowStatus, no tint", /<RowStatus /.test(chip) && !/st-warn-bg|rgba\(/.test(chip), chip.slice(0, 160));
const busyI = html.indexOf("paused: the road changed");
const busy = html.slice(busyI - 200, busyI + 200);
ok("the paused busy-hours word in the Routes list is a RowStatus", busyI > 0 && /<RowStatus word=\{`Busy hours: Alt \$\{u\.alt\}`\} tone="warn" \/>/.test(busy));
const hold = html.slice(html.indexOf('hr.state === "route_again") return <span data-route-holding'), html.indexOf('hr.state === "route_again") return <span data-route-holding') + 400);
ok("the holding-area 'Route again' word is a RowStatus", /<RowStatus word=\{words\} tone="warn" \/>/.test(hold));
const stuckI = html.indexOf("no way round yet. Until you find one");
const stuck = html.slice(stuckI - 300, stuckI);
ok("the 'no way round yet' line is a status sentence (.st-line), no box", stuckI > 0 && /st-line st-warn/.test(stuck) && !/st-warn-bg/.test(stuck));

const tokv = (name, dark) => { const v = (html.match(new RegExp("--" + name + ":(#[0-9A-Fa-f]{6})", "g")) || []).map(m => m.split(":")[1]); return dark ? v[1] : v[0]; };
const warnInk = tokv("warn-text", false), bgInk = tokv("surface", false);
const warnDk = tokv("warn-text", true), bgDk = tokv("surface", true);
ok("ink: --warn-text on the surface passes 4.5:1", warnInk && bgInk && ratio(warnInk, bgInk) >= 4.5, `${warnInk} on ${bgInk} ${warnInk && bgInk ? ratio(warnInk, bgInk).toFixed(2) : "?"}`);
ok("Dark: --warn-text on the surface passes 4.5:1", warnDk && bgDk && ratio(warnDk, bgDk) >= 4.5, `${warnDk} on ${bgDk} ${warnDk && bgDk ? ratio(warnDk, bgDk).toFixed(2) : "?"}`);
ok("the old pair really failed (the audit's 4.25:1)", Math.abs(ratio("#B45309", "#F6EAE1") - 4.25) < 0.01);

console.log(`ui_fix_warn_chips.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
