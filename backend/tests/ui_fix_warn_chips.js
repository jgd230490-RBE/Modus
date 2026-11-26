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
const solid = (html.match(/background: "var\(--st-warn-bg\)", color: "var\(--warn-text\)"/g) || []).length;
ok("🔴 the five amber words sit on the solid var(--st-warn-bg)", solid === 5, String(solid));

const chip = html.slice(html.indexOf("<span data-route-diverted={r.id}"), html.indexOf("<span data-route-diverted={r.id}") + 500);
ok("the Routes list's 'Diverted …' chip is one of them", /background: "var\(--st-warn-bg\)", color: "var\(--warn-text\)"/.test(chip), chip.slice(0, 120));
ok("...and its red 'Not diverted' side is unchanged (5.38:1 on white already)", /background: "rgba\(197,48,48,\.12\)", color: "var\(--bad-text\)"/.test(chip));
const busy = html.slice(html.indexOf("data-route-busy={r.id}"), html.indexOf("data-route-busy={r.id}") + 400);
ok("the busy-hours chip in the Routes list is one of them", /var\(--st-warn-bg\)/.test(busy));
const hold = html.slice(html.indexOf("<span data-route-holding={hr.state}"), html.indexOf("<span data-route-holding={hr.state}") + 600);
ok("the holding-area 'Route again' chip is one of them", /var\(--st-warn-bg\)/.test(hold));
const stuck = html.slice(html.indexOf("no way round yet. Until you find one") - 300, html.indexOf("no way round yet. Until you find one"));
ok("the 'no way round yet' box is one of them", /var\(--st-warn-bg\)/.test(stuck));

const warnInk = tok("warn-text", false), bgInk = tok("st-warn-bg", false);
const warnDk = tok("warn-text", true), bgDk = tok("st-warn-bg", true);
ok("ink: --warn-text on --st-warn-bg passes 4.5:1", warnInk && bgInk && ratio(warnInk, bgInk) >= 4.5, `${warnInk} on ${bgInk} ${warnInk && bgInk ? ratio(warnInk, bgInk).toFixed(2) : "?"}`);
ok("Dark: --warn-text on --st-warn-bg passes 4.5:1", warnDk && bgDk && ratio(warnDk, bgDk) >= 4.5, `${warnDk} on ${bgDk} ${warnDk && bgDk ? ratio(warnDk, bgDk).toFixed(2) : "?"}`);
ok("the old pair really failed (the audit's 4.25:1)", Math.abs(ratio("#B45309", "#F6EAE1") - 4.25) < 0.01);

console.log(`ui_fix_warn_chips.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
