/*
 * own_look_tokens.js — 23 Nov 2026, branch claude/own-look-tokens (Group A of Wayscope's own look; John's yes to the
 * three own-look mockups, notes\design-language-1123.md). Its own file, so the branch adds nothing to a shared harness's
 * end blocks while claude/working-list is still open.
 *
 *   1  type        Sora for page headings, box titles and large figures; IBM Plex Sans for everything else; no Inter
 *   2  greys       neutral, made from the ink, in Ink / Light and in Dark (no slate, no blue-tinted grey)
 *   3  sign blue   #0B4EA2 (Dark #8AB4F8) for selected things and links; a selection is a tint or an underline
 *   4  the button  --action is the sign blue (Dark: the light sign blue, dark text); Confirm week stays green
 *   5  no picker   the accent picker is gone (CSS, ACCENTS, useAccent, the boot script, the guide, the audit's Blue pass)
 *   6  chart blue  the trial of --chart-2 as the sign blue (kept or put back by the palette check in parse_frontend)
 *   7  guards      ceilings that may only come down (GUARD_MAX below)
 *
 * Source checks on frontend/index.html (the `html` page; `code` the Babel script). Contrast pairs are measured in test_h1_uk.
 */
"use strict";
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const styleEnd = html.indexOf("</style>");
const css = html.slice(0, styleEnd);
const rootBlock = (() => { const a = css.indexOf("  :root{"); return css.slice(a, css.indexOf("\n  }", a)); })();
const darkBlock = (() => { const a = css.indexOf('  html[data-theme="dark"]{'); return css.slice(a, css.indexOf("\n  }", a)); })();
const tokenIn = (block, name) => { const m = block.match(new RegExp("--" + name + ":\\s*([^;]+);")); return m ? m[1].trim() : null; };

// ---- 1 type --------------------------------------------------------------------------------------------------------
const fontLinks = html.match(/<link href="https:\/\/fonts\.googleapis\.com\/css2\?[^"]+" rel="stylesheet">/g) || [];
ok("⭐ 1 type: ONE Google Fonts stylesheet, for Sora and IBM Plex Sans, and no Inter",
   fontLinks.length === 1 && fontLinks[0].includes("family=Sora:") && fontLinks[0].includes("family=IBM+Plex+Sans:")
   && !/family=Inter\b/.test(fontLinks[0]), fontLinks.join(" | "));
ok("1 type: the two faces are tokens on :root (--f-text IBM Plex Sans, --f-head Sora then IBM Plex Sans)",
   tokenIn(rootBlock, "f-text") === "'IBM Plex Sans',system-ui,sans-serif"
   && tokenIn(rootBlock, "f-head") === "Sora,'IBM Plex Sans',system-ui,sans-serif");
ok("🔴 1 type: the body reads the text face", /\n  body\{margin:0;font-family:var\(--f-text\);/.test(html));
ok("⭐ 1 type: page headings, box titles and large figures read Sora (h1 to h4, .ct-h, .kpi-num, the rate tiles, the clock)",
   /\n  h1,h2,h3,h4,\.ct-h,\.kpi-num,\.rc-tile b,\.sim-clock\{font-family:var\(--f-head\);\}/.test(html));
ok("1 type: the Look-ahead's figure tiles carry the figure class (Sora)",
   html.includes('<div className={"kpi-num font-semibold tabular-nums truncate leading-8 " + (len > 12'));
// no Inter anywhere on the app page: CSS font lists, canvas fonts, the picture of a chart
const interUses = html.match(/(^|[\s'",:(`])Inter(?=[\s'",;)`]|$)/gm) || [];
ok("🔴 1 type: the word Inter names no typeface on the app page (CSS, canvas, a chart's picture)", interUses.length === 0,
   String(interUses.length));
// every canvas font that names a typeface names IBM Plex Sans (the map signs' own system-ui glyphs aside: the map's own look)
const canvasFaces = (html.match(/\.font = [`"][^`"]*[`"]/g) || []).filter(f => /[a-z]-?serif|'/.test(f));
const notPlex = canvasFaces.filter(f => !f.includes("'IBM Plex Sans'") && !f.includes("${font}") && !/bold (\d+|\$\{[^}]+\})px system-ui, sans-serif/.test(f));
ok("1 type: every canvas text on a chart is IBM Plex Sans (the Routes map's sign glyphs keep their own face)",
   canvasFaces.length >= 10 && notPlex.length === 0, notPlex.join(" | "));
ok("1 type: Chart.js draws its own axes and keys in IBM Plex Sans (guarded: a stub Chart has no font object)",
   html.includes("if(window.Chart.defaults.font) window.Chart.defaults.font.family = \"'IBM Plex Sans', system-ui, sans-serif\";"));
ok("1 type: a chart's downloaded picture and the record's picture name IBM Plex Sans first",
   (html.match(/font = "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"/g) || []).length === 2);

console.log(`own_look_tokens.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
