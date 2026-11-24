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
const allowed = ["6px", "3px", "0", "0 !important", "50%", "9px", "6px 6px 0 0", "0 0 6px 6px", "0 0 3px 3px"];
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

// ---------------------------------------------------------------- stage 3: tags as plain words joined by "·"
ok("3 tags: .tg undoes a chip's tint, border, padding and corner (beats the old inline tints); tags side by side are joined by a middle dot",
   css.includes(".tg{background:none !important;border:0 !important;padding:0 !important;border-radius:0 !important;box-shadow:none !important;}")
   && css.includes('.tg:has(+ .tg)::after{content:"\\00B7";'));
ok("3 tags: a team, a workstream and a material are plain words in the second-text grey, with no colour of their own",
   code.includes('<span className="tg tg-plain text-xs font-semibold">{teamName(k)}</span>') && code.includes('<span className="tg tg-plain text-xs font-semibold">{ws}</span>')
   && code.includes('<span key={c} className="tg tg-plain text-xs whitespace-nowrap">{c}</span>') && css.includes(".tg-plain{color:var(--st-none) !important;}")
   && !code.includes("IPT_PALETTE_C[k] || \"#62656B\" }}>{teamName(k)}"));
ok("3 tags: a tag in the warning or bad words carries the status shape (diamond / square), so it is never colour alone; 'Avoided' (a kind) does not",
   /\.tg:not\(\.tg-ns\)\[style\*="--warn-text"\]::before,\.tg:not\(\.tg-ns\)\[style\*="--bad-text"\]::before\{content:"";display:inline-block;width:9px;height:9px;/.test(css)
   && css.includes('.tg:not(.tg-ns)[style*="--warn-text"]::before{transform:rotate(45deg);}') && code.includes('className="tg tg-ns text-xs font-semibold px-2 py-0.5 rounded" style={{ color: "var(--bad-text)" }}>Avoided'));
ok("3 tags: every former pill span carries .tg (24), none is left without it; the two controls with a chip's classes (a season month, a button) do not",
   count(code, /className=\{?"tg /g) === 24 && !/<span[^>]*className=\{?"(?!tg )[^"]*\bpx-1\.5 (py-0\.5 )?rounded\b/.test(code)
   && /<label key=\{m\} className=\{"text-xs px-1\.5 py-0\.5 rounded border cursor-pointer/.test(code));
ok("3 tags: the CSS pills are plain words: abnormal-load categories, the row details' chips (joined by a dot), the CLP organisation, the lorry plan's badge, the Simulation's chips, the record's end word",
   /\.al-chip\{display:inline-block;font-size:12px;font-weight:600;white-space:nowrap;margin-right:8px;\}/.test(css) && !/\.al-(so|vr1|stgo|cu|warn|bad|grey|okc)\{[^}]*background/.test(css)
   && !/\.(rd-chip|clp-org|lp-badge|sim-chip|rc-end)\{[^}]*(background|border-radius|padding)/.test(css) && css.includes('.rd-chips .rd-chip+.rd-chip::before{content:"\\00B7";')
   && !/html\[data-theme="dark"\] \.al-\w+\{background/.test(css));
// ---------------------------------------------------------------- stage 4: figures as one ruled strip
ok("4 figures: .fig-strip is the one ruled strip (2 px ink on top, a hairline under, no gap, no box); its cells lose their box and take hairlines",
   css.includes(".fig-strip{display:grid;gap:0 !important;border-top:2px solid var(--ink);border-bottom:1px solid var(--line);overflow:hidden;background:none;}")
   && css.includes(".fig-strip>*{border:0 !important;border-radius:0 !important;background:none !important;box-shadow:inset 1px 0 0 var(--line),inset 0 1px 0 var(--line) !important;margin:-1px 0 0 -1px;min-width:0;}"));
ok("4 figures: the Look-ahead's tiles and the Submit page's six figures are .fig-strip rows; the tiles carry no .card, the Submit strip no fill",
   code.includes('<div className="fig-strip grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-3" data-fig-strip="lookahead">')
   && code.includes('<div className="px-4 py-3 min-w-0" data-la-kpi="1"') && !code.includes('<div className="card px-4 py-3 min-w-0"')
   && code.includes('<div className="fig-strip grid grid-cols-2 md:grid-cols-6 kpi-num" data-fig-strip="submit">') && !code.includes("divide-x divide-slate-200 text-white kpi-num"));
const ruled = sel => new RegExp("\\n  \\." + sel + "\\{[^}]*border-top:2px solid var\\(--ink\\);").test(css);
ok("4 figures: every other row of figures is ruled under the ink line (Dashboard, Routes tiles, lorry plan, abnormal loads, pours, the phone's day)",
   ["dash-cards", "rc-tiles", "lp-kpis", "al-stats", "pour-figs", "ph-figs"].every(ruled), ["dash-cards", "rc-tiles", "lp-kpis", "al-stats", "pour-figs", "ph-figs"].filter(x => !ruled(x)));
ok("4 figures: no figure cell keeps a box (border + corner) of its own",
   !/\n  \.(lp-kpi|al-stat|pour-figs div|dash-cards \.dash-card)\{[^}]*border:1px solid/.test(css) && !/\n  \.(lp-kpi|al-stat|pour-figs div)\{[^}]*border-radius:6px/.test(css));
ok("4 figures: the phone's day summary is four cells, the Dashboard's labels keep two lines so the figures line up",
   /\n  \.ph-figs\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\);/.test(css) && /\.ph-figs>span\{display:block;/.test(css)
   && /\n  \.dash-card-l\{[^}]*min-height:2\.6em;/.test(css));
// ---------------------------------------------------------------- stage 5: sections ruled, not boxed
ok("5 sections: a .card is a 1 px ink line and its content, no border, corner, fill or side padding",
   css.includes(".card{background:none;border:0;border-top:1px solid var(--ink);border-radius:0;padding-left:0 !important;padding-right:0 !important;}"));
ok("5 sections: a sideways-scrolling table in a section keeps an edge (a hairline under it); a table's outer cells sit flush with the rule",
   css.includes(".card.overflow-auto,.card.overflow-x-auto{border-bottom:1px solid var(--line);}")
   && css.includes(".card .tbl th:first-child,.card .tbl td:first-child{padding-left:0;}"));
const boxed = ["dash-more", "rc-pcard", "ct-strip", "sim-fold", "sim-card", "sim-tl", "sim-scroll", "sim-pcard", "gw-gate", "al-strip", "dash-wallbar", "bo-card"]
  .filter(c => !new RegExp("\\n  \\." + c + "\\{[^}]*border:0;[^}]*border-top:(1|2)px solid var\\(--(ink|line)[^}]*border-radius:0;").test(css));
ok("5 sections: the app's own boxes are ruled (folds, the strips, the simulation's cards, gates, the big-screen bar, the Best option card)", boxed.length === 0, boxed);
ok("5 sections: the Best option card opens under a 2 px ink line and its notes are margin lines; the abnormal-load advice and the read-only note too",
   /\n  \.bo-card\{[^}]*border-top:2px solid var\(--ink\);/.test(css) && /\n  \.bo-state\{background:none;border:0;border-left:2px solid var\(--line-2\);/.test(css)
   && /\n  \.al-advice\{background:none;border:0;border-left:2px solid var\(--line-2\);/.test(css) && /\n  \.cfg-ro-note\{border:0;border-left:2px solid var\(--line-2\);/.test(css)
   && /--line-2:#C6C8CC;/.test(css) && /--line-2:#4B4D52;/.test(css));
ok("5 sections: no rounded bordered section box is left in the markup (bg-white rounded-xl border), the dialog's own box aside; the Tailwind sections are .ruled",
   !/rounded-xl border/.test(code) && count(code, /className=\{?"ruled /g) >= 5 && css.includes(".ruled{background:none !important;border:0 !important;border-top:1px solid var(--ink) !important;"));
ok("5 sections: Routes' open route is columns divided by a hairline", css.includes(".ro-body.ro-wide>.ro-side{border-left:1px solid var(--line);padding-left:16px;}"));
// ---------------------------------------------------------------- stage 6: the place line
ok("6 place: the place line is the mark (/brand/mark.svg, 12 px, hidden from readers) and the place, in the text face and the caption grey",
   code.includes('<img className="kicker-mark" src="/brand/mark.svg" alt="" aria-hidden="true" />{placeWords(kicker)}')
   && css.includes(".kicker{display:flex;align-items:center;gap:7px;font:400 12px/1.4 var(--f-text);color:var(--muted);margin-bottom:4px;}")
   && css.includes(".kicker-mark{height:12px;width:auto;flex:none;}"));
ok("6 place: sentence case a part, the words unchanged: placeWords capitalises each part's first letter and nothing else",
   (() => { const m = code.match(/function placeWords\(k\)\{[^\n]*\}/); if (!m) return false; const placeWords = new Function("return " + m[0])();
     return placeWords("Track · commit week") === "Track · Commit week" && placeWords("May 2026 – May 2027 · approved") === "May 2026 – May 2027 · Approved"
       && placeWords("Plan") === "Plan" && placeWords(undefined) === undefined; })());
ok("6 place: no capitals, monospace or letter-spacing on the place line", !/\.kicker\{[^}]*(monospace|uppercase|letter-spacing)/.test(css));
// ---------------------------------------------------------------- stage 7: small bars beside a status are ink
ok("7 bars: the Dashboard's week bars and the gates' peak bars (and their key) are ink in every state; no amber or red bar fill",
   code.includes('background: "var(--ink)" }} /></div>') && !code.includes('tone || "var(--green)"') && !/<Bar [^>]*tone=/.test(code)
   && css.includes(".ga-pbar i{display:block;height:100%;border-radius:3px;background:var(--ink);}") && !/\.ga-li-(warn|bad) \.ga-pbar i\{/.test(css)
   && css.includes(".ga-key-bar{width:16px;height:10px;border-radius:3px;background:var(--ink);}"));
// ---------------------------------------------------------------- stage 8: a chosen tab or day is an underline only
ok("8 select: a chosen tab is sign blue words on a 2 px sign blue underline, no tint or outline; a chosen day the same with 3 px",
   css.includes('.ws-tab[aria-selected="true"],.ws-tab[aria-current="page"],.ws-tab[aria-pressed="true"],.ws-on{background:var(--surface);color:var(--navy);border-color:var(--line-2);box-shadow:inset 0 -2px 0 var(--navy);}')
   && css.includes('.ph-day[aria-pressed="true"]{border-color:var(--line-2);box-shadow:inset 0 -3px 0 var(--navy);color:var(--navy);}')
   && !/\.ws-tab\[aria-selected="true"\][^{]*\{[^}]*navy-soft/.test(css));
ok("8 warning: a warning sentence carries the diamond (every amber block sentence and the road-closures line when not checked)",
   css.includes('p.text-amber-700::before,.warn-line>span:first-child::before{content:"";display:inline-block;width:9px;height:9px;margin:0 8px 1px 1px;background:var(--gold);transform:rotate(45deg);')
   && code.includes('"text-amber-700 warn-line")}>'));
ok("3 tags: no NUL byte or other control character crept into the page", !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(html));

console.log(`own_look_shape.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }
