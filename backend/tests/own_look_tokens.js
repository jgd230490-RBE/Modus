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
const slate = cfgAt > 0 ? Object.fromEntries([...html.slice(cfgAt, html.indexOf("}", cfgAt + 50)).matchAll(/(\d+):"(#[0-9A-F]{6})"/g)].map(m => [m[1], m[2]])) : {};
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

// ---- 3 sign blue ---------------------------------------------------------------------------------------------------
const lightHdr = (() => { const a = css.indexOf('  html[data-theme="light"]{'); return css.slice(a, css.indexOf("\n  }", a)); })();
ok("⭐ 3 sign blue: --navy and --blue are #0B4EA2, --navy-soft its 10 % tint (a chosen thing), --navy-soft-col its 6 % tint (a table column)",
   tokenIn(rootBlock, "navy") === "#0B4EA2" && tokenIn(rootBlock, "blue") === "#0B4EA2"
   && tokenIn(rootBlock, "navy-soft") === "rgba(11,78,162,.10)" && tokenIn(rootBlock, "navy-soft-col") === "rgba(11,78,162,.06)");
ok("🔴 3 sign blue: Dark's is the light sign blue #8AB4F8 (16 % and 10 % tints) with dark text on a fill, never orange",
   tokenIn(darkBlock, "navy") === "#8AB4F8" && tokenIn(darkBlock, "blue") === "#8AB4F8" && tokenIn(darkBlock, "navy-soft") === "rgba(138,180,248,.16)"
   && tokenIn(darkBlock, "navy-soft-col") === "rgba(138,180,248,.10)" && tokenIn(darkBlock, "control-fg") === "#141518");
ok("3 sign blue: the white bar's chosen segment is a sign blue tint with sign blue words (was an orange tint)",
   tokenIn(lightHdr, "hdr-on") === "rgba(11,78,162,.10)" && css.includes('html[data-theme="light"] .hdr-seg button.is-on{color:var(--navy);}'));
ok("3 sign blue: the page's five blue utilities are the sign blue ramp, and Dark remaps them to the light sign blue (no orange)",
   // NARROWED 24 Nov 2026 (own look, B1 stage 1): the config now carries the one corner (borderRadius) after the colours
   html.includes('950:"#0C0D0F"},blue:{50:"#F0F4F9",200:"#C2D3E8",300:"#9DB8DA",700:"#0B4EA2",800:"#083A79"}},borderRadius:{sm:"3px",DEFAULT:"6px",md:"6px",lg:"6px",xl:"6px","2xl":"6px"}}}};</script>')
   && css.includes('html[data-theme="dark"] .bg-blue-50{background-color:rgba(138,180,248,.12)}') && css.includes('html[data-theme="dark"] .text-blue-700{color:#8AB4F8}')
   && css.includes('html[data-theme="dark"] .text-blue-800{color:#A9C8FA}') && css.includes('html[data-theme="dark"] .border-blue-300{border-color:rgba(138,180,248,.45)}'));
ok("⭐ 3 selection: the rail's chosen page, the wall bar's chosen button and the phone's chosen segment are the 10 % tint with sign blue words — none filled",
   css.includes(".rail-item.is-on{background:var(--navy-soft);color:var(--navy);font-weight:600;}")
   && css.includes(".dash-wallbar-btn.is-on{background:var(--navy-soft);color:var(--navy);}")
   && css.includes('.ph-seg button[aria-pressed="true"]{background:var(--navy-soft);color:var(--navy);}'));
ok("3 selection: the phone's chosen tab, its More item and its chosen day read the sign blue, not the action colour",
   css.includes(".phone-tab.is-on{color:var(--navy);") && /\.phone-tab\.is-on::before\{[^}]*background:var\(--navy\);\}/.test(css)
   && css.includes(".phone-more-item.is-on{color:var(--navy);") && css.includes('.ph-day[aria-pressed="true"]{border-color:var(--navy);')
   && !/\.(phone-tab\.is-on|phone-more-item\.is-on|ph-day\[aria-pressed="true"\]|ph-seg button\[aria-pressed="true"\])[^{]*\{[^}]*var\(--action\)/.test(css));
ok("3 selection: the look list's chosen row is a light sign blue tint and tick on the dark popover (was orange)",
   // NARROWED 24 Nov 2026 (stage 5): the accent items went with the picker's accent half
   css.includes(".appearance-item.is-on{background:rgba(138,180,248,.16);}") && css.includes(".appearance-item .tick{opacity:0;color:#8AB4F8;}"));
const placeOn = html.match(/style=\{(gatePlace|areaPlace|picking === c\.name) \? \{ background: "var\(--navy-soft\)", color: "var\(--navy\)" \} : undefined\}/g) || [];
ok("🔴 3 selection: the three 'Place on map' toggles and the drawing palette's picked tool are the tint and sign blue words; no text-white sits on a --navy or --blue fill but the Submit strip",
   placeOn.length === 3 && html.includes('style={on ? { background: "var(--navy-soft)", color: "var(--navy)" } : undefined} />;')
   && !/background: ?"var\(--blue\)"/.test(html)
   && (html.match(/background: ?"var\(--navy\)"/g) || []).length === 1 && html.includes('text-white kpi-num" style={{ background: "var(--navy)" }}>'));
ok("3 selection: a table column (today, the commit week) is the 6 % tint: eight column washes, none on the 10 % tint",
   (html.match(/var\(--navy-soft-col\)/g) || []).length === 8 && !/\{ background: "var\(--navy-soft\)" \}/.test(html));
ok("3 figures: the Cost groups and their planned and fair £, today's vehicles, the Submit page's loads and fair £ and the Today heading read the ink, not the sign blue",
   (html.match(/<Group title="Cost" tone="var\(--navy-deep\)">/g) || []).length === 2 && !/tone="var\(--navy\)"/.test(html.replace('<Bar pct={acctPct != null ? acctPct : 0} tone="var(--navy)" />', ""))
   && html.includes('fig-group" style={{ color: "var(--navy-deep)" }}>Today'));
ok("⭐ 3 links: the road closures line's link is the sign blue even when the line is an amber warning",
   html.includes('<button onClick={refreshTarkTee} className="font-semibold underline hover:no-underline" style={{ color: "var(--navy)" }}>'));
ok("3 controls: the supplies checkbox and the look swatches take the sign blue (no stock blue on a control)",
   html.includes('style={{ accentColor: "var(--navy)" }}') && !html.includes('accentColor: "#2563EB"')
   && html.includes('page: "#F5F5F6", dot: "#0B4EA2" }]') && html.includes('page: "#141518", dot: "#8AB4F8" }]'));

// ---- 4 the one primary button --------------------------------------------------------------------------------------
ok("⭐ 4 button: --action is the sign blue with white text; Dark's the light sign blue with dark text",
   tokenIn(rootBlock, "action") === "#0B4EA2" && tokenIn(rootBlock, "action-fg") === "#FFFFFF"
   && tokenIn(darkBlock, "action") === "#8AB4F8" && tokenIn(darkBlock, "action-fg") === "#141518");
ok("4 button: the filled button and an inline accent fill read the pair (.btn-pri, .text-white on var(--action))",
   /\.btn-pri\{[^}]*background:var\(--action\);color:var\(--action-fg\);/.test(css) && css.includes('.text-white[style*="var(--action)"]{color:var(--action-fg);}'));
ok("🔴 4 button: Confirm week stays green — its own pair, unchanged, on both buttons",
   tokenIn(rootBlock, "ok-btn") === "#047857" && tokenIn(rootBlock, "ok-btn-fg") === "#FFFFFF" && tokenIn(darkBlock, "ok-btn") === "#34D399"
   && (html.match(/style=\{\{ background: "var\(--ok-btn\)", color: "var\(--ok-btn-fg\)" \}\}/g) || []).length === 2);
// orange is the brand only: the logo (an image) and the 2 px rule under the header. Left as data, not controls: the chart
// palette's slot 1 (#E8590C / #E8681E), the lorry plan's blocks (.pb-dis, lpPalette) and the accent list (stage 5 removes it)
const accentsCut = css.indexOf("ACCENTS-START") > 0 ? css.slice(0, css.indexOf("ACCENTS-START")) + css.slice(css.indexOf("ACCENTS-END")) : css;
const orangeCss = (accentsCut.replace(/\/\*[\s\S]*?\*\//g, "").match(/#(C2410C|FF8C14|FFA10A|EA580C|F97316)\b|rgba\((194, ?65, ?12|255, ?140, ?20)/gi) || []);
ok("⭐ 4 orange is the brand only: no burnt or brand orange on any control, tint or focus in the stylesheet (the brand tokens and the lorry plan's data block aside)",
   orangeCss.map(c => c.toUpperCase()).sort().join(" ") === "#C2410C #FF8C14 #FFA10A" && (accentsCut.match(/\.pb-dis\{background:#C2410C;\}/g) || []).length === 1
   && tokenIn(rootBlock, "brand-orange") === "#FF8C14" && tokenIn(rootBlock, "brand-orange-to") === "#FFA10A", orangeCss.join(" "));
ok("4 orange is the brand only: --brand-orange paints the header's 2 px rule and nothing else",
   (html.match(/var\(--brand-orange\)/g) || []).length === 1 && css.includes(".brand-bar{background:var(--hdr-bg);color:var(--hdr-fg);border-bottom:2px solid var(--brand-orange);}"));
ok("4 the guide's dot is the sign blue (was the burnt orange), its pulse from the same token",
   /\.guide-dot\{[^}]*background:var\(--navy\);/.test(css) && css.includes("@keyframes guide-pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--navy) 45%,transparent)}"));

ok("4 button: the supplier orders menu's 'All suppliers' zip is an action, so it reads the button pair (was a --navy fill)",
   css.includes(".row-menu-list button.so-all{margin-top:6px;text-align:center;background:var(--action);color:var(--action-fg);font-weight:600;}")
   && !/so-all\{[^}]*var\(--navy\)/.test(css));

// ---- 5 no accent picker -------------------------------------------------------------------------------------------
const script = html.slice(html.indexOf('<script type="text/babel"'));
ok("⭐ 5 no picker: no ACCENTS block, no [data-accent] selector, no accent item in the stylesheet",
   !css.includes("ACCENTS-START") && !css.includes("ACCENTS-END") && !css.includes("[data-accent") && !css.includes("accent-item") && !css.includes("accent-sw"));
ok("🔴 5 no picker: no ACCENTS, ACCENT, applyAccent, useAccent or setAccent in the app, and no chart listens to an accent",
   !/ACCENTS?/.test(script) && !/applyAccent|useAccent|setAccent/.test(script) && !/accent, sized\]/.test(script) && !script.includes("<h6>Accent</h6>"));
ok("🔴 5 no picker: nothing sets or reads data-accent or the stored modus_accent (the <head> script sets the look only)",
   !html.includes("data-accent") && !html.includes("modus_accent") && /d\.setAttribute\("data-theme",/.test(html));
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8");
ok("5 no picker: the guide's Appearance passage names the three looks and no accent",
   guide.includes("picks the look: <strong>Ink</strong> (the default), <strong>Light</strong> or <strong>Dark</strong>. On a chart the first series is the plan")
   && !/under it the accent|Orange shades|Blue shades|In every accent/.test(guide));
const audit = fs.readFileSync(path.join(__dirname, "ui_audit.js"), "utf8");
ok("5 no picker: the UI audit has no Blue pass, no extra accents and no --accents, and sets no stored accent",
   !/EXTRA_ACCENTS|EXTRA_PASSES|--accents|modus_accent|accent: "blue"|accent: "orange"/.test(audit));
ok("5 the last stock-ish blue checkboxes (#1D4ED8) take the sign blue",
   !html.includes('accentColor: "#1D4ED8"') && (html.match(/accentColor: "var\(--navy\)"/g) || []).length >= 6);

// ---- 6 the chart-blue trial: delivered (series 2) is the sign blue, kept because the palette check passes ---------
// 24 Nov 2026, the palette check's own maths (parse_frontend W16): light worst colour-blind 21.0 (was 20.7), everyone
// 22.5 (22.6), lowest series contrast 3.58, series 2 8.00:1 (5.17); Dark worst 15.2 (14.7), 18.5 (17.2), 4.59, 7.72.
ok("⭐ 6 chart blue: --chart-2 is the sign blue in light (#0B4EA2) and Dark (#8AB4F8); the 'delivered' fallbacks follow",
   tokenIn(rootBlock, "chart-2") === "#0B4EA2" && /html\[data-theme="dark"\]\{[^}]*--chart-2:#8AB4F8;/.test(css)
   && !/tok\("--chart-2", "#2563EB"\)/.test(html) && (html.match(/tok\("--chart-2", "#0B4EA2"\)/g) || []).length === 2);

// ---- 7 guards: CEILINGS that may only come down (as ui_audit_rules' PINNED_MAX) -----------------------------------
// A ceiling is lowered when the thing it counts goes; it is never raised. Each count was 0 or the figure below on
// 24 Nov 2026 (the branch's stage 7); the same counters on main 388d2b2 read: Inter 2, stock blue 20, data-accent 22,
// an orange --action 3, filled selections 3 (the phone segment, the wall bar's chosen button, PalBtn): each fails there.
const CEIL = {
  INTER: 0,           // "Inter" as a font name on the app page
  STOCK_BLUE: 7,      // literal #2563EB / #3B82F6 outside the chart tokens: all data colours on a map or a plan block
                      //   (--sim-lorry, .pb-there, two sim fallbacks, ROUTE_COLOR, NODE_COLORS' Port, one place stroke)
  DATA_ACCENT: 0,     // data-accent anywhere on the page
  ACTION_ORANGE: 0,   // a --action defined as an orange anywhere (a token block or an inline style)
  FILLED_SELECTION: 0 // a selected / pressed / current thing drawn as a solid blue fill
};
const noComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const htmlNC = noComments(html);
const interN = (htmlNC.match(/font-family:[^;}"]*\bInter\b|family=Inter\b|["']Inter["']/g) || []).length;
ok("⭐ 7 ceiling: no Inter on the app page (font-family, a Google Fonts family or a quoted name)", interN <= CEIL.INTER, "found " + interN);
const tokenBlocks = [rootBlock, ...[...css.matchAll(/html\[data-theme="(?:dark|light)"\]\{[^}]*\}/g)].map(m => m[0])];
let chartTokenBlues = 0; for (const b of tokenBlocks) chartTokenBlues += (b.match(/--chart-[0-9a-z-]+:\s*#(?:2563EB|3B82F6)/gi) || []).length;
const stockN = (htmlNC.match(/#(?:2563EB|3B82F6)\b/gi) || []).length - chartTokenBlues;
ok("⭐ 7 ceiling: literal #2563EB / #3B82F6 outside the chart tokens may only fall (" + CEIL.STOCK_BLUE + ", all map / plan data colours)",
   stockN <= CEIL.STOCK_BLUE, "found " + stockN);
const accN = (html.match(/data-accent/g) || []).length;
ok("🔴 7 ceiling: no data-accent anywhere on the page", accN <= CEIL.DATA_ACCENT, "found " + accN);
const isOrange = (hex) => { const h = hex.replace("#", ""); if (!/^[0-9a-f]{6}$/i.test(h)) return false;
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); return r > 150 && r > g && g > b && r - b > 90 && g > 40; };
const actionDefs = [...htmlNC.matchAll(/["']?--action["']?\s*:\s*["']?(#[0-9a-fA-F]{6}|var\(--[a-z0-9-]+\))/g)].map(m => m[1]);
const resolve = (v) => { const t = v.match(/^var\(--([a-z0-9-]+)\)$/); return t ? (tokenIn(rootBlock, t[1]) || v) : v; };
const orangeActions = actionDefs.map(resolve).filter(isOrange);
ok("🔴 7 ceiling: no --action resolves to an orange (every definition, token blocks and inline styles)",
   actionDefs.length >= 2 && orangeActions.length <= CEIL.ACTION_ORANGE && isOrange("#C2410C") && isOrange("#FF8C14") && !isOrange("#0B4EA2") && !isOrange("#8AB4F8"),
   "defs " + actionDefs.join(" ") + " · orange " + orangeActions.join(" "));
const FILL = /background(?:-color)?:\s*(var\(--(?:navy|action|blue)\)|#0B4EA2|#8AB4F8|#2563EB|#3B82F6|#5B8FF0|#1D4ED8)\s*[;}]/i;
const SELECTED = /\.is-on|\[aria-pressed="true"\]|\[aria-selected="true"\]|\[aria-current|\.active\b|:checked|\.on\b|\.sel\b|\.picked/;
const fills = [];
css.replace(/([^{}]+)\{([^{}]*)\}/g, (m, sel, body) => {   // a 1–4 px ::before / ::after bar is a marker, not a fill
  if (SELECTED.test(sel) && FILL.test(body) && !(/::(before|after)/.test(sel) && /height:\s*[1-4]px/.test(body))) fills.push(sel.trim().slice(-60)); return m; });
const BLUE_V = '(?:var\\(--(?:navy|action|blue)\\)|#0B4EA2|#8AB4F8|#2563EB|#3B82F6|#1D4ED8)';
for (const re of [new RegExp('\\b(?:on|active|sel|selected|picked|isOn|chosen|cur|current|is[A-Z]\\w*)\\b[^?\\n]{0,40}\\?\\s*\\{?\\s*(?:background|backgroundColor):\\s*"' + BLUE_V + '"', "g"),
                  new RegExp('(?:background|backgroundColor):\\s*[\\w.!=<>"\' ]{1,60}\\?\\s*"' + BLUE_V + '"', "g"),
                  /\?\s*"[^"]*\bbg-(?:blue-(?:600|700|800)|\[var\(--navy\)\])[^"]*"/g])
  for (const m of script.matchAll(re)) fills.push(m[0].slice(0, 60));
ok("⭐ 7 ceiling: no selection is a solid blue fill (CSS for a chosen / pressed / current thing; a ternary on a chosen flag)",
   fills.length <= CEIL.FILLED_SELECTION, JSON.stringify(fills));
ok("7 the ceilings only come down: every one is at or under its figure of 24 Nov 2026",
   CEIL.INTER <= 0 && CEIL.STOCK_BLUE <= 7 && CEIL.DATA_ACCENT <= 0 && CEIL.ACTION_ORANGE <= 0 && CEIL.FILLED_SELECTION <= 0);

console.log(`own_look_tokens.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
