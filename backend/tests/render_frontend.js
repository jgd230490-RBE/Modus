/*
 * 2.5b — RENDER the frontend, don't just grep it.
 *
 * WHY THIS EXISTS
 * ---------------
 * parse_frontend.js asserts at source level, which is right for "is this control really
 * gone" but cannot catch the failure 2.5b was most likely to introduce: a page in the
 * new rail that names a component that does not exist, or a component whose render path
 * reaches an identifier that was deleted with My submissions and Approvals. TypeScript
 * parses that happily; it only blows up when React tries to render it.
 *
 * So this evaluates the whole <script type="text/babel"> block in a vm with the real
 * React, stubs everything a browser would provide, and calls
 * ReactDOMServer.renderToStaticMarkup on each page of the portal.
 *
 * ⚠️ WHAT THIS DOES **NOT** PROVE
 * -------------------------------
 * useEffect never runs under renderToStaticMarkup, so every fetch in this file is a
 * promise that never settles and every page renders its LOADING or EMPTY branch. That
 * means:
 *   - no table row, no filter behaviour and no save path is exercised here;
 *   - Mapbox is a stub, so Data Management renders its chrome and an empty div;
 *   - CSS, layout and anything visual are unverified — there is no browser.
 * What it proves is exactly one thing, and it is the thing greps cannot: every page the
 * rail can reach mounts without throwing.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
// 29 Sep 2026: resolve the global packages through NODE_PATH or a node_modules on the
// path first (CI, Codespace, any sandbox); the old sandbox's fixed folder is the fallback.
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
const React = require(G + "react");
const ReactDOMServer = require(G + "react-dom/server");

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");   // 9 Oct 2026: a Windows checkout (core.autocrlf) hands us CRLF; the regexes expect LF

let pass = 0;
const fail = [];
function ok(label, cond, extra) {
  if (cond) pass++;
  else fail.push(label + (extra ? "  " + extra : ""));
}

const m = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/);
if (!m) { console.log("no babel block"); process.exit(1); }
// the mount call is the one line that needs a real DOM; drop it and export instead
const src = m[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, {
  compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019 },
}).outputText;

// ---- the browser, stubbed ------------------------------------------------------
const store = () => {
  const d = {};
  return { getItem: k => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); },
           removeItem: k => { delete d[k]; }, clear: () => { for (const k in d) delete d[k]; } };
};
// a fetch that never settles: every useEffect is unreachable here anyway, and a
// promise that resolves would only invite this harness to pretend it tested the
// loaded state, which it does not.
const fetchStub = () => new Promise(() => {});
const el = () => ({ appendChild(){}, removeChild(){}, click(){}, setAttribute(){}, style: {},
                    addEventListener(){}, removeEventListener(){}, getContext: () => null });
const sandbox = {
  React, console, Math, Date, JSON, URL: { createObjectURL: () => "blob:x", revokeObjectURL(){} },
  URLSearchParams, Blob: function(){}, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage: store(), sessionStorage: store(), fetch: fetchStub,
  alert(){}, confirm: () => true, prompt: () => "reason",
  mapboxgl: { Map: function(){ return { on(){}, remove(){}, getCanvas: () => ({ style: {} }),
              addControl(){}, getSource: () => null, getLayer: () => null, resize(){}, setStyle(){} }; },
              accessToken: "", NavigationControl: function(){}, ScaleControl: function(){} },
  Chart: function(){ return { destroy(){}, update(){} }; },
};
sandbox.window = sandbox;
sandbox.document = { getElementById: () => el(), createElement: () => el(), body: el(),
                     addEventListener(){}, removeEventListener(){} };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

let loaded = true;
try {
  vm.runInContext(js, sandbox, { filename: "index.tsx" });
  ok("the whole script block evaluates", true);
} catch (e) {
  loaded = false;
  ok("the whole script block evaluates", false, e.message);
}

// 11 Oct 2026: day of the week of an ISO date (0 Sunday … 6 Saturday), for the week fixtures' "today"
const isoDow = (iso) => new Date(iso + "T00:00:00Z").getUTCDay();
const weekdayInWeek = (fx) => !!(fx && fx.today && fx.commit_week && fx.commit_week.from <= fx.today
  && fx.today <= fx.commit_week.to && isoDow(fx.today) >= 1 && isoDow(fx.today) <= 5);
// 13 Oct 2026 (W6, narrowed): ", today" (one " · " a cell at most)
const TODAY_HEADER = /(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+, today/;

// ---- the fixture ---------------------------------------------------------------
// Deliberately minimal and deliberately EMPTY of routes: a first-boot database is the
// state most likely to throw, and it is the state a new empty-state branch is written
// for. A populated fixture would not reach those branches at all.
const meta = {
  routes: [], materials: ["Aggregate"], vehicles: ["Artic Tipper (44t)"], units: ["m3", "t", "vehicles"],
  months: { start_year: 2026, count: 60 }, factors: { material_density_t_per_m3: {}, vehicle_payload_t: {},
  vehicle_emissions_kg_co2e_per_km: {}, planning: { working_days_per_month: 21 } },
  // NARROWED 11 Oct 2026 (EU vehicles removed): the languages the server OFFERS — English alone for the seed
  // (it sent every slot, ["en", "eu", "ee"], until then)
  mapbox_token: "", vehicle_labels: { labels: {}, fallbacks: {}, langs: ["en"] },
  disciplines: [], sections: [],
};
const planner = { role: "planner", label: "Planner", ipt: null, can_approve: true,
                  ipt_locked: false, ipt_required: true, demo: false, ipts: ["IPT1", "IPT2"] };
const submitter = { role: "ipt", label: "IPT 3", ipt: "IPT3", can_approve: false,
                    ipt_locked: true, ipt_required: true, demo: false, ipts: ["IPT3"] };

function render(label, node) {
  try {
    const out = ReactDOMServer.renderToStaticMarkup(node);
    ok(label, typeof out === "string" && out.length > 0);
    return out;
  } catch (e) {
    ok(label, false, e.message);
    return "";
  }
}

if (loaded) {
  const h = React.createElement;
  const { Portal, Forecasts, ConfigPage, PageHeader, EmptyState, Dashboard, LookAhead,
          DataManagement, Matrix, CostingTab, FuelWidget } = sandbox;

  ok("the new shell components are all defined",
    [Portal, Forecasts, ConfigPage, PageHeader, EmptyState].every(f => typeof f === "function"));
  ok("My submissions and Approvals are gone from the module, not just unrendered",
    sandbox.MySubmissions === undefined && sandbox.Approvals === undefined);

  // ---- every page of the rail, as a planner ------------------------------------
  // Portal keeps the page in localStorage, so each page is selected by seeding it and
  // rendering fresh. That also proves the persistence path parses a value it did not
  // write itself.
  const PAGES = ["dashboard", "submit", "forecasts", "carbon", "lookahead", "locations", "routes",
                 "zones", "config", "map"];
  for (const page of PAGES) {
    sandbox.localStorage.setItem("modus_page", page);
    const out = render(`the ${page} page renders for a planner`,
      h(Portal, { role: planner, who: "tester", meta, metaErr: false, vehLang: "en" }));
    if (page === "map") ok("...the map page is an iframe", out.includes("<iframe"));
    if (page === "config") ok("...the config page asks for the admin token", out.includes("Admin token"));
    if (page === "carbon") ok("...the carbon page waits for its one read (no figures before the server answers)", out.includes("Loading the carbon planner"));
  }

  // ---- the submitter sees the same shell minus the Data group -------------------
  sandbox.localStorage.setItem("modus_page", "forecasts");
  const subOut = render("the portal renders for an IPT submitter",
    h(Portal, { role: submitter, who: "tester", meta, metaErr: false, vehLang: "en" }));
  ok("⭐ a submitter is not offered the Data group",
    !subOut.includes(">Locations<") && !subOut.includes(">Config<") && subOut.includes(">Look-ahead<"));
  ok("...and is not offered Zones either", !subOut.includes(">Zones<"));
  const planOut = (sandbox.localStorage.setItem("modus_page", "forecasts"), render(
    "the planner is offered the Data group",
    h(Portal, { role: planner, who: "tester", meta, metaErr: false, vehLang: "en" })));
  ok("...which lists all four data pages",
    [">Locations<", ">Routes<", ">Zones<", ">Config<"].every(s => planOut.includes(s)));

  // ---- the states a page can be in ---------------------------------------------
  ok("metaErr renders the service message rather than an empty shell",
    render("portal with metaErr",
      h(Portal, { role: planner, who: "t", meta: null, metaErr: true, vehLang: "en" }))
      .includes("reach the forecasting service"));   // apostrophes arrive HTML-escaped
  ok("no meta yet renders a loading state",
    render("portal with no meta",
      h(Portal, { role: planner, who: "t", meta: null, metaErr: false, vehLang: "en" }))
      .includes("Loading"));

  // ---- the merged page, both ways ----------------------------------------------
  const fPlanner = render("Forecasts renders for an approver",
    h(Forecasts, { meta, who: "t", access: planner, onEdit(){}, onChanged(){} }));
  const fSubmitter = render("Forecasts renders for a submitter",
    h(Forecasts, { meta, who: "t", access: submitter, onEdit(){}, onChanged(){} }));
  ok("⭐ the two roles get different copy, not one wording for both",
    fPlanner !== fSubmitter && fPlanner.includes("Approve or reject each line here")
    && fSubmitter.includes("across every year each one covers")
    && !fPlanner.includes("across every year each one covers"));

  // ---- 10 Oct 2026: the Carbon planner POPULATED from the scenario test_carbon.py writes
  // (156.995 t baseline; 'Greener' −124.153 t; drivers disposal, fuel, recycled — hand-worked there)
  const cbPath = path.join(__dirname, "fixtures", "carbon_scenario.json");
  ok("the carbon-scenario fixture exists (written by test_carbon.py)", fs.existsSync(cbPath));
  if (fs.existsSync(cbPath) && typeof sandbox.CarbonPage === "function") {
    const cs = JSON.parse(fs.readFileSync(cbPath, "utf8"));
    const cOut = render("the Carbon page renders POPULATED from the scenario fixture", h(sandbox.CarbonPage, { meta, access: planner, initialData: cs }));
    // NARROWED 11 Oct 2026 (plain-English pass): the same figures, in the new words
    ok("⭐ ...the approved plan 157.0 t and the alternative 32.8 t, 124.2 tCO2e lower (79.1%)",
      cOut.includes(">Approved plan<") && cOut.includes("157.0") && cOut.includes("32.8")
      && cOut.includes("124.2 tCO2e lower than the approved plan (79.1%)") && !cOut.includes("Baseline"));
    // NARROWED 11 Oct 2026 (the process layout: step 3's "Battery electric lorries" control now comes before the ranking in
    // step 5, so the order is read inside the ranking, from its heading on)
    const iW = cOut.indexOf("Which decisions change carbon most"), iD = cOut.indexOf("Receiving site and disposal method", iW), iF = cOut.indexOf(">Battery electric lorries<", iD);
    ok("⭐ ...the drivers in the server's order: receiving site and disposal method, then battery electric lorries, then recycled content",
      iW > 0 && iD > iW && iF > iD && cOut.indexOf("Recycled content", iF) > iF);
    ok("...lorry loads beside the carbon: 335 on the approved plan, 382 on the alternative, 47 more because each lorry carries less",
      cOut.includes(">335<") && cOut.includes(">382<") && cOut.includes("47 more lorry loads, because each lorry carries less"));
    ok("...the NH intensity is the restated 159 to 181 at 2023 prices, context only",
      cOut.includes("159 (2024/25) to 181 (2025/26) tCO2e per £m, 2023 prices") && !cOut.includes("210"));
    ok("...the three methods side by side, the NH Carbon Tool basis labelled for comparison",
      cOut.includes("Wayscope: per vehicle-km, both legs") && cOut.includes("National Highways Carbon Tool method (for comparison)")
      && cOut.includes("46.2"));
    ok("...the diesel-or-electric table: 300 diesel trips, 342 electric, 19 950 kWh",
      cOut.includes(">Battery electric<") && cOut.includes(">300<") && cOut.includes(">342<") && cOut.includes("19 950")
      && cOut.includes("no charge needed inside a shift") && !cOut.includes("up to 0 charge"));
    ok("...the controls: a disabled recycled slider for soil with the reason, the EPD fields, the electric switch",
      cOut.includes("Not available: no primary-production factor is published for Soils.") && cOut.includes("EPD reference (required)")
      && cOut.includes("Battery electric lorries") && cOut.includes("Where Config has an electric profile for that lorry"));
    // after the show (11 Oct 2026, items 8, 9, 11–15) — the figures test_carbon.py hand-works
    // NARROWED 11 Oct 2026 (the process layout: "What this page counts" is now the "What this counts" details in step 1)
    ok("...item 8 what the page counts, and the one unrouted line named as left out",
      cOut.includes("<summary>What this counts</summary>") && cOut.includes("Making the material (A1–A3); transport to site and back, both legs (A4)")
      && cOut.includes("1 plan line has no route distance yet: transport not counted"));
    ok("...item 14 the life-cycle modules on both cards: 30.4 · 5.6 · 120.9 and 25.1 · 1.2 · 6.5",
      cOut.includes("By life-cycle module: A1–A3 30.4 · A4 5.6 · A5 120.9") && cOut.includes("By life-cycle module: A1–A3 25.1 · A4 1.2 · A5 6.5"));
    ok("...item 12 well-to-wheel beside the totals: 16.2 and 2.4 tCO2e, and in the methods table",
      cOut.includes("Transport well-to-wheel: 16.2 tCO2e") && cOut.includes("Transport well-to-wheel: 2.4 tCO2e")
      && cOut.includes("Wayscope, well-to-wheel (adds producing the fuel or electricity)"));
    ok("...item 9 each decision's lorry effect: the soil hub 4 800 fewer lorry-km; electric 47 more loads and 1 960 more lorry-km; the alternative 3 512 fewer",
      cOut.includes("4 800 fewer lorry-km") && cOut.includes("47 more lorry loads · 1 960 more lorry-km")
      && cOut.includes("no change in lorry loads or lorry-km") && cOut.includes("3 512 fewer lorry-km"));
    ok("...item 13 the waste hierarchy on the muck-away route (landfill: disposal) and on each method offered",
      cOut.includes("Waste hierarchy: disposal") && cOut.includes("Recycled (closed-loop) · waste hierarchy: recycling")
      && cOut.includes("Wayscope does not replace these or the duty of care"));
    // NARROWED 11 Oct 2026 (the process layout: the summary is step 5's second action, its commentary in a details;
    // "Using these results" is "Who acts on these results" under About these figures)
    ok("...item 11 the summary card and item 15 who acts",
      cOut.includes("<summary>Add a commentary (optional)</summary>") && cOut.includes("Download the summary (PDF)") && cOut.includes("Who acts on these results")
      // REVERSED 11 Oct 2026 ("Buyer" is not a CLOCS role, so the page no longer says the roles are CLOCS's)
      && cOut.includes("Principal contractor") && !cOut.includes("as CLOCS names them") && cOut.includes("Agrees the carbon target for the scheme (a planner records it in step 6)"));
    ok("...the Planned panel and the known limits, and nothing renders as undefined or NaN",
      cOut.includes("Not built yet") && cOut.includes("Known limits") && !/undefined|NaN/.test(cOut));

    // ---- 11 Oct 2026: the process layout and step 6, the carbon target (fixtures/carbon_target.json from
    // test_carbon_target.py: a 73.1% target (held to 6 dp, 73.098745), approved 161.446, with the decisions 43.431,
    // target 43.431, gaps 118.015 and 0.0, the server's verdicts "not on target" and "on target", pending 5.653).
    // The other states are the same GET with the fields the server would send (verdicts included).
    ok("⭐ ...the six steps render in order, with the result strip at the foot pointing to step 5",
      [1, 2, 3, 4, 5, 6].every(n => cOut.indexOf(`id="carbon-step-${n}"`) > 0 && (n === 1 || cOut.indexOf(`id="carbon-step-${n - 1}"`) < cOut.indexOf(`id="carbon-step-${n}"`)))
      && ["Your approved plan", "Materials", "Lorries and routes", "Surplus material", "Result", "Carbon target"].every(t => cOut.includes(`<span>${t}</span>`))
      && cOut.includes("Result: <b>32.8 tCO2e</b>, 124.2 tCO2e lower (79.1%)") && cOut.includes(">See step 5</button>")
      && cOut.indexOf(">See step 5</button>") > cOut.indexOf('id="carbon-step-6"'));
    const ct6Path = path.join(__dirname, "fixtures", "carbon_target.json");
    ok("the carbon-target fixture exists for the Carbon page's step 6 (written by test_carbon_target.py)", fs.existsSync(ct6Path));
    if (fs.existsSync(ct6Path)) {
      const CT6 = JSON.parse(fs.readFileSync(ct6Path, "utf8"));
      const with6 = (s, t) => ({ target: { ...CT6.target, ...(t || {}) }, status: { ...CT6.status, ...s } });
      const step6 = (o) => { const i = o.indexOf('id="carbon-step-6"'); return i < 0 ? "" : o.slice(i, o.indexOf("About these figures", i)); };
      const cp = (ct, acc) => render("the Carbon page renders a carbon target state", h(sandbox.CarbonPage, { meta, access: acc || planner, who: "Sam", initialData: cs, initialTarget: ct }));
      const pSet = cp(CT6), p6 = step6(pSet);
      // NARROWED 11 Oct 2026 (the review: one way of saying the target on all four pages; the verdicts are the server's):
      // "which is 43.4 tCO2e today" is the Dashboard's "= 43.4 tCO2e"; the figures are no longer bold, as on the Dashboard
      ok("⭐ ...step 6, a planner and a set target: the target; as forecast 118.0 tCO2e over; with the agreed decisions on target (the server's verdict); what the pending lines would add; who set it",
        p6.includes(">Target: 73.1% below the approved plan = 43.4 tCO2e<") && p6.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target<")
        && p6.includes(">With the agreed decisions: 43.4 tCO2e, on target<") && p6.includes("Lines waiting for approval would add 5.7 tCO2e.")
        && p6.includes(">Set by Sam (planner)<") && p6.includes("<li>Recycled content 30% — Small aggregate</li>") && !/undefined|NaN/.test(pSet));
      ok("...the planner's controls: the stored mode pressed and ticked, Set waiting for a choice (and saying so), Open the agreed decisions, Clear the target",
        p6.includes('aria-pressed="true"') && p6.includes("✓ % below the approved plan") && p6.includes(">Fixed tCO2e cap</button>")
        // NARROWED 11 Oct 2026 (Set wraps on a phone: style white-space normal)
        && /<button type="button" class="btn-pri" style="white-space:normal" disabled="">Set as the scheme&#x27;s carbon target<\/button>/.test(p6) && p6.includes("Make a choice in steps 2 to 4 first.")
        && p6.includes(">Open the agreed decisions</button>") && p6.includes(">Clear the target</button>"));
      ok("...and step 1 says there is a target, pointing to step 6",
        // NARROWED 11 Oct 2026 (the shared target sentence)
        pSet.slice(0, pSet.indexOf('id="carbon-step-2"')).includes(">Target: 73.1% below the approved plan = 43.4 tCO2e (step 6)<"));
      const pNone = step6(cp({ target: null, status: null }));
      ok("...no target: says so, the % mode picked for the next one, nothing to open or clear",
        // NARROWED 11 Oct 2026 (one "no target" sentence on all four pages)
        pNone.includes(">No carbon target set yet.<") && pNone.includes("✓ % below the approved plan") && !pNone.includes("Clear the target") && !pNone.includes("Open the agreed decisions"));
      // NARROWED 11 Oct 2026 (the server's verdict: under by 12.34 is not on target; the cap reads with its "(… when it was set)")
      const pCap = step6(cp(with6({ target_t: 43.431, gap_as_forecast_t: 118.015, gap_with_decisions_t: -12.34, on_target_with_decisions: false }, { mode: "cap" })));
      ok("...a cap reads as a fixed cap, ticked; a gap below it reads 12.3 tCO2e under the target",
        pCap.includes(">Target: a fixed cap of 43.4 tCO2e (73.1% below the approved plan when it was set)<") && pCap.includes("✓ Fixed tCO2e cap")
        && pCap.includes(">With the agreed decisions: 43.4 tCO2e, 12.3 tCO2e under the target<") && !/undefined|NaN/.test(pCap));
      // REVERSED 11 Oct 2026 (the review: a team code got the scheme's % applied to its own lines, so a team the decisions do not
      // touch read "over the target" while the scheme was on it). The server now sends a team code no target_t, no gaps and no
      // verdicts in EITHER mode; the page says the target is the whole scheme's and labels the figures as the team's lines.
      // REVERSED AGAIN 13 Oct 2026 (the user, 12 Oct: each team gets its own share of the target): the server sends a team code
      // its share (target_t, share_pct: the target split by each team's plan with the decisions) and its own verdicts.
      // It asserted "for the whole scheme, not split by team" and no verdict.
      const TEAM6 = { scope: "team", target_t: 43.43, share_pct: 79.5, gap_as_forecast_t: 118.015, gap_with_decisions_t: 0, on_target_as_forecast: false, on_target_with_decisions: true };
      const pTeam = step6(cp(with6(TEAM6), submitter));
      const pTeamCap = step6(cp(with6(TEAM6, { mode: "cap" }), submitter));
      ok("⭐ ...a team code: its OWN share of the target (79.5%), % or cap, with its own verdicts; no controls, told who sets it; no team id",
        pTeam.includes(">Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s target (73.1% below the approved plan)<") && pTeam.includes("Your planner sets the scheme&#x27;s carbon target.")
        && !pTeam.includes("Set as the scheme") && !pTeam.includes("Clear the target") && !pTeam.includes("aria-pressed")
        && pTeamCap.includes(">Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s fixed cap of 43.4 tCO2e<")
        && [pTeam, pTeamCap].every(o => o.includes(">As forecast on your team&#x27;s lines: 161.4 tCO2e, 118.0 tCO2e over the target<") && o.includes(">With the agreed decisions on your team&#x27;s lines: 43.4 tCO2e, on target<")
          && o.includes("These figures are for your team&#x27;s lines only, against their share of the scheme&#x27;s target: the target split by each team&#x27;s plan with the agreed decisions. The shares add up to the target.")
          && !o.includes("not split by") && !o.includes("not compared"))
        && !/IPT\d/.test(pTeam + pTeamCap) && !/undefined|NaN/.test(pTeam + pTeamCap));
      ok("🔴 R3 ...a team code gets no 'Open the agreed decisions' and no list of the decisions (as on the Dashboard)",
        !pTeam.includes("Open the agreed decisions") && !pTeam.includes("The agreed decisions</p>") && !pTeam.includes("Recycled content 30%")
        && pSet.includes("The agreed decisions</p>") && p6.includes(">Open the agreed decisions</button>"));
      // NARROWED 11 Oct 2026 (the server's sentence now names the Carbon planner and says a planner sets it again; no bold figures)
      const pBad = step6(cp(with6({ with_decisions_t: null, gap_with_decisions_t: null, on_target_with_decisions: null,
        invalid: "The agreed decisions no longer fit the plan (route 'R4' does not exist), so the plan with them cannot be worked out. A planner needs to set the target again on the Carbon planner." })));
      ok("...decisions that no longer apply: the server's sentence in place of the second line, the as-forecast line kept",
        pBad.includes("The agreed decisions no longer fit the plan (route &#x27;R4&#x27; does not exist)") && !pBad.includes("With the agreed decisions:")
        && pBad.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target<"));
      // 11 Oct 2026 (R2): ONE rule, the server's. A cap 2.0 tCO2e over reads over here as on the Dashboard; and the page
      // follows the server's verdict, not the size of the gap (a 2.0 gap the server calls on target reads on target)
      const pCap2 = step6(cp(with6({ approved_t: 7361.1, with_decisions_t: 7002.8, target_t: 7000.8, gap_with_decisions_t: 2.0, on_target_with_decisions: false }, { mode: "cap", cap_t: 7000.8 })));
      const pFollow = step6(cp(with6({ gap_with_decisions_t: 2.0, on_target_with_decisions: true })));
      ok("⭐ R2 ...a cap 2.0 tCO2e over reads '2.0 tCO2e over the target'; the verdict is the server's on_target, never a margin worked out here",
        pCap2.includes(">With the agreed decisions: 7 002.8 tCO2e, 2.0 tCO2e over the target<") && pFollow.includes(">With the agreed decisions: 43.4 tCO2e, on target<"));
      const pWhen = step6(cp(with6({}, { updated_at: "2026-10-11T23:30:00Z" })));
      const _d = new Date("2026-10-11T23:30:00Z"), _M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const _day = `${_d.getDate()} ${_M[_d.getMonth()]} ${_d.getFullYear()}`;
      ok("...the date a target was set is the reader's own day (00:30 BST is 12 Oct, not the UTC 11 Oct), the same helper as the Dashboard's",
        pWhen.includes(`>Set by Sam (planner), ${_day}<`) && sandbox.ctSetBy({ updated_by: "Sam (planner)", updated_at: "2026-10-11T23:30:00Z" }) === `Set by Sam (planner), ${_day}`);
    }
  } else {
    ok("CarbonPage is defined", false);
  }

  // ---- 11 Sep: the Dashboard and the Forecasts page POPULATED from the server's cost lines
  // (test_costlines.py writes the fixture through costlines.lines() on its scratch database)
  const clPath = path.join(__dirname, "fixtures", "cost_lines.json");
  ok("the cost-lines fixture exists (written by test_costlines.py)", fs.existsSync(clPath));
  const cl = fs.existsSync(clPath) ? JSON.parse(fs.readFileSync(clPath, "utf8")) : null;
  if (cl) {
    const dMeta = { ...meta, months: { start_year: 2026, count: 24 }, materials: ["Small aggregate"], vehicles: ["Rigid 8-wheeler (32t)"],
                    factors: { ...meta.factors, material_density_t_per_m3: { "Small aggregate": 1.6 }, vehicle_payload_t: { "Rigid 8-wheeler (32t)": 20 } } };
    const dOut = render("the Dashboard renders POPULATED from the cost lines (initialData)", h(Dashboard, { meta: dMeta, initialData: cl }));
    ok("...with the three KPI groups — Volume, Cost, Carbon — and the coverage line",
      // 13 Oct 2026 (W3, narrowed): the coverage line in plain words
      dOut.includes(">Volume<") && dOut.includes(">Cost<") && dOut.includes(">Carbon<") && dOut.includes("forecast months have a route")
      && dOut.includes("leave out the " + (cl.totals.lines - cl.totals.baked_lines) + " not routed yet"));
    // the default view is Approved only, so the KPIs are sums over the Approved rows of the fixture
    const appr = cl.lines.filter(l => l.status === "Approved");
    const sumTrips = appr.reduce((a, l) => a + l.trips, 0);
    const fairT = appr.filter(l => l.fair.eur != null);
    const fairPerT = fairT.reduce((a, l) => a + l.fair.eur, 0) / fairT.reduce((a, l) => a + l.tonnes, 0);
    ok("...the trips KPI is the SUM of the server's rounded-up trips (no arithmetic of its own) and fair €/t the weighted figure",
      dOut.includes(">" + sumTrips.toLocaleString("en-US").replace(/,/g, " ") + "<") && dOut.includes("planned €") && dOut.includes("fair € (model)")
      && dOut.includes("€ " + fairPerT.toFixed(2)));
    ok("...the diesel index is in the header, and IPT / discipline filters exist",
      dOut.includes("€" + (+cl.costing.index_eur_per_l).toFixed(3) + "/L") && dOut.includes("All Teams") && dOut.includes("All disciplines"));
    // 13 Oct 2026 (W3, narrowed): "not baked" reads "not routed"
    ok("...the route table prints planned € with a 'target' chip, fair € and fair €/t, and 'not routed' on the unbaked route",
      // 13 Oct 2026 (W6, narrowed): "not routed" is the unrouted line's status word, "Not routed"
      dOut.includes(">target<") && dOut.includes("Fair € (model)") && dOut.includes(">Not routed<") && !dOut.includes("not baked") && dOut.includes("Cost over time"));
    ok("...nothing renders as undefined or NaN", !/undefined|NaN/.test(dOut));
    // 11 Sep pm: the four groups, the Delivered figures from the fixture's reported line, every Fig with a title
    ok("...the Delivered-to-date group prints the server's actual tonnes and % of plan (a reported line is in the fixture)",
      dOut.includes(">Delivered to date<") && cl.totals.actual_tonnes != null
      && dOut.includes(">" + cl.totals.actual_tonnes.toLocaleString("en-US").replace(/,/g, " ") + "<")
      && dOut.includes("tonnes moved") && dOut.includes("forecast months reported"));     // 13 Oct 2026 (W3, narrowed): was "line-months" 
    ok("...every KPI value sits in a nowrap clamp()-sized div, none truncated",
      (dOut.match(/font-size:clamp\(1\.1rem/g) || []).length >= 16 && !/kpi-num[^"]*truncate/.test(dOut));
    // 13 Oct 2026 (W3, narrowed): the hover title became an info box button; no cursor:help is left
    ok("...every KPI cell has an info box (was: a title attribute on hover)",
      (dOut.match(/<div class="min-w-0"><div class="kpi-num[\s\S]*?class="ibtn" aria-label="About: [^"]+"/g) || []).length >= 16 && !dOut.includes("cursor-help"));
    ok("...the Today strip renders its loading state without the week, and the stock chart card is there (no stock table)",
      dOut.includes("Loading this week") && dOut.includes("Stockpile capacity") && !dOut.includes("Stock held") && dOut.includes("Big screen"));
    // 12 Oct 2026 (C4): the Monthly bulletin menu renders on the working view, closed, with the month and the two actions
    ok("...the Dashboard's working view carries the Monthly bulletin menu: the month select, Download the PDF, Open the page (/bulletin/?month=N)",
      dOut.includes('<details class="row-menu bulletin-menu">') && dOut.includes(">Monthly bulletin ▾</summary>")
      && dOut.includes(">Download the PDF</button>") && /<a href="\/bulletin\/\?month=\d+" target="_blank" rel="noopener">Open the page<\/a>/.test(dOut)
      && dOut.includes('aria-label="Bulletin month"'));
    ok("...the route table has a Delivered column with a % on the reported line and — elsewhere",
      dOut.includes(">Delivered") && / %<\/span>/.test(dOut));
    // with the week fixture: today's deliveries, this week to date, last week, the map card
    const wkPath = path.join(__dirname, "fixtures", "lookahead_page_fuel.json");
    const wk = fs.existsSync(wkPath) ? JSON.parse(fs.readFileSync(wkPath, "utf8")) : null;
    if (wk) {
      // 2026-10-11 (a Sunday): written on a weekend with the clock's date, this fixture's today had no
      // planned line and the check below failed on correct output. test_costing.py now pins today to a
      // weekday of the commit week (portable.fixture_today); this says so first, so a lost pin reads as itself.
      ok(`the week fixture's today (${wk.today}) is a weekday inside its commit week (pinned by test_costing.py on a weekend)`,
        weekdayInWeek(wk), `week ${(wk.commit_week || {}).from}..${(wk.commit_week || {}).to}`);
      const wOut = render("the Dashboard renders POPULATED with the week too (initialWeek)", h(Dashboard, { meta: dMeta, initialData: cl, initialWeek: wk }));
      const todayRows = [];
      wk.commit.lines.forEach(l => (l.days || []).forEach(d => { if (d.day_date === wk.today && ((d.planned_qty || 0) > 0 || d.actual_qty != null)) todayRows.push({ l, d }); }));
      const tT = todayRows.reduce((a, x) => a + ((x.d.derived || {}).tonnes || 0), 0);
      const tTrips = todayRows.reduce((a, x) => a + ((x.d.derived || {}).trips || 0), 0);
      ok(`...today (${wk.today}) lists ${todayRows.length} lines with the SERVER's day tonnes and trips summed (${tT} t, ${tTrips} trips)`,
        todayRows.length > 0 && wOut.includes(">tonnes<") && wOut.includes("day actuals typed today") && wOut.includes(">" + tT.toLocaleString("en-US").replace(/,/g, " ") + "<")
        && wOut.includes(">" + tTrips.toLocaleString("en-US").replace(/,/g, " ") + "<")
        // 13 Oct 2026 (W6, narrowed): the route id is a details line under each Today row
        && todayRows.every(x => wOut.includes("<dt>Route</dt><dd>" + x.l.route_id + "</dd>")));
      ok("...this week to date and last week's account are printed with their bars",
        wOut.includes("This week to date") && wOut.includes("Last week") && (wOut.match(/h-2 rounded-full bg-slate-100/g) || []).length === 2
        && wOut.includes(`${wk.account.reported} of ${wk.account.lines} lines reported`));
      ok("...the map card carries the Look-ahead's CommitMap with the Dashboard's title, and no € anywhere in the Today strip",
        wOut.includes("This week&#x27;s lines on the map") && !/€/.test(wOut.slice(wOut.indexOf("Today · "), wOut.indexOf("Delivered to date"))));
      ok("...nothing renders as undefined or NaN", !/undefined|NaN/.test(wOut));
      ok("...and a weekday's strip never says \"nothing planned today\"", !wOut.includes("nothing planned today"));
      // 2026-10-11: the weekend, rendered on purpose every day rather than only when the harness happens
      // to run on one: the same week with the server's today on its Sunday (the week's days already carry
      // Sat and Sun at 0 planned). Today has no line; the week's figures are still there.
      const sun = (wk.commit_week || {}).to;
      const sunRows = wk.commit.lines.reduce((n, l) => n + (l.days || []).filter(d => d.day_date === sun && ((d.planned_qty || 0) > 0 || d.actual_qty != null)).length, 0);
      const sOut = render("the Dashboard renders the same week on its Sunday (a weekend today)", h(Dashboard, { meta: dMeta, initialData: cl, initialWeek: { ...wk, today: sun } }));
      ok(`...on Sunday (${sun}) today lists no line: tonnes, trips, vehicles and reported read —, the strip says "nothing planned today", the week's figures stay`,
        isoDow(sun) === 0 && sunRows === 0 && sOut.includes("Today · Sunday") && sOut.includes("nothing planned today")
        && (sOut.match(/kpi-num[^>]*>—</g) || []).length >= 4 && sOut.includes("This week to date") && sOut.includes("trips planned this week")
        && !/undefined|NaN/.test(sOut), `${sunRows} rows on ${sun}`);
    }
    // Approved-only default: the Pending IPT2 line is not in the default view
    ok("...the default view is Approved only (the Pending line is filtered out; the status select says so)",
      // 13 Oct 2026 (W3, narrowed): the scope is said once, in the kicker ("· approved"); the subtitle that repeated it is gone
      dOut.includes(" · approved<") && !dOut.includes("approved only") && !dOut.includes(">R4<"));
    const rowsFix = cl.lines.map(l => ({ route_id: l.route_id, discipline: l.discipline, section_id: l.section_id, month_index: l.month_index,
      quantity: l.quantity, unit: l.unit, status: l.status, ipt: l.ipt, material_type: l.material_type, material_description: null,
      vehicle_type: l.vehicle_type, submitted_by: "tester", reject_reason: null }));
    const fOut = render("the Forecasts page renders POPULATED with the cost column (initialRows + initialCost)",
      h(Forecasts, { meta: dMeta, who: "t", access: planner, onEdit(){}, onChanged(){}, initialRows: rowsFix, initialCost: cl }));
    const nLines = new Set(cl.lines.map(l => `${l.route_id}|${l.discipline}|${l.section_id}`)).size;
    // 13 Oct 2026 (W6, narrowed): the cost cell is two columns, Planned and Fair; the fair figure's reason for "—" and its
    // per-unit split are in the row's details
    ok("...one Cost cell per line, each with a planned figure (or 'rate not set') and a fair figure (or 'fair —')",
      (fOut.match(/data-cost-cell="1"/g) || []).length === nLines && (fOut.match(/<dt>Fair € \(model\)<\/dt><dd>€ /g) || []).length >= 1
      && /<dt>Fair € \(model\)<\/dt><dd>(Not routed yet for this vehicle, so no distance and no fair price|No diesel index)<\/dd>/.test(fOut)
      && (fOut.match(/>target<\/span>/g) || []).length >= 1);
    ok("...and the fair figure carries €/t beside it", /<dt>Fair, per unit<\/dt><dd>€ [\d.]+\/t, /.test(fOut));
    ok("...nothing renders as undefined or NaN", !/undefined|NaN/.test(fOut));
  }

  // ---- 11 Sep pm: the Submit matrix with the price while typing (initialCost) -------
  const pvPath = path.join(__dirname, "fixtures", "cost_preview.json");
  ok("the cost-preview fixture exists (written by test_costlines.py)", fs.existsSync(pvPath));
  const pv = fs.existsSync(pvPath) ? JSON.parse(fs.readFileSync(pvPath, "utf8")) : null;
  if (pv) {
    const mMeta = { ...meta, months: { start_year: 2026, count: 24 }, routes: [{ route_id: "R1", origin: "Pit", dest: "Site", distance_km: 30 }],
                    materials: ["Small aggregate"], vehicles: [pv.vehicle_type], planning_vehicles: [pv.vehicle_type],
                    factors: { ...meta.factors, material_density_t_per_m3: { "Small aggregate": 1.6, _default: 1.6 }, vehicle_payload_t: { [pv.vehicle_type]: 20, _default: 20 } } };
    const mOut = render("the Submit matrix renders with a cost preview (initialCost)",
      h(Matrix, { meta: mMeta, who: "t", editTarget: null, vehLang: "en", access: planner, initialCost: pv }));
    const fairT = pv.totals.fair;
    ok("...the strip prints the preview's fair € total, €/t, €/trip, €/km and the planned € with 'target rate'",
      mOut.includes('data-cost-strip="1"') && mOut.includes("€ " + Math.round(fairT.eur).toLocaleString("en-US").replace(/,/g, " "))
      && mOut.includes("€ " + (+fairT.per_t).toFixed(2)) && mOut.includes("€ " + (+fairT.per_km).toFixed(2)) && mOut.includes("target rate"));
    ok("...and the diesel index the model priced at, with the winter note", mOut.includes("€" + (+pv.index_eur_per_l).toFixed(3) + "/L") && mOut.includes("winter months"));
    ok("...nothing renders as undefined or NaN", !/undefined|NaN/.test(mOut));
    const mNone = render("the matrix renders with NO preview (nothing typed)", h(Matrix, { meta: mMeta, who: "t", editTarget: null, vehLang: "en", access: planner, initialCost: null }));
    ok("...and says 'type a quantity to see the price' with fair — and 'rate not set'", mNone.includes("type a quantity to see the price") && mNone.includes("rate not set"));
    const mUnb = render("the matrix renders an UNBAKED preview", h(Matrix, { meta: mMeta, who: "t", editTarget: null, vehLang: "en", access: planner,
      initialCost: { ...pv, baked: false, fair_reason: "not baked", cells: [], totals: { ...pv.totals, fair: { eur: null, per_t: null, per_trip: null, per_km: null } } } }));
    // 13 Oct 2026 (W3, narrowed): plain words
    ok("...which says why there is no fair price and where to fix it", mUnb.includes("not routed for") && mUnb.includes("route it on Data → Routes"));
  }

  // ---- 11 Oct 2026: the carbon target on the Dashboard, Forecasts and Submit forecast, from the fixtures
  // test_carbon_target.py writes: carbon_target.json (the planner's GET of a 73.1% target held to 6 dp: approved
  // 161.446, with the decisions 43.431, target 43.431, gaps 118.015 and 0.0 with the server's verdicts, pending
  // 5.653, transport 14.091)
  // and cost_preview_carbon.json (R1, 2900 t: material 22.629 + transport 5.636 = 28.265). The other
  // states (cap, team, under, no longer applies) are the same GET with the fields the server would send.
  const ctPath = path.join(__dirname, "fixtures", "carbon_target.json");
  const pcPath = path.join(__dirname, "fixtures", "cost_preview_carbon.json");
  ok("the carbon-target and preview-with-carbon fixtures exist (written by test_carbon_target.py)", fs.existsSync(ctPath) && fs.existsSync(pcPath));
  if (fs.existsSync(ctPath) && fs.existsSync(pcPath) && cl) {
    const CT = JSON.parse(fs.readFileSync(ctPath, "utf8"));
    const PC = JSON.parse(fs.readFileSync(pcPath, "utf8"));
    const NONE = { target: null, status: null };
    // the part of a page the target owns (a page's own team filter carries ids in its option values)
    const seg = (out, a, b) => { const i = out.indexOf(a); return i < 0 ? "" : out.slice(i, out.indexOf(b, i) < 0 ? undefined : out.indexOf(b, i)); };
    const withS = (s, t) => ({ target: { ...CT.target, ...(t || {}) }, status: { ...CT.status, ...s } });
    // NARROWED 11 Oct 2026 (R2 and the team change): each state carries the server's verdicts; a team code, % or cap, has no
    // target_t, gaps or verdicts (the server sends none), and the server's sentence for decisions that no longer apply is its new one
    // REVERSED 13 Oct 2026 (each team its share): a team code now carries its share and its verdicts (TEAMNO kept for the
    // one state with no share: decisions that no longer fit, so there is no plan with them to split by)
    const TEAMNO = { scope: "team", target_t: 43.43, share_pct: 79.5, gap_as_forecast_t: 118.015, gap_with_decisions_t: 0, on_target_as_forecast: false, on_target_with_decisions: true };
    const TEAMX = { scope: "team", target_t: null, share_pct: null, with_decisions_t: null, gap_as_forecast_t: null, gap_with_decisions_t: null, on_target_as_forecast: null, on_target_with_decisions: null,
      invalid: "The agreed decisions no longer fit the plan (route 'R4' does not exist), so your share of the target cannot be worked out. A planner needs to set the target again on the Carbon planner." };
    const CAP = withS({ target_t: 43.431, gap_as_forecast_t: 118.015, gap_with_decisions_t: 0, on_target_as_forecast: false, on_target_with_decisions: true }, { mode: "cap" });
    const TEAMP = withS(TEAMNO);
    const TEAMC = withS(TEAMNO, { mode: "cap" });
    const UNDER = withS({ gap_with_decisions_t: -12.34, on_target_with_decisions: false });
    const BAD = withS({ with_decisions_t: null, gap_with_decisions_t: null, on_target_with_decisions: null,
      invalid: "The agreed decisions no longer fit the plan (route 'R4' does not exist), so the plan with them cannot be worked out. A planner needs to set the target again on the Carbon planner." });
    const CAP2 = withS({ approved_t: 7361.1, with_decisions_t: 7002.8, target_t: 7000.8, gap_as_forecast_t: 360.3, gap_with_decisions_t: 2.0,
                         on_target_as_forecast: false, on_target_with_decisions: false }, { mode: "cap", cap_t: 7000.8 });
    const FOLLOW = withS({ gap_with_decisions_t: 2.0, on_target_with_decisions: true });
    const ctMeta = { ...meta, months: { start_year: 2026, count: 24 }, materials: ["Small aggregate"], vehicles: ["Rigid 8-wheeler (32t)"],
                     factors: { ...meta.factors, material_density_t_per_m3: { "Small aggregate": 1.6 }, vehicle_payload_t: { "Rigid 8-wheeler (32t)": 20 } } };
    const dash = (ct, extra) => render("the Dashboard renders with a carbon target state", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: ct, ...(extra || {}) }));
    const dSet = dash(CT, { onOpen(){} });
    // NARROWED 11 Oct 2026 (a gap carries its unit, as on the Carbon page: "118.0 tCO2e over the target")
    ok("⭐ Dashboard: the strip reads the contract's words — 73.1% below the approved plan = 43.4 tCO2e; as forecast 161.4, 118.0 over; with the agreed decisions 43.4, on target",
      dSet.includes('data-carbon-target="set"') && dSet.includes("<b>Target: 73.1% below the approved plan = 43.4 tCO2e</b>")
      && dSet.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target<") && dSet.includes(">With the agreed decisions: 43.4 tCO2e, on target<"));
    // NARROWED 11 Oct 2026 (R1 + R2): there is no rounding to absorb (the % is held to 6 dp, the gap is 0.0) and the verdict is
    // the server's; the page follows it — a 2.0 gap the server calls on target reads on target, never "2.0 over"
    const dFollow = dash(FOLLOW);
    ok("...the gap at set time is 0.0 and reads on target, not 0.0 over; the verdict is the server's (a 2.0 gap it calls on target reads on target)",
      !dSet.includes("0.0 over") && !dSet.includes("0.0 under") && CT.status.gap_with_decisions_t === 0 && CT.status.on_target_with_decisions === true
      && dFollow.includes(">With the agreed decisions: 43.4 tCO2e, on target<") && !dFollow.includes("2.0 tCO2e over"));
    ok("...the strip offers the Carbon planner with a target set too (it only did with none)", dSet.includes(">Open the Carbon planner</button>"));
    ok("...says once that it is all-in beside the transport-only card, with the transport part (14.1) on hover; who set it, with no date for a scrubbed one",
      dSet.includes("All-in: making the material, transport and waste disposal, on the whole approved plan. The Transport carbon card above counts transport only.")
      // 13 Oct 2026 (W3, narrowed): the transport part is in an info box, not on hover (dom_frontend opens it and reads 14.1)
      && dSet.includes('aria-label="About: Transport in this target"') && !dSet.includes('title="Transport is 14.1')
      && dSet.includes(">Set by Sam (planner)<"));
    ok("...the 2 agreed decisions, collapsed, in the server's words",
      dSet.includes("<summary>The 2 agreed decisions</summary>") && dSet.includes("<li>Recycled content 30% — Small aggregate</li>"));
    ok("🔴 ...under the six cards (still six), above the charts; nothing undefined or NaN",
      (dSet.match(/class="card dash-card min-w-0"/g) || []).length === 6 && dSet.indexOf(">Transport carbon<") < dSet.indexOf('data-carbon-target="set"')
      && dSet.indexOf('data-carbon-target="set"') < dSet.indexOf("Material demand over time") && !/undefined|NaN/.test(dSet));
    const dNone = dash(NONE, { onOpen(){} }), dNoNav = dash(NONE);
    ok("⭐ ...no target: says so and who sets it, with a button to the Carbon planner (only when the page can switch)",
      dNone.includes('data-carbon-target="none"') && dNone.includes("No carbon target set yet. A planner sets it in the Carbon planner.")
      && dNone.includes(">Open the Carbon planner</button>") && dNoNav.includes("No carbon target set yet.") && !dNoNav.includes("Open the Carbon planner"));
    const dCap = dash(CAP), dUnder = dash(UNDER), dBad = dash(BAD);
    // NARROWED 11 Oct 2026 (a cap reads "a fixed cap of" on every page, so the % / cap toggle shows everywhere; a gap carries its unit)
    ok("...a cap: a fixed cap of 43.4 tCO2e (73.1% below the approved plan when it was set); a gap below the target reads 12.3 tCO2e under",
      dCap.includes("<b>Target: a fixed cap of 43.4 tCO2e (73.1% below the approved plan when it was set)</b>") && dCap.includes("tCO2e, on target<")
      && dUnder.includes(">With the agreed decisions: 43.4 tCO2e, 12.3 tCO2e under the target<"));
    // NARROWED 11 Oct 2026 (the server's new sentence; the gap carries its unit)
    ok("...decisions that no longer apply: the server's sentence in place of the second line, the as-forecast line kept",
      dBad.includes(">The agreed decisions no longer fit the plan (route &#x27;R4&#x27; does not exist), so the plan with them cannot be worked out. A planner needs to set the target again on the Carbon planner.<")
      && !dBad.includes("With the agreed decisions:") && dBad.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target<") && !/undefined|NaN/.test(dBad));
    const dTp = dash(TEAMP), dTc = dash(TEAMC);
    // REVERSED 11 Oct 2026 (the review): it asserted "with the scheme's cut applied to them" for a team code in % mode. A team
    // code's figures are now never compared with the scheme's target, % or cap, and the strip no longer says they are "on the
    // whole approved plan" (they are the team's lines)
    // REVERSED 13 Oct 2026 (each team its share): it asserted "for the whole scheme, not split by team" and no verdict
    ok("⭐ ...a team code: its own share of the target, % or cap, with its own verdicts; no decisions listed; no team id",
      [dTp, dTc].every(o => o.includes("These figures are for your team&#x27;s lines only, against their share of the scheme&#x27;s target: the target split by each team&#x27;s plan with the agreed decisions. The shares add up to the target.")
        && o.includes("As forecast on your team&#x27;s lines: 161.4 tCO2e, 118.0 tCO2e over the target") && o.includes("With the agreed decisions on your team&#x27;s lines: 43.4 tCO2e, on target")
        && !o.includes("agreed decisions</summary>")
        && !o.includes("whole approved plan") && o.includes("All-in: making the material, transport and waste disposal, on the approved plan on your team&#x27;s lines."))
      && dTp.includes("<b>Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s target (73.1% below the approved plan)</b>") && !dTp.includes("scheme&#x27;s cut")
      && dTc.includes("<b>Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s fixed cap of 43.4 tCO2e</b>")
      && !/IPT\d/.test(seg(dTp, "data-carbon-target", "Material demand") + seg(dTc, "data-carbon-target", "Material demand"))
      && !/undefined|NaN/.test(dTp + dTc));
    // ---- 11 Oct 2026: Gate arrivals on the Dashboard, from fixtures/gate_arrivals.json (test_gate_arrivals.py writes it:
    // the planner's month 9 of the §2.6 seed — three gates, one red, one with no check-in typed, one holding). The page shows
    // what the server sends and adds nothing; a team code's response (per_team already stripped) is the same fixture masked here.
    // The panel's own markup is sliced (gaSeg): the carbon target on the same page carries 161.4 too.
    const gaPath = path.join(__dirname, "fixtures", "gate_arrivals.json");
    ok("the gate-arrivals fixture exists (written by test_gate_arrivals.py)", fs.existsSync(gaPath));
    if (fs.existsSync(gaPath)) {
      const GA = JSON.parse(fs.readFileSync(gaPath, "utf8"));
      const gaSeg = (out) => seg(out, 'data-gate-arrivals="', "</section>");
      const gOut = render("the Dashboard renders POPULATED with gate arrivals (initialGates)", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: CT, initialGates: GA, onOpen(){} }));
      const gP = gaSeg(gOut);
      const red = GA.gates.filter(g => g.flag === "red"), untyped = GA.gates.filter(g => g.gate_minutes == null);
      ok("⭐ GATE ARRIVALS: three gates, one red, one untyped, one holding, each a row with its data attribute",
        GA.gates.length === 3 && red.length === 1 && untyped.length === 1 && GA.gates.every(g => gP.includes(`data-ga-gate="${g.gate_id}"`) && gP.includes(`data-ga-flag="${g.flag || "none"}"`))
        && gOut.includes('data-gate-arrivals="set"') && gP.includes('>Gate arrivals<button type="button" class="ibtn" aria-label="About: Gate arrivals"'));   // 13 Oct 2026 (W3, narrowed): + its info box
      ok("🔴 the red gate reads 'Queue likely' once, the untyped 'No check-in time typed' once, the third 'Spacing holds' once — each as the chip's word",
        // 13 Oct 2026 (W6, narrowed): the chip is RowStatus; red is its "bad" tone, once
        (gP.match(/>Queue likely</g) || []).length === 1 && (gP.match(/>No check-in time typed</g) || []).length === 1 && (gP.match(/>Spacing holds</g) || []).length === 1
        && !/amber|Amber/.test(gP) && gP.includes('data-ga-flag="red"') && (gP.match(/data-row-status="bad"/g) || []).length === 1
        && (gP.match(/data-row-status="none"/g) || []).length === 2 && !gP.includes('data-row-status="ok"'));
      ok("⭐ every figure is the server's, formatted to 1 dp, with the gap in the contract's words; the check-in is a word, never a bare 0",
        // 13 Oct 2026 (W6, narrowed): the gap cell is "2.6 min", the sentence and the laden / coming-to-load split are details lines
        GA.gates.every(g => gP.includes(`>${g.arrivals_per_day.toFixed(1)}<`) && (g.gap_minutes == null || (gP.includes(`One every ${g.gap_minutes.toFixed(1)} min if arrivals are spread evenly.`) && gP.includes(`>${g.gap_minutes.toFixed(1)} min<`))))
        && gP.includes(">not typed<") && gP.includes(">2 min a lorry<") && gP.includes(">3 min a lorry<") && !gP.includes(">0 min a lorry<")
        && gP.includes("<dt>Laden a day</dt><dd>0.0</dd></div><div class=\"rd-i\"><dt>Coming to load a day</dt><dd>252.3</dd>")
        && gP.includes("<dt>Laden a day</dt><dd>227.3</dd></div><div class=\"rd-i\"><dt>Coming to load a day</dt><dd>4.5</dd>") && !/undefined|NaN/.test(gP));
      ok("the origin gate carries the share note and the pending gates their pending line; the compound carries neither",
        gP.includes("West pit serves other customers too; Wayscope sees only this scheme&#x27;s share of this gate&#x27;s traffic.")
        && (gP.match(/serves other customers too/g) || []).length === 1
        && (gP.match(/>1 pending line would add 5\.0 a day here once approved\.</g) || []).length === 2
        // 13 Oct 2026 (W6, narrowed): the two note rows became details lines (three notes on two gates, as before)
        && (gP.match(/<dt>Waiting for approval<\/dt>/g) || []).length === 2 && (gP.match(/<dt>Not all of this gate&#x27;s traffic<\/dt>/g) || []).length === 1);
      ok("⭐ team NAMES, every team at the gate, the planner's per-team split (Team 1 161.4 / Team 2 90.9)",
        // 13 Oct 2026 (W6, narrowed): the teams are chips and a details line; each team's figure its own details line
        gP.includes(">Team 1, Team 2<") && gP.includes('<span class="rd-chip">Team 1</span>') && gP.includes("<dt>Team 1, a day</dt><dd>161.4</dd>")
        && gP.includes("<dt>Team 2, a day</dt><dd>90.9</dd>") && gP.includes("<dt>Team 1, a day</dt><dd>140.9</dd>")
        // the gate id is the row's data attribute for these harnesses and nothing else: stripped, no id, location id, route id or scope is left on the page
        // 13 Oct 2026 (W6, narrowed): RowDetails keys its details row by the gate id too (id / aria-controls / data-rd*,
        // attributes nobody reads on screen); those are stripped with the data attribute
        && !/IPT ?[1-6]/.test(gP) && !/G00[1-9]|\bL[1-9]\b|\bR[1-9]\b|scheme</.test(gP.replace(/data-ga-gate="G00\d"|(?:id|aria-controls|data-rd|data-rd-details)="(?:rd-)?ga-G00\d"/g, "")));
      ok("the month's words under the header, and the two notes under the table, in the server's words",
        // NARROWED 11 Oct 2026 (review): "every teams" was ungrammatical — "all teams together"
        gP.includes("Sep 2026: lorries a day at each gate, all teams together, if arrivals are spread evenly across the 10 h shift.") && !gP.includes("every teams")
        && GA.notes.every(n => gP.includes(n.replace(/'/g, "&#x27;"))) && gP.indexOf("</table>") < gP.indexOf("Averages only, if arrivals are spread evenly"));
      const GAT = { ...GA, scope: "team", gates: GA.gates.map(g => ({ ...g, per_team: g.per_team.filter(t => t.team === "Team 2") })) };
      const tOut = render("the Dashboard renders a team code's gate arrivals (per_team already stripped by the server)", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: CT, initialGates: GAT, onOpen(){} }));
      const tP = gaSeg(tOut);
      ok("🔴 a team code's page shows the totals and both names but never the other team's figure",
        // 13 Oct 2026 (W6, narrowed): the same, in the details lines
        tP.includes(">252.3<") && tP.includes(">231.8<") && tP.includes(">Team 1, Team 2<") && !tP.includes("161.4") && !tP.includes("140.9")
        && (tP.match(/<dt>Team 2, a day<\/dt><dd>90\.9</g) || []).length === 2 && !tP.includes("<dt>Team 1, a day") && !/undefined|NaN/.test(tP));
      const eOut = render("the Dashboard renders an EMPTY month of gate arrivals", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: CT, initialGates: { ...GA, month: 11, label: "Nov 2026", gates: [], notes: ["No approved lines in Nov 2026.", GA.notes[GA.notes.length - 1]] }, onOpen(){} }));
      const eP = gaSeg(eOut);
      ok("the empty state names the month and keeps the averages note; no table",
        eOut.includes('data-gate-arrivals="none"') && eP.includes("No approved lines in Nov 2026") && eP.includes('data-empty="none"')
        // NARROWED 11 Oct 2026 (review): the body had the pending rule backwards
        && eP.includes("Pick another month. Pending lines appear as a note until they are approved, then in the figures.") && eP.includes("No hourly peak is typed") && !eP.includes("<table"));
      // a gate listed for its PENDING lines only (nothing approved there this month): the chip says so and claims no spacing
      const pOnly = { ...GA.gates[1], laden_per_day: 0.0, empty_per_day: 0.0, arrivals_per_day: 0.0, gap_minutes: null, flag: null,
                      reason: "No approved arrivals this month.", pending_lines: 1, pending_per_day: 5.0, per_team: [], teams: [] };
      const pOut = render("the Dashboard renders a pending-only gate", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: CT, initialGates: { ...GA, gates: [pOnly] }, onOpen(){} }));
      const pP = gaSeg(pOut);
      ok("🔴 a pending-only gate reads 'No approved arrivals' as the chip's word and 'no approved arrivals' as its gap; never 'Spacing holds' or 'one every —'",
        // 13 Oct 2026 (W6, narrowed): the gap cell reads "none", the details "No approved arrivals."
        (pP.match(/>No approved arrivals</g) || []).length === 1 && pP.includes(">none<") && pP.includes(">No approved arrivals.<") && !pP.includes("Spacing holds") && !/one every/i.test(pP)
        && !pP.includes("—") && pP.includes('data-ga-flag="none"') && pP.includes(">1 pending line would add 5.0 a day here once approved.<") && !/undefined|NaN/.test(pP));
      const selP = seg(gP, '<select class="ga-sel"', "</select>");
      ok("the month select shows the fixture's month in the Dashboard's words (Sep 26), 24 months of the horizon",
        /<option value="9" selected="">Sep 26<\/option>/.test(selP) && (selP.match(/<option/g) || []).length === ctMeta.months.count && (selP.match(/selected/g) || []).length === 1
        && /<select class="ga-sel"[^>]*aria-label="Month"/.test(eP) && /<option value="11" selected="">Nov 26<\/option>/.test(eP));
      ok("🔴 none of the banned words in the rendered panel",
        !/\b(real-time|live tracking|telematics|optimi[sz]\w*|predict\w*|trucks?|secure|booking|peak hour)\b/i.test(gP + tP + eP) && !/\bAI\b/.test(gP + tP + eP));
      // REVERSED 11 Oct 2026 (review): the page once rendered an `unbaked_note` the server never sends. A field the
      // contract does not carry is ignored: no extra note row, nothing of it on the page.
      const uOut = render("the Dashboard renders a gate carrying a field outside the contract", h(Dashboard, { meta: ctMeta, initialData: cl, initialTarget: CT,
        initialGates: { ...GA, gates: GA.gates.map((g, i) => i === 1 ? { ...g, unbaked_note: "One route here is not baked yet." } : g) }, onOpen(){} }));
      ok("a field outside the contract is ignored: the same two note rows, nothing of it on the page",
        // 13 Oct 2026 (W6, narrowed): the note rows are details lines
        (gaSeg(uOut).match(/<dt>Waiting for approval<\/dt>/g) || []).length === 2 && !gaSeg(uOut).includes("not baked yet") && !gP.includes("unbaked"));
      ok("🔴 without initialGates the panel renders nothing (the Dashboard's other render tests keep their shape); the footnote still names the read",
        // 13 Oct 2026 (W3, narrowed): the footnote no longer names the read (the technical guide does; parse_frontend pins it)
        !dSet.includes("data-gate-arrivals") && !dSet.includes("About: Gate arrivals") && !dNone.includes("data-gate-arrivals") && !dNone.includes("ga-table")
        && !dSet.includes("<code>/api/gates/arrivals</code>") && dSet.includes("technical guide</a>"));
    }
    // R2: a cap 2.0 tCO2e over (approved 7 361.1, with the decisions 7 002.8, cap 7 000.8) reads OVER on the Dashboard, as on the
    // Carbon page (the Dashboard used to call any gap within 0.05% of the plan "on target", whatever the mode)
    const dCap2 = dash(CAP2);
    ok("⭐ R2 ...a cap 2.0 tCO2e over reads '2.0 tCO2e over the target' on the Dashboard (it read 'on target' there and 'over' on the Carbon page)",
      dCap2.includes(">With the agreed decisions: 7 002.8 tCO2e, 2.0 tCO2e over the target<") && !dCap2.includes("7 002.8 tCO2e, on target"));

    const rowsCt = cl.lines.map(l => ({ route_id: l.route_id, discipline: l.discipline, section_id: l.section_id, month_index: l.month_index,
      quantity: l.quantity, unit: l.unit, status: l.status, ipt: l.ipt, material_type: l.material_type, material_description: null,
      vehicle_type: l.vehicle_type, submitted_by: "tester", reject_reason: null }));
    const pendN = new Set(cl.lines.filter(l => l.status === "Pending").map(l => `${l.route_id}|${l.discipline}|${l.section_id}`)).size;
    const fc = (ct, extra) => render("the Forecasts page renders with a carbon target state",
      h(Forecasts, { meta: ctMeta, who: "t", access: planner, onEdit(){}, onChanged(){}, initialRows: rowsCt, initialCost: cl, initialTarget: ct, ...(extra || {}) }));
    const fSet = fc(CT);
    // NARROWED 11 Oct 2026 (one way of saying the target: the Dashboard's target sentence, then both figures with the server's
    // verdicts — it printed the three figures with no verdict, so a % target read as missed the moment it was set)
    ok(`⭐ Forecasts: under the header, the target (73.1% below the approved plan = 43.4 tCO2e), as forecast 118.0 over, with the agreed decisions on target, and the ${pendN} pending line(s) would add 5.7`,
      pendN >= 1 && fSet.includes("<b>Carbon (all-in):</b> Target: 73.1% below the approved plan = 43.4 tCO2e<")
      && fSet.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target · With the agreed decisions: 43.4 tCO2e, on target<")
      && fSet.includes(`>The ${pendN} pending line${pendN === 1 ? "" : "s"} would add 5.7 tCO2e.<`)
      && fSet.indexOf('data-carbon-target="set"') > fSet.indexOf(">Forecasts<") && fSet.indexOf('data-carbon-target="set"') < fSet.indexOf("<table")
      && !/undefined|NaN/.test(fSet));
    const fNone = fc(NONE), fLoading = render("the Forecasts page renders a target while the list is still loading",
      h(Forecasts, { meta: ctMeta, who: "t", access: planner, onEdit(){}, onChanged(){}, initialTarget: CT }));
    const fTp = fc(TEAMP, { access: submitter }), fTc = fc(TEAMC, { access: submitter }), fBad = fc(BAD);
    ok("...no target: one line that says so; while the list loads, no pending sentence (the count is the page's own)",
      fNone.includes(">No carbon target set yet. A planner sets it in the Carbon planner.<") && !fNone.includes("Open the Carbon planner")
      // NARROWED 11 Oct 2026 (the shared words)
      && fLoading.includes(">As forecast: 161.4 tCO2e, 118.0 tCO2e over the target") && !fLoading.includes("pending line") && !fLoading.includes("waiting for approval"));
    // NARROWED 11 Oct 2026 (the merge: the segment ran on to "<table" and so took in the page's own Team
    // filter, whose option values are team ids by design; it now stops at that filter row, and each
    // segment must hold the target's line, so the no-id check cannot pass on an empty string)
    const fSegs = [fTp, fTc, fBad].map(o => seg(o, "data-carbon-target", 'data-guide="forecast-status"'));
    const fCap2 = fc(CAP2);
    ok("⭐ R2 ...Forecasts says the same verdicts as the Dashboard: a cap 2.0 tCO2e over reads over",
      fCap2.includes(">As forecast: 7 361.1 tCO2e, 360.3 tCO2e over the target · With the agreed decisions: 7 002.8 tCO2e, 2.0 tCO2e over the target<")
      && fCap2.includes("Target: a fixed cap of 7 000.8 tCO2e (73.1% below the approved plan when it was set)<"));
    // REVERSED 11 Oct 2026 (no team share of the scheme's target): it asserted "target 43.4 (the scheme's 73.1% cut)" for a team code
    // REVERSED 13 Oct 2026 (each team its share): it asserted "for the whole scheme, not split by team" and no verdict
    ok("...a team code: its own share of the target, % or cap, with its verdicts; decisions that no longer apply say so",
      fTp.includes("<b>Carbon (all-in):</b> Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s target (73.1% below the approved plan)<") && !fTp.includes("scheme&#x27;s 73.1% cut")
      && fTp.includes(">As forecast on your team&#x27;s lines: 161.4 tCO2e, 118.0 tCO2e over the target · With the agreed decisions on your team&#x27;s lines: 43.4 tCO2e, on target<")
      && fTc.includes("Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s fixed cap of 43.4 tCO2e<") && !/not split by|not compared/.test(fSegs[0] + fSegs[1])
      && fBad.includes("With the agreed decisions: —<") && fBad.includes("A planner needs to set the target again on the Carbon planner.")
      && fSegs.every(x => x.includes("Carbon (all-in)") && !x.includes("<select"))
      && !/IPT\d/.test(fSegs.join("")) && !/undefined|NaN/.test(fTp + fTc + fBad));

    const pcMeta = { ...meta, months: { start_year: 2026, count: 24 }, routes: [{ route_id: "R1", origin: "Pit", dest: "Site", distance_km: 30 }],
                     materials: ["Small aggregate"], vehicles: [PC.vehicle_type], planning_vehicles: [PC.vehicle_type],
                     factors: { ...meta.factors, material_density_t_per_m3: { "Small aggregate": 1.6, _default: 1.6 }, vehicle_payload_t: { [PC.vehicle_type]: 29, _default: 29 } } };
    const mx = (pv, ct, acc) => render("the Submit matrix renders with the preview's carbon",
      h(Matrix, { meta: pcMeta, who: "t", editTarget: null, vehLang: "en", access: acc || planner, initialCost: pv, initialTarget: ct }));
    const mSet = mx(PC, CT);
    ok("⭐ Submit forecast: Carbon of these cells 28.3 tCO2e (material 22.6 · transport 5.6), the server's basis on hover, in the price strip",
      mSet.includes('data-carbon-cells="1"') && mSet.includes("Carbon of these cells: <b>28.3 tCO2e</b> (material 22.6 · transport 5.6)<")
      && mSet.includes('title="Making the material at the UK Government 2026 factor for aggregates; transport there and back on the routed distance."')
      && !mSet.includes("no route distance yet") && mSet.indexOf('data-cost-strip="1"') < mSet.indexOf('data-carbon-cells="1"')
      && mSet.indexOf('data-carbon-cells="1"') < mSet.indexOf("Movements = loads per working day"));
    // NARROWED 11 Oct 2026 (the review: Submit forecast showed only "approved plan now", which always read far over a % target;
    // it now says the same three things as the Dashboard and Forecasts, with the server's verdicts)
    ok("...and the scheme target beside it, as forecast AND with the agreed decisions, in the Dashboard's words; nothing undefined or NaN",
      mSet.includes(">Target: 73.1% below the approved plan = 43.4 tCO2e · As forecast: 161.4 tCO2e, 118.0 tCO2e over the target · With the agreed decisions: 43.4 tCO2e, on target<")
      && !mSet.includes("approved plan now") && !/undefined|NaN/.test(mSet));
    const mUnr = mx({ ...PC, carbon: { material_t: 22.629, transport_t: null, disposal_t: null, total_t: 22.629, unrouted: true,
      basis: "Making the material at the UK Government 2026 factor for aggregates; transport is not counted until the route has a distance." } }, CT);
    const mTip = mx({ ...PC, carbon: { material_t: null, transport_t: null, disposal_t: 19.554, total_t: 19.554, unrouted: true,
      basis: "Transport is not counted until the route has a distance; disposal by landfill at the UK Government 2026 factor for soils." } }, NONE);
    ok("...an unrouted line says transport is not counted (never estimated); a tip line shows waste disposal only; no target says so",
      mUnr.includes("Carbon of these cells: <b>22.6 tCO2e</b> (material 22.6) · no route distance yet, so transport is not counted<")
      // NARROWED 11 Oct 2026 (one "no target" sentence on all four pages)
      && mTip.includes("Carbon of these cells: <b>19.6 tCO2e</b> (waste disposal 19.6) · no route distance yet") && mTip.includes(">No carbon target set yet. A planner sets it in the Carbon planner.<"));
    const mTp = mx(PC, TEAMP, submitter), mTc = mx(PC, TEAMC, submitter);
    const pcNo = { ...PC }; delete pcNo.carbon;
    const mNo = mx(pcNo, null);
    // REVERSED 11 Oct 2026 (no team share of the scheme's target): it asserted "Target for your team's lines: 43.4 tCO2e"
    // REVERSED 13 Oct 2026 (each team its share): it asserted the scheme's target "not split by team" and no verdict
    ok("...a team code: its own share of the target, % or cap, beside its own lines' figures and verdicts; no carbon block and no target read yet: neither line",
      mTp.includes(">Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s target (73.1% below the approved plan) · As forecast on your team&#x27;s lines: 161.4 tCO2e, 118.0 tCO2e over the target · With the agreed decisions on your team&#x27;s lines: 43.4 tCO2e, on target<")
      && mTc.includes(">Target for your team&#x27;s lines: 43.4 tCO2e, 79.5% of the scheme&#x27;s fixed cap of 43.4 tCO2e · As forecast on your team&#x27;s lines: 161.4 tCO2e")
      && !mNo.includes("data-carbon-cells") && !mNo.includes("data-carbon-target")
      && !/IPT\d/.test([mTp, mTc].map(o => seg(o, 'data-cost-strip="1"', "Movements = loads per working day")).join("")) && !/undefined|NaN/.test(mTp + mTc + mNo));
    const mBad = mx(PC, BAD), mCap2 = mx(PC, CAP2);
    ok("...decisions that no longer apply: 'With the agreed decisions: —' on the line and the server's sentence under it; a cap 2.0 over reads over",
      mBad.includes(" · With the agreed decisions: —<") && mBad.includes('<div class="w-full ct-note">The agreed decisions no longer fit the plan (route &#x27;R4&#x27; does not exist), so the plan with them cannot be worked out. A planner needs to set the target again on the Carbon planner.</div>')
      && mCap2.includes("With the agreed decisions: 7 002.8 tCO2e, 2.0 tCO2e over the target<") && !/undefined|NaN/.test(mBad + mCap2));

    // the big screen's target figure (ctFig, called directly: the Dashboard is NOT rendered in wall mode here)
    const fg = (ct, err) => sandbox.ctFig(ct, err);
    const gS = fg(CT), gC = fg(CAP), gTp = fg(TEAMP), gTc = fg(TEAMC), gB = fg(BAD), gC2 = fg(CAP2);
    ok("⭐ the big screen's figure: the scheme's target 43.4, its sub the mode and both verdicts in the shared words",
      gS.value === "43.4" && gS.sub === "73.1% below the approved plan · as forecast: 118.0 tCO2e over the target · with the agreed decisions: on target"
      && gS.title.startsWith("Target: 73.1% below the approved plan = 43.4 tCO2e. As forecast: 161.4 tCO2e, 118.0 tCO2e over the target. With the agreed decisions: 43.4 tCO2e, on target.")
      && gC.sub.startsWith("fixed cap · as forecast: ") && gC2.sub.endsWith("with the agreed decisions: 2.0 tCO2e over the target"));
    // REVERSED 13 Oct 2026 (each team its share): it asserted '—' for a %, the scheme's cap for a cap, "not split by team"
    const gTx = fg(withS(TEAMX));
    ok("...a team code: its OWN share as the figure, % or cap, the sub naming the share and both verdicts; '—' only with no share",
      gTp.value === "43.4" && gTp.sub === "your share (79.5%) of the scheme's 73.1% below the approved plan · as forecast: 118.0 tCO2e over the target · with the agreed decisions: on target"
      && gTc.value === "43.4" && gTc.sub === "your share (79.5%) of the scheme's fixed cap · as forecast: 118.0 tCO2e over the target · with the agreed decisions: on target"
      && gTx.value === "—" && gTx.sub === "whole scheme: 73.1% below the approved plan; no share while the agreed decisions do not fit the plan"
      && gTx.title.includes("Target: 73.1% below the approved plan for the whole scheme; your team's lines have no share of it while the agreed decisions do not fit the plan"));
    ok("...decisions that no longer apply, no target, a failed read and the wait: each in words, nothing undefined or NaN",
      gB.sub.endsWith("the agreed decisions no longer fit the plan") && fg(NONE).sub === "none set yet"
      && fg(NONE).title === "No carbon target set yet. A planner sets it in the Carbon planner." && fg(null, true).sub === "did not load"
      && fg(null, false).sub === "loading" && !/undefined|NaN/.test(JSON.stringify([gS, gC, gTp, gTc, gB, gC2])));
  }

  // ---- the shared furniture -----------------------------------------------------
  ok("PageHeader renders a title, a subtitle and actions",
    (() => { const o = ReactDOMServer.renderToStaticMarkup(
      h(PageHeader, { title: "T", subtitle: "S", actions: h("button", null, "A") }));
      return o.includes("T") && o.includes("S") && o.includes("<button"); })());
  ok("EmptyState renders its title and body",
    ReactDOMServer.renderToStaticMarkup(h(EmptyState, { title: "T", body: "B" })).includes("B"));

  // ---- Look-ahead v2 (09 Sep evening): the three views, POPULATED ----------------
  // useEffect never runs here, so the page is handed in through `initialPage` — a fixture
  // written by the BACKEND test harness (test_lookahead.py's own scratch database, run
  // through lookahead.page()). The shape the page renders is therefore the shape the
  // server actually produces, not one typed by hand.
  const fixPath = path.join(__dirname, "fixtures", "lookahead_page.json");
  ok("the Look-ahead page fixture exists (written by test_lookahead.py)", fs.existsSync(fixPath));
  const fixture = fs.existsSync(fixPath) ? JSON.parse(fs.readFileSync(fixPath, "utf8")) : null;
  const laMeta = { ...meta, months: { start_year: 2026, count: 60 } };
  if (fixture) {
    // 2026-10-11 (a Sunday): written on a weekend with the clock's date, today was no printed column and
    // the "day headers name today" check below failed on correct output. test_lookahead.py now pins today
    // to a weekday of the commit week (portable.fixture_today); this says so first.
    ok(`the Look-ahead page fixture's today (${fixture.today}) is a weekday inside its commit week (pinned by test_lookahead.py on a weekend)`,
      weekdayInWeek(fixture), `week ${(fixture.commit_week || {}).from}..${(fixture.commit_week || {}).to}`);
    const commitOut = render("the Commit view renders with a populated page",
      h(LookAhead, { meta: laMeta, who: "t", initialPage: fixture, initialView: "commit" }));
    ok("...with the KPI strip, the clash rail and one row per line",
      // 13 Oct 2026 (W6, narrowed): one RowDetails chevron a line, not a ▶
      commitOut.includes("planned this week") && commitOut.includes("+" + (fixture.clashes.count - 3) + " more")
      && (commitOut.match(/class="rd-chev"/g) || []).length === fixture.commit.lines.length);
    // 10 Oct 2026 NARROWED: the 9 px "qty · tr · veh" sub-label went with the one-off styles; the five
    // day columns are counted by their headers (a day name and number), and the caption says the rest
    ok("...the day headers name today, and there are exactly five day columns — Mon–Fri only (10 Sep)",
      commitOut.includes(", today") && !commitOut.includes("0 default")   // 13 Oct 2026 (W6, narrowed): ", today"
      && (commitOut.match(/<th class="num"[^>]*><span[^>]*>(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+/g) || []).length === 5
      && commitOut.includes("Planned quantity by day"));
    // 2026-10-11: the weekend, rendered on purpose: the same page with the server's today on the week's
    // Sunday. No header says today, and the five Mon–Fri columns and one row per line stay.
    const sunOut = render("the Commit view renders the same week on its Sunday (a weekend today)",
      h(LookAhead, { meta: laMeta, who: "t", initialPage: { ...fixture, today: (fixture.commit_week || {}).to }, initialView: "commit" }));
    ok("...on a weekend no day header says today, and there are still exactly five day columns (Mon–Fri) and one row per line",
      isoDow((fixture.commit_week || {}).to) === 0 && TODAY_HEADER.test(commitOut) && !TODAY_HEADER.test(sunOut)
      && (sunOut.match(/<th class="num"[^>]*><span[^>]*>(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+/g) || []).length === 5
      && (sunOut.match(/class="rd-chev"/g) || []).length === fixture.commit.lines.length && !/undefined|NaN/.test(sunOut));   // 13 Oct 2026 (W6, narrowed)
    // 13 Oct 2026 (W6, narrowed): a cell shows ONE unit (the switch); every weekday's trips and vehicles are in the
    // line's by-day table in the details: five rows a line, each with a loads and a lorries figure
    ok("...every weekday cell carries trips and vehicles (baked fixture)",
      (commitOut.match(/<table class="rd-days">/g) || []).length === fixture.commit.lines.length
      && (commitOut.match(/<tr><td>(Mon|Tue|Wed|Thu|Fri) \d+<\/td><td>[\d .]+<\/td><td>[\d .]+<\/td><td>\d[\d ]*<\/td><td>\d[\d ]*<\/td>/g) || []).length >= fixture.commit.lines.length * 5);
    ok("...no stock card on Commit any more (10 Sep) — and no map either under the render harness (initialPage)",
      !commitOut.includes("Stock held") && !commitOut.includes("This week's movements"));
    ok("...Export XLSX and the green Confirm week are in the bar",
      commitOut.includes(">Export XLSX<") && commitOut.includes(">Confirm week<"));
    ok("...nothing renders as 'undefined' or 'NaN'", !/undefined|NaN/.test(commitOut));

    const acctOut = render("the Account view renders with a populated page",
      h(LookAhead, { meta: laMeta, who: "t", initialPage: fixture, initialView: "account" }));
    ok("...with the four KPI cards and the held / applied / waiting states of the fixture",
      acctOut.includes("last week delivered · 98% band") && acctOut.includes("open to calibrate")
      && acctOut.includes(">held<") && acctOut.includes("applied · ") && acctOut.includes(">waiting<"));
    ok("...the confirmed cost box is rendered next to the actual",
      acctOut.includes("The confirmed cost of this week"));
    // 13 Oct 2026 (W3, narrowed): the footer's rule is in the Variance header's info box (dom_frontend opens it)
    ok("...and the Variance header carries the not-reported rule's info box",
      acctOut.includes('aria-label="About: Variance"') && !acctOut.includes("Empty actual is not zero"));

    const hzOut = render("the Horizon view renders with a populated page",
      h(LookAhead, { meta: laMeta, who: "t", initialPage: fixture, initialView: "horizon" }));
    ok("...with the role labels on the columns and no Confirm button",
      hzOut.includes("COMMIT") && hzOut.includes("MAKE-READY") && hzOut.includes("EARLY WARNING")
      && !hzOut.includes(">Confirm week<"));
    ok("...and NO stockpile grid under it any more (10 Sep)", !hzOut.includes("max · opening") && !hzOut.includes("Type what came out"));
    ok("...the Account view carries the account week's stockpiles with one 'out' box each",
      acctOut.includes("Stockpiles · ") && acctOut.includes('aria-label="About: Stockpiles"')   // 13 Oct 2026 (W3, narrowed): the how-to is in the info box
      && (acctOut.match(/placeholder="out —"/g) || []).length === fixture.account.stock.length && fixture.account.stock.length >= 1);
    ok("...and says the fixture's stockpile is OVER, with the same figure the server sent",
      acctOut.includes("OVER by " + Math.round(-fixture.account.stock[0].remaining).toLocaleString("en-US").replace(/,/g, " ")));

    // ---- 10 Sep evening: the fuel widget and Quote + BAF, from test_costing.py's fixture --
    const fuelFixPath = path.join(__dirname, "fixtures", "lookahead_page_fuel.json");
    ok("the fuel page fixture exists (written by test_costing.py)", fs.existsSync(fuelFixPath));
    const fuelFix = fs.existsSync(fuelFixPath) ? JSON.parse(fs.readFileSync(fuelFixPath, "utf8")) : null;
    if (fuelFix) {
      const pct = fuelFix.costing.baf_pct;
      const bafLbl = `BAF ${pct >= 0 ? "+" : ""}${(pct * 100).toFixed(2)} % of quote`;
      const fOut = render("the Commit view renders with the fuel fixture (target + index + base + share)",
        h(LookAhead, { meta: laMeta, who: "t", access: planner, initialPage: fuelFix, initialView: "commit" }));
      // NARROWED (G2): the date is labelled by where the price came from — "bulletin" when
      // fetched, "typed" when an admin typed it (this fixture's index is typed: source manual)
      ok("...the compact widget is in the KPI strip with the index, its dated source and the BAF %",
        fOut.includes('data-fuel-widget="compact"') && fOut.includes("€" + fuelFix.costing.index_eur_per_l.toFixed(3) + " / L")
        && fOut.includes("diesel EE · " + (fuelFix.costing.index_source === "manual" ? "typed" : "bulletin"))
        && fOut.includes(bafLbl));
      ok("...the planned € card counts the target-priced lines and prints the + BAF total beside the quote",
        fOut.includes(`· ${fuelFix.commit.totals.eur_target_lines} at target`) && fOut.includes("+ BAF € ")
        && fOut.includes("€ " + Math.round(fuelFix.commit.totals.eur).toLocaleString("en-US").replace(/,/g, " ")));
      ok("...nothing renders as 'undefined' or 'NaN'", !/undefined|NaN/.test(fOut));
      const fAcct = render("the Account view renders with the fuel fixture",
        h(LookAhead, { meta: laMeta, who: "t", access: planner, initialPage: fuelFix, initialView: "account" }));
      const nTarget = fuelFix.account.rows.filter(r => r.rate_source === "target").length;
      ok("...the strip widget sits above the KPI cards with typeable yard and share boxes for a planner",
        fAcct.includes('data-fuel-widget="strip"') && fAcct.indexOf('data-fuel-widget="strip"') < fAcct.indexOf("last week delivered · 98% band")
        && fAcct.includes("Yard €/L") && fAcct.includes("Fuel share %") && (fAcct.match(/inputmode="decimal"/gi) || []).length >= 2);
      ok("...every target-priced account row carries the 'target' chip and every priced row a + BAF line",
        (fAcct.match(/>target<\/span>/g) || []).length === nTarget && nTarget >= 1
        && (fAcct.match(/\+ BAF € /g) || []).length === fuelFix.account.rows.filter(r => r.planned_eur_adj != null).length);
      const fSub = render("the Account view renders for a SUBMITTER with the fuel fixture",
        h(LookAhead, { meta: laMeta, who: "t", access: submitter, initialPage: fuelFix, initialView: "account" }));
      ok("...whose widget shows the yard and share as text, not inputs",
        fSub.includes('data-fuel-widget="strip"') && !fSub.includes("Yard €/L</span><input"));
      const fCfg = render("the Costing tab renders (no data yet — useEffect never runs here)",
        h(CostingTab, { who: "t", access: planner, token: "", setToken: () => {} }));
      ok("...with the target-rate copy and the config widget's admin controls",
        fCfg.includes("Target rate") && fCfg.includes('data-fuel-widget="config"') && fCfg.includes("Reset the BAF base")
        // NARROWED (H1, 29 Sep): with no data and no tenant country there is no automatic
        // series, so the fetch button is correctly ABSENT here; the manual index stays.
        && !fCfg.includes("Fetch the bulletin now") && !fCfg.includes("DESNZ price now") && fCfg.includes("Use this index") && !/undefined|NaN/.test(fCfg));
      // 10 Sep night: the fair price on the Account view, and the coefficients section on Config
      const nFair = fuelFix.account.rows.filter(r => r.planned_fair_eur != null).length;
      ok("...the Account view has a 'Fair € (model)' column with a figure on every baked row and — on the unbaked one",
        fAcct.includes("Fair € <span") && nFair >= 1
        && (fAcct.match(/title="No fair price: the route is not routed yet/g) || []).length === fuelFix.account.rows.length - nFair);   // 13 Oct 2026 (W3, narrowed): plain words
      ok("...the KPI caption on Commit carries the fair total and how many lines it covers",
        fuelFix.commit.totals.fair_eur != null && fOut.includes(`(model, ${fuelFix.commit.totals.fair_lines} of ${fuelFix.commit.totals.lines})`));
      const fileDoc = { fair_price: { driver_eur_per_h: 20, vehicle_standing_eur_per_h: 16, running_eur_per_km: 0.12, margin_pct: 8,
        consumption: { l_per_100km_per_tonne: 0.4, rigid: { l_per_100km_empty: 27 }, artic: { l_per_100km_empty: 23.6 } },
        season: { winter_months: [11, 12, 1, 2, 3], winter_consumption_uplift_pct: 8, thaw_months: [3, 4] } } };
      const fCfg2 = render("the Costing tab renders the fair-price section from the FILE when the document has no block",
        h(CostingTab, { who: "t", access: planner, token: "", setToken: () => {}, doc: { vehicles: {} }, upd: () => {}, fileDoc }));
      ok("...with the file's values in the inputs, the 'no block yet' note, and the three assumption labels",
        fCfg2.includes('data-fair-price-section="1"') && fCfg2.includes('value="20"') && fCfg2.includes('value="23.6"')
        && fCfg2.includes("the live document has no fair_price block yet") && (fCfg2.match(/ASSUMPTION/g) || []).length === 3 && !/undefined|NaN/.test(fCfg2));
      const fCfg3 = render("...and from the DOCUMENT when it has one",
        h(CostingTab, { who: "t", access: planner, token: "", setToken: () => {}, doc: { fair_price: { ...fileDoc.fair_price, driver_eur_per_h: 25 } }, upd: () => {}, fileDoc }));
      ok("...the document's value wins and the note is gone", fCfg3.includes('value="25"') && !fCfg3.includes("no fair_price block yet"));
      const fNone = render("the widget renders with NO data at all", h(FuelWidget, { who: "t", access: planner, mode: "strip", initial: null }));
      ok("...as 'Index unavailable — type a price' for a planner, and nothing undefined",
        fNone.includes("Index unavailable — type a price") && !/undefined|NaN/.test(fNone));
      const fStale = render("the widget renders a stale index", h(FuelWidget, { who: "t", access: planner, mode: "compact",
        initial: { ...fuelFix.costing, index_eur_per_l: null } }));
      ok("...a compact card with no index says so instead of a price", fStale.includes("Index unavailable"));
    }

    // the empty page: no lines, no account, no horizon — every view has an EmptyState
    const empty = { ...fixture, commit: { ...fixture.commit, lines: [], totals: {} }, account: { week: null, rows: [] },
                    horizon: { rows: [], from_month: 9, to_month: 10, roles: {} }, clashes: { flags: [], count: 0, sources: {} }, stock: [] };
    for (const v of ["commit", "account", "horizon"]) {
      const o = render(`the ${v} view renders its empty state`, h(LookAhead, { meta: laMeta, who: "t", initialPage: empty, initialView: v }));
      // 10 Oct 2026: NARROWED — the family card is marked data-empty; the dashed border went with the one-off styles
      ok(`...${v}: an EmptyState, and nothing undefined`, o.includes('data-empty="') && !/undefined|NaN/.test(o));
    }
  }

  // ---- 11 Oct 2026: the demo bar, rendered in the App shell --------------------------------------------------
  // App renders here on its first (public) view: no effect runs, so no map has announced its tour and the bar has
  // no Guide yet; that path is exercised in dom_frontend.js. This proves the bar mounts between the header and
  // <main> without touching the stubbed document, carries the tenant's words, and is absent for a real tenant.
  {
    const { App, DemoBar } = sandbox;
    const N = "Fictional demo scheme · nothing here is real";
    ok("App and DemoBar are defined", typeof App === "function" && typeof DemoBar === "function");
    vm.runInContext(`TENANT.name = "Wolds Link"; TENANT.demo_notice = ${JSON.stringify(N)};`, sandbox);
    const appOut = render("⭐ App renders with a demo tenant (the stubbed document has no querySelector, so the bar reads none while rendering)", h(App));
    const iH = appOut.indexOf("</header>"), iB = appOut.indexOf('<div class="demo-bar"'), iM = appOut.indexOf("<main");
    ok("⭐ ...the bar sits straight after the header and before <main>", iH > 0 && iB === iH + "</header>".length && iM > iB);
    ok("...with the tenant's words in the bar's text span, and no Guide before the map says its tour is ready",
      appOut.includes(`<span class="demo-bar-text" title="${N}">${N}</span>`) && !appOut.includes("demo-bar-guide") && !appOut.includes("has-guide"));
    ok("...the header has no badge and no Guide button any more", !appOut.includes("demo-badge") && !/>Guide</.test(appOut.slice(0, iH)));
    ok("...and the public map's iframe is the EMBEDDED map", /<iframe src="\/map\/\?embed=1&amp;v=\d+" title="Public Route Map"/.test(appOut));
    const withGuide = render("the bar renders with a Guide to replay", h(DemoBar, { onGuide: () => {} }));
    ok("...the Guide button at its end, and the has-guide slot", withGuide.startsWith('<div class="demo-bar has-guide" role="note">')
      && withGuide.endsWith('<button type="button" class="demo-bar-guide" title="Replay the guide for this page">Guide</button></div>'));
    const noGuide = render("the bar renders with no tour to replay (the sign-in view)", h(DemoBar, { onGuide: null }));
    ok("...the notice alone, no button", noGuide === `<div class="demo-bar" role="note"><span class="demo-bar-text" title="${N}">${N}</span></div>`);
    const long = "x".repeat(120);
    vm.runInContext(`TENANT.demo_notice = ${JSON.stringify(long)};`, sandbox);
    ok("a 120-character notice (the validator's limit) is rendered whole; the CSS ends it in an ellipsis",
      ReactDOMServer.renderToStaticMarkup(h(DemoBar, { onGuide: () => {} })).includes(`>${long}</span>`));
    vm.runInContext("TENANT.demo_notice = null;", sandbox);
    const realOut = render("App renders for a real tenant (no notice)", h(App));
    ok("🔴 a real tenant gets no bar and no Guide anywhere", !realOut.includes("demo-bar") && !/>Guide</.test(realOut)
      && ReactDOMServer.renderToStaticMarkup(h(DemoBar, { onGuide: () => {} })) === "");
    vm.runInContext('delete TENANT.demo_notice; TENANT.name = "Wayscope";', sandbox);
  }
}

console.log();
for (const f of fail) console.log("  FAIL:", f);
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
