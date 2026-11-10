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
    const list = ph.el.querySelector("[data-ga-list]");
    const lis = [...ph.el.querySelectorAll("[data-ga-li]")];
    ok("PHONE GATES: a list, no chart and no key — one row a gate that has arrivals (the gate with 0 is left out)",
       !!list && !ph.el.querySelector("[data-ga-chart]") && !ph.el.querySelector("canvas") && !ph.el.querySelector(".ga-key") && lis.length === 4,
       `rows ${lis.length}`);
    ok("PHONE GATES: the fullest gate first, by its share of its own capacity (no capacity last)",
       lis.map(l => l.getAttribute("data-ga-li")).join("|") === "903|902|901|904", lis.map(l => l.getAttribute("data-ga-li")).join("|"));
    const t = (l) => l.textContent.replace(/\s+/g, " ");
    ok("PHONE GATES: the whole name is printed, never cut (the long name, then the gate under it)",
       t(lis[2]).includes("Melton Compound gate with a very long whole name") && t(lis[2]).includes("North weighbridge (in)")
       && !/…|\.\.\./.test(t(lis[2])));
    ok("PHONE GATES: lorries a day and the share of capacity on every row; amber says queue likely, red says over capacity; a gate with no check-in says so",
       t(lis[2]).includes("27.9 a day · 82 %") && !/queue likely|over capacity/.test(t(lis[2]))
       && t(lis[1]).includes("31.5 a day · 93 % · queue likely") && t(lis[0]).includes("18.2 a day · 120 % · over capacity")
       && t(lis[3]).includes("9.0 a day · no check-in time typed"), lis.map(t).join(" || "));
    const bar = (l) => l.querySelector(".ga-pbar i");
    ok("PHONE GATES: a thin bar under each, as wide as the gate's own share (capped at 100 %), amber from the server's amber flag, red on red; none without a capacity",
       bar(lis[2]).style.width === "82%" && bar(lis[1]).style.width === "93%" && bar(lis[0]).style.width === "100%" && !bar(lis[3])
       && lis[0].classList.contains("ga-li-bad") && lis[1].classList.contains("ga-li-warn") && !lis[2].classList.contains("ga-li-warn") && !lis[2].classList.contains("ga-li-bad"));
    ok("PHONE GATES: the headline counts the red gates first", ph.el.querySelector(".ga-head-v").textContent === "1 gate over capacity");
    ok("PHONE GATES: the Gate by gate detail table is still there under the list", !!ph.el.querySelector("[data-ga-table]"));
    ph.done();

    const dk = mount(w.GateArrivalsPanel, { ...props, phone: false });
    ok("DESK GATES: unchanged — the chart and its key, no list", !!dk.el.querySelector("[data-ga-chart]") && !!dk.el.querySelector(".ga-key") && !dk.el.querySelector("[data-ga-list]"));
    dk.done();
    const dk2 = mount(w.GateArrivalsPanel, props);
    ok("DESK GATES: with no `phone` prop the panel is the desk panel", !!dk2.el.querySelector("[data-ga-chart]") && !dk2.el.querySelector("[data-ga-list]"));
    dk2.done();

    // ---- source: the CSS and the wiring ---------------------------------------------------------------------
    const css = (sel) => { const m = html.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
    ok("PHONE GATES: a name wraps (overflow-wrap) and the bar is 6 px high; type is 13 px or more; the amber / red words are the text-grade colours",
       /overflow-wrap:anywhere/.test(css(".ga-li-name")) && /height:6px/.test(css(".ga-pbar")) && /font-size:13px/.test(css(".ga-li-fig")) && /font-size:13px/.test(css(".ga-li-name small"))
       && /var\(--warn-text\)/.test(css(".ga-li-warn .ga-li-fig")) && /var\(--bad-text\)/.test(css(".ga-li-bad .ga-li-fig"))
       && /var\(--gold\)/.test(css(".ga-li-warn .ga-pbar i")) && /var\(--red\)/.test(css(".ga-li-bad .ga-pbar i")));
    ok("PHONE GATES: the Dashboard hands its `phone` to the panel", html.includes("sited={sites.length ? sitesWords(sites, locList) : \"\"} phone={!!phone} onOpen={canApprove ? onOpen : null} />"));

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
