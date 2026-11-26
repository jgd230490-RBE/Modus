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
// NARROWED 26 Nov 2026 (claude/own-look-shape, taking main bbf9c7e in): the own look's status has NO tint at all (design
// language: a shape and a word), so the five amber words are the status chip (RowStatus, rs-warn) or, for the "no way round
// yet" sentence, a status line with its diamond (.st-line.st-warn), each on the page's own surface. The tint's fault cannot
// occur; the word is measured against the surfaces it now sits on (white and the second surface in ink, the dark surfaces).
const solid = (html.match(/background: "var\(--st-warn-bg\)", color: "var\(--warn-text\)"/g) || []).length;
ok("🔴 the five amber words sit on the solid var(--st-warn-bg)  [NARROWED: on no background, the status shape and word]",
   solid === 0 && html.includes(".row-st.rs-warn{color:var(--warn-text);}") && html.includes(".st-line.st-warn{color:var(--warn-text);}"), String(solid));

const chip = html.slice(html.indexOf("<span data-route-diverted={r.id}"), html.indexOf("<span data-route-diverted={r.id}") + 500);
ok("the Routes list's 'Diverted …' chip is one of them", /<RowStatus word=\{`\$\{used\.length \? "Diverted" : "Not diverted"\}/.test(chip) && /tone=\{used\.length \? "warn" : "bad"\}/.test(chip), chip.slice(0, 120));
ok("...and its red 'Not diverted' side is unchanged (5.38:1 on white already)  [NARROWED: the red status, --bad-text through .row-st]",
   /tone=\{used\.length \? "warn" : "bad"\}/.test(chip) && html.includes(".row-st.rs-bad{color:var(--bad-text);}") && !/style=\{used\.length/.test(chip));
const busy = html.slice(html.indexOf("data-route-busy={r.id}"), html.indexOf("data-route-busy={r.id}") + 700);
ok("the busy-hours chip in the Routes list is one of them", /<RowStatus word=\{`Busy hours: Alt \$\{u\.alt\}`\} tone="warn" \/>/.test(busy));
const hold = html.slice(html.indexOf("if(hr.state === \"route_again\") return <span data-route-holding"), html.indexOf("if(hr.state === \"route_again\") return <span data-route-holding") + 400);
ok("the holding-area 'Route again' chip is one of them", /<RowStatus word=\{words\} tone="warn" \/>/.test(hold));
const stuck = html.slice(html.indexOf("no way round yet. Until you find one") - 300, html.indexOf("no way round yet. Until you find one"));
ok("the 'no way round yet' box is one of them", /className="mt-2 text-\[13px\] st-line st-warn"/.test(stuck) && !/background/.test(stuck));
const zones = html.slice(html.indexOf("data-busy-in-use={u.from}"), html.indexOf("data-busy-in-use={u.from}") + 700);
ok("the Zones busy-hours line is one of them (added 26 Nov)", /<RowStatus word=\{`Busy hours: Alt \$\{u\.alt\} · paused`\} tone="warn" \/>/.test(zones));

const warnInk = tok("warn-text", false), warnDk = tok("warn-text", true);
const surfInk = tok("surface", false), surf2Ink = tok("surface-2", false), surfDk = tok("surface", true), surf2Dk = tok("surface-2", true);
ok("ink: --warn-text on --st-warn-bg passes 4.5:1  [NARROWED: on --surface and --surface-2]",
   warnInk && surfInk && surf2Ink && ratio(warnInk, surfInk) >= 4.5 && ratio(warnInk, surf2Ink) >= 4.5,
   `${warnInk} on ${surfInk} ${warnInk && surfInk ? ratio(warnInk, surfInk).toFixed(2) : "?"}, on ${surf2Ink} ${warnInk && surf2Ink ? ratio(warnInk, surf2Ink).toFixed(2) : "?"}`);
ok("Dark: --warn-text on --st-warn-bg passes 4.5:1  [NARROWED: on the dark --surface and --surface-2]",
   warnDk && surfDk && surf2Dk && ratio(warnDk, surfDk) >= 4.5 && ratio(warnDk, surf2Dk) >= 4.5,
   `${warnDk} on ${surfDk} ${warnDk && surfDk ? ratio(warnDk, surfDk).toFixed(2) : "?"}, on ${surf2Dk} ${warnDk && surf2Dk ? ratio(warnDk, surf2Dk).toFixed(2) : "?"}`);
ok("the old pair really failed (the audit's 4.25:1)", Math.abs(ratio("#B45309", "#F6EAE1") - 4.25) < 0.01);

console.log(`ui_fix_warn_chips.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
