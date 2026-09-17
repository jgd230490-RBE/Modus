/*
 * tools/make_guide_images.js — the user guide's explanatory figures and its screenshot
 * placeholders, drawn in the Modus theme. Modus G2, 16 Sep 2026.
 *
 *     NODE_PATH=$(npm root -g) node backend/tools/make_guide_images.js          # both sets
 *     NODE_PATH=$(npm root -g) node backend/tools/make_guide_images.js figures  # only fig-*.png
 *     NODE_PATH=$(npm root -g) node backend/tools/make_guide_images.js holders  # only the S and M placeholders
 *
 * Needs Playwright with a Chromium it can launch. Writes into frontend/help/media/.
 *
 * FIGURES (fig-*.png) are diagrams: they explain how the numbers are built and carry no
 * data from anyone's project. They are drawn from the HTML below, so an edit to a figure
 * is an edit to this file, not to a picture.
 *
 * PLACEHOLDERS (S01–S15, M01–M08 except M04) stand where the guide's screenshots go.
 * Each says, on the image itself, that it is NOT a capture and how to make the real one:
 * import the demo package on a deployment, bake the network, then run
 * backend/tools/capture_guide.js. A placeholder that looked like a screenshot would be a
 * false caption — the previous guide had exactly that bug inside its PNGs.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const MEDIA = path.join(ROOT, "frontend", "help", "media");
const which = process.argv[2] || "all";

// ---- the Modus theme (frontend :root tokens) ------------------------------------------
const T = {
  ink: "#0F172A", body: "#334155", muted: "#64748B", line: "#E2E8F0", panel: "#F8FAFC",
  accent: "#2563EB", accentSoft: "#EFF6FF", ok: "#059669", okSoft: "#ECFDF5",
  warn: "#D97706", warnSoft: "#FFFBEB", clash: "#DC2626", clashSoft: "#FEF2F2",
};
const FONT = `Inter, "Segoe UI", system-ui, "DejaVu Sans", Arial, sans-serif`;
const MONO = `"JetBrains Mono", Consolas, "DejaVu Sans Mono", monospace`;

const BASE_CSS = `
*{box-sizing:border-box;margin:0;padding:0}
body{font:15px/1.45 ${FONT};color:${T.body};background:#fff;padding:36px 40px;width:2080px}
h1{font-size:30px;font-weight:700;color:${T.ink};letter-spacing:-.01em;margin-bottom:26px}
h1 small{font-weight:500;color:${T.muted};font-size:20px;margin-left:10px}
.card{border:1.5px solid ${T.line};border-radius:14px;background:${T.panel};padding:20px 24px}
.card h3{font-size:21px;color:${T.ink};margin-bottom:8px}
.card p,.card li{font-size:18px;color:${T.body}}
.muted{color:${T.muted}}
.accent{border-color:${T.accent};background:${T.accentSoft}}
.ok{border-color:${T.ok};background:${T.okSoft}}
.warn{border-color:${T.warn};background:${T.warnSoft}}
.row{display:flex;gap:18px;align-items:stretch}
code,.mono{font-family:${MONO};font-size:17px;color:${T.ink}}
`;

function page(title, inner, extraCss = "") {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}${extraCss}</style></head>
<body><h1>${title}</h1>${inner}</body></html>`;
}

// ---- figure 1: from a typed quantity to trucks on the road ---------------------------
function figNumbers() {
  const steps = [
    ["Quantity", "what you typed:<br>m³, tonnes or vehicles<br>per month", ""],
    ["Tonnes", "m³ × density of the<br>material category<br><span class=muted>(Config › Materials)</span>", ""],
    ["Trips", "tonnes ÷ payload of<br>the vehicle<br><span class=muted>(Config › Vehicles)</span>", ""],
    ["Trips per day", "÷ working days (22 per month), or week ÷ 5 on the Look-ahead", ""],
    ["Vehicles", "trips per day ÷ what one truck can do in a 10 h shift on that route's baked cycle", "accent"],
    ["km · t·km · CO₂e · cost", "trips × routed km; tonnes × km basis; km × kg CO₂e/km; typed route rates", "ok"],
  ];
  const boxes = steps.map(([h, p, cls], i) =>
    `<div class="card ${cls}" style="flex:1;text-align:center"><h3>${h}</h3><p>${p}</p></div>` +
    (i < steps.length - 1 ? `<div class="arrow">›</div>` : "")).join("");
  return page("From a forecast to trucks on the road — how each number is derived",
    `<div class="row">${boxes}</div>
     <div class="card warn" style="margin-top:26px">
       <h3>What this means when you read a figure</h3>
       <p>Payloads are planning figures, not weighbridge values. Distances and drive times come from truck routing for that
       vehicle, both legs; the cycle includes load, unload and gate induction minutes. A route not baked for the vehicle
       shows “not baked” or “—”, never an estimate. Carbon uses the emission factor per vehicle type in Config; treat it as a
       planning figure. Money is in your organisation's currency — no exchange rate is ever applied.</p>
     </div>`,
    `.arrow{font-size:46px;color:${T.muted};font-weight:300;line-height:1;align-self:center}`);
}

// ---- figure 3: the staff app, pages in the left rail ---------------------------------
function figAppMap() {
  const col = (title, who, items, cls = "") => `
    <div class="card ${cls}" style="flex:1">
      <h3 style="font-size:24px">${title}</h3><p class="muted" style="font-style:italic;margin-bottom:14px">${who}</p>
      ${items.map(([h, p]) => `<div class="item"><b>${h}</b><p>${p}</p></div>`).join("")}
    </div>`;
  return page("The staff app — pages in the left rail",
    `<div class="row">
      ${col("Plan", "all roles", [
        ["Dashboard", "KPIs, charts, per-route table, stockpile capacity by week"],
        ["Submit forecast", "one line: route, discipline, work section, material, vehicle, unit, months"],
        ["Forecasts", "every line you may see; approve / reject / edit / withdraw; CSV"]])}
      ${col("Track", "all roles — filtered per team on the server", [
        ["Look-ahead", "Account (last week) · Commit (this / next week) · Horizon"]])}
      ${col("Data", "planners and admins only", [
        ["Locations", "sites, gates, stockpile capacity"],
        ["Routes", "bake per vehicle, alternatives, planning rates, road-restriction check where connected"],
        ["Zones", "disruption zones and temporary haul roads"],
        ["Config", "vehicles, materials, planning constants, seasonal windows, organisation settings"]], "accent")}
      ${col("Map", "all roles", [["Route map", "the corridor map inside the app"]])}
    </div>
    <p class="muted" style="margin-top:20px;font-style:italic;font-size:18px">Sign-in: name + access code. The rail remembers the last page; a page the role cannot see falls back to the Dashboard.</p>`,
    `.item{background:#fff;border:1.5px solid ${T.line};border-radius:10px;padding:12px 16px;margin-bottom:12px}
     .item b{display:block;color:${T.ink};font-size:20px;margin-bottom:2px}.item p{font-size:17px}`);
}

// ---- figure 27: the haul cycle -----------------------------------------------------------
function figHaulCycle() {
  return page("The haul cycle — where every fleet-size figure comes from",
    `<div class="row" style="align-items:center;gap:0">
       <div class="card ok" style="width:380px;text-align:center"><h3>Origin</h3><p>quarry / port / railhead<br>exit gate (or default gate,<br>or the site marker)</p></div>
       <div style="flex:1;padding:0 18px">
         <div class="leg"><span class="lab">LADEN leg — truck routing at gross weight → distance, drive time</span><div class="bar laden"></div></div>
         <p class="muted" style="text-align:center;font-style:italic;margin:14px 0">both legs stored per vehicle profile (alternative 0 = primary)</p>
         <div class="leg"><div class="bar empty"></div><span class="lab">RETURN leg — routed separately at empty weight → may use roads the laden truck cannot</span></div>
       </div>
       <div class="card accent" style="width:380px;text-align:center"><h3>Destination</h3><p>site / stockpile / compound<br>entry gate<br>induction minutes here</p></div>
     </div>
     <div class="row" style="margin-top:24px">
       <div class="card" style="flex:1"><h3>Turnaround (per vehicle, from Config)</h3>
         <p>load minutes + unload minutes (e.g. artic tipper 15 + 9, artic flatbed 25 + 20)<br>
         + gate induction at each arrival gate, once per cycle<br>
         + gate-to-face travel — a flat figure, or the drawn haul road's own time (never both)</p></div>
       <div class="card" style="flex:1"><h3>Substitutions that stay auditable</h3>
         <p>Temporary haul road: its stretch timed at length ÷ assigned speed; the routing service's own figure is kept beside it.<br>
         Zones that affect routing: their bounding box is sent to the routing service as an area to avoid.</p></div>
     </div>
     <div class="card" style="margin-top:24px;background:#fff;border-color:${T.ink}">
       <h3>Formulas</h3>
       <p class="mono">cycle_hr &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= laden drive + return drive + turnaround</p>
       <p class="mono">trips_per_day = floor(shift hours ÷ cycle_hr) &nbsp;&nbsp;<span class="muted">shift = 10 h (Config › Planning)</span></p>
       <p class="mono">trips &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= ceil(tonnes ÷ payload) &nbsp;&nbsp;&nbsp; vehicles = ceil(trips per day ÷ trips_per_day)</p>
       <p class="mono">km &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= trips × routed km &nbsp;&nbsp;&nbsp; t·km = tonnes × basis km &nbsp;&nbsp;&nbsp; CO₂e = km × kg CO₂e/km</p>
     </div>`,
    `.leg{display:flex;align-items:center;gap:14px}.lab{font-size:17px;color:${T.muted};white-space:nowrap}
     .bar{flex:1;height:0;border-top:5px solid ${T.ok};position:relative}
     .bar.laden:after{content:"";position:absolute;right:-4px;top:-14px;border-left:22px solid ${T.ok};border-top:11px solid transparent;border-bottom:11px solid transparent}
     .bar.empty{border-top:5px dashed ${T.warn}}
     .bar.empty:before{content:"";position:absolute;left:-4px;top:-14px;border-right:22px solid ${T.warn};border-top:11px solid transparent;border-bottom:11px solid transparent}
     .mono{margin:6px 0}`);
}

// ---- figure 9: the weekly rhythm ---------------------------------------------------------
function figRhythm() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri"].map(d =>
    `<div class="card ${d === "Thu" ? "accent" : ""}" style="flex:1;text-align:center;padding:14px"><h3 style="margin:0">${d}</h3></div>`).join("");
  return page("The weekly rhythm — what a planner does on the Look-ahead",
    `<div class="row">${days}</div>
     <div class="row" style="margin-top:22px">
       <div class="card ok" style="flex:2"><h3>Monday · Account</h3>
         <p>Type last week's actual quantity and, if known, the invoiced cost per line. Note the reason if short.<br>
         Type stock consumed per stockpile (“out”).<br>Press “spread on this week” where a shortfall must be carried.</p></div>
       <div class="card accent" style="flex:2"><h3>Any day · Commit</h3>
         <p>Check the grid: quantity, trips and vehicles per day per line.<br>Type over a day if the site's plan differs.<br>
         Read the clash rail — flags, never blocks.<br>Confirm the week once it is right; export XLSX / PDF for hauliers.</p></div>
       <div class="card" style="flex:1.4"><h3>Thursday · next week</h3>
         <p>Switch to “Commit · next week” and commit it while this week is still running. A second spread carries only the difference.</p></div>
     </div>
     <div class="card" style="margin-top:22px"><h3>Horizon</h3>
       <p>Week totals for this month and next — 4 or 5 columns per month, each headed with its Monday–Sunday dates; the commit week is highlighted. Nothing is confirmed here.<br>
       The Dashboard's Stockpile capacity panel reads the balances you typed on Account; the route map shows the same month's traffic.</p></div>`);
}

// ---- figure 8: calendar weeks --------------------------------------------------------------
function figWeeks() {
  const rows = [
    ["Sep wk 1", ["31 Aug", "1", "2", "3", "4", "5", "6"], "Account · last week", ""],
    ["Sep wk 2", ["7", "8", "9", "10", "11", "12", "13"], "Commit · this week", "commit"],
    ["Sep wk 3", ["14", "15", "16", "17", "18", "19", "20"], "Commit · next week (Thursday)", ""],
    ["Sep wk 4", ["21", "22", "23", "24", "25", "26", "27"], "Horizon", "plain"],
    ["Oct wk 1", ["28", "29", "30", "1 Oct", "2", "3", "4"], "Horizon — October (its Thursday is 1 Oct)", "oct"],
  ];
  const head = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(d =>
    `<div class="hd ${d === "Thu" ? "thu" : ""}">${d}</div>`).join("");
  const body = rows.map(([lab, ds, note, kind]) => {
    const cells = ds.map((d, i) => {
      const we = i >= 5;
      const today = kind === "commit" && d === "10";
      const sub = we ? `<span class="z">0</span>` : (kind === "plain" || kind === "oct" ? "" : `<span class="s">week ÷ 5</span>`);
      return `<div class="c ${we ? "we" : ""} ${kind === "commit" && !we ? "cw" : ""} ${kind === "oct" && !we ? "oc" : ""} ${today ? "today" : ""}">${today ? "<b>" + d + "</b>" : d}${sub}</div>`;
    }).join("");
    return `<div class="lab">${lab}</div>${cells}<div class="note ${kind === "commit" ? "cn" : ""}">${note}</div>`;
  }).join("");
  return page("Calendar weeks — how a month becomes weeks and days <small>(September 2026)</small>",
    `<div class="grid"><div></div>${head}<div></div>${body}</div>
     <p style="text-align:center;margin:10px 0 0 -300px;color:${T.clash};font-style:italic;font-size:18px">Thursday decides the month (ISO 8601)</p>
     <div class="card" style="margin-top:20px;background:#fff;border-color:${T.ink}"><h3>Rules</h3>
       <p>A week is Monday–Sunday and belongs to the month that holds its Thursday. A month has 4 or 5 weeks (September 2026: 4; October and December 2026: 5).<br>
       The approved month quantity splits equally over its weeks (÷ 4 or ÷ 5); each week splits equally over Monday–Friday; Saturday and Sunday default to 0.<br>
       Derived weeks and days refresh when the parent changes; anything typed (edited) or confirmed holds and is flagged instead. “Today” is Thu 10 Sep in this picture.</p></div>`,
    `.grid{display:grid;grid-template-columns:150px repeat(7,165px) 1fr;gap:10px;align-items:center}
     .hd{text-align:center;font-weight:700;color:${T.muted};font-size:19px}.hd.thu{color:${T.clash}}
     .lab{font-weight:700;color:${T.ink};font-size:19px;text-align:right;padding-right:6px}
     .c{height:74px;border:1.5px solid ${T.line};border-radius:9px;background:${T.panel};padding:8px 12px;font-size:19px;color:${T.ink};display:flex;flex-direction:column;justify-content:space-between}
     .c .s{font-size:15px;color:${T.ok}}.c .z{font-size:15px;color:${T.muted}}
     .c.we{color:${T.muted}}.c.cw{background:${T.accentSoft}}.c.oc{background:${T.warnSoft}}
     .c.today{border:3px solid ${T.clash}}
     .note{font-style:italic;color:${T.muted};font-size:18px;padding-left:8px}.note.cn{color:${T.accent}}`);
}

// ---- placeholders ----------------------------------------------------------------------
const HOLDERS = {
  S01: ["The sign-in screen", "the site address, before signing in", "app"],
  S02: ["The Dashboard — KPI tiles and charts", "Dashboard, Approved, the demo's four months", "app"],
  S03: ["The Stockpile capacity panel on the Dashboard", "Dashboard, scrolled to Stockpile capacity", "app"],
  S04: ["Submit forecast — one line across a year, with the totals strip", "Submit forecast, a demo route picked", "app"],
  S05: ["Forecasts — the ledger with status chips and actions (planner view)", "Forecasts, as the planner", "app"],
  S06: ["Commit view — KPI strip, clash rail and the Monday–Friday grid", "Look-ahead › Commit", "app"],
  S07: ["A row expanded, and the map of this week's lines under the grid", "Look-ahead › Commit, first row expanded", "app"],
  S08: ["Account view — planned, actual, variance, cost, and the Stockpiles block", "Look-ahead › Account", "app"],
  S09: ["Horizon — week totals for this month and next", "Look-ahead › Horizon", "app"],
  S10: ["The Confirm week dialog", "Look-ahead › Commit next week › Confirm week", "app"],
  S11: ["Locations — the map and the edit form with gates and stockpile capacity", "Locations, a stockpile selected", "app"],
  S12: ["Routes — a route expanded: bake status, analysis, alternatives, vehicles, planning block", "Routes, a baked route expanded", "app"],
  S13: ["Zones — a disruption zone and a haul road with speed and mode", "Zones, the demo haul road selected", "app"],
  S14: ["Config — the Vehicles tab", "Config › Vehicles", "app"],
  S15: ["The supplier PDF — one row per line, Monday to Friday, coordinates, route map", "Look-ahead › PDF, first page", "pdf"],
  M01: ["The route map — corridor view with the control panel open", "/map/, corridor zoom", "map"],
  M02: ["The alignment popup — team, work section and chainage", "/map/, a band clicked", "map"],
  M03: ["Sites and assets — the stockpile gauge and its popup", "/map/, a stockpile clicked", "map"],
  M05: ["A road restriction and its verdict for the vehicle", "/map/ on a tenant with a restriction provider", "map"],
  M06: ["The timeline playing — the KPI panel, callouts and in-use marks", "/map/, timeline on October", "map"],
  M07: ["The satellite basemap under routes and alignment", "/map/, Basemap › Satellite", "map"],
  M08: ["Street View from a site popup", "/map/, a quarry clicked, Street View", "map"],
};

function holder(code, [caption, where, kind]) {
  const chrome = kind === "app"
    ? `<div class="hdr"><span class="brand">Modus</span><span class="pill"></span><span class="pill"></span></div>
       <div class="rail">${"<i></i>".repeat(9)}</div>`
    : kind === "map"
      ? `<div class="side">${"<i></i>".repeat(12)}</div><div class="mapbg"></div>`
      : `<div class="sheet">${"<i></i>".repeat(14)}</div>`;
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{width:1440px;height:760px;font:16px/1.5 ${FONT};background:${T.panel};position:relative;overflow:hidden}
    .hdr{position:absolute;left:0;right:0;top:0;height:46px;background:${T.ink};display:flex;align-items:center;gap:14px;padding:0 20px}
    .brand{color:#fff;font-weight:700;font-size:17px;margin-right:auto}.pill{width:90px;height:22px;border-radius:6px;background:rgba(255,255,255,.14)}
    .rail{position:absolute;left:0;top:46px;bottom:0;width:48px;background:#fff;border-right:1px solid ${T.line};padding-top:14px}
    .rail i{display:block;width:18px;height:18px;border-radius:5px;background:${T.line};margin:0 auto 16px}
    .side{position:absolute;left:0;top:0;bottom:0;width:250px;background:#fff;border-right:1px solid ${T.line};padding:24px 18px}
    .side i{display:block;height:14px;border-radius:4px;background:${T.line};margin-bottom:18px}
    .side i:nth-child(3n){width:60%}
    .mapbg{position:absolute;left:250px;right:0;top:0;bottom:0;background:
      repeating-linear-gradient(0deg,transparent 0 59px,${T.line} 59px 60px),
      repeating-linear-gradient(90deg,transparent 0 59px,${T.line} 59px 60px)}
    .sheet{position:absolute;left:120px;right:120px;top:40px;bottom:-40px;background:#fff;border:1px solid ${T.line};padding:40px}
    .sheet i{display:block;height:12px;border-radius:3px;background:${T.line};margin-bottom:22px}
    .card{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:760px;background:#fff;
      border:2px dashed ${T.muted};border-radius:16px;padding:34px 40px;text-align:left;box-shadow:0 10px 30px rgba(15,23,42,.08)}
    .tag{display:inline-block;font:600 13px/1 ${FONT};letter-spacing:.08em;text-transform:uppercase;color:${T.warn};
      background:${T.warnSoft};border:1px solid ${T.warn};border-radius:999px;padding:6px 12px;margin-bottom:16px}
    h2{font-size:26px;color:${T.ink};line-height:1.25;margin-bottom:12px}
    p{color:${T.body};font-size:17px;margin-bottom:8px}
    code{font:15px ${MONO};background:${T.panel};border:1px solid ${T.line};border-radius:5px;padding:1px 6px;color:${T.ink}}
    .id{position:absolute;right:18px;bottom:14px;font:600 14px ${MONO};color:${T.muted}}
  </style></head><body>${chrome}
  <div class="card">
    <span class="tag">Placeholder — not a screenshot</span>
    <h2>${caption}</h2>
    <p><b>Capture:</b> ${where}.</p>
    <p>Import <code>demo/uk-corridor.package.json</code> on a deployment, bake the network, then run
       <code>backend/tools/capture_guide.js</code> — it replaces this file with the real screen.</p>
  </div>
  <div class="id">${code}.png</div>
  </body></html>`;
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 1 });
  const pg = await ctx.newPage();
  const out = [];
  if (which === "all" || which === "figures") {
    const figs = { "fig-numbers.png": figNumbers(), "fig-app-map.png": figAppMap(), "fig-haul-cycle.png": figHaulCycle(),
                   "fig-rhythm.png": figRhythm(), "fig-weeks.png": figWeeks() };
    for (const [name, html] of Object.entries(figs)) {
      await pg.setViewportSize({ width: 2080, height: 600 });
      await pg.setContent(html, { waitUntil: "load" });
      const h = await pg.evaluate(() => Math.ceil(document.body.getBoundingClientRect().height) + 36);
      await pg.setViewportSize({ width: 2080, height: h });
      await pg.screenshot({ path: path.join(MEDIA, name), clip: { x: 0, y: 0, width: 2080, height: h } });
      out.push(name);
    }
  }
  if (which === "all" || which === "holders") {
    await pg.setViewportSize({ width: 1440, height: 760 });
    for (const [code, spec] of Object.entries(HOLDERS)) {
      await pg.setContent(holder(code, spec), { waitUntil: "load" });
      await pg.screenshot({ path: path.join(MEDIA, code + ".png"), clip: { x: 0, y: 0, width: 1440, height: 760 } });
      out.push(code + ".png");
    }
  }
  await browser.close();
  console.log(`wrote ${out.length} images into frontend/help/media/: ${out.join(", ")}`);
})().catch(e => { console.error(e); process.exit(1); });
