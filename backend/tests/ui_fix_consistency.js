/*
 * ui_fix_consistency.js — the 9 Nov 2026 UI critique, wave 2, branch claude/ui-fix-consistency (the pieces every screen shares).
 *
 *   Finding 12 / card 12: ONE status chip (RowStatus; StatusWord draws it too): a tinted pill, one shape and one colour a
 *     tone, the words in sentence case; the pour flags in words a site manager reads ("Mixers in a no-delivery time").
 *   Finding 13 / card 13, decision 4: every primary action takes the accent (--action); blue (--navy) only for what is
 *     selected, drawn as a tint; ONE tab (.ws-tab) on Users, Config, Stockpiles, the Look-ahead and the CLP notes.
 *   Finding 14 / card 14: the staff maps follow the Dark look — the Route map (the embedded public map page) reads the app's
 *     look and opens on Dark; the data pages' map follows a change of look; a basemap picked by hand is kept.
 *   Finding 20, decision 5 (mockup notes\ui-fix-consistency-mockup-1110\): one distance unit per organisation, set on Config
 *     → Planning; the per-distance Config fields typed in it; a comma for thousands; "£57,833"; "£1.986 per litre";
 *     "May 2026" ("May '26" on chart axes only); Config's last saved in UK time, no "by —".
 *
 * Its own file (the wave rule, notes\ui-critique-1109.md §H): nothing appended to dom_frontend.js / parse_frontend.js /
 * parse_map.js. Source checks plus the small formatters run for real (transpiled out of the page). Needs typescript through
 * NODE_PATH; without it it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts;
try { ts = require("typescript"); } catch (e) { console.log("ui_fix_consistency.js: SKIPPED — typescript not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const map = read("map", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const css = html.slice(0, html.indexOf("</style>"));
const tokens = (block) => { const o = {}; for (const m of block.matchAll(/--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})/g)) o[m[1]] = m[2]; return o; };
const rootBlock = css.slice(css.indexOf(":root{"), css.indexOf("html[data-theme=\"light\"]{"));
const darkBlock = css.slice(css.indexOf("html[data-theme=\"dark\"]{"), css.indexOf("/* ACCENTS-START"));
const ROOT_T = tokens(rootBlock), DARK_T = tokens(darkBlock);
const lum = (hex) => { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

// ---------------------------------------------------------------- finding 12: the one status chip
ok("⭐ 12: the status chip is a pill — rounded, padded, tinted per tone, the word in the tone's text colour",
   /\.row-st\{[^}]*border-radius:999px;padding:2px 10px 2px 3px;background:var\(--st-none-bg\);\}/.test(css)
   && css.includes(".row-st.rs-ok{background:var(--st-ok-bg);color:var(--ok-text);}")
   && css.includes(".row-st.rs-warn{background:var(--st-warn-bg);color:var(--warn-text);}")
   && css.includes(".row-st.rs-bad{background:var(--st-bad-bg);color:var(--bad-text);}"));
ok("...each tone keeps its own icon SHAPE (✓ circle, ! square, ! circle, hollow ring), so a status is never colour alone (D39)",
   code.includes('const RS_ICON = { ok: "✓", warn: "!", bad: "!", none: "–", draft: "" };')
   && css.includes(".row-st.rs-warn i{background:var(--gold);color:#1F2024;border-radius:3px;}") && css.includes(".row-st.rs-draft i{background:transparent;"));
const tints = [["ok-text", "st-ok-bg"], ["warn-text", "st-warn-bg"], ["bad-text", "st-bad-bg"], ["ink", "st-none-bg"]];
const lows = [];
for (const [T, look] of [[ROOT_T, "ink"], [Object.assign({}, ROOT_T, DARK_T), "dark"]]) {
  for (const [fg, bg] of tints) { const r = cr(T[fg], T[bg]); if (!(r >= 4.5)) lows.push(`${look} ${fg} on ${bg} ${r.toFixed(2)}`); }
}
ok("...the chip's words read 4.5:1 or better on their tint in the light looks and in Dark (four tones × two)", lows.length === 0 && Object.keys(DARK_T).includes("st-ok-bg"), lows.join("; "));
ok("...StatusWord (Forecasts' and Users' status, Config's changed / unsaved) draws the SAME chip, not the old dot",
   code.includes("function StatusWord({ status, label }){\n  return <RowStatus word={label || status} tone={STATUS_TONE[status] || \"none\"} />;")
   && !/className="chip-st"/.test(code));
ok("...an abnormal load's flags, the Abnormal loads summary and the Look-ahead's flag strip use the chip too",
   code.includes('<span className="al-flag" title={f.text}><RowStatus word={AL_FLAG_WORD[f.code] || f.code} tone={AL_FLAG_TONE[f.code] || "warn"} /></span>')
   && code.includes('<RowStatus word="Notice late" tone="bad" />') && code.includes('<RowStatus word="AIL road limit" tone="bad" />')
   && code.includes('<span key={i} className="la-flag-line"><RowStatus word={flagWord(f)} tone={laTone(f.code)} />')
   && !code.includes("NOTICE LATE</AlChip>"));
const caps = [];
for (const name of ["RAIL_LABEL", "LINE_FLAG_LABEL", "POUR_WORD", "AL_FLAG_WORD"]) {
  const m = code.match(new RegExp("const " + name + " = \\{[\\s\\S]*?\\};"));
  if (!m) { caps.push(name + " missing"); continue; }
  for (const v of m[0].matchAll(/:\s*"([^"]+)"/g)) if (/^[A-Z][A-Z ≠]+$/.test(v[1]) && v[1].length > 3) caps.push(name + ": " + v[1]);
}
ok("⭐ 12: no flag word in capitals (SHORT, IN A BAND, ROAD LIMIT …): every flag table is in sentence case", caps.length === 0, caps.join(", "));
ok("...the pours read as a site manager would: Mixers in a no-delivery time, Too few mixers, Cold joint likely, Too long in transit, Over the month's plan",
   code.includes('POUR_BAND: "Mixers in a no-delivery time"') && code.includes('POUR_SHORT: "Too few mixers"')
   && code.includes('POUR_COLD_JOINT: "Cold joint likely"') && code.includes('POUR_TRANSIT: "Too long in transit"') && code.includes(`POUR_OVER_PLAN: "Over the month's plan"`));
const pw = read("backend", "pours.py");
ok("...and the server's pour words (pours.WORDS) say the same", pw.includes('"POUR_BAND": "Mixers in a no-delivery time"') && pw.includes('"POUR_SHORT": "Too few mixers"') && !/WORDS = \{[^}]*"IN A BAND"/.test(pw));
ok("...the Look-ahead's Short keeps its WHEN (finding 5 is wave 3's): SHORTAGE still ranks 2 and is still red", code.includes("LA_FLAG_RANK = { LIMIT: 0, RESTRICTION: 1, SHORTAGE: 2,") && code.includes('SHORTAGE: "Short"'));
ok("...a provider's own restriction word in capitals reads in sentence case (ROADWORKS → Roadworks)", code.includes("? capsWord(f.label) :"));

// ---------------------------------------------------------------- finding 13: one primary colour, one tab
ok("⭐ 13: an inline accent fill keeps text-white and reads --action-fg (dark on Dark's orange)", css.includes('.text-white[style*="var(--action)"]{color:var(--action-fg);}'));
ok("...Submit's Save & send, Locations / Zones / Routes' Save and Create, the layout card's actions take the accent",
   /style=\{\{background: "var\(--action\)"\}\}>\s*\{busy \? "Saving…" : "Save & send for approval"\}/.test(code)
   && /style=\{\{ background: "var\(--action\)" \}\}>\s*\{savingLoc \? "Working…"/.test(code.replace(/disabled:opacity-50" /g, 'disabled:opacity-50"\n '))
   && (code.match(/background: ?"var\(--action\)"/g) || []).length >= 22);
const navyButtons = [...code.matchAll(/<button[^>]*?background: ?"var\(--navy\)"/g)].map(m => m[0]);
ok("...no ACTION button is filled blue any more: the one navy-filled button left is a selection (the drawing palette's picked tool, aria-pressed)",
   navyButtons.length === 1 && navyButtons[0].startsWith("<button {...r} aria-pressed={on}"), navyButtons.length + " navy buttons");
ok("⭐ 13: ONE tab — .ws-tab, the selected one a --navy-soft tint with --navy text and edge, never filled like a button",
   css.includes('.ws-tab[aria-selected="true"],.ws-tab[aria-current="page"],.ws-tab[aria-pressed="true"],.ws-on{background:var(--navy-soft);color:var(--navy);border-color:var(--navy);}'));
ok("...Users' tabs, the Look-ahead's Account / Commit / Horizon, Stockpiles' piles and years and the CLP notes' tabs all use it",
   code.includes('className="ws-tab" aria-current={tab === k ? "page" : undefined}>{l}</button>)}')
   && code.includes('<button key={id} type="button" onClick={() => pick(id)} className="ws-tab" aria-current={view === id ? "page" : undefined}>{label}</button>')
   && code.includes('<div className="ws-tabs mb-3" role="tablist" aria-label="Stockpile">') && code.includes('className="ws-tab">{y}</button>)}')
   && code.includes('<div className="ws-tabs mt-2 mb-1" role="tablist" aria-label="Whose notes and tasks" data-clp-tabs="1">')
   && !code.includes('className={tab === k ? "btn-pri" : "btn-sec"}'));
ok("...Config's section list shows its picked section the same way (tint, --navy text and edge)", css.includes(".cfg-nav-item.is-on{color:var(--navy);font-weight:600;border-left-color:var(--navy);background:var(--navy-soft);}"));
ok("...the selected segment (Loads / Tonnes / Lorries, the Simulation's, the route legs) is the tint, not a blue fill",
   css.includes('.unit-sw-seg button[aria-pressed="true"]{background:var(--navy-soft);color:var(--navy);box-shadow:inset 0 0 0 1px var(--navy);}')
   && css.includes(".sim-seg button.on{background:var(--navy-soft);color:var(--navy);box-shadow:inset 0 0 0 1px var(--navy);}")
   && code.includes('(leg === v ? { background: "var(--navy-soft)", color: "var(--navy)", boxShadow: "inset 0 0 0 1px var(--navy)" }'));
ok("...Export XLSX and Supplier orders are plain secondary buttons; the route panel's two Saves take the accent",
   code.includes('className="btn-sec disabled:opacity-40">Export XLSX</button>') && code.includes('borderColor: "var(--line)", color: "var(--ink)", background: "var(--surface)", opacity: disabled ? 0.4 : 1 }}>Supplier orders')
   && !code.includes('borderColor: "var(--navy)", color: "var(--navy)"'));

// ---------------------------------------------------------------- finding 14: the staff maps in Dark
ok("⭐ 14: the Route map (the map page embedded in the app) reads the app's look and opens on Dark there",
   map.includes("const appDark = () => { try { return EMBED && localStorage.getItem('modus_theme') === 'dark'; }")
   && map.includes("const lookBasemap = () => appDark() ? 'mapbox://styles/mapbox/dark-v11' : 'mapbox://styles/mapbox/light-v11';")
   && map.includes("const INITIAL_BASEMAP = LINK_BASEMAP || lookBasemap();"));
ok("...a basemap picked by hand (the select, the widget, the link) is kept; otherwise a change of look in the app restyles it",
   map.includes("function pickBasemap(styleUrl) { BASEMAP.byHand = true; changeBasemap(styleUrl); }") && map.includes('onchange="pickBasemap(this.value)"')
   && map.includes("window.changeTheme = function(btn, styleUrl) { pickBasemap(styleUrl); };") && map.includes("byHand: !!LINK_BASEMAP")
   && map.includes("if (!BASEMAP.byHand) changeBasemap(lookBasemap());") && map.includes("if (opt) pickBasemap(want);"));
const mapCss = (map.match(/<style>[\s\S]*?<\/style>/g) || []).join("\n");
ok("...the panel, the figures bar, the timeline and the drawers are on tokens, with a Dark block for the embedded map only",
   !/background:\s*#fff(?![0-9a-fA-F])/.test(mapCss) && mapCss.includes("html[data-look=\"dark\"]{") && mapCss.includes("--surface:#1F2024;")
   && /#kpi-hud\{[^}]*background:var\(--surface\)/.test(mapCss.replace(/\n\s*/g, " ")) && map.includes("document.documentElement.setAttribute('data-look', 'dark')"));
ok("...the fixed light boxes the token swap does not reach go dark too (found in Chrome): the tour strip, the timeline rail, the drawer's picked tab, the credit line; no inline fixed grey text left",
   mapCss.includes('html[data-look="dark"] .guide-strip{') && mapCss.includes('html[data-look="dark"] .tl-rail{') && mapCss.includes('html[data-look="dark"] .drawer-tab.active{')
   && mapCss.includes('html[data-look="dark"] .mapboxgl-ctrl.mapboxgl-ctrl-attrib{') && !/color:#(57534E|5b6270)/i.test(map) && !map.includes("12.5px;color:#475569"));
ok("...the data pages' map opens on the look's basemap and follows a change of look unless picked by hand; the Look-ahead's map opens on it",
   code.includes("const [basemap, setBasemap] = useState(() => lookMapStyle());") && code.includes("if(!basemapByHand.current) changeStyle(lookMapStyle(), true);")
   && code.includes("if(!auto) basemapByHand.current = true;") && code.includes("style: lookMapStyle(),   // 10 Nov 2026 (card 14)"));

// ---------------------------------------------------------------- finding 20: units and formats
ok("⭐ 20: Config → Planning sets the organisation's ONE distance unit (Miles | Kilometres → tenant.distance_unit)",
   code.includes('data-cfg="distance-unit"') && code.includes('onClick={() => upd(d => { d.tenant = d.tenant || {}; d.tenant.distance_unit = k; })}')
   && code.includes('[["mi", "Miles"], ["km", "Kilometres"]]') && code.includes('data-ro-only-on="1"'));
ok("...a saved unit reaches every screen at once; a reader of Config sees the chosen unit only",
   code.includes('if(du === "mi" || du === "km") TENANT.distance_unit = du;') && css.includes('.cfg-ro [data-ro-only-on] button[aria-pressed="true"]{display:inline-flex;cursor:default;}'));
ok("...Config's per-distance figures are typed in the unit (kg CO₂e, the three litres per 100, the running cost, the average haul speed): no km label left",
   (code.match(/<UnitNum /g) || []).length >= 6 && !code.includes('"kg CO₂e / km"') && !code.includes("L/100 km per tonne carried") && !code.includes("empty L/100 km</span>")
   && code.includes("`Average haul speed, ${SPD()}`") && code.includes("Assigned speed ({SPD()})"));
ok("...the unit field re-reads its value with Object.is, so a NaN can never re-render it for ever",
   code.includes("useEffect(() => { if(!Object.is(value, last.current) || unit.current !== DU()){"));
ok("...a haul road's speed is typed in the unit and saved in km/h",
   code.includes('? Math.round(Number(zoneForm.speed_kph) * (DU() === "mi" ? KM_PER_MI : 1) * 10) / 10 : null),')
   && code.includes('speed_kph: (z.speed_kph == null ? "" : String(Math.round(speed(z.speed_kph) * 10) / 10)),'));
ok("...Config's last saved is UK time with the person's name, never \"UTC\" nor \"by —\"",
   code.includes('timeZone: "Europe/London" }); };') && !code.includes('" UTC"; };') && !code.includes('by {status.updated_by || "—"}'));
ok("...money is written against the symbol (no \"£ 57 833\"); a fuel price says per litre where there is room",
   !code.includes("${CUR()} ${") && !code.includes("`${CUR()} ` +") && code.includes("const eurFmt = (n) => (n == null) ? \"rate not set\" : `${CUR()}` + grp(n);")
   && code.includes("toFixed(3)} per litre` : null;") && code.includes("toFixed(3)}/L` : null;   // 10 Nov 2026 (finding 20): the compact card is tight") && !code.includes("toFixed(3)} / L"));
// the formatters themselves, run
const pick = (re) => { const m = code.match(re); if (!m) throw new Error("missing " + re); return m[0]; };
let F = null;
try {
  const snippet = [
    'const TENANT = { distance_unit: "mi", symbol: "£" }; const CUR = () => TENANT.symbol;',
    'const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];',
    pick(/const KM_PER_MI = [^\n]*/), pick(/const DU = [^\n]*/), pick(/const dist = [^\n]*/), pick(/const distRate = [^\n]*/), pick(/const distInRate = [^\n]*/),
    pick(/const grp = \(n, d\)[^\n]*\n[^\n]*/), pick(/const eurFmt = [^\n]*/), pick(/const monthLabelAbs = [^\n]*/), pick(/const monthAxis = [^\n]*/),
    pick(/const cfgWhen = [^\n]*/),
    "module.exports = { TENANT, grp, eurFmt, monthLabelAbs, monthAxis, cfgWhen, distRate, distInRate };"].join("\n");
  const m = { exports: {} }; new Function("module", ts.transpile(snippet))(m); F = m.exports;
} catch (e) { fail.push("formatters did not load: " + e.message); }
if (F) {
  ok("⭐ 20: thousands with a comma: 8,405 · 162,438 · 1,374; decimals kept", F.grp(8405) === "8,405" && F.grp(162438) === "162,438" && F.grp(1234.5, 1) === "1,234.5", F.grp(8405));
  ok("...money \"£57,833\"", F.eurFmt(57833) === "£57,833", F.eurFmt(57833));
  ok("...months \"May 2026\" (never \"May 26\"); \"May '26\" only from monthAxis", F.monthLabelAbs(5, 2026) === "May 2026" && F.monthLabelAbs(13, 2026) === "Jan 2027" && F.monthAxis(5, 2026) === "May '26", F.monthLabelAbs(5, 2026));
  ok("...last saved \"10 Nov 2026, 14:05\" in UK time (a 14:05 GMT save), \"9 Jun 2026, 15:30\" in summer time (14:30 UTC)",
     F.cfgWhen("2026-11-10 14:05:00") === "10 Nov 2026, 14:05" && F.cfgWhen("2026-06-09 14:30:00") === "9 Jun 2026, 15:30", F.cfgWhen("2026-11-10 14:05:00") + " | " + F.cfgWhen("2026-06-09 14:30:00"));
  ok("...a rate per km shows per mile and a typed per-mile rate goes back to per km: 1 kg a km = 1.609344 kg a mile, and back",
     Math.abs(F.distRate(1) - 1.609344) < 1e-9 && Math.abs(F.distInRate(1.609344) - 1) < 1e-9 && Math.abs(F.distInRate(F.distRate(0.99773)) - 0.99773) < 1e-12);
}
ok("...chart axes use the short month, pickers and headings the full one",
   code.includes("labels.push(monthAxis(i, months.start_year));") && code.includes("data.by_month.map(r => monthAxis(cnIdx(r.month, sy), sy))")
   && code.includes("const rangeLabel = D.lo === D.hi ? monthLabelAbs(D.lo, months.start_year)"));
const cfgPy = read("backend", "config.py");
ok("⭐ 20: with no unit saved, a GB organisation reads miles, any other km (backend config.tenant_settings)",
   cfgPy.includes('t["distance_unit"] = du if du in DISTANCE_UNITS else ("mi" if t["country"] == "GB" else "km")'));
const bd = read("backend", "bulletin_doc.py"), ex = read("backend", "export.py"), bm = read("backend", "basemap.py");
ok("...the bulletin's and the PDF maps' scale bars are in the organisation's unit; the bulletin's carbon line says distance, not km",
   bd.includes("km, px = basemap.scale(v, 110, unit=du)") && bd.includes('class="sc">{km:g} {word}</text>') && ex.includes("km, px = basemap.scale(v, 24 * mm / k, unit=du)")
   && bm.includes('def scale(v, target_px, unit="km"):') && bd.includes("split by the distance driven in each district") && !bd.includes("routed km × the vehicle"));

console.log(`ui_fix_consistency.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  ✗ " + f)); process.exit(1); }
