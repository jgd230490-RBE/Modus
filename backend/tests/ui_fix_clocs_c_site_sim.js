/*
 * ui_fix_clocs_c_site_sim.js — CLOCS "Everything left" cards, group C, branch claude/clocs-c-site-sim (11 Nov 2026,
 * John's yes: "Yes, as recommended").
 *
 *   C-F3  The Dashboard's Gate arrivals keeps the month picked, and the Simulation keeps its Month-scale month (Week /
 *         Day show the server's month and Month goes back): until sign-out, a reload or a new day. Never stored.
 *   C-I1  With no gate at the 85 % step in the month on screen, Gate arrivals says "Next queue likely: <month>, <gate> ·
 *         Show" (John's (a): the first month near capacity after it; past the last, the fullest). "Show" sets the
 *         month; the Simulation line follows, and "Open the Simulation" carries a picked month.
 *   C-F5  The holding area card names the sites it serves and "n at a time", says why it is quiet ("No lorry for these
 *         sites this day." / "None waited this day.") and leaves out the with / without fold when nothing was held or waited.
 *   C-F6  Ticking a site layout's "Show on the public map" asks first ("Show this layout on the public map?" / Cancel /
 *         Show it); unticking writes at once.
 *   C-F8  "Loading…" until the first answer, not the empty words: Data → Locations, Data → Zones (the sweep), the site
 *         layout card, the Dashboard's sites menu.
 *
 * Source checks, plus the page's own keptMonth / gaNextQueue / simHoldWords run for real (transpiled out of the page).
 * The server's months with a queue: test_clocs_c_queue.py. Needs typescript through NODE_PATH.
 *
 * WHAT THIS DOES NOT PROVE: the screens in a browser (the UI audit and the Chrome pictures do), two tabs open at once
 * (each keeps its own months), a touch screen.
 */
const fs = require("fs");
const path = require("path");
let ts;
try { ts = require("typescript"); } catch (e) { console.log("ui_fix_clocs_c_site_sim.js: SKIPPED — typescript not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const guide = read("frontend", "help", "index.html");
const tech = read("frontend", "help", "technical", "index.html");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const css = html.slice(0, html.indexOf("</style>"));
const between = (a, b) => { const i = code.indexOf(a), j = code.indexOf(b, i + 1); return i >= 0 && j > i ? code.slice(i, j) : ""; };
const panel = between("function GateArrivalsPanel({", "\n// ---- 11 Oct 2026: the carbon target");
const dash = between("function Dashboard({", "\nfunction DashboardToday(");
const sim = between("function SimulationPage({", "\n// the phone's Simulation:");
const simLine = between("function SimDashLine({", "\n// ---- 17 Oct 2026: the Simulation on the BIG SCREEN");
const layCard = between("function SiteLayoutCard({", "\nfunction ");

// ---------------------------------------------------------------- the page's own functions, run
const grabTo = (start, end) => { const i = code.indexOf(start); return i < 0 ? "" : code.slice(i, code.indexOf(end, i) + end.length); };
const grabLine = (start) => { const i = code.indexOf(start); return i < 0 ? "" : code.slice(i, code.indexOf("\n", i)); };
const src = [grabLine("const KEPT_MONTH = {};"), grabLine("const keptMonth = (k) =>"), grabLine("const keepMonth = (k, m) =>"),
  grabLine("const forgetKeptMonths = () =>"), grabTo("const gaNextQueue = (q, month, sites) => {", "\n};\n"),
  grabTo("const simHoldServedIn = (h, D) => {", "; };\n"), grabTo("function simHoldWords(h, D){", "\n}\n")].join("\n");
let F = {};
try {
  const js = ts.transpileModule(src + "\nmodule.exports = { KEPT_MONTH, keptMonth, keepMonth, forgetKeptMonths, gaNextQueue, simHoldWords };",
    { compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS } }).outputText;
  const m = { exports: {} };
  new Function("module", "exports", "simHM", js)(m, m.exports, (t) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.round(t % 60)).padStart(2, "0")}`);
  F = m.exports;
} catch (e) { fail.push("the page's small functions transpile and run  " + e.message); }

// ---------------------------------------------------------------- C-F3: the kept months
if (F.keptMonth) {
  const none = F.keptMonth("ga");
  F.keepMonth("ga", 31); F.keepMonth("sim", 29); F.keepMonth("x", 0);
  const a = F.keptMonth("ga"), b = F.keptMonth("sim"), z = F.keptMonth("x");
  F.KEPT_MONTH.ga.day = "Mon Jan 01 2001";                // yesterday's pick
  const stale = F.keptMonth("ga");
  F.forgetKeptMonths();
  ok("⭐ C-F3: a month picked is kept (Gate arrivals and the Simulation each their own); none before; a month 0 is not kept",
     none === null && a === 31 && b === 29 && z === null, JSON.stringify({ none, a, b, z }));
  ok("C-F3: a month kept on another day is not used (a new day starts on this month); sign-out forgets them all",
     stale === null && F.keptMonth("sim") === null && Object.keys(F.KEPT_MONTH).length === 0);
}
ok("C-F3: kept in the page only — never localStorage / sessionStorage / the address (D86)",
   !/(localStorage|sessionStorage|location\.hash)[^\n]*(KEPT_MONTH|keepMonth)/.test(code) && !/KEPT_MONTH[^\n]*(localStorage|sessionStorage)/.test(code));
ok("⭐ C-F3: the Dashboard opens Gate arrivals on the kept month, else this month; picking one keeps it",
   dash.includes('useState(() => (initialGates && initialGates.month) || keptMonth("ga") || gaMonthToday(months));')
   && dash.includes('const setGaMonth = (m) => { keepMonth("ga", m); setGaMonthRaw(m); };'));
ok("⭐ C-F3: the Simulation opens on its kept month without the busiest read (ready at once); else the busiest month as before",
   sim.includes('const kept0 = initial ? null : keptMonth("sim");') && sim.includes("|| kept0 || gaMonthToday(months));")
   && sim.includes("const [ready, setReady] = useState(!!initial || !!kept0);") && sim.includes("fetch(`${API}/sim/busiest-month`)"));
ok("⭐ C-F3: the Month scale's month is kept; Week / Day leave it be, and pressing Month goes back to it (Jul 2028, not the week's Nov 2026)",
   sim.includes('useEffect(() => { if(ready && sc.scale === "month") keepMonth("sim", month); }, [month, sc.scale, ready]);')
   && sim.includes('if(v === "month" && keptMonth("sim")) setMonth(keptMonth("sim"));'));
ok("C-F3: sign-out forgets the kept months (the next person starts on this month)",
   between("const signOut = () => {", "\n  };").includes("forgetKeptMonths();"));
ok("C-F3 / C-I1: 'Open the Simulation' carries the line's month only when it was picked on Gate arrivals (untouched: the busiest month)",
   simLine.includes('onClick={() => { if(keptMonth("ga") === month) keepMonth("sim", month); if(onOpen) onOpen("simulation"); }}>Open the Simulation</button>'));

// ---------------------------------------------------------------- C-I1: next queue likely
if (F.gaNextQueue) {
  const g = (loc, pct, flag) => ({ gate_id: loc + "-g", gate_name: "Gate", location_id: loc, location_name: loc === "P" ? "Wolds Link Asphalt Plant" : "Tilton Compound", capacity_pct: pct, flag });
  const q = { near_pct: 85, months: [
    { month: 5, label: "May 2026", gates: [g("T", 88, "amber")] },
    { month: 29, label: "May 2028", gates: [g("P", 95, "amber")] },
    { month: 31, label: "Jul 2028", gates: [g("P", 109, "red"), g("T", 86, "amber")] },
    { month: 41, label: "May 2029", gates: [g("P", 87, "amber")] }] };
  const n11 = F.gaNextQueue(q, 11), n29 = F.gaNextQueue(q, 30), past = F.gaNextQueue(q, 50), siteT = F.gaNextQueue(q, 11, ["T"]);
  ok("⭐ C-I1 (John's (a)): from Nov 2026 the next queue is the first month near capacity after it, May 2028 at the plant",
     n11 && n11.month === 29 && n11.gates[0].location_name === "Wolds Link Asphalt Plant", JSON.stringify(n11 && n11.month));
  ok("C-I1: from Jun 2028 the next is Jul 2028; past the plan's last queue, the fullest month with one (Jul 2028, 109 %)",
     n29 && n29.month === 31 && past && past.month === 31, JSON.stringify([n29 && n29.month, past && past.month]));
  ok("C-I1: with sites picked, only their gates count (Tilton: Jul 2028, the plant's month May 2028 skipped)",
     siteT && siteT.month === 31 && siteT.gates.length === 1 && siteT.gates[0].location_id === "T", JSON.stringify(siteT));
  ok("C-I1: no queue in the plan (or no reply) gives no line", F.gaNextQueue({ months: [] }, 11) === null && F.gaNextQueue(null, 11) === null
     && F.gaNextQueue(q, 11, ["X"]) === null);
}
ok("⭐ C-I1: the line shows only when no gate on screen is at the 85 % step; 'Show' sets the month (kept, the Simulation line follows)",
   panel.includes("const nextQ = (nOverG || nNearG) ? null : gaNextQueue(queue, month, sites);")
   && panel.includes('<span className="ga-next" data-ga-next={nextQ.month}>Next queue likely: {nextQ.label}, {simGateName(nextQ.gates[0])} · <button type="button" className="link-btn" onClick={() => onMonth(nextQ.month)}>Show</button></span>')
   && dash.includes("<SimDashLine ga={gaShown} month={gaMonth} months={months} onOpen={onOpen} />"));
ok("C-I1: in the desk head and the phone head (after the status words), and under an empty month's message",
   (panel.match(/<\/span>\n\s*\{nextLine\}/g) || []).length === 2 && panel.includes('{state === "none" && nextLine && <div className="ga-head">{nextLine}</div>}'));
ok("C-I1: the Dashboard reads /gates/queue-months once (and on its tick), not on the big screen; a failed read leaves the line out",
   dash.includes("fetch(`${API}/gates/queue-months`).then(okJSON).then(j => { if(live) setGaQueue(j); }).catch(() => {});")
   && dash.includes("if(initialGates || wall) return;") && (dash.match(/gates\/queue-months/g) || []).length === 1
   && dash.includes("queue={gaQueue} sites={sites} />"));
ok("C-I1: 'Show' is a 24 px target in 13 px words (WCAG 2.2)", css.includes(".ga-next .link-btn{display:inline-block;min-height:24px;line-height:24px;padding:0 4px;font-size:13px;}"));
ok("C-I1: the technical guide names the read; the screen names no back end", tech.includes("<code>GET /api/gates/queue-months</code>")
   && !/queue-months|85 %|capacity_pct/.test(panel.slice(panel.indexOf("const nextLine"), panel.indexOf("// 17 Oct 2026: every gate has clock hours"))));

// ---------------------------------------------------------------- C-F5: the holding area card
if (F.simHoldWords) {
  const h = { served: [{ id: "T1", name: "Tilton Compound" }, { id: "T2", name: "Tilton Viaduct site" }], call: 2, held: 0, most: 0 };
  const dayNone = { gates: [{ location_id: "P", arrivals: 164 }, { location_id: "T1", arrivals: 0 }] };
  const dayStraight = { gates: [{ location_id: "T2", arrivals: 3 }] };
  ok("⭐ C-F5: no lorry for the sites it serves: 'No lorry for these sites this day.'; theirs came straight in: 'None waited this day.'",
     F.simHoldWords(h, dayNone) === "No lorry for these sites this day." && F.simHoldWords(h, dayStraight) === "None waited this day.");
  ok("C-F5: a day with lorries through it keeps its words", F.simHoldWords({ ...h, held: 5 }, dayNone) === "5 lorries passed through · none waited."
     && F.simHoldWords({ ...h, held: 7, most: 3, most_at: 600, spaces: 4 }, dayNone) === "7 lorries waited here · most 3 at once at 10:00, of 4 spaces.");
}
const holdCard = sim.length ? code.slice(code.indexOf("{(D.holding || []).filter(h => h.on).map(h => { const w = h.with || {}"), code.indexOf("{site\n            ? <div className=\"sim-card\" data-sim-stations-now=\"1\">")) : "";
ok("⭐ C-F5: the card names the sites it serves and how many are called forward at a time ('For A, B · 2 at a time')",
   holdCard.includes('<div className="ct-note" data-sim-hold-for="1">For {h.served.map(s => s.name).join(", ")} · {h.call} at a time</div>'));
ok("⭐ C-F5: the with / without fold is left out when nothing was held and nobody waited either way; otherwise as before",
   holdCard.includes("const still = !h.held && !(w.site_most || wo.site_most || w.gate_most || wo.gate_most) && !mins(w) && !mins(wo);")
   && holdCard.includes('{!still && <details className="sim-hold-fold" open={!!h.most}><summary>With and without the holding area</summary>')
   && holdCard.includes("</details>}"));
ok("C-F5: the card and the phone read the day's gates for the words; 'No lorry called off here this day.' is gone",
   (code.match(/\{simHoldWords\(h, D\)\}/g) || []).length === 2 && !code.includes("No lorry called off here this day."));
ok("C-F5: the user guide's Simulation section says it in one sentence",
   guide.includes("The card names the sites it serves; on a day with no lorry for them it says so and leaves the comparison out."));

// ---------------------------------------------------------------- C-F6: the public map asks first
ok("⭐ C-F6: ticking 'Show on the public map' writes nothing: it opens the question; unticking writes at once (taking it off)",
   layCard.includes('onChange={e => { if(e.target.checked) setAskPub(true); else if(askPub) setAskPub(false); else setPublic(false); }}')
   && layCard.includes("checked={!!lay.public || askPub}"));
const ask = layCard.slice(layCard.indexOf("{askPub && <div"), layCard.indexOf("</div>}", layCard.indexOf("{askPub && <div")));
ok("⭐ C-F6: the question as drawn: 'Show this layout on the public map?' / 'Anyone with the map's link will see it.' / Cancel / Show it",
   ask.includes(">Show this layout on the public map?</p>") && ask.includes(">Anyone with the map's link will see it.</p>")
   && ask.includes('onClick={() => setAskPub(false)} data-site-layout-ask-no="1">Cancel</button>')
   && ask.includes('onClick={() => { setAskPub(false); setPublic(true); }} data-site-layout-ask-yes="1">Show it</button>'));
ok("C-F6: 'Show it' is the primary (the action fill, white words); Cancel the secondary; the group is named by its question",
   /className="[^"]*text-white[^"]*" style=\{\{ background: "var\(--action\)" \}\}\s*onClick=\{\(\) => \{ setAskPub\(false\); setPublic\(true\); \}\}/.test(ask)
   && ask.includes('className="btn-sec"') && ask.includes('role="group" aria-labelledby="sl-ask-pub"') && ask.includes('id="sl-ask-pub"'));
ok("C-F6: another place, the question goes (it never carries over)", layCard.includes("setLayIn(false); setAskPub(false);"));

// ---------------------------------------------------------------- C-F8: "Loading…" before the first answer
ok("⭐ C-F8: Data → Locations: 'Loading…' until the first answer (a failed read shows the empty words as before)",
   code.includes('{!locs.length && !locsIn && <tr data-locs-loading="1"><td colSpan="8" className="px-3 py-6 text-center text-slate-500">Loading…</td></tr>}')
   && code.includes('{!locs.length && locsIn && <tr data-locs-empty="1">') && code.includes("const setLocs = (v) => { setLocsIn(true); setLocsRaw(v); };")
   && code.includes("}).catch(() => { setLocsIn(true); });"));
ok("⭐ C-F8: the site layout card: 'Loading…' until the layout's answer, then 'No layout yet.' only if it has none; a new place starts again",
   layCard.includes('{layIn ? "No layout yet." : "Loading…"}') && layCard.includes("setLayIn(true);\n  };") && layCard.includes("setLayIn(false); setAskPub(false);"));
ok("C-F8 (the sweep): Data → Zones and the Dashboard's sites menu the same way",
   code.includes('{!zoneList.length && !zonesIn && <tr data-zones-loading="1">') && code.includes("reloadZones().catch(() => setZoneList([])).finally(() => setZonesIn(true));")
   && code.includes('{!locList && <div className="sites-empty" data-sites-loading="1">Loading…</div>}')
   && code.includes('{locList && locList.length === 0 && <div className="sites-empty">No locations yet.</div>}'));
ok("🔴 C-F8: no empty message left on these four that shows before the first answer",
   !code.includes("{!locs.length && <tr") && !code.includes("{!zoneList.length && <tr") && !code.includes("{(locList || []).length === 0 && <div")
   && !layCard.includes('<p className="text-[13px] text-slate-500 mt-1">No layout yet.</p>'));

console.log(fail.length ? fail.map(f => "  FAIL: " + f).join("\n") : "");
console.log(`ui_fix_clocs_c_site_sim.js: ${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
