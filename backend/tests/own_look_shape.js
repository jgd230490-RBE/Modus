// own_look_shape.js — the app's SHAPE in Wayscope's own look (claude/own-look-shape, Group B1, 24 Nov 2026).
// John's yes to the second and third own-look mockups (23 Nov 2026; notes own-look-build-1123 README "B1"): one corner (6 px,
// 3 px for a small inner piece), status as a shape and a word, tags as plain words, figures as a ruled strip, sections ruled
// not boxed, the place line in sentence case, small bars in ink, a chosen tab or day an underline only. Source-level checks
// on frontend/index.html; the CEILINGS at the end may only come down (PINNED_MAX style).
"use strict";
const fs = require("fs"), path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "..", "frontend", "index.html"), "utf8").replace(/\r\n/g, "\n");
const css = html.slice(html.indexOf("<style>"), html.indexOf("</style>"));
const code = html.slice(html.indexOf("</style>"));
let pass = 0; const fail = [];
const ok = (name, cond, more) => { if (cond) pass++; else fail.push(name + (more !== undefined ? "  " + JSON.stringify(more) : "")); };
const count = (s, re) => (s.match(re) || []).length;

// ---------------------------------------------------------------- stage 1: one corner
ok("1 corner: the Tailwind config maps every rounded-* utility to the one 6 px corner and rounded-sm to the small 3 px",
   html.includes('borderRadius:{sm:"3px",DEFAULT:"6px",md:"6px",lg:"6px",xl:"6px","2xl":"6px"}'));
ok("1 corner: no rounded-full is left on the page (the pills took the one corner)", !/\brounded-full\b/.test(html));
const radii = [...new Set((css.match(/border-radius:[^;}"]*/g) || []).map(r => r.slice(14).trim()))].sort();
const allowed = ["6px", "3px", "0", "50%", "9px", "6px 6px 0 0", "0 0 6px 6px", "0 0 3px 3px"];
ok("1 corner: the stylesheet's corners are 6 px, the small 3 px, none, a round dot (50 %) and the count dot's 9 px only",
   radii.every(r => allowed.includes(r)), radii);
ok("1 corner: no 999px corner is left in the stylesheet (the count dots are 9 px on an 18 px box)", !/border-radius:999px/.test(css));
ok("1 corner: the demo bar's Guide button takes the 6 px corner (third mockup Q4), its colours unchanged",
   /\.demo-bar-guide\{[^}]*border-radius:6px;background:var\(--demo-btn-bg\);box-shadow:inset 0 0 0 1px var\(--demo-btn-ring\)/.test(css));
ok("1 corner: the count dots stay round (.rail-dot and the phone tab's count, 9 px on 18 px)",
   /\.rail-dot\{[^}]*height:18px;[^}]*border-radius:9px;/.test(css) && /\.phone-tab \.rail-count\{[^}]*border-radius:9px;/.test(css));
ok("1 corner: the info button stays a ring (50 %), no 999px", /\.ibtn\{[^}]*border-radius:50%;/.test(css));
const jsxR = [...new Set((code.match(/borderRadius: \d+/g) || []))].sort();
ok("1 corner: inline corners in the script are the small 3 px, the one 6 px or a legend dot (999 on a 10 px dot)",
   jsxR.every(r => ["borderRadius: 3", "borderRadius: 6", "borderRadius: 999"].includes(r)), jsxR);

// ---------------------------------------------------------------- stage 2: status = a shape and a word, no tint
ok("2 status: RowStatus draws an empty <i> (the shape, in CSS) and the word — no glyph, no RS_ICON",
   code.includes('<i aria-hidden="true"></i>{word}') && !code.includes("RS_ICON") && !/RS_[A-Z]+ = \{[^}]*"✓"/.test(code));
ok("2 status: dot = ok, diamond = warning, square = bad, ring = none (and draft), 10 px, the ring a 2 px stroke",
   /\.row-st i\{[^}]*width:10px;height:10px;border-radius:50%;background:transparent;border:2px solid var\(--st-none\);\}/.test(css)
   && /\.row-st\.rs-ok i\{background:var\(--green\);border:0;\}/.test(css)
   && /\.row-st\.rs-warn i\{background:var\(--gold\);border:0;border-radius:0;width:9px;height:9px;margin:0 1px;transform:rotate\(45deg\);\}/.test(css)
   && /\.row-st\.rs-bad i\{background:var\(--red\);border:0;border-radius:0;\}/.test(css)
   && /\.row-st\.rs-draft i\{background:transparent;border:2px solid var\(--st-none\);\}/.test(css));
ok("2 status: the chip has no tint, no padding, no corner; the --st-*-bg tints are gone (nothing reads them)",
   !/\.row-st(\.rs-\w+)?\{[^}]*(background|padding|border-radius)/.test(css) && !/--st-(ok|warn|bad|none)-bg/.test(html));
ok("2 status: the second-text token for the ring and the none word, light #44464B and Dark #C9CACE",
   /--st-none:#44464B;/.test(css) && /--st-none:#C9CACE;/.test(css));
ok("2 status: the Look-ahead flag chips (.chip-st) take the same four shapes, 10 px (warning a diamond, bad a square)",
   /\.chip-st i\{width:10px;height:10px;border-radius:50%;/.test(css) && /\.chip-st i\[style\*="--gold"\]\{[^}]*transform:rotate\(45deg\);\}/.test(css)
   && /\.chip-st i\[style\*="--red"\]\{border-radius:0;\}/.test(css) && !/clip-path:polygon/.test(css.slice(css.indexOf(".chip-st"), css.indexOf(".chip-st") + 1200)));

console.log(`own_look_shape.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
