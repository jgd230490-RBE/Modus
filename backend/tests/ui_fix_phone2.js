/*
 * ui_fix_phone2.js — UI fix "phone 2" (9 Nov 2026 critique, wave 1): the phone's Gate arrivals as a plain list, and the
 * guide strip placed on a phone. Its own file (parallel UI branches never meet at the end of parse_frontend.js).
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_phone2.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const FIX = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", f), "utf8"));

const dom = new JSDOM(`<!doctype html><html><head><meta name="theme-color" content="#1F2024"></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__N = { NAV, DESK_LINE, PHONE_READ_PAGES, PHONE_PAGES };");

const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };

(async () => {
  try {
    // ---- the phone's Gate arrivals: a plain list ----------------------------------------------------------
    const GAF = FIX("gate_arrivals.json");
    const g0 = GAF.gates;
    const gates = [
      { ...g0[0], gate_id: 901, location_name: "Melton Compound gate with a very long whole name", gate_name: "North weighbridge (in)", arrivals_per_day: 27.9, capacity_pct: 82, flag: null },
      { ...g0[0], gate_id: 902, location_name: "Harborough Compound", gate_name: "A6 entrance (in)", arrivals_per_day: 31.5, capacity_pct: 93, flag: "amber" },
      { ...g0[1], gate_id: 903, location_name: "Kilby Ridge Quarry", gate_name: "Weighbridge (in)", arrivals_per_day: 18.2, capacity_pct: 120, flag: "red" },
      { ...g0[2], gate_id: 904, location_name: "North stockpile", gate_name: "Stockpile gate", arrivals_per_day: 9, capacity_per_day: null, capacity_pct: null, flag: null },
      { ...g0[2], gate_id: 905, location_name: "Quiet gate", gate_name: "Nothing", arrivals_per_day: 0, capacity_pct: 0, flag: null },
    ];
    const ga = { ...GAF, gates };
    const props = { ga, err: false, month: ga.month, months: { start_year: 2026, count: 60 }, onMonth(){} };
    const ph = mount(w.GateArrivalsPanel, { ...props, phone: true });
    // REVERSED 24 Nov 2026 (Dashboard rethink A2, gate dials): the phone's plain list became the same dials as the desk, two across (John: "a gauge for each
    // gate"; the brief: "a phone two across"). Each check below is the list's check turned round.
    const list = ph.el.querySelector("ul.ga-dials");
    const lis = [...ph.el.querySelectorAll("[data-ga-li]")];
    ok("PHONE GATES: REVERSED 24 Nov 2026 (Dashboard rethink A2, gate dials) — dials two across (ga-dials-phone), no chart canvas, no old list; one dial a gate that has arrivals (the gate with 0 is left out)",
       !!list && list.classList.contains("ga-dials-phone") && !ph.el.querySelector("[data-ga-list]") && !ph.el.querySelector("[data-ga-chart]") && !ph.el.querySelector("canvas")
       && !!ph.el.querySelector(".ga-key") && lis.length === 4, `dials ${lis.length}`);
    ok("PHONE GATES: the fullest gate first, by its share of its own capacity (no capacity last)",
       lis.map(l => l.getAttribute("data-ga-li")).join("|") === "903|902|901|904", lis.map(l => l.getAttribute("data-ga-li")).join("|"));
    const t = (l) => l.textContent.replace(/\s+/g, " ");
    ok("PHONE GATES: NARROWED 24 Nov 2026 (Dashboard rethink A2, gate dials) — the dial prints the place (the whole name in its title, never lost); two dials of one place print the gate",
       lis[2].querySelector(".ga-d-name").getAttribute("title") === "Melton Compound gate with a very long whole name, North weighbridge (in)"
       && t(lis[2]).includes("Melton Compound gate with a very long whole name"));
    ok("PHONE GATES: NARROWED 24 Nov 2026 (Dashboard rethink A2, gate dials) — the share in the middle and 'N a day of C' on every dial; amber says queue likely, red over capacity, a fine gate no word; a gate with no check-in says so",
       t(lis[2]).includes("82 %") && !/Queue likely|Over capacity/.test(t(lis[2]))
       && t(lis[1]).includes("93 %") && t(lis[1]).includes("Queue likely") && t(lis[0]).includes("120 %") && t(lis[0]).includes("Over capacity")
       && /27\.9 a day of \d/.test(t(lis[2])) && t(lis[3]).includes("9.0 a day") && t(lis[3]).includes("No check-in time typed") && t(lis[3]).includes("—"), lis.map(t).join(" || "));
    ok("PHONE GATES: REVERSED 24 Nov 2026 (Dashboard rethink A2, gate dials) — no thin bar; the arc's tone is the server's flag (bad on red, warn on amber, ok otherwise), the ring alone without a capacity",
       !ph.el.querySelector(".ga-pbar") && lis[0].getAttribute("data-ga-tone") === "bad" && lis[1].getAttribute("data-ga-tone") === "warn"
       && lis[2].getAttribute("data-ga-tone") === "ok" && lis[3].getAttribute("data-ga-tone") === "none" && !lis[3].querySelector(".ga-d-arc") && !!lis[2].querySelector(".ga-d-arc"));
    ok("PHONE GATES: the headline counts the red gates first", ph.el.querySelector(".ga-head-v").textContent === "1 gate over capacity");
    ok("PHONE GATES: the Gate by gate detail table is still there under the dials", !!ph.el.querySelector("[data-ga-table]"));
    ph.done();

    const dk = mount(w.GateArrivalsPanel, { ...props, phone: false });
    ok("DESK GATES: REVERSED 24 Nov 2026 (Dashboard rethink A2, gate dials) — the same dials, six across on a desk (no phone class), the key line, no chart, no list",
       !!dk.el.querySelector("[data-ga-dials]") && !dk.el.querySelector(".ga-dials-phone") && !!dk.el.querySelector(".ga-key") && !dk.el.querySelector("[data-ga-chart]") && !dk.el.querySelector("[data-ga-list]"));
    dk.done();
    const dk2 = mount(w.GateArrivalsPanel, props);
    ok("DESK GATES: with no `phone` prop the panel is the desk panel", !!dk2.el.querySelector("[data-ga-dials]") && !dk2.el.querySelector(".ga-dials-phone") && !dk2.el.querySelector("[data-ga-list]"));
    dk2.done();

    // ---- source: the CSS and the wiring ---------------------------------------------------------------------
    const css = (sel) => { const m = html.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
    ok("PHONE GATES: REVERSED 24 Nov 2026 (Dashboard rethink A2, gate dials) — the list's CSS is gone; the dials two across on a phone; a name cut with an ellipsis (its title holds it whole); 12 px type at least",
       !/\.ga-li-(name|fig|warn|bad)/.test(html.replace(/\.gw-cap\.ga-li-(warn|bad)/g, "")) && !/\.ga-list\{/.test(html)
       && /grid-template-columns:repeat\(2,/.test(css(".ga-dials-phone")) && /text-overflow:ellipsis/.test(css(".ga-d-name")) && /font-size:12px/.test(css(".ga-d-fig"))
       // REVERSED 24 Nov 2026 (own look, B1 stage 7): the bar is ink in every state (a small bar beside a status); kept for the
       // Look-ahead's GatesWeek, which still draws it
       && /var\(--ink\)/.test(css(".ga-pbar i")) && !/\.ga-li-(warn|bad) \.ga-pbar i\{/.test(html));
    ok("PHONE GATES: the Dashboard hands its `phone` to the panel", html.includes("sited={sites.length ? sitesWords(sites, locList) : \"\"} phone={!!phone} onOpen={canApprove ? onOpen : null} queue={gaQueue} sites={sites} />")   /* NARROWED 11 Nov 2026 (CLOCS idea C-I1) */);

    // ---- the guide strip on a phone ------------------------------------------------------------------------
    const gi = html.indexOf("const own = phone ? [] : stepsOf();");
    const gEff = gi > 0 ? html.slice(gi - 400, gi + 1800) : "";
    ok("GUIDE STRIP PHONE: the placement pass runs on a phone too (it sets the strip's left edge from the tab bar and lifts it clear of it); only the dots are left out",
       gi > 0 && gEff.includes("if(!hints || steps.length){ setDots([]); return; }") && gEff.includes("setRailRight(rr.height > rr.width ? Math.round(rr.right) : 0)")
       && gEff.includes("setStripBottom(b => (b === lift ? b : lift))") && !gEff.includes("phone){ setDots"));
    ok("GUIDE STRIP PHONE: the desk keeps its rail-wide start (240 px default) and the strip's own CSS is unchanged (13 px, max-width 100vw − 72)",
       html.includes("const [railRight, setRailRight] = useState(240);") && /\.guide-strip\{[^}]*max-width:calc\(100vw - 72px\)/.test(html));

    // ---- the desktop cards and the More sheet (10 Nov 2026, the part John approved from the mockup) -------------
    const NAVITEMS = w.__N.NAV.flatMap(g => g.items), DL = w.__N.DESK_LINE, READ = w.__N.PHONE_READ_PAGES, PP = w.__N.PHONE_PAGES;
    const deskIds = NAVITEMS.map(i => i.id).filter(id => !PP.includes(id) && !READ.includes(id));
    ok("DESK CARDS: every desk page has its own one-line purpose, all different, none with a back-end word or a decision code",
       deskIds.length >= 13 && deskIds.every(id => typeof DL[id] === "string" && DL[id].length > 8 && DL[id].length < 60) && new Set(deskIds.map(id => DL[id])).size === deskIds.length
       && !deskIds.some(id => /\b(API|endpoint|server|JSON|token|D\d\d)\b/.test(DL[id])), deskIds.join(","));
    let homed = 0;
    const leads = [];
    for (const id of deskIds) {
      const label = NAVITEMS.find(i => i.id === id).label;
      const d = mount(w.DeskOnly, { id, label, onHome(){ homed++; } });
      leads.push(d.el.querySelector(".do-lead").textContent);
      const txt = d.el.textContent;
      ok(`DESK CARD ${id}: its name, its own line, then one sentence naming the four phone pages and where to open it; no 'Open on a desktop to edit this'`,
         d.el.querySelector("h2").textContent === label && d.el.querySelector(".do-lead").textContent === DL[id]
         && txt.includes("Open it on a computer or a tablet. A phone reads the Dashboard, the Look-ahead, the Route map and the Simulation.") && !txt.includes("Open on a desktop to edit this"));
      if (id === deskIds[0]) { d.el.querySelector("button").dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }
      d.done();
    }
    ok("DESK CARDS: the nine-plus cards are not identical (every lead differs) and the button still goes to the Dashboard", new Set(leads).size === leads.length && homed === 1);

    const groups = w.__N.NAV;
    const pm = mount(w.PhoneMore, { groups, page: "dashboard", onPick(){}, onClose(){}, role: { role: "planner", label: "Planner", ipt: null }, who: "Sam", pending: 7, concernNew: 3 });
    const heads = [...pm.el.querySelectorAll("h3")].map(h => h.textContent);
    ok("MORE: two headings, 'Read here' (the Simulation) then 'Open on a computer or tablet'; no paragraph under them",
       heads.join("|") === "Read here|Open on a computer or tablet" && !pm.el.querySelector("#phone-more > p") && !/Made for a desktop|plan on a desktop|say so/.test(pm.el.textContent));
    ok("MORE: no count — 'waiting' and 'new' are gone even when the page is handed numbers; only the guide's 'new tab' note stays",
       !/\d+ waiting|\d+ new\b/.test(pm.el.textContent) && [...pm.el.querySelectorAll(".pm-note")].map(n => n.textContent).join("|") === "new tab");
    const items = [...pm.el.querySelectorAll("button.phone-more-item")];
    ok("MORE: the Simulation is in the ink weight, every desk page carries the plainer pm-desk class",
       !items.find(b => /Simulation/.test(b.textContent)).classList.contains("pm-desk") && items.filter(b => b.classList.contains("pm-desk")).length === items.length - 1 && items.length >= 14);
    pm.done();
    const tb = mount(w.PhoneTabs, { groups, page: "dashboard", onPick(){}, moreOpen: false, onMore(){}, pending: 5 });
    ok("MORE TAB: no red count on the More tab", !tb.el.querySelector(".rail-count") && tb.el.querySelectorAll(".phone-tab").length === 4);
    tb.done();
    ok("MORE: the pm-desk rule sits before the is-on rule (the open page still reads in the action colour) and uses the muted caption colour",
       html.indexOf(".phone-more-item.pm-desk{") > 0 && html.indexOf(".phone-more-item.pm-desk{") < html.indexOf(".phone-more-item.is-on{") && /var\(--muted\)/.test(css(".phone-more-item.pm-desk")));
  } catch (e) { ok("PHONE 2: the harness ran to the end", false, String(e && e.stack || e).slice(0, 600)); }
  console.log(`\n${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
})();
