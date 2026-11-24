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

// ---- 2 greys -------------------------------------------------------------------------------------------------------
const twAt = html.indexOf('<script src="/vendor/tailwind-play-3.4.17.js"></script>');
const cfgAt = html.indexOf("<script>tailwind.config={theme:{extend:{colors:{slate:{");
const slate = cfgAt > 0 ? Object.fromEntries([...html.slice(cfgAt, html.indexOf("</script>", cfgAt)).matchAll(/(\d+):"(#[0-9A-F]{6})"/g)].map(m => [m[1], m[2]])) : {};
ok("⭐ 2 greys: Tailwind's slate ramp is re-defined in ONE place, the page's Tailwind config, right after the play script loads",
   twAt > 0 && cfgAt > twAt && cfgAt - twAt < 700, `${twAt} ${cfgAt}`);
ok("2 greys: ...as the neutral ramp made from the ink (50 soft surface, 200 / 300 lines, 500 captions, 600 second text, 800 ink)",
   JSON.stringify(slate) === JSON.stringify({ 50: "#F5F5F6", 100: "#EDEEEF", 200: "#E1E2E4", 300: "#C6C8CC", 400: "#8A8D93", 500: "#62656B",
     600: "#44464B", 700: "#34363A", 800: "#1F2024", 900: "#141518", 950: "#0C0D0F" }), JSON.stringify(slate));
ok("🔴 2 greys: the light tokens are neutral (ink, captions, lines, the rail and soft surfaces; no warm paper)",
   tokenIn(rootBlock, "ink") === "#1F2024" && tokenIn(rootBlock, "muted") === "#62656B" && tokenIn(rootBlock, "line") === "#E1E2E4"
   && tokenIn(rootBlock, "grey") === "#C6C8CC" && tokenIn(rootBlock, "surface-2") === "#F5F5F6" && tokenIn(rootBlock, "surface-3") === "#EDEEEF"
   && tokenIn(rootBlock, "rail-bg") === "#F5F5F6");
ok("🔴 2 greys: Dark's greys are neutral too (captions #9C9FA4, lines #333539 / #4B4D52; the ink surfaces stay)",
   tokenIn(darkBlock, "muted") === "#9C9FA4" && tokenIn(darkBlock, "line") === "#333539" && tokenIn(darkBlock, "grey") === "#4B4D52"
   && tokenIn(darkBlock, "surface") === "#1F2024" && tokenIn(darkBlock, "bg") === "#141518"
   && css.includes('html[data-theme="dark"] .text-slate-400{color:#9C9FA4}') && css.includes('html[data-theme="dark"] .text-slate-600{color:#C9CACE}')
   && css.includes('html[data-theme="dark"] .border-slate-200{border-color:#333539}') && css.includes('html[data-theme="dark"] .border-slate-300{border-color:#4B4D52}'));
ok("2 greys: no map popup or label falls back to a system typeface (the Routes map's popups read the text face)",
   !/font:1[24]px system-ui/.test(html) && (html.match(/font:1[24]px var\(--f-text\)/g) || []).length === 3);

console.log(`own_look_tokens.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
