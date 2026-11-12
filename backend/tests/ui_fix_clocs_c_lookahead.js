/*
 * ui_fix_clocs_c_lookahead.js — CLOCS "Everything left" cards, group C, branch claude/clocs-c-lookahead (11 Nov 2026,
 * John's yes: "Yes, as recommended").
 *
 *   C-F4  A "Day sheet ▾" menu on the desk Look-ahead's Commit toolbar (the week's weekdays, today first; the phone's
 *         address); the Lorry plan's trip blocks show their route code whole, in white, on a fill deep enough for it
 *         (the shared .row-menu summary rule made each trip 32 px wide and grey: "R02" on dark blue).
 *   C-F6  A trip is dragged only after "Move trips" (then "Done"); its menu moves it either way.
 *   C-F7  The Lorry plan opens on today (the Look-ahead's own today; the read carries none, so it opened on Monday).
 *   C-F10 The Account opens on Tonnes; its money columns behind "Show Tonnes · Cost" (remembered in this browser).
 *   C-F2  (the screen half) the Account's line names the lorry in full ("Artic Tipper (44t)"), not "Tipper (44t)".
 *
 * Source checks, plus lpDeep / lpLum run for real (transpiled out of the page). dom_frontend.js drives the Lorry plan's
 * Move trips and today's chip; render_frontend.js renders the Account's two views. Needs typescript through NODE_PATH.
 *
 * WHAT THIS DOES NOT PROVE: how the blocks look in a browser (the container query hides a code under 38 px: checked by
 * eye in Chrome), and that the Day sheet downloads (the address is the phone's, tested in test_lookahead.py).
 */
const fs = require("fs");
const path = require("path");
let ts;
try { ts = require("typescript"); } catch (e) { console.log("ui_fix_clocs_c_lookahead.js: SKIPPED — typescript not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const css = html.slice(0, html.indexOf("</style>"));
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const la = between("function LookAhead({", "\nfunction CommitMap(");
const lp = between("function LorryPlan({", "\n// 10 Nov 2026 (UI critique, 16 Oct item 33");
const trip = between("function LpTrip({", "\nfunction LorryPlanRow(");
const row = between("function LorryPlanRow({", "\nfunction LorryPlan(");
const dsm = between("function DaySheetMenu({", "\n}\n");
const acct = la.slice(la.indexOf(') : view === "account" ? ('), la.indexOf("{/* 10 Sep: what came OUT of each stockpile"));

// ------------------------------------------------------------------ C-F4: the Day sheet menu
ok("⭐ C-F4: the Commit toolbar carries 'Day sheet ▾' between PDF and Supplier orders, given the week's days and today",
   la.includes("<DaySheetMenu bucket={bucket} dates={dates} today={today} disabled={!!busy || !lines.length} />\n            <SupplierOrdersMenu")
   && la.indexOf("<DaySheetMenu") > la.indexOf(">PDF</button>"));
ok("C-F4: the menu lists today first, marked ', today', then the other weekdays in order; each fetches the phone's address",
   dsm.includes("const days = (dates || []).filter(d => d === today).concat((dates || []).filter(d => d !== today));")
   && dsm.includes("${API}/forecast-weeks/day-sheet?bucket=${bucket}&day=${iso}") && dsm.includes('${d === today ? ", today" : ""}')
   && dsm.includes(">Day sheet ▾</summary>") && dsm.includes('data-day-sheet={d}'));
ok("C-F4: the menu writes nothing (GET only) and a failure is one plain sentence (errSay)",
   !/method:\s*"POST"/.test(dsm) && dsm.includes('errSay("The day sheet did not download.", e)'));
ok("C-F4: the phone keeps its own Day sheet button", code.includes("const daySheet = async () => {") && code.includes("a.download = `day-sheet-${shown}.pdf`;"));

// ------------------------------------------------------------------ C-F4: readable route codes
ok("⭐ C-F4: a trip's block is its trip's full width, white, left-aligned (the .row-menu summary's 32 px and grey are overridden)",
   css.includes(".lp-trip summary.lp-blk{width:100%;justify-content:flex-start;color:#fff;font-weight:600;padding:0 4px}"));
ok("C-F4: a code is drawn whole or not at all: a container query on the block hides it under 38 px; its title / menu keep it",
   css.includes(".lp-blk:not(.is-break){container-type:inline-size}") && css.includes("@container (max-width:37px){ .lp-code{visibility:hidden} }")
   && trip.includes('<span className="lp-code">{b.route_id}</span></summary>') && row.includes('<span className="lp-code">{b.route_id}</span>'));
let F = {};
try {
  const grab = (start) => { const i = code.indexOf(start); return i < 0 ? "" : code.slice(i, code.indexOf("\n}\n", i) + 2); };
  const lum = code.slice(code.indexOf("function lpLum(h){"), code.indexOf("\n", code.indexOf("function lpLum(h){")));
  const js = ts.transpileModule(lum + "\n" + grab("function lpDeep(hex){") + "\nmodule.exports = { lpLum, lpDeep };",
    { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const m = { exports: {} };
  new Function("module", "exports", js)(m, m.exports);
  F = m.exports;
} catch (e) { fail.push("lpDeep / lpLum transpile and run  " + e.message); }
const contrast = (hex) => 1.05 / (F.lpLum(hex) + 0.05);
if (F.lpDeep) {
  const tokens = ["#E8590C", "#2563EB", "#0D9488", "#7C3AED", "#A07D34", "#E8681E", "#5B8FF0", "#13A193", "#9572EE", "#B48E3E",
    "#1D4ED8", "#0891B2", "#4F46E5", "#A8A29E", "#9A3412", "#BE185D", "#9D174D", "#0F766E", "#B45309", "#4338CA", "#C2410C"];
  const deep = tokens.map(F.lpDeep);
  ok("⭐ C-F4: every chart token and extra fill, deepened, carries white text at 4.5 : 1 or more (it was 3.4 on #E8590C)",
     deep.every(h => /^#[0-9a-f]{6}$/i.test(h) && contrast(h) >= 4.5) && contrast("#E8590C") < 4.5, JSON.stringify(deep));
  ok("C-F4: a fill already deep enough is left as it is; anything not #rrggbb is passed through",
     F.lpDeep("#1D4ED8") === "#1D4ED8" && F.lpDeep("#9D174D") === "#9D174D" && F.lpDeep("rgb(1,2,3)") === "rgb(1,2,3)" && F.lpDeep("") === "");
  const hue = (h) => { const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)); return r >= g && r >= b ? "r" : g >= b ? "g" : "b"; };
  ok("C-F4: deepening keeps the hue family (orange stays orange, teal stays teal)", tokens.every((t, i) => hue(t) === hue(deep[i])));
}
ok("C-F4: the Lorry plan's palette goes through lpDeep (the trips and their key share it)",
   code.includes('.concat(["#9D174D", "#0F766E", "#B45309", "#4338CA", "#C2410C"]).map(lpDeep);'));

// ------------------------------------------------------------------ C-F6: Move trips
ok("⭐ C-F6: a trip is draggable only while 'Move trips' is on (dnd.dragOn); a drag started otherwise is cancelled",
   trip.includes('draggable={dnd.dragOn ? "true" : "false"}') && trip.includes("if(!dnd.dragOn){ e.preventDefault(); return; }")
   && lp.includes("dragOn: canMove && moving && !busy,") && lp.includes("const [moving, setMoving] = useState(false);"));
ok("C-F6: the toggle sits before Driver sheets, for a planner / admin with trips on screen, reads 'Move trips' / 'Done', aria-pressed",
   lp.includes('{canMove && blocks.length > 0 && <button type="button" className="btn-sec" aria-pressed={moving ? "true" : "false"} onClick={() => setMoving(m => !m)} data-lp-move-toggle="1">{moving ? "Done" : "Move trips"}</button>}\n              <button type="button" className="btn-sec" onClick={() => download("pdf")}'));
ok("C-F6: the drag hint shows only while moving; the menu (keyboard) is there either way; the cursor is a pointer until then",
   lp.includes("{canMove && moving && blocks.length > 0 && <div className=\"clp-note\" data-lp-drag-hint=\"1\">")
   && trip.includes("const items = dnd.targets(trip);") && css.includes('.lp-trip:not([draggable="true"]) summary.lp-blk{cursor:pointer}'));

// ------------------------------------------------------------------ C-F7: today
ok("⭐ C-F7: the Look-ahead passes its today to the Lorry plan, which opens on it when it is in the week, marked ', today'",
   la.includes("weekConfirmed={allConfirmed} today={today} />") && lp.includes("const todayIso = today || (data && data.today) || null;")
   && lp.includes("(days.includes(todayIso) ? todayIso : days[0])") && lp.includes('{lpDayWords(d)}{d === todayIso ? ", today" : ""}</button>'));

// ------------------------------------------------------------------ C-F10 + C-F2: the Account
ok("⭐ C-F10: the Account opens on Tonnes unless this browser chose Cost; the choice is remembered (modus_la_acct_show)",
   la.includes('localStorage.getItem("modus_la_acct_show") === "cost" ? "cost" : "tonnes"') && la.includes('localStorage.setItem("modus_la_acct_show", v)'));
ok("C-F10: 'Show Tonnes · Cost' above the table, the Commit view's switch look (unit-sw)",
   acct.includes('<div className="unit-sw mb-2" data-acct-show={acctShow}>') && acct.includes('[["tonnes", "Tonnes"], ["cost", "Cost"]]'));
const th = acct.slice(acct.indexOf("<thead"), acct.indexOf("</thead>"));
ok("⭐ C-F10: Tonnes shows Actual and Difference; Cost shows the four money columns; Line, Planned, Note and Action always",
   th.includes('{!acctCost && <th className="px-2 py-2 text-right font-semibold">Actual</th>}')
   && th.includes('{!acctCost && <th className="px-2 py-2 text-right font-semibold">Difference<InfoTip id="la.variance" /></th>}')
   && th.includes("{acctCost && <><th") && th.includes("{CUR()} var</th></>}")
   && (th.match(/<th /g) || []).length === 10 && th.includes(">Note</th>") && th.includes("la-pin\">Action"));
ok("C-F10: the cells follow the headings (the actual and difference cells, the four money cells, wrapped the same way)",
   acct.includes("{!acctCost && <td className=\"px-2 py-2 text-right\">") && acct.includes("{!acctCost && <td className=\"px-2 py-2 text-right tabular-nums font-medium whitespace-nowrap\" data-la-var=")
   && acct.includes("{acctCost && <><td className=\"px-2 py-2 text-right tabular-nums text-slate-600\">") && acct.includes("</td></>}"));
ok("⭐ C-F2: the Account's line names the lorry in full (vehLabel), not the chips' short form",
   acct.includes('<span>{r.material_type || "—"} · {vehLabel(r.vehicle_type) || "—"} · {r.status}</span>') && !acct.includes("vehShort(r.vehicle_type)"));

console.log(fail.length ? fail.map(f => "  FAIL: " + f).join("\n") : "");
console.log(`ui_fix_clocs_c_lookahead.js: ${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
