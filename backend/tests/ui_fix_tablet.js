/*
 * ui_fix_tablet.js — the 9 Nov 2026 UI critique, wave 4, branch claude/ui-fix-tablet: finding 3 under John's decision 2
 * ("at 768–1024 px the rail folds to icons and the busy tables become cards"), built from the mockup he approved on 10 Nov
 * (notes\ui-fix-tablet-mockup-1110\, cards 1–8).
 *
 *   Card 1: at 768–1024 the rail always opens folded (the desk's Collapse choice stays the desk's); "›" or Ctrl K opens the
 *     full rail OVER the page (a scrim, Escape, a page picked or a tap outside folds it); the waiting counts ride on the
 *     icons; a folded icon says its name when pointed at or focused, and to a screen reader; User guide is in the opened rail.
 *   Cards 2–5: Forecasts, Abnormal loads, Pours, CLP documents, Routes, Zones and Locations are one card a row at 768–1024
 *     (.tab-cards): the lead and the status on the top line, the figures in a row with their labels, the foot and the one
 *     next-step button with its "⋯" last; the Data page's panel (the key, the editor) sits under the map there.
 *   Card 6: the Look-ahead's Status sits under the route's name at 768–1024 and the day columns narrow.
 *   Card 7: Configuration → Vehicles: cards two a row at 768–1024; on a desk the name column is held and a fade says more.
 *   Card 8: on both maps at 768–1024, while the Control Panel is shut, Play and the month chips at the foot (the timeline
 *     bar's place), the map opening on this month.
 *
 * Its own file (the wave rule, notes\ui-critique-1109.md §H). Source and CSS checks: each fails on the code before this
 * branch. The layouts themselves were checked in Chrome at 768 and 1024 by the UI audit (BROWSER_ONLY, never CI).
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const css = html.slice(0, html.indexOf("</style>"));
const map = read("map", "index.html");
const between = (src, a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i + 1); return i >= 0 && j > i ? src.slice(i, j) : ""; };
// the CSS inside one @media block, from its opening line to its closing brace (balanced)
const mediaBlock = (src, opener) => {
  const i = src.indexOf(opener); if (i < 0) return "";
  let d = 0, j = src.indexOf("{", i);
  for (let k = j; k < src.length; k++) { if (src[k] === "{") d++; else if (src[k] === "}") { d--; if (!d) return src.slice(i, k + 1); } }
  return "";
};
const TAB_MQ = "@media (min-width:768px) and (max-width:1024px){";

// ---------------------------------------------------------------- one tablet range, read once
ok("the tablet range is ONE query, 768–1024 px (TABLET_MQ), read by a shared hook (useMQ); the phone's stays below 768",
   code.includes('const TABLET_MQ = "(min-width: 768px) and (max-width: 1024px)";') && /function useMQ\(q\)\{/.test(code)
   && code.includes('const NARROW_Q = "(max-width: 767px)";'));

// ---------------------------------------------------------------- card 1: the folded rail
const app = between(code, "const TABLET_Q = TABLET_MQ;", "<main className=\"flex-1 min-h-0 overflow-auto\">");
ok("⭐ 1: at 768–1024 the rail is open only while it is opened over the page (railOver); the desk keeps its own choice (railDesk, modus_rail)",
   app.includes("const railOpen = tablet ? railOver : railDesk;") && app.includes("const railShown = railOpen;")
   && /const \[railDesk, setRailOpen\] = useState\(\(\) => \{ try \{ return localStorage\.getItem\("modus_rail"\) !== "closed";/.test(code)
   && app.includes('const v = !railDesk; setRailOpen(v); try { localStorage.setItem("modus_rail", v ? "open" : "closed"); } catch(e){}'));
ok("...a tablet's \"›\" opens it over the page and focuses Find a page; it is never written to the desk's choice",
   app.includes("if(tablet){ const v = !railOver; setRailOver(v); setRailTip(null); if(v) setTimeout(() => navRef.current && navRef.current.focus(), 0); return; }"));
ok("...Ctrl K opens the over-the-page rail on a tablet, the desk rail on a desk, the More sheet on a phone",
   code.includes("if(window.matchMedia && window.matchMedia(NARROW_Q).matches){ setMoreOpen(true); return; } if(window.matchMedia && window.matchMedia(TABLET_Q).matches) setRailOver(true); else setRailOpen(true);"));
ok("⭐ 1: it folds again on Escape, on a page picked (any way: an effect on the page) and on a tap outside (the scrim)",
   app.includes('const k = (e) => { if(e.key === "Escape") setRailOver(false); };')
   && app.includes("useEffect(() => { setRailOver(false); setRailTip(null); }, [page]);")
   && app.includes('<div className="rail-scrim" aria-hidden="true" data-rail-scrim="1" onClick={() => setRailOver(false)} />'));
ok("...the opened rail lies OVER the page: a 56 px spacer keeps the page where it was, the rail absolute with a shadow, the scrim under it",
   app.includes('{!narrow && tablet && railOver && <div className="w-14 shrink-0" aria-hidden="true" data-rail-spacer="1" />}')
   && app.includes('(tablet && railOver ? " rail-over" : "")')
   && /\.rail\.rail-over\{position:absolute;left:0;top:0;bottom:0;z-index:60;/.test(css) && /\.rail-scrim\{position:absolute;inset:0;z-index:59;/.test(css));
ok("⭐ 1: a folded rail keeps the waiting counts as a badge on the icon (it dropped them before)",
   app.includes('{badge != null && !railShown && <span className="rail-dot" aria-hidden="true" data-rail-dot={it.id}>{badge}</span>}')
   && /\.rail-dot\{position:absolute;[^}]*background:var\(--action\);color:var\(--action-fg\);font-size:12px;/.test(css));
ok("...a folded icon is named for a screen reader with its count (\"Forecasts, 1 waiting\"), and the current page says so",
   app.includes("aria-label={railShown ? undefined : it.label + (badgeWords ? \", \" + badgeWords : \"\")}")
   && app.includes('const badgeWords = badge == null ? "" : it.id === "concerns" ? `${badge} new` : `${badge} waiting`;')
   && app.includes('aria-current={active ? "page" : undefined}'));
ok("⭐ 1: on a tablet a folded icon says its name beside itself when pointed at OR focused (railTip, a fixed tip: the rail's scroller would clip a ::after)",
   app.includes("onMouseEnter={tipOn} onFocus={tipOn} onMouseLeave={() => setRailTip(null)} onBlur={() => setRailTip(null)}")
   && app.includes('{!narrow && tablet && railTip && <div className="rail-tip" role="presentation" aria-hidden="true" style={{ top: railTip.top }} data-rail-tip="1">{railTip.label}</div>}')
   && /\.rail-tip\{position:fixed;left:60px;[^}]*font-size:13px;/.test(css));
ok("...the desk's folded rail keeps its browser tooltip (title); a tablet's uses the tip instead, never both",
   app.includes("title={railShown || tablet ? undefined : it.label}"));
ok("⭐ 1: User guide is in the opened rail on a tablet (not on the folded one); the desk shows it as before",
   app.includes('{(!tablet || railShown) && <a href={"/help/?role="'));
ok("...the toggle says whether the tablet rail is open (aria-expanded), the words \"‹ Collapse\" / \"›\" as before",
   app.includes('aria-expanded={tablet ? (railOver ? "true" : "false") : undefined} data-rail-toggle="1">')
   && app.includes('{railShown ? "‹ Collapse" : "›"}'));
ok("🔴 1: the phone has no rail still (below 768: the tab bar), and nothing of the tablet rail is drawn there",
   app.includes('{!narrow && <aside data-guide="rail" className={"rail shrink-0') && app.includes("{!narrow && tablet && railOver && <div className=\"rail-scrim\""));

// ---------------------------------------------------------------- cards 2–5: the cards
const tc = mediaBlock(css, TAB_MQ + "\n    .tab-cards{");
ok("⭐ 2–5: ONE card rule for every busy table at 768–1024 (.tab-cards): no header, a grid card a row, a label over each figure",
   !!tc && tc.includes(".tab-cards>thead{display:none;}") && tc.includes(".tab-cards,.tab-cards>tbody{display:block;}")
   && /\.tab-cards>tbody>tr:not\(\.rd-details\):not\(\.al-det-row\):not\(:has\(>td\[colspan\]\)\)\{position:relative;display:grid;grid-template-columns:repeat\(var\(--tc-n,4\),minmax\(0,1fr\)\);/.test(tc)
   && tc.includes(".tab-cards>tbody>tr>td[data-label]::before{content:attr(data-label);display:block;font-size:12px;font-weight:600;color:var(--muted);"));
ok("...the lead (rd-primary) top left, the status (rd-status) top right with no label, the foot and the one next step (rd-actions) last",
   tc.includes(".tab-cards>tbody>tr>td.rd-primary{order:0;grid-column:1 / -2;}") && tc.includes(".tab-cards>tbody>tr>td.rd-status{order:1;grid-column:-2 / -1;justify-self:end;")
   && tc.includes(".tab-cards>tbody>tr>td.rd-status::before,.tab-cards>tbody>tr>td.rd-primary::before{content:none !important;}")
   && /\.tab-cards>tbody>tr>td\.tc-foot\{order:8;/.test(tc) && /\.tab-cards>tbody>tr>td\.rd-actions\{order:9;grid-column:-2 \/ -1;[^}]*display:flex;justify-content:flex-end;/.test(tc));
ok("...a row's details (and any row of one wide cell) hang under its card; a folded CLP child stays hidden; .tc-hide is left to the details",
   tc.includes(".tab-cards>tbody>tr.rd-details,.tab-cards>tbody>tr.al-det-row,.tab-cards>tbody>tr:has(>td[colspan]){display:block;")
   && tc.includes(".tab-cards>tbody>tr[hidden]{display:none !important;}") && tc.includes(".tab-cards .tc-hide{display:none !important;}"));
ok("🔴 2–5: none of it reaches the phone or the desk: the card rule lives inside the one 768–1024 block, and .tc-only is hidden outside it",
   !/\.tab-cards[^{]*\{/.test(css.replace(tc, "").replace(/\/\*[\s\S]*?\*\//g, "")) && css.includes("  .tc-only{display:none !important;}"));

// card 2: Forecasts
const fc = between(code, "function Forecasts(", "function CostingTab(");
ok("⭐ 2: Forecasts are cards at 768–1024 (three figures a row; Approve and ⋯ at the foot, the status top right)",
   fc.includes('<table className="tbl rd-table tab-cards" data-rd-table="forecasts" style={{ "--tc-n": 3 }}>')
   && fc.includes('<td className="rd-status" data-label="Status">') && fc.includes('<td className="num whitespace-nowrap rd-actions">'));

// card 3: Abnormal loads
const al = between(code, "function AbnormalPage(", "\nfunction ");
const alRow = between(al, "<tr data-al-row={m.id}", "</tr>");
ok("⭐ 3: Abnormal loads are cards: the load and its size lead, the status top right, From → to / Window / What it needs / Notify by labelled",
   al.includes('<table className="tbl al-tbl tab-cards" data-tab-cards="abnormal">')
   && alRow.includes('<td className="rd-primary"><div className="font-medium text-slate-800">{m.name}</div>')
   && alRow.includes('<td className="rd-status"><StatusWord')
   && ["From → to", "Window", "What it needs", "Notify by"].every(l => alRow.includes(`data-label="${l}"`)));
ok("...team and route on the foot line beside the next-step button and ⋯; the gates and the apply-by date are left to Details",
   alRow.includes('<td className="tc-foot">{m.team_name || "—"}</td>') && alRow.includes('<td className="tc-foot tc-span2" data-al-route-cell=')
   && alRow.includes('data-al-actions={m.id}>') && alRow.includes('className="text-right whitespace-nowrap rd-actions"')
   && /text-\[13px\] text-slate-500 tc-hide">\{\[m\.origin_gate_name/.test(alRow) && alRow.includes('text-[13px] text-slate-500 tc-hide">apply by'));
ok("⭐ 3: a card opens its details with a worded \"Details\" (tc-only: a tablet only); the chevron cell is left out there",
   alRow.includes('<button type="button" className="tc-only al-det-btn" aria-expanded={isOpen} data-al-det-btn={m.id} onClick={() => setOpen(isOpen ? null : m.id)}>{isOpen ? "Hide details" : "Details"}</button>')
   && alRow.includes('<td className="tc-hide"><button type="button" className={"al-tri"'));

// card 4: Pours and CLP documents
const pours = between(code, "function PoursPage(", "\nfunction ");
ok("⭐ 4: Pours are cards at 768–1024 (1024 too): the pour leads, m³ / Mixers / Gap labelled, the status top right, ⋯ at the foot",
   pours.includes('<table className="tbl tab-cards" data-pours-table="1" style={{ "--tc-n": 3 }}>')
   && pours.includes('<td className="rd-primary" style={{ whiteSpace: "normal" }}>') && ["m³", "Mixers", "Gap"].every(l => pours.includes(`data-label="${l}"`))
   && pours.includes('<td className="rd-actions"><RowMenu name={p.place || p.id}>'));
const clp = between(code, "function ClpPage(", "\nfunction ");
ok("⭐ 4: CLP documents are cards: the CLP leads, its status top right, Last issue and Tasks labelled, the next step and ⋯ across the foot",
   clp.includes('<table className="tbl tab-cards" data-clp-table="1" style={{ "--tc-n": 2 }}>') && clp.includes('<td className="rd-primary" style={{ whiteSpace: "normal", minWidth: 220 }}>')
   && clp.includes('<td data-label="Last issue">') && clp.includes('<td data-label="Tasks" data-clp-tasks-cell="1">')
   && clp.includes('<td className="rd-actions tc-wide"><div className="flex items-center gap-2 justify-end">{primary(c, child)}'));
ok("...checked in Chrome at 768: the foot's lines join (the foot cells stretch to one height), a chip wraps in its column, a route's ▶ has its own room and a 28 px tap",
   tc.includes(".tab-cards>tbody>tr>td.tc-foot{order:8;align-self:stretch;display:flex;") && /td\.rd-actions\{[^}]*align-self:stretch;/.test(tc)
   && tc.includes(".tab-cards>tbody>tr>td>span{display:inline-block;max-width:100%;white-space:normal;}")
   && tc.includes(".tab-cards>tbody>tr.tc-has-tri{padding-left:46px !important;}") && tc.includes(".tab-cards>tbody>tr>td.tc-tri>button{width:28px;height:28px;}"));
ok("...a Simulation tick is 24 px tall on one line (a wider page at 768–1024 put \"Wheel wash on the way out\" on one 21 px line: the audit's targets-24px)",
   css.includes(".sim-check{display:flex;align-items:flex-start;gap:8px;cursor:pointer;min-height:24px;}"));
ok("...a site's team CLPs still fold under it, indented as cards", css.includes(".tab-cards>tbody>tr.clp-kid{margin-left:40px;}"));

// card 5: Routes, Zones, Locations, and the panel under the map
const dm = between(code, "function DataManagement(", "\nconst styles_ok");
ok("⭐ 5: Routes, Zones and Locations are cards at 768–1024, each cell labelled (the team in the tenant's word, the distances in its unit)",
   ["routes", "zones", "locations"].every(t => dm.includes(`tab-cards" data-tab-cards="${t}"`))
   && dm.includes("data-label={TEAM()}") && dm.includes("data-label={`Out ${DU()}`}") && dm.includes("data-label={`Back ${DU()}`}")
   && ["Near the route", "Out min", "Back min", "Vehicles", "Kind", "Routing", "From", "To", "Used by", "Type", "Role", "Supplies", "Receives", "Coordinates", "Gate", "Routes"].every(l => dm.includes(`data-label="${l}"`)));
ok("...a route's code and From → to lead the card (its ▶ top left), a zone's State top right, an admin's Route / ⋯ at the foot",
   dm.includes('className="px-3 py-2 font-medium text-slate-800 tc-lead"') && dm.includes('<td className="px-3 py-2 tc-lead tc-span3" style={{ minWidth: 220 }}>')
   && dm.includes('<td className="px-2 py-2 tc-tri">') && dm.includes('<td className="px-3 py-2 text-xs rd-status">')
   && dm.includes('<td className="px-3 py-2 text-right whitespace-nowrap rd-actions tc-late">') && dm.includes('<td className="px-3 py-2 text-right rd-actions" onClick={e => e.stopPropagation()}>'));
ok("⭐ 5: the map keeps the full width at 768–1024: map | panel side by side only above 1024 px, no gap at a zoomed 1024.2 (was Tailwind's lg, 1024), the panel's height free there",
   dm.includes('"grid dm-grid gap-4"') && dm.includes('"dm-map card overflow-hidden"') && !dm.includes("lg:grid-cols-3 gap-4") && !dm.includes("lg:col-span-2 card")
   && css.includes("@media not all and (max-width:1024px){ .dm-grid{grid-template-columns:repeat(3,minmax(0,1fr));} .dm-grid>.dm-map{grid-column:span 2 / span 2;} }")
   && dm.includes('const panelStyle = isWide && !tabletW ? { height: MAP_H, overflowY: "auto" } : undefined;'));

// ---------------------------------------------------------------- card 6: the Look-ahead
const la = between(code, "function LookAhead({ meta, who, access, initialPage, initialView }){", "\nfunction CommitMap(");
ok("⭐ 6: at 768–1024 the Status column goes and its chip (and last week's carry line) sits under the route's name",
   la.includes("const laTab = useMQ(TABLET_MQ);") && la.includes("{!laTab && <th>Status</th>}")
   && la.includes('{laTab && <span className="la-st-under" data-la-st-under="1"><RowStatus word={st.word} tone={st.tone} more={st.more} />')
   && la.includes('{!laTab && <td className="rd-status" data-label="Status">') && la.includes("{!laTab && <td></td>}")
   && la.includes("colSpan={(laTab ? 2 : 3) + dates.length}"));
ok("...the day columns narrow (Mon–Fri and Week fit at 768 with the rail folded); more days scroll, the route column held at 200 px",
   la.includes("style={{ minWidth: laTab ? `${200 + (dates.length + 1) * 70}px` : `${440 + dates.length * 96}px` }}")
   && la.includes('<div className="overflow-auto rd-scroll" data-la-tab={laTab ? "1" : undefined}>')
   && css.includes('[data-la-tab="1"] .tbl .la-stick{min-width:200px !important;}') && css.includes(".la-st-under{display:block;margin-top:4px;font-weight:400;}"));
ok("🔴 6: the desk's grid is as it was (the Route column 280 px, one Status column, 96 px a day)",
   la.includes('<th className="la-stick" style={{ minWidth: 280 }}>Route</th>') && la.includes('firstStyle={{ minWidth: 280 }}'));
ok("...the eight cards stay two rows of four from 768 (md:grid-cols-4), as approved on 9 Nov", la.includes('<div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-3">'));

// ---------------------------------------------------------------- card 7: Configuration → Vehicles
const cfg = between(code, "function ConfigPage(", "\nfunction ");
const veh = between(cfg, '{tab === "vehicles" && (', '{tab === "materials" && (');
ok("⭐ 7: on a desk the vehicle's name column is held while the rest scrolls, and a fade says there is more (FadeScroll, data-more)",
   veh.includes('<FadeScroll className="cfg-veh-fade" data-cfg-veh-scroll="1">') && veh.includes('<table className="tbl cfg-veh" data-cfg-veh-table="1">')
   && veh.includes('<td className="cfg-veh-name"><div className="font-medium text-slate-800 leading-tight" data-cfg-vehname>{nm}</div>')
   && css.includes(".tbl.cfg-veh th:first-child,.tbl.cfg-veh td.cfg-veh-name{position:sticky;left:0;z-index:2;background:var(--surface);")
   && css.includes('.fade-scroll[data-more="1"]::after{opacity:1;}'));
ok("...FadeScroll measures the scroller itself (on scroll, after a render, on a resize); no new ResizeObserver (the page counts them)",
   /function FadeScroll\(\{ className, children, \.\.\.rest \}\)\{/.test(code)
   && code.includes("setMore(!!t && t.getBoundingClientRect().right > sc.getBoundingClientRect().left + sc.clientWidth + 2);")
   && !/new ResizeObserver/.test(between(code, "function FadeScroll(", "\n}\n")));
const vb = mediaBlock(css, TAB_MQ + "\n    .fade-scroll.cfg-veh-fade::after");
ok("⭐ 7: a Config READER's scroll box is the one outside the fieldset (.cfg-ro-box): the fade measures that box, listens to it and stays at its edge (checked in Chrome)",
   code.includes('const scroller = (el) => (window.getComputedStyle(el).overflowX === "visible" && el.closest(".cfg-ro-box")) || el;')
   && code.includes('sc.addEventListener("scroll", check, { passive: true })') && code.includes('el.parentElement.style.setProperty("--fade-x", sc === el ? "0px" : `${-sc.scrollLeft}px`)')
   && css.includes(".fade-scroll::after{content:\"\";position:absolute;top:0;right:var(--fade-x,0px);bottom:0;"));
ok("⭐ 7: at 768–1024 each vehicle is a card, two a row, each box with its label over it (the name and the name boxes across)",
   !!vb && vb.includes(".tbl.cfg-veh>tbody{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));")
   && vb.includes(".tbl.cfg-veh>tbody>tr>td.cfg-veh-name,.tbl.cfg-veh>tbody>tr>td.cfg-veh-wide,.tbl.cfg-veh>tbody>tr>td.cfg-veh-span{grid-column:1 / -1;}")
   && vb.includes(".tbl.cfg-veh>tbody>tr>td.cfg-veh-name{position:static;box-shadow:none;}")   // the desk's held column draws no edge in a card
   && veh.includes('<td className={"num w-28" + (v.fuel === "electric" ? " cfg-veh-span" : "")}')   // a reader's "derived: kWh × UK grid" spans the card
   && ["Payload t", "GVW t", "Load min", "Unload min", "Euro class", "Planning", "English name"].every(l => veh.includes(`data-label="${l}"`))
   && veh.includes("data-label={`kg CO₂e / ${PER_DIST()}`}"));

// ---------------------------------------------------------------- card 8: the maps
const ts = mediaBlock(map, "@media (min-width:768px) and (max-width:1024px){\n            body.sidebar-closed:not(.wall-mode) #t-strip{");
ok("⭐ 8: at 768–1024, with the Control Panel shut, Play and the month chips at the map's foot (#t-strip), in the timeline bar's place",
   map.includes('<div id="t-strip" role="group" aria-label="Months on the map">')
   && map.includes('<button type="button" class="t-play" id="t-play" onclick="toggleTimeline()" aria-label="Play" aria-pressed="false">&#9654;</button>')
   && map.includes('<div class="t-chips m-chips-row"><div class="month-chips" id="t-chips" role="group" aria-label="Month"></div></div>')
   && /#t-strip\{ display:none; \}/.test(map) && !!ts && ts.includes("body.sidebar-closed:not(.wall-mode) #timeline-bar{ display:none !important; }"));
ok("...its chips are the page's own (renderMonthChips fills every .month-chips, scrolls the row to the month), 44 px taps, Play in the accent",
   /document\.querySelectorAll\('\.month-chips'\)\.forEach/.test(map) && ts.includes("#t-strip .month-chip{ flex:0 0 auto; min-height:44px; min-width:52px; }")
   && ts.includes("#t-strip .t-play{ flex:0 0 48px; width:48px; height:48px;"));
ok("⭐ 8: the map opens on this month there (openTabletMonth → openTimeline: D22's start month), never over a linked month or in wall mode, once",
   /function openTabletMonth\(\) \{\n[^\n]*\n\s*if \(TSTRIP\.opened \|\| !isTabletStrip\(\) \|\| sidebarIsOpen\(\) \|\| TL\.on \|\| TL\.cleared \|\| TL\.wall/.test(map)
   && map.includes("applyViewFromUrl();\n        openTabletMonth();")
   // and only after the one read of every month's figures: no single-month heavy read beside it on every tablet load
   && map.includes("ensureTimelineMatrix().then(() => kpiFetchAll().catch(() => {}))\n            .then(() => { if (!TL.on && !TL.cleared && isTabletStrip() && !sidebarIsOpen()) openTimeline(); syncTimelineFoot(); }, () => {});") && map.includes("const TABLET_STRIP_MQ = '(min-width:768px) and (max-width:1024px)';"));
ok("...the strip's Play follows the timeline (syncPlayButtons), and the map's credits ride above the strip as above the bar (--tl-foot)",
   map.includes("const tp = document.getElementById('t-play');") && map.includes("const foot = sOn ? Math.round(strip.offsetHeight + 18 + 8) : h;")
   && map.includes("observeEl('main-sidebar', { attributes: true, attributeFilter: ['class'] }, () => setTimeout(syncTimelineFoot, 0));"));
ok("...with a month on screen at 768 (the audit) a council's tick row was 20 px: now 24 px, every width",
   map.includes("#area-district-rows .control-item label{ min-height:24px; }"));
ok("🔴 8: the phone's sheet and the desk are untouched: the strip shows only inside the 768–1024 block, and below 768 the sheet keeps its chips",
   map.includes('<div class="month-chips" id="m-chips" role="group" aria-label="Month"></div>') && !/#t-strip\{ display:flex/.test(map.replace(ts, "")));

// ---------------------------------------------------------------- the house rules on the new words
// the words a person reads: the badge's words and the Details button's
const newWords = ["`${badge} new`", "`${badge} waiting`", '"Hide details" : "Details"'];
ok("🔴 the new words name no back end and no id (\"waiting\", \"new\", \"Details\")", newWords.every(w => code.includes(w)) && !/HERE|server|endpoint|token|IPT\d|\bid\b/.test(newWords.join(" ")));
ok("🔴 no 9, 10 or 11 px text in the new CSS", ![css.slice(css.indexOf("TABLET-RAIL"), css.indexOf(".rail-tip{") + 300), tc, vb, ts].some(b => /font-size:(9|10|11)px/.test(b)));

console.log(`ui_fix_tablet.js: ${pass} passed, ${fail.length} failed`);
fail.forEach(f => console.log("  FAIL: " + f));
process.exit(fail.length ? 1 : 0);
