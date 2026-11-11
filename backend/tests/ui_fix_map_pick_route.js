/* ui_fix_map_pick_route.js — 12 Nov 2026, branch claude/map-pick-route (John, 11 Nov: "Yes, A and R1 now", from the mockup page
 * notes\map-forecast-detail-mockup-1111). Source checks on map/index.html plus sandboxes that run the page's OWN functions
 * against stand-ins; no browser (the browser half is the Chrome check in the session note).
 *
 *   A.  The route panel's "Forecast detail" tab opened EMPTY after a route was picked: the tab only showed the panel, and only the
 *       Control Panel's button asked for the table. The tab now loads the table itself, and the picked route's lines come first,
 *       tinted. Nothing else about the table changes.
 *   R1. The road card's rows were plain text: only the clicked line's route was tinted and had a button. Each route number is now
 *       a button: a click tints that row and lights that route on the map as a picked route looks today; the card stays open;
 *       the one "<route>'s card" button follows the row.
 *
 * Its own file (BUILD.md rule 3; the card's own HTML checks are in parse_map.js's sandbox). Every check fails on the code before.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");
let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
const fnSrc = (re) => (re.exec(html) || [""])[0];
const mat = (names) => { const m = {}; let i = 0; names.forEach(k => { m[k] = "#c" + (i++); }); return m; };

(async () => {
  // ---------- A: the Forecast detail tab ----------
  ok("⭐ A: the tab's button loads the table itself (openForecastDetail), no longer only shows the empty panel; the Control Panel's own button still calls it",
     html.includes('<button class="drawer-tab" id="tab-detail" onclick="openForecastDetail()">Forecast detail</button>')
     && !html.includes('id="tab-detail" onclick="showDrawerTab(\'detail\')"')
     && (html.match(/openForecastDetail\(\)/g) || []).length >= 3);
  const ofd = fnSrc(/async function openForecastDetail\(\)\{[\s\S]*?\n    \}/);
  ok("A: the function is in the page, shows the tab first and asks for the table", !!ofd && ofd.indexOf("showDrawerTab('detail')") < ofd.indexOf("await fetchMatrix('t')"));
  const run = async (routes, picked) => {
    const box = { innerHTML: "" }; let tab = null;
    const f = new Function("showDrawerTab", "document", "fetchMatrix", "materialColorMap", "monthLabel", "selectedRouteId",
                           ofd + "\nreturn openForecastDetail;")(t => { tab = t; }, { getElementById: () => box }, async () => ({ routes, from: 1, to: 3 }), mat2, i => "M" + i, picked);
    await f(); return { html: box.innerHTML, tab };
  };
  const mat2 = (routes) => mat(Array.from(new Set(routes.map(r => r.material_type || "—"))));
  const R = [{ route_id: "R019", material_type: "Soil", monthly: { 1: 100 }, total: 900 }, { route_id: "R050", material_type: "Soil", monthly: { 1: 800 }, total: 800 },
             { route_id: "R050", material_type: "Stone", monthly: { 2: 50 }, total: 50 }, { route_id: "R032", material_type: "Sand", monthly: { 3: 5 }, total: 5 }];
  const ids = (h) => (h.match(/<\/span>(R\d+)<\/td>/g) || []).map(x => x.replace(/<\/span>|<\/td>/g, ""));
  {
    const a = await run(R.map(r => ({ ...r })), "R050");
    ok("⭐ A (run): a picked route's lines (one per material) come FIRST and are tinted; the others keep their order (sorted by total)",
       ids(a.html).join() === "R050,R050,R019,R032" && (a.html.match(/<tr class="fc-picked">/g) || []).length === 2 && a.tab === "detail");
    const b = await run(R.map(r => ({ ...r })), null);
    ok("A (run): nothing picked = today's table exactly: same order, no tint", ids(b.html).join() === "R019,R050,R050,R032" && !b.html.includes("fc-picked"));
    const c = await run(R.map(r => ({ ...r })), " r050 ");
    ok("A (run): the pick is matched without regard to case or spaces (the map lowercases ids to compare)", ids(c.html).join() === "R050,R050,R019,R032");
    ok("A (run): the heading, the window line ('4 route(s) · sorted by total'), the columns and the totals are untouched",
       a.html.includes("Approved forecast — tonnes of material by month") && a.html.includes("4 route(s) · sorted by total") && a.html.includes("<th>Route</th><th>M1</th><th>M2</th><th>M3</th><th>Total</th>")
       && a.html.includes("<td><b>800</b></td>"));
  }
  ok("⭐ A: a route picked while the Forecast detail tab is open re-reads the table (the pick follows), only with the drawer open on that tab",
     html.includes("const dr = document.getElementById('route-drawer'); if (drawerTab === 'detail' && dr && dr.classList.contains('open') && typeof openForecastDetail === 'function') openForecastDetail();"));
  ok("A: the tint has a light and a Dark look (the first column is sticky and has its own background, so it is named)",
     html.includes("table.fc-matrix tr.fc-picked td, table.fc-matrix tr.fc-picked td:first-child{ background:#EFF6FF; }")
     && html.includes('html[data-look="dark"] table.fc-matrix tr.fc-picked td, html[data-look="dark"] table.fc-matrix tr.fc-picked td:first-child{ background:rgba(37,99,235,.22); }'));

  // ---------- R1: the road card's row buttons ----------
  const pick = fnSrc(/function secselPickRow\(rid, kind\) \{[\s\S]*?\n    \}/);
  ok("⭐ R1: secselPickRow is in the page", !!pick);
  const mk = (withRoadAt, area) => {
    const calls = { sel: [], redraw: 0, redrawArea: 0, focus: [] };
    const sc = { scrollTop: 137 };
    const btns = ["R1", "R2", "R3"].map(id => ({ dataset: { rid: id }, focus: () => calls.focus.push(id) }));
    const el = { querySelector: () => sc, querySelectorAll: () => btns };
    const SECSEL = { roadAt: withRoadAt ? { clicked: "R1" } : null, area: area ? [0, 0, 1, 1] : null, areaPick: null, roadPopup: { getElement: () => el } };
    const f = new Function("SECSEL", "SHEET", "selectRoute", "redrawRoadCard", "redrawAreaCard", "document", pick + "\nreturn secselPickRow;")(
      SECSEL, { card: null }, id => calls.sel.push(id), () => { calls.redraw++; sc.scrollTop = 0; }, () => { calls.redrawArea++; sc.scrollTop = 0; }, { getElementById: () => el });
    return { f, SECSEL, calls, sc };
  };
  {
    const t = mk(true); t.f("R3", "road");
    ok("⭐ R1 (run): a click on R3's number makes R3 the card's picked route, lights it on the map (selectRoute, as a picked route is), and draws the card again once",
       t.SECSEL.roadAt.clicked === "R3" && t.calls.sel.join() === "R3" && t.calls.redraw === 1 && t.calls.redrawArea === 0);
    ok("⭐ R1 (run): the card STAYS open (nothing closes the popup) and the table keeps its scroll (137) and the keyboard stays on R3's button after the card is drawn again",
       t.sc.scrollTop === 137 && t.calls.focus.join() === "R3" && !/roadPopup\s*\.remove|closePopup/.test(pick));
    const n = mk(false); n.f("R3", "road");
    ok("R1 (run): with no road card open nothing happens; an empty id too", n.calls.sel.length === 0 && n.calls.redraw === 0 && (() => { const e = mk(true); e.f("", "road"); return e.calls.sel.length === 0; })());
    const a = mk(false, true); a.f("R2", "area");
    ok("⭐ frame 8 (run): on the AREA card a click picks the route for the area (areaPick), lights the whole route, and draws the AREA card again (the road card is left alone)",
       a.SECSEL.areaPick === "R2" && a.calls.sel.join() === "R2" && a.calls.redrawArea === 1 && a.calls.redraw === 0 && a.sc.scrollTop === 137 && a.calls.focus.join() === "R2");
    const a0 = mk(true, false); a0.f("R2", "area");
    ok("frame 8 (run): no area drawn = nothing happens on an area click", a0.calls.sel.length === 0 && a0.SECSEL.areaPick === null);
  }
  // ---------- frames 6 and 7: closing the card, and the month moving ----------
  const drop = fnSrc(/function secselDropPick\(\) \{[\s\S]*?\n    \}/), keep = fnSrc(/function secselKeepPick\(was, now, area\) \{[\s\S]*?\n    \}/);
  ok("⭐ frame 6/7: secselDropPick and secselKeepPick are in the page", !!drop && !!keep);
  {
    const mkDrop = (drawerOpen) => { const c = { cleared: 0 }; const f = new Function("document", "clearSelection", drop + "\nreturn secselDropPick;")({ getElementById: () => ({ classList: { contains: () => drawerOpen } }) }, () => c.cleared++); return { f, c }; };
    const d1 = mkDrop(false); d1.f(); const d2 = mkDrop(true); d2.f();
    ok("⭐ frame 6 (run): closing the card clears the light and the pick, EXCEPT while a route's panel is open (that route stays lit, as today)", d1.c.cleared === 1 && d2.c.cleared === 0);
    const mkKeep = (road, area) => { const c = { dropped: 0 }; const SECSEL = { roadAt: road ? { clicked: road } : null, areaPick: area || null };
      const f = new Function("SECSEL", "secselDropPick", keep + "\nreturn secselKeepPick;")(SECSEL, () => c.dropped++); return { f, c, SECSEL }; };
    const was = { month: 22 }, nowHas = { month: 23, routes: [{ route_id: "R49" }, { route_id: "R50" }] }, nowNot = { month: 23, routes: [{ route_id: "R50" }] };
    let k = mkKeep("R49"); k.f(was, nowHas, false);
    ok("⭐ frame 7 (run): the month moved and the picked route is still listed: it stays picked, tinted and lit", k.SECSEL.roadAt.clicked === "R49" && k.c.dropped === 0);
    k = mkKeep("R49"); k.f(was, nowNot, false);
    ok("⭐ frame 7 (run): the picked route has no loads that month (not listed): the pick, its tint and its light go", k.SECSEL.roadAt.clicked === null && k.c.dropped === 1);
    k = mkKeep(null, "R49"); k.f(was, nowNot, true);
    ok("frame 7 (run): the same on the area card (areaPick)", k.SECSEL.areaPick === null && k.c.dropped === 1);
    k = mkKeep("R49"); k.f({ month: 23, loading: true }, nowNot, false); const k2 = mkKeep("R49"); k2.f({ month: 23 }, nowNot, false); const k3 = mkKeep("R49"); k3.f(null, nowNot, false);
    ok("frame 7 (run): only a month MOVE drops a pick: the first answer to a click (same month, or still loading), or nothing to compare with, leaves it (the 10 Nov 'no loads' line for a clicked idle route is untouched)",
       k.c.dropped === 0 && k2.c.dropped === 0 && k3.c.dropped === 0 && k.SECSEL.roadAt.clicked === "R49");
  }
  ok("⭐ frame 6 (source): the road card's x drops the pick (not the card replaced by a new click, not the card closed to open a route's panel); the area's x / Clear the area drops it; the road card reload and the area reload ask secselKeepPick",
     html.includes("pop.on('close', () => { if (SECSEL.roadPopup === pop) { SECSEL.roadPopup = null; SECSEL.roadAt = null; SECSEL.roadKey = ''; secselDropPick(); } });")
     && html.includes("if (kind !== 'area' && SECSEL.roadPopup) { const pp = SECSEL.roadPopup; SECSEL.roadPopup = null; SECSEL.roadAt = null; SECSEL.roadKey = ''; try { pp.remove(); } catch (e) {} }")
     && html.includes("if (picked) secselDropPick();") && html.includes("secselKeepPick(was, j, false); redrawRoadCard();") && html.includes("secselKeepPick(was, j, true); redrawAreaCard();")
     && html.includes("SECSEL.area = box; SECSEL.areaPick = null;"));
  ok("⭐ R1: the row button is 44 px tall at least, fills its cell, and has a visible keyboard focus",
     /\.secsel-rid-btn\{[^}]*min-width:44px; min-height:44px;/.test(html) && /table\.secsel-table td\.secsel-rid\{ padding:0; \}/.test(html)
     && /\.secsel-rid-btn:focus-visible\{ outline:2px solid #1D4ED8;/.test(html)
     && html.includes('html[data-look="dark"] .secsel-rid-btn:focus-visible{ outline-color:#8FB3F5; }'));
  ok("R1: the phone's sheet draws the same card (roadCardHTML) and the same button (its onclick is in the HTML, so the sheet needs nothing extra); Dark: the tint is the existing one",
     html.includes("box.innerHTML = sc === 'road' ? roadCardHTML() +") && html.includes('html[data-look="dark"] table.secsel-table tr.secsel-clicked td{ background:rgba(37,99,235,.22); }'));
  ok("⭐ A + R1: technical T1 says what the tab and the row buttons do, and that the card stays open",
     guide.includes('id="t1-pick-route"') && guide.includes("<code>secselPickRow</code>") && guide.includes("<code>openForecastDetail</code>") && guide.includes("fc-picked") && guide.includes("stays open"));
  for (const f of fail) console.log("  FAIL: " + f);
  console.log(`${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
